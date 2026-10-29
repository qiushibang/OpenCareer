"""Portable read-only job MCP entrypoint; no resumes, shell or file tools."""
from __future__ import annotations
import argparse
import os
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenCareer portable jobs MCP (stdio)")
    parser.add_argument("--data-dir", type=Path, required=True, help="Career data directory containing career.sqlite3")
    parser.add_argument("--sync", action="store_true", help="Download public catalog before serving; no cloud login")
    parser.add_argument("--sync-only", action="store_true", help="Download the public catalog and exit")
    parser.add_argument("--state-dir", type=Path, help="Explicit local model settings directory; default is data-dir/mcp-state")
    parser.add_argument("--subscriptions", action="store_true", help="Expose DISABLED draft management; activation remains in local UI")
    args = parser.parse_args()
    os.environ["CAREER_DATA_DIR"] = str(args.data_dir.expanduser().resolve())
    os.environ["COWORKER_STATE_DIR"] = str((args.state_dir or args.data_dir / "mcp-state").expanduser().resolve())
    for key in ("DATABASE_URL", "REDIS_URL", "OPENCAR_PRINCIPAL_USER_ID"):
        os.environ.pop(key, None)
    os.environ["OPENCAR_LOCAL_MODE"] = "1" if args.subscriptions else "0"
    if args.sync or args.sync_only:
        from .services.public_catalog import PublicCatalogSync
        from .config import CareerConfig
        result = PublicCatalogSync(CareerConfig.from_env()).run()
        if args.sync_only:
            if result.get("failed"):
                raise SystemExit("公共岗位同步未完成，请检查网络；已有数据保留。")
            return
    from mcp.server.fastmcp import FastMCP
    from . import server
    app = FastMCP("opencareer-jobs")
    for tool in (server.get_job_catalog_schema, server.search_job_catalog, server.get_job_catalog_status, server.get_job):
        app.tool(annotations={"readOnlyHint": True})(tool)
    if args.subscriptions:
        app.tool()(server.list_job_subscriptions)
        app.tool()(server.draft_job_subscription)
    app.run()


if __name__ == "__main__":
    main()
