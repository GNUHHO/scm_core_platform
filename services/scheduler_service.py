import threading
import time
import schedule
from services.scraper_service import scrape_and_sync_competitor_prices
from database.db_manager import build_live_catalog_and_suppliers, save_orchestrator_results
from agents.orchestrator import MultiAgentSupplyChainOrchestrator


def _scheduler_worker_loop() -> None:
    """Continuous background loop checking pending scheduled jobs."""
    while True:
        schedule.run_pending()
        time.sleep(30)


def start_background_scheduler(api_key: str = "", model: str = "gemini-3.8-flash") -> threading.Thread:
    """
    Register weekly Sunday 02:00 AM automated scraping and Multi-Agent audit job.
    """
    def automated_weekend_pipeline():
        print("[Scheduler] Executing scheduled weekend price scrape...")
        scrape_and_sync_competitor_prices()

        if api_key:
            print("[Scheduler] Triggering Multi-Agent Supply Chain Orchestrator...")
            catalog, suppliers = build_live_catalog_and_suppliers()
            orchestrator = MultiAgentSupplyChainOrchestrator(api_key=api_key, model=model)
            res = orchestrator.run_full_pipeline(catalog, suppliers)
            save_orchestrator_results(res, trigger_type="CRON_AUTO_WEEKEND", model_used=model)

    schedule.clear()
    schedule.every().sunday.at("02:00").do(automated_weekend_pipeline)

    thread = threading.Thread(target=_scheduler_worker_loop, daemon=True)
    thread.start()
    return thread