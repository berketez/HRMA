"""i18n katmanı ve dil karışıklığı regresyon testleri (2026-07-19).

Berke Windows testinde "Türkçe ve İngilizce karışık olmuş, dil seçeneği
Home sekmesine gelmeli" dedi. Bu dosya iki şeyi kalıcı olarak kilitler:

  1. i18n ALTYAPISI
     - hrma/static/js/i18n.js var, `node --check` geçiyor (node varsa),
       window.I18N sözleşmesini (lang/t/setLang/apply) sunuyor.
     - EN ve TR sözlüklerinin anahtar kümeleri BİREBİR aynı; eksik çeviri
       testi kırar (yarım çeviri = yeni dil karışıklığı).
     - index.html'de #langSelect var ve dört şablon da i18n.js'i yüklüyor.

  2. TEK DİL = İNGİLİZCE (alt sayfalar)
     advanced/solid/liquid şablonlarında kullanıcıya GÖRÜNEN Türkçe metin
     kalmadı. Heuristik bilinçli olarak dar tutuldu (yanlış pozitif üretmesin):
       - HTML yorumları (<!-- -->), JS blok/satır yorumları ve <style>
         blokları maskelenir. Kod yorumları Türkçe KALIR, kural değil.
       - Yalnız (a) `>metin<` düğümleri, (b) çeviri gerektiren nitelikler
         (title/placeholder/alt/aria-label) ve (c) JS tırnaklı string'leri
         taranır. Değişken/fonksiyon adları ve CSS taranmaz.
       - Türkçe'ye özgü karakter kümesi: ç ğ ı İ ö ş ü (+ büyükleri).
         'â/î/û' gibi ortak karakterler ve özel isimler (Tezgöçen) hariç.
"""

import json
import pathlib
import re
import shutil
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATES = REPO_ROOT / 'hrma' / 'templates'
STATIC_JS = REPO_ROOT / 'hrma' / 'static' / 'js'
I18N_JS = STATIC_JS / 'i18n.js'

# Çok-parçalı sözlük dosyaları: hrma/static/js/i18n_<kapsam>.js
# (i18n.js'in kendisi bu desene UYMAZ — alt çizgi zorunlu.)
DICT_FILES = sorted(STATIC_JS.glob('i18n_*.js'))

INDEX_HTML = TEMPLATES / 'index.html'
I18N_SUB_TEMPLATES = [TEMPLATES / name for name in ('advanced.html', 'solid.html', 'liquid.html')]
I18N_ALL_TEMPLATES = [INDEX_HTML] + I18N_SUB_TEMPLATES

# Türkçe'ye özgü harfler. 'İ' ve 'ı' en ayırt edici olanlar.
TURKISH_CHARS = re.compile(r'[çğıİöşüÇĞÖŞÜ]')

# Aksansız yazılmış Türkçe kelimeler (ör. 'Hesapla', 'Toplam Uzunluk') karakter
# testine takılmaz. Bu liste BİLİNÇLİ olarak dar: yalnız İngilizce'de karşılığı
# olmayan, teknik kısaltmalarla karışmayan tam kelimeler. Yeni yanlış pozitif
# çıkarsa kelimeyi listeden çıkar, heuristiği gevşetme.
TURKISH_WORDS = re.compile(
    r'\b('
    r'Hesapla|Hesaplama|Kaydet|Kapat|Yukleniyor|Basinc|Sicaklik|Yakit|Enjektor|'
    r'Kamara|Sonuc|Uyari|Tasarim|Deger|Kutle|Uzunluk|Kalinlik|Oksitleyici|'
    r'Yanma|Analizi|Malzeme|Maliyet|Toplam|Ortalama|Baslangic|Bitis|Gerilme|'
    r'Guvenlik|Kasa|Bilinmeyen|bilinmeyen|Verimlilik|Yogunluk|Cozucu|'
    r'UYARI|Uyari|Onerilen|Gerekli|Yeterli|Basarili|Basarisiz|Elektrik|'
    r'olmali|hesaplayin|calistirin|cinsinden|saat'
    r')\b'
)

# Kullanıcıya görünen metin taşıyan nitelikler (id/class/style taranmaz).
VISIBLE_ATTRS = re.compile(r'(?:title|placeholder|alt|aria-label)\s*=\s*"([^"]*)"')

# Özel isimler ve bilinçli istisnalar (dil seçicisindeki 'Türkçe' dahil).
ALLOWED = (
    'Tezgöçen',
    'Türkçe',
)


# --------------------------------------------------------------------------
# Yardımcılar
# --------------------------------------------------------------------------
def read(path):
    return path.read_text(encoding='utf-8')


def mask_comments_and_style(text):
    """Yorumları ve <style> bloklarını aynı uzunlukta boşlukla değiştirir.

    Ofsetler korunur, böylece satır numarası raporlanabilir. Türkçe kod
    yorumları projede BİLİNÇLİ olarak Türkçe (Berke'nin tercihi) — testin
    kapsamı yalnız ekranda görünen metin.
    """
    def blank(match):
        return re.sub(r'[^\n]', ' ', match.group(0))

    text = re.sub(r'<!--.*?-->', blank, text, flags=re.S)
    text = re.sub(r'<style\b[^>]*>.*?</style>', blank, text, flags=re.S | re.I)
    text = re.sub(r'/\*.*?\*/', blank, text, flags=re.S)

    # Satır yorumları: tırnak içindeki '//' (ör. https://) yanlışlıkla kesilmesin
    out_lines = []
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
        out_lines.append(line if cut is None else line[:cut] + ' ' * (len(line) - cut))
    return '\n'.join(out_lines)


