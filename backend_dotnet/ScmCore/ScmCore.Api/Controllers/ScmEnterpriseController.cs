using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using ScmCore.Api.Data;
using ScmCore.Api.Services;

namespace ScmCore.Api.Controllers;

public record ScrapeSyncRequest(string ProviderMode = "LOCAL", bool ForceAi = false);
public record WhatIfRequest(
    string Sku = "CPU-AMD-7800X3D",
    int? CustomOnHandStock = null,
    long? CustomListedPrice = null,
    long? CustomCompetitorPrice = null,
    decimal ServiceLevelZ = 1.65m,
    decimal Elasticity = -1.8m);
public record ApproveRequest(string WarehouseId = "WH-HCM-01", string ManagerUsername = "admin.scm");
public record RejectRequest(string ManagerUsername = "admin.scm");
public record ReceiveGrnRequest(
    int AcceptedQty,
    long ActualInvoiceUnitCost,
    string SupplierInvoiceNo = "VAT-2026-001",
    string WarehouseKeeper = "keeper.hcm");

[ApiController]
[Route("api/erp")]
public class ScmEnterpriseController : ControllerBase
{
    private readonly ScmDbContext _db;
    private readonly WarehouseInventoryService _wmsService;

    public ScmEnterpriseController(ScmDbContext db, WarehouseInventoryService wmsService)
    {
        _db = db;
        _wmsService = wmsService;
    }

    /// <summary>
    /// 1. View live multi-state inventory, latest competitor price & PostgreSQL 18 VIRTUAL columns.
    /// </summary>
    [HttpGet("inventory")]
    public async Task<IActionResult> GetWarehouseInventory()
    {
        var latestCompPrices = await _db.LiveMlFeatures
            .GroupBy(f => f.Sku)
            .Select(g => g.OrderByDescending(x => x.RecordDate).First())
            .ToDictionaryAsync(k => k.Sku, v => v.CompetitorPrice);

        var rows = await (from p in _db.Products
                          join s in _db.InventoryStocks on p.Sku equals s.Sku
                          select new
                          {
                              p.Sku,
                              p.Name,
                              p.Category,
                              p.DefaultSupplierId,
                              s.WarehouseId,
                              s.DefaultBinCode,
                              s.OnHandQty,
                              s.ReservedQty,
                              s.AvailableQty,
                              s.IncomingQty,
                              s.NetInventoryPosition,
                              s.MinSafetyStock,
                              s.ReorderPointRop,
                              p.CostPrice,
                              p.ListedPrice,
                              p.GrossMarginPct,
                              p.LeadTimeDays,
                              s.UpdatedAt
                          }).ToListAsync();

        var enriched = rows.Select(r => new
        {
            r.Sku,
            r.Name,
            r.Category,
            r.DefaultSupplierId,
            r.WarehouseId,
            r.DefaultBinCode,
            r.OnHandQty,
            r.ReservedQty,
            r.AvailableQty,
            r.IncomingQty,
            r.NetInventoryPosition,
            r.MinSafetyStock,
            r.ReorderPointRop,
            r.CostPrice,
            r.ListedPrice,
            CompetitorPrice = latestCompPrices.GetValueOrDefault(r.Sku, r.ListedPrice),
            r.GrossMarginPct,
            r.LeadTimeDays,
            r.UpdatedAt
        });

        return Ok(enriched);
    }

    /// <summary>
    /// 2. Trigger PriceStalkerEngine + Agent 0 and sync live competitor prices into PostgreSQL 18.
    /// </summary>
    [HttpPost("sync-competitor-prices")]
    public async Task<IActionResult> SyncCompetitorPrices([FromBody] ScrapeSyncRequest req)
    {
        var result = await _wmsService.SyncCompetitorPricesAsync(req.ProviderMode, req.ForceAi);
        return Ok(result);
    }

    /// <summary>
    /// 3. Sub-50ms Quantitative What-If Simulator (LightGBM + Random Forest + Stochastic ROP + Scipy Solver).
    /// </summary>
    [HttpPost("simulate-what-if")]
    public async Task<IActionResult> SimulateWhatIf([FromBody] WhatIfRequest req)
    {
        var result = await _wmsService.RunWhatIfSimulationAsync(
            req.Sku,
            req.CustomOnHandStock,
            req.CustomListedPrice,
            req.CustomCompetitorPrice,
            req.ServiceLevelZ,
            req.Elasticity);
        return Ok(result);
    }

