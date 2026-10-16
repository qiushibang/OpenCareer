# 面试评价与 Career 数据平台设计

> 日期：2026-08-18
>
> 状态：方案已批准，书面规格修订中
>
> 目标：在不削弱 Alpha 安全、不破坏桌面端的前提下，增加可审计的面试评价能力，
> 隔离用户私有数据，恢复完整岗位抓取，并为共享岗位目录演进建立明确边界。
>
> 数据平台细化设计以
> `2026-08-18-postgres-context-and-crawler-platform-design.md` 为准。该规格根据用户反馈
> 将 PostgreSQL、完整上下文入库和精确 Origin 纳入本轮交付。

## 1. 范围与交付顺序

本设计包含四个相互关联、但必须独立验收的交付包：

1. 面试评价 Skill、逐题评价契约和用户可见报告。
2. InterviewSession 驱动的五题动态进度看板与会话复用。
3. M1a 用户私有 Career 数据、简历文件、Conversation 和运行目录隔离。
4. PostgreSQL 数据平台、完整上下文迁移、全来源岗位抓取和每日调度。

执行顺序遵守现有 M1 Gate：

1. 先完成并部署验证 M1a-1 身份上下文。
2. 再完成 M1a-2 Career 私有数据隔离。
3. 再完成 M1a-3 每用户 OpenWorker Runtime 和 Conversation 隔离。
4. 当前单用户 Alpha 完整抓取可以并行恢复，但只写当前生产库。
5. 隔离 Gate 通过后，在同一轮继续完成 PostgreSQL 迁移和共享岗位目录切换。

每个交付包使用独立提交、测试和部署 Gate。任何一个 Gate 失败时停止后续线上切换，
不回滚用户原有未提交修改，也不覆盖生产数据。

## 2. 本轮不可违反的边界

- PostgreSQL 是云端权威持久层；Redis 只保存可重建运行态，不能成为业务数据唯一副本。
- Origin 可以改为数据库驱动的多入口配置，但必须继续按协议、主机和端口精确匹配，不能
  使用通配、后缀匹配或宽松正则。
- 不修改 Alpha token 注入或高风险工具限制。
- 不把 token、简历内容或模型密钥写入前端产物。
- 不进行自动投递、登录招聘网站、验证码处理或受限接口绕过。
- 不使用面试分数预测录用概率。
- 不将口音、语速、停顿、人格印象或文化契合度作为默认评分项。

## 3. 面试评价 Skill

### 3.1 边界

新增产品 Skill：

```text
.coworker/skills/career-interview-evaluation/SKILL.md
```

Skill 名称为 `career-interview-evaluation`。它只负责把一道题、该题目标和用户回答
转成结构化评价建议，不负责创建 InterviewSession、保存问题、切换题目或生成文件。

现有 `mock-interview` 继续负责：

- 根据 Blueprint 生成单问题。
- 提交回答和评价。
- 决定追问、核验、深挖、切题或结束。
- 调用报告生成工具。

面试开始时加载 `mock-interview` 和 `career-interview-evaluation`。后续回答不再由 GUI
重复发送 Skill 名称；服务端从同一 Conversation 历史识别已成功加载的 Skill。刷新或
服务恢复后，如果历史中缺少有效 Skill 结果，才允许重新加载。

### 3.2 输入上下文

评价前必须取得：

- 精确问题文本、题型和本题目标胜任力。
- `probe_target`、`probe_dimension` 和 `depth_level`。
- 与本题相关的 JD 要求。
- 允许使用的已确认简历证据卡。
- 当前用户回答。
- 当前题已有追问及评价证据，避免重复追问同一缺口。

不能取得目标胜任力、问题或回答时，不生成分数，返回结构化缺失原因。

### 3.3 动态激活维度

通用候选维度：

