# -*- coding: utf-8 -*-
"""OH D28 / arayuz asama-4 bekcileri — P11/P12B onarimlari.

Onbir kalem: dokuzu onarildi, ikisi olcumle curutuldu (curutulen ikisi de
yeniden acilmasin diye kilitlenir). Her bekci onarimin SEMBOLUNU dogrudan
sinar; ters-mutasyon kanitlari docs/scofield/raw/OH/D28/arayuz/a4/.

Not (D27 dersi 10): bu dosyadaki butun tanimlayici ve dugum adlari ASCII.
"""
import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
ADV = KOK / 'hrma/templates/advanced.html'
FX = KOK / 'hrma/templates/formulas.html'
LS = KOK / 'hrma/templates/launch_site.html'
IDX = KOK / 'hrma/templates/index.html'
APPJS = KOK / 'hrma/static/js/app.js'
I18N_ADV = KOK / 'hrma/static/js/i18n_advanced.js'
I18N_COMMON = KOK / 'hrma/static/js/i18n_common.js'
I18N_LS = KOK / 'hrma/static/js/i18n_launch_site.js'
SIXDOF = KOK / 'hrma/analysis/six_dof_trajectory.py'
HEAT = KOK / 'hrma/analysis/heat_transfer_analysis.py'
STRUCT = KOK / 'hrma/analysis/structural_analysis.py'


def metin(p: Path) -> str:
    return p.read_text(encoding='utf-8')


def yorumsuz(s: str) -> str:
    """HTML yorumlarini soker — yorum kullaniciya cizilmez.

    Bekciler sayfanin GORUNEN metnini olcer; onarim yorumlari (eski kusuru
    anlatan aciklamalar) olcume girmemeli, yoksa bekci kendi yorumunu
    kusur sanip yesil kalir.
    """
    return re.sub(r'<!--.*?-->', '', s, flags=re.S)


def kodsuz_yorum(s: str) -> str:
    """HTML yorumlari + JS satir yorumlari silinmis metin.

    Onarim yorumlari eski kusuru ADIYLA anlatir ("eskiden 'UZAYTEK_Motor'
    yedegine dusuyordu"); bekci bunlari kod sanarsa kendi aciklamasini
    kusur olarak raporlar. Yalniz CALISAN metin olculur.
    """
    s = yorumsuz(s)
    return '\n'.join(ln for ln in s.splitlines()
                     if not ln.lstrip().startswith('//'))


def bolum(s: str, bas_id: str, son_id: str) -> str:
    i = s.find('id="%s"' % bas_id)
    assert i >= 0, 'bolum bulunamadi: %s' % bas_id
    j = s.find('id="%s"' % son_id, i + 1)
    return s[i:j if j > 0 else len(s)]


def i18n_ciftli(yol: Path, anahtar: str) -> int:
    """Anahtarin EN ve TR bloklarinda kac kez gectigi."""
    return len(re.findall(r"'%s'\s*:" % re.escape(anahtar), metin(yol)))


