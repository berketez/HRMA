# -*- coding: utf-8 -*-
"""ÖH Dalga-25 · kulvar electron · aşama 1/1 — bekçiler.

Kapsanan kalem
--------------
``P12aB5-06``  (ŞART, Fable-D19) "/launch-site sayfasında 'Ayarlar' ve
               'Sürüm Notları' bağlantıları HİÇ çizilmiyor; Ayarlar o
               sayfada hiçbir yoldan açılamıyor."

               JS yarısı D18'de (release_notes.js'teki TEK tanımlı
               ``NAV_HOSTS`` tablosu + ``window.HRMA_SHELL_NAV``), yerel
               pencere menüsü yarısı D24'te (OH-D23-02, launcher.py
               'Settings…' MenuAction) kapandı. ŞART bu iki yarının
               yerinde durduğunu ölçmeyi ister.

               BU AŞAMADA ÖLÇÜLEN VE ONARILAN KUSUR — bekçi boşluğu:
               kalemin kendi kusuru bugün geri gelse mevcut bekçiler
               YAKALAMIYORDU. Kusuru geri getirmenin en kısa yolu
               bağlantı kodunu bozmak değil, kabuk betiğini şablondan
               DÜŞÜRMEKTİR: betik yüklenmezse şerit bağlantısı çizilmez
               ve ``window.hrmaShowSettings`` hiç tanımlanmaz — menü
               ögesi kardeşleriyle ortak ``window.x && x()`` deseni
               yüzünden SESSİZCE hiçbir şey yapar (istisna bile atmaz).

               ÖLÇÜLDÜ (once_bekci_boslugu.json): 6 kusur enjeksiyonundan
               yalnız 1'i (release_notes.js düşürülmesi) yakalanıyordu;
               kalemin kendi kusuru olan
               ``launch_site.html::settings_panel.js`` dâhil 5'i tüm
               bekçiler yeşilken KAÇIYORDU.

Sözleşme notu: bu dosya TARAYICI AÇMAZ. Canlı ölçümün kendisi
``docs/scofield/raw/OH/D25/electron/a1/tur_p12ab5_06.json`` dosyasındadır;
buradaki bekçiler ölçümün ürüne DOĞRU yansıdığını sınar.

Envanter TEK KAYNAKTAN türetilir (ÖK/doktrin-4): gereken betik listesi
elle yazılmaz, ``packaging/launcher.py`` menüsünün çağırdığı köprülerden
ve o köprüleri yayımlayan JS dosyalarından çıkarılır; kabuk şeritleri de
``release_notes.js``teki ``NAV_HOSTS`` tablosundan okunur. Menüye yeni bir
öge eklendiğinde bekçi kendiliğinden onu da şart koşar.
"""
from __future__ import annotations

import ast
import json
import os
import re

import pytest
from tests.support.kanit import kanit_gerekli

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL = os.path.join(ROOT, 'hrma', 'templates')
JSD = os.path.join(ROOT, 'hrma', 'static', 'js')
KANIT_DIZINI = os.path.join(ROOT, 'docs', 'scofield', 'raw', 'OH', 'D25',
                            'electron', 'a1')
MENU_ISLEVLERI = ('_macos_menu', '_windows_menu')


def _oku(*parcalar):
    with open(os.path.join(ROOT, *parcalar), encoding='utf-8',
              errors='replace') as f:
        return f.read()


def _launcher():
    return _oku('packaging', 'launcher.py')


def _menu_handlerlari(kaynak: str) -> dict:
    """{menü işlevi: [(etiket, handler adı), ...]} — MenuAction çağrıları."""
    agac = ast.parse(kaynak)
    tanimlar = {d.name: d for d in ast.walk(agac)
                if isinstance(d, ast.FunctionDef)}
    cikti = {}
    for fn in MENU_ISLEVLERI:
        d = tanimlar.get(fn)
        if d is None:
            continue
        ogeler = []
        for dugum in ast.walk(d):
            if (isinstance(dugum, ast.Call)
                    and isinstance(dugum.func, ast.Attribute)
                    and dugum.func.attr == 'MenuAction'
                    and dugum.args
                    and isinstance(dugum.args[0], ast.Constant)):
                h = dugum.args[1] if len(dugum.args) > 1 else None
                ogeler.append((dugum.args[0].value,
                               h.id if isinstance(h, ast.Name) else None))
        cikti[fn] = ogeler
    return cikti


