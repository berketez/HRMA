"""Gerçek STEP (AP214) katı model üretimi — build123d/OCC tabanlı.

Eski durum: "STEP" butonu ya alert'ti ya da FreeCAD'e bağlıydı (kurulu değil,
hiç çalışmadı). Bu modül build123d (OpenCascade çekirdeği) ile ÇÖZÜCÜNÜN
kendi geometrisinden parametrik katılar üretir:

  - chamber   : silindirik duvar + baş kapak (revolve edilmiş kapalı profil)
  - nozzle    : gerçek iç kontur (sample_nozzle_inner_contour — 2D/3D/STL ile
                AYNI tek kaynak) + duvar ofseti, eksen etrafında revolve
  - fuel_grain: portlu halka silindir
  - injector  : orifis delikli plaka (gerçek boolean delikler)

Her bileşen ayrı .step + tümü tek assembly .step olarak yazılır.
build123d import edilemezse RuntimeError yükselir; endpoint bunu 501 olarak
kullanıcıya AÇIKÇA raporlar (sessiz düşüş yok).
"""

import os
import tempfile
from datetime import datetime

import numpy as np

from hrma.engines.nozzle_design import sample_nozzle_inner_contour

try:
    from build123d import (
        BuildPart, BuildSketch, BuildLine, Plane, Polyline, Line,
        make_face, revolve, Axis, Cylinder, Pos, Compound, export_step,
        Mode, Locations,
    )
    BUILD123D_AVAILABLE = True
except Exception:  # ImportError ve OCC yükleme hataları
    BUILD123D_AVAILABLE = False


def _num(v, fb):
    try:
        f = float(v)
        return f if np.isfinite(f) else fb
    except (TypeError, ValueError):
        return fb


def _require():
    if not BUILD123D_AVAILABLE:
        raise RuntimeError(
            "build123d kurulu değil — STEP üretimi yapılamıyor. "
            "Kurulum: pip install build123d 'numpy<2'")


def _revolve_profile(points_rz):
    """(z, r) kapalı profilini X ekseni etrafında revolve eder (katı döner).

    build123d: profil XY düzleminde (x=z ekseni, y=r) çizilir, X ekseni
    etrafında 360° döndürülür.
    """
    pts = [(float(z), float(r)) for z, r in points_rz]
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    with BuildPart() as part:
        with BuildSketch(Plane.XY) as sk:
            with BuildLine():
                Polyline(*pts)
            make_face()
        revolve(axis=Axis.X)
    return part.part


