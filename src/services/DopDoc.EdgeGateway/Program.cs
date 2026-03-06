using DopDoc.EdgeGateway;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddEdgeGateway(builder.Configuration);

var app = builder.Build();

app.UseEdgeGateway();

app.Run();
