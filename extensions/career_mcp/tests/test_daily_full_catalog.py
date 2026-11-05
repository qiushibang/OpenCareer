"""Two real generations, fresh clients, private state and complete-feed failure gates."""
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json

import pytest

from extensions.career_mcp.config import CareerConfig
from extensions.career_mcp.database.migrations import connect
from extensions.career_mcp.domain.crawler import JobSnapshot
from extensions.career_mcp.public_catalog_format import publish_stream
from extensions.career_mcp.services.job_catalog import JobCatalog
from extensions.career_mcp.services.job_tracking import JobTrackingService
from extensions.career_mcp.services.jobs import JobService
from extensions.career_mcp.tests.test_public_catalog import DESCRIPTOR, job, syncer


def full_publish(path, rows, stamp):
    return publish_stream(iter([
        {'kind': 'source', 'descriptor': asdict(DESCRIPTOR), 'expected_count': len(rows),
         'last_success_at': stamp, 'latest_status': 'succeeded'},
        *({'kind': 'job', 'job': {**row, 'observed_at': stamp, 'catalog_events': row.get('catalog_events', [])}} for row in rows),
        {'kind': 'end_source'}, {'kind': 'end_feed'}]), path,
        generation={'id': stamp[:10], 'started_at': stamp, 'completed_at': stamp})


def test_complete_feed_removes_missing_retains_private_state_and_upstream_newness(tmp_path):
    feed, config = tmp_path/'feed', CareerConfig(tmp_path/'client')
    day1, day2 = '2026-11-05T01:00:00Z', '2026-11-06T01:00:00Z'
    full_publish(feed, [job('gone', observed_at=day1), job('stay', observed_at=day1)], day1)
    sync = syncer(config, feed)
    assert sync.run()['completed'] == 1
    with connect(config.database_path) as db:
        old = {r['external_job_id']:dict(r) for r in db.execute('SELECT * FROM jobs')}
    tracking = JobTrackingService(config)
    tracking.update(old['gone']['id'], {'expected_version':0,'is_favorite':True,'note':'保留申请备注'})
    event = {'kind':'new', 'observed_at':day2, 'window_start':day1}
    full_publish(feed, [job('stay', observed_at=day2), job('new', first_seen_at=day2,
                 observed_at=day2, last_changed_at=day2, catalog_events=[event])], day2)
    assert sync.run()['completed'] == 1
    active = JobService(config).search_jobs(statuses=['active'])['jobs']
    with connect(config.database_path) as db:
        current = {r['external_job_id']:r['id'] for r in db.execute("SELECT * FROM jobs WHERE status='active'")}
    assert set(current) == {'stay','new'}
    assert current['stay'] == old['stay']['id']
    assert tracking.get(old['gone']['id'])['note'] == '保留申请备注'
    fresh = CareerConfig(tmp_path/'fresh')
    assert syncer(fresh, feed).run()['completed'] == 1
    catalog = JobCatalog(fresh)
    condition={'all':[{'field':'new_at','op':'between','values':[day2,'2026-11-07T01:00:00Z']},
                      {'field':'locations','op':'in','values':['北京']}]}
    result=catalog.search(condition)
    assert result['total'] == 1
    assert result['jobs'][0]['new_at'] == day2
    assert syncer(fresh, feed).run()['unchanged'] == 1
    with connect(fresh.database_path) as db:
        assert db.execute("SELECT count(*) FROM job_catalog_changes WHERE kind='new'").fetchone()[0] == 1


def test_empty_complete_source_closes_current_jobs(tmp_path):
    feed, config=tmp_path/'feed',CareerConfig(tmp_path/'client')
    full_publish(feed,[job()], '2026-11-05T01:00:00Z');sync=syncer(config,feed);sync.run()
    full_publish(feed,[], '2026-11-06T01:00:00Z')
    assert sync.run()['completed']==1
    assert JobService(config).search_jobs(statuses=['active'])['total']==0


