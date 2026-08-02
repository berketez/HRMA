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
from datetime import datetime

import numpy as np

from hrma.engines.nozzle_design import sample_nozzle_inner_contour
from hrma.export.export_workspace import (
    atomic_produce, new_workspace, purge_stale_workspaces)
from hrma.utils.input_guard import safe_name

#: DXF birim başlığı: 4 = millimetre (DXF referansı, $INSUNITS tablosu).
#: ezdxf.new(..., setup=True) varsayılanı 6'dır (METRE) ve depoda hiçbir yerde
#: ezilmiyordu; üretilen geometri ise mm (ölçüldü: X aralığı 0 -> 1077.04).
#: Yani CAD yazılımı çizimi 1000× büyük ölçekliyordu — A1'deki STL hatasının
#: aynı sınıfı. Faz 4B / A2.
DXF_INSUNITS_MILLIMETERS = 4


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


def _render_or_raise(fig, width, height):
    """Teknik çizim figürünü PNG'ye çevirir; render edilemezse yükseltir.

    chart_render katmanı kaleido asılmasını zaman aşımıyla keser (Windows
    2026-07-20 saha hatası). Teknik çizimler shape-temellidir → matplotlib
    emniyet çizicisi anlamlı görüntü üretemez (allow_fallback=False); None
    dönerse RuntimeError yükseltilir ve çağıran sayfa mevcut except yoluyla
    'render failed' notunu basar — istek asla asılı kalmaz.
    """
    from hrma.export.chart_render import figure_png
    png = figure_png(fig, width=width, height=height, scale=2,
                     allow_fallback=False)
    if not png:
        raise RuntimeError('chart renderer (kaleido) unavailable or timed out')
    return png


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
    return _render_or_raise(fig, width=width, height=height)


def _injector_face_png(motor_results, size=700):
    """Enjektör yüz deseni: orifis yerleşimi ölçekli daire deseni (PNG bayt).

    Delik sayısı/çapı TEK doğruluk kaynağından okunur: cad_visualization
    ._injector_spec (motor sonucundaki injector_design). Aynı motor koşusunda
    ekrandaki enjektör grafiği, bu imalat çizimi ve CAD sözlüğü farklı sayılar
    gösteriyordu (2026-07-19 denetimi, kritik bulgu: 50 delik x 0.94 mm ekranda,
    5 delik x 2.26 mm çizimde). Değer yoksa desen çizilmez; sayfa "not
    available" notuyla basılır — uydurma delik sayısı çizilmez.
    """
    import plotly.graph_objects as go
    import plotly.io as pio

    from hrma.export.cad_visualization import _injector_spec

    md = motor_results or {}
    spec = _injector_spec(md)
    D_ch = _num(md.get('chamber_diameter'), 0.1) * 1000
    n = spec['n_orifices']
    d_h = spec['orifice_diameter_mm']
    if not n or not d_h:
        raise ValueError('injector orifice count/diameter not available in the '
                         'motor result (injector_design missing)')
    n = int(n)
    inj_type = str(spec['type'] or 'injector')

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
        title=(f'INJECTOR FACE - {n} x d{d_h:.2f} mm ({inj_type}); '
               f'ring layout shown schematically'),
        paper_bgcolor='white', plot_bgcolor='white',
        font=dict(color='#1a2733'),
        xaxis=dict(title='mm', scaleanchor='y', scaleratio=1,
                   range=[-R * 1.15, R * 1.15]),
        yaxis=dict(title='mm', range=[-R * 1.15, R * 1.15]),
        showlegend=False, width=size, height=size,
    )
    return _render_or_raise(fig, width=size, height=size)


