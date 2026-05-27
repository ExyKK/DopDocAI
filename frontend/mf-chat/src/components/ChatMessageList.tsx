import React, { useCallback, useState } from "react";
import { Box, Chip, IconButton, Stack, Tooltip, Typography } from "@mui/material";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import type { ChatMessage, ChatMessageSource } from "@rag/shared";

import { MarkdownRenderer } from "./MarkdownRenderer";

async function copyToClipboard(text: string) {
    try {
        await navigator.clipboard.writeText(text);
        return;
    } catch {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.left = "-9999px";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
    }
}

function sourceLabel(source: ChatMessageSource) {
    const label = source.citation_label ? `${source.citation_label} ` : "";
    const path = source.file_path ?? source.symbol_name ?? source.source_kind;
    const range =
        source.start_line != null
            ? `:${source.start_line}${source.end_line != null && source.end_line !== source.start_line ? `-${source.end_line}` : ""}`
            : "";
    return `${label}${path}${range}`;
}

export function ChatMessageList({
    messages,
    loading,
    bottomRef,
}: {
    messages: ChatMessage[];
    loading: boolean;
    bottomRef: React.RefObject<HTMLDivElement | null>;
}) {
    const [copiedId, setCopiedId] = useState<string | null>(null);

    const onCopy = useCallback(async (id: string, text: string) => {
        await copyToClipboard(text);
        setCopiedId(id);
        window.setTimeout(() => {
            setCopiedId((cur) => (cur === id ? null : cur));
        }, 1200);
    }, []);

    return (
        <Box sx={{ flex: 1, minHeight: 0, overflow: "auto", pr: 1, opacity: loading ? 0.7 : 1 }}>
            {messages.length === 0 && !loading && (
                <Typography color="text.secondary" sx={{ py: 4 }}>
                    Ask a question about this repository to start a grounded chat.
                </Typography>
            )}

            {messages.map((message) => {
                const isAssistant = message.role === "assistant";
                const isUser = message.role === "user";
                const sources = (message.sources ?? []).filter((source) => source.used_in_answer).slice(0, 6);

                return (
                    <Box
                        key={message.id}
                        sx={{
                            mb: 2,
                            display: "flex",
                            flexDirection: "column",
                            alignItems: isUser ? "flex-end" : "flex-start",
                        }}
                    >
                        <Box
                            sx={{
                                maxWidth: "min(940px, 100%)",
                                width: "fit-content",
                                p: 1.5,
                                borderRadius: 2,
                                border: "1px solid rgba(255,255,255,0.12)",
                                backgroundColor: isUser ? "rgba(144, 202, 249, 0.12)" : "transparent",
                                borderColor: isUser ? "rgba(144, 202, 249, 0.25)" : "rgba(255,255,255,0.12)",
                            }}
                        >
                            <Box
                                sx={{
                                    "& p": { m: 0, mb: 1, whiteSpace: "pre-wrap" },
                                    "& p:last-child": { mb: 0 },
                                    "& ul, & ol": { m: 0, pl: 3, mb: 1 },
                                    "& li:last-child": { mb: 0 },
                                }}
                            >
                                <MarkdownRenderer>{message.content_markdown}</MarkdownRenderer>
                            </Box>
                        </Box>

                        {isAssistant && (
                            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mt: 0.75, maxWidth: "940px" }}>
                                <Tooltip title={copiedId === message.id ? "Copied" : "Copy"}>
                                    <IconButton
                                        size="small"
                                        onClick={() => void onCopy(message.id, message.content_markdown)}
                                        aria-label="Copy assistant answer"
                                    >
                                        <ContentCopyIcon fontSize="inherit" />
                                    </IconButton>
                                </Tooltip>
                                {sources.map((source) => (
                                    <Chip key={`${message.id}-${source.ordinal}`} size="small" label={sourceLabel(source)} />
                                ))}
                            </Stack>
                        )}
                    </Box>
                );
            })}

            <div ref={bottomRef} />
        </Box>
    );
}