def test_invalid_or_future_public_events_do_not_publish(tmp_path):
    feed=tmp_path/'feed';full_publish(feed,[job()], '2026-11-05T01:00:00Z');before=(feed/'manifest.json').read_bytes()
    with pytest.raises(ValueError):
        full_publish(feed,[job(catalog_events=[{'kind':'delete','observed_at':'2026-11-05T01:00:00Z','window_start':None}])], '2026-11-05T01:00:00Z')
    assert (feed/'manifest.json').read_bytes()==before


class LiveFixtureAdapter:
    source_slug=DESCRIPTOR.source_slug
    descriptor=DESCRIPTOR
    def __init__(self, clock):
        self.clock=clock;self.calls=[];self.items=[('one','产品经理')];self.fail=False
    def fetch_jobs(self):
        self.calls.append(self.clock().isoformat())
        if self.fail:
            raise RuntimeError('official source unavailable')
        stamp=self.clock().isoformat()
        return [JobSnapshot(key,title,'职责：产品设计',f'https://careers.example.com/job/{key}',stamp,'北京','experienced') for key,title in self.items]


def test_daily_runner_crawls_fresh_each_day_and_keeps_history_separate(tmp_path):
    from extensions.career_mcp.daily_catalog import DailyCatalogRunner
    now=[datetime(2026,11,5,0,tzinfo=timezone.utc)]
    clock=lambda:now[0]
    adapter=LiveFixtureAdapter(clock)
    runner=DailyCatalogRunner(tmp_path/'worker',tmp_path/'feed',adapters=[adapter],resumable_adapters=[],clock=clock,pause=0)
    first=runner.step()
    assert first['state']=='published'
    first_db=runner.config_for('2026-11-05').database_path
    assert runner.step()['state']=='published' and len(adapter.calls)==1
    now[0]=datetime(2026,11,6,0,tzinfo=timezone.utc)
    adapter.items=[('two','策略产品经理')]
    second=runner.step()
    assert second['state']=='published' and len(adapter.calls)==2
    with connect(runner.config_for('2026-11-06').database_path) as db:
        assert [r[0] for r in db.execute('SELECT external_job_id FROM jobs')]==['two']
    with connect(first_db) as db:
        assert [r[0] for r in db.execute('SELECT external_job_id FROM jobs')]==['one']
    # A new user sees the server's comparison even without yesterday's local DB.
    cfg=CareerConfig(tmp_path/'client');assert syncer(cfg,tmp_path/'feed').run()['completed']==1
    assert JobCatalog(cfg).search({'field':'new_at','op':'between','values':['2026-11-06T00:00:00Z','2026-11-07T00:00:00Z']})['total']==1
    now[0]=datetime(2026,11,7,0,tzinfo=timezone.utc);adapter.items=[('one','产品经理')]
    assert runner.step()['state']=='published'
    syncer(cfg,tmp_path/'feed').run()
    with connect(cfg.database_path) as db:
        assert db.execute("SELECT count(*) FROM job_catalog_changes WHERE kind='reopened'").fetchone()[0]==1


def test_daily_failure_cannot_publish_partial_or_reuse_yesterday(tmp_path):
    from extensions.career_mcp.daily_catalog import DailyCatalogRunner
    now=[datetime(2026,11,5,0,tzinfo=timezone.utc)];clock=lambda:now[0]
    adapter=LiveFixtureAdapter(clock)
    runner=DailyCatalogRunner(tmp_path/'worker',tmp_path/'feed',adapters=[adapter],resumable_adapters=[],clock=clock,pause=0)
    assert runner.step()['state']=='published';before=(tmp_path/'feed/manifest.json').read_bytes()
    now[0]=datetime(2026,11,6,0,tzinfo=timezone.utc);adapter.fail=True
    assert runner.step()['state']=='incomplete'
    assert (tmp_path/'feed/manifest.json').read_bytes()==before
    assert runner.config_for('2026-11-06').database_path!=runner.config_for('2026-11-05').database_path
    # Retry same day, restart new runner, then supersede unfinished old day.
    restarted=DailyCatalogRunner(tmp_path/'worker',tmp_path/'feed',adapters=[adapter],resumable_adapters=[],clock=clock,pause=0)
    assert restarted.step()['state']=='incomplete'
    now[0]=datetime(2026,11,7,0,tzinfo=timezone.utc);adapter.fail=False
    assert restarted.step()['state']=='published'
    assert (tmp_path/'worker/runs/2026-11-06/run.json').is_file()


