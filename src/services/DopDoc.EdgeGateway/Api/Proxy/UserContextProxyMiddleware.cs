using System.Security.Claims;
using DopDoc.Common.Correlation;
using Microsoft.Extensions.Options;

namespace DopDoc.EdgeGateway.Api.Proxy;

public sealed class UserContextProxyMiddleware : IMiddleware
{
    private readonly CorrelationOptions _correlationOptions;

    public UserContextProxyMiddleware(IOptions<CorrelationOptions> correlationOptions)
    {
        _correlationOptions = correlationOptions.Value;
    }

    public Task InvokeAsync(HttpContext context, RequestDelegate next)
    {
        ForwardCorrelationId(context);
        ForwardUserContext(context);

        return next(context);
    }

    private void ForwardCorrelationId(HttpContext context)
    {
        var headerName = _correlationOptions.HeaderName;
        if (context.Items.TryGetValue(headerName, out var correlationObj) &&
            correlationObj is string correlationId &&
            !string.IsNullOrWhiteSpace(correlationId))
        {
            context.Request.Headers[headerName] = correlationId;
        }
    }

    private static void ForwardUserContext(HttpContext context)
    {
        if (context.User.Identity?.IsAuthenticated is not true)
            return;

        var userId = context.User.FindFirstValue(ClaimTypes.NameIdentifier)
                     ?? context.User.FindFirstValue("sub");
        var email = context.User.FindFirstValue(ClaimTypes.Email)
                    ?? context.User.FindFirstValue("email");

        if (!string.IsNullOrWhiteSpace(userId))
            context.Request.Headers[ProxyUserHeaders.UserId] = userId;

        if (!string.IsNullOrWhiteSpace(email))
            context.Request.Headers[ProxyUserHeaders.UserEmail] = email;
    }
}
