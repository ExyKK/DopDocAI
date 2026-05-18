using DopDoc.Common.Correlation;
using DopDoc.Common.Configuration;
using DopDoc.Common.Errors;
using DopDoc.Common.Health;
using DopDoc.Common.Logging;
using DopDoc.Common.Observability;
using DopDoc.Common.UserContext;
using DopDoc.RepositoryService.Api;
using DopDoc.RepositoryService.Application.Documentation;
using DopDoc.RepositoryService.Application.Jobs;
using DopDoc.RepositoryService.Application.Repositories;
using DopDoc.RepositoryService.Infrastructure.Data;
using Microsoft.EntityFrameworkCore;
using Microsoft.OpenApi;
using Microsoft.Extensions.Options;
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
        services.AddOptions<JobExecutionOptions>()
            .Bind(config.GetSection("Jobs"))
            .Validate(x => x.MaxAttempts > 0, "Jobs:MaxAttempts must be greater than 0")
            .Validate(x => x.LeaseSeconds > 0, "Jobs:LeaseSeconds must be greater than 0")
            .Validate(x => x.HeartbeatSeconds > 0, "Jobs:HeartbeatSeconds must be greater than 0")
            .ValidateOnStart();
        services.AddScoped<RepositoryApplicationService>();
        services.AddScoped<RepositorySnapshotApplicationService>();
        services.AddScoped<AnalysisArtifactApplicationService>();
        services.AddScoped<DocumentationSectionApplicationService>();
        services.AddScoped<DocumentationArtifactApplicationService>();
        services.AddScoped<JobRunApplicationService>();

        services.AddOptions<DbOptions>()
            .Bind(config.GetSection("Db"))
            .ValidateOnStart();

        services.AddDbContext<RepositoryDbContext>((sp, o) =>
        {
            var cfg = sp.GetRequiredService<IConfiguration>();
            var db = sp.GetRequiredService<IOptions<DbOptions>>().Value;

            var cs = cfg.GetConnectionString("RepoDb");
            if (string.IsNullOrWhiteSpace(cs))
                throw new InvalidOperationException("ConnectionStrings:RepoDb is required");

            o.UseNpgsql(cs, npgsql => npgsql.MigrationsHistoryTable("__EFMigrationsHistory", db.Schema));
        });

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
        app.MapRepositoryInternalEndpoints();
        app.MapDocumentationInternalEndpoints();
        app.MapRunEndpoints();

        app.Logger.LogInformation("Repository service started. Env={Env}", app.Environment.EnvironmentName);

        return app;
    }
}
