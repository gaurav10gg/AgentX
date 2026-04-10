# <span style="color:#FF6B35;">AgentX</span> <span style="color:#EF4444;">V1 + V2</span>

<p align="center">
  <b><span style="color:#FF6B35;">AI agent for your phone.</span></b><br/>
  <span style="color:#EF4444;">Type in the app, and it plans, executes, and now begins to automate Android apps.</span>
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-Backend-FF6B35?style=for-the-badge"/>
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-API-EF4444?style=for-the-badge"/>
  <img alt="React Native" src="https://img.shields.io/badge/React_Native-Android-FF6B35?style=for-the-badge"/>
  <img alt="Expo" src="https://img.shields.io/badge/Expo-Mobile-EF4444?style=for-the-badge"/>
  <img alt="Accessibility" src="https://img.shields.io/badge/Android-Accessibility-FF6B35?style=for-the-badge"/>
</p>

---

## What Is AgentX?

AgentX is a local-first mobile AI agent platform built in two layers:

- **V1** is the working assistant stack today: chat orchestration, tool-calling, Gmail/Calendar/Contacts/Search/Alarm tools, session memory, and scheduled task execution.
- **V2** is the new mobile automation layer: Android accessibility-based app control, UI tree capture, normalization, task-state memory, and a Swiggy-first automation loop.

The direction is simple:

```text
User intent
-> backend reasoning + memory
-> tool execution OR Android UI automation
-> result back in chat
```

---

## Current Status

### V1 is working today

- FastAPI backend with ReAct-style tool orchestration
- Provider routing (`sarvam`, `groq`, `gemini`, `openai`, custom OpenAI-compatible base URLs)
- Gmail, Calendar, Contacts, Search, and Alarm tools
- Per-session conversation memory
- Scheduled tasks with persistence
- Task completion notifications surfaced in later chat turns
- Expo Android app with chat, settings, Google connect flow, and local alarm support

### V2 foundation is now built

- `/v2` backend routes added
- Intent classification layer
- Constraint extraction layer
- UI normalization layer
- Navigation/task/element memory storage
- Decision layer for next-action selection
- Android native accessibility service scaffold
- Android action executor (`tap`, `type`, `scroll`, `back`, `home`, `wait`)
- React Native bridge for automation
- Automation Lab screen for testing V2 from the app

### V2 is not fully production-complete yet

What exists now is a **strong foundation**, not a finished universal phone agent. The architecture is in place, but real-world reliability tuning, richer app-specific heuristics, and more robust recovery loops still need iteration.

---

## Architecture

### V1 Flow

```text
Android App
  -> POST /chat
FastAPI Server
  -> refresh Google token if needed
  -> scheduler tick fallback
  -> run_agent()
     -> LLM provider
     -> tool router
     -> memory store
     -> task store
Tools
  -> Gmail / Calendar / Contacts / Web Search / Alarm
```

### V2 Flow

```text
User message
  -> POST /v2/chat
Intent Layer
  -> classify request
  -> extract constraints
Decision Orchestrator
  -> ask device to open app / observe UI
Android Accessibility Service
  -> capture raw UI tree
Backend Normalizer
  -> compact HTML-like screen
Memory + Constraint Engine
  -> retrieve hints
  -> filter options
Decision Layer
  -> choose next action
Android Action Executor
  -> tap / type / scroll / back / home
Loop
  -> observe -> think -> act -> repeat
```

---

## What We Have Built

### V1 backend

- [`server.py`](./server.py)
- [`agent/agent.py`](./agent/agent.py)
- [`agent/toolRouter.py`](./agent/toolRouter.py)
- [`agent/memory.py`](./agent/memory.py)
- [`agent/task_store.py`](./agent/task_store.py)
- [`agent/scheduler.py`](./agent/scheduler.py)

Highlights:

- Scheduler starts on backend startup
- `/chat` includes deterministic task-notification surfacing
- Reminder scheduling flow is more robust
- UTF-8/mojibake cleanup added to replies

### V2 backend

- [`agent_v2/intent.py`](./agent_v2/intent.py)
- [`agent_v2/constraints.py`](./agent_v2/constraints.py)
- [`agent_v2/normalize.py`](./agent_v2/normalize.py)
- [`agent_v2/decision.py`](./agent_v2/decision.py)
- [`agent_v2/orchestrator.py`](./agent_v2/orchestrator.py)
- [`agent_v2/memory_store.py`](./agent_v2/memory_store.py)
- [`agent_v2/router.py`](./agent_v2/router.py)
- [`agent_v2/app_registry.py`](./agent_v2/app_registry.py)
- [`agent_v2/offline_learning.py`](./agent_v2/offline_learning.py)

