import { makeAutoObservable, runInAction } from "mobx";
import { api, endpoints } from "@rag/shared";
import type {
    IndexRepositoryRequest,
    IndexRun,
    PagedResponse,
    Repository,
    RunAcceptedResponse,
} from "@rag/shared";

export type RepositoryListItem = Repository & {
    latest_index_run?: IndexRun | null;
};

function isActive(status?: string | null) {
    return status === "queued" || status === "running";
}

export class RepoStore {
    repos: RepositoryListItem[] = [];
    activeIndexRunIds = new Set<string>();

    loadingList = false;
    loadingStatuses = false;
    indexing = false;
    error: string | null = null;

    private statusTimer: number | null = null;
    private statusesInFlight = false;

    constructor() {
        makeAutoObservable(this, {}, { autoBind: true });
    }

    async init() {
        await this.loadReposList();
        this.startStatusPolling();
    }

    async loadReposList() {
        this.loadingList = true;
        this.error = null;

        try {
            const res = await api.get<PagedResponse<Repository>>(endpoints.repositories.list, {
                params: { limit: 100, offset: 0 },
            });
            const repos = res.data.items;
            const withRuns = await Promise.all(repos.map((repo) => this.loadLatestIndexRun(repo)));

            runInAction(() => {
                this.repos = withRuns;
                this.activeIndexRunIds = new Set(
                    withRuns
                        .map((repo) => repo.latest_index_run)
                        .filter((run): run is IndexRun => Boolean(run && isActive(run.status)))
                        .map((run) => run.id),
                );
                this.loadingList = false;
            });
        } catch {
            runInAction(() => {
                this.loadingList = false;
                this.error = "Failed to load repositories";
            });
        }
    }

    async refreshStatuses() {
        if (this.statusesInFlight) return;
        if (this.repos.length === 0 && this.activeIndexRunIds.size === 0) return;

        this.statusesInFlight = true;
        this.loadingStatuses = true;

        try {
            const runIds = Array.from(this.activeIndexRunIds);
            const runResults = await Promise.all(
                runIds.map(async (runId) => {
                    const res = await api.get<IndexRun>(endpoints.indexRuns.get(runId));
                    return res.data;
                }),
            );

            const repoRefreshIds = new Set(
                runResults
                    .filter((run) => run.status === "succeeded")
                    .map((run) => run.repository_id),
            );
            const repoResults = await Promise.all(
                Array.from(repoRefreshIds).map(async (repositoryId) => {
                    const res = await api.get<Repository>(endpoints.repositories.get(repositoryId));
                    return res.data;
                }),
            );

            runInAction(() => {
                const runsByRepo = new Map(runResults.map((run) => [run.repository_id, run]));
                const refreshedRepos = new Map(repoResults.map((repo) => [repo.id, repo]));
                this.repos = this.repos.map((repo) => {
                    const refreshed = refreshedRepos.get(repo.id);
                    const run = runsByRepo.get(repo.id) ?? repo.latest_index_run ?? null;
                    return {
                        ...(refreshed ?? repo),
                        latest_index_run: run,
                    };
                });
                this.activeIndexRunIds = new Set(
                    runResults
                        .filter((run) => isActive(run.status))
                        .map((run) => run.id),
                );
                this.loadingStatuses = false;
            });
        } finally {
            this.statusesInFlight = false;
            runInAction(() => {
                this.loadingStatuses = false;
            });
        }
    }

    startStatusPolling() {
        if (this.statusTimer != null) return;
        this.statusTimer = window.setInterval(() => {
            void this.refreshStatuses();
        }, 4000);
    }

    stopStatusPolling() {
        if (this.statusTimer == null) return;
        window.clearInterval(this.statusTimer);
        this.statusTimer = null;
    }

    async startIndexing(url: string, selectedBranch: string | null = null) {
        this.error = null;
        this.indexing = true;

        try {
            const payload: IndexRepositoryRequest = {
                repository_url: url,
                selected_branch: selectedBranch || null,
            };
            const indexRes = await api.post<RunAcceptedResponse>(endpoints.repositories.index, payload);
            const repoRes = await api.get<Repository>(endpoints.repositories.get(indexRes.data.repository_id));
            const runRes = await api.get<IndexRun>(endpoints.indexRuns.get(indexRes.data.id));

            const repo: RepositoryListItem = {
                ...repoRes.data,
                latest_index_run: runRes.data,
            };

            runInAction(() => {
                const idx = this.repos.findIndex((item) => item.id === repo.id);
                if (idx >= 0) {
                    this.repos = [repo, ...this.repos.slice(0, idx), ...this.repos.slice(idx + 1)];
                } else {
                    this.repos = [repo, ...this.repos];
                }
                if (isActive(runRes.data.status)) {
                    this.activeIndexRunIds.add(runRes.data.id);
                }
                this.indexing = false;
            });

            this.startStatusPolling();
            return repo;
        } catch (error) {
            runInAction(() => {
                this.indexing = false;
                this.error = "Failed to start indexing";
            });
            throw error;
        }
    }

    dispose() {
        this.stopStatusPolling();
    }

    private async loadLatestIndexRun(repo: Repository): Promise<RepositoryListItem> {
        try {
            const res = await api.get<PagedResponse<IndexRun>>(endpoints.repositories.indexRuns(repo.id), {
                params: { limit: 1, offset: 0 },
            });
            return {
                ...repo,
                latest_index_run: res.data.items[0] ?? null,
            };
        } catch {
            return {
                ...repo,
                latest_index_run: null,
            };
        }
    }
}
