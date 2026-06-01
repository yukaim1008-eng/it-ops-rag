"""
RAG 后端进程 —— 在独立 Python 进程中加载模型并处理查询
通过 stdin/stdout JSON 行协议与 Streamlit 前端通信

协议：
  请求: {"query": "...", "mode": "quick|deep", "filter_json": "...|null"}
  响应: {"answer": "...", "citations": [...], "trace": {...}}
"""
import sys
import json
import os

# Windows 下 stdin/stdout 默认 GBK，强制 UTF-8
sys.stdin.reconfigure(encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"

import torch
torch.set_num_threads(1)

from retrieval import preload_models, init_bm25, ensure_payload_indexes
from orchestrator import answer


def _write_json(obj: dict):
    """写一行 JSON 到 stdout 并 flush"""
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


# ---- 启动：加载模型 ----
ensure_payload_indexes()
init_bm25()
preload_models()
print("READY", flush=True)

# ---- 主循环 ----
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue

    try:
        request = json.loads(line)
        query = request["query"]
        mode = request.get("mode", "quick")
        filter_json = request.get("filter_json", "null")
        metadata_filter = json.loads(filter_json) if filter_json and filter_json != "null" else None
    except (json.JSONDecodeError, KeyError) as e:
        _write_json({"answer": f"请求解析失败：{e}", "citations": [], "trace": None})
        continue

    try:
        # 调用 orchestrator.answer()，一次性返回完整结果
        result = answer(query=query, mode=mode, metadata_filter=metadata_filter)
        _write_json({
            "answer": result["answer"],
            "citations": result["citations"],
            "trace": result["trace"],
        })

    except Exception as e:
        import traceback as tb
        tb.print_exc(file=sys.stderr)
        _write_json({
            "answer": f"处理请求时出错：{e}",
            "citations": [],
            "trace": None,
        })
