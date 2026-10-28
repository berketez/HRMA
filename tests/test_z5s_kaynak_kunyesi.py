"""Z5S / P09-F — KAYNAK KÜNYESİ VE VERİ TAZELİĞİ BEKÇİLERİ.

Tek kural: **künye kazanılır.** Bir sayı gerçekten o kaynaktan geldiyse o
kaynağın adı basılır; gelmediyse kaynağın adı DEĞİL gerçek köken yazılır.
Bu, Z4'te kurulan "kazanılmış güvenlik katsayısı" sözleşmesinin veri
katmanındaki eşliğidir. Hiçbir fiziksel değer değiştirilmedi; bekçiler
yalnız künye/beyan/yaş alanlarını ölçer ve sayıların OYNAMADIĞINI de
kilitler.

Kapsanan kalemler
-----------------
P9B5-15  fetch_nist_gas_properties HTTP 200 + SIFIR ayıklama -> 'Live'
P9B5-33  fetch_nist_data'nın birincil kaynağı NIST değil, nist-api.fly.dev
P9B5-32  external_data_fetcher "real-time fetches" diyor, ağ çağrısı yok
P9B5-22  fetch_spacex_telemetry gömülü sabitleri 'SpaceX Public API' sanıyor
P9B5-23  'isp_sea_level' aslında eps=16 VAKUM değeri / 0,88 uydurması
P9B5-24  bileşik confidence tazeliğe bakmıyor ('stale' kayıt hâlâ 'high')
P9B4-19  offline_store.get() kaydın YAŞINI düşürüyor
P9B5-08  oksitleyicide boiling_point = 200 K kategori sabiti, CoolProp künyeli

AĞA ÇIKILMAZ: her test ``requests`` çağrılarını ConnectionError'a bağlar
ya da sahte taşıyıcı verir. Gerçek ağ davranışı DEĞİŞTİRİLMEDİ, yalnız
künye dürüstlüğü sınanır.
"""

import ast
import copy
import json
import os
import pathlib
import re

import pytest
import requests

from hrma.data import external_data_fetcher as edf
from hrma.data import offline_store
from hrma.data import web_propellant_api as wpa
from hrma.data.nasa_realtime_validator import NASARealtimeValidator
from hrma.data.open_source_propellant_api import OpenSourcePropellantAPI


# ---------------------------------------------------------------------------
# Ortak yardımcılar — ağ KAPALI, kullanıcı dizini GEÇİCİ
# ---------------------------------------------------------------------------

class _AgKapali(requests.ConnectionError):
    """Testte ağa çıkma girişiminin işareti."""


def _ag_patlat(*a, **kw):
    raise _AgKapali('bekci: ag kapali')


@pytest.fixture(autouse=True)
def _ag_ve_dizin(tmp_path, monkeypatch):
    """Her testte ağ kapalı + kullanıcı veri dizini geçici olsun."""
    monkeypatch.setattr(requests, 'get', _ag_patlat, raising=False)
    monkeypatch.setattr(requests, 'post', _ag_patlat, raising=False)
    monkeypatch.setattr(requests.Session, 'get', _ag_patlat, raising=False)
    monkeypatch.setattr(requests.Session, 'post', _ag_patlat, raising=False)
    monkeypatch.setenv('HRMA_USER_DATA_DIR', str(tmp_path / 'userdata'))
    os.makedirs(tmp_path / 'userdata', exist_ok=True)
    offline_store._read_memo.clear()
    yield
    offline_store._read_memo.clear()


class _SahteYanit:
    """requests.Response yerine geçen asgari taşıyıcı (ağ YOK)."""

    def __init__(self, status_code=200, text='', payload=None):
        self.status_code = status_code
        self.text = text
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError('no json')
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


def _temiz_api(tmp_path):
    """Önbelleği geçici dizine bakan taze bir WebPropellantAPI."""
    api = wpa.WebPropellantAPI()
    api.cache_dir = str(tmp_path / 'propcache')
    os.makedirs(api.cache_dir, mode=0o700, exist_ok=True)
    return api


