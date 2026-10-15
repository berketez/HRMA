# -*- coding: utf-8 -*-
"""ÖH Dalga-17 / kulvar `electron` / aşama a1 — bekçiler.

Onarılan kalemler (parti P12a, bulucu 3/4/5):

  P12aB4-01  STEP içe aktarma katı sayfasında ODA boyunu TANE boyu alanına
             yazıyordu (toplam impuls +%11,1 kayması).
  P12aB4-02  Proje yüklemede sunucunun ürettiği uyarılar yalnız console.warn'a
             gidiyordu; ekranda yalnız yeşil "yüklendi" görünüyordu.
  P12aB4-03  GIBS karo kabuğu tabandan 2.548,4 m yukarıdaydı; yüzeye çapalı
             işaretçiler kabuğun altında kalıyordu.
  P12aB4-04  Karo yüklemesi başarısız olunca anahtar siliniyor, 250 ms sonra
             aynı 25 karo yeniden isteniyordu (100 istek/sn, ~360.000/saat).
  P12aB4-05  Türkçe sözlük uçuş İRTİFASI ile saha RAKIMI için aynı kelimeyi
             ("Rakım") kullanıyordu.
  P12aB4-06  Saha seçim ışını TABAN küreye çarpıyordu; kullanıcının gördüğü
             karo yüzeyiyle arasında 2.637 m sabit kayma vardı.
  P12aB5-01  "Hata bildir" bölümünün 47 `shell.bug.*` anahtarı (+3 uyarı kodu)
             hiçbir sözlükte tanımlı değildi — gizlilik/rıza beyanı dâhil.
  P12aB5-02  İndirme durumu okunamayınca yoklama sonsuza dek sessiz sürüyordu.
  P12aB3-02  Enjektör altyazısı delik YERLEŞİMİNİN basınç düşümünü
             belirlediğini söylüyordu; ölçüm 26 alanın 0'ının değiştiğini
             gösteriyor.
  P12aB3-08  "Balistik uçuş (yörünge değil)" beyanı hiç basılmıyordu (anahtar
             sözlükte tanımlı bile değildi).
  P12aB3-09  Sabit id ile çizilen 7 grafik açıklamasız kalıyordu.

Bekçiler ürün dosyalarının SEMANTİĞİNİ ölçer (metin biçimini değil): her
iddia, onarımın geri alınmasıyla kırmızıya döner (bkz.
docs/scofield/raw/OH/D17/electron/a1/mutasyon.json).
"""
import json
import os
import re

import pytest
from tests.support.kanit import kanit_gerekli

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS = os.path.join(KOK, 'hrma', 'static', 'js')


def oku(rel):
    with open(os.path.join(KOK, rel), encoding='utf-8') as f:
        return f.read()


def maske_yorum(metin):
    """JS yorumlarını boşluğa çevirir (satır numaraları korunur).

    ÖH D29 / OH-D19-26 (f) — YORUM KAÇAĞI ONARIMI. ``sozlukler()`` ham
    metinde ``'anahtar': '`` deseni arıyordu; sözlük dosyalarındaki
    AÇIKLAMA satırları da bu deseni taşıyor. ÖLÇÜLDÜ (raw/OH/D29/
    arayuz-i18n/a1/{once,sonra}_kalan.json, K2): yalnız YORUMDA geçen üç
    hayalet anahtar "tanımlı" sayılıyordu (i18n.js: ``panel.pc``,
    ``panel.thrust``; i18n_pages.js: ``app.rep.webThickness``). Bu, ölü
    anahtar bekçisinin tersi bir boşluktur: üründe çağrılan bir anahtar
    sözlükte OLMASA bile, adı bir yorumda geçiyorsa bekçi yeşil kalır.
    """
    o = list(metin)
    for desen in (r'/\*[\s\S]*?\*/', r'(?m)^[ \t]*//[^\n]*$'):
        for m in re.finditer(desen, metin):
            for i in range(m.start(), m.end()):
                if o[i] != '\n':
                    o[i] = ' '
    return ''.join(o)