| 维度 | 观察对象 |
|---|---|
| `relevance` | 是否直接回答本题目标并识别关键约束 |
| `specificity` | 是否提供具体、可核查的情境或事实 |
| `ownership` | 本人的职责、决策、动作和团队边界是否清楚 |
| `reasoning` | 假设、备选方案、选择依据和因果链是否成立 |
| `outcome` | 结果、基线、口径、验证方式和副作用是否明确 |
| `clarity` | 信息是否足以理解和评分 |
| `reflection` | 是否识别局限、纠偏和后续改变，仅在适用题型启用 |

题型附加维度：

- 产品题：用户问题、优先级、方案一致性、指标与实验、协作推进。
- 技术题：技术正确性、边界条件、设计质量、权衡、测试和可靠性。
- AI/ML 题：问题形式化、数据质量、基线、模型选择、实验评估、误差分析和部署约束。

每题只激活与题目目标相关的维度。STAR、量化结果、失败、反思、权衡、领导力和技术
深度均不得机械用于每一道题。

### 3.4 行为锚点与计分

模型为每个激活维度返回 0 到 4 的行为等级：

| 等级 | 含义 |
|---:|---|
| 0 | 偏题、矛盾，或完全没有可评分证据 |
| 1 | 只有抽象主张，关键事实缺失 |
| 2 | 有相关经历或思路，但证据链不完整 |
| 3 | 证据具体，主要判断成立，仍有一个次要缺口 |
| 4 | 证据充分、可核查，且与本题目标一致 |

模型必须为每个等级附上回答原文证据或 `missing_evidence`，不得直接凭总体印象输出总分。
后端根据题型预设权重确定性计算：

```text
question_score =
    round(sum(level * weight) / sum(4 * weight) * 100)
```

未激活维度不进入分母。用户可见分数带：

- 85–100：证据充分。
- 70–84：主体成立，存在一处关键缺口。
- 50–69：相关但不足以稳定判断。
- 0–49：偏题、过度抽象、关键事实缺失或明显矛盾。

该分数表示本题目标达成度，不表示录用概率或候选人的总体能力。

### 3.5 主痛点、原因和优化策略

主痛点从激活维度中选择，优先级如下：

1. 会使回答无法成立的缺口。
2. 当前等级距离下一行为锚点最大的缺口。
3. 能通过一次追问或一次重组明显改善的缺口。

原因必须包含：

- 观察：回答实际说了什么或缺少什么。
- 标准：本题下一行为等级需要什么。
- 影响：为什么该缺口妨碍面试官判断。

优化策略只给一个下一步动作，不生成虚构数字、经历、角色或结果。

### 3.6 结构化输出

模型输出的数据进入 `evaluation_v2`，至少包含：

```json
{
  "question_type": "past_behavior",
  "target_competency": "product_judgment",
  "active_dimensions": [
    {
      "name": "ownership",
      "level": 2,
      "weight": 2,
      "evidence": ["我们最后选择了灰度发布"],
      "missing_evidence": "本人负责的判断和交付边界"
    }
  ],
  "primary_pain": "个人贡献不清",
  "reason": "说明了团队方案，但没有说明本人决策和动作。",
  "improvement": "用团队目标、我的职责、关键动作和结果重组回答。"
}
```

服务端验证枚举、等级、权重、证据长度和必填字段，再计算 `question_score`。新对象在现有
`evaluation_json` 中写入 `version: 2`；原有 v1 五维字段继续可读，不再作为新回答的用户
可见评价来源。

### 3.7 Skill 提示词协议

`SKILL.md` 使用以下固定步骤，模型不得跳步：

1. 读取当前 InterviewSession，不使用聊天记忆猜测题目、岗位或简历。
2. 从本题 `question_type`、`probe_target` 和 Blueprint 选择评价模板。
3. 只激活评价模板允许的维度，并说明每个激活维度与本题目标的关系。
4. 从候选人回答中摘录支持证据；没有原文支持时写入 `missing_evidence`。
5. 对每个激活维度匹配 0–4 行为锚点，不直接生成 0–100 总分。
6. 选择一个阻碍本题判断的主痛点，生成“观察、标准、影响”三段式原因。
7. 只提出一个不改变事实的优化动作。
8. 根据证据缺口建议 `FOLLOW_UP`、`VERIFY_CLAIM`、`DEEP_DIVE` 或
   `SWITCH_TOPIC`，但最终动作仍由 `mock-interview` 和领域门禁决定。

