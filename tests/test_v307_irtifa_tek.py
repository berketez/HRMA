"""V307/İRTİFA-TEK — kullanıcının irtifası her yolda GEOMETRİK okunur.

Ana model kararı (16 Kas 2026): kullanıcının girdiği irtifa (test irtifası,
tasarım irtifası, tablo irtifası, saha rakımı, uçuş irtifası) geometriktir;
US Standard Atmosphere 1976 katman tablosu geopotansiyel irtifayla tanımlı
olduğundan H = h·r0/(r0 + h) ile çevrilerek verilir (USSA 1976 Denk. 18,
r0 = 6 356 766 m). Yardımcılar ``hrma.constants``: ``geometric_to_geopotential``,
``isa_pressure_geometric``, ``isa_temperature_geometric``. ``isa_pressure`` /
``isa_temperature`` geopotansiyel bekler ve değişmedi.

Önceden aynı "irtifa" iki ayrı basınç veriyordu: motor yolları dönüşümsüz
(geopotansiyel) okuyordu, yörünge çözücüsü geometrik; fark 20 km'de %0,99,
50 km'de %5,05 (ölçüm: docs/scofield/raw/OH/V307/irtifa-tek/olcum/).

Bekçiler:
  (a) kaynak taraması — ürün kodunda ``isa_pressure(`` / ``isa_temperature(``
      doğrudan çağrısı YALNIZ adıyla izinli geopotansiyel / deniz seviyesi
      çağıranlarda kalır; yeni çağıran listeye girmeden KIRMIZI. Aynı tarama
      ön yüzdeki tek JS atmosferi (``advanced.html``) için.
  (b) parametrik çapraz denetim — 0 / 1 / 20 / 50 km'de her yolun ortam
      basıncı ``isa_pressure_geometric`` ile bağıl 1e-12 (alanın bandı darsa
      bandın içindeki irtifalar); h = 0'da deniz seviyesi bit-aynı.
  (c) r0 tek tanım — ``test_d20_altyapi_a1`` envanteri .py/.js'i tarar; bu
      bekçi şablonları (.html) da tarar ve tek ön yüz ikizini merkeze çaprazlar.
"""
import ast
import collections
import contextlib
import io
import math
import pathlib
import re
import shutil
import subprocess
import warnings

import pytest

from hrma import constants as C

KOK = pathlib.Path(__file__).resolve().parent.parent
HOST = {'Host': '127.0.0.1:8080'}
IRTIFALAR_M = (0.0, 1000.0, 20000.0, 50000.0)


def _sessiz(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()), \
            warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return fn(*a, **k)


def _geo_pa(h):
    return C.isa_pressure_geometric(h)


