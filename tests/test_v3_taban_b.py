# -*- coding: utf-8 -*-
"""ÖH V3 taban-b — depo bekçisi taban kırmızılarının onarım bekçileri.

Bu dosya yalnız bu turun YENİ davranışlarını savunur; çevrilen düğümlerin
kendisi kendi dosyalarında durur (rapor:
``docs/scofield/raw/OH/V3/taban/b/rapor.md``).

1. ``transient_panel.js`` — regüleli kipte ``transient.tank_state_role``
   rozeti (OH-UC-04 ekran ayağı). Düzenek ürünün GERÇEK yardımcılarını
   (``T``, ``TF``, ``ekranSayisi``, ``badge``) kaynaktan çıkarır; saplama
   yazılmaz. Girdi gerçek ``/api/transient-analysis`` gövdesidir.
2. ``test_d18_bekci_cevirisi_a1`` rota çözücüsünün dördüncü genişlemesi —
   üç yeni kalıbın fail-closed sınırları (belirsizde ÇÖZMEZ).
"""

import ast
import json
import pathlib
import shutil
import subprocess

import pytest

import tests.test_d18_bekci_cevirisi_a1 as d18

KOK = pathlib.Path(__file__).resolve().parents[1]
PANEL_JS = KOK / 'hrma' / 'static' / 'js' / 'transient_panel.js'
I18N_COMMON = KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js'
NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(NODE is None, reason='node yok')

#: test_wave3_contract'taki panel yüküyle AYNI çekirdek hibrit girdi
#: (orada ``TRANSIENT_INPUT``); ikinci bir kopya yazılmaz, ithal edilir.
from tests.test_wave3_contract import TRANSIENT_INPUT  # noqa: E402


def _islev(kaynak, ad):
    """``function ad(`` gövdesini dengeli süslü parantezle çıkarır."""
    bas = kaynak.index('function %s(' % ad)
    i = kaynak.index('{', bas)
    derinlik = 0
    while True:
        if kaynak[i] == '{':
            derinlik += 1
        elif kaynak[i] == '}':
            derinlik -= 1
            if derinlik == 0:
                return kaynak[bas:i + 1]
        i += 1


