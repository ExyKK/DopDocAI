namespace DopDoc.ChatService.Infrastructure.Clients;

public sealed class RepositoryServiceOptions
{
    public string BaseUrl { get; init; } = "http://repository_service:19200";
    public double TimeoutSeconds { get; init; } = 10;
}

