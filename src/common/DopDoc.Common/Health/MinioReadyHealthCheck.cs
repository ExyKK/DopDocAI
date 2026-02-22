using Microsoft.Extensions.Diagnostics.HealthChecks;
using Microsoft.Extensions.Options;

namespace DopDoc.Common.Health;

public sealed class MinioReadyHealthCheck : IHealthCheck
{
    private readonly IHttpClientFactory _http;
    private readonly HealthOptions _options;

    public MinioReadyHealthCheck(IHttpClientFactory http, IOptions<HealthOptions> options)
    {
        _http = http;
        _options = options.Value;
    }

    public async Task<HealthCheckResult> CheckHealthAsync(HealthCheckContext context, CancellationToken ct = default)
    {
        var o = _options.Ready.Minio;
        if (!o.Enabled) 
            return HealthCheckResult.Healthy("MinIO check disabled");

        if (string.IsNullOrWhiteSpace(o.Endpoint))
            return HealthCheckResult.Unhealthy("Health:Ready:Minio:Endpoint not set");

        var url = o.Endpoint.TrimEnd('/') + "/minio/health/live";

        var client = _http.CreateClient(nameof(MinioReadyHealthCheck));
        client.Timeout = TimeSpan.FromSeconds(Math.Max(1, o.TimeoutSeconds));

        try
        {
            using var resp = await client.GetAsync(url, ct);
            return resp.IsSuccessStatusCode
                ? HealthCheckResult.Healthy($"MinIO reachable ({(int)resp.StatusCode})")
                : HealthCheckResult.Unhealthy($"MinIO unhealthy ({(int)resp.StatusCode})");
        }
        catch (Exception ex)
        {
            return HealthCheckResult.Unhealthy("MinIO unreachable", ex);
        }
    }
}