using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;

namespace DopDoc.Common.Correlation;

public static class CorrelationExtensions
{
    public static IServiceCollection AddDopDocCorrelation(
        this IServiceCollection services,
        IConfiguration config)
    {
        services.AddOptions<CorrelationOptions>()
            .Bind(config.GetSection("Correlation"))
            .ValidateOnStart();

        services.AddTransient<CorrelationIdMiddleware>();
        return services;
    }

    public static IApplicationBuilder UseDopDocCorrelation(this IApplicationBuilder app)
    {
        return app.UseMiddleware<CorrelationIdMiddleware>();
    }
}