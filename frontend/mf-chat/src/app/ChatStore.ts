import { makeAutoObservable, runInAction } from "mobx";
import { api, endpoints } from "@rag/shared";
import type {
    Chat,
    ChatMessage,
    CreateChatRequest,
    CreateDocumentationRunRequest,
    DocumentationArtifact,
    DocumentationRun,
    IndexRun,
    PagedResponse,
    Repository,
    RepositorySnapshot,
    RunAcceptedResponse,
    SendMessageRequest,
    SendMessageResponse,
    UUID,
} from "@rag/shared";

const POLL_INTERVAL_MS = 4000;

const FINAL_DOCUMENT_KINDS = [
    "documentation_markdown",
    "document_repository_brief",
    "document_onboarding_guide",
    "document_architecture_map",
    "document_api_reference",
    "document_configuration_reference",
    "document_commands_reference",
    "document_package_service_index",
    "document_change_report",
];

const DOCUMENT_KIND_LABELS: Record<string, string> = {
    documentation_markdown: "Index",
    document_repository_brief: "Brief",
    document_onboarding_guide: "Onboarding",
    document_architecture_map: "Architecture",
    document_api_reference: "API",
    document_configuration_reference: "Config",
    document_commands_reference: "Commands",
    document_package_service_index: "Packages",
    document_change_report: "Changes",
};

function makeTempId(prefix: string) {
    return `${prefix}_${Math.random().toString(16).slice(2)}_${Date.now()}`;
}

function isActive(status?: string | null) {
    return status === "queued" || status === "running";
}

function documentSortRank(kind: string) {
    const rank = FINAL_DOCUMENT_KINDS.indexOf(kind);
    return rank === -1 ? FINAL_DOCUMENT_KINDS.length : rank;
}

function makeLocalMessage(chatId: UUID, role: "user" | "assistant", content: string): ChatMessage {
    return {
        id: makeTempId(role),
        chat_id: chatId,
        role,
        content_markdown: content,
        model_name: null,
        provider: null,
        finish_reason: null,
        created_at: new Date().toISOString(),
        sources: [],
    };
}

export class ChatStore {
    repoId: UUID | null = null;
    repo: Repository | null = null;
    readySnapshot: RepositorySnapshot | null = null;

    indexRuns: IndexRun[] = [];
    documentationRuns: DocumentationRun[] = [];
    documentationArtifacts: DocumentationArtifact[] = [];
    selectedArtifactId: UUID | null = null;
    artifactContent = "";

    chatId: UUID | null = null;
    messages: ChatMessage[] = [];

    loading = false;
    loadingArtifact = false;
    generatingDocumentation = false;
    sending = false;
    error: string | null = null;
    docsError: string | null = null;

    private loadSeq = 0;
    private sendSeq = 0;
    private pollTimer: number | null = null;

    constructor() {
        makeAutoObservable(
            this,
            {
                loadSeq: false,
                sendSeq: false,
                pollTimer: false,
            },
            { autoBind: true }
        );
    }

    get latestIndexRun() {
        return this.indexRuns[0] ?? null;
    }

    get latestDocumentationRun() {
        return this.documentationRuns[0] ?? null;
    }

    get hasReadySnapshot() {
        return this.readySnapshot != null || this.repo?.active_snapshot_id != null;
    }

    get isIndexing() {
        return isActive(this.latestIndexRun?.status);
    }

    get isDocumenting() {
        return isActive(this.latestDocumentationRun?.status);
    }

    get canGenerateDocumentation() {
        return this.repoId != null && this.hasReadySnapshot && !this.generatingDocumentation && !this.isDocumenting;
    }

    get canChat() {
        return this.repoId != null && this.hasReadySnapshot;
    }

    get selectedArtifact() {
        return this.documentationArtifacts.find((artifact) => artifact.id === this.selectedArtifactId) ?? null;
    }

    documentLabel(artifact: DocumentationArtifact) {
        return DOCUMENT_KIND_LABELS[artifact.artifact_kind] ?? artifact.artifact_kind;
    }

