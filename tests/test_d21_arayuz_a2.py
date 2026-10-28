# -*- coding: utf-8 -*-
"""ÖH Dalga-21 · arayuz kulvarı · aşama-2 bekçileri.

Her sınıf tek bir ölçülmüş kusuru mandallar. Ölçüm kanıtı:
``docs/scofield/raw/OH/D21/arayuz/a2/once.json`` (onarımdan önce) ve
``sonra.json`` (sonra); ters mutasyon kanıtı ``mutasyon.json``.

Kural (ÖK-05): bu dosyadaki her sınama, onarımı geçici olarak geri alınca
KIRMIZI olduğu gösterilmiş bir sınamadır.
"""
import json
import os
import re

import pytest
from tests.support.kanit import kanit_gerekli

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def oku(gorece):
    with open(os.path.join(KOK, gorece), encoding='utf-8') as f:
        return f.read()


def kod(metin):
    """JS/HTML yorumlarını söker.

    Bekçiler KODU ölçer, gerekçe metnini değil: bir onarımın kendi künyesi
    içinde eski kusurun adını anması normaldir (kayıt tutmak için gerekir),
    ama o ad koda geri sızarsa kusur geri gelmiş demektir.
    """
    metin = re.sub(r'/\*.*?\*/', ' ', metin, flags=re.S)
    metin = re.sub(r'^\s*//.*$', ' ', metin, flags=re.M)
    metin = re.sub(r'<!--.*?-->', ' ', metin, flags=re.S)
    return metin


# ==========================================================================
# P17B3-09 — katı özet PDF'i performansın tamamını 0,0 yazıyordu
# ==========================================================================
PERF_ALANLARI = ('thrust', 'specific_impulse', 'chamber_pressure',
                 'exit_velocity', 'mass_flow_rate', 'burn_time',
                 'total_impulse')


def _pdf_yuk_anahtarlari():
    blok = re.search(r'const _pdfAlanlar = \{(.*?)\n                \};',
                     oku('hrma/templates/solid.html'), re.S)
    assert blok, 'solid.html PDF yük bloğu bulunamadı'
    return re.findall(r'^\s{20}([a-z_]+):', blok.group(1), re.M)


class TestP17B309KatiPdfPerformansi:
    """PDF yükü çözücünün performansını taşır; sıfır uydurulmaz."""

    def test_yuk_performans_anahtarlarini_tasiyor(self):
        anahtarlar = set(_pdf_yuk_anahtarlari())
        eksik = {'max_thrust', 'specific_impulse', 'burn_time',
                 'total_impulse', 'chamber_pressure'} - anahtarlar
        assert not eksik, (
            'katı PDF yükü çözücünün performans alanlarını taşımıyor: %s'
            % sorted(eksik))

    def test_gercek_cozucu_yaniti_yedi_alandan_besini_cozuyor(self):
        """Ölçülen /calculate_solid gövdesiyle uçtan uca."""
        from hrma.export.pdf_generator import PDFReportGenerator
        capa = os.path.join(
            KOK, 'docs/scofield/raw/OH/D21/arayuz/a1/02_capa_SONRA.json')
        if not os.path.exists(kanit_gerekli(capa)):
            pytest.skip('çapa kaydı yok')
        with open(kanit_gerekli(capa), encoding='utf-8') as f:
            ham = json.load(f)['A_gecerli_govde'][
                'A2_kati_calculate_solid']['govde']
        cozucu = {}
        for k, v in ham.items():
            if isinstance(v, str):
                try:
                    cozucu[k] = float(v)
                except ValueError:
                    pass
        motor_data = {k: cozucu[k] for k in _pdf_yuk_anahtarlari()
                      if k in cozucu}
        cozulen = [a for a in PERF_ALANLARI
                   if PDFReportGenerator._resolve_performance(
                       a, {}, motor_data) is not None]
        assert len(cozulen) >= 5, (
            'ölçülen katı yanıtıyla yalnız %s çözülüyor' % cozulen)
        # Manşetteki dört büyüklüğün DÖRDÜ de gerçek sayı olmalı.
        for alan in ('thrust', 'specific_impulse', 'burn_time',
                     'total_impulse'):
            deger = PDFReportGenerator._resolve_performance(alan, {}, motor_data)
            assert deger is not None and deger > 0, alan

    def test_fail_closed_null_alan_yuke_konmaz(self):
        """Çözücü yayımlamadıysa anahtar yüke KONMAZ (sıfır uydurulmaz)."""
        govde = oku('hrma/templates/solid.html')
        assert "if (v !== null && v !== undefined && v !== '')" in govde
        blok = re.search(r'const _pdfAlanlar = \{(.*?)\n                \};',
                         govde, re.S).group(1)
        # Her performans alanı _sonlu() süzgecinden geçer.
        for alan in ('max_thrust', 'specific_impulse', 'burn_time',
                     'total_impulse', 'chamber_pressure'):
            assert re.search(r'%s: _sonlu\(_r\.' % alan, blok), alan

    def test_komsu_buyukluk_ikame_edilmiyor(self):
        """Aşırı kapanma ikizi: average_thrust 'Maximum Thrust' olamaz."""
        blok = kod(re.search(r'const _pdfAlanlar = \{(.*?)\n                \};',
                             oku('hrma/templates/solid.html'), re.S).group(1))
        assert 'average_thrust' not in blok
        assert 'isp_vacuum' not in blok


