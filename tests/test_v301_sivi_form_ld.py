"""V301/L-D — sıvı formu bekçileri (SV-04, SV-09, SV-12, SV-16, SV-17, NK-59,
NK-64, L-A DEVİR 2).

Kanıt ve önce/sonra ölçümleri: docs/scofield/raw/OH/V301/kati-sivi/L-D/.
"""
import copy
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from hrma.app import app

KOK = Path(__file__).resolve().parents[1]
LIQ = KOK / 'hrma' / 'templates' / 'liquid.html'
PAGES = KOK / 'hrma' / 'static' / 'js' / 'i18n_pages.js'
HOST = {'Host': '127.0.0.1:8080'}


def _html():
    return LIQ.read_text(encoding='utf-8')


def _toplayici_govdesi(html):
    a = html.index('function collectAllParameters()')
    govde = html[a:html.index('\n            };', a)]
    # yorum satırları (eski kalıbın tarihçesi) kod değildir
    return '\n'.join(s for s in govde.split('\n')
                     if not s.strip().startswith('//'))


def _fn(html, ad):
    a = html.index('function %s(' % ad)
    derinlik, i = 0, html.index('{', a)
    while True:
        if html[i] == '{':
            derinlik += 1
        elif html[i] == '}':
            derinlik -= 1
            if derinlik == 0:
                return html[a:i + 1]
        i += 1


@pytest.fixture(scope='module')
def istemci():
    return app.test_client()


# ---------------------------------------------------------------------------
# SV-04 — boş alan gizli sayı göndermez
# ---------------------------------------------------------------------------
def test_toplayicida_gizli_sayi_kalibi_yok():
    govde = _toplayici_govdesi(_html())
    kalip = re.findall(r"\|\|\s*[0-9.]+", govde)
    assert not kalip, 'collectAllParameters gizli sayı gönderiyor: %s' % kalip
    assert 'parseFloat(document.getElementById' not in govde
    # sayı alanlarının hepsi "boşsa gönderme" okuyucusundan geçer
    assert govde.count("liqOptNum('") >= 30


def test_bos_alanlarin_cozucu_varsayilani_adiyla_beyan(istemci):
    from hrma.app import _SIVI_BEYANLI_VARSAYILAN_OKUYUCULARI
    assert set(_SIVI_BEYANLI_VARSAYILAN_OKUYUCULARI) == {
        'engine_life_cycles', 'of_min', 'of_max'}
    govde = {'thrust': 10000, 'chamber_pressure': 100, 'mixture_ratio': 2.5,
             'fuel_type': 'rp1', 'oxidizer_type': 'lox',
             'engine_cycle': 'gas_generator'}
    r = istemci.post('/calculate_liquid', json=govde, headers=HOST)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    j = r.get_json()
    kunye = {k['field']: k for k in j.get('defaults_applied') or []}
    for alan in ('engine_life_cycles', 'of_min', 'of_max'):
        assert alan in kunye and kunye[alan]['reason'] == 'endpoint_default'
    assert kunye['engine_life_cycles']['value'] == j['structural_analysis'][
        'design_requirements']['thermal_cycles']
    # boş kaynama noktası: denetim yapılmadı, sessiz değil
    kodlar = {w.get('code') for w in j.get('input_warnings') or []}
    assert 'warn.liquid.coolant_boiling_check_not_evaluated' in kodlar
    assert 'warn.liquid.coolant_exit_above_boiling' not in kodlar
    # SV-12: besleme hattı malzeme metni hesabın kullandığı borudan
    from hrma.data.materials_db import get_material_safe
    boru = j['detailed_feed_system']['valve_feedline']['fuel_line'][
        'pipe_structural_material']
    kayit, anahtar = get_material_safe(boru)
    for hat in ('fuel_main', 'oxidizer_main'):
        blok = j['feed_system']['feed_lines'][hat]
        assert blok['material'] == kayit['name']
        assert blok['material_key'] == anahtar


# ---------------------------------------------------------------------------
# SV-09 — formda görünen her girdi ya hesabı değiştirir ya adıyla beyanlıdır
# ---------------------------------------------------------------------------
def _form_kimlikleri(html):
    a = html.index('<!-- 1. Propellant Data -->')
    b = html.index('<!-- Calculate Button -->')
    return set(re.findall(r'<(?:input|select)[^>]*\bid="([a-z_0-9]+)"',
                          html[a:b]))


