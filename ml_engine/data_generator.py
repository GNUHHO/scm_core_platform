import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from ml_engine.config import DATA_RAW_DIR


def generate_retail_sales_data(days: int = 365) -> pd.DataFrame:
    """
    Generate synthetic daily retail transaction records incorporating
    weekend seasonality, promotional lifts, and microeconomic price elasticity.
    """
    np.random.seed(42)
    start_date = datetime(2025, 10, 1)
    skus = [
        {"sku": "SSD-KING-1TB", "base_price": 1550000, "base_cost": 1280000, "base_demand": 4.5},
        {"sku": "VGA-ASUS-4060", "base_price": 8490000, "base_cost": 7600000, "base_demand": 1.2},
        {"sku": "CPU-AMD-7800X3D", "base_price": 11200000, "base_cost": 9800000, "base_demand": 1.8},
    ]

    records = []
    for day_idx in range(days):
        current_date = start_date + timedelta(days=day_idx)
        is_weekend = 1 if current_date.weekday() >= 5 else 0

        for item in skus:
            # Simulate competitor price fluctuations (e.g., flash sales or markups)
            comp_diff_pct = np.random.choice(
                [-0.05, -0.02, 0.0, 0.02, 0.05], p=[0.10, 0.25, 0.40, 0.15, 0.10]
            )
            comp_price = int(item["base_price"] * (1 + comp_diff_pct))
            is_promo = 1 if np.random.rand() < 0.15 else 0

            # Compute expected demand using constant price elasticity (-1.5)
            price_ratio = item["base_price"] / comp_price
            demand_mean = (
                item["base_demand"]
                * (1 + 0.4 * is_weekend)
                * (1 + 0.6 * is_promo)
                * (price_ratio ** -1.5)
            )
            sales_qty = np.random.poisson(max(0.1, demand_mean))

            records.append({
                "date": current_date.strftime("%Y-%m-%d"),
                "sku": item["sku"],
                "listed_price": item["base_price"],
                "cost_price": item["base_cost"],
                "competitor_price": comp_price,
                "is_promo": is_promo,
                "sales_qty": sales_qty,
            })

    df = pd.DataFrame(records)
    output_path = os.path.join(DATA_RAW_DIR, "historical_sales.csv")
    df.to_csv(output_path, index=False)
    print(f"[DataGenerator] Generated {len(df)} records -> {output_path}")
    return df


if __name__ == "__main__":
    generate_retail_sales_data()