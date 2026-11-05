"""04:00 Shanghai full rebuilds, isolated from website and user databases.

Each daily run owns an initially empty database. Only a complete registered-source
scan may update the public history ledger and atomically publish a full feed.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import json
import multiprocessing
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
import os
from pathlib import Path
import signal
import time
from typing import Callable, Iterator
from zoneinfo import ZoneInfo

from .config import CareerConfig
from .crawler.adapters import JobAdapter, default_adapters, default_resumable_adapters
from .database.migrations import connect
from .domain.crawler import SourceDescriptor
from .local_jobs import LocalJobSync, worker_lock, read_status
from .public_catalog_format import publish_stream, public_job
from .services.public_catalog import PublicCatalogSync

SHANGHAI = ZoneInfo('Asia/Shanghai')


def generation_day(now: datetime) -> str:
    """Most recent scheduled 04:00, independent of the host's timezone."""
    if now.tzinfo is None:
        raise ValueError('scheduler clock must have a timezone')
    local = now.astimezone(SHANGHAI)
    return (local.date() - timedelta(days=local.hour < 4)).isoformat()


def seconds_to_next_run(now: datetime) -> float:
    local = now.astimezone(SHANGHAI)
    target = local.replace(hour=4, minute=0, second=0, microsecond=0)
    if target <= local:
        target += timedelta(days=1)
    return (target - local).total_seconds()


def _save(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def _read(path: Path) -> dict:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError('invalid daily catalog state')
    return value


def _step_worker(root: str, output: str, sender: Connection) -> None:
    """One bounded generation advance, supervised independently of networking."""
    if os.name != 'nt':
        os.setsid()
    try:
        sender.send(DailyCatalogRunner(Path(root), Path(output)).step())
    except Exception as exc:
        sender.send({'state':'failed', 'error_type':type(exc).__name__})
    finally:
        sender.close()


def _stop_step(process: BaseProcess) -> None:
    """Stop only this collector's child group, including its browser children."""
    if not process.is_alive():
        process.join()
        return
    try:
        if os.name != 'nt' and os.getpgid(process.pid) == process.pid:
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
    except ProcessLookupError:
        pass
    process.join(timeout=1)
    if process.is_alive():
        try:
            if os.name != 'nt' and os.getpgid(process.pid) == process.pid:
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            pass
        process.join(timeout=1)


def advance_until_boundary(root: Path, output: Path, *, clock: Callable[[], datetime] | None = None,
                           worker: Callable[[str, str, Connection], None] | None = None) -> dict:
    """A slow source must not postpone tomorrow's scheduled fresh scan.

    Source-level watchdogs remain in place, while this parent owns the daily
    deadline. Interrupted work stays isolated under yesterday's directory.
    """
    clock = clock or (lambda: datetime.now(timezone.utc))
    day = generation_day(clock())
    context = multiprocessing.get_context('spawn')
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=worker or _step_worker, args=(str(root), str(output), sender))
    process.start()
    sender.close()
    try:
        while generation_day(clock()) == day:
            if receiver.poll(min(1, seconds_to_next_run(clock()))):
                try:
                    result = receiver.recv()
                except EOFError:
                    return {'state':'failed', 'error_type':'CollectorExited'}
                process.join(timeout=1)
                return result
            if not process.is_alive():
                return {'state':'failed', 'error_type':'CollectorExited'}
        _stop_step(process)
        path = root/'runs'/day/'run.json'
        state = _read(path)
        state.update(state='superseded')
        _save(path, state)
        _save(root/'status.json', state)
        return state
    finally:
        _stop_step(process)
        receiver.close()


