from __future__ import annotations

from pathlib import Path
from io import BytesIO
import tempfile
import zipfile

import numpy as np
import pandas as pd
import streamlit as st

from modules.excel_io import load_excel, get_sheet, to_excel_bytes
from modules.validation import validate_all
from modules.hydrology import build_design_flows, RETURN_PERIODS
from modules.flow_profile import normalize_flow_points, get_section_kms, build_flow_profile_by_km
from modules.hydraulics import compute_hydraulics_for_sections
from modules.hydraulic_solver_1d import compute_energy_grade_line, detect_mixed_regime, compute_standard_step_profile
from modules.sediment_transport import compute_sediment_transport, interpolate_granulometry
from modules.sediment_routing import exner_balance
from modules.scour import compute_scour_deposition
from modules.control_point import read_control_point, bbox_from_point
from modules.dem_downloader import build_globaldem_url, download_dem
from modules.contour_kmz_reader import read_contour_kmz, apply_manual_elevations
from modules.terrain_processing import contours_to_grid
from modules.contour_generator import contours_from_grid
from modules.flood_mapping import build_water_surface_grid, compute_depth_grid, connectivity_filter, flood_summary
from modules.velocity_mapping import velocity_grid_from_depth, velocity_summary, classify_velocity
from modules.plotting import plot_longitudinal_profile, plot_cross_section, plot_hydrology, plot_raster_map
from modules.kmz_export import export_sections_kmz, export_flood_kmz
from modules.report_generator import generate_word_report
from modules.model_diagnostics import run_technical_checks

APP_TITLE = "HidroSed Cauces Chile"
OUT_DIR = Path("outputs")
OUT_DIR.mkdir(exist_ok=True)

st.set_page_config(page_title=APP_TITLE, layout="wide")
st.title("HidroSed Cauces Chile")
st.caption("Hidrología, hidráulica 1D, sedimentos, socavación, depositación, DEM/curvas de nivel e inundación preliminar en planta.")

with st.sidebar:
    st.header("Estado del modelo")
    st.write("Períodos obligatorios:", ", ".join([str(t) for t in RETURN_PERIODS]))
    st.warning("Herramienta preliminar. No reemplaza modelación HEC-RAS 1D/2D ni revisión profesional.")

if "sheets" not in st.session_state:
    st.session_state.sheets = {}
if "validation" not in st.session_state:
    st.session_state.validation = None
if "design_flows" not in st.session_state:
    st.session_state.design_flows = pd.DataFrame()
if "hyd" not in st.session_state:
    st.session_state.hyd = pd.DataFrame()
if "flow_points_km" not in st.session_state:
    st.session_state.flow_points_km = pd.DataFrame()
if "flow_profile_km" not in st.session_state:
    st.session_state.flow_profile_km = pd.DataFrame()
if "terrain" not in st.session_state:
    st.session_state.terrain = {}

# -------------------------
# Tabs
# -------------------------
tabs = st.tabs([
    "1. Carga de datos",
    "2. Validación del Excel",
    "3. Terreno, DEM y curvas de nivel",
    "4. Perfil longitudinal",
    "5. Secciones transversales",
    "6. Hidrología y caudales",
    "7. Hidráulica 1D",
    "8. Perfiles hidráulicos",
    "9. Granulometría",
    "10. Transporte de sedimentos",
    "11. Socavación y depositación",
    "12. Visualización hidráulica y socavación",
    "13. Inundación en planta",
    "14. Velocidad y zonas críticas",
    "15. Resultados",
    "16. Descargas",
    "17. Informe técnico",
])

# 1 Carga
with tabs[0]:
    st.subheader("Carga de Excel de entrada")
    uploaded = st.file_uploader("Cargar Excel", type=["xlsx", "xlsm", "xls"])
    if uploaded:
        try:
            result = load_excel(uploaded)
            st.session_state.sheets = result.sheets
            st.success(f"Excel cargado con {len(result.sheets)} hojas.")
            if result.missing_sheets:
                st.error("Faltan hojas requeridas: " + ", ".join(result.missing_sheets))
            for w in result.warnings:
                st.warning(w)
        except Exception as exc:
            st.error(str(exc))
    st.info("La plantilla de ejemplo se encuentra en data/plantilla_entrada.xlsx dentro del paquete.")

