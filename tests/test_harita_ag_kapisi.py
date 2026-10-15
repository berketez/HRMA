# -*- coding: utf-8 -*-
"""Harita K5a ağ kapısı bekçileri (gizlilik; temel ilke karar §28-33,
tasarım ``docs/scofield/raw/OH/UI/harita-detay/tasarim.md`` §4.1-2, §6 K5).

Kâhin: tasarım §4.1-2 ("Ağ anahtarı kapalıyken sunucu dış isteği reddeder
... Yanıt 403 {"network_disabled": true} ... Ayar okunamazsa kapı kapalı
sayılır") ve §4.3 A seçeneği (varsayılan KAPALI).

GERÇEK DIŞ İSTEK YOK: ağ katmanı (``urllib.request.urlopen``) taklit edilir
ve çağrı sayısı ölçülür. Önbellek dizini test başına geçici dizindir.
Taklit nesneler TEST ALTYAPISIDIR; kullanıcıya gösterilen veri değildir.
"""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import threading
import urllib.request

import pytest

from hrma.analysis import tile_cache as tc

KOK = pathlib.Path(__file__).resolve().parents[1]
GLOBE = KOK / 'hrma' / 'static' / 'js' / 'launch_site_globe.js'
SABLON = KOK / 'hrma' / 'templates' / 'launch_site.html'
NODE = shutil.which('node')

_SAHTE_JPEG = b'\xff\xd8\xff\xe0' + b'\x00' * 512 + b'\xff\xd9'


class _SahteYanit:
    status = 200
    headers = {'Content-Type': 'image/jpeg'}

    def read(self):
        return _SAHTE_JPEG

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def ag(tmp_path, monkeypatch):
    """Ağ katmanını taklit eder; her çağrının URL'sini kaydeder."""
    monkeypatch.setenv('HRMA_TILE_CACHE_DIR', str(tmp_path / 'tiles'))
    cagrilar = []

    def sahte_urlopen(istek, timeout=None):
        cagrilar.append(istek.full_url if hasattr(istek, 'full_url') else str(istek))
        return _SahteYanit()

    monkeypatch.setattr(urllib.request, 'urlopen', sahte_urlopen)
    return cagrilar


# ---------------------------------------------------------------------------
# Sunucu kapısı (tile_cache)
# ---------------------------------------------------------------------------

def test_varsayilan_kapali_dis_istek_sifir_403(ag):
    r = tc.resolve_tile('bluemarble', 5, 10, 5)
    assert ag == [], 'ağ anahtarı kapalıyken dış istek gitti'
    assert r['ok'] is False and r['code'] == 403
    assert r['network_disabled'] is True and r['available'] is False
    assert tc.cache_status()['tiles'] == 0, 'kapalıyken önbelleğe yazıldı'


@pytest.mark.parametrize('deger', [None, False, 1, '1', 'true', 'on', [True]])
def test_tam_true_disinda_her_deger_kapali(ag, deger):
    r = tc.resolve_tile('bluemarble', 5, 10, 5, allow_network=deger)
    assert ag == [] and r['code'] == 403, deger


def test_acikken_mevcut_gibs_katmani_eskisi_gibi(ag):
    r = tc.resolve_tile('bluemarble', 7, 159, 57, allow_network=True)
    assert r['ok'] is True and r['cached'] is False
    assert ag == [tc._gibs_url(tc.LAYERS['bluemarble'], 7, 159, 57, 'default')]
    assert ag[0].startswith('https://%s/' % tc.GIBS_HOST)
    assert '/BlueMarble_ShadedRelief_Bathymetry/default/500m/7/57/159.jpg' in ag[0]
    # İkinci çağrı önbellekten: kapalıyken de dış istek olmadan sunulur.
    r2 = tc.resolve_tile('bluemarble', 7, 159, 57)
    assert r2['ok'] is True and r2['cached'] is True
    assert len(ag) == 1


def test_izin_cagri_disina_sizmaz(ag):
    tc.resolve_tile('bluemarble', 5, 10, 5, allow_network=True)
    assert len(ag) == 1
    with pytest.raises(tc.NetworkDisabledError):
        tc._http_bytes('https://%s/x' % tc.GIBS_HOST)
    assert len(ag) == 1
    # Başka iş parçacığı izni miras almaz.
    sonuc = {}

    def calis():
        sonuc['r'] = tc.resolve_tile('bluemarble', 5, 11, 5)
    t = threading.Thread(target=calis)
    t.start()
    t.join()
    assert sonuc['r']['code'] == 403 and len(ag) == 1


