# 美团国内社招 Adapter 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 将美团官方国内社招全业务线接入 Career MCP。

**架构：** 纯 parser + 注入式 POST transport；官方列表提供完整 JD，海外城市枚举用于确定性过滤。

**技术栈：** Python 标准库、pytest、SQLite schema v3、FastMCP。

---

1. 保存 listing、海外城市和 metadata fixture。
2. 写 parser/海外过滤红灯测试。
3. 实现 envelope、岗位映射和城市集合解析。
4. 写 100 条分页 Adapter 红灯测试。
5. 实现串行分页、完整计数和海外过滤。
6. 写 POST URL/body/host/content-type/size 测试。
7. 实现生产 transport。
8. fixture pipeline created/unchanged。
9. live smoke、overlap、MCP dry run。
10. registry、文档、完整回归和提交。

停止条件：请求需要登录/签名、完整计数不稳定、列表缺少完整 JD、海外范围无法确定
或 live 超过 120 秒。
