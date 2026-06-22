# HidroSed Cauces Chile v1.2 — Modo dios hidráulico

Aplicación técnica en Python + Streamlit para análisis hidrológico, hidráulico 1D conectado, transporte de sedimentos, socavación, depositación, terreno desde DEM/curvas de nivel e inundación preliminar en planta.

## Mejora central v1.2

La versión v1.2 incorpora un **motor hidráulico 1D por paso estándar**, más cercano a la lógica de HEC-RAS 1D para flujo permanente. La aplicación ya no depende solamente de Manning local por sección: ahora puede conectar hidráulicamente las secciones mediante la ecuación de energía.

El nuevo motor considera:

- cálculo sección a sección mediante ecuación de energía;
- régimen subcrítico, supercrítico o automático;
- condición de borde aguas abajo o aguas arriba;
- condición de borde por tirante normal, cota conocida o tirante crítico;
- profundidad crítica por sección irregular;
- energía específica y energía total;
- pérdidas por fricción;
- pérdidas locales por contracción y expansión;
- coeficientes hidráulicos por tramo;
- Manning por perfil, por sección o por material;
- comparación entre resultado local y resultado por paso estándar;
- diagnóstico de régimen mixto;
- residual de cierre energético;
- control de calidad de monotonía de niveles de agua;
- nivel de confianza del modelo.

## Alcance

La aplicación permite:

- Cargar un Excel con perfil longitudinal, secciones transversales, cuenca, precipitación, granulometría y parámetros.
- Clasificar secciones válidas, descartadas y de revisión manual.
- Estimar caudales para T = 2, 5, 10, 25, 50, 100 y 200 años.
- Ingresar caudales por km del cauce, como aporte lateral/tributario, extracción, caudal local o caudal de control que reemplaza el caudal base desde ese km hacia aguas abajo.
- Calcular hidráulica por sección con caudal variable longitudinalmente.
- Calcular perfiles hidráulicos conectados por energía.
- Calcular movilidad del lecho, transporte de fondo preliminar, balance Exner simplificado, socavación y depositación.
- Cargar KMZ/KML con punto de control para descarga DEM COP30 desde OpenTopography.
- Cargar KMZ/KML con curvas de nivel del cauce, detectar cotas y generar superficie interpolada.
- Proyectar área aproximada de inundación, profundidad, velocidad y zonas críticas en rojo por velocidad.
- Exportar Excel, KMZ e informe Word preliminar.

## Advertencia técnica

Esta herramienta es de apoyo técnico preliminar. No reemplaza una modelación HEC-RAS 1D/2D validada ni un levantamiento topográfico de detalle.

La versión v1.2 mejora la conexión hidráulica entre secciones, pero los resultados deben ser revisados por especialista, especialmente cuando existan:

- puentes o alcantarillas complejas;
- flujo mixto con resaltos hidráulicos;
- remansos fuertes;
- planicies 2D relevantes;
- cauces urbanos encajonados;
- topografía insuficiente;
- sedimentos cohesivos o flujos detríticos.

OpenTopography requiere API Key para GlobalDEM. COP30 es un DSM, por lo que puede incluir vegetación, edificios e infraestructura.

## Estructura del proyecto

```text
app.py
requirements.txt
README.md
REVISION_3_CORRIDAS.md
modules/
  excel_io.py
  validation.py
  hydrology.py
  flow_profile.py
  hydraulics.py
  hydraulic_solver_1d.py
  boundary_conditions.py
  sediment_transport.py
  sediment_routing.py
  scour.py
  control_point.py
  dem_downloader.py
  contour_kmz_reader.py
  terrain_processing.py
  contour_generator.py
  flood_mapping.py
  velocity_mapping.py
  plotting.py
  kmz_export.py
  report_generator.py
  hecras_export.py
  model_diagnostics.py
data/
  plantilla_entrada.xlsx
  punto_control_ejemplo.kmz
  curvas_nivel_ejemplo.kmz
outputs/
tests/
  run_selfcheck.py
```

## Hojas nuevas o reforzadas en la plantilla

### `Condiciones_Borde`

