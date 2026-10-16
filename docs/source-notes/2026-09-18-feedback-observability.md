# 反馈与日志排错：官方资料核查

资料查询日期：2026-09-18。仅核查公开官方说明；未读取真实日志、凭据或用户材料，未安装、接入、部署服务，也未检查生产状态。

## 官方事实

OWASP（Open Worldwide Application Security Project，开放全球应用安全项目）建议用 interaction identifier（交互关联编号）连接同一次用户操作的相关事件，避免事后猜测关联关系。[事件属性](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#event-attributes)

日志通常不应直接保存会话标识、访问令牌、密码、密钥、数据库连接串及敏感个人信息；姓名、电话、邮箱、文件路径也可能需要特别处理。不可信字段应验证格式，清理回车、换行和分隔符，并按输出格式编码，防止日志注入；日志失败不应拖垮应用。[排除数据](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#data-to-exclude)、[事件采集](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#event-collection)

Sentry JavaScript 文档说明：默认仍会收集请求网址、查询串、控制台操作线索及设备环境，不等于“没有个人信息”。当前文档称 `sendDefaultPii` 自 10.54.0 弃用；提供 `dataCollection` 对象后，未显式设置的类别采用更宽松默认值，可包含请求/响应正文及人工智能输入输出，应逐项关闭而非依赖一个总开关。[采集数据](https://docs.sentry.io/platforms/javascript/guides/react/data-management/data-collected/)

浏览器发送前过滤与服务端脱敏不同：后者不能保证敏感内容未离开浏览器。错误事件可用 `beforeSend`，操作线索可用 `beforeBreadcrumb`；其它数据类型需各自过滤。[敏感数据清理](https://docs.sentry.io/platforms/javascript/guides/react/data-management/sensitive-data/)

Session Replay（会话回放）默认遮蔽文本、输入并阻挡媒体，但仍有网址和控制台信息，允许网络详情后还可采集正文；其隐私配置独立于上述总开关，官方要求上线前验证遮蔽。[回放隐私](https://docs.sentry.io/platforms/javascript/guides/react/session-replay/privacy/)、[采集数据](https://docs.sentry.io/platforms/javascript/guides/react/data-management/data-collected/#session-replay)

## 项目方案建议（未实施）

首版采用站内文本反馈、受控错误上报、关联编号和独立管理员权限；诊断只允许事件类别、版本、时间、耗时、状态码等必要字段，不收集原始对话、简历、提示词、键盘记录或回放。若以后评估 Sentry，应先锁定版本、显式字段白名单，再用虚构数据检查实际上报内容与禁网降级。

按仓库 `AGENTS.md` 所述单机 2 GiB 内存约束，优先有限容量日志轮转、保留期限和基础主机告警，不先自建重型平台；这不是当前生产资源或告警状态的实测结论。
