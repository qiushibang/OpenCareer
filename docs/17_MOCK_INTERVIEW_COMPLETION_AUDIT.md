# Mock Interview 完成度审计

审计日期：2026-08-11

权威输入：

- 用户提供的 `CAREER_AGENT_MOCK_INTERVIEW_TECH_SPEC.md`（1347 行）。
- `docs/superpowers/specs/2026-08-10-application-support-and-mock-interview-design.md`。
- 当前代码、测试、真实 TurnEngine 记录和本机 SecretStore 状态。

状态定义：

- **已证明**：当前代码和与需求同范围的测试或真实运行证据均存在。
- **部分证明**：实现和离线协议测试存在，但缺少需求要求的真实外部运行证据。
- **未完成**：缺少实现或端到端验收。

## MVP Done Definition

| # | 要求 | 状态 | 权威证据 |
|---|---|---|---|
| 1 | 可选择一个已保存 JD | 已证明 | `CareerJobMatchPanel` 岗位入口；真实 Creation Workflow 使用保存的 `job_id`。 |
| 2 | 可选择一个简历版本 | 已证明 | `CareerJobMatchPanel.test.tsx` 覆盖单份和多份 fresh 简历选择。 |
| 3 | 可创建 InterviewSession | 已证明 | Service、HTTP、MCP 测试；真实 Session `baaad67b-8ac6-4edb-b245-933686620460`。 |
| 4 | 可生成 Interview Blueprint | 已证明 | `test_blueprint_uses_only_current_match_references` 和真实五轮 Session。 |
| 5 | 可进行文本模拟面试 | 已证明 | 真实 Aiden/TurnEngine 五轮文本闭环，记录于 `docs/11_DEVELOPMENT_LOG.md`。 |
| 6 | 每轮只问一道题 | 已证明 | Domain 拒绝多问号和单问号复合请求；真实首题修正后只保存合法问题。 |
| 7 | 下一题根据上一轮回答动态生成 | 已证明 | 真实动作链包含 `FOLLOW_UP` 和 `DEEP_DIVE`，第二题追问上一轮质量验收。 |
| 8 | 能针对简历项目深挖 | 已证明 | Blueprint fact refs、Skill 的 `DEEP_DIVE` 规则和真实项目追问。 |
| 9 | 能针对 JD 核心能力追问 | 已证明 | 非首题必须引用当前 Blueprint requirement/fact ref。 |
| 10 | 能识别模糊回答并追问 | 已证明 | Skill 强制对模糊回答优先 `FOLLOW_UP/VERIFY_CLAIM/DEEP_DIVE`；真实五轮含跟进。 |
| 11 | 能识别缺少数据的回答并追问 | 已证明 | hidden evaluation 的 `evidence`、issues 和 Skill 的证据追问规则。 |
| 12 | 能复用 OpenWorker 麦克风录音 | 已证明 | Tauri capture-only 复用 `ocw-stt`；共享 `VoiceRecordingMeter` 复用实时音量和计时。 |
| 13 | 支持中文云端 ASR | 已证明 | 豆包流式语音识别模型 2.0 小时版真实调用通过；指定中文句保留 `OpenWorker` 和“求职 Agent”。 |
| 14 | 支持 AI 面试官 TTS | 已证明 | 豆包语音合成模型 2.0 字符版真实调用通过；官方 2.0 音色返回 MP3 并完成五题合成。 |
| 15 | 可完整完成至少 5 轮语音面试 | 已证明 | 隔离真实 Aiden/TurnEngine 完成 5 次问题 TTS、5 次回答 ASR、动态追问和三份报告 Artifact。 |
| 16 | 用户可提前结束面试 | 已证明 | Service 支持评价后或等待下一题时提前结束；GUI 一轮后显示入口。 |
| 17 | 可生成 `transcript.md` | 已证明 | Service 原子发布、HTTP 下载和真实 Artifact 哈希证据。 |
| 18 | 可生成面试报告 | 已证明 | `interview-report.md` 原子发布、HTTP 下载和真实 Artifact 哈希证据。 |
| 19 | 报告包含逐题复盘 | 已证明 | 编译器固定 `## 逐题复盘`，包含原回答、问题、结构、参考优化和事实引用。 |
| 20 | 报告包含能力维度评价 | 已证明 | relevance、clarity、structure、depth、evidence 五维平均分。 |
| 21 | 不编造用户经历 | 已证明 | refs 白名单、敏感/资格结论校验、真实验收前后 Career Vault 行数不变。 |
| 22 | ASR/TTS 失败可退回文字模式 | 已证明 | `InterviewView` 保留可编辑文本和提交；TTS 失败继续显示问题。 |
| 23 | 默认不永久保存用户音频 | 已证明 | capture、HTTP、Voice Service 全程内存；残留扫描和写文件阻断测试通过。 |

