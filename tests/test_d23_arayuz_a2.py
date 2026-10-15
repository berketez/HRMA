# -*- coding: utf-8 -*-
"""ÖH Dalga-23 · arayuz kulvarı · aşama 2/2 — bekçiler (P17 görsel tur ailesi).

Her onarım, kusuru GÖRDÜĞÜ ters mutasyonla kanıtlanmış bir bekçiye bağlıdır
(ÖK-05). Mutasyon kanıtı:
    docs/scofield/raw/OH/D23/arayuz/a2/mutasyon.json

Ölçüm kanıtı: once.json / sonra.json (statik),
              atesleme.json (P17B1-04 — yükten türetme).
"""
import io
import json
import os
import re

import pytest
from tests.support.kanit import kanit_gerekli

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def oku(rel):
    with io.open(os.path.join(KOK, rel), encoding='utf-8') as f:
        return f.read()


@pytest.fixture(scope='module')
def viz3d():
    return oku('hrma/static/js/motor_viz3d.js')


@pytest.fixture(scope='module')
def deck():
    return oku('hrma/static/js/motor_viz_deck.js')


@pytest.fixture(scope='module')
def theme():
    return oku('hrma/static/css/theme.css')


@pytest.fixture(scope='module')
def fea():
    return oku('hrma/static/js/fea_panel.js')


@pytest.fixture(scope='module')
def tfea():
    return oku('hrma/static/js/thermal_fea_panel.js')


@pytest.fixture(scope='module')
def sozluk():
    return ''.join(oku('hrma/static/js/' + f) for f in (
        'i18n_common.js', 'i18n_pages.js', 'i18n_shell.js',
        'i18n_launch_site.js', 'i18n_advanced.js'))


def yorumsuz(js):
    """`//` ve `/* */` yorumlarını atar.

    BEKÇİ SERTLEŞTİRMESİ (a2 mutasyon turu 1): bir bekçi aradığı sembolü
    KODUN kendisinde değil, yanındaki AÇIKLAMA metninde bulup geçiyordu —
    onarımı sökmek bekçiyi kırmızıya düşürmedi. Aynı ders D23 a1'de de
    çıkmıştı. Kod denetimi yapan her arama bu süzgeçten geçer.
    """
    js = re.sub(r'/\*.*?\*/', '', js, flags=re.S)
    return re.sub(r'//[^\n]*', '', js)


def anahtar_dilleri(sozluk_metni, anahtar):
    """Anahtarın sözlükteki karşılıkları (EN + TR beklenir)."""
    desen = r"'" + re.escape(anahtar) + r"':\s*'((?:[^'\\]|\\.)*)'"
    return re.findall(desen, sozluk_metni)


# =====================================================================
# P17B1-09 — 3B sahne oturum dilini izler VE dil değişiminde tazelenir
# =====================================================================
class TestP17B109SahneDili:
    """en-US oturumda Türkçe etiket kalmaz; dil değişince sahne donmaz."""

    def test_yakit_ve_oda_etiketleri_sabit_turkce_degil(self, viz3d):
        """ÖLÇÜLDÜ (once.json): ham_turkce_YAKIT=1, ham_turkce_ODA=1.

        Hükmün (H1) kaynak taramasının kaçırdığı altıncı etiket buydu:
        ekranda `L 668 mm • YAKIT 506 mm`. Sabit Türkçe sözcük ölçü
        etiketine GÖMÜLÜ olamaz.
        """
        assert not re.search(r"'\s*•\s*YAKIT ", viz3d), (
            'ölçü etiketinde sabit Türkçe "YAKIT" geri gelmiş')
        assert not re.search(r"'\s*•\s*ODA ", viz3d), (
            'ölçü etiketinde sabit Türkçe "ODA" geri gelmiş')

    def test_etiket_sozcukleri_i18n_kanalindan_gecer(self, viz3d):
        assert "T('viz3d.label.grain'" in viz3d
        assert "T('viz3d.label.chamber'" in viz3d

    @pytest.mark.parametrize('anahtar', ['viz3d.label.grain',
                                         'viz3d.label.chamber'])
    def test_etiket_anahtarlari_iki_dilde_var(self, sozluk, anahtar):
        degerler = anahtar_dilleri(sozluk, anahtar)
        assert len(degerler) >= 2, (
            '%s sözlükte iki dilde bulunmalı, bulunan: %d'
            % (anahtar, len(degerler)))
        assert all(d.strip() for d in degerler), anahtar

    def test_dil_degisiminde_olcu_etiketleri_yeniden_kurulur(self, viz3d):
        """Sprite metni DOM değildir; translateTree ona ULAŞAMAZ.

        ÖLÇÜLDÜ (once.json): lang_etiketleri_tazeler = 0 — dinleyici
        yalnız durum çiplerini tazeliyordu, ölçü etiketleri ilk kurulum
        dilinde DONUYORDU.
        """
        m = re.search(r"this\._langHandler = function \(\) \{(.*?)\n        \};",
                      viz3d, re.S)
        assert m, '_langHandler gövdesi bulunamadı'
        govde = yorumsuz(m.group(1))   # açıklama metni kanıt değildir
        assert '_buildLabels' in govde, (
            'dil değişiminde ölçü etiketleri yeniden kurulmuyor')
        assert '_refreshGridBadge' in govde, (
            'dil değişiminde ızgara hücresi rozeti yeniden kurulmuyor')
        assert '_refreshStatusChips' in govde, (
            'D21 onarımı (durum çipleri) korunmalı')

    def test_izgara_rozeti_tazeleyicisi_var_ve_metni_kendi_uretir(self, viz3d):
        assert 'MotorScene.prototype._refreshGridBadge' in viz3d
        m = re.search(r'MotorScene\.prototype\._refreshGridBadge = function \(\) \{'
                      r'(.*?)\n    \};', viz3d, re.S)
        assert m, '_refreshGridBadge gövdesi bulunamadı'
        assert 'gridBadgeText(' in yorumsuz(m.group(1)), (
            'rozet metni yeniden ÜRETİLMİYOR (eski doku korunuyorsa dil '
            'değişimi ekrana yansımaz)')


