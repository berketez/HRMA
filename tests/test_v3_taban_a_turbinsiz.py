"""V3 taban-a (14 Eki 2026) — türbinsiz çevrimde türbin alanları bekçisi.

KAB devri (kabul brifi ``docs/kabul/cowork_brif_v3_0.md`` N7; ölçüm
``docs/kabul/kanit_2026-10-14/taze.json`` ``ek_sivi_eps5``): sıvı sayfasının
FORM yolu türbin alanlarının varsayılanlarını (150 bar / 4) basınç
beslemeli çevrimde de gönderiyordu ve motor türbini OLMAYAN bu çevrimde
'warn.liquid.turbine_pr_inconsistent' basıyordu.

Karar (brif): türbinsiz çevrimde türbin alanları DEĞERLENDİRİLMEZ ve
gönderildilerse kullanılmadıkları ADIYLA beyan edilir (sessizce yutulmaz);
türbinli çevrimlerde uyarı AYNEN kalır. Yayımlanan hiçbir sayı değişmez.

Kâhin: basınç beslemeli çevrimde türbin yoktur (Sutton & Biblarz 9th ed.
Böl. 6 ⟷ 10; Huzel & Huang Böl. 1); A1b sivi-kati-form CW-F1 ölçümü
(``docs/scofield/raw/OH/A1b/sivi-kati-form/a1/once/cevrim_alan_tablosu.json``):
bu iki alan basınç beslemede uyarı dışında HİÇBİR yaprağı oynatmıyordu.
"""

import json

import pytest

from hrma.engines.liquid_rocket_engine import (
    LiquidRocketEngine,
    TURBINE_INPUT_FIELDS,
    TURBINE_INPUT_UNUSED_REASON,
)
from tests.support.form_defaults import sayisal_varsayilanlar

#: KAB ek_sivi_eps5 vakası (taze.py ile aynı gövde).
EK_EPS5 = {
    'fuel_type': 'rp1', 'oxidizer_type': 'lox', 'thrust': 25000.0,
    'chamber_pressure': 30.0, 'mixture_ratio': 2.4,
    'engine_cycle': 'pressure_fed', 'feed_pressure': 60.0,
    'cooling_type': 'ablative', 'chamber_material': 'steel_316',
    'nozzle_type': 'bell_80', 'nozzle_expansion_ratio': 5.0,
    'max_burn_duration': 60.0,
}
ESKI_UYARI = 'warn.liquid.turbine_pr_inconsistent'
YENI_UYARI = 'warn.liquid.turbine_input_not_used_pressure_fed'
#: Beyan ve uyarı kanalları dışında hiçbir yaprak değişmemeli.
BEYAN_ANAHTARLARI = ('input_warnings', 'inputs_not_used', 'unwired_inputs')


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _govde(cevrim, turbin=True):
    g = dict(sayisal_varsayilanlar('liquid'))
    g.update(EK_EPS5)
    g['engine_cycle'] = cevrim
    if not turbin:
        for alan in TURBINE_INPUT_FIELDS:
            g.pop(alan, None)
    return g


def _post(istemci, govde):
    r = istemci.post('/calculate_liquid', json=govde)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


def _kodlar(yanit):
    return [w.get('code') for w in yanit.get('input_warnings', [])
            if isinstance(w, dict)]


def _duz(d, on=''):
    if isinstance(d, dict):
        for k, v in d.items():
            yield from _duz(v, f'{on}.{k}' if on else k)
    elif isinstance(d, list):
        for i, v in enumerate(d):
            yield from _duz(v, f'{on}[{i}]')
    else:
        yield on, d


@pytest.fixture(scope='module')
def yanitlar(istemci):
    return {
        'pf_ile': _post(istemci, _govde('pressure_fed', True)),
        'pf_olmadan': _post(istemci, _govde('pressure_fed', False)),
        'gg_ile': _post(istemci, _govde('gas_generator', True)),
    }


def test_form_varsayilanlari_turbin_alanlarini_gonderiyor():
    """Önerme: FORM yolu iki türbin alanını gerçekten gönderiyor."""
    g = _govde('pressure_fed', True)
    for alan in TURBINE_INPUT_FIELDS:
        assert alan in g, alan


def test_basinc_beslemede_turbin_uyarisi_basilmaz(yanitlar):
    assert ESKI_UYARI not in _kodlar(yanitlar['pf_ile'])


