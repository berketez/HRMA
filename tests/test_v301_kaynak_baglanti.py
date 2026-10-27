"""v3.0.1 K kulvarı — Berke ek maddesi: "online offline varsa sök, aynen
bağlandı bağlanmadı olmalı".

ÖLÇÜLEN KUSUR (taban c6fc59aad): ``/api/database-status`` NIST kolunda sayfa
GELDİĞİ hâlde (ayrıştırıcı NIST HTML'iyle eşleşmediği için) ``status =
'error'`` yayımlıyordu; arayüz bunu "NIST WebBook Offline" diye okuyordu.
CEA kolu ise yerel bir kütüphane olduğu hâlde bağlantı diliyle anlatılıyordu
("NASA CEA Offline"). Bekçiler:

* NIST: bağlantı (``connection``: 'connected' | 'not_connected') ve veri
  (``data_parsed``) AYRI alanlardır; "sayfa geldi, ayrıştırılamadı" bağlandı
  + ``data_parsed = False``'tur, 'error' DEĞİLDİR. HTTP 4xx/5xx de bir
  yanıttır (bağlandı); ``requests.Response`` bu kodlarda FALSY olduğu için
  ayrıca sınanır.
* CEA: bağlantı kavramı yoktur (``connection = 'not_applicable'``,
  ``kind = 'local_library'``, ``available`` = RocketCEA içe aktarılabiliyor
  mu); blokta bağlantı/çevrimdışı sözcüğü geçmez.
* Arayüz metinleri: üç tasarım sayfasında ve onların sözlüklerinde
  "Offline/Online/Çevrimdışı/Çevrimiçi" kullanıcı metni kalmadı (harita
  karoları launch_site sayfasındadır, kapsam dışı).
"""

import json
import pathlib
import re

import pytest
import requests

from hrma.data import database_integrations as di
from hrma.data.database_integrations import DatabaseManager, NistWebBookAPI

KOK = pathlib.Path(__file__).resolve().parents[1]
BAGLANTI_SOZCUKLERI = re.compile(
    r'\b(?:online|offline|connected|connection)\b', re.IGNORECASE)


class _Yanit:
    def __init__(self, kod, metin='<html><body>baska duzen</body></html>'):
        self.status_code = kod
        self.text = metin

    def raise_for_status(self):
        if self.status_code >= 400:
            hata = requests.HTTPError('%d Server Error' % self.status_code)
            hata.response = self
            raise hata

    def __bool__(self):                  # requests.Response ile aynı
        return self.status_code < 400


@pytest.fixture
def ag(monkeypatch):
    """``requests.Session.get``i istenen davranışa çeviren kurucu."""
    def kur(davranis):
        if isinstance(davranis, Exception):
            def _get(_self, *a, **k):
                raise davranis
        else:
            def _get(_self, *a, **k):
                return davranis
        monkeypatch.setattr(requests.Session, 'get', _get)
    return kur


# ---------------------------------------------------------------------------
# NIST — bağlandı / bağlanamadı ⟷ veri ayrıştırıldı mı
# ---------------------------------------------------------------------------
def test_ag_yoksa_baglanamadi(ag):
    ag(requests.exceptions.ConnectionError('ag kapali (test)'))
    n = DatabaseManager().test_connections()['nist']
    assert n['connection'] == 'not_connected' == n['status']
    assert n['data_parsed'] is False
    assert n['http_status'] is None
    assert 'ag kapali' in n['error']
    assert n['supplies_calculation_data'] is False


def test_zaman_asimi_baglanamadi(ag):
    ag(requests.exceptions.Timeout('zaman asimi (test)'))
    n = DatabaseManager().test_connections()['nist']
    assert n['connection'] == 'not_connected'


def test_sayfa_geldi_ayristirilamadi_hata_degil(ag):
    ag(_Yanit(200))
    n = DatabaseManager().test_connections()['nist']
    assert n['status'] != 'error'
    assert n['connection'] == 'connected' == n['status']
    assert n['http_status'] == 200
    assert n['data_parsed'] is False
    assert 'error' not in n
    assert n['supplies_calculation_data'] is False


def test_http_hata_kodu_da_bir_yanittir(ag):
    """503 bir YANITTIR: bağlandı, veri yok. (``Response`` 5xx'te falsy.)"""
    ag(_Yanit(503))
    n = DatabaseManager().test_connections()['nist']
    assert n['connection'] == 'connected'
    assert n['http_status'] == 503
    assert n['data_parsed'] is False


