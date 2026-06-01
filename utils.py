"""
通用工具函数 —— BM25 分词、去重合并、日志配置
"""
import logging
import jieba
from collections import OrderedDict


def setup_logger(name: str = "it_ops_rag", level: int = logging.INFO) -> logging.Logger:
    """创建统一的日志记录器"""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
        )
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger


logger = setup_logger()


# ==================== BM25 分词工具 ====================

def tokenize_for_index(text: str) -> list[str]:
    """
    文档侧分词：使用 jieba.cut 精确模式
    用于构建 BM25 索引
    """
    return list(jieba.cut(text))


def tokenize_for_query(text: str) -> list[str]:
    """
    查询侧分词：使用 jieba.cut_for_search 搜索引擎模式
    会对复合词进行更细粒度的拆分，提高召回率
    """
    return list(jieba.cut_for_search(text))


# ==================== 检索结果去重合并 ====================

def dedup_by_chunk_id(results: list) -> list:
    """
    按 chunk_id 去重，保留首次出现的条目（即排名更靠前的）

    Args:
        results: 列表，每项为 (chunk_id, score) 或带有 metadata 的对象

    Returns:
        去重后的列表，保持原有顺序
    """
    seen = set()
    deduped = []
    for item in results:
        # 兼容多种返回格式
        if isinstance(item, tuple) and len(item) >= 1:
            obj = item[0]
            chunk_id = getattr(obj, "metadata", {}).get("chunk_id", id(obj))
        else:
            chunk_id = getattr(item, "metadata", {}).get("chunk_id", id(item))

        if chunk_id not in seen:
            seen.add(chunk_id)
            deduped.append(item)
    return deduped


# ==================== RRF 融合 ====================

def reciprocal_rank_fusion(
    dense_results: list,
    sparse_results: list,
    rrf_k: int = 60,
    dense_weight: float = 1.0,
    sparse_weight: float = 1.0,
) -> list:
    """
    加权 RRF (Reciprocal Rank Fusion) 融合稠密检索和稀疏检索的结果

    算法：对每个文档，计算 w_i * sum(1 / (k + rank_i))，
    其中 w_i 是检索器的权重，rank_i 是该文档在第 i 个检索器中的排名（从 1 开始）

    Args:
        dense_results: 稠密检索结果列表 [(doc, score), ...]
        sparse_results: 稀疏检索结果列表 [(doc, score), ...]
        rrf_k: RRF 参数，默认 60
        dense_weight: 稠密检索权重（默认 1.0）
        sparse_weight: 稀疏检索权重（默认 1.0）

    Returns:
        按 RRF 分数降序排列的列表 [(doc, rrf_score), ...]
    """
    rrf_scores = {}
    doc_map = {}

    # 稠密检索结果（加权）
    for rank, item in enumerate(dense_results, start=1):
        doc = item[0] if isinstance(item, tuple) else item
        doc_id = doc.get("chunk_id", str(rank)) if isinstance(doc, dict) else doc.metadata.get("chunk_id", str(rank))
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + dense_weight / (rrf_k + rank)
        doc_map[doc_id] = doc

    # 稀疏检索结果（加权）
    for rank, item in enumerate(sparse_results, start=1):
        doc = item[0] if isinstance(item, tuple) else item
        doc_id = doc.get("chunk_id", str(rank)) if isinstance(doc, dict) else doc.metadata.get("chunk_id", str(rank))
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + sparse_weight / (rrf_k + rank)
        doc_map[doc_id] = doc

    # 按 RRF 分数降序排列
    sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)
    return [(doc_map[doc_id], rrf_scores[doc_id]) for doc_id in sorted_ids]
