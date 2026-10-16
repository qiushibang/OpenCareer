# 申请支持材料与模拟面试设计

## 1. 目标

本阶段在现有 OpenCareer 求职闭环上补齐两类能力：

1. 在现有受保护申请准备包中增加自我介绍、内推/HR 沟通文本和申请
   Checklist。
2. 实现与一个已保存岗位、一份已确认简历和一个 fresh match snapshot 绑定的
   按轮模拟面试，支持文本、中文云端 ASR/TTS、动态追问和结构化复盘报告。

模拟面试是 Career Agent 的领域能力，不创建独立 Voice Agent 产品。产品品牌继续
使用 OpenCareer；Career Agent 是 Persona 和能力名称。

本阶段冻结 OCR、macOS/Windows packaging、招聘来源扩充和其他发布工作。

## 2. 第一性原理

1. 模拟面试的价值是基于目标 JD、真实简历和上一轮回答进行连续深挖，不是让模型
   具备语音播放能力。
2. Agent 推理继续由 OpenWorker TurnEngine、Provider Router、Persona、Skill 和
   MCP 工具循环承担；Career Service 不直接调用模型。
3. 岗位、已确认简历和 fresh match snapshot 是面试前事实的唯一来源。面试回答是
   训练 transcript，不自动成为 Career Vault 事实。
4. 动态问题和评价需要模型语义能力，但状态、题量、事实引用、并发、隐私和文件发布
   必须由确定性 Domain/Service 强制。
5. 语音是文本面试的增强层。ASR/TTS 失败不能破坏 Session，也不能阻止文字回答。
6. 现有麦克风采集、波形、录音计时和取消能力必须复用，不重新实现。
7. 默认不持久化音频。长期保存的只有问题、transcript、隐藏评价和报告。
8. 三项申请支持材料与现有申请包使用同一事实边界和文件生命周期，不建立三套重复
   Service。

## 3. 范围

### 3.1 本阶段实现

- 申请包新增自我介绍、内推/HR 沟通文本、申请 Checklist。
- InterviewSession、InterviewTurn、Blueprint 和状态机。
- 岗位详情入口和 Career Agent 对话入口。
- 10/15/20 分钟与 5/8/10 题固定预算。
- simple、standard、deep 三档难度。
- 每轮只问一道题。
- 根据上一轮回答动态选择 FOLLOW_UP、VERIFY_CLAIM、DEEP_DIVE、
  SWITCH_TOPIC 或 WRAP_UP。
- 隐藏的逐轮评价。
- 至少五轮文本面试。
- 中文云端 ASR 和 TTS。
- ASR transcript 用户确认后提交。
- ASR/TTS 失败退回文字模式。
- transcript、interview report 和 session JSON 三个 Artifact。
- 用户提前结束。

### 3.2 明确不做

- RTC、WebRTC、LiveKit、全双工、流式 ASR/TTS。
- VAD、自动判停、用户打断 AI、回声消除。
- 摄像头、视频、表情、情绪、自信度、眼神、声纹或测谎。
- 压力面和完整 Case Interview。
- 音频长期保存或音频回放历史。
- PDF 面试报告。
- 把面试回答自动写回 Career Vault。
- Service 直接调用模型或重写 OpenWorker Agent Loop。

## 4. 采用方案

采用“专用 InterviewView + 绑定 Career Agent 会话 + Career MCP 状态机”。

不采用纯对话模式，因为它不能稳定表达 Session/Turn、进度、隐藏评价和报告状态。

不采用 Interview Service 直接调用模型，因为这会重复 Provider Router、绕开
TurnEngine，并让模型上下文、工具权限和会话生命周期出现第二套实现。

不采用一次生成问题列表，因为它无法根据用户上一轮回答动态追问。

## 5. 模块边界

### 5.1 申请支持材料

`extensions/career_mcp/domain/application_packets.py` 继续是申请准备包唯一编译器。
固定章节从八章扩展为十一章：

```text
# 申请准备包
## 岗位与官方来源
## 使用的简历
## 岗位要求证据矩阵
## 建议重点强调的已确认经历
## 暂无佐证与待确认问题
## 简历调整建议
## 自我介绍
## 内推与 HR 沟通文本
## 面试准备问题
## 申请 Checklist
## 数据版本与生成时间
```

规则：

- 自我介绍只组合已确认的职业摘要和 direct/related evidence。
- 没有职业摘要时使用岗位、教育/项目/工作证据构造，不补充新事实。
- 沟通文本固定包含岗位名称、公司、官方 URL 和最多两条已确认证据。
- 不输出手机号、邮箱、微信或其他敏感字段。
- Checklist 只把系统可证明的状态标记为完成。
- “核对官网、确认截止时间、提交申请、保存投递记录”等人工动作默认未完成。
- 继续禁止资格结论、匹配率、录用概率和从日期推导工作年限。
- 沿用现有 `ApplicationPacketService` 原子写入、幂等文件名和校验入口。

