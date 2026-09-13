import os

from flask import Flask, jsonify, redirect, render_template, request, url_for

from models import Alert, Notification, Ticker, db
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


@app.route("/")
def dashboard():
    tickers = Ticker.query.order_by(Ticker.symbol).all()
    unread_count = Notification.query.filter_by(read=False).count()
    return render_template("dashboard.html", tickers=tickers, unread_count=unread_count)


@app.route("/tickers", methods=["POST"])
def add_ticker():
    symbol = request.form.get("symbol", "").strip().upper()
    if not symbol:
        return redirect(url_for("dashboard"))

    if not Ticker.query.filter_by(symbol=symbol).first():
        if not symbol_exists(symbol):
            tickers = Ticker.query.order_by(Ticker.symbol).all()
            return render_template(
                "dashboard.html",
                tickers=tickers,
                unread_count=Notification.query.filter_by(read=False).count(),
                error=f"Could not find symbol '{symbol}'.",
            )
        price, change_pct = fetch_quote(symbol)
        db.session.add(
            Ticker(symbol=symbol, last_price=price, last_change_pct=change_pct)
        )
        db.session.commit()

    return redirect(url_for("dashboard"))


@app.route("/tickers/<int:ticker_id>/delete", methods=["POST"])
def delete_ticker(ticker_id):
    ticker = Ticker.query.get_or_404(ticker_id)
    db.session.delete(ticker)
    db.session.commit()
    return redirect(url_for("dashboard"))


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
    if direction in ("above", "below") and threshold is not None:
        db.session.add(Alert(ticker_id=ticker.id, direction=direction, threshold=threshold))
        db.session.commit()
    return redirect(url_for("ticker_detail", ticker_id=ticker_id))


@app.route("/alerts/<int:alert_id>/delete", methods=["POST"])
def delete_alert(alert_id):
    alert = Alert.query.get_or_404(alert_id)
    ticker_id = alert.ticker_id
    db.session.delete(alert)
    db.session.commit()
    return redirect(url_for("ticker_detail", ticker_id=ticker_id))


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
    return render_template("screeners.html", screener_names=list_screeners())


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


if __name__ == "__main__":
    start_scheduler(app)
    app.run(debug=True, use_reloader=False)
