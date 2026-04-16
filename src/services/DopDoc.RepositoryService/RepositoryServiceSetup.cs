using DopDoc.Common.Correlation;
using DopDoc.Common.Errors;
using DopDoc.Common.Health;
using DopDoc.Common.Logging;
using DopDoc.Common.Observability;
using DopDoc.Common.UserContext;
using DopDoc.RepositoryService.Api;
using Microsoft.OpenApi;
using Serilog;

namespace DopDoc.RepositoryService;

public static class RepositoryServiceSetup
{
    public static IServiceCollection AddRepositoryService(this IServiceCollection services, IConfiguration config)
    {
        var serviceName = config["Otel:ServiceName"] ?? "repository_service";

        SerilogSetup.ConfigureBootstrapLogger(serviceName, config);

        services.AddSerilog(lc => lc
            .ReadFrom.Configuration(config)
            .Enrich.FromLogContext());

        services.AddEndpointsApiExplorer();
        services.AddSwaggerGen(o =>
        {
            o.SwaggerDoc("v1", new OpenApiInfo
            {
                Title = "DopDocAI Repository API",
                Version = "v1"
            });
        });

        services.AddDopDocProblemDetails();
        services.AddDopDocHealth(config);
        services.AddDopDocOpenTelemetry(config);
        services.AddDopDocCorrelation(config);
        services.AddDopDocUserContext();

        return services;
    }

    public static WebApplication UseRepositoryService(this WebApplication app)
    {
        app.UseDopDocCorrelation();
        app.UseSerilogRequestLogging();
        app.UseDopDocExceptionHandling();

        app.UseSwagger();
        app.UseSwaggerUI(o =>
        {
            o.SwaggerEndpoint("/swagger/v1/swagger.json", "DopDocAI Repository API v1");
        });

        app.MapDopDocHealth();
        app.MapGet("/", () => Results.Ok(new { service = "repository_service", status = "ok" })).AllowAnonymous();
        app.MapRepositoryEndpoints();

        app.Logger.LogInformation("Repository service started. Env={Env}", app.Environment.EnvironmentName);

        return app;
    }
}
