// All public API paths are rooted at axios baseURL `/api`.

export const endpoints = {
    auth: {
        login: "/v1/auth/login",
        refresh: "/v1/auth/refresh",
        register: "/v1/auth/register",
    },
    repositories: {
        index: "/v1/repositories/index",
        list: "/v1/repositories",
        get: (repositoryId: string) => `/v1/repositories/${repositoryId}`,
        readySnapshot: (repositoryId: string) => `/v1/repositories/${repositoryId}/snapshots/ready`,
        indexRuns: (repositoryId: string) => `/v1/repositories/${repositoryId}/index-runs`,
        documentationRuns: (repositoryId: string) => `/v1/repositories/${repositoryId}/documentation-runs`,
        createDocumentationRun: (repositoryId: string) => `/v1/repositories/${repositoryId}/documentation`,
    },
    indexRuns: {
        get: (runId: string) => `/v1/index-runs/${runId}`,
    },
    documentationRuns: {
        get: (runId: string) => `/v1/documentation-runs/${runId}`,
        artifacts: (runId: string) => `/v1/documentation-runs/${runId}/artifacts`,
        artifactContent: (runId: string, artifactId: string) =>
            `/v1/documentation-runs/${runId}/artifacts/${artifactId}/content`,
    },
    chats: {
        list: "/v1/chats",
        create: "/v1/chats",
        messages: (chatId: string) => `/v1/chats/${chatId}/messages`,
        send: (chatId: string) => `/v1/chats/${chatId}/messages`,
    },
};
