"""v3.0.1 / V301/K-A — katı motor geometrisi ve girdi kapıları (8 kalem).

Kalemler (``A-kati/RAPOR.md``; kanıt ``docs/scofield/raw/OH/V301/kati-sivi/
K-A/``): KT-01, KT-02, KT-03, KT-06, KT-13, KT-14, KT-20, KT-23.

Ana model kararları (22 Eki):
  * ``chamber_diameter`` DAİMA kasa iç çapıdır (``outer_diameter``
    gönderildiğinde); kural kasa >= tane + 2·(astar + yalıtım); sığmazsa
    422 ``grain_does_not_fit_case`` + gereken en küçük çap. Tek çaplı eski
    biçimde (``outer_diameter`` yok) değer tane çapı okunur, kasa türetilir
    ve ``case_bore`` künyesinde beyan edilir (karar A).
  * Aralık dışı / okunamaz girdi 200 + yerleşik değer DEĞİL, 422
    ``input_not_accepted``.
  * A_port,0 <= A_t her yolda RET (``port_smaller_than_throat``);
    varsayılan motor geçerli portlu (çekirdek 48 mm, tek kaynak).
"""
import contextlib
import inspect
import io
import json
import re
import subprocess
import warnings
from pathlib import Path

import pytest

from hrma.engines.solid_rocket_engine import (
    SOLID_CASE_FIT_RULE,
    SOLID_DEFAULT_GEOMETRY_MM,
    SOLID_DESIGN_POINT,
    SolidDesignRejected,
    SolidRocketEngine,
)

KOK = Path(__file__).resolve().parents[1]
SOLID_HTML = KOK / 'hrma' / 'templates' / 'solid.html'

#: Sayfa biçimi (outer_diameter gönderilir; astar 2 + yalıtım 3 mm sayfanın
#: kendi açılış değerleri). Kasa (chamber_diameter) gönderilmez = türetilir.
KA_SAYFA_GOVDESI = {
    'propellant_type': 'apcp', 'grain_type': 'bates',
    'outer_diameter': 100.0,
    'core_diameter': float(SOLID_DEFAULT_GEOMETRY_MM['core_diameter']),
    'grain_length': 500.0, 'chamber_pressure': 40.0,
    'liner_thickness': 2.0, 'insulation_thickness': 3.0,
}


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()), \
            warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return fn(*a, **kw)


@pytest.fixture(scope='module')
def istemci():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _post(istemci, **ek):
    govde = dict(KA_SAYFA_GOVDESI)
    for k, v in ek.items():
        if v is KeyError:
            govde.pop(k, None)
        else:
            govde[k] = v
    r = _sessiz(istemci.post, '/calculate_solid', json=govde)
    return r.status_code, (r.get_json() or {})


