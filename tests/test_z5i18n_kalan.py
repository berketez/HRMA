"""OH-Z4-04 — Z4-B'nin MAKİNE-YOLU kaçışıyla bıraktığı hüküm metinleri.

Bu dosya Z5S i18n dalgasının KALAN kalemini kilitler. Kalem iki ayaklıydı:

  1. ANAHTAR AYAĞI — ``panel.structural.*`` ailesinden beş kullanıcı cümlesi
     sözlüğe hiç girmemişti. Z5 i18n süpürmesi onları açamamıştı çünkü
     ``tests/test_i18n_common.py::test_every_dictionary_key_is_used``
     tüketicisi olmayan anahtarı ölü çeviri sayıp KIRMIZI veriyor; anahtar
     ve çağrı yeri aynı commit'te inmek zorunda, çağrı yeri ise başka bir
     ajanın dosyasındaydı (``panels/structural_panel.js``).
  2. SUNUCU CÜMLESİ AYAĞI — "kanal var, kapı yok". Süpürme
     ``structural_analysis.py``nin DÖRT ``minimum_safety_factor_verdict_basis``
     dalını ``i18n_charts.js`` MSG_PATTERNS'e yazmıştı, ama panel ve app.js
     o metni HAM basıyordu; kurallar ekrana hiç ulaşmıyordu.

ÖLÇÜLEN TABAN (97881a0, gerçek uç + gerçek panel, iki dilde çizim —
``docs/scofield/raw/OH/Z5S/i18nkalan/once/olcum.txt``):
  · beş cümlenin İngilizcesi de Türkçesi de ekranda YOK (10/10 eksik),
  · manşet satırının etiketi ``Safety Factor`` (kardeşi "Minimum SF (all
    modes)" iken kazanılmış minimumun kendi adı yok),
  · TÜRKÇE kipte sunucunun gerekçe cümlesi İNGİLİZCE kalıyor (dört dalın
    hangisi düşerse düşsün: ``basisEN_*`` var, ``basisTR_*`` yok) —
    panelde de app.js hüküm şeridinde de.

ONARIM SONRASI (``…/sonra/olcum.txt``): beş cümle iki dilde de yerinde,
sunucu gerekçesi Türkçe kipte Türkçe, ve MAKİNE ADLARI (alan adresleri)
aynen duruyor — onlar bilinçli kaçıştır, çevrilmezler.

Bekçinin ölçtükleri kopya değil ÜRÜNÜN KENDİSİdir: ``structural_panel.js``
sahte DOM'da gerçekten çizilir, ``app.js``in hüküm şeridi gerçekten
çağrılır, i18n yığını (i18n.js + i18n_common.js + i18n_charts.js) gerçekten
yüklenir. Mutasyonlar ürün dosyasına DEĞİL, statik ağacın geçici bir
KOPYASINA uygulanır (depo hiç kirlenmez).
"""

import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import warnings
from pathlib import Path

import pytest

warnings.filterwarnings('ignore')

KOK = Path(__file__).resolve().parents[1]
STATIK = KOK / 'hrma' / 'static' / 'js'
PANEL = STATIK / 'panels' / 'structural_panel.js'
APPJS = STATIK / 'app.js'
SOZLUK = STATIK / 'i18n_common.js'
NODE = shutil.which('node')

pytestmark = pytest.mark.filterwarnings('ignore::RuntimeWarning')

# ---------------------------------------------------------------------------
# Kalemin kendisi — beş anahtar, iki dil, TEK tanım
# ---------------------------------------------------------------------------
#: OH-Z4-04'ün açtığı anahtarlar: anahtar -> (EN, TR).
#: Bu tablo bekçinin TEK doğruluk kaynağıdır; sözlük, panel ve ekran
#: ölçümlerinin hepsi buradan sürülür (parametre tutarlılığı kuralı).
Z5K_ANAHTARLAR = {
    'panel.structural.sfMinEarned': (
        'Minimum SF (earned)',
        'Asgari EK (kazanılmış)'),
    'panel.structural.sfTargetReadback': (
        'This safety factor reads the design target back — it was not '
        'measured on a wall you supplied.',
        'Bu emniyet katsayısı tasarım hedefini geri okuyor — sizin '
        'verdiğiniz bir cidar üstünde ölçülmedi.'),
    'panel.structural.wallNotApplied': (
        'Wall thickness suggestion withheld — not applied',
        'Cidar kalınlığı önerisi geri çekildi — uygulanmadı'),
    'panel.structural.scopeIncomplete': (
        'Verification scope is incomplete: some stations in the basket were '
        'not verified.',
        'Doğrulama kapsamı eksik: sepetteki bazı istasyonlar doğrulanmadı.'),
    'panel.structural.runMotorSolve': (
        'No motor result on this page yet — run the motor calculation first.',
        'Bu sayfada henüz motor sonucu yok — önce motor hesabını '
        'çalıştırın.'),
}

#: AÇILMAYAN altıncı metin. Tüketicisi ölçülerek yok bulundu: panelin
#: ``render()``i ancak panel KOŞTUKTAN sonra çağrılır, app.js hüküm şeridi
#: ise güverte panelinin koşup koşmadığını bilmez. Tüketicisiz anahtar ölü
#: çeviridir — uydurma çağrı yeri açmak yerine anahtar açılmadı.
Z5K_ACILMAYAN = 'panel.structural.runPanel'

#: BİLİNÇLİ MAKİNE YOLU: bunlar alan ADRESİdir, kullanıcı metni değil ve
#: ANAHTARA ÇEVRİLMEZ. Z4-B'nin kaçış kapısı; ekrandan düşerlerse kullanıcı
#: sayının hangi alandan geldiğini bir daha göremez.
Z5K_MAKINE_ADLARI = (
    'stations_reading_back_target',
    'wall_thickness_suggestion',
    'verification_scope_complete',
    'stations_not_verified',
    'design_target_assessment',
    'minimum_earned_safety_factor',
)

