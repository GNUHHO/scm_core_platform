using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using ScmCore.Api.Data;
using ScmCore.Api.Models;

namespace ScmCore.Api.Services;

public class WarehouseInventoryService
{
    private readonly ScmDbContext _db;
    private readonly IHttpClientFactory _httpFactory;

    public WarehouseInventoryService(ScmDbContext db, IHttpClientFactory httpFactory)
    {
        _db = db;
        _httpFactory = httpFactory;
    }

    /// <summary>
    /// Pulls live PostgreSQL 18 stock & 22 window lag features, calls Python FastAPI Multi-Agent endpoint,
    /// and persists all Agent 1, Agent 2, and Supervisor Agent 3 recommendations into PostgreSQL 18.
    /// </summary>
    public async Task<object> TriggerAndPersistAiAuditAsync(string modelName = "gemini-3.5-flash-lite")
    {
        var products = await _db.Products.ToListAsync();
        var stocks = await _db.InventoryStocks.ToListAsync();
        var suppliers = await _db.Suppliers.ToListAsync();

        var latestFeatures = await _db.LiveMlFeatures
            .GroupBy(f => f.Sku)
            .Select(g => g.OrderByDescending(x => x.RecordDate).First())
            .ToListAsync();

        var catalogPayload = new List<object>();

        foreach (var p in products)
        {
            var stk = stocks.FirstOrDefault(s => s.Sku == p.Sku);
            var feat = latestFeatures.FirstOrDefault(f => f.Sku == p.Sku);
            if (stk == null || feat == null) continue;

            catalogPayload.Add(new
            {
                sku = p.Sku,
                name = p.Name,
                stock = stk.AvailableQty,
                incoming_stock = stk.IncomingQty,
                cost = p.CostPrice,
                listed_price = p.ListedPrice,
                competitor_price = feat.CompetitorPrice,
                lead_time_days = p.LeadTimeDays,
                features_ml = new Dictionary<string, object>
                {
                    ["day_of_week"] = feat.DayOfWeek,
                    ["day_of_month"] = feat.DayOfMonth,
                    ["month"] = feat.Month,
                    ["is_weekend"] = feat.IsWeekend,
                    ["is_promo"] = feat.IsPromo,
                    ["listed_price"] = feat.ListedPrice,
                    ["competitor_price"] = feat.CompetitorPrice,
                    ["cost_price"] = feat.CostPrice,
                    ["price_diff"] = feat.PriceDiff,
                    ["price_ratio"] = feat.PriceRatio,
                    ["margin_pct"] = feat.MarginPct,
                    ["sales_lag_1"] = feat.SalesLag1,
                    ["sales_lag_3"] = feat.SalesLag3,
                    ["sales_lag_7"] = feat.SalesLag7,
                    ["sales_lag_14"] = feat.SalesLag14,
                    ["comp_price_lag_1"] = feat.CompPriceLag1,
                    ["comp_price_lag_3"] = feat.CompPriceLag3,
                    ["comp_price_lag_7"] = feat.CompPriceLag7,
                    ["comp_price_lag_14"] = feat.CompPriceLag14,
                    ["sales_roll_mean_7"] = feat.SalesRollMean7,
                    ["sales_roll_std_7"] = feat.SalesRollStd7,
                    ["sales_roll_mean_14"] = feat.SalesRollMean14
                }
            });
        }

        var suppliersPayload = suppliers.Select(s => new
        {
            supplier_id = s.SupplierId,
            name = s.Name,
            lead_time_days = s.DefaultLeadTimeDays,
            policy = s.SlaPolicy
        }).ToList();

        var client = _httpFactory.CreateClient("PythonAi");
        var response = await client.PostAsJsonAsync("/api/v1/audit", new
        {
            model = modelName,
            service_level_z = 1.65,
            elasticity = -1.8,
            catalog_override = catalogPayload,
            suppliers_override = suppliersPayload
        });

        var rawJson = await response.Content.ReadAsStringAsync();
        if (!response.IsSuccessStatusCode)
            throw new InvalidOperationException($"Python AI Service error: {rawJson}");

        // Parse Python FastAPI response and persist into PostgreSQL 18
        using var doc = JsonDocument.Parse(rawJson);
        var root = doc.RootElement;

        int execMs = root.TryGetProperty("execution_time_ms", out var msEl) ? msEl.GetInt32() : 0;
        var execPayload = root.GetProperty("final_executive_payload");
        string summary = execPayload.TryGetProperty("executive_summary", out var sumEl)
            ? sumEl.GetString() ?? ""
            : "";

        var decisions = execPayload.GetProperty("final_decisions");
        var quantList = root.GetProperty("quantitative_context");
        var a1Plans = root.GetProperty("agent1_procurement").GetProperty("procurement_plans");
        var a2Plans = root.GetProperty("agent2_pricing").GetProperty("pricing_plans");

        await using var transaction = await _db.Database.BeginTransactionAsync();

        // Supersede previous PENDING recommendations before saving new audit run
        await _db.AiSkuRecommendations
            .Where(r => r.ApprovalStatus == "PENDING")
            .ExecuteUpdateAsync(s => s.SetProperty(r => r.ApprovalStatus, "SUPERSEDED"));

        var auditRun = new AgentAuditRun
        {
            TriggerType = "DOTNET_ERP_API",
            LlmModelUsed = modelName,
            SkusProcessed = decisions.GetArrayLength(),
            ExecutionTimeMs = execMs,
            ExecutiveSummary = summary,
            ExecutedAt = DateTime.UtcNow
        };
        _db.AgentAuditRuns.Add(auditRun);
        await _db.SaveChangesAsync();

        var savedRecs = new List<AiSkuRecommendation>();

        foreach (var d in decisions.EnumerateArray())
        {
            string sku = d.GetProperty("sku").GetString() ?? "";

            // Match quantitative metrics for this SKU
            JsonElement? qMatch = null;
            foreach (var q in quantList.EnumerateArray())
            {
                if (q.GetProperty("sku").GetString() == sku) { qMatch = q; break; }
            }

            // Match raw Agent 1 & Agent 2 JSON traces
            string a1Json = "{}";
            foreach (var p1 in a1Plans.EnumerateArray())
            {
                if (p1.GetProperty("sku").GetString() == sku) { a1Json = p1.GetRawText(); break; }
            }

            string a2Json = "{}";
            foreach (var p2 in a2Plans.EnumerateArray())
            {
                if (p2.GetProperty("sku").GetString() == sku) { a2Json = p2.GetRawText(); break; }
            }

            decimal predDemand = qMatch?.GetProperty("ml_predictions").GetProperty("predicted_daily_demand").GetDecimal() ?? 1.0m;
            string rfTrend = qMatch?.GetProperty("ml_predictions").GetProperty("competitor_7d_trend").GetString() ?? "STABLE";
            decimal rfConf = qMatch?.GetProperty("ml_predictions").GetProperty("trend_confidence").GetDecimal() ?? 0.8m;
            int rop = qMatch?.GetProperty("inventory_math").GetProperty("reorder_point_rop").GetInt32() ?? 10;
            int ss = qMatch?.GetProperty("inventory_math").GetProperty("dynamic_safety_stock").GetInt32() ?? 4;
            long optPrice = qMatch?.GetProperty("pricing_math").GetProperty("math_optimal_price").GetInt64() ?? 0;

            string rawSupplier = d.TryGetProperty("recommended_supplier", out var supEl) ? supEl.GetString() ?? "" : "";
            string? resolvedSupplierId = ResolveSupplierId(rawSupplier, suppliers);

            var rec = new AiSkuRecommendation
            {
                RunId = auditRun.RunId,
                Sku = sku,
                MlPredictedDemand = predDemand,
                RfCompetitorTrend = rfTrend,
                RfTrendConfidence = rfConf,
                MathReorderPointRop = rop,
                MathSafetyStock = ss,
                MathOptimalPrice = optPrice,
                Agent1ProcurementTrace = a1Json,
                Agent2PricingTrace = a2Json,
                FinalSuggestedPrice = d.GetProperty("final_suggested_price").GetInt64(),
                PriceAction = d.GetProperty("price_action").GetString() ?? "HOLD",
                RecommendedRestockQty = d.GetProperty("recommended_restock_qty").GetInt32(),
                RecommendedSupplierId = resolvedSupplierId,
                OptimalOrderDate = d.TryGetProperty("optimal_order_date", out var dtEl) ? dtEl.GetString() : "Immediately",
                RestockStatus = d.GetProperty("restock_status").GetString() ?? "HEALTHY",
                SupervisorJustification = d.GetProperty("supervisor_justification").GetString() ?? "",
                ApprovalStatus = "PENDING",
                CreatedAt = DateTime.UtcNow
            };

            _db.AiSkuRecommendations.Add(rec);
            savedRecs.Add(rec);
        }

        await _db.SaveChangesAsync();
        await transaction.CommitAsync();

        return new
        {
            auditRun.RunId,
            auditRun.TraceUuid,
            auditRun.ExecutionTimeMs,
            auditRun.ExecutiveSummary,
            Recommendations = savedRecs.Select(r => new
            {
                r.RecommendationId,
                r.Sku,
                r.RestockStatus,
                r.RecommendedRestockQty,
                r.RecommendedSupplierId,
                r.FinalSuggestedPrice,
                r.PriceAction,
                r.SupervisorJustification,
                r.ApprovalStatus
            })
        };
    }

