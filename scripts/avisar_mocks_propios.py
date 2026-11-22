#!/usr/bin/env python3
"""Avisa, sin bloquear el commit, de mocks nuevos sobre código propio en tests.

Hook de pre-commit (regla 7 de docs/ai-guidelines/testing-guidelines.md).
Solo mira las líneas añadidas en el commit, no el código heredado. Señala:

- `patch("ilovevoley....")` (en una línea o multilínea) sobre un módulo propio
  que no está en FRONTERAS;
- `SimpleNamespace(` usado para montar objetos de dominio.

Una línea que mockea una frontera no listada se silencia con `# frontera`.
Siempre sale con 0: es un aviso para quien escribe, no una prohibición.
"""

from __future__ import annotations

import re
import subprocess
import sys

# Fronteras donde mockear es lo correcto: red (scraping federativo, logos,
# YouTube, DNS), Google Vision, Web Push, email, broker de Celery, logger y
# reloj. Orientativa: amplíala cuando aparezca otra.
FRONTERAS = re.compile(
    r"safe_get|requests\b|getaddrinfo|_fetch_|fetch_|download_|_pdf_text"
    r"|acta_vision|read_acta|vision"
    r"|send_web_push|pywebpush_send"
    r"|send_mail"
    r"|\.delay$|\.chord$|\.logger\b|timezone\.now"
)
PATCH_PROPIO = re.compile(r"""\bpatch\(\s*["'](ilovevoley\.[\w.]+)""")
PATCH_MULTILINEA = re.compile(r"\bpatch\(\s*$")
CADENA_PROPIA = re.compile(r"""^\s*["'](ilovevoley\.[\w.]+)""")
SIMPLE_NAMESPACE = re.compile(r"\bSimpleNamespace\(")


def _decir(*partes: object) -> None:
    sys.stdout.write(" ".join(map(str, partes)) + "\n")


def lineas_añadidas(ficheros: list[str]) -> list[tuple[str, str]]:
    diff = subprocess.run(
        ["git", "diff", "--cached", "-U0", "--no-color", "--", *ficheros],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    actual, añadidas = "", []
    for linea in diff.splitlines():
        if linea.startswith("+++ b/"):
            actual = linea[6:]
        elif linea.startswith("+") and not linea.startswith("+++"):
            añadidas.append((actual, linea[1:]))
    return añadidas


def main(ficheros: list[str]) -> int:
    avisos = []
    fichero_anterior = ""
    esperando_objetivo = False
    for fichero, linea in lineas_añadidas(ficheros):
        if fichero != fichero_anterior:
            fichero_anterior = fichero
            esperando_objetivo = False
        if "# frontera" in linea:
            esperando_objetivo = False
            continue
        objetivo = PATCH_PROPIO.search(linea)
        if not objetivo and esperando_objetivo:
            objetivo = CADENA_PROPIA.match(linea)
        esperando_objetivo = bool(PATCH_MULTILINEA.search(linea))
        if objetivo and not FRONTERAS.search(objetivo.group(1)):
            avisos.append(f"{fichero}: mock de código propio: {objetivo.group(1)}")
        if SIMPLE_NAMESPACE.search(linea):
            avisos.append(f"{fichero}: SimpleNamespace en un test: {linea.strip()}")
    if avisos:
        _decir("\n".join(avisos))
        _decir(
            "\nAviso (regla 7 de docs/ai-guidelines/testing-guidelines.md): usa "
            "objetos reales y mockea solo fronteras. Si es una frontera, marca la "
            "línea con `# frontera`."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