提示词必须包含以下禁止项：

- 不得使用未出现在已确认简历或当前回答中的事实。
- 不得奖励孤立百分比；数字必须有样本、基线、口径和个人贡献。
- 不得因为回答没有使用 STAR 字样而扣分。
- 不得把表达风格、口音、停顿或人格印象写入评价。
- 不得在 `evidence` 低或关键缺口仍可追问时建议 `SWITCH_TOPIC`。
- 不得把本题分数解释成录用概率或候选人总体排名。

Skill 输出先由模型写成严格 JSON，再作为 `submit_interview_answer` 的评价参数。模型在
JSON 前后添加解释文本时，工具调用应被拒绝并要求重试，不能用字符串截取猜测 JSON。

### 3.8 题型模板与权重

权重不是由模型自由决定，而是由领域代码按题型和目标胜任力读取。初始模板如下：

| 题型 | 必选维度 | 可选维度 | 权重原则 |
|---|---|---|---|
| 过去行为题 | relevance、specificity、ownership、outcome | reasoning、reflection、clarity | 本题目标和 ownership 权重最高 |
| 产品 Case | relevance、reasoning、product_problem、prioritization、validation | tradeoff、clarity | 问题定义、判断和验证权重最高 |
| 技术知识题 | relevance、technical_correctness、clarity | boundary、tradeoff | 正确性权重最高，不要求 STAR |
| 编码题 | relevance、technical_correctness、testing、boundary | complexity、clarity | 正确性、测试和边界权重最高 |
| 系统设计题 | relevance、architecture、tradeoff、reliability | scale、evolution、clarity | 架构、权衡和可靠性权重最高 |
| AI/ML Case | relevance、problem_formulation、data、evaluation | baseline、error_analysis、deployment | 问题、数据和评估权重最高 |
| 失败/复盘题 | relevance、ownership、diagnosis、reflection | outcome、clarity | 责任、诊断和改变权重最高 |

每个模板权重总和不要求相同，换算公式统一归一化。新增题型必须同时增加模板、行为锚点和
测试，不能回退到“所有维度平均”。

## 4. 面试进度与报告

### 4.1 进度看板

右侧看板直接消费 `useConversationInterview` 已有的 InterviewSession 状态，不建立
第二套流程状态。

固定显示五个题位：

- 已完成：蓝色，显示题号、动态标签和问题摘要。
- 当前题：绿色，显示题号、动态标签和完整当前问题。
- 未生成：灰色，只显示题号和“待生成”。

删除“重播问题”“提前结束”和独立“流程状态”。用户提交文字或语音回答后，系统完成
评价并自动推进下一题。评价失败时当前题保持绿色，并显示可重试错误，不提前标记完成。

### 4.2 报告

每道题只展示：

- 题目和动态标签。
- 单题综合分。
- 一个主要痛点。
- 基于回答证据的原因。
- 一个可执行优化策略。

后台保留激活维度、行为等级、原文证据和评分公式，供调试和审计。跨题总结按 Blueprint
覆盖目标汇总，不计算五个固定维度的机械平均分。

### 4.3 相似会话复用

用户从同一岗位、同一简历再次进入面试时：

- 存在绑定 Conversation 的未完成 InterviewSession：默认恢复该会话。
- 已完成：创建新会话，保留历史结果。
- 用户明确选择重新开始：创建新会话，并将旧的未完成会话归档，不删除记录。

Conversation 标题包含精确岗位标题和面试状态，降低左侧相似会话的识别成本。

## 5. 数据所有权与 PostgreSQL

### 5.1 云端权威数据源