def sozlukler():
    """Tüm i18n_*.js parçalarında tanımlı anahtarlar (dil ayrımı yapmadan).

    Yalnız GERÇEK tanımlar sayılır: yorum blokları maskelenir.
    """
    tanimli = set()
    for f in sorted(os.listdir(JS)):
        if f.startswith('i18n') and f.endswith('.js'):
            metin = maske_yorum(oku('hrma/static/js/' + f))
            tanimli |= set(re.findall(r"'([A-Za-z0-9_.]+)':\s*'", metin))
    return tanimli


def dil_bloklari(rel):
    """i18n parçasının en/tr bloklarını ayrı ayrı döndürür."""
    metin = oku(rel)
    i, j = metin.index('        en: {'), metin.index('        tr: {')
    return metin[i:j], metin[j:]


def deger(blok, anahtar):
    m = re.search(r"'" + re.escape(anahtar) + r"':\s*'((?:[^'\\]|\\.)*)'", blok)
    return m.group(1) if m else None


# ==========================================================================
# P12aB4-01 — STEP oda boyu → tane boyu
# ==========================================================================
class TestP12aB401StepOdaBoyu:
    """CAD'den okunan oda boyu, katı sayfasında TANE boyu alanına yazılamaz."""

    def _solid_blok(self):
        s = oku('hrma/static/js/step_import_ui.js')
        m = re.search(r'solid:\s*\{([\s\S]*?)\n        \},', s)
        assert m, 'PAGE_MAPS.solid bloğu bulunamadı'
        return m.group(1)

    def test_oda_boyu_tane_boyu_alanina_yazilmaz(self):
        blok = self._solid_blok()
        alanlar = re.search(r'fields:\s*\{([\s\S]*?)\},', blok).group(1)
        assert 'chamber_length_mm' not in alanlar, (
            'Katı sayfasında oda boyu bir forma yazılıyor. `#grain_length` TEK '
            'propelan tanesinin boyudur, oda boyu değildir; sayfanın kendi '
            'çözümü oda boyunu `grain_length / 0.9` ile türetir. Ölçülen ürün '
            'etkisi: grain_length 500 -> 560 mm toplam impulsü +%11,1 kaydırır.')

    def test_reddin_gerekcesi_adiyla_basiliyor(self):
        """Fail-closed yetmez: kullanıcı NEDEN uygulanmadığını okumalı."""
        blok = self._solid_blok()
        m = re.search(r"refusals:\s*\{([\s\S]*?)\},\n", blok)
        assert m, 'katı haritasında adlı ret (refusals) tablosu yok'
        assert 'chamber_length_mm' in m.group(1), (
            'oda boyu için adlı ret gerekçesi tanımlı değil')
        anahtar = re.search(r"\['([A-Za-z0-9_.]+)'", m.group(1)).group(1)
        assert anahtar in sozlukler(), (
            'ret gerekçesi anahtarı (%s) hiçbir sözlükte tanımlı değil, '
            'yani Türkçe arayüzde İngilizce kalır' % anahtar)

    def test_render_reddi_ekrana_basiyor(self):
        s = oku('hrma/static/js/step_import_ui.js')
        assert re.search(r'var refusal = \(pageMap\.refusals', s), (
            'öneri kartı ret tablosunu okumuyor')
        assert re.search(r'refusal\s*\n?\s*\?\s*T\(refusal\[0\], refusal\[1\]\)', s), (
            'ret gerekçesi kartta basılmıyor — genel "no form field" metni '
            'kalıyor, kullanıcı yakın görünen alanın BAŞKA büyüklük olduğunu '
            'öğrenemiyor')

    def test_hibrit_esleme_bozulmadi(self):
        """Hibritte oda boyu alanı GERÇEKTEN oda boyudur; kaldırılmamalı."""
        s = oku('hrma/static/js/step_import_ui.js')
        h = re.search(r'hybrid:\s*\{([\s\S]*?)\n        \},', s).group(1)
        assert "chamber_length_mm: 'chamber_length_override'" in h


