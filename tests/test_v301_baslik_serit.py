"""v3.0.1 (26 Eki 2026) — üst şerit başlığı menünün üstüne binmez.

Berke'nin ekran görüntüsü (sıvı sayfası): "MOTOR ANALİZİ - Sıvı Çift İticili"
metni "Ana Sayfa" bağlantısının üstüne çiziliyordu, bağlantı iki satıra
kırılmıştı.

ÖLÇÜLDÜ (main a10db67ed, Playwright, Range kutularının kesişimi): üç motor
sayfası, TR ve EN, 1536 px'e kadar her genişlikte başlık menüye biniyordu
(1440'ta 19-66 px, 1280'de 62-226 px, 1024'te 318-482 px). Kök: başlık
KUTUSU daralıyordu (``flex: 0 1 auto; min-width: 0``) ama ``nowrap`` METİN
daralmıyor, kutudan taşıyordu. Düzeltmeden sonra aynı ölçüm 6 sayfa × 8
genişlik × 2 dilde 0 çakışma verdi (kanıt: docs/scofield/raw/OH/V301/
ana-model/baslik-serit/).

Bu bekçi kuralın üç ayağını tutar: başlık daralmaz, menü kalan genişliği alıp
kendi içinde satır kırar, bağlantı metni kırılmaz.
"""
import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
CSS = KOK / 'hrma' / 'static' / 'css' / 'theme.css'


def _kural(metin, secici, baslangic=0):
    m = re.search(re.escape(secici) + r'\s*\{([^}]*)\}', metin[baslangic:])
    assert m, f'{secici!r} kuralı yok'
    return m.group(1)


def _v301_bolumu():
    s = CSS.read_text(encoding='utf-8')
    i = s.find('BAŞLIK MENÜNÜN ÜSTÜNE')
    assert i >= 0, 'v3.0.1 başlık şeridi açıklaması yok'
    return s, i


def test_baslik_daralmaz_metin_kutudan_tasmaz():
    s, i = _v301_bolumu()
    kural = _kural(s, '.navbar h1', i)
    assert re.search(r'flex:\s*0 0 auto', kural), (
        'başlık daralabilir: nowrap metin kutudan taşıp menünün üstüne çizilir', kural)
    assert 'min-width: 0' not in kural, kural
    assert 'white-space: nowrap' in kural, kural


def test_menu_kalan_genisligi_alir_ve_kendi_icinde_kirilir():
    s, i = _v301_bolumu()
    kural = _kural(s, '.navbar .nav-links', i)
    assert re.search(r'flex:\s*1 1 0', kural), kural
    assert 'flex-wrap: wrap' in kural, kural
    assert 'justify-content: flex-end' in kural, kural


def test_baglanti_metni_kirilmaz():
    s, i = _v301_bolumu()
    kural = _kural(s, '.navbar .nav-links a', i)
    assert 'white-space: nowrap' in kural, (
        '"Ana Sayfa" iki satıra kırılıp başlığın yanına taşıyordu', kural)


def test_dar_ekranda_baslik_tam_satir_alir():
    s = CSS.read_text(encoding='utf-8')
    m = re.search(r'@media \(max-width: 768px\)\s*\{(.*?)\n\}', s, re.S)
    assert m, '768 px medya bloğu yok'
    blok = m.group(1)
    assert re.search(r'\.navbar h1\s*\{[^}]*white-space: normal[^}]*flex:\s*1 1 100%', blok), (
        'dar ekranda daralmayan başlık sayfayı yatay taşırır')
