"""Day 3: URL 短链服务 — 短码生成 / 302 重定向 / 点击统计。"""
import uuid
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

app = FastAPI(title="sre-from-zero", version="0.2.0")

# ========== 内存存储（后续换 Redis）==========
links: dict[str, str] = {}   # 短码 -> 长链接
clicks: dict[str, int] = {}  # 短码 -> 点击次数

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
    """UUID 的 128 位整数做 base62 编码，取前 8 位当短码。"""
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


@app.get("/stats/{code}")
def stats(code: str):
    """查询短码的原始链接和点击次数。"""
    if code not in links:
        raise HTTPException(status_code=404, detail="short code not found")
    return {"short_code": code, "long_url": links[code], "clicks": clicks[code]}


# ========== 动态路由必须放在最后 ==========
@app.get("/{code}")
def redirect_to(code: str):
    """查表 -> 点击+1 -> 302 跳到原始链接。"""
    if code not in links:
        raise HTTPException(status_code=404, detail="short code not found")
    clicks[code] += 1
    return RedirectResponse(url=links[code], status_code=301)