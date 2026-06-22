from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.excel_io import load_excel, get_sheet
from modules.validation import validate_all
from modules.hydrology import build_design_flows
from modules.flow_profile import get_section_kms, build_flow_profile_by_km
from modules.hydraulics import compute_hydraulics_for_sections
from modules.hydraulic_solver_1d import compute_energy_grade_line, compute_standard_step_profile, detect_mixed_regime
from modules.sediment_transport import compute_sediment_transport
from modules.sediment_routing import exner_balance
from modules.scour import compute_scour_deposition
from modules.contour_kmz_reader import read_contour_kmz, apply_manual_elevations
from modules.terrain_processing import contours_to_grid
from modules.flood_mapping import build_water_surface_grid, compute_depth_grid, connectivity_filter, flood_summary
from modules.velocity_mapping import velocity_grid_from_depth, velocity_summary
from modules.model_diagnostics import run_technical_checks


def main():
    print('CORRIDA 1 - Estructural/imports: OK')
    xlsx = ROOT / 'data' / 'plantilla_entrada.xlsx'
    kmz = ROOT / 'data' / 'curvas_nivel_ejemplo.kmz'
    loaded = load_excel(xlsx)
    assert not loaded.missing_sheets, loaded.missing_sheets
    sheets = loaded.sheets
    report = validate_all(sheets)
    if report.errors:
        raise AssertionError(report.errors)
    profile = get_sheet(sheets, 'Perfil_Longitudinal')
    sections = get_sheet(sheets, 'Secciones')
    cuenca = get_sheet(sheets, 'Cuenca')
    precip = get_sheet(sheets, 'Precipitacion')
    gran = get_sheet(sheets, 'Granulometria')
    caudales_km = get_sheet(sheets, 'Caudales_Km')
    axis_df = get_sheet(sheets, 'Eje_Cauce')
    boundary = get_sheet(sheets, 'Condiciones_Borde')
    coeffs = get_sheet(sheets, 'Coeficientes_Hidraulicos')
    flows = build_design_flows(cuenca, precip)
    sec_kms = get_section_kms(sections, report.section_status)
    q_profile = build_flow_profile_by_km(flows, sec_kms, caudales_km)
    assert not q_profile.empty
    hyd0 = compute_hydraulics_for_sections(sections, report.section_status, profile, flows, flow_profile=q_profile)
    hyd = compute_standard_step_profile(sections, report.section_status, profile, flows, flow_profile=q_profile, boundary_conditions=boundary, coeffs=coeffs, regime_mode='auto')
    if hyd.empty:
        hyd = compute_energy_grade_line(hyd0, profile)
    diag = detect_mixed_regime(hyd)
    assert 'metodo_hidraulico' in hyd.columns
    assert 'tirante_critico_m' in hyd.columns
    assert 'residual_energia_m' in hyd.columns
    sed = compute_sediment_transport(hyd, gran, event_duration_h=6)
    routing = exner_balance(sed)
    scour, dep = compute_scour_deposition(hyd, sed, routing)
    assert not flows.empty and not hyd.empty and not sed.empty and not diag.empty
    assert 'caudal_base_diseno_m3s' in hyd.columns and 'observaciones_caudal_km' in hyd.columns
    print('CORRIDA 2 - Funcional plantilla/hidrología/hidráulica/sedimentos: OK')
    lines, pts = read_contour_kmz(kmz)
    pts2 = apply_manual_elevations(pts, lines)
    gx, gy, gz = contours_to_grid(pts2, resolution=0.0005)
    hp = hyd[hyd['periodo_retorno'] == 100]
    wse = build_water_surface_grid(gx, gy, hp, axis_df)
    depth = compute_depth_grid(wse, gz)
    mask = connectivity_filter(depth)
    depth = depth * mask
    fs = flood_summary(depth)
    v = velocity_grid_from_depth(depth)
    vs = velocity_summary(v, depth)
    issues = run_technical_checks(flows, hyd)
    # velocidades altas pueden ser advertencia, no falla, salvo no exista salida
    assert 'area_inundada_ha' in fs and 'velocidad_max_m_s' in vs
    print('CORRIDA 3 - Técnica monotonía/mapa inundación/velocidad: OK')
    if issues:
        print('ADVERTENCIAS TÉCNICAS DETECTADAS:')
        for issue in issues:
            print('-', issue)
    print('SELF CHECK COMPLETO')

if __name__ == '__main__':
    main()