def turkish_hits(path):
    """Kullanıcıya görünen Türkçe metin parçalarını (satır, metin) döndürür."""
    raw = read(path)
    masked = mask_comments_and_style(raw)

    def line_of(offset):
        return masked.count('\n', 0, offset) + 1

    hits = []

    def consider(offset, fragment):
        text = ' '.join(fragment.split())
        if not text:
            return
        for ok in ALLOWED:
            text = text.replace(ok, '')
        if TURKISH_CHARS.search(text) or TURKISH_WORDS.search(text):
            hits.append((line_of(offset), text[:120]))

    # (a) HTML metin düğümleri (script içindeki template literal HTML'i dahil)
    for m in re.finditer(r'>([^<>]+)<', masked):
        consider(m.start(1), m.group(1))

    # (b) Kullanıcıya görünen nitelikler
    for m in VISIBLE_ATTRS.finditer(masked):
        consider(m.start(1), m.group(1))

    # (c) JS tırnaklı string'leri (HTML parçası içerenler (a)'da yakalandı)
    for pattern in (r"'((?:[^'\\\n]|\\.)*)'", r'"((?:[^"\\\n]|\\.)*)"'):
        for m in re.finditer(pattern, masked):
            if '<' not in m.group(1):
                consider(m.start(1), m.group(1))

    # (d) Template literal'ler (`...`): tek satırlık uyarı/mesaj metinleri
    #     buraya saklanıyordu (ör. eski 'UYARI: Tank pressure ...' mesajı).
    #     ${...} yerleştirmeleri maskelenir ki değişken adları taranmasın.
    for m in re.finditer(r'`([^`]*)`', masked):
        body = re.sub(r'\$\{[^{}]*\}', ' ', m.group(1))
        if '<' in body:
            continue          # HTML parçası → (a) zaten tarıyor
        consider(m.start(1), body)

    return hits


def dict_keys(block_name):
    """i18n.js içindeki STRINGS.<block_name> sözlüğünün anahtarlarını çıkarır."""
    source = read(I18N_JS)
    start = source.index('var STRINGS = {')
    marker = re.search(r'^\s{8}%s:\s*\{' % re.escape(block_name), source[start:], re.M)
    assert marker, "i18n.js içinde '%s' sözlük bloğu bulunamadı" % block_name
    begin = start + marker.end() - 1          # '{' konumu
    depth = 0
    for idx in range(begin, len(source)):
        if source[idx] == '{':
            depth += 1
        elif source[idx] == '}':
            depth -= 1
            if depth == 0:
                body = source[begin:idx]
                break
    else:                                      # pragma: no cover - bozuk dosya
        pytest.fail("i18n.js '%s' bloğunun kapanışı bulunamadı" % block_name)
    return re.findall(r"^\s*'([^']+)'\s*:", body, re.M)


# --------------------------------------------------------------------------
# 1. Altyapı
# --------------------------------------------------------------------------
def test_i18n_js_exists_and_not_empty():
    assert I18N_JS.exists(), 'hrma/static/js/i18n.js yok'
    assert len(read(I18N_JS)) > 500, 'i18n.js beklenenden küçük (boş şablon mu?)'


@pytest.mark.skipif(shutil.which('node') is None, reason='node kurulu değil')
def test_i18n_js_syntax_ok():
    result = subprocess.run(
        [shutil.which('node'), '--check', str(I18N_JS)],
        capture_output=True, text=True
    )
    assert result.returncode == 0, 'i18n.js sözdizimi hatası:\n' + result.stderr


def test_i18n_js_api_contract():
    source = read(I18N_JS)
    for member in ('global.I18N = I18N', 'I18N.t =', 'I18N.setLang =',
                   'I18N.apply =', 'hrma_lang'):
        assert member in source, "i18n.js sözleşmesinde eksik: %s" % member
    # data-i18n nitelik desteği
    for attr in ('[data-i18n]', '[data-i18n-title]', '[data-i18n-placeholder]'):
        assert attr in source, 'i18n.js %s desteğini kaybetmiş' % attr


def test_en_and_tr_key_sets_are_identical():
    en = dict_keys('en')
    tr = dict_keys('tr')
    assert en, 'EN sözlüğü boş'
    assert len(en) == len(set(en)), 'EN sözlüğünde tekrar eden anahtar var'
    assert len(tr) == len(set(tr)), 'TR sözlüğünde tekrar eden anahtar var'
    missing_tr = sorted(set(en) - set(tr))
    extra_tr = sorted(set(tr) - set(en))
    assert not missing_tr, 'TR çevirisi eksik anahtarlar: %s' % missing_tr
    assert not extra_tr, "TR'de olup EN'de olmayan anahtarlar: %s" % extra_tr


def test_tr_values_are_not_copies_of_en():
    """Yarım çeviri koruması: TR değerlerinin çoğu EN'den farklı olmalı."""
    source = read(I18N_JS)
    def values(block):
        start = source.index("        %s: {" % block)
        depth = 0
        for idx in range(start + len("        %s: " % block), len(source)):
            if source[idx] == '{':
                depth += 1
            elif source[idx] == '}':
                depth -= 1
                if depth == 0:
                    body = source[start:idx]
                    break
        return dict(re.findall(r"^\s*'([^']+)':\s*'(.*?)',?\s*$", body, re.M))

    en, tr = values('en'), values('tr')
    shared = set(en) & set(tr)
    identical = [k for k in shared if en[k] == tr[k]]
    # 'lang.en'/'lang.tr' gibi dil adları bilerek aynı kalır.
    assert len(identical) <= 3, 'Çevrilmemiş görünen TR anahtarları: %s' % sorted(identical)


# --------------------------------------------------------------------------
# 2. Şablon entegrasyonu
# --------------------------------------------------------------------------
def test_index_has_language_selector():
    html = read(INDEX_HTML)
    assert 'id="langSelect"' in html, 'Ana sayfada dil seçici (#langSelect) yok'
    assert 'value="en"' in html and 'value="tr"' in html, 'Dil seçeneklerinden biri eksik'
    assert 'I18N.setLang' in html, 'Dil seçici I18N.setLang çağırmıyor'


