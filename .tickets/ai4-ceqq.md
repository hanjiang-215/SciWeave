---
id: ai4-ceqq
status: open
deps: []
links: []
created: 2026-10-26T14:05:45Z
type: feature
priority: 1
assignee: hanjiang
parent: ai4-f985
tags: [email-service, notification, smtp]
---
# 接入真实 SMTP 发送端口

## 现状

`src/main.py:16` 注入的是 `UnboundMailSender()`，它的 `send()` 直接抛 `EmailServiceError("sender_unavailable")`。后台投递循环调它时被 `service.py` 的 `except EmailServiceError` 接住，记 `permanent_failure`、摘要 `sender_failure`。也就是说：**产品代码这条链路一封邮件都发不出去**，而且每一封都记成永久失败。

`ai4-m1d1` 的 Notes 里记着「用一次性脚本经真实 MCP 调用、真实 163 SMTP 投递成功，状态为 sent，**未改产品代码**」。那次成功验证了协议能通，但没有任何一行留在仓库里。全仓库（全部本地与远程分支）搜 `smtplib`、`SMTP_SSL`、`starttls` 均为 0 处。

`ai4-f985` 第 71 行把「真实 SMTP」明确排除在首版之外，第 95 行把「真实 SMTP/第三方邮件 SDK 的选型、生产凭据配置」列入 Out of Scope。**本票就是补上这条被显式推迟的工作**，不是推翻 `ai4-f985` 的规格——规格里发送端口一直是可替换的，只是那个「可替换」现在两端都是空的。

## 要做的事

1. 新增发送适配器，放在 `email-service` 自己的 `src/email_service/` 下，不建共享包（只有这一个角色用，按 `AGENTS.md` 的共享包判据不成立）。
2. `main.py` 用它替换 `UnboundMailSender`。
3. 打开发送通道的配置项与启动校验。

## 必须遵守的约束

**① 通道配置不进消息对象。** 现在 `OutboundMail` 同时装内容（`from_address` / `to_address` / `subject` / `body` / `notification_id`）和通道（`smtp_host` / `smtp_port` / `smtp_username` / `smtp_password`）。这导致 `repr(OutboundMail)` 会打印 SMTP 密码：

```
OutboundMail(..., smtp_password='SUPER-SECRET-PASSWORD')
```

现在没有日志所以没炸，但任何一次异常回溯或调试打印都会把生产邮箱密码写进日志。把通道字段从 `OutboundMail` 移除，由发送端口在构造时持有 `MailboxSettings`。理由见 [ADR-0005](../docs/adr/0005-mail-sender-error-classification.md)。

**② 加密方式显式配置，不给默认值。** 新增 `SCIWEAVE_EMAIL_SMTP_SECURITY`，取值 `ssl` / `starttls` / `none`。猜错的后果不是发不出信，而是在 `starttls()` 之前就发出 `AUTH`，把密码明文送出去。不按端口推断：本地联调端口（2525）不在映射表里，加豁免规则等于一个隐式变量。

**③ SMTP socket 超时独立配置。** 新增 `SCIWEAVE_EMAIL_SMTP_TIMEOUT_SECONDS`。`smtplib.SMTP(host, port)` 不传 `timeout` 时是永久阻塞，而投递是单线程串行（`_run` → `_deliver_one` 一条一条发），一个卡死的连接会让整条队列停住。不复用 `SCIWEAVE_EMAIL_SENDING_TIMEOUT_SECONDS`：那是「重启后一条 `sending` 记录卡多久算过期」的恢复判定。

**④ 异常按投递语义分类，不按 `isinstance` 猜。** `smtplib` 的异常继承树很怪——`SMTPException` 的基类是 `OSError`，网络错误和认证失败在类型上同源。必须显式列表：

| `smtplib` 异常 | 映射 |
| --- | --- |
| `SMTPServerDisconnected`、`SMTPConnectError`、`TimeoutError`、其余 `OSError` | `TransientSenderFailure` |
| `SMTPAuthenticationError` | `PermanentSenderFailure` |
| `SMTPRecipientsRefused` | `PermanentSenderFailure` |
| `SMTPDataError` | `PermanentSenderFailure` |
| `SMTPNotSupportedError` | `PermanentSenderFailure` |
| `SMTPSenderRefused`、`SMTPHeloError` | `PermanentSenderFailure` |
| `ValueError`（报文构造失败） | `NonRetryableContentError` |
| 未列出的 `SMTPException` | `PermanentSenderFailure` |

