# 阿里云上线手册（你这台机器专用）

对应的机器：**华北2（北京）· Ubuntu 24.04 · 2 vCPU / 2 GiB · 40 GB · 公网 IP 203.0.113.10**，
镜像选了 Docker 应用镜像（Docker 已预装）。

这份手册只讲**现在这一步**：先在**没有域名、没有备案**的情况下，用 `http://公网IP:18080` 把产品跑起来自己测通。
备案通过后再切到域名 + HTTPS 给朋友用（最后一节讲怎么切，数据不会丢）。

---

## 0. 先明确三件事（避免白折腾）

1. **域名要备案，IP 不用。** 服务在中国内地机房，任何域名都必须先完成 ICP 备案才能正常对外提供 Web 访问，
   未备案的域名解析过来会被拦截。而直接用公网 IP 自测不牵扯域名，现在就能跑。
2. **轻量应用服务器的防火墙默认只放行 22 / 80 / 443**，其他端口要去控制台手动加规则。
   我们故意用非标端口 `18080`：需要时加规则，测完删规则，等于对外关门。
3. **这个自测入口没有登录**。Caddy 会把邀请码（token）自动注入请求头，所以打开网址就是「已登录」状态——
   谁扫到这个 IP + 端口，就能用你的账号、烧你的模型额度。所以：
   - 自测期间不要把地址发出去；
   - 不要上传真实简历（明文 HTTP，没有加密）；
   - 测完就把防火墙规则删掉。

---

## 1. 设置密码并登录服务器

控制台实例卡片上先点「**设置密码**」（你截图里那个带红点的按钮），设一个 root 密码。

然后在你自己的 Mac 上：

```bash
ssh root@203.0.113.10
```

第一次会问 `yes/no`，输 `yes`，再输刚设的密码。

进来之后先确认 Docker 真的在（应用镜像应该自带）：

```bash
docker --version
docker compose version      # 必须有这条；只有老的 docker-compose 不行
free -m                     # 看内存，应该是 ~2G
df -h /                     # 看磁盘，应该有 30G+ 可用
```

如果 `docker compose version` 报错，先补一下插件：

```bash
apt-get update && apt-get install -y docker-compose-plugin
```

---

## 2. 把代码传上去

在**你自己的 Mac**上（不是服务器上），进到部署包所在目录：

```bash
scp OpenCareer-alpha-deploy.tar.gz root@203.0.113.10:/root/
```

回到服务器上解包：

```bash
mkdir -p /opt/opencareer
tar xzf /root/OpenCareer-alpha-deploy.tar.gz -C /opt/opencareer --strip-components=1
ls /opt/opencareer/deploy          # 应该能看到 aliyun-bootstrap.sh、docker-compose.ip.yml
ls /opt/opencareer/deploy/web      # 前端已经打好包了，服务器上不需要装 Node
```

---

## 3. 拿一个 Docker 镜像加速地址（这一步不能省）

国内机器直连 Docker Hub 基本拉不动镜像，`docker build` 会卡在第一步。

1. 打开 <https://cr.console.aliyun.com>（容器镜像服务 ACR，个人版免费）
2. 左侧「镜像工具 → 镜像加速器」
3. 复制那个形如 `https://xxxxxxxx.mirror.aliyuncs.com` 的地址

---

## 4. 一键上线

在服务器上执行（把上一步的加速地址替换进去）：

```bash
cd /opt/opencareer/deploy
sudo DOCKER_MIRROR=https://xxxxxxxx.mirror.aliyuncs.com bash aliyun-bootstrap.sh
```

脚本会依次做：体检 → 加 2GB swap（2G 内存构建镜像必须，否则容易被 OOM kill）→ 配镜像加速器 →
试拉基础镜像 → 生成 `.env`（自动填公网 IP、自动生成随机邀请码）→ 构建并启动 → 自检并打印访问地址。

首次构建大约 **5～15 分钟**，主要时间在装 Python 依赖。

> 脚本是幂等的：可以反复执行，已经填好的 `.env` 不会被覆盖。

### 4.1 填模型 API Key

脚本不会替你填模型密钥（猜不到）。构建完成后：

```bash
nano /opt/opencareer/deploy/.env
```

找到这两行填好（示例用 OpenAI，用别家就填对应那一行，并把 `OPENCAR_MODEL` 改成对应写法）：

