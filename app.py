import os
from datetime import datetime, timezone

from flask import Flask, jsonify, redirect, render_template, request, url_for

from models import Alert, Holding, Notification, PortfolioSnapshot, RealizedTrade, Ticker, db
from scheduler import start_scheduler
from screeners import list_screeners, run_screener
from stock_data import fetch_history, fetch_quote, symbol_exists

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def create_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.join(BASE_DIR, 'stock_monitor.db')}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["POLLING_ENABLED"] = True

    db.init_app(app)

    with app.app_context():
        db.create_all()

    return app


app = create_app()


def _stock_detail_context(symbol, period, origin):
    symbol = symbol.strip().upper()
    origin = origin if origin in ("dashboard", "screeners") else "dashboard"
    ticker = Ticker.query.filter_by(symbol=symbol).first()
    if ticker:
        price, change_pct = ticker.last_price, ticker.last_change_pct
    else:
        price, change_pct = fetch_quote(symbol)
    history = fetch_history(symbol, period=period)
    return {
        "symbol": symbol,
        "ticker": ticker,
        "price": price,
        "change_pct": change_pct,
        "history": history,
        "period": period,
        "origin": origin,
        "next_url": url_for(origin) + f"?selected={symbol}",
    }


@app.route("/stocks/<symbol>")
def stock_fragment(symbol):
    period = request.args.get("period", "6mo")
    origin = request.args.get("origin", "dashboard")
    return render_template("_stock_detail.html", **_stock_detail_context(symbol, period, origin))


@app.route("/")
def dashboard():
    tickers = Ticker.query.order_by(Ticker.symbol).all()
    unread_count = Notification.query.filter_by(read=False).count()
    selected_symbol = request.args.get("selected", "").strip().upper() or None
    detail_ctx = (
        _stock_detail_context(selected_symbol, request.args.get("period", "6mo"), "dashboard")
        if selected_symbol
        else {}
    )
    return render_template(
        "dashboard.html",
        tickers=tickers,
        unread_count=unread_count,
        selected_symbol=selected_symbol,
        **detail_ctx,
    )


@app.route("/tickers", methods=["POST"])
def add_ticker():
    symbol = request.form.get("symbol", "").strip().upper()
    next_url = request.form.get("next")
    origin = request.form.get("origin", "dashboard")
    if not symbol:
        return redirect(next_url or url_for("dashboard"))

    if not Ticker.query.filter_by(symbol=symbol).first():
        if not symbol_exists(symbol):
            error = f"Could not find symbol '{symbol}'."
            if origin == "screeners":
                return render_template(
                    "screeners.html", screener_names=list_screeners(), error=error
                )
            tickers = Ticker.query.order_by(Ticker.symbol).all()
            return render_template(
                "dashboard.html",
                tickers=tickers,
                unread_count=Notification.query.filter_by(read=False).count(),
                error=error,
            )
        price, change_pct = fetch_quote(symbol)
        db.session.add(
            Ticker(symbol=symbol, last_price=price, last_change_pct=change_pct)
        )
        db.session.commit()

    return redirect(next_url or url_for("dashboard"))


@app.route("/tickers/<int:ticker_id>/delete", methods=["POST"])
def delete_ticker(ticker_id):
    ticker = Ticker.query.get_or_404(ticker_id)
    next_url = request.form.get("next")
    db.session.delete(ticker)
    db.session.commit()
    return redirect(next_url or url_for("dashboard"))


@app.route("/tickers/<int:ticker_id>")
def ticker_detail(ticker_id):
    ticker = Ticker.query.get_or_404(ticker_id)
    period = request.args.get("period", "6mo")
    history = fetch_history(ticker.symbol, period=period)
    return render_template("ticker.html", ticker=ticker, history=history, period=period)


@app.route("/tickers/<int:ticker_id>/alerts", methods=["POST"])
def add_alert(ticker_id):
    ticker = Ticker.query.get_or_404(ticker_id)
    direction = request.form.get("direction")
    threshold = request.form.get("threshold", type=float)
    next_url = request.form.get("next")
    if direction in ("above", "below") and threshold is not None:
        db.session.add(Alert(ticker_id=ticker.id, direction=direction, threshold=threshold))
        db.session.commit()
    return redirect(next_url or url_for("ticker_detail", ticker_id=ticker_id))


@app.route("/alerts/<int:alert_id>/delete", methods=["POST"])
def delete_alert(alert_id):
    alert = Alert.query.get_or_404(alert_id)
    ticker_id = alert.ticker_id
    next_url = request.form.get("next")
    db.session.delete(alert)
    db.session.commit()
    return redirect(next_url or url_for("ticker_detail", ticker_id=ticker_id))


@app.route("/notifications")
def notifications():
    items = Notification.query.order_by(Notification.created_at.desc()).all()
    for n in items:
        n.read = True
    db.session.commit()
    return render_template("notifications.html", notifications=items)


@app.route("/api/notifications/unread-count")
def unread_count():
    return jsonify({"count": Notification.query.filter_by(read=False).count()})


@app.context_processor
def inject_polling_state():
    return {"polling_enabled": app.config["POLLING_ENABLED"]}


@app.route("/settings/polling/toggle", methods=["POST"])
def toggle_polling():
    app.config["POLLING_ENABLED"] = not app.config["POLLING_ENABLED"]
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/screeners")
def screeners():
    selected_symbol = request.args.get("selected", "").strip().upper() or None
    detail_ctx = (
        _stock_detail_context(selected_symbol, request.args.get("period", "6mo"), "screeners")
        if selected_symbol
        else {}
    )
    return render_template(
        "screeners.html",
        screener_names=list_screeners(),
        selected_symbol=selected_symbol,
        **detail_ctx,
    )