@pytest.mark.parametrize('page', I18N_ALL_TEMPLATES, ids=lambda p: p.name)
def test_all_pages_load_i18n(page):
    assert '/static/js/i18n.js' in read(page), '%s i18n.js yüklemiyor' % page.name


def test_index_texts_are_marked_for_translation():
    """Ana sayfa tam çevrilebilir olmalı: kartlar/başlıklar data-i18n taşır."""
    html = read(INDEX_HTML)
    keys = set(re.findall(r'data-i18n="([^"]+)"', html))
    required = {
        'hero.tagline', 'section.select',
        'card.hybrid.title', 'card.solid.title', 'card.liquid.title',
        'card.hybrid.desc', 'card.solid.desc', 'card.liquid.desc',
        'btn.launch', 'link.formulas',
    }
    assert required <= keys, 'Ana sayfada işaretlenmemiş metinler: %s' % sorted(required - keys)
    # Kullanılan her anahtarın sözlükte karşılığı olmalı (yazım hatası koruması)
    known = set(dict_keys('en'))
    unknown = sorted(k for k in keys if k not in known)
    assert not unknown, 'Sözlükte olmayan data-i18n anahtarları: %s' % unknown


# --------------------------------------------------------------------------
# 3. Alt sayfalarda Türkçe kalıntı yok
# --------------------------------------------------------------------------
@pytest.mark.parametrize('page', I18N_SUB_TEMPLATES, ids=lambda p: p.name)
def test_no_turkish_left_in_visible_text(page):
    hits = turkish_hits(page)
    detail = '\n'.join('  %s:%d  %s' % (page.name, ln, txt) for ln, txt in hits)
    assert not hits, (
        '%s içinde kullanıcıya görünen Türkçe metin kaldı '
        '(alt sayfalar tek dilli: İngilizce):\n%s' % (page.name, detail)
    )


def test_index_visible_turkish_only_allowed_items():
    """Ana sayfa İngilizce; tek istisnalar 'Türkçe' seçeneği ve yazar adı."""
    assert not turkish_hits(INDEX_HTML)


@pytest.mark.parametrize('page', I18N_ALL_TEMPLATES, ids=lambda p: p.name)
def test_no_emoji_in_templates(page):
    """Berke kuralı: arayüz metinlerinde emoji yok."""
    emoji = re.compile('[\U0001F000-\U0001FAFF\U00002600-\U000027BF]')
    found = emoji.findall(read(page))
    assert not found, '%s içinde emoji: %s' % (page.name, found[:10])


# --------------------------------------------------------------------------
# 4. Çok-parçalı sözlük dosyaları (i18n_*.js)
# --------------------------------------------------------------------------
# register() sözleşmesi ve dosya kalıbı i18n.js başlığında belgelenmiştir.
# Buradaki testler o kalıba uymayan sözlük dosyasını erken yakalar; asıl amaç
# "yarım çeviri" ile arayüzün yeniden TR/EN karışığına dönmesini engellemek.

# Değeri iki dilde AYNI kalabilen teknik kısaltmalar/işaretler. Bunlar
# çevrilmez (çevrilirse yanlış olur), o yüzden 'kopya' sayılmazlar.
TECH_TOKENS = (
    'NASA CEA', 'NASA', 'CEA', 'NIST', '6-DOF', 'O/F', 'BATES', 'NHNE',
    'HTPB', 'APCP', 'LOX', 'RP-1', 'LH2', 'N2O', 'H2O2', 'PMMA', 'ABS',
    'Isp', 'c*', 'CF', 'Kn', 'L*', 'STL', 'STEP', 'DXF', 'PDF', 'CSV',
    'JSON', 'CAD', '3D', '2D', '3B', 'HRMA', 'CFD', 'RPA', 'ISA', 'SI',
)

# İki dilde aynı yazılan sık kelimeler (çeviri hatası değil).
SAME_IN_BOTH = {
    'motor', 'motorlar', 'test', 'grain', 'radar', 'plotly', 'python',
    'bar', 'mm', 'cm', 'kg', 'kn', 'mpa', 'kpa', 'pa', 'psi', 'sn', 's',
    'ok', 'no', 'min', 'max', 'total', 'normal', 'standart', 'standard',
    'lineer', 'oksit', 'parafin', 'paraffin', 'hibrit', 'ideal', 'kritik',
    'kombinasyon', 'optimum', 'profil', 'panel', 'rapor', 'analiz', 'export',
    # Özel adlar: kişi adından gelen ölçüt adları iki dilde de aynı yazılır
    # ('von Mises gerilmesi' / 'von Mises stress'). Yalnız ADIN kendisi
    # muaftır; 'gerilme/stress' gibi çevrilebilir sözcükler taranmaya devam
    # eder, yani 'von Mises stress' TR'de kopya kalırsa yine yakalanır.
    'von', 'mises', 'jacobian', 'gauss',
}