```
OPENCAR_MODEL=openai:gpt-4.1-mini
OPENAI_API_KEY=sk-xxxxxxxx
```

`Ctrl+O` 回车保存、`Ctrl+X` 退出，然后让改动生效：

```bash
cd /opt/opencareer/deploy && docker compose -f docker-compose.ip.yml up -d
```

> ⚠️ 这是**你自己的额度**在跑。去模型供应商后台设一个消费上限，别等账单说话。

---

## 5. 放行端口 → 打开网页

控制台：**轻量应用服务器 → 你的实例 → 安全 / 防火墙 → 添加规则**

| 项目 | 填什么 |
| --- | --- |
| 应用类型 | 自定义 |
| 协议 | TCP |
| 端口范围 | `18080` |
| 备注 | opencareer-alpha |

然后浏览器打开：

```
http://203.0.113.10:18080
```

**自测完，回来把这条规则删掉。**

---

## 6. 出问题时看哪里

```bash
cd /opt/opencareer/deploy

docker compose -f docker-compose.ip.yml ps                      # 容器状态（backend-a 应为 healthy）
docker compose -f docker-compose.ip.yml logs --tail=80 backend-a  # 后端日志
docker compose -f docker-compose.ip.yml logs --tail=40 caddy      # 入口 / 访问日志

curl -s localhost:18080/_openworker/v1/health                   # 后端活着吗（不需要 token）
curl -sI localhost:18080/                                        # 前端页面出得来吗
free -m                                                          # 内存 / swap 用量
```

对症下药：

| 现象 | 大概率原因 | 怎么办 |
| --- | --- | --- |
| 浏览器一直转圈 / 连不上 | 防火墙规则没加，或端口填错 | 控制台确认 TCP 18080 已放行；`curl localhost:18080` 在服务器上是通的说明只差防火墙 |
| 页面能打开，但功能报错、控制台一堆 CORS | `.env` 里 `SERVER_IP` / `IP_PORT` 和你地址栏里的不一致 | 白名单是**逐字**匹配（含端口）。改 `.env` 后 `up -d` 重启 |
| 一对话就报鉴权失败 | 模型 API Key 没填或填错 | 见 4.1 |
| `docker build` 卡住/失败在装依赖 | 镜像加速器没配 / pip 源没生效 | 确认 `.env` 里 `PIP_INDEX_URL`、`REQUIREMENTS=deploy/requirements-server.cn.txt`，重跑 bootstrap |
| 构建过程中 SSH 掉线、容器被杀 | 2G 内存不够 | 确认 swap 生效（`free -m` 的 Swap 行非 0），别同时构建抓取镜像 |

---

## 7. 每日岗位抓取（可选，2G 机器上按需开）

抓取容器带一个 chromium，镜像 ~1.5GB，内存占用是全套里最高的，所以**默认不启动**。想验证时：

```bash
cd /opt/opencareer/deploy

# 先看有哪些数据源（不联网抓，只列清单）
docker compose -f docker-compose.ip.yml --profile crawl run --rm crawler list

# 手动抓一个源试试（源名必须来自上面 list 的第一列，例如 tencent-cdg-experienced）
docker compose -f docker-compose.ip.yml --profile crawl run --rm crawler once --only tencent-cdg-experienced

# 满意了再让它常驻，每天 04:00 附近自动抓一轮
docker compose -f docker-compose.ip.yml --profile crawl up -d --build crawler

# 不想跑了
docker compose -f docker-compose.ip.yml --profile crawl stop crawler
```

细节（源清单、失败重放、参数）看 `deploy/crawler/README.md`。

---

## 8. 备案通过后：切到单域名 + Authing

正式入口已经调整为 `https://app.opencareer.online`，使用一个后端和 PostgreSQL 用户隔离，
不再使用 `friend-a / friend-b / friend-c` 子域名，也不再给域名请求注入共享邀请码。

现在备案仍在审批中，因此不要提前解析或开放域名。审批通过后请严格按照
[域名与 Authing 上线手册](../docs/19_DOMAIN_AUTHING_LAUNCH_RUNBOOK.md) 配置 Authing、DNS、HTTPS、备案号、
双账号隔离验收与回滚。根据当前决定，切换后 18080 暂时保留，不要删除其防火墙规则。
