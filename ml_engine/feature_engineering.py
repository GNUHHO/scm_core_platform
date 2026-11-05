import pandas as pd
import numpy as np


def build_features(df: pd.DataFrame, is_training: bool = True) -> pd.DataFrame:
    """
    Construct temporal, price-competitiveness, lag, and rolling window features.
    If is_training=True, computes the 7-day forward competitor price trend target
    and drops rows where forward targets or backward lags are NaN.
    """
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(by=["sku", "date"]).reset_index(drop=True)

    # 1. Temporal & calendar features
    df["day_of_week"] = df["date"].dt.dayofweek
    df["day_of_month"] = df["date"].dt.day
    df["month"] = df["date"].dt.month
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)

    # 2. Market competitiveness features
    df["price_diff"] = df["listed_price"] - df["competitor_price"]
    df["price_ratio"] = df["listed_price"] / df["competitor_price"]
    df["margin_pct"] = (df["listed_price"] - df["cost_price"]) / df["listed_price"]

    # 3. Autoregressive lag features per SKU
    for lag in [1, 3, 7, 14]:
        df[f"sales_lag_{lag}"] = df.groupby("sku")["sales_qty"].shift(lag)
        df[f"comp_price_lag_{lag}"] = df.groupby("sku")["competitor_price"].shift(lag)

    # 4. Rolling window statistics (shifted by 1 to prevent target leakage)
    df["sales_roll_mean_7"] = df.groupby("sku")["sales_qty"].transform(
        lambda x: x.shift(1).rolling(7).mean()
    )
    df["sales_roll_std_7"] = df.groupby("sku")["sales_qty"].transform(
        lambda x: x.shift(1).rolling(7).std()
    )
    df["sales_roll_mean_14"] = df.groupby("sku")["sales_qty"].transform(
        lambda x: x.shift(1).rolling(14).mean()
    )

    if is_training:
        # 5. Forward 7-day competitor price trend target (0: MARKDOWN, 1: STABLE, 2: MARKUP)
        comp_price_next_7 = df.groupby("sku")["competitor_price"].shift(-7)
        pct_change = (comp_price_next_7 - df["competitor_price"]) / df["competitor_price"]

        # Drop rows where future target is unavailable before assigning classes
        df = df[comp_price_next_7.notna()].copy()
        pct_change = pct_change.loc[df.index]

        conditions = [
            (pct_change < -0.015),
            (pct_change >= -0.015) & (pct_change <= 0.015),
            (pct_change > 0.015),
        ]
        df["price_trend_target"] = np.select(conditions, [0, 1, 2], default=1)

    # Drop initial rows with NaN lag values
    clean_df = df.dropna().reset_index(drop=True)
    return clean_df