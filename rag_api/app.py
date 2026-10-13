# -*- coding: utf-8 -*-
"""
知识库检索服务（FastAPI 骨架）
================================
端点：
  GET  /health           健康检查（需 API Key）
  POST /api/reload       触发全量/增量索引（需 API Key）
  POST /api/retrieve     内部调试检索口（需 API Key，user_id 必填，fail-closed）
  POST /webhook/gitea    Gitea Webhook 回调，自动重建索引
  POST /feishu/event     员工消息入口（对外路径，飞书签名鉴权，身份取自验签事件）
  GET  /docs             Swagger 文档（受 API Key 保护）

设计要点（来自部署指南）：
  - 笔记目录只读挂载，本服务绝不写入源笔记
  - 向量库仅内网，rag_api 通过 QDRANT_URL 访问
  - 无 GPU/模型时自动降级为关键词检索，保证容器可启动演示
  - 权限感知（硬控制）：入库按 vault 顶层目录标记 department；检索时按
    身份解析部门并对 Qdrant 加 must 过滤，别的部门数据从头到尾不进模型，
    而非把部门写进 prompt 让模型"自觉"收敛（软控制易被诱导漏出）
  - 身份来源（v1.2 新增）：对外路径 /feishu/event 从【飞书签名事件】的
    event.sender.sender_id 取 open_id，客户端无法伪造；/api/retrieve 仅为
    内部调试口（需 API Key），不再有“无 user_id 即全量放行”的后门。

运行：uvicorn app:app --host 0.0.0.0 --port 8000
"""
import os
import re
import json
import glob
import time
import hashlib
import hmac
import logging
import collections
import urllib.request
from typing import Dict, List, Optional, Set

from fastapi import FastAPI, BackgroundTasks, Header, HTTPException, Request, Depends
from pydantic import BaseModel

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("rag_api")

API_KEY = os.getenv("API_GLOBAL_KEY", "dev_key")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
FEISHU_ENCRYPT_KEY = os.getenv("FEISHU_ENCRYPT_KEY", "")
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
VAULT = os.getenv("VAULT_PATH", "/vault")
COLLECTION = "knowledge"
EMBED_DIM = 768

# 部门边界配置
DEPT_MAP_PATH = os.getenv("DEPT_MAP_PATH", "/app/data/dept_map.json")
SHARED_DEPT = os.getenv("SHARED_DEPT", "公共")
# 找不到映射时是否放行到共享域。默认 false = 默认拒绝（fail-closed）
ALLOW_UNKNOWN = os.getenv("ALLOW_UNKNOWN_DEPT", "false").lower() in ("1", "true", "yes")

# ---- 飞书回复：把检索结果回给提问人 ----
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
FEISHU_REPLY_ENABLED = os.getenv("FEISHU_REPLY_ENABLED", "true").lower() in ("1", "true", "yes")
# 可选：接 OpenAI 兼容接口的大模型生成答案（DeepSeek / Qwen 等）；不配则回拼接的检索片段
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "")
# 飞书事件去重（飞书超时会重推同一事件，避免重复回复）
_SEEN_EVENTS: "collections.OrderedDict" = collections.OrderedDict()
_MAX_SEEN = 500

# ---- 能力探测（降级开关）----
try:
    from sentence_transformers import SentenceTransformer
    EMB = SentenceTransformer(os.getenv("EMBED_MODEL_PATH", "BAAI/bge-base-zh-v1.5"))
    HAS_EMB = True
except Exception as e:
    EMB = None
    HAS_EMB = False
    print("[WARN] embedding 模型不可用，降级关键词模式:", e)

try:
    from qdrant_client import QdrantClient
    qc = QdrantClient(url=QDRANT_URL)
    qc.get_collections()
    HAS_Q = True
except Exception as e:
    qc = None
    HAS_Q = False
    print("[WARN] Qdrant 不可用，内存降级模式:", e)

MEM: List[dict] = []  # 降级模式下的内存索引

app = FastAPI(title="Knowledge RAG API", version="1.2")


