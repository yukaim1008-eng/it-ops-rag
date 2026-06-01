# 高阶 RAG —— 智能 IT 运维知识库

## 一句话定位
能精准回答 IT 运维问题、标注来源段落、给出可溯源解决步骤的企业级 RAG 助手。

## 核心技术（6 个亮点）
1. **混合检索**：稠密(BGE-large) + 稀疏(BM25) → RRF 融合
2. **元数据过滤**：Qdrant payload，按系统/模块/文档类型预筛选
3. **查询重写**：LLM 把"电脑很卡"→ 拆成"CPU过高""内存不足""磁盘IO高"三个精确查
4. **多步推理检索**：搜一次→判断是否够→不够自动换关键词再搜
5. **重排序**：Cross-encoder 粗筛 10 段 → 精排 Top 3
6. **引用溯源**：每条回答标 "来源：XX文档 第Y段"

## 技术栈
Python 3.13 · LangChain · Qdrant Cloud · BGE-large(SentenceTransformer) · bge-reranker-base · BM25(rank-bm25) · DeepSeek API · Streamlit

## 当前状态
✅ 完整可跑。四层架构（data_loader 离线管道 / retrieval 检索 / orchestrator 编排 / backend 独立进程 / main Streamlit 前端）已落地。
- 6 个核心亮点全部实现
- 超额完成：检索路由器、闲聊/技术自动分类、置信度警告、检索过程 trace、用户系统 + 对话历史 + 个人中心
- 知识库：8 篇 IT 运维排障文档（演示集）
