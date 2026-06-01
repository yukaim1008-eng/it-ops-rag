# 四周学习与开发计划 —— 智能 IT 运维知识库

## 使用方式
- **你**：每天按计划自己写代码，遇到问题随时问我
- **我**：答疑、review 你的代码、每天结束时帮你生成学习笔记
- **节奏**：自由控制，可以比计划快（提前完成就提前进入下一阶段）

---

## 第一周：基础与数据管道（文档 → 向量库）

### Day 1：环境搭建与依赖理解
**任务：**
- [ ] 创建 Python 3.13 虚拟环境 `.venv`
- [ ] 安装以下包，每装一个就查一下它是干什么的：
  - `langchain` `langchain-deepseek` `langchain-community` — LangChain 生态
  - `qdrant-client` — Qdrant 向量数据库的 Python SDK
  - `FlagEmbedding` — BGE 模型的封装库（含 embedding 和 reranker）
  - `rank-bm25` — BM25 稀疏检索算法实现
  - `jieba` — 中文分词（BM25 依赖它）
  - `streamlit` — Web UI 框架
  - `python-dotenv` — 从 .env 文件加载环境变量
  - `pymupdf` — PDF 解析（PyMuPDF）
  - `tiktoken` — OpenAI 的 tokenizer（LangChain 内部用）
- [ ] 创建 `.gitignore`（排除 `.env`、`.venv/`、`__pycache__/`）
- [ ] 创建 `.env` 文件，写入三个占位符 Key

**学习重点：**
- 理解每个包在 RAG 系统中扮演什么角色
- 理解为什么要用虚拟环境

---

### Day 2：配置管理（config.py）
**任务：**
- [ ] 写 `config.py`，把所有可配置项集中管理
- [ ] 用 `python-dotenv` 加载 `.env`
- [ ] 定义以下配置项：
  - API 密钥、模型名、Qdrant 连接信息
  - 切片参数（chunk_size=500, chunk_overlap=50）
  - 检索参数（top_k=20, final_k=3, RRF_K=60）
  - 多步推理参数（max_rounds=2, 置信度阈值）
- [ ] 写一个 `validate_config()` 函数：启动时检查 Key 是否已填写
- [ ] 写 `get_llm()` 工厂函数，返回 `ChatDeepSeek` 实例

**学习重点：**
- 为什么要把配置集中管理而不是散落各处？
- LangChain 的 `ChatDeepSeek` 封装了什么？
- 环境变量 vs 硬编码的安全意义

---

### Day 3：理解文档切片策略 + 写示例文档
**任务：**
- [ ] 创建 `data/` 目录结构（按系统模块分子目录）
- [ ] 写 6-8 篇中文 Markdown 运维文档（每篇 500-1500 字），覆盖：
  - `server/` — CPU 飙高排查、内存泄漏诊断
  - `network/` — DNS 解析失败排查
  - `database/` — MySQL 慢查询优化
  - `application/` — Nginx 502 排查、Docker 容器崩溃
  - `security/` — SSL 证书过期处理
  - `monitoring/` — Prometheus+Grafana 搭建
- [ ] 创建 `data/metadata.json`，记录每篇文档的元数据：
  ```json
  {
    "server_cpu_high.md": {
      "system_name": "服务器",
      "doc_type": "troubleshooting",
      "severity": "L1",
      "tags": ["CPU", "性能", "top命令"]
    }
  }
  ```

**学习重点：**
- 文档元数据（metadata）在 RAG 中的作用是什么？
- 一个好的 chunk 应该具备什么特征？（完整性、独立性）
- 中文分块和英文分块的差异在哪里？

---

### Day 4：工具函数（utils.py）
**任务：**
- [ ] 写 `tokenize_for_index(text)` — 用 `jieba.cut`（精确模式）分词
- [ ] 写 `tokenize_for_query(text)` — 用 `jieba.cut_for_search`（搜索模式）分词
- [ ] 思考：为什么索引侧和查询侧要用不同的分词模式？
- [ ] 写 `dedup_by_chunk_id(results)` — 按 chunk_id 去重
- [ ] 写 `reciprocal_rank_fusion(dense_results, sparse_results, k=60)` — RRF 融合算法
- [ ] 写 `setup_logger()` — 统一的日志配置

**学习重点：**
- RRF 算法的数学原理：`score = Σ 1/(k+rank_i)`
- 为什么 RRF 不需要做 score normalization？
- jieba 三种分词模式的区别（精确/全/搜索引擎）

---

### Day 5：文档加载与切片（data_loader.py 上半部分）
**任务：**
- [ ] 实现 `load_documents(data_dir)` — 加载 data/ 下所有 .md 文件
  - 使用 `langchain_community.document_loaders` 中的 DirectoryLoader
  - 每个 Document 对象附带 metadata（从 metadata.json 合并进来）
