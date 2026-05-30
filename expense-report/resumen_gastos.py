#!/usr/bin/env python3
"""Genera un resumen en Excel a partir de un CSV de gastos personales.

El script lee un CSV con las columnas ``fecha,descripcion,categoria,monto``,
limpia y valida los datos, agrupa los gastos por mes y categoría y produce un
archivo Excel (``resumen_gastos.xlsx`` por defecto) con:

  * una hoja de detalle con los datos ya procesados,
  * una hoja de resumen mensual (tabla dinámica mes x categoría + totales),
  * una hoja con tres gráficos: distribución por categoría, comparativo de
    gastos entre meses y barras apiladas de categoría por mes.

Uso:
    python resumen_gastos.py --entrada gastos.csv --salida resumen_gastos.xlsx
"""

from __future__ import annotations

import argparse
import os
import sys
from io import BytesIO

import matplotlib

# Backend no interactivo: el script debe funcionar en servidores sin pantalla.
matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402  (debe ir tras matplotlib.use)
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from openpyxl.drawing.image import Image as ImagenExcel  # noqa: E402

# Columnas que el CSV debe contener obligatoriamente (en minúsculas).
COLUMNAS_REQUERIDAS = ["fecha", "descripcion", "categoria", "monto"]


class ErrorDatosGastos(Exception):
    """Error de negocio con un mensaje claro para el usuario final."""


# ---------------------------------------------------------------------------
# Carga y validación
# ---------------------------------------------------------------------------
def cargar_csv(ruta: str) -> pd.DataFrame:
    """Lee el CSV de ``ruta`` y devuelve un DataFrame.

    Normaliza los nombres de columna (minúsculas y sin espacios) y traduce los
    errores técnicos a mensajes comprensibles.
    """
    if not os.path.isfile(ruta):
        raise ErrorDatosGastos(f"No se encontró el archivo CSV: '{ruta}'.")

    try:
        df = pd.read_csv(ruta)
    except pd.errors.EmptyDataError:
        raise ErrorDatosGastos(f"El archivo '{ruta}' está vacío.")
    except pd.errors.ParserError as exc:
        raise ErrorDatosGastos(f"No se pudo interpretar el CSV '{ruta}': {exc}")
    except UnicodeDecodeError as exc:
        raise ErrorDatosGastos(
            f"Problema de codificación al leer '{ruta}'. "
            f"Guarda el archivo en UTF-8. Detalle: {exc}"
        )

    # Homogeneizar los nombres de columna para el resto del flujo.
    df.columns = [str(c).strip().lower() for c in df.columns]

    if df.empty:
        raise ErrorDatosGastos(f"El archivo '{ruta}' no contiene filas de datos.")

    return df


def validar_columnas(df: pd.DataFrame) -> None:
    """Verifica que estén todas las columnas requeridas; si no, aborta."""
    faltantes = [c for c in COLUMNAS_REQUERIDAS if c not in df.columns]
    if faltantes:
        raise ErrorDatosGastos(
            f"Faltan columnas requeridas en el CSV: {', '.join(faltantes)}. "
            f"Se esperaban: {', '.join(COLUMNAS_REQUERIDAS)}."
        )