# ======================================================================
# P12bB3-20 — disa aktarim adinin TEK cozucusu
# ======================================================================
class TestB320ExportName:
    def test_ham_motor_name_yedegi_kalmadi(self):
        """`motor.motor_name || '<literal>'` kaliplarinin tamami soküldü."""
        s = yorumsuz(metin(ADV))
        kalan = re.findall(
            r"(?:currentResults\.)?motor\.motor_name\s*\|\|\s*"
            r"(?:formVal\([^)]*\)\s*\|\|\s*)?'([^']+)'", s)
        assert kalan == [], (
            'ad cozumu yine yedege dusuyor; kalan literaller: %r' % kalan)

    #: OK-21 KILIDI: bu iki satir FORM KATMANI varsayilanidir (yukte
    #: motor_name alani). Form value/|| sokumu bu dalgada YASAK, o yuzden
    #: literal yerinde kalir. Envanter KUME olcusudur (D27 dersi 11):
    #: yeni bir disa-aktarim literali eklenirse kume buyur ve bekci duser.
    OK21_FORM_KATMANI = {
        "motor_name: document.getElementById('motor_name').value "
        "|| 'HRMA_Motor',",
        "motor_name: document.getElementById('motor_name').value "
        "|| 'HRMA_Motor'",
    }

    def test_tek_yedek_literali(self):
        """Yedek ad TEK yerde tanimli; disa aktarimda eski literal yok."""
        s = kodsuz_yorum(metin(ADV))
        assert s.count("const EXPORT_MOTOR_NAME_FALLBACK = 'HRMA_Motor';") == 1
        assert "'HRMA_motor'" not in s, "eski yedek literali geri geldi"
        kalan = {ln.strip() for ln in s.splitlines()
                 if "'HRMA_Motor'" in ln
                 and 'EXPORT_MOTOR_NAME_FALLBACK' not in ln}
        assert kalan == self.OK21_FORM_KATMANI, (
            'HRMA_Motor literali beklenmeyen yerde: %r'
            % (kalan - self.OK21_FORM_KATMANI))

    def test_bes_cagri_yeri_tek_cozucuden_geciyor(self):
        """STL / regresyon / PDF / STL-zip / DXF-STEP-ENG hepsi ayni cozucude."""
        s = yorumsuz(metin(ADV))
        # ÖH 15 Eki (ana model) — dört koşulla çevrildi: (1) STL çağrı yeri
        # hiçbir düğmeye bağlı olmayan exportMotorSTL içindeydi; CADK D-T6-3
        # (322ab002f, 14 Eki) ölçüp ölü kod olarak söktü; (2) kâhin: söküm —
        # işlev de /api/export-stl çağrısı da şablonda YOK, kalan dört çağrı
        # yeri aşağıda aynı çözücüden geçer; (3) tolerans yok; (4) rapor
        # docs/scofield/raw/OH/V3/yayin/kapi/birlesik_supurme_15eki.md.
        assert 'function exportMotorSTL' not in s
        assert "'/api/export-stl'" not in s
        assert 'const motorName = disaAktarimMotorAdi(motor);' in s
        assert 'const name = disaAktarimDosyaAdi();' in s
        assert '`${disaAktarimDosyaAdi()}_STL_package.zip`' in s
        assert re.search(r'function _motorName\(\)\s*\{[^}]*'
                         r'return disaAktarimDosyaAdi\(\);', s, re.S)

    def test_cozucu_design_summary_title_yolunu_koruyor(self):
        """Hibrit yanitta motor_name YOK; ad design_summary.title'dan gelir."""
        s = metin(ADV)
        assert re.search(
            r'function disaAktarimMotorAdi\(m\)\s*\{.*?motorNameOf\(kaynak\)',
            s, re.S), 'disaAktarimMotorAdi artik motorNameOf cagirmiyor'
        assert re.search(r"function motorNameOf\(m\).*?design_summary.*?title",
                         s, re.S)

    def test_form_alani_ikinci_basamak(self):
        """Cozucu ad vermezse kullanicinin forma yazdigi ad kullanilir."""
        s = metin(ADV)
        govde = re.search(r'function disaAktarimMotorAdi\(m\)(.*?)\n        \}',
                          s, re.S).group(1)
        assert "getElementById('motor_name')" in govde


