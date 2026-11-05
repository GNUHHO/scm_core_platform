import os
import json
from agents.orchestrator import MultiAgentSupplyChainOrchestrator


def run_test() -> None:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        api_key = input("Enter your Gemini API Key: ").strip()

    suppliers = [
        {
            "supplier_id": "SUP-SPC",
            "name": "Vinh Xuan Distributor (SPC)",
            "lead_time_days": 3,
            "policy": "Extra 2% discount on orders placed Tuesday morning. Net-30 credit terms.",
        },
        {
            "supplier_id": "SUP-VSC",
            "name": "Viet Son Distributor",
            "lead_time_days": 2,
            "policy": "Express 48-hour delivery within Ho Chi Minh City. Cash on delivery.",
        },
        {
            "supplier_id": "SUP-DGW",
            "name": "Digiworld Distributor (DGW)",
            "lead_time_days": 5,
            "policy": "Best wholesale tier for orders > 50 units. 1.5% quarterly volume rebate.",
        },
    ]

    catalog = [
        {
            "sku": "SSD-KING-1TB",
            "name": "Kingston NV2 1TB PCIe 4.0 SSD",
            "stock": 18,
            "cost": 1280000,
            "listed_price": 1550000,
            "competitor_price": 1520000,
            "lead_time_days": 3,
            "features_ml": {
                "day_of_week": 4, "day_of_month": 23, "month": 10, "is_weekend": 0, "is_promo": 0,
                "listed_price": 1550000, "competitor_price": 1520000, "cost_price": 1280000,
                "price_diff": 30000, "price_ratio": 1550000 / 1520000,
                "margin_pct": (1550000 - 1280000) / 1550000,
                "sales_lag_1": 4, "sales_lag_3": 5, "sales_lag_7": 4, "sales_lag_14": 4,
                "comp_price_lag_1": 1520000, "comp_price_lag_3": 1520000,
                "comp_price_lag_7": 1530000, "comp_price_lag_14": 1550000,
                "sales_roll_mean_7": 4.5, "sales_roll_std_7": 1.2, "sales_roll_mean_14": 4.3,
            },
        },
        {
            "sku": "VGA-ASUS-4060",
            "name": "ASUS Dual GeForce RTX 4060 8GB GPU",
            "stock": 42,
            "cost": 7600000,
            "listed_price": 8490000,
            "competitor_price": 8190000,
            "lead_time_days": 2,
            "features_ml": {
                "day_of_week": 4, "day_of_month": 23, "month": 10, "is_weekend": 0, "is_promo": 0,
                "listed_price": 8490000, "competitor_price": 8190000, "cost_price": 7600000,
                "price_diff": 300000, "price_ratio": 8490000 / 8190000,
                "margin_pct": (8490000 - 7600000) / 8490000,
                "sales_lag_1": 1, "sales_lag_3": 1, "sales_lag_7": 1, "sales_lag_14": 1,
                "comp_price_lag_1": 8190000, "comp_price_lag_3": 8250000,
                "comp_price_lag_7": 8390000, "comp_price_lag_14": 8490000,
                "sales_roll_mean_7": 0.8, "sales_roll_std_7": 0.4, "sales_roll_mean_14": 0.9,
            },
        },
    ]

    orchestrator = MultiAgentSupplyChainOrchestrator(api_key=api_key, model="gemini-3.5-flash-lite")
    result = orchestrator.run_full_pipeline(catalog, suppliers)

    print("\n" + "=" * 70)
    print("[Supervisor Report] FINAL CONSOLIDATED SUPPLY CHAIN DECISIONS")
    print("=" * 70)
    print(f"Executive Summary:\n{result['final_executive_payload']['executive_summary']}\n")
    print(json.dumps(result["final_executive_payload"]["final_decisions"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    run_test()