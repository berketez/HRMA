"""V301/FİZİK-2 kalem 9 (S1) — güverte Yapısal sekmesi motorun tek yapısal hükmünü basar.

ÖLÇÜLEN KUSUR (docs/scofield/raw/OH/V301/fizik-2/k9_yapisal_once.json):
sekme cidarı 0 nöbetçisiyle gönderiyordu; uç cidarı kendisi boyutlandırıp
katı örnekte "UNSAFE · HIGH" (aynı yanıtta hüküm geri çekili), hibritte SF
0,566 ve sıvıda 0,916 ile "UNSAFE" basıyordu. Motorun kendi kaydı
(``motor_structural_verdict``) üçünde de NOT_EVALUATED. Sonra
(k9_yapisal_sonra.json): sekme motorun gerçek cidarını künyeyle gönderir,
uç hükmü motorun kaydından benimser; cidar "kullanıcının cidarı" sayılmaz.
"""
import contextlib
import copy
import io
import pathlib
import re

import pytest

from hrma.analysis.safety_analysis import (MOTOR_STRUCTURAL_VERDICT_BLOCKS,
                                           STRUCTURAL_VERDICT_SOURCE_MOTOR,
                                           motor_structural_verdict)
from tests.support import kabul

KOK = pathlib.Path(__file__).resolve().parents[1]
UC = '/analyze_structural_safety'
needs_node = pytest.mark.skipif(kabul.NODE is None, reason='node yok')


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


def _blok(sonuc, mt):
    for yol in MOTOR_STRUCTURAL_VERDICT_BLOCKS[mt]:
        o = sonuc
        for p in yol.split('.'):
            o = o.get(p) if isinstance(o, dict) else None
        if isinstance(o, dict) and o:
            kopya = h = {}
            parcalar = yol.split('.')
            for i, p in enumerate(parcalar):
                h[p] = o if i == len(parcalar) - 1 else {}
                h = h[p]
            return kopya
    return None


@pytest.fixture(scope='module')
def vakalar(client):
    kat = client.get('/api/materials').get_json()
    out = {}
    for mt in ('solid', 'hybrid', 'liquid'):
        s = _sessiz(client.post, kabul.hesap_ucu(mt),
                    json=kabul.sayfa_yuku(mt)).get_json()
        sp = kabul.guverte_yukleri(mt, s, kat)['specs']
        govde = dict([e for e in sp if e.get('id') == 'structural'][0]
                     ['payload'])
        m = s['motor'] if mt == 'hybrid' else s
        # Bağlam: panelin contextFromResults kuralının aynası (KABUL aynası
        # bağlamı uygulamıyor; JS tarafı test_z5_rozet_dock C1'de sınanır).
        govde.update({
            'motor_type': mt, 'motor_result': _blok(s, mt),
            'motor_verdict_inputs': {
                'chamber_pressure': m.get('chamber_pressure'),
                'chamber_diameter': govde['chamber_diameter'],
                'wall_thickness': govde['wall_thickness']},
            'motor_wall_source': 'sized_by_hrma'})
        out[mt] = (s, govde)
    return out


@needs_node
@pytest.mark.parametrize('mt', ['solid', 'hybrid', 'liquid'])
def test_sekme_motorun_hukmunu_ve_cidarini_kullanir(client, vakalar, mt):
    s, govde = vakalar[mt]
    assert govde['wall_thickness'] > 0, '0 nöbetçisiyle koşuyor'
    j = _sessiz(client.post, UC, json=govde).get_json()
    sa = j['structural_analysis']['safety_analysis']
    kayit = motor_structural_verdict(mt, s)
    assert sa['verdict_source'] == STRUCTURAL_VERDICT_SOURCE_MOTOR
    assert sa['status'] == kayit['status']
    assert sa['verdict_withheld'] is (kayit.get('withheld') is True)
    db = j['design_basis']
    assert db['wall_thickness_source'] == 'sized_by_hrma'
    assert db['is_verification'] is False
    assert db['verdict'] == ('withheld' if kayit.get('withheld') else 'issued')


@needs_node
def test_duzenlenmis_cidar_motor_hukmunu_kazanmaz(client, vakalar):
    _s, govde = vakalar['solid']
    g = copy.deepcopy(govde)
    g['wall_thickness'] = govde['wall_thickness'] * 2.0
    j = _sessiz(client.post, UC, json=g).get_json()
    sa = j['structural_analysis']['safety_analysis']
    assert sa['verdict_source'] == 'safety_module_structural_check'
    assert sa['motor_verdict_not_adopted']['fields'] == ['wall_thickness']
    assert j['design_basis']['wall_thickness_source'] != 'sized_by_hrma'


def test_nesne_olmayan_baglam_tip_reddi(client):
    g = {'chamber_pressure': 40, 'chamber_diameter': 0.085,
         'chamber_length': 0.4, 'throat_diameter': 0.018,
         'wall_thickness': 0.002, 'material': 'steel',
         'motor_result': 'peynir'}
    r = _sessiz(client.post, UC, json=g)
    assert 400 <= r.status_code < 500
    assert 'motor_result' in r.get_data(as_text=True)


def test_js_yol_tablosu_sunucuyla_ayni():
    js = (KOK / 'hrma' / 'static' / 'js' / 'panels' /
          'structural_panel.js').read_text(encoding='utf-8')
    blok = js.split('const MOTOR_VERDICT_BLOCKS = {', 1)[1].split('};', 1)[0]
    for mt, yollar in MOTOR_STRUCTURAL_VERDICT_BLOCKS.items():
        satir = re.search(mt + r':\s*(\[\[.*?\]\])[,\n]', blok, re.S).group(1)
        js_yollar = ['.'.join(re.findall(r"'([a-z_]+)'", p))
                     for p in satir.split('],')]
        assert js_yollar == list(yollar), (mt, js_yollar, yollar)


def test_kunye_anahtari_iki_dilde():
    i18n = (KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js').read_text(
        encoding='utf-8')
    assert i18n.count("'panel.structural.wallFromMotorSized':") == 2