# ---------------------------------------------------------------------------
# KT-01 / KT-03 — kasa iç çapı kuralı
# ---------------------------------------------------------------------------
class TestKasaSigma:

    def test_esitlik_ozel_durumu_kalkti_ve_422(self, istemci):
        """Eski: 100/100 + 3 mm yalıtım -> kasa sessizce 106 mm, uyarısız."""
        kod, g = _post(istemci, chamber_diameter=100.0)
        assert kod == 422, g
        assert g['error_code'] == 'grain_does_not_fit_case'
        k = g['invalid_fields'][0]
        assert k['field'] == 'chamber_diameter'
        assert k['submitted'] == pytest.approx(100.0)
        # astar dahil: 100 + 2·(2 + 3)
        assert k['required_min'] == pytest.approx(110.0)
        assert k['rule'] == SOLID_CASE_FIT_RULE
        assert g['error'].startswith('No design was published')
        assert 'Enter at least 110.0 mm' in g['error']

    def test_onerilen_en_kucuk_cap_kapidan_gecer(self, istemci):
        kod, g = _post(istemci, chamber_diameter=104.3,
                       insulation_thickness=0.0, liner_thickness=2.17)
        assert kod == 422
        gereken = g['invalid_fields'][0]['required_min']
        assert gereken == pytest.approx(104.4)          # 104,34 -> yukarı
        kod2, g2 = _post(istemci, chamber_diameter=gereken,
                         insulation_thickness=0.0, liner_thickness=2.17)
        assert kod2 == 200, g2.get('error')
        assert g2['cad_design']['case_design']['inner_diameter'] == \
            pytest.approx(gereken)

    def test_sigan_beyan_aynen_kullanilir(self, istemci):
        kod, g = _post(istemci, chamber_diameter=120.0)
        assert kod == 200, g.get('error')
        assert g['cad_design']['case_design']['inner_diameter'] == \
            pytest.approx(120.0)
        assert g['case_bore']['case_inner_diameter_source'] == \
            'chamber_diameter'

    def test_bos_kasa_turetilir_ve_beyan_edilir(self, istemci):
        kod, g = _post(istemci)
        assert kod == 200, g.get('error')
        cb = g['case_bore']
        assert cb['case_inner_diameter_mm'] == pytest.approx(110.0)
        assert cb['case_inner_diameter_source'] == 'derived_from_grain'
        assert cb['grain_outer_diameter_source'] == 'outer_diameter'
        assert 'chamber_diameter was left empty' in cb['message']
        # Uç varsayılanı diye BEYAN EDİLMEZ (türetildi).
        alanlar = [d.get('field') for d in g.get('defaults_applied') or []]
        assert 'chamber_diameter' not in alanlar

    def test_bos_dize_kasa_da_turetilir(self, istemci):
        kod, g = _post(istemci, chamber_diameter='')
        assert kod == 200, g.get('error')
        assert g['case_bore']['case_inner_diameter_mm'] == \
            pytest.approx(110.0)

    def test_tek_cap_eski_bicim_beyanli(self, istemci):
        """Karar A: outer_diameter yoksa chamber_diameter tane çapıdır."""
        kod, g = _post(istemci, outer_diameter=KeyError,
                       chamber_diameter=100.0)
        assert kod == 200, g.get('error')
        cb = g['case_bore']
        assert cb['grain_outer_diameter_source'] == \
            'chamber_diameter_single_diameter_form'
        assert cb['grain_outer_diameter_mm'] == pytest.approx(100.0)
        assert cb['case_inner_diameter_mm'] == pytest.approx(110.0)
        assert ('outer_diameter was not supplied, so chamber_diameter'
                in cb['message'])
        assert 'grain outer diameter + 2 x (liner + insulation)' in \
            cb['message']

    def test_astar_radyal_yer_kaplar(self, istemci):
        """KT-03: 60 mm astarlı tane 3 mm boşluğa 'sığıyordu'."""
        kod, g = _post(istemci, liner_thickness=60.0, chamber_diameter=110.0)
        assert kod == 422
        assert g['invalid_fields'][0]['required_min'] == pytest.approx(226.0)
        kod2, g2 = _post(istemci, liner_thickness=5.0)
        assert kod2 == 200, g2.get('error')
        assert g2['cad_design']['case_design']['inner_diameter'] == \
            pytest.approx(100.0 + 2 * (5.0 + 3.0))

    def test_motor_kapisi_tasarim_noktasi_sonrasi_da_sinar(self):
        """Kurucu kapısı doğrudan Python API'de de RET verir."""
        with pytest.raises(SolidDesignRejected) as exc:
            _sessiz(SolidRocketEngine, chamber_diameter=100,
                    overrides={'outer_diameter': 100})
        assert exc.value.code == 'grain_does_not_fit_case'


# ---------------------------------------------------------------------------
# KT-02 — motor dış çapı tek kaynaktan
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('ek', [
    {},                                                   # türetilen kasa
    {'chamber_diameter': 150.0},                          # beyan edilen kasa
    {'outer_diameter': KeyError, 'chamber_diameter': 100.0},  # tek çap
])
def test_ozet_motor_dis_capi_cad_ile_ayni(istemci, ek):
    kod, g = _post(istemci, **ek)
    assert kod == 200, g.get('error')
    kd = g['design_summary']['key_dimensions']
    cad = g['cad_design']['case_design']
    assert kd['motor_outer_diameter_mm'] == pytest.approx(
        cad['outer_diameter'], rel=1e-12)
    assert kd['motor_outer_diameter_mm'] == pytest.approx(
        cad['inner_diameter'] + 2 * cad['wall_thickness'], rel=1e-12)


