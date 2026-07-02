import os
import re
import requests
from datetime import datetime

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, session, current_app)
from flask_login import login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, EqualTo, Length, ValidationError, Regexp

from models import db, User
from app import oauth

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _is_safe_url(url):
    if not url:
        return False
    return not url.startswith(('http://', 'https://', 'ftp://', '//'))


def _send_email(to, subject, body_html):
    """Send email via Brevo's HTTP API. In dev (no BREVO_API_KEY), flash the link instead."""
    api_key = current_app.config.get('BREVO_API_KEY', '').strip()
    if not api_key:
        m = re.search(r'href="([^"]+)"', body_html)
        if m:
            link = m.group(1)
            from flask import flash as _flash
            _flash(f'[DEV — no mail] Click to proceed: <a href="{link}">{link}</a>', 'info')
        current_app.logger.warning(f'[DEV] Email to {to}: {subject}')
        return True, None

    sender_email = current_app.config.get('MAIL_DEFAULT_SENDER', 'noreply@floodprediction.com')

    payload = {
        "sender": {"name": "Rising Waters", "email": sender_email},
        "to": [{"email": to}],
        "subject": subject,
        "htmlContent": body_html,
    }
    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json",
    }

    try:
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            json=payload,
            headers=headers,
            timeout=10,
        )
        if response.status_code in (200, 201):
            return True, None
        else:
            err = f"Brevo API error {response.status_code}: {response.text}"
            current_app.logger.error(err)
            return False, err
    except requests.exceptions.RequestException as exc:
        current_app.logger.error(f'Brevo request failed: {exc}')
        return False, str(exc)


_PHONE_RE = r'^\+?[0-9]{7,15}$'
_PHONE_MSG = 'Enter a valid phone number (7-15 digits, optional leading +).'


# ─────────────────────────────────────────────────────────────────────────────
# Forms
# ─────────────────────────────────────────────────────────────────────────────

_EMAIL_RE = r'^[^@\s]+@[^@\s]+\.[^@\s]+$'
_EMAIL_MSG = 'Enter a valid email address.'

class SignUpForm(FlaskForm):
    username = StringField('Username',
        validators=[DataRequired(), Length(min=3, max=80)],
        render_kw={'class': 'form-control', 'placeholder': 'Enter username'})
    email = StringField('Email',
        validators=[DataRequired(), Regexp(_EMAIL_RE, message=_EMAIL_MSG)],
        render_kw={'class': 'form-control', 'placeholder': 'Enter email'})
    phone = StringField('Phone Number',
        validators=[DataRequired(), Regexp(_PHONE_RE, message=_PHONE_MSG)],
        render_kw={'class': 'form-control', 'placeholder': 'e.g. +919876543210'})
    password = PasswordField('Password',
        validators=[DataRequired(), Length(min=8)],
        render_kw={'class': 'form-control', 'placeholder': 'Min 8 characters'})
    confirm_password = PasswordField('Confirm Password',
        validators=[DataRequired(), EqualTo('password', message='Passwords must match')],
        render_kw={'class': 'form-control', 'placeholder': 'Repeat password'})
    submit = SubmitField('Create Account', render_kw={'class': 'btn btn-primary w-100'})

    def validate_username(self, field):
        if User.query.filter_by(username=field.data).first():
            raise ValidationError('Username already taken.')

    def validate_email(self, field):
        if User.query.filter_by(email=field.data).first():
            raise ValidationError('Email already registered.')

    def validate_phone(self, field):
        if User.query.filter_by(phone=field.data).first():
            raise ValidationError('Phone number already registered.')


class LoginForm(FlaskForm):
    identifier = StringField('Email or Phone Number',
        validators=[DataRequired()],
        render_kw={'class': 'form-control', 'placeholder': 'your@email.com or phone number'})
    password = PasswordField('Password',
        validators=[DataRequired()],
        render_kw={'class': 'form-control', 'placeholder': '••••••••'})
    remember_me = BooleanField('Remember me')
    submit = SubmitField('Sign In', render_kw={'class': 'btn btn-primary w-100'})


class ForgotPasswordForm(FlaskForm):
    email = StringField('Email',
        validators=[DataRequired(), Regexp(_EMAIL_RE, message=_EMAIL_MSG)],
        render_kw={'class': 'form-control', 'placeholder': 'your@email.com'})
    submit = SubmitField('Send Reset Link', render_kw={'class': 'btn btn-primary w-100'})


class ResetPasswordForm(FlaskForm):
    password = PasswordField('New Password',
        validators=[DataRequired(), Length(min=8)],
        render_kw={'class': 'form-control', 'placeholder': 'New password'})
    confirm_password = PasswordField('Confirm Password',
        validators=[DataRequired(), EqualTo('password', message='Passwords must match')],
        render_kw={'class': 'form-control', 'placeholder': 'Repeat password'})
    submit = SubmitField('Reset Password', render_kw={'class': 'btn btn-primary w-100'})


