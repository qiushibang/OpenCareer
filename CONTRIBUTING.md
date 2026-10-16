# 贡献指南

感谢帮助改进 OpenCareer。请先阅读 `AGENTS.md`、`CODEX_START_HERE.md` 和 `docs/README.md`。

小范围问题可直接提交修复；较大的功能或架构变化请先开 Issue 讨论。
复用 OpenWorker 的现有引擎、权限、模型路由与会话机制，求职能力放在 Career 扩展中。

开发环境使用 Python 3.12，安装 `python -m pip install -e '.[dev,messaging,bedrock,cloud]'`；
前端在 `surfaces/gui/` 下执行 `npm ci`。运行两套 Python 测试时请分开：

```bash
python -m pytest tests -q
python -m pytest extensions/career_mcp/tests -m 'not ocr_acceptance' -q
```

前端执行 `npx tsc --noEmit`、`npx vitest run` 和 `npm run e2e`。
本地启动集成验收见 `docs/22_LOCAL_QUICKSTART.md`。提交中说明复现、测试和未验证项。

测试只用虚构简历、假密钥和离线 fixture，不默认访问公开招聘源或真实模型。
不得提交 `.env`、运行数据、令牌、私密截图或真实用户日志。提交前运行 Gitleaks：
`gitleaks git --redact --config .gitleaks.toml`，并人工检查 staged diff。
现有允许项仅限两条已审查的假凭据，不得扩大允许范围来掩盖真实泄露。

公开项目不是托管生产环境。贡献者无需生产凭据，不运行 `deploy/sync-to-server.sh`。
漏洞按 `SECURITY.md` 私下报告；正常 Issue 也请先脱敏。
