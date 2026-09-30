# knowledge-rag — 权限感知 RAG 问答运行时

[![CI](https://github.com/<GH_USER>/knowledge-rag/actions/workflows/ci.yml/badge.svg)](https://github.com/<GH_USER>/knowledge-rag/actions/workflows/ci.yml)

个人项目：一个把"企业知识库问答"做成**可验收成果**的最小运行时——检索在服务端按提问人身份做部门硬过滤，权限约束在模型上下文之外确定性生效，提示词注入无法绕过。

> 语料为脱敏/模拟的企业文档，非任何公司生产数据。评测注明"模拟电商场景"。

## 核心设计：权限感知检索（服务端硬过滤）

```
飞书事件(签名)  ──验签──►  /feishu/event        ──►  身份 = 事件体 sender.open_id（客户端不可伪造）
Gitea push      ──webhook──►  /api/webhook       ──►  增量重建索引（只读挂载 vault，程序绝不写源笔记）
                                      │
                                      ▼
                      服务端查 dept_map → 部门集合（未知身份 fail-closed）
                                      │
                                      ▼
                 Qdrant search(filter=must department∈depts)   ← 别的部门数据根本不进上下文
                                      │
                                      ▼
                        拼 prompt → 生成答案（带来源、命中阈值防编造）
```

| 机制 | 说明 |
|---|---|
| 身份盖章 | `/feishu/event` 校验 `X-Lark-Signature = SHA256(timestamp+nonce+encrypt_key+body)`，身份取**已验签事件体**，请求里的 `user_id` 字段一概不看 |
| 检索层过滤 | `department` 在入库时按 vault 顶层目录打标；查询时服务端注入 `Filter(must=MatchAny(本部门, 公共域))` |
| 注入免疫 | 攻击者/模型只能改变查询文本，不能改变过滤域——不在上下文里的内容无法被套出 |
| fail-closed | 无 key/验签失败/查不到部门映射 → 一律拒绝或空结果，不放行 |
| 降级可用 | 无 Qdrant/无模型权重时自动降级关键词检索，权限过滤同样生效（CI 即跑此模式） |

## 快速开始（30 秒，无需 GPU/模型）

```bash
pip install fastapi "uvicorn[standard]" pydantic
# Linux/macOS
VAULT_PATH=$PWD/feishu_demo/demo_vault DEPT_MAP_PATH=$PWD/feishu_demo/dept_map.json \
FEISHU_ENCRYPT_KEY=demo_key API_GLOBAL_KEY=demo_api uvicorn rag_api.app:app --port 8000 &
curl -X POST -H "X-API-Key: demo_api" http://127.0.0.1:8000/api/reload
FEISHU_ENCRYPT_KEY=demo_key API_GLOBAL_KEY=demo_api python rag_api/mock_feishu_event.py
```

输出 `7/7 case(s) passed`——覆盖：合法签名放行 / 篡改 body 拒绝 / 伪造签名拒绝 / 注入诱导不泄露跨部门内容 / 调试口无 key 拒绝 / 未知身份 fail-closed / 部门过滤正确命中。

## Docker 部署

```bash
cp .env.example .env   # 改三个密钥
docker compose up -d --build
curl http://127.0.0.1:8000/health
```

服务器上配好 GitHub Secrets（`DEPLOY_HOST/DEPLOY_USER/DEPLOY_SSH_KEY`）后，push main 自动部署，见 [SERVER-SETUP.md](SERVER-SETUP.md)。

## 检索质量评测（eval/）

同一套模型与代码，在自建模拟电商语料（32 篇文档 / 34 条查询）上实跑：

| 配置 | recall@1 | MRR |
|---|---|---|
| 向量单阶段（bge-base-zh） | 0.882 | 0.936 |
| 向量 + Rerank（bge-reranker-v2-m3） | **0.971** | **0.985** |

结论：Rerank 精排价值随语料规模与查询多样性上升而显现（小语料反而降 MRR）；3 次连跑完全一致，可复现。详见 [eval/evidence/电商场景模拟评测报告.md](eval/evidence/电商场景模拟评测报告.md)。

```bash
python eval/eval.py --golden eval/evidence/golden_set_ecom.json   # 需下载 bge 模型
```

## 目录结构

```
rag_api/            FastAPI 检索服务（app.py v1.2）+ 飞书事件 mock 脚本 + Dockerfile
feishu_demo/        三部门演示语料 + dept_map.json（安全用例回归的数据底座）
eval/               检索质量评测：黄金集、评测脚本、模拟电商场景实跑报告
docker-compose.yml  gitea + qdrant(仅内网) + rag_api 一键编排
.github/workflows/  ci.yml（安全用例回归+compose校验，push 即跑）/ deploy.yml（配 Secrets 后自动 SSH 部署）
```

## 技术栈

Python · FastAPI · Qdrant（metadata 硬过滤）· BGE embedding + Reranker（交叉编码器精排）· Gitea webhook 增量索引 · 飞书签名事件（身份盖章）· Docker Compose · GitHub Actions
