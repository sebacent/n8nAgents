#!/usr/bin/env python3
"""Importa estados de cuenta de distintas fuentes a un CSV canónico.

Cada fuente (banco, tarjeta, archivo manual) tiene su propio adaptador. Todos
devuelven un DataFrame con el formato canónico que consume ``resumen_gastos.py``:

    fecha, descripcion, categoria, monto, tipo, fuente, id_doc

Flujo:
  1) El adaptador parsea el archivo crudo y produce filas sin clasificar.
  2) Se aplica un YAML de reglas (``categorias.yml`` por defecto) para asignar
     ``categoria`` (y opcionalmente forzar ``tipo``) según patrones en la
     descripción. Lo no matcheado queda como ``Sin clasificar``.
  3) Si se usa ``--append`` y el destino existe, se descartan duplicados por
     la tupla (fecha, monto, id_doc, fuente).

Uso:
    python importar_estado.py --fuente brou --entrada estado_mayo.xlsx \
        --salida gastos.csv [--append] [--reglas categorias.yml]
"""

from __future__ import annotations

import argparse
import os
import sys
import unicodedata
from typing import Callable

import pandas as pd
import yaml

# Columnas del formato canónico, en orden.
COLUMNAS_CANONICAS = [
    "fecha",
    "descripcion",
    "categoria",
    "monto",
    "tipo",
    "fuente",
    "id_doc",
]


class ErrorImportacion(Exception):
    """Error de negocio del importador con mensaje claro para el usuario."""


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def _parsear_monto_europeo(valor) -> float | None:
    """Convierte ``'43.007,09'`` (formato europeo) a ``43007.09``.

    Acepta también números nativos y devuelve ``None`` para vacíos/inválidos.
    """
    if pd.isna(valor):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip()
    if not texto:
        return None
    # Punto = separador de miles, coma = decimal.
    normalizado = texto.replace(".", "").replace(",", ".")
    try:
        return float(normalizado)
    except ValueError:
        return None


def _normalizar_nombre_columna(nombre: str) -> str:
    """Quita acentos, pasa a minúsculas y reemplaza espacios por '_'."""
    sin_acentos = (
        unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()
    )
    return sin_acentos.strip().lower().replace(" ", "_")


# ---------------------------------------------------------------------------
# Adaptadores por fuente
# ---------------------------------------------------------------------------
def adaptador_manual(ruta: str) -> pd.DataFrame:
    """Lee un CSV ya en el formato canónico (útil para anexar a mano)."""
    if not os.path.isfile(ruta):
        raise ErrorImportacion(f"No se encontró el archivo: '{ruta}'.")
    try:
        df = pd.read_csv(ruta)
    except pd.errors.EmptyDataError:
        raise ErrorImportacion(f"El archivo '{ruta}' está vacío.")
    df.columns = [c.strip().lower() for c in df.columns]
    requeridas = ["fecha", "descripcion", "monto"]
    faltantes = [c for c in requeridas if c not in df.columns]
    if faltantes:
        raise ErrorImportacion(
            f"Faltan columnas requeridas en '{ruta}': {', '.join(faltantes)}."
        )
    # Completar columnas opcionales con sus defaults.
    if "categoria" not in df.columns:
        df["categoria"] = ""
    if "tipo" not in df.columns:
        df["tipo"] = "gasto"
    if "fuente" not in df.columns:
        df["fuente"] = "manual"
    if "id_doc" not in df.columns:
        df["id_doc"] = ""
    return df[COLUMNAS_CANONICAS].copy()


