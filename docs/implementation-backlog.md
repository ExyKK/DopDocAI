# DopDocAI Implementation Backlog

Этот backlog фиксирует целевую последовательность работ для перевода проекта в production-ready состояние с новой архитектурой:

- `AuthService` и `EdgeGateway` остаются на C#.
- `RepositoryService` и `ChatService` реализуются на C#.
- `ingestion_service` остается на Python и превращается в worker + retrieval service.
- `documentation_service` реализуется на Python.
- Тяжелые процессы строятся через `Postgres-backed jobs + отдельные worker-процессы`.
- Legacy-сервисы в `backend/repos_service` и `backend/chats_service` считаются временными и не развиваются.

## Priorities

- `P0` — блокирует основную архитектуру и старт имплементации.
- `P1` — нужен для основного end-to-end use case.
- `P2` — улучшение качества, UX и эксплуатации.

## Execution Order

Работы лучше выполнять в таком порядке:

1. `ARCH-*`, `DATA-*`, `PLATFORM-*`
2. `REPO-*`
3. `JOBS-*`
4. `INGEST-*`, `RAG-*`
5. `CHAT-*`
6. `DOCS-*`
7. `GATEWAY-*`, `FRONT-*`
8. `OBS-*`, `TEST-*`, `OPS-*`, `LEGACY-*`

## Definition Of Done

Каждая задача считается завершенной, если:

- код вмержен в основную ветку;
- есть минимальные automated tests для измененного поведения;
- есть observability: logs + базовые metrics/traces для нового потока;
- обновлены compose/configuration и локальный сценарий запуска;
- API-контракты и payload schema зафиксированы в коде и документации.

## Epic ARCH — Architecture Freeze

### ARCH-001 — Зафиксировать service boundaries
- Priority: `P0`
- Depends on: none
- Status: `completed`
- Artifact: [Service Boundaries](./architecture/service-boundaries.md)
- Goal: формально закрепить финальный набор сервисов и зоны ответственности.
- Tasks:
- описать роли `RepositoryService`, `ChatService`, `ingestion_service`, `documentation_service`;
- зафиксировать, что `EdgeGateway` — единственная публичная точка входа;
- зафиксировать, что `user_id` больше не передается в body/query, а берется из `X-User-Id`;
- зафиксировать, что индексация и документация привязаны к `snapshot_id` и `commit_sha`.
- Acceptance:
- есть документ с service boundaries;
- все дальнейшие задачи backlog опираются на одни и те же термины: `repository`, `snapshot`, `index_run`, `documentation_run`.

### ARCH-002 — Зафиксировать API style guide
- Priority: `P0`
- Depends on: `ARCH-001`
- Status: `completed`
- Artifact: [API Style Guide](./architecture/api-style-guide.md)
- Goal: не допустить размытия контрактов между новыми сервисами.
- Tasks:
- зафиксировать naming conventions для endpoints и DTO;
- определить общие правила ответа для `202 Accepted`, ошибок, SSE, paginated list;
- определить стандарт для correlation id и user context headers;
- определить внутренние vs внешние endpoints.
- Acceptance:
- есть единый style guide для REST/SSE контрактов;
- новые сервисы используют одинаковый формат ошибок и status payload.

## Epic DATA — PostgreSQL Schema And Persistence

### DATA-001 — Создать новую схему `repo`
- Priority: `P0`
- Depends on: `ARCH-001`
- Goal: вынести новую доменную модель репозиториев, snapshot, jobs и документации в отдельную схему.
- Tasks:
- создать проект `DopDoc.RepositoryService`;
- добавить `DbContext` и первую миграцию;
- создать таблицы `repositories`, `user_repositories`, `repository_snapshots`, `index_runs`, `index_run_events`, `analysis_artifacts`, `documentation_runs`, `documentation_sections`, `documentation_section_sources`, `documentation_artifacts`;
- создать индексы и unique constraints.
- Acceptance:
- миграция поднимается локально на чистой БД;
- схема не зависит от legacy `repos_service`.

### DATA-002 — Создать новую схему `chat`
- Priority: `P0`
- Depends on: `ARCH-001`
- Goal: отделить chat persistence от legacy Python сервиса.
- Tasks:
- создать таблицы `chats`, `chat_messages`, `chat_message_sources`;
- поддержать привязку `chat -> repository_id + snapshot_id`;
- предусмотреть поля для usage и retrieval metadata.
- Acceptance:
- миграция поднимается локально;
- один chat может быть надежно привязан к конкретному snapshot.

