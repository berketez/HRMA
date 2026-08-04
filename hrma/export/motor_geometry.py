"""Katı ve sıvı motor sonuçlarını ortak motor-geometri sözlüğüne çevirir.

Kesit çizimi (create_improved_motor_cross_section), STEP/STL üreticileri ve
teknik çizimler hibrit-şekilli, METRE bazlı bir motor_data sözlüğü bekler.
Katı motor rotası mm bazlı, sıvı motor rotası KARIŞIK birimli (chamber mm,
throat/exit m) sonuç döndürür — dönüşümler burada tek noktada yapılır.

BİRİM SÖZLEŞMESİ (Faz 5B / H4-2) — bu modül dışa aktarım katmanının TEK
birim otoritesidir. Ölçüldü (HEAD 9d3728e, 3 Ağustos 2026): ``/calculate_solid``
yanıtı doğrudan ``/api/export-dxf``e verilince çizim ``Ø_chamber = 100000.0 mm``
(gerçek 100.0), ``Ø_throat = 47927.25 mm`` (gerçek 47.93), STEP/STL zarfları da
1000× büyük çıkıyordu; sıvıda ``Ø_chamber = 99192.1 mm`` yazarken boğaz/çıkış
DOĞRU idi — yani TEK çizimde kamara lülenin 1000 katıydı. Sebep: üreticilerin
her biri girdiyi koşulsuz METRE kabul edip 1000 ile çarpıyordu
(``drawing_generator._dims_mm``, ``step_export``, ``cad_visualization``), oysa
katı rotası mm, sıvı rotası karışık birim döndürüyor.

Çözüm tek noktada: ``normalise_export_geometry`` gelen sözlüğün birimini
AÇIKÇA çözer ve METRE cinsinden bir kopya döndürür; kopya ``length_units='m'``
beyanını ve alan-başına hangi yoldan çözüldüğünü gösteren
``geometry_unit_resolution`` kaydını taşır. Çözüm sırası:

  1. ``motor_geometry`` alt sözlüğü — bu modülde normalize edilmiştir, SI
     GARANTİLİ (``/calculate_solid`` ve ``/calculate_liquid`` yanıtlarında
     hazır gelir).
  2. ``length_units`` beyanı ('m' / 'mm').
  3. Büyüklük çıkarımı — eşikler aşağıda tek yerde tanımlı.

Hiçbir yolda çözülemeyen alan **uydurulmaz**: değer ``None`` kalır ve
üreticiler "hesaplanmadı" diye beyan eder.
"""

import numpy as np


def _num(v, fb):
    try:
        f = float(v)
        return f if np.isfinite(f) else fb
    except (TypeError, ValueError):
        return fb


# ---------------------------------------------------------------------------
# Birim çıkarım eşikleri — TEK tanım noktası (CLAUDE.md kural 11).
# ---------------------------------------------------------------------------
# Bu sınıftaki (amatör/üniversite) motorlarda bir çap metre cinsinden 1 m'yi,
# bir boy 5 m'yi geçmez; geçiyorsa değer milimetredir. Belirsiz bant (ör. 1.0)
# çap için mm kabul edilir: 1 m boğaz bu yazılımın kapsamı dışında, 1 mm boğaz
# ise gerçek bir mikro-motor ölçüsüdür. Eşikler daha önce
# ``openrocket_integration.py`` içinde tanımlıydı ve dışa aktarımın geri
# kalanından habersizdi; artık oradan da buradan içe aktarılır.
DIAMETER_SI_MAX_M = 1.0
LENGTH_SI_MAX_M = 5.0
THICKNESS_SI_MAX_M = 0.1

#: Birimi çözülen uzunluk alanları ve her birinin SI üst sınırı.
EXPORT_LENGTH_FIELDS = {
    'chamber_diameter': DIAMETER_SI_MAX_M,
    'throat_diameter': DIAMETER_SI_MAX_M,
    'exit_diameter': DIAMETER_SI_MAX_M,
    'port_diameter_initial': DIAMETER_SI_MAX_M,
    'port_diameter_final': DIAMETER_SI_MAX_M,
    'chamber_length': LENGTH_SI_MAX_M,
    'grain_length': LENGTH_SI_MAX_M,
    'nozzle_length': LENGTH_SI_MAX_M,
    'nozzle_convergent_length': LENGTH_SI_MAX_M,
    'nozzle_divergent_length': LENGTH_SI_MAX_M,
}

