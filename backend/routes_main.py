import os
import time
import requests
from datetime import datetime, timedelta

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, jsonify, send_file, abort, current_app
)
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import FloatField, StringField, TextAreaField, SelectField, SubmitField, BooleanField
from wtforms.validators import DataRequired, NumberRange, Optional, Length

from models import db, MLModel, WeatherData, PredictionResult, SavedLocation
from prediction_engine import PredictionEngine
import weather_service

main_bp = Blueprint('main', __name__)

# Singleton prediction engine (caches loaded models in memory)
engine = PredictionEngine()


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------

class PredictForm(FlaskForm):
    """Weather-data input form for flood prediction."""
    annual_rainfall = FloatField(
        'Annual Rainfall (mm)',
        validators=[DataRequired(), NumberRange(min=0, max=10000)],
        render_kw={'class': 'form-control', 'placeholder': '0 – 10000'}
    )
    cloud_visibility = FloatField(
        'Cloud Visibility (km)',
        validators=[DataRequired(), NumberRange(min=0, max=100)],
        render_kw={'class': 'form-control', 'placeholder': '0 – 100'}
    )
    temperature = FloatField(
        'Temperature (°C)',
        validators=[DataRequired(), NumberRange(min=-50, max=60)],
        render_kw={'class': 'form-control', 'placeholder': '-50 – 60'}
    )
    humidity = FloatField(
        'Humidity (%)',
        validators=[DataRequired(), NumberRange(min=0, max=100)],
        render_kw={'class': 'form-control', 'placeholder': '0 – 100'}
    )
    seasonal_rainfall = FloatField(
        'Seasonal Rainfall (mm)',
        validators=[DataRequired(), NumberRange(min=0, max=10000)],
        render_kw={'class': 'form-control', 'placeholder': '0 – 10000'}
    )
    region = StringField(
        'Region / Location',
        validators=[Optional()],
        render_kw={'class': 'form-control', 'placeholder': 'e.g. Mumbai, Maharashtra'}
    )
    notes = TextAreaField(
        'Notes',
        validators=[Optional()],
        render_kw={'class': 'form-control', 'rows': 3, 'placeholder': 'Optional notes…'}
    )
    model_id = SelectField(
        'ML Model',
        validators=[DataRequired()],
        render_kw={'class': 'form-control'}
    )
    submit = SubmitField('Run Prediction', render_kw={'class': 'btn btn-primary btn-lg w-100'})


class AddLocationForm(FlaskForm):
    """Add a saved location by name (e.g. city) for weather monitoring."""
    label = StringField(
        'Label',
        validators=[DataRequired(), Length(min=1, max=100)],
        render_kw={'class': 'form-control', 'placeholder': 'e.g. Home, Office, Mumbai'}
    )
    query = StringField(
        'City / Place',
        validators=[DataRequired(), Length(min=2, max=200)],
        render_kw={'class': 'form-control', 'placeholder': 'e.g. Pune, Maharashtra'}
    )
    alerts_enabled = BooleanField('Email me about severe weather here', default=True)
    submit = SubmitField('Add Location', render_kw={'class': 'btn btn-primary'})


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@main_bp.route('/')
@login_required
def index():
    return redirect(url_for('main.dashboard'))


