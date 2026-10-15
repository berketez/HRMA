# -*- coding: utf-8 -*-
"""ÖH Dalga-30 · kulvar ``app-api-uc`` · aşama 1/3 — uç ailesi bekçisi.

Her sınıf TEK bir defter kalemine bağlıdır ve o kalemin ÖLÇÜLEN kusurunu
görür. Ölçümler ``docs/scofield/raw/OH/D30/app-api-uc/a1/once.json`` ve
``sonra.json``; ters-mutasyon kanıtı ``mutasyon.json``.

Kapsanan kalemler:
  P16B1-33  cidarın 0 hâli "hiç vermediniz" diye sınıflanıyordu
  P16B1-42  reddedilen cidarın DEĞERİ künyeden düşüyordu
  OH-D28-11 FORM_LIMITS tablosu veri güdümlü değildi (kanal var kapı yok)
  OH-D29-01 /analyze_safety oxidizer_type alanını kabul etmiyordu
  OH-D28-13 enjektör plakası ΔP'si sessizce ham isteğe düşüyordu
  P7B4-14   üç 501 saplaması successor'ı iki farklı tipte yayımlıyordu
  OH-D29-13 /api/analysis/thermal-protection ölü takma yolu (= P7B1-22)
  P16B1-38  chamber_length_override sessiz kelepçesi (ÇÜRÜTÜLDÜ — kilit)
  OH-D28-09 /calculate 400 gövdesi makine-okur değil (ÇÜRÜTÜLDÜ — kilit)
  OH-D29-08 fin_count 1e6 -> 503 duvar saati (ÇÜRÜTÜLDÜ — kilit)
  P7B2-23   slosh büyüklük ekseni (KISMEN — ölçüm kilidi)

ÖH D33-3 / kulvar ``bekci-cevirisi`` — BU DOSYADA İKİ BEKÇİ ÇEVRİLDİ:
  OH-D33-18  ``TestOHD2813DeltaPKaynagi`` SALT METİNDEN DAVRANIŞA
             (2 metin testi -> 0; ürünü çalıştıran test 0 -> 4)
  OH-D33-19  ``test_ohd2908_fin_count_butceye_carpmiyor`` kusuru koruyan
             ``status_code == 200`` kilidi söküldü; iddia SÜRE/BÜTÇE
             ekseninde kaldı
Ölçüm ``docs/scofield/raw/OH/D33-3/bekci-cevirisi/a1/once.json`` ⟷
``sonra.json``; ters-mutasyon ``mutasyon.json`` (M1-M4).
"""
import ast
import contextlib
import io
import subprocess
import time
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
APP_PY = KOK / 'hrma' / 'app.py'


@pytest.fixture(scope='module')
def istemci():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


YAPISAL = {'chamber_pressure': 50, 'chamber_diameter': 0.15,
           'chamber_length': 0.6, 'throat_diameter': 0.04,
           'chamber_temperature': 3000, 'material': 'steel_4130',
           'safety_factor': 2.0}


def _tabani(govde):
    """``design_basis`` bloğunu döndürür (uç onu üst düzeyde yayımlıyor)."""
    if isinstance(govde.get('design_basis'), dict):
        return govde['design_basis']
    ic = govde.get('structural_analysis')
    if isinstance(ic, dict) and isinstance(ic.get('design_basis'), dict):
        return ic['design_basis']
    return {}