def _public_rows(config: CareerConfig, slug: str) -> list[dict]:
    with connect(config.database_path) as db:
        rows = db.execute('''SELECT j.external_job_id,j.title,j.description_raw,j.canonical_url,
            j.location_raw,j.locations_json,j.recruitment_type,j.status,j.first_seen_at,
            j.last_seen_at,j.last_changed_at,j.responsibilities_json,j.requirements_json
            FROM jobs j JOIN crawl_sources s ON s.id=j.crawl_source_id
            JOIN job_sources js ON js.id=j.source_id
            WHERE s.slug=? AND js.source_type='crawler' AND j.status='active'
            ORDER BY j.external_job_id''', (slug,)).fetchall()
    return [public_job({
        'external_job_id': r['external_job_id'], 'title': r['title'],
        'description_raw': r['description_raw'], 'source_url': r['canonical_url'],
        'location_raw': r['location_raw'], 'locations': json.loads(r['locations_json']),
        'recruitment_type': r['recruitment_type'], 'status': r['status'],
        'first_seen_at': r['first_seen_at'], 'observed_at': r['last_seen_at'],
        'last_changed_at': r['last_changed_at'],
        'responsibilities': json.loads(r['responsibilities_json']),
        'requirements': json.loads(r['requirements_json'])}) for r in rows]