def test_schedule_is_exactly_four_shanghai_not_host_timezone():
    from extensions.career_mcp.daily_catalog import generation_day, seconds_to_next_run
    assert generation_day(datetime(2026,11,5,19,59,tzinfo=timezone.utc))=='2026-11-05'
    assert generation_day(datetime(2026,11,5,20,0,tzinfo=timezone.utc))=='2026-11-06'
    assert seconds_to_next_run(datetime(2026,11,5,19,59,tzinfo=timezone.utc))==60
    assert seconds_to_next_run(datetime(2026,11,5,20,0,tzinfo=timezone.utc))==86400


def test_actual_source_completion_can_follow_last_job_observation(tmp_path):
    from extensions.career_mcp.daily_catalog import DailyCatalogRunner
    current=[datetime(2026,11,5,0,tzinfo=timezone.utc)]
    clock=lambda:current[0]
    adapter=LiveFixtureAdapter(clock)
    original=adapter.fetch_jobs
    def fetch():
        rows=original();current[0]+=timedelta(seconds=2);return rows
    adapter.fetch_jobs=fetch
    runner=DailyCatalogRunner(tmp_path/'worker',tmp_path/'feed',adapters=[adapter],resumable_adapters=[],clock=clock,pause=0)
    assert runner.step()['state']=='published'
    cfg=CareerConfig(tmp_path/'client');assert syncer(cfg,tmp_path/'feed').run()['completed']==1


def test_all_registered_sources_must_complete_and_restart_skips_only_this_day_successes(tmp_path):
    from dataclasses import replace
    from extensions.career_mcp.daily_catalog import DailyCatalogRunner
    now=[datetime(2026,11,5,0,tzinfo=timezone.utc)];clock=lambda:now[0]
    a,b=LiveFixtureAdapter(clock),LiveFixtureAdapter(clock)
    b.source_slug='other-official';b.descriptor=replace(DESCRIPTOR,source_slug=b.source_slug,scope_key='other');b.items=[('other','产品经理')];b.fail=True
    runner=DailyCatalogRunner(tmp_path/'worker',tmp_path/'feed',adapters=[a,b],resumable_adapters=[],clock=clock,pause=0)
    assert runner.step()['state']=='incomplete'
    assert not (tmp_path/'feed/manifest.json').exists()
    restarted=DailyCatalogRunner(tmp_path/'worker',tmp_path/'feed',adapters=[a,b],resumable_adapters=[],clock=clock,pause=0)
    b.fail=False
    now[0]+=timedelta(minutes=15)
    assert restarted.step()['state']=='published'
    assert len(a.calls)==1 and len(b.calls)==2
    now[0]=datetime(2026,11,6,0,tzinfo=timezone.utc)
    assert restarted.step()['state']=='published'
    assert len(a.calls)==2 and len(b.calls)==3


def test_stale_or_future_row_cannot_replace_completed_feed(tmp_path):
    from extensions.career_mcp.daily_catalog import DailyCatalogRunner
    current=[datetime(2026,11,5,0,tzinfo=timezone.utc)];clock=lambda:current[0]
    adapter=LiveFixtureAdapter(clock)
    runner=DailyCatalogRunner(tmp_path/'worker',tmp_path/'feed',adapters=[adapter],resumable_adapters=[],clock=clock,pause=0)
    assert runner.step()['state']=='published';before=(tmp_path/'feed/manifest.json').read_bytes()
    current[0]=datetime(2026,11,6,0,tzinfo=timezone.utc)
    adapter.fetch_jobs=lambda:[JobSnapshot('old','产品经理','职责', 'https://careers.example.com/old','2026-08-01T00:00:00Z','北京')]
    with pytest.raises(ValueError,match='outside this full scan'):
        runner.step()
    assert (tmp_path/'feed/manifest.json').read_bytes()==before


