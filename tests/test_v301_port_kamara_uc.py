"""v3.0.1 · kulvar P — artık et girdisi ve grain zarfı reddinin UÇ/ARAYÜZ yüzü.

Motor tarafı bekçileri ``tests/test_v301_port_kamara_zarf.py``de. Bu dosya:
  * ``residual_web_thickness`` /calculate ve /api/quick-geometry'den motora
    ULAŞIYOR mu (ölü girdi değil), aykırı değer 422 + ``invalid_fields`` mi;
  * verilmediyse varsayılan ``defaults_applied`` ile ADIYLA beyan ediliyor mu;
  * kullanıcı kamara çapı son portları taşıyamıyorsa 422 gövdesi gereken en
    küçük çapı ``error`` cümlesinin BAŞINDA taşıyor mu (ölçüldü: arayüz
    ``app.js::sunucuHataMetni`` yalnız ``error``ı basıyor ve ~300 karakterde
    kesiyor);
  * form alanı, getFormData okuması, beyan şeridi ve EN/TR anahtarları.
"""

import json
import re
from pathlib import Path

import pytest

DEPO = Path(__file__).resolve().parents[1]
SABLON = DEPO / 'hrma' / 'templates' / 'advanced.html'
SOZLUK = DEPO / 'hrma' / 'static' / 'js' / 'i18n_advanced.js'
GOVDE = json.loads((DEPO / 'tests' / 'fixtures' / 'd36_hibrit_ornek_govde.json')
                   .read_text(encoding='utf-8'))['govde']


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    return app.test_client()


def _govde(**ek):
    g = dict(GOVDE)
    g['calculate_trajectory'] = False
    g.update(ek)
    return g


@pytest.fixture(scope='module')
def varsayilan_yanit(istemci):
    r = istemci.post('/calculate', json=_govde())
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def test_verilmeyen_artik_et_adiyla_beyan_edilir(varsayilan_yanit):
    kayitlar = [k for k in varsayilan_yanit.get('defaults_applied') or []
                if k.get('field') == 'residual_web_thickness']
    assert len(kayitlar) == 1
    k = kayitlar[0]
    assert k['value'] == 0.0 and k['unit'] == 'mm'
    assert k['reason'] == 'not_supplied'
    assert 'thermal protection and regression uncertainty not included' \
        in k['message']
    g = varsayilan_yanit['motor']['grain_design']
    assert g['residual_web_source'] == 'default_zero_idealisation'
    assert g['grain_outer_diameter_mm'] == pytest.approx(
        g['port_diameter_final_mm'], rel=1e-12)


def test_artik_et_motora_ulasir(istemci, varsayilan_yanit):
    r = istemci.post('/calculate', json=_govde(residual_web_thickness=2.5))
    assert r.status_code == 200
    j = r.get_json()
    g = j['motor']['grain_design']
    assert g['residual_web_mm'] == pytest.approx(2.5)
    assert g['residual_web_source'] == 'user_input'
    assert g['grain_outer_diameter_mm'] == pytest.approx(
        g['port_diameter_final_mm'] + 5.0, rel=1e-12)
    assert not [k for k in j.get('defaults_applied') or []
                if k.get('field') == 'residual_web_thickness']
    assert 'residual_web_thickness' not in [
        k.get('field') for k in j.get('inputs_not_used') or []]


@pytest.mark.parametrize('ham, neden', [
    (-1, 'negative'), ('abc', 'not_a_json_number'),
    (True, 'not_a_json_number'), ([1], 'not_a_json_number'),
    ({'a': 1}, 'not_a_json_number'), (1e12, 'above_chamber_diameter_band'),
])
def test_aykiri_artik_et_422(istemci, ham, neden):
    r = istemci.post('/calculate', json=_govde(residual_web_thickness=ham))
    assert r.status_code == 422
    j = r.get_json()
    assert j['status'] == 'invalid_input'
    assert j['error_code'] == neden
    alan = j['invalid_fields'][0]
    assert alan['field'] == 'residual_web_thickness'
    assert alan['reason'] == neden
    assert 'motor' not in j


def test_kucuk_kamara_422_ve_cumle_basinda_gereken_cap(istemci):
    r = istemci.post('/calculate', json=_govde(chamber_diameter_input=50))
    assert r.status_code == 422
    j = r.get_json()
    assert j['error_code'] == 'grain_envelope_too_small_for_final_ports'
    alan = j['invalid_fields'][0]
    assert alan['field'] == 'chamber_diameter_input'
    gereken = '%.1f mm minimum' % alan['required_min']
    assert gereken in j['error'][:200], j['error']
    assert j['error'].startswith('No design was published')


def test_tasarim_modu_ucu_ayni_kapidan_gecer(istemci):
    r = istemci.post('/api/quick-geometry',
                     json=_govde(chamber_diameter_input=50))
    assert r.status_code == 422
    j = r.get_json()
    assert j['status'] == 'error'
    assert j['error'].startswith('No design was published')
    r = istemci.post('/api/quick-geometry',
                     json=_govde(residual_web_thickness=-3))
    assert r.status_code == 422
    assert r.get_json()['invalid_fields'][0]['reason'] == 'negative'
    r = istemci.post('/api/quick-geometry',
                     json=_govde(residual_web_thickness=3))
    assert r.status_code == 200
    g = r.get_json()['motor']['grain_design']
    assert g['residual_web_mm'] == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# ARAYÜZ (statik)
# ---------------------------------------------------------------------------

def test_form_alani_ve_getformdata_okumasi():
    s = SABLON.read_text(encoding='utf-8')
    assert re.search(r'<input type="number" id="residual_web_thickness"', s)
    assert "getElementById('residual_web_thickness')" in s
    assert 'data.residual_web_thickness' in s
    # Boş alan gövdeye girmez; optNum (0/negatifi düşüren) kullanılmaz.
    assert "optNum('residual_web_thickness')" not in s


def test_beyan_seridi_yanittan_dolar_ve_kancali():
    s = SABLON.read_text(encoding='utf-8')
    assert 'id="grainEnvelopeDecl"' in s
    assert 'try { _grainEnvelopeDecl(results); } catch (e) {}' in s
    govde = s[s.index('function _grainEnvelopeDecl'):]
    govde = govde[:govde.index('\n        }\n')]
    for alan in ('port_diameter_final_mm', 'grain_outer_diameter_mm',
                 'residual_web_mm', 'fuel_sliver_fraction'):
        assert 'g.' + alan in govde
    # Zorunlu alan yoksa şerit gizli kalır (uydurma sayı yok).
    assert 'return;' in govde


@pytest.mark.parametrize('anahtar', [
    'adv.label.residualWebMm', 'adv.unit.emptyZeroIdealised',
    'adv.tip.residualWebMm', 'adv.decl.grainEnvelope',
    'adv.decl.residualWebUser', 'adv.decl.residualWebDefault',
    'adv.decl.grainZeroWebIdealised',
])
def test_yeni_anahtarlar_iki_dilde(anahtar):
    s = SOZLUK.read_text(encoding='utf-8')
    assert s.count("'%s':" % anahtar) == 2, anahtar


def test_kamara_ipucu_eski_yanlis_cumleyi_tasimaz():
    """Eski ipucu 'Auto-calculation uses L* and throat area' diyordu;
    otomatik çap hiçbir zaman L*'tan gelmedi (1,5·√N·D_son idi)."""
    for yol in (SABLON, SOZLUK):
        s = yol.read_text(encoding='utf-8')
        assert 'Auto-calculation uses L* and throat area' not in s
        assert 'Otomatik hesap L* ile boğaz alanını kullanır' not in s
