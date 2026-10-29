import asyncio
from types import SimpleNamespace

import pytest

from coworker.automation.scheduler import Scheduler
from coworker.automation.store import TaskStore
from extensions.career_mcp.subscription_runtime import schedule_tick


@pytest.mark.asyncio
async def test_shutdown_during_process_creation_does_not_leave_a_digest_running(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCAR_LOCAL_MODE", "1")
    entered, release, exited = asyncio.Event(), asyncio.Event(), asyncio.Event()
    class Child:
        returncode = None
        def terminate(self):
            self.returncode = 0
            exited.set()
        def kill(self):
            self.terminate()
        async def wait(self):
            await exited.wait()
            return self.returncode
    child = Child()
    async def spawn(*args, **kwargs):
        assert args[1:] == ("-m", "extensions.career_mcp.subscription_runtime")
        entered.set()
        await release.wait()
        return child
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    async def unused(*args):
        raise AssertionError("generic agent tasks are not used")
    scheduler = Scheduler(TaskStore(tmp_path / "tasks.sqlite3"), unused)
    manager = SimpleNamespace(scheduler=scheduler)
    await schedule_tick(manager)
    await entered.wait()
    stopping = asyncio.create_task(scheduler.stop())
    await asyncio.sleep(0)
    release.set()
    await stopping
    assert child.returncode == 0
