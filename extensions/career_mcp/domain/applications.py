"""Bounded, model-free validation of user-owned application records."""
from __future__ import annotations

from datetime import date, datetime, timezone
from urllib.parse import urlsplit
from decimal import Decimal, InvalidOperation
import re

from .job_tracking import APPLICATION_STATUSES

STATUS_LABELS = dict(zip(APPLICATION_STATUSES, ("未开始", "准备投递", "已投递", "笔试／测评中", "面试中", "已获Offer", "已接受Offer", "未通过", "已撤回")))
FIELD_LABELS = {"salary_months":"发薪月数", "monthly_salary":"月薪酬", "experience_notes":"面经", "company":"公司", "title":"岗位", "location":"地点", "status":"申请状态", "stage":"当前阶段", "priority":"优先级", "recruitment_type":"招聘类型", "batch":"批次", "department":"部门", "business_line":"业务线", "channel":"渠道", "source_url":"链接", "jd":"职位描述", "notes":"申请备注", "tags":"标签", "applied_on":"投递日期", "applied_date_source":"投递日期出处", "next_action":"下一步", "next_at":"下次时间", "deadline_on":"截止日期", "next_done":"待办完成状态", "archived":"归档状态", "salary_advertised":"岗位薪资", "salary_expected":"期望薪资", "salary_offer":"Offer报价", "offer_currency":"币种", "offer_period":"计薪周期", "offer_months":"发薪月数", "resume_import_id":"关联简历", "resume_label":"简历版本说明", "resume_sha256":"简历版本指纹", "round_name":"轮次名称", "round_number":"轮次序号", "kind":"面试类型", "format":"面试形式", "scheduled_at":"面试时间", "arrangement":"安排状态", "result":"面试结果", "questions":"面试问题", "answers":"回答要点", "review":"面经复盘", "knowledge_gaps":"待补知识", "next_step":"面试后下一步"}

TEXT_FIELDS = {"company": 200, "title": 300, "location": 200, "batch": 120,
               "department": 200, "business_line": 200, "channel": 100, "source_url": 2000,
               "jd": 200000, "stage": 100, "next_action": 2000, "notes": 200000,
               "monthly_salary": 500, "salary_advertised": 500, "salary_expected": 500, "salary_offer": 500,
               "resume_label": 300}
DEFAULTS = {**{key: "" for key in TEXT_FIELDS}, "status": "preparing", "priority": "normal",
            "recruitment_type": "", "tags": [], "applied_on": None, "next_at": None,
            "deadline_on": None, "next_done": False, "archived": False,
            "resume_import_id": None, "resume_sha256": "", "applied_date_source": "unknown", "offer_currency": "CNY", "offer_period": "month", "offer_months": None, "salary_months": 12}
ROUND_TEXT = {"experience_notes": 1000000, "round_name": 100, "questions": 200000, "answers": 200000, "review": 200000,
              "knowledge_gaps": 200000, "next_step": 10000}
ROUND_DEFAULTS = {**{key: "" for key in ROUND_TEXT}, "kind": "business", "format": "video",
                  "experience_notes": None, "scheduled_at": None, "arrangement": "unscheduled", "result": "pending", "round_number": None}
ENUMS = {"status": APPLICATION_STATUSES, "priority": ("high", "normal", "low"),
         "recruitment_type": ("", "experienced", "campus", "internship"),
         "offer_currency": ("CNY", "USD", "HKD", "other"), "offer_period": ("month", "year", "day", "unknown")}
ROUND_ENUMS = {"kind": ("business", "technical", "hr", "final", "extra", "group", "other"),
               "format": ("video", "phone", "onsite", "other"),
               "arrangement": ("unscheduled", "scheduled", "completed", "cancelled"),
               "result": ("pending", "passed", "failed", "unknown")}


def normalize(values: dict, *, interview: bool = False) -> dict:
    if not isinstance(values, dict):
        raise ValueError("记录必须是对象。")
    defaults, limits, enums = (ROUND_DEFAULTS, ROUND_TEXT, ROUND_ENUMS) if interview else (DEFAULTS, TEXT_FIELDS, ENUMS)
    if set(values) - set(defaults) or {"resume_sha256", "applied_date_source"} & set(values):
        raise ValueError("包含不支持的字段。")
    result = dict(values)
    for key, value in values.items():
        if key in limits:
            if not isinstance(value, str) or len(value) > limits[key] or "\x00" in value:
                raise ValueError(f"{FIELD_LABELS.get(key, '字段')}须为文本，且不能超过{limits[key]}个字符。")
        elif key in enums:
            if value not in enums[key]:
                raise ValueError(f"{FIELD_LABELS.get(key, '字段')}选项不正确。")
        elif key in {"archived", "next_done"}:
            if type(value) is not bool:
                raise ValueError(f"{FIELD_LABELS.get(key, '字段')}选项不正确。")
        elif key in {"round_number", "offer_months", "salary_months"}:
            if value is not None and (type(value) is not int or not 1 <= value <= (99 if interview else 24)):
                raise ValueError(f"{FIELD_LABELS.get(key, '字段')}数值范围不正确。")
        elif key in {"applied_on", "deadline_on"}:
            if value not in (None, "") and not isinstance(value, str):
                raise ValueError("日期须为字符串或空值。")
            if value:
                if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
                    raise ValueError("日期须为年-月-日。")
            result[key] = value or None
        elif key in {"scheduled_at", "next_at"}:
            if value not in (None, "") and not isinstance(value, str):
                raise ValueError("时间须为字符串或空值。")
            if value:
                if not isinstance(value, str):
                    raise ValueError("时间类型不正确。")
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    raise ValueError("时间必须包含时区。")
                result[key] = parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            else:
                result[key] = None
        elif key == "tags":
            if not isinstance(value, list) or len(value) > 20 or any(not isinstance(v, str) or not v.strip() or len(v) > 40 for v in value):
                raise ValueError("最多20个短标签。")
            result[key] = list(dict.fromkeys(v.strip() for v in value))
        elif key == "resume_import_id":
            if value is not None and (not isinstance(value, str) or len(value) > 100):
                raise ValueError("简历标识不正确。")
    if result.get("source_url"):
        url = urlsplit(result["source_url"])
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
            raise ValueError("岗位链接须为不含账号密码的HTTP或HTTPS网址。")
    return result


def validate_record(data: dict, *, interview: bool = False) -> None:
    for field in (("round_name",) if interview else ("company", "title")):
        if not data[field].strip():
            raise ValueError("请填写公司和岗位名称。" if not interview else "请填写本轮面试名称。")
    if interview and data["arrangement"] == "scheduled" and not data["scheduled_at"]:
        raise ValueError("已约面试请填写面试时间。")


def annual_salary(monthly: str, months: int | None) -> str:
    """Estimate gross annual compensation only for unambiguous numeric monthly pay."""
    if type(months) is not int or not 1 <= months <= 24:
        return ""
    match = re.fullmatch(r"\s*(\d+(?:\.\d{1,2})?)\s*(k|K|千|万|w|W)?\s*(?:元)?\s*(?:[／/]月)?\s*", monthly.replace(",", "").replace("，", ""))
    if not match:
        return ""
    try:
        amount = Decimal(match[1]) * {"k":1000,"K":1000,"千":1000,"万":10000,"w":10000,"W":10000}.get(match[2],1) * months
        if not amount.is_finite() or amount < 0 or amount > Decimal("100000000000"):
            return ""
        return format(amount.quantize(Decimal("0.01")), "f").removesuffix(".00")
    except InvalidOperation:
        return ""
