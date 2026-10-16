import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3]))

from extensions.career_mcp.crawler.adapters import FakeAdapter
from extensions.career_mcp.crawler.normalize import normalize_snapshot
from extensions.career_mcp.domain.crawler import JobSnapshot, SourceDescriptor


def _snapshot() -> JobSnapshot:
    return JobSnapshot(
        external_job_id="42",
        title="Agent Engineer",
        description_raw="Build tools",
        source_url="https://jobs.example/42",
        observed_at="2026-08-05T00:00:00Z",
        location_raw="北京",
        recruitment_type="internship",
    )


def test_normalize_snapshot_has_stable_identity_and_content_hash():
    snapshot = _snapshot()

    job = normalize_snapshot("fake-source", snapshot)

    assert job.identity == "fake-source:42"
    assert job.content_hash == normalize_snapshot("fake-source", snapshot).content_hash
    assert job.locations == ["北京"]


def test_normalize_snapshot_splits_composite_locations():
    snapshot = _snapshot()
    snapshot = JobSnapshot(
        **{
            **snapshot.__dict__,
            "location_raw": "北京市、深圳市、广州市",
        }
    )

    job = normalize_snapshot("fake-source", snapshot)

    assert job.locations == ["北京", "深圳", "广州"]


def test_fake_adapter_returns_its_injected_snapshots():
    snapshots = [_snapshot()]

    adapter = FakeAdapter("fake-source", snapshots)

    assert adapter.fetch_jobs() == snapshots


def test_source_descriptor_separates_company_from_crawl_scope():
    descriptor = SourceDescriptor(
        source_slug="bytedance-campus-seed-2027",
        source_name="字节跳动 2027 Seed 大模型人才校招",
        company_slug="bytedance",
        company_name="字节跳动",
        scope_key="project:7621018151002507573",
        adapter_type="playwright-json",
        base_url="https://jobs.bytedance.com/campus/position",
    )

    assert descriptor.company_slug == "bytedance"
    assert descriptor.source_slug == "bytedance-campus-seed-2027"


def test_fake_adapter_accepts_explicit_source_descriptor():
    descriptor = SourceDescriptor(
        source_slug="bytedance-campus-seed-2027",
        source_name="字节跳动 2027 Seed 大模型人才校招",
        company_slug="bytedance",
        company_name="字节跳动",
        scope_key="project:7621018151002507573",
        adapter_type="fixture",
        base_url="https://jobs.bytedance.com/campus/position",
    )

    adapter = FakeAdapter(
        descriptor.source_slug,
        [_snapshot()],
        descriptor=descriptor,
    )

    assert adapter.descriptor == descriptor
    assert adapter.source_slug == descriptor.source_slug
