namespace DopDoc.ChatService.Infrastructure.Clients;

public sealed class RetrievalOptions
{
    public string BaseUrl { get; init; } = "http://ingestion_service:19100";
    public double TimeoutSeconds { get; init; } = 60;
    public int TopK { get; init; } = 8;
    public bool IncludeTests { get; init; } = true;
    public double? ScoreThreshold { get; init; }
}