    /// <summary>
    /// STEP 1 (Approve): Updates ListedPrice + PriceChangeLedger, creates PurchaseOrder,
    /// and increments IncomingQty so PostgreSQL 18 VIRTUAL net_inventory_position increases immediately.
    /// </summary>
    public async Task<object> ApproveAiRecommendationAsync(
        long recommendationId,
        string warehouseId,
        string managerUsername)
    {
        await using var transaction = await _db.Database.BeginTransactionAsync();
        var rec = await _db.AiSkuRecommendations
            .FirstOrDefaultAsync(r => r.RecommendationId == recommendationId);

        if (rec == null || rec.ApprovalStatus != "PENDING")
            throw new InvalidOperationException("Recommendation not found or not in PENDING status.");

        var product = await _db.Products.FirstAsync(p => p.Sku == rec.Sku);
        var stock = await _db.InventoryStocks
            .FirstAsync(s => s.Sku == rec.Sku && s.WarehouseId == warehouseId);

        rec.ApprovalStatus = "APPROVED";
        rec.ReviewedBy = managerUsername;
        rec.ReviewedAt = DateTime.UtcNow;

        long oldPrice = product.ListedPrice;
        if (rec.FinalSuggestedPrice > 0 && rec.FinalSuggestedPrice != product.ListedPrice)
        {
            _db.PriceChangeLedgers.Add(new PriceChangeLedger
            {
                Sku = product.Sku,
                RecommendationId = rec.RecommendationId,
                OldPrice = oldPrice,
                NewPrice = rec.FinalSuggestedPrice,
                PriceAction = rec.PriceAction,
                ApprovedBy = managerUsername,
                ChangedAt = DateTime.UtcNow
            });

            product.ListedPrice = rec.FinalSuggestedPrice;
            product.UpdatedAt = DateTime.UtcNow;
        }

        PurchaseOrder? createdPo = null;

        if (rec.RecommendedRestockQty > 0)
        {
            string poNumber = $"PO-{DateTime.UtcNow:yyyyMMdd}-{Random.Shared.Next(1000, 9999)}";
            string supplierId = rec.RecommendedSupplierId ?? product.DefaultSupplierId ?? "SUP-SPC";

            createdPo = new PurchaseOrder
            {
                PoNumber = poNumber,
                AiRecommendationId = rec.RecommendationId,
                SupplierId = supplierId,
                WarehouseId = warehouseId,
                Status = "APPROVED_IN_TRANSIT",
                TotalAmount = rec.RecommendedRestockQty * product.CostPrice,
                ExpectedDeliveryDate = DateOnly.FromDateTime(DateTime.UtcNow.AddDays(product.LeadTimeDays)),
                ApprovedBy = managerUsername,
                CreatedAt = DateTime.UtcNow,
                Items = new List<PurchaseOrderItem>
                {
                    new PurchaseOrderItem
                    {
                        Sku = product.Sku,
                        OrderedQty = rec.RecommendedRestockQty,
                        ReceivedQty = 0,
                        AgreedUnitCost = product.CostPrice
                    }
                }
            };

            _db.PurchaseOrders.Add(createdPo);

            // Increment IncomingQty (goods in transit)
            stock.IncomingQty += rec.RecommendedRestockQty;
            stock.ReorderPointRop = rec.MathReorderPointRop;
            stock.MinSafetyStock = rec.MathSafetyStock;
            stock.UpdatedAt = DateTime.UtcNow;
        }

        await _db.SaveChangesAsync();
        await transaction.CommitAsync();

        // Reload stock to read updated PostgreSQL 18 VIRTUAL columns
        await _db.Entry(stock).ReloadAsync();

        return new
        {
            Message = "AI Recommendation Approved Successfully",
            rec.RecommendationId,
            rec.Sku,
            OldListedPrice = oldPrice,
            NewListedPrice = product.ListedPrice,
            CreatedPoId = createdPo?.PoId,
            CreatedPoNumber = createdPo?.PoNumber ?? "NONE (Price Change Only)",
            UpdatedStockState = new
            {
                stock.OnHandQty,
                stock.IncomingQty,
                stock.AvailableQty,
                stock.NetInventoryPosition,
                stock.ReorderPointRop
            }
        };
    }