# ASCII'ye kaçış avcısı: doğru yazımında MUTLAKA Türkçe harf içeren kökler.
# Yalnız bunlar aranır — 'Toplam', 'Uzunluk' gibi zaten aksansız kelimeler
# taranmaz (yanlış pozitif üretirdi). Kök eşleşmesi kelime BAŞINDAN yapılır,
# ek serbesttir ('basinc' -> 'basinci' da yakalanır). Ünsüz yumuşamasının
# değiştirdiği köklerin (k -> ğ) iki hâli de listede.
#
# İki bilinçli sınır (yanlış pozitifi sıfırlamak için):
#   1. Eşleşme BÜYÜK/KÜÇÜK HARFE DUYARLI yapılır ve kelime küçük harfe
#      çevrilerek denenir. re.IGNORECASE KULLANILAMAZ: Python'da 'ı' ile 'i'
#      görmezden gelme modunda eşleşir, doğru yazılmış 'hız' bile 'hiz'
#      köküne takılırdı.
#   2. TAMAMI BÜYÜK yazılmış kelimeler atlanır. Türkçe'de 'yakıt' -> 'YAKIT'
#      olur; büyük harfte ı/I ayrımı dilin kendisinde kaybolur, oradan kaçış
#      tespit etmek imkânsız.
# İngilizce ile çakışan kısa köklerden (cap, sec, sure, once, ac) BİLEREK
# kaçınıldı; yanlış pozitif üretirlerdi.
ASCII_SLIP = re.compile(
    r'^('
    r'basinc|sicaklik|sicaklig|yogunluk|yogunlug|kutle|kalinlik|kalinlig|'
    r'guvenlik|guvenlig|agirlik|agirlig|genislik|genislig|yukseklik|yukseklig|'
    r'olcu|olce|cozum|cozucu|sonuc|baslangic|bitis|cikti|cikis|giris|'
    r'deger|carpim|carpan|katsayi|dogru|dogal|yukleniyor|hesaplaniyor|'
    r'calistir|tasarim|basari|akis|akiskan|sogutma|yakit|enjektor|lule|bogaz|'
    r'uzerinde|icin|dusuk|yuksek|buyuk|kucuk|gorunum|ozgul|duzeltme|gosterge|'
    r'uyari|ayrinti|ozet|disa|sifirla|varsayilan|seci|degistir|gunluk|'
    # 'geci' kökü BİLEREK açık yazıldı (gecis|gecici|gecit): 'gecikme'
    # doğru yazımında hiç Türkçe harf taşımaz, ortak önek yanlış alarmdı
    # (CI 2026-08-16: adv.label.parachuteDeployDelayS).
    r'baglanti|klasor|ornek|gecis|gecici|gecit|yanlis|artis|degisim|egri|cizim|cizgi|cizel|'
    r'yaricap|hiz|agir|asagi|yukari|kaydir|kisim|kisa|sinir|sart|sekil|sema|'
    r'islem|isaret|cok|tum|hic|acik|kapali|sayi|tasiyici|cevir|kati|sivi'
    r')'
)

# Kelime ayrıştırıcı: Türkçe harfler dâhil.
WORD_RE = re.compile(r'[0-9A-Za-zÇĞİÖŞÜçğıöşü]+')


# Ünlü harfler — ünsüz yumuşaması denetimi için (aşağıya bakınız).
UNLULER = set('aeıioöuü')

# ÜNSÜZ YUMUŞAMASI İSTİSNASI (2026-08-05): yalnız doğru yazımı son harf
# DIŞINDA tamamen ASCII olan kökler. 'sonuç' + 'u' = 'sonucu' baştan sona
# ASCII'dir ve DOĞRU yazımdır ('sonuçu' yanlıştır) — kök taraması onu kaçış
# sanıyordu. Buna karşılık 'basınç' + 'ı' = 'basıncı' iki 'ı' taşır, yani
# doğru yazım hiçbir zaman tümü-ASCII olmaz: 'basinci' GERÇEK kaçıştır ve
# istisnaya girmez. Bu yüzden liste dar tutulur, kural genelleştirilmez.
YUMUSAYAN_ASCII_KOKLER = {'sonuc'}


def ascii_slip(text):
    """Türkçe karakteri kaybolmuş görünen ilk kelimeyi döndürür (yoksa None).

    Yumuşama istisnası için bkz. YUMUSAYAN_ASCII_KOKLER: o köklerden biri
    ünlüden ÖNCE geliyorsa kaçış sayılmaz ('sonucu' doğru). Ünsüzden önce
    ('sonucta') ve yalın hâlde ('sonuc') denetim aynen sürer — 'sonuçta' ve
    'sonuç' doğru yazımlardır.
    """
    for token in TECH_TOKENS:
        text = text.replace(token, ' ')
    for word in WORD_RE.findall(text):
        if len(word) > 1 and word.isupper():
            continue                      # 'YAKIT' meşru büyük harf yazımı
        # 'İ'.lower() 'i' + birleşen nokta (U+0307) üretir; kökle eşleşsin diye silinir.
        plain = word.lower().replace('̇', '')
        eslesme = ASCII_SLIP.match(plain)
        if not eslesme:
            continue
        kok = eslesme.group(1)
        sonraki = plain[len(kok):len(kok) + 1]
        if kok in YUMUSAYAN_ASCII_KOKLER and sonraki and sonraki in UNLULER:
            continue                      # meşru yumuşama: sonuç -> sonucu
        return word
    return None


def _strip_js_comments(text):
    """JS yorumlarını boşlukla değiştirir (ofsetler korunur).

    Türkçe yorumlardaki kesme işareti ("i18n.js'ten") tırnak tarayıcısını
    bozmasın diye ayrıştırmadan ÖNCE çağrılır.
    """
    return mask_comments_and_style(text)


def _find_lang_block(source, lang):
    """`<lang>: { ... }` bloğunun gövdesini döndürür (tırnak-duyarlı tarama)."""
    match = re.search(r'\b%s\s*:\s*\{' % re.escape(lang), source)
    if not match:
        return None
    idx = match.end() - 1          # '{' konumu
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
    return None


PAIR_RE = re.compile(
    r"""^\s*(?P<q1>['"])(?P<key>(?:\\.|(?!(?P=q1))[^\\])*?)(?P=q1)"""
    r"""\s*:\s*(?P<q2>['"])(?P<val>(?:\\.|(?!(?P=q2))[^\\])*?)(?P=q2)\s*,?\s*$""",
    re.M,
)


def _unescape(text):
    return text.replace("\\'", "'").replace('\\"', '"').replace('\\\\', '\\')


def dict_pairs(path, lang):
    """i18n_*.js (veya i18n.js) içindeki bir dil bloğunun (anahtar, değer) listesi.

    Liste döner (sözlük değil) ki dosya içi yinelenen anahtar da görülebilsin.
    """
    source = _strip_js_comments(read(path))
    body = _find_lang_block(source, lang)
    if body is None:
        return None
    return [(_unescape(m.group('key')), _unescape(m.group('val')))
            for m in PAIR_RE.finditer(body)]


