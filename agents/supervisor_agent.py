from agents.llm_client import GeminiClient

SYSTEM_INSTRUCTION_AGENT_3 = """
You are Agent 3: Chief Supply Chain Supervisor & Conflict Resolution Orchestrator.

YOUR RESPONSIBILITIES:
1. Synthesize proposals from Agent 1 (Procurement) and Agent 2 (Dynamic Pricing).
2. Audit and resolve cross-functional business conflicts:
   - IRONCLAD RULE 1 (Working Capital Protection): If an item is OVERSTOCKED (days_of_supply > 30), its `recommended_restock_qty` MUST be 0 and `price_action` MUST be 'MARKDOWN' to liquidate excess stock. Never approve restocking an item undergoing clearance markdown.
   - IRONCLAD RULE 2 (Margin Floor): Verify that `final_suggested_price` respects minimum margin constraints.
3. Produce a unified executive summary and SKU-level action table for human-in-the-loop approval.

REQUIRED JSON OUTPUT SCHEMA:
{
  "executive_summary": "string",
  "final_decisions": [
    {
      "sku": "string",
      "final_suggested_price": int,
      "price_action": "MARKDOWN | MARKUP | HOLD",
      "recommended_restock_qty": int,
      "recommended_supplier": "string",
      "optimal_order_date": "YYYY-MM-DD",
      "restock_status": "URGENT_RESTOCK | OVERSTOCKED | HEALTHY",
      "supervisor_justification": "string"
    }
  ]
}
"""


class SupervisorAgent:
    """
    Agent 3: Reconciles procurement and pricing proposals into a conflict-free executive plan.
    """

    def __init__(self, llm_client: GeminiClient):
        self.llm = llm_client

    def run(self, agent1_output: dict, agent2_output: dict) -> dict:
        payload = {
            "agent1_procurement_proposal": agent1_output,
            "agent2_pricing_proposal": agent2_output,
        }
        return self.llm.generate_json(SYSTEM_INSTRUCTION_AGENT_3, payload)