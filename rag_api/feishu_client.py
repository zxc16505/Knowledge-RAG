# -*- coding: utf-8 -*-
"""飞书开放平台 API 客户端（只依赖标准库）。

用途：把检索结果作为消息发回给提问的员工。
两件事：
  1. 换取 tenant_access_token（应用级凭证，带缓存，提前 300s 刷新）
  2. 给指定 open_id 发文本消息

环境变量：
  FEISHU_APP_ID / FEISHU_APP_SECRET   飞书自建应用凭证（必填）
  FEISHU_BASE_URL                     默认 https://open.feishu.cn（本地自测可指向 stub）

接口依据（飞书开放平台文档）：
  - 自建应用获取 tenant_access_token：
      POST /open-apis/auth/v3/tenant_access_token/internal
      body {"app_id","app_secret"} -> {"code":0,"tenant_access_token","expire"}
  - 发送消息：
      POST /open-apis/im/v1/messages?receive_id_type=open_id
      header Authorization: Bearer <tenant_access_token>
      body {"receive_id","msg_type":"text","content":"{\\"text\\":\\"...\\"}"}
"""
import json
import os
import time
import urllib.error
import urllib.request


class FeishuError(RuntimeError):
    pass


class FeishuClient:
    def __init__(self, app_id=None, app_secret=None, base=None, timeout=10):
        self.app_id = app_id or os.getenv("FEISHU_APP_ID", "")
        self.app_secret = app_secret or os.getenv("FEISHU_APP_SECRET", "")
        self.base = (base or os.getenv("FEISHU_BASE_URL", "https://open.feishu.cn")).rstrip("/")
        self.timeout = timeout
        self._token = None
        self._expire_at = 0.0

    # ---------- 低层 ----------
    def _post(self, path, payload, headers=None):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        hdr = {"Content-Type": "application/json; charset=utf-8"}
        if headers:
            hdr.update(headers)
        req = urllib.request.Request(self.base + path, data=body, headers=hdr, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            raise FeishuError(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
        except Exception as e:
            raise FeishuError(f"请求失败: {e}")

    # ---------- 凭证 ----------
    def token(self):
        """返回 tenant_access_token（带缓存，提前 300s 过期重取）。"""
        now = time.time()
        if self._token and now < self._expire_at:
            return self._token
        if not self.app_id or not self.app_secret:
            raise FeishuError("缺少 FEISHU_APP_ID / FEISHU_APP_SECRET")
        d = self._post(
            "/open-apis/auth/v3/tenant_access_token/internal",
            {"app_id": self.app_id, "app_secret": self.app_secret},
        )
        if d.get("code") != 0:
            raise FeishuError(f"取 tenant_access_token 失败: {d}")
        self._token = d["tenant_access_token"]
        self._expire_at = now + max(int(d.get("expire", 7200)) - 300, 60)
        return self._token

    # ---------- 发消息 ----------
    def send_text(self, open_id, text):
        """给某个 open_id 发文本消息，返回 message_id。"""
        tk = self.token()
        payload = {
            "receive_id": open_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        }
        d = self._post(
            "/open-apis/im/v1/messages?receive_id_type=open_id",
            payload,
            headers={"Authorization": f"Bearer {tk}"},
        )
        if d.get("code") != 0:
            raise FeishuError(f"发消息失败: {d}")
        return (d.get("data") or {}).get("message_id", "")
