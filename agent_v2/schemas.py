from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class IntentKind(str, Enum):
    SIMPLE_LOCAL = "simple_local"
    API_TOOL = "api_tool"
    UI_AUTOMATION = "ui_automation"
    SCHEDULED_UI_AUTOMATION = "scheduled_ui_automation"


class ConstraintSet(BaseModel):
    price_max: Optional[float] = None
    rating_min: Optional[float] = None
    payment: Optional[str] = None
    cuisine: Optional[str] = None
    item_query: Optional[str] = None
    distance_max_km: Optional[float] = None
    delivery_time_max_min: Optional[int] = None
    hard: List[str] = Field(default_factory=list)
    soft: List[str] = Field(default_factory=list)


class IntentResult(BaseModel):
    raw_message: str = ""
    kind: IntentKind
    task: str
    app: Optional[str] = None
    target_package: Optional[str] = None
    constraints: ConstraintSet = Field(default_factory=ConstraintSet)
    requires_llm: bool = False
    time_context: Dict[str, Any] = Field(default_factory=dict)
    extracted_query: Optional[str] = None
    confidence: float = 0.0
    ambiguity_reasons: List[str] = Field(default_factory=list)
    classification_source: Literal["heuristic", "llm"] = "heuristic"


class RawUiNode(BaseModel):
    native_id: str
    class_name: str
    package_name: Optional[str] = None
    text: Optional[str] = None
    content_description: Optional[str] = None
    resource_id: Optional[str] = None
    bounds: Optional[Dict[str, int]] = None
    clickable: bool = False
    editable: bool = False
    focusable: bool = False
    scrollable: bool = False
    visible: bool = True
    checked: Optional[bool] = None
    selected: Optional[bool] = None
    children: List["RawUiNode"] = Field(default_factory=list)


class DeviceObservation(BaseModel):
    session_id: str
    device_id: str = "default_device"
    user_id: str = "default_user"
    foreground_app: Optional[str] = None
    screen_title: Optional[str] = None
    timestamp: Optional[str] = None
    ui_tree: Optional[RawUiNode] = None
    ui_tree_list: List[RawUiNode] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class NormalizedElement(BaseModel):
    id: str
    native_id: str
    role: str
    label: str
    text: Optional[str] = None
    package_name: Optional[str] = None
    resource_id: Optional[str] = None
    clickable: bool = False
    editable: bool = False
    scrollable: bool = False
    path: str
    score: float = 0.0
    meta: Dict[str, Any] = Field(default_factory=dict)


class NormalizedScreen(BaseModel):
    screen_id: str
    app_package: Optional[str] = None
    screen_signature: str
    title: Optional[str] = None
    html: str
    elements: List[NormalizedElement] = Field(default_factory=list)
    anchors: List[str] = Field(default_factory=list)
    candidates: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AgentAction(BaseModel):
    id: str
    action: Literal[
        "open_app",
        "tap_element",
        "type_text",
        "scroll",
        "press_back",
        "press_home",
        "wait_for",
        "complete",
        "ask_user",
    ]
    element_id: Optional[str] = None
    input_text: Optional[str] = None
    package_name: Optional[str] = None
    direction: Optional[Literal["up", "down", "left", "right"]] = None
    timeout_ms: Optional[int] = None
    reason_code: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class V2TaskState(BaseModel):
    session_id: str
    user_id: str
    device_id: str = "default_device"
    status: str = "idle"
    mode: str = "idle"
    message: str = ""
    intent: Optional[IntentResult] = None
    current_app: Optional[str] = None
    current_package: Optional[str] = None
    latest_observation: Optional[DeviceObservation] = None
    latest_screen: Optional[NormalizedScreen] = None
    pending_action: Optional[AgentAction] = None
    reply: str = ""
    history: List[Dict[str, Any]] = Field(default_factory=list)
    llm_calls: int = 0
    estimated_llm_tokens: int = 0
    classifier_calls: int = 0
    recovery_attempts: int = 0
    last_error: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class V2ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    user_id: str = "default_user"
    provider: str = "sarvam"
    api_key: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None
    device_id: str = "default_device"


class V2ChatResponse(BaseModel):
    mode: str
    reply: str
    task_state: Optional[V2TaskState] = None
    task_notifications: List[Dict[str, Any]] = Field(default_factory=list)
    requires_device_action: bool = False
    next_action: Optional[AgentAction] = None


class ObserveResponse(BaseModel):
    reply: str
    task_state: Optional[V2TaskState] = None
    normalized_screen: Optional[NormalizedScreen] = None
    next_action: Optional[AgentAction] = None
    requires_device_action: bool = False


class ActionResultRequest(BaseModel):
    session_id: str
    user_id: str = "default_user"
    device_id: str = "default_device"
    action: AgentAction
    success: bool = True
    result: Optional[str] = None
    observation: Optional[DeviceObservation] = None


RawUiNode.model_rebuild()
