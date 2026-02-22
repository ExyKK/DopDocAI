using System.Net.Sockets;
using Microsoft.Extensions.Diagnostics.HealthChecks;
using Microsoft.Extensions.Options;

namespace DopDoc.Common.Health;

public sealed class RabbitReadyHealthCheck : IHealthCheck
{
    private readonly HealthOptions _options;

    public RabbitReadyHealthCheck(IOptions<HealthOptions> options) => _options = options.Value;

    public async Task<HealthCheckResult> CheckHealthAsync(HealthCheckContext context, CancellationToken ct = default)
    {
        var o = _options.Ready.Rabbit;
        if (!o.Enabled) 
            return HealthCheckResult.Healthy("Rabbit check disabled");

        if (string.IsNullOrWhiteSpace(o.AmqpUrl))
            return HealthCheckResult.Unhealthy("Health:Ready:Rabbit:AmqpUrl not set");

        if (!Uri.TryCreate(o.AmqpUrl, UriKind.Absolute, out var uri) || string.IsNullOrWhiteSpace(uri.Host))
            return HealthCheckResult.Unhealthy("Rabbit AmqpUrl is invalid");

        var port = uri.Port > 0 ? uri.Port : 5672;

        try
        {
            using var client = new TcpClient();
            using var timeoutCts = CancellationTokenSource.CreateLinkedTokenSource(ct);
            timeoutCts.CancelAfter(TimeSpan.FromSeconds(Math.Max(1, o.TimeoutSeconds)));

            await client.ConnectAsync(uri.Host, port, timeoutCts.Token);
            return HealthCheckResult.Healthy("Rabbit reachable");
        }
        catch (Exception ex)
        {
            return HealthCheckResult.Unhealthy("Rabbit unreachable", ex);
        }
    }
}