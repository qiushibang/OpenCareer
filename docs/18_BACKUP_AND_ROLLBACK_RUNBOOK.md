# OpenCareer 备份与回滚 Runbook

## 1. 适用范围

本手册覆盖：

- 仍使用 SQLite/本地文件卷的 Alpha。
- PostgreSQL System of Record。
- Caddy 配置、证书卷、静态前端和当前 Docker 镜像。

Redis 只保存可重建运行态，不作为恢复源。

## 2. 不变量

1. 不把 `deploy/.env` 明文写入普通备份；加密文件和密钥必须分开保存。
2. PostgreSQL 必须用数据库超级用户执行 `pg_dump`，否则 `FORCE RLS` 可能漏掉其他租户。
3. 运行中的 SQLite 不直接复制数据库文件，使用 SQLite Online Backup API。
4. 回滚不把 PostgreSQL 数据反向覆盖旧 SQLite 卷。
5. 恢复先进入临时卷、临时数据库和备用端口，通过后才能进入切换窗口。
6. 任何校验失败都保持当前线上容器不变。

## 3. 完整备份集

每个恢复点必须包含：

- Alpha 数据卷：私有简历、Career SQLite、Conversation、Context 与工作区产物。
- PostgreSQL custom-format dump，以及 `pg_restore --list` 清单。
- Compose、Caddyfile、静态前端、Caddy data/config 卷。
- 精确的后端 Docker image archive。
- 加密的 `.env`；解密密钥只放离机副本，权限 `0600`。
- `SHA256SUMS`、镜像 ID、容器状态和关键业务计数。

服务器副本和离机副本都必须执行：

```bash
sha256sum -c SHA256SUMS
```

## 4. PostgreSQL 备份

以宿主机 PostgreSQL 超级用户执行：

```bash
sudo -u postgres pg_dump \
  --format=custom \
  --no-owner \
  --no-acl \
  opencareer > opencareer.dump

pg_restore --list opencareer.dump > opencareer.list
```

不要使用普通应用账号做全量 dump；租户 RLS 会让备份看似成功但缺少其他用户数据。

## 5. 隔离恢复 Gate

### 5.1 SQLite/文件卷

1. 创建新的 rehearsal Docker volume。
2. 解压备份并恢复 UID/GID `10001:10001`。
3. 对清单中的每个文件重新计算 SHA-256。
4. 对每个 `.db` / `.sqlite3` 执行 `PRAGMA integrity_check`。
5. 用备份中的旧镜像和 rehearsal 卷启动无公网容器。
6. 验证 health、岗位数、简历数和 Conversation 存在。

### 5.2 PostgreSQL

```bash
sudo -u postgres createdb -O <app-role> opencareer_restore_rehearsal
sudo -u postgres pg_restore \
  --exit-on-error \
  --no-owner \
  --no-acl \
  --role=<app-role> \
  -d opencareer_restore_rehearsal \
  opencareer.dump
```

`<app-role>` 必须从目标环境的 `DATABASE_URL` 用户名取得，不要假定固定角色名。

必须验证：

- 每张业务表的行数与源库一致。
- Blob ID、元数据 SHA 和内容指纹一致。
- 外键与唯一约束存在。
- Catalog active/source/duplicate 计数一致。
- 新后端连接临时数据库后 health 显示 PostgreSQL、Redis ready。

## 6. 正式切换与回滚

正式切换窗口：

1. 记录旧镜像 ID、Compose hash、数据卷和 health。
2. 停止用户写入。
3. 生成最终增量恢复点并校验。
4. 启动新后端，执行 REST、WebSocket、简历、面试和 Blob 下载 smoke。
5. 只有全部 Gate 通过才恢复用户流量。

任一 Gate 失败时：

1. 停止新后端。
2. 恢复备份中的 Compose、静态前端和加密配置。
3. `docker load` 恢复旧镜像。
4. 将旧数据卷以 UID `10001` 挂载到旧后端。
5. 启动旧后端并验证 health 与关键业务计数。
6. PostgreSQL 保留为只读诊断源，不覆盖旧 SQLite。

## 7. 已验证恢复点

恢复点：`20260819T072425Z`

- 服务器：`/opt/opencareer-backups/20260819T072425Z`
- 离机副本：`.local-state/backups/server/20260819T072425Z`
- 离机解密密钥：同目录 `deploy.env.key`，权限 `0600`
- 线上 Alpha 在整个演练中未重启、未替换，最终为 healthy、restart count `0`

详细结果见备份内：

```text
meta/backup-info.txt
meta/restore-rehearsal.txt
SHA256SUMS
```

## 8. 已完成生产切流

最终停写恢复点：`20260819T103248Z`

- 服务器：`/opt/opencareer-backups/20260819T103248Z`
- 离机副本：`.local-state/backups/server/20260819T103248Z`
- 离机密钥：`meta/deploy.env.key`，权限 `0600`；服务器密钥已删除
- 离机 `sha256sum -c SHA256SUMS`：全部通过
- 新后端：`opencareer-alpha-backend-pg-1`
- 新镜像：`sha256:9e2e9f8a…8d3cf`
- 旧后端：`opencareer-alpha-backend-a-1`，停止但未删除
- 旧数据卷：`opencareer-alpha_data-a`，保留且未被 PostgreSQL 反向覆盖
- Caddy 上游：`172.18.0.1:18765`