### DATA-003 — Зафиксировать индексы и concurrency constraints
- Priority: `P0`
- Depends on: `DATA-001`, `DATA-002`
- Goal: исключить дубликаты snapshot и конфликтующие активные jobs.
- Tasks:
- сделать `unique(repository_id, commit_sha)` для snapshot;
- сделать partial unique index на активный `index_run` по `repository_id`;
- сделать partial unique index на активный `documentation_run` по `repository_id + snapshot_id + template_kind`;
- добавить индексы для claim-loop jobs по `status`, `lease_until`, `created_at`.
- Acceptance:
- конкурентный запуск одинаковых работ не создает логических дублей;
- claim-loop может выбирать задачи без full scan.

### DATA-004 — Зафиксировать retention strategy
- Priority: `P1`
- Depends on: `DATA-001`
- Goal: заранее определить, что удаляется, а что хранится долго.
- Tasks:
- определить retention для `index_run_events`;
- определить политику хранения старых `documentation_runs`;
- определить soft-delete/archiving для `repositories` и `chats`;
- определить стратегию cleanup orphaned MinIO artifacts.
- Acceptance:
- есть документированная retention policy;
- схема не требует срочного рефакторинга после появления первых данных.

## Epic PLATFORM — Common .NET Foundation

### PLATFORM-001 — Подготовить solution под новые сервисы
- Priority: `P0`
- Depends on: `ARCH-001`
- Goal: добавить в `src` новые сервисы и общие зависимости.
- Tasks:
- добавить `DopDoc.RepositoryService` и `DopDoc.ChatService` в solution;
- подключить общие проекты `DopDoc.Common.Hosting`, `DopDoc.Common.Observability`, `DopDoc.Common.Persistence`;
- настроить `appsettings`, Dockerfile, health checks и bootstrap logging.
- Acceptance:
- сервисы собираются и стартуют пустыми;
- оба сервиса видны в compose.

### PLATFORM-002 — Вынести общий user context abstraction
- Priority: `P0`
- Depends on: `PLATFORM-001`
- Goal: унифицировать чтение `X-User-Id` и correlation headers.
- Tasks:
- создать reusable helper/abstraction для доступа к user context;
- использовать его в `RepositoryService` и `ChatService`;
- убрать потребность в `user_id` в request body/query.
- Acceptance:
- новые сервисы получают user id только из headers;
- публичные DTO не содержат `user_id`.

### PLATFORM-003 — Вынести typed clients для internal HTTP
- Priority: `P1`
- Depends on: `PLATFORM-001`
- Goal: не плодить ad-hoc HTTP вызовы между сервисами.
- Tasks:
- создать typed clients для вызовов `ingestion_service`, `documentation_service`, `RepositoryService`;
- добавить timeout, retry policy, correlation header propagation;
- покрыть клиенты contract tests.
- Acceptance:
- межсервисные HTTP вызовы типизированы и централизованы.

## Epic REPO — RepositoryService

### REPO-001 — Поднять минимальный `RepositoryService`
- Priority: `P0`
- Depends on: `DATA-001`, `PLATFORM-001`, `PLATFORM-002`
- Goal: сервис должен стартовать, применять миграции и отдавать health/swagger.
- Tasks:
- создать setup по аналогии с AuthService;
- подключить EF Core, migrations, problem details, auth, observability;
- настроить compose/env variables.
- Acceptance:
- сервис стартует локально;
- `/health/live`, `/health/ready`, swagger и auth работают.

### REPO-002 — Реализовать CRUD модели `repository`
- Priority: `P0`
- Depends on: `REPO-001`
- Goal: дать пользователю возможность зарегистрировать и просматривать репозитории.
- Tasks:
- реализовать `POST /repositories/index` как входную точку индексации;
- реализовать `GET /repositories`, `GET /repositories/{id}`;
- реализовать нормализацию GitHub URL;
- реализовать привязку `user_repositories`.
- Acceptance:
- пользователь может добавить публичный GitHub URL и увидеть его в списке;
- URL одного и того же репозитория не дублируется логически.

### REPO-003 — Реализовать `snapshot` lifecycle
- Priority: `P0`
- Depends on: `REPO-002`
- Goal: RepositoryService должен знать, какой snapshot активный и какие уже существуют.
- Tasks:
- реализовать сохранение snapshot metadata;
- реализовать `GET /repositories/{id}/snapshots`;
- реализовать выбор `active_snapshot_id`;
- реализовать lookup "есть ли уже готовый snapshot для данного commit_sha".
- Acceptance:
- repository может иметь историю snapshot;
- повторная индексация того же commit не создает второй ready snapshot без необходимости.

