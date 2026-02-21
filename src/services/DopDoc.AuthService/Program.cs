using DopDoc.AuthService.Api;
using DopDoc.AuthService.Application.Auth;
using DopDoc.AuthService.Infrastructure.Data;
using DopDoc.AuthService.Infrastructure.Security;
using DopDoc.Common.Configuration;
using DopDoc.Common.Health;
using DopDoc.Common.Logging;
using DopDoc.Common.Observability;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;
using Microsoft.OpenApi;
using Serilog;

var builder = WebApplication.CreateBuilder(args);

var serviceName = builder.Configuration["Otel:ServiceName"] ?? "auth_service";

// Serilog
SerilogSetup.ConfigureBootstrapLogger(serviceName, builder.Configuration);
builder.Host.UseSerilog((ctx, lc) => lc
    .ReadFrom.Configuration(ctx.Configuration)
    .Enrich.FromLogContext()
);

// Options + services
builder.Services
    .AddOptions<AuthOptions>()
    .Bind(builder.Configuration.GetSection("Auth"))
    .Validate(o => !string.IsNullOrWhiteSpace(o.JwtSecret) && o.JwtSecret.Length >= 32,
        "Auth:JwtSecret must be set and at least 32 chars.")
    .Validate(o => !string.IsNullOrWhiteSpace(o.RefreshPepper) && o.RefreshPepper.Length >= 32,
        "Auth:RefreshPepper must be set and at least 32 chars.")
    .ValidateOnStart();
builder.Services.AddSingleton<TokenService>();
builder.Services.AddScoped<AuthApplicationService>();

// Db
builder.Services
    .AddOptions<DbOptions>()
    .Bind(builder.Configuration.GetSection("Db"))
    .ValidateOnStart();

builder.Services.AddDbContext<AuthDbContext>((sp, o) =>
{
    var cfg = sp.GetRequiredService<IConfiguration>();
    var db = sp.GetRequiredService<IOptions<DbOptions>>().Value;

    var cs = cfg.GetConnectionString("AuthDb");
    if (string.IsNullOrWhiteSpace(cs))
        throw new InvalidOperationException("ConnectionStrings:AuthDb is required");

    o.UseNpgsql(cs, npgsql => npgsql.MigrationsHistoryTable("__EFMigrationsHistory", db.Schema));
});

// Swagger
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen(o =>
{
    o.SwaggerDoc("v1", new OpenApiInfo
    {
        Title = "DopDocAI Auth API",
        Version = "v1"
    });
});

// Health + OTEL
builder.Services.AddDopDocHealth();
builder.Services.AddDopDocOpenTelemetry(builder.Configuration);

var app = builder.Build();

app.UseSerilogRequestLogging();

app.UseSwagger();
app.UseSwaggerUI(o =>
{
    o.SwaggerEndpoint("/swagger/v1/swagger.json", "DopDocAI Auth API v1");
});

// Endpoints
app.MapGet("/", () => Results.Ok(new { service = serviceName, status = "ok" }));
app.MapDopDocHealth();
app.MapAuthEndpoints();

app.Logger.LogInformation("Auth service started. Env={Env}", app.Environment.EnvironmentName);

app.Run();