Permite indicar la condición de borde para el perfil hidráulico 1D.

| columna | descripción |
|---|---|
| `tipo` | `normal_depth`, `known_wse` o `critical_depth` |
| `ubicacion` | `aguas_abajo` o `aguas_arriba` |
| `km` | progresiva asociada |
| `valor` | pendiente normal o cota de agua, según tipo |
| `unidad` | `pendiente`, `m` o `-` |
| `periodo_retorno` | opcional; si está vacío aplica general |
| `observacion` | criterio usado |

### `Coeficientes_Hidraulicos`

Define pérdidas locales por tramo.

| columna | descripción |
|---|---|
| `km_inicio` | inicio del tramo |
| `km_fin` | fin del tramo |
| `contraccion` | coeficiente de contracción |
| `expansion` | coeficiente de expansión |
| `tipo_tramo` | transición gradual, cambio moderado, puente, etc. |
| `observacion` | criterio técnico |

### `Secciones`

Ahora puede incluir columnas opcionales:

| columna | descripción |
|---|---|
| `zona_hidraulica` | `ribera_izquierda`, `cauce_principal`, `ribera_derecha` |
| `n_manning` | rugosidad por punto/sección |

Si no existe `n_manning`, la app usa el Manning del perfil longitudinal o recomienda uno por material.

## Caudales por km del cauce

La plantilla incluye la hoja `Caudales_Km`, que permite modificar el caudal de cálculo en un punto específico del cauce.

| columna | descripción |
|---|---|
| `km` | progresiva del cauce donde se aplica el caudal o aporte |
| `periodo_retorno` | 2, 5, 10, 25, 50, 100 o 200 |
| `caudal_m3s` | caudal a sumar, restar o adoptar |
| `tipo_caudal` | `aporte_lateral`, `extraccion`, `caudal_control` o `caudal_local` |
| `observaciones` | explicación técnica del origen del caudal |

Reglas aplicadas:

- `aporte_lateral`: suma el caudal desde ese km hacia aguas abajo.
- `extraccion`: resta el caudal desde ese km hacia aguas abajo.
- `caudal_control`: reemplaza el caudal base desde ese km hacia aguas abajo.
- `caudal_local`: aplica el caudal solo a la sección más cercana al km indicado.

## Uso recomendado en plataforma

1. Cargar Excel.
2. Validar secciones.
3. Cargar terreno: DEM, punto KMZ o curvas de nivel KMZ.
4. Calcular caudales.
5. Revisar o ingresar caudales por km.
6. Ir a **Hidráulica 1D — Modo dios hidráulico**.
7. Usar por defecto: `1D paso estándar por energía` + régimen `Automático`.
8. Revisar condición de borde.
9. Calcular hidráulica conectada 1D.
10. Revisar diagnóstico de régimen/convergencia.
11. Continuar con sedimentos, socavación, inundación y descargas.

## Ejecutar localmente

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
streamlit run app.py
```

## Ejecutar en Streamlit Cloud

1. Crear repositorio GitHub.
2. Subir todos los archivos del proyecto.
3. En Streamlit Cloud seleccionar el repositorio.
4. Main file path:

```text
app.py
```

## Protocolo de tres corridas

Antes de usar una versión definitiva, ejecutar:

```bash
python tests/run_selfcheck.py
```

El script realiza:

1. Corrida estructural: importación y sintaxis de módulos.
2. Corrida funcional: lectura de plantilla, validación, caudales, hidráulica 1D, sedimentos y socavación.
3. Corrida técnica: revisión de monotonía, residual energético, mapa de inundación y velocidad.

## Recomendaciones futuras

- Exportador nativo HEC-RAS GIS/SDF completo.
- Lectura de resultados HEC-RAS para comparación.
- Módulo de estructuras avanzado para puentes y alcantarillas.
- Manejo de régimen mixto con detección de resalto hidráulico.
- Modelación 2D real externa o acople con HEC-RAS 2D.
- Rasterización/polygonización real de inundaciones con `rasterio.features`.
- Calibración automática con marcas de crecida y niveles observados.