#: ``length_units`` beyanında kabul edilen yazımlar.
_DECLARED_METRE = frozenset({'m', 'metre', 'meter', 'metres', 'meters', 'si'})
_DECLARED_MM = frozenset({'mm', 'millimetre', 'millimeter', 'millimetres',
                          'millimeters'})

#: Grain verisi bulunamadığında üreticilerin basacağı gerekçe. Sıvı çift
#: yakıtlı motorda katı yakıt bloğu FİZİKSEL OLARAK yoktur; eski kod bu
#: durumda 240 mm boyunda, Ø30→50 mm portlu bir grain uydurup imalat
#: çizimine, STEP montajına ve STL'e koyuyordu (Faz 5B / H4-1).
GRAIN_NOT_IN_RESULT = (
    'NOT MODELLED: the analysis result carries no solid grain geometry '
    '(no grain_design, grain_length or port diameter). A liquid bipropellant '
    'engine has no grain; nothing is drawn in its place.')


def length_in_meters(value, si_max):
    """Bir uzunluğu metreye çevirir; birimi büyüklüğünden çıkarır.

    Döner: ``(metre veya None, 'si' | 'mm' | 'missing')``. Üst seviye motor
    sonuçları birimi beyan etmediği için başka yol yok; çağıran hangi yolun
    seçildiğini raporlar.
    """
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None, 'missing'
    if not np.isfinite(f) or f <= 0.0:
        return None, 'missing'
    if f > si_max:
        return f / 1000.0, 'mm'
    return f, 'si'


def declared_length_unit(motor_results):
    """``length_units`` beyanını çözer: 'm', 'mm' ya da None (beyan yok)."""
    declared = str((motor_results or {}).get('length_units') or '').strip().lower()
    if declared in _DECLARED_METRE:
        return 'm'
    if declared in _DECLARED_MM:
        return 'mm'
    return None


def resolve_length_m(motor_results, key, si_max=None):
    """Tek bir uzunluk alanını METRE olarak çözer; kaynağını da döndürür.

    Döner: ``(metre veya None, kaynak)``. Kaynak değerleri:
    ``motor_geometry`` (normalize blok, SI garantili), ``declared:m``,
    ``declared:mm``, ``si`` / ``mm`` (büyüklük çıkarımı), ``missing``.
    """
    md = motor_results if isinstance(motor_results, dict) else {}
    if si_max is None:
        si_max = EXPORT_LENGTH_FIELDS.get(key, LENGTH_SI_MAX_M)

    geo = md.get('motor_geometry')
    if isinstance(geo, dict):
        try:
            f = float(geo.get(key))
        except (TypeError, ValueError):
            f = None
        if f is not None and np.isfinite(f) and f > 0.0:
            return f, 'motor_geometry'

    declared = declared_length_unit(md)
    if declared is not None:
        try:
            f = float(md.get(key))
        except (TypeError, ValueError):
            return None, 'missing'
        if not np.isfinite(f) or f <= 0.0:
            return None, 'missing'
        return (f if declared == 'm' else f / 1000.0), f'declared:{declared}'

    value, unit = length_in_meters(md.get(key), si_max)
    return value, unit


def resolve_grain_m(motor_results):
    """Grain geometrisini METRE olarak çözer; yoksa ``None`` döner.

    Döner: ``(sözlük veya None, gerekçe)``. Sözlük anahtarları
    ``length``, ``port_initial``, ``port_final`` (metre; sonuncusu None
    olabilir) ve ``source``.

    UYDURMA YOK: boy ya da başlangıç portu çözülemiyorsa grain HİÇ
    döndürülmez — çağıran çizmez ve gerekçeyi basar.
    """
    md = motor_results if isinstance(motor_results, dict) else {}
    # Normalize blok varsa grain de oradan okunur (SI garantili).
    geo = md.get('motor_geometry')
    sources = []
    if isinstance(geo, dict):
        sources.append((geo, 'motor_geometry'))
    sources.append((md, 'motor result'))

    for node, label in sources:
        gd = node.get('grain_design') if isinstance(node, dict) else None
        gd = gd if isinstance(gd, dict) else {}
        # ``*_mm`` ekli anahtarlar birimini BEYAN eder — çıkarım yapılmaz.
        length_mm = _first_positive(gd.get('grain_length_mm'))
        port0_mm = _first_positive(gd.get('port_diameter_initial_mm'),
                                   gd.get('inner_diameter_mm'))
        port1_mm = _first_positive(gd.get('port_diameter_final_mm'),
                                   gd.get('outer_diameter_mm'))
        length_m = length_mm / 1000.0 if length_mm is not None else None
        port0_m = port0_mm / 1000.0 if port0_mm is not None else None
        port1_m = port1_mm / 1000.0 if port1_mm is not None else None
        src = f'{label}.grain_design (mm, declared)'

        if length_m is None or port0_m is None:
            # Beyansız üst seviye alanlar — birim çıkarımı ile.
            lv, lsrc = resolve_length_m(node, 'grain_length')
            p0, p0src = resolve_length_m(node, 'port_diameter_initial')
            p1, _p1src = resolve_length_m(node, 'port_diameter_final')
            if length_m is None and lv is not None:
                length_m, src = lv, f'{label}.grain_length ({lsrc})'
            if port0_m is None and p0 is not None:
                port0_m = p0
                src = f'{src}; port from {label} ({p0src})'
            if port1_m is None and p1 is not None:
                port1_m = p1

        if length_m is not None and port0_m is not None:
            return {'length': length_m, 'port_initial': port0_m,
                    'port_final': port1_m, 'source': src}, None

    return None, GRAIN_NOT_IN_RESULT


