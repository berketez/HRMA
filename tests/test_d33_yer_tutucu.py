# -*- coding: utf-8 -*-
"""ÖH D33 · OH-D33-48 — FORM YER TUTUCUSU: ÇEVRİLİ OLACAK VE ALANA SIĞACAK.

Neden bu dosya var
------------------
OH-D33-47 (emsal, ``954177c6``) katı sayfasında İKİ yer tutucu buldu: ikisi
de Türkçe arayüzde İngilizce duruyordu ve ikisi de alandan taşıp sözcük
ortasından kırpılıyordu. O onarım iki alanı kapattı ama SINIFI kapatmadı;
kapanış notu da bunu adıyla yazdı ("bu iki alan buzdağının görünen kısmı").

Bu süpürme dalgasında şablonların TAMAMI ölçüldü (Playwright, sistem
Chrome'u, 1440x900, hem ``en`` hem ``tr`` kipinde, gerçek sunucu):

* 60 yer tutucunun 7'sinde çeviri anahtarı YOKTU ve hepsi ``liquid.html``
  içindeydi; Türkçe arayüzde İngilizce duruyorlardı.
* 22 yer tutucu-alan çifti (dil ayrı sayılırsa) alandan TAŞIYORDU. En kötüsü
  ``#chamber_pressure``: 286 piksellik alanda 1024,8 piksellik metin, yani
  görünen kısım dörtte birden azdı.

Ölçümün fiziği
--------------
Girdi alanları tek aralıklı (monospace) 14 piksellik yazı tipiyle çiziliyor
(``14px "JetBrains Mono", "SF Mono", Consolas, monospace``). Ölçülen ilerleme
genişliği HER karakter için 8,4 piksel; 122 karakterlik dize tam 1024,8
piksel ölçtü (122 x 8,4). Bu yüzden bütçe KARAKTER cinsinden yazılabiliyor ve
bu bekçinin tarayıcıya ihtiyacı yok: alanın ölçülen iç genişliği burada
durur, kural ``karakter x 8,4 <= iç genişlik`` olarak uygulanır.

Bekçinin kuralı METİN DEĞİL KURALDIR: hangi cümlenin yazılacağını değil,
(a) her yer tutucunun bir çeviri anahtarına bağlı olmasını, (b) anahtarın
sayfanın yüklediği sözlükte EN+TR olarak bulunmasını, (c) şablondaki yedek
metnin EN sözlük girdisiyle birebir aynı olmasını, (d) iki dildeki metnin de
ölçülen alana sığmasını şart koşar. Yeni bir yer tutucu eklenip ölçülmezse
bekçi KIRMIZI verir (fail-closed): ölçülmemiş alan "sığıyor" sayılmaz.
"""
import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
SABLONLAR = KOK / 'hrma' / 'templates'
JS_DIZINI = KOK / 'hrma' / 'static' / 'js'

#: Ölçülen tek aralıklı ilerleme genişliği (piksel/karakter). 14px yazı tipi;
#: canvas ``measureText`` her dizede tam ``8.4 * uzunluk`` döndürdü.
PIKSEL_KARAKTER = 8.4

