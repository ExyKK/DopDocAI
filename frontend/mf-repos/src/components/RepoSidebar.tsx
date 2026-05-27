import React, { useEffect, useMemo, useState } from "react";
import { observer } from "mobx-react-lite";
import { useNavigate, useParams } from "react-router-dom";
import {
    Alert,
    Box,
    Button,
    Chip,
    Divider,
    LinearProgress,
    List,
    ListItemButton,
    ListItemText,
    Snackbar,
    TextField,
    Tooltip,
    Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import RefreshIcon from "@mui/icons-material/Refresh";
import type { RepositoryListItem } from "../app/RepoStore";
import { repoStore } from "../app/store";

function runStatus(repo: RepositoryListItem): string {
    return repo.latest_index_run?.status ?? (repo.active_snapshot_id ? "ready" : "not_indexed");
}

function statusColor(status?: string): "default" | "warning" | "success" | "error" {
    if (status === "ready" || status === "succeeded") return "success";
    if (status === "running" || status === "queued") return "warning";
    if (status === "failed" || status === "stale" || status === "canceled") return "error";
    return "default";
}

function statusLabel(repo: RepositoryListItem): string {
    const status = runStatus(repo);
    if (status === "succeeded") return "ready";
    if (status === "not_indexed") return "new";
    return status;
}

function statusPriority(repo: RepositoryListItem): number {
    const status = runStatus(repo);
    if (status === "running" || status === "queued") return 0;
    if (status === "ready" || status === "succeeded") return 1;
    return 2;
}

export const RepoSidebar = observer(function RepoSidebar() {
    const repos = repoStore;
    const navigate = useNavigate();
    const { repoId } = useParams<{ repoId: string }>();

    const [url, setUrl] = useState("");
    const [branch, setBranch] = useState("");
    const [snack, setSnack] = useState<string | null>(null);

    const sorted = useMemo(() => {
        return [...repos.repos].sort((a, b) => {
            const priority = statusPriority(a) - statusPriority(b);
            if (priority !== 0) return priority;
            return a.full_name.localeCompare(b.full_name);
        });
    }, [repos.repos]);

    async function onAdd() {
        try {
            const repo = await repos.startIndexing(url, branch.trim() || null);
            setUrl("");
            setBranch("");
            setSnack("Indexing started");
            navigate(`/app/repos/${repo.id}`);
        } catch (e) {
            setSnack(e instanceof Error ? e.message : "Failed to add repository");
        }
    }

    useEffect(() => {
        void repos.init();
        return () => repos.dispose();
    }, [repos]);

    return (
        <Box sx={{ p: 2, height: "100%", display: "flex", flexDirection: "column", gap: 2 }}>
            <Box>
                <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
                    <Typography variant="h6" sx={{ flex: 1 }}>
                        Repositories
                    </Typography>
                    <Tooltip title="Refresh">
                        <span>
                            <Button
                                size="small"
                                variant="text"
                                onClick={() => void repos.loadReposList()}
                                disabled={repos.loadingList}
                                sx={{ minWidth: 36, px: 1 }}
                            >
                                <RefreshIcon fontSize="small" />
                            </Button>
                        </span>
                    </Tooltip>
                </Box>

                <Box sx={{ display: "grid", gap: 1 }}>
                    <TextField
                        size="small"
                        label="GitHub repo URL"
                        value={url}
                        onChange={(e) => setUrl(e.target.value)}
                        fullWidth
                    />
                    <Box sx={{ display: "flex", gap: 1 }}>
                        <TextField
                            size="small"
                            label="Branch"
                            value={branch}
                            onChange={(e) => setBranch(e.target.value)}
                            sx={{ flex: 1 }}
                        />
                        <Button
                            variant="contained"
                            onClick={onAdd}
                            disabled={!url.trim() || repos.indexing}
                            startIcon={<AddIcon />}
                        >
                            Index
                        </Button>
                    </Box>
                </Box>
            </Box>

            {(repos.loadingList || repos.loadingStatuses || repos.indexing) && <LinearProgress />}

            <Divider />

            {repos.error && <Alert severity="error">{repos.error}</Alert>}

            <Box sx={{ flex: 1, minHeight: 0, overflow: "auto" }}>
                <List dense disablePadding>
                    {sorted.map((repo) => (
                        <ListItemButton
                            key={repo.id}
                            selected={repo.id === repoId}
                            onClick={() => navigate(`/app/repos/${repo.id}`)}
                            sx={{ alignItems: "flex-start", borderRadius: 1, mb: 0.5 }}
                        >
                            <ListItemText
                                primary={
                                    <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
                                        <Typography variant="body2" sx={{ flex: 1, wordBreak: "break-word" }}>
                                            {repo.full_name}
                                        </Typography>
                                        <Chip
                                            size="small"
                                            label={statusLabel(repo)}
                                            color={statusColor(runStatus(repo))}
                                        />
                                    </Box>
                                }
                                secondary={
                                    <Box sx={{ display: "grid", gap: 0.25, mt: 0.5 }}>
                                        <Typography variant="caption" color="text.secondary">
                                            {repo.selected_branch ?? repo.default_branch ?? "default branch"}
                                        </Typography>
                                        {repo.latest_index_run?.status === "running" && (
                                            <Typography variant="caption" color="text.secondary">
                                                {repo.latest_index_run.stage} · {repo.latest_index_run.progress_pct}%
                                            </Typography>
                                        )}
                                        {repo.latest_index_run?.error_message && (
                                            <Typography variant="caption" color="error">
                                                {repo.latest_index_run.error_message}
                                            </Typography>
                                        )}
                                    </Box>
                                }
                            />
                        </ListItemButton>
                    ))}
                </List>
            </Box>

            <Snackbar open={Boolean(snack)} autoHideDuration={2500} onClose={() => setSnack(null)}>
                <Alert severity="info" onClose={() => setSnack(null)}>
                    {snack}
                </Alert>
            </Snackbar>
        </Box>
    );
});

export default RepoSidebar;
