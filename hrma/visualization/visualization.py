import base64
import functools
import math

import plotly.graph_objects as go
import numpy as np
import json
from scipy.interpolate import griddata
from typing import Dict, List, Tuple, Optional

from hrma.engines.nozzle_design import sample_nozzle_inner_contour

# ---------------------------------------------------------------------------
# Plotly JSON çıkışı — binary (bdata) kodlamasını SÖKEN tek kapı
# ---------------------------------------------------------------------------
# plotly 6.0.1, fig.to_json()/to_dict() içinde numpy dizilerini base64
# "bdata" bloklarına çevirir. Uygulamanın paketlediği vendor plotly.js
# 1.58.5 bu formatı ÇÖZEMEZ → seri boş çizilir ("Regression Rate & Port
# Growth boş" bugının kökü, 2026-07-19). Bu yüzden her figür JSON'u
# _fig_json() üzerinden geçirilir: bdata blokları listeye açılır, numpy
# skalerleri Python tiplerine döner, NaN/Inf null olur (plotly.js boşluk
# olarak yorumlar).
_BDATA_DTYPES = {
    'f8': '<f8', 'f4': '<f4', 'i1': '<i1', 'u1': '<u1', 'i2': '<i2',
    'u2': '<u2', 'i4': '<i4', 'u4': '<u4', 'i8': '<i8', 'u8': '<u8',
}


def _decode_bdata(obj):
    """{'dtype','bdata'[,'shape']} bloğunu numpy dizisine geri çevirir."""
    arr = np.frombuffer(base64.b64decode(obj['bdata']),
                        dtype=_BDATA_DTYPES[obj['dtype']])
    shape = obj.get('shape')
    if shape:
        dims = [int(s) for s in str(shape).replace(' ', '').split(',') if s]
        arr = arr.reshape(dims)
    return arr


def _to_plain(obj):
    """Figür sözlüğünü saf Python (JSON-güvenli) tiplere indirger."""
    if isinstance(obj, dict):
        if 'bdata' in obj and obj.get('dtype') in _BDATA_DTYPES:
            return _to_plain(_decode_bdata(obj))
        return {k: _to_plain(v) for k, v in obj.items()}
    if isinstance(obj, np.ndarray):
        return [_to_plain(v) for v in obj.tolist()]
    if isinstance(obj, np.generic):
        return _to_plain(obj.item())
    if isinstance(obj, (list, tuple)):
        return [_to_plain(v) for v in obj]
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    return obj


def _fig_json(fig):
    """fig.to_json() yerine kullanılır: bdata'sız, saf JSON string."""
    return json.dumps(_to_plain(fig.to_dict()))

# ---------------------------------------------------------------------------
# Ortak koyu tema paleti — theme.css / plotly_dark.js COLORWAY ile hizalı.
# Kural: seri/çizgi renkleri bu sıradan atanır; kırmızı-yeşil-sarı YALNIZ
# anlamsal (güvenli/uyarı/tehlike) kullanım içindir (kitsch kuralı).
# advanced_results.py de bu sabitleri import eder — tek kaynak.
# ---------------------------------------------------------------------------
PALETTE = ['#00e5ff', '#ff8c33', '#2dd4a8', '#ff5d73',
           '#c792ea', '#ffd166', '#7cc4ff', '#f78fb3']
COL_SAFE = '#2dd4a8'      # güvenli / hedefte
COL_WARN = '#ffd166'      # uyarı (hafif)
COL_WARN_HI = '#ff8c33'   # uyarı (kuvvetli)
COL_DANGER = '#ff5d73'    # tehlike / limit aşımı
STRUCT_INK = '#d7e3ee'    # yapı çizgileri (koyu zeminde okunur mürekkep)
STRUCT_DIM = '#5f7c8c'    # ikincil çizgiler (eksen/ölçü yardımcıları)
# Sıralı büyüklükler için tek aileli cyan skala; sıcak aile yalnız ısı akısı
# gibi fiziksel olarak "sıcak" büyüklüklerde kullanılır (yine tek aile)
SEQ_CYAN = [[0.0, '#0a1322'], [0.5, '#0a7c8f'], [1.0, '#00e5ff']]
SEQ_WARM = [[0.0, '#1a0e08'], [0.5, '#8f4a0a'], [1.0, '#ff8c33']]
SEQ_BROWN = [[0.0, '#3a2415'], [1.0, '#c98a55']]  # yakıt grain malzemesi
# Kutuplu (diverging) büyüklükler: tehlike ↔ nötr koyu ↔ cyan
DIV_SCALE = [[0.0, '#ff5d73'], [0.5, '#0a1322'], [1.0, '#00e5ff']]
# Gauge step zeminleri — yarı saydam, gövdeyi bastırmayan
STEP_DIM = 'rgba(125, 151, 165, 0.15)'
STEP_SAFE = 'rgba(45, 212, 168, 0.25)'
STEP_WARN = 'rgba(255, 209, 102, 0.25)'
STEP_DANGER = 'rgba(255, 93, 115, 0.25)'
# Koyu panel zeminleri (plotly_dark.js ile aynı değerler)
DARK_PLOT_BG = 'rgba(8, 16, 28, 0.35)'
DARK_PAPER_BG = 'rgba(0,0,0,0)'
DARK_LEGEND_BG = 'rgba(6, 13, 24, 0.7)'
DARK_LEGEND_BORDER = 'rgba(0, 229, 255, 0.2)'

# ---------------------------------------------------------------------------
# Analiz Güvertesi figürleri — çözücüye bağlı sabitler (2026-07-19 uydurma
# denetimi). Bu blok ÖNCE uydurma şekil fonksiyonlarının içine gömülü olan
# katsayıların yerini alır: artık ya gerçek çözücü çağrılır ya da eksik girdi
# figürün üstünde AÇIKÇA "assumed" olarak listelenir. Sessiz varsayım yok.
# ---------------------------------------------------------------------------
#: Pc x O/F performans yüzeyinin ızgara boyutu (her düğüm = bir gerçek
#: CombustionAnalyzer.analyze_combustion çağrısı ~28 ms; 7x7 = 49 çağrı).
PERF_SURFACE_GRID_N = 7
#: Yüzey tarama aralıkları (bar / O-F kütle oranı). Panelin eski görsel
#: kapsamıyla aynı; tek fark artık her düğümde denge GERÇEKTEN çözülüyor.
PERF_SURFACE_PC_RANGE_BAR = (10.0, 100.0)
PERF_SURFACE_OF_RANGE = (1.0, 6.0)
#: Tarama için propellant kimliği verilmediğinde kullanılan referans çift.
#: Figür alt başlığında AÇIKÇA yazılır (kullanıcı kendi yakıtını sandığında
#: yanılmasın diye) — app.py bu alanları geçirdiğinde otomatik değişir.
PERF_SURFACE_DEFAULT_FUEL = 'htpb'
PERF_SURFACE_DEFAULT_OXIDIZER = 'N2O'

#: Quasi-1D Mach konturu: gaz özellikleri figüre geçirilmezse kullanılan
#: referans oda hâli. Sutton & Biblarz 9. baskı Bölüm 3'te tipik hibrit/sıvı
#: yanma gazı bandı (gamma 1.15-1.25, MW 20-28 g/mol). Bu değerler figürün
#: alt başlığında "assumed" olarak listelenir.
NOZZLE_FIG_DEFAULT_GAMMA = 1.20
NOZZLE_FIG_DEFAULT_MW = 24.0            # g/mol
NOZZLE_FIG_DEFAULT_PC_BAR = 20.0
NOZZLE_FIG_DEFAULT_TC_K = 3000.0
NOZZLE_FIG_AMBIENT_PA = 101325.0        # deniz seviyesi (ISA)
NOZZLE_FIG_N_STATIONS = 45
#: Kontur ızgarasının radyal düğüm sayısı (quasi-1D: M yarıçap boyunca
#: SABİT; ızgara yalnız duvar içini boyamak için var).
NOZZLE_FIG_N_RADIAL = 31

#: Cidar ısı akısı figürü: Bartz profili için istasyon sayısı ve zaman
#: ekseni düğüm sayısı (yığın-ısıl kütle geçici çözümü).
HEATFLUX_FIG_N_STATIONS = 40
HEATFLUX_FIG_N_TIME = 40
#: Geçici cidar çözümü için varsayılan malzeme/kalınlık (HeatTransferAnalyzer
#: malzeme veritabanı anahtarı). Figürde "assumed" listesine yazılır.
HEATFLUX_FIG_DEFAULT_MATERIAL = 'steel'
HEATFLUX_FIG_DEFAULT_WALL_M = 0.005
HEATFLUX_FIG_DEFAULT_COOLING = 'natural'


def _style_subplot_titles(fig, size=13, color='#cfe8f2'):
    """make_subplots başlıklarını küçült — 16px varsayılan başlıklar
    kalabalık panolarda eksen etiketleriyle iç içe geçiyordu.
    make_subplots'tan HEMEN sonra çağrılmalı (başlıklar annotation'dır;
    sonradan eklenen annotation'lara dokunulmasın)."""
    for ann in fig.layout.annotations:
        ann.font = dict(size=size, color=color)


def _legend_below(y=-0.12):
    """Kalabalık legend'ı grafiğin altına yatay dizer (çakışma önleme)."""
    return dict(orientation='h', yanchor='top', y=y, x=0.5, xanchor='center',
                bgcolor=DARK_LEGEND_BG, bordercolor=DARK_LEGEND_BORDER)


def _match_time_axes(fig, cells):
    """Aynı zaman eksenini paylaşan alt grafiklerde senkron zoom kurar.

    cells: [(row, col), ...] — ilk hücrenin x ekseni referans alınır,
    kalanlara ``matches`` bağlanır (plotly.js 1.45+ / paketli 1.58.5
    destekler, dağıtımdaki bundle üzerinde teyit edildi 2026-07-21).
    Tek hücre verilirse hiçbir şey yapılmaz. Eksen kimliği subplot
    ızgarasından türetilir; indicator/domain hücreleri numaralandırmayı
    kaydırdığı için sabit 'x2' benzeri adlar YAZILMAZ.
    """
    if not cells or len(cells) < 2:
        return
    try:
        ref_axis = fig.get_subplot(row=cells[0][0], col=cells[0][1]).xaxis
        ref = ref_axis.plotly_name.replace('axis', '')  # 'xaxis3' -> 'x3'
    except Exception:
        return
    for r, c in cells[1:]:
        fig.update_xaxes(matches=ref, row=r, col=c)


def create_motor_plot(motor_data):
    """Create professional motor cross-section plot"""
    
    # Extract dimensions with safe defaults
    L = motor_data.get('chamber_length', 0.3)  # Default 300mm
    D_ch = motor_data.get('chamber_diameter', 0.1)  # Default 100mm
    D_port_i = motor_data.get('port_diameter_initial', 0.03)  # Default 30mm
    D_port_f = motor_data.get('port_diameter_final', 0.05)  # Default 50mm
    d_t = motor_data.get('throat_diameter', 0.02)  # Default 20mm
    d_e = motor_data.get('exit_diameter', 0.08)  # Default 80mm
    
    # Create figure
    fig = go.Figure()
    
    # Convert to mm for better readability
    L_mm = L * 1000
    D_ch_mm = D_ch * 1000
    D_port_i_mm = D_port_i * 1000
    D_port_f_mm = D_port_f * 1000
    d_t_mm = d_t * 1000
    d_e_mm = d_e * 1000
    
    # Calculate schematic nozzle geometry.
    # DIKKAT (2026-07-19 uydurma denetimi): bu FALLBACK cizimdir. Ana yol
    # create_improved_motor_cross_section() olup gercek nozul konturunu
    # (sample_nozzle_inner_contour) kullanir; buraya yalnizca o yol istisna
    # atinca dusulur. Nozul boyu burada cozucuden DEGIL, cikis capindan
    # turetilen bir cizim oranidir — figure gorunur uyari eklenir.
    nozzle_length = max(d_e_mm * 1.5, 80)  # schematic proportion, not solved
    
    # Chamber walls (upper and lower)
    chamber_wall_upper_x = [-L_mm/2, L_mm/2]
    chamber_wall_upper_y = [D_ch_mm/2, D_ch_mm/2]
    chamber_wall_lower_x = [-L_mm/2, L_mm/2]
    chamber_wall_lower_y = [-D_ch_mm/2, -D_ch_mm/2]
    
    fig.add_trace(go.Scatter(
        x=chamber_wall_upper_x, y=chamber_wall_upper_y,
        mode='lines',
        line=dict(color=STRUCT_INK, width=4),
        name='Chamber Wall',
        showlegend=False
    ))
    
    fig.add_trace(go.Scatter(
        x=chamber_wall_lower_x, y=chamber_wall_lower_y,
        mode='lines',
        line=dict(color=STRUCT_INK, width=4),
        name='Chamber Wall',
        showlegend=False
    ))
    
    # Head end wall
    fig.add_trace(go.Scatter(
        x=[-L_mm/2, -L_mm/2],
        y=[-D_ch_mm/2, D_ch_mm/2],
        mode='lines',
        line=dict(color=STRUCT_INK, width=4),
        name='Head End',
        showlegend=False
    ))
    
    # Fuel grain - simple and clean design
    grain_length = L_mm * 0.8
    case_thickness = max(8, D_ch_mm * 0.08)  # Realistic case thickness
    
    # Fuel grain geometry
    grain_outer_radius = D_ch_mm/2 - case_thickness
    port_radius = D_port_i_mm/2
    
    # Grain boundaries
    grain_start = -grain_length/2
    grain_end = grain_length/2
    
    # Upper fuel grain (rectangle approximation for clarity)
    fig.add_trace(go.Scatter(
        x=[grain_start, grain_end, grain_end, grain_start, grain_start],
        y=[port_radius, port_radius, grain_outer_radius, grain_outer_radius, port_radius],
        fill='toself',
        fillcolor='rgba(178, 116, 68, 0.9)',
        mode='lines',
        line=dict(color='#c98a55', width=3),
        name='Fuel Grain',
        hovertemplate=f'Fuel Grain<br>Length: {grain_length:.1f} mm<br>Thickness: {grain_outer_radius-port_radius:.1f} mm<br>Port: {D_port_i_mm:.1f} mm'
    ))
    
    # Lower fuel grain
    fig.add_trace(go.Scatter(
        x=[grain_start, grain_end, grain_end, grain_start, grain_start],
        y=[-port_radius, -port_radius, -grain_outer_radius, -grain_outer_radius, -port_radius],
        fill='toself',
        fillcolor='rgba(178, 116, 68, 0.9)',
        mode='lines',
        line=dict(color='#c98a55', width=3),
        showlegend=False,
        hoverinfo='skip'
    ))
    
    # Final port outline (dashed) - simple lines
    final_port_radius = D_port_f_mm/2
    
    fig.add_trace(go.Scatter(
        x=[grain_start, grain_end],
        y=[final_port_radius, final_port_radius],
        mode='lines',
        line=dict(color=COL_DANGER, width=3, dash='dash'),
        name='Port (Final)',
        hovertemplate=f'Final Port: {D_port_f_mm:.1f} mm diameter'
    ))
    
    fig.add_trace(go.Scatter(
        x=[grain_start, grain_end],
        y=[-final_port_radius, -final_port_radius],
        mode='lines',
        line=dict(color=COL_DANGER, width=3, dash='dash'),
        showlegend=False,
        hoverinfo='skip'
    ))
    
    # Nozzle geometry
    nozzle_start_x = L_mm/2
    nozzle_end_x = nozzle_start_x + nozzle_length
    
    # Convergent section (chamber to throat)
    conv_length = nozzle_length * 0.3
    conv_x = np.linspace(nozzle_start_x, nozzle_start_x + conv_length, 30)
    conv_y_upper = D_ch_mm/2 - (D_ch_mm/2 - d_t_mm/2) * ((conv_x - nozzle_start_x) / conv_length)**1.5
    conv_y_lower = -conv_y_upper
    
    # Divergent section (throat to exit) - bell profile
    div_length = nozzle_length * 0.7
    div_x = np.linspace(nozzle_start_x + conv_length, nozzle_end_x, 50)
    div_progress = (div_x - (nozzle_start_x + conv_length)) / div_length
    div_y_upper = d_t_mm/2 + (d_e_mm/2 - d_t_mm/2) * div_progress**0.7
    div_y_lower = -div_y_upper
    
    # Complete nozzle contour
    nozzle_x_complete = np.concatenate([conv_x, div_x, div_x[::-1], conv_x[::-1]])
    nozzle_y_complete = np.concatenate([conv_y_upper, div_y_upper, div_y_lower[::-1], conv_y_lower[::-1]])
    
    fig.add_trace(go.Scatter(
        x=nozzle_x_complete, y=nozzle_y_complete,
        fill='toself',
        fillcolor='rgba(160, 160, 160, 0.8)',
        mode='lines',
        line=dict(color=STRUCT_INK, width=3),
        name='Nozzle',
        hovertemplate='Nozzle<br>Throat: %.1f mm<br>Exit: %.1f mm<br>Expansion Ratio: %.1f' % 
                     (d_t_mm, d_e_mm, motor_data.get('expansion_ratio', d_e_mm**2/d_t_mm**2))
    ))
    
    # Add throat line indicator
    throat_x = nozzle_start_x + conv_length
    fig.add_trace(go.Scatter(
        x=[throat_x, throat_x],
        y=[-d_t_mm/2, d_t_mm/2],
        mode='lines',
        line=dict(color=COL_WARN_HI, width=3),
        name='Throat',
        hovertemplate='Throat Location<br>Diameter: %.2f mm' % d_t_mm
    ))
    
    # Add centerline
    total_length = nozzle_end_x - (-L_mm/2)
    fig.add_trace(go.Scatter(
        x=[-L_mm/2, nozzle_end_x],
        y=[0, 0],
        mode='lines',
        line=dict(color=STRUCT_DIM, width=1, dash='dot'),
        name='Centerline',
        showlegend=False
    ))
    
    # Get nozzle angles from motor data
    convergent_angle = motor_data.get('convergent_angle', 15.0)  # degrees
    divergent_angle = motor_data.get('divergent_angle', 12.0)   # degrees
    expansion_ratio = (d_e_mm / d_t_mm) ** 2
    
    # Add angle indicator lines with better visibility
    # Convergent angle line and arc
    conv_mid_x = nozzle_start_x + conv_length * 0.5
    conv_mid_y = D_ch_mm/2 - (D_ch_mm/2 - d_t_mm/2) * 0.5
    angle_line_length = 40  # mm - increased for better visibility
    
    conv_angle_rad = np.radians(convergent_angle)
    conv_angle_end_x = conv_mid_x + angle_line_length * np.cos(np.pi - conv_angle_rad)
    conv_angle_end_y = conv_mid_y + angle_line_length * np.sin(np.pi - conv_angle_rad)
    
    # Add angle arc for convergent section
    arc_angles = np.linspace(np.pi, np.pi - conv_angle_rad, 20)
    arc_radius = 25
    arc_x = conv_mid_x + arc_radius * np.cos(arc_angles)
    arc_y = conv_mid_y + arc_radius * np.sin(arc_angles)
    
    fig.add_trace(go.Scatter(
        x=arc_x,
        y=arc_y,
        mode='lines',
        line=dict(color=COL_WARN_HI, width=2),
        name=f'Convergent {convergent_angle}°',
        showlegend=True
    ))
    
    fig.add_trace(go.Scatter(
        x=[conv_mid_x, conv_angle_end_x],
        y=[conv_mid_y, conv_angle_end_y],
        mode='lines',
        line=dict(color=COL_WARN_HI, width=3, dash='dot'),
        name=f'Conv. Angle {convergent_angle}°',
        showlegend=False
    ))
    
    # Divergent angle line and arc
    div_mid_x = throat_x + (nozzle_end_x - throat_x) * 0.5
    div_progress_mid = (div_mid_x - throat_x) / div_length
    div_mid_y = d_t_mm/2 + (d_e_mm/2 - d_t_mm/2) * div_progress_mid**0.7
    
    div_angle_rad = np.radians(divergent_angle)
    div_angle_end_x = div_mid_x + angle_line_length * np.cos(div_angle_rad)
    div_angle_end_y = div_mid_y + angle_line_length * np.sin(div_angle_rad)
    
    # Add angle arc for divergent section
    arc_angles_div = np.linspace(0, div_angle_rad, 20)
    arc_x_div = div_mid_x + arc_radius * np.cos(arc_angles_div)
    arc_y_div = div_mid_y + arc_radius * np.sin(arc_angles_div)
    
    fig.add_trace(go.Scatter(
        x=arc_x_div,
        y=arc_y_div,
        mode='lines',
        line=dict(color='#2dd4a8', width=2),
        name=f'Divergent {divergent_angle}°',
        showlegend=True
    ))
    
    fig.add_trace(go.Scatter(
        x=[div_mid_x, div_angle_end_x],
        y=[div_mid_y, div_angle_end_y],
        mode='lines',
        line=dict(color='#2dd4a8', width=3, dash='dot'),
        name=f'Div. Angle {divergent_angle}°',
        showlegend=False
    ))

    # Add dimension annotations
    annotations = [
        dict(x=0, y=D_ch_mm/2 + 20, text=f'L = {L_mm:.1f} mm', 
             showarrow=False, font=dict(size=12)),
        dict(x=-L_mm/2 - 40, y=0, text=f'D = {D_ch_mm:.1f} mm', 
             showarrow=False, font=dict(size=12), textangle=90),
        dict(x=throat_x, y=-d_t_mm/2 - 30, text=f'dt = {d_t_mm:.2f} mm',
             showarrow=False, font=dict(size=10)),
        dict(x=nozzle_end_x, y=-d_e_mm/2 - 30, text=f'de = {d_e_mm:.1f} mm',
             showarrow=False, font=dict(size=10)),
        # Add angle annotations with larger text
        dict(x=conv_mid_x + 15, y=conv_mid_y + 10, text=f'α = {convergent_angle}°',
             showarrow=True, arrowhead=2, ax=0, ay=-30,
             font=dict(size=14, color='#ff8c33', family='Inter, sans-serif')),
        dict(x=div_mid_x + 15, y=div_mid_y + 10, text=f'β = {divergent_angle}°',
             showarrow=True, arrowhead=2, ax=0, ay=-30,
             font=dict(size=14, color='#2dd4a8', family='Inter, sans-serif')),
        # Add expansion ratio
        dict(x=(throat_x + nozzle_end_x) / 2, y=D_ch_mm/2 + 40, text=f'ε = {expansion_ratio:.1f}',
             showarrow=False, font=dict(size=11, color='#c792ea'))
    ]
    
    # Clean motor layout with improved sizing
    fig.update_layout(
        title=dict(
            text='Hybrid Rocket Motor - Axial Cross-Section View',
            x=0.5,
            font=dict(size=18, family='Arial', color=STRUCT_INK)
        ),
        xaxis=dict(
            title='Length (mm)',
            showgrid=True,
            gridcolor='rgba(128,128,128,0.2)',
            zeroline=True,
            zerolinecolor='gray',
            zerolinewidth=2,
            tickfont=dict(size=12)
        ),
        yaxis=dict(
            title='Radius (mm)',
            showgrid=True,
            gridcolor='rgba(128,128,128,0.2)',
            zeroline=True,
            zerolinecolor='gray',
            zerolinewidth=2,
            scaleanchor='x',
            scaleratio=0.5,
            tickfont=dict(size=12)
        ),
        showlegend=True,
        legend=dict(
            x=0.02, 
            y=0.98,
            bgcolor='rgba(255,255,255,0.9)',
            bordercolor=STRUCT_INK,
            borderwidth=1
        ),
        hovermode='closest',
        # Sabit width=1200 dar pencerede taşma/üst üste binme yaratıyordu;
        # responsive konteynerde autosize + sabit yükseklik yeterli
        autosize=True,
        height=600,
        plot_bgcolor='white',
        annotations=annotations,
        # b: 80 -> 125, alttaki yedek-şema uyarısına yer açmak için
        margin=dict(t=80, b=125, l=100, r=60)
    )
    # Uyarı BAŞLIK BANDINA değil çizim alanının ALTINA basılır (2026-07-23).
    # Eski hâli x=0.5, y=1.06, yref='paper' idi: t=80 ve height=600 ile çizim
    # alanı ~440 px, yani annotation çizim alanının yalnız ~26 px üstünde
    # kalıyor ve aynı 80 px'lik bantta ortalanmış 18 px'lik başlıkla üst üste
    # biniyordu. Alt kenar kalıbı bu dosyada zaten kullanılıyor (y=-0.14/-0.06
    # emsalleri). Metin ayrıca iki satıra bölündü: Plotly annotation'ı width
    # verilmedikçe satır kaydırmaz, ~130 karakterlik tek satır dar konteynerde
    # yatay olarak taşıyordu.
    fig.add_annotation(
        x=0.0, y=-0.20, xref='paper', yref='paper', xanchor='left',
        showarrow=False, align='left',
        text=('Fallback schematic — the solver nozzle contour was not '
              'available for this run;<br>nozzle proportions are drawn, '
              'not computed.'),
        font=dict(size=11, color=COL_WARN_HI))

    return _fig_json(fig)

