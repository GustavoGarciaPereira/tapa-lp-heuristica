"""Interface de linha de comando: resolver um tabuleiro ou comparar heurísticas."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tapa_solver_deterministico.solver import solve as solve_deterministico

from .io_puzzles import load_puzzle, render_solution
from .uniqueness import count_solutions
from .solver_lp import LPConfig, solve_with_lp

STRATEGIES = {
    "deterministico": None,
    "lp-first": LPConfig(use_probe=True, branch="first", value_order="black_first"),
    "lp-frac": LPConfig(use_probe=True, branch="most_fractional", value_order="lp_guided"),
    "lp-patterns": LPConfig(use_probe=True, branch="fewest_patterns", value_order="lp_guided"),
}


def _run(path: Path, strategy: str, timeout: float, node_limit: int):
    puzzle = load_puzzle(path)
    cfg = STRATEGIES[strategy]
    if cfg is None:
        r = solve_deterministico(puzzle, timeout_seconds=timeout, node_limit=node_limit)
        return puzzle, r.solved, r.board, {
            "nodes": r.stats.nodes, "backtracks": r.stats.backtracks,
            "decisions": r.stats.decisions, "lp_solves": 0,
            "deducoes": 0, "seconds": r.stats.elapsed_seconds, "message": r.message,
        }
    r = solve_with_lp(puzzle, cfg, timeout_seconds=timeout, node_limit=node_limit)
    s = r.stats
    return puzzle, r.solved, r.board, {
        "nodes": s.nodes, "backtracks": s.backtracks, "decisions": s.decisions,
        "lp_solves": s.lp_solves,
        "deducoes": s.lp_deductions_black + s.lp_deductions_white,
        "seconds": s.elapsed_seconds, "message": r.message,
    }


def cmd_solve(args) -> int:
    puzzle, solved, board, info = _run(Path(args.puzzle), args.strategy, args.timeout, args.node_limit)
    print(f"tabuleiro : {puzzle.name} ({puzzle.rows}x{puzzle.cols}, {len(puzzle.clues)} pistas)")
    print(f"estratégia: {args.strategy}")
    print(f"resultado : {'RESOLVIDO' if solved else 'NÃO RESOLVIDO'} — {info['message']}")
    if board is not None:
        print(f"\n{board.render()}\n")
        print("solução (# = preta):")
        print(render_solution(board))
    print("\nestatísticas:")
    for k in ("nodes", "decisions", "backtracks", "lp_solves", "deducoes"):
        print(f"  {k:<12} {info[k]}")
    print(f"  {'segundos':<12} {info['seconds']:.3f}")
    return 0 if solved else 1


def cmd_bench(args) -> int:
    folder = Path(args.folder)
    files = sorted(folder.glob("*.txt"))
    if not files:
        print(f"nenhum .txt em {folder}")
        return 1
    strategies = args.strategies or list(STRATEGIES)
    header = f"{'tabuleiro':<16}{'estratégia':<17}{'ok':<5}{'nós':>9}{'backtr':>8}{'decis':>7}{'PLs':>7}{'dedu':>6}{'seg':>8}"
    print(header)
    print("-" * len(header))
    for f in files:
        for st in strategies:
            puzzle, solved, _, info = _run(f, st, args.timeout, args.node_limit)
            print(f"{f.stem:<16}{st:<17}{'sim' if solved else 'não':<5}"
                  f"{info['nodes']:>9}{info['backtracks']:>8}{info['decisions']:>7}"
                  f"{info['lp_solves']:>7}{info['deducoes']:>6}{info['seconds']:>8.3f}")
        print()
    return 0


def cmd_check(args) -> int:
    puzzle = load_puzzle(Path(args.puzzle))
    sols = count_solutions(puzzle, max_solutions=args.max)
    print(f"tabuleiro : {puzzle.name} ({puzzle.rows}x{puzzle.cols}, {len(puzzle.clues)} pistas)")
    if not sols:
        print("soluções  : NENHUMA (tabuleiro impossível)")
        return 1
    print(f"soluções  : {len(sols)}" + (" ou mais" if len(sols) >= args.max else ""))
    for i, sol in enumerate(sols, 1):
        print(f"  solução {i}: {sum(sol)} células pretas")
    print("veredito  :", "única (bem formado)" if len(sols) == 1 else "AMBÍGUO — mais de uma solução")
    return 0 if len(sols) == 1 else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tapa-lp", description="Tapa: determinístico + heurística de PL")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_solve = sub.add_parser("solve", help="resolve um tabuleiro .txt")
    p_solve.add_argument("puzzle")
    p_solve.add_argument("--strategy", default="lp-frac", choices=list(STRATEGIES))
    p_solve.add_argument("--timeout", type=float, default=120.0)
    p_solve.add_argument("--node-limit", type=int, default=1_000_000)
    p_solve.set_defaults(func=cmd_solve)

    p_bench = sub.add_parser("bench", help="compara estratégias em uma pasta de tabuleiros")
    p_bench.add_argument("folder")
    p_bench.add_argument("--strategies", nargs="*", choices=list(STRATEGIES))
    p_bench.add_argument("--timeout", type=float, default=120.0)
    p_bench.add_argument("--node-limit", type=int, default=1_000_000)
    p_bench.set_defaults(func=cmd_bench)

    p_check = sub.add_parser("check", help="conta quantas soluções o tabuleiro admite")
    p_check.add_argument("puzzle")
    p_check.add_argument("--max", type=int, default=2)
    p_check.set_defaults(func=cmd_check)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
