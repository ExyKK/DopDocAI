namespace DopDoc.Common.Health;

public sealed class HealthOptions
{
    public ReadyOptions Ready { get; init; } = new();

    public sealed class ReadyOptions
    {
        public PostgresOptions Postgres { get; init; } = new();
        public MinioOptions Minio { get; init; } = new();
        public QdrantOptions Qdrant { get; init; } = new();
    }

    public sealed class PostgresOptions
    {
        public bool Enabled { get; init; } = false;
        public string ConnectionName { get; init; } = "Default";
        public int TimeoutSeconds { get; init; } = 2;
    }

    public sealed class MinioOptions
    {
        public bool Enabled { get; init; } = false;
        public string? Endpoint { get; init; }
        public int TimeoutSeconds { get; init; } = 2;
    }

    public sealed class QdrantOptions
    {
        public bool Enabled { get; init; } = false;
        public string? BaseUrl { get; init; }
        public string ReadyPath { get; init; } = "/readyz";
        public int TimeoutSeconds { get; init; } = 2;
    }
}