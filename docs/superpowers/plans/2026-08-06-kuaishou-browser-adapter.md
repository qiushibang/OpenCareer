# 快手国内社招浏览器 Adapter 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 接入快手官方国内社招 1,417 条公开岗位。

**架构：** fixture 纯解析；生产环境使用一次性 Playwright context 遍历 142 页，
不暴露或持久化匿名 session。

**技术栈：** Python、pytest、Playwright browser extra、SQLite v3、FastMCP。

---

1. 保存 listing、dictionary、metadata fixture。
2. parser 与字典映射红灯。
3. 实现完整 JD、地点、职类、经验映射。
4. dataset Adapter 与 pipeline 红灯。
5. 实现一次性 Playwright 全页 fetcher。
6. 测试 asyncio 线程、host、总数、重复 ID 和超时。
7. full live smoke。
8. MCP dry run、registry、完整回归和提交。

停止条件：完整遍历超过 120 秒、页面要求登录/验证码、Cookie 必须跨 crawl 保存，
或公开 dictionary 不能映射全部岗位代码。
