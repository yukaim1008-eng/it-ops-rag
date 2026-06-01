# 高阶 RAG —— 智能 IT 运维知识库

> 面向企业 IT 服务台的智能问答系统：精准回答运维问题、**标注来源段落**、给出可溯源的解决步骤。核心是"高阶检索"。

## ✨ 六大核心亮点

| # | 亮点 | 说明 |
|---|------|------|
| 1 | **混合检索** | 稠密向量（BGE-large）+ 稀疏 BM25 → **RRF 融合** |
| 2 | **元数据过滤** | Qdrant payload，按系统 / 模块 / 文档类型预筛选 |
| 3 | **查询重写** | LLM 把"电脑很卡"拆成"CPU 过高 / 内存不足 / 磁盘 IO 高"多角度精确查 |
| 4 | **多步推理检索** | 搜一次 → 判断信息是否充分 → 不够自动换关键词再搜（最多 2 轮） |
| 5 | **Cross-encoder 重排序** | 粗召回 Top-N → bge-reranker 精排 Top-3 |
| 6 | **引用溯源** | 每条回答标注「来源：XX 文档 第 Y 段」，防幻觉 |

> 超额实现：检索路由器、闲聊/技术自动分类、置信度警告、检索过程 trace、用户系统 + 对话历史 + 个人中心。

## 🏗️ 四层架构

```
main.py (Streamlit 前端：聊天 / 侧边栏过滤 / 引用展示)
   │
backend.py (独立进程：常驻加载模型，JSON 行协议)
   │
orchestrator.py (编排：查询重写 → 检索路由 → 多步推理 → 答案生成 + trace)
   │
retrieval.py (检索核心：稠密 + BM25 → RRF → 元数据过滤 → Cross-encoder 重排)
   │
data_loader.py (离线管道：加载 → 切片 → BGE 嵌入 → 写入 Qdrant)
```

对外主入口：`orchestrator.answer(query, mode="quick"|"deep", metadata_filter=None)`
→ 返回 `{"answer", "citations", "trace"}`（多 Agent 项目即通过此接口联动）

## 🛠️ 技术栈

Python 3.13 · LangChain · **Qdrant Cloud** · BGE-large-zh（SentenceTransformer）· bge-reranker-base · BM25（rank-bm25 + jieba）· DeepSeek API · Streamlit

## 🚀 运行

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 配置 .env：DEEPSEEK_API_KEY / QDRANT_URL / QDRANT_API_KEY
python data_loader.py             # 一次性：文档 → 向量库
streamlit run main.py             # 启动问答界面
```

## 📁 知识库

`data/` 下 8 篇 IT 运维排障演示文档（服务器 / 网络 / 数据库 / 应用 / 安全 / 监控），
每篇在 `data/metadata.json` 中登记元数据（系统名、文档类型、严重级、标签）。

## 🧪 踩过的坑与解决

1. HuggingFace 被墙 → 走 `hf-mirror.com` 镜像站
2. Windows 下 PyTorch + Streamlit 线程冲突 → 限制 torch 线程数 + 模型在独立进程加载
3. 查询侧需加 instruction prefix（非对称嵌入），文档侧不加
4. BM25 元数据过滤：需多召回后置过滤（稀疏检索无原生 payload 过滤）
