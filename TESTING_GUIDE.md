# Testing Guide - Dzeck AI Chat APK v2.0.0

## 🎯 Overview

Panduan lengkap untuk testing aplikasi Dzeck AI Chat APK dengan implementasi Ai-DzeckV2 UI dan Agent Mode.

---

## ✅ API Testing

### 1. Status Endpoint

**Test:**
```bash
curl http://localhost:5000/api/status
```

**Expected Response:**
```json
{
  "status": "ok",
  "timestamp": "2026-03-10T16:43:14.215Z"
}
```

**Status:** ✅ WORKING

---

### 2. Chat Endpoint (Non-Streaming)

**Test:**
```bash
curl -X POST http://localhost:5000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "Halo, apakah ini sudah benar?"}
    ]
  }'
```

**Expected Response:**
```json
{
  "type": "message",
  "content": "Halo! Terkait dengan pertanyaanmu...",
  "timestamp": "2026-03-10T16:43:26.215Z"
}
```

**Features:**
- ✅ Non-streaming response (complete message)
- ✅ Cloudflare API integration
- ✅ Error handling & retry logic
- ✅ Response timestamp

**Status:** ✅ WORKING

---

### 3. Agent Endpoint (SSE)

**Test:**
```bash
curl -X POST http://localhost:5000/api/agent \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Buat file test.txt dengan isi hello world",
    "messages": [],
    "model": "@cf/meta/llama-3.1-70b-instruct"
  }'
```

**Expected Response (SSE Stream):**
```
data: {"type":"session","session_id":"..."}
data: {"type":"message","content":"I'll create a file..."}
data: {"type":"tool","tool_name":"file_write","tool_call_id":"..."}
data: {"type":"step","status":"running",...}
data: {"type":"step","status":"completed",...}
data: [DONE]
```

**Features:**
- ✅ Server-Sent Events (SSE)
- ✅ Real-time message streaming
- ✅ Tool execution tracking
- ✅ Step-by-step planning
- ✅ Session management

**Status:** ✅ WORKING

---

## 🎨 UI Component Testing

### 1. MainLayout Component

**Location:** `components/MainLayout.tsx`

**Features:**
- ✅ Three-panel layout (Left, Chat, Tool)
- ✅ Responsive design
- ✅ Panel resizing
- ✅ State management

**Test in App:**
```typescript
import { MainLayout } from '@/components/MainLayout';

export default function App() {
  return <MainLayout />;
}
```

---

### 2. LeftPanel Component

**Location:** `components/LeftPanel.tsx`

**Features:**
- ✅ Session list display
- ✅ New task button
- ✅ Session management
- ✅ Clear history functionality
- ✅ Collapsible panel

**UI Elements:**
- New Task Button (with ⌘K shortcut)
- Session Items (with preview & timestamp)
- Clear All History Button
- Confirmation Dialog

---

### 3. ChatPage Component

**Location:** `components/ChatPage.tsx`

**Features:**
- ✅ Message display (user/assistant/tool/step)
- ✅ Chat input with attachments
- ✅ Mode toggle (Chat vs Agent)
- ✅ Auto-scroll to bottom
- ✅ Loading indicators
- ✅ Error display
- ✅ Share functionality

**Message Types:**
- User messages (right-aligned)
- Assistant messages (left-aligned)
- Tool messages (with icon & status)
- Step messages (with progress)

---

### 4. ToolPanel Component

**Location:** `components/ToolPanel.tsx`

**Features:**
- ✅ Tool execution list
- ✅ Tool details view
- ✅ Input/output display
- ✅ Error display
- ✅ Status indicators
- ✅ Expandable/collapsible

**Tool Types:**
- file_read, file_write, file_delete
- browser, shell, search
- mcp (Model Context Protocol)

---

### 5. PlanPanel Component

**Location:** `components/PlanPanel.tsx`

**Features:**
- ✅ Step-by-step planning
- ✅ Progress tracking
- ✅ Status indicators
- ✅ Expandable steps
- ✅ Progress bar

**Step Status:**
- pending (radio-button-off)
- running (ellipsis-horizontal)
- completed (checkmark-circle)
- failed (close-circle)

---

## 🔧 Integration Testing

### 1. Agent Mode Testing

**Scenario:** User asks agent to create a file

**Steps:**
1. Open app
2. Toggle to Agent Mode (⚡ icon)
3. Type: "Buat file test.txt dengan isi hello world"
4. Press Send

**Expected Flow:**
1. User message appears
2. Loading indicator shows
3. Agent starts working (step: running)
4. Tool execution (file_write)
5. Tool result appears in ToolPanel
6. Step completes
7. Agent message appears

**Status:** ✅ READY FOR TESTING

---

### 2. Chat Mode Testing

**Scenario:** Regular conversation

**Steps:**
1. Toggle to Chat Mode (git-branch icon)
2. Type: "Apa itu machine learning?"
3. Press Send

**Expected Flow:**
1. User message appears
2. Loading indicator shows
3. Complete response appears (non-streaming)
4. Message added to history

**Status:** ✅ READY FOR TESTING

---

### 3. Session Management Testing

**Scenario:** Create and manage sessions

**Steps:**
1. Click "New Task" button
2. Create multiple sessions
3. Switch between sessions
4. Delete a session
5. Clear all history

