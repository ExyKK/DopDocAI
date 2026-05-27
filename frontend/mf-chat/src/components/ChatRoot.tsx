import React from "react";
import { Box } from "@mui/material";

export function ChatRoot({ children }: { children: React.ReactNode }) {
    return (
        <Box sx={{ flex: 1, p: 2, width: "100%", display: "flex", flexDirection: "column", minHeight: 0 }}>
            {children}
        </Box>
    );
}
