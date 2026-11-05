from ml_engine.inference_service import predict_future_demand, predict_competitor_trend
from optimization_engine.stochastic_inventory import StochasticInventoryEngine
from optimization_engine.elastic_pricing_solver import ElasticPricingSolver


def test_pipeline_integration() -> None:
    print("=" * 65)
    print("[Test] INTEGRATION TEST: LAYER 1 (ML) + LAYER 2 (OPTIMIZATION)")
    print("=" * 65)

    inv_engine = StochasticInventoryEngine(service_level_z=1.65)
    price_solver = ElasticPricingSolver(elasticity=-1.8)

    test_cases = [
        {
            "sku": "SSD-KING-1TB",
            "name": "Kingston NV2 1TB PCIe 4.0 SSD",
            "stock": 18,
            "cost": 1280000,
            "listed_price": 1550000,
            "competitor_price": 1520000,
            "features_ml": {
                "day_of_week": 4, "day_of_month": 16, "month": 10, "is_weekend": 0, "is_promo": 0,
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
            "name": "ASUS Dual GeForce RTX 4060 8GB GPU (Overstocked)",
            "stock": 42,
            "cost": 7600000,
            "listed_price": 8490000,
            "competitor_price": 8190000,
            "features_ml": {
                "day_of_week": 4, "day_of_month": 16, "month": 10, "is_weekend": 0, "is_promo": 0,
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

    for item in test_cases:
        print(f"\n[SKU Analysis] {item['sku']} - {item['name']}")

        pred_demand = predict_future_demand(item["features_ml"])
        trend_info = predict_competitor_trend(item["features_ml"])
        print(f"  [Layer 1 ML] Forecasted Demand (LightGBM): {pred_demand} units/day")
        print(f"  [Layer 1 ML] Competitor Price Trend (RF): {trend_info['trend_label']} "
              f"(Confidence: {trend_info['confidence']*100:.1f}%)")

        inv_result = inv_engine.calculate_replenishment_metrics(
            current_stock=item["stock"],
            predicted_daily_demand=pred_demand,
            lead_time_days=3,
        )
        print(f"  [Layer 2 Inventory] Stock: {inv_result['current_stock']} | "
              f"ROP: {inv_result['reorder_point_rop']} | Safety Stock: {inv_result['dynamic_safety_stock']}")
        print(f"  [Layer 2 Inventory] Days of Supply: {inv_result['days_of_supply']} days -> "
              f"Status: {inv_result['inventory_status']} | Suggested Order Qty: {inv_result['recommended_restock_qty']}")

        price_result = price_solver.solve_optimal_price(
            cost_price=item["cost"],
            current_price=item["listed_price"],
            competitor_price=item["competitor_price"],
            current_stock=item["stock"],
            base_daily_demand=pred_demand,
            competitor_trend_label=trend_info["trend_label"],
        )
        print(f"  [Layer 2 Pricing] Listed: {item['listed_price']:,} VND -> "
              f"Optimal: {price_result['math_optimal_price']:,} VND "
              f"(Margin: {price_result['optimal_margin_pct']}% | Action: {price_result['price_action']})")


if __name__ == "__main__":
    test_pipeline_integration()