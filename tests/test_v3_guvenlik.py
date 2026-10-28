"""V3 SG-2 bölüm A bekçileri: ağ kapıları, kaynak tavanları, XXE beyanı.

Karar §28-33 (Berke, 12 Eki) ve düzeltmesi: güvenlik HRMA'nın her zaman
geçerli temel ilkesidir; SG-0 denetiminin bulduğu açıklar özellik eksiği
değil KUSURDUR. Rapor: ``docs/scofield/raw/OH/V3/guvenlik/SG0_saldiri_yuzeyi.md``;
bu turun raporu ``.../SG2_rapor.md`` (Bölüm A), ters mutasyon kaydı
``.../sg2a/mutasyon.md``.

Kalemler:

* SG-02 — portsuz Origin'in portu şemadan türetilir (http 80, https 443) ve
  sunucunun kendi portuyla karşılaştırılır; ``hrma/run.py`` sunucunun
  portunu üç başlatma dalının hepsinden önce kapıya bildirir.
* SG-06 — yan etkili GET uçları (``tile_proxy``, ``correlation_report``,
  ``update_check``) Sec-Fetch-Site / Origin denetiminden geçer; ret
  durumunda ucun yan etkisi (disk, ağır koşu, dış ağ) HİÇ çalışmaz.
* SG-03 — ``/api/comparative-analysis`` ve ``/api/validate-fuel`` kalem
  sayısı tavanı + 413 beyanı (adlandırılmış sabitler).
* SG-01 — defusedxml olmadan da XXE kapalı; kaynaktaki beyan bunu söyler.
* SG-07 (yan bulgu) — gövde bayt tavanı (``MAX_CONTENT_LENGTH``) aşımı her
  ölçülebilir uçta gövde okunmadan JSON 413 (beyan ⟷ gerçek).

Bütün istekler Flask ``test_client``; gerçek sunucu, disk yan etkisi ve
dış ağ yok (yan etkili fonksiyonlar kayıt tutan yerine geçenlerle
değiştirilir).
"""
import base64
import gzip
import io
import json
import os
import re
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault('HRMA_HEADLESS', '1')

import hrma.app as app_module  # noqa: E402
from hrma.app import app  # noqa: E402
from hrma.security import limits, origin_gate  # noqa: E402

SELF_PORT = 8080
SELF_HOST = f'127.0.0.1:{SELF_PORT}'


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def self_port_known(monkeypatch):
    """Paketli başlatıcı / hrma/run.py yolu: sunucunun portu biliniyor."""
    monkeypatch.setitem(app.config, origin_gate.SELF_PORT_CONFIG_KEY,
                        SELF_PORT)


def _state_change(client, origin):
    """Ucuz, yan etkisiz bir durum değiştiren (POST) çağrı."""
    headers = {'Host': SELF_HOST}
    if origin is not None:
        headers['Origin'] = origin
    return client.post('/api/altitude-to-pressure', json={'altitude': 1000},
                       headers=headers)


# ===========================================================================
# SG-02 — portsuz Origin
# ===========================================================================

class TestSG02PortsuzOrigin:
    """Portsuz Origin "port yok" değil, şemanın varsayılan portudur."""

    @pytest.mark.parametrize('raw, beklenen', [
        ('http://localhost', ('http', 'localhost', 80)),
        ('https://localhost', ('https', 'localhost', 443)),
        ('http://[::1]', ('http', '::1', 80)),
        ('http://127.0.0.1', ('http', '127.0.0.1', 80)),
        ('HTTP://LOCALHOST:8080', ('http', 'localhost', 8080)),
        ('http://127.0.0.1:8081', ('http', '127.0.0.1', 8081)),
        ('ftp://127.0.0.1', ('ftp', '127.0.0.1', None)),
        ('null', (None, None, None)),
        ('http://127.0.0.1:abc', (None, None, None)),
    ])
    def test_etkin_port_semadan_turetilir(self, raw, beklenen):
        assert origin_gate.origin_parts(raw) == beklenen

    @pytest.mark.parametrize('origin', [
        'http://localhost', 'http://127.0.0.1', 'https://localhost',
        'http://[::1]', 'https://127.0.0.1', 'ftp://127.0.0.1',
    ])
    def test_portsuz_yabanci_port_reddedilir(self, client, self_port_known,
                                             origin):
        """ÖNCE (SG-0 ölçümü): bu kökenler SELF_PORT=8080 iken 200 alıyordu."""
        r = _state_change(client, origin)
        assert r.status_code == 403, (origin, r.status_code)
        assert r.get_json()['reason'] == 'origin_port_mismatch'

    @pytest.mark.parametrize('origin', [
        None, f'http://127.0.0.1:{SELF_PORT}', f'http://localhost:{SELF_PORT}',
        f'http://[::1]:{SELF_PORT}',
    ])
    def test_kendi_portu_gecer(self, client, self_port_known, origin):
        r = _state_change(client, origin)
        assert r.status_code == 200, (origin, r.status_code, r.get_data()[:200])

    def test_https_kendi_portu_gecer(self, client, monkeypatch):
        """Etkin port eşitliği şemadan bağımsız: https://127.0.0.1 = 443."""
        monkeypatch.setitem(app.config, origin_gate.SELF_PORT_CONFIG_KEY, 443)
        r = client.post('/api/altitude-to-pressure', json={'altitude': 1000},
                        headers={'Host': '127.0.0.1:443',
                                 'Origin': 'https://127.0.0.1'})
        assert r.status_code == 200

    @pytest.mark.parametrize('origin', [
        'http://evil.example', 'null', 'http://192.168.1.50:8080',
    ])
    def test_uzak_koken_hala_reddedilir(self, client, self_port_known, origin):
        """Mevcut koruma bozulmadı (SG-0 envanteri)."""
        r = _state_change(client, origin)
        assert r.status_code == 403
        assert r.get_json()['reason'] == 'origin_not_loopback'

    def test_host_kapisi_hala_once_calisir(self, client, self_port_known):
        r = client.post('/api/altitude-to-pressure', json={'altitude': 1000},
                        headers={'Host': 'evil.example:8080',
                                 'Origin': 'http://127.0.0.1:8080'})
        assert r.status_code == 403
        assert r.get_json()['reason'] == 'host_not_loopback'


def _self_port_ortami_yok(monkeypatch):
    """``HRMA_SELF_PORT`` ortam değişkenini KAYITLI biçimde kaldırır (Ş3).

    SG-2 şart turu (13 Eki, denetim uyumsuz 3): ``monkeypatch.delenv(...,
    raising=False)`` değişken zaten YOKKEN geri alma kaydı tutmaz. Testin
    içinde ``register_self_port`` ``os.environ``'a yazınca değer test
    bitince sürece SIZIYORDU (ölçüldü: iki port bekçisinden sonra aynı
    süreçte ``'8087'``; sıra bağımlılığı sınıfı). ``setenv`` özgün durumu
    (yok ya da değer) kaydeder; ardından gelen ``delenv`` her zaman
    kayıtlıdır. Geri almada kayıtlar ters sırayla açılır: önce ara değer,
    sonra özgün durum (yoksa silinir).
    """
    monkeypatch.setenv(origin_gate.SELF_PORT_ENV, '')
    monkeypatch.delenv(origin_gate.SELF_PORT_ENV)


class TestSG02RunPyPortuBildirir:
    """``hrma/run.py`` üç sunucu dalının HER birinde kapı portu bilmeli.

    ÖNCE: ``run.py`` HRMA_SELF_PORT'u hiç atamıyordu (SG-0
    ``sg_ag_kapilar.json`` → ``statik``); kaynaktan çalıştırmada kapı
    127.0.0.1'in her portuna açıktı. Davranış ölçülür: sunucu başlatma
    çağrıları yakalanır, çağrı anında ``app.config`` ve ortam okunur.
    """

    PORT = 8087

    @pytest.fixture
    def run_mod(self, monkeypatch):
        import hrma.run as run_mod
        monkeypatch.setenv('HRMA_PORT', str(self.PORT))
        _self_port_ortami_yok(monkeypatch)
        monkeypatch.setitem(app.config, origin_gate.SELF_PORT_CONFIG_KEY,
                            None)
        # Tarayıcı zamanlayıcısı kurulmaz (BROWSER açılmaz).
        monkeypatch.setattr(run_mod, 'Timer',
                            lambda *a, **k: type('T', (), {'start': lambda s: None})())
        return run_mod

    def _yakala(self, monkeypatch, run_mod, platform_adi, waitress_var):
        gorulen = []

        def kayit(*args, **kwargs):
            gorulen.append({
                'config': app.config.get(origin_gate.SELF_PORT_CONFIG_KEY),
                'env': os.environ.get(origin_gate.SELF_PORT_ENV),
                'port': kwargs.get('port'),
            })

        monkeypatch.setattr(app, 'run', kayit)
        if waitress_var:
            sahte = type(sys)('waitress')
            sahte.serve = kayit
            monkeypatch.setitem(sys.modules, 'waitress', sahte)
        else:
            monkeypatch.setitem(sys.modules, 'waitress', None)
        monkeypatch.setattr(run_mod.platform, 'system', lambda: platform_adi)
        run_mod.run_server()
        return gorulen

    @pytest.mark.parametrize('platform_adi, waitress_var', [
        ('Windows', True),      # waitress dalı
        ('Windows', False),     # Windows yedek (Flask) dalı
        ('Darwin', True),       # Unix dalı
    ])
    def test_her_dalda_self_port_dolu(self, monkeypatch, run_mod,
                                      platform_adi, waitress_var):
        gorulen = self._yakala(monkeypatch, run_mod, platform_adi,
                               waitress_var)
        assert len(gorulen) == 1, gorulen
        assert gorulen[0]['port'] == self.PORT
        assert gorulen[0]['config'] == self.PORT
        assert gorulen[0]['env'] == str(self.PORT)


# ===========================================================================
# SG-06 — yan etkili GET uçları
# ===========================================================================

class _Kayit:
    def __init__(self, donus):
        self.cagri = 0
        self.donus = donus

    def __call__(self, *args, **kwargs):
        self.cagri += 1
        return self.donus


#: ``db_manager.test_connections`` yerine geçenin döndürdüğü gövde (uç
#: ``{'nist', 'cea'}`` anahtarlarını yankılar; gerçek NIST isteği YOK).
SG06_DB_STUB = {'nist': {'status': 'stub'}, 'cea': {'status': 'stub'}}

#: Arayüzün veri tabanı rozeti çağrısının kaynaktaki biçimi (göreli yol =
#: sayfanın kendi kökeni, Sec-Fetch-Site: same-origin).
SG06_DB_GORELI_CAGRI = "fetch('/api/database-status')"


@pytest.fixture
def yan_etkiler(monkeypatch):
    """Üç ucun yan etkili fonksiyonunu kayıt tutan yerine geçenle değiştirir.

    Disk yazımı (karo önbelleği), ağır korelasyon koşusu ve dış ağ (GitHub)
    bu testte HİÇ çalışmaz; yalnız ucun görünümüne ulaşılıp ulaşılmadığı
    sayılır.

    SG-2 şart turu (13 Eki, Ş1) dördüncü ucu ekledi: ``check_database_status``
    (canlı NIST isteği ``db_manager.test_connections``). Ucun önbelleği her
    testte SOĞUK kurulur (``monkeypatch`` geri alır): düz yol da görünüme
    ulaşırsa yan etkiyi çalıştırır, sayaç bunu görür.
    """
    from hrma.analysis import tile_cache
    from hrma.utils import update_checker
    k = {
        'tile_proxy': _Kayit({'ok': False, 'code': 503, 'error': 'stub'}),
        'correlation_report': _Kayit({'status': 'stub'}),
        'update_check': _Kayit({'status': 'stub'}),
        'check_database_status': _Kayit(dict(SG06_DB_STUB)),
    }
    monkeypatch.setattr(tile_cache, 'resolve_tile', k['tile_proxy'])
    monkeypatch.setattr(app_module, '_correlation_report_body',
                        k['correlation_report'])
    monkeypatch.setattr(update_checker, 'check_for_update', k['update_check'])
    monkeypatch.setattr(app_module.db_manager, 'test_connections',
                        k['check_database_status'])
    monkeypatch.setattr(app_module, '_db_status_cache',
                        {'value': None, 'ts': 0.0})
    return k


#: Somut GET yolu -> Flask uç adı. Anahtar YOL olduğu için rota çağrıları
#: ``parametrize('yol', sorted(...))`` ile statik olarak çözülür
#: (tests/test_d24_bekci_cevirisi_a1.py çözülemeyen-çağrı tavanı).
YAN_ETKILI_YOLLAR = {
    '/api/tile/bluemarble/0/0/0': 'tile_proxy',
    '/api/correlation-report': 'correlation_report',
    '/api/update/check': 'update_check',
    # SG-2 şart turu (Ş1). Anahtar sorgusuz yol: ``url_map.match`` sorgu
    # dizgesini çözmez (``test_kume_uc_adlariyla_ayni``); fikstür önbelleği
    # soğuk kurduğu için düz yol da yan etkiye ulaşır. ``?refresh=1`` (sıcak
    # önbellekte bile canlı istek) aşağıda ``test_db_tazeleme_*`` ile ayrıca.
    '/api/database-status': 'check_database_status',
}


