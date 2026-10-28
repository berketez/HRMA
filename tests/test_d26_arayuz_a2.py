# -*- coding: utf-8 -*-
"""ÖH Dalga-26 / arayuz aşama-2 — ONARIM BEKÇİLERİ.

Her iddia, o kalemin ÖLÇÜLEN kusurunu görür: onarımı geri alan bir
ters-mutasyon testi KIRMIZI yapmalıdır (kanıt:
``docs/scofield/raw/OH/D26/arayuz/a2/mutasyon.json``).

Kapsanan kalemler
-----------------
P5B4-30   karo matris geometrisi tek sahipli (sunucu yayımlar, JS okur)
P5B4-35   atıf metni kopyaları kilitli + dil karışımı giderildi (kısmi)
OH-D25-22 ters-yön envanteri yalnız ÇALIŞAN kodu sayar (yorum/ölü dal)
OH-D25-12 advanced.html custom oksitleyici ölü yolu fail-closed
P11B4-06  hükmün gerekçesi çiğ makine anahtarı değil
P15B4-04  solid/liquid/advanced ihraç gövdeleri motor_type gönderir
OH-B3-03  /analyze_structural_safety defaults_applied ekranda
OH-B3-02  sağır blok envanteri (flow/correlation/cooling/feed/wall_profile)
P11B3-15  mesh yakınsaması rozet katında, zaman adımı rozeti kapsamlı
P11B3-16  ortam sıcaklığı tek kaynakta + sahibi ilan ediliyor
P11B3-18  CFD "yankılanan girdiler" tablosu SÜZMEZ, hepsini basar
(ek)      U.esc kapısı: flow_panel'in çağırdığı yardımcı güvertede VAR
"""
import json
import re
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
TPL = KOK / 'hrma' / 'templates'

_YORUM_BLOK = re.compile(r'/\*.*?\*/', re.S)
_YORUM_SATIR = re.compile(r'^[ \t]*//.*$', re.M)


def govde(yol):
    """Yorumları sökülmüş kaynak — iddia YALNIZ çalışan koda bakar.

    (a1 dersi: onarımın kendi açıklama yorumları ölçümü şişiriyordu.)
    """
    metin = Path(yol).read_text(encoding='utf-8')
    return _YORUM_SATIR.sub('', _YORUM_BLOK.sub('', metin))


def ham(yol):
    return Path(yol).read_text(encoding='utf-8')


# ===========================================================================
# P5B4-30 — karo matris geometrisinin TEK sahibi
# ===========================================================================
class TestP5B430KaroGeometrisiTekSahipli:
    """ÖLÇÜLDÜ (taban 7751531, ``a2/once.json``): geometri İKİ yerde
    yaşıyordu — ``tile_cache.matrix_size`` (tamsayı ceil) ve
    ``launch_site_globe.js`` (``Math.ceil(360.0/span)``, float). Sayısal
    ayrışma z0-z7'de YOKTU; kusur SAHİPLİKTEDİR ve JS dosyasının kendi
    yorumu bunu itiraf ediyordu ("İkisi değişirse birlikte
    güncellenmeli"). Artık sunucu yayımlar, istemci okur."""

    def test_sunucu_geometriyi_yayimliyor(self):
        from hrma.analysis import tile_cache
        g = tile_cache.matrix_geometry()
        assert g['levels'], 'matrix_geometry seviye yayımlamıyor'
        # GIBS WMTSCapabilities.xml ile birebir çapa (modülün kendi künyesi)
        assert (g['levels']['0']['matrix_width'],
                g['levels']['0']['matrix_height']) == (2, 1)
        assert (g['levels']['3']['matrix_width'],
                g['levels']['3']['matrix_height']) == (10, 5)
        assert (g['levels']['7']['matrix_width'],
                g['levels']['7']['matrix_height']) == (160, 80)
        # Sarmalama/kırpma sözleşmesi de yayımlanır (istemci icat etmesin)
        assert g['wrap_x'] is True and g['clamp_y'] is True

    def test_yayin_matrix_size_ile_ayni(self):
        """Yayımlanan sayı, modülün KENDİ hesabıyla bit-aynı olmalı."""
        from hrma.analysis import tile_cache
        g = tile_cache.matrix_geometry()
        for z_str, lv in g['levels'].items():
            z = int(z_str)
            mw, mh = tile_cache.matrix_size(z)
            assert (lv['matrix_width'], lv['matrix_height']) == (mw, mh), (
                f'z={z}: yayımlanan matris {lv} ile matrix_size({z}) '
                f'= {(mw, mh)} ayrışıyor')
            assert lv['span_deg'] == tile_cache.tile_span_deg(z)

    def test_uc_tile_matrix_alanini_gonderiyor(self):
        from hrma.app import app
        with app.test_client() as c:
            r = c.get('/api/tile/cache/status')
            assert r.status_code == 200
            j = r.get_json()
        assert 'tile_matrix' in j, (
            "/api/tile/cache/status gövdesinde `tile_matrix` yok — "
            "önyükleme sözleşmesi yok, istemci geometriyi yine türetir")
        assert j['tile_matrix']['levels']['7']['matrix_width'] == 160

    def test_istemci_geometriyi_TURETMIYOR(self):
        """TERS-MUTASYON ÇAPASI: JS kendi ceil türetimini geri koyarsa
        bu iddia KIRMIZI olur."""
        s = govde(JS / 'launch_site_globe.js')
        assert 'Math.ceil(360.0 /' not in s.replace(' ', ' '), (
            'launch_site_globe.js matris GENİŞLİĞİNİ yine kendi türetiyor')
        assert not re.search(r'Math\.ceil\(\s*360\.0\s*/', s), (
            'launch_site_globe.js matris genişliğini yine türetiyor')
        assert not re.search(r'Math\.ceil\(\s*180\.0\s*/', s), (
            'launch_site_globe.js matris yüksekliğini yine türetiyor')
        assert not re.search(r'288\.0\s*/\s*Math\.pow', s), (
            'launch_site_globe.js karo açıklığını yine türetiyor')

    def test_istemci_sunucudan_okuyor_ve_fail_closed(self):
        s = govde(JS / 'launch_site_globe.js')
        assert 'tile_matrix' in s, 'istemci sunucu alanını okumuyor'
        assert 'tileGeomYukle' in s, 'önyükleme çağrısı yok'
        # Geometri yoksa karo İSTENMEZ (uydurma kutu çizilmez)
        assert re.search(r'if\s*\(!lv\)\s*\{[^}]*return', s), (
            'geometri yokken karo turu fail-closed dönmüyor')
        assert re.search(r'if\s*\(!\(span\s*>\s*0\)\)\s*return null', s), (
            '_makeTileMesh açıklık bilinmezken yama kurmayı reddetmiyor')


