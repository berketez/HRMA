# -*- coding: utf-8 -*-
"""ÖH D32 · kati · aşama 1/1 — OH-D31-17 İKİ-FAZ KAYIP ZİNCİRİ BEKÇİSİ.

Kalem: OH-D31-17 (Katı motor iki-faz kaybı zinciri doğrulanmamış).
Berke/Astra hükmü 15 Eyl 2026 (docs/scofield/raw/OH/D32/oturum-devri/
berke_kararlari_2026-09-15.md §1 + astra/astra3_q1_cevap.md):

  * Zinciri DOĞRULA (kaynak/model/geçerlilik zarfı; boyut + sembolik;
    0,98 yolu ⟷ boş yol ⟷ aday model önce/sonra),
  * ara dönemde "iki-faz düzeltmesi doğrulanmamış" durumunu
    API/panel/PDF'e TAŞI ve bu sayıdan doğrulanmış performans hükmü
    ÜRETME,
  * çözücü VARSAYILANINI DEĞİŞTİRME — uygulama kararı Berke'nindir.

Bu dosya üç şeyi kilitler:
  A) zincir kimliği (doğrusal çapa = 100·K·X_p; modül = çapa·g(x);
     Hermsen d43 yeniden üretimi; limitler),
  B) durum beyanının ÜÇ kanalda birden bulunması (API gövdesi, panel
     şablonu, PDF'in okuduğu uyarı kaydı) ve
  C) çözücü varsayılanının DEĞİŞMEDİĞİ (eta = 1,0; Isp 248,5791 s).

Her iddia ters-mutasyonla kırmızı görüldü
(docs/scofield/raw/OH/D32/kati/a1/mutasyon.json).
"""
import json
import os
import re

import pytest
from tests.support.kanit import kanit_gerekli

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _oku(*parca):
    with open(os.path.join(KOK, *parca), encoding='utf-8') as f:
        return f.read()


#: Varsayılan katı koşum — Berke/Astra kaleminde adı geçen girdiler.
TABAN_YUK = {
    'motor_name': 'D32-KATI-A1', 'propellant_type': 'apcp',
    'grain_type': 'bates', 'chamber_pressure': 50.0, 'thrust': 5000.0,
    'burn_time': 5.0, 'chamber_diameter': 100.0, 'grain_length': 500.0,
    'core_diameter': 30.0, 'expansion_ratio': 8.0,
}


@pytest.fixture(scope='module')
def istemci():
    os.environ.setdefault('HRMA_HEADLESS', '1')
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _kos(istemci, **ek):
    r = istemci.post('/calculate_solid', json=dict(TABAN_YUK, **ek))
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


@pytest.fixture(scope='module')
def bos_yol(istemci):
    """Kullanıcı çarpanı YOK — bugünkü varsayılan (a3 sonrası)."""
    return _kos(istemci)


def _tva(j):
    return ((j.get('detailed_analysis') or {}).get('performance_metrics')
            or {}).get('theoretical_vs_actual_isp') or {}