def _menu_koprulari() -> dict:
    """{köprü adı: [(menü işlevi, etiket), ...]} — menüden çağrılan
    ``window.hrma*`` köprüleri, hangi ögeden çağrıldığıyla."""
    kaynak = _launcher()
    agac = ast.parse(kaynak)
    govdeler = {d.name: (ast.get_source_segment(kaynak, d) or '')
                for d in ast.walk(agac) if isinstance(d, ast.FunctionDef)}
    cikti: dict = {}
    for fn, ogeler in _menu_handlerlari(kaynak).items():
        for etiket, handler in ogeler:
            for ad in re.findall(r'window\.(hrma[A-Za-z0-9_]+)',
                                 govdeler.get(handler, '')):
                cikti.setdefault(ad, []).append((fn, etiket))
    return cikti


def _js_kod(dosya: str) -> str:
    """JS dosyasının YORUMSUZ gövdesi.

    Yorumlar ayıklanmazsa açıklama metnindeki ``window.HRMA_VERSION`` gibi
    anmalar bağımlılık sanılır (ölçüldü: settings_panel.js:87 yalnız yorumda
    geçiyor)."""
    ham = _oku('hrma', 'static', 'js', dosya)
    ham = re.sub(r'/\*.*?\*/', '', ham, flags=re.S)
    return re.sub(r'(^|[^:\'"\\])//[^\n]*', r'\1', ham)


#: ``X = ...`` ataması — ``X === ...`` karşılaştırmasıyla karışmasın diye
#: ``=`` ardından ikinci ``=`` gelmemeli (ölçüldü: bug_report.js:608
#: ``typeof global.open === 'function'`` yayın sanılıyordu).
ATAMA = r'(?:window|global)\.([A-Za-z_$][\w$]*)\s*=(?!=)'
ANMA = r'(?:window|global)\.([A-Za-z_$][\w$]*)'


def _yayimlayan(desen: str = None) -> dict:
    """{genel ad: {yayımlayan js dosyası}} — kabuk betikleri ``window.X =``
    ya da IIFE içinde ``global.X =`` ile yayımlar."""
    desen = desen or ATAMA
    cikti: dict = {}
    for dosya in sorted(os.listdir(JSD)):
        if not dosya.endswith('.js'):
            continue
        for ad in re.findall(desen, _js_kod(dosya)):
            cikti.setdefault(ad, set()).add(dosya)
    return cikti


def _gereken_kabuk_betikleri() -> tuple:
    """Kabuk şeridi çizen HER sayfada bulunması gereken betik kümesi —
    elle yazılmaz, TÜRETİLİR:

      1. ``packaging/launcher.py`` menüsünün çağırdığı ``window.hrma*``
         köprülerini yayımlayan dosyalar,
      2. şerit tablosunu (``NAV_HOSTS``) tanımlayan ``release_notes.js``,
      3. (1)+(2)'nin KODUNDA (yorumda değil) tükettiği ve başka bir kabuk
         dosyasının yayımladığı genel adların kaynakları — bunlar yüklü
         değilse ilgili bölüm SESSİZCE düşer (ör. ``HRMABugReport`` yoksa
         Ayarlar penceresi açılır ama içindeki "Hata bildir" bölümü hiç
         çizilmez: settings_panel.js ``appendBugSection`` → ``if (!BR)
         return;``).

    ``(gereken küme, gerekçe sözlüğü)`` döner."""
    yayim = _yayimlayan()
    koprular = _menu_koprulari()
    gereken = {'release_notes.js'}
    gerekce = {'release_notes.js': ['NAV_HOSTS şerit tablosu']}
    for ad in sorted(koprular):
        for dosya in sorted(yayim.get(ad, set())):
            gereken.add(dosya)
            gerekce.setdefault(dosya, []).append('menü köprüsü %s' % ad)
    for dosya in sorted(gereken):
        for ad in sorted(set(re.findall(ANMA, _js_kod(dosya)))):
            for kaynak in sorted(yayim.get(ad, set()) - gereken):
                gerekce.setdefault(kaynak, []).append(
                    '%s dosyasının kullandığı %s' % (dosya, ad))
    gereken |= set(gerekce)
    return gereken, gerekce