云端全部持久数据进入 PostgreSQL：

- 共享岗位目录和抓取历史。
- 用户 Career、简历、投递、匹配和面试。
- Conversation、完整消息、Compaction、Memory、Todo、Inbox、审批和 Automation。
- 简历原件、报告、导出文件和抓取快照 Blob。
- 每轮 Context Manifest 和审计事件。

Redis 只保存可重建的缓存、租约、锁、presence、限流和事件通知，不保存业务唯一副本。

### 5.2 共享岗位目录

PostgreSQL `catalog` schema 拥有：

- `companies`
- `job_sources`
- `crawl_sources`
- `crawl_runs`
- `jobs`
- `job_versions`
- `job_events`
- 原始快照索引

它不保存简历、收藏、投递、匹配、面试、对话或用户标识。Crawler 使用独立数据库角色，
是唯一批量写入者；后端以读取为主。

### 5.3 用户私有 Career 数据

PostgreSQL `career` schema 的用户表拥有：

- 简历导入、确认事实、版本和预览。
- 收藏、投递状态和申请事件。
- 岗位匹配快照。
- 申请准备包、定制简历和导出记录。
- InterviewSession、逐题回答和评价。

用户表包含 `user_id`、启用 RLS，并通过外键引用共享岗位。Repository 显式带 `user_id`，
RLS 作为第二道隔离门禁。

### 5.4 简历和 Artifact

简历原文件、面试报告、逐字稿和定制简历进入带 SHA-256、媒体类型、所有者和生命周期的
PostgreSQL Blob。临时文件只用于 OCR 和渲染，事务完成后删除。删除继续采用显式名称确认
和软删除记录。

### 5.5 Conversation 与 Runtime

Conversation 的完整消息以 append-only 行保存；Compaction 只保存压缩视图，不删除原消息。
Memory、Skill hash、Context Manifest、Todo、Automation 和 Inbox 同样入库。同一用户的
HTTP、WebSocket 和后台任务必须解析到同一个 `Principal`。桌面端继续使用 SQLite/文件
Adapter，保持现有行为兼容。

## 6. 分阶段迁移

### 6.1 M1a-2：先证明私有隔离

先通过 Principal、Repository 条件和 PostgreSQL RLS 三层测试证明 Alice 无法读取 Bob 的
简历、面试、匹配、投递、Conversation 和 Blob。桌面端仍读取现有本地数据库。

### 6.2 M1a-3：隔离 Conversation 和 Runtime

引入有上限、惰性创建的 `ManagerRegistry`。验证每个用户的 Conversation、审批、Memory、
Context Manifest 和 MCP 环境互不交叉。

### 6.3 PostgreSQL 迁移

短暂停写后，把 SQLite、JSONL、JSON 和私有文件迁移到 PostgreSQL；校验每表计数、主键、
外键、Blob SHA-256 和抽样业务查询。通过影子读取后切换 `DATABASE_URL`，原数据卷保留只读
回滚。详细步骤以 PostgreSQL 数据平台规格为准。

## 7. 完整爬虫恢复

### 7.1 数据流

```text
官方公开来源
  -> 每来源一次 fetch
  -> JobSnapshot 缓存
  -> 数量和字段质量检查
  -> CrawlerService 幂等写入
  -> JobVersion / JobEvent / CrawlRun
```

不为每个用户重复访问招聘站点。迁移后 Crawler 只写 PostgreSQL `catalog` 和 shared Blob；
Redis 只接收缓存失效通知。

### 7.2 运行策略

- 全部来源串行，源之间保留暂停。
- 单来源墙钟超时，失败不阻塞其他来源。
- 失败来源不产生部分写入，不增加 missing_count，不触发 offline。
- 数量异常下降或关键字段空值异常时标记 degraded。
- 快照写入 `crawler-cache`，落库失败可离线重放。
- Playwright 源使用独立 Crawler 容器，容器 uid 保持 10001。