class TestSG06YanEtkiliGet:

    def test_kume_uc_adlariyla_ayni(self):
        """Küme Flask'taki GERÇEK uç adlarını göstermeli (ad kayması bekçisi)."""
        adlar = {r.endpoint for r in app.url_map.iter_rules()}
        assert set(origin_gate.SIDE_EFFECT_GET_ENDPOINTS) <= adlar
        assert (set(YAN_ETKILI_YOLLAR.values())
                == set(origin_gate.SIDE_EFFECT_GET_ENDPOINTS))
        for yol, uc in YAN_ETKILI_YOLLAR.items():
            eslesen = app.url_map.bind('localhost').match(yol, method='GET')
            assert eslesen[0] == uc

    @pytest.mark.parametrize('yol', sorted(YAN_ETKILI_YOLLAR))
    @pytest.mark.parametrize('site', ['cross-site', 'same-site', 'bogus'])
    def test_capraz_site_reddedilir_yan_etki_calismaz(self, client, yan_etkiler,
                                                      yol, site):
        uc = YAN_ETKILI_YOLLAR[yol]
        r = client.get(yol,
                       headers={'Host': SELF_HOST, 'Sec-Fetch-Site': site})
        assert r.status_code == 403, (uc, site, r.status_code)
        assert r.get_json()['reason'] == 'fetch_site_not_same_origin'
        assert yan_etkiler[uc].cagri == 0, f'{uc} yan etkisi çalıştı'

    @pytest.mark.parametrize('yol', sorted(YAN_ETKILI_YOLLAR))
    def test_head_de_denetlenir(self, client, yan_etkiler, yol):
        uc = YAN_ETKILI_YOLLAR[yol]
        r = client.head(yol,
                        headers={'Host': SELF_HOST,
                                 'Sec-Fetch-Site': 'cross-site'})
        assert r.status_code == 403
        assert yan_etkiler[uc].cagri == 0

    @pytest.mark.parametrize('yol', sorted(YAN_ETKILI_YOLLAR))
    @pytest.mark.parametrize('origin, neden', [
        ('http://127.0.0.1:5173', 'origin_port_mismatch'),
        ('http://localhost', 'origin_port_mismatch'),
        ('http://evil.example', 'origin_not_loopback'),
        ('null', 'origin_not_loopback'),
    ])
    def test_yabanci_origin_reddedilir(self, client, yan_etkiler,
                                       self_port_known, yol, origin, neden):
        uc = YAN_ETKILI_YOLLAR[yol]
        r = client.get(yol,
                       headers={'Host': SELF_HOST, 'Origin': origin})
        assert r.status_code == 403
        assert r.get_json()['reason'] == neden
        assert yan_etkiler[uc].cagri == 0

    @pytest.mark.parametrize('yol', sorted(YAN_ETKILI_YOLLAR))
    @pytest.mark.parametrize('basliklar', [
        {},                                         # başlıksız yerel istek
        {'Sec-Fetch-Site': 'same-origin'},          # arayüzün kendi fetch'i
        {'Sec-Fetch-Site': 'none'},                 # adres çubuğu / yer imi
        {'Sec-Fetch-Site': 'same-origin',
         'Origin': f'http://127.0.0.1:{SELF_PORT}'},
    ])
    def test_ayni_koken_ve_basliksiz_gecer(self, client, yan_etkiler,
                                           self_port_known, yol, basliklar):
        uc = YAN_ETKILI_YOLLAR[yol]
        h = {'Host': SELF_HOST, **basliklar}
        r = client.get(yol, headers=h)
        assert r.status_code != 403, (uc, basliklar, r.get_data()[:200])
        assert yan_etkiler[uc].cagri == 1

    @pytest.mark.parametrize('yol', ['/api/projects', '/api/update/status',
                                     '/api/tile/cache/status'])
    def test_okuma_uclari_etkilenmez(self, client, yol):
        """Kapı hedefli: yan etkisiz GET'ler eskisi gibi Origin'den bağımsız."""
        r = client.get(yol, headers={'Host': SELF_HOST,
                                     'Sec-Fetch-Site': 'cross-site',
                                     'Origin': 'http://evil.example'})
        assert r.status_code != 403, (yol, r.status_code)

    def test_options_on_ucusu_gorunum_calistirmaz(self, client, yan_etkiler):
        r = client.open('/api/update/check', method='OPTIONS',
                        headers={'Host': SELF_HOST,
                                 'Sec-Fetch-Site': 'cross-site'})
        assert r.status_code != 403
        assert yan_etkiler['update_check'].cagri == 0
        assert r.headers.get('Access-Control-Allow-Origin') is None

    # --- SG-2 şart turu (13 Eki, Ş1): /api/database-status?refresh=1 ---
    # ÖNCE (sgs/sonuc/db_status_once.json): aşağıdaki her vakada 200 ve
    # canlı NIST çağrısı 1; gerçek Chromium'da başka porttaki sayfa 200,
    # yan etki 2 (sgs/sonuc/db_tarayici_once.json).

    @pytest.fixture
    def db_sicak(self, monkeypatch, yan_etkiler):
        """Önbellek SICAK (arayüzün ikinci açılışı): yalnız ``?refresh=1``
        canlı isteği zorlar. Döndürdüğü kayıt ``test_connections`` çağrı
        sayacıdır."""
        import time
        monkeypatch.setattr(app_module, '_db_status_cache',
                            {'value': dict(SG06_DB_STUB),
                             'ts': time.monotonic()})
        return yan_etkiler['check_database_status']

    @pytest.mark.parametrize('site', ['cross-site', 'same-site', 'bogus'])
    def test_db_tazeleme_capraz_site_reddedilir(self, client, db_sicak, site):
        r = client.get('/api/database-status?refresh=1',
                       headers={'Host': SELF_HOST, 'Sec-Fetch-Site': site})
        assert r.status_code == 403, (site, r.status_code)
        assert r.get_json()['reason'] == 'fetch_site_not_same_origin'
        assert db_sicak.cagri == 0, 'canlı NIST isteği çalıştı'

    @pytest.mark.parametrize('site', ['same-site', 'cross-site'])
    def test_db_tazeleme_head_de_denetlenir(self, client, db_sicak, site):
        r = client.head('/api/database-status?refresh=1',
                        headers={'Host': SELF_HOST, 'Sec-Fetch-Site': site})
        assert r.status_code == 403, (site, r.status_code)
        assert db_sicak.cagri == 0, 'canlı NIST isteği çalıştı'

    @pytest.mark.parametrize('basliklar', [
        {},                                         # başlıksız yerel istek
        {'Sec-Fetch-Site': 'same-origin'},          # arayüzün kendi fetch'i
        {'Sec-Fetch-Site': 'none'},                 # adres çubuğu / yer imi
    ])
    def test_db_tazeleme_ayni_koken_ve_basliksiz_gecer(self, client, db_sicak,
                                                       basliklar):
        r = client.get('/api/database-status?refresh=1',
                       headers={'Host': SELF_HOST, **basliklar})
        assert r.status_code == 200, (basliklar, r.get_data()[:200])
        assert r.get_json() == SG06_DB_STUB
        assert db_sicak.cagri == 1


class TestSG06ArayuzCagrilariAyniKoken:
    """Arayüzün bu uçları çağırdığı her yer GÖRELİ yol kullanmalı.

    Göreli yol = sayfanın kendi kökeni (Sec-Fetch-Site: same-origin). Mutlak
    bir ``http://`` adresi (ör. localhost <-> 127.0.0.1) tarayıcıda
    cross-site sayılır ve yeni kapıda 403 alırdı.
    """

    #: (dosya, ucun göreli yolu kaynakta nasıl geçiyor)
    CAGRI_YERLERI = [
        ('hrma/static/js/launch_site_globe.js', "'/api/tile/'"),
        ('hrma/static/js/update_check.js', "fetch('/api/update/check')"),
        ('hrma/static/js/settings_panel.js', "fetch('/api/update/check')"),
        ('hrma/static/js/panels/correlation_panel.js',
         "ENDPOINT = '/api/correlation-report'"),
        # SG-2 şart turu (Ş1): veri tabanı rozeti üç sayfada (advanced,
        # liquid, solid) /api/database-status'u çağırıyordu. v3.0.1 K kulvarı
        # (Ayberk tur 1): rozet HER makinede yanlışlıkla "Offline" dediği ve
        # hiçbir sayının kaynağı olmadığı için söküldü; üç çağrı yeri de
        # kalktı. Uç API uyumu için sunucuda durur ve yan etki kapısı
        # (TestSG06YanEtkiliGet) onu ölçmeye devam eder. Aşağıdaki
        # ``test_db_durumu_her_cagri_goreli`` artık BOŞ çağıran kümesini
        # kilitler: yeni bir ön yüz çağrısı listeye (göreli biçimde)
        # girmeden geçemez.
    ]

    @pytest.mark.parametrize('dosya, desen', CAGRI_YERLERI)
    def test_cagri_yeri_goreli(self, dosya, desen):
        assert desen in (ROOT / dosya).read_text(encoding='utf-8')

    def test_mutlak_adresle_cagri_yok(self):
        kotu = re.compile(r"https?://[^'\"\s]*/api/(tile/|update/check|"
                          r"correlation-report)")
        bulunan = []
        for p in list((ROOT / 'hrma/static').rglob('*.js')) + list(
                (ROOT / 'hrma/templates').rglob('*.html')):
            if 'vendor' in p.parts:
                continue
            for i, satir in enumerate(
                    p.read_text(encoding='utf-8', errors='replace')
                    .splitlines(), 1):
                if kotu.search(satir):
                    bulunan.append(f'{p.relative_to(ROOT)}:{i}')
        assert not bulunan, bulunan

    def test_db_durumu_her_cagri_goreli(self):
        """Ş1: ``/api/database-status``'u ``fetch`` ile çağıran HER ön yüz
        satırı göreli biçimdedir ve çağıran dosya kümesi yukarıdaki listeyle
        aynıdır (yeni bir çağrı yeri listeye girmeden geçemez); mutlak
        adresle çağrı yok."""
        mutlak = re.compile(r"https?://[^'\"\s]*/api/database-status")
        fetch_cagrisi = re.compile(r"fetch\([^)]*/api/database-status")
        beklenen = {d for d, desen in self.CAGRI_YERLERI
                    if desen == SG06_DB_GORELI_CAGRI}
        cagiran, kotu = set(), []
        for p in list((ROOT / 'hrma/static').rglob('*.js')) + list(
                (ROOT / 'hrma/templates').rglob('*.html')):
            if 'vendor' in p.parts:
                continue
            for i, satir in enumerate(
                    p.read_text(encoding='utf-8', errors='replace')
                    .splitlines(), 1):
                yer = f'{p.relative_to(ROOT)}:{i}'
                if mutlak.search(satir):
                    kotu.append(yer)
                if fetch_cagrisi.search(satir):
                    cagiran.add(str(p.relative_to(ROOT)))
                    if SG06_DB_GORELI_CAGRI not in satir:
                        kotu.append(yer)
        assert not kotu, kotu
        assert cagiran == beklenen, (cagiran, beklenen)


# ===========================================================================
# SG-03 — kalem sayısı tavanları
# ===========================================================================

def _configs(n):
    return {f'm{i}': {'thrust': 1000.0 + i, 'isp': 250.0, 'total_mass': 10.0}
            for i in range(n)}


def _composition(n):
    return [{'formula': 'C', 'percentage': 100.0 / n} for _ in range(n)]


class TestSG03KalemTavani:

    def test_tavanlar_adlandirilmis_ve_makul(self):
        # Gerçek kullanım (limits.py künyesi): panel elle eklenen anlık
        # görüntü, örnek projelerde 0; CEA reaktan tablosu MAXR = 24.
        assert limits.COMPARATIVE_MAX_CONFIGS >= 64
        assert limits.FUEL_COMPOSITION_MAX_ITEMS > 24
        assert limits.BUDGET_EXCEEDED_HTTP_STATUS == 413

    def test_karsilastirma_tavanda_calisir(self, client):
        n = limits.COMPARATIVE_MAX_CONFIGS
        r = client.post('/api/comparative-analysis',
                        json={'motor_configs': _configs(n)})
        assert r.status_code == 200, r.get_data()[:300]
        assert r.get_json()['analysis']['total_configs'] == n

    def test_karsilastirma_tavan_asiminda_413_ve_hesap_yok(self, client,
                                                          monkeypatch):
        cizim = _Kayit({})
        monkeypatch.setattr(app_module, 'create_comparative_analysis_plot',
                            cizim)
        n = limits.COMPARATIVE_MAX_CONFIGS + 1
        r = client.post('/api/comparative-analysis',
                        json={'motor_configs': _configs(n)})
        assert r.status_code == 413
        j = r.get_json()
        assert j['error'] == 'item_budget_exceeded'
        assert j['field'] == 'motor_configs'
        assert j['maximum'] == limits.COMPARATIVE_MAX_CONFIGS
        assert j['requested'] == n
        assert cizim.cagri == 0
        assert len(r.get_data()) < 1024     # yanıt büyütmesi yok

    def test_yakit_tavanda_calisir(self, client):
        n = limits.FUEL_COMPOSITION_MAX_ITEMS
        r = client.post('/api/validate-fuel',
                        json={'composition': _composition(n)})
        assert r.status_code != 413, r.get_data()[:300]

    def test_yakit_tavan_asiminda_413_ve_dogrulama_yok(self, client,
                                                       monkeypatch):
        dogrulama = _Kayit({'status': 'success'})
        monkeypatch.setattr(app_module.db_manager,
                            'validate_fuel_composition', dogrulama)
        n = limits.FUEL_COMPOSITION_MAX_ITEMS + 1
        r = client.post('/api/validate-fuel',
                        json={'composition': _composition(n)})
        assert r.status_code == 413
        j = r.get_json()
        assert j['error'] == 'item_budget_exceeded'
        assert j['field'] == 'composition'
        assert j['maximum'] == limits.FUEL_COMPOSITION_MAX_ITEMS
        assert j['requested'] == n
        assert dogrulama.cagri == 0

    def test_yakit_tavan_oge_dongusunden_once(self, client):
        """ÖNCE: 1M bozuk öğe 422 + öğe başına bir invalid_fields kaydı."""
        n = limits.FUEL_COMPOSITION_MAX_ITEMS * 10
        r = client.post('/api/validate-fuel',
                        json={'composition': ['bozuk'] * n})
        assert r.status_code == 413
        assert 'invalid_fields' not in r.get_json()
        assert len(r.get_data()) < 1024


