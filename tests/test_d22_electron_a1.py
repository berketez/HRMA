"""ÖH Dalga-22 / electron a1 bekçileri.

Kapsam (parti P12a + OH devirleri):
  · OH-D18-10  uçuş irtifası DATUM sözleşmesi (6-DOF serisi ↔ küre çizimi
               ↔ okuma satırı)
  · P12aB5-11  ölü CSS seçicileri + `.hd-led` kaskad kusuru (fail-open LED)
  · P12aB5-12  ayarlar penceresi durum satırları dil değişiminde tazelenir
  · P12aB5-14  imsiz iki dilli sürüm notunda dil ayrımının çökmemesi
  · P12aB5-15  `user_guide.js` menü beyanının GERÇEK olması
  · P12aB4-24  motor adı önerisi + proje açıklaması üç sayfada da çalışır

Her bekçi ters-mutasyonla kırmızıya çevrilebilecek biçimde YAZILMIŞTIR
(kanıt: docs/scofield/raw/OH/D22/electron/a1/mutasyon.json).
"""
import json
import pathlib
import re
import shutil
import subprocess

import pytest
from tests.support.kanit import kanit_gerekli

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
CSS = KOK / 'hrma' / 'static' / 'css'
KANIT = KOK / 'docs' / 'scofield' / 'raw' / 'OH' / 'D22' / 'electron' / 'a1'


def oku(rel):
    return (KOK / rel).read_text(encoding='utf-8')


def js_yorumsuz(src):
    """JS yorumlarını söker — bekçi BEYANI değil KODU ölçsün."""
    src = re.sub(r'/\*.*?\*/', ' ', src, flags=re.S)
    return re.sub(r'(?m)^\s*//.*$', ' ', src)


# ---------------------------------------------------------------------------
# OH-D18-10 — uçuş irtifası datum sözleşmesi
# ---------------------------------------------------------------------------
class TestUcusIrtifasiDatumu:
    """Küre yüzeyi deniz seviyesidir; 6-DOF irtifası SAHA ÜSTÜdür.

    İki datum tek sözcükle ("İrtifa"/"Apoje") gösterilince 1500 m'lik bir
    sahada 1500 m'lik sahte bir fark doğuyordu. Sözleşme üç ayakta da adıyla
    duracak: üretici yayımlayacak, çizim OKUYACAK, okuma satırı çözücüyle
    AYNI datumda basacak.
    """

    def test_cozucu_seri_datumunu_adiyla_yayimlar(self):
        src = oku('hrma/analysis/six_dof_trajectory.py')
        assert "'altitude_datum': 'above_launch_site'" in src, (
            "six_dof_trajectory.py `altitude` dizisinin datumunu adıyla "
            "yayımlamıyor — tüketici datumu VARSAYMAK zorunda kalır")
        # Apoje ve seri AYNI sözcüğü kullanmalı (iki sözlük = iki gerçek)
        apoje = re.search(r"'apogee_datum':\s*'([a-z_]+)'", src)
        seri = re.search(r"'altitude_datum':\s*'([a-z_]+)'", src)
        assert apoje and seri and apoje.group(1) == seri.group(1), (
            'apogee_datum ile altitude_datum aynı datum sözcüğünü '
            'kullanmıyor: %s / %s' % (apoje, seri))

    def test_kure_datumu_okur_ve_taninmayani_reddeder(self):
        src = js_yorumsuz(oku('hrma/static/js/launch_site_globe.js'))
        assert 'series.altitude_datum' in src, (
            'setFlightPath dizi datumunu OKUMUYOR (varsayım sürüyor)')
        assert re.search(r"ALT_DATUM_BILINEN\.indexOf\(datum\)\s*<\s*0", src), (
            'tanınmayan datum FAIL-CLOSED reddedilmiyor')
        assert "_onError('flight_altitude_datum_unknown')" in src, (
            'tanınmayan datumda hata kancası ateşlenmiyor — kusur sessiz')

    def test_kure_msl_dizisini_iki_kez_saymaz(self):
        src = js_yorumsuz(oku('hrma/static/js/launch_site_globe.js'))
        assert re.search(
            r"datum === ALT_DATUM_MSL\)\s*\?\s*\(series\.altitude\[i\] - h0\)",
            src), ('deniz seviyesi bildiren dizi h0 kadar indirgenmiyor — '
                   'saha rakımı İKİ KEZ sayılır')

    def test_okuma_bloklari_saha_ustu_datumda(self):
        src = js_yorumsuz(oku('hrma/static/js/launch_site_globe.js'))
        assert 'altAgl: f.alt[i] - f.h0' in src, (
            '_emitTime saha üstü irtifayı yayımlamıyor')
        assert 'apogeeAgl: f.apogee - f.h0' in src, (
            '_emitTime saha üstü apojeyi yayımlamıyor')
        html = oku('hrma/templates/launch_site.html')
        assert 's.altAgl != null ? s.altAgl : s.alt' in html, (
            'okuma satırı hâlâ deniz seviyesi irtifasını basıyor')
        assert 's.apogeeAgl != null ? s.apogeeAgl : s.apogee' in html, (
            'apoje satırı çözücüden farklı datumda')
        assert "site.altDatumTip" in html, (
            'deniz seviyesi karşılığı ekrandan tamamen kayboldu')

    def test_datum_ipucu_iki_dilde_tanimli(self):
        src = oku('hrma/static/js/i18n_launch_site.js')
        assert src.count("'site.altDatumTip'") == 2, (
            'site.altDatumTip iki dilde tanımlı değil')


