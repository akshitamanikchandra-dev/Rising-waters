import os
from flask import Flask, redirect, render_template, url_for
from flask_login import LoginManager
from flask_mail import Mail
from flask_wtf.csrf import CSRFProtect
from authlib.integrations.flask_client import OAuth
from models import db, User
from config import config

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
TEMPLATE_DIR = os.path.join(ROOT_DIR, 'frontend', 'templates')
UPLOAD_DIR = os.path.join(ROOT_DIR, 'uploads', 'models')

mail = Mail()
oauth = OAuth()
csrf = CSRFProtect()


def create_app(config_name='development'):
    app = Flask(__name__, template_folder=TEMPLATE_DIR)

    cfg_class = config.get(config_name, config['default'])
    app.config.from_object(cfg_class)
    app.config['UPLOAD_FOLDER'] = UPLOAD_DIR
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    # Allow OAuth over plain http in development
    if app.config.get('DEBUG'):
        os.environ.setdefault('OAUTHLIB_INSECURE_TRANSPORT', '1')

    db.init_app(app)
    mail.init_app(app)
    csrf.init_app(app)   # makes csrf_token() available in all templates
    oauth.init_app(app)

    oauth.register(
        name='google',
        client_id=app.config.get('GOOGLE_CLIENT_ID'),
        client_secret=app.config.get('GOOGLE_CLIENT_SECRET'),
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'},
    )

    @app.template_filter('basename')
    def basename_filter(path):
        return os.path.basename(path) if path else ''

    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, user_id)

    from routes_auth import auth_bp
    from routes_main import main_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    from flask import request
    from flask_login import current_user
    @app.before_request
    def enforce_profile_completion():
        if current_user.is_authenticated and (not current_user.phone or not current_user.username):
            allowed_endpoints = {'auth.complete_profile', 'auth.logout', 'static'}
            if request.endpoint not in allowed_endpoints:
                return redirect(url_for('auth.complete_profile'))

    _register_error_handlers(app)

    with app.app_context():
        db.create_all()

    return app


def _register_error_handlers(app):
    @app.errorhandler(404)
    def not_found(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(403)
    def forbidden(error):
        return render_template('errors/403.html'), 403

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('errors/500.html'), 500