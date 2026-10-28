"""V301/PANEL kalem 6 (NK-12) — termal FEA lüle cidarını lülenin malzemesiyle çözer.

ÖLÇÜLEN KUSUR (``docs/scofield/raw/OH/V301/panel/fea_malzeme_once.json``,
panelin kendi zinciri): örnek hibritte termal alan yalnız lüleyken
(include_chamber = False) cidar kamara malzemesiyle (ss_304) çözülüyordu:
tepe 3243,6 K, "erime noktası aşılıyor (1673 K)". Motorun lüle malzemesi
grafit (izin 3300 K); ana zincir aynı boğazı grafitle değerlendiriyor.
H-PANEL bunu rozetle beyan etmişti; beyan çözüm değildir.

Sonra (``fea_malzeme_sonra.json``): profil ve ağ grafit, tepe 3316,7 K,
izin 3300 K aşılır, erime 3900 K aşılmaz — ana zincirin lüle hükmüyle
(``warn.hybrid.nozzle_material_over_temp``, 3304 K ⟷ 3300 K) aynı hüküm.
"""
import contextlib
import io
import json
import pathlib

import pytest

from hrma.fea.bridge import (NOZZLE_MATERIAL_PATHS, _lule_malzemesi,
                             extract_thermal_inputs)
from tests.test_fea_termal_uc import TERMAL_KUCUK_KOSU
from tests.test_thermal_fea_panel import (panel_gazi_ve_kalinligi,
                                          profil_govdesi)

KOK = pathlib.Path(__file__).resolve().parents[1]


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
    r = _sessiz(client.post, '/calculate', json=alan)
    assert r.status_code == 200
    return r.get_json()['motor']


@pytest.fixture(scope='module')
def zincir(client, motor):
    govde = dict(profil_govdesi(motor), **panel_gazi_ve_kalinligi(motor))
    wp = _sessiz(client.post, '/api/analysis/wall-profile', json=govde)
    assert wp.status_code == 200, wp.get_data(as_text=True)[:300]
    prof = wp.get_json()['wall_profile']
    f = _sessiz(client.post, '/api/fea/thermal', json=dict(
        TERMAL_KUCUK_KOSU, motor_results=motor, axial_profile=prof,
        ambient_temperature_K=293.15))
    assert f.status_code == 200, f.get_data(as_text=True)[:400]
    return govde, prof, f.get_json()['fea']


def test_ornegin_lule_ve_kamara_malzemesi_farkli(motor):
    assert motor['structural_analysis']['design_parameters']['material'] \
        == 'ss_304'
    assert _lule_malzemesi(motor) == ('graphite', NOZZLE_MATERIAL_PATHS[0])


