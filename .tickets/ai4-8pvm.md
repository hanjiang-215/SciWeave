---
id: ai4-8pvm
status: open
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

- [ ] 新建 `sci-weave/centre-control/shared/message-envelope/`，含 `pyproject.toml`、`src/`、`tests/`、`README.md`。
- [ ] 信封含 `message_id`、`message_type`、`schema_version`、`dedupe_key`、`occurred_at`、`published_at`、`producer`、`routing`、`payload` 九个字段。
- [ ] 提供信封构造、JSON（UTF-8）序列化、反序列化与校验的公开接口。
- [ ] 四类失败可区分：格式非法、`schema_version` 不支持、`message_type` 未知、载荷非法。不得合并成单一异常。
- [ ] 反序列化遇未知 payload 字段不报错；序列化→反序列化→再序列化后未知字段不丢失。
- [ ] `occurred_at` 与 `published_at` 各自独立校验为合法时间，缺失或格式非法时报格式错误。
- [ ] 包内不出现任何 Kafka 客户端导入，用导入检查断言这一点。
- [ ] 单元测试覆盖：正常往返、未知字段容忍、版本不匹配、必填字段缺失、时间格式非法、未知消息类型。
- [ ] `README.md` 写明用途、公开接口、验证命令与「纯协议包、不含客户端」的边界。
- [ ] 在 fer 记录验证命令、结果和提交哈希。

## Notes

- 载荷在本票里是自由字典，不做类型化。类型化由 `ai4-sv1u` 承接。
- 不提交锁文件：`shared/` 是代码归属边界，不是项目组，按 `docs/TECH_STACK.md` 由各调用方各自提交。参考 `shared/audit-trail/`，它提交了 `uv.lock`——那是既有事实，本票与之保持一致即可。
- 顺序：先跑通「一个信封往返」再扩校验。四类错误区分的价值在于消费方处置不同，不在于分类本身好看。