@main_bp.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard with statistics and charts."""
    # Aggregate stats
    all_predictions = (
        PredictionResult.query
        .join(WeatherData)
        .filter(WeatherData.user_id == current_user.id)
        .order_by(PredictionResult.prediction_date.desc())
        .all()
    )

    total = len(all_predictions)
    high_risk = sum(1 for p in all_predictions if p.flood_probability >= 0.7)
    medium_risk = sum(1 for p in all_predictions if 0.4 <= p.flood_probability < 0.7)
    low_risk = sum(1 for p in all_predictions if p.flood_probability < 0.4)

    # Recent high-risk in last 24 h
    cutoff = datetime.utcnow() - timedelta(hours=24)
    recent_high_risk = sum(
        1 for p in all_predictions
        if p.flood_probability >= 0.7 and p.prediction_date >= cutoff
    )

    # Last-7-days chart data (daily average probability)
    chart_labels = []
    chart_data = []
    for i in range(6, -1, -1):
        day = datetime.utcnow() - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        day_preds = [
            p for p in all_predictions
            if day_start <= p.prediction_date < day_end
        ]
        chart_labels.append(day.strftime('%b %d'))
        avg = round(sum(p.flood_probability for p in day_preds) / len(day_preds) * 100, 1) if day_preds else 0
        chart_data.append(avg)

    active_models = MLModel.query.filter_by(is_active=True).order_by(MLModel.accuracy.desc()).all()

    return render_template(
        'main/dashboard.html',
        total_predictions=total,
        high_risk_count=high_risk,
        medium_risk_count=medium_risk,
        low_risk_count=low_risk,
        recent_high_risk=recent_high_risk,
        recent_predictions=all_predictions[:10],
        chart_labels=chart_labels,
        chart_data=chart_data,
        models=active_models,
    )


@main_bp.route('/predict', methods=['GET', 'POST'])
@login_required
def predict():
    """Submit weather data and run flood prediction."""
    active_models = MLModel.query.filter_by(is_active=True).order_by(MLModel.accuracy.desc()).all()

    form = PredictForm()
    form.model_id.choices = [(m.id, f'{m.name} ({m.accuracy:.1f}% acc.)') for m in active_models]

    if not active_models:
        flash('No active ML models are available. Please contact the administrator.', 'warning')

    if form.validate_on_submit():
        model = db.session.get(MLModel, form.model_id.data)
        if not model:
            flash('Selected model not found.', 'danger')
            return redirect(url_for('main.predict'))

        features = [
            form.annual_rainfall.data,
            form.cloud_visibility.data,
            form.temperature.data,
            form.humidity.data,
            form.seasonal_rainfall.data,
        ]

        try:
            PredictionEngine.validate_features(features)
            start = time.time()
            probability = engine.predict(model.model_file, features)
            elapsed_ms = round((time.time() - start) * 1000, 2)
        except Exception as exc:
            flash(f'Prediction error: {exc}', 'danger')
            return redirect(url_for('main.predict'))

        # Persist data
        weather = WeatherData(
            user_id=current_user.id,
            annual_rainfall=form.annual_rainfall.data,
            cloud_visibility=form.cloud_visibility.data,
            temperature=form.temperature.data,
            humidity=form.humidity.data,
            seasonal_rainfall=form.seasonal_rainfall.data,
            region=form.region.data or None,
            notes=form.notes.data or None,
        )
        db.session.add(weather)
        db.session.flush()  # get weather.id before commit

        result = PredictionResult(
            data_id=weather.id,
            model_id=model.id,
            flood_result=probability >= 0.5,
            flood_probability=probability,
            confidence=probability if probability >= 0.5 else 1 - probability,
            processing_time_ms=elapsed_ms,
        )
        db.session.add(result)
        db.session.commit()

        flash('Prediction completed successfully!', 'success')
        return redirect(url_for('main.prediction_detail', prediction_id=result.id))

    return render_template('main/predict.html', form=form, models=active_models)


@main_bp.route('/predictions')
@login_required
def predictions_list():
    """List all predictions made by the current user."""
    page = request.args.get('page', 1, type=int)

    pagination = (
        PredictionResult.query
        .join(WeatherData)
        .filter(WeatherData.user_id == current_user.id)
        .order_by(PredictionResult.prediction_date.desc())
        .paginate(page=page, per_page=15, error_out=False)
    )

    return render_template('main/predictions_list.html', pagination=pagination)


@main_bp.route('/predictions/<prediction_id>')
@login_required
def prediction_detail(prediction_id):
    """Show a single prediction's details."""
    result = db.session.get(PredictionResult, prediction_id)
    if not result:
        abort(404)
    # Only allow the owner or an admin to view
    if result.weather_data.user_id != current_user.id and current_user.role != 'admin':
        abort(403)
    return render_template('main/prediction_detail.html', result=result)


