---
name: researcher-install-suite
description: 把一个套件 zip 装到研究员自己的机器上，并让它真的能用。
---

# 装套件

你是研究员自己的 Personal Agent。你手上有一个套件目录（或它的 zip）。按下面三步走，
每步结束都要能给研究员一句可核对的结论。

## 1. 先校验，再执行任何命令

```bash
python -m suitecheck.cli check <套件目录>
```

`check` 只读文件，不执行 manifest 里的任何命令。它会告诉你：`suite.yaml` 的字段是否闭合、
每个 `SKILL.md` 是否有 frontmatter、MCP 卡片是否存在且 `name` 对得上、hook 是否有可执行位、
以及 **声明的能力有没有超过这个套件角色的上限**。

能力越界是硬错误，不是风格问题。看到 `capability_over_ceiling` 就停下，回报研究员，
不要自己把 `suite.yaml` 里的能力删掉凑通过——那等于替他改了一个他没同意的授权。

## 2. 看清它要什么，再装

读 `requires.env` 与 `requires.services`。`researcher-agent-toolkit` 需要：

- `SCIWEAVE_AGENT_ID` 与 `SCIWEAVE_SUBSCRIBER_TOPICS`：决定订阅哪条交接 topic；
- `DRAFT_BUFFER_MCP_URL` / `_TOKEN`、`RESEARCH_MAPPING_MCP_URL` / `_TOKEN`、
  `LLM_WIKI_MCP_URL` / `_TOKEN`、`EMAIL_MCP_URL` / `_TOKEN`：四类中央服务的地址与令牌；
- `SCIWEAVE_REGISTRY_URL` / `_TOKEN`：注册表，用来把自己的 Task Agent 与实例登记上去；
- `DISPOSITION_MCP_URL` / `_TOKEN`：本机处置面。

变量只写名字，值来自研究员本机的 `.env`。你**不写**任何令牌到仓库、日志或对话里。

## 3. 执行安装

```bash
python -m suitecheck.cli run install <套件目录> --dry-run   # 先看它到底要跑什么
python -m suitecheck.cli run install <套件目录>
```

`deploy-task-agent/install.sh` 会把运行时、服务模板、libs、技能和 systemd 单元复制到
`${SCIWEAVE_TASK_AGENT_HOME:-$HOME/.sciweave/task-agent}`，装好运行时依赖，然后把两个
user 服务注册上，**但不 enable**——第一步是让研究员填 `.env`。

装完跑 `check`：

```bash
python -m suitecheck.cli run check <套件目录>
```

## 不该做的事

- 不要为了「装得上」去改 `runtime/`、Worker Lease、Gateway 或 `systemd/` 单元；
  那些属于套件维护者。你能改的只有 Agent 定义、工作流声明、MCP 资源和 `.env`。
- 不要手工 `systemctl enable --now` 另一个人的服务，也不要替研究员决定 `SCIWEAVE_AGENT_ID`。
- 不要在 harness 打开时启停常驻服务之外的东西：`hooks/check-services.sh` 只补启动缺的
  两个服务，关闭 harness 不停它们。

装完把结果交给 `researcher-register-instance`——没在注册表里登记成 `online` 的 Task Agent，
交接协调服务不会把任务投给它。
