using Microsoft.Extensions.Configuration;
using Serilog;
using Serilog.Events;
using Serilog.Formatting.Json;
using Serilog.Sinks.OpenTelemetry;

namespace DopDoc.Common.Logging;

public static class SerilogSetup
{
    public static void ConfigureBootstrapLogger(string serviceName, IConfiguration config)
    {
        var minLevel = config["Serilog:MinimumLevel:Default"] ?? "Information";
        var otlpEndpoint = config["Otel:ExporterOtlpEndpoint"];

        var loggerConfig = new LoggerConfiguration()
            .MinimumLevel.Is(ParseLevel(minLevel))
            .MinimumLevel.Override("Microsoft", LogEventLevel.Warning)
            .MinimumLevel.Override("System", LogEventLevel.Warning)
            .Enrich.FromLogContext()
            .Enrich.WithProperty("service.name", serviceName)
            .WriteTo.Console(new JsonFormatter(renderMessage: true));

        if (!string.IsNullOrWhiteSpace(otlpEndpoint))
        {
            loggerConfig.WriteTo.OpenTelemetry(options =>
            {
                options.Endpoint = otlpEndpoint;
                options.Protocol = OtlpProtocol.Grpc;
                options.ResourceAttributes = new Dictionary<string, object>
                {
                    ["service.name"] = serviceName
                };
            });
        }

        Log.Logger = loggerConfig.CreateBootstrapLogger();
    }

    private static LogEventLevel ParseLevel(string level) =>
        Enum.TryParse<LogEventLevel>(level, ignoreCase: true, out var parsed)
            ? parsed
            : LogEventLevel.Information;
}