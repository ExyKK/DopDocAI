using System.Text;
using DopDoc.EdgeGateway.Infrastructure.Security;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.Extensions.Options;
using Microsoft.IdentityModel.Tokens;

namespace DopDoc.EdgeGateway.Api.Auth;

public static class GatewayJwtAuthExtensions
{
    public const string AuthenticatedPolicy = "gateway.authenticated";

    public static IServiceCollection AddDopDocGatewayJwtAuth(this IServiceCollection services)
    {
        services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
            .AddJwtBearer();

        services.AddOptions<JwtBearerOptions>(JwtBearerDefaults.AuthenticationScheme)
            .Configure<IOptions<GatewayAuthOptions>>((o, authOptions) =>
            {
                var auth = authOptions.Value;

                o.TokenValidationParameters = new TokenValidationParameters
                {
                    ValidateIssuer = true,
                    ValidIssuer = auth.JwtIssuer,

                    ValidateAudience = true,
                    ValidAudience = auth.JwtAudience,

                    ValidateIssuerSigningKey = true,
                    IssuerSigningKey = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(auth.JwtSecret)),

                    ValidateLifetime = true,
                    ClockSkew = TimeSpan.FromSeconds(30),
                };
            });

        services.AddAuthorization(options =>
        {
            options.AddPolicy(AuthenticatedPolicy, policy => policy.RequireAuthenticatedUser());
        });

        return services;
    }
}