# ===========================================================================
# P9B5-15 — NIST WebBook: HTTP 200 'Live' künyesini KAZANDIRMAZ
# ===========================================================================

class TestP9B5_15NistGazKunyesi:
    """Yanıtın gelmesi, sayının ayıklanması demek değildir."""

    def test_bos_yanit_live_kunyesi_almaz(self, monkeypatch):
        """HTTP 200 ama TEK SAYI ayıklanamadı -> 'Live' YASAK.

        ÖNCE: ``{'molecular_weight': None, 'cp_cv_ratio': None,
        'source': 'NIST WebBook Live'}`` dönüyordu.
        """
        nv = NASARealtimeValidator()
        monkeypatch.setattr(
            requests, 'get',
            lambda *a, **kw: _SahteYanit(200, '<html>bos sayfa</html>'))

        out = nv.fetch_nist_gas_properties('lox')

        assert isinstance(out, dict), 'HTTP 200 yolunda sözlük dönmeli'
        assert 'live' not in str(out.get('source', '')).lower(), (
            "sıfır sayı ayıklandı ama künye hâlâ 'Live' diyor: %r"
            % out.get('source'))
        assert out.get('status') == 'parse_failed'
        # Fail-closed: uydurma/None sayı basılmaz
        assert 'molecular_weight' not in out
        assert 'cp_cv_ratio' not in out
        assert sorted(out.get('unparsed_fields', [])) == [
            'cp_cv_ratio', 'molecular_weight']

    def test_gercek_sayi_ayiklaninca_live_kazanilir(self, monkeypatch):
        """Sayı GERÇEKTEN ayıklandıysa künye 'Live' olabilir (aşırı düzeltme yok)."""
        nv = NASARealtimeValidator()
        govde = 'Molecular weight 31.998 g/mol ... Cp/Cv 1.395 ...'
        monkeypatch.setattr(requests, 'get',
                            lambda *a, **kw: _SahteYanit(200, govde))

        out = nv.fetch_nist_gas_properties('lox')

        assert out['status'] == 'success'
        assert 'Live' in out['source']
        assert out['molecular_weight'] == pytest.approx(31.998)
        assert out['cp_cv_ratio'] == pytest.approx(1.395)
        assert out['parsed_fields'] == ['cp_cv_ratio', 'molecular_weight']
        assert out['unparsed_fields'] == []

    def test_yarim_ayiklama_kismi_beyan_eder(self, monkeypatch):
        """Bir alan geldi biri gelmedi -> 'partial', eksik alan ADIYLA yazılır."""
        nv = NASARealtimeValidator()
        monkeypatch.setattr(
            requests, 'get',
            lambda *a, **kw: _SahteYanit(200, 'Molecular weight 2.016 g/mol'))

        out = nv.fetch_nist_gas_properties('lh2')

        assert out['status'] == 'partial'
        assert out['molecular_weight'] == pytest.approx(2.016)
        assert 'cp_cv_ratio' not in out
        assert out['unparsed_fields'] == ['cp_cv_ratio']


# ===========================================================================
# P9B5-33 — Künye kaynağın GERÇEK işletmecisini söyler
# ===========================================================================

