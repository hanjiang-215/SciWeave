# Windows 支持边界

本文按**能力**逐项说明 Windows 上的状态，不以“存在 `.cmd` 文件”作为端到端支持的证明。三分类固定为：**已验证**（本仓库有可重复的验证命令与结果）、**未验证**（有实现但未在本机 Windows 上实测）、**暂不支持**（明确不做或不可用）。

本机验证环境为 Linux；下列“未验证”项需要在 Windows 主机上执行给出的命令后才可升级为“已验证”。

## 已验证

| 能力 | 证据 |
| --- | --- |
| 清单解析（Python） | `suitecheck` 纯 Python，无平台分支；`tests/test_manifest_schema_v1.py` 在 CI 与 Linux 上均通过 |
| 路径含空格的导出 | `tests/test_exporter.py::test_export_escapes_paths_that_contain_spaces` 一类路径断言；导出目录用 `pathlib`，无 shell 拼接 |
| 无凭据输出 | `tests/test_exporter.py` 覆盖“发布文件含真实值即拒绝”和“占位符不误报” |
| 导出目录位置校验 | `validate.py::_export_findings` 拒绝越界与未覆盖载荷 |

复现命令（两平台通用）：

```bash
python -m unittest discover -s sci-weave/toolkits/suitecheck/tests -q
```

## 未验证

| 能力 | 当前实现 | 在 Windows 上需要执行 |
| --- | --- | --- |
| Project Owner / Researcher 的 Harness 输入导出 | Python 导出器，Windows 上应可声明 `supported` | 在 Windows 上跑上节命令；确认含空格路径的项目目录 |
| SciencePal `.cmd` 成功/失败退出码 | `custom-mcp/sciencepal-bridge/bin/sciencepal.cmd` 透传 `ERRORLEVEL` | 在 cmd/PowerShell 中以成功与失败参数各跑一次，核对 `%ERRORLEVEL%` |
| SciencePal `.cmd` 路径含空格 | 脚本对 `%~dp0` 加引号后 `pushd` | 部署到含空格目录后重跑上一条 |

## 暂不支持

| 能力 | 原因 |
| --- | --- |
| Task Agent 后台服务 / 自动重启 / harness hook | 首期只承诺 Linux `systemd --user`；Windows 无对应项目绑定服务实例 |
| 自动写入 `.env`、注册或启动服务 | 需要用户显式确认与 Harness 授权，套件不代为执行副作用 |

## 对 Harness 的要求

Harness 自行注册 Skills 与 MCP 卡片；套件不写 `.dsh`、`.cursor`、全局 MCP 注册或用户级 Skill 配置。若 Harness 不能执行副作用，套件只输出人工步骤，绝不把未验证的能力报告为“已安装”。