### 5.2 Interview Domain

新增 `extensions/career_mcp/domain/interviews.py`，只包含：

- session、phase、difficulty、next action 枚举。
- duration 到 question budget 的固定映射。
- Blueprint 结构和验证。
- question proposal、evaluation 和 report item 验证。
- 单问题约束和重复问题检查。
- 状态转换。
- transcript 文字统计。
- transcript、report 和 session JSON 的确定性编译。

Domain 不访问 SQLite、文件、网络、模型、Tauri 或 GUI。

### 5.3 Repository 与 Service

新增：

```text
extensions/career_mcp/database/interview_repository.py
extensions/career_mcp/services/interviews.py
```

Repository 只管理 schema v10 的 interview 表和 CAS 写入。

Service 负责：

- 校验岗位存在且可读取完整 JD。
- 校验简历已确认、未删除。
- 校验 snapshot 精确属于 job/resume 且为 fresh。
- 确定性构造 Blueprint。
- 事务状态转换和 turn index 唯一性。
- CAS version 冲突。
- 报告目录安全、原子写入、哈希和失败补偿。
- 向 HTTP/MCP 返回无私人路径的稳定结果。

Service 不调用模型，不读取敏感联系方式，不处理音频供应商。

### 5.4 Agent 与 Skill

新增：

```text
.coworker/skills/mock-interview/SKILL.md
```

Skill 强制：

- 每轮只生成一道简短问题。
- 首题可以使用固定 INTRO 引用。
- 其他问题至少绑定一个合法 requirement ID 或 resume fact path。
- 优先追问上一轮回答，不顺序朗读预生成题库。
- 模糊回答要求具体案例。
- “我们”表述追问个人贡献。
- 模糊结果追问证据或指标，但不得发明指标。
- 面试过程中不辅导、不显示评分。
- 不重复已覆盖能力，除非上一轮需要验证。
- 不读取敏感 Career Vault 字段。
- 不把回答声明为已确认事实。
- 题型能力覆盖自我介绍、简历/项目深挖、JD 能力、行为面试、产品场景、技术理解
  和可选公司动机，但只在当前 JD、简历、Blueprint 和 Previous Turns 支持时使用。

### 5.5 Voice Layer

新增：

```text
extensions/career_mcp/voice/__init__.py
extensions/career_mcp/voice/base.py
extensions/career_mcp/voice/volcengine.py
extensions/career_mcp/services/interview_voice.py
```

接口：

```python
class VoiceProvider(Protocol):
    async def transcribe(
        self,
        audio: bytes,
        *,
        language: str = "zh-CN",
    ) -> str: ...

    async def synthesize(
        self,
        text: str,
        *,
        voice: str = "interviewer",
    ) -> bytes: ...
```

火山实现是第一版 production provider。凭证存入 OpenWorker SecretStore，不写
repository、SQLite、日志、Artifact 或 Agent prompt。

现有 `ocw-stt` 继续负责麦克风。新增 capture-only WAV 能力，使云 ASR 不依赖
当前英文 Whisper 模型。原 Composer 本地英文 dictation 行为保持不变。

### 5.6 GUI

新增：

```text
surfaces/gui/src/components/InterviewView.tsx
surfaces/gui/src/careerInterview.ts
```

InterviewView 包含：

- 岗位和简历标题。
- 当前单问题卡。
- TTS 播放/重播。
- 录音或文字回答。
- ASR transcript 编辑确认。
- 轮次和题量进度。
- 提前结束。
- 完成后的报告入口。

语音只在 Tauri 中显示。浏览器开发模式保持完整文本面试能力。

## 6. 数据模型

schema 从 v9 升级到 v10。

### 6.1 `interview_sessions`

