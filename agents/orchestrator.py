import inspect
import time
from concurrent.futures import ThreadPoolExecutor
from ml_engine.inference_service import predict_future_demand, predict_competitor_trend
from optimization_engine.stochastic_inventory import StochasticInventoryEngine
from optimization_engine.elastic_pricing_solver import ElasticPricingSolver
from agents.llm_client import GeminiClient
from agents.procurement_agent import ProcurementAgent
from agents.pricing_agent import PricingAgent
from agents.supervisor_agent import SupervisorAgent


class MultiAgentSupplyChainOrchestrator:
    """
    Central coordinator connecting Layer 1 (Predictive ML), Layer 2 (Quantitative Math),
    and Layer 3 (Parallel Multi-Agent Reasoning with Chief Supervisor Arbitration).
    """

    def __init__(self, api_key: str, model: str = "gemini-3.5-flash-lite"):
        self.api_key = api_key
        self.model = model

        # Initialize shared Gemini LLM Client
        self.llm_client = self._init_llm_client(api_key, model)

        # Layer 2: Quantitative Math Engines
        self.inv_engine = StochasticInventoryEngine(service_level_z=1.65)
        self.price_solver = ElasticPricingSolver(elasticity=-1.8)

        # Layer 3: Autonomous Specialist Agents
        self.procurement_agent = self._init_agent(ProcurementAgent)
        self.pricing_agent = self._init_agent(PricingAgent)
        self.supervisor_agent = self._init_agent(SupervisorAgent)

    @staticmethod
    def _init_llm_client(api_key: str, model: str) -> GeminiClient:
        sig = inspect.signature(GeminiClient.__init__)
        params = sig.parameters
        if "default_model" in params:
            return GeminiClient(api_key=api_key, default_model=model)
        if "model" in params:
            return GeminiClient(api_key=api_key, model=model)
        return GeminiClient(api_key)

    def _init_agent(self, agent_cls):
        """Instantiate an agent class regardless of whether it expects GeminiClient or (api_key, model)."""
        sig = inspect.signature(agent_cls.__init__)
        params = [p for p in sig.parameters.keys() if p != "self"]

        if not params:
            return agent_cls()
        if "api_key" in params:
            if "model" in params:
                return agent_cls(api_key=self.api_key, model=self.model)
            return agent_cls(api_key=self.api_key)

        return agent_cls(self.llm_client)

    @staticmethod
    def _invoke_with_matching_arity(fn, *candidate_args):
        """
        Inspect the target method signature and pass the exact number of positional arguments it expects.
        For example, if SupervisorAgent.run(self, procurement_plan, pricing_plan) expects 2 args,
        and 3 args (catalog, agent1, agent2) are provided, it automatically passes (agent1, agent2).
        """
        sig = inspect.signature(fn)
        pos_params = [
            p for p in sig.parameters.values()
            if p.name != "self" and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        ]
        has_varargs = any(p.kind == p.VAR_POSITIONAL for p in sig.parameters.values())

        if has_varargs or len(pos_params) >= len(candidate_args):
            return fn(*candidate_args)

        if len(pos_params) == 2 and len(candidate_args) == 3:
            # SupervisorAgent.run(procurement_plan, pricing_plan) -> take the last 2 arguments
            first_param_name = pos_params[0].name.lower()
            if "catalog" in first_param_name or "context" in first_param_name:
                return fn(candidate_args[0], candidate_args[1])
            return fn(candidate_args[1], candidate_args[2])

        if len(pos_params) == 1:
            return fn(candidate_args[0])

        return fn(*candidate_args[: len(pos_params)])

    def _call_agent_method(self, agent_obj, candidate_methods: list[str], *args):
        """Find the execution method on an agent instance and invoke it with matched argument count."""
        for name in candidate_methods:
            if hasattr(agent_obj, name):
                method = getattr(agent_obj, name)
                return self._invoke_with_matching_arity(method, *args)

        for attr_name in dir(agent_obj):
            if not attr_name.startswith("_"):
                attr = getattr(agent_obj, attr_name)
                if callable(attr):
                    return self._invoke_with_matching_arity(attr, *args)

        raise AttributeError(f"No callable execution method found on {type(agent_obj).__name__}")

    def run_full_pipeline(self, catalog_items: list[dict], suppliers_data: list[dict]) -> dict:
        """
        Execute the end-to-end neuro-symbolic pipeline with parallel Agent 1 & Agent 2 execution
        and strict JSON schema normalization for C# .NET 10 ERP persistence.
        """
        start_ts = time.perf_counter()
        enriched_catalog = []
        catalog_by_sku = {}

        for item in catalog_items:
            sku = item["sku"]
            features = item["features_ml"]

            on_hand_stock = int(item.get("stock", item.get("current_stock", 0)))
            incoming_stock = int(item.get("incoming_stock", 0))
            net_inventory_position = on_hand_stock + incoming_stock

            # --- LAYER 1: Machine Learning Inference ---
            pred_demand = float(predict_future_demand(features))
            pred_trend = predict_competitor_trend(features)

            # --- LAYER 2: Quantitative Optimization ---
            inv_metrics = self.inv_engine.calculate_replenishment_metrics(
                current_stock=net_inventory_position,
                predicted_daily_demand=pred_demand,
                lead_time_days=int(item["lead_time_days"]),
            )
            inv_metrics["reorder_point_rop"] = int(round(float(inv_metrics.get("reorder_point_rop", 10))))
            inv_metrics["dynamic_safety_stock"] = int(round(float(inv_metrics.get("dynamic_safety_stock", 4))))

            price_metrics = self.price_solver.solve_optimal_price(
                cost_price=int(item["cost"]),
                current_price=int(item["listed_price"]),
                competitor_price=int(item["competitor_price"]),
                current_stock=on_hand_stock,
                base_daily_demand=pred_demand,
                competitor_trend_label=pred_trend["trend_label"],
            )
            price_metrics["math_optimal_price"] = int(
                round(float(price_metrics.get("math_optimal_price", item["listed_price"])))
            )

            enriched_item = {
                "sku": sku,
                "name": item["name"],
                "stock": net_inventory_position,
                "current_stock": net_inventory_position,
                "on_hand_stock": on_hand_stock,
                "incoming_stock": incoming_stock,
                "net_inventory_position": net_inventory_position,
                "cost": int(item["cost"]),
                "cost_price": int(item["cost"]),
                "listed_price": int(item["listed_price"]),
                "competitor_price": int(item["competitor_price"]),
                "lead_time_days": int(item["lead_time_days"]),
                "ml_predictions": {
                    "predicted_daily_demand": round(pred_demand, 2),
                    "competitor_7d_trend": str(pred_trend.get("trend_label", "STABLE")),
                    "trend_confidence": round(float(pred_trend.get("confidence", 0.85)), 3),
                },
                "inventory_math": inv_metrics,
                "pricing_math": price_metrics,
            }
            enriched_catalog.append(enriched_item)
            catalog_by_sku[sku] = enriched_item

        # --- LAYER 3A: Parallel Execution of Agent 1 & Agent 2 ---
        print(f"[Orchestrator] Dispatching Agent 1 & Agent 2 in parallel using {self.model}...")
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_proc = executor.submit(
                self._call_agent_method,
                self.procurement_agent,
                ["generate_procurement_plan", "analyze_procurement", "evaluate_inventory", "run"],
                enriched_catalog,
                suppliers_data,
            )
            future_price = executor.submit(
                self._call_agent_method,
                self.pricing_agent,
                ["generate_pricing_plan", "analyze_pricing", "optimize_catalog_prices", "run"],
                enriched_catalog,
            )

            agent1_output = future_proc.result()
            agent2_output = future_price.result()

        # Normalize Agent 1 & Agent 2 output keys
        if isinstance(agent1_output, list):
            agent1_output = {"procurement_plans": agent1_output}
        elif isinstance(agent1_output, dict) and "procurement_plans" not in agent1_output:
            for v in list(agent1_output.values()):
                if isinstance(v, list):
                    agent1_output["procurement_plans"] = v
                    break
            else:
                agent1_output["procurement_plans"] = []

        if isinstance(agent2_output, list):
            agent2_output = {"pricing_plans": agent2_output}
        elif isinstance(agent2_output, dict) and "pricing_plans" not in agent2_output:
            for v in list(agent2_output.values()):
                if isinstance(v, list):
                    agent2_output["pricing_plans"] = v
                    break
            else:
                agent2_output["pricing_plans"] = []

        # --- LAYER 3B: Chief Supervisor Conflict Resolution (Agent 3) ---
        print("[Orchestrator] Running Agent 3 (Chief Supervisor) for cross-functional arbitration...")
        supervisor_raw = self._call_agent_method(
            self.supervisor_agent,
            ["arbitrate_and_finalize", "synthesize_and_resolve", "resolve_conflicts", "run"],
            enriched_catalog,
            agent1_output,
            agent2_output,
        )

        # Normalize Supervisor payload so C# WarehouseInventoryService parses every field cleanly
        supervisor_output = self._normalize_supervisor_output(
            supervisor_raw, catalog_by_sku, agent1_output, agent2_output
        )

        elapsed_ms = int((time.perf_counter() - start_ts) * 1000)
        print(f"[Orchestrator] Full Multi-Agent pipeline completed in {elapsed_ms} ms.")

        return {
            "execution_time_ms": elapsed_ms,
            "quantitative_context": enriched_catalog,
            "agent1_procurement": agent1_output,
            "agent2_pricing": agent2_output,
            "final_executive_payload": supervisor_output,
        }

    @staticmethod
    def _normalize_supervisor_output(
        supervisor_raw, catalog_by_sku: dict, agent1_output: dict, agent2_output: dict
    ) -> dict:
        """Guarantee exact JSON property names expected by C# WarehouseInventoryService."""
        if isinstance(supervisor_raw, list):
            supervisor_dict = {"final_decisions": supervisor_raw}
        elif isinstance(supervisor_raw, dict):
            supervisor_dict = dict(supervisor_raw)
        else:
            supervisor_dict = {}

        summary = (
            supervisor_dict.get("executive_summary")
            or supervisor_dict.get("summary")
            or supervisor_dict.get("overall_summary")
            or "Multi-Agent Supply Chain & Dynamic Pricing Audit completed."
        )

        raw_decisions = supervisor_dict.get("final_decisions")
        if not isinstance(raw_decisions, list):
            for k, v in supervisor_dict.items():
                if isinstance(v, list):
                    raw_decisions = v
                    break
            else:
                raw_decisions = []

        a1_by_sku = {
            p.get("sku"): p for p in agent1_output.get("procurement_plans", []) if isinstance(p, dict)
        }
        a2_by_sku = {
            p.get("sku"): p for p in agent2_output.get("pricing_plans", []) if isinstance(p, dict)
        }

        normalized_decisions = []
        for dec in raw_decisions:
            if not isinstance(dec, dict):
                continue
            sku = str(dec.get("sku", ""))
            cat = catalog_by_sku.get(sku, {})
            a1 = a1_by_sku.get(sku, {})
            a2 = a2_by_sku.get(sku, {})

            default_price = cat.get("pricing_math", {}).get("math_optimal_price", cat.get("listed_price", 0))
            raw_price = (
                dec.get("final_suggested_price")
                or dec.get("suggested_price")
                or dec.get("recommended_price")
                or a2.get("suggested_price")
                or default_price
            )

            default_qty = cat.get("inventory_math", {}).get("recommended_order_qty", 0)
            raw_qty = (
                dec.get("recommended_restock_qty")
                if dec.get("recommended_restock_qty") is not None
                else dec.get("restock_qty", dec.get("order_qty", a1.get("recommended_order_qty", default_qty)))
            )

            normalized_decisions.append({
                "sku": sku,
                "final_suggested_price": int(round(float(raw_price or 0))),
                "price_action": str(
                    dec.get("price_action")
                    or dec.get("pricing_action")
                    or dec.get("pricing_strategy")
                    or a2.get("price_action")
                    or "HOLD"
                ),
                "recommended_restock_qty": int(round(float(raw_qty or 0))),
                "recommended_supplier": str(
                    dec.get("recommended_supplier")
                    or dec.get("selected_supplier")
                    or a1.get("recommended_supplier")
                    or "SUP-SPC"
                ),
                "optimal_order_date": str(
                    dec.get("optimal_order_date")
                    or dec.get("order_timing")
                    or a1.get("optimal_order_date")
                    or "Immediately"
                ),
                "restock_status": str(
                    dec.get("restock_status")
                    or dec.get("inventory_status")
                    or cat.get("inventory_math", {}).get("status")
                    or "HEALTHY"
                ),
                "supervisor_justification": str(
                    dec.get("supervisor_justification")
                    or dec.get("justification")
                    or dec.get("conflict_resolution")
                    or dec.get("reasoning")
                    or "Verified by Chief Supervisor Agent."
                ),
            })

        return {
            "executive_summary": str(summary),
            "final_decisions": normalized_decisions,
        }