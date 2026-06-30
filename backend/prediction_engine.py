import joblib
import numpy as np
import os
from sklearn.preprocessing import StandardScaler


class PredictionEngine:
    """
    Prediction engine that loads trained models and makes predictions.
    Model files are cached in memory after first load.
    """

    def __init__(self):
        self.models_cache = {}
        self.scalers_cache = {}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_absolute_path(self, path):
        """Resolve *path* to an absolute path relative to the project root."""
        if not path:
            return path
        if os.path.isabs(path):
            return path
        # backend/ -> project root
        current_dir = os.path.dirname(os.path.abspath(__file__))
        root_dir = os.path.dirname(current_dir)
        return os.path.abspath(os.path.join(root_dir, path))

    def _load_model(self, model_path):
        """Load model from disk and store in cache."""
        model_path = self._get_absolute_path(model_path)
        if not os.path.exists(model_path):
            raise FileNotFoundError(f'Model file not found: {model_path}')

        if not model_path.endswith(('.pkl', '.joblib')):
            raise ValueError(f'Unsupported model format: {model_path}')

        try:
            model = joblib.load(model_path)
        except Exception as exc:
            raise RuntimeError(f'Failed to load model: {exc}') from exc

        self.models_cache[model_path] = model

    def _get_scaler(self, model_path):
        """Load (and cache) an optional scaler co-located with the model file."""
        scaler_path = os.path.join(os.path.dirname(model_path), 'scaler.pkl')
        if scaler_path not in self.scalers_cache:
            if os.path.exists(scaler_path):
                try:
                    self.scalers_cache[scaler_path] = joblib.load(scaler_path)
                except Exception:
                    self.scalers_cache[scaler_path] = None
            else:
                self.scalers_cache[scaler_path] = None
        return self.scalers_cache[scaler_path]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def predict(self, model_path, features):
        """
        Make a single prediction.

        Args:
            model_path: Path to the saved model (.pkl or .joblib).
            features: Sequence of 5 weather feature values
                      [annual_rainfall, cloud_visibility, temperature,
                       humidity, seasonal_rainfall].

        Returns:
            float: Flood probability in [0.0, 1.0].
        """
        try:
            model_path = self._get_absolute_path(model_path)
            if model_path not in self.models_cache:
                self._load_model(model_path)

            model = self.models_cache[model_path]
            features_array = np.array(features, dtype=float).reshape(1, -1)

            scaler = self._get_scaler(model_path)
            if scaler is not None:
                features_array = scaler.transform(features_array)

            if hasattr(model, 'predict_proba'):
                probability = model.predict_proba(features_array)[0][1]
            else:
                probability = float(model.predict(features_array)[0])

            return float(np.clip(probability, 0.0, 1.0))

        except FileNotFoundError:
            raise
        except Exception as exc:
            raise RuntimeError(f'Prediction error: {exc}') from exc

    def predict_batch(self, model_path, features_list):
        """
        Make predictions for multiple samples.

        Args:
            model_path: Path to the saved model file.
            features_list: List of feature arrays.

        Returns:
            list[float]: Flood probabilities in [0.0, 1.0].
        """
        try:
            model_path = self._get_absolute_path(model_path)
            if model_path not in self.models_cache:
                self._load_model(model_path)

            model = self.models_cache[model_path]
            features_array = np.array(features_list, dtype=float)

            scaler = self._get_scaler(model_path)
            if scaler is not None:
                features_array = scaler.transform(features_array)

            if hasattr(model, 'predict_proba'):
                results = model.predict_proba(features_array)[:, 1]
            else:
                results = model.predict(features_array)

            return [float(np.clip(v, 0.0, 1.0)) for v in results]

        except Exception as exc:
            raise RuntimeError(f'Batch prediction error: {exc}') from exc

    def clear_cache(self):
        """Free cached models and scalers."""
        self.models_cache.clear()
        self.scalers_cache.clear()

    # ------------------------------------------------------------------
    # Static validation
    # ------------------------------------------------------------------

    @staticmethod
    def validate_features(features):
        """
        Validate the 5 input features.

        Raises:
            ValueError: if features are invalid.
        Returns:
            True on success.
        """
        if len(features) != 5:
            raise ValueError('Expected exactly 5 features.')

        try:
            features = [float(f) for f in features]
        except (ValueError, TypeError):
            raise ValueError('All features must be numeric.')

        annual_rainfall, cloud_visibility, temperature, humidity, seasonal_rainfall = features

        if not (0 <= annual_rainfall <= 10000):
            raise ValueError('Annual rainfall must be 0–10000 mm.')
        if not (0 <= cloud_visibility <= 100):
            raise ValueError('Cloud visibility must be 0–100 km.')
        if not (-50 <= temperature <= 60):
            raise ValueError('Temperature must be -50–60 °C.')
        if not (0 <= humidity <= 100):
            raise ValueError('Humidity must be 0–100 %.')
        if not (0 <= seasonal_rainfall <= 10000):
            raise ValueError('Seasonal rainfall must be 0–10000 mm.')

        return True