def _core_pairs(lang):
    source = _strip_js_comments(read(I18N_JS))
    start = source.index('var STRINGS = {')
    body = _find_lang_block(source[start:], lang)
    return [(_unescape(m.group('key')), _unescape(m.group('val')))
            for m in PAIR_RE.finditer(body)]


def _all_pairs(lang):
    """Çekirdek + tüm sözlük dosyalarındaki (dosya, anahtar, değer) üçlüleri."""
    out = [(I18N_JS.name, k, v) for k, v in _core_pairs(lang)]
    for path in DICT_FILES:
        pairs = dict_pairs(path, lang) or []
        out.extend((path.name, k, v) for k, v in pairs)
    return out


def _looks_translated(en_value, tr_value):
    """TR değeri EN'in ham kopyası mı? (kısaltma/birim istisnalarıyla)"""
    if en_value != tr_value:
        return True
    text = tr_value
    for token in TECH_TOKENS:
        text = text.replace(token, ' ')
    words = [w for w in re.findall(r'[A-Za-zÇĞİÖŞÜçğıöşü]{3,}', text)
             if w.lower() not in SAME_IN_BOTH]
    return not words          # geriye çevrilebilir kelime kalmadıysa sorun yok


def _dict_file_ids():
    return [p.name for p in DICT_FILES] or ['(sözlük dosyası yok)']


DICT_PARAMS = DICT_FILES or [None]


@pytest.mark.parametrize('path', DICT_PARAMS, ids=_dict_file_ids())
def test_dict_file_follows_register_contract(path):
    """Her i18n_*.js dosyası register()/pending kalıbını kullanmalı."""
    if path is None:
        pytest.skip('hrma/static/js/i18n_*.js henüz yok (sözlükler ayrılmamış)')
    source = read(path)
    assert 'I18N.register(' in source, \
        '%s register() çağırmıyor — sözlük hiçbir zaman yüklenmez' % path.name
    assert '__I18N_PENDING' in source, \
        '%s yükleme sırası koruması (__I18N_PENDING) içermiyor' % path.name


@pytest.mark.skipif(shutil.which('node') is None, reason='node kurulu değil')
@pytest.mark.parametrize('path', DICT_PARAMS, ids=_dict_file_ids())
def test_dict_file_syntax_ok(path):
    if path is None:
        pytest.skip('sözlük dosyası yok')
    result = subprocess.run([shutil.which('node'), '--check', str(path)],
                            capture_output=True, text=True)
    assert result.returncode == 0, '%s sözdizimi hatası:\n%s' % (path.name, result.stderr)


@pytest.mark.parametrize('path', DICT_PARAMS, ids=_dict_file_ids())
def test_dict_file_key_sets_are_identical(path):
    """EN ve TR anahtar kümeleri BİREBİR aynı (eksik çeviri = dil karışıklığı)."""
    if path is None:
        pytest.skip('sözlük dosyası yok')
    en = dict_pairs(path, 'en')
    tr = dict_pairs(path, 'tr')
    assert en is not None, "%s içinde 'en:' sözlük bloğu bulunamadı" % path.name
    assert tr is not None, "%s içinde 'tr:' sözlük bloğu bulunamadı" % path.name
    assert en, '%s EN sözlüğü boş (ayrıştırma kalıbı bozulmuş olabilir)' % path.name

    en_keys = [k for k, _ in en]
    tr_keys = [k for k, _ in tr]
    dup_en = sorted({k for k in en_keys if en_keys.count(k) > 1})
    dup_tr = sorted({k for k in tr_keys if tr_keys.count(k) > 1})
    assert not dup_en, '%s EN sözlüğünde yinelenen anahtar: %s' % (path.name, dup_en)
    assert not dup_tr, '%s TR sözlüğünde yinelenen anahtar: %s' % (path.name, dup_tr)

    missing = sorted(set(en_keys) - set(tr_keys))
    extra = sorted(set(tr_keys) - set(en_keys))
    assert not missing, '%s TR çevirisi eksik anahtarlar: %s' % (path.name, missing)
    assert not extra, "%s TR'de olup EN'de olmayan anahtarlar: %s" % (path.name, extra)


@pytest.mark.parametrize('path', DICT_PARAMS, ids=_dict_file_ids())
def test_dict_file_tr_values_are_translated(path):
    """TR değerleri EN'in kopyası olmamalı (kopya = çevrilmemiş)."""
    if path is None:
        pytest.skip('sözlük dosyası yok')
    en = dict(dict_pairs(path, 'en') or [])
    tr = dict(dict_pairs(path, 'tr') or [])
    shared = sorted(set(en) & set(tr))
    if not shared:
        pytest.skip('%s ayrıştırılabilir çift içermiyor' % path.name)
    untranslated = [k for k in shared if not _looks_translated(en[k], tr[k])]
    # Teknik kısaltma/birim istisnaları _looks_translated içinde elendi;
    # geriye kalan birebir kopyalar gerçek eksik çeviridir.
    detail = '\n'.join('  %s = %r' % (k, tr[k]) for k in untranslated[:25])
    assert not untranslated, (
        '%s içinde çevrilmemiş görünen TR değerleri (%d adet):\n%s'
        % (path.name, len(untranslated), detail)
    )


def test_tr_values_have_no_ascii_slips():
    """TR metinlerinde Türkçe karakter kaybı olmamalı ('Basinc' -> 'Basınç').

    Heuristik: yalnız doğru yazımında MUTLAKA Türkçe harf içeren kökler aranır
    (ASCII_SLIP). Yanlış pozitif çıkarsa kökü listeden ÇIKAR, heuristiği
    gevşetme — aksi hâlde gerçek kaçışlar da görünmez olur.
    """
    slips = []
    for filename, key, value in _all_pairs('tr'):
        word = ascii_slip(value)
        if word:
            slips.append('%s :: %s = %r  (şüpheli: %r)'
                         % (filename, key, value, word))
    assert not slips, 'Türkçe karakter kaybı şüphesi:\n  ' + '\n  '.join(slips)


