---
id: ai4-j7g2
status: open
deps: []
links: []
created: 2026-10-27T01:01:29Z
type: bug
priority: 1
assignee: Frank Qi
parent: ai4-aaff
tags: [bug, demo, evidence, ai4science]
---
# T2 基线脚本直接输出硬编码快照哈希，从未校验实际输入

`humans/competition/demo-evidence/run_iris_baseline.py` 第 27 行把 `SNAPSHOT_SHA256` 写成常量，第 95 行把这个常量原样塞进输出的 `input_snapshot_sha256`。脚本全文没有任何 `hashlib` 调用，也就是说：**T2 输出里那个「输入快照哈希」不是测出来的，是写死的。**

两个后果：

1. 分析结果与输入快照之间没有真实绑定。评委问「你怎么证明这次 0.955556 跑的是锁定快照」，现有脚本答不上来——它只是把自己写的常量又打印了一遍。
2. 与 `ai4-483l` 同一个根因：常量值 `daaeb5e3…` 是 CRLF 副本的哈希，仓库内快照是 LF 的 `ea110d42…`。当前 T2 会在**未校验**的情况下产出一份声称哈希为 `daaeb5e3…` 的证据，而该哈希与仓库里的文件对不上。

本票与 `ai4-483l` 共用同一个归一化哈希实现，但改动对象是另一个脚本、验收方式也不同，故分票。

## Design

1. 引入与 `ai4-483l` 相同的 `sha256_of`（整块读取、`\r\n` → `\n` 归一化），两个脚本保持同一实现，避免再次漂移。
2. `SNAPSHOT_SHA256` 保留为**期望值**，角色从「输出值」变成「断言值」：先算实际哈希，与期望值比较，不一致立即返回 `{"status": "failed", "reason_code": "source_hash_mismatch", ...}` 并退出非零，不进入分类计算。
3. 输出的 `input_snapshot_sha256` 改为实际计算值。哈希一致时两者相等，但语义上它来自实测。
4. 断言负责 provenance，`load()` 负责结构（列缺失、非数值），两层职责分开，失败各自给理由码。

## Acceptance Criteria

- [ ] `run_iris_baseline.py` 计算实际输入哈希，不再直接输出常量。
- [ ] 输入哈希与固定期望不一致时返回 `status: failed` / `reason_code: source_hash_mismatch`，且不产出准确率与混淆矩阵。
- [ ] `input_snapshot_sha256` 字段来自实际计算，且在仓库内快照上等于 `ea110d42c2240c77fd292751dfdc4db00c699fee569528ed33ca270838b6f9f4`。
- [ ] `python3 run_iris_baseline.py iris_data.csv` 仍得到准确率 `0.955556`、45 条测试样本、混淆矩阵完整，与既有证据一致。
- [ ] `python3 run_iris_baseline.py iris_data_failure_inject.csv`（缺 `class` 列）以结构错误失败，不进入分类。
- [ ] `demo-evidence/iris_baseline_result.json` 重新生成并存为 UTF-8。
- [ ] 若脚本副本尚未按 `ai4-3vkc` 去重，两份副本内容保持一致。

## Notes

**2026-10-27 登记（Frank Qi）**

身份核对：本票 assignee 为 Frank Qi，当前分支 `feature/frank-qi`、`git config user.name=Frank Qi`，一致。

发现方式：核对 `evidence-card.md` 第 39 行记录的 `input_snapshot_sha256` 时反查脚本，发现该值无任何计算路径。T2 的准确率本身可复现（本机实测 43/45），本票只针对 provenance 缺失，不改变已固定的 K=3 / 种子 `20261023` / 70-30 划分。
