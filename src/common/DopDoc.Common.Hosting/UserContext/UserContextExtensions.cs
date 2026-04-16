using Microsoft.Extensions.DependencyInjection;

namespace DopDoc.Common.UserContext;

public static class UserContextExtensions
{
    public static IServiceCollection AddDopDocUserContext(this IServiceCollection services)
    {
        services.AddHttpContextAccessor();
        services.AddScoped<IUserContextAccessor, HeaderUserContextAccessor>();
        return services;
    }
}