# ===========================================================================
# P5B4-35 — atıf metni: kopyalar kilitli, dil karışımı yok
# ===========================================================================
class TestP5B435AtifKopyalari:
    """ÖLÇÜLDÜ (``a2/once.json``): atıf dizesi üç yerde YAŞIYOR
    (tile_cache.py katman tablosu, i18n_launch_site.js EN bloğu,
    launch_site.html ``data-i18n`` yedeği) ve ``viirs`` kaydı ayrıca
    yarı Türkçeydi. Ekrandaki metnin kaynağı i18n'dir (ÖH D21 /
    P12aB4-19 kararı, D24 künye düzeltmesi); bu yüzden literal TEKE
    indirilemez — ama SESSİZ KAYMA kapatılabilir: üç kopya artık
    birbirine kilitlidir, biri değişip diğeri kalırsa test kırmızı."""

    def _tile_cache_atfi(self):
        from hrma.analysis import tile_cache
        return tile_cache.LAYERS['bluemarble']['attribution']

    def test_uc_kopya_birebir_ayni(self):
        sunucu = self._tile_cache_atfi()
        i18n = ham(JS / 'i18n_launch_site.js')
        m = re.search(r"'site\.tileAttribution':\s*'([^']*)'", i18n)
        assert m, 'i18n_launch_site.js EN atıf anahtarı bulunamadı'
        en = m.group(1).replace('\\u2014', '—')
        assert en == sunucu, (
            f'atıf kopyaları AYRIŞTI:\n  tile_cache.py: {sunucu!r}\n'
            f'  i18n (EN)    : {en!r}')
        html = ham(TPL / 'launch_site.html')
        assert sunucu in html, (
            'launch_site.html yedek metni sunucu kaydından ayrıştı — '
            'i18n yüklenmeden önce ekranda BAŞKA bir atıf görünür')

    def test_sunucu_kayitlari_tek_dilde(self):
        """``attribution`` bir API alanıdır; kayıtlar aynı dilde konuşur."""
        from hrma.analysis import tile_cache
        turkce = re.compile(r'[çğıöşüÇĞİÖŞÜ]|tarihli|bulut riski')
        for ad, cfg in tile_cache.LAYERS.items():
            atif = cfg.get('attribution') or ''
            assert not turkce.search(atif), (
                f"{ad}: `attribution` API alanı Türkçe parça taşıyor "
                f"({atif!r}); kardeş kayıtlar İngilizce")


