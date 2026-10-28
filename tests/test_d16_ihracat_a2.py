# -*- coding: utf-8 -*-
"""ÖH Dalga-16 · kulvar **ihracat** · aşama 2 — bekçiler.

Kapsanan kalemler (parti P09 · bölüm B5 + Z1):

- **P9B5-16** ``/api/import/ork`` fiziksel zarf kapısı (1e9 m gövde →
  684 milyon kg, HTTP 200, ``warnings: []``).
- **P9B5-20** emperyal birimli önbellek kaydı sorgusuz geri dönüyordu.
- **P9B5-21** yedek CEA tablosu termodinamik olarak İMKÂNSIZ üçlü
  taşıyordu (CF sonsuz-genişleme sınırını %32,9 aşıyordu).
- **P9B5-10** ağ TAMAMEN kapalıyken yeşil "NASA CEA Connected" rozeti.
- **P9B5-11** NIST'ten hiçbir şey ayrıştıramayıp ``status: 'success'``.
- **P9B5-12** yedek yoğunluk kapısı (negatif / hâl-kör sayı).
- **P9B5-07** tanınmayan akışkana koşulsuz CoolProp künyesi.
- **P9B5-03** kullanıcı vermemişken ``density_source: 'user input'``
  (taban ölçümünde ZATEN KAPALI — bu dosya GERİLEME kilididir).
- **OH-Z1-02** ``OX_REF_DENSITY`` şablon kopyası + h2o2 görünümü (bekçisi
  ÖH D36'da iki sayfayla birlikte emekli — Berke 23 Eyl, dalga36/sokum).

Her bekçi ters mutasyonla kırmızıya çevrilebildiği ölçülerek yazıldı;
mutasyon defteri ``docs/scofield/raw/OH/D16/ihracat/a2/04_mutasyon.txt``.
"""
import base64
import io
import json
import math
import os
import re
import tempfile
import zipfile

import pytest
import requests

import hrma.data.web_propellant_api as wpa
from hrma.app import app
from hrma.constants import G_0
from hrma.data.database_integrations import DatabaseManager, NistWebBookAPI
from hrma.importers import ork_import

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ===========================================================================
# Ortak yardımcılar
# ===========================================================================
_ORK = """<?xml version="1.0" encoding="UTF-8"?>
<openrocket version="1.5" creator="bekci">
  <rocket><name>B</name><subcomponents><stage><name>S</name>
    <subcomponents>
      <nosecone><name>Nose</name><length>0.15</length><thickness>0.002</thickness>
        <aftradius>0.04</aftradius>
        <material type="bulk" density="1200.0">Cardboard</material></nosecone>
      <bodytube><name>Body</name><length>{L}</length><thickness>0.002</thickness>
        <radius>{R}</radius>
        <material type="bulk" density="1200.0">Cardboard</material></bodytube>
    </subcomponents>
  </stage></subcomponents></rocket>
</openrocket>
"""


def _ork_b64(uzunluk, yaricap):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('rocket.ork', _ORK.format(L=uzunluk, R=yaricap))
    return base64.b64encode(buf.getvalue()).decode('ascii')


@pytest.fixture(scope='module')
def istemci():
    return app.test_client()


def _ork_gonder(istemci, uzunluk, yaricap):
    return istemci.post('/api/import/ork',
                        json={'content_base64': _ork_b64(uzunluk, yaricap),
                              'filename': 'bekci.ork'})


class _AgKapali:
    """``requests.Session.get``i bağlantı hatasına çeviren bağlam."""

    def __enter__(self):
        self._orj = requests.Session.get

        def _yasak(_self, *a, **k):
            raise requests.exceptions.ConnectionError('network disabled (test)')

        requests.Session.get = _yasak
        return self

    def __exit__(self, *exc):
        requests.Session.get = self._orj
        return False


class _AgBosSayfa:
    """HTTP 200 döner ama ayrıştırılabilir hiçbir şey içermez."""

    class _Yanit:
        status_code = 200
        text = '<html><body>not the expected NIST layout</body></html>'

        def raise_for_status(self):
            return None

    def __enter__(self):
        self._orj = requests.Session.get
        requests.Session.get = lambda _self, *a, **k: _AgBosSayfa._Yanit()
        return self

    def __exit__(self, *exc):
        requests.Session.get = self._orj
        return False


