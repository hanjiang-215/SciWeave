from __future__ import annotations

import unittest

from research_mapping.config import MappingConfig

_REQUIRED = {
    "SCIWEAVE_MAPPING_SQLITE_PATH": ":memory:",
    "SCIWEAVE_MAPPING_DOMAIN_ID": "iris",
    "SCIWEAVE_MAPPING_TERMINUSDB_URL": "http://127.0.0.1:6363",
    "SCIWEAVE_MAPPING_TERMINUSDB_DATABASE": "sciweave_mapping",
    "SCIWEAVE_MAPPING_TERMINUSDB_STORE": "admin",
}


class _FakeProducer:
    def close(self) -> None:
        pass


class GovernanceBootstrapConfigTests(unittest.TestCase):
    """ai4-e1jk 回归：SCIWEAVE_MAPPING_KAFKA_BOOTSTRAP 必须进入配置对象。

    修复前 `governance_kafka_bootstrap` 只被读进局部变量、从未传给 dataclass，
    `main.py` 里的 `create_governance_publisher(config.governance_kafka_bootstrap)`
    因此恒为 None，治理事件（候选提交、正式发布）永远不会发布到队列——coordinator
    和 Centre Agent 在真实部署里永远听不到领域变化。
    """

    def test_kafka_bootstrap_reaches_the_config_field(self) -> None:
        env = dict(_REQUIRED)
        env["SCIWEAVE_MAPPING_KAFKA_BOOTSTRAP"] = "redpanda:19092"
        config = MappingConfig.from_environment(env)
        self.assertEqual(config.governance_kafka_bootstrap, "redpanda:19092")

    def test_unset_kafka_bootstrap_stays_none(self) -> None:
        config = MappingConfig.from_environment(dict(_REQUIRED))
        self.assertIsNone(config.governance_kafka_bootstrap)

    def test_configured_bootstrap_selects_kafka_publisher(self) -> None:
        from research_mapping.governance_events import (
            KafkaGovernanceEventPublisher,
            create_governance_publisher,
        )

        config = MappingConfig.from_environment({**_REQUIRED, "SCIWEAVE_MAPPING_KAFKA_BOOTSTRAP": "redpanda:19092"})
        publisher = create_governance_publisher(
            config.governance_kafka_bootstrap,
            producer_factory=lambda **_: _FakeProducer(),  # 不做真实连接
        )
        self.assertIsInstance(publisher, KafkaGovernanceEventPublisher)
        publisher.close()

    def test_absent_bootstrap_selects_noop_publisher(self) -> None:
        from research_mapping.governance_events import (
            NoopGovernanceEventPublisher,
            create_governance_publisher,
        )

        config = MappingConfig.from_environment(dict(_REQUIRED))
        publisher = create_governance_publisher(config.governance_kafka_bootstrap)
        self.assertIsInstance(publisher, NoopGovernanceEventPublisher)


if __name__ == "__main__":
    unittest.main()