def _kabuk_capalari() -> list:
    """release_notes.js'teki NAV_HOSTS tablosundan şerit seçicileri."""
    js = _oku('hrma', 'static', 'js', 'release_notes.js')
    m = re.search(r'var\s+NAV_HOSTS\s*=\s*\[(.*?)\];', js, re.S)
    assert m, 'release_notes.js: NAV_HOSTS tablosu bulunamadı'
    return re.findall(r"host:\s*'([^']+)'", m.group(1))


def _sablon_capalari(html: str, capalar) -> list:
    bulunan = []
    for sec in capalar:
        if sec.startswith('.'):
            varmi = re.search(r'class\s*=\s*"[^"]*\b%s\b' % re.escape(sec[1:]),
                              html)
        else:
            varmi = re.search(r'id\s*=\s*"%s"' % re.escape(sec[1:]), html)
        if varmi:
            bulunan.append(sec)
    return bulunan


def _capali_sablonlar() -> dict:
    """{şablon adı: (html, [bulunan çapalar])} — kabuk şeridi çizen sayfalar."""
    capalar = _kabuk_capalari()
    cikti = {}
    for ad in sorted(os.listdir(TPL)):
        if not ad.endswith('.html'):
            continue
        html = _oku('hrma', 'templates', ad)
        bulunan = _sablon_capalari(html, capalar)
        if bulunan:
            cikti[ad] = (html, bulunan)
    return cikti


# ---------------------------------------------------------------------------
# P12aB5-06 — menü köprüsü zinciri: menü ögesi → köprü → betik → şablon
# ---------------------------------------------------------------------------
class TestP12aB506MenuKoprusuZinciri:
    """Yerel pencere menüsündeki her öge ``window.<köprü> && <köprü>()``
    deseniyle çağırır. Zincirin herhangi bir halkası kopunca öge SESSİZCE
    hiçbir şey yapar; kullanıcı ayarları açamaz ve hiçbir hata görmez.
    Bu yüzden zincir uçtan uca şart koşulur."""

    def test_ayarlar_ogesi_iki_platform_menusunde_de_var(self):
        """ŞART'ın ikinci yarısı (OH-D23-02) yerinde mi — hem macOS
        uygulama menüsünde hem Windows menü çubuğunda."""
        handlerlar = _menu_handlerlari(_launcher())
        assert set(handlerlar) == set(MENU_ISLEVLERI), sorted(handlerlar)
        for fn, ogeler in handlerlar.items():
            ayarlar = [h for e, h in ogeler
                       if re.search(r'settings', e or '', re.I)]
            assert ayarlar == ['_menu_settings'], (fn, ogeler)

    def test_her_menu_koprusu_TEK_betikte_yayimlaniyor(self):
        """İki dosya aynı köprüyü yayımlarsa hangisinin kazandığını yükleme
        sırası belirler — sessiz ayrışma. Tek kaynak şart."""
        yayim = _yayimlayan()
        koprular = _menu_koprulari()
        assert koprular, 'menüden çağrılan köprü bulunamadı (ayrıştırma bozuk)'
        for ad in sorted(koprular):
            kaynaklar = yayim.get(ad, set())
            assert len(kaynaklar) == 1, (
                '%s köprüsünü %d dosya yayımlıyor: %s' % (
                    ad, len(kaynaklar), sorted(kaynaklar)))

    def test_yetim_kopru_yok(self):
        """Ürün bir ``hrma*`` köprüsü yayımlıyorsa menü ya onu çağırır ya
        da kalem açılır (OH-D23-02 sözleşmesi burada da tutulur)."""
        cagrilan = set(re.findall(r'window\.(hrma[A-Za-z0-9_]+)', _launcher()))
        yayim = _yayimlayan(r'window\.(hrma[A-Za-z0-9_]+)\s*=(?!=)')
        assert sorted(set(yayim) - cagrilan) == []

    def test_kabuk_capasi_olan_her_sablon_menu_betiklerini_YUKLUYOR(self):
        """ÖLÇÜLEN BEKÇİ BOŞLUĞU (once_bekci_boslugu.json): kabuk şeridi
        çizen bir şablondan ``settings_panel.js`` düşürülünce /launch-site'ta
        ne Ayarlar bağlantısı çizilir ne de menü ögesi bir şey yapar —
        P12aB5-06'nın TAM kusuru — ama bütün bekçiler yeşil kalıyordu
        (6 enjeksiyondan 5'i kaçıyordu).

        Gereken betik listesi elle yazılmaz: menünün çağırdığı köprüleri
        yayımlayan dosyalar + şerit tablosunu tanımlayan dosya."""
        gereken, gerekce = _gereken_kabuk_betikleri()
        # Vakumsuzluk: türetme çökerse bekçi boş/eksik kümeyle yeşil kalmasın.
        assert {'release_notes.js', 'settings_panel.js', 'user_guide.js',
                'update_check.js', 'bug_report.js', 'i18n.js'} <= gereken, \
            sorted(gereken)

        sablonlar = _capali_sablonlar()
        assert len(sablonlar) >= 6, sorted(sablonlar)

        eksikler = []
        for ad, (html, capalar) in sablonlar.items():
            for betik in sorted(gereken):
                if '/static/js/%s' % betik not in html:
                    eksikler.append(
                        '%s (%s şeridi): %s yüklü değil — gerekçe: %s'
                        % (ad, ','.join(capalar), betik,
                           '; '.join(gerekce.get(betik, ['—']))))
        assert eksikler == [], '\n'.join(eksikler)

    def test_ayarlar_koprusu_launch_site_kabugunda_TAM_zincir(self):
        """Kalemin adını taşıyan sayfa için zincir tek tek: şerit çapası →
        tablo betiği → ayar betiği → köprü yayını → menü ögesi."""
        html = _oku('hrma', 'templates', 'launch_site.html')
        assert '#ls-topbar' in _kabuk_capalari()
        assert re.search(r'id\s*=\s*"ls-topbar"', html)
        i = html.find('/static/js/release_notes.js')
        j = html.find('/static/js/settings_panel.js')
        assert i >= 0 and j >= 0 and i < j, (i, j)
        js = _oku('hrma', 'static', 'js', 'settings_panel.js')
        assert re.search(r'window\.hrmaShowSettings\s*=', js)
        assert 'hrmaShowSettings' in _menu_koprulari()


