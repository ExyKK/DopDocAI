namespace DopDoc.ChatService.Domain;

public sealed class Chat
{
    public Guid Id { get; set; }
    public Guid RepositoryId { get; set; }
    public Guid SnapshotId { get; set; }
    public Guid UserId { get; set; }
    public string? Title { get; set; }
    public DateTimeOffset CreatedAt { get; set; }
    public DateTimeOffset UpdatedAt { get; set; }
    public DateTimeOffset? LastMessageAt { get; set; }
    public DateTimeOffset? ArchivedAt { get; set; }

    public ICollection<ChatMessage> Messages { get; set; } = new List<ChatMessage>();
}

public sealed class ChatMessage
{
    public Guid Id { get; set; }
    public Guid ChatId { get; set; }
    public string Role { get; set; } = "";
    public string ContentMarkdown { get; set; } = "";
    public string? ModelName { get; set; }
    public string? Provider { get; set; }
    public string? PromptVersion { get; set; }
    public int? InputTokens { get; set; }
    public int? OutputTokens { get; set; }
    public string? FinishReason { get; set; }
    public int? RetrievalTimeMs { get; set; }
    public int? GenerationTimeMs { get; set; }
    public DateTimeOffset CreatedAt { get; set; }

    public Chat Chat { get; set; } = null!;
    public ICollection<ChatMessageSource> Sources { get; set; } = new List<ChatMessageSource>();
}

public sealed class ChatMessageSource
{
    public Guid MessageId { get; set; }
    public int Ordinal { get; set; }
    public Guid SnapshotId { get; set; }
    public string SourceKind { get; set; } = "";
    public string? FilePath { get; set; }
    public string? SymbolName { get; set; }
    public int? StartLine { get; set; }
    public int? EndLine { get; set; }
    public string? ChunkId { get; set; }
    public double? Score { get; set; }
    public bool UsedInAnswer { get; set; }
    public string? CitationLabel { get; set; }

    public ChatMessage Message { get; set; } = null!;
}