# ===========================================================================
# P9B5-16 — .ork fiziksel zarf
# ===========================================================================
class TestP9B516OrkFizikZarfi:
    """1e9 m gövde HTTP 200 + 684 356 690 kg ile geçiyordu."""

    def test_devasa_uzunluk_reddedilir(self, istemci):
        """ÖNCE: 200 · bileşen kütlesi 588.106.144,75 kg · warnings []."""
        yanit = _ork_gonder(istemci, 1e9, 0.04)
        assert yanit.status_code == 400, (
            '1e9 m gövde hâlâ içe aktarılıyor')
        govde = yanit.get_json()
        assert govde['error_code'] == 'unphysical_component_length'
        assert '<length>' in govde['error']
        # Gerekçe SAYIYI ve BANDI söylemeli (beyansız ret yok)
        assert f'{ork_import.ORK_COMPONENT_LENGTH_MAX_M:g} m' in govde['error']

    def test_devasa_yaricap_reddedilir(self, istemci):
        """ÖNCE: 200 · aero.body_diameter = 2.000.000.000 m."""
        yanit = _ork_gonder(istemci, 1.0, 1e9)
        assert yanit.status_code == 400
        govde = yanit.get_json()
        assert govde['error_code'] == 'unphysical_component_radius'
        assert f'{ork_import.ORK_COMPONENT_RADIUS_MAX_M:g} m' in govde['error']

    def test_negatif_yaricap_reddedilir(self, istemci):
        """ÖNCE: 200; kütle sessizce listeden düşüyordu, geometri kalıyordu."""
        yanit = _ork_gonder(istemci, 1.0, -0.04)
        assert yanit.status_code == 400
        assert (yanit.get_json()['error_code']
                == 'unphysical_component_radius')

    def test_hata_metni_dosyanin_kendi_etiketini_suclar(self, istemci):
        """Gövde tüpünde alan ``<radius>``tir; ``<foreradius>`` denemez."""
        govde = _ork_gonder(istemci, 1.0, -0.04).get_json()
        assert '<radius>' in govde['error']
        assert '<foreradius>' not in govde['error']

    def test_saglikli_govde_hala_gecer(self, istemci):
        """Aşırı düzeltme yok: gerçek bir tasarım aynen içe aktarılır."""
        yanit = _ork_gonder(istemci, 1.0, 0.04)
        assert yanit.status_code == 200
        aero = (yanit.get_json().get('rocket') or yanit.get_json())['aero']
        assert aero['body_length'] == pytest.approx(1.15)
        assert aero['body_diameter'] == pytest.approx(0.08)

    def test_bant_kenarlari_kapsayicidir(self, istemci):
        """Zarfın KENDİSİ geçer, bir tık üstü geçmez (kapı bandın adıdır)."""
        L = ork_import.ORK_COMPONENT_LENGTH_MAX_M
        R = ork_import.ORK_COMPONENT_RADIUS_MAX_M
        assert _ork_gonder(istemci, L, 0.04).status_code == 200
        assert _ork_gonder(istemci, L + 0.001, 0.04).status_code == 400
        assert _ork_gonder(istemci, 1.0, R).status_code == 200
        assert _ork_gonder(istemci, 1.0, R + 0.001).status_code == 400

    def test_zarf_gercek_araclari_disarida_birakmaz(self):
        """Bant cömerttir: uçmuş en büyük araçlar bandın İÇİNDE kalmalı."""
        # Starship/Super Heavy ~121 m, Saturn V 110,6 m, N1 105,3 m
        assert ork_import.ORK_COMPONENT_LENGTH_MAX_M > 121.0
        # N1 birinci kademe tabanı 17,0 m çap -> 8,5 m yarıçap
        assert ork_import.ORK_COMPONENT_RADIUS_MAX_M > 8.5


# ===========================================================================
# P9B5-20 — birim sözleşmesi
# ===========================================================================
@pytest.fixture()
def api_yalitilmis(tmp_path):
    api = wpa.WebPropellantAPI()
    api.cache_dir = str(tmp_path / 'cache')
    os.makedirs(api.cache_dir, exist_ok=True)
    return api