# ======================================================================
# P12bB3-22 — kosulsuz "tum parametreler optimize" hukmu
# ======================================================================
class TestB322DesignValidation:
    def test_kosulsuz_iddia_sablonda_yok(self):
        s = yorumsuz(metin(ADV))
        assert 'adv.txt.allParametersOptimizedStableCombustion' not in s, (
            'kosulsuz olumlu dogrulama hukmu sablona geri geldi')

    def test_canli_dugum_var(self):
        s = yorumsuz(metin(ADV))
        assert 'id="design_validation_verdict"' in s
        assert 'adv.txt.designValidationPending' in s

    def test_hukmu_sunucu_yaziyor(self):
        """Panel kendi hukmunu URETMEZ: metin validation.overall_status'tan."""
        a = metin(APPJS)
        assert 'function setDesignValidationVerdict(validation)' in a
        govde = re.search(
            r'function setDesignValidationVerdict\(validation\)(.*?)\n\}',
            a, re.S).group(1)
        assert 'warnToText(validation.overall_status)' in govde
        assert 'app.warn.validationNotPublished' in govde, (
            'sunucu hukum yayimlamadiginda olumlu bir sey yazilmamali')

    def test_yazici_displayWarnings_basinda_cagriliyor(self):
        """Uyari YOKKEN de dugum guncellenmeli (erken return'den ONCE)."""
        a = metin(APPJS)
        m = re.search(r'function displayWarnings\(warnings, validation\)\s*\{'
                      r'(.*?)const warningsPanel', a, re.S)
        assert m and 'setDesignValidationVerdict(validation);' in m.group(1)

    def test_i18n_ciftleri_tam(self):
        assert i18n_ciftli(I18N_ADV, 'adv.txt.designValidationPending') == 2
        assert i18n_ciftli(I18N_COMMON, 'app.warn.validationNotPublished') == 2


# ======================================================================
# P12bB3-23 — Tasarim Modu kaydiricilari forma geri yaziyor
# ======================================================================
class TestB323DesignSliderWriteback:
    ALANLAR = ('chamber_diameter_input', 'l_star', 'expansion_ratio')

    def test_uc_alan_da_forma_yaziliyor(self):
        s = metin(ADV)
        govde = re.search(r'async function vizDesignApply\(\)(.*?)\n        \}\n',
                          s, re.S).group(1)
        for alan in self.ALANLAR:
            assert "formaYazDesign('%s'" % alan in govde, (
                '%s forma yazilmiyor: onizleme ile CALCULATE ayrisir' % alan)

    def test_yazma_yalniz_basarili_onizlemeden_sonra(self):
        """Kabul edilmemis geometri forma sizmamali."""
        s = metin(ADV)
        govde = re.search(r'async function vizDesignApply\(\)(.*?)\n        \}\n',
                          s, re.S).group(1)
        i_kapi = govde.find("if (r.status === 'success' && r.motor)")
        i_yaz = govde.find("formaYazDesign('chamber_diameter_input'")
        assert 0 <= i_kapi < i_yaz, (
            'forma yazma basari kapisinin disinda kalmis')

    def test_yazici_sayi_uydurmuyor(self):
        s = metin(ADV)
        govde = re.search(r'function formaYazDesign\(alanId, deger\)(.*?)\n        \}',
                          s, re.S).group(1)
        assert 'if (!el) return false;' in govde
        assert 'isFinite(deger)' in govde
        assert 'dispatchEvent' in govde, (
            'alana bagli dinleyiciler haberdar edilmeli')


# ======================================================================
# P12bB3-25 — uydurma cevrimdisi ozellik tablosu
# ======================================================================
class TestB325OxidizerFallback:
    def test_uydurma_tablo_sokuldu(self):
        s = yorumsuz(metin(ADV))
        assert not re.search(r"'n2o'\s*:\s*\{\s*density:\s*1004", s), (
            'uydurma cevrimdisi ozellik tablosu geri geldi')
        assert '0.000158' not in s, (
            'sunucu veri tabanindan %43,6 sapan viskozite yedegi geri geldi')

    def test_yedekten_alana_yazan_satir_yok(self):
        """Alana yazmak `value != defaultValue` yapip uydurma sayiyi
        KULLANICI GIRDISI'ne cevirip cozucuye gonderiyordu."""
        s = yorumsuz(metin(ADV))
        assert not re.search(
            r'(?:densityInput|viscosityInput)\.value\s*=\s*fallback\.', s)

    def test_fail_closed_mesaji_var(self):
        s = yorumsuz(metin(ADV))
        assert 'adv.msg.oxPropsUnresolved' in s
        assert i18n_ciftli(I18N_ADV, 'adv.msg.oxPropsUnresolved') == 2

    def test_viskozite_kullanici_girdisi_kapisi_duruyor(self):
        """Dokunulmamis alan null gider — cozucu kendi tablosundan cozer."""
        s = metin(ADV)
        govde = re.search(r'function viskoziteGovdeDegeri\(\)(.*?)\n        \}',
                          s, re.S).group(1)
        assert 'viskoziteKullaniciGirdisiMi(el)' in govde
        assert 'return null' in govde


