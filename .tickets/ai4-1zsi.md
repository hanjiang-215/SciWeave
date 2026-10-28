---
id: ai4-1zsi
status: closed
deps: []
links: []
created: 2026-10-28T15:53:31Z
type: chore
priority: 2
assignee: Frank Qi
tags: [dependencies, uv, mirror]
---
# 将所有 uv.lock 包索引源统一为清华镜像

将仓库内 Git 跟踪的 uv.lock 中 PyPI simple 与 artifact URL 统一切换为清华镜像，保留版本、哈希和依赖解析结果。

## Design

仅替换 registry、sdist、wheel URL 的源 host/path，不重新解析依赖；临时目录和未跟踪锁文件不作为仓库交付。

## Acceptance Criteria

所有跟踪的 uv.lock 不再引用 pypi.org/simple 或 files.pythonhosted.org；registry 使用 mirrors.tuna.tsinghua.edu.cn/pypi/web/simple，artifact 使用 mirrors.tuna.tsinghua.edu.cn/pypi/web/packages；版本和 hashes 不变；uv lock --check 或等价验证通过；创建目标为 develop 的 Gitee PR。

## Notes

**2026-10-28**

已将 5 个含 PyPI URL 的跟踪锁文件切换到清华镜像；其余跟踪锁文件本身已使用清华源或只有本地/editable 依赖。所有 14 个跟踪 `uv.lock` 均完成源检查，13 个含可解析项目的锁文件通过 `uv --cache-dir /tmp/uv-cache lock --check`，未改版本、哈希或依赖解析结果。