# ===========================================================================
# SG-07 — gövde bayt tavanı her uçta JSON 413 (beyan ⟷ gerçek)
# ===========================================================================

#: Ölçüm ölçeği: tavan bu süreçte 1,1 MB'a indirilir, 1,2 MB'lık geçerli
#: JSON gönderilir (gövde kapısı 1 MiB üstünü okumaz; istek uca ulaşırdı).
SG07_OLCUM_TAVANI = 1_100_000
SG07_ASIRI_DOLGU = 'x' * 1_200_000

#: Uç kataloğu (canlı test_client ile güvenli çağrıldığı ölçülmüş POST
#: uçları ve taban yükleri; yan etkili uçlar bu listede yok).
SG07_KATALOG = json.loads((ROOT / 'tests/support/uc_yukleri.json').read_text(
    encoding='utf-8'))

#: Kapının ÖNCE ölçülen her ret sınıfından temsilci uçlar
#: (``sg2a/sonuc/govde_tavani_once.json``) + SG-03'ün iki ucu. Liste
#: LİTERAL: rota çağrıları statik çözülür. 62 ucun tamamı ölçüm betiğinde
#: (``sg2a/olcum_govde_tavani.py``) koşar.
SG07_TEMSILCI_UCLAR = (
    '/analyze_safety',              # önce 500 JSON
    '/api/comparative-analysis',    # önce 500 JSON (SG-03 ucu)
    '/api/validate-fuel',           # önce 422 not_an_object (SG-03 ucu)
    '/api/quick-geometry',          # önce 400
    '/api/slosh-analysis',          # önce 500 HTML (işlenmemiş hata)
    '/export_tank_cad',             # önce 500 HTML (UnboundLocalError)
    '/api/import/ork',              # önce HTML 413
)


class TestSG07GovdeTavani:
    """ÖNCE (``sg2a/sonuc/govde_tavani_once.json``): 62 uçtan 54'ü tavan
    aşımını 500/400/422'ye çeviriyordu; ikisi HTML 500 (işlenmemiş hata)."""

    def test_yardimci_sinirlar(self):
        assert limits.body_budget_error(None, 10) is None      # chunked
        assert limits.body_budget_error(10, 10) is None        # eşit geçer
        assert limits.body_budget_error(11, None) is None      # tavan yok
        govde, kod = limits.body_budget_error(11, 10)
        assert kod == 413
        assert govde['error'] == 'request_body_too_large'
        assert (govde['maximum'], govde['requested']) == (10, 11)

    def test_tavan_tek_kaynak_app_config(self):
        """Yardımcı ikinci bir sayı taşımaz; tavan app.config'ten okunur."""
        kaynak = (ROOT / 'hrma/security/limits.py').read_text(
            encoding='utf-8')
        assert '32 * 1024 * 1024' not in kaynak
        assert app.config['MAX_CONTENT_LENGTH'] == 32 * 1024 * 1024

    def test_temsilciler_katalogda(self):
        assert set(SG07_TEMSILCI_UCLAR) <= set(SG07_KATALOG)

    @pytest.mark.parametrize('yol', SG07_TEMSILCI_UCLAR)
    def test_her_ucta_json_413(self, client, monkeypatch, yol):
        monkeypatch.setitem(app.config, 'MAX_CONTENT_LENGTH',
                            SG07_OLCUM_TAVANI)
        yuk = SG07_KATALOG[yol]
        govde = dict(yuk) if isinstance(yuk, dict) else {'_yuk': yuk}
        govde['_sg07_dolgu'] = SG07_ASIRI_DOLGU
        r = client.post(yol, data=json.dumps(govde),
                        content_type='application/json')
        assert r.status_code == 413, (yol, r.status_code,
                                      r.get_data()[:160])
        assert r.is_json, yol
        assert r.get_json()['error'] == 'request_body_too_large'

    def test_tavan_altinda_davranis_degismez(self, client, monkeypatch):
        monkeypatch.setitem(app.config, 'MAX_CONTENT_LENGTH',
                            SG07_OLCUM_TAVANI)
        r = client.post('/api/altitude-to-pressure',
                        data=json.dumps({'altitude': 1000,
                                         '_dolgu': 'x' * 900_000}),
                        content_type='application/json')
        assert r.status_code == 200


# ===========================================================================
# SG-01 — XXE defusedxml olmadan da kapalı; beyan gerçeği söyler
# ===========================================================================

KANARY_IMZA = 'HRMA_SG2_KANARY_SIZAMAZ_7f3e'


def _xxe_ork(kanary_yolu, kodlama='utf-8'):
    xml = (f'<?xml version="1.0" encoding="{kodlama}"?>\n'
           f'<!DOCTYPE openrocket [ <!ENTITY xx SYSTEM "file://{kanary_yolu}"> ]>\n'
           f'<openrocket><rocket><name>&xx;</name></rocket></openrocket>')
    return xml.encode(kodlama)


class TestSG01XxeDefusedxmlsiz:

    @pytest.fixture
    def defusedxml_yok(self, monkeypatch):
        from hrma.importers import ork_import
        monkeypatch.setattr(ork_import, '_defused_fromstring', None)
        return ork_import

    @pytest.mark.parametrize('kodlama', ['utf-8', 'utf-16', 'utf-16-be'])
    @pytest.mark.parametrize('kap', ['duz', 'zip', 'gzip'])
    def test_xxe_reddedilir(self, defusedxml_yok, tmp_path, kodlama, kap):
        kanary = tmp_path / 'kanary.txt'
        kanary.write_text(KANARY_IMZA, encoding='utf-8')
        veri = _xxe_ork(kanary, kodlama)
        if kap == 'zip':
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, 'w') as z:
                z.writestr('rocket.ork', veri)
            veri = buf.getvalue()
        elif kap == 'gzip':
            veri = gzip.compress(veri)
        sonuc = defusedxml_yok.parse_ork(veri)
        assert sonuc.get('error_code') == 'xml_security', sonuc
        assert KANARY_IMZA not in json.dumps(sonuc, ensure_ascii=False)

    def test_uc_uzerinden_xxe_reddedilir(self, client, defusedxml_yok,
                                         tmp_path):
        kanary = tmp_path / 'kanary.txt'
        kanary.write_text(KANARY_IMZA, encoding='utf-8')
        b64 = base64.b64encode(_xxe_ork(kanary)).decode()
        r = client.post('/api/import/ork',
                        json={'content_base64': b64, 'filename': 'x.ork'})
        assert r.status_code == 400
        assert KANARY_IMZA not in r.get_data(as_text=True)

    def test_beyan_gercegi_soyler(self):
        """defusedxml ek katman olarak beyan edilir, asıl kapı olarak değil."""
        kaynak = (ROOT / 'hrma/importers/ork_import.py').read_text(
            encoding='utf-8')
        assert "bekçi regex'ine bağımlılık kalmaz" not in kaynak
        assert ('ve ayrıştırma da DTD/varlık çözmeyen bir ayrıştırıcıyla '
                'yapılır.') not in kaynak
        assert 'defusedxml İSTEĞE BAĞLI ek katmandır' in kaynak
        assert 'defusedxml KURULUYSA onunla (ek katman' in kaynak


# ===========================================================================
# V3 SG-2 BÖLÜM B — DOM-XSS derinlemesine savunma (SG-05), CSP (SG-04),
# karşılaştırma panelinde kalem tavanı metni (SG-03 devri)
# ===========================================================================
#
# Rapor: ``docs/scofield/raw/OH/V3/guvenlik/SG2_rapor.md`` Bölüm B; sink
# envanteri ``.../sg2b/sonuc/sink_envanteri.json``; ters mutasyon
# ``.../sg2b/mutasyon.md``.
#
# İşaret dizgesi zararsızdır (betik çalıştırmaz); ölçülen şey, sunucu ya da
# istisna metninin HTML'e HAM mı yoksa METİN (kaçışlı) olarak mı girdiğidir.

import shutil  # noqa: E402
import subprocess  # noqa: E402

NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(NODE is None, reason='node kurulu değil')

SG05_ISARET = '<b data-sg05>x</b>'
SG05_ISARET_KACISLI = '&lt;b data-sg05&gt;x&lt;/b&gt;'
LIQ_HTML = ROOT / 'hrma/templates/liquid.html'
SOLID_HTML = ROOT / 'hrma/templates/solid.html'
JS_DIR = ROOT / 'hrma/static/js'

#: HTML sink'i: atama (innerHTML / outerHTML), insertAdjacentHTML,
#: document.write. Sıvı ve katı sayfalarda ``showMessage`` iletiyi
#: innerHTML'e koyduğu için onun sarmalayıcıları da sink sayılır
#: (gelişmiş sayfanın showMessage'ı ve app.js showNotice textContent
#: kullanır; onlar sink DEĞİL).
_SG05_ATAMA = re.compile(r"\.(?:innerHTML|outerHTML)\s*\+?=(?!=)"
                         r"|insertAdjacentHTML\s*\(|document\.write(?:ln)?\s*\(")
_SG05_CAGRI = re.compile(r"(?<![\w.])(?:showError|showSuccess|showWarning|"
                         r"showInfo|showMessage)\s*\(")
#: Kaçış yapan bilinen yardımcılar (çağrı adının son parçası).
_SG05_KACIS = frozenset({
    'escapeNoticeText', 'esc', 'escapeHtml', 'escHtml', 'escAttr',
    'gimbalEsc', 'escWarn', 'attrSafe', 'tpKacis', 'grainPreviewEscape',
    'escNote', 'escapeHTML', 'htmlEscape',
    # step_import_ui.js: gövdesi ``escapeHtml(message)``; bekçi bunu
    # ``TestSG05HataMetniSinkEnvanteri.test_errorhtml_kacislar`` ile doğrular.
    'errorHtml'})
#: Güvenilmeyen hata metni kaynakları (istisna iletisi ve sunucu hata alanı).
_SG05_HATA_KAYNAGI = re.compile(
    r"\b(?:error|err|e|ex)\.message\b|\berrorData\.error\b"
    r"|\b(?:data|result|results|d)\.error\b")


def _sg05_ifade(src, i, cagri):
    """``i``'den başlayan sink sağ tarafını (ya da çağrı argümanlarını) ve
    her karakterin kod mu (True) dize mi olduğunu gösteren maskeyi döndürür.
    Şablon literali ``${…}`` içi koddur."""
    n = len(src)
    j = i
    depth = 1 if cagri else 0
    maske = []

    def ileri_dize(k, q):
        k += 1
        while k < n and src[k] != q:
            if src[k] == '\\':
                k += 1
            k += 1
        return k + 1

    def ileri_sablon(k):
        k += 1
        while k < n and src[k] != '`':
            if src[k] == '\\':
                k += 2
                continue
            if src.startswith('${', k):
                k = ileri_kod_blok(k + 2)
                continue
            k += 1
        return k + 1

    def ileri_kod_blok(k):
        d = 1
        while k < n and d:
            ch = src[k]
            if ch in '\'"':
                k = ileri_dize(k, ch)
                continue
            if ch == '`':
                k = ileri_sablon(k)
                continue
            if ch == '{':
                d += 1
            elif ch == '}':
                d -= 1
            k += 1
        return k

    # Maskeyi yazmak için ikinci, işaretleyen bir geçiş: kod/dize ayrımı.
    def isaretle(a, b, kod):
        maske.extend([kod] * (b - a))

    while j < n:
        c = src[j]
        if c in '\'"':
            e = ileri_dize(j, c)
            isaretle(j, e, False)
            j = e
            continue
        if c == '`':
            k = j + 1
            isaretle(j, k, False)
            while k < n and src[k] != '`':
                if src[k] == '\\':
                    isaretle(k, k + 2, False)
                    k += 2
                    continue
                if src.startswith('${', k):
                    e = ileri_kod_blok(k + 2)
                    isaretle(k, k + 2, False)
                    isaretle(k + 2, e - 1, True)
                    isaretle(e - 1, e, False)
                    k = e
                    continue
                isaretle(k, k + 1, False)
                k += 1
            isaretle(k, k + 1, False)
            j = k + 1
            continue
        if src.startswith('//', j):
            e = src.find('\n', j)
            e = n if e < 0 else e
            isaretle(j, e, False)
            j = e
            continue
        if src.startswith('/*', j):
            e = src.find('*/', j + 2)
            e = n if e < 0 else e + 2
            isaretle(j, e, False)
            j = e
            continue
        if c in '([{':
            depth += 1
        elif c in ')]}':
            depth -= 1
            if depth < 0 or (cagri and depth == 0):
                return src[i:j], maske
        elif c == ';' and depth == 0:
            return src[i:j], maske
        isaretle(j, j + 1, True)
        j += 1
    return src[i:j], maske


