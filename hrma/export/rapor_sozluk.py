"""Rapor metinlerinin EKRANLA ortak kaynağı — arayüz sözlükleri (tek yer).

V306/RAPOR-HATA (M-SIVI-13 / M-KATI-3 / M-SIVI-14). ÖLÇÜLDÜ (mühendis turu,
taban 686c34b98, ``docs/scofield/raw/OH/V306/rapor/once/*.txt``): indirilen
PDF'lerde çözücü uyarıları ``warn.solid.initial_mass_flux_high
(mass_flux_kg_m2s=2455; threshold_kg_m2s=1400)`` gibi HAM KOD + parametre
dökümü, bazıları doldurulmamış şablon (``n = {exponent}``) olarak
basılıyordu. Kök: rapor katmanının sözlüğü yoktu ("arka uç dilsizdir");
cümleyi ekranın sözlüğü (``hrma/static/js/i18n_*.js``) kurar ve rapor ona
erişemiyordu.

Bu modül o sözlükleri OKUR (yazmaz, kopyalamaz): aynı anahtar ekranda ve
belgede aynı metni verir; ekrandaki metin değişirse (ör. sıvı başlık Isp
adı) belge de değişir. Sözlük dosyalarının sözleşmesi (i18n_common.js
başlığı): dil bloğu ``en: {`` / ``tr: {``, satır başına bir çift, anahtar ve
değer TEK TIRNAK içinde, değer tek satırda.

Kural (doktrin 1): anahtar sözlükte yoksa METİN UYDURULMAZ; çağıran kaydın
kendi yedek cümlesine (``fallback``) düşer, o da yoksa None döner.
"""
import os
import re
from functools import lru_cache
from typing import Any, Dict, Mapping, Optional

from hrma.utils.input_guard import finite_number

#: Sözlük parçaları (ekranın yükleme sırasıyla; aynı anahtar iki dosyada
#: varsa ilk bulunan kullanılır).
RAPOR_SOZLUK_PARCALARI = ('i18n.js', 'i18n_common.js', 'i18n_pages.js',
                    'i18n_charts.js', 'i18n_advanced.js', 'i18n_shell.js',
                    'i18n_formulas.js', 'i18n_launch_site.js')

DILLER = ('en', 'tr')

_JS_DIZINI = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'static', 'js')

_CIFT = re.compile(r"^\s*'((?:[^'\\]|\\.)*)'\s*:\s*'((?:[^'\\]|\\.)*)'\s*,?\s*$",
                   re.M)
_KACIS = re.compile(r"\\(u\{[0-9a-fA-F]+\}|u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|.)",
                    re.S)
_YER = re.compile(r'\{(\w+)\}')


def _kacis_coz(metin: str) -> str:
    """JS tek tırnaklı dize kaçışlarını çözer (\\' \\n \\uXXXX ...)."""
    def _bir(m):
        k = m.group(1)
        if k.startswith('u{'):
            return chr(int(k[2:-1], 16))
        if k.startswith('u') and len(k) == 5:
            return chr(int(k[1:], 16))
        if k.startswith('x') and len(k) == 3:
            return chr(int(k[1:], 16))
        return {'n': '\n', 't': '\t', 'r': '\r', '0': '\0'}.get(k, k)
    return _KACIS.sub(_bir, metin)


def _blok(kaynak: str, dil: str) -> Optional[str]:
    """``<dil>: {`` bloğunun gövdesi (dize içindeki parantezler sayılmaz)."""
    m = re.search(r'^\s*%s\s*:\s*\{' % dil, kaynak, re.M)
    if not m:
        return None
    i = m.end()
    derinlik, tirnak = 1, None
    while i < len(kaynak):
        ch = kaynak[i]
        if tirnak:
            if ch == '\\':
                i += 2
                continue
            if ch == tirnak:
                tirnak = None
        elif ch in '\'"`':
            tirnak = ch
        elif ch == '/' and kaynak.startswith('/*', i):
            j = kaynak.find('*/', i + 2)
            i = len(kaynak) if j < 0 else j + 2
            continue
        elif ch == '/' and kaynak.startswith('//', i):
            j = kaynak.find('\n', i)
            i = len(kaynak) if j < 0 else j
            continue
        elif ch == '{':
            derinlik += 1
        elif ch == '}':
            derinlik -= 1
            if derinlik == 0:
                return kaynak[m.end():i]
        i += 1
    return None


@lru_cache(maxsize=None)
def sozluk(dil: str = 'en') -> Dict[str, str]:
    """Ekran sözlüğünün ``dil`` bloğu (bütün parçalar birleşik)."""
    if dil not in DILLER:
        raise ValueError('desteklenmeyen dil: %r' % (dil,))
    sonuc: Dict[str, str] = {}
    for ad in RAPOR_SOZLUK_PARCALARI:
        yol = os.path.join(_JS_DIZINI, ad)
        try:
            with open(yol, encoding='utf-8') as fh:
                kaynak = fh.read()
        except OSError:
            continue
        govde = _blok(kaynak, dil)
        if not govde:
            continue
        for anahtar, deger in _CIFT.findall(govde):
            sonuc.setdefault(_kacis_coz(anahtar), _kacis_coz(deger))
    return sonuc


#: Değeri yayımlanmamış (None) ya da kayıtta hiç olmayan yer tutucunun
#: yerine basılan işaret — ham ``{ad}`` ya da Python ``None`` basılmaz.
YAYIMLANMADI = '—'
_EVET_HAYIR = {'en': ('yes', 'no'), 'tr': ('evet', 'hayır')}


def _deger_metni(deger: Any, dil: str) -> str:
    """Yer tutucuya giren değer: sayı rapor kuralıyla, iç içe kayıt cümleyle."""
    if deger is None:
        return YAYIMLANMADI
    if isinstance(deger, bool):
        return _EVET_HAYIR[dil][0 if deger else 1]
    if isinstance(deger, int):
        return str(deger)
    if isinstance(deger, float):
        if finite_number(deger) is None:      # sonlu-sayı kararı merkezden
            return str(deger)
        kisa = float('%.6g' % deger)
        metin = repr(kisa)
        metin = metin[:-2] if metin.endswith('.0') else metin
        return metin.replace('.', ',') if dil == 'tr' else metin
    if isinstance(deger, Mapping):
        ic = uyari_cumlesi(deger, dil)
        if ic:
            return ic
        return '; '.join('%s: %s' % (k, _deger_metni(v, dil))
                         for k, v in deger.items())
    if isinstance(deger, (list, tuple)):
        return ', '.join(_deger_metni(v, dil) for v in deger)
    return str(deger)


