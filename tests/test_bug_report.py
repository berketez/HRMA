"""Ayarlar panelindeki "Hata bildir" akışının bekçileri (2026-08-04).

Berke'nin isteği: ayarlarda bir "Hata bildir" tuşu olsun, kullanıcı yazıp
gönderince berketez/HRMA issues'a gitsin.

TASARIM KARARI — GÖMÜLÜ BELİRTEÇ YOK. Dağıtılan ikiliye GitHub belirteci
gömmek onu herkese açık etmek demektir. Bu yüzden HRMA kimsenin adına kayıt
AÇMAZ; form → ZORUNLU önizleme → ön-doldurulmuş issue bağlantısı yeni sekmede
açılır → kullanıcı kendi hesabıyla gönderir.

Burada kilitlenen sözleşmeler:

  1. Gövde derleyici sürüm / işletim sistemi / sayfa alanlarını GERÇEK
     kaynaklardan üretir; okunamayan alanı uydurmaz, "bilinmiyor" + dayanak
     yazar (sahte veri yasağı).
  2. Tanılama onay kutusu KAPALIYKEN konsol günlüğü ve girdi özeti gövdeye
     GİRMEZ. (Testin boş yere geçmediğini kanıtlamak için aynı girdiyle
     tanılama AÇIK hâli de sınanır — kapalıyken yok, açıkken var.)
  3. URL kaçışlaması doğru: başlık ve gövde encodeURIComponent'ten geçer,
     çözüldüğünde BİREBİR geri gelir (&, #, +, satır sonu, Türkçe harfler).
  4. ~8000 karakterlik URL sınırı aşılırsa gövde SONDAN kısaltılır (önce
     tanılama günlüğü gider, kullanıcının kendi metni korunur) ve kısaltma
     beyanı + 'warn.bugreport.body_truncated' kodu eklenir.
  5. Hedef depo TEK YERDE sabittir ve berketez/HRMA'dır.
  6. Önizleme ZORUNLU: openIssue(), markPreviewed() ile işaretlenmemiş bir
     gövdeyi açmaz; kırpma gerektiren gövdeyi de açmadan geri verir
     (gönderilen = görülen).
  7. Kişisel bilgi taşınmaz: ev dizini/kullanıcı adı, e-posta ve dosya yolları
     kayıt ANINDA temizlenir; PII görünümlü alan adları girdi özetine girmez.

Ölçüm yöntemi: bug_report.js GERÇEK node ile, küçük bir DOM/navigator/location
taklidi altında BÜTÜN olarak koşturulur (kalıp: tests/test_blowdown_panel.py
harness'i). Yalnız çalıştırılamayan iddialar (şablon etiketleri, panel
bağlama, i18n ad alanı) kaynak taramasıyla sınanır.
"""

import json
import pathlib
import re
import shutil
import subprocess
import urllib.parse

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
JS_DIR = REPO_ROOT / 'hrma' / 'static' / 'js'
BUG_JS = JS_DIR / 'bug_report.js'
PANEL_JS = JS_DIR / 'settings_panel.js'
TEMPLATE_DIR = REPO_ROOT / 'hrma' / 'templates'

NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node kurulu değil')

# Ayarlar panelini yükleyen (yani "Hata bildir" bölümünü gösterebilecek) sayfalar
PAGES_WITH_SETTINGS = ['index.html', 'advanced.html', 'solid.html',
                       'liquid.html', 'formulas.html', 'launch_site.html']


# ---------------------------------------------------------------------------
# node koşum ortamı
# ---------------------------------------------------------------------------
HARNESS = r"""
'use strict';
const fs = require('fs');
const spec = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const modulePath = process.argv[3];

global.window = global;

// ---- location / navigator ----
// node 21+ kendi `navigator` küreselini yalnız-okunur tanımlıyor; taklidi
// defineProperty ile üstüne yazıyoruz.
function setGlobal(name, value) {
    Object.defineProperty(global, name, {
        value: value, writable: true, configurable: true, enumerable: true });
}
setGlobal('location', { pathname: spec.pathname || '/' });
setGlobal('navigator', { userAgent: spec.userAgent === undefined
                                    ? '' : spec.userAgent });

// ---- küçük DOM: yalnız gereken iki sorgu ----
function makeInput(desc) {
    return { id: desc.id || '', name: desc.name || '',
             type: desc.type || 'number',
             value: desc.value === undefined ? '' : String(desc.value) };
}
const inputs = (spec.inputs || []).map(makeInput);
const footer = spec.footerText === undefined
    ? null : { textContent: String(spec.footerText) };

global.document = {
    querySelector(sel) {
        if (sel === '.footer') return footer;
        return null;
    },
    querySelectorAll(sel) {
        if (sel === 'input') return inputs;
        return [];
    },
};

// ---- olay dinleyicileri ----
const listeners = {};
global.addEventListener = function (name, fn) {
    (listeners[name] = listeners[name] || []).push(fn);
};

// ---- window.open taklidi ----
const opened = [];
global.open = function (url, target, features) {
    opened.push({ url: url, target: target, features: features });
    return spec.openBlocked ? null : { closed: false };
};

// ---- sayfa küresel değişkenleri (sürüm yayımlama biçimleri) ----
Object.keys(spec.globals || {}).forEach(k => { global[k] = spec.globals[k]; });
if (spec.lang) global.I18N = { lang: spec.lang };

require(modulePath);
const BR = window.HRMABugReport;

// ---- konsol hatası üretimi: gerçek yollardan ----
(spec.consoleErrors || []).forEach(msg => { console.error(msg); });
(spec.windowErrors || []).forEach(ev => {
    (listeners['error'] || []).forEach(fn => fn(ev));
});
(spec.rejections || []).forEach(r => {
    (listeners['unhandledrejection'] || []).forEach(fn => fn({ reason: r }));
});

const env = BR.collectEnvironment();
const inputSummary = BR.collectInputSummary();
const body = (spec.bodyOverride !== undefined && spec.bodyOverride !== null)
    ? spec.bodyOverride
    : BR.buildBody(spec.fields || {}, { diagnostics: !!spec.diagnostics });
const built = BR.buildIssueUrl(spec.title || '', body);

let openResult = null;
if (spec.doOpen) {
    if (spec.markPreviewed) BR.markPreviewed(built.title, built.body);
    openResult = BR.openIssue(built.title, built.body);
}
let openWithoutPreview = null;
if (spec.doOpenWithoutPreview) {
    BR.resetPreview();
    openWithoutPreview = BR.openIssue(spec.title || '', body);
}

process.stdout.write(JSON.stringify({
    env: env,
    inputSummary: inputSummary,
    capturedErrors: BR.consoleErrors(),
    body: body,
    built: built,
    openResult: openResult,
    openWithoutPreview: openWithoutPreview,
    opened: opened,
    listeners: Object.keys(listeners),
    redact: (spec.redactSamples || []).map(s => BR.redact(s)),
    constants: { repo: BR.REPO, issueUrl: BR.ISSUE_NEW_URL,
                 maxUrl: BR.MAX_URL_CHARS, maxTitle: BR.MAX_TITLE_CHARS,
                 maxConsole: BR.MAX_CONSOLE_ENTRIES },
}));
"""


