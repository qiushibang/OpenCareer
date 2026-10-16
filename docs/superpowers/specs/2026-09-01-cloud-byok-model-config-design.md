# 云端 BYOK：用户自带 API Key 与自选模型（设计规格）

日期：2026-09-01
状态：已批准（用户确认密钥存储与回退策略两项决策）

## 背景

`app.opencareer.online` 上线 Authing 登录后，所有用户的模型调用都走服务器内置
DeepSeek key，额度由站长承担。桌面端 OpenWorker 本来就有完整的 BYOK 设施：
`/v1/providers` REST（配置/校验/删除 key）、`ProviderSetup.tsx` 表单、
`ProviderRouter` 按 `provider:<name>` 前缀从 `SecretStore` 取凭据。云端缺失的只有
两件事：

1. `SessionManager.__init__`（`coworker/server/manager.py:193`）硬编码
   `SecretStore()`，全部用户共享进程级 `state_dir()/secrets.json`。
2. `coworker/server/alpha.py:28` 把 `/v1/providers`、`/v1/settings` 整段 403。

## 决策

- **密钥存储**：每用户文件 SecretStore（`state_dir()/users/<uid>/secrets.json`，
  0600）。与桌面行为一致；数据库 dump/备份天然不含用户密钥。缺点：密钥明文落盘
  在服务器数据卷上，与桌面本地存储同级；用户已确认接受。
- **回退策略**：未配置 BYOK 的用户继续用服务器默认模型（`manager.model` 回退
   DeepSeek）。已配置用户的默认模型来自自己的 prefs。

## 设计

### 后端（3 处最小改动）

1. `SessionManager.__init__` 增加可选参数 `secrets: SecretStore | None = None`，
   `self.secrets = secrets or SecretStore()`。桌面默认行为不变。
2. `run.py` `manager_for(principal)` 传入
   `SecretStore(state_dir()/"users"/<uid>/"secrets.json")`。下游 ProviderRouter、
   MCPManager、engine 零改动即按用户隔离。
3. `alpha.py`：`_BLOCKED_PREFIXES` 移除 `/v1/providers`；`blocks_http` 增加精确
   路径放行 `/v1/settings/default-model`（其余 `/v1/settings` 保持 403，
   `/v1/chat/completions` 代理保持封禁）。

复用的既有语义：`set_provider` 合并字段写入 profile 并盖 `key_set_at` 戳、
推荐模型自动加入清单、首个可用 provider 自动接管默认模型；
`verify_provider` 不落盘做活体校验；`set_default_model` 写 per-user prefs 并即时
生效（新会话用 `self.model`，当前会话随消息携带 model）。

### GUI

1. `composerModelPolicy` alpha 分支扩展：`configuredModels`（来自
   `getProviders()` 推导）非空时提供可选列表，`backendModel` 保持首位；空列表时
   维持现状单模型。
2. `App.tsx`：alpha 模式 boot 时 `getProviders()` 推导模型列表（已配置 provider
   的 `suggested_models`，openai 裸名、其余 `name:model` 前缀），填入 `models`
   state 供 composer picker 使用。
3. `ModelsTab`（`ManageTabs.tsx`）alpha 适配：`getSettings` 403 不再卡
   "正在加载…"；ProviderCards/ProviderForm 原样复用；桌面专属
   ComposerPickerCard（依赖 `/v1/settings/models/*`）在 alpha 替换为
   「默认模型」卡片（POST `/v1/settings/default-model`，成功后刷新 health）。

## 安全边界

- `get_providers()` 响应只含非 secret 字段（base_url 等），永不含 key 明文。
- alpha 放行面 = 已登录用户 + 仅这两个前缀；匿名仍由 auth middleware 401。
- 用户 key 只进入自己 SessionManager 的 SecretStore 与 ProviderRouter 缓存，
  不写日志、不进数据库。

## 验收

1. 双账号隔离：A 配置 key/默认模型后，B 的 `/v1/providers` 不显示 A 的配置，
   B 的对话仍走服务器默认模型；A 删除 key 不影响 B。
2. 响应审计：providers/default-model 全链路响应与后端日志无 key 明文。
3. alpha 闸门：`/v1/providers*` 与 `/v1/settings/default-model` 可达；其余
   `/v1/settings/*`、`/v1/chat/completions` 仍 403。
4. GUI：alpha 登录后设置 → 模型可配置 key（Test 通过/失败路径）、选默认模型、
   composer picker 出现用户模型并随消息生效。
5. 服务器部署后真实浏览器走完整流程。

## 非目标

- 不改 `coworker/providers/registry.py`、`router.py`、`engine.py`。
- 不做 key 轮换提醒、用量统计、按 token 计费。
- 不放行 `/v1/chat/completions` 代理（openai 兼容接口滥用面）。