def doldur(sablon: str, params: Optional[Mapping], dil: str = 'en') -> str:
    """``{ad}`` yer tutucularını ``params``tan doldurur (ekranın I18N.tf'si).

    Değeri olmayan yer tutucu OLDUĞU GİBİ kalır — çağıran bunu
    :func:`bos_yer_tutucu` ile denetler ve kaydı yedek cümleye çevirmez.
    """
    p = params if isinstance(params, Mapping) else {}
    return _YER.sub(lambda m: (_deger_metni(p[m.group(1)], dil)
                               if m.group(1) in p else m.group(0)), sablon)


def bos_yer_tutucu(metin: str) -> bool:
    """Metinde doldurulmamış ``{ad}`` kaldı mı?"""
    return bool(_YER.search(metin or ''))


def metin(anahtar: str, dil: str = 'en', params: Optional[Mapping] = None,
          yedek: Optional[str] = None) -> Optional[str]:
    """Sözlük metni (doldurulmuş). Anahtar yoksa ``yedek`` (doldurulmuş)."""
    sablon = sozluk(dil).get(anahtar)
    if sablon is None:
        sablon = yedek
    if sablon is None:
        return None
    return doldur(sablon, params, dil)


def uyari_cumlesi(kayit: Any, dil: str = 'en') -> Optional[str]:
    """Çözücü uyarı kaydının ``{code, params, fallback}`` OKUNUR cümlesi.

    Ekranın ``warnToText``ı ile aynı sıra: sözlükteki kod metni, yoksa
    kaydın kendi ``fallback`` cümlesi; ikisi de parametrelerle doldurulur.
    Hiçbir aday tam dolmazsa ilk aday kullanılır ve kayıtta olmayan yer
    tutucu :data:`YAYIMLANMADI` olur. Hiç aday yoksa None (ham kod basılmaz;
    çağıran adıyla beyan eder).
    """
    if not isinstance(kayit, Mapping):
        return None
    kod = kayit.get('code')
    params = kayit.get('params')
    adaylar = []
    if isinstance(kod, str) and kod:
        adaylar.append(sozluk(dil).get(kod))
    for alan in ('fallback', 'message', 'text'):
        deger = kayit.get(alan)
        if isinstance(deger, str) and deger.strip() and deger != kod:
            adaylar.append(deger)
    ilk = None
    for sablon in adaylar:
        if not sablon:
            continue
        dolu = doldur(sablon, params, dil)
        if not bos_yer_tutucu(dolu):
            return dolu
        if ilk is None:
            ilk = dolu
    if ilk is not None:
        # Hiçbir aday tam dolmadı: kayıtta olmayan yer tutucu ham basılmaz,
        # yayımlanmadı işaretiyle kalır (cümlenin geri kalanı kaybolmaz).
        return _YER.sub(YAYIMLANMADI, ilk)
    return None


# ===========================================================================
# V306/RAPOR-DİL — RAPORUN DİLİ (istek dili, sayı biçimi, metin çevirisi)
# ===========================================================================
#
# ÖLÇÜLEN KUSUR (RAPOR-HATA §5, taban 686c34b98; bu kulvarın ``once/``
# ölçümü): Türkçe arayüzden indirilen PDF TAMAMEN İngilizce iniyordu. İstek
# gövdesinde dil alanı yoktu ve üretici (``pdf_generator.py``) sabit
# İngilizce metin basıyordu; TR ve EN arayüzden inen belge içerikçe aynıydı.
#
# MEKANİZMA (ekranın ``I18N.chartText`` / ``I18N.serverText`` sözleşmesinin
# Python karşılığı; ``i18n_charts.js`` başlığı "ANAHTAR = İNGİLİZCE METNİN
# KENDİSİ"): üretici İngilizce metni KAYNAK olarak basmaya devam eder; belge
# kurulurken her metin parçası etkin dilin karşılığına çevrilir. Karşılık
# TEK yerden gelir: ekranın sözlükleri + raporun kendi sözlüğü
# (``i18n_report.js``, ``report.*``). Ekranda aynı İngilizcenin karşılığı
# varsa ONUNKİ kullanılır (aynı İngilizceye iki Türkçe yok); rapor sözlüğü
# yalnız ekranda olmayan metinleri taşır.
#
# Sıra (ekranın ``translateSegment`` / ``sunucuCevir`` sırası):
#   1. sözlükte birebir (normalize edilmiş) karşılık;
#   2. yer tutuculu sözlük metinleri ({ad}) DESEN olarak (yakalanan değer
#      kendisi de çevrilir, sayı TR ondalığına geçer);
#   3. ekranın sunucu ve grafik desenleri (``i18n_charts.js`` MSG_PATTERNS +
#      PATTERNS — dize şablonlu kurallar dosyadan OKUNUR, kopyalanmaz) ve
#      sonradan eklenen kuyruk cümleleri (KUYRUK_DESENLERI), hat önekleri;
#   4. yapı kuralları: "Etiket: değer", "Etiket — değer", "Taban (ek)",
#      madde imi; cümle cümle bölme;
#   5. sayı/birim parçası: yalnız ondalık ayracı (TR virgül; binlik ayracı
#      YOK — ekranın ``I18N.number`` kuralı).
# Hiçbiri tutmazsa metin AYNEN kalır (asla anahtar, asla boş) ve
# "çevrilemeyen" kaydına girer: ölçüm ve bekçi o kayıttan sayar; çözücünün
# karşılığı olmayan İngilizce cümleleri DEVİR DİL-SUNUCU listesine gider.
#
# Dil 'en' ise HİÇBİR metne dokunulmaz (EN belge bit-aynı metin).

import contextvars
import html as _html
from contextlib import contextmanager
from xml.sax.saxutils import escape as _xml_kacis

