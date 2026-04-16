using DopDoc.ChatService.Api;
using DopDoc.Common.Correlation;
using DopDoc.Common.Errors;
using DopDoc.Common.Health;
using DopDoc.Common.Logging;
using DopDoc.Common.Observability;
using DopDoc.Common.UserContext;
using Microsoft.OpenApi;
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
