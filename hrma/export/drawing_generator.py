"""Gerçek teknik çizim üretimi: ölçülü PDF paketi + DXF imalat çizimi.

Eski durum (Opus/keşif denetimi): "technical drawings" yalnız JSON sözlüğüydü,
popup butonları alert'ten ibaretti. Bu modül:

1. `generate_drawing_pdf`  — kaleido ile mevcut Plotly mühendislik kesitini
   (create_improved_motor_cross_section — çözücüyle AYNI geometri kaynağı)
   rasterleştirip reportlab ile antetli, boyut tablolu çok sayfalı çizim
   PDF'ine dönüştürür (kesit + enjektör yüz deseni + boyut/malzeme tabloları).
2. `generate_dxf` — ezdxf ile 2D imalat çizimi: iç akış yolu konturu
   (sample_nozzle_inner_contour, TEK kontur kaynağı), kamara dış duvarı,
   grain profili; katman ayrımı (CONTOUR / OUTLINE / CENTERLINE / TEXT).
   DXF her CAD yazılımında açılır (DWG kapalı format olduğundan DXF verilir).

Her iki üretici de dosya YOLU döndürür; Flask endpoint'i dosyayı stream eder.
"""

import io
import os
import json
import tempfile
from datetime import datetime

import numpy as np

from hrma.engines.nozzle_design import sample_nozzle_inner_contour


def _num(v, fb):
    try:
        f = float(v)
        return f if np.isfinite(f) else fb
    except (TypeError, ValueError):
        return fb


def _dims_mm(motor_results):
    """Çizimlerde kullanılan ana boyutları (mm) tek yerden çıkarır."""
    md = motor_results or {}
    gd = md.get('grain_design') or {}
    return {
        'L': _num(md.get('chamber_length'), 0.3) * 1000,
        'D_ch': _num(md.get('chamber_diameter'), 0.1) * 1000,
        'd_t': _num(md.get('throat_diameter'), 0.02) * 1000,
        'd_e': _num(md.get('exit_diameter'), 0.08) * 1000,
        'L_g': _num(gd.get('grain_length_mm'),
                    _num(md.get('grain_length'), 0.24) * 1000),
        'd_p0': _num(gd.get('port_diameter_initial_mm'),
                     _num(md.get('port_diameter_initial'), 0.03) * 1000),
        'd_pf': _num(gd.get('port_diameter_final_mm'),
                     _num(md.get('port_diameter_final'), 0.05) * 1000),
        'eps': _num(md.get('expansion_ratio'), 4.0),
    }


# ---------------------------------------------------------------------------
# PDF çizim paketi
# ---------------------------------------------------------------------------

def _cross_section_png(motor_results, width=1500, height=520):
    """Mühendislik kesitini kaleido ile PNG'ye rasterleştirir (bayt döner)."""
    import plotly.io as pio
    from hrma.visualization.visualization import create_improved_motor_cross_section

    fig_json = create_improved_motor_cross_section(motor_results)
    fig = pio.from_json(fig_json)
    # Baskı için beyaz-üstü-koyu yerine açık tema tercih edilir (çizim kağıdı)
    fig.update_layout(paper_bgcolor='white', plot_bgcolor='white',
                      font=dict(color='#1a2733'),
                      title_font=dict(color='#1a2733'))
    fig.update_xaxes(gridcolor='rgba(30,60,90,0.15)',
                     tickfont=dict(color='#1a2733'),
                     title_font=dict(color='#1a2733'))
    fig.update_yaxes(gridcolor='rgba(30,60,90,0.15)',
                     tickfont=dict(color='#1a2733'),
                     title_font=dict(color='#1a2733'))
    return pio.to_image(fig, format='png', width=width, height=height, scale=2)