def test_restart_inside_source_loop_recovers_completed_same_day_sources(tmp_path):
    from dataclasses import replace
    from extensions.career_mcp.daily_catalog import DailyCatalogRunner
    clock=lambda:datetime(2026,11,5,0,tzinfo=timezone.utc)
    a,b=LiveFixtureAdapter(clock),LiveFixtureAdapter(clock)
    b.source_slug='z-other-official';b.descriptor=replace(DESCRIPTOR,source_slug=b.source_slug,scope_key='other');b.items=[('other','产品经理')]
    fetch=b.fetch_jobs
    b.fetch_jobs=lambda:(_ for _ in ()).throw(KeyboardInterrupt())
    runner=DailyCatalogRunner(tmp_path/'worker',tmp_path/'feed',adapters=[a,b],resumable_adapters=[],clock=clock,pause=0)
    with pytest.raises(KeyboardInterrupt):runner.step()
    assert len(a.calls)==1 and not (tmp_path/'feed/manifest.json').exists()
    b.fetch_jobs=fetch
    restarted=DailyCatalogRunner(tmp_path/'worker',tmp_path/'feed',adapters=[a,b],resumable_adapters=[],clock=clock,pause=0)
    assert restarted.step()['state']=='published'
    assert len(a.calls)==1


def test_new_day_arriving_inside_scan_cannot_publish_previous_generation(tmp_path):
    from datetime import timedelta
    from extensions.career_mcp.daily_catalog import DailyCatalogRunner
    now=[datetime(2026,11,5,19,59,tzinfo=timezone.utc)];clock=lambda:now[0]
    a=LiveFixtureAdapter(clock);fetch=a.fetch_jobs
    def crosses_four():
        data=fetch();now[0]+=timedelta(minutes=2);return data
    a.fetch_jobs=crosses_four
    runner=DailyCatalogRunner(tmp_path/'worker',tmp_path/'feed',adapters=[a],resumable_adapters=[],clock=clock,pause=0)
    assert runner.step()['state']=='superseded'
    assert not (tmp_path/'feed/manifest.json').exists()


def test_full_multi_source_download_failure_never_exposes_partial_generation(tmp_path):
    from dataclasses import replace
    from extensions.career_mcp.services.public_catalog import PublicCatalogSync
    feed=tmp_path/'feed';cfg=CareerConfig(tmp_path/'client')
    other=replace(DESCRIPTOR,source_slug='other-official',scope_key='other')
    def publish_pair(stamp,title):
        records=[]
        for desc in (DESCRIPTOR,other):
            records += [{'kind':'source','descriptor':asdict(desc),'expected_count':1,'last_success_at':stamp,'latest_status':'succeeded'},
                        {'kind':'job','job':job(desc.source_slug,title=title,observed_at=stamp,catalog_events=[])}, {'kind':'end_source'}]
        return publish_stream(iter([*records,{'kind':'end_feed'}]),feed,
            generation={'id':stamp[:10],'started_at':stamp,'completed_at':stamp})
    def fetch(url,limit):return (feed/url.removeprefix('https://feed.example.com/')).read_bytes()
    sync=PublicCatalogSync(cfg,base_url='https://feed.example.com/',fetch=fetch,descriptors=[DESCRIPTOR,other])
    publish_pair('2026-11-05T00:00:00Z','旧版产品岗');assert sync.run()['completed']==2
    m=publish_pair('2026-11-06T00:00:00Z','新版产品岗');(feed/m['sources'][1]['path']).write_bytes(b'corrupt')
    assert sync.run()['failed']>0
    assert {r['title'] for r in JobService(cfg).search_jobs()['jobs']}=={'旧版产品岗'}