# ---------------------------------------------------------------------------
# P12aB5-11 — ölü CSS + LED kaskadı
# ---------------------------------------------------------------------------
#: Sökülen adlar: üründe (şablon + JS + Python) HİÇ geçmiyorlardı.
OLU_SINIFLAR = [
    'hd-frame', 'hd-reveal', 'hd-sweepline', 'hd-report-head',
    'hd-report-eyebrow', 'hd-report-meta', 'hd-report-title',
    'hd-report-strip', 'hd-metric-foot', 'hd-delta', 'hd-spark',
    'risk-level-critical', 'risk-level-high', 'risk-level-medium',
    'risk-level-low', 'safety-metric', 'safety-tabs', 'safety-tab',
    'safety-tab-content', 'viz-fallback-note', 'spec-panel',
    'materials-list',
]


def _tanimli_siniflar(dosya):
    metin = (CSS / dosya).read_text(encoding='utf-8')
    govde = re.sub(r'/\*.*?\*/', ' ', metin, flags=re.S)
    sec = ' '.join(re.findall(r'([^{}]*)\{', govde))
    return set(re.findall(r'\.(-?[A-Za-z_][\w-]*)', sec))


class TestOluCssSokuldu:

    def test_olu_siniflar_geri_gelmedi(self):
        tanimli = set()
        for d in ('theme.css', 'results_hud.css', 'hd_doc.css'):
            tanimli |= _tanimli_siniflar(d)
        geri = sorted(s for s in OLU_SINIFLAR if s in tanimli)
        assert not geri, (
            'üründe hiç çizilmeyen CSS sınıfları geri geldi: %s' % geri)

    def test_led_kaskadi_kapsayicidan_akar(self):
        """`.hd-led { --led: … }` kapsayıcının durum rengini GÖLGELİYORDU.

        Özel özellik en yakın tanımdan okunur; LED'in kendi kuralında
        tanımlanan `--led`, `[data-state="unsafe"]`in kırmızısını yener ve
        LED durum ne olursa olsun YEŞİL kalır (fail-open).
        """
        css = re.sub(r'/\*.*?\*/', ' ',
                     (CSS / 'results_hud.css').read_text(encoding='utf-8'),
                     flags=re.S)
        blok = re.search(r'\.hd-led\s*\{([^}]*)\}', css)
        assert blok, '.hd-led kuralı kayboldu'
        assert '--led' not in blok.group(1).split('background')[0], (
            '.hd-led kendi üstünde --led tanımlıyor — durum rengi gölgelenir')
        assert 'var(--led, var(--hd-green))' in blok.group(1), (
            'LED yedeği var() içinde değil; durum verilmemişse renk çöker')

    def test_canli_api_bicimi_silinmedi(self):
        """`HRMAHud.termLog` yayımlanmış API; biçimi ölü sayılıp silinemez."""
        assert 'termLog: termLog' in oku('hrma/static/js/hud.js')
        tanimli = _tanimli_siniflar('results_hud.css')
        assert 'hd-termlog' in tanimli, 'canlı API biçim sözleşmesi silinmiş'
        assert 'hd-statustag' in tanimli, (
            'durum sözcüğü pili silinmiş — --state-ink zincirinin tek '
            'tüketicisiydi (tests/test_d21_electron_a1.py ona bağlı)')


