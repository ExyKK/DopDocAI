using DopDoc.ChatService.Application.Snapshots;
using DopDoc.ChatService.Domain;
using DopDoc.ChatService.Infrastructure.Clients;
using DopDoc.ChatService.Infrastructure.Data;
using DopDoc.Common.Errors;
using Microsoft.EntityFrameworkCore;

namespace DopDoc.ChatService.Application.Chats;

public sealed class ChatCrudService
{
    private readonly ChatDbContext _db;
    private readonly RepositoryServiceClient _repositories;

    public ChatCrudService(ChatDbContext db, RepositoryServiceClient repositories)
    {
        _db = db;
        _repositories = repositories;
    }

    public async Task<Chat> CreateAsync(Guid userId, CreateChatCommand command, CancellationToken ct)
    {
        ValidateCreateCommand(command);

        ReadySnapshotRef snapshot = await _repositories.GetReadySnapshotAsync(
            userId,
            command.RepositoryId,
            command.SnapshotId,
            ct);

        var now = DateTimeOffset.UtcNow;
        var chat = new Chat
        {
            Id = Guid.NewGuid(),
            RepositoryId = snapshot.RepositoryId,
            SnapshotId = snapshot.SnapshotId,
            UserId = userId,
            Title = NormalizeTitle(command.Title),
            CreatedAt = now,
            UpdatedAt = now
        };

        _db.Chats.Add(chat);
        await _db.SaveChangesAsync(ct);

        return chat;
    }

    public async Task<PagedChatResult> ListAsync(
        Guid userId,
        Guid? repositoryId,
        ChatPagination pagination,
        CancellationToken ct)
    {
        var query = _db.Chats
            .AsNoTracking()
            .Where(x => x.UserId == userId && x.ArchivedAt == null);

        if (repositoryId is not null)
            query = query.Where(x => x.RepositoryId == repositoryId.Value);

        var total = await query.CountAsync(ct);
        var items = await query
            .OrderByDescending(x => x.LastMessageAt ?? x.CreatedAt)
            .ThenByDescending(x => x.CreatedAt)
            .Skip(pagination.Offset)
            .Take(pagination.Limit)
            .ToListAsync(ct);

        return new PagedChatResult(items, total, pagination.Limit, pagination.Offset);
    }

    public async Task<Chat> GetAsync(Guid userId, Guid chatId, CancellationToken ct)
    {
        var chat = await _db.Chats
            .AsNoTracking()
            .FirstOrDefaultAsync(x => x.Id == chatId && x.UserId == userId && x.ArchivedAt == null, ct);

        return chat ?? throw ChatErrors.NotFound(chatId);
    }

    public async Task<PagedChatMessageResult> ListMessagesAsync(
        Guid userId,
        Guid chatId,
        ChatPagination pagination,
        CancellationToken ct)
    {
        await EnsureChatExistsAsync(userId, chatId, ct);

        var query = _db.ChatMessages
            .AsNoTracking()
            .Where(x => x.ChatId == chatId);

        var total = await query.CountAsync(ct);
        var items = await query
            .Include(x => x.Sources.OrderBy(s => s.Ordinal))
            .OrderBy(x => x.CreatedAt)
            .Skip(pagination.Offset)
            .Take(pagination.Limit)
            .ToListAsync(ct);

        return new PagedChatMessageResult(items, total, pagination.Limit, pagination.Offset);
    }

    private async Task EnsureChatExistsAsync(Guid userId, Guid chatId, CancellationToken ct)
    {
        var exists = await _db.Chats
            .AsNoTracking()
            .AnyAsync(x => x.Id == chatId && x.UserId == userId && x.ArchivedAt == null, ct);

        if (!exists)
            throw ChatErrors.NotFound(chatId);
    }

    private static void ValidateCreateCommand(CreateChatCommand command)
    {
        if (command.RepositoryId == Guid.Empty)
            throw new ValidationException("repository_id is required", errorCode: "repository_id_required");

        if (command.SnapshotId == Guid.Empty)
            throw new ValidationException("snapshot_id is invalid", errorCode: "snapshot_id_invalid");

        if (NormalizeTitle(command.Title) is { Length: > 512 })
            throw new ValidationException("title is too long", errorCode: "chat_title_too_long");
    }

    private static string? NormalizeTitle(string? title)
    {
        return string.IsNullOrWhiteSpace(title) ? null : title.Trim();
    }
}