def _injector_face_png(motor_results, size=700):
    """Enjektör yüz deseni: orifis yerleşimi ölçekli daire deseni (PNG bayt)."""
    import plotly.graph_objects as go
    import plotly.io as pio

    md = motor_results or {}
    inj = md.get('injector_design') or md.get('injector') or {}
    D_ch = _num(md.get('chamber_diameter'), 0.1) * 1000
    n = int(_num(inj.get('number_of_orifices') or inj.get('n_holes'), 12))
    d_h = _num(inj.get('orifice_diameter_mm') or inj.get('hole_diameter'), 1.5)

    fig = go.Figure()
    R = D_ch / 2
    theta = np.linspace(0, 2 * np.pi, 100)
    fig.add_trace(go.Scatter(x=R * np.cos(theta), y=R * np.sin(theta),
                             mode='lines', line=dict(color='#1a2733', width=2),
                             name=f'Plate Ø{D_ch:.1f} mm'))
    # Orifisler eş merkezli halkalara dağıtılır (0.35R ve 0.7R)
    placed = 0
    for ring_r, frac in ((0.7 * R, 0.67), (0.38 * R, 0.33)):
        k = max(1, round(n * frac)) if placed + round(n * frac) <= n else n - placed
        for i in range(k):
            a = 2 * np.pi * i / max(k, 1)
            cx, cy = ring_r * np.cos(a), ring_r * np.sin(a)
            fig.add_shape(type='circle',
                          x0=cx - d_h / 2, x1=cx + d_h / 2,
                          y0=cy - d_h / 2, y1=cy + d_h / 2,
                          line=dict(color='#c0392b', width=1.5))
        placed += k
    fig.update_layout(
        title=f'INJECTOR FACE — {n} × Ø{d_h:.2f} mm (showerhead)',
        paper_bgcolor='white', plot_bgcolor='white',
        font=dict(color='#1a2733'),
        xaxis=dict(title='mm', scaleanchor='y', scaleratio=1,
                   range=[-R * 1.15, R * 1.15]),
        yaxis=dict(title='mm', range=[-R * 1.15, R * 1.15]),
        showlegend=False, width=size, height=size,
    )
    return pio.to_image(fig, format='png', width=size, height=size, scale=2)


def generate_drawing_pdf(motor_results, out_path=None):
    """Antetli, çok sayfalı teknik çizim PDF'i üretir; dosya yolu döner."""
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm as MM
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as rl_canvas

    d = _dims_mm(motor_results)
    name = (motor_results or {}).get('motor_name') or 'HRMA_MOTOR'
    stamp = datetime.now().strftime('%Y-%m-%d')

    if out_path is None:
        out_path = os.path.join(tempfile.gettempdir(),
                                f'{name}_drawings_{stamp}.pdf')

    page_w, page_h = landscape(A4)
    c = rl_canvas.Canvas(out_path, pagesize=landscape(A4))

    def title_block(page_title, sheet, total):
        """Standart antet: alt şerit — proje / sayfa / tarih / ölçek notu."""
        c.setLineWidth(1.2)
        c.rect(10 * MM, 10 * MM, page_w - 20 * MM, page_h - 20 * MM)
        c.setLineWidth(0.8)
        c.line(10 * MM, 24 * MM, page_w - 10 * MM, 24 * MM)
        c.setFont('Helvetica-Bold', 11)
        c.drawString(14 * MM, 18 * MM, f'HRMA — {name}')
        c.setFont('Helvetica', 9)
        c.drawString(14 * MM, 13 * MM,
                     'High-Fidelity Rocket Motor Analysis — solver-generated geometry')
        c.setFont('Helvetica-Bold', 10)
        c.drawRightString(page_w - 14 * MM, 18 * MM, page_title)
        c.setFont('Helvetica', 9)
        c.drawRightString(page_w - 14 * MM, 13 * MM,
                          f'{stamp}  ·  SHEET {sheet}/{total}  ·  DIMS IN mm  ·  NOT TO SCALE')

    total_sheets = 3

    # ---- Sayfa 1: Eksenel kesit ----
    title_block('MOTOR AXIAL CROSS-SECTION', 1, total_sheets)
    try:
        png = _cross_section_png(motor_results)
        img = ImageReader(io.BytesIO(png))
        c.drawImage(img, 15 * MM, 40 * MM, width=page_w - 30 * MM,
                    height=page_h - 70 * MM, preserveAspectRatio=True,
                    anchor='c')
    except Exception as exc:  # kaleido/figür hatası — sayfayı boş bırakma
        c.setFont('Helvetica', 12)
        c.drawString(20 * MM, page_h / 2, f'Cross-section render failed: {exc}')
    c.showPage()

    # ---- Sayfa 2: Enjektör yüzü ----
    title_block('INJECTOR FACE PATTERN', 2, total_sheets)
    try:
        png = _injector_face_png(motor_results)
        img = ImageReader(io.BytesIO(png))
        side = min(page_w - 60 * MM, page_h - 70 * MM)
        c.drawImage(img, (page_w - side) / 2, 38 * MM, width=side,
                    height=side, preserveAspectRatio=True, anchor='c')
    except Exception as exc:
        c.setFont('Helvetica', 12)
        c.drawString(20 * MM, page_h / 2, f'Injector render failed: {exc}')
    c.showPage()

    # ---- Sayfa 3: Boyut ve malzeme tablosu ----
    title_block('DIMENSION & MATERIAL SCHEDULE', 3, total_sheets)
    rows = [
        ('Chamber inner diameter', f"{d['D_ch']:.1f} mm"),
        ('Chamber length', f"{d['L']:.1f} mm"),
        ('Grain length', f"{d['L_g']:.1f} mm"),
        ('Port diameter (initial)', f"{d['d_p0']:.1f} mm"),
        ('Port diameter (final)', f"{d['d_pf']:.1f} mm"),
        ('Throat diameter', f"{d['d_t']:.2f} mm"),
        ('Exit diameter', f"{d['d_e']:.2f} mm"),
        ('Expansion ratio', f"{d['eps']:.2f}"),
        ('Chamber material', 'AISI 316L / 4130 (see structural analysis)'),
        ('Nozzle material', 'Graphite / ablative composite'),
        ('Injector material', 'Aluminum 6061-T6'),
        ('Pressure test requirement', '1.5 × MEOP hydrostatic before firing'),
    ]
    y = page_h - 45 * MM
    c.setFont('Helvetica-Bold', 11)
    c.drawString(30 * MM, y, 'PARAMETER')
    c.drawString(140 * MM, y, 'VALUE / SPEC')
    y -= 4 * MM
    c.line(30 * MM, y, page_w - 30 * MM, y)
    c.setFont('Helvetica', 10)
    for label, val in rows:
        y -= 8 * MM
        c.drawString(30 * MM, y, label)
        c.drawString(140 * MM, y, val)
    c.showPage()

    c.save()
    return out_path


