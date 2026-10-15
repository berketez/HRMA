# -*- coding: utf-8 -*-
"""ÖH Dalga-28 · arayuz · aşama 3/4 — bekçiler.

Kapsam (11 kalem): P12bB2-13/-14/-15/-16/-17/-18/-19 ve
P12bB3-06/-09/-14/-17. Her bekçi ters-mutasyonla kırmızı görülmüştür
(kanıt: ``docs/scofield/raw/OH/D28/arayuz/a3/mutasyon.json``).

Bekçi sınıfı 1 (test-yok) kalemlerdi: bu dosya o boşluğu kapatır.
"""
import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
SOLID = KOK / 'hrma' / 'templates' / 'solid.html'
ADV = KOK / 'hrma' / 'templates' / 'advanced.html'
APPJS = KOK / 'hrma' / 'static' / 'js' / 'app.js'
I18NP = KOK / 'hrma' / 'static' / 'js' / 'i18n_pages.js'


def metin(p: Path) -> str:
    return p.read_text(encoding='utf-8')


def govde(kaynak: str, ad: str) -> str:
    """``function ad(...) { ... }`` gövdesini parantez sayımıyla çıkarır."""
    m = re.search(r'(?m)^\s*(?:async\s+)?function\s+' + re.escape(ad) + r'\s*\(',
                  kaynak)
    if not m:
        return ''
    i = kaynak.find('{', m.end())
    if i < 0:
        return ''
    derinlik, j = 0, i
    while j < len(kaynak):
        if kaynak[j] == '{':
            derinlik += 1
        elif kaynak[j] == '}':
            derinlik -= 1
            if derinlik == 0:
                return kaynak[i:j + 1]
        j += 1
    return kaynak[i:]


# ---------------------------------------------------------------- B2-13
class TestB213TaneTipiIpucu:
    """Tane BİÇİMİ tek başına itki profilini belirlemez.

    ÖLÇÜLDÜ (a3/once_kosum.json): aynı varsayılan motorda çözücünün
    ``grain_design.burn_profile`` hükmü star = 'progressive-regressive',
    end_burner = 'neutral'. Şablonun ipucu ise "Star: ... for progressive
    thrust" ve "Wagon Wheel: ... for regressive thrust" diyordu; bulgunun
    işaret ettiği ikinci adres (Thrust Curve yardımı) OH-D23-08 ile zaten
    çözücü hükmüne bağlanmıştı, bu ipucu ise ayakta kalmıştı.
    """

    def test_tane_ipucu_kosulsuz_profil_iddia_etmez(self):
        s = metin(SOLID)
        assert not re.search(
            r'BATES[^<]{0,40}neutral[^<]{0,80}[Ss]tar[^<]{0,40}progressive', s), (
            'Tane tipi ipucu biçim -> itki profili eşlemesini koşulsuz iddia '
            'ediyor; çözücü aynı koşumda star için progressive-regressive diyor.')

    def test_ipucu_hukmu_cozucuye_havale_eder(self):
        s = metin(SOLID)
        m = re.search(r'solid\.ui\.geometric_configuration_of_the_solid_propellant">'
                      r'([^<]*)</span>', s)
        assert m, 'tane tipi ipucu bulunamadı'
        assert 'classified by the solver' in m.group(1), (
            'İpucu, profilin çözücü tarafından sınıflandırıldığını söylemeli.')

    def test_i18n_en_ve_tr_ayni_hukmu_tasir(self):
        j = metin(I18NP)
        satırlar = [ln for ln in j.splitlines()
                    if 'solid.ui.geometric_configuration_of_the_solid_propellant' in ln]
        assert len(satırlar) == 2, satırlar
        assert 'progressive thrust' not in satırlar[0]
        assert 'artan itki' not in satırlar[1]

    def test_cozucu_hukmu_kabi_durur(self):
        # OH-D23-08 onarımı geri gelmesin diye kilitlenir.
        assert metin(SOLID).count('solid_burn_profile_line') >= 2


