# Dzeck AI

Cross-platform AI chat + autonomous agent app built with Expo (React Native) and Node.js backend.

## Architecture

- **Frontend**: Expo/React Native (web via Metro bundler on port 8081)
- **Backend**: Express.js server on port 5000 (main webview)
- **AI Engine**: Python 3.11 calling Cloudflare Workers AI via urllib.request

## Key Features

- **Chat Mode**: Real-time streaming via Cloudflare Workers AI SSE
- **Agent Mode**: Autonomous Plan-Act agent with real tool execution (shell, file, web search, browser, MCP)

## Setup

### Running the Project

1. **Backend** (Start Backend workflow): `npm run server:dev` — serves on port 5000
2. **Frontend** (Start Frontend workflow): Expo Metro bundler on port 8081

### AI Configuration

- Uses **Cloudflare Workers AI** via AI Gateway
- Credentials stored in `.env` file
- Model: `@cf/meta/llama-3-8b-instruct`
- Retry logic: exponential backoff (up to 5 retries) for HTTP 429 and 5xx errors
- User-Agent header required to avoid Cloudflare bot detection

### Environment Variables

Create `.env` in project root (copy from `.env.example`):

```
CF_API_KEY=your-cloudflare-api-key-here
CF_ACCOUNT_ID=your-account-id-here
CF_GATEWAY_NAME=your-gateway-name-here
CF_MODEL=@cf/meta/llama-3-8b-instruct
PORT=5000
NODE_ENV=development
```

The `.env` file is loaded automatically at startup by both Node.js (`server/index.ts`) and Python (`agent_flow.py`, `g4f_chat.py`, `tools/mcp.py`).

### Python Dependencies

- `pydantic>=2.0.0` - Data models for agent
- `beautifulsoup4>=4.12.0` - HTML parsing for browser tool

## File Structure

```
server/
  index.ts          - Express server entry point (.env loading here)
  routes.ts         - API routes (/api/chat, /api/agent) — Cloudflare SSE streaming
  g4f_chat.py       - Python bridge for chat (Cloudflare Workers AI)
  agent/
    agent_flow.py   - Core Plan-Act autonomous agent (Cloudflare Workers AI + tool calling)
    tools/          - Agent tools (shell, file, search, browser, mcp)
    prompts/        - LLM prompt templates
    models/         - Data models
    utils/          - Robust JSON parser (anti-hallucination)
app/                - Expo React Native frontend
components/         - UI components
.env                - Local environment variables (gitignored, copy from .env.example)
.env.example        - Template for environment variables
```

## API Endpoints

- `GET /api/status` - Health check
- `POST /api/chat` - Streaming chat (SSE) — Cloudflare Workers AI with streaming
- `POST /api/agent` - Autonomous agent (SSE) — Python Plan-Act flow with real tool execution

## Key Technical Notes

### Cloudflare Workers AI Response Format
- Non-streaming: `{"response": "...", "usage": {...}}` — no "result" wrapper
- Streaming SSE: `data: {"response": "chunk", "p": "..."}` then `data: [DONE]`
- Tool calls: `{"tool_calls": [{"name": "func", "arguments": {...}}]}`
- Tool schema format: `{"name": "...", "description": "...", "parameters": {...}}` (no OpenAI wrapper)

### Agent Event System
- `type: "message"` — clean text sent to chat UI
- `type: "tool"` — tool execution card (calling/called/error states)
- `type: "thinking"` — subtle progress indicator (clean text only, no raw JSON)
- `type: "plan"` — plan creation/updates
- `type: "step"` — step execution status
- Raw JSON is never forwarded to the chat UI