def test_ayristirilan_sayfa_veri_var(ag, monkeypatch):
    ag(_Yanit(200))
    monkeypatch.setattr(NistWebBookAPI, '_parse_nist_response',
                        lambda self, h, t: {'density': 785.1})
    n = DatabaseManager().test_connections()['nist']
    assert n['connection'] == 'connected'
    assert n['data_parsed'] is True
    # Erişilebilirlik köken değildir (P17B3-05 dersi korunur).
    assert n['supplies_calculation_data'] is False
    assert 'REACHABILITY ONLY' in n['message']


def test_veri_islevi_sozlesmesi_degismedi(ag):
    """``get_compound_properties`` VERİ hükmü aynı (P9B5-11): boş
    ayrıştırma 'success' değildir; yanına bağlantı olgusu eklenir."""
    ag(_Yanit(200))
    r = NistWebBookAPI().get_compound_properties('N2O', 293.15)
    assert r['status'] == 'error'
    assert r['connection'] == 'connected' and r['http_status'] == 200


# ---------------------------------------------------------------------------
# CEA — bağlantı kavramı yok
# ---------------------------------------------------------------------------
def test_cea_yerel_kutuphane(ag):
    ag(requests.exceptions.ConnectionError('ag kapali (test)'))
    c = DatabaseManager().test_connections()['cea']
    assert c['connection'] == 'not_applicable'
    assert c['kind'] == 'local_library'
    assert c['available'] is True
    assert c['status'] == DatabaseManager.CEA_LOCAL_STATUS == 'local'
    assert c['network_source'] is False
    assert 'RocketCEA' in c['library']


def test_cea_blogunda_baglanti_dili_yok(ag):
    ag(requests.exceptions.ConnectionError('ag kapali (test)'))
    c = DatabaseManager().test_connections()['cea']
    metin = json.dumps({k: v for k, v in c.items() if k != 'connection'})
    assert not BAGLANTI_SOZCUKLERI.search(metin), metin


def test_rocketcea_yoksa_kullanilamiyor(ag, monkeypatch):
    from hrma.engines import cea_bridge
    ag(requests.exceptions.ConnectionError('ag kapali (test)'))
    monkeypatch.setattr(cea_bridge, 'is_rocketcea_available', lambda: False)
    c = DatabaseManager().test_connections()['cea']
    assert c['available'] is False
    assert c['status'] == 'unavailable'
    assert c['connection'] == 'not_applicable'
    assert c['library'] is None
    metin = json.dumps({k: v for k, v in c.items() if k != 'connection'})
    assert not BAGLANTI_SOZCUKLERI.search(metin), metin


def test_uc_yeni_alanlari_yayimliyor(ag, monkeypatch):
    from hrma import app as app_module
    ag(_Yanit(200))
    monkeypatch.setattr(app_module, '_db_status_cache',
                        {'value': None, 'ts': 0.0})
    r = app_module.app.test_client().get(
        '/api/database-status?refresh=1',
        headers={'Sec-Fetch-Site': 'same-origin'})
    assert r.status_code == 200
    j = r.get_json()
    assert j['nist']['connection'] == 'connected'
    assert j['nist']['data_parsed'] is False
    assert j['cea']['connection'] == 'not_applicable'


# ---------------------------------------------------------------------------
# Arayüz metinleri — bağlantı durumu dili kalmadı
# ---------------------------------------------------------------------------
def _kod(metin):
    metin = re.sub(r'<!--.*?-->', '', metin, flags=re.S)
    metin = re.sub(r'\{#.*?#\}', '', metin, flags=re.S)
    metin = re.sub(r'/\*.*?\*/', '', metin, flags=re.S)
    return '\n'.join(re.sub(r'(^|\s)//.*$', r'\1', s)
                     for s in metin.split('\n'))


DURUM_DILI = re.compile(r'\b(?:Offline|Online|Çevrimdışı|çevrimdışı|'
                        r'Çevrimiçi|çevrimiçi)\b')


@pytest.mark.parametrize('bagil', [
    'hrma/templates/advanced.html', 'hrma/templates/solid.html',
    'hrma/templates/liquid.html', 'hrma/static/js/i18n_advanced.js',
    'hrma/static/js/i18n_pages.js',
])
def test_tasarim_sayfalarinda_durum_dili_yok(bagil):
    kod = _kod((KOK / bagil).read_text(encoding='utf-8'))
    bulunan = DURUM_DILI.findall(kod)
    assert not bulunan, (bagil, bulunan)
