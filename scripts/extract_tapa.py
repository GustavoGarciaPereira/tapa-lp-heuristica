"""Baixa full_dataset.jsonl do HuggingFace em streaming e mantém só os Tapa.

Não grava os 663 MB em disco: filtra linha a linha conforme chega.
Uso:
    python scripts/extract_tapa.py            # -> data/tapa_full.jsonl
    python scripts/extract_tapa.py --check    # só conta e compara com o esperado
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

URL = "https://huggingface.co/datasets/bluecoconut/pencil-puzzle-bench/resolve/main/full_dataset.jsonl"


def main() -> None:
    check = "--check" in sys.argv
    destino = Path("data/tapa_full.jsonl")
    destino.parent.mkdir(parents=True, exist_ok=True)
    total = tapa = 0
    print("baixando em streaming (663 MB não vão para o disco)…", flush=True)
    with urllib.request.urlopen(URL) as resp, destino.open("w", encoding="utf-8") as out:
        for bruto in resp:
            total += 1
            if b'"pid": "tapa"' in bruto or b'"pid":"tapa"' in bruto:
                tapa += 1
                if not check:
                    out.write(bruto.decode("utf-8"))
            if total % 10000 == 0:
                print(f"  {total} linhas lidas, {tapa} Tapa", flush=True)
    print(f"\ntotal de tabuleiros no dataset: {total}")
    print(f"tabuleiros Tapa: {tapa}")
    if check:
        destino.unlink(missing_ok=True)
        print("esperado pelo relatório do projeto: 653 -> " + ("confere" if tapa == 653 else "DIVERGE"))
    else:
        print(f"salvo em {destino}")
        amostra = json.loads(destino.read_text(encoding="utf-8").splitlines()[0])
        print("chaves de cada registro:", ", ".join(amostra))
        print("\nATENÇÃO: este arquivo NÃO traz as pistas nem a grade solução —")
        print("a solução vem como sequência de cliques (solution_enc), não como grid.")
        print("Para o benchmark use os JSONs já decodificados do frontend,")
        print("que saíram deste mesmo dataset (assets/boards.json).")


if __name__ == "__main__":
    main()