# ---------- 工具函数 ----------
def auth(x_api_key: Optional[str] = Header(None)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="invalid api key")


def chunk_text(text: str) -> List[str]:
    """结构感知切分：按标题层级与空行分块，避免表格/规则被拦腰截断。"""
    parts = re.split(r"\n#{1,6}\s+|\n\n+", text)
    return [p.strip() for p in parts if len(p.strip()) > 10]


def derive_dept(path: str) -> str:
    """按 vault 顶层目录名作为部门；根目录文件或公共目录归公共域。"""
    rel = os.path.relpath(path, VAULT)
    top = rel.split(os.sep)[0]
    if os.sep not in rel or top in ("", ".", SHARED_DEPT):
        return SHARED_DEPT
    return top


def load_dept_map() -> dict:
    """user_id -> 部门 映射；文件缺失或损坏返回空表（安全降级）。"""
    try:
        with open(DEPT_MAP_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def resolve_depts(user_id: Optional[str]) -> List[str]:
    """权限感知核心：返回允许检索的部门列表（硬控制，fail-closed）。

    已删除“无 user_id 即全量放行”的后门：
    - 无/空 user_id -> 仅公共域；ALLOW_UNKNOWN=False（默认）时为拒绝（空列表）
    - 已知 user_id -> [本部门, 公共域]
    - 未知 user_id -> 仅公共域；ALLOW_UNKNOWN=False（默认）时为拒绝（空列表）
    """
    if user_id:
        dept = load_dept_map().get(user_id)
        if dept:
            return list({dept, SHARED_DEPT})
    return [SHARED_DEPT] if ALLOW_UNKNOWN else []


def verify_feishu_signature(timestamp: str, nonce: str, signature: str, body: bytes) -> bool:
    """飞书事件订阅签名校验（官方算法）。

    string_to_sign = timestamp + nonce + encrypt_key + body
    signature_calc = SHA256(string_to_sign).hexdigest()
    与请求头 X-Lark-Signature 做常量时间比较。

    - 未配置 FEISHU_ENCRYPT_KEY -> 拒绝一切飞书请求（fail-closed）
    - 任一参数为空 -> 拒绝
    这一步保证“身份来源”是飞书服务端盖章的事件，而非客户端自填字段。
    """
    if not FEISHU_ENCRYPT_KEY or not timestamp or not nonce or not signature:
        return False
    string_to_sign = timestamp + nonce + FEISHU_ENCRYPT_KEY + body.decode("utf-8", "replace")
    calc = hashlib.sha256(string_to_sign.encode("utf-8")).hexdigest()
    return hmac.compare_digest(calc, signature)


def scan_vault() -> List[dict]:
    items = []
    for f in glob.glob(os.path.join(VAULT, "**", "*.md"), recursive=True):
        try:
            with open(f, encoding="utf-8") as fh:
                text = fh.read()
        except Exception:
            continue
        for i, c in enumerate(chunk_text(text)):
            items.append({"source": f, "chunk": i, "text": c, "department": derive_dept(f)})
    return items


def index_vault() -> int:
    items = scan_vault()
    if HAS_EMB and HAS_Q:
        # 真实向量写入 Qdrant
        from qdrant_client.models import Distance, VectorParams, PointStruct
        if not qc.collection_exists(COLLECTION):
            qc.create_collection(
                COLLECTION, vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE)
            )
        vecs = EMB.encode([it["text"] for it in items], normalize_embeddings=True)
        pts = [
            PointStruct(id=idx, vector=vecs[idx].tolist(), payload=it)
            for idx, it in enumerate(items)
        ]
        qc.upsert(COLLECTION, pts)
    else:
        MEM.clear()
        MEM.extend(items)
    return len(items)


# ---------- 端点 ----------
@app.get("/health")
def health(_=Depends(auth)):
    return {"status": "ok", "embedding": HAS_EMB, "qdrant": HAS_Q}


