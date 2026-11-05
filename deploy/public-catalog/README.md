# 公共岗位快照分发

此任务只读既有 PostgreSQL 公共岗位目录，输出静态压缩文件。无需重建、重启或
替换网站、后端或爬虫容器。默认网页目录已挂载到 Caddy，存在的静态文件可直接
通过 `/public/jobs/v1/manifest.json` 读取，不需要新增认证例外或反向代理规则。

## 一次性准备

在自己的服务器建立 `/opt/opencareer-public-feed` 和
`/opt/opencareer/deploy/web/public/jobs/v1`；确认后一个路径是 Caddy 当前静态挂载
下的专用目录。将以下文件放入前一个目录：

| 仓库文件 | 服务器文件名 |
|---|---|
| `extensions/career_mcp/public_catalog_export.py` | `public_catalog_export.py` |
| `extensions/career_mcp/public_catalog_format.py` | `public_catalog_format.py` |
| `deploy/public-catalog/run-export.sh` | `run-export.sh` |

从同一源码生成 `sources.txt`，仅包含注册来源的逗号分隔 slug（标识），不要加入
用户自定义网址或 Shell 内容：

```bash
python -c 'from extensions.career_mcp.crawler.adapters import default_adapters,default_resumable_adapters; print(",".join(sorted(a.source_slug for a in [*default_adapters(),*default_resumable_adapters()])))'
```

生产连接串保留在原容器内部；不要复制 `.env`、密钥或数据库文件。可通过
`PUBLIC_CATALOG_CONTAINER`、`PUBLIC_CATALOG_ROOT` 和 `PUBLIC_CATALOG_OUTPUT`
环境变量适配自己的目录，systemd 单元里的路径需对应修改。

## 验证与启用

先手动运行 `bash /opt/opencareer-public-feed/run-export.sh`，核对输出数量与原公共
目录一致；从公网访问清单和至少一个快照，检查摘要和客户端导入结果。确认私有和
手动岗位均未出现，网站健康及原容器启动时间不变，再安装本目录的 service／timer：

```bash
systemctl daemon-reload
systemctl start opencareer-public-catalog.service
systemctl enable --now opencareer-public-catalog.timer
systemctl list-timers opencareer-public-catalog.timer
```

单元应复制到 `/etc/systemd/system/`。发布服务限制主机发布进程的内存与处理器使用，
数据库导出使用只读事务、服务器端游标和查询超时；文件锁防止重复运行。只有完整
导出结束后才替换清单；失败继续提供旧版本。任务日志只含数量、摘要或错误类型，
不将 JSON 行流或凭据写入日志。任务可随时独立停止：

```bash
systemctl disable --now opencareer-public-catalog.timer
```

停止分发任务不停止网站。不要删除原公共目录或用户数据库；保留旧快照便于客户端
在下载清单后继续读取对应不可变文件。生产前端同步脚本不删除 live web 的专用子目录，
如使用自己的整目录替换流程，必须保留该命名空间或重新发布快照。

## 岗位时效与持续采集

目录文件重新生成不等于官网重新核验。排查“文件是今天、岗位仍停在八月”时，检查
清单各来源的 `last_success_at`，不要只看 `generated_at`。发布器会在日志输出
`stale_source_count` 和 `stale_sources`（默认超过 48 小时）；过期来源保留已有数据，
不会把旧岗位时间改成今天。完整扫描尚未结束时，也继续保留上一份完整目录。

上游爬虫与本任务独立：字节大陆来源采用持久化分批扫描，未完成返回退出码 3，
容器每 60 秒接续；重启同样恢复已有进度，完成的来源不重复扫描。
`CRAWL_RESUME_SECONDS` 控制接续间隔，`CRAWL_RESUMABLE_BATCHES` 控制单次预算。
采集成功后，本目录现有小时级定时器才会将新数据库内容发布给共享模式客户端。
本地验证和发布边界见 [时效验收记录](../../docs/29_JOB_CATALOG_FRESHNESS_20261105.md)。
