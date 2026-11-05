import os
from agents.llm_client import GeminiClient

SCRAPER_AGENT_SYSTEM_PROMPT = """
You are the Market Intelligence & Web Scraping Specialist Agent (Agent 0) in a Supply Chain Multi-Agent System.
Your role is to audit candidate prices extracted from Vietnamese hardware retailers (An Phat PC, MemoryZone, GearVN, Phong Vu).

STRICT HARDWARE VERIFICATION RULES:
1. Verify exact chipset, brand, and capacity parity (e.g., Kingston 1TB/1000G != 500GB; RTX 4060 != RTX 4060 Ti; Ryzen 7 7800X3D != 9800X3D).
2. Reject installment prices, bundle deals, PC build prices, or out-of-stock placeholders.
3. If a product line was succeeded by an immediate replacement at the same tier (e.g., Kingston NV2 1TB -> NV3 1TB), accept it and note the transition.

REQUIRED JSON OUTPUT SCHEMA:
{
  "selected_price": int,
  "matched_title": "string",
  "confidence": float,
  "stock_status": "In Stock | Low Stock | Out of Stock",
  "agent_reasoning": "Concise 1-sentence explanation of why this candidate was chosen over others."
}
"""


class MarketScraperAgent:
    """
    Agent 0: Autonomous Market Intelligence & Price Verification Agent.
    Uses Gemini to arbitrate ambiguous DOM candidates and verify hardware specifications
    """

    def __init__(self, api_key: str = None, model: str = None):
        resolved_key = (api_key or os.getenv("GEMINI_API_KEY", "")).strip()
        resolved_model = (model or os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")).strip()
        self.llm_client = (
            GeminiClient(api_key=resolved_key, default_model=resolved_model)
            if resolved_key
            else None
        )

    def verify_and_select_candidate(
        self, sku: str, target_product_name: str, candidates: list[dict], force_ai: bool = False
    ) -> dict:
        """
        Arbitrate extracted price candidates using deterministic consensus first,
        escalating to Gemini LLM reasoning when candidates conflict or force_ai=True.
        """
        if not candidates:
            return {
                "price": 0,
                "matched_title": "",
                "confidence": 0.0,
                "method": "NO_VALID_CANDIDATES",
                "agent_reasoning": "No HTML elements matched the hardware discriminator boundaries.",
            }

        top = candidates[0]

        # Count consensus votes across different extractors (JSON-LD, Meta, DOM Card)
        price_votes = {}
        for c in candidates:
            price_votes[c["price"]] = price_votes.get(c["price"], 0) + 1

        # Fast-path: High deterministic confidence and no forced AI call
        if not force_ai and (price_votes[top["price"]] >= 2 or top["confidence"] >= 0.85 or not self.llm_client):
            return {
                "price": top["price"],
                "matched_title": top["title"],
                "confidence": top["confidence"],
                "method": f"DETERMINISTIC_CONSENSUS ({top['extractor']})",
                "agent_reasoning": (
                    f"Selected '{top['title']}' at {top['price']:,} VND via high-confidence "
                    f"hardware token match (score={top['confidence']})."
                ),
            }

        # Slow-path / Agentic path: Invoke Gemini Agent to resolve ambiguity
        if self.llm_client:
            try:
                user_payload = {
                    "sku": sku,
                    "target_product": target_product_name,
                    "extracted_candidates": candidates[:6],
                }
                ai_res = self.llm_client.generate_json(SCRAPER_AGENT_SYSTEM_PROMPT, user_payload)
                sel_price = int(ai_res.get("selected_price", 0))
                if sel_price > 0:
                    return {
                        "price": sel_price,
                        "matched_title": ai_res.get("matched_title", top["title"]),
                        "confidence": float(ai_res.get("confidence", 0.95)),
                        "method": "AGENT_0_GEMINI_VERIFIED",
                        "agent_reasoning": ai_res.get(
                            "agent_reasoning", "Verified by MarketScraperAgent via LLM inspection."
                        ),
                    }
            except Exception as e:
                print(f"[MarketScraperAgent] LLM arbitration warning for {sku}: {e}")

        return {
            "price": top["price"],
            "matched_title": top["title"],
            "confidence": top["confidence"],
            "method": f"FALLBACK_TOP_CANDIDATE ({top['extractor']})",
            "agent_reasoning": "Fallback to highest-scoring DOM candidate.",
        }