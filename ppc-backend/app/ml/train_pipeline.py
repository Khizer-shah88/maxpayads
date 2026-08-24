"""
Training pipeline for the Isolation Forest fraud detection model.
Run: python -m app.ml.train_pipeline
"""
import numpy as np
import joblib
import os
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "fraud_model.pkl")


def generate_training_data(n_samples: int = 10000):
    """Generate synthetic click data for training."""
    rng = np.random.RandomState(42)

    # Normal clicks (90%)
    n_normal = int(n_samples * 0.90)
    normal_clicks = np.column_stack([
        rng.uniform(6, 22, n_normal) / 23.0,      # hour (daytime hours)
        rng.randint(0, 5, n_normal) / 6.0,          # weekday
        rng.choice([0, 1, 2], n_normal, p=[0.6, 0.3, 0.1]) / 2.0,  # device
        rng.uniform(0.1, 0.4, n_normal),             # country risk (low)
        np.zeros(n_normal),                           # not datacenter
        rng.uniform(0.3, 0.9, n_normal),             # UA length (normal)
        rng.choice([0, 1], n_normal, p=[0.2, 0.8]),  # has referrer
        rng.choice([0, 1], n_normal, p=[0.95, 0.05]),   # short UA flag (normal = rarely short)
    ])

    # Fraudulent clicks (10%)
    n_fraud = n_samples - n_normal
    fraud_clicks = np.column_stack([
        rng.choice([0, 1, 23], n_fraud) / 23.0,    # odd hours
        rng.randint(0, 7, n_fraud) / 6.0,
        rng.choice([0, 1, 2], n_fraud) / 2.0,
        rng.uniform(0.6, 1.0, n_fraud),              # high risk country
        rng.choice([0, 1], n_fraud, p=[0.3, 0.7]),  # often datacenter
        rng.uniform(0.0, 0.2, n_fraud),              # very short UA
        np.zeros(n_fraud),                            # no referrer
        rng.choice([0, 1], n_fraud, p=[0.2, 0.8]),   # short UA flag (fraud = often short)
    ])

    X = np.vstack([normal_clicks, fraud_clicks])
    return X


def train_model():
    print("Generating training data...")
    X = generate_training_data(10000)

    print("Training Isolation Forest model...")
    model = IsolationForest(
        n_estimators=200,
        contamination=0.10,
        max_features=8,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X)

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    print(f"Model saved to {MODEL_PATH}")
    return model


if __name__ == "__main__":
    train_model()