# ---------------------------------------------------------------------------
# KT-06 / KT-13 — aralık dışı girdi 422 (yerleşik değer yok)
# ---------------------------------------------------------------------------
#: (alan, değer, beklenen gerekçe kodu, kabul aralığı)
ARALIK_DISI = [
    ('combustion_efficiency', 0.3, 'out_of_accepted_range', [0.5, 1.0]),
    ('combustion_efficiency', 5, 'out_of_accepted_range', [0.5, 1.0]),
    ('combustion_efficiency', 1.0735, 'out_of_accepted_range', [0.5, 1.0]),
    ('cf_efficiency', 1.07, 'out_of_accepted_range', [0.8, 1.0]),
    ('discharge_coeff', 1.1, 'out_of_accepted_range', [0.7, 1.0]),
    ('nozzle_efficiency', 1.11, 'out_of_accepted_range', [0.8, 1.0]),
    ('kinetic_efficiency', 1.09, 'out_of_accepted_range', [0.8, 1.0]),
    ('safety_factor', 0.5, 'out_of_accepted_range', [1.1, 10.0]),
    ('safety_factor', -1, 'out_of_accepted_range', [1.1, 10.0]),
    ('grain_count', 0, 'out_of_accepted_range', None),
    ('grain_count', -2, 'out_of_accepted_range', None),
    ('grain_count', 2.5, 'not_a_whole_number', None),
    ('initial_temp', 500, 'out_of_accepted_range', [200.0, 350.0]),
    ('insulation_thickness', -3, 'out_of_accepted_range', [0.0, 100.0]),
    ('yield_strength', -250, 'out_of_accepted_range', [10.0, 3000.0]),
    ('density', -1800, 'out_of_accepted_range', [500.0, 3000.0]),
    ('gamma', 0.9, 'out_of_accepted_range', [1.05, 1.5]),
    ('divergent_angle', 90, 'out_of_accepted_range', [5.0, 45.0]),
    ('convergent_angle', -15, 'out_of_accepted_range', [10.0, 80.0]),
    ('closure_bolt_count', 500, 'out_of_accepted_range', None),
    ('nozzle_efficiency', True, 'boolean_is_not_a_number', [0.8, 1.0]),
    ('density', 'abc', 'not_a_number', [500.0, 3000.0]),
    ('combustion_efficiency', '0,9', 'not_a_number', [0.5, 1.0]),
]


@pytest.mark.parametrize('alan,deger,gerekce,aralik', ARALIK_DISI)
def test_aralik_disi_girdi_tasarimi_yayimlamaz(istemci, alan, deger,
                                               gerekce, aralik):
    kod, g = _post(istemci, **{alan: deger})
    assert kod == 422, (alan, deger, str(g)[:200])
    assert g['error_code'] == 'input_not_accepted'
    assert g['status'] == 'invalid_input'
    assert 'average_thrust' not in g and 'specific_impulse' not in g
    kayit = [k for k in g['invalid_fields'] if k['field'] == alan]
    assert kayit, g['invalid_fields']
    assert kayit[0]['reason'] == gerekce
    if aralik is not None:
        assert kayit[0]['accepted_range'] == pytest.approx(aralik)
    assert 'unit' in kayit[0]
    assert alan in g['error']


def test_coklu_red_tum_alanlari_birlikte_soyler(istemci):
    kod, g = _post(istemci, combustion_efficiency=5, safety_factor=0.5,
                   grain_count=2.5, initial_temp=500)
    assert kod == 422
    alanlar = {k['field'] for k in g['invalid_fields']}
    assert alanlar == {'combustion_efficiency', 'safety_factor',
                       'grain_count', 'initial_temp'}
    assert g['error'].startswith('No design was published: 4 input(s)')


def test_kasa_turetme_biciminde_okunamaz_tane_capi_422(istemci):
    kod, g = _post(istemci, outer_diameter='abc')
    assert kod == 422
    assert g['invalid_fields'][0]['field'] == 'outer_diameter'
    assert g['invalid_fields'][0]['reason'] == 'not_a_number'


def test_bant_icindeki_deger_hala_uygulanir(istemci):
    kod, g = _post(istemci, combustion_efficiency=0.9)
    assert kod == 200, g.get('error')
    ca = g['advanced_performance']['combustion_analysis']
    assert ca['combustion_efficiency_percent'] == pytest.approx(90.0)


def test_eski_400_retleri_degismedi(istemci):
    """Mevcut bant kapıları (çekirdek alt ucu, basınç) 400 kalır."""
    kod, g = _post(istemci, core_diameter=2.0)
    assert kod == 400, g
    kod, g = _post(istemci, chamber_pressure=1000.0)
    assert kod == 400, g


# ---------------------------------------------------------------------------
# KT-14 — çekirdek taneye sığmalı
# ---------------------------------------------------------------------------
def test_cekirdek_tane_capini_asarsa_422(istemci):
    """Eski: çekirdek 60 / tane 50 -> HTTP 200 + 'Invalid grain geometry'."""
    kod, g = _post(istemci, core_diameter=60.0, outer_diameter=50.0)
    assert kod == 422
    assert g['error_code'] == 'core_too_large_for_grain'
    k = g['invalid_fields'][0]
    assert k['field'] == 'core_diameter'
    assert k['max_allowed'] == pytest.approx(45.0)
    assert k['minimum_web_mm'] == pytest.approx(2.5)


