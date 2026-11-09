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

V306/HİBRİT-NOZUL (FİZİK-2 DEVİR 1, kararın birinci dalı): motor artık lüle
malzemesiyle, kendi gazıyla kurduğu boğaz katsayısını yayımlıyor
(``nozzle_material_analysis.throat_thermal.throat_h_g_W_m2K`` + malzeme,
referans cidar, gaz künyesi). Ağ o malzemeyle çözülünce kapı lüle bölgesinde
KOŞAR (ölçüldü: panel profili ⟷ motor katsayısı bağıl 0; docs/scofield/raw/
OH/V306/hibrit-nozul/olcum/). Çapa alanı yoksa (eski sonuç) ya da malzemesi
ağınkinden farklıysa bugünkü 'calistirilamadi' yolu AYNEN durur; bu yol
aşağıda çapası silinmiş motor sözlüğüyle kilitli.
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


#: V3.0.5 (28 Eki, A1): örnek hibrit gerçek sayfa gövdesiyle yeniden üretildi
#: (V301/ÖRNEK 5fa435893, main'e 9ece56015). Dosya artık sayfanın BÜTÜN form
#: alanlarını taşır; aralarında toplam impuls kipinin kendi alanı
#: (``total_impulse`` = 10000) da var. Eski fikstür ``inputs.fields``i HAM
#: gönderiyordu: motor ``total_impulse`` + ``thrust``tan yanma süresini
#: 10000 / 3000 = 3,33 s türetiyordu (ölçüldü; örnek ve sayfa 10 s der).
#: Sayfanın itki/süre kipinde gönderdiği gövde ``total_impulse = F·t_b``dir
#: (``hrma.analysis.flight_vehicle.page_payload``, hibrit ``getFormData``
#: aynası) → 10 s. Fikstür bu yüzden ürünün sayfa gövdesi eşlemesiyle kurulur.
def _hibrit_motor(client, **degisen):
    from tests.test_example_projects import calculate_payload
    alan = json.loads((KOK / 'examples' / 'Example Hybrid N2O-HTPB 3kN.hrma')
                      .read_text(encoding='utf-8'))['inputs']['fields']
    alan.update(degisen)
    r = _sessiz(client.post, '/calculate',
                json=calculate_payload('hybrid', alan), headers=H)
    assert r.status_code == 200
    return r.get_json()['motor']


@pytest.fixture(scope='module')
def motor(client):
    m = _hibrit_motor(client)
    # V306/UÇUŞ-FEA (ek kalem 7): fikstürün sorusu "gövde sayfanın itki/süre
    # kipinde mi (10 s), ham impuls kipinde mi (3,33 s)". V306/HİBRİT-ÇAPRAZ
    # (1102aef68, 4 Kas) manşet ``burn_time``ı N₂O kendinden basınçlı tankın
    # TESLİM süresine çevirdi (boşalma çözümü, bu örnekte 10,414 s); sayfanın
    # istediği süre artık ``burn_time_requested_s``. Eski satır manşeti
    # okuyordu → 9 ERROR (fikstür kurulumu). Soru aynı, alan doğru alan.
    assert m['burn_time_requested_s'] == pytest.approx(10.0)
    assert m['burn_time'] >= m['burn_time_requested_s']
    return m


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


def _capasiz(motor):
    """Lüle çapası olmayan motor sözlüğü (V306 öncesi kaydedilmiş sonuç)."""
    m = copy.deepcopy(motor)
    m['nozzle_material_analysis']['throat_thermal'].pop('throat_h_g_W_m2K')
    return m