# ==========================================================================
# P17B2-07 — dört veritabanı rozeti açılışta YEŞİL "Connected"
# ==========================================================================
ROZET_SABLONLARI = ('hrma/templates/advanced.html', 'hrma/templates/solid.html')


class TestP17B207RozetAcilistaYesilDegil:

    @pytest.mark.parametrize('sablon', ROZET_SABLONLARI)
    def test_sablonda_onceden_baglandi_rozeti_yok(self, sablon):
        govde = oku(sablon)
        onceden = re.findall(
            r'<span class="database-status[^"]*status-connected[^"]*"',
            govde)
        assert not onceden, (
            '%s: %d rozet daha hiçbir denetim koşmadan YEŞİL "Connected"'
            % (sablon, len(onceden)))

    # ------------------------------------------------------------------
    # ÇEVRİLDİ (v3.0.1 K kulvarı, Ayberk tur 1). Aşağıdaki dört bekçi
    # ROZETİN kendisini (``database-status`` span'ları, "not checked"
    # metni, setNistStatus/setCeaStatus ve /api/database-status yoklaması)
    # şart koşuyordu. ÖLÇÜLDÜ (docs/scofield/raw/OH/V301/ayberk1/
    # kaynak-cea/gorsel_once.json, gerçek tarayıcı): rozetler yoklamadan
    # sonra HER makinede "NASA CEA OFFLINE / NIST WEBBOOK OFFLINE" diyordu
    # (CEA kolu DAİMA 'local', NIST ayrıştırıcısı HİÇ eşleşmiyor) ve hiçbiri
    # hesabın bir sayısının kaynağı değildi. Bekçiler bu yüzden KUSURU
    # kilitliyordu; rozet söküldü. P17B2-07'nin kazanımı (hesap koşmadan
    # kazanılmamış bir hüküm gösterilmez; canlı künye yazılınca sözlük onu
    # ezmez) YENİ veri kaynağı satırında aynen ölçülür.
    # ------------------------------------------------------------------
    @pytest.mark.parametrize('sablon, anahtar', [
        ('hrma/templates/advanced.html', 'adv.ds.fuelPending'),
        ('hrma/templates/advanced.html', 'adv.ds.oxidizerPending'),
        ('hrma/templates/solid.html', 'solid.ui.data_source_catalogue'),
    ])
    def test_baslangic_durumu_notr_ve_adlandirilmis(self, sablon, anahtar):
        govde = oku(sablon)
        m = re.search(r'<div class="data-source-line"[^>]*data-i18n="%s">'
                      r'([^<]*)</div>' % re.escape(anahtar), govde)
        assert m, (sablon, anahtar)
        metin = m.group(1)
        # Kazanılmamış hüküm yok: bağlantı/çevrimdışı iddiası basılmaz.
        for yasak in ('Connected', 'Offline', 'connected', 'offline'):
            assert yasak not in metin, (sablon, metin)
        assert metin.startswith('Data source:'), metin
        assert not re.search(r'class="[^"]*\b(?:database-status|cea-status|nist-status)\b', govde)

    def test_gercek_durum_yazilinca_sozluk_ustune_yazamaz(self):
        govde = oku('hrma/templates/advanced.html')
        i = govde.index('function renderDataSourceLines()')
        j = govde.index('\n        }\n', i)
        blok = govde[i:j]
        # Canlı künye iki satıra da yazılınca data-i18n kaldırılır.
        assert blok.count("removeAttribute('data-i18n')") == 2, blok

    def test_sozluk_anahtarlari_EN_ve_TR(self):
        adv = oku('hrma/static/js/i18n_advanced.js')
        pages = oku('hrma/static/js/i18n_pages.js')
        for anahtar in ("'adv.ds.fuelPending'", "'adv.ds.oxidizerPending'"):
            assert adv.count(anahtar) == 2, anahtar
        assert pages.count("'solid.ui.data_source_catalogue'") == 2
        # Sökülen rozet anahtarları sözlükte ölü kalmadı.
        for anahtar in ("'adv.txt.ceaNotChecked'", "'adv.txt.nistNotChecked'"):
            assert adv.count(anahtar) == 0, anahtar
        for anahtar in ("'solid.ui.nasa_cea_not_checked'",
                        "'solid.ui.nist_webbook_not_checked'"):
            assert pages.count(anahtar) == 0, anahtar

    def test_gercek_denetim_yolu_hala_yesile_donebiliyor(self):
        """Aşırı kapanma ikizi: satır gerçek bir kaynağı SÖYLEYEBİLMELİ.

        Hesap öncesi oksitleyici satırı /api/oxidizer-properties künyesiyle,
        hesap sonrası yakıt satırı /calculate data_sources bloğuyla yazılır
        (sayfa artık /api/database-status yoklamaz).
        """
        govde = oku('hrma/templates/advanced.html')
        assert 'setOxidizerSourceKunye(result);' in govde
        assert 'r.data_sources' in govde
        assert "fetch('/api/database-status')" not in govde


