using DopDoc.Common.Health;
using DopDoc.Common.Logging;
using DopDoc.Common.Observability;
using Microsoft.OpenApi;
using Serilog;

var builder = WebApplication.CreateBuilder(args);

var serviceName = builder.Configuration["OTEL_SERVICE_NAME"] ?? "auth_service";

SerilogSetup.ConfigureBootstrapLogger(serviceName, builder.Configuration);
builder.Host.UseSerilog((ctx, lc) => lc
    .ReadFrom.Configuration(ctx.Configuration)
    .Enrich.FromLogContext()
);

builder.Services.AddEndpointsApiExplorer();

builder.Services.AddSwaggerGen(o =>
{
    o.SwaggerDoc("v1", new OpenApiInfo
    {
        Title = "DopDocAI Auth API",
        Version = "v1"
    });
});

builder.Services.AddDopDocHealth();
builder.Services.AddDopDocOpenTelemetry(builder.Configuration, serviceName);

var app = builder.Build();

app.Logger.LogInformation("Auth service started. Env={Env}", app.Environment.EnvironmentName);

app.UseSerilogRequestLogging();

app.UseSwagger();
app.UseSwaggerUI(o =>
{
    o.SwaggerEndpoint("/swagger/v1/swagger.json", "DopDocAI Auth API v1");
});

app.MapGet("/", () => Results.Ok(new { service = serviceName, status = "ok" }));

app.MapDopDocHealth();

app.Run();
