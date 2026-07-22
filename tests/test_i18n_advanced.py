"""Hibrit motor sayfasının (advanced.html) çeviri kapsamı testleri.

Berke'nin hedefi: "Türkçe seçilirse HER ŞEY Türkçe, İngilizce seçilirse her şey
İngilizce." Bu dosya o hedefi hibrit sayfası için kalıcı olarak kilitler:

  1. SÖZLÜK BÜTÜNLÜĞÜ
     - hrma/static/js/i18n_advanced.js var, `node --check` geçiyor (node varsa),
       register()/__I18N_PENDING kalıbına uyuyor.
     - EN ve TR anahtar kümeleri birebir aynı, yinelenen anahtar yok.
     - {yer_tutucu} işaretleri iki dilde aynı (I18N.tf eksik parametreyle
       ekrana "{value}" basmasın).

  2. ŞABLON ↔ SÖZLÜK EŞLEŞMESİ
     - advanced.html'deki her data-i18n / -title / -placeholder anahtarının
       sözlükte karşılığı var (yazım hatası koruması).
     - Sözlükte tanımlanıp hiçbir yerde kullanılmayan anahtar yok (ölü çeviri).
     - data-i18n taşıyan düğümün İngilizce metni sözlükteki EN değeriyle aynı
       (dil EN iken sayfa hiç değişmemeli — regresyon riski sıfır).

  3. KAPSAM (çevrilmemiş metin kalmadı)
     - Kullanıcıya görünen metin düğümleri ve title/placeholder nitelikleri
       işaretlenmiş; kalan serbest metin yok (heuristik, dar tutuldu).
     - showMessage(...) çağrıları çıplak metin değil, i18nText/i18nFmt alıyor.

  4. SAYFA KABLOLAMASI
     - i18n.js ve i18n_advanced.js yükleniyor (sıra: çekirdek önce).
     - Dil seçici mountSwitcher ile navigasyona basılıyor.
     - Satır içi script'ler `node --check` geçiyor.
"""

import pathlib
import re
import shutil
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE = REPO_ROOT / 'hrma' / 'templates' / 'advanced.html'
DICT_JS = REPO_ROOT / 'hrma' / 'static' / 'js' / 'i18n_advanced.js'
CORE_JS = REPO_ROOT / 'hrma' / 'static' / 'js' / 'i18n.js'

NODE = shutil.which('node')


# --------------------------------------------------------------------------
# Yardımcılar
# --------------------------------------------------------------------------
def read(path):
    return path.read_text(encoding='utf-8')


def blank(match):
    """Eşleşmeyi aynı uzunlukta boşlukla değiştirir (satır numarası korunur)."""
    return re.sub(r'[^\n]', ' ', match.group(0))


def body_markup():
    """Şablonun HTML gövdesi: <body> ile ana satır içi script arasındaki bölüm.

    Script blokları ve HTML yorumları maskelenir; kalan metin gerçekten
    kullanıcıya görünen işaretlemedir.
    """
    src = read(PAGE)
    start = src.index('<body>')
    end = src.index('    <script>\n        // Global variables')
    region = src[start:end]
    region = re.sub(r'<script\b.*?</script>', blank, region, flags=re.S)
    region = re.sub(r'<!--.*?-->', blank, region, flags=re.S)
    return region


def inline_scripts():
    """advanced.html içindeki satır içi script gövdeleri."""
    return re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>',
                      read(PAGE), flags=re.S)


def _lang_block(source, lang):
    """`<lang>: { ... }` gövdesini tırnak-duyarlı tarayarak döndürür."""
    match = re.search(r'\b%s\s*:\s*\{' % re.escape(lang), source)
    assert match, "i18n_advanced.js içinde '%s' bloğu yok" % lang
    idx = match.end() - 1
    depth = 0
    quote = None
    escaped = False
    while idx < len(source):
        ch = source[idx]
        if quote:
            if escaped:
                escaped = False
            elif ch == '\\':
                escaped = True
            elif ch == quote:
                quote = None
        else:
            if ch in '\'"`':
                quote = ch
            elif ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return source[match.end():idx]
        idx += 1
    pytest.fail("'%s' bloğunun kapanışı bulunamadı" % lang)


PAIR_RE = re.compile(
    r"""^\s*'(?P<key>(?:\\.|[^'\\])*)'\s*:\s*'(?P<val>(?:\\.|[^'\\])*)'\s*,?\s*$""",
    re.M,
)


def _unescape(text):
    return text.replace("\\'", "'").replace('\\\\', '\\')


