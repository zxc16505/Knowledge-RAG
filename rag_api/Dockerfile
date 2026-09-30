FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
# 镜像瘦身：只装服务核心依赖；向量/重排模型依赖（sentence-transformers）较重，
# 缺省时服务自动降级为关键词检索，仍可完整演示权限感知链路。
# 需要真向量检索时改为: pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir fastapi==0.111.0 "uvicorn[standard]==0.30.1" pydantic==2.7.4 qdrant-client==1.9.0

COPY app.py .
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