#: Sunucunun DÖRT gerekçe dalı (structural_analysis.py:2057-2084). Ekranda
#: Türkçe kipte bunların İNGİLİZCESİ görünmemeli.
Z5K_BASIS_EN = (
    'No acceptance is issued and no verdict is issued at all',
    'No acceptance is issued: the measured sections',
    'The verdict comes from verdict_safety_factor',
    'Every station in the basket was evaluated against a user-supplied',
)
#: Aynı dört dalın Türkçe karşılıklarından çapa parçaları (i18n_charts.js).
Z5K_BASIS_TR = (
    'Ne onay ne de hüküm verildi',
    'Onay verilmedi: ölçülen kesitler',
    'Hüküm verdict_safety_factor alanından geliyor',
    'Sepetteki her istasyon kullanıcının verdiği bir kalınlığa karşı',
)

# ---------------------------------------------------------------------------
# İstekler — bu dosyanın TEK tanımı
# ---------------------------------------------------------------------------
Z5K_HIBRIT = {'motor_name': 'z5k-h', 'fuel_type': 'htpb',
              'oxidizer_type': 'n2o', 'thrust': 2000, 'burn_time': 10,
              'chamber_pressure': 30, 'of_ratio': 6.0}
#: Cidar alanı YOK -> HRMA kendi boyutlandırır (design_mode: size)
Z5K_PANEL_SIZE = {'chamber_pressure': 30, 'chamber_diameter': 0.101,
                  'chamber_length': 0.6, 'throat_diameter': 0.0243,
                  'burn_time': 10, 'material': 'steel_4130', 'thrust': 2000}
#: Kullanıcının İNCE cidarı -> hüküm gerçekten kazanılır
Z5K_PANEL_INCE = dict(Z5K_PANEL_SIZE, wall_thickness=0.002)
#: Kalın cidar -> hedef geri okuması baskın
Z5K_PANEL_KALIN = dict(Z5K_PANEL_SIZE, wall_thickness=0.015)


