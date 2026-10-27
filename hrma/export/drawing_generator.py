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
import re
from datetime import datetime

import numpy as np

from hrma.engines.nozzle_design import sample_nozzle_inner_contour
from hrma.export.export_workspace import (
    atomic_produce, new_workspace, purge_stale_workspaces)
from hrma.utils.input_guard import (
    finite_number, finite_positive, safe_name)

#: DXF birim başlığı: 4 = millimetre (DXF referansı, $INSUNITS tablosu).
#: ezdxf.new(..., setup=True) varsayılanı 6'dır (METRE) ve depoda hiçbir yerde
#: ezilmiyordu; üretilen geometri ise mm (ölçüldü: X aralığı 0 -> 1077.04).
#: Yani CAD yazılımı çizimi 1000× büyük ölçekliyordu — A1'deki STL hatasının
#: aynı sınıfı. Faz 4B / A2.
DXF_INSUNITS_MILLIMETERS = 4
#: ÖH V3 CAD A2 · U5 — ilişkisel ölçü varlıklarının (DIMENSION) katmanı.
DXF_DIMENSION_LAYER = 'DIMENSIONS'


def _num(v, fb):
    """Sonlu sayı ya da ``fb`` yedeği — kural merkezden (OH-D27-11)."""
    return finite_number(v, fb)


class DrawingGeometryError(ValueError):
    """İmalat çizimi için zorunlu ölçü çözülemedi — çizim ÜRETİLMEZ."""


#: Ölçüsü çözülemeyen satırların çizimde ve tabloda göründüğü metin.
NOT_RESOLVED = 'NOT AVAILABLE FROM THE ANALYSIS'

# ---------------------------------------------------------------------------
# ÖH Z5S / defter P9B2-22, -28, -29: çizimin BEYAN ETMEDİĞİ üreteç kararları
# ---------------------------------------------------------------------------
#: Grain'in eksenel konumu (katı motorda) bir ÜRETEÇ YERLEŞİM kuralıdır.
#: ÖH V3 CAD A2 · H7: sabitler ARTIK burada yeniden YAZILMAZ — bu modül
#: STEP ve STL ile aynı tek tanımı (``cad_visualization``) okur; kural da
#: aynı fonksiyondur (``grain_axial_layout_mm``). Eskiden buradaki kopya
#: yığın boyunu (segment araları) görmüyordu ve çizim 1,4 mm farklı yerdeydi.
from hrma.export.cad_visualization import (  # noqa: E402,F401
    GRAIN_AXIAL_MIN_SLACK_MM, GRAIN_AXIAL_POSITION_FRACTION)
from hrma.export.motor_geometry import (  # noqa: E402
    EXPORT_AXIS, EXPORT_AXIS_NOTE, MESH_BUILD_AXIS)
#: Eksen sözleşmesi (P9B2-28). ÖH V3 CAD A2 (A1 devri D-A2-4): bu metin ÖH
#: D26'dan beri YANLIŞTI — "the STL meshes ... are built about +Z - rotate
#: them 90 deg about Y" diyordu, oysa D26 STL paketini dosyaya yazarken +X'e
#: çeviriyor (``cad_visualization.export_stl_files``). İmalat çizimindeki
#: künye artık tek kaynaktan (``motor_geometry.EXPORT_AXIS_NOTE``) kurulur.
AXIS_CONVENTION_NOTE = (
    'AXIS CONVENTION: ' + EXPORT_AXIS_NOTE[len('axis convention: '):]
    + ' This drawing uses the same axis (+' + EXPORT_AXIS + ', left to '
    'right).')
#: PDF ölçü tablosunun eksen satırı — aynı tek kaynaktan.
AXIS_CONVENTION_ROW = (
    'motor axis = +' + EXPORT_AXIS + ' in this drawing, in the STEP solids '
    'and in the STL files (x = 0 at the injector face); the STL meshes are '
    'built about +' + MESH_BUILD_AXIS + ' in memory and rotated to +'
    + EXPORT_AXIS + ' when written, so the exports open together without '
    'rotating anything')
#: Lüle et kalınlığı bu görünüşte ÇİZİLMEZ: dış profil yok, dolayısıyla
#: ölçülendirilmez de. "WALL THICKNESS" ölçüsü YALNIZ kamaraya aittir
#: (P9B2-29).
NOZZLE_WALL_NOT_DRAWN_NOTE = (
    'NOZZLE WALL: the nozzle outer profile is NOT drawn and NOT dimensioned '
    'in this view; the WALL THICKNESS dimension above belongs to the chamber '
    'only. The STEP export builds the nozzle wall from a declared generator '
    'rule (see the nozzle part name in the STEP package), not from an analysis'
)


def _nozzle_wall_note(motor_results):
    """Lüle et beyanı — STEP'in GERÇEKTEN kullandığı kaynağı söyler.

    ÖH V3 CAD A1 · H2: STEP lülesi artık çözücü et yayımlıyorsa onu çizer
    (``cad_visualization._nozzle_wall_design``, tek kaynak). Sabit not
    (``NOZZLE_WALL_NOT_DRAWN_NOTE``) "generator rule, not from an analysis"
    diyordu; hibritte bu artık YANLIŞ olurdu. Et yayımlanmamışsa sabit not
    aynen basılır.
    """
    from hrma.export.cad_visualization import _nozzle_wall_design
    design = _nozzle_wall_design(motor_results)
    if not design['published']:
        return NOZZLE_WALL_NOT_DRAWN_NOTE
    return ('NOZZLE WALL: the nozzle outer profile is NOT drawn and NOT '
            'dimensioned in this view; the WALL THICKNESS dimension above '
            'belongs to the chamber only. The STEP export builds the nozzle '
            f"wall {design['thickness_m'] * 1000.0:.2f} mm from "
            f"{design['source']} (see the nozzle part name in the STEP "
            'package)')


def _grain_layout(motor_results, chamber_length_mm, grain_length_mm):
    """Tane yığını planı + ön yüz — STEP ve STL ile TEK kaynak.

    ÖH V3 CAD A1 · H3 / A2 · H7. Döner ``(yığın, yerleşim)``:
    ``cad_visualization.grain_stack_plan`` (segment sayısı, boyu, boşluğu)
    ve ``grain_axial_layout_mm`` (çözücü konumu ya da beyanlı üreteç
    kuralı). Yayımlanan düzen çizilemiyorsa çizim de ÜRETİLMEZ
    (``DrawingGeometryError``; uç 422 ``incomplete_export_inputs`` verir).
    """
    from hrma.export.cad_visualization import (
        GrainLayoutError, grain_axial_layout_mm, grain_stack_plan)
    yigin = grain_stack_plan(motor_results, grain_length_mm)
    try:
        yer = grain_axial_layout_mm(motor_results, chamber_length_mm,
                                    yigin['stack_mm'])
    except GrainLayoutError as hata:
        raise DrawingGeometryError(str(hata)) from hata
    return yigin, yer


def _grain_section_gate(motor_results, artefact):
    """ÖH V3 CAD A2 · H1 — çizilemeyen tane kesiti çizime de girmez.

    Uç kapısı (app.py) aynı hükmü 422 + i18n ile verir; bu, uçtan geçmeyen
    doğrudan çağrılar için ikinci kapıdır (``step_export`` ile aynı).
    """
    from hrma.export.cad_visualization import (
        grain_gate_message, grain_section_refusals)
    red = grain_section_refusals(motor_results)
    if red:
        raise DrawingGeometryError(grain_gate_message(red, artefact))