# ===========================================================================
# P16B1-33 — 0 SENTİNELİ "hiç vermediniz" DEĞİLDİR
# ===========================================================================
class TestP16B133SentinelKunyesi:
    """ÖLÇÜLDÜ (``a1/once.json`` K1, taban ``ab7cf68b``):
    ``wall_thickness = 0`` gönderen istek
    ``wall_thickness_input_status = 'not_supplied'`` +
    ``submitted_wall_thickness_mm = null`` + *"No wall thickness was
    supplied"* künyesini alıyordu. Alan GELMİŞTİ; ürün onu yok saymakla
    kalmayıp kullanıcıya "vermediniz" diyordu.

    Sentinel SÖZLEŞMESİ (0 = "cidarı sen boyutlandır") KORUNUR — panel
    varsayılanı odur; değişen tek şey künyenin doğruyu söylemesidir.
    """

    def test_sifir_kendi_durumunu_tasir(self, istemci):
        g = istemci.post('/analyze_structural_safety',
                         json=dict(YAPISAL, wall_thickness=0)).get_json()
        db = _tabani(g)
        assert db['wall_thickness_input_status'] == 'sizing_sentinel'
        assert 'No wall thickness was supplied' not in db['message']
        assert 'size the wall for me' in db['message']

    def test_sentinel_boyutlandirma_sozlesmesi_korunur(self, istemci):
        """Kusur giderildi diye ürünün en sık koştuğu yol DEĞİŞMEZ."""
        g = istemci.post('/analyze_structural_safety',
                         json=dict(YAPISAL, wall_thickness=0)).get_json()
        db = _tabani(g)
        assert db['wall_thickness_source'] == 'sized_by_hrma'
        assert db['is_verification'] is False

    def test_alan_hic_gelmediginde_ayri_cumle(self, istemci):
        """İki hâl AYNI cümleye düşerse kusur geri gelmiş demektir."""
        g = istemci.post('/analyze_structural_safety',
                         json=dict(YAPISAL)).get_json()
        db = _tabani(g)
        assert db['wall_thickness_input_status'] == 'not_supplied'
        assert 'No wall thickness was supplied' in db['message']


# ===========================================================================
# P16B1-42 — "NE GÖNDERDİĞİNİZ" KÜNYEDEN DÜŞMEZ
# ===========================================================================
class TestP16B142GonderilenDeger:
    """ÖLÇÜLDÜ (``a1/once.json`` K1): ``wall_thickness = -5``
    ``user_value_not_applied`` + ``not_positive`` künyesi alıyor (hüküm
    doğru geri çekiliyor) ama ``submitted_wall_thickness_mm = null``
    oluyordu — mesaj "gönderdiğiniz cidar değerlendirilen değildi" derken
    hangisi olduğunu söylemiyordu.
    """

    def test_negatif_deger_kunyeden_dusmez(self, istemci):
        g = istemci.post('/analyze_structural_safety',
                         json=dict(YAPISAL, wall_thickness=-5)).get_json()
        db = _tabani(g)
        assert db['wall_thickness_source'] == 'user_value_not_applied'
        assert db['submitted_wall_thickness_mm'] == pytest.approx(-5000.0)

    def test_sifir_da_yankilanir(self, istemci):
        g = istemci.post('/analyze_structural_safety',
                         json=dict(YAPISAL, wall_thickness=0)).get_json()
        assert _tabani(g)['submitted_wall_thickness_mm'] == pytest.approx(0.0)


# ===========================================================================
# OH-D28-11 — FORM_LIMITS KAPISI TABLOYU GEZER
# ===========================================================================
class TestOHD2811GeziciBandKapisi:
    """ÖLÇÜLDÜ (``a1/once.json`` K3, AST): tabloda 15 satır, uçlarda 14 açık
    ``_form_band_kapisi`` çağrısı, KAPALI satır 12. Üç satır kapısızdı ve
    ``quick_geometry.chamber_temperature``ın bandı ayrıca ELLE ikinci kez
    yazılıydı. Tabloya satır eklemek kapıyı kapatmıyordu.
    """

    @staticmethod
    def _kapisiz_satirlar():
        from hrma.validation.motor_validation import FORM_LIMITS
        agac = ast.parse(APP_PY.read_text(encoding='utf-8'))
        acik, gezilen = set(), set()
        for d in ast.walk(agac):
            if not isinstance(d, ast.Call) or not isinstance(d.func, ast.Name):
                continue
            if (d.func.id == '_form_band_kapisi' and len(d.args) >= 3
                    and isinstance(d.args[1], ast.Constant)
                    and isinstance(d.args[2], ast.Constant)):
                acik.add((d.args[1].value, d.args[2].value))
            if (d.func.id == '_form_band_tablosunu_gez' and len(d.args) >= 2
                    and isinstance(d.args[1], ast.Constant)):
                gezilen.add(d.args[1].value)
        tum = {(f, a) for f, alanlar in FORM_LIMITS.items() for a in alanlar}
        return {t for t in tum if t not in acik and t[0] not in gezilen}

    def test_uc_kapisiz_satir_kapandi(self):
        kalan = self._kapisiz_satirlar()
        for beklenen in (('quick_geometry', 'chamber_temperature'),
                         ('solid', 'burn_rate_a'), ('solid', 'burn_rate_n')):
            assert beklenen not in kalan, beklenen

    def test_elle_yazili_ikinci_bant_soktu(self):
        """300/6000 ikinci kez app.py'de YAZILI kalmamalı (tek kaynak)."""
        metin = APP_PY.read_text(encoding='utf-8')
        assert 'validate_input_range(data[\'chamber_temperature\'], 300, 6000' \
            not in metin

    def test_tabloya_satir_eklemek_kapiyi_kapatir(self, istemci):
        """Gezici kapının DAVRANIŞ kanıtı: tablodaki bant uçta uygulanıyor."""
        r = istemci.post('/api/quick-geometry', json={
            'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
            'chamber_pressure': 30, 'chamber_temperature': 99999})
        assert r.status_code == 400, r.status_code

    def test_burn_rate_bandi_artik_uygulaniyor(self, istemci):
        r = istemci.post('/calculate_solid', json={
            'chamber_diameter': 100.0, 'grain_length': 300.0,
            'core_diameter': 30.0, 'propellant_type': 'apcp',
            'burn_time': 5, 'chamber_pressure': 50, 'burn_rate_a': 99.0})
        assert r.status_code == 400, r.status_code
        g = r.get_json()
        assert any(x.get('field') == 'burn_rate_a'
                   for x in (g.get('invalid_fields') or []))


