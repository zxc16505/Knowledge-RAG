# -*- coding: utf-8 -*-
"""
知识库检索架构离线评测脚本（真实 BGE + Rerank 版本 · 本机 Windows 版）
============================================================
用途：对比「向量单阶段召回」与「向量召回 + Rerank 重排双阶段」的检索效果。
运行环境：本机 Windows（无 GPU 也可，CPU 跑 9 篇文档 + 15 条查询约数分钟）。
          模型通过 ModelScope 国内源（modelscope.cn，经本机代理可达）下载到本地
          models_cache 后离线加载。

依赖：
    pip install torch sentence-transformers modelscope numpy

用法：
    # 自动从 ModelScope 下载模型并评测
    python eval.py --golden golden_set.json

    # 已下载过，跳过下载直接跑
    python eval.py --golden golden_set.json --no-download

输出：recall@1 / recall@3 / recall@5 / MRR 对比表，可直接用于简历量化。
"""
import argparse
import json
import os
import sys
from typing import List, Dict


def cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def load_golden(path: str):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    docs = {d["id"]: d["text"] for d in data["documents"]}
    queries = data["queries"]
    return docs, queries


def download_models(models_dir: str):
    """通过 ModelScope 国内源（modelscope.cn）把 bge 向量模型与 reranker 下载到本地。

    注意：本机出网必须走代理（HTTP_PROXY），而代理无法隧道到 huggingface.co；
    modelscope.cn 经代理可达，因此用 modelscope 库下载。不要清除代理。
    """
    from modelscope.hub.snapshot_download import snapshot_download

    emb = snapshot_download("BAAI/bge-base-zh-v1.5",
                            cache_dir=models_dir)
    rk = snapshot_download("BAAI/bge-reranker-v2-m3",
                           cache_dir=models_dir)
    return emb, rk


def stage1_only(docs, queries, embed_model):
    """单向量阶段：对每个 query 用余弦相似度对所有文档排序。"""
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(embed_model)
    doc_ids = list(docs.keys())
    doc_emb = model.encode([docs[i] for i in doc_ids], normalize_embeddings=True)
    q_emb = model.encode([q["query"] for q in queries], normalize_embeddings=True)

    results = []
    for qi in range(len(queries)):
        scores = [cosine(q_emb[qi], doc_emb[di]) for di in range(len(doc_ids))]
        ranked = sorted(range(len(doc_ids)), key=lambda i: scores[i], reverse=True)
        results.append([doc_ids[i] for i in ranked])
    return results


def stage2_rerank(docs, queries, emb_results, rerank_model, rerank_topk=10):
    """双阶段：stage1 召回 top-k 候选，再用交叉编码器重排。"""
    from sentence_transformers import CrossEncoder

    reranker = CrossEncoder(rerank_model)
    final = []
    for qi, q in enumerate(queries):
        cand = emb_results[qi][:rerank_topk]
        pairs = [(q["query"], docs[c]) for c in cand]
        scores = reranker.predict(pairs)
        ranked = sorted(range(len(cand)), key=lambda i: scores[i], reverse=True)
        final.append([cand[i] for i in ranked])
    return final


def evaluate(ranked_lists: List[List[str]], queries, ks=(1, 3, 5)) -> Dict:
    metrics = {f"recall@{k}": 0.0 for k in ks}
    mrr = 0.0
    for qi, q in enumerate(queries):
        rel = set(q["relevant"])
        ranked = ranked_lists[qi]
        for k in ks:
            if any(r in rel for r in ranked[:k]):
                metrics[f"recall@{k}"] += 1
        for rank, doc_id in enumerate(ranked, start=1):
            if doc_id in rel:
                mrr += 1.0 / rank
                break
    n = len(queries)
    for k in metrics:
        metrics[k] = round(metrics[k] / n, 4)
    return {"n_queries": n, "MRR": round(mrr / n, 4), **metrics}


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", default=os.path.join(here, "golden_set.json"))
    ap.add_argument("--models-dir", default=os.path.join(here, "models_cache"))
    ap.add_argument("--no-download", action="store_true")
    ap.add_argument("--embed-model", default=None)
    ap.add_argument("--rerank-model", default=None)
    ap.add_argument("--rerank-topk", type=int, default=10)
    args = ap.parse_args()

    if args.embed_model and args.rerank_model and args.no_download:
        emb, rk = args.embed_model, args.rerank_model
    else:
        print("[*] 通过 ModelScope 下载 BGE 模型（国内源，首次约 1-2GB）...")
        emb, rk = download_models(args.models_dir)
        print(f"[*] 向量模型路径: {emb}")
        print(f"[*] 重排模型路径: {rk}")

    docs, queries = load_golden(args.golden)
    print(f"[*] 加载 {len(docs)} 篇文档，{len(queries)} 条查询")

    print("[*] 阶段一：向量单阶段召回 ...")
    s1 = stage1_only(docs, queries, emb)
    print("[*] 阶段二：向量召回 + Rerank 重排 ...")
    s2 = stage2_rerank(docs, queries, s1, rk, args.rerank_topk)

    r1 = evaluate(s1, queries)
    r2 = evaluate(s2, queries)

    print("\n===== 检索效果对比（真实 BGE + Rerank）=====")
    print(f"{'指标':<12}{'向量单阶段':<14}{'向量+Rerank':<14}{'提升':<10}")
    for key in ["recall@1", "recall@3", "recall@5", "MRR"]:
        v1, v2 = r1[key], r2[key]
        delta = f"+{round((v2 - v1) * 100, 1)}pt" if v2 >= v1 else f"{round((v2 - v1) * 100, 1)}pt"
        print(f"{key:<12}{v1:<14}{v2:<14}{delta:<10}")
    print("\n说明：pt 为百分点。该结果可直接替换简历中『[待补充数据]』作为量化证据。")


if __name__ == "__main__":
    main()
