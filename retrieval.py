"""
检索核心层 —— 混合检索（稠密 + 稀疏）→ RRF 融合 → 重排序
"""
import os
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

# Windows 下 PyTorch + Streamlit 线程冲突：必须在 import torch 之前设置
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"

# 在 sentence_transformers（会 import torch）之前限制 torch 线程数
import torch
torch.set_num_threads(1)
# set_num_interop_threads 需在 set_num_threads 之前调用，且 OMP_NUM_THREADS=1 已足够

from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from sentence_transformers import SentenceTransformer, CrossEncoder
from rank_bm25 import BM25Okapi

from config import (
    QDRANT_URL,
    QDRANT_API_KEY,
    QDRANT_COLLECTION_NAME,
    EMBEDDING_MODEL_NAME,
    RERANKER_MODEL_NAME,
    TOP_K_RETRIEVAL,
    TOP_K_FINAL,
    RRF_K,
)
from utils import logger, tokenize_for_index, tokenize_for_query, reciprocal_rank_fusion


# ==================== 模块级缓存（懒加载，避免重复初始化） ====================

_qdrant_client = None
_embedding_model = None
_reranker = None
_bm25_index = None
_bm25_chunks = None


def _get_qdrant_client():
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=30)
    return _qdrant_client


def _get_embedding_model():
    """获取 BGE 嵌入模型（单例），查询侧编码时需手动加 instruction prefix"""
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _embedding_model


def get_embedding_model():
    """公开接口：获取嵌入模型（供 data_loader 等外部模块使用）"""
    return _get_embedding_model()