    async openRepo(repoId: UUID | null) {
        const seq = ++this.loadSeq;
        this.stopPolling();

        runInAction(() => {
            this.repoId = repoId;
            this.repo = null;
            this.readySnapshot = null;
            this.indexRuns = [];
            this.documentationRuns = [];
            this.documentationArtifacts = [];
            this.selectedArtifactId = null;
            this.artifactContent = "";
            this.chatId = null;
            this.messages = [];
            this.error = null;
            this.docsError = null;
            this.loading = repoId != null;
            this.loadingArtifact = false;
            this.generatingDocumentation = false;
            this.sending = false;
        });

        if (!repoId) {
            return;
        }

        try {
            await this.loadRepositoryWorkspace(repoId, seq);
            if (seq !== this.loadSeq || this.repoId !== repoId) return;

            runInAction(() => {
                this.loading = false;
            });

            this.startPollingIfNeeded();
        } catch (error) {
            if (seq !== this.loadSeq) return;
            runInAction(() => {
                this.loading = false;
                this.error = "Failed to open repository workspace.";
            });
            throw error;
        }
    }

    async refresh() {
        const repoId = this.repoId;
        if (!repoId) return;

        const seq = this.loadSeq;
        await this.loadRepositoryWorkspace(repoId, seq);
        if (seq !== this.loadSeq) return;

        this.startPollingIfNeeded();
    }

    async generateDocumentation() {
        const repoId = this.repoId;
        if (!repoId || !this.canGenerateDocumentation) return;

        runInAction(() => {
            this.generatingDocumentation = true;
            this.docsError = null;
        });

        try {
            const payload: CreateDocumentationRunRequest = {
                snapshot_id: this.readySnapshot?.id ?? this.repo?.active_snapshot_id ?? null,
                template_kind: "developer_handbook",
            };
            const accepted = await api.post<RunAcceptedResponse>(endpoints.repositories.createDocumentationRun(repoId), payload);
            const run = await this.fetchDocumentationRun(accepted.data.id);

            runInAction(() => {
                this.documentationRuns = this.mergeDocumentationRun(run);
                this.generatingDocumentation = false;
            });

            this.startPollingIfNeeded();
        } catch (error) {
            runInAction(() => {
                this.generatingDocumentation = false;
                this.docsError = "Failed to start documentation generation.";
            });
            throw error;
        }
    }

    async selectArtifact(artifactId: UUID) {
        if (artifactId === this.selectedArtifactId && this.artifactContent) {
            return;
        }

        const runId = this.latestDocumentationRun?.id;
        if (!runId) return;

        runInAction(() => {
            this.selectedArtifactId = artifactId;
            this.loadingArtifact = true;
            this.docsError = null;
        });

        try {
            const res = await api.get<string>(endpoints.documentationRuns.artifactContent(runId, artifactId), {
                responseType: "text",
                transformResponse: [(data) => data],
            });

            runInAction(() => {
                this.artifactContent = res.data;
                this.loadingArtifact = false;
            });
        } catch (error) {
            runInAction(() => {
                this.loadingArtifact = false;
                this.docsError = "Failed to load documentation artifact.";
            });
            throw error;
        }
    }

