# 邮件发送端口按投递语义分类异常，SMTP 连接超时独立配置

`email-service` 的发送端口只有三种语义：`TransientSenderFailure`（进 `retryable`，会重发）、`PermanentSenderFailure`（进 `permanent_failure`，不重发）、`NonRetryableContentError`。真实 SMTP 适配器必须把 `smtplib` 的异常映射进这三类，而 `smtplib` 的继承树以 `OSError` 为基类——网络错误和认证失败在类型上同源，不能靠 `isinstance` 猜，只能显式列表。同时 SMTP 连接的 socket 超时必须独立配置，不能复用投递记录过期阈值。

## Status

accepted（2026-10-26）

## Considered Options

1. **全部映射成 `TransientSenderFailure`，让重试兜底**（否决）：错误密码（535）和无效收件人不会自愈，重试只会把发件箱推进服务商的黑名单，并把一封注定失败的信重复投递到 `max_attempts`。否决理由：把不可恢复的错误声明成可恢复，是让系统主动制造垃圾流量。
2. **只分两类：`OSError` 系→Transient，其余全 Permanent**（否决）：这个分法看着省事，但 `smtplib.SMTPException` 的基类就是 `OSError`，`except OSError` 会把 `SMTPAuthenticationError`（535 密码错）一起当成网络抖动去重试。要把认证失败摘出来，就必须显式枚举，枚举出来之后「只分两类」就退化成了一张更短的显式表；而更短的表的唯一实际差别，是把报文构造的 `ValueError` 也压进 `PermanentSenderFailure`，让「内容非法」和「发信服务坏了」共用一个摘要。否决理由：省下的不是复杂度，是错误信息的可读性。
3. **按端口推断加密方式（465→SSL，587→STARTTLS）**（否决）：本地联调端口（如 2525）不在映射表里，得再加豁免规则，最终等于一个隐式变量。而且猜错的后果不是发不出信，是在 `starttls()` 之前就发出 `AUTH`，把密码明文送出。
4. **复用 `SCIWEAVE_EMAIL_SENDING_TIMEOUT_SECONDS` 作为 socket 超时**（否决）：该值现在的语义是「重启后一条 `sending` 记录卡多久算过期」，属恢复判定；socket 超时是「一次投递尝试最多阻塞多久」。复用的后果是：为了让重启容忍度变松而调大过期阈值，顺手把 socket 阻塞上限也调大了。

## Consequences

- 映射表写在 `smtplib` 适配器里，抽成纯函数 `classify_smtp_error(exc) -> EmailServiceError`，单测直接喂异常对象，不起 SMTP 服务器。未列出的 `smtplib.SMTPException` 一律 `PermanentSenderFailure`：不猜可恢复性，与 [ai4-v8r8](../../.tickets/ai4-v8r8.md) 既定原则一致。
- 新增 `SCIWEAVE_EMAIL_SMTP_SECURITY`（`ssl` / `starttls` / `none`）和 `SCIWEAVE_EMAIL_SMTP_TIMEOUT_SECONDS`，都无默认值或取显式默认，缺失即启动失败。加密方式不给默认值的理由是：默认值一旦错，凭据泄露不可逆。
- 报文必须用 `email.message.EmailMessage` 或 `email.headerregistry` 构造，**不得手工拼接 header 字符串**。Python 的邮件库会拒绝含 `\r`/`\n` 的 header 值（`ValueError`），手工拼接则等于开放 SMTP 头注入。该 `ValueError` 映射为 `NonRetryableContentError`。
- `OutboundMail` 不再携带 `smtp_host` / `smtp_port` / `smtp_username` / `smtp_password`。通道配置由发送端口在构造时持有，消息对象只表达「这封信写给谁、写了什么」。理由是同一封信换一台 SMTP 重发，内容没变；把密码放进每一封信的 dataclass，任何一次 `repr` 或异常回溯都会把它写进日志。
- 投递是 at-least-once，不追求恰好一次。每封信带一个由 `notification_id` 与收件人派生的稳定 `Message-ID`，后缀取发件地址的域名而不是写死项目名，避免在严格 SPF/DKIM 环境里被扣分。
