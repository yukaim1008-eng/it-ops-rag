"""
离线数据管道：加载文档 → 文本切片 → 生成嵌入 → 写入 Qdrant
运行方式：python data_loader.py
"""
import json
import os
import uuid
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from config import (
    DATA_DIR,
    QDRANT_URL,
    QDRANT_API_KEY,
    QDRANT_COLLECTION_NAME,
    EMBEDDING_MODEL_NAME,
    VECTOR_SIZE,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
)
from retrieval import encode_documents
from utils import logger


# ==================== 第一步：加载文档 ====================

def load_documents(data_dir: str) -> list:
    """
    加载 data/ 下所有 .md 文件，合并 metadata.json 中的元数据
    返回 LangChain Document 对象列表
    """
    # 1. 读取 metadata.json
    metadata_path = os.path.join(data_dir, "metadata.json")
    with open(metadata_path, "r", encoding="utf-8") as f:
        all_metadata = json.load(f)

    # 2. 用 DirectoryLoader 加载所有 .md 文件
    loader = DirectoryLoader(
        path=data_dir,
        glob="**/*.md",            # 递归匹配所有子目录的 .md 文件
        loader_cls=TextLoader,     # 用 TextLoader 读取纯文本
        loader_kwargs={"encoding": "utf-8"},
        show_progress=True,        # 显示进度条
    )
    docs = loader.load()
    logger.info(f"共加载 {len(docs)} 篇文档")

    # 3. 将 metadata.json 中的元数据合并到每个 Document
    for doc in docs:
        # source 字段是文件的绝对路径，提取文件名作为 key
        filename = os.path.basename(doc.metadata["source"])
        if filename in all_metadata:
            doc.metadata.update(all_metadata[filename])
        else:
            logger.warning(f"metadata.json 中未找到 {filename} 的元数据，跳过")

    return docs


# ==================== 第二步：文本切片 ====================

def split_documents(docs: list) -> list:
    """
    将文档按中文语义边界切分成小块，每个块附带唯一 chunk_id
    """
    # 分隔符按优先级：段落 → 换行 → 句号 → 感叹号 → 问号 → 分号 → 空格 → 字符
    text_splitter = RecursiveCharacterTextSplitter(
        separators=["\n\n", "\n", "。", "！", "？", "；", " ", ""],
        chunk_size=CHUNK_SIZE,        # 每块最大 500 字符
        chunk_overlap=CHUNK_OVERLAP,  # 相邻块重叠 50 字符
    )

    chunks = text_splitter.split_documents(docs)
    logger.info(f"共切分为 {len(chunks)} 个文档块")

    # 为每个 chunk 分配唯一编号
    for i, chunk in enumerate(chunks):
        filename = os.path.basename(chunk.metadata.get("source", ""))
        chunk.metadata["chunk_id"] = f"{filename}_chunk_{i}"
        chunk.metadata["chunk_index"] = i

    return chunks


# ==================== 第三步：生成嵌入向量 ====================

def embed_chunks(chunks: list) -> list[list[float]]:
    """
    用 BGE-large 模型将每个 chunk 转为 1024 维向量
    复用 retrieval 模块的 SentenceTransformer 单例，避免重复加载模型
    注意：文档侧不需要加 instruction prefix
    """
    logger.info(f"正在用 SentenceTransformer 加载嵌入模型 {EMBEDDING_MODEL_NAME} ...")
    texts = [chunk.page_content for chunk in chunks]
    logger.info(f"正在为 {len(texts)} 个文档块生成嵌入向量...")
    return encode_documents(texts, batch_size=32)


# ==================== 第四步：写入 Qdrant ====================

def ingest_to_qdrant(chunks: list, embeddings: list[list[float]]):
    """
    将文档块和嵌入向量批量写入 Qdrant Cloud
    """
    # 1. 连接 Qdrant Cloud
    client = QdrantClient(
        url=QDRANT_URL,
        api_key=QDRANT_API_KEY,
        timeout=30,  # 网络超时 30 秒
    )
    logger.info(f"已连接 Qdrant：{QDRANT_URL}")

    # 2. 创建或重建 collection（如果已存在则删除重建）
    if client.collection_exists(QDRANT_COLLECTION_NAME):
        logger.warning(f"集合 {QDRANT_COLLECTION_NAME} 已存在，将删除重建")
        client.delete_collection(QDRANT_COLLECTION_NAME)

    client.create_collection(
        collection_name=QDRANT_COLLECTION_NAME,
        vectors_config=VectorParams(
            size=VECTOR_SIZE,       # 1024，BGE-large 的输出维度
            distance=Distance.COSINE,  # 余弦相似度
        ),
    )
    logger.info(f"已创建集合：{QDRANT_COLLECTION_NAME}")

    # 3. 构造 Point 并分批写入
    points = []
    for chunk, embedding in zip(chunks, embeddings):
        point = PointStruct(
            id=str(uuid.uuid4()),  # Qdrant 仅支持 UUID 或数字 ID
            vector=embedding,
            payload={
                "text": chunk.page_content,
                "source_file": os.path.basename(chunk.metadata.get("source", "")),
                "chunk_index": chunk.metadata.get("chunk_index", 0),
                "system_name": chunk.metadata.get("system_name", ""),
                "doc_type": chunk.metadata.get("doc_type", ""),
                "severity": chunk.metadata.get("severity", ""),
                "tags": chunk.metadata.get("tags", []),
            },
        )
        points.append(point)

    # 分批上传，每批 100 个
    batch_size = 100
    for i in range(0, len(points), batch_size):
        batch = points[i : i + batch_size]
        client.upsert(collection_name=QDRANT_COLLECTION_NAME, points=batch)
        logger.info(f"已上传 {min(i + batch_size, len(points))}/{len(points)} 个点")

    # 4. 验证入库数量
    count = client.count(QDRANT_COLLECTION_NAME).count
    logger.info(f"入库完成！集合中共 {count} 个点")
    assert count == len(chunks), f"数量不一致！chunks={len(chunks)}, Qdrant={count}"


# ==================== 主流程 ====================

if __name__ == "__main__":
    logger.info("========== 开始数据管道 ==========")

    # 第一步：加载文档
    docs = load_documents(DATA_DIR)

    # 第二步：切分
    chunks = split_documents(docs)

    # 第三步：嵌入
    embeddings = embed_chunks(chunks)

    # 第四步：入库
    ingest_to_qdrant(chunks, embeddings)

    logger.info(f"========== 完成！共入库 {len(chunks)} 个文档块 ==========")