def test_en_buyuk_izinli_cekirdek_kapidan_gecer(istemci):
    kod, g = _post(istemci, core_diameter=45.0, outer_diameter=50.0)
    assert g.get('error_code') != 'core_too_large_for_grain', g


def test_motor_kapisi_cekirdegi_taneye_karsi_sinar():
    with pytest.raises(SolidDesignRejected) as exc:
        _sessiz(SolidRocketEngine, chamber_diameter=100, core_diameter=60,
                overrides={'outer_diameter': 50, 'chamber_diameter': ''})
    assert exc.value.code == 'core_not_inside_grain'


def test_cozucunun_hata_sozlugu_200_ile_yayimlanmaz(istemci, monkeypatch):
    """Çözücü yanma yüzeyi bulamazsa (``error`` sözlüğü) -> 422."""
    from hrma.engines import solid_rocket_engine as m
    monkeypatch.setattr(
        m.SolidRocketEngine, 'calculate_performance',
        lambda self: {'error': 'Invalid grain geometry',
                      'error_i18n': {'code': 'warn.solid.invalid_grain_'
                                             'geometry'}})
    kod, g = _post(istemci)
    assert kod == 422
    assert g['error_code'] == 'invalid_grain_geometry'
    assert {k['field'] for k in g['invalid_fields']} == {
        'core_diameter', 'outer_diameter'}


# ---------------------------------------------------------------------------
# KT-23 — port boğazdan küçükse RET
# ---------------------------------------------------------------------------
def test_port_bogazdan_kucukse_422_ve_gereken_cekirdek(istemci):
    kod, g = _post(istemci, core_diameter=10.0)
    assert kod == 422
    assert g['error_code'] == 'port_smaller_than_throat'
    k = g['invalid_fields'][0]
    assert k['port_to_throat_area_ratio'] <= 1.0
    gereken = k['required_min']
    assert gereken is not None and gereken > 10.0
    kod2, g2 = _post(istemci, core_diameter=gereken)
    assert kod2 == 200, g2.get('error')
    # 1 < oran < 2 bandının uyarısı aynen kalır.
    kodlar = {w['code'] for w in g2['design_warnings']}
    assert 'warn.solid.port_to_throat_low' in kodlar


def test_port_kapisi_dogrudan_motorda_da_gecerli():
    e = _sessiz(SolidRocketEngine, chamber_diameter=100, grain_length=500,
                core_diameter=30, chamber_pressure=40)
    with pytest.raises(SolidDesignRejected) as exc:
        _sessiz(e.calculate_performance)
    assert exc.value.code == 'port_smaller_than_throat'
    # V301/T-ÇAPA-A: N-CEA-2 (katı termokimya motorun Pc'sinde NASA CEA'dan) sonrası yeniden
    # ölçüldü: 0,947 -> 0,94975 (c* değişti, boğaz onunla). CEA kapalı aynı
    # motor 0,947 bandında kalır. Tolerans aynı.
    assert exc.value.invalid_fields[0]['port_to_throat_area_ratio'] == \
        pytest.approx(0.9497, abs=0.002)


# ---------------------------------------------------------------------------
# KT-20 — varsayılanlar tek kaynaktan ve çelişkisiz
# ---------------------------------------------------------------------------
def _html_degeri(html, alan):
    m = re.search(r'<input[^>]*\bid="%s"[^>]*>' % alan, html)
    assert m, alan
    v = re.search(r'\bvalue="([^"]*)"', m.group(0))
    return v.group(1) if v else None


def test_varsayilan_geometri_tek_kaynak():
    from hrma.app import SOLID_ENDPOINT_DEFAULTS
    for ad in ('chamber_diameter', 'grain_length', 'core_diameter'):
        assert SOLID_ENDPOINT_DEFAULTS[ad] == SOLID_DEFAULT_GEOMETRY_MM[ad]
    imza = inspect.signature(SolidRocketEngine.__init__).parameters
    for ad in ('chamber_diameter', 'grain_length', 'core_diameter'):
        assert imza[ad].default == SOLID_DEFAULT_GEOMETRY_MM[ad], ad
    html = SOLID_HTML.read_text(encoding='utf-8')
    assert float(_html_degeri(html, 'outer_diameter')) == \
        SOLID_DEFAULT_GEOMETRY_MM['chamber_diameter']
    assert float(_html_degeri(html, 'grain_length')) == \
        SOLID_DEFAULT_GEOMETRY_MM['grain_length']
    assert float(_html_degeri(html, 'core_diameter')) == \
        SOLID_DEFAULT_GEOMETRY_MM['core_diameter']
    # Türetilen / kaynaksız alanlar BOŞ açılır.
    for ad in ('chamber_diameter', 'chamber_volume', 'erosion_factor',
               'web_thickness'):
        assert _html_degeri(html, ad) == '', ad
        assert "%s: solOptNum('%s')" % (ad, ad) in html, ad


