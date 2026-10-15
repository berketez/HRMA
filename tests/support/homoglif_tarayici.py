# -*- coding: utf-8 -*-
"""Karıştırılabilir (homoglif) tanımlayıcı tarayıcısı — TEK KAYNAK.

ÖH D27 · defter OH-D26-14 (D26 yapisal-sistem a1 öğretici bulgusu).

ÖLÇÜLEN KUSUR
-------------
Depoda iki tanımlayıcıda Latin harf yerine KİRİL homoglifi vardı:

* ``tests/test_d26_arayuz_a2.py`` — ``…_baglі`` (son harf U+0456 CYRILLIC
  SMALL LETTER BYELORUSSIAN-UKRAINIAN I),
* ``tests/test_z5s_isi_zinciri.py`` — ``aciklik`` yerel adı (U+043A
  CYRILLIC SMALL LETTER KA), üç kullanım. (ÖH D28 · termo-ucus a1,
  OH-D27-12: dosyanın sahibi ÖDEDİ — depo nüfusu 3 → 0.)

Bunlar ekranda Latin ``i`` / ``k`` ile AYNI görünür. Sonuç, sessiz ve
tehlikelidir: düğüm adı elle (Latin harfle) yazılıp ``pytest dosya::ad``
koşulduğunda pytest **istisna atmaz**; "no tests ran" basar ve çıkış kodu
``4`` (``USAGE_ERROR`` — düğüm bulunamadı) döner. ``-k`` seçicisiyle aynı
durum ``5`` (``NO_TESTS_COLLECTED``) verir. Ters-mutasyon turunda bu,
"bekçi kırmızı olmadı" diye değil "bekçi koştu ve yeşildi" diye okunur —
yani kusuru gördüğü iddia edilen bekçi HİÇ KOŞMAMIŞTIR. D26 a1'de üç
kayıt tam olarak böyle sessizce eksik kalmıştı.

KURAL
-----
1. ``.py`` / ``.js`` / ``.html`` kaynaklarında TANIMLAYICI adları
   karıştırılabilir Kiril/Yunan harfi taşıyamaz (nüfus tavanı SIFIR;
   D27'nin tek adlı muafiyeti D28'de ödendi, MUAFİYET YOKTUR).
2. pytest DÜĞÜM adları (``test_*`` / ``Test*``) ASCII-dışı harf
   taşıdığında envantere girer; envanter TEK YÖNLÜDÜR (büyüyemez).
3. pytest'i kabuk üzerinden çağıran her mutasyon düzeneği ``no tests
   ran`` / çıkış kodu ``4`` veya ``5`` durumunu **KIRMIZI** saymak
   zorundadır (bkz. :func:`bos_kosum_mu`). "Kırmızı çıkmadı" ile "hiç
   koşmadı" AYNI ŞEY DEĞİLDİR.

Bu modül ölçümün ve bekçinin ORTAK kaynağıdır: aynı kod hem taban
ağacında (``docs/scofield/raw/OH/D27/bekci-cevirisi/a1/olcum.py``) hem
bekçide (``tests/test_d27_bekci_cevirisi_a1.py``) koşar.
"""

import ast
import os
import re
import unicodedata

__all__ = [
    'KIRIL_HOMOGLIFLER', 'YUNAN_HOMOGLIFLER', 'HOMOGLIFLER', 'ATLA_DIZIN',
    'PYTEST_BOS_KOSUM_CIKIS_KODU', 'PYTEST_DUGUM_BULUNAMADI_CIKIS_KODU',
    'PYTEST_BOS_KOSUM_CIKIS_KODLARI', 'bos_kosum_mu', 'kunye',
    'karistirilabilir_harfler', 'py_tanimlayicilari', 'js_kiril_adlari',
    'html_kiril_kimlikleri', 'pytest_dugum_adlari', 'ascii_disi_dugumler',
    'tara',
]

#: Yürüyüşte atlanan dizin adları (``vendor``: üçüncü taraf paketler).
ATLA_DIZIN = frozenset({
    '.git', '__pycache__', 'node_modules', '.pytest_cache', 'venv',
    '.venv', 'build', 'dist', '.mypy_cache', 'htmlcov', 'vendor',
})

