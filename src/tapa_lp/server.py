"""Servidor único: API dos solvers + frontend estático (mesma origem, sem CORS)."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from tapa_solver_deterministico.model import Puzzle
from tapa_solver_deterministico.solver import solve as solve_deterministico

from .jobs import SOLVERS, JobManager, parse_cells
from .runs import RunStore

from . import solver_lp as _solver_lp  # garante import do pacote

MAX_BOARD_AREA = int(os.getenv("TAPA_MAX_AREA", "4000"))

app = FastAPI(title="Tapa — API dos solvers", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

store = RunStore()
manager = JobManager(store)


class CellInput(BaseModel):
    type: str
    label: str = ""


class JobRequest(BaseModel):
    testName: str = ""
    boardId: str = "board"
    solver: str = "lp-patterns"
    width: int = Field(ge=1, le=200)
    height: int = Field(ge=1, le=200)
    cells: list[CellInput]
    solution: list[int] | None = None
    source: str | None = None
    timeoutSeconds: float = Field(default=60.0, gt=0, le=1800)
    nodeLimit: int = Field(default=1_000_000, gt=0)


class SyncRequest(JobRequest):
    pass


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "solvers": len(SOLVERS), "runs": len(store.list())}


@app.get("/api/solvers")
def list_solvers() -> dict:
    return {"solvers": [
        {"id": k, "name": v["name"], "description": v["description"], "kind": v["kind"]}
        for k, v in SOLVERS.items()
    ]}


@app.post("/api/jobs")
def create_job(req: JobRequest) -> dict:
    if req.width * req.height > MAX_BOARD_AREA:
        raise HTTPException(400, f"tabuleiro acima de {MAX_BOARD_AREA} células")
    try:
        job = manager.submit(
            testName=(req.testName.strip() or f"teste-{len(store.list()) + 1}"),
            boardId=req.boardId, solver=req.solver, width=req.width, height=req.height,
            cells=[c.model_dump() for c in req.cells], solution=req.solution,
            source=req.source, timeout_seconds=req.timeoutSeconds, node_limit=req.nodeLimit,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"id": job.id, "status": job.status}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(404, "job não encontrado")
    return manager.public(job)


@app.post("/api/jobs/{job_id}/cancel")
def job_cancel(job_id: str) -> dict:
    return {"cancelled": manager.cancel(job_id)}


@app.post("/api/solve")
def solve_sync(req: SyncRequest) -> dict:
    """Chamada direta (sem polling), compatível com o contrato do projeto original."""
    try:
        puzzle, _ = parse_cells(req.width, req.height, [c.model_dump() for c in req.cells])
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if req.solver == "deterministico":
        r = solve_deterministico(puzzle, timeout_seconds=req.timeoutSeconds, node_limit=req.nodeLimit)
        return {"solved": r.solved, "message": r.message,
                "nodes": r.stats.nodes, "backtracks": r.stats.backtracks,
                "solution": ([1 if v == 1 else 0 for v in r.board.values] if r.board else None)}
    raise HTTPException(400, "use POST /api/jobs para os solvers com PL")


@app.get("/api/runs")
def list_runs(limit: int | None = None) -> dict:
    return {"runs": store.list(limit), "summary": store.summary()}


@app.delete("/api/runs")
def clear_runs() -> dict:
    store.clear()
    return {"ok": True}


@app.get("/api/runs.csv", response_class=PlainTextResponse)
def runs_csv() -> str:
    return store.csv()


def find_frontend() -> Path | None:
    env = os.getenv("TAPA_FRONTEND_DIR")
    candidates = [Path(env)] if env else []
    here = Path(__file__).resolve()
    candidates += [Path.cwd() / "Tapa-Puzzle-Frontend",
                   here.parents[2] / "Tapa-Puzzle-Frontend",
                   here.parents[3] / "Tapa-Puzzle-Frontend"]
    for c in candidates:
        if c and (c / "index.html").exists():
            return c
    return None


def mount_frontend() -> Path | None:
    folder = find_frontend()
    if folder is not None:
        app.mount("/", StaticFiles(directory=str(folder), html=True), name="frontend")
    return folder


def run() -> None:
    import uvicorn

    folder = mount_frontend()
    port = int(os.getenv("TAPA_PORT", "8000"))
    print(f"frontend: {folder if folder else 'não encontrado (só a API)'}")
    print(f"abra http://127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    run()
