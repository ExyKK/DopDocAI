import {defineConfig} from "vite";
import react from "@vitejs/plugin-react";
import {federation} from '@module-federation/vite';

export default defineConfig({
    plugins: [
        react(),
        federation({
            dev: true,
            name: "host",
            manifest: true,
            remotes: {
                mf_repos: {
                    type: "module",
                    name: "mf_repos",
                    entry: "http://localhost:5174/remoteEntry.js",
                },
                mf_chat: {
                    type: "module",
                    name: "mf_chat",
                    entry: "http://localhost:5175/remoteEntry.js",
                },
            },
            shared: {
                "@rag/shared": {singleton: true},
                "react": {singleton: true},
                "react-dom": {singleton: true},
                "mobx": {singleton: true},
                "react-router-dom": {singleton: true},
                "mobx-react-lite": {singleton: true}
            }
        })
    ],
    server: {
        port: 5173,
        strictPort: true,
        proxy: {
            "/api": {
                target: "http://localhost:18000",
                changeOrigin: true,
                secure: false,
            },
        },
    },
    build: {
        modulePreload: false,
        target: 'chrome89',
        minify: false,
        cssCodeSplit: false
    }
});