# ==========================================================================
# P12aB4-02 — proje yükleme uyarıları
# ==========================================================================
class TestP12aB402ProjeUyarilari:
    def _foreach_govdesi(self):
        s = oku('hrma/static/js/project_bar.js')
        lb = re.search(r'async function loadIntoPage\(name\)([\s\S]*?)\n    \}', s)
        assert lb, 'loadIntoPage gövdesi bulunamadı'
        return lb.group(1)

    def test_uyarilar_ekrana_basiliyor(self):
        lb = self._foreach_govdesi()
        assert 'data.warnings' in lb, 'sunucu uyarıları hiç okunmuyor'
        gövde = re.search(
            r'\.warnings[\s\S]{0,400}?forEach\(function \(w\) \{([\s\S]*?)\n            \}\);',
            lb)
        assert gövde, 'uyarı başına çalışan gövde bulunamadı'
        assert 'toast(' in gövde.group(1), (
            'sunucunun ürettiği yükleme uyarısı yalnız console.warn\'a gidiyor; '
            'kullanıcı farklı sürümde kaydedilmiş bir projeyi açtığını ekrandan '
            'öğrenemiyor')

    def test_uyari_varken_basari_bildirimi_yesil_degil(self):
        lb = self._foreach_govdesi()
        assert 'proj.loadedWithWarnings' in lb, (
            'uyarı varken de düz yeşil "yüklendi" bildirimi basılıyor')
        assert re.search(r"uyarilar\.length \? 'warn' : 'ok'", lb), (
            'bildirim türü uyarı sayısına bağlanmamış')

    def test_bildirim_anahtari_sozlukte_tanimli(self):
        assert 'proj.loadedWithWarnings' in sozlukler()


# ==========================================================================
# P12aB4-03 + P12aB4-06 — karo kabuğu / ışın yüzeyi (tek kök)
# ==========================================================================
GLOBE_R = 100.0
R_EARTH_M = 6371000.0
M_PER_UNIT = R_EARTH_M / GLOBE_R


