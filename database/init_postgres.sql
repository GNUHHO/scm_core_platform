-- ============================================================================
-- SCM CORE PLATFORM - POSTGRESQL 18 ENTERPRISE INITIALIZATION SCRIPT
-- Features used: uuidv7(), VIRTUAL Generated Columns, Window Lag Views
-- ============================================================================

-- 1. Warehouses
CREATE TABLE warehouses (
    warehouse_id VARCHAR(20) PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    address VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 2. Suppliers
CREATE TABLE suppliers (
    supplier_id VARCHAR(20) PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    default_lead_time_days INT NOT NULL CHECK (default_lead_time_days > 0),
    reliability_score NUMERIC(4, 2) DEFAULT 9.0,
    sla_policy TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 3. Products
CREATE TABLE products (
    sku VARCHAR(30) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    category VARCHAR(50) NOT NULL,
    default_supplier_id VARCHAR(20) REFERENCES suppliers(supplier_id),
    cost_price BIGINT NOT NULL CHECK (cost_price > 0),
    listed_price BIGINT NOT NULL CHECK (listed_price > 0),
    lead_time_days INT NOT NULL DEFAULT 3,
    service_level_z NUMERIC(4, 2) NOT NULL DEFAULT 1.65,
    price_elasticity NUMERIC(4, 2) NOT NULL DEFAULT -1.80,
    -- PG 18 VIRTUAL Generated Column: Tự động tính % biên lợi nhuận gộp không tốn ổ cứng
    gross_margin_pct NUMERIC(6, 2) GENERATED ALWAYS AS (
        ROUND(((listed_price - cost_price)::numeric / NULLIF(listed_price, 0)) * 100, 2)
    ) VIRTUAL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 4. Inventory Stocks
CREATE TABLE inventory_stocks (
    stock_id BIGSERIAL PRIMARY KEY,
    warehouse_id VARCHAR(20) NOT NULL REFERENCES warehouses(warehouse_id),
    sku VARCHAR(30) NOT NULL REFERENCES products(sku) ON DELETE CASCADE,
    default_bin_code VARCHAR(30) DEFAULT 'A-01-01',
    on_hand_qty INT NOT NULL DEFAULT 0 CHECK (on_hand_qty >= 0),
    reserved_qty INT NOT NULL DEFAULT 0 CHECK (reserved_qty >= 0),
    incoming_qty INT NOT NULL DEFAULT 0 CHECK (incoming_qty >= 0),
    defective_qty INT NOT NULL DEFAULT 0 CHECK (defective_qty >= 0),
    -- PG 18 VIRTUAL Generated Columns:
    available_qty INT GENERATED ALWAYS AS (
        GREATEST(0, on_hand_qty - reserved_qty)
    ) VIRTUAL,
    net_inventory_position INT GENERATED ALWAYS AS (
        GREATEST(0, on_hand_qty - reserved_qty) + incoming_qty
    ) VIRTUAL,
    min_safety_stock INT NOT NULL DEFAULT 5,
    reorder_point_rop INT NOT NULL DEFAULT 12,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (warehouse_id, sku)
);

-- 5. Scraper Target Rules
CREATE TABLE scraper_target_rules (
    rule_id SERIAL PRIMARY KEY,
    sku VARCHAR(30) NOT NULL REFERENCES products(sku) ON DELETE CASCADE,
    competitor_name VARCHAR(100) NOT NULL,
    target_product_name VARCHAR(200) NOT NULL,
    required_tokens JSONB NOT NULL DEFAULT '[]'::jsonb,
    any_of_tokens JSONB NOT NULL DEFAULT '[]'::jsonb,
    forbidden_tokens JSONB NOT NULL DEFAULT '[]'::jsonb,
    candidate_urls JSONB NOT NULL DEFAULT '[]'::jsonb,
    min_valid_price BIGINT NOT NULL,
    max_valid_price BIGINT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    UNIQUE (sku, competitor_name)
);

-- 6. Competitor Price Logs
CREATE TABLE competitor_price_logs (
    log_id UUID PRIMARY KEY DEFAULT uuidv7(),
    sku VARCHAR(30) NOT NULL REFERENCES products(sku) ON DELETE CASCADE,
    competitor_name VARCHAR(100) NOT NULL,
    matched_title VARCHAR(255),
    price BIGINT NOT NULL CHECK (price > 0),
    stock_status VARCHAR(50) DEFAULT 'In Stock',
    confidence_score NUMERIC(4, 3) DEFAULT 1.000,
    extraction_method VARCHAR(80),
    scraped_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_comp_prices_sku_time ON competitor_price_logs (sku, scraped_at DESC);

-- 7. Daily Market History
CREATE TABLE daily_market_history (
    history_id BIGSERIAL PRIMARY KEY,
    sku VARCHAR(30) NOT NULL REFERENCES products(sku) ON DELETE CASCADE,
    record_date DATE NOT NULL,
    sales_qty INT NOT NULL DEFAULT 0 CHECK (sales_qty >= 0),
    listed_price BIGINT NOT NULL,
    competitor_min_price BIGINT NOT NULL,
    cost_price BIGINT NOT NULL,
    is_promo BOOLEAN DEFAULT FALSE,
    UNIQUE (sku, record_date)
);
CREATE INDEX idx_market_history_sku_date ON daily_market_history (sku, record_date DESC);

-- 8. Agent Audit Runs & AI SKU Recommendations
CREATE TABLE agent_audit_runs (
    run_id BIGSERIAL PRIMARY KEY,
    trace_uuid UUID NOT NULL DEFAULT uuidv7(),
    trigger_type VARCHAR(50) NOT NULL,
    llm_model_used VARCHAR(60) NOT NULL DEFAULT 'gemini-2.5-flash',
    skus_processed INT NOT NULL DEFAULT 0,
    execution_time_ms INT,
    executive_summary TEXT,
    executed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE ai_sku_recommendations (
    recommendation_id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES agent_audit_runs(run_id) ON DELETE CASCADE,
    sku VARCHAR(30) NOT NULL REFERENCES products(sku) ON DELETE CASCADE,
    ml_predicted_demand NUMERIC(8, 2) NOT NULL,
    rf_competitor_trend VARCHAR(30) NOT NULL,
    rf_trend_confidence NUMERIC(4, 3),
    math_reorder_point_rop INT NOT NULL,
    math_safety_stock INT NOT NULL,
    math_optimal_price BIGINT NOT NULL,
    agent1_procurement_trace JSONB,
    agent2_pricing_trace JSONB,
    final_suggested_price BIGINT NOT NULL,
    price_action VARCHAR(40) NOT NULL,
    recommended_restock_qty INT NOT NULL DEFAULT 0,
    recommended_supplier_id VARCHAR(20) REFERENCES suppliers(supplier_id),
    optimal_order_date VARCHAR(50),
    restock_status VARCHAR(40) NOT NULL,
    supervisor_justification TEXT NOT NULL,
    approval_status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
        CHECK (approval_status IN ('PENDING', 'APPROVED', 'REJECTED', 'SUPERSEDED')),
    reviewed_by VARCHAR(100),
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 9. Purchase Orders, Goods Receipts, Batches & Ledgers
CREATE TABLE purchase_orders (
    po_id BIGSERIAL PRIMARY KEY,
    po_uuid UUID NOT NULL DEFAULT uuidv7(),
    po_number VARCHAR(40) UNIQUE NOT NULL,
    ai_recommendation_id BIGINT REFERENCES ai_sku_recommendations(recommendation_id),
    supplier_id VARCHAR(20) NOT NULL REFERENCES suppliers(supplier_id),
    warehouse_id VARCHAR(20) NOT NULL REFERENCES warehouses(warehouse_id),
    status VARCHAR(30) NOT NULL DEFAULT 'APPROVED_IN_TRANSIT',
    total_amount BIGINT NOT NULL,
    expected_delivery_date DATE,
    approved_by VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE purchase_order_items (
    po_item_id BIGSERIAL PRIMARY KEY,
    po_id BIGINT NOT NULL REFERENCES purchase_orders(po_id) ON DELETE CASCADE,
    sku VARCHAR(30) NOT NULL REFERENCES products(sku),
    ordered_qty INT NOT NULL CHECK (ordered_qty > 0),
    received_qty INT NOT NULL DEFAULT 0,
    agreed_unit_cost BIGINT NOT NULL,
    -- PG 18 VIRTUAL Column:
    line_total BIGINT GENERATED ALWAYS AS (ordered_qty * agreed_unit_cost) VIRTUAL
);

CREATE TABLE goods_receipts (
    grn_id BIGSERIAL PRIMARY KEY,
    grn_uuid UUID NOT NULL DEFAULT uuidv7(),
    grn_number VARCHAR(40) UNIQUE NOT NULL,
    po_id BIGINT NOT NULL REFERENCES purchase_orders(po_id),
    warehouse_id VARCHAR(20) NOT NULL REFERENCES warehouses(warehouse_id),
    supplier_invoice_no VARCHAR(60),
    received_by VARCHAR(100),
    received_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE inventory_batches (
    batch_id BIGSERIAL PRIMARY KEY,
    batch_number VARCHAR(60) UNIQUE NOT NULL,
    sku VARCHAR(30) NOT NULL REFERENCES products(sku),
    warehouse_id VARCHAR(20) NOT NULL REFERENCES warehouses(warehouse_id),
    initial_qty INT NOT NULL,
    remaining_qty INT NOT NULL,
    unit_import_cost BIGINT NOT NULL,
    received_date DATE NOT NULL,
    supplier_warranty_expiry DATE NOT NULL
);

CREATE TABLE stock_movements (
    movement_id UUID PRIMARY KEY DEFAULT uuidv7(),
    warehouse_id VARCHAR(20) NOT NULL REFERENCES warehouses(warehouse_id),
    sku VARCHAR(30) NOT NULL REFERENCES products(sku),
    batch_id BIGINT REFERENCES inventory_batches(batch_id),
    movement_type VARCHAR(30) NOT NULL,
    qty_change INT NOT NULL,
    on_hand_before INT NOT NULL,
    on_hand_after INT NOT NULL,
    moving_avg_cost_after BIGINT NOT NULL,
    reference_code VARCHAR(60),
    created_by VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE price_change_ledger (
    price_log_id UUID PRIMARY KEY DEFAULT uuidv7(),
    sku VARCHAR(30) NOT NULL REFERENCES products(sku),
    recommendation_id BIGINT REFERENCES ai_sku_recommendations(recommendation_id),
    old_price BIGINT NOT NULL,
    new_price BIGINT NOT NULL,
    price_action VARCHAR(40) NOT NULL,
    approved_by VARCHAR(100),
    changed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- DYNAMIC 22-FEATURE TIME-SERIES VIEW (vw_live_ml_features)
-- ============================================================================
CREATE OR REPLACE VIEW vw_live_ml_features AS
SELECT
    sku,
    record_date,
    EXTRACT(ISODOW FROM record_date)::int - 1 AS day_of_week,
    EXTRACT(DAY FROM record_date)::int AS day_of_month,
    EXTRACT(MONTH FROM record_date)::int AS month,
    CASE WHEN EXTRACT(ISODOW FROM record_date) IN (6, 7) THEN 1 ELSE 0 END AS is_weekend,
    CASE WHEN is_promo THEN 1 ELSE 0 END AS is_promo,
    listed_price,
    competitor_min_price AS competitor_price,
    cost_price,
    (listed_price - competitor_min_price) AS price_diff,
    ROUND(listed_price::numeric / NULLIF(competitor_min_price, 0), 4) AS price_ratio,
    ROUND((listed_price - cost_price)::numeric / NULLIF(listed_price, 0), 4) AS margin_pct,
    COALESCE(LAG(sales_qty, 1) OVER w, sales_qty)::numeric(8,2) AS sales_lag_1,
    COALESCE(LAG(sales_qty, 3) OVER w, sales_qty)::numeric(8,2) AS sales_lag_3,
    COALESCE(LAG(sales_qty, 7) OVER w, sales_qty)::numeric(8,2) AS sales_lag_7,
    COALESCE(LAG(sales_qty, 14) OVER w, sales_qty)::numeric(8,2) AS sales_lag_14,
    COALESCE(LAG(competitor_min_price, 1) OVER w, competitor_min_price)::numeric(12,2) AS comp_price_lag_1,
    COALESCE(LAG(competitor_min_price, 3) OVER w, competitor_min_price)::numeric(12,2) AS comp_price_lag_3,
    COALESCE(LAG(competitor_min_price, 7) OVER w, competitor_min_price)::numeric(12,2) AS comp_price_lag_7,
    COALESCE(LAG(competitor_min_price, 14) OVER w, competitor_min_price)::numeric(12,2) AS comp_price_lag_14,
    COALESCE(AVG(sales_qty) OVER (PARTITION BY sku ORDER BY record_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), sales_qty)::numeric(8,2) AS sales_roll_mean_7,
    COALESCE(STDDEV(sales_qty) OVER (PARTITION BY sku ORDER BY record_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 0.5)::numeric(8,2) AS sales_roll_std_7,
    COALESCE(AVG(sales_qty) OVER (PARTITION BY sku ORDER BY record_date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW), sales_qty)::numeric(8,2) AS sales_roll_mean_14
FROM daily_market_history
WINDOW w AS (PARTITION BY sku ORDER BY record_date);

-- ============================================================================
-- SEED MASTER DATA & 31-DAY TIME-SERIES HISTORY
-- ============================================================================
INSERT INTO warehouses (warehouse_id, name, address) VALUES
('WH-HCM-01', 'Kho Tổng Quận 7 - TP.HCM', 'Khu Chế Xuất Tân Thuận, Quận 7, TP.HCM');

INSERT INTO suppliers (supplier_id, name, default_lead_time_days, reliability_score, sla_policy) VALUES
('SUP-SPC', 'Vinh Xuan Distributor (SPC)', 3, 9.5, 'Extra 2% discount on orders placed Tuesday morning. Net-30 credit terms.'),
('SUP-VSC', 'Viet Son Distributor', 2, 9.0, 'Express 48-hour delivery within Ho Chi Minh City. Cash on delivery.'),
('SUP-DGW', 'Digiworld Distributor (DGW)', 5, 9.2, 'Best wholesale tier for orders over 50 units. 1.5% quarterly volume rebate.');

INSERT INTO products (sku, name, category, default_supplier_id, cost_price, listed_price, lead_time_days) VALUES
('SSD-KING-1TB', 'Kingston NV3 1TB PCIe 4.0 NVMe SSD', 'Storage', 'SUP-SPC', 1280000, 1550000, 3),
('VGA-ASUS-4060', 'ASUS Dual GeForce RTX 4060 8GB GPU', 'GPU', 'SUP-DGW', 7600000, 8490000, 2),
('CPU-AMD-7800X3D', 'AMD Ryzen 7 7800X3D Processor', 'CPU', 'SUP-VSC', 9800000, 11200000, 3);

INSERT INTO inventory_stocks (warehouse_id, sku, default_bin_code, on_hand_qty, reserved_qty, incoming_qty, min_safety_stock, reorder_point_rop) VALUES
('WH-HCM-01', 'SSD-KING-1TB', 'A-01-01', 18, 2, 0, 6, 19),
('WH-HCM-01', 'VGA-ASUS-4060', 'B-02-01', 42, 1, 0, 3, 9),
('WH-HCM-01', 'CPU-AMD-7800X3D', 'C-01-01', 5, 1, 0, 4, 12);

INSERT INTO competitor_price_logs (sku, competitor_name, matched_title, price, stock_status, confidence_score, extraction_method) VALUES
('SSD-KING-1TB', 'An Phat PC', 'SSD Kingston NV3 1TB PCIe Gen4 x4 NVMe', 1520000, 'In Stock', 0.945, 'DOM_CARD (.p-item)'),
('VGA-ASUS-4060', 'An Phat PC', 'VGA ASUS Dual GeForce RTX 4060 OC Edition 8GB', 8190000, 'In Stock', 0.912, 'DOM_CARD (.p-item)'),
('CPU-AMD-7800X3D', 'An Phat PC', 'CPU AMD Ryzen 7 7800X3D (AM5 - 8 Core - 16 Thread)', 11490000, 'In Stock', 0.946, 'DOM_CARD (.p-item)');

INSERT INTO daily_market_history (sku, record_date, sales_qty, listed_price, competitor_min_price, cost_price, is_promo)
SELECT 'SSD-KING-1TB', d::date, 4 + (EXTRACT(DAY FROM d)::int % 4), 1550000, 1520000 + ((EXTRACT(DAY FROM d)::int % 3) * 10000), 1280000, FALSE
FROM generate_series(CURRENT_DATE - INTERVAL '30 days', CURRENT_DATE, INTERVAL '1 day') AS d;

INSERT INTO daily_market_history (sku, record_date, sales_qty, listed_price, competitor_min_price, cost_price, is_promo)
SELECT 'VGA-ASUS-4060', d::date, 1 + (EXTRACT(DAY FROM d)::int % 3), 8490000, 8190000 + ((EXTRACT(DAY FROM d)::int % 4) * 20000), 7600000, FALSE
FROM generate_series(CURRENT_DATE - INTERVAL '30 days', CURRENT_DATE, INTERVAL '1 day') AS d;

INSERT INTO daily_market_history (sku, record_date, sales_qty, listed_price, competitor_min_price, cost_price, is_promo)
SELECT 'CPU-AMD-7800X3D', d::date, 2 + (EXTRACT(DAY FROM d)::int % 3), 11200000, 11490000 - ((EXTRACT(DAY FROM d)::int % 3) * 30000), 9800000, FALSE
FROM generate_series(CURRENT_DATE - INTERVAL '30 days', CURRENT_DATE, INTERVAL '1 day') AS d;