#: Raporun kendi sözlük dosyası (ekran sayfaları YÜKLEMEZ; yalnız bu modül
#: okur). Ekran parçalarından SONRA okunur: ekran metni önceliklidir.
RAPOR_SOZLUK_DOSYASI = 'i18n_report.js'
RAPOR_SOZLUK_PARCALARI = RAPOR_SOZLUK_PARCALARI + (RAPOR_SOZLUK_DOSYASI,)

#: İstek gövdesinde ``lang`` yoksa kullanılan dil (beyanlı varsayılan; API
#: notu ``/api/export-pdf`` ucunda).
VARSAYILAN_DIL = 'en'

_ETKIN_DIL = contextvars.ContextVar('hrma_rapor_dili', default=VARSAYILAN_DIL)
_CEVRILMEYEN = contextvars.ContextVar('hrma_rapor_cevrilmeyen', default=None)


def etkin_dil() -> str:
    """Belge kurulurken etkin olan dil (bağlam dışında 'en')."""
    return _ETKIN_DIL.get()


@contextmanager
def dil_baglami(dil: str):
    """``with dil_baglami('tr'):`` — bloğun içinde kurulan belge metinleri."""
    if dil not in DILLER:
        raise ValueError('desteklenmeyen rapor dili: %r' % (dil,))
    jeton = _ETKIN_DIL.set(dil)
    try:
        yield dil
    finally:
        _ETKIN_DIL.reset(jeton)


@contextmanager
def cevrilmeyen_kaydi():
    """Bloğun içinde ÇEVRİLEMEYEN metin parçalarını toplar (ölçüm/bekçi)."""
    liste: list = []
    jeton = _CEVRILMEYEN.set(liste)
    try:
        yield liste
    finally:
        _CEVRILMEYEN.reset(jeton)


_DESEN_KAYDI = contextvars.ContextVar('hrma_rapor_desen_kaydi', default=None)


@contextmanager
def desen_kaydi():
    """Bloğun içinde EKRANIN sunucu/grafik desenlerinin (i18n_charts.js)
    ürettiği çevirileri toplar: bu metinlerin içeriği ekran sözlüğünündür
    (bekçi, içlerindeki adları bu kulvarın metni saymaz)."""
    liste: list = []
    jeton = _DESEN_KAYDI.set(liste)
    try:
        yield liste
    finally:
        _DESEN_KAYDI.reset(jeton)


def _kaydet(parca: str) -> None:
    liste = _CEVRILMEYEN.get()
    if liste is not None:
        liste.append(parca)


def normalize(metin: str) -> str:
    """Kırpma + çoklu boşluğu teke indirme (ekranın ``normalize``u)."""
    return ' '.join(str(metin).split())


# --- sayı biçimi ------------------------------------------------------------
#: Ekranın ``I18N.decimalText`` kapsamı: BAŞTAN SONA sayı ve ondalık kesirli
#: metin (sürüm '2.6.27', tarih, birimli metin DEĞİŞMEZ).
_SAF_ONDALIK = re.compile(r'^[+-]?\d+\.\d+(?:[eE][+-]?\d+)?$')
#: Cümle/ölçü içindeki ondalık sayı: önünde/arkasında harf, rakam, nokta ya
#: da alt çizgi yoksa (sürüm 'v3.0.5', 'eq. 2.3a', alan adı 'x_1.2' dokunulmaz).
_ICTEKI_ONDALIK = re.compile(
    r'(?<![\w.])([+-]?\d+)\.(\d+(?:[eE][+-]?\d+)?)(?![\w.])')
_YUZDE = re.compile(r'^([+-]?\d+(?:[.,]\d+)?)\s?%$')


def ondalik_metni(metin: str, dil: Optional[str] = None) -> str:
    """Önceden biçimlenmiş SAF sayı metninin ayracı (ekranın decimalText'i)."""
    dil = dil or etkin_dil()
    if dil != 'tr' or not isinstance(metin, str):
        return metin
    if _SAF_ONDALIK.match(metin):
        return metin.replace('.', ',', 1)
    return metin


def yakalanan_metni(deger: str, dil: Optional[str] = None) -> str:
    """Desenden yakalanan değer (ekranın ``YAKALANAN``ı): saf ondalık → TR
    ayracı; 'sayı%' → TDK yazımı '%sayı'. Tanınmayan biçim DEĞİŞMEZ."""
    dil = dil or etkin_dil()
    if dil != 'tr' or not isinstance(deger, str) or not deger:
        return deger
    d = ondalik_metni(deger, dil)
    if d != deger:
        return d
    m = _YUZDE.match(deger)
    if m:
        return '%' + m.group(1).replace('.', ',')
    return deger


def olcu_metni(metin: str, dil: Optional[str] = None) -> str:
    """Sayı + birim parçasında YALNIZ ondalık ayracı (ekranın I18N_OLCU'su)."""
    dil = dil or etkin_dil()
    if dil != 'tr' or not isinstance(metin, str):
        return metin
    return _ICTEKI_ONDALIK.sub(r'\1,\2', metin)


def bicimli_sayi(metin: str, dil: Optional[str] = None) -> str:
    """Raporun ``_fmt`` çıktısı: saf ondalık ya da 'sayı%' etkin dilde."""
    return yakalanan_metni(metin, dil)


# --- ters sözlük ve şablonlar ----------------------------------------------
_TR_HARFI = re.compile('[çğıöşüÇĞİÖŞÜ]')
#: Biçim işareti taşıyan sözlük değeri ('<b>', '</sub>', '<br/>'): belge
#: parçası olarak eşleşmez ('SF < 1' gibi düz '<' işareti eşleşir).
_ISARETLI = re.compile(r'<[A-Za-z/!]')
_HARF = re.compile(r'[A-Za-z]')


#: Birleştirilen cümle PARÇALARININ anahtar öneki: bunlar yalnız anahtarla
#: (``metin``) çağrılır; ters aramaya ve şablonlara GİRMEZ ('with the {p1}'
#: gibi bir parça şablonu başka metinleri yutardı).
PARCA_ONEKI = 'report.part.'


