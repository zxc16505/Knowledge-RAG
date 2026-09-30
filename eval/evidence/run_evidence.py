# -*- coding: utf-8 -*-
"""多组复跑证据采集：证明扩展集（14 篇 / 21 条）检索评测可复现且结论稳健。
- repro: 主配置(topk=10) 连跑 3 次，验证结果一致（确定性）
- topk_sweep: rerank topk ∈ {3,5,10,20}，验证结论对不同候选量不敏感
输出: evidence/evidence.json
"""
import importlib.util, json, os, sys, time

base = 'D:/项目/job/知识库项目材料/eval'
sys.path.insert(0, base)
import eval as m  # 复用 cosine / evaluate

emb = os.path.join(base, 'models_cache', 'models', 'BAAI--bge-base-zh-v1.5', 'snapshots', 'master')
rk = os.path.join(base, 'models_cache', 'models', 'BAAI--bge-reranker-v2-m3', 'snapshots', 'master')

docs, queries = m.load_golden(os.path.join(base, 'golden_set.json'))
print(f'[*] loaded {len(docs)} docs, {len(queries)} queries', flush=True)

from sentence_transformers import SentenceTransformer, CrossEncoder
print('[*] loading models ...', flush=True)
emodel = SentenceTransformer(emb)
rmodel = CrossEncoder(rk)
print('[*] models loaded', flush=True)


def stage1():
    doc_ids = list(docs.keys())
    de = emodel.encode([docs[i] for i in doc_ids], normalize_embeddings=True)
    qe = emodel.encode([q['query'] for q in queries], normalize_embeddings=True)
    res = []
    for qi in range(len(queries)):
        sc = [m.cosine(qe[qi], de[di]) for di in range(len(doc_ids))]
        ranked = sorted(range(len(doc_ids)), key=lambda i: sc[i], reverse=True)
        res.append([doc_ids[i] for i in ranked])
    return res


def stage2(s1, topk=10):
    final = []
    for qi, q in enumerate(queries):
        cand = s1[qi][:topk]
        pairs = [(q['query'], docs[c]) for c in cand]
        sc = rmodel.predict(pairs)
        ranked = sorted(range(len(cand)), key=lambda i: sc[i], reverse=True)
        final.append([cand[i] for i in ranked])
    return final


def ev(ranked):
    return m.evaluate(ranked, queries)


results = {
    'meta': {
        'n_docs': len(docs), 'n_queries': len(queries),
        'embed': 'bge-base-zh-v1.5', 'rerank': 'bge-reranker-v2-m3',
        'note': '确定性计算，无随机种子；多次复跑应完全一致',
    },
    'repro': [], 'topk_sweep': {},
}

t0 = time.time()
for i in range(3):
    s1 = stage1(); s2 = stage2(s1, 10)
    r1, r2 = ev(s1), ev(s2)
    results['repro'].append({'run': i + 1, 'stage1': r1, 'stage2': r2})
    print(f'[repro] run{i+1}: s1 MRR={r1["MRR"]} recall@3={r1["recall@3"]} | s2 MRR={r2["MRR"]} recall@3={r2["recall@3"]}', flush=True)

for tk in [3, 5, 10, 20]:
    s1 = stage1(); s2 = stage2(s1, tk)
    r1, r2 = ev(s1), ev(s2)
    results['topk_sweep'][str(tk)] = {'stage1': r1, 'stage2': r2}
    print(f'[topk={tk}] s1 MRR={r1["MRR"]} | s2 MRR={r2["MRR"]} recall@3={r2["recall@3"]}', flush=True)

results['elapsed_sec'] = round(time.time() - t0, 1)
os.makedirs(base + '/evidence', exist_ok=True)
json.dump(results, open(base + '/evidence/evidence.json', 'w', encoding='utf-8'),
          ensure_ascii=False, indent=2)
print('[DONE] evidence written to evidence/evidence.json', flush=True)