class TestP12aB403ve06KaroKabugu:
    def _globe(self):
        return oku('hrma/static/js/launch_site_globe.js')

    def _tile_carpani(self):
        g = self._globe()
        m = re.search(r'var TILE_RADIUS\s*=\s*GLOBE_R\s*\*\s*([0-9.]+)\s*;', g)
        if m:
            return float(m.group(1))
        assert re.search(r'var TILE_RADIUS\s*=\s*GLOBE_R\s*;', g), (
            'TILE_RADIUS tanımı tanınmadı')
        return 1.0

    def test_karo_kabugu_sahte_irtifa_uretmiyor(self):
        """Kabuk taban küreyle aynı yarıçapta olmalı: sahne birimi = fizik."""
        yukseklik_m = (self._tile_carpani() - 1.0) * GLOBE_R * M_PER_UNIT
        assert yukseklik_m < 1.0, (
            'karo kabuğu tabandan %.1f m yukarıda; bu geometrik kaydırma '
            'fiziksel değil salt çizim hilesidir ve yüzeye çapalı '
            'işaretçileri altında bırakır' % yukseklik_m)

    def test_isaretciler_kabugun_ustunde(self):
        """viewSite (uçuş varken d = 0,03·R) çerçevesinde üçü de görünür."""
        kabuk_m = (self._tile_carpani() - 1.0) * GLOBE_R * M_PER_UNIT
        d = 0.03 * GLOBE_R
        gomulen = []
        for ad, k in (('saha iğnesi', 0.013), ('olay noktası', 0.0075),
                      ('roket sembolü', 0.020)):
            if k * d * M_PER_UNIT < kabuk_m:
                gomulen.append(ad)
        assert not gomulen, (
            'karolar açıkken şu işaretçiler kabuğun altında kalıyor: %s'
            % ', '.join(gomulen))

    def test_z_fighting_derinlik_yanliligiyla_cozuluyor(self):
        """Yarıçap kaydırması kaldırıldıysa yerine bir çözüm konmuş olmalı."""
        g = self._globe()
        mat = re.search(r'_makeTileMesh = function([\s\S]*?)\n    \};', g).group(1)
        assert 'polygonOffset' in mat, (
            'karo yaması taban küreyle çakışık ama derinlik yanlılığı yok — '
            'z-fighting doğar')
        assert 'renderOrder' in mat

    def test_saha_isini_gorulen_yuzeye_carpiyor(self):
        """Işın taban küreye çarpar; taban ile karo yüzeyi AYNI olmalı."""
        g = self._globe()
        hit = re.search(r'_hitLatLon = function([\s\S]*?)\n    \};', g).group(1)
        assert 'intersectObject(this.globe' in hit
        kayma_m = ((self._tile_carpani() - 1.0) * GLOBE_R * M_PER_UNIT
                   * 1.0355)          # tan(46°) — raporun eğik bakış açısı
        assert kayma_m < 1.0, (
            'tıklanan yer ile seçilen enlem/boylam arasında %.1f m kayma var: '
            'kullanıcı KARO yüzeyini görüyor, ışın TABAN küreye çarpıyor'
            % kayma_m)

    def test_saha_halkasi_karo_yamasinin_onunde(self):
        """Çakışık yüzeyde taban halkası karonun altında kaybolmamalı."""
        g = self._globe()
        m = re.search(r'_buildMarker = function([\s\S]*?)\n    \};', g).group(1)
        assert 'polygonOffset' in m and 'renderOrder' in m


# ==========================================================================
# P12aB4-04 — karo yeniden deneme fırtınası
# ==========================================================================
class TestP12aB404KaroFirtinasi:
    def _globe(self):
        return oku('hrma/static/js/launch_site_globe.js')

    def test_basarisiz_karo_negatif_onbellege_yaziliyor(self):
        g = self._globe()
        hata = re.search(
            r'_buildTilePatch = function[\s\S]*?undefined, function \(\) \{([\s\S]*?)\}\);',
            g).group(1)
        assert 'failed: true' in hata and 'retryAt' in hata, (
            'başarısız karo Map\'ten siliniyor; 250 ms sonraki tarama onu '
            '"hiç denenmemiş" sanıp yeniden istiyor — çevrimdışı ölçümde '
            '100 istek/sn (~360.000/saat), sunucuda her istek 8 sn\'lik bir '
            'dış GIBS denemesi açıyor')

    def test_tarama_dongusu_geri_cekilmeye_uyuyor(self):
        g = self._globe()
        tarama = re.search(r'for \(var dy = -R[\s\S]*?\n        \}\n', g).group(0)
        assert 'entry.failed' in tarama and 'retryAt' in tarama, (
            'tarama döngüsü negatif önbelleği tanımıyor')

    def test_deneme_sayisi_ustten_sinirli(self):
        g = self._globe()
        m = re.search(r'TILE_FAIL_MAX\s*=\s*(\d+)', g)
        assert m, 'deneme üst sınırı yok — geri çekilme sonsuza dek sürer'
        assert 1 <= int(m.group(1)) <= 10
        assert re.search(r'TILE_FAIL_BACKOFF_MS\s*=\s*(\d+)', g)

    def test_karo_sayaci_cizilmeyeni_saymiyor(self):
        """getTileInfo negatif önbellek girdilerini "yüklü karo" saymamalı."""
        g = self._globe()
        info = re.search(r'getTileInfo = function([\s\S]*?)\n    \};', g).group(1)
        assert 'this._tiles.size' not in info, (
            'karo sayısı Map boyutundan okunuyor; başarısızlar da Map\'te '
            'durduğu için ekrana çizilmemiş karolar "yüklü" sayılır')
        assert 'e.mesh' in info


