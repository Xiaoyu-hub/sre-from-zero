"""Day 1: FastAPI hello world — 验证 Docker 化基础链路。"""
from fastapi import FastAPI

app = FastAPI(title="sre-from-zero", version="0.1.0")


@app.get("/")
def root():
    return {"service": "sre-from-zero", "status": "ok"}


@app.get("/healthz")
def healthz():
    """K8s 后续会用到的健康检查端点。"""
    return {"status": "alive"}