### REPO-004 — Реализовать index/documentation run API
- Priority: `P0`
- Depends on: `REPO-003`, `JOBS-001`
- Goal: RepositoryService становится control plane для heavy jobs.
- Tasks:
- реализовать `POST /repositories/index`;
- реализовать `GET /index-runs/{id}`;
- реализовать `POST /repositories/{id}/documentation`;
- реализовать `GET /documentation-runs/{id}`;
- реализовать DTO статусов, этапов и progress.
- Acceptance:
- API умеет создавать runs и возвращать актуальный status/progress;
- UI/clients больше не используют legacy `repo_index_states`.

### REPO-005 — Реализовать SSE status streaming
- Priority: `P1`
- Depends on: `REPO-004`
- Goal: заменить polling для индексации и документации.
- Tasks:
- реализовать `GET /index-runs/{id}/stream`;
- реализовать `GET /documentation-runs/{id}/stream`;
- стримить статус, stage, progress и последние events;
- добавить reconnect-friendly event ids.
- Acceptance:
- фронт может подписаться на прогресс без polling.

## Epic JOBS — Postgres-backed Jobs

### JOBS-001 — Спроектировать общий job execution contract
- Priority: `P0`
- Depends on: `DATA-001`
- Goal: один и тот же execution model должен работать для index и docs jobs.
- Tasks:
- определить statuses: `queued`, `running`, `succeeded`, `failed`, `canceled`, `stale`;
- определить stages для index и docs runs;
- определить поля `worker_id`, `lease_until`, `heartbeat_at`, `attempt`, `max_attempts`;
- определить набор error codes.
- Acceptance:
- есть единый job execution contract;
- все worker-процессы используют одну и ту же модель.

### JOBS-002 — Реализовать claim loop для `index_runs`
- Priority: `P0`
- Depends on: `JOBS-001`, `REPO-004`
- Goal: убрать heavy work из HTTP lifecycle.
- Tasks:
- реализовать SQL claim через `FOR UPDATE SKIP LOCKED`;
- реализовать lease update и heartbeat;
- реализовать safe transition `queued -> running -> succeeded/failed`;
- покрыть интеграционными тестами конкурентный claim.
- Acceptance:
- два worker-а не берут одну и ту же задачу;
- зависший job может быть переclaimed после истечения lease.

### JOBS-003 — Реализовать claim loop для `documentation_runs`
- Priority: `P1`
- Depends on: `JOBS-001`
- Goal: переиспользовать тот же execution pattern для docs generation.
- Tasks:
- повторно использовать общий claim/lease/heartbeat infrastructure;
- реализовать docs-specific stage transitions;
- покрыть сценарии retry и stale detection.
- Acceptance:
- docs jobs живут по той же модели, что и index jobs.

### JOBS-004 — Реализовать stale job recovery
- Priority: `P1`
- Depends on: `JOBS-002`
- Goal: корректно восстанавливать jobs после падения worker-а.
- Tasks:
- реализовать reaper-процесс или background sweep;
- переводить stale runs обратно в `queued` либо в `failed` при превышении лимита попыток;
- логировать recovery в `index_run_events`/`documentation_run_events`.
- Acceptance:
- убитый worker не оставляет job навсегда в `running`.

### JOBS-005 — Реализовать cancel semantics
- Priority: `P2`
- Depends on: `JOBS-002`, `JOBS-003`
- Goal: уметь прерывать долгие процессы без ручного вмешательства в БД.
- Tasks:
- добавить `cancel_requested_at`, `canceled_at`, `cancel_reason`;
- дать worker-у возможность корректно завершать run;
- реализовать endpoint отмены.
- Acceptance:
- пользователь или администратор может отменить index/doc run штатно.

## Epic INGEST — Indexing Worker And Project Analysis

### INGEST-001 — Отделить HTTP API от worker режима в `ingestion_service`
- Priority: `P0`
- Depends on: `JOBS-002`
- Goal: текущий `BackgroundTasks` должен исчезнуть.
- Tasks:
- убрать зависимость от текущей схемы запуска через FastAPI request lifecycle;
- добавить отдельный worker entrypoint;
- сохранить retrieval API как отдельный режим сервиса;
- настроить compose на отдельные контейнеры `ingestion_api` и `ingestion_worker` либо режимы запуска одного образа.
- Acceptance:
- индексация больше не выполняется внутри HTTP запроса;
- worker можно запустить отдельно.

