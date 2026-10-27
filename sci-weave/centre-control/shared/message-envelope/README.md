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
    payload={
        "mapping_domain_id": "map-1",
        "task_node_id": "T1",
        "completed_version_ref": "v1",
        "execution_id": "exec-1",
        "draft_id": "draft-1",
        "completed_at": "2026-10-26T08:00:00Z",
        "result_ref": "result-1",
    },
)

body = encode(envelope)      # 校验后编成 UTF-8 JSON 字节
same = decode(body)          # 解回来并再校验一次
```

`encode` 也做校验，所以生产方在构造时就能发现漏字段，而不是等消费方解析失败。`payload` 没有默认值：每种消息类型都有必填载荷字段，一个没有载荷的信封不可能是合法的，本包不该造出自己解码器会拒的消息。

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
| `PAYLOAD_SCHEMAS` | 常量 | 每种消息类型的载荷必填字段 |
| `required_payload_fields(message_type)` | 函数 | 取该类型的必填字段，未知类型返回空元组 |
| `validate_payload(message_type, payload)` | 函数 | 只校验载荷，非法时抛 `PayloadError` |
| `EnvelopeError` | 异常基类 | 统一兜底时捕它 |
| `EnvelopeFormatError` / `SchemaVersionError` / `UnknownMessageTypeError` / `PayloadError` | 异常 | 四类失败，见下节 |

`decode` 只接受 `bytes`，会拒绝四种结构性问题：入参不是字节、字节不是 UTF-8 JSON、顶层不是对象、缺 `payload` 键。缺键报格式错误而不是当成空载荷；显式写 `{}` 则通过格式检查、在载荷校验阶段失败——每种消息类型都有必填载荷字段，空载荷不可能合法。

信封自己的字段缺陷**优先于**版本判断：一封 `schema_version=2` 且 `dedupe_key` 为空的消息报的是格式错误，不是版本错误。想靠 `SchemaVersionError` 触发升级提示的调用方要注意这一点。

## 四类失败

失败被刻意分开，因为消费方对它们的处置不同：

| 异常 | 含义 | 处置 |
| --- | --- | --- |
| `EnvelopeFormatError` | 字节不是可用信封 | 永久错误，生产方坏了 |
| `SchemaVersionError` | 声明了本代码不认识的版本 | 可能是发布方先上线，考虑升级 |
| `UnknownMessageTypeError` | 消息类型无处理器 | 可能是新生产者上线 |
| `PayloadError` | 信封正常，业务载荷不合法 | 生产方 bug |

四者都继承 `EnvelopeError`，需要统一兜底时捕它，能捕全——载荷里塞了不可序列化对象或 `NaN` 时，`encode` 抛的也是 `PayloadError`，不会是裸 `TypeError`。合成一个异常会丢掉消费方唯一能用来判断处置的信息。

`NaN` 与 `Infinity` 被显式拒绝（`json.dumps(allow_nan=False)`）：它们是 Python 的 JSON 扩展而非 JSON，写成 `"payload": {"n": NaN}` 会让非 Python 的消费方直接解析失败。

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

只接受扩展格式且必须用 `T` 分隔（`2026-10-26T08:00:00Z`）。Python 3.11 的 `fromisoformat` 还认 `2026-10-26X08:00:01Z` 和紧凑写法 `20261026T080001Z`，本包刻意收紧：否则自家生产方能发出别家消费方解不开的字节。

## 载荷

载荷按 `message_type` 结构化，必填字段见 `PAYLOAD_SCHEMAS`（字段清单来自 `ai4-te1v` 的统一信封表，本包不自行增删）：

| `message_type` | 必填载荷字段 |
| --- | --- |
| `task_handoff_ready` | `mapping_domain_id`、`task_node_id`、`target_node_version_ref`、`target_agent_id`、`pending_handoff_id`、`trigger_revision_id`、`upstream_source_refs`、`dependency_edge_version_refs`、`executor_ref_snapshot` |
| `task_completed` | `mapping_domain_id`、`task_node_id`、`completed_version_ref`、`execution_id`、`draft_id`、`completed_at`、`result_ref` |
| `formal_revision_published` | `mapping_domain_id`、`formal_revision_id` |
| `candidate_created` | `mapping_domain_id`、`candidate_id` |
| `candidate_head_updated` | `mapping_domain_id`、`candidate_id` |

三条规则：

- **只约束必填项，不约束多余项。** 未知 payload 字段一律容忍并原样往返，容忍式读取不会因为载荷类型化而失效。
- **多值引用恒为数组。** `upstream_source_refs`、`dependency_edge_version_refs`、`executor_ref_snapshot` 即使只有一个元素也必须是数组；写成单值报 `PayloadError`。形状随数量变化会逼每个消费方写两套分支，而「只有一个」那条分支通常没人测。
- **键必须是字符串。** JSON 对象键是字符串，整数键在线上会被改写、生产方再也匹配不回来；同时排序序列化无法比较 `int` 与 `str`。报明确的 `PayloadError`，不泄漏 `json` 的 `TypeError`。

`executor_ref_snapshot` 只用于审计，不替代当前正式 Map 的校验：它记录派发当时看到的执行者集合，事后能分辨「当时没有别的执行者」和「当时有但选错了」。

载荷内容本身的合法性（例如 `mapping_domain_id` 是否指向真实域）不在本包判断范围，那是接收方服务的问题；协议包要查它就得先有对方的数据库。

## 运行测试

```bash
uv run --extra test pytest
```

本包不提交 `uv.lock`（见下节）。`uv run` 会在本地生成一份，已被 `.gitignore` 忽略，不要提交。

## 边界提醒

`shared/` 是代码归属边界，不是项目组。按 `docs/TECH_STACK.md`，它不产生组级 `pyproject.toml` 或组级锁文件，各调用方各自提交自己的锁文件。

源码按概念分三处：`__init__.py` 是信封本体与编解码器，`errors.py` 是四类失败，`payloads.py` 是每种消息类型的载荷规则。载荷类型化落地后 `validate` 按 `message_type` 分派，失败类型又被载荷规则复用，两处都够独立成模块；`models.py` / `codec.py` 仍未拆——信封与编解码器共用同一份校验，拆开只会把一条规则写两遍。
