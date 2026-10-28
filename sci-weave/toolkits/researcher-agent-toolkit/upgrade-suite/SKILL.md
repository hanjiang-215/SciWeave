---
name: researcher-upgrade-suite
description: 把套件升到新版本，保留研究员的 .env、工作目录和数据库，并在升级前后核对边界。
---

# 升级套件

升级和研究员的配置是两件事，升级脚本必须让这个区分成立：**代码换掉，`.env`、
`WORKER_HOME`、SQLite、Agent 定义与本地技能不换。**

## 升级前

1. 记下现在跑的是什么：

   ```bash
   cat "$SCIWEAVE_TASK_AGENT_HOME/.env" | grep -E '^(SCIWEAVE_AGENT_ID|SCIWEAVE_SUBSCRIBER_TOPICS)='
   systemctl --user is-active sciweave-task-agent-mcp.service sciweave-task-agent-subscriber.service
   ```

2. 看新版本声明的边界有没有变宽：

   ```bash
   python -m suitecheck.cli check <新套件目录>
   ```

   关注 `capability_over_ceiling`：如果新版本声明的能力超过了 `researcher` 的上限，
   那不是「新版本更强」，那是有人在卡片里放进了他不该有的工具。停下来问。

3. 看 `requires.env` 有没有新增项。新增项意味着 `.env` 要补，而 `install.sh` 不会替你补
   ——它只在 `.env` 不存在时才从 `.env.example` 复制。

## 升级

```bash
python -m suitecheck.cli run install <新套件目录> --dry-run   # 看它要做什么
python -m suitecheck.cli run install <新套件目录>
```

`deploy-task-agent/install.sh` 逐项 `rm -rf` 再 `cp -R`，所以它天然会覆盖代码；
它明确**不**覆盖已存在的 `.env`。这就是为什么升级是安全的——但它也意味着：

- 逐个文件改过的本地改动会被覆盖。研究员的本地改动应该放在 `LOCAL_*` 目录里
  （`LOCAL_AGENT_DEFINITIONS_PATH`、`LOCAL_MCP_LIBS`、`LOCAL_WORKFLOW_LIBS_PATH`、
  `LOCAL_SKILLS_PATH`），而不是直接改 `agent-definitions/` 与 `libs/`。
- `systemd` 单元会用新文件重写，然后 `daemon-reload`；服务不会自动重启。

## 升级后

```bash
python -m suitecheck.cli run check <新套件目录>
systemctl --user restart sciweave-task-agent-mcp.service sciweave-task-agent-subscriber.service
```

再跑一次 `researcher-register-instance` 的 `online`，否则新进程的实例状态还是旧的。

## 回滚

套件不保留旧版本副本——回滚靠 Git，不靠安装目录里的 `backup/`。所以升级前确认这个套件
目录本身在一个可回退的版本里（仓库 checkout 或打好的 zip）。装完发现不对，回到旧目录重装即可；
`.env` 与数据库没被动过，重装不会丢失历史。