class TestP9B520EmperyalOnbellek:
    """Emperyal birimli kayıt aynı anahtarla SI gibi dönüyordu."""

    ANAHTAR = ('cea', 'rp1_lox', {'pc': 100, 'mr': 2.5})

    def _yaz_oku(self, api, govde):
        key = api._get_cache_key(*self.ANAHTAR[:2], self.ANAHTAR[2])
        api._save_cache(key, govde, source_url='local:rocketcea')
        return api._load_cache(key)

    def test_etiketli_emperyal_kayit_reddedilir(self, api_yalitilmis):
        """ÖNCE: c_star = 5934,662 (ft/s) aynen geri dönüyordu."""
        geri = self._yaz_oku(api_yalitilmis, {
            'c_star': 5934.662, 'c_star_units': 'ft/s',
            'chamber_temperature': 6672.677,
            'chamber_temperature_units': 'R', 'status': 'success'})
        assert geri is None, 'ft/s etiketli kayıt hâlâ kabul ediliyor'

    def test_etiketsiz_emperyal_kayit_da_reddedilir(self, api_yalitilmis):
        """Çeviri ÖNCESİ yazılan kayıtlar birim etiketi TAŞIMIYORDU."""
        geri = self._yaz_oku(api_yalitilmis, {
            'c_star': 5934.662, 'chamber_temperature': 6672.677,
            'status': 'success'})
        assert geri is None, (
            'etiketsiz emperyal kayıt fiziksel tavandan geçemez olmalı')

    def test_si_kayit_gecer(self, api_yalitilmis):
        """Aşırı düzeltme yok: doğru birimli kayıt aynen döner."""
        geri = self._yaz_oku(api_yalitilmis, {
            'c_star': 1808.885, 'c_star_units': 'm/s',
            'chamber_temperature': 3707.04,
            'chamber_temperature_units': 'K', 'status': 'success'})
        assert geri is not None
        assert geri['c_star'] == pytest.approx(1808.885)

    def test_sema_surumu_birim_sozlesmesiyle_birlikte_yukseldi(self):
        """Sözleşme değişti; numara da değişmeli (eski kayıtlar düşsün)."""
        assert wpa.CACHE_SCHEMA_VERSION >= 2

    def test_cevrimdisi_depo_da_ayni_kapidan_gecer(self, api_yalitilmis,
                                                   monkeypatch):
        """Disk önbelleğinden reddedilen sayı depodan sızmamalı."""
        monkeypatch.setattr(
            wpa.offline_store, 'get_entry',
            lambda k: {'data': {'c_star': 5934.662, 'c_star_units': 'ft/s'},
                       'age_seconds': 1.0, 'origin': 'test',
                       'timestamp': '2026-09-01T00:00:00'})
        assert api_yalitilmis._load_offline_store('herhangi') is None

    def test_tavanlar_fiziksel_zarftir(self):
        """Tavan kimyasal itici sınırının ÜSTÜNDE, ft/s değerinin ALTINDA."""
        # Bilinen en yüksek kimyasal c* ~2530 m/s (H2/F2)
        assert wpa.CEA_C_STAR_MAX_M_S > 2530.0
        # Aynı değerin ft/s karşılığı takılmalı
        assert 2530.0 / 0.3048 > wpa.CEA_C_STAR_MAX_M_S
        # Bilinen en yüksek alev sıcaklığı ~4700 K
        assert wpa.CEA_CHAMBER_TEMP_MAX_K > 4700.0
        assert 3700.0 * 9.0 / 5.0 > wpa.CEA_CHAMBER_TEMP_MAX_K


# ===========================================================================
# P9B5-21 — yedek CEA tablosu termodinamiği
# ===========================================================================
def _cf_max(gamma):
    g = float(gamma)
    return math.sqrt((2.0 * g * g / (g - 1.0))
                     * (2.0 / (g + 1.0)) ** ((g + 1.0) / (g - 1.0)))


