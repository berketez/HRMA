"""V301/FİZİK-2 kalem 1 (NK-12) — h(z) makullük kapısının çapası ağın malzemesiyle.

ÖLÇÜLEN KUSUR (docs/scofield/raw/OH/V301/fizik-2/k1_capa_once.json,
k1_fea_once.json): termal FEA lüleyi KAMARA malzemesiyle (ss_304) çözüyor ve
"erime noktası aşılıyor (1673 K)" diyordu; varsayılan hibritte ana zincir
grafit lüleye SAFE (3261 K < 3300 K) derken FEA aynı lüleye "eriyor"
diyordu. PANEL yaması (DEVIR_nk12) ağı lülenin malzemesiyle (grafit) çözer.
Engel: h(z) makullük kapısının çapası (motorun boğaz katsayıları) kamara
malzemesinin referans cidar sıcaklığıyla (1073 K) kurulu; Bartz σ cidar
sıcaklığına bağlı olduğundan grafit profili aynı motorda %19,5-20,5 sapıyor,
gazı beyan etmeyen gövdede %38 → NOT_MODELLED.

Karar (ana model): çapa ağın malzemesiyle tutarlı olmalı. Motor lüle
malzemesiyle boğaz katsayısı yayımlamadığından lüle bölgesi kapının DIŞINDA
kalır ve ADIYLA beyan edilir; tolerans gevşetilmez; olumlu hüküm geri
çekilir, aşım kalır (k1_fea_sonra.json).
"""
import contextlib
import copy
import io
import json
import pathlib

import pytest

from hrma.fea import bridge
from tests.test_fea_termal_uc import TERMAL_KUCUK_KOSU
from tests.test_thermal_fea_panel import (panel_gazi_ve_kalinligi,
                                          profil_govdesi)

KOK = pathlib.Path(__file__).resolve().parents[1]
H = {'Host': '127.0.0.1:8080'}


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


@pytest.fixture(scope='module')
def motor(client):
    alan = json.loads((KOK / 'examples' / 'Example Hybrid N2O-HTPB 3kN.hrma')
                      .read_text(encoding='utf-8'))['inputs']['fields']
    r = _sessiz(client.post, '/calculate', json=alan, headers=H)
    assert r.status_code == 200
    return r.get_json()['motor']


def _profil(client, motor, malzeme=None):
    govde = dict(profil_govdesi(motor), **panel_gazi_ve_kalinligi(motor))
    if malzeme is not None:
        govde['material'] = malzeme
    r = _sessiz(client.post, '/api/analysis/wall-profile', json=govde,
                headers=H)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()['wall_profile']


@pytest.fixture(scope='module')
def profil(client, motor):
    """Panelin KENDİ gövdesi (lüle malzemesi: grafit, motorun gazı)."""
    return _profil(client, motor)


def _fea(client, motor, prof):
    r = _sessiz(client.post, '/api/fea/thermal', json=dict(
        TERMAL_KUCUK_KOSU, motor_results=motor, axial_profile=prof,
        ambient_temperature_K=293.15), headers=H)
    return r.status_code, (r.get_json() or {})


@pytest.fixture(scope='module')
def fea_ornek(client, motor, profil):
    kod, j = _fea(client, motor, profil)
    assert kod == 200, str(j)[:400]
    return j['fea']


def test_tolerans_gevsemedi():
    assert bridge.THERMAL_HG_CROSS_CHECK_TOL == 0.25


def test_ornekte_capa_kamara_ag_lule(motor, profil):
    assert profil['material'] == 'graphite'
    out = _sessiz(bridge.extract_thermal_inputs, motor, axial_profile=profil)
    assert out['status'] == bridge.BRIDGE_STATUS_OK, out.get('reason')
    assert out['material_key'] == 'graphite'
    kapi = out['_basis']['h_profili']['makulluk_kapisi']
    assert kapi['durum'] == 'calistirilamadi'
    assert kapi['neden'] == bridge.HG_GATE_NOT_RUN_ANCHOR_MATERIAL
    assert kapi['capa_malzemesi'] == 'ss_304'
    assert kapi['ag_malzemesi'] == 'graphite'
    # Çapanın referans cidarı motorun yayımladığı alandan (ss_304: 1073 K).
    assert kapi['capa_referans_cidar_K'] == pytest.approx(1073.0)
    # Beyan çapa alanlarını ve iki malzemeyi ADIYLA söyler.
    for parca in ('ss_304', 'graphite', 'LÜLE BÖLGESİ',
                  'heat_transfer_analysis.heat_transfer_coefficients.gas_side'):
        assert parca in kapi['beyan'], parca


def test_olumlu_hukum_geri_cekilir_asim_kalir(fea_ornek, motor):
    ml = fea_ornek['material_limits']
    assert fea_ornek['scalars']['material_key'] == 'graphite'
    assert bridge.VERDICT_WITHHELD_HG_ANCHOR_MATERIAL in \
        ml['verdict_withheld_reasons']
    assert ml['hg_anchor_material'] == 'ss_304'
    assert ml['hg_mesh_material'] == 'graphite'
    # Ana zincirle aynı hüküm: grafit izin sınırını aşıyor (aşım gizlenmez);
    # erime (3900 K) için olumlu hüküm verilmez.
    assert ml['exceeds_allowable'] is True
    assert ml['exceeds_melting'] is None
    tt = motor['nozzle_material_analysis']['throat_thermal']
    assert tt['verdict'] == 'EXCEEDS_ALLOWABLE'


