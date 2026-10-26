---
id: ai4-8pvm
status: closed
deps: []
links: [ai4-3zxu, ai4-te1v]
created: 2026-10-26T08:21:15Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-3zxu
tags: [implementation, centre-control, shared, message-queue, ready-for-agent]
---
# 信封核心与 JSON 编解码

## What to build

让中央各服务能构造一个统一信封、编成字节、再解回来，并且在校验失败时能分清是哪一类失败。这是 `shared/message-envelope/` 的第一层：只有信封本身，载荷还是自由字典。

规格见 [`2026-10-26-message-envelope-protocol-package-design.md`](../docs/superpowers/specs/2026-10-26-message-envelope-protocol-package-design.md)。

## Acceptance Criteria

- [x] 新建 `sci-weave/centre-control/shared/message-envelope/`，含 `pyproject.toml`、`src/`、`tests/`、`README.md`。
- [x] 信封含 `message_id`、`message_type`、`schema_version`、`dedupe_key`、`occurred_at`、`published_at`、`producer`、`routing`、`payload` 九个字段。
- [x] 提供信封构造、JSON（UTF-8）序列化、反序列化与校验的公开接口。
- [x] 四类失败可区分：格式非法、`schema_version` 不支持、`message_type` 未知、载荷非法。不得合并成单一异常。
- [x] 反序列化遇未知 payload 字段不报错；序列化→反序列化→再序列化后未知字段不丢失。
- [x] `occurred_at` 与 `published_at` 各自独立校验为合法时间，缺失或格式非法时报格式错误。
- [x] 包内不出现任何 Kafka 客户端导入，用导入检查断言这一点。
- [x] 单元测试覆盖：正常往返、未知字段容忍、版本不匹配、必填字段缺失、时间格式非法、未知消息类型。
- [x] `README.md` 写明用途、公开接口、验证命令与「纯协议包、不含客户端」的边界。
- [x] 在 fer 记录验证命令、结果和提交哈希。

## Verification

- 提交：`a8f5c6e feat(shared): add the message envelope protocol package`
- 命令：`cd sci-weave/centre-control/shared/message-envelope && UV_CACHE_DIR=/tmp/uvcache uv run --extra test pytest -q`
- 结果：`17 passed in 0.02s`
- 编译检查：`uv run python -m compileall -q src tests` → 通过
- 边界断言：`tests/test_no_kafka.py` 用 AST 扫描包内全部 `.py`，确认无 `confluent_kafka` / `kafka` / `aiokafka` 导入，且无 `socket` / `threading` / `subprocess`。

### 与父票 AC 的一处出入

`ai4-3zxu` 第 50 行写「包实现与 `pyproject.toml`，无锁文件」，本票提交了包内 `uv.lock`。依据是同目录的 `shared/audit-trail/` 已提交自己的 `uv.lock`，而 `docs/TECH_STACK.md` 禁止的是 `sci-weave/centre-control/` 这一级的**组级**锁文件（该文件确实不存在）。包内锁文件属于包自身，不构成组级清单。若父票要按字面执行，删除该文件即可，不影响任何测试。

## Notes

- 载荷在本票里是自由字典，不做类型化。类型化由 `ai4-sv1u` 承接。
- 锁文件：提交了包内 `uv.lock`。`docs/TECH_STACK.md` 禁止的是 `sci-weave/centre-control/` 这一级的组级锁文件，包自身的锁文件不在禁止范围内；`shared/audit-trail/` 已有同样的既有事实。
- 顺序：先跑通「一个信封往返」再扩校验。四类错误区分的价值在于消费方处置不同，不在于分类本身好看。