class TestP9B5_33UcuncuTarafKunyesi:
    """'NIST API (Live)' etiketi NIST'in ucundan gelmiyordu."""

    #: Modülün BİRİNCİL (tek) ağ kaynağı
    UC = 'https://nist-api.fly.dev/crawl.json'

    def _canli_cekim(self, tmp_path, monkeypatch):
        api = _temiz_api(tmp_path)
        yanit = _SahteYanit(200, payload={
            'items': [{'properties': {'density': 1141.7,
                                      'viscosity': 0.000194}}]})
        monkeypatch.setattr(api.session, 'get', lambda *a, **kw: yanit)
        return api.fetch_nist_data('lox')

    def test_birincil_uc_hala_ucuncu_taraf(self):
        """Çapa: kaynak gerçekten NIST'in kendi sunucusu değil."""
        assert wpa.WebPropellantAPI().endpoints['nist_unofficial'] == self.UC

    def test_kunye_nist_iddiasini_kazanmadan_basmaz(self, tmp_path,
                                                   monkeypatch):
        out = self._canli_cekim(tmp_path, monkeypatch)

        kaynak = str(out.get('source', ''))
        assert out.get('source_is_official_nist') is False, (
            'resmî NIST olup olmadığı makinece okunabilir olmalı')
        assert out.get('source_url') == self.UC
        assert 'nist-api.fly.dev' in kaynak, (
            'künye gerçek işletmeciyi anmalı: %r' % kaynak)
        assert kaynak != 'NIST API (Live)', (
            'eski, kazanılmamış künye geri gelmiş')
        # Sayı DEĞİŞMEDİ
        assert out['density'] == pytest.approx(1141.7)

    def test_bayat_yolda_live_eki_yine_duzeliyor(self, tmp_path, monkeypatch):
        """Yeni künye ``_damgala``nın 'Live' düzeltmesini bozmamalı."""
        api = _temiz_api(tmp_path)
        canli = {'compound': 'lox', 'density': 1141.7, 'status': 'success',
                 'source': wpa.NIST_UCUNCU_TARAF_KUNYE}
        for durum, beklenen in ((wpa.DATA_STATE_STALE, 'Stale cache'),
                                (wpa.DATA_STATE_OFFLINE, 'Stored copy'),  # v3.0.1: 'Offline store' etiketi söküldü
                                (wpa.DATA_STATE_CACHED, 'Cached')):
            damgali = api._damgala(dict(canli), durum, 10.0)
            assert 'live' not in damgali['source'].lower(), damgali['source']
            assert beklenen in damgali['source'], damgali['source']


# ===========================================================================
# P9B5-32 — "real-time fetches" iddiası KAYNAKLA ölçülür
# ===========================================================================

class TestP9B5_32AgIddiasi:
    """Modül ağ çağrısı yapmıyorsa künyesi de öyle demeli."""

    KAYNAK = pathlib.Path(edf.__file__)

    #: Ağ çağrısı sayılan öznitelik adları
    AG_CAGRILARI = {'get', 'post', 'put', 'delete', 'patch', 'head',
                    'request', 'urlopen', 'urlretrieve'}
    #: Ağ taşıyıcısı sayılan kök adlar
    AG_TASIYICILARI = {'requests', 'session', 'urllib', 'aiohttp', 'httpx',
                       'urlopen', 'http'}

    def _olculen_ag_cagrilari(self):
        agac = ast.parse(self.KAYNAK.read_text(encoding='utf-8'))
        bulunan = []
        for dugum in ast.walk(agac):
            if not isinstance(dugum, ast.Call):
                continue
            fn = dugum.func
            if isinstance(fn, ast.Attribute) and fn.attr in self.AG_CAGRILARI:
                kok = fn.value
                while isinstance(kok, ast.Attribute):
                    kok = kok.value
                ad = getattr(kok, 'id', '')
                if ad.lower() in self.AG_TASIYICILARI:
                    bulunan.append('%s.%s (satır %d)'
                                   % (ad, fn.attr, dugum.lineno))
            elif isinstance(fn, ast.Name) and fn.id in {'urlopen',
                                                        'urlretrieve'}:
                bulunan.append('%s (satır %d)' % (fn.id, dugum.lineno))
        return bulunan

    def test_dosyada_ag_cagrisi_yok(self):
        """Ölçüm: bu dosyada tek bir HTTP çağrısı yok."""
        assert self._olculen_ag_cagrilari() == []

    def test_bayrak_olcumle_tutuyor(self):
        """``MAKES_NETWORK_CALLS`` kaynağın ölçümüyle çelişemez."""
        assert edf.MAKES_NETWORK_CALLS is bool(self._olculen_ag_cagrilari())
        assert edf.MAKES_NETWORK_CALLS is False

    def test_kunye_gercek_zamanli_cekim_iddia_etmiyor(self):
        """Modül/sınıf künyesi kazanılmamış 'fetches real-time' demez."""
        for ad, metin in (('modül', edf.__doc__ or ''),
                          ('sınıf', edf.ExternalDataFetcher.__doc__ or '')):
            # Kaldırılan kusurun birebir alıntısı muaf blokta duruyor;
            # bekçi yalnız muaf blok DIŞINDAKİ iddiayı ölçer.
            temiz = re.sub(
                r'IDDIA-LINT-MUAF-BASLANGIC.*?IDDIA-LINT-MUAF-BITIS',
                '', metin, flags=re.S)
            kucuk = temiz.lower()
            assert 'real-time' not in kucuk and 'real time' not in kucuk, (
                '%s künyesi hâlâ gerçek zamanlı çekim iddia ediyor' % ad)
            assert not re.search(r'\bfetch(es|ing)?\s+real', kucuk), ad

    def test_uc_dizeleri_cagrilmadigini_soyluyor(self):
        """Adresler duruyor ama çağrılmadıkları YAZILI (sessiz yanılgı yok)."""
        df = edf.ExternalDataFetcher()
        assert df.endpoints_are_called is False
        # Adresler DEĞİŞMEDİ (yalnız beyan eklendi)
        assert df.nist_base_url == 'https://webbook.nist.gov/cgi/'
        assert df.cea_endpoints[0] == 'https://cearun.grc.nasa.gov/cea/api'


