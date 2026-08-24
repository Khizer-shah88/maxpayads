import os
import joblib
import numpy as np
from typing import List, Optional
from sklearn.ensemble import IsolationForest
import logging

logger = logging.getLogger(__name__)

MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "fraud_model.pkl")


class FraudDetectionModel:
    def __init__(self):
        self.model: Optional[IsolationForest] = None
        self.model_path = MODEL_PATH

    def load(self):
        """Load trained model from disk."""
        if os.path.exists(self.model_path):
            try:
                self.model = joblib.load(self.model_path)
                logger.info(f"Fraud model loaded from {self.model_path}")
            except Exception as e:
                logger.warning(f"Failed to load fraud model: {e}")
        else:
            logger.info("No pre-trained fraud model found. Training basic model...")
            self._train_basic_model()

    def _train_basic_model(self):
        """Train a basic model with synthetic data if no model exists."""
        try:
            rng = np.random.RandomState(42)
            # Generate synthetic "normal" click features
            X_train = rng.uniform(0, 1, size=(500, 8))
            # Add some obvious fraud patterns
            X_train[:50, 4] = 1.0  # datacenter IPs
            X_train[:50, 3] = 0.9  # high risk country

            self.model = IsolationForest(
                n_estimators=100,
                contamination=0.1,
                random_state=42,
            )
            self.model.fit(X_train)
            self.save()
            logger.info("Basic fraud model trained and saved")
        except Exception as e:
            logger.error(f"Failed to train basic model: {e}")

    def save(self):
        """Save trained model to disk."""
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
        joblib.dump(self.model, self.model_path)
        logger.info(f"Fraud model saved to {self.model_path}")

    def predict(self, features: List[float]) -> float:
        """
        Predict fraud score for a click.
        Returns float 0-1 where higher = more likely fraud.
        """
        if self.model is None:
            return 0.0
        try:
            X = np.array(features).reshape(1, -1)
            # IsolationForest: -1 = anomaly (fraud), 1 = normal
            # decision_function: lower = more anomalous
            score = self.model.decision_function(X)[0]
            # Normalize: convert to 0-1 fraud probability
            # decision_function values typically range from -0.5 to 0.5
            fraud_prob = max(0.0, min(1.0, (0.5 - score)))
            return float(fraud_prob)
        except Exception as e:
            logger.warning(f"ML prediction error: {e}")
            return 0.0

    def is_fraud(self, features: List[float], threshold: float = 0.65) -> bool:
        return self.predict(features) >= threshold


# Global singleton instance
fraud_model = FraudDetectionModel()
