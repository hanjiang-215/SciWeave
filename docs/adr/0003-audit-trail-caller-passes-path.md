# 调用账本共享包不读环境变量，路径由调用方传入

`sci-weave/centre-control/shared/audit-trail` 是被中央服务调用的库，没有自己的进程。审计库路径由调用方从自己的环境变量读出后传给 `open_connection`；库内不读环境，也不提交 `.env.example`。

## Status

accepted（2026-10-23）

## Considered Options

1. **库自己读 `SCIWEAVE_AUDIT_SQLITE_PATH`**（否决）：缺路径时从进程环境取值，超时和日志模式也各设环境变量。否决理由：库没有部署单元，不该绑死变量名；同一进程也无法不改环境就打开另一个库。
2. **调用方传入路径**（采纳）：`open_connection(path, *, busy_timeout_ms=5000, journal_mode="WAL")` 的路径必填。各接入方在自己的 `.env.example` 声明 `SCIWEAVE_AUDIT_SQLITE_PATH`。各中央服务传入同一路径才是一份账本，这是部署约定，包不强制。

## Consequences

- 「路径必须来自环境变量」仍约束会启动的进程，不约束这个库。看到库里没有 `os.environ` 不是漏做。
- 进程启动时打开一次连接并建表，之后复用；库不加锁，保持 SQLite 默认的同线程检查，并发由调用方在包外串行化。
- 打开或建表失败时库抛 `AuditUnavailableError`，不自己退出进程。调用方在开始对外服务之前完成这两步，任一步失败则不起服务。运行中的单次失败仍按调用阶段处理：写调用失败则业务不执行，读调用失败只告警。
