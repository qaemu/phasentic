<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../assets/wordmark-dark.svg">
    <img src="../assets/wordmark-light.svg" alt="phasentic" width="360">
  </picture>
</p>

<p align="center">
  Identificación de fases por difracción de rayos X en polvo con un método validado y reproducible.
</p>

<p align="center">
  <a href="../README.md">English</a> | <b>Español</b> | <a href="README_fr.md">Français</a> | <a href="README_cn.md">简体中文</a> | <a href="README_ar.md">العربية</a> | <a href="README_de.md">Deutsch</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%E2%80%933.13-3776ab" alt="Python 3.10–3.13">
  <a href="../LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="Licencia MIT"></a>
</p>

<p align="center">
  <a href="#install">Instalación</a> ·
  <a href="#quick-start">Inicio rápido</a> ·
  <a href="#how-accurate-is-it">Validación</a> ·
  <a href="../docs/">Documentación</a>
</p>

Phasentic lee un difractograma de polvo (`.xy`, `.xrdml` o `.raw` en ASCII),
detecta los picos, consulta una base de datos de referencia construida a partir de la
[Crystallography Open Database](https://www.crystallography.net/cod/) (o [POW_COD](https://www.ba.ic.cnr.it/softwareic/qualx/) del CNR)
y ajusta mezclas de hasta cinco fases. Devuelve hipótesis de fases ordenadas y
registra en un informe JSON todos los parámetros, hashes y advertencias. Se
ejecuta en local, desde el navegador o desde la línea de comandos.

<p align="center">
  <img src="../docs/images/interface.png" alt="Interfaz de Phasentic: un resultado provisional de ZrO2 con la gráfica del ajuste, las hipótesis alternativas y las alternativas por fase" width="900">
  <br>
  <sub>Un difractograma de desarrollo del conjunto de datos Precursor Genome (PG_2452, Cu Kα), elegido al azar. Phasentic selecciona ZrO₂. La etiqueta refinada manualmente contiene además dos fases minoritarias: LiOH·H₂O, que aparece solo en las hipótesis alternativas (ZrO₂ + LiH₃O₂), y Li₂CO₃, que esta ejecución no detecta.</sub>
</p>

<a name="how-accurate-is-it"></a>
## Qué tan preciso es

Los parámetros se ajustaron con 485 difractogramas de Precursor Genome
(etiquetas refinadas manualmente) y luego se aplicaron a 200 difractogramas
bloqueados que el ajuste nunca vio, con la base de datos PXRD_COD 2026.11
(derivada de COD, con un complemento de Materials Project). Las abstenciones
cuentan como fallos.

| Nivel | Correctos | Tasa |
|---|---|---|
| Compuestos y estructuras cristalinas correctos (estricto) | 85 / 200 | 42,5 % |
| Compuestos correctos, cualquier polimorfo (familia) | 104 / 200 | 52,0 % |

Es la segunda ejecución sobre estos 200 difractogramas. La primera (72 y 99)
usó la base de datos solo con COD; el complemento de la base, las fórmulas con
hidrógeno restaurado y la preferencia por la descripción de mayor simetría de
un material se desarrollaron solo con los 485 difractogramas de ajuste. El
método sin ajustar obtuvo 71 y 96. Estas cifras valen para el preset validado
con PXRD_COD 2026.11, Cu Kα y la química de precursores de la muestra; otras
configuraciones no están probadas.

<a name="install"></a>
## Instalación

La instalación incluye Python 3.12, Phasentic y su base de datos de referencia
(una descarga de 8,6 GB desde Zenodo; deje unos 10 GB libres). No hacen falta
permisos de administrador.

Windows: pegue estas cuatro líneas en PowerShell (la primera es el instalador
oficial de [uv](https://docs.astral.sh/uv/), que instala Python):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
uv tool install --force --python 3.12 https://github.com/qaemu/phasentic/archive/refs/tags/v1.0.0.zip
phasentic setup
```

macOS y Linux:

```bash
curl -LsSf https://raw.githubusercontent.com/qaemu/phasentic/v1.0.0/install.sh | sh
```

En Windows, `phasentic setup` descarga la base de datos, agrega un acceso
directo **Phasentic** en el Escritorio y el menú Inicio y abre Phasentic en su
propia ventana; cierre Phasentic antes de reinstalar. En macOS el instalador
agrega Phasentic a Aplicaciones y en Linux al menú de aplicaciones. Si la
descarga se interrumpe, ejecute los mismos comandos otra vez; se reanuda.

### Usar POW_COD en su lugar

Si tiene **POW_COD 2205 (FULL)** de la
[página de descarga del CNR](https://www.ba.ic.cnr.it/softwareic/qualx/download/powcod-2205/),
instálelo con el comando siguiente; Phasentic lo usará en lugar de la base de
COD. Las cifras de precisión publicadas se midieron con la base de COD, no con
POW_COD.

```bash
phasentic setup-powcod ~/Downloads/powcod-2205.zip
```

<a name="quick-start"></a>
## Inicio rápido

Abra Phasentic desde su acceso directo o ejecute `phasentic-app`. Para usarlo
en un navegador, ejecute el comando siguiente y abra <http://127.0.0.1:8000>:

```bash
phasentic serve
```

Suelte un difractograma en la ventana (o elíjalo), escriba las fórmulas de
precursores y objetivo y pulse *Analizar*. Con fórmulas y Cu Kα se usa el
método validado; la tolerancia de picos y el máximo de fases se pueden cambiar
en *Ajustes de búsqueda*, y otros valores no están validados. *PDF* guarda un
informe simple con los valores medidos y calculados; *Informe formal* abre un
informe imprimible (gráfica del ajuste, evidencia por fase, hipótesis
alternativas, método y trazabilidad); *CIF* y *JSON* entregan los datos.

Desde la línea de comandos, el mismo método validado:

```bash
phasentic analyze scan.xrdml --preset validated --chemistry "Ag2O BaCO3 Ba2Ag2C2O7" --output report.json
```

`--chemistry` limita los candidatos a los elementos de esas fórmulas más H, C y
O (carbonatos, hidróxidos, hidratos). Sin `--preset`, cada parámetro del
análisis se puede ajustar con opciones (`phasentic analyze --help`); esas
combinaciones no están validadas.

Los resultados son como máximo `tentative` (o `ambiguous` / `unresolved`): una
decisión `supported` necesitaría una calibración de posiciones de línea
adjunta, que esta versión no ofrece. `phasentic calibrate standard.xy` sigue
comprobando las posiciones de línea de un instrumento con un difractograma
patrón (silicio NIST SRM 640g por defecto).

## Cuándo no usarlo

- **Para fracciones de fase.** Las escalas del ajuste son amplitudes de
  cribado, no porcentajes en peso.
- **Para muestras con tres o más fases**, donde en las pruebas identificó todos
  los compuestos solo el 11 % de las veces.
- **Para fases minoritarias o de baja dispersión** (por ejemplo sales de Li, B o
  K junto a fases de elementos pesados), que a menudo no detecta.

## Cómo funciona

1. Importa el difractograma, estima el fondo y detecta los picos (según el ruido).
2. Busca candidatos en la base de datos de referencia, limitados a los elementos de la muestra.
3. Ajusta mezclas no negativas de perfiles de referencia con una búsqueda en
   haz acotada, nuevas consultas sobre el residuo e intercambios de fases;
   descarta las fases cuyas líneas fuertes faltan en el difractograma.
4. Ordena las hipótesis, informa la ambigüedad y registra la procedencia (hash
   de la entrada, parámetros, identidad de la base de datos, versiones de los
   algoritmos).

Detalles: [docs/scientific-method.md](../docs/scientific-method.md) y
[PARAMETERS.md](../PARAMETERS.md).

## Cómo citar

Si Phasentic contribuye a su trabajo, cite la versión que usó. El botón *Cite
this repository* de GitHub (a partir de [CITATION.cff](../CITATION.cff)) da
APA y BibTeX. Cite también la base de datos de referencia,
[PXRD_COD 2026.11](https://doi.org/10.5281/zenodo.24059658), y las fuentes de
las que se construye: la Crystallography Open Database y Materials Project (y
POW_COD si lo usa en su lugar).

## Licencia

MIT para el código. La base de datos de referencia es CC BY 4.0 (datos de COD
CC0, datos de Materials Project CC BY 4.0). Los datos de POW_COD y Precursor
Genome se distribuyen bajo sus propios términos y no se incluyen en este
repositorio.
