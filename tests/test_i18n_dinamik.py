"""Dinamik yüzeylerin dil bütünlüğü (2026-08-03).

Kapsam — statik şablon katmanının DIŞINDA kalan, çalışma anında JS'in
ürettiği metinler:

  * ``hrma/static/js/i18n_charts.js``  — ``serverText`` boru hattı
  * ``hrma/static/js/analysis_dock.js``, ``hrma/static/js/app.js``
        — düz metin uyarıları serverText'e BAĞLAYAN kablolama
  * ``hrma/static/js/motor_viz_deck.js`` — 3B güverte HUD metinleri
  * ``hrma/static/js/plotly_dark.js``    — modebar ipucu metni
  * ``hrma/validation/experiment_db.py`` — küratör hata mesajlarının imlası

NEDEN BU DOSYA VAR
------------------
``serverText`` 2026-07'de yazıldı, MSG_PATTERNS tablosuna 20+ kural
girdi — ve fonksiyon **hiçbir yerden çağrılmadı**. Kanal vardı, kapı
yoktu: ``{code, params}`` sözleşmesine geçmemiş bütün API uyarıları
(validation/*, importers/*, regen_cooling) TR modda İngilizce kaldı.
Sözlük testleri bunu göremezdi, çünkü sözlük doğruydu; eksik olan
çağrıydı. Aşağıdaki testler hem KABLOYU hem de gerçek backend mesaj
biçimlerini kilitler.

Aynı kusur ailesi 3B güvertede de vardı: ``motor_viz_deck.js``in görünür
metinlerinin tamamı sabit İngilizceydi ve dil değişiminde tazelenecek bir
kanca yoktu (plotly_dark.js grafikler için bunu ``redrawAllPlots`` ile
çözüyordu, güverte için karşılığı yoktu).
"""

import json
import pathlib
import re
import shutil
import subprocess
import warnings

import pytest

warnings.filterwarnings('ignore')

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC_JS = REPO_ROOT / 'hrma' / 'static' / 'js'
CHARTS_JS = STATIC_JS / 'i18n_charts.js'
DOCK_JS = STATIC_JS / 'analysis_dock.js'
APP_JS = STATIC_JS / 'app.js'
DECK_JS = STATIC_JS / 'motor_viz_deck.js'
PLOTLY_DARK_JS = STATIC_JS / 'plotly_dark.js'

NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node kurulu değil')


# ---------------------------------------------------------------------------
# 1. KABLOLAMA — serverText gerçekten çağrılıyor mu?
# ---------------------------------------------------------------------------
def test_analysis_dock_duz_metin_uyarisini_serverText_ten_geciriyor():
    """warnText'in string dalı çeviriden geçmeli.

    Bu dal düz ``return w;`` olursa MSG_PATTERNS yeniden ölü koda döner.
    """
    src = DOCK_JS.read_text(encoding='utf-8')
    assert 'I18N.serverText' in src, \
        'analysis_dock.js serverText köprüsünü hiç kurmuyor'
    assert re.search(r"typeof w === 'string'\) return SRV\(w\);", src), \
        ("analysis_dock.js::warnText düz metin dalı serverText'ten geçmiyor — "
         'API uyarıları TR modda İngilizce kalır')


def test_app_js_duz_metin_uyarisini_serverText_ten_geciriyor():
    src = APP_JS.read_text(encoding='utf-8')
    assert 'I18N.serverText' in src, 'app.js serverText köprüsünü hiç kurmuyor'
    assert re.search(r"typeof w === 'string'\) return SRV\(w\);", src), \
        "app.js::warnToText düz metin dalı serverText'ten geçmiyor"
    assert 'SRV(w.message || w.text || JSON.stringify(w))' in src, \
        ('kodsuz uyarı nesnesinin message/text alanı çevrilmiyor — '
         '{code} taşımayan uyarılar İngilizce kalır')