#: KİRİL homoglifleri -> görsel Latin karşılığı. Bu depoda Kiril harfin
#: MEŞRU kullanımı YOKTUR (arayüz dilleri Türkçe/İngilizce, ikisi de
#: Latin); dolayısıyla nerede görünürse görünsün kusurdur.
KIRIL_HOMOGLIFLER = {
    'а': 'a', 'в': 'b', 'е': 'e', 'ѕ': 's', 'і': 'i', 'ј': 'j',
    'к': 'k', 'м': 'm', 'о': 'o', 'р': 'p', 'с': 'c', 'т': 't',
    'у': 'y', 'х': 'x', 'һ': 'h', 'ԁ': 'd', 'ԛ': 'q', 'ѡ': 'w',
    'А': 'A', 'В': 'B', 'Е': 'E', 'Ѕ': 'S', 'І': 'I', 'Ј': 'J',
    'К': 'K', 'М': 'M', 'Н': 'H', 'О': 'O', 'Р': 'P', 'С': 'C',
    'Т': 'T', 'У': 'Y', 'Х': 'X',
}

#: YUNAN homoglifleri. DİKKAT — Yunan harfi bu depoda MEŞRUDUR: arayüz
#: etiketlerinde ve grafik eksenlerinde fizik gösterimi olarak geçer
#: (``ρ``, ``α``, ``ε``, ``τ``, ``ν``, ``CN_α``). Bu yüzden Yunan kuralı
#: YALNIZ Python TANIMLAYICILARINA uygulanır; JS/HTML metnine değil.
#: (Ölçüm: taban ağacında JS'te 105 Yunan geçişi — hepsi kullanıcıya
#: dönük etiket dizgesi; Python tanımlayıcılarında 0.)
YUNAN_HOMOGLIFLER = {
    'α': 'a', 'β': 'b', 'ε': 'e', 'ι': 'i', 'κ': 'k', 'ν': 'v',
    'ο': 'o', 'ρ': 'p', 'τ': 't', 'υ': 'u', 'χ': 'x',
    'Α': 'A', 'Β': 'B', 'Ε': 'E', 'Ζ': 'Z', 'Η': 'H', 'Ι': 'I',
    'Κ': 'K', 'Μ': 'M', 'Ν': 'N', 'Ο': 'O', 'Ρ': 'P', 'Τ': 'T',
    'Υ': 'Y', 'Χ': 'X',
}

#: Python tanımlayıcıları için TAM küme.
HOMOGLIFLER = dict(KIRIL_HOMOGLIFLER, **YUNAN_HOMOGLIFLER)

#: pytest'in "hiç test toplanmadı" çıkış kodu (``pytest.ExitCode
#: .NO_TESTS_COLLECTED``): ``-k`` seçicisi hiçbir şeyi tutmadığında.
PYTEST_BOS_KOSUM_CIKIS_KODU = 5

#: ``pytest.ExitCode.USAGE_ERROR``: ``dosya::dugum`` biçiminde verilen
#: düğüm BULUNAMADIĞINDA dönen kod. ÖLÇÜLDÜ (ÖH D27, bu dosyanın
#: bekçisi): homoglif vakasının GERÇEK yolu budur — mutasyon düzenekleri
#: düğümü ``::`` ile seçer, pytest ``4`` + "no tests ran" +
#: "ERROR: not found" basar. Yalnız 5'e bakan bir düzenek bunu kaçırır.
PYTEST_DUGUM_BULUNAMADI_CIKIS_KODU = 4

#: Boş koşum sayılan çıkış kodları.
PYTEST_BOS_KOSUM_CIKIS_KODLARI = frozenset({
    PYTEST_BOS_KOSUM_CIKIS_KODU, PYTEST_DUGUM_BULUNAMADI_CIKIS_KODU})

#: Boş koşumun metin imzaları (pytest sürümleri arası).
_BOS_IMZALAR = ('no tests ran', 'no tests collected', 'collected 0 items',
                'error: not found')


