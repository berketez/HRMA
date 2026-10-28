"""V301/FİZİK-2 kalem 5 (L-C §10) — kararlılık paneli pintle'da ana sonuçla aynı hüküm.

ÖLÇÜLEN KUSUR (docs/scofield/raw/OH/V301/fizik-2/k5_kararlilik_once.json):
ana sonuç pintle'da chug hükmünü iki atomizasyon ölçeğiyle veriyor (t ve d;
farklıysa ``marginal``), Analiz Merkezi'nin kararlılık paneli ise ucu yalnız
nominal τ ile koşup ``unstable`` basıyordu. Sonra (k5_kararlilik_sonra.json):
panel ana sonucun ölçek kaydını gönderir, uç hükmü motorun KENDİ yöntemiyle
(``LiquidRocketEngine._pintle_chug_scale_check``) kurar → aynı hüküm.
Kısma haritası yalnız nominal ölçekle koştuğunu adıyla beyan eder.
"""
import contextlib
import copy
import io
import json
import pathlib
import subprocess

import pytest

from hrma.engines.liquid_rocket_engine import PINTLE_CHUG_NOMINAL_SCALE
from tests.support import kabul
from tests.test_stability_panel import CENTER_JS, HARNESS, NODE, PANEL_JS

KOK = pathlib.Path(__file__).resolve().parents[1]
H = {'Host': '127.0.0.1:8080'}
UC = '/api/analysis/combustion-stability'
needs_node = pytest.mark.skipif(NODE is None, reason='node yok')


def _sessiz(fn, *a, **k):
    t = io.StringIO()
    with contextlib.redirect_stdout(t), contextlib.redirect_stderr(t):
        return fn(*a, **k)


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _sivi(client, **ek):
    govde = dict(kabul.sayfa_yuku('liquid'), **ek)
    r = _sessiz(client.post, '/calculate_liquid', json=govde, headers=H)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()


def _dongu(s):
    return s['combustion_analysis']['stability_analysis']['chug_loop']


@pytest.fixture(scope='module')
def pintle(client):
    return _sivi(client, injector_type='pintle')


@pytest.fixture(scope='module')
def unlike(client):
    return _sivi(client)


def _panel_govdesi(tmp_path, sonuc):
    betik = tmp_path / 'h.js'
    betik.write_text(HARNESS, encoding='utf-8')
    girdi = tmp_path / 'g.json'
    girdi.write_text(json.dumps({
        'motorType': 'liquid', 'results': sonuc,
        'select': ['chamber_acoustics', 'combustion_stability'], 'runs': 1,
        'response': {}}), encoding='utf-8')
    p = subprocess.run([NODE, str(betik), str(girdi), str(CENTER_JS),
                        str(PANEL_JS)], capture_output=True, text=True,
                       timeout=180)
    assert p.returncode == 0, p.stderr[-2000:]
    cagri = [c for c in json.loads(p.stdout)['fetchCalls']
             if c['url'].endswith('combustion-stability')]
    assert cagri, 'panel isteği kurmadı'
    return cagri[0]['body']


def test_ornek_pintle_olcege_duyarli(pintle):
    loop = _dongu(pintle)
    assert loop['verdict'] == 'marginal'
    assert loop['atomisation_scale_check']['verdicts_agree'] is False


@needs_node
def test_panel_ana_sonucla_ayni_hukum(client, pintle, tmp_path):
    loop = _dongu(pintle)
    govde = _panel_govdesi(tmp_path, pintle)
    assert set(govde['atomisation_scales']) == set(
        loop['atomisation_scale_check']['scales'])
    r = _sessiz(client.post, UC, json=govde, headers=H)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    j = r.get_json()
    a = j['assessment']
    assert a['verdict'] == loop['verdict'] == 'marginal'
    assert a['nominal_verdict'] == loop['nominal_verdict']
    # Nominal sayılar yerinde: ölçek denetimi nominal çevrimin sayılarını
    # DEĞİŞTİRMEZ (aynı gövde bağlamsız → bit-aynı). Ana sonuçla fark yalnız
    # Analiz Merkezi'nin 6 anlamlı basamak yuvarlamasıdır (J 0,285714 …).
    yalin = {k: v for k, v in govde.items() if k != 'atomisation_scales'}
    a0 = _sessiz(client.post, UC, json=yalin, headers=H).get_json()[
        'assessment']
    for k in ('growth_rate_1_s', 'tau_s', 'tau_over_tau_c', 'frequency_hz'):
        assert a[k] == a0[k], k
    assert a['nominal_verdict'] == a0['verdict']
    chk = a['atomisation_scale_check']
    assert chk['published_verdict'] == 'marginal'
    for ad, olcek in loop['atomisation_scale_check']['scales'].items():
        assert chk['scales'][ad]['verdict'] == olcek['verdict']
    kodlar = [w['code'] for w in j['warnings']]
    assert kodlar == ['warn.liquid.chug_scale_sensitive_nominal_%s'
                      % loop['nominal_verdict']]


