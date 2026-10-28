# -*- coding: utf-8 -*-
"""ÖH Dalga-26 · kulvar **arayuz** · aşama **4/4** — bekçiler.

Kapsanan kalemler
-----------------
* **OH-F0-01** (bekçi-kırmızı) — ``/hybrid`` enjektör sonuç bölgesinde iki
  tablo yatayda ÜST ÜSTE biniyordu (değer sütunu komşu tablonun etiket ve
  değerlerinin üstünde).
* **P17B1-19** (bekçi-kırmızı) — aynı sayfa görüntü alanını **282 px** yatay
  aşıyordu.

İkisinin de bekçisi (``denetimler.yerlesim_tasma_denetimi`` /
``yerlesim_ortusme_denetimi``) Faz 0'da YAZILDI ve mutasyonla kanıtlandı
(``tests/test_gorsel_kapi_faz0.py``); **kusur onarılmamıştı**, kalem borç
imiyle duruyordu. Bu dosya borcun ÖDENDİĞİNİ gösterir.

Bekçinin dayanağı: kayıtlı CANLI ÖLÇÜM + KURAL MÜHRÜ
----------------------------------------------------
Yerleşim kusuru ancak gerçek bir tarayıcıda ölçülür; CI'da tarayıcı
açılmaz. Bu yüzden ölçüm bir kez koşulur ve kanıt dizinine yazılır
(``docs/scofield/raw/OH/D26/arayuz/a4/{once,sonra}_canli.json``, üretici
``olcum_canli.py``, sistem Chrome 152, 1600x1000). Kayıtlı sayı tek başına
"bugün de doğru" demez; bu yüzden ölçümle birlikte, sayıyı ÜRETEN CSS
kuralları da mühürlenir. Bekçi mührü **bugünkü** ``advanced.html``e karşı
sınar: kural dosyadan çıkarsa ya da eski hâline dönerse test KIRMIZI olur.

Ayrıca kayıtlı **önce** ölçümü, ürünün KENDİ hüküm katmanından geçirilir ve
KIRMIZI olması iddia edilir: ölçümün ayırt edici olduğu (eşik sonsuza
çekilirse testin kırıldığı) mutasyonla gösterilmiştir
(``a4/mutasyon.json``: ``M8a``, ``M8b``, ``M8c``).
"""

from __future__ import annotations

import json
import pathlib
import sys

import pytest
from tests.support.kanit import kanit_gerekli

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.browser_harness import denetimler, esikler  # noqa: E402

KANIT = ROOT / 'docs/scofield/raw/OH/D26/arayuz/a4'
SABLON = ROOT / 'hrma/templates/advanced.html'
#: v3.0.1 N-girdi-1 (26 Eki 2026): ipucu balonu kuralları üç şablondaki
#: kopyalardan TEK kaynağa (theme.css "Alan ipucu (ortak bileşen)")
#: taşındı; aynı ``scale(0)`` onarımı artık katı ve sıvı sayfasını da
#: kapsar. Balonu üreten kurallar bu yüzden şablon + tema metninde aranır
#: (girinti farkı yok sayılır: şablonda 12, temada 4 boşluk).
TEMA = ROOT / 'hrma/static/css/theme.css'


def _kural_metni():
    return SABLON.read_text(encoding='utf-8') + '\n' + TEMA.read_text(encoding='utf-8')


def _satirlar(metin):
    return '\n'.join(x.strip() for x in metin.splitlines())

#: OH-F0-01'in gövdesi: enjektör tablosunun satır etiketleri. Kalem
#: metninde ölçülen çiftler tam bunlardı ('80.0 mm' ⟂ 'L/D Ratio', …).
ENJEKTOR_ETIKETLERI = (
    'L/D Ratio', 'Discharge Coefficient', 'Injection Area',
    'Weber Number', 'Pressure Drop Basis',
)

