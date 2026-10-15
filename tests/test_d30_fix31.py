# -*- coding: utf-8 -*-
"""ÖH D30 · fix-31 — i18n sözlük borcunun bekçisi.

ÖLÇÜLEN TABAN (11a46906, ``pytest tests/test_i18n_common.py``): iki kırmızı.

* ``test_every_used_key_exists_in_dictionary`` — 14 anahtar KODDA çağrılıyor
  ama sözlükte yok: 11'i ``panel.uncertainty.*`` (D30 arayuz-panel a2'nin
  açtığı örnekleyici/UQ sürümü kartları ve dağılım künyesi tablosu), biri
  ``panel.comparative.bestEfficiencyScopeTip``, biri
  ``panel.vessel.cardMarginAutoTip``, biri de motor tarafından yayımlanan
  ``warn.solid.erosion_exponent_extrapolated`` (D30 katı a1).
  Sözlüksüz anahtar üründe ham anahtar ya da yalnız İngilizce yedek demektir:
  Türkçe kipte kullanıcı İngilizce cümle görür.
* ``test_every_dictionary_key_is_used`` — 31 anahtarın tüketicisi yok.
  D30 arayuz-panel a1 (896d2e83) ``app.js``teki ölü gölge gövdeleri söktü;
  o gövdelerin çağırdığı 29 ``app.msg.*`` ile ``common.success`` /
  ``common.warning`` sözlükte ÖKSÜZ kaldı.

Bu dosya onarımı KİLİTLER. Üç ayaklıdır ve üçü de ayrı bir yalanı yakalar:
anahtarın eksikliği, çevirinin yapılmamışlığı (TR = EN), ölü anahtarın
geri sızması.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DICT_JS = ROOT / 'hrma' / 'static' / 'js' / 'i18n_common.js'

#: fix-31'in EKLEDİĞİ anahtarlar — hepsi kodda çağrılıyor (çağrı yerleri
#: ``test_i18n_common.test_every_used_key_exists_in_dictionary`` tarafından
#: türetilir; burada yalnız sözlük ayağı kilitlenir).
EKLENEN = (
    'panel.uncertainty.cardSampler',
    'panel.uncertainty.cardSamplerTip',
    'panel.uncertainty.cardUqVersion',
    'panel.uncertainty.cardUqVersionTip',
    'panel.uncertainty.distApplies',
    'panel.uncertainty.distLabel',
    'panel.uncertainty.distMode',
    'panel.uncertainty.distName',
    'panel.uncertainty.distSource',
    'panel.uncertainty.distTitle',
    'panel.uncertainty.distUnreported',
    'panel.comparative.bestEfficiencyScopeTip',
    'panel.vessel.cardMarginAutoTip',
    'warn.solid.erosion_exponent_extrapolated',
)

#: fix-31'in SİLDİĞİ ölü anahtarlar (tüketici sayısı ölçüldü: 0).
SILINEN = (
    'app.msg.analysisFirst', 'app.msg.cadError', 'app.msg.cadFailed',
    'app.msg.cadOk', 'app.msg.cadOkAlert', 'app.msg.calculateFirst',
    'app.msg.configureFirst', 'app.msg.engError', 'app.msg.engFailed',
    'app.msg.engOk', 'app.msg.generating3d', 'app.msg.packageDownloaded',
    'app.msg.packageError', 'app.msg.packageFailed',
    'app.msg.packageGenerating', 'app.msg.packageOk', 'app.msg.paramError',
    'app.msg.paramFormMissing', 'app.msg.paramInvalid', 'app.msg.paramNoPlot',
    'app.msg.paramOk', 'app.msg.paramRange', 'app.msg.paramStarted',
    'app.msg.paramSteps', 'app.msg.paramTruncated', 'app.msg.stlError',
    'app.msg.stlFailed', 'app.msg.stlFiles', 'app.msg.stlOk',
    'common.success', 'common.warning',
)

#: Türkçesi İngilizcesiyle MEŞRU biçimde aynı olabilecek anahtarlar.
#: fix-31'in eklediklerinde böyle bir kalem YOKTUR; küme boş bırakılmıştır
#: ki ileride bir istisna eklenirse gerekçesi buraya yazılsın.
TR_ESITLIGI_MESRU = frozenset()


def _blok(lang):
    """i18n_common.js içindeki bir dil bloğunun anahtar -> değer sözlüğü.

    Ayrıştırma ``test_i18n_common.dict_block`` ile aynı sözleşmededir
    (tek satırlık ``'anahtar': 'değer',`` girdileri): bu bekçinin ölçtüğü
    dosya biçimi orada da ölçülür, iki taraf ayrışamaz.
    """
    kaynak = DICT_JS.read_text(encoding='utf-8')
    bas = kaynak.index('        %s: {' % lang)
    derinlik = 0
    for i in range(bas + len('        %s: ' % lang), len(kaynak)):
        if kaynak[i] == '{':
            derinlik += 1
        elif kaynak[i] == '}':
            derinlik -= 1
            if derinlik == 0:
                govde = kaynak[bas:i]
                break
    else:                                   # pragma: no cover - bozuk dosya
        pytest.fail("i18n_common.js '%s' bloğu kapanmıyor" % lang)
    ciftler = re.findall(
        r"^\s*'((?:[^'\\]|\\.)*)':\s*'((?:[^'\\]|\\.)*)',?\s*$",
        govde, re.M)
    return {k.replace("\\'", "'"): v.replace("\\'", "'") for k, v in ciftler}


@pytest.fixture(scope='module')
def sozlukler():
    return _blok('en'), _blok('tr')


def test_eklenen_anahtarlar_iki_dilde_de_var(sozlukler):
    """14 anahtarın EN ve TR karşılığı olmalı, ikisi de boş olmamalı."""
    en, tr = sozlukler
    eksik_en = sorted(k for k in EKLENEN if not en.get(k, '').strip())
    eksik_tr = sorted(k for k in EKLENEN if not tr.get(k, '').strip())
    assert not eksik_en, 'EN karşılığı yok/boş: %s' % eksik_en
    assert not eksik_tr, 'TR karşılığı yok/boş: %s' % eksik_tr


def test_eklenen_anahtarlarin_turkcesi_ingilizcesinden_farkli(sozlukler):
    """Anahtarı eklemek çevirmek DEĞİLDİR.

    TR bloğuna İngilizce metni kopyalamak testi yeşile boyar ama kullanıcı
    yine İngilizce görür. Bu ayak o sessiz kaçışı kapatır.
    """
    en, tr = sozlukler
    ayni = sorted(k for k in EKLENEN
                  if k not in TR_ESITLIGI_MESRU
                  and en.get(k, '').strip() == tr.get(k, '').strip())
    assert not ayni, ('TR değeri EN ile birebir aynı (çeviri yapılmamış): %s'
                      % ayni)


def test_eklenen_turkce_degerler_turkce_harf_tasiyor(sozlukler):
    """Çevirinin gerçekten Türkçe olduğunun ikinci, bağımsız ölçüsü.

    Kısa etiketlerde (``input`` -> ``girdi``) harf ölçüsü tutmayabilir;
    o yüzden ölçüt "en az bir Türkçe harf VEYA EN'den farklı sözcük
    kümesi" değil, doğrudan Türkçe harf ARAYAN bir alt küme üstünde
    uygulanır: uzun cümleler. Kısa etiketleri bir üstteki eşitlik ayağı
    zaten korur.
    """
    en, tr = sozlukler
    turkce = re.compile(r'[çğıİöşüÇĞÖŞÜ]')
    uzunlar = [k for k in EKLENEN if len(en.get(k, '')) > 30]
    assert uzunlar, 'uzun metinli anahtar kalmadı — ölçüt boşa düştü'
    harfsiz = sorted(k for k in uzunlar if not turkce.search(tr.get(k, '')))
    assert not harfsiz, ('TR değeri hiç Türkçe harf taşımıyor (İngilizce '
                         'kopya olabilir): %s' % harfsiz)


def test_olu_anahtarlar_iki_blokta_da_yok(sozlukler):
    """31 ölü anahtar geri sızmamalı (ne EN ne TR)."""
    en, tr = sozlukler
    geri = sorted(k for k in SILINEN if k in en or k in tr)
    assert not geri, ('silinen ölü anahtar sözlüğe geri gelmiş: %s' % geri)


def test_olu_anahtarlarin_tuketicisi_hala_yok():
    """Silme ölçüme dayanıyordu: tüketici sayısı 0.

    Bir anahtarı silmek, onu kullanan bir yol varsa üründe ham metin
    demektir. Bu ayak ölçümü CANLI tutar: biri sökülen adları yeniden
    çağırırsa (silinmiş anahtarla) burada kırmızı verir.
    """
    js_kok = ROOT / 'hrma' / 'static' / 'js'
    sablon_kok = ROOT / 'hrma' / 'templates'
    govde = []
    for kok, desen in ((js_kok, '**/*.js'), (sablon_kok, '**/*.html')):
        for yol in sorted(kok.glob(desen)):
            if yol.name in ('i18n_common.js', 'i18n.js', 'i18n_pages.js',
                            'i18n_shell.js'):
                continue            # sözlük kaynakları taranmaz
            govde.append(yol.read_text(encoding='utf-8'))
    metin = '\n'.join(govde)
    # Yalnız ÇEVİRİ ÇAĞRISI sayılır: yorumdaki anılma tüketici değildir
    # (``app.js`` P11B2-24 notu iki adı gerekçe olarak anar).
    cagrilar = set(re.findall(
        r"(?:\bT|\bTF|U\.t|U\.tf|window\.I18N\.t|window\.I18N\.tf)\(\s*"
        r"['\"]([\w.]+)['\"]", metin))
    diri = sorted(k for k in SILINEN if k in cagrilar)
    assert not diri, ('silinen anahtarın çeviri çağrısı var — silme '
                      'ölçümü bayatladı: %s' % diri)


def test_warn_anahtari_motor_yedegiyle_birebir_ayni(sozlukler):
    """``warn.solid.erosion_exponent_extrapolated`` EN'i motorun yedeğidir.

    Motor kaydı İngilizce cümleyi ``fallback`` alanında taşır ve ekran
    katmanı sözlük yoksa onu basar. İki metin ayrışırsa kullanıcı aynı
    uyarıyı iki farklı İngilizce cümleyle görür — biri sözlükten, biri
    yedekten. Bu ayak ikisini tek kaynağa bağlar.
    """
    en, _ = sozlukler
    py = (ROOT / 'hrma' / 'engines' / 'solid_rocket_engine.py').read_text(
        encoding='utf-8')
    i = py.index("'warn.solid.erosion_exponent_extrapolated'")
    m = re.search(r'fallback=\(\s*((?:\s*"[^"]*"\s*)+)\)\)\)', py[i:i + 2000])
    assert m, 'motor kaydının fallback metni okunamadı'
    yedek = ''.join(re.findall(r'"([^"]*)"', m.group(1)))
    assert en['warn.solid.erosion_exponent_extrapolated'] == yedek, (
        'sözlük EN metni motor yedeğinden farklı:\n  sözlük: %r\n  yedek : %r'
        % (en['warn.solid.erosion_exponent_extrapolated'][:120], yedek[:120]))


if __name__ == '__main__':                  # pragma: no cover
    import sys
    sys.exit(pytest.main([__file__, '-v']))
