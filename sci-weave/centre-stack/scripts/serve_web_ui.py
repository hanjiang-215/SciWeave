"""静态托管 web-ui 构建产物，供单容器部署直接使用。

这是部署胶水，不是产品源码：`sci-weave/centre-control/web-ui` 的产品代码仍然
只有 Vue 前端本身。镜像里不装 Node 运行时，所以不能跑 `vite preview`；这里用
标准库做三件事：

1. 按扩展名回 Content-Type；
2. 未命中的非资源路径回退到 `index.html`——Vue Router 用 `createWebHistory`，
   `/knowledge`、`/tasks/<id>` 这类深链接必须由入口页接管；
3. `GET /health` 回就绪状态，供容器健康检查使用。

监听地址与端口只从环境变量读：
`SCIWEAVE_WEB_UI_STATIC_HOST`、`SCIWEAVE_WEB_UI_STATIC_PORT`、
`SCIWEAVE_WEB_UI_STATIC_ROOT`。
"""

from __future__ import annotations

import json
import mimetypes
import os
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

INDEX_FILE = "index.html"
API_VERSION = "web-ui-static-v1"

# 前端产物必须回准确的 Content-Type：浏览器对 <script type="module"> 做严格
# MIME 校验，回 text/plain 会直接拒绝执行。这里不依赖宿主机的 mime 数据库
# （Windows 上 .js 会被注册表映射成 text/plain）。
_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".map": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".txt": "text/plain; charset=utf-8",
}


def content_type_for(path: Path) -> str:
    return _CONTENT_TYPES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"

HOST_ENV = "SCIWEAVE_WEB_UI_STATIC_HOST"
PORT_ENV = "SCIWEAVE_WEB_UI_STATIC_PORT"
ROOT_ENV = "SCIWEAVE_WEB_UI_STATIC_ROOT"


def resolve_asset(root: Path, request_path: str) -> Path | None:
    """把请求路径映射到 root 下的文件；越界或不存在返回 None。"""
    path = unquote(urlsplit(request_path).path)
    if path in ("", "/"):
        return root / INDEX_FILE
    target = (root / path.lstrip("/")).resolve()
    # 目录穿越一律拒绝：只允许 root 本身及其子孙。
    if target != root and root not in target.parents:
        return None
    if target.is_dir():
        target = target / INDEX_FILE
    return target if target.is_file() else None


def is_asset_request(request_path: str) -> bool:
    """带扩展名的请求按静态资源对待，不再回退到入口页。

    没有这条区分，`/assets/app.js` 写错路径时会返回一份 200 的 HTML，
    浏览器报的是语法错误而不是 404。
    """
    path = urlsplit(request_path).path
    return Path(path).suffix != ""


class WebUiStaticServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], root: Path) -> None:
        super().__init__(address, WebUiStaticHandler)
        self.root = root


class WebUiStaticHandler(BaseHTTPRequestHandler):
    server_version = "SciWeaveWebUiStatic/1"
    server: WebUiStaticServer

    def _send_bytes(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_bytes(status, body, "application/json; charset=utf-8")

    def _send_file(self, path: Path) -> None:
        try:
            body = path.read_bytes()
        except OSError:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        self._send_bytes(HTTPStatus.OK, body, content_type_for(path))

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler 的固定名字
        path = urlsplit(self.path).path
        if path == "/health":
            self._send_json(
                HTTPStatus.OK,
                {"status": "ready", "service": "sciweave-web-ui-static", "api_version": API_VERSION},
            )
            return
        asset = resolve_asset(self.server.root, self.path)
        if asset is not None:
            self._send_file(asset)
            return
        if is_asset_request(self.path):
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        index = self.server.root / INDEX_FILE
        if not index.is_file():
            self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "index_missing"})
            return
        self._send_file(index)

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        # 统一走 stdout，由 supervisord 收集；带服务名前缀便于在合并日志里定位。
        sys.stdout.write(f"web-ui-static {self.address_string()} {format % args}\n")
        sys.stdout.flush()


def main() -> int:
    host = os.environ.get(HOST_ENV, "").strip()
    port_text = os.environ.get(PORT_ENV, "").strip()
    root_text = os.environ.get(ROOT_ENV, "").strip()
    missing = [name for name, value in ((HOST_ENV, host), (PORT_ENV, port_text), (ROOT_ENV, root_text)) if not value]
    if missing:
        print(f"missing required environment: {', '.join(missing)}", file=sys.stderr)
        return 2
    root = Path(root_text).resolve()
    if not (root / INDEX_FILE).is_file():
        print(f"{root} does not contain {INDEX_FILE}", file=sys.stderr)
        return 2
    server = WebUiStaticServer((host, int(port_text)), root)
    print(
        json.dumps(
            {"status": "ready", "service": "sciweave-web-ui-static", "host": host, "port": server.server_address[1]},
            ensure_ascii=False,
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