# ---------------------------------------------------------------- B2-14
class TestB214IrtifaEpsilonBeyani:
    """İrtifa eğrisi her satırda BAŞKA bir lüleyi çiziyor; ε kırpması var.

    ÖLÇÜLDÜ (a3/once_kosum.json): 8 satırın 3'ü kırpık, kırpılmamış
    optimum ε = 2046,84, tasarım ε = 7,00, eğri aralığı 7,00 -> 500.
    Şablonda ``expansion_ratio_clamped`` / ``_uncapped`` / ``_basis``
    geçiş sayısı 0 idi.
    """

    def test_kirpma_alanlari_okunur(self):
        s = metin(SOLID)
        for alan in ('expansion_ratio_clamped', 'expansion_ratio_uncapped',
                     'expansion_ratio_basis'):
            assert s.count(alan) >= 1, alan

    def test_beyan_islevi_grafige_bagli(self):
        s = metin(SOLID)
        assert 'renderAltitudeEpsilonBasis(results.altitude_performance' in s
        g = govde(s, 'renderAltitudeEpsilonBasis')
        assert g, 'renderAltitudeEpsilonBasis tanımı yok'
        assert 'altitude_epsilon_basis' in g
        # Metin SUNUCUDAN gelir: künye dizesi birebir basılır.
        assert 'expansion_ratio_basis' in g

    def test_alan_yoksa_sayi_uydurulmaz(self):
        g = govde(metin(SOLID), 'renderAltitudeEpsilonBasis')
        assert "=== true" in g, 'kırpma bayrağı katı denetimle okunmalı'
        assert 'isFinite' in g, 'sayı doğrulaması olmadan basım yapılmamalı'

    def test_i18n_anahtarlari_en_ve_tr(self):
        j = metin(I18NP)
        for k in ('solid.js.altitude_eps_per_row', 'solid.js.altitude_eps_clamped',
                  'solid.js.altitude_eps_uncapped'):
            assert j.count("'%s'" % k) == 2, k


# ---------------------------------------------------------------- B2-15
class TestB215SayfaVarsayilanlari:
    """Sayfanın kendi varsayılanlarının doğurduğu uyarılar.

    ÖLÇÜLDÜ (a3/once_kosum.json, bu ağaç): varsayılan formla 6 uyarı
    çıkıyor ve bulgunun saydığı üçünden İKİSİ artık yok
    (``erosive_k_overridden`` ve ``temp_coeff_overridden`` kodları uyarı
    kümesinde geçmiyor). Kalan tek kalem ``case_volume_inconsistent``tir
    ve kaynağı ``chamber_volume`` form varsayılanıdır — ÖK-21 gereği form
    katmanı bu dalgada sökülmez. Bekçi, GERİLEMEYİ kilitler: iki uyarı
    geri gelemez.
    """

    UYARI_KODLARI = None

    @classmethod
    def _uyarilar(cls):
        if cls.UYARI_KODLARI is None:
            import os
            os.environ.setdefault('HRMA_HEADLESS', '1')
            from hrma.app import app
            c = app.test_client()
            d = c.post('/calculate_solid', json={
                'motor_name': 'Test', 'propellant_type': 'apcp',
                'grain_type': 'bates', 'chamber_diameter': 100,
                'grain_length': 500, 'core_diameter': 30,
                'chamber_pressure': 50, 'expansion_ratio': 8,
                'erosive_k': 0.0002, 'erosive_m': 0.8, 'temp_coeff': 0.002,
                'chamber_volume': 2.5, 'char_velocity': 1550,
            }).get_json() or {}
            cls.UYARI_KODLARI = sorted(
                {(u.get('code') or u.get('key') or '') for u in (d.get('warnings') or [])
                 if isinstance(u, dict)})
        return cls.UYARI_KODLARI

    def test_yakit_tablosu_ezme_uyarilari_geri_gelmez(self):
        kodlar = self._uyarilar()
        assert 'warn.solid.erosive_k_overridden' not in kodlar, kodlar
        assert 'warn.solid.temp_coeff_overridden' not in kodlar, kodlar

    def test_kalan_kalem_ok21_ile_kayitli(self):
        # Kalan tek varsayılan kaynaklı uyarı BELGELİDİR; sessizce
        # kaybolursa (ya da çoğalırsa) bu bekçi konuşur.
        kodlar = self._uyarilar()
        assert 'warn.solid.case_volume_inconsistent' in kodlar, (
            'ÖK-21 kaydı bayatladı: chamber_volume varsayılanı artık uyarı '
            'doğurmuyorsa defter kalemi güncellenmelidir.')
        s = metin(SOLID)
        m = re.search(r'id="chamber_volume"[^>]*value="([^"]*)"', s)
        assert m and m.group(1) == '2.5', (
            'ÖK-21 form katmanı bu dalgada sökülmez; değiştiyse kalem yeniden '
            'ölçülmelidir.')