# ===========================================================================
# P9B5-22 — Gömülü Falcon 9 sabitleri API'den gelmiş sayılmaz
# ===========================================================================

class TestP9B5_22SpacexKunyesi:
    """API'den okunan TEK alan uçuş tarihiydi."""

    #: Değişmemesi gereken gömülü sayılar (SAYI ONARIMI DEĞİL, KÜNYE ONARIMI)
    SABITLER = {'thrust_sea_level': 845000, 'thrust_vacuum': 914000,
                'isp_sea_level': 282, 'isp_vacuum': 311,
                'mixture_ratio': 2.56}

    def _cek(self, tmp_path, monkeypatch, payload):
        api = _temiz_api(tmp_path)
        monkeypatch.setattr(api.session, 'get',
                            lambda *a, **kw: _SahteYanit(200, payload=payload))
        return api.fetch_spacex_telemetry()['falcon9_merlin']

    def test_gomulu_sabitler_api_kunyesi_tasimaz(self, tmp_path, monkeypatch):
        motor = self._cek(tmp_path, monkeypatch,
                          {'date_utc': '2026-01-02T03:04:05.000Z'})

        kaynak = str(motor['source'])
        assert kaynak != 'SpaceX Public API', 'eski künye geri gelmiş'
        assert 'NOT returned by the SpaceX API' in kaynak, kaynak
        assert set(motor['constant_fields']) >= set(self.SABITLER), (
            'gömülü alanlar adlarıyla beyan edilmeli')
        assert motor['api_derived_fields'] == ['last_flight'], (
            'API''den gelen alan yalnız uçuş tarihidir')
        assert motor['last_flight'] == '2026-01-02T03:04:05.000Z'

    def test_sayilar_degismedi(self, tmp_path, monkeypatch):
        """Künye onarımı hiçbir performans sayısına dokunmadı."""
        motor = self._cek(tmp_path, monkeypatch, {'date_utc': 'x'})
        for alan, deger in self.SABITLER.items():
            assert motor[alan] == deger, alan
        assert motor['propellants'] == 'RP-1/LOX'

    def test_tarih_yoksa_uydurulmaz(self, tmp_path, monkeypatch):
        """date_utc yoksa 'Unknown' basılmaz; alan hiç konmaz + gerekçe."""
        motor = self._cek(tmp_path, monkeypatch, {'id': 'yok'})

        assert 'last_flight' not in motor
        assert motor['api_derived_fields'] == []
        assert 'no' in motor['last_flight_withheld_reason'].lower()