# ==========================================================================
# P17B2-08 — güverte, çözücünün malzemesini düşürüp kendi varsayılanını
# gönderiyor; uyarı YALNIZ konsolda
# ==========================================================================
class TestP17B208MalzemeUyusmazligiEkranda:

    def test_dusen_oneri_withheld_kanalina_yazilir(self):
        govde = oku('hrma/static/js/analysis_dock.js')
        assert 'solver_value_not_in_option_list' in govde
        # Kayıt SELECT dalında, "listede yok" cümlesiyle aynı blokta.
        i = govde.find('solver_value_not_in_option_list')
        j = govde.find('seçeneği listede yok')
        assert -1 < i < j, 'kayıt SELECT dalında değil'

    def test_gerekce_ekranda_gorunur_metin(self):
        govde = oku('hrma/static/js/analysis_dock.js')
        assert 'ad-withheld-note' in govde
        blok = re.search(r'function paintFieldSources\(.*?\n    \}',
                         govde, re.S).group(0)
        assert 'insertAdjacentHTML' in blok
        assert 'ad-withheld-note' in blok
        # Görünür olmalı: display:block, title değil.
        assert 'display:block' in blok
        # Görünür satırın koşulu, ipucuna gerekçeyi ekleyen koşulun AYNISI
        # olmalı. (Ters mutasyon dersi: `if (false && ...)` yazıldığında dize
        # taraması hâlâ yeşil kalıyordu — koşulun kendisi ölçülüyor.)
        kosul = re.search(
            r'if \(([^)]*)\) \{\n\s*slot\.insertAdjacentHTML', blok)
        assert kosul, 'görünür satırın koşulu okunamadı'
        assert kosul.group(1).strip() == 'withheld && withheld[fid]', (
            kosul.group(1))
        # Aynı koşul ipucu dalında da kullanılıyor (tek kaynak).
        assert blok.count('withheld && withheld[fid]') == 2

    def test_sessiz_geri_dusme_kapisi_duruyor(self):
        """Bilgi kaybı ikizi: alan hâlâ EZİLMİYOR, konsol iletisi duruyor.

        ÖH D25 fix-23 — ÇEVRİLDİ (gerekçe ÖLÇÜLDÜ). Eski satır
        ``blok.count('el.value = want;') == 1`` sayıyordu: "bulunamayan
        dalda alana yazma yok" ÖZELLİĞİNİ, iki dalın TOPLAMINDAKİ literal
        sayısıyla vekâleten ölçüyordu. D24 arayuz a3 (``f447a60``,
        P17B2-08 alias çözümü) ``if (found)`` dalına ikinci bir
        ``el.value = want;`` yazınca sayım 2 oldu ve bekçi kırmızı verdi;
        oysa ölçülen özellik BOZULMADI (bulunamayan dalda hâlâ hiçbir
        atama yok). Vekil sayım yerine özelliğin kendisi ölçülüyor ve
        iddia DARALIYOR: eski hâli yalnız tek bir literal biçimini
        (``el.value = want;``) görüyordu, ``el.value = el.dataset.x;``
        gibi başka bir sessiz ezmeyi kaçırırdı; yeni hâli bulunamayan
        dalda ``el.value``ye YAPILAN HER ATAMAYI yakalar.
        """
        govde = oku('hrma/static/js/analysis_dock.js')
        assert 'alan değiştirilmedi (görünen değer gönderilir)' in govde
        m = re.search(
            r'\n                if \(found\) \{\n(.*?)'
            r'\n                \} else \{\n(.*?)'
            r'\n                \}\n                return;', govde, re.S)
        assert m, 'select dalının if(found)/else gövdesi okunamadı'
        bulundu, bulunamadi = m.group(1), m.group(2)
        # 1) Bulunamayan dalda `el.value`ye HİÇBİR atama yok (okuma serbest:
        #    `el.value == null`, `String(el.value)` gönderileni künyeler).
        atama = re.findall(r'el\.value\s*=(?!=)', bulunamadi)
        assert not atama, (
            'bulunamayan dalda alana atama belirdi (%d adet) — sessiz geri '
            'düşme geri geldi: ekranda görünen değer ile gönderilen değer '
            'ayrışır' % len(atama))
        # 2) Gerekçe hâlâ hem ekran kanalına hem konsola yazılıyor.
        assert 'withheld[k]' in bulunamadi, 'ekran kanalı (withheld) kayboldu'
        assert 'console.warn' in bulunamadi, 'konsol iletisi kayboldu'
        # 3) Bulunan dalda yazılan değer YİNE seçenek listesinden geliyor:
        #    ya doğrudan eşleşen `want`, ya alias çözümünün seçtiği seçenek.
        assert 'el.value = want;' in bulundu
        assert 'el.value = opts[i].value;' in govde, (
            'alias dalı seçenek değerini yazmıyor (P17B2-08 tek kaynak)')


