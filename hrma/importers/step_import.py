"""STEP (ISO 10303-21) içe aktarma — geometri analizi ve ölçü adayı çıkarma.

Amaç: Kullanıcının yüklediği bir STEP dosyasından motor benzeri eksenel
simetrik geometrinin ölçü ADAYLARINI çıkarmak (Katman C, yönlendirmeli akış):
boğaz/çıkış/oda çapları, oda boyu, et kalınlığı. Hiçbir değer otomatik olarak
çözücüye YAZILMAZ; bu modül yalnızca aday + güven seviyesi üretir, son karar
kullanıcınındır (uydurma-veri-yasağı kimliği: eksik alan sessizce doldurulmaz,
bulunamayan öneri hiç yazılmaz, her öneri "estimated" işaretlidir).

Yöntem (hrma/export/step_export.py'deki build123d/OCC desenine paralel):
  1. build123d ``import_step`` ile katı okunur (OCC oturum birimi mm'ye
     sabitlenir; dosya inch/cm bildiriyorsa çekirdek mm'ye çevirir).
  2. TopExp_Explorer + BRepAdaptor_Surface ile yüzeyler taranır; silindir ve
     koni yüzeylerinin eksenleri alan ağırlıklı kümelenir. En büyük alanı
     paylaşan eksen = motor ekseni.
  3. Eksen üstündeki silindir/koni yüzeyleri (z0, z1, çap) adaylarına çevrilir;
     yüzey normalinin eksene göre yönünden iç/dış ayrımı yapılır (belirsizse
     dürüstçe "unknown").
  4. Aday listesinden öneriler türetilir: boğaz = iç konturun minimum çapı,
     çıkış = boğaz sonrası genişleyen son parçanın uç çapı, oda = en uzun iç
     silindir, et kalınlığı = oda z-aralığında dış-iç yarıçap farkının medyanı.

Tembel import: build123d/OCC yüklemesi saniyeler sürer; modül import'u ucuz
kalsın diye tüm ağır bağımlılıklar fonksiyon içinde yüklenir.

Kullanıcıya dönen tüm metinler İngilizce'dir (UI kuralı).
"""

import math
import os
import re

import numpy as np

# ---------------------------------------------------------------------------
# Modül parametreleri (parametre tutarlılığı kuralı: tek yerde tanım).
# Bu eşikler projede başka yerde tanımlı değildir (Grep ile doğrulandı);
# STEP içe aktarma katmanına özgüdür.
# ---------------------------------------------------------------------------
#: İki eksenin "aynı" sayılması için azami açı sapması (derece).
AXIS_ANGLE_TOL_DEG = 1.0
#: İki (paralel) eksen doğrusunun "çakışık" sayılması için azami dik uzaklık (mm).
AXIS_DIST_TOL_MM = 0.5
#: Yüzey normal-radyal doğrultu kosinüsü bu değerin altındaysa iç/dış "unknown".
SURFACE_SIDE_DOT_MIN = 0.5
#: İç konturda (r_max-r_min)/r_min bu oranın altındaysa "boğaz yok" kabul edilir
#: (düz boru için boğaz uydurulmaz).
THROAT_MIN_CONTRACTION = 0.02
#: Boğaz komşuluğunda "genişliyor" saymak için yarıçap çarpanı.
THROAT_NEIGHBOR_MARGIN = 1.05
#: Et kalınlığı medyanı için her iç/dış çakışma aralığından alınan örnek sayısı.
WALL_SAMPLES_PER_OVERLAP = 5
#: Et kalınlığı örnek yayılımı (maks-min)/medyan bu oranın altındaysa "high".
WALL_SPREAD_HIGH = 0.25
#: Tanınmayan (BSpline vb.) yüzey alanı oranı bu eşiği aşarsa uyarı yazılır.
UNRECOGNIZED_WARN_RATIO = 0.2
#: Eksenel simetriden sapma oranı bu eşiği aşarsa uyarı yazılır.
SYMMETRY_WARN_RATIO = 0.1
#: Oda önerisinde L/D bu değerin üstündeyse güven "high".
CHAMBER_LD_HIGH = 1.0

