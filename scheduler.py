from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from models import Alert, Holding, Notification, PortfolioSnapshot, Ticker, db
from stock_data import fetch_quote

POLL_INTERVAL_SECONDS = 60


def poll_prices(app):
    if not app.config.get("POLLING_ENABLED", True):
        return
    with app.app_context():
        price_cache = {}
        for ticker in Ticker.query.all():
            price, change_pct = fetch_quote(ticker.symbol)
            if price is None:
                continue
            price_cache[ticker.symbol] = price
            ticker.last_price = price
            ticker.last_change_pct = change_pct
            ticker.updated_at = datetime.now(timezone.utc)

            for alert in Alert.query.filter_by(ticker_id=ticker.id, active=True):
                crossed = (
                    alert.direction == "above" and price >= alert.threshold
                ) or (alert.direction == "below" and price <= alert.threshold)
                if crossed:
                    alert.active = False
                    alert.triggered_at = datetime.now(timezone.utc)
                    db.session.add(
                        Notification(
                            message=(
                                f"{ticker.symbol} is now ${price:.2f} "
                                f"({alert.direction} threshold ${alert.threshold:.2f})"
                            )
                        )
                    )

        holdings = Holding.query.all()
        if holdings:
            total_value = 0.0
            total_cost = 0.0
            for holding in holdings:
                price = price_cache.get(holding.symbol)
                if price is None:
                    price, _ = fetch_quote(holding.symbol)
                if price is None:
                    continue
                total_value += price * holding.quantity
                total_cost += holding.avg_cost * holding.quantity
            db.session.add(PortfolioSnapshot(total_value=total_value, total_cost=total_cost))

        db.session.commit()


def start_scheduler(app):
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        poll_prices,
        "interval",
        seconds=POLL_INTERVAL_SECONDS,
        args=[app],
        next_run_time=datetime.now(),
    )
    scheduler.start()
    return scheduler