def create_injector_plot(injector_data, injector_type):
    """Create professional injector visualization (legacy fallback path)."""

    fig = go.Figure()

    # Tip takma adları kanonik üç çizim dalına indirgenir: impingement delik
    # deseni olarak (showerhead), koaksiyel eş merkezli kesit olarak (pintle)
    # çizilir. Aksi halde bilinmeyen tip UnboundLocalError'a düşüyordu.
    injector_type = INJECTOR_TYPE_ALIASES.get(str(injector_type).lower(),
                                              'showerhead')
    if injector_type == 'impingement':
        injector_type = 'showerhead'
    elif injector_type == 'coaxial':
        injector_type = 'pintle'

    if injector_type == 'showerhead':
        # Create professional showerhead pattern
        n_holes = injector_data['n_holes']
        d_h_mm = injector_data['hole_diameter']  # Keep in mm
        
        # Simplified plate design — FALLBACK yol (ana yol
        # create_improved_injector_design). Plaka yaricapi cozucuden gelmez;
        # figure gorunur uyari eklenir (2026-07-19 uydurma denetimi).
        plate_radius_mm = 60  # schematic outline, not a reported dimension
        
        # Simple hole pattern - hexagonal close-packed or circular rings
        hole_positions_x = []
        hole_positions_y = []
        
        if n_holes == 1:
            # Single center hole
            hole_positions_x = [0]
            hole_positions_y = [0]
        elif n_holes <= 7:
            # Center + ring pattern
            hole_positions_x = [0]
            hole_positions_y = [0]
            
            remaining = n_holes - 1
            if remaining > 0:
                ring_radius = 20
                angles = np.linspace(0, 2*np.pi, remaining, endpoint=False)
                hole_positions_x.extend(ring_radius * np.cos(angles))
                hole_positions_y.extend(ring_radius * np.sin(angles))
        else:
            # Multiple rings
            holes_placed = 0
            ring = 0
            
            while holes_placed < n_holes:
                if ring == 0:
                    # Center hole
                    hole_positions_x.append(0)
                    hole_positions_y.append(0)
                    holes_placed += 1
                else:
                    # Ring holes
                    ring_radius = ring * 15  # 15mm spacing
                    holes_in_ring = min(6 * ring, n_holes - holes_placed)
                    
                    angles = np.linspace(0, 2*np.pi, holes_in_ring, endpoint=False)
                    hole_positions_x.extend(ring_radius * np.cos(angles))
                    hole_positions_y.extend(ring_radius * np.sin(angles))
                    holes_placed += holes_in_ring
                
                ring += 1
        
        # Draw all holes at once
        fig.add_trace(go.Scatter(
            x=hole_positions_x,
            y=hole_positions_y,
            mode='markers',
            marker=dict(
                size=max(12, min(20, d_h_mm * 8)), 
                color='lightblue', 
                # v2.5.5: darkblue → palet (JS COLOR_FIX ile aynı ton)
                line=dict(color=PALETTE[6], width=2),
                symbol='circle'
            ),
            name=f'Injection Holes ({n_holes})',
            hovertemplate=f'Injection Hole<br>Diameter: {d_h_mm:.2f} mm<br>Total Holes: {n_holes}<br>Total Area: {n_holes * np.pi * (d_h_mm/2)**2:.2f} mm²'
        ))
        
        # Simple plate boundary
        theta = np.linspace(0, 2*np.pi, 100)
        
        fig.add_trace(go.Scatter(
            x=plate_radius_mm * np.cos(theta),
            y=plate_radius_mm * np.sin(theta),
            mode='lines',
            line=dict(color=STRUCT_INK, width=4),
            name='Injector Plate',
            hovertemplate=f'Plate Diameter: {plate_radius_mm*2:.1f} mm'
        ))
        
        title = f'Showerhead Injector Design'
        subtitle = f'{n_holes} holes × ⌀{d_h_mm:.2f} mm | Total Area: {n_holes * np.pi * (d_h_mm/2)**2:.1f} mm²'
        
    elif injector_type == 'pintle':
        # Professional pintle injector cross-section with proper dimensions
        D_outer_mm = injector_data['outer_diameter']  # Keep in mm
        D_pintle_mm = injector_data['pintle_diameter']  # Keep in mm
        gap_mm = injector_data['gap']  # Keep in mm
        
        theta = np.linspace(0, 2*np.pi, 100)
        
        # Outer body with realistic appearance
        fig.add_trace(go.Scatter(
            x=D_outer_mm/2 * np.cos(theta),
            y=D_outer_mm/2 * np.sin(theta),
            fill='toself',
            fillcolor='rgba(160, 160, 160, 0.7)',
            mode='lines',
            line=dict(color=STRUCT_INK, width=4),
            name='Outer Body',
            hovertemplate=f'Outer Body<br>Diameter: {D_outer_mm:.1f} mm<br>Material: Stainless Steel'
        ))
        
        # Inner flow annulus
        inner_radius = (D_outer_mm - gap_mm) / 2
        fig.add_trace(go.Scatter(
            x=inner_radius * np.cos(theta),
            y=inner_radius * np.sin(theta),
            fill='toself',
            fillcolor='rgba(173, 216, 230, 0.4)',
            mode='lines',
            line=dict(color='#00e5ff', width=2, dash='dot'),
            name='Flow Annulus',
            hovertemplate=f'Flow Annulus<br>Gap: {gap_mm:.2f} mm<br>Flow Area: {np.pi * ((D_outer_mm/2)**2 - inner_radius**2):.1f} mm²'
        ))
        
        # Pintle with professional appearance
        fig.add_trace(go.Scatter(
            x=D_pintle_mm/2 * np.cos(theta),
            y=D_pintle_mm/2 * np.sin(theta),
            fill='toself',
            fillcolor='rgba(64, 64, 64, 0.9)',
            mode='lines',
            line=dict(color=STRUCT_INK, width=3),
            name='Pintle',
            hovertemplate=f'Pintle<br>Diameter: {D_pintle_mm:.1f} mm<br>Material: Stainless Steel'
        ))
        
        # Add mounting features
        # Pintle support arms (4 arms at 90° intervals)
        arm_angles = [0, np.pi/2, np.pi, 3*np.pi/2]
        arm_width = 2
        
        for i, angle in enumerate(arm_angles):
            x_inner = D_pintle_mm/2 * np.cos(angle)
            y_inner = D_pintle_mm/2 * np.sin(angle)
            x_outer = inner_radius * np.cos(angle)
            y_outer = inner_radius * np.sin(angle)
            
            # Create arm rectangle
            arm_x = [x_inner - arm_width/2 * np.sin(angle), 
                    x_outer - arm_width/2 * np.sin(angle),
                    x_outer + arm_width/2 * np.sin(angle),
                    x_inner + arm_width/2 * np.sin(angle),
                    x_inner - arm_width/2 * np.sin(angle)]
            arm_y = [y_inner + arm_width/2 * np.cos(angle),
                    y_outer + arm_width/2 * np.cos(angle), 
                    y_outer - arm_width/2 * np.cos(angle),
                    y_inner - arm_width/2 * np.cos(angle),
                    y_inner + arm_width/2 * np.cos(angle)]
            
            fig.add_trace(go.Scatter(
                x=arm_x, y=arm_y,
                fill='toself',
                fillcolor='rgba(64, 64, 64, 0.9)',
                mode='lines',
                line=dict(color=STRUCT_INK, width=2),
                name='Support Arms' if i == 0 else '',
                showlegend=i == 0,
                hovertemplate='Support Arm<br>Thickness: 2 mm'
            ))
        
        # Flow direction arrows
        n_arrows = 8
        arrow_angles = np.linspace(0, 2*np.pi, n_arrows, endpoint=False)
        arrow_radius = (inner_radius + D_pintle_mm/2) / 2
        
        for i, angle in enumerate(arrow_angles):
            # Skip arrows where support arms are
            if not any(abs(angle - arm_angle) < 0.3 for arm_angle in arm_angles):
                x_start = arrow_radius * np.cos(angle)
                y_start = arrow_radius * np.sin(angle)
                x_end = (arrow_radius + 8) * np.cos(angle)
                y_end = (arrow_radius + 8) * np.sin(angle)
                
                fig.add_trace(go.Scatter(
                    x=[x_start, x_end],
                    y=[y_start, y_end],
                    mode='lines',
                    line=dict(color='#ff5d73', width=3),
                    name='Flow Direction' if i == 0 else '',
                    showlegend=i == 0 and 'Flow Direction' not in [trace.name for trace in fig.data],
                    hoverinfo='skip'
                ))
        
        # Add dimension lines
        fig.add_trace(go.Scatter(
            x=[-D_outer_mm/2, D_outer_mm/2],
            y=[-D_outer_mm/2 - 10, -D_outer_mm/2 - 10],
            mode='lines+text',
            line=dict(color='gray', width=1),
            text=[f'⌀{D_outer_mm:.1f} mm', ''],
            textposition='middle center',
            name='Dimensions',
            hoverinfo='skip'
        ))
        
        title = f'Pintle Injector Design'
        subtitle = f'Gap: {gap_mm:.2f} mm | Flow Area: {np.pi * ((D_outer_mm/2)**2 - (D_pintle_mm/2)**2):.1f} mm²'
        
    elif injector_type == 'swirl':
        # Professional swirl injector top view with proper dimensions
        n_slots = injector_data['n_slots']
        w_mm = injector_data['slot_width']  # Keep in mm
        h_mm = injector_data['slot_height']  # Keep in mm
        
        # Chamber with realistic dimensions
        chamber_radius_mm = max(30, w_mm * 10)  # Minimum 30mm radius
        theta = np.linspace(0, 2*np.pi, 100)
        
        # Swirl chamber outer wall
        fig.add_trace(go.Scatter(
            x=chamber_radius_mm * np.cos(theta),
            y=chamber_radius_mm * np.sin(theta),
            fill='toself',
            fillcolor='rgba(180, 180, 180, 0.6)',
            mode='lines',
            line=dict(color=STRUCT_INK, width=4),
            name='Swirl Chamber',
            hovertemplate=f'Swirl Chamber<br>Diameter: {chamber_radius_mm*2:.1f} mm<br>Material: Stainless Steel'
        ))
        
        # Inner swirl region
        inner_radius_mm = chamber_radius_mm * 0.7
        fig.add_trace(go.Scatter(
            x=inner_radius_mm * np.cos(theta),
            y=inner_radius_mm * np.sin(theta),
            fill='toself',
            fillcolor='rgba(135, 206, 235, 0.3)',
            mode='lines',
            line=dict(color='#00e5ff', width=2, dash='dot'),
            name='Swirl Region',
            hovertemplate='Swirl Flow Region'
        ))
        
        # Tangential slots with professional appearance
        slot_angles = np.linspace(0, 2*np.pi, n_slots, endpoint=False)
        
        for i, angle in enumerate(slot_angles):
            # Slot entry point on chamber wall
            x1 = chamber_radius_mm * np.cos(angle)
            y1 = chamber_radius_mm * np.sin(angle)
            
            # Tangential direction (90° offset for swirl)
            tangent_angle = angle + np.pi/2
            
            # Slot geometry - rectangular slot
            slot_length = w_mm * 3
            
            # Create slot as rectangle
            slot_corners_x = [
                x1 + w_mm/2 * np.cos(angle),
                x1 - w_mm/2 * np.cos(angle),
                x1 - w_mm/2 * np.cos(angle) + slot_length * np.cos(tangent_angle),
                x1 + w_mm/2 * np.cos(angle) + slot_length * np.cos(tangent_angle),
                x1 + w_mm/2 * np.cos(angle)
            ]
            
            slot_corners_y = [
                y1 + w_mm/2 * np.sin(angle),
                y1 - w_mm/2 * np.sin(angle),
                y1 - w_mm/2 * np.sin(angle) + slot_length * np.sin(tangent_angle),
                y1 + w_mm/2 * np.sin(angle) + slot_length * np.sin(tangent_angle),
                y1 + w_mm/2 * np.sin(angle)
            ]
            
            fig.add_trace(go.Scatter(
                x=slot_corners_x, y=slot_corners_y,
                fill='toself',
                fillcolor='rgba(255, 165, 0, 0.8)',
                mode='lines',
                # v2.5.5: darkorange → palet (JS COLOR_FIX ile aynı ton)
                line=dict(color=COL_WARN_HI, width=2),
                name=f'Injection Slot' if i == 0 else '',
                showlegend=i == 0,
                hovertemplate=f'Slot {i+1}<br>Width: {w_mm:.2f} mm<br>Height: {h_mm:.2f} mm<br>Area: {w_mm * h_mm:.2f} mm²'
            ))
            
            # Add flow direction arrow
            arrow_start_x = x1 + slot_length/2 * np.cos(tangent_angle)
            arrow_start_y = y1 + slot_length/2 * np.sin(tangent_angle)
            arrow_end_x = arrow_start_x + 8 * np.cos(tangent_angle)
            arrow_end_y = arrow_start_y + 8 * np.sin(tangent_angle)
            
            fig.add_trace(go.Scatter(
                x=[arrow_start_x, arrow_end_x],
                y=[arrow_start_y, arrow_end_y],
                mode='lines',
                line=dict(color='#ff5d73', width=3),
                name='Flow Direction' if i == 0 else '',
                showlegend=i == 0,
                hoverinfo='skip'
            ))
        
        # Central exit orifice with realistic sizing
        exit_area_mm2 = injector_data['exit_orifice_area']  # Assume this is in mm²
        exit_radius_mm = np.sqrt(exit_area_mm2 / np.pi)
        
        fig.add_trace(go.Scatter(
            x=exit_radius_mm * np.cos(theta),
            y=exit_radius_mm * np.sin(theta),
            fill='toself',
            fillcolor='white',
            mode='lines',
            line=dict(color=STRUCT_INK, width=3),
            name='Exit Orifice',
            hovertemplate=f'Exit Orifice<br>Diameter: {exit_radius_mm*2:.2f} mm<br>Area: {exit_area_mm2:.2f} mm²'
        ))
        
        # Add swirl flow indicators (spiral pattern)
        spiral_angles = np.linspace(0, 4*np.pi, 50)
        spiral_radius = np.linspace(exit_radius_mm * 1.2, inner_radius_mm, 50)
        spiral_x = spiral_radius * np.cos(spiral_angles)
        spiral_y = spiral_radius * np.sin(spiral_angles)
        
        fig.add_trace(go.Scatter(
            x=spiral_x, y=spiral_y,
            mode='lines',
            line=dict(color='#00e5ff', width=2, dash='dash'),
            name='Swirl Pattern',
            hovertemplate='Swirl Flow Pattern'
        ))
        
        # Add mounting holes
        mount_radius = chamber_radius_mm * 1.2
        n_mounts = 6
        mount_angles = np.linspace(0, 2*np.pi, n_mounts, endpoint=False)
        mount_x = mount_radius * np.cos(mount_angles)
        mount_y = mount_radius * np.sin(mount_angles)
        
        fig.add_trace(go.Scatter(
            x=mount_x, y=mount_y,
            mode='markers',
            marker=dict(size=8, color='gray', symbol='circle'),
            name='Mounting Holes',
            hovertemplate='M8 Mounting Hole'
        ))
        
        title = f'Swirl Injector Design'
        subtitle = f'{n_slots} slots × {w_mm:.1f}×{h_mm:.1f} mm | Spray Angle: {injector_data["spray_angle"]}°'
    
    # Clean layout with improved sizing
    fig.update_layout(
        title=dict(
            text=f'{title}<br><sub>{subtitle}</sub>',
            x=0.5,
            font=dict(size=18, family='Arial', color=STRUCT_INK)
        ),
        xaxis=dict(
            title='X (mm)',
            showgrid=False,
            zeroline=True,
            zerolinecolor='gray',
            zerolinewidth=1
        ),
        yaxis=dict(
            title='Y (mm)',
            showgrid=False,
            zeroline=True,
            zerolinecolor='gray',
            zerolinewidth=1,
            scaleanchor='x',
            scaleratio=1
        ),
        showlegend=True,
        legend=dict(x=0.02, y=0.98),
        autosize=True,
        height=800,
        plot_bgcolor='white',
        hovermode='closest',
        margin=dict(t=100, b=80, l=80, r=80)
    )
    fig.add_annotation(
        x=0.5, y=1.05, xref='paper', yref='paper', showarrow=False,
        text=('Fallback schematic — the detailed injector view was not '
              'available for this run; plate outline is drawn, not computed.'),
        font=dict(size=11, color=COL_WARN_HI), align='center')

    return _fig_json(fig)

# ---------------------------------------------------------------------------
# Performans panosu (create_performance_plots) — motor tipine duyarlı adaptör
# ---------------------------------------------------------------------------
# Eski sürüm YALNIZ hibrit alan adlarına (mdot_ox / mdot_f / port_history /
# injector.pressure_drop) bağlıydı; katı ve sıvı sayfalarında pano hiç
# üretilemiyordu. Artık motor tipi motor_data'dan çıkarılır ve her tip kendi
# panel listesini kurar. Veri yoksa panel UYDURULMAZ, listeden düşer ve ızgara
# kalan panel sayısına göre yeniden boyutlanır. Çağrı imzası korunur
# (injector_data katı motorda anlamsız olduğu için opsiyoneldir).
PERF_V_SPACING = 0.20     # satırlar arası boşluk (dar ekran onarımı, 2026-07-19)
PERF_H_SPACING = 0.22     # sütunlar arası boşluk
PERF_ROW_HEIGHT = 425     # px/satır — 2 satır = eski 850 px pano yüksekliği
PERF_TITLE_SIZE = 22
PERF_SUBPLOT_COLS = 2     # varsayılan ızgara genişliği
PERF_MIN_SERIES = 3       # bir zaman serisinin panel çizmeye yetmesi için min nokta
# Enjektör göstergesi: ölçek tam skalası ve bölge sınırları ORAN olarak tutulur
# (100 m/s tam skalada eski mutlak 20/50/100 sınırlarıyla birebir aynıdır).
PERF_GAUGE_FULL_SCALE = 100.0   # m/s
PERF_GAUGE_ROUND = 50.0         # skala taşarsa yuvarlanacağı adım
PERF_GAUGE_STEP_FRACTIONS = (0.20, 0.50, 1.00)
PERF_GAUGE_THRESHOLD_FRACTION = 0.50
# Birim dönüşümleri (panolarda gösterim birimi)
M_TO_MM = 1000.0
M2_TO_CM2 = 1.0e4


def _perf_num(value):
    """Sonlu bir sayıya çevrilebiliyorsa saf float döner, aksi halde None."""
    if value is None or isinstance(value, (bool, str, dict, list, tuple)):
        if isinstance(value, str):
            try:
                value = float(value)
            except (TypeError, ValueError):
                return None
        else:
            return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _perf_series(seq, min_len=PERF_MIN_SERIES):
    """Diziyi saf Python float listesine indirger.

    numpy dizisi doğrudan Plotly'ye verilirse fig.to_dict() base64 'bdata'
    bloğu üretir ve paketlenmiş plotly.js 1.58.5 bunu çözemez (boş çizgi
    bugı). Bu yüzden pano serilerinin TAMAMI buradan geçer.
    """
    if seq is None:
        return None
    if isinstance(seq, np.ndarray):
        seq = seq.tolist()
    if not isinstance(seq, (list, tuple)):
        return None
    out = []
    for v in seq:
        n = _perf_num(v)
        if n is None:
            return None
        out.append(n)
    return out if len(out) >= min_len else None


def _perf_motor_type(motor_data):
    """motor_data'dan motor tipini çıkarır (hibrit / katı / sıvı).

    Öncelik: açık 'motor_type' / 'viz_motor_type' anahtarı; yoksa alan
    varlığından çıkarım (app.py'ye dokunmadan çalışabilmesi için).
    """
    explicit = motor_data.get('motor_type') or motor_data.get('viz_motor_type')
    if isinstance(explicit, str) and explicit.strip().lower() in ('hybrid', 'solid', 'liquid'):
        return explicit.strip().lower()

    # Hibrit: tek gövdede iki ayrı debi (oksitleyici sıvı/gaz + katı yakıt)
    if _perf_num(motor_data.get('mdot_ox')) is not None and \
            _perf_num(motor_data.get('mdot_f')) is not None:
        return 'hybrid'

    # Katı: yanma alanı zaman serisi yalnız katı çözücüde vardır
    curve = motor_data.get('thrust_curve')
    if isinstance(curve, dict) and curve.get('burn_area') is not None:
        return 'solid'
    if motor_data.get('grain_type') and motor_data.get('propellant_type'):
        return 'solid'

    # Sıvı: besleme sistemi debileri
    feed = motor_data.get('feed_system')
    if isinstance(feed, dict) and isinstance(feed.get('mass_flow_rates'), dict):
        return 'liquid'
    if _perf_num(motor_data.get('mixture_ratio')) is not None and \
            _perf_num(motor_data.get('total_mass_flow')) is not None:
        return 'liquid'

    return 'hybrid'


def _perf_grid(n_panels):
    """Panel sayısına göre (satır, sütun, yerleşim) döndürür.

    Yerleşim öğesi (row, col, colspan). Tek sayıda panelde son panel satırı
    boyunca uzatılır ki ızgarada boş hücre kalmasın.
    """
    if n_panels <= 1:
        return 1, 1, [(1, 1, 1)]
    if n_panels == 2:
        return 1, 2, [(1, 1, 1), (1, 2, 1)]
    cols = PERF_SUBPLOT_COLS
    rows = int(math.ceil(n_panels / float(cols)))
    slots = []
    for i in range(n_panels):
        r = i // cols + 1
        c = i % cols + 1
        span = cols if (i == n_panels - 1 and c == 1) else 1
        slots.append((r, c, span))
    return rows, cols, slots


def _perf_bar_panel(title, labels, values, colors, value_fmt,
                    x_title, y_title, trace_name=None):
    """Sonlu değeri olan çubukları bir panel sözlüğüne çevirir (yoksa None)."""
    trace_name = trace_name or title
    keep = [(l, _perf_num(v), c) for l, v, c in zip(labels, values, colors)]
    keep = [(l, v, c) for l, v, c in keep if v is not None]
    if not keep:
        return None
    xs = [k[0] for k in keep]
    ys = [k[1] for k in keep]
    cs = [k[2] for k in keep]
    texts = [value_fmt.format(v) for v in ys]

    def draw(fig, row, col):
        fig.add_trace(
            go.Bar(
                x=xs, y=ys, marker_color=cs, text=texts,
                textposition='auto',
                # Dik yazılan çubuk etiketleri dar ekranda okunmuyordu; yatay
                # sabitlenir ve eksen kutusunun dışına taşabilir (kırpılmaz)
                textangle=0,
                cliponaxis=False,
                name=trace_name, showlegend=False
            ),
            row=row, col=col
        )

    def axes(fig, row, col):
        fig.update_xaxes(title_text=x_title, row=row, col=col)
        fig.update_yaxes(title_text=y_title, row=row, col=col)

    return {'title': title, 'spec': {'type': 'bar'}, 'draw': draw, 'axes': axes}


def _perf_gauge_panel(title, value, unit='m/s'):
    """Enjektör hız göstergesi paneli (değer yoksa None)."""
    val = _perf_num(value)
    if val is None or val <= 0:
        return None
    full = PERF_GAUGE_FULL_SCALE
    if val > full:
        full = math.ceil(val / PERF_GAUGE_ROUND) * PERF_GAUGE_ROUND
    f_lo, f_mid, f_hi = PERF_GAUGE_STEP_FRACTIONS
    steps = [
        {'range': [0, full * f_lo], 'color': "#46606d"},
        {'range': [full * f_lo, full * f_mid], 'color': COL_SAFE},
        {'range': [full * f_mid, full * f_hi], 'color': COL_DANGER},
    ]

    def draw(fig, row, col):
        fig.add_trace(
            go.Indicator(
                mode="gauge+number",
                value=val,
                # Başlık BİLEREK yok: hücrenin üstünde subplot_titles'tan gelen
                # başlık annotation'ı var; Indicator'ın kendi title'ı onunla
                # AYNI noktaya basılıp üst üste biniyordu. Birim, başlık yerine
                # sayının sonekinde taşınır.
                number={'suffix': ' ' + unit, 'font': {'size': 26}},
                domain={'x': [0, 1], 'y': [0, 1]},
                gauge={
                    # Dar ekranda gösterge ekseni etiketleri sayının üstüne
                    # biniyordu: yazı boyutu küçültüldü (2026-07-19)
                    'axis': {'range': [0, full], 'tickfont': {'size': 10}},
                    # v2.5.5: darkblue koyu zeminde kayboluyordu → palet
                    'bar': {'color': PALETTE[6]},
                    'steps': steps,
                    'threshold': {
                        'line': {'color': COL_DANGER, 'width': 4},
                        'thickness': 0.75,
                        'value': full * PERF_GAUGE_THRESHOLD_FRACTION
                    }
                }
            ),
            row=row, col=col
        )

    def axes(fig, row, col):
        return None

    return {'title': title, 'spec': {'type': 'indicator'},
            'draw': draw, 'axes': axes}