@lru_cache(maxsize=None)
def ters_sozluk(dil: str) -> Dict[str, str]:
    """Normalize İngilizce metin → ``dil`` karşılığı (ekran önce, rapor sonra).

    Değerinde yer tutucu ya da biçim işareti ('<') olan kayıtlar birebir
    sözlüğe girmez (yer tutucular :func:`_sablonlar`a gider).
    """
    en, hedef = sozluk('en'), sozluk(dil)
    sonuc: Dict[str, str] = {}
    for anahtar, deger in en.items():
        karsilik = hedef.get(anahtar)
        if karsilik is None or _ISARETLI.search(deger) or _YER.search(deger) \
                or anahtar.startswith(PARCA_ONEKI):
            continue
        sonuc.setdefault(normalize(deger), karsilik)
    return sonuc


@lru_cache(maxsize=None)
def _sablonlar(dil: str):
    """Yer tutuculu sözlük metinleri → derlenmiş desen listesi.

    Yalnız en az iki sabit sözcüğü olan şablonlar alınır ('{a} ({b})' gibi
    yalnız yer tutucudan oluşan kalıp her metni yutardı).
    """
    en, hedef = sozluk('en'), sozluk(dil)
    sonuc = []
    gorulen = set()
    for anahtar, deger in en.items():
        karsilik = hedef.get(anahtar)
        if karsilik is None or _ISARETLI.search(deger) or not _YER.search(deger) \
                or anahtar.startswith(PARCA_ONEKI):
            continue
        sabit = _YER.sub(' ', deger)
        # Ekran şablonu en az iki sabit sözcük ister ('{a} ({b})' gibi kalıp
        # her metni yutardı); rapor sözlüğünün şablonları bu belge için
        # yazıldığından tek sözcük yeter ('Reference: {p1}', 'Chart {p1}').
        en_az = 1 if anahtar.startswith('report.') else 2
        if len(re.findall(r'[A-Za-z]{2,}', sabit)) < en_az:
            continue
        norm = normalize(deger)
        if norm in gorulen:
            continue
        gorulen.add(norm)
        adlar = []
        desen = ''
        son = 0
        for m in _YER.finditer(norm):
            desen += re.escape(norm[son:m.start()])
            # Yakalama cümle sınırını ('. B') aşmaz: şablon sonraki cümleyi
            # yutmasın (sayıdaki nokta '69.0' sınır değildir).
            desen += r'((?:(?!\. [A-Z]).)+?)'
            adlar.append(m.group(1))
            son = m.end()
        desen += re.escape(norm[son:])
        try:
            derli = re.compile('^' + desen + '$', re.S)
        except re.error:
            continue
        parcalar = [p.strip() for p in _YER.split(norm)[::2] if p.strip()]
        en_uzun = max(parcalar, key=len) if parcalar else ''
        sonuc.append((en_uzun, derli, adlar, karsilik))
    # Uzun sabitli şablon önce (daha özgül olan kazanır).
    sonuc.sort(key=lambda s: -len(s[0]))
    return tuple(sonuc)


# --- ekranın desen tabloları (i18n_charts.js) -------------------------------
def _js_dize_oku(kaynak: str, i: int):
    """``i``deki tırnaktan başlayan JS dizesi → (çözülmüş metin, son konum)."""
    tirnak = kaynak[i]
    j = i + 1
    while j < len(kaynak):
        if kaynak[j] == '\\':
            j += 2
            continue
        if kaynak[j] == tirnak:
            return _kacis_coz(kaynak[i + 1:j]), j + 1
        j += 1
    raise ValueError('kapanmayan dize')


def _js_regex_oku(kaynak: str, i: int):
    """``i``deki '/' ile başlayan regex sabiti → (kaynak, bayraklar, son)."""
    j = i + 1
    sinif = False
    while j < len(kaynak):
        ch = kaynak[j]
        if ch == '\\':
            j += 2
            continue
        if ch == '[':
            sinif = True
        elif ch == ']':
            sinif = False
        elif ch == '/' and not sinif:
            k = j + 1
            while k < len(kaynak) and kaynak[k].isalpha():
                k += 1
            return kaynak[i + 1:j], kaynak[j + 1:k], k
        j += 1
    raise ValueError('kapanmayan regex')


def _bosluk_atla(kaynak: str, i: int) -> int:
    while i < len(kaynak):
        if kaynak[i].isspace():
            i += 1
        elif kaynak.startswith('/*', i):
            j = kaynak.find('*/', i + 2)
            i = len(kaynak) if j < 0 else j + 2
        elif kaynak.startswith('//', i):
            j = kaynak.find('\n', i)
            i = len(kaynak) if j < 0 else j
        else:
            break
    return i


def _blok_sonu(kaynak: str, i: int, ac: str, kapa: str) -> int:
    """``i``deki ``ac`` ile açılan bloğun kapanışından sonraki konum
    (dize, yorum ve regex sabitleri sayılmaz)."""
    derinlik = 0
    onceki = ''
    while i < len(kaynak):
        ch = kaynak[i]
        if ch in '\'"`':
            _m, i = _js_dize_oku(kaynak, i)
            onceki = 'x'
            continue
        if kaynak.startswith('/*', i) or kaynak.startswith('//', i):
            i = _bosluk_atla(kaynak, i)
            continue
        if ch == '/' and onceki in ('(', ',', '=', ':', '[', '!', '&',
                                    '|', '?', '{', '}', ';', '+', ''):
            _r, _b, i = _js_regex_oku(kaynak, i)
            onceki = 'x'
            continue
        if ch == ac:
            derinlik += 1
        elif ch == kapa:
            derinlik -= 1
            if derinlik == 0:
                return i + 1
        if not ch.isspace():
            onceki = ch
        i += 1
    raise ValueError('kapanmayan blok')