# ---------------------------------------------------------------------------
# P12aB5-06 — canlı turun ürüne yansıması
# ---------------------------------------------------------------------------
class TestP12aB506CanliTur:
    """Statik bekçiler betiğin YÜKLENDİĞİNİ şart koşar; bu sınıf o betiğin
    gerçek tarayıcıda /launch-site'ta İŞE YARADIĞINI ölçen turun kaydını
    ürünün kendisiyle çaprazlar (kayıt tek başına delil sayılmaz)."""

    @pytest.fixture(scope='class')
    def tur(self):
        yol = os.path.join(KANIT_DIZINI, 'tur_p12ab5_06.json')
        if not os.path.exists(kanit_gerekli(yol)):
            pytest.skip('canlı tur kaydı yok: %s' % yol)
        with open(kanit_gerekli(yol), encoding='utf-8') as f:
            return json.load(f)

    def test_uc_kabuk_baglantisi_gercek_sayfada_cizildi(self, tur):
        assert tur['sayfa'].endswith('/launch-site'), tur['sayfa']
        for kimlik in ('settingsLink', 'releaseNotesLink', 'userGuideLink'):
            assert kimlik in tur['topbar_kimlikleri'], (
                kimlik, tur['topbar_kimlikleri'])
        assert tur['topbar_kimlikleri'][-1] == 'ls-link:site.back', (
            'Uygulamaya dön en sağda kalmalı', tur['topbar_kimlikleri'])

    def test_menu_ifadesi_ayarlari_gercekten_acti(self, tur):
        """Yerel menü ögesinin çalıştırdığı İFADENİN tıpatıp aynısı."""
        assert tur['menu_ifadesi'] == (
            'window.hrmaShowSettings && window.hrmaShowSettings()')
        assert tur['menu_ifadesi_modal_acti'] is True
        assert tur['baglanti_tiklamasi_modal_acti'] is True
        assert tur['konsol_hatalari'] == [], tur['konsol_hatalari']

    def test_turun_kullandigi_kimlikler_urunle_ayni(self, tur):
        """Tur kaydı ürünle çaprazlanır: modal kimliği settings_panel.js'te,
        menü ifadesi launcher.py'de aynen geçmeli — kayıt tek başına delil
        değildir."""
        js = _oku('hrma', 'static', 'js', 'settings_panel.js')
        assert "getElementById('%s')" % tur['modal_kimligi'] in js, (
            tur['modal_kimligi'])
        assert tur['menu_ifadesi'] in _launcher()