class PhoneForm(FlaskForm):
    phone = StringField('Phone Number',
        validators=[DataRequired(), Regexp(_PHONE_RE, message=_PHONE_MSG)],
        render_kw={'class': 'form-control', 'placeholder': 'e.g. +919876543210'})
    submit = SubmitField('Continue', render_kw={'class': 'btn btn-primary w-100'})

    def validate_phone(self, field):
        if User.query.filter_by(phone=field.data).first():
            raise ValidationError('Phone number already registered.')


# ─────────────────────────────────────────────────────────────────────────────
# Manual Signup flow (email/password + phone)
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    form = SignUpForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data,
            email=form.email.data,
            phone=form.phone.data,
            role='analyst',
            email_verified=False,
            auth_method='password',
        )
        user.set_password(form.password.data)

        try:
            db.session.add(user)
            db.session.flush()

            token = user.generate_email_token()
            db.session.commit()

            verify_url = url_for('auth.verify_email', token=token, _external=True)
            body = (
                f'<p>Hi {user.username},</p>'
                f'<p>Please verify your email by clicking the link below:</p>'
                f'<p><a href="{verify_url}" style="background:#3b82f6;color:#fff;'
                f'padding:10px 20px;border-radius:6px;text-decoration:none;">Verify Email</a></p>'
                f'<p>This link expires in 24 hours.</p>'
                f'<p>— Rising Waters Team</p>'
            )
            mail_ok, mail_err = _send_email(user.email, 'Verify your Rising Waters email', body)

        except Exception:
            db.session.rollback()
            current_app.logger.exception('Manual signup failed for %s', form.email.data)
            flash('Account creation failed. Please try again.', 'danger')
            return render_template('auth/signup.html', form=form)

        if mail_ok:
            flash('Account created! Check your email for the verification link '
                  'to activate your account.', 'success')
        else:
            flash(f'Account created, but the verification email could not be sent '
                  f'({mail_err}). Use "Resend verification link" on the login page.', 'warning')
        return redirect(url_for('auth.login'))

    return render_template('auth/signup.html', form=form)


@auth_bp.route('/verify-email/<token>')
def verify_email(token):
    user = User.query.filter_by(email_verification_token=token).first()
    if not user:
        flash('Invalid verification link.', 'danger')
        return redirect(url_for('auth.login'))

    if not user.verify_email_token(token):
        flash('Verification link expired. Please contact support.', 'danger')
        return redirect(url_for('auth.login'))

    user.email_verified = True
    user.email_verification_token = None
    user.email_verification_expiry = None
    db.session.commit()

    flash('Email verified! You can now log in.', 'success')
    return redirect(url_for('auth.login'))


@auth_bp.route('/resend-verification')
def resend_verification():
    email = request.args.get('email', '').strip()
    user = User.query.filter_by(email=email).first()
    if not user:
        flash('That email is not registered.', 'danger')
        return redirect(url_for('auth.login'))
    if user.email_verified:
        flash('That email is already verified. You can log in.', 'info')
        return redirect(url_for('auth.login'))

    token = user.generate_email_token()
    db.session.commit()
    verify_url = url_for('auth.verify_email', token=token, _external=True)
    body = (
        f'<p>Hi {user.username or "there"},</p>'
        f'<p>Click below to verify your email address:</p>'
        f'<p><a href="{verify_url}" style="background:#3b82f6;color:#fff;'
        f'padding:10px 20px;border-radius:6px;text-decoration:none;">Verify Email</a></p>'
        f'<p>This link expires in 24 hours.</p>'
    )
    ok, err = _send_email(user.email, 'Verify your Rising Waters email', body)
    if not ok:
        flash(f'Could not send the verification email: {err}.', 'danger')
    else:
        flash('A new verification link has been sent to your email.', 'success')
    return redirect(url_for('auth.login'))


# ─────────────────────────────────────────────────────────────────────────────
# Login (email OR phone + password)
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    form = LoginForm()
    if form.validate_on_submit():
        identifier = form.identifier.data.strip()
        user = User.query.filter(
            (User.email == identifier) | (User.phone == identifier)
        ).first()

        if user and user.check_password(form.password.data):
            if not user.is_active:
                flash('Account inactive. Contact the administrator.', 'warning')
                return redirect(url_for('auth.login'))
            if not user.email_verified:
                flash('Please verify your email first. '
                      'Check your inbox or resend below.', 'warning')
                return render_template('auth/login.html', form=form,
                                       unverified_email=user.email)
            login_user(user, remember=form.remember_me.data)
            user.last_login = datetime.utcnow()
            db.session.commit()
            next_page = request.args.get('next')
            if not next_page or not _is_safe_url(next_page):
                next_page = url_for('main.dashboard')
            return redirect(next_page)
        elif not user:
            flash('No account found with that email or phone number.', 'danger')
        else:
            flash('Password is incorrect.', 'danger')

    return render_template('auth/login.html', form=form)