### INGEST-002 — Реализовать clone + snapshot resolution pipeline
- Priority: `P0`
- Depends on: `INGEST-001`, `REPO-003`
- Goal: worker должен получать конкретный commit и собирать воспроизводимый snapshot.
- Tasks:
- clone заданного репозитория;
- resolve `selected_branch` в head commit;
- checkout конкретного `commit_sha`;
- вычислить `tree_hash`, counters и metadata;
- записать snapshot в Postgres до начала тяжелого анализа.
- Acceptance:
- у каждого index_run есть точный `snapshot_id` и `commit_sha`;
- повторный запуск на том же commit может быть идемпотентным.

### INGEST-003 — Реализовать `file_inventory.json`
- Priority: `P0`
- Depends on: `INGEST-002`
- Goal: создать детерминированный инвентарь файлов как базовый артефакт.
- Tasks:
- пройти по дереву репозитория;
- классифицировать файлы: go, markdown, config, test, binary, generated, vendor;
- вычислить `sha256`, lines count, size;
- записать артефакт в MinIO и metadata в `analysis_artifacts`.
- Acceptance:
- `file_inventory.json` существует для каждого успешного snapshot;
- downstream pipeline может использовать его как источник правды по файлам.

### INGEST-004 — Реализовать `go_symbols.json`
- Priority: `P0`
- Depends on: `INGEST-003`
- Goal: получить структурированный список сущностей Go.
- Tasks:
- доработать tree-sitter extractor под функции, методы, struct, interface, type;
- извлечь package, imports, comments, signature;
- вычислить symbol ids;
- привязать symbol к file_path и line range.
- Acceptance:
- для Go файлов формируется детерминированный symbols inventory;
- symbol list пригоден и для retrieval, и для docs.

### INGEST-005 — Реализовать `package_graph.json`
- Priority: `P1`
- Depends on: `INGEST-004`
- Goal: отразить связи пакетов внутри репозитория.
- Tasks:
- агрегировать imports по packages;
- учитывать `go.mod` и локальные import path;
- определить entrypoint packages типа `cmd/*`;
- сформировать `packages[]` и `edges[]`.
- Acceptance:
- можно восстановить package map и import graph проекта.

### INGEST-006 — Реализовать `config_inventory.json`
- Priority: `P1`
- Depends on: `INGEST-004`
- Goal: собрать конфигурационные точки проекта.
- Tasks:
- эвристически извлечь `os.Getenv`, `flag.*`, yaml/json/toml keys, config structs;
- связать config keys с source files и symbols;
- поддержать default values и required flags, если они обнаружимы.
- Acceptance:
- handbook и `configuration_and_ops` могут строиться на основе артефакта, а не только свободного RAG.

### INGEST-007 — Реализовать `project_model.json`
- Priority: `P0`
- Depends on: `INGEST-004`, `INGEST-005`, `INGEST-006`
- Goal: получить единую нормализованную модель проекта.
- Tasks:
- агрегировать files, packages, symbols, entrypoints, config, external integrations;
- выделить `http_surface`, если она уверенно обнаруживается;
- сформировать summary counts и topology;
- записать artifact versioned schema.
- Acceptance:
- docs generator может стартовать только по `project_model + artifacts`, без повторного глубокого анализа repo tree.

### INGEST-008 — Реализовать `commit_log.json`
- Priority: `P1`
- Depends on: `INGEST-002`
- Goal: поддержать diff-aware документацию и историю snapshot.
- Tasks:
- собрать N последних commit;
- если есть `base_snapshot_id`, собрать интервал между base и head;
- агрегировать touched files/packages;
- записать structured commit log.
- Acceptance:
- сервис документации может строить `changes_since_previous_snapshot`.

### INGEST-009 — Реализовать artifact publishing в MinIO
- Priority: `P0`
- Depends on: `INGEST-003`..`INGEST-008`
- Goal: все промежуточные артефакты должны публиковаться единообразно.
- Tasks:
- реализовать naming convention для object keys;
- публиковать checksum, content type, size;
- записывать metadata в `analysis_artifacts`;
- делать overwrite/idempotent publish для одного snapshot.
- Acceptance:
- все analysis artifacts доступны по snapshot и version.

## Epic RAG — Vector Index And Retrieval

