namespace DopDoc.Common.Correlation;

public sealed class CorrelationOptions
{
    public string HeaderName { get; init; } = "X-Correlation-Id";

    // Если true — используем trace id как correlation id,
    // false — генерим отдельный корреляционный id.
    public bool UseTraceIdAsCorrelationId { get; init; } = false;
}