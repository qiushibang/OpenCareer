# 快手国内社招浏览器 Adapter 设计

## 目标

在不复用匿名 session Cookie 的前提下，通过快手公开招聘页面完整抓取国内社招。

## 架构

- 纯 parser 处理 listing 与 dictionary fixture。
- `KuaishouBrowserAdapter` 接受注入式 `fetch_dataset`。
- 生产 fetcher 在专用线程启动一次 fresh Playwright context。
- 页面首屏取得 dictionary/第一页，随后点击“下一页”直到总数完成。
- 浏览器返回纯 JSON 后立即关闭，parser 生成 JobSnapshot。

## 安全

- 只允许 `zhaopin.kuaishou.cn`。
- 不读取、保存或复用 Cookie/storage state。
- 不登录、不处理验证码。
- 90 秒浏览器预算，MCP 总预算 120 秒。
- 总数、页数、重复 ID、字典映射或 JD 必填字段异常时整轮失败。

## 数据

地点、职类、经验必须通过官方 dictionary code 映射。未知 code 整轮失败，不能直接
显示内部代码或猜测名称。

## 测试与验收

- fixture parser；
- dictionary 映射；
- 重复 ID、未知 code、空 JD；
- 注入 dataset pipeline；
- asyncio 专用线程；
- 142 页 live smoke；
- MCP dry run；
- registry 与完整回归。
