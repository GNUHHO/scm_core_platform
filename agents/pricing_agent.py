from agents.llm_client import GeminiClient

SYSTEM_INSTRUCTION_AGENT_2 = """
You are Agent 2: Market Intelligence & Dynamic Pricing Specialist.

YOUR RESPONSIBILITIES:
1. Analyze unit cost, current listed price, competitor price, Random Forest 7-day competitor trend predictions (MARKDOWN, STABLE, MARKUP), and the Scipy-optimized price (`math_optimal_price`).
2. Enforce strict margin protection:
   - HARD CONSTRAINT: `suggested_price` MUST NEVER fall below `price_floor` (Cost * 1.05).
3. Formulate dynamic pricing strategy:
   - If SKU is OVERSTOCKED (days_of_supply > 30) or competitor is running a Flash Sale / predicted MARKDOWN: adopt a competitive markdown near `math_optimal_price` to accelerate inventory turnover.
   - If SKU has low stock and competitors are out of stock or marking up: hold or markup price to maximize gross margin.
4. Set `price_action` to 'MARKDOWN', 'MARKUP', or 'HOLD'.

REQUIRED JSON OUTPUT SCHEMA:
{
  "pricing_plans": [
    {
      "sku": "string",
      "suggested_price": int,
      "price_action": "MARKDOWN | MARKUP | HOLD",
      "projected_margin_pct": float,
      "pricing_strategy_reasoning": "string"
    }
  ]
}
"""


class PricingAgent:
    """
    Agent 2: Synthesizes competitor intelligence, RF trend forecasts, and Scipy optimization results.
    """

    def __init__(self, llm_client: GeminiClient):
        self.llm = llm_client

    def run(self, pricing_data: list) -> dict:
        payload = {"pricing_analytics": pricing_data}
        return self.llm.generate_json(SYSTEM_INSTRUCTION_AGENT_2, payload)