def _js_kurallar(kaynak: str, ad: str):
    """``var <ad> = [ ... ]`` dizisindeki kurallar.

    Dönüş: ``(dize_kurallari, islev_kural_sayisi)``; dize kuralı
    ``(derlenmiş regex, şablon, çevrilecek grup listesi, küresel mi)``.
    İşlev gövdeli kurallar (ekranın kendi JS işlevi) Python'da koşulamaz;
    SAYILIR ve rapora yazılır.
    """
    m = re.search(r'var %s = \[' % re.escape(ad), kaynak)
    if not m:
        return [], 0
    i = m.end()
    son = _blok_sonu(kaynak, m.end() - 1, '[', ']') - 1
    kurallar, islevli = [], 0
    while True:
        i = _bosluk_atla(kaynak, i)
        if i >= son or kaynak[i] != '[':
            break
        giris_sonu = _blok_sonu(kaynak, i, '[', ']')
        j = _bosluk_atla(kaynak, i + 1)
        try:
            if kaynak[j] != '/':
                raise ValueError('regex yok')
            rkaynak, bayrak, j = _js_regex_oku(kaynak, j)
            j = _bosluk_atla(kaynak, j)
            if kaynak[j] != ',':
                raise ValueError(',')
            j = _bosluk_atla(kaynak, j + 1)
            if kaynak[j] not in '\'"':
                islevli += 1
                i = _bosluk_atla(kaynak, giris_sonu)
                if i < len(kaynak) and kaynak[i] == ',':
                    i += 1
                continue
            sablon, j = _js_dize_oku(kaynak, j)
            j = _bosluk_atla(kaynak, j)
            while kaynak[j] == '+':
                j = _bosluk_atla(kaynak, j + 1)
                ek, j = _js_dize_oku(kaynak, j)
                sablon += ek
                j = _bosluk_atla(kaynak, j)
            gruplar = []
            if kaynak[j] == ',':
                j = _bosluk_atla(kaynak, j + 1)
                if kaynak[j] == '[':
                    gs = _blok_sonu(kaynak, j, '[', ']')
                    gruplar = [int(x) for x in
                               re.findall(r'\d+', kaynak[j:gs])]
            pdesen = rkaynak.replace('(?<', '(?P<').replace('(?P<=', '(?<=') \
                .replace('(?P<!', '(?<!')
            derli = re.compile(pdesen, re.I if 'i' in bayrak else 0)
            kurallar.append((derli, sablon, gruplar, 'g' in bayrak))
        except (ValueError, IndexError, re.error):
            islevli += 1
        i = _bosluk_atla(kaynak, giris_sonu)
        if i < len(kaynak) and kaynak[i] == ',':
            i += 1
    return kurallar, islevli


def _js_nesne(kaynak: str, ad: str) -> Dict[str, str]:
    """``var <ad> = { 'a': 'b', ... }`` düz eşleme nesnesi."""
    m = re.search(r'var %s = \{' % re.escape(ad), kaynak)
    if not m:
        return {}
    son = _blok_sonu(kaynak, m.end() - 1, '{', '}')
    govde = kaynak[m.end():son - 1]
    return {_kacis_coz(a): _kacis_coz(b) for a, b in re.findall(
        r"'((?:[^'\\]|\\.)*)'\s*:\s*'((?:[^'\\]|\\.)*)'", govde)}


@lru_cache(maxsize=None)
def ekran_desenleri():
    """``i18n_charts.js``in desen tabloları (dosyadan okunur, kopyalanmaz)."""
    yol = os.path.join(_JS_DIZINI, 'i18n_charts.js')
    try:
        with open(yol, encoding='utf-8') as fh:
            kaynak = fh.read()
    except OSError:
        return {'MSG_PATTERNS': [], 'PATTERNS': [], 'KUYRUK_DESENLERI': [],
                'UNIT_WORDS': [], 'HAT_ONEKLERI': {}, 'islevli': {}}
    sonuc = {'islevli': {}}
    for ad in ('MSG_PATTERNS', 'PATTERNS', 'KUYRUK_DESENLERI', 'UNIT_WORDS'):
        kurallar, islevli = _js_kurallar(kaynak, ad)
        sonuc[ad] = kurallar
        sonuc['islevli'][ad] = islevli
    sonuc['HAT_ONEKLERI'] = _js_nesne(kaynak, 'HAT_ONEKLERI')
    return sonuc


def _yerlestir(sablon: str, parcalar, dil: str) -> str:
    def _bir(m):
        n = int(m.group(1))
        p = parcalar[n - 1] if 0 < n <= len(parcalar) else None
        return '' if p is None else yakalanan_metni(str(p), dil)
    return re.sub(r'\$(\d)', _bir, sablon)


def _desen_uygula(metin: str, kurallar, dil: str) -> Optional[str]:
    """Ekranın ``applyPatterns``ı (dize şablonlu kurallar)."""
    for derli, sablon, gruplar, _kuresel in kurallar:
        m = derli.search(metin)
        if not m:
            continue
        parcalar = list(m.groups())
        if not gruplar:
            return derli.sub(lambda mm: _yerlestir(
                sablon, list(mm.groups()), dil), metin, count=1)
        for g in gruplar:
            if 0 < g <= len(parcalar) and parcalar[g - 1] is not None:
                karsilik = ters_sozluk(dil).get(normalize(parcalar[g - 1]))
                if karsilik is not None:
                    parcalar[g - 1] = karsilik
        return _yerlestir(sablon, parcalar, dil)
    return None


def _kuyruga_ayir(metin: str, dil: str):
    """Ekranın ``kuyrugaAyir``ı: sonradan eklenen sonuç cümlelerini ayırır."""
    govde, kuyruk = metin, ''
    kurallar = ekran_desenleri()['KUYRUK_DESENLERI']
    for _tur in range(len(kurallar)):
        soyuldu = False
        for derli, sablon, _g, _k in kurallar:
            m = derli.search(govde)
            if not m:
                continue
            kuyruk = derli.sub(lambda mm: _yerlestir(
                sablon, list(mm.groups()), dil), govde[m.start():],
                count=1) + kuyruk
            govde = govde[:m.start()]
            soyuldu = True
            break
        if not soyuldu:
            break
    return govde, kuyruk


# --- çeviri merdiveni ---------------------------------------------------
_BAS_NOKTALAMA = re.compile(r'^(?:[—–:;,]\s+|• |- |· )')
#: Birim simgesi: harf dizileri en çok 4 harf, toplam en çok 12 karakter
#: ('K', 'bar', 'm/s', 'kg/kmol', 'N⋅s', 'MPa', 'kg/m3', 'N/A').
_BIRIM = re.compile(r'^[A-Za-zµμΩ°%·⋅/²³0-9^()\-.]{1,12}$')


def _birim_mi(metin: str) -> bool:
    if not _BIRIM.match(metin):
        return False
    return all(len(s) <= 4 for s in re.findall(r'[A-Za-zµμΩ]+', metin))


