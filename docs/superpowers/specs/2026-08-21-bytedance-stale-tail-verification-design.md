# 字节岗位 Stale 尾部自动核验设计

## 目标

当字节全量 cycle 完成第三遍后，仅剩少量 `last_pass < 3` 岗位时，自动访问这些岗位
的官方公开详情页，区分仍在线与明确下线，替代人工 SQL 尾部对账。只有全部 stale
岗位都得到确定结果后才允许提交 Catalog。

该能力只处理公开页面，不登录、不携带 Cookie、不读取用户浏览器 profile，也不生成、
保存或逆向 `_signature`。

## 触发边界

- 仅在所有分片完成、`pass_number >= 3` 且常规覆盖检查未收敛时触发。
- stale 岗位数量必须在 `1..20`；超过 20 条继续标记 `degraded`。
- Adapter 必须显式实现 `verify_stale_jobs()`；其他 resumable Adapter 保持原行为。
- 已收敛 cycle 不访问详情页。

## 详情判定

`ByteDanceMainlandAdapter` 使用一个新的无状态 Chromium browser/context/page，按
scope 和数字 external job ID 构造固定官方 URL：

```text
https://jobs.bytedance.com/experienced/position/<id>/detail
https://jobs.bytedance.com/campus/position/<id>/detail
```

页面只允许最终停留在 `https://jobs.bytedance.com`。图片、媒体和字体继续阻断。
判定规则为：

- `offline`：正文包含精确文案 `该职位已下线`。
- `active`：正文同时包含 `职位描述` 和 `职位要求`，且不含下线文案。
- `unknown`：其余页面，包括登录、验证码、空白、错误页和未完成渲染。

任一岗位为 `unknown`、访问超时或发生非官方重定向时，整次尾部核验失败关闭，不修改
staging，不提交 Catalog。

## Staging 对账

Repository 新增一个原子方法，输入 active/offline ID 集合、当前 pass 和核验时间：

- active：仅将对应 stale 行的 `last_pass` 更新为当前 pass，同时更新 `observed_at`。
- offline：仅删除对应 stale staging 行，使正式提交时该岗位按完整快照缺席处理。
- 两组 ID 必须互斥；实际更新/删除数量必须与请求数量完全一致，否则事务回滚。

对账后 Runner 重新读取 cycle jobs，并再次要求所有剩余行
`last_pass == pass_number`。通过后才进入现有 `commit_complete_snapshot()` 原子提交。

## 结果与错误

成功结果增加：

```json
{
  "tail_verification": {
    "active": 2,
    "offline": 4
  }
}
```

失败结果保持 `status=degraded`、`transitions={}`，错误摘要只说明核验类别和数量，
不记录 Cookie、请求头或页面内容。

## 测试

- 纯函数覆盖 active、offline、unknown 分类。
- Adapter 覆盖固定官方 URL、单 browser 批量核验和 20 条上限。
- SQLite Repository 覆盖 active 更新、offline 删除、数量不匹配回滚。
- Runner 覆盖 2 active + 4 offline 后提交、unknown 失败关闭、超过 20 条不调用网络。
- PostgreSQL 聚焦测试覆盖 SQL 参数与受限更新条件。
- 真实官网 Gate 使用上一轮 6 个 ID，期望 2 active、4 offline；只运行详情核验，
  不改已 committed 的隔离 cycle。

## 生产影响

本轮实现和真实 Gate 仅使用本机隔离环境，不修改线上 Alpha。生产部署前仍需备份、
迁移检查和受控 crawler 发布；不能把本地 19,057 条直接写入线上数据库。