@pytest.mark.parametrize('govde', [
    'sayfa',
    'eski_api',
])
def test_varsayilan_motor_port_bogaz_en_az_iki(istemci, govde):
    if govde == 'sayfa':
        kod, g = _post(istemci)
    else:
        from hrma.app import SOLID_ENDPOINT_DEFAULTS
        r = _sessiz(istemci.post, '/calculate_solid',
                    json=dict(SOLID_ENDPOINT_DEFAULTS))
        kod, g = r.status_code, r.get_json()
    assert kod == 200, g.get('error')
    kodlar = {w['code'] for w in g['design_warnings']}
    assert 'warn.solid.port_to_throat_low' not in kodlar
    assert 'warn.solid.initial_mass_flux_high' not in kodlar
    assert 'warn.solid.case_volume_inconsistent' not in kodlar
    assert 'warn.solid.throat_erosion_coeff_off_band' not in kodlar
    e = _sessiz(SolidRocketEngine)
    assert e._port_throat_ratio_at_core(e.D_core) >= \
        SOLID_DESIGN_POINT['port_to_throat_min']


# ---------------------------------------------------------------------------
# 422 metni ekranda: tek çözücü + TR deseni
# ---------------------------------------------------------------------------
def test_sayfa_ret_govdesini_ortak_cozucuyle_basar():
    html = SOLID_HTML.read_text(encoding='utf-8')
    govde = re.search(r'async function calculateSolid\(\)(.*?)\n        \}\n',
                      html, re.S).group(1)
    assert '_solidRetMetni(results, response.status)' in govde
    assert '!response.ok' in govde
    yardimci = re.search(r'function _solidRetMetni\((.*?)\n        \}\n',
                         html, re.S).group(1)
    assert 'HRMAReject.metni' in yardimci
    assert 'serverText' in yardimci


def _ret_cumleleri(istemci):
    vakalar = (
        {'chamber_diameter': 100.0},
        {'combustion_efficiency': 5, 'safety_factor': 0.5,
         'grain_count': 2.5, 'initial_temp': 500, 'density': 'abc',
         'nozzle_efficiency': True},
        {'core_diameter': 60.0, 'outer_diameter': 50.0},
        {'core_diameter': 10.0},
    )
    out = []
    for ek in vakalar:
        kod, g = _post(istemci, **ek)
        assert kod == 422, (ek, g)
        out.append(g['error'])
    # Motor ayağının cümlesi (doğrudan API; uçta imalat payı kapısı önce
    # ateşlendiği için bu cümle uçtan gelmez).
    with pytest.raises(SolidDesignRejected) as exc:
        _sessiz(SolidRocketEngine, chamber_diameter=100, core_diameter=60,
                overrides={'outer_diameter': 50, 'chamber_diameter': ''})
    out.append(str(exc.value))
    return out


from tests.test_app_hata_dili import (  # noqa: E402
    NODE, NODE_DUZENEGI, STATIC_JS, TURKCE_KARAKTER, needs_node)


@needs_node
def test_ret_cumleleri_turkcede_kesilmeden_cevrilir(istemci, tmp_path):
    cumleler = _ret_cumleleri(istemci)
    duzenek = tmp_path / 'srv.js'
    duzenek.write_text(NODE_DUZENEGI, encoding='utf-8')
    girdi = tmp_path / 'in.json'
    girdi.write_text(json.dumps(cumleler), encoding='utf-8')
    islem = subprocess.run(
        [NODE, str(duzenek), str(STATIC_JS), str(girdi)],
        capture_output=True, text=True, timeout=120)
    assert islem.returncode == 0, islem.stderr
    sonuc = json.loads(islem.stdout)
    assert sonuc['en'] == cumleler, 'EN kipinde metin değişti'
    for kaynak, tr in zip(cumleler, sonuc['tr']):
        assert tr != kaynak and TURKCE_KARAKTER.search(tr), (
            'çevrilmedi: %s' % kaynak)
        assert tr.startswith('Tasarım yayımlanmadı'), tr
    # Ondalık kanonu: 110.0 -> 110,0 ; alan adları korunur.
    assert '110,0 mm' in sonuc['tr'][0] and '110.0' not in sonuc['tr'][0]
    assert 'combustion_efficiency' in sonuc['tr'][1]
    assert 'tam sayı değil' in sonuc['tr'][1]
    assert 'sayı değil' in sonuc['tr'][1]