# ---------------------------------------------------------------- B2-16
class TestB216RuzgarHizi:
    """Sayfanın sorduğu rüzgâr hızı yörünge ucuna gitmelidir.

    ÖLÇÜLDÜ: ``wind_speed = 25`` gövdeye eklenince
    ``performance.trajectory_metrics.max_altitude`` 6299,278 -> 6290,735 m.
    """

    def test_yorunge_govdesi_ruzgari_tasir(self):
        g = govde(metin(SOLID), 'computeTrajectory')
        assert g, 'computeTrajectory bulunamadı'
        assert 'body.wind_speed' in g, (
            'Sayfa rüzgâr hızı soruyor ama yörünge gövdesine koymuyor.')

    def test_bos_alan_anahtar_gondermez(self):
        g = govde(metin(SOLID), 'computeTrajectory')
        assert "String(ruzgarEl.value).trim() !== ''" in g, (
            'Uç "anahtar yok" ile "değer geldi" ayrımını anahtarın varlığından '
            'yapıyor; boş alan anahtar göndermemeli.')

    def test_uc_alani_gercekten_okuyor(self):
        import os
        os.environ.setdefault('HRMA_HEADLESS', '1')
        from hrma.app import app
        c = app.test_client()
        g = {'initial_mass': 12, 'final_mass': 5, 'drag_coefficient': 0.5,
             'reference_area': 0.008, 'burn_time': 2,
             'thrust': 7 * 200 * 9.80665 / 2, 'isp': 200}
        a = c.post('/api/trajectory-analysis', json=g).get_json() or {}
        b = c.post('/api/trajectory-analysis',
                   json=dict(g, wind_speed=25)).get_json() or {}
        assert a.get('status') == 'success' and b.get('status') == 'success'

        def apoje(r):
            return (((r.get('trajectory_data') or {}).get('performance') or {})
                    .get('trajectory_metrics') or {}).get('max_altitude')
        assert apoje(a) is not None and apoje(b) is not None
        assert apoje(a) != apoje(b), (
            'Rüzgâr hızı sonucu değiştirmiyorsa bu kalemin gerekçesi bayattır.')


# ---------------------------------------------------------------- B2-17
class TestB217UcYanmaliPort:
    """Uç yanmalı tanede çekirdek kanalı yoktur (çözücü: "no port")."""

    def test_viz_portu_sifirlar(self):
        g = govde(metin(SOLID), 'buildSolidVizData')
        assert g, 'buildSolidVizData bulunamadı'
        assert 'end_burner' in g, '3B veri kurucusu uç yanmalı taneyi ayırmıyor'
        assert 'portInitM = 0' in g

    def test_tane_tipi_sonuctan_okunur(self):
        g = govde(metin(SOLID), 'buildSolidVizData')
        assert 'r.grain_type' in g, (
            'Tane tipi form yerine ÇÖZÜCÜ yanıtından okunmalı (tek kaynak).')

    def test_cozucu_portsuzlugu_beyan_ediyor(self):
        import os
        os.environ.setdefault('HRMA_HEADLESS', '1')
        from hrma.app import app
        c = app.test_client()
        d = c.post('/calculate_solid', json={
            'motor_name': 'T', 'propellant_type': 'apcp',
            'grain_type': 'end_burner', 'chamber_diameter': 100,
            'grain_length': 500, 'core_diameter': 30,
            'chamber_pressure': 50, 'expansion_ratio': 8,
            'char_velocity': 1550}).get_json() or {}
        assert d.get('grain_type') == 'end_burner'
        künye = (d.get('thrust_curve') or {}).get('port_area_basis') or ''
        assert 'no port' in künye, künye

    def test_desteklenmeyen_kesit_adi_icat_edilmedi(self):
        g = govde(metin(SOLID), 'solidPortShape')
        for ad in re.findall(r"return '([a-z]+)'", g):
            assert ad in {'circular', 'star', 'multiport', 'finocyl'}, ad