# 2 Validación
with tabs[1]:
    st.subheader("Validación automática")
    if not st.session_state.sheets:
        st.info("Cargue un Excel para validar.")
    else:
        report = validate_all(st.session_state.sheets)
        st.session_state.validation = report
        c1, c2, c3 = st.columns(3)
        c1.metric("Errores", len(report.errors))
        c2.metric("Advertencias", len(report.warnings))
        c3.metric("Secciones clasificadas", len(report.section_status))
        if report.errors:
            for e in report.errors:
                st.error(e)
        if report.warnings:
            for w in report.warnings:
                st.warning(w)
        st.dataframe(report.section_status, use_container_width=True)

# 3 Terreno
with tabs[2]:
    st.subheader("Terreno, DEM y curvas de nivel")
    st.write("Este módulo permite usar DEM COP30, DEM propio o KMZ/KML de curvas de nivel del cauce.")
    source = st.radio("Fuente de terreno", ["Sin terreno", "Descargar DEM COP30 desde punto KMZ", "Cargar DEM GeoTIFF propio", "Cargar KMZ/KML con curvas de nivel"], horizontal=False)
    if source == "Descargar DEM COP30 desde punto KMZ":
        col1, col2 = st.columns(2)
        point_file = col1.file_uploader("KMZ/KML punto de control", type=["kmz", "kml"], key="pointkmz")
        api_key = col2.text_input("API Key OpenTopography", type="password")
        margin = st.slider("Margen de descarga en grados", 0.005, 0.25, 0.05, step=0.005)
        if point_file:
            try:
                pt = read_control_point(point_file)
                st.session_state.terrain["control_point"] = pt
                st.success(f"Punto detectado: lat {pt['latitud']:.6f}, lon {pt['longitud']:.6f}")
                bbox = bbox_from_point(pt["latitud"], pt["longitud"], margin)
                st.json(bbox)
                st.code(build_globaldem_url(bbox, api_key or "SU_API_KEY", demtype="COP30"))
                if api_key and st.button("Descargar DEM COP30"):
                    out = OUT_DIR / "dem_cop30.tif"
                    p = download_dem(bbox, api_key, out)
                    st.session_state.terrain["dem_path"] = str(p)
                    st.success(f"DEM descargado: {p}")
            except Exception as exc:
                st.error(str(exc))
    elif source == "Cargar DEM GeoTIFF propio":
        dem = st.file_uploader("Cargar DEM GeoTIFF", type=["tif", "tiff"])
        if dem:
            path = OUT_DIR / dem.name
            path.write_bytes(dem.getbuffer())
            st.session_state.terrain["dem_path"] = str(path)
            st.success(f"DEM cargado: {path}")
    elif source == "Cargar KMZ/KML con curvas de nivel":
        contour_file = st.file_uploader("KMZ/KML curvas de nivel", type=["kmz", "kml"], key="contourkmz")
        res = st.number_input("Resolución de grilla interpolada en grados", min_value=0.00005, max_value=0.005, value=0.0005, step=0.00005, format="%.5f")
        if contour_file:
            try:
                lines_df, pts_df = read_contour_kmz(contour_file)
                st.session_state.terrain["contour_lines"] = lines_df
                st.session_state.terrain["contour_points"] = pts_df
                st.write("Curvas detectadas")
                edited = st.data_editor(lines_df, use_container_width=True, key="edited_contours")
                pts2 = apply_manual_elevations(pts_df, edited)
                if st.button("Interpolar terreno desde curvas"):
                    gx, gy, gz = contours_to_grid(pts2, resolution=res)
                    st.session_state.terrain["grid"] = (gx, gy, gz)
                    st.session_state.terrain["terrain_source"] = "curvas_kmz"
                    st.success("Terreno interpolado desde curvas de nivel.")
                    st.plotly_chart(plot_raster_map(gx, gy, gz, "Terreno interpolado desde curvas", colorscale="Earth"), use_container_width=True)
                if "grid" in st.session_state.terrain:
                    gx, gy, gz = st.session_state.terrain["grid"]
                    st.plotly_chart(plot_raster_map(gx, gy, gz, "Terreno interpolado desde curvas", colorscale="Earth"), use_container_width=True)
            except Exception as exc:
                st.error(str(exc))

