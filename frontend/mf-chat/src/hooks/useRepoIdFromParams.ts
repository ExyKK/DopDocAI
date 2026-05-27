import { useParams } from "react-router-dom";

export function useRepoIdFromParams() {
    const { repoId } = useParams<{ repoId: string }>();
    return repoId?.trim() || null;
}
