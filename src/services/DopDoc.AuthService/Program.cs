using DopDoc.AuthService;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddAuthService(builder.Configuration);

var app = builder.Build();

app.UseAuthService();

app.Run();
