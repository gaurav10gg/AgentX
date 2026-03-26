# <span style="color:#FF6B35;">PhoneX</span> <span style="color:#EF4444;">V1</span>

<p align="center">
  <b><span style="color:#FF6B35;">AI agent for your phone.</span></b><br/>
  <span style="color:#EF4444;">Type in the app, and it executes real actions.</span>
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-Backend-FF6B35?style=for-the-badge"/>
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-API-EF4444?style=for-the-badge"/>
  <img alt="React Native" src="https://img.shields.io/badge/React_Native-Android-FF6B35?style=for-the-badge"/>
  <img alt="Expo" src="https://img.shields.io/badge/Expo-Mobile-EF4444?style=for-the-badge"/>
</p>

---

## What is AgentX?

AgentX is a local-first mobile AI agent platform:

- You send natural language in your app.
- Backend runs a ReAct-style loop (reason -> tool -> observe).
- It can call Gmail, Calendar, Contacts, Search, Alarm, and Scheduler tools.
- It supports delayed execution ("remind me in 1 minute") with task persistence.
- It keeps per-session memory so multiple chats stay isolated.

This repo currently contains **V1** (functional backend + Android app client).

---

## V1 Features

- **Chat orchestration API (FastAPI)** with provider selection per request.
- **Tool calling agent loop** with max-iteration guard.
- **Google OAuth** (Gmail/Calendar/Contacts scopes).
- **Scheduled tasks** with persistent queue and execution status.
- **Task completion surfacing** in next user message (`task_notifications` + reply summary).
- **Session memory** in SQLite (`last N messages`).
- **Android app (Expo)** with chat UI, settings, provider key input, backend URL setup, and Google connect flow.
- **UTF-8/mojibake cleanup** in backend response sanitization.

---

## High-Level Architecture

```text
Android App (Expo)
   -> POST /chat
FastAPI Server
   -> refresh token (if needed)
   -> scheduler tick fallback
   -> run_agent()
       -> LLM provider (OpenAI-compatible endpoint)
       -> tool router
       -> memory store
       -> task store
Tools
   -> Gmail / Calendar / Contacts / Web Search / Alarm
```

---

## Project Structure

```text
phone-agent/
├─ server.py                 # FastAPI entrypoint
├─ agent/
│  ├─ agent.py               # ReAct + schedule/list/cancel task orchestration
│  ├─ toolRouter.py          # Tool schemas + runtime dispatch
│  ├─ memory.py              # SQLite conversation memory
│  ├─ task_store.py          # Pending tasks + encrypted task token cache
│  └─ scheduler.py           # Background due-task executor
├─ auth/
│  ├─ google_oauth.py        # OAuth routes
│  └─ token_store.py         # Per-user token persistence/refresh
├─ tools/
│  ├─ gmail.py
│  ├─ calendar.py
│  ├─ contacts.py
│  ├─ search.py
│  └─ alarm.py
├─ config/settings.py
└─ mobile/PhoneAgentApp/     # Expo Android client
```

---

## Quick Start (V1)

### 1. Backend setup

```bash
# from repo root
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Create `.env` in repo root:

```env
# Server
HOST=0.0.0.0
PORT=8000
DEBUG=true

# Google OAuth
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/callback

# Optional search
BRAVE_SEARCH_API_KEY=
```

Run backend:

```bash
uvicorn server:app --reload
```

Open API docs:

- `http://127.0.0.1:8000/docs`

### 2. Mobile app setup (Expo Android)

```bash
cd mobile/PhoneAgentApp
npm install
npx expo start
```

In app settings:

- Set backend URL:
  - Android emulator: `http://10.0.2.2:8000`
  - Real phone: `http://<your-laptop-lan-ip>:8000`
- Select provider (`sarvam`, `groq`, `gemini`, `openai`, or custom).
- Add your provider API key.
- Connect Google account (optional, needed for Gmail/Calendar/Contacts tools).

---

## API (V1)

### `POST /chat`

Request body:

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

Response shape:

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

Other useful routes:

- `GET /` -> health + Google connection status
- `GET /providers` -> provider presets
- `GET /tasks/{session_id}` -> pending tasks for that session
- `DELETE /chat/history/{session_id}` -> clear memory for session
- `GET /auth/login`, `/auth/status`, `DELETE /auth/logout`

---

## V1 Behavior Notes

- Memory is scoped by `session_id` (separate chats stay separate).
- Google auth is scoped by `user_id`.
- Scheduler persists tasks in `.tasks/pending_tasks.json`.
- Task completion notifications are persisted and surfaced in next chat turn.
- Scheduler fallback runs on every `/chat` request, so due tasks still process even if background loop is paused.

---

## Security Notes (Current V1)

- Use your own API keys and rotate if exposed.
- `.tokens/` stores Google tokens locally; do not commit this folder.
- `.data/token.key` is used for encrypted task token cache; keep it private.
- This is V1/dev-stage; add stricter auth/rate limits before public multi-user deployment.

---

## Brand

- **Primary Orange:** `#FF6B35`
- **Accent Red:** `#EF4444`
- Product voice: fast, action-oriented, local-first.

---

## Road to V2

- Stable background scheduler lifecycle on startup.
- Push notifications for completed tasks (not only on next chat).
- Better task conflict handling + retries.
- Expanded Android action layer (accessibility-driven automation).
- Hosted multi-user deployment path.

---

## License

MIT (recommended for open developer collaboration).
