# -*- coding: utf-8 -*-
"""ÖH D24 · app-api · aşama-2 bekçileri.

Kapsanan kalemler (kanıt: ``docs/scofield/raw/OH/D24/app-api/a2/``):

* **OH-D23-04** (yüksek) — ``/api/export-stl-zip`` ve ``/api/export-cad``
  birim/işaret kapısı yoktu (500 "geçerli mesh üretilemedi", ``invalid_fields``
  yok / 422 ama alan adsız ve üretimden SONRA).
* **P7B2-18** — ``/api/flight-vehicle``: var olmayan proje 500 (404 dalı ölü
  kod), itki kaynağı çözülemeyen araç 200 'success'.
* **P7B2-10** — ``/api/advanced-analysis``: yapısal kol ``motor_data``sız 164
  sayı yayımlıyordu; tanınmayan analiz türü 200 'success'.
* **P7B2-17** — ``/api/validate-fuel``: doğrulama hatası HTTP 200 ile
  dönüyordu; negatif kütle kesri 200 'success'.
* **P7B2-03** — ``/api/oxidizer-properties`` 'air' bölmesinin faz kapısı yoktu.
* **P7B2-04** — ``/api/altitude-to-pressure`` irtifa kapısı yoktu (1e9 m → 200,
  basınç 0,0 bar); başlıktaki "kendi 2 katmanlı modeli" iddiası ÇÜRÜTÜLDÜ.
* **P7B3-02** — ``/api/generate-complete-package`` ``files_included`` künyesi
  üretilen bölümü değil, istekteki bayrakları sayıyordu.
* **OH-D23-13** — ``injector_design.py`` Türkçe dizeleri İngilizce yanıt
  gövdesinde.

Her sınıf hem KUSURU (ret) hem de KARŞI-TESTİ (sağlıklı gövde hâlâ geçer,
ÖK-22) ölçer.
"""
import json
import math

import pytest

from hrma.app import app


@pytest.fixture()
def istemci():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _post(c, yol, govde):
    r = c.post(yol, json=govde)
    try:
        j = r.get_json()
    except Exception:  # noqa: BLE001
        j = None
    return r.status_code, (j if isinstance(j, dict) else None), r


#: Kanıt dizinindeki ``IYI_GEOMETRI`` ile AYNI gövde (olcum.py).
IYI_GEOMETRI = {
    'motor_name': 'D24_A2',
    'chamber_diameter': 0.1,
    'chamber_length': 0.5,
    'throat_diameter': 0.03,
    'exit_diameter': 0.08,
    'port_diameter': 0.04,
    'chamber_pressure': 20.0,
    'thrust': 5000.0,
    'burn_time': 10.0,
    # ``/api/generate-complete-package`` kendi sözleşmesiyle (.eng üreticisi)
    # bu iki alanı da ister; kapı ÖH D18 / P16B4-21'de kurulmuştur.
    'propellant_mass': 2.5,
    'total_impulse': 50000.0,
}