def _nozzle_angle_source(motor_results):
    """Lüle açılarının KAYNAK beyanı — çözücünün kendi alanından.

    ÖH Z5S / defter P9B2-10. Ölçüldü (27 Ağustos 2026, Ø100 mm katı motor):
    çözücü ``nozzle_angles['angles_source'] = 'conical_default_30_15'``
    yayımlıyor, yani "bu 30°/15° bir ÜRETEÇ VARSAYIMIDIR, kullanıcı girdisi
    değildir" diyor. İmalat çizimi bu beyanı düşürüp yalnız
    ``conical; conv 30.0 deg, div 15.0 deg`` basıyordu — imalatçı, açının
    tasarım kararı mı yoksa varsayılan mı olduğunu göremiyordu.

    Künye KAZANILIR: beyan varsa aynen taşınır, "default" diyorsa okuyucuya
    açıkça söylenir, hiç beyan yoksa "kullanıcı girdisi" İDDİA EDİLMEZ.
    """
    angles = (motor_results or {}).get('nozzle_angles') or {}
    declared = angles.get('angles_source')
    if not isinstance(declared, str) or not declared.strip():
        return ('angle source NOT STATED by this analysis run (no '
                'nozzle_angles.angles_source)')
    declared = declared.strip()
    if 'default' in declared.lower():
        return (f'angles_source = "{declared}" - GENERATOR DEFAULT angles, '
                'NOT a user input and NOT an optimised contour')
    return f'angles_source = "{declared}"'


def _nozzle_div_angle_meaning(noz_type):
    """``div`` sütununun o lüle ailesinde NE ANLAMA geldiğini söyler.

    ÖH D15 (defter P9B2-09): çan lülede ıraksak açı sabit değildir; tablodaki
    sayı BOĞAZ açısıdır ve çıkışta açı küçülür. Aynı ayrım CAD sözlüğünde
    ``divergence_angle_meaning`` alanında zaten yayımlanıyordu; imalat
    çiziminde yoktu.
    """
    from hrma.export.cad_visualization import _nozzle_family
    if _nozzle_family(noz_type) == 'bell':
        return 'throat angle; the wall angle decreases toward the exit'
    return 'constant half angle'


def _nozzle_angle_source_tag(motor_results):
    """Açı satırının yanına basılan KISA künye.

    Uzun beyan ayrı bir tablo satırında yaşar; buradaki kısa etiket sayının
    TAM YANINDA durur, çünkü imalatçının gördüğü ilk şey sayıdır. Etiket
    bilerek kısa tutulur (<= 22 karakter): tablo satırı sarmalanırsa
    kendisinden sonraki satırların yaprak dağılımı kayar ve kardeş bekçiler
    başka yaprağa bakmaya başlar.
    """
    angles = (motor_results or {}).get('nozzle_angles') or {}
    declared = angles.get('angles_source')
    if not isinstance(declared, str) or not declared.strip():
        return '[SOURCE NOT STATED]'
    declared = declared.strip()
    if 'default' in declared.lower():
        return '[GENERATOR DEFAULT]'
    return '[src: ' + declared[:14] + ']'


def _motor_claims_injector(motor_results):
    """Bu sonuç bir enjektör parçası İDDİA EDİYOR mu?

    ÖH Z5S / defter P9B2-30. Katı motorda enjektör YOKTUR; buna rağmen çizim
    paketi her koşuda "SHEET 2 - INJECTOR FACE PATTERN" yaprağını basıyor ve
    üzerine ``Injector render failed: ... (injector_design missing)`` yazıyordu
    (ölçüldü, Ø100 mm katı motor). Bu bir HATA değil, OLMAYAN bir parçadır:
    hata mesajı basmak yerine yaprak hiç üretilmez.

    Kapı ``step_export.generate_step_assembly`` ile AYNI soruyu sorar (sonuç
    bir enjektör bloğu taşıyor mu) — böylece aynı koşuda STEP'te plaka varken
    çizimde yaprak eksik (ya da tersi) olamaz. Blok BOŞ olsa bile iddia
    sayılır: o hâlde plan gerçekten çözülemedi demektir ve yaprak, dürüst
    başarısızlık notuyla basılır.
    """
    md = motor_results or {}
    return any(isinstance(md.get(key), dict)
               for key in ('injector_design', 'injector', 'injector_results'))


def _prepare(motor_results):
    """Girdiyi METRE'ye indirger ve çizim ölçülerini (mm) çıkarır.

    Faz 5B / H4-1 ve H4-2. İki ayrı kusur burada kapanır:

    * Birim: ``_dims_mm`` girdiyi KOŞULSUZ metre kabul edip 1000 ile
      çarpıyordu. Ölçüldü (HEAD 9d3728e): ``/calculate_solid`` yanıtı
      doğrudan verilince ``Ø_chamber = 100000.0 mm`` (gerçek 100.0),
      ``Ø_throat = 47927.25 mm`` (gerçek 47.93); sıvıda kamara 99192.1 mm
      iken boğaz/çıkış doğruydu — tek çizimde iki farklı ölçek. Artık birim
      ``motor_geometry.normalise_export_geometry`` ile AÇIKÇA çözülür ve
      nozul konturu da aynı normalize sözlükten örneklenir (kontur
      örnekleyicisi de metre bekliyor: ölçüldü, ham katı girdide z aralığı
      0..174 848 mm çıkıyordu).
    * Grain: eski kod grain boyu/portu için SABİT YEDEK taşıyordu
      (0.24 m / 0.03 m / 0.05 m). Sıvı çift yakıtlı motorda grain YOKTUR;
      yedekler devreye girip imalat çizimine 240 mm boyunda, Ø30→50 mm
      portlu UYDURMA bir katı yakıt bloğu koyuyordu. Artık grain yalnız
      sonuçta gerçekten varsa çizilir.

    Döner: ``(normalize_motor_data, dims)``.
    """
    from hrma.export.motor_geometry import normalise_export_geometry

    md, report = normalise_export_geometry(motor_results)

    def mm(key):
        """Metre alanını mm'ye çevirir; kapı merkezden (OH-D27-11)."""
        f = finite_positive(md.get(key))
        return None if f is None else f * 1000.0

    grain = report['grain']
    dims = {
        'L': mm('chamber_length'),
        'D_ch': mm('chamber_diameter'),
        'd_t': mm('throat_diameter'),
        'd_e': mm('exit_diameter'),
        'eps': _num(md.get('expansion_ratio'), None),
        'grain': ({'L_g': grain['length'] * 1000.0,
                   'd_p0': grain['port_initial'] * 1000.0,
                   'd_pf': (grain['port_final'] * 1000.0
                            if grain['port_final'] is not None else None),
                   'source': grain['source']}
                  if grain is not None else None),
        'grain_reason': report['grain_reason'],
        'units': report['fields'],
    }
    return md, dims


def _dims_mm(motor_results):
    """Çizimlerde kullanılan ana boyutları (mm) tek yerden çıkarır.

    Çözülemeyen ölçü ``None`` döner — uydurma yedek ÜRETİLMEZ. Grain verisi
    yoksa ``dims['grain'] is None`` ve ``dims['grain_reason']`` nedeni söyler.
    """
    return _prepare(motor_results)[1]


def _mm_text(value, pattern='{:.1f}'):
    """Ölçüyü 'x.x mm' olarak yazar; çözülemediyse açık beyan basar."""
    if value is None:
        return NOT_RESOLVED
    return pattern.format(value) + ' mm'


def _wrap(text, width):
    """Uzun metni sabit genişlikte satırlara böler (sayfadan taşma olmasın)."""
    words = str(text).split()
    if not words:
        return ['']
    lines, cur = [], words[0]
    for w in words[1:]:
        if len(cur) + 1 + len(w) <= width:
            cur += ' ' + w
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def _unit_note(units):
    """Alan-başına birim çözümünü tek satırlık beyana çevirir."""
    labels = {
        'motor_geometry': 'normalised motor_geometry (SI)',
        'declared:m': 'declared m',
        'declared:mm': 'declared mm',
        'si': 'inferred m',
        'mm': 'inferred mm',
        'missing': 'not available',
    }
    seen = []
    for key in ('chamber_diameter', 'chamber_length', 'throat_diameter',
                'exit_diameter'):
        src = units.get(key)
        if src is None:
            continue
        text = labels.get(src, src)
        if text not in seen:
            seen.append(text)
    if not seen:
        return NOT_RESOLVED
    return ('all dimensions printed in mm; input resolved as '
            + ', '.join(seen))


