"""
检索效果评估 (Retrieval Eval) —— 量化各检索策略的命中率与排序质量

默认（不调 LLM，秒级）对比 4 种「原语」策略：
  bm25    纯稀疏 BM25                （诊断：确认稀疏索引本身有效）
  dense   纯稠密 BGE-large
  hybrid  混合 = Dense + BM25 → RRF 融合
  rerank  混合 + Cross-Encoder 重排   （≈ 系统 quick 模式的检索）

加 --deep 再多跑一档（需 DEEPSEEK_API_KEY，分钟级 + 少量 LLM 费用）：
  deep    路由 → 查询重写 → 多步推理检索   （系统 deep 模式的真实管线）
  ↑ 这一档专门解决「口语 / 中英混杂 / 同义词」导致的召回 miss，
    它相对 rerank 的提升，就是简历里「查询重写 + 多步推理」的真实增益。

指标：Recall@1 / Recall@3 / MRR
产出：eval_report.md（可读 / 测试报告）+ eval_report.json（机读）

用法（在 it-ops-rag 目录下）：
    python eval_retrieval.py            # 仅原语 4 档，快
    python eval_retrieval.py --deep     # 加 deep 真实管线对比（推荐，出简历主数字）
"""
import sys
import json
import time
from datetime import datetime

from config import QDRANT_COLLECTION_NAME, DEEPSEEK_API_KEY
from retrieval import (
    dense_search,
    bm25_search,
    hybrid_search,
    rerank,
    init_bm25,
    preload_models,
    _get_qdrant_client,
)

# ==================== Gold 评测集：口语化问题 → 应命中的源文档 ====================
# 刻意用「症状 / 口语」描述，而非照抄文档标题，保证对「语义检索 / 查询重写」有真实区分度。
GOLD = [
    {"q": "MySQL 查询特别慢，怎么定位和优化？",           "gold": "database_slow_query"},
    {"q": "服务器内存占用一直往上涨，怀疑哪里泄漏了",       "gold": "server_memory_leak"},
    {"q": "网站访问报 502 Bad Gateway，怎么排查？",        "gold": "app_nginx_502"},
    {"q": "域名突然解析不了，ping 域名不通但 IP 能通",      "gold": "network_dns_failure"},
    {"q": "两个事务互相等锁，数据库像是死锁了",             "gold": "database_deadlock"},
    {"q": "磁盘空间满了导致服务起不来",                     "gold": "server_disk_full"},
    {"q": "Docker 容器一直反复重启、起来就崩",              "gold": "docker_container_crash"},
    {"q": "消息队列消费积压越来越多、延迟很高",             "gold": "mq_kafka_consumer_lag"},
    {"q": "HTTPS 网站浏览器提示证书已过期",                "gold": "security_ssl_expiry"},
    {"q": "后台出现大量登录失败，疑似被暴力破解",           "gold": "security_brute_force"},
    {"q": "Java 应用抛 OutOfMemoryError、堆内存溢出",       "gold": "app_jvm_oom"},
    {"q": "CPU 飙到 100%，怎么找出是哪个进程/线程？",       "gold": "server_cpu_high"},
    {"q": "接口大量超时，线程池好像被打满了",               "gold": "app_thread_pool_exhausted"},
    {"q": "应用报 too many connections、连接池耗尽",        "gold": "database_connection_exhausted"},
    {"q": "想给服务器搭一套指标监控和告警，用什么？",       "gold": "monitoring_prometheus_setup"},
    {"q": "跨机房网络偶发丢包、延迟抖动严重",               "gold": "network_packet_loss"},
    {"q": "客户端连服务直接报 connection refused",         "gold": "network_connection_refused"},
    {"q": "系统 load average 很高，但 CPU 又没满",          "gold": "server_high_load"},
    {"q": "大量缓存同时失效，请求全打到数据库、接口大面积超时", "gold": "cache_avalanche"},
    {"q": "Redis 内存快满了，写入报 OOM、key 被大量淘汰",      "gold": "cache_redis_memory"},
]

