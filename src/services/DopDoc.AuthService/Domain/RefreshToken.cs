namespace DopDoc.AuthService.Domain;

public sealed class RefreshToken
{
    public Guid Id { get; set; }
    public Guid UserId { get; set; }
    
    public string TokenHash { get; set; }
    
    public DateTime CreatedAt { get; set; }
    public DateTime ExpiresAt { get; set; }
    public DateTime? RevokedAt { get; set; }
    
    public string? UserAgent { get; set; }
    public string? Ip { get; set; }
}