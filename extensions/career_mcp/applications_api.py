"""Local-only personal workflow routes; hosted deployments expose no new surface."""
from __future__ import annotations

import os
from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import JSONResponse


def router() -> APIRouter:
    routes = APIRouter(prefix="/v1/career/applications")

    def service():
        if os.environ.get("OPENCAR_LOCAL_MODE") != "1" or os.environ.get("DATABASE_URL"):
            raise HTTPException(404, "Local-only feature")
        from .services.applications import Applications
        return Applications()

    def run(action):
        try:
            return {"ok": True, "data": action(service())}
        except HTTPException:
            raise
        except ValueError as exc:
            text = str(exc)
            return JSONResponse({"ok": False, "error": text}, status_code=409 if text.startswith("VERSION_CONFLICT") else 404 if text.startswith("NOT_FOUND") else 400)
        except Exception:
            return JSONResponse({"ok": False, "error": "求职进度保存失败，请稍后重试；已有数据不会清除。"}, status_code=500)

    @routes.post("/query")
    def query(body: dict = Body(...)):
        def action(s):
            if set(body) - {"filters", "limit", "offset"}:
                raise ValueError("查询参数不正确。")
            return s.list(**body)
        return run(action)

    @routes.post("/export")
    def export(body: dict = Body(...)):
        return run(lambda s: s.export(body))

    @routes.post("")
    def create(body: dict = Body(...)):
        return run(lambda s: s.create(body))

    @routes.get("/{application_id}")
    def detail(application_id: str):
        return run(lambda s: s.get(application_id))

    @routes.patch("/{application_id}")
    def update(application_id: str, body: dict = Body(...)):
        return run(lambda s: s.update(application_id, body))

    @routes.post("/{application_id}/interviews")
    def interview(application_id: str, body: dict = Body(...)):
        return run(lambda s: s.save_interview(application_id, body))

    @routes.patch("/{application_id}/interviews/{interview_id}")
    def update_interview(application_id: str, interview_id: str, body: dict = Body(...)):
        return run(lambda s: s.save_interview(application_id, body, interview_id))

    @routes.delete("/{application_id}/interviews/{interview_id}")
    def delete_interview(application_id: str, interview_id: str, body: dict = Body(...)):
        return run(lambda s: s.delete_interview(application_id, interview_id, body))

    return routes