def test_ornekte_lule_capasi_ile_kapi_kosar(motor, profil):
    """V306/HİBRİT-NOZUL: çapa motorun LÜLE katsayısı, kapı lülede koşar."""
    assert profil['material'] == 'graphite'
    tt = motor['nozzle_material_analysis']['throat_thermal']
    assert tt['h_g_material'] == 'graphite'
    assert tt['gas_properties_basis']['assumed_fields'] == []
    out = _sessiz(bridge.extract_thermal_inputs, motor, axial_profile=profil)
    assert out['status'] == bridge.BRIDGE_STATUS_OK, out.get('reason')
    assert out['material_key'] == 'graphite'
    kapi = out['_basis']['h_profili']['makulluk_kapisi']
    assert kapi['durum'] == 'gecti'
    assert 'neden' not in kapi
    assert kapi['en_yakin_motor_alani'] == '.'.join(
        bridge.MOTOR_NOZZLE_THROAT_HG_ANCHOR['h_g_W_m2K'])
    assert kapi['en_yakin_motor_degeri_W_m2K'] == tt['throat_h_g_W_m2K']
    assert kapi['capa_malzemesi'] == kapi['ag_malzemesi'] == 'graphite'
    assert kapi['capa_referans_cidar_K'] == pytest.approx(
        tt['gas_side_reference_wall_temperature'])
    assert kapi['capa_gaz_varsayilan_alanlari'] == []
    # Panel profili ile motor aynı gazla, aynı malzemeyle kurulur.
    assert kapi['bagil_sapma'] == pytest.approx(0.0, abs=1e-9)
    assert kapi['tolerans'] == bridge.THERMAL_HG_CROSS_CHECK_TOL
    # Kamara katsayıları beyanda adıyla durur ama kıyasa girmez.
    assert set(kapi['kamara_capa_alanlari_W_m2K']) == {
        'heat_transfer_analysis.heat_transfer_coefficients.gas_side',
        'thermal_protection.nozzle_entry_liner.h_gas_W_m2K'}
    assert 'ss_304' in kapi['beyan']


def test_lule_capasi_malzemesi_farkliysa_eski_yol(motor, profil):
    """Çapanın malzemesi ağınkinden farklıysa kapı lüleye taşınmaz."""
    m = copy.deepcopy(motor)
    m['nozzle_material_analysis']['throat_thermal']['h_g_material'] = 'ss_304'
    out = _sessiz(bridge.extract_thermal_inputs, m, axial_profile=profil)
    kapi = out['_basis']['h_profili']['makulluk_kapisi']
    assert kapi['durum'] == 'calistirilamadi'
    assert kapi['neden'] == bridge.HG_GATE_NOT_RUN_ANCHOR_MATERIAL


def test_ornekte_capasiz_sonucta_kamara_ag_lule(motor, profil):
    """Çapası olmayan (eski) sonuç: V301/FİZİK-2 yolu AYNEN."""
    assert profil['material'] == 'graphite'
    out = _sessiz(bridge.extract_thermal_inputs, _capasiz(motor),
                  axial_profile=profil)
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


#: Aşım vakasının tasarım noktası: örneğin 27 Eki'ye kadarki O/F'si (7,0;
#: bugünkü örnek 6,0 — V301/ÖRNEK sayfa varsayılanı). ÖLÇÜLDÜ (28 Eki, RAPOR
#: A1, sayfa gövdesi, 10 s): O/F 7,0'da FEA tepe 3316,65 K > izin 3300 K,
#: ana zincir boğaz 3304,24 K EXCEEDS_ALLOWABLE (27 Eki ölçümü 3317 K ile
#: aynı); O/F 6,0'da FEA tepe 3259,51 K, ana zincir 3250,80 K SAFE.
ASIM_OF_ORANI = 7.0


@pytest.fixture(scope='module')
def motor_asim(client):
    return _hibrit_motor(client, of_ratio=ASIM_OF_ORANI)


@pytest.fixture(scope='module')
def fea_asim(client, motor_asim):
    kod, j = _fea(client, motor_asim, _profil(client, motor_asim))
    assert kod == 200, str(j)[:400]
    return j['fea']


def _capa_disi_beyani(fea):
    ml = fea['material_limits']
    assert fea['scalars']['material_key'] == 'graphite'
    assert bridge.VERDICT_WITHHELD_HG_ANCHOR_MATERIAL in \
        ml['verdict_withheld_reasons']
    assert ml['hg_anchor_material'] == 'ss_304'
    assert ml['hg_mesh_material'] == 'graphite'
    return ml


def _lule_capali(fea):
    """V306: kapı lülede koştu — çapa-dışı geri çekme nedeni YOK."""
    ml = fea['material_limits']
    assert fea['scalars']['material_key'] == 'graphite'
    assert bridge.VERDICT_WITHHELD_HG_ANCHOR_MATERIAL not in \
        ml['verdict_withheld_reasons']
    assert 'hg_anchor_material' not in ml
    assert fea['meta']['girdiler']['h_profili']['makulluk_kapisi'][
        'durum'] == 'gecti'
    return ml