#: SI önek -> birim adı eşlemesi (STEP başlığındaki SI_UNIT gösterimi).
_SI_PREFIX_UNIT = {
    '$': 'm', '.MILLI.': 'mm', '.CENTI.': 'cm', '.DECI.': 'dm',
    '.MICRO.': 'um', '.NANO.': 'nm', '.KILO.': 'km',
}
#: CONVERSION_BASED_UNIT adları -> normalize birim adı.
_CONV_UNIT_NAMES = {
    'INCH': 'inch', 'INCHES': 'inch', "'INCH'": 'inch',
    'FOOT': 'ft', 'FEET': 'ft', 'MILE': 'mile',
    'MILLI INCH': 'mil', 'THOU': 'mil',
}

_EPS = 1e-9
#: Kayan nokta karşılaştırmalarında z/yarıçap eş kabul toleransı (mm).
_GEOM_TOL_MM = 1e-6


# ---------------------------------------------------------------------------
# Tembel bağımlılık yükleme
# ---------------------------------------------------------------------------
_DEPS_CACHE = None


def _load_deps():
    """build123d + OCP sembollerini bir kez yükler.

    Returns
    -------
    (dict | None, str | None)
        Başarıda (semboller, None); hatada (None, hata metni).
    """
    global _DEPS_CACHE
    if _DEPS_CACHE is not None:
        return _DEPS_CACHE
    try:
        from build123d import import_step, Solid  # noqa: F401
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
        from OCP.TopoDS import TopoDS
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.GeomAbs import (
            GeomAbs_Plane, GeomAbs_Cylinder, GeomAbs_Cone, GeomAbs_Sphere,
            GeomAbs_Torus, GeomAbs_SurfaceOfRevolution,
        )
        from OCP.BRepGProp import BRepGProp
        from OCP.GProp import GProp_GProps
        from OCP.gp import gp_Pnt, gp_Vec
        from OCP.STEPControl import STEPControl_Controller
        from OCP.Interface import Interface_Static
        _DEPS_CACHE = (dict(
            import_step=import_step, Solid=Solid,
            TopExp_Explorer=TopExp_Explorer, TopAbs_FACE=TopAbs_FACE,
            TopAbs_REVERSED=TopAbs_REVERSED, TopoDS=TopoDS,
            BRepAdaptor_Surface=BRepAdaptor_Surface,
            GeomAbs_Plane=GeomAbs_Plane, GeomAbs_Cylinder=GeomAbs_Cylinder,
            GeomAbs_Cone=GeomAbs_Cone, GeomAbs_Sphere=GeomAbs_Sphere,
            GeomAbs_Torus=GeomAbs_Torus,
            GeomAbs_SurfaceOfRevolution=GeomAbs_SurfaceOfRevolution,
            BRepGProp=BRepGProp, GProp_GProps=GProp_GProps,
            gp_Pnt=gp_Pnt, gp_Vec=gp_Vec,
            STEPControl_Controller=STEPControl_Controller,
            Interface_Static=Interface_Static,
        ), None)
    except Exception as exc:  # ImportError + OCC dinamik yükleme hataları
        # Hata önbelleğe alınmaz: kullanıcı paketi kurarsa sonraki çağrı dener.
        return None, (
            "build123d/OCP is not available — STEP import cannot run. "
            f"Install: pip install build123d 'numpy<2' (detail: {exc})")
    return _DEPS_CACHE


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------

def _rnd(x, nd=4):
    return round(float(x), nd)


def _unitize(v):
    n = np.linalg.norm(v)
    return v / n if n > _EPS else v


def _canonical_dir(d):
    """Yön işaretini belirlenimli yapar (en büyük mutlak bileşen pozitif)."""
    d = _unitize(np.asarray(d, dtype=float))
    i = int(np.argmax(np.abs(d)))
    return -d if d[i] < 0 else d


def _axis_angle_ok(d1, d2):
    c = abs(float(np.dot(_unitize(d1), _unitize(d2))))
    return c >= math.cos(math.radians(AXIS_ANGLE_TOL_DEG))


def _line_distance(o1, d1, o2):
    """(o1, d1) doğrusuna o2 noktasının dik uzaklığı (paralel eksen kıyası)."""
    d1 = _unitize(d1)
    w = np.asarray(o2, dtype=float) - np.asarray(o1, dtype=float)
    return float(np.linalg.norm(w - np.dot(w, d1) * d1))


def _same_axis(o1, d1, o2, d2):
    return _axis_angle_ok(d1, d2) and _line_distance(o1, d1, o2) <= AXIS_DIST_TOL_MM