# ---------------------------------------------------------------------------
# Limpieza de datos
# ---------------------------------------------------------------------------
def limpiar_datos(df: pd.DataFrame) -> pd.DataFrame:
    """Convierte tipos, descarta filas inválidas y añade la columna ``mes``.

    Las fechas no parseables y los montos no numéricos se convierten a valores
    nulos; toda fila con fecha inválida, monto inválido o categoría vacía se
    reporta (con su número de línea en el CSV) y se descarta. Si tras la
    limpieza no queda ninguna fila válida, se aborta.
    """
    df = df.copy()

    # Normalizar texto antes de validar.
    for col in ("descripcion", "categoria"):
        df[col] = df[col].astype("string").str.strip()

    # Conversión tolerante a errores: lo no convertible queda como nulo.
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df["monto"] = pd.to_numeric(df["monto"], errors="coerce")

    # Detectar el motivo de invalidez de cada fila.
    motivos: dict[int, list[str]] = {}
    for idx in df.index:
        razones: list[str] = []
        if pd.isna(df.at[idx, "fecha"]):
            razones.append("fecha inválida")
        if pd.isna(df.at[idx, "monto"]):
            razones.append("monto no numérico")
        categoria = df.at[idx, "categoria"]
        if pd.isna(categoria) or categoria == "":
            razones.append("categoría vacía")
        if razones:
            motivos[idx] = razones

    # Avisar de cada fila descartada. El +2 mapea el índice 0-based a la línea
    # del CSV (1 por el encabezado + 1 por el inicio en 0).
    for idx in sorted(motivos):
        print(
            f"  Advertencia: fila {idx + 2} descartada "
            f"({', '.join(motivos[idx])}).",
            file=sys.stderr,
        )

    df_valido = df.drop(index=list(motivos)).copy()
    if df_valido.empty:
        raise ErrorDatosGastos(
            "No quedaron filas válidas tras la limpieza; revisa los datos de entrada."
        )

    # Descripción vacía es aceptable: se completa para evitar nulos en la hoja.
    df_valido["descripcion"] = df_valido["descripcion"].fillna("")
    # Etiqueta de periodo "YYYY-MM" usada para agrupar.
    df_valido["mes"] = df_valido["fecha"].dt.strftime("%Y-%m")

    columnas = ["fecha", "descripcion", "categoria", "monto", "mes"]
    return df_valido.sort_values("fecha")[columnas].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Agregaciones
# ---------------------------------------------------------------------------
def agrupar_por_mes_categoria(df: pd.DataFrame) -> pd.DataFrame:
    """Tabla dinámica mes x categoría (suma) con totales por fila y columna."""
    pivot = pd.pivot_table(
        df,
        index="mes",
        columns="categoria",
        values="monto",
        aggfunc="sum",
        fill_value=0,
    )

    # Añadir totales sin contar dos veces la columna "Total".
    resultado = pivot.copy()
    resultado["Total"] = pivot.sum(axis=1)
    fila_total = pivot.sum(axis=0)
    fila_total["Total"] = float(pivot.to_numpy().sum())
    resultado.loc["Total"] = fila_total
    return resultado


def resumen_mensual(df: pd.DataFrame) -> pd.DataFrame:
    """Total gastado y cantidad de movimientos por mes."""
    resumen = (
        df.groupby("mes")["monto"].agg(total="sum", cantidad="count").reset_index()
    )
    return resumen


# ---------------------------------------------------------------------------
# Gráficos (matplotlib -> PNG en memoria)
# ---------------------------------------------------------------------------
def _figura_a_imagen(fig) -> BytesIO:
    """Renderiza una figura de matplotlib a un PNG en memoria y la cierra."""
    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    buffer.seek(0)
    return buffer


def grafico_distribucion_categorias(df: pd.DataFrame) -> BytesIO:
    """Gráfico de pastel con el peso de cada categoría sobre el gasto total."""
    por_categoria = df.groupby("categoria")["monto"].sum().sort_values(ascending=False)

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.pie(
        por_categoria.to_numpy(),
        labels=list(por_categoria.index),
        autopct="%1.1f%%",
        startangle=90,
    )
    ax.axis("equal")
    ax.set_title("Distribución de gastos por categoría")
    return _figura_a_imagen(fig)


def grafico_comparativo_meses(df: pd.DataFrame) -> BytesIO:
    """Gráfico de barras con el gasto total de cada mes."""
    por_mes = df.groupby("mes")["monto"].sum()

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(por_mes.index, por_mes.to_numpy(), color="#4C72B0")
    ax.set_title("Comparativo de gastos por mes")
    ax.set_xlabel("Mes")
    ax.set_ylabel("Monto total")
    ax.tick_params(axis="x", rotation=45)
    for i, valor in enumerate(por_mes.to_numpy()):
        ax.text(i, valor, f"{valor:,.0f}", ha="center", va="bottom", fontsize=8)
    return _figura_a_imagen(fig)