# ─────────────────────────────────────────────────────────────────────────────
# Complete profile (phone number) — used after Google sign-up
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route('/complete-profile', methods=['GET', 'POST'])
@login_required
def complete_profile():
    if current_user.phone:
        return redirect(url_for('main.dashboard'))

    form = PhoneForm()
    if form.validate_on_submit():
        current_user.phone = form.phone.data
        db.session.commit()
        flash('Phone number saved!', 'success')
        return redirect(url_for('main.dashboard'))

    return render_template('auth/complete_profile.html', form=form)


# ─────────────────────────────────────────────────────────────────────────────
# Google OAuth
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route('/google')
def google_login():
    if not current_app.config.get('GOOGLE_CLIENT_ID'):
        flash('Google Sign-In is not configured. '
              'Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to your .env.', 'warning')
        return redirect(url_for('auth.login'))
    redirect_uri = url_for('auth.google_callback', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@auth_bp.route('/google/callback')
def google_callback():
    try:
        token = oauth.google.authorize_access_token()
    except Exception as exc:
        flash(f'Google sign-in failed: {exc}', 'danger')
        return redirect(url_for('auth.login'))

    user_info = token.get('userinfo') or oauth.google.userinfo()
    google_id  = user_info.get('sub')
    email      = user_info.get('email', '').lower()
    name       = user_info.get('name', email.split('@')[0] if email else '')
    picture    = user_info.get('picture', '')

    if not google_id or not email:
        flash('Could not retrieve Google account info.', 'danger')
        return redirect(url_for('auth.login'))

    user = User.query.filter_by(google_id=google_id).first()
    if not user:
        user = User.query.filter_by(email=email).first()

    if user:
        if not user.google_id:
            user.google_id = google_id
        user.google_picture = picture
        user.email_verified = True
        user.last_login = datetime.utcnow()
        db.session.commit()
        login_user(user, remember=True)
        flash(f'Welcome back, {user.username or user.email}!', 'success')
        if not user.phone:
            return redirect(url_for('auth.complete_profile'))
        return redirect(url_for('main.dashboard'))

    # New user — Google already verifies the email, so create the account immediately.
    raw_username = (name or email.split('@')[0])
    username = re.sub(r'[^a-zA-Z0-9]', '', raw_username).lower() or email.split('@')[0]
    base, counter = username, 1
    while User.query.filter_by(username=username).first():
        username = f'{base}{counter}'
        counter += 1

    user = User(
        username=username,
        email=email,
        google_id=google_id,
        google_picture=picture,
        email_verified=True,
        role='analyst',
        auth_method='google',
    )
    try:
        db.session.add(user)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Google signup failed for %s', email)
        flash('Account creation failed. Please try again.', 'danger')
        return redirect(url_for('auth.login'))

    login_user(user, remember=True)
    flash(f'Welcome to Rising Waters, {user.username}!', 'success')
    return redirect(url_for('auth.complete_profile'))


# ─────────────────────────────────────────────────────────────────────────────
# Logout / Forgot / Reset password
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been signed out.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if not user:
            form.email.errors.append('This email is not registered.')
            return render_template('auth/forgot_password.html', form=form)

        token = user.generate_reset_token()
        db.session.commit()
        reset_url = url_for('auth.reset_password', token=token, _external=True)
        body = (
            f'<p>Hi,</p>'
            f'<p>Click below to reset your Rising Waters password. '
            f'This link expires in 24 hours.</p>'
            f'<p><a href="{reset_url}" style="background:#3b82f6;color:#fff;'
            f'padding:10px 20px;border-radius:6px;text-decoration:none;">'
            f'Reset Password</a></p>'
        )
        ok, err = _send_email(user.email, 'Reset your Rising Waters password', body)
        if not ok:
            flash(f'Could not send the reset email: {err}. Please try again later.', 'danger')
            return render_template('auth/forgot_password.html', form=form)

        flash('A password reset link has been sent to your email.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/forgot_password.html', form=form)


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    user = User.query.filter_by(reset_token=token).first()
    if not user or not user.verify_reset_token(token):
        if user:
            db.session.commit()
        flash('Reset link is invalid or expired.', 'danger')
        return redirect(url_for('auth.forgot_password'))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        user.clear_reset_token()
        db.session.commit()
        flash('Password reset! Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html', form=form, token=token)