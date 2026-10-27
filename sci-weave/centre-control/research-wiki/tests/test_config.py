from __future__ import annotations

import unittest

from llm_wiki.config import WikiConfig

_REQUIRED = {
    "SCIWEAVE_WIKI_SQLITE_PATH": ":memory:",
    "SCIWEAVE_WIKI_DOMAIN_ID": "wiki",
    "SCIWEAVE_WIKI_TERMINUSDB_URL": "http://127.0.0.1:6363",
    "SCIWEAVE_WIKI_TERMINUSDB_DATABASE": "sciweave_wiki",
    "SCIWEAVE_WIKI_TERMINUSDB_STORE": "admin",
}


class _FakeProducer:
    def close(self) -> None:
        pass


class GovernanceBootstrapConfigTests(unittest.TestCase):
    """ai4-u5e6 回归：SCIWEAVE_WIKI_KAFKA_BOOTSTRAP 必须进入配置对象。

    与 research-map 同族的缺陷形状是「读了但没传给 dataclass」，配置对象字段
    恒为 None，publisher 永远是 Noop，而所有调用点看起来都正常。
    """

    def test_kafka_bootstrap_reaches_the_config_field(self) -> None:
        config = WikiConfig.from_environment(
            {**_REQUIRED, "SCIWEAVE_WIKI_KAFKA_BOOTSTRAP": "redpanda:19092"}
        )
        self.assertEqual(config.governance_kafka_bootstrap, "redpanda:19092")

    def test_unset_kafka_bootstrap_stays_none(self) -> None:
        config = WikiConfig.from_environment(dict(_REQUIRED))
        self.assertIsNone(config.governance_kafka_bootstrap)

    def test_configured_bootstrap_selects_kafka_publisher(self) -> None:
        from llm_wiki.governance_events import (
            KafkaGovernanceEventPublisher,
            create_governance_publisher,
        )

        config = WikiConfig.from_environment(
            {**_REQUIRED, "SCIWEAVE_WIKI_KAFKA_BOOTSTRAP": "redpanda:19092"}
        )
        publisher = create_governance_publisher(
            config.governance_kafka_bootstrap,
            producer_factory=lambda **_: _FakeProducer(),  # 不做真实连接
        )
        self.assertIsInstance(publisher, KafkaGovernanceEventPublisher)
        publisher.close()

    def test_absent_bootstrap_selects_noop_publisher(self) -> None:
        from llm_wiki.governance_events import (
            NoopGovernanceEventPublisher,
            create_governance_publisher,
        )

        config = WikiConfig.from_environment(dict(_REQUIRED))
        publisher = create_governance_publisher(config.governance_kafka_bootstrap)
        self.assertIsInstance(publisher, NoopGovernanceEventPublisher)

    def test_publisher_does_not_connect_until_the_first_publish(self) -> None:
        """ai4-xncm：构造期不能等 broker。

        kafka-python 的 KafkaProducer 构造时同步拉元数据（默认 60 秒），broker
        不可达就抛错——放在进程启动路径上会把 wiki 管理 MCP 一起拖死。
        """
        from llm_wiki.governance_events import create_governance_publisher

        created: list[dict] = []
        create_governance_publisher(
            "redpanda:19092", producer_factory=lambda **kwargs: created.append(kwargs)
        )
        self.assertEqual(created, [], "publisher must not connect at construction time")


if __name__ == "__main__":
    unittest.main()