"""Portable, evidence-bearing job queries. Never executes model supplied SQL."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from collections import Counter
import hashlib
import json
import re
import sqlite3
import uuid
from typing import Callable
from zoneinfo import ZoneInfo

from ..config import CareerConfig
from .jobs import JobService

VERSION = "2026-10-29.3"
TZ = ZoneInfo("Asia/Shanghai")
FAMILIES = {"product": ["产品经理", "产品岗", "产品策划", "产品专家", "产品负责人", "Product Manager"],
            "algorithm": ["算法", "机器学习", "深度学习", "研究科学家"],
            "engineering": ["开发工程师", "研发工程师", "软件工程师", "前端", "后端"],
            "design": ["设计师", "交互设计"], "operations": ["运营"], "other": []}
DIRECTIONS = {
    "strategy_product": ("product", ["策略"]), "evaluation_product": ("product", ["评测", "评估"]),
    "commercial_product": ("product", ["商业化", "广告", "变现"]), "growth_product": ("product", ["增长"]),
    "platform_product": ("product", ["平台", "中台"]), "ai_product": ("product", ["AI", "大模型", "智能体"]),
    "recommendation": ("algorithm", ["推荐"]), "search": ("algorithm", ["搜索", "检索"]),
    "advertising": ("algorithm", ["广告"]), "nlp": ("algorithm", ["自然语言", "NLP"]),
    "multimodal": ("algorithm", ["多模态", "视觉"]), "llm_training": ("algorithm", ["大模型训练", "预训练", "后训练"]),
    "llm_inference": ("algorithm", ["推理", "模型部署"]),
}
LABELS = {"product": "产品", "algorithm": "算法", "engineering": "研发", "design": "设计", "operations": "运营", "other": "其他",
          "strategy_product": "策略产品", "evaluation_product": "评测产品", "commercial_product": "商业化产品",
          "growth_product": "增长产品", "platform_product": "平台产品", "ai_product": "AI 产品", "recommendation": "推荐算法",
          "search": "搜索算法", "advertising": "广告算法", "nlp": "自然语言算法", "multimodal": "多模态算法",
          "llm_training": "大模型训练", "llm_inference": "大模型推理"}
ALIASES = {"字节": "bytedance", "字节跳动": "bytedance", "ByteDance": "bytedance", "小米": "xiaomi", "美团": "meituan", "腾讯": "tencent", "阿里": "alibaba", "阿里巴巴": "alibaba"}
FIELDS = {"company", "locations", "recruitment_type", "status", "job_family", "directions", "business_lines", "business_line_candidates", "official_department", "official_category", "text", "title", "first_seen_at", "published_at", "last_seen_at"}
DATES = {"first_seen_at", "published_at", "last_seen_at"}


def instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=TZ) if parsed.tzinfo is None else parsed


def classify(job: dict) -> dict:
    title, body = str(job.get("title") or ""), str(job.get("description_raw") or "")
    def has_term(term: str, text: str) -> bool:
        if re.fullmatch(r"[A-Za-z ]+", term):
            return re.search(r"(?<![A-Za-z])" + re.escape(term) + r"(?![A-Za-z])", text, re.IGNORECASE) is not None
        return term.casefold() in text.casefold()
    def explicit(names: str) -> str | None:
        found = re.search(rf"(?m)^\s*(?:{names})[：:]\s*([^\n]{{1,200}})", body)
        return found.group(1).strip() if found else None
    department = explicit("部门|所属部门")
    category = explicit("职类|岗位类别|职位类别")
    business = explicit("业务线|所属业务线|所属业务|事业群|业务群")
    published = explicit("发布日期|发布时间")
    if published:
        date = re.search(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", published)
        try:
            published = instant(date.group().replace("/", "-")).isoformat() if date else None
        except ValueError:
            published = None
    evidence = []
    family = "other"
    for name, terms in FAMILIES.items():
        hit = next((term for term in terms if has_term(term, title + " " + (category or ""))), None)
        if hit:
            family = name
            evidence.append({"field": "job_family", "value": name, "origin": "rule", "text": hit})
            break
    directions = []
    for name, (required, terms) in DIRECTIONS.items():
        hit = next((term for term in terms if has_term(term, title + "\n" + body)), None)
        if family == required and hit:
            directions.append(name)
            evidence.append({"field": "directions", "value": name, "origin": "rule", "text": hit})
    if department:
        evidence.append({"field": "official_department", "value": department, "origin": "official", "text": "部门：" + department})
    if business:
        evidence.append({"field": "business_lines", "value": business, "origin": "official", "text": "业务线：" + business})
    candidates = [name for name in ("抖音", "豆包", "飞书", "火山引擎", "剪映", "TikTok", "CapCut", "微信", "腾讯云") if name.casefold() in title.casefold() and name != business]
    evidence.extend({"field": "business_line_candidates", "value": name, "origin": "rule", "text": name} for name in candidates)
    return {"version": VERSION, "job_family": family, "directions": directions, "business_line_candidates": candidates,
            "official_department": department, "official_category": category, "published_at": published,
            "business_lines": [business] if business else [], "evidence": evidence}


def validate_condition(condition: dict | None, depth: int = 0, count: list | None = None) -> dict:
    if condition is None:
        return {"all": []}
    count = count if count is not None else [0]
    count[0] += 1
    if depth > 6 or count[0] > 50 or not isinstance(condition, dict):
        raise ValueError("筛选条件过深或过多（最多 50 项、6 层）。")
    for key in ("all", "any", "not"):
        if key not in condition:
            continue
        if set(condition) != {key}:
            raise ValueError("条件不能混用分组和字段。")
        if key == "not":
            return {key: validate_condition(condition[key], depth + 1, count)}
        if not isinstance(condition[key], list) or (key == "any" and not condition[key]):
            raise ValueError("分组必须是条件列表。")
        return {key: [validate_condition(c, depth + 1, count) for c in condition[key]]}
    if set(condition) != {"field", "op", "values"}:
        raise ValueError("条件需要 field、op、values，不能包含额外字段。")
    field, op, values = condition["field"], condition["op"], condition["values"]
    if field not in FIELDS or op not in {"in", "contains", "between", "unknown"}:
        raise ValueError("不支持的筛选字段或操作，请先读取岗位查询 schema。")
    if not isinstance(values, list) or len(values) > 30 or any(not isinstance(v, str) or not v.strip() or len(v) > 300 for v in values):
        raise ValueError("values 必须是最多 30 项的非空短字符串列表。")
    if op == "unknown":
        if values:
            raise ValueError("unknown 操作不接受值。")
    elif not values:
        raise ValueError("筛选值不能为空。")
    if field in DATES and op not in {"between", "unknown"}:
        raise ValueError("时间字段使用 between，结束时间不包含在内。")
    if op == "between":
        if field not in DATES or len(values) != 2 or instant(values[0]) >= instant(values[1]):
            raise ValueError("时间区间应为 [开始, 结束)，开始必须早于结束。")
    if field in {"job_family", "directions"}:
        allowed = FAMILIES if field == "job_family" else DIRECTIONS
        values = [next((k for k, label in LABELS.items() if label == v), v) for v in values]
        if any(v not in allowed for v in values):
            raise ValueError("未知岗位分类，请从 schema 的分类取值中选择。")
    return {"field": field, "op": op, "values": values}


def matches(job: dict, c: dict) -> bool:
    if "all" in c:
        return all(matches(job, child) for child in c["all"])
    if "any" in c:
        return any(matches(job, child) for child in c["any"])
    if "not" in c:
        return not matches(job, c["not"])
    field, op, expected = c["field"], c["op"], c["values"]
    if field == "company":
        actual = [job["company"]["slug"], job["company"]["name"]]
        expected = [ALIASES.get(v, v) for v in expected]
    elif field == "text":
        actual = [str(job.get("title") or "") + "\n" + str(job.get("description_raw") or "")]
    else:
        actual = job["classification"].get(field) if field in {"job_family", "directions", "business_lines", "business_line_candidates", "official_department", "official_category", "published_at"} else job.get(field)
        actual = actual if isinstance(actual, list) else [actual] if actual is not None else []
    if op == "unknown":
        return not actual
    if op == "between":
        return bool(actual) and instant(expected[0]) <= instant(actual[0]) < instant(expected[1])
    if field == "locations":
        actual = [str(a).removesuffix("市") for a in actual]
        expected = [v.removesuffix("市") for v in expected]
    if op == "contains":
        return any(e.casefold() in str(a).casefold() for e in expected for a in actual)
    return any(e.casefold() == str(a).casefold() for e in expected for a in actual)


class JobCatalog:
    def __init__(self, config: CareerConfig | None = None, *, jobs: JobService | None = None,
                 semantic: Callable | None = None, clock: Callable | None = None):
        self.config = config or CareerConfig.from_env()
        self.jobs = jobs or JobService(self.config)
        self.semantic = semantic
        self._semantic_cache_hits = 0
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _records(self, condition: dict | None = None, *, active_only: bool = False) -> list[dict]:
        # Push index-friendly exact predicates to storage before classifying candidates.
        # Complex any/not and derived tags remain fully checked by matches below.
        prefilters = [{"field": "status", "op": "in", "values": ["active"]}] if active_only else []
        def visit(c: dict) -> None:
            if "all" in c:
                for child in c["all"]:
                    visit(child)
            elif c.get("field") in {"company", "locations", "recruitment_type", "status", *DATES} and c.get("op") in {"in", "between"}:
                prefilters.append({**c, "values": [ALIASES.get(v, v) for v in c["values"]]} if c["field"] == "company" else c)
        if condition:
            visit(condition)
        with self.jobs._repository_session() as repository:
            records = repository.catalog_records(prefilters)
        self.config.data_dir.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.config.data_dir / "catalog-derived.sqlite3", timeout=30) as cache:
            cache.execute("CREATE TABLE IF NOT EXISTS classification (job_id TEXT PRIMARY KEY, fingerprint TEXT, data TEXT)")
            saved = {r[0]: (r[1], r[2]) for r in cache.execute("SELECT job_id,fingerprint,data FROM classification")}
            for job in records:
                fingerprint = hashlib.sha256((VERSION + str(job.get("title")) + str(job.get("description_raw"))).encode()).hexdigest()
                prior = saved.get(job["id"])
                data = json.loads(prior[1]) if prior and prior[0] == fingerprint else classify(job)
                if not prior or prior[0] != fingerprint:
                    cache.execute("INSERT OR REPLACE INTO classification VALUES (?,?,?)", (job["id"], fingerprint, json.dumps(data, ensure_ascii=False)))
                job["classification"] = data
        return records

    def schema(self) -> dict:
        facets = self.jobs.get_job_filters()
        records = self._records()
        observed = {}
        for field in ("business_lines", "business_line_candidates", "official_department", "official_category"):
            values = Counter()
            unknown = 0
            for job in records:
                value = job["classification"][field]
                if not value:
                    unknown += 1
                values.update(value if isinstance(value, list) else [value] if value else [])
            observed[field] = {"values": [{"value": v, "count": n} for v, n in values.most_common(50)],
                               "unique_values": len(values), "truncated": len(values) > 50, "unknown_jobs": unknown}
        return {"version": 1, "fields": sorted(FIELDS), "operators": ["in", "contains", "between", "unknown"],
                "groups": ["all", "any", "not"], "date_interval": "[start,end)", "timezone": "Asia/Shanghai",
                "default_status": "active", "newness": "公共目录首次发现，非首次导入时间",
                "companies": facets["companies"], "locations": facets["locations"], "company_aliases": ALIASES,
                "recruitment_types": facets["recruitment_types"],
                "observed_classification_values": observed,
                "job_families": {k: LABELS[k] for k in FAMILIES}, "directions": {k: LABELS[k] for k in DIRECTIONS},
                "semantic_candidate_limit": 100, "now": self.clock().isoformat(),
                "example": {"all": [{"field": "company", "op": "in", "values": ["字节"]}, {"field": "locations", "op": "in", "values": ["北京"]}]}}

    def search(self, condition: dict | None = None, *, limit: int = 20, offset: int = 0,
               include_inactive: bool = False, today: bool = False, semantic_query: str | None = None,
               semantic_offset: int = 0) -> dict:
        return self._search(condition, limit=limit, offset=offset, include_inactive=include_inactive,
                            today=today, semantic_query=semantic_query, semantic_offset=semantic_offset)

    def collect(self, condition: dict | None = None, *, include_inactive: bool = False,
                today: bool = False, semantic_query: str | None = None) -> dict:
        """Trusted digest executor: evaluate one snapshot once, retain every match."""
        return self._search(condition, include_inactive=include_inactive, today=today,
                            semantic_query=semantic_query, collect=True)

    def _search(self, condition: dict | None = None, *, limit: int = 20, offset: int = 0,
               include_inactive: bool = False, today: bool = False, semantic_query: str | None = None,
               semantic_offset: int = 0, collect: bool = False) -> dict:
        self._semantic_cache_hits = 0
        c = validate_condition(condition)
        query_options = {"condition": c, "today": today, "include_inactive": include_inactive, "semantic_query": semantic_query, "semantic_offset": semantic_offset}
        if any(type(v) is not int for v in (limit, offset, semantic_offset)) or not 1 <= limit <= 100 or offset < 0 or semantic_offset < 0:
            raise ValueError("分页范围不正确，limit 为 1–100。")
        if type(today) is not bool or type(include_inactive) is not bool:
            raise ValueError("today 和 include_inactive 必须是布尔值。")
        if semantic_query is not None and (not isinstance(semantic_query, str) or not 1 <= len(semantic_query.strip()) <= 1000):
            raise ValueError("语义条件必须是 1–1000 字的文本。")
        if today:
            day = self.clock().astimezone(TZ).date()
            c = {"all": [c, {"field": "first_seen_at", "op": "between", "values": [datetime.combine(day, time.min, TZ).isoformat(), datetime.combine(day + timedelta(days=1), time.min, TZ).isoformat()]}]}
        rows = [j for j in self._records(c, active_only=not include_inactive) if (include_inactive or j["status"] == "active") and matches(j, c)]
        rows.sort(key=lambda j: (instant(j["first_seen_at"]).timestamp(), j["id"]), reverse=True)
        total_candidates, warnings = len(rows), []
        stale = sum((self.clock() - instant(j["last_seen_at"])).total_seconds() > 7 * 86400 for j in rows)
        if stale:
            warnings.append(f"候选中有 {stale} 个岗位超过7天未确认，请以官网为准；仍保留原在招标记，不推断为下线。")
        stale_sources = self.status().get("stale_sources", [])
        if stale_sources:
            warnings.append(f"公共目录有 {len(stale_sources)} 个来源超过48小时未成功确认或尚无成功记录；未匹配不能解释为官网没有新增。")
        if self.status().get("state") in {None, "waiting", "running"}:
            warnings.append("岗位目录尚未完成本轮同步；当前结果不代表官网的完整岗位范围。")
        partial, evaluated = False, 0
        if semantic_query:
            if self.semantic is None:
                raise ValueError("SEMANTIC_UNAVAILABLE：请先配置模型；不能把语义评估失败当作零匹配。")
            candidates = rows[semantic_offset:semantic_offset + 100]
            evaluated, partial = len(candidates), semantic_offset + len(candidates) < len(rows) or semantic_offset > 0
            rows = self._semantic_rows(candidates, semantic_query)
            if partial:
                warnings.append("仅评估候选的一部分，匹配数量不是全库总数。")
            warnings.append("语义判断仅使用每个岗位前4000字的原文证据，信息不足的岗位未被判断为匹配。")
        page = rows if collect else rows[offset:offset + limit]
        for job in page:
            job["match_evidence"] = job["classification"]["evidence"] + job.get("semantic_evidence", [])
            for key in ("description_raw", "responsibilities", "requirements"):
                job.pop(key, None)
        result = {"kind": "job_catalog_result", "result_id": uuid.uuid4().hex, "jobs": page, "query": query_options, "total": None if partial else len(rows),
                "evaluated_matches": len(rows), "candidate_total": total_candidates,
                "limit": len(rows) if collect else limit, "offset": offset, "has_more": not collect and offset + limit < len(rows),
                "applied_condition": c, "include_inactive": include_inactive, "semantic_query": semantic_query,
                "semantic": {"evaluated": evaluated, "cache_hits": self._semantic_cache_hits, "model_calls": evaluated - self._semantic_cache_hits,
                             "partial": partial, "next_offset": semantic_offset + evaluated if semantic_query and semantic_offset + evaluated < total_candidates else None},
                "warnings": warnings, "sort": "first_seen_at_desc,id_desc", "timezone": "Asia/Shanghai", "generated_at": self.clock().isoformat(), "freshness": self.status()}
        if not collect:
            with sqlite3.connect(self.config.data_dir / "catalog-derived.sqlite3", timeout=30) as cache:
                cache.execute("CREATE TABLE IF NOT EXISTS query_results (id TEXT PRIMARY KEY, data TEXT, created REAL)")
                cache.execute("INSERT INTO query_results VALUES (?,?,?)", (result["result_id"], json.dumps(result, ensure_ascii=False), self.clock().timestamp()))
                cache.execute("DELETE FROM query_results WHERE id NOT IN (SELECT id FROM query_results ORDER BY created DESC LIMIT 200)")
        return result

    def result(self, result_id: str) -> dict:
        if not re.fullmatch(r"[a-f0-9]{32}", result_id):
            raise ValueError("无效查询标识。")
        try:
            with sqlite3.connect(self.config.data_dir / "catalog-derived.sqlite3") as cache:
                row = cache.execute("SELECT data FROM query_results WHERE id=?", (result_id,)).fetchone()
        except sqlite3.Error:
            row = None
        if not row:
            raise ValueError("查询结果已过期，请重新查询。")
        return json.loads(row[0])

    def _semantic_rows(self, rows: list[dict], query: str) -> list[dict]:
        self._semantic_cache_hits = 0
        from ..local_jobs import worker_lock
        scope = hashlib.sha256((str(getattr(self.semantic, "cache_namespace", "custom")) + query).encode()).hexdigest()
        try:
            with worker_lock(self.config.data_dir / (".semantic-" + scope + ".lock")):
                return self._evaluate_semantic_rows(rows, query)
        except BlockingIOError:
            raise ValueError("相同语义条件正在评估，请等待完成后重试；未重复调用模型。") from None

    def _evaluate_semantic_rows(self, rows: list[dict], query: str) -> list[dict]:
        output = []
        with sqlite3.connect(self.config.data_dir / "catalog-derived.sqlite3", timeout=30) as cache:
            cache.execute("CREATE TABLE IF NOT EXISTS semantic_cache (cache_key TEXT PRIMARY KEY, result TEXT)")
        for job in rows:
            key = hashlib.sha256(json.dumps([VERSION, getattr(self.semantic, "cache_namespace", "custom"), query, job["title"], job["description_raw"]], ensure_ascii=False).encode()).hexdigest()
            with sqlite3.connect(self.config.data_dir / "catalog-derived.sqlite3", timeout=30) as cache:
                stored = cache.execute("SELECT result FROM semantic_cache WHERE cache_key=?", (key,)).fetchone()
            if stored:
                self._semantic_cache_hits += 1
            # Model calls must never hold a SQLite write transaction.
            decision = json.loads(stored[0]) if stored else self.semantic(query, job)
            if not isinstance(decision, dict) or type(decision.get("match")) is not bool or not isinstance(decision.get("evidence"), str):
                raise ValueError("SEMANTIC_FAILED：模型未返回有效判断。")
            evidence = decision["evidence"]
            if decision["match"] and (not evidence or evidence not in job["title"] + "\n" + job["description_raw"]):
                raise ValueError("SEMANTIC_FAILED：判断缺少可核验的原文依据。")
            if not stored:
                with sqlite3.connect(self.config.data_dir / "catalog-derived.sqlite3", timeout=30) as cache:
                    cache.execute("INSERT OR REPLACE INTO semantic_cache VALUES (?,?)", (key, json.dumps(decision)))
            if decision["match"]:
                job["semantic_evidence"] = [{"field": "semantic", "origin": "model", "text": evidence}]
                output.append(job)
        return output

    def status(self) -> dict:
        from ..local_jobs import read_status
        state = read_status(self.config)
        result = {k: state.get(k) for k in ("mode", "state", "completed", "failed", "updated_at", "published_at", "sources")}
        stale = []
        for source in state.get("sources", []):
            success = source.get("last_success_at")
            if state.get("mode") == "local":
                timestamp = source.get("checked_at", 0) if source.get("status") == "succeeded" else 0
                success = datetime.fromtimestamp(timestamp, timezone.utc).isoformat() if timestamp else None
            if not success or (self.clock() - instant(success)).total_seconds() > 48 * 3600:
                stale.append({"slug": source.get("slug"), "last_success_at": success})
        result["stale_sources"] = stale
        return result