class TestP9B521YedekCeaTablosu:
    """Yedek tablo İMKÂNSIZ üçlü taşıyordu (CF üst sınırı %32,9 aşıyordu)."""

    @pytest.mark.parametrize('cift', [('lh2', 'lox'), ('rp1', 'lox')])
    def test_capa_satiri_termodinamik_olarak_mumkun(self, cift):
        """ÖNCE: lh2/lox CF 2,8042 > CF_max 2,1099 (+%32,9)."""
        satir = wpa._CEA_ANCHOR_TABLE[cift]
        cf = satir['isp_vacuum'] * G_0 / satir['c_star']
        cf_max = _cf_max(satir['gamma'])
        assert cf <= cf_max, (
            f'{cift}: ima edilen CF {cf:.4f} sonsuz-genişleme sınırı '
            f'{cf_max:.4f} üstünde — bu üçlü fiziksel değil')

    @pytest.mark.parametrize('cift', [('lh2', 'lox'), ('rp1', 'lox')])
    def test_uc_yayimlanan_deger_de_kapidan_gecer(self, api_yalitilmis, cift):
        """Kapı tabloda DEĞİL, YAYIMLANAN sözlükte de tutmalı."""
        d = api_yalitilmis._get_fallback_cea_data(*cift)
        assert d['status'] == 'fallback'
        gecti, gerekce = wpa._cea_ucluSu_mumkun_mu(d)
        assert gecti, gerekce

    def test_imkansiz_ucluye_sayi_yayimlanmaz(self, api_yalitilmis,
                                              monkeypatch):
        """Fizik kapısı düşerse sayı GİZLENİR (beyan çözüm değildir)."""
        monkeypatch.setitem(
            wpa._CEA_ANCHOR_TABLE, ('rp1', 'lox'),
            {'isp_vacuum': 353.2, 'isp_sea_level': 311.8, 'c_star': 1520.0,
             'chamber_temperature': 3670.2, 'gamma': 1.2165,
             'molecular_weight': 22.86})
        monkeypatch.setattr(api_yalitilmis, '_cea_cozumu',
                            lambda f, o: (dict(wpa._CEA_ANCHOR_TABLE[(f, o)]),
                                          'test'))
        d = api_yalitilmis._get_fallback_cea_data('rp1', 'lox')
        assert d['status'] == 'not_modelled'
        assert d.get('c_star') is None
        assert d.get('isp_vacuum') is None
        assert 'CF' in d['error']

    def test_bilinmeyen_cift_sayi_uydurmaz(self, api_yalitilmis):
        """ÖNCE: her tanınmayan çift 320 s / 1650 / 3200 / 1,22 / 25 alıyordu."""
        d = api_yalitilmis._get_fallback_cea_data('zirbirzort', 'yokboyle')
        assert d['status'] == 'not_modelled'
        for anahtar in ('isp_vacuum', 'c_star', 'chamber_temperature',
                        'gamma', 'molecular_weight'):
            assert d.get(anahtar) is None, f'{anahtar} hâlâ uyduruluyor'

    def test_capa_kosullari_sonucla_birlikte_yayimlanir(self, api_yalitilmis):
        """Tablo TEK çalışma noktasına demirli; koşulsuz okunamaz."""
        d = api_yalitilmis._get_fallback_cea_data('rp1', 'lox')
        kosul = d['anchor_conditions']
        assert kosul['chamber_pressure_bar'] == 100.0
        assert kosul['mixture_ratio'] == 2.5
        assert d['c_star_units'] == 'm/s'
        assert d['chamber_temperature_units'] == 'K'

    def test_yedek_yol_emperyal_yayimlamaz(self, api_yalitilmis):
        """Yedek yolun sayıları da birim sözleşmesinden geçmeli."""
        d = api_yalitilmis._get_fallback_cea_data('lh2', 'lox')
        assert wpa._birim_sozlesmesi_ihlali(d) is None

    def test_cf_ust_siniri_bilinen_degerle_uyusuyor(self):
        """CF_max(1,20) Sutton Tablo 3-2 ile uyumlu (~2,246)."""
        assert wpa._cf_vakum_ust_siniri(1.20) == pytest.approx(2.2459,
                                                               abs=1e-3)
        with pytest.raises(ValueError):
            wpa._cf_vakum_ust_siniri(1.0)