@app.route("/screeners/<name>/run", methods=["POST"])
def run_screener_route(name):
    results, error = run_screener(name)
    return render_template(
        "screeners.html",
        screener_names=list_screeners(),
        ran=name,
        results=results,
        error=error,
    )


def _current_price(symbol):
    ticker = Ticker.query.filter_by(symbol=symbol).first()
    if ticker and ticker.last_price is not None:
        return ticker.last_price
    price, _ = fetch_quote(symbol)
    return price


def _portfolio_context(selected_symbol=None, period="6mo", error=None):
    holdings = Holding.query.order_by(Holding.symbol).all()
    closed = RealizedTrade.query.order_by(RealizedTrade.sold_at.desc()).all()
    snapshots = PortfolioSnapshot.query.order_by(PortfolioSnapshot.taken_at).all()

    rows = []
    total_value = 0.0
    total_cost = 0.0
    for holding in holdings:
        price = _current_price(holding.symbol)
        market_value = (price or 0.0) * holding.quantity
        cost_basis = holding.avg_cost * holding.quantity
        unrealized_pl = market_value - cost_basis if price is not None else None
        unrealized_pct = (
            unrealized_pl / cost_basis * 100 if unrealized_pl is not None and cost_basis else None
        )
        total_value += market_value
        total_cost += cost_basis
        rows.append(
            {
                "holding": holding,
                "price": price,
                "market_value": market_value,
                "cost_basis": cost_basis,
                "unrealized_pl": unrealized_pl,
                "unrealized_pct": unrealized_pct,
            }
        )

    total_realized_pl = sum(t.realized_pl for t in closed)
    total_unrealized_pl = total_value - total_cost

    selected_row = next((r for r in rows if r["holding"].symbol == selected_symbol), None)
    selected_history = fetch_history(selected_symbol, period=period) if selected_symbol else None

    return {
        "rows": rows,
        "closed": closed,
        "snapshots": snapshots,
        "snapshot_labels": [s.taken_at.strftime("%m-%d %H:%M") for s in snapshots],
        "total_value": total_value,
        "total_cost": total_cost,
        "total_realized_pl": total_realized_pl,
        "total_unrealized_pl": total_unrealized_pl,
        "selected_symbol": selected_symbol,
        "selected_row": selected_row,
        "selected_history": selected_history,
        "period": period,
        "error": error,
    }


@app.route("/portfolio")
def portfolio():
    selected_symbol = request.args.get("selected", "").strip().upper() or None
    period = request.args.get("period", "6mo")
    return render_template("portfolio.html", **_portfolio_context(selected_symbol, period))


@app.route("/portfolio/buy", methods=["POST"])
def buy_holding():
    symbol = request.form.get("symbol", "").strip().upper()
    quantity = request.form.get("quantity", type=float)
    price = request.form.get("price", type=float)

    if not symbol or quantity is None or quantity <= 0:
        return render_template(
            "portfolio.html", **_portfolio_context(error="Enter a symbol and a positive quantity.")
        )
    if not symbol_exists(symbol):
        return render_template(
            "portfolio.html", **_portfolio_context(error=f"Could not find symbol '{symbol}'.")
        )

    if price is None:
        price = _current_price(symbol)
    if price is None:
        return render_template(
            "portfolio.html",
            **_portfolio_context(error=f"Could not fetch a price for '{symbol}'; enter one manually."),
        )

    holding = Holding.query.filter_by(symbol=symbol).first()
    if holding:
        new_qty = holding.quantity + quantity
        holding.avg_cost = (holding.quantity * holding.avg_cost + quantity * price) / new_qty
        holding.quantity = new_qty
        holding.updated_at = datetime.now(timezone.utc)
    else:
        db.session.add(Holding(symbol=symbol, quantity=quantity, avg_cost=price))
    db.session.commit()
    return redirect(url_for("portfolio", selected=symbol))


@app.route("/portfolio/<int:holding_id>/sell", methods=["POST"])
def sell_holding(holding_id):
    holding = Holding.query.get_or_404(holding_id)
    quantity = request.form.get("quantity", type=float)
    price = request.form.get("price", type=float)

    if quantity is None or quantity <= 0 or quantity > holding.quantity:
        return render_template(
            "portfolio.html",
            **_portfolio_context(
                selected_symbol=holding.symbol,
                error=f"Invalid quantity. You hold {holding.quantity} shares of {holding.symbol}.",
            ),
        )

    if price is None:
        price = _current_price(holding.symbol)
    if price is None:
        return render_template(
            "portfolio.html",
            **_portfolio_context(
                selected_symbol=holding.symbol,
                error=f"Could not fetch a price for '{holding.symbol}'; enter one manually.",
            ),
        )

    realized_pl = (price - holding.avg_cost) * quantity
    db.session.add(
        RealizedTrade(
            symbol=holding.symbol,
            quantity=quantity,
            avg_cost=holding.avg_cost,
            sell_price=price,
            realized_pl=realized_pl,
        )
    )

    symbol = holding.symbol
    if quantity == holding.quantity:
        db.session.delete(holding)
        symbol = None
    else:
        holding.quantity -= quantity
        holding.updated_at = datetime.now(timezone.utc)

    db.session.commit()
    return redirect(url_for("portfolio", **({"selected": symbol} if symbol else {})))


if __name__ == "__main__":
    start_scheduler(app)
    app.run(debug=True, use_reloader=False)