# ---------------------------------------------------------------------------
# P12aB5-12 — ayarlar durum satırları dil değişiminde tazelenir
# ---------------------------------------------------------------------------
DURUM_DUGUMLERI = ('checkStatus', 'skipStatus', 'formStatus', 'counter',
                   'sendStatus')


class TestAyarlarDurumSatirlariCevrilir:

    def test_durum_metni_dogrudan_basilmiyor(self):
        src = js_yorumsuz(oku('hrma/static/js/settings_panel.js'))
        kacak = re.findall(
            r'(%s)\.textContent\s*=' % '|'.join(DURUM_DUGUMLERI), src)
        assert not kacak, (
            'durum düğümüne i18n bağı OLMADAN metin basılıyor: %s' % kacak)

    def test_setStatus_anahtari_dugume_yaziyor(self):
        src = js_yorumsuz(oku('hrma/static/js/settings_panel.js'))
        govde = re.search(r'function setStatus\(node, key, params, fallback\)'
                          r'\s*\{(.*?)\n    \}', src, re.S)
        assert govde, 'setStatus yardımcısı yok'
        g = govde.group(1)
        assert "setAttribute('data-i18n', key)" in g, (
            'anahtar düğüme yazılmıyor — I18N.apply tazeleyemez')
        assert "setAttribute('data-i18n-params'" in g, (
            'parametreler düğümde durmuyor — TF şablonu ham kalır')
        assert "removeAttribute('data-i18n')" in g, (
            'temizlemede iz kalıyor — boş satır eski anahtarla dolar')

    def test_uyari_pili_de_tazelenir(self):
        src = js_yorumsuz(oku('hrma/static/js/settings_panel.js'))
        govde = re.search(r'function warnChip\(w\)\s*\{(.*?)\n    \}', src,
                          re.S)
        assert govde and "setAttribute('data-i18n', code)" in govde.group(1), (
            'uyarı pili dil değişiminde eski dilde kalıyor')


# ---------------------------------------------------------------------------
# P12aB5-14 — imsiz iki dilli notta dil ayrımı
# ---------------------------------------------------------------------------
class TestSurumNotuDilAyrimi:

    def test_sira_kurali_tek_yerde_yazili(self):
        src = js_yorumsuz(oku('hrma/static/js/update_check.js'))
        assert re.search(r"var SECTION_ORDER = \['en', 'tr'\]", src), (
            'yayın sırası kuralı tek tanım olarak yazılmamış')

    def test_yayimlanan_notlar_sira_kuralina_uyuyor(self):
        """Kural uydurulmadı: imli her sürüm dosyasında ölçüldü."""
        dosyalar = sorted((KOK / 'packaging').glob('release_notes_v*.md'))
        olculen = 0
        for p in dosyalar:
            imler = re.findall(r'HRMA-LANG:([a-z]{2})',
                               p.read_text(encoding='utf-8'))
            if not imler:
                continue
            olculen += 1
            assert imler == ['en', 'tr'], (
                '%s yayın sırası kuralına uymuyor: %s' % (p.name, imler))
        assert olculen >= 3, 'ölçülen imli sürüm notu sayısı beklenenden az'

    @pytest.mark.skipif(shutil.which('node') is None,
                        reason='node kurulu değil')
    def test_turkce_harfsiz_tr_bolumu_de_ayrilir(self):
        """Türkçe bölüm Türkçe harf taşımasa da karşı dil SIZMAZ.

        Eski davranış: iki blok da 'en' sınıflanıyor, `sectionsByHeading`
        null dönüyor ve Türkçe kullanıcıya İNGİLİZCE bölüm de gösteriliyordu.
        """
        cikti = subprocess.run(
            [shutil.which('node'), kanit_gerekli(str(KANIT / 'b514_kanit.js')), str(KOK)],
            capture_output=True, text=True, timeout=120)
        assert cikti.returncode == 0, cikti.stderr[-500:]
        d = json.loads(cikti.stdout.strip().splitlines()[-1])
        assert 'hata' not in d, d
        assert d['bolunebildi'], 'gövde iki dile hiç ayrılamadı'
        assert not d['tr_ingilizce_sizdi'], (
            'Türkçe kullanıcıya İngilizce bölüm de gösteriliyor')
        assert not d['en_turkce_sizdi'], (
            'İngilizce kullanıcıya Türkçe bölüm de gösteriliyor')
        assert d['tr_kendi_metnini_aldi'] and d['en_kendi_metnini_aldi'], (
            'bölümler karışmış')


