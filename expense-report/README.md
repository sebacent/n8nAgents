# Reporte de gastos personales

Genera un Excel anual (una hoja por mes + resumen + gráficos) a partir de los
estados de cuenta del banco.

## Instalación (una sola vez)

```bash
cd expense-report
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> En algunas distros de Linux, la interfaz gráfica necesita el paquete de
> sistema de Tk (no se instala con pip):
> `sudo apt install python3-tk`

## Uso con la app (recomendado)

```bash
./lanzar.sh
```

Y en la ventana:

1. **Agregar archivo…** → elegí uno o varios estados de cuenta (`.xls`,
   `.xlsx` o `.csv`).
2. Por cada archivo, elegí el **tipo**: *Cuenta BROU*, *Tarjeta BROU* o
   *Manual*.
3. (Opcional) Cambiá la **carpeta de salida** (por defecto `reportes/`).
4. **Generar reporte**.

Al terminar aparece un `resumen_gastos_<año>.xlsx` por cada año, y el botón
**Abrir carpeta de salida** te lleva ahí.

Si cargás la cuenta y la tarjeta juntas, la app procesa la cuenta primero y
reemplaza el pago de la tarjeta por su desglose real (evita el doble conteo).

## Uso por línea de comandos (avanzado)

```bash
# 1) Importar cada estado al CSV canónico
python importar_estado.py --fuente brou    --entrada estado_cuenta.xls  --salida gastos.csv
python importar_estado.py --fuente brou_tc --entrada estado_tarjeta.xls --salida gastos.csv --append

# 2) Generar los Excel anuales
python resumen_gastos.py --entrada gastos.csv --salida-dir reportes
```

Fuentes disponibles (`--fuente`): `brou` (cuenta), `brou_tc` (tarjeta),
`manual` (CSV ya en formato canónico).

## Categorías

La clasificación se controla con `categorias.yml` (categoría → lista de
patrones de texto). El tipo *gasto/ingreso* lo determina siempre el banco
(columnas Débito/Crédito), no las reglas.
