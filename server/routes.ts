import { createServer, type Server } from "node:http";
import { spawn, type ChildProcess } from "node:child_process";
import * as https from "node:https";
import * as net from "node:net";
import { randomUUID } from "node:crypto";

// ─── VNC / Virtual Display Management ────────────────────────────────────────
const VNC_DISPLAY = ":99";
const VNC_RFB_PORT = 5910;
const VNC_WS_PORT = 6081;

let _xvfbProc: ChildProcess | null = null;
let _x11vncProc: ChildProcess | null = null;
let _websockifyProc: ChildProcess | null = null;
let _vncReady = false;

function startVNCStack() {
  console.log("[VNC] Starting virtual display stack...");

  _xvfbProc = spawn("Xvfb", [VNC_DISPLAY, "-screen", "0", "1280x720x24", "-nolisten", "tcp"], {
    stdio: "ignore",
    detached: false,
  });
  _xvfbProc.on("error", (e: Error) => console.warn("[VNC] Xvfb error:", e.message));

  setTimeout(() => {
    _x11vncProc = spawn("x11vnc", [
      "-display", VNC_DISPLAY,
      "-nopw", "-listen", "localhost",
      "-rfbport", String(VNC_RFB_PORT),
      "-forever", "-quiet", "-noxdamage", "-shared",
    ], { stdio: "ignore", detached: false });
    _x11vncProc.on("error", (e: Error) => console.warn("[VNC] x11vnc error:", e.message));

    setTimeout(() => {
      _websockifyProc = spawn("python3", [
        "-m", "websockify",
        "--heartbeat", "30",
        `0.0.0.0:${VNC_WS_PORT}`,
        `localhost:${VNC_RFB_PORT}`,
      ], { stdio: "ignore", detached: false });
      _websockifyProc.on("error", (e: Error) => console.warn("[VNC] websockify error:", e.message));
      _vncReady = true;
      console.log(`[VNC] Stack ready → display=${VNC_DISPLAY} ws=:${VNC_WS_PORT}`);
    }, 2500);
  }, 1500);
}

function stopVNCStack() {
  [_websockifyProc, _x11vncProc, _xvfbProc].forEach(p => { try { p?.kill(); } catch {} });
}

// Properly forward WebSocket upgrade to local websockify
function proxyVNCUpgrade(req: any, socket: net.Socket, head: Buffer) {
  const target = net.connect(VNC_WS_PORT, "127.0.0.1");

  target.on("connect", () => {
    // Re-send the original HTTP upgrade request to websockify
    const headerLines = [`GET / HTTP/1.1`];
    for (const [k, v] of Object.entries(req.headers)) {
      headerLines.push(`${k}: ${v}`);
    }
    headerLines.push("", "");
    target.write(headerLines.join("\r\n"));
    if (head && head.length > 0) target.write(head);
  });

  target.on("error", () => { try { socket.destroy(); } catch {} });
  socket.on("error", () => { try { target.destroy(); } catch {} });

  // Bidirectional pipe after handshake
  target.pipe(socket);
  socket.pipe(target);
}

function getCFConfig() {
  const accountId = process.env.CF_ACCOUNT_ID || "";
  const gatewayName = process.env.CF_GATEWAY_NAME || "";
  const model = process.env.CF_MODEL || "@cf/meta/llama-3-8b-instruct";
  const agentModel = process.env.CF_AGENT_MODEL || "@cf/meta/llama-3.1-70b-instruct";
  const apiKey = process.env.CF_API_KEY || "";
  const cfPath = `/v1/${accountId}/${gatewayName}/workers-ai/run/${model}`;
  return { cfPath, apiKey, model, agentModel };
}

function setupSSEHeaders(res: any) {
  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");
  res.setHeader("X-Accel-Buffering", "no");
  res.flushHeaders();
}

