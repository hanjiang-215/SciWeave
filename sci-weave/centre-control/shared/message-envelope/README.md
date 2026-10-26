# SciWeave message-envelope

`message_envelope` 是中央服务共用的消息信封协议包。它只做 schema 定义、JSON 编解码、信封构造与校验。

**它不持有 Kafka 客户端、不建连接、不起消费者、不含重试循环。** 各角色自行接入 `confluent-kafka`，只把构造好的字节交给客户端。这条边界由 `tests/test_no_kafka.py` 断言。

## 使用

```python
from message_envelope import Envelope, Producer, Routing, decode, encode

envelope = Envelope(
    message_id="msg-1",
    message_type="task_completed",
    schema_version=1,
    dedupe_key="map-1:T1:v1:task_completed",
    occurred_at="2026-10-26T08:00:00Z",
    published_at="2026-10-26T08:00:01Z",
    producer=Producer(service="coordinator", instance_id="c-1"),
    routing=Routing(partition_key="task:T1"),
    payload={"mapping_domain_id": "map-1"},
)

body = encode(envelope)      # 校验后编成 UTF-8 JSON 字节
same = decode(body)          # 解回来并再校验一次
```

`encode` 也做校验，所以生产方在构造时就能发现漏字段，而不是等消费方解析失败。

## 公开接口

| 名称 | 类型 | 用途 |
| --- | --- | --- |
| `Envelope` | dataclass | 统一信封本体，九个字段 |
| `Producer` | dataclass | `service` 必填，`instance_id` 可选 |
| `Routing` | dataclass | `partition_key` 必填，`target_agent_id` 可选 |
| `encode(envelope) -> bytes` | 函数 | 校验后编成 UTF-8 JSON |
| `decode(data) -> Envelope` | 函数 | 解成信封并再校验一次 |
| `validate(envelope) -> None` | 函数 | 只校验已在内存里的信封，非法时抛具体异常 |
| `SCHEMA_VERSION` | 常量 | 当前支持的版本，值为 `1` |
| `MESSAGE_TYPES` | 常量 | 本包认识的消息类型集合 |
| `EnvelopeError` | 异常基类 | 统一兜底时捕它 |
| `EnvelopeFormatError` / `SchemaVersionError` / `UnknownMessageTypeError` / `PayloadError` | 异常 | 四类失败，见下节 |

`decode` 会拒绝三种结构性问题：字节不是 UTF-8 JSON、顶层不是对象、缺 `payload` 键。缺键报格式错误而不是当成空载荷——每种消息类型都有必填载荷字段，缺失的信封不可能是合法的。显式写 `{}` 则照常接受。

## 四类失败

失败被刻意分开，因为消费方对它们的处置不同：

| 异常 | 含义 | 处置 |
| --- | --- | --- |
| `EnvelopeFormatError` | 字节不是可用信封 | 永久错误，生产方坏了 |
| `SchemaVersionError` | 声明了本代码不认识的版本 | 可能是发布方先上线，考虑升级 |
| `UnknownMessageTypeError` | 消息类型无处理器 | 可能是新生产者上线 |
| `PayloadError` | 信封正常，业务载荷不合法 | 生产方 bug |

四者都继承 `EnvelopeError`，需要统一兜底时捕它。合成一个异常会丢掉消费方唯一能用来判断处置的信息。

## 版本兼容

`schema_version` 是**整数精确匹配**，首版为 `1`，不存在次版本号。

兼容策略是容忍式读取：

- 同版本一律可消费；
- 消费方**必须忽略** payload 中的未知字段；
- 新增字段必须可选并声明文档化默认值；
- 已有字段名**不得改变用途**；
- 只有删除字段、改变字段语义或改变必填性，才升版本。

后两条读不出来，只能守。容忍式读取看不出同名不同义，而这类改动比新增字段危险得多。

## 时间字段

`occurred_at` 与 `published_at` 分离：补偿重发时前者保持原事件时点，后者记录这次实际发出。两者都必须是带时区的 ISO-8601；无时区的时间无法与另一个排序，而排序是这两个字段唯一的用途。

## 载荷

本包只校验信封本身，载荷按 `message_type` 结构化由后续票承接。「未知 payload 字段一律容忍」现在就是契约，不会因为载荷类型化而改变——类型化只约束必填项，不约束多余项。

## 运行测试

```bash
uv run --extra test pytest
```

## 边界提醒

`shared/` 是代码归属边界，不是项目组。按 `docs/TECH_STACK.md`，它不产生组级 `pyproject.toml` 或组级锁文件，各调用方各自提交自己的锁文件。
