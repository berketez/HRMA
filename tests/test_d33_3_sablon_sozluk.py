"""ÖH D33-3 · OH-D33-21 — ŞABLON METNİ İLE SÖZLÜK METNİ AYRIŞAMAZ.

ÖLÇÜLDÜ (Opus uç denetimi v2, arayuz-04 paketi, 16 Eylül 2026; RET
P12bB4-02): ``formulas.html`` §8.2 açıklaması D28'de onarılmış ve
"sıcaklığa göre düşürülmüş AKMA dayanımı" demeye başlamıştı, ama
``i18n_formulas.js`` sözlüğü ESKİ metni ("material ultimate strength" /
"nihai dayanımı") taşımayı sürdürdü. ``i18n.js`` DOMContentLoaded'da
``I18N.apply()`` çağırıyor ve ``I18N.t`` anahtar sözlükte VARSA sözlüğü
döndürüyor; satır-içi şablon metni yalnız anahtar YOKSA yedektir.

Sonuç: kullanıcı ekranda ESKİ ve YANLIŞ cümleyi okuyordu; şablonu ölçen
bekçi onarımı "yapılmış" sanıyordu. Bu bir BEKÇİ SINIFI kusurudur —
şablon dosyasını ölçen her bekçi, ekrana çizilen metne kördür.

Bu bekçi sınıfı kapatır: ``data-i18n`` taşıyan bir düğümün şablon metni ile
EN sözlük girdisi AYNI olmalı; anahtar sözlükte eksikse (TR kullanıcı
İngilizce okur) kırmızı verir.
"""
import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
SABLON = KOK / 'hrma' / 'templates' / 'formulas.html'
SOZLUK = KOK / 'hrma' / 'static' / 'js' / 'i18n_formulas.js'

#: Bu dosyanın kapsamı: §8.2'nin RET ile yeniden açılan iki düğümü.
#: Kapsam bilerek dardır ve BEYAN EDİLİR: formulas.html'de yüzlerce
#: ``data-i18n`` düğümü var, tümünü bir kerede kilitlemek bu dalganın işi
#: değil (OH-D33-22: kapsamı sayfanın tamamına taşıyan ayrı kalem).
KAPSAM = ('fx.s8_2.desc', 'fx.s8_2.model_note',
          # ÖH D35 / OH-GT-20 (22 Eylül 2026): kalan dört model notu.
          # ÖLÇÜLDÜ (raw/OH/D35/dil-safligi/a1/once.json, GT20): bu dört
          # anahtarın EN ve TR sözlük kaydı HİÇ YOKTU, yani TR arayüzde
          # "ürünün gerçekte ne koştuğunu" anlatan kutular İngilizceydi.
          'fx.s5_3.model_note', 'fx.s6_1.model_note',
          'fx.s7_1.model_note', 'fx.s13_2.model_note')


def _sablon_metni(anahtar):
    # ÖH D36 · OH-K-05: HTML taşıyan notlar `data-i18n-html` özniteliği de
    # taşır; öznitelik payı bırakılır (metin karşılaştırması değişmez).
    m = re.search(r'data-i18n="%s"(?:\s+[^>]*)?>(.*?)</span>' % re.escape(anahtar),
                  SABLON.read_text(encoding='utf-8'), re.S)
    assert m, 'sablonda %s dugumu yok' % anahtar
    return ' '.join(m.group(1).split())


#: JS tek-tırnaklı dize kaçışları. ÖH D35 / OH-GT-20 (22 Eylül 2026):
#: bu bekçi eskiden YALNIZ ``\\'`` kaçışını çözüyordu, yani kaynakta ters bölü
#: geçen her girdide ÇALIŞTIRMA ZAMANI metniyle kaynak metnini karıştırıyordu.
#: Ölçüldü: ``fx.s5_3.model_note`` LaTeX taşır (``$Nu = 0.023\\,Re^{0.8}...$``);
#: JS kaynağında bu ``\\\\,`` yazılmak ZORUNDADIR (tek ters bölü ECMA-262'de
#: tanınmayan kaçıştır ve sessizce DÜŞER), ama bekçi kaynağı ham okuduğu için
#: şablondaki ``\\,`` ile kaynak ``\\\\,`` ayrışık görünüyordu. Karşılaştırma
#: ÇALIŞTIRMA ZAMANI metni üzerinden yapılmalı: kaçışlar çözülür.
_JS_KACIS = {'\\\\': '\\', "\\'": "'", '\\"': '"', '\\n': '\n',
             '\\t': '\t', '\\r': '\r', '\\b': '\b', '\\f': '\f',
             '\\/': '/'}


def _js_coz(ham):
    """JS tek-tırnaklı dize gövdesini çalıştırma zamanı metnine çevirir."""
    out = []
    i = 0
    while i < len(ham):
        if ham[i] == '\\' and i + 1 < len(ham):
            ikili = ham[i:i + 2]
            if ikili in _JS_KACIS:
                out.append(_JS_KACIS[ikili])
            else:
                # ECMA-262: tanınmayan kaçışta ters bölü düşer ('\\,' -> ',')
                out.append(ham[i + 1])
            i += 2
            continue
        out.append(ham[i])
        i += 1
    return ''.join(out)


def _sozluk_metinleri(anahtar):
    return [' '.join(_js_coz(m.group(1)).split())
            for m in re.finditer(
                r"'%s':\s*'((?:[^'\\]|\\.)*)'" % re.escape(anahtar),
                SOZLUK.read_text(encoding='utf-8'))]


@pytest.mark.parametrize('anahtar', KAPSAM)
def test_anahtar_iki_sozlukte_de_var(anahtar):
    kayitlar = _sozluk_metinleri(anahtar)
    assert len(kayitlar) == 2, (
        '%s sozlukte %d kez gecti (EN + TR beklenir): anahtar eksikse TR '
        'kullanici Ingilizce okur' % (anahtar, len(kayitlar)))


@pytest.mark.parametrize('anahtar', KAPSAM)
def test_sablon_metni_EN_sozlukle_ayni(anahtar):
    sablon = _sablon_metni(anahtar)
    en = _sozluk_metinleri(anahtar)[0]
    assert en == sablon, (
        '%s: sablon metni ile EN sozluk girdisi AYRISIK. Ekrana SOZLUK '
        'cizilir (I18N.apply), yani sablonu duzeltmek tek basina kullaniciya '
        'ULASMAZ.\nsablon: %s...\nsozluk: %s...' % (anahtar, sablon[:120],
                                                    en[:120]))


def test_derate_edilmis_AKMA_dayanimi_ekranda():
    """RET'in özü: ekrana çizilen metin 'nihai dayanım' DEMEMELİ."""
    en, tr = _sozluk_metinleri('fx.s8_2.desc')
    assert 'ultimate strength and actual working' not in en, (
        'EN sozlukte eski "ultimate strength" cumlesi duruyor (P12bB4-02)')
    assert 'nihai dayanımı ile gerçek' not in tr, (
        'TR sozlukte eski "nihai dayanımı" cumlesi duruyor (P12bB4-02)')
    assert 'derated yield strength' in en or 'temperature-derated yield' in en
    assert 'akma' in tr.lower()
