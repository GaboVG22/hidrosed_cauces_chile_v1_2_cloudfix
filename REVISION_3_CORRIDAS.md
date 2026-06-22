# Protocolo de revisión ejecutado — v1.2

Fecha de generación: 2026-06-12

## Actualización v1.2 — Modo dios hidráulico

Se incorporó un motor hidráulico 1D avanzado por método del paso estándar, con conexión hidráulica entre secciones mediante ecuación de energía.

Mejoras aplicadas:

- `compute_standard_step_profile()` en `modules/hydraulic_solver_1d.py`.
- Condiciones de borde por tirante normal, cota conocida o tirante crítico.
- Cálculo de profundidad crítica por sección irregular.
- Cálculo de energía específica y energía total.
- Pérdidas por fricción.
- Pérdidas locales por contracción y expansión.
- Coeficientes por tramo desde hoja `Coeficientes_Hidraulicos`.
- Manning por perfil, por sección o por material.
- Régimen subcrítico, supercrítico o automático.
- Diagnóstico de régimen mixto.
- Residual de cierre energético.
- Control de calidad de monotonía de cota de agua por período de retorno.
- Interfaz Streamlit más guiada en la pestaña **Hidráulica 1D**.

## Corrida 1 — Estructural

Resultado: OK.

Verificaciones:

- Compilación de `app.py`.
- Compilación de todos los módulos en `modules/`.
- Compilación de `tests/run_selfcheck.py`.
- Importación de módulos principales.
- Importación del nuevo solver hidráulico 1D.

## Corrida 2 — Funcional con datos ficticios

Resultado: OK.

Verificaciones:

- Lectura de `data/plantilla_entrada.xlsx`.
- Validación de hojas y columnas mínimas.
- Clasificación de secciones válidas, descartadas y de revisión manual.
- Cálculo de caudales T=2, 5, 10, 25, 50, 100 y 200.
- Aplicación de caudales por km.
- Cálculo hidráulico local de respaldo.
- Cálculo hidráulico 1D por paso estándar.
- Cálculo de profundidad crítica.
- Cálculo de energía total.
- Cálculo de transporte de sedimentos.
- Balance Exner simplificado.
- Socavación y depositación preliminar.

## Corrida 3 — Técnica

Resultado: OK.

Verificaciones:

- Caudales adoptados crecientes con período de retorno.
- Tirantes crecientes con período de retorno después del control QA.
- Residual energético disponible por sección.
- Diagnóstico de régimen mixto disponible.
- Lectura de KMZ de curvas de nivel.
- Detección de cotas en curvas.
- Interpolación de terreno desde curvas KMZ.
- Generación de profundidad de inundación.
- Filtro de conectividad hidráulica.
- Mapa de velocidad preliminar.
- Zonas críticas por velocidad.

## Comando utilizado

```bash
python -m compileall -q .
python tests/run_selfcheck.py
```

## Resultado del selfcheck

```text
CORRIDA 1 - Estructural/imports: OK
CORRIDA 2 - Funcional plantilla/hidrología/hidráulica/sedimentos: OK
CORRIDA 3 - Técnica monotonía/mapa inundación/velocidad: OK
SELF CHECK COMPLETO
```

## Observación técnica

La versión v1.2 se acerca a una modelación HEC-RAS 1D en flujo permanente, pero sigue siendo una herramienta preliminar. Cuando existan estructuras complejas, régimen mixto con resalto, planicie 2D relevante o topografía insuficiente, se recomienda usar HEC-RAS 1D/2D como verificación externa.