def test_full_generation_database_failure_rolls_back_earlier_sources(tmp_path, monkeypatch):
    feed,cfg=tmp_path/'feed',CareerConfig(tmp_path/'client')
    full_publish(feed,[job(title='旧产品岗')],'2026-11-05T00:00:00Z');sync=syncer(cfg,feed);sync.run()
    full_publish(feed,[job(title='新产品岗')],'2026-11-06T00:00:00Z')
    real=sync._apply
    def fail_after_apply(*args,**kwargs):
        real(*args,**kwargs)
        raise RuntimeError('simulated storage failure')
    monkeypatch.setattr(sync,'_apply',fail_after_apply)
    assert sync.run()['failed']==1
    assert JobService(cfg).search_jobs()['jobs'][0]['title']=='旧产品岗'
    assert not list(cfg.data_dir.glob('.catalog-download-*'))


@pytest.mark.asyncio
async def test_daily_feed_still_serves_company_city_direction_and_new_date_over_mcp(tmp_path):
    import os,sys
    from dataclasses import replace
    from mcp import ClientSession,StdioServerParameters
    from mcp.client.stdio import stdio_client
    from extensions.career_mcp.daily_catalog import DailyCatalogRunner
    now=[datetime(2026,11,5,0,tzinfo=timezone.utc)];clock=lambda:now[0]
    adapter=LiveFixtureAdapter(clock)
    adapter.descriptor=replace(DESCRIPTOR,company_slug='bytedance',company_name='字节跳动')
    runner=DailyCatalogRunner(tmp_path/'worker',tmp_path/'feed',adapters=[adapter],resumable_adapters=[],clock=clock,pause=0)
    runner.step();now[0]=datetime(2026,11,6,0,tzinfo=timezone.utc)
    adapter.items += [('new','策略产品实习生')];assert runner.step()['state']=='published'
    cfg=CareerConfig(tmp_path/'client')
    from extensions.career_mcp.services.public_catalog import PublicCatalogSync
    sync=PublicCatalogSync(cfg,base_url='https://feed.example.com/',descriptors=[adapter.descriptor],
       fetch=lambda url,limit:(tmp_path/'feed'/url.removeprefix('https://feed.example.com/')).read_bytes())
    assert sync.run()['completed']==1
    params=StdioServerParameters(command=sys.executable,args=['-m','extensions.career_mcp.jobs_mcp','--data-dir',str(cfg.data_dir)],
                                env={**os.environ,'DATABASE_URL':'postgresql://not-used.invalid/unused'})
    async with stdio_client(params) as (read,write):
        async with ClientSession(read,write) as client:
            await client.initialize()
            schema=await client.call_tool('get_job_catalog_schema',{})
            assert 'new_at' in str(schema.content)
            response=await client.call_tool('search_job_catalog',{'condition':{'all':[
                {'field':'company','op':'in','values':['字节跳动']},
                {'field':'locations','op':'in','values':['北京']},
                {'field':'job_family','op':'in','values':['product']},
                {'field':'new_at','op':'between','values':['2026-11-06T00:00:00Z','2026-11-07T00:00:00Z']} ]}})
            assert not response.isError
            envelope=json.loads(response.content[0].text)
            assert envelope['ok'], envelope
            result=envelope['data']
            assert result['total']==1 and result['jobs'][0]['title']=='策略产品实习生'


def test_subsecond_official_observation_is_not_later_than_source_completion(tmp_path):
    from extensions.career_mcp.daily_catalog import DailyCatalogRunner
    now=[datetime(2026,11,5,0,0,0,800000,tzinfo=timezone.utc)];clock=lambda:now[0]
    adapter=LiveFixtureAdapter(clock)
    runner=DailyCatalogRunner(tmp_path/'worker',tmp_path/'feed',adapters=[adapter],resumable_adapters=[],clock=clock,pause=0)
    assert runner.step()['state']=='published'
    now[0]+=timedelta(days=1);adapter.items += [('new','策略产品经理')]
    assert runner.step()['state']=='published'
    cfg=CareerConfig(tmp_path/'client');assert syncer(cfg,tmp_path/'feed').run()['completed']==1
    with connect(cfg.database_path) as db:
        assert db.execute("SELECT count(*) FROM job_catalog_changes WHERE kind='new'").fetchone()[0]==1