抽成纯函数 `classify_smtp_error(exc) -> EmailServiceError`，单测直接喂异常对象，不起 SMTP 服务器。本文与拒绝理由见 [ADR-0005](../docs/adr/0005-mail-sender-error-classification.md)。

**⑤ 报文用标准库的邮件对象构造，不手工拼 header。** 必须用 `email.message.EmailMessage`（或 `email.headerregistry`）。Python 会拒绝含 `\r` / `\n` 的 header 值，手工拼接则等于开放 SMTP 头注入。

**⑥ 每封信带稳定 `Message-ID`。** 由 `notification_id` 与收件人派生，后缀取 `from_address` 的域名（**不要写死项目名**，否则在严格 SPF/DKIM 环境下会被扣分）。SMTP 是 at-least-once，不追求恰好一次，但重复了要能被认出来是同一封信。

**⑦ `/health` 要能表达「发送端口能不能发」。** 现在 `_mailbox_state` 只看四个配置字段非空，完全不看 sender 是什么，所以存在这样的状态：`GET /health` 返回 `ready`（`mailbox: ready`），而 `send_notification` 受理后全部 `permanent_failure`。健康检查绿灯、投递 100% 失败。加一个 `sender` 分项，让「未绑定发送端口」在健康上可见；**不主动连着 SMTP 探活**，那会把健康检查变成外部依赖。

## 依赖处理

只用 Python 标准库 `smtplib` + `email`，不新增运行时依赖，因此 `pyproject.toml` 的 `dependencies` 不变，`uv.lock` 预期不变。如果实现时发现必须引入 `aiosmtplib` 等第三方包，**停下来先问我**：那是一次新的依赖选型，要走 `docs/DEPENDENCIES.md` 的登记流程，不能在实现票里顺手加。

## 本地联调

不引入 `aiosmtpd` 之类的 SMTP 测试服务依赖。标准库的 `smtpd` 模块已在 Python 3.13 移除（本机 3.13.14，`import smtpd` 报 `ModuleNotFoundError`）。单测一律注入 Fake sender，不起真实 SMTP。真实的 163 SMTP 联调由人工做一次并记录命令与结果，不写成自动化测试。

## Acceptance Criteria

- [ ] `src/email_service/` 下存在真实 SMTP 发送适配器，实现 `MailSender` 协议；`main.py` 用它替换 `UnboundMailSender`。
- [ ] `UnboundMailSender` 保留但不再出现在 `main.py`；若全仓库无引用则评估是否删除，删除需在同一提交注明。
- [ ] `OutboundMail` 只保留内容字段；`repr()` 输出不含任何凭据。有测试断言这一点。
- [ ] 三个新配置项进入 `EmailServiceConfig` 与 `.env.example`：`SCIWEAVE_EMAIL_SMTP_SECURITY`（无默认值）、`SCIWEAVE_EMAIL_SMTP_TIMEOUT_SECONDS`、保留既有四个 `SCIWEAVE_EMAIL_SMTP_*`。
- [ ] `SCIWEAVE_EMAIL_SMTP_SECURITY` 取值非法、缺失，或选 `ssl`/`starttls` 但缺少 host/port/username/password 时，启动即失败并给出明确错误；选 `none` 时允许无认证（本地明文联调）。
- [ ] `classify_smtp_error` 覆盖上表全部行，含「未列出的 `SMTPException` 落 `permanent_failure`」。
- [ ] 报文经 `EmailMessage` 构造；有测试断言 `Message-ID` 存在、由 `notification_id` 与收件人派生、后缀取自发件地址域名。
- [ ] `/health` 新增 `sender` 分项；未绑定发送端口时整体状态不报 `ready`。
- [ ] `README.md` 的「本服务不连接真实 SMTP……邮件发送端口仍使用未绑定占位」一句改写为实际行为。
- [ ] 全量 pytest 通过（现有 67 个 + 新增）；`python -m compileall -q src tests` 通过；`git diff --check` 通过。
- [ ] 人工完成一次真实 SMTP 投递（163，`smtp.163.com:465` + SSL），记录命令、耗时与 `delivery_status=sent`，回写到本票 Notes。**不要把凭据写进票里。**

## Not in Scope

- 邮件模板平台、HTML 正文、附件上传（`ai4-f985` 已排除）。
- 第三方邮件 API / SDK（SendGrid、Resend 等）。首版只用标准库 SMTP。
- 高可用、发信速率限制、退信（bounce）处理、SPF/DKIM/DMARC 配置与域名预热。
- `email-service` 的部署编排与容器化。
- 主题含 CRLF 的受理端收紧，见 `ai4-9687`。
- Registry 错误码解析，见 `ai4-dp9t`。

