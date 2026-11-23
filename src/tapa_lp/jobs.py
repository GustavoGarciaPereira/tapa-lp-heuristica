"""Execução de testes em segundo plano, com progresso ao vivo e cancelamento."""
from __future__ import annotations

import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from tapa_solver_deterministico.model import BLACK, Puzzle
from tapa_solver_deterministico.verifier import verify

from .instrumented import solve_com_progresso
from .solver_lp import LPConfig, solve_with_lp

MAX_LP_CELLS = int(os.getenv("TAPA_MAX_LP_CELLS", "400"))

SOLVERS: dict[str, dict] = {
    "deterministico": {
        "name": "Determinístico",
        "kind": "deterministico",
        "description": "Propagação de regras + primeira célula vazia em ordem de leitura (preta primeiro). Sem PL.",
    },
    "lp-first": {
        "name": "PL + primeira célula",
        "kind": "lp",
        "description": "PL só prova o que é obrigatório; ramifica na primeira célula vazia.",
        "config": dict(use_probe=True, branch="first", value_order="black_first",
                       probe_scope="near_clue", integral_exit=True, connectivity_lp=False),
    },
    "lp-frac": {
        "name": "PL + mais fracionária",
        "kind": "lp",
        "description": "PL prova obrigatórios; ramifica na célula mais perto de 0,5 na resposta da PL.",
        "config": dict(use_probe=True, branch="most_fractional", value_order="lp_guided",
                       probe_scope="near_clue", integral_exit=True, connectivity_lp=False),
    },
    "lp-patterns": {
        "name": "PL + mais restringida",
        "kind": "lp",
        "description": "PL prova obrigatórios; ramifica na célula com menos padrões compatíveis.",
        "config": dict(use_probe=True, branch="fewest_patterns", value_order="lp_guided",
                       probe_scope="near_clue", integral_exit=True, connectivity_lp=False),
    },
}


def parse_cells(width: int, height: int, cells: list[dict]) -> tuple[Puzzle, list[int] | None]:
    if len(cells) != width * height:
        raise ValueError("a quantidade de células não corresponde às dimensões")
    clues: dict[tuple[int, int], tuple] = {}
    for index, cell in enumerate(cells):
        if cell.get("type") != "clue":
            continue
        raw = str(cell.get("label", "")).strip()
        if not raw:
            raise ValueError(f"pista vazia na célula {divmod(index, width)}")
        runs: list = []
        for token in raw.split():
            if token in {"?", "-"}:
                runs.append("?")
            elif token.isdigit() and len(token) == 1:
                runs.append(int(token))
            elif token.isdigit():
                # "12" no formato compacto = grupos 1 e 2
                runs.extend(int(ch) for ch in token)
            else:
                raise ValueError(f"pista inválida na célula {divmod(index, width)}: {raw!r}")
        clues[divmod(index, width)] = tuple(runs)
    return Puzzle(height, width, clues), None


@dataclass
class Job:
    id: str
    testName: str
    boardId: str
    solver: str
    width: int
    height: int
    status: str = "queued"
    live: dict = field(default_factory=dict)
    result: dict | None = None
    error: str | None = None
    cancel: bool = False
    started_at: float = field(default_factory=time.time)