def _perf_dual_axis_panel(title, x, primary, secondary, x_title):
    """İki eksenli zaman serisi paneli.

    primary/secondary: (y_listesi, ad, renk, y_ekseni_başlığı, hover_birimi)
    secondary None ise tek eksen çizilir.
    """
    xs = _perf_series(x)
    if xs is None or primary is None:
        return None
    y1, name1, color1, ytitle1, unit1 = primary
    ys1 = _perf_series(y1)
    if ys1 is None or len(ys1) != len(xs):
        return None
    sec = None
    if secondary is not None:
        y2, name2, color2, ytitle2, unit2 = secondary
        ys2 = _perf_series(y2)
        if ys2 is not None and len(ys2) == len(xs):
            sec = (ys2, name2, color2, ytitle2, unit2)

    def draw(fig, row, col):
        fig.add_trace(
            go.Scatter(
                x=xs, y=ys1, mode='lines',
                line=dict(color=color1, width=3),
                name=name1,
                hovertemplate=('%{x:.2f} s<br>' + name1 +
                               ': %{y:.2f} ' + unit1).rstrip() + '<extra></extra>'
            ),
            row=row, col=col
        )
        if sec is not None:
            fig.add_trace(
                go.Scatter(
                    x=xs, y=sec[0], mode='lines',
                    line=dict(color=sec[2], width=2),
                    name=sec[1],
                    hovertemplate=('%{x:.2f} s<br>' + sec[1] +
                                   ': %{y:.2f} ' + sec[4]).rstrip() + '<extra></extra>'
                ),
                row=row, col=col, secondary_y=True
            )

    def axes(fig, row, col):
        fig.update_xaxes(title_text=x_title, row=row, col=col)
        fig.update_yaxes(title_text=ytitle1, secondary_y=False, row=row, col=col)
        if sec is not None:
            fig.update_yaxes(title_text=sec[3], secondary_y=True,
                             row=row, col=col)

    # time_axis: aynı panodaki zaman panelleri senkron zoom için eşlenir
    # (create_performance_plots sonunda _match_time_axes ile bağlanır).
    return {'title': title, 'spec': {'secondary_y': True},
            'draw': draw, 'axes': axes,
            'time_axis': x_title == 'Time (s)'}


# --- Hibrit panelleri -------------------------------------------------------

def _perf_panels_hybrid(motor_data, injector_data):
    panels = []

    panels.append(_perf_bar_panel(
        'Mass Flow Rates',
        ['Total', 'Oxidizer', 'Fuel'],
        [motor_data.get('mdot_total'), motor_data.get('mdot_ox'),
         motor_data.get('mdot_f')],
        ['#00e5ff', COL_SAFE, COL_WARN_HI],
        '{:.3f} kg/s', 'Component', 'Mass Flow Rate (kg/s)',
        trace_name='Mass Flow'
    ))

    # Basınç dağılımı — Tank çubuğu GERÇEK tank basıncını gösterir.
    # Eski kod Pc + ΔP_enjektör yazıyordu; bu besleme hattı kayıplarını yok
    # sayan bir tahmindi ve kullanıcının girdiği tank basıncıyla çelişiyordu.
    chamber = _perf_num(motor_data.get('chamber_pressure'))
    inj_dp = _perf_num(injector_data.get('pressure_drop'))
    tank = _perf_num(motor_data.get('tank_pressure'))
    if (tank is None or tank <= 0) and chamber is not None and inj_dp is not None:
        tank = inj_dp + chamber
    panels.append(_perf_bar_panel(
        'Pressure Distribution',
        ['Chamber', 'Tank', 'Inj. ΔP'],
        [chamber, tank, inj_dp],
        [COL_DANGER, '#00e5ff', COL_SAFE],
        '{:.1f} bar', 'Location', 'Pressure (bar)',
        trace_name='Pressure'
    ))

    panels.append(_perf_panel_regression(motor_data))
    panels.append(_perf_gauge_panel('Injector Performance',
                                    injector_data.get('exit_velocity')))
    return [p for p in panels if p]


def _perf_panel_regression(motor_data):
    """Regresyon/port evrimi — GERÇEK çözücü serisinden.

    Eski kod lineer interpolasyon + yapay sinüs dalgacığı çiziyordu; Euler
    marşının ürettiği port_history (zaman, çap) artık doğrudan kullanılır,
    regresyon hızı da bu serinin türevinden gelir (r = (dD/dt)/2).
    """
    ph = motor_data.get('port_history') or {}
    t_ph = _perf_series(ph.get('time')) if isinstance(ph, dict) else None
    d_ph = _perf_series(ph.get('port_diameter')) if isinstance(ph, dict) else None

    if t_ph and d_ph and len(t_ph) == len(d_ph):
        time = np.asarray(t_ph, dtype=float)
        port_diameter = np.asarray(d_ph, dtype=float)  # m
        regression = np.gradient(port_diameter, time) / 2.0 * M_TO_MM  # mm/s
        reg_label = (f'Regression Rate (avg: '
                     f'{float(np.mean(regression)):.2f} mm/s)')
        port_mm = (port_diameter * M_TO_MM).tolist()
        reg_list = regression.tolist()
        t_list = time.tolist()
    else:
        # port_history yoksa (eski kayıt/yabancı veri) analitik özete düş
        burn_time = _perf_num(motor_data.get('burn_time'))
        rate = _perf_num(motor_data.get('regression_rate'))
        d_i = _perf_num(motor_data.get('port_diameter_initial'))
        d_f = _perf_num(motor_data.get('port_diameter_final'))
        if burn_time is None or burn_time <= 0 or rate is None \
                or d_i is None or d_f is None:
            return None
        n_pts = 100
        t_list = np.linspace(0, burn_time, n_pts).tolist()
        port_mm = (np.linspace(d_i, d_f, n_pts) * M_TO_MM).tolist()
        reg_list = (np.ones(n_pts) * rate * M_TO_MM).tolist()
        reg_label = f'Regression Rate (avg: {rate * M_TO_MM:.2f} mm/s)'

    def draw(fig, row, col):
        fig.add_trace(
            go.Scatter(
                x=t_list, y=port_mm, mode='lines',
                line=dict(color='#c792ea', width=3),
                name='Port Diameter Growth',
                hovertemplate='Time: %{x:.1f}s<br>Port Diameter: %{y:.1f}mm<extra></extra>'
            ),
            row=row, col=col
        )
        fig.add_trace(
            go.Scatter(
                x=t_list, y=reg_list, mode='lines',
                line=dict(color=COL_DANGER, width=2),
                name=reg_label,
                hovertemplate='Time: %{x:.1f}s<br>Regression Rate: %{y:.2f} mm/s<extra></extra>'
            ),
            row=row, col=col, secondary_y=True
        )

    def axes(fig, row, col):
        fig.update_xaxes(title_text="Time (s)", row=row, col=col)
        fig.update_yaxes(title_text="Port Diameter (mm)", secondary_y=False,
                         row=row, col=col)
        # İkincil eksen başlığı dar ekranda komşu hücreye taşıyordu; kısaltıldı
        fig.update_yaxes(title_text="r (mm/s)", secondary_y=True,
                         row=row, col=col)

    return {'title': 'Regression Rate & Port Growth',
            'spec': {'secondary_y': True}, 'draw': draw, 'axes': axes,
            'time_axis': True}


# --- Katı motor panelleri ---------------------------------------------------

def _perf_panels_solid(motor_data):
    """Katı motor panosu: debi + basınç + F(t) + yanma alanı/Kn.

    Katıda tek propellant vardır (oksitleyici/yakıt ayrımı YOK) ve port
    yerine yanan yüzey regresyonu izlenir; paneller buna göre kurulur.
    """
    curve = motor_data.get('thrust_curve')
    curve = curve if isinstance(curve, dict) else {}
    t = _perf_series(curve.get('time'))
    thrust = _perf_series(curve.get('thrust'))
    pressure = _perf_series(curve.get('pressure'))
    mdot = _perf_series(curve.get('mass_flow'))
    burn_area = _perf_series(curve.get('burn_area'))

    panels = []

    # 1) Kütle debisi — tek propellant; tepe/ortalama/sönme değerleri
    if mdot:
        panels.append(_perf_bar_panel(
            'Propellant Mass Flow',
            ['Peak', 'Average', 'Burnout'],
            [max(mdot), sum(mdot) / len(mdot), mdot[-1]],
            ['#00e5ff', COL_SAFE, COL_WARN_HI],
            '{:.3f} kg/s', 'Operating Point', 'Mass Flow Rate (kg/s)'
        ))

    # 2) Basınç dağılımı — tasarım Pc ile gerçekleşen tepe/ortalama
    design_pc = _perf_num(motor_data.get('chamber_pressure'))
    if pressure:
        panels.append(_perf_bar_panel(
            'Pressure Distribution',
            ['Design Pc', 'Peak', 'Average'],
            [design_pc, max(pressure), sum(pressure) / len(pressure)],
            ['#00e5ff', COL_DANGER, COL_SAFE],
            '{:.1f} bar', 'Operating Point', 'Pressure (bar)'
        ))
    elif design_pc is not None:
        panels.append(_perf_bar_panel(
            'Pressure Distribution', ['Design Pc'], [design_pc],
            ['#00e5ff'], '{:.1f} bar', 'Operating Point', 'Pressure (bar)'
        ))

    # 3) İtki ve kamara basıncı zaman serisi
    if t and thrust:
        sec = None
        if pressure and len(pressure) == len(t):
            sec = (pressure, 'Chamber Pressure', COL_DANGER,
                   'Pressure (bar)', 'bar')
        panels.append(_perf_dual_axis_panel(
            'Thrust & Chamber Pressure vs Time', t,
            (thrust, 'Thrust', '#00e5ff', 'Thrust (N)', 'N'),
            sec, 'Time (s)'
        ))

    # 4) Yanan yüzey alanı ve Kn (= A_burn / A_throat) evrimi
    if t and burn_area and len(burn_area) == len(t):
        area_cm2 = [a * M2_TO_CM2 for a in burn_area]
        d_throat_mm = _perf_num(motor_data.get('throat_diameter'))
        sec = None
        if d_throat_mm and d_throat_mm > 0:
            a_throat = math.pi * (d_throat_mm / M_TO_MM / 2.0) ** 2  # m^2
            sec = ([a / a_throat for a in burn_area], 'Kn', COL_WARN_HI,
                   'Kn (-)', '')
        panels.append(_perf_dual_axis_panel(
            'Burn Area & Kn vs Time', t,
            (area_cm2, 'Burn Area', '#c792ea', 'Burn Area (cm²)', 'cm²'),
            sec, 'Time (s)'
        ))

    return [p for p in panels if p]


# --- Sıvı motor panelleri ---------------------------------------------------

def _perf_panels_liquid(motor_data, injector_data):
    """Sıvı motor panosu: debiler + basınç + besleme bütçesi + enjektör.

    Sıvıda port regresyonu YOKTUR; onun yerine besleme sistemi basınç
    bütçesi gösterilir (feed_system.pressure_drops).
    """
    feed = motor_data.get('feed_system')
    feed = feed if isinstance(feed, dict) else {}
    rates = feed.get('mass_flow_rates')
    rates = rates if isinstance(rates, dict) else {}
    inj_design = motor_data.get('injector_design')
    inj_design = inj_design if isinstance(inj_design, dict) else {}
    inj_system = motor_data.get('injection_system')
    inj_system = inj_system if isinstance(inj_system, dict) else {}

    mdot_total = _perf_num(rates.get('total'))
    if mdot_total is None:
        mdot_total = _perf_num(motor_data.get('total_mass_flow'))
    mdot_ox = _perf_num(rates.get('oxidizer'))
    if mdot_ox is None:
        mdot_ox = _perf_num(motor_data.get('oxidizer_flow'))
    mdot_f = _perf_num(rates.get('fuel'))
    if mdot_f is None:
        mdot_f = _perf_num(motor_data.get('fuel_flow'))

    panels = []

    panels.append(_perf_bar_panel(
        'Mass Flow Rates',
        ['Total', 'Oxidizer', 'Fuel'],
        [mdot_total, mdot_ox, mdot_f],
        ['#00e5ff', COL_SAFE, COL_WARN_HI],
        '{:.3f} kg/s', 'Component', 'Mass Flow Rate (kg/s)',
        trace_name='Mass Flow'
    ))

    # Basınç dağılımı: kamara / besleme (pompa çıkışı veya tank) / enjektör ΔP
    chamber = _perf_num(motor_data.get('chamber_pressure'))
    drops = feed.get('pressure_drops')
    drops = drops if isinstance(drops, dict) else {}
    inj_dp = _perf_num(inj_design.get('injection_pressure_drop_ox_bar'))
    if inj_dp is None:
        inj_dp = _perf_num(inj_system.get('ox_pressure_drop'))
    if inj_dp is None:
        inj_dp = _perf_num(injector_data.get('pressure_drop'))
    if inj_dp is None:
        inj_dp = _perf_num(drops.get('injector'))
    feed_pressure = _perf_num(drops.get('pump_discharge_pressure_ox'))
    if feed_pressure is None:
        feed_pressure = _perf_num(inj_system.get('required_ox_tank_pressure'))
    if feed_pressure is None:
        feed_pressure = _perf_num(motor_data.get('tank_pressure'))
    panels.append(_perf_bar_panel(
        'Pressure Distribution',
        ['Chamber', 'Feed', 'Inj. ΔP'],
        [chamber, feed_pressure, inj_dp],
        [COL_DANGER, '#00e5ff', COL_SAFE],
        '{:.1f} bar', 'Location', 'Pressure (bar)'
    ))

    # Besleme hattı basınç bütçesi (yalnız bileşen kayıpları; toplamlar hariç)
    budget_labels = [
        ('tank_outlet', 'Tank Outlet'), ('main_valve', 'Main Valve'),
        ('filters', 'Filters'), ('feed_lines', 'Feed Lines'),
        ('injector', 'Injector'),
    ]
    b_names, b_vals = [], []
    for key, label in budget_labels:
        val = _perf_num(drops.get(key))
        if val is not None:
            b_names.append(label)
            b_vals.append(val)
    if b_names:
        panels.append(_perf_bar_panel(
            'Feed System Pressure Budget', b_names, b_vals,
            [PALETTE[i % len(PALETTE)] for i in range(len(b_names))],
            '{:.2f} bar', 'Component', 'Pressure Drop (bar)'
        ))

    inj_velocity = _perf_num(inj_design.get('ox_injection_velocity_m_s'))
    if inj_velocity is None:
        inj_velocity = _perf_num(inj_system.get('ox_injection_velocity'))
    if inj_velocity is None:
        inj_velocity = _perf_num(injector_data.get('exit_velocity'))
    panels.append(_perf_gauge_panel('Injector Performance', inj_velocity))

    return [p for p in panels if p]


def _perf_empty_figure(title, note='No performance data available'):
    """Hiçbir panel kurulamadığında boş ama okunur bir figür döner."""
    fig = go.Figure()
    fig.add_annotation(text=note, showarrow=False,
                       font=dict(size=16, color=STRUCT_DIM),
                       xref='paper', yref='paper', x=0.5, y=0.5)
    fig.update_layout(
        title=dict(text=title,
                   font=dict(size=PERF_TITLE_SIZE, family='Arial',
                             color=STRUCT_INK),
                   x=0.5),
        height=PERF_ROW_HEIGHT, autosize=True,
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        plot_bgcolor='white', paper_bgcolor='white'
    )
    return _fig_json(fig)


PERF_TITLES = {
    'hybrid': 'Hybrid Rocket Performance Analysis',
    'solid': 'Solid Rocket Performance Analysis',
    'liquid': 'Liquid Rocket Performance Analysis',
}


def create_performance_plots(motor_data, injector_data=None):
    """Motor tipine duyarlı performans panosu (hibrit / katı / sıvı).

    injector_data katı motorda anlamsız olduğundan opsiyoneldir; hibrit
    çağrı imzası (motor_data, injector_data) değişmeden korunur.
    """
    from plotly.subplots import make_subplots

    motor_data = motor_data if isinstance(motor_data, dict) else {}
    injector_data = injector_data if isinstance(injector_data, dict) else {}

    motor_type = _perf_motor_type(motor_data)
    title = PERF_TITLES.get(motor_type, PERF_TITLES['hybrid'])
    if motor_type == 'solid':
        panels = _perf_panels_solid(motor_data)
    elif motor_type == 'liquid':
        panels = _perf_panels_liquid(motor_data, injector_data)
    else:
        panels = _perf_panels_hybrid(motor_data, injector_data)

    if not panels:
        return _perf_empty_figure(title)

    rows, cols, slots = _perf_grid(len(panels))
    specs = [[None] * cols for _ in range(rows)]
    for panel, (r, c, span) in zip(panels, slots):
        spec = dict(panel['spec'])
        if span > 1:
            spec['colspan'] = span
        specs[r - 1][c - 1] = spec

    fig = make_subplots(
        rows=rows, cols=cols,
        subplot_titles=[p['title'] for p in panels],
        specs=specs,
        vertical_spacing=PERF_V_SPACING,
        # Dar ekran onarımı (2026-07-19): Windows %125-150 ölçekte efektif
        # genişlik ~800 px'e düşüyor; 0.15 aralıkta sol sütunun y ekseni
        # başlığı sağ sütunun çubuk etiketlerine giriyordu.
        horizontal_spacing=PERF_H_SPACING
    )

    for panel, (r, c, _span) in zip(panels, slots):
        panel['draw'](fig, r, c)

    fig.update_layout(
        title=dict(
            text=title,
            font=dict(size=PERF_TITLE_SIZE, family='Arial', color=STRUCT_INK),
            x=0.5
        ),
        showlegend=True,
        height=rows * PERF_ROW_HEIGHT,
        autosize=True,
        plot_bgcolor='white',
        paper_bgcolor='white',
        margin=dict(t=120, b=100, l=100, r=100)
    )

    for panel, (r, c, _span) in zip(panels, slots):
        panel['axes'](fig, r, c)

    # Senkron zoom (v2.5.5): zaman ekseni taşıyan paneller (katı panoda
    # F(t)/Pc(t) ve yanma alanı/Kn panelleri) birbirine 'matches' ile
    # bağlanır — tek panel varsa (hibrit regresyon) hiçbir şey değişmez.
    _match_time_axes(fig, [(r, c) for panel, (r, c, _s) in zip(panels, slots)
                           if panel.get('time_axis')])

    return _fig_json(fig)

def create_heat_transfer_plots(heat_data):
    """Create comprehensive heat transfer analysis plots"""
    from plotly.subplots import make_subplots
    
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=('Wall Temperature Distribution', 'Thermal Stress Profile',
                       'Cooling Effectiveness', 'Temperature vs Time'),
        specs=[[{'type': 'scatter'}, {'type': 'heatmap'}],
               [{'type': 'bar'}, {'type': 'scatter'}]]
    )
    
    # Wall temperature distribution
    if 'wall_temperature_profile' in heat_data:
        wall_data = heat_data['wall_temperature_profile']
        fig.add_trace(
            go.Scatter(
                x=wall_data['position'],
                y=wall_data['temperature'],
                mode='lines+markers',
                line=dict(color='#ff5d73', width=3),
                marker=dict(size=6),
                name='Wall Temperature',
                hovertemplate='Position: %{x:.2f} m<br>Temperature: %{y:.1f} K'
            ),
            row=1, col=1
        )
        
        # Add critical temperature line
        critical_temp = heat_data.get('material_limit', 1073)
        fig.add_hline(
            y=critical_temp,
            line_dash="dash",
            line_color="#ff8c33",
            annotation_text=f"Critical Temp: {critical_temp}K",
            row=1, col=1
        )
    
    # Thermal stress heatmap
    if 'thermal_stress_map' in heat_data:
        stress_data = heat_data['thermal_stress_map']
        fig.add_trace(
            go.Heatmap(
                z=stress_data['stress_matrix'],
                x=stress_data['x_coords'],
                y=stress_data['y_coords'],
                colorscale='Reds',
                showscale=True,
                colorbar=dict(title="Stress (MPa)"),
                hovertemplate='X: %{x:.2f}<br>Y: %{y:.2f}<br>Stress: %{z:.1f} MPa'
            ),
            row=1, col=2
        )
    
    # Cooling effectiveness
    if 'cooling_analysis' in heat_data:
        cooling_data = heat_data['cooling_analysis']
        fig.add_trace(
            go.Bar(
                x=cooling_data['zones'],
                y=cooling_data['effectiveness'],
                marker_color=['#2dd4a8' if x > 0.8 else '#ff8c33' if x > 0.6 else '#ff5d73' 
                             for x in cooling_data['effectiveness']],
                text=[f"{x:.1%}" for x in cooling_data['effectiveness']],
                textposition='auto',
                name='Cooling Effectiveness'
            ),
            row=2, col=1
        )
    
    # Temperature vs time
    if 'temperature_history' in heat_data:
        temp_history = heat_data['temperature_history']
        for zone, data in temp_history.items():
            fig.add_trace(
                go.Scatter(
                    x=data['time'],
                    y=data['temperature'],
                    mode='lines',
                    name=f'{zone} Temperature',
                    line=dict(width=2)
                ),
                row=2, col=2
            )
    
    fig.update_layout(
        title_text="Heat Transfer Analysis Dashboard",
        showlegend=True,
        height=800,
        autosize=True
    )
    
    # Update axes
    fig.update_xaxes(title_text="Position (m)", row=1, col=1)
    fig.update_yaxes(title_text="Temperature (K)", row=1, col=1)
    
    fig.update_xaxes(title_text="Zone", row=2, col=1)
    fig.update_yaxes(title_text="Effectiveness (%)", row=2, col=1)
    
    fig.update_xaxes(title_text="Time (s)", row=2, col=2)
    fig.update_yaxes(title_text="Temperature (K)", row=2, col=2)
    
    return _fig_json(fig)

def _combustion_species_bars(combustion_data, station='chamber', top_n=10):
    """Denge çözücüsünün GERÇEK tür kesirlerini (mol) döndürür.

    Kaynak: CombustionAnalyzer.analyze_combustion -> compositions[station]
    ['species'] = {tur: {'mole_fraction','mass_fraction'}}. Eski sürüm
    hiç üretilmeyen 'species_concentrations' anahtarını aradığı için bu
    çeyrek HER ZAMAN boş çiziliyordu (2026-07-19 uydurma denetimi).
    """
    comps = (combustion_data or {}).get('compositions') or {}
    node = comps.get(station) or {}
    species = node.get('species') if isinstance(node, dict) else None
    if not isinstance(species, dict) or not species:
        return [], []
    pairs = []
    for name, val in species.items():
        if isinstance(val, dict):
            x = _perf_num(val.get('mole_fraction'))
        else:
            x = _perf_num(val)
        if x is not None and x > 0:
            pairs.append((str(name), float(x)))
    pairs.sort(key=lambda kv: kv[1], reverse=True)
    pairs = pairs[:top_n]
    return [k for k, _ in pairs], [v for _, v in pairs]


def _combustion_station_temperatures(combustion_data):
    """conditions{chamber,throat,exit}.T -> (etiketler, sıcaklıklar).

    Eski sürüm 'flame_temperature_profile' anahtarını arıyordu; çözücü onu
    hiç üretmiyor. Gerçek çözüm üç istasyonu raporluyor — eksen etiketinde
    'station' yazılır, uydurma bir x[m] ekseni ÜRETİLMEZ.
    """
    cond = (combustion_data or {}).get('conditions') or {}
    labels, temps = [], []
    for key, label in (('chamber', 'Chamber'), ('throat', 'Throat'),
                       ('exit', 'Exit')):
        t = _perf_num((cond.get(key) or {}).get('T'))
        if t is not None:
            labels.append(label)
            temps.append(float(t))
    return labels, temps