# ===========================================================================
# P9B5-10 — "NASA CEA Connected" rozeti
# ===========================================================================
class TestP9B510CeaRozeti:
    """Rozet ağ TAMAMEN kapalıyken de yeşil yanıyordu."""

    def test_nasa_cea_sinifinda_ag_cagrisi_yok(self):
        """Ölçüm: AST ile sayılan session.get/post sayısı 0."""
        import ast
        import inspect
        from hrma.data import database_integrations as di
        agac = ast.parse(inspect.getsource(di))
        sayi = None
        for n in agac.body:
            if isinstance(n, ast.ClassDef) and n.name == 'NasaCeaAPI':
                sayi = 0
                for m in ast.walk(n):
                    if (isinstance(m, ast.Call)
                            and isinstance(m.func, ast.Attribute)
                            and m.func.attr in ('get', 'post', 'request')):
                        for taban in ast.walk(m.func.value):
                            if (isinstance(taban, ast.Attribute)
                                    and taban.attr == 'session'):
                                sayi += 1
        assert sayi == 0, (
            'NasaCeaAPI ağ çağrısı kazandıysa durum etiketi de yeniden '
            'düşünülmeli — bu bekçi "yerel tablo" hükmünü kilitliyor')

    def test_agsiz_cea_connected_diyemez(self):
        """ÖNCE: {'status': 'connected', 'message': 'Connected successfully'}."""
        with _AgKapali():
            durum = DatabaseManager().test_connections()
        assert durum['cea']['status'] != 'connected'
        assert durum['cea']['status'] == DatabaseManager.CEA_LOCAL_STATUS
        assert durum['cea']['network_source'] is False

    def test_cea_mesaji_ne_oldugunu_soyler(self):
        with _AgKapali():
            durum = DatabaseManager().test_connections()
        mesaj = durum['cea']['message']
        assert 'no network request' in mesaj
        assert 'Local CEA species table' in mesaj

    def test_uc_yesil_rozet_besleyemez(self, istemci):
        """Rozet ``status === 'connected'`` ile yeşile döner; dönmemeli."""
        with _AgKapali():
            yanit = istemci.get('/api/database-status?refresh=1')
        assert yanit.status_code == 200
        govde = yanit.get_json()
        assert govde['cea']['status'] != 'connected'
        # v3.0.1 K (Berke ek maddesi): NIST kolu bağlantıyı ADIYLA söyler.
        # Ağ kapalıyken eski değer 'error' idi; artık 'not_connected'
        # (bağlanamadı) ve CEA kolunda bağlantı kavramı yok.
        assert govde['nist']['status'] == 'not_connected'
        assert govde['nist']['connection'] == 'not_connected'
        assert govde['cea']['connection'] == 'not_applicable'

    def test_nist_dogru_calisirken_connected_kalir(self):
        """Aşırı düzeltme yok: gerçek ağ kaynağı hâlâ 'connected' diyebilir."""
        from hrma.data import database_integrations as di
        dm = DatabaseManager()
        orj = di.NistWebBookAPI.get_compound_properties
        try:
            di.NistWebBookAPI.get_compound_properties = (
                lambda self, f, t=293.15: {'status': 'success',
                                           'data': {'density': 785.1}})
            durum = dm.test_connections()
        finally:
            di.NistWebBookAPI.get_compound_properties = orj
        assert durum['nist']['status'] == 'connected'
        assert durum['nist']['network_source'] is True


# ===========================================================================
# P9B5-11 — boş ayrıştırma "başarı" değildir
# ===========================================================================
class TestP9B511BosAyristirma:
    """HTTP 200 + ayrıştırılamayan HTML 'success' + data {} dönüyordu."""

    def test_bos_ayristirma_success_diyemez(self):
        with _AgBosSayfa():
            sonuc = NistWebBookAPI().get_compound_properties('N2O', 293.15)
        assert sonuc['status'] == 'error', (
            'boş ayrıştırma hâlâ başarı sayılıyor')
        assert 'no property could be parsed' in sonuc['error']

    def test_kunye_nist_atfi_yapmaz(self):
        """Sayı NIST'ten gelmediyse künye NIST demez."""
        with _AgBosSayfa():
            sonuc = NistWebBookAPI().get_compound_properties('N2O', 293.15)
        assert 'unparsable' in sonuc['source']

    def test_yedek_veri_yine_sunulur(self):
        """Fail-closed ret DEĞİL: dürüst yedek kanalı korunur."""
        with _AgBosSayfa():
            sonuc = NistWebBookAPI().get_compound_properties('N2O', 293.15)
        assert sonuc['data'].get('density') == pytest.approx(785.104, abs=1e-2)
        # ve o sayının kendi künyesi var
        assert 'density_source' in sonuc['data']

    def test_bos_sonuc_rozeti_yesil_yakamaz(self):
        """ÇEVRİLDİ (v3.0.1 K kulvarı — Berke ek maddesi).

        Eski beklenti ``status == 'error'`` idi: sayfa GELDİĞİ hâlde uç
        "hata" yayımlıyor, arayüz bunu "NIST WebBook Offline" diye okuyordu
        (bağlanmış kaynağa "bağlanamadı" demek — beklenti kusuru
        kilitliyordu). Bağlantı ve veri artık ayrı: bağlandı, ama veri
        ayrıştırılmadı ve hesaba sayı vermiyor. P9B5-11'in kazanımı (boş
        ayrıştırma BAŞARI değildir, NIST'e değer atfedilmez) ``data_parsed``
        ile korunur.
        """
        with _AgBosSayfa():
            durum = DatabaseManager().test_connections()
        assert durum['nist']['status'] == 'connected'
        assert durum['nist']['connection'] == 'connected'
        assert durum['nist']['http_status'] == 200
        assert durum['nist']['data_parsed'] is False
        assert durum['nist']['supplies_calculation_data'] is False
        assert 'no value is attributed to NIST' in durum['nist']['message']

    def test_ayristirilabilen_sayfa_hala_success(self):
        """Aşırı düzeltme yok: gerçekten ayrıştırılan sayfa başarıdır."""
        nist = NistWebBookAPI()
        orj = nist._parse_nist_response
        try:
            nist._parse_nist_response = lambda h, t: {'density': 785.1}
            with _AgBosSayfa():
                sonuc = nist.get_compound_properties('N2O', 293.15)
        finally:
            nist._parse_nist_response = orj
        assert sonuc['status'] == 'success'
        assert sonuc['source'] == 'NIST WebBook'