# ======================================================================
# P12bB4-02 — /formulas §8.2 emniyet katsayisi
# ======================================================================
class TestB402SafetyFactor:
    def test_sigma_ultimate_tanimi_kalmadi(self):
        s82 = bolum(yorumsuz(metin(FX)), 'structural-analysis',
                    'trajectory-analysis')
        assert '\\sigma_{ultimate}' not in s82, (
            'sayfa yine ultimate dayanimla SF tanimliyor (4,75x iyimser)')

    def test_derate_edilmis_akma_gosteriliyor(self):
        s82 = bolum(yorumsuz(metin(FX)), 'structural-analysis',
                    'trajectory-analysis')
        assert '\\sigma_{yield}(T_{wall})' in s82
        assert 'k_{derate}' in s82

    def test_tasarim_basinci_katsayisi_yaziyor(self):
        s82 = bolum(yorumsuz(metin(FX)), 'structural-analysis',
                    'trajectory-analysis')
        assert 'P_{design}' in s82 and 'K_{design}' in s82

    def test_urun_tarafi_hala_derate_edilmis_akma(self):
        """Sayfa urune bagli: urun tanimi degisirse bu bekci de dusmeli."""
        u = metin(STRUCT)
        assert re.search(
            r'hoop_safety_factor\s*=\s*yield_for_design\s*/\s*hoop_stress', u)
        assert "derating['derated_yield_strength']" in u

    def test_olculen_oran_sayfada_yaziyor(self):
        s82 = bolum(yorumsuz(metin(FX)), 'structural-analysis',
                    'trajectory-analysis')
        assert '4.75' in s82, 'olculen sapma sayfada adiyla durmali'


# ======================================================================
# P12bB4-04 — yerel yercekimi (CURUTULDU: cozucu artik okuyor)
# ======================================================================
class TestB404LocalGravity:
    """Kalem basligi ('6-DOF g_surface'i bir kez bile okumuyor') olcumle
    CURUTULDU: turevdeki yercekimi satiri artik self.g_surface'ten geliyor.
    Bekci tuketimi KILITLER — regresyon sayfayi yine yalanci yapardi."""

    def test_g_surface_turevde_tuketiliyor(self):
        kod = [ln for ln in metin(SIXDOF).splitlines()
               if not ln.lstrip().startswith('#')]
        okuma = [ln for ln in kod
                 if 'g_surface' in ln
                 and not re.search(r'^\s*self\.g_surface\s*=', ln)]
        assert okuma, 'g_surface yine hicbir yerde okunmuyor'
        assert any(re.search(r'g\s*=\s*self\.g_surface\s*\*', ln)
                   for ln in okuma), (
            'turevdeki yercekimi satiri yine sabit G0 kullaniyor')

    def test_agirlik_da_yerel_yercekiminden(self):
        kod = '\n'.join(ln for ln in metin(SIXDOF).splitlines()
                        if not ln.lstrip().startswith('#'))
        assert re.search(r'float\(self\.g_surface\)', kod)

    def test_sayfa_satiri_duruyor(self):
        """Sayfa yerel yercekimini basmaya devam etmeli (artik dogru)."""
        assert 'ls-r-glocal' in metin(LS)