def _tr_buyuk(metin: str) -> str:
    return metin.replace('i', 'İ').replace('ı', 'I').upper()


def _tr_kucuk(metin: str) -> str:
    return metin.replace('I', 'ı').replace('İ', 'i').lower()


def _harf_uydur(en_metin: str, karsilik: str) -> str:
    """Büyük/küçük harf duyarsız eşleşmede karşılığın harf biçimi
    İngilizce metne uydurulur (başlık 'Performance' → 'Performans', rozet
    'PERFORMANS' değil). Türkçe İ/ı kuralıyla."""
    if not karsilik:
        return karsilik
    if en_metin.isupper():
        return _tr_buyuk(karsilik)
    if en_metin == en_metin.lower() and re.search('[a-z]', en_metin):
        return _tr_kucuk(karsilik)          # 'burn time' → 'yanma süresi'
    if karsilik.isupper() and len(karsilik) > 1:
        kucuk = _tr_kucuk(karsilik)
        return (_tr_buyuk(kucuk[0]) + kucuk[1:]) if en_metin[0].isupper() \
            else kucuk
    if en_metin[0].isupper() and karsilik[0].islower():
        return _tr_buyuk(karsilik[0]) + karsilik[1:]
    if en_metin[0].islower() and karsilik[0].isupper() \
            and not karsilik[:2].isupper():
        return _tr_kucuk(karsilik[0]) + karsilik[1:]
    return karsilik


@lru_cache(maxsize=None)
def ters_sozluk_kucuk(dil: str) -> Dict[str, str]:
    """Büyük/küçük harf duyarsız ters sözlük (birebir arama tutmazsa)."""
    sonuc: Dict[str, str] = {}
    for en_metin, karsilik in ters_sozluk(dil).items():
        sonuc.setdefault(en_metin.casefold(), karsilik)
    return sonuc


_BIRIM_SOZCUGU = re.compile(r'[A-Za-zµμΩ]+')
#: Etiket tarafının üst boyu (ekranın 'Etiket: değer' kuralı 60; rapor
#: etiketleri daha uzun olabiliyor).
_ETIKET_AZAMI = 90
_CUMLE_SINIRI = re.compile(r'(?<=[.;])\s+(?=[A-Z(\'"“])')


def _ara(metin: str, dil: str) -> Optional[str]:
    """Birebir, yoksa büyük/küçük harf duyarsız sözlük karşılığı."""
    hit = ters_sozluk(dil).get(metin)
    if hit is not None:
        # Ekran rozeti BÜYÜK harfle yazılmış olabilir ('not evaluated' →
        # 'DEĞERLENDİRİLMEDİ'); belge cümlesinde İngilizcenin harf biçimi
        # izlenir (dar tablo sütununda sözcük ortasından kırılma da önlenir).
        if hit.isupper() and len(hit) > 3 and not metin.isupper():
            return _harf_uydur(metin, hit)
        return hit
    hit = ters_sozluk_kucuk(dil).get(metin.casefold())
    return None if hit is None else _harf_uydur(metin, hit)


#: Makine adının (alan / sınıf / değer) okunur İngilizcesini taşıyan rapor
#: sözlüğü önekleri (sırayla).
OKUNUR_AD_ONEKLERI = ('report.value.', 'report.safety.value.',
                      'report.field.', 'report.safety.field.')


def okunur_ad(ad: str) -> Optional[str]:
    """Makine adının rapor sözlüğündeki okunur İngilizcesi; yoksa None."""
    en = sozluk('en')
    for onek in OKUNUR_AD_ONEKLERI:
        if onek + ad in en:
            return en[onek + ad]
    return None


def _nesir_mi(metin: str) -> bool:
    """Çevrilmemiş parça bir CÜMLE mi (en az üç sözcük)? Ad, sayı, künye
    ve kısa değerler çeviri kaydına girmez."""
    return len(re.findall(r'(?:^|\s)[A-Za-z][A-Za-z\'’-]+', metin or '')) >= 3


def _parantez_disi_bol(metin: str, ayrac: str):
    """``ayrac`` ile böler; parantez içindeki ayracı bölmez."""
    parcalar, derin, bas, i = [], 0, 0, 0
    while i < len(metin):
        ch = metin[i]
        if ch in '([':
            derin += 1
        elif ch in ')]':
            derin = max(0, derin - 1)
        elif derin == 0 and metin.startswith(ayrac, i):
            parcalar.append(metin[bas:i])
            i += len(ayrac)
            bas = i
            continue
        i += 1
    parcalar.append(metin[bas:])
    return parcalar


def _degersel(metin: str) -> bool:
    """Sayı/birim parçası mı? (rakam var, hiçbir harf dizisi 5'ten uzun değil)"""
    if not re.search(r'\d', metin):
        return False
    return all(len(s) <= 5 for s in _BIRIM_SOZCUGU.findall(metin))


def _sablon_cevir(metin: str, dil: str, derinlik: int) -> Optional[str]:
    hit = _sablon_cevir_tam(metin, dil, derinlik)
    if hit is None and len(metin) > 1 and metin[-1] in ':.' \
            and not _CUMLE_SINIRI.search(metin):
        ic = _sablon_cevir_tam(metin[:-1].rstrip(), dil, derinlik)
        if ic is not None:
            return ic + metin[-1]
    return hit


def _sablon_cevir_tam(metin: str, dil: str, derinlik: int) -> Optional[str]:
    for en_uzun, derli, adlar, karsilik in _sablonlar(dil):
        if en_uzun and en_uzun not in metin:
            continue
        m = derli.match(metin)
        if not m:
            continue
        degerler = {}
        for ad, deger in zip(adlar, m.groups()):
            ic = _cekirdek(deger.strip(), dil, derinlik + 1, kayit=False)
            if ic is None and _nesir_mi(deger):
                _kaydet(deger.strip())       # yakalanan çözücü cümlesi
            if ic is not None and deger.strip():
                # Yakalamanın çevresindeki boşluk korunur (' (4)' → ' (4)').
                ic = deger[:len(deger) - len(deger.lstrip())] + ic \
                    + deger[len(deger.rstrip()):]
            degerler.setdefault(ad, deger if ic is None else ic)
        return _YER.sub(lambda mm: degerler.get(mm.group(1), mm.group(0)),
                        karsilik)
    return None