def test_unchanged_job_second_pass_keeps_actual_new_official_observation(tmp_path):
    from dataclasses import replace
    from extensions.career_mcp.crawler.adapters import FakeAdapter
    from extensions.career_mcp.domain.crawler import ResumableListingPage
    from extensions.career_mcp.services.resumable_crawler import ResumableCrawlerService
    class Adapter(FakeAdapter):
        def __init__(self):
            super().__init__(DESCRIPTOR.source_slug,[],descriptor=DESCRIPTOR)
            self.stamp='2026-08-01T00:00:00Z'
        def initial_shards(self):return [{'shard_key':'all','filters':{}}]
        def fetch_page(self,filters,offset):
            return ResumableListingPage([JobSnapshot('1','产品经理','职责', 'https://careers.example.com/1',self.stamp,'北京')],1,1,True,'1')
    adapter=Adapter();cfg=CareerConfig(tmp_path/'career');service=ResumableCrawlerService(cfg)
    assert service.run_batch(adapter)['has_more']
    adapter.stamp='2026-11-05T01:00:00Z'
    assert service.run_batch(adapter)['status']=='committed'
    with connect(cfg.database_path) as db:
        row=db.execute('SELECT last_seen_at FROM jobs').fetchone()
        assert row[0]==adapter.stamp


def test_legacy_sqlite_checkpoint_time_recovers_from_authoritative_column(tmp_path):
    from extensions.career_mcp.database.repository import JobRepository
    cfg=CareerConfig(tmp_path/'career')
    with connect(cfg.database_path) as db:
        repo=JobRepository(db);source=repo.ensure_crawl_source(DESCRIPTOR)
        cycle=repo.get_or_create_crawl_cycle(str(source['crawl_source_id']),[{'shard_key':'all','filters':{}}])
        repo.stage_cycle_job(cycle['id'],external_job_id='1',content_hash='same',pass_number=1,
            snapshot={'observed_at':'2026-08-01T00:00:00Z'},observed_at='2026-08-01T00:00:00Z')
        db.execute('UPDATE crawl_cycle_jobs SET observed_at=?,last_pass=3',('2026-11-05T01:00:00Z',))
        assert repo.list_cycle_jobs(cycle['id'])[0]['snapshot']['observed_at']=='2026-11-05T01:00:00Z'


def _slow_scheduled_fixture(root,output,sender):
    import os,time
    if os.name!='nt':os.setsid()
    Path=__import__('pathlib').Path
    Path(root).mkdir(parents=True,exist_ok=True)
    (Path(root)/'fixture-started').write_text(str(os.getpid()))
    time.sleep(30)
    sender.send({'state':'published'})


def test_slow_source_cannot_delay_next_four_oclock_fresh_generation(tmp_path):
    import time
    from extensions.career_mcp.daily_catalog import advance_until_boundary
    started=time.monotonic()
    ready_at=[None]
    marker=tmp_path/'worker/fixture-started'
    def clock():
        if marker.exists() and ready_at[0] is None:
            ready_at[0]=time.monotonic()
        elapsed=0 if ready_at[0] is None else time.monotonic()-ready_at[0]
        return datetime(2026,11,5,19,59,59,tzinfo=timezone.utc)+timedelta(seconds=elapsed)
    state=advance_until_boundary(tmp_path/'worker',tmp_path/'feed',clock=clock,worker=_slow_scheduled_fixture)
    assert marker.exists()  # Exercise a running source, not just process startup.
    assert state['state']=='superseded'
    assert time.monotonic()-started<8  # The source itself sleeps for 30 seconds.
    assert not (tmp_path/'feed/manifest.json').exists()