# =====================================================================
# P17B2-10 — ε (U+03B5) CSS büyütmesinde Ε (U+0395) olmaz
# =====================================================================
class TestP17B210EpsilonSembolu:
    def test_uppercase_kurali_hala_var(self, theme):
        """Onarım kuralı SÖKMEZ; yalnız sembolü muaf tutar."""
        assert re.search(r'\.viz-chip \.k \{[^}]*text-transform:\s*uppercase',
                         theme), 'çip başlığı büyütmesi kaybolmuş'

    def test_sembol_muafiyeti_kurali_var(self, theme):
        assert '.viz-chip .k .viz-sym' in theme
        m = re.search(r'\.viz-chip \.k \.viz-sym \{([^}]*)\}', theme)
        assert m and 'text-transform: none' in m.group(1), (
            'sembol kabı büyütmeden muaf değil')

    def test_cip_basligi_sembol_koruyan_yoldan_basilir(self, deck):
        """İki çizim yolu da (ilk boya + dil tazeleme) aynı yoldan geçer."""
        assert deck.count('TXK(c.label)') == 2, (
            'çip başlığı iki yerde basılır; ikisi de sembol korumalı '
            'olmalı — yoksa dil değişiminde ε yeniden bozulur')
        assert 'function sembolKoru(' in deck
        assert 'function TXK(' in deck

    def test_sembol_koruma_epsilonu_sarar(self, deck):
        """Desen gerçekten ε'yi (ve alt indisi) yakalıyor mu."""
        m = re.search(r'var SEMBOL_DESENI = /\(\[(.*?)\]\)/g;', deck)
        assert m, 'sembol deseni bulunamadı'
        sinif = m.group(1)
        # Yunan bloğu aralığı ε'yi (U+03B5) kapsamalı
        assert 'Ͱ' in sinif and 'Ͽ' in sinif, (
            'Yunan harf aralığı desende yok: %r' % sinif)
        assert 'sub>' in deck and 'sup>' in deck

    def test_etiket_kaynagi_bozulmadi(self, deck):
        """Sözlük anahtarı = İngilizce kaynak metin; DEĞİŞMEMELİ."""
        assert "label: 'Expansion &epsilon;'" in deck, (
            'etiket kaynağı değişmiş — TX() sözlük eşleşmesi kırılır')
        assert "label: 'P<sub>c</sub>'" in deck


# =====================================================================
# P17B2-09 — her canlı çizim kabının altyazı kaydı var
# =====================================================================
class TestP17B209CizimAltyazisi:
    KAPLAR = ('solid_motor_kesit', 'liquid_motor_kesit', 'mc_hist_isp',
              'mc_hist_thrust', 'cad_3d_view', 'cad_visualization',
              'altitude_preview', 'altitude_plot')

    @pytest.mark.parametrize('kap', KAPLAR)
    def test_kabin_altyazi_kaydi_var(self, kap):
        caps = oku('hrma/static/js/chart_captions.js')
        assert re.search(r"'chartCap\." + kap + r"'\s*:", caps), (
            '%s kabının altyazı kaydı YOK — maybeAttach onu sessizce '
            'atlar (chart_captions.js: kayıt yoksa altyazı eklenmez)' % kap)

    def test_sivi_kesit_altyazisi_iki_dilde(self, sozluk):
        degerler = anahtar_dilleri(sozluk, 'chartCap.liquid_motor_kesit')
        assert len(degerler) >= 2, (
            'sıvı kesit altyazısı iki dilde bulunmalı, bulunan: %d'
            % len(degerler))

    def test_sivi_kesit_kabi_gercekten_ciziliyor(self):
        """Ölü kayıt eklemedik: kap şablonda VAR ve çiziliyor."""
        liq = oku('hrma/templates/liquid.html')
        assert 'id="liquid_motor_kesit"' in liq
        assert "liquidPlot('liquid_motor_kesit'" in liq