```sql
CREATE TABLE interview_sessions (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id),
    resume_import_id TEXT NOT NULL REFERENCES resume_imports(id),
    snapshot_id TEXT NOT NULL REFERENCES job_resume_matches(id),
    conversation_id TEXT,
    company TEXT,
    position TEXT NOT NULL,
    difficulty TEXT NOT NULL CHECK(
        difficulty IN ('simple', 'standard', 'deep')
    ),
    duration_minutes INTEGER NOT NULL CHECK(
        duration_minutes IN (10, 15, 20)
    ),
    question_budget INTEGER NOT NULL CHECK(
        question_budget IN (5, 8, 10)
    ),
    blueprint_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK(
        status IN (
            'created', 'ready', 'in_progress',
            'completed', 'cancelled', 'failed'
        )
    ),
    phase TEXT NOT NULL CHECK(
        phase IN (
            'preparing', 'asking', 'waiting_for_answer',
            'transcribing', 'evaluating', 'generating_report',
            'idle'
        )
    ),
    version INTEGER NOT NULL CHECK(version >= 1),
    started_at TEXT,
    ended_at TEXT,
    report_path TEXT,
    transcript_path TEXT,
    session_path TEXT,
    report_sha256 TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### 6.2 `interview_turns`

```sql
CREATE TABLE interview_turns (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES interview_sessions(id),
    turn_index INTEGER NOT NULL CHECK(turn_index >= 1),
    question_text TEXT NOT NULL,
    question_refs_json TEXT NOT NULL,
    answer_text TEXT,
    evaluation_json TEXT,
    next_action TEXT CHECK(
        next_action IS NULL OR next_action IN (
            'FOLLOW_UP', 'VERIFY_CLAIM', 'DEEP_DIVE',
            'SWITCH_TOPIC', 'WRAP_UP'
        )
    ),
    next_reason TEXT,
    started_at TEXT NOT NULL,
    answered_at TEXT,
    evaluated_at TEXT,
    UNIQUE(session_id, turn_index)
);
```

不存储音频路径。报告相对路径只允许位于
`artifacts/interviews/<session_id>/`。

## 7. Blueprint

Service 从当前岗位和 match result 构建：

```json
{
  "version": 1,
  "company": "示例公司",
  "position": "AI 产品经理",
  "difficulty": "standard",
  "duration_minutes": 15,
  "question_budget": 8,
  "focus_areas": [
    {
      "requirement_id": "requirement-1",
      "requirement": "具备 Agent 产品经验",
      "category": "hard",
      "evidence_status": "direct",
      "evidence_paths": ["project[0].highlights[0]"]
    }
  ],
  "candidate_strengths": ["project[0].highlights[0]"],
  "candidate_risks": ["requirement-2"],
  "must_probe": ["requirement-2"]
}
```

Blueprint 不包含联系方式、完整私人简历路径或未确认 preview。

## 8. 状态机

持久 status：

```text
created → ready → in_progress → completed
                            ↘ cancelled
                            ↘ failed