# ==========================================================================
# P17B2-05 — Ayarlar penceresi okunabilirliği
# ==========================================================================
class TestP17B205AyarlarOkunabilirligi:

    def test_aciklama_satiri_13px_ve_dim_murekkep(self):
        govde = oku('hrma/static/js/settings_panel.js')
        blok = kod(re.search(r'function descLine\(key, fallback\) \{(.*?)\n    \}',
                             govde, re.S).group(1))
        # ÖH D23 / P17B2-05 — ÇEVRİLDİ (gerekçe): bu satır ÇIPLAK
        # `font-size:13px` literalini arıyordu. D23'te pencerenin yazı
        # ölçeği TEK KAYNAĞA bağlandı (`PX_TABAN`), çünkü D21'den sonra da
        # 22 görünür satırın 9'u 13 px'in altında ölçülüyordu
        # (docs/scofield/raw/OH/D23/electron/a1/once_ayarlar.json). Literali
        # arayan bu bekçi, tek-kaynak düzenlemesini kusur sanıyordu; sınadığı
        # ÖZELLİK korundu ve güçlendirildi: boyut tek kaynaktan gelir VE o
        # kaynak 13 px'in altına düşemez.
        assert re.search(r"font-size:' \+ PX_TABAN \+ 'px", blok), \
            'gizlilik beyanı boyutu tek kaynaktan (PX_TABAN) gelmiyor'
        _taban = re.search(r'var PX_TABAN = (\d+);', govde)
        assert _taban and int(_taban.group(1)) >= 13, \
            'okunabilirlik tabanı 13 px altına düştü'
        assert '--hd-ink-faint' not in blok, 'en sönük mürekkep hâlâ kullanımda'
        assert '--hd-ink-dim' in blok

    def test_kodda_en_sonuk_murekkep_kalmadi(self):
        """Ölçülen 2,75:1'in kaynağı `--hd-ink-faint` idi; kodda kalmadı."""
        govde = kod(oku('hrma/static/js/settings_panel.js'))
        assert govde.count('--hd-ink-faint') == 0

    def test_sayac_ve_surum_beyani_da_buyudu(self):
        govde = oku('hrma/static/js/settings_panel.js')
        for imza in ("var counter = el('div',", "var vBasis = el('span',"):
            i = govde.find(imza)
            assert i != -1, imza
            blok = kod(govde[i:i + 320])
            assert 'font-size:11px' not in blok, imza
            assert '--hd-ink-faint' not in blok, imza
            assert '--hd-ink-dim' in blok, imza

    def test_dil_ve_surum_yarilari_kapali_kalir(self):
        """Ölçülen üç kusurun ikisi önceki dalgalarda kapandı; geri gelmesin."""
        shell = oku('hrma/static/js/i18n_shell.js')
        tr = shell.find('\n        tr: {')
        assert tr > 0
        assert len(re.findall(r"'shell\.bug\.", shell[:tr])) >= 45
        assert len(re.findall(r"'shell\.bug\.", shell[tr:])) >= 45
        # Sürüm okuyucu TEK KAYNAK (bug_report.detectVersion).
        assert 'HRMABugReport' in oku('hrma/static/js/settings_panel.js')


