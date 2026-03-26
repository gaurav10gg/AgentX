from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from .app_registry import list_apps
from .orchestrator import get_tasks, handle_action_result, handle_chat, handle_observation
from .schemas import ActionResultRequest, DeviceObservation, ObserveResponse, V2ChatRequest, V2ChatResponse


router = APIRouter(prefix="/v2", tags=["agent-v2"])


@router.post("/chat", response_model=V2ChatResponse)
async def v2_chat(req: V2ChatRequest):
    if not req.message.strip():
        raise HTTPException(400, "Message cannot be empty")
    return await handle_chat(req)


@router.post("/device/observe", response_model=ObserveResponse)
async def v2_device_observe(
    observation: DeviceObservation,
    provider: str = Query("sarvam"),
    api_key: Optional[str] = Query(default=None),
    model: Optional[str] = Query(default=None),
    base_url: Optional[str] = Query(default=None),
):
    return await handle_observation(
        observation=observation,
        provider=provider,
        api_key=api_key,
        model=model,
        base_url=base_url,
    )


@router.post("/device/action-result", response_model=ObserveResponse)
async def v2_device_action_result(
    req: ActionResultRequest,
    provider: str = Query("sarvam"),
    api_key: Optional[str] = Query(default=None),
    model: Optional[str] = Query(default=None),
    base_url: Optional[str] = Query(default=None),
):
    return await handle_action_result(
        req,
        provider=provider,
        api_key=api_key,
        model=model,
        base_url=base_url,
    )


@router.get("/apps")
async def v2_list_apps():
    return {"apps": list_apps()}


@router.get("/tasks/{session_id}")
async def v2_list_tasks(session_id: str):
    return {"tasks": [task.model_dump(mode="json") for task in get_tasks(session_id)]}
