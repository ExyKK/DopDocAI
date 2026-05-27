import {makeAutoObservable, runInAction} from "mobx";
import {api} from "../api/axios";
import {endpoints} from "../api/endpoints";
import {storage} from "../utils/storage";
import type {AuthResponse, LoginRequest, RegisterRequest} from "../types/api";

export class AuthStore {
    token: string | null = storage.getToken();
    userId: string | null = storage.getUserId();
    email: string | null = storage.getEmail();

    initializing = true;
    loading = false;
    error: string | null = null;

    constructor() {
        makeAutoObservable(this, {}, {autoBind: true});

        storage.onTokenChange(() => {
            runInAction(() => {
                this.token = storage.getToken();
            });
        });

        storage.onUserChange(() => {
            runInAction(() => {
                this.userId = storage.getUserId();
                this.email = storage.getEmail();
            });
        });
    }

    get isAuthenticated() {
        return Boolean(this.token);
    }

    async init() {
        // на старте пытаемся обновить access token по cookie
        try {
            await this.refresh();
        } finally {
            runInAction(() => {
                this.initializing = false;
            });
        }
    }

    async login(input: LoginRequest) {
        this.loading = true;
        this.error = null;

        try {
            const res = await api.post<AuthResponse>(endpoints.auth.login, input);

            runInAction(() => {
                storage.setToken(res.data.access_token);
                storage.setUserId(res.data.user_id);
                storage.setEmail(res.data.email);
                this.loading = false;
            });

        } catch (e) {
            runInAction(() => {
                this.error = "Login failed";
                this.loading = false;
            });
            throw e;
        }
    }

    async register(input: RegisterRequest) {
        this.loading = true;
        this.error = null;

        try {
            const res = await api.post<AuthResponse>(endpoints.auth.register, input);
            runInAction(() => {
                storage.setToken(res.data.access_token);
                storage.setUserId(res.data.user_id);
                storage.setEmail(res.data.email);
                this.loading = false;
            });
        } catch (e) {
            runInAction(() => {
                this.error = "Registration failed";
                this.loading = false;
            });
            throw e;
        }
    }

    async refresh() {
        try {
            const res = await api.post<AuthResponse>(endpoints.auth.refresh);
            storage.setToken(res.data.access_token);
            storage.setUserId(res.data.user_id);
            storage.setEmail(res.data.email);
        } catch {
            // refresh может честно не быть — это не ошибка инициализации
            storage.clearAuth();
        }
    }

    logout() {
        storage.clearAuth();
    }
}