# ===========================================================================
# OH-D23-04 — ihracat ailesinin iki kapısı bu iki uçta da var
# ===========================================================================
class TestOHD2304IhracatKapiCifti:
    """Aile sözleşmesi: aynı gövde, aynı hüküm — ucun kimliği hüküm vermez."""

    UCLAR = ('/api/export-stl-zip', '/api/export-cad')

    @pytest.mark.parametrize('uc', UCLAR)
    def test_negatif_cap_alan_adiyla_reddedilir(self, istemci, uc):
        """ÖLÇÜLDÜ (taban 88a29d3): ikisi de 500 / alan adsız 422 veriyordu."""
        kod, govde, _ = _post(istemci, uc, {
            'motor_data': dict(IYI_GEOMETRI, chamber_diameter=-0.10)})
        assert kod == 422, (uc, kod, govde)
        alanlar = [x.get('field') for x in (govde or {}).get('invalid_fields', [])]
        assert 'chamber_diameter' in alanlar, (uc, govde)

    @pytest.mark.parametrize('uc', UCLAR)
    def test_negatif_cap_500_ile_YAYIMLANMAZ(self, istemci, uc):
        """500 SUNUCU arızası sınıfıdır; istemcinin negatif çapı öyle değildir."""
        kod, _, _ = _post(istemci, uc, {
            'motor_data': dict(IYI_GEOMETRI, chamber_diameter=-0.10)})
        assert kod != 500, uc

    @pytest.mark.parametrize('uc', UCLAR)
    def test_cozulemeyen_birim_alan_adiyla_reddedilir(self, istemci, uc):
        """``exit_diameter = 3,0`` — m mi mm mi? Kardeş uç 422 diyordu."""
        kod, govde, _ = _post(istemci, uc, {
            'motor_data': dict(IYI_GEOMETRI, exit_diameter=3.0)})
        assert kod == 422, (uc, kod, govde)
        assert (govde or {}).get('status') == 'unresolved_geometry_units', govde
        alanlar = [x.get('field') for x in (govde or {}).get('invalid_fields', [])]
        assert 'exit_diameter' in alanlar, (uc, govde)

    @pytest.mark.parametrize('uc', UCLAR)
    def test_saglikli_govde_hala_uretir(self, istemci, uc):
        """ÖK-22: kapı sağlıklı envanteri daraltmaz."""
        kod, govde, ham = _post(istemci, uc, {
            'motor_data': dict(IYI_GEOMETRI),
            'formats': ['technical_drawings']})
        assert kod == 200, (uc, kod, govde)

    def test_aile_ayni_govdede_ayni_hukmu_verir(self, istemci):
        """Kardeş ``/api/export-complete-zip`` ile hüküm SINIFI aynı olmalı."""
        govde = {'motor_data': dict(IYI_GEOMETRI, chamber_diameter=-0.10)}
        kodlar = {}
        for uc in ('/api/export-stl-zip', '/api/export-cad',
                   '/api/export-complete-zip'):
            kodlar[uc] = _post(istemci, uc, govde)[0]
        assert len(set(kodlar.values())) == 1, kodlar
        assert set(kodlar.values()) == {422}, kodlar

    def test_kapilar_ikinci_kez_YAZILMAZ(self):
        """Doktrin 4: iki uç, kardeşin YARDIMCILARINI çağırır (kopya değil)."""
        import inspect
        from hrma import app as m
        for fn in (m.export_stl_zip, m.export_cad_files):
            kaynak = inspect.getsource(fn)
            assert '_reject_unphysical_export_geometry(' in kaynak, fn
            assert '_reject_unresolved_export_units(' in kaynak, fn


# ===========================================================================
# P7B2-18 — /api/flight-vehicle
# ===========================================================================
class TestP7B218UcanArac:

    def test_var_olmayan_proje_404_alir(self, istemci):
        """ÖLÇÜLDÜ: 500 + "Project 'X' not found" (404 dalı ulaşılamazdı)."""
        kod, govde, _ = _post(istemci, '/api/flight-vehicle', {
            'source': 'project', 'name': 'BOYLE_BIR_PROJE_YOK_D24'})
        assert kod == 404, (kod, govde)

    def test_var_olmayan_proje_500_ILE_yayimlanmaz(self, istemci):
        kod, _, _ = _post(istemci, '/api/flight-vehicle', {
            'source': 'project', 'name': 'BOYLE_BIR_PROJE_YOK_D24'})
        assert kod != 500

    def test_ProjectNotFoundError_FileNotFoundError_DEGIL(self):
        """404 dalının neden ölü olduğunun ölçülmüş kanıtı."""
        from hrma.utils import projects
        assert not issubclass(projects.ProjectNotFoundError, FileNotFoundError)

    @pytest.mark.parametrize('results', [
        {'banana': 1},
        {'motor': {}},
    ])
    def test_itkisiz_arac_success_almaz(self, istemci, results):
        """ÖLÇÜLDÜ: 200 'success' + 7 alanı ``None`` olan bir "araç"."""
        kod, govde, _ = _post(istemci, '/api/flight-vehicle', {
            'source': 'results', 'motor_type': 'hybrid', 'results': results})
        assert kod == 422, (kod, govde)
        assert (govde or {}).get('error') == 'unflyable_vehicle', govde
        assert (govde or {}).get('status') != 'success'

    def test_itki_tasiyan_arac_hala_gecer(self, istemci):
        """ÖK-22: meşru araç (tek sayı olarak itki) reddedilmez."""
        kod, govde, _ = _post(istemci, '/api/flight-vehicle', {
            'source': 'results', 'motor_type': 'hybrid',
            'results': {'motor': {'thrust': 5000.0, 'burn_time': 10.0}}})
        assert kod == 200, (kod, govde)
        assert (govde or {}).get('status') == 'success', govde