# ===========================================================================
# OH-D25-22 — ters-yön envanteri yalnız ÇALIŞAN kodu sayar
# ===========================================================================
class TestOHD2522CanliKodKilidi:
    """ÖLÇÜLDÜ (``a2/once.json``, ``_envanter_metinden`` CANLI çağrılarak):
    ``kanit_yorum_okuma_sayiliyor = 1`` ve
    ``kanit_olu_dal_okuma_sayiliyor = 1``. Yani bir alanı yalnız yorumda
    anmak ya da ``if (false && …)`` içinde anmak, ters yön iddiasına göre
    'panel bu alanı basıyor' demekti — D24 fix aşaması raporunun (bulgu 3)
    adlandırdığı kaçak."""

    def _env(self):
        from tests.test_wave3_contract import _envanter_metinden
        return _envanter_metinden

    def test_yorumdaki_ad_okuma_sayilmaz(self):
        env = self._env()
        metin = "// d.gizli_alan burada yalnız YORUMDA geçiyor\nconst x = 1;"
        assert 'gizli_alan' not in env(metin), (
            'yorumda geçen alan adı hâlâ "panel basıyor" sayılıyor')

    def test_blok_yorumdaki_ad_okuma_sayilmaz(self):
        env = self._env()
        metin = "/* eski sürüm d.eski_alan basıyordu */\nconst x = 1;"
        assert 'eski_alan' not in env(metin)

    def test_olu_daldaki_ad_okuma_sayilmaz(self):
        env = self._env()
        metin = "if (false && d.olu_alan) { html += d.olu_alan; }"
        assert 'olu_alan' not in env(metin), (
            '`if (false && …)` mutasyonu hâlâ yakalanmıyor — dizge '
            'yerinde kaldığı için bekçi kusuru göremiyor')

    def test_sifir_kosullu_olu_dal_da_sokulur(self):
        env = self._env()
        assert 'sifir_alan' not in env("if (0) { x = d.sifir_alan; }")

    def test_GERCEK_okuma_hayatta_kalir(self):
        """Sıkılaştırma yanlış kırmızı ÜRETMEZ: canlı okuma kalır."""
        env = self._env()
        metin = ("// d.alan hakkında bir yorum\n"
                 "const v = d.alan;\n")
        assert 'alan' in env(metin), (
            'sıkılaştırma GERÇEK okumayı da sildi')

    def test_dizgedeki_cift_slash_yorum_sanilmaz(self):
        """`https://` gibi diziler yorum sökümünü tetiklememeli."""
        env = self._env()
        metin = "const u = 'https://x/y'; const v = d.gercek_alan;"
        assert 'gercek_alan' in env(metin)

    def test_urun_panellerinde_envanter_taban_ustunde(self):
        """Sıkılaştırma çıkarımı BOZMADI (ölçülen maliyet 2-11 ad)."""
        from tests.test_wave3_contract import (
            TestPanelOkumaEnvanteri, _okuma_envanteri)
        for rel, taban in TestPanelOkumaEnvanteri.ENVANTER_TABANI.items():
            boy = len(_okuma_envanteri(rel))
            assert boy >= int(taban * 0.7), (
                f'{rel}: sıkılaştırma envanteri {boy} ada düşürdü '
                f'(taban {taban}) — çıkarım bozuldu')


# ===========================================================================
# OH-D25-12 — advanced.html custom oksitleyici ölü yolu fail-closed
# ===========================================================================
class TestOHD2512CustomOksitleyici:
    """ÖLÇÜLDÜ (``a2/once.json``): ölü dal ``densityInput.value = '1000'``
    ve ``viscosityInput.value = '0.001'`` yazıyordu; seçenek zaten
    ``disabled`` (sunucu 'custom' akışkanını çözmüyor)."""

    def test_yer_tutucu_sayilar_yok(self):
        s = govde(TPL / 'advanced.html')
        assert not re.search(r"densityInput\.value\s*=\s*'1000'", s), (
            'custom dalı yine 1000 kg/m³ yer tutucusu yazıyor')
        assert not re.search(r"viscosityInput\.value\s*=\s*'0\.001'", s), (
            'custom dalı yine 0,001 Pa·s yer tutucusu yazıyor')

    def test_dal_adiyla_reddediyor(self):
        s = govde(TPL / 'advanced.html')
        assert 'adv.msg.customOxidizerUnsupported' in s, (
            'custom dalı durumu ADIYLA reddetmiyor')
        assert re.search(r"densityInput\.value\s*=\s*''", s), (
            'custom dalı alanı temizlemiyor — eski sayı ekranda kalır')

    def test_i18n_anahtari_EN_ve_TR_bloklarinda(self):
        s = ham(JS / 'i18n_advanced.js')
        assert s.count("'adv.msg.customOxidizerUnsupported'") == 2, (
            'yeni anahtar EN ve TR bloklarının İKİSİNDE de olmalı')


# ===========================================================================
# P11B4-06 — hükmün gerekçesi çiğ makine anahtarı değil
# ===========================================================================
class TestP11B406HukumGerekcesi:
    """ÖLÇÜLDÜ (``a2/once.json``): ``verdict_withheld_reasons`` ve
    ``not_evaluated`` listeleri ekrana OLDUĞU GİBİ iniyordu — kullanıcı
    "Why no acceptance was issued" altında
    ``safety_factor_is_tautological`` okuyordu."""

    def test_cevirici_var_ve_listelere_bagli(self):
        # ÖH D27 · OH-D26-14: bu düğümün adı U+0456 (KİRİL i) ile
        # bitiyordu; ekranda Latin ``i``den ayırt edilemediği için düğüm
        # elle yazıldığında pytest HATA vermeden "no tests ran" dönüyor,
        # bekçi hiç koşmadan yeşil görünüyordu. Ad saf ASCII'ye çevrildi
        # (aynı çevrim a2 mutasyon düzeneğinde de yapıldı); depo geneli
        # tarayıcı: tests/test_d27_bekci_cevirisi_a1.py.
        s = govde(JS / 'panels' / 'structural_panel.js')
        assert 'function hukumKoduMetni' in s, 'kod çevirici yok'
        assert 'function degerlendirilmeyenMetni' in s
        assert 'reasons.map(hukumKoduMetni)' in s, (
            'gerekçe listesi hâlâ HAM basılıyor')
        assert 'notEval.map(degerlendirilmeyenMetni)' in s, (
            '`not_evaluated` listesi hâlâ HAM basılıyor')

    def test_bilinen_kod_cumleye_cevrilir_ham_anahtar_KALIR(self):
        """ÖK-22: künye izlenebilirliği daralmaz — ham anahtar kalır."""
        s = govde(JS / 'panels' / 'structural_panel.js')
        assert 'safety_factor_is_tautological: [' in s
        assert "return T(rec[0], rec[1]) + ' (' + ad + ')';" in s, (
            'çeviri ham anahtarı GİZLİYOR — izlenebilirlik daraldı')

    def test_bilinmeyen_kod_GIZLENMEZ(self):
        s = govde(JS / 'panels' / 'structural_panel.js')
        assert 'if (!rec) return ad;' in s, (
            'sözlükte olmayan kod için panel cümle uyduruyor ya da '
            'kodu düşürüyor — fail-closed değil')

    def test_i18n_anahtarlari_EN_ve_TR(self):
        s = ham(JS / 'i18n_common.js')
        for anahtar in ('panel.structural.reasonTautological',
                        'panel.structural.reasonWallTempNotComputed',
                        'panel.structural.reasonMaterialUnresolved',
                        'panel.structural.reasonUserWallNotApplied',
                        'panel.structural.notEvalWallTemperature'):
            assert s.count("'%s'" % anahtar) == 2, (
                f'{anahtar} EN ve TR bloklarının İKİSİNDE olmalı')