def test_sahte_dusuk_profil_olumlu_hukum_almaz(client, motor, profil):
    """P8B2-01 saldırısı lüle bölgesinde: Bartz'ın 1/50'si 'izin içinde'
    hükmü KAZANMAZ (kapı koşmasa da olumlu hüküm geri çekilir)."""
    p = copy.deepcopy(profil)
    p['h_g'] = [v / 50.0 for v in profil['h_g']]
    kod, j = _fea(client, motor, p)
    assert kod == 200, str(j)[:300]
    ml = j['fea']['material_limits']
    assert ml['exceeds_allowable'] is None
    assert ml['exceeds_melting'] is None
    assert bridge.VERDICT_WITHHELD_HG_ANCHOR_MATERIAL in \
        ml['verdict_withheld_reasons']


def test_malzemeler_ayniysa_kapi_eskisi_gibi_calisir(client, motor):
    """Lüle malzemesi kamarayla aynıysa çapa ağın malzemesidir: kapı koşar,
    doğru profil geçer, 1/50 profili adıyla reddedilir (P8B2-01 korunur)."""
    m = copy.deepcopy(motor)
    m['nozzle_material_analysis']['material'] = 'ss_304'
    prof = _profil(client, m, 'ss_304')
    out = _sessiz(bridge.extract_thermal_inputs, m, axial_profile=prof)
    kapi = out['_basis']['h_profili']['makulluk_kapisi']
    assert kapi['durum'] == 'gecti'
    assert kapi['bagil_sapma'] == pytest.approx(0.0, abs=1e-9)
    p = copy.deepcopy(prof)
    p['h_g'] = [v / 50.0 for v in prof['h_g']]
    red = _sessiz(bridge.extract_thermal_inputs, m, axial_profile=p)
    assert red['status'] == bridge.BRIDGE_STATUS_NOT_MODELLED
    assert 'axial_profile.h_g' in ' '.join(red['missing'])


def test_iki_malzemeli_ret_profilden_once(motor, profil):
    """include_chamber = True ve iki malzeme farklı: profil denetimlerinden
    ÖNCE adlı ret (profil kamarayı kapsamasa bile neden malzemedir)."""
    out = _sessiz(bridge.extract_thermal_inputs, motor, axial_profile=profil,
                  include_chamber=True)
    assert out['status'] == bridge.BRIDGE_STATUS_NOT_MODELLED
    assert out['missing'] == ['iki malzemeli cidar (kamara + lüle)']


def test_neden_kodu_ekranda_iki_dilde():
    i18n = (KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js').read_text(
        encoding='utf-8')
    assert i18n.count("'feaT.withheldHgAnchorMaterial':") == 2
    assert 'lüle cidarında h(z) mertebe denetimi yapılamadı' in i18n
    js = (KOK / 'hrma' / 'static' / 'js' / 'thermal_fea_panel.js').read_text(
        encoding='utf-8')
    assert ("k === '%s'" % bridge.VERDICT_WITHHELD_HG_ANCHOR_MATERIAL) in js


def test_asim_varken_geri_cekme_gerekcesi_rozet_katinda():
    """Ekran ölçümü (docs/…/fizik-2/ortusme_termal_once → ortusme_termal):
    örnek hibritte tepe 3317 K > izin 3300 K. Rozet zinciri aşım rozetini
    seçince withheldBadge basılmıyordu; lüle bölgesinde h(z) mertebe
    denetiminin koşmadığı (sunucunun geri çekme gerekçesi) ekranda yoktu
    (TR/EN × 1280/1440: 4/4 yok → 4/4 var). Aşım hükmü korunur; gerekçe
    ayrı rozetle söylenir."""
    kok = pathlib.Path(__file__).resolve().parents[1]
    js = (kok / 'hrma' / 'static' / 'js' / 'thermal_fea_panel.js').read_text(
        encoding='utf-8')
    govde = js.split('function renderBadges(el, vm)', 1)[1].split(
        'el.innerHTML = html;', 1)[0]
    i = govde.find("TF('feaT.badgeWithheldOnExceedance'")
    assert i > 0, 'aşım varken gerekçe rozeti yok'
    kosul = govde[max(0, i - 300):i]
    assert 'ml.verdict_withheld === true' in kosul
    assert 'ml.exceeds_allowable === true' in kosul
    assert 'ml.exceeds_melting === true' in kosul
    assert 'esc(withheldReasonText(ml))' in govde[i:i + 200]
    i18n = (kok / 'hrma' / 'static' / 'js' / 'i18n_common.js').read_text(
        encoding='utf-8')
    assert i18n.count("'feaT.badgeWithheldOnExceedance':") == 2
