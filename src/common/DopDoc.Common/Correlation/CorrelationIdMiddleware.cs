using System.Diagnostics;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Options;
using Serilog.Context;

namespace DopDoc.Common.Correlation;

public sealed class CorrelationIdMiddleware : IMiddleware
{
    private readonly CorrelationOptions _options;

    public CorrelationIdMiddleware(IOptions<CorrelationOptions> options)
    {
        _options = options.Value;
    }

    public async Task InvokeAsync(HttpContext context, RequestDelegate next)
    {
        var headerName = _options.HeaderName;

        var incoming = context.Request.Headers.TryGetValue(headerName, out var values)
            ? values.ToString()
            : null;

        var correlationId = !string.IsNullOrWhiteSpace(incoming)
            ? incoming.Trim()
            : CreateCorrelationId();

        // response header
        context.Response.OnStarting(() =>
        {
            context.Response.Headers[headerName] = correlationId;
            return Task.CompletedTask;
        });

        // HttpContext items for downstream access
        context.Items[headerName] = correlationId;

        // Serilog enrichment
        using (LogContext.PushProperty("correlation_id", correlationId))
        using (LogContext.PushProperty("trace_id", Activity.Current?.TraceId.ToString()))
        using (LogContext.PushProperty("span_id", Activity.Current?.SpanId.ToString()))
        {
            // Add to Activity (Tempo search / tags)
            var act = Activity.Current;
            if (act is not null)
            {
                act.SetTag("correlation_id", correlationId);
                act.AddBaggage("correlation_id", correlationId);
            }

            await next(context);
        }
    }

    private string CreateCorrelationId()
    {
        if (_options.UseTraceIdAsCorrelationId && Activity.Current is not null)
            return Activity.Current.TraceId.ToString();

        // “человеческий” формат: 32 hex
        return Guid.NewGuid().ToString("N");
    }
}