# ==========================================================================
# P12aB4-05 — irtifa / rakım ayrımı
# ==========================================================================
class TestP12aB405IrtifaRakim:
    def test_ucus_irtifasi_ile_saha_rakimi_ayri_kelime(self):
        _en, tr = dil_bloklari('hrma/static/js/i18n_launch_site.js')
        alt, elev = deger(tr, 'site.alt'), deger(tr, 'site.elevation')
        assert alt and elev
        assert alt != elev, (
            '"%s" hem roketin anlık uçuş irtifası (#ls-alt) hem sahanın arazi '
            'rakımı (#ls-r-elev) için kullanılıyor; ikisi aynı ekranda yan yana '
            'duruyor' % alt)

    def test_terimler_tdk_havacilik_kullanimina_uyuyor(self):
        _en, tr = dil_bloklari('hrma/static/js/i18n_launch_site.js')
        assert deger(tr, 'site.alt') == 'İrtifa'
        assert deger(tr, 'site.elevation') == 'Rakım'
        assert 'İrtifa' in (deger(tr, 'site.exaggerate') or ''), (
            'site.exaggerate uçuş irtifası abartmasıdır, saha rakımı değil')

    def test_ingilizce_ayrim_bozulmadi(self):
        en, _tr = dil_bloklari('hrma/static/js/i18n_launch_site.js')
        assert deger(en, 'site.alt') == 'Altitude'
        assert deger(en, 'site.elevation') == 'Elevation'


# ==========================================================================
# P12aB5-01 — "Hata bildir" bölümünün sözlüğü
# ==========================================================================
class TestP12aB501HataBildirSozlugu:
    def _kullanilan(self):
        anahtarlar = set()
        for f in ('settings_panel.js', 'bug_report.js'):
            metin = oku('hrma/static/js/' + f)
            anahtarlar |= set(re.findall(
                r"'(shell\.bug\.[A-Za-z0-9_.]+)'", metin))
            anahtarlar |= set(re.findall(
                r"'(warn\.bugreport\.[A-Za-z0-9_.]+)'", metin))
        return anahtarlar

    def test_tum_anahtarlar_sozlukte_tanimli(self):
        eksik = sorted(self._kullanilan() - sozlukler())
        assert not eksik, (
            '%d anahtar hiçbir sözlükte tanımlı değil; Türkçe arayüzde bölüm '
            'İngilizce kalır: %s' % (len(eksik), eksik[:8]))

    def test_anahtarlar_iki_dilde_de_var(self):
        en, tr = dil_bloklari('hrma/static/js/i18n_shell.js')
        eksik = [k for k in sorted(self._kullanilan())
                 if deger(en, k) is None or deger(tr, k) is None]
        assert not eksik, 'tek dilde kalan anahtarlar: %s' % eksik[:8]

    def test_gizlilik_beyani_turkce(self):
        """Rızanın dayandığı cümle kullanıcının dilinde okunabilmeli."""
        _en, tr = dil_bloklari('hrma/static/js/i18n_shell.js')
        metin = deger(tr, 'shell.bug.diagnosticsDesc')
        assert metin, 'tanılama onay kutusunun gizlilik beyanı Türkçe yok'
        for parca in ('sayısal girdi', 'konsol hata', 'e-posta'):
            assert parca in metin, (
                'gizlilik beyanı hangi verinin herkese açık GitHub kaydına '
                'gideceğini saymıyor (eksik: %s)' % parca)

    def test_govde_basliklari_da_cevrilmis(self):
        """Kullanıcı önizlemede GÖNDERECEĞİ metni kendi dilinde okur."""
        _en, tr = dil_bloklari('hrma/static/js/i18n_shell.js')
        for k in ('shell.bug.body.what', 'shell.bug.body.env',
                  'shell.bug.body.inputs', 'shell.bug.body.console',
                  'shell.bug.body.redactNote'):
            assert deger(tr, k), '%s Türkçe karşılığı yok' % k