    async sendMessage(content: string) {
        const trimmed = content.trim();
        const chatId = this.chatId;

        if (!trimmed) return;
        if (!chatId || !this.canChat) {
            runInAction(() => {
                this.error = "Documentation-ready repository snapshot is required before chatting.";
            });
            return;
        }

        const seq = ++this.sendSeq;

        runInAction(() => {
            this.sending = true;
            this.error = null;
        });

        const optimisticUser = makeLocalMessage(chatId, "user", trimmed);
        const placeholderAssistant = makeLocalMessage(chatId, "assistant", "Thinking...");

        runInAction(() => {
            this.messages = [...this.messages, optimisticUser, placeholderAssistant];
        });

        try {
            const payload: SendMessageRequest = { content: trimmed };
            const res = await api.post<SendMessageResponse>(endpoints.chats.send(chatId), payload);

            if (seq !== this.sendSeq) return;

            runInAction(() => {
                this.messages = this.messages.map((message) => {
                    if (message.id === optimisticUser.id) return res.data.user_message;
                    if (message.id === placeholderAssistant.id) return res.data.assistant_message;
                    return message;
                });
                this.sending = false;
            });
        } catch (error) {
            if (seq !== this.sendSeq) return;
            runInAction(() => {
                this.messages = this.messages.map((message) =>
                    message.id === placeholderAssistant.id
                        ? { ...message, content_markdown: "Failed to get an answer." }
                        : message
                );
                this.sending = false;
                this.error = "Failed to send message.";
            });
            throw error;
        }
    }

    reset() {
        this.stopPolling();
        runInAction(() => {
            this.repoId = null;
            this.repo = null;
            this.readySnapshot = null;
            this.indexRuns = [];
            this.documentationRuns = [];
            this.documentationArtifacts = [];
            this.selectedArtifactId = null;
            this.artifactContent = "";
            this.chatId = null;
            this.messages = [];
            this.loading = false;
            this.loadingArtifact = false;
            this.generatingDocumentation = false;
            this.sending = false;
            this.error = null;
            this.docsError = null;
            this.loadSeq = 0;
            this.sendSeq = 0;
        });
    }

    private async loadRepositoryWorkspace(repoId: UUID, seq: number) {
        const [repoRes, indexRunsRes, docRunsRes] = await Promise.all([
            api.get<Repository>(endpoints.repositories.get(repoId)),
            api.get<PagedResponse<IndexRun>>(endpoints.repositories.indexRuns(repoId), { params: { limit: 5, offset: 0 } }),
            api.get<PagedResponse<DocumentationRun>>(endpoints.repositories.documentationRuns(repoId), {
                params: { limit: 5, offset: 0 },
            }),
        ]);

        if (seq !== this.loadSeq || this.repoId !== repoId) return;

        runInAction(() => {
            this.repo = repoRes.data;
            this.indexRuns = indexRunsRes.data.items;
            this.documentationRuns = docRunsRes.data.items;
        });

        await this.loadReadySnapshot(repoId, seq);

        const latestDocRun = this.latestDocumentationRun;
        if (latestDocRun?.status === "succeeded") {
            await this.loadDocumentationArtifacts(latestDocRun.id, seq);
        }

        if (this.canChat) {
            const chatId = await this.ensureChat(repoId, seq);
            if (chatId) {
                await this.loadMessages(chatId, seq);
            }
        }
    }

    private async loadReadySnapshot(repoId: UUID, seq: number) {
        try {
            const readyRes = await api.get<RepositorySnapshot>(endpoints.repositories.readySnapshot(repoId));
            if (seq !== this.loadSeq || this.repoId !== repoId) return;
            runInAction(() => {
                this.readySnapshot = readyRes.data;
            });
        } catch {
            if (seq !== this.loadSeq || this.repoId !== repoId) return;
            runInAction(() => {
                this.readySnapshot = null;
            });
        }
    }

    private async ensureChat(repoId: UUID, seq: number): Promise<UUID | null> {
        const listRes = await api.get<PagedResponse<Chat>>(endpoints.chats.list, {
            params: { repository_id: repoId, limit: 1, offset: 0 },
        });

        if (seq !== this.loadSeq || this.repoId !== repoId) return null;

        const existing = listRes.data.items[0];
        if (existing) {
            runInAction(() => {
                this.chatId = existing.id;
            });
            return existing.id;
        }

        const payload: CreateChatRequest = {
            repository_id: repoId,
            snapshot_id: this.readySnapshot?.id ?? this.repo?.active_snapshot_id ?? null,
            title: this.repo?.full_name ?? null,
        };
        const createRes = await api.post<Chat>(endpoints.chats.create, payload);

        if (seq !== this.loadSeq || this.repoId !== repoId) return null;

        runInAction(() => {
            this.chatId = createRes.data.id;
        });
        return createRes.data.id;
    }

