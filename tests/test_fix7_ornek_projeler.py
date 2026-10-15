# -*- coding: utf-8 -*-
"""ÖH D17 fix-7 — ürünle gelen örnek projeler hesaplanabilir kalır.

Ölçüldü (taban kaydı-2, main 2a6862b, 2 Eyl 2026): ``examples/Example Hybrid
N2O-HTPB 3kN.hrma`` ``/calculate``'ten HTTP 400 alıyordu —
``chamber_diameter_input: 0`` (arayüz varsayılanı, "0 = otomatik") D17
P16B1-09'un doğrudan gövdeye uyguladığı ``must_be_positive`` bandına
takılmıştı. Sözleşme: süpürme ekseninde 0 anlamsız (parametrik kapı aynı),
doğrudan gövdede 0 "çözücü çözer" (``_CALCULATE_ZERO_MEANS_AUTO``); negatif
yine adıyla reddedilir; kullanılan çap ``inputs_not_used`` ile beyan edilir.
Ters mutasyon: ``_CALCULATE_ZERO_MEANS_AUTO = frozenset()`` → örnek hibrit
proje 400, ``test_sifir_hazne_capi_otomatik`` KIRMIZI.
"""
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / 'examples'
HEADERS = {'Content-Type': 'application/json'}
ORNEKLER = {
    'hybrid': ('Example Hybrid N2O-HTPB 3kN', '/calculate'),
    'solid': ('Example Solid KNDX BATES 75mm', '/calculate_solid'),
    'liquid': ('Example Liquid LOX-RP1 25kN', '/calculate_liquid'),
}


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _ornek(ad):
    return json.loads((EXAMPLES_DIR / (ad + '.hrma')).read_text(encoding='utf-8'))


@pytest.mark.parametrize('motor_type', sorted(ORNEKLER))
def test_ornek_proje_hesaplanir(client, motor_type):
    ad, uc = ORNEKLER[motor_type]
    proje = _ornek(ad)
    r = client.post(uc, json=dict(proje['inputs']['fields']), headers=HEADERS)
    assert r.status_code == 200, f'{ad}: {uc} {r.status_code} {r.get_data(as_text=True)[:400]}'


def test_sifir_hazne_capi_otomatik(client):
    """0 = otomatik: 200 + kullanılan çap beyanı; sayı sessizce yutulmaz."""
    ad, uc = ORNEKLER['hybrid']
    govde = dict(_ornek(ad)['inputs']['fields'])
    govde['chamber_diameter_input'] = 0
    r = client.post(uc, json=govde, headers=HEADERS)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    j = r.get_json()
    beyan = [b for b in (j.get('inputs_not_used') or []) if b.get('field') == 'chamber_diameter_input']
    assert beyan, ('0 gönderilip çözülen hazne çapı inputs_not_used ile beyan edilmeli; '
                   f"beyanlar: {j.get('inputs_not_used')}")
    # Beyan kullanıcının birimiyle (mm) konuşur ve motorun çözdüğü çapla eşittir.
    assert beyan[0]['used_by_model'] == pytest.approx(j['motor']['chamber_diameter'] * 1000.0)
    assert beyan[0]['message'].rstrip('.').endswith('mm')
    from hrma.app import _CALCULATE_ZERO_MEANS_AUTO
    assert 'chamber_diameter_input' in _CALCULATE_ZERO_MEANS_AUTO


def test_negatif_hazne_capi_adiyla_reddedilir(client):
    ad, uc = ORNEKLER['hybrid']
    govde = dict(_ornek(ad)['inputs']['fields'])
    govde['chamber_diameter_input'] = -50.0
    r = client.post(uc, json=govde, headers=HEADERS)
    assert r.status_code == 400
    j = r.get_json()
    kayit = [k for k in j['invalid_fields'] if k['field'] == 'chamber_diameter_input']
    # Ölçüldü: doğrulayıcının mm bandı ([10; 5000] mm, ``out_of_range``,
    # resolved_as=chamber_diameter) işaret kapısından ÖNCE yakalıyor; işaret
    # kapısı yalnız bandsız adlarda ``must_be_non_negative`` der. İkisi de
    # adlı rettir; sessiz 200 ya da ham 500 olmaması kilitlenir.
    assert kayit and kayit[0]['reason'] in ('must_be_non_negative', 'out_of_range'), j['invalid_fields']