# ==========================================================================
# P12aB5-02 — sonsuz sessiz güncelleme yoklaması
# ==========================================================================
class TestP12aB502GuncellemeYoklamasi:
    def _catch(self):
        uc = oku('hrma/static/js/update_check.js')
        poll = re.search(r'function pollStatus\(\)[\s\S]*?\n        \}\n    \}', uc)
        assert poll, 'pollStatus gövdesi bulunamadı'
        m = re.search(r'\.catch\(function \(\) \{([\s\S]*?)\n                \}\);',
                      poll.group(0))
        if not m:
            m = re.search(r'\.catch\(function \(\) \{([\s\S]{0,200}?)\}\);',
                          poll.group(0))
        return uc, m.group(1)

    def test_hata_kolunda_deneme_sayaci_var(self):
        _uc, ct = self._catch()
        assert re.search(r'errorStrikes|attempt|retries', ct), (
            '/api/update/status ulaşılamadığında yoklama sonsuza dek sürüyor; '
            'ölçümde 200 çağrıda durmadı ve ekranda "Downloading…" donuk kaldı')

    def test_hata_kolu_kullaniciyi_bilgilendiriyor(self):
        _uc, ct = self._catch()
        assert 'progressText' in ct and 'highlightManual' in ct, (
            'kullanıcı hatayı ve elle indirebileceğini hiç öğrenmiyor')
        assert 'updateBtn.disabled = false' in ct, 'düğme kilitli kalıyor'

    def test_esik_idle_koluyla_ayni(self):
        uc, _ct = self._catch()
        idle = int(re.search(r'idleStrikes > (\d+)', uc).group(1))
        hata = int(re.search(r'ERROR_LIMIT = (\d+)', uc).group(1))
        assert idle == hata, (
            'aynı fonksiyonun iki durma kolu farklı eşik kullanıyor')

    def test_bildirim_anahtari_iki_dilde_tanimli(self):
        en, tr = dil_bloklari('hrma/static/js/i18n_shell.js')
        assert deger(en, 'update.statusUnreachable')
        assert deger(tr, 'update.statusUnreachable')


# ==========================================================================
# P12aB3-02 — enjektör altyazısının yanlış nedenselliği
# ==========================================================================
class TestP12aB302EnjektorAltyazisi:
    YANLIS_EN = 'orifice layout and the key dimensions that set'
    YANLIS_TR = 'belirleyen delik yerleşimi'

    def _etkin_anahtar(self):
        cc = oku('hrma/static/js/chart_captions.js')
        km = re.search(r'CAPTION_KEYS = \{([\s\S]*?)\};', cc)
        ezme = dict(re.findall(r"(\w+):\s*'([^']+)'", km.group(1))) if km else {}
        return cc, ezme.get('injector_plot', 'chartCap.injector_plot')

    def test_ekrana_cikan_metin_yerlesimi_neden_saymiyor(self):
        """hole_pattern 26 sayısal alanın 0'ını değiştiriyor (B3-repro-13)."""
        cc, anahtar = self._etkin_anahtar()
        yedek = deger(cc, anahtar) or ''
        assert self.YANLIS_EN not in yedek, (
            'altyazı delik yerleşiminin basınç düşümünü "belirlediğini" '
            'söylüyor; ölçümde yerleşim hiçbir sayıyı değiştirmiyor')
        for f in sorted(os.listdir(JS)):
            if not (f.startswith('i18n') and f.endswith('.js')):
                continue
            metin = oku('hrma/static/js/' + f)
            for m in re.finditer(
                    r"'" + re.escape(anahtar) + r"':\s*'((?:[^'\\]|\\.)*)'", metin):
                assert self.YANLIS_EN not in m.group(1)
                assert self.YANLIS_TR not in m.group(1)

    def test_yerlesimin_cizim_oldugu_iki_dilde_de_yaziyor(self):
        cc, anahtar = self._etkin_anahtar()
        en, tr = dil_bloklari('hrma/static/js/i18n_shell.js')
        assert 'drawing only' in (deger(en, anahtar) or '')
        assert 'yalnızca çizimdir' in (deger(tr, anahtar) or '')
        assert 'drawing only' in (deger(cc, anahtar) or ''), (
            'sözlük yüklenemezse görünen EN yedek metin düzeltilmemiş')

    def test_anahtar_ezme_haritasi_kullaniliyor(self):
        cc, _a = self._etkin_anahtar()
        assert re.search(r'CAPTION_KEYS\[el\.id\] \|\| \(\'chartCap\.\' \+ el\.id\)', cc)


