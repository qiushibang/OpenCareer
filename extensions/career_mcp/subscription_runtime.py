"""Attach bounded subscription processes to OpenWorker's existing scheduler lifecycle."""
from __future__ import annotations
import asyncio
import os
import sys


async def schedule_tick(manager) -> None:
    if os.environ.get("OPENCAR_LOCAL_MODE") != "1":
        return
    prior = getattr(manager, "_career_digest_task", None)
    if prior is not None and not prior.done():
        return

    async def execute():
        creation = asyncio.create_task(asyncio.create_subprocess_exec(sys.executable, "-m", "extensions.career_mcp.subscription_runtime",
                   stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL))
        process = None
        try:
            process = await asyncio.shield(creation)
            await process.wait()
        finally:
            if process is None:
                process = await creation
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()

    task = asyncio.create_task(execute())
    manager._career_digest_task = task
    # The existing scheduler cancels and awaits these tasks on shutdown.
    manager.scheduler._spawned.add(task)
    task.add_done_callback(manager.scheduler._spawned.discard)


def main():
    if os.environ.get("OPENCAR_LOCAL_MODE") != "1":
        return
    from .services.catalog_semantic import configured_semantic
    from .services.job_catalog import JobCatalog
    from .services.job_subscriptions import JobSubscriptions
    JobSubscriptions(catalog=JobCatalog(semantic=configured_semantic())).tick()


if __name__ == "__main__":
    main()
