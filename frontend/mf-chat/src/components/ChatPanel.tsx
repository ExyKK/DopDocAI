import React, { useEffect, useState } from "react";
import { observer } from "mobx-react-lite";
import {
    Alert,
    Box,
    Button,
    Chip,
    CircularProgress,
    Divider,
    LinearProgress,
    Stack,
    Tab,
    Tabs,
    Typography,
} from "@mui/material";
import AutoStoriesIcon from "@mui/icons-material/AutoStories";
import ChatIcon from "@mui/icons-material/Chat";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import RefreshIcon from "@mui/icons-material/Refresh";

import { chatStore } from "../app/store";
import { useRepoIdFromParams } from "../hooks/useRepoIdFromParams";
import { useAutoScroll } from "../hooks/useAutoScroll";

import { ChatRoot } from "./ChatRoot";
import { ChatStatus } from "./ChatStatus";
import { ChatMessageList } from "./ChatMessageList";
import { ChatComposer } from "./ChatComposer";
import { MarkdownRenderer } from "./MarkdownRenderer";

function statusColor(status?: string | null): "default" | "primary" | "success" | "error" | "warning" {
    if (status === "succeeded") return "success";
    if (status === "failed") return "error";
    if (status === "running") return "primary";
    if (status === "queued") return "warning";
    return "default";
}

function progressLabel(progressPct?: number | null) {
    return `${Math.max(0, Math.min(100, progressPct ?? 0))}%`;
}

