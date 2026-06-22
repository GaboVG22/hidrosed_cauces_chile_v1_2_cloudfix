"""Gráficos Plotly para la aplicación."""
from __future__ import annotations
import numpy as np
import pandas as pd
import plotly.graph_objects as go


def plot_longitudinal_profile(profile: pd.DataFrame, sections_status: pd.DataFrame | None = None, hyd_profile: pd.DataFrame | None = None, selected_periods=None):
    fig = go.Figure()
    if profile is not None and not profile.empty:
        p = profile.sort_values("km")
        x = p["km"] if "km" in p.columns else p["distancia_m"]
        fig.add_trace(go.Scatter(x=x, y=p["cota_fondo_m"], mode="lines+markers", name="Fondo cauce", line=dict(color="black", width=3)))
    if sections_status is not None and not sections_status.empty and profile is not None and not profile.empty:
        p = profile.sort_values("km")
        for estado, color in [("Válida", "blue"), ("Revisar manualmente", "orange"), ("Descartada", "red")]:
            ss = sections_status[sections_status["estado"] == estado]
            if not ss.empty:
                yvals = np.interp(ss["km"], p["km"], p["cota_fondo_m"])
                fig.add_trace(go.Scatter(x=ss["km"], y=yvals, mode="markers", name=f"Secciones {estado}", marker=dict(color=color, size=9)))
    if hyd_profile is not None and not hyd_profile.empty:
        periods = selected_periods or sorted(hyd_profile["periodo_retorno"].unique())
        for T in periods:
            h = hyd_profile[hyd_profile["periodo_retorno"] == T].sort_values("km")
            if not h.empty:
                fig.add_trace(go.Scatter(x=h["km"], y=h["cota_agua_m"], mode="lines+markers", name=f"Agua T={T}", line=dict(width=2)))
                if "energia_total_m" in h.columns:
                    fig.add_trace(go.Scatter(x=h["km"], y=h["energia_total_m"], mode="lines", name=f"Energía T={T}", line=dict(width=1, dash="dot")))
    fig.update_layout(title="Perfil longitudinal hidráulico", xaxis_title="km", yaxis_title="Cota (m)", legend=dict(orientation="h"), height=520)
    return fig


def plot_cross_section(section_df: pd.DataFrame, wse: float | None = None, scour_depth: float = 0.0, deposition_depth: float = 0.0, show_layers: bool = True):
    sec = section_df.sort_values("x_m")
    x, z = sec["x_m"], sec["z_m"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=z, mode="lines+markers", name="Sección original", line=dict(color="black", width=3)))
    if wse is not None and np.isfinite(wse):
        fig.add_trace(go.Scatter(x=[x.min(), x.max()], y=[wse, wse], mode="lines", name="Nivel de agua", line=dict(color="blue", width=2)))
        # área mojada rellena aproximada
        zfill = np.minimum(z, wse)
        wet_mask = z < wse
        if wet_mask.any():
            fig.add_trace(go.Scatter(x=list(x)+list(x[::-1]), y=list(zfill)+[wse]*len(x), fill="toself", fillcolor="rgba(80,150,255,0.35)", line=dict(color="rgba(0,0,0,0)"), name="Área mojada"))
    if scour_depth > 0:
        fig.add_trace(go.Scatter(x=x, y=z - scour_depth, mode="lines", name="Fondo socavado", line=dict(color="red", width=3, dash="dash")))
    if deposition_depth > 0:
        fig.add_trace(go.Scatter(x=x, y=z + deposition_depth, mode="lines", name="Fondo con depositación", line=dict(color="green", width=3, dash="dot")))
    fig.update_layout(title="Sección transversal", xaxis_title="Distancia transversal x (m)", yaxis_title="Cota z (m)", height=500, legend=dict(orientation="h"))
    return fig


def plot_hydrology(design_flows: pd.DataFrame):
    fig = go.Figure()
    if design_flows is not None and not design_flows.empty:
        fig.add_trace(go.Scatter(x=design_flows["periodo_retorno"], y=design_flows["caudal_calculado_m3s"], mode="lines+markers", name="Q calculado"))
        fig.add_trace(go.Scatter(x=design_flows["periodo_retorno"], y=design_flows["caudal_adoptado_m3s"], mode="lines+markers", name="Q adoptado"))
    fig.update_layout(title="Caudal vs período de retorno", xaxis_title="Período de retorno (años)", yaxis_title="Caudal (m³/s)", height=420)
    return fig


def plot_raster_map(gx, gy, grid, title="Mapa", colorscale="Blues"):
    fig = go.Figure(go.Heatmap(x=gx[0, :], y=gy[:, 0], z=grid, colorscale=colorscale, colorbar=dict(title="valor")))
    fig.update_layout(title=title, xaxis_title="Longitud", yaxis_title="Latitud", height=560)
    return fig