def test_basinc_beslemede_gonderilen_turbin_alanlari_adiyla_beyan_edilir(yanitlar):
    beyan = {b['field']: b for b in yanitlar['pf_ile'].get('inputs_not_used') or []
             if b.get('reason') == TURBINE_INPUT_UNUSED_REASON}
    assert sorted(beyan) == sorted(TURBINE_INPUT_FIELDS)
    gonderilen = _govde('pressure_fed', True)
    for alan, b in beyan.items():
        assert b['submitted'] == float(gonderilen[alan])
        assert b['used_by_model'] is None
        assert alan in b['message'] and 'no turbine' in b['message']
    uyari_alanlari = sorted(
        w['params']['field'] for w in yanitlar['pf_ile']['input_warnings']
        if isinstance(w, dict) and w.get('code') == YENI_UYARI)
    assert uyari_alanlari == sorted(TURBINE_INPUT_FIELDS)
    # Karşılaştırma YAPILMADIĞI için 'karşılaştırma' diye beyan edilmez.
    assert 'turbine_inlet_pressure' not in (
        yanitlar['pf_ile']['unwired_inputs']['reported_for_comparison'])


def test_gonderilmeyen_alan_icin_beyan_yok(yanitlar):
    y = yanitlar['pf_olmadan']
    assert not [b for b in (y.get('inputs_not_used') or [])
                if b.get('reason') == TURBINE_INPUT_UNUSED_REASON]
    assert YENI_UYARI not in _kodlar(y)
    assert ESKI_UYARI not in _kodlar(y)


def test_basinc_beslemede_yayimlanan_sayilar_degismez(yanitlar):
    a = dict(_duz({k: v for k, v in yanitlar['pf_ile'].items()
                   if k not in BEYAN_ANAHTARLARI}))
    b = dict(_duz({k: v for k, v in yanitlar['pf_olmadan'].items()
                   if k not in BEYAN_ANAHTARLARI}))
    farkli = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
    assert farkli == [], farkli[:10]
    # Beyan dışındaki uyarı kümesi de aynı.
    ua = [w for w in yanitlar['pf_ile']['input_warnings'] if
          not (isinstance(w, dict) and w.get('code') == YENI_UYARI)]
    assert ua == yanitlar['pf_olmadan']['input_warnings']


def test_turbinli_cevrimde_uyari_aynen(yanitlar):
    y = yanitlar['gg_ile']
    assert ESKI_UYARI in _kodlar(y)
    assert YENI_UYARI not in _kodlar(y)
    assert not [b for b in (y.get('inputs_not_used') or [])
                if b.get('reason') == TURBINE_INPUT_UNUSED_REASON]
    assert 'turbine_inlet_pressure' in y['unwired_inputs']['reported_for_comparison']


@pytest.mark.parametrize('ham,beklenen', [
    (float('nan'), 'nan'), (float('inf'), 'inf'), ('abc' * 40, 'abc' * 26 + 'ab'),
    (True, 'bool'), ([1, 2], 'list'), ('150', 150.0),
])
def test_beyan_yankisi_fail_closed_ve_json_guvenli(ham, beklenen):
    """Sonlu olmayan/sayı dışı girdi yankısı JSON'a güvenle yazılır."""
    motor = LiquidRocketEngine.__new__(LiquidRocketEngine)
    motor.overrides = {'turbine_inlet_pressure': ham}
    motor.design_warnings = []
    beyan = motor._declare_turbine_inputs_unused()
    assert len(beyan) == 1 and beyan[0]['field'] == 'turbine_inlet_pressure'
    assert beyan[0]['submitted'] == beklenen
    metin = json.dumps(beyan, allow_nan=False)
    assert 'NaN' not in metin and 'Infinity' not in metin


def test_bos_ve_none_alan_beyan_edilmez():
    motor = LiquidRocketEngine.__new__(LiquidRocketEngine)
    motor.overrides = {'turbine_inlet_pressure': '', 'turbine_expansion_ratio': None}
    motor.design_warnings = []
    assert motor._declare_turbine_inputs_unused() == []
    assert motor.design_warnings == []


def test_uyari_anahtari_iki_dilde_ve_yer_tutucu_esit():
    import re
    from pathlib import Path
    kaynak = (Path(__file__).resolve().parents[1] / 'hrma' / 'static' / 'js'
              / 'i18n_common.js').read_text(encoding='utf-8')
    satirlar = [s for s in kaynak.splitlines() if "'%s':" % YENI_UYARI in s]
    assert len(satirlar) == 2, satirlar
    yer = [sorted(re.findall(r'\{(\w+)\}', s)) for s in satirlar]
    assert yer[0] == yer[1] == ['field']
    assert any(any(h in s for h in 'çğıİöşü') for s in satirlar)