def adaptador_brou(ruta: str) -> pd.DataFrame:
    """Parser para estados de cuenta de BROU (Uruguay) en formato Excel.

    NOTA: Adaptador best-effort basado en una captura. Asunciones a validar
    contra un .xlsx real:
      * La tabla 'Movimientos' arranca en una fila cuya primera celda dice
        'Fecha' (puede haber muchas filas de encabezado/saldos antes).
      * Columnas (en orden): Fecha, Descripción, Número de documento, Asunto,
        Dependencia, Débito, Crédito.
      * La tabla termina en la primera fila donde 'Fecha' está vacía.
      * Las fechas son datetime nativos de Excel (no strings).
      * Montos pueden venir como número o como string en formato europeo.
    """
    if not os.path.isfile(ruta):
        raise ErrorImportacion(f"No se encontró el archivo: '{ruta}'.")

    # Leer todo sin asumir encabezados para ubicar la tabla.
    df_crudo = pd.read_excel(ruta, header=None, dtype=object)
    fila_header = _localizar_header_brou(df_crudo)
    if fila_header is None:
        raise ErrorImportacion(
            f"No se encontró la tabla 'Movimientos' en '{ruta}'. "
            "El layout puede haber cambiado; revisar adaptador BROU."
        )

    df = pd.read_excel(ruta, header=fila_header, dtype=object)
    df.columns = [_normalizar_nombre_columna(str(c)) for c in df.columns]

    columnas_esperadas = {"fecha", "descripcion", "debito", "credito"}
    faltantes = columnas_esperadas - set(df.columns)
    if faltantes:
        raise ErrorImportacion(
            f"Faltan columnas esperadas en el estado BROU: {', '.join(sorted(faltantes))}. "
            f"Columnas encontradas: {', '.join(df.columns)}."
        )

    # Cortar en la primera fila con fecha vacía (fin de la tabla).
    fecha_serie = df["fecha"]
    if fecha_serie.isna().any():
        df = df.iloc[: fecha_serie.isna().idxmax()].copy()

    debito = pd.Series(
        [_parsear_monto_europeo(v) for v in df["debito"]], index=df.index
    ).fillna(0.0)
    credito = pd.Series(
        [_parsear_monto_europeo(v) for v in df["credito"]], index=df.index
    ).fillna(0.0)

    descripcion = (
        df["descripcion"].astype("string")
        .str.replace(r"^\s*Comercio:\s*", "", regex=True)
        .str.strip()
    )

    es_debito = debito > 0
    es_credito = credito > 0
    monto = debito.where(es_debito, credito)
    tipo = pd.Series("gasto", index=df.index).where(es_debito, "ingreso")

    id_doc_col = (
        df["numero_de_documento"] if "numero_de_documento" in df.columns
        else pd.Series("", index=df.index)
    )

    resultado = pd.DataFrame(
        {
            "fecha": pd.to_datetime(df["fecha"], errors="coerce"),
            "descripcion": descripcion,
            "categoria": "",
            "monto": monto,
            "tipo": tipo,
            "fuente": "brou",
            "id_doc": id_doc_col.astype("string").fillna(""),
        }
    )
    # Descartar filas sin movimiento (débito y crédito ambos cero).
    return resultado[es_debito | es_credito].reset_index(drop=True)


def _localizar_header_brou(df_crudo: pd.DataFrame) -> int | None:
    """Busca la fila donde arranca el header de la tabla 'Movimientos'."""
    for i, fila in df_crudo.iterrows():
        celda = fila.iloc[0]
        if isinstance(celda, str) and celda.strip().lower() == "fecha":
            return int(i)
    return None


# Registry de adaptadores. Agregar acá nuevos bancos/tarjetas.
ADAPTADORES: dict[str, Callable[[str], pd.DataFrame]] = {
    "brou": adaptador_brou,
    "manual": adaptador_manual,
}


# ---------------------------------------------------------------------------
# Reglas de clasificación
# ---------------------------------------------------------------------------
class Regla:
    """Patrón que asigna una categoría (y opcionalmente fuerza un tipo)."""

    def __init__(self, categoria: str, patrones: list[str], tipo: str | None = None):
        self.categoria = categoria
        self.patrones = [str(p).lower() for p in patrones]
        self.tipo = tipo

    def matchea(self, descripcion: str) -> bool:
        desc = descripcion.lower()
        return any(p in desc for p in self.patrones)