def _sg05_sinkler(yol, cagri_sinkleri):
    """Dosyadaki her HTML sink ifadesi: (satır, tür, ifade, maske)."""
    src = yol.read_text(encoding='utf-8')
    desenler = [(_SG05_ATAMA, 'atama')]
    if cagri_sinkleri:
        desenler.append((_SG05_CAGRI, 'cagri'))
    out = []
    for desen, tur in desenler:
        for m in desen.finditer(src):
            satir_basi = src.rfind('\n', 0, m.start()) + 1
            if src[satir_basi:m.start()].lstrip().startswith(('//', '*')):
                continue
            if tur == 'cagri' and src[satir_basi:m.start()].rstrip() \
                    .endswith('function'):
                continue
            cagri = m.group(0).endswith('(')
            ifade, maske = _sg05_ifade(src, m.end(), cagri)
            out.append((src.count('\n', 0, m.start()) + 1, tur, ifade, maske))
    return out


def _sg05_cagri_adi(ifade, maske, k):
    """``ifade[k] == '('`` çağrısının çağrılan adı. ``(globalThis.ad ||
    String)(…)`` biçiminde (sökülmüş-işlev koşumlarıyla uyum) parantez
    içindeki ``globalThis.<ad>`` döner."""
    on = ifade[:k].rstrip()
    if on.endswith(')'):
        d, j = 0, len(on) - 1
        while j >= 0:
            if maske[j]:
                if on[j] == ')':
                    d += 1
                elif on[j] == '(':
                    d -= 1
                    if d == 0:
                        break
            j -= 1
        m = re.fullmatch(r'\(\s*globalThis\.([\w$]+)\s*\|\|\s*String\s*\)',
                         on[j:])
        return m.group(1) if m else None
    m = re.search(r'([\w$]+)\s*$', on)
    return m.group(1) if m else None


def _sg05_kacisli_mi(ifade, maske, konum):
    """``konum``daki kaynak, kapsayan bir kaçış çağrısının içinde mi?"""
    d = 0
    k = konum - 1
    while k >= 0:
        if maske[k]:
            ch = ifade[k]
            if ch in ')]}':
                d += 1
            elif ch in '([{':
                if d == 0:
                    if ch == '(' and _sg05_cagri_adi(ifade, maske, k) \
                            in _SG05_KACIS:
                        return True
                else:
                    d -= 1
        k -= 1
    return False


def _sg05_dosyalar():
    js = sorted(p for p in JS_DIR.rglob('*.js')
                if not p.name.startswith('i18n'))
    sablon = sorted((ROOT / 'hrma/templates').glob('*.html'))
    return [(p, p in (LIQ_HTML, SOLID_HTML)) for p in sablon + js]


def _sg05_kacissiz_hata_metni():
    """HTML sink'ine kaçışsız giren hata metni kaynakları (dosya:satır)."""
    bulgu, toplam = [], 0
    for yol, cagri in _sg05_dosyalar():
        for satir, tur, ifade, maske in _sg05_sinkler(yol, cagri):
            for m in _SG05_HATA_KAYNAGI.finditer(ifade):
                if not maske[m.start()]:
                    continue
                toplam += 1
                if not _sg05_kacisli_mi(ifade, maske, m.start()):
                    bulgu.append(f'{yol.relative_to(ROOT)}:{satir} '
                                 f'{m.group(0)}')
    return bulgu, toplam


class TestSG05HataMetniSinkEnvanteri:
    """Sistematik tarama: istisna iletisi ve sunucu hata alanı hiçbir HTML
    sink'ine kaçışsız girmez (şablonlar + bütün JS, i18n sözlükleri hariç).
    Önce (dal 5d6a23e9): 23 kaynaktan 16'sı kaçışsızdı (sıvı 9, katı 7);
    sonra 0 (ölçüm: ``sg2b/sonuc/hata_metni_envanteri_{once,sonra}.json``)."""

    def test_kacissiz_hata_metni_yok(self):
        bulgu, toplam = _sg05_kacissiz_hata_metni()
        assert toplam >= 20, f'tarayıcı kaynak bulamadı ({toplam})'
        assert bulgu == [], 'kaçışsız hata metni:\n' + '\n'.join(bulgu)

    def test_errorhtml_kacislar(self):
        kaynak = (JS_DIR / 'step_import_ui.js').read_text(encoding='utf-8')
        govde = _sg05_fn(kaynak, 'errorHtml')
        assert "+ escapeHtml(message) +" in govde

    def test_tarayici_kacissizi_gorur(self):
        """Tarayıcının kendisi ısırır: kaçışsız örnek yakalanır."""
        ornek = "x.innerHTML = '<p>' + T('k', 'Hata: ') + error.message + '</p>';"
        m = _SG05_ATAMA.search(ornek)
        ifade, maske = _sg05_ifade(ornek, m.end(), False)
        k = ifade.index('error.message')
        assert maske[k] and not _sg05_kacisli_mi(ifade, maske, k)
        ornek2 = ("x.innerHTML = `<p>${escapeNoticeText(TF('k', "
                  "{ m: error.message }, '{m}'))}</p>`;")
        m = _SG05_ATAMA.search(ornek2)
        ifade, maske = _sg05_ifade(ornek2, m.end(), False)
        k = ifade.index('error.message')
        assert maske[k] and _sg05_kacisli_mi(ifade, maske, k)
        ornek3 = ("showError(T('k', 'Hata: ') + "
                  "(globalThis.escapeNoticeText || String)(error.message));")
        m = _SG05_CAGRI.search(ornek3)
        ifade, maske = _sg05_ifade(ornek3, m.end(), True)
        k = ifade.index('error.message')
        assert maske[k] and _sg05_kacisli_mi(ifade, maske, k)
        ornek4 = "showError((globalThis.bilinmeyen || String)(error.message));"
        m = _SG05_CAGRI.search(ornek4)
        ifade, maske = _sg05_ifade(ornek4, m.end(), True)
        k = ifade.index('error.message')
        assert not _sg05_kacisli_mi(ifade, maske, k)


# --- node ile DOM düzeyinde koşum ------------------------------------------
#
# Sink ifadesinin sağ tarafı (ya da showError argümanı) gerçek kaynaktan
# sökülür ve node'da ``with`` kapsamında değerlendirilir. Güvenilmeyen kaynak
# adları İŞARET vekiline bağlanır: vekilin her alanı yine vekildir ve dizgeye
# çevrildiğinde ``<b data-sg05>x</b>`` olur. Bilinmeyen adlar zararsız boş
# vekile düşer. ``escapeNoticeText`` şablonun KENDİ fonksiyonudur.

_SG05_KOSUCU = r"""
const ISARET = girdi.isaret;
function vekil(metin) {
  const f = function () { return vekil(metin); };
  return new Proxy(f, {
    get(t, ad) {
      if (ad === Symbol.toPrimitive) return () => metin;
      if (ad === 'toString' || ad === 'valueOf') return () => metin;
      if (ad === 'length') return 0;
      if (typeof ad === 'symbol') return undefined;
      return vekil(metin);
    },
    apply() { return vekil(metin); },
  });
}
const BOS = vekil('');
const kayit = [];
const yardimci = (new Function(
  Object.values(girdi.fonksiyonlar).join('\n') + '\nreturn {'
  + Object.keys(girdi.fonksiyonlar).join(', ') + '};'))();
function TF(k, p, fb) {
  return String(fb).replace(/\{(\w+)\}/g, (w, n) =>
    (p && Object.prototype.hasOwnProperty.call(p, n)) ? String(p[n]) : w);
}
function T(k, fb) { return fb === undefined ? k : fb; }
const GERCEK = new Set(['String', 'Number', 'Object', 'Array', 'JSON',
  'Math', 'isFinite', 'parseFloat', 'parseInt', 'Date', 'RegExp', 'Symbol',
  'undefined', 'NaN', 'Infinity', 'Boolean', 'encodeURIComponent']);
const sonuclar = [];
for (const kalem of girdi.kalemler) {
  const bag = Object.assign({ T, TF }, yardimci);
  // Şablon çağrısı `(globalThis.escapeNoticeText || String)(…)`: koşucunun
  // globalThis'i şablonun GERÇEK yardımcılarını taşır.
  bag.globalThis = Object.assign({}, yardimci);
  for (const ad of kalem.isaretli) bag[ad] = vekil(ISARET);
  for (const [ad, js] of Object.entries(kalem.bag || {})) {
    bag[ad] = (new Function('ISARET', 'vekil', 'return (' + js + ');'))(ISARET, vekil);
  }
  const kapsam = new Proxy(bag, {
    has(t, ad) { return !GERCEK.has(ad); },
    get(t, ad) {
      if (ad === Symbol.unscopables) return undefined;
      return Object.prototype.hasOwnProperty.call(t, ad) ? t[ad] : BOS;
    },
  });
  let html;
  try {
    const fn = new Function('kapsam', 'with (kapsam) { return (' + kalem.ifade + '); }');
    html = fn(kapsam);
    if (kalem.cagir) html = html.apply(null, kalem.cagir.map(
      a => a === '@ISARET' ? vekil(ISARET) : a));
    html = String(html);
  } catch (e) { html = 'HATA: ' + e.message; }
  sonuclar.push({ kimlik: kalem.kimlik, html });
}
process.stdout.write(JSON.stringify(sonuclar));
"""


def _sg05_fn(kaynak, ad):
    """``function ad(`` bildirimini parantez dengesiyle söker."""
    i = kaynak.index(f'function {ad}(')
    j = kaynak.index('{', i)
    d = 0
    for k in range(j, len(kaynak)):
        if kaynak[k] == '{':
            d += 1
        elif kaynak[k] == '}':
            d -= 1
            if d == 0:
                return kaynak[i:k + 1]
    raise AssertionError(ad)


def _sg05_sink_ifadesi(yol, igne, beklenen=1, cagri=True):
    """İğneyi (düz dize, dize demeti — hepsi — ya da re.Pattern) taşıyan
    sink ifadeleri."""
    eslesen = []
    for satir, tur, ifade, _m in _sg05_sinkler(yol, cagri):
        if hasattr(igne, 'search'):
            ok = bool(igne.search(ifade))
        elif isinstance(igne, tuple):
            ok = all(parca in ifade for parca in igne)
        else:
            ok = igne in ifade
        if ok:
            eslesen.append((satir, ifade))
    assert len(eslesen) == beklenen, (yol.name, igne, eslesen)
    return eslesen


def _sg05_kos(kalemler, fonksiyonlar):
    # Betik stdin ile verilir (argv DEĞİL: test_node_cagri_sozlesmesi);
    # girdi betiğin başına JSON dize literali olarak gömülür.
    girdi = json.dumps({'isaret': SG05_ISARET, 'kalemler': kalemler,
                        'fonksiyonlar': fonksiyonlar})
    betik = ('const girdi = JSON.parse(' + json.dumps(girdi) + ');\n'
             + _SG05_KOSUCU)
    out = subprocess.run([NODE, '-'], input=betik, capture_output=True,
                         text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-2000:]
    return {r['kimlik']: r['html'] for r in json.loads(out.stdout)}


#: Tek değişkenli ``showError(…)`` argümanının olası kaçış sarmalı (iğne
#: düzeltmeden bağımsız: sarmal olsa da olmasa da aynı ifade bulunur).
_SG05_SARMAL = (r"^(?:\(globalThis\.escapeNoticeText \|\| String\)\("
                r"|escapeNoticeText\()?")

#: (kimlik, dosya, iğne, işaretlenecek adlar) — sink ifadesi tekildir.
_SG05_SITELER = [
    ('L1a', LIQ_HTML, ("'liq.js.fuel_properties_not_loaded'", 'error.message'),
     ['error']),
    ('L1b', LIQ_HTML, ("'liq.js.ox_properties_not_loaded'", 'error.message'),
     ['error']),
    # v3.0.1 (26 Eki, L-A SV-15): hesap hatası bildirimi artık ret durumuna
    # göre önek kurar (onEk = 'Girdi sunucu tarafından reddedildi (HTTP …)'
    # ya da 'Hata'); sunucu metni yine escapeNoticeText'ten geçer.
    ('L2', LIQ_HTML, re.compile(r"^onEk \+ ': ' \+"), ['error']),
    ('L3', LIQ_HTML, "'liq.msg.error_generating_cad_files'", ['error']),
    ('L4', LIQ_HTML, "'liq.msg.cad_export_failed_prefix', 'CAD export failed: ') +",
     ['error']),
    ('L5', LIQ_HTML, re.compile(_SG05_SARMAL + r"msg\)?$"), ['msg']),
    ('L6', LIQ_HTML, "'liq.js.oxidizer_tank_card'", ['tankData']),
    ('L7', LIQ_HTML, "'liq.js.fuel_tank_card'", ['tankData']),
    ('L8', LIQ_HTML, "'liq.js.trajectory_could_not_be_computed'", ['e']),
    ('L10', LIQ_HTML, "'liq.msg.export_failed'", ['error']),
    ('L11', LIQ_HTML, re.compile(_SG05_SARMAL + r"metin\)?$"), ['metin']),
    ('L12', LIQ_HTML, "'liq.js.detailed_cad_generation_failed'",
     ['errorData']),
    ('L13', LIQ_HTML, re.compile(r'hd-red, #ff5d73\);">Error: \$\{'),
     ['error']),
    ('S1', SOLID_HTML, "'solid.msg.export_failed'", ['error']),
    ('S2', SOLID_HTML, "'solid.msg.trajectory_could_not_be_computed'", ['e']),
    ('S4', SOLID_HTML, "'solid.js.error_prefix'", ['error']),
    ('S5', SOLID_HTML, "'solid.msg.monte_carlo_error'", ['error']),
    ('S6', SOLID_HTML, "'solid.msg.cad_export_error'", ['error']),
    ('S7', SOLID_HTML, "'solid.msg.technical_drawing_error'", ['error']),
    ('S8', SOLID_HTML, "'solid.js.eng_export_error'", ['error']),
]