#: Alanların ÖLÇÜLEN iç genişliği (clientWidth - yatay dolgu), piksel.
#: Kaynak: Playwright turu, sistem Chrome'u, 1440x900, ``en`` ve ``tr``
#: kipleri; iki dilden KÜÇÜK olan değer yazıldı. Gizli sekmelerdeki alanlar
#: ölçüm sırasında ``display:block !important`` ile görünür kılındı, ölçüm
#: bitince sayfa eski hâline döndürüldü. Enjektör kollarının alanları
#: (``outer_diameter``, ``pintle_diameter``, ``n_slots``) ilgili enjektör
#: türü seçilerek ayrıca ölçüldü.
#: simple.html (1) + uzaytek.html (3) ölçüm girdileri emekli — sayfa sökümü: Berke 23 Eyl, dalga36/sokum
ALAN_GENISLIGI = {
    ('advanced.html', 'ambient_temp'): 302,
    ('advanced.html', 'burn_time_impulse'): 403,
    ('advanced.html', 'chamber_diameter_input'): 312,
    ('advanced.html', 'chamber_length_override'): 302,
    ('advanced.html', 'contraction_ratio'): 312,
    ('advanced.html', 'discharge_coefficient'): 666,
    ('advanced.html', 'expansion_ratio'): 312,
    ('advanced.html', 'feed_line_inner_diameter_mm'): 312,
    ('advanced.html', 'feed_line_length_m'): 312,
    ('advanced.html', 'hole_diameter_max'): 312,
    ('advanced.html', 'hole_diameter_min'): 312,
    ('advanced.html', 'l_star'): 312,
    ('advanced.html', 'motor_description'): 646,
    ('advanced.html', 'motor_name'): 646,
    ('advanced.html', 'n_holes_override'): 302,
    ('advanced.html', 'n_slots'): 312,
    ('advanced.html', 'outer_diameter'): 312,
    ('advanced.html', 'oxidizer_density'): 312,
    ('advanced.html', 'parachute_area'): 302,
    ('advanced.html', 'parachute_cd'): 302,
    ('advanced.html', 'parachute_deploy_delay'): 302,
    ('advanced.html', 'pintle_diameter'): 312,
    ('advanced.html', 'port_count'): 312,
    ('advanced.html', 'tank_pressure'): 1334,
    ('advanced.html', 'target_velocity'): 312,
    ('advanced.html', 'thrust_impulse'): 403,
    ('liquid.html', 'chamber_diameter'): 286,
    ('liquid.html', 'chamber_pressure'): 286,
    ('liquid.html', 'closure_bolt_count'): 286,
    ('liquid.html', 'feed_line_diameter_mm'): 286,
    ('liquid.html', 'feed_line_length_m'): 286,
    ('liquid.html', 'feed_line_wall_thickness'): 286,
    ('liquid.html', 'fuel_density'): 286,
    ('liquid.html', 'fuel_viscosity'): 286,
    ('liquid.html', 'gimbal_actuator_arm'): 286,
    ('liquid.html', 'gimbal_bolt_circle'): 286,
    ('liquid.html', 'gimbal_bolt_count'): 286,
    ('liquid.html', 'gimbal_ring_offset'): 286,
    ('liquid.html', 'mixture_ratio'): 286,
    ('liquid.html', 'oxidizer_density'): 286,
    ('liquid.html', 'oxidizer_viscosity'): 286,
    ('liquid.html', 'temp_range_min'): 286,
    ('liquid.html', 'thrust'): 286,
    ('liquid.html', 'traj_burn_time'): 241,
    ('liquid.html', 'valve_closure_time_ms'): 286,
    ('solid.html', 'burn_rate_a'): 286,
    ('solid.html', 'burn_rate_n'): 286,
    ('solid.html', 'case_thickness'): 286,
    ('solid.html', 'closure_bolt_count'): 286,
    ('solid.html', 'parachute_area'): 206,
    ('solid.html', 'parachute_cd'): 206,
    ('solid.html', 'parachute_deploy_delay'): 206,
    ('solid.html', 'propellant_name'): 286,
    ('solid.html', 'two_phase_loss'): 286,
}

#: Çeviri anahtarı ARANMAYAN yer tutucular ve GEREKÇESİ.
#: Muafiyet bir kaçış kapısı değildir: aşağıdaki iki desen dil taşımaz,
#: dolayısıyla çevrilecek bir şey yoktur. ``test_muafiyet_gercekten_dilsiz``
#: bu listeyi kuralın kendisine karşı ölçer; prosa bir metin muafiyet
#: kapsamına giremez.
#:
#: 1. SALT SAYI ÖRNEĞİ — ``'1'``, ``'0.78'``, ``'293.15'``. Alanın beklediği
#:    büyüklüğün örnek değeri; rakam her iki dilde de aynıdır. (Ondalık
#:    ayracı ayrı bir kalemdir ve ``i18n.js::ondalikAyraci`` tek kaynağına
#:    bağlıdır; yer tutucudaki örnek sayı kullanıcıya okunan bir SONUÇ
#:    değildir.)
#: 2. UZUN TİRE — ``'—'``. "Değer yok / boş bırakılabilir" anlamındaki
#:    tipografik im; sözcük içermez, çevrilecek dili yoktur.
SAYI_ORNEGI = re.compile(r'^\d+(?:[.,]\d+)?$')
UZUN_TIRE = '—'


