namespace DopDoc.ChatService.Infrastructure.Llm;

public sealed class LlmOptions
{
    public string Provider { get; set; } = "openrouter";
    public string Endpoint { get; set; } = "https://openrouter.ai/api/v1/chat/completions";
    public string ApiKey { get; set; } = "";
    public string Model { get; set; } = "deepseek/deepseek-v4-flash";
    public double TimeoutSeconds { get; set; } = 90;
    public double Temperature { get; set; } = 0.2;
    public int MaxTokens { get; set; } = 1536;
    public double TopP { get; set; } = 0.95;
    public double? RepetitionPenalty { get; set; } = 1.05;
    public int HistoryLimit { get; set; } = 20;
    public int MaxSourceChars { get; set; } = 24_000;
    public string DefaultSystemPrompt { get; set; } =
        "You are DopDocAI, a helpful assistant for answering questions about indexed code repositories.";
}