@node_gerekli
class TestSG05DomIsaret:
    """Düzeltilen her sink, işaret dizgesini HTML olarak DEĞİL metin olarak
    basar; meşru (özel karaktersiz) metin bit-aynı kalır."""

    @staticmethod
    def _fonksiyonlar():
        liq = LIQ_HTML.read_text(encoding='utf-8')
        # Tank kartlarının kendi kaçışlı yardımcıları da GERÇEK koddan
        # gelir (vekile düşmez); kart ifadesi bütünüyle koşar.
        return {ad: _sg05_fn(liq, ad) for ad in (
            'escapeNoticeText', '_tankEsc', 'tankKunye', 'tankKriyoSatiri',
            'tankMalzemeHucresi')}

    def test_sablon_sinkleri_isareti_metin_basar(self):
        kalemler = []
        for kimlik, yol, igne, isaretli in _SG05_SITELER:
            (_satir, ifade), = _sg05_sink_ifadesi(yol, igne)
            kalemler.append({'kimlik': kimlik, 'ifade': ifade,
                             'isaretli': isaretli, 'bag': {'label': "'CAD'",
                                                           'onEk': "'Error'"}})
        # Katı sayfanın escapeNoticeText'i sıvıdakiyle bayt-aynı mı?
        assert _sg05_fn(SOLID_HTML.read_text(encoding='utf-8'),
                        'escapeNoticeText') == self._fonksiyonlar()[
                            'escapeNoticeText']
        sonuc = _sg05_kos(kalemler, self._fonksiyonlar())
        sizan = {k: h for k, h in sonuc.items()
                 if SG05_ISARET in h or h.startswith('HATA')}
        assert sizan == {}, sizan
        akmayan = {k: h for k, h in sonuc.items()
                   if SG05_ISARET_KACISLI not in h}
        assert akmayan == {}, akmayan

    def test_mesru_metin_bit_ayni(self):
        """Özel karaktersiz ileti kaçıştan değişmeden geçer."""
        duz = 'Sunucu iletisi 42 (bar)'
        kalemler = []
        for kimlik, yol, igne, isaretli in _SG05_SITELER:
            (_satir, ifade), = _sg05_sink_ifadesi(yol, igne)
            kalemler.append({'kimlik': kimlik, 'ifade': ifade,
                             'isaretli': [], 'bag': {
                                 'onEk': "'Error'",
                                 **{ad: f'vekil({json.dumps(duz)})'
                                    for ad in isaretli}}})
        sonuc = _sg05_kos(kalemler, self._fonksiyonlar())
        assert all(duz in h for h in sonuc.values()), sonuc

    def test_uyari_panelleri_isareti_metin_basar(self):
        """Sunucu uyarı metni: sıvı sayfa ``item``, katı sayfa uyarı listesi,
        gelişmiş sayfa (app.js) ``displayWarnings``."""
        liq = LIQ_HTML.read_text(encoding='utf-8')
        i = liq.index('const item = (label, text, cls) =>')
        item_ifade = _sg05_ifade(liq, i + len('const item = '), False)[0]
        (_s, solid_ifade), = _sg05_sink_ifadesi(
            SOLID_HTML, "'solid.msg.warning_count'")
        app = (JS_DIR / 'app.js').read_text(encoding='utf-8')
        goruntule = _sg05_fn(app, 'displayWarnings')
        sahte_dom = (
            "(function(){ const el = {}; const k = {style: {}}; "
            "const d = {getElementById: (id) => id === 'warningsList' ? el "
            ": k}; return {d, el}; })()")
        kalemler = [
            {'kimlik': 'L9', 'ifade': item_ifade, 'isaretli': [],
             'bag': {'warnToText': '(w) => String(w)'},
             'cagir': ['ETIKET', '@ISARET', 'warning-regular']},
            {'kimlik': 'S3', 'ifade': solid_ifade, 'isaretli': [],
             'bag': {'items': "[{message: ISARET, level: 'regular'}]",
                     'critical': '0'}},
            {'kimlik': 'A1', 'isaretli': [],
             'ifade': ('(function () { const D = ' + sahte_dom + '; '
                       'const document = D.d; '
                       'const setDesignValidationVerdict = () => {}; '
                       'const warnToText = (w) => String(w); '
                       'const warnIsCritical = () => false; '
                       + goruntule + ' displayWarnings([ISARET], '
                       '{overall_status: ISARET, critical_warnings: [ISARET], '
                       'regular_warnings: [ISARET]}); '
                       'return D.el.innerHTML; })()'),
             'bag': {'ISARET': 'ISARET'}},
        ]
        sonuc = _sg05_kos(kalemler, self._fonksiyonlar())
        for kimlik, html in sonuc.items():
            assert not html.startswith('HATA'), (kimlik, html)
            assert SG05_ISARET not in html, (kimlik, html)
            assert SG05_ISARET_KACISLI in html, (kimlik, html)
        # app.js: dört uyarı kaydı (durum satırı + 3 kayıt) hepsi kaçışlı.
        assert sonuc['A1'].count(SG05_ISARET_KACISLI) == 4, sonuc['A1']


class TestSG05PanelSunucuMetni:
    """Yapısal ve akış panellerinde sunucunun serbest metni (gerekçe,
    varsayılan değer, model adı) şablon dizgisine kaçışla girer.
    Dize düzeyi: alan, kapsayan bir ``U.esc(…)`` çağrısının içinde."""

    @pytest.mark.parametrize('dosya, desen, beklenen', [
        ('panels/structural_panel.js', r'wallSuggestion\.reason\}', 0),
        # V3.0.5 T-ÇAPA-C1 — BEKLENTİ DEĞİŞTİ (V301/DİL-2 571d6506e): gerekçe
        # görünen cümle (reasonVisible) ve ipucu (reasonTitle) olarak İKİ
        # yuvada basılır; ikisi de U.esc içinde.
        ('panels/structural_panel.js',
         r'\$\{U\.esc\(reason(?:Title|Visible)\(wallSuggestion\.reason\)\)\}', 2),
        ('panels/structural_panel.js', r'\$\{U\.esc\(rec\.reason \|\| \'\'\)\}', 2),
        ('panels/structural_panel.js', r'\$\{String\(rec\.(?:reason|value)', 0),
        ('panels/structural_panel.js', r'\$\{U\.esc\(rec\.value\)\}\$\{U\.esc\(birim\)\}', 1),
        ('panels/structural_panel.js', r'return \[U\.esc\(k\),', 2),
        ('panels/flow_panel.js', r'\$\{U\.esc\(flow\.model \|\| \'\'\)\}', 1),
        ('panels/flow_panel.js', r'\$\{flow\.model', 0),
    ])
    def test_kacis(self, dosya, desen, beklenen):
        kaynak = (JS_DIR / dosya).read_text(encoding='utf-8')
        assert len(re.findall(desen, kaynak)) == beklenen

    def test_u_esc_yayimlaniyor(self):
        dock = (JS_DIR / 'analysis_dock.js').read_text(encoding='utf-8')
        assert re.search(r'^\s+esc: escAttr,$', dock, re.M)


# ===========================================================================
# SG-04 — CSP: object-src 'none' + base-uri 'none' (tek kaynak)
# ===========================================================================

class TestSG04Csp:

    def test_sayfa_basligi(self, client):
        # Rota çağrıları literal (d24 bekçisi statik çözer).
        h = {'Host': SELF_HOST}
        yanitlar = {
            '/': client.get('/', headers=h),
            '/liquid': client.get('/liquid', headers=h),
            '/solid': client.get('/solid', headers=h),
            '/hybrid': client.get('/hybrid', headers=h),
            '/formulas': client.get('/formulas', headers=h),
            '/launch-site': client.get('/launch-site', headers=h),
        }
        for yol, r in yanitlar.items():
            assert r.status_code == 200, yol
            csp = r.headers.get('Content-Security-Policy', '')
            yonergeler = {p.strip() for p in csp.split(';')}
            assert {"frame-ancestors 'none'", "object-src 'none'",
                    "base-uri 'none'"} <= yonergeler, (yol, csp)

    def test_api_yaniti_da_tasir(self, client):
        r = client.post('/api/altitude-to-pressure', json={'altitude': 1000},
                        headers={'Host': SELF_HOST})
        assert "object-src 'none'" in r.headers.get(
            'Content-Security-Policy', '')

    def test_tek_kaynak(self):
        from hrma.security import csp
        assert csp.CONTENT_SECURITY_POLICY == (
            "frame-ancestors 'none'; object-src 'none'; base-uri 'none'")
        kaynak = (ROOT / 'hrma/app.py').read_text(encoding='utf-8')
        assert "frame-ancestors 'none'\"" not in kaynak
        assert ("response.headers.setdefault('Content-Security-Policy', "
                "_csp.CONTENT_SECURITY_POLICY)") in kaynak

    def test_arayuz_object_embed_base_kullanmiyor(self):
        """İki yönergenin arayüzü bozmamasının ön koşulu: ürün bu öğeleri
        hiç kullanmıyor (gerçek tarayıcı ölçümü: sg2b/sonuc/csp_*.json)."""
        desen = re.compile(r"<(?:object|embed|applet|base)\b|createElement\("
                           r"['\"](?:object|embed|base)['\"]", re.I)
        bulgu = []
        for yol in list((ROOT / 'hrma/templates').glob('*.html')) + \
                list(JS_DIR.rglob('*.js')):
            for m in desen.finditer(yol.read_text(encoding='utf-8')):
                bulgu.append(f'{yol.name}: {m.group(0)}')
        assert bulgu == []


# ===========================================================================
# SG-03 devri — karşılaştırma panelinde kalem tavanı aşımı insan okur metin
# ===========================================================================

_SG2B_SOZLUK = r"""
global.window = global;
Object.defineProperty(global, 'localStorage', { value: { getItem() { return null; }, setItem() {} }, configurable: true });
Object.defineProperty(global, 'navigator', { value: { language: 'en' }, configurable: true });
global.document = global.document || { documentElement: { lang: 'en', setAttribute() {}, getAttribute() { return null; } },
    querySelectorAll() { return []; }, addEventListener() {}, readyState: 'complete' };
require(%(i18n)s); require(%(common)s);
"""


@node_gerekli
class TestSG03KarsilastirmaMetni:

    def _kos(self, govdeler, lang):
        panel = (JS_DIR / 'panels/comparative_panel.js').read_text(
            encoding='utf-8')
        sabit = re.search(r"const ITEM_BUDGET_CODE = '[^']+';", panel).group(0)
        fn = _sg05_fn(panel, 'budgetMessage')
        betik = (_SG2B_SOZLUK % {
            'i18n': json.dumps(str(JS_DIR / 'i18n.js')),
            'common': json.dumps(str(JS_DIR / 'i18n_common.js'))}
            + f"window.I18N.setLang({json.dumps(lang)});\n"
            + "const U = { tf: (k, p, f) => window.I18N.tf(k, p, f) };\n"
            + sabit + '\n' + fn + '\n'
            + f"process.stdout.write(JSON.stringify({json.dumps(govdeler)}"
            + ".map(budgetMessage)));")
        out = subprocess.run([NODE, '-'], input=betik, capture_output=True,
                             text=True, timeout=60)
        assert out.returncode == 0, out.stderr[-2000:]
        return json.loads(out.stdout)

    def test_gercek_413_govdesi_insan_okur(self, client):
        n = limits.COMPARATIVE_MAX_CONFIGS + 1
        r = client.post('/api/comparative-analysis',
                        json={'motor_configs': _configs(n)},
                        headers={'Host': SELF_HOST})
        assert r.status_code == limits.BUDGET_EXCEEDED_HTTP_STATUS
        govde = r.get_json()
        en, = self._kos([govde], 'en')
        tr, = self._kos([govde], 'tr')
        for metin in (en, tr):
            assert metin and 'item_budget_exceeded' not in metin
            assert str(n) in metin
            assert str(limits.COMPARATIVE_MAX_CONFIGS) in metin
        assert en.startswith('Too many designs to compare')
        assert tr.startswith('Karşılaştırılacak tasarım sayısı fazla')

    def test_baska_hata_ve_sayisiz_govde_eski_yol(self):
        sonuc = self._kos([
            {'status': 'error', 'error': 'At least two configurations'},
            {'status': 'error', 'error': 'item_budget_exceeded',
             'maximum': '256', 'requested': 300},
            None], 'en')
        assert sonuc == [None, None, None]

    def test_en_tr_anahtar_ve_yedek(self):
        sozluk = (JS_DIR / 'i18n_common.js').read_text(encoding='utf-8')
        degerler = re.findall(
            r"'panel\.comparative\.itemBudgetExceeded': '([^']+)'", sozluk)
        assert len(degerler) == 2
        yer = [set(re.findall(r'\{(\w+)\}', d)) for d in degerler]
        assert yer[0] == yer[1] == {'requested', 'maximum'}
        panel = (JS_DIR / 'panels/comparative_panel.js').read_text(
            encoding='utf-8')
        yedek = ''.join(re.findall(
            r"'([^']*)'", _sg05_fn(panel, 'budgetMessage').split(
                "'panel.comparative.itemBudgetExceeded',")[1].split(');')[0]))
        assert yedek == degerler[0]
        # Koşu yolu GERÇEKTEN kullanıyor: hata dalı önce budgetMessage'a sorar
        # (tanım satırındaki ``budgetMessage(data)`` bunu kanıtlamaz).
        assert re.search(r"throw new Error\(budgetMessage\(data\)\s*\|\| "
                         r"\(data && data\.error\)", panel)
        assert re.search(r"status\.textContent = U\.tf\('common\.errorPrefix'",
                         panel)


