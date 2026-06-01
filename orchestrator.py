"""
智能编排层 —— 查询重写 → 多步推理检索 → 答案生成（含 trace 追踪 & 流式输出）
"""
from langchain_deepseek import ChatDeepSeek

from config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_MODEL,
    LLM_TEMPERATURE,
    LLM_MAX_TOKENS,
    TOP_K_FINAL,
    MAX_RETRIEVAL_ROUNDS,
    MIN_SUFFICIENT_SCORE,
    TOP_SCORE_THRESHOLD,
    REWRITE_PROMPT,
    REASONING_KEYWORD_PROMPT,
    QA_SYSTEM_PROMPT,
)
from retrieval import retrieve, hybrid_search, rerank
from utils import logger

import re


# ==================== LLM 工厂 ====================

def _get_llm():
    """每次调用创建新的 LLM 实例（LangChain 的 ChatDeepSeek 是无状态的）"""
    return ChatDeepSeek(
        model=DEEPSEEK_MODEL,
        api_key=DEEPSEEK_API_KEY,
        temperature=LLM_TEMPERATURE,
        max_tokens=LLM_MAX_TOKENS,
    )


# ==================== 查询重写 ====================

def rewrite_query(original_query: str) -> list[str]:
    """
    用 LLM 将模糊的用户问题改写成 2-3 条精确的 IT 运维检索查询
    例如："电脑很卡" → ["CPU使用率过高排查", "内存不足诊断", "磁盘IO性能问题"]
    """
    llm = _get_llm()
    prompt = REWRITE_PROMPT.format(query=original_query)

    try:
        response = llm.invoke(prompt)
        content = response.content.strip()

        # 按行分割，过滤空行和编号前缀
        lines = []
        for line in content.split("\n"):
            line = line.strip()
            # 去掉可能的编号前缀 "1." "1、" "- " 等
            line = line.lstrip("0123456789.、- ") .strip()
            if line and len(line) > 2:
                lines.append(line)

        # 去重，保留顺序
        seen = set()
        queries = []
        for line in lines:
            if line not in seen and line != original_query:
                seen.add(line)
                queries.append(line)

        if not queries:
            logger.warning("查询重写返回空，使用原始查询")
            return [original_query]

        logger.info(f"查询重写：{original_query} → {queries}")
        return queries[:3]  # 最多 3 条

    except Exception as e:
        logger.error(f"查询重写失败：{e}，使用原始查询")
        return [original_query]


# ==================== 检索路由器 ====================

def route_retrieval(query: str) -> dict:
    """
    根据查询特征判断检索策略偏向，返回 Dense/BM25 权重。

    规则（非 LLM，零延迟）：
    - 含错误码（如 ERR-001、SSL-EXPIRED）→ BM25 权重高（精确匹配）
    - 自然语言疑问句（怎么/如何/为什么…）→ Dense 权重高（语义匹配）
    - 默认 → 等权重
    """
    # 错误码模式：大写字母-数字
    if re.search(r'[A-Z]+-\d+', query):
        logger.info(f"路由：检测到错误码 → 偏向 BM25 精确匹配")
        return {"dense_weight": 0.3, "sparse_weight": 1.0, "reason": "检测到错误码，偏向 BM25 精确匹配"}

    # 错误码模式：英文缩写+连字符（如 SSL-EXPIRED）
    if re.search(r'[A-Z]{2,}-[A-Z]+', query):
        logger.info(f"路由：检测到英文错误标识 → 偏向 BM25 精确匹配")
        return {"dense_weight": 0.3, "sparse_weight": 1.0, "reason": "检测到英文错误标识，偏向 BM25 精确匹配"}

    # 自然语言疑问句
    question_keywords = ['怎么', '如何', '为什么', '是什么', '怎么办', '什么原因', '怎样', '排查', '步骤']
    if any(kw in query for kw in question_keywords):
        logger.info(f"路由：检测到自然语言疑问 → 偏向 Dense 语义匹配")
        return {"dense_weight": 1.0, "sparse_weight": 0.3, "reason": "检测到自然语言疑问，偏向 Dense 语义匹配"}

    # 默认等权重
    logger.info(f"路由：默认等权重")
    return {"dense_weight": 1.0, "sparse_weight": 1.0, "reason": "默认等权重混合检索"}


# ==================== 检索质量判断 ====================

def is_retrieval_sufficient(results: list[dict]) -> bool:
    """
    判断检索结果是否充分：
    - 条件 A：至少 3 个结果的 rerank 分数 >= 0.5
    - 条件 B：Top-1 分数 >= 0.7
    满足任一条件即为充分
    """
    if not results:
        return False

    top_score = results[0].get("rerank_score", 0)
    sufficient_count = sum(
        1 for r in results if r.get("rerank_score", 0) >= MIN_SUFFICIENT_SCORE
    )

    return top_score >= TOP_SCORE_THRESHOLD or sufficient_count >= 3