def cargar_reglas(ruta: str) -> list[Regla]:
    """Lee un YAML de reglas. Formato documentado en categorias.yml."""
    if not os.path.isfile(ruta):
        raise ErrorImportacion(f"No se encontró el archivo de reglas: '{ruta}'.")
    with open(ruta, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    reglas: list[Regla] = []
    for categoria, valor in data.items():
        if isinstance(valor, list):
            reglas.append(Regla(categoria, valor))
        elif isinstance(valor, dict):
            patrones = valor.get("patrones", [])
            tipo = valor.get("tipo")
            if tipo is not None and tipo not in {"gasto", "ingreso"}:
                raise ErrorImportacion(
                    f"Tipo inválido '{tipo}' para la categoría '{categoria}'."
                )
            reglas.append(Regla(categoria, patrones, tipo))
        else:
            raise ErrorImportacion(
                f"Formato inválido para la categoría '{categoria}' en '{ruta}'."
            )
    return reglas


def clasificar(df: pd.DataFrame, reglas: list[Regla]) -> pd.DataFrame:
    """Aplica reglas a cada fila. Respeta categorías ya asignadas (no vacías)."""
    df = df.copy()
    if "categoria" not in df.columns:
        df["categoria"] = ""

    for idx in df.index:
        actual = df.at[idx, "categoria"]
        if pd.notna(actual) and str(actual).strip():
            continue  # ya tenía categoría asignada manualmente, respetar.

        desc = str(df.at[idx, "descripcion"])
        for regla in reglas:
            if regla.matchea(desc):
                df.at[idx, "categoria"] = regla.categoria
                if regla.tipo:
                    df.at[idx, "tipo"] = regla.tipo
                break
        else:
            df.at[idx, "categoria"] = "Sin clasificar"
    return df


# ---------------------------------------------------------------------------
# Deduplicación al anexar
# ---------------------------------------------------------------------------
def deduplicar(
    df_nuevo: pd.DataFrame, df_existente: pd.DataFrame
) -> tuple[pd.DataFrame, int]:
    """Quita filas de ``df_nuevo`` cuya clave ya esté en ``df_existente``."""
    if df_existente.empty:
        return df_nuevo.reset_index(drop=True), 0

    clave = ["fecha", "monto", "id_doc", "fuente"]
    existente_keys = set(
        map(tuple, df_existente[clave].astype(str).values)
    )
    es_dup = df_nuevo[clave].astype(str).apply(tuple, axis=1).isin(existente_keys)
    n_omitidos = int(es_dup.sum())
    return df_nuevo[~es_dup].reset_index(drop=True), n_omitidos


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------
def parsear_argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Importa un estado de cuenta a un CSV canónico de gastos. "
            "Aplica reglas de clasificación y deduplica al anexar."
        )
    )
    parser.add_argument(
        "--fuente",
        required=True,
        choices=sorted(ADAPTADORES),
        help="Identificador del adaptador a usar.",
    )
    parser.add_argument(
        "--entrada", required=True, help="Ruta del archivo del banco/tarjeta."
    )
    parser.add_argument(
        "--salida",
        default="gastos.csv",
        help="CSV canónico de salida (default: gastos.csv).",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Si la salida existe, anexa en lugar de sobrescribir (con dedupe).",
    )
    parser.add_argument(
        "--reglas",
        default=None,
        help="YAML de reglas. Default: categorias.yml junto al script.",
    )
    return parser.parse_args()


def main() -> None:
    args = parsear_argumentos()
    try:
        adaptador = ADAPTADORES[args.fuente]
        df = adaptador(args.entrada)

        ruta_reglas = args.reglas or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "categorias.yml"
        )
        if os.path.isfile(ruta_reglas):
            reglas = cargar_reglas(ruta_reglas)
            df = clasificar(df, reglas)
        else:
            print(
                f"Aviso: no se encontró '{ruta_reglas}'; las filas sin categoría "
                "quedan como 'Sin clasificar'.",
                file=sys.stderr,
            )
            df.loc[df["categoria"].fillna("").eq(""), "categoria"] = "Sin clasificar"

        n_omitidos = 0
        if args.append and os.path.isfile(args.salida):
            df_existente = pd.read_csv(args.salida)
            df, n_omitidos = deduplicar(df, df_existente)
            df_final = pd.concat([df_existente, df], ignore_index=True)
        else:
            df_final = df

        df_final[COLUMNAS_CANONICAS].to_csv(args.salida, index=False)
    except ErrorImportacion as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    sin_clasificar = int((df["categoria"] == "Sin clasificar").sum())
    print(f"Listo. {len(df)} filas nuevas escritas en '{args.salida}'.")
    if n_omitidos:
        print(f"  {n_omitidos} filas omitidas por duplicado.")
    if sin_clasificar:
        print(
            f"  {sin_clasificar} filas quedaron 'Sin clasificar' "
            "(agregar patrones a categorias.yml para clasificarlas)."
        )


if __name__ == "__main__":
    main()
