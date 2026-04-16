using DopDoc.ChatService;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddChatService(builder.Configuration);

var app = builder.Build();

app.UseChatService();

app.Run();