# ===========================================================================
# OH-D29-01 — /analyze_safety OKSİTLEYİCİYİ OKUR
# ===========================================================================
SAFETY = {'chamber_pressure': 50, 'propellant_mass': 5,
          'chamber_diameter': 0.15, 'wall_thickness': 0.005,
          'motor_type': 'hybrid'}


def _patlayici(govde):
    sa = govde.get('safety_analysis')
    if isinstance(sa, dict) and isinstance(sa.get('explosive_hazards'), dict):
        return sa['explosive_hazards']
    return govde.get('explosive_hazards') or {}


class TestOHD2901OksitleyiciAlani:
    """ÖLÇÜLDÜ (``a1/once.json`` K4): ``oxidizer_type='h2o2'`` gönderen
    hibrit istek sınıf ``composite`` / TNT **2,100 kg** alıyordu; AYNI motor
    ``propellant_type='h2o2_htpb'`` yazılınca ``hybrid_h2o2`` / TNT
    **3,446 kg**. Peroksit hibriti (689/446 = 1,55x daha enerjik) ancak adı
    YAKIT alanına yazılırsa kendi güvenlik hükmünü alıyordu.
    """

    def test_oksitleyici_sinifi_belirler(self, istemci):
        g = istemci.post('/analyze_safety',
                         json=dict(SAFETY, oxidizer_type='h2o2')).get_json()
        exp = _patlayici(g)
        assert exp['explosive_class'] == 'hybrid_h2o2'
        assert 'oxidizer_type' in exp['explosive_class_basis']

    def test_iki_yol_ayni_hukmu_verir(self, istemci):
        """Alanı yazmak ile yakıt metnine gömmek AYNI sınıfa götürmeli."""
        a = _patlayici(istemci.post(
            '/analyze_safety',
            json=dict(SAFETY, oxidizer_type='h2o2')).get_json())
        b = _patlayici(istemci.post(
            '/analyze_safety',
            json=dict(SAFETY, propellant_type='h2o2_htpb')).get_json())
        assert a['explosive_class'] == b['explosive_class']
        assert a['tnt_equivalent_kg'] == pytest.approx(b['tnt_equivalent_kg'])

    def test_cozulemeyen_oksitleyici_sayi_uydurmaz(self, istemci):
        """ÖH D33-3 / OH-D33-30 — BU BEKÇİ ÇEVRİLDİ (kusuru koruyordu).

        Eski hâli ``oxidizer_type='peynir'`` isteğinde ``explosive_class``ın
        ``hybrid_`` ile başlamasını ve künyede ``ASSUMPTION`` geçmesini
        şart koşuyordu — yani adı BEYAN EDİLMİŞ bir uydurmayı sözleşme
        sayıyordu. Bekçinin kendi adı ("sayı uydurmaz") ile ölçtüğü
        davranış çelişiyordu: ÖLÇÜLDÜ (``docs/scofield/raw/OH/D33-3/
        app-api-kapilar/a1/once.json`` K1, taban ``fa7c4e1d``) — istek
        HTTP 200 + ``hybrid_n2o`` + **22,2775 kg TNT** alıyordu ve o sayı
        tahliye mesafelerini belirliyordu; kardeş uç
        ``/api/oxidizer-properties`` AYNI değere 400
        ``oxidizer_type_unknown`` diyordu.

        Doktrin 1 (beyan çözüm değildir) ve Berke kararı (16 Eyl 2026:
        "kanon TEK olmalı, yön ADIYLA 400") uyarınca sözleşme artık
        fail-closed'dır. Kalemin asıl derdi ("çözülemeyen ad için sayı
        üretme") KORUNUYOR, ölçütü sertleşti.
        """
        r = istemci.post('/analyze_safety',
                         json=dict(SAFETY, oxidizer_type='peynir'))
        g = r.get_json()
        assert r.status_code == 400, r.status_code
        assert g['error_code'] == 'oxidizer_type_unknown', g
        assert g['field'] == 'oxidizer_type', g
        assert 'safety_analysis' not in g, 'reddedilen istekte hüküm var'

    def test_varsayilan_kumesi_buyumedi(self, istemci):
        """Alan eklendi ama VARSAYILAN eklenmedi (panel bekçisi korunur)."""
        g = istemci.post('/analyze_safety', json=dict(SAFETY)).get_json()
        assert 'oxidizer_type' not in (g.get('defaults_applied') or [])