def test_no_duplicate_keys_across_dict_files():
    """Aynı anahtar iki dosyada farklı değerle tanımlanmamalı.

    register() 'ilk kazanır' kuralıyla çalışır; ikinci tanım sessizce yok
    sayılır ve o metin hiçbir zaman ekrana çıkmaz.
    """
    problems = []
    for lang in ('en', 'tr'):
        seen = {}
        for filename, key, value in _all_pairs(lang):
            if key in seen and seen[key][1] != value:
                problems.append('%s "%s": %s=%r vs %s=%r'
                                % (lang, key, seen[key][0], seen[key][1], filename, value))
            seen.setdefault(key, (filename, value))
    assert not problems, 'Çakışan sözlük anahtarları:\n  ' + '\n  '.join(problems)


def test_no_emoji_in_dictionaries():
    """Berke kuralı: arayüz metinlerinde emoji yok (sözlükler dâhil)."""
    emoji = re.compile('[\U0001F000-\U0001FAFF\U00002600-\U000027BF]')
    found = []
    for lang in ('en', 'tr'):
        for filename, key, value in _all_pairs(lang):
            if emoji.search(value):
                found.append('%s :: %s = %r' % (filename, key, value))
    assert not found, 'Sözlükte emoji:\n  ' + '\n  '.join(found)


# --------------------------------------------------------------------------
# 5. Yeni API sözleşmesi (kaynak düzeyi)
# --------------------------------------------------------------------------
def test_i18n_js_extended_api_contract():
    """Diğer paneller bu adlara göre yazılıyor — adlar SABİT."""
    source = read(I18N_JS)
    for member in ('I18N.register =', 'I18N.tf =', 'I18N.applyTo =',
                   'I18N.onChange =', 'I18N.number =', 'I18N.mountSwitcher =',
                   'I18N.has =', '__I18N_PENDING'):
        assert member in source, 'i18n.js sözleşmesinde eksik: %s' % member


def test_i18n_js_documents_dictionary_convention():
    """Sözlük dosyası adlandırma kuralı dosyanın başında yazılı olmalı."""
    header = read(I18N_JS)[:6000]
    assert 'i18n_' in header, 'i18n.js sözlük dosyası adlandırma kuralını belgelemiyor'
    assert 'register' in header, 'i18n.js register() sözleşmesini belgelemiyor'


