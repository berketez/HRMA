# -*- coding: utf-8 -*-
"""ÖH Dalga-23 · arayuz kulvarı aşama-1 bekçileri.

Her sınıf BİR defter kalemine karşılık gelir ve o kalemin onarımını
TERS-MUTASYONLA kırmızıya döndürülebilir biçimde kilitler
(``docs/scofield/raw/OH/D23/arayuz/a1/mutasyon.json``).

Ölçüm dosyaları:
  * ``docs/scofield/raw/OH/D23/arayuz/a1/once.json``      (statik, taban ağacı)
  * ``docs/scofield/raw/OH/D23/arayuz/a1/once_uc.json``   (uç, taban ağacı)
  * ``.../sonra.json`` · ``.../sonra_uc.json``            (bu ağaç)
"""
import io
import os
import re

import pytest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _oku(*parcalar):
    with io.open(os.path.join(KOK, *parcalar), encoding='utf-8') as f:
        return f.read()


@pytest.fixture(scope='module')
def liquid_html():
    return _oku('hrma', 'templates', 'liquid.html')


@pytest.fixture(scope='module')
def solid_html():
    return _oku('hrma', 'templates', 'solid.html')


@pytest.fixture(scope='module')
def advanced_html():
    return _oku('hrma', 'templates', 'advanced.html')


@pytest.fixture(scope='module')
def launch_site_html():
    return _oku('hrma', 'templates', 'launch_site.html')


@pytest.fixture(scope='module')
def structural_panel_js():
    return _oku('hrma', 'static', 'js', 'panels', 'structural_panel.js')


@pytest.fixture(scope='module')
def app_js():
    return _oku('hrma', 'static', 'js', 'app.js')


@pytest.fixture(scope='module')
def i18n_pages_js():
    return _oku('hrma', 'static', 'js', 'i18n_pages.js')


@pytest.fixture(scope='module')
def i18n_common_js():
    return _oku('hrma', 'static', 'js', 'i18n_common.js')


@pytest.fixture(scope='module')
def i18n_advanced_js():
    return _oku('hrma', 'static', 'js', 'i18n_advanced.js')


def _anahtar_cift(metin, anahtar):
    """Anahtar EN + TR bloklarının İKİSİNDE de tanımlı mı?"""
    return len(re.findall(r"'%s'\s*:" % re.escape(anahtar), metin))


# --------------------------------------------------------------- P13B2-05
class TestP13B2_05RozetIlkBoya:
    """liquid.html rozeti hüküm kazanmadan YEŞİL yanamaz.

    ÖLÇÜLDÜ (once.json P13B2-05, taban ef527ae):
    ``liquid_static_connected_cea = 1``, ``liquid_static_unknown = 0``,
    ``i18n_liq_not_checked_keys = 0``. Yani sayfa açılır açılmaz, hiçbir
    denetim koşmadan "NASA CEA Connected" yazıyordu. Kardeş şablonda
    (solid.html) tam bu kusur P17B2-07 olarak ölçülüp ÖH D21'de onarıldı
    (``solid_static_unknown = 2``).
    """

    def test_ilk_boyada_kazanilmamis_hukum_yok(self, liquid_html):
        assert 'database-status status-connected cea-status' not in liquid_html
        assert 'database-status status-connected nist-status' not in liquid_html

    # ÇEVRİLDİ (v3.0.1 K kulvarı, Ayberk tur 1). Aşağıdaki üç bekçi
    # rozetin "denetlenmedi" ilk boyasını ve onun sözlük çiftini ŞART
    # koşuyordu. ÖLÇÜLDÜ (docs/scofield/raw/OH/V301/ayberk1/kaynak-cea/
    # gorsel_once.json): yoklamadan sonra rozet HER makinede "Offline"a
    # dönüyordu ve hesabın hiçbir sayısının kaynağı değildi; bekçi kusurlu
    # göstergenin VARLIĞINI kilitliyordu. Rozet söküldü. P13B2-05'in
    # kazanımı (ilk boyada kazanılmamış hüküm yok) yeni veri kaynağı
    # satırında ölçülür.
    def test_ilk_boya_denetlenmedi_diyor(self, liquid_html):
        assert not re.search(r'class="[^"]*\b(?:database-status|cea-status|nist-status)\b', liquid_html)
        m = re.search(r'<div class="data-source-line"[^>]*'
                      r'data-i18n="liq.ui.data_source_line">([^<]*)</div>',
                      liquid_html)
        assert m, 'veri kaynağı satırı yok'
        for yasak in ('Connected', 'Offline'):
            assert yasak not in m.group(1), m.group(1)

    def test_nötr_durum_sinifi_tanimli(self, liquid_html):
        # Satırın biçimi CSS'te tanımlı (rozet sınıflarının halefi).
        assert re.search(r'\.data-source-line\s*\{', liquid_html)

    @pytest.mark.parametrize('anahtar', [
        'liq.ui.data_source_line', 'liq.js.ds_combustion_cea',
        'liq.js.ds_combustion_table', 'liq.js.ds_combustion_unstated'])
    def test_i18n_cifti_var(self, i18n_pages_js, anahtar):
        assert _anahtar_cift(i18n_pages_js, anahtar) == 2, (
            '%s EN+TR çifti eksik' % anahtar)


