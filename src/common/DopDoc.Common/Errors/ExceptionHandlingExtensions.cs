using System.Diagnostics;
using Microsoft.AspNetCore.Builder;
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

        app.Use(async (context, next) =>
        {
            try
            {
                await next();
            }
            catch (Exception ex)
            {
                var traceId = Activity.Current?.TraceId.ToString() ?? context.TraceIdentifier;

                var correlationId =
                    context.Items.TryGetValue("X-Correlation-Id", out var v) ? v?.ToString() :
                    context.Request.Headers.TryGetValue("X-Correlation-Id", out var hv) ? hv.ToString() :
                    null;

                var pd = BuildProblemDetails(ex, env, traceId, correlationId, out var logLevel);

                if (logLevel == LogLevel.Error)
                    logger.LogError(ex, "{Title}. TraceId={TraceId} CorrelationId={CorrelationId}", pd.Title, traceId, correlationId);
                else if (logLevel == LogLevel.Warning)
                    logger.LogWarning(ex, "{Title}. TraceId={TraceId} CorrelationId={CorrelationId}", pd.Title, traceId, correlationId);
                else
                    logger.LogInformation("{Title}. TraceId={TraceId} CorrelationId={CorrelationId}", pd.Title, traceId, correlationId);
                
                if (context.Response.HasStarted)
                    throw;

                context.Response.Clear();
                context.Response.StatusCode = pd.Status ?? StatusCodes.Status500InternalServerError;
                context.Response.ContentType = "application/problem+json";
                await context.Response.WriteAsJsonAsync(pd);
            }
        });

        return app;
    }

    private static ProblemDetails BuildProblemDetails(
        Exception? ex,
        IHostEnvironment env,
        string traceId,
        string? correlationId,
        out LogLevel logLevel)
    {
        ProblemDetails pd;

        if (ex is DopDocException dd)
        {
            logLevel = dd.StatusCode >= 500 ? LogLevel.Error : LogLevel.Information;
            
            pd = new ProblemDetails
            {
                Title = dd.Title,
                Status = dd.StatusCode,
                Type = dd.Type,
                Detail = dd.Message
            };

            if (!string.IsNullOrWhiteSpace(dd.ErrorCode))
                pd.Extensions["error_code"] = dd.ErrorCode;

            if (dd.Extensions is not null)
            {
                foreach (var (k, v) in dd.Extensions)
                    pd.Extensions[k] = v;
            }
        }
        else if (ex is OperationCanceledException)
        {
            logLevel = LogLevel.Information;
            pd = new ProblemDetails
            {
                Title = "Client closed request",
                Status = 499,
                Type = "about:blank",
                Detail = null
            };
        }
        else
        {
            logLevel = LogLevel.Error;
            pd = new ProblemDetails
            {
                Title = "An unexpected error occurred",
                Status = StatusCodes.Status500InternalServerError,
                Type = "https://httpstatuses.com/500",
                Detail = env.IsDevelopment() ? ex?.ToString() : null
            };
        }

        pd.Extensions["trace_id"] = traceId;
        if (!string.IsNullOrWhiteSpace(correlationId))
            pd.Extensions["correlation_id"] = correlationId;

        return pd;
    }
}