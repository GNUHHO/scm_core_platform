using Microsoft.EntityFrameworkCore;
using ScmCore.Api.Models;

namespace ScmCore.Api.Data;

public class ScmDbContext : DbContext
{
    public ScmDbContext(DbContextOptions<ScmDbContext> options) : base(options) { }

    public DbSet<Warehouse> Warehouses => Set<Warehouse>();
    public DbSet<Supplier> Suppliers => Set<Supplier>();
    public DbSet<Product> Products => Set<Product>();
    public DbSet<InventoryStock> InventoryStocks => Set<InventoryStock>();
    public DbSet<CompetitorPriceLog> CompetitorPriceLogs => Set<CompetitorPriceLog>();
    public DbSet<DailyMarketHistory> DailyMarketHistories => Set<DailyMarketHistory>();
    public DbSet<AgentAuditRun> AgentAuditRuns => Set<AgentAuditRun>();
    public DbSet<AiSkuRecommendation> AiSkuRecommendations => Set<AiSkuRecommendation>();
    public DbSet<PurchaseOrder> PurchaseOrders => Set<PurchaseOrder>();
    public DbSet<PurchaseOrderItem> PurchaseOrderItems => Set<PurchaseOrderItem>();
    public DbSet<GoodsReceipt> GoodsReceipts => Set<GoodsReceipt>();
    public DbSet<InventoryBatch> InventoryBatches => Set<InventoryBatch>();
    public DbSet<StockMovement> StockMovements => Set<StockMovement>();
    public DbSet<PriceChangeLedger> PriceChangeLedgers => Set<PriceChangeLedger>();
    public DbSet<LiveMlFeatureView> LiveMlFeatures => Set<LiveMlFeatureView>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        // Map PostgreSQL 18 22-Feature Window View
        modelBuilder.Entity<LiveMlFeatureView>()
            .ToView("vw_live_ml_features")
            .HasNoKey();

        // PurchaseOrder 1-N PurchaseOrderItems relationship
        modelBuilder.Entity<PurchaseOrder>()
            .HasMany(p => p.Items)
            .WithOne()
            .HasForeignKey(i => i.PoId);

        // ĐĂNG KÝ KHÓA CHÍNH RÕ RÀNG CHO CompetitorPriceLog ĐỂ EF CORE THEO DÕI (TRACK) ĐƯỢC
        modelBuilder.Entity<CompetitorPriceLog>()
            .HasKey(c => c.LogId);
    }
}