def pairs(lang):
    """i18n_advanced.js içindeki bir dil bloğunun (anahtar, değer) listesi."""
    source = read(DICT_JS)
    # Yorum satırlarını temizle (blok yorumları içinde 'key': 'value' yok)
    source = re.sub(r'/\*.*?\*/', blank, source, flags=re.S)
    body = _lang_block(source, lang)
    return [(_unescape(m.group('key')), _unescape(m.group('val')))
            for m in PAIR_RE.finditer(body)]


def template_keys():
    """Şablonda geçen tüm çeviri anahtarları (HTML nitelikleri + JS çağrıları)."""
    src = read(PAGE)
    keys = set(re.findall(r'data-i18n(?:-title|-placeholder)?="([^"]+)"', src))
    keys |= set(re.findall(r"i18n(?:Text|Fmt)\('([^']+)'", src))
    keys |= set(re.findall(r"setAttribute\('data-i18n',\s*'([^']+)'\)", src))
    keys |= set(re.findall(r"'(adv\.js\.port[A-Za-z]+)'", src))   # PORT_LABEL_KEYS
    # ['anahtar', 'İngilizce yedek'] biçimindeki eşleme tabloları (requiredFields)
    keys |= set(re.findall(r"\['(adv\.[\w.]+)',", src))
    return keys


def normalize(text):
    return ' '.join(text.split())


# --------------------------------------------------------------------------
# 1. Sözlük bütünlüğü
# --------------------------------------------------------------------------
def test_dictionary_file_exists():
    assert DICT_JS.exists(), 'hrma/static/js/i18n_advanced.js yok'
    assert len(read(DICT_JS)) > 5000, 'sözlük beklenenden küçük (yarım mı kaldı?)'


@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
def test_dictionary_syntax_ok():
    result = subprocess.run([NODE, '--check', str(DICT_JS)],
                            capture_output=True, text=True)
    assert result.returncode == 0, 'i18n_advanced.js sözdizimi hatası:\n' + result.stderr


def test_dictionary_uses_register_contract():
    source = read(DICT_JS)
    assert "I18N.register(DICT, 'i18n_advanced.js')" in source, \
        'sözlük register() ile kaydedilmiyor — hiçbir zaman yüklenmez'
    assert '__I18N_PENDING' in source, 'yükleme sırası koruması (__I18N_PENDING) yok'


def test_en_and_tr_key_sets_match():
    en = pairs('en')
    tr = pairs('tr')
    assert en, 'EN bloğu ayrıştırılamadı (kalıp bozulmuş olabilir)'
    en_keys = [k for k, _ in en]
    tr_keys = [k for k, _ in tr]
    dup_en = sorted({k for k in en_keys if en_keys.count(k) > 1})
    dup_tr = sorted({k for k in tr_keys if tr_keys.count(k) > 1})
    assert not dup_en, 'EN sözlüğünde yinelenen anahtar: %s' % dup_en
    assert not dup_tr, 'TR sözlüğünde yinelenen anahtar: %s' % dup_tr
    missing = sorted(set(en_keys) - set(tr_keys))
    extra = sorted(set(tr_keys) - set(en_keys))
    assert not missing, 'TR çevirisi eksik: %s' % missing
    assert not extra, "TR'de olup EN'de olmayan anahtar: %s" % extra


def test_placeholders_match_between_languages():
    """{yer_tutucu} kümeleri iki dilde aynı olmalı (I18N.tf doldurur)."""
    en = dict(pairs('en'))
    tr = dict(pairs('tr'))
    problems = []
    for key, value in en.items():
        want = set(re.findall(r'\{(\w+)\}', value))
        got = set(re.findall(r'\{(\w+)\}', tr.get(key, '')))
        if want != got:
            problems.append('%s: EN%s TR%s' % (key, sorted(want), sorted(got)))
    assert not problems, 'Yer tutucu uyuşmazlığı:\n  ' + '\n  '.join(problems)


def test_turkish_values_use_turkish_characters():
    """TR sözlüğü gerçekten Türkçe olmalı: ç/ğ/ı/İ/ö/ş/ü yeterince geçmeli.

    Kaba ama etkili bir 'makine kopyası' koruması: 620 metinlik bir sözlükte
    Türkçe harf içeren değerlerin oranı düşükse çeviri yapılmamış demektir.
    """
    tr = dict(pairs('tr'))
    turkish = re.compile('[çğıİöşüÇĞÖŞÜ]')
    hits = sum(1 for v in tr.values() if turkish.search(v))
    assert hits > len(tr) * 0.5, \
        'TR değerlerinin yalnızca %d/%d tanesinde Türkçe harf var' % (hits, len(tr))


