"""Emekli uçların sözleşme bekçisi (v2.6.27, teknik borç §4).

BULGU (mimari tarama, 14-15 Ağustos 2026): /api/cfd-analysis,
/api/kinetic-analysis ve /api/professional-analysis HTTP 501 dönüyordu ama
çözücüleri (`cfd_analysis.py` ~kütle korunumsuz/ıraksak, `kinetic_analysis.py`
~23 dk/istasyon) her açılışta yükleniyordu — ~2 100 satır ölü ağırlık.
Açılış importları ve 501 sonrası erişilemez gövdeler söküldü; dosyalar
depoda duruyor (kaldırma/legacy kararı ayrı).

Bu dosya iki sözleşmeyi kilitler: (1) emekli modüller uygulama importuyla
YÜKLENMEZ, (2) uçlar 501 + halef yönlendirmesi döndürmeye devam eder
(istemci sözleşmesi bozulmaz).
"""

import sys

import pytest

LOCAL_HOST = {'Host': '127.0.0.1:8080'}

EMEKLI_UCLAR = (
    '/api/cfd-analysis',
    '/api/kinetic-analysis',
    '/api/professional-analysis',
)


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def test_emekli_moduller_acilista_yuklenmez(client):
    """`import hrma.app` emekli çözücüleri belleğe ÇEKMEMELİ.

    Bekçi geri gelen importu yakalar: app.py ya da analysis/__init__.py
    yeniden `from ... import cfd_analyzer` yazarsa bu test kırılır.
    (client fixture'ı uygulamayı zaten import etti; sys.modules kanıttır.)
    """
    yuklu = [m for m in sys.modules
             if m.endswith('cfd_analysis') or m.endswith('kinetic_analysis')]
    assert not yuklu, (
        'Emekli çözücüler uygulama açılışında yüklendi: %s — 501 dönen ucun '
        'çözücüsü belleğe çekilmez (teknik borç §4 kapanışı).' % yuklu)


@pytest.mark.parametrize('uc', EMEKLI_UCLAR)
def test_emekli_uc_501_ve_halef_yonlendirmesi(client, uc):
    """501 + `successor` alanı: istemci sözleşmesi gövde sökümünden etkilenmez."""
    r = client.post(uc, json={}, headers=LOCAL_HOST)
    assert r.status_code == 501
    b = r.get_json()
    assert b.get('status') == 'unavailable'
    assert b.get('successor'), 'yönlendirme alanı kayboldu'
    assert 'error' in b