# =====================================================================
# P17B4-07 + P17B1-18 — istemci zaman aşımı ve gerekçeli meşgul satırı
# =====================================================================
class TestP17B407ZamanAsimi:
    def test_zaman_asimi_tek_kaynakta(self, fea):
        """Doktrin 4: 180000 üç şablonda ayrı ayrı yazılıydı."""
        assert 'const ISTEK_ZAMAN_ASIMI_MS = 180000;' in fea
        assert 'window.HRMA_ISTEK_ZAMAN_ASIMI_MS = ISTEK_ZAMAN_ASIMI_MS;' in fea

    @pytest.mark.parametrize('sablon', ['advanced', 'solid', 'liquid'])
    def test_sablonlar_ciplak_sayi_yazmiyor(self, sablon):
        s = oku('hrma/templates/%s.html' % sablon)
        assert 'AbortSignal.timeout(180000)' not in s, (
            '%s.html hâlâ çıplak süreyi yazıyor (tek kaynak bozuldu)'
            % sablon)
        assert 'window.HRMA_ISTEK_ZAMAN_ASIMI_MS' in s, (
            '%s.html zaman aşımını tek kaynaktan okumuyor' % sablon)

    def test_yapisal_ve_tane_kosumu_sinyal_tasiyor(self, fea):
        """ÖLÇÜLDÜ (once.json): abort_panel_js = 0 — iki fetch de sinyalsizdi.

        ÖH D26 · arayuz a3 (P11B3-19) aynı kanala KULLANICI İPTALİNİ de
        ekledi: iki koşum yolu artık zaman aşımı sinyalini doğrudan değil,
        iptal denetleyicisiyle BİRLEŞTİREN ``kosumSinyali()`` üzerinden
        taşıyor. Bu bekçi eski SEMBOL ADINI arıyordu ve a3'ten sonra
        kırmızıya düştü (ölçüldü: a4 sembol taraması — taban ağacında
        yeşil, worktree'de kırmızı). Ölçüt METİN yerine ANLAM'a çevrildi:
        iki fetch de sinyal taşımalı VE o sinyal zaman aşımını İÇERMELİ.
        Gevşetme yok — sinyalsiz bir fetch de, zaman aşımı zincirden
        çıkarılırsa da test yine KIRMIZI olur.
        """
        assert fea.count('signal: kosumSinyali(') == 2, (
            'fea_panel.js iki koşum yolu da (yapısal + tane) koşum '
            'sinyali taşımalı')
        assert 'function zamanAsimiSinyali()' in fea
        assert 'function zamanAsimiMi(' in fea
        # Zaman aşımı zincirden çıkarılamaz: birleşik sinyal onu içerir ve
        # AbortSignal.any yoksa süre sınırı elle kurulur.
        assert 'AbortSignal.any([c.signal, zs])' in fea
        assert 'const zs = zamanAsimiSinyali();' in fea

    def test_termal_kosumu_iki_adiminda_da_sinyal_tasiyor(self, tfea):
        """Termal zincir iki adımlıdır; a3 sonrası ikisi de birleşik sinyalde.

        Adım 1 koşum sinyalini kurar (``kosumSinyali()``), adım 2 aynı
        koşumun AKTİF sinyalini yeniden kullanır (``aktifSinyal``) — iptal
        ikinci adımı da durdurur, süre sınırı koşumun tamamını ölçer.
        """
        assert tfea.count('signal: kosumSinyali()') == 1, (
            'termal koşumun ilk adımı (wall-profile) sinyal taşımalı')
        assert tfea.count('signal: aktifSinyal || zamanAsimiSinyali()') == 1, (
            'termal koşumun ikinci adımı (transient) AYNI koşumun sinyalini '
            'taşımalı')
        assert tfea.count('signal: ') == 2, (
            'termal panelde sinyalsiz ya da fazladan fetch var: %d'
            % tfea.count('signal: '))

    def test_termal_panel_sureyi_kendi_yazmiyor(self, tfea):
        """Süre TEK KAYNAKTAN okunur; ikinci literal yasak."""
        assert '180000' not in tfea
        assert 'window.HRMA_ISTEK_ZAMAN_ASIMI_MS' in tfea