Highlights:

- Supports `simple_local`, `api_tool`, `ui_automation`, `scheduled_ui_automation`
- Swiggy-first app resolution
- Price/rating/delivery/COD constraint parsing
- Normalized screen snapshots and candidate extraction
- Task-state persistence and memory shortcuts
- Safer status transitions and failed-action learning handling

### Android native automation layer

- [`mobile/PhoneAgentApp/android/app/src/main/java/com/gaurav_10g/PhoneAgentApp/automation/AccessibilityAutomationService.kt`](./mobile/PhoneAgentApp/android/app/src/main/java/com/gaurav_10g/PhoneAgentApp/automation/AccessibilityAutomationService.kt)
- [`mobile/PhoneAgentApp/android/app/src/main/java/com/gaurav_10g/PhoneAgentApp/automation/UiTreeSerializer.kt`](./mobile/PhoneAgentApp/android/app/src/main/java/com/gaurav_10g/PhoneAgentApp/automation/UiTreeSerializer.kt)
- [`mobile/PhoneAgentApp/android/app/src/main/java/com/gaurav_10g/PhoneAgentApp/automation/ActionExecutor.kt`](./mobile/PhoneAgentApp/android/app/src/main/java/com/gaurav_10g/PhoneAgentApp/automation/ActionExecutor.kt)
- [`mobile/PhoneAgentApp/android/app/src/main/java/com/gaurav_10g/PhoneAgentApp/automation/AppLauncher.kt`](./mobile/PhoneAgentApp/android/app/src/main/java/com/gaurav_10g/PhoneAgentApp/automation/AppLauncher.kt)
- [`mobile/PhoneAgentApp/android/app/src/main/java/com/gaurav_10g/PhoneAgentApp/automation/AutomationBridgeModule.kt`](./mobile/PhoneAgentApp/android/app/src/main/java/com/gaurav_10g/PhoneAgentApp/automation/AutomationBridgeModule.kt)

Highlights:

- Accessibility service registration
- Raw UI tree serialization
- Action execution primitives
- RN native bridge
- Node-cap to avoid oversized snapshots

### Mobile app

- Chat UI for V1
- Settings and provider configuration
- Google account connect/disconnect
- Automation Lab for V2 testing

Key files:

- [`mobile/PhoneAgentApp/App.js`](./mobile/PhoneAgentApp/App.js)
- [`mobile/PhoneAgentApp/screens/ChatScreen.jsx`](./mobile/PhoneAgentApp/screens/ChatScreen.jsx)
- [`mobile/PhoneAgentApp/screens/SettingsScreen.jsx`](./mobile/PhoneAgentApp/screens/SettingsScreen.jsx)
- [`mobile/PhoneAgentApp/screens/AutomationLabScreen.jsx`](./mobile/PhoneAgentApp/screens/AutomationLabScreen.jsx)
- [`mobile/PhoneAgentApp/services/api.js`](./mobile/PhoneAgentApp/services/api.js)
- [`mobile/PhoneAgentApp/services/automationBridge.js`](./mobile/PhoneAgentApp/services/automationBridge.js)
- [`mobile/PhoneAgentApp/services/deviceState.js`](./mobile/PhoneAgentApp/services/deviceState.js)

---

## Project Structure

```text
phone-agent/
├─ server.py
├─ agent/
│  ├─ agent.py
│  ├─ toolRouter.py
│  ├─ memory.py
│  ├─ task_store.py
│  └─ scheduler.py
├─ agent_v2/
│  ├─ intent.py
│  ├─ constraints.py
│  ├─ normalize.py
│  ├─ decision.py
│  ├─ orchestrator.py
│  ├─ memory_store.py
│  ├─ app_registry.py
│  ├─ offline_learning.py
│  ├─ schemas.py
│  └─ screen_signature.py
├─ auth/
│  ├─ google_oauth.py
│  └─ token_store.py
├─ tools/
│  ├─ gmail.py
│  ├─ calendar.py
│  ├─ contacts.py
│  ├─ search.py
│  └─ alarm.py
├─ config/
│  └─ settings.py
└─ mobile/PhoneAgentApp/
   ├─ screens/
   ├─ services/
   ├─ components/
   └─ android/
```

---

## Quick Start