def test_app_js_yedek_grafik_metinleri_cevriliyor():
    """Grafik çizilemediğinde basılan yedek metinler de dil katmanından geçer."""
    src = APP_JS.read_text(encoding='utf-8')
    for metin in ('Plot data unavailable', 'No data available',
                  '3D visualization unavailable'):
        assert "SRV('%s')" % metin in src, \
            'app.js yedek metni çeviriden geçmiyor: %r' % metin


def test_plotly_dark_modebar_ipucu_dile_bagli():
    """toImage düğmesinin ipucu SABİT dize olmamalı.

    Sabit dize olursa metin yükleme anındaki dilde donar; dil değişince
    grafikler yeniden çizilse bile ipucu İngilizce kalır.
    """
    src = PLOTLY_DARK_JS.read_text(encoding='utf-8')
    assert re.search(r'get title\(\)\s*\{', src), \
        'plotly_dark.js modebar başlığı getter değil — dil değişimini kaçırır'
    assert not re.search(r"^\s*title: 'Download plot as a png',", src, re.M), \
        'modebar ipucu hâlâ sabit İngilizce dize'


# ---------------------------------------------------------------------------
# 2. DAVRANIŞ — gerçek dosyalar node'da koşturulur
# ---------------------------------------------------------------------------
SERVER_HARNESS = r"""
'use strict';
const fs = require('fs');
const vm = require('vm');
const ROOT = process.argv[2];
const IN = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));

const sandbox = {
    console, setTimeout, clearTimeout, setInterval, clearInterval,
    JSON, Object, Array, Math, RegExp, String, Number, Boolean, Date, Error,
};
sandbox.window = sandbox;
sandbox.self = sandbox;
sandbox.document = {
    readyState: 'complete',
    documentElement: { setAttribute() {}, appendChild() {} },
    head: { appendChild() {} },
    createElement: () => ({ setAttribute() {}, appendChild() {}, style: {} }),
    getElementById: () => null,
    querySelector: () => null,
    querySelectorAll: () => [],
    addEventListener() {}, dispatchEvent() { return true; },
};
sandbox.localStorage = null;
sandbox.CustomEvent = function (t, i) { this.type = t; this.detail = i && i.detail; };
vm.createContext(sandbox);
for (const f of ['i18n.js', 'i18n_charts.js']) {
    vm.runInContext(fs.readFileSync(ROOT + '/' + f, 'utf8'), sandbox, { filename: f });
}
sandbox.I18N.setLang('tr');
const tr = IN.map((s) => sandbox.I18N.serverText(s));
sandbox.I18N.setLang('en');
const en = IN.map((s) => sandbox.I18N.serverText(s));
process.stdout.write(JSON.stringify({ tr, en }));
"""