@needs_node
def test_pintle_disi_govde_ve_yanit_degismez(client, unlike, tmp_path):
    govde = _panel_govdesi(tmp_path, unlike)
    assert 'atomisation_scales' not in govde
    j = _sessiz(client.post, UC, json=govde, headers=H).get_json()
    assert 'atomisation_scale_check' not in j['assessment']
    assert 'warnings' not in j
    assert j['assessment']['verdict'] == _dongu(unlike)['verdict']


def _olcekler(loop):
    return {ad: {k: v[k] for k in ('tau_s', 'length_scale_mm')}
            for ad, v in loop['atomisation_scale_check']['scales'].items()}


def _govde(loop, **ek):
    g = {'mode': 'chug', 'dp_ratio_j': loop['dp_ratio_j'],
         'tau_s': loop['inputs']['tau_s'], 'tau_c_s': loop['tau_c_s'],
         'atomisation_scales': _olcekler(loop)}
    if loop.get('tau_f_s'):
        g['tau_f_s'] = loop['tau_f_s']
    g.update(ek)
    return g


def test_duzenlenmis_tau_olcek_kuralini_kazanmaz(client, pintle):
    loop = _dongu(pintle)
    g = _govde(loop, tau_s=loop['inputs']['tau_s'] * 1.5)
    a = _sessiz(client.post, UC, json=g, headers=H).get_json()['assessment']
    chk = a['atomisation_scale_check']
    assert chk['status'] == 'NOT_APPLIED'
    assert chk['reason'] == 'tau_s_differs_from_nominal_scale'
    assert a['verdict'] in ('stable', 'unstable')
    assert 'nominal_verdict' not in a


@pytest.mark.parametrize('bozuk, alan', [
    ([1, 2], 'atomisation_scales'),
    ({'annulus_gap_t': {'tau_s': 1e-3, 'length_scale_mm': 1.0}},
     'atomisation_scales'),
    ({'x': {'tau_s': 1e-3, 'length_scale_mm': 1.0},
      'y': {'tau_s': 1e-3, 'length_scale_mm': 1.0}}, 'atomisation_scales'),
    ({PINTLE_CHUG_NOMINAL_SCALE: {'tau_s': -1.0, 'length_scale_mm': 1.0},
      'radial_hole_d': {'tau_s': 1e-3, 'length_scale_mm': 1.0}},
     'atomisation_scales.%s.tau_s' % PINTLE_CHUG_NOMINAL_SCALE),
    ({PINTLE_CHUG_NOMINAL_SCALE: {'tau_s': 1e-3, 'length_scale_mm': 'a'},
      'radial_hole_d': {'tau_s': 1e-3, 'length_scale_mm': 1.0}},
     'atomisation_scales.%s.length_scale_mm' % PINTLE_CHUG_NOMINAL_SCALE),
])
def test_bozuk_olcek_baglami_adli_422(client, pintle, bozuk, alan):
    g = _govde(_dongu(pintle), atomisation_scales=bozuk)
    r = _sessiz(client.post, UC, json=g, headers=H)
    assert r.status_code == 422, r.get_data(as_text=True)[:300]
    j = r.get_json()
    assert j['error'] == 'invalid_atomisation_scales'
    assert j['invalid_fields'][0]['field'] == alan


def test_kisma_haritasi_olcegi_beyan_eder(pintle, unlike):
    tm = pintle['throttle_map']['chug_loop_across_throttle']
    assert tm['atomisation_scale_used'] == PINTLE_CHUG_NOMINAL_SCALE
    assert tm['atomisation_scale_check_applied'] is False
    assert 'design point only' in tm['atomisation_scale_basis']
    tu = unlike['throttle_map']['chug_loop_across_throttle']
    assert 'atomisation_scale_basis' not in tu


def test_rozet_anahtarlari_iki_dilde():
    i18n = (KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js').read_text(
        encoding='utf-8')
    for k in ('panel.stab.badgeScaleNotApplied',
              'panel.stab.badgeScaleNotEvaluated',
              'panel.stab.badgeScaleAgree'):
        assert i18n.count("'%s':" % k) == 2, k