# ===========================================================================
# P7B2-10 — /api/advanced-analysis
# ===========================================================================
class TestP7B210GelismisAnaliz:

    def test_yapisal_hukum_varsayilandan_kurulmaz(self, istemci):
        """ÖLÇÜLDÜ: ``{'analysis_types': ['structural']}`` -> 200 + 164 sayı."""
        kod, govde, _ = _post(istemci, '/api/advanced-analysis',
                              {'analysis_types': ['structural']})
        assert kod == 422, (kod, govde)
        assert (govde or {}).get('error') == 'incomplete_structural_input', govde

    def test_yapisal_kol_bos_govdede_SAYI_YAYIMLAMAZ(self, istemci):
        kod, govde, _ = _post(istemci, '/api/advanced-analysis',
                              {'analysis_types': ['structural']})

        def say(n):
            if isinstance(n, bool):
                return 0
            if isinstance(n, (int, float)):
                return 1 if math.isfinite(n) else 0
            if isinstance(n, dict):
                return sum(say(v) for v in n.values())
            if isinstance(n, list):
                return sum(say(v) for v in n)
            return 0

        assert say(govde) == 0, govde

    def test_tek_alan_gelirse_yapisal_kol_hala_kosar(self, istemci):
        """ÖK-22: reddedilen yalnız HİÇBİRİ gönderilmemiş hâl."""
        kod, govde, _ = _post(istemci, '/api/advanced-analysis', {
            'analysis_types': ['structural'],
            'motor_data': {'chamber_pressure': 20.0,
                           'chamber_diameter': 0.1,
                           'chamber_length': 0.5,
                           'throat_diameter': 0.02}})
        assert kod == 200, (kod, govde)
        assert 'structural_analysis' in (govde or {}).get('results', {}), govde

    @pytest.mark.parametrize('turler', [['banana'], [], ['performance']])
    def test_tanimsiz_analiz_turu_success_almaz(self, istemci, turler):
        """ÖLÇÜLDÜ: 'banana' ve boş liste 200 'success' + boş ``results``."""
        kod, govde, _ = _post(istemci, '/api/advanced-analysis',
                              {'analysis_types': turler})
        assert kod == 422, (turler, kod, govde)
        assert (govde or {}).get('status') != 'success', govde

    def test_katalog_kollarla_ortusur(self):
        """Katalog rotanın GERÇEK kollarıyla çaprazlanır (tek kaynak bekçisi)."""
        import inspect
        from hrma import app as m
        kaynak = inspect.getsource(m.advanced_analysis)
        for ad in m.ADVANCED_ANALYSIS_TYPES:
            assert f"'{ad}' in analysis_types" in kaynak, ad


# ===========================================================================
# P7B2-17 — /api/validate-fuel
# ===========================================================================
class TestP7B217YakitDogrulama:

    @pytest.mark.parametrize('comp,beklenen_kod', [
        ([{'formula': 'CH4', 'percentage': 200}], 422),
        ([{'formula': 'CH4', 'percentage': 100},
          {'formula': 'C2H6', 'percentage': 50}], 422),
    ])
    def test_dogrulama_hatasi_200_ile_donmez(self, istemci, comp, beklenen_kod):
        """ÖLÇÜLDÜ: %200 karışım HTTP 200 + status 'error' alıyordu."""
        kod, govde, _ = _post(istemci, '/api/validate-fuel',
                              {'composition': comp})
        assert kod == beklenen_kod, (kod, govde)
        assert (govde or {}).get('status') == 'error', govde

    def test_hata_govdesi_KAYBOLMAZ(self, istemci):
        """Değişen YALNIZ durum kodu; metin aynen durur."""
        _, govde, _ = _post(istemci, '/api/validate-fuel',
                            {'composition': [{'formula': 'CH4',
                                              'percentage': 200}]})
        assert '200' in str((govde or {}).get('error', '')), govde

    def test_negatif_kutle_kesri_reddedilir(self, istemci):
        """ÖLÇÜLDÜ: -10 % + 110 % (toplam 100) -> 200 'success'."""
        kod, govde, _ = _post(istemci, '/api/validate-fuel', {'composition': [
            {'formula': 'CH4', 'percentage': -10},
            {'formula': 'C2H6', 'percentage': 110}]})
        assert kod == 422, (kod, govde)
        gerekceler = [x.get('reason')
                      for x in (govde or {}).get('invalid_fields', [])]
        assert 'must_not_be_negative' in gerekceler, govde

    def test_saglikli_karisim_hala_gecer(self, istemci):
        kod, govde, _ = _post(istemci, '/api/validate-fuel', {
            'composition': [{'formula': 'CH4', 'percentage': 100}]})
        assert kod == 200, (kod, govde)
        assert (govde or {}).get('status') == 'success', govde


