# providers/base.py
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class BaseLLMProvider(ABC):
    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    @abstractmethod
    async def chat(
        self,
        messages: List[Dict],
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2048
    ) -> str:
        pass

    @abstractmethod
    async def chat_with_tools(
        self,
        messages: List[Dict],
        tools: List[Dict],
        system_prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        pass