def _require_drawable(dims):
    """Kamara çapı/boyu olmadan imalat çizimi üretilmez (fail-closed)."""
    missing = [name for name, key in (('chamber_diameter', 'D_ch'),
                                      ('chamber_length', 'L'))
               if dims[key] is None]
    if missing:
        raise DrawingGeometryError(
            'cannot draw a manufacturing view without ' + ' and '.join(missing)
            + '; the analysis result does not carry it (checked '
              'motor_geometry, the declared length_units and the top-level '
              'fields). Run the analysis again instead of receiving a drawing '
              'built from generator defaults.')


class DrawingRendererUnavailable(RuntimeError):
    """Teknik çizim sayfası ÇİZİLEMEDİ: grafik çizici yok / zaman aşımı.

    ÖH D16 / P16B4-16. ÖLÇÜLDÜ (taban 6fde52b, aynı İYİ gövde, aynı uç):

        kaleido sağlam  -> HTTP 200, 129.300 B, 3 sayfa, kesit ÇİZİLİ
        kaleido bozuk   -> HTTP 200,   5.122 B, 3 sayfa, kesit YOK  (25x)

    Bozuk koşumda belge içine ``Cross-section render failed: ...`` notu
    DÜŞÜYOR (bu iyi ve korunur) — ama dosya yine "teknik çizim PDF'i" adıyla,
    HTTP 200 ile, başarılı bir indirme olarak iniyordu. Beyan kusuru
    gidermez: çizimi olmayan bir çizim paketi YAYIMLANMAZ. Süreç bir kez
    düştükten sonra ömrü boyunca bozuk kaldığı için kullanıcı "tekrar dene"
    ile de düzeltemiyordu; sessiz 5 KB yerine adı konmuş bir hata gerekir.
    """


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

    from hrma.export.cad_visualization import (
        _injector_spec, pintle_type_claimed)

    md = motor_results or {}
    # V301 bilinen C2: pintle'da yüz deseni EŞDEĞER orifis planı değildir
    # (çözücünün beyanı: "The pintle is NOT drilled this way"); yüz görünüşü
    # STEP/STL ile TEK çözümleyiciden (``pintle_cad_geometry``) çizilir.
    if pintle_type_claimed(md):
        return _render_or_raise(_pintle_face_figure(md, size), width=size,
                                height=size)
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
    # Orifisler eş merkezli halkalara dağıtılır (0.38R ve 0.7R).
    #
    # ÖH D24 / P9B2-21 — ÇİZİLEN DELİK SAYISI BAŞLIKTAKİ SAYIYA EŞİTTİR.
    # ÖLÇÜLDÜ (taban 88a29d3, ``once.json`` M5): ``n = 1`` için başlık
    # "INJECTOR FACE - 1 x d1.20 mm" yazarken yüzde **2** daire çiziliyordu
    # (n = 2, 3, 7, 20 doğruydu; kusur yalnız tek orifiste).
    # Kök: halka payı ``max(1, round(n * frac))`` idi; ikinci halkanın payı
    # ``round(1 x 0,33) = 0`` çıkınca ``max(1, 0)`` onu 1'e YÜKSELTİYOR,
    # koşul ``placed + 0 <= n`` de doğru olduğu için düzeltici dal hiç
    # çalışmıyordu. Tek orifisli bir enjektörün imalat çizimini okuyan kişi
    # iki delik deliyordu.
    #
    # Artık paylar ÖNCE hesaplanır, toplamı n'e eşitlenir ve payı sıfır olan
    # halka ÇİZİLMEZ. Sayı uydurulmaz: n ne ise o kadar daire iner.
    halkalar = ((0.7 * R, 0.67), (0.38 * R, 0.33))
    paylar = [int(round(n * frac)) for _, frac in halkalar]
    paylar[0] = max(0, min(n, paylar[0]))
    paylar[-1] = n - sum(paylar[:-1])
    for (ring_r, _frac), k in zip(halkalar, paylar):
        if k <= 0:
            continue
        for i in range(k):
            a = 2 * np.pi * i / k
            cx, cy = ring_r * np.cos(a), ring_r * np.sin(a)
            fig.add_shape(type='circle',
                          x0=cx - d_h / 2, x1=cx + d_h / 2,
                          y0=cy - d_h / 2, y1=cy + d_h / 2,
                          line=dict(color='#c0392b', width=1.5))
    if sum(paylar) != n:                    # sözleşme: çizim = başlık
        raise ValueError(
            'injector_face_orifice_count_mismatch: the face pattern would '
            'draw %d holes while the title states %d; no drawing is issued '
            'with a hole count the analysis did not produce.'
            % (sum(paylar), n))
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


def _pintle_face_figure(motor_results, size=700):
    """V301 bilinen C2 — pintle enjektörün yüz görünüşü (plotly figürü).

    Sayılar STEP/STL ile AYNI çözümleyiciden (``pintle_cad_geometry``):
    kamara deliği, yüz plakası yayımlanmışsa anülüs deliği, direk ve uç
    deliklerinin açısal yerleri (delikler direğin YAN yüzündedir; yüzden
    bakışta direk çevresinde radyal çentik olarak gösterilir). Kanonik
    geometri yoksa ``PintleCADError`` yükselir; sayfa adlı gerekçeyi basar,
    eşdeğer orifisli düz plaka ÇİZİLMEZ.
    """
    import plotly.graph_objects as go

    from hrma.export.cad_visualization import pintle_cad_geometry

    md = motor_results or {}
    geo = pintle_cad_geometry(md)
    R = _num(md.get('chamber_diameter'), None) * 1000.0 / 2.0
    theta = np.linspace(0, 2 * np.pi, 181)
    fig = go.Figure()

    def daire(r, renk, kalinlik, kesik=False):
        fig.add_trace(go.Scatter(
            x=r * np.cos(theta), y=r * np.sin(theta), mode='lines',
            line=dict(color=renk, width=kalinlik,
                      dash='dash' if kesik else 'solid')))

    daire(R, '#1a2733', 2)
    if geo['plate_t'] is not None:
        daire(geo['bore'] / 2.0, '#1a2733', 1.5)
    else:
        daire(geo['bore'] / 2.0, '#8a93a0', 1, kesik=True)
    daire(geo['d_post'] / 2.0, '#c0392b', 1.5)
    r_p = geo['d_post'] / 2.0
    for i in range(geo['n_holes']):
        a = 2 * np.pi * i / geo['n_holes']
        fig.add_shape(type='line', x0=r_p * np.cos(a), y0=r_p * np.sin(a),
                      x1=(r_p - geo['hole_depth']) * np.cos(a),
                      y1=(r_p - geo['hole_depth']) * np.sin(a),
                      line=dict(color='#c0392b', width=1.5))
    if geo['n_holes']:
        delik = (f"{geo['n_holes']} x d{geo['d_hole']:.2f} mm radial tip "
                 f"holes at L_s {geo['skip']:.2f} mm")
    else:
        delik = 'no tip holes'
    plaka = (f"annulus bore d{geo['bore']:.2f} mm"
             if geo['plate_t'] is not None else
             f"annulus bore d{geo['bore']:.2f} mm (dashed: faceplate not "
             'modelled)')
    fig.update_layout(
        title=dict(text=(
            f"INJECTOR FACE - pintle: post d{geo['d_post']:.2f} mm<br>"
            f"{plaka}<br>{delik}<br>the equivalent orifice plan is NOT "
            'drilled'), font=dict(size=13)),
        margin=dict(t=130),
        paper_bgcolor='white', plot_bgcolor='white',
        font=dict(color='#1a2733'),
        xaxis=dict(title='mm', scaleanchor='y', scaleratio=1,
                   range=[-R * 1.15, R * 1.15]),
        yaxis=dict(title='mm', range=[-R * 1.15, R * 1.15]),
        showlegend=False, width=size, height=size,
    )
    return fig


