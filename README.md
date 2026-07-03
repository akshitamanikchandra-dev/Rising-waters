# Rising Waters

Flood risk prediction web application built with Flask, SQLAlchemy, and scikit-learn/XGBoost.

It includes:
- User authentication (email/password + Google OAuth)
- Email verification and password reset
- ML model seeding and inference
- Prediction history, detail views, and dashboard stats
- Render-ready deployment config

## Quick Start

### 1. Prerequisites
- Python 3.14
- pip

### 2. Create and activate a virtual environment

Windows:
```bash
python -m venv venv
venv\Scripts\activate
```

macOS/Linux:
```bash
python -m venv venv
source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure environment
Create a `.env` file in the project root (you can start from `.env.example`) and set values as needed.

### 5. Seed ML models (required)
```bash
python backend/seed_models.py
```

This trains and registers 4 models:
- Random Forest
- Gradient Boosting
- Logistic Regression
- XGBoost

Model artifacts are saved in `uploads/models/`, and metadata is stored in the database.

### 6. Run the app
```bash
python backend/run.py
```

Open: http://localhost:5000

## Authentication Flows

### Manual signup
1. User signs up with username, email, phone, and password.
2. Account is created with `email_verified=False`.
3. Verification email link is sent.
4. User clicks verification link.
5. User can log in.

### Login with password
- Accepts email, phone, or username + password.
- If email is unverified, login is blocked until verification.

### Google OAuth
1. User clicks Google sign-in.
2. Existing account is matched by Google ID or email.
3. Email is treated as verified.
4. If profile is incomplete, user is redirected to complete profile (username + phone).

### Password reset
1. User requests reset link.
2. Reset email is sent.
3. User sets a new password from tokenized link.

## Environment Variables

Key variables used by the app:

| Variable | Required | Purpose |
|---|---|---|
| `FLASK_ENV` | Yes | `development` or `production` |
| `SECRET_KEY` | Yes | Session and CSRF security |
| `DEBUG` | Dev only | Enable debug mode |
| `DATABASE_URL` | No (dev), Yes (prod) | DB connection string (defaults to SQLite when empty) |
| `APP_DOMAIN` | Yes | Base URL used in generated links |
| `GOOGLE_CLIENT_ID` | For Google login | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | For Google login | Google OAuth client secret |
| `BREVO_API_KEY` | Optional | If set, emails are sent via Brevo API |
| `MAIL_DEFAULT_SENDER` | Recommended | Sender email identity |
| `MAIL_SERVER` | Optional fallback config | Mail settings from config |
| `MAIL_PORT` | Optional fallback config | Mail settings from config |
| `MAIL_USE_TLS` | Optional fallback config | Mail settings from config |
| `MAIL_USE_SSL` | Optional fallback config | Mail settings from config |
| `MAIL_USERNAME` | Optional fallback config | Mail settings from config |
| `MAIL_PASSWORD` | Optional fallback config | Mail settings from config |

Notes:
- If `BREVO_API_KEY` is not set in development, verification/reset links are surfaced in-app for local testing.
- For production, always set a strong `SECRET_KEY` and use HTTPS.

## Project Layout

```text
Rising-waters/
   backend/
      app.py
      config.py
      models.py
      prediction_engine.py
      routes_auth.py
      routes_main.py
      run.py
      seed_models.py
   frontend/
      templates/
         auth/
         errors/
         main/
         base.html
   uploads/
      models/
   requirements.txt
   render.yaml
   README.md
```

## Development Notes

- `backend/seed_models.py` should be run when setting up a fresh environment or when you want to regenerate model artifacts.
- `backend/prediction_engine.py` caches loaded models in memory for faster repeated inference.
- The app creates database tables on startup using `db.create_all()`.

## Deployment (Render)

This repo includes `render.yaml` configured for:
- Python web service
- Build command: `pip install -r requirements.txt && python backend/seed_models.py`
- Start command: `gunicorn --chdir backend run:app --workers 2 --bind 0.0.0.0:$PORT`
- Managed PostgreSQL database and environment variable wiring

### Recommended deployment checklist
1. Set `FLASK_ENV=production`.
2. Set a secure `SECRET_KEY`.
3. Set `APP_DOMAIN` to your live URL.
4. Configure `DATABASE_URL` (Render can inject it automatically).
5. Configure Google OAuth redirect URI:
    - `https://<your-domain>/auth/google/callback`
6. Configure email delivery (`BREVO_API_KEY`) for real verification/reset emails.

## API Endpoints

Authenticated JSON endpoints:
- `GET /api/predictions/recent`
- `GET /api/stats`

## License

No license file is currently included. Add one (for example, MIT) if you plan to distribute this project publicly.
