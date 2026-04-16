namespace DopDoc.Common.UserContext;

public interface IUserContextAccessor
{
    CurrentUserContext? CurrentUser { get; }
    Guid? UserId { get; }
    string? UserEmail { get; }
    Guid GetRequiredUserId();
}
