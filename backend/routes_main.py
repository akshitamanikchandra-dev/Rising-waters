import os
import time
from datetime import datetime, timedelta

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, jsonify, send_file, abort
)
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import FloatField, StringField, TextAreaField, SelectField, SubmitField
from wtforms.validators import DataRequired, NumberRange, Optional

from models import db, MLModel, WeatherData, PredictionResult
from prediction_engine import PredictionEngine

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