def test_formda_cozucunun_okumadigi_girdi_yok():
    from hrma.engines.liquid_rocket_engine import LiquidRocketEngine
    html = _html()
    katalog = LiquidRocketEngine.unwired_inputs(None)
    olu = set(katalog['informational']) | set(katalog['transient_not_modelled'])
    kimlikler = _form_kimlikleri(html)
    # gimbal paneli girdileri formdadır ama motora GİTMEZ
    govde = _toplayici_govdesi(html)
    for alan in ('engine_mount', 'gimbal_range'):
        assert alan in kimlikler
        assert re.search(r'^\s+%s:' % alan, govde, re.M) is None
    assert not ((kimlikler - {'engine_mount', 'gimbal_range'}) & olu), sorted(
        (kimlikler - {'engine_mount', 'gimbal_range'}) & olu)
    # karşılaştırma girdileri hesaptan ÖNCE işaretli ve boş açılır
    m = re.search(r'const UNWIRED_INPUT_IDS = \[(.*?)\];', html, re.S)
    statik = set(re.findall(r"'([a-z_]+)'", m.group(1)))
    # koşullu karşılaştırma alanları (turbine_inlet_pressure: yalnız
    # genişleme oranı da verilmişse; contraction_ratio: yalnız oda çapı
    # verilmişse) hesaptan önce işaretlenmez — hükmü gövde verir.
    assert statik == set(katalog['reported_for_comparison']) - {
        'turbine_inlet_pressure', 'contraction_ratio'}
    for alan in statik:
        etiket = re.search(r'<input[^>]*\bid="%s"[^>]*>' % alan, html).group(0)
        assert 'value=""' in etiket, alan


def test_beyan_yalniz_gonderilen_alanlari_adlandirir():
    from hrma.engines.liquid_rocket_engine import LiquidRocketEngine

    class _M:
        overrides = {'engine_start_time': 2.0, 'throat_diameter': 50,
                     'engine_shutdown_time': ''}
        engine_cycle = 'gas_generator'
    beyan = LiquidRocketEngine.unwired_inputs(_M())
    assert beyan['transient_not_modelled'] == ['engine_start_time']
    assert beyan['informational'] == []
    assert beyan['reported_for_comparison'] == ['throat_diameter']
    tam = LiquidRocketEngine.unwired_inputs(None)
    assert 'engine_shutdown_time' in tam['transient_not_modelled']


# ---------------------------------------------------------------------------
# L-A DEVİR 2 — turbopompalı çevrimde feed_pressure gizli ve gönderilmez
# ---------------------------------------------------------------------------
def test_feed_pressure_turbopompali_cevrimlerde_gizli():
    html = _html()
    a = html.index('const LIQ_CYCLE_UNREAD_FIELDS = {')
    blok = html[a:html.index('};', a)]
    for cevrim in ('gas_generator', 'staged_combustion', 'full_flow_staged',
                   'expander', 'tap_off'):
        assert re.search(r"%s: \['feed_pressure'\]" % cevrim, blok), cevrim
    assert 'feed_pressure' not in re.search(r'pressure_fed: \[([^\]]*)\]',
                                            blok).group(1)


# ---------------------------------------------------------------------------
# SV-16 — ipuçlarındaki kabul aralıkları çözücünün TEK bant tablosundan
# ---------------------------------------------------------------------------
IPUCU_ANAHTARLARI = {
    'throat_diameter': 'liq.ui.diameter_at_nozzle_throat_minimum_area',
    'fuel_injection_velocity': 'liq.ui.fuel_velocity_at_injection_higher_velocity',
    'oxidizer_injection_velocity': 'liq.ui.oxidizer_velocity_at_injection_typically_higher',
    'fuel_orifice_diameter': 'liq.ui.diameter_of_fuel_injection_orifices_smaller',
    'oxidizer_orifice_diameter': 'liq.ui.diameter_of_oxidizer_injection_orifices_sized',
    'target_thrust_to_weight': 'liq.ui.engine_thrust_divided_by_engine_mass',
    'injector_pressure_drop': 'liq.ui.pressure_drop_across_injector_as_percentage',
    'feed_pressure': 'liq.ui.pressure_at_turbopump_exit_or_tank',
    'fuel_heat_capacity': 'liq.ui.fuel_specific_heat_capacity_important_for',
    'fuel_boiling_point': 'liq.ui.fuel_boiling_point_at_1_atm',
    'max_burn_duration': 'liq.ui.maximum_continuous_operation_time_limited_by',
    'feed_line_diameter_mm': 'liq.ui.feed_line_diameter_tip',
}


