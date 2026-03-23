# agent/memory.py
from typing import List, Dict
from config.settings import settings

_sessions: Dict[str, List[Dict]] = {}

def get_history(session_id: str) -> List[Dict]:
    return _sessions.get(session_id, [])

def add_message(session_id: str, role: str, content: str):
    if session_id not in _sessions:
        _sessions[session_id] = []
    _sessions[session_id].append({"role": role, "content": content})
    max_len = settings.conversation_memory_length
    if len(_sessions[session_id]) > max_len:
        _sessions[session_id] = _sessions[session_id][-max_len:]

def clear_history(session_id: str):
    if session_id in _sessions:
        del _sessions[session_id]

def get_all_sessions() -> List[str]:
    return list(_sessions.keys())