# ===========================================================================
# P7B2-03 — /api/oxidizer-properties 'air' bölmesi
# ===========================================================================
class TestP7B203HavaFazKapisi:
    """ÖH D31 / P7B2-03 — ÇEVRİLDİ: 'air' bölmesi SÖKÜLDÜ.

    Bu sınıf D24'te kurulduğunda bölme duruyordu ve oradaki onarım ALT faz
    kapısıydı (78,8 K); ÜST geçerlilik sınırı açık bırakılmış, gerekçesi de
    "deponun beyan ettiği bir üst bant yok, yazmak ÖK-16 ihlali olurdu"
    diye kayda geçmişti.

    D31'de tüketici ölçümü yapıldı (``D31/app-api-uc/a2/once.json`` K5):
    ``air`` bu üründe oksitleyici değildir — ``normalize_oxidizer('air')``
    None, ``OXIDIZER_LIQUID_BAND``da kaydı yok, ``advanced.html`` seçeneği
    ``disabled``, ``/calculate`` 400, ``/api/get-propellant-properties``
    422. Bölmeyi SÖKMEK üst bandı İCAT ETMEDEN kapattı.

    Eski iki bekçi (``test_esik_akiskanin_KENDI_kaydindan_okunur``,
    ``test_referans_durumu_hala_gecer``) artık ÖLÜ KODU ölçüyordu —
    D30 dersi 18 uyarınca sahte yeşil bırakmak yerine yeni sözleşmeye
    çevrildi. Üçüncüsü (``...gaz_yogunlugu_yayimlanmaz``) 400 beklediği
    için yeşil KALIRDI ama GEREKÇESİ değişmişti; o da adıyla yazıldı.
    Yeni sözleşmenin tam kilidi ``tests/test_d31_app_api_uc_a2.py``
    ``TestP7B203HavaBolmesiSokuldu`` sınıfındadır.
    """

    @pytest.mark.parametrize('sicaklik', (50.0, 293.15, 5000.0))
    def test_air_hicbir_sicaklikta_sayi_yayimlamaz(self, istemci, sicaklik):
        """Bölme yok: 78,8 K altı da üstü de AYNI ret."""
        kod, govde, _ = _post(istemci, '/api/oxidizer-properties',
                              {'oxidizer_type': 'air',
                               'temperature': sicaklik})
        assert kod == 400, (sicaklik, kod, govde)
        assert (govde or {}).get('error_code') == 'oxidizer_type_unknown', \
            govde
        assert ((govde or {}).get('properties') or {}).get('density') is None

    def test_olu_ideal_gaz_yardimcisi_kalmadi(self):
        """Doktrin 4 + D30 dersi 18: sökülen bölmenin kodu da gider."""
        from hrma import app as m
        assert not hasattr(m, '_compressed_air_props')

    def test_baslikta_iddia_edilen_zincir_bugun_YOK(self, istemci):
        """P7B2-03 başlığı: h2o2 @ 0 K -> HTTP 500. ÖLÇÜLDÜ: 400, adıyla."""
        kod, govde, _ = _post(istemci, '/api/oxidizer-properties',
                              {'oxidizer_type': 'h2o2', 'temperature': 0})
        assert kod == 400, (kod, govde)
        assert (govde or {}).get('error_code') == 'oxidizer_state_undefined'

    def test_bilinmeyen_oksitleyici_200_almaz(self, istemci):
        """Başlığın ikinci ayağı: bilinmeyen ad -> 200 + status:error."""
        kod, govde, _ = _post(istemci, '/api/oxidizer-properties',
                              {'oxidizer_type': 'kerosene',
                               'temperature': 293.15})
        assert kod == 400, (kod, govde)