def _run(spec, tmp_path):
    """bug_report.js'i node altında BÜTÜN olarak koşturur."""
    script = tmp_path / 'kos.js'
    script.write_text(HARNESS, encoding='utf-8')
    data = tmp_path / 'girdi.json'
    data.write_text(json.dumps(spec), encoding='utf-8')
    proc = subprocess.run([NODE, str(script), str(data), str(BUG_JS)],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, 'bug_report.js node altında çöktü:\n' + proc.stderr
    return json.loads(proc.stdout)


def _base_spec(**over):
    spec = {
        'pathname': '/hybrid',
        'userAgent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/126.0.0.0 Safari/537.36'),
        'globals': {'HRMA_APP_VERSION': '2.6.27'},
        'lang': 'tr',
        'title': 'Hibrit analizde itki eğrisi çizilmiyor',
        'fields': {'what': 'Analiz bitti ama itki grafiği boş kaldı.',
                   'expected': 'İtki eğrisinin çizilmesini bekliyordum.',
                   'steps': '1. Hibrit sayfası\n2. Analiz Et'},
        'diagnostics': False,
    }
    spec.update(over)
    return spec


def _decode_url(url):
    """Ön-doldurulmuş issue bağlantısından başlık ve gövdeyi geri çözer."""
    parsed = urllib.parse.urlsplit(url)
    pairs = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    return parsed, pairs


# ===========================================================================
# 1. Gövde derleyici: sürüm / işletim sistemi / sayfa
# ===========================================================================
@needs_node
class TestGovdeOrtamAlanlari:

    def test_surum_isletim_sistemi_ve_sayfa_govdeye_giriyor(self, tmp_path):
        out = _run(_base_spec(), tmp_path)
        body = out['body']
        assert 'v2.6.27' in body, 'sürüm gövdede yok'
        assert 'macOS' in body, 'işletim sistemi gövdede yok'
        assert '/hybrid' in body, 'sayfa yolu gövdede yok'
        assert 'hybrid' in body

    def test_ortam_alanlari_dayanak_beyan_ediyor(self, tmp_path):
        out = _run(_base_spec(), tmp_path)
        env = out['env']
        for alan in ('version', 'os', 'browser', 'page', 'ui_lang'):
            assert env[alan + '_basis'], alan + ' için dayanak yok'
        assert env['version_basis'] == 'window.HRMA_APP_VERSION'
        assert env['os_basis'] == 'navigator.userAgent'
        assert env['page_basis'] == 'location.pathname'
        # Dayanak metinleri gövdeye de basılır (okuyan kişi kaynağı görsün)
        assert 'window.HRMA_APP_VERSION' in out['body']
        assert 'location.pathname' in out['body']

    def test_kullanici_metni_govdeye_birebir_giriyor(self, tmp_path):
        spec = _base_spec(fields={'what': 'ITKI-BOS-KALDI',
                                  'expected': 'EGRI-CIZILSIN',
                                  'steps': 'ADIM-BIR'})
        out = _run(spec, tmp_path)
        for parca in ('ITKI-BOS-KALDI', 'EGRI-CIZILSIN', 'ADIM-BIR'):
            assert parca in out['body']

    def test_bos_alan_uydurulmuyor_doldurulmadi_yaziliyor(self, tmp_path):
        spec = _base_spec(fields={'what': 'X', 'expected': '', 'steps': '   '})
        out = _run(spec, tmp_path)
        # İki boş alan için iki "doldurulmadı" beyanı
        assert out['body'].count('not filled in') == 2

    @pytest.mark.parametrize('ua,beklenen', [
        ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
         '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36', 'Windows NT 10.0'),
        ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 '
         '(KHTML, like Gecko) Version/17.4 Safari/605.1.15', 'macOS 10.15.7'),
        ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
         '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36', 'Linux'),
    ])
    def test_isletim_sistemi_useragent_ten_cikariliyor(self, ua, beklenen,
                                                       tmp_path):
        out = _run(_base_spec(userAgent=ua), tmp_path)
        assert out['env']['os'] == beklenen

    def test_ham_useragent_de_govdede_kaliyor(self, tmp_path):
        """Türetilen etiket yanılabilir; ham UA da taşınır (dayanak)."""
        out = _run(_base_spec(), tmp_path)
        assert 'Chrome/126.0.0.0' in out['body']


