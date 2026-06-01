"""
集中配置文件 —— 所有模块从这里导入设置，避免硬编码
"""
import os
from dotenv import load_dotenv

# 解决国内 HuggingFace 连接问题：优先走镜像站
# setdefault 保证命令行显式设置的值不会被覆盖
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

load_dotenv()

# ==================== API 密钥 ====================
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
QDRANT_URL = os.getenv("QDRANT_URL", "")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")

# ==================== 模型配置 ====================
DEEPSEEK_MODEL = "deepseek-chat"
EMBEDDING_MODEL_NAME = "BAAI/bge-large-zh-v1.5"
RERANKER_MODEL_NAME = "BAAI/bge-reranker-base"

# ==================== Qdrant 配置 ====================
QDRANT_COLLECTION_NAME = "it_ops_knowledge"
VECTOR_SIZE = 1024  # BGE-large-zh-v1.5 输出 1024 维

# ==================== 文档切片配置 ====================
CHUNK_SIZE = 500       # 每个文本块的最大字符数
CHUNK_OVERLAP = 50     # 相邻块之间的重叠字符数

# ==================== 检索配置 ====================
TOP_K_RETRIEVAL = 10   # 粗召回数量（混合检索后给重排序的候选）
TOP_K_FINAL = 3         # 最终返回给 LLM 的文档块数量
RRF_K = 60              # RRF 融合算法参数（标准值）

# ==================== 多步推理配置 ====================
MAX_RETRIEVAL_ROUNDS = 2       # 最多检索轮次
MIN_SUFFICIENT_SCORE = 0.5     # 检索置信度阈值
TOP_SCORE_THRESHOLD = 0.7      # Top-1 高分阈值

# ==================== LLM 调用配置 ====================
LLM_TEMPERATURE = 0.1
LLM_MAX_TOKENS = 2048

# ==================== 路径配置 ====================
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# ==================== QA 文档加载提示词模板 ====================
QA_SYSTEM_PROMPT = """你叫"小智"，是一位专业的IT运维私人助手。你的语气亲切、专业、可靠，像一位经验丰富的运维搭档。

用户问题：{query}

参考文档：
{context}

请遵循以下规则：
1. 如果参考文档包含相关信息，请基于文档内容给出准确、详细的解答，包括具体的操作步骤和命令
2. 在每个关键信息后面标注来源，格式为：[来源: 文件名 第X段]
3. 如果参考文档不能完全回答问题，请诚实说明"抱歉，根据现有知识库，这个问题信息不足"，并给出部分相关建议
4. 回答要结构化，使用标题、列表和代码块使内容清晰可读
5. 用"你"称呼用户，语气自然不生硬，可以适当使用"建议""推荐""注意"等措辞
"""

REWRITE_PROMPT = """你是一个IT运维查询优化专家。用户提出了以下问题：

"{query}"

请将这个问题改写成2-3个更精确、更专业的IT运维检索查询，从不同角度覆盖问题可能涉及的技术点。
直接返回查询列表，每行一个查询，不要编号，不要其他内容。"""

REASONING_KEYWORD_PROMPT = """当前检索结果未能充分覆盖问题 "{query}"。
现有结果涉及：{result_summary}

请生成1-2个不同的检索关键词，覆盖可能被遗漏的技术角度。
直接返回关键词，每行一个，不要编号，不要其他内容。"""


def get_llm():
    """返回配置好的 DeepSeek LLM 实例"""
    from langchain_deepseek import ChatDeepSeek
    return ChatDeepSeek(
        model=DEEPSEEK_MODEL,
        api_key=DEEPSEEK_API_KEY,
        temperature=LLM_TEMPERATURE,
        max_tokens=LLM_MAX_TOKENS,
    )


def validate_config():
    """启动时校验必要配置项，缺失则抛出明确的中文错误提示"""
    missing = []
    if not DEEPSEEK_API_KEY or "your-" in DEEPSEEK_API_KEY:
        missing.append("DEEPSEEK_API_KEY（在 .env 文件中配置）")
    if not QDRANT_URL or "your-" in QDRANT_URL:
        missing.append("QDRANT_URL（在 .env 文件中配置）")
    if not QDRANT_API_KEY or "your-" in QDRANT_API_KEY:
        missing.append("QDRANT_API_KEY（在 .env 文件中配置）")
    if missing:
        raise ValueError(
            f"以下配置项缺失或未修改默认值，请在 .env 文件中填写：\n" +
            "\n".join(f"  - {m}" for m in missing)
        )