def _combustion_efficiency_breakdown(combustion_data, propellant=None):
    """Yanma/kinetik verimini GERÇEKTEN hesaplar.

    Döner: (yuzde | None, kaynak_notu)

    Bileşenler:
      eta_c*   : performance['c_star_delivered'] / performance['c_star'].
                 eta_c_star çağırana verilmediyse teorik denge = teslim
                 kabulüdür (1.000) ve not satırında BÖYLE yazılır.
      eta_kin  : sonlu-hız (kinetik) lüle verimi — KineticEfficiency
                 mühendislik korelasyonu, isp_predicted / isp_shifting.
                 O/F, Pc ve gaz hâline gerçekten duyarlıdır.

    Eski sürüm hiç üretilmeyen 'combustion_efficiency' anahtarını okuyup
    varsayılan 0.95'e düşüyordu; gösterge HER koşuda %95 gösteriyordu.
    """
    perf = ((combustion_data or {}).get('performance') or {})
    c_star = _perf_num(perf.get('c_star'))
    c_star_del = _perf_num(perf.get('c_star_delivered'))
    eta_c = None
    if c_star and c_star > 0 and c_star_del is not None:
        eta_c = c_star_del / c_star
    eta_c_supplied = _perf_num(perf.get('eta_c_star')) is not None

    eta_kin, kin_note = None, None
    try:
        from hrma.analysis.kinetic_efficiency import KineticEfficiency
        pc_bar = _perf_num(((combustion_data.get('conditions') or {})
                            .get('chamber') or {}).get('P'))
        kin = KineticEfficiency().evaluate(
            combustion_results=combustion_data,
            chamber_pressure=pc_bar,
            characteristic_length=(propellant or {}).get('characteristic_length'),
            throat_diameter=(propellant or {}).get('throat_diameter'),
            fidelity='engineering',
        )
        isp_sh = _perf_num(kin.get('isp_shifting'))
        isp_pr = _perf_num(kin.get('isp_predicted'))
        if isp_sh and isp_sh > 0 and isp_pr is not None:
            eta_kin = isp_pr / isp_sh
            kin_note = (f"eta_kin = {eta_kin * 100:.2f}% "
                        f"({kin.get('fidelity_used', 'engineering')} "
                        f"finite-rate correlation)")
    except Exception as exc:                     # kinetik yol yoksa sessiz düşme YOK
        kin_note = f"eta_kin not available ({type(exc).__name__})"

    if eta_c is None and eta_kin is None:
        return None, 'Not available for this run: solver reported no c* or Isp data.'

    total = 1.0
    parts = []
    if eta_c is not None:
        total *= eta_c
        parts.append(
            f"eta_c* = {eta_c * 100:.2f}%"
            + ('' if eta_c_supplied
               else ' (theoretical equilibrium; no measured c* efficiency supplied)')
        )
    if eta_kin is not None:
        total *= eta_kin
    if kin_note:
        parts.append(kin_note)
    return total * 100.0, ' | '.join(parts)


def _of_sweep_solve(fuel, ox, pc, lo, hi, n_points, analyzer=None):
    """O/F taramasının denge çözümü — her nokta bir analyze_combustion.

    Fizik burada; önbellekleme _of_sweep_solve_cached'te. Sonuç: (of, isp)
    liste çifti ya da None (2'den az nokta çözüldüyse).
    """
    if analyzer is None:
        from hrma.engines.combustion_analysis import CombustionAnalyzer
        analyzer = CombustionAnalyzer(memoize=True)
    of_vals, isp_vals = [], []
    for of in np.linspace(float(lo), float(hi), int(n_points)):
        try:
            res = analyzer.analyze_combustion(dict(fuel), str(ox), float(of),
                                              float(pc))
        except Exception:
            continue
        isp = _perf_num((res.get('performance') or {}).get('isp'))
        if isp is None:
            continue
        of_vals.append(float(of))
        isp_vals.append(float(isp))
    if len(of_vals) < 2:
        return None
    return of_vals, isp_vals


@functools.lru_cache(maxsize=16)
def _of_sweep_solve_cached(fuel_key, ox, pc, lo, hi, n_points):
    """Modül seviyesi tarama önbelleği (v2.5.5).

    Aynı yakıt/oksitleyici/Pc/aralık için tarama her panel isteğinde
    yeniden ÇÖZÜLMESİN diye sonuç saklanır. Fizik SONUCU değişmez —
    yalnız tekrar hesap önlenir. Anahtar hashlenebilir olmalı: yakıt
    sözlüğü frozenset(items) olarak gelir. Değişmezlik için tuple döner.
    """
    out = _of_sweep_solve(dict(fuel_key), ox, pc, lo, hi, n_points)
    if out is None:
        return None
    return tuple(out[0]), tuple(out[1])


def _combustion_of_sweep(propellant, n_points=9):
    """Gerçek O/F taraması: her nokta bir analyze_combustion çağrısıdır.

    propellant = {'fuel_composition': {...}, 'oxidizer_type': str,
                  'chamber_pressure': bar, 'of_range': (lo, hi)}
    Kimlik verilmemişse (app.py bugün geçirmiyor) None döner ve çeyrek
    'not available' notuyla çizilir — uydurma bir parabol ÇİZİLMEZ.
    """
    if not propellant:
        return None
    fuel = propellant.get('fuel_composition')
    ox = propellant.get('oxidizer_type')
    pc = _perf_num(propellant.get('chamber_pressure'))
    if not fuel or not ox or not pc:
        return None
    lo, hi = propellant.get('of_range') or PERF_SURFACE_OF_RANGE

    # Çağıran kendi analyzer örneğini verdiyse önbellek ATLANIR (örneğin
    # testler çözücü davranışını yamalayabilir); davranış birebir eski akış.
    if propellant.get('analyzer') is not None:
        return _of_sweep_solve(fuel, ox, pc, lo, hi, n_points,
                               analyzer=propellant['analyzer'])

    try:
        key = (frozenset(dict(fuel).items()), str(ox), float(pc),
               float(lo), float(hi), int(n_points))
    except TypeError:
        # Hashlenemeyen egzotik girdi: önbelleksiz çöz (davranış korunur)
        return _of_sweep_solve(fuel, ox, pc, lo, hi, n_points)
    cached = _of_sweep_solve_cached(*key)
    if cached is None:
        return None
    return list(cached[0]), list(cached[1])


def _propellant_from_combustion_data(combustion_data):
    """Kimlik parametresi verilmediyse çözücü çıktısındaki 'inputs'
    bloğundan türetir (analyze_combustion koşunun girdi kimliğini sonuca
    yazar). Eski/eksik sözlükte None döner; tarama çeyreği o zaman
    'not available' notuyla kalır — kimlik uydurulmaz."""
    if not isinstance(combustion_data, dict):
        return None
    ins = combustion_data.get('inputs')
    if not isinstance(ins, dict):
        return None
    fuel = ins.get('fuel_composition')
    ox = ins.get('oxidizer_type')
    pc = _perf_num(ins.get('chamber_pressure'))
    if not fuel or not ox or not pc:
        return None
    return {'fuel_composition': fuel, 'oxidizer_type': ox,
            'chamber_pressure': pc}


def create_combustion_analysis_plots(combustion_data, propellant=None):
    """Combustion dashboard fed by the equilibrium solver (no placeholders).

    Parameters
    ----------
    combustion_data : dict
        ``CombustionAnalyzer.analyze_combustion`` output.
    propellant : dict, optional
        ``{'fuel_composition': {...}, 'oxidizer_type': 'N2O',
        'chamber_pressure': bar}``. Only the O/F sweep quadrant needs it
        (the sweep re-solves equilibrium at each point). Absent -> that
        quadrant states it is unavailable instead of drawing a shape
        function.
    """
    from plotly.subplots import make_subplots

    # Çağıran kimliği geçirmediyse çözücü çıktısının 'inputs' bloğundan
    # türet — app.py çağrıları kimliği ayrıca taşımıyor (saha bulgusu
    # 2026-07-22: Isp vs O/F çeyreği bu yüzden hep boş kalıyordu).
    if not propellant:
        propellant = _propellant_from_combustion_data(combustion_data)

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=('Chamber Equilibrium Composition (solver)',
                        'Temperature by Station (solver)',
                        'Combustion / Kinetic Efficiency',
                        'Isp vs O/F (equilibrium sweep)'),
        specs=[[{'type': 'bar'}, {'type': 'scatter'}],
               [{'type': 'indicator'}, {'type': 'scatter'}]]
    )
    _style_subplot_titles(fig)
    notes = []

    # --- (1,1) Denge bileşimi: gerçek mol kesirleri --------------------
    names, fracs = _combustion_species_bars(combustion_data)
    if names:
        fig.add_trace(
            go.Bar(x=names, y=fracs, marker_color=PALETTE[0],
                   text=[f"{v:.4f}" for v in fracs], textposition='auto',
                   name='Mole fraction',
                   hovertemplate='%{x}: %{y:.5f} mole fraction<extra></extra>'),
            row=1, col=1)
    else:
        notes.append('Equilibrium composition not available for this run.')

    # --- (1,2) İstasyon sıcaklıkları ----------------------------------
    labels, temps = _combustion_station_temperatures(combustion_data)
    if temps:
        fig.add_trace(
            go.Scatter(x=labels, y=temps, mode='lines+markers',
                       line=dict(color=PALETTE[1], width=3),
                       marker=dict(size=10, color=PALETTE[3]),
                       name='Temperature',
                       hovertemplate='%{x}: %{y:.1f} K<extra></extra>'),
            row=1, col=2)
    else:
        notes.append('Station temperatures not available for this run.')

    # --- (2,1) Verim göstergesi: HESAPLANMIŞ ---------------------------
    eff_pct, eff_note = _combustion_efficiency_breakdown(
        combustion_data, propellant)
    if eff_pct is not None:
        fig.add_trace(
            go.Indicator(
                mode="gauge+number+delta",
                value=eff_pct,
                domain={'x': [0, 1], 'y': [0, 1]},
                # Başlık BİLEREK yok: subplot_titles'tan gelen "Combustion /
                # Kinetic Efficiency" annotation'ı ile aynı noktaya basılıp
                # üst üste biniyordu (saha fotoğrafı 2026-07-20). Formül
                # (eta_c* x eta_kinetic) altta hover/nota değil sayının
                # yüzde soneki yeterli — _perf_gauge_panel emsali.
                number={'suffix': ' %', 'valueformat': '.2f'},
                # Referans = ideal kayan-denge (kayıpsız) hâl
                delta={'reference': 100.0, 'valueformat': '.2f'},
                gauge={
                    'axis': {'range': [90, 100]},
                    'bar': {'color': COL_SAFE},
                    'steps': [
                        {'range': [90, 95], 'color': STEP_DANGER},
                        {'range': [95, 98], 'color': STEP_WARN},
                        {'range': [98, 100], 'color': STEP_SAFE},
                    ],
                }),
            row=2, col=1)
    notes.append(eff_note)

    # --- (2,2) Gerçek O/F taraması ------------------------------------
    sweep = _combustion_of_sweep(propellant)
    if sweep:
        of_vals, isp_vals = sweep
        fig.add_trace(
            go.Scatter(x=of_vals, y=isp_vals, mode='lines+markers',
                       line=dict(color=PALETTE[0], width=3),
                       marker=dict(size=7), name='Isp vs O/F',
                       hovertemplate='O/F %{x:.2f}: %{y:.1f} s<extra></extra>'),
            row=2, col=2)
        k = int(np.argmax(isp_vals))
        fig.add_trace(
            go.Scatter(x=[of_vals[k]], y=[isp_vals[k]], mode='markers',
                       marker=dict(size=15, color=COL_DANGER, symbol='star'),
                       name='Sweep maximum',
                       hovertemplate=(f'Sweep maximum<br>O/F {of_vals[k]:.2f}'
                                      f'<br>Isp {isp_vals[k]:.1f} s'
                                      '<extra></extra>')),
            row=2, col=2)
    else:
        notes.append('Isp vs O/F sweep not available: propellant identity '
                     '(fuel/oxidizer/chamber pressure) was not supplied to '
                     'this figure.')

    fig.add_annotation(
        x=0.0, y=-0.14, xref='paper', yref='paper', xanchor='left',
        showarrow=False, align='left',
        text='<br>'.join(f'- {n}' for n in notes if n),
        font=dict(size=10, color=STRUCT_DIM))

    fig.update_layout(
        title_text="Combustion Analysis Dashboard",
        showlegend=True, height=820, autosize=True,
        legend=_legend_below(-0.24),
        margin=dict(b=170))

    fig.update_xaxes(title_text="Species", row=1, col=1)
    fig.update_yaxes(title_text="Mole Fraction", row=1, col=1)
    fig.update_xaxes(title_text="Station", row=1, col=2)
    fig.update_yaxes(title_text="Temperature (K)", row=1, col=2)
    fig.update_xaxes(title_text="O/F Ratio", row=2, col=2)
    fig.update_yaxes(title_text="Specific Impulse (s)", row=2, col=2)

    return _fig_json(fig)

def create_structural_analysis_plots(structural_data):
    """Create comprehensive structural analysis visualizations"""
    from plotly.subplots import make_subplots
    
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=('Stress Distribution', 'Safety Factor Analysis',
                       'Wall Thickness Optimization', 'Fatigue Analysis'),
        specs=[[{'type': 'heatmap'}, {'type': 'bar'}],
               [{'type': 'scatter'}, {'type': 'scatter'}]]
    )
    
    # Stress distribution heatmap
    if 'stress_distribution' in structural_data:
        stress_data = structural_data['stress_distribution']
        fig.add_trace(
            go.Heatmap(
                z=stress_data['stress_matrix'],
                x=stress_data['x_coords'],
                y=stress_data['y_coords'],
                colorscale='RdYlBu_r',
                showscale=True,
                colorbar=dict(title="Von Mises Stress (MPa)"),
                hovertemplate='X: %{x:.2f}m<br>Y: %{y:.2f}m<br>Stress: %{z:.1f} MPa'
            ),
            row=1, col=1
        )
    
    # Safety factor analysis
    if 'safety_factors' in structural_data:
        sf_data = structural_data['safety_factors']
        colors = ['#2dd4a8' if x > 4 else '#ff8c33' if x > 2 else '#ff5d73' for x in sf_data['values']]
        fig.add_trace(
            go.Bar(
                x=sf_data['locations'],
                y=sf_data['values'],
                marker_color=colors,
                text=[f"SF: {x:.1f}" for x in sf_data['values']],
                textposition='auto',
                name='Safety Factor'
            ),
            row=1, col=2
        )
        
        # Add minimum safety factor line
        fig.add_hline(
            y=2.0,
            line_dash="dash",
            line_color="#ff5d73",
            annotation_text="Min SF: 2.0",
            row=1, col=2
        )
    
    # Wall thickness optimization
    if 'wall_thickness_analysis' in structural_data:
        wt_data = structural_data['wall_thickness_analysis']
        fig.add_trace(
            go.Scatter(
                x=wt_data['thickness'],
                y=wt_data['mass'],
                mode='lines+markers',
                line=dict(color='#00e5ff', width=3),
                marker=dict(size=6),
                name='Mass vs Thickness',
                yaxis='y'
            ),
            row=2, col=1
        )
        
        fig.add_trace(
            go.Scatter(
                x=wt_data['thickness'],
                y=wt_data['safety_factor'],
                mode='lines+markers',
                line=dict(color='#ff5d73', width=3),
                marker=dict(size=6),
                name='Safety Factor',
                yaxis='y2'
            ),
            row=2, col=1
        )
    
    # Fatigue analysis
    if 'fatigue_analysis' in structural_data:
        fatigue_data = structural_data['fatigue_analysis']
        fig.add_trace(
            go.Scatter(
                x=fatigue_data['cycles'],
                y=fatigue_data['stress_amplitude'],
                mode='lines+markers',
                line=dict(color='#c792ea', width=3),
                marker=dict(size=6),
                name='S-N Curve'
            ),
            row=2, col=2
        )
        
        # Add fatigue limit
        if 'fatigue_limit' in fatigue_data:
            fig.add_hline(
                y=fatigue_data['fatigue_limit'],
                line_dash="dash",
                line_color="#2dd4a8",
                annotation_text=f"Fatigue Limit: {fatigue_data['fatigue_limit']:.0f} MPa",
                row=2, col=2
            )
    
    fig.update_layout(
        title_text="Structural Analysis Dashboard",
        showlegend=True,
        height=800,
        autosize=True
    )
    
    # Update axes
    fig.update_xaxes(title_text="Location", row=1, col=2)
    fig.update_yaxes(title_text="Safety Factor", row=1, col=2)
    
    fig.update_xaxes(title_text="Wall Thickness (mm)", row=2, col=1)
    fig.update_yaxes(title_text="Mass (kg)", row=2, col=1)
    
    fig.update_xaxes(title_text="Cycles to Failure", row=2, col=2, type="log")
    fig.update_yaxes(title_text="Stress Amplitude (MPa)", row=2, col=2, type="log")
    
    return _fig_json(fig)

def create_real_time_dashboard(motor_data, time_data):
    """Create real-time performance monitoring dashboard"""
    from plotly.subplots import make_subplots
    
    fig = make_subplots(
        rows=3, cols=3,
        subplot_titles=('Thrust', 'Chamber Pressure', 'Mass Flow Rate',
                       'Temperature', 'O/F Ratio', 'Isp',
                       'Propellant Mass', 'Burn Rate', 'Port Diameter'),
        specs=[[{'type': 'indicator'}, {'type': 'indicator'}, {'type': 'indicator'}],
               [{'type': 'indicator'}, {'type': 'indicator'}, {'type': 'indicator'}],
               [{'type': 'scatter'}, {'type': 'scatter'}, {'type': 'scatter'}]],
        vertical_spacing=0.14
    )
    _style_subplot_titles(fig)

    # Gösterge hücreleri: Indicator'ın kendi title'ı BİLEREK yok —
    # subplot_titles annotation'ıyla aynı noktaya basılıp üst üste biniyordu
    # (saha fotoğrafı 2026-07-20). Birim sayının sonekinde taşınır
    # (_perf_gauge_panel emsali). Sıfır/eksik değerde 1.2*0 = [0, 0] ekseni
    # gauge'u kırıyordu -> tam skala en az 1 olacak şekilde korunur.
    def _gauge(value, suffix, bar_color, steps=None, full_scale=None):
        v = float(value or 0.0)
        full = full_scale if full_scale else max(v * 1.2, 1.0)
        return go.Indicator(
            mode="gauge+number",
            value=v,
            number={'suffix': suffix, 'font': {'size': 26}},
            gauge={
                'axis': {'range': [0, full], 'tickfont': {'size': 10}},
                'bar': {'color': bar_color},
                'steps': steps or [],
            }
        )

    # Current values indicators
    # v2.5.5: darkgreen/darkblue/darkorange/teal adlı CSS renkleri
    # koyu zeminde kayboluyordu → gauge bar renkleri merkezi paletten gelir
    # (plotly_dark.js fixTrace ayrıca emniyet katmanı olarak düzeltir).
    current_thrust = motor_data.get('thrust', 0)
    fig.add_trace(
        _gauge(current_thrust, ' N', COL_SAFE,
               steps=[{'range': [0, float(current_thrust or 0.0) * 0.8],
                       'color': "#46606d"}]),
        row=1, col=1
    )

    current_pressure = motor_data.get('chamber_pressure', 0)
    fig.add_trace(_gauge(current_pressure, ' bar', PALETTE[6]), row=1, col=2)

    current_mdot = motor_data.get('mdot_total', 0)
    fig.add_trace(_gauge(current_mdot, ' kg/s', COL_WARN_HI), row=1, col=3)

    # 2. sıra (saha fotoğrafı 2026-07-20: başlıklar vardı ama gauge'lar hiç
    # eklenmemişti -> Temperature / O/F Ratio / Isp hücreleri bomboştu).
    # Değerler motor sonuç sözlüğünün gerçek anahtarlarından gelir
    # (_compile_results: chamber_temperature, of_ratio, isp).
    current_temp = motor_data.get('chamber_temperature', 0)
    fig.add_trace(_gauge(current_temp, ' K', "#b3403a"), row=2, col=1)

    current_of = motor_data.get('of_ratio', 0)
    # O/F tipik 0-10 bandında; 1.2x tam skala iğneyi hep sağ uca yaslıyordu
    fig.add_trace(
        _gauge(current_of, '', PALETTE[0],
               full_scale=max(float(current_of or 0.0) * 2.0, 1.0)),
        row=2, col=2
    )

    current_isp = motor_data.get('isp', 0)
    fig.add_trace(_gauge(current_isp, ' s', "#7a5cc0"), row=2, col=3)

    # Hücre başlığı bandını boşalt: gauge'un tepe tick etiketi (tam skalanın
    # ~yarısına düşen değer) subplot başlığıyla aynı banda çizilebiliyor —
    # veri bağımlı çakışma, 3 ajanlı inceleme render kanıtıyla yakaladı.
    # Indicator domain'i hücre içinde aşağı sıkıştırılır; başlık üstte
    # kendi şeridinde kalır.
    for tr in fig.data:
        if tr.type == 'indicator':
            y0, y1 = tr.domain.y
            tr.domain.y = [y0, y0 + 0.78 * (y1 - y0)]
    
    # Time history plots if available
    if time_data:
        # Propellant mass over time
        fig.add_trace(
            go.Scatter(
                x=time_data['time'],
                y=time_data['propellant_mass'],
                mode='lines',
                line=dict(color='#ff5d73', width=3),
                name='Propellant Mass'
            ),
            row=3, col=1
        )
        
        # Burn rate over time
        fig.add_trace(
            go.Scatter(
                x=time_data['time'],
                y=time_data['burn_rate'],
                mode='lines',
                line=dict(color='#ff8c33', width=3),
                name='Burn Rate'
            ),
            row=3, col=2
        )
        
        # Port diameter over time
        fig.add_trace(
            go.Scatter(
                x=time_data['time'],
                y=time_data['port_diameter'],
                mode='lines',
                line=dict(color='#00e5ff', width=3),
                name='Port Diameter'
            ),
            row=3, col=3
        )

        # Senkron zoom (v2.5.5): 3. satırın üç paneli aynı zaman eksenini
        # paylaşır — birinde yapılan yakınlaştırma diğerlerine de uygulanır
        # (plotly.js 1.58.5 'matches' desteği 1.45.0'dan beri var, teyitli).
        _match_time_axes(fig, [(3, 1), (3, 2), (3, 3)])

    fig.update_layout(
        title_text="Real-Time Motor Performance Dashboard",
        # Figür başlığı üst marja sabitlenir; varsayılan yerleşimde 1. sıra
        # gauge içeriğiyle çakışıyordu (saha fotoğrafı 2026-07-20)
        title={'y': 0.985, 'yanchor': 'top'},
        margin=dict(t=80),
        showlegend=False,
        height=900,
        autosize=True
    )

    return _fig_json(fig)

def create_3d_motor_visualization(motor_data):
    """Create 3D motor visualization with cross-section and flow"""
    
    # Extract dimensions with safe defaults
    L = motor_data.get('chamber_length', 0.3) * 1000  # Convert to mm, default 300mm
    D = motor_data.get('chamber_diameter', 0.1) * 1000  # Default 100mm
    d_port = motor_data.get('port_diameter_initial', 0.03) * 1000  # Default 30mm
    d_throat = motor_data.get('throat_diameter', 0.02) * 1000  # Default 20mm
    d_exit = motor_data.get('exit_diameter', 0.08) * 1000  # Default 80mm
    
    fig = go.Figure()
    
    # Create cylinder for chamber
    theta = np.linspace(0, 2*np.pi, 50)
    z_chamber = np.linspace(-L/2, L/2, 50)
    
    # Chamber outer surface
    theta_mesh, z_mesh = np.meshgrid(theta, z_chamber)
    x_outer = (D/2) * np.cos(theta_mesh)
    y_outer = (D/2) * np.sin(theta_mesh)
    
    fig.add_trace(go.Surface(
        x=x_outer,
        y=y_outer,
        z=z_mesh,
        colorscale='Greys',
        opacity=0.7,
        name='Chamber Wall'
    ))
    
    # Fuel grain
    x_fuel = (d_port/2 + (D/2 - d_port/2)/2) * np.cos(theta_mesh)
    y_fuel = (d_port/2 + (D/2 - d_port/2)/2) * np.sin(theta_mesh)
    
    fig.add_trace(go.Surface(
        x=x_fuel,
        y=y_fuel,
        z=z_mesh,
        colorscale='burg',
        opacity=0.8,
        name='Fuel Grain'
    ))
    
    # Port (flow channel)
    x_port = (d_port/2) * np.cos(theta_mesh)
    y_port = (d_port/2) * np.sin(theta_mesh)
    
    fig.add_trace(go.Surface(
        x=x_port,
        y=y_port,
        z=z_mesh,
        colorscale='Blues',
        opacity=0.3,
        name='Flow Channel'
    ))
    
    # Nozzle — TEK ortak geometri kaynağı (2D kesit / STEP / STL ile aynı).
    # DURUSTLUK DUZELTMESI (2026-07-19): eski surum `nozzle_length = 100 mm`
    # SABIT cizip bogazi bu sabitin %30'una koyuyordu; ayni sayfadaki 2D
    # kesit gercek konturu kullandigi icin iki gorsel celisiyordu.
    contour_pts, contour_meta = sample_nozzle_inner_contour(motor_data)
    z_c = np.array([p[0] for p in contour_pts], dtype=float)   # mm
    r_c = np.array([p[1] for p in contour_pts], dtype=float)   # mm
    z_nozzle = L / 2 + z_c
    nozzle_radius = r_c

    theta_nozzle, z_nozzle_mesh = np.meshgrid(theta, z_nozzle)
    radius_mesh = np.array([nozzle_radius]).T
    x_nozzle = radius_mesh * np.cos(theta_nozzle)
    y_nozzle = radius_mesh * np.sin(theta_nozzle)
    
    fig.add_trace(go.Surface(
        x=x_nozzle,
        y=y_nozzle,
        z=z_nozzle_mesh,
        colorscale='Greys',
        opacity=0.8,
        name='Nozzle'
    ))
    
    fig.update_layout(
        title='3D Hybrid Rocket Motor Visualization',
        scene=dict(
            xaxis_title='X (mm)',
            yaxis_title='Y (mm)',
            zaxis_title='Z (mm)',
            aspectmode='data'
        ),
        autosize=True,
        height=600
    )
    
    return _fig_json(fig)