def test_izinli_cagri_hata_verse_de_izin_kapanir(ag, monkeypatch):
    def patlayan(istek, timeout=None):
        raise OSError('ağ yok')
    monkeypatch.setattr(urllib.request, 'urlopen', patlayan)
    r = tc.resolve_tile('bluemarble', 5, 10, 5, allow_network=True)
    assert r['code'] == 503
    with pytest.raises(tc.NetworkDisabledError):
        tc._http_bytes('https://%s/x' % tc.GIBS_HOST)


@pytest.mark.parametrize('deger,beklenen', [
    ('1', True), (None, False), ('', False), ('0', False), ('true', False),
    ('on', False), ('1 ', False), (' 1', False), ('11', False), (1, False),
    (True, False), (['1'], False)])
def test_riza_degeri_fail_closed_okunur(deger, beklenen):
    assert tc.network_opt_in(deger) is beklenen


def test_riza_sozlesmesi_durum_ucunda_yayimlanir(ag):
    d = tc.cache_status()['network_opt_in']
    assert d == {'param': tc.NETWORK_OPT_IN_PARAM, 'value': tc.NETWORK_OPT_IN_VALUE,
                 'default': 'off'}


# ---------------------------------------------------------------------------
# HTTP ucu (app.py yalnız ayarı okur)
# ---------------------------------------------------------------------------

@pytest.fixture
def istemci(ag):
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.mark.parametrize('sorgu', ['', '?net=0', '?net=true', '?net=yes', '?net=',
                                   '?NET=1', '?net=1%20', '?ag=1'])
def test_uc_rizasiz_istekte_disari_cikmaz(istemci, ag, sorgu):
    y = istemci.get('/api/tile/bluemarble/5/10/5' + sorgu)
    assert y.status_code == 403, sorgu
    assert y.get_json()['network_disabled'] is True
    assert ag == [], sorgu


def test_uc_rizali_istekte_gibs_eskisi_gibi(istemci, ag):
    y = istemci.get('/api/tile/bluemarble/5/10/5?net=1')
    assert y.status_code == 200 and y.data == _SAHTE_JPEG
    assert len(ag) == 1 and ag[0].startswith('https://%s/' % tc.GIBS_HOST)
    # Önbellekte olan karo rızasız da sunulur; yeni dış istek yok.
    y2 = istemci.get('/api/tile/bluemarble/5/10/5')
    assert y2.status_code == 200 and len(ag) == 1


def test_durum_ucu_riza_sozlesmesini_tasir(istemci):
    d = istemci.get('/api/tile/cache/status').get_json()
    assert d['network_opt_in']['param'] == tc.NETWORK_OPT_IN_PARAM
    assert d['network_opt_in']['value'] == tc.NETWORK_OPT_IN_VALUE


# ---------------------------------------------------------------------------
# İstemci (launch_site_globe.js): parametre YALNIZ anahtar açıkken
# ---------------------------------------------------------------------------

def _blok(kaynak: str, bas: str, son: str) -> str:
    i = kaynak.index(bas)
    j = kaynak.index(son, i)
    return kaynak[i:j]