def generate_step_assembly(motor_results, out_dir=None):
    """Motor bileşenlerini STEP olarak üretir; dosya yolu listesi döner."""
    _require()

    md = motor_results or {}
    name = md.get('motor_name') or 'HRMA_MOTOR'
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    if out_dir is None:
        out_dir = os.path.join(tempfile.gettempdir(), f'hrma_step_{stamp}')
    os.makedirs(out_dir, exist_ok=True)

    # ---- boyutlar (mm) ----
    L = _num(md.get('chamber_length'), 0.3) * 1000
    D_ch = _num(md.get('chamber_diameter'), 0.1) * 1000
    rc = D_ch / 2
    gd = md.get('grain_design') or {}
    L_g = min(_num(gd.get('grain_length_mm'),
                   _num(md.get('grain_length'), 0.8 * L / 1000) * 1000), 0.92 * L)
    r_p0 = _num(gd.get('port_diameter_initial_mm'),
                _num(md.get('port_diameter_initial'), 0.03) * 1000) / 2
    struct = md.get('structural_analysis') or {}
    wall = min(max(_num((struct.get('chamber_analysis') or {})
                        .get('recommended_thickness'), 0.045 * D_ch), 3.0),
               0.12 * D_ch)
    liner = min(max(0.02 * D_ch, 1.5), 5.0)
    cap = min(max(1.6 * wall, 8.0), 0.3 * rc + 8.0)

    files = {}
    solids = []

    # ---- Kamara: duvar + baş kapak (kapalı profil revolve) ----
    chamber_profile = [
        (-cap, 0.0), (-cap, rc + wall), (L, rc + wall), (L, rc),
        (0.0, rc), (0.0, 0.0),
    ]
    chamber = _revolve_profile(chamber_profile)
    files['chamber'] = os.path.join(out_dir, f'{name}_chamber.step')
    export_step(chamber, files['chamber'])
    solids.append(chamber)

    # ---- Nozul: iç kontur + duvar ofseti (tek kontur kaynağı) ----
    pts, meta = sample_nozzle_inner_contour(md)
    wall_noz = max(3.0, 0.1 * _num(md.get('throat_diameter'), 0.02) * 1000)
    inner = [(L + z, r) for z, r in pts]
    outer = [(z, r + wall_noz) for z, r in reversed(inner)]
    nozzle = _revolve_profile(inner + outer)
    files['nozzle'] = os.path.join(out_dir, f'{name}_nozzle.step')
    export_step(nozzle, files['nozzle'])
    solids.append(nozzle)

    # ---- Yakıt grain'i: portlu halka silindir ----
    r_go = rc - liner
    zg0 = 0.35 * max(4.0, L - L_g)
    with BuildPart() as grain_bp:
        with Locations((zg0 + L_g / 2, 0, 0)):
            Cylinder(radius=r_go, height=L_g, rotation=(0, 90, 0))
            Cylinder(radius=max(r_p0, 1.0), height=L_g + 2,
                     rotation=(0, 90, 0), mode=Mode.SUBTRACT)
    grain = grain_bp.part
    files['fuel_grain'] = os.path.join(out_dir, f'{name}_fuel_grain.step')
    export_step(grain, files['fuel_grain'])
    solids.append(grain)

    # ---- Enjektör plakası: gerçek orifis delikleri ----
    inj = md.get('injector_design') or md.get('injector') or {}
    n_ori = int(_num(inj.get('number_of_orifices') or inj.get('n_holes'), 12))
    d_ori = _num(inj.get('orifice_diameter_mm') or inj.get('hole_diameter'), 1.5)
    t_inj = min(max(0.9 * cap, 6.0), 24.0)
    with BuildPart() as inj_bp:
        with Locations((4 + t_inj / 2, 0, 0)):
            Cylinder(radius=rc - 0.5, height=t_inj, rotation=(0, 90, 0))
        ring_r = 0.7 * rc
        k = max(n_ori, 1)
        for i in range(k):
            a = 2 * np.pi * i / k
            with Locations((4 + t_inj / 2, ring_r * np.cos(a),
                           ring_r * np.sin(a))):
                Cylinder(radius=max(d_ori / 2, 0.25), height=t_inj + 2,
                         rotation=(0, 90, 0), mode=Mode.SUBTRACT)
    injector = inj_bp.part
    files['injector'] = os.path.join(out_dir, f'{name}_injector.step')
    export_step(injector, files['injector'])
    solids.append(injector)

    # ---- Assembly (tek dosya) ----
    assembly = Compound(children=solids)
    files['assembly'] = os.path.join(out_dir, f'{name}_assembly.step')
    export_step(assembly, files['assembly'])

    return files


def generate_tank_step(tank_data, out_dir=None):
    """Sıvı motor tankları için gerçek STEP (silindir + yarıküre başlıklar)."""
    _require()

    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    if out_dir is None:
        out_dir = os.path.join(tempfile.gettempdir(), f'hrma_tank_step_{stamp}')
    os.makedirs(out_dir, exist_ok=True)

    files = {}
    for key in ('fuel_tank', 'oxidizer_tank'):
        td = (tank_data or {}).get(key) or {}
        D = _num(td.get('diameter'), 0.3) * 1000
        Lc = _num(td.get('length'), 0.8) * 1000
        r = D / 2
        with BuildPart() as bp:
            with Locations((Lc / 2, 0, 0)):
                Cylinder(radius=r, height=Lc, rotation=(0, 90, 0))
            # Yarıküre başlıklar (Sphere kesişimi yerine tam küre — birleşim)
            from build123d import Sphere
            with Locations((0, 0, 0)):
                Sphere(radius=r)
            with Locations((Lc, 0, 0)):
                Sphere(radius=r)
        files[key] = os.path.join(out_dir, f'{key}.step')
        export_step(bp.part, files[key])
    return files
