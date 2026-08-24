"""
Train the Isolation Forest fraud detection model.
Run: python scripts/train_fraud_model.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ml.train_pipeline import train_model

if __name__ == "__main__":
    print("Starting fraud model training...")
    model = train_model()
    print("Training complete!")
    print(f"Model saved to app/ml/models/fraud_model.pkl")
