/**
 * API Service untuk komunikasi dengan backend
 * Implementasi non-streaming untuk respon yang lengkap
 */

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatResponse {
  type: string;
  content?: string;
  session_id?: string;
  timestamp?: string;
  error?: string;
}

export interface AgentEvent {
  type: string;
  content?: string;
  session_id?: string;
  tool_name?: string;
  tool_args?: Record<string, any>;
  timestamp?: string;
  error?: string;
}

class ApiService {
  private baseUrl: string;

  constructor(baseUrl: string = "") {
    this.baseUrl = baseUrl || (typeof window !== "undefined" ? window.location.origin : "");
  }

  /**
   * Non-streaming chat endpoint
   * Mengirim pesan dan menerima respon lengkap (bukan streaming)
   */
  async chat(messages: ChatMessage[]): Promise<ChatResponse> {
    try {
      const response = await fetch(`${this.baseUrl}/api/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ messages }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      return data;
    } catch (error) {
      console.error("Chat API error:", error);
      throw error;
    }
  }

  /**
   * Agent endpoint dengan SSE untuk streaming events
   * Namun setiap event adalah complete message (non-streaming per message)
   */
  async agent(
    message: string,
    onEvent: (event: AgentEvent) => void,
    onError: (error: Error) => void,
    onComplete: () => void
  ): Promise<() => void> {
    try {
      const response = await fetch(`${this.baseUrl}/api/agent`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          message,
          messages: [],
          model: "@cf/meta/llama-3.1-70b-instruct",
          attachments: [],
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error("Response body is not readable");
      }

      const decoder = new TextDecoder();
      let buffer = "";
      let isClosed = false;

      const processStream = async () => {
        try {
          while (!isClosed) {
            const { done, value } = await reader.read();

            if (done) {
              isClosed = true;
              onComplete();
              break;
            }

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop() || "";

            for (const line of lines) {
              const trimmed = line.trim();
              if (!trimmed || !trimmed.startsWith("data: ")) continue;

              const data = trimmed.slice(6);
              if (data === "[DONE]") {
                isClosed = true;
                onComplete();
                return;
              }

              try {
                const event = JSON.parse(data);
                onEvent(event);
              } catch (e) {
                console.error("Failed to parse event:", e);
              }
            }
          }
        } catch (error) {
          if (!isClosed) {
            isClosed = true;
            onError(error instanceof Error ? error : new Error(String(error)));
          }
        }
      };

      processStream();

      // Return cancel function
      return () => {
        isClosed = true;
        reader.cancel();
      };
    } catch (error) {
      console.error("Agent API error:", error);
      throw error;
    }
  }

  /**
   * Test endpoint untuk verifikasi API
   */
  async test(): Promise<any> {
    try {
      const response = await fetch(`${this.baseUrl}/api/test`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error("Test API error:", error);
      throw error;
    }
  }
}

export const apiService = new ApiService();