# ===========================================================================
# OH-D28-13 — ΔP KAYNAĞI BEYAN EDİLİR
# ===========================================================================
class TestOHD2813DeltaPKaynagi:
    """ÖLÇÜLDÜ (``a1/once.json`` K7): ``if not dp: dp = data.get(
    'pressure_drop')`` — yayımlanan ΔP 0/None olduğunda hüküm HAM İSTEK
    alanına düşüyor ve bunu HİÇBİR yerde söylemiyordu.

    ÖH D33-3 / OH-D33-19'un kardeşi OH-D33-18 — **BU SINIF ÇEVRİLDİ.**
    Eski hâli iki testten ibaretti ve ikisi de ``hrma/app.py`` KAYNAK
    METNİNDE dize arıyordu (``"report['delta_P_source'] = dp_kaynak" in
    metin``); tek bir istek atmıyordu. ÖLÇÜLDÜ (``docs/scofield/raw/OH/
    D33-3/bekci-cevirisi/a1/once.json`` K1, taban ``fa7c4e1d``):
    sınıfın 2 testinin 2'si salt metin, 0'ı davranış; ``delta_P_source``
    adı ``tests/`` ağacının TAMAMINDA 1 kez geçiyordu — o da bu dize
    karşılaştırmasıydı. Yani kusurun asıl dalı (çözücü ΔP üretmedi,
    kullanıcının kendi sayısı hükme girdi) hiçbir davranış bekçisiyle
    örtülü değildi: satır yeniden düzenlense (ör. ``dp_kaynak`` başka bir
    yardımcıya taşınsa) bekçi kırmızı verir, davranış bozulsa ama dize
    yerinde kalsa bekçi YEŞİL kalırdı.

    Yeni hâl üç dalı da ÇALIŞTIRARAK ölçer (ölçüm ``once.json``
    ``K1_OH_D33_18_davranis``):

    * ``injector_solution`` — ``/calculate`` ucundan gerçek istekle
      (ölçüldü: ΔP 7,0 bar, kaynak ``injector_solution``);
    * ``request_echo``      — çözücü ΔP yayımlamadığında
      (ölçüldü: ΔP 7,0 bar, ``is_verification=False``);
    * ``unavailable``       — ne çözücüde ne istekte ΔP olduğunda
      (ölçüldü: ΔP ``None``, hüküm kurulmaz).

    ARTAKALAN — FALSY TUZAĞI (ADIYLA BEYAN, bu kulvarda ONARILMADI):
    ``hrma/app.py:661`` ``dp_kaynak = 'injector_solution' if dp else None``
    ve ``:662`` ``if not dp:`` ΔP'yi DOĞRULUK değeriyle sınar. Çözücü ΔP'yi
    TAM ``0.0`` yayımlarsa (fizikte "basınç farkı yok" demektir, "değer
    yok" değil) hüküm istek yankısına düşer ve künye "The injector
    solution published no pressure drop" der — oysa yayımlamıştır.
    ÖLÇÜLDÜ (``once.json`` ``K1...davranis.falsy_tuzagi_dp_tam_sifir``):
    ``injector_results={'pressure_drop': 0.0}`` + ``data={'pressure_drop':
    7.0}`` -> ``delta_P_source='request_echo'``, ``delta_P_bar=7.0``.
    Onarım ``hrma/app.py`` sahasının (``app-api-kapilar`` kulvarı) işidir;
    bu kulvarın sahası ``tests/**``tir. Bekçisi de orada kurulmalıdır —
    burada kusuru DONDURAN bir test yazılmadı (bkz. Doktrin 1).
    """

    #: ``/calculate`` ucunu enjektör plakası hükmüne kadar götüren en küçük
    #: gövde (ölçüldü: HTTP 200, ``injector.plate_structural`` yayımlanır).
    PLAKA_YUKU = {
        'motor_type': 'hybrid', 'thrust': 5000, 'burn_time': 10,
        'chamber_pressure': 20, 'tank_pressure': 50, 'of_ratio': 2.5,
        'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
        'oxidizer_phase': 'liquid', 'oxidizer_density': 1220,
        'injector_type': 'showerhead', 'plate_thickness': 3.0,
        'injector_material': 'stainless_steel', 'safety_factor': 4.0,
        'chamber_material': 'steel_4130', 'wall_thickness': 5,
        'chamber_temperature': 3000, 'include_plots': False,
        'pressure_drop': 7.0,
    }

    @staticmethod
    def _plaka(istemci, **ek):
        g = istemci.post('/calculate',
                         json=dict(TestOHD2813DeltaPKaynagi.PLAKA_YUKU,
                                   **ek)).get_json() or {}
        return (g.get('injector') or {}), ((g.get('injector') or {})
                                           .get('plate_structural') or {})

    @staticmethod
    def _rapor(**ek):
        """``_injector_plate_report``i DOĞRUDAN koşar (dal seçimi ölçülür).

        Uç, çözücünün ΔP'sini her zaman pozitif yayımladığı için
        ``request_echo``/``unavailable`` dalları HTTP yüzeyinden bugün
        erişilemez (ölçüldü: ``once.json`` K1 — ``injector_solution``,
        7,0 bar). Dalın kendisi CANLIdır ve sözleşmesi burada ölçülür;
        dize karşılaştırmasıyla değil, çalıştırarak.
        """
        with contextlib.redirect_stdout(io.StringIO()):
            from hrma.app import _injector_plate_report
            return _injector_plate_report(
                'stainless_steel',
                dict({'safety_factor': 4.0}, **ek.pop('istek', {})),
                {'chamber_diameter': 0.15},
                dict({'plate_thickness': 3.0, 'n_holes': 11,
                      'hole_diameter': 2.45}, **ek.pop('cozucu', {})))

    def test_uc_hangi_DP_ile_hukum_kurdugunu_yayimlar(self, istemci):
        """Çözücü dalı: kaynak ADIYLA yayımlanır ve DEĞERLE tutarlıdır."""
        inj, plaka = self._plaka(istemci)
        assert plaka, 'plate_structural yayımlanmadı'
        assert plaka['delta_P_source'] == 'injector_solution', plaka
        assert plaka['delta_P_bar'] == pytest.approx(inj['pressure_drop']), (
            'plaka hükmü enjektör çözümünün ΔP\'sinden BAŞKA bir sayıyla '
            'kurulmuş: %r vs %r' % (plaka['delta_P_bar'],
                                    inj.get('pressure_drop')))

    def test_istek_yankisi_dali_dogrulama_sayilmaz(self):
        """Çözücü ΔP üretmediyse hüküm 'doğrulama' DEĞİLDİR ve bunu söyler."""
        r = self._rapor(istek={'pressure_drop': 7.0},
                        cozucu={'plate_thickness': 3.0})
        assert r['delta_P_source'] == 'request_echo', r
        assert r['delta_P_bar'] == pytest.approx(7.0), r
        assert r['is_verification'] is False, (
            'istek yankısı DOĞRULAMA sayılıyor: %r' % r.get('is_verification'))
        assert 'not a verification' in r['delta_P_basis'], r['delta_P_basis']

    def test_hicbir_kaynak_yoksa_hukum_kurulmaz(self):
        """Ne çözücüde ne istekte ΔP varsa sayı UYDURULMAZ (fail-closed)."""
        r = self._rapor(cozucu={'plate_thickness': 3.0})
        assert r['delta_P_source'] == 'unavailable', r
        assert r['delta_P_bar'] is None, r
        assert 'unknown load' in r['delta_P_basis'], r['delta_P_basis']

    def test_kaynak_adi_uc_sozlesmesinde_makine_okur(self, istemci):
        """Alan İSİMDİR: üç değerden biri, serbest metin değil."""
        _inj, plaka = self._plaka(istemci)
        assert plaka['delta_P_source'] in (
            'injector_solution', 'request_echo', 'unavailable'), plaka


