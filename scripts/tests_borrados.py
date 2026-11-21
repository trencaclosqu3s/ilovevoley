#!/usr/bin/env python3
"""Lista los tests de pytest borrados frente a una ref y los restaura.

Es la herramienta de la revisión de una poda (docs/ai-guidelines/testing-guidelines.md, regla 11).

    python3 scripts/tests_borrados.py listar [--ref HEAD] RUTA...
    python3 scripts/tests_borrados.py restaurar [--ref HEAD] NODEID...

`listar` imprime el nodeid de cada test que existía en REF y ya no existe.
Un test renombrado o fusionado en un `parametrize` también sale: compruébalo
antes de restaurarlo.

`restaurar` copia el test de REF, con sus decoradores, al final de su clase
(la recrea vacía si ya no existe) o del fichero. No trae helpers, fixtures ni
imports: después, `uvx ruff check --select F821 <fichero>` te dice qué falta de REF.
"""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _decir(texto: str) -> None:
    sys.stdout.write(texto + "\n")


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=RAIZ, capture_output=True, text=True, check=True
    ).stdout


def _es_fichero_de_tests(ruta: str) -> bool:
    nombre = Path(ruta).name
    return nombre == "tests.py" or (
        nombre.startswith("test_") and nombre.endswith(".py")
    )


def _inicio(nodo: ast.AST) -> int:
    return min([d.lineno for d in nodo.decorator_list] + [nodo.lineno])


def _tests(fuente: str) -> dict[tuple[str, ...], ast.AST]:
    """(Clase, ..., test) -> nodo, para cada test del módulo."""
    encontrados: dict[tuple[str, ...], ast.AST] = {}

    def recorrer(nodo: ast.AST, clases: tuple[str, ...]) -> None:
        for hijo in ast.iter_child_nodes(nodo):
            if isinstance(hijo, ast.ClassDef):
                recorrer(hijo, (*clases, hijo.name))
            elif isinstance(
                hijo, (ast.FunctionDef, ast.AsyncFunctionDef)
            ) and hijo.name.startswith("test"):
                encontrados[(*clases, hijo.name)] = hijo

    recorrer(ast.parse(fuente), ())
    return encontrados


def listar(ref: str, rutas: list[str]) -> int:
    ficheros = [
        f
        for f in _git("ls-tree", "-r", "--name-only", ref, "--", *rutas).splitlines()
        if _es_fichero_de_tests(f)
    ]
    total = 0
    for fichero in ficheros:
        antes = _tests(_git("show", f"{ref}:{fichero}"))
        actual = RAIZ / fichero
        ahora = _tests(actual.read_text(encoding="utf-8")) if actual.exists() else {}
        for clave in antes:
            if clave not in ahora:
                _decir("::".join([fichero, *clave]))
                total += 1
    sys.stderr.write(f"# {total} tests borrados frente a {ref}\n")
    return 0


def _cabecera_de_clase(lineas: list[str], clase: ast.ClassDef) -> str:
    """La clase de REF sin sus métodos: decoradores, `class ...:` y docstring."""
    primero = clase.body[0]
    fin = primero.lineno - 1
    if isinstance(primero, ast.Expr) and isinstance(
        getattr(primero, "value", None), ast.Constant
    ):
        fin = primero.end_lineno
    return "".join(lineas[_inicio(clase) - 1 : fin])


def _clase(arbol: ast.AST, ruta: tuple[str, ...]) -> ast.ClassDef | None:
    nodo = arbol
    for nombre in ruta:
        nodo = next(
            (
                n
                for n in ast.iter_child_nodes(nodo)
                if isinstance(n, ast.ClassDef) and n.name == nombre
            ),
            None,
        )
        if nodo is None:
            return None
    return nodo


def restaurar(ref: str, nodeids: list[str]) -> int:
    for nodeid in nodeids:
        fichero, *clave = nodeid.split("::")
        clave = tuple(clave)
        actual = RAIZ / fichero
        if not actual.exists():
            _decir(f"{nodeid}: el fichero ya no existe; recupéralo con git show")
            return 1
        fuente_ref = _git("show", f"{ref}:{fichero}")
        lineas_ref = fuente_ref.splitlines(keepends=True)
        nodo = _tests(fuente_ref).get(clave)
        if nodo is None:
            _decir(f"{nodeid}: no existe en {ref}")
            return 1
        texto = actual.read_text(encoding="utf-8")
        if clave in _tests(texto):
            _decir(f"{nodeid}: ya existe")
            continue
        bloque = "".join(lineas_ref[_inicio(nodo) - 1 : nodo.end_lineno])
        lineas = texto.splitlines(keepends=True)
        if lineas and not lineas[-1].endswith("\n"):
            lineas[-1] += "\n"
        clases = clave[:-1]
        destino = _clase(ast.parse(texto), clases) if clases else None
        if clases and destino is not None:
            lineas[destino.end_lineno : destino.end_lineno] = ["\n", bloque]
        elif clases:
            clase_ref = _clase(ast.parse(fuente_ref), clases)
            lineas += ["\n\n", _cabecera_de_clase(lineas_ref, clase_ref), "\n", bloque]
        else:
            lineas += ["\n\n", bloque]
        actual.write_text("".join(lineas), encoding="utf-8")
        _decir(f"{nodeid}: restaurado")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="orden", required=True)
    for orden, ayuda in (("listar", "RUTA"), ("restaurar", "NODEID")):
        p = sub.add_parser(orden)
        p.add_argument("--ref", default="HEAD")
        p.add_argument("args", nargs="+", metavar=ayuda)
    opts = parser.parse_args(argv)
    if opts.orden == "listar":
        return listar(opts.ref, opts.args)
    return restaurar(opts.ref, opts.args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
