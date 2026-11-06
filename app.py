import os
import json
import streamlit as st
import pandas as pd

from database.db_manager import (
    init_db,
    get_connection,
    build_live_catalog_and_suppliers,
    save_orchestrator_results,
    update_decision_approval,
)
from services.scraper_service import scrape_and_sync_competitor_prices
from services.scheduler_service import start_background_scheduler
from agents.orchestrator import MultiAgentSupplyChainOrchestrator
from ml_engine.inference_service import predict_future_demand, predict_competitor_trend
from optimization_engine.stochastic_inventory import StochasticInventoryEngine
from optimization_engine.elastic_pricing_solver import ElasticPricingSolver
from ml_engine.config import DATA_RAW_DIR

# Configure Streamlit page
st.set_page_config(
    page_title="AI Supply Chain & Multi-Agent Workbench",
    page_icon="🤖",
    layout="wide",
)

# Initialize SQLite database and background cron scheduler
init_db()


@st.cache_resource
def init_cron_worker():
    """Start non-blocking background scheduler once per application session."""
    return start_background_scheduler()


init_cron_worker()

# --- SIDEBAR: GLOBAL CONFIGURATION & BATCH PIPELINE ---
with st.sidebar:
    st.title(" System & Agent Config")

    # Read API Key silently from backend environment (.env)
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    default_env_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()

    if api_key and not api_key.startswith("AIzaSy_YOUR"):
        st.success(" AI Engine: Connected (.env Loaded)")
    else:
        st.error(" AI Engine: Missing GEMINI_API_KEY in .env")

    model_options = ["gemini-2.5-flash", "gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-flash-latest"]
    default_idx = model_options.index(default_env_model) if default_env_model in model_options else 0

    model_choice = st.selectbox(
        "LLM Backbone Model",
        options=model_options,
        index=default_idx,
    )
    elasticity_param = st.slider(
        "Price Elasticity of Demand (ε)",
        min_value=-3.0,
        max_value=-0.8,
        value=-1.8,
        step=0.1,
        help="Microeconomic sensitivity of customer demand to price changes.",
    )
    service_level_z = st.selectbox(
        "Safety Stock Service Level (Z-Score)",
        options=[1.28, 1.65, 1.96, 2.33],
        index=1,
        format_func=lambda z: {
            1.28: "90% (Z=1.28)",
            1.65: "95% (Z=1.65)",
            1.96: "97.5% (Z=1.96)",
            2.33: "99% (Z=2.33)",
        }[z],
    )

    st.markdown("---")
    st.subheader(" Global Batch Pipeline")

    if st.button(" 1. Run PriceStalker Scraper", use_container_width=True):
        with st.spinner("Running PriceStalker consensus scraper across retailers..."):
            scrape_res = scrape_and_sync_competitor_prices(api_key=api_key)
            st.session_state["last_scrape_result"] = scrape_res
            st.success(f"{scrape_res['status']} ({scrape_res['updated_records']} SKUs updated)")
            st.rerun()

    if st.button(" 2. Run Full Catalog Multi-Agent Audit", type="primary", use_container_width=True):
        if not api_key or api_key.startswith("AIzaSy_YOUR"):
            st.error("Missing valid GEMINI_API_KEY in your .env file.")
        else:
            with st.status("Executing Full Supply Chain Pipeline...", expanded=True) as status:
                status.write(" Step 1/4: Syncing live competitor prices via PriceStalkerEngine...")
                scrape_res = scrape_and_sync_competitor_prices(api_key=api_key)
                st.session_state["last_scrape_result"] = scrape_res

                status.write(" Step 2/4: Building lag features & running LightGBM + Random Forest...")
                catalog, suppliers = build_live_catalog_and_suppliers()

                status.write("Step 3/4: Orchestrating Agent 1, Agent 2 & Chief Supervisor...")
                orchestrator = MultiAgentSupplyChainOrchestrator(
                    api_key=api_key, model=model_choice
                )
                orchestrator.inv_engine.z = service_level_z
                orchestrator.price_solver.elasticity = elasticity_param

                full_res = orchestrator.run_full_pipeline(catalog, suppliers)
                st.session_state["last_full_pipeline_result"] = full_res

                status.write(" Step 4/4: Persisting decisions to SQLite...")
                save_orchestrator_results(
                    full_res, trigger_type="MANUAL_WORKBENCH", model_used=model_choice
                )
                status.update(label=" Full Multi-Agent Audit Completed!", state="complete", expanded=False)
            st.rerun()

    st.markdown("---")
    st.caption(" Background Cron: **Active (Every Sunday 02:00 AM)**")

