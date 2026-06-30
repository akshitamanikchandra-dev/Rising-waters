from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import uuid
import pyotp
from sqlalchemy import JSON

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = db.Column(db.String(80), unique=True, nullable=True, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=True)

    # Google OAuth
    google_id = db.Column(db.String(255), unique=True, nullable=True, index=True)
    google_picture = db.Column(db.Text, nullable=True)

    # Phone & SMS OTP
    phone = db.Column(db.String(20), unique=True, nullable=True, index=True)
    phone_verified = db.Column(db.Boolean, default=False)
    sms_otp = db.Column(db.String(6), nullable=True)
    sms_otp_expiry = db.Column(db.DateTime, nullable=True)

    # Email verification
    email_verified = db.Column(db.Boolean, default=False)
    email_verification_token = db.Column(db.String(255), nullable=True, unique=True)
    email_verification_expiry = db.Column(db.DateTime, nullable=True)

    # Password reset
    reset_token = db.Column(db.String(255), nullable=True, unique=True)
    reset_token_expiry = db.Column(db.DateTime, nullable=True)

    # Role and status
    role = db.Column(db.String(20), default='analyst')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    auth_method = db.Column(db.String(50), default='password')

    # Relationships
    weather_data = db.relationship('WeatherData', backref='user', lazy=True, cascade='all, delete-orphan')
    login_history = db.relationship('LoginHistory', backref='user', lazy=True, cascade='all, delete-orphan')

    # ------------------------------------------------------------------ passwords
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    # ------------------------------------------------------------------ SMS OTP
    def generate_sms_otp(self):
        import random
        self.sms_otp = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        self.sms_otp_expiry = datetime.utcnow() + timedelta(minutes=10)
        return self.sms_otp

    def verify_sms_otp(self, token):
        if not self.sms_otp or not self.sms_otp_expiry:
            return False
        if datetime.utcnow() > self.sms_otp_expiry:
            self.sms_otp = None
            self.sms_otp_expiry = None
            return False
        return self.sms_otp == str(token).strip()

    def clear_sms_otp(self):
        self.sms_otp = None
        self.sms_otp_expiry = None

    # ------------------------------------------------------------------ email verification
    def generate_email_token(self):
        self.email_verification_token = str(uuid.uuid4())
        self.email_verification_expiry = datetime.utcnow() + timedelta(hours=24)
        return self.email_verification_token

    def verify_email_token(self, token):
        if not self.email_verification_token or not self.email_verification_expiry:
            return False
        if self.email_verification_token != token:
            return False
        if datetime.utcnow() > self.email_verification_expiry:
            return False
        return True

    # ------------------------------------------------------------------ password reset
    def generate_reset_token(self):
        self.reset_token = str(uuid.uuid4())
        self.reset_token_expiry = datetime.utcnow() + timedelta(hours=24)
        return self.reset_token

    def verify_reset_token(self, token):
        if not self.reset_token or not self.reset_token_expiry:
            return False
        if self.reset_token != token:
            return False
        if datetime.utcnow() > self.reset_token_expiry:
            self.reset_token = None
            self.reset_token_expiry = None
            return False
        return True

    def clear_reset_token(self):
        self.reset_token = None
        self.reset_token_expiry = None

    def __repr__(self):
        return f'<User {self.email}>'


class LoginHistory(db.Model):
    __tablename__ = 'login_history'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False, index=True)
    login_at = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.Text, nullable=True)
    auth_method = db.Column(db.String(50), default='password')


class MLModel(db.Model):
    __tablename__ = 'ml_model'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(100), nullable=False, unique=True)
    algorithm_type = db.Column(db.String(50), nullable=False)
    accuracy = db.Column(db.Float, nullable=False, default=0.0)
    model_file = db.Column(db.String(500), nullable=False)
    version = db.Column(db.String(20), default='1.0')
    is_active = db.Column(db.Boolean, default=True)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    predictions = db.relationship('PredictionResult', backref='model', lazy=True)

    def __repr__(self):
        return f'<MLModel {self.name} v{self.version}>'


class WeatherData(db.Model):
    __tablename__ = 'weather_data'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False, index=True)

    annual_rainfall = db.Column(db.Float, nullable=False)
    cloud_visibility = db.Column(db.Float, nullable=False)
    temperature = db.Column(db.Float, nullable=False)
    humidity = db.Column(db.Float, nullable=False)
    seasonal_rainfall = db.Column(db.Float, nullable=False)

    region = db.Column(db.String(100))
    date_recorded = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text)

    predictions = db.relationship('PredictionResult', backref='weather_data', lazy=True, cascade='all, delete-orphan')


class PredictionResult(db.Model):
    __tablename__ = 'prediction_result'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    data_id = db.Column(db.String(36), db.ForeignKey('weather_data.id'), nullable=False, index=True)
    model_id = db.Column(db.String(36), db.ForeignKey('ml_model.id'), nullable=False, index=True)

    flood_result = db.Column(db.Boolean, nullable=False)
    flood_probability = db.Column(db.Float, nullable=False)
    confidence = db.Column(db.Float)
    prediction_date = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    processing_time_ms = db.Column(db.Float)

    def risk_level(self):
        if self.flood_probability >= 0.7:
            return 'HIGH'
        elif self.flood_probability >= 0.4:
            return 'MEDIUM'
        return 'LOW'