TOP_N = 10  # 每种策略取前 N 个候选用于计算 MRR；Recall@k 取前 k

RAW_MODES = ["bm25", "dense", "hybrid", "rerank"]
MODE_LABEL = {
    "bm25":   "纯稀疏 BM25",
    "dense":  "纯稠密 Dense",
    "hybrid": "混合 Hybrid(RRF)",
    "rerank": "混合+重排 quick",
    "deep":   "deep 重写+多步",
}


def _sources(results):
    """从检索结果列表按顺序提取 source_file"""
    return [(r.get("source_file") or "") for r in results]


def _first_rank(sources, gold):
    """gold 在 sources 中的首次命中排名(1-based)；未命中返回 None"""
    for i, s in enumerate(sources):
        if gold in s:
            return i + 1
    return None


def _deep_retrieve(query):
    """复刻 orchestrator.answer(mode='deep') 的检索路径（不生成答案），返回有序 source 列表。
    路由 → 查询重写(LLM) → 每条改写做多步推理检索 → 合并去重(按 rerank 分数)。"""
    from orchestrator import rewrite_query, multi_step_retrieve, route_retrieval

    routing = route_retrieval(query)
    dw, sw = routing["dense_weight"], routing["sparse_weight"]
    rewritten = rewrite_query(query)

    pool = []
    for sub_q in rewritten:
        chunks, _ = multi_step_retrieve(sub_q, dense_weight=dw, sparse_weight=sw)
        pool.extend(chunks)

    # 本地合并去重（不截断，便于按完整排名算 MRR）
    seen, merged = set(), []
    for r in sorted(pool, key=lambda x: x.get("rerank_score", 0), reverse=True):
        cid = r.get("chunk_id", id(r))
        if cid not in seen:
            seen.add(cid)
            merged.append(r)
    return _sources(merged)


def _run_modes(query, include_deep):
    """对单条 query 跑各策略，返回 {mode: 有序 source 列表}"""
    out = {}
    out["bm25"] = _sources(bm25_search(query, top_k=TOP_N))
    out["dense"] = _sources(dense_search(query, top_k=TOP_N))

    hyb = hybrid_search(query, top_k=TOP_N)
    hyb_sorted = sorted(hyb, key=lambda d: d.get("rrf_score", 0), reverse=True)
    out["hybrid"] = _sources(hyb_sorted)
    out["rerank"] = _sources(rerank(query, list(hyb), top_k=TOP_N))

    if include_deep:
        out["deep"] = _deep_retrieve(query)
    return out


def evaluate(include_deep):
    # 预检
    client = _get_qdrant_client()
    if not client.collection_exists(QDRANT_COLLECTION_NAME):
        raise SystemExit(f"❌ Qdrant 集合 '{QDRANT_COLLECTION_NAME}' 不存在，请先运行 data_loader 入库。")
    chunk_count = client.count(QDRANT_COLLECTION_NAME).count
    if chunk_count == 0:
        raise SystemExit("❌ 知识库为空，请先入库。")
    if include_deep and (not DEEPSEEK_API_KEY or "your-" in DEEPSEEK_API_KEY):
        raise SystemExit("❌ --deep 模式需要 .env 里配置有效的 DEEPSEEK_API_KEY（查询重写要调 LLM）。")
    print(f"✅ 知识库就绪：{chunk_count} 个文档块"
          + ("　|　deep 模式开启（含查询重写 + 多步推理，较慢且有少量 LLM 费用）" if include_deep else ""))

    print("加载模型 + 构建 BM25 索引中…")
    preload_models()
    init_bm25()

    modes = RAW_MODES + (["deep"] if include_deep else [])
    agg = {m: {"r1": 0, "r3": 0, "mrr": 0.0} for m in modes}
    per_query = []

    t0 = time.time()
    for i, item in enumerate(GOLD, 1):
        q, gold = item["q"], item["gold"]
        if include_deep:
            print(f"  [{i}/{len(GOLD)}] {q[:24]}…")
        res = _run_modes(q, include_deep)
        row = {"q": q, "gold": gold}
        for m in modes:
            rank = _first_rank(res[m], gold)
            row[m] = rank
            if rank is not None:
                if rank <= 1:
                    agg[m]["r1"] += 1
                if rank <= 3:
                    agg[m]["r3"] += 1
                agg[m]["mrr"] += 1.0 / rank
        per_query.append(row)
    elapsed = time.time() - t0

    n = len(GOLD)
    summary = {
        m: {
            "recall@1": agg[m]["r1"] / n,
            "recall@3": agg[m]["r3"] / n,
            "mrr": agg[m]["mrr"] / n,
        }
        for m in modes
    }
    _print_and_save(summary, per_query, modes, n, chunk_count, elapsed, include_deep)