# --------------------------------------------------------------- OH-D22-05
class TestOHD22_05MansetSayisi:
    """Manşet sayısı ADIYLA basılır (P7B3-23'ün ekran ayağı).

    ÖLÇÜLDÜ (once.json OH-D22-05): üretici alanı yayımlıyor
    (``uretici = 1``) ama ``panel_headline = 0`` idi; panelin ilk satırı
    ``minimum_earned_safety_factor`` (grep 12) basıyordu.
    UÇ ÖLÇÜMÜ (once_uc.json): ``headline_safety_factor = None`` +
    ``headline_safety_factor_source`` YAYIMLI — yani hüküm geri
    çekilmişken bile ekranın söyleyeceği bir şey vardı ve söylemiyordu.
    """

    def test_panel_mansett_alanini_okuyor(self, structural_panel_js):
        assert 'sf.headline_safety_factor_source' in structural_panel_js
        assert 'sf.headline_safety_factor' in structural_panel_js

    def test_manset_fail_closed(self, structural_panel_js):
        # Alan yayımlanmadıysa satır HİÇ basılmaz; sayı null ise '—'.
        assert re.search(
            r"typeof sf\.headline_safety_factor_source === 'string'",
            structural_panel_js)
        assert 'headline_safety_factor: null' in structural_panel_js

    def test_p5b1_01_satirlari_korunuyor(self, structural_panel_js):
        """Manşet satırı P5B1-01'in kazandığı iki satırı YERİNDEN ETMEZ."""
        assert 'earnedLabel' in structural_panel_js
        assert "rows.push([earnedLabel, earnedCell, SRV(basis)]);" \
            in structural_panel_js
        assert 'panel.structural.sfMinAll' in structural_panel_js

    def test_i18n_cifti_var(self, i18n_common_js):
        assert _anahtar_cift(i18n_common_js, 'panel.structural.sfHeadline') == 2


