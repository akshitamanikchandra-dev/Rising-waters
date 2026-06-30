#!/bin/bash
set -e

echo "Installing dependencies..."
pip install -r requirements.txt

echo "Seeding ML models..."
python seed_model.py

echo "Running database migrations..."
python -c "from app import app, db; app.app_context().push(); db.create_all(); print('✓ Database initialized')"

echo "Build completed successfully!"