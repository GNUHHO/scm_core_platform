using Microsoft.EntityFrameworkCore;
using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace ScmCore.Api.Models;

[Table("warehouses")]
public class Warehouse
{
    [Key, Column("warehouse_id")] public string WarehouseId { get; set; } = "WH-HCM-01";
    [Column("name")] public string Name { get; set; } = string.Empty;
    [Column("address")] public string? Address { get; set; }
    [Column("is_active")] public bool IsActive { get; set; } = true;
}

[Table("suppliers")]
public class Supplier
{
    [Key, Column("supplier_id")] public string SupplierId { get; set; } = string.Empty;
    [Column("name")] public string Name { get; set; } = string.Empty;
    [Column("default_lead_time_days")] public int DefaultLeadTimeDays { get; set; }
    [Column("reliability_score")] public decimal ReliabilityScore { get; set; }
    [Column("sla_policy")] public string SlaPolicy { get; set; } = string.Empty;
    [Column("is_active")] public bool IsActive { get; set; } = true;
}

[Table("products")]
public class Product
{
    [Key, Column("sku")] public string Sku { get; set; } = string.Empty;
    [Column("name")] public string Name { get; set; } = string.Empty;
    [Column("category")] public string Category { get; set; } = string.Empty;
    [Column("default_supplier_id")] public string? DefaultSupplierId { get; set; }
    [Column("cost_price")] public long CostPrice { get; set; }
    [Column("listed_price")] public long ListedPrice { get; set; }
    [Column("lead_time_days")] public int LeadTimeDays { get; set; } = 3;
    [Column("service_level_z")] public decimal ServiceLevelZ { get; set; } = 1.65m;
    [Column("price_elasticity")] public decimal PriceElasticity { get; set; } = -1.80m;

    // PostgreSQL 18 VIRTUAL Generated Column (Read-only from DB)
    [Column("gross_margin_pct")]
    [DatabaseGenerated(DatabaseGeneratedOption.Computed)]
    public decimal GrossMarginPct { get; private set; }

    [Column("updated_at")] public DateTime UpdatedAt { get; set; } = DateTime.UtcNow;
}

[Table("inventory_stocks")]
public class InventoryStock
{
    [Key, Column("stock_id")] public long StockId { get; set; }
    [Column("warehouse_id")] public string WarehouseId { get; set; } = "WH-HCM-01";
    [Column("sku")] public string Sku { get; set; } = string.Empty;
    [Column("default_bin_code")] public string DefaultBinCode { get; set; } = "A-01-01";
    [Column("on_hand_qty")] public int OnHandQty { get; set; }
    [Column("reserved_qty")] public int ReservedQty { get; set; }
    [Column("incoming_qty")] public int IncomingQty { get; set; }
    [Column("defective_qty")] public int DefectiveQty { get; set; }

    // PostgreSQL 18 VIRTUAL Generated Columns (Read-only from DB)
    [Column("available_qty")]
    [DatabaseGenerated(DatabaseGeneratedOption.Computed)]
    public int AvailableQty { get; private set; }

    [Column("net_inventory_position")]
    [DatabaseGenerated(DatabaseGeneratedOption.Computed)]
    public int NetInventoryPosition { get; private set; }

    [Column("min_safety_stock")] public int MinSafetyStock { get; set; }
    [Column("reorder_point_rop")] public int ReorderPointRop { get; set; }

    // PostgreSQL system column xmin for Optimistic Concurrency Control
    [Timestamp, Column("xmin", TypeName = "xid")]
    public uint RowVersion { get; set; }

    [Column("updated_at")] public DateTime UpdatedAt { get; set; } = DateTime.UtcNow;
}

[Table("agent_audit_runs")]
public class AgentAuditRun
{
    [Key, Column("run_id")] public long RunId { get; set; }
    [Column("trace_uuid")] public Guid TraceUuid { get; set; } = Guid.CreateVersion7();
    [Column("trigger_type")] public string TriggerType { get; set; } = "DOTNET_API";
    [Column("llm_model_used")] public string LlmModelUsed { get; set; } = "gemini-2.5-flash";
    [Column("skus_processed")] public int SkusProcessed { get; set; }
    [Column("execution_time_ms")] public int ExecutionTimeMs { get; set; }
    [Column("executive_summary")] public string? ExecutiveSummary { get; set; }
    [Column("executed_at")] public DateTime ExecutedAt { get; set; } = DateTime.UtcNow;
}

