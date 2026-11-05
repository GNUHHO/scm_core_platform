import math


class StochasticInventoryEngine:
    """
    Stochastic inventory control engine for computing dynamic safety stock,
    reorder points (ROP), and order quantities under demand and lead-time uncertainty.
    """

    def __init__(self, service_level_z: float = 1.65):
        # Z = 1.65 corresponds to a 95% cycle service level under a normal distribution
        self.z = service_level_z

    def calculate_replenishment_metrics(
        self,
        current_stock: int,
        predicted_daily_demand: float,
        lead_time_days: int = 3,
        std_lead_time: float = 0.5,
        planning_horizon_days: int = 14,
    ) -> dict:
        """
        Compute safety stock, ROP, days of supply, and replenishment quantity.
        """
        avg_demand = max(0.1, float(predicted_daily_demand))
        std_demand = max(0.2, avg_demand * 0.25)

        # 1. Dynamic Safety Stock: SS = Z * sqrt(L * sigma_D^2 + D^2 * sigma_L^2)
        variance_term = (lead_time_days * (std_demand ** 2)) + ((avg_demand ** 2) * (std_lead_time ** 2))
        safety_stock = int(math.ceil(self.z * math.sqrt(variance_term)))

        # 2. Reorder Point: ROP = (D * L) + SS
        rop = int(math.ceil((avg_demand * lead_time_days) + safety_stock))

        # 3. Days of Supply (DoS)
        days_of_supply = round(current_stock / avg_demand, 1)

        # 4. Target order-up-to level for the planning horizon
        target_stock_level = int(math.ceil((avg_demand * planning_horizon_days) + safety_stock))

        if current_stock <= rop:
            recommended_qty = max(0, target_stock_level - current_stock)
            inventory_status = "URGENT_RESTOCK"
        elif days_of_supply > 30.0:
            recommended_qty = 0
            inventory_status = "OVERSTOCKED"
        else:
            recommended_qty = 0
            inventory_status = "HEALTHY"

        return {
            "predicted_daily_demand": round(avg_demand, 2),
            "dynamic_safety_stock": safety_stock,
            "reorder_point_rop": rop,
            "current_stock": current_stock,
            "days_of_supply": days_of_supply,
            "inventory_status": inventory_status,
            "recommended_restock_qty": recommended_qty,
            "target_stock_level": target_stock_level,
        }