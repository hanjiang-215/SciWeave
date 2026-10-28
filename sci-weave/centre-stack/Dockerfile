# 中央服务单容器镜像。
#
# 一个镜像、一个容器，用 supervisord 把 `sci-weave/centre-control` 的 12 个进程
# 角色全部跑起来（research-map 的 MCP 与看板来源、research-wiki 的 MCP 与看板
# 来源、buffer、registry、email-service、coordinator、centre-agents 的
# gateway/mcp 与 gateway/subscriber、dashboard-api、web-ui 静态托管）。
#
# 这是 `docs/TECH_STACK.md` 里「centre-control 是否打成一个镜像、单容器多进程」
# 那条待裁决问题的落地形态，决策记录见 `docs/adr/0006-centre-single-container.md`。
#
# 构建上下文必须是 `sci-weave/`（不是 `centre-control/`，也不是本目录）：
#   docker compose -f sci-weave/centre-stack/compose.yaml build
# 两个 ARG 用于受限网络下把基础镜像指向镜像代理；镜像源属于环境配置，不写进仓库。
ARG PYTHON_IMAGE=python:3.13-slim
ARG NODE_IMAGE=node:22-slim
# ---------------------------------------------------------------- web-ui 构建
# VITE_DASHBOARD_API_URL 是 Vite 的构建期变量，所以前端必须在这里构建成静态
# 产物；运行时镜像不含 Node。
FROM ${NODE_IMAGE} AS web-ui

ENV PNPM_HOME=/pnpm \
    PATH=/pnpm:$PATH \
    CI=1

RUN npm install -g pnpm@10

WORKDIR /build

# 先只装依赖，源码改动时不必重装。
COPY centre-control/web-ui/package.json centre-control/web-ui/pnpm-lock.yaml \
     centre-control/web-ui/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY centre-control/web-ui/ ./
# 浏览器直接访问 dashboard-api，因此这里必须是浏览器视角的绝对地址。
# 默认值只适用于本机冒烟；部署时用 `--build-arg` 或 compose 的 build.args 覆盖。
ARG VITE_DASHBOARD_API_URL=http://127.0.0.1:8702/
ENV VITE_DASHBOARD_API_URL=${VITE_DASHBOARD_API_URL}
RUN pnpm run build

# --------------------------------------------------------------- 运行时镜像
FROM ${PYTHON_IMAGE}

# uv 只用于构建期同步依赖，装完即删。从 PyPI 装而不是 COPY ghcr 官方镜像：
# 受限网络下 ghcr 常常拉不动，而 pip 通道本来就要用（supervisord 也走它），
# 少一个必须可达的镜像源就少一类构建失败。版本与应用侧的 uv 保持一致。
ARG UV_VERSION=0.10.7
RUN pip install --no-cache-dir "uv==${UV_VERSION}"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON=/usr/local/bin/python3 \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# 各项目都以 path 依赖引用 shared/audit-trail，因此先落共享包再同步依赖。
COPY centre-control/shared/ /app/shared/
COPY centre-control/research-map/ /app/research-map/
COPY centre-control/research-wiki/ /app/research-wiki/
COPY centre-control/buffer/ /app/buffer/
COPY centre-control/registry/ /app/registry/
COPY centre-control/email-service/ /app/email-service/
COPY centre-control/coordinator/ /app/coordinator/
COPY centre-control/dashboard-api/ /app/dashboard-api/
COPY centre-control/centre-agents/ /app/centre-agents/

# 每个目录是独立项目、各带自己的 uv.lock，因此逐个 sync；虚拟环境放在项目目录
# 之外（/opt/venvs/<项目>），这样 12 个角色的 PATH 不会互相遮蔽。
RUN set -eu; \
    for project in research-map research-wiki buffer registry email-service coordinator dashboard-api; do \
        echo "== uv sync ${project}"; \
        UV_PROJECT_ENVIRONMENT="/opt/venvs/${project}" \
            uv sync --project "/app/${project}" --locked --no-dev --no-progress; \
    done; \
    echo "== uv sync centre-agents (uv workspace)"; \
    UV_PROJECT_ENVIRONMENT=/opt/venvs/centre-agents \
        uv sync --project /app/centre-agents --locked --no-dev --no-progress

# supervisord 是唯一的进程管理者：需要一个能在容器里自启、能重启单进程、能汇
# 聚日志的监督器。装完仍用系统 Python，不额外引虚拟环境。
ARG SUPERVISOR_VERSION=>=4.3,<5
RUN pip install --no-cache-dir "supervisor${SUPERVISOR_VERSION}"

RUN rm -f /usr/local/bin/uv /usr/local/bin/uvx \
    && rm -rf /root/.cache/uv /root/.cache/pip

COPY --from=web-ui /build/dist /app/web-ui/dist
COPY centre-stack/supervisord.conf /etc/supervisord.conf
COPY centre-stack/scripts/serve_web_ui.py /opt/centre/bin/serve_web_ui.py
COPY centre-stack/scripts/bootstrap_terminusdb.py /opt/centre/bin/bootstrap_terminusdb.py

# 12 个角色共用一份 SQLite/会话数据目录；以非 root 身份运行。
# /data 在镜像里先建好并给出属主，Docker 初始化空具名卷时会沿用该属主。
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin sciweave \
    && install -d -o sciweave -g sciweave /data \
    && install -d -o sciweave -g sciweave \
        /data/mapping /data/wiki /data/audit /data/registry /data/email \
        /data/coordinator /data/centre-agents /data/centre-agents/worker-home \
    && chown -R sciweave:sciweave /app \
    && chmod 0755 /opt/centre/bin/serve_web_ui.py /opt/centre/bin/bootstrap_terminusdb.py

USER sciweave

# 12 个角色各自的默认端口（实际值全部来自环境变量，见 .env.example / compose.yaml）。
#   8710 research-map 管理 MCP          8711 research-map 看板来源
#   8720 research-wiki 管理 MCP         8721 research-wiki 看板来源
#   8730 buffer MCP                     8740 registry MCP
#   8750 email-service MCP              8760 centre-agents gateway MCP
#   8761 centre-agents 队列看板来源      8762 coordinator MCP
#   8702 dashboard-api                  8080 web-ui 静态站点
EXPOSE 8080 8702 8710 8711 8720 8721 8730 8740 8750 8760 8761 8762

# 容器级健康检查只看 dashboard-api：它启动时会把实际端口打印到 stdout，且不依赖
# TerminusDB 才能回 ready。单个角色的健康状态用 supervisorctl status 观察。
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
    CMD python -c "import os,sys,urllib.request; port=os.environ.get('SCIWEAVE_DASHBOARD_PORT','8702'); sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:' + port + '/health', timeout=3).status == 200 else 1)"

CMD ["/usr/local/bin/supervisord", "-c", "/etc/supervisord.conf", "-n"]