## Notes

**2026-10-26 立项（Frank Qi）**

身份核对：assignee `Frank Qi`、分支 `feature/frank-qi`、`git config user.name=Frank Qi`，三者一致。

出处：与用户逐条裁决后立项。用户先问「email 还差什么」，随后对七条设计选择裁决为「按你推荐的来」。裁决记录见 [ADR-0005](../docs/adr/0005-mail-sender-error-classification.md) 与 [GLOSSARY.md](../GLOSSARY.md) 的「人工通知」章节。

关于 `ai4-f985` 的 Out of Scope：第 95 行把真实 SMTP 排除在**首版**之外。本票不推翻该结论，只是 `ai4-f985` 描述的「可替换发送端口」现在两端都空，需要真的补上一端。实现完成后应在 `ai4-f985` 追加一条带日期的修订注记，说明首版延期项已落地，不改原规格正文。

一个必须说清的事实：用户提到「我之前的 email 已经可以实现发送了」。那指的是 `ai4-m1d1` 记录的一次性脚本，不是产品代码。当前产品链路仍然是 100% 记 `permanent_failure`。本票验收通过后，这句话才在代码层面成立。

**2026-10-27 转交（Frank Qi）**

> *This was generated by AI during triage.*

原负责人 Frank Qi，现负责人 hanjiang，转交时间 2026-10-27T02:54:43Z。已与 hanjiang 商定：中央控制面（`sci-weave/centre-control/**`）的缺陷与收口由他继续推进，本票属该范围。

转交前复核，正文「现状」段已过期，但本票仍未完成——一句话说清哪些已做、哪些没做，接手时不必重新考证：

**已由 `ai4-4pyb`（hanjiang，提交 `e0c1013`）落地：**
- 真实 SMTP 发送适配器 `src/email_service/smtp_sender.py::SmtpMailSender` 存在并实现 `MailSender`；`main.py` 已改装配它。**验收第 1 条已满足。**
- `UnboundMailSender` 现在全仓库只剩 `ports.py:82` 的定义：`main.py` 与 `tests/` 都不引用，只有 `smtp_sender.py` 的模块 docstring 提到它（讲历史）。按验收第 2 条的口径，这里就是「全仓库无引用、需评估删除」的状态，可以直接删。
- 报文经 `EmailMessage` 构造（约束 ⑤ 已满足），通知 id 写进 `X-SciWeave-Notification-Id` 头。
- `README.md` 里「邮件发送端口仍使用未绑定占位」那句已改写成 `SmtpMailSender` 的实际行为。**验收第 9 条已满足。**

**仍未做（本票剩余范围）：**
- `OutboundMail` 仍带 `smtp_host` / `smtp_port` / `smtp_username` / `smtp_password` 四个通道字段，`repr()` 实测仍打印明文密码（`OutboundMail(..., smtp_password='SUPER-SECRET')`）。这台票最该先做的一条，也是唯一有安全后果的一条。
- `SCIWEAVE_EMAIL_SMTP_SECURITY` 与 `SCIWEAVE_EMAIL_SMTP_TIMEOUT_SECONDS` 均未加；`config.py` 只有原有四个变量，`.env.example` 同样。
- `classify_smtp_error` 不存在；现实现是在 `send()` 里按 `except` 分支内联判断，没有表里那档「未列出的 `SMTPException` 落 permanent」的显式覆盖，`SMTPDataError` / `SMTPHeloError` / `ValueError` 也没进分类。
- `Message-ID` 未设置（全仓库 `grep Message-ID` 无命中）。
- `/health` 只有 `mailbox` 分项，没有 `sender`；`_mailbox_state` 仍只看配置字段，所以「配置齐全但发送端口异常」这种情况仍报 `ready`。
- 真实 163 SMTP 人工投递未做（`e0c1013` 的验证只有 8 条单测，没走真实服务器）。

**验收第 10 条需要重算**：原文写「现有 67 个 + 新增」，`e0c1013` 之后 email-service 已是 75 passed，接手时按实际基线改。

`ai4-4pyb` 与本票的关系：`4pyb` 修的是「产品链路一封都发不出去」，本票修的是「发出去之后仍然不安全、不可配置、不可观测」。两者不重复，本票的 Not in Scope 也没有把上面的剩余项排除出去。

正文与其余验收标准保持原样，只在上面这段说明哪些已勾。
