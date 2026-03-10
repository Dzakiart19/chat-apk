# Dzeck AI

Cross-platform AI chat + autonomous agent app built with Expo (React Native) and Node.js backend.

## Architecture (Upgraded to ai-manus pattern)

| Aspek | Implementation |
|---|---|
| Language | Python async (AsyncGenerator) |
| LLM | Cloudflare Workers AI (llama-3-8b) |
| Framework | Pydantic BaseModel + async generator streaming |
| Database | MongoDB Atlas (motor async driver) for session/agent persistence |
| Cache | Redis (aioredis) for session state caching |
| Browser | Playwright real browser + HTTP fallback |
| Architecture | DDD: Domain / Application / Infrastructure layers |
| Session mgmt | Full session resume + rollback support |

## Key Features

- **Chat Mode**: Real-time streaming via Cloudflare Workers AI SSE
- **Agent Mode**: Async autonomous Plan-Act agent with real tool execution
- **Session Persistence**: Full MongoDB session history with Redis cache
- **Browser Automation**: Playwright-powered real browser (with HTTP fallback)
- **Session Resume/Rollback**: Resume interrupted sessions, rollback to any step
- **DDD Architecture**: Clean separation of domain, application, and infrastructure

## Setup

### Running the Project

1. **Backend** (Start Backend workflow): `npm run server:dev` — serves on port 5000
2. **Frontend** (Start Frontend workflow): Expo Metro bundler on port 8081

### Environment Variables (set in Replit Secrets)

```
CF_API_KEY=<cloudflare-api-key>
CF_ACCOUNT_ID=6c807fe58ad83714e772403cd528dbeb
CF_GATEWAY_NAME=dzeck
CF_MODEL=@cf/meta/llama-3-8b-instruct
MONGODB_URI=<mongodb-atlas-uri>
REDIS_HOST=<redis-host>
REDIS_PORT=16364
REDIS_PASSWORD=<redis-password>
SESSION_TTL_HOURS=24
PLAYWRIGHT_ENABLED=true
```

## File Structure

```
server/
  index.ts              - Express server entry point
  routes.ts             - API routes + session management endpoints
  agent/
    agent_flow.py       - Core async Plan-Act agent (AsyncGenerator)
    db/
      session_store.py  - MongoDB session persistence (motor async)
      cache.py          - Redis session cache (aioredis)
    services/
      session_service.py - Session lifecycle orchestration (DDD Application layer)
    tools/
      browser.py        - Playwright + HTTP browser tools
      shell.py          - Shell execution tools
      file.py           - File system tools
      search.py         - Web search tools
      message.py        - User notification tools
      mcp.py            - MCP protocol tools
    prompts/            - LLM prompt templates
    models/             - Pydantic data models (Plan, Step, Memory, etc.)
    utils/              - Robust JSON parser
app/                    - Expo React Native frontend
components/             - UI components (AgentPlanView, AgentToolCard, etc.)
```

## API Endpoints

- `GET /api/status` — Health check
- `POST /api/chat` — Streaming chat (SSE)
- `POST /api/agent` — Async autonomous agent (SSE) with session_id
- `GET /api/sessions` — List all sessions from MongoDB
- `GET /api/sessions/:id` — Get session details
- `POST /api/sessions/:id/resume` — Resume an interrupted session (SSE)
- `POST /api/sessions/:id/rollback` — Rollback session to previous step
- `GET /api/sessions/:id/events` — Get full event log for a session

## Python Dependencies

- `pydantic>=2.0.0` - Pydantic BaseModel data models
- `motor>=3.7.0` - Async MongoDB driver (AsyncIOMotorClient)
- `redis>=5.0.0` - Redis async client
- `playwright>=1.40.0` - Real browser automation (Chromium)
- `beautifulsoup4>=4.12.0` - HTML parsing
- `aiohttp` - Async HTTP client
- `requests` - Sync HTTP client
- `g4f` - GPT4Free fallback
- `flask`, `flask-cors` - Flask (optional)

## Nix System Dependencies (for Playwright Chromium)

Required for Playwright to work on Replit/NixOS:
- `nspr`, `nss`, `mesa`, `expat`, `libxkbcommon`, `glib`, `dbus`
- `atk`, `at-spi2-atk`
- `xorg.libXdamage`, `xorg.libXrandr`, `xorg.libXfixes`, `xorg.libX11`
- `xorg.libXcomposite`, `xorg.libXext`, `xorg.libXcursor`, `xorg.libXtst`
- `xorg.libXinerama`, `xorg.libXi`, `xorg.libxcb`, `xorg.libXScrnSaver`
- `cups`, `alsa-lib`, `pango`, `cairo`

## Key Technical Notes

### Async Agent Flow (AsyncGenerator)
The agent uses Python's `AsyncGenerator` pattern - events are yielded as they happen, enabling true real-time streaming without blocking.

### True Real-Time Streaming (asyncio.Queue bridge)
`call_cf_streaming_realtime()` uses an `asyncio.Queue` to bridge the sync urllib thread with the async generator. Cloudflare chunks are pushed to the queue from a thread via `loop.call_soon_threadsafe()` and yielded immediately - no buffering, no fake streaming.

### Session Persistence
- **MongoDB Atlas**: Stores full session documents (plan, steps, events, metadata)
- **Redis**: Fast cache for hot session state (TTL: 1 hour per session)
- **Session ID**: Auto-generated UUID, returned in first SSE event

### Cloudflare Workers AI Response Format
- Non-streaming: `{"response": "...", "usage": {...}}`
- Streaming SSE: `data: {"response": "chunk"}` then `data: [DONE]`
- Tool calls: `{"tool_calls": [{"name": "func", "arguments": {...}}]}`

### Agent Event Types
- `type: "session"` — session_id assigned
- `type: "plan"` — plan creating/created/running/updated/completed
- `type: "step"` — step running/completed/failed
- `type: "tool"` — tool calling/called/error
- `type: "message_start/chunk/end"` — streaming text
- `type: "done"` — agent finished