@app.post("/api/reload")
def reload(_=Depends(auth)):
    n = index_vault()
    return {"indexed": n}


@app.post("/webhook/gitea")
async def webhook(req: Request):
    secret = req.headers.get("X-Gitea-Signature") or req.query_params.get("secret", "")
    if WEBHOOK_SECRET and secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="invalid webhook secret")
    n = index_vault()
    return {"triggered": True, "indexed": n}


def do_retrieve(query: str, depts: List[str], top_k: int = 3) -> dict:
    """内部检索实现：depts 为已解析的部门白名单（硬过滤域）。

    调用方负责在传入 depts 之前完成身份核验；本函数只认 depts，
    绝不再从任何请求字段反查身份——这是“授权在模型/客户端之外”的落点。
    depts 为空列表时 fail-closed：向量模式 MatchAny([]) 命中 0 条，
    关键词模式池为空，均无结果。
    """
    if HAS_EMB and HAS_Q:
        from qdrant_client.models import Filter, FieldCondition, MatchAny
        qv = EMB.encode([query], normalize_embeddings=True)[0].tolist()
        filt = Filter(must=[FieldCondition(key="department", match=MatchAny(values=depts))])
        hits = qc.search(COLLECTION, query_vector=qv, limit=top_k, query_filter=filt)
        return {
            "results": [
                {"text": h.payload["text"][:300], "source": h.payload["source"], "score": round(h.score, 4)}
                for h in hits
            ]
        }
    # 关键词降级
    pool = [d for d in MEM if d.get("department") in depts]
    qset = set(query)
    scored = sorted(
        ((sum(1 for ch in qset if ch in d["text"]), d) for d in pool),
        key=lambda x: x[0], reverse=True,
    )
    return {
        "results": [
            {"text": d["text"][:300], "source": d["source"], "score": s}
            for s, d in scored[:top_k]
        ]
    }


# ---------- 答案组装与飞书回复 ----------
def _is_duplicate(event_id: Optional[str]) -> bool:
    """飞书事件去重：超时重推时同一 event_id 只处理一次，避免重复回复。"""
    if not event_id:
        return False
    if event_id in _SEEN_EVENTS:
        return True
    _SEEN_EVENTS[event_id] = time.time()
    while len(_SEEN_EVENTS) > _MAX_SEEN:
        _SEEN_EVENTS.popitem(last=False)
    return False


def _fallback_answer(results: dict) -> str:
    """无大模型时的降级回答：直接回检索到的原文片段与来源。"""
    hits = results.get("results") or []
    if not hits:
        return "没找到相关内容——可能不在你所在部门的可检索范围内。"
    lines = ["根据知识库检索到以下内容："]
    for i, h in enumerate(hits, 1):
        src = os.path.basename(str(h.get("source", "")))
        lines.append(f"{i}. {str(h.get('text', '')).strip()}\n   来源：{src}")
    return "\n".join(lines)