def _first_positive(*values):
    """İlk sonlu-pozitif değeri döndürür; yoksa None (uydurma yedek YOK)."""
    for v in values:
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if np.isfinite(f) and f > 0.0:
            return f
    return None


def normalise_export_geometry(motor_results):
    """Dışa aktarım üreticileri için girdiyi METRE'ye indirger.

    Döner: ``(kopya, rapor)``.

    * ``kopya`` — girdinin sığ kopyası; çözülebilen uzunluk alanları METRE
      olarak yeniden yazılır, ``length_units='m'`` beyanı eklenir. Çözülemeyen
      alanlar DOKUNULMAZ (uydurma değer yazılmaz) ve raporda ``missing``
      görünür.
    * ``rapor`` — ``{'fields': {alan: kaynak}, 'notes': [...],
      'grain': {...} | None, 'grain_reason': str | None}``.

    Fonksiyon idempotenttir: çıktısını tekrar verirseniz ``declared:m``
    yoluyla aynı değerleri döndürür (ölçüldü, bkz. tests/test_faz5_cizim_birim).
    """
    md = motor_results if isinstance(motor_results, dict) else {}
    out = dict(md)
    fields = {}
    notes = []

    for key, si_max in EXPORT_LENGTH_FIELDS.items():
        if key not in md and not isinstance(md.get('motor_geometry'), dict):
            continue
        value, source = resolve_length_m(md, key, si_max)
        if value is None:
            if key in md:
                fields[key] = 'missing'
            continue
        fields[key] = source
        if source in ('mm', 'declared:mm'):
            notes.append(f'{key} read as mm ({float(md[key]):.6g}) -> '
                         f'{value:.6g} m')
        out[key] = value

    grain, grain_reason = resolve_grain_m(md)
    if grain is not None:
        out['grain_length'] = grain['length']
        out['port_diameter_initial'] = grain['port_initial']
        if grain['port_final'] is not None:
            out['port_diameter_final'] = grain['port_final']
        fields['grain'] = grain['source']

    # Beyan: bundan sonra bu sözlüğü okuyan herkes METRE görür.
    out['length_units'] = 'm'
    report = {
        'fields': fields,
        'notes': notes,
        'grain': grain,
        'grain_reason': grain_reason,
    }
    out['geometry_unit_resolution'] = report
    return out, report


def _real_mm(*values):
    """Verilen adaylardan ilk sonlu-pozitif MİLİMETRE değerini döndürür.

    Hiçbiri geçerli değilse None döner — uydurma varsayılan ÜRETİLMEZ.
    """
    for v in values:
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if np.isfinite(f) and f > 0:
            return f
    return None


