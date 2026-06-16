# syntax=docker/dockerfile:1

# ── HSAP UI：Label Studio 工程 (apps/hsap-platform) ──
# 构建前在宿主机执行: bash scripts/build_hsap_ls_ui.sh
# 或 CI 将 dist 拷入 platform/ui-hsap/dist

# ── Platform API ──
FROM python:3.11-slim AS platform

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/data/hsap/platform

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl bash \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /data/hsap

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY platform/ ./platform/
# 前端静态包（scripts/build_web.sh 生成；推 GHCR 前必须已 build）
COPY platform/ui-hsap/dist ./platform/ui-hsap/dist
COPY scripts/ ./scripts/
COPY datasets/ ./datasets/
COPY as.py workflow.registry.yaml ./
COPY algorithms/registry.yaml ./algorithms/

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8787

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "-m", "as_platform.api.server", "--host", "0.0.0.0", "--port", "8787"]
