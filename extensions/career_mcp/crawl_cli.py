"""无人值守抓取入口：抓一次网络，写多个数据库。

为什么需要它：仓库里原本只有 MCP 工具 `crawl_all_sources`（server.py），触发方式是让 Agent
去调工具。服务器上的每日定时任务不该依赖 Agent 和 LLM，所以这里提供一个纯命令行入口，直接
调用 `CrawlerService`——归一化、upsert、offline 判定全部复用现有实现，没有另写一套抓取逻辑。

为什么要「一次抓取、多库写入」：云端 alpha 阶段是「一个朋友一个后端容器一份数据卷」，每个人
有独立的 career.sqlite3。如果对每个人分别跑一次完整抓取，对招聘站点的请求量就会乘以人数，
很容易触发风控封 IP。所以拆成两个阶段：

    阶段一 fetch    每个数据源只请求一次网络，快照留在内存里
    阶段二 persist  把同一批快照分别写进每个人的库（各自生成 id，各自算 offline）

快照 `JobSnapshot` 是 frozen dataclass，复用给多个库是安全的。

用法：
    python -m extensions.career_mcp.crawl_cli --list
    python -m extensions.career_mcp.crawl_cli --dry-run
    python -m extensions.career_mcp.crawl_cli \
        --data-dir /targets/a/career --data-dir /targets/b/career
    python -m extensions.career_mcp.crawl_cli --only tencent-careers,xiaomi-public

退出码：0 全部成功；1 有数据源失败（其余已照常写入）；2 参数错误或没有可写目标。
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sqlite3
import sys
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from coworker.storage.factory import build_storage_runtime

from .config import CareerConfig
from .crawler.adapters import (
    JobAdapter,
    default_adapters,
    default_resumable_adapters,
)
from .database.migrations import connect, migrate
from .database.postgres_catalog_repository import (
    PostgresCatalogRepository,
)
from .domain.crawler import JobSnapshot, SourceDescriptor
from .services.crawler import CrawlerService
from .services.resumable_crawler import ResumableCrawlerService

# 同一个库可能同时被后端容器写（用户点操作）和抓取容器写。sqlite 默认 5s 超时且不开 WAL，
# 撞上就直接 "database is locked"。下面两个常量是抓取侧的退避策略。
_LOCK_RETRIES = 4
_LOCK_BACKOFF_SECONDS = 3.0


class _ReplayAdapter:
    """把阶段一抓到的快照重放给 CrawlerService，不再产生网络请求。

    形态上满足 `JobAdapter` 协议（descriptor + source_slug + fetch_jobs），因此
    CrawlerService 完全不知道自己拿到的是重放数据还是实时抓取。
    """

    def __init__(self, descriptor: SourceDescriptor, snapshots: list[JobSnapshot]) -> None:
        self.descriptor = descriptor
        self.source_slug = descriptor.source_slug
        self._snapshots = list(snapshots)

    def fetch_jobs(self) -> list[JobSnapshot]:
        return list(self._snapshots)


@dataclass
class _FetchOutcome:
    source_slug: str
    ok: bool
    snapshot_count: int = 0
    error: str | None = None
    seconds: float = 0.0
    descriptor: SourceDescriptor | None = None
    snapshots: list[JobSnapshot] = field(default_factory=list)


@dataclass
class _PersistOutcome:
    target: str
    source_slug: str
    status: str
    transitions: dict[str, int] = field(default_factory=dict)
    error: str | None = None


class _SourceTimeout(Exception):
    pass


@contextmanager
def _watchdog(seconds: int) -> Iterator[None]:
    """给单个数据源套一个墙钟上限。

    Playwright 起浏览器时如果目标站点挂住，adapter 自己的超时不一定兜得住；定时任务被一个源
    卡死整晚是最难排查的故障，所以在这里用 SIGALRM 强制打断（容器里是 Linux，够用）。
    """

    if seconds <= 0:
        yield
        return

    def _on_alarm(signum, frame):  # noqa: ANN001 - signal 回调签名固定
        raise _SourceTimeout(f"source exceeded {seconds}s wall clock limit")

    previous = signal.signal(signal.SIGALRM, _on_alarm)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def _log(message: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[crawl {stamp}] {message}", flush=True)


def _cache_path(cache_dir: Path, source_slug: str) -> Path:
    return cache_dir / f"{source_slug}.json"


def _write_cache(cache_dir: Path, outcome: _FetchOutcome) -> None:
    """把阶段一的快照落盘。

    两个用处：① 写库失败时可以 --from-cache 重放，不用再去打一次招聘站点；
    ② 抓取和落库解耦后，落库逻辑可以脱网做确定性验证。
    """

    assert outcome.descriptor is not None
    cache_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "descriptor": asdict(outcome.descriptor),
        "snapshots": [asdict(item) for item in outcome.snapshots],
    }
    path = _cache_path(cache_dir, outcome.source_slug)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _log(f"CACHE      {outcome.source_slug} -> {path} ({len(outcome.snapshots)} 条)")


def _read_cache(cache_dir: Path, adapters: list[JobAdapter]) -> list[_FetchOutcome]:
    """从缓存目录重建阶段一的结果，完全不联网。"""

    wanted = {adapter.descriptor.source_slug for adapter in adapters}
    outcomes: list[_FetchOutcome] = []
    for path in sorted(cache_dir.glob("*.json")):
        slug = path.stem
        if slug not in wanted:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            descriptor = SourceDescriptor(**payload["descriptor"])
            snapshots = [JobSnapshot(**item) for item in payload["snapshots"]]
        except Exception as exc:  # noqa: BLE001
            outcomes.append(_FetchOutcome(slug, False, error=f"缓存不可用: {exc}"))
            _log(f"CACHE BAD  {slug}: {exc}")
            continue
        outcomes.append(
            _FetchOutcome(
                slug,
                True,
                snapshot_count=len(snapshots),
                descriptor=descriptor,
                snapshots=snapshots,
            )
        )
        _log(f"CACHE HIT  {slug}: {len(snapshots)} 条（{payload.get('fetched_at', '?')} 抓的）")
    return outcomes


def _resolve_targets(raw: list[str]) -> list[Path]:
    """--data-dir 可重复；不给就退回单库模式（CAREER_DATA_DIR 或项目默认）。"""

    if raw:
        seen: dict[Path, None] = {}
        for item in raw:
            for part in item.split(os.pathsep):
                part = part.strip()
                if part:
                    seen.setdefault(Path(part).expanduser().resolve(), None)
        return list(seen)
    return [CareerConfig.from_env().data_dir]


def _ensure_schema(data_dir: Path) -> None:
    """建表 + 开 WAL。

    WAL 是写进数据库文件头的持久属性，设一次就长期有效：让「后端读 + 抓取写」不再互相阻塞，
    把锁冲突收敛到「写 vs 写」这种罕见情况。
    """

    config = CareerConfig(data_dir=data_dir)
    connection = connect(config.database_path)
    try:
        connection.execute("PRAGMA busy_timeout = 30000")
        mode = connection.execute("PRAGMA journal_mode = WAL").fetchone()[0]
        migrate(connection)
        connection.commit()
    finally:
        connection.close()
    _log(f"schema ready: {config.database_path} (journal_mode={mode})")


def _select_adapters(only: str | None, skip: str | None) -> list[JobAdapter]:
    adapters = list(default_adapters())
    if only:
        wanted = {item.strip() for item in only.split(",") if item.strip()}
        known = {adapter.descriptor.source_slug for adapter in adapters}
        unknown = sorted(wanted - known)
        if unknown:
            raise SystemExit(f"未知数据源: {', '.join(unknown)}（用 --list 查看全部）")
        adapters = [a for a in adapters if a.descriptor.source_slug in wanted]
    if skip:
        unwanted = {item.strip() for item in skip.split(",") if item.strip()}
        adapters = [a for a in adapters if a.descriptor.source_slug not in unwanted]
    return sorted(adapters, key=lambda a: a.descriptor.source_slug)


def _run_resumable_batches(batch_count: int) -> int:
    if batch_count < 1:
        raise ValueError("resumable batch count must be positive")
    try:
        runtime = build_storage_runtime()
    except RuntimeError:
        _log("PostgreSQL/Redis 初始化失败")
        return 2
    try:
        if runtime.mode != "postgres":
            _log("可续跑字节来源只在 PostgreSQL 模式启用")
            return 2

        @contextmanager
        def repository_session():
            with runtime.database.shared_transaction() as connection:
                yield PostgresCatalogRepository(connection)

        service = ResumableCrawlerService(
            repository_session=repository_session,
        )
        failed = False
        for adapter in default_resumable_adapters():
            for _ in range(batch_count):
                try:
                    progress = service.run_batch(adapter)
                except Exception as exc:
                    failed = True
                    _log(
                        f"RESUME FAIL {adapter.source_slug}: "
                        f"{type(exc).__name__}: {exc}"
                    )
                    break
                _log(
                    f"RESUME {adapter.source_slug}: "
                    + json.dumps(progress, ensure_ascii=False)
                )
                if progress["status"] in {
                    "committed",
                    "degraded",
                    "failed",
                }:
                    failed = failed or progress["status"] != "committed"
                    break
        return 1 if failed else 0
    finally:
        runtime.close()


def _fetch_all(adapters: list[JobAdapter], *, timeout: int, pause: float) -> list[_FetchOutcome]:
    """阶段一：每个源只打一次网络。单源失败不影响其它源。"""

    outcomes: list[_FetchOutcome] = []
    for index, adapter in enumerate(adapters):
        slug = adapter.descriptor.source_slug
        started = time.monotonic()
        try:
            with _watchdog(timeout):
                snapshots = adapter.fetch_jobs()
        except _SourceTimeout as exc:
            outcomes.append(
                _FetchOutcome(slug, False, error=str(exc), seconds=time.monotonic() - started)
            )
            _log(f"FETCH TIMEOUT {slug}: {exc}")
        except Exception as exc:  # noqa: BLE001 - 定时任务必须容忍任意站点异常
            outcomes.append(
                _FetchOutcome(
                    slug,
                    False,
                    error=f"{type(exc).__name__}: {exc}",
                    seconds=time.monotonic() - started,
                )
            )
            _log(f"FETCH FAIL {slug}: {type(exc).__name__}: {exc}")
        else:
            elapsed = time.monotonic() - started
            outcomes.append(
                _FetchOutcome(
                    slug,
                    True,
                    snapshot_count=len(snapshots),
                    seconds=elapsed,
                    descriptor=adapter.descriptor,
                    snapshots=list(snapshots),
                )
            )
            _log(f"FETCH OK   {slug}: {len(snapshots)} 条，{elapsed:.1f}s")
        # 源之间歇一下，避免连续打同一批站点时被当成爬虫。
        if pause > 0 and index + 1 < len(adapters):
            time.sleep(pause)
    return outcomes


def _persist_one(
    data_dir: Path, descriptor: SourceDescriptor, snapshots: list[JobSnapshot]
) -> _PersistOutcome:
    """把一个源的快照写进一个库，遇到 sqlite 锁就退避重试。"""

    target = str(data_dir)
    slug = descriptor.source_slug
    service = CrawlerService(
        CareerConfig(data_dir=data_dir), adapters=[_ReplayAdapter(descriptor, snapshots)]
    )
    for attempt in range(1, _LOCK_RETRIES + 1):
        try:
            result = service.crawl_registered_source(slug, dry_run=False)
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt == _LOCK_RETRIES:
                return _PersistOutcome(target, slug, "failed", error=f"sqlite: {exc}")
            wait = _LOCK_BACKOFF_SECONDS * attempt
            _log(f"LOCKED     {slug} -> {target}，{wait:.0f}s 后重试（{attempt}/{_LOCK_RETRIES}）")
            time.sleep(wait)
        except Exception as exc:  # noqa: BLE001
            return _PersistOutcome(target, slug, "failed", error=f"{type(exc).__name__}: {exc}")
        else:
            return _PersistOutcome(
                target,
                slug,
                result.status,
                transitions=dict(result.transitions),
                error=result.error_summary,
            )
    return _PersistOutcome(target, slug, "failed", error="sqlite 持续加锁，已放弃")


def _persist_one_postgres(
    database,
    coordinator,
    descriptor: SourceDescriptor,
    snapshots: list[JobSnapshot],
    *,
    lock_ttl_seconds: int,
    repository_factory=PostgresCatalogRepository,
) -> _PersistOutcome:
    slug = descriptor.source_slug
    owner = str(uuid.uuid4())
    if not coordinator.acquire_crawler_lock(
        slug,
        owner,
        lock_ttl_seconds,
    ):
        return _PersistOutcome(
            "postgresql",
            slug,
            "failed",
            error="crawl source is already running",
        )

    @contextmanager
    def repository_session():
        with database.shared_transaction() as connection:
            yield repository_factory(connection)

    try:
        service = CrawlerService(
            adapters=[_ReplayAdapter(descriptor, snapshots)],
            repository_session=repository_session,
        )
        result = service.crawl_registered_source(slug, dry_run=False)
        if result.status == "succeeded":
            coordinator.publish(
                "catalog",
                {
                    "type": "source_updated",
                    "source_slug": slug,
                    "run_id": result.run_id,
                },
            )
        return _PersistOutcome(
            "postgresql",
            slug,
            result.status,
            transitions=dict(result.transitions),
            error=result.error_summary,
        )
    except Exception as exc:  # noqa: BLE001
        return _PersistOutcome(
            "postgresql",
            slug,
            "failed",
            error=f"{type(exc).__name__}: {exc}",
        )
    finally:
        coordinator.release_lease(f"crawler:{slug}", owner)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m extensions.career_mcp.crawl_cli",
        description="抓取全部公开岗位源并写入一个或多个 career 数据库（供服务器定时任务使用）。",
    )
    parser.add_argument(
        "--data-dir",
        action="append",
        default=[],
        metavar="PATH",
        help="目标 career 数据目录（含 career.sqlite3）。可重复传，或用路径分隔符分隔。"
        "不传则使用 CAREER_DATA_DIR。",
    )
    parser.add_argument("--only", help="只跑这些 source_slug，逗号分隔")
    parser.add_argument("--skip", help="跳过这些 source_slug，逗号分隔")
    parser.add_argument(
        "--dry-run", action="store_true", help="只抓取不落库，用来验证数据源是否还通"
    )
    parser.add_argument("--list", action="store_true", help="列出全部数据源后退出")
    parser.add_argument(
        "--source-timeout",
        type=int,
        default=int(os.environ.get("CRAWL_SOURCE_TIMEOUT", "300")),
        help="单个数据源墙钟上限（秒），0 表示不限。默认 300",
    )
    parser.add_argument(
        "--pause",
        type=float,
        default=float(os.environ.get("CRAWL_PAUSE_SECONDS", "2")),
        help="相邻数据源之间的间隔（秒），默认 2",
    )
    parser.add_argument(
        "--snapshot-cache",
        metavar="DIR",
        default=os.environ.get("CRAWL_SNAPSHOT_CACHE") or None,
        help="把抓到的快照另存为 JSON（每个源一个文件），便于失败重放和排查",
    )
    parser.add_argument(
        "--from-cache",
        action="store_true",
        help="不联网，直接用 --snapshot-cache 里的快照落库（重放上一次抓取的结果）",
    )
    parser.add_argument(
        "--resumable-only",
        action="store_true",
        help="只运行 PostgreSQL 中可断点续跑的字节全量来源",
    )
    parser.add_argument(
        "--resumable-batches",
        type=int,
        default=int(os.environ.get("CRAWL_RESUMABLE_BATCHES", "12")),
        help="每个可续跑来源本次最多执行的 20 页批次数，默认 12",
    )
    parser.add_argument("--json", action="store_true", help="最后额外打印一行 JSON 汇总")
    args = parser.parse_args(argv)

    if args.list:
        for adapter in [
            *_select_adapters(None, None),
            *default_resumable_adapters(),
        ]:
            d = adapter.descriptor
            print(f"{d.source_slug:<28} {d.company_name:<12} {d.adapter_type:<10} {d.base_url or '-'}")
        return 0
    if args.resumable_only:
        return _run_resumable_batches(args.resumable_batches)

    adapters = _select_adapters(args.only, args.skip)
    if not adapters:
        _log("没有选中任何数据源")
        return 2

    cache_dir = Path(args.snapshot_cache).expanduser().resolve() if args.snapshot_cache else None
    if args.from_cache and cache_dir is None:
        _log("--from-cache 需要同时给 --snapshot-cache DIR")
        return 2

    started_at = datetime.now(timezone.utc)
    _log(
        f"开始：{len(adapters)} 个数据源，dry_run={args.dry_run}，"
        f"来源={'缓存重放' if args.from_cache else '实时抓取'}"
    )

    if args.from_cache:
        assert cache_dir is not None
        if not cache_dir.is_dir():
            _log(f"缓存目录不存在: {cache_dir}")
            return 2
        fetched = _read_cache(cache_dir, adapters)
        if not fetched:
            _log("缓存里没有匹配的数据源")
            return 2
    else:
        fetched = _fetch_all(adapters, timeout=args.source_timeout, pause=args.pause)
        if cache_dir is not None:
            for item in fetched:
                if item.ok:
                    _write_cache(cache_dir, item)
    ok_fetches = [item for item in fetched if item.ok]
    failed_fetches = [item for item in fetched if not item.ok]

    persisted: list[_PersistOutcome] = []
    targets: list[Path | str] = []
    if not args.dry_run:
        cloud_requested = bool(
            os.environ.get("DATABASE_URL")
            or os.environ.get("REDIS_URL")
        )
        if cloud_requested:
            if args.data_dir:
                _log("PostgreSQL 云模式不接受 --data-dir")
                return 2
            try:
                runtime = build_storage_runtime()
            except RuntimeError:
                _log("PostgreSQL/Redis 初始化失败")
                return 2
            try:
                if runtime.mode != "postgres":
                    _log("云端抓取需要 PostgreSQL 和 Redis")
                    return 2
                targets = ["postgresql"]
                for item in ok_fetches:
                    assert item.descriptor is not None
                    outcome = _persist_one_postgres(
                        runtime.database,
                        runtime.coordinator,
                        item.descriptor,
                        item.snapshots,
                        lock_ttl_seconds=max(
                            int(args.source_timeout) + 60,
                            60,
                        ),
                    )
                    persisted.append(outcome)
                    flag = (
                        "OK  " if outcome.status != "failed" else "FAIL"
                    )
                    detail = outcome.error or json.dumps(
                        outcome.transitions,
                        ensure_ascii=False,
                    )
                    _log(
                        f"WRITE {flag} {outcome.source_slug} "
                        f"-> postgresql: {detail}"
                    )
            finally:
                runtime.close()
        else:
            targets = _resolve_targets(args.data_dir)
            if not targets:
                _log("没有可写入的目标数据目录")
                return 2
            for target in targets:
                assert isinstance(target, Path)
                _ensure_schema(target)
            for target in targets:
                assert isinstance(target, Path)
                for item in ok_fetches:
                    assert item.descriptor is not None
                    outcome = _persist_one(
                        target,
                        item.descriptor,
                        item.snapshots,
                    )
                    persisted.append(outcome)
                    flag = (
                        "OK  " if outcome.status != "failed" else "FAIL"
                    )
                    detail = outcome.error or json.dumps(
                        outcome.transitions,
                        ensure_ascii=False,
                    )
                    _log(
                        f"WRITE {flag} {outcome.source_slug} "
                        f"-> {target}: {detail}"
                    )

    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
    write_failures = [item for item in persisted if item.status == "failed"]
    summary = {
        "started_at": started_at.isoformat(),
        "elapsed_seconds": round(elapsed, 1),
        "dry_run": args.dry_run,
        "from_cache": args.from_cache,
        "targets": [str(t) for t in targets],
        "sources_total": len(adapters),
        "sources_fetched": len(ok_fetches),
        "sources_fetch_failed": [
            {"source": item.source_slug, "error": item.error} for item in failed_fetches
        ],
        "snapshots_total": sum(item.snapshot_count for item in ok_fetches),
        "writes_total": len(persisted),
        "writes_failed": [
            {"target": item.target, "source": item.source_slug, "error": item.error}
            for item in write_failures
        ],
    }
    _log(
        f"结束：抓到 {summary['snapshots_total']} 条 / 成功源 {len(ok_fetches)}/{len(adapters)}"
        f" / 写入 {len(persisted) - len(write_failures)}/{len(persisted)} / 耗时 {elapsed:.0f}s"
    )
    if args.json:
        print(json.dumps(summary, ensure_ascii=False))

    return 1 if (failed_fetches or write_failures) else 0


if __name__ == "__main__":
    sys.exit(main())
