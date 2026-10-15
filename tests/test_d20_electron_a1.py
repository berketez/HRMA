# -*- coding: utf-8 -*-
"""ÖH Dalga-20 / kulvar `electron` / aşama a1 — bekçiler.

Onarılan 11 kalem (parti P12A, bölüm B3/B4/B5). Her iddia onarımın geçici
olarak geri alınmasıyla KIRMIZIYA döner; ters mutasyon kanıtı
``docs/scofield/raw/OH/D20/electron/a1/mutasyon.json``.

  P12aB5-08  Ayarlar penceresi 6 sayfanın 5'inde çıplak "v?" basıyordu;
             aynı andaki hata kaydı aynı sayfalarda sürümü doğru buluyordu.
             İki ayrı okuyucu vardı. Panel artık `bug_report.detectVersion`
             ÇAĞIRIYOR ve okunamayan sürümü beyanla ("denenen kaynaklar…")
             bildiriyor.
  P12aB5-09  `--hd-ink-faint` kullanıldığı DÖRT zeminde de WCAG AA eşiğinin
             altındaydı (2,75-3,03; eşik 4,5) ve 11-13 px metinlerde
             kullanılıyordu.
  P12aB4-14  Aynı kökün iki ürün metni (şerit "PROJECT" etiketi + STEP
             beyanı); şerit etiketi 2,75:1 idi.
  P12aB5-10  `results_hud.css` risk matrisi kurallarının 7'si de ürünün
             bastığı sınıflarla eşleşmiyordu; renk merdiveni satır içi bir
             ikinci tablodan (BAND_BG) geliyor, tasarımın kehribar basamağı
             kayboluyordu.
  P12aB3-07  `/launch-site` dört buton ipucu İngilizce sabitti; oynat/
             duraklat düğmesinin TEK yazısı o ipucuydu.
  P12aB3-11  Altyazı yedekleri sözlükten yalnız tipografik kesme işareti
             (U+2019) yüzünden üç kalemde ayrışıyordu.
  P12aB4-09  `/api/flight-vehicle` 'results' kolu köprünün gönderdiği
             `motor_name`'i hiç okumuyordu; ekran jenerik "Hybrid Motor"
             yazıyordu.
  P12aB4-11  Kaydedilmemiş değişiklikleri ATAN iki onayın düğmesi nötr
             "TAMAM" idi; aynı yol tarayıcının `beforeunload` korumasını da
             kapatıyordu.
  P12aB4-13  `--hd-yellow` hiçbir CSS dosyasında tanımlı değildi.
  P12aB4-15  Sunucu hata metinleri `I18N.serverText` köprüsünden geçmiyordu.
  P12aB4-16  İstemci ad aynası sunucunun 22 ayrılmış Windows adını hiç
             tanımıyordu (22/22 geçiyordu).
"""
import json
import os
import re
import subprocess

import pytest
from tests.support.kanit import kanit_gerekli

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KANIT = os.path.join(KOK, 'docs', 'scofield', 'raw', 'OH', 'D20',
                     'electron', 'a1')

AA_ESIK = 4.5          # WCAG 2.1 AA — normal metin


def oku(rel):
    with open(os.path.join(KOK, rel), encoding='utf-8') as f:
        return f.read()


def govde(kaynak, imza):
    """`imza`dan sonraki ilk dengeli `{`...`}` bloğunu (imza dâhil) döndürür."""
    i = kaynak.index(imza)
    j = kaynak.index('{', i)
    derinlik = 0
    for k in range(j, len(kaynak)):
        if kaynak[k] == '{':
            derinlik += 1
        elif kaynak[k] == '}':
            derinlik -= 1
            if derinlik == 0:
                return kaynak[i:k + 1]
    raise AssertionError('kapanmayan blok: ' + imza)


def node_harness(ad):
    """Kanıt dizinindeki node harness'ını koşup JSON çıktısını döndürür."""
    yol = os.path.join(KANIT, ad)
    if not os.path.exists(kanit_gerekli(yol)):
        pytest.skip('harness yok: ' + ad)
    r = subprocess.run(['node', kanit_gerekli(yol)], capture_output=True, text=True,
                       timeout=120)
    assert r.returncode == 0, f'{ad} koşumu başarısız:\n{r.stderr[-800:]}'
    return json.loads(r.stdout)


# --- WCAG yardımcıları (tek tanım; ölçüm betiğiyle aynı formül) ------------