    private async loadMessages(chatId: UUID, seq: number) {
        const res = await api.get<PagedResponse<ChatMessage>>(endpoints.chats.messages(chatId), {
            params: { limit: 100, offset: 0 },
        });

        if (seq !== this.loadSeq) return;

        runInAction(() => {
            this.messages = res.data.items;
        });
    }

    private async fetchDocumentationRun(runId: UUID) {
        const res = await api.get<DocumentationRun>(endpoints.documentationRuns.get(runId));
        return res.data;
    }

    private async fetchIndexRun(runId: UUID) {
        const res = await api.get<IndexRun>(endpoints.indexRuns.get(runId));
        return res.data;
    }

    private async loadDocumentationArtifacts(runId: UUID, seq: number) {
        const artifactsRes = await api.get<DocumentationArtifact[]>(endpoints.documentationRuns.artifacts(runId), {
            params: { limit: 100, offset: 0 },
        });

        if (seq !== this.loadSeq) return;

        const artifacts = artifactsRes.data
            .filter((artifact) => FINAL_DOCUMENT_KINDS.includes(artifact.artifact_kind))
            .sort((a, b) => documentSortRank(a.artifact_kind) - documentSortRank(b.artifact_kind));

        const preferred =
            artifacts.find((artifact) => artifact.artifact_kind === "documentation_markdown") ?? artifacts[0] ?? null;

        runInAction(() => {
            this.documentationArtifacts = artifacts;
            this.selectedArtifactId = preferred?.id ?? null;
            this.artifactContent = "";
        });

        if (preferred) {
            await this.selectArtifact(preferred.id);
        }
    }

    private mergeDocumentationRun(run: DocumentationRun) {
        const rest = this.documentationRuns.filter((item) => item.id !== run.id);
        return [run, ...rest].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
    }

    private mergeIndexRun(run: IndexRun) {
        const rest = this.indexRuns.filter((item) => item.id !== run.id);
        return [run, ...rest].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
    }

    private startPollingIfNeeded() {
        this.stopPolling();
        if (!this.isIndexing && !this.isDocumenting) return;

        this.pollTimer = window.setInterval(() => {
            void this.pollActiveRuns();
        }, POLL_INTERVAL_MS);
    }

    private stopPolling() {
        if (this.pollTimer != null) {
            window.clearInterval(this.pollTimer);
            this.pollTimer = null;
        }
    }

    private async pollActiveRuns() {
        const repoId = this.repoId;
        const seq = this.loadSeq;
        if (!repoId) {
            this.stopPolling();
            return;
        }

        const activeIndex = this.indexRuns.find((run) => isActive(run.status));
        const activeDocs = this.documentationRuns.find((run) => isActive(run.status));

        try {
            const [indexRun, documentationRun] = await Promise.all([
                activeIndex ? this.fetchIndexRun(activeIndex.id) : Promise.resolve(null),
                activeDocs ? this.fetchDocumentationRun(activeDocs.id) : Promise.resolve(null),
            ]);

            if (seq !== this.loadSeq || this.repoId !== repoId) return;

            runInAction(() => {
                if (indexRun) this.indexRuns = this.mergeIndexRun(indexRun);
                if (documentationRun) {
                    this.documentationRuns = this.mergeDocumentationRun(documentationRun);
                    this.generatingDocumentation = false;
                }
            });

            if (indexRun?.status === "succeeded") {
                await this.refresh();
                return;
            }

            if (documentationRun?.status === "succeeded") {
                await this.loadDocumentationArtifacts(documentationRun.id, seq);
            }

            if (!this.isIndexing && !this.isDocumenting) {
                this.stopPolling();
            }
        } catch {
            this.stopPolling();
            runInAction(() => {
                this.docsError = "Failed to refresh background job status.";
            });
        }
    }
}