# ===========================================================================
# 2. Sürüm okunamıyorsa uydurulmuyor (sahte veri yasağı)
# ===========================================================================
@needs_node
class TestSurumDurustlugu:

    def test_surum_yoksa_bilinmiyor_ve_dayanak_yaziliyor(self, tmp_path):
        out = _run(_base_spec(globals={}), tmp_path)
        assert out['env']['version'] is None, 'sürüm uydurulmuş'
        assert 'unknown' in out['body']
        assert 'does not expose the version' in out['body']
        # Uydurma bir sürüm numarası kaçmasın
        assert not re.search(r'HRMA: v\d', out['body'])

    def test_eski_kuresel_ad_da_okunuyor(self, tmp_path):
        """advanced.html sürümü window.HRMA_VERSION olarak yayımlıyor."""
        out = _run(_base_spec(globals={'HRMA_VERSION': '2.6.27'}), tmp_path)
        assert out['env']['version'] == '2.6.27'
        assert out['env']['version_basis'] == 'window.HRMA_VERSION'

    def test_altbilgi_yedegi_calisiyor(self, tmp_path):
        """formulas.html sürümü yalnız altbilgi metninde taşıyor."""
        out = _run(_base_spec(globals={},
                              footerText='UZAYTEK Motor Analysis v2.6.27 | ...'),
                   tmp_path)
        assert out['env']['version'] == '2.6.27'
        assert out['env']['version_basis'] == '.footer'

    def test_useragent_bossa_isletim_sistemi_uydurulmuyor(self, tmp_path):
        out = _run(_base_spec(userAgent=''), tmp_path)
        assert out['env']['os'] is None
        assert out['env']['browser'] is None
        assert 'unknown' in out['body']


# ===========================================================================
# 3. Tanılama kapalıyken konsol/girdi özeti gövdeye GİRMEZ
# ===========================================================================
@needs_node
class TestTanilamaKapisi:

    KONSOL_IZI = 'KONSOL-IZI-9137'
    GIRDI_ADI = 'chamber_pressure_bar'
    GIRDI_DEGERI = 41.7

    def _spec(self, diagnostics):
        return _base_spec(
            diagnostics=diagnostics,
            consoleErrors=[self.KONSOL_IZI + ' patladi'],
            inputs=[{'id': self.GIRDI_ADI, 'value': self.GIRDI_DEGERI},
                    {'id': 'throat_diameter', 'value': 12.5}])

    def test_kapaliyken_konsol_ve_girdi_govdede_yok(self, tmp_path):
        out = _run(self._spec(False), tmp_path)
        body = out['body']
        assert self.KONSOL_IZI not in body, 'konsol hatası kapalıyken sızdı'
        assert self.GIRDI_ADI not in body, 'girdi adı kapalıyken sızdı'
        assert str(self.GIRDI_DEGERI) not in body, 'girdi değeri kapalıyken sızdı'
        assert 'was not attached' in body, 'eklenmediği beyan edilmemiş'

    def test_aciksa_konsol_ve_girdi_govdede_var(self, tmp_path):
        """Yukarıdaki olumsuz testin boş yere geçmediğinin kanıtı."""
        out = _run(self._spec(True), tmp_path)
        body = out['body']
        assert self.KONSOL_IZI in body
        assert self.GIRDI_ADI in body
        assert str(self.GIRDI_DEGERI) in body

    def test_kapali_govde_acik_govdeden_kisa(self, tmp_path):
        kapali = _run(self._spec(False), tmp_path)['body']
        acik = _run(self._spec(True), tmp_path)['body']
        assert len(kapali) < len(acik)

    def test_konsol_hatasi_yoksa_yok_diye_beyan_ediliyor(self, tmp_path):
        out = _run(_base_spec(diagnostics=True, consoleErrors=[]), tmp_path)
        assert 'No console error was captured' in out['body']

    def test_sayisal_girdi_yoksa_yok_diye_beyan_ediliyor(self, tmp_path):
        out = _run(_base_spec(diagnostics=True, inputs=[]), tmp_path)
        assert 'No numeric input was found' in out['body']


# ===========================================================================
# 4. Girdi özeti yalnız SAYISAL alanları taşır, kişisel bilgi taşımaz
# ===========================================================================
@needs_node
class TestGirdiOzetiMahremiyeti:

    def test_sayisal_olmayan_alanlar_elenir(self, tmp_path):
        out = _run(_base_spec(diagnostics=True, inputs=[
            {'id': 'chamber_pressure', 'value': 20},
            {'id': 'propellant_label', 'type': 'text', 'value': 'HTPB-KARISIM'},
        ]), tmp_path)
        idler = [f['id'] for f in out['inputSummary']['fields']]
        assert idler == ['chamber_pressure']
        assert 'HTPB-KARISIM' not in out['body']

    @pytest.mark.parametrize('alan', [
        'project_name', 'output_path', 'user_email', 'api_token',
        'file_name', 'author_note', 'secret_key', 'home_folder',
    ])
    def test_kisisel_gorunumlu_alan_adlari_hic_okunmaz(self, alan, tmp_path):
        out = _run(_base_spec(diagnostics=True, inputs=[
            {'id': alan, 'value': 42},
            {'id': 'chamber_pressure', 'value': 20},
        ]), tmp_path)
        idler = [f['id'] for f in out['inputSummary']['fields']]
        assert alan not in idler, alan + ' girdi özetine sızdı'
        assert alan not in out['body']

    def test_parola_ve_dosya_alanlari_okunmaz(self, tmp_path):
        out = _run(_base_spec(diagnostics=True, inputs=[
            {'id': 'gizli', 'type': 'password', 'value': 12345},
            {'id': 'yukleme', 'type': 'file', 'value': 999},
            {'id': 'chamber_pressure', 'value': 20},
        ]), tmp_path)
        idler = [f['id'] for f in out['inputSummary']['fields']]
        assert idler == ['chamber_pressure']

    def test_girdi_ozeti_dayanak_beyan_eder(self, tmp_path):
        out = _run(_base_spec(diagnostics=True,
                              inputs=[{'id': 'chamber_pressure', 'value': 20}]),
                   tmp_path)
        assert out['inputSummary']['basis']