def _detect_declared_unit(file_path):
    """STEP başlığındaki uzunluk birimini okur (varsayım YOK).

    Returns
    -------
    (str | None, str | None)
        (normalize birim adı ör. 'mm'/'inch', ham gösterim) — bulunamazsa
        (None, None).
    """
    buf = ''
    try:
        with open(file_path, 'r', errors='ignore') as fh:
            for line in fh:
                buf += line
                if ';' not in line:
                    # Tek ifade satırlara bölünmüş olabilir; biriktir.
                    if len(buf) > 65536:
                        buf = buf[-8192:]
                    continue
                statements = buf.split(';')
                buf = statements[-1]
                for st in statements[:-1]:
                    if 'LENGTH_UNIT' not in st:
                        continue
                    m = re.search(r"CONVERSION_BASED_UNIT\s*\(\s*'([^']+)'", st)
                    if m:
                        raw = m.group(1).strip().upper()
                        return _CONV_UNIT_NAMES.get(raw, raw.lower()), raw
                    m = re.search(
                        r"SI_UNIT\s*\(\s*(\$|\.\w+\.)\s*,\s*\.METRE\.", st)
                    if m:
                        raw = m.group(1)
                        return _SI_PREFIX_UNIT.get(raw, 'm?'), raw
    except OSError:
        return None, None
    return None, None


def _collect_solids(shape, deps):
    """build123d şeklinden (etiket, Solid) listesi çıkarır.

    Compound çocuk etiketleri (STEP ürün adları) korunur; etiketsiz katılar
    "solid_N" olarak adlandırılır — ad UYDURULMAZ, jenerik indeks verilir.
    """
    Solid = deps['Solid']
    found = []

    def walk(node):
        if isinstance(node, Solid):
            found.append(node)
            return
        children = list(getattr(node, 'children', []) or [])
        if children:
            for ch in children:
                walk(ch)
        elif hasattr(node, 'solids'):
            for s in node.solids():
                found.append(s)

    walk(shape)
    if hasattr(shape, 'solids'):
        flat = list(shape.solids())
        if len(found) != len(flat):
            # Ağaç yürüyüşü topolojiyle uyuşmadı — düz listeye düş (etiketsiz).
            found = flat
    out = []
    for i, s in enumerate(found):
        label = (getattr(s, 'label', '') or '').strip()
        out.append((label if label else f'solid_{i}', s))
    return out


def _face_side(adaptor, face, axis_origin, axis_dir, deps):
    """Yüzeyin iç/dış ayrımı: normalin eksene göre radyal yönü.

    Normal eksenden dışa bakıyorsa malzeme içeride kalır -> "outer";
    eksene doğru bakıyorsa yüzey bir oyuğu sarar -> "inner"; belirsizse
    dürüstçe "unknown".
    """
    try:
        u0, u1 = adaptor.FirstUParameter(), adaptor.LastUParameter()
        v0, v1 = adaptor.FirstVParameter(), adaptor.LastVParameter()
        um, vm = (u0 + u1) / 2.0, (v0 + v1) / 2.0
        p = deps['gp_Pnt']()
        d1u = deps['gp_Vec']()
        d1v = deps['gp_Vec']()
        adaptor.D1(um, vm, p, d1u, d1v)
        n = d1u.Crossed(d1v)
        if face.Orientation() == deps['TopAbs_REVERSED']:
            n.Reverse()
        n_np = _unitize(np.array([n.X(), n.Y(), n.Z()]))
        p_np = np.array([p.X(), p.Y(), p.Z()])
        w = p_np - np.asarray(axis_origin, dtype=float)
        radial = w - np.dot(w, axis_dir) * np.asarray(axis_dir, dtype=float)
        radial = _unitize(radial)
        dot = float(np.dot(n_np, radial))
        if dot > SURFACE_SIDE_DOT_MIN:
            return 'outer'
        if dot < -SURFACE_SIDE_DOT_MIN:
            return 'inner'
        return 'unknown'
    except Exception:
        return 'unknown'


