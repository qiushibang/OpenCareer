"""Local-launcher-owned official job sync; no model, hosted account or user data export."""
from __future__ import annotations

import argparse
from contextlib import contextmanager, nullcontext
import json
import os
from pathlib import Path
import signal
import sys
import time
from typing import Callable, Iterator

from .config import CareerConfig
from .crawler.adapters import JobAdapter, default_adapters, default_resumable_adapters
from .database.migrations import connect, migrate
from .database.repository import JobRepository
from .domain.crawler import JobSnapshot
from .services.crawler import CrawlerService
from .services.resumable_crawler import ResumableCrawlerService

INTERVAL = 12 * 60 * 60
STATUS_FILE = "local-job-sync.json"
REQUEST_FILE = "local-job-sync.request"


def read_status(config: CareerConfig) -> dict:
    try:
        data = json.loads((config.data_dir / STATUS_FILE).read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("sources"), list):
            return data
    except (OSError, ValueError):
        pass
    return {"state": "waiting", "sources": [], "completed": 0, "failed": 0,
            "total_sources": 0, "updated_at": 0}


def request_refresh(config: CareerConfig) -> bool:
    """Coalesce refresh clicks; the sole worker consumes the fixed local marker."""
    config.data_dir.mkdir(parents=True, exist_ok=True)
    try:
        with (config.data_dir / REQUEST_FILE).open("x", encoding="utf-8") as stream:
            stream.write("refresh\n")
        return True
    except FileExistsError:
        return False


class LocalJobSync:
    def __init__(self, config: CareerConfig, *, adapters: list[JobAdapter] | None = None,
                 resumable_adapters: list | None = None, pause: float = 2,
                 clock: Callable[[], float] = time.time) -> None:
        self.config = config
        self.adapters = default_adapters() if adapters is None else adapters
        self.resumable_adapters = (default_resumable_adapters()
                                   if resumable_adapters is None else resumable_adapters)
        self.pause = pause
        self.clock = clock
        self.crawler = CrawlerService(config)
        # Page checkpoints write before network requests. Keep their long SQLite
        # transactions away from the user's favorites/application database.
        self.staging_config = CareerConfig(config.data_dir / "local-crawl-staging")
        self.resumable = ResumableCrawlerService(self.staging_config)

    def _publish_resumable(self, adapter: JobAdapter, result: dict) -> bool:
        from .crawl_cli import _ReplayAdapter
        connection = connect(self.staging_config.database_path)
        try:
            rows = JobRepository(connection).list_cycle_jobs(result["cycle_id"])
            snapshots = [JobSnapshot(**row["snapshot"]) for row in rows]
        finally:
            connection.close()
        # Publish only a complete, validated cycle through the normal catalog
        # upsert, retaining job IDs, favorites and all failure/offline protections.
        return self.crawler.crawl(_ReplayAdapter(adapter.descriptor, snapshots)).status == "succeeded"

    def _save(self, sources: list[dict], state: str) -> dict:
        result = {"state": state, "sources": sources, "total_sources": len(sources),
                  "completed": sum(s["status"] == "succeeded" for s in sources),
                  "failed": sum(s["status"] == "failed" for s in sources),
                  "updated_at": self.clock()}
        path = self.config.data_dir / STATUS_FILE
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
        return result

    def run_cycle(self, *, force: bool = False) -> dict:
        force = force or not self.config.database_path.is_file()
        connection = connect(self.config.database_path)
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            migrate(connection)
            connection.commit()
        finally:
            connection.close()
        previous = {s["slug"]: s for s in read_status(self.config)["sources"]}
        # A small static source provides the first visible jobs quickly. All other
        # registered sources still run, including full resumable mainland sources.
        def priority(adapter: JobAdapter) -> tuple[int, str]:
            rank = {"deepseek-careers": 0, "xiaomi-careers": 1}.get(
                adapter.source_slug, 3 if "playwright" in adapter.descriptor.adapter_type else 2)
            return rank, adapter.source_slug
        adapters = sorted(self.adapters, key=priority)
        adapters = [*adapters, *self.resumable_adapters]
        resumable_slugs = {a.source_slug for a in self.resumable_adapters}
        sources = []
        for adapter in adapters:
            old = previous.get(adapter.source_slug, {})
            fresh = (not force and old.get("status") == "succeeded"
                     and self.clock() - old.get("checked_at", 0) < INTERVAL)
            sources.append({"slug": adapter.source_slug, "name": adapter.descriptor.source_name,
                            "status": "succeeded" if fresh else "queued",
                            "checked_at": old.get("checked_at", 0)})
        self._save(sources, "running")
        for adapter, source in zip(adapters, sources):
            if source["status"] == "succeeded":
                continue
            source["status"] = "running"
            self._save(sources, "running")
            try:
                # Existing CLI watchdog is Unix-only; Windows adapters retain their
                # own HTTP/browser timeouts. Keep the entire worker off the web process.
                from .crawl_cli import _watchdog
                if adapter.source_slug in resumable_slugs:
                    for _ in range(200):
                        guard = _watchdog(300) if hasattr(signal, "SIGALRM") else nullcontext()
                        with guard:
                            result = self.resumable.run_batch(adapter)
                        source["observed_unique"] = result.get("observed_unique", 0)
                        self._save(sources, "running")
                        if not result.get("has_more"):
                            break
                        time.sleep(self.pause)
                    else:
                        raise RuntimeError("batch limit; checkpoint retained")
                    succeeded = (result["status"] == "committed"
                                 and self._publish_resumable(adapter, result))
                else:
                    guard = _watchdog(300) if hasattr(signal, "SIGALRM") else nullcontext()
                    with guard:
                        result = self.crawler.crawl(adapter)
                    succeeded = result.status == "succeeded"
                source["status"] = "succeeded" if succeeded else "failed"
            except Exception:
                # Remote response text may contain query tokens or HTML. Keep it out
                # of the status API; catalog services retain their normal local evidence.
                source["status"] = "failed"
            source["checked_at"] = self.clock()
            self._save(sources, "running")
            time.sleep(self.pause)
        return self._save(sources, "partial" if any(s["status"] == "failed" for s in sources) else "completed")


@contextmanager
def worker_lock(path: Path) -> Iterator[None]:
    """OS-released lock: crashes cannot leave a permanently locked installation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        if os.name == "nt":
            import msvcrt
            if path.stat().st_size == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def main() -> int:
    parser = argparse.ArgumentParser(description="本地官方岗位后台采集")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if os.environ.get("OPENCAR_LOCAL_MODE") != "1":
        print("请通过 start_local.py 启动本地岗位采集。", file=sys.stderr)
        return 2
    config = CareerConfig.from_env()
    try:
        with worker_lock(config.data_dir / ".local-job-sync.lock"):
            sync = LocalJobSync(config)
            while True:
                marker = config.data_dir / REQUEST_FILE
                force = marker.exists()
                marker.unlink(missing_ok=True)
                sync.run_cycle(force=force)
                if args.once:
                    return 0
                deadline = time.monotonic() + INTERVAL
                while time.monotonic() < deadline and not marker.exists():
                    time.sleep(1)
    except KeyboardInterrupt:
        return 0
    except BlockingIOError:
        print("已有本地岗位采集进程运行。", file=sys.stderr)
        return 1


if __name__ == "__main__":
    def interrupted(_signum: int, _frame: object) -> None:
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    raise SystemExit(main())