# ===========================================================================
# 5. Kişisel bilgi temizliği (redaction)
# ===========================================================================
@needs_node
class TestTemizleme:

    @pytest.mark.parametrize('ham,olmamali', [
        ('at /Users/berke/HRMA/app.js:12', 'berke'),
        (r'C:\Users\berke\AppData\Local\HRMA\x.js', 'berke'),
        ('/home/berke/hrma/run.py', 'berke'),
        ('mail: btezgocen97@gmail.com', 'btezgocen97@gmail.com'),
    ])
    def test_ev_dizini_ve_eposta_siliniyor(self, ham, olmamali, tmp_path):
        out = _run(_base_spec(redactSamples=[ham]), tmp_path)
        assert olmamali not in out['redact'][0], out['redact'][0]

    def test_temizleme_kayit_aninda_yapiliyor(self, tmp_path):
        """Temizlenmemiş metin belleğe HİÇ girmemeli."""
        out = _run(_base_spec(
            consoleErrors=['TypeError at /Users/berke/HRMA/x.js:9']), tmp_path)
        kayitli = ' '.join(e['text'] for e in out['capturedErrors'])
        assert 'berke' not in kayitli
        assert '<kullanici>' in kayitli

    def test_uzun_belirtec_gorunumlu_diziler_gizleniyor(self, tmp_path):
        jeton = 'ghp_' + 'A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8'
        out = _run(_base_spec(redactSamples=[jeton]), tmp_path)
        assert jeton not in out['redact'][0]
        assert '<gizlendi>' in out['redact'][0]

    def test_useragent_de_temizlikten_geciyor(self, tmp_path):
        out = _run(_base_spec(userAgent='HRMA/1.0 (/Users/berke/App)'),
                   tmp_path)
        assert 'berke' not in out['env']['user_agent']


# ===========================================================================
# 6. Konsol yakalayıcı
# ===========================================================================
@needs_node
class TestKonsolYakalayici:

    def test_console_error_yakalaniyor(self, tmp_path):
        out = _run(_base_spec(consoleErrors=['ILK-HATA', 'IKINCI-HATA']),
                   tmp_path)
        metin = ' '.join(e['text'] for e in out['capturedErrors'])
        assert 'ILK-HATA' in metin and 'IKINCI-HATA' in metin

    def test_pencere_hatasi_ve_soz_reddi_yakalaniyor(self, tmp_path):
        out = _run(_base_spec(
            windowErrors=[{'message': 'PENCERE-HATASI', 'filename': 'a.js',
                           'lineno': 4}],
            rejections=['SOZ-REDDI']), tmp_path)
        metin = ' '.join(e['text'] for e in out['capturedErrors'])
        assert 'PENCERE-HATASI' in metin
        assert 'SOZ-REDDI' in metin
        assert 'error' in out['listeners']
        assert 'unhandledrejection' in out['listeners']

    def test_halka_tampon_ust_sinirda_duruyor(self, tmp_path):
        n = 60
        out = _run(_base_spec(consoleErrors=['HATA-%02d' % i
                                             for i in range(n)]), tmp_path)
        sinir = out['constants']['maxConsole']
        assert len(out['capturedErrors']) == sinir
        # En yenileri tutulur, en eskiler düşer
        metin = ' '.join(e['text'] for e in out['capturedErrors'])
        assert 'HATA-59' in metin
        assert 'HATA-00' not in metin

    def test_her_kaydin_zaman_damgasi_ve_turu_var(self, tmp_path):
        out = _run(_base_spec(consoleErrors=['X']), tmp_path)
        kayit = out['capturedErrors'][0]
        assert kayit['kind'] == 'console'
        assert re.match(r'^\+\d+\.\d+s$', kayit['at']), kayit['at']


# ===========================================================================
# 7. URL kaçışlaması
# ===========================================================================
@needs_node
class TestUrlKacislamasi:

    def test_baslik_ve_govde_birebir_geri_cozuluyor(self, tmp_path):
        baslik = 'Itki & basınç #3 + %50 "tuhaf" /eğri/'
        out = _run(_base_spec(title=baslik), tmp_path)
        _, alanlar = _decode_url(out['built']['url'])
        assert alanlar['title'] == baslik
        assert alanlar['body'] == out['built']['body']

    def test_satir_sonlari_ve_turkce_harfler_korunuyor(self, tmp_path):
        out = _run(_base_spec(
            fields={'what': 'Şöyle oldu:\nikinci satır\tsekme',
                    'expected': 'Böyle olmalıydı — çğıöşü',
                    'steps': ''}), tmp_path)
        _, alanlar = _decode_url(out['built']['url'])
        assert 'ikinci satır' in alanlar['body']
        assert 'çğıöşü' in alanlar['body']
        assert alanlar['body'] == out['built']['body']

    def test_ham_ayrac_karakterleri_urlde_kacislanmis(self, tmp_path):
        out = _run(_base_spec(title='a&b=c#d'), tmp_path)
        url = out['built']['url']
        sorgu = url.split('?', 1)[1]
        # Yalnız iki gerçek parametre ayracı olmalı
        assert sorgu.count('&') == 1
        assert '#' not in url, 'kaçışlanmamış # bağlantıyı kesiyor'
        assert '%26' in sorgu and '%23' in sorgu

    def test_bos_alanlarla_da_gecerli_url_uretiliyor(self, tmp_path):
        out = _run(_base_spec(title='', fields={}), tmp_path)
        parsed, alanlar = _decode_url(out['built']['url'])
        assert parsed.scheme == 'https'
        assert alanlar['title'] == ''
        assert alanlar['body']


