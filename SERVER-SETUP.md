# 服务器一次性初始化（约 10 分钟，之后 push 即自动部署）

适用：任意一台 Linux 云主机（2C4G 足够，轻量 ECS 一年几百元的档位可跑）。

## 1. 装 Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo systemctl enable --now docker
sudo usermod -aG docker $USER   # 重新登录生效
```

## 2. 拉仓库、起服务

```bash
sudo mkdir -p /opt/knowledge-rag && sudo chown $USER /opt/knowledge-rag
cd /opt/knowledge-rag
git clone <你的仓库地址> .
cp .env.example .env
# 生成三个密钥填进 .env：
openssl rand -hex 16   # API_GLOBAL_KEY
openssl rand -hex 16   # WEBHOOK_SECRET
openssl rand -hex 16   # FEISHU_ENCRYPT_KEY（演示用；接真飞书时改为后台的 Encrypt Key）

mkdir -p rag_data
cp feishu_demo/dept_map.json rag_data/dept_map.json

docker compose up -d --build
set -a; . ./.env; set +a
curl -H "X-API-Key: $API_GLOBAL_KEY" http://127.0.0.1:8000/health   # {"status":"ok","embedding":false,"qdrant":true}
```

想启用真向量检索：把 `bge-base-zh-v1.5` 模型放到 `./models/BAAI/bge-base-zh-v1.5/`，重启即可（compose 已配 `HF_HUB_OFFLINE=1`，全程离线）。

## 3. 配 GitHub Actions 部署密钥

```bash
ssh-keygen -t ed25519 -f ~/.ssh/github_deploy -N ""   # 服务器上生成专用密钥对
cat ~/.ssh/github_deploy.pub >> ~/.ssh/authorized_keys
echo "PRIVATE_KEY 内容 = ~/.ssh/github_deploy"
```

记下三样东西，到 GitHub 仓库 **Settings -> Secrets and variables -> Actions -> New repository secret**：

| Secret 名 | 值 |
|---|---|
| `DEPLOY_HOST` | 服务器公网 IP |
| `DEPLOY_USER` | 你登录用的用户名 |
| `DEPLOY_SSH_KEY` | `~/.ssh/github_deploy` 的完整私钥内容 |

配置完成后，每次 `git push` 到 main：GitHub 自动 SSH 到服务器执行 `git pull + compose up -d --build + /health 冒烟`。不配置则 Deploy workflow 自动跳过，CI（安全用例回归 + compose 校验）照常运行。

## 4. 本地验证部署链路（可选）

```bash
ssh -i ~/.ssh/github_deploy $DEPLOY_USER@$DEPLOY_HOST ". /opt/knowledge-rag/.env; curl -s -H \"X-API-Key: \$API_GLOBAL_KEY\" http://127.0.0.1:8000/health"
```

## 安全注意

- 8000/3000 端口默认只对公网开放的话，务必先用随机长密钥（本仓库 `.env.example` 已提示）；更稳妥的做法是服务器上只 bind 127.0.0.1，前置 nginx/Caddy 加 TLS。
- `/api/retrieve` 是**内部调试口**（API Key + 必填 user_id + 未知身份 fail-closed）；对外用户侧只应暴露 `/feishu/event`（飞书签名验签）。
- Qdrant 不映射公网端口（compose 里只 `expose`），仅内网可达。