# ===========================================================================
# P9B5-12 — yedek yoğunluk kapısı
# ===========================================================================
class TestP9B512YedekYogunluk:
    """Manşet (negatif ρ, 329 kg/m³ 'sıvı' O2) Z1'de kapandı; kilit + hâl kapısı."""

    @pytest.mark.parametrize('formul,sicaklik', [
        ('O2', 90.19), ('O2', 150.0), ('N2O', 293.15), ('H2O2', 293.15),
        ('N2O4', 280.0)])
    def test_yayimlanan_yogunluk_pozitif(self, formul, sicaklik):
        """GERİLEME KİLİDİ: bu kanal bir daha negatif/sıfır ρ üretemez."""
        d = NistWebBookAPI()._get_fallback_properties(formul, sicaklik)
        rho = d.get('density')
        assert rho is not None and rho > 0, (formul, sicaklik, d)

    @pytest.mark.parametrize('sicaklik', [200.0, 293.15, 375.4, 400.0, 500.0])
    def test_sivi_bandi_disinda_sayi_yayimlanmaz(self, sicaklik):
        """ÖNCE: 293,15 K'de 1141 kg/m³ (gerçeği ~1,31 — 878 kat)."""
        d = NistWebBookAPI()._get_fallback_properties('O2', sicaklik)
        assert d.get('density') is None, (
            f'O2 {sicaklik} K sıvı bandının dışında (T_kritik = 154,58 K) '
            f'ama hâlâ bir yoğunluk yayımlanıyor: {d.get("density")}')
        assert 'OUTSIDE the liquid band' in d['density_error']

    def test_bant_icinde_sayi_yayimlanmaya_devam_eder(self):
        """Aşırı düzeltme yok: LOX NKN'de değer aynen gelir."""
        d = NistWebBookAPI()._get_fallback_properties('O2', 90.19)
        assert d['density'] == pytest.approx(1141.0, abs=1.0)
        assert 'density_source' in d

    def test_tanimayan_formule_jenerik_sayi_yok(self):
        """ÖNCE: bilinmeyen formül 1000 kg/m³ + 0,001 Pa·s alıyordu."""
        d = NistWebBookAPI()._get_fallback_properties('ZZZ', 293.15)
        assert d.get('density') is None
        assert d.get('viscosity') is None
        assert 'no generic substitute is invented' in d['error']


# ===========================================================================
# P9B5-07 — CoolProp künyesi kazanılır
# ===========================================================================
from hrma.data.open_source_propellant_api import (  # noqa: E402
    OpenSourcePropellantAPI)
from hrma.data.propellant_database import propellant_db  # noqa: E402


@pytest.fixture(scope='module')
def os_api():
    return OpenSourcePropellantAPI()


