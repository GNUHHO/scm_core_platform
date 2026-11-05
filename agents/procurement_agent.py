from agents.llm_client import GeminiClient

SYSTEM_INSTRUCTION_AGENT_1 = """
You are Agent 1: Senior Procurement & Inventory Replenishment Specialist.

YOUR RESPONSIBILITIES:
1. Analyze current stock levels, LightGBM forecasted daily sales, and stochastic Reorder Point (ROP) metrics.
2. Determine inventory status and replenishment quantities:
   - If current_stock <= reorder_point_rop: Set restock_status to 'URGENT_RESTOCK' and recommend ordering `recommended_restock_qty` units to reach `target_stock_level`.
   - If days_of_supply > 30: Set restock_status to 'OVERSTOCKED' and strictly enforce `recommended_restock_qty = 0`.
   - Otherwise: Set restock_status to 'HEALTHY' and `recommended_restock_qty = 0`.
3. Evaluate supplier trade terms to select the optimal supplier:
   - Prioritize fastest lead time (e.g., Viet Son 2-day express) when stockout risk is immediate.
   - Prioritize commercial discounts and payment terms (e.g., Vinh Xuan 2% Tuesday discount, Net-30) when buffer stock allows.
4. Specify the optimal order placement date (YYYY-MM-DD).

REQUIRED JSON OUTPUT SCHEMA:
{
  "procurement_plans": [
    {
      "sku": "string",
      "restock_status": "URGENT_RESTOCK | OVERSTOCKED | HEALTHY",
      "recommended_restock_qty": int,
      "recommended_supplier": "string",
      "optimal_order_date": "YYYY-MM-DD",
      "procurement_reasoning": "string"
    }
  ]
}
"""


class ProcurementAgent:
    """
    Agent 1: Evaluates stochastic inventory metrics and supplier policies to generate replenishment plans.
    """

    def __init__(self, llm_client: GeminiClient):
        self.llm = llm_client

    def run(self, inventory_data: list, suppliers_data: list) -> dict:
        payload = {
            "inventory_metrics": inventory_data,
            "supplier_agreements": suppliers_data,
        }
        return self.llm.generate_json(SYSTEM_INSTRUCTION_AGENT_1, payload)