class TestP17B118MesgulBeyani:
    def test_yapisal_mesgul_satiri_gecen_sureyi_yazar(self, fea):
        """ÖLÇÜLDÜ (canlı tur): mesgul=true, gerekçe çipi BOŞ, 180 s sonra
        hâlâ "çalışıyor" — geçen süre yok, sınır yok, iptal yok."""
        assert "mesgulYaz('structural'" in fea
        assert "'fea.busyElapsed'" in fea
        assert 'function mesgulYaz(' in fea

    def test_tane_mesgul_satiri_gecen_sureyi_yazar(self, fea):
        assert "mesgulYaz('grain'" in fea
        assert "GL('busyElapsed'" in fea

    def test_zaman_asimi_kendi_gerekcesini_yazar(self, fea, tfea):
        """Sessiz düşüş yok: zaman aşımı jenerik hata metnine düşmez."""
        assert "'fea.timeout'" in fea
        assert "GL('timeout'" in fea
        assert "'feaT.timeout'" in tfea

    @pytest.mark.parametrize('anahtar', ['fea.busyElapsed', 'fea.timeout',
                                         'feaT.busyElapsed', 'feaT.timeout',
                                         'solid.fea.busy_elapsed',
                                         'solid.fea.timeout'])
    def test_gerekce_anahtarlari_iki_dilde(self, sozluk, anahtar):
        degerler = anahtar_dilleri(sozluk, anahtar)
        assert len(degerler) >= 2, (
            '%s iki dilde bulunmalı, bulunan: %d' % (anahtar, len(degerler)))

    def test_sahte_ilerleme_yok(self, fea):
        """Doktrin 6: yüzde UYDURULMAZ — çözücü kaç tur yapacağını bilmiyor."""
        m = re.search(r'function mesgulYaz\((.*?)\n    \}\n', fea, re.S)
        assert m, 'mesgulYaz gövdesi bulunamadı'
        govde = yorumsuz(m.group(1))
        assert 'progress' not in govde.lower()
        assert '%' not in govde, (
            'meşgul satırında yüzde üretiliyor — sahte ilerleme yasağı')


# =====================================================================
# P17B2-14 — çözünürlük beyanı hiçbir an boş kalmaz
# =====================================================================
class TestP17B214CozunurlukBeyani:
    def test_taban_beyani_dugumu_var(self):
        ls = oku('hrma/templates/launch_site.html')
        assert 'id="ls-basenote"' in ls
        assert 'data-i18n="site.baseTextureNote"' in ls

    def test_taban_beyani_yalniz_oteki_ikisi_kapaliyken_acilir(self):
        """Üç beyan birbirini DIŞLAR; çelişkili iki beyan yan yana duramaz."""
        ls = oku('hrma/templates/launch_site.html')
        m = re.search(r"el\('ls-basenote'\)\.style\.display =\s*(.*?);", ls, re.S)
        assert m, 'taban beyanı kapısı bulunamadı'
        kosul = m.group(1)
        assert '!info.tilesDrawn' in kosul, (
            'karo çiziliyken taban beyanı basılırsa iki çözünürlük '
            'iddiası aynı anda ekranda olur (P12aB4-07 kusuru geri gelir)')
        assert '!info.textureCoarse' in kosul, (
            'yakın zoom notuyla aynı anda basılırsa iki beyan çelişir')

    def test_taban_beyani_anahtari_iki_dilde(self, sozluk):
        degerler = anahtar_dilleri(sozluk, 'site.baseTextureNote')
        assert len(degerler) >= 2, len(degerler)
        for d in degerler:
            assert '9 km' in d, (
                'taban beyanı çözünürlüğü SAYIYLA söylemeli: %r' % d)

    def test_yakin_zoom_notu_korundu(self):
        ls = oku('hrma/templates/launch_site.html')
        assert 'id="ls-texnote"' in ls
        assert "el('ls-texnote').style.display = info.textureCoarse" in ls