def _put_nozzle_lengths(out, conv_mm, div_mm):
    """Çözücünün lüle uzunluklarını METRE olarak ortak sözlüğe yazar.

    Faz 4B / A5: bu sözlük lüle uzunluğunu HİÇ taşımıyordu; tüketici
    (``nozzle_design.sample_nozzle_inner_contour``) ıraksak boyu yeniden
    türetmek zorunda kalıyor ve bell lülede ``divergent_half_angle_deg``
    alanını (bell'de bu BOĞAZ açısıdır: bell_80 -> 30°, bell_60 -> 34°) konik
    yarı açı sanıyordu. Ölçüldü (HEAD a7ff1e7, 10 kN sıvı motor):
    bell_80 çözücü 107.69 mm / export 62.48 mm (-41.99%),
    bell_60 çözücü 80.77 mm / export 53.48 mm (-33.79%), konik +0.78%.

    Değer yoksa ANAHTAR HİÇ YAZILMAZ — 'hesaplanmadı' hâli, sıfır ya da
    uydurma bir sayı değil, anahtarın yokluğuyla bildirilir.
    """
    if conv_mm is not None:
        out['nozzle_convergent_length'] = conv_mm / 1000.0
    if div_mm is not None:
        out['nozzle_divergent_length'] = div_mm / 1000.0


def solid_results_to_motor_geometry(results):
    """/calculate_solid sonucundan hibrit-şekilli geometri (m) üretir.

    Katıda 'port' çekirdek (core) deliğidir: başlangıç portu = core çapı.

    Son port için eskiden KOŞULSUZ ``grain_od_mm`` yazılıyordu, gerekçesi de
    "web tamamen yanar" diye not düşülmüştü. Bu yalnız iç yüzeyin yandığı
    (dış yüzey inhibitörlü) durumda doğrudur. Dış yüzey de yanıyorsa cephe
    İKİ taraftan ilerler, tükenme yarı web'te olur ve grain dışı hiçbir zaman
    porta dönüşmez.

    2026-08-03 (Faz 6, T07 kök nedeni) ölçümü: varsayılan Ø100/Ø30 grain'de
    inhibitör açık/kapalı arasında yanma süresi 2,1863 s -> 1,1757 s değişiyor
    ama ``port_diameter_final`` iki koşuda da 100,0 mm dönüyordu — yani
    tükenmenin yarıya indiğini bilen çözücüyle çelişiyordu. Çözücü doğru
    sayıyı zaten yayımlıyor (``grain_design.web_burnout_mm`` +
    ``web_basis``); burada o kullanılır, yoksa eski davranışa düşülür.
    """
    r = results or {}
    gd = r.get('grain_design') or {}
    ks = ((r.get('design_summary') or {}).get('key_dimensions')) or {}
    case = ((r.get('cad_design') or {}).get('case_design')) or {}

    grain_len_mm = _num(gd.get('grain_length_mm'), _num(r.get('grain_length'), 500.0))
    chamber_d_mm = _num(case.get('inner_diameter'),
                        _num(r.get('chamber_diameter'), 100.0))
    chamber_l_mm = _num(case.get('length'),
                        _num(ks.get('motor_length_mm'), grain_len_mm / 0.85))
    chamber_l_mm = max(chamber_l_mm, grain_len_mm * 1.05)
    core_d_mm = _num(gd.get('inner_diameter_mm'), _num(r.get('core_diameter'), 30.0))
    grain_od_mm = _num(gd.get('outer_diameter_mm'), chamber_d_mm - 4.0)

    # Son port: çözücünün tükenen web'i varsa ondan türetilir (bkz. üstteki
    # açıklama). ``web_burnout_mm`` iç cepheden tüketilen kalınlıktır, port
    # yarıçapı o kadar büyür — yani çap 2× artar.
    web_burnout_mm = _num(gd.get('web_burnout_mm'), None)
    if web_burnout_mm is not None and web_burnout_mm > 0:
        port_final_mm = min(core_d_mm + 2.0 * web_burnout_mm, grain_od_mm)
    else:
        port_final_mm = grain_od_mm  # bilgi yoksa eski (tek cepheli) varsayım

    ang = r.get('nozzle_angles') or {}
    ds_noz = ((r.get('design_summary') or {}).get('nozzle')) or {}
    noz_geo = (r.get('nozzle_design') or {}).get('geometry') or {}

    out = {
        'motor_name': r.get('motor_name') or 'UZAYTEK_SOLID',
        'chamber_diameter': chamber_d_mm / 1000.0,
        'chamber_length': chamber_l_mm / 1000.0,
        'throat_diameter': _num(r.get('throat_diameter'), 20.0) / 1000.0,
        'exit_diameter': _num(r.get('exit_diameter'), 60.0) / 1000.0,
        'expansion_ratio': _num(r.get('expansion_ratio'), 9.0),
        'chamber_pressure': _num(r.get('chamber_pressure'), 40.0),
        'burn_time': _num(r.get('burn_time'), 0.0),
        'thrust': _num(r.get('average_thrust'), 0.0),
        'total_impulse': _num(r.get('total_impulse'), 0.0),
        'isp': _num(r.get('specific_impulse'), 0.0),
        'propellant_mass_total': _num(r.get('propellant_mass'), 0.0),
        'grain_length': grain_len_mm / 1000.0,
        'port_diameter_initial': core_d_mm / 1000.0,
        'port_diameter_final': port_final_mm / 1000.0,
        'grain_design': gd,
        'nozzle_angles': ang,
        'structural_analysis': r.get('structural_analysis') or {},
    }
    # Katıda üç kaynak da aynı çözümden gelir; ilk gerçek değer kullanılır.
    _put_nozzle_lengths(
        out,
        _real_mm(ang.get('convergent_length_mm'),
                 ds_noz.get('convergent_length_mm'),
                 noz_geo.get('convergent_length')),
        _real_mm(ang.get('divergent_length_mm'),
                 ds_noz.get('divergent_length_mm'),
                 noz_geo.get('divergent_length')))
    return out


