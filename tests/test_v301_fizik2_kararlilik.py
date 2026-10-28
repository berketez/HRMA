"""V301/FİZİK-2 kalem 5 (L-C §10) — kararlılık paneli pintle'da ana sonuçla aynı hüküm.

ÖLÇÜLEN KUSUR (docs/scofield/raw/OH/V301/fizik-2/k5_kararlilik_once.json):
ana sonuç pintle'da chug hükmünü iki atomizasyon ölçeğiyle veriyor (t ve d;
farklıysa ``marginal``), Analiz Merkezi'nin kararlılık paneli ise ucu yalnız
nominal τ ile koşup ``unstable`` basıyordu. Sonra (k5_kararlilik_sonra.json):
panel ana sonucun ölçek kaydını gönderir, uç hükmü motorun KENDİ yöntemiyle
(``LiquidRocketEngine._pintle_chug_scale_check``) kurar → aynı hüküm.
Kısma haritası yalnız nominal ölçekle koştuğunu adıyla beyan eder.

ÖLÇÜM KOŞULU SABİTLENDİ (V305/C1, 28 Eki): FİZİK-2 'pintle_ornek' vakasını
o günkü örnek gövdesiyle ölçtü (Pc 70 bar, O/F 2,3, Δp_inj 20 bar → J =
0,2857). V301/ÖRNEK (5fa435893, main'e 9ece56015, 27 Eki 14:27) örneği
gerçek sayfa gövdesiyle yeniden üretti: Pc 50 bar, O/F 2,0 (Δp_inj aynı 20
bar → J = 0,4). FİZİK-2 dalı bu birleşmeden önce ayrılmıştı; fe72e04b5'te
iki bekçi bu yüzden kırmızıydı. Yeni örnekte iki ölçek de 'stable' ve bu
FİZİKSEL OLARAK DOĞRU (aşağıdaki kapalı biçim nötr eğri bekçisi). Ölçeğe
duyarlı ('marginal') yolun bekçileri FİZİK-2'nin ölçüm koşulunda
(``FIZIK2_OLCUM_KOSULU``) koşar; o koşulda nominal τ bugün de k5_kararlilik
_sonra.json'daki değerle bit-aynı (0,002549909132311208 s, büyüme hızı
2,5811006081067944 1/s; ölçüldü). Örneğin kendi hükmü ayrıca çapalanır.
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


#: FİZİK-2'nin ölçüm koşulu (docs/scofield/raw/OH/V301/fizik-2/
#: k5_kararlilik_sonra.json, 'pintle_ornek': V301/ÖRNEK 5fa435893 öncesi
#: örnek gövdesi). Bugünkü sayfa gövdesinden YALNIZ bu iki alanla ayrılır;
#: Δp_inj 20 bar iki gövdede de aynı, J = 20/70.
FIZIK2_OLCUM_KOSULU = {'chamber_pressure': 70, 'mixture_ratio': 2.3}


@pytest.fixture(scope='module')
def pintle(client):
    """Bugünkü örnek sayfa gövdesi (Pc 50, O/F 2,0) + pintle."""
    return _sivi(client, injector_type='pintle')


@pytest.fixture(scope='module')
def pintle_duyarli(client):
    """FİZİK-2 ölçüm koşulu: iki ölçeğin hükmü ayrışır ('marginal')."""
    return _sivi(client, injector_type='pintle', **FIZIK2_OLCUM_KOSULU)


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


def test_ornek_pintle_olcege_duyarli(pintle_duyarli):
    """Ölçeğe duyarlı yol FİZİK-2'nin ölçüm koşulunda (V305/C1)."""
    loop = _dongu(pintle_duyarli)
    assert loop['dp_ratio_j'] == pytest.approx(20.0 / 70.0, rel=1e-12)
    assert loop['verdict'] == 'marginal'
    assert loop['nominal_verdict'] == 'unstable'
    assert loop['atomisation_scale_check']['verdicts_agree'] is False
    # FİZİK-2 ölçümüyle bit-aynı nominal (k5_kararlilik_sonra.json).
    assert loop['inputs']['tau_s'] == pytest.approx(
        0.002549909132311208, rel=1e-12)


def _notr_tau_orani(j):
    """Kapalı biçim nötr eğri: τ_kritik/τ_c (G = 1/(2J) > 1), yoksa inf.

    Ürünün beyan ettiği toplu chug denklemi τ_c·s + 1 + G·e^(−sτ) = 0
    (NASA SP-194, Harrje & Reardon 1972, Böl. 3 toplu besleme-bağlı model;
    ``chug_loop.model_basis``). s = iω yerleştirilince gerçel kısım
    cos(ωτ) = −1/G, sanal kısım ω·τ_c = G·sin(ωτ) = sqrt(G² − 1) verir;
    ilk geçiş θ = arccos(−1/G) ∈ (π/2, π), τ_kritik/τ_c = θ / sqrt(G² − 1).
    τ < τ_kritik kararlı. G ≤ 1 ise kök sağ yarı düzleme geçemez.
    """
    import math
    g = 1.0 / (2.0 * j)
    if g <= 1.0:
        return math.inf
    return math.acos(-1.0 / g) / math.sqrt(g * g - 1.0)


def test_ornek_pintle_hukmu_kapali_bicim_notr_egriyle(pintle,
                                                      pintle_duyarli):
    """Örneğin 'stable' hükmü fiziksel olarak doğru (V305/C1, ölçüldü).

    Örnek (Pc 50, Δp 20 → J 0,4, G 1,25): τ_kritik/τ_c = 3,331; iki ölçeğin
    τ/τ_c'si 1,879 (t) ve 1,821 (d) → ikisi de kararlı, hükümler aynı.
    FİZİK-2 koşulu (J 0,2857, G 1,75): τ_kritik/τ_c = 1,517; t ölçeği
    1,541 (kararsız), d ölçeği 1,299 (kararlı) → 'marginal'. Hüküm motorun
    sayısal kökünden gelir; bu bekçi onu bağımsız kapalı biçimle sınar.
    """
    for sonuc, beklenen in ((pintle, 'stable'), (pintle_duyarli, None)):
        loop = _dongu(sonuc)
        kritik = _notr_tau_orani(loop['dp_ratio_j'])
        hukumler = set()
        for ad, olcek in loop['atomisation_scale_check']['scales'].items():
            oran = olcek['tau_s'] / loop['tau_c_s']
            assert oran == pytest.approx(olcek['tau_over_tau_c'],
                                         rel=1e-9), ad
            kapali = 'stable' if oran < kritik else 'unstable'
            assert olcek['verdict'] == kapali, (ad, oran, kritik)
            hukumler.add(kapali)
        yayin = hukumler.pop() if len(hukumler) == 1 else 'marginal'
        assert loop['verdict'] == yayin
        if beklenen:
            assert loop['verdict'] == beklenen
    ornek = _dongu(pintle)
    assert ornek['dp_ratio_j'] == pytest.approx(20.0 / 50.0, rel=1e-12)
    assert ornek['atomisation_scale_check']['verdicts_agree'] is True


@needs_node
def test_panel_ana_sonucla_ayni_hukum(client, pintle_duyarli, tmp_path):
    # V305/C1: ölçeğe duyarlı yol FİZİK-2 ölçüm koşulunda (modül belgesi).
    pintle = pintle_duyarli
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