def generate_drawing_pdf(motor_results, out_path=None):
    """Antetli, çok sayfalı teknik çizim PDF'i üretir; dosya yolu döner."""
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm as MM
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as rl_canvas

    d = _dims_mm(motor_results)
    # Ad dosya yoluna giriyor: mutlak yol / '..' geçmesin (K-1).
    name = safe_name((motor_results or {}).get('motor_name'))
    stamp = datetime.now().strftime('%Y-%m-%d')

    # D1: dosya adı GÜN çözünürlüklüydü ve paylaşılan /tmp köküne yazıyordu —
    # aynı motor adıyla gelen iki eşzamanlı istek aynı dosyayı eziyordu.
    # Artık her iş kendi mkdtemp dizinini alır; ad çakışması imkânsız.
    if out_path is None:
        purge_stale_workspaces()
        out_path = os.path.join(new_workspace('hrma_drawings_'),
                                f'{name}_drawings_{stamp}.pdf')
    out_path = os.path.abspath(out_path)

    page_w, page_h = landscape(A4)
    # Yazma ATOMİK: reportlab doğrudan hedefe yazarsa yarım PDF okunabilir.
    work_path = out_path + '.part'
    c = rl_canvas.Canvas(work_path, pagesize=landscape(A4))

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
                     'HRMA — solver-generated geometry')
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
    # Cidar kalınlığı, malzeme ve enjektör satırları ÇÖZÜCÜ sonucundan gelir
    # (eski tablo sabit malzeme adları yazıyordu ve enjektör hiç yoktu).
    from hrma.export.cad_visualization import (
        NOT_AVAILABLE_SPEC, _chamber_material, _chamber_wall_thickness_m,
        _injector_spec, _nozzle_half_angles)

    wall_m, wall_src = _chamber_wall_thickness_m(motor_results)
    _mat_key, mat_name, _rho = _chamber_material(motor_results)
    spec = _injector_spec(motor_results)
    conv_deg, div_deg, noz_type = _nozzle_half_angles(motor_results)

    rows = [
        ('Chamber inner diameter', f"{d['D_ch']:.1f} mm"),
        ('Chamber length', f"{d['L']:.1f} mm"),
        ('Chamber wall thickness',
         f"{wall_m * 1000:.2f} mm  [{wall_src}]" if wall_m else NOT_AVAILABLE_SPEC),
        ('Grain length', f"{d['L_g']:.1f} mm"),
        ('Port diameter (initial)', f"{d['d_p0']:.1f} mm"),
        ('Port diameter (final)', f"{d['d_pf']:.1f} mm"),
        ('Throat diameter', f"{d['d_t']:.2f} mm"),
        ('Exit diameter', f"{d['d_e']:.2f} mm"),
        ('Expansion ratio', f"{d['eps']:.2f}"),
        ('Nozzle type / half angles',
         f"{noz_type}; conv "
         f"{('%.1f deg' % conv_deg) if conv_deg else 'n/a'}, div "
         f"{('%.1f deg' % div_deg) if div_deg else 'n/a'}"),
        ('Injector orifices',
         (f"{spec['n_orifices']} x d{spec['orifice_diameter_mm']:.2f} mm "
          f"({spec['type'] or 'type n/a'})")
         if (spec['n_orifices'] and spec['orifice_diameter_mm'])
         else NOT_AVAILABLE_SPEC),
        ('Injector pressure drop',
         f"{spec['pressure_drop_bar']:.2f} bar" if spec['pressure_drop_bar']
         else NOT_AVAILABLE_SPEC),
        ('Chamber material', mat_name or NOT_AVAILABLE_SPEC),
        ('Nozzle material',
         (motor_results or {}).get('nozzle_material')
         or (motor_results or {}).get('throat_material') or NOT_AVAILABLE_SPEC),
        ('Injector material',
         (motor_results or {}).get('injector_material') or NOT_AVAILABLE_SPEC),
        ('Pressure test requirement', '1.5 x MEOP hydrostatic before firing'),
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
    os.replace(work_path, out_path)
    return out_path


# ---------------------------------------------------------------------------
# DXF imalat çizimi
# ---------------------------------------------------------------------------

def generate_dxf(motor_results, out_path=None):
    """2D imalat çizimi (DXF R2010): iç akış yolu + kamara + grain profili.

    Birim: MİLİMETRE — dosyaya ``$INSUNITS = 4`` olarak da yazılır (A2).
    Eşzamanlılık: ``out_path`` verilmezse her çağrı kendi geçici dizinini alır
    ve dosya atomik yazılır (D1).
    """
    import ezdxf

    d = _dims_mm(motor_results)
    # Ad dosya yoluna giriyor: mutlak yol / '..' geçmesin (K-1).
    name = safe_name((motor_results or {}).get('motor_name'))
    if out_path is None:
        purge_stale_workspaces()
        out_path = os.path.join(
            new_workspace('hrma_dxf_'),
            f"{name}_profile_{datetime.now().strftime('%Y%m%d')}.dxf")
    out_path = os.path.abspath(out_path)

    doc = ezdxf.new('R2010', setup=True)
    # Geometri mm; başlık da mm demeli. ezdxf varsayılanı 6 (metre) —
    # ayarlanmadığında CAD çizimi 1000× büyük ölçeklendiriyordu.
    doc.header['$INSUNITS'] = DXF_INSUNITS_MILLIMETERS
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

    # Kamara dış duvarı — kalınlık YALNIZ yapısal analizden gelir.
    # A8: burası da ``chamber_analysis`` anahtarını arıyor, katı/sıvı motorda
    # bulamayınca 0.045·D uydurmasına düşüyordu. Artık üç şemayı tanıyan tek
    # çözümleyici kullanılır; değer yoksa dış duvar ÇİZİLMEZ ve çizim bunu
    # yazıyla söyler (imalatçı uydurma bir et kalınlığı ölçmesin).
    from hrma.export.cad_visualization import _chamber_wall_thickness_m
    wall_m, wall_src = _chamber_wall_thickness_m(motor_results)
    wall = (wall_m * 1000.0) if wall_m is not None else None
    if wall is not None:
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
    y_wall = rc + (wall if wall is not None else 0.0)
    labels = [
        (L / 2, y_wall + 12, f"L_chamber = {L:.1f} mm"),
        (L + meta['z_throat'], d['d_t'] / 2 + 14, f"Ø_throat = {d['d_t']:.2f} mm"),
        (z_end, d['d_e'] / 2 + 14, f"Ø_exit = {d['d_e']:.2f} mm"),
        (-10, rc + 8, f"Ø_chamber = {d['D_ch']:.1f} mm"),
        ((zg0 + zg1) / 2, -(y_wall + 16), f"grain {d['L_g']:.1f} mm, port Ø{d['d_p0']:.1f}→{d['d_pf']:.1f} mm"),
        (0.0, -(y_wall + 30),
         (f"WALL THICKNESS = {wall:.2f} mm [{wall_src}]" if wall is not None
          else 'WALL THICKNESS: NOT AVAILABLE FROM THE ANALYSIS - '
               'outer profile not drawn')),
        (0.0, -(y_wall + 40),
         f"NOZZLE DIVERGENT LENGTH: {meta['divergent_length_source']}"),
        (0.0, -(y_wall + 50), 'ALL DIMENSIONS IN MILLIMETRES ($INSUNITS=4)'),
    ]
    for x, y, text in labels:
        msp.add_text(text, dxfattribs={'layer': 'TEXT', 'height': 5.0}
                     ).set_placement((x, y))

    # Yazma ATOMİK (D1): yarım DXF HTTP 200 ile indirilmesin.
    atomic_produce(out_path, doc.saveas)
    return out_path