#: Karşılaştırma grafiğinin tanıdığı metrik anahtarları (şema esnetildi:
#: eksik anahtar artık KeyError değil — panel yalnız mevcut veriyle çizilir)
COMPARATIVE_METRIC_KEYS = ('thrust', 'isp', 'total_impulse', 'total_mass')


def _validate_comparative_configs(motor_configs):
    """Şema doğrulaması — çağırana NET hata mesajı (İngilizce).

    Dalga 4 onarımı (2026-07-14): eski kod motor_configs[name]['total_impulse']
    gibi zorunlu indekslemeler yüzünden eksik anahtarda KeyError atıyor,
    /api/comparative-analysis 500 dönüyordu. Yeni sözleşme: anahtarlar
    opsiyonel, ama yapı (dict-of-dict, sayısal değerler) doğrulanır.
    """
    if not isinstance(motor_configs, dict) or not motor_configs:
        raise ValueError(
            "motor_configs must be a non-empty dict of "
            "{config_name: {metric: value}} entries.")
    for name, cfg in motor_configs.items():
        if not isinstance(cfg, dict):
            raise ValueError(
                f"Configuration '{name}' must be a dict of metrics "
                f"(got {type(cfg).__name__}). Expected keys include: "
                + ", ".join(COMPARATIVE_METRIC_KEYS) + ".")
        for key in COMPARATIVE_METRIC_KEYS:
            value = cfg.get(key)
            if value is not None and not isinstance(value, (int, float)):
                raise ValueError(
                    f"Configuration '{name}' key '{key}' must be numeric, "
                    f"got {type(value).__name__}.")
    if not any(cfg.get(key) is not None
               for cfg in motor_configs.values()
               for key in COMPARATIVE_METRIC_KEYS):
        raise ValueError(
            "No plottable metrics found in motor_configs. Provide at "
            "least one of: " + ", ".join(COMPARATIVE_METRIC_KEYS) + ".")


def create_comparative_analysis_plot(motor_configs):
    """Create comparative analysis between different motor configurations.

    Eksik metrik anahtarları tolere edilir: her panel yalnızca o metriğe
    sahip konfigürasyonlarla çizilir; hiçbir konfigürasyonda yoksa panel
    boş bırakılır. Yapısal bozukluklar (dict olmayan config, sayısal
    olmayan değer) ValueError ile net mesaj verir.
    """
    from plotly.subplots import make_subplots

    _validate_comparative_configs(motor_configs)

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=('Thrust Comparison', 'Isp Comparison',
                       'Total Impulse Comparison', 'Mass Efficiency'),
        specs=[[{'type': 'bar'}, {'type': 'bar'}],
               [{'type': 'bar'}, {'type': 'scatter'}]]
    )

    def _pairs(key):
        # (isim, değer) — yalnız anahtarı mevcut ve sayısal olan configler
        return [(name, cfg[key]) for name, cfg in motor_configs.items()
                if cfg.get(key) is not None]

    # Thrust comparison
    thrust_pairs = _pairs('thrust')
    if thrust_pairs:
        fig.add_trace(
            go.Bar(
                x=[n for n, _ in thrust_pairs],
                y=[v for _, v in thrust_pairs],
                marker_color='lightblue',
                text=[f"{v:.0f} N" for _, v in thrust_pairs],
                textposition='auto',
                name='Thrust'
            ),
            row=1, col=1
        )

    # Isp comparison
    isp_pairs = _pairs('isp')
    if isp_pairs:
        fig.add_trace(
            go.Bar(
                x=[n for n, _ in isp_pairs],
                y=[v for _, v in isp_pairs],
                marker_color='lightgreen',
                text=[f"{v:.1f} s" for _, v in isp_pairs],
                textposition='auto',
                name='Specific Impulse'
            ),
            row=1, col=2
        )

    # Total impulse comparison (eski kodda zorunlu indeksleme -> KeyError)
    impulse_pairs = _pairs('total_impulse')
    if impulse_pairs:
        fig.add_trace(
            go.Bar(
                x=[n for n, _ in impulse_pairs],
                y=[v for _, v in impulse_pairs],
                marker_color='lightcoral',
                text=[f"{v:.0f} N⋅s" for _, v in impulse_pairs],
                textposition='auto',
                name='Total Impulse'
            ),
            row=2, col=1
        )

    # Mass efficiency scatter — hem total_mass hem isp gerektirir
    eff_points = [(name, cfg['total_mass'], cfg['isp'])
                  for name, cfg in motor_configs.items()
                  if cfg.get('total_mass') is not None
                  and cfg.get('isp') is not None]
    if eff_points:
        fig.add_trace(
            go.Scatter(
                x=[m for _, m, _ in eff_points],
                y=[i for _, _, i in eff_points],
                mode='markers+text',
                marker=dict(size=15, color='#c792ea'),
                text=[n for n, _, _ in eff_points],
                textposition='top center',
                name='Mass vs Isp'
            ),
            row=2, col=2
        )
    
    fig.update_layout(
        title_text="Motor Configuration Comparison",
        showlegend=False,
        height=800,
        autosize=True
    )
    
    # Update axes
    fig.update_xaxes(title_text="Configuration", row=1, col=1)
    fig.update_yaxes(title_text="Thrust (N)", row=1, col=1)
    
    fig.update_xaxes(title_text="Configuration", row=1, col=2)
    fig.update_yaxes(title_text="Isp (s)", row=1, col=2)
    
    fig.update_xaxes(title_text="Configuration", row=2, col=1)
    fig.update_yaxes(title_text="Total Impulse (N⋅s)", row=2, col=1)
    
    fig.update_xaxes(title_text="Total Mass (kg)", row=2, col=2)
    fig.update_yaxes(title_text="Isp (s)", row=2, col=2)
    
    return _fig_json(fig)

def _resolve_surface_propellant(engine_data):
    """Yüzey taraması için yakıt/oksitleyici kimliğini çözer.

    Döner: (fuel_composition, oxidizer_type, supplied_flag). Çağıran kimlik
    vermezse referans çift kullanılır ve figür alt başlığında AÇIKÇA yazılır
    (kullanıcı kendi propellantını sanmasın).
    """
    ed = engine_data or {}
    fuel = ed.get('fuel_composition')
    if not isinstance(fuel, dict) or not fuel:
        ftype = ed.get('fuel_type')
        fuel = {str(ftype).lower(): 100.0} if ftype else None
    ox = ed.get('oxidizer_type')
    supplied = bool(fuel and ox)
    if not fuel:
        fuel = {PERF_SURFACE_DEFAULT_FUEL: 100.0}
    if not ox:
        ox = PERF_SURFACE_DEFAULT_OXIDIZER
    return fuel, str(ox), supplied


def _isp_surface_solve(fuel, oxidizer, pc_lo, pc_hi, of_lo, of_hi, n):
    """Pc x O/F ızgarasında denge çözümü — figürden bağımsız saf hesap.

    Döner: (ISP ndarray [n x n, NaN = çözülemeyen düğüm], failures,
    first_error). Fizik değişmedi; yalnız create_..._3d_surface içinden
    önbelleklenebilir bir birime taşındı (v2.5.5).
    """
    from hrma.engines.combustion_analysis import CombustionAnalyzer

    pc_range = np.linspace(float(pc_lo), float(pc_hi), int(n))
    of_range = np.linspace(float(of_lo), float(of_hi), int(n))
    PC, OF = np.meshgrid(pc_range, of_range)

    analyzer = CombustionAnalyzer(memoize=True)
    ISP = np.full(PC.shape, np.nan)
    failures = 0
    first_error = None
    for j in range(int(n)):           # O/F ekseni
        for i in range(int(n)):       # Pc ekseni
            try:
                res = analyzer.analyze_combustion(
                    dict(fuel), oxidizer, float(OF[j, i]), float(PC[j, i]))
                isp = _perf_num((res.get('performance') or {}).get('isp'))
                if isp is not None and isp > 0:
                    ISP[j, i] = isp
                else:
                    failures += 1
            except Exception as exc:
                failures += 1
                if first_error is None:
                    first_error = str(exc)
    return ISP, failures, first_error


@functools.lru_cache(maxsize=16)
def _isp_surface_solve_cached(fuel_key, oxidizer, pc_lo, pc_hi,
                              of_lo, of_hi, n):
    """Yüzey ızgarası önbelleği (v2.5.5): 49+ denge çözümü her panel
    isteğinde tekrarlanmasın. Anahtar: frozenset(fuel.items()) + oksitleyici
    + aralıklar + n. Dönen dizi paylaşıldığı için yazmaya KAPATILIR
    (önbelleğin kazayla mutasyona uğramaması için).
    """
    ISP, failures, first_error = _isp_surface_solve(
        dict(fuel_key), oxidizer, pc_lo, pc_hi, of_lo, of_hi, n)
    ISP.flags.writeable = False
    return ISP, failures, first_error


def create_chamber_pressure_mixture_ratio_3d_surface(engine_data: Dict) -> str:
    """Isp surface over chamber pressure x O/F — solved, not shape-fitted.

    Every node of the grid is a real ``CombustionAnalyzer.analyze_combustion``
    call (chemical equilibrium + frozen/shifting expansion). The previous
    version multiplied a constant ``base_isp`` by two invented analytic shape
    functions and shaded an "instability" band with no sourced criterion
    (2026-07-19 fabrication audit).

    ``engine_data`` keys used: ``fuel_composition`` or ``fuel_type``,
    ``oxidizer_type``, ``chamber_pressure``/``optimal_chamber_pressure``,
    ``optimal_of_ratio``, ``base_isp`` (design point marker only),
    ``pc_range``, ``of_range``, ``grid_n``.
    """
    ed = engine_data or {}
    fuel, oxidizer, prop_supplied = _resolve_surface_propellant(ed)

    pc_lo, pc_hi = ed.get('pc_range') or PERF_SURFACE_PC_RANGE_BAR
    of_lo, of_hi = ed.get('of_range') or PERF_SURFACE_OF_RANGE
    n = int(ed.get('grid_n') or PERF_SURFACE_GRID_N)
    n = max(3, min(n, 21))

    pc_range = np.linspace(float(pc_lo), float(pc_hi), n)
    of_range = np.linspace(float(of_lo), float(of_hi), n)
    PC, OF = np.meshgrid(pc_range, of_range)

    # 49+ denge çözümü her istekte tekrarlanmasın: ızgara çözümü modül
    # seviyesi önbellekten gelir (v2.5.5). Tasarım noktası işaretleri ve
    # başlık metinleri önbelleğin DIŞINDA kalır — engine_data'nın base_isp
    # gibi alanları figürü etkilemeye devam eder, fizik sonucu değişmez.
    try:
        key = (frozenset(dict(fuel).items()), oxidizer,
               float(pc_lo), float(pc_hi), float(of_lo), float(of_hi), n)
        ISP, failures, first_error = _isp_surface_solve_cached(*key)
    except TypeError:
        # Hashlenemeyen egzotik yakıt girdisi: önbelleksiz çöz
        ISP, failures, first_error = _isp_surface_solve(
            fuel, oxidizer, float(pc_lo), float(pc_hi),
            float(of_lo), float(of_hi), n)

    fig = go.Figure()
    fig.add_trace(go.Surface(
        x=PC, y=OF, z=ISP,
        colorscale='Viridis',
        name='Equilibrium Isp',
        showscale=True,
        colorbar=dict(title="Isp (s)", x=1.02),
        hovertemplate=('Pc %{x:.1f} bar<br>O/F %{y:.2f}<br>'
                       'Isp %{z:.1f} s<extra></extra>')))

    # Izgara maksimumu — taramanın KENDİ sonucundan, uydurma tepe yok
    if np.isfinite(ISP).any():
        j, i = np.unravel_index(np.nanargmax(ISP), ISP.shape)
        fig.add_trace(go.Scatter3d(
            x=[float(PC[j, i])], y=[float(OF[j, i])], z=[float(ISP[j, i])],
            mode='markers',
            marker=dict(size=8, color=COL_WARN, symbol='diamond'),
            name='Sweep maximum',
            hovertemplate=(f'Sweep maximum<br>Pc {PC[j, i]:.1f} bar<br>'
                           f'O/F {OF[j, i]:.2f}<br>Isp {ISP[j, i]:.1f} s'
                           '<extra></extra>')))

    # Tasarım noktası: motor sonucundan gelen Isp (base_isp) — taramayla
    # karşılaştırılabilsin diye AYRI işaretlenir, yüzeye karıştırılmaz.
    design_pc = _perf_num(ed.get('optimal_chamber_pressure')
                          if ed.get('optimal_chamber_pressure') is not None
                          else ed.get('chamber_pressure'))
    design_of = _perf_num(ed.get('optimal_of_ratio'))
    design_isp = _perf_num(ed.get('base_isp'))
    if None not in (design_pc, design_of, design_isp):
        fig.add_trace(go.Scatter3d(
            x=[design_pc], y=[design_of], z=[design_isp],
            mode='markers',
            marker=dict(size=9, color=COL_DANGER, symbol='cross'),
            name='Design point (motor result)',
            hovertemplate=(f'Design point reported by the motor solver<br>'
                           f'Pc {design_pc:.1f} bar<br>O/F {design_of:.2f}<br>'
                           f'Isp {design_isp:.1f} s<extra></extra>')))

    prop_txt = (f"{oxidizer.upper()} / "
                f"{'+'.join(str(k).upper() for k in fuel)}")
    if not prop_supplied:
        prop_txt += ' (reference pair — propellant identity not supplied)'
    solved = int(n * n - failures)
    subtitle = (f"Chemical-equilibrium sweep, {solved}/{n * n} nodes solved | "
                f"{prop_txt}")
    if failures:
        subtitle += f" | {failures} node(s) unsolved (drawn as gaps)"

    note = ('Combustion-instability bands are NOT modeled here; the earlier '
            'shaded band had no sourced criterion and was removed. '
            'Sea-level expansion (Pe = 1 bar) is used for Isp.')
    if solved == 0:
        note = ('Surface not available: the equilibrium solver rejected every '
                'node of this sweep'
                + (f' ({first_error})' if first_error else '')
                + '. No surrogate surface is drawn.')
    fig.add_annotation(
        x=0.0, y=-0.06, xref='paper', yref='paper', xanchor='left',
        showarrow=False, align='left', text=note,
        font=dict(size=10, color=STRUCT_DIM))

    fig.update_layout(
        title={'text': ('3D Performance Map: Chamber Pressure vs O/F vs Isp'
                        f'<br><sub>{subtitle}</sub>'),
               'x': 0.5, 'font': {'size': 16}},
        scene=dict(
            xaxis_title='Chamber Pressure (bar)',
            yaxis_title='O/F Ratio',
            zaxis_title='Specific Impulse (s)',
            camera=dict(eye=dict(x=1.5, y=1.5, z=1.2))),
        autosize=True, height=700, showlegend=True,
        margin=dict(b=90))

    return _fig_json(fig)

def _nozzle_fig_motor_data(cfd_data: Dict) -> Tuple[Dict, List[str]]:
    """Mach/akış figürü için motor sözlüğü kurar; varsayılanları RAPORLAR.

    Döner: (motor_data, assumed_list). assumed_list figürün alt başlığına
    yazılır — çağıran gerçek gaz hâlini geçirmediyse kullanıcı bunu görür.
    """
    cd = cfd_data or {}
    assumed: List[str] = []

    throat_d = _perf_num(cd.get('throat_diameter'))
    if throat_d is None:
        a_t = _perf_num(cd.get('throat_area'))
        if a_t is None or a_t <= 0:
            raise ValueError('throat_area (m^2) or throat_diameter (m) '
                             'is required for the nozzle flow figure.')
        throat_d = float(np.sqrt(4.0 * a_t / np.pi))

    eps = _perf_num(cd.get('expansion_ratio'))
    exit_d = _perf_num(cd.get('exit_diameter'))
    if exit_d is None:
        if eps is None or eps <= 1.0:
            raise ValueError('expansion_ratio > 1 (or exit_diameter) is '
                             'required for the nozzle flow figure.')
        exit_d = throat_d * float(np.sqrt(eps))

    def _pick(key, default, label):
        val = _perf_num(cd.get(key))
        if val is None:
            assumed.append(label)
            return default
        return val

    gamma = _pick('gamma', NOZZLE_FIG_DEFAULT_GAMMA,
                  f'gamma = {NOZZLE_FIG_DEFAULT_GAMMA:.2f}')
    mw = _pick('molecular_weight', NOZZLE_FIG_DEFAULT_MW,
               f'MW = {NOZZLE_FIG_DEFAULT_MW:.0f} g/mol')
    pc_bar = _pick('chamber_pressure', NOZZLE_FIG_DEFAULT_PC_BAR,
                   f'Pc = {NOZZLE_FIG_DEFAULT_PC_BAR:.0f} bar')
    tc = _pick('chamber_temperature', NOZZLE_FIG_DEFAULT_TC_K,
               f'Tc = {NOZZLE_FIG_DEFAULT_TC_K:.0f} K')

    md = {
        'throat_diameter': throat_d,
        'exit_diameter': exit_d,
        'expansion_ratio': (exit_d / throat_d) ** 2,
        'gamma': gamma,
        'molecular_weight': mw,
        'chamber_pressure': pc_bar,
        'chamber_temperature': tc,
    }
    if _perf_num(cd.get('chamber_diameter')) is not None:
        md['chamber_diameter'] = float(cd['chamber_diameter'])
    else:
        # NozzleDesigner geleneğiyle uyumlu daralma kabulü (r_c ~ 1.5 r_t;
        # sample_nozzle_inner_contour docstring'inde belgeli). Sabit 0.1 m
        # varsayılanı büyük boğazlarda r_c < r_t üretip konturu bozuyordu.
        md['chamber_diameter'] = 1.5 * throat_d
        assumed.append('chamber diameter = 1.5 x throat diameter')

    # Kullanıcının verdiği nozul boyu GERÇEKTEN geometriye girsin: konik
    # diverjan için yarım açı L'den türetilir (alpha = atan((Re-Rt)/L)).
    # Böylece 'Nozzle Length' girdisi ölü kalmaz ve kontur ona uyar.
    l_noz = _perf_num(cd.get('nozzle_length'))
    if l_noz is not None and l_noz > 0:
        half_deg = float(np.degrees(np.arctan(
            max(exit_d - throat_d, 1e-9) / 2.0 / l_noz)))
        half_deg = float(min(max(half_deg, 1.0), 60.0))
        md['nozzle_angles'] = {'divergent_half_angle_deg': half_deg}
        md['nozzle_contour'] = {'divergent': {'type': 'conical',
                                              'half_angle': half_deg,
                                              'length': l_noz * 1000.0}}
    return md, assumed


def create_nozzle_mach_area_ratio_contour(cfd_data: Dict) -> str:
    """Nozzle Mach field from the project's quasi-1D compressible solver.

    Physics source: :class:`hrma.analysis.nozzle_flow_1d.NozzleFlow1D`
    (area-Mach relation solved with Brent on the correct branch — subsonic
    upstream of the throat, supersonic downstream — on the SAME contour the
    2D section, 3D deck and CAD export use).

    Replaces (2026-07-19 fabrication audit) a hand-rolled area law, a fixed
    gamma, a diverging Newton iteration that produced Mach numbers in the
    thousands, and an invented near-wall Mach reduction.

    Quasi-1D means the Mach number is uniform across each cross-section; the
    contour is therefore constant radially by construction and the plot says
    so. Nothing outside the real wall radius is coloured.
    """
    from hrma.analysis.nozzle_flow_1d import NozzleFlow1D

    md, assumed = _nozzle_fig_motor_data(cfd_data)
    pa = _perf_num((cfd_data or {}).get('ambient_pressure'))
    if pa is None:
        pa = NOZZLE_FIG_AMBIENT_PA
        assumed.append('ambient = 1 atm (sea level)')

    solver = NozzleFlow1D.from_motor_data(
        md, ambient_pressure=float(pa), n_stations=NOZZLE_FIG_N_STATIONS)
    sol = solver.solve(include_bartz=False)

    st = sol['stations']
    x_mm = np.asarray(st['x_mm'], dtype=float)
    r_mm = np.asarray(st['radius_mm'], dtype=float)
    mach = np.asarray(st['mach'], dtype=float)
    i_t = int(sol['throat']['index'])

    # Radyal ızgara: gerçek duvar yarıçapına ölçekli (eski sürüm sabit
    # +-50 mm kullanıyordu; büyük lülelerde duvar grafiğin dışında kalıyordu)
    r_max = float(np.max(r_mm))
    y_mm = np.linspace(-r_max, r_max, NOZZLE_FIG_N_RADIAL)
    MACH = np.tile(mach, (len(y_mm), 1))
    outside = np.abs(y_mm)[:, None] > r_mm[None, :]
    MACH = np.where(outside, np.nan, MACH)

    m_max = float(np.nanmax(MACH))
    step = max(0.1, round(m_max / 16.0, 2))

    fig = go.Figure()
    fig.add_trace(go.Contour(
        x=x_mm, y=y_mm, z=MACH,
        colorscale=SEQ_CYAN,
        contours=dict(start=0.0, end=float(np.ceil(m_max * 10) / 10),
                      size=step),
        colorbar=dict(title="Mach", x=1.02),
        connectgaps=False,
        name='Mach field',
        hovertemplate=('x %{x:.1f} mm<br>r %{y:.1f} mm<br>'
                       'M %{z:.3f}<extra></extra>')))

    for sign, show in ((1.0, True), (-1.0, False)):
        fig.add_trace(go.Scatter(
            x=x_mm, y=sign * r_mm, mode='lines',
            line=dict(color=STRUCT_INK, width=3),
            name='Nozzle wall', showlegend=show,
            hovertemplate='x %{x:.1f} mm<br>wall r %{y:.1f} mm<extra></extra>'))

    fig.add_vline(x=float(x_mm[i_t]), line_dash="dash",
                  line_color=COL_DANGER,
                  annotation_text=f"Throat (M = {mach[i_t]:.2f})")

    # Rejim: çözücünün SINIFLANDIRMASI — uydurma 'shock zone' yok
    regime = sol.get('regime') or {}
    reg_type = str(regime.get('type', 'unknown')).replace('_', ' ')
    shock = regime.get('normal_shock')
    sep = regime.get('separation')
    if isinstance(shock, dict) and shock.get('station_x_mm') is not None:
        fig.add_vline(x=float(shock['station_x_mm']), line_dash='dot',
                      line_color=COL_WARN_HI,
                      annotation_text='Normal shock (quasi-1D)')
    if isinstance(sep, dict) and sep.get('station_x_mm') is not None:
        fig.add_vline(x=float(sep['station_x_mm']), line_dash='dot',
                      line_color=COL_WARN,
                      annotation_text='Flow separation (Summerfield)')

    perf = sol.get('performance') or {}
    sub = (f"Quasi-1D compressible solution | isentropic exit M = "
           f"{float(mach[-1]):.2f}"
           f" | Ae/At = {perf.get('expansion_ratio', 0):.1f} | regime: {reg_type}")
    m_eff = _perf_num((perf.get('exit') or {}).get('mach'))
    if m_eff is not None and abs(m_eff - float(mach[-1])) > 1e-3:
        sub += f" (effective exit M = {m_eff:.2f})"
    if assumed:
        sub += '<br>Assumed (not supplied by this call): ' + ', '.join(assumed)

    fig.add_annotation(
        x=0.0, y=-0.20, xref='paper', yref='paper', xanchor='left',
        showarrow=False, align='left',
        text=('Quasi-1D: Mach is uniform across each cross-section — the '
              'radial axis shows geometry only, no boundary layer is modeled.'),
        font=dict(size=10, color=STRUCT_DIM))

    fig.update_layout(
        title={'text': ('Nozzle Mach Number Distribution'
                        f'<br><sub>{sub}</sub>'),
               'x': 0.5, 'font': {'size': 16}},
        xaxis_title='Axial Position (mm)',
        yaxis_title='Radial Position (mm)',
        autosize=True, height=620, showlegend=True,
        margin=dict(b=110))
    fig.update_yaxes(scaleanchor='x', scaleratio=1)

    return _fig_json(fig)