def _pintle_schedule_value(motor_results, spec):
    """V301 bilinen C2 — ölçü tablosunun pintle satırı (çizimle aynı
    çözümleyiciden). Eşdeğer orifis planı adıyla 'delinmez' diye yazılır;
    kanonik geometri çizilemiyorsa adlı gerekçe basılır."""
    from hrma.export.cad_visualization import (
        NOT_AVAILABLE_SPEC, PintleCADError, pintle_cad_geometry)
    try:
        geo = pintle_cad_geometry(motor_results)
    except PintleCADError as exc:
        return f'{NOT_AVAILABLE_SPEC} - {exc.invalid_fields[0]["reason"]}'
    parca = [f"post d{geo['d_post']:.2f} mm",
             f"annulus bore d{geo['bore']:.2f} mm"]
    if geo['n_holes']:
        parca.append(f"{geo['n_holes']} x d{geo['d_hole']:.2f} mm tip holes "
                     f"at L_s {geo['skip']:.2f} mm")
    else:
        parca.append('no tip holes')
    if spec.get('n_orifices') and spec.get('orifice_diameter_mm'):
        parca.append(f"equivalent plan {spec['n_orifices']} x "
                     f"d{spec['orifice_diameter_mm']:.2f} mm NOT drilled")
    return '; '.join(parca)


#: Ölçü tablosunda bir değer sütununun sığdığı karakter sayısı (Helvetica 10,
#: 140 mm sütun başlangıcı). Satır kırma ve sayfa hesabı AYNI sayıyı kullanır.
SCHEDULE_WRAP_COLUMNS = 62
#: Tablo satırlarının dikey yerleşimi [mm]: ilk satır, sarılmış devam satırı,
#: tablo başlığının üst kenarı ve antet şeridinin üstünde bırakılan alt sınır.
SCHEDULE_ROW_MM = 8.0
SCHEDULE_WRAP_MM = 6.0
SCHEDULE_TOP_MM = 45.0
SCHEDULE_BOTTOM_MM = 30.0


def _schedule_rows(motor_results, d):
    """Ölçü ve malzeme tablosunun (etiket, değer) satırları.

    ``generate_drawing_pdf``ten AYRILDI (ÖH Z2): sayfa sayısı satırlardan
    çıkarılıyor ve antetteki "SHEET x/y" ilk yaprakta doğru yazılabilsin diye
    satırların çizimden ÖNCE kurulması gerekiyor.
    """
    # Cidar kalınlığı, malzeme ve enjektör satırları ÇÖZÜCÜ sonucundan gelir
    # (eski tablo sabit malzeme adları yazıyordu ve enjektör hiç yoktu).
    from hrma.export.cad_visualization import (
        NOT_AVAILABLE_SPEC, _chamber_material, _chamber_wall_design,
        _injector_spec, _nozzle_exit_angle_deg, _nozzle_family,
        _nozzle_half_angles, _wall_sf_basis_text, pintle_type_claimed)

    wall_design = _chamber_wall_design(motor_results)
    wall_m, wall_src = wall_design['thickness_m'], wall_design['source']
    _mat_key, mat_name, _rho = _chamber_material(motor_results)
    spec = _injector_spec(motor_results)
    conv_deg, div_deg, noz_type = _nozzle_half_angles(motor_results)
    exit_deg = _nozzle_exit_angle_deg(motor_results)

    # Grain satırları YALNIZ gerçekten grain'i olan motorda basılır. Sıvı
    # motorda eskiden sabit yedeklerden gelen "Grain length 240.0 mm /
    # Port diameter 30.0→50.0 mm" satırları gerçek ölçülerle aynı tabloda,
    # dayanak beyanı olmadan duruyordu (Faz 5B / H4-1).
    grain = d['grain']
    # ÖH Z5S / P9B2-22: eksenel konum bir ÜRETEÇ kuralıdır; sayı yıllardır
    # basılıyordu ama nereden geldiği hiçbir çıktıda yazmıyordu. Satır
    # tablonun SONUNA eklenir (aşağıdaki ``tail_rows``): araya girseydi
    # kendisinden sonraki satırların yaprak dağılımı kayardı ve kardeş
    # bekçiler (ör. enjektör satırını 3. yaprakta arayan
    # test_export_real_data) sessizce başka yaprağa bakardı.
    tail_rows = []
    # ÖH D15 / P9B2-09: çıkış açısı satırı da TABLONUN SONUNA eklenir. Araya
    # girdiğinde ölçüldü (31 Ağustos 2026): kendisinden sonraki satırların
    # yaprak dağılımı kaydı ve enjektör satırını 3. yaprakta arayan kardeş
    # bekçi (``test_export_real_data::test_drawing_pdf_uses_solver_injector``)
    # sessizce başka yaprağa baktı — Z5S'in aynı dosyadaki uyarısının birebir
    # tekrarı.
    tail_rows.append(
        ('Nozzle exit half angle',
         (f"{exit_deg:.1f} deg - this is the angle that sets the divergence "
          f"loss ((1+cos {exit_deg:.1f})/2); machine the contour to it. The "
          f"divergence half angle above is the {_nozzle_div_angle_meaning(noz_type)}")
         if exit_deg is not None
         else ('same as the divergence half angle - '
               + _nozzle_div_angle_meaning(noz_type)
               if _nozzle_family(noz_type) != 'bell'
               else NOT_AVAILABLE_SPEC)))
    if grain is not None:
        grain_rows = [
            ('Grain length', _mm_text(grain['L_g'])),
            ('Port diameter (initial)', _mm_text(grain['d_p0'])),
            ('Port diameter (final)', _mm_text(grain['d_pf'])),
        ]
        # ÖH V3 CAD A1 · H3 / A2 · H7: yerleşim STEP/STL/DXF ile TEK
        # fonksiyondan (çözücü konumu ya da beyanlı üreteç kuralı).
        if d['L']:
            _yigin, yer = _grain_layout(motor_results, d['L'], grain['L_g'])
            tail_rows.append(('Grain axial position', yer['note']))
    else:
        grain_rows = [('Solid grain', d['grain_reason'] or NOT_AVAILABLE_SPEC)]

    # ÖH Z2 (defter P9B2-07): cidar satırının yanında ÖNERİ ve emniyet
    # katsayısının DURUMU da yazar. Ölçüldü: yapısal analiz 23,18 mm
    # önerirken çizim 5,00 mm gösteriyor, "önerilen" sözcüğü çıktının
    # hiçbir yerinde geçmiyordu — imalatçı farkı göremiyordu.
    wall_rows = [
        ('Chamber wall thickness',
         f"{wall_m * 1000:.2f} mm  [{wall_src}]" if wall_m else NOT_AVAILABLE_SPEC),
    ]
    if wall_design['recommended_mm'] is not None:
        wall_rows.append(
            ('Structural sizing recommends',
             f"{wall_design['recommended_mm']:.2f} mm"))
    sf = wall_design['safety_factor']
    measured = wall_design['safety_factor_is_measured']
    if measured is not None and sf is not None:
        wall_rows.append(
            ('Safety factor at the drawn wall',
             f"{sf:.2f}"
             + ('' if sf >= 1.0 else '  ** BELOW 1.0 - THE DRAWN WALL FAILS **')
             + ('' if measured else '  (NOT a verification)')))
    else:
        wall_rows.append(('Safety factor at the drawn wall',
                          'NOT PUBLISHED BY THIS ANALYSIS'))
    if measured is not True:
        wall_rows.append(
            ('Safety factor basis',
             wall_design['safety_factor_basis']
             or _wall_sf_basis_text(wall_design)))
    if wall_design['note']:
        wall_rows.append(('Wall thickness note', wall_design['note']))

    return [
        ('Chamber inner diameter', _mm_text(d['D_ch'])),
        ('Chamber length', _mm_text(d['L'])),
    ] + wall_rows + grain_rows + [
        ('Throat diameter', _mm_text(d['d_t'], '{:.2f}')),
        ('Exit diameter', _mm_text(d['d_e'], '{:.2f}')),
        ('Expansion ratio',
         f"{d['eps']:.2f}" if d['eps'] is not None else NOT_AVAILABLE_SPEC),
        # ÖH Z5S / P9B2-10: açıların KAYNAK künyesi sayının YANINDA (kısa) ve
        # tablonun sonunda (tam beyan) yaşar; çözücünün "varsayılan" sözü
        # artık düşürülmüyor.
        # ÖH D15 / P9B2-09: çan lülede tek açı YETMEZ. Ölçüldü (bell_80,
        # 10 kN RP1/LOX): satır 'div 30.0 deg' diyordu — o BOĞAZ açısıdır;
        # yayımlanan Isp ise çıkıştaki 8,5 dereceye demirli
        # ((1+cos 8,5)/2 = 0,9945079 = divergence_efficiency). Künyeye bakıp
        # 30 derecelik düz koni üreten atölye -%6,18 itki alır. Çıkış açısı
        # artık ADIYLA basılır ve div'in ne anlama geldiği yazılır.
        ('Nozzle type / half angles',
         f"{noz_type}; conv "
         f"{('%.1f deg' % conv_deg) if conv_deg else 'n/a'}, div "
         f"{('%.1f deg' % div_deg) if div_deg else 'n/a'} "
         + _nozzle_angle_source_tag(motor_results)),
        (('Injector (pintle)', _pintle_schedule_value(motor_results, spec))
         if pintle_type_claimed(motor_results) else
         ('Injector orifices',
          (f"{spec['n_orifices']} x d{spec['orifice_diameter_mm']:.2f} mm "
           f"({spec['type'] or 'type n/a'})")
          if (spec['n_orifices'] and spec['orifice_diameter_mm'])
          else NOT_AVAILABLE_SPEC)),
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
        # Birim sözleşmesi çizimin ÜSTÜNDE beyan edilir: imalatçı ölçülerin
        # hangi girdi biriminden çevrildiğini görebilmeli (Faz 5B / H4-2).
        ('Input length units', _unit_note(d['units'])),
        # ÖH Z5S / P9B2-29 ve -28: BEYAN satırları TABLONUN SONUNA eklenir.
        # Yeri rastgele değil — araya girseler yukarıdaki satırların yaprak
        # dağılımı kayardı (``_paginate_rows`` sığdıkça doldurur).
        ('Nozzle angle source', _nozzle_angle_source(motor_results)),
        # ÖH V3 CAD A2: iki satır da artık GERÇEĞİ söyler. Lüle eti satırı
        # sabit "declared generator rule, not from a structural or thermal
        # analysis" diyordu; A1 · H2'den beri hibrit STEP lülesi çözücünün
        # yayımladığı eti çizer (DXF notuyla tek kaynak). Eksen satırı STL
        # paketinin hâlâ +Z'de olduğunu söylüyordu (D-A2-4).
        ('Nozzle wall thickness',
         'NOT DIMENSIONED IN THIS DRAWING - '
         + _nozzle_wall_note(motor_results)[len('NOZZLE WALL: '):]),
        ('Axis convention', AXIS_CONVENTION_ROW),
    ] + tail_rows


