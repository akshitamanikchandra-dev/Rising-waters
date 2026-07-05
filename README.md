# Rising Waters 🌊

A full-stack flood risk prediction web application built with **Flask**, **SQLAlchemy**, and **scikit-learn / XGBoost**. Rising Waters lets users run ML-powered flood predictions, monitor live weather conditions for saved locations, receive automated email alerts, and get AI-assisted answers from a built-in flood assistant chatbot.

---

## Features

| Area | Details |
|---|---|
| **Authentication** | Email/password signup with verification, Google OAuth, password reset, login history |
| **Profile Management** | Username, phone, profile picture (Google), email change with OTP confirmation |
| **Flood Prediction** | 5-feature ML inference (annual rainfall, cloud visibility, temperature, humidity, seasonal rainfall) |
| **ML Model Registry** | 4 trained models stored in DB: Random Forest, Gradient Boosting, Logistic Regression, XGBoost |
| **Dashboard** | Aggregated stats, risk distribution, 7-day prediction trend chart |
| **Prediction History** | Paginated list, per-prediction detail view, text export |
| **Location Monitoring** | Save named locations, view live weather + 3-day forecast via Open-Meteo (no API key needed) |
| **Automated Weather Alerts** | APScheduler background job checks every saved location hourly and emails severe-weather warnings |
| **AI Chatbot (Flood Bot)** | Gemini 2.5 Flash powered assistant for flood safety and platform questions |
| **Deployment** | Render-ready (`render.yaml`) with managed PostgreSQL |

---

## Quick Start

### 1. Prerequisites

- Python 3.10+
- `pip`

### 2. Create and activate a virtual environment

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**macOS / Linux:**
```bash
python -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

See the [Environment Variables](#environment-variables) section below for details.

### 5. Seed ML models *(required on first run)*

```bash
python backend/seed_models.py
```

This trains and registers 4 models using the included `flood dataset.xlsx`:

- Random Forest
- Gradient Boosting
- Logistic Regression
- XGBoost

Model artifacts are saved under `uploads/models/` and metadata is written to the database.

### 6. Run the app

```bash
python backend/run.py
```

Open [http://localhost:5000](http://localhost:5000).

---

## Authentication Flows

### Email / Password Signup
1. User registers with username, email, phone, and password.
2. Account is created with `email_verified = False`.
3. A verification link is emailed (or shown in-app in development when no mail config is set).
4. User clicks the link → account is activated.
5. User can now log in.

### Login
- Accepts **email**, **phone number**, or **username** + password.
- Login is blocked until email is verified.

### Google OAuth
1. User clicks *Sign in with Google*.
2. Existing account is matched by Google ID or email.
3. Email is automatically treated as verified.
4. If username / phone are missing, user is redirected to a *Complete Profile* page.

### Password Reset
1. User requests a reset link via Forgot Password.
2. A tokenised reset link is emailed (24-hour expiry).
3. User sets a new password from the link.

### Email Change (from Profile)
1. User enters a new email address in profile settings.
2. A 6-digit OTP is sent to the new address (15-minute expiry).
3. User confirms the OTP → email is updated.

---

## Environment Variables

Create a `.env` file at the project root (copy from `.env.example`):

| Variable | Required | Purpose |
|---|---|---|
| `FLASK_ENV` | Yes | `development` or `production` |
| `SECRET_KEY` | Yes | Session and CSRF security |
| `DEBUG` | Dev only | Enable Flask debug mode |
| `DATABASE_URL` | Prod | PostgreSQL connection string; defaults to SQLite in development |
| `APP_DOMAIN` | Yes | Base URL used in email links (e.g. `http://localhost:5000`) |
| `GOOGLE_CLIENT_ID` | OAuth | Google OAuth 2.0 client ID |
| `GOOGLE_CLIENT_SECRET` | OAuth | Google OAuth 2.0 client secret |
| `MAIL_SERVER` | Email | SMTP host (e.g. `smtp.gmail.com`) |
| `MAIL_PORT` | Email | SMTP port (e.g. `587`) |
| `MAIL_USE_TLS` | Email | `True` / `False` |
| `MAIL_USE_SSL` | Email | `True` / `False` |
| `MAIL_USERNAME` | Email | SMTP login username |
| `MAIL_PASSWORD` | Email | SMTP login password (use an App Password for Gmail) |
| `MAIL_DEFAULT_SENDER` | Email | From address for outgoing emails |
| `GEMINI_API_KEY` | Chatbot | Google Gemini API key — enables the Flood Bot assistant |
| `WEATHER_ALERT_INTERVAL_MINUTES` | Optional | How often the alert scheduler runs (default: `60`) |