- [ ] 实现 `split_documents(docs)` — 文本切片
  - 使用 `RecursiveCharacterTextSplitter`
  - 分隔符顺序：`["\n\n", "\n", "。", "！", "？", "；", " ", ""]`
  - 每个 chunk 分配唯一 `chunk_id`（格式：`{文件名}_chunk_{序号}`）

**学习重点：**
- RecursiveCharacterTextSplitter 的工作原理——为什么分隔符有顺序？
- chunk_size 和 chunk_overlap 如何影响检索质量？
  - size 太大 → 检索不准（噪音多）
  - size 太小 → 信息不完整（丢失上下文）
  - overlap 太大 → 冗余
  - overlap 太小 → 断句处信息割裂

---

### Day 6：嵌入生成与向量入库（data_loader.py 下半部分）
**任务：**
- [ ] 实现 `embed_chunks(chunks)` — 用 BGE-large 生成嵌入向量
  - 直接使用 `FlagEmbedding` 的 `BGEM3FlagModel` 或 `bge-large-zh-v1.5`
  - 文档侧不需要加 instruction prefix（只有查询侧需要）
  - 批量编码（batch_size=32），`normalize_embeddings=True`
- [ ] 实现 `ingest_to_qdrant(chunks, embeddings)` — 写入 Qdrant
  - 创建/重建 collection（vector_size=1024, distance=Cosine）
  - 每个 point 携带完整 payload（text + 所有 metadata 字段）
  - 分批 upsert（batch_size=100）

**学习重点：**
- BGE 模型的 instruction prefix 设计——为什么只在查询侧加？
- Qdrant 的 Collection、Point、Payload 概念
- 为什么选择 Cosine 距离而不是 Euclidean 或 Dot？

---

### Day 7：跑通数据管道 + 验证
**任务：**
- [ ] 运行 `python data_loader.py`，完成全流程
- [ ] 写一个简单的验证脚本，确认：
  - Qdrant collection 存在且 point 数量正确
  - 随机取几个 point 查看 text 和 metadata 是否完整
  - 用一个简单查询测试向量搜索是否返回合理结果
- [ ] 如果 Qdrant Cloud 还没准备好，先用本地模式（`:memory:`）开发

**学习重点：**
- 整个数据管道的端到端流程复盘
- 向量检索的基本原理（相似度计算）

---

## 第二周：检索核心（混合检索 → 重排序）

### Day 8：稠密检索（Dense Retrieval）
**任务：**
- [ ] 在 `retrieval.py` 中实现 `dense_search(query, top_k, metadata_filter)`
  - 用 `FlagEmbedding.encode()` 将查询转为向量
  - **注意：查询侧要加 instruction prefix** `"为这个句子生成表示以用于检索相关文章："`
  - 调用 `qdrant_client.search()` 执行相似度搜索
  - 支持可选的 metadata filter（Qdrant 的 Filter API）

**学习重点：**
- 向量相似度搜索的工作原理（ANN 近似最近邻）
- 为什么同样一个模型，查询侧和文档侧的编码方式不同？（非对称嵌入）

---

### Day 9：稀疏检索（BM25 Sparse Retrieval）
**任务：**
- [ ] 在 `retrieval.py` 中实现 `BM25Searcher` 类
  - `__init__`: 从文档列表构建 BM25 索引（用 jieba 分词后喂给 rank-bm25）
  - `search(query, top_k)`: 查询侧分词后计算 BM25 分数，返回 top_k
- [ ] 实现 `init_bm25()` — 从 Qdrant 拉取所有文档用于构建索引
- [ ] 思考：BM25 索引在应用启动时构建一次 vs 每次查询重建？

**学习重点：**
- BM25 的 TF-IDF 核心思想
- 稠密检索 vs 稀疏检索各自的优势场景：
  - 语义相似（"服务器很卡" vs "CPU 使用率高"）→ 稠密
  - 精确关键词（错误码 "ERR-001"）→ 稀疏

---

### Day 10：混合检索 + RRF 融合
**任务：**
- [ ] 实现 `hybrid_search(query, top_k, metadata_filter)`
  - 同时调用 `dense_search` 和 `BM25Searcher.search`
  - 用 RRF 算法融合两个结果列表
  - 去重（按 chunk_id）后返回 top_k

**学习重点：**
- RRF 为什么能有效融合异构检索结果？（不依赖原始分数，只看排名）
- 面试高频问题：你为什么选择 RRF 而不是简单的分数加权？

---

### Day 11：元数据过滤
**任务：**
- [ ] 实现 `build_metadata_filter(selections)` — 将用户选择转为 Qdrant Filter
  - 例如 `{"system_name": "服务器", "severity": "L1"}` → Qdrant Filter must 条件
