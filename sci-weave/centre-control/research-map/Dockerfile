# research-map 看板来源镜像。
#
# 构建上下文必须是 sci-weave/centre-control（不是本目录）：research-map 通过
# [tool.uv.sources] 依赖 ../shared/audit-trail，uv 需要那条相对路径存在。
#   docker build -f research-map/Dockerfile -t sciweave/research-map ..
# 基础镜像可通过 ARG 覆盖：受限网络下用镜像代理构建属于环境配置，不该写进仓库。
ARG PYTHON_IMAGE=python:3.13-slim
FROM ${PYTHON_IMAGE}

COPY --from=ghcr.io/astral-sh/uv:0.10.7 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 先放依赖清单并同步，让依赖层在源码变更时仍然命中缓存。
COPY shared/audit-trail /app/shared/audit-trail
COPY research-map/pyproject.toml research-map/uv.lock /app/research-map/
WORKDIR /app/research-map
RUN uv sync --locked --no-dev --no-install-project

COPY research-map/src /app/research-map/src
RUN uv sync --locked --no-dev

ENV PATH="/app/research-map/.venv/bin:$PATH"

# 默认以看板来源模式运行；MCP 模式由编排层覆盖 command 即可。
ENV SCIWEAVE_MAPPING_DASHBOARD_MODE=1
EXPOSE 8701

CMD ["python", "src/main.py"]