# =====================================================================
# P17B2-06 — ÇÜRÜTÜLDÜ; kapanış bekçisi (gerileme koruması)
# =====================================================================
class TestP17B206KabukSeridi:
    """Kalem ÇÜRÜTÜLDÜ: ÖLÇÜLDÜ (once.json) ki /launch-site ve / artık
    tanınan bir kabuk şeridi taşıyor ve Ayarlar / Sürüm Notları oraya
    bağlanıyor. Kusurun kökü D18'de (P12aB5-06) kapatılmış: kanca yalnız
    `.nav-links` sormuyor, üç şeridi de tanıyan TEK tablo (NAV_HOSTS)
    üzerinden geçiyor. Bu bekçi kapanışı KİLİTLER: kabuk betiklerini
    yükleyen her şablon tanınan bir çapa taşımak zorunda, yoksa bağlantı
    sessizce (fail-open) düşer — kalemin ölçtüğü kusur tam buydu.
    """

    # ÖH D33-KOLAY · denetim ŞARTI (arayuz): `simple` ve `uzaytek` demete
    # eklenmişti (kabuk betiği yüklemedikleri için skip dalına düşüyorlardı).
    # 'simple', 'uzaytek' girdileri emekli — sayfa sökümü: Berke 23 Eyl, dalga36/sokum
    SABLONLAR = ('index', 'launch_site', 'advanced', 'solid', 'liquid',
                 'formulas')

    @pytest.mark.parametrize('sablon', SABLONLAR)
    def test_kabuk_betigi_yukleyen_sablon_capa_tasir(self, sablon):
        s = oku('hrma/templates/%s.html' % sablon)
        if 'release_notes.js' not in s and 'settings_panel.js' not in s:
            pytest.skip('%s kabuk betiklerini yüklemiyor' % sablon)
        capalar = ('class="nav-links"', 'aux-links', 'id="ls-topbar"')
        assert any(c in s for c in capalar), (
            '%s.html kabuk betiklerini yüklüyor ama tanınan hiçbir şerit '
            'çapası taşımıyor; injectShellNavLink sessizce null döner ve '
            'Ayarlar / Sürüm Notları o sayfada HİÇBİR yoldan açılamaz'
            % sablon)

    def test_taninan_serit_tablosu_uc_kabugu_da_kapsar(self):
        rn = oku('hrma/static/js/release_notes.js')
        m = re.search(r'var NAV_HOSTS = \[(.*?)\];', rn, re.S)
        assert m, 'NAV_HOSTS tablosu bulunamadı'
        tablo = m.group(1)
        for secici in ("'.nav-links'", "'.aux-links'", "'#ls-topbar'"):
            assert secici in tablo, (
                '%s şeridi tabloda yok — o kabuğu kullanan sayfada '
                'bağlantı sessizce düşer' % secici)

    def test_tablo_tek_kaynak_ve_yayimlaniyor(self):
        # ÖH D33-KOLAY · denetim ŞARTI (arayuz): ilk iki assert de
        # `yorumsuz()` süzgecinden geçer. Aynı testin üçüncü asserti zaten
        # bu yardımcıyı kullanıyordu; ilk ikisi sembolü AÇIKLAMA metninde
        # bulup geçebiliyordu (release_notes.js:229 ve settings_panel.js:836
        # yorumlarında `window.HRMA_SHELL_NAV` YAZILI). Tek kaynak sökülse
        # bekçi yorum sayesinde yeşil kalırdı.
        rn = yorumsuz(oku('hrma/static/js/release_notes.js'))
        sp = yorumsuz(oku('hrma/static/js/settings_panel.js'))
        assert 'window.HRMA_SHELL_NAV' in rn, 'tablo yayımlanmıyor'
        assert 'window.HRMA_SHELL_NAV' in sp, (
            'Ayarlar kancası tabloyu okumuyor — ikinci bir kopya tutulursa '
            'iki kanca ayrışır (P12aB5-06 kusurunun kaynağı)')
        assert "querySelector('.nav-links')" not in sp, (
            'Ayarlar kancası yine YALNIZ .nav-links soruyor')


# =====================================================================
# P17B3-07 — ölü `exportOpenRocket` kopyaları söküldü
# =====================================================================
class TestP17B307OluIhracYolu:
    def test_olu_islev_iki_dosyadan_da_kalkti(self):
        appjs = oku('hrma/static/js/app.js')
        adv = oku('hrma/templates/advanced.html')
        assert 'function exportOpenRocket' not in appjs
        assert 'function exportOpenRocket' not in adv

    def test_uretim_yolu_dokunulmadi(self):
        """Tek tıkta indiren yol KORUNUR (katı/sıvı kardeşleriyle aynı)."""
        adv = oku('hrma/templates/advanced.html')
        assert 'async function downloadEngFile()' in adv
        assert 'id="downloadEngBtn"' in adv
        assert 'onclick="downloadEngFile()"' in adv

    def test_dugme_hesaptan_sonra_aciliyor(self):
        appjs = oku('hrma/static/js/app.js')
        assert "getElementById('downloadEngBtn')" in appjs
        assert "'downloadEngBtn'" in appjs


