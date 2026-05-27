import type { ChatMessage, UUID } from "./domain";

export interface PagedResponse<TItem> {
    items: TItem[];
    limit: number;
    offset: number;
    has_more: boolean;
    total_count: number;
}

export interface IndexRepositoryRequest {
    repository_url: string;
    selected_branch?: string | null;
}

export interface RunAcceptedResponse {
    id: UUID;
    kind: "index" | "documentation" | string;
    status: string;
    stage: string;
    repository_id: UUID;
    snapshot_id: UUID | null;
    status_url: string;
    stream_url: string;
}

export interface CreateDocumentationRunRequest {
    snapshot_id?: UUID | null;
    template_kind?: string | null;
    base_snapshot_id?: UUID | null;
}

export interface CreateChatRequest {
    repository_id: UUID;
    snapshot_id?: UUID | null;
    title?: string | null;
}

export interface SendMessageRequest {
    content: string;
}

export interface SendMessageResponse {
    user_message: ChatMessage;
    assistant_message: ChatMessage;
}

export interface LoginRequest {
    email: string;
    password: string;
}

export interface RegisterRequest {
    email: string;
    password: string;
}

export interface AuthResponse {
    access_token: string;
    token_type: "bearer" | string;
    expires_in: number;
    user_id: UUID;
    email: string;
}
