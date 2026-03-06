using Microsoft.Extensions.Diagnostics.HealthChecks;
using Microsoft.Extensions.Options;

namespace DopDoc.Common.Health;

public sealed class QdrantReadyHealthCheck : IHealthCheck
{
    private readonly IHttpClientFactory _http;
    private readonly HealthOptions _options;

    public QdrantReadyHealthCheck(IHttpClientFactory http, IOptions<HealthOptions> options)
    {
        _http = http;
        _options = options.Value;
    }

    public async Task<HealthCheckResult> CheckHealthAsync(HealthCheckContext context, CancellationToken ct = default)
    {
        var o = _options.Ready.Qdrant;
        if (!o.Enabled) 
            return HealthCheckResult.Healthy("Qdrant check disabled");

        if (string.IsNullOrWhiteSpace(o.BaseUrl))
            return HealthCheckResult.Unhealthy("Health:Ready:Qdrant:BaseUrl not set");

        var url = o.BaseUrl.TrimEnd('/') + o.ReadyPath;

        var client = _http.CreateClient(nameof(QdrantReadyHealthCheck));
        client.Timeout = TimeSpan.FromSeconds(Math.Max(1, o.TimeoutSeconds));

        try
        {
            using var resp = await client.GetAsync(url, ct);
            return resp.IsSuccessStatusCode
                ? HealthCheckResult.Healthy($"Qdrant reachable ({(int)resp.StatusCode})")
                : HealthCheckResult.Unhealthy($"Qdrant unhealthy ({(int)resp.StatusCode})");
        }
        catch (Exception ex)
        {
            return HealthCheckResult.Unhealthy("Qdrant unreachable", ex);
        }
    }
}