# ==========================================================================
# P17B2-01 — HUD yapısal hükmü YALNIZ renkle taşınıyordu
# ==========================================================================
class TestP17B201HukumRenkDisiKanalda:

    def test_kart_hukum_sozcugunu_tasiyor(self):
        govde = oku('hrma/static/js/app.js')
        assert 'stateWord' in govde
        assert 'hd-state-word' in govde

    def test_aria_label_hukmu_iceriyor(self):
        govde = oku('hrma/static/js/app.js')
        blok = re.search(r'const kartEtiketi = (.*?);\n', govde, re.S).group(1)
        assert 'm.stateWord' in blok
        assert 'aria-label' in govde

    def test_sozcuk_sunucunun_belirteci_siniflandirma_uretilmiyor(self):
        """Aşırı kapanma ikizi: eşik/sınıflandırma burada TÜRETİLMEZ."""
        govde = oku('hrma/static/js/app.js')
        blok = re.search(r'stateWord: \((.*?)\n            note:', govde,
                         re.S).group(1)
        assert 'structSafety.status' in blok
        for yasak in ('> 1', '< 1', 'UNSAFE', 'MARGINAL'):
            assert yasak not in blok, yasak

    def test_renk_kanali_kaldirilmadi(self):
        """Bilgi kaybı ikizi: data-state bağlaması duruyor."""
        assert 'HRMAHud.bindState' in oku('hrma/static/js/app.js')

    def test_hudsuz_yolda_da_sozcuk_basiliyor(self):
        """HUD katmanı yoksa renk kanalı hiç yok; sözcük TEK kanal."""
        govde = oku('hrma/static/js/app.js')
        i = govde.find("if (typeof window.HRMAHud === 'undefined')")
        assert i != -1
        blok = govde[i:i + 900]
        assert 'm.stateWord' in blok, 'HUD\'suz yolda hüküm sözcüğü düşüyor'


