# providers/index.py
# One generic OpenAI-compatible client for ALL providers.
# Sarvam, Groq, Gemini, OpenAI all use the same interface — just swap base_url + api_key.

from openai import AsyncOpenAI
from typing import List, Dict, Any, Optional
from .base import BaseLLMProvider


class GenericProvider(BaseLLMProvider):
    def __init__(self, api_key: str, base_url: str, model: str):
        super().__init__(api_key, base_url, model)
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def chat(
        self,
        messages: List[Dict],
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2048
    ) -> str:
        all_messages = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=all_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content

    async def chat_with_tools(
        self,
        messages: List[Dict],
        tools: List[Dict],
        system_prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        all_messages = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=all_messages,
            tools=tools,
            tool_choice="auto",
        )
        msg = response.choices[0].message
        return {
            "content": msg.content,
            "tool_calls": msg.tool_calls,
            "finish_reason": response.choices[0].finish_reason
        }


def get_provider(
    provider: str,
    api_key: str,
    model: str = None,
    base_url: str = None
) -> BaseLLMProvider:
    from config.settings import PROVIDER_PRESETS
    presets = PROVIDER_PRESETS.get(provider, {})
    return GenericProvider(
        api_key=api_key,
        base_url=base_url or presets.get("base_url", ""),
        model=model or presets.get("model", ""),
    )