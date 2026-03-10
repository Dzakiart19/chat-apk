import type { Express } from "express";
import { createServer, type Server } from "node:http";
import { spawn } from "node:child_process";
import * as https from "node:https";

function getCFConfig() {
  const accountId = process.env.CF_ACCOUNT_ID || "";
  const gatewayName = process.env.CF_GATEWAY_NAME || "";
  const model = process.env.CF_MODEL || "@cf/meta/llama-3-8b-instruct";
  const apiKey = process.env.CF_API_KEY || "";
  // Build path directly — do NOT encodeURIComponent the model (slashes are part of path)
  const cfPath = `/v1/${accountId}/${gatewayName}/workers-ai/run/${model}`;
  return { cfPath, apiKey, model };
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

  // Chat endpoint — streams Cloudflare Workers AI SSE to client
  app.post("/api/chat", (req, res) => {
    const { messages } = req.body;

    if (!messages || !Array.isArray(messages)) {
      res.status(400).json({ error: "messages array is required" });
      return;
    }

    res.setHeader("Content-Type", "text/event-stream");
    res.setHeader("Cache-Control", "no-cache");
    res.setHeader("Connection", "keep-alive");
    res.setHeader("X-Accel-Buffering", "no");
    res.flushHeaders();

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
            console.warn(
              `CF API ${apiRes.statusCode}, retry ${retryCount}/${maxRetries} in ${wait}ms`
            );
            setTimeout(attemptRequest, wait);
          } else {
            if (!res.writableEnded) {
              res.write(
                `data: ${JSON.stringify({ error: "AI service rate limited, please try again" })}\n\n`
              );
              res.write("data: [DONE]\n\n");
              res.end();
            }
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
              // Cloudflare Workers AI SSE: { response: "chunk", p: "..." }
              // Also handle OpenAI-compatible delta format as fallback
              const content =
                parsed.response ??
                parsed.choices?.[0]?.delta?.content ??
                parsed.content ??
                "";

              if (
                content &&
                (content.includes("Ratelimit") ||
                  content.includes("ratelimit"))
              ) {
                apiRes.destroy();
                if (retryCount < maxRetries) {
                  retryCount++;
                  const wait = Math.pow(2, retryCount) * 1000;
                  console.warn(
                    `Rate limit in stream, retry ${retryCount}/${maxRetries} in ${wait}ms`
                  );
                  setTimeout(attemptRequest, wait);
                } else {
                  if (!res.writableEnded) {
                    res.write(
                      `data: ${JSON.stringify({ error: "AI service rate limited, please try again later" })}\n\n`
                    );
                    res.write("data: [DONE]\n\n");
                    res.end();
                  }
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
          if (!res.writableEnded) {
            res.write(
              `data: ${JSON.stringify({ error: "AI service error" })}\n\n`
            );
            res.write("data: [DONE]\n\n");
            res.end();
          }
        });
      });

      apiReq.on("error", (err) => {
        console.error("CF API request error:", err);
        if (!res.writableEnded) {
          res.write(
            `data: ${JSON.stringify({ error: "AI service connection error" })}\n\n`
          );
          res.write("data: [DONE]\n\n");
          res.end();
        }
      });

      apiReq.write(requestBody);
      apiReq.end();

      res.on("close", () => {
        apiReq.destroy();
      });
    };

    attemptRequest();
  });

  // Agent endpoint — spawns Python agent, relays SSE events to client
  app.post("/api/agent", (req, res) => {
    const { message, messages, model, attachments } = req.body;

    if (!message && (!messages || !Array.isArray(messages))) {
      res.status(400).json({ error: "message or messages array is required" });
      return;
    }

    res.setHeader("Content-Type", "text/event-stream");
    res.setHeader("Cache-Control", "no-cache");
    res.setHeader("Connection", "keep-alive");
    res.setHeader("X-Accel-Buffering", "no");
    res.flushHeaders();

    const { apiKey } = getCFConfig();

    const proc = spawn("python3", ["-m", "server.agent.agent_flow"], {
      stdio: ["pipe", "pipe", "pipe"],
      cwd: process.cwd(),
      env: {
        ...process.env,
        CF_API_KEY: apiKey,
      },
    });

    const input = JSON.stringify({
      message: message || "",
      messages: messages || [],
      model: model || process.env.CF_MODEL || "@cf/meta/llama-3-8b-instruct",
      attachments: attachments || [],
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
          // Skip malformed JSON lines
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
      if (!res.writableEnded) {
        res.write(
          `data: ${JSON.stringify({ type: "error", error: "Agent service error" })}\n\n`
        );
        res.write("data: [DONE]\n\n");
        res.end();
      }
    });

    res.on("close", () => {
      if (!proc.killed) {
        proc.kill();
      }
    });
  });

  const httpServer = createServer(app);
  return httpServer;
}