# ===========================================================================
# (a) Kaynak taraması
# ===========================================================================
#: Ürün kodunda ``isa_pressure(`` / ``isa_temperature(`` DOĞRUDAN çağrısının
#: izinli olduğu yerler: (dosya, çevreleyen işlev, çağrılan, argüman) -> adet.
#: Argüman ya geopotansiyeldir (çevrilmiş H, tablo sınırı) ya da deniz
#: seviyesidir (0 m: iki okuma tanım gereği bit-aynı). Liste bir MANDALDIR:
#: yeni çağıran girerse (ya da biri kalkarsa) KIRMIZI — gerekçesiyle eklenir.
IZINLI_DOGRUDAN = collections.Counter({
    # Yardımcıların kendisi: geometrik girdiyi çevirip tabloya verir.
    ('hrma/constants.py', 'isa_pressure_geometric', 'isa_pressure',
     'geometric_to_geopotential(altitude_m)'): 1,
    ('hrma/constants.py', 'isa_temperature_geometric', 'isa_temperature',
     'geometric_to_geopotential(altitude_m)'): 1,
    # Katı ve sıvı irtifa tablolarının tablo üstü dalı: H çevrilmiş
    # geopotansiyel irtifadır (aynı işlevde H = geometric_to_geopotential).
    ('hrma/engines/solid_rocket_engine.py', 'calculate_altitude_performance',
     'isa_pressure', 'H'): 1,
    ('hrma/engines/solid_rocket_engine.py', 'calculate_altitude_performance',
     'isa_temperature', 'H'): 1,
    ('hrma/engines/liquid_rocket_engine.py', 'calculate_altitude_performance',
     'isa_pressure', 'H'): 1,
    ('hrma/engines/liquid_rocket_engine.py', 'calculate_altitude_performance',
     'isa_temperature', 'H'): 1,
    # 6-DOF / yörünge itki telafisi referans basınç bandı: tablonun KENDİ
    # geopotansiyel sınırlarındaki basınç (girdi irtifası değil).
    ('hrma/app.py', '_itki_telafi_girdisi', 'isa_pressure',
     'ISA_TABLE_TOP_M'): 1,
    ('hrma/app.py', '_itki_telafi_girdisi', 'isa_pressure',
     'ISA_TABLE_BOTTOM_M'): 1,
    # Deniz seviyesi (0 m).
    ('hrma/analysis/water_hammer.py', 'analyze', 'isa_pressure', '0.0'): 1,
    ('hrma/engines/combustion_analysis.py', '_exit_pressure_from_expansion',
     'isa_pressure', '0.0'): 2,
    ('hrma/engines/combustion_analysis.py', '_fixed_nozzle_altitude_sweep',
     'isa_pressure', '0.0'): 1,
    ('hrma/engines/combustion_analysis.py', 'analyze_combustion',
     'isa_pressure', '0.0'): 1,
    # 3.0.7 ONARIM2-İTKİ (M7-ITKI-8): 3B Isp yüzeyinin çıkış basıncı —
    # hibrit çözücünün ε'suz çapasıyla AYNI ifade (deniz seviyesi, 0 m);
    # sıvı düğümleri (cea_bridge) de bu basınca eşleşik genleşir.
    ('hrma/visualization/visualization.py', '_surface_exit_pressure_bar',
     'isa_pressure', '0.0'): 1,
})


_HEDEF_ADLAR = ('isa_pressure', 'isa_temperature')


def _dogrudan_cagrilar():
    sayac = collections.Counter()
    for yol in sorted((KOK / 'hrma').rglob('*.py')):
        agac = ast.parse(yol.read_text(encoding='utf-8'))
        goreli = yol.relative_to(KOK).as_posix()
        # Takma adla ithal (``from hrma.constants import isa_pressure as p``)
        # taramadan kaçamaz: takma ad gerçek ada çözülür.
        takma = {}
        for dugum in ast.walk(agac):
            if (isinstance(dugum, ast.ImportFrom)
                    and dugum.module == 'hrma.constants'):
                for ad in dugum.names:
                    if ad.name in _HEDEF_ADLAR and ad.asname:
                        takma[ad.asname] = ad.name

        class Gezgin(ast.NodeVisitor):
            def __init__(self):
                self.islev = []

            def visit_FunctionDef(self, dugum):
                self.islev.append(dugum.name)
                self.generic_visit(dugum)
                self.islev.pop()

            visit_AsyncFunctionDef = visit_FunctionDef

            def visit_Call(self, dugum):
                f = dugum.func
                ad = (f.id if isinstance(f, ast.Name)
                      else f.attr if isinstance(f, ast.Attribute) else None)
                ad = takma.get(ad, ad)
                if ad in _HEDEF_ADLAR:
                    arg = ast.unparse(dugum.args[0]) if dugum.args else ''
                    sayac[(goreli, self.islev[-1] if self.islev else '<modul>',
                           ad, arg)] += 1
                self.generic_visit(dugum)

        Gezgin().visit(agac)
    return sayac


