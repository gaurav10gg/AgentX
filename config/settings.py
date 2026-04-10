# config/settings.py
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    llm_provider: str = "sarvam"
    llm_base_url: str = "https://api.sarvam.ai/v1"
    llm_api_key: str = ""
    llm_model: str = "sarvam-30b"
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/callback"
    brave_search_api_key: Optional[str] = None
    max_iterations: int = 10
    tool_timeout_seconds: int = 15
    conversation_memory_length: int = 20
    v2_max_llm_calls_per_task: int = 4
    v2_max_llm_calls_per_task_hard_cap: int = 8
    v2_max_recovery_attempts: int = 2
    v2_llm_token_budget: int = 6000
    v2_llm_same_screen_cooldown_events: int = 8
    v2_llm_same_screen_max_calls: int = 1
    v2_memory_shortcut_threshold: float = 0.88
    v2_intent_confidence_accept_threshold: float = 0.88
    v2_classifier_temperature: float = 0.0
    v2_max_classifier_calls_per_task: int = 1
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# THIS IS OUTSIDE THE CLASS - no indentation
settings = Settings()

PROVIDER_PRESETS = {
    "sarvam": {"base_url": "https://api.sarvam.ai/v1", "model": "sarvam-30b"},
    "groq": {"base_url": "https://api.groq.com/openai/v1", "model": "llama-3.3-70b-versatile"},
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "model": "gemini-2.0-flash"},
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
    "custom": {"base_url": "", "model": ""},
}