# ---------------------------------------------------------------- B2-18
class TestB218EnBoyOrani:
    """3B CAD görünümü gerçek narinliği çizmelidir (ölçülen 5,82:1)."""

    def test_cube_kipi_sokuldu(self):
        s = metin(SOLID)
        assert not re.search(r"aspectmode:\s*'cube'", s)

    def test_veri_kipi_kondu(self):
        # ÖH V3 taban-v (14 Eki 2026) — SAYIM KODA DARALTILDI (iddia
        # DEĞİŞMEDİ: sahnede veri kipi TEK kez kurulur). ÖH D35 OH-GT-30
        # (commit f3c735ee) kameranın yönelim onarımına bir GEREKÇE YORUMU
        # ekledi; yorum oranın kaynağını anlatırken "`aspectmode: 'data'`"
        # metnini alıntılıyor. Ham metin sayımı yorumu ikinci kurulum sandı
        # (2 == 1). Yorumlar (``/* */``, tam satır ``//``, ``<!-- -->``)
        # aynı uzunlukta boşlukla maskelenir; sayılan yalnız koddur.
        s = metin(SOLID)
        kod = re.sub(r'/\*[\s\S]*?\*/|^[ \t]*//[^\n]*$|<!--[\s\S]*?-->',
                     lambda m: re.sub(r'[^\n]', ' ', m.group(0)), s,
                     flags=re.M)
        assert len(re.findall(r"aspectmode:\s*'data'", kod)) == 1


# ---------------------------------------------------------------- B2-19
class TestB219I18nBogazi:
    """Kullanıcıya görünen metinler i18n boğazından geçer."""

    DESENLER = (
        (r"showError\('Error: '", 'showError ham İngilizce önek'),
        (r"textContent = 'Computing\.\.\.'", "'Computing...' düğme metni"),
        (r"title: 'Frequency'", "'Frequency' eksen başlığı"),
        (r"showSuccess\('\.eng file downloaded'\)", '.eng indirme iletisi'),
        (r"showError\('\.eng export error: '", '.eng hata iletisi'),
        (r">Success Rate \(' \+", 'Monte Carlo başarı oranı başlığı'),
        (r"mcStatCard\('Thrust'", 'Monte Carlo itki kartı etiketi'),
        (r"\+\s*'[^']*runs did not converge \(excluded", 'yakınsamayan koşu satırı'),
        (r"nozzleLength, 'Nozzle',", '3B lüle izi adı'),
    )

    @pytest.mark.parametrize('desen,ad', DESENLER)
    def test_ham_metin_kalmadi(self, desen, ad):
        assert not re.search(desen, metin(SOLID)), ad

    def test_yeni_anahtarlar_en_ve_tr(self):
        j = metin(I18NP)
        for k in ('solid.js.error_prefix', 'solid.js.computing',
                  'solid.js.frequency_axis', 'solid.js.eng_downloaded',
                  'solid.js.eng_export_error', 'solid.js.mc_success_rate',
                  'solid.js.mc_thrust', 'solid.js.mc_failed_runs',
                  'solid.msg.nozzle'):
            assert j.count("'%s'" % k) == 2, k


# ---------------------------------------------------------------- B3-06
class TestB306OptimumEgrisi:
    """15 noktalık Isp⟷O/F eğrisi DOM'a girmelidir."""

    def test_egri_dom_a_ekleniyor(self):
        s = metin(ADV)
        g = govde(s, 'findOptimumOF')
        assert g, 'findOptimumOF bulunamadı'
        i = g.find("plotDiv.id = 'of-optimization-plot'")
        assert i >= 0, 'O/F eğrisinin çizim düğümü bulunamadı'
        # Ekleme, düğümün KENDİSİNE ait olmalı: aynı işlevde başka
        # insertBefore/appendChild çağrıları da var (ölçüldü: 1 + 2).
        pencere = g[i:i + 900]
        assert ('insertBefore(plotDiv' in pencere
                or 'appendChild(plotDiv)' in pencere
                or 'insertAdjacentElement' in pencere and 'plotDiv' in pencere), (
            "Eğri serbest bir düğüme çiziliyor ve DOM'a hiç eklenmiyor.")

    def test_kapsiz_dugume_cizilmez(self):
        g = govde(metin(ADV), 'findOptimumOF')
        assert 'if (plotDiv.parentNode)' in g, (
            'Kap bulunamazsa serbest düğüme çizip atmak yerine hiç çizilmemeli.')

    def test_kap_sayfada_var(self):
        assert 'id="optimum_of_result"' in metin(ADV)