def test_a_dogrudan_isa_cagrisi_yalniz_izinli_yerlerde():
    simdi = _dogrudan_cagrilar()
    yeni = simdi - IZINLI_DOGRUDAN
    kalkan = IZINLI_DOGRUDAN - simdi
    assert not yeni, (
        'Geometrik girdi isa_pressure/isa_temperature\'a DOĞRUDAN verilmiş '
        'olabilir (yeni çağıran): %s. Kullanıcı irtifası, saha rakımı ya da '
        'uçuş irtifası ise isa_pressure_geometric / isa_temperature_geometric '
        'kullanın; gerçekten geopotansiyel ya da deniz seviyesiyse '
        'IZINLI_DOGRUDAN listesine gerekçesiyle ekleyin.' % sorted(yeni))
    assert not kalkan, (
        'İzinli liste bayat (mandal daralmalı): %s' % sorted(kalkan))


def test_a_tablo_islevleri_H_yi_merkezi_yardimcidan_alir():
    """Katı ve sıvı irtifa tablolarının satır içi dönüşüm kopyaları
    ``geometric_to_geopotential``a bağlandı (26 145 irtifada bit-aynı); katman
    yürüyüşü ve tablo üstü eşiği H ile."""
    import inspect
    from hrma.engines import liquid_rocket_engine as lre
    from hrma.engines import solid_rocket_engine as sre
    for sinif in (sre.SolidRocketEngine, lre.LiquidRocketEngine):
        govde = inspect.getsource(sinif.calculate_altitude_performance)
        assert 'H = geometric_to_geopotential(alt)' in govde, sinif
        assert 'if H >= candidate[0]:' in govde, sinif
        assert 'if H > ISA_TABLE_TOP_M:' in govde, sinif
        assert 'if alt > ISA_TABLE_TOP_M' not in govde, sinif
        assert 'isa_pressure(alt)' not in govde, sinif


_JS_ATMOSFER = re.compile(r'_isaPressurePaJS\s*\(([^)]*)\)')


def test_a_on_yuzun_tek_atmosferi_geometrik_okur():
    """Ön yüzde tablo okuyan tek JS işlevi ``_isaPressurePaJS``tir
    (hibrit sayfası); onu çağıran tek yer ``altitudeToPressure`` ve argüman
    çevrilmiş H'dir."""
    bulunan = []
    for yol in sorted(list((KOK / 'hrma' / 'templates').glob('*.html'))
                      + list((KOK / 'hrma' / 'static' / 'js').rglob('*.js'))):
        if yol.name.endswith('.min.js'):
            continue
        metin = yol.read_text(encoding='utf-8')
        for m in _JS_ATMOSFER.finditer(metin):
            bulunan.append((yol.relative_to(KOK).as_posix(), m.group(1)))
    assert sorted(bulunan) == [('hrma/templates/advanced.html', 'H'),
                               ('hrma/templates/advanced.html', 'h')], bulunan
    html = (KOK / 'hrma' / 'templates' / 'advanced.html').read_text(
        encoding='utf-8')
    i = html.index('function altitudeToPressure(')
    govde = html[i:html.index('\n        }\n', i)]
    assert 'var H = h * ISA_R0_JS / (ISA_R0_JS + h);' in govde
    assert 'return _isaPressurePaJS(H) / 1e5;' in govde


# ===========================================================================
# (b) Parametrik çapraz denetim: her yol, aynı irtifa, aynı basınç
# ===========================================================================
def test_b_yardimcilar_h0_da_bit_ayni_ve_dogrudan_okumadan_ayri():
    import struct
    for f_geo, f_dog in ((C.isa_pressure_geometric, C.isa_pressure),
                         (C.isa_temperature_geometric, C.isa_temperature)):
        assert struct.pack('<d', f_geo(0.0)) == struct.pack('<d', f_dog(0.0))
    # Fark ölçülen büyüklükte (dönüşümsüz okuma düşük basınç verir).
    oran20 = C.isa_pressure(20000.0) / C.isa_pressure_geometric(20000.0)
    oran50 = C.isa_pressure(50000.0) / C.isa_pressure_geometric(50000.0)
    assert 0.989 < oran20 < 0.991, oran20
    assert 0.950 < oran50 < 0.953, oran50
    # Sıcaklık eşi aynı H'yi okur.
    for h in IRTIFALAR_M + (84000.0, 90000.0):
        assert C.isa_temperature_geometric(h) == C.isa_temperature(
            C.geometric_to_geopotential(h))