def _face_records(solid_topods, deps):
    """Katının tüm yüzeylerini sınıflandırır; kayıt listesi döndürür."""
    records = []
    props_cls = deps['GProp_GProps']
    exp = deps['TopExp_Explorer'](solid_topods, deps['TopAbs_FACE'])
    while exp.More():
        face = deps['TopoDS'].Face_s(exp.Current())
        exp.Next()
        try:
            props = props_cls()
            deps['BRepGProp'].SurfaceProperties_s(face, props)
            area = float(props.Mass())
            ad = deps['BRepAdaptor_Surface'](face, True)
            stype = ad.GetType()
        except Exception:
            records.append({'stype': 'other', 'area': 0.0})
            continue

        rec = {'area': area, 'face': face, 'adaptor': ad}
        try:
            if stype == deps['GeomAbs_Cylinder']:
                cyl = ad.Cylinder()
                ax = cyl.Axis()
                loc, dr = ax.Location(), ax.Direction()
                o = np.array([loc.X(), loc.Y(), loc.Z()])
                d = _unitize(np.array([dr.X(), dr.Y(), dr.Z()]))
                v0, v1 = ad.FirstVParameter(), ad.LastVParameter()
                if not (np.isfinite(v0) and np.isfinite(v1)):
                    raise ValueError('infinite parameter range')
                rec.update(stype='cylinder', axis_origin=o, axis_dir=d,
                           p_start=o + v0 * d, p_end=o + v1 * d,
                           r_start=float(cyl.Radius()),
                           r_end=float(cyl.Radius()))
            elif stype == deps['GeomAbs_Cone']:
                cone = ad.Cone()
                ax = cone.Axis()
                loc, dr = ax.Location(), ax.Direction()
                o = np.array([loc.X(), loc.Y(), loc.Z()])
                d = _unitize(np.array([dr.X(), dr.Y(), dr.Z()]))
                a = float(cone.SemiAngle())
                R = float(cone.RefRadius())
                v0, v1 = ad.FirstVParameter(), ad.LastVParameter()
                if not (np.isfinite(v0) and np.isfinite(v1)):
                    raise ValueError('infinite parameter range')
                rec.update(stype='cone', axis_origin=o, axis_dir=d,
                           p_start=o + (v0 * math.cos(a)) * d,
                           p_end=o + (v1 * math.cos(a)) * d,
                           r_start=max(R + v0 * math.sin(a), 0.0),
                           r_end=max(R + v1 * math.sin(a), 0.0))
            elif stype == deps['GeomAbs_Plane']:
                pl = ad.Plane()
                nd = pl.Axis().Direction()
                rec.update(stype='plane',
                           normal=_unitize(np.array([nd.X(), nd.Y(), nd.Z()])))
            elif stype == deps['GeomAbs_Sphere']:
                sp = ad.Sphere()
                c = sp.Location()
                rec.update(stype='sphere',
                           center=np.array([c.X(), c.Y(), c.Z()]))
            elif stype == deps['GeomAbs_Torus']:
                to = ad.Torus()
                ax = to.Axis()
                loc, dr = ax.Location(), ax.Direction()
                rec.update(stype='torus',
                           axis_origin=np.array([loc.X(), loc.Y(), loc.Z()]),
                           axis_dir=_unitize(
                               np.array([dr.X(), dr.Y(), dr.Z()])))
            elif stype == deps['GeomAbs_SurfaceOfRevolution']:
                ax = ad.AxeOfRevolution()
                loc, dr = ax.Location(), ax.Direction()
                rec.update(stype='revolution',
                           axis_origin=np.array([loc.X(), loc.Y(), loc.Z()]),
                           axis_dir=_unitize(
                               np.array([dr.X(), dr.Y(), dr.Z()])))
            else:
                rec.update(stype='other')
        except Exception:
            rec.update(stype='other')
        records.append(rec)
    return records


def _cluster_axes(records):
    """Silindir/koni eksenlerini alan ağırlıklı kümeler; kümeleri döndürür."""
    clusters = []
    for rec in records:
        if rec['stype'] not in ('cylinder', 'cone'):
            continue
        for cl in clusters:
            if _same_axis(cl['origin'], cl['dir'],
                          rec['axis_origin'], rec['axis_dir']):
                cl['area'] += rec['area']
                cl['members'].append(rec)
                break
        else:
            clusters.append({
                'origin': np.asarray(rec['axis_origin'], dtype=float),
                'dir': _canonical_dir(rec['axis_dir']),
                'area': rec['area'],
                'members': [rec],
            })
    return clusters


def _is_on_axis(rec, axis_origin, axis_dir):
    """Bir yüzey kaydının motor eksenine göre eksen-üstü olup olmadığı."""
    st = rec['stype']
    if st in ('cylinder', 'cone', 'torus', 'revolution'):
        return _same_axis(axis_origin, axis_dir,
                          rec['axis_origin'], rec['axis_dir'])
    if st == 'plane':
        return _axis_angle_ok(rec['normal'], axis_dir)
    if st == 'sphere':
        return _line_distance(axis_origin, axis_dir,
                              rec['center']) <= AXIS_DIST_TOL_MM
    return False