# --------------------------------------------------------------- OH-D22-06
class TestOHD22_06KesilenTarama:
    """Süre bütçesiyle kesilen tarama "başarılı" diye künyelenmez.

    ÖLÇÜLDÜ (once.json OH-D22-06): uç alanı üç yerde üretiyor
    (``uretici_app_py = 3``), JS katmanında grep 0 (``js_truncated = 0``).
    P16B3-06'dan sonra eskiden 422 alan istekler 200 + KISMİ eğri dönüyor.
    """

    def test_advanced_kesilmeyi_okuyor(self, advanced_html):
        # Yorum metni DEĞİL kodun kendisi aranır.
        assert 'const kesik = (results.truncated_by_time_budget' \
            in advanced_html
        assert 'points_not_attempted' in advanced_html

    def test_advanced_yesil_basmiyor(self, advanced_html):
        """Kesilme varsa 'completed successfully' dalına GİRİLMEZ."""
        assert re.search(
            r'if \(kesik\) \{', advanced_html), 'kesilme dalı yok'
        i_kesik = advanced_html.index('if (kesik) {')
        i_basarili = advanced_html.index(
            'adv.msg.parametricAnalysisCompletedSuccessfully')
        assert i_kesik < i_basarili, (
            'kesilme dalı başarı dalından SONRA geliyor: yeşil hüküm önce '
            'basılır')

    def test_app_js_olu_kopya_geri_gelmedi(self, app_js):
        # fix-33 (14 Eyl 2026, Fable sivi-01 bulgusu): app.js'teki parametrik tarama
        # kopyası ÖLÜYDÜ (advanced.html satır içi sürümü kazanıyordu) ve D30 panel a1
        # (896d2e83) onu söktü; kesilme okuması CANLI yolda test_advanced_kesilmeyi_okuyor
        # ile ölçülür. Bu düğüm ölü kopyanın geri gelmediğini kilitler.
        assert 'const kesikTarama = (result.truncated_by_time_budget' not in app_js
        assert "TF('app.msg.paramTruncated'" not in app_js

    def test_i18n_ciftleri_var(self, i18n_common_js, i18n_advanced_js):
        # app.msg.paramTruncated ölü kopyayla birlikte fix-31'de sözlükten çıktı;
        # canlı anahtar adv.msg.parametricAnalysisTruncated (EN+TR).
        assert _anahtar_cift(i18n_common_js, 'app.msg.paramTruncated') == 0
        assert _anahtar_cift(
            i18n_advanced_js, 'adv.msg.parametricAnalysisTruncated') == 2


# --------------------------------------------------------------- P16B2-10
class TestP16B2_10LuleTermalDenetimi:
    """Koşmayan boğaz termal denetimi SESSİZ kalmaz.

    ÖLÇÜLDÜ (once_uc.json P16B2-10, taban):
      * ``phenolic``  -> status 'not_analyzed', verdict None,
                        warnings 0  (panel HİÇBİR ŞEY basmıyordu)
      * ``graphite``  -> status 'analyzed', verdict 'EXCEEDS_ALLOWABLE',
                        warnings 1 (critical)
      * ``copper``    -> aynı
    Yani kullanıcı ``graphite``ten ``phenolic``e geçtiğinde KRİTİK
    aşırı-sıcaklık hükmü ekrandan sessizce kayboluyor, yerine hiçbir şey
    gelmiyordu (once.json ``solid_status_reason_basiyor = 0``).
    """

    def test_panel_kosmayan_denetimi_beyan_ediyor(self, solid_html):
        assert 'panelwarn.solid.nozzle_thermal_not_evaluated' in solid_html
        assert 'nozzleThermal.status' in solid_html
        assert 'nozzleThermal.reason' in solid_html

    def test_beyan_uyari_kanalina_giriyor(self, solid_html):
        """Kayıt gerçekten ``raw`` listesine ekleniyor mu?"""
        assert 'nozzleBeyani' in solid_html
        assert re.search(r'nozzleThermal\.warnings \|\| \[\],\s*\n\s*'
                         r'nozzleBeyani', solid_html)

    def test_beyan_yalniz_denetim_kosmadiysa_dogar(self, solid_html):
        assert "nozzleDurum !== 'analyzed'" in solid_html
        assert "nozzleHukum === 'NOT_EVALUATED'" in solid_html

    def test_i18n_cifti_var(self, i18n_common_js):
        assert _anahtar_cift(
            i18n_common_js, 'panelwarn.solid.nozzle_thermal_not_evaluated') == 2

    def test_uc_ayagi_geri_gitmedi(self):
        """API ayağı (D22'de ölçüldü) hâlâ gerekçeli."""
        kaynak = _oku('hrma', 'engines', 'solid_rocket_engine.py')
        assert "'status': 'not_analyzed'" in kaynak
        assert 'warn.solid.nozzle_material_over_temp' in kaynak