> **Development tip:** In development, if no mail config is present, verification and password-reset links are surfaced directly in the app flash messages so you can test without a mail server.

> **Production:** Always set a strong `SECRET_KEY`, use HTTPS, and configure a real email provider.

---

## Project Layout

```text
Rising-waters/
├── backend/
│   ├── alerts.py            # APScheduler background job — severe-weather email alerts
│   ├── app.py               # Flask app factory and extension init
│   ├── config.py            # Config classes (dev / prod)
│   ├── models.py            # SQLAlchemy models (User, MLModel, WeatherData, PredictionResult, SavedLocation, LoginHistory)
│   ├── prediction_engine.py # ML inference engine (loads joblib models, caches in memory)
│   ├── routes_auth.py       # Auth routes (signup, login, OAuth, password reset, profile)
│   ├── routes_main.py       # App routes (dashboard, predict, locations, chatbot, API)
│   ├── run.py               # Entry point
│   ├── seed_models.py       # Train and register ML models from the dataset
│   └── weather_service.py   # Open-Meteo geocoding + current/forecast weather fetching
├── frontend/
│   └── templates/
│       ├── auth/
│       │   ├── login.html
│       │   ├── signup.html
│       │   ├── forgot_password.html
│       │   ├── reset_password.html
│       │   ├── complete_profile.html
│       │   ├── confirm_email_change.html
│       │   └── profile.html
│       ├── main/
│       │   ├── dashboard.html
│       │   ├── predict.html
│       │   ├── predictions_list.html
│       │   ├── prediction_detail.html
│       │   ├── prediction_export.html
│       │   ├── models_list.html
│       │   ├── locations.html
│       │   ├── location_weather.html
│       │   └── about.html
│       └── base.html
├── uploads/
│   └── models/              # Serialised joblib model artefacts
├── flood dataset.xlsx        # Training data
├── requirements.txt
├── render.yaml
└── .env.example
```

---

## API Endpoints

All endpoints require authentication (session cookie).

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/predictions/recent` | Last 10 predictions for the current user (JSON) |
| `GET` | `/api/stats` | Dashboard chart data — daily counts + risk distribution (JSON) |
| `POST` | `/api/chatbot` | Send a message to the Flood Bot assistant (JSON `{ "message": "..." }`) |

---

## Background Jobs

The APScheduler background job (`alerts.py`) runs inside the Flask process and:

1. Queries every `SavedLocation` with `alerts_enabled = True`.
2. Fetches live weather from Open-Meteo for each location.
3. If **severe** conditions are detected (heavy rain, extreme weather codes) and the location hasn't been alerted in the last **6 hours**, sends an email to the location owner.

The check interval defaults to 60 minutes and is configurable via `WEATHER_ALERT_INTERVAL_MINUTES`.

---

## Deployment (Render)

`render.yaml` provisions:
- A Python web service (`rising-waters`)
- A managed PostgreSQL database (`rising-waters-db`, database `flood_prediction`)

### Build & start commands

```
Build:  pip install -r requirements.txt && python backend/seed_models.py
Start:  gunicorn --chdir backend run:app --workers 2 --bind 0.0.0.0:$PORT
```

### Pre-deployment checklist

1. Set `FLASK_ENV=production`.
2. Set a secure `SECRET_KEY` (Render can auto-generate one).
3. Set `APP_DOMAIN` to your live URL (e.g. `https://rising-waters.onrender.com`).
4. `DATABASE_URL` is injected automatically from the managed database.
5. Configure Google OAuth → add the redirect URI:
   ```
   https://<your-domain>/auth/google/callback
   ```
6. Set mail credentials (`MAIL_SERVER`, `MAIL_USERNAME`, `MAIL_PASSWORD`, etc.) for real email delivery.
7. Set `GEMINI_API_KEY` if you want the Flood Bot chatbot to be functional.

---

## Development Notes

- **Model caching:** `PredictionEngine` loads a model from disk on first use and caches it in memory for faster repeated inference.
- **Database:** `db.create_all()` runs on startup, so tables are created automatically on a fresh database.
- **Re-seeding models:** Re-run `python backend/seed_models.py` any time you want to regenerate model artefacts or update training data.
- **Weather data:** Fetched in real time from [Open-Meteo](https://open-meteo.com) — no API key required.

---

## License

No license file is currently included. Add one (e.g. MIT) if you plan to distribute this project publicly.
