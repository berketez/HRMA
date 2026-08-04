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

import numpy as np

from hrma.engines.nozzle_design import sample_nozzle_inner_contour
from hrma.export.export_workspace import (
    atomic_produce, new_workspace, purge_stale_workspaces)
from hrma.utils.input_guard import safe_name

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


def _export_step_atomic(shape, path):
    """STEP dosyasını ATOMİK yazar (yarım dosya okunamasın — D1)."""
    return atomic_produce(path, lambda tmp: export_step(shape, tmp))


def generate_step_assembly(motor_results, out_dir=None, motor_type='hybrid'):
    """Motor bileşenlerini STEP olarak üretir; dosya yolu SÖZLÜĞÜ döner.

    motor_type: 'hybrid' (grain+enjektör), 'solid' (grain var, enjektör yok),
    'liquid' (enjektör var, grain yok).

    SÖZLEŞME (D1, v2.6.26): ``out_dir`` verilmezse her çağrı KENDİ benzersiz
    geçici dizinini alır (``mkdtemp``). Eski davranış saniye çözünürlüklü bir
    zaman damgasıydı ve ``exist_ok=True`` ile aynı saniyedeki iki istek aynı
    dizine yazıyordu. Dönen sözlüğün değerleri MUTLAK yollardır; çağıran
    dosyaları okuduktan sonra dizini silmelidir
    (``export_workspace.cleanup_workspace``).

    A8 (fail-closed): kamara/kasa cidar kalınlığı yapısal analizden
    okunamazsa ``ValueError`` yükseltilir. Eskiden ``0.045·D_ch`` yedeğine
    düşülüyordu; ölçüldü (Ø100 mm katı motor): analiz 2.40 mm, STEP 4.50 mm —
    imalata analizde hiç doğrulanmamış bir cidar gidiyordu.

    v2.6.27 (dürüstlük kapısı, enjektör): sonuç bir enjektör bloğu taşıyor
    ama orifis sayısı/çapı çözülemiyorsa ``ValueError`` yükseltilir (eski
    davranış: 12 × Ø1,5 mm uydurma plaka — ham sıvı sonucunda motorun
    hesapladığı ``number_of_elements`` bile okunmuyordu). Sonuç enjektörden
    hiç söz etmiyorsa parça grain ilkesindeki gibi (H4-1) çizilmez. Orifis
    halka yarıçapı hiçbir çözücüde modellenmediği için desen verisi yoksa
    katı, parça adına gömülü açık ``ASSUMED`` beyanıyla çizilir (bkz.
    gövdedeki kapı notu).

    Faz 5B / H4-1 ve H4-2 (ölçüldü, HEAD 9d3728e):

    * Birim: girdi KOŞULSUZ metre kabul ediliyordu. ``/calculate_solid``
      yanıtı doğrudan verilince STEP montaj zarfı 174 992 × 98 156 mm
      çıkıyordu (gerçek 782.68 × 98.16 mm). Artık birim
      ``motor_geometry.normalise_export_geometry`` ile açıkça çözülür.
    * Grain: ``motor_type`` varsayılanı 'hybrid' olduğu ve rota katmanı bu
      argümanı hiç geçmediği için SIVI motorda da ``fuel_grain.step``
      üretiliyordu (ölçüldü: 85.22 mm boyunda, Ø30 mm portlu uydurma bir
      blok). Grain artık yalnız sonuçta gerçekten varsa üretilir.
    """
    _require()
    from hrma.export.motor_geometry import (
        _first_positive, normalise_export_geometry, resolve_grain_m)

    md, _report = normalise_export_geometry(motor_results)
    grain_geo, _grain_reason = resolve_grain_m(md)
    # Grain iki koşulun İKİSİNİ birden ister: motor tipi grain taşıyor olmalı
    # VE çözümde gerçek grain geometrisi bulunmalı. Yedek ölçü YOK.
    has_grain = motor_type in ('hybrid', 'solid') and grain_geo is not None
    has_injector = motor_type in ('hybrid', 'liquid')

    # Ad dosya yoluna giriyor: mutlak yol / '..' geçmesin (K-1).
    name = safe_name(md.get('motor_name'))
    if out_dir is None:
        # Çökme sonrası kalanları topla (D10), sonra kendi dizinini aç.
        purge_stale_workspaces()
        out_dir = new_workspace('hrma_step_')
    else:
        os.makedirs(out_dir, exist_ok=True)
    out_dir = os.path.abspath(out_dir)

    # ---- boyutlar (mm) — girdi yukarıda METRE'ye indirgendi ----
    L_m = md.get('chamber_length')
    D_m = md.get('chamber_diameter')
    if not (isinstance(L_m, (int, float)) and np.isfinite(L_m) and L_m > 0
            and isinstance(D_m, (int, float)) and np.isfinite(D_m) and D_m > 0):
        raise ValueError(
            'chamber_length / chamber_diameter could not be resolved from the '
            'analysis result (checked motor_geometry, the declared '
            'length_units and the top-level fields); refusing to emit a '
            'manufacturing STEP built from generator defaults.')
    L = float(L_m) * 1000.0
    D_ch = float(D_m) * 1000.0
    rc = D_ch / 2
    if has_grain:
        L_g = min(grain_geo['length'] * 1000.0, 0.92 * L)
        r_p0 = grain_geo['port_initial'] * 1000.0 / 2
    # Cidar TEK çözümleyiciden gelir (üç motor tipinin üç ayrı anahtar şeması
    # orada tanınır): chamber_analysis / case_analysis / chamber_structure.
    from hrma.export.cad_visualization import _chamber_wall_thickness_m
    wall_m, wall_src = _chamber_wall_thickness_m(md)
    if wall_m is None:
        raise ValueError(
            'chamber wall thickness is not available from the structural '
            'analysis (looked for chamber_analysis / case_analysis / '
            'chamber_structure); refusing to emit a manufacturing STEP with '
            'an assumed wall. Run the structural analysis first.')
    wall = wall_m * 1000.0
    liner = min(max(0.02 * D_ch, 1.5), 5.0)
    cap = min(max(1.6 * wall, 8.0), 0.3 * rc + 8.0)

    # ---- Enjektör girdileri: katı üretimine BAŞLAMADAN doğrula ----
    # v2.6.27 dürüstlük kapısı: "12 delik × Ø1,5 mm" uydurma varsayılanları
    # KALDIRILDI. Ölçüldü (denetçi, 2026-08-04): enjektör verisi hiç olmayan
    # bir sonuçla bile buradan 12 delikli bir "imalat" plakası çıkıyordu;
    # ham sıvı sonucunda ise motorun GERÇEKTEN hesapladığı plan
    # (``number_of_elements`` / ``fuel_orifice_diameter_mm``) okunmayıp
    # yerine yine 12 × Ø1,5 mm uyduruluyordu. Yeni sözleşme iki hâli ayırır:
    #
    # * Sonuç bir enjektör bloğu TAŞIYOR ama plan çözülemiyor (boş blok ya da
    #   motorun ``status: not_analyzed`` beyanı) -> REDDET (A8 ilkesi).
    #   Motorun kendi sözleşmesi (hybrid_rocket_engine, v2.6.26) delik planı
    #   üretilemediğinde uydurma yedek üretmez — imalat çıktısı, motorun
    #   reddettiği planı uyduramaz.
    # * Sonuç enjektörden HİÇ söz etmiyor (ör. katı motor sonucu varsayılan
    #   'hybrid' rotasından geçti) -> parça uydurulMAZ ve çizilMEZ — grain
    #   ilkesinin (H4-1: "yalnız sonuçta gerçekten varsa üretilir") eşleniği.
    #
    # Doğrulama katı üretiminden ÖNCE yapılır ki ret hâlinde çalışma dizinine
    # yarım dosya yazılmasın.
    if has_injector:
        inj = md.get('injector_design')
        if not isinstance(inj, dict):
            inj = md.get('injector')
        if not isinstance(inj, dict):
            has_injector = False  # sonuçta enjektör iddiası yok — çizilmez
    if has_injector:
        n_ori_f = _first_positive(inj.get('number_of_orifices'),
                                  inj.get('n_holes'),
                                  inj.get('number_of_elements'))
        d_ori = _first_positive(inj.get('orifice_diameter_mm'),
                                inj.get('hole_diameter'),
                                inj.get('fuel_orifice_diameter_mm'))
        if n_ori_f is None or d_ori is None:
            raise ValueError(
                'injector orifice count / diameter could not be resolved '
                'from the analysis result (looked for injector_design / '
                'injector: number_of_orifices | n_holes | number_of_elements '
                'and orifice_diameter_mm | hole_diameter | '
                'fuel_orifice_diameter_mm; the injector circuit model may '
                'have reported status=not_analyzed); refusing to emit a '
                'manufacturing STEP built from generator defaults.')
        n_ori = int(round(n_ori_f))
        # Halka yarıçapı: hiçbir çözücü orifis YERLEŞİMİNİ modellemez (devre
        # modeli sayı/çap/ΔP verir, radyal konum vermez). Delik sayısı/çapının
        # aksine bu "çözülemedi" değil "modellenmiyor" hâlidir; her enjektör
        # STEP'ini reddetmek imalat çıktısını tümden öldürürdü. Depodaki
        # yerleşik kalıp (safety_analysis 'ASSUMED L/D', water_hammer
        # 'ASSUMED material') izlenir: değer gerçek desen verisinden
        # gelmiyorsa katı ANCAK açık 'ASSUMED' beyanıyla çizilir ve beyan
        # STEP dosyasının içinde, parça adında taşınır (CAD ağacında görünür).
        ring_r_mm = _first_positive(inj.get('orifice_ring_radius_mm'))
        ring_assumed = ring_r_mm is None
        if ring_assumed:
            ring_r_mm = 0.7 * rc

    files = {}
    solids = []

    # ---- Kamara: duvar + baş kapak (kapalı profil revolve) ----
    chamber_profile = [
        (-cap, 0.0), (-cap, rc + wall), (L, rc + wall), (L, rc),
        (0.0, rc), (0.0, 0.0),
    ]
    chamber = _revolve_profile(chamber_profile)
    files['chamber'] = os.path.join(out_dir, f'{name}_chamber.step')
    _export_step_atomic(chamber, files['chamber'])
    chamber.label = 'chamber'
    solids.append(chamber)

    # ---- Nozul: iç kontur + duvar ofseti (tek kontur kaynağı) ----
    # İmalat çıktısı: ıraksak boy hesaplanmadıysa katı ÜRETİLMEZ (A5).
    pts, meta = sample_nozzle_inner_contour(md, require_solved_length=True)
    wall_noz = max(3.0, 0.1 * _num(md.get('throat_diameter'), 0.02) * 1000)
    inner = [(L + z, r) for z, r in pts]
    outer = [(z, r + wall_noz) for z, r in reversed(inner)]
    nozzle = _revolve_profile(inner + outer)
    files['nozzle'] = os.path.join(out_dir, f'{name}_nozzle.step')
    _export_step_atomic(nozzle, files['nozzle'])
    nozzle.label = 'nozzle'
    solids.append(nozzle)

    # ---- Yakıt grain'i: portlu halka silindir ----
    if has_grain:
        r_go = rc - liner
        zg0 = 0.35 * max(4.0, L - L_g)
        with BuildPart() as grain_bp:
            with Locations((zg0 + L_g / 2, 0, 0)):
                Cylinder(radius=r_go, height=L_g, rotation=(0, 90, 0))
                Cylinder(radius=max(r_p0, 1.0), height=L_g + 2,
                         rotation=(0, 90, 0), mode=Mode.SUBTRACT)
        grain = grain_bp.part
        files['fuel_grain'] = os.path.join(out_dir, f'{name}_fuel_grain.step')
        _export_step_atomic(grain, files['fuel_grain'])
        grain.label = 'fuel_grain'
        solids.append(grain)

    # ---- Enjektör plakası: gerçek orifis delikleri ----
    # Delik sayısı/çapı yukarıdaki kapıdan gelir (çözülemediyse buraya hiç
    # ulaşılmaz); halka yarıçapı desen verisi yoksa 'ASSUMED' beyanıyla çizilir.
    if has_injector:
        t_inj = min(max(0.9 * cap, 6.0), 24.0)
        with BuildPart() as inj_bp:
            with Locations((4 + t_inj / 2, 0, 0)):
                Cylinder(radius=rc - 0.5, height=t_inj, rotation=(0, 90, 0))
            ring_r = float(ring_r_mm)
            k = max(n_ori, 1)
            for i in range(k):
                a = 2 * np.pi * i / k
                with Locations((4 + t_inj / 2, ring_r * np.cos(a),
                               ring_r * np.sin(a))):
                    Cylinder(radius=max(d_ori / 2, 0.25), height=t_inj + 2,
                             rotation=(0, 90, 0), mode=Mode.SUBTRACT)
        injector = inj_bp.part
        files['injector'] = os.path.join(out_dir, f'{name}_injector.step')
        # Beyan parça ADINDA taşınır: STEP dosyasına ve CAD ağacına gömülür,
        # dosyayı açan imalatçı varsayımı görmeden deliği konumlandıramaz.
        injector.label = (
            'injector (orifice ring radius ASSUMED 0.7*R_chamber - not from '
            'pattern analysis)' if ring_assumed else 'injector')
        _export_step_atomic(injector, files['injector'])
        solids.append(injector)

    # ---- Assembly (tek dosya) ----
    # Parça adları CAD ağacında görünsün (SolidWorks/Fusion 'COMPOUND ×5' sorunu)
    assembly = Compound(children=solids, label='HRMA_motor_assembly')
    files['assembly'] = os.path.join(out_dir, f'{name}_assembly.step')
    _export_step_atomic(assembly, files['assembly'])

    return files