def _turkce_icerikli(metin: str, dil: str, derinlik: int,
                     kayit: bool) -> str:
    """Türkçe harf taşıyan metin: Türkçe parçalar aynen, İngilizce parçalar
    (etiket, '; ' listesi öğesi, cümle) çevrilir. Hiçbir zaman None
    dönmez (Türkçe metin 'çevrilemedi' sayılmaz)."""
    if derinlik > 8:
        return metin

    def _ic(parca):
        if not parca.strip():
            return parca
        c = _cekirdek(parca.strip(), dil, derinlik + 1, kayit)
        if c is None:
            if kayit and _nesir_mi(parca):
                _kaydet(parca.strip())
            return parca
        return parca[:len(parca) - len(parca.lstrip())] + c \
            + parca[len(parca.rstrip()):]

    hit = _sablon_cevir(metin, dil, derinlik)   # Türkçe yakalamalı şablon
    if hit is not None:
        return hit
    for ayrac in (': ', ' — '):
        if ayrac in metin:
            sol, sag = metin.split(ayrac, 1)
            if sol and len(sol) <= _ETIKET_AZAMI and not _TR_HARFI.search(sol) \
                    and '. ' not in sol:
                etiket = _ara(sol, dil)
                if etiket is not None:
                    return etiket + ayrac + _ic(sag)
    ogeler = _parantez_disi_bol(metin, '; ')
    if len(ogeler) > 1:
        return '; '.join(_ic(o) for o in ogeler)
    cumleler = _CUMLE_SINIRI.split(metin)
    if len(cumleler) > 1:
        return ' '.join(_ic(c) for c in cumleler)
    return metin


def _cekirdek(metin: str, dil: str, derinlik: int = 0,
              kayit: bool = True) -> Optional[str]:
    """Normalize metnin karşılığı; çevrilemezse None."""
    if not metin:
        return metin
    if not _HARF.search(metin):
        return olcu_metni(metin, dil)
    if _TR_HARFI.search(metin):
        # Türkçe parça içeren metin (kurulurken çevrilmiş uyarı cümlesi gibi):
        # Türkçe kısım AYNEN kalır, yanındaki İngilizce parçalar yapı
        # kurallarıyla çevrilir.
        return _turkce_icerikli(metin, dil, derinlik, kayit)
    ters = ters_sozluk(dil)
    hit = _ara(metin, dil)
    if hit is not None:
        return hit
    if _birim_mi(metin):
        return metin                         # birim simgesi (iki dilde aynı)
    # Makine değeri: BÜYÜK_HARF hüküm sabiti ('NOT_EVALUATED') ve küçük harf
    # sınıf/alan adı ('unlike_impinging') — sözlüğün okunur adıyla.
    if re.fullmatch(r'[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+', metin):
        return _ara(metin.replace('_', ' '), dil)
    if re.fullmatch(r'[a-z][a-z0-9]*(?:_[a-z0-9]+)+', metin):
        okunur = okunur_ad(metin)
        return _ara(okunur, dil) if okunur else None
    if re.fullmatch(r'[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+', metin):
        return metin                         # yanıt yolu künyesi (makine adı)
    # Baştaki noktalama / madde imi ayrılıp çekirdek yeniden çevrilir
    # (ör. '</b> — açıklama.' parçası).
    bas = _BAS_NOKTALAMA.match(metin)
    if bas and bas.end() < len(metin):
        ic = _cekirdek(metin[bas.end():], dil, derinlik, kayit)
        return None if ic is None else metin[:bas.end()] + ic
    # Sondaki noktalama: önce birebir ('Etiket:' hücresi).
    if metin[-1] in ':.;,' and len(metin) > 1:
        ic = _ara(metin[:-1].rstrip(), dil)
        if ic is not None:
            return ic + metin[-1]
    if derinlik > 8:
        return None
    hit = _sablon_cevir(metin, dil, derinlik)
    if hit is not None:
        return hit
    desen = ekran_desenleri()
    for tablo in ('MSG_PATTERNS', 'PATTERNS'):
        hit = _desen_uygula(metin, desen[tablo], dil)
        if hit is not None and hit != metin:
            liste = _DESEN_KAYDI.get()
            if liste is not None:
                liste.append(hit)
            return hit
    onek = re.match(r'^\[([^\]]+)\]\s+(.+)$', metin, re.S)
    if onek and onek.group(1) in desen['HAT_ONEKLERI']:
        ic = _cekirdek(onek.group(2), dil, derinlik + 1, kayit)
        if ic is not None:
            return '[%s] %s' % (desen['HAT_ONEKLERI'][onek.group(1)], ic)
    govde, kuyruk = _kuyruga_ayir(metin, dil)
    if kuyruk:
        ic = _cekirdek(govde.strip(), dil, derinlik + 1, kayit=False)
        if ic is not None:
            return ic + kuyruk
    # "Etiket: değer" / "Etiket — değer"
    for ayrac in (': ', ' — ', ' - '):
        if ayrac not in metin:
            continue
        sol, sag = metin.split(ayrac, 1)
        if not sol or len(sol) > _ETIKET_AZAMI or '. ' in sol:
            continue
        etiket = _ara(sol, dil) or _sablon_cevir(sol, dil, derinlik)
        if etiket is None:
            continue
        deger = _cekirdek(sag.strip(), dil, derinlik + 1, kayit)
        if deger is None and kayit and _nesir_mi(sag):
            _kaydet(sag.strip())
        return etiket + ayrac + (sag if deger is None else deger)
    # Satır içi madde imleri ('... include: • A: x • B: y'): her madde ayrı.
    if ' • ' in metin:
        parcalar = metin.split(' • ')
        cikti, kalan = [], []
        for n, p in enumerate(parcalar):
            ic = _cekirdek(p.strip(), dil, derinlik + 1, kayit=False)
            if ic is None:
                kalan.append(p)
            cikti.append(p if ic is None else ic)
        if len(kalan) < len(parcalar):
            if kayit:
                for p in kalan:
                    _kaydet(p)
            return ' • '.join(cikti)
    # Etiket zinciri ('Emergency response › Explosion response › …').
    if ' › ' in metin:
        halkalar = [_ara(h.strip(), dil) for h in metin.split(' › ')]
        if all(h is not None for h in halkalar):
            return ' › '.join(halkalar)
    # 'A and B' / 'A, B and C': bütün öğeler çevrilirse ', ' ve ' ve '.
    if ' and ' in metin and '. ' not in metin:
        bas_kisim, son_oge = metin.rsplit(' and ', 1)
        ogeler = _parantez_disi_bol(bas_kisim, ', ') + [son_oge]
        if len(ogeler) <= 6:
            cevrilen = [_ara(o.strip(), dil) for o in ogeler]
            if all(c is not None for c in cevrilen):
                return ', '.join(cevrilen[:-1]) + ' ve ' + cevrilen[-1]
    # Liste ('burn time, chamber diameter, ...' ya da '; ' ile): öğeler
    # bağımsız çevrilir; en az yarısı çevrilirse birleştirilir.
    for ayrac in ('; ', ', '):
        if ayrac not in metin or (ayrac == ', ' and '. ' in metin):
            continue
        ogeler = _parantez_disi_bol(metin, ayrac)
        if len(ogeler) > 1 and all(0 < len(o) <= 160 for o in ogeler):
            cikti, kalan = [], []
            for o in ogeler:
                ic = _cekirdek(o.strip(), dil, derinlik + 1, kayit=False)
                if ic is None:
                    kalan.append(o)
                cikti.append(o if ic is None else ic)
            if (not kalan) if ayrac == ', ' else (2 * len(kalan) <= len(ogeler)):
                if kayit:
                    for o in kalan:
                        _kaydet(o)
                return ayrac.join(cikti)
    # "Taban (ek)"
    par = re.match(r'^(.+?)\s*\(([^()]*)\)$', metin)
    if par:
        taban = _ara(par.group(1), dil)
        if taban is not None:
            ek = _cekirdek(par.group(2), dil, derinlik + 1, kayit)
            if ek is None and kayit and _nesir_mi(par.group(2)):
                _kaydet(par.group(2))
            return '%s (%s)' % (taban, par.group(2) if ek is None else ek)
    # "Taban 12" (sondaki sayı korunur).
    sayili = re.match(r'^(.+?)\s+([-+]?\d[\d.,]*\s*\S{0,6})$', metin)
    if sayili:
        bas_ad = _ara(sayili.group(1), dil)
        if bas_ad is not None:
            return bas_ad + ' ' + olcu_metni(sayili.group(2), dil)
    if _degersel(metin):
        return olcu_metni(metin, dil)
    # Sondaki noktalama ayrılmış hâliyle tam merdiven (tek cümlelik metin).
    if metin[-1] in ':.;,' and len(metin) > 1 and derinlik <= 8 \
            and not _CUMLE_SINIRI.search(metin):
        ic = _cekirdek(metin[:-1].rstrip(), dil, derinlik + 1, kayit=False)
        if ic is not None:
            return ic + metin[-1]
    # Cümle cümle (en az biri çevrilirse birleştirilir; çevrilemeyen cümle
    # AYNEN kalır ve kendi adıyla kayda girer).
    cumleler = _CUMLE_SINIRI.split(metin)
    if len(cumleler) > 1:
        cikti, kalan = [], []
        i = 0
        while i < len(cumleler):
            # Önce birden çok cümleyi kapsayan sözlük metni/şablonu aranır
            # (en uzun pencere önce; şablonun kendi içinde cümle sınırı olabilir).
            bulundu = False
            for j in range(min(len(cumleler), i + 4), i + 1, -1):
                pencere = ' '.join(cumleler[i:j])
                ic = _ara(pencere, dil) or _sablon_cevir(pencere, dil, derinlik)
                if ic is not None:
                    cikti.append(ic)
                    i = j
                    bulundu = True
                    break
            if bulundu:
                continue
            c = cumleler[i]
            ic = _cekirdek(c, dil, derinlik + 1, kayit=False)
            if ic is None:
                kalan.append(c)
                cikti.append(c)
            else:
                cikti.append(ic)
            i += 1
        if len(kalan) < len(cumleler):
            if kayit:
                for c in kalan:
                    _kaydet(c)
            return ' '.join(cikti)
    return None


