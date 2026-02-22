using System.Data;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Diagnostics.HealthChecks;
using Microsoft.Extensions.Options;
using Npgsql;

namespace DopDoc.Common.Health;

public sealed class PostgresReadyHealthCheck : IHealthCheck
{
    private readonly IConfiguration _config;
    private readonly HealthOptions _options;

    public PostgresReadyHealthCheck(IConfiguration config, IOptions<HealthOptions> options)
    {
        _config = config;
        _options = options.Value;
    }

    public async Task<HealthCheckResult> CheckHealthAsync(HealthCheckContext context, CancellationToken ct = default)
    {
        var o = _options.Ready.Postgres;
        if (!o.Enabled)
            return HealthCheckResult.Healthy("Postgres check disabled");
        
        var cs = _config.GetConnectionString(o.ConnectionName);
        if (string.IsNullOrWhiteSpace(cs))
            return HealthCheckResult.Unhealthy($"ConnectionStrings:{o.ConnectionName} is missing");

        try
        {
            using var cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
            cts.CancelAfter(TimeSpan.FromSeconds(Math.Max(1, o.TimeoutSeconds)));

            await using var conn = new NpgsqlConnection(cs);
            await conn.OpenAsync(cts.Token);

            await using var cmd = new NpgsqlCommand("SELECT 1;", conn)
            {
                CommandType = CommandType.Text
            };
            _ = await cmd.ExecuteScalarAsync(cts.Token);

            return HealthCheckResult.Healthy("Postgres reachable");
        }
        catch (Exception ex)
        {
            return HealthCheckResult.Unhealthy("Postgres unreachable", ex);
        }
    }
}