def _muaf_mi(metin):
    return bool(SAYI_ORNEGI.match(metin)) or metin == UZUN_TIRE


# ---------------------------------------------------------------------------
# Şablon ayrıştırma
# ---------------------------------------------------------------------------
ETIKET = re.compile(r'<(?:input|textarea|select)\b[^>]*>', re.S | re.I)
#: ``data-i18n-placeholder`` ile karışmasın diye önünde boşluk şartı var.
YER_TUTUCU = re.compile(r'(?:^|\s)placeholder\s*=\s*"([^"]*)"')
ANAHTAR = re.compile(r'(?:^|\s)data-i18n-placeholder\s*=\s*"([^"]*)"')
KIMLIK = re.compile(r'(?:^|\s)id\s*=\s*"([^"]*)"')
SOZLUK_IMI = re.compile(r'<script\s+src="/static/js/(i18n[^"]*\.js)"')


def _sablon_yer_tutuculari():
    """Her şablondaki yer tutucuları (dosya, satır, kimlik, anahtar, metin)."""
    kayitlar = []
    for yol in sorted(SABLONLAR.glob('*.html')):
        govde = yol.read_text(encoding='utf-8')
        for m in ETIKET.finditer(govde):
            etiket = m.group(0)
            yt = YER_TUTUCU.search(etiket)
            if not yt:
                continue
            anahtar = ANAHTAR.search(etiket)
            kimlik = KIMLIK.search(etiket)
            kayitlar.append({
                'dosya': yol.name,
                'satir': govde[:m.start()].count('\n') + 1,
                'kimlik': kimlik.group(1) if kimlik else '',
                'anahtar': anahtar.group(1) if anahtar else None,
                'metin': yt.group(1),
            })
    return kayitlar


KAYITLAR = _sablon_yer_tutuculari()
#: Süpürmenin ölçtüğü sayı. Şablona yeni yer tutucu girerse bu bekçi onu
#: kendiliğinden kapsar (liste elle tutulmaz), ama ölçüm tablosuna
#: yazılmadıkça ``test_alan_genisligi_olculmus`` kırmızı verir.
assert KAYITLAR, 'şablonlarda hiç yer tutucu bulunamadı — ayrıştırıcı bozuk'


def _kimlik(kayit):
    return '%s:%d:%s' % (kayit['dosya'], kayit['satir'],
                         kayit['kimlik'] or '(kimliksiz)')


CEVRILECEKLER = [k for k in KAYITLAR if not _muaf_mi(k['metin'])]
MUAFLAR = [k for k in KAYITLAR if _muaf_mi(k['metin'])]


# ---------------------------------------------------------------------------
# Sözlük ayrıştırma
# ---------------------------------------------------------------------------
def _sayfanin_sozlukleri(dosya):
    """Şablonun KENDİ yüklediği i18n dosyaları (elle tutulan eşleme yok)."""
    govde = (SABLONLAR / dosya).read_text(encoding='utf-8')
    return [JS_DIZINI / ad for ad in SOZLUK_IMI.findall(govde)]


def _sozluk_degerleri(anahtar, dosyalar):
    """Anahtarın sözlüklerdeki değerleri; sıra EN, TR (dosyadaki sıra)."""
    desen = re.compile(r"'%s':\s*'((?:[^'\\]|\\.)*)'" % re.escape(anahtar))
    degerler = []
    for yol in dosyalar:
        if not yol.exists():
            continue
        for m in desen.finditer(yol.read_text(encoding='utf-8')):
            degerler.append(m.group(1).replace("\\'", "'").replace('\\\\', '\\'))
    return degerler