def _project_segment(rec, axis_origin, axis_dir):
    """Yüzeyin eksen boyu (z0, r0, z1, r1) izdüşümü; z0 < z1 garanti."""
    z0 = float(np.dot(rec['p_start'] - axis_origin, axis_dir))
    z1 = float(np.dot(rec['p_end'] - axis_origin, axis_dir))
    r0, r1 = rec['r_start'], rec['r_end']
    if z0 > z1:
        z0, z1, r0, r1 = z1, z0, r1, r0
    return z0, r0, z1, r1


def _segment_radius_at(seg, z):
    """Segment üzerinde z konumundaki yarıçap (doğrusal enterpolasyon)."""
    z0, r0, z1, r1 = seg['z0'], seg['r0'], seg['z1'], seg['r1']
    if abs(z1 - z0) < _GEOM_TOL_MM:
        return 0.5 * (r0 + r1)
    t = (z - z0) / (z1 - z0)
    return r0 + t * (r1 - r0)


def _build_profile(segments):
    """Segment listesinden [[z, r], ...] meridyen çoklu çizgisi üretir."""
    pts = []
    for seg in sorted(segments, key=lambda s: (s['z0'], s['z1'])):
        for z, r in ((seg['z0'], seg['r0']), (seg['z1'], seg['r1'])):
            p = [_rnd(z), _rnd(r)]
            if not pts or (abs(pts[-1][0] - p[0]) > _GEOM_TOL_MM
                           or abs(pts[-1][1] - p[1]) > _GEOM_TOL_MM):
                pts.append(p)
    return pts


def _suggestion(value, candidate_index, confidence):
    """Öneri girdisi — her öneri açıkça 'estimated' işaretlidir."""
    return {'value': _rnd(value), 'candidate_index': int(candidate_index),
            'confidence': confidence, 'estimated': True}