# =====================================================================
# A) ZİNCİR KİMLİĞİ — iki sayı HANGİ modelden geliyor?
# =====================================================================
class TestAZincirKimligi:
    """Astra (15 Eyl): '%4,08 boyut düzeltmeli model değil, 100·k·X_p
    doğrusal teşhisidir'. İddia ölçüldü ve burada kilitleniyor."""

    def test_dogrusal_teshis_tam_olarak_100_K_Xp(self, bos_yol):
        from hrma.engines.solid_rocket_engine import TWO_PHASE_LOSS_COEFF
        tva = _tva(bos_yol)
        blok = bos_yol['two_phase_loss']
        beta = blok['inputs_used']['condensed_mass_fraction']
        beklenen = 100.0 * TWO_PHASE_LOSS_COEFF * beta
        assert tva['two_phase_losses'] == pytest.approx(beklenen, abs=1e-12)
        # ÖLÇÜLDÜ (zincir_once.json M1): sapma tam olarak 0,0.
        assert tva['two_phase_losses'] == pytest.approx(4.081423276501111,
                                                        rel=1e-12)

    def test_modul_dogrusal_capanin_g_x_katidir(self, bos_yol):
        """modül = 100·K·β·g(x), g(x) = 2x/(1+x),
        x = (d43/D43_REF)²·(D_THROAT_REF/Dt) — ÖZDEŞLİK."""
        from hrma.analysis.two_phase_loss import two_phase_loss as _tpl
        D43_REF_UM = _tpl.D43_REF_UM
        D_THROAT_REF_M = _tpl.D_THROAT_REF_M
        tva = _tva(bos_yol)
        blok = bos_yol['two_phase_loss']
        assert blok['status'] == 'computed'
        d43 = blok['particle_diameter_um']
        dt_m = blok['inputs_used']['throat_diameter_m']
        x = (d43 / D43_REF_UM) ** 2 * (D_THROAT_REF_M / dt_m)
        g = 2.0 * x / (1.0 + x)
        assert blok['two_phase_loss_pct'] == pytest.approx(
            tva['two_phase_losses'] * g, rel=1e-12)
        # İki sayı FARKLIDIR: aynı büyüklüğün iki modeli (D31 dersi 24).
        assert blok['two_phase_loss_pct'] != pytest.approx(
            tva['two_phase_losses'], rel=1e-6)

    def test_hermsen_d43_yeniden_uretilebilir(self, bos_yol):
        """d43 [um] = C·Dt[in]^n·(1-exp(-c·zeta_c·Pc[psia]·tau[ms]))."""
        import math
        from hrma.analysis.two_phase_loss import (
            AL2O3_MOLAR_MASS_KG_KMOL, PSIA_PER_BAR, two_phase_loss as _tpl)
        blok = bos_yol['two_phase_loss']
        g = blok['inputs_used']
        dt_in = g['throat_diameter_m'] * 1000.0 / 25.4
        pc_psia = g['chamber_pressure_bar'] * PSIA_PER_BAR
        zeta_c = 100.0 * g['condensed_mass_fraction'] / AL2O3_MOLAR_MASS_KG_KMOL
        arg = (_tpl.HERMSEN_EXP_COEFF * zeta_c * pc_psia
               * g['residence_time_ms'])
        beklenen = (_tpl.HERMSEN_COEFF * dt_in ** _tpl.HERMSEN_DT_EXP
                    * (1.0 - math.exp(-arg)))
        assert blok['particle_diameter_um'] == pytest.approx(beklenen,
                                                             rel=1e-12)

    def test_sifir_yogusmus_faz_limiti_tam_sifir(self):
        """β → 0 limitinde kayıp TAM sıfır (Astra'nın istediği limit)."""
        from hrma.analysis.two_phase_loss import two_phase_loss as _tpl
        s = _tpl.evaluate(condensed_mass_fraction=0.0, throat_diameter=0.03,
                          chamber_pressure=50.0, residence_time_ms=20.0,
                          gamma_gas=1.1986, molecular_weight_gas=28.0)
        assert s['valid'] is True
        assert s['two_phase_loss_pct'] == 0.0

    def test_taban_nozul_verimi_iki_faz_carpani_ICEREMEZ(self, bos_yol):
        """Çifte sayım ölçümü: APCP tablo verimi referans koniyi bile
        çarpan olarak içeremez (artık NEGATİF), dolayısıyla iki-faz
        kaybını da içeremez. ÖLÇÜLDÜ: once.json Z3."""
        from hrma.engines.solid_rocket_engine import (
            SOLID_NOZZLE_REFERENCE_HALF_ANGLE_DEG,
            _conical_divergence_efficiency)
        lam_ref = _conical_divergence_efficiency(
            SOLID_NOZZLE_REFERENCE_HALF_ANGLE_DEG)
        # V307 KATI-DOĞRULAMA faz 3 (B1, 16 Kas 2026): iddia TABLO verimi içindir.
        # Eski satır ``nozzle_efficiency_applied`` okuyordu; B1'den önce o
        # tablo verimine eşitti (0,985), B1 ile modülün iki fazlı tahminini
        # de taşır (0,9370). Ölçülen şey değişmedi: TABLO verimi referans
        # koniden büyüktür, yani iki fazlı kaybı içeremez.
        eta = bos_yol['delivered_performance_basis'][
            'nozzle_efficiency_table']['value']
        assert eta == 0.985
        assert eta > lam_ref, (eta, lam_ref)
        artik = 100.0 * (1.0 - eta / lam_ref)
        assert artik < 0.0
        # Künye bu gerçeği SÖYLEMELİ: tablo verimi iki-faz çarpanı taşımaz;
        # modül tahmini AYRI çarpan olarak uygulanır ve kullanıcı çarpanı
        # onun YERİNE geçer (çarpım yok).
        beyan = bos_yol['two_phase_loss']['overlap_declaration']
        assert 'does not contain a two-phase factor' in beyan
        assert 'NASA SP-8039 Fig. 8' in beyan
        assert 'REPLACED this estimate' in beyan