def _heat_flux_reference_planes(fig, time_s, x_mm, thermal_data):
    """Kullanıcının girdiği referans akıları düzlem olarak ekler.

    Bunlar HESAP DEĞİL, kullanıcı girdisidir; ad ve hover metni bunu açıkça
    söyler (eski sürüm base_heat_flux'ı hesaplanmış akı gibi sunuyordu).
    """
    td = thermal_data or {}
    t0, t1 = float(time_s[0]), float(time_s[-1])
    x0, x1 = float(x_mm[0]), float(x_mm[-1])
    grid_t = [[t0, t1], [t0, t1]]
    grid_x = [[x0, x0], [x1, x1]]

    base = _perf_num(td.get('base_heat_flux'))
    if base is not None and base > 0:
        lvl = base / 1e6
        fig.add_trace(go.Surface(
            x=grid_t, y=grid_x, z=[[lvl, lvl], [lvl, lvl]],
            showscale=False, opacity=0.25,
            colorscale=[[0, PALETTE[0]], [1, PALETTE[0]]],
            name=f'Reference flux (input) {lvl:.2f} MW/m2',
            hovertemplate=(f'User input reference flux: {lvl:.2f} MW/m2'
                           '<br>(not computed)<extra></extra>'),
            showlegend=True))

    crit = _perf_num(td.get('critical_heat_flux'))
    if crit is not None and crit > 0:
        fig.add_trace(go.Surface(
            x=grid_t, y=grid_x, z=[[crit, crit], [crit, crit]],
            showscale=False, opacity=0.25,
            colorscale=[[0, COL_DANGER], [1, COL_DANGER]],
            name=f'Critical flux (input) {crit:.2f} MW/m2',
            hovertemplate=(f'User input critical flux: {crit:.2f} MW/m2'
                           '<br>(not computed)<extra></extra>'),
            showlegend=True))


def _heat_flux_unavailable_figure(thermal_data, reason):
    """Girdi yetersizse: panel KALIR, uydurma yüzey ÇİZİLMEZ."""
    td = thermal_data or {}
    burn = _perf_num(td.get('burn_time')) or 1.0
    time_s = np.linspace(0.0, float(burn), 2)
    total_mm = 1000.0 * ((_perf_num(td.get('chamber_length')) or 0.0)
                         + (_perf_num(td.get('nozzle_length')) or 0.0))
    x_mm = np.linspace(0.0, max(total_mm, 1.0), 2)

    fig = go.Figure()
    _heat_flux_reference_planes(fig, time_s, x_mm, td)
    fig.add_annotation(
        x=0.5, y=0.5, xref='paper', yref='paper', showarrow=False,
        text=('<b>Computed wall heat flux not available for this call</b><br>'
              + reason + '<br>'
              'Only the reference levels you entered are shown; no surrogate '
              'flux field is drawn.'),
        font=dict(size=13, color=COL_WARN_HI), align='center')
    fig.update_layout(
        title={'text': ('Wall Heat Flux Distribution'
                        '<br><sub>Bartz axial profile unavailable — inputs '
                        'missing</sub>'),
               'x': 0.5, 'font': {'size': 16}},
        scene=dict(xaxis_title='Time (s)', yaxis_title='Axial Position (mm)',
                   zaxis_title='Heat Flux (MW/m2)'),
        autosize=True, height=700, showlegend=True)
    return _fig_json(fig)


def create_wall_heat_flux_waterfall_plot(thermal_data: Dict) -> str:
    """Wall heat flux q(x, t) from the project's Bartz axial solver.

    Axial profile: :meth:`HeatTransferAnalyzer.analyze_axial_profile` — the
    same Bartz correlation + Leckner gas radiation used by the cooling deck,
    evaluated on the shared nozzle contour.

    Time axis: lumped-capacitance (heat-sink) wall,
    ``rho c t_w dTw/dt = h_g (Taw - Tw)`` with the per-station Bartz
    coefficient, giving ``Tw(t) = Taw - (Taw - Tw0) exp(-t/tau)`` and
    ``q_conv(t) = q_conv(0) exp(-t/tau)``, ``tau = rho c t_w / h_g``. The flux
    therefore FALLS as the wall soaks — the physical behaviour of an uncooled
    wall. The previous version multiplied a user constant by an invented
    50 mm Gaussian and a 5 s buildup and then multiplied every cell above
    5 MW/m2 by 1.5 ("thermal runaway"), which is not a heat-transfer result
    (2026-07-19 fabrication audit).

    Keys used: ``chamber_pressure`` [bar], ``throat_area`` [m2] or
    ``throat_diameter`` [m], ``expansion_ratio``/``exit_diameter``,
    ``chamber_temperature``, ``gamma``, ``molecular_weight``,
    ``chamber_length``/``nozzle_length`` [m], ``burn_time`` [s],
    ``material``, ``wall_thickness`` [m], ``cooling_type``,
    ``initial_wall_temperature`` [K], ``base_heat_flux``/``critical_heat_flux``
    (reference levels only).
    """
    from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer

    td = thermal_data or {}
    if _perf_num(td.get('throat_area')) is None \
            and _perf_num(td.get('throat_diameter')) is None:
        return _heat_flux_unavailable_figure(
            td, 'Throat geometry (throat_area or throat_diameter) was not '
                'supplied, so the Bartz correlation cannot be evaluated.')
    try:
        md, assumed = _nozzle_fig_motor_data(td)
    except ValueError as exc:
        return _heat_flux_unavailable_figure(td, str(exc))

    material = str(td.get('material') or HEATFLUX_FIG_DEFAULT_MATERIAL)
    wall_m = _perf_num(td.get('wall_thickness')) or HEATFLUX_FIG_DEFAULT_WALL_M
    cooling = str(td.get('cooling_type') or HEATFLUX_FIG_DEFAULT_COOLING)
    if td.get('material') is None:
        assumed.append(f'wall material = {material}')
    if _perf_num(td.get('wall_thickness')) is None:
        assumed.append(f'wall thickness = {wall_m * 1000:.1f} mm')

    analyzer = HeatTransferAnalyzer()
    md_heat = dict(md)
    md_heat.setdefault('mdot_total', _perf_num(td.get('mdot_total')) or 1.0)
    prof = analyzer.analyze_axial_profile(
        md_heat, n_stations=HEATFLUX_FIG_N_STATIONS,
        material=material, wall_thickness=float(wall_m),
        cooling_type=cooling)

    x_noz = np.asarray(prof['x_mm'], dtype=float)
    h_g = np.asarray(prof['h_g'], dtype=float)
    taw = np.asarray(prof['T_recovery'], dtype=float)
    q_design = np.asarray(prof['q_MW'], dtype=float)      # MW/m2 (conv + rad)
    throat_x = float(prof['x_throat_mm'])

    # Hazne (sabit kesit) parçası: alan oranı sabit olduğundan Bartz de
    # sabittir; ilk istasyonun değerleri yukarı doğru uzatılır.
    chamber_len_mm = 1000.0 * (_perf_num(td.get('chamber_length')) or 0.0)
    if chamber_len_mm > 0:
        n_ch = max(2, int(HEATFLUX_FIG_N_STATIONS * 0.25))
        x_ch = np.linspace(0.0, chamber_len_mm, n_ch, endpoint=False)
        x_mm = np.concatenate([x_ch, x_noz + chamber_len_mm])
        h_g = np.concatenate([np.full(n_ch, h_g[0]), h_g])
        taw = np.concatenate([np.full(n_ch, taw[0]), taw])
        q_design = np.concatenate([np.full(n_ch, q_design[0]), q_design])
        throat_x += chamber_len_mm
    else:
        x_mm = x_noz

    # --- Yığın ısıl kütle (heat-sink) cidar geçicisi ---
    mat = analyzer.materials.get(material, analyzer.materials['steel'])
    rho_w = float(mat['density'])
    cp_w = float(mat['specific_heat'])
    k_w = float(mat['thermal_conductivity'])
    tw0 = _perf_num(td.get('initial_wall_temperature')) or 293.15
    if _perf_num(td.get('initial_wall_temperature')) is None:
        assumed.append('initial wall temperature = 293.15 K')

    # Dış (soğutucu) taraf direnci — ısı modülünün KENDİ katsayısı, kopya yok
    h_coolant = float(analyzer._coolant_side_coefficient(md_heat, cooling))
    r_out = float(wall_m) / k_w + 1.0 / max(h_coolant, 1e-9)   # m2*K/W
    # Denge cidar sıcaklığı: modülün eksenel profil çözümünden (radyasyon dahil)
    t_eq = np.asarray(prof['T_wall_eq'], dtype=float)
    if chamber_len_mm > 0:
        t_eq = np.concatenate([np.full(len(x_mm) - len(t_eq), t_eq[0]), t_eq])

    burn_time = _perf_num(td.get('burn_time')) or 1.0
    time_s = np.linspace(0.0, float(burn_time), HEATFLUX_FIG_N_TIME)
    # tau = rho*c*t_w / (h_g + 1/R_out): giriş ve çıkış yollarının toplamı
    tau = (rho_w * cp_w * float(wall_m)
           / np.maximum(h_g + 1.0 / r_out, 1e-6))                   # s
    T, X = np.meshgrid(time_s, x_mm)                                # (nx, nt)
    TAU = np.tile(tau[:, None], (1, len(time_s)))
    TAW = np.tile(taw[:, None], (1, len(time_s)))
    TEQ = np.tile(t_eq[:, None], (1, len(time_s)))
    HG = np.tile(h_g[:, None], (1, len(time_s)))
    TW = TEQ - (TEQ - tw0) * np.exp(-T / TAU)
    HEAT_FLUX_MW = HG * (TAW - TW) / 1e6

    # Malzeme sınırı: cidar erime noktasını geçtikten sonra model geçersizdir;
    # o hücreler BOŞ bırakılır (uydurma bir "hâlâ çalışıyor" yüzeyi yok).
    t_melt = _perf_num(mat.get('melting_point'))
    t_service = _perf_num(mat.get('allowable_temperature'))
    limit_note = ''
    if t_melt:
        beyond = TW > t_melt
        if beyond.any():
            HEAT_FLUX_MW = np.where(beyond, np.nan, HEAT_FLUX_MW)
            first = float(T[beyond].min())
            limit_note = (f' Wall reaches the {material} melting point '
                          f'({t_melt:.0f} K) at t = {first:.2f} s; the surface '
                          'is left blank beyond that.')
    if t_service and (TW > t_service).any():
        first_s = float(T[TW > t_service].min())
        limit_note += (f' Service limit ({t_service:.0f} K) is exceeded from '
                       f't = {first_s:.2f} s.')

    biot = float(np.max(h_g) * float(wall_m) / k_w)

    fig = go.Figure()
    fig.add_trace(go.Surface(
        x=T, y=X, z=HEAT_FLUX_MW,
        colorscale='Hot',
        name='Convective flux (Bartz, heat-sink wall)',
        colorbar=dict(title="q_conv (MW/m2)", x=1.02), showscale=True,
        hovertemplate=('t %{x:.2f} s<br>x %{y:.1f} mm<br>'
                       'q %{z:.2f} MW/m2<extra></extra>')))

    # Modülün tasarım akısı (taşınım + Leckner radyasyonu, referans soğutulmuş
    # cidarda) — geçici yüzeyle karşılaştırma için t=0 kenarında çizgi
    fig.add_trace(go.Scatter3d(
        x=np.zeros_like(x_mm), y=x_mm, z=q_design, mode='lines',
        line=dict(color=PALETTE[0], width=5),
        name='Design flux at reference cooled wall (conv + radiation)',
        hovertemplate=('x %{y:.1f} mm<br>q_design %{z:.2f} MW/m2'
                       '<extra></extra>')))

    fig.add_trace(go.Scatter3d(
        x=[0.0, float(time_s[-1])], y=[throat_x, throat_x],
        z=[0.0, 0.0], mode='lines',
        line=dict(color=PALETTE[0], width=4, dash='dash'),
        name='Throat station'))

    _heat_flux_reference_planes(fig, time_s, x_mm, td)

    sub = (f"Bartz axial profile | peak design flux "
           f"{np.max(q_design):.2f} MW/m2 at the throat | "
           f"lumped-capacitance wall ({material}, {wall_m * 1000:.1f} mm), "
           f"Biot_max = {biot:.2f}")
    if assumed:
        sub += '<br>Assumed (not supplied by this call): ' + ', '.join(assumed)

    note = ('Time dependence is the wall soak of a lumped-capacitance wall '
            'toward the equilibrium temperature of the selected cooling: '
            'q_conv falls as Tw rises. No "thermal runaway" multiplier is '
            'applied — exceeding a flux limit raises wall temperature, it '
            'does not raise the flux.' + limit_note)
    if biot > 0.1:
        note += (f' Biot number {biot:.2f} > 0.1: the lumped wall model is '
                 'approximate here, treat the transient as indicative.')
    fig.add_annotation(
        x=0.0, y=-0.02, xref='paper', yref='paper', xanchor='left',
        showarrow=False, align='left', text=note,
        font=dict(size=10, color=STRUCT_DIM))

    fig.update_layout(
        title={'text': f'Wall Heat Flux Distribution<br><sub>{sub}</sub>',
               'x': 0.5, 'font': {'size': 16}},
        scene=dict(
            xaxis_title='Time (s)',
            yaxis_title='Axial Position (mm)',
            zaxis_title='Heat Flux (MW/m2)',
            camera=dict(eye=dict(x=1.3, y=1.3, z=1.3))),
        autosize=True, height=700, showlegend=True,
        legend=_legend_below(-0.08), margin=dict(b=120))

    return _fig_json(fig)


# ============================================================
# Improved Visualization Functions (merged from visualization_improved.py)
# ============================================================

# Kesitte kullanılan enjektör tipi takma adları → kanonik ad. Yeni ARGE
# zinciri ('impinging_doublet', 'coax_swirl' …) ve eski /calculate zinciri
# ('showerhead', 'pintle', 'swirl', 'impingement', 'coaxial') aynı çizim
# dallarına eşlenir.
INJECTOR_TYPE_ALIASES = {
    'showerhead': 'showerhead',
    'pintle': 'pintle',
    'swirl': 'swirl',
    'coax_swirl': 'coaxial',
    'coaxial': 'coaxial',
    'impingement': 'impingement',
    'impinging': 'impingement',
    'impinging_doublet': 'impingement',
    'impinging_triplet': 'impingement',
    'like_impinging': 'impingement',
}


def resolve_injector_type(motor_data):
    """motor_data'dan kanonik enjektör tipini çözer (bilinmeyen → showerhead)."""
    inj = (motor_data or {}).get('injector_design') or {}
    raw = inj.get('injector_type') or inj.get('type') or 'showerhead'
    return INJECTOR_TYPE_ALIASES.get(str(raw).lower(), 'showerhead')