def _paginate_rows(rows, page_h, mm):
    """Satırları yapraklara böler; her yaprak (etiket, sarılmış_satırlar).

    ÖH Z2 ölçümü (27 Ağustos 2026): tablo TEK sayfaya basılıyordu ve son
    satır y = **-258 pt**'ye düşüyordu — antet şeridi 68 pt'de olduğuna göre
    sayfanın 46 cm altı. Yani "Pressure test requirement" ve "Input length
    units" gibi satırlar PDF'in içindeydi ama KÂĞITTA yoktu (metin çıkarıcı
    görüyor, okuyan göremiyor). Cidar künyesi satırları eklenince taşma
    büyüdüğü için yerleşim burada kapatıldı: sığmayan satır yeni yaprağa
    geçer, yaprak sayısı antette yazar.
    """
    wrapped = [(label, _wrap(val, SCHEDULE_WRAP_COLUMNS) or [''])
               for label, val in rows]
    top = page_h - SCHEDULE_TOP_MM * mm - 4.0 * mm
    bottom = SCHEDULE_BOTTOM_MM * mm
    pages, y = [[]], top
    for label, chunks in wrapped:
        height = (SCHEDULE_ROW_MM + SCHEDULE_WRAP_MM * (len(chunks) - 1)) * mm
        if pages[-1] and (y - height) < bottom:
            pages.append([])
            y = top
        pages[-1].append((label, chunks))
        y -= height
    return pages


def generate_drawing_pdf(motor_results, out_path=None):
    """Antetli, çok sayfalı teknik çizim PDF'i üretir; dosya yolu döner."""
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm as MM
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as rl_canvas

    # Birim TEK noktada çözülür; sayfa 1 kesiti ve enjektör deseni de aynı
    # normalize sözlükten üretilir (aksi hâlde tablo mm, kesit metre olurdu).
    motor_results, d = _prepare(motor_results)
    _require_drawable(d)
    if d['grain'] is not None:
        _grain_section_gate(motor_results, 'Technical drawing PDF')
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

    # Tablo satırları ÖNCE kurulur: sayfa sayısı buradan çıkar ve antetteki
    # "SHEET x/y" ilk sayfada doğru yazılabilsin (aşağıdaki _schedule_rows
    # sayfaya sığmayan satırları yeni yaprağa taşır).
    rows = _schedule_rows(motor_results, d)
    schedule_pages = _paginate_rows(rows, page_h, MM)
    # ÖH Z5S / P9B2-30: enjektör yaprağı YALNIZ sonuç bir enjektör iddia
    # ediyorsa basılır. Katı motorda enjektör yoktur; "render failed" yazan
    # boş bir yaprak, olmayan bir parçayı hata gibi göstermektir.
    has_injector_sheet = _motor_claims_injector(motor_results)
    total_sheets = 1 + (1 if has_injector_sheet else 0) + len(schedule_pages)

    # ---- Sayfa 1: Eksenel kesit ----
    title_block('MOTOR AXIAL CROSS-SECTION', 1, total_sheets)
    try:
        png = _cross_section_png(motor_results)
        img = ImageReader(io.BytesIO(png))
        c.drawImage(img, 15 * MM, 40 * MM, width=page_w - 30 * MM,
                    height=page_h - 70 * MM, preserveAspectRatio=True,
                    anchor='c')
    except Exception as exc:  # kaleido/figür hatası
        # ÖH D16 / P16B4-16 — FAIL-CLOSED. Not basılmaya devam eder (belge
        # yarım kalmasın diye değil, kanıt olsun diye), ama paket teslim
        # EDİLMEZ: çağıran aşağıdaki istisnayı görür ve uç adı konmuş bir
        # hata döner. Ayrıntı: DrawingRendererUnavailable docstring'i.
        c.setFont('Helvetica', 12)
        c.drawString(20 * MM, page_h / 2, f'Cross-section render failed: {exc}')
        c.showPage()
        c.save()
        try:
            os.remove(work_path)
        except OSError:
            pass
        raise DrawingRendererUnavailable(
            'the axial cross-section sheet could not be drawn '
            f'({exc}); a technical drawing package without its drawing is '
            'not written') from exc
    c.showPage()

    # ---- Sayfa 2: Enjektör yüzü (YALNIZ enjektörü olan motorda) ----
    if has_injector_sheet:
        title_block('INJECTOR FACE PATTERN', 2, total_sheets)
        try:
            png = _injector_face_png(motor_results)
            img = ImageReader(io.BytesIO(png))
            side = min(page_w - 60 * MM, page_h - 70 * MM)
            c.drawImage(img, (page_w - side) / 2, 38 * MM, width=side,
                        height=side, preserveAspectRatio=True, anchor='c')
        except Exception as exc:
            c.setFont('Helvetica', 12)
            c.drawString(20 * MM, page_h / 2,
                         f'Injector render failed: {exc}')
        c.showPage()

    # ---- Sayfa 3+: Boyut ve malzeme tablosu ----
    first_schedule_sheet = 2 + (1 if has_injector_sheet else 0)
    for sheet_index, page_rows in enumerate(schedule_pages):
        title_block('DIMENSION & MATERIAL SCHEDULE'
                    + ('' if len(schedule_pages) == 1
                       else f' ({sheet_index + 1}/{len(schedule_pages)})'),
                    first_schedule_sheet + sheet_index, total_sheets)
        y = page_h - 45 * MM
        c.setFont('Helvetica-Bold', 11)
        c.drawString(30 * MM, y, 'PARAMETER')
        c.drawString(140 * MM, y, 'VALUE / SPEC')
        y -= 4 * MM
        c.line(30 * MM, y, page_w - 30 * MM, y)
        c.setFont('Helvetica', 10)
        for label, chunks in page_rows:
            for i, chunk in enumerate(chunks):
                y -= 6 * MM if i else 8 * MM
                if i == 0:
                    c.drawString(30 * MM, y, label)
                c.drawString(140 * MM, y, chunk)
        c.showPage()

    c.save()
    os.replace(work_path, out_path)
    return out_path


