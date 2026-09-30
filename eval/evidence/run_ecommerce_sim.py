# -*- coding: utf-8 -*-
"""
模拟电商场景实跑脚本（串行加载，降低峰值内存）
=========================================================
针对「模拟中型电商知识库」评测集跑多组评测：
  - 主配置（rerank_topk=10）连跑 3 次，验证结果可复现（确定性计算）
  - rerank_topk 扫描 {3,5,10,20}，验证「重排是否带来增益」对候选量不敏感
关键改动（相比初版）：
  - 先加载 embedding 模型、跑完「向量单阶段」并释放 embedding 模型，
    再单独加载 reranker，避免两个大模型同时驻留导致页面文件不足（os error 1455）
  - reranker 用 float16 进一步降低显存/内存占用
输出：evidence_ecom.json（含每次 console 数字，可复现铁证）
"""
import sys, os, gc, json
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
print(f"[*] 文档 {len(docs)} 篇，查询 {len(queries)} 条")

# ---------- 阶段一：向量单阶段（先跑，跑完即释放 embedding 模型） ----------
print("[*] 加载 embedding 模型（缓存优先）...")
emb_path, rk_path = ev.download_models(MODELS_DIR)
emb_model = SentenceTransformer(emb_path)
print("[*] 编码文档与查询 ...")
doc_emb = emb_model.encode([docs[i] for i in doc_ids], normalize_embeddings=True)
q_emb = emb_model.encode([q["query"] for q in queries], normalize_embeddings=True)
np.savez(os.path.join(BASE, "evidence", "_ecom_emb.npz"), doc_emb=doc_emb, q_emb=q_emb)
emb_model = None
gc.collect()
print("[*] embedding 模型已释放")


def vec_rank(qi):
    scores = [ev.cosine(q_emb[qi], doc_emb[di]) for di in range(len(doc_ids))]
    return [doc_ids[i] for i in sorted(range(len(doc_ids)), key=lambda i: scores[i], reverse=True)]


def evaluate_vec():
    return [vec_rank(qi) for qi in range(len(queries))]


# ---------- 阶段二：重排（单独加载 reranker） ----------
print("[*] 加载 reranker（float16）...")
rerank_note = ""
try:
    reranker = CrossEncoder(rk_path, model_kwargs={"torch_dtype": "float16"})
except Exception as e:
    print(f"[!] reranker 加载失败：{e}")
    reranker = None
    rerank_note = f"reranker 加载失败（{type(e).__name__}），仅输出向量单阶段结果"

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


# ---------- 主配置复现 3 次 ----------
repro = []
print("\n===== 主配置复现（rerank_topk=10，连跑3次）=====")
for i in range(3):
    s1 = evaluate_vec()
    vec = ev.evaluate(s1, queries)
    vrr = rerank(s1, 10)
    r2 = ev.evaluate(vrr, queries) if vrr is not None else None
    repro.append({"run": i + 1, "vec": vec, "vec_rerank": r2})
    print(f"[复现{i+1}] 向量: recall@1={vec['recall@1']} recall@3={vec['recall@3']} MRR={vec['MRR']}"
          + (f" | 向量+rerank: recall@1={r2['recall@1']} recall@3={r2['recall@3']} MRR={r2['MRR']}"
             if r2 is not None else " | 向量+rerank: (未运行)"))

# ---------- rerank_topk 扫描 ----------
sweep = {}
print("\n===== rerank_topk 扫描（验证重排增益对候选量不敏感）=====")
for k in [3, 5, 10, 20]:
    s1 = evaluate_vec()
    vec = ev.evaluate(s1, queries)
    vrr = rerank(s1, k)
    r2 = ev.evaluate(vrr, queries) if vrr is not None else None
    sweep[str(k)] = {"vec": vec, "vec_rerank": r2}
    print(f"[topk={k}] 向量 MRR={vec['MRR']} recall@3={vec['recall@3']}"
          + (f" | 向量+rerank MRR={r2['MRR']} recall@3={r2['recall@3']}"
             if r2 is not None else " | 向量+rerank: (未运行)"))

out = {
    "golden": GOLDEN,
    "scene": "模拟中型电商企业知识库（四品牌：百斯盾/猫人/红豆/百家好；含商品成分、尺码、颜色编码、销售报表、库存、各部门SOP、平台规则、合格证规范）",
    "n_docs": len(docs), "n_queries": len(queries),
    "repro_main_topk10": repro,
    "rerank_topk_sweep": sweep,
    "note": rerank_note or "reranker 正常加载并参与评测",
}
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(f"\n[*] 已写出 {OUT}")