class DailyCatalogRunner:
    def __init__(self, root: Path, output: Path, *, adapters: list[JobAdapter] | None = None,
                 resumable_adapters: list | None = None, clock: Callable[[], datetime] | None = None,
                 pause: float = 2) -> None:
        self.root, self.output = root.resolve(), output.resolve()
        self.adapters = default_adapters() if adapters is None else adapters
        self.resumable_adapters = default_resumable_adapters() if resumable_adapters is None else resumable_adapters
        from .crawler.zhipu import ZhipuMokaAdapter
        # Daily scans use the parser's complete 20x30-page envelope, rather
        # than the old interactive request budget of 30 campus jobs.
        self.adapters = [ZhipuMokaAdapter(replace(a.scope, max_jobs=600),
                            fetch_dataset=a._fetch_dataset, clock=a._clock)
                         if isinstance(a, ZhipuMokaAdapter) else a for a in self.adapters]
        from .crawler.tencent import TencentCareersAdapter, TencentResumableAdapter
        self.resumable_adapters = [*self.resumable_adapters,
            *(TencentResumableAdapter(a) for a in self.adapters if isinstance(a, TencentCareersAdapter))]
        self.adapters = [a for a in self.adapters if not isinstance(a, TencentCareersAdapter)]
        all_adapters = [*self.adapters, *self.resumable_adapters]
        self.descriptors = {a.source_slug: a.descriptor for a in all_adapters}
        if not self.descriptors or len(self.descriptors) != len(all_adapters):
            raise ValueError('daily catalog requires distinct registered sources')
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.pause = pause
        self.ledger = CareerConfig(self.root/'public-history')

    def config_for(self, day: str) -> CareerConfig:
        # Only ISO dates produced by the scheduler may become a directory name.
        if datetime.strptime(day, '%Y-%m-%d').date().isoformat() != day:
            raise ValueError('invalid generation day')
        return CareerConfig(self.root/'runs'/day/'career')

    def step(self) -> dict:
        now = self.clock()
        day = generation_day(now)
        config = self.config_for(day)
        path = config.data_dir.parent/'run.json'
        state = _read(path)
        if not state:
            if config.database_path.exists():
                raise ValueError('refusing an unowned pre-existing daily database')
            state = {'generation': {'id': day, 'started_at': now.isoformat()},
                     'required_sources': sorted(self.descriptors), 'sources': {}, 'state': 'collecting'}
            _save(path, state)
        if state['required_sources'] != sorted(self.descriptors):
            raise ValueError('registered source set changed during a daily generation')
        if state['state'] == 'published':
            return state
        # A crash can occur inside LocalJobSync, before this coordinator returns.
        # Its per-source checkpoint belongs to this day's initially empty DB;
        # recover only completed sources observed after the generation started.
        start = datetime.fromisoformat(state['generation']['started_at'])
        for source in read_status(config)['sources']:
            slug = source.get('slug')
            # Old workers formatted last_success_at to whole seconds while
            # confirmed_at retained the actual completion instant.
            if source.get('status') == 'succeeded' and source.get('confirmed_at'):
                source['last_success_at'] = datetime.fromtimestamp(source['confirmed_at'], timezone.utc).isoformat().replace('+00:00', 'Z')
            stamp = source.get('last_success_at')
            if (slug in self.descriptors and source.get('status') == 'succeeded' and stamp
                    and datetime.fromisoformat(stamp.replace('Z', '+00:00')) >= start):
                state['sources'][slug] = source
        # Source progress is saved inside the crawler before the coordinator
        # returns. Recover a completed main-DB replay even after repeated
        # crashes replaced the smaller pending-source status file.
        if config.database_path.exists():
            with connect(config.database_path) as db:
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='crawl_runs'").fetchone():
                    recovered = db.execute('''SELECT s.slug,r.completed_at FROM crawl_sources s
                        JOIN crawl_runs r ON r.source_id=s.id WHERE r.id=(SELECT r2.id FROM crawl_runs r2
                        WHERE r2.source_id=s.id ORDER BY r2.started_at DESC,r2.rowid DESC LIMIT 1)
                        AND r.status='succeeded' AND r.completed_at IS NOT NULL''').fetchall()
                    for row in recovered:
                        slug, stamp = row['slug'], row['completed_at']
                        completed = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
                        if slug in self.descriptors and start <= completed <= now and state['sources'].get(slug, {}).get('status') != 'succeeded':
                            state['sources'][slug] = {'slug':slug,'name':self.descriptors[slug].source_name,
                                'status':'succeeded','last_success_at':stamp,'confirmed_at':completed.timestamp()}
        _save(path, state)
        pending = {slug for slug in self.descriptors
                   if state['sources'].get(slug, {}).get('status') != 'succeeded'
                   and not (state['sources'].get(slug, {}).get('status') == 'failed'
                            and now.timestamp() - state['sources'][slug].get('checked_at', 0) < 900)}
        if pending:
            # Reuse paging/normalization/completeness; only the storage lifecycle
            # differs. A new day never sees yesterday's jobs or checkpoints.
            sync = LocalJobSync(config,
                adapters=[a for a in self.adapters if a.source_slug in pending],
                resumable_adapters=[a for a in self.resumable_adapters if a.source_slug in pending],
                clock=lambda: self.clock().timestamp(), pause=self.pause)
            result = sync.run_cycle(force=True)
            state['sources'].update({s['slug']: s for s in result['sources']})
        complete = all(state['sources'].get(slug, {}).get('status') == 'succeeded' for slug in self.descriptors)
        state['state'] = 'ready' if complete else 'incomplete'
        _save(path, state)
        _save(self.root/'status.json', state)
        if not complete:
            return state
        generation = {**state['generation'], 'completed_at': self.clock().isoformat()}
        if generation_day(self.clock()) != day:
            state['state'] = 'superseded'
            _save(path, state)
            _save(self.root/'status.json', state)
            return state
        # Validate the whole generation before touching history or manifest.
        start = datetime.fromisoformat(generation['started_at'])
        end = datetime.fromisoformat(generation['completed_at'])
        for slug in self.descriptors:
            for row in _public_rows(config, slug):
                observed = datetime.fromisoformat(row['observed_at'].replace('Z', '+00:00'))
                if not start <= observed <= end:
                    raise ValueError('daily generation contains an observation outside this full scan')
        self._merge_history(config, state)
        manifest = publish_stream(self._records(state, generation), self.output, generation=generation)
        state.update(state='published', generation=generation, revision=manifest['revision'],
                     job_count=manifest['job_count'], published_at=manifest['generated_at'])
        _save(path, state)
        _save(self.root/'status.json', state)
        return state

    def _merge_history(self, config: CareerConfig, state: dict) -> None:
        sync = PublicCatalogSync(self.ledger, descriptors=list(self.descriptors.values()))
        for slug, descriptor in self.descriptors.items():
            rows = _public_rows(config, slug)
            # Daily storage is fresh, but provenance and change dates are not
            # reset. The public-only history ledger is never exported as a DB.
            prior = {}
            if self.ledger.database_path.exists():
                with connect(self.ledger.database_path) as db:
                    prior = {r['external_job_id']: dict(r) for r in db.execute('''SELECT j.external_job_id,
                        j.first_seen_at,j.last_changed_at,j.content_hash,j.status FROM jobs j
                        JOIN crawl_sources s ON s.id=j.crawl_source_id WHERE s.slug=?''', (slug,))}
            from .crawler.normalize import normalize_snapshot
            from .domain.crawler import JobSnapshot
            for row in rows:
                old = prior.get(row['external_job_id'])
                if old:
                    row['first_seen_at'] = old['first_seen_at']
                    normalized = normalize_snapshot(slug, JobSnapshot(**{k: row[k] for k in (
                        'external_job_id','title','description_raw','source_url','observed_at','location_raw','recruitment_type')}))
                    if old['content_hash'] == normalized.content_hash and old['status'] == 'active':
                        row['last_changed_at'] = old['last_changed_at']
            sync._apply(descriptor, rows, state['sources'][slug]['last_success_at'], complete=True)

    def _records(self, state: dict, generation: dict) -> Iterator[dict]:
        cutoff = (datetime.fromisoformat(generation['completed_at']) - timedelta(days=90)).isoformat()
        for slug, descriptor in sorted(self.descriptors.items()):
            rows = _public_rows(self.ledger, slug)
            with connect(self.ledger.database_path) as db:
                events: dict[str, list] = {}
                for e in db.execute('''SELECT j.external_job_id,e.kind,e.observed_at,e.window_start
                    FROM job_catalog_changes e JOIN jobs j ON j.id=e.job_id
                    JOIN crawl_sources s ON s.id=j.crawl_source_id WHERE s.slug=?
                    AND julianday(e.observed_at)>=julianday(?) ORDER BY julianday(e.observed_at),e.rowid''', (slug, cutoff)):
                    events.setdefault(e['external_job_id'], []).append({k: e[k] for k in ('kind','observed_at','window_start')})
            yield {'kind':'source', 'descriptor':asdict(descriptor), 'expected_count':len(rows),
                   'last_success_at':state['sources'][slug]['last_success_at'], 'latest_status':'succeeded'}
            for row in rows:
                yield {'kind':'job', 'job':{**row, 'catalog_events':events.get(row['external_job_id'], [])}}
            yield {'kind':'end_source'}
        yield {'kind':'end_feed'}