# =====================================================================
# P17B3-08 — geçici ile kalıcı uygulanamazlık ayrı rozetler
# =====================================================================
class TestP17B308GeciciKaliciAyrimi:
    @pytest.fixture(scope='class')
    def ac(self):
        return oku('hrma/static/js/analysis_center.js')

    def test_sonuc_yoklugu_gecici_durumdur(self, ac):
        """ÖLÇÜLDÜ (P17 B3 tur-02): hesaptan SONRA aynı satır `ready`
        oluyor, yani durum geçiciydi; kalıcı uygulanamazlıkla aynı
        rozeti giymemeli."""
        m = re.search(r"// 3\) Sayfada sonuç yok(.*?)return row;", ac, re.S)
        assert m, 'sonuç yokluğu dalı bulunamadı'
        dal = yorumsuz(m.group(1))
        assert "row.state = 'not_ready'" in dal
        assert "row.state = 'blocked'" not in dal

    def test_not_ready_kendi_rozetini_tasir(self, ac):
        m = re.search(r'const STATE_BADGE = \{(.*?)\};', ac, re.S)
        assert m, 'STATE_BADGE bulunamadı'
        tablo = m.group(1)
        assert 'not_ready:' in tablo
        assert "'ac.state.notReady'" in tablo
        # Rozet metni ve rengi kalıcı durumdan AYRIŞMALI
        assert "'AWAITING RESULT'" in tablo
        assert "'NOT APPLICABLE'" in tablo
        gecici = re.search(r"not_ready: \{ kind: '(\w+)'", tablo)
        kalici = re.search(r"blocked: \{ kind: '(\w+)'", tablo)
        assert gecici and kalici
        assert gecici.group(1) != kalici.group(1), (
            'iki durum aynı renk sınıfını giyiyor — ayrım yine yalnız '
            'gerekçe cümlesinde kalır (P17B3-08 kusuru)')

    def test_motor_tipi_dali_kalici_kaldi(self, ac):
        """Kalıcı uygulanamazlık `blocked` OLARAK KALIR."""
        m = re.search(r"// 1\) Motor tipi(.*?)return row;", ac, re.S)
        assert m and "row.state = 'blocked'" in yorumsuz(m.group(1))

    def test_not_ready_anahtari_iki_dilde(self, sozluk):
        degerler = anahtar_dilleri(sozluk, 'ac.state.notReady')
        assert len(degerler) >= 2, len(degerler)


# =====================================================================
# P17B4-05 — bozuk proje satırı sessiz değil
# =====================================================================
class TestP17B405BozukSatirBeyani:
    @pytest.fixture(scope='class')
    def pbar(self):
        return oku('hrma/static/js/project_bar.js')

    def test_bozuk_satir_tiklamasi_beyan_uretir(self, pbar):
        """ÖLÇÜLDÜ (P17 B4 canlı): toastlar=[], modal açık, URL değişmedi."""
        m = re.search(r'if \(corrupt\) \{(.*?)\n        \}\n', pbar, re.S)
        assert m, 'bozuk satır dalı bulunamadı'
        govde = yorumsuz(m.group(1))
        assert 'addEventListener' in govde
        assert 'toast(' in govde

    def test_gerekce_sunucudan_gelir_turetilmez(self, pbar):
        """Cümleyi SUNUCU yazar; panel uydurmaz."""
        assert 'p.reason' in pbar
        assert "srv(p.reason" in pbar

    def test_gerekce_yoksa_sessiz_kalinmaz(self, pbar):
        """Fail-closed: gerekçe gelmediyse bu da SÖYLENİR."""
        assert "'proj.corruptNoReason'" in pbar

    def test_uc_gerekceyi_gercekten_uretiyor(self):
        """Ölü alan okumadık: list_projects reason yayımlıyor."""
        proj = oku('hrma/utils/projects.py')
        assert proj.count("entry['reason']") >= 3

    @pytest.mark.parametrize('anahtar', ['proj.corruptWhy',
                                         'proj.corruptNoReason'])
    def test_bozuk_gerekce_anahtarlari_iki_dilde(self, sozluk, anahtar):
        degerler = anahtar_dilleri(sozluk, anahtar)
        assert len(degerler) >= 2, (anahtar, len(degerler))


