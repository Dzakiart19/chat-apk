import type { Express } from "express";
import { createServer, type Server } from "node:http";
import { spawn } from "node:child_process";
import * as https from "node:https";
import { randomUUID } from "node:crypto";

function getCFConfig() {
  const accountId = process.env.CF_ACCOUNT_ID || "";
  const gatewayName = process.env.CF_GATEWAY_NAME || "";
  const model = process.env.CF_MODEL || "@cf/meta/llama-3-8b-instruct";
  const agentModel = process.env.CF_AGENT_MODEL || "@cf/meta/llama-3.1-70b-instruct";
  const apiKey = process.env.CF_API_KEY || "";
  const cfPath = `/v1/${accountId}/${gatewayName}/workers-ai/run/${model}`;
  return { cfPath, apiKey, model, agentModel };
}

function sendSSEError(res: any, message: string) {
  if (!res.writableEnded) {
    res.write(`data: ${JSON.stringify({ type: "error", error: message })}\n\n`);
    res.write("data: [DONE]\n\n");
    res.end();
  }
}

function setupSSEHeaders(res: any) {
  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");
  res.setHeader("X-Accel-Buffering", "no");
  res.flushHeaders();
}

export async function registerRoutes(app: Express): Promise<Server> {
  const startupCfg = getCFConfig();
  if (!startupCfg.apiKey) {
    console.warn("[WARNING] CF_API_KEY is not set. AI features will not work.");
  }

  app.get("/status", (_req, res) => {
    res.json({ status: "ok", timestamp: new Date().toISOString() });
  });

  app.get("/api/status", (_req, res) => {
    res.json({ status: "ok", timestamp: new Date().toISOString() });
  });

  // ─── Chat endpoint — streams Cloudflare Workers AI SSE ─────────────────
  app.post("/api/chat", (req, res) => {
    const { messages } = req.body;

    if (!messages || !Array.isArray(messages)) {
      res.status(400).json({ error: "messages array is required" });
      return;
    }

    setupSSEHeaders(res);

    const { cfPath, apiKey } = getCFConfig();

    const requestBody = JSON.stringify({
      messages,
      stream: true,
      max_tokens: 4096,
    });

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
        if (
          apiRes.statusCode === 429 ||
          (apiRes.statusCode && apiRes.statusCode >= 500)
        ) {
          const retryAfter = parseInt(
            (apiRes.headers["retry-after"] as string) || "0",
            10
          );
          const wait =
            retryAfter > 0
              ? retryAfter * 1000
              : Math.pow(2, retryCount) * 1000;
          apiRes.resume();

          if (retryCount < maxRetries) {
            retryCount++;
            console.warn(`CF API ${apiRes.statusCode}, retry ${retryCount}/${maxRetries} in ${wait}ms`);
            setTimeout(attemptRequest, wait);
          } else {
            sendSSEError(res, "AI service rate limited, please try again");
          }
          return;
        }

        let apiBuffer = "";
        let streamDone = false;

        apiRes.on("data", (chunk: Buffer) => {
          apiBuffer += chunk.toString();
          const lines = apiBuffer.split("\n");
          apiBuffer = lines.pop() || "";

          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed || !trimmed.startsWith("data: ")) continue;

            const data = trimmed.slice(6);
            if (data === "[DONE]") {
              streamDone = true;
              if (!res.writableEnded) {
                res.write("data: [DONE]\n\n");
                res.end();
              }
              return;
            }

            try {
              const parsed = JSON.parse(data);
              const content =
                parsed.response ??
                parsed.choices?.[0]?.delta?.content ??
                parsed.content ??
                "";

              if (
                content &&
                (content.includes("Ratelimit") || content.includes("ratelimit"))
              ) {
                apiRes.destroy();
                if (retryCount < maxRetries) {
                  retryCount++;
                  const wait = Math.pow(2, retryCount) * 1000;
                  setTimeout(attemptRequest, wait);
                } else {
                  sendSSEError(res, "AI service rate limited, please try again later");
                }
                return;
              }

              if (content) {
                res.write(`data: ${JSON.stringify({ content })}\n\n`);
              }
            } catch {
              // Skip malformed JSON chunks
            }
          }
        });

        apiRes.on("end", () => {
          if (!streamDone && !res.writableEnded) {
            res.write("data: [DONE]\n\n");
            res.end();
          }
        });

        apiRes.on("error", (err) => {
          console.error("CF API response error:", err);
          sendSSEError(res, "AI service error");
        });
      });

      apiReq.on("error", (err) => {
        console.error("CF API request error:", err);
        sendSSEError(res, "AI service connection error");
      });

      apiReq.write(requestBody);
      apiReq.end();

      res.on("close", () => {
        apiReq.destroy();
      });
    };

    attemptRequest();
  });

  // ─── Agent endpoint — spawns async Python agent ────────────────────────
  app.post("/api/agent", (req, res) => {
    const { message, messages, model, attachments, session_id, resume_from_session } = req.body;

    if (!message && (!messages || !Array.isArray(messages))) {
      res.status(400).json({ error: "message or messages array is required" });
      return;
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
      },
    });

    const input = JSON.stringify({
      message: message || "",
      messages: messages || [],
      model: agentModel,
      attachments: attachments || [],
      session_id: sid,
      resume_from_session: resume_from_session || null,
    });
    proc.stdin.write(input);
    proc.stdin.end();

    let buffer = "";
    let doneSent = false;

    res.write(`data: ${JSON.stringify({ type: "session", session_id: sid })}\n\n`);

    proc.stdout.on("data", (data: Buffer) => {
      buffer += data.toString();
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const parsed = JSON.parse(line);
          if (parsed.type === "done") {
            doneSent = true;
            res.write("data: [DONE]\n\n");
          } else {
            res.write(`data: ${JSON.stringify(parsed)}\n\n`);
          }
        } catch {
          // Skip malformed JSON
        }
      }
    });

    proc.stderr.on("data", (data: Buffer) => {
      console.error("agent stderr:", data.toString());
    });

    proc.on("close", () => {
      if (!res.writableEnded) {
        if (!doneSent) {
          res.write("data: [DONE]\n\n");
        }
        res.end();
      }
    });

    proc.on("error", (err) => {
      console.error("agent process error:", err);
      sendSSEError(res, "Agent service error");
    });

    res.on("close", () => {
      if (!proc.killed) {
        proc.kill();
      }
    });
  });

  // ─── Session management endpoints ─────────────────────────────────────

  app.get("/api/sessions", async (req, res) => {
    try {
      const limit = parseInt((req.query.limit as string) || "20", 10);
      const status = (req.query.status as string) || undefined;

      const result = await runPythonScript("list_sessions", { limit, status });
      res.json(result);
    } catch (err) {
      console.error("list sessions error:", err);
      res.status(500).json({ error: "Failed to list sessions", sessions: [] });
    }
  });

  app.get("/api/sessions/:sessionId", async (req, res) => {
    try {
      const result = await runPythonScript("get_session", {
        session_id: req.params.sessionId,
      });
      if (!result) {
        res.status(404).json({ error: "Session not found" });
        return;
      }
      res.json(result);
    } catch (err) {
      console.error("get session error:", err);
      res.status(500).json({ error: "Failed to get session" });
    }
  });

  app.post("/api/sessions/:sessionId/rollback", async (req, res) => {
    try {
      const { to_step_id } = req.body;
      const result = await runPythonScript("rollback_session", {
        session_id: req.params.sessionId,
        to_step_id: to_step_id || null,
      });
      res.json(result || { success: false, error: "Session not found" });
    } catch (err) {
      console.error("rollback error:", err);
      res.status(500).json({ error: "Rollback failed" });
    }
  });

  app.post("/api/sessions/:sessionId/resume", (req, res) => {
    const { message } = req.body;
    const sessionId = req.params.sessionId;

    if (!message) {
      res.status(400).json({ error: "message is required for resume" });
      return;
    }

    setupSSEHeaders(res);

    const { apiKey, agentModel } = getCFConfig();

    const proc = spawn("python3", ["-u", "-m", "server.agent.agent_flow"], {
      stdio: ["pipe", "pipe", "pipe"],
      cwd: process.cwd(),
      env: {
        ...process.env,
        CF_API_KEY: apiKey,
        CF_AGENT_MODEL: agentModel,
        PYTHONPATH: process.cwd(),
        PYTHONUNBUFFERED: "1",
      },
    });

    const input = JSON.stringify({
      message,
      messages: [],
      model: agentModel,
      attachments: [],
      session_id: sessionId,
      resume_from_session: sessionId,
    });
    proc.stdin.write(input);
    proc.stdin.end();

    let buffer = "";
    let doneSent = false;

    proc.stdout.on("data", (data: Buffer) => {
      buffer += data.toString();
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const parsed = JSON.parse(line);
          if (parsed.type === "done") {
            doneSent = true;
            res.write("data: [DONE]\n\n");
          } else {
            res.write(`data: ${JSON.stringify(parsed)}\n\n`);
          }
        } catch {
          // Skip
        }
      }
    });

    proc.stderr.on("data", (data: Buffer) => {
      console.error("resume agent stderr:", data.toString());
    });

    proc.on("close", () => {
      if (!res.writableEnded) {
        if (!doneSent) res.write("data: [DONE]\n\n");
        res.end();
      }
    });

    proc.on("error", (err) => {
      console.error("resume process error:", err);
      sendSSEError(res, "Resume service error");
    });

    res.on("close", () => {
      if (!proc.killed) proc.kill();
    });
  });

  app.get("/api/sessions/:sessionId/events", async (req, res) => {
    try {
      const event_type = (req.query.event_type as string) || undefined;
      const result = await runPythonScript("get_session_events", {
        session_id: req.params.sessionId,
        event_type: event_type || null,
      });
      res.json(result || []);
    } catch (err) {
      console.error("get events error:", err);
      res.status(500).json({ error: "Failed to get events", events: [] });
    }
  });

  const httpServer = createServer(app);
  return httpServer;
}