# ==================== 多步推理检索 ====================

def multi_step_retrieve(
    query: str,
    metadata_filter: dict | None = None,
    max_rounds: int = MAX_RETRIEVAL_ROUNDS,
    dense_weight: float = 1.0,
    sparse_weight: float = 1.0,
) -> tuple[list[dict], list[dict]]:
    """
    多步推理检索，返回 (结果列表, 轮次 trace)
    """
    all_results = []
    round_traces = []

    # Round 1：初始检索
    logger.info(f"[Round 1] 检索：{query}")
    round1_results = retrieve(query, metadata_filter=metadata_filter,
                              dense_weight=dense_weight, sparse_weight=sparse_weight)
    all_results.extend(round1_results)

    top_score = round1_results[0].get("rerank_score", 0) if round1_results else 0
    round_traces.append({
        "round": 1,
        "query": query,
        "candidates_count": len(round1_results),
        "final_count": len(round1_results),
        "top_score": round(top_score, 3),
        "sources": [r.get("source_file", "") for r in round1_results[:3]],
        "sufficient": is_retrieval_sufficient(round1_results),
    })

    if is_retrieval_sufficient(round1_results):
        logger.info(f"[Round 1] 检索充分，Top-1 分数：{top_score:.3f}")
        return _merge_and_dedup(all_results), round_traces

    # Round 2：LLM 生成新关键词再搜
    logger.info(f"[Round 1] 检索不充分，启动 Round 2")
    result_summary = "、".join([r.get("source_file", "") for r in round1_results[:5]])

    llm = _get_llm()
    keyword_prompt = REASONING_KEYWORD_PROMPT.format(query=query, result_summary=result_summary)

    try:
        response = llm.invoke(keyword_prompt)
        keywords = []
        for line in response.content.strip().split("\n"):
            line = line.strip().lstrip("0123456789.、- ").strip()
            if line and len(line) > 1:
                keywords.append(line)
        keywords = keywords[:2]  # 最多 2 个新关键词
    except Exception as e:
        logger.error(f"Round 2 关键词生成失败：{e}")
        keywords = []

    for keyword in keywords:
        logger.info(f"[Round 2] 检索：{keyword}")
        round2_results = retrieve(keyword, metadata_filter=metadata_filter,
                                  dense_weight=dense_weight, sparse_weight=sparse_weight)
        all_results.extend(round2_results)
        top2 = round2_results[0].get("rerank_score", 0) if round2_results else 0
        round_traces.append({
            "round": 2,
            "query": keyword,
            "candidates_count": len(round2_results),
            "final_count": len(round2_results),
            "top_score": round(top2, 3),
            "sources": [r.get("source_file", "") for r in round2_results[:3]],
            "sufficient": is_retrieval_sufficient(round2_results),
        })

    return _merge_and_dedup(all_results), round_traces


def _merge_and_dedup(results: list[dict]) -> list[dict]:
    """合并多轮检索结果，按 chunk_id 去重，按 rerank_score 降序"""
    seen = set()
    merged = []
    for r in sorted(results, key=lambda x: x.get("rerank_score", 0), reverse=True):
        cid = r.get("chunk_id", id(r))
        if cid not in seen:
            seen.add(cid)
            merged.append(r)
    return merged[:TOP_K_FINAL]


# ==================== 答案生成 ====================

def generate_answer(query: str, context_chunks: list[dict]) -> dict:
    """
    基于检索到的文档块，用 LLM 生成带引用的答案

    Returns:
        {"answer": str, "citations": [{"source_file": str, "chunk_index": int, "text": str}, ...]}
    """
    if not context_chunks:
        return {
            "answer": "抱歉，知识库中未找到相关信息，请尝试换个关键词或联系运维团队进一步排查。",
            "citations": [],
        }

    # 格式化上下文：每条标注来源
    context_parts = []
    for i, chunk in enumerate(context_chunks, 1):
        source = chunk.get("source_file", "未知")
        idx = chunk.get("chunk_index", 0)
        text = chunk.get("text", "")
        context_parts.append(f"[文档{i}] 来源：{source} 第{idx}段\n{text}")

    formatted_context = "\n\n".join(context_parts)

    # 构建 Prompt
    prompt = QA_SYSTEM_PROMPT.format(query=query, context=formatted_context)

    llm = _get_llm()

    try:
        response = llm.invoke(prompt)
        answer_text = response.content.strip()
    except Exception as e:
        logger.error(f"答案生成失败：{e}")
        return {
            "answer": f"LLM 服务暂时不可用，以下为检索到的相关文档片段：\n\n{formatted_context}",
            "citations": context_chunks,
        }

    # 整理引用
    citations = []
    for chunk in context_chunks:
        citations.append({
            "source_file": chunk.get("source_file", ""),
            "chunk_index": chunk.get("chunk_index", 0),
            "text": chunk.get("text", "")[:200],  # 截取前 200 字符展示
        })

    return {
        "answer": answer_text,
        "citations": citations,
    }