# ===========================================================================
# 8. 8000 karakter sınırı: kısaltma + beyan
# ===========================================================================
@needs_node
class TestUzunlukSiniri:

    KULLANICI_IZI = 'KULLANICI-METNI-KORUNSUN-7781'

    def _uzun_spec(self):
        # 20 kayıtlık halka tampon + her kayıt 400 karaktere kadar → sınırı
        # rahatça aşan bir tanılama günlüğü. (Metin BOŞLUKLU seçildi: uzun
        # bitişik diziler temizleyicinin '<gizlendi>' kuralına takılıp
        # günlüğü kısaltıyordu.)
        dolgu = 'yigin izi satiri burada devam ediyor ' * 10
        hatalar = ['HATA-%02d ' % i + dolgu for i in range(30)]
        return _base_spec(
            diagnostics=True,
            consoleErrors=hatalar,
            title='Uzun gunluk',
            fields={'what': self.KULLANICI_IZI, 'expected': 'olmasin',
                    'steps': 'adim'})

    def test_kisa_govde_kirpilmiyor(self, tmp_path):
        out = _run(_base_spec(), tmp_path)
        assert out['built']['truncated'] is False
        assert out['built']['removed_chars'] == 0
        assert 'body_truncated' not in out['built']['body']

    def test_uzun_govde_kirpiliyor_ve_sinira_giriyor(self, tmp_path):
        out = _run(self._uzun_spec(), tmp_path)
        built = out['built']
        assert built['truncated'] is True, 'kırpma tetiklenmedi'
        assert len(built['url']) <= built['limit'] == 8000
        assert built['url_chars'] == len(built['url'])
        assert built['removed_chars'] > 0

    def test_kirpma_beyani_ve_kodu_ekleniyor(self, tmp_path):
        out = _run(self._uzun_spec(), tmp_path)
        built = out['built']
        assert 'warn.bugreport.body_truncated' in built['body'], \
            'kısaltma gövdede beyan edilmemiş'
        kodlar = [w['code'] for w in built['warnings']]
        assert 'warn.bugreport.body_truncated' in kodlar
        uyari = [w for w in built['warnings']
                 if w['code'] == 'warn.bugreport.body_truncated'][0]
        assert uyari['params']['chars'] == built['removed_chars']
        assert uyari['params']['limit'] == 8000

    def test_once_gunluk_gider_kullanici_metni_kalir(self, tmp_path):
        out = _run(self._uzun_spec(), tmp_path)
        govde = out['built']['body']
        assert self.KULLANICI_IZI in govde, 'kullanıcının kendi metni kırpıldı'
        # Günlüğün sonu (en yeni kayıtlar) kesilmiş olmalı
        assert 'HATA-29' not in govde

    def test_kirpilmis_url_de_birebir_cozuluyor(self, tmp_path):
        out = _run(self._uzun_spec(), tmp_path)
        _, alanlar = _decode_url(out['built']['url'])
        assert alanlar['body'] == out['built']['body']

    def test_asiri_uzun_baslik_github_sinirina_iniyor(self, tmp_path):
        out = _run(_base_spec(title='B' * 900), tmp_path)
        built = out['built']
        assert len(built['title']) == out['constants']['maxTitle'] == 256
        kodlar = [w['code'] for w in built['warnings']]
        assert 'warn.bugreport.title_truncated' in kodlar

    def test_sinir_kaynakta_tek_yerde_tanimli(self):
        kaynak = BUG_JS.read_text(encoding='utf-8')
        atamalar = re.findall(r'var MAX_URL_CHARS\s*=\s*(\d+)', kaynak)
        assert atamalar == ['8000'], atamalar


# ===========================================================================
# 9. Önizleme zorunlu (gönderilen = görülen)
# ===========================================================================
@needs_node
class TestOnizlemeKilidi:

    def test_onizlenmemis_govde_acilmaz(self, tmp_path):
        out = _run(_base_spec(doOpenWithoutPreview=True), tmp_path)
        res = out['openWithoutPreview']
        assert res['opened'] is False
        assert res['needs_preview'] is True
        assert res['url'] is None
        kodlar = [w['code'] for w in res['warnings']]
        assert 'warn.bugreport.preview_required' in kodlar
        assert out['opened'] == [], 'window.open önizlemeden önce çağrıldı'

    def test_onizlenmis_govde_yeni_sekmede_aciliyor(self, tmp_path):
        out = _run(_base_spec(doOpen=True, markPreviewed=True), tmp_path)
        res = out['openResult']
        assert res['opened'] is True
        assert res['needs_preview'] is False
        assert len(out['opened']) == 1
        cagri = out['opened'][0]
        assert cagri['url'] == res['url']
        assert cagri['target'] == '_blank'
        assert 'noopener' in (cagri['features'] or '')

    def test_onizlemeden_sonra_degisen_metin_kilit_disi(self, tmp_path):
        """markPreviewed edilen metin değiştirilirse kilit yeniden devreye
        girer — bu yüzden panel her düzenlemede markPreviewed çağırır."""
        kaynak = BUG_JS.read_text(encoding='utf-8')
        assert 'function isPreviewed' in kaynak
        assert '=== _seenBody' in kaynak or '_seenBody' in kaynak
        panel = PANEL_JS.read_text(encoding='utf-8')
        assert 'markPreviewed' in panel
        assert "bodyArea.addEventListener('input', syncPreview)" in panel

    def test_sekme_engellenirse_acilmadi_bildirilir(self, tmp_path):
        out = _run(_base_spec(doOpen=True, markPreviewed=True,
                              openBlocked=True), tmp_path)
        res = out['openResult']
        assert res['opened'] is False
        assert res['url'], 'elle açılabilsin diye bağlantı geri verilmeli'
        assert res['needs_preview'] is False