@main_bp.route('/predictions/<prediction_id>/export')
@login_required
def prediction_export(prediction_id):
    """Export a prediction result as a simple text report."""
    result = db.session.get(PredictionResult, prediction_id)
    if not result:
        abort(404)
    if result.weather_data.user_id != current_user.id and current_user.role != 'admin':
        abort(403)
    return render_template('main/prediction_export.html', result=result)


@main_bp.route('/models')
@login_required
def models_list():
    """List registered ML models."""
    models = MLModel.query.order_by(MLModel.accuracy.desc()).all()
    return render_template('main/models_list.html', models=models)


@main_bp.route('/about')
@login_required
def about():
    """About page."""
    models = MLModel.query.filter_by(is_active=True).all()
    return render_template('main/about.html', models=models)


# ---------------------------------------------------------------------------
# Your Location Weather — saved locations, live conditions & alert emails
# ---------------------------------------------------------------------------

@main_bp.route('/locations', methods=['GET', 'POST'])
@login_required
def locations():
    """List saved locations with a quick current-conditions snapshot, and
    let the user add a new one."""
    form = AddLocationForm()

    if form.validate_on_submit():
        matches = weather_service.geocode(form.query.data.strip())
        if not matches:
            flash(f'Could not find a place matching "{form.query.data}". '
                  f'Try a more specific name (e.g. add state/country).', 'danger')
        else:
            best = matches[0]
            existing = SavedLocation.query.filter_by(
                user_id=current_user.id, label=form.label.data.strip()
            ).first()
            if existing:
                flash(f'You already have a saved location labeled "{form.label.data}".', 'danger')
            else:
                place_bits = [best['name'], best.get('admin1'), best.get('country')]
                display_name = ', '.join(b for b in place_bits if b)
                loc = SavedLocation(
                    user_id=current_user.id,
                    label=form.label.data.strip(),
                    display_name=display_name,
                    country=best.get('country'),
                    latitude=best['latitude'],
                    longitude=best['longitude'],
                    alerts_enabled=form.alerts_enabled.data,
                )
                db.session.add(loc)
                db.session.commit()
                flash(f'Added "{loc.label}" ({display_name}) to your monitored locations.', 'success')
                return redirect(url_for('main.locations'))

    saved = SavedLocation.query.filter_by(user_id=current_user.id).order_by(SavedLocation.created_at.desc()).all()

    snapshots = {}
    for loc in saved:
        weather, err = weather_service.get_weather(loc.latitude, loc.longitude)
        snapshots[loc.id] = {
            'weather': weather,
            'error': err,
            'alerts': weather_service.evaluate_alerts(weather) if weather else [],
        }

    return render_template('main/locations.html', form=form, locations=saved, snapshots=snapshots)


@main_bp.route('/locations/<location_id>/delete', methods=['POST'])
@login_required
def delete_location(location_id):
    loc = db.session.get(SavedLocation, location_id)
    if not loc or loc.user_id != current_user.id:
        abort(404)
    db.session.delete(loc)
    db.session.commit()
    flash(f'Removed "{loc.label}" from your monitored locations.', 'info')
    return redirect(url_for('main.locations'))


@main_bp.route('/locations/<location_id>/toggle-alerts', methods=['POST'])
@login_required
def toggle_location_alerts(location_id):
    loc = db.session.get(SavedLocation, location_id)
    if not loc or loc.user_id != current_user.id:
        abort(404)
    loc.alerts_enabled = not loc.alerts_enabled
    db.session.commit()
    flash(f'Email alerts for "{loc.label}" are now '
          f'{"enabled" if loc.alerts_enabled else "disabled"}.', 'info')
    return redirect(url_for('main.locations'))