结论：**23 项全部已证明。**

## 补充规格覆盖

- 两个入口均已实现：岗位详情入口和 Career Agent 对话入口。
- 10/15/20 分钟固定对应 5/8/10 题；支持 simple/standard/deep。
- Career Agent 对话创建后由 GUI 绑定真实 OpenWorker Session ID，模型不能伪造
  `conversation_id`。
- 第一版题型策略覆盖自我介绍、简历/项目深挖、JD 能力、行为面试、产品场景、
  技术理解和可选公司动机；只允许使用当前 JD、简历、Blueprint 和 Previous Turns。
- Transcript 分析覆盖字数、口头禅、重复表达、偏题程度、STAR/结构完整度、
  数字/百分比和“我们/我”责任边界。
- 逐题参考优化只使用 hidden evaluation 的结构建议、原回答和已确认事实。
- 不包含 RTC、LiveKit、VAD、自动判停、摄像头、视频或情绪识别。
- 申请支持材料已并入现有申请准备包：自我介绍、内推/HR 沟通文本和申请
  Checklist 共用原有事实边界、校验器和原子发布流程。

## 真实 Voice Gate

本机 SecretStore 权限为 `0600`，使用旧版控制台 App ID + Access Token 鉴权。凭证未
写入 Git、日志、Artifact 或本文件。生产配置为：

```text
ASR Resource ID: volc.seedasr.sauc.duration
TTS Resource ID: seed-tts-2.0
Speaker: zh_male_ruyayichen_uranus_bigtts
```

单项 smoke：

- TTS：29,037 bytes MP3，约 2,741 ms。
- ASR：116,012 bytes 内存 WAV，约 8,753 ms；识别结果保留 `OpenWorker` 和
  “求职 Agent”。
- ASR request ID：`51c4148b-1835-4633-91c2-7de137ba9d97`
- ASR `X-Tt-Logid`：`202608110556202124F38096769BC1BBA9`
- TTS request ID：`beed0d10-a1bc-49c8-a85d-3c6378b1a106`
- TTS `X-Tt-Logid`：`20260811055618137ECC92F2FBD7712998`

五轮闭环：

```text
Conversation: career-real-voice-five-turns
Interview: 24c52cb6-4577-461d-8062-08b0fcde33a8
Action: FOLLOW_UP -> FOLLOW_UP -> SWITCH_TOPIC -> FOLLOW_UP -> WRAP_UP
Final: completed / idle / version 15
```

五题 TTS 延迟为 1,261–1,874 ms；五次 ASR 延迟为 12,093–16,624 ms。每轮 transcript
为 43–69 字，且每题只有一个合法 Blueprint ref。

三份 Artifact 均为 `0600`：

- `interview-report.md`：
  `13c5de0fa649221e96b01992971318ba0612d44f685257b100e140e873c915de`
- `transcript.md`：
  `43f2b86e4d4ac5a4efd5a704224a99648c82f636ec158d9a1d162616a11156f0`
- `session.json`：
  `51d61728449f19c73287761aea29bea6ccbb0991a53e84dbca4b7eb9d3a4788e`

残留审计：凭证泄漏、音频文件、Career Vault 回写、symlink 和外键违规均为 0。
五轮云端音频由自动验收生成；物理麦克风采集由 Rust capture 与 InterviewView
测试覆盖，本轮未要求真人现场朗读。