# ===========================================================================
# P7B2-04 — /api/altitude-to-pressure
# ===========================================================================
class TestP7B204IrtifaKapisi:

    def test_tablo_disi_irtifada_sayi_yayimlanmaz(self, istemci):
        """ÖLÇÜLDÜ: 1e9 m -> 200, pressure 0,0 bar, temperature 186,946 K."""
        kod, govde, _ = _post(istemci, '/api/altitude-to-pressure',
                              {'altitude': 1e9})
        assert kod == 422, (kod, govde)
        assert (govde or {}).get('error') == 'altitude_outside_model', govde
        assert 'pressure' not in (govde or {}), govde
        assert 'temperature' not in (govde or {}), govde

    def test_tablo_ustunde_rejim_ADIYLA_yazilir(self, istemci):
        """Uzantı, tablo DEĞİLDİR; üretilen sayının kimliği yanıttadır."""
        kod, govde, _ = _post(istemci, '/api/altitude-to-pressure',
                              {'altitude': 100000.0})
        assert kod == 200, (kod, govde)
        assert (govde or {}).get('model_regime') == (
            'isothermal_extension_above_table_top'), govde

    def test_tablo_icinde_govde_BIT_AYNI(self, istemci):
        """ÖK-22: tablo içinde ne rejim alanı eklenir ne davranış değişir."""
        kod, govde, _ = _post(istemci, '/api/altitude-to-pressure',
                              {'altitude': 30000.0})
        assert kod == 200, (kod, govde)
        assert sorted(govde) == ['altitude', 'pressure', 'temperature'], govde

    @pytest.mark.parametrize('h', [0.0, 11000.0, 30000.0, 50000.0, 70000.0])
    def test_USSA1976_TEK_KAYNAKTAN_gelir(self, istemci, h):
        """P7B2-04 başlığı ("70 km'de −%55,51") ÖLÇÜMLE ÇÜRÜTÜLDÜ."""
        from hrma.constants import isa_pressure, isa_temperature
        _, govde, _ = _post(istemci, '/api/altitude-to-pressure',
                            {'altitude': h})
        assert govde['pressure'] == pytest.approx(isa_pressure(h) / 1e5,
                                                  rel=1e-12)
        assert govde['temperature'] == pytest.approx(isa_temperature(h),
                                                     rel=1e-12)


# ===========================================================================
# P7B3-02 — files_included künyesi
# ===========================================================================
class TestP7B302PaketKunyesi:

    @pytest.mark.parametrize('secenekler', [
        None,
        {'technical_drawings': True},
        {'include_cad': True},
    ])
    def test_kunye_URETILENI_sayar(self, istemci, secenekler):
        """ÖLÇÜLDÜ: 5 bölüm üretilirken künye 0 ya da 1 diyordu."""
        govde_istek = {'motor_data': dict(IYI_GEOMETRI)}
        if secenekler is not None:
            govde_istek['package_options'] = secenekler
        kod, govde, _ = _post(istemci, '/api/generate-complete-package',
                              govde_istek)
        assert kod == 200, (kod, govde)
        paket = govde['complete_package']
        kunye = govde['package_info']
        assert kunye['files_included'] == len(paket), (kunye, sorted(paket))
        assert kunye['sections'] == sorted(paket), kunye

    def test_kunye_ISTEKTEKI_bayraklari_saymaz(self, istemci):
        """Rotanın tanımadığı ad gönderildiğinde künye 1 diyordu."""
        kod, govde, _ = _post(istemci, '/api/generate-complete-package', {
            'motor_data': dict(IYI_GEOMETRI),
            'package_options': {'technical_drawings': True}})
        assert kod == 200, (kod, govde)
        assert govde['package_info']['files_included'] != 1, govde['package_info']


