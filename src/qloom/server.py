"""Local CPU Studio; bounded inputs, one compilation at a time, no remote service."""

import json
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .compiler import compile_circuit
from .devices import device_named, make_device
from .examples import example_list

ROOT = Path(__file__).parent
DATA = ROOT / "data"
lock = Lock()
app = FastAPI(title="QLOOM local compiler", version="0.1.0", docs_url="/api/docs")


class CompileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    qasm: str = Field(min_length=1, max_length=100_000)
    device: str = "line-5"
    budget: int = Field(default=4, ge=1, le=24)
    seed: int = Field(default=7, ge=0, lt=2**32)
    strategy: str = "learned"


@app.middleware("http")
async def local_request_boundary(request: Request, call_next):
    origin = request.headers.get("origin")
    if origin and urlsplit(origin).netloc != request.headers.get("host"):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            {"detail": "Cross-origin requests are disabled for this local Studio."}, status_code=403
        )
    content_length = request.headers.get("content-length")
    if content_length and (not content_length.isdigit() or int(content_length) > 130_000):
        from fastapi.responses import JSONResponse

        return JSONResponse({"detail": "Request exceeds 130 KB."}, status_code=413)
    return await call_next(request)


@app.get("/api/examples")
def examples():
    return example_list()


@app.get("/api/devices")
def devices():
    return [
        make_device(shape, n).to_dict() for n in range(2, 9) for shape in ("line", "ring", "star", "grid")
    ]


@app.get("/api/demo")
def demo():
    path = DATA / "demo.json"
    if not path.exists():
        raise HTTPException(404, "Recorded demo not installed. Compile an example to begin.")
    return json.loads(path.read_text())


@app.get("/api/benchmarks")
def benchmarks():
    path = DATA / "benchmark-summary.json"
    return json.loads(path.read_text()) if path.exists() else {"status": "not installed"}


@app.post("/api/compile")
def compile_request(body: CompileRequest):
    if not lock.acquire(blocking=False):
        raise HTTPException(409, "A compilation is already running. Wait for it to finish.")
    try:
        return compile_circuit(body.qasm, device_named(body.device), body.budget, body.seed, body.strategy)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Compilation failed: {type(exc).__name__}: {exc}") from exc
    finally:
        lock.release()


@app.get("/")
def index():
    return FileResponse(ROOT / "web" / "index.html")


app.mount("/", StaticFiles(directory=ROOT / "web"), name="studio")