### 7.3 恢复 Gate

服务器依次执行：

1. `--list` 核对注册来源。
2. 分组 dry-run，记录每源数量、耗时和失败原因。
3. 备份生产数据库。
4. 按轻量 API、静态来源、Playwright 来源分批正式写入。
5. 检查 schema v11、外键、重复身份、来源数和 active 数。
6. 复跑成功来源，验证绝大多数为 unchanged。
7. 启动每日 04:00 加随机抖动的调度。

历史 `9,960 active` 是参考基线，不是强制伪造目标。验收以当前官方来源真实返回、失败源
清单、无部分污染和幂等复跑为准。

## 8. 错误处理与回滚

- 评价模型输出不合法：拒绝保存评价，保留回答并重试评价，不重复提交用户回答。
- 当前题推进失败：保持原题和版本，提示可恢复，不创建重复 Conversation。
- 用户路径解析失败：明确拒绝请求，不退回 `local` 用户目录。
- 数据库锁：使用 busy timeout 和有界退避，超过上限后停止该写入。
- 爬虫单源失败：记录失败并继续其他来源，不执行该源下线判断。
- 迁移校验失败：继续使用原数据库和原容器配置。
- 线上部署失败：恢复旧镜像和 Compose 配置，数据卷不删除。

## 9. 测试与验收

### 9.1 Skill 与评价

- Skill frontmatter、触发条件和必要指令契约测试。
- 不同题型激活不同维度。
- 缺少数字但不要求量化的回答不被机械扣分。
- 低证据回答保持同一 target 追问。
- 模型不能凭空补充数字、角色或结果。
- 同一结构化等级输入得到相同后端总分。
- 旧 v1 报告仍可读取。

### 9.2 GUI

- 五个题位的完成、当前和待生成状态。
- 动态题目标签和长文本不溢出。
- 无重播、提前结束和独立流程状态控件。
- 文字与语音回答均自动推进。
- 相同未完成面试恢复原 Conversation。
- 桌面和移动视口截图无重叠。

### 9.3 数据隔离

- 两个 token 的简历、面试、投递和 Artifact 交叉访问均失败。
- 两个 Manager 的 Conversation、消息、Compaction 和 Context Manifest 不交叉。
- MCP 子进程收到匹配 Principal 的目录。
- 非法 user ID 和路径穿越被拒绝。
- 桌面 `local` 回归通过。

### 9.4 爬虫

- Fixture 测试默认不联网。
- dry-run 不修改岗位状态。
- 缓存重放不访问网络。
- 失败源不触发 offline。
- WAL、锁重试和多次抓取幂等。
- 服务器完成来源计数、外键、重复身份和健康检查。

### 9.5 项目级 Gate

至少运行：

```bash
python -m coworker.server.run --help
cd surfaces/gui && npx tsc && cd -
bash deploy/build-frontend.sh
python -m extensions.career_mcp.crawl_cli --list
docker compose -f deploy/docker-compose.ip.yml config >/dev/null
docker compose -f deploy/docker-compose.yml config >/dev/null
```

涉及服务器部署时额外验证：

- `/_openworker/v1/health`
- Alpha REST 403 边界
- WebSocket 101 和错误 token 1008
- 当前用户简历、会话和岗位计数
- Crawler 容器内 uid 10001

## 10. 完成定义

本设计完成需要同时满足：

- 评价 Skill 能稳定输出可审计的逐题评价，报告只展示单题分、痛点、原因和策略。
- 右侧五题进度由 InterviewSession 驱动，重复入口可恢复未完成会话。
- 用户私有 Career、简历、Conversation 和 Artifact 通过自动化测试证明隔离。
- 当前 Alpha 恢复全来源抓取并启用每日调度，失败源有明确记录且不污染岗位状态。
- 共享岗位目录具有经过校验和可回滚的迁移路径，不为每用户重复抓取或复制长期岗位历史。
- 桌面端、Alpha 安全不变量和现有用户数据保持可用。