> [!IMPORTANT]
> For V2 Android automation development, native code changes require a full rebuild.
> If you modify files under `mobile/PhoneAgentApp/android/`, run:
> `npx expo run:android --device`
> instead of only `npx expo start`.

### 1. Backend setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Create `.env` in repo root:

```env
HOST=0.0.0.0
PORT=8000
DEBUG=true

GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/callback

BRAVE_SEARCH_API_KEY=
```

Run backend:

```bash
uvicorn server:app --reload
```

Docs:

- `http://127.0.0.1:8000/docs`

### 2. Mobile app setup

```bash
cd mobile/PhoneAgentApp
npm install
```

If you only want Metro:

```bash
npx expo start
```

If you changed native Android code for V2, rebuild the app:

```bash
npx expo run:android
```

### 3. App settings

In the app:

- Set backend URL
  - Emulator: `http://10.0.2.2:8000`
  - Real device: `http://<your-laptop-lan-ip>:8000`
- Set provider and API key
- Connect Google if you want Gmail/Calendar/Contacts tools

---

## API Overview

### V1

#### `POST /chat`

```json
{
  "message": "Remind me in 1 minute to drink water",
  "session_id": "talk_a",
  "provider": "sarvam",
  "api_key": "YOUR_KEY",
  "model": "sarvam-30b",
  "base_url": "https://api.sarvam.ai/v1",
  "user_id": "default_user"
}
```

Response:

```json
{
  "reply": "string",
  "actions_taken": [],
  "alarm_data": null,
  "requires_confirmation": false,
  "iterations": 1,
  "task_notifications": []
}
```

Useful routes:

- `GET /`
- `GET /providers`
- `GET /tasks/{session_id}`
- `DELETE /chat/history/{session_id}`
- `GET /auth/login`
- `GET /auth/status`
- `DELETE /auth/logout`

### V2

#### `POST /v2/chat`

Starts a V2 automation task and returns either:

- immediate guidance,
- a `next_action`,
- or a request for device observation.

#### `POST /v2/device/observe`

Sends current Android accessibility snapshot to backend.

#### `POST /v2/device/action-result`

Returns action result plus optional follow-up observation.

#### `GET /v2/apps`

Lists supported app mappings.

#### `GET /v2/tasks/{session_id}`

Returns current V2 task state for a session.

---

## How To Test

### Test V1

1. Start backend
2. Open app
3. Add provider key in Settings
4. Try:
   - `Remind me in 1 minute to drink water`
   - `What is my schedule tomorrow?`
   - `Email my professor about leave for 4 days`

### Test V2

1. Start backend
2. Build Android app with native code:
   - `npx expo run:android`
3. Open app
4. Go to `Settings -> Automation Lab`
5. Enable accessibility service
6. Try:
   - `Open Swiggy`
   - `Search biryani on Swiggy`
   - `Order biryani under 250 with rating above 4.5 using cash on delivery`

---

## Current Limitations

- V2 is scaffolded and testable, but not yet fully robust across all app layouts
- Swiggy heuristics are early-stage
- Checkout boundary is intentionally conservative
- Real-device validation is still required after Android native changes
- Background push for task completion is not built yet
- There is still room to improve line-ending cleanup and cross-platform dev ergonomics

## Known Blocker: Accessibility Disabled

Symptoms:
- V2 appears active but keeps operating on the wrong screen.
- Observations show app UI unrelated to requested target flow.

Diagnosis:
- Android Accessibility service is OFF or disconnected.

Fix:
1. Open `Automation Lab`.
2. Tap `Open Accessibility Settings`.
3. Enable the AgentX accessibility service.
4. Return and tap `Check Status` until `enabled: Yes`.

---

## Roadmap

### Near-term

- Improve Swiggy card extraction and option ranking
- Add richer task traces and retries
- Improve V2 failure recovery and clarification flow
- Add better offline app exploration and UTG memory generation

### Mid-term

- WhatsApp automation
- More generic app widgets and reusable flows
- Push notifications for task completion
- Multi-device and reconnect handling

### Long-term

- General Android operating layer
- More reliable low-cost decision routing
- Hosted multi-user deployment

---

## Security Notes

- Use your own provider API keys
- Keep `.tokens/` private
- Keep `.data/token.key` private
- Do not expose this backend publicly without auth, rate limits, and access control
- `/chat` now includes basic in-memory rate limiting to reduce accidental provider-cost spikes
- V2 automation should stop before irreversible final actions unless explicitly confirmed

---

## Brand

- **Primary Orange:** `#FF6B35`
- **Accent Red:** `#EF4444`

---

## License

MIT
