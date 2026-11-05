import os
import sqlite3
from datetime import datetime
import pandas as pd
from ml_engine.config import BASE_DIR, DATA_RAW_DIR

DB_PATH = os.path.join(BASE_DIR, "database", "supply_chain.db")


def get_connection() -> sqlite3.Connection:
    """Create and return a thread-safe SQLite database connection."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db() -> None:
    """Initialize database schema and seed baseline master data if empty."""
    conn = get_connection()
    cur = conn.cursor()

    # 1. Master product catalog table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS products (
        sku TEXT PRIMARY KEY,
        name TEXT,
        category TEXT,
        current_stock INTEGER,
        cost_price INTEGER,
        listed_price INTEGER,
        lead_time_days INTEGER
    )""")

    # 2. Supplier contracts and SLA policies table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS suppliers (
        supplier_id TEXT PRIMARY KEY,
        name TEXT,
        lead_time_days INTEGER,
        reliability_score REAL,
        policy TEXT
    )""")

    # 3. Scraped competitor prices table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS competitor_prices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sku TEXT,
        competitor_name TEXT,
        price INTEGER,
        stock_status TEXT,
        updated_at TEXT
    )""")

    # 4. Consolidated Multi-Agent recommendations table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS ai_recommendations (
        sku TEXT PRIMARY KEY,
        final_suggested_price INTEGER,
        price_action TEXT,
        recommended_restock_qty INTEGER,
        recommended_supplier TEXT,
        optimal_order_date TEXT,
        restock_status TEXT,
        supervisor_justification TEXT,
        approval_status TEXT DEFAULT 'PENDING',
        updated_at TEXT
    )""")

    # 5. Audit log table for executive traceability
    cur.execute("""
    CREATE TABLE IF NOT EXISTS agent_audit_logs (
        run_id INTEGER PRIMARY KEY AUTOINCREMENT,
        trigger_type TEXT,
        model_used TEXT,
        skus_processed INTEGER,
        executive_summary TEXT,
        executed_at TEXT
    )""")

    # Seed initial catalog if table is empty
    cur.execute("SELECT COUNT(*) FROM products")
    if cur.fetchone()[0] == 0:
        products_seed = [
            ("SSD-KING-1TB", "Kingston NV2 1TB PCIe 4.0 SSD", "Storage", 18, 1280000, 1550000, 3),
            ("VGA-ASUS-4060", "ASUS Dual GeForce RTX 4060 8GB GPU", "GPU", 42, 7600000, 8490000, 2),
            ("CPU-AMD-7800X3D", "AMD Ryzen 7 7800X3D Processor", "CPU", 5, 9800000, 11200000, 3),
        ]
        cur.executemany("INSERT INTO products VALUES (?,?,?,?,?,?,?)", products_seed)

        suppliers_seed = [
            ("SUP-SPC", "Vinh Xuan Distributor (SPC)", 3, 9.5,
             "Extra 2% discount on orders placed Tuesday morning. Net-30 credit terms."),
            ("SUP-VSC", "Viet Son Distributor", 2, 9.0,
             "Express 48-hour delivery within Ho Chi Minh City. Cash on delivery."),
            ("SUP-DGW", "Digiworld Distributor (DGW)", 5, 9.2,
             "Best wholesale tier for orders > 50 units. 1.5% quarterly volume rebate."),
        ]
        cur.executemany("INSERT INTO suppliers VALUES (?,?,?,?,?)", suppliers_seed)

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        competitors_seed = [
            ("SSD-KING-1TB", "Phong Vu", 1520000, "In Stock", now_str),
            ("SSD-KING-1TB", "GearVN", 1540000, "In Stock", now_str),
            ("VGA-ASUS-4060", "Phong Vu", 8190000, "In Stock (Flash Sale)", now_str),
            ("VGA-ASUS-4060", "GearVN", 8290000, "In Stock", now_str),
            ("CPU-AMD-7800X3D", "Phong Vu", 11490000, "Low Stock", now_str),
            ("CPU-AMD-7800X3D", "GearVN", 11390000, "In Stock", now_str),
        ]
        cur.executemany(
            "INSERT INTO competitor_prices (sku, competitor_name, price, stock_status, updated_at) VALUES (?,?,?,?,?)",
            competitors_seed,
        )

    conn.commit()
    conn.close()


def build_live_catalog_and_suppliers() -> tuple[list, list]:
    """
    Construct live input payloads for MultiAgentSupplyChainOrchestrator by combining
    SQLite operational records with historical time-series lag features.
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT sku, name, current_stock, cost_price, listed_price, lead_time_days FROM products")
    product_rows = cur.fetchall()

    cur.execute("SELECT supplier_id, name, lead_time_days, policy FROM suppliers")
    supplier_rows = cur.fetchall()

    suppliers_data = [
        {
            "supplier_id": r[0],
            "name": r[1],
            "lead_time_days": r[2],
            "policy": r[3],
        }
        for r in supplier_rows
    ]

    # Load historical transaction CSV to compute real lag and rolling window features
    raw_csv_path = os.path.join(DATA_RAW_DIR, "historical_sales.csv")
    df_hist = pd.read_csv(raw_csv_path) if os.path.exists(raw_csv_path) else pd.DataFrame()

    now = datetime.now()
    catalog_items = []

    for row in product_rows:
        sku, name, stock, cost, listed_price, lead_time = row

        # Query lowest active competitor price for this SKU
        cur.execute(
            "SELECT MIN(price) FROM competitor_prices WHERE sku = ? AND stock_status NOT LIKE '%Out%'",
            (sku,),
        )
        min_comp_row = cur.fetchone()
        comp_price = int(min_comp_row[0]) if (min_comp_row and min_comp_row[0]) else listed_price

        # Extract historical series for the specific SKU
        if not df_hist.empty and sku in df_hist["sku"].values:
            sku_hist = df_hist[df_hist["sku"] == sku].sort_values("date").reset_index(drop=True)
            sales_series = sku_hist["sales_qty"].tolist()
            comp_series = sku_hist["competitor_price"].tolist()

            sales_lag_1 = float(sales_series[-1])
            sales_lag_3 = float(sales_series[-3])
            sales_lag_7 = float(sales_series[-7])
            sales_lag_14 = float(sales_series[-14])

            comp_lag_1 = float(comp_series[-1])
            comp_lag_3 = float(comp_series[-3])
            comp_lag_7 = float(comp_series[-7])
            comp_lag_14 = float(comp_series[-14])

            roll_mean_7 = float(pd.Series(sales_series[-7:]).mean())
            roll_std_7 = float(pd.Series(sales_series[-7:]).std())
            roll_mean_14 = float(pd.Series(sales_series[-14:]).mean())
        else:
            # Fallback baseline statistics if historical CSV is missing
            sales_lag_1 = sales_lag_3 = sales_lag_7 = sales_lag_14 = 2.0
            comp_lag_1 = comp_lag_3 = comp_lag_7 = comp_lag_14 = float(comp_price)
            roll_mean_7 = roll_mean_14 = 2.0
            roll_std_7 = 0.5

        features_ml = {
            "day_of_week": now.weekday(),
            "day_of_month": now.day,
            "month": now.month,
            "is_weekend": 1 if now.weekday() >= 5 else 0,
            "is_promo": 0,
            "listed_price": listed_price,
            "competitor_price": comp_price,
            "cost_price": cost,
            "price_diff": listed_price - comp_price,
            "price_ratio": listed_price / max(1, comp_price),
            "margin_pct": (listed_price - cost) / max(1, listed_price),
            "sales_lag_1": sales_lag_1,
            "sales_lag_3": sales_lag_3,
            "sales_lag_7": sales_lag_7,
            "sales_lag_14": sales_lag_14,
            "comp_price_lag_1": comp_lag_1,
            "comp_price_lag_3": comp_lag_3,
            "comp_price_lag_7": comp_lag_7,
            "comp_price_lag_14": comp_lag_14,
            "sales_roll_mean_7": roll_mean_7,
            "sales_roll_std_7": roll_std_7,
            "sales_roll_mean_14": roll_mean_14,
        }

        catalog_items.append({
            "sku": sku,
            "name": name,
            "stock": stock,
            "cost": cost,
            "listed_price": listed_price,
            "competitor_price": comp_price,
            "lead_time_days": lead_time,
            "features_ml": features_ml,
        })

    conn.close()
    return catalog_items, suppliers_data