# =====================================================================
# P17B1-04 — rozet sözleşmesi ateşleme koşuluyla genişledi
# =====================================================================
class TestP17B104AteslemeKosulu:
    YENI = ('yapisal_mesh_boyutu', 'yapisal_tepe_von_mises',
            'yapisal_motor_yerlesimi', 'yapisal_yakinsama_hukmu',
            'yapisal_motorun_kendi_sf_hukmu')

    @pytest.fixture(scope='class')
    def imzalar(self):
        import sys
        if KOK not in sys.path:
            sys.path.insert(0, KOK)
        from tools.browser_harness import esikler
        return esikler.ROZET_IMZALARI

    @pytest.mark.parametrize('imza', YENI)
    def test_imza_atesleme_kosulu_tasiyor(self, imzalar, imza):
        """D20-D22'nin engeli tam olarak buydu: ateşleme koşulu olmayan
        imza sözleşmeyi büyütür, KAPSAMI büyütmez."""
        assert imza in imzalar, '%s imzası yok' % imza
        ak = imzalar[imza].get('atesleme_kosulu')
        assert isinstance(ak, dict), '%s ateşleme koşulu taşımıyor' % imza
        for alan in ('sayfa', 'uc', 'kosul', 'olculen_yuk', 'olculen_deger'):
            assert ak.get(alan), '%s.%s boş' % (imza, alan)

    @pytest.mark.parametrize('imza', YENI)
    def test_imza_sozlukteki_her_dilde_geciyor(self, imzalar, sozluk, imza):
        """Mevcut sözleşmenin kuralı yeni imzalara da uygulanır."""
        tanim = imzalar[imza]
        varyantlar = tanim['varyantlar']
        assert varyantlar, imza
        for anahtar in tanim['sozluk_anahtarlari']:
            degerler = anahtar_dilleri(sozluk, anahtar)
            assert len(degerler) >= 2, (
                '%s sözlükte iki dilde bulunmalı, bulunan: %d'
                % (anahtar, len(degerler)))
            for deger in degerler:
                assert any(v in deger for v in varyantlar), (
                    'imza %r, %s karşılığında geçmiyor: %r'
                    % (varyantlar, anahtar, deger))

    @pytest.mark.parametrize('imza', YENI)
    def test_imza_ingilizce_yedekte_de_geciyor(self, imzalar, imza):
        """Sözlük yüklenmezse panel YEDEK metni basar; imza orada da olmalı."""
        tanim = imzalar[imza]
        assert tanim['kaynak_dosyalar'], imza
        for dosya in tanim['kaynak_dosyalar']:
            metin = oku(dosya)
            assert any(v in metin for v in tanim['varyantlar']), (imza, dosya)

    def test_yakinsama_imzasi_olumsuz_hukmu_yakalamaz(self, imzalar, sozluk):
        """Dar varyant şartı: 'CONVERGED' tek başına 'NOT CONVERGED'i de
        eşler ve imza olumsuz hükmü olumlu sanardı."""
        varyantlar = imzalar['yapisal_yakinsama_hukmu']['varyantlar']
        for olumsuz in anahtar_dilleri(sozluk, 'fea.badgeNotConverged'):
            assert not any(v in olumsuz for v in varyantlar), (
                'yakınsama imzası olumsuz hükmü de eşliyor: %r' % olumsuz)

    def test_turetme_kaniti_dosyada_ve_yukten(self):
        """Ateşleme koşulu UYDURULMADI: gerçek bir koşumdan türetildi."""
        yol = os.path.join(
            KOK, 'docs/scofield/raw/OH/D23/arayuz/a2/atesleme.json')
        assert os.path.exists(kanit_gerekli(yol)), 'türetme kanıtı yok'
        with io.open(kanit_gerekli(yol), encoding='utf-8') as f:
            d = json.load(f)
        assert d['adimlar']['calculate']['durum'] == 200
        assert d['adimlar']['fea_structural']['durum'] == 200
        ates = d['atesleme']
        for imza_anahtari in ('fea.badgeMesh', 'fea.badgeVm',
                              'fea.badgeEngine', 'fea.badgeConverged',
                              'fea.badgeEngineSf'):
            assert ates[imza_anahtari]['atesledi'] is True, (
                '%s bu yükte ateşlemedi; beklenen kümesine konamaz'
                % imza_anahtari)

    def test_atesmeyen_anahtarlar_sozlesmeye_konmadi(self, imzalar):
        """Dürüstlük şartı: bu yükte ateşlemeyen anahtar imzalanmaz.

        D20-D22'de reddedilen tam olarak buydu — anahtarı listeye ekleyip
        hiçbir sayfanın beklenen kümesine koymamak.
        """
        yol = os.path.join(
            KOK, 'docs/scofield/raw/OH/D23/arayuz/a2/atesleme.json')
        with io.open(kanit_gerekli(yol), encoding='utf-8') as f:
            d = json.load(f)
        atesmeyen = set(d['ozet']['bu_yukte_atesmeyen'])
        imzali = set()
        for tanim in imzalar.values():
            imzali.update(tanim.get('sozluk_anahtarlari') or ())
        cakisma = atesmeyen & imzali
        assert not cakisma, (
            'bu yükte ateşlemeyen anahtar(lar) imzalanmış: %s' % sorted(cakisma))


