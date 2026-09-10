from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Ticker(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(16), unique=True, nullable=False)
    last_price = db.Column(db.Float)
    last_change_pct = db.Column(db.Float)
    updated_at = db.Column(db.DateTime)

    alerts = db.relationship("Alert", backref="ticker", cascade="all, delete-orphan")


class Alert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticker_id = db.Column(db.Integer, db.ForeignKey("ticker.id"), nullable=False)
    direction = db.Column(db.String(5), nullable=False)  # "above" or "below"
    threshold = db.Column(db.Float, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    triggered_at = db.Column(db.DateTime)


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    read = db.Column(db.Boolean, default=False, nullable=False)
