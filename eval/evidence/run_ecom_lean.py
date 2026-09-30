# -*- coding: utf-8 -*-
"""
模拟电商场景实跑（轻量版）：串行加载 + 只跑必要组数，避免内存 swap 卡死
- 向量单阶段：主配置连跑 3 次（验证可复现，仅重排预计算分数，几乎瞬时）
- 重排对比：只跑 1 次主配置（rerank_topk=10），不再做 4 组 topk 扫描
- reranker 用 fp32（CPU 上比模拟 float16 快），且 embedding 释放后再加载
"""
import sys, os, gc, json, time
os.environ.setdefault("OMP_NUM_THREADS", "4")
sys.path.insert(0, r"D:/项目/job/知识库项目材料/eval")
import numpy as np
import eval as ev
from sentence_transformers import SentenceTransformer, CrossEncoder

BASE = r"D:/项目/job/知识库项目材料/eval"
GOLDEN = os.path.join(BASE, "evidence", "golden_set_ecom.json")
MODELS_DIR = os.path.join(BASE, "models_cache")
OUT = os.path.join(BASE, "evidence", "evidence_ecom.json")

docs, queries = ev.load_golden(GOLDEN)
doc_ids = list(docs.keys())
print(f"[*] 文档 {len(docs)} 篇，查询 {len(queries)} 条", flush=True)

# ---------- 阶段一：向量单阶段 ----------
print("[*] 加载 embedding 模型（缓存优先）...", flush=True)
emb_path, rk_path = ev.download_models(MODELS_DIR)
t0 = time.time()
emb_model = SentenceTransformer(emb_path)
doc_emb = emb_model.encode([docs[i] for i in doc_ids], normalize_embeddings=True)
q_emb = emb_model.encode([q["query"] for q in queries], normalize_embeddings=True)
emb_model = None
gc.collect()
print(f"[*] embedding 完成（{time.time()-t0:.1f}s），模型已释放", flush=True)


def vec_rank(qi):
    scores = [ev.cosine(q_emb[qi], doc_emb[di]) for di in range(len(doc_ids))]
    return [doc_ids[i] for i in sorted(range(len(doc_ids)), key=lambda i: scores[i], reverse=True)]


# 向量单阶段先落盘，避免重排卡死时白跑
repro = []
print("\n===== 向量单阶段复现（连跑3次）=====", flush=True)
for i in range(3):
    s1 = [vec_rank(qi) for qi in range(len(queries))]
    vec = ev.evaluate(s1, queries)
    repro.append({"run": i + 1, "vec": vec})
    print(f"[复现{i+1}] recall@1={vec['recall@1']} recall@3={vec['recall@3']} MRR={vec['MRR']}", flush=True)

out = {
    "golden": GOLDEN,
    "scene": "模拟中型电商企业知识库（四品牌：百斯盾/猫人/红豆/百家好；含商品成分、尺码、颜色编码、销售报表、库存、各部门SOP、平台规则、合格证规范）",
    "n_docs": len(docs), "n_queries": len(queries),
    "repro_main_topk10_vec_only": repro,
    "vec_rerank": None,
    "note": "向量单阶段已完成；rerank 对比待加载后追加",
}
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(f"[*] 向量结果已写出 {OUT}", flush=True)

# ---------- 阶段二：重排（单独加载 reranker，fp32） ----------
print("[*] 加载 reranker（fp32）...", flush=True)
t1 = time.time()
try:
    reranker = CrossEncoder(rk_path)
except Exception as e:
    print(f"[!] reranker 加载失败：{e}", flush=True)
    reranker = None

docs_text = [docs[i] for i in doc_ids]


def rerank(vec_res, rerank_topk=10):
    if reranker is None:
        return None
    final = []
    for qi, q in enumerate(queries):
        cand = vec_res[qi][:rerank_topk]
        pairs = [(q["query"], docs_text[doc_ids.index(c)]) for c in cand]
        scores = reranker.predict(pairs)
        ranked = sorted(range(len(cand)), key=lambda i: scores[i], reverse=True)
        final.append([cand[i] for i in ranked])
    return final


print("[*] 重排主配置（topk=10，1次）...", flush=True)
s1 = [vec_rank(qi) for qi in range(len(queries))]
vec = ev.evaluate(s1, queries)
vrr = rerank(s1, 10)
r2 = ev.evaluate(vrr, queries) if vrr is not None else None
print(f"[重排] 向量 MRR={vec['MRR']} recall@3={vec['recall@3']}"
      + (f" | 向量+rerank MRR={r2['MRR']} recall@3={r2['recall@3']}" if r2 else " | (未运行)"), flush=True)

out["vec_rerank"] = {
    "topk10_once": {"vec": vec, "vec_rerank": r2},
    "elapsed_rerank_s": round(time.time() - t1, 1),
}
out["note"] = "向量单阶段 + rerank 主配置对比均完成"
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(f"[*] 全部完成，已写出 {OUT}", flush=True)