[Table("ai_sku_recommendations")]
public class AiSkuRecommendation
{
    [Key, Column("recommendation_id")] public long RecommendationId { get; set; }
    [Column("run_id")] public long RunId { get; set; }
    [Column("sku")] public string Sku { get; set; } = string.Empty;
    [Column("ml_predicted_demand")] public decimal MlPredictedDemand { get; set; }
    [Column("rf_competitor_trend")] public string RfCompetitorTrend { get; set; } = "STABLE";
    [Column("rf_trend_confidence")] public decimal RfTrendConfidence { get; set; }
    [Column("math_reorder_point_rop")] public int MathReorderPointRop { get; set; }
    [Column("math_safety_stock")] public int MathSafetyStock { get; set; }
    [Column("math_optimal_price")] public long MathOptimalPrice { get; set; }
    [Column("agent1_procurement_trace", TypeName = "jsonb")] public string? Agent1ProcurementTrace { get; set; }
    [Column("agent2_pricing_trace", TypeName = "jsonb")] public string? Agent2PricingTrace { get; set; }
    [Column("final_suggested_price")] public long FinalSuggestedPrice { get; set; }
    [Column("price_action")] public string PriceAction { get; set; } = "HOLD";
    [Column("recommended_restock_qty")] public int RecommendedRestockQty { get; set; }
    [Column("recommended_supplier_id")] public string? RecommendedSupplierId { get; set; }
    [Column("optimal_order_date")] public string? OptimalOrderDate { get; set; }
    [Column("restock_status")] public string RestockStatus { get; set; } = "HEALTHY";
    [Column("supervisor_justification")] public string SupervisorJustification { get; set; } = string.Empty;
    [Column("approval_status")] public string ApprovalStatus { get; set; } = "PENDING";
    [Column("reviewed_by")] public string? ReviewedBy { get; set; }
    [Column("reviewed_at")] public DateTime? ReviewedAt { get; set; }
    [Column("created_at")] public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
}

[Table("purchase_orders")]
public class PurchaseOrder
{
    [Key, Column("po_id")] public long PoId { get; set; }
    [Column("po_uuid")] public Guid PoUuid { get; set; } = Guid.CreateVersion7();
    [Column("po_number")] public string PoNumber { get; set; } = string.Empty;
    [Column("ai_recommendation_id")] public long? AiRecommendationId { get; set; }
    [Column("supplier_id")] public string SupplierId { get; set; } = string.Empty;
    [Column("warehouse_id")] public string WarehouseId { get; set; } = "WH-HCM-01";
    [Column("status")] public string Status { get; set; } = "APPROVED_IN_TRANSIT";
    [Column("total_amount")] public long TotalAmount { get; set; }
    [Column("expected_delivery_date")] public DateOnly? ExpectedDeliveryDate { get; set; }
    [Column("approved_by")] public string? ApprovedBy { get; set; }
    [Column("created_at")] public DateTime CreatedAt { get; set; } = DateTime.UtcNow;

    public List<PurchaseOrderItem> Items { get; set; } = new();
}

[Table("purchase_order_items")]
public class PurchaseOrderItem
{
    [Key, Column("po_item_id")] public long PoItemId { get; set; }
    [Column("po_id")] public long PoId { get; set; }
    [Column("sku")] public string Sku { get; set; } = string.Empty;
    [Column("ordered_qty")] public int OrderedQty { get; set; }
    [Column("received_qty")] public int ReceivedQty { get; set; }
    [Column("agreed_unit_cost")] public long AgreedUnitCost { get; set; }

    // PostgreSQL 18 VIRTUAL Generated Column
    [Column("line_total")]
    [DatabaseGenerated(DatabaseGeneratedOption.Computed)]
    public long LineTotal { get; private set; }
}

[Table("goods_receipts")]
public class GoodsReceipt
{
    [Key, Column("grn_id")] public long GrnId { get; set; }
    [Column("grn_uuid")] public Guid GrnUuid { get; set; } = Guid.CreateVersion7();
    [Column("grn_number")] public string GrnNumber { get; set; } = string.Empty;
    [Column("po_id")] public long PoId { get; set; }
    [Column("warehouse_id")] public string WarehouseId { get; set; } = "WH-HCM-01";
    [Column("supplier_invoice_no")] public string? SupplierInvoiceNo { get; set; }
    [Column("received_by")] public string? ReceivedBy { get; set; }
    [Column("received_at")] public DateTime ReceivedAt { get; set; } = DateTime.UtcNow;
}

[Table("inventory_batches")]
public class InventoryBatch
{
    [Key, Column("batch_id")] public long BatchId { get; set; }
    [Column("batch_number")] public string BatchNumber { get; set; } = string.Empty;
    [Column("sku")] public string Sku { get; set; } = string.Empty;
    [Column("warehouse_id")] public string WarehouseId { get; set; } = "WH-HCM-01";
    [Column("initial_qty")] public int InitialQty { get; set; }
    [Column("remaining_qty")] public int RemainingQty { get; set; }
    [Column("unit_import_cost")] public long UnitImportCost { get; set; }
    [Column("received_date")] public DateOnly ReceivedDate { get; set; }
    [Column("supplier_warranty_expiry")] public DateOnly SupplierWarrantyExpiry { get; set; }
}