#: Enjektör paneli sonuç ızgarasının ÜÇÜNCÜ sütunudur; ölçülen kutusu
#: x 1080..1600 (a4/once_canli.json ``izgara_kutulari``). Bölgeyi etiket
#: metniyle değil KONUMLA tanımlarız: kusur "değer sütunu komşu tablonun
#: üstüne biniyor"dur, hangi satırın denk geldiği çalıştırmaya bağlıdır.
ENJEKTOR_SUTUNU_X = 1080


def _olcum(ad):
    yol = KANIT / ('%s_canli.json' % ad)
    assert kanit_gerekli(yol).exists(), 'kayıtlı canlı ölçüm yok: %s' % yol
    return json.loads(kanit_gerekli(yol).read_text(encoding='utf-8'))


@pytest.fixture(scope='module')
def once():
    return _olcum('once')


@pytest.fixture(scope='module')
def sonra():
    return _olcum('sonra')


class TestOHF001VeP17B119Yerlesim:

    # -- 0. Ölçümün künyesi ------------------------------------------------

    @pytest.mark.parametrize('ad', ['once', 'sonra'])
    def test_olcum_kunyesi_turun_kosullariyla_ayni(self, ad):
        """Kayıtlı sayı ancak turun KOŞULLARINDA alındıysa karşılaştırılır."""
        o = _olcum(ad)
        assert o['sayfa'] == '/hybrid'
        assert o['goruntu_alani'] == dict(esikler.GORUNTU_ALANI), (
            'ölçüm başka bir görüntü alanında alınmış: %r' % o['goruntu_alani'])
        assert o['tarayici']['kanal'] == 'chrome'
        assert o['tarayici']['surum'], 'tarayıcı sürümü kaydedilmemiş'

    # -- 1. ÖNCE: kusur ürünün kendi kapısında KIRMIZI ---------------------

    def test_once_yatay_tasma_kapiyi_kapatiyordu(self, once):
        """P17B1-19'un ölçtüğü 282 px, kayıtta AYNEN duruyor."""
        olcum = once['hesap_sonrasi']
        assert olcum['yatay_tasma_px'] == 282, olcum['yatay_tasma_px']
        assert olcum['belge_genisligi'] == 1882
        hukum = denetimler.yerlesim_tasma_denetimi(olcum)
        assert hukum.gecti is False, hukum.ozet
        assert '282 px' in hukum.ozet

    def test_once_hesap_yapilmadan_da_tasiyordu(self, once):
        """Kalem metninde olmayan ikinci kök: hesapsız sayfa 80 px taşıyordu."""
        olcum = once['hesap_oncesi']
        assert olcum['yatay_tasma_px'] == 80, olcum['yatay_tasma_px']
        assert denetimler.yerlesim_tasma_denetimi(olcum).gecti is False

    def test_once_enjektor_bolgesinde_ortusme_vardi(self, once):
        """OH-F0-01'in gövdesi: enjektör satırlarının üstüne binen değerler."""
        ortusmeler = once['hesap_sonrasi']['ortusmeler']
        assert len(ortusmeler) == esikler.RAPOR_ORNEK_UST_SINIRI, (
            'kayıt rapor tavanında değil: %d' % len(ortusmeler))
        enjektor = [o for o in ortusmeler
                    if (o.get('konum') or [0])[0] >= ENJEKTOR_SUTUNU_X]
        assert len(enjektor) == len(ortusmeler), (
            'kayıtlı örtüşmelerin hepsi enjektör sütununda değil: %d/%d'
            % (len(enjektor), len(ortusmeler)))
        adlar = ' | '.join('%s %s' % (o.get('a'), o.get('b')) for o in ortusmeler)
        for etiket in ENJEKTOR_ETIKETLERI:
            assert etiket in adlar, (
                'kalem metnindeki %r satırı kayıtta yok' % etiket)
        hukum = denetimler.yerlesim_ortusme_denetimi(once['hesap_sonrasi'])
        assert hukum.gecti is False, hukum.ozet

    # -- 2. SONRA: onarım ürünün kendi kapısını açıyor ---------------------

    def test_sonra_yatay_tasma_kapandi(self, sonra):
        """Her iki ölçüm anında da taşma tolerans içinde."""
        for asama in ('hesap_oncesi', 'hesap_sonrasi'):
            olcum = sonra[asama]
            hukum = denetimler.yerlesim_tasma_denetimi(olcum)
            assert hukum.gecti is True, '%s: %s' % (asama, hukum.ozet)
            assert olcum['yatay_tasma_px'] <= esikler.YATAY_TASMA_TOLERANS_PX

    def test_sonra_enjektor_ortusmesi_kalmadi(self, sonra):
        """OH-F0-01 gövdesi kapandı: enjektör satırlarına binen METİN YOK."""
        ortusmeler = sonra['hesap_sonrasi']['ortusmeler']
        kalan = [o for o in ortusmeler
                 if (o.get('konum') or [0])[0] >= ENJEKTOR_SUTUNU_X
                 or any(e in (o.get('a') or '') or e in (o.get('b') or '')
                        for e in ENJEKTOR_ETIKETLERI)]
        assert kalan == [], 'enjektör bölgesinde örtüşme sürüyor: %r' % kalan

    def test_kalan_tek_ortusme_yapiskan_serit_artefaktidir(self):
        """Kalan 1 çift bir YERLEŞİM kusuru değil, ÖLÇÜM artefaktıdır.

        Enjektör örtüşmeleri kapanınca rapor tavanının (25) altında saklı
        kalan tek çift göründü: Analiz Merkezi'nin ``<h2>`` başlığı ⟂
        ``#ac_history_box``. Kutu ``position: sticky; bottom: 8px``tır
        (``analysis_center.css``, bilerek seçilmiş). Tur sayfayı BAŞINDAN
        ölçtüğü için yapışkan kutu kapsayıcısının üstüne KENETLENİYOR ve
        başlığın üstüne düşüyor; panel gerçekten ekrandayken kutu 654 px
        AŞAĞIDA duruyor ve örtüşme YOK.

        Ölçüldü (``sonra_sticky.json``): kaydırılmış ölçümde
        ``ortusmeler == []``. Yani onarımdan sonra ``/hybrid``de GERÇEK
        metin örtüşmesi KALMADI; kalan tek satır turun tarama kuralının
        (position:sticky'yi hesaba katmaması) sonucudur ve altyapı
        kulvarının denetim tarafına aittir.
        """
        d = json.loads((kanit_gerekli(KANIT / 'sonra_sticky.json')).read_text(encoding='utf-8'))
        bas, ekranda = d['sayfa_basinda'], d['panel_ekrandayken']
        assert bas['kutu']['pos'] == 'sticky'
        # Sayfa başındayken kutu başlığın kutusuyla KESİŞİYOR.
        assert bas['kutu']['top'] < bas['h2']['alt'], bas
        # Panel gerçekten ekrandayken kesişme YOK ve kutu çok aşağıda.
        assert ekranda['kutu']['top'] > ekranda['h2']['alt'], ekranda
        assert ekranda['kutu']['top'] - bas['kutu']['top'] > 500, (
            'yapışkan kayma beklenenden küçük: %r' % d)
        # Ve kaydırılmış ölçümde HİÇ örtüşme yok.
        assert d['yerlesim_kaydirilmis']['ortusmeler'] == [], (
            'kaydırılmış ölçümde de örtüşme var: %r'
            % d['yerlesim_kaydirilmis']['ortusmeler'])
        assert denetimler.yerlesim_ortusme_denetimi(
            d['yerlesim_kaydirilmis']).gecti is True

    def test_sonra_tarama_ayni_derinlikte(self, sonra, once):
        """Sayı düşüşü, taramanın DARALMASINDAN gelmiş olamaz.

        Örtüşme 25'ten 1'e indi; bu, ölçümün daha az yaprak taradığı için
        olsaydı kanıt değersiz olurdu. Yaprak sayısı iki koşumda da AYNI.
        """
        assert (sonra['hesap_sonrasi']['yaprak_sayisi']
                == once['hesap_sonrasi']['yaprak_sayisi'] == 800)
        assert sonra['hesap_sonrasi']['kirpildi'] is False

    # -- 3. Sayıyı ÜRETEN kurallar bugünkü dosyada duruyor mu? -------------

    def test_kural_muhru_bugunku_sablonda_duruyor(self, sonra):
        """Kayıtlı ölçüm ancak onu üreten kurallar yerindeyse geçerlidir."""
        metin = _satirlar(_kural_metni())
        muhur = sonra['kural_muhru']
        assert muhur, 'sonra ölçümünde kural mührü yok'
        for ad, kural in muhur.items():
            assert kural is not None, 'mühür ölçüm anında da yoktu: %s' % ad
            assert _satirlar(kural) in metin, (
                'ölçümü üreten kural %s bugünkü advanced.html içinde YOK — '
                'kayıtlı sayı artık bu dosyayı temsil etmiyor' % ad)

    def test_once_muhru_onarim_oncesini_gosteriyor(self, once):
        """Önce ölçümü, kuralların HİÇBİRİ yokken alınmıştı."""
        assert once['kural_muhru'], 'önce ölçümünde mühür alanı yok'
        assert all(v is None for v in once['kural_muhru'].values()), (
            'önce ölçümü onarımdan sonra alınmış görünüyor: %r'
            % once['kural_muhru'])

    def test_ipucu_balonu_gizliyken_gorunur_hale_donebiliyor(self):
        """Onarım balonu ÖLDÜRMEDİ: hover'da geri geliyor (ÖK: kusuru gizleme).

        ``scale(0)`` yalnız gizli hâlde uygulanır; ``:hover`` kuralı
        ``scale(1)`` ile geri alır ve solma süresi korunur.
        """
        metin = _kural_metni()
        # v3.0.1 N-girdi-1: kural tek kaynakta, seçici listesi klavye
        # (``:focus-within``) ve dokunma (``.tip-open``) ile genişledi.
        hover = metin[metin.index('.tooltip:hover .tooltip-text'):]
        hover = hover[:hover.index('}')]
        assert 'transform: scale(1);' in hover, hover
        assert 'visibility: visible;' in hover

    def test_ortusme_gizlenerek_kapatilmadi(self):
        """Kusur çözüldü, SAKLANMADI: panel kırpılmıyor.

        ``overflow: hidden/auto`` konsaydı örtüşme raporda kaybolurdu ama
        kullanıcı yine değeri okuyamazdı; dahası turun ölçümü kırpma
        dikdörtgenini kestiği için kapı KÖRLEŞİRDİ. Onarım bloğu böyle bir
        kural taşımamalı.
        """
        metin = SABLON.read_text(encoding='utf-8')
        blok = metin[metin.index('KÖK B: TASARIM RAPORU TABLOSU'):]
        # ÖH V3 taban-v (14 Eki 2026) — DİLİM SONU ÇEVRİLDİ (iddia DEĞİŞMEDİ).
        # Eski bitiş çapası ``#designReport .report-table td {`` kuralıydı;
        # ÖH D34 piksel turu OH-P-02 (commit 08b10c52) o kuralı söküp yerine
        # ``table-layout: fixed`` + ``td:first-child`` / ``td:last-child``
        # kurallarını koydu ve çapa kalmadı (ValueError). Dilim artık
        # #designReport rapor bölgesinin TAMAMINI (KÖK B onarımı + OH-P-02
        # kuralları) kapsar: sayfanın ondan sonraki ilk kuralı
        # ``.form-group label {`` çapasına kadar. Kapsam DARALMADI, genişledi.
        son = blok.index('.form-group label {')
        assert '#designReport' not in blok[son:son + 200]
        blok = blok[:son]
        assert blok.count('#designReport .report-table') >= 3, (
            'dilim rapor bölgesinin kurallarını taşımıyor (çapa kaydı)')
        for yasak in ('overflow: hidden', 'overflow-x: hidden',
                      'overflow: auto', 'overflow-x: auto'):
            assert yasak not in blok, (
                'örtüşme gizlenerek kapatılmış olabilir: %r' % yasak)