### RAG-001 — Выбрать модель хранения в Qdrant
- Priority: `P0`
- Depends on: `INGEST-002`
- Goal: перейти от коллекции на repo к коллекции на schema/version.
- Tasks:
- создать дизайн `code_chunks_v1`;
- определить payload поля: `snapshot_id`, `repository_id`, `commit_sha`, `file_path`, `language`, `package`, `kind`, `name`, `start_line`, `end_line`, `chunk_kind`, `is_test`;
- определить payload indexes.
- Acceptance:
- retrieval возможен через filter по `snapshot_id`;
- Qdrant не просачивается в публичную доменную модель.

### RAG-002 — Реализовать chunking и deterministic chunk ids
- Priority: `P0`
- Depends on: `RAG-001`, `INGEST-004`
- Goal: обеспечить идемпотентность и предсказуемость индекса.
- Tasks:
- определить стратегию chunking для Go entities и plain text fallback;
- формировать chunk id из `snapshot_id + file_path + symbol signature + chunk_index`;
- хранить связь `symbol -> chunk`.
- Acceptance:
- повторный индекс одного snapshot не плодит новые логические чанки.

### RAG-003 — Реализовать upsert/delete by snapshot
- Priority: `P0`
- Depends on: `RAG-002`
- Goal: безопасно переиндексировать snapshot без мусора.
- Tasks:
- удалить старые points данного `snapshot_id` перед полной перезаливкой;
- делать batch upsert;
- логировать counters в `index_runs`.
- Acceptance:
- stale chunks не остаются после реиндексации того же snapshot.

### RAG-004 — Реализовать retrieval API по `snapshot_id`
- Priority: `P0`
- Depends on: `RAG-003`
- Goal: chats и docs не должны знать про коллекции и qdrant payload details.
- Tasks:
- реализовать внутренний endpoint `POST /internal/retrieval/search`;
- принимать `snapshot_id`, `query`, `top_k`, optional filters;
- возвращать normalized source DTO;
- добавить latency metrics.
- Acceptance:
- любой downstream consumer делает retrieval только через `snapshot_id`.

### RAG-005 — Добавить hybrid retrieval
- Priority: `P1`
- Depends on: `RAG-004`, `INGEST-007`
- Goal: улучшить точность ответов и документации.
- Tasks:
- добавить exact/path/symbol boost поверх dense search;
- использовать `project_model` и `go_symbols` для query expansion;
- добавить rerank heuristic без отдельного ML reranker.
- Acceptance:
- вопросы по символам, пакетам и конкретным файлам отвечаются стабильнее.

## Epic CHAT — ChatService

### CHAT-001 — Поднять минимальный `ChatService`
- Priority: `P0`
- Depends on: `DATA-002`, `PLATFORM-001`, `PLATFORM-002`
- Goal: сервис должен стартовать и владеть своей БД.
- Tasks:
- создать setup по образцу AuthService;
- подключить DbContext, auth, health, observability;
- настроить compose/env variables.
- Acceptance:
- сервис стартует локально и имеет свою схему `chat`.

### CHAT-002 — Реализовать chat CRUD
- Priority: `P0`
- Depends on: `CHAT-001`, `REPO-003`
- Goal: создавать и читать snapshot-bound чаты.
- Tasks:
- реализовать `POST /chats`, `GET /chats`, `GET /chats/{id}`, `GET /chats/{id}/messages`;
- при создании чата принимать `repository_id` и optional `snapshot_id`;
- если `snapshot_id` не передан, выбирать последний ready snapshot.
- Acceptance:
- chat всегда знает, к какому snapshot относится.

### CHAT-003 — Реализовать send message pipeline
- Priority: `P0`
- Depends on: `CHAT-002`, `RAG-004`
- Goal: восстановить основной use case чата на новой архитектуре.
- Tasks:
- загрузить chat history;
- выполнить retrieval через `snapshot_id`;
- собрать prompt c жесткими source rules;
- вызвать LLM provider;
- сохранить `chat_messages` и `chat_message_sources`.
- Acceptance:
- пользователь может задавать вопросы по snapshot и получать grounded answer с источниками.

### CHAT-004 — Реализовать usage and source persistence
- Priority: `P1`
- Depends on: `CHAT-003`
- Goal: сделать chat пригодным для анализа и отладки.
- Tasks:
- сохранять `input_tokens`, `output_tokens`, `provider`, `finish_reason`;
- сохранять normalized citations и scores;
- сохранить retrieval/generation latency.
- Acceptance:
- по каждому assistant message видно, какие chunks были использованы и во что обошелся ответ.