# ===========================================================================
# P15B4-04 — arayüz yarısı: motor_type istekte taşınır
# ===========================================================================
class TestP15B404MotorTipiIstekte:
    """ÖLÇÜLDÜ (``a2/once.json``): üç şablonun ihraç gövdesi de
    ``motor_type`` göndermiyordu (0/0/0); sunucu yarısı (D25 ihracat,
    ``normalise_step_motor_type``) tabanda ZATEN duruyordu."""

    # Ad kaleme özgüdür: depo genelinde `ESLEME` başka bir dosyada başka
    # bir anlamla kullanılıyor (tutarlılık kancası ad çakışmasını
    # tutarsızlık sanıyor).
    IHRAC_ESLEMESI = (
        ('solid.html', '_solidDownloadExport', 'solid'),
        ('liquid.html', '_downloadLiquidExport', 'liquid'),
        ('advanced.html', '_downloadExport', 'hybrid'),
    )

    @pytest.mark.parametrize('dosya,fonk,tip', IHRAC_ESLEMESI,
                             ids=[e[0] for e in IHRAC_ESLEMESI])
    def test_ihrac_govdesi_motor_type_gonderiyor(self, dosya, fonk, tip):
        s = govde(TPL / dosya)
        m = re.search(r'async function ' + fonk + r'\([\s\S]{0,1600}', s)
        assert m, f'{dosya}: {fonk} bulunamadı'
        blok = m.group(0)
        assert re.search(r"motor_type:\s*'%s'" % tip, blok), (
            f'{dosya}: ihraç gövdesi motor_type göndermiyor — STEP '
            f"üreticisi 'hybrid' varsayılanına düşer")

    def test_sunucu_yarisi_duruyor(self):
        """ÖNKOŞUL: D25 ihracat onarımı tabanda; kaybolursa haber ver."""
        s = ham(KOK / 'hrma' / 'app.py')
        assert 'normalise_step_motor_type' in s, (
            'sunucu yarısı (D25) kaybolmuş — arayüz alanı tüketilmiyor')

    def test_uc_motor_type_alanini_tuketiyor(self):
        """Alan gerçekten TÜKETİLİYOR mu — normalleştirici + uç bağlantısı.

        NOT: ``/api/export-complete-zip`` geometri kapısını motor tipi
        kapısından ÖNCE koşar (boş ``motor_data`` ->
        ``missing_export_geometry``), o yüzden uçtaki bağlantı kaynak
        düzeyinde, normalleştiricinin hükmü ise doğrudan sınanır.
        """
        from hrma.export.step_export import normalise_step_motor_type
        for tip in ('solid', 'liquid', 'hybrid'):
            deger, hata = normalise_step_motor_type(tip)
            assert not hata, f'{tip} reddedildi: {hata}'
            assert deger, f'{tip} için normalleştirilmiş tip boş'
        _deger, hata = normalise_step_motor_type('banana')
        assert hata, 'tanınmayan motor tipi sessizce kabul ediliyor'

        s = ham(KOK / 'hrma' / 'app.py')
        assert re.search(
            r"normalise_step_motor_type\(\s*\n?\s*\(request\.json or \{\}\)"
            r"\.get\('motor_type'\)", s), (
            'uç istekteki motor_type alanını okumuyor — arayüzün '
            'gönderdiği alan tüketilmiyor')


