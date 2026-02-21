namespace DopDoc.Common.Observability;

public sealed class OtelOptions
{
    public string ServiceName { get; init; } = "unknown_service";
    public string ExporterOtlpEndpoint { get; init; } = "";
    public bool EnableTracing { get; init; } = true;
    public bool EnableMetrics { get; init; } = true;
}