# -*- coding: utf-8 -*-
"""
知识库检索评测 —— 零依赖演示版（DEMO，非真实 BGE 数字）
===================================================
用途：在你本地（无 GPU / 无模型）也能跑通整套「单向量 vs 双阶段」评测流程，
      验证脚本逻辑与指标计算。
注意：本脚本用字符级 bigram + TF-IDF 近似「向量」，用 IDF 加权词命中近似「Rerank 重排」。
      由于二者使用同源特征，差异可能不明显——这正说明近似无法替代真模型。
      **数字不代表真实 BGE 模型效果**。真实量化请在服务器用 eval.py
      （加载 bge-base-zh-v1.5 + bge-reranker）运行，结果可直接写入简历。

运行：python demo_eval.py
"""
import json
import math
from collections import Counter


def bigrams(text: str):
    text = "".join(ch for ch in text if ch.strip())
    return [text[i:i + 2] for i in range(len(text) - 1)]


def tfidf_vectors(docs: list):
    df = Counter()
    raw = []
    for d in docs:
        bg = bigrams(d)
        raw.append(bg)
        for t in set(bg):
            df[t] += 1
    n = len(docs)
    idf = {t: math.log((n + 1) / (c + 1)) + 1 for t, c in df.items()}
    vecs = []
    for bg in raw:
        tf = Counter(bg)
        vec = {}
        for t, c in tf.items():
            vec[t] = (1 + math.log(c)) * idf[t]
        vecs.append(vec)
    return vecs, idf


def cosine(a, b):
    keys = set(a) | set(b)
    dot = sum(a.get(k, 0) * b.get(k, 0) for k in keys)
    na = sum(v * v for v in a.values()) ** 0.5
    nb = sum(v * v for v in b.values()) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def stage1(docs, queries, doc_vecs, q_vecs, doc_ids):
    """单向量阶段：按余弦相似度对所有文档排序，返回文档 id 列表。"""
    res = []
    for qv in q_vecs:
        scored = sorted(range(len(docs)), key=lambda i: cosine(qv, doc_vecs[i]), reverse=True)
        res.append([doc_ids[i] for i in scored])
    return res


def stage2(docs_by_id, queries, s1, idf, doc_ids, topk=8):
    """双阶段：stage1 召回 top-k 候选，用 IDF 加权「查询-文档词命中率」近似重排。"""
    res = []
    for qi, q in enumerate(queries):
        qset = set(bigrams(q["query"]))
        cand = s1[qi][:topk]
        scored = []
        for d_id in cand:
            dbg = set(bigrams(docs_by_id[d_id]))
            # 稀有词命中权重高，模拟交叉编码器对区分性特征的敏感
            hit = sum(idf.get(t, 0) for t in qset if t in dbg)
            denom = sum(idf.get(t, 0) for t in qset) or 1
            scored.append((d_id, hit / denom))
        scored.sort(key=lambda x: x[1], reverse=True)
        res.append([d_id for d_id, _ in scored])
    return res


def evaluate(ranked, queries, ks=(1, 3, 5)):
    m = {f"recall@{k}": 0.0 for k in ks}
    mrr = 0.0
    for qi, q in enumerate(queries):
        rel = set(q["relevant"])
        for k in ks:
            if any(r in rel for r in ranked[qi][:k]):
                m[f"recall@{k}"] += 1
        for rank, did in enumerate(ranked[qi], 1):
            if did in rel:
                mrr += 1.0 / rank
                break
    n = len(queries)
    return {"MRR": round(mrr / n, 4), **{k: round(m[k] / n, 4) for k in m}}


def main():
    with open("golden_set.json", encoding="utf-8") as f:
        data = json.load(f)
    doc_ids = [d["id"] for d in data["documents"]]
    docs_by_id = {d["id"]: d["text"] for d in data["documents"]}
    queries = data["queries"]
    corpus = [docs_by_id[i] for i in doc_ids]

    doc_vecs, idf = tfidf_vectors(corpus)
    q_vecs = tfidf_vectors([q["query"] for q in queries])[0]
    s1 = stage1(corpus, queries, doc_vecs, q_vecs, doc_ids)
    s2 = stage2(docs_by_id, queries, s1, idf, doc_ids)

    r1, r2 = evaluate(s1, queries), evaluate(s2, queries)
    print("=" * 60)
    print("【DEMO 演示】字符 bigram 近似，数字非真实 BGE 效果")
    print("=" * 60)
    print(f"{'指标':<12}{'向量单阶段':<14}{'向量+Rerank':<14}{'提升':<10}")
    for key in ["recall@1", "recall@3", "recall@5", "MRR"]:
        v1, v2 = r1[key], r2[key]
        d = f"+{round((v2 - v1) * 100, 1)}pt"
        print(f"{key:<12}{v1:<14}{v2:<14}{d:<10}")
    print("\n说明：本 DEMO 用同源字符特征近似「向量」与「Rerank」，二者天然接近，故差异可能")
    print("      不明显——这正说明近似无法替代真模型。真实双阶段增益请用 eval.py 在服务器")
    print("      加载 bge-base-zh-v1.5 + bge-reranker 实测，结果可直接写入简历量化证据。")


if __name__ == "__main__":
    main()
