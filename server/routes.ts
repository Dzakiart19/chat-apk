import type { Express } from "express";
import { createServer, type Server } from "node:http";
import { spawn } from "node:child_process";
import * as https from "node:https";

const AIRFORCE_API_URL = "https://api.airforce/v1/chat/completions";
const AIRFORCE_API_KEY = process.env.AIRFORCE_API_KEY || "";

if (!AIRFORCE_API_KEY) {
  console.warn("[WARNING] AIRFORCE_API_KEY is not set. AI features will not work.");
}

export async function registerRoutes(app: Express): Promise<Server> {
  // Health check / status endpoint
  app.get("/status", (_req, res) => {
    res.json({ status: "ok", timestamp: new Date().toISOString() });
  });

  app.get("/api/status", (_req, res) => {
    res.json({ status: "ok", timestamp: new Date().toISOString() });
  });

  // Chat API endpoint with SSE streaming - calls airforce API directly
  app.post("/api/chat", (req, res) => {
    const { messages, model } = req.body;

    if (!messages || !Array.isArray(messages)) {
      res.status(400).json({ error: "messages array is required" });
      return;
    }

    res.setHeader("Content-Type", "text/event-stream");
    res.setHeader("Cache-Control", "no-cache");
    res.setHeader("Connection", "keep-alive");
    res.setHeader("X-Accel-Buffering", "no");
    res.flushHeaders();

    const requestBody = JSON.stringify({
      model: model || "gpt-4o-mini",
      messages,
      stream: true,
      temperature: 0.7,
      max_tokens: 4096,
    });

    const url = new URL(AIRFORCE_API_URL);

    const options: https.RequestOptions = {
      hostname: url.hostname,
      port: 443,
      path: url.pathname,
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${AIRFORCE_API_KEY}`,
        "Content-Length": Buffer.byteLength(requestBody),
      },
    };

    let retryCount = 0;
    const maxRetries = 4;

    const attemptRequest = () => {
      const apiReq = https.request(options, (apiRes) => {
        // Handle rate limit / server errors with retry
        if (apiRes.statusCode === 429 || (apiRes.statusCode && apiRes.statusCode >= 500)) {
          const retryAfter = parseInt(apiRes.headers["retry-after"] as string || "0", 10);
          const wait = retryAfter > 0 ? retryAfter * 1000 : Math.pow(2, retryCount) * 1000;
          apiRes.resume(); // drain body

          if (retryCount < maxRetries) {
            retryCount++;
            console.warn(`Airforce API ${apiRes.statusCode}, retry ${retryCount}/${maxRetries} in ${wait}ms`);
            setTimeout(attemptRequest, wait);
          } else {
            if (!res.writableEnded) {
              res.write(`data: ${JSON.stringify({ error: "AI service rate limited, please try again" })}\n\n`);
              res.write("data: [DONE]\n\n");
              res.end();
            }
          }
          return;
        }

        let apiBuffer = "";

        apiRes.on("data", (chunk: Buffer) => {
          apiBuffer += chunk.toString();
          const lines = apiBuffer.split("\n");
          apiBuffer = lines.pop() || "";

          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed || !trimmed.startsWith("data: ")) continue;

            const data = trimmed.slice(6);
            if (data === "[DONE]") {
              res.write("data: [DONE]\n\n");
              return;
            }

            try {
              const parsed = JSON.parse(data);
              if (parsed.choices && parsed.choices[0]?.delta?.content) {
                res.write(
                  `data: ${JSON.stringify({ content: parsed.choices[0].delta.content })}\n\n`,
                );
              }
            } catch {
              // Skip malformed JSON
            }
          }
        });

        apiRes.on("end", () => {
          if (!res.writableEnded) {
            res.write("data: [DONE]\n\n");
            res.end();
          }
        });

        apiRes.on("error", (err) => {
          console.error("Airforce API response error:", err);
          if (!res.writableEnded) {
            res.write(`data: ${JSON.stringify({ error: "AI service error" })}\n\n`);
            res.write("data: [DONE]\n\n");
            res.end();
          }
        });
      });

      apiReq.on("error", (err) => {
        console.error("Airforce API request error:", err);
        if (!res.writableEnded) {
          res.write(`data: ${JSON.stringify({ error: "AI service connection error" })}\n\n`);
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

  // Agent API endpoint with SSE streaming - Full autonomous AI agent mode
  // Ported from ai-manus PlanActFlow architecture
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

    const proc = spawn("python3", ["-m", "server.agent.agent_flow"], {
      stdio: ["pipe", "pipe", "pipe"],
      cwd: process.cwd(),
      env: {
        ...process.env,
        AIRFORCE_API_KEY: AIRFORCE_API_KEY,
      },
    });

    const input = JSON.stringify({
      message: message || "",
      messages: messages || [],
      model: model || "gpt-4o-mini",
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
        if (line.trim()) {
          try {
            const parsed = JSON.parse(line);
            if (parsed.type === "done") {
              doneSent = true;
              res.write("data: [DONE]\n\n");
            } else {
              // Forward all agent events as SSE
              res.write(`data: ${JSON.stringify(parsed)}\n\n`);
            }
          } catch {
            // Skip malformed JSON lines
          }
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
          `data: ${JSON.stringify({ type: "error", error: "Agent service error" })}\n\n`,
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
