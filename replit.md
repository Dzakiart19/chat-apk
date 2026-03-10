# Dzeck AI

Cross-platform AI chat + autonomous agent app built with Expo (React Native) and Node.js backend.

## Architecture

- **Frontend**: Expo/React Native (web via Metro bundler on port 8081)
- **Backend**: Express.js server on port 5000 (main webview)
- **AI Engine**: Python 3.11 calling Airforce API directly via `urllib.request`

## Key Features

- **Chat Mode**: Streaming conversational AI via `POST https://api.airforce/v1/chat/completions`
- **Agent Mode**: Autonomous Plan-Act agent with tools (shell, file, web search, browser, MCP)

## Setup

### Running the Project

1. **Backend** (Start Backend workflow): `npm run server:dev` - serves on port 5000
2. **Frontend** (Start Frontend workflow): Expo Metro bundler on port 8081

### AI Configuration

- Uses **Airforce API** (`https://api.airforce/v1/chat/completions`)
- API key stored in `.env` file as `AIRFORCE_API_KEY`
- Model: `gpt-4o-mini` (both chat and agent)
- Retry logic: exponential backoff (up to 5 retries) for HTTP 429 and 5xx errors

### Environment Variables

Copy `.env.example` to `.env` and fill in your key:

```
AIRFORCE_API_KEY=sk-air-your-key-here
PORT=5000
NODE_ENV=development
```

The `.env` file is loaded automatically at startup by both Node.js (server/index.ts) and Python (agent_flow.py, g4f_chat.py).

### Python Dependencies

- `pydantic>=2.0.0` - Data models for agent
- `beautifulsoup4>=4.12.0` - HTML parsing for browser tool
- `requests` - HTTP utilities
- `aiohttp` - Async HTTP (optional)

## File Structure

```
server/
  index.ts          - Express server entry point (.env loading here)
  routes.ts         - API routes (/api/chat, /api/agent) with retry logic
  g4f_chat.py       - Python bridge for chat (Airforce API)
  agent/
    agent_flow.py   - Core Plan-Act autonomous agent (Airforce API + .env loading)
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
- `POST /api/chat` - Streaming chat (SSE) with auto-retry on rate limit
- `POST /api/agent` - Autonomous agent (SSE) with auto-retry on rate limit
