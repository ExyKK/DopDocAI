using DopDoc.AuthService.Domain;
using DopDoc.AuthService.Infrastructure.Data;
using DopDoc.AuthService.Infrastructure.Security;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;

namespace DopDoc.AuthService.Application.Auth;

public sealed class AuthApplicationService
{
    private readonly AuthDbContext _db;
    private readonly TokenService _tokens;
    private readonly AuthOptions _options;

    public AuthApplicationService(AuthDbContext db, TokenService tokens, IOptions<AuthOptions> options)
    {
        _db = db;
        _tokens = tokens;
        _options = options.Value;
    }

    public async Task<Guid> RegisterAsync(string email, string password, CancellationToken ct)
    {
        email = email.Trim().ToLowerInvariant();

        if (email.Length < 3) throw new ArgumentException("Invalid email");
        if (password.Length < 8) throw new ArgumentException("Password too short (min 8)");

        if (await _db.Users.AnyAsync(x => x.Email == email, ct))
            throw new InvalidOperationException("Email already registered");

        var user = new User
        {
            Email = email,
            PasswordHash = BCrypt.Net.BCrypt.HashPassword(password),
            IsActive = true,
            CreatedAt = DateTime.UtcNow
        };

        _db.Users.Add(user);
        await _db.SaveChangesAsync(ct);

        return user.Id;
    }

    public async Task<AuthResult> LoginAsync(string email, string password, string? userAgent, string? ip, CancellationToken ct)
    {
        email = email.Trim().ToLowerInvariant();

        var user = await _db.Users.FirstOrDefaultAsync(x => x.Email == email, ct);
        if (user is null || !user.IsActive) 
            throw new UnauthorizedAccessException();
        if (!BCrypt.Net.BCrypt.Verify(password, user.PasswordHash))
            throw new UnauthorizedAccessException();

        user.LastLoginAt = DateTime.UtcNow;

        var access = _tokens.CreateAccessToken(user);
        var (plainRefresh, hashRefresh) = _tokens.CreateRefreshToken();

        _db.RefreshTokens.Add(new RefreshToken
        {
            UserId = user.Id,
            TokenHash = hashRefresh,
            CreatedAt = DateTime.UtcNow,
            ExpiresAt = DateTime.UtcNow.AddDays(_options.RefreshTokenDays),
            UserAgent = userAgent,
            Ip = ip
        });

        await _db.SaveChangesAsync(ct);

        return new AuthResult(access, plainRefresh, _options.AccessTokenMinutes * 60);
    }

    public async Task<AuthResult> RefreshAsync(string refreshTokenPlain, string? userAgent, string? ip, CancellationToken ct)
    {
        var hash = _tokens.HashRefreshToken(refreshTokenPlain);

        var rt = await _db.RefreshTokens.FirstOrDefaultAsync(x => x.TokenHash == hash, ct);
        if (rt is null || rt.RevokedAt is not null || rt.ExpiresAt <= DateTime.UtcNow)
            throw new UnauthorizedAccessException();

        var user = await _db.Users.FirstOrDefaultAsync(x => x.Id == rt.UserId, ct);
        if (user is null || !user.IsActive) 
            throw new UnauthorizedAccessException();

        // rotate
        rt.RevokedAt = DateTime.UtcNow;

        var access = _tokens.CreateAccessToken(user);
        var (newPlain, newHash) = _tokens.CreateRefreshToken();

        _db.RefreshTokens.Add(new RefreshToken
        {
            UserId = user.Id,
            TokenHash = newHash,
            CreatedAt = DateTime.UtcNow,
            ExpiresAt = DateTime.UtcNow.AddDays(_options.RefreshTokenDays),
            UserAgent = userAgent,
            Ip = ip
        });

        await _db.SaveChangesAsync(ct);

        return new AuthResult(access, newPlain, _options.AccessTokenMinutes * 60);
    }

    public async Task LogoutAsync(string refreshTokenPlain, CancellationToken ct)
    {
        var hash = _tokens.HashRefreshToken(refreshTokenPlain);
        var rt = await _db.RefreshTokens.FirstOrDefaultAsync(x => x.TokenHash == hash, ct);
        if (rt is not null && rt.RevokedAt is null)
        {
            rt.RevokedAt = DateTime.UtcNow;
            await _db.SaveChangesAsync(ct);
        }
    }
}