using System.Diagnostics;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Diagnostics;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

namespace DopDoc.Common.Errors;

public static class ExceptionHandlingExtensions
{
    public static IServiceCollection AddDopDocProblemDetails(this IServiceCollection services)
    {
        services.AddProblemDetails();
        return services;
    }

    public static IApplicationBuilder UseDopDocExceptionHandling(this IApplicationBuilder app)
    {
        var env = app.ApplicationServices.GetRequiredService<IHostEnvironment>();
        var logger = app.ApplicationServices.GetRequiredService<ILoggerFactory>().CreateLogger("DopDoc.ExceptionHandling");

        app.UseExceptionHandler(errorApp =>
        {
            errorApp.Run(async context =>
            {
                var ex = context.Features.Get<IExceptionHandlerFeature>()?.Error;

                var traceId = Activity.Current?.TraceId.ToString() ?? context.TraceIdentifier;

                // correlation_id кладём middleware-ом, но на всякий случай читаем из Items/Headers
                var correlationId =
                    context.Items.TryGetValue("X-Correlation-Id", out var v) ? v?.ToString() :
                    context.Request.Headers.TryGetValue("X-Correlation-Id", out var hv) ? hv.ToString() :
                    null;

                if (ex is not null)
                {
                    logger.LogError(ex,
                        "Unhandled exception. TraceId={TraceId} CorrelationId={CorrelationId}",
                        traceId, correlationId);
                }

                var pd = new ProblemDetails
                {
                    Title = "An unexpected error occurred",
                    Status = StatusCodes.Status500InternalServerError,
                    Type = "https://httpstatuses.com/500",
                    Detail = env.IsDevelopment() ? ex?.ToString() : null
                };

                pd.Extensions["trace_id"] = traceId;
                if (!string.IsNullOrWhiteSpace(correlationId))
                    pd.Extensions["correlation_id"] = correlationId;

                context.Response.StatusCode = pd.Status.Value;
                context.Response.ContentType = "application/problem+json";
                await context.Response.WriteAsJsonAsync(pd);
            });
        });

        return app;
    }
}