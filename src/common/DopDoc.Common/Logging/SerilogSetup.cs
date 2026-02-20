using Microsoft.Extensions.Configuration;
using Serilog;
using Serilog.Events;
using Serilog.Formatting.Json;

namespace DopDoc.Common.Logging;

public static class SerilogSetup
{
    public static void ConfigureBootstrapLogger(string serviceName, IConfiguration config)
    {
        var minLevel = config["LOG_LEVEL"] ?? "Information";

        Log.Logger = new LoggerConfiguration()
            .MinimumLevel.Is(ParseLevel(minLevel))
            .MinimumLevel.Override("Microsoft", LogEventLevel.Warning)
            .MinimumLevel.Override("System", LogEventLevel.Warning)
            .Enrich.FromLogContext()
            .Enrich.WithProperty("service", serviceName)
            .WriteTo.Console(new JsonFormatter(renderMessage: true))
            .CreateBootstrapLogger();
    }

    private static LogEventLevel ParseLevel(string level) =>
        Enum.TryParse<LogEventLevel>(level, ignoreCase: true, out var parsed)
            ? parsed
            : LogEventLevel.Information;
}