def grafico_apilado_categoria_mes(df: pd.DataFrame) -> BytesIO:
    """Barras apiladas: aporte de cada categoría dentro de cada mes."""
    pivot = pd.pivot_table(
        df,
        index="mes",
        columns="categoria",
        values="monto",
        aggfunc="sum",
        fill_value=0,
    )

    fig, ax = plt.subplots(figsize=(9, 5))
    acumulado = np.zeros(len(pivot))
    for categoria in pivot.columns:
        valores = pivot[categoria].to_numpy()
        ax.bar(pivot.index, valores, bottom=acumulado, label=str(categoria))
        acumulado += valores

    ax.set_title("Gastos por categoría y mes")
    ax.set_xlabel("Mes")
    ax.set_ylabel("Monto total")
    ax.tick_params(axis="x", rotation=45)
    ax.legend(title="Categoría", bbox_to_anchor=(1.02, 1), loc="upper left")
    return _figura_a_imagen(fig)


# ---------------------------------------------------------------------------
# Escritura del Excel
# ---------------------------------------------------------------------------
def _autoajustar_columnas(hoja, dataframe: pd.DataFrame, offset: int = 0) -> None:
    """Ajusta el ancho de columna al contenido más largo (con un tope)."""
    for posicion, columna in enumerate(dataframe.columns, start=1 + offset):
        valores = dataframe[columna].astype(str)
        ancho = max([len(str(columna)), *(len(v) for v in valores)]) + 2
        hoja.column_dimensions[hoja.cell(row=1, column=posicion).column_letter].width = (
            min(ancho, 40)
        )


def escribir_excel(
    detalle: pd.DataFrame,
    pivot: pd.DataFrame,
    resumen_mes: pd.DataFrame,
    graficos: list[tuple[str, BytesIO]],
    ruta_salida: str,
) -> None:
    """Escribe las hojas de datos y embebe los gráficos en el Excel."""
    # Copia para mostrar la fecha sin componente horario.
    detalle_export = detalle.copy()
    detalle_export["fecha"] = detalle_export["fecha"].dt.date

    with pd.ExcelWriter(ruta_salida, engine="openpyxl") as writer:
        # Hoja 1: detalle procesado.
        detalle_export.to_excel(writer, sheet_name="Detalle", index=False)
        _autoajustar_columnas(writer.sheets["Detalle"], detalle_export)

        # Hoja 2: resumen mensual (pivote + tabla de totales por mes).
        pivot.to_excel(writer, sheet_name="Resumen Mensual")
        inicio_resumen = len(pivot) + 3
        resumen_mes.to_excel(
            writer,
            sheet_name="Resumen Mensual",
            startrow=inicio_resumen,
            index=False,
        )

        # Hoja 3: gráficos embebidos uno debajo de otro.
        libro = writer.book
        hoja_graficos = libro.create_sheet("Gráficos")
        fila = 1
        for titulo, imagen in graficos:
            hoja_graficos.cell(row=fila, column=1, value=titulo)
            hoja_graficos.add_image(ImagenExcel(imagen), f"A{fila + 1}")
            fila += 26  # espacio suficiente para no solapar las imágenes


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------
def parsear_argumentos() -> argparse.Namespace:
    """Define y parsea los argumentos de línea de comandos."""
    parser = argparse.ArgumentParser(
        description="Genera un resumen en Excel de gastos personales a partir de un CSV."
    )
    parser.add_argument(
        "--entrada",
        default="gastos.csv",
        help="Ruta del CSV de entrada (por defecto: gastos.csv).",
    )
    parser.add_argument(
        "--salida",
        default="resumen_gastos.xlsx",
        help="Ruta del Excel de salida (por defecto: resumen_gastos.xlsx).",
    )
    return parser.parse_args()


def main() -> None:
    """Orquesta el flujo completo: cargar, validar, procesar y exportar."""
    args = parsear_argumentos()
    try:
        df_crudo = cargar_csv(args.entrada)
        validar_columnas(df_crudo)
        df = limpiar_datos(df_crudo)

        pivot = agrupar_por_mes_categoria(df)
        resumen_mes = resumen_mensual(df)

        graficos = [
            ("Distribución por categoría", grafico_distribucion_categorias(df)),
            ("Comparativo por mes", grafico_comparativo_meses(df)),
            ("Categorías por mes (apilado)", grafico_apilado_categoria_mes(df)),
        ]

        escribir_excel(df, pivot, resumen_mes, graficos, args.salida)
    except ErrorDatosGastos as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Listo: se generó '{args.salida}' con {len(df)} registros válidos.")


if __name__ == "__main__":
    main()