# ===========================================================================
# 10. Hedef depo tek yerde ve doğru
# ===========================================================================
class TestHedefDepo:

    def test_depo_kaynakta_tek_yerde_sabit(self):
        kaynak = BUG_JS.read_text(encoding='utf-8')
        atamalar = re.findall(r"var REPO\s*=\s*'([^']+)'", kaynak)
        assert atamalar == ['berketez/HRMA'], atamalar
        # Depo adı başka hiçbir yerde tekrar yazılmamalı (tek kaynak)
        assert kaynak.count('berketez/HRMA') == 1

    def test_issue_url_i_depodan_turetiliyor(self):
        kaynak = BUG_JS.read_text(encoding='utf-8')
        assert "ISSUE_NEW_URL = 'https://github.com/' + REPO + '/issues/new'" \
            in kaynak
        # Elle yazılmış ikinci bir github.com adresi olmamalı
        assert len(re.findall(r"https://github\.com/", kaynak)) == 1

    def test_panel_issue_adresini_kendi_yazmiyor(self):
        panel = PANEL_JS.read_text(encoding='utf-8')
        assert 'issues/new' not in panel, \
            'panel issue adresini kendi kuruyor; tek kaynak bug_report.js olmalı'

    @needs_node
    def test_uretilen_url_dogru_depoya_gidiyor(self, tmp_path):
        out = _run(_base_spec(), tmp_path)
        url = out['built']['url']
        assert url.startswith('https://github.com/berketez/HRMA/issues/new?')
        assert out['constants']['repo'] == 'berketez/HRMA'


# ===========================================================================
# 11. Panel bağlaması (kaynak taraması — DOM cerrahisi node'da koşmaz)
# ===========================================================================
class TestPanelBaglamasi:

    @pytest.fixture(scope='class')
    def panel(self):
        return PANEL_JS.read_text(encoding='utf-8')

    def test_bolum_ayarlar_panelinde_ciziliyor(self, panel):
        assert 'appendBugSection(box)' in panel
        assert "sectionTitle('shell.bug.section'" in panel

    def test_betik_yoksa_olu_dugme_konmuyor(self, panel):
        bolum = panel.split('function appendBugSection', 1)[1]
        bas = bolum[:400]
        assert 'var BR = window.HRMABugReport;' in bas
        assert 'if (!BR) return;' in bas

    def test_tanilama_kutusu_varsayilan_kapali(self, panel):
        assert 'diagBox.checked = false;' in panel
        assert 'diagBox.checked = true' not in panel

    def test_form_alanlari_tam(self, panel):
        for anahtar in ('shell.bug.titleLabel', 'shell.bug.whatLabel',
                        'shell.bug.expectedLabel', 'shell.bug.stepsLabel',
                        'shell.bug.diagnostics'):
            assert anahtar in panel, anahtar + ' alanı yok'

    def test_gonderme_yalniz_openIssue_uzerinden(self, panel):
        """Panelin issue açan tek yolu bug_report.js'in kilitli kapısıdır."""
        assert 'BR.openIssue(' in panel
        # Panelde doğrudan window.open ile issue açan bir kestirme olmamalı
        assert 'window.open' not in panel
        assert '.open(' not in panel.replace('BR.openIssue(', '')

    def test_onizleme_adimi_gonderme_adimindan_once(self, panel):
        assert panel.index('previewBtn.addEventListener') \
            < panel.index('sendBtn.addEventListener')
        # Önizleme kırpmayı BURADA yapar (gönderilen = görülen)
        onizleme = panel.split('previewBtn.addEventListener', 1)[1][:1200]
        assert 'BR.buildIssueUrl(' in onizleme
        assert 'bodyArea.value = built.body;' in onizleme

    def test_panel_kapaninca_onizleme_kilidi_sifirlaniyor(self, panel):
        kapat = panel.split('function closeModal', 1)[1][:400]
        assert 'resetPreview' in kapat

    def test_uyari_cipleri_kod_params_sozlesmesiyle(self, panel):
        assert "node.setAttribute('data-warn-code', code);" in panel
        assert 'WARN_FALLBACK' in panel
        for kod in ('warn.bugreport.body_truncated',
                    'warn.bugreport.title_truncated',
                    'warn.bugreport.preview_required'):
            assert kod in panel, kod + ' için yedek metin yok'


