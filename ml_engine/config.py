import os
from pathlib import Path
from dotenv import load_dotenv

# Resolve absolute project root directory (D:\scm_core_platform)
BASE_DIR = str(Path(__file__).resolve().parent.parent)

# Automatically load environment variables from D:\scm_core_platform\.env
ENV_FILE_PATH = Path(BASE_DIR) / ".env"
load_dotenv(dotenv_path=ENV_FILE_PATH, override=False)

DATA_RAW_DIR = str(Path(BASE_DIR) / "data" / "raw")
DATA_PROCESSED_DIR = str(Path(BASE_DIR) / "data" / "processed")
MODELS_REGISTRY_DIR = str(Path(BASE_DIR) / "models_registry")

# Ensure root-level directories exist
Path(DATA_RAW_DIR).mkdir(parents=True, exist_ok=True)
Path(DATA_PROCESSED_DIR).mkdir(parents=True, exist_ok=True)
Path(MODELS_REGISTRY_DIR).mkdir(parents=True, exist_ok=True)

# LightGBM hyperparameters for Poisson count demand forecasting
LGBM_PARAMS = {
    "objective": "poisson",
    "metric": "rmse",
    "boosting_type": "gbdt",
    "n_estimators": 300,
    "learning_rate": 0.03,
    "num_leaves": 31,
    "max_depth": 6,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "random_state": 42,
    "verbose": -1,
}

# Random Forest hyperparameters for 7-day competitor price trend classification
RF_PARAMS = {
    "n_estimators": 200,
    "max_depth": 8,
    "min_samples_split": 5,
    "min_samples_leaf": 2,
    "class_weight": "balanced",
    "random_state": 42,
    "n_jobs": -1,
}