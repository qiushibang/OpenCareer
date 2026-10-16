# OpenCareer 每日岗位抓取容器（M0.5）。
#
# 和后端镜像的关系：依赖清单是「后端精简依赖 + playwright + chromium」。刻意做成两个镜像，
# 因为浏览器只有抓取时需要：朋友们的后端容器保持轻量，浏览器的体积和内存只由这一个容器承担。
#
# 构建上下文同样是仓库根目录（compose 里已配 context: ..）：
#   docker compose -f deploy/docker-compose.yml build crawler
#   docker build -f deploy/crawler/Dockerfile -t opencareer-crawler:alpha .
FROM python:3.11-slim

# ---- 国内机房加速开关（默认全空 = 官方源，境外构建不用管）--------------------------------
# 抓取镜像是三个镜像里最容易被网络卡住的：pip + apt + chromium 二进制（~150MB）都要下载。
#   APT_MIRROR                例：mirrors.aliyun.com
#   PIP_INDEX_URL             例：https://mirrors.aliyun.com/pypi/simple/
#   PIP_TRUSTED_HOST          例：mirrors.aliyun.com
#   PLAYWRIGHT_DOWNLOAD_HOST  例：https://cdn.npmmirror.com/binaries/playwright
#     （playwright 默认从 cdn.playwright.dev 拉浏览器，国内经常超时/断流）
ARG APT_MIRROR=""
ARG PIP_INDEX_URL=""
ARG PIP_TRUSTED_HOST=""
ARG PLAYWRIGHT_DOWNLOAD_HOST=""
ARG REQUIREMENTS=deploy/requirements-server.txt

RUN if [ -n "$APT_MIRROR" ]; then \
      sed -i "s|deb.debian.org|$APT_MIRROR|g; s|security.debian.org|$APT_MIRROR|g" \
        /etc/apt/sources.list.d/debian.sources /etc/apt/sources.list 2>/dev/null || true; \
    fi

# git：aisuite 走 git 依赖时需要。ca-certificates：抓 https 站点。tzdata：定时按本地时区算点，
# 不装的话容器里只有 UTC，"每天凌晨 4 点" 会偏 8 小时。
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Shanghai \
    # 浏览器装到固定全局路径，而不是 root 的 ~/.cache——否则切到非 root 用户后找不到。
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

COPY deploy/vendor /tmp/vendor
COPY deploy/requirements-server.txt deploy/requirements-server.cn.txt /tmp/
COPY deploy/crawler/requirements-crawler.txt /tmp/requirements-crawler.txt
RUN set -eu; \
    if [ -n "$PIP_INDEX_URL" ]; then export PIP_INDEX_URL="$PIP_INDEX_URL"; fi; \
    if [ -n "$PIP_TRUSTED_HOST" ]; then export PIP_TRUSTED_HOST="$PIP_TRUSTED_HOST"; fi; \
    pip install -r "/tmp/$(basename "$REQUIREMENTS")" -r /tmp/requirements-crawler.txt

# --with-deps 会用 apt 装 chromium 需要的一堆系统库（字体、libnss、libatk……）。
# 必须在 root 下执行，且只装 chromium（firefox/webkit 用不到，能省 ~500MB）。
RUN set -eu; \
    if [ -n "$PLAYWRIGHT_DOWNLOAD_HOST" ]; then export PLAYWRIGHT_DOWNLOAD_HOST="$PLAYWRIGHT_DOWNLOAD_HOST"; fi; \
    playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/pyproject.toml
COPY coworker /app/coworker
COPY extensions /app/extensions
COPY deploy/crawler/entrypoint.sh /app/deploy/crawler/entrypoint.sh

# -e . 让 extensions 包可导入（和后端镜像同理）；--no-deps 防止 pip 顺手拖进 OCR 全家桶。
RUN pip install --no-deps -e . \
    && chmod +x /app/deploy/crawler/entrypoint.sh

# ⚠️ uid 必须和后端镜像一致（deploy/Dockerfile 里也是 10001）。抓取容器要写朋友们的数据卷，
# uid 不一致就会 Permission denied。
RUN useradd --create-home --uid 10001 opencareer \
    && mkdir -p /cache /targets \
    && chown -R opencareer:opencareer /app /cache /targets \
    && chmod -R a+rX /ms-playwright

USER opencareer

# CRAWL_TARGETS 留空时只写 CAREER_DATA_DIR 一个库（本地单人调试用）。
# compose 会把它设成 "/targets/a/career /targets/b/career ..."。
ENV CRAWL_TARGETS="" \
    CRAWL_AT="04:00" \
    CRAWL_JITTER_MINUTES=25 \
    CRAWL_RUN_ON_START=0 \
    CRAWL_SNAPSHOT_CACHE=/cache/snapshots \
    CRAWL_SOURCE_TIMEOUT=300 \
    CRAWL_PAUSE_SECONDS=3 \
    OPENCAR_HEADLESS=1

ENTRYPOINT ["/app/deploy/crawler/entrypoint.sh"]
