using System.Data;
using DopDoc.AuthService.Domain;
using DopDoc.AuthService.Infrastructure.Data;
using DopDoc.AuthService.Infrastructure.Security;
using DopDoc.Common.Errors;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;
using Npgsql;

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
        if (string.IsNullOrWhiteSpace(email))
            throw new ValidationException("Email is required", errorCode: "email_required");

        if (string.IsNullOrWhiteSpace(password))
            throw new ValidationException("Password is required", errorCode: "password_required");

        email = email.Trim().ToLowerInvariant();

        if (email.Length < 3)
            throw new ValidationException("Invalid email", errorCode: "email_invalid");

        if (password.Length < 8)
            throw new ValidationException("Password too short (min 8)", errorCode: "password_too_short",
                extensions: new Dictionary<string, object?> { ["min_length"] = 8 });

        if (await _db.Users.AnyAsync(x => x.Email == email, ct))
            throw new ConflictException("Email already registered", errorCode: "email_already_registered");

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
        if (string.IsNullOrWhiteSpace(email) || string.IsNullOrWhiteSpace(password))
            throw new ValidationException("Email and password are required", errorCode: "credentials_required");

        email = email.Trim().ToLowerInvariant();

        var user = await _db.Users.FirstOrDefaultAsync(x => x.Email == email, ct);
        if (user is null || !user.IsActive)
            throw new UnauthorizedException();

        if (!BCrypt.Net.BCrypt.Verify(password, user.PasswordHash))
            throw new UnauthorizedException();

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

        return new AuthResult(access, plainRefresh, _options.AccessTokenMinutes * 60, user.Id, user.Email);
    }

    public async Task<AuthResult> RefreshAsync(string refreshTokenPlain, string? userAgent, string? ip, CancellationToken ct)
    {
        if (string.IsNullOrWhiteSpace(refreshTokenPlain))
            throw new ValidationException("Missing refresh token", errorCode: "refresh_token_missing");

        var hash = _tokens.HashRefreshToken(refreshTokenPlain);

        await using var tx = await _db.Database.BeginTransactionAsync(IsolationLevel.Serializable, ct);

        try
        {
            var sql = $"SELECT * FROM \"{_db.Schema}\".\"refresh_tokens\" WHERE \"TokenHash\" = {{0}} FOR UPDATE";
            var rt = await _db.RefreshTokens.FromSqlRaw(sql, hash).SingleOrDefaultAsync(ct);
            if (rt is null || rt.RevokedAt is not null || rt.ExpiresAt <= DateTime.UtcNow)
                throw new UnauthorizedException();

            var user = await _db.Users.FirstOrDefaultAsync(x => x.Id == rt.UserId, ct);
            if (user is null || !user.IsActive)
                throw new UnauthorizedException();

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
            await tx.CommitAsync(ct);

            return new AuthResult(access, newPlain, _options.AccessTokenMinutes * 60, user.Id, user.Email);
        }
        catch (PostgresException ex) when (ex.SqlState == PostgresErrorCodes.SerializationFailure)
        {
            await tx.RollbackAsync(CancellationToken.None);
            throw new UnauthorizedException();
        }
    }

    public async Task LogoutAsync(string refreshTokenPlain, CancellationToken ct)
    {
        if (string.IsNullOrWhiteSpace(refreshTokenPlain))
            return;

        var hash = _tokens.HashRefreshToken(refreshTokenPlain);
        var rt = await _db.RefreshTokens.FirstOrDefaultAsync(x => x.TokenHash == hash, ct);

        if (rt is not null && rt.RevokedAt is null)
        {
            rt.RevokedAt = DateTime.UtcNow;
            await _db.SaveChangesAsync(ct);
        }
    }
}