# ===========================================================================
# P7B4-14 — 501 SAPLAMALARI TEK TİP
# ===========================================================================
SAPLAMALAR = ('/api/cfd-analysis', '/api/kinetic-analysis',
              '/api/professional-analysis')


class TestP7B414SuccessorTekTip:
    """ÖLÇÜLDÜ (``a1/once.json`` K11): ``successor`` iki uçta ``str``, birinde
    ``list``; listenin üçüncü öğesi yol DEĞİL serbest metindi
    (``'Analysis Deck panels (...)'``). İstemci tek bir okuma yazamıyordu.
    """

    @pytest.mark.parametrize('yol', SAPLAMALAR)
    def test_successor_hep_liste(self, istemci, yol):
        g = istemci.post(yol, json={}).get_json()
        assert isinstance(g['successor'], list), yol

    @pytest.mark.parametrize('yol', SAPLAMALAR)
    def test_her_oge_bir_uc_yolu(self, istemci, yol):
        g = istemci.post(yol, json={}).get_json()
        assert g['successor'], yol
        for oge in g['successor']:
            assert isinstance(oge, str) and oge.startswith('/api/'), oge

    def test_yol_olmayan_yonlendirme_ayri_alanda(self, istemci):
        g = istemci.post('/api/professional-analysis', json={}).get_json()
        assert 'Analysis Deck panels' in ' '.join(g['successor_notes'])


