"""Leitura e escrita de tabuleiros em texto simples.

Formato (linhas iniciadas por # são comentários):

    # nome opcional na primeira linha de comentário
    8 8
    . . . . . . . .
    . . 1,2 . . . . .
    . . . . . 3 . .
    ...

` . ` = célula sem pista; `1,2` = pista com dois grupos (1 e 2);
`?` sozinho ou dentro da lista = curinga (bloco de tamanho desconhecido).
"""
from __future__ import annotations

from pathlib import Path

from tapa_solver_deterministico.model import BLACK, Puzzle


def load_puzzle(path: str | Path) -> Puzzle:
    text = Path(path).read_text(encoding="utf-8")
    name = Path(path).stem
    rows_data: list[list[str]] = []
    dims: tuple[int, int] | None = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            if name == Path(path).stem and line.lstrip("# ").strip():
                name = line.lstrip("# ").strip()
            continue
        tokens = line.replace(",", " , ").split()
        if dims is None and len(tokens) == 2 and all(t.isdigit() for t in tokens):
            dims = (int(tokens[0]), int(tokens[1]))
            continue
        # remonta os tokens de pista que foram separados pela vírgula
        merged: list[str] = []
        pending: list[str] = []
        for tok in line.split():
            if tok.endswith(",") or pending:
                pending.append(tok.rstrip(","))
                if not tok.endswith(","):
                    merged.append("".join(pending))
                    pending = []
            else:
                merged.append(tok)
        rows_data.append(merged)

    if dims is None:
        dims = (len(rows_data), len(rows_data[0]) if rows_data else 0)
    rows, cols = dims
    if len(rows_data) != rows:
        raise ValueError(f"{path}: esperadas {rows} linhas, encontradas {len(rows_data)}")

    clues: dict[tuple[int, int], tuple[int | str, ...]] = {}
    for r, line in enumerate(rows_data):
        if len(line) != cols:
            raise ValueError(f"{path}: linha {r} deve ter {cols} células, tem {len(line)}")
        for c, token in enumerate(line):
            if token in {".", "-", ""}:
                continue
            runs: list[int | str] = []
            for part in token.split(","):
                part = part.strip()
                if part in {"?", "-"}:
                    runs.append("?")
                elif part.isdigit():
                    runs.append(int(part))
                else:
                    raise ValueError(f"{path}: pista inválida em ({r}, {c}): {token!r}")
            clues[(r, c)] = tuple(runs)
    return Puzzle(rows, cols, clues, name)


def render_solution(board) -> str:
    lines = []
    for row in range(board.puzzle.rows):
        cells = []
        for col in range(board.puzzle.cols):
            cells.append({BLACK: "#", 0: ".", -1: "?"}[board.get(row, col)])
        lines.append("".join(cells))
    return "\n".join(lines)
