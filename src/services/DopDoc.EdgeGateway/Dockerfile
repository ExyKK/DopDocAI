# build
FROM mcr.microsoft.com/dotnet/sdk:10.0.100 AS build
WORKDIR /src

COPY src/DopDoc.slnx ./DopDoc.slnx
COPY src/common/DopDoc.Common.Hosting/DopDoc.Common.Hosting.csproj common/DopDoc.Common.Hosting/
COPY src/common/DopDoc.Common.Observability/DopDoc.Common.Observability.csproj common/DopDoc.Common.Observability/
COPY src/services/DopDoc.EdgeGateway/DopDoc.EdgeGateway.csproj services/DopDoc.EdgeGateway/

RUN dotnet restore services/DopDoc.EdgeGateway/DopDoc.EdgeGateway.csproj

COPY src/common/DopDoc.Common.Hosting/ common/DopDoc.Common.Hosting/
COPY src/common/DopDoc.Common.Observability/ common/DopDoc.Common.Observability/
COPY src/services/DopDoc.EdgeGateway/ services/DopDoc.EdgeGateway/

RUN dotnet publish services/DopDoc.EdgeGateway/DopDoc.EdgeGateway.csproj -c Release -o /app/publish

# runtime
FROM mcr.microsoft.com/dotnet/aspnet:10.0.0
WORKDIR /app
COPY --from=build /app/publish .
ENV ASPNETCORE_URLS=http://0.0.0.0:18000
EXPOSE 18000
ENTRYPOINT ["dotnet", "DopDoc.EdgeGateway.dll"]