export async function registerRoutes(app: any): Promise<Server> {
  const startupCfg = getCFConfig();
  if (!startupCfg.apiKey) {
    console.warn("[WARNING] CF_API_KEY is not set. AI features will not work.");
  }

  startVNCStack();

  app.get("/status", (_req: any, res: any) => {
    res.json({ status: "ok", timestamp: new Date().toISOString() });
  });

  app.get("/api/status", (_req: any, res: any) => {
    res.json({ status: "ok", timestamp: new Date().toISOString(), vncReady: _vncReady });
  });

  // ─── Chat endpoint ─────────────────────────────────────────────────────────
  app.post("/api/chat", async (req: any, res: any) => {
    const { messages } = req.body;
    if (!messages || !Array.isArray(messages)) {
      return res.status(400).json({ error: "messages array is required" });
    }

    const { cfPath, apiKey } = getCFConfig();
    const requestBody = JSON.stringify({ messages, stream: false, max_tokens: 4096 });
    const options: https.RequestOptions = {
      hostname: "gateway.ai.cloudflare.com",
      port: 443,
      path: cfPath,
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
        "Content-Length": Buffer.byteLength(requestBody),
      },
    };

    let retryCount = 0;
    const maxRetries = 4;
    const attemptRequest = () => {
      const apiReq = https.request(options, (apiRes) => {
        if (apiRes.statusCode === 429 || (apiRes.statusCode && apiRes.statusCode >= 500)) {
          const wait = Math.pow(2, retryCount) * 1000;
          apiRes.resume();
          if (retryCount < maxRetries) { retryCount++; setTimeout(attemptRequest, wait); }
          else res.status(503).json({ error: "AI service rate limited, please try again" });
          return;
        }
        let buffer = "";
        apiRes.on("data", (chunk: Buffer) => { buffer += chunk.toString(); });
        apiRes.on("end", () => {
          try {
            const parsed = JSON.parse(buffer);
            const content = parsed.response ?? parsed.choices?.[0]?.message?.content ?? parsed.result?.response ?? "";
            if (!content) return res.status(500).json({ error: "Empty response from AI" });
            res.json({ type: "message", content, timestamp: new Date().toISOString() });
          } catch { res.status(500).json({ error: "Failed to parse AI response" }); }
        });
        apiRes.on("error", () => res.status(500).json({ error: "AI service error" }));
      });
      apiReq.on("error", () => res.status(500).json({ error: "AI service connection error" }));
      apiReq.write(requestBody);
      apiReq.end();
    };
    attemptRequest();
  });

  // ─── Agent endpoint with SSE ───────────────────────────────────────────────
  app.post("/api/agent", (req: any, res: any) => {
    const { message, messages, attachments, session_id, resume_from_session } = req.body;
    if (!message && (!messages || !Array.isArray(messages))) {
      return res.status(400).json({ error: "message or messages array is required" });
    }

    setupSSEHeaders(res);

    const { apiKey, agentModel } = getCFConfig();
    const sid = session_id || randomUUID();

    const proc = spawn("python3", ["-u", "-m", "server.agent.agent_flow"], {
      stdio: ["pipe", "pipe", "pipe"],
      cwd: process.cwd(),
      env: {
        ...process.env,
        CF_API_KEY: apiKey,
        CF_AGENT_MODEL: agentModel,
        PYTHONPATH: process.cwd(),
        PYTHONUNBUFFERED: "1",
        DISPLAY: VNC_DISPLAY,
      },
    });

    proc.stdin.write(JSON.stringify({
      message: message || "",
      messages: messages || [],
      model: agentModel,
      attachments: attachments || [],
      session_id: sid,
      resume_from_session: resume_from_session || null,
    }));
    proc.stdin.end();

    let buf = "";
    let doneSent = false;

    res.write(`data: ${JSON.stringify({ type: "session", session_id: sid, vnc_ws_port: VNC_WS_PORT })}\n\n`);

    proc.stdout.on("data", (data: Buffer) => {
      buf += data.toString();
      const lines = buf.split("\n");
      buf = lines.pop() || "";
      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const parsed = JSON.parse(line);
          if (parsed.type === "done") { doneSent = true; res.write("data: [DONE]\n\n"); }
          else res.write(`data: ${JSON.stringify(parsed)}\n\n`);
        } catch {}
      }
    });

    proc.stderr.on("data", (data: Buffer) => {
      const stderr = data.toString();
      console.error("[Agent stderr]:", stderr);
      const BENIGN = [/redis/i, /mongodb/i, /motor/i, /DNS/i, /Name or service not known/i,
        /ConnectionRefusedError/i, /\[CacheStore\]/i, /\[SessionStore\]/i, /\[SessionService\]/i,
        /WARNING:/i, /DeprecationWarning/i, /connection failed/i, /Traceback/i];
      if (!BENIGN.some(p => p.test(stderr)) && !doneSent && !res.writableEnded) {
        res.write(`data: ${JSON.stringify({ type: "error", error: stderr })}\n\n`);
      }
    });

    proc.on("close", (code: number | null) => {
      if (!doneSent && !res.writableEnded) res.write("data: [DONE]\n\n");
      res.end();
      if (code !== 0) console.error(`Agent process exited with code ${code}`);
    });

    res.on("close", () => { proc.kill(); });
  });

  app.get("/api/test", (_req: any, res: any) => {
    res.json({ message: "API is working", timestamp: new Date().toISOString(), cloudflareConfigured: !!startupCfg.apiKey, vncReady: _vncReady });
  });

  const httpServer = createServer(app);

  // WebSocket upgrade → proxy to local websockify/VNC
  httpServer.on("upgrade", (req, socket, head) => {
    const url = req.url || "";
    if (url === "/vnc-ws" || url.startsWith("/vnc-ws?")) {
      proxyVNCUpgrade(req, socket as net.Socket, head);
    } else {
      (socket as net.Socket).destroy();
    }
  });

  process.on("exit", stopVNCStack);
  process.on("SIGINT", () => { stopVNCStack(); process.exit(0); });
  process.on("SIGTERM", () => { stopVNCStack(); process.exit(0); });

  return httpServer;
}
