# MCP 资源参考

标准资源包括 `research-mapping`（正式 Mapping 只读查询与候选提交/审阅/正式化）、`research-wiki`（正式 Wiki 只读查询与候选提交/审阅/正式化）和 `draft-buffer`（草稿创建、提交、审阅与转候选）。三张卡片的工具清单与领域管理 MCP、草稿箱服务的真实工具面一一对应；具体可调用范围由服务端能力档位（read / candidate_submit / candidate_review / formalize / centre）裁决，卡片只描述能力面。地址和令牌分别通过资源描述符声明的环境变量提供；真实值不提交。

`LOCAL_MCP_LIBS` 可指向本地描述符目录；兼容的 1.x 本地同名资源覆盖标准资源，同名冲突或不兼容版本应失败。资源库只提供目录和配置约定，不主动建立网络连接。