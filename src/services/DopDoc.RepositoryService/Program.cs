using DopDoc.RepositoryService;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddRepositoryService(builder.Configuration);

var app = builder.Build();

app.UseRepositoryService();

app.Run();