# ===========================================================================
# OH-B3-03 — defaults_applied ekranda
# ===========================================================================
class TestOHB303DefaultsApplied:
    """ÖLÇÜLDÜ (``a2/once.json``: panel_defaults_applied_okumasi = 0):
    uç listeyi yanıtın üst katında yayımlıyordu, panel adı bir kez bile
    anmıyordu. ``tests/test_wave3_contract.py`` bunu 'structural/ust'
    altında xfail(strict) borç imiyle taşıyordu — im KALDIRILDI."""

    def test_panel_listeyi_okuyor(self):
        s = govde(JS / 'panels' / 'structural_panel.js')
        assert 'data.defaults_applied' in s, (
            'panel `defaults_applied` alanını okumuyor')

    def test_bos_liste_de_soyleniyor(self):
        s = govde(JS / 'panels' / 'structural_panel.js')
        assert 'panel.structural.defaultsAppliedNone' in s, (
            'boş liste sessizce geçiliyor — "hiçbir varsayılan '
            'uygulanmadı" da bir cevaptır')

    def test_uc_alani_hala_yayimliyor(self):
        """Bekçi ucun kanalına bağlı: kanal kapanırsa haber ver."""
        s = ham(KOK / 'hrma' / 'app.py')
        assert "'defaults_applied': defaults_applied," in s

    def test_borc_imi_kaldirildi(self):
        """İm SÖZLÜĞÜNDEN kalkmalı (metin araması değil — aynı blok adı
        ``TERS_MUAFIYET`` içinde de geçiyor)."""
        from tests.test_wave3_contract import TERS_BORCLU_BLOKLAR
        assert 'structural/ust' not in TERS_BORCLU_BLOKLAR, (
            'borç imi hâlâ duruyor — XPASS(strict) süiti kırar')


# ===========================================================================
# OH-B3-02 — sağır blok envanteri (ödenen paylar)
# ===========================================================================
class TestOHB302SagirBloklar:
    """ÖLÇÜLDÜ (``a2/once.json``): on iki sağır bloğun ölçülen payı
    panelde SIFIR kez geçiyordu. Bu aşamada ÖDENEN yedi blok aşağıda;
    üçü (blowdown 6 künye, transient.erosion, transient.flow_separation)
    kardeş dal çakışması yüzünden ENGELLİdir (blowdown_panel.js ve
    transient_panel.js'e hibrit kulvarı dokunuyor)."""

    ODENEN = (
        ('panels/flow_panel.js', 'friction_loss_fraction_basis'),
        ('panels/flow_panel.js', 'friction_loss_fraction_source'),
        ('panels/flow_panel.js', 'friction_loss_fraction_bl_note'),
        ('panels/flow_panel.js', 'friction_comparison_basis'),
        ('panels/flow_panel.js', 'thresholds_Pa'),
        ('panels/flow_panel.js', 'diagnostics'),
        ('panels/correlation_panel.js', 'skipped_summary'),
        ('panels/cooling_panel.js', 'property_table_clamped_stations'),
        ('panels/feed_panel.js', 'confidence'),
        ('panels/feed_panel.js', 'vapor_pressure_source'),
        ('panels/feed_panel.js', 'flow_source'),
        ('thermal_fea_panel.js', 'contour_basis'),
    )

    @pytest.mark.parametrize('rel,alan', ODENEN,
                             ids=[f'{r.split("/")[-1]}:{a}'
                                  for r, a in ODENEN])
    def test_alan_panelde_geciyor(self, rel, alan):
        s = govde(JS / rel)
        assert alan in s, (
            f'{rel}: `{alan}` ekrana inmiyor — sağır blok geri döndü')

    #: Bu aşamada ÖDENEN blok -> alan eşlemesi. Borç imi PARAMETRE olarak
    #: BLOĞA takılır (``_ters_param``), oysa ödenen şey ALANDIR; ikisini
    #: eşitlemek, bloğa sonradan BAŞKA bir alan için im takılmasını da
    #: yasaklar. Ayrım ÖH D27 / fix-26b'de açıldı (aşağıdaki nota bak).
    ODENEN_IM_ALANLARI = {
        'wave4a': {
            'flow/losses': ('friction_loss_fraction_basis',
                            'friction_loss_fraction_source',
                            'friction_loss_fraction_bl_note',
                            'friction_comparison_basis', 'thresholds_Pa',
                            'diagnostics'),
            'correlation': ('skipped_summary',),
        },
        'wave4b': {
            'cooling/summary': ('property_table_clamped_stations',),
            'feed/slosh': ('confidence',),
            'feed/press_reg': ('confidence',),
            'feed/press_bd': ('confidence',),
            'feed/water_hammer': ('vapor_pressure_source', 'flow_source'),
            'thermal_fea/wall_profile': ('contour_basis',),
        },
    }

    def test_borc_imleri_kaldirildi(self):
        """Ödenen ALAN için im geri gelmemeli.

        ÖH D27 / fix-26b — BEKÇİ BLOK DÜZEYİNDEN ALAN DÜZEYİNE ÇEVRİLDİ.
        Eski iddia "şu BLOKLAR ``TERS_BORCLU_BLOKLAR`` sözlüğünde hiç
        geçmesin" diyordu. Bu, OH-B3-02'nin gerçekte ödediğinden fazlasını
        kilitliyordu: ödenen şey bir ALANDIR (``thermal_fea/wall_profile``
        bloğunda ``contour_basis``), oysa im aynı bloğa SONRADAN, BAŞKA
        bir alan için de takılabilir. Nitekim öyle oldu — D26 / app-api a4
        (``e5882484``, P7B3-31) aynı bloğa yeni bir dürüstlük künyesi
        ekledi (``column_basis``, altı çocuk) ve panel onu okumuyor;
        wave4b bunu gerekçeli im + envanterle kaydetti. Eski iddia bu
        yüzden kırmızı verdi, ama gösterdiği şey bir gerileme DEĞİLDİ:
        bekçinin kendisi fazla genişti.

        Yeni iddia daha DAR ama daha KESKİN: bir imin gerekçesi ödenen
        alanın adını taşıyamaz (yani ödeme geri alınamaz) ve ödenen bloğa
        takılan her im hangi aşamadan geldiğini yazmak zorundadır. Ödemenin
        KENDİSİ ayrıca ve doğrudan ``test_alan_panelde_geciyor``da ölçülür:
        alan panel dosyasında hâlâ geçiyor mu?
        """
        from tests.test_wave4a_contract import (
            TERS_BORCLU_BLOKLAR as IM_4A)
        from tests.test_wave4b_contract import (
            TERS_BORCLU_BLOKLAR as IM_4B)
        for etiket, imler in (('wave4a', IM_4A), ('wave4b', IM_4B)):
            for blok, alanlar in self.ODENEN_IM_ALANLARI[etiket].items():
                gerekce = imler.get(blok)
                if gerekce is None:
                    continue
                geri_donen = [a for a in alanlar if a in str(gerekce)]
                assert not geri_donen, (
                    f'{etiket} `{blok}`: OH-B3-02\'de ÖDENEN alan(lar) '
                    f'için borç imi geri geldi: {geri_donen}')
                assert 'D2' in str(gerekce), (
                    f'{etiket} `{blok}`: ödenmiş bir bloğa takılan im '
                    'hangi aşamanın hangi alanını borçlandırdığını '
                    f'yazmıyor: {str(gerekce)[:120]!r}')