# ---------------------------------------------------------------- B3-09
class TestB309GolgelemeKapisi:
    """Şablonun ezdiği app.js işlevlerinde kapı kaybı olmamalıdır."""

    ADLAR = ('updateInjectorParams', 'showLoading', 'showMessage',
             'showDesignConfig', 'switchConfigTab', 'generateCAD',
             'exportSTL', 'rotate3DView', 'reset3DView', 'downloadEngFile',
             'generateCompletePackage', 'calculateParametric')

    #: ÖH D30 · arayuz-panel a1 — bu adların ``app.js`` kopyaları SÖKÜLDÜ
    #: (ölçüldü: 11 canlı gölge, 446 erişilemez satır;
    #: docs/scofield/raw/OH/D30/arayuz-panel/a1/{once,sonra}.json).
    #: Rakip sürüm kalmadığı için karşılaştırma artık yapılamaz — bekçi
    #: SESSİZCE boşa düşmesin diye eksik kalan adlar ADIYLA sayılır.
    D30_SOKULEN = {'showLoading', 'showMessage', 'showDesignConfig',
                   'switchConfigTab', 'generateCAD', 'exportSTL',
                   'rotate3DView', 'reset3DView', 'downloadEngFile',
                   'generateCompletePackage', 'calculateParametric'}
    #: ``updateInjectorParams`` app.js'te TABANDA DA yoktu (ölçüldü:
    #: ``git show ab7cf68b:hrma/static/js/app.js`` -> 0 bildirim); yalnız
    #: advanced.html'de tanımlı, yani karşılaştırılacak rakip hiç olmadı.
    RAKIPSIZ = {'updateInjectorParams'}

    def _olculemeyen(self):
        adv, app_js = metin(ADV), metin(APPJS)
        return sorted(ad for ad in self.ADLAR
                      if not (govde(adv, ad) and govde(app_js, ad)))

    def test_olculemeyenler_d30_sokumuyle_aciklanir(self):
        """Karşılaştırılamayan her ad ölçülmüş bir sökümle açıklanmalı."""
        beklenen = sorted(self.D30_SOKULEN | self.RAKIPSIZ)
        assert self._olculemeyen() == beklenen, (
            'app.js/şablon çiftinin karşılaştırılamadığı adlar değişti: %s — '
            'bekçi sessizce boşa düşüyor olabilir' % self._olculemeyen())

    def _kapi_kaybi(self):
        adv, app_js = metin(ADV), metin(APPJS)
        kayıp = []
        for ad in self.ADLAR:
            ga, gb = govde(adv, ad), govde(app_js, ad)
            if not (ga and gb):
                continue

            def kapili(g):
                i = g.find('currentResults')
                return i >= 0 and 'return' in g[i:i + 900]
            if kapili(gb) and not kapili(ga):
                kayıp.append(ad)
        return kayıp

    def test_kapi_kaybi_yok(self):
        assert self._kapi_kaybi() == [], (
            'Kazanan şablon sürümü, gölgelediği app.js sürümünün kapısını '
            'kaybediyor: %s' % self._kapi_kaybi())

    def test_showDesignConfig_hesapsiz_paneli_acmaz(self):
        g = govde(metin(ADV), 'showDesignConfig')
        assert g
        i = g.find('currentResults')
        assert i >= 0 and 'return' in g[i:i + 400], (
            'showDesignConfig hesap yapılmadan yapılandırma panelini açıyor.')


