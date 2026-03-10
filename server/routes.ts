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

function setupSSEHeaders(res: any) {
  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");
  res.setHeader("X-Accel-Buffering", "no");
  res.flushHeaders();
}

/**
 * Non-streaming chat endpoint - collects full response before sending
 */
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

  // ─── Non-streaming Chat endpoint ─────────────────────────────────────
  app.post("/api/chat", async (req, res) => {
    const { messages } = req.body;

    if (!messages || !Array.isArray(messages)) {
      res.status(400).json({ error: "messages array is required" });
      return;
    }

    const { cfPath, apiKey } = getCFConfig();

    const requestBody = JSON.stringify({
      messages,
      stream: false,
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
            res.status(503).json({ error: "AI service rate limited, please try again" });
          }
          return;
        }

        let buffer = "";

        apiRes.on("data", (chunk: Buffer) => {
          buffer += chunk.toString();
        });

        apiRes.on("end", () => {
          try {
            const parsed = JSON.parse(buffer);
            const content =
              parsed.response ??
              parsed.choices?.[0]?.message?.content ??
              parsed.result?.response ??
              "";

            if (!content) {
              return res.status(500).json({ error: "Empty response from AI" });
            }

            // Send complete response (non-streaming)
            res.json({
              type: "message",
              content: content,
              timestamp: new Date().toISOString(),
            });
          } catch (error) {
            console.error("Parse error:", error);
            res.status(500).json({ error: "Failed to parse AI response" });
          }
        });

        apiRes.on("error", (err) => {
          console.error("CF API response error:", err);
          res.status(500).json({ error: "AI service error" });
        });
      });

      apiReq.on("error", (err) => {
        console.error("CF API request error:", err);
        res.status(500).json({ error: "AI service connection error" });
      });

      apiReq.write(requestBody);
      apiReq.end();
    };

    attemptRequest();
  });

  // ─── Agent endpoint with SSE (non-streaming per message) ────────────────────────────────────────────────────────
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
      const stderr = data.toString();
      console.error("[Agent stderr]:", stderr);
      if (!doneSent && !res.writableEnded) {
        res.write(`data: ${JSON.stringify({ type: "error", error: stderr })}\n\n`);
      }
    });

    proc.on("close", (code) => {
      if (!doneSent && !res.writableEnded) {
        res.write("data: [DONE]\n\n");
      }
      res.end();
      if (code !== 0) {
        console.error(`Agent process exited with code ${code}`);
      }
    });

    res.on("close", () => {
      proc.kill();
    });
  });

  // ─── Simple test endpoint ────────────────────────────────────────────
  app.get("/api/test", (req, res) => {
    res.json({
      message: "API is working",
      timestamp: new Date().toISOString(),
      cloudflareConfigured: !!startupCfg.apiKey,
    });
  });

  return createServer(app);
}