def test_lule_alani_lule_malzemesiyle_cozulur(motor, zincir):
    """İki zincir ZIT hüküm vermez (V301/CI-FİZİK, 28 Eki; ana model
    kararı: ana zincirin kararlı hâl denge cidar sıcaklığı T_wall_eq
    yöneten, tutucu hükümdür; geçici FEA tepesi onun altında kalır).

    Eski beklenti koşulsuz "ikisi de aşar" idi (eski örnek: O/F 7,
    T_c 3333 K, ana zincir 3304 K > 3300 K). V301/ÖRNEK (5fa435893,
    27 Eki) örneği O/F 6'ya çekti: T_c 3279 K, boğaz geri kazanım
    sıcaklığı 3265 K < izin 3300 K — aşım fiziksel olarak imkânsız.
    Ölçüm (bu örnek): ana zincir 3250,8 K, SAFE, uyarı yok; FEA tepe
    3176,7 K, exceeds_allowable None (zaman adımı yakınsamadı, h_g
    çapraz denetimi koşmadı — olumlu hüküm bekletildi).
    """
    govde, prof, fea = zincir
    assert govde['material'] == 'graphite'          # panel profili
    assert prof['material'] == 'graphite'            # uç profili
    assert fea['scalars']['material_key'] == 'graphite'   # ağ
    sinir = fea['material_limits']
    assert sinir['melting_point_K'] == pytest.approx(3900.0)
    nma = motor['nozzle_material_analysis']
    tt = nma['throat_thermal']
    kodlar = {w.get('code') for w in nma.get('warnings') or []
              if isinstance(w, dict)}
    # (c) İki zincir aynı izin eşiğine bakar (tek eşik fonksiyonu).
    assert tt['allowable_temperature_K'] == pytest.approx(
        sinir['allowable_temperature_K'], rel=1e-12)
    # (a) Ana zincirin uyarısı kendi sayısının hükmüdür.
    ana_asiyor = (tt['throat_wall_temperature_K']
                  > tt['allowable_temperature_K'])
    assert ('warn.hybrid.nozzle_material_over_temp' in kodlar) == ana_asiyor
    assert tt['verdict'] == ('EXCEEDS_ALLOWABLE' if ana_asiyor else 'SAFE')
    # (b) Zıt hüküm yok: FEA aşım derse yöneten (tutucu) zincir de der;
    # FEA olumlu hüküm verirse yöneten zincir aşım demez.
    if sinir['exceeds_allowable'] is True:
        assert ana_asiyor
    if sinir['exceeds_allowable'] is False:
        assert not ana_asiyor
    # (d) Taşınımla ısınan cidar gazın geri kazanım sıcaklığını aşamaz.
    assert sinir['peak_wall_T_K'] <= max(prof['T_recovery'])
    assert sinir.get('exceeds_melting') in (False, None)


def test_kaynak_yazilir(motor):
    out = _sessiz(extract_thermal_inputs, motor, axial_profile=_profil(motor))
    assert out['material_key'] == 'graphite'
    assert out['thermal_material_source'] == \
        'motorun lüle malzemesi (nozzle_material_analysis.material)'


def _profil(motor):
    from hrma.app import app
    with app.test_client() as c:
        govde = dict(profil_govdesi(motor), **panel_gazi_ve_kalinligi(motor))
        return _sessiz(c.post, '/api/analysis/wall-profile',
                       json=govde).get_json()['wall_profile']


def test_kamara_dahil_iki_malzemede_adli_ret(motor):
    """Tek malzemeli ağ iki cidarı anlatamaz: kamara malzemesi lüleye
    sessizce uygulanmaz (fail-closed)."""
    out = _sessiz(extract_thermal_inputs, motor, axial_profile=_profil(motor),
                  include_chamber=True)
    assert out['status'] != 'ok'
    metin = json.dumps(out, ensure_ascii=False, default=str)
    assert 'iki malzemeli' in metin


def test_lule_malzemesi_yoksa_kamara_malzemesi_kalir(motor):
    import copy
    m = copy.deepcopy(motor)
    m.pop('nozzle_material_analysis', None)
    m.pop('nozzle_design', None)
    assert _lule_malzemesi(m) is None
    out = _sessiz(extract_thermal_inputs, m, axial_profile=_profil(motor))
    assert out['material_key'] == 'ss_304'
    assert out['thermal_material_source'].startswith('kamara malzemesi')


def test_rozet_anahtari_iki_dilde():
    metin = (KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js').read_text(
        encoding='utf-8')
    assert metin.count("'feaT.badgeNozzleMaterialUsed':") == 2
    # V301/CI-FİZİK (28 Eki): TR sözlüğün terimi 'nozul' (test_d36_dil2_a1:
    # sözlük 'lüle' demez); rozet metni sözlüğe çekilmişti, test eski
    # 'lüle' metnini arıyordu (main'de de kırmızıydı).
    assert ('CİDAR MALZEMESİ: {nozzle} — motorun nozul malzemesi '
            '(bu alan yalnız nozul cidarını kapsar)') in metin
    assert 'motorun lüle malzemesi' not in metin