# ===========================================================================
# OH-D29-13 (= P7B1-22) — ÖLÜ TAKMA YOL SİLİNDİ
# ===========================================================================
class TestOHD2913TakmaYolSilindi:
    """ÖLÇÜLDÜ (``a1/once.json`` K9): takma yol kayıtlıydı, ürün tarafında
    (``hrma/static``, ``hrma/templates``) SIFIR eşleşme vardı; tüketicileri
    yalnız deponun kendi test envanteriydi. İKİNCİ YOLLA DOĞRULANDI:
    ``/api/analysis/`` ön eki hiçbir yerde dinamik olarak kurulmuyor
    (``'/api/analysis/' +``, şablon dizgesi: 0 eşleşme), yani yol dolaylı
    da çağrılmıyordu. D24 gerekçesinin andığı ``thermal_panel.js`` bu ucu
    değil ``/api/analysis/wall-profile``ı çağırıyor.
    """

    def test_takma_yol_404(self, istemci):
        r = istemci.post('/api/analysis/thermal-protection',
                         json={'mode': 'ablative', 'q_net_W_m2': 1e6,
                               'burn_time_s': 10,
                               'material': 'carbon_phenolic',
                               'q_star_MJ_kg': 5.0})
        assert r.status_code == 404, r.status_code

    def test_birincil_yol_yasiyor(self, istemci):
        r = istemci.post('/api/thermal-protection',
                         json={'mode': 'ablative', 'q_net_W_m2': 1e6,
                               'burn_time_s': 10,
                               'material': 'carbon_phenolic',
                               'q_star_MJ_kg': 5.0})
        assert r.status_code == 200, r.status_code

    def test_envanterde_takma_yol_kalmadi(self):
        for ad in ('tests/support/uc_katalogu.py',
                   'tests/support/uc_yukleri.json'):
            metin = (KOK / ad).read_text(encoding='utf-8')
            assert "'/api/analysis/thermal-protection':" not in metin
            assert '"/api/analysis/thermal-protection":' not in metin

    def test_dinamik_yol_kurulumu_yok(self):
        """Silmenin ikinci-yol kanıtı bekçiye bağlanır."""
        out = subprocess.run(
            ['git', 'grep', '-n', '/api/analysis/', '--',
             'hrma/static', 'hrma/templates'],
            cwd=str(KOK), capture_output=True, text=True).stdout
        for satir in out.splitlines():
            # Yalnız YOL kullanımı sayılır; künye metninde ucun adının
            # geçmesi çağrı değildir (``stability_panel.js`` ikizinden söz
            # ediyor). Aranan şey somut yolun kendisidir.
            assert '/api/analysis/thermal-protection' not in satir, satir