# common loaded sheets
sheets = st.session_state.sheets
profile = get_sheet(sheets, "Perfil_Longitudinal") if sheets else pd.DataFrame()
sections = get_sheet(sheets, "Secciones") if sheets else pd.DataFrame()
cuenca = get_sheet(sheets, "Cuenca") if sheets else pd.DataFrame()
precip = get_sheet(sheets, "Precipitacion") if sheets else pd.DataFrame()
gran = get_sheet(sheets, "Granulometria") if sheets else pd.DataFrame()
manual_flows = get_sheet(sheets, "Caudales_Observados") if sheets else pd.DataFrame()
caudales_km = get_sheet(sheets, "Caudales_Km") if sheets else pd.DataFrame()
if caudales_km.empty and sheets:
    caudales_km = get_sheet(sheets, "Caudales_Por_Km")
axis_df = get_sheet(sheets, "Eje_Cauce") if sheets else pd.DataFrame()
boundary_conditions_df = get_sheet(sheets, "Condiciones_Borde") if sheets else pd.DataFrame()
coeffs_hidraulicos_df = get_sheet(sheets, "Coeficientes_Hidraulicos") if sheets else pd.DataFrame()
observaciones_hid_df = get_sheet(sheets, "Observaciones_Hidraulicas") if sheets else pd.DataFrame()

# 4 Perfil
with tabs[3]:
    st.subheader("Perfil longitudinal")
    if profile.empty:
        st.info("Cargue perfil longitudinal.")
    else:
        status = st.session_state.validation.section_status if st.session_state.validation else pd.DataFrame()
        st.plotly_chart(plot_longitudinal_profile(profile, status), use_container_width=True)
        st.dataframe(profile, use_container_width=True)

# 5 Secciones
with tabs[4]:
    st.subheader("Secciones transversales")
    if sections.empty:
        st.info("Cargue secciones.")
    else:
        ids = list(sections["id_seccion"].dropna().unique())
        sid = st.selectbox("Sección", ids)
        g = sections[sections["id_seccion"] == sid]
        st.plotly_chart(plot_cross_section(g), use_container_width=True)
        st.dataframe(g, use_container_width=True)