    /// <summary>
    /// STEP 2 (Goods Receipt GRN): Converts IncomingQty -> OnHandQty, recalculates Weighted Moving Average Cost (MAC),
    /// creates a 36-month warranty FIFO Batch, and records an immutable StockMovement ledger entry.
    /// </summary>
    public async Task<object> ReceiveGoodsFromPoAsync(
        long poId,
        int acceptedQty,
        long actualInvoiceUnitCost,
        string supplierInvoiceNo,
        string warehouseKeeper)
    {
        await using var transaction = await _db.Database.BeginTransactionAsync();

        var po = await _db.PurchaseOrders
            .Include(p => p.Items)
            .FirstOrDefaultAsync(p => p.PoId == poId);

        if (po == null || po.Status == "COMPLETED")
            throw new InvalidOperationException("Purchase Order not found or already completed.");

        var poItem = po.Items.First();
        var product = await _db.Products.FirstAsync(p => p.Sku == poItem.Sku);
        var stock = await _db.InventoryStocks
            .FirstAsync(s => s.Sku == poItem.Sku && s.WarehouseId == po.WarehouseId);

        int oldOnHand = stock.OnHandQty;
        long oldCost = product.CostPrice;

        // Weighted Moving Average Cost (MAC) calculation
        int newOnHand = oldOnHand + acceptedQty;
        long newMovingAvgCost = newOnHand > 0
            ? ((oldOnHand * oldCost) + (acceptedQty * actualInvoiceUnitCost)) / newOnHand
            : actualInvoiceUnitCost;

        product.CostPrice = newMovingAvgCost;
        product.UpdatedAt = DateTime.UtcNow;

        stock.IncomingQty = Math.Max(0, stock.IncomingQty - acceptedQty);
        stock.OnHandQty = newOnHand;
        stock.UpdatedAt = DateTime.UtcNow;

        poItem.ReceivedQty += acceptedQty;
        po.Status = poItem.ReceivedQty >= poItem.OrderedQty ? "COMPLETED" : "PARTIAL_RECEIVED";

        string grnNumber = $"GRN-{DateTime.UtcNow:yyyyMMdd}-{Random.Shared.Next(1000, 9999)}";
        var grn = new GoodsReceipt
        {
            GrnNumber = grnNumber,
            PoId = po.PoId,
            WarehouseId = po.WarehouseId,
            SupplierInvoiceNo = supplierInvoiceNo,
            ReceivedBy = warehouseKeeper,
            ReceivedAt = DateTime.UtcNow
        };
        _db.GoodsReceipts.Add(grn);

        var batch = new InventoryBatch
        {
            BatchNumber = $"LOT-{DateTime.UtcNow:yyyyMMdd}-{po.SupplierId}-{Random.Shared.Next(100, 999)}",
            Sku = product.Sku,
            WarehouseId = po.WarehouseId,
            InitialQty = acceptedQty,
            RemainingQty = acceptedQty,
            UnitImportCost = actualInvoiceUnitCost,
            ReceivedDate = DateOnly.FromDateTime(DateTime.UtcNow),
            SupplierWarrantyExpiry = DateOnly.FromDateTime(DateTime.UtcNow.AddMonths(36))
        };
        _db.InventoryBatches.Add(batch);
        await _db.SaveChangesAsync();

        var movement = new StockMovement
        {
            WarehouseId = po.WarehouseId,
            Sku = product.Sku,
            BatchId = batch.BatchId,
            MovementType = "GRN_INBOUND",
            QtyChange = acceptedQty,
            OnHandBefore = oldOnHand,
            OnHandAfter = newOnHand,
            MovingAvgCostAfter = newMovingAvgCost,
            ReferenceCode = grnNumber,
            CreatedBy = warehouseKeeper,
            CreatedAt = DateTime.UtcNow
        };
        _db.StockMovements.Add(movement);

        await _db.SaveChangesAsync();
        await transaction.CommitAsync();

        await _db.Entry(stock).ReloadAsync();
        await _db.Entry(product).ReloadAsync();

        return new
        {
            Message = "Goods Receipt Note (GRN) Processed Successfully",
            GrnNumber = grnNumber,
            BatchNumber = batch.BatchNumber,
            PoStatus = po.Status,
            Sku = product.Sku,
            OnHandBefore = oldOnHand,
            OnHandAfter = stock.OnHandQty,
            IncomingRemaining = stock.IncomingQty,
            NetInventoryPosition = stock.NetInventoryPosition,
            OldMovingAvgCost = oldCost,
            NewMovingAvgCost = product.CostPrice,
            NewGrossMarginPct = product.GrossMarginPct
        };
    }
    /// <summary>
    /// Calls Python /api/v1/scrape (PriceStalkerEngine + Agent 0), writes verified competitor prices
    /// into PostgreSQL 18 competitor_price_logs, and updates today's row in daily_market_history
    /// so the 22-feature SQL Window View (vw_live_ml_features) immediately reflects live market prices!
    /// </summary>
    public async Task<object> SyncCompetitorPricesAsync(string providerMode = "LOCAL", bool forceAi = false)
    {
        var client = _httpFactory.CreateClient("PythonAi");
        var response = await client.PostAsJsonAsync("/api/v1/scrape", new
        {
            provider_mode = providerMode,
            force_ai = forceAi
        });

        var rawJson = await response.Content.ReadAsStringAsync();
        if (!response.IsSuccessStatusCode)
            throw new InvalidOperationException($"Python Scraper error: {rawJson}");

        using var doc = JsonDocument.Parse(rawJson);
        var root = doc.RootElement;
        string status = root.TryGetProperty("status", out var stEl) ? stEl.GetString() ?? "OK" : "OK";

        var syncedItems = new List<object>();
        var today = DateOnly.FromDateTime(DateTime.UtcNow.AddHours(7)); // Vietnam TZ

        if (root.TryGetProperty("details", out var detailsEl) && detailsEl.ValueKind == JsonValueKind.Array)
        {
            await using var transaction = await _db.Database.BeginTransactionAsync();

            foreach (var item in detailsEl.EnumerateArray())
            {
                string sku = item.GetProperty("sku").GetString() ?? "";
                string comp = item.TryGetProperty("competitor", out var cEl) ? cEl.GetString() ?? "An Phat PC" : "An Phat PC";
                string title = item.TryGetProperty("matched_title", out var tEl) ? tEl.GetString() ?? "" : "";
                long price = item.GetProperty("price").GetInt64();
                decimal conf = item.TryGetProperty("confidence", out var cfEl) ? cfEl.GetDecimal() : 0.95m;
                string method = item.TryGetProperty("method", out var mEl) ? mEl.GetString() ?? "DOM_CARD" : "DOM_CARD";
                string reasoning = item.TryGetProperty("agent_reasoning", out var rEl) ? rEl.GetString() ?? "" : "";

                if (price <= 0) continue;

                // 1. Insert immutable log with PostgreSQL 18 uuidv7()
                var priceLog = new CompetitorPriceLog
                {
                    Sku = sku,
                    CompetitorName = comp,
                    MatchedTitle = title,
                    Price = price,
                    StockStatus = "In Stock (Live Verified)",
                    ConfidenceScore = conf,
                    ExtractionMethod = method,
                    ScrapedAt = DateTime.UtcNow
                };
                _db.CompetitorPriceLogs.Add(priceLog);

                // 2. Upsert today's time-series row in daily_market_history so vw_live_ml_features stays live
                var product = await _db.Products.FirstOrDefaultAsync(p => p.Sku == sku);
                if (product != null)
                {
                    var todayHistory = await _db.DailyMarketHistories
                        .FirstOrDefaultAsync(h => h.Sku == sku && h.RecordDate == today);

                    if (todayHistory != null)
                    {
                        todayHistory.CompetitorMinPrice = price;
                        todayHistory.ListedPrice = product.ListedPrice;
                        todayHistory.CostPrice = product.CostPrice;
                    }
                    else
                    {
                        _db.DailyMarketHistories.Add(new DailyMarketHistory
                        {
                            Sku = sku,
                            RecordDate = today,
                            SalesQty = 3,
                            ListedPrice = product.ListedPrice,
                            CompetitorMinPrice = price,
                            CostPrice = product.CostPrice,
                            IsPromo = false
                        });
                    }
                }

                syncedItems.Add(new
                {
                    priceLog.LogId,
                    sku,
                    competitor = comp,
                    matchedTitle = title,
                    price,
                    confidence = conf,
                    method,
                    agentReasoning = reasoning
                });
            }

            await _db.SaveChangesAsync();
            await transaction.CommitAsync();
        }

        return new
        {
            Status = status,
            SyncedToPostgresCount = syncedItems.Count,
            Timestamp = DateTime.UtcNow,
            Details = syncedItems
        };
    }