- [ ] 元数据过滤集成到 `dense_search` 中（利用 Qdrant 原生过滤）
- [ ] 思考：BM25 如何做元数据过滤？（提示：需要先多召回一些再后置过滤）

**学习重点：**
- Qdrant 的 payload 索引机制
- 元数据过滤在实际企业 RAG 中的价值（权限控制、范围限定）

---

### Day 12：Cross-Encoder 重排序
**任务：**
- [ ] 实现 `rerank(query, candidates, top_k)` 
  - 使用 `FlagEmbedding` 的 `FlagReranker`（加载 `bge-reranker-base`）
  - 对每个 (query, chunk_text) 对计算相关性分数
  - 按分数降序返回 top_k
- [ ] 形成完整的检索管线：`hybrid_search(top_20) → rerank(top_3)`

**学习重点：**
- Bi-Encoder vs Cross-Encoder 的区别和各自适用场景：
  - Bi-Encoder：查询和文档独立编码，速度快，适合大规模召回
  - Cross-Encoder：查询和文档联合编码，精度高但慢，适合小规模精排
- "粗排 → 精排" 两阶段架构的设计哲学

---

### Day 13：检索层集成测试
**任务：**
- [ ] 写 8+ 个测试查询，覆盖不同场景：
  - 精确匹配（"nginx 502错误怎么排查"）
  - 模糊语义（"服务器很慢"）
  - 元数据过滤（"数据库相关的慢查询问题"）
  - 错误码（"ERR-SSL-001"）
  - 不相关查询（测试空结果处理）
- [ ] 对每个查询，人工评估 top-3 结果的相关性
- [ ] 记录不理想的 case，思考如何改进

**学习重点：**
- 如何量化评估检索质量？（Precision@K, Recall@K, MRR）
- 为什么不同业务场景可能需要不同的检索策略？

---

### Day 14：缓冲日 / 复习
- 回顾第一周+第二周内容
- 整理笔记
- 修复遗留问题

---

## 第三周：智能编排（查询理解 → 多步推理 → 生成回答）

### Day 15：查询重写（Query Rewriting）
**任务：**
- [ ] 在 `orchestrator.py` 中实现 `rewrite_query(original_query, llm)`
  - 用 LLM 将模糊的用户问题改写成 2-3 条精确的检索查询
  - Prompt 要点：要求从不同技术角度覆盖问题
  - 处理边界：LLM 返回空、返回原文、返回过长文本
  - 解析 LLM 响应（按行分割，过滤空行）

**学习重点：**
- 查询重写在 RAG 中的核心价值——弥补"用户表达"和"文档表述"之间的 gap
- 为什么"电脑很卡"需要拆成 "CPU高/内存不足/磁盘IO高"？

---

### Day 16：检索路由器
**任务：**
- [ ] 实现 `route_retrieval(query)` — 判断检索策略偏向
  - 规则式路由（不是 LLM 调用）：
    - 包含错误码正则 `[A-Z]+-\d+` → 偏向 BM25
    - 自然语言疑问句 → 偏向 Dense
    - 默认 → 等权重
  - 返回路由配置 dict

**学习重点：**
- 为什么先做规则路由而不是 LLM 路由？（延迟、成本、可靠性）
- 什么时候应该升级到 LLM 路由？

---

### Day 17：多步推理检索（上）
**任务：**
- [ ] 实现 `multi_step_retrieve(query, rewritten_queries, max_rounds)` 的 Round 1
  - 对每条重写后的查询执行 `hybrid_search` + `rerank`
  - 合并所有结果，按 chunk_id 去重
  - 记录最高分和候选数量

**学习重点：**
- 多步推理和 Agentic RAG 的关系
- 什么时候需要多步检索？（信息不足时自动追加搜索）

---

### Day 18：多步推理检索（下）+ 质量判断
**任务：**
- [ ] 实现 `is_retrieval_sufficient(results)` — 判断检索质量是否达标
  - 条件 A：至少 3 个 chunks 的 cross-encoder 分 >= 0.5
  - 条件 B：Top-1 分数 >= 0.7
  - 满足任一条件即为"充分"
- [ ] 实现 Round 2：如果不够，LLM 生成新的检索关键词，再搜一次
- [ ] 限制最多 2 轮，防止无限循环

**学习重点：**
- 阈值是怎么选的？（0.5 和 0.7 是经验值，实际需要根据业务调整）
- 多步推理的成本-收益分析

---

### Day 19：答案生成与引用溯源
**任务：**
- [ ] 实现 `generate_answer(query, context_chunks, llm)`
  - 构建 QA Prompt（从 config.py 导入模板）
  - 将 context 格式化为 `[文档1] 来源：xxx.md 第3段\n...`
  - 要求 LLM 在每个关键信息后标注 `[来源: 文件名 第X段]`
  - 返回结构化结果：{"answer": str, "citations": [...]}