# ===========================================================================
# ÇÜRÜTME KİLİTLERİ — kalem başlığı ölçümle çürütüldü, ölçüm dondurulur
# ===========================================================================
class TestCurutmeKilitleri:
    """Üç kalem başlığı bu tabanda ARTIK GEÇERLİ DEĞİL. Kilit, kusurun
    sessizce geri dönmesini engeller (çürütme = "yok" değil, "ölçüldü ve
    yok"); ölçümler ``a1/once.json`` K2 / K6 / K8.
    """

    def test_p16b138_kelepce_yok(self, istemci):
        """K2: 500000 mm ezme SESSİZCE kırpılmıyor, adıyla reddediliyor."""
        r = istemci.post('/calculate', json={
            'motor_type': 'hybrid', 'chamber_pressure': 30, 'thrust': 5000,
            'burn_time': 10, 'of_ratio': 6.0, 'oxidizer_type': 'n2o',
            'fuel_type': 'htpb', 'chamber_length_override': 500000})
        assert r.status_code == 400
        g = r.get_json()
        alanlar = {x.get('field') for x in (g.get('invalid_fields') or [])}
        assert 'chamber_length_override' in alanlar

    def test_ohd2809_400_makine_okur(self, istemci):
        """K6: /calculate 400 gövdesi alan adını YAPILI alanda taşıyor."""
        r = istemci.post('/calculate', json={
            'motor_type': 'hybrid', 'chamber_pressure': 30, 'thrust': 5000,
            'burn_time': 10, 'of_ratio': 'abc', 'oxidizer_type': 'n2o',
            'fuel_type': 'htpb'})
        assert r.status_code == 400
        kayit = (r.get_json().get('invalid_fields') or [{}])[0]
        assert kayit.get('field') == 'of_ratio'
        assert kayit.get('reason')

    #: OH-D29-08'in ÇÜRÜTÜLEN iddiasının yükü (ÖH D30 K8).
    FIN_YUKU = {'dry_mass': 30, 'propellant_mass': 20, 'thrust': 5000,
                'burn_time': 5, 'body_diameter': 0.15, 'body_length': 2.0,
                'nose_length': 0.4, 'fin_span': 0.15, 'fin_root_chord': 0.2,
                'fin_tip_chord': 0.1, 'cd0': 0.5, 'fin_count': 1000000}

    def test_ohd2908_fin_count_butceye_carpmiyor(self, istemci):
        """K8 ÇEVRİLDİ (ÖH D33-3 / OH-D33-19) — iddia SÜRE/BÜTÇE eksenindedir.

        ÇÜRÜTÜLEN İDDİA: "``fin_count = 1e6`` 60 saniyelik duvar saati
        bütçesine çarpar ve uç 503 verir." Ölçüm bunu yalanladı (D30 K8:
        0,09 s / HTTP 200) ve kalem kilitlendi.

        BEKÇİ KUSURU (ÖLÇÜLDÜ, ``docs/scofield/raw/OH/D33-3/bekci-cevirisi/
        a1/once.json`` K2, taban ``fa7c4e1d``): testin iki iddiasından biri
        ``r.status_code == 200`` idi. Bu, ÇÜRÜTÜLEN iddianın ekseni DEĞİL;
        "saçma kanat sayısı (1e6) KABUL EDİLİR" hükmünü donduruyordu. Aynı
        ölçümde ``fin_count=4`` 47.402 B, ``fin_count=1e6`` 47.401 B yanıt
        verir — yani sayı yanıtı fiilen hiç oynatmaz. Gün gelip bu uca bir
        ``fin_count`` sağduyu kapısı (adlı 4xx) eklendiğinde bu bekçi HAKSIZ
        kırmızı verecek ve DOĞRU onarımı engelleyecekti; D33'ün "kusuru
        koruyan bekçi" dersinin tam örneği.

        Çevrilen ölçüt: bütçe ekseni KORUNUR (duvar saati + sunucu tarafı
        çöküş/zaman aşımı yasak), durum kodu DONDURULMAZ. Adlı bir kapı
        eklenirse bekçi yeşil kalır — ama kapı ADSIZ olamaz: 4xx dönen bir
        yanıt reddin alanını söylemek zorundadır (fail-closed).
        """
        t0 = time.monotonic()
        r = istemci.post('/api/six-dof-analysis', json=dict(self.FIN_YUKU))
        gecen = time.monotonic() - t0
        assert gecen < 30.0, gecen
        assert r.status_code not in (500, 502, 503, 504), (
            'çürütülen iddia geri geldi: uç duvar saatine/çöküşe düştü '
            '(HTTP %s, %.2f s)' % (r.status_code, gecen))
        if r.status_code != 200:
            g = r.get_json() or {}
            alanlar = {x.get('field')
                       for x in (g.get('invalid_fields') or [])}
            assert 'fin_count' in alanlar, (
                'uç %s ile reddetti ama reddin alanını SÖYLEMEDİ: %s'
                % (r.status_code, g))

    def test_p7b223_isaret_ve_sonluluk_kapisi_duruyor(self, istemci):
        """K5: D29'da kurulan kapılar yürürlükte (kalan iş BÜYÜKLÜK ekseni)."""
        for yuk in ({'radius': 0, 'fill_height': 1.0},
                    {'radius': -1, 'fill_height': 1.0},
                    {'radius': 0.5, 'fill_height': -1}):
            r = istemci.post('/api/slosh-analysis', json=yuk)
            assert r.status_code == 400, (yuk, r.status_code)