# --------------------------------------------------------------------------
# 2. Şablon ↔ sözlük eşleşmesi
# --------------------------------------------------------------------------
def test_every_template_key_exists_in_dictionary():
    known = {k for k, _ in pairs('en')}
    unknown = sorted(k for k in template_keys() if k not in known)
    assert not unknown, 'Sözlükte karşılığı olmayan anahtarlar: %s' % unknown


def test_no_unused_dictionary_keys():
    used = template_keys()
    unused = sorted(k for k, _ in pairs('en') if k not in used)
    assert not unused, 'Hiçbir yerde kullanılmayan sözlük anahtarları: %s' % unused


def test_english_values_match_template_text():
    """data-i18n taşıyan düğümün şablondaki metni EN sözlük değeriyle aynı.

    Böylece dil İngilizce iken sayfa BİREBİR eskisi gibi kalır; çeviri katmanı
    görünen metni sessizce değiştiremez.
    """
    en = dict(pairs('en'))
    markup = body_markup()
    problems = []
    for match in re.finditer(r'data-i18n="([^"]+)"[^>]*>([^<]*)<', markup):
        key, text = match.group(1), normalize(match.group(2))
        if not text or key not in en:
            continue
        if normalize(en[key]) != text:
            problems.append('%s:\n      şablon: %r\n      sözlük: %r'
                            % (key, text, en[key]))
    assert not problems, ('Şablon metni ile EN sözlük değeri farklı:\n  '
                          + '\n  '.join(problems[:20]))


def test_attribute_values_match_template():
    en = dict(pairs('en'))
    markup = body_markup()
    problems = []
    patterns = (
        (r'title="([^"]*)"[^>]*data-i18n-title="([^"]+)"', 0),
        (r'data-i18n-title="([^"]+)"[^>]*title="([^"]*)"', 1),
        (r'placeholder="([^"]*)"[^>]*data-i18n-placeholder="([^"]+)"', 0),
        (r'data-i18n-placeholder="([^"]+)"[^>]*placeholder="([^"]*)"', 1),
    )
    for pattern, key_index in patterns:
        for m in re.finditer(pattern, markup):
            key = m.group(key_index + 1)
            value = m.group(2 - key_index)
            if key in en and normalize(en[key]) != normalize(value):
                problems.append('%s: şablon %r / sözlük %r' % (key, value, en[key]))
    assert not problems, 'Nitelik metni sözlükle uyuşmuyor:\n  ' + '\n  '.join(problems)


# --------------------------------------------------------------------------
# 3. Kapsam: çevrilmemiş metin kalmadı
# --------------------------------------------------------------------------
# İşaretlenmesi gerekmeyen metinler: yalnız simge/sayı/birim olanlar ve
# ölçü çizgisi tireleri. Liste BİLİNÇLİ olarak dar tutuldu.
IGNORE_TEXT = re.compile(r'^[\s\d.,:/()\[\]%×+\-—–…°&;#a-z]{0,4}$')
SYMBOLIC = {'?', '—', '1&times;', '&#9654;', 't = 0.00 s / — s', 'N⋅s',
            'P', '(t)', '(A', '/A)', '0.9', 't', '100%', '1050 kg/m³'}


def test_no_unmarked_visible_text_in_markup():
    """Gövdede data-i18n taşımayan serbest metin düğümü kalmamalı."""
    markup = body_markup()
    tokens = [(m.start(), m.group(0))
              for m in re.finditer(r'(<[^>]*>)|([^<]+)', markup)]
    leftovers = []
    for index, (offset, token) in enumerate(tokens):
        if token.startswith('<'):
            continue
        text = normalize(token)
        if not text or text in SYMBOLIC or IGNORE_TEXT.match(text):
            continue
        if not re.search(r'[A-Za-z]{2}', re.sub(r'&[a-zA-Z]+;|&#\d+;', ' ', text)):
            continue
        prev = tokens[index - 1][1] if index else ''
        if 'data-i18n' in prev:
            continue
        line = markup.count('\n', 0, offset) + 1
        leftovers.append('gövde satırı ~%d: %r' % (line, text[:90]))
    assert not leftovers, ('İşaretlenmemiş görünen metin kaldı '
                           '(data-i18n eklenmeli):\n  ' + '\n  '.join(leftovers))