# =====================================================================
# a1 GERİLEMELERİ — bu aşamada onarıldı, tekrarı kilitlendi
# =====================================================================
class TestA1Gerilemeleri:
    """Aşama-1 denetiminde ÖLÇÜLEN iki gerileme ve bekçileri.

    İkisi de taban ağacında YEŞİL, a1 commit'inde KIRMIZIYDI; a1
    raporunun sembol taraması bu iki dosyayı kapsamamıştı.
    """

    # TABANDA SAĞLIKLI ölçülen sözlükler (ef527ae, aynı tarayıcıyla):
    # i18n_pages 146750<146761 · launch_site 9194<9205 · advanced
    # 62500<62511 · charts 36057<36068 · formulas 68268<68279.
    # i18n_common.js ve i18n_shell.js TABANDA DA bu tarayıcıya göre
    # bütün DEĞİL (443198>225689 ve en_sonu=-1); onlar bu dalganın
    # kusuru değildir ve hiçbir aktif bekçi onları böyle ayrıştırmıyor,
    # bu yüzden listeye ALINMADI — kapsam dürüstlüğü.
    SOZLUK_DOSYALARI = ('i18n_pages.js', 'i18n_launch_site.js',
                        'i18n_advanced.js', 'i18n_charts.js',
                        'i18n_formulas.js')

    @staticmethod
    def _blok_sonu(src, lang):
        """Sözlük ayrıştırıcılarının gördüğü blok sonu (tırnak sayan,
        yorumu ATLAMAYAN tarayıcı — test_faz6_i18n::_lang_block ile aynı).
        """
        m = re.search(r'\b%s\s*:\s*\{' % lang, src)
        if not m:
            return None
        i, derinlik, tirnak, kacis = m.end() - 1, 0, None, False
        while i < len(src):
            ch = src[i]
            if tirnak:
                if kacis:
                    kacis = False
                elif ch == '\\':
                    kacis = True
                elif ch == tirnak:
                    tirnak = None
            elif ch in '\'"`':
                tirnak = ch
            elif ch == '{':
                derinlik += 1
            elif ch == '}':
                derinlik -= 1
                if derinlik == 0:
                    return i
            i += 1
        return -1

    @pytest.mark.parametrize('dosya', SOZLUK_DOSYALARI)
    def test_dil_bloklari_ic_ice_gecmiyor_her_sozlukte(self, dosya):
        """EN bloğu TR bloğundan ÖNCE kapanmalı.

        ÖLÇÜLDÜ: a1, i18n_pages.js EN bloğuna `ÖH D21\'de onarıldı.`
        yorumunu koydu. Sözlüğü ayrıştıran bekçiler tırnak SAYAR ve
        yorumu atlamaz; tek kesme işareti bir dize açtı, EN bloğunun
        kapanışı TR bloğunun İÇİNE kaydı ve `pages_dict['en']` Türkçe
        metin döndürdü — üç bekçi birden kırmızı (taban ağacında YEŞİL).
        Kural PER-SATIR tırnak dengesi DEĞİLDİR (depoda zararsız,
        satırlar arası eşleşen kesmeler var); kural, ayrıştırıcının
        gördüğü SONUÇTUR.
        """
        src = oku('hrma/static/js/' + dosya)
        tr = re.search(r'\btr\s*:\s*\{', src)
        if not tr:
            pytest.skip('%s iki dilli blok yapısı taşımıyor' % dosya)
        en_sonu = self._blok_sonu(src, 'en')
        assert en_sonu is not None, dosya
        assert 0 < en_sonu < tr.start(), (
            '%s: EN sözlük bloğu TR bloğunun içine taşmış (en_sonu=%s, '
            'tr_basi=%s) — bir yorumdaki dengesiz kesme işareti '
            'ayrıştırıcıyı kaydırıyor'
            % (dosya, en_sonu, tr.start()))

    @pytest.mark.parametrize('anahtar', [
        'panelwarn.solid.nozzle_thermal_not_evaluated',
        'panelwarn.liquid.valve_regime_not_verified',
        'panelwarn.liquid.roughness_provenance_undeclared'])
    def test_panel_uyarilari_motor_ad_uzayini_isgal_etmiyor(self, sozluk,
                                                            anahtar):
        """`warn.<altsistem>.` ad uzayı BACKEND kodlarına ayrılmıştır.

        test_engine_warning_i18n sözleşmesi her `warn.*` çevirisinin
        hrma/**.py içinde bir üreticisi olmasını şart koşar. a1 üç
        PANEL uyarısını o ad uzayına koymuştu ve üçü de "yetim" ilan
        edildi. Metinler aynı; önek beyanın kaynağını söylüyor.
        """
        degerler = anahtar_dilleri(sozluk, anahtar)
        assert len(degerler) >= 2, (anahtar, len(degerler))
        eski = anahtar.replace('panelwarn.', 'warn.', 1)
        assert not anahtar_dilleri(sozluk, eski), (
            '%s hâlâ motor ad uyzayında duruyor' % eski)

    @pytest.mark.parametrize('sablon,anahtar', [
        ('liquid', 'panelwarn.liquid.valve_regime_not_verified'),
        ('liquid', 'panelwarn.liquid.roughness_provenance_undeclared'),
        ('solid', 'panelwarn.solid.nozzle_thermal_not_evaluated')])
    def test_a1_onarimlari_yerinde_duruyor(self, sablon, anahtar):
        """Ad uzayı değişti, ONARIM DEĞİŞMEDİ — üreten dal hâlâ orada."""
        s = oku('hrma/templates/%s.html' % sablon)
        assert "code: '%s'" % anahtar in s


# =====================================================================
# Kapsam bekçisi — ölçüm betiği ve kanıt dosyaları yerinde
# =====================================================================
class TestKanitDosyalari:
    @pytest.mark.parametrize('ad', ['once.json', 'sonra.json', 'olcum.py',
                                    'atesleme.json', 'atesleme_turetme.py',
                                    'mutasyon.json'])
    def test_kanit_dosyasi_var(self, ad):
        yol = os.path.join(KOK, 'docs/scofield/raw/OH/D23/arayuz/a2', ad)
        assert os.path.exists(kanit_gerekli(yol)), '%s kanıt dosyası yok' % ad