def _sessiz(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        return fn(*a, **kw)


def _oku(path):
    return path.read_text(encoding='utf-8')


def _js_yorumsuz(text):
    """JS yorumlarını aynı uzunlukta boşluğa çevirir (ofsetler korunur).

    Bekçi YORUMDA geçen anahtarı "tüketici" sayarsa kendini kandırır:
    OH-Z4-04'ün tam da devrettiği yol buydu (metinler yorumda duruyordu).
    """
    def blank(m):
        return re.sub(r'[^\n]', ' ', m.group(0))

    text = re.sub(r'/\*.*?\*/', blank, text, flags=re.S)
    out = []
    for line in text.split('\n'):
        quote = None
        cut = None
        i = 0
        while i < len(line):
            ch = line[i]
            if quote:
                if ch == '\\':
                    i += 2
                    continue
                if ch == quote:
                    quote = None
            else:
                if ch in '\'"`':
                    quote = ch
                elif ch == '/' and i + 1 < len(line) and line[i + 1] == '/':
                    cut = i
                    break
            i += 1
        out.append(line if cut is None else line[:cut] + ' ' * (len(line) - cut))
    return '\n'.join(out)


def _sozluk(path, lang):
    """i18n_common.js'in bir dil bloğunu (anahtar -> değer) okur."""
    src = _oku(path)
    start = src.index('        %s: {' % lang)
    depth = 0
    body = None
    for idx in range(start + len('        %s: ' % lang), len(src)):
        if src[idx] == '{':
            depth += 1
        elif src[idx] == '}':
            depth -= 1
            if depth == 0:
                body = src[start:idx]
                break
    assert body is not None, "i18n_common.js '%s' bloğu kapanmıyor" % lang
    pairs = re.findall(r"^\s*'((?:[^'\\]|\\.)*)':\s*'((?:[^'\\]|\\.)*)',?\s*$",
                       body, re.M)
    return {k.replace("\\'", "'"): v.replace("\\'", "'") for k, v in pairs}


EN = _sozluk(SOZLUK, 'en')
TR = _sozluk(SOZLUK, 'tr')


# ===========================================================================
# 1. SÖZLÜK AYAĞI
# ===========================================================================
@pytest.mark.parametrize('anahtar', sorted(Z5K_ANAHTARLAR))
def test_anahtar_iki_dilde_ve_tam_metniyle_var(anahtar):
    """Beş anahtar EN ve TR bloklarında, birebir devredilen metinlerle."""
    ing, tur = Z5K_ANAHTARLAR[anahtar]
    assert anahtar in EN, (
        '%s EN sözlüğünde yok — OH-Z4-04 anahtar ayağı geri gitti' % anahtar)
    assert anahtar in TR, '%s TR sözlüğünde yok' % anahtar
    assert EN[anahtar] == ing, (
        '%s EN değeri devredilen metinden ayrıştı:\n  var : %r\n  olmalı: %r'
        % (anahtar, EN[anahtar], ing))
    assert TR[anahtar] == tur, (
        '%s TR değeri devredilen metinden ayrıştı:\n  var : %r\n  olmalı: %r'
        % (anahtar, TR[anahtar], tur))
    assert EN[anahtar] != TR[anahtar], '%s çevrilmemiş' % anahtar


def test_turkce_karsiliklar_urun_terim_kanonuna_uyuyor():
    """TR metinler ürünün kendi kanonunu kullanmalı (Z5 süpürmesi ölçtü).

    Kanon uydurma değildir: emniyet katsayısı 51⟷güvenlik katsayısı 2,
    cidar kalınlığı 37⟷duvar kalınlığı 2 (raw/OH/Z5/i18n/01). Yeni anahtar
    eski terime kayarsa süpürmenin kazancı sessizce delinir.
    """
    yasak = {'güvenlik katsayı': 'emniyet katsayı',
             'duvar kalınlığ': 'cidar kalınlığ',
             'lüle': 'nozul'}
    hatalar = []
    for anahtar in Z5K_ANAHTARLAR:
        alt = TR[anahtar].lower().replace('İ', 'i')
        for kotu, iyi in yasak.items():
            if kotu in alt:
                hatalar.append('%s: %r içinde %r var (kanon: %r)'
                               % (anahtar, TR[anahtar], kotu, iyi))
    assert not hatalar, 'Terim kanonu ihlali:\n  ' + '\n  '.join(hatalar)


def test_ingilizce_blokta_turkce_harf_yok():
    """Yeni anahtarların EN değeri gerçekten İngilizce olmalı."""
    turkce = re.compile(r'[çğıİöşüÇĞÖŞÜ]')
    kaymis = sorted(k for k in Z5K_ANAHTARLAR if turkce.search(EN[k]))
    assert not kaymis, 'EN bloğuna Türkçe metin sızmış: %s' % kaymis


def test_runpanel_acilmadi_ve_gerekcesi_dosyada_yazili():
    """Altıncı metin AÇILMADI; kararın gerekçesi dosyada durmalı.

    Bu bir "yapılmadı" imi değil, ÖLÇÜLMÜŞ bir karardır: tüketicisi yok.
    Gerekçe silinirse birileri anahtarı tüketicisiz açar ve ölü-çeviri
    bekçisi kırmızı verir; bu bekçi o turu bir adım öne alır.
    """
    assert Z5K_ACILMAYAN not in EN and Z5K_ACILMAYAN not in TR, (
        '%s sözlüğe girmiş — tüketicisi var mı? Yoksa '
        'test_every_dictionary_key_is_used da kırmızı verecek. Tüketici '
        'eklendiyse bu bekçiyi ve i18n_common.js notunu güncelleyin.'
        % Z5K_ACILMAYAN)
    src = _oku(SOZLUK)
    assert 'runPanel' in src and 'OH-Z4-04' in src, (
        'i18n_common.js OH-Z4-04 notunu / runPanel gerekçesini kaybetmiş — '
        'karar kayıtsız kaldı')
    # Gerekçe GERÇEKTEN gerekçe mi: kararın dayanağı adıyla yazılı olmalı.
    for capa in ('tüketicisi', 'render'):
        assert capa in src, (
            'runPanel gerekçesi %r sözcüğünü taşımıyor — not, kararın '
            'dayanağını değil yalnız sonucunu yazıyor' % capa)


def test_sozluk_basligi_olcmedigi_kapsami_iddia_etmiyor():
    """i18n_common.js başlığı ölçülmemiş bir kapsam iddia edemez.

    Z5 i18n süpürmesinin kendi risk notu (madde 6): "i18n_common.js başlığı
    da 'Ana sayfa dışındaki JS katmanının TÜM kullanıcı metinleri' diyor —
    P12aB2-06'nın aynısı, başka dosyada." P12aB2-06 ÖLÇÜLDÜĞÜNDE iddia
    yanlış çıkmıştı (12 bağlanmamış metin). Başlık artık yalnız BEKÇİLERİN
    ölçtüğünü söylüyor; iddia geri gelirse burası kırmızı verir.
    """
    bas = _oku(SOZLUK)[:4000]
    yasak = re.search(r'(?:t[üu]m|b[üu]t[üu]n)\s+kullanıcı metinleri',
                      bas, re.I)
    assert not yasak, (
        'Başlık yine ölçülmemiş bir kapsam iddia ediyor: %r — iddia '
        'edilecekse ÖNCE ölçülmeli (P12aB2-06 deseni).' % yasak.group(0))
    for capa in ('GARANTİ EDİLMEZ', 'test_every_dictionary_key_is_used',
                 'test_every_used_key_exists_in_dictionary'):
        assert capa in bas, (
            'Başlık %r bölümünü kaybetmiş — "ne garanti edilir, ne edilmez" '
            'ayrımı olmadan kapsam yine belirsiz kalır' % capa)
    # Adlandırılmış borç, GERÇEK bekçinin listesiyle aynı olmalı.
    borc = re.search(r'CEVIRI_BORCU_AILELERI = \((.*?)\)',
                     _oku(KOK / 'tests' / 'test_i18n_common.py'), re.S)
    assert borc, 'test_i18n_common.py CEVIRI_BORCU_AILELERI bulunamadı'
    for aile in re.findall(r"'([^']+)'", borc.group(1)):
        assert aile in bas, (
            'Başlık adlandırılmış borcu eksik yazıyor: %r bekçide var, '
            'başlıkta yok' % aile)


# ===========================================================================
# 2. TÜKETİCİ AYAĞI — anahtarın ÇAĞRI YERİ gerçekten var mı
# ===========================================================================
@pytest.mark.parametrize('anahtar', sorted(Z5K_ANAHTARLAR))
def test_anahtarin_tuketicisi_panelde_ve_yorumda_degil(anahtar):
    """Her anahtar ``T('anahtar', …)`` olarak panelde çağrılmalı.

    Yorum satırları ELENİR: OH-Z4-04'ün devrettiği hâlde metinler yorumda
    duruyordu ve o "tüketici" değildir.
    """
    src = _js_yorumsuz(_oku(PANEL))
    desen = re.compile(r"\bT\(\s*'%s'\s*," % re.escape(anahtar))
    assert desen.search(src), (
        "%s panels/structural_panel.js içinde T() ile çağrılmıyor "
        '(yorumda geçmesi sayılmaz)' % anahtar)


def test_makine_adlari_hala_ekrana_basiliyor():
    """Alan ADRESLERİ anahtara çevrilmedi — kaçış kapısı korunuyor."""
    src = _js_yorumsuz(_oku(PANEL))
    kayip = [ad for ad in Z5K_MAKINE_ADLARI if ad not in src]
    assert not kayip, (
        'Makine adı panelden düşmüş: %s — kullanıcı sayının hangi alandan '
        'geldiğini bir daha göremez (Z4-B kaçış kapısı)' % kayip)


# ===========================================================================
# 3. SUNUCU CÜMLESİ AYAĞI — "kanal var, kapı yok" kapandı mı
# ===========================================================================
def test_panel_sunucu_metnini_ceviri_kanalindan_geciriyor():
    """Panel serbest sunucu metnini SRV()'den geçirmeli, ham basmamalı."""
    src = _js_yorumsuz(_oku(PANEL))
    assert re.search(r'function SRV\s*\(', src), (
        'structural_panel.js SRV yardımcısını tanımlamıyor — sunucu '
        'cümleleri çeviri kanalına hiç girmiyor')
    ham = []
    for capa in (r'\$\{db\.message\}', r'\$\{basis\}', r'\$\{note\}',
                 r'\$\{buck\.source\}'):
        if re.search(capa, src):
            ham.append(capa)
    assert not ham, (
        'Sunucu metni HAM basılıyor (Türkçe kipte İngilizce kalır): %s' % ham)


def test_appjs_hukum_seridi_ceviri_kanalindan_geciyor():
    """app.js yapısal hüküm şeridi gerekçe cümlesini SRV'den geçirmeli."""
    src = _js_yorumsuz(_oku(APPJS))
    assert 'hdEscape(SRV(t))' in src, (
        'app.js hüküm şeridi gerekçeyi ham basıyor — Z5 süpürmesinin dört '
        'MSG_PATTERNS kuralı bu ekranda ölü kalır')
    # Tekilleştirme HAM metin üstünden yapılmalı: çeviri iki ayrı İngilizce
    # cümleyi aynı Türkçeye indirebilir, o zaman indexOf yanlış eler.
    i = src.index('const gerekce = [];')
    blok = src[i:i + 900]
    assert 'SRV(' not in blok, (
        'gerekçe listesi ÇEVİRİDEN SONRA kuruluyor — tekilleştirme ham '
        'metin üstünden yapılmalı')


# ===========================================================================
# 4. EKRAN AYAĞI — gerçek panel, gerçek i18n, iki dil
# ===========================================================================
HARNESS = r"""
'use strict';
const fs = require('fs'); const path = require('path'); const vm = require('vm');
function El(tag) {
    this.tagName = String(tag || 'div').toUpperCase();
    this.children = []; this.style = {}; this._a = {};
    this.innerHTML = ''; this.dataset = {}; this.id = '';
}
El.prototype.appendChild = function (x) { this.children.push(x); return x; };
El.prototype.setAttribute = function (k, v) { this._a[k] = String(v); };
El.prototype.getAttribute = function (k) {
    return Object.prototype.hasOwnProperty.call(this._a, k) ? this._a[k] : null; };
El.prototype.querySelectorAll = function () { return []; };
El.prototype.addEventListener = function () {};
function kurSandbox() {
    const depo = {};
    const doc = {
        head: new El('head'), body: new El('body'), readyState: 'complete',
        documentElement: new El('html'),
        createElement: function (t) { return new El(t); },
        querySelector: function () { return null; },
        querySelectorAll: function () { return []; },
        getElementById: function () { return null; },
        addEventListener: function () {},
    };
    const sb = {
        console: { log: function () {}, warn: function () {},
                   error: function () {} },
        setTimeout: setTimeout, clearTimeout: clearTimeout,
        setInterval: function () {}, clearInterval: clearInterval,
        fetch: function () { return Promise.reject(new Error('ag yok')); },
        JSON: JSON, Math: Math, Number: Number, Array: Array, Object: Object,
        String: String, Boolean: Boolean, RegExp: RegExp, Date: Date,
        isFinite: isFinite, parseFloat: parseFloat, parseInt: parseInt,
        alert: function () {}, document: doc,
        localStorage: {
            getItem: function (k) { return (k in depo) ? depo[k] : null; },
            setItem: function (k, v) { depo[k] = String(v); },
            removeItem: function (k) { delete depo[k]; },
        },
        navigator: { language: 'en-US' },
    };
    sb.window = sb; sb.globalThis = sb;
    vm.createContext(sb);
    return sb;
}
function kos(sb, f) {
    vm.runInContext(fs.readFileSync(f, 'utf8'), sb, { filename: f }); }

const [staticDir, girdiYolu] = process.argv.slice(2);
const P = JSON.parse(fs.readFileSync(girdiYolu, 'utf8'));
const sb = kurSandbox();
kos(sb, path.join(staticDir, 'i18n.js'));
kos(sb, path.join(staticDir, 'i18n_common.js'));
kos(sb, path.join(staticDir, 'i18n_charts.js'));
kos(sb, path.join(staticDir, 'analysis_dock.js'));
kos(sb, path.join(staticDir, 'panels', 'structural_panel.js'));
kos(sb, path.join(staticDir, 'app.js'));
try {
    sb.window.AnalysisDock.init({ motorType: 'hybrid',
        resultsProvider: function () { return P.motor; } });
} catch (e) { /* gercek DOM yok; kayit yine kuruldu */ }
const spec = sb.window.AnalysisDock._registry.filter(function (s) {
    return s.id === 'structural'; })[0];
function ciz(motorRes, panelYanit) {
    spec.fromResults(motorRes);
    const kok = new El('div');
    sb.window.StructuralPanel._render(panelYanit, kok);
    return kok.innerHTML || kok.children.map(function (x) {
        return x.innerHTML; }).join('');
}
const OUT = { serit: {} };
['en', 'tr'].forEach(function (dil) {
    sb.window.I18N.setLang(dil);
    const md = (P.motor && P.motor.motor) ? P.motor.motor : P.motor;
    OUT.serit[dil] = sb.structuralVerdictBlock(md, P.motor) || '';
});
(P.vakalar || []).forEach(function (v) {
    OUT[v.ad] = {};
    ['en', 'tr'].forEach(function (dil) {
        sb.window.I18N.setLang(dil);
        OUT[v.ad][dil] = ciz(v.motor || {}, v.panel);
    });
});
process.stdout.write(JSON.stringify(OUT));
"""


def _node_ciz(static_dir, girdi):
    with tempfile.TemporaryDirectory() as tmp:
        betik = os.path.join(tmp, 'kos.js')
        with open(betik, 'w', encoding='utf-8') as fh:
            fh.write(HARNESS)
        veri = os.path.join(tmp, 'girdi.json')
        with open(veri, 'w', encoding='utf-8') as fh:
            json.dump(girdi, fh)
        proc = subprocess.run([NODE, betik, str(static_dir), veri],
                              capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, 'node çöktü:\n' + proc.stderr[-3000:]
    return json.loads(proc.stdout.strip().splitlines()[-1])


@pytest.fixture(scope='module')
def yanitlar():
    """Gerçek uç koşumları: bir motor + üç cidar dalı."""
    from hrma.app import app
    app.config['TESTING'] = True
    out = {}
    with app.test_client() as c:
        r = _sessiz(c.post, '/calculate', json=Z5K_HIBRIT)
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        out['motor'] = r.get_json()
        for ad, istek in (('size', Z5K_PANEL_SIZE), ('ince', Z5K_PANEL_INCE),
                          ('kalin', Z5K_PANEL_KALIN)):
            p = _sessiz(c.post, '/analyze_structural_safety', json=istek)
            assert p.status_code == 200, p.get_data(as_text=True)[:300]
            out[ad] = p.get_json()
    return out


def _girdi(yanitlar):
    return {'motor': yanitlar['motor'], 'vakalar': [
        {'ad': 'size_motorlu', 'motor': yanitlar['motor'],
         'panel': yanitlar['size']},
        {'ad': 'ince_motorlu', 'motor': yanitlar['motor'],
         'panel': yanitlar['ince']},
        {'ad': 'kalin_motorlu', 'motor': yanitlar['motor'],
         'panel': yanitlar['kalin']},
        {'ad': 'kalin_motorsuz', 'motor': {}, 'panel': yanitlar['kalin']},
    ]}


@pytest.fixture(scope='module')
def ekran(yanitlar):
    if not NODE:
        pytest.skip('node bulunamadı')
    return _node_ciz(STATIK, _girdi(yanitlar))


#: Hangi vakada hangi anahtarın ekranda olması BEKLENİYOR (ölçüldü —
#: raw/OH/Z5S/i18nkalan/sonra/olcum.txt). Beklenti vakaya özgüdür:
#: ``runMotorSolve`` YALNIZ motor koşumu olmayan dalda basılır.
Z5K_BEKLENEN = {
    'size_motorlu': ('panel.structural.sfMinEarned',
                     'panel.structural.sfTargetReadback',
                     'panel.structural.wallNotApplied',
                     'panel.structural.scopeIncomplete'),
    'ince_motorlu': ('panel.structural.sfMinEarned',
                     'panel.structural.sfTargetReadback',
                     'panel.structural.wallNotApplied',
                     'panel.structural.scopeIncomplete'),
    'kalin_motorlu': ('panel.structural.sfMinEarned',
                      'panel.structural.sfTargetReadback',
                      'panel.structural.wallNotApplied',
                      'panel.structural.scopeIncomplete'),
    'kalin_motorsuz': ('panel.structural.sfMinEarned',
                       'panel.structural.sfTargetReadback',
                       'panel.structural.wallNotApplied',
                       'panel.structural.scopeIncomplete',
                       'panel.structural.runMotorSolve'),
}


@pytest.mark.parametrize('vaka', sorted(Z5K_BEKLENEN))
@pytest.mark.parametrize('dil', ['en', 'tr'])
def test_bes_cumle_ekranda_dogru_dilde(ekran, vaka, dil):
    """Anahtarlar ekrana İNİYOR ve dil değişince Türkçeleşiyor."""
    html = ekran[vaka][dil]
    eksik = []
    for anahtar in Z5K_BEKLENEN[vaka]:
        metin = Z5K_ANAHTARLAR[anahtar][0 if dil == 'en' else 1]
        if metin not in html:
            eksik.append(anahtar)
    assert not eksik, (
        '%s / %s: şu cümleler ekranda yok: %s' % (vaka, dil, eksik))
    # Ters yön: karşı dilin metni ekranda OLMAMALI (dil karışması).
    karsi = []
    for anahtar in Z5K_BEKLENEN[vaka]:
        oteki = Z5K_ANAHTARLAR[anahtar][1 if dil == 'en' else 0]
        if oteki in html:
            karsi.append(anahtar)
    assert not karsi, (
        '%s / %s: karşı dilin metni de ekranda: %s' % (vaka, dil, karsi))


def test_run_motor_solve_yalniz_motorsuz_dalda_ve_uc_adi_uydurulmadan(ekran):
    """Fail-closed sözleşmesi korunuyor: koşum yoksa uç adı BASILMAZ.

    ``tests/test_z5guard_urun_tur.py::
    test_motor_kosumu_yoksa_kiyas_satiri_basilmaz`` motor koşumu yokken
    ``/calculate`` dizesini yasaklıyor. Gerekçe cümlesi o yasağı delmeden
    basılmalı — yoksa "kıyas var" izlenimi doğar.
    """
    metin_en = Z5K_ANAHTARLAR['panel.structural.runMotorSolve'][0]
    for dil in ('en', 'tr'):
        metin = Z5K_ANAHTARLAR['panel.structural.runMotorSolve'][
            0 if dil == 'en' else 1]
        assert metin in ekran['kalin_motorsuz'][dil], (
            'motor koşumu yokken gerekçe basılmıyor (%s)' % dil)
        assert metin not in ekran['kalin_motorlu'][dil], (
            'motor koşumu VARKEN "koşum yok" gerekçesi basılıyor (%s)' % dil)
    assert '/calculate' not in ekran['kalin_motorsuz']['en'], (
        'gerekçe satırı uç adını basıyor — fail-closed sözleşmesi delindi')
    assert '/calculate' in ekran['kalin_motorlu']['en'], (
        'motor koşumu varken kıyas satırı uç adını basmıyor (kıyas kayboldu)')
    assert metin_en  # çapa boş kalmasın


@pytest.mark.parametrize('vaka', sorted(Z5K_BEKLENEN))
def test_makine_adlari_ekranda_duruyor(ekran, vaka):
    """Çeviri, makine adlarını ekrandan SÜPÜRMEDİ."""
    html = ekran[vaka]['tr']
    kayip = [ad for ad in ('stations_reading_back_target',
                           'wall_thickness_suggestion',
                           'verification_scope_complete')
             if ad not in html]
    assert not kayip, (
        '%s: makine adı ekrandan düşmüş: %s' % (vaka, kayip))


@pytest.mark.parametrize('vaka', sorted(Z5K_BEKLENEN))
def test_turkce_kipte_sunucu_gerekcesi_ingilizce_kalmiyor(ekran, vaka):
    """Panelde "kanal var kapı yok" kapandı: TR'de EN gerekçe kalmaz."""
    tr = ekran[vaka]['tr']
    en = ekran[vaka]['en']
    kalan = [c for c in Z5K_BASIS_EN if c in tr]
    assert not kalan, (
        '%s: Türkçe kipte sunucunun İngilizce gerekçesi duruyor: %s'
        % (vaka, kalan))
    # Bekçi boşa koşmasın: İngilizce kipte gerekçenin GERÇEKTEN olduğu,
    # Türkçe kipte de karşılığının basıldığı ölçülür.
    assert any(c in en for c in Z5K_BASIS_EN), (
        '%s: İngilizce kipte hiç gerekçe cümlesi yok — bu koşum kalemin '
        'vakasını üretmiyor, bekçi boşa koşuyor' % vaka)
    assert any(c in tr for c in Z5K_BASIS_TR), (
        '%s: Türkçe karşılık basılmıyor (desen ıskaladı mı?)' % vaka)


def test_appjs_hukum_seridi_ekranda_turkcelesiyor(ekran, yanitlar):
    """app.js hüküm şeridi de aynı kapıdan geçiyor.

    V3 yapi-sf 3. tur Ş2-2 — ÇEVİRİ (karar §28-37 seçenek (a); karar §28-24
    (C); dört koşul). Eski ön koşul: şeritte sunucunun DÖRT eski gerekçe
    dalından biri. (C) ile hibrit kamara yapısal modelin geçerlilik sınırı
    dışında (kâhin: malzeme kaydı ⟷ yayımlanan cidar sıcaklığı) ve sunucu
    BEŞİNCİ dalı (``MODEL_VALIDITY_VERDICT_BASIS``) basıyor. Çapa sunucu
    sabitinin kendisinden doğrulanır; sorunun kendisi (TR kipte sıfır
    İngilizce gerekçe, Türkçe karşılık basılıyor) AYNEN.
    """
    from hrma.analysis.structural_analysis import MODEL_VALIDITY_VERDICT_BASIS
    from tests.test_v3_yapi_sf import malzeme_kaydina_gore_gecerlilik_disi

    c_en = 'No acceptance and no numeric design verdict is issued'
    c_tr = 'Ne onay ne de sayısal tasarım hükmü verildi'
    assert MODEL_VALIDITY_VERDICT_BASIS.startswith(c_en), (
        'çapa sunucunun (C) gerekçe sabitinden kopmuş')
    gerekce_en = Z5K_BASIS_EN + (c_en,)
    gerekce_tr = Z5K_BASIS_TR + (c_tr,)

    en, tr = ekran['serit']['en'], ekran['serit']['tr']
    assert en.strip(), 'hüküm şeridi hiç basılmıyor — bekçi boşa koşuyor'
    assert malzeme_kaydina_gore_gecerlilik_disi(
        yanitlar['motor']['motor']['structural_analysis']) is True
    assert c_en in en, (
        'geçerlilik dışı hibritte şerit (C) gerekçesini basmıyor')
    kalan = [c for c in gerekce_en if c in tr]
    assert not kalan, (
        'app.js hüküm şeridi Türkçe kipte İngilizce gerekçe basıyor: %s'
        % kalan)
    assert any(c in tr for c in gerekce_tr), (
        'app.js hüküm şeridinde Türkçe gerekçe yok')
    assert c_tr in tr, 'şeritte (C) gerekçesinin Türkçesi yok'


# ===========================================================================
# 4b. CİDAR KAPISI GÖVDELERİ — desen ELLE KOPYALANMADI, ÜRETİLDİ
# ===========================================================================
# Z5 i18n süpürmesinin kendi risk notu: "MSG_PATTERNS regexleri sunucunun
# BUGÜNKÜ f-string metinlerine bağlı; bekçinin örnek metinleri de aynı
# kaynaktan ELLE kopyalandı — sunucu metni değişirse İKİSİNİ birden
# güncellemek gerekir." Bu bekçi o riski kapatır: örnek metinler elle
# yazılmaz, ``_classify_wall_thickness_gate`` ÇAĞRILARAK üretilir. Sunucu
# cümlesini değiştiren kişi burada KIRMIZI görür.
SERVERTEXT_HARNESS = r"""
'use strict';
const fs = require('fs'); const path = require('path'); const vm = require('vm');
const [staticDir, girdiYolu] = process.argv.slice(2);
const P = JSON.parse(fs.readFileSync(girdiYolu, 'utf8'));
const depo = {};
const sb = {
    console: { log: function () {}, warn: function () {}, error: function () {} },
    JSON: JSON, Math: Math, Number: Number, Array: Array, Object: Object,
    String: String, Boolean: Boolean, RegExp: RegExp, Date: Date,
    isFinite: isFinite, parseFloat: parseFloat, parseInt: parseInt,
    setTimeout: setTimeout, clearTimeout: clearTimeout,
    document: { readyState: 'complete', addEventListener: function () {},
                querySelectorAll: function () { return []; },
                querySelector: function () { return null; },
                documentElement: { setAttribute: function () {} },
                createElement: function () { return { style: {} }; } },
    localStorage: {
        getItem: function (k) { return (k in depo) ? depo[k] : null; },
        setItem: function (k, v) { depo[k] = String(v); },
        removeItem: function (k) { delete depo[k]; } },
    navigator: { language: 'en-US' },
};
sb.window = sb; sb.globalThis = sb;
vm.createContext(sb);
function kos(f) {
    vm.runInContext(fs.readFileSync(f, 'utf8'), sb, { filename: f }); }
kos(path.join(staticDir, 'i18n.js'));
kos(path.join(staticDir, 'i18n_common.js'));
kos(path.join(staticDir, 'i18n_charts.js'));
const OUT = {};
sb.window.I18N.setLang('tr');
P.metinler.forEach(function (m, i) {
    OUT[i] = sb.window.I18N.serverText(m);
});
process.stdout.write(JSON.stringify(OUT));
"""


@pytest.fixture(scope='module')
def kapi_govdeleri():
    """``_classify_wall_thickness_gate``in ÜRETTİĞİ dört gövde (+alt dallar)."""
    from hrma import app as appmod
    g = appmod._classify_wall_thickness_gate
    vakalar = [
        ('sized', (None, 0.0159, appmod.WALL_INPUT_NOT_SUPPLIED, 'm')),
        ('user', (0.0159, 0.0159, appmod.WALL_INPUT_OK, 'm')),
        ('unreadable', (None, 0.0159, appmod.WALL_INPUT_UNREADABLE, 'm')),
        ('not_positive', (None, 0.0159, appmod.WALL_INPUT_NOT_POSITIVE, 'm')),
        ('not_finite', (None, 0.0159, appmod.WALL_INPUT_NOT_FINITE, 'm')),
        ('bilinmeyen', (None, 0.0159, 'baska_bir_durum', 'm')),
        ('farkli', (0.005, 0.0159, appmod.WALL_INPUT_OK, 'm')),
    ]
    return {ad: _sessiz(g, *args)['message'] for ad, args in vakalar}


@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
def test_cidar_kapisinin_her_govdesi_turkceye_geciyor(kapi_govdeleri):
    """Yedi gövdenin yedisi de Türkçe kipte Türkçeleşmeli."""
    adlar = sorted(kapi_govdeleri)
    metinler = [kapi_govdeleri[a] for a in adlar]
    with tempfile.TemporaryDirectory() as tmp:
        betik = os.path.join(tmp, 'srv.js')
        with open(betik, 'w', encoding='utf-8') as fh:
            fh.write(SERVERTEXT_HARNESS)
        veri = os.path.join(tmp, 'girdi.json')
        with open(veri, 'w', encoding='utf-8') as fh:
            json.dump({'metinler': metinler}, fh)
        proc = subprocess.run([NODE, betik, str(STATIK), veri],
                              capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, 'node çöktü:\n' + proc.stderr[-3000:]
    cikti = json.loads(proc.stdout.strip().splitlines()[-1])
    kalan = []
    for i, ad in enumerate(adlar):
        tr = cikti[str(i)]
        if tr == metinler[i]:
            kalan.append('%s: %r' % (ad, metinler[i][:90]))
    assert not kalan, (
        'Cidar kapısı gövdesi Türkçe kipte İNGİLİZCE kalıyor (%d/%d) — '
        'sunucu metni mi değişti, desen mi eksik?\n  %s'
        % (len(kalan), len(adlar), '\n  '.join(kalan)))
    # Sayılar çeviride kaybolmamalı: 'farkli' dalı iki kalınlık taşıyor.
    #
    # ÖH D35 / OH-GT-24(d) (22 Eylül 2026) — BEKÇİ ÇEVRİLDİ.
    # Bu satır DEĞERİN kaybolmadığını ölçmek için yazılmıştı ama AYRACI da
    # kilitliyordu: '5.0' dizesi birebir aranıyordu. Türkçe kipte ondalık
    # ayracı VİRGÜLDÜR (tek kaynak: i18n.js `I18N.decimalText`, ÖH D30 /
    # P12aB1-01) ve desen yakalamaları artık o kanondan geçiyor; yani eski
    # biçimiyle bu bekçi tam da onarılan kusuru (aynı ekranda iki ayraç)
    # KORUYORDU. Ölçüt korunur — sayı DÜŞMEYECEK, YENİSİ DOĞMAYACAK —
    # yalnız kabul edilen biçim genişletildi: nokta ya da TR virgül.
    farkli_tr = cikti[str(adlar.index('farkli'))]
    for sayi in re.findall(r'\d+\.\d+', kapi_govdeleri['farkli']):
        assert sayi in farkli_tr or sayi.replace('.', ',') in farkli_tr, (
            'çeviri sayıyı düşürdü: %s (ne nokta ne virgül biçimi var)'
            '\n  %r' % (sayi, farkli_tr))


# ===========================================================================
# 5. MUTASYON — bekçi gerçekten yük taşıyor mu
# ===========================================================================
#: (ad, dosya, aranan, yerine) — statik ağacın KOPYASINA uygulanır.
Z5K_MUTASYONLAR = (
    ('sfMinEarned_anahtari_geri_alinir', 'panels/structural_panel.js',
     "T('panel.structural.sfMinEarned', 'Minimum SF (earned)')",
     "T('common.safetyFactor', 'Safety Factor')"),
    ('SRV_basis_kapisi_kapatilir', 'panels/structural_panel.js',
     '${SRV(basis)}', '${basis}'),
    ('SRV_message_kapisi_kapatilir', 'panels/structural_panel.js',
     '${SRV(db.message)}', '${db.message}'),
    ('scopeIncomplete_cagrisi_silinir', 'panels/structural_panel.js',
     "'panel.structural.scopeIncomplete',", "'panel.structural.YOK',"),
)


@pytest.fixture(scope='module')
def mutant_ekran(yanitlar):
    """Her mutasyon için ayrı bir statik KOPYA çizilir (depo kirlenmez)."""
    if not NODE:
        pytest.skip('node bulunamadı')
    out = {}
    girdi = _girdi(yanitlar)
    with tempfile.TemporaryDirectory() as tmp:
        for ad, dosya, aranan, yerine in Z5K_MUTASYONLAR:
            hedef = Path(tmp) / ad
            shutil.copytree(STATIK, hedef)
            yol = hedef / dosya
            src = yol.read_text(encoding='utf-8')
            assert src.count(aranan) >= 1, (
                'mutasyon çapası ürün dosyasında yok: %r (%s)' % (aranan, ad))
            yol.write_text(src.replace(aranan, yerine, 1), encoding='utf-8')
            out[ad] = _node_ciz(hedef, girdi)
    return out


def test_mutasyon_sfminearned_geri_alininca_eski_etiket_doner(mutant_ekran):
    """Manşet etiketi geri alınırsa yeni cümle ekrandan DÜŞMELİ."""
    html = mutant_ekran['sfMinEarned_anahtari_geri_alinir']['kalin_motorlu']
    assert Z5K_ANAHTARLAR['panel.structural.sfMinEarned'][0] not in html['en'], (
        'anahtar geri alındığı hâlde cümle ekranda — bekçi yük taşımıyor')
    assert Z5K_ANAHTARLAR['panel.structural.sfMinEarned'][1] not in html['tr']


def test_mutasyon_srv_basis_kapisi_kapatilinca_ingilizce_doner(mutant_ekran):
    """Hüküm gerekçesinin kapısı kapatılırsa TR kipte İngilizce geri gelir."""
    tr = mutant_ekran['SRV_basis_kapisi_kapatilir']['size_motorlu']['tr']
    assert any(c in tr for c in Z5K_BASIS_EN), (
        'kapı kapatıldığı hâlde Türkçe kipte İngilizce gerekçe yok — '
        'ölçüm yanlış yeri okuyor olabilir')


def test_mutasyon_srv_message_kapisi_kapatilinca_ingilizce_doner(mutant_ekran):
    """Cidar kapısı gövdesinin kapısı kapatılırsa TR kipte İngilizce döner."""
    tr = mutant_ekran['SRV_message_kapisi_kapatilir']['size_motorlu']['tr']
    assert 'No wall thickness was supplied' in tr, (
        'db.message kapısı kapatıldığı hâlde Türkçe kipte İngilizce gövde '
        'yok — ölçüm yanlış yeri okuyor olabilir')
    saglam = mutant_ekran['SRV_basis_kapisi_kapatilir']['size_motorlu']['tr']
    assert 'No wall thickness was supplied' not in saglam, (
        'db.message kapısı AÇIKKEN de İngilizce basılıyor — kapı çalışmıyor')


def test_mutasyon_scope_cagrisi_bozulunca_cumle_dusuyor(mutant_ekran):
    """Anahtar adı bozulursa cümle ekrandan düşer (fallback İngilizce kalır)."""
    tr = mutant_ekran['scopeIncomplete_cagrisi_silinir']['kalin_motorlu']['tr']
    assert Z5K_ANAHTARLAR['panel.structural.scopeIncomplete'][1] not in tr, (
        'anahtar bozulduğu hâlde Türkçe cümle ekranda — çağrı yeri ölçülen '
        'yer değil')


# ===========================================================================
# 6. SÖZDİZİMİ
# ===========================================================================
@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
@pytest.mark.parametrize('yol', [SOZLUK, PANEL, APPJS,
                                 STATIK / 'i18n_charts.js'],
                         ids=lambda p: p.name)
def test_js_sozdizimi(yol):
    r = subprocess.run([NODE, '--check', str(yol)], capture_output=True,
                       text=True, timeout=60)
    assert r.returncode == 0, '%s: %s' % (yol.name, r.stderr)


if __name__ == '__main__':                  # pragma: no cover
    import sys
    sys.exit(pytest.main([__file__, '-v']))