def test_visible_attributes_are_marked():
    """title/placeholder nitelikleri çeviri anahtarı taşımalı."""
    markup = body_markup()
    missing = []
    for m in re.finditer(r'<[^>]+>', markup):
        tag = m.group(0)
        for attr in ('title', 'placeholder'):
            am = re.search(r'\b%s\s*=\s*"([^"]*)"' % attr, tag)
            if not am or not re.search(r'[A-Za-z]{2}', am.group(1)):
                continue
            if 'data-i18n-%s=' % attr not in tag:
                missing.append('%s=%r' % (attr, am.group(1)[:60]))
    assert not missing, 'Çeviri anahtarı olmayan nitelikler: %s' % missing


def test_show_message_calls_are_translated():
    """showMessage(...) çıplak metin literali almamalı."""
    bad = []
    for block in inline_scripts():
        for m in re.finditer(r"showMessage\(\s*(['\"`])((?:[^'\"`\\]|\\.)*)\1", block):
            if re.search(r'[A-Za-z]{3}', m.group(2)):
                bad.append(m.group(2)[:70])
    assert not bad, ('Çevrilmemiş showMessage metinleri (i18nText/i18nFmt '
                     'kullanılmalı): %s' % bad)


def test_i18n_helpers_are_defined():
    source = read(PAGE)
    assert 'function i18nText(' in source, 'i18nText yardımcısı tanımlı değil'
    assert 'function i18nFmt(' in source, 'i18nFmt yardımcısı tanımlı değil'
    # Sözlük yüklenmezse sayfa çökmemeli: guard zorunlu
    assert "typeof window.I18N !== 'undefined'" in source, \
        'i18n yardımcıları guard kullanmıyor (sözlük yoksa sayfa çöker)'


def test_dynamic_injector_fields_are_translated():
    """Enjektör tipine göre üretilen alanlar da çevrilmeli."""
    source = read(PAGE)
    start = source.index('function updateInjectorParams()')
    end = source.index('paramsDiv.innerHTML = html;', start)
    block = source[start:end]
    labels = re.findall(r'<label>([^<\n]+)', block)
    assert not labels, 'Çevrilmemiş enjektör etiketleri: %s' % labels
    tips = re.findall(r'<span class="tooltip-text">', block)
    assert not tips, 'Çevrilmemiş enjektör yardım balonu kaldı (%d adet)' % len(tips)
    assert 'I18N.applyTo(paramsDiv)' in source, \
        'innerHTML sonrası I18N.applyTo çağrılmıyor — yeni alanlar çevrilmez'


# --------------------------------------------------------------------------
# 4. Sayfa kablolaması
# --------------------------------------------------------------------------
def test_page_loads_core_then_dictionary():
    source = read(PAGE)
    core = source.index('/static/js/i18n.js')
    dictionary = source.index('/static/js/i18n_advanced.js')
    assert core < dictionary, 'i18n.js sözlükten SONRA yükleniyor (sıra bozuk)'


def test_language_switcher_is_mounted():
    source = read(PAGE)
    assert 'I18N.mountSwitcher' in source, 'Dil seçici sayfaya basılmıyor'
    assert 'id="navLangMount"' in source, 'Dil seçici için nav kabı yok'
    assert 'I18N.onChange' in source, \
        'Dil değişiminde JS ile basılan metinler yenilenmiyor'


@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
def test_inline_scripts_syntax_ok(tmp_path):
    checked = 0
    for index, block in enumerate(inline_scripts()):
        if not block.strip() or '{{' in block:
            continue          # Jinja değişkeni içeren blok JS olarak denetlenemez
        path = tmp_path / ('inline_%d.js' % index)
        path.write_text(block, encoding='utf-8')
        result = subprocess.run([NODE, '--check', str(path)],
                                capture_output=True, text=True)
        assert result.returncode == 0, \
            'advanced.html satır içi script #%d sözdizimi hatası:\n%s' % (index, result.stderr)
        checked += 1
    assert checked >= 1, 'Denetlenebilir satır içi script bulunamadı'


@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
def test_language_switch_translates_and_restores(tmp_path):
    """Gerçek koşum: i18n.js + sözlük yüklenir, sahte DOM'da dil değiştirilir.

    'TR seçilince her şey Türkçe, EN seçilince her şey İngilizce' kuralı
    burada fiilen denenir — regex testleri yalnız 'yazılmış mı' der.
    """
    harness = tmp_path / 'harness.js'
    harness.write_text(HARNESS_JS, encoding='utf-8')
    result = subprocess.run(
        [NODE, str(harness), str(CORE_JS), str(DICT_JS)],
        capture_output=True, text=True)
    assert result.returncode == 0, 'koşum hatası:\n' + result.stderr
    lines = [line for line in result.stdout.strip().split('\n') if line.startswith('CHECK')]
    assert lines, 'koşum çıktı üretmedi:\n' + result.stdout
    failures = [line for line in lines if ' FAIL' in line]
    assert not failures, 'Dil değişimi koşumu başarısız:\n  ' + '\n  '.join(failures)