# 6 Hidrología
with tabs[5]:
    st.subheader("Hidrología y caudales")
    mode = st.radio("Modo", ["Calculado por aplicación", "Manual desde hoja Caudales_Observados"], horizontal=True)
    if st.button("Calcular caudales de diseño"):
        try:
            flows = build_design_flows(cuenca, precip, manual_flows if mode.startswith("Manual") else None, mode=mode)
            st.session_state.design_flows = flows
            st.success("Caudales calculados/adoptados.")
        except Exception as exc:
            st.error(str(exc))
    if not st.session_state.design_flows.empty:
        st.plotly_chart(plot_hydrology(st.session_state.design_flows), use_container_width=True)
        st.dataframe(st.session_state.design_flows, use_container_width=True)

    st.markdown("### Caudales ingresados por km del cauce")
    st.caption("Permite representar un aporte lateral/tributario, una extracción o un caudal conocido en un km específico. Por defecto se asume que el km aumenta hacia aguas abajo.")
    default_flow_points = caudales_km.copy() if not caudales_km.empty else pd.DataFrame({
        "km": [0.50],
        "periodo_retorno": [100],
        "caudal_m3s": [0.0],
        "tipo_caudal": ["aporte_lateral"],
        "observaciones": ["Ejemplo: aporte tributario o caudal lateral desde este km hacia aguas abajo"],
    })
    edited_flows_km = st.data_editor(
        default_flow_points,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "tipo_caudal": st.column_config.SelectboxColumn(
                "tipo_caudal",
                options=["aporte_lateral", "extraccion", "caudal_control", "caudal_local"],
                help="aporte_lateral suma hacia aguas abajo; extraccion resta; caudal_control reemplaza desde ese km; caudal_local aplica solo a la sección más cercana.",
            ),
            "periodo_retorno": st.column_config.SelectboxColumn("periodo_retorno", options=RETURN_PERIODS),
        },
        key="caudales_km_editor",
    )
    km_downstream = st.checkbox("El km aumenta hacia aguas abajo", value=True)
    if st.button("Aplicar caudales por km al modelo hidráulico"):
        try:
            flow_points = normalize_flow_points(edited_flows_km)
            st.session_state.flow_points_km = flow_points
            if st.session_state.design_flows.empty:
                st.session_state.design_flows = build_design_flows(cuenca, precip, manual_flows if mode.startswith("Manual") else None, mode=mode)
            sec_kms = get_section_kms(sections, st.session_state.validation.section_status if st.session_state.validation else None)
            profile_q = build_flow_profile_by_km(st.session_state.design_flows, sec_kms, flow_points, km_increases_downstream=km_downstream)
            st.session_state.flow_profile_km = profile_q
            st.success("Perfil longitudinal de caudal por km generado. Se usará en la hidráulica 1D.")
        except Exception as exc:
            st.error(str(exc))
    if not st.session_state.flow_points_km.empty:
        st.write("Caudales por km normalizados")
        st.dataframe(st.session_state.flow_points_km, use_container_width=True)
    if not st.session_state.flow_profile_km.empty:
        st.write("Perfil de caudal aplicado por sección")
        st.dataframe(st.session_state.flow_profile_km, use_container_width=True)