    /// <summary>
    /// Calls Python /api/v1/simulate for sub-50ms quantitative What-If Sandbox simulation
    /// using live PostgreSQL 18 lag features and custom slider overrides.
    /// </summary>
    public async Task<JsonElement> RunWhatIfSimulationAsync(
        string sku,
        int? customOnHandStock,
        long? customListedPrice,
        long? customCompetitorPrice,
        decimal serviceLevelZ = 1.65m,
        decimal elasticity = -1.8m)
    {
        var product = await _db.Products.FirstOrDefaultAsync(p => p.Sku == sku)
            ?? throw new InvalidOperationException($"SKU {sku} not found.");

        var stock = await _db.InventoryStocks.FirstAsync(s => s.Sku == sku);
        var feat = await _db.LiveMlFeatures
            .Where(f => f.Sku == sku)
            .OrderByDescending(f => f.RecordDate)
            .FirstAsync();

        int simOnHand = customOnHandStock ?? stock.AvailableQty;
        long simListed = customListedPrice ?? product.ListedPrice;
        long simComp = customCompetitorPrice ?? feat.CompetitorPrice;
        long simDiff = simListed - simComp;
        decimal simRatio = simComp > 0 ? Math.Round((decimal)simListed / simComp, 4) : 1.0m;
        decimal simMargin = simListed > 0 ? Math.Round((decimal)(simListed - product.CostPrice) / simListed, 4) : 0.15m;

        var payload = new
        {
            sku = product.Sku,
            on_hand_stock = simOnHand,
            incoming_stock = stock.IncomingQty,
            cost_price = product.CostPrice,
            listed_price = simListed,
            competitor_price = simComp,
            lead_time_days = product.LeadTimeDays,
            service_level_z = serviceLevelZ,
            elasticity = elasticity,
            features_ml = new Dictionary<string, object>
            {
                ["day_of_week"] = feat.DayOfWeek,
                ["day_of_month"] = feat.DayOfMonth,
                ["month"] = feat.Month,
                ["is_weekend"] = feat.IsWeekend,
                ["is_promo"] = feat.IsPromo,
                ["listed_price"] = simListed,
                ["competitor_price"] = simComp,
                ["cost_price"] = product.CostPrice,
                ["price_diff"] = simDiff,
                ["price_ratio"] = simRatio,
                ["margin_pct"] = simMargin,
                ["sales_lag_1"] = feat.SalesLag1,
                ["sales_lag_3"] = feat.SalesLag3,
                ["sales_lag_7"] = feat.SalesLag7,
                ["sales_lag_14"] = feat.SalesLag14,
                ["comp_price_lag_1"] = feat.CompPriceLag1,
                ["comp_price_lag_3"] = feat.CompPriceLag3,
                ["comp_price_lag_7"] = feat.CompPriceLag7,
                ["comp_price_lag_14"] = feat.CompPriceLag14,
                ["sales_roll_mean_7"] = feat.SalesRollMean7,
                ["sales_roll_std_7"] = feat.SalesRollStd7,
                ["sales_roll_mean_14"] = feat.SalesRollMean14
            }
        };

        var client = _httpFactory.CreateClient("PythonAi");
        var response = await client.PostAsJsonAsync("/api/v1/simulate", payload);
        var rawJson = await response.Content.ReadAsStringAsync();

        if (!response.IsSuccessStatusCode)
            throw new InvalidOperationException($"Python Simulation error: {rawJson}");

        using var doc = JsonDocument.Parse(rawJson);
        return doc.RootElement.Clone();
    }