@main_bp.route('/locations/<location_id>/weather')
@login_required
def location_weather(location_id):
    """Detailed current + 3-day forecast view for a single saved location."""
    loc = db.session.get(SavedLocation, location_id)
    if not loc or loc.user_id != current_user.id:
        abort(404)

    weather, err = weather_service.get_weather(loc.latitude, loc.longitude)
    alerts = weather_service.evaluate_alerts(weather) if weather else []

    forecast = []
    if weather:
        for date, precip, prob in zip(
            weather.get('forecast_dates', []),
            weather.get('forecast_precip_sum', []),
            weather.get('forecast_precip_probability', []),
        ):
            forecast.append({'date': date, 'precip_sum': precip, 'precip_probability': prob})

    return render_template(
        'main/location_weather.html',
        location=loc, weather=weather, error=err, alerts=alerts, forecast=forecast,
    )


# ---------------------------------------------------------------------------
# API endpoints (JSON)
# ---------------------------------------------------------------------------

@main_bp.route('/api/predictions/recent')
@login_required
def api_recent_predictions():
    """Return the 10 most recent predictions for the current user as JSON."""
    predictions = (
        PredictionResult.query
        .join(WeatherData)
        .filter(WeatherData.user_id == current_user.id)
        .order_by(PredictionResult.prediction_date.desc())
        .limit(10)
        .all()
    )
    data = [
        {
            'id': p.id,
            'probability': round(p.flood_probability * 100, 1),
            'risk_level': p.risk_level(),
            'date': p.prediction_date.isoformat(),
            'region': p.weather_data.region or 'N/A',
        }
        for p in predictions
    ]
    return jsonify(data)


@main_bp.route('/api/stats')
@login_required
def api_stats():
    """Return dashboard chart data as JSON (called by dashboard.html JS)."""
    all_predictions = (
        PredictionResult.query
        .join(WeatherData)
        .filter(WeatherData.user_id == current_user.id)
        .order_by(PredictionResult.prediction_date.desc())
        .all()
    )

    # Daily prediction counts for last 7 days
    labels = []
    daily_counts = []
    for i in range(6, -1, -1):
        day = datetime.utcnow() - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        count = sum(1 for p in all_predictions if day_start <= p.prediction_date < day_end)
        labels.append(day.strftime('%b %d'))
        daily_counts.append(count)

    # Risk distribution
    high = sum(1 for p in all_predictions if p.flood_probability >= 0.7)
    medium = sum(1 for p in all_predictions if 0.4 <= p.flood_probability < 0.7)
    low = sum(1 for p in all_predictions if p.flood_probability < 0.4)

    return jsonify({
        'daily_predictions': {'labels': labels, 'data': daily_counts},
        'risk_distribution': {'high': high, 'medium': medium, 'low': low},
    })

# ---------------------------------------------------------------------------
# Flood Bot (Gemini API)
# ---------------------------------------------------------------------------

@main_bp.route('/api/chatbot', methods=['POST'])
@login_required
def chatbot():
    data = request.get_json(silent=True) or {}
    user_message = (data.get('message') or '').strip()

    if not user_message:
        return jsonify({'error': 'Message is required.'}), 400

    api_key = current_app.config.get('GEMINI_API_KEY', '').strip()
    if not api_key:
        return jsonify({'error': 'Chatbot is not configured.'}), 503

    system_context = (
        "You are Flood Bot, a helpful assistant for the Rising Waters flood "
        "prediction platform. Answer questions about flood risk, flood safety, "
        "how the platform works, and general flood-related topics concisely "
        "and clearly. If asked something unrelated to floods or the platform, "
        "gently steer the conversation back."
    )

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": f"{system_context}\n\nUser question: {user_message}"}]
            }
        ]
    }

    try:
        response = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            },
            json=payload,
            timeout=15,
        )
        response.raise_for_status()
        result = response.json()
        reply = (
            result.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "Sorry, I could not generate a response.")
        )
        return jsonify({'reply': reply})

    except requests.exceptions.RequestException as exc:
        current_app.logger.error(f'Gemini API request failed: {exc}')
        return jsonify({'error': 'Chatbot is temporarily unavailable. Please try again.'}), 502
    except (KeyError, IndexError) as exc:
        current_app.logger.error(f'Unexpected Gemini API response format: {exc}')
        return jsonify({'error': 'Chatbot returned an unexpected response.'}), 502
