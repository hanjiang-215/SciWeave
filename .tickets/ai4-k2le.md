---
id: ai4-k2le
status: open
deps: [ai4-tesq]
links: [ai4-349h, ai4-tesq, ai4-8d9j, ai4-8dgd]
created: 2026-10-28T01:06:37Z
type: feature
priority: 2
assignee: Frank Qi
parent: ai4-yidf
tags: [centre-control, centre-agents, agent, ready-for-agent]
---
# 预审 Agent 定义从 YAML 加载：指令不再硬编码

中央 Worker 的预审指令是硬编码在 Python 里的一行字符串：`You are a SciWeave Task Agent Worker. Complete the owner's command concisely.`——这句话既没说预审，也没说不能批准候选。

套件侧已经把这件事做成了可加载的定义（`agent-definitions/agents/*.yaml`，字段 `identity` / `instruction` / `model` / `allowed_mcp_resources` / `resources`），并由 `assembly.py` 严格加载：目录缺失或定义无效就抛错，不回退到内置 Agent。

中央侧只需要其中一小部分：读一份 YAML、校验 `allowed_mcp_resources` 都在注册表里、把 instruction 与 model 交给运行时。不做套件那套四根目录、本地覆盖、未知资源覆盖的完整机制。

指令里必须写明能力边界：只能读候选、只能追加预审日志、不得批准任何候选。这一条不能只靠卡片收窄保证，因为模型会看到工具描述。

规格见 `docs/superpowers/specs/2026-10-28-centre-agent-runtime-template-port-design.md`。

## Acceptance Criteria

- [ ] 存在一份中央预审 Agent 定义 YAML，含 `identity` / `instruction` / `model` / `allowed_mcp_resources`
- [ ] 指令明确写出「只读候选、只追加预审日志、不得批准」，不是一句通用的「完成任务」
- [ ] 定义目录缺失或定义无效时硬失败，不回退到内置指令
- [ ] 声明的 `allowed_mcp_resources` 不在卡片目录里时硬失败
- [ ] 改 YAML 里的 instruction 能改变框架收到的指令，有测试钉住这一点
- [ ] `model` 来自定义而不是环境变量里另写一份，避免两处真相