HARNESS_JS = r"""
'use strict';
const fs = require('fs');
const vm = require('vm');

function El(tag) {
    this.nodeType = 1;
    this.tagName = (tag || 'div').toUpperCase();
    this._attrs = {};
    this.textContent = '';
    this.children = [];
    this.options = [];
    this._listeners = {};
    this.className = '';
}
El.prototype.getAttribute = function (k) {
    return Object.prototype.hasOwnProperty.call(this._attrs, k) ? this._attrs[k] : null;
};
El.prototype.setAttribute = function (k, v) { this._attrs[k] = v; };
El.prototype.appendChild = function (c) {
    this.children.push(c);
    if (c.tagName === 'OPTION') this.options.push(c);
    return c;
};
El.prototype.addEventListener = function (t, fn) {
    (this._listeners[t] = this._listeners[t] || []).push(fn);
};
El.prototype.matches = function (sel) {
    const self = this;
    return sel.split(',').some(function (part) {
        part = part.trim();
        const m = part.match(/^(\w+)?\[([\w-]+)\]$/);
        if (!m) return false;
        if (m[1] && self.tagName !== m[1].toUpperCase()) return false;
        return self.getAttribute(m[2]) !== null;
    });
};
El.prototype.descendants = function () {
    let out = [];
    this.children.forEach(function (c) {
        out.push(c);
        out = out.concat(c.descendants());
    });
    return out;
};
El.prototype.querySelectorAll = function (sel) {
    return this.descendants().filter(function (e) { return e.matches(sel); });
};
El.prototype.querySelector = function (sel) { return this.querySelectorAll(sel)[0] || null; };

const body = new El('body');
const document = {
    nodeType: 9,
    readyState: 'complete',
    documentElement: new El('html'),
    head: new El('head'),
    body: body,
    createElement: function (tag) { return new El(tag); },
    getElementById: function () { return null; },
    addEventListener: function () {},
    dispatchEvent: function () { return true; },
    querySelectorAll: function (sel) { return body.querySelectorAll(sel); },
    querySelector: function (sel) { return body.querySelector(sel); }
};
const store = {};
const win = {
    document: document,
    localStorage: {
        getItem: function (k) { return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null; },
        setItem: function (k, v) { store[k] = String(v); }
    },
    console: { warn: function () {}, log: function () {} },
    WeakMap: WeakMap
};
win.window = win;
const context = vm.createContext(win);
vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), context);   // i18n.js
vm.runInContext(fs.readFileSync(process.argv[3], 'utf8'), context);   // i18n_advanced.js

const I18N = win.I18N;
function check(name, ok, detail) {
    console.log('CHECK ' + name + (ok ? ' OK' : ' FAIL ' + (detail || '')));
}

// Sözlük gerçekten yüklendi mi
check('sozluk-yuklendi', I18N.has('adv.sec.motorInformation'));

// data-i18n taşıyan bir düğüm dil değişince çevrilir ve geri döner
const node = new El('h2');
node.setAttribute('data-i18n', 'adv.sec.motorInformation');
node.textContent = 'Motor Information';
body.appendChild(node);

const input = new El('input');
input.setAttribute('data-i18n-placeholder', 'adv.ph.briefDescriptionMotor');
input.setAttribute('placeholder', 'Brief description of the motor...');
body.appendChild(input);

I18N.setLang('tr');
check('tr-metin', node.textContent === 'Motor Bilgileri', node.textContent);
check('tr-placeholder', input.getAttribute('placeholder') === 'Motorun kısa açıklaması...',
      input.getAttribute('placeholder'));
check('tr-html-lang', document.documentElement.getAttribute('lang') === 'tr');

I18N.setLang('en');
check('en-metin', node.textContent === 'Motor Information', node.textContent);
check('en-placeholder', input.getAttribute('placeholder') === 'Brief description of the motor...',
      input.getAttribute('placeholder'));

// tf(): yer tutucu iki dilde de dolar
I18N.setLang('tr');
const filled = I18N.tf('adv.msg.generating', { label: 'STL paketi' });
check('tf-yer-tutucu', filled.indexOf('STL paketi') >= 0 && filled.indexOf('{') < 0, filled);

// Dil tercihi saklanır
check('tercih-saklandi', store.hrma_lang === 'tr', store.hrma_lang);
"""