## 11. 实施文件与今晚交付批次

### 11.1 批次 A：评价 Skill 与报告

主要文件：

- 新增 `.coworker/skills/career-interview-evaluation/SKILL.md`。
- 修改 `.coworker/skills/mock-interview/SKILL.md`，接入评价 Skill，但不复制其规则。
- 修改 `extensions/career_mcp/domain/interviews.py`，增加题型模板、结构校验、确定性计分和
  v2 报告编译。
- 复用 `interview_turns.evaluation_json` 保存带 `version: 2` 的新对象，不修改数据库
  schema，不重建用户表。
- 修改 `extensions/career_mcp/services/interviews.py` 和对应 Repository。
- 增加 Skill 契约、领域计分、迁移和旧报告兼容测试。

验收：对高质量、模糊、缺数据、矛盾和虚构诱导回答运行固定用例；逐题报告只显示总分、
主痛点、原因和策略。

### 11.2 批次 B：进度看板、会话复用与 Skill 缓存

主要文件：

- 修改 `surfaces/gui/src/components/RightRail.tsx`，接入 InterviewSession。
- 新增聚焦的面试进度组件，避免继续扩大通用 RightRail。
- 修改 `surfaces/gui/src/App.tsx` 和 `CareerJobsView.tsx`，恢复未完成面试。
- 修改 `careerInterview.ts`，回答轮次不再重复声明 Skill。
- 修改 `coworker/server/app.py`，仅在 Conversation 未加载 Skill 时注入加载指令。
- 增加 React 状态、会话恢复和服务端 Skill 历史测试。

验收：五个动态题位、无多余按钮、文字和语音自动推进；重复进入恢复原会话；首轮加载后
后续回答不再调用 `load_skill`。

### 11.3 批次 C：M1a-2 与 M1a-3 隔离

主要文件：

- 新增 PostgreSQL schema、RLS 和 Repository Adapter。
- 修改 Career 服务构造，所有用户查询显式使用 Principal。
- 新增 `coworker/server/managers.py`，实现有上限的 `ManagerRegistry`。
- 修改 `coworker/server/run.py`、`app.py` 和 `manager.py`，统一解析用户 Runtime 和数据库
  事务上下文。
- 增加跨 token Career、Conversation、Blob、Context Manifest 和 MCP 环境隔离测试。

验收：两个测试用户建立同名简历和同标题会话后仍完全隔离；连接池复用不泄漏 Principal；
桌面 `local` 不迁移、不回归。

### 11.4 批次 D：全来源爬虫恢复

执行内容：

- 本地运行 fixture 和 CLI 自检。
- 部署 PostgreSQL，完成 SQLite/JSONL/JSON/文件迁移和影子读取。
- 服务器清理同步包中的 `._*` 文件，重建 Crawler 镜像。
- 服务器分组 dry-run，保存 JSON 摘要和快照缓存。
- 备份原数据卷和 PostgreSQL。
- 轻量来源、静态来源、Playwright 来源分批正式写入。
- 核验来源、岗位、active、失败源、外键和重复身份。
- 启动 Crawler profile 并确认下一次调度时间。

该批次写入共享 PostgreSQL Job Catalog。服务器内存不足、来源持续风控或数据质量 Gate
失败时，保留成功来源和失败清单，不强行达到历史数量。

### 11.5 批次 E：完整上下文与运行协调

本轮把 canonical messages、Compaction、Memory、Skill hash、Context Manifest、Todo、
Inbox 和 Automation 写入 PostgreSQL。Redis 接入缓存、锁、租约、presence 和事件通知；
Redis flush 后必须能从 PostgreSQL 恢复运行。OriginPolicy 从 PostgreSQL 读取多入口精确
origin，并与 HTTP/WS 共用。

每个批次完成后更新开发日志并形成独立提交。任何批次失败都不能通过放宽 Origin、token、
用户路径、简历门禁、评分证据或抓取质量检查来继续。