@pytest.mark.parametrize('h', (1000.0, 20000.0, 30000.0))
def test_b_kati_test_irtifasi(h):
    """Katı test irtifası (form bandı 0–30 000 m; 50 km bant dışı)."""
    from hrma.engines.solid_rocket_engine import SolidRocketEngine
    m = _sessiz(SolidRocketEngine, overrides={'test_altitude': h})
    assert m.ambient_pressure_bar * 1e5 == pytest.approx(_geo_pa(h),
                                                         rel=1e-12)


def test_b_kati_test_irtifasi_sifirda_deniz_seviyesi():
    from hrma.engines.solid_rocket_engine import (SEA_LEVEL_PRESSURE_BAR,
                                                  SolidRocketEngine)
    m = _sessiz(SolidRocketEngine, overrides={'test_altitude': 0})
    assert m.ambient_pressure_bar == SEA_LEVEL_PRESSURE_BAR


def test_b_kati_irtifa_tablosu():
    from hrma.engines.solid_rocket_engine import SolidRocketEngine
    m = SolidRocketEngine(grain_type='bates', propellant_type='apcp',
                          chamber_diameter=100.0, grain_length=500.0,
                          core_diameter=40.0, chamber_pressure=40.0)
    _sessiz(m.calculate_performance)
    satirlar = _sessiz(m.calculate_altitude_performance,
                       list(IRTIFALAR_M) + [90000.0, 100000.0])
    for s in satirlar:
        h = float(s['altitude'])
        # Satırın ``pressure`` alanı bar (tablonun kendi sözleşmesi).
        anahtar = 'pressure' if 'pressure' in s else 'ambient_pressure'
        assert s[anahtar] * 1e5 == pytest.approx(_geo_pa(h), rel=1e-12), s


def test_b_kati_cakisma_kapisi_motorla_ayni_sayi():
    from hrma.app import _ortam_basinci_cakismasi
    for h in (1000.0, 20000.0, 30000.0):
        govde = _ortam_basinci_cakismasi({'test_altitude': h,
                                          'atm_pressure': 101.325})
        alan = govde['invalid_fields'][0]
        assert alan['field'] == 'test_altitude'
        assert alan['implies_ambient_pressure_kPa'] == pytest.approx(
            _geo_pa(h) / 1e3, rel=1e-12)
        # Motorun okuduğu basıncı gönderen istemci çakışma görmez.
        assert _ortam_basinci_cakismasi(
            {'test_altitude': h, 'atm_pressure': _geo_pa(h) / 1e3}) is None


def test_b_hibrit_irtifa_tablosu():
    from hrma.engines.combustion_analysis import CombustionAnalyzer
    satirlar, _meta = CombustionAnalyzer._fixed_nozzle_altitude_sweep(
        1.0, 2000.0, 1.0, 1500.0, 300.0, list(IRTIFALAR_M))
    for s in satirlar:
        h = float(s['altitude'])
        assert s['pressure'] * C.PA_PER_BAR == pytest.approx(_geo_pa(h),
                                                             rel=1e-12)
        assert s['temperature'] == pytest.approx(
            C.isa_temperature_geometric(h), rel=1e-12)
    sifir = satirlar[0]
    assert sifir['pressure'] == C.isa_pressure(0.0) * C.BAR_PER_PA
    assert sifir['temperature'] == C.isa_temperature(0.0)


def _profil_motoru(p_tas_pa):
    """İrtifa Profili için asgari motor yanıtı (test düzeneği)."""
    return {
        'thrust': 300.0,
        'altitude_performance': {'nozzle_loss_model': {
            'exit_area_m2': 4.0e-4, 'anchor_ambient_pressure_pa': p_tas_pa,
            'mass_flow_kg_s': 0.15, 'thrust_vacuum_n': 340.0}},
        # Çıkış basıncı 0,5 bar: Summerfield (P_e < 0,4·p_a) 0 m'de de
        # ayrılma öngörmez, her satır sayı yayımlar.
        'nozzle_expansion_screen': {'exit_pressure_bar': 0.5,
                                    'floor_applied': False},
    }