# =====================================================================
# B) DURUM BEYANI — API / PANEL / PDF, ÜÇÜ BİRDEN
# =====================================================================
class TestBDurumBeyani:
    """Astra: "iki-faz düzeltmesi doğrulanmamış" durumu Isp yanında
    görünür, JSON/PDF'e taşınır, bu sayıdan doğrulanmış performans
    hükmü üretilmez. ÖLÇÜLDÜ (once.json Z4): üç kanalda da 0 eşleşme."""

    def test_api_govdesi_durumu_yayimlar(self, bos_yol):
        # V307 KATI-DOĞRULAMA faz 3 (B1, 16 Kas 2026): durum 'uygulanmadı'dan 'modül
        # tahmini uygulandı'ya döndü (ana model kararı). "Doğrulandı" DENMEZ:
        # tahmin kaynaklıdır ama bu itici için bağımsız ateşleme kaydı yok.
        from hrma.engines.solid_rocket_engine import (
            TWO_PHASE_STATUS_MODULE_APPLIED)
        tva = _tva(bos_yol)
        assert tva['two_phase_correction_status'] == \
            TWO_PHASE_STATUS_MODULE_APPLIED
        assert tva['two_phase_correction_verified'] is False
        kunye = tva['two_phase_correction_status_basis']
        assert 'IS applied to the thrust coefficient' in kunye
        assert 'not a verified value for this propellant' in kunye
        assert 'NASA SP-8039' in kunye and 'NASA-CR-158815' in kunye

    def test_teshis_blogu_ayni_durumu_tasir(self, bos_yol):
        """İki kanal AYNI tek tanım noktasından beslenir."""
        tva = _tva(bos_yol)
        blok = bos_yol['two_phase_loss']
        for alan in ('two_phase_correction_status',
                     'two_phase_correction_verified',
                     'two_phase_correction_status_basis'):
            assert blok[alan] == tva[alan]

    def test_pdf_kanali_uyari_kaydi_tasir(self, bos_yol):
        """pdf_generator yalnız design_warnings/warnings okur
        (PDFReportGenerator.WARNING_SOURCES) — durum ORADA olmalı."""
        from hrma.export.pdf_generator import PDFReportGenerator
        etiketler = {k for _, _, k in PDFReportGenerator.WARNING_SOURCES}
        assert 'design_warnings' in etiketler
        # V307 KATI-DOĞRULAMA faz 3 (B1, 16 Kas 2026): PDF kanalındaki TEK kayıt artık
        # 'uygulandı' kaydıdır (bilgi düzeyi). Eski kayıt
        # ('…two_phase_correction_unverified', status not_applied_unverified,
        # applied_efficiency 1,0) "Isp iki-faz düzeltmesi taşımıyor" diyordu;
        # B1 ile bu yanlış olurdu. Kanal sözleşmesi aynı: durum uyarı
        # listesinde DURUR, kayıt sayısı 1'dir.
        eski = [w for w in bos_yol['design_warnings']
                if isinstance(w, dict)
                and w.get('code') == 'warn.solid.two_phase_correction'
                                     '_unverified']
        assert eski == []
        kayitlar = [w for w in bos_yol['design_warnings']
                    if isinstance(w, dict)
                    and w.get('code') == 'warn.solid.two_phase_estimate'
                                         '_applied']
        assert len(kayitlar) == 1, bos_yol['design_warnings']
        assert kayitlar[0]['severity'] == 'info'
        p = kayitlar[0]['params']
        assert p['loss_percent'] == pytest.approx(
            bos_yol['two_phase_loss']['two_phase_loss_pct'], abs=5e-3)
        assert p['band_low_percent'] < p['loss_percent'] < p['band_high_percent']
        # D-track sözleşmesi: params DİLSİZDİR — string parametre boşluk
        # taşıyamaz (cümle 'fallback'e ve künye alanına yazılır). Bu mandal
        # olmasaydı uzun künye parametreye geri sızabilirdi.
        for ad, deger in p.items():
            if isinstance(deger, str):
                assert ' ' not in deger.strip(), (ad, deger)
        # 'warnings' ile 'design_warnings' AYNI listedir — panel de görür.
        assert kayitlar[0] in bos_yol['warnings']
        # i18n anahtarı arayuz-i18n kulvarında; kayıt İngilizce cümlesini
        # KENDİ taşır (ZINCIR_BORCU imi kazanılmış olmalı), yoksa kullanıcı
        # ham anahtar görürdü.
        yedek = kayitlar[0].get('fallback') or ''
        assert 'include a two-phase' in yedek
        assert '{loss_percent}' in yedek and '{band_low_percent}' in yedek
        assert 'rather than a verified value' in yedek
        from tests.test_engine_warning_i18n import ZINCIR_BORCU
        # fix-35e (ana model, 15 Eyl 2026): borç ÖDENDİ — anahtar EN+TR
        # sözlükte (hrma/static/js/i18n_common.js), ZINCIR_BORCU imi kalktı.
        # İddia yön değiştirdi: im DURMAMALI, sözlük iki dilde TAŞIMALI.
        assert 'warn.solid.two_phase_correction_unverified' not in ZINCIR_BORCU
        import re as _re
        sozluk = open(os.path.join(os.path.dirname(__file__), '..', 'hrma',
                                   'static', 'js', 'i18n_common.js'),
                      encoding='utf-8').read()
        assert len(_re.findall(
            r"'warn\.solid\.two_phase_correction_unverified'\s*:", sozluk)) == 2, (
            'anahtar EN ve TR sözlükte birer kez tanımlı olmalı')

    def test_panel_durumu_Isp_kartlarinin_altinda_basar(self):
        """solid.html displayResults, metrik ızgarasının SONUNA durum
        bandını ekler ve metni çözücünün künyesinden alır."""
        html = _oku('hrma', 'templates', 'solid.html')
        assert 'function twoPhaseStatusBannerHTML' in html
        assert "metricsDiv.insertAdjacentHTML(" in html
        i_banner = html.index('twoPhaseStatusBannerHTML(results)')
        i_isp = html.index("'solid.msg.sea_level_isp'")
        assert i_isp < i_banner, 'band Isp kartlarindan SONRA gelmeli'
        kesit = html[html.index('function twoPhaseStatusBannerHTML'):
                     html.index('function twoPhaseDiagnosticHTML')]
        # Alan yoksa "doğrulandı" varsayılmaz (fail-closed).
        assert 'NOT PUBLISHED BY THE' in kesit
        assert 'two_phase correction NOT VERIFIED' in kesit
        assert 'two_phase_correction_status_basis' in kesit

    def test_kullanici_carpani_dogrulanmis_sayilmaz(self, istemci):
        from hrma.engines.solid_rocket_engine import TWO_PHASE_STATUS_USER
        j = _kos(istemci, two_phase_loss=0.98)
        tva = _tva(j)
        assert tva['two_phase_efficiency_applied'] == pytest.approx(0.98)
        assert tva['two_phase_correction_status'] == TWO_PHASE_STATUS_USER
        assert tva['two_phase_correction_verified'] is False
        assert 'user input, not a validated model result' in \
            tva['two_phase_correction_status_basis']

    def test_sifir_yogusmus_fazda_durum_DOGRULANMIS(self, istemci):
        """Tek doğrulanabilir hâl: β = 0. Burada uyarı kaydı da YAZILMAZ."""
        from hrma.engines.solid_rocket_engine import TWO_PHASE_STATUS_ZERO
        j = _kos(istemci, propellant_type='double_base')
        tva = _tva(j)
        assert tva['two_phase_losses'] == 0.0
        assert tva['two_phase_correction_status'] == TWO_PHASE_STATUS_ZERO
        assert tva['two_phase_correction_verified'] is True
        assert not [w for w in j['design_warnings'] if isinstance(w, dict)
                    and w.get('code') == 'warn.solid.two_phase_correction'
                                         '_unverified']

    def test_zarf_disi_kesir_extrapolasyon_diye_beyan_edilir(self, istemci):
        """knsu X_p = 0,44: modül SAYI ÜRETMİYOR (SP-8039 0-0,40
        penceresi); doğrusal teşhis de ARTIK ÜRETMİYOR.

        ÖH D33 · motorlar a1 (OH-D32-17) — BEKÇİ ÇEVRİLDİ, GEVŞETİLMEDİ.
        D32'de bu düğüm "%5,28 yayımlanıyor AMA durum beyan ediliyor"
        sözleşmesini kilitliyordu; yani KUSURU (pencere dışında sayı
        yayımlamayı) koruyan bir bekçiydi. Berke kararı 15 Eyl 2026
        (hüküm-21c, docs/scofield/raw/OH/D33/oturum-devri brief'i): teşhis
        SAYISI geri çekilsin (``None`` + gerekçe), beyan kalsın.

        İDDİA KORUNDU, yönü değişti: "aynı büyüklüğün iki ucu farklı
        davranıyorsa durum adıyla beyan edilir" hükmü artık DAHA GÜÇLÜ
        karşılanıyor — iki uç aynı durumda susuyor ve susmanın gerekçesi
        makine-okur bir alanda (``two_phase_losses_withheld_reason``)
        yayımlanıyor. Yeni sözleşmenin tam bekçisi
        ``tests/test_d33_motorlar_a1.py::
        TestOHD3217ZarfDisiTeshisGeriCekildi``tir; oradaki 5 yakıt için de
        ters-mutasyonla kırmızı görüldü
        (docs/scofield/raw/OH/D33/motorlar/a1/mutasyon.json · M3).
        """
        from hrma.engines.solid_rocket_engine import (
            TWO_PHASE_STATUS_OUT_OF_ENVELOPE)
        j = _kos(istemci, propellant_type='knsu')
        tva = _tva(j)
        blok = j['two_phase_loss']
        assert blok['status'] == 'OUT_OF_PUBLISHED_RANGE'
        assert blok['two_phase_loss_pct'] is None
        # ÖLÇÜLDÜ (a1/once.json K4, taban 56f88e70): burada 5,28 vardı.
        assert tva['two_phase_losses'] is None
        assert tva['two_phase_losses_withheld_reason'] == \
            'outside_anchor_envelope'
        assert tva['two_phase_correction_status'] == \
            TWO_PHASE_STATUS_OUT_OF_ENVELOPE
        assert tva['two_phase_correction_verified'] is False
        kunye = tva['two_phase_correction_status_basis']
        assert 'OUTSIDE the published data window' in kunye
        assert 'aluminium-oxide anchors' in kunye

    def test_zarf_penceresi_TEK_KAYNAKTAN_okunur(self):
        """0,40 sayısı ikinci kez yazılmaz; modülün kendi penceresidir."""
        from hrma.analysis.two_phase_loss import VALIDITY_RANGES
        from hrma.engines.solid_rocket_engine import (
            _two_phase_anchor_envelope)
        pencere, kaynak = _two_phase_anchor_envelope()
        assert pencere == tuple(
            float(v) for v in
            VALIDITY_RANGES['condensed_mass_fraction']['range'])
        assert 'SP-8039' in kaynak
        motor = _oku('hrma', 'engines', 'solid_rocket_engine.py')
        govde = motor[motor.index('def _two_phase_anchor_envelope'):
                      motor.index('def _two_phase_correction_state')]
        assert '0.40' not in govde and '0.4,' not in govde


