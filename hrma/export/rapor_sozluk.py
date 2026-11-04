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