# ---------------------------------------------------------------- B3-14
class TestB314CeaHukmu:
    """"NASA CEA ile doğrulandı" hükmü kazanılmadan basılamaz.

    ÖLÇÜLDÜ: ``ZZZ9`` bileşimi için uç HTTP 200 + ``status: success``
    dönüyor ama hiçbir bileşen CEA tablosunda YOK; şablon artık hükmü
    ``found_in_database`` alanından kuruyor ve tablo dışıysa "NOT
    validated" diyor. Bekçi bu ayrımı kilitler.
    """

    def test_kosulsuz_dogrulandi_cumlesi_yok(self):
        s = metin(ADV)
        assert 'Composition validated successfully with NASA CEA database' not in s

    def test_olu_cea_sarmali_geri_gelmedi(self):
        """ÇEVRİLDİ (ÖH D33-KOLAY · OH-D32-11).

        ESKİ SÖZLEŞME: hükmün ``validateComposition()`` gövdesinde
        ``found_in_database`` alanından kurulduğu ölçülüyordu. Sözleşme ölü
        fonksiyonun DURMASINI şart koşuyordu; ölçüldü ki (D33 a1/once.json ·
        M2) tek çağıranı OH-D31-05'te sökülen panelin düğmesiydi ve akış
        hiçbir yoldan açılamıyordu. Sarmal D33'te silindi.

        YENİ SÖZLEŞME: hükmü basacak istemci yüzeyi YOK; geri gelirse bu
        bekçi kırmızı verir. Kalemin ürün ayağı (uç, ZZZ9 senaryosu)
        aşağıdaki testte dokunulmadan durur.
        """
        s = re.sub(r'<!--.*?-->', '', metin(ADV), flags=re.S)
        assert 'function validateComposition' not in s, (
            'erişilemez CEA sarmalı geri geldi (OH-D32-11)')
        assert 'ceaNotInTable' not in s, (
            'ölü CEA hüküm anahtarı geri geldi')

    def test_uc_kimyasal_anlami_dogrulamiyor_kaydi(self):
        import os
        os.environ.setdefault('HRMA_HEADLESS', '1')
        from hrma.app import app
        c = app.test_client()
        r = c.post('/api/validate-fuel',
                   json={'composition': [{'compound': 'ZZZ9',
                                          'percentage': 100}]})
        d = r.get_json() or {}
        if d.get('status') == 'success':
            bileşenler = d.get('components') or []
            assert bileşenler, d
            assert all(not b.get('found_in_database') for b in bileşenler), (
                'Uç anlamsız bir formülü tabloda BULDUĞUNU söylüyorsa hüküm '
                'katmanı da yanılır; kalem yeniden ölçülmelidir.')

    def test_sunucu_dizesi_innerHTML_e_ham_gitmiyor(self):
        s = metin(ADV)
        assert not re.search(
            r'innerHTML\s*=\s*[`\'"][^`\'";]{0,400}\$\{?result\.error', s)


# ---------------------------------------------------------------- B3-17
class TestB317IstemciDogrulamasi:
    """Sayfanın ilan ettiği sayısal bantlar gerçekten uygulanmalıdır."""

    def test_dogrulayici_cagriliyor(self):
        s = metin(APPJS)
        assert 'window.validateFormData' in s, (
            'advanced.html 50 satırlık validateFormData taşıyor ve hiç '
            'çağrılmıyordu; ilan edilen beş bant uygulanmıyor.')
        g = govde(s, 'calculate')
        assert g and 'window.validateFormData(data)' in g, (
            'Doğrulayıcı ÇAĞRILMIYOR (yalnız adı geçiyor olabilir).')
        # Çağrı ULAŞILABİLİR olmalı: ölü bir dalın içinde durmamalı.
        i = g.find('typeof window.validateFormData')
        assert i >= 0
        koşul = g[max(0, i - 60):i]
        assert 'false &&' not in koşul and '0 &&' not in koşul, (
            'Doğrulayıcı çağrısı ölü bir dalın arkasında.')

    def test_hata_varsa_istek_gonderilmez(self):
        g = govde(metin(APPJS), 'calculate')
        i = g.find('window.validateFormData')
        assert i >= 0
        pencere = g[i:i + 700]
        assert 'return' in pencere
        assert pencere.find('return') < pencere.find('fetch') or 'fetch' not in pencere

    def test_dogrulayici_bantlari_ilan_ediyor(self):
        g = govde(metin(ADV), 'validateFormData')
        assert g
        for parça in ('of_ratio', 'chamber_pressure', 'thrust', 'burn_time'):
            assert parça in g, parça

    def test_zorunlu_alanlar_getFormData_yukunde_var(self):
        """Kapı kondu diye ürün kilitlenmemeli.

        Doğrulayıcının zorunlu saydığı 10 alan, ``getFormData()``nın
        ÜRETTİĞİ yükte bulunmalıdır — bir kısmı aynı adlı bir ``input``
        değildir (``atmospheric_pressure`` iki ortam kipinden türetilir),
        bu yüzden ölçü form kimliklerine değil YÜKE bakar. Alan yükte yoksa
        her hesap "Missing ..." ile reddedilirdi.
        """
        adv = metin(ADV)
        g = govde(adv, 'validateFormData')
        yük = govde(adv, 'getFormData')
        assert yük, 'getFormData bulunamadı'
        eksik = [alan for alan in re.findall(r"'([a-z_]+)': \['adv\.", g)
                 if not re.search(r'(?m)^\s*' + alan + r'\s*:', yük)]
        assert eksik == [], (
            'Doğrulayıcı zorunlu sayıyor ama getFormData üretmiyor: %s' % eksik)
