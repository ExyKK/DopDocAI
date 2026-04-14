using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Diagnostics.HealthChecks;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Diagnostics.HealthChecks;

namespace DopDoc.Common.Health;

public static class HealthExtensions
{
    public static IServiceCollection AddDopDocHealth(this IServiceCollection services, IConfiguration config)
    {
        services.AddOptions<HealthOptions>()
            .Bind(config.GetSection("Health"))
            .ValidateOnStart();

        services.AddHttpClient();

        var hc = services.AddHealthChecks();

        hc.AddCheck<PostgresReadyHealthCheck>(
            "postgres_ready",
            failureStatus: HealthStatus.Unhealthy,
            tags: ["ready"]
        );
        hc.AddCheck<MinioReadyHealthCheck>(
            "minio_ready",
            failureStatus: HealthStatus.Unhealthy,
            tags: ["ready"]
        );
        hc.AddCheck<QdrantReadyHealthCheck>(
            "qdrant_ready",
            failureStatus: HealthStatus.Unhealthy,
            tags: ["ready"]
        );

        return services;
    }

    public static IEndpointRouteBuilder MapDopDocHealth(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapGet("/health/live", () => Results.Ok(new { status = "live" }));

        endpoints.MapHealthChecks("/health/ready", new HealthCheckOptions
        {
            Predicate = r => r.Tags.Contains("ready"),
            ResponseWriter = async (ctx, report) =>
            {
                ctx.Response.ContentType = "application/json";
                var result = new
                {
                    status = report.Status.ToString(),
                    checks = report.Entries.Select(e => new
                    {
                        name = e.Key,
                        status = e.Value.Status.ToString(),
                        error = e.Value.Exception?.Message,
                        durationMs = (int)e.Value.Duration.TotalMilliseconds
                    })
                };
                await ctx.Response.WriteAsJsonAsync(result);
            }
        });

        return endpoints;
    }
}