@node_gerekli
class TestSG05PaylasilanListe:
    """Güvertenin paylaşılan uyarı/varsayım listesi (``U.listBlock``):
    ~30 panel çağırır; doğrulama panelinde içe aktarılan motor dosyasının
    uyarıları da buradan basılır. Öğeler METİN olarak girer. Gerçek
    ``listBlock`` + ``escAttr`` koşar (``kindColor``/``warnText`` sabit)."""

    def test_isaret_metin_basar(self):
        dock = (JS_DIR / 'analysis_dock.js').read_text(encoding='utf-8')
        fonk = {
            'escAttr': _sg05_fn(dock, 'escAttr'),
            'listBlock': _sg05_fn(dock, 'listBlock'),
            'kindColor': "function kindColor(k) { return '#7d97a5'; }",
            'warnText': 'function warnText(w) { return String(w); }',
        }
        sonuc = _sg05_kos([{
            'kimlik': 'D1', 'isaretli': [], 'bag': {'ISARET': 'ISARET'},
            'ifade': "listBlock('Uyarılar', [ISARET, 'düz metin'], 'warn')"}],
            fonk)
        html = sonuc['D1']
        assert SG05_ISARET not in html, html
        assert SG05_ISARET_KACISLI in html, html
        assert '<li>düz metin</li>' in html

    def test_cagiranlar_onceden_kacislamiyor(self):
        """Çift kaçış olmasın: öğe listesine ``esc(``/``escapeHtml(`` ile
        hazırlanmış dizge veren U.listBlock çağıranı yok."""
        bulgu = []
        for yol in (JS_DIR / 'panels').glob('*.js'):
            kaynak = yol.read_text(encoding='utf-8')
            for m in re.finditer(r'U\.listBlock\(', kaynak):
                ifade, _m = _sg05_ifade(kaynak, m.end(), True)
                arg = ifade.split(',', 1)[-1]
                if re.search(r'\b(?:U\.esc|esc|escapeHtml)\(', arg):
                    bulgu.append(f'{yol.name}: {ifade[:80]}')
        assert bulgu == []


class TestSG05SunucuRetMetni:
    """Gelişmiş sayfa optimum O/F: sunucu ret metni (``HRMAReject.metni``)
    textContent'e gider; besleme paneli sunucu önerisi ve künye değeri
    kaçışlı."""

    def test_optimum_of_metin(self):
        adv = (ROOT / 'hrma/templates/advanced.html').read_text(
            encoding='utf-8')
        assert "getElementById('optimum_of_result').innerHTML" not in adv
        assert ("document.getElementById('optimum_of_result').textContent "
                "= msg;") in adv

    @pytest.mark.parametrize('desen, beklenen', [
        (r"\+ U\.esc\(w\.recommendation\) \+", 1),
        (r"\+ w\.recommendation \+", 0),
        (r": U\.esc\(String\(v\)\);", 1),
    ])
    def test_besleme_paneli(self, desen, beklenen):
        kaynak = (JS_DIR / 'panels/feed_panel.js').read_text(encoding='utf-8')
        assert len(re.findall(desen, kaynak)) == beklenen


# ===========================================================================
# Bölüm C — SG-02c port bilinmiyorken fail-closed, run_windows.py port
# kaydı, SG-07 artıkları (parçalı gövde, iki ucun hata dalı, STEP tavanı).
# Rapor: SG2_rapor.md "Bölüm C"; ters mutasyon: sgc/mutasyon.md.
# ===========================================================================

from hrma.security import body_limit, json_body  # noqa: E402

#: SG-02c ölçüm ızgarası: başlatıcının port aralığı ve üç geri döngü yazımı
#: (``hrma/run.py::PORT_RANGE`` ile aynı aralık; oradan okunur).
from hrma.run import PORT_RANGE as SGC_PORT_ARALIGI  # noqa: E402

SGC_ANA_MAKINELER = ('127.0.0.1', 'localhost', '[::1]')


def _sgc_post(client, host, origin):
    return client.post('/api/altitude-to-pressure', json={'altitude': 1000},
                       headers={'Host': host, 'Origin': origin})


class TestSG02cPortBilinmiyor:
    """ÖNCE (SG-0 + ``sg2a/oneri_selfport_yok_olcum.json``): HRMA_SELF_PORT
    ayarsızken (``flask run``, WSGI gömme) kapı yalnız geri döngü denetimi
    yapıyordu; 127.0.0.1'in başka portundaki sayfa durum değiştiren istek
    atabiliyordu. Artık sunucunun portu isteğin Host'undan alınır."""

    @pytest.fixture(autouse=True)
    def _port_yok(self, monkeypatch):
        monkeypatch.setitem(app.config, origin_gate.SELF_PORT_CONFIG_KEY,
                            None)

    def test_tarayici_izgarasi(self, client):
        """Aralığın her portu × üç ana makine: aynı port 200, yabancı 403."""
        sonuc = []
        portlar = list(SGC_PORT_ARALIGI)
        for ana in SGC_ANA_MAKINELER:
            for i, port in enumerate(portlar):
                yabanci = portlar[(i + 1) % len(portlar)]
                ayni = _sgc_post(client, f'{ana}:{port}',
                                 f'http://{ana}:{port}')
                kotu = _sgc_post(client, f'{ana}:{port}',
                                 f'http://{ana}:{yabanci}')
                sonuc.append((ana, port, ayni.status_code, kotu.status_code,
                              (kotu.get_json() or {}).get('reason')))
        assert len(sonuc) == 3 * len(portlar)
        hatali = [s for s in sonuc
                  if s[2:] != (200, 403, 'origin_port_mismatch')]
        assert hatali == []

    @pytest.mark.parametrize('origin, beklenen', [
        ('http://127.0.0.1', 200),          # Host portsuz = 80 = Origin 80
        ('http://127.0.0.1:80', 200),
        ('http://127.0.0.1:8080', 403),
        ('https://127.0.0.1', 403),         # 443 ≠ 80
    ])
    def test_portsuz_host_semanin_varsayilani(self, client, origin,
                                              beklenen):
        r = _sgc_post(client, '127.0.0.1', origin)
        assert r.status_code == beklenen, (origin, r.status_code)

    def test_originsiz_istek_gecer(self, client):
        r = client.post('/api/altitude-to-pressure', json={'altitude': 1000},
                        headers={'Host': '127.0.0.1:8085'})
        assert r.status_code == 200

    def test_bilinen_port_hosttan_once_gelir(self, client, monkeypatch):
        """Host yalnız yedektir: port biliniyorsa Host aynı olsa da eşleşmez."""
        monkeypatch.setitem(app.config, origin_gate.SELF_PORT_CONFIG_KEY,
                            8080)
        r = _sgc_post(client, '127.0.0.1:8081', 'http://127.0.0.1:8081')
        assert r.status_code == 403
        assert r.get_json()['reason'] == 'origin_port_mismatch'

    @pytest.mark.parametrize('host, sema, beklenen', [
        ('127.0.0.1:8081', 'http', 8081),
        ('[::1]:8085', 'http', 8085),
        ('localhost', 'http', 80),
        ('localhost', 'https', 443),
        ('127.0.0.1:abc', 'http', None),
        ('', 'http', None),
        (None, 'http', None),
        ('127.0.0.1', 'ftp', None),
    ])
    def test_self_port_from_host(self, host, sema, beklenen):
        assert origin_gate.self_port_from_host(host, sema) == beklenen

    def test_port_turetilemezse_ret(self):
        """Ne yapılandırma ne Host port veriyorsa Origin'li istek reddedilir."""
        loop = app_module._is_loopback
        basliklar = {'Origin': 'http://127.0.0.1:8080'}
        assert origin_gate.request_rejection(
            'POST', 'x', basliklar, None, loop, None, 'http') == \
            'self_port_unknown'
        assert origin_gate.request_rejection(
            'POST', 'x', {}, None, loop, None, 'http') is None


class TestSG02RunWindowsPortuBildirir:
    """``hrma/run_windows.py`` (``start.bat`` yolu) kapıya portu bildirir.

    ÖNCE (``sg2a/sonuc/run_windows_portu.json``): ``serve`` anında
    ``app.config['HRMA_SELF_PORT']`` None, ortam değişkeni yok.
    """

    PORT = 8086

    @pytest.mark.parametrize('waitress_var', [True, False])
    def test_serve_aninda_port_dolu(self, monkeypatch, waitress_var):
        import hrma.run_windows as rw
        monkeypatch.setattr(sys, 'path', list(sys.path))   # run_server ekler
        monkeypatch.setenv('HRMA_PORT', str(self.PORT))
        _self_port_ortami_yok(monkeypatch)
        monkeypatch.setitem(app.config, origin_gate.SELF_PORT_CONFIG_KEY,
                            None)
        monkeypatch.setattr(rw, 'check_dependencies', lambda: [])
        monkeypatch.setattr(
            rw, 'Timer',
            lambda *a, **k: type('T', (), {'start': lambda s: None})())
        gorulen = []

        def kayit(*args, **kwargs):
            gorulen.append({
                'config': app.config.get(origin_gate.SELF_PORT_CONFIG_KEY),
                'env': os.environ.get(origin_gate.SELF_PORT_ENV),
                'port': kwargs.get('port')})

        monkeypatch.setattr(app, 'run', kayit)
        if waitress_var:
            sahte = type(sys)('waitress')
            sahte.serve = kayit
            monkeypatch.setitem(sys.modules, 'waitress', sahte)
        else:
            monkeypatch.setitem(sys.modules, 'waitress', None)
        rw.run_server()
        assert gorulen == [{'config': self.PORT, 'env': str(self.PORT),
                            'port': self.PORT}]


