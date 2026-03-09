import { fetch } from "expo/fetch";

/**
 * Stream chat responses from the g4f API via SSE.
 * Yields text chunks as they arrive.
 */
export async function* streamChat(
  messages: Array<{ role: string; content: string }>,
  apiUrl: string,
  signal?: AbortSignal,
): AsyncGenerator<string> {
  const response = await fetch(`${apiUrl}api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, model: "mistral-small-24b" }),
    signal,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Chat request failed: ${response.status} ${text}`);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith("data: ")) {
        const data = trimmed.slice(6);
        if (data === "[DONE]") return;
        try {
          const parsed = JSON.parse(data);
          if (parsed.content) yield parsed.content;
          if (parsed.error) throw new Error(parsed.error);
        } catch (e) {
          if (e instanceof SyntaxError) continue;
          throw e;
        }
      }
    }
  }
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: number;
  attachments?: ChatAttachment[];
  isStreaming?: boolean;
  error?: string;
}

export interface ChatAttachment {
  uri: string;
  type: "image";
  name?: string;
}