def test_b_hibrit_irtifa_profili():
    from hrma.analysis.altitude_performance import fixed_nozzle_profile
    profil = {'start': 0.0, 'end': 50000.0, 'points': 51}
    r = fixed_nozzle_profile(_profil_motoru(C.isa_pressure(0.0)), profil)
    assert r['status'] == 'computed', r
    satirlar = {s['altitude_m']: s for s in r['rows']}
    for h in IRTIFALAR_M:
        assert satirlar[h]['ambient_pressure_bar'] * C.PA_PER_BAR == \
            pytest.approx(_geo_pa(h), rel=1e-12)
    assert satirlar[0.0]['thrust_n'] == 300.0
    assert 'isa_pressure_geometric' in r['basis']


def test_b_hibrit_profilin_baslangici_tasarim_ortaminin_kendisi():
    """Form başlangıç irtifasının basıncını gönderir (altitudeToPressure,
    geometrik); profilin başlangıç satırı aynı basınçla motorun itkisidir."""
    from hrma.analysis.altitude_performance import fixed_nozzle_profile
    h0 = 20000.0
    p_tas = _geo_pa(h0)
    r = fixed_nozzle_profile(_profil_motoru(p_tas),
                             {'start': h0, 'end': 0.0, 'points': 5})
    bas = r['rows'][0]
    assert bas['altitude_m'] == h0
    assert bas['ambient_pressure_bar'] == p_tas * C.BAR_PER_PA
    assert bas['thrust_n'] == 300.0


def test_b_saha_atmosferi():
    from hrma.analysis import launch_site as ls
    for h in (-430.0,) + IRTIFALAR_M + (9000.0,):
        atm = ls.atmosphere_at(h)
        assert atm['pressure_pa'] == pytest.approx(_geo_pa(h), rel=1e-12)
        assert atm['temperature_k'] == pytest.approx(
            C.isa_temperature_geometric(h), rel=1e-12)
    # Deniz seviyesi bit-aynı.
    s0 = ls.atmosphere_at(0.0)
    assert s0['pressure_pa'] == C.P_SEA_LEVEL_PA
    assert s0['temperature_k'] == C.ISA_LAYERS[0][1]


def test_b_saha_basinc_duyarliligi_basincin_kendi_turevi():
    """dP/dh, yayımlanan basıncın GEOMETRİK irtifaya göre türevidir."""
    from hrma.analysis import launch_site as ls
    for h in (500.0, 3000.0, 8000.0):
        d = 0.5
        sayisal = -(ls.atmosphere_at(h + d)['pressure_pa']
                    - ls.atmosphere_at(h - d)['pressure_pa']) / (2 * d)
        assert ls.isa_pressure_sensitivity_pa_per_m(h) == pytest.approx(
            sayisal, rel=1e-6), h
    assert ls.isa_pressure_sensitivity_pa_per_m(0.0) == (
        ls.atmosphere_at(0.0)['density_kg_m3'] * C.G_0)


def test_b_saha_cozumu_rakimin_geometrik_basinci():
    from hrma.analysis import launch_site as ls
    r = _sessiz(ls.resolve_launch_site, 37.8746, 32.4932, use_online=False)
    h = r['elevation_m']
    assert h > 500.0, r
    assert r['pressure_pa'] == pytest.approx(_geo_pa(h), rel=1e-12)


def test_b_openrocket_ucus_profili_yogunlugu():
    from hrma.export import openrocket_integration as oi
    for h in IRTIFALAR_M:
        beklenen = (_geo_pa(h) * C.M_AIR
                    / (C.R_STAR_ICAO * C.isa_temperature_geometric(h)))
        assert oi._air_density(h) == pytest.approx(beklenen, rel=1e-12)


