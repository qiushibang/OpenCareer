"""One-shot acceptance data for the fit/interview-prep skill gates (local alpha).

Creates, under the local alpha state dirs:
- 4 confirmed manual jobs (one with a master's-degree hard gate);
- 1 confirmed fictional resume (all sections, evidence for Python/RAG/Agent).
Fictional data only — never a real person's resume.
"""

from __future__ import annotations

import os

os.environ.setdefault("CAREER_DATA_DIR", ".local-state/alpha-career")
os.environ.setdefault("COWORKER_STATE_DIR", ".local-state/alpha-test")

from extensions.career_mcp.services.jobs import JobService
from extensions.career_mcp.services.resumes import ResumeService


JOBS = (
    {
        "company_name": "示例 AI 公司",
        "title": "大模型应用工程师",
        "source_url": "https://example.invalid/jobs/llm-application-engineer",
        "raw_text": (
            "示例 AI 公司正在招聘大模型应用工程师。\n\n"
            "职责：参与 Agent 应用开发、评估和上线优化。\n"
            "要求：熟悉 Python、检索增强生成和模型调用，有完整项目经验。\n"
            "地点：北京。"
        ),
    },
    {
        "company_name": "示例算法公司",
        "title": "算法工程师（硕士优先硬门槛测试）",
        "source_url": "https://example.invalid/jobs/ms-gate",
        "raw_text": (
            "示例算法公司招聘算法工程师。\n\n"
            "职责：负责推荐算法的设计、离线评估与在线调优。\n"
            "要求：硕士研究生及以上学历，计算机相关专业；熟悉 Python 与机器学习。\n"
            "地点：北京。"
        ),
    },
)


def seed_jobs() -> None:
    service = JobService()
    for job in JOBS:
        preview = service.import_manual_jd(**job, confirmed=False)
        result = service.import_manual_jd(
            **job, confirmed=True, preview_hash=preview["preview_hash"]
        )
        print("job:", result.get("job_id"), job["title"], "created=", result.get("created"))


RESUME_TEXT = (
    "测试用户，计算机科学与技术本科，2026 届。\n"
    "项目经历：校园 AI 助手（2025.03-2025.09）：使用 Python 与检索增强生成搭建问答服务，"
    "服务 500 名学生，问答准确率从 62% 提升到 81%。\n"
    "实习经历：某互联网公司后端实习（2025.06-2025.09）：参与任务队列与服务稳定性治理，"
    "编写 Go 与 Python 代码。\n"
    "技能：Python、检索增强生成、LangChain、SQL。\n"
)


def seed_resume() -> None:
    service = ResumeService()
    staged = service.stage_resume(filename="acceptance.txt", mime="text/plain", text=RESUME_TEXT)
    token = staged["upload_token"]
    proposal = {
        "basic": {"name": "测试用户", "email": None, "phone": None},
        "education": [
            {
                "school": "示例大学",
                "major": "计算机科学与技术",
                "degree": "本科",
                "start_date": "2022-09",
                "end_date": "2026-06",
            }
        ],
        "experience": [
            {
                "company": "某互联网公司",
                "title": "后端实习生",
                "start_date": "2025-06",
                "end_date": "2025-09",
                "highlights": ["参与任务队列与服务稳定性治理，编写 Go 与 Python 代码。"],
            }
        ],
        "project": [
            {
                "name": "校园 AI 助手",
                "role": "独立开发者",
                "start_date": "2025-03",
                "end_date": "2025-09",
                "highlights": [
                    "使用 Python 与检索增强生成搭建问答服务，服务 500 名学生。",
                    "问答准确率从 62% 提升到 81%。",
                ],
            }
        ],
        "skill": ["Python", "检索增强生成", "LangChain", "SQL"],
        "missing_fields": [],
        "warnings": [],
    }
    preview = service.preview_resume_import(token, proposal)
    confirmed = service.confirm_resume_sections(preview["preview_token"], ["basic", "education", "experience", "project", "skill"])
    print("resume confirmed:", confirmed.get("resume_id") or confirmed)


if __name__ == "__main__":
    seed_jobs()
    seed_resume()
