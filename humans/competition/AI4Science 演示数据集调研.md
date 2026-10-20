# AI4Science 演示数据集调研

> 调研日期：2026-10-19。用途限定为可替换的验证夹具：产品核心保持学科中立，不由示例数据集决定产品领域或对象模型。

## 赛事要求与数据使用边界

赛事官网要求从真实科学问题或科研痛点出发制作可运行、可展示、可验证的作品，且至少一个核心环节实质性使用 SciencePal；仅用其写介绍、润色文案或制作演示稿不算有效使用。提交材料包括 3–5 分钟演示视频、不超过 5 页的项目说明，以及模型、数据、代码、API 和外部工具使用情况与原创性、合规说明；评审关注科学价值、创新性和可行性（[赛事官网](https://sciencepal.ai/hackathon)）。官网公开页面没有列出指定数据集或通用数据集许可证要求；这不替代参赛者核实所选数据自身的许可和署名条件。

## 候选比较

| 候选 | 用途与结构 | 获取和复现 | 许可、署名与注意事项 |
| --- | --- | --- | --- |
| **NOAA Mauna Loa CO₂ 月均值（替换验证场景）** | 官方月度 CSV 以年、月、十进制日期、月均值、去季节化值、观测天数、标准差和不确定度 8 列组成，适合作为不同数据形态的替换验证，演示时间序列分析、季节变化观察以及对来源和缺测处理的人工审查（[NOAA 数据页](https://gml.noaa.gov/ccgg/trends/data.html)、[CSV 文件说明与数据](https://gml.noaa.gov/webdata/ccgg/trends/co2/co2_mm_mlo.csv)）。NOAA 说明 CO₂ 数值是干空气中的摩尔分数，单位 ppm（[测量说明](https://gml.noaa.gov/ccgg/about/co2_measurements.html)）。 | 官方 CSV 可直接下载。本次检查（2026-10-19）HTTP 200，38,776 字节、823 条月记录，覆盖 1958-03 至 2026-09；SHA-256：`d895fb5b4a59fb5e4cd98e69b7667fe5bef595c6581f630852b12cb41c07f675`。数据会因质控而小幅修订，因此演示应保存所用快照、下载日期与哈希，而非只依赖实时 URL（[NOAA 数据页](https://gml.noaa.gov/ccgg/trends/data.html)、[CSV](https://gml.noaa.gov/webdata/ccgg/trends/co2/co2_mm_mlo.csv)）。 | 文件说明称数据向公众和科学界免费提供，以广泛传播促进理解和新发现，并为确保 NOAA GML 获得公平认可，请在出版物中加入相关引用；趋势页建议引用 Xin Lan（NOAA/GML）及 Ralph Keeling（Scripps）。文件还鼓励联系数据提供者；若数据对出版物至关重要，数据提供者共同署名可能适当。这些是页面写明的致谢/出版建议，并非页面明确列出的通用许可条款。所核查来源未标明 CC BY 等标准开放许可证，也未明确说明竞赛提交、再分发或其他非出版用途的许可条件；应准确记为“公开提供并提出出版引用建议；标准许可证及非出版用途条件未明确”，不能将其推断为无限制使用（[CSV 文件说明](https://gml.noaa.gov/webdata/ccgg/trends/co2/co2_mm_mlo.csv)、[引用说明](https://gml.noaa.gov/ccgg/trends/data.html)）。1958-03 至 1974-04 数据来自 Scripps；NOAA 文件说明缺失月份有插值并用负标准差/不确定度标记。2022 年末至 2023 年 7 月初因火山活动，记录来自约 21 英里以北的 Maunakea 站点。可将演示分析窗口设为 1974-05 以后以避免早期来源混合，但仍应注明站点变化及数据处理说明（[CSV 文件说明](https://gml.noaa.gov/webdata/ccgg/trends/co2/co2_mm_mlo.csv)）。 |
| **UCI Iris（主演示场景）** | 经典植物分类数据：150 条、4 个实数特征（萼片和花瓣长宽，单位 cm）及 3 类目标，无缺失；UCI 将其标为生物学领域、分类任务（[UCI 数据集页](https://archive.ics.uci.edu/dataset/53/iris)、[官方 API 元数据](https://archive.ics.uci.edu/api/dataset?id=53)）。 | 官方 CSV：[`data.csv`](https://archive.ics.uci.edu/static/public/53/data.csv)。本次检查 HTTP 200，4,615 字节、150 条数据（另有表头），适合离线夹具和快速验证；UCI 页面列出的 Iris 数据文件大小约 4.4 KB，页面提供 DOI `10.24432/C56C76`。复现时固定下载文件和校验值；本次文件 SHA-256：`daaeb5e3e889d07fbdd44544f5a39fe2372a07172e25899d577be0ad74df9e65`（[UCI 数据集页](https://archive.ics.uci.edu/dataset/53/iris)、[CSV](https://archive.ics.uci.edu/static/public/53/data.csv)）。 | UCI 明确标为 **CC BY 4.0**，允许为任何目的分享和改编，条件是给予适当署名；按许可页要求保留署名并链接许可证（[UCI 许可说明](https://archive.ics.uci.edu/dataset/53/iris)、[CC BY 4.0 法律文本](https://creativecommons.org/licenses/by/4.0/legalcode)）。UCI 元数据给出原始创建年份 1936、R. A. Fisher 和数据集 DOI；来源本身很经典，分类演示偏通用机器学习示例；这正适合将赛事演示重点放在通用流程和治理闭环，而不是包装新的植物学发现（[UCI 官方 API](https://archive.ics.uci.edu/api/dataset?id=53)）。 |

## 建议

优先用 **UCI Iris** 作为主演示数据：数据经典、体量小，可固定为可复现输入；官方页面给出字段、来源 DOI、文件下载和明确的 CC BY 4.0 许可，署名后可用于任何目的，适合在赛事时间内快速构造可验证闭环。数据很小、分类问题也经典，因此演示重点应放在输入核验、SciencePal 实际执行、结果证据、人员接纳及路线治理，而不是把分类结果包装成新的植物学发现。

把 **NOAA Mauna Loa CO₂** 保留为时间序列替换验证，不作为提交时默认打包的数据。它能检查同一通用流程是否适配时间字段、ppm 单位、缺测/质量标记和变化中的快照，但 NOAA 页面未明确标准许可证及竞赛提交、再分发等非出版用途条件。若未来需要把该数据副本或衍生数据随作品重新发布，应先向数据提供方核实适用条件并保留来源说明。

以上是以赛事时限、数据可复现与许可明确性为依据的样例选择；两者均不定义 SciWeave 的产品领域。该选择不代表已完成 SciencePal 实演、完整 3–5 分钟脚本或工单验收。
