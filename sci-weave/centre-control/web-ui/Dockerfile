# web-ui 镜像：跑 Vite dev server，而不是把 dist 烤进镜像。
#
# 原因：VITE_DASHBOARD_API_URL 是 Vite 的构建期变量。用 dev server 时它可以在
# 运行时由编排层注入，同一个镜像能指向不同 dashboard-api；烤进 dist 就得为每个
# 环境重新构建。
# 基础镜像可通过 ARG 覆盖：受限网络下用镜像代理构建属于环境配置，不该写进仓库。
ARG NODE_IMAGE=node:22-slim
FROM ${NODE_IMAGE}

ENV PNPM_HOME=/pnpm \
    PATH=/pnpm:$PATH

RUN npm install -g pnpm@10

WORKDIR /app

# 先装依赖，源码变更时不必重装。
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .

EXPOSE 5173

CMD ["pnpm", "exec", "vite", "--host", "0.0.0.0", "--port", "5173", "--strictPort"]
