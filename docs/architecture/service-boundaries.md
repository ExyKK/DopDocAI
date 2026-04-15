# DopDocAI Service Boundaries

## Purpose

Этот документ фиксирует целевую архитектурную рамку проекта и служит источником правды для задач `ARCH-001` и всех последующих epics из backlog.

Ключевая цель:

- разделить public API, orchestration, heavy workers и domain ownership;
- убрать зависимость новых сервисов от legacy-контрактов;
- зафиксировать канонические термины, чтобы во всех следующих задачах они использовались одинаково.

## Target Repository Layout

Целевая структура сервисов:

- `src/services/DopDoc.AuthService` — C#
- `src/services/DopDoc.EdgeGateway` — C#
- `src/services/DopDoc.RepositoryService` — C#
- `src/services/DopDoc.ChatService` — C#
- `src/services/ingestion_service` — Python
- `src/services/documentation_service` — Python

Пояснения:

- `ingestion_service` остается Python-сервисом, но должен быть перенесен из `/backend` в `/src/services/ingestion_service`;
- новый `documentation_service` также должен создаваться внутри `/src/services/documentation_service`;
- директория `/backend` рассматривается как временная зона для legacy-кода и должна постепенно опустеть по мере миграции;
- новые сервисы и новые workflow не должны строиться вокруг `/backend` как постоянной корневой директории.

## Canonical Terms

- `repository` — логическая запись о публичном GitHub-репозитории, известном системе.
- `selected_branch` — единственная ветка, с которой система работает для данного repository.
- `snapshot` — неизменяемое состояние repository, привязанное к конкретному `commit_sha`.
- `index_run` — асинхронная задача построения analysis artifacts и vector index для snapshot.
- `documentation_run` — асинхронная задача генерации документации для snapshot и заданного template.
- `artifact` — файл, опубликованный в MinIO и зарегистрированный метаданными в Postgres.
- `chat` — диалог пользователя, жестко привязанный к конкретному snapshot.
- `source` — нормализованная ссылка на фрагмент знания: файл, символ или chunk с координатами.

Эти термины являются обязательными для БД, API-контрактов, логов, observability и backlog-задач.

## Architectural Principles

- `EdgeGateway` является единственной публичной точкой входа.
- Внешний клиент не знает о внутренних деталях хранения, таких как `qdrant_collection`, `repo_index_states`, `payload schema`.
- Все тяжелые операции выполняются как `Postgres-backed jobs + отдельные worker-процессы`.
- Индексация, чат и документация должны быть воспроизводимыми, а значит привязываются к `snapshot_id` и `commit_sha`.
- Поддержка нескольких веток не нужна. Для repository хранится один `selected_branch`.
- Совместимость с legacy API не является целью.
- Новые сервисы не должны передавать `user_id` в body или query string.

## Trust Boundaries

### Public boundary

- браузер и любые внешние клиенты обращаются только к `EdgeGateway`;
- публичные endpoints живут под `/api/v1/...`;
- gateway проверяет JWT и пробрасывает user context дальше внутрь контура.

### Internal boundary

- сервисы внутри docker network общаются между собой по внутренним HTTP endpoints и через Postgres-backed jobs;
- internal endpoints не должны публиковаться наружу через gateway по умолчанию;
- worker-процессы могут читать и обновлять job state напрямую в Postgres, если это часть утвержденного execution model.

### Storage boundary

- Postgres хранит metadata, ownership state, job state, chat history, source references;
- Qdrant хранит только retrieval index;
- MinIO хранит analysis artifacts и documentation artifacts;
- файловые временные каталоги worker-ов считаются ephemeral state.

## User Context Contract

Новая архитектура использует такой contract:

- `Authorization: Bearer <token>` приходит только на gateway;
- gateway извлекает identity из JWT;
- downstream-сервисам пробрасываются `X-User-Id` и `X-User-Email`;
- downstream-сервисы доверяют этим заголовкам только если запрос пришел через внутренний trusted boundary;
- `user_id` не передается в request body;
- `user_id` не передается в query string;
- storage модели могут хранить `user_id` как ownership field, но он никогда не становится частью публичного API.

## Service Responsibilities

## `DopDoc.EdgeGateway`

### Owns

- публичный ingress;
- JWT-authentication на внешней границе;
- проброс `X-User-Id`, `X-User-Email`, `X-Correlation-Id`;
- reverse proxy routing на внутренние сервисы.

### Does not own

- бизнес-логику repository, chat, indexing, documentation;
- хранение domain state;
- orchestration тяжелых jobs.

## `DopDoc.AuthService`

### Owns

- регистрация пользователя;
- login, refresh, logout;
- выпуск access token и refresh token;
- auth schema в Postgres.

### Does not own

- repository metadata;
- chats;
- permissions на уровне доменных сущностей beyond authentication.

## `DopDoc.RepositoryService`

### Owns

- logical repositories;
- association `user <-> repository`;
- snapshots;
- `index_runs` и `documentation_runs` как control plane сущности;
- metadata analysis artifacts и docs artifacts;
- status API и SSE для long-running jobs.

