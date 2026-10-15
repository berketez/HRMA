"""Arayüz "yedek metni" dilinin TEK KAYNAĞI (ÖH D22 · P13B2-06).

Depoda birden çok bekçi aynı **tasarım kararını** ayrı ayrı kilitliyordu:

* ``T('anahtar', 'Fallback text')`` çağrılarında yedek metin ZORUNLUDUR
  (sözlük anahtarı henüz eklenmemişken ekrana ham anahtar basılmasın), ve
* o yedek metin **İngilizce**dir (Türkçe sürüm sözlükten gelir).

İkinci kural bir olgu değil bir KARAR'dır: ürün bir gün "yedek dili
kullanıcının seçtiği dil olsun" ya da "yedekler de yerelleşsin" derse,
karar değişmeden önce bu dosyadaki tanımın taşınması gerekir — kararın
kendisi tek yerde durduğu için taşımanın maliyeti bir satırdır. Kural
dosyalara dağılmışken (ÖH D22 öncesi) aynı taşıma, farklı düzenli
ifadelerle yazılmış bekçilerin tek tek avlanmasını gerektiriyordu.

ÖLÇÜLDÜ (ÖH D22, ``once.json``/``P13B2-06``): Türkçe-harf yasağı yalnız
``bug_report.js``in 21 yedeğini tarıyordu; ``settings_panel.js``in 10 ve
``blowdown_panel.js``in 18 yedeği yasağın DIŞINDAYDI — yani aynı karar
kimi dosyada kilitli, kimi dosyada serbestti. Asimetri kararın kendisinden
değil, kuralın kopyalanmasından geliyordu.
"""
from __future__ import annotations

import re
from typing import Iterable, List, Tuple

#: Yedek metinlerin dili. Değeri değiştirmek bir TASARIM KARARIDIR;
#: değiştirildiğinde bu dosyadaki denetçiler de birlikte gözden geçirilir.
YEDEK_DILI = 'en'

#: Türkçeye özgü harfler (ASCII karşılıkları kasten dışarıda: ``bogaz``
#: gibi ASCII'ye kaçmış Türkçe bu denetçinin konusu değil, i18n terim
#: bekçisinin konusudur).
TURKCE_HARF_DESENI = re.compile(r'[çğıöşüÇĞİÖŞÜ]')

#: ``T('anahtar', 'yedek')`` / ``TF('anahtar', 'yedek', ...)`` çağrılarından
#: yedek metni çeken desen. Yedeği OLMAYAN çağrı bu desene takılmaz; onu
#: ``yedeksiz_cagrilar`` bulur.
_YEDEKLI = re.compile(r"\bTF?\(\s*'([^']+)'\s*,\s*'([^']*)'")
#: ÖH D22 fix-19 (birleşme etkileşimi): electron kulvarı (P12aB5-12) settings_panel.js'te
#: durum metinlerini ``setStatus(node, 'anahtar', params, 'yedek')`` yardımcısına taşıdı;
#: yedek metin hâlâ DÜZ DİZE olarak kaynakta durur ve aynı dil kararına tabidir. Bu biçim
#: sayılmazsa yasak kapsamı sessizce daralır (bekci-cevirisi a1 tabanı 10 → 4 görünürdü).
#: params ``null`` ya da çok satırlı ``{...}`` olabilir; yedek dizesinin yalnız ilk
#: parçası (``'…' + '…'`` birleştirmesinde) yakalanır — dil denetimi için yeterlidir.
_YEDEKLI_SETSTATUS = re.compile(
    r"\bsetStatus\(\s*[A-Za-z_$][\w$]*\s*,\s*'([^']+)'\s*,\s*(?:null|\{.*?\})\s*,\s*'([^']*)'", re.S)
_YEDEKSIZ = re.compile(r"\bT\(\s*'[^']+'\s*\)")


def yedekler(kaynak: str, anahtar_oneki: str = '') -> List[Tuple[str, str]]:
    """Kaynaktaki ``(anahtar, yedek metin)`` çiftleri."""
    ciftler = _YEDEKLI.findall(kaynak) + _YEDEKLI_SETSTATUS.findall(kaynak)
    return [(a, y) for a, y in ciftler if a.startswith(anahtar_oneki)]


def yedeksiz_cagrilar(kaynak: str) -> List[str]:
    """Yedeği olmayan ``T('anahtar')`` çağrıları (ekrana ham anahtar riski)."""
    return _YEDEKSIZ.findall(kaynak)


def dil_kacaklari(ciftler: Iterable[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """Karara aykırı yedekler: ``YEDEK_DILI == 'en'`` iken Türkçe harf taşıyanlar.

    Karar değişirse (``YEDEK_DILI``) burası tek noktadan güncellenir.
    """
    if YEDEK_DILI != 'en':                       # pragma: no cover - karar dalı
        return []
    return [(a, y) for a, y in ciftler if TURKCE_HARF_DESENI.search(y)]