def save_orchestrator_results(result: dict, trigger_type: str = "MANUAL", model_used: str = "gemini-3.8-flash") -> None:
    """Persist Supervisor Agent decisions and audit logs into SQLite."""
    conn = get_connection()
    cur = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    exec_payload = result.get("final_executive_payload", {})
    decisions = exec_payload.get("final_decisions", [])
    summary = exec_payload.get("executive_summary", "")

    for d in decisions:
        cur.execute("""
            INSERT OR REPLACE INTO ai_recommendations (
                sku, final_suggested_price, price_action, recommended_restock_qty,
                recommended_supplier, optimal_order_date, restock_status,
                supervisor_justification, approval_status, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
        """, (
            d["sku"],
            int(d["final_suggested_price"]),
            d["price_action"],
            int(d["recommended_restock_qty"]),
            d["recommended_supplier"],
            d["optimal_order_date"],
            d["restock_status"],
            d["supervisor_justification"],
            now_str,
        ))

    cur.execute("""
        INSERT INTO agent_audit_logs (
            trigger_type, model_used, skus_processed, executive_summary, executed_at
        ) VALUES (?, ?, ?, ?, ?)
    """, (trigger_type, model_used, len(decisions), summary, now_str))

    conn.commit()
    conn.close()


def update_decision_approval(sku: str, new_status: str) -> None:
    """
    Human-in-the-loop approval handler.
    When APPROVED, automatically updates the active listed_price in the products table.
    """
    conn = get_connection()
    cur = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur.execute(
        "UPDATE ai_recommendations SET approval_status = ?, updated_at = ? WHERE sku = ?",
        (new_status, now_str, sku),
    )

    if new_status == "APPROVED":
        cur.execute("SELECT final_suggested_price FROM ai_recommendations WHERE sku = ?", (sku,))
        row = cur.fetchone()
        if row and row[0]:
            cur.execute("UPDATE products SET listed_price = ? WHERE sku = ?", (int(row[0]), sku))

    conn.commit()
    conn.close()