### Responsibilities

- нормализовать GitHub URL и управлять записью repository;
- создавать runs и выдавать `202 Accepted`;
- вести source of truth по статусу, этапам и прогрессу jobs;
- хранить metadata по snapshot и published artifacts;
- предоставлять public API для repository/snapshot/run management.

### Does not own

- embedding и vector index internals;
- непосредственное выполнение parse/embed/generate workload;
- chat history.

## `DopDoc.ChatService`

### Owns

- chats;
- chat messages;
- normalized message sources;
- LLM orchestration для вопрос-ответ по snapshot.

### Responsibilities

- создавать snapshot-bound chats;
- загружать history;
- вызывать retrieval по `snapshot_id`;
- вызывать LLM provider;
- сохранять answer, usage и normalized sources.

### Does not own

- lifecycle indexing jobs;
- lifecycle documentation jobs;
- Qdrant-специфику;
- project analysis artifacts.

## `ingestion_service`

### Owns

- worker execution для `index_runs`;
- clone/checkout repository snapshot;
- file traversal, Go parsing, chunking, embeddings;
- публикацию analysis artifacts в MinIO;
- поддержку retrieval API по `snapshot_id`;
- управление vector index в Qdrant.

### Responsibilities

- claim-ить `index_runs` из Postgres;
- обновлять `lease_until`, `heartbeat_at`, `stage`, `progress`;
- строить `file_inventory.json`, `go_symbols.json`, `package_graph.json`, `config_inventory.json`, `project_model.json`, `commit_log.json`;
- загружать code chunks в Qdrant;
- отдавать normalized retrieval results для chat/docs.

### Does not own

- public API для repository management;
- chat persistence;
- documentation persistence;
- пользовательскую аутентификацию.

## `documentation_service`

### Owns

- worker execution для `documentation_runs`;
- section planning;
- evidence assembly;
- section generation;
- verification;
- публикацию generated documentation artifacts в MinIO.

### Responsibilities

- claim-ить `documentation_runs` из Postgres;
- читать `project_model` и остальные analysis artifacts;
- вызывать retrieval по `snapshot_id`, когда structured artifacts недостаточно;
- генерировать `developer_handbook` и другие templates;
- сохранять section metadata, sources и verification report.

### Does not own

- snapshot creation;
- vector indexing;
- chat lifecycle;
- public repository API.

## Storage Ownership

- `AuthService` владеет только схемой `auth`.
- `RepositoryService` владеет схемой `repo` как доменной моделью repository/snapshot/runs/artifacts.
- `ChatService` владеет схемой `chat`.
- `ingestion_service` является владельцем Qdrant indexing strategy и analysis artifact content.
- `documentation_service` является владельцем generated documentation artifact content.

Допустимое исключение:

- Python worker-ы могут читать и обновлять записи `repo`-схемы, связанные с claim/heartbeat/progress и artifact registration, если это часть согласованного job protocol.

## Main Workflows

## Repository Indexing

1. Клиент отправляет запрос в `EdgeGateway`.
2. `EdgeGateway` аутентифицирует пользователя и проксирует запрос в `RepositoryService`.
3. `RepositoryService` нормализует URL, создает или находит repository, создает `index_run` в статусе `queued`, возвращает `202 Accepted`.
4. `ingestion_service` worker claim-ит `index_run` из Postgres.
5. Worker clone-ит repository, фиксирует `snapshot`, строит analysis artifacts, заливает chunks в Qdrant, публикует artifacts в MinIO.
6. Worker завершает run статусом `succeeded` или `failed`.
7. `RepositoryService` отдает status и SSE события по run.

## Chat

1. Клиент создает chat по repository или конкретному snapshot через `EdgeGateway`.
2. `ChatService` создает snapshot-bound chat.
3. При отправке сообщения `ChatService` получает retrieval results по `snapshot_id`.
4. `ChatService` вызывает LLM и сохраняет answer вместе с normalized sources.

## Documentation Generation

1. Клиент запускает генерацию документации через `RepositoryService`.
2. `RepositoryService` создает `documentation_run` в статусе `queued`.
3. `documentation_service` worker claim-ит job.
4. Worker загружает artifacts для snapshot, собирает evidence pack по section schema, генерирует sections, верифицирует результат и публикует артефакты.
5. `RepositoryService` отдает статус и artifacts metadata.

## Explicit Non-Responsibilities

- `RepositoryService` не должен напрямую читать Qdrant payloads.
- `ChatService` не должен напрямую управлять `index_runs`.
- `documentation_service` не должен строить snapshot заново.
- `ingestion_service` не должен владеть public API для repository listing.
- `EdgeGateway` не должен содержать бизнес-логику beyond auth, proxying и header propagation.

## Legacy Transition Rules

- legacy `backend/repos_service` и `backend/chats_service` не расширяются новыми возможностями;
- для новых use cases используются только новые сервисы;
- legacy директории остаются только как временный reference и подлежат удалению после миграции;
- любые новые документы, compose changes и implementation tasks должны ссылаться на target layout в `/src/services`, а не строиться вокруг `/backend`.