# ---------------------------------------------------------------------------
# OH-D24-16 (okuma ayağı) — dizi datumu VARSAYILANI çözücünün ilanıyla bağlı
# ---------------------------------------------------------------------------
class TestOHD2416DatumVarsayilani:
    """Kalem AÇIK kalır: ``/api/six-dof-analysis`` yanıtı
    ``series.altitude_datum`` alanını HÂLÂ yayımlamıyor (ölçüldü,
    once_ohd2416.json: series anahtarları alpha_deg/altitude/east/mach/
    north/speed/time — datum yok), bu yüzden ``launch_site_globe.js``
    alan yokken ``ALT_DATUM_VARSAYILAN``ı uyguluyor. Uç yayını bu kulvarın
    sahasında DEĞİL (hrma/app.py 6-DOF ucu + six_dof_trajectory.py);
    okuma ayağını uç yayımlamadan fail-closed yapmak, bugün DOĞRU çizilen
    uçuş yolunu çizilemez hâle getirirdi.

    Okuma ayağının bu aşamada kapatılabilen yarısı: varsayılan artık
    denetimsiz bir varsayım değil, ÇÖZÜCÜNÜN İLANINA BAĞLI. Çözücü datumu
    değiştirir de uç yine yayımlamazsa (yani okuyucu varsayılana düşmeye
    devam ederse) küre uçuşu sessizce h0 kadar kaydırırdı — bu bekçi o
    ayrışmayı kırmızıya çevirir.

    D22 bekçisi (test_d22_electron_a1.py::TestUcusIrtifasiDatumu) okumanın
    VARLIĞINI ve tanınmayan datumun reddini şart koşuyor; varsayılanın
    DEĞERİNİ hiçbir bekçi çözücüyle çaprazlamıyordu."""

    def test_varsayilan_datum_cozucunun_ilan_ettigi_datum(self):
        js = _js_kod('launch_site_globe.js')
        sabitler = dict(re.findall(
            r"var\s+(ALT_DATUM_[A-Z_]+)\s*=\s*'([a-z_]+)'", js))
        varsayilan_adi = re.search(
            r'var\s+ALT_DATUM_VARSAYILAN\s*=\s*([A-Z_]+)\s*;', js)
        assert varsayilan_adi, 'ALT_DATUM_VARSAYILAN tanımı bulunamadı'
        deger = sabitler.get(varsayilan_adi.group(1))
        assert deger, (varsayilan_adi.group(1), sabitler)

        cozucu = _oku('hrma', 'analysis', 'six_dof_trajectory.py')
        ilan = sorted(set(re.findall(
            r"'altitude_datum':\s*'([a-z_]+)'", cozucu)))
        assert ilan, 'çözücü altitude_datum ilan etmiyor'
        assert deger in ilan, (
            'küre alan yokken %r datumunu uyguluyor ama çözücü %s ilan '
            'ediyor — uç alanı yayımlamadığı sürece uçuş yolu sessizce '
            'h0 kadar kayar' % (deger, ilan))

    def test_varsayilan_datum_taninan_kumede(self):
        js = _js_kod('launch_site_globe.js')
        assert re.search(r'ALT_DATUM_BILINEN\s*=\s*\[\s*ALT_DATUM_AGL\s*,'
                         r'\s*ALT_DATUM_MSL\s*\]', js)
        assert re.search(r'series\.altitude_datum\s*\|\|\s*'
                         r'ALT_DATUM_VARSAYILAN', js), (
            'varsayılanın uygulandığı satır değişti — bekçi bayatladı')
