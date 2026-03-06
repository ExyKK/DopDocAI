using DopDoc.Common.Correlation;
using DopDoc.Common.Errors;
using DopDoc.Common.Health;
using DopDoc.Common.Logging;
using DopDoc.Common.Observability;
using DopDoc.EdgeGateway.Api.Auth;
using DopDoc.EdgeGateway.Api.Proxy;
using DopDoc.EdgeGateway.Infrastructure.Security;
using Microsoft.OpenApi;
using Serilog;

namespace DopDoc.EdgeGateway;

public static class EdgeGatewaySetup
{
    public static IServiceCollection AddEdgeGateway(this IServiceCollection services, IConfiguration config)
    {
        var serviceName = config["Otel:ServiceName"] ?? "edge_gateway";

        SerilogSetup.ConfigureBootstrapLogger(serviceName, config);

        services.AddSerilog(lc => lc
            .ReadFrom.Configuration(config)
            .Enrich.FromLogContext()
        );

        services.AddOptions<GatewayAuthOptions>()
            .Bind(config.GetSection("Auth"))
            .Validate(o => !string.IsNullOrWhiteSpace(o.JwtSecret) && o.JwtSecret.Length >= 32,
                "Auth:JwtSecret must be set and at least 32 chars.")
            .Validate(o => !string.IsNullOrWhiteSpace(o.JwtIssuer),
                "Auth:JwtIssuer must be set.")
            .Validate(o => !string.IsNullOrWhiteSpace(o.JwtAudience),
                "Auth:JwtAudience must be set.")
            .ValidateOnStart();

        services.AddTransient<UserContextProxyMiddleware>();
        services.AddDopDocGatewayJwtAuth();

        services.AddReverseProxy()
            .LoadFromConfig(config.GetSection("ReverseProxy"));

        services.AddEndpointsApiExplorer();
        services.AddSwaggerGen(o =>
        {
            o.SwaggerDoc("v1", new OpenApiInfo
            {
                Title = "DopDocAI Edge Gateway API",
                Version = "v1"
            });
        });

        services.AddDopDocProblemDetails();
        services.AddDopDocHealth(config);
        services.AddDopDocOpenTelemetry(config);
        services.AddDopDocCorrelation(config);

        return services;
    }

    public static WebApplication UseEdgeGateway(this WebApplication app)
    {
        app.UseDopDocCorrelation();
        app.UseSerilogRequestLogging();
        app.UseDopDocExceptionHandling();
        app.UseWebSockets();
        app.UseAuthentication();
        app.UseAuthorization();
        app.UseMiddleware<UserContextProxyMiddleware>();

        app.UseSwagger();
        app.UseSwaggerUI(o =>
        {
            o.SwaggerEndpoint("/swagger/v1/swagger.json", "DopDocAI Edge Gateway API v1");
        });

        app.MapDopDocHealth();
        app.MapGet("/", () => Results.Ok(new { service = "edge_gateway", status = "ok" })).AllowAnonymous();
        app.MapReverseProxy();

        app.Logger.LogInformation("Edge gateway started. Env={Env}", app.Environment.EnvironmentName);

        return app;
    }
}