def _rozet(tr):
    kaynak = PANEL_JS.read_text(encoding='utf-8')
    kod = '\n'.join(_islev(kaynak, ad) for ad in (
        'T', 'TF', 'ekranSayisi', 'badge', 'tankStateRoleBadge'))
    betik = ('var window = {};\n' + kod + '\nprocess.stdout.write('
             'JSON.stringify(tankStateRoleBadge(%s)));\n' % json.dumps(tr))
    r = subprocess.run([NODE], input=betik, capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr[-1500:]
    return json.loads(r.stdout)


@pytest.fixture(scope='module')
def govdeler():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        reg = c.post('/api/transient-analysis', json=TRANSIENT_INPUT)
        blow = c.post('/api/transient-analysis',
                      json=dict(TRANSIENT_INPUT, feed_mode='blowdown'))
    assert reg.status_code == 200, reg.get_data(as_text=True)[:300]
    assert blow.status_code == 200, blow.get_data(as_text=True)[:300]
    return reg.get_json()['transient'], blow.get_json()['transient']


@node_gerekli
class TestTankDurumuRozeti:

    def test_regule_kipte_rozet_ucun_carpanini_basar(self, govdeler):
        reg, _ = govdeler
        tsr = reg['tank_state_role']
        assert tsr['used_by_this_model'] is False
        f = tsr['regulated_flow_temperature_sensitivity'][
            'implied_mdot_factor_sqrt_rho_ratio']
        html = _rozet(reg)
        assert 'TANK STATE NOT USED' in html, html
        # Sayı ucun alanından (i18n yokken nokta ondalıklı toFixed(3)).
        assert ('= %.3f' % f) in html, (f, html)
        # İpucu kullanıcının girdiği sıcaklığı yankılar (ucun alanı).
        assert ('%.1f K' % tsr['tank_temperature_K_received']) in html, html

    def test_carpan_yoksa_OLCULMEDI_der_sayi_uydurmaz(self, govdeler):
        reg, _ = govdeler
        tr = json.loads(json.dumps(reg))
        tr['tank_state_role']['regulated_flow_temperature_sensitivity'] = None
        html = _rozet(tr)
        assert 'NOT MEASURED' in html, html
        assert '√(ρ(T)/ρ(T_ref)) =' not in html, html

    def test_blowdown_kipinde_rozet_yok(self, govdeler):
        _, blow = govdeler
        assert blow['tank_state_role'] is None
        assert _rozet(blow) == ''

    def test_render_rozeti_cagiriyor(self):
        govde = _islev(PANEL_JS.read_text(encoding='utf-8'), 'render')
        assert 'html += tankStateRoleBadge(tr);' in govde


def test_rozet_anahtarlari_iki_dilde():
    metin = I18N_COMMON.read_text(encoding='utf-8')
    for anahtar in ('transient.badgeTankStateUnused',
                    'transient.badgeTankStateUnusedNoFactor',
                    'transient.tankStateUnusedTip'):
        assert metin.count("'%s':" % anahtar) == 2, anahtar
    assert 'TANK DURUMU KULLANILMADI (regüleli)' in metin
    assert 'girdiğiniz tank sıcaklığı ({t} K)' in metin


# ---------------------------------------------------------------------------
# 2. Rota çözücüsünün yeni kalıpları — fail-closed sınırlar
# ---------------------------------------------------------------------------
def _cagri_ve_kapsam(kaynak):
    agac = ast.parse(kaynak)
    modul, kapsamlar = d18._fonksiyon_kapsamlari(agac)
    cagri = [d for d in ast.walk(agac) if isinstance(d, ast.Call)
             and isinstance(d.func, ast.Attribute)
             and d.func.attr == 'post'][0]
    return agac, cagri, kapsamlar.get(id(cagri), modul)


def test_altsimge_tum_degerler_dizgeyse_cozulur():
    agac, cagri, _ = _cagri_ve_kapsam(
        "UC = {'a': '/calculate', 'b': '/calculate_solid'}\n"
        "def test_x(client, t):\n    client.post(UC[t], json={})\n")
    assert d18._altsimge_degerleri(cagri.args[0], d18._sozluk_dugumleri(
        agac)) == {'/calculate', '/calculate_solid'}


def test_altsimge_karisik_degerde_COZMEZ():
    agac, cagri, _ = _cagri_ve_kapsam(
        "UC = {'a': '/calculate', 'b': YOL}\n"
        "def test_x(client, t):\n    client.post(UC[t], json={})\n")
    assert d18._altsimge_degerleri(
        cagri.args[0], d18._sozluk_dugumleri(agac)) == set()


def test_iki_kez_atanan_ad_belirsiz_sayilir():
    agac, cagri, _ = _cagri_ve_kapsam(
        "UC = {'a': '/calculate'}\nUC = {'a': '/x'}\n"
        "def test_x(client, t):\n    client.post(UC[t], json={})\n")
    assert d18._altsimge_degerleri(
        cagri.args[0], d18._sozluk_dugumleri(agac)) == set()


def test_sorgu_eki_yol_segmenti_eklerse_COZMEZ():
    _, cagri, kapsam = _cagri_ve_kapsam(
        "import pytest\n"
        "@pytest.mark.parametrize('ek', ['?a=1', '/baska'])\n"
        "def test_x(client, ek):\n    client.post('/api/x/1' + ek)\n")
    assert d18._sorgu_ekli_somut_yol(cagri.args[0], kapsam) == ''
    _, cagri, kapsam = _cagri_ve_kapsam(
        "import pytest\n"
        "@pytest.mark.parametrize('ek', ['', '?a=1'])\n"
        "def test_x(client, ek):\n    client.post('/api/x/1' + ek)\n")
    assert d18._sorgu_ekli_somut_yol(cagri.args[0], kapsam) == '/api/x/1'


def test_adla_verilen_cok_sutunlu_parametrize_cozulur():
    _, _, kapsam = _cagri_ve_kapsam(
        "import pytest\n"
        "L = [('p1', '/analyze_safety', {}), ('p2', '/api/bolted-joint', {})]\n"
        "@pytest.mark.parametrize('panel,uc,govde', L)\n"
        "def test_x(client, panel, uc, govde):\n"
        "    client.post(uc, json=govde)\n")
    assert kapsam['uc'] == {'/analyze_safety', '/api/bolted-joint'}
    assert kapsam['panel'] == {'p1', 'p2'}