# ===========================================================================
# P9B5-23 — 'isp_sea_level' adı kazanılmamıştı
# ===========================================================================

class TestP9B5_23IspAdi:
    """eps=16 VAKUM değeri ve 0,88 çarpanı deniz seviyesi Isp'si değildir."""

    KAYNAK = pathlib.Path(wpa.__file__).read_text(encoding='utf-8')

    def test_cea_ayristirmasi_0_88_uydurmasini_basmiyor(self):
        """``isp_vacuum * 0.88`` yaklaşımı ile üretilen sayı yayımlanmaz."""
        api = wpa.WebPropellantAPI()
        metin = ('Isp, sec  350.5\nCSTAR, M/SEC  1750.2\n'
                 'T, K  3400.0\nGAMMAs 1.21\n')

        out = api._parse_cea_output(metin, 'rp1', 'lox')

        assert out['isp_vacuum'] == pytest.approx(350.5)
        assert 'isp_sea_level' not in out, (
            'dayanaksız 0,88 çarpanı geri gelmiş: %r'
            % out.get('isp_sea_level'))
        assert 'isp_sea_level_withheld_reason' in out
        # Eski uydurma değerin kendisi de hiçbir alanda görünmemeli
        assert 350.5 * 0.88 not in [v for v in out.values()
                                    if isinstance(v, float)]

    def test_kaynakta_0_88_carpimi_kalmadi(self):
        """Çarpan KODDA da kalmasın — metinde değil, AST'de ölçülür.

        (Gerekçe metninde '0.88' geçebilir; yasak olan onunla ÇARPMAK.)
        """
        agac = ast.parse(self.KAYNAK)
        carpimlar = [d.lineno for d in ast.walk(agac)
                     if isinstance(d, ast.BinOp)
                     and isinstance(d.op, ast.Mult)
                     and any(isinstance(y, ast.Constant) and y.value == 0.88
                             for y in (d.left, d.right))]
        assert carpimlar == [], (
            'dayanaksiz 0,88 carpani su satirlarda geri gelmis: %r'
            % carpimlar)

    def test_rocketcea_dali_isp_sea_level_atamiyor(self):
        """Kaynak düzeyi bekçi: kütüphane kurulu olmasa da koşar.

        ``_use_rocketcea_library`` içinde 'isp_sea_level' anahtarına ATAMA
        yapılmamalı (eskiden eps=16'nın vakum değeri o adla basılıyordu).
        """
        agac = ast.parse(self.KAYNAK)
        fn = next(d for d in ast.walk(agac)
                  if isinstance(d, ast.FunctionDef)
                  and d.name == '_use_rocketcea_library')
        anahtarlar = [k.value for d in ast.walk(fn)
                      if isinstance(d, ast.Dict)
                      for k in d.keys
                      if isinstance(k, ast.Constant)]
        assert 'isp_sea_level' not in anahtarlar, (
            'eps=16 vakum değeri yine deniz seviyesi diye basılıyor')
        assert 'isp_vacuum_eps16' in anahtarlar
        assert 'isp_sea_level_withheld_reason' in anahtarlar

    def test_rocketcea_canli_deger_ayni_kaldi(self):
        """Kütüphane varsa: sayı DEĞİŞMEDİ, yalnız adı düzeldi."""
        # Yokluk iddiası kurulum SORUSUNA dayanır (TestAtlamaGerekcesiDurust
        # sözleşmesi): kurulu değilken atla; kuruluyken ithal kırığı ise
        # atlanmaz, KIRMIZI yanar (ürün yolu bozulmuş demektir).
        from tests.bagimlilik_kapisi import kurulu_mu
        if not kurulu_mu('rocketcea'):
            pytest.skip('rocketcea kurulu değil (kaynak bekçisi yine koştu)')
        from rocketcea.cea_obj import CEA_Obj
        api = wpa.WebPropellantAPI()
        out = api._use_rocketcea_library('rp1', 'lox', 20.0, 2.5)
        if out.get('status') != 'success':  # pragma: no cover
            pytest.skip('rocketcea bu ortamda çözemedi: %r' % out.get('status'))

        cea = CEA_Obj(oxName='LOX', fuelName='RP1')
        # Bekçi ürünle AYNI tek kaynağı okur: burada literal yazmak,
        # ürünün merkezden okuduğu katsayının ikizini teste taşırdı
        # (ÖH D30 / fix-29a; ürün tarafı web_propellant_api.py:897).
        from hrma.constants import PSIA_PER_BAR
        beklenen = cea.get_Isp(Pc=20.0 * PSIA_PER_BAR, MR=2.5, eps=16)
        assert out['isp_vacuum_eps16'] == pytest.approx(beklenen, rel=1e-12)
        assert out['isp_vacuum_eps16_expansion_ratio'] == 16
        assert out['isp_vacuum_expansion_ratio'] == 200
        assert 'isp_sea_level' not in out