# --------------------------------------------------------------- OH-D19-19
class TestOHD19_19ProjeYuklemeUyarilari:
    """``vehicle.load_warnings`` artık bir ekrana ulaşıyor.

    ÖLÇÜLDÜ (once.json OH-D19-19): ``app_py_uretim = 1`` (uç alanı
    üretiyor), ``js_load_warnings_toplam = 0`` (hiçbir panel okumuyor).
    """

    def test_uretici_yerinde(self):
        kaynak = _oku('hrma', 'app.py')
        assert "vehicle['load_warnings']" in kaynak

    def test_sayfa_uyarilari_basiyor(self, launch_site_html):
        # Yorum metni DEĞİL kodun kendisi aranır (yorumdaki alan adı bir
        # bekçiyi yeşil tutmaya yetmemeli — ters mutasyon bunu gösterdi).
        assert 'Array.isArray(v.load_warnings)' in launch_site_html
        assert 'v.load_warnings.filter(' in launch_site_html
        assert "'load_warnings: '" in launch_site_html

    def test_uyari_varsa_kunye_notr_kalmiyor(self, launch_site_html):
        assert 'ls-note-warn' in launch_site_html
        assert re.search(r'\.ls-hint\.ls-note-warn\s*\{', launch_site_html)


# --------------------------------------------------------------- OH-D18-10
class TestOHD18_10BeslemeVeKapakSozlesmeleri:
    """P4B3-21/P5B3-08/P5B3-10 üç sözleşme alanı ekrana çıkıyor.

    ÖLÇÜLDÜ (once.json OH-D18-10): ``feed_regime_verified = 0``,
    ``feed_roughness_provenance = 0``, ``feed_head_by_type = 0``;
    üretici tarafta dördü de yayımlı (``uretici_valve_feedline = 4``).
    UÇ ÖLÇÜMÜ (once_uc.json OH-D18-10_feed, /calculate_liquid RP-1/LOX):
    ``fuel_line.regime_verified = False`` — yani geri çekilmiş rejim
    hükmü ekranda doğrulanmış bir vana boyutu gibi duruyordu.
    """

    def test_sivi_sayfasi_rejim_hukmunu_okuyor(self, liquid_html):
        assert 'regime_verified === false' in liquid_html
        assert 'panelwarn.liquid.valve_regime_not_verified' in liquid_html

    def test_sivi_sayfasi_puruzluluk_kokenini_okuyor(self, liquid_html):
        assert 'roughness_provenance === null' in liquid_html
        assert 'panelwarn.liquid.roughness_provenance_undeclared' in liquid_html

    def test_beyanlar_yalniz_fail_closed_durumda_dogar(self, liquid_html):
        """Rejim doğrulanmışsa ya da köken beyanlıysa uyarı ÜRETİLMEZ."""
        assert 'kap.regime_verified === false' in liquid_html
        assert 'pm.roughness_provenance === null' in liquid_html

    def test_yapisal_panel_kapak_tiplerini_ayri_basiyor(
            self, structural_panel_js):
        # Yorum metni DEĞİL kodun kendisi aranır.
        assert 'const sfTip = cap.head_safety_factor_by_type;' \
            in structural_panel_js
        assert 'const stressTip = cap.head_stress_by_type_MPa;' \
            in structural_panel_js
        assert 'cap.head_safety_factor_by_type_basis' in structural_panel_js

    def test_i18n_ciftleri_var(self, i18n_common_js):
        assert _anahtar_cift(
            i18n_common_js, 'panelwarn.liquid.valve_regime_not_verified') == 2
        assert _anahtar_cift(
            i18n_common_js,
            'panelwarn.liquid.roughness_provenance_undeclared') == 2
        assert _anahtar_cift(
            i18n_common_js, 'panel.structural.headSfByType') == 2


# --------------------------------------------------------------- OH-D17-04
class TestOHD17_04ViskoziteKokeni:
    """Girilmemiş sayı 'kullanıcı girdisi' künyesi almaz.

    ÖLÇÜLDÜ (once.json OH-D17-04): ``adv_value_default = 1`` +
    ``adv_or_default = 1`` + ``adv_kokeni_beyan = 0``; çözücü tarafında
    ``viscosity_basis = 'user input'`` (injector_design.py). Yani
    viskozite alanına HİÇ dokunulmasa da 0,0002 Pa·s gövdeye gidiyor ve
    raporda kullanıcının ölçümü gibi görünüyordu.
    """

    def test_govde_kokeni_ayirt_ediyor(self, advanced_html):
        assert 'viskoziteGovdeDegeri' in advanced_html
        assert 'viskoziteKullaniciGirdisiMi' in advanced_html
        assert 'oxidizer_viscosity: viskoziteGovdeDegeri()' in advanced_html

    def test_dokunulmamis_alan_null_gonderir(self, advanced_html):
        assert re.search(
            r'if \(!el \|\| !viskoziteKullaniciGirdisiMi\(el\)\) return null;',
            advanced_html)

    def test_ok21_form_katmani_sokulmedi(self, advanced_html):
        """ÖK-21: ``value="X"`` ve ``|| X`` yedeği YERİNDE kalır."""
        assert advanced_html.count(
            'id="oxidizer_viscosity" value="0.0002"') == 1
        assert 'el.value || 0.0002' in advanced_html

    # test_kardes_sayfa_deseniyle_ayni (1 düğüm, simple.html) emekli — sayfa sökümü: Berke 23 Eyl, dalga36/sokum

    def test_cozucu_sirasi_yerinde(self):
        kaynak = _oku('hrma', 'utils', 'injector_design.py')
        assert "self.viscosity_basis = 'user input'" in kaynak
        assert 'def _resolve_viscosity' in kaynak