# ==================== 问题分类 ====================

def classify_query(context_chunks: list[dict]) -> str:
    """
    根据检索分数自动判断问题类型（零维护，不需要关键词库）：
    - Top-1 rerank_score >= 0.25 → tech（知识库有匹配）
    - 否则 → chat（知识库无相关内容，大概率是闲聊）
    """
    if not context_chunks:
        return "chat"
    top_score = context_chunks[0].get("rerank_score", 0)
    return "tech" if top_score >= 0.25 else "chat"


# ==================== 置信度判断 ====================

LOW_CONFIDENCE_THRESHOLD = 0.3


def check_confidence(context_chunks: list[dict], query_type: str = "tech") -> str | None:
    """
    检查检索置信度，仅对技术问题返回警告。闲聊不显示。
    """
    if query_type == "chat":
        return None
    if not context_chunks:
        return None
    top_score = context_chunks[0].get("rerank_score", 0)
    if top_score < LOW_CONFIDENCE_THRESHOLD:
        return f"⚠️ 此回答置信度较低（检索匹配度 {top_score:.2f}），建议补充相关文档或换个角度提问。\n\n"
    return None


# ==================== 主编排入口 ====================

def answer(
    query: str,
    mode: str = "quick",
    metadata_filter: dict | None = None,
) -> dict:
    """
    RAG 系统主入口

    Args:
        query: 用户问题
        mode: "quick"（快速模式，跳过重写和多步推理）或 "deep"（深度推理模式）
        metadata_filter: 元数据过滤条件

    Returns:
        {"answer": str, "citations": list[dict], "trace": dict}
    """
    logger.info(f"收到查询 [{mode}模式]：{query}")

    # ---- 先执行检索（始终执行，用分数判断问题类型） ----
    routing = route_retrieval(query)
    dense_weight = routing["dense_weight"]
    sparse_weight = routing["sparse_weight"]

    if mode == "deep":
        rewritten = rewrite_query(query)
        all_context = []
        all_rounds = []
        for q in rewritten:
            chunks, rounds = multi_step_retrieve(q, metadata_filter=metadata_filter,
                                                  dense_weight=dense_weight, sparse_weight=sparse_weight)
            all_context.extend(chunks)
            all_rounds.extend(rounds)
        context = _merge_and_dedup(all_context)
        rounds_trace = all_rounds
    else:
        context = retrieve(query, metadata_filter=metadata_filter,
                           dense_weight=dense_weight, sparse_weight=sparse_weight)
        top_score = context[0].get("rerank_score", 0) if context else 0
        rounds_trace = [{
            "round": 1,
            "query": query,
            "candidates_count": len(context),
            "final_count": len(context),
            "top_score": round(top_score, 3),
            "sources": [r.get("source_file", "") for r in context[:3]],
            "sufficient": is_retrieval_sufficient(context),
        }]

    # ---- 根据检索分数判断问题类型 ----
    query_type = classify_query(context)

    trace = {
        "mode": mode,
        "query_type": query_type,
        "routing": routing,
        "rewritten_queries": rewritten if mode == "deep" else [],
        "rounds": rounds_trace,
    }

    # ---- 闲聊模式：检索分数低 → 直接 LLM 聊天，不显示引用和置信度 ----
    if query_type == "chat":
        logger.info(f"检索分数低（Top-1={context[0].get('rerank_score', 0):.3f}），判定为闲聊")
        llm = _get_llm()
        chat_prompt = f"""你叫"小智"，是一位专业的IT运维私人助手。用户正在和你闲聊。

用户说：{query}

请友好、自然地回复。如果用户的话与IT运维完全无关，简单回应即可，控制在2-4句话。"""
        try:
            response = llm.invoke(chat_prompt)
            answer_text = response.content.strip()
        except Exception as e:
            answer_text = "你好呀！有什么运维问题需要帮忙吗？"
        return {
            "answer": answer_text,
            "citations": [],
            "trace": trace,
        }

    # ---- 技术模式：正常 RAG 流程 ----
    confidence_warning = check_confidence(context, query_type="tech")
    trace["low_confidence"] = confidence_warning is not None
    trace["top_score"] = context[0].get("rerank_score", 0) if context else 0

    result = generate_answer(query, context)

    if confidence_warning:
        result["answer"] = confidence_warning + result["answer"]

    result["trace"] = trace

    logger.info(f"答案生成完成，共 {len(result['citations'])} 条引用")
    return result