### CHAT-005 — Реализовать streaming replies
- Priority: `P1`
- Depends on: `CHAT-003`
- Goal: улучшить UX без изменения core logic.
- Tasks:
- реализовать `POST /chats/{id}/messages/stream`;
- отправлять partial tokens и финальные normalized sources;
- обеспечить корректное завершение и сохранение финального сообщения.
- Acceptance:
- фронт может стримить ответ LLM.

## Epic DOCS — Documentation Generator

### DOCS-001 — Создать `documentation_service` scaffold
- Priority: `P0`
- Depends on: `DATA-001`, `JOBS-003`
- Goal: поднять отдельный Python сервис/worker для генерации документации.
- Tasks:
- создать структуру проекта и docker image;
- реализовать worker entrypoint для `documentation_runs`;
- подключить Postgres, MinIO, observability.
- Acceptance:
- сервис стартует и может claim-ить jobs.

### DOCS-002 — Реализовать section planning
- Priority: `P0`
- Depends on: `DOCS-001`, `INGEST-007`
- Goal: генератор должен строить документацию не “целиком одним промптом”, а по схеме разделов.
- Tasks:
- определить template schema для `developer_handbook`;
- создать section plan с fixed section keys;
- записывать sections в `documentation_sections`.
- Acceptance:
- один `documentation_run` создаёт предсказуемый набор sections.

### DOCS-003 — Реализовать evidence retrieval per section
- Priority: `P0`
- Depends on: `DOCS-002`, `RAG-004`
- Goal: каждый раздел должен опираться на structured artifacts и search.
- Tasks:
- читать `project_model`, `package_graph`, `config_inventory`, `commit_log`;
- при необходимости делать retrieval по `snapshot_id`;
- формировать normalized section evidence pack;
- сохранять section sources.
- Acceptance:
- секции документации имеют machine-readable source set.

### DOCS-004 — Реализовать `developer_handbook`
- Priority: `P0`
- Depends on: `DOCS-003`
- Goal: получить первый реально полезный тип документации.
- Tasks:
- сгенерировать sections `overview`, `repository_layout`, `package_map`, `entry_points`, `major_flows`, `domain_entities`, `integrations`, `configuration`, `build_run_test`, `known_gaps`;
- собрать `documentation.md` и `manifest.json`;
- сохранить section artifacts и bundle.
- Acceptance:
- можно сгенерировать developer handbook для проиндексированного snapshot.

### DOCS-005 — Реализовать `api_reference`
- Priority: `P1`
- Depends on: `DOCS-003`, `INGEST-007`
- Goal: генерировать API reference, если проект действительно содержит HTTP surface.
- Tasks:
- использовать `http_surface` из `project_model`;
- генерировать summary и endpoint sections;
- помечать документ partial, если источников недостаточно.
- Acceptance:
- при наличии API в репозитории можно получить пригодную reference doc.

### DOCS-006 — Реализовать `configuration_and_ops`
- Priority: `P1`
- Depends on: `DOCS-003`, `INGEST-006`
- Goal: выдавать полезную документацию по конфигурации и эксплуатации.
- Tasks:
- использовать `config_inventory` и related source files;
- описать env vars, config files, external services, локальный запуск;
- собирать dedicated artifact bundle.
- Acceptance:
- документ отражает найденные настройки и зависимости проекта.

### DOCS-007 — Реализовать `changes_since_previous_snapshot`
- Priority: `P1`
- Depends on: `DOCS-003`, `INGEST-008`
- Goal: поддержать changelog-style документацию между snapshot.
- Tasks:
- использовать `base_snapshot_id`;
- агрегировать commits, changed packages, possible impact;
- формировать diff-based documentation artifact.
- Acceptance:
- по двум snapshot можно получить readable change summary с источниками.

### DOCS-008 — Реализовать verification pipeline
- Priority: `P0`
- Depends on: `DOCS-004`
- Goal: документация должна проходить проверку before publish.
- Tasks:
- проверять supported claims и наличие source refs;
- проверять консистентность sections;
- сохранять `verification_report.json`;
- переводить run в `published` только при успешной проверке.
- Acceptance:
- docs run не публикуется как успешный без verification.

## Epic GATEWAY — Public API Integration