def bos_kosum_mu(cikis_kodu, cikti=''):
    """Bir pytest koşumu HİÇ test koşmadan bitti mi?

    Mutasyon düzeneklerinin sözleşmesi: bu ``True`` dönerse sonuç
    "yeşil" değil **KIRMIZI**'dır — düğüm adı yanlış yazılmış (çoğu kez
    homoglif yüzünden) ya da seçici hiçbir şeyi tutmamıştır.

    Karar ÖNCE çıkış koduna bakar: ``4`` (``USAGE_ERROR``, ``::`` ile
    verilen düğüm bulunamadı) ve ``5`` (``NO_TESTS_COLLECTED``, seçici
    boş) boş koşumdur. Metin imzalarına YALNIZ çıkış kodu ``0`` iken
    bakılır; ``1`` (``TESTS_FAILED``) tanım gereği koşmuş demektir.

    Metin kontrolünün koda bağlanması zorunludur: bu deponun kendi bekçi
    iletileri "no tests ran" ifadesini AÇIKLAMA olarak taşır (bkz.
    ``tests/test_d27_bekci_cevirisi_a1.py``), yani ham metin araması
    gerçek bir kırmızıyı "boş koşum" diye yanlış etiketler. ÖLÇÜLDÜ:
    ÖH D27 mutasyon turu M1, ilk denemede tam olarak buna takıldı.
    """
    if cikis_kodu in PYTEST_BOS_KOSUM_CIKIS_KODLARI:
        return True
    if cikis_kodu != 0:
        return False
    metin = (cikti or '').lower()
    return any(imza in metin for imza in _BOS_IMZALAR)


def kunye(harf):
    """Bir karakterin künyesi: kod noktası, Unicode adı, Latin ikizi."""
    try:
        ad = unicodedata.name(harf)
    except ValueError:
        ad = 'ADSIZ'
    return {'kod': 'U+%04X' % ord(harf), 'ad': ad,
            'latin_ikizi': HOMOGLIFLER.get(harf, '')}


def karistirilabilir_harfler(ad, kume=None):
    """``ad`` içindeki karıştırılabilir harfler (varsayılan: Kiril+Yunan)."""
    kume = HOMOGLIFLER if kume is None else kume
    return [c for c in ad if c in kume]


def _ascii_disi(ad):
    return [c for c in ad if ord(c) > 127]


def _dosyalar(kok, uzantilar):
    for dizin, altlar, adlar in os.walk(kok):
        altlar[:] = [a for a in altlar if a not in ATLA_DIZIN]
        for ad in sorted(adlar):
            if os.path.splitext(ad)[1] in uzantilar:
                yield os.path.join(dizin, ad)


def _bagil(tam, kok):
    return os.path.relpath(tam, kok).replace(os.sep, '/')


def py_tanimlayicilari(yol):
    """(satır, tür, ad) — Python tanımlayıcıları, AST ile.

    AST kullanıldığı için yorum ve dizge içindeki metinler SAYILMAZ;
    yalnız gerçek tanımlayıcılar taranır.
    """
    try:
        agac = ast.parse(open(yol, encoding='utf-8').read(), filename=yol)
    except (SyntaxError, UnicodeDecodeError, ValueError):
        return
    for d in ast.walk(agac):
        if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef,
                          ast.ClassDef)):
            yield d.lineno, 'tanim', d.name
        elif isinstance(d, ast.Name):
            yield d.lineno, 'ad', d.id
        elif isinstance(d, ast.Attribute):
            yield d.lineno, 'oznitelik', d.attr
        elif isinstance(d, ast.arg):
            yield d.lineno, 'parametre', d.arg
        elif isinstance(d, ast.keyword) and d.arg:
            yield d.lineno, 'anahtar', d.arg


# JS/HTML'de AST yok; tarama KARAKTER düzeyinde yapılır ve YALNIZ Kiril
# aranır. Kiril bu depoda hiçbir bağlamda (kod, yorum, kullanıcı metni)
# meşru değildir; bu yüzden dizge/yorum ayrımına gerek kalmaz, yanlış
# pozitif de vermez. Yunan harfleri burada BİLEREK aranmaz — etiket
# metinlerinde fizik gösterimidir.
_JS_ADIMSI = re.compile(r'[\w$]+', re.UNICODE)
_HTML_KIMLIK = re.compile(
    r'\b(?:id|class|name|for|data-[\w-]+)\s*=\s*"([^"]*)"')


