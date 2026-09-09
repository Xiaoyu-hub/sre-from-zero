# ==================== Day 1: 多阶段构建 Hello World ====================
# 多阶段构建的目的：
#   - 第一阶段（builder）安装依赖，生成 wheel
#   - 第二阶段（runtime）只复制需要的文件，镜像更小、更安全
# 阶段一与二可以共享层缓存。

# ---------- 阶段 1: builder ----------
FROM python:3.11-slim AS builder

# 设置工作目录
WORKDIR /build

# 先单独复制 requirements.txt 并安装依赖
# 这样改代码不会触发依赖重装（利用 Docker 层缓存）
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# ---------- 阶段 2: runtime ----------
FROM python:3.11-slim

# 加元数据（标签），生产里很重要
LABEL maintainer="sre-from-zero" \
      version="0.1.0" \
      description="Day 1 hello world — FastAPI on Docker"

# 容器内创建一个非 root 用户（生产安全最佳实践）
RUN useradd --create-home --shell /bin/bash appuser

# 切换工作目录
WORKDIR /app

# 从 builder 阶段复制已安装的 Python 包
COPY --from=builder /root/.local /home/appuser/.local

# 复制应用代码
COPY app/ ./app/

# 让 PATH 包含用户级 bin，并把目录所有权给 appuser
ENV PATH=/home/appuser/.local/bin:$PATH \
    PYTHONUNBUFFERED=1

# 切换到非 root 用户
USER appuser

# 暴露端口（仅声明，不会真的发布）
EXPOSE 8000

# 容器启动命令
# --host 0.0.0.0 让容器外能访问
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