切流 Gate：

- health：`storage.mode=postgres / postgres=ready / redis=ready`
- Catalog：10,802 active、34 个抓取源、重复业务键 0
- 共享 Catalog 表和 79 个共享 Blob 在迁移前后逐表计数不变
- Career：2 份导入、5 条事实、3 个面试会话、8 个 turn、1 条 Match
- Context：10 个 Conversation、158 条 Message、1 条 Compaction
- 用户 Blob：2 条，内容 SHA-256 mismatch 0
- 对抗租户读取：Resume、Conversation、用户 Blob 均为 0
- REST、WebSocket、简历原件、面试读取和真实浏览器岗位/档案/面试页面通过
- 新后端、旧后端和 Caddy restart count 均为 0

旧 SQLite 中同一岗位/简历存在两个活动面试。迁移保留全部历史，只把较旧活动会话
标记为 `cancelled` 并记录原状态；最新活动会话保持可恢复。共享 Catalog 已存在时，
迁移只映射旧岗位引用，不写入公司、来源、岗位、版本或事件。

## 9. 字节全量来源部署恢复点

恢复点：`20260821T032119Z`

- 服务器：`/opt/opencareer-backups/20260821T032119Z`
- 离机副本：`.local-state/backups/server/20260821T032119Z`
- 离机密钥：`meta/deploy.env.key`，权限 `0600`；服务器只保留加密配置
- 14 个备份文件在服务器与离机副本均通过 `sha256sum -c`
- PostgreSQL custom dump 通过 `pg_restore --list`
- 旧镜像：`sha256:4167e8b7…572079b`
- 新镜像：`sha256:468d6b66…a3e1584`
- 旧容器 `opencareer-alpha-backend-job-radar` 和
  `opencareer-alpha_data-a` 数据卷均保留

切换后 Catalog 为 29,612 个 active 岗位，其中字节 19,063 个；active external
ID 重复为 0。Resume、Interview、Conversation 和 Message 计数与切换前一致。

## 10. 岗位雷达性能优化恢复点

恢复点：`20260821T075235Z`

- 服务器：`/opt/opencareer-backups/20260821T075235Z`
- 离机副本：`.local-state/backups/server/20260821T075235Z`
- 离机密钥：`meta/deploy.env.key`，权限 `0600`；服务器临时密钥已删除
- 12 个备份文件在服务器与离机副本均通过 `sha256sum -c`
- PostgreSQL 停写窗口 18 秒，custom dump 可由 `pg_restore --list` 读取
- 旧后端镜像：`sha256:468d6b66…a3e1584`
- 新后端镜像：`sha256:4c5f4d68…079f2`
- 旧容器 `opencareer-alpha-backend-bytedance-full` 保持 stopped 并保留

切换后 migration 8、租户可见性、REST、WebSocket、PostgreSQL、Redis、active
计数 29,612 和 active external ID 重复 0 均通过。

## 11. 旧生成链路归档与 Retirement

该流程只处理已下线的岗位匹配、Application Packet、定制简历草稿和导出。它不会
删除简历原件、面试会话、面试 Artifact、普通 Conversation 附件或抓取快照。

执行前必须停止写入并完成第 3–5 节的完整恢复点与隔离恢复 Gate。当前线上尚未执行
retirement。

SQLite：

```bash
python -m deploy.archive_legacy_career \
  --sqlite-db /data/career/career.sqlite3 \
  --workspace-root /data/workspace \
  --output /secure-backup/legacy-career

python -m deploy.retire_legacy_career \
  --sqlite-db /data/career/career.sqlite3 \
  --workspace-root /data/workspace \
  --archive /secure-backup/legacy-career \
  --manifest-sha256 <离线记录的 manifest SHA-256>
```

PostgreSQL 必须通过具有 `rolsuper` 或 `rolbypassrls` 的维护连接执行，不能使用受
FORCE RLS 限制的应用账号。凭据只通过环境变量提供：

```bash
DATABASE_URL='<maintenance connection>' \
python -m deploy.archive_legacy_career \
  --postgres \
  --output /secure-backup/legacy-career

DATABASE_URL='<maintenance connection>' \
python -m deploy.retire_legacy_career \
  --postgres \
  --archive /secure-backup/legacy-career \
  --manifest-sha256 <离线记录的 manifest SHA-256> \
  --recovery-point-id <完整恢复点 ID>
```

把归档命令输出的 `manifest_sha256` 写入独立恢复点元数据，不要只保存在归档目录
内。retirement 会复验该外部 SHA、全部 JSONL/Blob 哈希和当前源数据摘要；任一
不一致都会拒绝删除。PostgreSQL 收缩 SQL 位于
`deploy/sql/retire_legacy_career.sql`，不属于自动 migration。