[Table("stock_movements")]
public class StockMovement
{
    [Key, Column("movement_id")] public Guid MovementId { get; set; } = Guid.CreateVersion7();
    [Column("warehouse_id")] public string WarehouseId { get; set; } = "WH-HCM-01";
    [Column("sku")] public string Sku { get; set; } = string.Empty;
    [Column("batch_id")] public long? BatchId { get; set; }
    [Column("movement_type")] public string MovementType { get; set; } = string.Empty;
    [Column("qty_change")] public int QtyChange { get; set; }
    [Column("on_hand_before")] public int OnHandBefore { get; set; }
    [Column("on_hand_after")] public int OnHandAfter { get; set; }
    [Column("moving_avg_cost_after")] public long MovingAvgCostAfter { get; set; }
    [Column("reference_code")] public string? ReferenceCode { get; set; }
    [Column("created_by")] public string? CreatedBy { get; set; }
    [Column("created_at")] public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
}

[Table("price_change_ledger")]
public class PriceChangeLedger
{
    [Key, Column("price_log_id")] public Guid PriceLogId { get; set; } = Guid.CreateVersion7();
    [Column("sku")] public string Sku { get; set; } = string.Empty;
    [Column("recommendation_id")] public long? RecommendationId { get; set; }
    [Column("old_price")] public long OldPrice { get; set; }
    [Column("new_price")] public long NewPrice { get; set; }
    [Column("price_action")] public string PriceAction { get; set; } = string.Empty;
    [Column("approved_by")] public string? ApprovedBy { get; set; }
    [Column("changed_at")] public DateTime ChangedAt { get; set; } = DateTime.UtcNow;
}

[Keyless]

[Table("competitor_price_logs")]
public class CompetitorPriceLog
{
    [Key, Column("log_id")] public Guid LogId { get; set; } = Guid.CreateVersion7();
    [Column("sku")] public string Sku { get; set; } = string.Empty;
    [Column("competitor_name")] public string CompetitorName { get; set; } = string.Empty;
    [Column("matched_title")] public string? MatchedTitle { get; set; }
    [Column("price")] public long Price { get; set; }
    [Column("stock_status")] public string StockStatus { get; set; } = "In Stock";
    [Column("confidence_score")] public decimal ConfidenceScore { get; set; } = 1.0m;
    [Column("extraction_method")] public string? ExtractionMethod { get; set; }
    [Column("scraped_at")] public DateTime ScrapedAt { get; set; } = DateTime.UtcNow;
}

[Table("daily_market_history")]
public class DailyMarketHistory
{
    [Key, Column("history_id")] public long HistoryId { get; set; }
    [Column("sku")] public string Sku { get; set; } = string.Empty;
    [Column("record_date")] public DateOnly RecordDate { get; set; }
    [Column("sales_qty")] public int SalesQty { get; set; }
    [Column("listed_price")] public long ListedPrice { get; set; }
    [Column("competitor_min_price")] public long CompetitorMinPrice { get; set; }
    [Column("cost_price")] public long CostPrice { get; set; }
    [Column("is_promo")] public bool IsPromo { get; set; }
}
public class LiveMlFeatureView
{
    [Column("sku")] public string Sku { get; set; } = string.Empty;
    [Column("record_date")] public DateOnly RecordDate { get; set; }
    [Column("day_of_week")] public int DayOfWeek { get; set; }
    [Column("day_of_month")] public int DayOfMonth { get; set; }
    [Column("month")] public int Month { get; set; }
    [Column("is_weekend")] public int IsWeekend { get; set; }
    [Column("is_promo")] public int IsPromo { get; set; }
    [Column("listed_price")] public long ListedPrice { get; set; }
    [Column("competitor_price")] public long CompetitorPrice { get; set; }
    [Column("cost_price")] public long CostPrice { get; set; }
    [Column("price_diff")] public long PriceDiff { get; set; }
    [Column("price_ratio")] public decimal PriceRatio { get; set; }
    [Column("margin_pct")] public decimal MarginPct { get; set; }
    [Column("sales_lag_1")] public decimal SalesLag1 { get; set; }
    [Column("sales_lag_3")] public decimal SalesLag3 { get; set; }
    [Column("sales_lag_7")] public decimal SalesLag7 { get; set; }
    [Column("sales_lag_14")] public decimal SalesLag14 { get; set; }
    [Column("comp_price_lag_1")] public decimal CompPriceLag1 { get; set; }
    [Column("comp_price_lag_3")] public decimal CompPriceLag3 { get; set; }
    [Column("comp_price_lag_7")] public decimal CompPriceLag7 { get; set; }
    [Column("comp_price_lag_14")] public decimal CompPriceLag14 { get; set; }
    [Column("sales_roll_mean_7")] public decimal SalesRollMean7 { get; set; }
    [Column("sales_roll_std_7")] public decimal SalesRollStd7 { get; set; }
    [Column("sales_roll_mean_14")] public decimal SalesRollMean14 { get; set; }
}