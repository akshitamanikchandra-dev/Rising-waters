# Rising Waters — Flood Prediction System

A Flask web app for flood risk prediction using ML models, with full authentication (email/password, Google OAuth, SMS OTP via Twilio).

---

## What Changed in This Version

### ML Models Fixed
- `python backend/seed_models.py` — trains 3 models (Random Forest, Gradient Boosting, Logistic Regression) and registers them in the DB. **Do this once before using the predictions page.**

### Authentication Flows

| Flow | Steps |
|------|-------|
| Manual Signup | Form (username + email + password + phone) → SMS OTP → phone verified → email verification link sent → user clicks link → account active → login |
| Google Sign Up | Click Google button → enter phone number → SMS OTP → account created (email auto-verified by Google) → dashboard |
| Google Sign In | Click Google button → existing account matched → dashboard |
| SMS OTP Login | Enter registered phone number → receive OTP → enter OTP → dashboard |
| Email/Password Login | Standard form → dashboard |

---

## Local Setup (Python 3.14)

### 1. Create and activate virtual environment

Windows:
```
python -m venv venv
venv\Scripts\activate
```

macOS / Linux:
```
python -m venv venv
source venv/bin/activate
```

### 2. Install dependencies

```
pip install -r requirements.txt
```

All package versions in requirements.txt are compatible with Python 3.14.

### 3. Configure environment

```
cp .env.example .env
```

Open `.env` and fill in your values (details below). If Twilio or mail credentials are not set, OTPs and verification links are automatically printed to the terminal — useful for local testing without external services.

### 4. Seed ML models (REQUIRED — do this once)

```
python backend/seed_models.py
```

This trains three flood prediction classifiers, saves them to `uploads/models/`, and registers them in the SQLite database. The Predict page will show "No active ML models" until you run this.

### 5. Run the app

```
python backend/run.py
```

Visit: http://localhost:5000

---

## Getting Service Credentials

### Google OAuth
1. Go to https://console.cloud.google.com/
2. Select or create a project → **APIs & Services → Credentials**
3. Click **Create Credentials → OAuth 2.0 Client ID**
4. Application type: **Web application**
5. Under **Authorized redirect URIs**, add:
   - `http://localhost:5000/auth/google/callback` (local dev)
   - `https://YOUR_APP.onrender.com/auth/google/callback` (production)
6. Copy **Client ID** and **Client Secret** into your `.env` file

### Twilio SMS
1. Create a free account at https://www.twilio.com/
2. In the Twilio Console → **Phone Numbers → Manage → Buy a number** (free trial number works)
3. Copy these three values into your `.env`:
   - `TWILIO_ACCOUNT_SID`
   - `TWILIO_AUTH_TOKEN`
   - `TWILIO_PHONE_NUMBER` (format: +12025551234)

### Gmail SMTP (email verification)
1. Enable **2-Factor Authentication** on the Gmail account you want to send from
2. Go to https://myaccount.google.com/apppasswords
3. Create an App Password for **Mail**
4. Set in `.env`:
   - `MAIL_USERNAME` = your Gmail address
   - `MAIL_PASSWORD` = the 16-character App Password (not your regular Gmail password)

---

## Push to a GitHub Repo

On GitHub.com, create a new repository. Then in your project folder:

```
step 1: git add .
step 2: git commit -m "Initial commit — Rising Waters flood prediction app"
step 3: git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
step 4: git branch -M main
step 5: git push -u origin main
```

For subsequent updates:
```
git add .
git commit -m "Describe your changes here"
git push
```

---

## Deploy on Render (Step-by-Step)

### Step 1 — Create a PostgreSQL Database
1. Log in to https://render.com/
2. Click **New → PostgreSQL**
3. Fill in:
   - **Name:** `rising-waters-db`
   - **Database:** `flood_prediction`
   - **User:** `flood_user`
4. Click **Create Database**
5. Copy the **Internal Database URL** — you will need it in Step 3

### Step 2 — Create the Web Service
1. Click **New → Web Service**
2. Connect your GitHub repository
3. Set:
   - **Name:** `rising-waters`
   - **Environment:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt && python backend/seed_models.py`
   - **Start Command:** `gunicorn --chdir backend run:app --workers 2 --bind 0.0.0.0:$PORT`

### Step 3 — Set Environment Variables
Go to your web service → **Environment** tab → add each variable:

| Variable | Value |
|----------|-------|
| `FLASK_ENV` | `production` |
| `SECRET_KEY` | click Generate (Render will generate one) |
| `DATABASE_URL` | paste the Internal Database URL from Step 1 |
| `APP_DOMAIN` | `https://rising-waters.onrender.com` |
| `GOOGLE_CLIENT_ID` | from Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | from Google Cloud Console |
| `TWILIO_ACCOUNT_SID` | from Twilio Console |
| `TWILIO_AUTH_TOKEN` | from Twilio Console |
| `TWILIO_PHONE_NUMBER` | your Twilio number e.g. `+12025551234` |
| `MAIL_SERVER` | `smtp.gmail.com` |
| `MAIL_PORT` | `587` |
| `MAIL_USE_TLS` | `True` |
| `MAIL_USERNAME` | your Gmail address |
| `MAIL_PASSWORD` | Gmail App Password |
| `MAIL_DEFAULT_SENDER` | `noreply@yourdomain.com` |

### Step 4 — Update Google OAuth Callback URL
In Google Cloud Console → Credentials → your OAuth Client → **Authorized redirect URIs**, add:
`https://rising-waters.onrender.com/auth/google/callback`

### Step 5 — Deploy
In Render → **Manual Deploy → Deploy latest commit**

Render will: install packages → run seed_models.py to train ML models → start Gunicorn. Logs are visible in the Render dashboard.

---

## Project Structure

```
flood-prediction/
  backend/
    app.py               Flask factory: registers OAuth, Mail, Login, blueprints
    config.py            DevelopmentConfig / ProductionConfig / TestingConfig
    models.py            User (phone/OTP/email-verify fields), MLModel, WeatherData, PredictionResult
    routes_auth.py       Signup, Login, SMS OTP, Google OAuth, email verify, password reset
    routes_main.py       Dashboard, Predict, Predictions list/detail/export, Models list
    prediction_engine.py Loads .pkl files, runs inference, caches models in memory
    seed_models.py       Trains 3 sklearn classifiers and registers them in DB
    run.py               Entry point (python backend/run.py)
  frontend/
    templates/
      auth/              login.html, signup.html, verify_phone.html, sms_login.html, google_phone.html,
                         forgot_password.html, reset_password.html
      main/              dashboard.html, predict.html, predictions_list.html, prediction_detail.html,
                         prediction_export.html, models_list.html, about.html
      errors/            403.html, 404.html, 500.html
      base.html          Shared layout with sidebar nav
  uploads/
    models/              .pkl files saved here by seed_models.py
  .env.example           Template for environment variables
  requirements.txt       Python dependencies (Python 3.14 compatible)
  render.yaml            Render deployment config
```