# ---------------------------------------------------------------------------
# DXF imalat çizimi
# ---------------------------------------------------------------------------

#: ÖH D24 / OH-D23-06 — DXF'in İÇERİKTEN BAĞIMSIZ (kararsız) alanları.
#:
#: ÖLÇÜLDÜ (taban 88a29d3, ``once.json`` M2): ``/api/export-dxf`` aynı ağaçta,
#: aynı gövdeyle art arda üç kez çağrıldığında HER seferinde HTTP 200 ve
#: **45.491 bayt** dönüyor ama sha256 ÜÇÜ DE FARKLI çıkıyordu. Bu yüzden
#: hüküm çapalarında DXF ucu her koşuda "değişti" işaretleniyor, gerçek bir
#: gerileme ile kütüphane damgası ayırt edilemiyordu.
#:
#: Kararsızlığın kaynağı ölçülerek altı yere indirildi (ezdxf 1.4.4):
#:   $TDCREATE / $TDUPDATE   -> Julian gün, çağrı ANI
#:   $FINGERPRINTGUID        -> her belgede yeni rastgele GUID
#:   $VERSIONGUID            -> her YAZIMDA yeni rastgele GUID
#:   CREATED_BY_EZDXF        -> "<sürüm> @ <ISO zaman>" (belge kurulurken)
#:   WRITTEN_BY_EZDXF        -> "<sürüm> @ <ISO zaman>" (yazım anında)
#:
#: Hiçbiri ÇİZİM değildir; altısı da imalatçıya giden geometriyi etkilemez.
#: Ürün dosyasındaki gerçek zaman damgası KORUNUR (uydurma tarih yazılmaz —
#: sabit bir sahte tarih basmak, dosyayı açan kişiye yalan söylemek olurdu);
#: kıyaslayan taraf ``canonicalize_dxf_text`` ile bu altı alanı maskeler ve
#: geriye yalnız çizimin kendisi kalır.
DXF_UNSTABLE_HEADER_VARS = ('$TDCREATE', '$TDUPDATE', '$TDUCREATE',
                            '$TDUUPDATE', '$FINGERPRINTGUID', '$VERSIONGUID')
#: Maskelenen alanın yerine yazılan sabit. Bir değer DEĞİL, "burada içerikten
#: bağımsız bir damga vardı" beyanıdır.
DXF_CANONICAL_PLACEHOLDER = '<HRMA-CANONICALIZED>'


def canonicalize_dxf_text(text):
    """DXF metnini KIYASLANABİLİR hâle getirir (ÖH D24 / OH-D23-06).

    Yalnız ``DXF_UNSTABLE_HEADER_VARS`` başlık değişkenlerinin değer satırı ve
    ezdxf'in ``<sürüm> @ <ISO zaman>`` künye dizeleri sabit bir yer tutucuyla
    değiştirilir. Geometri, katman, metin ve ölçü satırlarına DOKUNULMAZ:
    çizimde gerçek bir değişiklik olursa kanonik metin de değişir, yani bu
    kanonikleştirme bir gerilemeyi GİZLEMEZ.

    Girdi ``str`` ya da ``bytes`` olabilir; dönüş girdiyle aynı türdedir.
    """
    ham_bytes = isinstance(text, (bytes, bytearray))
    s = text.decode('utf-8', 'replace') if ham_bytes else text

    satirlar = s.split('\n')
    # DXF etiket akışı satır çiftidir: grup kodu satırı, sonra değer satırı.
    # Başlık değişkeninin adı bir değer satırıdır; onu izleyen grup kodu (9
    # değil, ör. 40/5) ve ardından gelen satır o değişkenin DEĞERİdir.
    for i, satir in enumerate(satirlar):
        if satir.strip() in DXF_UNSTABLE_HEADER_VARS and i + 2 < len(satirlar):
            satirlar[i + 2] = DXF_CANONICAL_PLACEHOLDER
    s = '\n'.join(satirlar)

    # ezdxf künyesi: "1.4.4 @ 2026-09-05T07:41:20.709149+00:00"
    s = re.sub(r'^\d+\.\d+(?:\.\d+)?[a-z0-9]* @ \d{4}-\d{2}-\d{2}T[^\n]*$',
               DXF_CANONICAL_PLACEHOLDER, s, flags=re.M)
    return s.encode('utf-8') if ham_bytes else s


def register_dxf_classes_in_fixed_order(doc):
    """DXF ``CLASSES`` bölümünü yazımdan ÖNCE sabit sırayla kurar.

    ÖH V3 CAD · CADI D-T6-2. ÖLÇÜLDÜ (14 Eki, ezdxf 1.4.4, aynı belge,
    ``PYTHONHASHSEED`` 0-7): ``CLASSES`` bölümünde ``LAYOUT`` ve
    ``ACDBPLACEHOLDER`` sınıflarının yazım sırası süreçten sürece
    değişiyordu (8 tohumun 2'sinde ``LAYOUT`` önde). Kök: ezdxf
    ``ClassesSection.add_required_classes`` kullanılan varlık tiplerini bir
    KÜMEDEN (``EntityDB.dxf_types_in_use() -> set``) gezerek ekler; dize
    özetleri süreç başına rastgele tohumlandığı için sıra da rastgeledir.
    (CADI'nin F1 notu bu farkı 'OBJECTS' bölümünde sanmıştı; satır 1325/1341
    ``CLASSES`` bölümüdür, OBJECTS'teki nesne sırası tohumdan bağımsızdır.)
    İçerik aynıydı, bayt değil: aynı girdi iki indirmede farklı sha256
    veriyordu.

    Çözüm ezdxf'in kendi kuralını SABİT sırayla önceden uygular: önce sürüm
    için zorunlu sınıflar (ezdxf'in liste sırası), sonra kullanılan varlık
    tipleri ADA GÖRE sıralı. ``saveas`` aynı kuralı yeniden uygular, ama
    kayıtlı sınıfı tekrar eklemez; geriye eklenecek bir şey kalmaz. Sınıf
    kümesi değişmez (yalnız sıra sabitlenir); ezdxf'in zorunlu liste adları
    bulunamazsa (sürüm değişikliği) yalnız sıralı adım uygulanır — sıra yine
    belirlenimcidir.
    """
    doc.commit_pending_changes()
    try:
        from ezdxf.sections.classes import REQUIRED_CLASSES, REQ_R2004
        zorunlu = REQUIRED_CLASSES.get(doc.dxfversion, REQ_R2004)
    except ImportError:
        zorunlu = ()
    for ad in zorunlu:
        doc.classes.add_class(ad)
    for ad in sorted(doc.entitydb.dxf_types_in_use()):
        doc.classes.add_class(ad)


