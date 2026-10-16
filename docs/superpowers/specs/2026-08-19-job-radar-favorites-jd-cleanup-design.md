# 岗位雷达收藏箱、JD 简化与测试数据清理设计

## 目标

本轮只处理岗位雷达中的三个问题：

1. 将现有“仅看收藏”复选框升级为顶部明确的“全部岗位 / 收藏箱”双入口。
2. 岗位详情不再分别展示“职位职责”和“职位要求”，只展示原始完整 JD。
3. 删除生产 PostgreSQL Catalog 中误留的测试公司和测试岗位，并阻止测试再次污染共享 Catalog。

本轮不改变岗位匹配、申请包、定制简历和模拟面试使用的结构化职责、要求字段。

## 收藏箱交互

岗位雷达标题和筛选区之间增加紧凑的分段入口：

- `全部岗位`：查询当前筛选条件下的全部岗位。
- `收藏箱`：在相同筛选条件上增加 `favorite_only=true`。

收藏箱显示当前用户的收藏岗位总数。数量通过现有岗位列表接口的 `total` 获取，不新增
收藏数据模型。进入收藏箱、取消收藏、筛选条件变化和收藏写入成功后均刷新该数量。

原“仅看收藏”复选框删除，避免同一状态出现两个控制入口。收藏按钮、CAS
`expected_version`、失败回滚和版本冲突刷新逻辑保持不变。用户在收藏箱中取消收藏后，
该岗位立即从列表移除，并自动选择剩余列表中的第一项；列表为空时显示收藏箱空状态。

## 岗位详情

删除详情中的“职位职责”和“职位要求”两个展示区块，将“完整 JD”标题改为“JD”。
页面逐字展示 `description_raw`，保留换行和原始顺序。

后端响应和 PostgreSQL 中的 `responsibilities`、`requirements` 字段继续保留，因为岗位
匹配、申请包、定制简历和模拟面试仍依赖这些结构化字段。本轮只是减少重复展示，不改变
领域数据或分析行为。

## 测试数据清理

生产库已确认存在 33 个无业务引用的测试岗位：

- `API Company`：1 个。
- `Flow Company`：1 个。
- `Packet Co`：10 个。
- `Tailored Co`：21 个。

识别条件使用测试公司 slug，而不是仅按显示名称匹配：

- `api-company`
- `flow-company`
- `packet-company-%`
- `tailored-company-%`

删除前在事务内再次验证：

1. 命中岗位数仍为 33。
2. `job_tracking`、`job_application_events`、`application_packets`、
   `tailored_resume_drafts`、`interview_sessions`、`job_resume_matches` 的引用数均为 0。
3. 命中的 Job Source `source_type` 只能是 `test` 或 `integration`。
4. 不命中任何正式公司 slug 和 34 个正式 Crawl Source。

任一条件不满足则回滚，不执行部分删除。验证通过后按外键顺序删除测试岗位、对应 Job
Source 和空 Company。执行前生成 SQL 计数和目标 ID 清单，执行后复核：

- 测试公司和岗位均为 0。
- active 岗位由包含测试数据的 10,802 降为 10,769，差值严格为 33。
- 正式来源数量不变。
- 重复业务键仍为 0。

## 防止再次污染

污染来源是 PostgreSQL 集成测试向 `TEST_DATABASE_URL` 写入共享 Catalog 后只关闭连接，
没有清理测试创建的公司、来源和岗位。

相关测试改为使用唯一 ID 并在 fixture teardown 中删除本测试创建的用户业务数据和共享
Catalog 数据。清理失败必须使测试失败，不能静默忽略。测试运行说明明确要求
`TEST_DATABASE_URL` 指向隔离 Gate 数据库；生产部署配置不作为测试默认值。

## 验收

自动化验收：

- 顶部存在“全部岗位”和“收藏箱”，原“仅看收藏”控件不存在。
- 收藏箱请求携带 `favorite_only=true`。
- 收藏数量、取消收藏后的列表和空状态正确。
- 岗位详情只出现一个“JD”区块，不出现“职位职责”“职位要求”或“完整 JD”标题。
- PostgreSQL 测试 teardown 后不存在本轮创建的 Company、Source、Job 和用户业务记录。
- TypeScript、GUI 聚焦测试、Python PostgreSQL 聚焦测试、Alpha build、
  `compileall` 和 `git diff --check` 通过。

真实验收：

- 生产公司筛选仅显示正式公司，不再出现 `API Company`、`Flow Company`、
  `Packet Co`、`Tailored Co`。
- 真实收藏、取消收藏和收藏箱切换通过。
- 桌面和 375×812 视口无横向溢出、遮挡或不可操作控件。
- 公网 health 为 PostgreSQL/Redis ready，后端和 Caddy restart count 为 0。

## 发布与回滚

前端和后端沿用当前 Alpha 受控发布流程。发布前备份当前静态前端、Skill/代码镜像和测试
数据删除清单。旧后端容器、原 PostgreSQL 恢复点和旧静态前端继续保留。

前端或后端 Gate 失败时恢复旧镜像和静态文件。测试 Catalog 数据删除不反向恢复，因为其
删除前已证明无业务引用；删除清单保留用于审计。