// ─── Python Session Script Bridge ─────────────────────────────────────────
async function runPythonScript(
  action: string,
  params: Record<string, any>
): Promise<any> {
  return new Promise((resolve, reject) => {
    const proc = spawn("python3", ["-c", `
import sys, json, asyncio
sys.path.insert(0, '.')

async def main():
    action = ${JSON.stringify(action)}
    params = json.loads(sys.stdin.read())
    try:
        from server.agent.services.session_service import get_session_service
        svc = await get_session_service()
        if action == 'list_sessions':
            result = await svc.list_sessions(
                limit=params.get('limit', 20),
                status=params.get('status')
            )
            print(json.dumps(result, default=str))
        elif action == 'get_session':
            result = await svc.get_session(params['session_id'])
            print(json.dumps(result, default=str))
        elif action == 'rollback_session':
            result = await svc.rollback_session(
                params['session_id'],
                to_step_id=params.get('to_step_id')
            )
            print(json.dumps(result, default=str))
        elif action == 'get_session_events':
            result = await svc.get_session_events(
                params['session_id'],
                event_type=params.get('event_type')
            )
            print(json.dumps(result, default=str))
        else:
            print(json.dumps({'error': 'Unknown action'}))
    except Exception as e:
        print(json.dumps({'error': str(e)}))

asyncio.run(main())
`],
      {
        stdio: ["pipe", "pipe", "pipe"],
        cwd: process.cwd(),
        env: { ...process.env, PYTHONPATH: process.cwd() },
      }
    );

    proc.stdin.write(JSON.stringify(params));
    proc.stdin.end();

    let output = "";
    let errOutput = "";

    proc.stdout.on("data", (d: Buffer) => { output += d.toString(); });
    proc.stderr.on("data", (d: Buffer) => { errOutput += d.toString(); });

    proc.on("close", (code) => {
      if (errOutput) console.error("python session script stderr:", errOutput);
      try {
        const lines = output.trim().split("\n").filter(Boolean);
        const lastLine = lines[lines.length - 1];
        resolve(JSON.parse(lastLine || "null"));
      } catch {
        resolve(null);
      }
    });

    proc.on("error", reject);

    setTimeout(() => {
      if (!proc.killed) proc.kill();
      reject(new Error("Python script timeout"));
    }, 15000);
  });
}