# 7 Hidráulica
with tabs[6]:
    st.subheader("Hidráulica 1D — Modo dios hidráulico")
    st.caption("Motor conectado por secciones: Manning local o paso estándar por ecuación de energía, con condición de borde, pérdidas locales y profundidad crítica.")

    colA, colB, colC = st.columns(3)
    motor_hidraulico = colA.selectbox(
        "Motor hidráulico",
        ["1D paso estándar por energía (recomendado)", "Manning local por sección (rápido)"],
        index=0,
        help="El paso estándar conecta hidráulicamente las secciones. Manning local calcula cada sección de manera independiente."
    )
    default_n = colB.number_input("Manning n por defecto", min_value=0.015, max_value=0.20, value=0.04, step=0.005)
    km_downstream_solver = colC.checkbox("El km aumenta hacia aguas abajo", value=True, key="km_solver")

    with st.expander("Asistente hidráulico avanzado", expanded=True):
        c1, c2, c3 = st.columns(3)
        regimen_ui = c1.selectbox(
            "Régimen de cálculo",
            ["Automático", "Subcrítico", "Supercrítico"],
            index=0,
            help="Subcrítico calcula desde aguas abajo hacia aguas arriba. Supercrítico calcula desde aguas arriba hacia aguas abajo."
        )
        bc_tipo_ui = c2.selectbox(
            "Condición de borde por defecto",
            ["normal_depth", "known_wse", "critical_depth"],
            index=0,
            help="normal_depth usa pendiente normal; known_wse usa una cota de agua conocida; critical_depth usa tirante crítico."
        )
        bc_valor_ui = c3.number_input(
            "Valor condición borde",
            value=0.005 if bc_tipo_ui == "normal_depth" else 0.0,
            step=0.001,
            format="%.4f",
            help="Para normal_depth: pendiente de energía. Para known_wse: cota de agua en m. Para critical_depth se ignora."
        )
        c4, c5, c6 = st.columns(3)
        default_contr = c4.number_input("Coef. contracción", min_value=0.0, max_value=1.5, value=0.10, step=0.05)
        default_exp = c5.number_input("Coef. expansión", min_value=0.0, max_value=1.5, value=0.30, step=0.05)
        mostrar_comparacion = c6.checkbox("Comparar paso estándar vs Manning local", value=True)

        st.info("Si existen hojas Condiciones_Borde o Coeficientes_Hidraulicos, la app las usa y complementa estos valores por defecto.")
        if not boundary_conditions_df.empty:
            st.write("Condiciones de borde desde Excel")
            st.dataframe(boundary_conditions_df, use_container_width=True)
        if not coeffs_hidraulicos_df.empty:
            st.write("Coeficientes hidráulicos por tramo desde Excel")
            st.dataframe(coeffs_hidraulicos_df, use_container_width=True)

    if st.button("Calcular hidráulica conectada 1D", type="primary"):
        if st.session_state.validation is None:
            st.session_state.validation = validate_all(sheets)
        if st.session_state.design_flows.empty:
            st.session_state.design_flows = build_design_flows(cuenca, precip, None)
        try:
            flow_profile = st.session_state.flow_profile_km
            if flow_profile.empty and not caudales_km.empty:
                flow_points = normalize_flow_points(caudales_km)
                sec_kms = get_section_kms(sections, st.session_state.validation.section_status)
                flow_profile = build_flow_profile_by_km(st.session_state.design_flows, sec_kms, flow_points)
                st.session_state.flow_points_km = flow_points
                st.session_state.flow_profile_km = flow_profile

            if motor_hidraulico.startswith("1D paso"):
                # Condición de borde desde interfaz cuando no existe hoja, o como respaldo.
                bc_user = pd.DataFrame({
                    "tipo": [bc_tipo_ui],
                    "ubicacion": ["aguas_abajo" if regimen_ui != "Supercrítico" else "aguas_arriba"],
                    "valor": [bc_valor_ui],
                    "unidad": ["m" if bc_tipo_ui == "known_wse" else "pendiente"],
                    "observacion": ["Condición ingresada en interfaz Streamlit"]
                })
                bc_use = boundary_conditions_df if not boundary_conditions_df.empty else bc_user
                regimen_map = {"Automático": "auto", "Subcrítico": "subcritico", "Supercrítico": "supercritico"}
                hyd = compute_standard_step_profile(
                    sections=sections,
                    valid_status=st.session_state.validation.section_status,
                    profile=profile,
                    design_flows=st.session_state.design_flows,
                    default_n=default_n,
                    flow_profile=flow_profile,
                    boundary_conditions=bc_use,
                    coeffs=coeffs_hidraulicos_df,
                    regime_mode=regimen_map[regimen_ui],
                    km_increases_downstream=km_downstream_solver,
                    default_contraction=default_contr,
                    default_expansion=default_exp,
                )
                st.session_state.hyd = hyd
                st.session_state.hyd_engine = "paso_estandar_energia"
            else:
                hyd_local = compute_hydraulics_for_sections(sections, st.session_state.validation.section_status, profile, st.session_state.design_flows, default_n=default_n, flow_profile=flow_profile)
                hyd_energy = compute_energy_grade_line(hyd_local, profile)
                hyd_energy["metodo_hidraulico"] = "manning_local"
                hyd_energy["nivel_confianza_modelo"] = "Nivel 1: cálculo local por sección"
                st.session_state.hyd = hyd_energy
                st.session_state.hyd_engine = "manning_local"
            st.success("Hidráulica calculada con motor: " + st.session_state.hyd_engine)
        except Exception as exc:
            st.error(str(exc))

    if not st.session_state.hyd.empty:
        hyd = st.session_state.hyd
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Secciones calculadas", hyd["id_seccion"].nunique())
        k2.metric("Períodos", hyd["periodo_retorno"].nunique())
        k3.metric("Velocidad máxima", f"{pd.to_numeric(hyd['velocidad_m_s'], errors='coerce').max():.2f} m/s")
        k4.metric("Froude máximo", f"{pd.to_numeric(hyd['froude'], errors='coerce').max():.2f}")
        st.dataframe(hyd, use_container_width=True)
        st.write("Diagnóstico régimen / convergencia")
        diag = detect_mixed_regime(hyd)
        st.dataframe(diag, use_container_width=True)
        if "solver_ok" in hyd.columns and (~hyd["solver_ok"].astype(bool)).any():
            st.warning("Existen secciones donde el solver no cerró energía con tolerancia estricta. Revisar condición de borde, geometría, coeficientes o régimen.")
        if mostrar_comparacion and "diferencia_wse_paso_vs_local_m" in hyd.columns:
            diff = pd.to_numeric(hyd["diferencia_wse_paso_vs_local_m"], errors="coerce")
            st.info(f"Diferencia paso estándar vs Manning local: media {diff.mean():.2f} m, máxima absoluta {diff.abs().max():.2f} m.")

