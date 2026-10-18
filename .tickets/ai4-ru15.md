---
id: ai4-ru15
status: open
deps: []
links: []
created: 2026-10-16T00:37:28Z
type: epic
priority: 1
assignee: SciWeave
tags: [wayfinder:map, product, ai4science]
---
# SciWeave 动态科研协作平台需求地图

## Destination
形成一个面向科研团队的动态科研协作平台宏观规格：支持多人和多个 AI Agent 围绕可演化的研究路线图共同规划、执行、共享资源、提交变更提案并完成负责人审计。此阶段只确定产品边界和一级功能，不进入技术栈、数据库、消息队列或具体实现。

## Notes
领域：通用科研 Agent 协作平台。
工作方式：研究路线图驱动任务，Agent 与人共同执行，公共资源沉淀，中央协调 Agent 处理提案，项目负责人承担最终审计责任。
参考方向：DeepScientist、Dify、n8n、LangGraph、AutoGen，以及现有相似产品调研。

## Decisions so far

- [平台定位与用户边界](ai4-9f7i.md)：平台服务一个科研小组及其项目，采用一名管理员和若干成员的简单组织方式；平台定位为通用科研任务控制平面，负责路线图、调度、审核、资源共享和审计，不开发具体科研领域能力或新的通用 harness 框架。研究人员可以接入自己的 personal-agent harness；平台提供的独立研究 Agent 使用轻量化、可配置的任务 harness。
- [多人和多 Agent 协作执行](ai4-e257.md)：任务节点可以由单人、多人、Personal Agent、轻量任务 Agent 或协作集合负责；Agent 处理重复和结构化工作，研究人员负责实验、判断、头脑风暴、路线维护和全部审计；Agent 结果须经负责人审核后才能进入公共资源，研究路线变化通过 Proposal 更新动态研究图。
- [科研路线图与动态研究图](ai4-ebqx.md)：项目只维护一个逻辑 Research Mapping，拓扑只包含统一的 TaskNode；节点保存自身信息，依赖和执行语义只由边保存；资源由独立资源系统管理并通过引用关联，展示通过视图筛选逻辑主图。Research Mapping 的存储治理区分 formal branch 与 candidate branch：正式分支只保存已正式化的版本，每个 Proposal 使用独立候选分支承载待审核变更；Agent 通过 MCP 提交结构化变更，中央 Agent 预审，负责人批准后由平台受控推进为正式 Commit 和 Formal MappingRevision。
- [TerminusDB Mapping 版本与 Agent 提交原型验证](ai4-9hcj.md)：实测 TerminusDB 12.0.8 支持 Schema、TaskNode、依赖边、Commit、History 和 Diff；HTTP 文档写入会立即生成 Commit，`commit=false` 不提供未提交工作区；原生 reset 会移动当前分支状态并使新提交不再出现在该分支日志中，因此 Proposal、审核和不可擦除回滚痕迹仍需由平台补充。
- [TerminusDB 候选分支与草稿工作区行为验证](ai4-2alw.md)：TerminusDB 12.0.8 支持从 main 创建隔离 candidate branch、独立写入、Commit/History/Diff 和通过 rebase 推进到 main；不存在无 Commit 草稿工作区，平台需将 candidate branch 与 Proposal 审核、正式 Revision 和正式查询投影关联，不能把 rebase 本身当作审批。
- [科研公共资源与证据空间](ai4-saug.md)：资源空间采用“范围广、首期实现窄”的边界；Resource Reference 可引用数字对象、研究假设、项目 Agent 输出、Skill、MCP 能力或实物，但排除平台初始化基础能力。Resource、ResourceVersion、Resource Reference 和可选 RawArtifact 分工明确，正式引用指向不可变版本；可直接读取资源走 direct query，实物等不可直接读取资源转为 researcher-required 处理任务，首期只完整演示数字资源闭环。
- [单一 Mapping 的草稿与正式视图模型](ai4-u3rs.md)：项目只维护一个逻辑 Research Mapping，正式内容位于 formal branch，每个 Proposal 使用独立 candidate branch 承载草稿；节点和边内容创建后不可原地修改，候选版本不可变，普通查询只读取当前 Formal MappingRevision，TerminusDB Commit/History/Diff 负责底层版本历史。后续统一治理决策允许从同一正式版本派生多个并行 Proposal，提交 Merge Request 后锁定 candidate head，最终只能选择一个完整方案正式化。
- [Wiki Buffer 提交单位：单文档、文档加引用还是完整 ChangeSet](ai4-36ek.md)：Buffer 以单个文档变更单元为最小接纳对象，正文与该版本所需的 Resource Reference 关系一起保持一致；多个单元再由 Proposal 聚合并整体审核，单个逻辑文档同一时间只允许一个活动草稿。
- [TerminusDB candidate branch 状态、只读归档与正式查询边界](ai4-2sdn.md)：TerminusDB 12.0.8 的 branch 只提供存储分支创建、写入和删除，不提供 Proposal 状态、只读或归档元数据；候选 Commit 不代表已批准，平台必须在结构化记录中保存 selected/not_selected/rejected/abandoned、审计和写入控制。一个正式版本可以派生多个 candidate branch，提交 Merge Request 后锁定 candidate head；普通查询只读取 formal branch 的当前 Formal WikiRevision，审计查询才读取候选分支、Commit、Diff 和治理记录，物理删除只能作为受控存储清理。
- [研究变更 Proposal / PR 治理](ai4-dy2x.md)：SciWeave 首版只将 Research Mapping 的路线结构变化纳入 Proposal / PR 闭环；任务执行状态、运行日志和普通进度记录不改变正式 Mapping，不单独创建 Proposal。首版采用单候选演示路径，中央 Agent 预审，项目负责人正式发布，候选和驳回记录保留审计；LLM-Wiki 与跨域原子正式化暂不进入首版。
- [通用平台的第一阶段产品范围](ai4-ay0e.md)：SciWeave 首版以 Research Mapping 驱动的科研任务闭环为唯一主线，覆盖项目入口、任务依赖、人员/Agent 执行、数字证据引用、Mapping Proposal、Project Owner 人工审核和执行审计；平台保持场景中立，通过可替换示例场景验证跨场景复用。LLM-Wiki 完整治理、复杂资源模型、并行候选、跨域写入、真实设备控制和复杂权限暂缓。
- [中央协调 Agent 与审计体系](ai4-vbnr.md)：首版由一个 Central Agent 负责调度、格式和影响范围预审、失败重试与执行留痕；Mapping 与 Wiki 仍通过独立管理 MCP 隔离。任何 Formal Mapping 或正式科研结果发布都必须由 Project Owner 明确批准，审计事件追加保留，失败改变路线时必须进入 Mapping Proposal。
- [Research Mapping 与 LLM-Wiki 统一提案治理内核](ai4-3nru.md)：Map 与 Wiki 共享 Buffer、Proposal、candidate branch、candidate head lock、Merge Request Buffer、diff/dry-run 和 Formal Revision 的治理语义，但分别实现独立 MCP、Buffer、校验器、TerminusDB、Revision 和审计链；允许并行 Proposal，最终只能选择一个完整方案正式化，不支持跨域 Proposal 或跨域原子正式化。

