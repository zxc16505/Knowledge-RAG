# -*- coding: utf-8 -*-
"""飞书长连接桥（WebSocket）：无需公网 IP / 域名，本地即可收飞书消息。

原理：
  飞书「长连接」模式由 SDK 主动连飞书服务器并完成鉴权，事件以明文推给本进程；
  本桥把事件转成标准事件体，POST 给本地 rag_api 的 /feishu/event（按
  FEISHU_ENCRYPT_KEY 自己算签名），从而复用完整的「验签 -> 部门硬过滤 -> 回复」链路。

  注意：长连接模式下 HTTP 签名层不承担安全职责（SDK 已在连接时鉴权），
  这里保留签名只是为了不绕过既有代码路径、让安全回归用例依然覆盖它。

依赖：pip install "lark-oapi" -U
用法：
  1) 先起 rag_api（默认 127.0.0.1:8000）
  2) 配好环境变量后：python ws_bridge.py
环境变量：
  FEISHU_APP_ID / FEISHU_APP_SECRET   飞书自建应用凭证（必填）
  FEISHU_ENCRYPT_KEY                  与 rag_api 一致（用于本地回环签名的计算）
  RAG_BASE_URL                        默认 http://127.0.0.1:8000

官方文档：open.feishu.cn -> 服务端 SDK -> Python SDK -> 处理事件（长连接）
"""
import hashlib
import json
import os
import time
import urllib.error
import urllib.request

import lark_oapi as lark

APP_ID = os.getenv("FEISHU_APP_ID", "")
APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
ENCRYPT_KEY = os.getenv("FEISHU_ENCRYPT_KEY", "")
RAG_BASE = os.getenv("RAG_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def forward(open_id: str, text: str, event_id: str) -> int:
    """把长连接事件转成标准事件体，POST 给本地 /feishu/event，返回 HTTP 状态码。"""
    ts = str(int(time.time()))
    nonce = hashlib.md5(f"{open_id}{ts}".encode("utf-8")).hexdigest()[:8]
    body = json.dumps(
        {
            "schema": "2.0",
            "header": {
                "event_type": "im.message.receive_v1",
                "event_id": event_id,
                "token": "ws",
            },
            "event": {
                "sender": {"sender_id": {"open_id": open_id}},
                "message": {"content": json.dumps({"text": text}, ensure_ascii=False)},
            },
        },
        ensure_ascii=False,
    )
    sig = hashlib.sha256((ts + nonce + ENCRYPT_KEY + body).encode("utf-8")).hexdigest()
    req = urllib.request.Request(
        RAG_BASE + "/feishu/event",
        data=body.encode("utf-8"),
        method="POST",
        headers={
            "X-Lark-Request-Timestamp": ts,
            "X-Lark-Request-Nonce": nonce,
            "X-Lark-Signature": sig,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        print("[转发本地后端失败]", e)
        return 0


def on_message(data: "lark.im.v1.P2ImMessageReceiveV1") -> None:
    """收到 im.message.receive_v1：提取身份与文本，交给本地后端处理并回复。

    必须在 3 秒内返回（飞书超时会重推）；本地回环调用是毫秒级，且后端把
    "发消息"放进后台任务，故此处不等回复完成。
    """
    try:
        ev = data.event
        open_id = ev.sender.sender_id.open_id
        content = json.loads(ev.message.content or "{}")
        text = content.get("text", "")
        event_id = getattr(data.header, "event_id", "") or ""
        print(f"[收到消息] open_id={open_id} text={text!r}")
        st = forward(open_id, text, event_id)
        print(f"[已转交本地后端] HTTP {st}")
    except Exception as e:
        print("[处理事件异常]", e)


def main() -> None:
    if not APP_ID or not APP_SECRET:
        raise SystemExit("请先设置环境变量 FEISHU_APP_ID / FEISHU_APP_SECRET")
    handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(on_message)
        .build()
    )
    cli = lark.ws.Client(
        APP_ID, APP_SECRET, event_handler=handler, log_level=lark.LogLevel.INFO
    )
    print("长连接建立中……连接成功后，飞书后台事件订阅方式选「长连接」")
    cli.start()


if __name__ == "__main__":
    main()