# ===========================================================================
# EK BULGU — U.esc kapısı (a1'in 'U is not defined' bulgusuyla aynı sınıf)
# ===========================================================================
class TestUEscKapisi:
    """ÖLÇÜLDÜ (node ile canlı koşum, taban 7751531):
    ``typeof AnalysisDock.ui.esc === 'undefined'`` (ui 37 anahtar taşıyor,
    ``esc`` yok) — oysa ``panels/flow_panel.js`` bu adı YEDİ kez çağırıyor
    ve İKİSİ ``honestyBlock()`` içindedir; o blok ana render yolundan
    KOŞULSUZ çağrılır. Yani ucun ``c_star_source`` alanı dolu geldiği an
    panel ``U.esc is not a function`` ile düşüyordu."""

    def test_guverte_esc_yayimliyor(self):
        s = govde(JS / 'analysis_dock.js')
        assert re.search(r'^\s*esc:\s*escAttr,', s, re.M), (
            'AnalysisDock.ui `esc` yardımcısını yayımlamıyor — '
            'flow_panel.js onu çağırıyor')

    def test_esc_ikinci_bir_kacici_DEGIL(self):
        """Doktrin 4: kaçıcı ikinci kez yazılmaz, mevcut olan yayımlanır."""
        s = govde(JS / 'analysis_dock.js')
        assert s.count('function escAttr(') == 1, (
            'ikinci bir kaçıcı tanımlanmış — tek kaynak bozuldu')

    def test_canli_kosumda_fonksiyon(self):
        """Ürün dosyasını node ile koşup gerçekten var mı diye bakar."""
        betik = r"""
const fs = require('fs');
global.window = { addEventListener(){}, location:{pathname:'/hybrid'} };
global.document = { addEventListener(){}, readyState:'complete',
  getElementById(){return null;}, querySelector(){return null;},
  querySelectorAll(){return [];},
  createElement(){return {style:{}, appendChild(){}, setAttribute(){},
    addEventListener(){}, classList:{add(){}}};},
  body:{appendChild(){}} };
global.navigator = { language: 'en' };
eval(fs.readFileSync(process.argv[2], 'utf8'));
const ui = window.AnalysisDock && window.AnalysisDock.ui;
console.log(JSON.stringify({ esc: typeof (ui && ui.esc) }));
"""
        # Betik STDIN'den gider (argv tavanı: Linux MAX_ARG_STRLEN).
        # Tek tire node'a "betiği stdin'den oku" der ve kalan argümanlar
        # process.argv'de durur — bu yüzden yol argv[2]'dedir (argv[1]
        # tirenin kendisi). Sözleşme: tests/test_node_cagri_sozlesmesi.py
        p = subprocess.run(
            ['node', '-', str(JS / 'analysis_dock.js')], input=betik,
            capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, f'node koşumu düştü: {p.stderr[-400:]}'
        assert json.loads(p.stdout.strip())['esc'] == 'function', (
            'AnalysisDock.ui.esc canlı koşumda fonksiyon DEĞİL')


# ===========================================================================
# EK BULGU — katlı sayacı yorumu kod sanıyordu (OH-D25-22 ile aynı sınıf)
# ===========================================================================
class TestKatliSayaciYorumuSaymaz:
    """ÖLÇÜLDÜ (bu aşamada, panel süiti koşumunda):
    ``tests/test_z5_rozet_dock.py::test_c4_urun_katlilarinin_hepsi_hala_
    varsayilan_kapali`` üründe **13** katlı sayıp kırmızı verdi; ürün 12
    taşıyordu. 13.'sü ``thermal_fea_panel.js``deki P11B3-15 açıklama
    bloğunun içinde geçen ``<details id="fea_t_basis">`` **cümlesiydi**.
    Sebep: sayaç yalnız satır ÖNEKİNE bakıyordu (``^\\s*(//|*|/*|#)``),
    yani ``/* … */`` bloğunun yıldızsız devam satırları KOD sayılıyordu.

    Ölçüt gevşetilmedi (envanter 12'de kaldı); **sayaç daraltıldı**:
    JS kaynaklarında dosyanın KENDİ kaçıcısı (``js_yorumsuz``) kullanılır.
    """

    def test_sayac_js_yorumunu_soker(self):
        s = ham(KOK / 'tests' / 'test_z5_rozet_dock.py')
        assert re.search(r"if yol\.suffix == '\.js':\s*\n\s*ham = js_yorumsuz\(ham\)",
                         s), (
            'katlı sayacı JS yorumlarını sökmüyor — blok yorumu içindeki '
            '<details cümlesi yine katlı sayılır')

    def test_envanter_BUYUTULMEDI(self):
        """Kusur 'envanteri 13 yap' diye kapatılmadı."""
        from tests.test_z5_rozet_dock import URUN_KATLILARI
        assert len(URUN_KATLILARI) == 12, (
            f'URUN_KATLILARI {len(URUN_KATLILARI)} — ölçüt gevşetilmiş '
            'olabilir (sayaç daraltılmalıydı, envanter değil)')

    def test_html_sablonlarda_js_sokucusu_UYGULANMIYOR(self):
        """`href`teki `//` satırın kalanını silip gerçek bir <details'i
        gizleyebilir; şablonlarda satır-öneki sezgisi KALIR."""
        s = ham(KOK / 'tests' / 'test_z5_rozet_dock.py')
        assert "yol.suffix == '.js'" in s, (
            'sökücü dosya türüne bakmadan uygulanıyor — HTML şablonlarında '
            'gerçek katlı gizlenebilir')


# ===========================================================================
# P11B3-15 — mesh yakınsaması rozet katında
# ===========================================================================
def _render_badges_govdesi(s):
    """``thermal_fea_panel.js`` renderBadges işlevinin TAMAMI (re.Match)."""
    return re.search(r'function renderBadges\([\s\S]*?\n    \}\n', s)


class TestP11B315MeshYakinsamasi:
    """ÖLÇÜLDÜ (``a2/once.json``): mesh politikası beyanı YALNIZ katlanmış
    ``<details id="fea_t_basis">`` künye bloğundaydı
    (mesh_politikasi_rozette = 0), rozet şeridinde ise YEŞİL
    "TIME STEP CONVERGED" duruyordu. Çözücü bunu zaten beyan ediyordu:
    "termal yolda MESH yakınsaması otomatik DENETLENMEZ"."""

    def test_mesh_rozeti_rozet_seridinde(self):
        s = govde(JS / 'thermal_fea_panel.js')
        assert 'feaT.badgeMeshNotConverged' in s, (
            'mesh yakınsaması rozeti yok — beyan hâlâ katlı künyede')
        # Rozet, zaman adımı rozetiyle AYNI fonksiyonda basılmalı
        # T-ÇAPA-C2 (27 Eki): sabit 4000 karakterlik pencere yerine işlevin
        # TAMAMI (4 boşluk girintili kapanışa kadar). V301/L-KABUK ve
        # N-girdi-2 rozet katını uzattı; mesh rozeti (``spatialBadge`` ya da
        # bildirilen dal) ve sahiplik rozeti pencere dışına kaydı — ikisi de
        # hâlâ renderBadges içinde basılıyor.
        m = _render_badges_govdesi(s)
        assert m and 'feaT.badgeMeshNotConverged' in m.group(0), (
            'mesh rozeti renderBadges dışında — aynı katta değil')

    def test_zaman_adimi_rozeti_kapsamini_soyluyor(self):
        s = govde(JS / 'thermal_fea_panel.js')
        assert 'TIME STEP CONVERGED (time axis only)' in s, (
            'zaman adımı rozeti hâlâ çıplak "yakınsadı" gibi okunuyor')

    def test_beyan_yoksa_hukum_uydurulmaz(self):
        s = govde(JS / 'thermal_fea_panel.js')
        assert 'mesh_declared' in s and 'feaT.badgeMeshNotDeclared' in s, (
            'çözücü mesh politikası yayımlamazsa panel ne diyeceğini '
            'bilmiyor — fail-closed değil')

    def test_cozucu_beyani_hala_yayimliyor(self):
        s = ham(KOK / 'hrma' / 'fea' / 'bridge.py')
        assert '"mesh_politikasi"' in s
        assert 'MESH yakınsaması otomatik DENETLENMEZ' in s

    def test_i18n_EN_ve_TR(self):
        s = ham(JS / 'i18n_common.js')
        for k in ('feaT.badgeMeshNotConverged', 'feaT.badgeMeshNotDeclared'):
            assert s.count("'%s'" % k) == 2, f'{k} EN+TR olmalı'


# ===========================================================================
# P11B3-16 — ortam sıcaklığı: tek kaynak + sahiplik ilanı
# ===========================================================================
class TestP11B316OrtamSicakligi:
    """ÖLÇÜLDÜ (``a2/once.json``): ``#fea_t_ambient`` ``value="293.15"``
    ile önceden doluydu (alan_onceden_dolu = 1), panel bu sonlu
    varsayılanı hiçbir yerde ilan etmiyordu (varsayilan_ilani = 0) ve
    sayı tek kaynakta değildi. Kardeş CFD paneli TERS politika uygular:
    ``P_ambient_Pa`` onun REQUIRED_FIELDS listesindedir."""

    def test_sayi_tek_kaynakta(self):
        s = govde(JS / 'thermal_fea_panel.js')
        assert 'AMBIENT_PANEL_DEFAULT_K = 293.15' in s, (
            'panel varsayılanı adlandırılmış sabitte değil')
        # HTML'de sayı İKİNCİ kez YAZILMAZ (sabitten kurulur)
        assert 'value="293.15"' not in s, (
            'sayı hâlâ HTML dizesine gömülü — iki sahipli')
        assert '${AMBIENT_PANEL_DEFAULT_K}' in s

    def test_gonderilen_sayinin_sahibi_kaydediliyor(self):
        s = govde(JS / 'thermal_fea_panel.js')
        assert 'ambientSource' in s
        assert "ambientIsUserSupplied() ? 'user' : 'panel_default'" in s, (
            'panel gönderdiği sayının kimin olduğunu kaydetmiyor')

    def test_sahiplik_ROZET_katinda_ilan_ediliyor(self):
        """P11B3-15'in dersi: beyan katlı künyede kalırsa görünmez."""
        s = govde(JS / 'thermal_fea_panel.js')
        m = _render_badges_govdesi(s)
        assert m and 'feaT.badgeAmbientDefault' in m.group(0), (
            'sahiplik ilanı rozet katında değil')

    def test_kullanici_dokununca_im_dusuyor(self):
        s = govde(JS / 'thermal_fea_panel.js')
        assert 'function markAmbientDirty' in s
        assert "addEventListener('input', markAmbientDirty)" in s, (
            'kullanıcı yazınca alan onun olmuyor')

    def test_ok21_form_degeri_SOKULMEDI(self):
        """ÖK-21 bu dalgada value/|| sökümünü yasaklar."""
        s = govde(JS / 'thermal_fea_panel.js')
        assert re.search(r'id="fea_t_ambient"[\s\S]{0,120}?value=', s), (
            'form değeri sökülmüş — ÖK-21 ihlali')

    def test_kardes_cfd_politikasi_hala_ters(self):
        s = govde(JS / 'panels' / 'cfd_panel.js')
        assert re.search(r"REQUIRED_FIELDS[\s\S]{0,200}?P_ambient_Pa", s), (
            'kıyas çapası bayat: CFD paneli artık ambient\'i zorunlu '
            'saymıyor')


# ===========================================================================
# P11B3-18 — CFD yankı tablosu SÜZMEZ
# ===========================================================================
class TestP11B318YankiTablosu:
    """ÖLÇÜLDÜ (``a2/once.json``): "INPUTS ECHOED BY THE ENDPOINT"
    tablosu SABİT 16 anahtarla kuruluyordu (sabit_liste_uzunlugu = 16);
    ucun yankıladığı girdi sayısı 30. ``wall_bc``, ``time_integrator``,
    ``initial_state`` gibi şema seçimleri sessizce düşüyordu."""

    def test_tablo_tum_yankiyi_basiyor(self):
        s = govde(JS / 'panels' / 'cfd_panel.js')
        assert 'Object.keys(inp)' in s, (
            'tablo hâlâ sabit listeyle SÜZÜYOR')
        assert 'EKO_SIRASI' in s, 'sıralama listesi adlandırılmamış'

    def test_sabit_liste_SUZGEC_degil_SIRALAMA(self):
        s = govde(JS / 'panels' / 'cfd_panel.js')
        m = re.search(r'const kalan = Object\.keys\(inp\)\.filter'
                      r'\([\s\S]{0,220}?\}\)\.sort\(\);', s)
        assert m, 'bilinmeyen anahtarlar toplanmıyor'
        assert 'EKO_SIRASI.concat(kalan).forEach' in s, (
            'bilinen + kalan birleşimi basılmıyor — alan yine düşer')

    def test_yeni_alan_kendiliginden_giriyor(self):
        """Sentetik yankı: listede OLMAYAN bir alan tabloya girmeli."""
        s = govde(JS / 'panels' / 'cfd_panel.js')
        m = re.search(r"const EKO_SIRASI = \[([\s\S]{0,400}?)\];", s)
        assert m, 'EKO_SIRASI bulunamadı'
        bilinen = set(re.findall(r"'([A-Za-z_]\w*)'", m.group(1)))
        for yeni in ('wall_bc', 'time_integrator', 'initial_state'):
            assert yeni not in bilinen, (
                f'{yeni} listeye eklenerek "çözülmüş" — süzgeç sorunu '
                'liste büyüterek kapatılamaz')