def test_b_sivi_irtifa_tablosu_ve_satir_lulesi():
    from hrma.engines import liquid_rocket_engine as lre
    govde = {
        'fuel_type': 'rp1', 'oxidizer_type': 'lox', 'mixture_ratio': 2.4,
        'engine_cycle': 'pressure_fed', 'thrust': 5000,
        'chamber_pressure': 30, 'feed_pressure': 45,
        'injector_type': 'unlike_impinging', 'cooling_type': 'ablative',
        'chamber_material': 'steel_4130', 'nozzle_type': 'bell_80'}

    def kur():
        m = lre.LiquidRocketEngine(
            thrust=govde['thrust'], chamber_pressure=govde['chamber_pressure'],
            mixture_ratio=govde['mixture_ratio'], fuel_type='rp1',
            oxidizer_type='lox', cooling_type='ablative',
            injector_type='unlike_impinging',
            propellant_data={'rp1': {}, 'lox': {}}, overrides=dict(govde))
        m._skip_optimization_maps = True
        return m, m.calculate_performance()
    _m, r = _sessiz(kur)
    satirlar = {s['altitude']: s for s in r['altitude_performance']}
    for h in (0, 1000, 20000, 50000, 100000):
        s = satirlar[h]
        assert s['pressure'] * 1e5 == pytest.approx(_geo_pa(h), rel=1e-12), s
    # Ortam-eşlenik lüle (ε verilmedi): satırın lülesi satırın KENDİ
    # basıncında eşlenik (önceden lüle dönüşümsüz okumayla çözülüyordu).
    for h in (1000, 5000, 10000, 20000):
        s = satirlar[h]
        assert s['exit_pressure_bar'] == pytest.approx(s['pressure'],
                                                       rel=1e-9), s
    assert satirlar[0]['pressure'] == C.P_SEA_LEVEL_PA / 1e5


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


@pytest.mark.parametrize('h', IRTIFALAR_M + (-4999.0, 84852.0, 100000.0))
def test_b_irtifa_basinc_ucu(istemci, h):
    y = istemci.post('/api/altitude-to-pressure', json={'altitude': h},
                     headers=HOST)
    assert y.status_code == 200, y.get_json()
    j = y.get_json()
    assert j['pressure'] == pytest.approx(_geo_pa(h) / 1e5, rel=1e-12)
    assert j['temperature'] == pytest.approx(C.isa_temperature_geometric(h),
                                             rel=1e-12)


def test_b_irtifa_basinc_ucu_uzanti_rejimi_H_ile(istemci):
    """Tablo tepesi geopotansiyel 84 852 m = geometrik 85 987,4 m."""
    tepe_geom = (C.ISA_TABLE_TOP_M * C.ISA_GEOPOTENTIAL_EARTH_RADIUS_M
                 / (C.ISA_GEOPOTENTIAL_EARTH_RADIUS_M - C.ISA_TABLE_TOP_M))
    for h, uzanti in ((85500.0, False), (math.floor(tepe_geom), False),
                      (math.ceil(tepe_geom), True), (100000.0, True)):
        j = istemci.post('/api/altitude-to-pressure', json={'altitude': h},
                         headers=HOST).get_json()
        assert (j.get('model_regime')
                == 'isothermal_extension_above_table_top') is uzanti, (h, j)


def test_b_yorunge_cozuculeri_zaten_geometrik():
    """Yörünge çözücüsü bit düzeyinde aynı; 6-DOF aynı okumayı kendi
    yuvarlanmış R_AIR'iyle (287,053) yapar: bağıl ≤ 1e-6 (dönüşümsüz okuma
    20 km'de %1 uzakta olurdu)."""
    from hrma.analysis import six_dof_trajectory as sd
    from hrma.analysis.trajectory_analysis import TrajectoryAnalyzer
    ta = TrajectoryAnalyzer()
    for h in IRTIFALAR_M:
        assert ta._atm_full(h)[1] == pytest.approx(_geo_pa(h), rel=1e-12)
        assert sd._atmosphere_full(h)[2] == pytest.approx(_geo_pa(h),
                                                          rel=1e-6)