# --- MAIN PAGE HEADER ---
st.title("Multi-Agent Supply Chain Testing Workbench & Command Center")
st.caption(
    "Layer 1: LightGBM & Random Forest  •  Layer 2: Stochastic ROP & Scipy Bounded Solver  •  "
    "Layer 3: Autonomous Procurement, Pricing & Supervisor Agents"
)

# Load current operational state from SQLite
conn = get_connection()
df_master = pd.read_sql_query("""
    SELECT 
        p.sku, p.name, p.category, p.current_stock, p.cost_price, p.listed_price, p.lead_time_days,
        (SELECT MIN(price) FROM competitor_prices cp WHERE cp.sku = p.sku) AS min_comp_price,
        r.final_suggested_price, r.price_action, r.recommended_restock_qty,
        r.recommended_supplier, r.optimal_order_date, r.restock_status,
        r.supervisor_justification, r.approval_status, r.updated_at
    FROM products p
    LEFT JOIN ai_recommendations r ON p.sku = r.sku
""", conn)
df_competitors = pd.read_sql_query(
    "SELECT sku, competitor_name, price, stock_status, updated_at FROM competitor_prices ORDER BY sku, price ASC",
    conn,
)
df_logs = pd.read_sql_query(
    "SELECT run_id, trigger_type, model_used, skus_processed, executive_summary, executed_at FROM agent_audit_logs ORDER BY run_id DESC LIMIT 10",
    conn,
)
conn.close()

# --- FOUR SPECIALIZED WORKBENCH TABS ---
tab_sandbox, tab_dashboard, tab_scraper, tab_history = st.tabs([
    " 1. AI Agent Sandbox (What-If Simulator)",
    " 2. Executive Command Center (Full Catalog)",
    " 3. PriceStalker Live Scraper Lab",
    " 4. Historical Demand & Audit Logs",
])

