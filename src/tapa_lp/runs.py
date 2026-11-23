"""Persistência dos resultados: histórico comparável em JSON + export CSV."""
from __future__ import annotations

import csv
import io
import json
import os
import threading
from pathlib import Path

FIELDS = [
    "id", "testName", "boardId", "solver", "source", "width", "height",
    "status", "solved", "verified", "matchesSolution", "nodes", "backtracks",
    "decisions", "lpSolves", "deductions", "elapsed", "message", "timestamp",
]


class RunStore:
    def __init__(self, path: str | Path | None = None) -> None:
        default = Path(os.getenv("TAPA_DATA_DIR", Path.cwd() / "data")) / "runs.json"
        self.path = Path(path) if path else default
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def _read(self) -> list[dict]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []

    def add(self, run: dict) -> dict:
        with self._lock:
            runs = self._read()
            runs.insert(0, {k: run.get(k) for k in FIELDS})
            self.path.write_text(json.dumps(runs, ensure_ascii=False, indent=1), encoding="utf-8")
            return runs[0]

    def list(self, limit: int | None = None) -> list[dict]:
        runs = self._read()
        return runs[:limit] if limit else runs

    def clear(self) -> None:
        with self._lock:
            self.path.write_text("[]", encoding="utf-8")

    def summary(self) -> list[dict]:
        """Agregado por solver: taxa de resolução, média de nós e de tempo."""
        groups: dict[str, list[dict]] = {}
        for r in self._read():
            groups.setdefault(r.get("solver") or "?", []).append(r)
        out = []
        for solver, rs in sorted(groups.items()):
            ok = [r for r in rs if r.get("solved")]
            out.append({
                "solver": solver,
                "runs": len(rs),
                "solved": len(ok),
                "solveRate": round(100 * len(ok) / len(rs), 1) if rs else 0.0,
                "avgNodes": round(sum(r["nodes"] for r in rs) / len(rs), 1) if rs else 0,
                "avgElapsed": round(sum(r["elapsed"] for r in rs) / len(rs), 3) if rs else 0,
                "avgBacktracks": round(sum(r["backtracks"] for r in rs) / len(rs), 1) if rs else 0,
            })
        return out

    def csv(self) -> str:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        for r in self._read():
            writer.writerow(r)
        return buf.getvalue()
