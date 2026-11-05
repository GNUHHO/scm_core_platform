using Microsoft.EntityFrameworkCore;
using ScmCore.Api.Data;
using ScmCore.Api.Services;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddControllers();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

// 1. Register PostgreSQL 18 DbContext
builder.Services.AddDbContext<ScmDbContext>(options =>
    options.UseNpgsql(builder.Configuration.GetConnectionString("ScmPostgres")));

// 2. Register Warehouse Inventory & AI Bridge Service
builder.Services.AddScoped<WarehouseInventoryService>();

// 3. Register HttpClient pointing to Python FastAPI AI Microservice
builder.Services.AddHttpClient("PythonAi", client =>
{
    var baseUrl = builder.Configuration["PythonAiService:BaseUrl"] ?? "http://localhost:8000";
    client.BaseAddress = new Uri(baseUrl);
    client.Timeout = TimeSpan.FromSeconds(60);
});

// 4. Enable CORS for Frontend
builder.Services.AddCors(options =>
{
    options.AddPolicy("AllowAll", policy =>
        policy.AllowAnyOrigin().AllowAnyHeader().AllowAnyMethod());
});

var app = builder.Build();

app.UseSwagger();
app.UseSwaggerUI();
app.UseCors("AllowAll");
app.MapControllers();

app.Run();