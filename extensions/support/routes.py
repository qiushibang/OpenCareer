"""Explicit support HTTP surface; never exposed to the Agent tool registry."""
from typing import Literal
from fastapi import APIRouter, Request, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from coworker.server.identity import Principal
from .feedback import FeedbackStore, FeedbackConflict
from .admin import SupportCenter
from .alerts import AlertCenter


class FeedbackInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["bug", "suggestion", "other"]
    description: str = Field(min_length=5, max_length=2000)
    nonce: str = Field(pattern=r"^[0-9a-f]{32}$")
    ui_release: str = Field(default="unknown", max_length=64)
    request_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")


class AnonymousFeedbackInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["bug", "suggestion", "other"]
    description: str = Field(min_length=5, max_length=2000)
    nonce: str = Field(pattern=r"^[0-9a-f]{32}$")
    ui_release: str = Field(default="unknown", max_length=64)


class AdminUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    status: Literal["open", "in_progress", "resolved", "declined"]
    reply: str = Field(max_length=1200)
    expected_updated_at: int = Field(ge=0)


class AdminMerge(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    target_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    expected_updated_at: int = Field(ge=0)


def support_router(store: FeedbackStore) -> APIRouter:
    router = APIRouter(prefix="/v1/support")
    center = SupportCenter(store)
    alerts = AlertCenter(center)

    def require_admin(request: Request) -> Principal:
        if not center.is_admin(request.state.principal):
            raise HTTPException(status_code=403, detail="没有问题中心的管理权限。")
        return request.state.principal

    @router.get("/capabilities")
    def capabilities(request: Request) -> dict[str, bool]:
        return {"admin": center.is_admin(request.state.principal)}

    @router.get("/admin/feedback")
    def admin_list(principal: Principal = Depends(require_admin), status: Literal["open", "in_progress", "resolved", "declined", "merged"] | None = None,
                   kind: Literal["bug", "suggestion", "other"] | None = None, offset: int = Query(default=0, ge=0, le=100000)) -> dict[str, list[dict]]:
        return {"feedback": center.list_feedback(principal, status=status, kind=kind, offset=offset)}

    @router.patch("/admin/feedback/{feedback_id}", response_model=None)
    def admin_update(body: AdminUpdate, feedback_id: str, principal: Principal = Depends(require_admin)) -> dict[str, dict] | JSONResponse:
        try:
            item = center.update(principal, feedback_id, **body.model_dump())
        except FeedbackConflict as error:
            return JSONResponse({"error": str(error)}, status_code=409)
        return {"feedback": item}

    @router.get("/admin/feedback/{feedback_id}", response_model=None)
    def admin_detail(feedback_id: str, principal: Principal = Depends(require_admin)) -> dict | JSONResponse:
        try:
            return center.detail(principal, feedback_id)
        except FeedbackConflict:
            return JSONResponse({"error": "反馈不存在。"}, status_code=404)

    @router.post("/admin/feedback/{feedback_id}/merge", response_model=None)
    def admin_merge(body: AdminMerge, feedback_id: str, principal: Principal = Depends(require_admin)) -> dict[str, dict] | JSONResponse:
        try:
            return {"feedback": center.merge(principal, feedback_id, **body.model_dump())}
        except FeedbackConflict as error:
            return JSONResponse({"error": str(error)}, status_code=409)

    @router.get("/admin/audit")
    def admin_audit(principal: Principal = Depends(require_admin)) -> dict[str, list[dict]]:
        return {"audit": center.list_audit(principal)}

    @router.get("/admin/alerts")
    def admin_alerts(principal: Principal = Depends(require_admin)) -> dict[str, list[dict]]:
        return {"alerts": alerts.application_alerts(principal)}

    @router.post("/anonymous-feedback", status_code=201, response_model=None)
    def anonymous_feedback(body: AnonymousFeedbackInput) -> dict[str, dict[str, str]] | JSONResponse:
        if len(body.description.strip()) < 5:
            return JSONResponse({"error": "请填写至少五个字的问题描述。"}, status_code=422)
        try:
            item = store.create(None, **body.model_dump())
        except FeedbackConflict as error:
            return JSONResponse({"error": str(error)}, status_code=409)
        return {"feedback": {"id": item["id"]}}

    @router.post("/feedback", status_code=201, response_model=None)
    def submit_feedback(request: Request, body: FeedbackInput) -> dict[str, dict] | JSONResponse:
        if len(body.description.strip()) < 5:
            return JSONResponse({"error": "请填写至少五个字的问题描述。"}, status_code=422)
        try:
            item = store.create(request.state.principal, **body.model_dump())
        except FeedbackConflict as error:
            return JSONResponse({"error": str(error)}, status_code=409)
        return {"feedback": item}

    @router.get("/feedback")
    def list_feedback(request: Request, limit: int = Query(default=50, ge=1, le=50), offset: int = Query(default=0, ge=0, le=500)) -> dict[str, list[dict]]:
        return {"feedback": store.list_own(request.state.principal, limit=limit, offset=offset)}

    @router.get("/feedback/{feedback_id}", response_model=None)
    def get_feedback(request: Request, feedback_id: str) -> dict[str, dict] | JSONResponse:
        item = store.get_own(request.state.principal, feedback_id)
        if item is None:
            return JSONResponse({"error": "反馈不存在。"}, status_code=404)
        return {"feedback": item}

    return router