# 8 Perfiles hidráulicos
with tabs[7]:
    st.subheader("Perfiles hidráulicos")
    if st.session_state.hyd.empty:
        st.info("Calcule hidráulica primero.")
    else:
        periods = st.multiselect("Períodos a visualizar", RETURN_PERIODS, default=[10, 50, 100, 200])
        status = st.session_state.validation.section_status if st.session_state.validation else pd.DataFrame()
        st.plotly_chart(plot_longitudinal_profile(profile, status, st.session_state.hyd, periods), use_container_width=True)

# 9 Granulometría
with tabs[8]:
    st.subheader("Granulometría")
    if gran.empty:
        st.warning("No hay granulometría; se asumirá condición desfavorable preliminar.")
    else:
        st.dataframe(gran, use_container_width=True)
    if not sections.empty:
        kms = sorted(pd.to_numeric(sections["km"], errors="coerce").dropna().unique())
        st.write("Granulometría interpolada por km de secciones")
        st.dataframe(interpolate_granulometry(gran, kms), use_container_width=True)

# 10 Sedimentos
with tabs[9]:
    st.subheader("Transporte de sedimentos")
    duration = st.selectbox("Duración evento", [1, 3, 6, 12, 24, "Manual"], index=2)
    if duration == "Manual":
        duration_h = st.number_input("Duración manual (h)", min_value=0.1, value=6.0)
    else:
        duration_h = float(duration)
    if st.button("Calcular transporte de sedimentos"):
        sed = compute_sediment_transport(st.session_state.hyd, gran, duration_h)
        st.session_state.sed = sed
        st.session_state.routing = exner_balance(sed)
        st.success("Sedimentos calculados.")
    sed = st.session_state.get("sed", pd.DataFrame())
    if not sed.empty:
        st.dataframe(sed, use_container_width=True)
        st.write("Balance Exner simplificado")
        st.dataframe(st.session_state.get("routing", pd.DataFrame()), use_container_width=True)

# 11 Socavación
with tabs[10]:
    st.subheader("Socavación y depositación")
    obra = st.selectbox("Tipo de situación", ["cauce natural sin obra", "puente", "alcantarilla", "atravieso", "defensa fluvial", "bocatoma", "canalización"])
    st.info("Para obras, esta versión entrega tendencia general. Socavación local requiere datos geométricos detallados.")
    sed = st.session_state.get("sed", pd.DataFrame())
    if st.button("Calcular socavación/depositación"):
        scour, dep = compute_scour_deposition(st.session_state.hyd, sed, st.session_state.get("routing", pd.DataFrame()))
        st.session_state.scour = scour
        st.session_state.dep = dep
        st.success("Socavación y depositación calculadas.")
    if not st.session_state.get("scour", pd.DataFrame()).empty:
        st.dataframe(st.session_state.scour, use_container_width=True)
        st.dataframe(st.session_state.dep, use_container_width=True)