    /// <summary>
    /// Rejects a PENDING AI recommendation without modifying inventory or prices.
    /// </summary>
    public async Task<object> RejectAiRecommendationAsync(long recommendationId, string managerUsername)
    {
        var rec = await _db.AiSkuRecommendations
            .FirstOrDefaultAsync(r => r.RecommendationId == recommendationId);

        if (rec == null || rec.ApprovalStatus != "PENDING")
            throw new InvalidOperationException("Recommendation not found or not in PENDING status.");

        rec.ApprovalStatus = "REJECTED";
        rec.ReviewedBy = managerUsername;
        rec.ReviewedAt = DateTime.UtcNow;

        await _db.SaveChangesAsync();

        return new
        {
            Message = "AI Recommendation Rejected",
            rec.RecommendationId,
            rec.Sku,
            rec.ApprovalStatus,
            rec.ReviewedBy,
            rec.ReviewedAt
        };
    }
    private static string? ResolveSupplierId(string rawName, List<Supplier> suppliers)
    {
        if (string.IsNullOrWhiteSpace(rawName)) return null;
        string lower = rawName.ToLowerInvariant();
        if (lower.Contains("spc") || lower.Contains("vinh xuan")) return "SUP-SPC";
        if (lower.Contains("vsc") || lower.Contains("viet son")) return "SUP-VSC";
        if (lower.Contains("dgw") || lower.Contains("digiworld")) return "SUP-DGW";
        return suppliers.FirstOrDefault()?.SupplierId;
    }
}