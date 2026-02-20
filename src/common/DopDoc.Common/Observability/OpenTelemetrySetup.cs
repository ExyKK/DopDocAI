using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using OpenTelemetry.Metrics;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;

namespace DopDoc.Common.Observability;

public static class OpenTelemetrySetup
{
    public static IServiceCollection AddDopDocOpenTelemetry(
        this IServiceCollection services,
        IConfiguration config,
        string serviceName)
    {
        var otlpEndpoint = config["OTEL_EXPORTER_OTLP_ENDPOINT"];
        var otlpProtocol = (config["OTEL_EXPORTER_OTLP_PROTOCOL"] ?? "grpc").ToLowerInvariant();

        services.AddOpenTelemetry()
            .ConfigureResource(r => r.AddService(serviceName))
            .WithTracing(t =>
            {
                t.AddAspNetCoreInstrumentation(o =>
                {
                    o.RecordException = true;
                });

                t.AddHttpClientInstrumentation(o =>
                {
                    o.RecordException = true;
                });

                if (!string.IsNullOrWhiteSpace(otlpEndpoint))
                {
                    t.AddOtlpExporter(o =>
                    {
                        o.Endpoint = new Uri(otlpEndpoint);
                        // protocol auto via env OTEL_EXPORTER_OTLP_PROTOCOL if needed,
                        // but we keep it minimal here.
                    });
                }
            })
            .WithMetrics(m =>
            {
                m.AddAspNetCoreInstrumentation();
                m.AddHttpClientInstrumentation();
                m.AddRuntimeInstrumentation();

                if (!string.IsNullOrWhiteSpace(otlpEndpoint))
                {
                    m.AddOtlpExporter(o =>
                    {
                        o.Endpoint = new Uri(otlpEndpoint);
                    });
                }
            });

        return services;
    }
}