#: SG-07 (b) ölçek: JSON gövde kapısının okuma bütçesini az aşan gövde
#: (kapı bunun altını uca ulaşmadan keser).
SGC_KAPI_USTU = app_module._JSON_BODY_GATE_MAX_BYTES + 1000
SGC_BICIM_HATALI_GOVDELER = {
    'dizi': b'[' + b'0,' * (SGC_KAPI_USTU // 2) + b'0]',
    'bozuk': b'{"a":' + b' ' * SGC_KAPI_USTU,
    'skaler': b'1' + b' ' * SGC_KAPI_USTU,
}


class TestSG07bHataDallari:
    """ÖNCE (``sgc/sonuc/sg07b_once.json``): ``/export_tank_cad`` üç vakada
    HTML 500 (``UnboundLocalError: TankCADDataError``), ``/api/slosh-analysis``
    bozuk JSON'da HTML 500, dizi/skalerde ham Python metniyle JSON 500."""

    @pytest.fixture
    def sunucu_ayari(self, monkeypatch):
        """Gerçek sunucu gibi: işlenmemiş hata HTML 500 olarak döner."""
        monkeypatch.setitem(app.config, 'TESTING', False)
        monkeypatch.setitem(app.config, 'PROPAGATE_EXCEPTIONS', False)

    @pytest.mark.parametrize('vaka', sorted(SGC_BICIM_HATALI_GOVDELER))
    @pytest.mark.parametrize('yol', ['/export_tank_cad',
                                     '/api/slosh-analysis'])
    def test_json_400_html_yok(self, client, sunucu_ayari, yol, vaka):
        govde = SGC_BICIM_HATALI_GOVDELER[vaka]
        assert len(govde) > app_module._JSON_BODY_GATE_MAX_BYTES
        r = client.post(yol, data=govde, headers={
            'Host': SELF_HOST, 'Content-Type': 'application/json'})
        ham = r.get_data()
        assert r.status_code == 400, (yol, vaka, r.status_code, ham[:120])
        assert r.is_json
        assert r.get_json()['error'] in ('malformed_json_body',
                                         'body_not_an_object')
        assert b'Traceback' not in ham and b'has no attribute' not in ham

    def test_yardimci(self):
        assert json_body.json_object_error({'a': 1}) is None
        assert json_body.json_object_error({}) is None
        g, kod = json_body.json_object_error(None)
        assert (g['error'], kod) == ('malformed_json_body', 400)
        g, kod = json_body.json_object_error([1])
        assert (g['error'], kod) == ('body_not_an_object', 400)
        assert 'list' in g['message']

    def test_mesru_govde_degismez(self, client):
        """Nesne gövdesi eskisi gibi ucun kendi sözleşmesine gider."""
        r = client.post('/api/slosh-analysis', json={'radius': 1.0},
                        headers={'Host': SELF_HOST})
        assert r.status_code == 400
        assert r.get_json()['invalid_fields'][0]['field'] == 'fill_height'
        r = client.post('/export_tank_cad', json={},
                        headers={'Host': SELF_HOST})
        assert r.status_code == 400
        assert r.get_json() == {'error': 'Tank data not found'}


def _sgc_parcali_kw(govde, ctype):
    """Content-Length'siz parçalı gövde (sunucu akışı sonlandırmış gibi);
    ``client.post(<literal rota>, **...)`` için (rota çağrısı literal kalır:
    d24 çözülemeyen rota sayacı)."""
    return {'input_stream': io.BytesIO(govde),
            'headers': {'Host': SELF_HOST, 'Content-Type': ctype,
                        'Transfer-Encoding': 'chunked'},
            'environ_overrides': {'wsgi.input_terminated': True}}


def _sgc_csv(n):
    """Artan zaman damgalı geçerli itki CSV'si, en az ``n`` bayt."""
    satirlar, boy, i = ['time,thrust'], len('time,thrust') + 1, 0
    while boy < n:
        satir = '%.4f,%.3f' % (i * 0.001, 100.0 + (i % 50))
        satirlar.append(satir)
        boy += len(satir) + 1
        i += 1
    return ('\n'.join(satirlar) + '\n').encode()


#: Parçalı gövde vakaları (rota -> (içerik tipi, gövde)); tavan ölçekte
#: ``SG07_OLCUM_TAVANI``.
SGC_PARCALI_TAVAN_USTU = {
    '/api/altitude-to-pressure': (
        'application/json',
        json.dumps({'altitude': 1000, '_d': SG07_ASIRI_DOLGU}).encode()),
    '/api/validation/upload-csv': (
        'text/csv', _sgc_csv(SG07_OLCUM_TAVANI + 100_000)),
}
SGC_PARCALI_TAVAN_ALTI = {
    '/api/altitude-to-pressure': (
        'application/json',
        json.dumps({'altitude': 1000, '_d': 'x' * 500_000}).encode()),
    '/api/validation/upload-csv': ('text/csv', _sgc_csv(4096)),
}


class TestSG07aParcaliGovde:
    """ÖNCE (``sgc/sonuc/sg07a_once_werkzeug.json``, gerçek Werkzeug
    sunucusu): tavanı aşan parçalı gövde JSON uçlarında tavanda kesilip
    400 ``malformed_json_body``, yüklemede HTML 413, CSV ucunda KESİLMİŞ
    veriyle 200 alıyordu."""

    @pytest.fixture(autouse=True)
    def _olcek(self, monkeypatch):
        monkeypatch.setitem(app.config, 'MAX_CONTENT_LENGTH',
                            SG07_OLCUM_TAVANI)

    @pytest.mark.parametrize('yol', ['/api/altitude-to-pressure',
                                     '/api/validation/upload-csv'])
    def test_tavan_ustu_json_413(self, client, yol):
        ctype, govde = SGC_PARCALI_TAVAN_USTU[yol]
        assert len(govde) > SG07_OLCUM_TAVANI
        r = client.post(yol, **_sgc_parcali_kw(govde, ctype))
        assert r.status_code == 413, (yol, r.status_code, r.get_data()[:120])
        assert r.get_json()['error'] == 'request_body_too_large'

    @pytest.mark.parametrize('yol', ['/api/altitude-to-pressure',
                                     '/api/validation/upload-csv'])
    def test_tavan_alti_content_length_ile_ayni(self, client, yol):
        """Meşru parçalı gövde, Content-Length'li eşiyle bit-aynı yanıt."""
        ctype, govde = SGC_PARCALI_TAVAN_ALTI[yol]
        p = client.post(yol, **_sgc_parcali_kw(govde, ctype))
        d = client.post(yol, data=govde, headers={
            'Host': SELF_HOST, 'Content-Type': ctype})
        assert (p.status_code, p.get_data()) == (d.status_code,
                                                 d.get_data()), yol
        assert p.status_code == 200, yol

    def test_yardimci(self):
        def ortam(govde, **ek):
            e = {'wsgi.input': io.BytesIO(govde),
                 'HTTP_TRANSFER_ENCODING': 'chunked',
                 'wsgi.input_terminated': True}
            e.update(ek)
            return e
        f = limits.streamed_body_budget_error
        e = ortam(b'x' * 10)
        assert f(e, 10) is None                              # eşit geçer
        assert (e['CONTENT_LENGTH'], e['wsgi.input'].read()) == ('10',
                                                                 b'x' * 10)
        assert 'HTTP_TRANSFER_ENCODING' not in e
        g, kod = f(ortam(b'x' * 11), 10)
        assert (kod, g['error'], g['maximum']) == (
            413, 'request_body_too_large', 10)
        # Content-Length de gelse Transfer-Encoding kazanır (RFC 9112 §6.3).
        g, kod = f(ortam(b'x' * 11, CONTENT_LENGTH='5'), 10)
        assert kod == 413
        e = ortam(b'x' * 7, CONTENT_LENGTH='5')
        assert f(e, 10) is None and e['CONTENT_LENGTH'] == '7'
        assert f(ortam(b'x' * 11), None) is None             # tavan yok
        e = ortam(b'x' * 11)
        del e['wsgi.input_terminated']
        assert f(e, 10) is None                              # akış sonsuz olabilir
        e = ortam(b'x' * 11, HTTP_TRANSFER_ENCODING='')
        assert f(e, 10) is None                              # parçalı değil

    def test_uc_normallestirilmis_uzunlugu_gorur(self):
        """Kapıdan sonra ``request.content_length`` gerçek uzunluk (None
        değil): uçların kendi uzunluk kapıları parçalı gövdede de çalışır."""
        govde = json.dumps({'altitude': 1000}).encode()
        with app.test_request_context(
                '/api/altitude-to-pressure', method='POST',
                input_stream=io.BytesIO(govde),
                headers={'Host': SELF_HOST, 'Content-Type': 'application/json',
                         'Transfer-Encoding': 'chunked'},
                environ_overrides={'wsgi.input_terminated': True}):
            from flask import request
            assert app_module._reject_oversized_body() is None
            assert request.content_length == len(govde)
            assert request.get_json() == {'altitude': 1000}


class TestSG07cStepTavani:
    """ÖNCE: ``step_api.MAX_UPLOAD_BYTES`` 50 MiB beyan ediyordu, genel
    tavan 32 MiB ve önce çalışıyor; STEP kapısı hiç ateşlenmiyordu."""

    def test_tek_deger(self):
        from hrma.importers import step_api
        assert step_api.MAX_UPLOAD_BYTES == app.config['MAX_CONTENT_LENGTH']
        assert step_api.MAX_UPLOAD_BYTES == body_limit.REQUEST_BODY_MAX_BYTES

    @pytest.mark.parametrize('dosya, hedef', [
        ('hrma/importers/step_api.py', 'MAX_UPLOAD_BYTES'),
        ('hrma/app.py', "app.config['MAX_CONTENT_LENGTH']"),
    ])
    def test_ikinci_sayi_yok(self, dosya, hedef):
        """Atama sayı değil tek kaynaktaki adı taşır (AST)."""
        import ast
        agac = ast.parse((ROOT / dosya).read_text(encoding='utf-8'))
        degerler = []
        for dugum in ast.walk(agac):
            if isinstance(dugum, ast.Assign) and len(dugum.targets) == 1:
                if ast.unparse(dugum.targets[0]) == hedef:
                    degerler.append(dugum.value)
        assert len(degerler) == 1, (dosya, len(degerler))
        assert isinstance(degerler[0], ast.Name), ast.unparse(degerler[0])
        assert degerler[0].id == 'REQUEST_BODY_MAX_BYTES'


# ===========================================================================
# SG-2 şart turu (13 Eki) — Ş2: kaçış yardımcısı sayfada global
# ===========================================================================

from html.parser import HTMLParser  # noqa: E402

#: HTML'in "klasik betik" saydığı ``type`` değerleri (küçük harf, kırpılmış;
#: öznitelik yoksa boş dize). ``module`` ve tanınmayan değerler klasik
#: DEĞİLDİR: modül betiğinin üst düzey bildirimleri global nesneye bağlanmaz.
SG05_KLASIK_BETIK_TURLERI = frozenset({'', 'text/javascript',
                                       'application/javascript'})

#: node koşucusu (girdi: ``ad``, ``kaynak``, ``isaret``). Betik vm
#: bağlamında İLK DEYİMDEN ÖNCE durdurulur: başına tek bir ``throw`` konur.
#: ECMAScript GlobalDeclarationInstantiation üst düzey işlev bildirimlerini
#: hiçbir deyim koşmadan global nesneye bağlar; IIFE ya da blok içindeki
#: bildirim bağlanmaz. Sayfa kodunun hiçbir satırı ÇALIŞMAZ.
_SG05_GLOBAL_KOSUCU = r"""
const vm = require('vm');
const DUR = 'HRMA_SG05_ILK_DEYIMDEN_ONCE_DUR';
const ctx = vm.createContext({});
let hata = null;
try {
  vm.runInContext('throw ' + JSON.stringify(DUR) + ';\n' + girdi.kaynak, ctx,
                  {filename: girdi.ad});
  hata = 'betik durdurulamadi';
} catch (e) {
  if (e !== DUR) { hata = String((e && e.stack) || e); }
}
const tur = vm.runInContext('typeof globalThis.escapeNoticeText', ctx);
const cikti = vm.runInContext('(globalThis.escapeNoticeText || String)('
                              + JSON.stringify(girdi.isaret) + ')', ctx);
process.stdout.write(JSON.stringify({hata: hata, tur: tur, cikti: cikti}));
"""


class _SG05SatirIciBetikler(HTMLParser):
    """Sunulan HTML'deki ``<script>`` öğeleri (öznitelikler + kaynak).

    ``html.parser`` betik içeriğini ham metin (CDATA) olarak verir;
    karakter başvuruları çözülmez (tarayıcıdaki gibi)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.betikler = []
        self._acik = None

    def handle_starttag(self, tag, attrs):
        if tag == 'script':
            self._acik = {'oznitelik': dict(attrs), 'parcalar': [],
                          'satir': self.getpos()[0]}

    def handle_data(self, data):
        if self._acik is not None:
            self._acik['parcalar'].append(data)

    def handle_endtag(self, tag):
        if tag == 'script' and self._acik is not None:
            acik, self._acik = self._acik, None
            self.betikler.append({'oznitelik': acik['oznitelik'],
                                  'satir': acik['satir'],
                                  'kaynak': ''.join(acik['parcalar'])})


@node_gerekli
class TestSG05KacisYardimcisiSayfadaGlobal:
    """Ş2 (denetim 13 Eki, uyumsuz 2): 22 sarmal
    ``(globalThis.escapeNoticeText || String)(…)`` yardımcı global DEĞİLSE
    sessizce kaçışsız ``String``'e düşer (fail-open). ``TestSG05DomIsaret``
    yardımcıyı koşucunun global'ine KENDİSİ koyduğu için bunu göremez
    (ölçüldü: sıvı tanımı IIFE içine alınınca üç güvenlik dosyası yeşil).

    Bu bekçi sayfanın SUNULAN HTML'inde (``/liquid``, ``/solid``) yardımcının
    ``type=module`` OLMAYAN satır içi betiğin ÜST DÜZEY işlev bildirimi
    olduğunu, yani sayfada ``globalThis.escapeNoticeText``'in çözüldüğünü
    ve sarmalın gerçekten kaçışladığını node vm ile ölçer."""

    @pytest.mark.parametrize('sayfa', ['/liquid', '/solid'])
    def test_yardimci_klasik_betikte_ust_duzey(self, client, sayfa):
        r = client.get(sayfa, headers={'Host': SELF_HOST})
        assert r.status_code == 200, (sayfa, r.status_code)
        ayristirici = _SG05SatirIciBetikler()
        ayristirici.feed(r.get_data(as_text=True))
        ayristirici.close()
        tanimlayan = [b for b in ayristirici.betikler
                      if 'src' not in b['oznitelik']
                      and 'function escapeNoticeText(' in b['kaynak']]
        assert len(tanimlayan) == 1, (
            sayfa, [(b['satir'], b['oznitelik']) for b in tanimlayan])
        betik = tanimlayan[0]
        tur = (betik['oznitelik'].get('type') or '').strip().lower()
        assert tur in SG05_KLASIK_BETIK_TURLERI, (sayfa, betik['satir'], tur)
        girdi = json.dumps({'ad': f'{sayfa}:{betik["satir"]}',
                            'kaynak': betik['kaynak'],
                            'isaret': SG05_ISARET})
        kod = ('const girdi = JSON.parse(' + json.dumps(girdi) + ');\n'
               + _SG05_GLOBAL_KOSUCU)
        out = subprocess.run([NODE, '-'], input=kod, capture_output=True,
                             text=True, timeout=60)
        assert out.returncode == 0, out.stderr[-2000:]
        sonuc = json.loads(out.stdout)
        assert sonuc['hata'] is None, (sayfa, sonuc['hata'][-1500:])
        assert sonuc['tur'] == 'function', (sayfa, sonuc)
        assert sonuc['cikti'] == SG05_ISARET_KACISLI, (sayfa, sonuc['cikti'])


# ===========================================================================
# SG-2 şart turu (13 Eki) — Ş3: port bekçilerinin ortam hijyeni
# ===========================================================================

class TestSG02PortBekcisiOrtamHijyeni:
    """Ş3 (denetim 13 Eki, uyumsuz 3): ``register_self_port`` çağıran iki
    port bekçisi süreç ortamını değişmeden bırakır.

    ÖNCE (``sgs/sonuc/s3_sonda_once.txt``): denetçi sondası iki sınıftan
    sonra aynı süreçte ``HRMA_SELF_PORT='8087'`` gördü."""

    def test_yardimci_register_yazimini_geri_alir(self):
        anahtar = origin_gate.SELF_PORT_ENV
        port = TestSG02RunPyPortuBildirir.PORT
        baslangic = os.environ.get(anahtar)
        sahte_app = type('SahteApp', (), {'config': {}})()
        with pytest.MonkeyPatch.context() as dis:
            # Sızıntının tetiklendiği durum kurulur: değişken YOK (kayıtlı).
            dis.setenv(anahtar, '')
            dis.delenv(anahtar)
            with pytest.MonkeyPatch.context() as mp:
                _self_port_ortami_yok(mp)
                origin_gate.register_self_port(sahte_app, port)
                assert os.environ.get(anahtar) == str(port)
            assert anahtar not in os.environ, os.environ.get(anahtar)
        assert os.environ.get(anahtar) == baslangic

    def test_iki_port_bekcisi_yardimciyi_kullanir(self):
        """AST: iki sınıf da yardımcıyı çağırır; dosyada ``SELF_PORT_ENV``
        için kayıtsız ``delenv(..., raising=...)`` kalmadı."""
        import ast
        agac = ast.parse(Path(__file__).read_text(encoding='utf-8'))
        siniflar = {d.name: d for d in agac.body
                    if isinstance(d, ast.ClassDef)}
        for ad in ('TestSG02RunPyPortuBildirir',
                   'TestSG02RunWindowsPortuBildirir'):
            cagrilar = {ast.unparse(c.func) for c in ast.walk(siniflar[ad])
                        if isinstance(c, ast.Call)}
            assert '_self_port_ortami_yok' in cagrilar, ad
        kayitsiz = [c.lineno for c in ast.walk(agac)
                    if isinstance(c, ast.Call)
                    and isinstance(c.func, ast.Attribute)
                    and c.func.attr == 'delenv'
                    and any(k.arg == 'raising' for k in c.keywords)
                    and c.args and 'SELF_PORT_ENV' in ast.unparse(c.args[0])]
        assert not kayitsiz, kayitsiz


# ===========================================================================
# Waitress gövde tavanı (14 Eki; SG-2 denetimi uyumsuz 7, karar §28-46)
# ===========================================================================

#: Waitress'in ret kuralı (3.0.2, ``waitress/parser.py:158`` Content-Length
#: ve ``:177`` parçalı gövde): ``uzunluk >= max_request_body_size`` olan
#: gövde 413 alır. Uygulamanın kuralı ``uzunluk > tavan``
#: (``limits.body_budget_error``). Aynı gövdeyi kabul etmeleri için
#: ``max_request_body_size = tavan + 1`` gerekir.
def _waitress_reddeder(uzunluk, max_request_body_size):
    return uzunluk >= max_request_body_size


#: Küçük ölçek sondası için tavan [bayt] (gerçek 32 MiB / 1 GiB yok).
SGW_KUCUK_TAVAN = 4096
#: Başlatma yollarının bekçide kullandığı port (ağ açılmaz).
SGW_PORT = 8089
SGW_YOLLAR = ('hrma/run.py', 'hrma/run_windows.py', 'packaging/launcher.py')


def _sgw_sahte_waitress(monkeypatch, gorulen):
    sahte = type(sys)('waitress')
    sahte.serve = lambda wsgi, **kw: gorulen.append(kw)
    monkeypatch.setitem(sys.modules, 'waitress', sahte)


def _sgw_zamanlayici_yok(*a, **k):
    return type('T', (), {'start': lambda s: None})()


def _sgw_run_py(monkeypatch, tmp_path, gorulen):
    import hrma.run as run_mod
    monkeypatch.setattr(sys, 'path', list(sys.path))
    monkeypatch.setattr(run_mod.platform, 'system', lambda: 'Windows')
    monkeypatch.setattr(run_mod, 'Timer', _sgw_zamanlayici_yok)
    run_mod.run_server()


def _sgw_run_windows(monkeypatch, tmp_path, gorulen):
    import hrma.run_windows as rw
    monkeypatch.setattr(sys, 'path', list(sys.path))
    monkeypatch.setattr(rw, 'check_dependencies', lambda: [])
    monkeypatch.setattr(rw, 'Timer', _sgw_zamanlayici_yok)
    rw.run_server()


class _SgwPencereKapandi(Exception):
    """Başlatıcı pencere adımına geldi: sunucu çağrısı yapılmış demektir."""


def _sgw_launcher(monkeypatch, tmp_path, gorulen):
    import importlib.util
    # Başlatıcı modül düzeyinde sys.dont_write_bytecode yazar; geri alınır.
    monkeypatch.setattr(sys, 'dont_write_bytecode', sys.dont_write_bytecode)
    spec = importlib.util.spec_from_file_location(
        'hrma_launcher_sgw', ROOT / 'packaging' / 'launcher.py')
    la = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(la)
    monkeypatch.chdir(tmp_path)          # main() os.chdir yapar; geri alınır
    monkeypatch.setenv('MPLBACKEND', os.environ.get('MPLBACKEND', 'Agg'))
    for ad in ('_setup_console', '_setup_paths', '_load_real_app',
               '_wait_for_port'):
        monkeypatch.setattr(la, ad, lambda *a, **k: None)
    monkeypatch.setattr(la, '_hrma_version', lambda: '')
    monkeypatch.setattr(la, '_pick_port', lambda: (SGW_PORT, False))
    monkeypatch.setattr(la, '_outputs_dir', lambda: str(tmp_path))

    class _Yanit:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"ready": false}'

    monkeypatch.setattr(la.urllib.request, 'urlopen',
                        lambda *a, **k: _Yanit())

    class _EsZamanliThread:
        def __init__(self, target=None, daemon=None, **k):
            self._target = target

        def start(self):
            self._target()

    monkeypatch.setattr(la, 'threading',
                        type(sys)('threading_sgw'), raising=True)
    la.threading.Thread = _EsZamanliThread

    def _pencere(url):
        raise _SgwPencereKapandi(url)

    monkeypatch.setattr(la, '_show_window_blocking', _pencere)
    with pytest.raises(_SgwPencereKapandi):
        la.main()


SGW_BASLATICILAR = {
    'hrma/run.py': _sgw_run_py,
    'hrma/run_windows.py': _sgw_run_windows,
    'packaging/launcher.py': _sgw_launcher,
}


def _sgw_serve_kwargs(monkeypatch, tmp_path, yol):
    """``yol`` başlatma yolunun waitress ``serve`` anahtar sözcükleri."""
    monkeypatch.setenv('HRMA_PORT', str(SGW_PORT))
    _self_port_ortami_yok(monkeypatch)
    monkeypatch.setitem(app.config, origin_gate.SELF_PORT_CONFIG_KEY, None)
    monkeypatch.setattr(app, 'run', lambda *a, **k: pytest.fail(
        f'{yol}: waitress varken Flask sunucusuna düştü'))
    gorulen = []
    _sgw_sahte_waitress(monkeypatch, gorulen)
    SGW_BASLATICILAR[yol](monkeypatch, tmp_path, gorulen)
    assert len(gorulen) == 1, (yol, gorulen)
    assert gorulen[0].get('port') == SGW_PORT, (yol, gorulen)
    return gorulen[0]


class TestWaitressGovdeTavani:
    """Üç waitress başlatma yolunda gövde tavanı = uygulamanın tavanı.

    ÖNCE (``docs/scofield/raw/OH/V3/guvenlik/sgw/sonuc/waitress_once.json``;
    gerçek ``hrma/run.py`` waitress dalı + paketli waitress 3.0.2):
    ``serve``'e ``max_request_body_size`` verilmiyordu, waitress varsayılanı
    1 073 741 824 bayt (1 GiB). Waitress gövdeyi uygulamaya, yani köken
    kapısına, vermeden ÖNCE tamamen alır: yabancı Origin'li tavan + 1 baytlık
    istek, yalnız başlıkla 3 s'de yanıt almadı (sunucu gövdeyi bekliyordu);
    gövdenin 33 554 433 baytının tamamı kabul edildi, 403 sonra geldi.
    """

    @pytest.mark.parametrize('yol', SGW_YOLLAR)
    def test_serve_tavani_uygulamanin_tavanina_esit(self, monkeypatch,
                                                    tmp_path, yol):
        kw = _sgw_serve_kwargs(monkeypatch, tmp_path, yol)
        assert 'max_request_body_size' in kw, (
            f'{yol}: waitress varsayılan 1 GiB tavanla kalkıyor')
        tavan = app.config['MAX_CONTENT_LENGTH']
        assert tavan == body_limit.REQUEST_BODY_MAX_BYTES
        mrbs = kw['max_request_body_size']
        # En büyük kabul edilen gövde iki katmanda aynı.
        assert not _waitress_reddeder(tavan, mrbs), (yol, mrbs, tavan)
        assert _waitress_reddeder(tavan + 1, mrbs), (yol, mrbs, tavan)

    @pytest.mark.parametrize('yol', SGW_YOLLAR)
    def test_tavan_tek_kaynagi_izler(self, monkeypatch, tmp_path, yol):
        """Tek kaynak küçültülünce ``serve`` tavanı onunla birlikte iner
        (kopya literal yok; küçük ölçek, ağ yok)."""
        monkeypatch.setattr(body_limit, 'REQUEST_BODY_MAX_BYTES',
                            SGW_KUCUK_TAVAN)
        kw = _sgw_serve_kwargs(monkeypatch, tmp_path, yol)
        mrbs = kw.get('max_request_body_size')
        assert mrbs is not None, yol
        assert not _waitress_reddeder(SGW_KUCUK_TAVAN, mrbs), (yol, mrbs)
        assert _waitress_reddeder(SGW_KUCUK_TAVAN + 1, mrbs), (yol, mrbs)

    @pytest.mark.parametrize('yol', SGW_YOLLAR)
    def test_her_serve_cagrisi_tavan_tasir(self, yol):
        """AST: dosyadaki HER ``serve(...)`` çağrısı ``max_request_body_size``
        taşır ve değeri tek kaynağın adından türer (sayı literali değil)."""
        import ast
        agac = ast.parse((ROOT / yol).read_text(encoding='utf-8'))
        cagrilar = [c for c in ast.walk(agac) if isinstance(c, ast.Call)
                    and isinstance(c.func, ast.Name) and c.func.id == 'serve']
        assert cagrilar, yol
        for c in cagrilar:
            kw = {k.arg: k.value for k in c.keywords}
            assert 'max_request_body_size' in kw, (yol, c.lineno)
            adlar = {n.id for n in ast.walk(kw['max_request_body_size'])
                     if isinstance(n, ast.Name)}
            assert 'REQUEST_BODY_MAX_BYTES' in adlar, (yol, c.lineno)

    @pytest.mark.parametrize('yol', SGW_YOLLAR)
    def test_gercek_waitress_ayristiricisi_tavan_arti_biri_reddeder(
            self, monkeypatch, tmp_path, yol):
        """Küçük ölçekte davranış: yolun ``serve``'e verdiği ayarla GERÇEK
        waitress ayrıştırıcısı tavanı kabul eder, tavan + 1'i (Content-Length
        ve parçalı) gövdeyi almadan / sayarken 413 ile reddeder. Waitress
        yalnız Windows ve paket bağımlılığıdır (requirements.txt:78,
        packaging/requirements_bundle.txt:32); kurulu değilse bu düğüm
        atlanır, kuralın modeli (yukarıdaki iki düğüm) her ortamda koşar."""
        waitress = pytest.importorskip('waitress.parser')
        from waitress.adjustments import Adjustments
        from waitress.utilities import RequestEntityTooLarge
        monkeypatch.setattr(body_limit, 'REQUEST_BODY_MAX_BYTES',
                            SGW_KUCUK_TAVAN)
        kw = _sgw_serve_kwargs(monkeypatch, tmp_path, yol)
        adj = Adjustments(max_request_body_size=kw['max_request_body_size'])

        def ayristir(istek):
            p = waitress.HTTPRequestParser(adj)
            veri = istek
            while veri and not p.completed:
                veri = veri[p.received(veri):]
            return p

        def cl_istegi(n, govde=True):
            bas = (f'POST /api/altitude-to-pressure HTTP/1.1\r\n'
                   f'Host: 127.0.0.1\r\nContent-Length: {n}\r\n\r\n')
            return bas.encode('ascii') + (b' ' * n if govde else b'')

        def parcali_istek(n):
            return (b'POST /api/altitude-to-pressure HTTP/1.1\r\n'
                    b'Host: 127.0.0.1\r\nTransfer-Encoding: chunked\r\n\r\n'
                    + b'%x\r\n' % n + b' ' * n + b'\r\n0\r\n\r\n')

        tamam = ayristir(cl_istegi(SGW_KUCUK_TAVAN))
        assert tamam.completed and tamam.error is None, (yol, tamam.error)
        assert tamam.content_length == SGW_KUCUK_TAVAN
        # Yalnız başlık: gövde beklenmeden ret (tampon yok).
        ret = ayristir(cl_istegi(SGW_KUCUK_TAVAN + 1, govde=False))
        assert isinstance(ret.error, RequestEntityTooLarge), (yol, ret.error)
        assert ret.error.code == 413
        ret_p = ayristir(parcali_istek(SGW_KUCUK_TAVAN + 1))
        assert isinstance(ret_p.error, RequestEntityTooLarge), (yol,
                                                                ret_p.error)


class TestWaitressBaglantiTavani:
    """Waitress bağlantı tavanı (ana model, 14 Eki; SG-2 waitress turu devri).

    Waitress her bağlantının gövdesini köken kapısından önce tavana kadar
    tamponlar; geçici tampon bağlantı sayısıyla çarpılır. run_windows.py
    gerekçesiz ``connection_limit=1000`` veriyordu (en kötü ~32 GiB). Kural:
    ``serve(...)`` çağrısı ``connection_limit`` veriyorsa değeri tek kaynaktaki
    ``WAITRESS_CONNECTION_LIMIT`` adından gelir (sayı literali değil) ve o ad
    waitress varsayılanını (100) aşmaz.
    """

    def test_tek_kaynak_varsayilani_asmaz(self):
        assert body_limit.WAITRESS_CONNECTION_LIMIT <= 100

    @pytest.mark.parametrize('yol', SGW_YOLLAR)
    def test_serve_baglanti_tavani_tek_kaynaktan(self, yol):
        import ast
        agac = ast.parse((ROOT / yol).read_text(encoding='utf-8'))
        for c in ast.walk(agac):
            if not (isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
                    and c.func.id == 'serve'):
                continue
            kw = {k.arg: k.value for k in c.keywords}
            if 'connection_limit' not in kw:
                continue  # waitress varsayılanı (100)
            deger = kw['connection_limit']
            assert isinstance(deger, ast.Name), (yol, c.lineno)
            assert deger.id == 'WAITRESS_CONNECTION_LIMIT', (yol, c.lineno)
