namespace DopDoc.AuthService.Api.Proxy;

public static class ReverseProxyExtensions
{
    public static IServiceCollection AddDopDocReverseProxy(this IServiceCollection services, IConfiguration config)
    {
        services.AddTransient<UserContextProxyMiddleware>();

        services
            .AddReverseProxy()
            .LoadFromConfig(config.GetSection("ReverseProxy"));

        return services;
    }

    public static IEndpointRouteBuilder MapDopDocReverseProxy(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapReverseProxy(proxyPipeline =>
            {
                proxyPipeline.UseMiddleware<UserContextProxyMiddleware>();
            })
            .RequireAuthorization();

        return endpoints;
    }
}