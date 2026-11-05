from ml_engine.demand_forecaster import DemandForecaster
from ml_engine.price_trend_predictor import PriceTrendPredictor

# Lazy-loaded global model instances
_demand_forecaster = None
_price_predictor = None


def _get_demand_forecaster() -> DemandForecaster:
    global _demand_forecaster
    if _demand_forecaster is None:
        _demand_forecaster = DemandForecaster()
        _demand_forecaster.load("lgbm_demand_model.joblib")
    return _demand_forecaster


def _get_price_predictor() -> PriceTrendPredictor:
    global _price_predictor
    if _price_predictor is None:
        _price_predictor = PriceTrendPredictor()
        _price_predictor.load("rf_price_trend_model.joblib")
    return _price_predictor


def predict_future_demand(features: dict) -> float:
    """
    Predict expected daily unit sales for a SKU using the trained LightGBM model.
    """
    model = _get_demand_forecaster()
    return model.predict(features)


def predict_competitor_trend(features: dict) -> dict:
    """
    Predict 7-day competitor price movement using the trained Random Forest model.
    """
    model = _get_price_predictor()
    return model.predict_trend(features)