    /// <summary>
    /// 4. Trigger full 4-Agent Audit (gemini-3.5-flash-lite) and persist recommendations to PostgreSQL 18.
    /// </summary>
    [HttpPost("trigger-ai-audit")]
    public async Task<IActionResult> TriggerHybridAiAudit([FromQuery] string model = "gemini-3.5-flash-lite")
    {
        var result = await _wmsService.TriggerAndPersistAiAuditAsync(model);
        return Ok(result);
    }

    /// <summary>
    /// 5. List AI recommendations stored in PostgreSQL 18 (filterable by PENDING / APPROVED / REJECTED / ALL).
    /// </summary>
    [HttpGet("recommendations")]
    public async Task<IActionResult> GetRecommendations([FromQuery] string? status = "PENDING")
    {
        var query = _db.AiSkuRecommendations.AsQueryable();
        if (!string.IsNullOrWhiteSpace(status) && !status.Equals("ALL", StringComparison.OrdinalIgnoreCase))
            query = query.Where(r => r.ApprovalStatus == status.ToUpperInvariant());

        var list = await query.OrderByDescending(r => r.RecommendationId).Take(50).ToListAsync();
        return Ok(list);
    }

    /// <summary>
    /// 6. STEP 1 (Approve): Updates ListedPrice, generates Purchase Order (PO), and increments IncomingQty.
    /// </summary>
    [HttpPost("recommendations/{recommendationId:long}/approve")]
    public async Task<IActionResult> ApproveRecommendation(long recommendationId, [FromBody] ApproveRequest req)
    {
        var result = await _wmsService.ApproveAiRecommendationAsync(
            recommendationId, req.WarehouseId, req.ManagerUsername);
        return Ok(result);
    }

    /// <summary>
    /// 7. Reject a PENDING AI recommendation.
    /// </summary>
    [HttpPost("recommendations/{recommendationId:long}/reject")]
    public async Task<IActionResult> RejectRecommendation(long recommendationId, [FromBody] RejectRequest req)
    {
        var result = await _wmsService.RejectAiRecommendationAsync(recommendationId, req.ManagerUsername);
        return Ok(result);
    }

    /// <summary>
    /// 8. List all Purchase Orders (POs) and their line items for the Warehouse GRN portal.
    /// </summary>
    [HttpGet("purchase-orders")]
    public async Task<IActionResult> GetPurchaseOrders()
    {
        var orders = await _db.PurchaseOrders
            .Include(p => p.Items)
            .OrderByDescending(p => p.PoId)
            .ToListAsync();
        return Ok(orders);
    }

    /// <summary>
    /// 9. STEP 2 (Warehouse GRN Receipt): Converts IncomingQty -> OnHandQty, updates Moving Average Cost (MAC), and logs StockMovement.
    /// </summary>
    [HttpPost("purchase-orders/{poId:long}/receive-grn")]
    public async Task<IActionResult> ReceiveGoodsGrn(long poId, [FromBody] ReceiveGrnRequest req)
    {
        var result = await _wmsService.ReceiveGoodsFromPoAsync(
            poId, req.AcceptedQty, req.ActualInvoiceUnitCost, req.SupplierInvoiceNo, req.WarehouseKeeper);
        return Ok(result);
    }

    /// <summary>
    /// 10. View Audit Ledgers (Stock Movements, FIFO Batches, Price Change Ledger, and Competitor Logs).
    /// </summary>
    [HttpGet("ledgers")]
    public async Task<IActionResult> GetAuditLedgers([FromQuery] string? sku = null)
    {
        var stockMovements = _db.StockMovements.AsQueryable();
        var priceChanges = _db.PriceChangeLedgers.AsQueryable();
        var batches = _db.InventoryBatches.AsQueryable();
        var compLogs = _db.CompetitorPriceLogs.AsQueryable();

        if (!string.IsNullOrWhiteSpace(sku))
        {
            stockMovements = stockMovements.Where(x => x.Sku == sku);
            priceChanges = priceChanges.Where(x => x.Sku == sku);
            batches = batches.Where(x => x.Sku == sku);
            compLogs = compLogs.Where(x => x.Sku == sku);
        }

        return Ok(new
        {
            StockMovements = await stockMovements.OrderByDescending(x => x.CreatedAt).Take(30).ToListAsync(),
            InventoryBatches = await batches.OrderByDescending(x => x.BatchId).Take(30).ToListAsync(),
            PriceChangeLedgers = await priceChanges.OrderByDescending(x => x.ChangedAt).Take(30).ToListAsync(),
            CompetitorPriceLogs = await compLogs.OrderByDescending(x => x.ScrapedAt).Take(30).ToListAsync()
        });
    }
}