def _srgb(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _lum(rgb):
    return (0.2126 * _srgb(rgb[0]) + 0.7152 * _srgb(rgb[1])
            + 0.0722 * _srgb(rgb[2]))


def _hex(h):
    h = h.strip().lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _uzerine(on, alt, alfa):
    return tuple(on[i] * alfa + alt[i] * (1 - alfa) for i in range(3))


def kontrast(a, b):
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def token(kaynak, ad):
    m = re.search(r'--' + ad + r':\s*([^;]+);', kaynak)
    assert m, f'--{ad} tanımlı değil'
    return m.group(1).strip()


#: `var(--hd-X, #hex)` biçimindeki yedek literalleri. Tek yerde tanımlı:
#: iki bekçi de aynı taramayı okur, ikinci bir kopya tarama yoktur.
_YEDEK_RE = re.compile(r'var\(\s*--(hd-[a-z0-9-]+)\s*,\s*(#[0-9A-Fa-f]{3,8})\s*\)')

#: theme.css'te HEX karşılığı OLMAYAN, ama üründe yedekle kullanılan token
#: adları (ÖLÇÜLDÜ 2026-09-09). `hd-inset` tanımlı ama değeri `rgba(...)`;
#: kalan altısı hiç tanımlı değil. D29 adayı, fix-28b sahası değil.
#: ÖH D31 · OH-D26-03 — 'hd-amber' bu kümeden ÇIKTI: theme.css'te artık
#: gerçek token (#ffbe46) ve yukarıdaki eşitlik kuralı onu kapsıyor.
#: Kalan altı ad hâlâ temasız (D31 sonrası aday).
_TEMASIZ_YEDEK_ADLARI = frozenset({
    'hd-bg', 'hd-dim', 'hd-inset', 'hd-muted', 'hd-violet',
    'hd-warn',
})


def _tokenlar(kaynak):
    return {m.group(1): m.group(2).strip().lower()
            for m in re.finditer(r'--(hd-[a-z0-9-]+):\s*([^;]+);', kaynak)}


def _tema_tokenleri():
    """(theme.css, hd_doc.css) token sözlükleri --- DEĞERLER DOSYADAN OKUNUR."""
    return (_tokenlar(oku('hrma/static/css/theme.css')),
            _tokenlar(oku('hrma/static/css/hd_doc.css')))


def _yedek_literalleri():
    """`hrma/` ağacındaki (göreli_yol, token_adı, yedek_hex, satır) dörtlüleri."""
    bulunan = []
    for kok, _d, dosyalar in os.walk(os.path.join(KOK, 'hrma')):
        for d in sorted(dosyalar):
            if not d.endswith(('.js', '.css', '.html')):
                continue
            yol = os.path.join(kok, d)
            try:
                metin = open(yol, encoding='utf-8').read()
            except (OSError, UnicodeDecodeError):
                continue
            rel = os.path.relpath(yol, KOK)
            for m in _YEDEK_RE.finditer(metin):
                bulunan.append((rel, m.group(1), m.group(2),
                                metin.count('\n', 0, m.start()) + 1))
    return bulunan


def zeminler(theme):
    bg0 = _hex(token(theme, 'hd-bg0'))
    out = {'--hd-bg0': bg0,
           '--hd-panel-solid': _hex(token(theme, 'hd-panel-solid'))}
    for ad in ('hd-panel', 'hd-inset'):
        m = re.match(r'rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)',
                     token(theme, ad))
        assert m, ad
        out['--' + ad] = _uzerine(tuple(float(m.group(i)) for i in (1, 2, 3)),
                                  bg0, float(m.group(4)))
    return out


# =========================================================================
# P12aB5-08 — tek sürüm okuyucusu
# =========================================================================
class TestP12aB508SurumOkuyucu:

    def test_ayarlar_paneli_kendi_kaynak_listesini_tasimaz(self):
        """Panelde İKİNCİ bir sürüm kaynağı listesi kalmamalı."""
        s = oku('hrma/static/js/settings_panel.js')
        assert 'function versionInfo(' in s, 'sürüm çözücüsü bulunamadı'
        blok = govde(s, 'function versionInfo(')
        # Kaynak adları YALNIZ bug_report.js'te yaşar; panel onları saymaz.
        for kaynak in ('HRMA_APP_VERSION', 'HRMA_VERSION', '.footer'):
            assert kaynak not in blok, (
                f'ayarlar paneli sürüm kaynağını yeniden sayıyor: {kaynak}')
        assert 'HRMABugReport' in blok and 'detectVersion' in blok, (
            'panel ortak çözücüyü çağırmıyor')

    def test_okunamayan_surum_beyanli_basilir(self):
        """Çıplak '?' YOK: okunamadıysa denenen kaynaklar yazılır."""
        s = oku('hrma/static/js/settings_panel.js')
        assert "return '?'" not in s, "çıplak '?' geri geldi"
        assert 'shell.settings.versionUnknown' in s
        assert 'shell.settings.versionBasis' in s

    def test_alti_sayfada_panel_ile_hata_kaydi_ayrismaz(self):
        h = node_harness('harness_versiyon.js')
        assert h['ayrisan_sayfa'] == 0, (
            f"panel/hata kaydı {h['ayrisan_sayfa']} sayfada ayrışıyor: "
            f"{[x['sayfa'] for x in h['senaryolar'] if x['ayrisma']]}")
        assert h['sessiz_soru_isareti'] == 0, 'beyansız boşluk kaldı'
        assert h['beyanli_bosluk'] == 3, (
            'sürümü hiç yayımlamayan üç sayfada beyan bekleniyordu')
        assert h['ortak_cozucu'] is True
        assert h['settings_kaynak_sayisi'] == 0

    def test_yeni_anahtarlar_iki_dilde_tanimli(self):
        s = oku('hrma/static/js/i18n_shell.js')
        for k in ('shell.settings.versionUnknown', 'shell.settings.versionBasis'):
            assert s.count("'%s'" % k) == 2, f'{k} iki dilde tanımlı değil'

    def test_beyan_dugumleri_dil_degisiminde_tazelenir(self):
        """Dil seçici bu panelin İÇİNDE: beyan düğümleri data-i18n taşımalı.

        Parametreli olan ayrıca `data-i18n-params` taşır, yoksa `I18N.apply`
        şablonu çıplak `{sources}` ile ezerdi.
        """
        s = oku('hrma/static/js/settings_panel.js')
        assert "setAttribute('data-i18n', 'shell.settings.versionUnknown')" in s
        assert "setAttribute('data-i18n', 'shell.settings.versionBasis')" in s
        assert "setAttribute('data-i18n-params'" in s


# =========================================================================
# P12aB5-09 + P12aB4-14 — kontrast
# =========================================================================
class TestP12aB509Kontrast:

    def test_tum_murekkepler_dort_zeminde_AA_gecer(self):
        theme = oku('hrma/static/css/theme.css')
        Z = zeminler(theme)
        kalan = []
        for mk in ('hd-ink', 'hd-ink-strong', 'hd-ink-dim', 'hd-ink-faint',
                   'hd-cyan', 'hd-cyan-soft', 'hd-orange', 'hd-green',
                   'hd-red'):
            deger = token(theme, mk)
            if not deger.startswith('#'):
                continue
            for zad, z in Z.items():
                oran = kontrast(_hex(deger), z)
                if oran < AA_ESIK:
                    kalan.append((mk, zad, round(oran, 2)))
        assert not kalan, f'WCAG AA eşiğinin altında kalan çiftler: {kalan}'

    def test_iki_css_dosyasi_ortak_tokenlerde_ayrismiyor(self):
        """`theme.css` ve `hd_doc.css` AYNI token kümesini AYNI değerle verir.

        ÖH D28 fix-28b: eski hâli yalnız ``--hd-ink-faint``i karşılaştırıyordu.
        Tek bir adı korumak, geri kalan 21 tokenin sessizce ayrışmasına izin
        veriyordu; ölçüldü (2026-09-09): iki dosyada da 22 token var ve
        hepsi eşit. Kural artık kümenin tamamına bakar, ada değil.
        """
        theme, hddoc = _tema_tokenleri()
        assert set(theme) == set(hddoc), (
            'iki CSS dosyası farklı token kümesi tanımlıyor; yalnız '
            'theme.css: %s, yalnız hd_doc.css: %s'
            % (sorted(set(theme) - set(hddoc)), sorted(set(hddoc) - set(theme))))
        ayrisan = {ad: (theme[ad], hddoc[ad])
                   for ad in sorted(theme) if theme[ad] != hddoc[ad]}
        assert not ayrisan, f'theme.css ve hd_doc.css ayrışmış: {ayrisan}'

    def test_yedek_hexler_tema_tokeninden_ayrismiyor(self):
        """Her `var(--hd-X, #hex)` yedeği theme.css'teki `--hd-X` ile AYNI.

        NEDEN ÜRÜN KURALI: yedek yalnız CSS değişkeni ÇÖZÜLEMEDİĞİNDE
        (tema dosyası yüklenmemişse, gölge kökte, ilk boyamada) kullanılır.
        Ayrışan bir yedek, o anda ekranda temanın söylemediği bir renk
        demektir. Berke'nin kuralı (9 Eyl 2026): "arayüzle uyumlu olsun".

        ÖH D28 fix-28b: eski hâli TEK adı (``--hd-ink-faint``) tarıyordu.
        Kural artık ADA BAĞLI DEĞİL: token değeri theme.css'ten OKUNUR,
        teste kopyalanmaz, ve hrma/ altındaki HER yedek ölçülür.
        ÖLÇÜLEN TABAN (2026-09-09, bu onarımdan önce): 558 yedek, 503
        uyumlu, 8 ayrışan --- ``--hd-cyan-soft`` x4 (update_check.js:339,
        project_bar.js:987, settings_panel.js:113/784; #6fd3e6 vs #3af2ff),
        ``--hd-orange`` x2 (settings_panel.js:266/267; #ffb454 vs #ff8c33),
        ``--hd-ink`` x2 (injector_schematics.js:105 #d7e3ee,
        analysis_center.js:958 #d7e6ee vs #cfe8f2). Sekizi de token
        değerine çekildi.
        """
        theme, _ = _tema_tokenleri()
        ayrisan = []
        for yol, ad, hx, satir in _yedek_literalleri():
            deger = theme.get(ad)
            if deger is None or not deger.startswith('#'):
                continue
            if hx.lower() != deger:
                ayrisan.append((yol, satir, ad, hx, deger))
        assert not ayrisan, (
            'token ile ayrışan yedek literaller (dosya, satır, token, '
            f'yedek, token değeri): {ayrisan}')

    def test_temada_karsiligi_olmayan_yedek_envanteri(self):
        """Yedeği olan ama theme.css'te HEX karşılığı olmayan token adları.

        Bu adlar için ``var()`` hiçbir zaman çözülmez (ya token tanımsızdır
        ya da değeri ``rgba(...)``), yani yedek HER ZAMAN kullanılır ---
        tema o rengi yönetmiyor demektir. Bu bir TASARIM kararıdır (token
        tanımlanacak mı, yoksa renk oraya ait değil mi) ve fix-28b'nin
        sahası değildir; D29 adayı olarak ADIYLA ilan edilir.

        Bekçinin işi: liste BÜYÜMESİN. Yeni bir ad girerse kırmızıya döner;
        bir ad token kazanınca da (liste küçülünce) kırmızı olur, çünkü o
        zaman bu envanter bayatlamıştır ve yukarıdaki eşitlik kuralı devralır.
        ÖLÇÜLEN TABAN (2026-09-09): 47 yedek, 7 ad.
        """
        theme, _ = _tema_tokenleri()
        adlar = {ad for _yol, ad, _hx, _satir in _yedek_literalleri()
                 if not (theme.get(ad) or '').startswith('#')}
        assert adlar == _TEMASIZ_YEDEK_ADLARI, (
            'temada hex karşılığı olmayan yedek adları değişti; yeni: %s, '
            'kalkan: %s --- D29 kalemi "yedek hex tema tokenine bağlı değil"'
            % (sorted(adlar - _TEMASIZ_YEDEK_ADLARI),
               sorted(_TEMASIZ_YEDEK_ADLARI - adlar)))

    def test_p12ab4_14_iki_urun_metni_AA_gecer(self):
        """Şerit "PROJECT" etiketi ve STEP beyanı --hd-panel-solid üstünde."""
        theme = oku('hrma/static/css/theme.css')
        ps = _hex(token(theme, 'hd-panel-solid'))
        for rel, desen in (
                ('hrma/static/js/project_bar.js', r"'proj\.label'"),
                ('hrma/static/js/step_import_ui.js', r'stepimp\.noTargetShort')):
            metin = oku(rel)
            m = re.search(desen, metin)
            assert m, f'{rel}: {desen} bulunamadı'
            parca = metin[max(0, m.start() - 700):m.start() + 300]
            murekkep = next((r for r in re.findall(r'var\(--(hd-ink[a-z-]*)',
                                                   parca)), None)
            assert murekkep, f'{rel}: mürekkep bulunamadı'
            oran = kontrast(_hex(token(theme, murekkep)), ps)
            assert oran >= AA_ESIK, (
                f'{rel} ({murekkep}) {oran:.2f}:1 — AA eşiği {AA_ESIK}')


# =========================================================================
# P12aB5-10 — risk matrisi tasarım katmanı
# =========================================================================
class TestP12aB510RiskMatrisi:

    def _siniflar(self):
        sp = oku('hrma/static/js/panels/safety_panel.js')
        duz = re.sub(r'\$\{[^}]*\}', ' ', sp)
        return {t for m in re.findall(r'class="([^"]*)"', duz)
                for t in m.split() if t.startswith('hd-')}

    def test_css_kurallari_urunun_bastigi_siniflarla_eslesir(self):
        hud = oku('hrma/static/css/results_hud.css')
        css = set(re.findall(r'\.hd-riskmatrix\s*>?\s*\.([A-Za-z0-9_-]+)', hud))
        urun = self._siniflar()
        olu = sorted(c for c in css if c not in urun and c != 'hit')
        assert not olu, f'ürünün hiç basmadığı CSS kuralları: {olu}'
        assert 'hd-rm-cell' in css and 'hd-rm-axis' in css

    def test_renk_merdiveni_tek_kaynakta(self):
        """Bant rengi YALNIZ results_hud.css'te; üründe satır içi tablo yok."""
        sp = oku('hrma/static/js/panels/safety_panel.js')
        assert 'BAND_BG' not in sp, 'satır içi bant rengi tablosu geri geldi'
        assert not re.search(r'grid-template-columns:\s*auto repeat\(5', sp), (
            'satır içi grid yerleşimi geri geldi (sayfa stilini ezer)')
        hud = oku('hrma/static/css/results_hud.css')
        merdiven = dict(re.findall(
            r'\.hd-riskmatrix \.hd-rm-cell\[data-band="(\w+)"\]\s*\{'
            r'\s*background:\s*([^;]+);', hud))
        for bant in ('low', 'medium', 'high', 'critical'):
            assert bant in merdiven, f'{bant} basamağı tanımlı değil'
        # Dört basamak dört AYRI renk olmalı (kehribar basamağı kaybolmasın)
        assert len({merdiven[b] for b in
                    ('low', 'medium', 'high', 'critical')}) == 4, (
            f'merdiven basamakları çakışıyor: {merdiven}')
        assert '190, 70' in merdiven['medium'], (
            "orta risk tasarımın kehribar tonunu kullanmıyor: "
            + merdiven['medium'])

    def test_bant_sozcugu_urunden_gelir(self):
        sp = oku('hrma/static/js/panels/safety_panel.js')
        assert 'data-band="${band}"' in sp, 'hücre bant sözcüğünü yayımlamıyor'


# =========================================================================
# P12aB3-07 — /launch-site buton ipuçları
# =========================================================================
class TestP12aB307ButonIpuclari:

    def test_ipucu_tasiyan_her_buton_cevrilebilir(self):
        tpl = oku('hrma/templates/launch_site.html')
        eksik = []
        for m in re.finditer(r'<button[^>]*>', tpl):
            et = m.group(0)
            if 'title="' in et and 'data-i18n-title=' not in et:
                idm = re.search(r'id="([^"]+)"', et)
                eksik.append(idm.group(1) if idm else et[:60])
        assert not eksik, f'İngilizce sabit ipucu taşıyan butonlar: {eksik}'

    def test_oynat_duraklat_iki_durumda_da_cevrilir(self):
        tpl = oku('hrma/templates/launch_site.html')
        assert "data-i18n-title=\"site.play\"" in tpl
        # Durum değiştikçe anahtar da değişir; aria-label aynı metni taşır.
        assert "'site.pause' : 'site.play'" in tpl
        assert "setAttribute('aria-label'" in tpl
        sozluk = oku('hrma/static/js/i18n_launch_site.js')
        for k in ('site.play', 'site.pause'):
            assert sozluk.count("'%s'" % k) == 2, (
                f'{k} iki dilde tanımlı değil')

    def test_ipucu_ile_gorunur_yazi_ayni_anahtari_kullanir(self):
        tpl = oku('hrma/templates/launch_site.html')
        for m in re.finditer(r'<button[^>]*>', tpl):
            et = m.group(0)
            a = re.search(r'data-i18n="([^"]+)"', et)
            b = re.search(r'data-i18n-title="([^"]+)"', et)
            if a and b:
                assert a.group(1) == b.group(1), (
                    f'ipucu ve yazı ayrı anahtar kullanıyor: {et[:80]}')


# =========================================================================
# P12aB3-11 — altyazı yedeği <-> sözlük
# =========================================================================
class TestP12aB311AltyaziYedegi:

    def test_yedek_metinler_sozlukle_birebir_ayni(self):
        cc = oku('hrma/static/js/chart_captions.js')
        ic = oku('hrma/static/js/i18n_common.js')
        en = ic[ic.index('\n        en: {'):ic.index('\n        tr: {')]
        anahtar = r"'(chartCap\.[A-Za-z0-9_]+)':\s*'((?:[^'\\]|\\.)*)'"
        yedek = dict(re.findall(anahtar, cc))
        sozluk = dict(re.findall(anahtar, en))
        assert yedek, 'yedek metinler okunamadı'

        def coz(x):
            return x.replace("\\'", "'").replace('\\"', '"')

        ayrisan = sorted(k for k, v in yedek.items()
                         if k in sozluk and coz(sozluk[k]) != coz(v))
        assert not ayrisan, f'yedek ile sözlük ayrışan anahtarlar: {ayrisan}'

    def test_yedeklerde_tipografik_kesme_yok(self):
        cc = oku('hrma/static/js/chart_captions.js')
        assert '\u2019' not in cc, (
            'sözlük ASCII kesme işareti kullanıyor; yedekte U+2019 var')


# =========================================================================
# P12aB4-09 — flight-vehicle motor adı
# =========================================================================
class TestP12aB409MotorAdi:

    def test_results_kolu_motor_name_veriyor(self):
        app = oku('hrma/app.py')
        i = app.index('def flight_vehicle()')
        kol = app[i:i + 4000]
        res = kol[kol.index("if source == 'results'"):
                  kol.index("elif source == 'project'")]
        assert 'motor_name=' in res, (
            "'results' kolu köprünün gönderdiği motor_name'i okumuyor")

    def test_ucta_kullanicinin_adi_kazanir(self):
        """Uç gerçekten çağrılır: gönderilen ad dönmelidir."""
        from hrma.app import app
        app.config['TESTING'] = True
        istemci = app.test_client()
        sonuc = {'motor': {'thrust': 1000.0, 'burn_time': 10.0,
                           'propellant_mass_total': 4.2,
                           'chamber_diameter': 0.1}}
        r = istemci.post('/api/flight-vehicle', json={
            'source': 'results', 'motor_type': 'hybrid',
            'motor_name': 'Berke Deneme Motoru', 'results': sonuc})
        assert r.status_code == 200, r.get_data(as_text=True)[:400]
        arac = (r.get_json() or {}).get('vehicle') or r.get_json()
        assert arac['motor_name'] == 'Berke Deneme Motoru', (
            f"kullanıcının adı düştü: {arac.get('motor_name')!r}")

    def test_ad_verilmezse_varsayilan_korunur(self):
        from hrma.app import app
        app.config['TESTING'] = True
        istemci = app.test_client()
        r = istemci.post('/api/flight-vehicle', json={
            'source': 'results', 'motor_type': 'hybrid',
            'results': {'motor': {'thrust': 1000.0, 'burn_time': 10.0}}})
        assert r.status_code == 200
        arac = (r.get_json() or {}).get('vehicle') or r.get_json()
        assert arac['motor_name'] == 'Hybrid Motor'

    def test_dize_olmayan_ad_sessizce_dusurulmez(self):
        """FAIL-CLOSED: çözülemeyen alan reddedilir, sessizce atılmaz."""
        from hrma.app import app
        app.config['TESTING'] = True
        istemci = app.test_client()
        r = istemci.post('/api/flight-vehicle', json={
            'source': 'results', 'motor_type': 'hybrid', 'motor_name': 12345,
            'results': {'motor': {'thrust': 1000.0, 'burn_time': 10.0}}})
        assert r.status_code == 400, r.status_code
        govde_json = r.get_json() or {}
        assert govde_json.get('field') == 'motor_name'


# =========================================================================
# P12aB4-11 — yıkıcı onayın adı
# =========================================================================
class TestP12aB411YikiciOnay:

    def test_kaydedilmemis_degisikligi_atan_onay_adlandirilir(self):
        pb = oku('hrma/static/js/project_bar.js')
        notr = []
        for m in re.finditer(r'confirmModal\(([\s\S]{0,600}?)\);', pb):
            blok = m.group(1)
            if 'unsavedWarn' not in blok:
                continue
            etiketler = re.findall(r"T\('([a-zA-Z0-9_.]+)'", blok)
            assert etiketler, 'onay düğmesi etiketi okunamadı'
            if etiketler[-1] in ('common.ok',):
                notr.append(etiketler[-1])
        assert not notr, (
            f'yıkıcı onay hâlâ nötr etiketli: {notr}')
        assert "proj.btnDiscard" in pb

    def test_btnDiscard_iki_dilde_tanimli(self):
        s = oku('hrma/static/js/i18n_shell.js')
        assert s.count("'proj.btnDiscard'") == 2


# =========================================================================
# P12aB4-13 — --hd-yellow
# =========================================================================
class TestP12aB413TanimsizDegisken:

    def test_bolgede_tanimsiz_hd_degiskeni_kullanilmaz(self):
        css = ''
        css_dizin = os.path.join(KOK, 'hrma', 'static', 'css')
        for d in sorted(os.listdir(css_dizin)):
            if d.endswith('.css'):
                css += oku('hrma/static/css/' + d)
        tanimli = set(re.findall(r'(--hd-[a-z0-9-]+)\s*:', css))
        eksik = {}
        # ÖH D26 (Fable-D20 ŞART) — hüküm-2 bu kalemi İKİ dosyaya
        # genişletmişti ama bekçi yalnız altı dosyayı tarıyordu:
        # sixdof_panel.js:65/68 (`--hd-yellow`, `--hd-blue`; ikisi de hiçbir
        # CSS'te tanımsız) listenin dışında kalıyordu. Ölçüm önce/sonra:
        # docs/scofield/raw/OH/D26/electron/a1/{once,sonra}.json.
        for rel in ('hrma/static/js/step_import_ui.js',
                    'hrma/static/js/project_bar.js',
                    'hrma/static/js/settings_panel.js',
                    'hrma/static/js/update_check.js',
                    'hrma/static/js/flight_handoff.js',
                    'hrma/static/js/chart_captions.js',
                    'hrma/static/js/sixdof_panel.js'):
            for ad in set(re.findall(r'var\((--hd-[a-z0-9-]+)', oku(rel))):
                if ad not in tanimli:
                    eksik.setdefault(rel, []).append(ad)
        assert not eksik, f'CSS\'te tanımlı olmayan değişkenler: {eksik}'

    def test_orta_guven_rozeti_temanin_kehribarini_kullanir(self):
        si = oku('hrma/static/js/step_import_ui.js')
        blok = govde(si, 'var CONF_COLORS =')
        assert '--hd-amber' in blok, 'orta güven rengi tema paletinin dışında'
        assert '--hd-yellow' not in blok


# =========================================================================
# P12aB4-15 — sunucu metni köprüsü
# =========================================================================
class TestP12aB415SunucuMetni:

    # ÖH D26 (Fable-D20 ŞART) — ESKİ ölçüt bir KÖR NOKTA taşıyordu:
    #   GOSTERIM_RE = (TF\(|errorHtml\(|textContent\s*=) … (err.message|…)
    # ARA DEĞİŞKENLİ akışı görmüyordu — step_import_ui.js:230
    #   `var msg = srv((data && data.error) || ('HTTP ' + resp.status));`
    # → 231 `errorHtml(TF('stepimp.failed', {message: msg}))` bir sunucu
    # metni gösterim noktasıdır; Fable ters mutasyonla 230'daki srv()'yi
    # söktü, test YEŞİL kaldı (kusuru görmeyen bekçi). Aynı regex'ten gelen
    # "4 gösterim noktası" sayımı da yanlıştı; gerçek sayı 5.
    #
    # YENİ ölçüt SATIR BAZLI: sunucu metni okuyan HER satır, metin
    # GÖSTERMEYEN sınıflardan biri değilse `srv(` içermek ZORUNDA.
    SUNUCU_RE = re.compile(r'data\.error|err\.message|e\.message|resp\.status')
    #: Metin GÖSTERMEYEN satır sınıfları. ŞART üçünü adlandırır
    #: (throw / console / err.status); ölçüm (D26/electron/a1/once.json)
    #: 'beklenen 5 nokta' için iki sınıfın daha gerektiğini gösterdi ve
    #: ikisi de ekrana bir şey yazmaz:
    #:   new Error( → hata KURULUMU; metin ileride err.message gösterim
    #:                noktasında köprülenir (project_bar.js:478)
    #:   saf koşul  → dallanma testi (step_import_ui.js:222, 229)
    HARIC_RE = re.compile(r'\bthrow\b|\bconsole\s*\.|\berr\.status\b'
                          r'|\bnew\s+Error\s*\(')
    SAF_KOSUL_RE = re.compile(r'^\s*(\}\s*)?(else\s+)?if\s*\(')
    ATAMA_RE = re.compile(r'(?<![=!<>+\-*/%&|^])=(?!=)')
    KOPRU_DOSYALARI = ('hrma/static/js/project_bar.js',
             'hrma/static/js/step_import_ui.js')

    @classmethod
    def gosterim_noktalari(cls):
        """(dosya, satır no, satır) — sunucu metnini EKRANA taşıyan satırlar."""
        noktalar = []
        for rel in cls.KOPRU_DOSYALARI:
            for no, satir in enumerate(oku(rel).splitlines(), 1):
                if not cls.SUNUCU_RE.search(satir):
                    continue
                if cls.HARIC_RE.search(satir):
                    continue
                if (cls.SAF_KOSUL_RE.match(satir)
                        and not cls.ATAMA_RE.search(satir)):
                    continue
                noktalar.append((rel, no, satir.strip()))
        return noktalar

    def test_sunucu_metnini_basan_her_nokta_koprulu(self):
        koprusuz = [(rel, no, satir[:70])
                    for rel, no, satir in self.gosterim_noktalari()
                    if 'srv(' not in satir]
        assert not koprusuz, (
            f'I18N.serverText köprüsünden geçmeyen gösterim noktaları: '
            f'{koprusuz}')

    def test_ara_degiskenli_gosterim_de_sayiliyor(self):
        """Kör nokta kilidi: ölçüt 230'daki ara değişkenli akışı GÖRMELİ."""
        noktalar = self.gosterim_noktalari()
        assert len(noktalar) >= 5, (
            f'gösterim noktası sayımı 5\'in altına düştü ({len(noktalar)}): '
            f'ölçüt daralmış olabilir — {[(r, n) for r, n, _ in noktalar]}')
        ara = [(rel, no) for rel, no, satir in noktalar
               if rel.endswith('step_import_ui.js') and 'var msg' in satir]
        assert ara, (
            'ara değişkenli gösterim (step_import_ui.js `var msg = srv(...)`) '
            'ölçütün dışında kaldı — D20 kör noktası geri geldi')

    def test_olculen_dort_mesaj_TR_karsiligi_var(self):
        h = node_harness('harness_servertext.js')
        cevrilmeyen = [x['mesaj'] for x in h['detay'] if not x['cevrildi']]
        assert not cevrilmeyen, f'TR karşılığı yok: {cevrilmeyen}'


# =========================================================================
# P12aB4-16 — ayrılmış Windows adları
# =========================================================================
class TestP12aB416AyrilmisAdlar:

    def test_istemci_aynasi_sunucu_listesiyle_birebir(self):
        """Ayna eksiksiz: iki liste her koşumda karşılaştırılır."""
        from hrma.utils.projects import _WINDOWS_RESERVED
        pb = oku('hrma/static/js/project_bar.js')
        m = re.search(r'var WINDOWS_RESERVED = \[([\s\S]*?)\];', pb)
        assert m, 'istemci ayrılmış-ad listesi bulunamadı'
        istemci = set(re.findall(r"'([A-Z0-9]+)'", m.group(1)))
        assert istemci == set(_WINDOWS_RESERVED), (
            'istemci aynası sunucu listesinden ayrışmış: '
            f'eksik={sorted(set(_WINDOWS_RESERVED) - istemci)} '
            f'fazla={sorted(istemci - set(_WINDOWS_RESERVED))}')

    def test_ayrilmis_adlarin_hicbiri_istemciden_gecmez(self):
        h = node_harness('harness_adkurali.js')
        assert h['istemciden_gecen_ayrilmis'] == 0, (
            f"{h['istemciden_gecen_ayrilmis']} ayrılmış ad istemciden geçiyor: "
            f"{h['gecen_ornek']}")
        assert h['istemciden_gecen_ayrilmis_kucuk_harf'] == 0, (
            'sunucu stem.upper() ile denetliyor; ayna küçük harfe kör')

    def test_mesru_adlar_reddedilmez(self):
        """Aşırı-red yok: ayrılmış ADI İÇEREN meşru adlar geçmeye devam eder."""
        h = node_harness('harness_adkurali.js')
        assert h['mesru_gecen'] == h['mesru_ad_sayisi'], (
            f"meşru adlar reddediliyor: {h['mesru_reddedilen']}")

    def test_red_gerekcesi_adlandirilir(self):
        pb = oku('hrma/static/js/project_bar.js')
        assert 'proj.nameReserved' in pb, (
            'ayrılmış ad reddi genel "kurala bakın" uyarısına düşüyor')
        s = oku('hrma/static/js/i18n_shell.js')
        assert s.count("'proj.nameReserved'") == 2
