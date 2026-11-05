import os
import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_error
from ml_engine.config import LGBM_PARAMS, MODELS_REGISTRY_DIR


class DemandForecaster:
    """
    LightGBM-based regressor for forecasting daily SKU unit sales.
    """

    def __init__(self):
        self.model = LGBMRegressor(**LGBM_PARAMS)
        self.feature_columns = [
            "day_of_week", "day_of_month", "month", "is_weekend", "is_promo",
            "listed_price", "price_diff", "price_ratio", "margin_pct",
            "sales_lag_1", "sales_lag_3", "sales_lag_7", "sales_lag_14",
            "sales_roll_mean_7", "sales_roll_std_7", "sales_roll_mean_14",
        ]

    def train(self, df_train: pd.DataFrame) -> None:
        X = df_train[self.feature_columns]
        y = df_train["sales_qty"]
        self.model.fit(X, y)

    def evaluate(self, df_test: pd.DataFrame) -> dict:
        X = df_test[self.feature_columns]
        y = df_test["sales_qty"]
        preds = self.model.predict(X)

        mse = mean_squared_error(y, preds)
        rmse = np.sqrt(mse)
        mae = mean_absolute_error(y, preds)
        return {"rmse": round(float(rmse), 4), "mae": round(float(mae), 4)}

    def predict(self, feature_dict: dict) -> float:
        input_df = pd.DataFrame([feature_dict])[self.feature_columns]
        prediction = self.model.predict(input_df)[0]
        return max(0.0, round(float(prediction), 2))

    def save(self, filename: str = "lgbm_demand_model.joblib") -> None:
        path = os.path.join(MODELS_REGISTRY_DIR, filename)
        joblib.dump({"model": self.model, "features": self.feature_columns}, path)
        print(f"[DemandForecaster] Model saved -> {path}")

    def load(self, filename: str = "lgbm_demand_model.joblib") -> None:
        path = os.path.join(MODELS_REGISTRY_DIR, filename)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Model file not found at {path}. Run train_pipeline first.")
        data = joblib.load(path)
        self.model = data["model"]
        self.feature_columns = data["features"]