def liquid_results_to_motor_geometry(results):
    """/calculate_liquid sonucundan hibrit-şekilli geometri (m) üretir.

    Dikkat — sıvı rotasının birimleri karışıktır: chamber_diameter ve
    chamber_length MM, throat_diameter ve exit_diameter METRE döner.
    """
    r = results or {}
    inj = r.get('injector_design') or {}
    ang = r.get('nozzle_angles') or {}
    cooling = r.get('cooling_system') or {}
    n_elem = _first_positive(inj.get('number_of_elements'))

    out = {
        'motor_name': r.get('motor_name') or 'UZAYTEK_LIQUID',
        'chamber_diameter': _num(r.get('chamber_diameter'), 150.0) / 1000.0,
        'chamber_length': _num(r.get('chamber_length'), 300.0) / 1000.0,
        'throat_diameter': _num(r.get('throat_diameter'), 0.03),
        'exit_diameter': _num(r.get('exit_diameter'), 0.09),
        'expansion_ratio': _num(r.get('expansion_ratio'), 9.0),
        'chamber_pressure': _num(r.get('chamber_pressure'), 50.0),
        'burn_time': _num(r.get('burn_time'), 0.0),
        'thrust': _num(r.get('thrust'), 0.0),
        'isp': _num(r.get('isp_sea_level'), 0.0),
        'of_ratio': _num(r.get('mixture_ratio'), 0.0),
        'nozzle_angles': ang,
        'injector_design': {
            'injector_type': inj.get('injector_type'),
            # v2.6.27: "12 delik / Ø1,5 mm" ikinci-katman uydurmaları
            # KALDIRILDI. Sıvı motor bu değerleri her başarılı koşuda kendisi
            # yayımlar (liquid_rocket_engine: number_of_elements /
            # fuel_orifice_diameter_mm); yayımlamadıysa None taşınır ve
            # imalat çıktısı (step_export) uydurmak yerine REDDEDER; çizim
            # katmanı da 'hesaplanmadı' beyan eder (uydurma yedek YOK).
            'number_of_orifices': (int(round(n_elem))
                                   if n_elem is not None else None),
            'orifice_diameter_mm': _real_mm(inj.get('fuel_orifice_diameter_mm')),
            'injection_pressure_drop_bar':
                _num(inj.get('injection_pressure_drop_fuel_bar'), 0.0),
        },
        # A8: imalata giden STEP cidar kalınlığını buradan okur. Bu anahtar
        # eskiden hiç taşınmıyordu; STEP 'chamber_analysis' arayıp bulamayınca
        # 0.045·D geometrik yedeğine düşüyordu. Sıvı motor cidarı
        # 'chamber_structure' bloğunda yayımlanır.
        'structural_analysis': r.get('structural_analysis') or {},
    }
    # Sıvıda nozzle_angles['nozzle_length_mm'] IRAKSAK boyudur (boğaz→çıkış,
    # calculate_nozzle_geometry içinde L_nozzle); yakınsak koni soğutma
    # bloğunda ayrı raporlanır. Ölçüldü: ikisi cooling_system'deki
    # convergent_length / divergent_length ile bit-aynı.
    _put_nozzle_lengths(
        out,
        _real_mm(cooling.get('convergent_length')),
        _real_mm(cooling.get('divergent_length'),
                 ang.get('nozzle_length_mm')))
    return out
