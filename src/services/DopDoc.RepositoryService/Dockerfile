FROM mcr.microsoft.com/dotnet/sdk:10.0.100 AS build
WORKDIR /src

COPY src/DopDoc.slnx ./DopDoc.slnx
COPY src/common/DopDoc.Common.Hosting/DopDoc.Common.Hosting.csproj common/DopDoc.Common.Hosting/
COPY src/common/DopDoc.Common.Observability/DopDoc.Common.Observability.csproj common/DopDoc.Common.Observability/
COPY src/common/DopDoc.Common.Persistence/DopDoc.Common.Persistence.csproj common/DopDoc.Common.Persistence/
COPY src/services/DopDoc.RepositoryService/DopDoc.RepositoryService.csproj services/DopDoc.RepositoryService/

RUN dotnet restore services/DopDoc.RepositoryService/DopDoc.RepositoryService.csproj

COPY src/common/DopDoc.Common.Hosting/ common/DopDoc.Common.Hosting/
COPY src/common/DopDoc.Common.Observability/ common/DopDoc.Common.Observability/
COPY src/common/DopDoc.Common.Persistence/ common/DopDoc.Common.Persistence/
COPY src/services/DopDoc.RepositoryService/ services/DopDoc.RepositoryService/

RUN dotnet publish services/DopDoc.RepositoryService/DopDoc.RepositoryService.csproj -c Release -o /app/publish

FROM mcr.microsoft.com/dotnet/aspnet:10.0.0
WORKDIR /app
COPY --from=build /app/publish .
ENV ASPNETCORE_URLS=http://0.0.0.0:19200
EXPOSE 19200
ENTRYPOINT ["dotnet", "DopDoc.RepositoryService.dll"]