# ===========================================================================
# P9B5-24 — Bileşik güven TAZELİĞE bakar
# ===========================================================================

class TestP9B5_24GuvenTazeligi:
    """'stale' damgalı 10 yıllık kayıt 'high' güven üretemez."""

    def _bilesik(self, tmp_path, monkeypatch, durum, status='success'):
        api = _temiz_api(tmp_path)
        parca = {'density': 1141.7, 'status': status, 'data_state': durum,
                 'source': 'test', 'cache_age_seconds': 315360000.0}
        yanma = {'isp_vacuum': 350.0, 'status': status, 'data_state': durum,
                 'source': 'test'}
        monkeypatch.setattr(api, 'fetch_nist_data',
                            lambda c: copy.deepcopy(parca))
        monkeypatch.setattr(
            api, 'fetch_nasa_cea_data',
            lambda f, o, p=100, m=2.5: copy.deepcopy(yanma))
        monkeypatch.setattr(api, '_load_offline_store', lambda k: None)
        monkeypatch.setattr(wpa.offline_store, 'put', lambda k, d: True)
        return api.get_comprehensive_data('rp1', 'lox')['summary']

    def test_bayat_kayit_high_alamaz(self, tmp_path, monkeypatch):
        """ÖNCE: all_success -> koşulsuz 'high' (yaş hiç sorulmuyordu)."""
        ozet = self._bilesik(tmp_path, monkeypatch, wpa.DATA_STATE_STALE)

        assert ozet['confidence'] != 'high', (
            '10 yıllık bayat kayıt hâlâ yüksek güven üretiyor')
        assert ozet['confidence'] == 'low'
        assert ozet['data_state'] == wpa.DATA_STATE_STALE

    def test_taze_kayit_high_alabilir(self, tmp_path, monkeypatch):
        """Aşırı düzeltme yok: canlı + ayrıştırılmış veri hâlâ 'high'."""
        ozet = self._bilesik(tmp_path, monkeypatch, wpa.DATA_STATE_LIVE)
        assert ozet['confidence'] == 'high'

    def test_cevrimdisi_depo_orta_guven(self, tmp_path, monkeypatch):
        """Paket anlık görüntüsü: küratörlü ama canlı değil -> 'medium'."""
        ozet = self._bilesik(tmp_path, monkeypatch, wpa.DATA_STATE_OFFLINE)
        assert ozet['confidence'] == 'medium'

    def test_hukmun_gerekcesi_yaziliyor(self, tmp_path, monkeypatch):
        """Tek kelime yetmez: hükmün iki girdisi de yayımlanır."""
        ozet = self._bilesik(tmp_path, monkeypatch, wpa.DATA_STATE_STALE)

        girdiler = ozet['confidence_inputs']
        assert girdiler['all_sources_parsed'] is True
        assert girdiler['data_state'] == wpa.DATA_STATE_STALE
        assert girdiler['oldest_component_age_seconds'] == pytest.approx(
            315360000.0)
        assert 'data_state' in ozet['confidence_basis']

    def test_ayristirilamayan_yanit_high_alamaz(self, tmp_path, monkeypatch):
        """status != success ise canlı bile olsa 'high' verilmez."""
        ozet = self._bilesik(tmp_path, monkeypatch, wpa.DATA_STATE_LIVE,
                             status='parse_failed')
        assert ozet['confidence'] != 'high'


