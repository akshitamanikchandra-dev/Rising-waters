"""
Run this once to train and register demo ML models.

Usage (from project root):
    python backend/seed_models.py
"""
import os
import sys
import uuid
import numpy as np
import joblib
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
from xgboost import XGBClassifier 

# -----------------------------------------------------------------------
# 1. Generate synthetic flood data
# -----------------------------------------------------------------------
np.random.seed(42)
N = 2000

annual_rainfall   = np.random.uniform(200, 4000, N)
cloud_visibility  = np.random.uniform(0, 100, N)
temperature       = np.random.uniform(15, 45, N)
humidity          = np.random.uniform(30, 100, N)
seasonal_rainfall = np.random.uniform(50, 2000, N)

X = np.column_stack([annual_rainfall, cloud_visibility, temperature, humidity, seasonal_rainfall])

# Flood probability rule-of-thumb
score = (
    (annual_rainfall / 4000) * 0.35
    + (1 - cloud_visibility / 100) * 0.15
    + (humidity / 100) * 0.25
    + (seasonal_rainfall / 2000) * 0.25
)
y = (score + np.random.normal(0, 0.05, N) > 0.5).astype(int)

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# -----------------------------------------------------------------------
# 2. Resolve upload directory
# -----------------------------------------------------------------------
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(ROOT_DIR, 'uploads', 'models')
os.makedirs(MODELS_DIR, exist_ok=True)

# -----------------------------------------------------------------------
# 3. Train & save models
# -----------------------------------------------------------------------
models_to_train = [
    {
        'name': 'Random Forest Flood Detector',
        'algorithm_type': 'random_forest',
        'description': 'Ensemble of 200 decision trees. Robust to outliers and missing patterns.',
        'estimator': Pipeline([
            ('scaler', StandardScaler()),
            ('clf', RandomForestClassifier(n_estimators=200, max_depth=8, random_state=42))
        ]),
        'filename': 'random_forest_v1.pkl',
    },
    {
        'name': 'Gradient Boosting Classifier',
        'algorithm_type': 'gradient_boosting',
        'description': 'Sequential boosting model. High accuracy on imbalanced flood datasets.',
        'estimator': Pipeline([
            ('scaler', StandardScaler()),
            ('clf', GradientBoostingClassifier(n_estimators=150, learning_rate=0.1, random_state=42))
        ]),
        'filename': 'gradient_boosting_v1.pkl',
    },
    {
        'name': 'Logistic Regression Baseline',
        'algorithm_type': 'logistic_regression',
        'description': 'Fast linear baseline. Useful for quick sanity-checks and feature importance.',
        'estimator': Pipeline([
            ('scaler', StandardScaler()),
            ('clf', LogisticRegression(max_iter=1000, random_state=42))
        ]),
        'filename': 'logistic_regression_v1.pkl',
    },
    {
        'name': 'XGBoost Flood Classifier',
        'algorithm_type': 'xgboost',
        'description': 'Extreme Gradient Boosting — highest accuracy model. Best for production flood risk scoring.',
        'estimator': Pipeline([
            ('scaler', StandardScaler()),
            ('clf', XGBClassifier(
                n_estimators=300,
                max_depth=6,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                use_label_encoder=False,
                eval_metric='logloss',
                random_state=42,
            ))
        ]),
        'filename': 'xgboost_v1.pkl',
    },
]

trained = []
for m in models_to_train:
    print(f"Training {m['name']}...")
    m['estimator'].fit(X_train, y_train)
    acc = accuracy_score(y_test, m['estimator'].predict(X_test))
    path = os.path.join(MODELS_DIR, m['filename'])
    joblib.dump(m['estimator'], path)
    rel_path = os.path.join('uploads', 'models', m['filename'])
    trained.append({**m, 'accuracy': round(acc * 100, 2), 'rel_path': rel_path})
    print(f"  Saved → {path}  (accuracy: {acc*100:.2f}%)")

# -----------------------------------------------------------------------
# 4. Register in the database
# -----------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import create_app
from models import db, MLModel

app = create_app('development')
with app.app_context():
    db.create_all()
    for m in trained:
        existing = MLModel.query.filter_by(name=m['name']).first()
        if existing:
            existing.accuracy = m['accuracy']
            existing.model_file = m['rel_path']
            print(f"  Updated existing record: {m['name']}")
        else:
            record = MLModel(
                id=str(uuid.uuid4()),
                name=m['name'],
                algorithm_type=m['algorithm_type'],
                accuracy=m['accuracy'],
                model_file=m['rel_path'],
                version='1.0',
                is_active=True,
                description=m['description'],
            )
            db.session.add(record)
            print(f"  Registered: {m['name']}")
    db.session.commit()
    print("\nAll models seeded successfully.")
