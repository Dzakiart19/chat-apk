import type { Express } from "express";
import { createServer, type Server } from "node:http";
import { spawn } from "node:child_process";
import * as path from "node:path";

export async function registerRoutes(app: Express): Promise<Server> {
  // Health check / status endpoint
  app.get("/status", (_req, res) => {
    res.json({ status: "ok", timestamp: new Date().toISOString() });
  });

  app.get("/api/status", (_req, res) => {
    res.json({ status: "ok", timestamp: new Date().toISOString() });
  });

  // Chat API endpoint with SSE streaming
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

    const pythonScript = path.resolve(process.cwd(), "server", "g4f_chat.py");
    const proc = spawn("python3", [pythonScript], {
      stdio: ["pipe", "pipe", "pipe"],
    });

    const input = JSON.stringify({
      messages,
      model: model || "mistral-small-24b",
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
            if (parsed.done) {
              doneSent = true;
              res.write("data: [DONE]\n\n");
            } else if (parsed.error) {
              res.write(
                `data: ${JSON.stringify({ error: parsed.error })}\n\n`,
              );
            } else if (parsed.content) {
              res.write(
                `data: ${JSON.stringify({ content: parsed.content })}\n\n`,
              );
            }
          } catch {
            // Skip malformed JSON lines
          }
        }
      }
    });

    proc.stderr.on("data", (data: Buffer) => {
      console.error("g4f stderr:", data.toString());
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
      console.error("g4f process error:", err);
      if (!res.writableEnded) {
        res.write(`data: ${JSON.stringify({ error: "AI service error" })}\n\n`);
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