# ===========================================================================
# P9B4-19 — Çevrimdışı kaydın YAŞI çağırana ulaşır
# ===========================================================================

class TestP9B4_19KayitYasi:
    """39 günlük paketli anlık görüntü ile 39 dakikalık veri ayırt edilebilmeli."""

    def test_get_entry_yasi_olcuyor(self):
        anahtar = offline_store.make_key('bekci', 'taze')
        assert offline_store.put(anahtar, {'x': 1}) is True

        kayit = offline_store.get_entry(anahtar)

        assert kayit['data'] == {'x': 1}
        assert kayit['age_available'] is True
        assert 0.0 <= kayit['age_seconds'] < 120.0
        assert kayit['origin'] == 'user_cache'
        assert kayit['timestamp']

    def test_eski_kayit_genc_gorunmuyor(self):
        """39 gün geriye alınan kayıt 39 gün YAŞINDA görünmeli."""
        anahtar = offline_store.make_key('bekci', 'eski')
        offline_store.put(anahtar, {'density': 1141.7})

        yol = offline_store.user_cache_path()
        belge = json.loads(pathlib.Path(yol).read_text(encoding='utf-8'))
        belge['entries'][anahtar]['timestamp'] = '2026-07-19T12:00:00'
        pathlib.Path(yol).write_text(json.dumps(belge), encoding='utf-8')
        offline_store._read_memo.clear()

        kayit = offline_store.get_entry(anahtar)

        assert kayit['age_seconds'] > 30 * 86400.0, (
            'eski kayıt taze görünüyor: %r' % kayit['age_seconds'])
        # Gövde sözleşmesi DEĞİŞMEDİ
        assert offline_store.get(anahtar) == {'density': 1141.7}

    def test_okunamayan_damga_yas_uydurmuyor(self):
        """Damga bozuksa yaş UYDURULMAZ (0 da denmez)."""
        anahtar = offline_store.make_key('bekci', 'bozuk')
        offline_store.put(anahtar, {'x': 2})
        yol = offline_store.user_cache_path()
        belge = json.loads(pathlib.Path(yol).read_text(encoding='utf-8'))
        belge['entries'][anahtar]['timestamp'] = 'dun-aksam'
        pathlib.Path(yol).write_text(json.dumps(belge), encoding='utf-8')
        offline_store._read_memo.clear()

        kayit = offline_store.get_entry(anahtar)

        assert kayit['age_available'] is False
        assert kayit['age_seconds'] is None

    def test_paket_anlik_goruntusu_kokenini_soyluyor(self):
        """Paketle gelen kayıt 'bundled_snapshot' diye işaretli ve damgalı."""
        with open(offline_store.SNAPSHOT_PATH, encoding='utf-8') as f:
            girdiler = json.load(f)['entries']
        anahtar = sorted(girdiler)[0]

        kayit = offline_store.get_entry(anahtar)

        assert kayit['origin'] == 'bundled_snapshot'
        assert kayit['timestamp'] == girdiler[anahtar]['timestamp']
        assert kayit['age_available'] is True

    def test_get_derin_kopya_sozlesmesi_korundu(self):
        """``get()`` hâlâ derin kopya döndürür (paylaşılan nesne sızmaz)."""
        anahtar = offline_store.make_key('bekci', 'kopya')
        offline_store.put(anahtar, {'nested': {'list': [1, 2, 3]}})

        ilk = offline_store.get(anahtar)
        ilk['nested']['list'].append(99)

        assert offline_store.get(anahtar)['nested']['list'] == [1, 2, 3]

    def test_web_api_depo_yolunda_yas_tasiniyor(self, tmp_path):
        """``_load_offline_store`` yaşı sonuç sözlüğüne yazar."""
        api = _temiz_api(tmp_path)
        anahtar = offline_store.make_key('webapi', 'nist', 'bekcifuel')
        offline_store.put(anahtar, {'density': 123.4, 'status': 'success',
                                    'source': 'NIST API (Live)'})

        out = api._load_offline_store(anahtar)

        assert out['density'] == 123.4
        assert out['data_state'] == wpa.DATA_STATE_OFFLINE
        assert out['offline_record_age_state'] == 'measured'
        assert out['offline_record_origin'] == 'user_cache'
        assert out['offline_record_timestamp']
        assert isinstance(out['offline_record_age_seconds'], float)