### GATEWAY-001 — Подключить новые маршруты в EdgeGateway
- Priority: `P0`
- Depends on: `REPO-004`, `CHAT-003`
- Goal: дать единый публичный доступ к новым сервисам.
- Tasks:
- добавить YARP routes для RepositoryService и ChatService;
- добавить маршруты для SSE endpoints;
- удалить публичную зависимость на legacy repos/chats services.
- Acceptance:
- весь основной публичный трафик идет через gateway в новые сервисы.

### GATEWAY-002 — Нормализовать auth/user context contract
- Priority: `P0`
- Depends on: `GATEWAY-001`, `PLATFORM-002`
- Goal: полностью убрать `user_id` из клиентских payload.
- Tasks:
- убедиться, что gateway всегда пробрасывает `X-User-Id`;
- обновить frontend/shared DTO;
- добавить integration tests на user context propagation.
- Acceptance:
- ни один новый публичный endpoint не требует `user_id` в body/query.

## Epic FRONT — Backend-first UI Adaptation

### FRONT-001 — Обновить shared API contracts
- Priority: `P1`
- Depends on: `GATEWAY-001`
- Goal: синхронизировать frontend с новой бэкенд-моделью.
- Tasks:
- заменить legacy endpoints `repo-index-states`, `ingest/repo`, старые chats contracts;
- добавить DTO для `snapshot`, `index_run`, `documentation_run`, SSE events;
- убрать `user_id` из payload.
- Acceptance:
- frontend/shared не содержит legacy domain model для новых потоков.

### FRONT-002 — Перевести экран индексации на SSE
- Priority: `P1`
- Depends on: `REPO-005`, `FRONT-001`
- Goal: убрать polling и показывать реальные стадии job.
- Tasks:
- подписываться на `index_run` SSE;
- показывать `stage`, `progress`, `error_message`;
- обновлять список snapshot после завершения.
- Acceptance:
- индексация отображается через streaming status updates.

### FRONT-003 — Добавить UI для документации
- Priority: `P2`
- Depends on: `DOCS-004`, `FRONT-001`
- Goal: дать минимальную возможность запускать генерацию и смотреть результат.
- Tasks:
- добавить кнопку generate docs;
- показать список documentation runs;
- показать markdown preview/download links.
- Acceptance:
- пользователь может с фронта запустить генерацию и открыть артефакты.

### FRONT-004 — Добавить chat streaming и sources UI
- Priority: `P2`
- Depends on: `CHAT-005`
- Goal: отобразить сильные стороны новой chat модели.
- Tasks:
- стримить assistant reply;
- показывать normalized sources отдельно от raw markdown;
- отображать snapshot context текущего чата.
- Acceptance:
- UI чата отражает snapshot-aware и source-aware модель.

## Epic OBS — Observability And Diagnostics

### OBS-001 — Покрыть новые сервисы и workers метриками
- Priority: `P1`
- Depends on: `REPO-001`, `CHAT-001`, `INGEST-001`, `DOCS-001`
- Goal: видеть состояние jobs и latency критических путей.
- Tasks:
- добавить metrics для queue depth, claim latency, run duration, failure counts;
- добавить retrieval, embedding, qdrant, llm latency metrics;
- добавить docs verification metrics.
- Acceptance:
- Grafana/Prometheus показывают состояние новых потоков.

### OBS-002 — Добавить structured event logging для jobs
- Priority: `P1`
- Depends on: `JOBS-002`, `JOBS-003`
- Goal: упростить разбор проблем с тяжелыми задачами.
- Tasks:
- логировать transitions job state/stage;
- логировать worker claim/release/retry;
- добавлять `run_id`, `snapshot_id`, `repository_id`, `worker_id` в контекст.
- Acceptance:
- по логам можно проследить полный lifecycle job.

## Epic TEST — Automated Verification

### TEST-001 — Написать integration tests для RepositoryService
- Priority: `P0`
- Depends on: `REPO-004`
- Goal: закрепить новую доменную модель и REST контракты.
- Tasks:
- тесты на repository create/list/get;
- тесты на snapshot lookup;
- тесты на creation of index/doc runs;
- тесты на SSE/status endpoints.
- Acceptance:
- базовый orchestration layer покрыт интеграционно.

### TEST-002 — Написать concurrency tests для jobs
- Priority: `P0`
- Depends on: `JOBS-002`, `JOBS-003`
- Goal: убедиться, что claim/lease работает надежно.
- Tasks:
- тест на конкурентный claim одной задачи;
- тест на stale recovery;
- тест на retry exhaustion.
- Acceptance:
- основные race conditions покрыты тестами.

