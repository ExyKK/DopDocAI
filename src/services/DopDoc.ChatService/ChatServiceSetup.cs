using DopDoc.ChatService.Api;
using DopDoc.ChatService.Application.Chats;
using DopDoc.ChatService.Infrastructure.Clients;
using DopDoc.Common.Correlation;
using DopDoc.Common.Configuration;
using DopDoc.Common.Errors;
using DopDoc.Common.Health;
using DopDoc.Common.Logging;
using DopDoc.Common.Observability;
using DopDoc.Common.UserContext;
using DopDoc.ChatService.Infrastructure.Data;
using DopDoc.ChatService.Infrastructure.Llm;
using Microsoft.EntityFrameworkCore;
using Microsoft.OpenApi;
using Microsoft.Extensions.Options;
using Serilog;

namespace DopDoc.ChatService;

public static class ChatServiceSetup
{
    public static IServiceCollection AddChatService(this IServiceCollection services, IConfiguration config)
    {
        var serviceName = config["Otel:ServiceName"] ?? "chat_service";

        SerilogSetup.ConfigureBootstrapLogger(serviceName, config);

        services.AddSerilog(lc => lc
            .ReadFrom.Configuration(config)
            .Enrich.FromLogContext());

        services.AddEndpointsApiExplorer();
        services.AddSwaggerGen(o =>
        {
            o.SwaggerDoc("v1", new OpenApiInfo
            {
                Title = "DopDocAI Chat API",
                Version = "v1"
            });
        });

        services.AddDopDocProblemDetails();
        services.AddDopDocHealth(config);
        services.AddDopDocOpenTelemetry(config);
        services.AddDopDocCorrelation(config);
        services.AddDopDocUserContext();

        services.AddOptions<RepositoryServiceOptions>()
            .Bind(config.GetSection("RepositoryService"))
            .Validate(o => Uri.TryCreate(o.BaseUrl, UriKind.Absolute, out _),
                "RepositoryService:BaseUrl must be an absolute URL")
            .Validate(o => o.TimeoutSeconds > 0,
                "RepositoryService:TimeoutSeconds must be greater than 0")
            .ValidateOnStart();

        services.AddOptions<RetrievalOptions>()
            .Bind(config.GetSection("Retrieval"))
            .Validate(o => Uri.TryCreate(o.BaseUrl, UriKind.Absolute, out _),
                "Retrieval:BaseUrl must be an absolute URL")
            .Validate(o => o.TimeoutSeconds > 0,
                "Retrieval:TimeoutSeconds must be greater than 0")
            .Validate(o => o.TopK is >= 1 and <= 50,
                "Retrieval:TopK must be between 1 and 50")
            .ValidateOnStart();

        services.AddOptions<LlmOptions>()
            .Bind(config.GetSection("Llm"))
            .Validate(o => o.Provider is "stub" or "openai_compatible" or "openrouter",
                "Llm:Provider must be stub, openai_compatible or openrouter")
            .Validate(o => o.Provider == "stub" || !string.IsNullOrWhiteSpace(o.ApiKey),
                "Llm:ApiKey is required when Llm:Provider is not stub")
            .Validate(o => o.Provider == "stub" || Uri.TryCreate(o.Endpoint, UriKind.Absolute, out _),
                "Llm:Endpoint must be an absolute URL")
            .Validate(o => o.TimeoutSeconds > 0,
                "Llm:TimeoutSeconds must be greater than 0")
            .Validate(o => o.MaxTokens > 0,
                "Llm:MaxTokens must be greater than 0")
            .Validate(o => o.HistoryLimit >= 0,
                "Llm:HistoryLimit must be greater than or equal to 0")
            .Validate(o => o.MaxSourceChars > 0,
                "Llm:MaxSourceChars must be greater than 0")
            .ValidateOnStart();

        services.AddScoped<ChatApplicationService>();
        services.AddHttpClient<RepositoryServiceClient>();
        services.AddHttpClient<RetrievalServiceClient>();
        services.AddHttpClient<OpenAiCompatibleChatCompletionProvider>();
        services.AddSingleton<StubChatCompletionProvider>();
        services.AddScoped<IChatCompletionProvider>(sp =>
        {
            var options = sp.GetRequiredService<IOptions<LlmOptions>>().Value;
            return options.Provider switch
            {
                "stub" => sp.GetRequiredService<StubChatCompletionProvider>(),
                "openai_compatible" or "openrouter" => sp.GetRequiredService<OpenAiCompatibleChatCompletionProvider>(),
                _ => throw new InvalidOperationException($"Unsupported LLM provider '{options.Provider}'.")
            };
        });

        services.AddOptions<DbOptions>()
            .Bind(config.GetSection("Db"))
            .ValidateOnStart();

        services.AddDbContext<ChatDbContext>((sp, o) =>
        {
            var cfg = sp.GetRequiredService<IConfiguration>();
            var db = sp.GetRequiredService<IOptions<DbOptions>>().Value;

            var cs = cfg.GetConnectionString("ChatDb");
            if (string.IsNullOrWhiteSpace(cs))
                throw new InvalidOperationException("ConnectionStrings:ChatDb is required");

            o.UseNpgsql(cs, npgsql => npgsql.MigrationsHistoryTable("__EFMigrationsHistory", db.Schema));
        });

        return services;
    }

    public static WebApplication UseChatService(this WebApplication app)
    {
        app.UseDopDocCorrelation();
        app.UseSerilogRequestLogging();
        app.UseDopDocExceptionHandling();

        app.UseSwagger();
        app.UseSwaggerUI(o =>
        {
            o.SwaggerEndpoint("/swagger/v1/swagger.json", "DopDocAI Chat API v1");
        });

        app.MapDopDocHealth();
        app.MapGet("/", () => Results.Ok(new { service = "chat_service", status = "ok" })).AllowAnonymous();
        app.MapChatEndpoints();

        app.Logger.LogInformation("Chat service started. Env={Env}", app.Environment.EnvironmentName);

        return app;
    }
}
