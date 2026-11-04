import itertools
import os
from datetime import datetime, timezone

from flask import Flask, jsonify, redirect, render_template, request, url_for

from models import (
    Alert,
    Holding,
    Notification,
    PortfolioSnapshot,
    RealizedTrade,
    RecentSearch,
    Ticker,
    db,
)
from analyzers import list_analyzers, run_analyzer
from scheduler import start_scheduler
from screeners import list_screeners, run_screener
from stock_data import fetch_history, fetch_quote, symbol_exists

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RECENT_SEARCH_LIMIT = 10

_analysis_runs = {}  # symbol -> {"analyzer", "result", "error", "ran_at"} (in-memory, resets on restart)
_screener_runs = {}  # run_id -> {"name", "tab_label", "results", "error", "params", "ran_at"} (in-memory)
_screener_run_seq = itertools.count(1)  # generates unique run_ids, so re-running a script opens another tab


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


def _next_url(origin, symbol, **extra):
    params = {"selected": symbol}
    params.update({k: v for k, v in extra.items() if v})
    return url_for(origin, **params)


def _stock_detail_context(symbol, period, origin, extra_params=None):
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
        "next_url": _next_url(origin, symbol, **(extra_params or {})),
    }


def _analysis_context(symbol, origin="dashboard", extra_params=None):
    symbol = symbol.strip().upper()
    origin = origin if origin in ("dashboard", "screeners") else "dashboard"
    return {
        "symbol": symbol,
        "analyzer_names": list_analyzers(),
        "analysis": _analysis_runs.get(symbol),
        "next_url": _next_url(origin, symbol, **(extra_params or {})),
    }


@app.route("/stocks/<symbol>")
def stock_fragment(symbol):
    period = request.args.get("period", "6mo")
    origin = request.args.get("origin", "dashboard")
    return render_template("_stock_detail.html", **_stock_detail_context(symbol, period, origin))


@app.route("/stocks/<symbol>/analysis")
def stock_analysis_fragment(symbol):
    origin = request.args.get("origin", "dashboard")
    tab = request.args.get("tab")
    return render_template(
        "_stock_analysis.html",
        **_analysis_context(symbol, origin, {"tab": tab} if tab else None),
    )


@app.route("/stocks/<symbol>/analyzers/<name>/run", methods=["POST"])
def run_analyzer_route(symbol, name):
    symbol = symbol.strip().upper()
    data, error = run_analyzer(name, symbol)
    _analysis_runs[symbol] = {
        "analyzer": name,
        "result": data,
        "error": error,
        "ran_at": datetime.now(timezone.utc),
    }
    next_url = request.form.get("next")
    return redirect(next_url or url_for("dashboard", selected=symbol))


def _recent_searches():
    return RecentSearch.query.order_by(RecentSearch.searched_at.desc()).all()


def _render_error_page(origin, error):
    if origin == "screeners":
        return render_template(
            "screeners.html",
            screener_specs=list_screeners(),
            open_tabs=[],
            active_tab=None,
            run=None,
            analyzer_names=[],
            analysis=None,
            symbol=None,
            error=error,
        )
    if origin == "portfolio":
        return render_template("portfolio.html", **_portfolio_context(error=error))
    tickers = Ticker.query.order_by(Ticker.symbol).all()
    return render_template(
        "dashboard.html",
        tickers=tickers,
        unread_count=Notification.query.filter_by(read=False).count(),
        recent_searches=_recent_searches(),
        error=error,
    )


@app.route("/")
def dashboard():
    tickers = Ticker.query.order_by(Ticker.symbol).all()
    unread_count = Notification.query.filter_by(read=False).count()
    selected_symbol = request.args.get("selected", "").strip().upper() or None
    if selected_symbol:
        ctx = {
            **_analysis_context(selected_symbol, "dashboard"),
            **_stock_detail_context(selected_symbol, request.args.get("period", "6mo"), "dashboard"),
        }
    else:
        ctx = {"symbol": None}
    return render_template(
        "dashboard.html",
        tickers=tickers,
        unread_count=unread_count,
        recent_searches=_recent_searches(),
        selected_symbol=selected_symbol,
        **ctx,
    )


@app.route("/search", methods=["POST"])
def search_stock():
    symbol = request.form.get("symbol", "").strip().upper()
    if not symbol:
        return redirect(url_for("dashboard"))
    if not symbol_exists(symbol):
        return _render_error_page("dashboard", f"Could not find symbol '{symbol}'.")

    price, change_pct = fetch_quote(symbol)
    existing = RecentSearch.query.filter_by(symbol=symbol).first()
    if existing:
        existing.price = price
        existing.change_pct = change_pct
        existing.searched_at = datetime.now(timezone.utc)
    else:
        db.session.add(RecentSearch(symbol=symbol, price=price, change_pct=change_pct))
    db.session.commit()

    overflow = _recent_searches()[RECENT_SEARCH_LIMIT:]
    for stale in overflow:
        db.session.delete(stale)
    if overflow:
        db.session.commit()

    return redirect(url_for("dashboard", selected=symbol))