### TEST-003 — Написать end-to-end test `index -> chat -> docs`
- Priority: `P1`
- Depends on: `CHAT-003`, `DOCS-004`
- Goal: проверить целостность всей новой системы.
- Tasks:
- поднять compose-test stack;
- проиндексировать небольшой Go repo;
- задать вопрос в чат;
- сгенерировать developer handbook;
- проверить наличие artifacts и sources.
- Acceptance:
- один e2e сценарий подтверждает работоспособность целевого use case.

## Epic OPS — Security, Limits, Reliability

### OPS-001 — Ограничить входные репозитории и ресурсы
- Priority: `P1`
- Depends on: `REPO-002`, `INGEST-002`
- Goal: предотвратить опасные и слишком тяжелые входы.
- Tasks:
- разрешить только public GitHub URL;
- ограничить repo size, file count, total bytes, clone timeout;
- ограничить поддерживаемые git protocols;
- отказоустойчиво обрабатывать oversized repository.
- Acceptance:
- система не пытается безгранично индексировать произвольные входы.

### OPS-002 — Ввести cleanup и GC для временных ресурсов
- Priority: `P1`
- Depends on: `INGEST-001`, `DOCS-001`
- Goal: не копить мусор на диске и в storage.
- Tasks:
- удалять temp clone dirs;
- удалять orphaned partial artifacts после failed jobs;
- реализовать cleanup stale local worker state.
- Acceptance:
- длительная работа системы не раздувает диск бесконтрольно.

### OPS-003 — Добавить rate limits и idempotency controls
- Priority: `P2`
- Depends on: `GATEWAY-001`, `REPO-004`, `CHAT-003`
- Goal: защитить сервисы от лишней нагрузки и дублей.
- Tasks:
- ограничить частоту index/doc/chat requests;
- добавить idempotency key для create run endpoints;
- корректно отвечать на повторные запросы.
- Acceptance:
- повторные клики пользователя не ломают систему и не плодят дублей.

## Epic LEGACY — Legacy Decommission

### LEGACY-001 — Удалить публичное использование legacy repos/chats сервисов
- Priority: `P1`
- Depends on: `GATEWAY-001`, `FRONT-001`
- Goal: перевести пользовательские сценарии на новые сервисы.
- Tasks:
- убрать legacy routes из gateway;
- убрать legacy env vars из compose;
- убедиться, что frontend больше не использует старые endpoints.
- Acceptance:
- основной пользовательский поток не зависит от `backend/repos_service` и `backend/chats_service`.

### LEGACY-002 — Удалить legacy схемы и код после стабилизации
- Priority: `P2`
- Depends on: `LEGACY-001`, `TEST-003`
- Goal: сократить техдолг после миграции.
- Tasks:
- удалить legacy repos/chats services;
- удалить устаревший `db-init`;
- удалить неактуальные workflow/config fragments;
- переписать `README.md` под новую архитектуру.
- Acceptance:
- в репозитории не осталось активно используемого legacy кода для замененных сервисов.

## Suggested First Implementation Slice

Если нужно начать немедленно и без дополнительной декомпозиции, первый рабочий срез такой:

1. `ARCH-001`
2. `ARCH-002`
3. `DATA-001`
4. `DATA-002`
5. `DATA-003`
6. `PLATFORM-001`
7. `PLATFORM-002`
8. `REPO-001`
9. `REPO-002`
10. `REPO-003`
11. `JOBS-001`
12. `JOBS-002`
13. `INGEST-001`
14. `INGEST-002`
15. `INGEST-003`
16. `INGEST-004`
17. `INGEST-007`
18. `RAG-001`
19. `RAG-002`
20. `RAG-003`
21. `RAG-004`
22. `REPO-004`
23. `CHAT-001`
24. `CHAT-002`
25. `CHAT-003`
26. `GATEWAY-001`
27. `GATEWAY-002`
28. `TEST-001`
29. `TEST-002`

После этого проект уже сможет:

- регистрировать репозиторий;
- запускать индексацию через durable job;
- строить snapshot и промежуточные analysis artifacts;
- индексировать чанки в Qdrant;
- отвечать на вопросы по snapshot через новый `ChatService`.

Следующий обязательный слой после этого:

1. `REPO-005`
2. `DOCS-001`
3. `DOCS-002`
4. `DOCS-003`
5. `DOCS-004`
6. `DOCS-008`
7. `FRONT-002`
8. `TEST-003`
