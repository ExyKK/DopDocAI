const TOKEN_KEY = "rag_token";
const USER_ID_KEY = "rag_user_id";
const EMAIL_KEY = "rag_email";

const TOKEN_EVENT = "rag:token_changed";
const USER_EVENT = "rag:user_changed";

function emit(name: string) {
    window.dispatchEvent(new Event(name));
}

export const storage = {
    getToken(): string | null {
        return localStorage.getItem(TOKEN_KEY);
    },
    setToken(token: string) {
        localStorage.setItem(TOKEN_KEY, token);
        emit(TOKEN_EVENT);
    },
    clearToken() {
        localStorage.removeItem(TOKEN_KEY);
        emit(TOKEN_EVENT);
    },

    getUserId(): string | null {
        return localStorage.getItem(USER_ID_KEY);
    },
    setUserId(userId: string | null) {
        if (userId == null) localStorage.removeItem(USER_ID_KEY);
        else localStorage.setItem(USER_ID_KEY, userId);
        emit(USER_EVENT);
    },

    getEmail(): string | null {
        return localStorage.getItem(EMAIL_KEY);
    },
    setEmail(email: string | null) {
        if (!email) localStorage.removeItem(EMAIL_KEY);
        else localStorage.setItem(EMAIL_KEY, email);
        emit(USER_EVENT);
    },

    clearAuth() {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(USER_ID_KEY);
        localStorage.removeItem(EMAIL_KEY);
        emit(TOKEN_EVENT);
        emit(USER_EVENT);
    },

    onTokenChange(cb: () => void) {
        const onEvt = () => cb();
        window.addEventListener(TOKEN_EVENT, onEvt);
        window.addEventListener("storage", (e) => {
            if (e.key === TOKEN_KEY) cb();
        });
        return () => window.removeEventListener(TOKEN_EVENT, onEvt);
    },

    onUserChange(cb: () => void) {
        const onEvt = () => cb();
        window.addEventListener(USER_EVENT, onEvt);
        window.addEventListener("storage", (e) => {
            if (e.key === USER_ID_KEY || e.key === EMAIL_KEY) cb();
        });
        return () => window.removeEventListener(USER_EVENT, onEvt);
    },
};