def _print_and_save(summary, per_query, modes, n, chunk_count, elapsed, include_deep):
    lines = []

    def out(s=""):
        print(s)
        lines.append(s)

    out("\n" + "=" * 62)
    out(f"检索效果评估报告  ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
    out(f"评测集：{n} 条口语化问题 · 知识库 {chunk_count} 个文档块 · 耗时 {elapsed:.1f}s")
    out("=" * 62)
    out(f"{'策略':<18}{'Recall@1':>10}{'Recall@3':>10}{'MRR':>8}")
    out("-" * 46)
    for m in modes:
        s = summary[m]
        out(f"{MODE_LABEL[m]:<18}{s['recall@1']*100:>9.1f}%{s['recall@3']*100:>9.1f}%{s['mrr']:>8.3f}")
    out("-" * 46)

    out("\n关键结论：")
    if include_deep:
        rk, dp = summary["rerank"], summary["deep"]
        out(f"  · 【简历主数字】查询重写+多步推理 vs quick 检索：")
        out(f"      Recall@3 {rk['recall@3']*100:.1f}% → {dp['recall@3']*100:.1f}% "
            f"(+{(dp['recall@3']-rk['recall@3'])*100:.1f} 个百分点)；"
            f"MRR {rk['mrr']:.3f} → {dp['mrr']:.3f}")
    rerank, dense = summary["rerank"], summary["dense"]
    out(f"  · 混合+重排 vs 纯稠密：Recall@3 {dense['recall@3']*100:.1f}% → {rerank['recall@3']*100:.1f}% "
        f"(+{(rerank['recall@3']-dense['recall@3'])*100:.1f} 个百分点)")
    out(f"  · BM25-only 诊断：Recall@3 {summary['bm25']['recall@3']*100:.1f}%（确认稀疏索引是否有效）")

    out("\n逐条命中排名（数字=gold 排名，✗=Top-10 外）：")
    head = f"{'问题':<26}" + "".join(f"{MODE_LABEL[m][:6]:>8}" for m in modes)
    out(head)
    for row in per_query:
        def fmt(v):
            return "✗" if v is None else str(v)
        line = f"{row['q'][:24]:<26}" + "".join(f"{fmt(row[m]):>8}" for m in modes)
        out(line)
    out("=" * 62)

    with open("eval_report.md", "w", encoding="utf-8") as f:
        f.write("# 检索效果评估报告\n\n")
        f.write("> IT 运维知识库 RAG —— 多检索策略命中率对比\n\n")
        f.write("```\n" + "\n".join(lines).lstrip("\n") + "\n```\n")
    with open("eval_report.json", "w", encoding="utf-8") as f:
        json.dump(
            {"summary": summary, "per_query": per_query, "modes": modes,
             "n": n, "chunk_count": chunk_count, "deep": include_deep},
            f, ensure_ascii=False, indent=2,
        )
    print("\n📄 已保存：eval_report.md / eval_report.json")


if __name__ == "__main__":
    evaluate(include_deep="--deep" in sys.argv)