@pytest.mark.parametrize('alan', sorted(IPUCU_ANAHTARLARI))
def test_ipucu_kabul_araligi_bant_tablosuyla_ayni(alan):
    from hrma.engines.liquid_rocket_engine import LIQUID_INPUT_BANDS
    lo, hi, _etiket, _birim = LIQUID_INPUT_BANDS[alan]
    anahtar = IPUCU_ANAHTARLARI[alan]
    pages = PAGES.read_text(encoding='utf-8')
    metinler = re.findall(r"'" + re.escape(anahtar) + r"':\s*'((?:[^'\\]|\\.)*)'",
                          pages)
    assert len(metinler) == 2
    en, tr = metinler
    sablon = re.search(r'data-i18n="' + re.escape(anahtar) + r'">([^<]*)<',
                       _html()).group(1)
    aralik_en = '%g-%g' % (lo, hi)
    aralik_tr = aralik_en.replace('.', ',')
    assert ('Accepted ' + aralik_en) in en, (alan, en[-120:])
    assert ('Accepted ' + aralik_en) in sablon, alan
    assert ('Kabul aralığı ' + aralik_tr) in tr, (alan, tr[-120:])
    etiket = re.search(r'<input[^>]*\bid="%s"[^>]*>' % alan, _html()).group(0)
    assert re.search(r'\bmin="%g"' % lo, etiket), etiket
    assert re.search(r'\bmax="%g"' % hi, etiket), etiket


def test_ipuclarinda_http_kodu_ve_api_anahtari_yok():
    pages = PAGES.read_text(encoding='utf-8')
    for anahtar in ('liq.ui.combustion_chamber_operating_pressure_higher_pre',
                    'liq.ui.target_thrust_level_for_the_liquid',
                    'liq.ui.mass_ratio_of_oxidizer_to_fuel',
                    'liq.ui.feed_line_diameter_tip'):
        for metin in re.findall(r"'" + re.escape(anahtar)
                                + r"':\s*'((?:[^'\\]|\\.)*)'", pages):
            assert '422' not in metin and 'incomplete_input' not in metin
            assert 'feed_line_area_m2' not in metin
            assert '5.5-6.0' not in metin and '3.6-3.8' not in metin


# ---------------------------------------------------------------------------
# SV-17 / SV-12 — kart yoğunluğu ve kamara malzemesi tek kaynaktan
# ---------------------------------------------------------------------------
def test_sayfa_kaydi_motorun_tablosundan(istemci):
    from hrma.app import _sivi_form_kaydi
    from hrma.engines.liquid_rocket_engine import (
        CHAMBER_MATERIAL_MAP, LIQUID_PROPELLANT_REFERENCE_TABLE)
    kayit = _sivi_form_kaydi()
    assert kayit['table_densities']['fuel']['rp1'] == \
        LIQUID_PROPELLANT_REFERENCE_TABLE[('rp1', 'lox')]['density_fuel']
    assert [o['value'] for o in kayit['chamber_material']['options']] == \
        list(CHAMBER_MATERIAL_MAP)
    sayfa = istemci.get('/liquid', headers=HOST).get_data(as_text=True)
    sec = sayfa[sayfa.index('<select id="chamber_material"'):]
    sec = sec[:sec.index('</select>')]
    assert re.findall(r'<option value="([a-z_0-9]+)"', sec) == \
        list(CHAMBER_MATERIAL_MAP)
    assert 'cucrzr' in sec
    # ham şablonda elle yazılmış seçenek yok
    ham = _html()
    ham_sec = ham[ham.index('<select id="chamber_material"'):]
    ham_sec = ham_sec[:ham_sec.index('</select>')]
    assert 'value="steel_304"' not in ham_sec