# ---------------------------------------------------------------------------
# Kurallar
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('kayit', CEVRILECEKLER, ids=_kimlik)
def test_yer_tutucu_ceviri_anahtarina_bagli(kayit):
    """Dil taşıyan her yer tutucu ``data-i18n-placeholder`` taşımalı."""
    assert kayit['anahtar'], (
        '%s: yer tutucu %r çeviri anahtarına BAĞLI DEĞİL — Türkçe arayüzde '
        'İngilizce durur (I18N.apply yalnız data-i18n-placeholder taşıyan '
        'düğümü çevirir, i18n.js:515).' % (_kimlik(kayit), kayit['metin']))


@pytest.mark.parametrize('kayit', CEVRILECEKLER, ids=_kimlik)
def test_anahtar_sayfanin_sozlugunde_iki_dilde_var(kayit):
    """Anahtar, sayfanın yüklediği sözlükte EN+TR olarak bulunmalı."""
    if not kayit['anahtar']:
        pytest.skip('anahtar yok — kardeş bekçi kırmızı verir')
    degerler = _sozluk_degerleri(kayit['anahtar'],
                                 _sayfanin_sozlukleri(kayit['dosya']))
    assert len(degerler) == 2, (
        '%s: %s anahtarı sayfanın sözlüklerinde %d kez geçti (EN+TR için tam '
        '2 beklenir). Eksikse kullanıcı öbür dilin metnini okur.'
        % (_kimlik(kayit), kayit['anahtar'], len(degerler)))


@pytest.mark.parametrize('kayit', CEVRILECEKLER, ids=_kimlik)
def test_sablon_yedegi_EN_sozlukle_ayni(kayit):
    """Şablondaki yedek metin ile EN sözlük girdisi AYRIŞAMAZ.

    Ekrana sözlük çizilir (``I18N.apply``); şablon metni yalnız betik
    çalışmazsa görünür. İkisi ayrışırsa iki ayrı gerçek doğar: birini
    düzeltmek kullanıcıya ulaşmayabilir (bkz. ``test_d33_3_sablon_sozluk``).
    """
    if not kayit['anahtar']:
        pytest.skip('anahtar yok — kardeş bekçi kırmızı verir')
    degerler = _sozluk_degerleri(kayit['anahtar'],
                                 _sayfanin_sozlukleri(kayit['dosya']))
    if len(degerler) != 2:
        pytest.skip('sözlük borcu ayrı bekçinin işi')
    assert degerler[0] == kayit['metin'], (
        '%s: şablon yedeği %r, EN sözlük girdisi %r — AYRIŞIK.'
        % (_kimlik(kayit), kayit['metin'], degerler[0]))


@pytest.mark.parametrize('kayit', KAYITLAR, ids=_kimlik)
def test_alan_genisligi_olculmus(kayit):
    """Fail-closed: ölçülmemiş alan "sığıyor" sayılmaz."""
    anahtar = (kayit['dosya'], kayit['kimlik'])
    assert anahtar in ALAN_GENISLIGI, (
        '%s alanının iç genişliği ÖLÇÜLMEMİŞ. Yeni yer tutucu eklendiyse '
        'tarayıcıda ölçülüp ALAN_GENISLIGI tablosuna yazılmalı: metnin '
        'sığıp sığmadığı tahmin edilemez.' % (_kimlik(kayit),))