# ==========================================================================
# P12aB3-08 — "balistik uçuş, yörünge değil" beyanı
# ==========================================================================
class TestP12aB308BalistikBeyani:
    def test_anahtar_iki_dilde_tanimli(self):
        en, tr = dil_bloklari('hrma/static/js/i18n_launch_site.js')
        assert deger(en, 'site.ballistic') and deger(tr, 'site.ballistic')
        assert deger(en, 'site.ballisticHint') and deger(tr, 'site.ballisticHint')

    def test_sayfada_gercekten_basiliyor(self):
        html = oku('hrma/templates/launch_site.html')
        assert 'data-i18n="site.ballistic"' in html, (
            '3B Dünya üzerinde uçuş yolu izleyen kullanıcı yörüngeye '
            'girmediğini hiçbir yerden okumuyor')
        assert 'data-i18n="site.ballisticHint"' in html

    def test_beyan_yorunge_olmadigini_soyluyor(self):
        en, tr = dil_bloklari('hrma/static/js/i18n_launch_site.js')
        assert 'not an orbit' in deger(en, 'site.ballistic')
        assert 'yörünge değil' in deger(tr, 'site.ballistic')


# ==========================================================================
# P12aB3-09 — açıklamasız grafikler
# ==========================================================================
class TestP12aB309AciklamasizGrafikler:
    EKSIKLER = ['mc_hist_thrust', 'mc_hist_isp', 'solid_motor_kesit',
                'altitude_plot', 'cad_visualization', 'cad_3d_view',
                'altitude_preview']

    @staticmethod
    def captions_govdesi():
        """chart_captions.js'teki CAPTIONS sözlüğünün YORUMSUZ gövdesi.

        ÖH D19 / Fable-D17 ŞART-3: eski ölçüt dosyanın TAMAMINI
        tarıyordu, bu yüzden yoruma alınmış (ürün için ölü) bir anahtar da
        'açıklanmış' sayılıyordu — kendi probumla ölçüldü: girdiyi yoruma
        alınca bekçi yeşil kalıyordu. Ölçüt artık yalnız gerçekten
        yüklenen sözlük gövdesine bakar.
        """
        cc = oku('hrma/static/js/chart_captions.js')
        bas = cc.index('var CAPTIONS = {')
        i = cc.index('{', bas)
        derinlik = 0
        son = None
        for j in range(i, len(cc)):
            if cc[j] == '{':
                derinlik += 1
            elif cc[j] == '}':
                derinlik -= 1
                if derinlik == 0:
                    son = j
                    break
        assert son is not None, 'CAPTIONS gövdesi kapanmıyor'
        govde = cc[i + 1:son]
        return '\n'.join(satir for satir in govde.split('\n')
                         if not satir.lstrip().startswith('//'))

    def test_yedi_grafik_de_aciklanmis(self):
        govde = self.captions_govdesi()
        kapsanan = set(re.findall(r"'chartCap\.([A-Za-z0-9_]+)'", govde))
        eksik = [k for k in self.EKSIKLER if k not in kapsanan]
        assert not eksik, (
            'sabit id ile çizilip açıklamasız kalan grafikler: %s' % eksik)

    def test_olcut_yorum_satirlarini_saymaz(self):
        """ŞART-3'ün kendi bekçisi: ölçüt yorum satırından beslenmemeli."""
        cc = oku('hrma/static/js/chart_captions.js')
        tum_dosya = set(re.findall(r"'chartCap\.([A-Za-z0-9_]+)'", cc))
        govde = set(re.findall(r"'chartCap\.([A-Za-z0-9_]+)'",
                               self.captions_govdesi()))
        yalniz_yorumda = tum_dosya - govde
        assert 'injector_plot' in yalniz_yorumda, (
            'chartCap.injector_plot P12aB3-02 ile ezildi ve yalnız yorumda '
            'geçiyor; gövde ölçütünde de görünüyorsa ölçüt yorum sayıyor')
        assert 'injector_plot' not in govde

    def test_aciklamalar_iki_dilde_tanimli(self):
        en, tr = dil_bloklari('hrma/static/js/i18n_shell.js')
        for k in self.EKSIKLER:
            assert deger(en, 'chartCap.' + k), 'chartCap.%s EN yok' % k
            assert deger(tr, 'chartCap.' + k), 'chartCap.%s TR yok' % k

    @pytest.mark.parametrize('kimlik,parca', [
        ('mc_hist_thrust', 'not a manufacturing guarantee'),
        ('mc_hist_isp', 'not as a measured scatter'),
        ('cad_visualization', 'not a manufacturing drawing'),
        ('cad_3d_view', 'not a manufacturing drawing'),
    ])
    def test_dagilim_ve_cad_aciklamalari_cekince_tasiyor(self, kimlik, parca):
        """En çok açıklama isteyenler kendi sınırlarını da söylemeli."""
        en, _tr = dil_bloklari('hrma/static/js/i18n_shell.js')
        assert parca in deger(en, 'chartCap.' + kimlik)