NODE = shutil.which('node')


@pytest.mark.skipif(NODE is None, reason='node yok')
def test_b_hibrit_formu_js_geometrik_okur():
    html = (KOK / 'hrma' / 'templates' / 'advanced.html').read_text(
        encoding='utf-8')
    blok = re.search(r'var ISA_LAYERS_JS = \[.*?var ISA_TABLE_TOP_M_JS = '
                     r'[0-9.]+;', html, re.S).group(0)
    parcalar = [blok]
    for ad in ('_isaLayerJS', '_isaPressurePaJS', 'altitudeToPressure'):
        m = re.search(r'\n\s*function %s\s*\(' % ad, html)
        i = html.index('{', m.end() - 1)
        d = 0
        for j in range(i, len(html)):
            d += {'{': 1, '}': -1}.get(html[j], 0)
            if d == 0:
                parcalar.append(html[m.start():j + 1])
                break
    kod = '\n'.join(parcalar) + (
        '\nconsole.log(JSON.stringify([0, 1000, 20000, 50000]'
        '.map(h => [h, altitudeToPressure(h)])));\n')
    cp = subprocess.run([NODE, '-'], input=kod, capture_output=True,
                        text=True, timeout=60)
    assert cp.returncode == 0, cp.stderr
    import json
    for h, p_bar in json.loads(cp.stdout):
        assert p_bar == pytest.approx(_geo_pa(h) / 1e5, rel=1e-12), h
        if h == 0:
            assert p_bar == C.isa_pressure(0.0) / 1e5


# ===========================================================================
# (c) r0 tek tanım
# ===========================================================================
_R0_DESEN = re.compile(r'(?<![0-9_.])6_?356_?766(?:\.0*)?(?![0-9_])')


def test_c_r0_literali_yalniz_merkezde_ve_capraz_denetli_on_yuz_ikizinde():
    bulunan = []
    for yol in sorted((KOK / 'hrma').rglob('*')):
        if yol.suffix not in ('.py', '.js', '.html') or not yol.is_file():
            continue
        for no, satir in enumerate(yol.read_text(encoding='utf-8').splitlines(),
                                   1):
            kod = satir.split('#', 1)[0] if yol.suffix == '.py' else \
                satir.split('//', 1)[0]
            if _R0_DESEN.search(kod):
                bulunan.append((yol.relative_to(KOK).as_posix(), kod.strip()))
    assert sorted(bulunan) == sorted([
        ('hrma/constants.py', 'ISA_GEOPOTENTIAL_EARTH_RADIUS_M = 6356766.0'),
        ('hrma/templates/advanced.html', 'var ISA_R0_JS = 6356766.0;'),
    ]), bulunan
    html = (KOK / 'hrma' / 'templates' / 'advanced.html').read_text(
        encoding='utf-8')
    m = re.search(r'var ISA_R0_JS = ([0-9.eE+-]+);', html)
    assert float(m.group(1)) == C.ISA_GEOPOTENTIAL_EARTH_RADIUS_M


def test_c_r0_okurlari_merkezin_ayni_nesnesi():
    from hrma.analysis import six_dof_trajectory as sd
    from hrma.analysis.trajectory_analysis import TrajectoryAnalyzer
    from hrma.engines import liquid_rocket_engine as lre
    from hrma.engines import solid_rocket_engine as sre
    r0 = C.ISA_GEOPOTENTIAL_EARTH_RADIUS_M
    assert TrajectoryAnalyzer().R_geopotential is r0
    assert sd.R_GEOPOTENTIAL is r0
    assert lre.ISA_GEOPOTENTIAL_EARTH_RADIUS_M is r0
    # Katı motor r0'ı hiç tutmaz; dönüşüm merkezî yardımcıdır.
    assert sre.geometric_to_geopotential is C.geometric_to_geopotential
    assert lre.geometric_to_geopotential is C.geometric_to_geopotential
