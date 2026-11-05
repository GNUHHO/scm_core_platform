import os
import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
from ml_engine.config import RF_PARAMS, MODELS_REGISTRY_DIR


class PriceTrendPredictor:
    """
    Random Forest classifier for predicting 7-day competitor price movements.
    """

    def __init__(self):
        self.model = RandomForestClassifier(**RF_PARAMS)
        self.feature_columns = [
            "listed_price", "competitor_price", "price_diff", "price_ratio",
            "comp_price_lag_1", "comp_price_lag_3", "comp_price_lag_7", "comp_price_lag_14",
            "sales_roll_mean_7", "is_promo", "month",
        ]
        self.label_map = {
            0: "MARKDOWN",
            1: "STABLE",
            2: "MARKUP",
        }

    def train(self, df_train: pd.DataFrame) -> None:
        X = df_train[self.feature_columns]
        y = df_train["price_trend_target"]
        self.model.fit(X, y)

    def evaluate(self, df_test: pd.DataFrame) -> dict:
        X = df_test[self.feature_columns]
        y = df_test["price_trend_target"]
        preds = self.model.predict(X)
        acc = accuracy_score(y, preds)
        return {"accuracy": round(float(acc), 4)}

    def predict_trend(self, feature_dict: dict) -> dict:
        input_df = pd.DataFrame([feature_dict])[self.feature_columns]
        pred_class = int(self.model.predict(input_df)[0])
        probabilities = self.model.predict_proba(input_df)[0]
        return {
            "trend_class": pred_class,
            "trend_label": self.label_map[pred_class],
            "confidence": round(float(probabilities[pred_class]), 3),
        }

    def save(self, filename: str = "rf_price_trend_model.joblib") -> None:
        path = os.path.join(MODELS_REGISTRY_DIR, filename)
        joblib.dump(
            {"model": self.model, "features": self.feature_columns, "labels": self.label_map},
            path,
        )
        print(f"[PriceTrendPredictor] Model saved -> {path}")

    def load(self, filename: str = "rf_price_trend_model.joblib") -> None:
        path = os.path.join(MODELS_REGISTRY_DIR, filename)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Model file not found at {path}. Run train_pipeline first.")
        data = joblib.load(path)
        self.model = data["model"]
        self.feature_columns = data["features"]
        self.label_map = data["labels"]