# ===========================================================================
# 11b. Akışın kendisi: panel node altında AÇILIR, düğmelere BASILIR
#      ("kanal var kapı yok" dersi: kaynak taraması düğmenin çalıştığını
#       kanıtlamaz; burada gerçek tıklama zinciri yürütülür)
# ===========================================================================
PANEL_HARNESS = r"""
'use strict';
const dir = process.argv[2];

function setG(n, v) {
    Object.defineProperty(global, n, {
        value: v, writable: true, configurable: true, enumerable: true });
}
global.window = global;
setG('location', { pathname: '/hybrid' });
setG('navigator', { userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X '
    + '10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 '
    + 'Safari/537.36' });
global.HRMA_APP_VERSION = '2.6.27';

// --- asgari DOM ---
function Node(tag) {
    this.tagName = String(tag || '').toUpperCase();
    this.children = []; this.parent = null; this.attrs = {};
    this.listeners = {}; this.style = {}; this._html = '';
    this.textContent = ''; this.id = ''; this.value = ''; this.checked = false;
}
Object.defineProperty(Node.prototype, 'innerHTML', {
    get() { return this._html; },
    set(v) { this._html = String(v); this.children = []; },
});
Node.prototype.setAttribute = function (k, v) { this.attrs[k] = String(v); };
Node.prototype.getAttribute = function (k) {
    return (k in this.attrs) ? this.attrs[k] : null; };
Node.prototype.appendChild = function (c) {
    c.parent = this; this.children.push(c); return c; };
Node.prototype.addEventListener = function (n, fn) {
    (this.listeners[n] = this.listeners[n] || []).push(fn); };
Node.prototype.remove = function () {
    if (!this.parent) return;
    const i = this.parent.children.indexOf(this);
    if (i >= 0) this.parent.children.splice(i, 1);
};
Node.prototype.querySelector = function () { return null; };
Node.prototype.click = function () {
    (this.listeners['click'] || []).forEach(fn => fn({ target: this }));
    if (typeof this.onclick === 'function') this.onclick({ target: this });
};

const body = new Node('body');
function walk(n, fn) { fn(n); n.children.forEach(c => walk(c, fn)); }
function byId(id) {
    let hit = null;
    walk(body, n => { if (!hit && n.id === id) hit = n; });
    return hit;
}
function allInputs() {
    const out = [];
    walk(body, n => { if (n.tagName === 'INPUT') out.push(n); });
    return out;
}
setG('document', {
    body: body,
    readyState: 'complete',
    createElement: t => new Node(t),
    createTextNode: t => { const n = new Node('#text');
                           n.textContent = String(t); return n; },
    getElementById: byId,
    querySelector: () => null,
    querySelectorAll: sel => (sel === 'input' ? allInputs() : []),
    addEventListener() {},
});
setG('localStorage', {
    _d: {},
    getItem(k) { return (k in this._d) ? this._d[k] : null; },
    setItem(k, v) { this._d[k] = String(v); },
    removeItem(k) { delete this._d[k]; },
});
global.addEventListener = function () {};
const opened = [];
global.open = function (u, t, f) {
    opened.push({ url: u, target: t, features: f });
    return { closed: false };
};

require(dir + '/bug_report.js');
require(dir + '/settings_panel.js');

const r = {};
window.hrmaShowSettings();
r.modalAcildi = !!byId('hrma-settings-modal');
r.bolumVar = !!byId('hrma-bug-preview-btn');
if (!r.bolumVar) {
    // Bölüm hiç çizilmediyse tıklama zinciri koşturulamaz; sonda çökmek
    // yerine eksiği bildirir (hangi bekçinin düştüğü okunur kalsın).
    process.stdout.write(JSON.stringify(r));
    process.exit(0);
}
r.tanilamaVarsayilan = byId('hrma-bug-diagnostics').checked;

// 1) eksik başlıkla önizleme reddediliyor mu
byId('hrma-bug-preview-btn').click();
r.bosBaslikUyarisi = byId('hrma-bug-form-status').textContent;
r.bosBaslikGovde = byId('hrma-bug-body').value;
r.bosBaslikAcilan = opened.length;

// 2) doldur, önizle
byId('hrma-bug-title').value = 'Itki egrisi cizilmiyor';
byId('hrma-bug-what').value = 'KULLANICI-METNI-42';
byId('hrma-bug-expected').value = 'Egri cizilsin';
byId('hrma-bug-steps').value = '1. hibrit 2. analiz';
byId('hrma-bug-preview-btn').click();
r.onizlemeGovde = byId('hrma-bug-body').value;
r.onizlemeSonrasiAcilan = opened.length;

// 3) gönder
byId('hrma-bug-send-btn').click();
r.gonderSonrasiAcilan = opened.length;
r.acilan = opened.length ? opened[0] : null;
r.gonderDurumu = byId('hrma-bug-send-status').textContent;

// 4) geri -> önizleme kilidi düşer
byId('hrma-bug-back-btn').click();
r.geriSonrasiKilit = window.HRMABugReport.isPreviewed(
    'Itki egrisi cizilmiyor', r.onizlemeGovde);

process.stdout.write(JSON.stringify(r));
"""


@needs_node
class TestPanelAkisi:
    """Ayarlar panelini gerçekten açar ve düğme zincirini yürütür."""

    @pytest.fixture(scope='class')
    def akis(self, tmp_path_factory):
        tmp = tmp_path_factory.mktemp('panel')
        script = tmp / 'panel.js'
        script.write_text(PANEL_HARNESS, encoding='utf-8')
        proc = subprocess.run([NODE, str(script), str(JS_DIR)],
                              capture_output=True, text=True, timeout=120)
        assert proc.returncode == 0, \
            'ayarlar paneli node altında çöktü:\n' + proc.stderr
        return json.loads(proc.stdout)

    def test_ayarlar_penceresi_hala_aciliyor(self, akis):
        """Yeni bölüm mevcut ayarlar penceresini bozmamalı."""
        assert akis['modalAcildi'] is True

    def test_hata_bildir_bolumu_ciziliyor(self, akis):
        assert akis['bolumVar'] is True

    @pytest.fixture(autouse=True)
    def _bolum_sart(self, request, akis):
        """Bölüm çizilmediyse akış bekçileri boş sözlük üstünden geçmesin."""
        if request.function.__name__ in ('test_ayarlar_penceresi_hala_aciliyor',
                                         'test_hata_bildir_bolumu_ciziliyor'):
            return
        assert akis.get('bolumVar') is True, \
            '"Hata bildir" bölümü çizilmedi — akış sınanamıyor'

    def test_tanilama_kutusu_kapali_aciliyor(self, akis):
        assert akis['tanilamaVarsayilan'] is False

    def test_bos_baslikla_onizleme_yapilmiyor(self, akis):
        assert akis['bosBaslikGovde'] == ''
        assert akis['bosBaslikUyarisi'], 'kullanıcıya gerekçe söylenmiyor'
        assert akis['bosBaslikAcilan'] == 0

    def test_onizleme_kullanici_metnini_ve_ortami_gosteriyor(self, akis):
        govde = akis['onizlemeGovde']
        assert 'KULLANICI-METNI-42' in govde
        assert 'v2.6.27' in govde
        assert '/hybrid' in govde

    def test_onizleme_asamasinda_hicbir_sekme_acilmiyor(self, akis):
        assert akis['onizlemeSonrasiAcilan'] == 0, \
            'önizleme adımı sekme açıyor — kullanıcı metni görmeden gidiyor'

    def test_gonder_dogru_depoyu_yeni_sekmede_aciyor(self, akis):
        assert akis['gonderSonrasiAcilan'] == 1
        cagri = akis['acilan']
        assert cagri['url'].startswith(
            'https://github.com/berketez/HRMA/issues/new?')
        assert cagri['target'] == '_blank'
        assert 'noopener' in (cagri['features'] or '')
        assert akis['gonderDurumu']

    def test_acilan_url_onizlemede_gorulen_govdeyi_tasiyor(self, akis):
        _, alanlar = _decode_url(akis['acilan']['url'])
        assert alanlar['body'] == akis['onizlemeGovde'], \
            'gönderilen metin önizlemede görülenden farklı'
        assert alanlar['title'] == 'Itki egrisi cizilmiyor'

    def test_geri_dugmesi_onizleme_kilidini_dusuruyor(self, akis):
        assert akis['geriSonrasiKilit'] is False


