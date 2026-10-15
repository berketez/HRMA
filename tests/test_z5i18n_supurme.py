# -*- coding: utf-8 -*-
"""Z5 i18n SÜPÜRMESİ — bu dalgada onarılan kalemlerin bekçileri.

Kapsanan defter kalemleri (her biri için ayrı bekçi ve mutasyon kanıtı
docs/scofield/raw/OH/Z5/i18n/ altında):

  P12aB1-07  Karşılaştırma panelinde tek nesnenin iki Türkçe adı
             ("Kaydet" düğmesi ⟷ "anlık görüntü alın" iletisi)
  P12aB1-08  `dock.diff.basis` tek başına İngilizce yüzde düzeni ({pct} %)
  P12aB3-04  i18n_formulas.js'in AYRI terim dağarcığı
  P12aB3-05  Terim bekçisi yalnız i18n_pages.js'i okuyordu; kendi ölçütü
             bölgenin öbür sözlüklerinde ihlal buluyordu
  P12aB2-12  Aynı İngilizce metnin iki farklı Türkçe karşılığı
  P12aB3-10  Sözlüğün gölgelediği ÖLÜ çeviri kuralları (güvenlik uyarısı dâhil)
  P12aB3-12  i18n_launch_site.js'te hiç çağrılmayan anahtarlar
  P12aB2-06  i18n_pages.js'in "TÜM kullanıcı metinleri" kapsam iddiası
  P12aB2-11  T()/TF() yedek sözleşmesinin karşılamadığı durum
  OH-Z3-04   regen_cooling.py uyarılarının Türkçeye hiç geçmemesi
  OH-Z4-04   Yapısal hükmün sunucu gerekçe cümleleri (TR kipinde İngilizce)
  P15B3-12   Türetilmiş FALLBACK_SOURCES kapsamı (bağımsız doğrulama)

BEKÇİ FELSEFESİ: her test ÖLÇÜLEN bir sayıya ya da metne bağlıdır; hiçbiri
"dosya değişmesin" demez. Kusur geri getirildiğinde KIRMIZI olduğu
mutasyonla kanıtlandı (kanıt dizini yukarıda).
"""
import collections
import json
import re
import shutil
import subprocess
import sys
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
if str(pathlib.Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
JS = REPO / 'hrma' / 'static' / 'js'
TPL = REPO / 'hrma' / 'templates'

Z5_SOZLUK_YEDILISI = ('i18n_advanced.js', 'i18n_charts.js', 'i18n_common.js',
                    'i18n_formulas.js', 'i18n_launch_site.js',
                    'i18n_pages.js', 'i18n_shell.js')

needs_node = pytest.mark.skipif(shutil.which('node') is None,
                                reason='node kurulu değil')


# ---------------------------------------------------------------------------
# Hasat — sözlük bloklarını (anahtar, değer) olarak çıkarır
# ---------------------------------------------------------------------------
def _oku(path):
    return path.read_text(encoding='utf-8')


def _kacis_coz(metin):
    r"""JS kaynağındaki \uXXXX kaçışlarını çözer.

    i18n_launch_site.js Türkçe harfleri kaçışla yazıyor ('s\u00fcresi').
    Çözülmezse terim bekçisi o dosyada YANLIŞ KIRMIZI verir — ölçüldü
    (docs/scofield/raw/OH/Z5/i18n/00-*: kaçış çözülmeden 2 sahte ihlal).
    """
    return re.sub(r'\\u([0-9a-fA-F]{4})',
                  lambda m: chr(int(m.group(1), 16)), metin)


def _blok(path, lang):
    kaynak = _oku(path)
    m = re.search(r'^\s{8}%s:\s*\{' % lang, kaynak, re.M)
    assert m, '%s içinde %r bloğu yok' % (path.name, lang)
    govde = kaynak[m.end():]
    son = govde.index('\n        }')
    return re.findall(r"^\s*'([^']+)':\s*'(.*)',?$", govde[:son], re.M)


def sozluk(path, lang):
    return dict((k, _kacis_coz(v.rstrip(',').rstrip("'")))
                for k, v in _blok(path, lang))


# ---------------------------------------------------------------------------
# Türkçe/İngilizce küçültme — tests/test_i18n_pages.py ile AYNI kural
# ---------------------------------------------------------------------------
def fold_en(metin):
    return metin.casefold().replace('\u0307', '')


def fold_tr(metin):
    return (metin.replace('İ', 'i').replace('I', 'ı')
            .casefold().replace('\u0307', ''))


#: tests/test_i18n_pages.py:429 TERMS ile BİREBİR aynı — kopya değil, aynı
#: sözleşmenin bölge geneline uygulanması (P12aB3-05). Ayrışırsa
#: `test_terim_sozlugu_pages_bekcisiyle_ayni` kırmızı verir.
TERMS = {
    'chamber pressure': 'oda basınc',
    'thrust': 'itki',
    'nozzle': 'nozul',
    'throat': 'boğaz',
    'burn time': 'yanma süre',
    'specific impulse': 'özgül itki',
    'mass flow': 'kütle debi',
    'safety factor': 'emniyet katsayı',
    'wall thickness': 'cidar kalınlığ',
}


def test_terim_sozlugu_pages_bekcisiyle_ayni():
    """Bu dosyanın TERMS'i, pages bekçisinin TERMS'iyle özdeş kalmalı.

    P12aB3-05'in kusuru "ölçüt doğru ama kapsam dar"dı. Kapsamı genişleten
    bekçi, ölçütü de sessizce değiştirirse aynı kusurun tersi doğar.
    """
    kaynak = _oku(REPO / 'tests' / 'test_i18n_pages.py')
    m = re.search(r'^TERMS = \{(.*?)^\}', kaynak, re.M | re.S)
    assert m, 'test_i18n_pages.py içinde TERMS bloğu bulunamadı'
    onlarinki = dict(re.findall(r"'([^']+)':\s*'([^']+)'", m.group(1)))
    assert onlarinki == TERMS, (
        'İki bekçinin terim sözlüğü ayrıştı:\n  yalnız pages: %s\n'
        '  yalnız Z5: %s'
        % (sorted(set(onlarinki.items()) - set(TERMS.items())),
           sorted(set(TERMS.items()) - set(onlarinki.items()))))


@pytest.mark.parametrize('dosya', Z5_SOZLUK_YEDILISI)
@pytest.mark.parametrize('english,turkish', sorted(TERMS.items()))
def test_terimler_butun_sozluklerde_tutarli(dosya, english, turkish):
    """P12aB3-04 + P12aB3-05 — terim kanonu BÖLGENİN TAMAMINDA geçerli.

    ÖLÇÜLEN TABAN (bu dalga öncesi, raw/OH/Z5/i18n/00-once-terim-olcumu.txt):
    yedi sözlükte 23 ihlal — i18n_common 15, i18n_formulas 5, i18n_charts 1,
    (+2 sahte, kaçış körlüğünden). Onarımdan sonra: 0.

    Kanon ürünün KENDİ çoğunluğundan seçildi (raw/…/01-once-rakip-terim-
    sayimi.txt): nozul 111⟷lüle 84, özgül itki 22⟷özgül impuls 20,
    emniyet katsayısı 51⟷güvenlik katsayısı 2, oda basıncı 100⟷yanma odası
    basıncı 6, cidar kalınlığı 37⟷duvar kalınlığı 2.
    """
    yol = JS / dosya
    en, tr = sozluk(yol, 'en'), sozluk(yol, 'tr')
    hits = [k for k, v in en.items() if fold_en(v).startswith(english)]
    yanlis = [k for k in hits if k in tr and turkish not in fold_tr(tr[k])]
    assert not yanlis, (
        '%s: "%s" için beklenen karşılık "%s" değil:\n  %s'
        % (dosya, english, turkish,
           '\n  '.join('%s = %r' % (k, tr[k]) for k in yanlis[:10])))


def test_terim_bekcisi_bos_kapsamda_calismiyor_sayilmasin():
    """Bekçi GERÇEKTEN ölçüyor mu? Her terimin en az bir eşleşmesi olmalı.

    Kapsam genişletmesi bir terimi sessizce boşaltırsa (P13S1-01'de
    yaşandı: İngilizce değeri Türkçe küçültmek 'specific impulse'ı
    3'ten 0'a düşürmüştü) test hâlâ yeşil kalırdı. Burada TOPLU ölçülür.
    """
    toplam = collections.Counter()
    for dosya in Z5_SOZLUK_YEDILISI:
        en = sozluk(JS / dosya, 'en')
        for english in TERMS:
            toplam[english] += sum(
                1 for v in en.values() if fold_en(v).startswith(english))
    bos = sorted(t for t in TERMS if toplam[t] == 0)
    assert not bos, ('Bu terimlerin İngilizce sözlüklerde HİÇ eşleşmesi yok, '
                     'yani bekçi onlar için boşa koşuyor: %s' % bos)


# ---------------------------------------------------------------------------
# P12aB1-07 — karşılaştırma panelinde tek nesnenin tek adı
# ---------------------------------------------------------------------------
def test_karsilastirma_paneli_nesneyi_tek_adla_aniyor():
    """Kullanıcının bastığı düğme ile iletilerin dili aynı olmalı.

    ÖLÇÜLEN KUSUR: 'panel.comparative.btnSnapshot' = "Mevcut hesabı KAYDET"
    iken 'needTwoOverlay' / 'overlaySame' / 'overlayNoCommon' aynı nesneden
    "ANLIK GÖRÜNTÜ" diye söz ediyordu.
    """
    tr = sozluk(JS / 'i18n_common.js', 'tr')
    panel = {k: v for k, v in tr.items() if k.startswith('panel.comparative.')}
    assert panel, 'panel.comparative.* anahtarları kayboldu'

    ikinci_ad = sorted(k for k, v in panel.items() if 'anlık görüntü' in v.lower())
    assert not ikinci_ad, (
        'Karşılaştırma paneli aynı nesneye ikinci bir ad veriyor '
        '("anlık görüntü"), oysa düğme "kaydet" diyor: %s' % ikinci_ad)

    # Kanonun GERÇEKTEN orada olduğu: düğme ve iletiler aynı kökten.
    assert 'kaydet' in panel['panel.comparative.btnSnapshot'].lower()
    for anahtar in ('panel.comparative.needTwoOverlay',
                    'panel.comparative.overlaySame',
                    'panel.comparative.overlayNoCommon',
                    'panel.comparative.needTwo'):
        assert 'kayıt' in panel[anahtar].lower() or 'kayıtta' in panel[anahtar].lower(), \
            '%s nesneyi "kayıt" diye anmıyor: %r' % (anahtar, panel[anahtar])


# ---------------------------------------------------------------------------
# P12aB1-08 — yüzde imi TDK'da önektir
# ---------------------------------------------------------------------------
#: Sayı yer tutucusundan SONRA gelen yüzde imi: '{pct} %' ya da '{pct}%'
#: Türkçede yanlıştır (TDK: %25). Yalnız TR bloğunda aranır.
_SONEK_YUZDE = re.compile(r'\{(?:pct|coverage_pct|tol)\}\s*%')


def test_turkce_yuzde_imi_hep_onek():
    """P12aB1-08 — TR sözlüklerinde yüzde imi sayıdan ÖNCE gelmeli."""
    kirli = []
    for dosya in Z5_SOZLUK_YEDILISI:
        for k, v in sozluk(JS / dosya, 'tr').items():
            if _SONEK_YUZDE.search(v):
                kirli.append('%s :: %s = %r' % (dosya, k, v))
    assert not kirli, (
        'Türkçe metinde yüzde imi sonek düzeninde ({pct} %%) yazılmış; '
        'TDK kuralı önektir (%%{pct}):\n  ' + '\n  '.join(kirli))


def test_dock_diff_basis_yuzde_oneki_ve_yer_tutucu():
    """Onarılan tekil kalem: ölçü hem düzeni hem yer tutucuyu kilitler."""
    tr = sozluk(JS / 'i18n_common.js', 'tr')
    en = sozluk(JS / 'i18n_common.js', 'en')
    deger = tr['dock.diff.basis']
    assert '%{pct}' in deger, 'TDK önek düzeni kayboldu: %r' % deger
    # Yer tutucu kümesi iki dilde AYNI kalmalı — çeviri sayı uyduramaz.
    assert (set(re.findall(r'\{(\w+)\}', deger))
            == set(re.findall(r'\{(\w+)\}', en['dock.diff.basis'])))


# ---------------------------------------------------------------------------
# P12aB2-12 — aynı İngilizce metnin tek Türkçe karşılığı
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('dosya', Z5_SOZLUK_YEDILISI)
def test_ayni_ingilizce_tek_turkce_karsilik(dosya):
    """Bir sözlük dosyası içinde aynı EN değeri iki TR değerine gidemez.

    ÖLÇÜLEN TABAN: i18n_pages.js 2 küme, i18n_common.js 15 küme
    (raw/OH/Z5/i18n/06-once-ikili-karsilik.txt). Onarımdan sonra: 0/0.
    """
    yol = JS / dosya
    en, tr = sozluk(yol, 'en'), sozluk(yol, 'tr')
    grup = collections.defaultdict(dict)
    for k, v in en.items():
        if k in tr:
            grup[v].setdefault(tr[k], []).append(k)
    catisan = {v: d for v, d in grup.items() if len(d) > 1}
    assert not catisan, (
        '%s: aynı İngilizce metin iki farklı Türkçe karşılık taşıyor '
        '(%d küme):\n%s'
        % (dosya, len(catisan),
           '\n'.join('  EN %r\n%s' % (v, '\n'.join(
               '      TR %r <- %s' % (tv, ', '.join(sorted(ks)))
               for tv, ks in sorted(d.items())))
               for v, d in sorted(catisan.items())[:5])))


# ---------------------------------------------------------------------------
# P12aB3-10 — sözlüğün gölgelediği ölü çeviri kuralı
# ---------------------------------------------------------------------------
def _yorumsuz(metin):
    """/* … */ blok yorumlarını atar (silinen kuralların kaydı ölçümü
    kirletmesin: yorum kod değildir, çalışmaz)."""
    return re.sub(r'/\*.*?\*/', '', metin, flags=re.S)


def _kural_desenleri(metin, ad):
    m = re.search(r'var %s = \[' % ad, metin)
    assert m, '%s listesi bulunamadı' % ad
    govde = metin[m.end():]
    derinlik, i = 1, 0
    while derinlik:
        if govde[i] == '[':
            derinlik += 1
        elif govde[i] == ']':
            derinlik -= 1
        i += 1
    return re.findall(r"\[/\^(.+?)\$/,\s*\n?\s*'", govde[:i - 1], re.S)


def _duz_metne_indir(desen):
    """Yakalama grubu yoksa deseni düz metne indirger, yoksa None."""
    if '(' in desen.replace('\\(', ''):
        return None
    duz = desen
    for kacis, harf in (('\\/', '/'), ('\\.', '.'), ('\\(', '('), ('\\)', ')'),
                        ('\\[', '['), ('\\]', ']'), ('\\*', '*'),
                        ('\\?', '?'), ('\\+', '+'), ('\\-', '-'),
                        ('\\!', '!')):
        duz = duz.replace(kacis, harf)
    if re.search(r'(?<!\\)[\\|]', duz):
        return None
    return duz


@pytest.mark.parametrize('liste', ('PATTERNS', 'MSG_PATTERNS'))
def test_sozluk_hicbir_ceviri_kuralini_golgelemiyor(liste):
    """P12aB3-10 — sözlükte KARŞILIĞI OLAN metin için kural yazılamaz.

    `chartText`/`serverText` önce sözlüğe bakar (translateSegment:
    lookup → applyPatterns). Sözlük vurursa kural HİÇ çalışmaz; iki
    kaynak sessizce ayrışır. ÖLÇÜLEN TABAN: 3 ölü kural — biri GÜVENLİK
    uyarısı ('WARNING: HTPB/ClF3 is extremely hypergolic and dangerous!',
    sözlükte "son derece hipergolik", kuralda "aşırı hipergoliktir").
    """
    metin = _yorumsuz(_oku(JS / 'i18n_charts.js'))
    en = sozluk(JS / 'i18n_charts.js', 'en')
    olu = []
    for desen in _kural_desenleri(metin, liste):
        duz = _duz_metne_indir(desen)
        if duz is not None and duz in en:
            olu.append(duz)
    assert not olu, (
        '%s içinde sözlüğün gölgelediği (asla çalışmayan) kural(lar): %s'
        % (liste, olu))


# ---------------------------------------------------------------------------
# P12aB3-12 — i18n_launch_site.js'te ölü anahtar yok
# ---------------------------------------------------------------------------
#: Şablonun tek dinamik anahtar kurulumu (launch_site.html:549):
#: `t('site.src.' + src, src)` — bu aile ADIYLA aranamaz, önekle korunur.
_DINAMIK_ONEKLER = ('site.src.',)


def test_launch_site_sozlugunde_olu_anahtar_yok():
    """P12aB3-12 — çağrılmayan anahtar ölü çeviridir.

    ÖLÇÜLEN TABAN: 104 anahtarın 15'i (%14,4) ürünün hiçbir yerinde
    geçmiyordu (hiç kurulmamış görünüm-kipi seçicisi + okuma paneli).
    Onarım: 15 anahtar iki dilden de silindi, 104 -> 89.

    NOT: taban ölçümü `git grep` ile alındığında `site.atmosphere`
    YANLIŞ CANLI görünüyordu — Python tarafındaki modül yolu
    `hrma.analysis.launch_site.atmosphere_at` metnin içinde geçiyor.
    Bu yüzden bekçi grep yerine ADI GEÇEN tüketici yüzeyini okur.
    """
    yol = JS / 'i18n_launch_site.js'
    en = sozluk(yol, 'en')
    # Tüketici yüzeyi: launch_site ile ilgili şablon + JS.
    tuketiciler = [TPL / 'launch_site.html',
                   JS / 'launch_site_globe.js',
                   JS / 'user_guide.js']
    govde = '\n'.join(_oku(p) for p in tuketiciler if p.exists())
    olu = [k for k in sorted(en)
           if k not in govde and not k.startswith(_DINAMIK_ONEKLER)]
    assert not olu, (
        'i18n_launch_site.js: ürünün hiçbir yerinde çağrılmayan anahtar '
        '(%d): %s' % (len(olu), olu))


def test_launch_site_dinamik_onek_gercekten_kullaniliyor():
    """Muafiyet listesi çürümesin: `site.src.` gerçekten dinamik kuruluyor.

    Bu test olmasa `_DINAMIK_ONEKLER` sessizce bir kaçış deliğine dönerdi.
    """
    html = _oku(TPL / 'launch_site.html')
    assert "'site.src.' +" in html, (
        "launch_site.html artık 'site.src.' önekini dinamik kurmuyor — "
        "muafiyet gerekçesi düştü, listeyi güncelleyin")
    en = sozluk(JS / 'i18n_launch_site.js', 'en')
    aile = [k for k in en if k.startswith('site.src.')]
    assert len(aile) >= 3, 'site.src.* ailesi beklenmedik biçimde küçüldü: %s' % aile


def test_launch_site_en_tr_paritesi():
    """Silme iki dilde birden yapıldı mı? (parite sözleşmesi)"""
    en = sozluk(JS / 'i18n_launch_site.js', 'en')
    tr = sozluk(JS / 'i18n_launch_site.js', 'tr')
    assert set(en) == set(tr), (
        'EN/TR anahtar kümesi ayrıştı: yalnız EN %s / yalnız TR %s'
        % (sorted(set(en) - set(tr)), sorted(set(tr) - set(en))))


# ---------------------------------------------------------------------------
# P12aB2-06 / P12aB2-11 — kapsam ve yedek sözleşmesi İDDİALARI dürüst
# ---------------------------------------------------------------------------
def test_pages_sozlugu_tum_metinleri_kapsadigini_iddia_etmiyor():
    """P12aB2-06 — ölçülemeyen kapsam iddiası dosyadan kalkmalı.

    Dosyanın başlığı "sayfaların TÜM kullanıcı metinleri" diyordu; ölçüm
    (raw/OH/Z5/i18n/05-bagsiz-ingilizce-metin.txt + defter tablosu) iki
    şablonda T()/TF() ile HİÇ bağlanmamış 12 görünür metin buluyor.
    """
    bas = _oku(JS / 'i18n_pages.js')[:4000]
    # İDDİA cümlesinin kendisi aranır; "eskiden şöyle diyordu" kaydı değil.
    assert 'sayfalarının TÜM kullanıcı metinleri' not in bas, (
        'i18n_pages.js hâlâ ölçülemeyen "TÜM kullanıcı metinleri" iddiasında')
    assert 'P12aB2-06' in bas, 'borç dosyada adıyla kayıtlı değil'
    # Borcun DÖKÜMÜ de dursun: iddia kalkarken ölçüm de kaybolmasın.
    for iz in ('Oxidizer Tank', 'Success Rate',
               'liq.msg.trajectory_data_could_not_be_retrieved'):
        assert iz in bas, 'kapsam borcunun dökümünden %r düşmüş' % iz


def test_bagsiz_ingilizce_metinler_defterdeki_sayidan_artmadi():
    """Borç BÜYÜMESİN: kart üreteçlerine düz İngilizce dize eklenmesin.

    `row(...)` / `wide(...)` / `addCard(...)` ilk argümanı ekrana basar;
    düz dize verilirse metin iki dilde de İngilizce kalır.

    ÖH D29 / arayuz-i18n a1 — MANDAL SIKILDI, BORÇ SIFIRLANDI. Taban
    ölçümü solid.html 0, liquid.html 4 idi (Material / Coolant / Title /
    Status); dördü de `liq.js.row_*` anahtarlarıyla bağlandı (ölçüm:
    raw/OH/D29/arayuz-i18n/a1/{once,sonra}.json, M1). Eşik ARTIK 0:
    `<= 4` bırakılsaydı aynı kusurdan dördü sessizce geri gelebilirdi.
    """
    uretecler = ('row', 'wide', 'addCard')
    ingilizce = re.compile(r"^[A-Z][A-Za-z][A-Za-z ./&()\-']{2,}$")
    bulunan = {}
    for ad in ('solid.html', 'liquid.html'):
        n = 0
        for uretec in uretecler:
            for m in re.finditer(r"\b%s\(\s*'((?:[^'\\]|\\.)*)'" % uretec,
                                 _oku(TPL / ad)):
                if ingilizce.match(m.group(1)):
                    n += 1
        bulunan[ad] = n
    assert bulunan['solid.html'] == 0, bulunan
    assert bulunan['liquid.html'] == 0, (
        'liquid.html içinde T() ile bağlanmamış kart etiketi VAR '
        '(D29 sonrası taban 0, şimdi %d) — P12aB2-06 borcu geri geldi'
        % bulunan['liquid.html'])


def test_yedek_sozlesmesi_karsilamadigi_durumu_soyluyor():
    """P12aB2-11 — BORÇ ÖDENDİ (ÖH D29 / arayuz-i18n a2).

    ESKİ ÖLÇÜM (bu bekçinin kurulduğu gün): `global.T` yalnız
    i18n_pages.js'te tanımlıydı; o dosya yüklenemezse solid+liquid'deki
    934 çağrı ReferenceError atıp sayfayı susturuyordu. Bekçi bunu bir
    BORÇ İMİ olarak kilitliyordu ve "sözü tersine çeviren kod girerse
    kırmızı verir, yorum güncellenir" diyordu — nitekim öyle oldu.

    YENİ ÖLÇÜT: sözleşme ÇEKİRDEKTE (i18n.js) tanımlı olmalı; sayfa
    sözlüğü (i18n_pages.js) onu EZMEMELİ. Bekçi artık borcu değil
    ÖDEMEYİ kilitliyor — çekirdek tanımı sökülürse kırmızı verir.
    Ölçüm: docs/scofield/raw/OH/D29/arayuz-i18n/a2/{once,sonra}.json M5
    (i18n.js T/TF tanımı 0 -> 1); canlı koşum bekçisi
    tests/test_d29_arayuz_i18n_a2.py::test_p12ab2_11_T_TF_cekirdekte_tanimli.
    """
    kaynak = _oku(JS / 'i18n_pages.js')
    assert 'P12aB2-11' in kaynak, 'yedek sözleşmesinin künyesi dosyada yazılı değil'

    tanimlayanlar = [p.name for p in sorted(JS.glob('*.js'))
                     if re.search(r'\bglobal\.T\s*=', _oku(p))]
    assert 'i18n.js' in tanimlayanlar, (
        'T taban sözleşmesi çekirdekten sökülmüş: %s' % tanimlayanlar)
    # Sayfa sözlüğü çekirdeği EZMEZ: kendi tanımını kapıya alır.
    assert re.search(r"if \(typeof global\.T !== 'function'\)", kaynak), \
        'i18n_pages.js çekirdek tanımını koşulsuz eziyor (tek kaynak kırıldı)'
    assert re.search(r"if \(typeof global\.TF !== 'function'\)", kaynak), \
        'i18n_pages.js TF tanımını koşulsuz eziyor'
    # Şablonlar hâlâ kendi taban tanımını YAPMAZ (tek kaynak çekirdektir).
    for ad in ('solid.html', 'liquid.html'):
        html = _oku(TPL / ad)
        assert not re.search(r'\b(?:window|global)\.T\s*=', html), (
            '%s kendi T taban tanımını yapıyor — sözleşme artık '
            'çekirdekte, ikinci kaynak açılmamalı' % ad)


# ---------------------------------------------------------------------------
# OH-Z3-04 / OH-Z4-04 — sunucu metinleri Türkçeye geçiyor mu? (node koşumu)
# ---------------------------------------------------------------------------
_SURUCU = r"""
'use strict';
const fs = require('fs');
const g = {};
g.I18N = { lang: 'tr' };
g.setTimeout = setTimeout;
g.setInterval = function () { return 0; };
g.clearInterval = function () {};
const kaynak = fs.readFileSync(process.argv[2], 'utf8');
(new Function('global', kaynak)).call(g, g);
const S = (g.I18N && g.I18N.serverText) ? g.I18N.serverText
                                        : g.HRMAChartI18N.serverText;
const girdi = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
process.stdout.write(JSON.stringify(girdi.map(function (t) {
    return { in: t, out: S(t) };
})));
"""

#: regen_cooling.py'nin 15 uyarısının HEPSİ (örnek sayılarla). Sayılar
#: temsilîdir; bekçi metnin ÇEVRİLDİĞİNİ ölçer, sayıyı değil.
REGEN_UYARILARI = [
    "CRITICAL: peak hot-wall temperature 1900 K exceeds Copper C18150 melting point 1356 K — liner failure.",
    "UNSAFE: peak hot-wall temperature 1250 K exceeds Inconel 718 service limit 1200 K.",
    "WARNING: peak hot-wall temperature 980 K exceeds Copper C18150 allowable 900 K — strength margin reduced.",
    "COKING: RP-1 coolant-side wall temperature reaches 620 K, above the ~590 K coking threshold (Huzel & Huang Ch. 4) — carbon deposition and channel fouling likely.",
    "PROPERTY RANGE: rp1 bulk temperature leaves the internal property table band (280-560 K) at 7 station(s) (T_bulk 265-575 K); properties there are FROZEN at the nearest band edge — transport properties and the coolant-side coefficient are an extrapolation outside the source validity envelope.",
    "NOTE: minimum channel Reynolds number 6400 is below the Dittus-Boelter turbulent floor (~1e4); the coolant-side coefficient there is an extrapolation.",
    "GEOMETRY: 120 channels of width 2.50 mm exceed the throat circumference (188.5 mm) — channels do not physically fit; reduce count/width.",
    "BOILING: water exit temperature 420 K exceeds the saturation temperature 410 K at the outlet pressure — single-phase assumption violated.",
    "SUBCRITICAL PRESSURE: methane inlet pressure 35.0 bar is below the critical pressure 46.0 bar — boiling is possible; the model stays single phase and only FLAGS the risk (no two-phase model).",
    "NOTE: coolant bulk temperature crosses the pseudo-critical temperature (205 K at inlet pressure) along the channel — strong property variation; the enthalpy march and Jackson property-ratio corrections account for it to first order.",
    "BOILING: coolant bulk temperature reaches/exceeds the local saturation temperature at 4 station(s) (subcritical pressure) — single-phase assumption violated; results there are not valid.",
    "BOILING RISK: coolant bulk temperature is within 15 K (screening margin) of the local saturation temperature at 9 station(s).",
    "NUCLEATE BOILING RISK: coolant-side wall temperature exceeds the local saturation temperature at 3 station(s) (subcritical pressure) — wall boiling not modelled.",
    "CONVERGENCE: the coupled wall balance did not converge to 1e-3 K at 2 station(s) — wall temperatures there carry iteration residual.",
    "NOTE: Jackson wall-side property ratios evaluated at the methane EOS temperature limit (625 K) at 5 station(s) — the coolant-side coefficient there is an extrapolation (wall-limit warnings apply independently).",
]

#: structural_analysis.py:2057-2084 dört gerekçe dalı (OH-Z4-04).
HUKUM_GEREKCELERI = [
    "No acceptance is issued and no verdict is issued at all: every safety factor in this response (chamber_hoop, end_cap, nozzle_throat) is the design target read back - HRMA sized those sections to meet the target, so the number cannot fall below it and carries no information about a wall you built. Supply the real wall / throat / head thickness to earn a verdict; the target itself is graded in design_target_assessment.",
    "No acceptance is issued: the measured sections (chamber_hoop) would pass, but end_cap, nozzle_throat were sized by HRMA and therefore not verified. An acceptance that does not cover every station is not an acceptance. The measured-scope result is published separately in measured_scope_status.",
    "The verdict comes from verdict_safety_factor, the lowest safety factor actually measured on a drawn wall (chamber_hoop, end_cap). This is a measured warning and is never suppressed. Sections not verified: nozzle_throat; of those, nozzle_throat only read the design target back.",
    "Every station in the basket was evaluated against a user-supplied thickness (chamber_hoop, end_cap, nozzle_throat), so the verdict is an independent verification drawn from verdict_safety_factor.",
]


def _serverText(metinler, tmp_path):
    surucu = tmp_path / 'surucu.js'
    surucu.write_text(_SURUCU, encoding='utf-8')
    girdi = tmp_path / 'girdi.json'
    girdi.write_text(json.dumps(metinler, ensure_ascii=False), encoding='utf-8')
    ciktı = subprocess.run(
        [shutil.which('node'), str(surucu), str(JS / 'i18n_charts.js'),
         str(girdi)], capture_output=True, text=True, timeout=120)
    assert ciktı.returncode == 0, ciktı.stderr[-2000:]
    return json.loads(ciktı.stdout)


@needs_node
def test_regen_sogutma_uyarilarinin_hepsi_turkceye_geciyor(tmp_path):
    """OH-Z3-04 — regen_cooling.py'nin 15 uyarısı da TR kipinde çevrilmeli.

    ÖLÇÜLEN TABAN (raw/OH/Z5/i18n/03-serverText-once-sonra.txt): 15'ten
    yalnız 2'si (COKING + CRITICAL erime) çevriliyordu; kalan 13'ü —
    kaynama, çekirdekli kaynama, kritik altı basınç, kanalların fiziksel
    olarak sığmaması, yakınsamama dâhil — İngilizce kalıyordu.
    """
    sonuc = _serverText(REGEN_UYARILARI, tmp_path)
    cevrilmeyen = [r['in'][:90] for r in sonuc if r['out'] == r['in']]
    assert not cevrilmeyen, (
        'Türkçe kipte İngilizce kalan regen uyarısı (%d):\n  %s'
        % (len(cevrilmeyen), '\n  '.join(cevrilmeyen)))


@needs_node
def test_regen_cevirisi_sayilari_aynen_tasiyor(tmp_path):
    """Çeviri hiçbir sayıyı yeniden yazmaz (uydurma değer yasağı).

    ÇOKLU KÜME olarak karşılaştırılır, sıralı DİZİ olarak değil: Türkçe
    sözdizimi yakalama gruplarının sırasını değiştirebilir ve bu meşrudur
    ("120 channels of width 2.50 mm" -> "2.50 mm genişliğindeki 120 kanal").
    Yasak olan, bir sayının KAYBOLMASI ya da YENİSİNİN doğmasıdır.
    """
    sonuc = _serverText(REGEN_UYARILARI + HUKUM_GEREKCELERI, tmp_path)
    for r in sonuc:
        girdi_sayilar = collections.Counter(re.findall(r'\d+(?:\.\d+)?', r['in']))
        cikti_sayilar = collections.Counter(re.findall(r'\d+(?:\.\d+)?', r['out']))
        assert girdi_sayilar == cikti_sayilar, (
            'Çeviri sayı kümesini değiştirdi:\n  EN %s\n  TR %s\n  metin: %s'
            % (sorted(girdi_sayilar.elements()),
               sorted(cikti_sayilar.elements()), r['out'][:120]))


@needs_node
def test_yapisal_hukum_gerekceleri_turkceye_geciyor(tmp_path):
    """OH-Z4-04 (sunucu cümlesi ayağı) — dört gerekçe dalı da çevrilmeli.

    İstasyon adları MAKİNE ADIDIR; çeviride aynen kalmalı.
    """
    sonuc = _serverText(HUKUM_GEREKCELERI, tmp_path)
    cevrilmeyen = [r['in'][:90] for r in sonuc if r['out'] == r['in']]
    assert not cevrilmeyen, (
        'Yapısal hüküm gerekçesi İngilizce kaldı:\n  %s'
        % '\n  '.join(cevrilmeyen))
    for r in sonuc:
        for ad in ('chamber_hoop', 'end_cap', 'nozzle_throat',
                   'verdict_safety_factor', 'design_target_assessment',
                   'measured_scope_status'):
            if ad in r['in']:
                assert ad in r['out'], (
                    'Makine adı %r çeviride kayboldu: %r' % (ad, r['out'][:120]))


@needs_node
def test_olu_kural_silinmesi_ekrandaki_metni_degistirmedi(tmp_path):
    """P12aB3-10 — silinen üç kuralın metinleri HÂLÂ çevriliyor.

    Kurallar ölüydü: çeviri zaten sözlükten geliyordu. Silme ekranda
    hiçbir şeyi değiştirmemeli — bu test onu ölçer.
    """
    sonuc = _serverText([
        'WARNING: HTPB/ClF3 is extremely hypergolic and dangerous!',
        'Note: Cryogenic propellants require specialized handling equipment',
    ], tmp_path)
    assert sonuc[0]['out'] == 'UYARI: HTPB/ClF3 son derece hipergolik ve tehlikelidir.'
    assert sonuc[1]['out'] == ('Not: Kriyojenik iticiler özel taşıma ve '
                               'kullanım ekipmanı gerektirir')


# ---------------------------------------------------------------------------
# P15B3-12 — türetilmiş kapsam (bağımsız doğrulama)
# ---------------------------------------------------------------------------
def test_parca_kopya_kapsami_turetilmis_ve_advanced_html_iceride():
    """P15B3-12 — kapsam elle listeden türetmeye geçti mi?

    Kalem "elle-liste çürümesi" diye açılmış, sonra ölçümle TERSİNE
    dönmüştü: advanced.html katkısız üye DEĞİLDİ, hasatçı `i18nText(...)`
    biçimini görmüyordu. Burada BAĞIMSIZ ölçülür: kapsam 5'ten çok daha
    geniş olmalı ve advanced.html gerçekten anahtar vermeli.
    """
    import test_i18n_parca_kopya as M  # noqa: E402  (tests/ sys.path'te)
    assert len(M.FALLBACK_SOURCES) >= 39, (
        'kapsam daraldı: %d kaynak (türetilmiş taban 39)'
        % len(M.FALLBACK_SOURCES))
    adlar = {p.name for p in M.FALLBACK_SOURCES}
    assert 'advanced.html' in adlar
    adv = next(p for p in M.FALLBACK_SOURCES if p.name == 'advanced.html')
    anahtarlar = set(M._CAGRI_RE.findall(_oku(adv)))
    assert len(anahtarlar) >= 150, (
        'advanced.html katkısı beklenenden düşük (%d < 150) — hasatçı yine '
        'bir çağrı biçimini görmüyor olabilir' % len(anahtarlar))


# ---------------------------------------------------------------------------
# Bütünlük — sözdizim ve blok yapısı bozulmadı
# ---------------------------------------------------------------------------
@needs_node
@pytest.mark.parametrize('dosya', Z5_SOZLUK_YEDILISI)
def test_sozluk_dosyalari_node_check_temiz(dosya):
    sonuc = subprocess.run([shutil.which('node'), '--check', str(JS / dosya)],
                           capture_output=True, text=True, timeout=120)
    assert sonuc.returncode == 0, sonuc.stderr[-2000:]


@pytest.mark.parametrize('dosya', Z5_SOZLUK_YEDILISI)
def test_yer_tutucu_paritesi(dosya):
    """Terim/kanon süpürmesi hiçbir yer tutucuyu düşürmedi mi?

    Bu dalgada ~130 Türkçe değer elden geçti. Çeviri UYDURMA değer
    taşıyamaz; bunun mekanik ölçüsü, {…} yer tutucu ÇOKLU KÜMESİNİN iki
    dilde birebir aynı kalmasıdır. Sıra değişebilir (Türkçe sözdizimi),
    sayısı ve adı değişemez. ÖLÇÜLDÜ: yedi sözlükte kırık 0.
    """
    en, tr = sozluk(JS / dosya, 'en'), sozluk(JS / dosya, 'tr')
    kirik = []
    for k in sorted(en):
        if k not in tr:
            continue
        a = collections.Counter(re.findall(r'\{(\w+)\}', en[k]))
        b = collections.Counter(re.findall(r'\{(\w+)\}', tr[k]))
        if a != b:
            kirik.append('%s: EN %s / TR %s'
                         % (k, sorted(a.elements()), sorted(b.elements())))
    assert not kirik, ('%s: yer tutucu paritesi kırık (%d):\n  %s'
                       % (dosya, len(kirik), '\n  '.join(kirik[:10])))


@pytest.mark.parametrize('dosya', Z5_SOZLUK_YEDILISI)
def test_en_tr_anahtar_kumeleri_birebir(dosya):
    en, tr = sozluk(JS / dosya, 'en'), sozluk(JS / dosya, 'tr')
    assert set(en) == set(tr), (
        '%s: yalnız EN %s / yalnız TR %s'
        % (dosya, sorted(set(en) - set(tr))[:10],
           sorted(set(tr) - set(en))[:10]))