## Not yet specified

- Research Mapping 的 TaskNode 与 Dependency Edge 字段模型、必填条件、状态约束、版本字段和正式查询所需字段，继续由 [Research Mapping 节点与依赖边字段模型](ai4-r3so.md) 决定。
- 首版默认科研示例场景、最小数字证据、SciencePal 承载方式、失败或路线调整脚本和最终验收证据，继续由 [SciWeave 默认科研示例场景与验证证据](ai4-aaff.md) 决定；当前只确定选择标准和验证闭环，尚未替用户选择具体学科。
- [首版任务执行、交接与失败恢复模型](ai4-m0vt.md) 负责在进入规格设计前确定任务状态、Execution Record、MCP Submission、执行主体、交接、重试、转交、人工接管、失败分类、幂等和两阶段审核边界；普通执行失败不自动改变正式 Mapping，改变研究路线才进入 Proposal。
- [首版 Mapping Proposal 生命周期与审计证据模型](ai4-xrxw.md) 负责确定 Proposal 状态生命周期、候选版本锁定、Diff/影响预览、Formal Query/正式调度门槛和 AuditEvent 的最小关联；它不重复决定已由 `ai4-u3rs` 与 `ai4-dy2x` 确定的候选分支宏观方向。
- [固定 TerminusDB 验证服务版本并同步说明](ai4-5j2j.md) 是实现准备任务，负责把已验证的 TerminusDB 12.0.8 固定到本地 Compose 并同步说明，不把实现准备误写成新的产品架构结论。
- Research Mapping 的 TaskNode 与 Dependency Edge 字段模型、必填条件、状态约束、版本字段和正式查询所需字段，继续由 [Research Mapping 节点与依赖边字段模型](ai4-r3so.md) 决定。
- 首版进入规格设计前，还需要把上述决策票收敛为可验证的最小领域规格：MCP 提交边界、Execution Record、AuditEvent、Formal Mapping 查询/调度边界、Proposal Diff/影响预览和演示验收脚本。
- 中央节点服务 raw 存储的版本、哈希、访问权限、容量阈值、备份、保留和删除规则，仍未确定。
- 节点和边的执行痕迹、失败路线和动态变更的完整表达，需在字段模型和首版规格中共同收敛。