**学习重点：**
- RAG 的 "G" —— 如何让 LLM 严格基于检索到的文档生成回答？
- Citation（引用）如何防止幻觉？（限制 LLM 只能引用提供的文档）
- Prompt Engineering 中的 System Prompt vs User Prompt

---

### Day 20：编排层集成测试
**任务：**
- [ ] 端到端测试：从 query → rewrite → retrieve → generate_answer
- [ ] 用 5 个真实问题测试，评估：
  - 回答是否准确？（跟源文档对照）
  - 引用是否正确？（citation 指向的 chunk 是否真的包含对应信息）
  - 回答是否完整？（有没有遗漏关键信息）

**学习重点：**
- RAG 系统的三个评价维度：Faithfulness（忠实度）、Answer Relevance（相关性）、Context Relevance（上下文相关性）
- 什么是 RAGAS 评估框架？

---

### Day 21：缓冲日 / 复习
- 回顾第三周内容
- 整理笔记
- 代码重构（如果发现之前的设计不够好）

---

## 第四周：界面与打磨（Streamlit → Demo → 面试准备）

### Day 22：Streamlit 聊天界面
**任务：**
- [ ] 在 `main.py` 中搭建基本聊天 UI
  - `st.set_page_config` 设置页面标题和布局
  - `st.session_state` 管理聊天历史和会话状态
  - `st.chat_input` + `st.chat_message` 构建对话界面
  - 接入 orchestrator：用户发消息 → 显示答案

**学习重点：**
- Streamlit 的 session_state 机制
- 聊天应用的 UI 设计模式

---

### Day 23：侧边栏控制面板
**任务：**
- [ ] 实现侧边栏：
  - 检索模式选择（快速 vs 深度推理）
  - 系统模块多选过滤
  - 角色选择器（一线运维 / 二线专家 / 安全审计员）
  - 清空对话按钮
- [ ] 角色选择影响元数据过滤规则
- [ ] 快速模式跳过查询重写和多步推理

**学习重点：**
- 元数据过滤在产品中的实际应用（权限、范围控制）
- 快速模式 vs 深度模式的架构差异

---

### Day 24：引用展示 + 来源高亮
**任务：**
- [ ] 在每条回答下方添加可折叠的引用区域（`st.expander`）
- [ ] 展示引用来源：文件名 + 段落号 + 文本片段
- [ ] 可选：用 `html` 标签高亮 chunk 中与查询关键词匹配的部分

**学习重点：**
- 引用溯源在 RAG 产品中的信任建立价值
- Web 前端如何做文本高亮匹配？

---

### Day 25：错误处理与降级
**任务：**
- [ ] 每一层都加 try/except 和用户友好的错误提示：
  - LLM 不可用 → 展示检索结果原文（不生成回答）
  - Qdrant 连接失败 → 启动时提示
  - 知识库为空 → 提示先运行 data_loader.py
  - 查询太短 → 验证并提示
- [ ] 所有 API 调用加 timeout

**学习重点：**
- 生产系统的优雅降级（Graceful Degradation）原则
- "宁可部分功能不正常，也不要整个系统崩溃"

---

### Day 26：端到端测试 + README
**任务：**
- [ ] 完整走一遍 demo 流程
- [ ] 写 README.md（面试官会看）：
  - 项目简介 + 架构图（ASCII 就行）
  - 6 个技术亮点
  - 安装与运行指南
  - 技术栈
- [ ] 准备 5-6 个 Demo 查询，展示每个技术亮点

---

### Day 27：面试准备 + 打磨
**任务：**
- [ ] 整理每个技术亮点的 "一句话解释"
- [ ] 准备以下面试问题的回答：
  - "为什么选择混合检索而不是纯向量检索？"
  - "重排序在你的系统中是怎么工作的？"
  - "你的 RAG 系统和其他 RAG 的最大区别是什么？"
  - "遇到的最大的技术挑战是什么？怎么解决的？"
- [ ] 优化代码的可读性（注释、变量名、函数拆分）

---

### Day 28：最终审查
- [ ] 完整运行一遍，截屏/录屏
- [ ] 检查代码是否有敏感信息（API Key）
- [ ] 更新 CLAUDE.md 的项目状态
- [ ] 总结四周的收获

---

## 学习建议
1. **先理解再动手**：每写一行代码前，问自己"这段代码在 RAG 管线中处于什么位置？输入什么？输出什么？"
2. **遇到问题先自己想 5 分钟**，再问我——这样学得更深
3. **记录踩过的坑**：每天晚上我会帮你生成一份学习笔记，你可以追加自己的踩坑记录
