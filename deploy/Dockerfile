# OpenCareer 云端后端镜像（单后端 + PostgreSQL 用户隔离，见 docker-compose.yml）。
#
# 构建上下文是仓库根目录，不是 deploy/：
#   docker compose -f deploy/docker-compose.yml build      # compose 已配好 context: ..
#   docker build -f deploy/Dockerfile -t opencareer-backend:alpha .    # 手动等价命令
FROM python:3.11-slim

# ---- 国内机房加速开关（默认全空 = 原来的官方源行为，境外机器不用管）---------------------
# 中国内地节点（阿里云/腾讯云…）直连 pypi.org、deb.debian.org 很容易超时，构建会卡死在装依赖。
# 这三个 ARG 就是给国内构建用的，compose 的 build.args 里传；本地/境外构建不传即保持原样。
#   APT_MIRROR       例：mirrors.aliyun.com   （只填域名，不带 https://）
#   PIP_INDEX_URL    例：https://mirrors.aliyun.com/pypi/simple/
#   PIP_TRUSTED_HOST 例：mirrors.aliyun.com
ARG APT_MIRROR=""
ARG PIP_INDEX_URL=""
ARG PIP_TRUSTED_HOST=""
# 依赖清单可切换：国内用 deploy/requirements-server.cn.txt（aisuite 走 vendor 里的 wheel，不连 GitHub）。
ARG REQUIREMENTS=deploy/requirements-server.txt

# Debian 12(bookworm) 的源在 /etc/apt/sources.list.d/debian.sources，老格式在 /etc/apt/sources.list，
# 两个都替一遍，谁存在替谁。
RUN if [ -n "$APT_MIRROR" ]; then \
      sed -i "s|deb.debian.org|$APT_MIRROR|g; s|security.debian.org|$APT_MIRROR|g" \
        /etc/apt/sources.list.d/debian.sources /etc/apt/sources.list 2>/dev/null || true; \
    fi

# git：aisuite 走 git 依赖时需要（国内清单已改成本地 wheel，装上也无害）。
# ca-certificates：出站调模型 API。
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# ARG 只在构建期生效。这里**故意不写成 ENV**：写成 ENV 时空值也会被 pip 当成「设了个空 index」，
# 反而报 URL 非法；下面在 RUN 里判空后再 export 才安全。

WORKDIR /app

# 依赖单独一层：改代码不必重装依赖。
# vendor/ 里是预先打好的 aisuite wheel（deploy/vendor/README.md 解释了来历），
# 国内清单会引用 /tmp/vendor/*.whl；官方清单用不到它，多拷这 200KB 无所谓。
COPY deploy/vendor /tmp/vendor
COPY deploy/requirements-server.txt deploy/requirements-server.cn.txt /tmp/
RUN set -eu; \
    if [ -n "$PIP_INDEX_URL" ]; then export PIP_INDEX_URL="$PIP_INDEX_URL"; fi; \
    if [ -n "$PIP_TRUSTED_HOST" ]; then export PIP_TRUSTED_HOST="$PIP_TRUSTED_HOST"; fi; \
    pip install -r "/tmp/$(basename "$REQUIREMENTS")"

# 只拷运行时真正需要的东西（避免把 surfaces/gui/node_modules、dist 拷进镜像）。
COPY pyproject.toml /app/pyproject.toml
COPY coworker /app/coworker
COPY extensions /app/extensions
COPY .coworker/skills /app/skills-bundled
COPY scripts/seed_alpha_demo.py /app/scripts/seed_alpha_demo.py
COPY deploy/entrypoint.sh /app/deploy/entrypoint.sh
COPY deploy/mcp.container.json /app/deploy/mcp.container.json

# `-e .` 是必须的：extensions 包只有装成 editable 才能被 `python -m extensions.career_mcp.server`
# 导入（career MCP 子进程的工作目录是数据卷，不是 /app）。--no-deps：依赖已由上面那层钉死，
# 不让 pip 顺手把 anthropic/google-genai/OCR 全家桶拖进来。
RUN pip install --no-deps -e . \
    && chmod +x /app/deploy/entrypoint.sh

# 非 root 运行。10001 是任意一个非系统 uid；宿主机上 docker volume 会自动跟随它的 owner。
RUN useradd --create-home --uid 10001 opencareer \
    && mkdir -p /data/state /data/career /data/private /data/workspace \
    && chown -R opencareer:opencareer /data /app

# 全部数据落在 /data 下（三个 env 都是项目自带的覆写点，无硬编码绝对路径）：
#   /data/state    COWORKER_STATE_DIR  → coworker.db / automation.db / inbox / personas / skills / .env
#   /data/career   CAREER_DATA_DIR     → career.sqlite3（岗位、投递、面试）
#   /data/private  CAREER_PRIVATE_DIR  → resumes/ staged/（简历原件，最敏感）
#   /data/workspace 会话工作区（alpha 模式只允许这一个）
ENV COWORKER_STATE_DIR=/data/state \
    CAREER_DATA_DIR=/data/career \
    CAREER_PRIVATE_DIR=/data/private \
    OPENCAR_ALPHA_WORKSPACE=/data/workspace \
    OPENCAR_ALPHA_TEST=1 \
    OPENCAR_HEADLESS=1
VOLUME ["/data"]

USER opencareer
EXPOSE 8765

# entrypoint 只做「首次启动的目录/MCP/技能兜底」，然后 exec 下面这条 CMD。
ENTRYPOINT ["/app/deploy/entrypoint.sh"]
CMD ["python", "-m", "coworker.server.run", "--cwd", "/data/workspace", "--host", "0.0.0.0", "--port", "8765"]