def save_dxf_deterministic(doc, path):
    """``doc.saveas(path)``; sınıf tablosu önce sabit sırayla kurulur."""
    register_dxf_classes_in_fixed_order(doc)
    doc.saveas(path)


def generate_dxf(motor_results, out_path=None):
    """2D imalat çizimi (DXF R2010): iç akış yolu + kamara + grain profili.

    Birim: MİLİMETRE — dosyaya ``$INSUNITS = 4`` olarak da yazılır (A2).
    Eşzamanlılık: ``out_path`` verilmezse her çağrı kendi geçici dizinini alır
    ve dosya atomik yazılır (D1).
    """
    import ezdxf

    # Birim TEK noktada çözülür ve kontur örnekleyicisine de NORMALİZE sözlük
    # verilir; aksi hâlde ham katı/sıvı yanıtında kontur 1000× büyük çıkıyordu
    # (ölçüldü: ham katı girdide z aralığı 0..174 848 mm, normalize edilmişte
    # 0..174.7 mm).
    motor_results, d = _prepare(motor_results)
    _require_drawable(d)
    if d['grain'] is not None:
        _grain_section_gate(motor_results, 'DXF manufacturing drawing')
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
    # ÖH V3 CAD A2 · U5: ilişkisel ölçü varlıkları (DIMENSION) ayrı katmanda.
    doc.layers.add(DXF_DIMENSION_LAYER, color=2)
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
    from hrma.export.cad_visualization import (
        _chamber_wall_design, _wall_sf_basis_text)
    wall_design = _chamber_wall_design(motor_results)
    wall_m, wall_src = wall_design['thickness_m'], wall_design['source']
    wall = (wall_m * 1000.0) if wall_m is not None else None
    if wall is not None:
        for s in (1, -1):
            msp.add_lwpolyline(
                [(0, s * (rc + wall)), (L, s * (rc + wall))],
                dxfattribs={'layer': 'OUTLINE'})
        msp.add_lwpolyline([(0, -(rc + wall)), (0, rc + wall)],
                           dxfattribs={'layer': 'OUTLINE'})

    # ÖH V3 CAD A2 · U5 — ÖN KAPAK BEYANI. ÖLÇÜLDÜ (7 Eki CAD kontrolü,
    # ezdxf): x = 0'da tek dikey çizgi var, kapak kalınlığı bu görünüşte
    # çizilmiyor ve hiçbir yerde yazmıyordu; STEP aynı kapağı x < 0'da katı
    # olarak çiziyor. Kapağı ÇİZMEK mevcut bir bekçiyi kırar
    # (``tests/test_faz5_cizim_birim.py::TestUcDosyaAyniMotor::
    # test_dxf_axial_span_matches_the_step_solid`` DXF ⟷ STEP farkının
    # TAM kapak kadar olmasını, yani kapağın çizilmemesini sabitliyor) —
    # bu yüzden kalınlık STEP/STL ile TEK çözümleyiciden (``_front_cap_design``)
    # okunup ADIYLA yazılır, çizimi ana model kararına devredildi.
    cap = None
    cap_line = ('CLOSURE HEAD: not available - the chamber wall is not '
                'available from the analysis, so the head that closes it is '
                'not modelled')
    if wall is not None:
        from hrma.export.cad_visualization import _front_cap_design
        cap_design = _front_cap_design(motor_results, wall_mm=wall,
                                       bore_radius_mm=rc)
        cap = cap_design['thickness_mm']
        cap_line = (
            (f"CLOSURE HEAD = {cap:.2f} mm, drawn at x < 0 in the STEP and "
             'STL solids and NOT drawn in this view (the outline starts at '
             f"the head inner face x = 0) [{cap_design['source']}]")
            if cap else
            'CLOSURE HEAD: NOT RESOLVED - '
            + str(cap_design.get('source') or NOT_RESOLVED))

    # Grain profili — YALNIZ sonuçta gerçekten grain varsa çizilir.
    # H4-1: burada sabit yedekler vardı (0.24 m boy, Ø0.03→0.05 m port) ve
    # sıvı motorda devreye girip imalat çizimine olmayan bir katı yakıt
    # bloğu koyuyordu. Grain yoksa hiçbir şey çizilmez; not yazıyla düşülür.
    grain = d['grain']
    grain_position_note = None
    grain_clearance_note = None
    if grain is not None:
        # ÖH V3 CAD A1 · H3 / A2 · H7 — yığın planı ve ön yüz STEP/STL ile
        # TEK kaynaktan (``_grain_layout``). ÖLÇÜLDÜ (7 Eki CAD kontrolü,
        # örnek katı BATES): bu çizim taneyi TEK dikdörtgen olarak 36,4 mm'den
        # çiziyordu; aynı isteğin STEP'i 3 x 120 mm segmenti 2 mm aralıkla
        # 35,0 mm'den çiziyordu (A1 devri D-A2-3 / D-A2-5).
        yigin, yer = _grain_layout(motor_results, L, grain['L_g'])
        zg0 = yer['front_mm']
        seg, gap, n_seg = yigin['segment_mm'], yigin['gap_mm'], yigin['n']
        from hrma.export.cad_visualization import (
            _grain_outer_radius_m, grain_radial_clearance_note)
        r_go_m, _r_go_src = _grain_outer_radius_m(motor_results)
        r_go = (r_go_m * 1000.0) if r_go_m is not None else None
        for i_seg in range(n_seg):
            z_a = zg0 + i_seg * (seg + gap)
            z_b = z_a + seg
            for s in (1, -1):
                msp.add_lwpolyline(
                    [(z_a, s * grain['d_p0'] / 2), (z_b, s * grain['d_p0'] / 2)],
                    dxfattribs={'layer': 'OUTLINE'})
                if r_go is not None:
                    # Segmentin iki uç yüzü (port -> tane dış çapı). Uç yüz
                    # bir YANMA yüzeyidir; BATES'in nötr eğrisi bu altı
                    # cepheden gelir — çizimde de görünür.
                    for z_u in (z_a, z_b):
                        msp.add_line((z_u, s * grain['d_p0'] / 2),
                                     (z_u, s * r_go),
                                     dxfattribs={'layer': 'OUTLINE'})
        zg1 = zg0 + yigin['stack_mm']
        port_text = (f"grain {grain['L_g']:.1f} mm"
                     + (f" ({n_seg} segments x {seg:.1f} mm"
                        + (f", gap {gap:.1f} mm" if gap > 0.0 else ', flush')
                        + ')' if n_seg > 1 else '')
                     + f", port Ø{grain['d_p0']:.1f}"
                     + (f"→{grain['d_pf']:.1f} mm" if grain['d_pf'] is not None
                        else ' mm (final port not reported)'))
        grain_label = ((zg0 + zg1) / 2, port_text)
        grain_position_note = 'GRAIN AXIAL POSITION: ' + yer['note']
        if r_go is not None:
            # ÖH V3 CAD A2 · H6 — astar/yalıtım çizilmez; pay beyan edilir.
            grain_clearance_note = (
                'GRAIN RADIAL CLEARANCE: '
                + grain_radial_clearance_note(motor_results, rc, r_go))
    else:
        grain_label = (0.0, 'SOLID GRAIN: ' + (d['grain_reason'] or NOT_RESOLVED))

    # Eksen çizgisi
    z_end = noz[-1][0] if noz else L
    msp.add_line((-15, 0), (z_end + 15, 0),
                 dxfattribs={'layer': 'CENTERLINE', 'linetype': 'CENTER'})

    # Ölçü metinleri (basit, imalatçıya yeterli açıklıkta)
    y_wall = rc + (wall if wall is not None else 0.0)
    # ÖH Z2 (defter P9B2-07, kritik): cidar etiketi tek satırdı ve o satır
    # katı/sıvı motorda koşulsuz "verified against the pressure load"
    # diyordu. Ölçüldü (27 Ağustos 2026): SF 0,8463 olan (yani 1'in altında
    # kalan!) bir kabin DXF'i bu damgayı taşıyor, yapısal analizin
    # "önerilen 23,18 mm" notu ise hiçbir çıktıya basılmıyordu. Etiket artık
    # üç satır: ÇİZİLEN kalınlık + künye, yapısal ÖNERİ, ve emniyet
    # katsayısının durumu (ölçülmüşse sayı; değilse NEDEN olmadığı).
    if wall is None:
        wall_lines = ['WALL THICKNESS: NOT AVAILABLE FROM THE ANALYSIS - '
                      'outer profile not drawn']
    else:
        wall_lines = [f"WALL THICKNESS = {wall:.2f} mm [{wall_src}]"]
        if wall_design['recommended_mm'] is not None:
            delta = ('' if abs(wall - wall_design['recommended_mm']) <= 1e-6
                     else '  ** DRAWN WALL IS NOT THE RECOMMENDED ONE **')
            wall_lines.append(
                'STRUCTURAL SIZING RECOMMENDS = '
                f"{wall_design['recommended_mm']:.2f} mm{delta}")
        sf = wall_design['safety_factor']
        measured = wall_design['safety_factor_is_measured']
        if measured is not None and sf is not None:
            # Sayı her iki hâlde de basılır (1'in altındaki bir katsayıyı
            # gizlemek en tehlikeli yöndür); DOĞRULAMA iddiası ise yalnız
            # gerçekten kazanıldıysa yapılır.
            wall_lines.append(
                f"SAFETY FACTOR AT THE DRAWN WALL = {sf:.4f}"
                + ('' if sf >= 1.0 else
                   '  ** BELOW 1.0 - THE DRAWN WALL FAILS AT THIS PRESSURE **')
                + ('' if measured else '  (NOT A VERIFICATION)'))
            if measured is False:
                wall_lines.append(
                    'SAFETY FACTOR BASIS: '
                    + (wall_design['safety_factor_basis']
                       or _wall_sf_basis_text(wall_design)))
        else:
            wall_lines.append(
                'SAFETY FACTOR AT THE DRAWN WALL: NOT PUBLISHED BY THIS '
                'ANALYSIS')
            wall_lines.append(
                'SAFETY FACTOR BASIS: '
                + (wall_design['safety_factor_basis']
                   or _wall_sf_basis_text(wall_design)))

    # ÖH Z5S: çizimin BEYAN ETMEDİĞİ üreteç kararları artık dosyada yazar.
    # Sıra önemli: hiçbiri "WALL THICKNESS" ile BAŞLAMAZ — kardeş bekçi
    # (test_faz4_export_geometri) o önekten kamara cidarını okuyor ve araya
    # giren bir satır ölçüyü kaçırtırdı.
    tail_lines = [
        f"NOZZLE DIVERGENT LENGTH: {meta['divergent_length_source']}",
        # P9B2-10: açıların kaynağı çözücünün kendi beyanından.
        'NOZZLE HALF ANGLES: ' + _nozzle_angle_source(motor_results),
        # P9B2-29: "WALL THICKNESS" ölçüsü YALNIZ kamaraya ait. ÖH V3 CAD
        # A1 · H2: STEP'in lüle eti kaynağı artık gerçeği söyler.
        _nozzle_wall_note(motor_results),
        # P9B2-28: eksen sözleşmesi.
        AXIS_CONVENTION_NOTE,
        'ALL DIMENSIONS IN MILLIMETRES ($INSUNITS=4)',
        # H4-2: geometrinin hangi girdi biriminden çevrildiği dosyada yazar.
        'INPUT UNITS: ' + _unit_note(d['units']),
    ]
    if grain_position_note is not None:
        # P9B2-22: grain'in eksenel konumu bir üreteç kuralı — beyan edilir.
        tail_lines.insert(1, grain_position_note)
    if grain_clearance_note is not None:
        tail_lines.insert(2, grain_clearance_note)
    tail_lines.insert(0, cap_line)

    labels = [
        (L / 2, y_wall + 12, f"L_chamber = {L:.1f} mm"),
        (L + meta['z_throat'],
         (d['d_t'] / 2 if d['d_t'] is not None else rc) + 14,
         'Ø_throat = ' + _mm_text(d['d_t'], '{:.2f}')),
        (z_end, (d['d_e'] / 2 if d['d_e'] is not None else rc) + 14,
         'Ø_exit = ' + _mm_text(d['d_e'], '{:.2f}')),
        (-10, rc + 8, f"Ø_chamber = {d['D_ch']:.1f} mm"),
        (grain_label[0], -(y_wall + 16), grain_label[1]),
    ] + [
        (0.0, -(y_wall + 30 + 10 * i), text)
        for i, text in enumerate(wall_lines)
    ] + [
        (0.0, -(y_wall + 30 + 10 * (len(wall_lines) + i)), text)
        for i, text in enumerate(tail_lines)
    ]
    for x, y, text in labels:
        msp.add_text(text, dxfattribs={'layer': 'TEXT', 'height': 5.0}
                     ).set_placement((x, y))

    # ÖH V3 CAD A2 · U5 — ilişkisel ölçüler. ÖLÇÜLDÜ (7 Eki CAD kontrolü):
    # bu çizimdeki bütün ölçüler serbest TEXT'ti; CAD'de ölçü varlığı yoktu.
    # TEXT satırları AYNEN kalır (okuyan bekçiler ve kullanıcılar var);
    # yanlarına geometriye bağlı DIMENSION varlıkları eklenir.
    def _olcu(p1, p2, base, angle=0.0):
        msp.add_linear_dim(base=base, p1=p1, p2=p2, angle=angle,
                           dimstyle='EZDXF',
                           dxfattribs={'layer': DXF_DIMENSION_LAYER}).render()

    y_ust = rc + (wall if wall is not None else 0.0)
    _olcu((0.0, rc), (L, rc), (0.0, y_ust + 25.0))                 # L_chamber
    _olcu((L * 0.25, -rc), (L * 0.25, rc), (-25.0, 0.0),
          angle=90.0)                                              # Ø bore
    if wall is not None:
        _olcu((L * 0.5, rc), (L * 0.5, rc + wall),
              (L * 0.5 + 15.0, rc), angle=90.0)                    # cidar

    # Yazma ATOMİK (D1): yarım DXF HTTP 200 ile indirilmesin. Sınıf
    # tablosu yazımdan önce SABİT sırayla kurulur (CADI D-T6-2).
    atomic_produce(out_path,
                   lambda yol: save_dxf_deterministic(doc, yol))
    return out_path