def test_olumlu_hukum_geri_cekilir_asim_kalir(fea_asim, motor_asim):
    """Aşım vakası (O/F 7,0): ana zincirle aynı hüküm — grafit izin
    sınırını aşıyor (aşım gizlenmez); erime (3900 K) için olumlu hüküm
    verilmez. V3.0.5 A1: vaka eskiden örneğin kendisiydi; örnek tasarımı
    O/F 6,0'a geçince (sayfa gövdesiyle) tepe izin altına indi, bu yüzden
    aşım yarısı önceki örnek tasarım noktasında sınanır.

    V306/HİBRİT-NOZUL: kapı lülede koştu; erime hükmünü bu küçük koşuda
    yalnız sayısal yakınsama bekletir (çapa-dışı neden yok). Ana zincir
    motorun gazıyla 3313,37 K (FİZİK-2 DEVİR 1 ölçümüyle aynı)."""
    ml = _lule_capali(fea_asim)
    assert ml['peak_wall_T_K'] > ml['allowable_temperature_K']
    assert ml['exceeds_allowable'] is True
    assert ml['exceeds_melting'] is None
    assert ml['verdict_withheld_reasons'] == [
        bridge.VERDICT_WITHHELD_NUMERICAL]
    tt = motor_asim['nozzle_material_analysis']['throat_thermal']
    assert tt['verdict'] == 'EXCEEDS_ALLOWABLE'
    assert tt['throat_wall_temperature_K'] == pytest.approx(3313.37, abs=0.05)


def test_ornekte_olumlu_hukum_geri_cekilir(fea_ornek, motor):
    """Bugünkü örnek (O/F 6,0): FEA tepesi izin sınırının ALTINDA, yani
    çözüm 'izin içinde' derdi; h(z) mertebe denetimi lüle bölgesinde
    çalışmadığından bu olumlu hüküm geri çekilir (null), sayılar silinmez.
    Ana zincir de aşım görmüyor (gizlenen bir aşım yok).

    V306/HİBRİT-NOZUL: kapı lülede koştu; olumlu hüküm bu küçük koşuda
    YALNIZ sayısal yakınsama yüzünden bekler (çapa-dışı neden kalktı)."""
    ml = _lule_capali(fea_ornek)
    assert ml['peak_wall_T_K'] < ml['allowable_temperature_K']
    assert ml['exceeds_allowable'] is None
    assert ml['exceeds_melting'] is None
    assert ml['verdict_withheld_reasons'] == [
        bridge.VERDICT_WITHHELD_NUMERICAL]
    tt = motor['nozzle_material_analysis']['throat_thermal']
    assert tt['verdict'] == 'SAFE'


def test_capasiz_sonucta_olumlu_hukum_geri_cekilir(client, motor, profil):
    """Eski (çapasız) sonuçta V301/FİZİK-2 geri çekmesi AYNEN."""
    kod, j = _fea(client, _capasiz(motor), profil)
    assert kod == 200, str(j)[:300]
    ml = _capa_disi_beyani(j['fea'])
    assert ml['exceeds_allowable'] is None
    assert ml['exceeds_melting'] is None


def test_sahte_dusuk_profil_lulede_adiyla_reddedilir(client, motor, profil):
    """V306/HİBRİT-NOZUL: P8B2-01 saldırısı (Bartz'ın 1/50'si) lüle
    bölgesinde artık KAPIDAN döner — sıcaklık alanı üretilmez, neden
    adıyla (eskiden alan üretiliyor, yalnız olumlu hüküm çekiliyordu)."""
    p = copy.deepcopy(profil)
    p['h_g'] = [v / 50.0 for v in profil['h_g']]
    kod, j = _fea(client, motor, p)
    assert kod == 422, str(j)[:300]
    fea = j['fea']
    assert fea['status'] == bridge.BRIDGE_STATUS_NOT_MODELLED
    assert any('lüle boğaz katsayısıyla' in m for m in fea['missing'])
    for alan in ('material_limits', 'scalars', 'fields'):
        assert alan not in fea, alan


def test_sahte_dusuk_profil_capasiz_olumlu_hukum_almaz(client, motor,
                                                       profil):
    """Eski (çapasız) sonuçta: Bartz'ın 1/50'si 'izin içinde' hükmü
    KAZANMAZ (kapı koşmasa da olumlu hüküm geri çekilir)."""
    p = copy.deepcopy(profil)
    p['h_g'] = [v / 50.0 for v in profil['h_g']]
    kod, j = _fea(client, _capasiz(motor), p)
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
    assert 'nozul cidarında h(z) mertebe denetimi yapılamadı' in i18n
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