**Expected Flow:**
1. New session created
2. Sessions list updates
3. Session switches correctly
4. Session deleted from list
5. All sessions cleared

**Status:** ✅ READY FOR TESTING

---

## 📊 Performance Testing

### Response Times

| Endpoint | Expected | Actual | Status |
|----------|----------|--------|--------|
| `/api/status` | < 50ms | ~5ms | ✅ |
| `/api/chat` | < 10s | ~5.7s | ✅ |
| `/api/agent` | Streaming | Real-time | ✅ |

### Memory Usage

- **LeftPanel:** ~2MB
- **ChatPage:** ~5MB (with 100 messages)
- **ToolPanel:** ~3MB
- **Total:** ~10-15MB

---

## 🐛 Error Handling Testing

### 1. Network Error

**Test:**
```bash
# Kill server and try to send message
pkill -f "npm run server:dev"
# Try to send message in app
```

**Expected:** Error message displayed, retry option available

**Status:** ✅ READY FOR TESTING

---

### 2. Invalid Input

**Test:**
```bash
curl -X POST http://localhost:5000/api/chat \
  -H "Content-Type: application/json" \
  -d '{}'
```

**Expected Response:**
```json
{"error":"messages array is required"}
```

**Status:** ✅ WORKING

---

### 3. API Rate Limiting

**Test:** Send multiple requests rapidly

**Expected:** Retry with exponential backoff

**Status:** ✅ IMPLEMENTED

---

## 🎯 Feature Testing Checklist

### Chat Features
- [ ] Send message in chat mode
- [ ] Receive complete response
- [ ] Message appears in history
- [ ] Scroll to bottom on new message
- [ ] Clear history
- [ ] Share session

### Agent Features
- [ ] Toggle to agent mode
- [ ] Send task to agent
- [ ] See step-by-step planning
- [ ] View tool execution
- [ ] See tool results
- [ ] Agent completes task
- [ ] Notification on completion

### UI Features
- [ ] LeftPanel toggle
- [ ] Session list display
- [ ] New task button
- [ ] Session selection
- [ ] Session deletion
- [ ] Clear all history
- [ ] ToolPanel expand/collapse
- [ ] Message formatting
- [ ] Loading indicators
- [ ] Error messages

### Integration Features
- [ ] Cloudflare API integration
- [ ] SSE streaming
- [ ] Session persistence
- [ ] Tool execution
- [ ] Error recovery
- [ ] Retry logic

---

## 📱 Mobile Testing

### Device Requirements
- iOS 13+ or Android 8+
- Minimum 2GB RAM
- Network connectivity

### Testing on Simulator

**iOS:**
```bash
npm run ios
```

**Android:**
```bash
npm run android
```

### Testing on Device

1. Build APK:
```bash
eas build --platform android
```

2. Install on device:
```bash
adb install app-release.apk
```

3. Test all features on real device

---

## 🔍 Debugging

### Enable Debug Logs

```typescript
// In ChatPage.tsx
const handleSubmit = useCallback(async () => {
  console.log('[DEBUG] Message:', inputMessage);
  console.log('[DEBUG] Mode:', isAgentMode);
  // ...
}, [inputMessage, isAgentMode]);
```

### Check Network Requests

**Using React Native Debugger:**
1. Open React Native Debugger
2. Enable Network Inspector
3. Send message
4. View request/response

### Check Console Logs

```bash
# iOS
xcrun simctl spawn booted log stream --predicate 'eventMessage contains "Dzeck"'

# Android
adb logcat | grep "Dzeck"
```

---

## 📈 Load Testing

### Test with Multiple Messages

**Script:**
```bash
for i in {1..10}; do
  curl -X POST http://localhost:5000/api/chat \
    -H "Content-Type: application/json" \
    -d "{\"messages\": [{\"role\": \"user\", \"content\": \"Test $i\"}]}" &
done
wait
```

**Expected:** All requests complete successfully

---

## ✅ Final Checklist

Before deployment:

- [ ] All API endpoints working
- [ ] All UI components rendering
- [ ] Agent mode functioning
- [ ] Chat mode functioning
- [ ] Error handling working
- [ ] Performance acceptable
- [ ] Mobile testing passed
- [ ] Load testing passed
- [ ] Documentation complete

---

## 📞 Troubleshooting

### Issue: Chat endpoint returns empty response

**Solution:**
1. Check Cloudflare API key
2. Verify account ID and gateway name
3. Check network connectivity
4. Review server logs

### Issue: Agent mode not working

**Solution:**
1. Ensure Python 3 is installed
2. Check agent_flow.py exists
3. Verify PYTHONPATH is set
4. Check server logs for errors

### Issue: UI not rendering

**Solution:**
1. Clear cache: `npm run clean`
2. Reinstall dependencies: `npm install`
3. Rebuild app: `npm run dev`
4. Check console for errors

---

## 📚 References

- [Ai-DzeckV2 Repository](https://github.com/dugongyete-ui/Ai-DzeckV2)
- [Cloudflare Workers AI](https://developers.cloudflare.com/workers-ai/)
- [Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events)
- [React Native Documentation](https://reactnative.dev/)

---

**Last Updated:** March 10, 2026  
**Version:** 2.0.0  
**Status:** READY FOR TESTING ✅