def _add_injector_cross_section(fig, motor_data, z0, thickness, rc,
                                plate_color, ink, dim):
    """Enjektör plakasını ve TİPE ÖZEL iç geometriyi eksenel kesite ekler.

    showerhead  : plaka + eksenel orifis işaretleri
    pintle      : plaka + eksene uzanan merkez gövde + uç radyal jetler + anülüs
    swirl       : plaka + teğetsel yuva sembolleri + sprey koni açısı çizgileri
    impingement : plaka + açılı delik çiftleri (çarpışan jetler)
    coaxial     : plaka + iç merkez jeti + dış halka (anülüs)
    """
    inj = (motor_data or {}).get('injector_design') or {}
    # GERÇEK enjektör geometrisi burada: design_injector() tam çıktısı
    # (pintle_geometry, swirl_geometry, pattern.impingement, atomization).
    # Eski sürüm bu sözlüğü hiç okumuyor, pintle çapını/anülüs boşluğunu
    # kamara yarıçapının sabit oranlarından ÜRETİP hover'da sayı olarak
    # veriyordu (2026-07-19 uydurma denetimi).
    detail = (motor_data or {}).get('injector_design_detail') or {}
    pintle_geo = detail.get('pintle_geometry') or {}
    swirl_geo = detail.get('swirl_geometry') or {}
    atomization = detail.get('atomization') or {}
    impinge_geo = ((detail.get('pattern') or {}).get('impingement')) or {}
    kind = resolve_injector_type(motor_data)
    n_ori = int(_num_safe(inj.get('number_of_orifices'), 12))
    z1 = z0 + thickness
    r_plate = rc - 0.4

    label = {
        'showerhead': 'Showerhead injector plate',
        'pintle': 'Pintle injector',
        'swirl': 'Swirl injector plate',
        'impingement': 'Impinging-jet injector plate',
        'coaxial': 'Coaxial injector plate',
    }[kind]

    fig.add_trace(go.Scatter(
        x=[z0, z0, z1, z1, z0],
        y=[-r_plate, r_plate, r_plate, -r_plate, -r_plate],
        fill='toself', fillcolor=plate_color, mode='lines',
        line=dict(color='#8a6a34', width=1.4), name='Injector plate',
        hoverinfo='text', hoveron='fills',
        hovertext=f'{label}<br>Plate thickness: {thickness:.1f} mm'))

    n_marks = max(3, min(n_ori // 2 + 1, 9))

    if kind == 'showerhead':
        ori_y = np.linspace(-0.62 * rc, 0.62 * rc, n_marks)
        fig.add_trace(go.Scatter(
            x=[z1] * len(ori_y), y=ori_y.tolist(), mode='markers',
            marker=dict(size=5, color='#10151a', symbol='circle'),
            name='Orifices', showlegend=False,
            hovertemplate=(f'Showerhead pattern: {n_ori} axial orifices'
                           '<extra></extra>')))

    elif kind == 'pintle':
        # Merkez gövde: plakadan odaya uzanır; ucunda radyal jetler.
        # Öncelik sırası: çözücünün pintle_geometry çıktısı -> injector_design
        # takma adları -> yalnız ÇİZİM için oran (bu durumda hover sayı VERMEZ).
        d_p_real = _perf_num(pintle_geo.get('d_pintle_mm'))
        if d_p_real is None:
            d_p_real = _perf_num(inj.get('pintle_diameter_mm'))
        if d_p_real is None:
            d_p_real = _perf_num(inj.get('pintle_diameter'))
        gap_real = _perf_num(pintle_geo.get('annulus_gap_mm'))
        if gap_real is None:
            gap_real = _perf_num(inj.get('annulus_gap_mm'))
        if gap_real is None:
            gap_real = _perf_num(inj.get('gap'))
        skip_real = _perf_num(pintle_geo.get('skip_distance_mm'))

        d_p = d_p_real if d_p_real is not None else 0.22 * 2 * rc
        r_p = max(1.5, min(d_p / 2.0, 0.45 * rc))
        post_len = max(2.5 * r_p, 0.9 * thickness)
        gap = gap_real if gap_real is not None else max(0.5, 0.06 * r_p)
        post_rows = (f'D_pintle: {d_p_real:.2f} mm' if d_p_real is not None
                     else 'D_pintle: not reported by the solver (schematic)')
        if skip_real is not None:
            post_rows += f'<br>Skip distance: {skip_real:.2f} mm'
        else:
            post_rows += '<br>Skip distance: not reported'
        n_rad = _perf_num(pintle_geo.get('n_radial_holes'))
        d_rad = _perf_num(pintle_geo.get('radial_hole_d_mm'))
        if n_rad is not None and d_rad is not None:
            post_rows += (f'<br>Radial holes: {int(n_rad)} x dia '
                          f'{d_rad:.2f} mm')
        gap_rows = (f'Gap: {gap_real:.3f} mm' if gap_real is not None
                    else 'Gap: not reported by the solver (schematic)')
        fig.add_trace(go.Scatter(
            x=[z1, z1 + post_len, z1 + post_len, z1, z1],
            y=[-r_p, -r_p, r_p, r_p, -r_p],
            fill='toself', fillcolor='rgba(122,136,150,0.9)', mode='lines',
            line=dict(color=ink, width=1.3), name='Pintle post',
            hoverinfo='text', hoveron='fills',
            hovertext='Pintle post<br>' + post_rows))
        # Uç radyal jet işaretleri (dışa doğru oklar)
        z_tip = z1 + post_len * 0.85
        for sgn in (1, -1):
            fig.add_annotation(x=z_tip, y=sgn * (r_p + 0.5 * rc * 0.35),
                               ax=z_tip, ay=sgn * r_p,
                               xref='x', yref='y', axref='x', ayref='y',
                               showarrow=True, arrowhead=2, arrowsize=1,
                               arrowwidth=1.6, arrowcolor='#ff8c33')
        # Anülüs (pintle çevresindeki eksenel oks tabakası). Gerçek boşluk
        # motor ölçeğinde (mm mertebesi) görünmez kalır; bant GÖRSEL olarak
        # kalınlaştırılır, gerçek değer etiket/hover'da verilir.
        gap_vis = max(gap, 0.035 * rc)
        for sgn, show in ((1, True), (-1, False)):
            fig.add_trace(go.Scatter(
                x=[z1, z1 + post_len, z1 + post_len, z1, z1],
                y=[sgn * r_p, sgn * r_p, sgn * (r_p + gap_vis),
                   sgn * (r_p + gap_vis), sgn * r_p],
                fill='toself', fillcolor='rgba(0,229,255,0.22)', mode='lines',
                line=dict(color='#00e5ff', width=1.2, dash='dot'),
                name=('Annulus gap %.3f mm' % gap_real if gap_real is not None
                      else 'Annulus gap (not reported)'),
                showlegend=show,
                hoverinfo='text', hoveron='fills',
                hovertext=('Annular oxidizer sheet<br>' + gap_rows
                           + '<br>(band drawn to scale-independent width)')))

    elif kind == 'swirl':
        # Teğetsel yuva sembolleri: plaka içinde eğik kısa çizgiler
        slot_y = np.linspace(-0.62 * rc, 0.62 * rc, min(n_marks, 6))
        for i, y in enumerate(slot_y):
            fig.add_trace(go.Scatter(
                x=[z0 + 0.15 * thickness, z1 + 0.6 * thickness],
                y=[y - 0.07 * rc, y + 0.07 * rc], mode='lines',
                line=dict(color='#ff8c33', width=3),
                name='Tangential slots', showlegend=(i == 0),
                legendgroup='swirl_slots',
                hovertemplate=('Tangential slot (swirl generator)'
                               '<extra></extra>')))
        # Sprey koni açısı çizgileri
        # Gerçek sprey yarı açısı: atomization.spray_cone_half_angle_deg
        # (Giffen-Muraszew swirl çözümünden) -> injector_design.spray_angle.
        half_real = _perf_num(atomization.get('spray_cone_half_angle_deg'))
        if half_real is None:
            half_real = _perf_num(swirl_geo.get('spray_cone_half_angle_deg'))
        if half_real is None:
            ang = _perf_num(inj.get('spray_angle'))
            half_real = (ang / 2.0) if ang is not None else None
        cone_is_real = half_real is not None
        half = max(5.0, min((half_real if cone_is_real else 45.0), 80.0))
        reach = 1.4 * rc
        dz = reach / max(np.tan(np.radians(half)), 0.1)
        for sgn, show in ((1, True), (-1, False)):
            fig.add_trace(go.Scatter(
                x=[z1, z1 + dz], y=[0, sgn * reach], mode='lines',
                line=dict(color=dim, width=1.5, dash='dash'),
                name=(f'Spray cone 2θ={2*half:.0f}°' if cone_is_real
                      else 'Spray cone (angle not reported)'),
                showlegend=show,
                hovertemplate=(
                    (f'Hollow-cone spray<br>Full angle: {2*half:.1f} deg'
                     if cone_is_real else
                     'Hollow-cone spray<br>Cone angle not reported by the '
                     'solver (drawn schematically)') + '<extra></extra>')))

    elif kind == 'impingement':
        # Açılı delik çiftleri: her çift eksene doğru yakınsayan iki çizgi
        half_real = _perf_num(impinge_geo.get('half_angle_deg'))
        if half_real is None:
            ang = _perf_num(inj.get('impingement_angle_deg'))
            half_real = (ang / 2.0) if ang is not None else None
        imp_is_real = half_real is not None
        half = max(10.0, min((half_real if imp_is_real else 30.0), 60.0))
        n_pairs = max(2, min(int(_num_safe(inj.get('n_pairs'), max(2, n_ori // 2))), 5))
        centers = np.linspace(-0.55 * rc, 0.55 * rc, n_pairs)
        spread = max(0.06 * rc, 1.5)
        reach = max(0.35 * rc, 6.0)
        dz = reach / max(np.tan(np.radians(half)), 0.1)
        for i, yc in enumerate(centers):
            for sgn in (1, -1):
                fig.add_trace(go.Scatter(
                    x=[z1, z1 + dz], y=[yc + sgn * spread, yc], mode='lines',
                    line=dict(color='#ff8c33', width=2),
                    name=(f'Impinging pairs (2θ={2*half:.0f}°)' if imp_is_real
                          else 'Impinging pairs (angle not reported)'),
                    showlegend=(i == 0 and sgn == 1),
                    legendgroup='impinge',
                    hovertemplate=(
                        (f'Like-on-like doublet<br>Included angle: '
                         f'{2*half:.1f} deg'
                         if imp_is_real else
                         'Like-on-like doublet<br>Included angle not reported '
                         'by the solver (drawn schematically)')
                        + '<extra></extra>')))

    else:  # coaxial
        d_in_real = _perf_num(inj.get('inner_jet_diameter'))
        if d_in_real is None:
            d_in_real = _perf_num(pintle_geo.get('d_pintle_mm'))
        gap_real = _perf_num(inj.get('annulus_gap'))
        if gap_real is None:
            gap_real = _perf_num(pintle_geo.get('annulus_gap_mm'))
        d_in = d_in_real if d_in_real is not None else 0.18 * 2 * rc
        r_in = max(1.2, min(d_in / 2.0, 0.35 * rc))
        gap = gap_real if gap_real is not None else max(0.6, 0.25 * r_in)
        jet_len = max(0.6 * thickness, 5.0)
        fig.add_trace(go.Scatter(
            x=[z1, z1 + jet_len, z1 + jet_len, z1, z1],
            y=[-r_in, -r_in, r_in, r_in, -r_in],
            fill='toself', fillcolor='rgba(0,229,255,0.20)', mode='lines',
            line=dict(color='#00e5ff', width=1.4), name='Inner jet',
            hoverinfo='text', hoveron='fills',
            hovertext=('Coaxial inner jet<br>'
                       + (f'Diameter: {d_in_real:.2f} mm'
                          if d_in_real is not None else
                          'Diameter: not reported by the solver (schematic)'))))
        for sgn, show in ((1, True), (-1, False)):
            fig.add_trace(go.Scatter(
                x=[z1, z1 + jet_len, z1 + jet_len, z1, z1],
                y=[sgn * (r_in + 0.6), sgn * (r_in + 0.6),
                   sgn * (r_in + 0.6 + gap), sgn * (r_in + 0.6 + gap),
                   sgn * (r_in + 0.6)],
                fill='toself', fillcolor='rgba(255,140,51,0.25)', mode='lines',
                line=dict(color='#ff8c33', width=1.2), name='Outer annulus',
                showlegend=show, hoverinfo='text', hoveron='fills',
                hovertext=('Coaxial outer annulus<br>'
                           + (f'Gap: {gap_real:.3f} mm'
                              if gap_real is not None else
                              'Gap: not reported by the solver (schematic)'))))


def _num_safe(v, fb):
    """Modül düzeyi sayı dönüştürücü (yerel _num'ların dışa açık eşi)."""
    try:
        f = float(v)
        return f if np.isfinite(f) else fb
    except (TypeError, ValueError):
        return fb


def create_improved_motor_cross_section(motor_data, motor_type='hybrid'):
    """Çözücü geometrisinden mühendislik eksenel kesit çizimi.

    Kamara duvarı + baş kapak, fenolik liner, yakıt grain'i (başlangıç ve
    son port), enjektör plakası ve GERÇEK nozul konturu (kosinüs konverjan,
    Rao boğaz yayı, konik doğru ya da bell Bézier diverjan) tek kesitte,
    çift oklu ölçü çizgileriyle gösterilir. Tüm boyutlar motor_results'tan
    okunur; eksikler güvenli varsayılanlara düşer.

    motor_type bileşen seçimini belirler:
      'hybrid' → grain + liner + enjektör (varsayılan, eski davranış)
      'solid'  → grain + liner var, enjektör YOK (port = çekirdek/core)
      'liquid' → grain/liner YOK, enjektör var
    """
    has_grain = motor_type in ('hybrid', 'solid')
    has_injector = motor_type in ('hybrid', 'liquid')

    def _num(v, fb):
        try:
            f = float(v)
            return f if np.isfinite(f) else fb
        except (TypeError, ValueError):
            return fb

    # ---------------- Boyutlar (mm) ----------------
    L = _num(motor_data.get('chamber_length'), 0.3) * 1000
    D_ch = _num(motor_data.get('chamber_diameter'), 0.1) * 1000
    d_t = _num(motor_data.get('throat_diameter'), 0.02) * 1000
    d_e = _num(motor_data.get('exit_diameter'), 0.08) * 1000
    rc, rt, re = D_ch / 2, d_t / 2, d_e / 2

    contour = motor_data.get('nozzle_contour') or {}
    div = contour.get('divergent') or {}
    angles = motor_data.get('nozzle_angles') or {}
    gd = motor_data.get('grain_design') or {}
    struct = motor_data.get('structural_analysis') or {}

    noz_type = div.get('type') or angles.get('nozzle_type') or 'conical'
    theta_n = _num(div.get('throat_angle'), 30.0)
    theta_e = _num(div.get('exit_angle'), 8.0)
    # Açı alt sınırı 1°: bozuk/sıfır girdide tan(0) bölme-sıfır → inf/null
    # koordinat üretmesin (hakem bulgusu — production akışı 15/30° üretir)
    half_angle = max(1.0, _num(div.get('half_angle'),
                               _num(angles.get('divergent_half_angle_deg'), 15.0)))
    # (Kontur uzunlukları/yayı sample_nozzle_inner_contour içinde hesaplanır;
    # burada yalnız açı etiketlerinde kullanılan değerler tutulur)

    wall_noz = _num((motor_data.get('nozzle_geometry') or {}).get('wall_thickness'),
                    max(3.0, 0.1 * d_t))
    wall_case = _num((struct.get('chamber_analysis') or {}).get('recommended_thickness'),
                     0.045 * D_ch)
    wall_case = min(max(wall_case, 3.0), 0.12 * D_ch)
    liner_t = min(max(0.02 * D_ch, 1.5), 5.0)
    cap_t = min(max(1.6 * wall_case, 8.0), 0.3 * rc + 8.0)

    L_g = _num(gd.get('grain_length_mm'),
               _num(motor_data.get('grain_length'), 0.8 * L / 1000) * 1000)
    L_g = min(L_g, 0.92 * L)
    r_p0 = _num(gd.get('port_diameter_initial_mm'),
                _num(motor_data.get('port_diameter_initial'), 0.03) * 1000) / 2
    r_pf = _num(gd.get('port_diameter_final_mm'),
                _num(motor_data.get('port_diameter_final'), 0.05) * 1000) / 2
    r_go = rc - liner_t
    r_pf = min(r_pf, r_go - 1.0)
    r_p0 = min(r_p0, r_pf)

    # Eksen: z=0 baş kapak iç yüzü; grain önünde %35 ön oda payı
    slack = max(4.0, L - L_g)
    zg0, zg1 = 0.35 * slack, 0.35 * slack + L_g

    # ---------------- Nozul iç konturu (ortak örnekleyici) ----------------
    # Geometri tek kaynaktan: 2D kesit, 3D görselleştirme ve CAD aynı konturu
    # kullanır (hrma.engines.nozzle_design.sample_nozzle_inner_contour)
    noz_pts, noz_meta = sample_nozzle_inner_contour(motor_data)
    noz_z = np.array([L + zz for zz, _ in noz_pts])
    noz_r = np.array([rr for _, rr in noz_pts])
    z_throat = L + noz_meta['z_throat']
    z_exit = L + noz_meta['z_exit']

    # ---------------- Çizim ----------------
    fig = go.Figure()

    # Dijital blueprint paleti (koyu tema — sayfa geneliyle uyumlu)
    INK = '#d7e3ee'
    DIM = '#22d3ee'
    C_CASE, C_LINER = 'rgba(148,163,180,0.85)', 'rgba(96,104,114,0.95)'
    C_GRAIN, C_INJ = 'rgba(178,116,68,0.92)', 'rgba(210,177,116,0.95)'
    C_NOZ = 'rgba(122,136,150,0.9)'

    def poly(z_pts, r_pts, fill, name, hover, legend=True, lg=None):
        fig.add_trace(go.Scatter(
            x=list(z_pts) + [z_pts[0]], y=list(r_pts) + [r_pts[0]],
            fill='toself', fillcolor=fill, mode='lines',
            line=dict(color=INK, width=1.4),
            name=name, legendgroup=lg or name, showlegend=legend,
            hoverinfo='text', hovertext=hover, hoveron='fills'))

    def mirrored(z_pts, r_pts, fill, name, hover, lg=None):
        poly(z_pts, r_pts, fill, name, hover, legend=True, lg=lg)
        poly(z_pts, [-r for r in r_pts], fill, name, hover, legend=False, lg=lg)

    # Kamara duvarı + baş kapak (tek katı)
    case_z = [-cap_t, -cap_t, L, L, 0, 0]
    case_r = [0, rc + wall_case, rc + wall_case, rc, rc, 0]
    mirrored(case_z, case_r, C_CASE, 'Chamber wall',
             f'Chamber wall<br>Thickness: {wall_case:.1f} mm<br>Bore: Ø{D_ch:.1f} mm')

    if has_grain:
        # Fenolik liner
        liner_z = [2, 2, L - 2, L - 2]
        liner_r = [r_go, rc - 0.2, rc - 0.2, r_go]
        mirrored(liner_z, liner_r, C_LINER, 'Liner (insulation)',
                 f'Phenolic liner<br>Thickness: {liner_t:.1f} mm')

        # Yakıt grain'i (katıda port = çekirdek/core, son port = grain dışı)
        grain_z = [zg0, zg0, zg1, zg1]
        grain_r = [r_p0, r_go, r_go, r_p0]
        mirrored(grain_z, grain_r, C_GRAIN, 'Fuel grain',
                 (f'Fuel grain<br>Length: {L_g:.1f} mm<br>Port (initial): Ø{2*r_p0:.1f} mm'
                  f'<br>Port (final): Ø{2*r_pf:.1f} mm<br>Web: {r_pf - r_p0:.1f} mm'))

    # Enjektör plakası + tipe özel iç geometri (D1 ajanı gerçek enjektör
    # tipini motor sonucuna kablolar; tip bilinmiyorsa showerhead varsayılır)
    if has_injector:
        inj_t = min(max(0.9 * cap_t, 6.0), 24.0)
        _add_injector_cross_section(
            fig, motor_data, z0=4.0, thickness=inj_t, rc=rc,
            plate_color=C_INJ, ink=INK, dim=DIM)

    # Nozul duvarı (iç kontur + duvar ofseti)
    noz_wall_z = list(noz_z) + list(noz_z[::-1])
    noz_wall_r = list(noz_r) + list((noz_r + wall_noz)[::-1])
    mirrored(noz_wall_z, noz_wall_r, C_NOZ, 'Nozzle',
             (f'Nozzle ({noz_type})<br>Throat: Ø{d_t:.1f} mm<br>Exit: Ø{d_e:.1f} mm'
              f'<br>Expansion ratio: {(re/rt)**2:.1f}<br>Wall: {wall_noz:.1f} mm'))

    # Son port çapı (kesikli) — eksenel kesitte yatay çizgi çifti
    if has_grain:
        for sgn, show in ((1, True), (-1, False)):
            fig.add_trace(go.Scatter(
                x=[zg0, zg1], y=[sgn * r_pf, sgn * r_pf], mode='lines',
                line=dict(color='#d1495b', width=2, dash='dash'),
                name=f'Final port Ø{2*r_pf:.1f} mm', showlegend=show,
                hovertemplate=f'End-of-burn port: Ø{2*r_pf:.1f} mm<extra></extra>'))

    # Merkez ekseni (dash-dot, mühendislik konvansiyonu)
    fig.add_trace(go.Scatter(
        x=[-cap_t - 22, z_exit + 15], y=[0, 0], mode='lines',
        line=dict(color='#5f7c8c', width=1, dash='dashdot'),
        name='Centerline', showlegend=False, hoverinfo='skip'))

    # Boğaz istasyonu
    fig.add_trace(go.Scatter(
        x=[z_throat, z_throat], y=[-rt, rt],
        mode='lines', line=dict(color=DIM, width=1, dash='dot'),
        name='Throat', showlegend=False,
        hovertemplate=f'Throat station<br>Ø{d_t:.1f} mm<extra></extra>'))

    # ---------------- Ölçü çizgileri ----------------
    r_out = rc + wall_case

    def dim_h(x0, x1, y, label, above=True):
        fig.add_trace(go.Scatter(
            x=[x0, x1], y=[y, y], mode='lines',
            line=dict(color=DIM, width=1), showlegend=False, hoverinfo='skip'))
        for xe in (x0, x1):  # uzatma çizgileri
            fig.add_trace(go.Scatter(
                x=[xe, xe], y=[y - 4, y + 4], mode='lines',
                line=dict(color=DIM, width=1), showlegend=False, hoverinfo='skip'))
        xm = (x0 + x1) / 2
        for xe in (x0, x1):  # çift ok
            fig.add_annotation(x=xe, y=y, ax=xm, ay=y, axref='x', ayref='y',
                               text='', showarrow=True, arrowhead=2,
                               arrowsize=1, arrowwidth=1.2, arrowcolor=DIM)
        fig.add_annotation(x=xm, y=y + (9 if above else -9), text=label,
                           showarrow=False, font=dict(size=11, color=DIM))

    def dim_v(x, y0, y1, label, side=1):
        fig.add_trace(go.Scatter(
            x=[x, x], y=[y0, y1], mode='lines',
            line=dict(color=DIM, width=1), showlegend=False, hoverinfo='skip'))
        ym = (y0 + y1) / 2
        for ye in (y0, y1):
            fig.add_annotation(x=x, y=ye, ax=x, ay=ym, axref='x', ayref='y',
                               text='', showarrow=True, arrowhead=2,
                               arrowsize=1, arrowwidth=1.2, arrowcolor=DIM)
        fig.add_annotation(x=x, y=ym, text=label, showarrow=False, textangle=-90,
                           xshift=side * 14, font=dict(size=11, color=DIM))

    dim_h(0, L, r_out + 16, f'L<sub>chamber</sub> = {L:.0f} mm')
    if has_grain:
        dim_h(zg0, zg1, r_out + 42, f'Grain = {L_g:.0f} mm')
    dim_h(-cap_t, z_exit, -(max(r_out, re + wall_noz) + 30),
          f'L<sub>total</sub> = {z_exit + cap_t:.0f} mm', above=False)
    dim_v(-cap_t - 18, -rc, rc, f'Ø<sub>c</sub> = {D_ch:.1f} mm', side=-1)
    dim_v(z_throat, -rt, rt, f'Ø<sub>t</sub> = {d_t:.1f} mm', side=1)
    dim_v(z_exit + 12, -re, re, f'Ø<sub>e</sub> = {d_e:.1f} mm', side=1)

    # Diverjan açı etiketi — lüle ALTINA konur. Eski konum (üst kontur
    # ortası) kısa lülelerde Ø_t/Ø_e dikey ölçü yazılarıyla üst üste
    # biniyordu (yatay 130 px'lik metin dar boğaz-çıkış bandını aşıyor).
    # Altta dikey etiketler yok (y=0 merkezli bantta kalırlar) ve
    # L_toplam ölçü çizgisi daha aşağıda (r_out+30).
    if noz_type == 'conical':
        angle_txt = f'Conical divergent: α = {half_angle:.0f}°'
    else:
        angle_txt = (f'{noz_type.capitalize()} contour: θ<sub>n</sub> = '
                     f'{theta_n:.0f}° → θ<sub>e</sub> = {theta_e:.0f}°')
    # Dikey Ø yazıları PİKSEL uzayında ~80 px uzunluğunda (metin ölçekten
    # bağımsız); yalnız veri-mm ofseti düşük px/mm ölçekte yetmiyor. Bu
    # yüzden konum iki bileşenli: veri-y lüle metalinin hemen altı
    # (geometriyle ölçeklenir) + yshift=-48 px (Ø yazılarının y=0 merkezli
    # ±40 px bandını her ölçekte temizler).
    fig.add_annotation(x=z_throat + 0.55 * (z_exit - z_throat),
                       y=-(max(rt, re) + wall_noz), yshift=-48, text=angle_txt,
                       showarrow=False, font=dict(size=11, color=INK))

    # ---------------- Yerleşim (dijital blueprint) ----------------
    # Eksen aralıkları AÇIKÇA verilir; scaleanchor KULLANILMAZ. Plotly
    # 1.58.5'te scaleanchor+autorange gizli konteynerde aralığı yüz binlere
    # şişiriyor, constrain='domain' ile de domain'i sıfıra çökertiyordu
    # (tutarlı ~185x hata). 1:1 ölçek yerine, x aralığı nominal çizim alanı
    # en-boy oranına (~3.9) eşitlenerek yaklaşık gerçek ölçek elde edilir —
    # deterministik, patlamaz.
    x_min = -cap_t - 45
    x_max = z_exit + 60
    y_max = max(r_out + 62, re + wall_noz + 48)
    ASPECT = 3.9  # nominal iç çizim alanı (genişlik/yükseklik), height=520+marj
    x_span_needed = 2.0 * y_max * ASPECT
    x_span = x_max - x_min
    if x_span < x_span_needed:
        pad = 0.5 * (x_span_needed - x_span)
        x_min -= pad
        x_max += pad
    else:
        y_max = 0.5 * x_span / ASPECT
    fig.update_layout(
        title=dict(text='MOTOR AXIAL CROSS-SECTION — SOLVER GEOMETRY',
                   x=0.5, font=dict(size=15, color='#eaf7fb')),
        xaxis=dict(title='Axial position (mm)', showgrid=True,
                   gridcolor='rgba(0,229,255,0.07)', zeroline=False,
                   range=[x_min, x_max],
                   tickfont=dict(color='#7d97a5'),
                   title_font=dict(color='#7d97a5')),
        yaxis=dict(title='Radius (mm)', showgrid=True,
                   gridcolor='rgba(0,229,255,0.07)', zeroline=False,
                   range=[-y_max, y_max],
                   tickfont=dict(color='#7d97a5'),
                   title_font=dict(color='#7d97a5')),
        plot_bgcolor='rgba(8,16,28,0.35)', paper_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#cfe8f2'),
        legend=dict(orientation='h', yanchor='bottom', y=1.02,
                    xanchor='center', x=0.5, font=dict(size=11, color='#7d97a5'),
                    bgcolor='rgba(6,13,24,0.7)',
                    bordercolor='rgba(0,229,255,0.2)'),
        hovermode='closest',
        margin=dict(l=70, r=40, t=90, b=60),
        height=520,
    )

    return _fig_json(fig)


def create_improved_injector_design(injector_data):
    """Improved 2D injector design visualisation (type-aware)."""

    raw = injector_data.get('type', 'showerhead')
    kind = INJECTOR_TYPE_ALIASES.get(str(raw).lower(), 'showerhead')

    if kind in ('showerhead', 'impingement'):
        # Impinging plakası da yüz görünüşünde delik deseni olarak okunur
        return create_showerhead_with_tooltips(injector_data)
    elif kind in ('pintle', 'coaxial'):
        # Koaksiyel eleman eş merkezlidir: pintle kesiti aynı geometriyi
        # (merkez gövde + anülüs) doğru gösterir; utils koaksiyel çıktısı
        # outer_diameter / pintle_diameter / gap takma adlarını sağlar.
        return create_pintle_cross_section(injector_data)
    else:
        return create_swirl_injector(injector_data)


#: Enjektör plakası kalınlık/çap oranı yerine kullanılan kaba çizim payı:
#: delik deseninin plaka kenarına değmemesi için bırakılan boşluk oranı.
INJ_PLATE_PATTERN_FILL = 0.80


def _injector_total_mdot(injector_data):
    """Enjektörden geçen TOPLAM debiyi [kg/s] çözer; kaynağını da döndürür.

    Döner: (mdot | None, kaynak_metni)

    Eski sürüm `injector_data.get('mdot_ox', 1.0)` yazıyordu; bu anahtar
    InjectorDesign.calculate() çıktısında YOK, dolayısıyla payda HER ZAMAN
    1.0 kg/s idi ve delik başı debi tamamen uyduruk çıkıyordu (2026-07-19
    uydurma denetimi). Artık debi ya gerçekten verilir, ya Cd*rho*A*v
    bağıntısından türetilir, ya da 'not available' denir.
    """
    d = injector_data or {}
    for key in ('mdot_ox', 'mdot_kg_s', 'oxidizer_flow_rate_kg_s',
                'mass_flow_rate', 'mdot_total'):
        val = _perf_num(d.get(key))
        if val is not None and val > 0:
            return float(val), f'solver field {key}'
    # Türetme: mdot = Cd * rho * A_inj * v_exit (A_inj mm^2 gelir)
    rho = _perf_num(d.get('oxidizer_density'))
    area_mm2 = _perf_num(d.get('injection_area'))
    vel = _perf_num(d.get('exit_velocity'))
    cd = _perf_num(d.get('discharge_coefficient'))
    if None not in (rho, area_mm2, vel) and rho > 0 and area_mm2 > 0:
        mdot = float(cd if cd else 1.0) * rho * (area_mm2 * 1e-6) * vel
        return mdot, 'derived from Cd x rho x A_inj x v_exit'
    return None, 'not available (oxidizer mass flow not reported)'


def _injector_plate_diameter(injector_data, pattern_reach_mm):
    """Plaka çapını [mm] çözer; ölçülemiyorsa şematik olduğunu bildirir.

    Döner: (çap_mm, gerçek_mi). Eski sürüm 100 mm SABİT çiziyor ve hover'da
    'Diameter: 100 mm' yazıyordu — kamara çapından bağımsızdı.
    """
    d = injector_data or {}
    for key, scale in (('plate_diameter', 1.0), ('outer_diameter', 1.0),
                       ('manifold_diameter_mm', 1.0),
                       ('chamber_diameter_mm', 1.0),
                       ('chamber_diameter', 1000.0)):
        val = _perf_num(d.get(key))
        if val is not None and val > 0:
            return float(val) * scale, True
    # Şematik: desen sığacak kadar; ölçü olarak SUNULMAZ
    return max(2.0 * pattern_reach_mm / INJ_PLATE_PATTERN_FILL, 20.0), False


def create_showerhead_with_tooltips(injector_data):
    """Showerhead injector face view with a detailed tooltip per hole.

    Per-hole mass flow comes from the solver's own mass flow (or is derived
    from Cd*rho*A*v); when neither is available the row says so instead of
    printing a number. The plate outline is the reported plate/chamber
    diameter when known, otherwise it is drawn as a schematic and labelled.
    """

    n_holes = int(_num_safe(injector_data.get('n_holes'), 20))
    n_holes = max(1, n_holes)
    hole_diameter = _num_safe(injector_data.get('hole_diameter'), 1.5)  # mm
    plate_thickness = _num_safe(injector_data.get('plate_thickness'), 3.0)
    exit_velocity = _num_safe(injector_data.get('exit_velocity'), 30)  # m/s
    reynolds = _num_safe(injector_data.get('reynolds_number'), 50000)
    plate_material = injector_data.get('plate_material')

    mdot_total, mdot_source = _injector_total_mdot(injector_data)

    fig = go.Figure()

    # --- Delik deseni: önce halka sayısı, sonra plakaya oranlı yarıçaplar ---
    if n_holes <= 7:
        n_rings = 1 if n_holes > 1 else 0
    else:
        n_rings, placed = 0, 1          # merkez delik
        while placed < n_holes:
            n_rings += 1
            placed += 6 * n_rings
    # Desenin ulaşacağı en dış yarıçap plaka yarıçapının payına oturtulur
    pattern_reach = max(n_rings, 1) * max(hole_diameter * 2.5, 3.0)
    plate_diameter, plate_is_real = _injector_plate_diameter(
        injector_data, pattern_reach)
    r_plate = plate_diameter / 2.0
    ring_step = (r_plate * INJ_PLATE_PATTERN_FILL / max(n_rings, 1)) \
        if n_rings else 0.0

    holes_x, holes_y, hole_info = [], [], []
    if n_holes == 1:
        holes_x, holes_y, hole_info = [0.0], [0.0], ['Center hole']
    elif n_holes <= 7:
        holes_x, holes_y, hole_info = [0.0], [0.0], ['Center']
        n_outer = min(6, n_holes - 1)
        for i in range(n_outer):
            angle = i * 2 * np.pi / n_outer
            holes_x.append(ring_step * np.cos(angle))
            holes_y.append(ring_step * np.sin(angle))
            hole_info.append(f'Outer ring #{i+1}')
    else:
        holes_x, holes_y, hole_info = [0.0], [0.0], ['Center']
        placed = 1
        ring_num = 1
        while placed < n_holes:
            ring_radius = ring_num * ring_step
            holes_in_ring = min(6 * ring_num, n_holes - placed)
            for i in range(holes_in_ring):
                angle = i * 2 * np.pi / holes_in_ring
                holes_x.append(ring_radius * np.cos(angle))
                holes_y.append(ring_radius * np.sin(angle))
                hole_info.append(f'Ring {ring_num}, hole {i+1}')
                placed += 1
            ring_num += 1

    if mdot_total is not None:
        flow_row = (f'Mass flow: {mdot_total / n_holes * 1000:.2f} g/s'
                    f' ({mdot_source})')
    else:
        flow_row = 'Mass flow: not available (total flow not reported)'

    for i in range(len(holes_x)):
        x = holes_x[i]
        y = holes_y[i]

        radial_distance = np.sqrt(x**2 + y**2)
        angle_deg = np.degrees(np.arctan2(y, x)) % 360

        # DURUSTLUK DUZELTMESI (v2.5.2): eski surum her delik icin hiz ve
        # Reynolds'a RASTGELE gurultu ekliyordu (0.05 / 0.03 std). Bu, delikler
        # arasi gercek bir dagilim olcumu DEGILDI; kullanici hover'da her
        # delikte farkli sayi gorup bunu hesaplanmis bir dagilim saniyordu.
        # Model tum delikleri esit paylasimli kabul ediyor, o yuzden tasarim
        # degeri oldugu gibi gosterilir.
        local_velocity = exit_velocity
        local_reynolds = reynolds

        hover_text = (
            f'<b>{hole_info[i]}</b><br>'
            f'Position: ({x:.1f}, {y:.1f}) mm<br>'
            f'Radial distance: {radial_distance:.1f} mm<br>'
            f'Angle: {angle_deg:.0f} deg<br>'
            f'---<br>'
            f'Diameter: {hole_diameter:.2f} mm<br>'
            f'Area: {np.pi*(hole_diameter/2)**2:.3f} mm2<br>'
            f'Velocity: {local_velocity:.1f} m/s<br>'
            f'Re: {local_reynolds:.0f}<br>'
            f'{flow_row}<br>'
            f'L/D: {plate_thickness/hole_diameter:.1f}'
        )

        fig.add_trace(go.Scatter(
            x=[x],
            y=[y],
            mode='markers',
            marker=dict(
                size=max(6, min(22, hole_diameter * 10)),
                color=PALETTE[0],
                line=dict(color=STRUCT_INK, width=1.5),
                symbol='circle'
            ),
            name=f'Hole {i+1}',
            hovertemplate=hover_text + '<extra></extra>',
            showlegend=False
        ))

        if n_holes <= 20:
            fig.add_annotation(
                x=x, y=y,
                text=str(i+1),
                showarrow=False,
                font=dict(size=8, color='#0a1322'),
                bgcolor=PALETTE[0],
                borderpad=2
            )

    theta = np.linspace(0, 2*np.pi, 100)
    if plate_is_real:
        plate_rows = f'Diameter: {plate_diameter:.1f} mm'
    else:
        plate_rows = ('Diameter: not reported by the solver'
                      '<br>Outline drawn schematically, not to scale')
    if plate_material:
        plate_rows += f'<br>Material: {plate_material}'
    fig.add_trace(go.Scatter(
        x=r_plate * np.cos(theta),
        y=r_plate * np.sin(theta),
        mode='lines',
        line=dict(color=STRUCT_INK, width=3,
                  dash=(None if plate_is_real else 'dot')),
        name='Injector plate',
        hovertemplate=(
            f'<b>Injector plate</b><br>'
            f'{plate_rows}<br>'
            f'Thickness: {plate_thickness:.1f} mm<extra></extra>'
        )
    ))

    for i in range(0, len(holes_x), max(1, len(holes_x)//10)):
        x = holes_x[i]
        y = holes_y[i]

        fig.add_annotation(
            x=x, y=y,
            ax=x, ay=y - 0.15 * r_plate,
            xref='x', yref='y',
            axref='x', ayref='y',
            showarrow=True,
            arrowhead=2,
            arrowsize=1,
            arrowwidth=2,
            arrowcolor=COL_DANGER,
            opacity=0.6
        )

    total_area = n_holes * np.pi * (hole_diameter/2)**2
    summary = (f'<b>SHOWERHEAD INJECTOR</b><br>'
               f'{n_holes} Holes x dia {hole_diameter:.2f} mm<br>'
               f'Total Area: {total_area:.1f} mm2<br>'
               f'Pressure Drop: {_num_safe(injector_data.get("pressure_drop"), 5):.1f} bar')
    if mdot_total is not None:
        summary += f'<br>Total Flow: {mdot_total:.3f} kg/s'
    else:
        summary += '<br>Total Flow: not reported'
    fig.add_annotation(
        x=0, y=r_plate * 1.22,
        text=summary,
        showarrow=False,
        font=dict(size=11, color=STRUCT_INK),
        align='center',
        bgcolor=DARK_LEGEND_BG,
        bordercolor=STRUCT_INK,
        borderwidth=1
    )

    fig.update_layout(
        title='Showerhead Injector - Front View',
        xaxis=dict(
            title='X Position (mm)',
            scaleanchor='y',
            scaleratio=1,
            showgrid=True,
            gridcolor='rgba(200, 200, 200, 0.3)'
        ),
        yaxis=dict(
            title='Y Position (mm)',
            showgrid=True,
            gridcolor='rgba(200, 200, 200, 0.3)'
        ),
        plot_bgcolor=DARK_PLOT_BG,
        paper_bgcolor=DARK_PAPER_BG,
        hovermode='closest',
        autosize=True,
        height=700
    )

    return _fig_json(fig)


def create_pintle_cross_section(injector_data):
    """Pintle injector cross-section (axial: x = axis, y = radius)."""

    outer_diameter = injector_data.get('outer_diameter', 50)  # mm
    pintle_diameter = injector_data.get('pintle_diameter', 25)  # mm
    gap = injector_data.get('gap', 1.5)  # mm

    fig = go.Figure()

    # ---------------- Türetilmiş geometri (mm) ----------------
    r_p = pintle_diameter / 2.0            # pintle mili yarıçapı
    r_ann = r_p + gap                      # anülüs dış yarıçapı (gövde iç bore)
    r_out = outer_diameter / 2.0           # gövde dış yarıçapı
    # Tutarsız girdi koruması: gövde her zaman anülüsü sarmalı
    r_out = max(r_out, r_ann + max(2.0, 0.15 * r_ann))
    body_len = 1.2 * outer_diameter        # manifold gövde uzunluğu (x<0)
    tip_len = 0.8 * pintle_diameter        # pintle'ın odaya uzanan kısmı (x>0)
    taper_len = 0.6 * r_p                  # konik uç uzunluğu
    r_tip = 0.35 * r_p                     # uç yarıçapı
    ann_area = np.pi * (r_ann**2 - r_p**2)  # anüler akış alanı (mm2)

    # ---------------- Gövde duvarları (üst + alt) ----------------
    body_x = [-body_len, 0, 0, -body_len, -body_len, None,
              -body_len, 0, 0, -body_len, -body_len]
    body_y = [r_ann, r_ann, r_out, r_out, r_ann, None,
              -r_ann, -r_ann, -r_out, -r_out, -r_ann]
    body_hover = (
        f'<b>Injector Body</b><br>'
        f'D_outer: {outer_diameter:.1f} mm<br>'
        f'Wall (radial): {r_out - r_ann:.1f} mm<br>'
        f'Function: houses oxidizer manifold and annulus'
    )
    fig.add_trace(go.Scatter(
        x=body_x, y=body_y, mode='lines', fill='toself',
        fillcolor='rgba(125, 151, 165, 0.22)',
        line=dict(color=STRUCT_INK, width=2),
        name='Injector Body', hoveron='fills+points',
        text=body_hover, hoverinfo='text', showlegend=False
    ))

    # ---------------- Anüler akış geçidi (üst + alt) ----------------
    ann_x = [-body_len, 0, 0, -body_len, -body_len, None,
             -body_len, 0, 0, -body_len, -body_len]
    ann_y = [r_p, r_p, r_ann, r_ann, r_p, None,
             -r_p, -r_p, -r_ann, -r_ann, -r_p]
    ann_hover = (
        f'<b>Annular Flow Passage</b><br>'
        f'Gap: {gap:.2f} mm<br>'
        f'Flow Area: {ann_area:.1f} mm2<br>'
        f'Function: axial oxidizer sheet around the pintle'
    )
    fig.add_trace(go.Scatter(
        x=ann_x, y=ann_y, mode='lines', fill='toself',
        fillcolor='rgba(0, 229, 255, 0.16)',
        line=dict(color='rgba(0, 229, 255, 0.45)', width=1),
        name='Annular Passage', hoveron='fills+points',
        text=ann_hover, hoverinfo='text', showlegend=False
    ))

    # ---------------- Pintle mili (konik uçlu kesit) ----------------
    pintle_x = [-body_len, tip_len - taper_len, tip_len, tip_len,
                tip_len - taper_len, -body_len, -body_len]
    pintle_y = [r_p, r_p, r_tip, -r_tip, -r_p, -r_p, r_p]
    pintle_hover = (
        f'<b>Pintle Post</b><br>'
        f'D_pintle: {pintle_diameter:.1f} mm<br>'
        f'Tip protrusion: {tip_len:.1f} mm<br>'
        f'Function: central post; fuel injected radially at the tip'
    )
    fig.add_trace(go.Scatter(
        x=pintle_x, y=pintle_y, mode='lines', fill='toself',
        fillcolor='rgba(255, 140, 51, 0.28)',
        line=dict(color=PALETTE[1], width=2),
        name='Pintle Post', hoveron='fills+points',
        text=pintle_hover, hoverinfo='text', showlegend=False
    ))

    # ---------------- Eksen çizgisi ----------------
    fig.add_trace(go.Scatter(
        x=[-body_len - 8, tip_len + 14], y=[0, 0], mode='lines',
        line=dict(color=STRUCT_DIM, width=1, dash='dashdot'),
        name='Centerline', hoverinfo='skip', showlegend=False
    ))

    # ---------------- Akış okları ----------------
    # Eksenel oksitleyici okları (anülüs içinde, +x yönü)
    arrow_len = 0.12 * body_len
    for xa in (-0.85 * body_len, -0.55 * body_len, -0.25 * body_len):
        for sgn in (1, -1):
            fig.add_annotation(
                x=xa + arrow_len, y=sgn * (r_p + gap / 2.0),
                ax=xa, ay=sgn * (r_p + gap / 2.0),
                xref='x', yref='y', axref='x', ayref='y',
                showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=2,
                arrowcolor=PALETTE[0], opacity=0.85
            )
    # Radyal yakıt okları (pintle ucu yakınında, dışa doğru)
    x_rad = 0.45 * tip_len
    for sgn in (1, -1):
        fig.add_annotation(
            x=x_rad, y=sgn * (r_p + 0.55 * gap + 4.0),
            ax=x_rad, ay=sgn * (0.55 * r_p),
            xref='x', yref='y', axref='x', ayref='y',
            showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=2,
            arrowcolor=PALETTE[1], opacity=0.9
        )
    # Sonuç sprey okları (~45 derece konik levha)
    x_spr = 0.7 * tip_len
    d_spr = 0.35 * outer_diameter
    for sgn in (1, -1):
        fig.add_annotation(
            x=x_spr + d_spr, y=sgn * (r_ann + d_spr),
            ax=x_spr, ay=sgn * r_ann,
            xref='x', yref='y', axref='x', ayref='y',
            showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=2,
            arrowcolor=PALETTE[6], opacity=0.8
        )
    fig.add_annotation(
        x=x_spr + d_spr + 2, y=r_ann + d_spr + 4,
        text='Spray sheet (~45 deg)', showarrow=False,
        font=dict(size=10, color=PALETTE[6])
    )

    # ---------------- Boyut anotasyonları ----------------
    # D_outer: sol tarafta çift oklu düşey ölçü çizgisi
    x_dim = -body_len - 6
    fig.add_annotation(
        x=x_dim, y=r_out, ax=x_dim, ay=-r_out,
        xref='x', yref='y', axref='x', ayref='y',
        showarrow=True, arrowhead=2, arrowside='end+start',
        arrowsize=1, arrowwidth=1.5, arrowcolor=STRUCT_DIM
    )
    fig.add_annotation(
        x=x_dim - 3, y=0, text=f'D_outer = {outer_diameter:.1f} mm',
        showarrow=False, textangle=-90, font=dict(size=10, color=STRUCT_DIM)
    )
    # D_pintle: mile işaret eden etiket oku
    fig.add_annotation(
        x=0.15 * tip_len, y=-0.4 * r_p,
        ax=tip_len + 10, ay=-(r_out + 10),
        xref='x', yref='y', axref='x', ayref='y',
        text=f'D_pintle = {pintle_diameter:.1f} mm',
        showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1.5,
        arrowcolor=STRUCT_DIM, font=dict(size=10, color=STRUCT_INK)
    )
    # gap: anülüse işaret eden etiket oku
    fig.add_annotation(
        x=-0.3 * body_len, y=r_p + gap / 2.0,
        ax=-0.3 * body_len + 12, ay=r_out + 10,
        xref='x', yref='y', axref='x', ayref='y',
        text=f'gap = {gap:.2f} mm',
        showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1.5,
        arrowcolor=STRUCT_DIM, font=dict(size=10, color=STRUCT_INK)
    )

    # ---------------- Özet bloğu ----------------
    fig.add_annotation(
        x=(-body_len + tip_len) / 2.0, y=r_out + 18,
        text=(
            f'<b>PINTLE INJECTOR - AXIAL CROSS-SECTION</b><br>'
            f'D_outer {outer_diameter:.1f} mm | D_pintle {pintle_diameter:.1f} mm '
            f'| gap {gap:.2f} mm<br>'
            f'Annulus Flow Area: {ann_area:.1f} mm2'
        ),
        showarrow=False, font=dict(size=11), align='center'
    )

    # ---------------- Yerleşim ----------------
    x_min = -body_len - 22
    x_max = tip_len + d_spr + 26
    y_lim = r_out + 28
    fig.update_layout(
        title='Pintle Injector - Cross Section',
        xaxis=dict(
            title='Axial Position (mm)',
            scaleanchor='y', scaleratio=1,
            range=[x_min, x_max], showgrid=True
        ),
        yaxis=dict(
            title='Radial Position (mm)',
            range=[-y_lim, y_lim], showgrid=True
        ),
        hovermode='closest',
        autosize=True,
        height=700
    )

    return _fig_json(fig)


def create_swirl_injector(injector_data):
    """Swirl injector face view (tangential slots + swirl chamber)."""

    n_slots = injector_data.get('n_slots', 6)

    fig = go.Figure()

    # ---------------- Parametreler ve türetilmiş geometri (mm) ----------------
    # DURUSTLUK DUZELTMESI (2026-07-19): çıkış orifisi çapı artık çözücünün
    # GERÇEK akış alanından türetilir (exit_orifice_area). Eski sürüm
    # outer_diameter=50 mm sabitinden zincirleme 0.6/0.35 oranlarıyla
    # d_exit=10.5 mm üretip bunu ölçü oku ile teknik resim gibi sunuyordu;
    # 6 kat debi değişiminde bile üç ölçü aynı kalıyordu.
    n_slots = max(1, int(n_slots))
    a_exit = _perf_num(injector_data.get('exit_orifice_area'))     # mm2
    d_exit_direct = _perf_num(injector_data.get('exit_orifice_diameter'))
    if d_exit_direct is not None and d_exit_direct > 0:
        r_ex, exit_is_real = d_exit_direct / 2.0, True
    elif a_exit is not None and a_exit > 0:
        r_ex, exit_is_real = float(np.sqrt(a_exit / np.pi)), True
    else:
        r_ex, exit_is_real = 5.0, False        # yalnız çizim ölçeği

    d_outer = _perf_num(injector_data.get('outer_diameter'))
    d_chamber = _perf_num(injector_data.get('swirl_chamber_diameter'))
    # Girdap odası / gövde çapı çözücü çıktısında YOK. Çizim ölçeği gerçek
    # çıkış orifisine oturtulur; ölçü çağrıları 'not reported' der.
    chamber_is_real = d_chamber is not None and d_chamber > 0
    r_ch = (d_chamber / 2.0) if chamber_is_real else (r_ex / 0.35)
    outer_is_real = d_outer is not None and d_outer > 0
    r_out = (d_outer / 2.0) if outer_is_real else (r_ch / 0.6)
    outer_diameter = 2.0 * r_out
    slot_width = _num_safe(injector_data.get('slot_width'),
                           max(1.5, 0.15 * r_ch))                 # mm
    slot_height = _num_safe(injector_data.get('slot_height'),
                            0.5 * r_ch)                           # mm
    # Yuva gövde dışına taşmasın (kaba koruma)
    max_reach = np.sqrt((r_ch + slot_width)**2 + slot_height**2)
    if max_reach > 0.96 * r_out:
        slot_height = max(0.5, np.sqrt(max(
            (0.96 * r_out)**2 - (r_ch + slot_width)**2, 0.25)))

    theta = np.linspace(0, 2 * np.pi, 120)

    # ---------------- Gövde yüzü (dış halka) ----------------
    fig.add_trace(go.Scatter(
        x=r_out * np.cos(theta), y=r_out * np.sin(theta),
        mode='lines', line=dict(color=STRUCT_INK, width=3),
        name='Injector Body',
        hovertemplate=(
            f'<b>Injector Body</b><br>'
            + (f'D_outer: {outer_diameter:.1f} mm<br>' if outer_is_real
               else 'D_outer: not reported by the solver (schematic)<br>')
            + f'Function: houses swirl chamber and feed slots<extra></extra>'
        ),
        showlegend=False
    ))

    # ---------------- Girdap odası ----------------
    fig.add_trace(go.Scatter(
        x=r_ch * np.cos(theta), y=r_ch * np.sin(theta),
        mode='lines', fill='toself',
        fillcolor='rgba(0, 229, 255, 0.07)',
        line=dict(color='rgba(0, 229, 255, 0.55)', width=2),
        name='Swirl Chamber', hoveron='fills+points',
        text=(
            f'<b>Swirl Chamber</b><br>'
            + (f'D_chamber: {2 * r_ch:.1f} mm<br>' if chamber_is_real
               else 'D_chamber: not reported by the solver (schematic)<br>')
            + f'Function: tangential inflow builds the vortex'
        ),
        hoverinfo='text', showlegend=False
    ))

    # ---------------- Çıkış orifisi ----------------
    fig.add_trace(go.Scatter(
        x=r_ex * np.cos(theta), y=r_ex * np.sin(theta),
        mode='lines', fill='toself',
        fillcolor='rgba(0, 229, 255, 0.25)',
        line=dict(color=PALETTE[0], width=2),
        name='Exit Orifice', hoveron='fills+points',
        text=(
            f'<b>Exit Orifice</b><br>'
            + (f'd_exit: {2 * r_ex:.2f} mm (from solver exit orifice area)<br>'
               if exit_is_real
               else 'd_exit: not reported by the solver (schematic)<br>')
            + f'Function: swirling film exits as a hollow cone spray'
        ),
        hoverinfo='text', showlegend=False
    ))

    # ---------------- Teğetsel giriş yuvaları ----------------
    arrow_step = 1 if n_slots <= 12 else max(1, n_slots // 8)
    for i in range(n_slots):
        ang = 2 * np.pi * i / n_slots
        c, s = np.cos(ang), np.sin(ang)
        px, py = r_ch * c, r_ch * s            # oda duvarındaki giriş noktası
        tx, ty = -s, c                         # teğet yön (saat yönü tersi)
        nx, ny = c, s                          # radyal dış yön
        # Dikdörtgen köşeleri: duvardan teğet geriye uzanan kanal
        xs = [px, px - slot_height * tx, px - slot_height * tx + slot_width * nx,
              px + slot_width * nx, px]
        ys = [py, py - slot_height * ty, py - slot_height * ty + slot_width * ny,
              py + slot_width * ny, py]
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode='lines', fill='toself',
            fillcolor='rgba(255, 140, 51, 0.30)',
            line=dict(color=PALETTE[1], width=1.5),
            name=f'Slot {i + 1}', hoveron='fills+points',
            text=(
                f'<b>Tangential Slot #{i + 1}</b><br>'
                f'Size: {slot_width:.2f} x {slot_height:.2f} mm<br>'
                f'Position: {np.degrees(ang):.0f} deg<br>'
                f'Function: injects propellant tangentially (angular momentum)'
            ),
            hoverinfo='text', showlegend=False
        ))
        # Giriş akış oku (teğet yönde odaya doğru)
        if i % arrow_step == 0:
            mx, my = px + 0.5 * slot_width * nx, py + 0.5 * slot_width * ny
            fig.add_annotation(
                x=mx - 0.1 * slot_height * tx, y=my - 0.1 * slot_height * ty,
                ax=mx - 0.85 * slot_height * tx, ay=my - 0.85 * slot_height * ty,
                xref='x', yref='y', axref='x', ayref='y',
                showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=2,
                arrowcolor=PALETTE[1], opacity=0.9
            )

    # ---------------- Dönüş yönü okları (dairesel yay + uç oku) ----------------
    r_arc = (r_ex + r_ch) / 2.0
    arc_span = np.radians(70)
    for a0 in np.radians([15, 135, 255]):
        arc = np.linspace(a0, a0 + arc_span, 30)
        fig.add_trace(go.Scatter(
            x=r_arc * np.cos(arc), y=r_arc * np.sin(arc),
            mode='lines', line=dict(color=PALETTE[0], width=2),
            name='Swirl Direction',
            hovertemplate='<b>Swirl Direction</b><br>'
                          'Counter-clockwise vortex<extra></extra>',
            showlegend=False
        ))
        a1 = a0 + arc_span
        fig.add_annotation(
            x=r_arc * np.cos(a1 + 0.12), y=r_arc * np.sin(a1 + 0.12),
            ax=r_arc * np.cos(a1), ay=r_arc * np.sin(a1),
            xref='x', yref='y', axref='x', ayref='y',
            showarrow=True, arrowhead=2, arrowsize=1.2, arrowwidth=2,
            arrowcolor=PALETTE[0]
        )

    # ---------------- Boyut anotasyonları ----------------
    # d_exit: orifis üzerinden çift oklu yatay ölçü
    fig.add_annotation(
        x=r_ex, y=0, ax=-r_ex, ay=0,
        xref='x', yref='y', axref='x', ayref='y',
        showarrow=True, arrowhead=2, arrowside='end+start',
        arrowsize=1, arrowwidth=1.5, arrowcolor=STRUCT_DIM
    )
    fig.add_annotation(
        x=0, y=-r_ex - 2.5,
        text=(f'd_exit = {2 * r_ex:.2f} mm' if exit_is_real
              else 'd_exit: not reported'),
        showarrow=False, font=dict(size=10, color=STRUCT_DIM)
    )
    # D_chamber: oda duvarına etiket oku
    ang_dim = np.radians(200)
    fig.add_annotation(
        x=r_ch * np.cos(ang_dim), y=r_ch * np.sin(ang_dim),
        ax=(r_out + 12) * np.cos(ang_dim), ay=(r_out + 12) * np.sin(ang_dim),
        xref='x', yref='y', axref='x', ayref='y',
        text=(f'D_chamber = {2 * r_ch:.1f} mm' if chamber_is_real
              else 'D_chamber: not reported'),
        showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1.5,
        arrowcolor=STRUCT_DIM, font=dict(size=10, color=STRUCT_INK)
    )
    # D_outer: gövde dış duvarına etiket oku
    ang_dim2 = np.radians(340)
    fig.add_annotation(
        x=r_out * np.cos(ang_dim2), y=r_out * np.sin(ang_dim2),
        ax=(r_out + 14) * np.cos(ang_dim2), ay=(r_out + 14) * np.sin(ang_dim2),
        xref='x', yref='y', axref='x', ayref='y',
        text=(f'D_outer = {outer_diameter:.1f} mm' if outer_is_real
              else 'D_outer: not reported'),
        showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1.5,
        arrowcolor=STRUCT_DIM, font=dict(size=10, color=STRUCT_INK)
    )

    # ---------------- Özet bloğu ----------------
    fig.add_annotation(
        x=0, y=r_out + 14,
        text=(
            f'<b>SWIRL INJECTOR - FACE VIEW</b><br>'
            f'{n_slots} Tangential Slots x {slot_width:.2f} x {slot_height:.2f} mm<br>'
            + (f'd_exit {2 * r_ex:.2f} mm' if exit_is_real
               else 'd_exit not reported')
            + (f' | D_chamber {2 * r_ch:.1f} mm' if chamber_is_real else '')
        ),
        showarrow=False, font=dict(size=11, color=STRUCT_INK), align='center'
    )
    if not (exit_is_real and chamber_is_real and outer_is_real):
        fig.add_annotation(
            x=0, y=-(r_out + 20), showarrow=False, align='center',
            text=('Body and swirl-chamber outlines are schematic: the solver '
                  'reports slot sizes and the exit orifice area, not the '
                  'housing diameters. Do not machine from this view.'),
            font=dict(size=10, color=STRUCT_DIM)
        )

    # ---------------- Yerleşim ----------------
    lim = r_out + 24
    fig.update_layout(
        title='Swirl Injector - Face View',
        xaxis=dict(
            title='X Position (mm)',
            scaleanchor='y', scaleratio=1,
            range=[-lim, lim], showgrid=True
        ),
        yaxis=dict(
            title='Y Position (mm)',
            range=[-lim, lim + 6], showgrid=True
        ),
        hovermode='closest',
        autosize=True,
        height=700
    )

    return _fig_json(fig)