#!/usr/bin/env python3
"""App de escritorio para generar el reporte de gastos en un solo paso.

Flujo de 3 clics: agregar los archivos del banco, indicar el tipo de cada uno
(Cuenta BROU / Tarjeta BROU / Manual) y apretar "Generar reporte". La app
encadena la importación (``importar_estado.importar_archivo``) y la generación
del Excel anual (``resumen_gastos.generar_reportes``) sin usar la terminal.

Se ejecuta con:  python app.py   (o ./lanzar.sh)
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from importar_estado import ErrorImportacion, importar_archivo
from resumen_gastos import ErrorDatosGastos, generar_reportes

# Directorio donde vive la app; ancla el CSV acumulador y la carpeta default.
DIR_APP = os.path.dirname(os.path.abspath(__file__))
CSV_ACUMULADOR = os.path.join(DIR_APP, "gastos.csv")

# Etiqueta visible -> identificador de fuente para el adaptador.
TIPOS_FUENTE = {
    "Cuenta BROU": "brou",
    "Tarjeta BROU": "brou_tc",
    "Manual (CSV)": "manual",
}
# Orden de procesamiento: cuenta/manual antes que tarjeta, para que el
# reemplazo del pago de TC "vea" las filas de la cuenta del mismo mes.
PRIORIDAD_FUENTE = {"brou": 0, "manual": 0, "brou_tc": 1}


class FilaArchivo:
    """Una fila de la lista: ruta del archivo + combo de tipo + botón quitar."""

    def __init__(self, app: "AppGastos", ruta: str):
        self.app = app
        self.ruta = ruta
        self.frame = ttk.Frame(app.cont_archivos)
        self.frame.pack(fill="x", pady=2)

        ttk.Label(self.frame, text=os.path.basename(ruta), width=38, anchor="w").pack(
            side="left", padx=(0, 6)
        )
        self.combo = ttk.Combobox(
            self.frame, values=list(TIPOS_FUENTE), state="readonly", width=16
        )
        # Preseleccionar según el nombre del archivo (heurística suave).
        nombre = os.path.basename(ruta).lower()
        if "tarjeta" in nombre or "_tc" in nombre or "credito" in nombre:
            self.combo.set("Tarjeta BROU")
        elif ruta.lower().endswith(".csv"):
            self.combo.set("Manual (CSV)")
        else:
            self.combo.set("Cuenta BROU")
        self.combo.pack(side="left", padx=6)

        ttk.Button(self.frame, text="Quitar", command=self.quitar, width=8).pack(
            side="left", padx=6
        )

    @property
    def fuente(self) -> str:
        return TIPOS_FUENTE[self.combo.get()]

    def quitar(self) -> None:
        self.frame.destroy()
        self.app.filas.remove(self)


class AppGastos:
    """Ventana principal."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.filas: list[FilaArchivo] = []
        self.cola: queue.Queue[tuple[str, object]] = queue.Queue()

        root.title("Reporte de gastos")
        root.minsize(640, 520)

        marco = ttk.Frame(root, padding=12)
        marco.pack(fill="both", expand=True)

        ttk.Label(
            marco, text="1. Archivos del banco", font=("", 11, "bold")
        ).pack(anchor="w")
        ttk.Button(marco, text="+ Agregar archivo…", command=self.agregar_archivo).pack(
            anchor="w", pady=(4, 6)
        )
        # Contenedor de filas de archivos.
        self.cont_archivos = ttk.Frame(marco)
        self.cont_archivos.pack(fill="x")

        ttk.Separator(marco).pack(fill="x", pady=10)

        ttk.Label(
            marco, text="2. Carpeta de salida", font=("", 11, "bold")
        ).pack(anchor="w")
        fila_out = ttk.Frame(marco)
        fila_out.pack(fill="x", pady=(4, 6))
        self.var_salida = tk.StringVar(value=os.path.join(DIR_APP, "reportes"))
        ttk.Entry(fila_out, textvariable=self.var_salida).pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(fila_out, text="Elegir…", command=self.elegir_carpeta).pack(
            side="left", padx=6
        )

        ttk.Separator(marco).pack(fill="x", pady=10)

        self.btn_generar = ttk.Button(
            marco, text="Generar reporte", command=self.generar
        )
        self.btn_generar.pack(anchor="w")

        ttk.Label(marco, text="Progreso", font=("", 11, "bold")).pack(
            anchor="w", pady=(10, 4)
        )
        self.log = ScrolledText(marco, height=12, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True)

        self.btn_abrir = ttk.Button(
            marco, text="Abrir carpeta de salida", command=self.abrir_carpeta,
            state="disabled",
        )
        self.btn_abrir.pack(anchor="w", pady=(8, 0))

    # ----- acciones de UI -----
    def agregar_archivo(self) -> None:
        rutas = filedialog.askopenfilenames(
            title="Elegir estado(s) de cuenta",
            filetypes=[
                ("Estados de cuenta", "*.xls *.xlsx *.csv"),
                ("Todos", "*.*"),
            ],
        )
        for ruta in rutas:
            self.filas.append(FilaArchivo(self, ruta))

    def elegir_carpeta(self) -> None:
        carpeta = filedialog.askdirectory(title="Carpeta de salida")
        if carpeta:
            self.var_salida.set(carpeta)

    def abrir_carpeta(self) -> None:
        _abrir_en_explorador(self.var_salida.get())

    def _escribir_log(self, texto: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", texto + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    # ----- generación (en worker thread) -----
    def generar(self) -> None:
        if not self.filas:
            messagebox.showwarning(
                "Sin archivos", "Agregá al menos un archivo antes de generar."
            )
            return

        # Snapshot de (fuente, ruta) para pasar al worker sin tocar widgets.
        trabajos = [(f.fuente, f.ruta) for f in self.filas]
        salida_dir = self.var_salida.get().strip() or os.path.join(DIR_APP, "reportes")

        self.btn_generar.configure(state="disabled")
        self.btn_abrir.configure(state="disabled")
        self._escribir_log("── Iniciando ──")

        hilo = threading.Thread(
            target=self._trabajar, args=(trabajos, salida_dir), daemon=True
        )
        hilo.start()
        self.root.after(100, self._drenar_cola)

    def _trabajar(self, trabajos: list[tuple[str, str]], salida_dir: str) -> None:
        """Corre en un hilo aparte; comunica progreso vía self.cola."""
        try:
            # Procesar cuenta/manual antes que tarjeta (reemplazo de pago TC).
            trabajos_ordenados = sorted(trabajos, key=lambda t: PRIORIDAD_FUENTE[t[0]])
            # Empezar de cero: el acumulador se reconstruye en cada corrida.
            if os.path.isfile(CSV_ACUMULADOR):
                os.remove(CSV_ACUMULADOR)

            for fuente, ruta in trabajos_ordenados:
                stats = importar_archivo(fuente, ruta, CSV_ACUMULADOR, append=True)
                self.cola.put(("log", f"Importado {os.path.basename(ruta)}: "
                                       f"{stats['filas']} filas"
                                       + (f", {stats['tc_reemplazadas']} pago(s) TC reemplazados"
                                          if stats["tc_reemplazadas"] else "")
                                       + (f", {stats['omitidos']} duplicadas omitidas"
                                          if stats["omitidos"] else "")
                                       + (f", {stats['sin_clasificar']} sin clasificar"
                                          if stats["sin_clasificar"] else "")))

            generados = generar_reportes(CSV_ACUMULADOR, salida_dir)
            self.cola.put(("log", "── Reportes generados ──"))
            for ruta_xlsx, n in generados:
                self.cola.put(("log", f"  {os.path.basename(ruta_xlsx)} ({n} registros)"))
            self.cola.put(("ok", salida_dir))
        except (ErrorImportacion, ErrorDatosGastos) as exc:
            self.cola.put(("error", str(exc)))
        except Exception as exc:  # red de seguridad: nunca dejar la UI colgada
            self.cola.put(("error", f"Error inesperado: {exc}"))

    def _drenar_cola(self) -> None:
        """Consume mensajes del worker y actualiza la UI (hilo principal)."""
        try:
            while True:
                tipo, dato = self.cola.get_nowait()
                if tipo == "log":
                    self._escribir_log(str(dato))
                elif tipo == "ok":
                    self._escribir_log("Listo ✓")
                    self.btn_generar.configure(state="normal")
                    self.btn_abrir.configure(state="normal")
                    return
                elif tipo == "error":
                    self._escribir_log(f"ERROR: {dato}")
                    messagebox.showerror("Error", str(dato))
                    self.btn_generar.configure(state="normal")
                    return
        except queue.Empty:
            pass
        self.root.after(100, self._drenar_cola)


def _abrir_en_explorador(ruta: str) -> None:
    """Abre una carpeta en el explorador de archivos del sistema."""
    if not os.path.isdir(ruta):
        return
    try:
        if sys.platform.startswith("linux"):
            subprocess.Popen(["xdg-open", ruta])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", ruta])
        elif sys.platform.startswith("win"):
            os.startfile(ruta)  # type: ignore[attr-defined]
    except Exception:
        pass  # abrir el explorador es un extra; no romper si falla


def main() -> None:
    root = tk.Tk()
    AppGastos(root)
    root.mainloop()


if __name__ == "__main__":
    main()
