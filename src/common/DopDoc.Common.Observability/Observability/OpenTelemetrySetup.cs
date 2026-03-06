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
        Action<OtelOptions>? configure = null)
    {
        var options = new OtelOptions();
        config.GetSection("Otel").Bind(options);
        configure?.Invoke(options);
        
        var serviceName = string.IsNullOrWhiteSpace(options.ServiceName) ? "unknown_service" : options.ServiceName;

        services.AddOpenTelemetry()
            .ConfigureResource(r => r.AddService(serviceName))
            .WithTracing(t =>
            {
                if (!options.EnableTracing) return;

                t.AddAspNetCoreInstrumentation(o => o.RecordException = true);
                t.AddHttpClientInstrumentation(o => o.RecordException = true);

                if (!string.IsNullOrWhiteSpace(options.ExporterOtlpEndpoint))
                {
                    t.AddOtlpExporter(exp =>
                    {
                        exp.Endpoint = new Uri(options.ExporterOtlpEndpoint);
                    });
                }
            })
            .WithMetrics(m =>
            {
                if (!options.EnableMetrics) return;

                m.AddAspNetCoreInstrumentation();
                m.AddHttpClientInstrumentation();
                m.AddRuntimeInstrumentation();

                if (!string.IsNullOrWhiteSpace(options.ExporterOtlpEndpoint))
                {
                    m.AddOtlpExporter(exp =>
                    {
                        exp.Endpoint = new Uri(options.ExporterOtlpEndpoint);
                    });
                }
            });

        return services;
    }
}