export const ChatPanel = observer(function ChatPanel() {
    const chat = chatStore;
    const repoId = useRepoIdFromParams();
    const bottomRef = useAutoScroll(chat.messages.length);
    const [tab, setTab] = useState(0);

    useEffect(() => {
        void chat.openRepo(repoId);
    }, [repoId, chat]);

    if (!repoId) {
        return (
            <ChatRoot>
                <Box sx={{ py: 8, color: "text.secondary" }}>
                    <Typography variant="h6" sx={{ mb: 1 }}>
                        Select or index a repository
                    </Typography>
                    <Typography>
                        The workspace will show documentation generation status, generated artifacts and repository chat.
                    </Typography>
                </Box>
            </ChatRoot>
        );
    }

    const indexRun = chat.latestIndexRun;
    const documentationRun = chat.latestDocumentationRun;

    return (
        <ChatRoot>
            <Stack direction="row" alignItems="flex-start" justifyContent="space-between" gap={2} sx={{ mb: 2 }}>
                <Box sx={{ minWidth: 0 }}>
                    <Typography variant="h6" noWrap>
                        {chat.repo?.full_name ?? "Repository"}
                    </Typography>
                    <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mt: 1 }}>
                        <Chip
                            size="small"
                            label={chat.hasReadySnapshot ? "ready snapshot" : chat.isIndexing ? "indexing" : "not ready"}
                            color={chat.hasReadySnapshot ? "success" : chat.isIndexing ? "primary" : "default"}
                        />
                        {indexRun && <Chip size="small" label={`index: ${indexRun.status}`} color={statusColor(indexRun.status)} />}
                        {documentationRun && (
                            <Chip
                                size="small"
                                label={`docs: ${documentationRun.status}`}
                                color={statusColor(documentationRun.status)}
                            />
                        )}
                        {documentationRun?.effective_template_kind && (
                            <Chip size="small" label={documentationRun.effective_template_kind} />
                        )}
                    </Stack>
                </Box>

                <Stack direction="row" spacing={1} sx={{ flexShrink: 0 }}>
                    <Button
                        size="small"
                        variant="outlined"
                        startIcon={<RefreshIcon />}
                        onClick={() => void chat.refresh()}
                        disabled={chat.loading}
                    >
                        Refresh
                    </Button>
                    <Button
                        size="small"
                        variant="contained"
                        startIcon={<PlayArrowIcon />}
                        onClick={() => void chat.generateDocumentation()}
                        disabled={!chat.canGenerateDocumentation}
                    >
                        Generate docs
                    </Button>
                </Stack>
            </Stack>

            {chat.loading && (
                <Alert severity="info" sx={{ mb: 2 }}>
                    Loading repository workspace...
                </Alert>
            )}
            {chat.error && (
                <Alert severity="error" sx={{ mb: 2 }}>
                    {chat.error}
                </Alert>
            )}

            {(chat.isIndexing || chat.isDocumenting) && (
                <Box sx={{ mb: 2 }}>
                    <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 0.5 }}>
                        <Typography variant="body2" color="text.secondary">
                            {chat.isDocumenting
                                ? documentationRun?.stage ?? "Generating documentation"
                                : indexRun?.stage ?? "Indexing repository"}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                            {progressLabel(chat.isDocumenting ? documentationRun?.progress_pct : indexRun?.progress_pct)}
                        </Typography>
                    </Stack>
                    <LinearProgress
                        variant="determinate"
                        value={chat.isDocumenting ? documentationRun?.progress_pct ?? 0 : indexRun?.progress_pct ?? 0}
                    />
                </Box>
            )}

            <Tabs value={tab} onChange={(_, value) => setTab(value)} sx={{ borderBottom: "1px solid", borderColor: "divider" }}>
                <Tab icon={<AutoStoriesIcon fontSize="small" />} iconPosition="start" label="Documentation" />
                <Tab icon={<ChatIcon fontSize="small" />} iconPosition="start" label="Chat" />
            </Tabs>

            {tab === 0 && (
                <Box sx={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column", pt: 2 }}>
                    {chat.docsError && (
                        <Alert severity="error" sx={{ mb: 2 }}>
                            {chat.docsError}
                        </Alert>
                    )}

                    {!chat.hasReadySnapshot && (
                        <Alert severity="warning" sx={{ mb: 2 }}>
                            Indexing must finish before documentation can be generated.
                        </Alert>
                    )}

                    {documentationRun?.error_message && documentationRun.status === "failed" && (
                        <Alert severity="error" sx={{ mb: 2 }}>
                            {documentationRun.error_message}
                        </Alert>
                    )}

                    {chat.documentationArtifacts.length > 0 && (
                        <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 2 }}>
                            {chat.documentationArtifacts.map((artifact) => (
                                <Button
                                    key={artifact.id}
                                    size="small"
                                    variant={artifact.id === chat.selectedArtifactId ? "contained" : "outlined"}
                                    onClick={() => void chat.selectArtifact(artifact.id)}
                                >
                                    {chat.documentLabel(artifact)}
                                </Button>
                            ))}
                        </Stack>
                    )}

                    <Box sx={{ flex: 1, minHeight: 0, overflow: "auto", pr: 1 }}>
                        {chat.loadingArtifact && (
                            <Stack direction="row" spacing={1} alignItems="center" sx={{ color: "text.secondary" }}>
                                <CircularProgress size={18} />
                                <Typography>Loading artifact...</Typography>
                            </Stack>
                        )}

                        {!chat.loadingArtifact && chat.artifactContent && (
                            <Box
                                sx={{
                                    "& h1, & h2, & h3": { mt: 2, mb: 1 },
                                    "& h1:first-of-type, & h2:first-of-type": { mt: 0 },
                                    "& p": { lineHeight: 1.7 },
                                    "& table": { borderCollapse: "collapse", width: "100%", my: 2 },
                                    "& th, & td": { border: "1px solid", borderColor: "divider", p: 1, verticalAlign: "top" },
                                    "& code": { wordBreak: "break-word" },
                                }}
                            >
                                <MarkdownRenderer>{chat.artifactContent}</MarkdownRenderer>
                            </Box>
                        )}

                        {!chat.loadingArtifact && !chat.artifactContent && (
                            <Typography color="text.secondary" sx={{ py: 4 }}>
                                {chat.hasReadySnapshot
                                    ? "Generate documentation to view repository artifacts here."
                                    : "Waiting for a ready indexed snapshot."}
                            </Typography>
                        )}
                    </Box>
                </Box>
            )}

            {tab === 1 && (
                <Box sx={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column", pt: 2 }}>
                    {!chat.canChat && (
                        <Alert severity="warning" sx={{ mb: 2 }}>
                            Chat is available after the repository has a ready indexed snapshot.
                        </Alert>
                    )}

                    <ChatStatus error={chat.error} loading={chat.loading} />
                    <ChatMessageList messages={chat.messages} loading={chat.loading} bottomRef={bottomRef} />

                    <Divider sx={{ my: 2 }} />

                    <ChatComposer
                        disabled={!chat.canChat || chat.loading || chat.sending}
                        onSend={(content) => chat.sendMessage(content)}
                    />
                </Box>
            )}
        </ChatRoot>
    );
});

export default ChatPanel;