@app.route("/tickers", methods=["POST"])
def add_ticker():
    symbol = request.form.get("symbol", "").strip().upper()
    next_url = request.form.get("next")
    origin = request.form.get("origin", "dashboard")
    if not symbol:
        return redirect(next_url or url_for("dashboard"))

    if not Ticker.query.filter_by(symbol=symbol).first():
        if not symbol_exists(symbol):
            return _render_error_page(origin, f"Could not find symbol '{symbol}'.")
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
    specs = list_screeners()
    open_ids = sorted(_screener_runs, key=lambda rid: _screener_runs[rid]["ran_at"])

    requested_tab = request.args.get("tab")
    if requested_tab in _screener_runs:
        active_tab = requested_tab
    elif open_ids:
        active_tab = open_ids[-1]
    else:
        active_tab = None

    run = _screener_runs.get(active_tab)
    selected_symbol = request.args.get("selected", "").strip().upper() or None
    period = request.args.get("period", "6mo")
    extra = {"tab": active_tab} if active_tab else None
    if selected_symbol:
        ctx = {
            **_analysis_context(selected_symbol, "screeners", extra),
            **_stock_detail_context(selected_symbol, period, "screeners", extra),
        }
    else:
        ctx = {"symbol": None}

    return render_template(
        "screeners.html",
        screener_specs=specs,
        open_tabs=[{"id": rid, **_screener_runs[rid]} for rid in open_ids],
        active_tab=active_tab,
        run=run,
        selected_symbol=selected_symbol,
        **ctx,
    )


def _coerce_param(value, param_type):
    if value is None:
        return None
    if param_type == "number":
        try:
            f = float(value)
            return int(f) if f.is_integer() else f
        except (TypeError, ValueError):
            return value
    return value


@app.route("/screeners/<name>/run", methods=["POST"])
def run_screener_route(name):
    spec = {s["name"]: s for s in list_screeners()}.get(name)
    params = {}
    if spec:
        for p in spec["params"]:
            raw = request.form.get(f"param_{p['name']}")
            if raw is None or raw == "":
                raw = p.get("default")
            params[p["name"]] = _coerce_param(raw, p.get("type"))

    results, error = run_screener(name, params)

    display_name = spec["display_name"] if spec else name
    if params:
        summary = ", ".join(f"{k}={v}" for k, v in params.items())
        tab_label = f"{display_name} ({summary})"
    else:
        tab_label = display_name

    run_id = f"r{next(_screener_run_seq)}"
    _screener_runs[run_id] = {
        "name": name,
        "tab_label": tab_label,
        "results": results,
        "error": error,
        "params": params,
        "ran_at": datetime.now(timezone.utc),
    }
    redirect_params = {"tab": run_id}
    selected = request.form.get("selected")
    if selected:
        redirect_params["selected"] = selected
    return redirect(url_for("screeners", **redirect_params))


@app.route("/screeners/<run_id>/close", methods=["POST"])
def close_screener_tab(run_id):
    _screener_runs.pop(run_id, None)
    redirect_params = {}
    selected = request.form.get("selected")
    if selected:
        redirect_params["selected"] = selected
    return redirect(url_for("screeners", **redirect_params))


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
    next_url = request.form.get("next")
    origin = request.form.get("origin", "portfolio")

    if not symbol or quantity is None or quantity <= 0:
        return _render_error_page(origin, "Enter a symbol and a positive quantity.")
    if not symbol_exists(symbol):
        return _render_error_page(origin, f"Could not find symbol '{symbol}'.")

    if price is None:
        price = _current_price(symbol)
    if price is None:
        return _render_error_page(origin, f"Could not fetch a price for '{symbol}'; enter one manually.")

    holding = Holding.query.filter_by(symbol=symbol).first()
    if holding:
        new_qty = holding.quantity + quantity
        holding.avg_cost = (holding.quantity * holding.avg_cost + quantity * price) / new_qty
        holding.quantity = new_qty
        holding.updated_at = datetime.now(timezone.utc)
    else:
        db.session.add(Holding(symbol=symbol, quantity=quantity, avg_cost=price))
    db.session.commit()
    return redirect(next_url or url_for("portfolio", selected=symbol))


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


@app.route("/portfolio/closed/<int:trade_id>/delete", methods=["POST"])
def delete_realized_trade(trade_id):
    trade = RealizedTrade.query.get_or_404(trade_id)
    next_url = request.form.get("next")
    db.session.delete(trade)
    db.session.commit()
    return redirect(next_url or url_for("portfolio"))


if __name__ == "__main__":
    start_scheduler(app)
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", use_reloader=False)