_NODE_GOVDE = r"""
const fs = require('fs');
const kaynak = fs.readFileSync(process.argv[2], 'utf8');
const blok = JSON.parse(fs.readFileSync(process.argv[3], 'utf8')).blok;
function kur(depo) {
  const global = { localStorage: depo };
  const f = new Function('global', blok +
    '\nreturn {tileAgAcik, tileAgYaz, tileAgRizasiOku, tileUrl};');
  return f(global);
}
function depo(baslangic, patla) {
  const m = new Map(Object.entries(baslangic || {}));
  return {
    getItem(k) { if (patla) throw new Error('engelli'); return m.has(k) ? m.get(k) : null; },
    setItem(k, v) { if (patla) throw new Error('engelli'); m.set(k, String(v)); },
    removeItem(k) { if (patla) throw new Error('engelli'); m.delete(k); },
  };
}
const R = { network_opt_in: { param: 'net', value: '1' } };
const s = {};
let g = kur(depo());
s.bos_depo = g.tileUrl('bluemarble', 5, 10, 5);
g.tileAgRizasiOku(R);
s.bos_depo_rizali = g.tileUrl('bluemarble', 5, 10, 5);
g = kur(depo({ hrma_tile_network: 'on' }));
s.acik_riza_yok = g.tileUrl('bluemarble', 5, 10, 5);
g.tileAgRizasiOku(R);
s.acik_rizali = g.tileUrl('bluemarble', 5, 10, 5);
g = kur(depo({ hrma_tile_network: 'on' }));
g.tileAgRizasiOku({ network_opt_in: { param: '../x', value: '1' } });
s.acik_bozuk_riza = g.tileUrl('bluemarble', 5, 10, 5);
g = kur(depo({ hrma_tile_network: 'true' }));
g.tileAgRizasiOku(R);
s.yanlis_deger = g.tileUrl('bluemarble', 5, 10, 5);
g = kur(depo({}, true));
g.tileAgRizasiOku(R);
g.tileAgYaz(true);
s.depo_engelli = g.tileUrl('bluemarble', 5, 10, 5);
s.depo_engelli_acik = g.tileAgAcik();
g = kur(undefined);
g.tileAgRizasiOku(R);
s.depo_yok = g.tileUrl('bluemarble', 5, 10, 5);
const d = depo();
g = kur(d);
g.tileAgRizasiOku(R);
g.tileAgYaz(true);
s.yaz_ac = g.tileUrl('bluemarble', 5, 10, 5);
g.tileAgYaz(false);
s.yaz_kapa = g.tileUrl('bluemarble', 5, 10, 5);
console.log(JSON.stringify(s));
"""


@pytest.mark.skipif(NODE is None, reason='node yok')
def test_istemci_riza_parametresini_yalniz_anahtar_acikken_ekler(tmp_path):
    kaynak = GLOBE.read_text(encoding='utf-8')
    blok = _blok(kaynak, 'var TILE_NETWORK_STORAGE_KEY', '    function tileGeomYukle()')
    assert 'function tileUrl' in blok
    (tmp_path / 'b.json').write_text(json.dumps({'blok': blok}), encoding='utf-8')
    js = tmp_path / 'k.js'
    js.write_text(_NODE_GOVDE, encoding='utf-8')
    r = subprocess.run([NODE, str(js), str(GLOBE), str(tmp_path / 'b.json')],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    s = json.loads(r.stdout)
    duz = '/api/tile/bluemarble/5/10/5'
    assert s['bos_depo'] == duz and s['bos_depo_rizali'] == duz
    assert s['acik_riza_yok'] == duz, 'rıza sözleşmesi okunmadan parametre eklendi'
    assert s['acik_rizali'] == duz + '?net=1'
    assert s['acik_bozuk_riza'] == duz
    assert s['yanlis_deger'] == duz
    assert s['depo_engelli'] == duz and s['depo_engelli_acik'] is False
    assert s['depo_yok'] == duz
    assert s['yaz_ac'] == duz + '?net=1' and s['yaz_kapa'] == duz


def test_istemci_karo_istegi_tek_url_kurucudan_gecer():
    kaynak = GLOBE.read_text(encoding='utf-8')
    kurucu = _blok(kaynak, 'LaunchSiteGlobe.prototype._buildTilePatch',
                   'LaunchSiteGlobe.prototype._makeTileMesh')
    assert 'tileUrl(layer, z, tx, ty)' in kurucu
    assert "'/api/tile/'" not in kurucu, 'karo URL\'si kapıyı atlayarak kuruluyor'
    assert kaynak.count("'/api/tile/' +") == 1


def test_sablon_anahtari_kureye_bagli_ve_metin_innerhtml_degil():
    html = SABLON.read_text(encoding='utf-8')
    assert 'id="ls-tile-network"' in html
    assert 'globe.setTileNetwork(' in html and 'globe.getTileNetwork(' in html
    for anahtar in ('site.tileNetworkToggle', 'site.tileNetworkWarn',
                    'site.tileNetworkOffNote'):
        assert 'data-i18n="%s"' % anahtar in html
    k5 = _blok(html, '// K5a — ağ anahtarı. Durum', '// ---- Saha seçimi kontrolleri')
    assert 'innerHTML' not in k5
