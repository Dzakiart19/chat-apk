# Dzeck AI

Cross-platform AI chat + autonomous agent app built with Expo (React Native) and Node.js backend.

## Architecture

- **Frontend**: Expo/React Native (web via Metro bundler on port 8081)
- **Backend**: Express.js server on port 5000 (main webview)
- **AI Engine**: Python 3.11 with g4f (gpt4free) - no API key required

## Key Features

- **Chat Mode**: Standard conversational AI using `mistral-small-24b` model via Yqcloud provider (g4f)
- **Agent Mode**: Autonomous Plan-Act agent with tools (shell, file, web search, browser, MCP)

## Setup

### Running the Project

1. **Backend** (Start Backend workflow): `npm run server:dev` - serves on port 5000
2. **Frontend** (Start Frontend workflow): Expo Metro bundler on port 8081

### AI Configuration

- Uses **gpt4free (g4f)** by default - FREE, no API key required
- Provider: **Yqcloud** (stable, free provider)
- Models: `mistral-small-24b` (chat), `gpt-4o-mini` (agent)
- To use OpenAI API instead: set `OPENAI_API_KEY` env var (agent will auto-switch)

### Python Dependencies

- `g4f` - gpt4free library
- `requests`, `aiohttp` - HTTP utilities

## File Structure

```
server/
  index.ts          - Express server entry point
  routes.ts         - API routes (/api/chat, /api/agent)
  g4f_chat.py       - Python bridge for chat (uses Yqcloud)
  agent/
    agent_flow.py   - Core Plan-Act autonomous agent
    tools/          - Agent tools (shell, file, search, browser, mcp)
    prompts/        - LLM prompt templates
    models/         - Data models
    utils/          - Robust JSON parser (anti-hallucination)
app/                - Expo React Native frontend
components/         - UI components
```

## API Endpoints

- `GET /api/status` - Health check
- `POST /api/chat` - Streaming chat (SSE)
- `POST /api/agent` - Autonomous agent (SSE)