def _derive_suggestions(segments, warnings):
    """Aday segmentlerden ölçü önerileri türetir (bulunamayan alan YAZILMAZ)."""
    suggestions = {}
    inner = [s for s in segments if s['surface'] == 'inner']
    outer = [s for s in segments if s['surface'] == 'outer']
    if not inner:
        warnings.append(
            'no inner surfaces recognized; no dimension suggestions derived')
        return suggestions

    # Uç noktalar: (z, r, aday indeksi)
    endpoints = []
    for s in inner:
        endpoints.append((s['z0'], s['r0'], s['index']))
        endpoints.append((s['z1'], s['r1'], s['index']))
    r_min = min(e[1] for e in endpoints)
    r_max = max(e[1] for e in endpoints)

    # --- Boğaz: iç konturun minimum çapı ---
    z_throat = None
    if (r_max - r_min) / max(r_min, _EPS) < THROAT_MIN_CONTRACTION:
        warnings.append(
            'no distinct throat found in inner contour '
            '(inner radius nearly constant)')
    else:
        z_throat, _, throat_idx = min(
            (e for e in endpoints if e[1] <= r_min + _GEOM_TOL_MM),
            key=lambda e: e[0])
        expands_before = any(
            e[0] < z_throat - _GEOM_TOL_MM
            and e[1] > r_min * THROAT_NEIGHBOR_MARGIN for e in endpoints)
        expands_after = any(
            e[0] > z_throat + _GEOM_TOL_MM
            and e[1] > r_min * THROAT_NEIGHBOR_MARGIN for e in endpoints)
        if expands_before and expands_after:
            conf = 'high'
        elif expands_before or expands_after:
            conf = 'medium'
        else:
            conf = 'low'
        suggestions['throat_diameter_mm'] = _suggestion(
            2.0 * r_min, throat_idx, conf)

    # --- Oda: en uzun iç silindir ---
    chamber = None
    cylinders = [s for s in inner if s['kind'] == 'cylinder']
    if cylinders:
        chamber = max(cylinders, key=lambda s: s['z1'] - s['z0'])
        length = chamber['z1'] - chamber['z0']
        diam = 2.0 * chamber['r0']
        if z_throat is not None and chamber['r0'] <= r_min * (
                1.0 + THROAT_MIN_CONTRACTION):
            conf = 'low'  # "oda" diye bulunan silindir boğaz çapında — şüpheli
        elif diam > 0 and length / diam >= CHAMBER_LD_HIGH:
            conf = 'high'
        else:
            conf = 'medium'
        suggestions['chamber_diameter_mm'] = _suggestion(
            diam, chamber['index'], conf)
        suggestions['chamber_length_mm'] = _suggestion(
            length, chamber['index'], conf)

    # --- Çıkış: boğaz sonrası genişleyen son parçanın uç çapı ---
    if z_throat is not None:
        z_lo = min(e[0] for e in endpoints)
        z_hi = max(e[0] for e in endpoints)
        exit_end = None
        conf_cap = None
        if chamber is not None:
            z_ch = 0.5 * (chamber['z0'] + chamber['z1'])
            # Çıkış, boğazın oda tarafının karşısındaki uçtadır.
            exit_end = z_hi if z_ch < z_throat else z_lo
        elif z_hi - z_throat > _GEOM_TOL_MM or z_throat - z_lo > _GEOM_TOL_MM:
            # Oda bulunamadı: daha geniş uca giden taraf seçilir (düşük güven).
            r_at_hi = max((e[1] for e in endpoints
                           if abs(e[0] - z_hi) < _GEOM_TOL_MM), default=0.0)
            r_at_lo = max((e[1] for e in endpoints
                           if abs(e[0] - z_lo) < _GEOM_TOL_MM), default=0.0)
            exit_end = z_hi if r_at_hi >= r_at_lo else z_lo
            conf_cap = 'low'
        if exit_end is not None and abs(exit_end - z_throat) > _GEOM_TOL_MM:
            ends = [e for e in endpoints
                    if abs(e[0] - exit_end) < _GEOM_TOL_MM]
            if ends:
                _, r_exit, exit_idx = max(ends, key=lambda e: e[1])
                exit_seg = next(s for s in inner if s['index'] == exit_idx)
                far_r, near_r = ((exit_seg['r1'], exit_seg['r0'])
                                 if exit_end >= exit_seg['z1'] - _GEOM_TOL_MM
                                 else (exit_seg['r0'], exit_seg['r1']))
                if r_exit <= r_min * (1.0 + THROAT_MIN_CONTRACTION):
                    conf = 'low'  # çıkış çapı boğazdan farksız — genişleme yok
                elif exit_seg['kind'] == 'cone' and far_r > near_r:
                    conf = 'high'
                else:
                    conf = 'medium'
                if conf_cap == 'low':
                    conf = 'low'
                suggestions['exit_diameter_mm'] = _suggestion(
                    2.0 * r_exit, exit_idx, conf)

    # --- Et kalınlığı: aynı z aralığında (dış - iç) yarıçap farkı medyanı ---
    samples = []  # (kalınlık, dış aday indeksi)
    restrict = (chamber['z0'], chamber['z1']) if chamber is not None else None
    for os_ in outer:
        for is_ in inner:
            lo = max(os_['z0'], is_['z0'])
            hi = min(os_['z1'], is_['z1'])
            if restrict is not None:
                lo, hi = max(lo, restrict[0]), min(hi, restrict[1])
            if hi - lo <= _GEOM_TOL_MM:
                continue
            for k in range(WALL_SAMPLES_PER_OVERLAP):
                z = lo + (hi - lo) * (k + 0.5) / WALL_SAMPLES_PER_OVERLAP
                t = _segment_radius_at(os_, z) - _segment_radius_at(is_, z)
                if t > _GEOM_TOL_MM:
                    samples.append((t, os_['index']))
    used_fallback = False
    if not samples and restrict is not None:
        # Oda aralığında çakışma yok — tüm çakışmalara düş (düşük güven).
        used_fallback = True
        for os_ in outer:
            for is_ in inner:
                lo = max(os_['z0'], is_['z0'])
                hi = min(os_['z1'], is_['z1'])
                if hi - lo <= _GEOM_TOL_MM:
                    continue
                for k in range(WALL_SAMPLES_PER_OVERLAP):
                    z = lo + (hi - lo) * (k + 0.5) / WALL_SAMPLES_PER_OVERLAP
                    t = (_segment_radius_at(os_, z)
                         - _segment_radius_at(is_, z))
                    if t > _GEOM_TOL_MM:
                        samples.append((t, os_['index']))
    if samples:
        values = np.array([s[0] for s in samples])
        med = float(np.median(values))
        nearest = min(samples, key=lambda s: abs(s[0] - med))
        spread = float((values.max() - values.min()) / max(med, _EPS))
        if used_fallback or restrict is None:
            conf = 'low'
        elif len(samples) >= 3 and spread < WALL_SPREAD_HIGH:
            conf = 'high'
        else:
            conf = 'medium'
        suggestions['wall_thickness_mm'] = _suggestion(med, nearest[1], conf)

    return suggestions


