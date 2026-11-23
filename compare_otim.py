"""Compara a heurística de PL original contra variantes otimizadas.

Todas as variantes usam o MESMO conjunto de tabuleiros e o MESMO orçamento,
e todas continuam deduzindo apenas por inviabilidade da PL.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "src")

from tapa_solver_deterministico.model import BLACK
from tapa_solver_deterministico.verifier import verify
from tapa_lp.jobs import parse_cells
from tapa_lp.solver_lp import LPConfig, solve_with_lp

FRONT = Path("../Tapa-Puzzle-Frontend")

VARIANTES = {
    "A base (atual)": LPConfig(probe_scope="all", integral_exit=False, solver_name="cbc"),
    "B -solve dup +integral": LPConfig(probe_scope="all", integral_exit=True, solver_name="cbc"),
    "C +probe perto de pista": LPConfig(probe_scope="near_clue", integral_exit=True, solver_name="cbc"),
    "D iguais C, sem fluxo": LPConfig(probe_scope="near_clue", integral_exit=True,
                                      connectivity_lp=False, solver_name="cbc"),
}


def carrega(limite_por_porte=6):
    boards = json.loads((FRONT / "assets" / "boards-gridpuzzle.json").read_text(encoding="utf-8"))
    por_area: dict[int, list] = {}
    for b in boards:
        por_area.setdefault(b["width"], []).append(b)
    sel = []
    for tam in sorted(por_area):
        sel += por_area[tam][:limite_por_porte]
    return sel


def main():
    boards = carrega()
    print(f"tabuleiros: {len(boards)} (GridPuzzle, 6 a 12)\n")
    linhas = []
    for nome, cfg in VARIANTES.items():
        t_total = 0.0
        ok = 0
        nos = bts = pls = 0
        tempos = []
        for b in boards:
            puzzle, _ = parse_cells(b["width"], b["height"], b["cells"])
            t0 = time.monotonic()
            r = solve_with_lp(puzzle, cfg, timeout_seconds=3.0, node_limit=20000)
            dt = time.monotonic() - t0
            t_total += dt
            tempos.append(dt)
            if r.solved and verify(r.board).valid:
                ok += 1
            nos += r.stats.nodes
            bts += r.stats.backtracks
            pls += r.stats.lp_solves
        tempos.sort()
        linhas.append({
            "variante": nome, "ok": f"{ok}/{len(boards)}", "tempo": round(t_total, 1),
            "mediana": round(tempos[len(tempos)//2], 3), "nos": nos,
            "bt": bts, "pls": pls,
        })
        print(f"{nome:<26}{linhas[-1]['ok']:>8}{t_total:>9.1f}s  mediana {linhas[-1]['mediana']:.3f}s"
              f"  nós {nos:>6}  bt {bts:>6}  PLs {pls:>7}", flush=True)
    Path("results/comparacao_otimizacoes.json").write_text(
        json.dumps(linhas, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