# 12 Visualización sección
with tabs[11]:
    st.subheader("Visualización hidráulica y socavación")
    if st.session_state.hyd.empty or sections.empty:
        st.info("Calcule hidráulica primero.")
    else:
        col1, col2 = st.columns(2)
        T = col1.selectbox("Período", RETURN_PERIODS, index=RETURN_PERIODS.index(100))
        ids = list(st.session_state.hyd["id_seccion"].dropna().unique())
        sid = col2.selectbox("Sección", ids, key="viz_sid")
        row = st.session_state.hyd[(st.session_state.hyd["periodo_retorno"] == T) & (st.session_state.hyd["id_seccion"] == sid)]
        if not row.empty:
            wse = float(row.iloc[0]["cota_agua_m"])
            scour_d = 0.0; dep_d = 0.0
            if not st.session_state.get("scour", pd.DataFrame()).empty:
                sr = st.session_state.scour[(st.session_state.scour["periodo_retorno"] == T) & (st.session_state.scour["id_seccion"] == sid)]
                if not sr.empty: scour_d = float(sr.iloc[0]["profundidad_socavacion_m"])
            if not st.session_state.get("dep", pd.DataFrame()).empty:
                dr = st.session_state.dep[(st.session_state.dep["periodo_retorno"] == T) & (st.session_state.dep["id_seccion"] == sid)]
                if not dr.empty: dep_d = float(dr.iloc[0]["profundidad_depositacion_m"])
            st.plotly_chart(plot_cross_section(sections[sections["id_seccion"] == sid], wse=wse, scour_depth=scour_d, deposition_depth=dep_d), use_container_width=True)
            st.dataframe(row, use_container_width=True)

# 13 Inundación
with tabs[12]:
    st.subheader("Inundación en planta")
    if st.session_state.hyd.empty:
        st.info("Calcule hidráulica primero.")
    elif "grid" not in st.session_state.terrain:
        st.info("Cargue/interpole terreno desde curvas KMZ o use DEM para generar grilla en una etapa SIG avanzada.")
    else:
        T = st.selectbox("Período para mapa de inundación", RETURN_PERIODS, index=RETURN_PERIODS.index(100), key="floodT")
        cell_area = st.number_input("Área aproximada de celda (m²)", min_value=1.0, value=900.0)
        gx, gy, gz = st.session_state.terrain["grid"]
        hp = st.session_state.hyd[st.session_state.hyd["periodo_retorno"] == T]
        wse = build_water_surface_grid(gx, gy, hp, axis_df if not axis_df.empty else None)
        depth = compute_depth_grid(wse, gz)
        mask = connectivity_filter(depth)
        depth = np.where(mask, depth, 0.0)
        st.session_state.terrain["depth"] = depth
        st.session_state.terrain["last_T"] = T
        summary = flood_summary(depth, cell_area)
        st.json(summary)
        st.plotly_chart(plot_raster_map(gx, gy, depth, f"Profundidad inundación T={T}", colorscale="Blues"), use_container_width=True)

# 14 Velocidad
with tabs[13]:
    st.subheader("Velocidad y zonas críticas")
    if "depth" not in st.session_state.terrain:
        st.info("Genere mapa de inundación primero.")
    else:
        slope = st.number_input("Pendiente de energía para mapa", min_value=0.0001, max_value=0.20, value=0.005, step=0.0005, format="%.4f")
        nmap = st.number_input("Manning n para planicie/cauce", min_value=0.015, max_value=0.20, value=0.05, step=0.005, key="nmap")
        cell_area_v = st.number_input("Área de celda para velocidad (m²)", min_value=1.0, value=900.0, key="cellv")
        depth = st.session_state.terrain["depth"]
        v = velocity_grid_from_depth(depth, slope=slope, n=nmap)
        cls = classify_velocity(v)
        critical = np.where(cls == 3, v, np.nan)
        st.session_state.terrain["velocity"] = v
        st.json(velocity_summary(v, depth, cell_area_v))
        st.plotly_chart(plot_raster_map(st.session_state.terrain["grid"][0], st.session_state.terrain["grid"][1], v, "Velocidad aproximada (m/s)", colorscale="Turbo"), use_container_width=True)
        st.plotly_chart(plot_raster_map(st.session_state.terrain["grid"][0], st.session_state.terrain["grid"][1], critical, "Zonas críticas por velocidad ≥ 3 m/s", colorscale="Reds"), use_container_width=True)

