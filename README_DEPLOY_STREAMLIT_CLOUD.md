# Corrección de despliegue en Streamlit Cloud

Esta versión deja `app.py`, `requirements.txt`, `packages.txt`, `modules/`, `data/` y `tests/` en la raíz del proyecto.

## Configuración recomendada

- Main file path: `app.py`
- Python version: `3.12` o `3.11` en Advanced settings.
- Si aparece `ModuleNotFoundError`, revisar en Manage app > Logs que Streamlit haya encontrado `requirements.txt`.

## Causa probable del error corregido

El error mostrado en pantalla corresponde a una falla de importación. En Streamlit Cloud suele ocurrir cuando:

1. `requirements.txt` no está en la raíz o en la misma carpeta del `app.py`.
2. El `Main file path` apunta a una carpeta distinta de la que contiene las dependencias.
3. Falta subir la carpeta `modules/` completa.
4. Alguna dependencia geoespacial necesita paquetes externos.

Esta versión corrige la estructura para que Streamlit Cloud detecte los archivos de dependencia y los módulos locales.