# ---------------------------------------------------------------------------
# Ana giriş noktası
# ---------------------------------------------------------------------------

def analyze_step(file_path, solid_index=None):
    """STEP dosyasını analiz eder; ölçü adayları + önerileri döndürür.

    Parameters
    ----------
    file_path : str
        Okunacak STEP dosyasının yolu.
    solid_index : int | None
        Montaj (çok katılı) dosyada analiz edilecek katının indeksi.
        None ise en büyük hacimli katı seçilir ve uyarı yazılır.

    Returns
    -------
    dict
        Başarıda: source, unit, axis, symmetry_deviation, candidates,
        suggestions, profile_2d, unrecognized_area_ratio, solids,
        solid_analyzed_index, warnings.
        Hatada: source, error, error_kind, candidates=[], warnings.
        İstisna sızdırmaz; tüm hatalar sözlük olarak döner.
    """
    warnings = []
    base = {'source': 'step_import'}

    def _fail(msg, kind):
        return {**base, 'error': msg, 'error_kind': kind,
                'candidates': [], 'warnings': warnings}

    try:
        # 1) Dosya ön kontrolleri (ağır bağımlılık yüklemeden)
        if not isinstance(file_path, str) or not os.path.isfile(file_path):
            return _fail('file not found', 'invalid_file')
        try:
            with open(file_path, 'rb') as fh:
                head = fh.read(4096)
        except OSError as exc:
            return _fail(f'file could not be read: {exc}', 'invalid_file')
        if b'ISO-10303-21' not in head:
            return _fail(
                'not a STEP file (missing ISO-10303-21 header); only '
                'plain-text STEP (.step/.stp) is supported', 'invalid_file')

        # 2) Bağımlılıklar
        deps, dep_err = _load_deps()
        if deps is None:
            return _fail(dep_err, 'dependency_missing')

        # 3) Birim: dosya başlığından OKUNUR, varsayılmaz
        unit, _raw = _detect_declared_unit(file_path)
        if unit is None:
            unit = 'unknown'
            warnings.append(
                'length unit declaration not found in STEP header; '
                'geometry interpreted as millimetres by the kernel')
        elif unit != 'mm':
            warnings.append(
                f'STEP file declares {unit} units; all values converted '
                'to millimetres by the geometry kernel')
        base['unit'] = unit

        # 4) Okuma — OCC oturum birimi mm'ye sabitlenir (belirlenimli okuma)
        deps['STEPControl_Controller'].Init_s()
        deps['Interface_Static'].SetCVal_s('xstep.cascade.unit', 'MM')
        try:
            shape = deps['import_step'](file_path)
        except Exception as exc:
            return _fail(f'STEP file could not be parsed: {exc}',
                         'invalid_file')

        solids = _collect_solids(shape, deps)
        if not solids:
            return _fail('no solid bodies found in STEP file', 'invalid_file')

        solids_info = []
        volumes = []
        for i, (name, sld) in enumerate(solids):
            try:
                vol = float(sld.volume)
            except Exception:
                vol = 0.0
            volumes.append(vol)
            solids_info.append(
                {'index': i, 'name': name, 'volume_mm3': _rnd(vol, 2)})
        base['solids'] = solids_info

        if solid_index is None:
            chosen = int(np.argmax(volumes))
            if len(solids) > 1:
                warnings.append(
                    f'assembly: {len(solids)} solids, largest analyzed '
                    f'(index {chosen})')
        else:
            try:
                chosen = int(solid_index)
            except (TypeError, ValueError):
                return _fail('solid_index must be an integer', 'bad_request')
            if not (0 <= chosen < len(solids)):
                return _fail(
                    f'solid_index out of range (0..{len(solids) - 1})',
                    'bad_request')
        base['solid_analyzed_index'] = chosen
        solid = solids[chosen][1]

        # 5) Yüzey taraması
        records = _face_records(solid.wrapped, deps)
        total_area = sum(r['area'] for r in records)
        if total_area <= _EPS:
            return _fail('solid has no measurable surface area',
                         'invalid_file')

        # 6) Eksen tespiti: silindir/koni eksenlerinin alan ağırlıklı kümesi
        clusters = _cluster_axes(records)
        if not clusters:
            warnings.append(
                'no cylindrical or conical faces found; motor axis could '
                'not be determined')
            unrec = sum(r['area'] for r in records
                        if r['stype'] == 'other') / total_area
            return {**base, 'axis': None, 'symmetry_deviation': None,
                    'candidates': [], 'suggestions': {},
                    'profile_2d': {'inner': [], 'outer': []},
                    'unrecognized_area_ratio': _rnd(unrec),
                    'warnings': warnings}
        best = max(clusters, key=lambda c: c['area'])
        axis_origin = best['origin']
        axis_dir = _canonical_dir(best['dir'])

        # 7) Simetri sapması + tanınmayan alan oranı
        off_axis_area = 0.0
        unrecognized_area = 0.0
        for rec in records:
            if rec['stype'] == 'other':
                unrecognized_area += rec['area']
            elif not _is_on_axis(rec, axis_origin, axis_dir):
                off_axis_area += rec['area']
        symmetry_deviation = off_axis_area / total_area
        unrecognized_ratio = unrecognized_area / total_area
        if symmetry_deviation > SYMMETRY_WARN_RATIO:
            warnings.append(
                'solid deviates from axisymmetry (off-axis surface area '
                f'ratio {symmetry_deviation:.2f}); candidates cover only '
                'the on-axis surfaces')
        if unrecognized_ratio > UNRECOGNIZED_WARN_RATIO:
            warnings.append(
                'large fraction of surface area '
                f'({unrecognized_ratio:.2f}) uses unsupported surface '
                'types (freeform/B-spline); analysis may be incomplete')

        # 8) Adaylar: eksen üstü silindir/koni yüzeyleri
        segments = []
        for rec in records:
            if rec['stype'] not in ('cylinder', 'cone'):
                continue
            if not _same_axis(axis_origin, axis_dir,
                              rec['axis_origin'], rec['axis_dir']):
                continue
            z0, r0, z1, r1 = _project_segment(rec, axis_origin, axis_dir)
            side = _face_side(rec['adaptor'], rec['face'],
                              axis_origin, axis_dir, deps)
            segments.append({'kind': rec['stype'], 'surface': side,
                             'z0': z0, 'r0': r0, 'z1': z1, 'r1': r1,
                             'area': rec['area']})
        if not segments:
            return {**base, 'axis': None, 'symmetry_deviation':
                    _rnd(symmetry_deviation), 'candidates': [],
                    'suggestions': {},
                    'profile_2d': {'inner': [], 'outer': []},
                    'unrecognized_area_ratio': _rnd(unrecognized_ratio),
                    'warnings': warnings + [
                        'no on-axis cylinder/cone faces; no candidates']}

        # z ekseni kaydırması: en küçük z = 0 (UI kesit çizimi için doğal)
        z_shift = min(s['z0'] for s in segments)
        for s in segments:
            s['z0'] -= z_shift
            s['z1'] -= z_shift
        axis_origin_out = axis_origin + z_shift * axis_dir

        segments.sort(key=lambda s: (s['z0'], s['z1'], s['r0']))
        for i, s in enumerate(segments):
            s['index'] = i

        candidates = []
        for s in segments:
            cand = {'kind': s['kind'], 'surface': s['surface'],
                    'd1_mm': _rnd(2.0 * s['r0']),
                    'z0_mm': _rnd(s['z0']), 'z1_mm': _rnd(s['z1']),
                    'area_mm2': _rnd(s['area'], 2)}
            if s['kind'] == 'cone':
                cand['d2_mm'] = _rnd(2.0 * s['r1'])
            candidates.append(cand)

        unknown_n = sum(1 for s in segments if s['surface'] == 'unknown')
        if unknown_n:
            warnings.append(
                f'{unknown_n} candidate surface(s) could not be classified '
                'as inner/outer; they are excluded from suggestions')

        # 9) Öneriler (bulunamayan alan hiç yazılmaz — sessiz doldurma yasak)
        suggestions = _derive_suggestions(segments, warnings)

        profile = {
            'inner': _build_profile(
                [s for s in segments if s['surface'] == 'inner']),
            'outer': _build_profile(
                [s for s in segments if s['surface'] == 'outer']),
        }

        return {**base,
                'axis': {'origin': [_rnd(v) for v in axis_origin_out],
                         'direction': [_rnd(v, 6) for v in axis_dir]},
                'symmetry_deviation': _rnd(symmetry_deviation),
                'candidates': candidates,
                'suggestions': suggestions,
                'profile_2d': profile,
                'unrecognized_area_ratio': _rnd(unrecognized_ratio),
                'warnings': warnings}
    except Exception as exc:  # hiçbir istisna sızdırılmaz
        return _fail(f'unexpected analysis error: {type(exc).__name__}: {exc}',
                     'internal')