def test_failed_sources_keep_backoff_while_other_work_can_continue(tmp_path):
    from extensions.career_mcp.daily_catalog import DailyCatalogRunner
    now=[datetime(2026,11,5,0,tzinfo=timezone.utc)];clock=lambda:now[0]
    adapter=LiveFixtureAdapter(clock);adapter.fail=True
    runner=DailyCatalogRunner(tmp_path/'worker',tmp_path/'feed',adapters=[adapter],resumable_adapters=[],clock=clock,pause=0)
    assert runner.step()['state']=='incomplete' and len(adapter.calls)==1
    adapter.fail=False;now[0]+=timedelta(minutes=1)
    assert runner.step()['state']=='incomplete' and len(adapter.calls)==1
    now[0]+=timedelta(minutes=14)
    assert runner.step()['state']=='published' and len(adapter.calls)==2


def test_new_endpoint_preserves_old_clients_and_rechecks_after_legacy_fallback(tmp_path):
    from extensions.career_mcp.services.public_catalog import PublicCatalogSync, DEFAULT_FEED_URL, LEGACY_FEED_URL
    from extensions.career_mcp.tests.test_public_catalog import publish
    old,new=tmp_path/'v1',tmp_path/'v2';publish(old,[job()]);calls=[];available=[False]
    def fetch(url,limit):
        calls.append(url)
        if url.startswith(DEFAULT_FEED_URL):
            if not available[0]:return b'<!doctype html><title>OpenCareer</title>'
            return (new/url.removeprefix(DEFAULT_FEED_URL)).read_bytes()
        assert url.startswith(LEGACY_FEED_URL)
        return (old/url.removeprefix(LEGACY_FEED_URL)).read_bytes()
    cfg=CareerConfig(tmp_path/'client');sync=PublicCatalogSync(cfg,fetch=fetch,descriptors=[DESCRIPTOR])
    assert sync.run()['legacy_fallback'] is True
    full_publish(new,[job(),job('new')],'2026-11-05T00:00:00Z');available[0]=True
    result=sync.run()
    assert result['feed_schema']==2 and result['legacy_fallback'] is False
    assert JobService(cfg).search_jobs(statuses=['active'])['total']==2
    # Publishing v2 did not modify the existing v1 endpoint.
    assert json.loads((old/'manifest.json').read_text())['schema_version']==1


def test_corrupt_new_endpoint_does_not_silently_fall_back_to_old_data(tmp_path):
    from extensions.career_mcp.services.public_catalog import PublicCatalogSync
    def corrupt(url,limit):return b'broken-json'
    with pytest.raises(ValueError):
        PublicCatalogSync(CareerConfig(tmp_path/'client'),fetch=corrupt).run()


def test_daily_zhipu_scan_uses_complete_page_envelope_instead_of_old_count_budget(tmp_path):
    from extensions.career_mcp.crawler.zhipu import ZhipuMokaAdapter,ZHIPU_CAMPUS_SCOPE
    from extensions.career_mcp.daily_catalog import DailyCatalogRunner
    stamp='2026-11-05T00:00:00Z'
    jobs=[{'href':f'#/job/00000000-0000-4000-8000-{i:012d}','title':f'算法工程师{i}',
           'metadata':['全职','其他','北京市'],'published_at':'发布于 2026-11-05','description':'职责：模型训练'} for i in range(31)]
    pages=[{'page':1,'page_count':2,'page_size':30,'jobs':jobs[:30]},
           {'page':2,'page_count':2,'page_size':30,'jobs':jobs[30:]}]
    adapter=ZhipuMokaAdapter(ZHIPU_CAMPUS_SCOPE,fetch_dataset=lambda scope:pages,clock=lambda:stamp)
    with pytest.raises(ValueError,match='safety limit'):adapter.fetch_jobs()
    runner=DailyCatalogRunner(tmp_path/'worker',tmp_path/'feed',adapters=[adapter],resumable_adapters=[],
                              clock=lambda:datetime.fromisoformat(stamp.replace('Z','+00:00')),pause=0)
    state=runner.step()
    assert state['state']=='published' and state['job_count']==31