class TestP9B507CoolPropKunyesi:
    """Tanınmayan akışkan bile koşulsuz CoolProp künyesi alıyordu."""

    def test_tanimayan_akiskan_coolprop_kunyesi_almaz(self, os_api):
        """ÖNCE: source = 'CoolProp (NIST REFPROP-based)', density = None."""
        p = os_api.get_coolprop_properties('zirbirzort')
        assert p.get('source') is None, (
            'CoolProp hiçbir sayı üretmediği hâlde künyesini basıyor')
        assert 'resolved no property' in p['coolprop_error']

    def test_coolprop_tanimadigini_adiyla_soyler(self, os_api):
        p = os_api.get_coolprop_properties('htpb')
        assert p.get('source') is None
        assert 'htpb' in p['coolprop_error']

    def test_gercek_akiskanda_kunye_basilir(self, os_api):
        """Aşırı düzeltme yok: CoolProp gerçekten çözerse künye basılır."""
        p = os_api.get_coolprop_properties('lox')
        assert p['source'] == 'CoolProp (NIST REFPROP-based)'
        assert 'density' in p['source_fields']

    def test_kunye_hangi_alanlari_kapsadigini_soyler(self, os_api):
        p = os_api.get_coolprop_properties('n2o')
        assert set(p['source_fields']) <= os_api._COOLPROP_OLCULEN_ALANLAR
        assert p['source_fields'], 'künye var ama kapsadığı alan yok'

    def test_tanimayan_ada_ozellik_seti_verilmez(self, os_api):
        """ÖNCE: 'zirbirzort' için ONBİR alan dolu dönüyordu."""
        u = os_api.get_propellant_for_ui('hybrid_fuel', 'zirbirzort')
        assert u.get('error') == 'unknown_propellant'
        for alan in ('density', 'molecular_weight', 'combustion_temp',
                     'specific_heat', 'thermal_conductivity',
                     'melting_point', 'regression_a', 'regression_n',
                     'data_source'):
            assert alan not in u, f'{alan} hâlâ uyduruluyor'

    def test_pubchem_eslesmesi_taniklik_sayilmaz(self, os_api):
        """PubChem anlamsız ada bile molekül döndürüyor (P9B5-05 ailesi)."""
        props = os_api.get_comprehensive_properties('yok')
        # Ölçüm: PubChem bu ada bir kimlik veriyor...
        assert props.get('molecular_weight') is not None
        # ...ama bu, ürünün onu bir itici saydığı anlamına GELMEZ.
        assert os_api.get_propellant_for_ui('liquid_fuel', 'yok').get(
            'error') == 'unknown_propellant'

    @pytest.mark.parametrize('ad', sorted(propellant_db.database))
    def test_katalogdaki_her_itici_hala_calisir(self, os_api, ad):
        """Kapı yalnız var OLMAYAN maddeyi keser; katalog tam geçer."""
        for tip in ('hybrid_fuel', 'liquid_fuel', 'solid_propellant',
                    'oxidizer'):
            u = os_api.get_propellant_for_ui(tip, ad)
            assert u.get('error') != 'unknown_propellant', (tip, ad)

    @pytest.mark.parametrize('ad', sorted(propellant_db.database))
    def test_uc_katalogdaki_her_itici_icin_200(self, istemci, ad):
        yanit = istemci.post('/api/get-propellant-properties',
                             json={'propellant_type': 'oxidizer',
                                   'propellant_name': ad})
        assert yanit.status_code == 200, (ad, yanit.get_json())

    def test_uc_bilinmeyen_adi_reddeder(self, istemci):
        yanit = istemci.post('/api/get-propellant-properties',
                             json={'propellant_type': 'hybrid_fuel',
                                   'propellant_name': 'ZZZ_NOT_A_PROPELLANT'})
        assert yanit.status_code == 422
        assert yanit.get_json()['error'] == 'unresolved_propellant_name'

    def test_tahmin_tablolari_tek_kaynak(self, os_api):
        """Literal kopyası kalmadı: yardımcılar sınıf sabitlerini okur."""
        import inspect
        for ad in ('_estimate_regression_a', '_estimate_regression_n',
                   '_estimate_burn_rate_a', '_estimate_burn_rate_n',
                   '_estimate_isp'):
            kaynak = inspect.getsource(getattr(OpenSourcePropellantAPI, ad))
            assert 'estimates = {' not in kaynak, (
                f'{ad} hâlâ kendi tablo kopyasını taşıyor')
        # ve değerler değişmedi
        assert os_api._estimate_regression_a('htpb') == 0.0003
        assert os_api._estimate_regression_n('paraffin') == 0.62
        assert os_api._estimate_burn_rate_a('kndx') == 0.008
        assert os_api._estimate_burn_rate_n('knsu') == 0.5
        assert os_api._estimate_isp('apcp') == 265


