namespace DopDoc.ChatService.Infrastructure.Llm;

public sealed class LlmOptions
{
    public string Provider { get; init; } = "stub";
    public string Endpoint { get; init; } = "https://openrouter.ai/api/v1/chat/completions";
    public string ApiKey { get; init; } = "";
    public string Model { get; init; } = "deepseek/deepseek-v3.2";
    public double TimeoutSeconds { get; init; } = 60;
    public double Temperature { get; init; } = 0.2;
    public int MaxTokens { get; init; } = 1536;
    public double TopP { get; init; } = 0.95;
    public double? RepetitionPenalty { get; init; } = 1.05;
    public int HistoryLimit { get; init; } = 20;
    public int MaxSourceChars { get; init; } = 24_000;
    public string DefaultSystemPrompt { get; init; } =
        "You are DopDocAI, a helpful assistant for answering questions about indexed code repositories.";
}

