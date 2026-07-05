"""
Periodic severe-weather check for every user's saved locations.

Runs inside an APScheduler background job (started from app.py). For each
saved location with alerts enabled, fetches current conditions and — if a
'severe' condition is found and we haven't already alerted for this location
recently — sends an email to the owning user.
"""
from datetime import datetime, timedelta

import weather_service

# Don't re-alert for the same location more often than this.
ALERT_COOLDOWN_HOURS = 6


def _send_alert_email(app, user, location, alerts):
    """Send the severe-weather email via the app's existing Brevo helper."""
    from routes_auth import _send_email  # local import avoids circular import at module load

    lines = ''.join(f'<li>{msg}</li>' for _, msg in alerts)
    body = (
        f'<p>Hi {user.username or "there"},</p>'
        f'<p><strong>Severe weather alert for {location.label} '
        f'({location.display_name or ""}):</strong></p>'
        f'<ul>{lines}</ul>'
        f'<p>Please take appropriate precautions and check the Rising Waters '
        f'dashboard for the latest conditions.</p>'
        f'<p>— Rising Waters Team</p>'
    )
    subject = f'⚠️ Weather Alert: {location.label}'
    return _send_email(user.email, subject, body)


def check_all_locations(app):
    """Iterate over every saved location and send alerts where warranted."""
    with app.app_context():
        from models import db, SavedLocation

        locations = SavedLocation.query.filter_by(alerts_enabled=True).all()
        now = datetime.utcnow()

        for location in locations:
            weather, err = weather_service.get_weather(location.latitude, location.longitude)
            if err or not weather:
                app.logger.warning(f'Weather fetch failed for location {location.id}: {err}')
                continue

            alerts = weather_service.evaluate_alerts(weather)
            severe = [a for a in alerts if a[0] == 'severe']
            if not severe:
                continue

            if (location.last_alert_sent_at and
                    now - location.last_alert_sent_at < timedelta(hours=ALERT_COOLDOWN_HOURS)):
                continue

            user = location.user
            if not user or not user.email:
                continue

            ok, mail_err = _send_alert_email(app, user, location, severe)
            if ok:
                location.last_alert_sent_at = now
                location.last_alert_level = 'severe'
                db.session.commit()
            else:
                app.logger.error(f'Failed to send alert email for location {location.id}: {mail_err}')


def init_scheduler(app, interval_minutes=60):
    """Attach a background job that runs check_all_locations on a timer."""
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        func=lambda: check_all_locations(app),
        trigger='interval',
        minutes=interval_minutes,
        id='severe_weather_check',
        replace_existing=True,
        next_run_time=datetime.utcnow() + timedelta(seconds=30),
    )
    scheduler.start()
    app.extensions['weather_scheduler'] = scheduler
    return scheduler