# --------------------------------------------------------------------------
# 6. Davranış koşumu (node ile gerçek çalıştırma)
# --------------------------------------------------------------------------
# Regex testleri "yazılmış mı" der, bu koşum "çalışıyor mu" der: i18n.js
# asgari bir sahte DOM içinde vm ile yüklenir ve tüm API sözleşmesi denenir.
HARNESS_JS = r"""
'use strict';
const fs = require('fs');
const vm = require('vm');
const SRC = fs.readFileSync(process.argv[2], 'utf8');
const results = [];
function check(name, cond, detail) {
    results.push({ name: name, ok: !!cond, detail: detail === undefined ? '' : String(detail) });
}
function makeDom() {
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
    El.prototype.fire = function (t) {
        (this._listeners[t] || []).forEach(function (fn) { fn({ type: t }); });
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
        dispatchEvent: function (ev) { document._events.push(ev); return true; },
        _events: [],
        querySelectorAll: function (sel) { return body.querySelectorAll(sel); },
        querySelector: function (sel) { return body.querySelector(sel); }
    };
    return { document: document, El: El, body: body };
}
function load(pending) {
    const dom = makeDom();
    const store = {};
    const warnings = [];
    const win = {
        document: dom.document,
        localStorage: {
            getItem: function (k) { return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null; },
            setItem: function (k, v) { store[k] = String(v); }
        },
        console: { warn: function (m) { warnings.push(String(m)); }, log: function () {} },
        CustomEvent: function (type, init) { this.type = type; this.detail = init && init.detail; },
        WeakMap: WeakMap,
        _warnings: warnings,
        _dom: dom
    };
    win.window = win;
    if (pending) win.__I18N_PENDING = pending;
    vm.createContext(win);
    vm.runInContext(SRC, win, { filename: 'i18n.js' });
    return win;
}

let w = load();
let I = w.I18N;
check('api.members', ['t', 'tf', 'setLang', 'apply', 'applyTo', 'onChange', 'number',
    'register', 'has', 'mountSwitcher', 'languages'].every(function (k) {
    return typeof I[k] === 'function';
}), Object.keys(I).join(','));
check('api.defaultLang', I.lang === 'en', I.lang);
check('api.languages', I.languages().indexOf('tr') >= 0, I.languages().join(','));

check('t.knownKey', I.t('nav.home') === 'Home', I.t('nav.home'));
check('t.unknownKeyReturnsKey', I.t('yok.olan.anahtar') === 'yok.olan.anahtar');
check('t.unknownKeyUsesFallback', I.t('yok.olan', 'Fallback') === 'Fallback');
I.register({ en: { 'only.en': 'English only' } }, 'test');
I.setLang('tr');
check('t.missingTrFallsBackToEn', I.t('only.en') === 'English only', I.t('only.en'));
check('t.trTranslation', I.t('nav.home') === 'Ana Sayfa', I.t('nav.home'));
I.setLang('en');

const added = I.register({ en: { 'x.a': 'A', 'x.b': 'B' }, tr: { 'x.a': 'Aa', 'x.b': 'Bb' } }, 'i18n_test.js');
check('register.returnsAddedCount', added === 4, added);
check('register.mergedEn', I.t('x.a') === 'A', I.t('x.a'));
I.setLang('tr');
check('register.mergedTr', I.t('x.a') === 'Aa', I.t('x.a'));
I.setLang('en');
const before = w._warnings.length;
I.register({ en: { 'x.a': 'CAKISAN' } }, 'i18n_other.js');
check('register.duplicateWarns', w._warnings.length > before, w._warnings.slice(before).join(' | '));
check('register.firstWins', I.t('x.a') === 'A', I.t('x.a'));
check('register.badInputSafe', I.register(null) === 0);

const w2 = load([{ en: { 'pending.key': 'Pending' }, tr: { 'pending.key': 'Bekleyen' } }]);
check('pending.drained', w2.I18N.t('pending.key') === 'Pending', w2.I18N.t('pending.key'));
w2.I18N.setLang('tr');
check('pending.drainedTr', w2.I18N.t('pending.key') === 'Bekleyen', w2.I18N.t('pending.key'));
(w2.__I18N_PENDING = w2.__I18N_PENDING || []).push({ en: { 'late.key': 'Late' }, tr: { 'late.key': 'Gec' } });
check('pending.afterLoad', w2.I18N.t('late.key') === 'Gec', w2.I18N.t('late.key'));

I.register({
    en: { 'fmt.pc': 'Chamber pressure {value} bar' },
    tr: { 'fmt.pc': 'Oda basinci {value} bar' }
}, 'i18n_test.js');
check('tf.en', I.tf('fmt.pc', { value: 12.5 }) === 'Chamber pressure 12.5 bar', I.tf('fmt.pc', { value: 12.5 }));
I.setLang('tr');
check('tf.tr', I.tf('fmt.pc', { value: 12.5 }) === 'Oda basinci 12,5 bar', I.tf('fmt.pc', { value: 12.5 }));
check('tf.missingParamKept', I.tf('fmt.pc', {}) === 'Oda basinci {value} bar', I.tf('fmt.pc', {}));
check('tf.stringParam', I.tf('fmt.pc', { value: 'N/A' }).indexOf('N/A') > 0);
I.setLang('en');

check('number.enDigits', I.number(3.14159, 2) === '3.14', I.number(3.14159, 2));
I.setLang('tr');
check('number.trDigits', I.number(3.14159, 2) === '3,14', I.number(3.14159, 2));
check('number.trPlain', I.number(2.5) === '2,5', I.number(2.5));
check('number.noGrouping', I.number(12500, 1) === '12500,0', I.number(12500, 1));
I.setLang('en');

const El = w._dom.El;
const root = new El('div');
root.setAttribute('data-i18n', 'nav.home');
const child = new El('span');
child.setAttribute('data-i18n', 'nav.hybrid');
const input = new El('input');
input.setAttribute('data-i18n-placeholder', 'nav.solid');
const titled = new El('a');
titled.setAttribute('data-i18n-title', 'nav.liquid');
root.appendChild(child);
root.appendChild(input);
root.appendChild(titled);
I.setLang('tr');
I.applyTo(root);
check('applyTo.rootItself', root.textContent === 'Ana Sayfa', root.textContent);
check('applyTo.child', child.textContent === 'Hibrit Motor', child.textContent);
check('applyTo.placeholder', input.getAttribute('placeholder') === 'Kati Yakitli Motor'
    || input.getAttribute('placeholder').length > 0, input.getAttribute('placeholder'));
check('applyTo.title', titled.getAttribute('title') && titled.getAttribute('title').length > 0,
    titled.getAttribute('title'));
I.setLang('en');
I.applyTo(root);
check('applyTo.switchBack', child.textContent === 'Hybrid Motor', child.textContent);
check('applyTo.nullSafe', (function () { try { I.applyTo(null); return true; } catch (e) { return false; } })());

let seen = [];
const off = I.onChange(function (lang) { seen.push(lang); });
I.setLang('tr');
check('onChange.fired', seen.length === 1 && seen[0] === 'tr', seen.join(','));
off();
I.setLang('en');
check('onChange.unsubscribed', seen.length === 1, seen.join(','));
check('onChange.badInputSafe', typeof I.onChange('fonksiyon degil') === 'function');
I.onChange(function () { throw new Error('bilerek hata'); });
check('onChange.throwIsolated', (function () { try { I.setLang('tr'); I.setLang('en'); return true; } catch (e) { return false; } })());

const evts = w.document._events.filter(function (e) { return e.type === 'hrma:langchange'; });
check('event.langchange', evts.length > 0 && evts[evts.length - 1].detail.lang === 'en',
    evts.length ? evts[evts.length - 1].detail.lang : 'yok');

const host = new El('nav');
w._dom.body.appendChild(host);
const sw = I.mountSwitcher(host);
check('switcher.mounted', !!sw && host.children.length === 1, host.children.length);
const sel = sw.querySelector('select[data-hrma-lang-select]');
check('switcher.hasSelect', !!sel);
check('switcher.optionCount', sel && sel.options.length === I.languages().length,
    sel ? sel.options.length : 0);
check('switcher.value', sel && sel.value === I.lang, sel ? sel.value : '');
check('switcher.idempotent', I.mountSwitcher(host) === sw && host.children.length === 1);
sel.value = 'tr';
sel.fire('change');
check('switcher.changesLang', I.lang === 'tr', I.lang);
check('switcher.optionLabelsTranslated', sel.options[0].textContent === 'English', sel.options[0].textContent);
I.setLang('en');
check('switcher.syncsOnSetLang', sel.value === 'en', sel.value);
check('switcher.noContainerSafe', (function () { try { I.mountSwitcher(); return true; } catch (e) { return false; } })());

check('has.true', I.has('nav.home') === true);
check('has.false', I.has('yok.olan') === false);

I.setLang('tr');
check('storage.persisted', w.localStorage.getItem('hrma_lang') === 'tr', w.localStorage.getItem('hrma_lang'));
check('storage.htmlLang', w.document.documentElement.getAttribute('lang') === 'tr',
    w.document.documentElement.getAttribute('lang'));

process.stdout.write(JSON.stringify(results));
"""