# =====================================================================
# C) ÇÖZÜCÜ VARSAYILANI DEĞİŞMEDİ — uygulama kararı Berke'nin
# =====================================================================
class TestCVarsayilanDegismedi:
    """Berke kararı yazılana kadar çözücü varsayılanı DEĞİŞMEZ
    (berke_kararlari_2026-09-15.md §1 UYGULAMA satırı)."""

    def test_varsayilan_eta_bir_ve_Isp_tabandaki_sayi(self, bos_yol):
        # V307 KATI-DOĞRULAMA faz 3 (B1, 16 Kas 2026) — VARSAYILAN BİLİNÇLİ DEĞİŞTİ.
        # Eski (T-ÇAPA-A sonrası taban): eta 1,0 / applied False /
        # Isp 250,8498930866734 / vakum 277,96092362420086 s.
        # Yeni: modülün boyut düzeltmeli tahmini (%4,8698) uygulanır ->
        # eta 0,951301840236341, Isp 238,65299346641592 (-%4,86), vakum
        # 264,4247597381701 s. Bu test "varsayılan değişmedi"yi
        # kilitliyordu; şimdi B1'in sayısını ve iç tutarlılığını (uygulanan
        # çarpan = 1 - yayımlanan kayıp/100) kilitler.
        tva = _tva(bos_yol)
        kayip = bos_yol['two_phase_loss']['two_phase_loss_pct']
        assert tva['two_phase_efficiency_applied'] == pytest.approx(
            1.0 - kayip / 100.0, rel=1e-12)
        assert tva['two_phase_efficiency_applied'] == pytest.approx(
            0.951301840236341, rel=1e-12)
        assert tva['two_phase_losses_applied'] is True
        assert tva['two_phase_applied_source'] == 'module_estimate'
        assert bos_yol['two_phase_loss']['applied_to_isp'] is True
        assert bos_yol['isp_sea_level'] == pytest.approx(
            238.65299346641592, rel=1e-12)
        assert bos_yol['isp_vacuum'] == pytest.approx(
            264.4247597381701, rel=1e-12)

    def test_kayip_en_fazla_BIR_KEZ_uygulanir(self, istemci):
        """Kullanıcı çarpanı verildiğinde toplam nozul verimi TAM olarak
        bir kez düşer; modülün kaybı üstüne EKLENMEZ."""
        bos = _kos(istemci)
        kul = _kos(istemci, two_phase_loss=0.98)
        # V307 KATI-DOĞRULAMA faz 3 (B1, 16 Kas 2026): kullanıcı çarpanı modül tahmininin
        # YERİNE geçer. Eski iddia e1 == e0 x 0,98 idi (e0 o zaman tablo
        # verimiydi); şimdi e0 modül tahminini de taşır, bu yüzden doğru
        # iddia e1 == TABLO x 0,98'dir ve e1, e0 x 0,98 DEĞİLDİR (çarpım
        # olsaydı kayıp iki kez sayılırdı).
        tablo = bos['delivered_performance_basis'][
            'nozzle_efficiency_table']['value']
        e0 = _tva(bos)['nozzle_efficiency_applied']
        e1 = _tva(kul)['nozzle_efficiency_applied']
        assert e1 == pytest.approx(tablo * 0.98, rel=1e-12)
        assert e1 != pytest.approx(e0 * 0.98, rel=1e-6)
        assert e0 == pytest.approx(
            tablo * (1.0 - bos['two_phase_loss']['two_phase_loss_pct'] / 100.0),
            rel=1e-12)
        assert _tva(kul)['two_phase_applied_source'] == 'user_input'
        assert kul['two_phase_loss']['applied_to_isp'] is False
        assert bos['two_phase_loss']['two_phase_loss_pct'] > 0.0

    def test_uc_yolun_onceden_olculen_sayilari(self, istemci):
        """0,98 yolu ⟷ boş yol ⟷ aday model — Berke'nin karar tablosu
        (once.json Z2a/Z2b/Z2c). Sayılar KAYAR SA rapor bayatlar."""
        bos = _kos(istemci)
        kul = _kos(istemci, two_phase_loss=0.98)
        aday_eta = 1.0 - bos['two_phase_loss']['two_phase_loss_pct'] / 100.0
        aday = _kos(istemci, two_phase_loss=round(aday_eta, 6))
        # V307 KATI-DOĞRULAMA faz 3 (B1, 16 Kas 2026): boş yol artık karar tablosundaki
        # "aday model"in kendisidir. 0,98 yolu DEĞİŞMEDİ
        # (245,85152033355664: kullanıcı çarpanı modülün yerine geçer).
        # Boş yol 250,8498930866734 -> 238,65299346641592 s. Aday yolu
        # 238,68178089908514 -> 238,67803101839135 s: aday çarpanı boş yolun
        # yayımladığı kayıptan türetilir ve hedefli boyutlandırma artık kaybı
        # gördüğü için o kayıp %0,002 kaydı. İki yol %0,011 içinde aynı Isp'yi
        # verir (çarpanın 6 haneye yuvarlanması + boyutlandırmanın kabul
        # ettiği iterasyon). Eski tarihçe: 246,9758 / 251,9975 / 239,7895
        # (N-CEA-2 öncesi).
        assert kul['isp_sea_level'] == pytest.approx(245.85152033355664,
                                                     rel=1e-9)
        assert bos['isp_sea_level'] == pytest.approx(238.65299346641592,
                                                     rel=1e-9)
        assert aday['isp_sea_level'] == pytest.approx(238.67803101839135,
                                                      rel=1e-9)
        assert bos['isp_sea_level'] == pytest.approx(aday['isp_sea_level'],
                                                     rel=2e-4)
        # Aday yol (sabit kullanıcı çarpanı) hedef itkiye daha yakın oturur
        # ve yakıt kütlesi boş yoldan büyüktür: hedefli boyutlandırma %10
        # toleransla İLK kabul edilen iterasyonda durur (boş yol 4796,8 N,
        # aday 4938,3 N; hedef 5000 N).
        assert aday['propellant_mass'] > bos['propellant_mass']


# =====================================================================
# D) KANIT PAKETİ DOSYALARI — rapor iddiasız kalmaz
# =====================================================================
def test_kanit_dosyalari_yerinde():
    d = os.path.join(KOK, 'docs', 'scofield', 'raw', 'OH', 'D32', 'kati', 'a1')
    for ad in ('once.json', 'sonra.json', 'zincir_once.json',
               'capa_once.json', 'capa_sonra.json', 'mutasyon.json',
               'rapor.md'):
        assert os.path.exists(kanit_gerekli(os.path.join(d, ad))), ad
    m = json.load(open(kanit_gerekli(os.path.join(d, 'mutasyon.json')), encoding='utf-8'))
    assert m['md5_esit'] is True
    assert all(k['kirmizi'] for k in m['kalemler'])
