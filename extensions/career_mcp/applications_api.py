"""Personal application workflow routes: local SQLite, or per-tenant PostgreSQL when hosted."""
from __future__ import annotations

import os
from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import JSONResponse


def router(hosted_service=None) -> APIRouter:
    """`hosted_service(request)` returns a per-tenant service in PostgreSQL mode, else None."""
    routes = APIRouter(prefix="/v1/career/applications")

    def service(request: Request):
        if hosted_service is not None:
            hosted = hosted_service(request)
            if hosted is not None:
                return hosted
        if os.environ.get("OPENCAR_LOCAL_MODE") != "1" or os.environ.get("DATABASE_URL"):
            raise HTTPException(404, "Local-only feature")
        from .services.applications import Applications
        return Applications()

    def run(request: Request, action):
        try:
            return {"ok": True, "data": action(service(request))}
        except HTTPException:
            raise
        except ValueError as exc:
            text = str(exc)
            return JSONResponse({"ok": False, "error": text}, status_code=409 if text.startswith("VERSION_CONFLICT") else 404 if text.startswith("NOT_FOUND") else 400)
        except Exception:
            return JSONResponse({"ok": False, "error": "求职进度保存失败，请稍后重试；已有数据不会清除。"}, status_code=500)

    @routes.post("/query")
    def query(request: Request, body: dict = Body(...)):
        def action(s):
            if set(body) - {"filters", "limit", "offset"}:
                raise ValueError("查询参数不正确。")
            return s.list(**body)
        return run(request, action)

    @routes.post("/export")
    def export(request: Request, body: dict = Body(...)):
        return run(request, lambda s: s.export(body))

    @routes.post("")
    def create(request: Request, body: dict = Body(...)):
        return run(request, lambda s: s.create(body))

    @routes.get("/{application_id}")
    def detail(request: Request, application_id: str):
        return run(request, lambda s: s.get(application_id))

    @routes.patch("/{application_id}")
    def update(request: Request, application_id: str, body: dict = Body(...)):
        return run(request, lambda s: s.update(application_id, body))

    @routes.post("/{application_id}/interviews")
    def interview(request: Request, application_id: str, body: dict = Body(...)):
        return run(request, lambda s: s.save_interview(application_id, body))

    @routes.patch("/{application_id}/interviews/{interview_id}")
    def update_interview(request: Request, application_id: str, interview_id: str, body: dict = Body(...)):
        return run(request, lambda s: s.save_interview(application_id, body, interview_id))

    @routes.delete("/{application_id}/interviews/{interview_id}")
    def delete_interview(request: Request, application_id: str, interview_id: str, body: dict = Body(...)):
        return run(request, lambda s: s.delete_interview(application_id, interview_id, body))

    return routes