def main() -> int:
    parser = argparse.ArgumentParser(description='Daily 04:00 Asia/Shanghai full official catalog rebuild')
    parser.add_argument('--data-dir', type=Path, required=True, help='Dedicated collector directory, never a user/website directory')
    parser.add_argument('--output', type=Path, required=True, help='Dedicated public feed directory')
    parser.add_argument('--once', action='store_true', help='Advance the current daily generation once; 3 means incomplete')
    args = parser.parse_args()
    def shutdown(signum, frame) -> None:
        # Ensure a service stop also cleans up its supervised browser group.
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, shutdown)
    runner = DailyCatalogRunner(args.data_dir, args.output)
    with worker_lock(args.data_dir/'daily-catalog.lock'):
        while True:
            state = {}
            try:
                state = runner.step() if args.once else advance_until_boundary(runner.root, runner.output)
                print(json.dumps({k:state.get(k) for k in ('state','generation','revision','job_count','error_type')}, ensure_ascii=False), flush=True)
                complete = state['state'] == 'published'
            except Exception as exc:
                # Do not log response bodies, URLs, credentials or candidate data.
                print(json.dumps({'state':'failed','error_type':type(exc).__name__}), flush=True)
                complete = False
            if args.once:
                return 0 if complete else 3
            if state.get('state') == 'superseded':
                continue
            pending = any(s.get('status') == 'pending' for s in state.get('sources', {}).values()) if not complete else False
            delay = seconds_to_next_run(runner.clock()) if complete else min(60 if pending else 900, seconds_to_next_run(runner.clock()))
            time.sleep(delay)


if __name__ == '__main__':
    raise SystemExit(main())
