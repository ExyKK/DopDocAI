using System.Text;
using DopDoc.AuthService.Infrastructure.Security;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.IdentityModel.Tokens;

namespace DopDoc.AuthService.Api.Auth;

public static class JwtAuthExtensions
{
    public static IServiceCollection AddDopDocJwtAuth(this IServiceCollection services, IConfiguration config)
    {
        var auth = new AuthOptions();
        config.GetSection("Auth").Bind(auth);
        
        services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
            .AddJwtBearer(o =>
            {
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

        services.AddAuthorization();
        return services;
    }
}