# ===========================================================================
# OH-D23-13 — injector_design.py Türkçe dizeleri
# ===========================================================================
class TestOHD2313EnjektorDizeleri:

    #: Yanıt gövdesine giden dizeler İngilizce olur (Doktrin 8: kullanıcıya
    #: dönük API metinleri İngilizce). Adında ``_tr`` taşıyan alanlar
    #: Türkçe olduğunu BEYAN eder ve kapsam dışıdır.
    TR_HARFLER = 'çğıöşüÇĞİÖŞÜ'

    def test_yanit_dizelerinde_turkce_kalmadi(self):
        import ast
        yol = 'hrma/engines/injector_design.py'
        agac = ast.parse(open(yol, encoding='utf-8').read())
        docstringler = set()
        for d in ast.walk(agac):
            if isinstance(d, (ast.Module, ast.FunctionDef,
                              ast.AsyncFunctionDef, ast.ClassDef)):
                if (d.body and isinstance(d.body[0], ast.Expr)
                        and isinstance(d.body[0].value, ast.Constant)
                        and isinstance(d.body[0].value.value, str)):
                    docstringler.add(id(d.body[0].value))
        kalan = [(d.lineno, d.value[:70]) for d in ast.walk(agac)
                 if isinstance(d, ast.Constant) and isinstance(d.value, str)
                 and id(d) not in docstringler
                 and any(ch in d.value for ch in self.TR_HARFLER)]
        # Kalan dizeler YALNIZ ``*_tr`` alanlarının değerleri olabilir.
        #
        # ÖH D25 / app-api a3 — ÇEVRİLDİ (iki gerekçe, ikisi de ölçülü):
        #  1) İzin listesi SATIR NUMARASIYLA yazılmıştı
        #     ({1612, 1613, ...}); dosyaya yukarıdan tek bir satır eklemek
        #     — P16B1-45'te ``DEFAULT_ORIFICE_INLET`` sabitleri eklendi —
        #     aynı iki meşru dizeyi "sızıntı" yapıyordu. Bekçi kodu değil
        #     SATIR SAYISINI kilitliyordu.
        #  2) Sızıntı dalı zaten KOŞULAMAZ hâldeydi:
        #     ``open(yol).splitlines()`` -> AttributeError (``.read()``
        #     unutulmuş). Yani ihlal ANINDA bekçi hata veriyordu, hükmü
        #     değil.
        # Denetim artık AĞAÇTAN yapılır: bir Türkçe dize ancak anahtarı
        # ``_tr`` ile biten bir sözlük değeriyse meşrudur. Bu satır
        # numarasından bağımsızdır ve izin listesinden DAHA DARDIR.
        beyanli = set()
        for d in ast.walk(agac):
            if not isinstance(d, ast.Dict):
                continue
            for anahtar, deger in zip(d.keys, d.values):
                if (isinstance(anahtar, ast.Constant)
                        and isinstance(anahtar.value, str)
                        and anahtar.value.endswith('_tr')):
                    beyanli.add(id(deger))
        sizan_dugumler = [d for d in ast.walk(agac)
                          if isinstance(d, ast.Constant)
                          and isinstance(d.value, str)
                          and id(d) not in docstringler
                          and any(ch in d.value for ch in self.TR_HARFLER)
                          and id(d) not in beyanli]
        assert len(kalan) <= 2, kalan
        assert not sizan_dugumler, [(d.lineno, d.value[:70])
                                    for d in sizan_dugumler]

    def test_cd_kunyesi_ingilizce(self):
        from hrma.engines.injector_design import (CD_TABLE,
                                                  discharge_coefficient)
        for _tip, _lo, _hi, _cd, aciklama in CD_TABLE:
            assert not any(ch in aciklama for ch in self.TR_HARFLER), aciklama
        _cd, gerekce = discharge_coefficient('sharp', 2.0)
        assert not any(ch in gerekce for ch in self.TR_HARFLER), gerekce
        assert 'reattaching' in gerekce, gerekce

    def test_karisik_dilli_hata_govdesi_kalmadi(self):
        """``f"{name}: 'T0_K' is required"`` — ``name`` Türkçeydi."""
        from hrma.engines.injector_design import _require_gas_stream
        with pytest.raises(ValueError) as exc:
            _require_gas_stream({'gas_ox': {'P0_bar': 10.0, 'gamma': 1.2}},
                                'gas_ox', 'oxidiser gas')
        assert not any(ch in str(exc.value) for ch in self.TR_HARFLER), exc.value