# ==========================================================================
# P17B1-08 — `http_hatalari` ölçülüp hiçbir denetime dönüşmüyordu
# ==========================================================================
class TestP17B108HttpHataKapisi:

    def test_denetim_alan_yoksa_gecmez(self):
        from tools.browser_harness import denetimler
        d = denetimler.http_hata_denetimi({})
        assert d.gecti is False
        assert 'ölçüm yapılmadı' in d.ozet

    def test_denetim_sifirda_gecer_pozitifte_kalir(self):
        from tools.browser_harness import denetimler
        assert denetimler.http_hata_denetimi({'http_hata_sayisi': 0}).gecti
        kirmizi = denetimler.http_hata_denetimi({
            'http_hata_sayisi': 2,
            'http_hatalari': [{'durum': 500, 'url': '/api/cad'}]})
        assert kirmizi.gecti is False
        assert '500' in kirmizi.ozet

    def test_rapor_hukmu_http_hatasinda_kapiyi_kapatir(self):
        from tools.browser_harness import denetimler
        temiz = {'sayfalar': [{'gecti': True, 'http_hata_sayisi': 0}]}
        assert denetimler.rapor_hukmu(temiz)
        assert denetimler.cikis_kodu(temiz) == 0
        kirli = {'sayfalar': [{'gecti': True, 'http_hata_sayisi': 1}]}
        assert denetimler.rapor_hukmu(kirli) is False
        assert denetimler.cikis_kodu(kirli) == 1

    def test_eski_hukum_kurallari_bozulmadi(self):
        from tools.browser_harness import denetimler
        assert denetimler.rapor_hukmu({'sayfalar': []}) is False
        assert denetimler.rapor_hukmu(
            {'sayfalar': [{'gecti': False}]}) is False
        assert denetimler.rapor_hukmu(
            {'sayfalar': [{'gecti': True}],
             'denetimler': [{'gecti': False}]}) is False


# ==========================================================================
# P17B1-09 — 3B sahne oturum dilinden bağımsız SABİT etiket basıyordu
# ==========================================================================
class TestP17B109SahneOturumDilindeYazar:

    SABIT_ETIKETLER = ("'ızgara '", "'ØC iç '", "'kontur: çözücü'",
                       "'kontur: yerel üretim'",
                       "'soğutma kanalları: veri yok'")

    def test_sabit_turkce_etiket_kalmadi(self):
        govde = kod(oku('hrma/static/js/motor_viz3d.js'))
        kalan = [e for e in self.SABIT_ETIKETLER if e in govde]
        assert not kalan, 'sahnede sabit Türkçe etiket: %s' % kalan

    def test_etiketler_T_kanalindan_geciyor(self):
        govde = oku('hrma/static/js/motor_viz3d.js')
        for anahtar in ('viz3d.badge.grid', 'viz3d.badge.inner',
                        'viz3d.badge.outer', 'viz3d.chip.coolingNoData',
                        'viz3d.chip.contourSolver', 'viz3d.chip.contourLocal'):
            assert ("T('%s'" % anahtar) in govde, anahtar

    def test_sozlukte_EN_ve_TR_karsiliklari_var(self):
        ortak = oku('hrma/static/js/i18n_common.js')
        for anahtar in ('viz3d.badge.grid', 'viz3d.badge.inner',
                        'viz3d.badge.outer', 'viz3d.chip.coolingNoData',
                        'viz3d.chip.contourSolver', 'viz3d.chip.contourLocal'):
            assert ortak.count("'%s':" % anahtar) == 2, anahtar
        # Türkçe karşılıklar gerçekten Türkçe (bilgi kaybı ikizi).
        for tr in ('ızgara', 'soğutma kanalları: veri yok',
                   'kontur: çözücü', 'kontur: yerel üretim'):
            assert tr in ortak, tr