# ===========================================================================
# P9B5-03 — 'user input' künyesi (taban ölçümünde ZATEN KAPALI)
# ===========================================================================
class TestP9B503KullaniciKunyesi:
    """ÇÜRÜTÜLDÜ (Z1/5e059a0). Bu sınıf GERİLEME kilididir."""

    GOVDE = {'motor_type': 'hybrid', 'thrust': 1000, 'burn_time': 10,
             'chamber_pressure': 20, 'oxidizer_type': 'n2o',
             'fuel_type': 'htpb', 'of_ratio': 6.0}

    def test_app_py_gomulu_yogunluk_varsayilani_tasimaz(self):
        """ÖNCE: ``data.get('oxidizer_density', 1220)`` (app.py:1510)."""
        import ast
        kaynak = open(os.path.join(KOK, 'hrma', 'app.py'),
                      encoding='utf-8').read()
        gomulu = []
        for n in ast.walk(ast.parse(kaynak)):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr == 'get' and len(n.args) == 2
                    and isinstance(n.args[0], ast.Constant)
                    and n.args[0].value == 'oxidizer_density'
                    and isinstance(n.args[1], ast.Constant)):
                gomulu.append((n.lineno, n.args[1].value))
        assert gomulu == [], (
            f'oxidizer_density yine gömülü varsayılanla okunuyor: {gomulu}')

    def test_kullanici_vermeyince_kunye_user_input_demez(self, istemci):
        """ÖNCE: 200 · density_source 'user input' · rho 1220."""
        assert 'oxidizer_density' not in self.GOVDE
        yanit = istemci.post('/calculate', json=dict(self.GOVDE))
        assert yanit.status_code == 200
        kunye = (yanit.get_json().get('injector') or {}).get('density_source')
        assert kunye is not None
        assert kunye != 'user input', (
            'kullanıcı hiçbir sayı vermedi ama künye onu suçluyor')

    def test_kunye_degerin_geldigi_yeri_soyler(self, istemci):
        yanit = istemci.post('/calculate', json=dict(self.GOVDE))
        kunye = (yanit.get_json().get('injector') or {})['density_source']
        assert 'N2O' in kunye or 'n2o' in kunye.lower()

    def test_kullanici_verirse_user_input_kalir(self, istemci):
        """Aşırı düzeltme yok: gerçekten verilen sayı 'user input'tur."""
        govde = dict(self.GOVDE, oxidizer_density=800.0)
        yanit = istemci.post('/calculate', json=govde)
        assert yanit.status_code == 200
        kunye = (yanit.get_json().get('injector') or {})['density_source']
        assert kunye == 'user input'


# ===========================================================================
# OH-Z1-02 — OX_REF_DENSITY şablon kopyası
# ===========================================================================
# TestOHZ102OxRefKopyasi (4 düğüm; _tek_kaynak_ox_ref/_sablon_ox_ref yardımcılarıyla) emekli — sayfa sökümü: Berke 23 Eyl, dalga36/sokum
# (merkezî tablonun h2o2 = %98 değeri ayağı tests/test_z5s_h2o2_etiketi.py::test_a1/test_a2'de yaşar)


class TestP9B507UcKunyesiKatkiyaBagli:
    """Künye düzeltmesi KUSURUN İMZASINA değil KATKIYA bağlı olmalı.

    Eski koşul ``source.startswith('CoolProp')`` idi; yalan künye
    kaynağında kapatılınca düzeltme de sessizce çalışmaz olmuştu
    (ÖLÇÜLDÜ: rp1 -> 'Estimated', n2o4 -> 'PubChem').
    """

    def _uc(self, istemci, ad, tur):
        yanit = istemci.post('/api/get-propellant-properties',
                             json={'propellant_type': tur,
                                   'propellant_name': ad})
        assert yanit.status_code == 200, (ad, yanit.get_json())
        return yanit.get_json()

    @pytest.mark.parametrize('ad,tur', [('rp1', 'liquid_fuel'),
                                        ('htpb', 'hybrid_fuel'),
                                        ('n2o4', 'oxidizer')])
    def test_coolprop_katkisiz_yolda_yerel_kunye_basilir(self, istemci,
                                                         ad, tur):
        govde = self._uc(istemci, ad, tur)
        yerel = propellant_db.get_propellant_properties(ad) or {}
        beklenen = yerel.get('source') or 'Built-in propellant table'
        assert govde['source'] == beklenen, (
            f'{ad}: künye {govde["source"]!r}, yerel tablo kaynağı '
            f'{beklenen!r}')
        assert not re.search(r'pubchem|webbook|nist\.gov',
                             str(govde['source']), re.I)

    @pytest.mark.parametrize('ad', ['n2o', 'lox'])
    def test_coolprop_katkiliysa_yerel_kunyeye_dusmez(self, istemci, ad):
        """Aşırı düzeltme yok: gerçek CoolProp katkısı yerel künyeye ezilmez.

        (n2o'da uç bir adım sonra alan alan künyeye geçiyor —
        'Mixed provenance' — bu da CoolProp katkısını ADIYLA taşıyor.)
        """
        govde = self._uc(istemci, ad, 'oxidizer')
        kunye = str(govde['source'])
        yerel = (propellant_db.get_propellant_properties(ad) or {}).get(
            'source')
        assert kunye != yerel, (
            f'{ad}: CoolProp katkısı var ama künye yerel tabloya düştü')
        alan_kunyeleri = json.dumps(
            (govde.get('properties') or {}).get('property_sources') or {})
        assert 'CoolProp' in kunye or 'CoolProp' in alan_kunyeleri, (
            ad, kunye, alan_kunyeleri[:200])