def encode_documents(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """文档侧编码（不含 query instruction prefix），供入库脚本使用"""
    model = _get_embedding_model()
    embeddings = model.encode(texts, batch_size=batch_size, show_progress_bar=True)
    return embeddings.tolist()


def _get_reranker():
    """获取 Cross-encoder 重排序模型（单例）"""
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoder(RERANKER_MODEL_NAME)
    return _reranker


def preload_models():
    """预加载所有模型（Streamlit 启动时在主线程调用，避免工作线程中加载导致 Windows 崩溃）"""
    logger.info("预加载嵌入模型和重排序模型...")
    _get_embedding_model()
    _get_reranker()
    logger.info("所有模型预加载完成")


def ensure_payload_indexes():
    """确保 Qdrant 的过滤字段有索引（否则元数据过滤会报错）"""
    from qdrant_client.models import PayloadSchemaType
    client = _get_qdrant_client()
    collection = QDRANT_COLLECTION_NAME

    if not client.collection_exists(collection):
        return

    for field in ["severity", "system_name", "doc_type"]:
        try:
            client.create_payload_index(
                collection_name=collection,
                field_name=field,
                field_schema=PayloadSchemaType.KEYWORD,
            )
            logger.info(f"已为字段 '{field}' 创建 keyword 索引")
        except Exception:
            # 索引已存在会抛异常，忽略
            pass


# ==================== 元数据过滤 ====================

def build_metadata_filter(selections: dict | None) -> Filter | None:
    if not selections:
        return None

    must_conditions = []
    for key, value in selections.items():
        must_conditions.append(
            FieldCondition(key=key, match=MatchValue(value=value))
        )

    return Filter(must=must_conditions)


# ==================== 稠密检索 ====================

def dense_search(
    query: str,
    top_k: int = TOP_K_RETRIEVAL,
    metadata_filter: dict | None = None,
) -> list[dict]:
    client = _get_qdrant_client()
    model = _get_embedding_model()

    # BGE 模型查询侧需要加 instruction prefix
    query_vector = model.encode(
        query,
        prompt="为这个句子生成表示以用于检索相关文章：",
    ).tolist()

    qdrant_filter = build_metadata_filter(metadata_filter)

    results = client.query_points(
        collection_name=QDRANT_COLLECTION_NAME,
        query=query_vector,
        limit=top_k,
        query_filter=qdrant_filter,
    )

    docs = []
    for r in results.points:
        docs.append({
            "chunk_id": r.id,
            "text": r.payload.get("text", ""),
            "source_file": r.payload.get("source_file", ""),
            "chunk_index": r.payload.get("chunk_index", 0),
            "system_name": r.payload.get("system_name", ""),
            "doc_type": r.payload.get("doc_type", ""),
            "severity": r.payload.get("severity", ""),
            "tags": r.payload.get("tags", []),
            "score": r.score,
        })

    return docs


# ==================== 稀疏检索（BM25） ====================

def init_bm25():
    global _bm25_index, _bm25_chunks

    if _bm25_index is not None:
        return  # 已初始化，跳过

    client = _get_qdrant_client()

    if not client.collection_exists(QDRANT_COLLECTION_NAME):
        logger.warning("Qdrant 集合不存在，BM25 索引初始化为空")
        _bm25_index = None
        _bm25_chunks = []
        return

    total = client.count(QDRANT_COLLECTION_NAME).count
    if total == 0:
        logger.warning("Qdrant 集合为空，BM25 索引初始化为空")
        _bm25_index = None
        _bm25_chunks = []
        return

    logger.info(f"正在构建 BM25 索引，共 {total} 个文档块...")
    all_points = []
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=QDRANT_COLLECTION_NAME,
            limit=100,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        all_points.extend(points)
        if offset is None:
            break

    tokenized_corpus = [tokenize_for_index(p.payload.get("text", "")) for p in all_points]
    _bm25_index = BM25Okapi(tokenized_corpus)
    _bm25_chunks = all_points
    logger.info(f"BM25 索引构建完成，{len(all_points)} 个文档")


def bm25_search(
    query: str,
    top_k: int = TOP_K_RETRIEVAL,
    metadata_filter: dict | None = None,
) -> list[dict]:
    if _bm25_index is None:
        logger.warning("BM25 索引未初始化，返回空结果")
        return []

    tokenized_query = tokenize_for_query(query)
    scores = _bm25_index.get_scores(tokenized_query)

    indexed_scores = list(enumerate(scores))
    indexed_scores.sort(key=lambda x: x[1], reverse=True)

    results = []
    for idx, score in indexed_scores:
        point = _bm25_chunks[idx]
        payload = point.payload

        # 后置元数据过滤
        if metadata_filter:
            skip = False
            for key, value in metadata_filter.items():
                if payload.get(key) != value:
                    skip = True
                    break
            if skip:
                continue

        results.append({
            "chunk_id": point.id,
            "text": payload.get("text", ""),
            "source_file": payload.get("source_file", ""),
            "chunk_index": payload.get("chunk_index", 0),
            "system_name": payload.get("system_name", ""),
            "doc_type": payload.get("doc_type", ""),
            "severity": payload.get("severity", ""),
            "tags": payload.get("tags", []),
            "score": float(score),
        })

        if len(results) >= top_k:
            break

    return results


# ==================== 混合检索 + RRF 融合 ====================

def hybrid_search(
    query: str,
    top_k: int = TOP_K_RETRIEVAL,
    metadata_filter: dict | None = None,
    dense_weight: float = 1.0,
    sparse_weight: float = 1.0,
) -> list[dict]:
    dense_results = dense_search(query, top_k=top_k, metadata_filter=metadata_filter)
    sparse_results = bm25_search(query, top_k=top_k, metadata_filter=metadata_filter)

    dense_wrapped = [(r, r["score"]) for r in dense_results]
    sparse_wrapped = [(r, r["score"]) for r in sparse_results]

    fused = reciprocal_rank_fusion(
        dense_wrapped, sparse_wrapped,
        rrf_k=RRF_K,
        dense_weight=dense_weight,
        sparse_weight=sparse_weight,
    )

    merged = []
    seen = set()
    for doc, rrf_score in fused:
        cid = doc["chunk_id"]
        if cid not in seen:
            seen.add(cid)
            doc["rrf_score"] = rrf_score
            merged.append(doc)
        if len(merged) >= top_k:
            break

    return merged


# ==================== 重排序（Cross-Encoder） ====================

def rerank(
    query: str,
    candidates: list[dict],
    top_k: int = TOP_K_FINAL,
) -> list[dict]:
    if not candidates:
        return []

    # 过滤掉空文本的候选（会导致 tokenizer 报错）
    valid_candidates = [c for c in candidates if c.get("text", "").strip()]
    if not valid_candidates:
        return []

    reranker = _get_reranker()

    # CrossEncoder.predict() 输入 (query, document) 对列表
    pairs = [(query, c["text"]) for c in valid_candidates]
    logger.info(f"Rerank: {len(pairs)} pairs, query={query[:50]}, first_text_len={len(pairs[0][1]) if pairs else 0}")
    scores = reranker.predict(pairs)  # 返回 numpy array

    for i, candidate in enumerate(valid_candidates):
        candidate["rerank_score"] = float(scores[i])

    valid_candidates.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
    return valid_candidates[:top_k]


# ==================== 完整检索管线 ====================

def retrieve(
    query: str,
    top_k_retrieval: int = TOP_K_RETRIEVAL,
    top_k_final: int = TOP_K_FINAL,
    metadata_filter: dict | None = None,
    dense_weight: float = 1.0,
    sparse_weight: float = 1.0,
) -> list[dict]:
    candidates = hybrid_search(
        query, top_k=top_k_retrieval, metadata_filter=metadata_filter,
        dense_weight=dense_weight, sparse_weight=sparse_weight,
    )
    logger.info(f"混合检索召回 {len(candidates)} 个候选（Dense权重={dense_weight}, Sparse权重={sparse_weight}）")

    final = rerank(query, candidates, top_k=top_k_final)
    logger.info(f"重排序后保留 Top-{len(final)}")

    return final
