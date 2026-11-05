import os
import traceback
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# Load .env from project root immediately
load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env", override=False)

from database.db_manager import init_db, build_live_catalog_and_suppliers, save_orchestrator_results
from services.scraper_service import scrape_and_sync_competitor_prices
from agents.orchestrator import MultiAgentSupplyChainOrchestrator
from ml_engine.inference_service import predict_future_demand, predict_competitor_trend
from optimization_engine.stochastic_inventory import StochasticInventoryEngine
from optimization_engine.elastic_pricing_solver import ElasticPricingSolver

app = FastAPI(
    title="SCM Core AI & Multi-Agent Microservice",
    description="Quantitative ML, Scipy Optimization, and 4-Agent Gemini Engine for C# .NET ERP Backend",
    version="2.0.0",
)

init_db()


class ScrapeRequest(BaseModel):
    api_key: Optional[str] = None
    provider_mode: str = Field(default="LOCAL", description="LOCAL or APIFY")
    apify_token: Optional[str] = None
    force_ai: bool = False


class QuantitativeSimRequest(BaseModel):
    sku: str
    on_hand_stock: int = Field(ge=0)
    incoming_stock: int = Field(default=0, ge=0)
    cost_price: int = Field(gt=0)
    listed_price: int = Field(gt=0)
    competitor_price: int = Field(gt=0)
    lead_time_days: int = Field(default=3, gt=0)
    service_level_z: float = Field(default=1.65)
    elasticity: float = Field(default=-1.8)
    features_ml: dict


class MultiAgentAuditRequest(BaseModel):
    api_key: Optional[str] = None
    model: str = "gemini-flash-latest"
    service_level_z: float = 1.65
    elasticity: float = -1.8
    catalog_override: Optional[list[dict]] = None
    suppliers_override: Optional[list[dict]] = None


@app.get("/api/v1/health")
def health_check():
    has_key = bool(os.getenv("GEMINI_API_KEY", "").strip())
    return {
        "status": "HEALTHY",
        "service": "scm-python-ai-microservice",
        "gemini_api_key_loaded": has_key,
        "agents_ready": ["Agent0_Scraper", "Agent1_Procurement", "Agent2_Pricing", "Agent3_Supervisor"],
    }


@app.post("/api/v1/scrape")
def trigger_competitor_scraper(req: ScrapeRequest):
    try:
        resolved_key = (req.api_key or os.getenv("GEMINI_API_KEY", "")).strip()
        return scrape_and_sync_competitor_prices(
            api_key=resolved_key,
            provider_mode=req.provider_mode,
            apify_token=req.apify_token,
            force_ai=req.force_ai,
        )
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[FastAPI Error in /scrape]\n{tb}")
        raise HTTPException(status_code=500, detail={"error": str(e), "traceback": tb})


@app.post("/api/v1/simulate")
def run_quantitative_simulation(req: QuantitativeSimRequest):
    try:
        pred_demand = predict_future_demand(req.features_ml)
        pred_trend = predict_competitor_trend(req.features_ml)

        net_stock = req.on_hand_stock + req.incoming_stock
        inv_engine = StochasticInventoryEngine(service_level_z=req.service_level_z)
        inv_metrics = inv_engine.calculate_replenishment_metrics(
            current_stock=net_stock,
            predicted_daily_demand=pred_demand,
            lead_time_days=req.lead_time_days,
        )

        price_solver = ElasticPricingSolver(elasticity=req.elasticity)
        price_metrics = price_solver.solve_optimal_price(
            cost_price=req.cost_price,
            current_price=req.listed_price,
            competitor_price=req.competitor_price,
            current_stock=req.on_hand_stock,
            base_daily_demand=pred_demand,
            competitor_trend_label=pred_trend["trend_label"],
        )

        return {
            "sku": req.sku,
            "net_inventory_position": net_stock,
            "ml_predictions": {
                "predicted_daily_demand": pred_demand,
                "competitor_7d_trend": pred_trend["trend_label"],
                "trend_confidence": pred_trend["confidence"],
            },
            "inventory_math": inv_metrics,
            "pricing_math": price_metrics,
        }
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[FastAPI Error in /simulate]\n{tb}")
        raise HTTPException(status_code=500, detail={"error": str(e), "traceback": tb})


@app.post("/api/v1/audit")
def run_multi_agent_audit(req: MultiAgentAuditRequest):
    try:
        resolved_key = (req.api_key or os.getenv("GEMINI_API_KEY", "")).strip()
        if not resolved_key or resolved_key.startswith("AIzaSy_YOUR"):
            raise ValueError("Missing or placeholder GEMINI_API_KEY in D:\\scm_core_platform\\.env")

        if req.catalog_override and req.suppliers_override:
            catalog = req.catalog_override
            suppliers = req.suppliers_override
        else:
            catalog, suppliers = build_live_catalog_and_suppliers()

        # Use model from .env if configured, otherwise fallback to request model
        active_model = os.getenv("GEMINI_MODEL", req.model).strip() or "gemini-flash-latest"

        orchestrator = MultiAgentSupplyChainOrchestrator(api_key=resolved_key, model=active_model)
        orchestrator.inv_engine.z = req.service_level_z
        orchestrator.price_solver.elasticity = req.elasticity

        result = orchestrator.run_full_pipeline(catalog, suppliers)

        if not req.catalog_override:
            save_orchestrator_results(result, trigger_type="FASTAPI_ENDPOINT", model_used=active_model)

        return result
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[FastAPI Error in /audit]\n{tb}")
        raise HTTPException(status_code=500, detail={"error": str(e), "traceback": tb})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True)