# ===========================================================================
# P7B4-13 — CAD "features" LİSTESİ SABİT DEĞİL, ÜRETİLENDEN TÜRER
# ===========================================================================
CAD_YUK = {'chamber_diameter': 0.1, 'chamber_length': 0.5,
           'throat_diameter': 0.02, 'exit_diameter': 0.06,
           'nozzle_length': 0.15, 'chamber_pressure': 30, 'thrust': 5000,
           'burn_time': 10, 'wall_thickness': 0.005}


class TestP7B413CadOzellikListesi:
    """ÖLÇÜLDÜ (``a1/once.json`` K10, ``/api/detailed-cad/liquid`` 200):
    ``component_details``in HER alanı *"NOT AVAILABLE - not produced by this
    analysis run"* iken (enjektör ``hole_count``, soğutma ``channel_count``,
    malzemeler, Isp) yanıt 'Injector hole patterns' ve 'Cooling channel
    layout' çizildiğini İDDİA ediyordu; liste motor tipinden de bağımsızdı.
    """

    def test_verisi_olmayan_ozellik_iddia_edilmez(self, istemci):
        r = istemci.post('/api/detailed-cad/liquid', json=CAD_YUK)
        assert r.status_code == 200, r.status_code
        g = r.get_json()
        detay = g['component_details']
        ozellikler = g['design_info']['features']
        for ad, anahtar in (('Injector hole patterns', 'injector'),
                            ('Cooling channel layout', 'cooling')):
            blok = detay.get(anahtar) or {}
            gercek = any(
                not str(v).startswith('NOT AVAILABLE')
                for k, v in blok.items() if k != 'source')
            if not gercek:
                assert ad not in ozellikler, (ad, blok)

    def test_cizim_ozellikleri_iz_sayisina_bagli(self, istemci):
        g = istemci.post('/api/detailed-cad/liquid', json=CAD_YUK).get_json()
        assert g['trace_count'] > 0
        assert 'Internal structure cross-section' in g['design_info']['features']

    def test_iddianin_dayanagi_yayimlanir(self, istemci):
        g = istemci.post('/api/detailed-cad/liquid', json=CAD_YUK).get_json()
        assert g['design_info']['features_basis']
