# -*- coding: utf-8 -*-
"""
/webhook/gitea HMAC 验签回归（对应 Gitea 出站 webhook 的 X-Gitea-Signature 机制）。

用法（先起服务，再跑本脚本；与服务同一组 WEBHOOK_SECRET）：
  1) 起 rag_api（降级模式即可），env 配 WEBHOOK_SECRET=demo_hook_secret
  2) python test_webhook_sig.py

覆盖 5 个关键行为：
  W1 合法 HMAC 签名 -> 放行并触发索引
  W2 伪造签名 -> 403
  W3 缺少签名头 -> 403
  W4 旧版 query 明文 secret（口令正确、无 HMAC 头）-> 403（旁路已封死）
  W5 合法签名但 body 被改一个字节（签名与 body 不匹配）-> 403
"""
import hashlib
import hmac
import json
import os
import sys
import urllib.error
import urllib.request

RESULTS = []  # [(用例名, 是否通过)]

SECRET = os.getenv("WEBHOOK_SECRET", "demo_hook_secret")
BASE = os.getenv("RAG_BASE_URL", "http://127.0.0.1:8000")

PUSH_BODY = json.dumps(
    {"ref": "refs/heads/main", "commits": [{"id": "deadbeef", "message": "note update"}]},
    ensure_ascii=False,
)


def sign(body: str) -> str:
    """与 Gitea 一致：hex(hmac_sha256(secret, raw_body))"""
    return hmac.new(SECRET.encode(), body.encode("utf-8"), hashlib.sha256).hexdigest()


def post(path: str, headers: dict, body: str):
    req = urllib.request.Request(BASE + path, data=body.encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def show(label, status, resp, expect="ok"):
    good = status < 400 if expect == "ok" else status in (401, 403)
    mark = "PASS" if good else "FAIL"
    RESULTS.append((label, good))
    print(f"[{mark}] {label} -> HTTP {status} | {resp[:140]}".replace("\n", " "))


def hook(sig: str, body: str):
    return post("/webhook/gitea", {"X-Gitea-Signature": sig, "Content-Type": "application/json"}, body)


def main():
    print("==== /webhook/gitea HMAC 验签回归 ====")

    st, rp = hook(sign(PUSH_BODY), PUSH_BODY)
    show("W1 合法HMAC签名", st, rp)

    st, rp = hook("0" * 64, PUSH_BODY)
    show("W2 伪造签名", st, rp, expect="reject")

    st, rp = post("/webhook/gitea", {"Content-Type": "application/json"}, PUSH_BODY)
    show("W3 缺少签名头", st, rp, expect="reject")

    st, rp = post(f"/webhook/gitea?secret={SECRET}", {}, "{}")
    show("W4 旧版query明文secret(旁路已封)", st, rp, expect="reject")

    tampered = PUSH_BODY[:-1] + ("}" if PUSH_BODY[-1] != "}" else " ")
    st, rp = hook(sign(PUSH_BODY), tampered)
    show("W5 合法签名但body被篡改", st, rp, expect="reject")

    passed = sum(1 for _, ok in RESULTS if ok)
    total = len(RESULTS)
    print(f"\n{passed}/{total} case(s) passed")
    if passed != total:
        for label, ok in RESULTS:
            if not ok:
                print(f"  FAILED: {label}")
        sys.exit(1)


if __name__ == "__main__":
    main()