# 15 Resultados
with tabs[14]:
    st.subheader("Resultados consolidados")
    status = st.session_state.validation.section_status if st.session_state.validation else pd.DataFrame()
    results = {
        "Caudales_Diseño": st.session_state.design_flows,
        "Caudales_Km_Ingresados": st.session_state.flow_points_km,
        "Perfil_Caudal_Km": st.session_state.flow_profile_km,
        "Hidraulica_por_Seccion": st.session_state.hyd,
        "Transporte_Sedimentos": st.session_state.get("sed", pd.DataFrame()),
        "Balance_Exner": st.session_state.get("routing", pd.DataFrame()),
        "Socavacion": st.session_state.get("scour", pd.DataFrame()),
        "Depositacion": st.session_state.get("dep", pd.DataFrame()),
        "Secciones_Validas": status[status.get("estado", pd.Series(dtype=str)).eq("Válida")] if not status.empty else pd.DataFrame(),
        "Secciones_Descartadas": status[status.get("estado", pd.Series(dtype=str)).eq("Descartada")] if not status.empty else pd.DataFrame(),
    }
    for name, df in results.items():
        with st.expander(name, expanded=name in ["Caudales_Diseño", "Hidraulica_por_Seccion"]):
            st.dataframe(df, use_container_width=True)
    issues = run_technical_checks(st.session_state.design_flows, st.session_state.hyd)
    if issues:
        st.warning("Diagnóstico técnico: " + " | ".join(issues))
    else:
        st.success("Sin inconsistencias técnicas automáticas principales detectadas.")

# 16 Descargas
with tabs[15]:
    st.subheader("Descargas")
    status = st.session_state.validation.section_status if st.session_state.validation else pd.DataFrame()
    results = {
        "Caudales_Diseño": st.session_state.design_flows,
        "Caudales_Km_Ingresados": st.session_state.flow_points_km,
        "Perfil_Caudal_Km": st.session_state.flow_profile_km,
        "Hidraulica_por_Seccion": st.session_state.hyd,
        "Transporte_Sedimentos": st.session_state.get("sed", pd.DataFrame()),
        "Balance_Exner": st.session_state.get("routing", pd.DataFrame()),
        "Socavacion": st.session_state.get("scour", pd.DataFrame()),
        "Depositacion": st.session_state.get("dep", pd.DataFrame()),
        "Secciones_Validas": status[status.get("estado", pd.Series(dtype=str)).eq("Válida")] if not status.empty else pd.DataFrame(),
        "Secciones_Descartadas": status[status.get("estado", pd.Series(dtype=str)).eq("Descartada")] if not status.empty else pd.DataFrame(),
    }
    st.download_button("Descargar Excel de resultados", data=to_excel_bytes(results), file_name="resultados_hidrosed.xlsx")
    if not status.empty:
        kmz_path = export_sections_kmz(status, OUT_DIR / "secciones_validas_descartadas.kmz", axis_df if not axis_df.empty else None)
        st.download_button("Descargar KMZ secciones válidas/descartadas", data=kmz_path.read_bytes(), file_name=kmz_path.name)

# 17 Informe
with tabs[16]:
    st.subheader("Informe técnico")
    if st.button("Generar informe Word preliminar"):
        status = st.session_state.validation.section_status if st.session_state.validation else pd.DataFrame()
        results = {
            "Caudales_Diseño": st.session_state.design_flows,
            "Caudales_Km_Ingresados": st.session_state.flow_points_km,
            "Perfil_Caudal_Km": st.session_state.flow_profile_km,
            "Hidraulica_por_Seccion": st.session_state.hyd,
            "Transporte_Sedimentos": st.session_state.get("sed", pd.DataFrame()),
            "Socavacion": st.session_state.get("scour", pd.DataFrame()),
            "Depositacion": st.session_state.get("dep", pd.DataFrame()),
            "Secciones": status,
        }
        warnings = []
        if st.session_state.validation:
            warnings += st.session_state.validation.warnings
        warnings += run_technical_checks(st.session_state.design_flows, st.session_state.hyd)
        out = generate_word_report(OUT_DIR / "informe_tecnico_hidrosed.docx", results, warnings=warnings)
        st.success(f"Informe generado: {out}")
        st.download_button("Descargar informe", data=out.read_bytes(), file_name=out.name)