def _server_translate(tmp_path, texts):
    harness = tmp_path / 'srv.js'
    harness.write_text(SERVER_HARNESS, encoding='utf-8')
    payload = tmp_path / 'in.json'
    payload.write_text(json.dumps(texts), encoding='utf-8')
    proc = subprocess.run([NODE, str(harness), str(STATIC_JS), str(payload)],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, 'node düzeneği düştü:\n%s' % proc.stderr
    return json.loads(proc.stdout)


def _gercek_dogrulama_mesajlari():
    """Python doğrulayıcılarını GERÇEKTEN çalıştırıp mesaj üretir.

    Metinler elle kopyalanmaz: biçim değişirse bu test kendiliğinden
    yeni metni ölçer ve desen tutmuyorsa kırmızıya döner.
    """
    from hrma.validation.motor_validation import MotorDataValidator
    from hrma.validation.user_data_validation import parse_thrust_csv
    from hrma.importers import motor_file

    mesajlar = []
    validator = MotorDataValidator()

    for veri, tip in (
        ({}, 'kahve_makinesi'),                       # geçersiz motor tipi
        ({'thrust': None}, 'hybrid'),                 # eksik zorunlu alan
        ({'thrust': 'çok', 'chamber_pressure': 30}, 'hybrid'),   # sayısal değil
        ({'thrust': 9e9, 'chamber_pressure': 30, 'burn_time': 5,
          'fuel_type': 'kahve', 'oxidizer_type': 'kola'}, 'hybrid'),  # aralık dışı
        ({'throat_diameter': 0.5, 'chamber_diameter': 0.1,
          'exit_diameter': 0.01, 'chamber_pressure': 30}, 'liquid'),  # geometri
    ):
        try:
            _, msgs = validator.validate_motor_data(veri, tip)
        except Exception:
            continue
        mesajlar.extend(m for m in msgs if isinstance(m, str))

    # Ölçüm CSV'si: hem uyarı hem hata (ValueError) dalları
    for icerik in (
        123,                                          # metin değil
        '',                                           # boş dosya
        'time,thrust\nabc,def\n',                     # sayısal satır yok
        'time,thrust\n1,5\n0,3\n1,9\n2,-4\n',         # sırasız + tekrar + negatif
        'time,thrust\ns,N\n0,0\n1,10\n2,0\n',         # birim satırı
    ):
        try:
            sonuc = parse_thrust_csv(icerik)
        except ValueError as hata:
            mesajlar.append(str(hata))
            continue
        except Exception:
            continue
        if isinstance(sonuc, dict):
            mesajlar.extend(m for m in (sonuc.get('warnings') or [])
                            if isinstance(m, str))

    # RASP/RSE içe aktarma uyarıları
    eng = ('; yorum\nTEST 38 120 0 0.05 0.08 HRMA\n'
           '   0.1 20.0\n   0.5 18.0\n   1.0 3.0\n')
    try:
        sonuc = motor_file.parse_eng(eng)
        if isinstance(sonuc, dict):
            mesajlar.extend(m for m in (sonuc.get('warnings') or [])
                            if isinstance(m, str))
    except Exception:
        pass

    return [re.sub(r'\s+', ' ', m).strip()
            for m in mesajlar if isinstance(m, str) and m.strip()]


@needs_node
def test_gercek_dogrulama_mesajlari_cevriliyor(tmp_path):
    """motor_validation / user_data_validation mesajları TR'de çevrilmeli.

    DÜŞÜK ÇIKARSA mesajı Python tarafında değiştirme — i18n_charts.js
    MSG_PATTERNS tablosuna kural ekle. Backend mesaj biçimi bu testin
    referansıdır; assert iletisi çevrilemeyenleri tek tek listeler.
    """
    mesajlar = sorted(set(_gercek_dogrulama_mesajlari()))
    if not mesajlar:
        pytest.skip('doğrulayıcılar bu koşuda mesaj üretmedi')

    sonuc = _server_translate(tmp_path, mesajlar)
    eksik = [m for m, c in zip(mesajlar, sonuc['tr']) if m == c]
    oran = 1.0 - len(eksik) / float(len(mesajlar))
    assert oran >= 0.95, (
        'Doğrulama mesajı çeviri kapsamı %%%.1f (>= %%95 olmalı). '
        'Çevrilemeyen %d mesaj:\n  %s'
        % (100 * oran, len(eksik), '\n  '.join(eksik))
    )


#: Çevrilmiş bir mesajda GÖRÜNMEMESİ gereken İngilizce işlev sözcükleri.
#: Yalnız sözcük sınırıyla aranır; teknik jetonlar (N, CSV, RASP) ve alan
#: adları (thrust, burn_time) bu listede DEĞİLDİR.
INGILIZCE_ISLEV_SOZCUKLERI = re.compile(
    r'\b(the|that|with|must|required|should|expected|check|please|'
    r'contains|values|were|because|which|from|into|about|there|'
    r'cannot|could|would|removed|skipped|kept|columns|rows)\b', re.I)


@needs_node
def test_cevrilen_mesajlarda_yarim_ceviri_kalmiyor(tmp_path):
    """Değişmiş olmak yetmez — mesajın TAMAMI Türkçeleşmiş olmalı.

    Kapsam sayacı "metin değişti mi" diye bakar; çok cümleli bir mesajda
    ilk cümleyi çeviren bir kural sayacı tatmin eder ama kullanıcıya yarı
    İngilizce satır gösterir. ÖLÇÜLDÜ (2026-08-03): 'Could not parse
    thrust data: ...' mesajının ikinci cümlesi tam olarak böyle
    İngilizce kalmıştı, çünkü applyPatterns İLK eşleşmede dönüyor ve
    ikinci cümle için yazılan ayrı kural hiç çalışmıyordu.
    """
    mesajlar = sorted(set(_gercek_dogrulama_mesajlari()))
    if not mesajlar:
        pytest.skip('doğrulayıcılar bu koşuda mesaj üretmedi')

    sonuc = _server_translate(tmp_path, mesajlar)
    yarim = []
    for kaynak, cevrilmis in zip(mesajlar, sonuc['tr']):
        if kaynak == cevrilmis:
            continue                       # hiç çevrilmemiş: öteki testin işi
        artik = INGILIZCE_ISLEV_SOZCUKLERI.findall(cevrilmis)
        if artik:
            yarim.append('%r\n     -> %r  (kalan: %s)'
                         % (kaynak, cevrilmis, sorted(set(artik))))
    assert not yarim, (
        'Yarım çeviri — mesaj değişti ama İngilizce cümle kaldı:\n  '
        + '\n  '.join(yarim)
        + '\n\nÇok cümleli mesaj için TEK kural yazın; applyPatterns ilk '
          'eşleşmede döner.'
    )


@needs_node
def test_server_text_en_dilinde_mesaja_dokunmuyor(tmp_path):
    """EN dokunulmazlığı: İngilizce kipte metin BİREBİR aynı kalmalı."""
    ornekler = [
        'Invalid motor type: kahve_makinesi',
        'Missing required parameter: thrust',
        'Cavitation risk: Nurick cavitation number K_c = -0.02 < 1.5 (P_v = 50.4 bar at 293 K)',
        'Totally unknown message that is in no dictionary',
    ]
    sonuc = _server_translate(tmp_path, ornekler)
    assert sonuc['en'] == ornekler, 'serverText EN kipinde metni değiştirdi'
    # Bilinmeyen mesaj TR'de de AYNEN kalmalı (asla anahtar, asla boş)
    assert sonuc['tr'][-1] == ornekler[-1]


# ---------------------------------------------------------------------------
# 3. 3B GÜVERTE — metinler çevriliyor ve dil değişiminde tazeleniyor mu?
# ---------------------------------------------------------------------------
DECK_HARNESS = r"""
'use strict';
const fs = require('fs');
const vm = require('vm');
const ROOT = process.argv[2];

/* --- Asgari DOM: motor_viz_deck.js yalnız şunlara dokunuyor --- */
function makeEl(id) {
    return {
        id, innerHTML: '', textContent: '', style: {},
        _attrs: {},
        classList: { toggle() {}, add() {}, remove() {}, contains: () => false },
        setAttribute(k, v) { this._attrs[k] = v; },
        getAttribute(k) { return this._attrs[k]; },
        appendChild() {}, removeChild() {}, click() {},
    };
}

const els = {};
const listeners = {};
const sandbox = {
    console, setTimeout, clearTimeout, setInterval, clearInterval,
    JSON, Object, Array, Math, RegExp, String, Number, Boolean, Date, Error,
    performance: { now: () => 0 },
};
sandbox.window = sandbox;
sandbox.self = sandbox;
sandbox.document = {
    readyState: 'complete',
    documentElement: { setAttribute() {}, appendChild() {} },
    head: { appendChild() {} },
    body: { appendChild() {}, removeChild() {} },
    createElement: () => makeEl('tmp'),
    getElementById: (id) => (els[id] = els[id] || makeEl(id)),
    querySelector: () => null,
    querySelectorAll: () => [],
    addEventListener: (n, fn) => { (listeners[n] = listeners[n] || []).push(fn); },
    dispatchEvent: (ev) => { (listeners[ev.type] || []).forEach((f) => f(ev)); return true; },
};
sandbox.localStorage = null;
sandbox.CustomEvent = function (t, i) { this.type = t; this.detail = i && i.detail; };

/* --- MotorViz3D taklidi: güverte yalnız bu yüzeyi kullanıyor --- */
const vizState = { playing: false, cutaway: true, labels: true, plume: true,
                   exploded: false, autoRotate: false, heatMap: false,
                   portShape: 'circular' };
sandbox.MotorViz3D = {
    isSupported: () => true,
    update() {},
    mount(id, md, opts) {
        return {
            state: vizState, dims: { burnTime: 10 },
            setCutaway() {}, setLabels() {}, setPlume() {}, setExploded() {},
            setAutoRotate() {}, setPortShape(s) { vizState.portShape = s; },
            cyclePortShape() { vizState.portShape = 'star'; },
            cycleCameraPreset: () => 'nozzle',
            setQuality() {}, cycleSpeed: () => 2,
            setHeatMap: (v) => v, getHeatInfo: () => null,
            resetCamera() {}, snapshot: () => null,
            play() {}, pause() {}, setTime() {}, update() {},
        };
    },
};

vm.createContext(sandbox);
for (const f of ['i18n.js', 'i18n_charts.js', 'motor_viz_deck.js']) {
    vm.runInContext(fs.readFileSync(ROOT + '/' + f, 'utf8'), sandbox, { filename: f });
}

const motorData = {
    viz_motor_type: 'solid', chamber_diameter: 0.075, grain_length: 0.36,
    chamber_pressure: 40, throat_diameter: 0.02, exit_diameter: 0.05,
};

const out = {};

/* --- EN kipinde kurulum --- */
sandbox.I18N.setLang('en');
const hostEn = sandbox.document.getElementById('host_en');
sandbox.MotorVizDeck.create('host_en', Object.assign({}, motorData), {});
out.en = hostEn.innerHTML;

/* --- TR kipinde kurulum --- */
sandbox.I18N.setLang('tr');
const hostTr = sandbox.document.getElementById('host_tr');
const deck = sandbox.MotorVizDeck.create('host_tr', Object.assign({}, motorData), {});
out.tr = hostTr.innerHTML;

/* --- Dil değişiminde tazeleme: EN'de kurulan güverte TR'ye dönmeli ---
   SINIR: bu taklitte host.innerHTML bir DİZEDİR, ayrıştırılmaz; yani
   düğmeler gerçek çocuk düğüm değildir. Dolayısıyla aşağıdaki ölçüm
   "kanca ateşlendi ve DOĞRU eleman kimliğine Türkçe metni yazdı"
   der — tarayıcıdaki boyama sırasını doğrulamaz. */
sandbox.I18N.setLang('en');
const deckSwap = sandbox.MotorVizDeck.create('host_swap', Object.assign({}, motorData), {});
const btnId = deckSwap.prefix + '_btn_cut';
out.swapBefore = sandbox.document.getElementById(btnId).textContent;
sandbox.I18N.setLang('tr');
out.swapAfter = sandbox.document.getElementById(btnId).textContent;
out.hasRefresh = typeof deck.refreshLabels === 'function';

process.stdout.write(JSON.stringify(out));
"""


@pytest.fixture(scope='module')
def deck_sonuc(tmp_path_factory):
    if NODE is None:
        pytest.skip('node kurulu değil')
    tmp = tmp_path_factory.mktemp('deck')
    harness = tmp / 'deck.js'
    harness.write_text(DECK_HARNESS, encoding='utf-8')
    proc = subprocess.run([NODE, str(harness), str(STATIC_JS)],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, 'güverte düzeneği düştü:\n%s' % proc.stderr
    assert proc.stdout.strip(), 'güverte düzeneği çıktı üretmedi:\n%s' % proc.stderr
    return json.loads(proc.stdout)


#: TR kipinde güvertede GÖRÜNMEMESİ gereken İngilizce metinler. Hepsi
#: 2026-08-03 öncesinde sabit kodluydu (deckHtml + onTick).
DECK_EN_KALINTILARI = (
    'Cutaway', 'Dimensions', 'Exhaust', 'Exploded', 'Heat Map',
    'Design Mode', 'Orbit', 'Reset View', 'STANDBY', 'MOTOR SIMULATION',
    'Web Remaining', 'GEOMETRY PREVIEW', 'WALL HEAT FLUX',
)


@needs_node
def test_guverte_en_kipinde_ingilizce(deck_sonuc):
    """Karşı kontrol: EN kipinde metinler İngilizce KALMALI."""
    en = deck_sonuc['en']
    for metin in DECK_EN_KALINTILARI:
        assert metin in en, \
            'EN kipinde güverte metni kayboldu: %r (çeviri katmanı EN yolunu bozdu)' % metin


@needs_node
def test_guverte_tr_kipinde_ingilizce_kalinti_birakmiyor(deck_sonuc):
    """TR kipinde güvertede sabit İngilizce metin kalmamalı."""
    tr = deck_sonuc['tr']
    kalan = [m for m in DECK_EN_KALINTILARI if m in tr]
    assert not kalan, (
        '3B güverte TR kipinde İngilizce kalıntı taşıyor: %s\n'
        'Metni TX() üstünden geçirin ve i18n_charts.js sözlüğüne ekleyin.'
        % kalan
    )


@needs_node
def test_guverte_tr_kipinde_turkce_metin_basiyor(deck_sonuc):
    """Kalıntı yokluğu yetmez — yerine Türkçesi yazılmış olmalı."""
    tr = deck_sonuc['tr']
    for beklenen in ('Kesit', 'Egzoz', 'Isı haritası', 'Görünümü sıfırla',
                     'BEKLEMEDE', 'MOTOR BENZETİMİ', 'Kalan web'):
        assert beklenen in tr, 'güvertede beklenen Türkçe metin yok: %r' % beklenen


@needs_node
def test_guverte_dil_degisiminde_tazeleniyor(deck_sonuc):
    """EN'de kurulan güverte, dil TR'ye dönünce metinlerini yenilemeli.

    Kanca olmazsa ekrandaki güverte ilk yüklenen dilde DONAR; kullanıcı
    dili değiştirir, grafikler Türkçeye döner, 3B panel İngilizce kalır.
    """
    assert deck_sonuc['hasRefresh'], \
        'güverte refreshLabels yeteneğini dışa açmıyor'
    assert deck_sonuc['swapBefore'] != 'Kesit', \
        'karşı kontrol bozuk: dil değişmeden metin zaten Türkçeydi'
    assert deck_sonuc['swapAfter'] == 'Kesit', (
        'dil değişince güverte düğmesi tazelenmedi (şu an %r) — '
        'I18N.onChange kancası bağlı değil' % deck_sonuc['swapAfter']
    )


# ---------------------------------------------------------------------------
# 4. experiment_db.py — küratör mesajlarının Türkçe imlası
# ---------------------------------------------------------------------------
#: ASCII'ye kaçmış Türkçe kökler. Bu köklerle BAŞLAYAN bir sözcük, Türkçe
#: karakterin düşürüldüğü anlamına gelir ('olmali' <- 'olmalı').
ASCII_TR_KOKLERI = re.compile(
    r'^(olmali|bos|gecerli|gecersiz|sayi|kayit|icin|icinde|dongusel|tum|'
    r'esit|egri|kunye|aciklama|buyukluk|olculen|olculmemis|yazilmaz|'
    r'kullanilmaz|sozluk|sema|dogrula|basarisiz|bicimli|elemanli|'
    r'uzunluklari|varsayilan|olusan|ozetleyen|kaynagin|sayisallastirma|'
    r'bayragi|tanimli|yalnizca|kayitli|baglanabilir|hic|ayni|sonuc|'
    r'gecemedi|yukleme|kurali|kurallarina|kaydi|dondur|duzey|yazim|'
    r'hatasi|korumasi|disi|bekcisi|degerler|degil)')


def _experiment_db_mesajlari():
    """Şema doğrulayıcısını bozuk kayıtlarla çalıştırıp mesaj toplar."""
    from hrma.validation import experiment_db

    kayitlar = [
        'metin değil sözlük olmalıydı',
        {},
        {'bilinmeyen_alan': 1, 'test_id': '', 'motor_type': 'yok',
         'record_type': 'yok', 'schema_version': '0.0',
         'source': 'obje değil', 'propellants': {}, 'geometry': 5,
         'inputs': {}, 'measured': {}, 'measurement_uncertainty': 3,
         'anomaly': 7, 'units_original': 9, 'digitized': 'evet',
         'synthetic': 'hayır', 'tags': [''], 'notes': 4},
        {'inputs': {'chamber_pressure': 1.0}, 'measured': {'chamber_pressure': 2.0}},
        {'measured': {'thrust': {'time_s': [1], 'value': 'liste değil', 'fazla': 1}}},
        {'source': {'citation': '', 'access': 'yok', 'confidence': 'yok',
                    'date_checked': 'dün', 'url': '', 'doi': 5,
                    'data_extraction': 'yok', 'bilinmeyen': 1}},
    ]
    mesajlar = []
    for kayit in kayitlar:
        mesajlar.extend(experiment_db.validate_record(kayit))
    return mesajlar


def test_experiment_db_mesajlari_duzgun_turkce():
    """Küratör hata mesajlarında ASCII'ye kaçmış Türkçe kalmamalı.

    Mesajlar HTTP yüzeyine SIZMIYOR (2026-08-03'te ölçüldü:
    /api/correlation-report yanıtında bu metinlerden iz yok), bu yüzden
    çeviri değil İMLA sorunudur — tek dil, doğru harflerle.
    """
    mesajlar = _experiment_db_mesajlari()
    assert len(mesajlar) >= 20, \
        'doğrulayıcı yeterli mesaj üretmedi (%d) — kurgu bozulmuş olabilir' % len(mesajlar)

    kacislar = []
    for mesaj in mesajlar:
        for sozcuk in re.findall(r'[A-Za-zÇĞİÖŞÜçğıöşü]+', mesaj):
            if len(sozcuk) > 1 and sozcuk.isupper():
                continue                       # 'YAZILMAZ' meşru büyük harf
            if ASCII_TR_KOKLERI.match(sozcuk.lower()):
                kacislar.append('%r (şüpheli: %r)' % (mesaj, sozcuk))
    assert not kacislar, (
        'experiment_db.py mesajlarında Türkçe karakter kaybı:\n  '
        + '\n  '.join(sorted(set(kacislar)))
    )


def test_experiment_db_mesajlari_tek_dilde():
    """Mesajlar Türkçe; alan adları (İngilizce şema anahtarları) hariç.

    Yarı Türkçe yarı İngilizce mesaj küratöre hangi dilde arama yapacağını
    bildirmez. Alan adresleri ('source.confidence: ...') şema anahtarıdır,
    çevrilmez ve bu testin dışındadır.
    """
    mesajlar = _experiment_db_mesajlari()
    turkce_isaret = re.compile(r'[çğıöşüÇĞİÖŞÜ]')
    dilsiz = [m for m in mesajlar if not turkce_isaret.search(m)]
    # Yalnız alan adı + değer listesi içeren mesajlar (ör. "zorunlu alan
    # eksik: 'x'") Türkçe karakter içermeyebilir; bunlar meşrudur.
    supheli = [m for m in dilsiz
               if not re.match(r'^[\w.]+: ', m) and 'zorunlu alan eksik' not in m]
    assert not supheli, (
        'Türkçe karakteri hiç olmayan şüpheli mesaj:\n  ' + '\n  '.join(supheli)
    )