# ---------------------------------------------------------------------------
# P12aB5-15 — kılavuz menü beyanı gerçek olmalı
# ---------------------------------------------------------------------------
class TestKilavuzMenusuGercek:

    def test_launcher_kilavuz_ogesini_tasiyor(self):
        src = oku('packaging/launcher.py')
        assert 'def _menu_user_guide():' in src, (
            'launcher.py kılavuz menü eylemini taşımıyor')
        assert 'window.hrmaOpenUserGuide' in src, (
            'menü eylemi arayüzdeki kılavuz açıcısını çağırmıyor')
        assert src.count('wm.MenuAction("User Guide…", _menu_user_guide)') == 2, (
            'kılavuz ögesi iki platformun Help menüsünde birden yok '
            '(macOS + Windows)')

    def test_beyan_ile_menu_ayni_adi_kullaniyor(self):
        """`user_guide.js` yayımlıyor, `launcher.py` çağırıyor — tek ad."""
        js = oku('hrma/static/js/user_guide.js')
        assert 'window.hrmaOpenUserGuide = openGuide;' in js
        ad = 'hrmaOpenUserGuide'
        assert ad in oku('packaging/launcher.py'), (
            'beyan ile menü farklı ad kullanıyor — güvence yine karşılıksız')


# ---------------------------------------------------------------------------
# P12aB4-24 — ad önerisi + açıklama üç sayfada
# ---------------------------------------------------------------------------
class TestProjeAdiVeAciklamasi:

    def test_ad_onerisi_sayfanin_kendi_kaynagina_dusuyor(self):
        src = js_yorumsuz(oku('hrma/static/js/project_bar.js'))
        assert "SAYFA_AD_KAYNAKLARI = ['_solidMotorName', '_liquidMotorName']" \
            in src, ('ad önerisi katı/sıvı sayfalarının kendi ad kaynağını '
                     'okumuyor — öneri boş kalır')
        assert re.search(r'function pageMotorName\(\)', src)
        assert 'var sayfa = pageMotorName();' in src, (
            'defaultNameSuggestion sayfa kaynağını hiç çağırmıyor')

    def test_ad_kaynaklari_gercekten_var(self):
        """Uydurma kaynak yok: iki işlev de o sayfalarda TANIMLI."""
        assert 'function _solidMotorName()' in oku('hrma/templates/solid.html')
        assert 'function _liquidMotorName()' in oku(
            'hrma/templates/liquid.html')

    def test_aciklama_sayfa_alanindan_bagimsiz_yasiyor(self):
        src = js_yorumsuz(oku('hrma/static/js/project_bar.js'))
        assert 'description:' in src, 'state.description alanı yok'
        assert "? String(descEl.value) : String(state.description || '')" \
            in src, ('buildPayload açıklamayı sayfa alanı yokken hiçbir '
                     'yerden okumuyor — katı/sıvıda açıklama kaydedilemez')
        assert 'if (desc.trim()) payload.description = desc;' in src, (
            'açıklama kayda tek yerden girmiyor')
        assert "state.description = String(doc.description || '')" in src, (
            'açılan projenin açıklaması geri yüklenmiyor — sonraki kayıtta '
            'sessizce silinir')

    def test_kayit_penceresi_alan_yokken_aciklama_soruyor(self):
        src = js_yorumsuz(oku('hrma/static/js/project_bar.js'))
        assert "var sayfaDesc = document.getElementById('motor_description');" \
            in src
        assert 'if (!sayfaDesc) {' in src, (
            'açıklama alanı sayfa alanı olsa da olmasa da çiziliyor — '
            'aynı veri iki yerden istenir')
        assert 'onSubmit(name, descIn ? String(descIn.value) : null);' in src, (
            'pencerede yazılan açıklama çağırana ulaşmıyor')

    def test_aciklama_etiketi_iki_dilde_tanimli(self):
        src = oku('hrma/static/js/i18n_shell.js')
        assert src.count("'proj.descLabel'") == 2, (
            'proj.descLabel iki dilde tanımlı değil')
