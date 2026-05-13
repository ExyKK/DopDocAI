using DopDoc.ChatService.Api.Contracts;
using DopDoc.ChatService.Application.Chats;
using DopDoc.Common.UserContext;
using Microsoft.AspNetCore.Mvc;

namespace DopDoc.ChatService.Api;

public static class ChatEndpoints
{
    public static RouteGroupBuilder MapChatEndpoints(this IEndpointRouteBuilder app)
    {
        var g = app.MapGroup("/api/v1/chats").WithTags("chats");

        g.MapPost("", async (
            CreateChatRequest request,
            IUserContextAccessor userContext,
            ChatApplicationService chats,
            CancellationToken ct) =>
        {
            var userId = userContext.GetRequiredUserId();
            var chat = await chats.CreateAsync(userId, ChatContractMapper.ToCommand(request), ct);
            var response = ChatContractMapper.ToResponse(chat);
            return Results.Created($"/api/v1/chats/{response.Id}", response);
        })
        .WithName("CreateChat");

        g.MapGet("", async (
            [FromQuery(Name = "repository_id")] Guid? repositoryId,
            [FromQuery] int? limit,
            [FromQuery] int? offset,
            IUserContextAccessor userContext,
            ChatApplicationService chats,
            CancellationToken ct) =>
        {
            var userId = userContext.GetRequiredUserId();
            var pagination = ChatPagination.Validate(limit, offset);
            var page = await chats.ListAsync(userId, repositoryId, pagination, ct);
            return TypedResults.Ok(ChatContractMapper.ToPagedResponse(page));
        })
        .WithName("ListChats");

        g.MapGet("/{chat_id:guid}", async (
            [FromRoute(Name = "chat_id")] Guid chatId,
            IUserContextAccessor userContext,
            ChatApplicationService chats,
            CancellationToken ct) =>
        {
            var userId = userContext.GetRequiredUserId();
            var chat = await chats.GetAsync(userId, chatId, ct);
            return TypedResults.Ok(ChatContractMapper.ToResponse(chat));
        })
        .WithName("GetChat");

        g.MapGet("/{chat_id:guid}/messages", async (
            [FromRoute(Name = "chat_id")] Guid chatId,
            [FromQuery] int? limit,
            [FromQuery] int? offset,
            IUserContextAccessor userContext,
            ChatApplicationService chats,
            CancellationToken ct) =>
        {
            var userId = userContext.GetRequiredUserId();
            var pagination = ChatPagination.Validate(limit, offset);
            var page = await chats.ListMessagesAsync(userId, chatId, pagination, ct);
            return TypedResults.Ok(ChatContractMapper.ToPagedResponse(page));
        })
        .WithName("ListChatMessages");

        g.MapPost("/{chat_id:guid}/messages", async (
            [FromRoute(Name = "chat_id")] Guid chatId,
            SendChatMessageRequest request,
            IUserContextAccessor userContext,
            ChatApplicationService chats,
            CancellationToken ct) =>
        {
            var userId = userContext.GetRequiredUserId();
            var result = await chats.SendMessageAsync(
                userId,
                chatId,
                ChatContractMapper.ToCommand(request),
                ct);

            return TypedResults.Ok(ChatContractMapper.ToResponse(result));
        })
        .WithName("SendChatMessage");

        return g;
    }
}