# ======================================================================
# P12bB4-05 — sessiz ruzgar
# ======================================================================
class TestB405Wind:
    def test_sabit_ruzgar_yukten_kalkti(self):
        s = yorumsuz(metin(LS))
        assert not re.search(r'wind_speed:\s*6\b', s), (
            'beyansiz 6 m/s ruzgar geri geldi (yanal surukleme 2,32x)')

    def test_ruzgar_panelde_soruluyor(self):
        s = yorumsuz(metin(LS))
        assert s.count('id="ls-a-windspeed"') == 1
        assert s.count('id="ls-a-winddir"') == 1

    def test_yuk_alanlardan_okuyor(self):
        s = yorumsuz(metin(LS))
        assert "wind_speed: fieldNum('ls-a-windspeed'" in s
        assert "wind_direction_deg: fieldNum('ls-a-winddir'" in s

    def test_varsayilan_ruzgarsiz(self):
        """Sayfa kendiliginden yanal yuk uydurmaz."""
        s = yorumsuz(metin(LS))
        assert re.search(r'id="ls-a-windspeed"[^>]*value="0"', s)

    def test_kalan_govde_sabitleri_beyan_edildi(self):
        s = yorumsuz(metin(LS))
        i = s.find('id="ls-notes"')
        notlar = s[i:i + 6000]
        assert 'id="ls-fixed-airframe-note"' in notlar, (
            'Barrowman marjina giren bes sabit yine beyansiz')
        assert "tf('site.fixedAirframeNote'" in s, (
            'not artik parametreli basilmiyor')

    def test_notun_sayilari_yukun_nesnesinden_geliyor(self):
        """OH D33-KOLAY / P12bB4-05 denetim SARTI.

        Bes sabit TEK nesnede (``LS_FIXED_AIRFRAME``) yasar; hem ucus yuku
        hem beyan notu AYNI nesneden okur. Onceden sayilar iki yerde
        yaziliydi -- yukte gomulu degismez, notun EN/TR metninde gomulu
        metin; biri degisirse ekrandaki beyan sessizce yalan olurdu.
        """
        s = yorumsuz(metin(LS))
        m = re.search(r'var LS_FIXED_AIRFRAME = \{(.*?)\};', s, re.S)
        assert m, 'LS_FIXED_AIRFRAME tek kaynagi yok'
        nesne = m.group(1)
        # ÖH D33-KOLAY · ikinci tur: eskiden yukun nesneden okudugu TUM
        # DOSYADA aranıyordu. Notu basan `renderFixedAirframeNote` de ayni
        # sembolleri kullandigi icin, YUK sabiti yeniden gomulse bile arama
        # notta karsiligini bulup YESIL kaliyordu (olculdu: mutasyon M5a
        # `nose_length: 0.50` ile bekci kirmizi OLMADI). Artik yalnizca
        # ucus yuku nesnesinin GOVDESI olculur.
        mb = re.search(r'var body = \{(.*?)\n        \};', s, re.S)
        assert mb, 'ucus yuku nesnesi bulunamadi'
        yuk = mb.group(1)
        for ad, deger in (('nose_length', '0.50'), ('fin_root_chord', '0.20'),
                          ('fin_tip_chord', '0.10'), ('fin_sweep', '0.08'),
                          ('rail_length', '5')):
            assert re.search(r'%s:\s*%s\b' % (ad, re.escape(deger)), nesne), (
                '%s tek kaynakta %s degil' % (ad, deger))
            # Yuk artik sayiyi gomulu tasimaz, NESNEDEN okur.
            assert re.search(r'\b%s:\s*LS_FIXED_AIRFRAME\.%s\b' % (ad, ad),
                             yuk), (
                '%s ucus yukune yine gomulu sayi olarak yaziliyor: tek '
                'kaynak ile ekrandaki beyan ayrisabilir' % ad)
        # Not, yuk ile AYNI nesneden basilir; yer tutuculara baglidir.
        m2 = re.search(r'function renderFixedAirframeNote\(\)(.*?)\n    \}',
                       s, re.S)
        assert m2, 'renderFixedAirframeNote yok'
        basici = m2.group(1)
        for alan in ('nose_length', 'fin_root_chord', 'fin_tip_chord',
                     'fin_sweep', 'rail_length'):
            assert 'LS_FIXED_AIRFRAME.%s' % alan in basici, (
                'not %s alanini yukun nesnesinden okumuyor' % alan)
        # EN/TR metinlerde gomulu sayi KALMADI; bes yer tutucu var.
        sozluk = metin(I18N_LS)
        for m3 in re.finditer(r"'site\.fixedAirframeNote': '([^']*)'", sozluk):
            metni = m3.group(1)
            assert set(re.findall(r'\{(\w+)\}', metni)) == {
                'nose', 'root', 'tip', 'sweep', 'rail'}, metni
            # \uXXXX kacislari sayi icerir; once onlar cozulur.
            duz = re.sub(r'\\u[0-9a-fA-F]{4}', 'X', metni)
            assert not re.search(r'\d', duz), (
                'beyan metninde hala gomulu sayi var: %s' % metni)

    def test_i18n_ciftleri_tam(self):
        for k in ('site.windSpeed', 'site.windDir', 'site.fixedAirframeNote'):
            assert i18n_ciftli(I18N_LS, k) == 2, 'EN/TR eksik: %s' % k