# --------------------------------------------------------------- P11B1-06
class TestP11B1_06IspReferansi:
    """ÇÜRÜTÜLDÜ — kapanış kilidi.

    Başlık: "Isp çipi VAKUM değerini niteliksiz basıyor". ÖLÇÜLDÜ
    (once.json P11B1-06, taban ef527ae): güvertenin etiketleyicisi
    ``ispLabel`` referansı ÇAĞIRANIN beyanından okuyor
    (``deck_ispLabel = 1``, ``deck_referanssiz_etiket = 3``; ÖH D21
    8e53817) ve güverteyi kuran İKİ sayfanın İKİSİ de beyanı gönderiyor:
    ``liquid_isp_reference_gonderiyor = 1`` (ÖH D22, sivi),
    ``solid_isp_reference_gonderiyor = 1``. Üçüncü bir çağıran YOK
    (``MotorVizDeck.create`` yalnız bu iki şablonda geçiyor). Kalem bu
    ağaçta kapalıdır; bu sınıf geri gidişi engeller.
    """

    def test_guverte_referansi_cagirandan_okuyor(self):
        deck = _oku('hrma', 'static', 'js', 'motor_viz_deck.js')
        assert 'function ispLabel' in deck
        assert 'ISP_REFERANSSIZ_ETIKET' in deck
        # ÖH D33-KOLAY · denetim ŞARTI (arayuz): sabitin ADI değil DEĞERİ
        # kilitlenir. Kalemin kendi başlığındaki kusur "çip niteliksiz 'Isp'
        # basıyor"du; ad kilidi o kusuru göremez (sabit `'Isp'` dizesine
        # çevrilse bekçi yeşil kalırdı). Kapanış kilidi artık başka
        # dosyadaki kardeş bekçiye bağımlı değildir.
        assert "var ISP_REFERANSSIZ_ETIKET = 'Isp (reference not declared)';" \
            in deck, ('referanssız etiket metni değişti: çip yine niteliksiz '
                      "'Isp' basıyor olabilir")
        assert 'md.isp_reference' in deck
        # Beyan yoksa sessizce 'vakum' sayılmaz.
        assert re.search(
            r"if \(typeof ref !== 'string'\) return ISP_REFERANSSIZ_ETIKET;",
            deck)

    def test_iki_cagiran_da_beyan_gonderiyor(self, liquid_html, solid_html):
        assert "data.isp_reference = 'vacuum'" in liquid_html
        assert 'isp_reference:' in solid_html

    def test_ucuncu_cagiran_yok(self, liquid_html, solid_html, app_js):
        """Beyansız yeni bir güverte çağrısı eklenirse bu bekçi kırılır."""
        toplam = (liquid_html.count('MotorVizDeck.create')
                  + solid_html.count('MotorVizDeck.create')
                  + app_js.count('MotorVizDeck.create'))
        assert toplam == 2, (
            'MotorVizDeck.create çağrısı sayısı değişti (%d): yeni çağıran '
            'isp_reference beyanını da göndermek zorundadır' % toplam)