# ==========================================================================
# P17B2-03 — dil düğmesi bir uyarı satırını KALICI siliyordu (ÇÜRÜTÜLDÜ:
# kökü D17'de kapandı; bu sınıf kapanmayı MANDALLIYOR, yeniden açılmasın)
# ==========================================================================
class TestP17B203DilDugmesiUyariSilmiyor:

    def test_paylasilan_alanlar_dil_degisiminde_yazilmiyor(self):
        """ÇEVRİLDİ (ÖH D33-KOLAY · OH-D32-11).

        ESKİ SÖZLEŞME: ``updateMixtureDensity`` gövdesinde paylaşılan üç
        alana yazımın `_karisimSecili` kapısının ardında olduğu ölçülüyordu.
        Sözleşme fonksiyonun VARLIĞINI şart koşuyordu; fonksiyon ise
        OH-D31-05'ten beri erişilemez paneli okuyup her dil değişiminde
        TypeError fırlatıyordu (ölçüm: raw/OH/D33/arayuz-panel/a1/once.json
        · M2b). YENİ SÖZLEŞME daha güçlü: yazım yolunun KENDİSİ yok.
        """
        adv = oku('hrma/templates/advanced.html')
        kodu = re.sub(r'<!--.*?-->', '', adv, flags=re.S)
        assert not re.search(r'function updateMixtureDensity\s*\(', kodu), (
            'ölü karışım fonksiyonu geri geldi (OH-D32-11)')
        m = re.search(r'if \(I18N\.onChange\) I18N\.onChange\(function \(\) \{'
                      r'(.*?)\n            \}\);', kodu, re.S)
        assert m, 'dil değişimi geri çağırımı bulunamadı'
        zincir = re.sub(r'//[^\n]*', '', m.group(1))
        for alan in ('fuel_density', 'regression_a', 'regression_n'):
            assert alan not in zincir, (
                'dil değişimi zinciri paylaşılan alan %s yazıyor' % alan)

    def test_dil_degisimi_zinciri_kesilmiyor(self):
        """Bilgi kaybı ikizi: zincirin SONU (veritabanı rozeti) da çalışır.

        ÖLÇÜLDÜ (a1/once.json · M2b): ``updateMixtureDensity`` fırladığı için
        ``catch`` zinciri kesiyor, ``checkDatabaseStatus()`` HİÇ
        çalışmıyordu; yakıt/oksitleyici veritabanı rozeti dil değişince eski
        dilde ve eski durumda kalıyordu.
        """
        adv = oku('hrma/templates/advanced.html')
        kodu = re.sub(r'<!--.*?-->', '', adv, flags=re.S)
        m = re.search(r'if \(I18N\.onChange\) I18N\.onChange\(function \(\) \{'
                      r'(.*?)\n            \}\);', kodu, re.S)
        # Künye yorumları kusurun ADINI anıyor; bekçi KODU ölçer.
        zincir = re.sub(r'//[^\n]*', '', m.group(1))
        cagrilar = re.findall(r"typeof (\w+) === 'function'\)", zincir)
        # v3.0.1 K: son halka checkDatabaseStatus (rozet yoklaması) idi;
        # rozet söküldü, halkanın yerini aynı işi (dil değişince kaynak
        # künyesini yeniden yazmak) yapan refreshDataSourceLines aldı.
        assert cagrilar[-1] == 'refreshDataSourceLines', cagrilar
        assert 'updateMixtureDensity' not in zincir, (
            'fırlatan ölü çağrı zincire geri kondu')

    def test_kaybolan_uyarinin_iki_dilde_de_karsiligi_var(self):
        ortak = oku('hrma/static/js/i18n_common.js')
        assert ortak.count("'warn.hybrid.htpb_coeff_bias'") == 2

    def test_uyari_listesi_dil_degisiminde_yeniden_cizilmiyor(self):
        """Uyarılar düz metindir (data-i18n yok) — I18N.apply silemez."""
        appjs = oku('hrma/static/js/app.js')
        blok = re.search(r'const item = \(label, text, cls\) =>(.*?);\n',
                         appjs, re.S).group(1)
        assert 'data-i18n' not in blok
        assert 'warnToText' in blok
