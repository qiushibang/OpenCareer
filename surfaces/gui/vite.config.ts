import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

// `base: "./"` makes built asset URLs relative, so the bundle loads from the `tauri://`
// origin in the desktop shell (absolute `/assets` 404s there); a server-hosted build is
// unaffected. Dev runs on a fixed port (1420) with strictPort so the Tauri webview always
// loads the vite instance Tauri itself spawns (a drifting port would make the window load a
// stale/other server). `tauri.conf.json` devUrl must match this.
export default defineConfig(({ command, mode }) => {
  const localMode = mode === "standalone";
  const alphaMode = mode === "alpha" || localMode;
  const alphaBackendPort = Number(process.env.VITE_ALPHA_BACKEND_PORT || "8765");
  const alphaUiPort = Number(process.env.VITE_ALPHA_UI_PORT || "1421");
  const sidecarPort = alphaMode ? alphaBackendPort : 8765;
  let devToken = "";
  if (command === "serve") {
    const state =
      process.env.COWORKER_STATE_DIR ||
      (process.platform === "win32"
        ? path.join(process.env.APPDATA || os.homedir(), "coworker")
        : path.join(os.homedir(), ".config", "coworker"));
    try {
      devToken = fs.readFileSync(path.join(state, `sidecar-${sidecarPort}.token`), "utf8").trim();
    } catch {
      // The Tauri dev shell injects its in-memory token at runtime. Plain browser dev
      // shows the normal startup retry until the standalone server/token file exists.
    }
  }
  const proxy = alphaMode
    ? {
        "/_openworker": {
          target: `http://127.0.0.1:${alphaBackendPort}`,
          changeOrigin: true,
          ws: true,
          rewrite: (requestPath: string) => requestPath.replace(/^\/_openworker/, ""),
          configure: (proxyServer: any) => {
            proxyServer.on("proxyReq", (proxyRequest: any) => {
              proxyRequest.setHeader("X-OpenWorker-Token", devToken);
            });
            proxyServer.on("proxyReqWs", (proxyRequest: any) => {
              proxyRequest.setHeader("X-OpenWorker-Token", devToken);
              // Local mode preserves the browser Origin for the backend's own check.
              if (!localMode) proxyRequest.setHeader("origin", `http://localhost:${alphaUiPort}`);
              proxyRequest.setHeader("sec-websocket-protocol", `openworker, ${devToken}`);
            });
          },
        },
      }
    : undefined;
  return {
    base: "./",
    // A local installation must never import a maintainer's .env or hosted build flags.
    envDir: localMode ? false : undefined,
    plugins: [react(), ...(localMode ? [{
      name: "opencareer-loopback-guard",
      configurePreviewServer(server: any) {
        const host = `127.0.0.1:${alphaUiPort}`;
        const permitted = (req: any) => req.headers.host === host
          && (!req.headers.origin || req.headers.origin === `http://${host}`)
          && (!req.headers["sec-fetch-site"] || ["same-origin", "none"].includes(req.headers["sec-fetch-site"]));
        server.middlewares.use((req: any, res: any, next: any) => {
          if (permitted(req)) return next();
          res.statusCode = 403;
          res.end("Local OpenCareer accepts same-origin loopback requests only.");
        });
        server.httpServer.prependListener("upgrade", (req: any, socket: any) => {
          if (!permitted(req)) {
            socket.end("HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n");
          }
        });
      },
    }] : [])],
    preview: localMode ? { host: "127.0.0.1", port: alphaUiPort, strictPort: true, cors: false, proxy } : undefined,
    server: {
      port: alphaMode ? alphaUiPort : 1420,
      strictPort: true,
      proxy,
      // cloudflared rewrites only the origin request's Host header to this
      // local-only name. Do not use `true`: Vite warns that it enables DNS rebinding.
      allowedHosts: alphaMode ? ["alpha.localhost"] : undefined,
    },
    // In alpha mode the Vite proxy keeps the sidecar token on this Mac.
    define: { __COWORKER_DEV_TOKEN__: JSON.stringify(alphaMode ? "" : devToken) },
    // Tauri CLI looks for these; harmless for the browser build.
    clearScreen: false,
    envPrefix: ["VITE_", "TAURI_"],
  };
});