@pytest.fixture(scope='module')
def harness_results(tmp_path_factory):
    node = shutil.which('node')
    if node is None:
        pytest.skip('node kurulu değil')
    script = tmp_path_factory.mktemp('i18n') / 'harness.js'
    script.write_text(HARNESS_JS, encoding='utf-8')
    proc = subprocess.run([node, str(script), str(I18N_JS)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, 'i18n davranış koşumu çöktü:\n%s' % proc.stderr[-3000:]
    return json.loads(proc.stdout)


def test_behaviour_harness_ran(harness_results):
    assert len(harness_results) >= 40, 'koşum beklenenden az kontrol çalıştırdı'


def test_behaviour_all_checks_pass(harness_results):
    failed = [r for r in harness_results if not r['ok']]
    detail = '\n'.join('  %s -> %s' % (r['name'], r['detail'][:150]) for r in failed)
    assert not failed, 'i18n davranış sözleşmesi bozuldu:\n%s' % detail


# --------------------------------------------------------------------------
# 7. Denetçilerin kendi doğruluğu
# --------------------------------------------------------------------------
# Bu testler ürünü değil, yukarıdaki heuristikleri sınar. Heuristik sessizce
# körleşirse (her şeyi 'temiz' görürse) diğer testler işe yaramaz hâle gelir.

def test_ascii_slip_detector_catches_known_slips():
    kotu = [
        'Oda basinci', 'Sicaklik profili', 'Yakit kutlesi', 'Tasarim raporu',
        'Guvenlik katsayisi', 'Regresyon hizi', 'Bogaz capi', 'Enjektor tipi',
        'Cikti dosyasi', 'Ozgul itki', 'Yukleniyor', 'Ayarlari degistir',
        'Yogunluk', 'Kalinlik', 'Baslangic degeri', 'Sogutma kanali',
        'Gecis analizi', 'Gecici dosya',
    ]
    kacan = [metin for metin in kotu if ascii_slip(metin) is None]
    assert not kacan, 'ASCII kaçışı yakalanamadı: %s' % kacan


def test_ascii_slip_detector_accepts_correct_turkish():
    iyi = [
        'Oda basıncı', 'Sıcaklık profili', 'Yakıt kütlesi', 'Tasarım raporu',
        'Güvenlik katsayısı', 'Regresyon hızı', 'Boğaz çapı', 'Enjektör tipi',
        'Çıktı dosyası', 'Özgül itki (Isp)', 'Yükleniyor', 'Ayarları değiştir',
        'KATI YAKIT', 'SIVI OKSİTLEYİCİ', 'İtki eğrisi', 'NASA CEA doğrulaması',
        'BATES grain geometrisi', '6-DOF yörünge analizi', 'Ortalama akış hızı',
        'Toplam yanma süresi', 'Cidar sıcaklığı', 'L* karakteristik uzunluk',
        'O/F oranı', 'CSV olarak dışa aktar', 'Emniyet katsayısı yeterli',
        # 'gecikme' baştan sona ASCII ve DOĞRU yazımdır ('geci' önek
        # çarpışması CI'da yanlış alarm vermişti, 2026-08-16):
        'Tepe Sonrası Açılma Gecikmesi (s)', 'Araç bu gecikme boyunca düşer',
    ]
    yanlis_pozitif = [(metin, ascii_slip(metin)) for metin in iyi if ascii_slip(metin)]
    assert not yanlis_pozitif, 'Doğru yazılmış metne yanlış alarm: %s' % yanlis_pozitif


def test_translation_copy_detector_sanity():
    assert _looks_translated('Thrust', 'İtki')
    assert not _looks_translated('Chamber pressure', 'Chamber pressure')
    # Teknik kısaltmalar ve birimler iki dilde aynı kalabilir.
    assert _looks_translated('Isp (s)', 'Isp (s)')
    assert _looks_translated('bar', 'bar')
    assert _looks_translated('NASA CEA', 'NASA CEA')
    assert _looks_translated('O/F', 'O/F')
    assert _looks_translated('3D / STL / STEP', '3D / STL / STEP')


SAMPLE_DICT_JS = """\
/* Örnek sözlük — i18n.js'ten sonra yüklenir. Yorumdaki kesme işareti
   ayrıştırıcıyı bozmamalı: 'tırnak', "çift tırnak", { süslü }. */
(function (global) {
    'use strict';
    var DICT = {
        en: {
            'panel.thrust': 'Thrust',
            'panel.pc': 'Chamber pressure {value} bar',
            'panel.quote': 'It\\'s fine'
        },
        tr: {
            'panel.thrust': 'İtki',
            'panel.pc': 'Oda basıncı {value} bar',
            'panel.quote': 'Sorun değil'
        }
    };
    // Kayıt: i18n.js henüz yüklenmemişse kuyruğa bırak
    if (global.I18N && global.I18N.register) {
        global.I18N.register(DICT, 'i18n_sample.js');
    } else {
        (global.__I18N_PENDING = global.__I18N_PENDING || []).push(DICT);
    }
})(typeof window !== 'undefined' ? window : this);
"""


def test_dict_parser_handles_documented_file_shape(tmp_path):
    """Ayrıştırıcı, i18n.js'te belgelenen dosya kalıbını okuyabilmeli."""
    sample = tmp_path / 'i18n_sample.js'
    sample.write_text(SAMPLE_DICT_JS, encoding='utf-8')

    en = dict_pairs(sample, 'en')
    tr = dict_pairs(sample, 'tr')
    assert en is not None and tr is not None, 'dil blokları bulunamadı'
    assert dict(en)['panel.thrust'] == 'Thrust'
    assert dict(tr)['panel.thrust'] == 'İtki'
    assert dict(tr)['panel.pc'] == 'Oda basıncı {value} bar'
    assert dict(en)['panel.quote'] == "It's fine", 'kaçışlı tırnak çözülmedi'
    assert [k for k, _ in en] == [k for k, _ in tr], 'anahtar sırası/kümesi tutmuyor'
    assert ascii_slip(dict(tr)['panel.pc']) is None
