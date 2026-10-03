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

<p align="center"><sub>Traducido del README en inglés con Claude Code y verificado mediante retrotraducción. Si ambas versiones difieren, prevalece la versión en inglés. Última sincronización: 2026-10-03.</sub></p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%E2%80%933.13-3776ab" alt="Python 3.10–3.13">
  <a href="../LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="Licencia MIT"></a>
</p>

<p align="center">
  <a href="#install">Instalación</a> ·
  <a href="#quick-start">Inicio rápido</a> ·
  <a href="#how-accurate-is-it">Validación</a> ·
  <a href="../docs/">Documentación</a> ·
  <a href="#how-this-was-built">Cómo se desarrolló</a>
</p>

Phasentic lee un difractograma de polvo (`.xy`, `.xrdml` o `.raw` en ASCII),
detecta los picos, consulta la base de datos de referencia
[POW_COD](https://www.ba.ic.cnr.it/softwareic/qualx/) del CNR y ajusta mezclas
de hasta cinco fases. Devuelve hipótesis de fases ordenadas por puntuación y
registra en un informe JSON todos los parámetros, hashes y advertencias. Se
ejecuta en local, desde el navegador o desde la línea de comandos.

<p align="center">
  <img src="../docs/images/interface.png" alt="Interfaz de Phasentic: un resultado provisional de ZrO2 y LiOH·H2O con la gráfica del ajuste y las hipótesis alternativas" width="900">
  <br>
  <sub>Un difractograma de desarrollo del conjunto de datos Precursor Genome (PG_2452, Cu Kα), elegido al azar. Phasentic encuentra ZrO₂ y LiOH·H₂O; la etiqueta refinada manualmente también incluye Li₂CO₃, que esta ejecución no detecta. La señal residual puede verse en <i>Evidencia por fase</i>.</sub>
</p>

<a name="how-accurate-is-it"></a>

## Exactitud

El método se congeló antes de las pruebas, junto con un objetivo declarado, y
se ejecutó una sola vez sobre 200 difractogramas que nunca había visto
(Precursor Genome, etiquetas refinadas manualmente). Las abstenciones cuentan
como fallos.

| Nivel | Aciertos | Tasa | Intervalo del 95% (Wilson) | Objetivo declarado |
|---|---|---|---|---|
| Compuestos y estructuras cristalinas correctos (strict) | 74 / 200 | 37.0% | 30.6–43.9% | ≥ 35% |
| Compuestos correctos, cualquier polimorfo (family) | 99 / 200 | 49.5% | 42.6–56.4% | ≥ 45% |

Ambas estimaciones puntuales alcanzan sus objetivos; ambos límites inferiores
quedan por debajo de ellos. La exactitud depende en gran medida del número de
fases:

| Fases en la muestra | Difractogramas | Aciertos (nivel family) |
|---|---|---|
| 1 | 8 | 3 |
| 2 | 125 | 87 (70%) |
| 3 o más | 67 | 9 (13%) |

El protocolo, la ejecución anterior sobre un conjunto de prueba reservado
(32% / 42% para la versión previa), el análisis de fallos y los comprobantes
se encuentran en [docs/validation.md](../docs/validation.md). Estas cifras se
aplican a la configuración validada con POW_COD, Cu Kα y la química de los
precursores de la muestra; otras configuraciones no se han probado.

<a name="install"></a>

## Instalación

Se necesita Python 3.10–3.13. La forma más sencilla instala el comando
`phasentic` en su propio entorno:

```bash
pipx install git+https://github.com/qaemu/phasentic
```

o bien, con [uv](https://docs.astral.sh/uv/): `uv tool install git+https://github.com/qaemu/phasentic`,
o directamente con pip: `pip install git+https://github.com/qaemu/phasentic`.

Comprobar que la instalación funciona:

```bash
phasentic --version
```

### Añadir la base de datos de referencia POW_COD (una sola vez)

Sin POW_COD, Phasentic funciona con un subconjunto de demostración de tres
fases que solo sirve para probar la interfaz. Para trabajo real:

1. Descargar **POW_COD 2205 (FULL)** (unos 1.9 GB) desde la
   [página de descarga del CNR](https://www.ba.ic.cnr.it/softwareic/qualx/download/powcod-2205/).
2. Ejecutar:

   ```bash
   phasentic setup-powcod ~/Downloads/powcod-2205.zip
   ```

Este comando verifica el archivo comprimido, lo extrae en `~/.phasentic/powcod`
(unos 6 GB) y construye una caché de consultas una única vez (20–60 minutos).
A partir de entonces, Phasentic usa POW_COD por defecto.

<a name="quick-start"></a>

## Inicio rápido

Iniciar la interfaz local y abrir <http://127.0.0.1:8000>:

```bash
phasentic serve
```

Elegir un difractograma, escribir las fórmulas de los precursores y del
producto objetivo, dejar seleccionado *Método validado* (la opción por defecto)
y pulsar *Analizar*. *Descargar informe* genera un documento imprimible de dos
páginas (gráfica del ajuste, evidencia por fase, hipótesis alternativas,
método y trazabilidad) que puede guardarse como PDF; *JSON* proporciona el
registro completo en formato legible por máquina.

Desde la línea de comandos, el mismo método validado:

```bash
phasentic analyze scan.xrdml --preset validated --chemistry "Ag2O BaCO3 Ba2Ag2C2O7" --output report.json
```

`--chemistry` restringe los candidatos a los elementos de esas fórmulas más H,
C y O (carbonatos, hidróxidos, hidratos). Sin `--preset`, todos los parámetros
del análisis pueden ajustarse mediante opciones (`phasentic analyze --help`);
esas combinaciones no están validadas.

Una decisión `supported` requiere además una calibración de la posición de las
líneas con un difractograma de un material de referencia (por defecto, silicio NIST SRM 640g):
`phasentic calibrate standard.xy`.

## Cuándo no usarlo

- **Para demostrar que una fase está presente.** Los resultados son hipótesis
  ordenadas que un científico debe confirmar, idealmente mediante refinamiento
  Rietveld.
- **Para obtener fracciones de fase.** Las escalas del ajuste son amplitudes
  de cribado, no porcentajes en peso.
- **Para muestras con tres o más fases**, en las que identificó todos los
  compuestos solo en el 13% de los casos durante las pruebas.
- **Para fases minoritarias o con bajo poder dispersor** (por ejemplo, sales de Li,
  B o K junto a fases con elementos pesados), que con frecuencia no detecta.
- **Sin la química de la muestra o con ánodos distintos de Cu**, que no
  formaron parte de la validación.

## Funcionamiento

1. Importar el difractograma, estimar el fondo y detectar los picos (teniendo
   en cuenta el ruido).
2. Recuperar candidatos de POW_COD, restringidos a los elementos de la muestra.
3. Ajustar mezclas no negativas de perfiles de referencia mediante una
   búsqueda en haz acotada, nuevas consultas sobre el residuo e intercambios de
   fases; descartar las fases cuyas líneas intensas no aparecen en el
   difractograma.
4. Ordenar las hipótesis, informar de las ambigüedades y registrar la
   procedencia (hash de la entrada, parámetros, identidad de la base de datos,
   versiones de los algoritmos).

Detalles: [docs/scientific-method.md](../docs/scientific-method.md) y
[PARAMETERS.md](../PARAMETERS.md).

## Reproducir la validación

Clonar el repositorio e instalarlo:

```bash
git clone https://github.com/qaemu/phasentic && cd phasentic
pip install -e .
```

Las ejecuciones validadas usan `scripts/run_wp5_parallel.py`, que se niega a
ejecutarse si el código de análisis difiere del hash registrado en la
configuración congelada (`validation/wp5-precursor-frozen-v5.json`). Las listas
de casos de cada cohorte y los comprobantes de resultados están en
[`validation/`](../validation/); los difractogramas proceden del conjunto de
datos [Precursor Genome](https://github.com/lauren-walters/precursor-genome)
(CC BY 4.0). Las instrucciones paso a paso están en
[docs/validation.md](../docs/validation.md).

<a name="how-this-was-built"></a>

## Cómo se desarrolló

Phasentic fue escrito casi en su totalidad por **Claude Code**, el agente de
programación de Anthropic, trabajando bajo mi dirección. Soy un único
desarrollador. Elegí el problema, los métodos y el protocolo de validación,
revisé los resultados y soy responsable de cada afirmación de este
repositorio.

Los elementos que permiten verificar las afirmaciones se fijaron antes de ver
los resultados: el objetivo de exactitud se declaró antes del ajuste de
parámetros, el ajuste usó solo 100 difractogramas de desarrollo, el conjunto
de prueba reservado se selló y se ejecutó una sola vez, la configuración y el
código se congelaron mediante hash, y las refactorizaciones posteriores
debían reproducir exactamente los 300 resultados
([docs/validation.md](../docs/validation.md)). Los commits realizados con
asistencia de IA llevan la línea final `Assisted-by: Claude Code`. Véase
[AI_USE.md](../AI_USE.md).

## Cómo citar

Si Phasentic contribuye a un trabajo, debe citarse la versión utilizada. El botón
*Cite this repository* de GitHub (generado a partir de
[CITATION.cff](../CITATION.cff)) proporciona las referencias en APA y BibTeX.
Deben citarse también POW_COD y la Crystallography Open Database.

## Licencia

MIT para el código. Los datos de POW_COD, COD y Precursor Genome se
distribuyen bajo sus propios términos y no se incluyen en este repositorio.