# ===========================================================================
# P9B5-08 — Oksitleyicide 200 K kategori sabiti CoolProp künyesi taşıyamaz
# ===========================================================================

class TestP9B5_08KaynamaNoktasi:
    """LOX'un gerçek NBP'si 90,19 K; 200 K hiçbir akışkanın değildi."""

    #: NIST SRD 69 — LOX normal kaynama noktası
    LOX_NBP_K = 90.19

    def _ui(self, monkeypatch, ad, props):
        api = OpenSourcePropellantAPI()
        monkeypatch.setattr(api, 'get_comprehensive_properties',
                            lambda n, *a, **kw: dict(props))
        return api.get_propellant_for_ui('oxidizer', ad)

    def test_kaynak_yoksa_alan_basilmaz(self, monkeypatch):
        """ÖNCE: her oksitleyici için boiling_point = 200 basılıyordu."""
        ui = self._ui(monkeypatch, 'lox',
                      {'density': 1141.7,
                       'source': 'CoolProp (NIST REFPROP-based)'})

        assert 'boiling_point' not in ui, (
            'kazanılmamış kategori sabiti hâlâ basılıyor: %r'
            % ui.get('boiling_point'))
        assert ui['fields_withheld'] == ['boiling_point']
        assert 'boiling_point' in ui['fields_withheld_reason']
        # Diğer alanlara dokunulmadı
        assert ui['density'] == pytest.approx(1141.7)

    def test_gercek_deger_varsa_basilir(self, monkeypatch):
        """Aşırı düzeltme yok: kaynak çözerse sayı yayımlanır."""
        ui = self._ui(monkeypatch, 'lox',
                      {'density': 1141.7, 'boiling_point': self.LOX_NBP_K,
                       'source': 'NIST Chemistry WebBook'})

        assert ui['boiling_point'] == pytest.approx(self.LOX_NBP_K)
        assert 'fields_withheld' not in ui

    def test_coolprop_kunyesiyle_200_asla_birlikte_gelmez(self):
        """Uçtan uca: ağ kapalıyken bile 200 K + CoolProp künyesi olamaz.

        Bu, kalemin ölçülen repro'sudur: onarımdan önce
        ``oxidizer/lox`` tam olarak bu ikiliyi yayımlıyordu.
        """
        api = OpenSourcePropellantAPI()
        for ad in ('lox', 'n2o', 'oxygen'):
            ui = api.get_propellant_for_ui('oxidizer', ad)
            bp = ui.get('boiling_point')
            assert bp != 200, (
                '%s: 200 K kategori sabiti hâlâ yayımlanıyor '
                '(künye: %r)' % (ad, ui.get('data_source')))
            if bp is None:
                assert 'boiling_point' in ui.get('fields_withheld', []), ad

    def test_lox_icin_yanlis_sayi_yayimlanmiyor(self):
        """LOX yayımlanan bir kaynama noktası varsa gerçeğe yakın olmalı."""
        ui = OpenSourcePropellantAPI().get_propellant_for_ui('oxidizer', 'lox')
        if 'boiling_point' in ui:
            assert ui['boiling_point'] == pytest.approx(self.LOX_NBP_K, rel=0.05)
