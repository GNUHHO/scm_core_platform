import os
import json
import pandas as pd
from ml_engine.config import DATA_RAW_DIR, DATA_PROCESSED_DIR, MODELS_REGISTRY_DIR
from ml_engine.data_generator import generate_retail_sales_data
from ml_engine.feature_engineering import build_features
from ml_engine.demand_forecaster import DemandForecaster
from ml_engine.price_trend_predictor import PriceTrendPredictor


def run_ml_pipeline() -> None:
    """
    End-to-end training pipeline: Data generation -> Feature engineering ->
    Chronological train/test split across all SKUs -> Model serialization.
    """
    print("=" * 65)
    print("[Pipeline] STARTING LAYER 1 MACHINE LEARNING TRAINING PIPELINE")
    print("=" * 65)

    # 1. Load or generate raw transaction data
    raw_path = os.path.join(DATA_RAW_DIR, "historical_sales.csv")
    if not os.path.exists(raw_path):
        df_raw = generate_retail_sales_data(days=365)
    else:
        df_raw = pd.read_csv(raw_path)

    # 2. Build features and save processed dataset
    print("[Pipeline] Running feature engineering...")
    df_features = build_features(df_raw, is_training=True)
    processed_path = os.path.join(DATA_PROCESSED_DIR, "processed_features.csv")
    df_features.to_csv(processed_path, index=False)

    # 3. Chronological split by date (ensures all SKUs are present in both Train and Test)
    unique_dates = sorted(df_features["date"].unique())
    cutoff_date = unique_dates[int(len(unique_dates) * 0.8)]

    train_df = df_features[df_features["date"] < cutoff_date].reset_index(drop=True)
    test_df = df_features[df_features["date"] >= cutoff_date].reset_index(drop=True)
    print(f"[Pipeline] Chronological Split (Cutoff: {str(cutoff_date)[:10]}): "
          f"Train={len(train_df)} rows, Test={len(test_df)} rows")

    # 4. Train and evaluate LightGBM Demand Forecaster
    print("\n[Pipeline] Training LightGBM Demand Forecaster...")
    demand_model = DemandForecaster()
    demand_model.train(train_df)
    demand_metrics = demand_model.evaluate(test_df)
    print(f"-> LightGBM Test Metrics: RMSE = {demand_metrics['rmse']}, MAE = {demand_metrics['mae']}")
    demand_model.save()

    # 5. Train and evaluate Random Forest Price Trend Predictor
    print("\n[Pipeline] Training Random Forest Price Trend Predictor...")
    rf_model = PriceTrendPredictor()
    rf_model.train(train_df)
    rf_metrics = rf_model.evaluate(test_df)
    print(f"-> Random Forest Test Accuracy: {rf_metrics['accuracy'] * 100:.2f}%")
    rf_model.save()

    # 6. Export training metadata
    meta_path = os.path.join(MODELS_REGISTRY_DIR, "feature_metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "trained_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                "cutoff_date": str(cutoff_date)[:10],
                "train_rows": len(train_df),
                "test_rows": len(test_df),
                "demand_metrics": demand_metrics,
                "price_trend_metrics": rf_metrics,
            },
            f,
            indent=2,
        )
    print(f"\n[Pipeline] Metadata saved -> {meta_path}")
    print("=" * 65)
    print("[Pipeline] LAYER 1 TRAINING COMPLETED SUCCESSFULLY")
    print("=" * 65)


if __name__ == "__main__":
    run_ml_pipeline()