# ==========================================================================
# Sözlük bütünlüğü — yeni anahtarlar hiçbir parçayla çakışmamalı
# ==========================================================================
def test_i18n_parcalari_arasinda_anahtar_cakismasi_yok():
    """i18n.register 'ilk kazanır' der; çakışma sessizce yok sayılan tanım
    demektir. Bu dalgada eklenen anahtarlar i18n_common.js'teki aileleri
    (chartCap.*, update.*, stepimp.*, proj.*) genişletiyor — çakışmadıkları
    burada kilitlenir."""
    sahip = {}
    cakisan = []
    for f in sorted(os.listdir(JS)):
        if not (f.startswith('i18n') and f.endswith('.js')):
            continue
        metin = oku('hrma/static/js/' + f)
        for k in set(re.findall(r"^\s+'([A-Za-z0-9_.]+)':\s*'", metin, re.M)):
            if k in sahip and sahip[k] != f:
                cakisan.append((k, sahip[k], f))
            sahip[k] = f
    assert not cakisan, 'çakışan anahtarlar: %s' % cakisan[:6]


def test_olcum_kaniti_yerinde():
    """Kalemlerin önce/sonra sayıları kanıt dizininde durmalı."""
    d = os.path.join(KOK, 'docs', 'scofield', 'raw', 'OH', 'D17', 'electron', 'a1')
    once = json.load(open(kanit_gerekli(os.path.join(d, 'once.json')), encoding='utf-8'))
    sonra = json.load(open(kanit_gerekli(os.path.join(d, 'sonra.json')), encoding='utf-8'))
    assert set(once) == set(sonra)
    assert len(once) == 11, 'ölçüm 11 kalemi kapsamalı, %d var' % len(once)