## Out of scope

- 当前阶段不确定具体编程语言、框架、数据库、消息中间件或部署方案。
- 当前阶段不实现完整科研平台、公开 Agent 市场或真实实验设备控制。
- 第一阶段不支持 Research Mapping 与 LLM-Wiki 的跨域写入：不允许单个 MCP Submission 或 Proposal 同时修改两个领域，不支持跨两个 TerminusDB 的原子正式化；需要同时产生两边变化时，由端侧 Agent 分别提交两次独立变更。

## Acceptance Criteria

完成宏观需求地图；每个一级功能域都有明确的产品决策票；明确当前范围、未决问题和暂不涉及的实现细节。

**2026-10-16T05:28:22Z**

PR 已创建：Gitee Pull Request #2 https://gitee.com/OWNER/ai4science/pulls/2，目标分支 develop，当前分支 feature/dev-a。PR 覆盖提交 87a51ee、dbba4c6、89cefa5、6af81f8、9218507、f58f675、98bea71、fbaa5c1、bcae02c、5b280b9；验证包括 git diff --check、git-cliff 生成 CHANGELOG.md，以及 TerminusDB 12.0.8 的 Schema/TaskNode/DependencyEdge/Commit/History/Diff/reset 实测。后续 TerminusDB 候选分支与草稿工作区仍由 ai4-2alw 验证。

**2026-10-16T11:26:37Z**

Gitee Pull Request #3 已创建：https://gitee.com/OWNER/ai4science/pulls/3，目标分支 develop，当前分支 feature/dev-a。PR 包含 TerminusDB-Wiki 治理方向、需求地图更新、术语表和 CHANGELOG.md；验证包括 git diff --check 与 git-cliff --config cliff.toml --output CHANGELOG.md。

**2026-10-17T01:43:58Z**

边界确认：Research Mapping 与 LLM-Wiki 第一阶段完全独立，分别拥有自己的 Agent、MCP、Buffer、内存上下文、校验器、TerminusDB、candidate branch、Revision 和审计链。第一阶段不支持跨域写入：单个 MCP Submission 或 Proposal 只能修改一个领域，不支持跨两个 TerminusDB 的原子正式化；需要同时产生两边变化时分别提交独立变更。两个领域只允许通过稳定对象 ID 和版本 ID 建立显式弱引用。

**2026-10-17T01:50:00Z**

冲突表述修正：Central Agent 不拆成两个独立 Agent；由同一个 Central Agent 配置独立的 Wiki 管理 MCP 和 Mapping 管理 MCP。两个管理 MCP 背后的 Buffer、TerminusDB、领域对象、Revision、审计链和写入状态仍然完全隔离，Central Agent 不通过一个 MCP Submission 或 Proposal 同时修改两个领域。Proposal 按领域分别维护，不存在跨域 Proposal。

**2026-10-17T15:26:44Z**

方案复审记录（2026-10-17）：复核时开放工单只有 ai4-aaff 与 ai4-r3so，未发现执行模型或 Proposal 生命周期模型的重复开放票。已创建 ai4-m0vt（任务执行/交接/失败恢复）、ai4-xrxw（Mapping Proposal 生命周期/审计证据）和 ai4-5j2j（固定 TerminusDB 验证服务版本并同步说明）；三票均挂在本需求地图下，并已建立与既有决策/验证票的依赖或关联。

**2026-10-18T07:06:44Z**

Gitee Pull Request #6 已创建：https://gitee.com/OWNER/ai4science/pulls/6，目标分支 develop，当前分支 feature/dev-b。PR 覆盖 25 个提交（相对 origin/develop），内容包括产品命名 SciWeave、README 产品定位、GLOSSARY 新增 Execution Record 与 AuditEvent、文件与命名规范 .cursor/rules/dev/files.mdc、依赖清单权威版本与 humans/dev 副本同步、CHANGELOG.md。验证：git diff --check 退出码 0；分支已包含 origin/develop 全部提交；git-cliff 按 cliff.toml 生成 CHANGELOG.md。本次为文档与工单变更，无测试可执行。