def cevir(metin: Any, dil: Optional[str] = None) -> Any:
    """Bir DÜZ metin parçasını etkin dile çevirir (biçim işareti yok).

    Dil 'en' ise ya da metin dize değilse AYNEN döner. Çevrilemeyen parça
    AYNEN döner ve :func:`cevrilmeyen_kaydi` listesine girer.
    """
    dil = dil or etkin_dil()
    if dil == 'en' or not isinstance(metin, str) or not metin.strip():
        return metin
    bas = metin[:len(metin) - len(metin.lstrip())]
    son = metin[len(metin.rstrip()):]
    norm = normalize(metin)
    sonuc = _cekirdek(norm, dil)
    if sonuc is None:
        _kaydet(norm)
        return metin
    return bas + sonuc + son


_ISARET = re.compile(r'(<[^<>]*>)')


def cevir_isaretli(metin: Any, dil: Optional[str] = None) -> Any:
    """ReportLab paragraf işaretli metni: etiketler KORUNUR, aradaki her
    metin parçası :func:`cevir` ile çevrilir (varlıklar çözülüp yeniden
    kaçırılır; değişmeyen parça bayt bayt aynen kalır)."""
    dil = dil or etkin_dil()
    if dil == 'en' or not isinstance(metin, str):
        return metin
    cikti = []
    for parca in _ISARET.split(metin):
        if not parca or (parca.startswith('<') and parca.endswith('>')) \
                or not parca.strip():
            cikti.append(parca)
            continue
        duz = _html.unescape(parca)
        cev = cevir(duz, dil)
        cikti.append(parca if cev == duz else _xml_kacis(cev))
    return ''.join(cikti)


def parca(anahtar: str, **params) -> str:
    """Birleştirilen cümlenin anahtarlı PARÇASI, etkin dilde doldurulmuş.

    Anahtar sözlükte yoksa ``KeyError`` (parça metni uydurulmaz; bekçi
    bütün ``report.part.*`` anahtarlarının iki dilde olduğunu denetler).
    """
    sonuc = metin(anahtar, etkin_dil(), params)
    if sonuc is None:
        raise KeyError(anahtar)
    return sonuc

