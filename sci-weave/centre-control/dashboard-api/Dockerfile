# dashboard-api 镜像。构建上下文为 sci-weave/centre-control。
#   docker build -f dashboard-api/Dockerfile -t sciweave/dashboard-api ..
# 基础镜像可通过 ARG 覆盖：受限网络下用镜像代理构建属于环境配置，不该写进仓库。
ARG PYTHON_IMAGE=python:3.13-slim
FROM ${PYTHON_IMAGE}

COPY --from=ghcr.io/astral-sh/uv:0.10.7 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY dashboard-api/pyproject.toml dashboard-api/uv.lock /app/dashboard-api/
WORKDIR /app/dashboard-api
RUN uv sync --locked --no-dev --no-install-project

COPY dashboard-api/src /app/dashboard-api/src
RUN uv sync --locked --no-dev

ENV PATH="/app/dashboard-api/.venv/bin:$PATH"
EXPOSE 8702

CMD ["python", "src/main.py"]