```

phase：

```text
preparing
→ asking
→ waiting_for_answer
→ transcribing
→ evaluating
→ asking
→ generating_report
→ idle
```

规则：

- 只有 ready 可开始。
- 只有 waiting_for_answer 的当前 turn 可提交回答。
- 回答提交后必须评价当前 turn，才能创建下一 turn。
- 保存评价和创建下一 turn 在同一事务中完成。
- 达到 question budget 后只能 WRAP_UP。
- 少于五轮时 Agent 不得主动 WRAP_UP，但用户可提前结束。
- completed/cancelled/failed 不可继续提交回答。
- 每次写入要求 expected version，旧 version 返回 VERSION_CONFLICT。

## 9. MCP 工具

保留技术文档中的七个工具名：

```text
create_interview_session
get_interview_session
start_mock_interview
submit_interview_answer
get_next_interview_question
finish_interview
generate_interview_report
```

职责：

- `create_interview_session`：创建并返回确定性 Blueprint。
- `get_interview_session`：读取无敏感信息的 session、turns 和合法引用。
- `start_mock_interview`：验证并保存第一题。
- `submit_interview_answer`：保存当前 turn 的 transcript。
- `get_next_interview_question`：原子保存上一轮隐藏评价并创建下一题。
- `finish_interview`：用户结束或正常 WRAP_UP。
- `generate_interview_report`：编译并原子发布三个 Artifact。

写工具继续经过 OpenWorker MCP 权限审批。HTTP GUI 路径使用同一 Service，不调用
MCP Client。

## 10. 每轮结构

问题 proposal：

```json
{
  "question": "请介绍与你申请这个岗位最相关的一段经历。",
  "refs": ["INTRO"],
  "topic": "self_introduction"
}
```

评价和下一题：

```json
{
  "evaluation": {
    "relevance": 8,
    "clarity": 7,
    "structure": 6,
    "depth": 8,
    "evidence": 5,
    "issues": ["结果证据不足"],
    "coaching_structure": ["背景", "个人行动", "可验证结果"],
    "fact_refs": ["project[0].highlights[0]"]
  },
  "next_action": "VERIFY_CLAIM",
  "next_reason": "需要确认结果依据",
  "next_question": {
    "question": "你通过什么指标或用户反馈判断效果有效？",
    "refs": ["project[0].highlights[0]"],
    "topic": "project_outcome"
  }
}
```

验证：

- score 是 1–10 的整数。
- 问题 5–200 字，只包含一个主问题，不拼接问题列表。
- refs 必须来自当前 Blueprint，INTRO 只允许首题。
- `fact_refs` 必须来自本次岗位/简历 match result。
- `issues` 和 `coaching_structure` 每项 1–120 字且数量有界。
- 评价不得包含录用概率、资格结论或隐藏敏感字段。
- 下一题不能与已有问题归一化后相同。

## 11. HTTP API

GUI 使用：

```text
POST /v1/career/interviews
GET  /v1/career/interviews/{session_id}
POST /v1/career/interviews/{session_id}/start
POST /v1/career/interviews/{session_id}/answers
POST /v1/career/interviews/{session_id}/next
POST /v1/career/interviews/{session_id}/finish
POST /v1/career/interviews/{session_id}/report
POST /v1/career/interviews/voice/transcribe
POST /v1/career/interviews/voice/synthesize
GET  /v1/career/interviews/{session_id}/artifacts/{kind}
```

所有接口使用现有 sidecar token 鉴权。音频接口限制 MIME、字节数和时长；错误响应
不返回供应商 body、token、音频、私人路径或完整简历。

## 12. VoiceProvider 与隐私

默认 provider 为 Volcengine。

配置项：

```text
VOLCENGINE_SPEECH_APP_ID
VOLCENGINE_SPEECH_ACCESS_TOKEN
VOLCENGINE_ASR_RESOURCE_ID=volc.seedasr.sauc.duration
VOLCENGINE_TTS_RESOURCE_ID=seed-tts-2.0
VOLCENGINE_TTS_SPEAKER=zh_male_ruyayichen_uranus_bigtts
```

实际值存入 SecretStore。环境变量只作为开发覆盖，不写入文档示例值或测试 fixture。
ASR/TTS Resource ID 和 speaker 必须属于同一已开通模型版本；TTS 2.0 不得使用
1.0 音色。

隐私不变量：

- 只在用户显式开始录音后采集。
- 默认最大单轮音频 5 分钟和 20 MB。
- Tauri、GUI 和 Server 均不写临时音频文件。
- 请求完成后释放 WAV、ASR response 和 TTS Blob。
- SQLite、日志、Artifact 和 prompt 中不出现音频 bytes。
- ASR transcript 提交前可编辑。
- 供应商失败映射为 `ASR_FAILED` 或 `TTS_FAILED`。
- ASR 失败可重试或文字回答。
- TTS 失败继续显示问题文本。

## 13. 报告

固定产物：

```text
artifacts/interviews/<session_id>/transcript.md
artifacts/interviews/<session_id>/interview-report.md
artifacts/interviews/<session_id>/session.json
```

report 固定章节：

```text
# 模拟面试复盘
## 岗位与简历
## 面试概况
## 能力维度评价
## 优势
## 主要问题
## Transcript 分析
## 逐题复盘
## 下一次训练建议
## 数据版本与生成时间
```

Transcript 分析包含：

- 回答字数总量、平均值、最长和最短回答。
- 固定中文口头禅计数。
- 归一化句段的重复表达次数。
- “我们”与“我”的使用次数。
- 数字和百分比使用次数。
- 基于 hidden relevance 的偏题程度。
- 基于 hidden structure 的 STAR/结构完整度。
- 每轮结构、证据和相关性评价。

报告中的评分明确标注为训练反馈，不是岗位资格或录用预测。逐题“参考优化”只输出
结构建议和绑定已有 answer/fact refs 的表达；固定提示按该结构重组原回答，只使用
原回答和已确认事实，不新增数字、经历、公司、项目或成果。

文件发布规则沿用定制简历的安全父目录、同目录临时文件、fsync、原子 rename 和失败
补偿。三个文件全部成功后才把 session 标记 completed。

## 14. GUI 流程

### 14.1 岗位入口

岗位详情显示“模拟面试”。点击后：

1. 选择一份已确认简历。
2. 要求存在 fresh match；没有时提示先执行岗位匹配。
3. 选择 10/15/20 分钟和 simple/standard/deep。
4. 创建 Career 会话和 InterviewSession。
5. 进入 InterviewView。

### 14.2 Career Agent 入口

用户在 Career 会话表达模拟面试意图时，Skill 要求提供或选择 job/resume/snapshot，
创建 Session 后打开相同 InterviewView，不建立第二套面试体验。

`conversation_id` 是 GUI 当前 OpenWorker Session 的身份，不是模型生成内容。该入口
必须遵守以下信任边界：

1. Career MCP 的 `create_interview_session` 不接受 `conversation_id`，只创建
   `conversation_id=NULL` 的 InterviewSession。
2. GUI 只从成功的 Career create tool result 中读取合法 UUID。
3. GUI 读取 InterviewSession 当前 version，再通过 authenticated HTTP 以当前真实
   `sessionId` 执行一次 CAS 绑定；`VERSION_CONFLICT` 最多重新读取并重试一次。
4. Service 只允许 ready/in_progress 且尚未绑定的 Session 绑定一次；相同值幂等，
   不同非空值返回 `INTERVIEW_STATE_CONFLICT`。
5. 绑定成功后才打开 InterviewView。模型不得猜测、声明或覆盖会话 ID。

### 14.3 回答

- Tauri：文字或语音。
- Browser：文字。
- ASR transcript 显示在可编辑框中。
- 用户点击“提交回答”后才进入 Agent turn。
- 提交期间禁止重复提交。
- VERSION_CONFLICT 刷新服务器状态，不丢弃用户尚未提交的文本。

## 15. 错误契约

```text
INVALID_INPUT
JOB_NOT_FOUND
RESUME_NOT_FOUND
SNAPSHOT_MISMATCH
STALE_MATCH
INTERVIEW_NOT_FOUND
INTERVIEW_STATE_CONFLICT
TURN_NOT_FOUND
TURN_ALREADY_ANSWERED
QUESTION_VALIDATION_FAILED
EVALUATION_VALIDATION_FAILED
VERSION_CONFLICT
VOICE_NOT_CONFIGURED
ASR_FAILED
TTS_FAILED
REPORT_VALIDATION_FAILED
PERSISTENCE_ERROR
```

GUI 使用固定中文映射，不显示内部异常。

## 16. 测试与阶段门

### Gate A：申请支持材料

- 十一个固定章节顺序和唯一性。
- 自我介绍、沟通文本只引用 direct/related evidence。
- none 不进入自我介绍或沟通文本。
- Checklist 的系统状态和人工未完成状态正确。
- 敏感字段、资格结论和新事实被拒绝。

### Gate B：Interview Domain 与 schema v10

- duration、difficulty、Blueprint 和引用验证。
- 单问题、重复问题、评分、Next Action 验证。
- 状态机和五轮下限。
- v9→v10 事务迁移失败可回滚和重试。

### Gate C：Repository、Service、HTTP、MCP 和 Skill

- job/resume/snapshot 精确绑定。
- MCP 创建不接受 conversation ID；GUI 使用真实 OpenWorker session ID 经 CAS
  绑定，绑定前不打开 InterviewView。
- CAS 并发和 turn index 唯一。
- submit answer 与 evaluation/next question 两阶段事务。
- Agent 不可越过 refs 或题量。
- HTTP/MCP 错误不泄漏私人数据。
- Skill 每轮只问一道题并使用 Previous Turns。

### Gate D：文本 InterviewView

- 从岗位详情选择简历并开始。
- 使用 fake Provider/Agent 完成至少五轮。
- 第二题以后依赖上一轮回答。
- 提前结束、刷新恢复和冲突处理。
- 生成并下载三个 Artifact。

### Gate E：Voice Layer

- fake Volcengine 请求 schema、鉴权、超时和错误映射。
- 音频 bytes 不写磁盘、SQLite、日志、Artifact 或 prompt。
- ASR transcript 可编辑确认。
- TTS 失败文字继续。
- Tauri capture-only 不影响现有 Composer dictation。
- 使用用户提供的凭证完成真实中文 ASR 和 TTS smoke。

### Gate F：完整验收

- 一场至少五轮的真实 Career Agent 面试。
- 问题 refs 均属于当前岗位/简历。
- 至少一次 FOLLOW_UP 或 VERIFY_CLAIM 由上一轮回答触发。
- 面试中不显示隐藏评分。
- report 包含逐题复盘和能力维度。
- 没有新事实进入 Career Vault。
- 没有音频残留。
- 后端相关回归、GUI 全量、production web build、schema v10、外键、
  `git diff --check` 通过。

本阶段不要求 OCR、macOS DMG 或 Windows installer Gate。

## 17. 今晚实施顺序

```text
申请包三章
→ Interview Domain
→ schema v10 + Repository
→ Interview Service
→ HTTP/MCP/Skill
→ 文本 InterviewView
→ VoiceProvider + 火山 ASR
→ 火山 TTS
→ 五轮真实闭环
→ 隐私与对抗验收
```

任何 Gate 未通过时停止进入下一 Gate，不通过放宽事实或隐私断言换取进度。