# ======================================================================
# P12bB4-06 — §7 isi transferi / §5.3 sogutucu
# ======================================================================
class TestB406HeatTransfer:
    def test_s7_bartz_aniyor(self):
        s7 = bolum(yorumsuz(metin(FX)), 'heat-transfer', 'structural-analysis')
        assert 'Bartz' in s7, 'gaz tarafi yine Bartz\'i anmiyor'

    def test_s7_dittus_boelter_gaz_tarafinda_degil(self):
        s7 = bolum(yorumsuz(metin(FX)), 'heat-transfer', 'structural-analysis')
        assert '0.023' not in s7, (
            'gaz tarafi yine Dittus-Boelter gosteriyor (1,37-1,41x sapma)')

    def test_s7_bartz_bicimi_urunle_ayni(self):
        s7 = bolum(yorumsuz(metin(FX)), 'heat-transfer', 'structural-analysis')
        assert '0.026' in s7 and 'D_t^{0.2}' in s7
        assert 'c^*' in s7, 'Bartz kutle akisi terimi eksik'

    def test_surukleyici_sicaklik_adyabatik_cidar(self):
        s7 = bolum(yorumsuz(metin(FX)), 'heat-transfer', 'structural-analysis')
        assert 'T_{aw}' in s7
        assert not re.search(r'\$q = h\(T_\{gas\} - T_\{wall\}\)\$', s7), (
            'gaz tarafi kutusu yine durgunluk sicakligi kullaniyor')

    def test_s53_sabit_katsayi_beyan_edildi(self):
        s5 = bolum(yorumsuz(metin(FX)), 'liquid-propellant', 'hybrid-motors')
        s53 = s5[s5.find('5.3 Cooling System'):]
        assert 'fx.s5_3.model_note' in s53
        assert '20000' in s53, 'rejeneratif sabit adiyla yazilmali'

    def test_urun_tarafi_bartz_ve_kunyeli_sogutucu(self):
        """Sayfa urune bagli; urun degisirse bu bekci dusmeli.

        OH D31 / P12bB4-06 (termo-ucus a1) — BEKCI CEVRILDI. Eski hali
        ``assert 'return 20000.0' in h`` idi: kusurun KENDISINI (soguutucu
        tarafinin sabit donmesi) urunde CIVILIYORDU; onarim bu satiri
        zorunlu olarak kirmizi yapardi. Olculen kusur ve onarim:
        once/sonra_p12bb406.json — kanal girdileri verildiginde katsayi
        artik Dittus-Boelter ile hesaplanir (dort tasarimda 6.639,7 /
        8.828,3 / 14.666,9 / 77.412,6 W/m2K), girdiler yoksa beyan edilen
        bant 'not_modelled' kunyesiyle doner. Bekcinin AMACI korundu:
        sayfa ile urunun sozlesmesi ayni kalmali.
        """
        h = metin(HEAT)
        assert 'def _bartz_coefficient' in h
        assert 'def _adiabatic_wall_temperature' in h
        assert 'COOLANT_SIDE_DECLARED_TYPICAL' in h
        assert "'not_modelled'" in h, (
            'soguutucu tarafi kunyesiz donuyor')
        assert 'def _coolant_side_dittus_boelter' in h, (
            'kanal girdileriyle korelasyon yolu yok')


