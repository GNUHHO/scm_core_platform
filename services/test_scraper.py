import json
from database.db_manager import init_db
from services.scraper_service import scrape_and_sync_competitor_prices


def run_scraper_test() -> None:
    """
    Test the local HasData-architected EcommercePriceScraper and verify SQLite sync.
    """
    print("=" * 65)
    print("[ScraperTest] RUNNING LOCAL HIERARCHICAL E-COMMERCE PRICE SCRAPER")
    print("=" * 65)

    init_db()
    result = scrape_and_sync_competitor_prices()
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    run_scraper_test()