class JobManager:
    def __init__(self, store) -> None:
        self.store = store
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tapa")

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def public(self, job: Job) -> dict:
        data = {
            "id": job.id, "testName": job.testName, "boardId": job.boardId,
            "solver": job.solver, "status": job.status, "error": job.error,
            "elapsed": round(job.live.get("elapsed", time.time() - job.started_at), 3),
        }
        data.update({k: v for k, v in job.live.items() if k != "elapsed"})
        if job.result is not None:
            data["result"] = job.result
        return data

    def submit(self, *, testName: str, boardId: str, solver: str, width: int, height: int,
               cells: list[dict], solution: list[int] | None, source: str | None,
               timeout_seconds: float, node_limit: int) -> Job:
        if solver not in SOLVERS:
            raise ValueError(f"solver desconhecido: {solver}")
        job = Job(id=uuid.uuid4().hex[:12], testName=testName, boardId=boardId,
                  solver=solver, width=width, height=height)
        with self._lock:
            self._jobs[job.id] = job
        self._pool.submit(self._run, job, cells, solution, source, timeout_seconds, node_limit)
        return job

    def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None or job.status in {"done", "error", "cancelled"}:
            return False
        job.cancel = True
        return True

    # ------------------------------------------------------------------ worker
    def _run(self, job: Job, cells: list[dict], solution: list[int] | None,
             source: str | None, timeout_seconds: float, node_limit: int) -> None:
        job.status = "running"
        try:
            puzzle, _ = parse_cells(job.width, job.height, cells)
            spec = SOLVERS[job.solver]

            def progress(d: dict) -> None:
                job.live.update(d)

            if spec["kind"] == "lp" and job.width * job.height > MAX_LP_CELLS:
                raise ValueError(
                    f"tabuleiro com {job.width * job.height} células excede o limite de "
                    f"{MAX_LP_CELLS} para o método de PL (use o determinístico)")
            if spec["kind"] == "lp":
                board, stats, message, extra = None, None, "", {}
                r = solve_with_lp(
                    puzzle, LPConfig(**spec["config"]),
                    timeout_seconds=timeout_seconds, node_limit=node_limit,
                    progress=progress, should_stop=lambda: job.cancel,
                )
                board, message = r.board, r.message
                s = r.stats
                extra = {"lpSolves": s.lp_solves, "deductions": s.lp_deductions_black + s.lp_deductions_white}
                job.live.update({"nodes": s.nodes, "backtracks": s.backtracks,
                                 "decisions": s.decisions, "elapsed": s.elapsed_seconds})
                cancelled = getattr(s, "cancelled", False)
            else:
                board, s, message = solve_com_progresso(
                    puzzle, progress=progress, should_stop=lambda: job.cancel,
                    timeout_seconds=timeout_seconds, node_limit=node_limit)
                extra = {"lpSolves": 0, "deductions": 0}
                job.live.update({"nodes": s.nodes, "backtracks": s.backtracks,
                                 "decisions": s.decisions, "elapsed": s.elapsed_seconds})
                cancelled = s.cancelled

            verified = verify(board).valid if board is not None else False
            matches = None
            if solution and board is not None and len(solution) == len(board.values):
                matches = all((1 if v == BLACK else 0) == int(sol)
                              for v, sol in zip(board.values, solution))
            status = "cancelled" if cancelled else ("solved" if board is not None else "failed")

            job.result = {
                "status": status, "solved": board is not None, "verified": verified,
                "matchesSolution": matches,
                "solution": ([1 if v == BLACK else 0 for v in board.values] if board is not None else None),
                "nodes": getattr(s, "nodes", 0), "backtracks": getattr(s, "backtracks", 0),
                "decisions": getattr(s, "decisions", 0),
                "elapsed": round(getattr(s, "elapsed_seconds", job.live.get("elapsed", 0)), 3),
                "message": message, **extra,
            }
            job.live.update({"nodes": job.result["nodes"], "backtracks": job.result["backtracks"],
                             "elapsed": job.result["elapsed"]})
            job.status = status
            self.store.add({
                "id": job.id, "testName": job.testName, "boardId": job.boardId,
                "solver": job.solver, "source": source, "width": job.width, "height": job.height,
                "status": status, "solved": job.result["solved"], "verified": verified,
                "matchesSolution": matches, "nodes": job.result["nodes"],
                "backtracks": job.result["backtracks"], "decisions": job.result["decisions"],
                "lpSolves": job.result["lpSolves"], "deductions": job.result["deductions"],
                "elapsed": job.result["elapsed"], "message": message,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            })
        except Exception as exc:  # erro de entrada ou falha interna
            job.error = str(exc)
            job.status = "error"
