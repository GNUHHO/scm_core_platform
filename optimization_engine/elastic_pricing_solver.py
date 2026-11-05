from scipy.optimize import minimize_scalar


class ElasticPricingSolver:
    """
    Microeconomic price optimization solver using bounded scalar minimization.
    Maximizes expected daily gross profit minus overstock capital holding penalties.
    """

    def __init__(
        self,
        elasticity: float = -1.8,
        min_margin_floor: float = 0.05,
        daily_holding_rate: float = 0.002,
    ):
        self.elasticity = elasticity
        self.min_margin_floor = min_margin_floor
        self.daily_holding_rate = daily_holding_rate

    def solve_optimal_price(
        self,
        cost_price: int,
        current_price: int,
        competitor_price: int,
        current_stock: int,
        base_daily_demand: float,
        competitor_trend_label: str = "STABLE",
    ) -> dict:
        """
        Solve for price P that maximizes:
        Objective(P) = (P - Cost) * D(P) - HoldingPenalty(P)
        where D(P) = base_demand * (P / current_price)^elasticity.
        """
        base_demand = max(0.1, float(base_daily_demand))

        # 1. Hard price floor: Never sell below Cost * (1 + min_margin_floor)
        price_floor = cost_price * (1.0 + self.min_margin_floor)

        # 2. Dynamic price ceiling conditioned on competitor trend prediction
        if "MARKDOWN" in competitor_trend_label:
            price_ceiling = competitor_price * 0.99 if competitor_price > 0 else current_price
        elif "MARKUP" in competitor_trend_label:
            price_ceiling = competitor_price * 1.05 if competitor_price > 0 else current_price * 1.15
        else:
            price_ceiling = competitor_price * 1.02 if competitor_price > 0 else current_price * 1.08

        # Ensure valid optimization bounds
        price_ceiling = max(price_ceiling, price_floor + 50000)

        # 3. Objective function with endogenous price-dependent Days of Supply
        def negative_net_profit(p: float) -> float:
            expected_demand = base_demand * ((p / current_price) ** self.elasticity)
            unit_margin = p - cost_price
            gross_profit = unit_margin * expected_demand

            # Effective days of supply at price p
            effective_dos = current_stock / max(0.05, expected_demand)
            excess_days = max(0.0, effective_dos - 30.0)

            # Capital holding penalty increases non-linearly with excess days of supply
            holding_cost_penalty = excess_days * cost_price * self.daily_holding_rate
            net_profit = gross_profit - holding_cost_penalty
            return -net_profit

        # 4. Bounded Golden-Section / Brent optimization
        res = minimize_scalar(
            negative_net_profit,
            bounds=(price_floor, price_ceiling),
            method="bounded",
        )

        # Round to nearest 1,000 VND
        optimal_price = int(round(res.x, -3))
        final_margin_pct = round(((optimal_price - cost_price) / optimal_price) * 100, 2)

        # 5. Classify strategic price action (threshold of 5,000 VND for noise filtering)
        if optimal_price < current_price - 5000:
            price_action = "MARKDOWN"
        elif optimal_price > current_price + 5000:
            price_action = "MARKUP"
        else:
            optimal_price = current_price
            price_action = "HOLD"

        return {
            "math_optimal_price": optimal_price,
            "current_price": current_price,
            "cost_price": cost_price,
            "price_floor": int(price_floor),
            "price_ceiling": int(price_ceiling),
            "optimal_margin_pct": final_margin_pct,
            "price_action": price_action,
            "solver_converged": bool(res.success),
        }