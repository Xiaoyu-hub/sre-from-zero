"""Day 4: 短链服务 + Prometheus metrics（可观测性第一步）。"""
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from pydantic import BaseModel

app = FastAPI(title="sre-from-zero", version="0.4.0")

# ========== 内存存储（后续换 Redis）==========
links: dict[str, str] = {}   # 短码 -> 长链接
clicks: dict[str, int] = {}  # 短码 -> 点击次数

# ========== Prometheus 指标 ==========
# Counter: 只增不减（请求总数、点击总数）
REQUESTS = Counter(
    "http_requests_total",
    "总请求数",
    ["method", "path", "status"],
)
CLICKS = Counter("shortener_clicks_total", "短链点击总次数")

# Gauge: 可增可减（在途请求数）
IN_PROGRESS = Gauge("http_requests_in_progress", "处理中的请求数")

# Histogram: 直方图（延迟分布，Day 7 用它算 P99）
DURATION = Histogram(
    "http_request_duration_seconds",
    "请求耗时（秒）",
    ["method", "path"],
)


# ========== 指标中间件：给所有请求统一记账 ==========
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    IN_PROGRESS.inc()
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        _record(request, "500")
        raise
    finally:
        IN_PROGRESS.dec()
    _record(request, str(response.status_code))
    DURATION.labels(
        method=request.method, path=_route_path(request)
    ).observe(time.perf_counter() - start)
    return response


def _route_path(request: Request) -> str:
    """取路由模板（/shorten、/{code}）而非真实路径：
    否则每个短码都会成为一个标签值，指标基数爆炸（高基数是 Prometheus 大忌）。"""
    route = request.scope.get("route")
    return getattr(route, "path", "unmatched")


def _record(request: Request, status: str) -> None:
    REQUESTS.labels(
        method=request.method, path=_route_path(request), status=status
    ).inc()


# ========== base62 短码生成 ==========
ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def base62_encode(n: int) -> str:
    """十进制整数转 base62 字符串（逢 62 进一，和十进制逢十进一同理）。"""
    if n == 0:
        return ALPHABET[0]
    chars = []
    while n > 0:
        n, r = divmod(n, 62)
        chars.append(ALPHABET[r])
    return "".join(reversed(chars))


def generate_code() -> str:
    """UUID 的 128 位整数做 base62 编码，取前 8 位当短码（带碰撞重试）。"""
    while True:
        code = base62_encode(uuid.uuid4().int)[:8]
        if code not in links:
            return code


# ========== 请求体模型（FastAPI 自动校验 JSON）==========
class ShortenRequest(BaseModel):
    url: str


# ========== 端点 ==========
@app.get("/")
def root():
    return {"service": "sre-from-zero", "status": "ok"}


@app.post("/shorten", status_code=201)
def shorten(req: ShortenRequest):
    """收长链接 -> 生成短码 -> 存内存表 -> 返回短码给用户。"""
    code = generate_code()
    links[code] = req.url
    clicks[code] = 0
    return {
        "short_code": code,
        "short_url": f"/{code}",
        "long_url": req.url,
    }


@app.get("/healthz")
def healthz():
    """健康检查端点（Day 5 的 K8s 探针会用它）。"""
    return {"status": "alive"}


@app.get("/metrics")
def metrics():
    """Prometheus 抓取端点：返回所有指标的文本格式。"""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/stats/{code}")
def stats(code: str):
    """查询短码的原始链接和点击次数（业务口径）。"""
    if code not in links:
        raise HTTPException(status_code=404, detail="short code not found")
    return {"short_code": code, "long_url": links[code], "clicks": clicks[code]}


# ========== 动态路由必须放在最后 ==========
@app.get("/{code}")
def redirect_to(code: str):
    """查表 -> 点击+1 -> 302 跳转到原始链接（no-store 防止缓存吞计数）。"""
    if code not in links:
        raise HTTPException(status_code=404, detail="short code not found")
    clicks[code] += 1
    CLICKS.inc()
    return RedirectResponse(
        url=links[code],
        status_code=302,
        headers={"Cache-Control": "no-store"},
    )