# ======================================================================
# P12bB4-08 — §14 ICINDEKILER'de yoktu
# ======================================================================
class TestB408TableOfContents:
    def test_toc_madde_sayisi_bolum_sayisina_esit(self):
        s = yorumsuz(metin(FX))
        toc = s[s.find('<div class="toc">'):s.find('<!-- Section 1')]
        h2 = len(re.findall(r'<h2 ', s))
        madde = len(re.findall(r'<li><a href="#', toc))
        assert madde == h2, ('ICINDEKILER %d madde, sayfada %d bolum'
                             % (madde, h2))

    def test_s14_toc_maddesi_var(self):
        s = yorumsuz(metin(FX))
        toc = s[s.find('<div class="toc">'):s.find('<!-- Section 1')]
        assert 'href="#nasa-standards"' in toc

    def test_model_farki_isareti_toc_altinda(self):
        s = yorumsuz(metin(FX))
        assert 'fx.toc.modelGapNotice' in s

    def test_hedef_bolum_gercekten_var(self):
        assert 'id="nasa-standards"' in metin(FX)


# ======================================================================
# P12bB4-09 — "NASA CEA Validated" rozeti (CURUTULDU)
# ======================================================================
class TestB409CeaBadge:
    """Kalem basliginin iki ayagi da olcumle CURUTULDU: rozet metni
    index.html'den kalkmis, iddia-lint kurali da sozcuk sirasini artik
    yakaliyor. Bekci ikisini de kilitler."""

    def test_rozette_dogrulama_iddiasi_yok(self):
        s = yorumsuz(metin(IDX))
        assert 'NASA CEA Validated' not in s
        assert 'CEA Validated' not in s

    def test_lint_kurali_sozcuk_sirasini_yakaliyor(self):
        import sys
        sys.path.insert(0, str(KOK))
        try:
            from tools import iddia_lint as il
        finally:
            if str(KOK) in sys.path:
                sys.path.remove(str(KOK))
        for ornek in ('NASA CEA Validated', 'NASA CEA Dogrulamali',
                      'NASA-validated'):
            vurus = [r.rule_id for r in il.ALL_RULES
                     if re.search(r.pattern, ornek, re.I)]
            assert vurus, 'iddia-lint kacirdi: %r' % ornek

    def test_index_lint_temiz(self):
        import sys
        sys.path.insert(0, str(KOK))
        try:
            from tools import iddia_lint as il
            bulgu = il.scan_file(str(IDX))
        finally:
            if str(KOK) in sys.path:
                sys.path.remove(str(KOK))
        assert bulgu == [], 'giris sayfasinda yasak iddia: %r' % bulgu


# ======================================================================
# P12bB4-10 — /launch-site surum yayimlamiyordu
# ======================================================================
class TestB410LaunchSiteVersion:
    def test_surum_yayimlaniyor(self):
        s = metin(LS)
        assert "window.HRMA_APP_VERSION = '{{ app_version }}';" in s

    def test_ikinci_surum_sabiti_yazilmadi(self):
        """Surum yalniz baglam isleyicisinden gelir (tek kaynak)."""
        s = yorumsuz(metin(LS))
        assert not re.search(r"HRMA_APP_VERSION\s*=\s*'\d+\.\d+", s), (
            'sayfaya elle surum sabiti yazilmis')

    def test_guncelleme_denetimi_yuklu(self):
        assert '/static/js/update_check.js' in metin(LS)

    def test_surum_betigi_bug_report_ten_once(self):
        """detectVersion() zinciri window.HRMA_APP_VERSION'i bulabilmeli."""
        s = metin(LS)
        i_ver = s.find('window.HRMA_APP_VERSION')
        i_bug = s.find('/static/js/bug_report.js')
        assert 0 <= i_ver < i_bug


@pytest.mark.parametrize('yol', [
    ADV, FX, LS, IDX, APPJS, I18N_ADV, I18N_COMMON, I18N_LS])
def test_dokunulan_dosyalar_duruyor(yol):
    assert yol.exists() and yol.stat().st_size > 0