# Tank STEP zarfı: bu sınırların dışındaki ölçü bir birim hatasının işaretidir,
# geçerli bir tasarım değil. Sessizce devam etmek yerine hata verilir.
_TANK_MIN_MM, _TANK_MAX_MM = 10.0, 10_000.0


def generate_tank_step(tank_data, out_dir=None):
    """Sıvı motor tankları için gerçek STEP (silindir + yarıküre başlıklar).

    BİRİM SÖZLEŞMESİ: ``diameter`` ve ``length`` **milimetre** cinsindendir —
    modülün geri kalanı ve üretilen AP214 dosyası da mm kullanır.

    v2.6.2 düzeltmesi (1000× birim hatası):
    Bu fonksiyon girdiyi METRE varsayıp 1000 ile çarpıyordu. Fakat çağıran
    adaptör (``cad_export.generate_tank_cad``) sıvı motorun ürettiği
    ``dimensions.diameter`` değerini geçiriyor ve o değer ZATEN mm.
    Sonuç: 300 mm'lik bir tank 300.000 mm = **300 metre** olarak kuruluyordu.
    Hata yalnız varsayılan yolda görünmüyordu, çünkü varsayılan 0.3 metre
    cinsindendi ve ×1000 ile doğru 300 mm'yi veriyordu — yani veri geldiğinde
    bozuluyor, gelmediğinde doğru çalışıyordu.

    Daha kötüsü: OpenCascade 300 metrelik silindir + küre birleşimini kuramayıp
    SESSİZCE boş bir katı döndürüyordu. İstisna fırlamadığı için
    ``cad_export`` içindeki "STEP_NOT_AVAILABLE" emniyet yolu hiç tetiklenmiyor,
    kullanıcı geçerli görünen ama içi tamamen boş bir STEP dosyası indiriyordu.
    Bu yüzden aşağıda hem zarf denetimi hem de üretilen katının boş olmadığı
    kontrolü var.
    """
    _require()

    # D1: saniye çözünürlüklü zaman damgası yerine istek başına benzersiz dizin.
    if out_dir is None:
        purge_stale_workspaces()
        out_dir = new_workspace('hrma_tank_step_')
    else:
        os.makedirs(out_dir, exist_ok=True)
    out_dir = os.path.abspath(out_dir)

    files = {}
    for key in ('fuel_tank', 'oxidizer_tank'):
        td = (tank_data or {}).get(key) or {}
        # Girdi ZATEN mm — burada ölçek dönüşümü YOK (bkz. docstring).
        # v2.6.27 dürüstlük kapısı: 300 / 800 mm uydurma varsayılanları
        # KALDIRILDI. Ölçüldü (denetçi, 2026-08-04): ``generate_tank_step({})``
        # hiç veri olmadan iki eksiksiz "imalat" tankı üretiyordu — Ø300 mm,
        # 800 mm gövde, tamamı üreteç varsayımı. Kamara kolundaki ilke burada
        # da geçerlidir: ölçü çözülemiyorsa STEP ÜRETİLMEZ.
        D = _num(td.get('diameter'), None)
        Lc = _num(td.get('length'), None)
        if D is None or Lc is None or D <= 0.0 or Lc <= 0.0:
            raise ValueError(
                f'{key}.diameter / {key}.length could not be resolved from '
                'the tank analysis result; refusing to emit a manufacturing '
                'STEP built from generator defaults. Run the tank sizing '
                'analysis first.')
        for label, val in (('diameter', D), ('length', Lc)):
            if not (_TANK_MIN_MM <= val <= _TANK_MAX_MM):
                raise ValueError(
                    f'{key}.{label} = {val:g} mm is outside the physical '
                    f'envelope [{_TANK_MIN_MM:g}, {_TANK_MAX_MM:g}] mm. '
                    'This usually means the value was supplied in metres '
                    'instead of millimetres.')
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
        _export_step_atomic(bp.part, files[key])
    return files