def test_kartta_kategori_yedegi_yogunluk_basilmiyor():
    html = _html()
    # kart, hâl çözümü yoksa hesabın tablo değerini (liqTableDensity) basar
    assert html.count("liqTableDensity('fuel', fuelType)") >= 2
    assert "liqTableDensity('oxidizer', oxType)" in html
    # NK-41: okunmaz satır içi açık zemin yok
    assert "'#fff3cd'" not in html


# ---------------------------------------------------------------------------
# NK-59 — yakıt değişince başka yakıtın değeri kalmaz (node, gerçek işlev)
# ---------------------------------------------------------------------------
node_gerekli = pytest.mark.skipif(shutil.which('node') is None,
                                  reason='node yok')


@node_gerekli
def test_yakit_degisince_bayat_alanlar_silinir():
    html = _html()
    kod = '\n'.join([
        re.search(r'const LIQ_FUEL_DEPENDENT_FIELDS = \[[^\]]*\];', html).group(0),
        _fn(html, 'liquidAutofillBayragi'),
        _fn(html, 'liqClearStaleFuelFields'),
    ])
    betik = r"""
const ogeler = {};
function oge(id) {
  if (!(id in ogeler)) ogeler[id] = { id: id, value: '', _a: {}, textContent: '', style: {},
    parentNode: { appendChild() {} },
    setAttribute(a, v) { this._a[a] = String(v); }, removeAttribute(a) { delete this._a[a]; },
    getAttribute(a) { return (a in this._a) ? this._a[a] : null; } };
  return ogeler[id];
}
global.document = { getElementById: oge, querySelector: () => null,
  createElement: () => oge('__not__' + Math.random()) };
function TF(k, p, f) { return f.replace('{fields}', p.fields); }
%s
oge('fuel_boiling_point').value = '500'; oge('fuel_boiling_point').setAttribute('data-hrma-owner', 'restored:rp1');
oge('fuel_heat_capacity').value = '2090'; oge('fuel_heat_capacity').setAttribute('data-hrma-owner', 'user:rp1');
oge('fuel_viscosity').value = '0.0012'; oge('fuel_viscosity').setAttribute('data-hrma-owner', 'restored:methane');
const silinen = liqClearStaleFuelFields('methane');
process.stdout.write(JSON.stringify({ silinen: silinen,
  kaynama: oge('fuel_boiling_point').value, cp: oge('fuel_heat_capacity').value,
  visk: oge('fuel_viscosity').value }));
""" % kod
    sonuc = subprocess.run([shutil.which('node'), '-e', betik],
                           capture_output=True, text=True, timeout=30)
    assert sonuc.returncode == 0, sonuc.stderr[:800]
    o = json.loads(sonuc.stdout)
    assert o['kaynama'] == '' and o['cp'] == ''
    assert o['visk'] == '0.0012', 'aynı yakıta ait değer silinmemeli'
    assert len(o['silinen']) == 2


# ---------------------------------------------------------------------------
# NK-64 — zorunlu alan reddi alanı kod adı + kullanıcı adıyla anar
# ---------------------------------------------------------------------------
def test_zorunlu_alan_reddi_kullanici_adini_tasir(istemci):
    r = istemci.post('/calculate_liquid', json={
        'chamber_pressure': 100, 'mixture_ratio': 2.5, 'fuel_type': 'rp1',
        'oxidizer_type': 'lox'}, headers=HOST)
    assert r.status_code == 422
    alanlar = r.get_json()['invalid_fields']
    assert alanlar[0]['field'] == 'thrust'
    assert alanlar[0]['label'] == 'Thrust (N)'


def test_ret_sayfada_alan_adi_ve_kaydirma():
    html = _html()
    fn = _fn(html, '_liquidRetAlanNotlari')
    assert 'scrollIntoView' in fn and "label[for=\"' + k.field" in fn
    assert "liq.msg.reject_fields_named" in html
    pages = PAGES.read_text(encoding='utf-8')
    for anahtar in ('liq.msg.reject_fields_named', 'liq.msg.reject_field_required',
                    'liq.msg.reject_field_range'):
        assert pages.count("'%s':" % anahtar) == 2, anahtar
