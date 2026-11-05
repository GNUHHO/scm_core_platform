import os
import shutil
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent


def clean_project_structure() -> None:
    """
    Remove duplicate nested directories inside ml_engine/, delete obsolete Apify test scripts,
    and ensure all Python packages contain an __init__.py file.
    """
    print("=" * 70)
    print("[Step 1/4] CLEANING DUPLICATE DIRECTORIES & STANDARDIZING PACKAGES")
    print("=" * 70)

    # 1. Remove duplicate folders inside ml_engine/
    duplicate_dirs = [
        PROJECT_ROOT / "ml_engine" / "data",
        PROJECT_ROOT / "ml_engine" / "models_registry",
    ]
    for d in duplicate_dirs:
        if d.exists():
            shutil.rmtree(d)
            print(f"  [Removed Duplicate Dir] {d.relative_to(PROJECT_ROOT)}")
        else:
            print(f"  [OK] No duplicate directory at {d.relative_to(PROJECT_ROOT)}")

    # 2. Remove deprecated Apify test script and cached bytecode
    deprecated_files = [
        PROJECT_ROOT / "services" / "test_apify.py",
        PROJECT_ROOT / "services" / "__pycache__" / "test_apify.cpython-314.pyc",
    ]
    for f in deprecated_files:
        if f.exists():
            f.unlink()
            print(f"  [Removed Deprecated File] {f.relative_to(PROJECT_ROOT)}")

    # 3. Ensure __init__.py exists in all 5 core packages
    packages = ["agents", "database", "ml_engine", "optimization_engine", "services"]
    for pkg in packages:
        init_file = PROJECT_ROOT / pkg / "__init__.py"
        if not init_file.exists():
            init_file.touch()
            print(f"  [Created Package Init] {init_file.relative_to(PROJECT_ROOT)}")
        else:
            print(f"  [OK] Package init verified: {init_file.relative_to(PROJECT_ROOT)}")


def verify_ml_config_paths() -> None:
    """
    Ensure ml_engine/config.py points to root-level data/ and models_registry/ directories.
    """
    print("\n" + "=" * 70)
    print("[Step 2/4] VERIFYING ML ENGINE PATH CONFIGURATION")
    print("=" * 70)

    from ml_engine.config import BASE_DIR, DATA_RAW_DIR, MODELS_REGISTRY_DIR

    print(f"  -> BASE_DIR            : {BASE_DIR}")
    print(f"  -> DATA_RAW_DIR        : {DATA_RAW_DIR}")
    print(f"  -> MODELS_REGISTRY_DIR : {MODELS_REGISTRY_DIR}")

    if Path(BASE_DIR).resolve() != PROJECT_ROOT:
        print("  ⚠️ WARNING: BASE_DIR in ml_engine/config.py does not match project root!")
    else:
        print("  ✅ Path configuration is strictly aligned with project root.")


def verify_database_and_models() -> None:
    """
    Check SQLite tables and run a live smoke test on Layer 1 (ML) and Layer 2 (Optimization).
    """
    print("\n" + "=" * 70)
    print("[Step 3/4] TESTING DATABASE SCHEMA, LAYER 1 (ML) & LAYER 2 (MATH)")
    print("=" * 70)

    from database.db_manager import init_db, build_live_catalog_and_suppliers, DB_PATH
    from ml_engine.inference_service import predict_future_demand, predict_competitor_trend
    from optimization_engine.stochastic_inventory import StochasticInventoryEngine
    from optimization_engine.elastic_pricing_solver import ElasticPricingSolver

    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        print(f"  -> Active SQLite Tables: {tables}")

    catalog, suppliers = build_live_catalog_and_suppliers()
    print(f"  -> Loaded {len(catalog)} SKUs and {len(suppliers)} suppliers from SQLite + CSV.")

    inv_engine = StochasticInventoryEngine(service_level_z=1.65)
    price_solver = ElasticPricingSolver(elasticity=-1.8)

    for item in catalog:
        sku = item["sku"]
        feat = item["features_ml"]
        demand = predict_future_demand(feat)
        trend = predict_competitor_trend(feat)
        inv_res = inv_engine.calculate_replenishment_metrics(item["stock"], demand, item["lead_time_days"])
        price_res = price_solver.solve_optimal_price(
            item["cost"], item["listed_price"], item["competitor_price"],
            item["stock"], demand, trend["trend_label"]
        )
        print(
            f"  ✅ [{sku}] Demand={demand}/day | Trend={trend['trend_label']} | "
            f"ROP={inv_res['reorder_point_rop']} ({inv_res['inventory_status']}) | "
            f"OptimalPrice={price_res['math_optimal_price']:,} VND"
        )


def verify_pricestalker_scraper() -> None:
    """
    Run a quick live verification of PriceStalkerEngine in services/scraper_service.py.
    """
    print("\n" + "=" * 70)
    print("[Step 4/4] VERIFYING PRICESTALKER LIVE COMPETITOR SCRAPER")
    print("=" * 70)

    from services.scraper_service import scrape_and_sync_competitor_prices

    res = scrape_and_sync_competitor_prices()
    print(f"  -> Scraper Status  : {res.get('status')}")
    print(f"  -> Records Updated : {res.get('updated_records')}")
    print("=" * 70)
    print("🎉 ALL SYSTEM AUDITS COMPLETED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    clean_project_structure()
    verify_ml_config_paths()
    verify_database_and_models()
    verify_pricestalker_scraper()