# ==============================================================================
# TAB 1: INTERACTIVE AI AGENT SANDBOX (WHAT-IF SIMULATOR)
# ==============================================================================
with tab_sandbox:
    st.subheader(" Single-SKU Multi-Agent What-If Simulator")
    st.markdown(
        "Test how **Layer 1 (ML)**, **Layer 2 (Math Optimization)**, and **Layer 3 (Multi-Agent System)** "
        "respond to custom inventory, cost, and competitor pricing scenarios in real time."
    )

    catalog_live, suppliers_live = build_live_catalog_and_suppliers()
    sku_map = {item["sku"]: item for item in catalog_live}

    col_sel, col_preset = st.columns([2, 2])
    with col_sel:
        selected_sku = st.selectbox(
            "Select Target Product SKU",
            options=list(sku_map.keys()),
            format_func=lambda k: f"{k} — {sku_map[k]['name']}",
        )
    with col_preset:
        scenario_preset = st.selectbox(
            "Load Test Scenario Preset",
            options=[
                "Live Database Values (Default)",
                "Scenario A: Severe Overstock + Competitor Flash Sale (Test Conflict Resolution)",
                "Scenario B: Critical Stockout Risk + High Demand (Test Express Procurement)",
                "Scenario C: Competitor Stockout / Markup Opportunity (Test Margin Expansion)",
            ],
        )

    base_item = sku_map[selected_sku]

    # Determine default values based on selected scenario preset
    default_stock = int(base_item["stock"])
    default_cost = int(base_item["cost"])
    default_listed = int(base_item["listed_price"])
    default_comp = int(base_item["competitor_price"])
    default_lead = int(base_item["lead_time_days"])

    if "Scenario A" in scenario_preset:
        default_stock = 85
        default_comp = int(default_cost * 1.07)
    elif "Scenario B" in scenario_preset:
        default_stock = 2
        default_comp = int(default_listed * 1.02)
    elif "Scenario C" in scenario_preset:
        default_stock = 12
        default_comp = int(default_listed * 1.12)

    # Interactive parameter controls
    p_col1, p_col2, p_col3, p_col4, p_col5 = st.columns(5)
    sim_stock = p_col1.number_input("Current Stock (Units)", min_value=0, max_value=500, value=default_stock, step=1)
    sim_cost = p_col2.number_input("Unit Cost (VND)", min_value=100000, max_value=50000000, value=default_cost, step=50000)
    sim_listed = p_col3.number_input("Listed Price (VND)", min_value=100000, max_value=50000000, value=default_listed, step=50000)
    sim_comp = p_col4.number_input("Competitor Price (VND)", min_value=100000, max_value=50000000, value=default_comp, step=50000)
    sim_lead = p_col5.number_input("Lead Time (Days)", min_value=1, max_value=14, value=default_lead, step=1)

    # Construct simulated feature dictionary for ML inference
    sim_features = dict(base_item["features_ml"])
    sim_features["listed_price"] = sim_listed
    sim_features["competitor_price"] = sim_comp
    sim_features["cost_price"] = sim_cost
    sim_features["price_diff"] = sim_listed - sim_comp
    sim_features["price_ratio"] = sim_listed / max(1, sim_comp)
    sim_features["margin_pct"] = (sim_listed - sim_cost) / max(1, sim_listed)

    # Instant Layer 1 & Layer 2 Deterministic Preview (No API key needed)
    pred_demand = predict_future_demand(sim_features)
    pred_trend = predict_competitor_trend(sim_features)

    inv_engine = StochasticInventoryEngine(service_level_z=service_level_z)
    inv_metrics = inv_engine.calculate_replenishment_metrics(
        current_stock=sim_stock,
        predicted_daily_demand=pred_demand,
        lead_time_days=sim_lead,
    )

    price_solver = ElasticPricingSolver(elasticity=elasticity_param)
    price_metrics = price_solver.solve_optimal_price(
        cost_price=sim_cost,
        current_price=sim_listed,
        competitor_price=sim_comp,
        current_stock=sim_stock,
        base_daily_demand=pred_demand,
        competitor_trend_label=pred_trend["trend_label"],
    )

    st.markdown("#### 📐 Deterministic Quantitative Preview (Layer 1 ML + Layer 2 Math)")
    q1, q2, q3, q4, q5, q6 = st.columns(6)
    q1.metric("LightGBM Demand", f"{pred_demand} units/day")
    q2.metric("RF 7-Day Trend", f"{pred_trend['trend_label']} ({int(pred_trend['confidence']*100)}%)")
    q3.metric("Reorder Point (ROP)", f"{inv_metrics['reorder_point_rop']} units", f"SS: {inv_metrics['dynamic_safety_stock']}")
    q4.metric("Days of Supply", f"{inv_metrics['days_of_supply']} days", inv_metrics["inventory_status"])
    q5.metric("Math Restock Qty", f"{inv_metrics['recommended_restock_qty']} units")
    q6.metric("Scipy Optimal Price", f"{price_metrics['math_optimal_price']:,} VND", f"{price_metrics['optimal_margin_pct']}% margin")

    if st.button("🔬 Run Multi-Agent Simulation on This Scenario", type="primary"):
        if not api_key.strip():
            st.error("Please enter your Gemini API Key in the left sidebar to invoke the AI Agents.")
        else:
            sim_item = {
                "sku": selected_sku,
                "name": base_item["name"],
                "stock": sim_stock,
                "cost": sim_cost,
                "listed_price": sim_listed,
                "competitor_price": sim_comp,
                "lead_time_days": sim_lead,
                "features_ml": sim_features,
            }
            with st.spinner(f"Running Agent 1 -> Agent 2 -> Agent 3 using `{model_choice}`..."):
                orchestrator = MultiAgentSupplyChainOrchestrator(
                    api_key=api_key.strip(), model=model_choice
                )
                orchestrator.inv_engine.z = service_level_z
                orchestrator.price_solver.elasticity = elasticity_param
                sim_result = orchestrator.run_full_pipeline([sim_item], suppliers_live)
                st.session_state["sandbox_result"] = sim_result

    # Render side-by-side Agent debate if simulation has been executed
    if "sandbox_result" in st.session_state:
        s_res = st.session_state["sandbox_result"]
        st.markdown("---")
        st.markdown("####  Multi-Agent Reasoning & Conflict Resolution Trace")

        a1_col, a2_col, a3_col = st.columns(3)

        with a1_col:
            st.info(" **Agent 1: Procurement Specialist**")
            a1_plans = s_res.get("agent1_procurement", {}).get("procurement_plans", [])
            if a1_plans:
                p1 = a1_plans[0]
                st.markdown(f"- **Status:** `{p1.get('restock_status')}`")
                st.markdown(f"- **Order Qty:** `{p1.get('recommended_restock_qty')} units`")
                st.markdown(f"- **Supplier:** `{p1.get('recommended_supplier')}`")
                st.markdown(f"- **Order Date:** `{p1.get('optimal_order_date')}`")
                st.markdown(f"**Reasoning:**\n> {p1.get('procurement_reasoning')}")
            with st.expander("View Raw Agent 1 JSON"):
                st.json(s_res.get("agent1_procurement", {}))

        with a2_col:
            st.warning("🏷 **Agent 2: Dynamic Pricing Specialist**")
            a2_plans = s_res.get("agent2_pricing", {}).get("pricing_plans", [])
            if a2_plans:
                p2 = a2_plans[0]
                st.markdown(f"- **Action:** `{p2.get('price_action')}`")
                st.markdown(f"- **Suggested Price:** `{int(p2.get('suggested_price', 0)):,} VND`")
                st.markdown(f"- **Projected Margin:** `{p2.get('projected_margin_pct')}%`")
                st.markdown(f"**Reasoning:**\n> {p2.get('pricing_strategy_reasoning')}")
            with st.expander("View Raw Agent 2 JSON"):
                st.json(s_res.get("agent2_pricing", {}))

        with a3_col:
            st.success(" **Agent 3: Chief Supervisor (Final Verdict)**")
            exec_payload = s_res.get("final_executive_payload", {})
            decisions = exec_payload.get("final_decisions", [])
            if decisions:
                d3 = decisions[0]
                st.markdown(f"- **Final Price:** `{int(d3.get('final_suggested_price', 0)):,} VND` (`{d3.get('price_action')}`)")
                st.markdown(f"- **Final Restock Qty:** `{d3.get('recommended_restock_qty')} units` (`{d3.get('restock_status')}`)")
                st.markdown(f"- **Selected Supplier:** `{d3.get('recommended_supplier')}`")
                st.markdown(f"**Supervisor Justification:**\n> {d3.get('supervisor_justification')}")
            with st.expander("View Raw Supervisor JSON"):
                st.json(exec_payload)

