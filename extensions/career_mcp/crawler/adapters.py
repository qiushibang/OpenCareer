"""Adapter boundary for crawler snapshot retrieval."""

from __future__ import annotations

from typing import Iterable, Protocol

from ..domain.crawler import JobSnapshot, SourceDescriptor


class JobAdapter(Protocol):
    descriptor: SourceDescriptor
    source_slug: str

    def fetch_jobs(self) -> list[JobSnapshot]:
        """Return source snapshots without persistence or Agent interaction."""


class FakeAdapter:
    """Fixture-only adapter used by offline crawler tests."""

    def __init__(
        self,
        source_slug: str,
        snapshots: list[JobSnapshot],
        *,
        descriptor: SourceDescriptor | None = None,
    ) -> None:
        self.source_slug = source_slug
        self.descriptor = descriptor or SourceDescriptor(
            source_slug=source_slug,
            source_name=source_slug,
            company_slug=source_slug,
            company_name=source_slug,
            scope_key=f"source:{source_slug}",
            adapter_type="fixture",
            base_url=None,
        )
        if self.descriptor.source_slug != source_slug:
            raise ValueError("descriptor source_slug must match source_slug")
        self._snapshots = snapshots

    def fetch_jobs(self) -> list[JobSnapshot]:
        return self._snapshots


class AdapterRegistry:
    """Explicitly registered adapters available to the crawler service."""

    def __init__(self, adapters: Iterable[JobAdapter] = ()) -> None:
        self._adapters = {
            adapter.descriptor.source_slug: adapter for adapter in adapters
        }

    def get(self, source_slug: str) -> JobAdapter:
        try:
            return self._adapters[source_slug]
        except KeyError as exc:
            raise LookupError("source not found") from exc

    def source_slugs(self) -> list[str]:
        return sorted(self._adapters)


def default_adapters() -> list[JobAdapter]:
    """Return production adapters that passed their latest public smoke check."""
    from .alibaba import ALIBABA_TONGYI_SCOPE, AlibabaCareersAdapter
    from .bytedance import (
        BYTEDANCE_FRONTIER_PROJECT,
        ByteDanceCampusProjectAdapter,
        ByteDanceSeedCampusAdapter,
    )
    from .deepseek import DeepSeekStaticBundleAdapter
    from .didi import DidiSocialAdapter
    from .kuaishou import KuaishouBrowserAdapter
    from .meituan import MeituanSocialAdapter
    from .moonshot import MoonshotSocialAdapter
    from .tencent import TENCENT_PRODUCTION_SCOPES, TencentCareersAdapter
    from .xiaomi import XiaomiPublicApiAdapter
    from .xiaohongshu import XiaohongshuSocialAdapter
    from .zhipu import ZHIPU_PRODUCTION_SCOPES, ZhipuMokaAdapter

    # Baidu remains disabled after its live SSR contract failed validation.
    # MiniMax and Zhipu remain disabled because their listing requests require
    # signatures or session state.
    return [
        AlibabaCareersAdapter(ALIBABA_TONGYI_SCOPE),
        ByteDanceCampusProjectAdapter(BYTEDANCE_FRONTIER_PROJECT),
        ByteDanceSeedCampusAdapter(),
        DeepSeekStaticBundleAdapter(),
        DidiSocialAdapter(),
        KuaishouBrowserAdapter(),
        MeituanSocialAdapter(),
        MoonshotSocialAdapter(),
        *(TencentCareersAdapter(scope) for scope in TENCENT_PRODUCTION_SCOPES),
        XiaomiPublicApiAdapter(),
        XiaohongshuSocialAdapter(),
        *(ZhipuMokaAdapter(scope) for scope in ZHIPU_PRODUCTION_SCOPES),
    ]


def default_resumable_adapters() -> list[object]:
    """Return sources that persist page checkpoints before Catalog commit."""
    from .bytedance import (
        BYTEDANCE_MAINLAND_CAMPUS,
        BYTEDANCE_MAINLAND_SOCIAL,
        ByteDanceMainlandAdapter,
    )

    return [
        ByteDanceMainlandAdapter(BYTEDANCE_MAINLAND_SOCIAL),
        ByteDanceMainlandAdapter(BYTEDANCE_MAINLAND_CAMPUS),
    ]