def js_kiril_adlari(yol):
    """(satır, tür, ad) — JS kaynağında KİRİL harf taşıyan ad benzeri
    diziler."""
    try:
        satirlar = open(yol, encoding='utf-8').read().splitlines()
    except (UnicodeDecodeError, ValueError):
        return
    for no, satir in enumerate(satirlar, 1):
        if not any(c in KIRIL_HOMOGLIFLER for c in satir):
            continue
        for m in _JS_ADIMSI.finditer(satir):
            if karistirilabilir_harfler(m.group(0), KIRIL_HOMOGLIFLER):
                yield no, 'js', m.group(0)


def html_kiril_kimlikleri(yol):
    """(satır, tür, ad) — HTML ``id/class/name/for/data-*`` değerlerinde
    KİRİL harf."""
    try:
        satirlar = open(yol, encoding='utf-8').read().splitlines()
    except (UnicodeDecodeError, ValueError):
        return
    for no, satir in enumerate(satirlar, 1):
        if not any(c in KIRIL_HOMOGLIFLER for c in satir):
            continue
        for m in _HTML_KIMLIK.finditer(satir):
            for parca in m.group(1).split():
                if karistirilabilir_harfler(parca, KIRIL_HOMOGLIFLER):
                    yield no, 'html', parca


def pytest_dugum_adlari(yol):
    """(satır, ad) — ``test_*`` işlev / ``Test*`` sınıf adları."""
    try:
        agac = ast.parse(open(yol, encoding='utf-8').read(), filename=yol)
    except (SyntaxError, UnicodeDecodeError, ValueError):
        return
    for d in ast.walk(agac):
        if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef,
                          ast.ClassDef)) and (
                d.name.startswith('test_') or d.name.startswith('Test')):
            yield d.lineno, d.name


def tara(kok, alt_dizinler=('hrma', 'tests', 'tools')):
    """Karıştırılabilir harf taşıyan TANIMLAYICILARI döndürür.

    Kural farkı bilinçlidir:

    * ``.py``  -> TANIMLAYICI adları, Kiril **ve** Yunan (AST ile; yorum
      ve dizgeler taranmaz, Yunan bir Python adında meşru değildir),
    * ``.js`` / ``.html`` -> yalnız **Kiril** (Yunan, etiket metninde
      fizik gösterimi olarak meşrudur).

    Dönen her kayıt: ``{dosya, satir, tur, ad, kacak}``.
    """
    bulgular = []
    for alt in alt_dizinler:
        taban = os.path.join(kok, alt)
        if not os.path.isdir(taban):
            continue
        for yol in _dosyalar(taban, {'.py'}):
            for satir, tur, ad in py_tanimlayicilari(yol):
                kotu = karistirilabilir_harfler(ad)
                if kotu:
                    bulgular.append({'dosya': _bagil(yol, kok),
                                     'satir': satir, 'tur': tur, 'ad': ad,
                                     'kacak': [kunye(c) for c in kotu]})
        for uzanti, uretec in (('.js', js_kiril_adlari),
                               ('.html', html_kiril_kimlikleri)):
            for yol in _dosyalar(taban, {uzanti}):
                for satir, tur, ad in uretec(yol):
                    kotu = karistirilabilir_harfler(ad, KIRIL_HOMOGLIFLER)
                    bulgular.append({'dosya': _bagil(yol, kok),
                                     'satir': satir, 'tur': tur, 'ad': ad,
                                     'kacak': [kunye(c) for c in kotu]})
    return sorted(bulgular, key=lambda b: (b['dosya'], b['satir'], b['ad']))


def ascii_disi_dugumler(kok):
    """ASCII-dışı harf taşıyan pytest düğüm adları (``tests/`` altı)."""
    bulgular = []
    taban = os.path.join(kok, 'tests')
    for yol in _dosyalar(taban, {'.py'}):
        for satir, ad in pytest_dugum_adlari(yol):
            kotu = _ascii_disi(ad)
            if kotu:
                bulgular.append({'dosya': _bagil(yol, kok), 'satir': satir,
                                 'ad': ad,
                                 'kacak': [kunye(c) for c in kotu],
                                 'homoglif': bool(
                                     karistirilabilir_harfler(ad))})
    return sorted(bulgular, key=lambda b: (b['dosya'], b['satir']))