# ===========================================================================
# 12. Şablonlar: betik her ayarlar sayfasında ve settings_panel'den ÖNCE
# ===========================================================================
class TestSablonlar:

    @pytest.mark.parametrize('sayfa', PAGES_WITH_SETTINGS)
    def test_betik_yukleniyor_ve_panelden_once(self, sayfa):
        metin = (TEMPLATE_DIR / sayfa).read_text(encoding='utf-8')
        bug = metin.find('/static/js/bug_report.js')
        panel = metin.find('/static/js/settings_panel.js')
        assert bug != -1, sayfa + ' bug_report.js yüklemiyor'
        assert panel != -1
        assert bug < panel, sayfa + ': bug_report.js panelden sonra yükleniyor'

    def test_ayarlar_paneli_yukleyen_sayfa_listesi_guncel(self):
        """Yeni bir sayfa ayarlar panelini yüklerse bu test onu yakalar."""
        yukleyen = sorted(p.name for p in TEMPLATE_DIR.glob('*.html')
                          if '/static/js/settings_panel.js'
                          in p.read_text(encoding='utf-8'))
        assert yukleyen == sorted(PAGES_WITH_SETTINGS), (
            'ayarlar panelini yükleyen sayfa kümesi değişti: ' + str(yukleyen))

    def test_betik_dosyasi_var_ve_bos_degil(self):
        assert BUG_JS.exists()
        assert BUG_JS.stat().st_size > 2000


class TestSunulanVarlik:
    """Sunucu betiği gerçekten servis ediyor mu (test_client — port yok)."""

    @pytest.fixture(scope='class')
    def client(self):
        from hrma.app import app
        app.config['TESTING'] = True
        with app.test_client() as c:
            yield c

    def test_betik_servis_ediliyor(self, client):
        res = client.get('/static/js/bug_report.js')
        assert res.status_code == 200
        assert b'HRMABugReport' in res.data

    @pytest.mark.parametrize('yol', ['/', '/hybrid', '/solid', '/liquid',
                                     '/formulas', '/launch-site'])
    def test_sayfa_betigi_isaretliyor(self, client, yol):
        res = client.get(yol)
        assert res.status_code == 200
        assert b'/static/js/bug_report.js' in res.data, yol


# ===========================================================================
# 13. i18n: metinler T()/TF() üzerinden, ad alanı ayrılmış
# ===========================================================================
class TestMetinler:

    KEY_RE = re.compile(r"\bTF?\(\s*'([^']+)'")

    def _keys(self, path):
        return set(self.KEY_RE.findall(path.read_text(encoding='utf-8')))

    def test_govde_basliklari_cevriliyor(self):
        """Markdown başlıkları sabit İngilizce metinle yazılmamalı."""
        kaynak = BUG_JS.read_text(encoding='utf-8')
        for satir in kaynak.splitlines():
            s = satir.strip()
            if s.startswith("L.push('###"):
                assert 'T(' in s, 'çevrilmeyen gövde başlığı: ' + s

    def test_bug_report_anahtarlari_ayrilmis_ad_alaninda(self):
        for k in self._keys(BUG_JS):
            assert k.startswith('shell.bug.'), \
                'bug_report.js ayrılmamış anahtar kullanıyor: ' + k

    def test_panelin_yeni_anahtarlari_ayrilmis_ad_alaninda(self):
        mevcut = {'shell.settings.', 'shell.close', 'lang.', 'link.'}
        for k in self._keys(PANEL_JS):
            if any(k.startswith(p) for p in mevcut):
                continue
            assert k.startswith('shell.bug.') or k.startswith('warn.bugreport.'), \
                'settings_panel.js beklenmedik anahtar kullanıyor: ' + k

    def test_her_ceviri_cagrisinin_ingilizce_yedegi_var(self):
        """Sözlük anahtarı henüz eklenmemişken arayüz boş kalmamalı."""
        desen = re.compile(r"\bT\(\s*'(shell\.bug\.[^']+)'\s*,\s*(.)", re.S)
        for path in (BUG_JS, PANEL_JS):
            bulunan = 0
            for m in desen.finditer(path.read_text(encoding='utf-8')):
                bulunan += 1
                assert m.group(2) == "'", \
                    path.name + ': ' + m.group(1) + ' için yedek metin yok'
            assert bulunan, path.name + ': hiç shell.bug.* çağrısı bulunamadı'

    def test_yedek_metinler_ingilizce(self):
        """Yedekler İngilizcedir (çeviri sözlükten gelir) — Türkçe kaçmasın."""
        kaynak = BUG_JS.read_text(encoding='utf-8')
        yedekler = re.findall(r"T\(\s*'shell\.bug\.[^']+'\s*,\s*'([^']*)'",
                              kaynak)
        assert yedekler, 'yedek metin bulunamadı (desen değişmiş olabilir)'
        for y in yedekler:
            assert not re.search(r'[çğıöşüÇĞİÖŞÜ]', y), \
                'İngilizce yedekte Türkçe harf: ' + y


# ===========================================================================
# 14. Dosya bütünlüğü
# ===========================================================================
class TestSozdizimi:

    @needs_node
    @pytest.mark.parametrize('path', [BUG_JS, PANEL_JS], ids=lambda p: p.name)
    def test_node_check_geciyor(self, path):
        proc = subprocess.run([NODE, '--check', str(path)],
                              capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, proc.stderr

    def test_gomulu_github_belirteci_yok(self):
        """Dağıtılan ikiliye belirteç gömmeme kararının bekçisi."""
        for path in (BUG_JS, PANEL_JS):
            kaynak = path.read_text(encoding='utf-8')
            assert not re.search(r'gh[pousr]_[A-Za-z0-9]{20,}', kaynak)
            assert 'Authorization' not in kaynak
            assert 'api.github.com' not in kaynak