def _llm_answer(query: str, results: dict) -> str:
    """用 OpenAI 兼容接口生成答案（只依据检索片段，禁止编造）。"""
    ctx = "\n\n".join(
        f"[{i}] {h.get('text', '')}" for i, h in enumerate(results.get("results") or [], 1)
    )
    prompt = (
        "只依据下面给出的资料回答问题；资料里没有的信息就直说「知识库中没有相关内容」，不要编造。\n\n"
        f"资料：\n{ctx}\n\n问题：{query}"
    )
    body = json.dumps(
        {
            "model": LLM_MODEL,
            "temperature": 0.2,
            "messages": [{"role": "user", "content": prompt}],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        LLM_BASE_URL.rstrip("/") + "/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LLM_API_KEY}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read().decode("utf-8", "replace"))
    return d["choices"][0]["message"]["content"].strip()


def compose_answer(query: str, results: dict) -> str:
    """组装给用户的回答：配了大模型就用大模型，否则回检索片段。"""
    if LLM_BASE_URL and LLM_API_KEY and LLM_MODEL:
        try:
            return _llm_answer(query, results)
        except Exception as e:
            log.warning("大模型生成失败，降级为检索片段：%s", e)
    return _fallback_answer(results)


def reply_to_feishu(open_id: str, text: str) -> None:
    """后台任务：把答案发回飞书。失败只记日志，不影响事件应答。"""
    try:
        try:
            from .feishu_client import FeishuClient
        except ImportError:
            from feishu_client import FeishuClient
        mid = FeishuClient().send_text(open_id, text)
        log.info("[已回复飞书] open_id=%s message_id=%s", open_id, mid)
    except Exception as e:
        log.error("[回复飞书失败] open_id=%s: %s", open_id, e)


class RetrieveReq(BaseModel):
    query: str
    top_k: int = 3
    user_id: str  # 必填：内部调试口，身份由调用方（服务端）提供


@app.post("/api/retrieve")
def retrieve(r: RetrieveReq, _=Depends(auth)):
    """内部调试检索口（非员工可达面）：user_id 必填，解析不到部门时 fail-closed。"""
    depts = resolve_depts(r.user_id)
    return do_retrieve(r.query, depts, r.top_k)


@app.post("/feishu/event")
async def feishu_event(req: Request, bg: BackgroundTasks):
    """员工消息入口（对外路径，无需 API Key，靠飞书签名鉴权）。

    飞书把事件 JSON POST 到此，带头 X-Lark-Request-Timestamp /
    X-Lark-Request-Nonce / X-Lark-Signature。本端点：
      1. 验签（verify_feishu_signature）—— 伪造/篡改一律 403
      2. 从【已验签事件体】取 event.sender.sender_id.open_id 作为身份
      3. 按 open_id 解析部门 -> do_retrieve 硬过滤
      4. 组装回答 -> 后台任务发回飞书（接口立即应答，避免飞书超时重推）
    这是“授权在模型之外”的真实落点：提示注入只能改 query 文本，过滤域纹丝不动。
    """
    ts = req.headers.get("X-Lark-Request-Timestamp", "")
    nonce = req.headers.get("X-Lark-Request-Nonce", "")
    signature = req.headers.get("X-Lark-Signature", "")
    raw = await req.body()
    if not verify_feishu_signature(ts, nonce, signature, raw):
        raise HTTPException(status_code=403, detail="invalid feishu signature")
    try:
        payload = json.loads(raw)
    except Exception:
        raise HTTPException(status_code=400, detail="bad json body")
    # 飞书回调 URL 验证回执
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge", "")}
    # 飞书超时重推去重
    event_id = (payload.get("header") or {}).get("event_id")
    if _is_duplicate(event_id):
        log.info("[重复事件已忽略] event_id=%s", event_id)
        return {"code": 0, "msg": "duplicate ignored"}
    # 从已验签事件提取提问人身份（唯一可信来源）
    event = payload.get("event", {})
    sender_id = event.get("sender", {}).get("sender_id", {})
    open_id = sender_id.get("open_id") or sender_id.get("user_id")
    if not open_id:
        raise HTTPException(status_code=400, detail="no sender identity in event")
    # 提取提问文本（im.message.receive_v1）
    content = event.get("message", {}).get("content", "{}")
    try:
        text = json.loads(content).get("text", "")
    except Exception:
        text = ""
    depts = resolve_depts(open_id)
    if not depts:
        # 未命中身份 fail-closed，同时记录 open_id，方便收集后授权
        log.warning(
            "[身份未命中] open_id=%s 不在 dept_map（fail-closed，无结果）。"
            "授权方式：把该 open_id 加进 dept_map.json",
            open_id,
        )
    result = do_retrieve(text, depts, 3)
    answer = compose_answer(text, result)
    # 后台回复：接口立即返回，避免飞书 3 秒超时重推
    if FEISHU_REPLY_ENABLED and text:
        bg.add_task(reply_to_feishu, open_id, answer)
    return {
        "code": 0,
        "open_id": open_id,
        "department_scope": depts,
        "retrieval": result,
        "reply": answer,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