# ==============================================================================
# TAB 2: EXECUTIVE COMMAND CENTER (FULL CATALOG & HUMAN APPROVAL)
# ==============================================================================
with tab_dashboard:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Monitored SKUs", len(df_master))
    col2.metric("Urgent Restock Alerts", int((df_master["restock_status"] == "URGENT_RESTOCK").sum()))
    col3.metric("Overstocked SKUs", int((df_master["restock_status"] == "OVERSTOCKED").sum()))
    col4.metric("Pending Human Approvals", int((df_master["approval_status"] == "PENDING").sum()))

    if not df_logs.empty:
        latest_log = df_logs.iloc[0]
        st.info(
            f"** Latest Chief Supervisor Executive Summary ({latest_log['executed_at']} | Model: `{latest_log['model_used']}`):**\n\n"
            f"{latest_log['executive_summary']}"
        )

    st.subheader("Master Catalog & Consolidated Agent Recommendations")
    st.dataframe(
        df_master[[
            "sku", "name", "current_stock", "cost_price", "listed_price",
            "min_comp_price", "final_suggested_price", "price_action",
            "restock_status", "recommended_restock_qty", "recommended_supplier",
            "optimal_order_date", "approval_status",
        ]],
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("###  Human-in-the-Loop Approval Cards")
    for _, row in df_master.iterrows():
        sku = row["sku"]
        status_badge = row["approval_status"] if pd.notna(row["approval_status"]) else "AWAITING_AUDIT"
        with st.expander(f" {sku} — {row['name']}  |  Approval Status: [{status_badge}]", expanded=(status_badge == "PENDING")):
            c1, c2, c3 = st.columns([2, 2, 1])
            with c1:
                st.markdown(f"**Current Stock:** `{row['current_stock']} units`")
                st.markdown(f"**Inventory Status:** `{row['restock_status']}`")
                st.markdown(f"**Recommended Restock:** `{row['recommended_restock_qty']} units` ({row['recommended_supplier']})")
                st.markdown(f"**Optimal Order Date:** `{row['optimal_order_date']}`")
            with c2:
                st.markdown(f"**Unit Cost:** `{row['cost_price']:,} VND`")
                st.markdown(f"**Current Listed Price:** `{row['listed_price']:,} VND`")
                min_cp = int(row["min_comp_price"]) if pd.notna(row["min_comp_price"]) else row["listed_price"]
                st.markdown(f"**Live Competitor Price:** `{min_cp:,} VND`")
                sug_p = int(row["final_suggested_price"]) if pd.notna(row["final_suggested_price"]) else row["listed_price"]
                st.markdown(f"**AI Suggested Price:** `{sug_p:,} VND` (`{row['price_action']}`)")
            with c3:
                if pd.notna(row["final_suggested_price"]):
                    if st.button(" Approve", key=f"approve_{sku}", use_container_width=True):
                        update_decision_approval(sku, "APPROVED")
                        st.success(f"Approved {sku}!")
                        st.rerun()
                    if st.button(" Reject", key=f"reject_{sku}", use_container_width=True):
                        update_decision_approval(sku, "REJECTED")
                        st.warning(f"Rejected {sku}.")
                        st.rerun()

            if pd.notna(row["supervisor_justification"]):
                st.markdown(f"**Supervisor Justification:**\n> {row['supervisor_justification']}")

# ==============================================================================
# TAB 3: PRICESTALKER LIVE SCRAPER LAB
# ==============================================================================
with tab_scraper:
    st.subheader(" PriceStalker v2.0 Consensus Scraper Diagnostics")
    st.markdown(
        "Inspect live competitor prices extracted via **Word-Boundary Hardware Gating**, "
        "**DOM Denoising**, and **Multi-Strategy Consensus Voting**."
    )

    if st.button(" Trigger Live PriceStalker Extraction Now"):
        with st.spinner("Stalking competitor prices across An Phat PC & MemoryZone..."):
            scrape_res = scrape_and_sync_competitor_prices(api_key=api_key)
            st.session_state["last_scrape_result"] = scrape_res
            st.rerun()

    if "last_scrape_result" in st.session_state:
        st.markdown("#### Latest Scraper Execution Diagnostic Output")
        st.json(st.session_state["last_scrape_result"])

    st.markdown("#### Active Competitor Price Table in SQLite")
    st.dataframe(df_competitors, use_container_width=True, hide_index=True)

# ==============================================================================
# TAB 4: HISTORICAL DEMAND & AUDIT LOGS
# ==============================================================================
with tab_history:
    st.subheader(" Historical Sales & Competitor Price Dynamics (Last 90 Days)")
    raw_csv_path = os.path.join(DATA_RAW_DIR, "historical_sales.csv")
    if os.path.exists(raw_csv_path):
        df_hist = pd.read_csv(raw_csv_path)
        hist_sku = st.selectbox("Select SKU to visualize time series:", df_hist["sku"].unique())
        sku_df = df_hist[df_hist["sku"] == hist_sku].tail(90)
        st.line_chart(sku_df.set_index("date")[["sales_qty"]])
        st.line_chart(sku_df.set_index("date")[["listed_price", "competitor_price"]])

    st.subheader(" Multi-Agent Execution Audit Trail")
    st.dataframe(df_logs, use_container_width=True, hide_index=True)