# ---------------------------------------------------------------------------
# DXF imalat çizimi
# ---------------------------------------------------------------------------

def generate_dxf(motor_results, out_path=None):
    """2D imalat çizimi (DXF R2010): iç akış yolu + kamara + grain profili."""
    import ezdxf

    d = _dims_mm(motor_results)
    name = (motor_results or {}).get('motor_name') or 'HRMA_MOTOR'
    if out_path is None:
        out_path = os.path.join(
            tempfile.gettempdir(),
            f"{name}_profile_{datetime.now().strftime('%Y%m%d')}.dxf")

    doc = ezdxf.new('R2010', setup=True)
    doc.layers.add('CONTOUR', color=1)      # kırmızı — iç akış yolu
    doc.layers.add('OUTLINE', color=5)      # mavi — dış duvarlar
    doc.layers.add('CENTERLINE', color=3)   # yeşil — eksen
    doc.layers.add('TEXT', color=7)
    msp = doc.modelspace()

    L, rc = d['L'], d['D_ch'] / 2
    # İç akış yolu: enjektör yüzünden nozul çıkışına (tek kontur kaynağı)
    pts, meta = sample_nozzle_inner_contour(motor_results)
    noz = [(L + z, r) for z, r in pts]

    upper = [(0.0, rc)] + noz
    lower = [(z, -r) for z, r in upper]
    msp.add_lwpolyline(upper, dxfattribs={'layer': 'CONTOUR'})
    msp.add_lwpolyline(lower, dxfattribs={'layer': 'CONTOUR'})

    # Kamara dış duvarı (temsili et kalınlığı: yapısal analizden ya da %4.5)
    struct = (motor_results or {}).get('structural_analysis') or {}
    wall = _num((struct.get('chamber_analysis') or {}).get('recommended_thickness'),
                0.045 * d['D_ch'])
    for s in (1, -1):
        msp.add_lwpolyline(
            [(0, s * (rc + wall)), (L, s * (rc + wall))],
            dxfattribs={'layer': 'OUTLINE'})
    msp.add_lwpolyline([(0, -(rc + wall)), (0, rc + wall)],
                       dxfattribs={'layer': 'OUTLINE'})

    # Grain profili (başlangıç portu, kesikli görünüm yerine ayrı katman)
    zg0 = 0.35 * max(4.0, L - d['L_g'])
    zg1 = zg0 + d['L_g']
    for s in (1, -1):
        msp.add_lwpolyline(
            [(zg0, s * d['d_p0'] / 2), (zg1, s * d['d_p0'] / 2)],
            dxfattribs={'layer': 'OUTLINE'})

    # Eksen çizgisi
    z_end = noz[-1][0] if noz else L
    msp.add_line((-15, 0), (z_end + 15, 0),
                 dxfattribs={'layer': 'CENTERLINE', 'linetype': 'CENTER'})

    # Ölçü metinleri (basit, imalatçıya yeterli açıklıkta)
    labels = [
        (L / 2, rc + wall + 12, f"L_chamber = {L:.1f} mm"),
        (L + meta['z_throat'], d['d_t'] / 2 + 14, f"Ø_throat = {d['d_t']:.2f} mm"),
        (z_end, d['d_e'] / 2 + 14, f"Ø_exit = {d['d_e']:.2f} mm"),
        (-10, rc + 8, f"Ø_chamber = {d['D_ch']:.1f} mm"),
        ((zg0 + zg1) / 2, -(rc + wall + 16), f"grain {d['L_g']:.1f} mm, port Ø{d['d_p0']:.1f}→{d['d_pf']:.1f} mm"),
    ]
    for x, y, text in labels:
        msp.add_text(text, dxfattribs={'layer': 'TEXT', 'height': 5.0}
                     ).set_placement((x, y))

    doc.saveas(out_path)
    return out_path
