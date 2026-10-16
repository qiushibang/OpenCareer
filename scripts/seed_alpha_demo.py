"""Create deterministic, non-personal job records for the public alpha workspace."""

from __future__ import annotations

from extensions.career_mcp.services.jobs import JobService


DEMO_JOBS = (
    {
        "company_name": "示例 AI 公司",
        "title": "大模型应用工程师",
        "source_url": "https://example.invalid/jobs/llm-application-engineer",
        "raw_text": """示例 AI 公司正在招聘大模型应用工程师。\n\n职责：参与 Agent 应用开发、评估和上线优化。\n要求：熟悉 Python、检索增强生成和模型调用，有完整项目经验。\n地点：北京。""",
    },
    {
        "company_name": "示例互联网公司",
        "title": "AI 产品经理",
        "source_url": "https://example.invalid/jobs/ai-product-manager",
        "raw_text": """示例互联网公司招聘 AI 产品经理。\n\n职责：负责 AI 功能的用户研究、需求拆解、方案设计和效果复盘。\n要求：具备产品分析能力，了解生成式 AI 产品。\n地点：上海。""",
    },
    {
        "company_name": "示例开发者工具公司",
        "title": "后端工程师（AI 平台）",
        "source_url": "https://example.invalid/jobs/ai-platform-backend",
        "raw_text": """示例开发者工具公司招聘后端工程师。\n\n职责：建设模型服务、任务队列和可观测性能力。\n要求：熟悉 Python 或 Go、关系型数据库和服务稳定性治理。\n地点：深圳。""",
    },
)


def main() -> None:
    service = JobService()
    for job in DEMO_JOBS:
        service.import_manual_jd(**job, confirmed=True)
    print(f"Seeded {len(DEMO_JOBS)} alpha demo jobs.")


if __name__ == "__main__":
    main()
