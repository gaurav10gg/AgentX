# server.py
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn
import traceback

from agent.agent import run_agent
from auth.google_oauth import router as auth_router
from auth.token_store import refresh_token_if_needed
from config.settings import settings, PROVIDER_PRESETS

app = FastAPI(title="PhoneAgent API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Bypass ngrok browser warning for all API calls
@app.middleware("http")
async def add_ngrok_header(request: Request, call_next):
    response = await call_next(request)
    response.headers["ngrok-skip-browser-warning"] = "true"
    return response

app.include_router(auth_router)

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    provider: str = "sarvam"
    api_key: str
    model: Optional[str] = None
    base_url: Optional[str] = None
    user_id: str = "default_user"

class ChatResponse(BaseModel):
    reply: str
    actions_taken: list = []
    alarm_data: Optional[dict] = None
    requires_confirmation: bool = False
    iterations: int = 0

@app.get("/")
async def health():
    from auth.token_store import get_token
    token = get_token("default_user")
    return {
        "status": "running",
        "version": "1.0.0",
        "google_connected": token is not None
    }

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(400, "Message cannot be empty")
    if not req.api_key.strip():
        raise HTTPException(401, "API key is required")

    google_token = refresh_token_if_needed(req.user_id)

    try:
        result = await run_agent(
            user_message=req.message,
            session_id=req.session_id,
            provider=req.provider,
            api_key=req.api_key,
            model=req.model,
            base_url=req.base_url,
            google_token=google_token,
        )
        return ChatResponse(**result)
    except Exception as e:
        print("FULL ERROR:")
        traceback.print_exc()
        raise HTTPException(500, f"Agent error: {str(e)}")

@app.delete("/chat/history/{session_id}")
async def clear_history(session_id: str):
    from agent.memory import clear_history
    clear_history(session_id)
    return {"status": "cleared", "session_id": session_id}

@app.get("/providers")
async def list_providers():
    return PROVIDER_PRESETS

if __name__ == "__main__":
    uvicorn.run("server:app", host=settings.host, port=settings.port, reload=settings.debug)