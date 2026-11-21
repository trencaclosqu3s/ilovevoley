#!/usr/bin/env python3
"""Rompe el código un momento y comprueba que los tests se ponen en rojo.

Aplica una sustitución literal en un fichero, ejecuta pytest en Docker y
restaura el fichero siempre, también si se interrumpe. Es la herramienta de la
regla 1 de docs/ai-guidelines/testing-guidelines.md.

    python3 scripts/en_rojo.py FICHERO BUSCAR REEMPLAZO [-- ARGS_PYTEST...]

    python3 scripts/en_rojo.py ilovevoley/competitions/services/notifications.py \\
        "if not match.stream_url or not match.is_live_window:" \\
        "if not match.stream_url:" \\
        -- ilovevoley/competitions/tests/test_live_stream_push.py

BUSCAR y REEMPLAZO son literales y BUSCAR debe aparecer una sola vez. Para
varias líneas, pasa saltos reales: $'linea 1\\n    linea 2' en zsh o bash.
Sin ARGS_PYTEST se ejecuta la carpeta tests/ más cercana al fichero; para ir
rápido, pasa solo los tests que tocan el código mutado (nodeid o -k).
pytest para en el primer fallo (-x).

Lote: muchas mutaciones con un solo arranque de Django.

    python3 scripts/en_rojo.py --lote mutaciones.jsonl [--reanudar] [--timeout S]
                                                 [--solo-etapa-1]

Una mutación por línea: {"fichero": ..., "buscar": ..., "reemplazo": ...,
"tests": [...]}. Si el módulo mutado no lo carga django.setup() (vistas,
servicios, serializers), la mutación cuesta lo que sus tests; si lo carga
(modelos, señales), paga un arranque propio.

Cada resultado se imprime al terminar y se anota en MUTACIONES.jsonl.resultados.jsonl;
con --reanudar se saltan las mutaciones que ya tienen resultado ahí (por su
posición en el fichero: no reordenes ni borres líneas entre ejecuciones).
Cada mutación tiene un tope de --timeout segundos (900 por defecto): si lo
supera (un bucle infinito, por ejemplo) sale NO VÁLIDA y el lote sigue.

Etapa 1 automática: si "tests" lleva carpetas (y como mucho opciones
--deselect), primero se ejecutan solo los ficheros de esas carpetas que citan
el nombre del módulo mutado. Si ahí sale rojo, ya es el veredicto (un test que
queda la detecta) y se ahorra recolectar y ejecutar la carpeta entera; si sale
verde, se ejecuta la carpeta completa. No se usa si más de la mitad de los
ficheros citan el nombre (módulos genéricos como `views` o `base`).
Con --solo-etapa-1 se ejecuta únicamente esa etapa: las mutaciones que no salen
rojas ahí se anotan como VERDE con etapa «solo etapa 1» (pendientes de la
carpeta completa, no son un verde real) para decidir cuáles merece la pena
pagar.

Usa `docker compose -f docker-compose.dev.yml run --rm web`: el contenedor monta
el repo en /app, así que ve la mutación escrita en el host.

Salida: 0 si la mutación se detecta (rojo; en lote, todas), 1 si sobrevive
(verde; en lote, alguna), 2 si no es válida (BUSCAR no aparece una sola vez, o
pytest no llega a ejecutar los tests: error de colección, sintaxis).
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
OPCIONES_PYTEST = ["-q", "-p", "no:randomly", "-p", "no:cacheprovider", "-x"]
# Repetir opciones fijadas cambia la salida (-q -q oculta el resumen final).
YA_FIJADAS = {"-q", "-x"}
MARCA = "EN_ROJO "
TIMEOUT_POR_DEFECTO = 900
# Fuera de lo que dan pytest y las señales (SIGKILL ya es -9).
HUBO_TIMEOUT = -1000
ROJO, VERDE, NO_VALIDA = 0, 1, 2
VEREDICTOS = {
    ROJO: "ROJO: la mutación se detecta.",
    VERDE: "VERDE: la mutación sobrevive; ningún test la detecta.",
    NO_VALIDA: "MUTACIÓN NO VÁLIDA",
}


def _decir(*partes: object) -> None:
    sys.stdout.write(" ".join(map(str, partes)) + "\n")
    sys.stdout.flush()


DOCKER = [
    "docker",
    "compose",
    "-f",
    "docker-compose.dev.yml",
    "run",
    "--rm",
    "-T",
    "web",
]


def _tests_por_defecto(fichero: Path) -> str:
    for carpeta in [fichero.parent, *fichero.parents]:
        if (carpeta / "tests").is_dir():
            return str((carpeta / "tests").relative_to(RAIZ))
        if carpeta == RAIZ:
            break
    sys.exit(f"No encuentro una carpeta tests/ para {fichero}; pasa -- ARGS_PYTEST")


def _tests(fichero: Path, args: list[str]) -> list[str]:
    return [a for a in args if a not in YA_FIJADAS] or [_tests_por_defecto(fichero)]


def _veredicto(codigo: int) -> int:
    # pytest: 1 = algún test falla, 0 = todos pasan; el resto (colección,
    # uso, interrupción) no dice nada de la mutación.
    return {1: ROJO, 0: VERDE}.get(codigo, NO_VALIDA)


def _resumen(salida: str) -> list[str]:
    return [
        linea
        for linea in salida.splitlines()
        if linea.startswith(("FAILED", "SUBFAIL", "ERROR"))
        or " passed" in linea
        or " failed" in linea
    ]


def _restaurar_al_salir() -> None:
    # SIGTERM pasa por los finally igual que Ctrl+C.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(130))


def una(posicionales: list[str], args_pytest: list[str]) -> int:
    fichero = (RAIZ / posicionales[0]).resolve()
    buscar, reemplazo = posicionales[1], posicionales[2]
    original = fichero.read_text(encoding="utf-8")
    apariciones = original.count(buscar)
    if apariciones != 1:
        _decir(f"BUSCAR aparece {apariciones} veces en {fichero}; debe ser 1.")
        return NO_VALIDA

    tests = _tests(fichero, args_pytest)
    _restaurar_al_salir()
    try:
        fichero.write_text(original.replace(buscar, reemplazo), encoding="utf-8")
        resultado = subprocess.run(
            [*DOCKER, "python", "-m", "pytest", *OPCIONES_PYTEST, *tests],
            cwd=RAIZ,
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        fichero.write_text(original, encoding="utf-8")

    salida = resultado.stdout + resultado.stderr
    veredicto = _veredicto(resultado.returncode)
    _decir("\n".join(_resumen(salida)) or salida[-3000:])
    if veredicto == NO_VALIDA:
        _decir(f"{VEREDICTOS[NO_VALIDA]}: pytest salió con {resultado.returncode}.")
        _decir(salida[-3000:])
    else:
        _decir(VEREDICTOS[veredicto])
    return veredicto


def _etapa_1(fichero: Path, tests: list[str]) -> list[str]:
    """Ficheros de test de las carpetas de `tests` que citan el módulo mutado.

    Vacío si no aplica: `tests` lleva algo que no son carpetas ni --deselect, o
    más de la mitad de los ficheros citan el nombre (módulo genérico).
    """
    deselects = [t for t in tests if t.startswith("--deselect")]
    carpetas = [RAIZ / t for t in tests if t not in deselects]
    if not carpetas or not all(c.is_dir() for c in carpetas):
        return []
    patron = re.compile(rf"\b{re.escape(fichero.stem)}\b")
    citan: list[str] = []
    todos = 0
    for carpeta in carpetas:
        for f in sorted(carpeta.rglob("test*.py")):
            todos += 1
            if patron.search(f.read_text(encoding="utf-8", errors="ignore")):
                citan.append(str(f.relative_to(RAIZ)))
    if not citan or len(citan) * 2 > todos:
        return []
    return [*citan, *deselects]


def lote(
    ruta: str,
    reanudar: bool = False,
    timeout: int = TIMEOUT_POR_DEFECTO,
    solo_etapa_1: bool = False,
) -> int:
    mutaciones = [
        json.loads(linea)
        for linea in Path(ruta).read_text(encoding="utf-8").splitlines()
        if linea.strip()
    ]
    anotados = Path(ruta + ".resultados.jsonl")
    resultados: dict[int, dict] = {}
    if reanudar and anotados.exists():
        for linea in anotados.read_text(encoding="utf-8").splitlines():
            if linea.strip():
                r = json.loads(linea)
                resultados[r["i"]] = r
        if not solo_etapa_1:
            # Las «solo etapa 1» siguen pendientes de la carpeta completa.
            resultados = {
                i: r
                for i, r in resultados.items()
                if not r.get("etapa", "").startswith("solo etapa 1")
            }
    else:
        anotados.write_text("", encoding="utf-8")

    def corto(texto: str) -> str:
        lineas = texto.strip().splitlines()
        return repr(lineas[0][:60] if lineas else "")

    nombres = {ROJO: "ROJO", VERDE: "VERDE", NO_VALIDA: "NO VÁLIDA"}

    def registrar(r: dict) -> None:
        # Se imprime y se anota al terminar cada mutación, no al final del lote.
        resultados[r["i"]] = r
        with anotados.open("a", encoding="utf-8") as f:
            f.write(json.dumps(r) + "\n")
        m = mutaciones[r["i"]]
        etapa = f" [{r['etapa']}]" if r.get("etapa") else ""
        _decir(
            f"{nombres[r['veredicto']]:9} #{r['i'] + 1} {m['fichero']}: "
            f"{corto(m['buscar'])} → {corto(m['reemplazo'])}{etapa}"
        )
        if r.get("detalle"):
            _decir("          " + r["detalle"].replace("\n", "\n          "))

    originales: dict[Path, str] = {}
    validas = []
    for i, m in enumerate(mutaciones):
        fichero = (RAIZ / m["fichero"]).resolve()
        texto = originales.setdefault(fichero, fichero.read_text(encoding="utf-8"))
        if i in resultados:
            continue
        apariciones = texto.count(m["buscar"])
        if apariciones != 1:
            registrar(
                {
                    "i": i,
                    "veredicto": NO_VALIDA,
                    "detalle": f"BUSCAR aparece {apariciones} veces",
                }
            )
            continue
        m["tests"] = _tests(fichero, m.get("tests", []))
        m["primero"] = _etapa_1(fichero, m["tests"])
        m["timeout"] = timeout
        m["solo_etapa_1"] = solo_etapa_1
        m["i"] = i
        validas.append(m)

    cola = ""
    if validas:
        _restaurar_al_salir()
        proceso = subprocess.Popen(
            [*DOCKER, "python", "scripts/en_rojo.py", "--dentro"],
            cwd=RAIZ,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            if proceso.stdin is None or proceso.stdout is None:
                return NO_VALIDA
            proceso.stdin.write("\n".join(json.dumps(m) for m in validas))
            proceso.stdin.close()
            for linea in proceso.stdout:
                if linea.startswith(MARCA):
                    registrar(json.loads(linea.removeprefix(MARCA)))
                else:
                    cola = (cola + linea)[-3000:]
            proceso.wait()
        finally:
            if proceso.poll() is None:
                proceso.terminate()
            # Red de seguridad: el proceso de dentro restaura cada mutación, pero
            # un contenedor matado a mitad no llega a hacerlo.
            for fichero, texto in originales.items():
                if fichero.read_text(encoding="utf-8") != texto:
                    fichero.write_text(texto, encoding="utf-8")

    if len(resultados) < len(mutaciones):
        _decir(cola)
        _decir("El lote no terminó: faltan mutaciones por resultado.")
        return NO_VALIDA
    cuenta = dict.fromkeys(nombres, 0)
    for r in resultados.values():
        cuenta[r["veredicto"]] += 1
    _decir(
        f"Resumen: {cuenta[ROJO]} rojas, {cuenta[VERDE]} verdes, "
        f"{cuenta[NO_VALIDA]} no válidas."
    )
    return max(r["veredicto"] for r in resultados.values()) if resultados else ROJO


def _modulo(fichero: Path) -> str:
    return ".".join(fichero.relative_to(RAIZ).with_suffix("").parts)


def _pytest_en_hijo(tests: list[str], timeout: int) -> tuple[int, str]:
    """pytest en un fork del proceso con Django ya cargado."""
    with tempfile.TemporaryFile(mode="w+") as salida:
        pid = os.fork()
        if pid == 0:
            os.dup2(salida.fileno(), 1)
            os.dup2(salida.fileno(), 2)
            import pytest

            codigo = 3
            try:
                codigo = int(pytest.main([*OPCIONES_PYTEST, *tests]))
            finally:
                sys.stdout.flush()
                sys.stderr.flush()
                os._exit(codigo)
        limite = time.monotonic() + timeout
        while True:
            terminado, estado = os.waitpid(pid, os.WNOHANG)
            if terminado:
                break
            if time.monotonic() > limite:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
                return HUBO_TIMEOUT, ""
            time.sleep(0.1)
        salida.seek(0)
        return os.waitstatus_to_exitcode(estado), salida.read()


def _correr(fichero: Path, tests: list[str], timeout: int) -> tuple[int, str]:
    if _modulo(fichero) in sys.modules:
        # Ya cargado por django.setup(): el fork vería el original.
        try:
            r = subprocess.run(
                [sys.executable, "-m", "pytest", *OPCIONES_PYTEST, *tests],
                cwd=RAIZ,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return HUBO_TIMEOUT, ""
        return r.returncode, r.stdout + r.stderr
    return _pytest_en_hijo(tests, timeout)


def dentro() -> int:
    """Ejecuta el lote dentro del contenedor; un resultado por línea."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_test")
    sys.path.insert(0, str(RAIZ))
    import django

    django.setup()
    for linea in sys.stdin.read().splitlines():
        m = json.loads(linea)
        fichero = (RAIZ / m["fichero"]).resolve()
        original = fichero.read_text(encoding="utf-8")
        try:
            fichero.write_text(
                original.replace(m["buscar"], m["reemplazo"]), encoding="utf-8"
            )
            timeout = m.get("timeout", TIMEOUT_POR_DEFECTO)
            etapa = ""
            codigo, salida = 0, ""
            if m.get("primero"):
                codigo, salida = _correr(fichero, m["primero"], timeout)
                etapa = "etapa 1: tests que citan el módulo"
            if codigo != 1:
                if m.get("solo_etapa_1"):
                    # Pendiente de la carpeta completa: se anota como verde.
                    etapa = "solo etapa 1: falta la carpeta completa"
                    codigo = 0
                else:
                    etapa = ""
                    codigo, salida = _correr(fichero, m["tests"], timeout)
        finally:
            fichero.write_text(original, encoding="utf-8")
        veredicto = _veredicto(codigo)
        detalle = "\n".join(
            linea
            for linea in _resumen(salida)
            if linea.startswith(("FAILED", "SUBFAIL"))
        )
        if codigo == HUBO_TIMEOUT:
            detalle = f"tiempo agotado tras {timeout} s (¿bucle infinito?)"
        elif veredicto == NO_VALIDA:
            detalle = f"pytest salió con {codigo}\n" + salida[-1500:]
        _decir(
            MARCA
            + json.dumps(
                {
                    "i": m["i"],
                    "veredicto": veredicto,
                    "detalle": detalle,
                    "etapa": etapa,
                }
            )
        )
    return 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["--dentro"]:
        return dentro()
    if argv[:1] == ["--lote"] and len(argv) >= 2:
        opciones = argv[2:]
        timeout = TIMEOUT_POR_DEFECTO
        if "--timeout" in opciones:
            timeout = int(opciones[opciones.index("--timeout") + 1])
        return lote(
            argv[1],
            reanudar="--reanudar" in opciones,
            timeout=timeout,
            solo_etapa_1="--solo-etapa-1" in opciones,
        )
    if "--" in argv:
        corte = argv.index("--")
        posicionales, args_pytest = argv[:corte], argv[corte + 1 :]
    else:
        posicionales, args_pytest = argv, []
    if len(posicionales) != 3:
        sys.stderr.write(__doc__ or "")
        return NO_VALIDA
    return una(posicionales, args_pytest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
