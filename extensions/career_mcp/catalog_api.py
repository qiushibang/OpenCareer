"""Attended local UI endpoints; no new production authentication exceptions."""
from __future__ import annotations
import os
from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import JSONResponse


def router() -> APIRouter:
    routes = APIRouter(prefix="/v1/career")

    def services():
        if os.environ.get("OPENCAR_LOCAL_MODE") != "1":
            raise HTTPException(404, "Local-only feature")
        from .services.job_catalog import JobCatalog
        from .services.catalog_semantic import configured_semantic
        from .services.job_subscriptions import JobSubscriptions
        catalog = JobCatalog(semantic=configured_semantic())
        return catalog, JobSubscriptions(catalog=catalog)

    def run(action):
        try:
            return {"ok": True, "data": action()}
        except HTTPException:
            raise
        except ValueError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
        except Exception:
            return JSONResponse({"ok": False, "error": "操作失败，请检查本地数据或模型连接。"}, status_code=500)

    @routes.get("/catalog/schema")
    def schema():
        return run(lambda: services()[0].schema())

    @routes.get("/catalog/status")
    def status():
        return run(lambda: services()[0].status())

    @routes.post("/catalog/search")
    def search(body: dict = Body(...)):
        return run(lambda: services()[0].search(**body))

    @routes.get("/catalog/results/{result_id}")
    def result(result_id: str):
        return run(lambda: services()[0].result(result_id))

    @routes.get("/job-subscriptions")
    def subscriptions():
        return run(lambda: services()[1].list())

    @routes.post("/job-subscriptions")
    def draft(body: dict = Body(...)):
        payload = dict(body)
        sid = payload.pop("subscription_id", None)
        return run(lambda: services()[1].draft(payload, subscription_id=sid))

    @routes.get("/job-subscriptions/channels")
    def channels():
        return run(lambda: services()[1].channels())

    @routes.post("/job-subscriptions/channels")
    def channel(body: dict = Body(...)):
        return run(lambda: services()[1].save_channel(**body))

    @routes.delete("/job-subscriptions/channels/{channel_id}")
    def remove_channel(channel_id: str):
        return run(lambda: services()[1].remove_channel(channel_id))

    @routes.post("/job-subscriptions/channels/{channel_id}/test")
    def test_channel(channel_id: str, body: dict = Body(...)):
        def action():
            if body.get("confirmed") is not True:
                raise ValueError("请明确点击发送测试消息。")
            return services()[1].test_channel(channel_id)
        return run(action)

    @routes.post("/job-subscriptions/{sid}/activate")
    def activate(sid: str, body: dict = Body(...)):
        def action():
            if body.get("confirmed") is not True:
                raise ValueError("请阅读筛选条件、渠道与时间后确认启用。")
            return services()[1].activate(sid, body.get("version"))
        return run(action)

    @routes.post("/job-subscriptions/{sid}/pause")
    def pause(sid: str):
        return run(lambda: services()[1].pause(sid))

    @routes.post("/job-subscriptions/{sid}/preview")
    def preview(sid: str):
        return run(lambda: services()[1].preview(sid))

    @routes.get("/job-subscriptions/{sid}/runs")
    def runs(sid: str):
        return run(lambda: services()[1].runs(sid))

    @routes.post("/job-subscriptions/runs/{run_id}/retry")
    def retry(run_id: str, body: dict = Body(...)):
        def action():
            if body.get("confirmed") is not True:
                raise ValueError("请确认只重试明确失败的消息。")
            return services()[1].retry_run(run_id)
        return run(action)

    return routes
