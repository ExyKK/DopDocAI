using DopDoc.AuthService.Api;
using DopDoc.AuthService.Api.Auth;
using DopDoc.AuthService.Api.Proxy;
using DopDoc.AuthService.Application.Auth;
using DopDoc.AuthService.Infrastructure.Data;
using DopDoc.AuthService.Infrastructure.Security;
using DopDoc.Common.Configuration;
using DopDoc.Common.Correlation;
using DopDoc.Common.Errors;
using DopDoc.Common.Health;
using DopDoc.Common.Logging;
using DopDoc.Common.Observability;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;
using Microsoft.OpenApi;
using Serilog;

namespace DopDoc.AuthService;

public static class AuthServiceSetup
{
    public static IServiceCollection AddAuthService(this IServiceCollection services, IConfiguration config)
    {
        var serviceName = config["Otel:ServiceName"] ?? "auth_service";

        // Serilog bootstrap
        SerilogSetup.ConfigureBootstrapLogger(serviceName, config);

        services.AddSerilog(lc => lc
            .ReadFrom.Configuration(config)
            .Enrich.FromLogContext()
        );

        // Options + domain/services
        services.AddOptions<AuthOptions>()
            .Bind(config.GetSection("Auth"))
            .Validate(o => !string.IsNullOrWhiteSpace(o.JwtSecret) && o.JwtSecret.Length >= 32,
                "Auth:JwtSecret must be set and at least 32 chars.")
            .Validate(o => !string.IsNullOrWhiteSpace(o.RefreshPepper) && o.RefreshPepper.Length >= 32,
                "Auth:RefreshPepper must be set and at least 32 chars.")
            .ValidateOnStart();

        services.AddSingleton<TokenService>();
        services.AddScoped<AuthApplicationService>();

        // Db
        services.AddOptions<DbOptions>()
            .Bind(config.GetSection("Db"))
            .ValidateOnStart();

        services.AddDbContext<AuthDbContext>((sp, o) =>
        {
            var cfg = sp.GetRequiredService<IConfiguration>();
            var db = sp.GetRequiredService<IOptions<DbOptions>>().Value;

            var cs = cfg.GetConnectionString("AuthDb");
            if (string.IsNullOrWhiteSpace(cs))
                throw new InvalidOperationException("ConnectionStrings:AuthDb is required");

            o.UseNpgsql(cs, npgsql => npgsql.MigrationsHistoryTable("__EFMigrationsHistory", db.Schema));
        });

        // Swagger
        services.AddEndpointsApiExplorer();
        services.AddSwaggerGen(o =>
        {
            o.SwaggerDoc("v1", new OpenApiInfo
            {
                Title = "DopDocAI Auth API",
                Version = "v1"
            });
        });

        // Common infra
        services.AddDopDocProblemDetails();
        services.AddDopDocHealth(config);
        services.AddDopDocOpenTelemetry(config);
        services.AddDopDocCorrelation(config);

        // Auth + Reverse Proxy
        services.AddDopDocJwtAuth(config);
        services.AddDopDocReverseProxy(config);

        return services;
    }

    public static WebApplication UseAuthService(this WebApplication app)
    {
        // Middleware
        app.UseDopDocCorrelation();
        app.UseSerilogRequestLogging();
        app.UseDopDocExceptionHandling();

        // Swagger
        app.UseSwagger();
        app.UseSwaggerUI(o =>
        {
            o.SwaggerEndpoint("/swagger/v1/swagger.json", "DopDocAI Auth API v1");
        });

        // Endpoints
        app.MapDopDocHealth();
        app.MapAuthEndpoints().AllowAnonymous();
        app.MapDopDocReverseProxy();

        app.Logger.LogInformation("Auth service started. Env={Env}", app.Environment.EnvironmentName);

        return app;
    }
}