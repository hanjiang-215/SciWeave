---
id: ai4-8d9j
status: open
deps: []
links: [ai4-tesq, ai4-349h, ai4-k2le, ai4-8dgd]
created: 2026-10-28T01:06:41Z
type: bug
priority: 2
assignee: Frank Qi
parent: ai4-yidf
tags: [toolkit, suite, packaging, ready-for-agent]
---
# 中央套件装齐 MCP 卡片：install.sh 补齐 mcp/ 与 suite.yaml，check.sh 覆盖

中央套件里 `mcp/` 目录和 `suite.yaml` 都写好了，但 `install.sh` 的拷贝清单只有 `bin cron systemd README.md`：

```sh
for item in bin cron systemd README.md; do
```

`check.sh` 也一次都没检查过 `mcp/`（`grep -c "mcp/" check.sh` 返回 0）。

所以安装完之后目标目录里没有卡片，也没有套件清单。而卡片的消费者在仓库里（套件本体、`suitecheck`），一旦中央侧开始读卡片目录，安装不完整就会变成运行时错误而不是安装错误。

这一片很小但要紧：安装脚本把卡片目录与套件清单一起拷进去，自检把它们算进「就绪」判定。设计规格里定的原则是「文件在仓库里、装完就没有」这类失败必须由自检挡住。

## Acceptance Criteria

- [ ] `install.sh` 把 `mcp/` 与 `suite.yaml` 拷进目标目录
- [ ] `check.sh` 在卡片目录或套件清单缺失时返回「不完整」（退出码 1），不是「已装但不可用」
- [ ] `check.sh` 对五张卡片逐一检查，缺一张就报出来
- [ ] 有测试断言安装脚本的拷贝清单包含这两项（先例：套件的 `test_installation.py`）
- [ ] `suitecheck` 仍能对三个套件一起通过