# --------------------------------------------------------------- P12aB4-18
class TestP12aB4_18HudDurumBaglama:
    """KISMEN — ölçüm dondurulur, onarım UÇ tarafına bağlıdır.

    ÖLÇÜLDÜ (once_uc.json P12aB4-18): ``/calculate_solid`` ve
    ``/calculate_liquid`` yanıtlarının İKİSİNDE de
    ``structural_analysis`` VAR ama ``safety_analysis`` YOK
    (``safety_analysis_var = False``, ``status = None``). Yani
    ``hud.js::bindState``in beklediği hüküm SÖZCÜĞÜ (SAFE / ACCEPTABLE /
    MARGINAL / UNSAFE / NOT_EVALUATED) bu iki sayfa için hiç
    yayımlanmıyor. Katı sayfasının yayımladığı tek hüküm sözcüğü
    ``nozzle_material_analysis.verdict = 'EXCEEDS_ALLOWABLE'`` ve o da
    ``hud.js::STATE_MAP`` içinde YOK — yani panele ``state`` koymak
    ancak (a) sayfanın kendi sınıflandırmasını UYDURMASIYLA (yasak) ya
    da (b) hüküm sözlüğünün genişletilmesiyle (hud.js, bu kulvarın
    sahası DIŞINDA; D22 electron kulvarı da bunu "yapısal kulvar
    kararı" diye bırakmıştı) mümkündür.

    Bu sınıf iki şeyi kilitler: döngü hâlâ AYAKTA (yani onarım tek
    satırlık bir alan eklemesine iniyor) ve sözlük fail-closed kalıyor.
    """

    def test_bindState_dongusu_iki_sayfada_da_duruyor(
            self, solid_html, liquid_html):
        assert 'HRMAHud.bindState' in solid_html
        assert 'HRMAHud.bindState' in liquid_html

    def test_hukum_sozlugu_fail_closed(self):
        """ÖH D24 / P12aB4-18 — BEKÇİ ÇEVRİLDİ (gerekçe aşağıda).

        Bu bekçinin AMACI doğruydu: ısıl bir sözcük (`EXCEEDS_ALLOWABLE`)
        YAPISAL hüküm merdivenine sessizce eklenmesin. Ama ÖLÇÜMÜ yanlış
        yerden alıyordu — sözcüğün hud.js KAYNAK METNİNDE geçmemesini
        istiyordu, oysa asıl değişmez sözcüğün ``STATE_MAP`` ANAHTARI
        olmamasıdır. Kaynak metin yasağı, kusuru anlatan bir yorumu bile
        yasaklıyor ve onarımı engelliyordu.

        Ayrıca `removeAttribute` dalının varlığını "tanınmayan sözcük renk
        almaz" diye okuyordu; CANLI ölçüm bunun TERSİNİ gösterdi: öznitelik
        silinince `.hd-led` kendi yedeğine (--hd-green) düşüyor, yani
        tanınmayan sözcük ONAY YEŞİLİ alıyordu (rgb(45, 212, 168);
        raw/OH/D24/electron/a1/once_b4_18.json). O dal artık YALNIZ hüküm
        HİÇ verilmemiş hâle ait.
        """
        hud = _oku('hrma', 'static', 'js', 'hud.js')
        m = re.search(r'var STATE_MAP = \{([^}]*)\}', hud)
        assert m, 'STATE_MAP bulunamadı'
        anahtarlar = set(re.findall(r'([A-Z_]+)\s*:', m.group(1)))
        assert anahtarlar == {'SAFE', 'ACCEPTABLE', 'MARGINAL', 'UNSAFE',
                              'NOT_EVALUATED'}, anahtarlar
        # Isıl uç sözcüğü YAPISAL merdivene ALINMADI (asıl değişmez).
        assert 'EXCEEDS_ALLOWABLE' not in anahtarlar
        # Hüküm HİÇ verilmemişse öznitelik silinir; sözlük dışı sözcükte
        # SİLİNMEZ — nötr `unrecognized` durumu konur (yeşile düşüş yok).
        assert re.search(r'\} else \{\s*\n\s*el\.removeAttribute\('
                         r"'data-state'\);", hud)
        assert re.search(r"else if \(raw !== ''\) \{\s*\n\s*"
                         r"el\.setAttribute\('data-state', UNRECOGNIZED_STATE\);",
                         hud), 'sözlük dışı sözcük için nötr durum dalı yok'