@pytest.mark.parametrize('kayit', KAYITLAR, ids=_kimlik)
def test_metin_alana_sigiyor(kayit):
    """EN ve TR metinlerin ikisi de ölçülen alana sığmalı."""
    anahtar_alan = (kayit['dosya'], kayit['kimlik'])
    if anahtar_alan not in ALAN_GENISLIGI:
        pytest.skip('ölçüm borcu ayrı bekçinin işi')
    genislik = ALAN_GENISLIGI[anahtar_alan]
    butce = int(genislik // PIKSEL_KARAKTER)
    if kayit['anahtar']:
        degerler = _sozluk_degerleri(kayit['anahtar'],
                                     _sayfanin_sozlukleri(kayit['dosya']))
        metinler = degerler or [kayit['metin']]
    else:
        metinler = [kayit['metin']]
    for metin in metinler:
        assert len(metin) <= butce, (
            '%s: %r yer tutucusu %d karakter; alan %d piksel, yani en çok %d '
            'karakter alıyor. Ekranda sözcük ortasından kırpılır — metin '
            'kısaltılmalı ve düşen beyan alanın İPUCU metnine taşınmalıdır '
            '(emsal: 954177c6).'
            % (_kimlik(kayit), metin, len(metin), genislik, butce))


# ---------------------------------------------------------------------------
# Betiğin çalışma anında koyduğu yer tutucu (şablon özniteliği yok)
# ---------------------------------------------------------------------------
#: ``traj_burn_time`` alanı kilitlidir; yer tutucusunu ``liquid.html``in
#: kendi betiği ``DOMContentLoaded``da koyar (ÖH D17 / P12bB1-07). Şablon
#: taraması bunu GÖREMEZ, o yüzden ayrıca kurala bağlanır.
BETIK_YER_TUTUCULARI = [
    ('liquid.html', 'traj_burn_time', 'liq.ui.burn_time_placeholder_derived'),
]


@pytest.mark.parametrize('dosya,kimlik,anahtar', BETIK_YER_TUTUCULARI)
def test_betikle_konan_yer_tutucu_sigiyor(dosya, kimlik, anahtar):
    degerler = _sozluk_degerleri(anahtar, _sayfanin_sozlukleri(dosya))
    assert len(degerler) == 2, (
        '%s anahtarı EN+TR olarak bulunamadı (%d)' % (anahtar, len(degerler)))
    genislik = ALAN_GENISLIGI[(dosya, kimlik)]
    butce = int(genislik // PIKSEL_KARAKTER)
    for metin in degerler:
        assert len(metin) <= butce, (
            '%s#%s: %r %d karakter, alan %d piksel (en çok %d karakter).'
            % (dosya, kimlik, metin, len(metin), genislik, butce))
    govde = (SABLONLAR / dosya).read_text(encoding='utf-8')
    assert govde.count("'%s'" % degerler[0]) >= 1, (
        '%s içindeki betik yedeği EN sözlük girdisi %r ile aynı değil'
        % (dosya, degerler[0]))


# ---------------------------------------------------------------------------
# Muafiyet listesinin kendisi ölçülür
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('kayit', MUAFLAR, ids=_kimlik)
def test_muafiyet_gercekten_dilsiz(kayit):
    """Muafiyet kaçış kapısı olmasın: muaf metin harf taşıyamaz."""
    metin = kayit['metin']
    assert not re.search(r'[^\W\d_]', metin, re.UNICODE), (
        '%s: %r muafiyet kapsamında görünüyor ama HARF taşıyor. Muafiyet '
        'yalnız salt sayı örnekleri ve uzun tire içindir; dil taşıyan metin '
        'çeviri anahtarına bağlanmalıdır.' % (_kimlik(kayit), metin))


def test_muafiyet_kumesi_beklenen_boyutta():
    """Muafiyet sessizce büyümesin: sayı değişirse gerekçesi yazılmalı.

    ÖLÇÜLEN (bu dalga): 60 yer tutucunun 17'si muaf — 14 uzun tire ve 3 salt
    sayı örneği (``1``, ``0.78``, ``293.15``). ÖH D36 sökümünden sonra 56 yer
    tutucu: sökülen dördü (simple 1, uzaytek 3) ÇEVRİLECEK sınıftaydı, muaf
    küme 17'de kaldı (tavan değişmedi).
    """
    tire = [k for k in MUAFLAR if k['metin'] == UZUN_TIRE]
    sayi = [k for k in MUAFLAR if SAYI_ORNEGI.match(k['metin'])]
    assert len(tire) + len(sayi) == len(MUAFLAR)
    assert len(MUAFLAR) <= 17, (
        'muafiyet kümesi büyümüş (%d > 17): yeni muafiyet eklenmişse '
        'gerekçesi bu dosyaya yazılmalı' % len(MUAFLAR))
