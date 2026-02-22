using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using System.Security.Cryptography;
using System.Text;
using DopDoc.AuthService.Domain;
using Microsoft.Extensions.Options;
using Microsoft.IdentityModel.Tokens;

namespace DopDoc.AuthService.Infrastructure.Security;

public sealed class TokenService
{
    private readonly AuthOptions _options;

    public TokenService(IOptions<AuthOptions> options)
    {
        _options = options.Value;
    }

    public string CreateAccessToken(User user)
    {
        var now = DateTimeOffset.UtcNow;
        var key = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(_options.JwtSecret));
        var creds = new SigningCredentials(key, SecurityAlgorithms.HmacSha256);

        var claims = new List<Claim>
        {
            // JWT standard
            new(JwtRegisteredClaimNames.Sub, user.Id.ToString()),
            new(JwtRegisteredClaimNames.Email, user.Email),

            // .NET standard
            new(ClaimTypes.NameIdentifier, user.Id.ToString()),
            new(ClaimTypes.Email, user.Email),
        };

        var token = new JwtSecurityToken(
            issuer: _options.JwtIssuer,
            audience: _options.JwtAudience,
            claims: claims,
            notBefore: now.UtcDateTime,
            expires: now.AddMinutes(_options.AccessTokenMinutes).UtcDateTime,
            signingCredentials: creds
        );

        return new JwtSecurityTokenHandler().WriteToken(token);
    }

    public (string Plain, string Hash) CreateRefreshToken()
    {
        // 32 bytes random -> base64url
        var bytes = RandomNumberGenerator.GetBytes(32);
        var plain = Base64UrlEncoder.Encode(bytes);
        return (plain, HashRefreshToken(plain));
    }

    public string HashRefreshToken(string refreshTokenPlain)
    {
        // sha256( token + pepper )
        using var sha = SHA256.Create();
        var input = Encoding.UTF8.GetBytes(refreshTokenPlain + _options.RefreshPepper);
        var hash = sha.ComputeHash(input);
        return Convert.ToHexString(hash).ToLowerInvariant();
    }
}