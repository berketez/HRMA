"""ÖH D37 · piksel-bekci (a1) — OLUŞMUŞ PİKSEL denetimlerinin bekçileri.

Defter OH-D33-45 (yüksek): 16 Eylül'de kılavuz ekran karelerinden üç kusur
çıktı ve tarayıcı iskelesinin hiçbir denetimi görmemişti — (1) yarım çeviri
(anahtar var, Python'un doldurduğu yer tutucunun içeriği İngilizce), (2) aynı
panelde virgül ve nokta ondalık karışık, (3) künye taşması (geometri).

Bu dosya denetimlerin KENDİSİNİ sınar, ürünün bugünkü kusurlarını kilitlemez.
İki katman:

* **Hüküm katmanı** (``denetimler.py``, tarayıcısız): elle kurulmuş ölçüm
  sözlükleriyle her denetim için kusurlu örnek → KIRMIZI, temiz örnek →
  yeşil, muaf örnek → yeşil (ve muafiyet SAYILIR); ölçüm yok/hatalı/kırpılmış
  → fail-closed KIRMIZI.
* **Ölçüm katmanı** (``piksel.py::JS_PIKSEL``, gerçek Chromium): sentetik
  HTML ``page.set_content`` ile yüklenir, ölçüm betiği koşar, hüküm verilir.
  Tarayıcı açılamazsa GEREKÇELİ atlanır (hangi yapıların denendiği yazılır);
  playwright kuruluyken ürün yolu burada yoktur — atlama yalnız ortamın
  tarayıcı ikilisini sorar.

Ters mutasyon kanıtı: ``docs/scofield/raw/OH/D37/piksel-bekci/a1/mutasyon.md``
ve a2 onarım turu için ``…/a2/mutasyon.md`` (her denetimin çekirdeği ve her
a2 onarımı devre dışı bırakıldığında bu dosyanın ilgili düğümleri KIRMIZI,
geri konunca yeşil; denetçinin DM1-DM6'sı dahil).

a2 onarım turu (denetçi bulguları): (a) M=1 ve 'not' listeden çıktı,
(b) dil birimi blok metni, (c) satır içi yedek kırpmayla kesişir, (d) sınır
bekçileri (``TestDilSinirlari``), (e) künye seçicisi tam sınıf adı,
(f) TR noktalı ondalık kırmızı + EN'de ç/ö/ü, (g) her kart ayrı grup ve yol
belirteci harf ister.

a3 (a2 yeniden denetiminin kapsam şartı, ölçüm kodu DEĞİŞMEDİ): denetçinin
yakalanmayan mutasyonları için vakalar — X7 JS kesik birim sayacı (4000'i
aşan birim, kuyrukta İngilizce → FAIL-CLOSED 'KESİLDİ'), X6 EN'de tek küçük
harfli Türkçe sözcük ('Chamber basıncı 3.5 bar' KIRMIZI), X2 satır içi
görünürlük kalıtımı (gizli span yeşil / gizli ebeveynde görünür çocuk
KIRMIZI), X4 birim üst sınırı (tam sınırda ölçülür, bir fazlası kesilir).
Kanıt: ``…/a3/rapor.md``.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import sys

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from tools.browser_harness import denetimler, esikler, piksel, sayfalar, tur  # noqa: E402

JS = KOK / 'hrma' / 'static' / 'js'


# ---------------------------------------------------------------------------
# Yardımcılar — sentetik ölçüm sözlükleri
# ---------------------------------------------------------------------------

def _yaprak(metin, panel='P1 div#panelA', tur_='metin', muaf='', uyari=False,
            secici='div#panelA > p'):
    return {'tur': tur_, 'm': metin, 's': secici, 'p': panel, 'muaf': muaf,
            'u': uyari}


def _olcum(yapraklar=(), dil='tr', **ek):
    o = {'dil': dil, 'html_dil': dil, 'yaprak_sayisi': len(yapraklar),
         'muaf_yaprak_sayisi': sum(1 for y in yapraklar if y.get('muaf')),
         'kirpildi': False, 'metinler': list(yapraklar), 'blok_sayisi': 10,
         'tasmalar': [], 'ebeveyn_asimlari': [],
         'sayfa': {'kaydirma_genisligi': 1440, 'ic_genislik': 1440,
                   'istemci_genislik': 1440, 'fazla_px': 0, 'suclular': [],
                   'suclu_sayisi': 0, 'gizli_suclu_sayisi': 0,
                   'kok_suclular': [], 'kok_suclu_sayisi': 0}}
    o.update(ek)
    return o


def _hukum(denetim_listesi, ad):
    for d in denetim_listesi:
        if d.ad == ad:
            return d
    raise AssertionError('denetim yok: %s' % ad)


#: a3 (denetçi X4/X7): birim üst sınırı vakalarının kurulduğu değer — BİLEREK
#: düz sayı: esikler.PIKSEL_BIRIM_METIN_UST_SINIRI'ndan türetilseydi
#: sabitle birlikte kayar, sabitin değişmesini yakalayamazdı. Eşitliği
#: TestDilSafligiHukmu::test_birim_siniri_canli_sinir_vakalarina_kilitli sınar.
_BIRIM_SINIRI = 4000
_TR_DOLGU = 'Yakıt tankı basınç düşümü ölçüldü ve kayıt altına alındı. '
_INGILIZCE_KUYRUK = ' the value is not set for this run'


def _ilk_imza(d):
    """Kırmızı dil hükmünün ilk imzası; FAIL-CLOSED hükümde kusur listesi
    yoktur — ek sınama KeyError ile bütün canlı tabloyu düşürmesin."""
    return ((d.olcum.get('kusurlar') or [{}])[0].get('imza') or '')


def _uzun_tr(uzunluk, kuyruk=''):
    """Tam ``uzunluk`` karakterlik tek birim metni: Türkçe dolgu + kuyruk.
    JS birimMetni boşlukları teke indirip kırptığı için dolgu boşlukla
    bitmez; ölçülen metnin boyu HTML'dekiyle aynı kalır."""
    n = uzunluk - len(kuyruk)
    govde = (_TR_DOLGU * (n // len(_TR_DOLGU) + 1))[:n]
    if govde.endswith(' '):
        govde = govde[:-1] + '.'
    return govde + kuyruk


# ---------------------------------------------------------------------------
# (a) DİL SAFLIĞI — hüküm katmanı
# ---------------------------------------------------------------------------

class TestDilSafligiHukmu:

    def test_tr_sayfada_ingilizce_yer_tutucu_icerigi_KIRMIZI(self):
        # OH-D33-45 (1): anahtar çevrilmiş, doldurulan içerik İngilizce.
        o = _olcum([_yaprak('Uyarı: HTPB oranı the regression rate is not '
                            'calibrated for this grain')])
        d = denetimler.dil_safligi_denetimi(o, 'tr')
        assert d.gecti is False
        assert d.olcum['kusur_sayisi'] == 1
        assert 'regression rate is not' in d.olcum['kusurlar'][0]['imza']

    def test_tr_temiz_metin_yesil(self):
        o = _olcum([_yaprak('Oda basıncı 20,5 bar; boğaz çapı hesaplandı.'),
                    _yaprak('Motor Tasarımı', secici='h2')])
        d = denetimler.dil_safligi_denetimi(o, 'tr')
        assert d.gecti is True, d.ozet

    @pytest.mark.parametrize('metin', [
        'Not: bu motor kabul testi sonrası yeniden hesaplanmalı',
        'Bu not ile kabul testi yeniden koşulur',
        'NOT: kabul testi yeniden koşulur',
    ])
    def test_turkce_not_sozcugu_imza_degil(self, metin):
        # a2: 'not' Türkçede de sözcüktür ve Türkçe cümlenin ASCII
        # sözcükleriyle ("Not bu motor kabul testi") tek diziye girer; eşik
        # 1'e indiği için işlev listesinden ÇIKARILDI.
        assert 'not' not in esikler.DIL_SAFLIGI_ISLEV_SOZCUKLERI
        o = _olcum([_yaprak(metin)])
        assert denetimler.dil_safligi_denetimi(o, 'tr').gecti is True, metin

    @pytest.mark.parametrize('metin', [
        # Denetçinin G1 örneği: tek işlev sözcüklü üç sözcüklük cümle.
        'Pressure is 3.5 bar',
        # a1 tabanında M=2 eşiğinin KAÇIRDIĞI katı TR 1440 katalog yaprakları
        # (tek işlev sözcüğü: with / for / and).
        'Ammonium perchlorate (NH4ClO4) with burn-rate catalyst',
        'emissivity = sooted/oxidized service surface assumption '
        '(conservative for gas-side radiation absorption',
        'derating and emissivity approximate (typical',
        'Coolant velocity is too high',
    ])
    def test_tek_islev_sozcuklu_ingilizce_cumle_KIRMIZI(self, metin):
        o = _olcum([_yaprak(metin)])
        d = denetimler.dil_safligi_denetimi(o, 'tr')
        assert d.gecti is False, (metin, d.ozet)
        assert len(d.olcum['kusurlar'][0]['islev_sozcukleri']) == 1

    def test_turkce_harfli_sozcuk_diziyi_keser(self):
        # 'the ... is' iki ayrı Türkçe sözcükle bölünmüş: tek dizi değildir.
        diziler = denetimler.ingilizce_diziler('the değer is çıktı to')
        assert diziler == []

    def test_sozcuk_siniri_information_for_icermez(self):
        assert denetimler.ingilizce_diziler('information formation isotope') == []

    def test_muaf_oge_yesil_ve_SAYILIR(self):
        o = _olcum([
            _yaprak('verdict_scope: the chamber is not verified for this run',
                    muaf='kunye'),
            _yaprak('the value is not set for this field', muaf='kod'),
            _yaprak('Oda basıncı 20,5 bar'),
        ])
        d = denetimler.dil_safligi_denetimi(o, 'tr')
        assert d.gecti is True, d.ozet
        assert d.olcum['muaf_yapraklar'] == {'kunye': 1, 'kod': 1}

    def test_makine_belirteci_ayiklanir_ve_sayilir(self):
        # 'time_to_burnout' bölünse 'to' işlev sözcüğü sanılırdı.
        o = _olcum([_yaprak('Alan time_to_burnout ve thrust_curve.sampling.cap_note '
                            'dosyası motor_is_the.stl okunmadı')])
        d = denetimler.dil_safligi_denetimi(o, 'tr')
        assert d.gecti is True, d.ozet
        sayim = d.olcum['ayiklanan_makine_belirtecleri']
        assert sayim.get('tanimlayici', 0) >= 1 and sayim.get('dosya_adi', 0) >= 1

    def test_en_sayfada_turkce_sozcuk_KIRMIZI(self):
        o = _olcum([_yaprak('Flow regime: türbülanslı değil geçiş')], dil='en')
        d = denetimler.dil_safligi_denetimi(o, 'en')
        assert d.gecti is False
        assert 'türbülanslı' in d.olcum['kusurlar'][0]['imza']

    @pytest.mark.parametrize('metin', [
        'Reference: Karabeyoğlu, hybrid regression data',
        # a2 (f): ç/ö/ü de imza harfi; tek, büyük harfli yabancı ad yine muaf.
        'Correlation after Müller, fitted to the test data',
    ])
    def test_en_sayfada_tek_buyuk_harfli_ozel_ad_imza_degil(self, metin):
        o = _olcum([_yaprak(metin)], dil='en')
        assert denetimler.dil_safligi_denetimi(o, 'en').gecti is True

    def test_en_sayfada_tek_kucuk_harfli_turkce_sozcuk_KIRMIZI(self):
        # a3 (denetçi X6): TEK Türkçe harfli sözcük, küçük harfle başlıyor.
        # İmza yalnız turkce_imzasi_var'ın küçük harf yolundan gelebilir —
        # ikinci yol (en az DIL_SAFLIGI_EN_MIN_TURKCE_SOZCUK sözcük) burada
        # tutmaz. Mevcut EN vakalarının hepsi ikinci yoldan yakalandığı için
        # 'if any(s[:1].islower() …)' satırı kapatılınca hepsi yeşil kalıyordu.
        # 'Müller' yeşili (yukarıda) bu kuralın öbür yüzüdür.
        metin = 'Chamber basıncı 3.5 bar'
        assert esikler.DIL_SAFLIGI_EN_MIN_TURKCE_SOZCUK > 1
        assert denetimler.turkce_sozcukler(metin) == ['basıncı']
        assert denetimler.turkce_imzasi_var(['basıncı']) is True
        assert denetimler.turkce_imzasi_var(['Müller']) is False
        d = denetimler.dil_safligi_denetimi(_olcum([_yaprak(metin)], dil='en'), 'en')
        assert d.gecti is False, d.ozet
        assert d.olcum['kusurlar'][0]['imza'] == 'basıncı'

    @pytest.mark.parametrize('metin', [
        # a2 (f) — yalnız ç/ö/ü taşıyan Türkçe (a1 yalnız ı/İ/ş/ğ arıyordu).
        'Output: Güç ölçümü tamam',
        'Chamber: Yüzey sürtünmesi',
    ])
    def test_en_sayfada_yalniz_c_o_u_tasiyan_turkce_KIRMIZI(self, metin):
        o = _olcum([_yaprak(metin)], dil='en')
        d = denetimler.dil_safligi_denetimi(o, 'en')
        assert d.gecti is False, (metin, d.ozet)

    @pytest.mark.parametrize('metin', ['Mode: Özgül itki', 'Status: Çözüm'])
    def test_en_tek_buyuk_harfli_turkce_sozcuk_SINIRI(self, metin):
        # Ölçülmüş SINIR (yabancı ad korumasının bedeli): tek, büyük harfle
        # başlayan Türkçe harfli sözcük imza değildir; 'itki' Türkçe harf
        # taşımaz. Bu cümleler EN sayfada GÖRÜNMEZ (rapor §6).
        o = _olcum([_yaprak(metin)], dil='en')
        assert denetimler.dil_safligi_denetimi(o, 'en').gecti is True

    @pytest.mark.parametrize('bozuk', [
        None, {}, {'hata': 'TypeError: x'},
        _olcum([_yaprak('Oda basıncı')], dil='en'),       # yanlış dil etkin
        _olcum([_yaprak('Oda basıncı')], kirpildi=True),   # kırpılmış
        _olcum([]),                                        # yaprak yok
    ])
    def test_fail_closed(self, bozuk):
        d = denetimler.dil_safligi_denetimi(bozuk, 'tr')
        assert d.gecti is False
        assert 'FAIL-CLOSED' in d.ozet

    def test_kesik_birim_fail_closed(self):
        # a2: birim metni PIKSEL_BIRIM_METIN_UST_SINIRI'nda kesildiyse kuyruk
        # ölçülmemiştir — dil de ondalık da temiz sayılamaz.
        o = _olcum([_yaprak('Oda basıncı')], kesik_birim_sayisi=1)
        for fn in (denetimler.dil_safligi_denetimi,
                   denetimler.ondalik_tutarliligi_denetimi):
            d = fn(o, 'tr')
            assert d.gecti is False and 'KESİLDİ' in d.ozet

    def test_birim_siniri_canli_sinir_vakalarina_kilitli(self):
        # a3 (denetçi X4): canlı sınır vakaları (birim_tam_sinirda_*,
        # birim_siniri_bir_asan_kesilir) _BIRIM_SINIRI değişmezine göre
        # kurulu. Sabitten türetilselerdi sabitle birlikte kayardı ve 4000 →
        # 400 (a1 değeri; ölçülen en uzun birim 1376'nın altında → gerçek
        # sayfada kalıcı sahte FAIL-CLOSED) yakalanmazdı. Sabit değişirse
        # vakalar BİLEREK yeniden kurulur.
        assert esikler.PIKSEL_BIRIM_METIN_UST_SINIRI == _BIRIM_SINIRI
        # Dolgu tek başına dil-temiz ve boyu tam: canlı yeşil beklentisi
        # dolgunun şansına bağlı değil.
        for n in (_BIRIM_SINIRI, _BIRIM_SINIRI + 1):
            assert len(_uzun_tr(n)) == n
            o = _olcum([_yaprak(_uzun_tr(n))])
            assert denetimler.dil_safligi_denetimi(o, 'tr').gecti is True
        kuyruklu = _uzun_tr(_BIRIM_SINIRI, _INGILIZCE_KUYRUK)
        assert len(kuyruklu) == _BIRIM_SINIRI and kuyruklu.endswith(_INGILIZCE_KUYRUK)

    def test_bilinmeyen_dil_fail_closed(self):
        d = denetimler.dil_safligi_denetimi(_olcum([_yaprak('x')], dil='de'), 'de')
        assert d.gecti is False and 'bilinmeyen dil' in d.ozet


class TestDilSinirlari:
    """a2 (d) — eşiklerin TAM sınırı: N = DIL_SAFLIGI_MIN_DIZI_SOZCUK ve
    M = DIL_SAFLIGI_MIN_ISLEV_SOZCUK'un iki yanı. Denetçi mutasyonları
    (DM1: M gevşetilir, DM2: N gevşetilir) bu sınıfı KIRMIZIYA çevirmeli."""

    def _hukum(self, metin):
        return denetimler.dil_safligi_denetimi(_olcum([_yaprak(metin)]), 'tr')

    def test_esikler_bu_sinirlara_gore_yazildi(self):
        # Sınır vakaları sabitlerin BUGÜNKÜ değerine göre kurulu; eşik
        # değişirse vakalar da yeniden kurulmalı (sessiz kayma olmasın).
        assert esikler.DIL_SAFLIGI_MIN_DIZI_SOZCUK == 3
        assert esikler.DIL_SAFLIGI_MIN_ISLEV_SOZCUK == 1

    @pytest.mark.parametrize('metin', ['Pressure is high', 'of the nozzle',
                                       'is set to'])
    def test_tam_N_sozcuk_KIRMIZI(self, metin):
        d = self._hukum(metin)
        assert d.gecti is False, (metin, d.ozet)
        assert d.olcum['kusurlar'][0]['imzalar'] == [metin]

    @pytest.mark.parametrize('metin', ['the nozzle', 'is high', 'of Mach',
                                       # sayı sözcük DEĞİLDİR: 'is' + 'bar' = 2
                                       'Basınç: is 3,5 bar'])
    def test_N_eksi_bir_sozcuk_yesil(self, metin):
        assert self._hukum(metin).gecti is True, metin

    def test_tam_iki_islev_sozcuklu_cumle_KIRMIZI(self):
        d = self._hukum('of the nozzle')
        assert d.gecti is False
        assert d.olcum['kusurlar'][0]['islev_sozcukleri'] == ['of', 'the']

    def test_tam_M_islev_sozcugu_KIRMIZI_M_eksi_bir_yesil(self):
        # M=1: tek işlev sözcüğü imzadır; sıfır işlev sözcüğü imza değildir
        # (ölçülmüş SINIR: işlev sözcüksüz İngilizce etiket kaçar — rapor §6).
        assert self._hukum('Chamber Pressure is Exceeded').gecti is False
        assert self._hukum('Chamber Pressure Exceeds Allowable Stress').gecti is True

    @pytest.mark.parametrize('metin', [
        'Pressure değeri is high',     # Türkçe harfli sözcük böler: 1 + 2 sözcük
        'Pressure · is high',          # künye ayracı böler
        'Pressure | is high',
        'Pressure\nis high',           # birim kesicisi (blok/br) böler
    ])
    def test_bolunmus_dizinin_parcalari_esik_alti_yesil(self, metin):
        assert self._hukum(metin).gecti is True, metin

    def test_sayi_ve_simge_diziyi_bolmez(self):
        # "NOT CONVERGED after 11 rounds to 0.68%" tek dizidir.
        d = self._hukum('Pressure (3.5 bar) is high')
        assert d.gecti is False
        assert d.olcum['kusurlar'][0]['imza'] == 'Pressure (3.5 bar) is high'


# ---------------------------------------------------------------------------
# (b) ONDALIK TUTARLILIĞI — hüküm katmanı
# ---------------------------------------------------------------------------

class TestOndalikTutarliligiHukmu:

    def test_ayni_panelde_iki_ayrac_KIRMIZI(self):
        # OH-D33-43'ün kusuru: her mesaj tek başına kusursuz, kusur ARADA.
        o = _olcum([_yaprak('Tank basıncı 35,5 bar'),
                    _yaprak('Gereken alt sınır: 36.3 bar')])
        d = denetimler.ondalik_tutarliligi_denetimi(o, 'tr')
        assert d.gecti is False
        assert d.olcum['karisik_panel_sayisi'] == 1
        assert d.olcum['yanlis_ayracli_ondalik_sayisi'] == 1

    @pytest.mark.parametrize('yapraklar', [
        # a2 (f) ANA MODEL KARARI: TR sayfada muaf olmayan noktalı ondalık
        # KARIŞIK olmasa da kırmızı — ayrı panellerde…
        [('Tank basıncı 35,5 bar', 'P1 a'), ('Gereken alt sınır: 36.3 bar', 'P2 b')],
        # …panelde tek başına (denetçinin G1 örneği)…
        [('Pressure is 3.5 bar', 'P1 a')],
        # …ya da yalnız noktalı sayılardan oluşan panel (hibrit altı-serbestlik).
        [('CG dolu 1.100 m', 'P1 a'), ('CP 1.416 m', 'P1 a')],
    ])
    def test_tr_noktali_ondalik_karisik_olmasa_da_KIRMIZI(self, yapraklar):
        o = _olcum([_yaprak(m, panel=pn) for m, pn in yapraklar])
        d = denetimler.ondalik_tutarliligi_denetimi(o, 'tr')
        assert d.gecti is False, d.ozet
        assert d.olcum['yanlis_ayrac_kirmizi'] is True
        assert d.olcum['karisik_panel_sayisi'] == 0
        assert 'TR hedefi 0' in d.ozet

    def test_en_virgullu_ondalik_ayri_panellerde_yesil_ama_RAPORLANIR(self):
        # EN yönü ana model kararının DIŞINDA: virgül EN'de binlik ayracıdır.
        o = _olcum([_yaprak('Tank pressure 35.5 bar', panel='P1 a'),
                    _yaprak('Lower bound: 36,3 bar', panel='P2 b')], dil='en')
        d = denetimler.ondalik_tutarliligi_denetimi(o, 'en')
        assert d.gecti is True, d.ozet
        assert d.olcum['yanlis_ayracli_ondalik_sayisi'] == 1
        assert d.olcum['yanlis_ayrac_kirmizi'] is False

    @pytest.mark.parametrize('dil,dis,ic', [
        ('en', 'Tank pressure 35.5 bar', 'Lower bound 36,3 bar'),
        ('tr', 'Tank basıncı 35,5 bar', 'Alt sınır 36.3 bar'),
    ])
    def test_dis_panel_ic_kart_karisimi_KIRMIZI(self, dil, dis, ic):
        # a2 (g): gruplama EN YAKIN panel değil — birim bütün panel/kart
        # atalarına sayılır, her kart ayrı değerlendirilir. Dış panel bir
        # ayraçla, iç kart öbürüyle yazılmışsa DIŞ panel karışıktır.
        o = _olcum([_yaprak(dis, panel='P1 div.panel') | {'pp': ['P1 div.panel']},
                    _yaprak(ic, panel='P2 div.card')
                    | {'pp': ['P2 div.card', 'P1 div.panel']}], dil=dil)
        d = denetimler.ondalik_tutarliligi_denetimi(o, dil)
        assert d.gecti is False, d.ozet
        assert [x['panel'] for x in d.olcum['karisik_paneller']] == ['P1 div.panel']

    def test_ic_ice_kartlar_ayni_ayracla_yesil(self):
        o = _olcum([_yaprak('Pressure 35.5 bar', panel='P1 div.panel')
                    | {'pp': ['P1 div.panel']},
                    _yaprak('Limit 36.3 bar', panel='P2 div.card')
                    | {'pp': ['P2 div.card', 'P1 div.panel']}], dil='en')
        d = denetimler.ondalik_tutarliligi_denetimi(o, 'en')
        assert d.gecti is True, d.ozet
        assert d.olcum['panel_sayisi'] == 2 and d.olcum['ondalik_sayisi']['nokta'] == 2

    def test_egik_cizgili_ondalik_dizisi_yol_sayilmaz(self):
        # a2 (g): a1'in yol deseni sayı parçalarını da yol sayıyordu;
        # '1.5/2.5/3.5' yutulup ölçümden düşüyordu.
        s = denetimler.ondalik_sayilari('Oran 1,5/2,5/3,5 ve Ratio 1.5/2.5/3.5', 'tr')
        assert s['virgul'] == ['1,5', '2,5', '3,5']
        assert s['nokta'] == ['1.5', '2.5', '3.5']
        o = _olcum([_yaprak('Oran 1,5/2,5/3,5'), _yaprak('Ratio 1.5/2.5/3.5')],
                   dil='en')
        assert denetimler.ondalik_tutarliligi_denetimi(o, 'en').gecti is False

    @pytest.mark.parametrize('metin,beklenen', [
        # (docs/… yolu BİLEREK yok: kanıt-atlama tarayıcısı docs dizesini
        # tohum sayar — tests/test_kanit_atlama_kapisi.py)
        ('bkz. api/v1/results', 1), ('hrma/static/js/app', 1),
        ('HTPB/AP/Al karışımı', 1), ('1.5/2.5/3.5', 0), ('1,5/2,5/3,5', 0),
    ])
    def test_yol_belirteci_harf_ister(self, metin, beklenen):
        _, sayim = denetimler.makine_belirteclerini_ayikla(metin)
        assert sayim.get('yol', 0) == beklenen, (metin, sayim)

    def test_yol_belirteci_uzun_metinde_geri_izlemez(self):
        # İç içe yıldızlı harf şartı 8000 karakterde 27 s geri izliyordu.
        import time
        t0 = time.perf_counter()
        denetimler.makine_belirteclerini_ayikla('a' * 4000 + ' ' + '1' * 4000)
        assert time.perf_counter() - t0 < 2.0

    def test_svg_metni_de_panele_girer(self):
        o = _olcum([_yaprak('Isp 222,8 s'),
                    _yaprak('SM 2.10 / 2.77 cal', tur_='svg')])
        assert denetimler.ondalik_tutarliligi_denetimi(o, 'tr').gecti is False

    @pytest.mark.parametrize('metin', [
        'HRMA v2.6.27 ile üretildi, 1,5 bar',
        'Sürüm 2.6.27 · basınç 1,5 bar',
        'Sutton & Biblarz Tablo 8-2, §8.9 ve Eq. 3.12; basınç 1,5 bar',
        'Tarih 23.09.2026, basınç 1,5 bar',
        'Sunucu 127.0.0.1:8191, basınç 1,5 bar',
        'Kaynak https://example.org/v1.2/rapor ve 1,5 bar',
    ])
    def test_muaf_desenler_yesil(self, metin):
        o = _olcum([_yaprak(metin)])
        d = denetimler.ondalik_tutarliligi_denetimi(o, 'tr')
        assert d.gecti is True, (metin, d.ozet)
        assert d.olcum['ondalik_sayisi']['nokta'] == 0

    def test_muaf_oge_ondaliga_girmez(self):
        o = _olcum([_yaprak('Tank basıncı 35,5 bar'),
                    _yaprak('verdict_safety_factor: 0.81', muaf='kunye')])
        d = denetimler.ondalik_tutarliligi_denetimi(o, 'tr')
        assert d.gecti is True, d.ozet
        assert d.olcum['muafiyetler'].get('oge:kunye') == 1

    def test_secili_secenek_etiketi_ondaliga_girmez(self):
        o = _olcum([_yaprak('Tank basıncı 35,5 bar'),
                    _yaprak('Ölçek 1.5x', tur_='secim')])
        assert denetimler.ondalik_tutarliligi_denetimi(o, 'tr').gecti is True

    def test_plotly_binlik_ayracli_tik_belirsiz_sayilir(self):
        # TR separators ',.' ile Plotly 10000'i "10.000" basar.
        o = _olcum([_yaprak('İtki 3,5 kN'),
                    _yaprak('10.000', tur_='svg'), _yaprak('12.500', tur_='svg')])
        d = denetimler.ondalik_tutarliligi_denetimi(o, 'tr')
        assert d.gecti is True, d.ozet
        assert d.olcum['belirsiz_binlik_sayisi'] == 2

    def test_html_metninde_binlik_kabul_edilmez(self):
        # Ürünün kendi biçimi binlik ayracı KULLANMAZ: HTML'deki 10.000 noktalı
        # ondalıktır.
        o = _olcum([_yaprak('İtki 3,5 kN'), _yaprak('Kütle 10.000 kg')])
        assert denetimler.ondalik_tutarliligi_denetimi(o, 'tr').gecti is False

    def test_gruplu_ondalik_ayracini_kendisi_soyler(self):
        s = denetimler.ondalik_sayilari('12.500,5 ve 1,234.5', 'tr', svg=True)
        assert s['virgul'] == ['12.500,5'] and s['nokta'] == ['1,234.5']

    def test_en_binlik_virgul_ondalik_sayilmaz(self):
        o = _olcum([_yaprak('Impulse 12,345 N·s at 3.25 s')], dil='en')
        d = denetimler.ondalik_tutarliligi_denetimi(o, 'en')
        assert d.gecti is True, d.ozet
        assert d.olcum['belirsiz_binlik_sayisi'] == 1

    def test_en_ayni_panelde_iki_ayrac_KIRMIZI(self):
        o = _olcum([_yaprak('Pressure 35.5 bar'), _yaprak('Limit 36,3 bar')],
                   dil='en')
        assert denetimler.ondalik_tutarliligi_denetimi(o, 'en').gecti is False

    def test_oh_d22_02_uyari_basamagi_raporlanir_kapatmaz(self):
        o = _olcum([_yaprak('analiz kendi bulduğu 5,18393 değerini kullanıyor',
                            uyari=True),
                    _yaprak('oran 1,42 ile', uyari=True)])
        d = denetimler.ondalik_tutarliligi_denetimi(o, 'tr')
        assert d.gecti is True
        rapor = d.olcum['oh_d22_02_uyari_basamak']
        assert rapor['sayi'] == 1 and rapor['ornekler'][0]['sayi'] == '5,18393'

    def test_anlamli_basamak(self):
        assert denetimler.anlamli_basamak('0,000123') == 3
        assert denetimler.anlamli_basamak('1,42412') == 6
        assert denetimler.anlamli_basamak('123,000') == 6

    def test_fail_closed(self):
        assert denetimler.ondalik_tutarliligi_denetimi(None, 'tr').gecti is False
        d = denetimler.ondalik_tutarliligi_denetimi(
            _olcum([_yaprak('1,5')], dil='en'), 'tr')
        assert d.gecti is False and 'AÇILMADI' in d.ozet


# ---------------------------------------------------------------------------
# (c) TAŞMA GEOMETRİSİ — hüküm katmanı
# ---------------------------------------------------------------------------

def _tasma(sinif, baslik=False, fazla=40):
    return {'s': 'div.hd-metric-note', 'm': 'minimum_earned_safety_factor',
            'sw': 200 + fazla, 'cw': 200, 'fazla': fazla, 'sinif': sinif,
            'ox': 'visible', 'to': 'clip', 'ws': 'normal', 'baslik': baslik}


class TestTasmaHukmu:

    def test_tasan_kutu_KIRMIZI(self):
        # OH-D33-44: künye çerçeveyi aşıyordu — geometri muafiyet TANIMAZ.
        d = denetimler.oge_tasmasi_denetimi(_olcum(tasmalar=[_tasma('tasan')]))
        assert d.gecti is False and d.olcum['kirmizi_sayisi'] == 1

    def test_basliksiz_kesilen_KIRMIZI_baslikli_yesil(self):
        assert denetimler.oge_tasmasi_denetimi(
            _olcum(tasmalar=[_tasma('kesilen')])).gecti is False
        assert denetimler.oge_tasmasi_denetimi(
            _olcum(tasmalar=[_tasma('kesilen', baslik=True)])).gecti is True

    @pytest.mark.parametrize('sinif', ['kaydirmali', 'erisim_gizli'])
    def test_tasarim_geregi_siniflar_yesil_ama_raporlanir(self, sinif):
        d = denetimler.oge_tasmasi_denetimi(_olcum(tasmalar=[_tasma(sinif)]))
        assert d.gecti is True
        assert d.olcum['siniflar'] == {sinif: 1}

    def test_ebeveyn_asimi_KIRMIZI(self):
        asim = {'s': 'div#vzd1_clock', 'm': 't = 0,00 s', 'ebeveyn': 'div.viz-timeline',
                'fazla': 77, 'yon': 'sag', 'ebeveyn_ox': 'visible', 'sinif': 'tasan',
                'genislik': 150, 'ebeveyn_genislik': 294}
        assert denetimler.ebeveyn_asimi_denetimi(
            _olcum(ebeveyn_asimlari=[asim])).gecti is False
        assert denetimler.ebeveyn_asimi_denetimi(_olcum()).gecti is True

    def test_yatay_kaydirma_KIRMIZI_ve_gizli_suclu_sayilir(self):
        sayfa = {'kaydirma_genisligi': 446, 'ic_genislik': 390,
                 'istemci_genislik': 390, 'fazla_px': 56,
                 'suclular': [{'s': 'span.tooltip-text', 'm': 'ipucu', 'sag': 446,
                               'fazla': 56, 'gizli': True, 'konum': 'absolute'}],
                 'suclu_sayisi': 1, 'gizli_suclu_sayisi': 1,
                 'kok_suclular': [{'s': 'span.tooltip-text', 'm': 'ipucu',
                                   'sag': 446, 'fazla': 56, 'gizli': True,
                                   'konum': 'absolute'}],
                 'kok_suclu_sayisi': 1}
        d = denetimler.yatay_kaydirma_denetimi(_olcum(sayfa=sayfa))
        assert d.gecti is False
        assert 'DV-TOOLTIP' in d.ozet and '[GİZLİ]' in d.ozet

    def test_yatay_kaydirma_tolerans_ANA_TURLA_ayni(self):
        t = esikler.YATAY_TASMA_TOLERANS_PX
        o = _olcum()
        o['sayfa'] = dict(o['sayfa'], fazla_px=t)
        assert denetimler.yatay_kaydirma_denetimi(o).gecti is True
        o['sayfa'] = dict(o['sayfa'], fazla_px=t + 1)
        assert denetimler.yatay_kaydirma_denetimi(o).gecti is False

    @pytest.mark.parametrize('fn', [denetimler.oge_tasmasi_denetimi,
                                    denetimler.ebeveyn_asimi_denetimi,
                                    denetimler.yatay_kaydirma_denetimi])
    @pytest.mark.parametrize('bozuk', [None, {}, {'hata': 'x'}])
    def test_fail_closed(self, fn, bozuk):
        d = fn(bozuk)
        assert d.gecti is False and 'FAIL-CLOSED' in d.ozet


class TestKayitVeSozlesme:

    def test_bes_denetim_sirasi(self):
        adlar = [d.ad for d in denetimler.piksel_denetimleri(_olcum([_yaprak('a')]), 'tr')]
        assert tuple(adlar) == denetimler.PIKSEL_DENETIM_ADLARI

    def test_varsayilan_tur_betikleri_degismedi(self):
        # Piksel ölçümü İSTEĞE BAĞLI kiptir: tur.py'ye JS_* eklenmedi, sahte
        # sayfa ikizinin sözleşmesi (her JS_* için senaryo) bozulmaz.
        assert not [a for a in dir(tur) if a.startswith('JS_') and 'PIKSEL' in a]
        assert 'piksel' not in (KOK / 'tools/browser_harness/tur.py').read_text(
            encoding='utf-8').lower().split('def turu_kos')[1]

    def test_dil_depolama_anahtari_urunde(self):
        kaynak = (JS / 'i18n.js').read_text(encoding='utf-8')
        assert re.search(r"STORAGE_KEY\s*=\s*'%s'" % esikler.URUN_DIL_DEPOLAMA_ANAHTARI,
                         kaynak)

    def test_ekran_basamagi_urunle_ayni(self):
        kaynak = (JS / 'i18n.js').read_text(encoding='utf-8')
        m = re.search(r'YEDEK_SIGFIG\s*=\s*(\d+)', kaynak)
        assert m and int(m.group(1)) == esikler.PIKSEL_EKRAN_ANLAMLI_BASAMAK

    def test_ornek_projeler_depoda(self):
        adlar = {}
        for yol in (KOK / 'examples').glob('*.hrma'):
            veri = json.loads(yol.read_text(encoding='utf-8'))
            adlar[veri.get('name')] = veri.get('motor_type')
        assert set(esikler.PIKSEL_ORNEK_PROJELERI) == set(sayfalar.HESAPLI_SIRA)
        for sayfa, ad in esikler.PIKSEL_ORNEK_PROJELERI.items():
            assert adlar.get(ad) == sayfa, (sayfa, ad)

    def test_muaf_seciciler_urunde_karsilik_buluyor(self):
        # Muafiyet ürünün BUGÜN kullandığı işarete bağlanmalı; ölü seçici
        # listede "muaf" görünüp hiçbir şeyi muaf tutmaz.
        app = (JS / 'app.js').read_text(encoding='utf-8')
        dock = (JS / 'analysis_dock.js').read_text(encoding='utf-8')
        fea = (JS / 'fea_panel.js').read_text(encoding='utf-8')
        assert 'class="hd-verdict-kunye"' in app and 'class="hd-metric-note"' in app
        assert 'data-src-field=' in dock
        assert re.search(r'<details id="fea_basis"', fea)
        adlar = [a for a, _, g in esikler.PIKSEL_MUAF_SECICILER]
        assert len(adlar) == len(set(adlar))
        assert all(g.strip() for _, _, g in esikler.PIKSEL_MUAF_SECICILER)

    def test_muaf_sinif_secicileri_tam_ad_ve_urunde_var(self):
        # a2 (e): sınıf muafiyeti TAM sınıf adına bağlanır. Alt dize seçicisi
        # ([class*=…], [class^=…], [class$=…]) adında o dizgeyi taşıyan HER
        # sınıfı — ileride eklenecek bir cümle kabı dahil — sessizce muaf
        # tutar. Her sınıf adı ürünün kaynağında bir sınıf olarak geçmeli.
        kaynak = '\n'.join(
            y.read_text(encoding='utf-8', errors='replace')
            for kok in ('hrma/static/js', 'hrma/static/css', 'hrma/templates')
            for y in (KOK / kok).rglob('*') if y.suffix in ('.js', '.css', '.html'))
        for ad, secici, _ in esikler.PIKSEL_MUAF_SECICILER:
            assert not re.search(r'\[class\s*[*^$]=', secici), (ad, secici)
            for sinif in re.findall(r'\.([A-Za-z][\w-]*)', secici):
                assert re.search(r'(?<![\w-])%s(?![\w-])' % re.escape(sinif), kaynak), \
                    (ad, sinif)

    def test_sozluk_yarisi_kipi_gercek_dosyayi_hedefliyor(self):
        # Kip ortak sözlüğü bekletir; glob ürünün dosyasına uymazsa kip
        # sessizce hiçbir şeyi geciktirmez ve "yarış yok" yalanı üretir.
        ad = esikler.PIKSEL_GEC_SOZLUK_DESENI.rsplit('/', 1)[-1]
        assert (JS / ad).is_file()
        dock = (JS / 'analysis_dock.js').read_text(encoding='utf-8')
        assert 'ensureCommonDictionary' in dock and ad in dock

    def test_dil_baslangic_betigi_urun_anahtarini_yazar(self):
        betik = piksel.dil_baslangic_betigi('tr')
        assert json.dumps(esikler.URUN_DIL_DEPOLAMA_ANAHTARI) in betik
        assert '"tr"' in betik

    def test_her_muafiyet_gerekceli(self):
        for liste in (esikler.PIKSEL_MUAF_SECICILER,
                      esikler.DIL_SAFLIGI_MAKINE_BELIRTECLERI,
                      esikler.ONDALIK_MUAF_DESENLERI):
            for ad, desen, gerekce in liste:
                assert ad and desen and len(gerekce) > 10, ad


# ---------------------------------------------------------------------------
# Ölçüm katmanı — gerçek Chromium üzerinde sentetik HTML
# ---------------------------------------------------------------------------
# TEK DÜĞÜM, bilerek: CI'da playwright kurulu değil (requirements*.txt ve iş
# akışlarında yok) ve atlama bütçesi (tools/atlama_kapisi.py) her atlanan
# düğümü sayar. Vakalar ayrı düğüm olsaydı tarayıcısız ortamda bütçeye 20
# atlama eklenirdi; tablo tek düğümde koşar, kırmızıda BÜTÜN kalan vakaları
# adıyla yazar.

_ELIPS = 'width:120px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis'

#: (vaka adı, gövde HTML, sayfa dili, denetim, beklenen hüküm, ek sınama)
CANLI_VAKALAR = (
    # --- (a) dil ---------------------------------------------------------
    ('dil_kusurlu', '<div class="panel"><p>Uyarı: the regression rate is not '
     'calibrated for this grain</p></div>', 'tr', 'piksel_dil_safligi', False, None),
    ('dil_temiz', '<div class="panel"><h2>Motor Tasarımı</h2><p>Oda basıncı '
     '20,5 bar</p></div>', 'tr', 'piksel_dil_safligi', True, None),
    ('dil_muaf', '<div class="panel"><p>Oda basıncı</p>'
     '<code>the value is not set for this</code>'
     '<div class="hd-verdict-kunye">verdict_scope: the chamber is not verified</div>'
     '<details id="fea_basis" open><summary>Çözücü künyesi</summary>'
     '<div>as declared by the solver for the run</div></details>'
     '<table><tr><td data-src-field="x">is the source of the</td></tr></table></div>',
     'tr', 'piksel_dil_safligi', True,
     lambda d, o: set(d.olcum['muaf_yapraklar']) == {'kod', 'kunye',
                                                      'cozucu_kunyesi', 'alan_adi'}),
    # a2 (e): adında "kunye" geçen AMA künye olmayan sınıf muaf DEĞİL.
    ('dil_kunye_benzeri_sinif_muaf_degil', '<div class="panel"><div class='
     '"rapor-kunye-kutusu"><p>The regression rate is not calibrated for this '
     'grain</p></div></div>', 'tr', 'piksel_dil_safligi', False,
     lambda d, o: not d.olcum['muaf_yapraklar']),
    ('dil_gorunmeyen_olculmez', '<div class="panel"><p>Oda basıncı</p>'
     '<div style="display:none">this is not visible to the user</div>'
     '<div style="opacity:0">this is not visible to the user</div>'
     '<details><summary>Ayrıntı</summary><p>this is not shown to the user</p>'
     '</details></div>', 'tr', 'piksel_dil_safligi', True,
     lambda d, o: all('user' not in y['m'] for y in o['metinler'])),
    # a2 (b): dil birimi BLOK metni — satır içi etiketler cümleyi bölmez.
    ('dil_satir_ici_etiketle_bolunmus_cumle', '<div class="panel"><p>The pressure '
     '<b>is</b> below <i>the</i> limit</p></div>', 'tr', 'piksel_dil_safligi', False,
     lambda d, o: 'The pressure is below the limit' in [y['m'] for y in o['metinler']]),
    ('dil_bolunmus_parcalar_tek_basina_esik_alti', '<div class="panel"><p>Coolant '
     'velocity <b>is</b> too high</p></div>', 'tr', 'piksel_dil_safligi', False,
     lambda d, o: [y['m'] for y in o['metinler']] == ['Coolant velocity is too high']),
    ('dil_satir_ici_kardesler_tek_birim', '<div class="panel"><div><span>Pressure'
     '</span> <span>is high</span></div></div>', 'tr', 'piksel_dil_safligi', False,
     None),
    ('dil_blok_kardesler_ayri_birim', '<div class="panel"><div>Pressure</div><div>'
     'is high</div></div>', 'tr', 'piksel_dil_safligi', True,
     lambda d, o: sorted(y['m'] for y in o['metinler']) == ['Pressure', 'is high']),
    ('dil_br_birimi_keser', '<div class="panel"><p>Pressure<br>is high</p></div>',
     'tr', 'piksel_dil_safligi', True, None),
    ('dil_birim_icinde_muaf_satir_ici', '<div class="panel"><p>Alan <code>set_to_'
     'the_value</code> için <span class="hd-verdict-kunye">the value is x</span> '
     'değer</p></div>', 'tr', 'piksel_dil_safligi', True,
     lambda d, o: d.olcum['muaf_yapraklar'] == {'kod': 1, 'kunye': 1}),
    # a2 (c): satır içi Range yedeği de KIRPMA dikdörtgeniyle kesiştirilir.
    ('dil_akordeonda_kirpik_satir_ici', '<div class="panel"><p>Basınç</p>'
     '<div style="max-height:0;overflow:hidden"><span>the value is not set for '
     'this</span></div></div>', 'tr', 'piksel_dil_safligi', True,
     lambda d, o: all('value' not in y['m'] for y in o['metinler'])),
    ('dil_akordeonda_kirpik_blok', '<div class="panel"><p>Basınç</p>'
     '<div style="max-height:0;overflow:hidden"><p>the value is not set for '
     'this</p></div></div>', 'tr', 'piksel_dil_safligi', True,
     lambda d, o: all('value' not in y['m'] for y in o['metinler'])),
    ('dil_kaydirmali_kapta_ekran_disi_satir_ici', '<div class="panel"><div style='
     '"width:150px;overflow-x:auto;white-space:nowrap"><span>Basınç</span><span '
     'style="margin-left:600px">the value is not set for this</span></div></div>',
     'tr', 'piksel_dil_safligi', True,
     lambda d, o: all('value' not in y['m'] for y in o['metinler'])),
    ('dil_akordeon_acik_satir_ici_olculur', '<div class="panel"><p>Basınç</p>'
     '<div style="max-height:200px;overflow:hidden"><span>the value is not set '
     'for this</span></div></div>', 'tr', 'piksel_dil_safligi', False, None),
    ('ondalik_akordeonda_kirpik_satir_ici', '<div class="panel"><p>Basınç 3,5 bar'
     '</p><div style="max-height:0;overflow:hidden"><span>Kütle 2.75 kg</span>'
     '</div></div>', 'tr', 'piksel_ondalik_tutarliligi', True,
     lambda d, o: d.olcum['ondalik_sayisi'] == {'virgul': 1, 'nokta': 0}),
    ('dil_svg_metni', '<div class="panel"><svg width="400" height="60"><text x="5" '
     'y="30">the gauges are not a live reading</text></svg></div>', 'tr',
     'piksel_dil_safligi', False, None),
    ('dil_en_sayfada_turkce', '<div class="panel"><p>Flow regime: türbülanslı '
     'değil geçiş</p></div>', 'en', 'piksel_dil_safligi', False, None),
    ('dil_en_sayfada_yalniz_c_o_u_turkce', '<div class="panel"><p>Output: Güç '
     'ölçümü tamam</p></div>', 'en', 'piksel_dil_safligi', False, None),
    # a3 (denetçi X6): tek, KÜÇÜK harfli Türkçe sözcük — yalnız küçük harf
    # yolu yakalar; tek, büyük harfli yabancı ad o yolun öbür yüzü (yeşil).
    ('dil_en_tek_kucuk_harfli_turkce_sozcuk', '<div class="panel"><p>Chamber '
     'basıncı 3.5 bar</p></div>', 'en', 'piksel_dil_safligi', False,
     lambda d, o: _ilk_imza(d) == 'basıncı'),
    ('dil_en_tek_buyuk_harfli_yabanci_ad_yesil', '<div class="panel"><p>Correlation '
     'after Müller, fitted to the test data</p></div>', 'en', 'piksel_dil_safligi',
     True, None),
    # a3 (denetçi X2): satır içi görünürlük KENDİ stilinden okunur, ebeveynin
    # gizli bayrağından kalıtılmaz — visibility:hidden çocuğu görünür yapabilir.
    ('dil_gorunur_blokta_gizli_satir_ici_olculmez', '<div class="panel"><p>Basınç '
     '<span style="visibility:hidden">the value is not set for this</span> '
     'ölçüldü</p></div>', 'tr', 'piksel_dil_safligi', True,
     lambda d, o: [y['m'] for y in o['metinler']] == ['Basınç ölçüldü']),
    ('dil_gizli_blokta_gorunur_cocuk_olculur', '<div class="panel"><p>Oda basıncı'
     '</p><p style="visibility:hidden">Gizli <span style="visibility:visible">the '
     'value is set for this</span></p></div>', 'tr', 'piksel_dil_safligi', False,
     lambda d, o: [y['m'] for y in o['metinler']]
     == ['Oda basıncı', 'the value is set for this']),
    # a3 (denetçi X7/X4): birim üst sınırı. Tam sınırda birim BÜTÜN ölçülür
    # (kuyruk dahil); bir karakter fazlası kesilir ve FAIL-CLOSED — JS
    # sayacı (kesikBirim) artmazsa kesilen kuyruk sessizce temiz sayılırdı
    # (a1'in 400 karakter kesmesinin sakladığı kusur sınıfı).
    ('birim_tam_sinirda_olculur', '<div class="panel"><p>%s</p></div>'
     % _uzun_tr(_BIRIM_SINIRI), 'tr', 'piksel_dil_safligi', True,
     lambda d, o: o.get('kesik_birim_sayisi') == 0
     and [len(y['m']) for y in o['metinler']] == [_BIRIM_SINIRI]),
    ('birim_tam_sinirda_kuyruk_olculur', '<div class="panel"><p>%s</p></div>'
     % _uzun_tr(_BIRIM_SINIRI, _INGILIZCE_KUYRUK), 'tr', 'piksel_dil_safligi', False,
     lambda d, o: o.get('kesik_birim_sayisi') == 0 and 'KESİLDİ' not in d.ozet
     and _INGILIZCE_KUYRUK.strip() in _ilk_imza(d)),
    ('birim_siniri_bir_asan_kesilir', '<div class="panel"><p>%s</p></div>'
     % _uzun_tr(_BIRIM_SINIRI + 1), 'tr', 'piksel_dil_safligi', False,
     lambda d, o: o.get('kesik_birim_sayisi') == 1
     and d.ozet.startswith('FAIL-CLOSED') and 'KESİLDİ' in d.ozet),
    ('birim_siniri_asan_kuyrukta_ingilizce_KESILDI', '<div class="panel"><p>%s</p>'
     '</div>' % _uzun_tr(_BIRIM_SINIRI + 400, _INGILIZCE_KUYRUK), 'tr',
     'piksel_dil_safligi', False,
     lambda d, o: o.get('kesik_birim_sayisi') == 1
     and d.ozet.startswith('FAIL-CLOSED') and 'KESİLDİ' in d.ozet),
    # --- (b) ondalık -----------------------------------------------------
    ('ondalik_karisik', '<div class="panel"><p>Tank basıncı 35,5 bar</p>'
     '<p>Alt sınır 36.3 bar</p></div>', 'tr', 'piksel_ondalik_tutarliligi', False, None),
    # a2 (g): dış panel ⟷ iç kart karışımı (EN: TR'de (f) zaten kırmızı).
    ('ondalik_dis_panel_ic_kart_karisik', '<div class="panel"><p>Tank pressure '
     '35.5 bar</p><div class="card"><p>Lower bound 36,3 bar</p></div></div>', 'en',
     'piksel_ondalik_tutarliligi', False,
     lambda d, o: d.olcum['karisik_panel_sayisi'] == 1
     and d.olcum['karisik_paneller'][0]['panel'].endswith('div.panel')),
    ('ondalik_egik_cizgili_dizi_sayilir', '<div class="panel"><p>Ratio 1.5/2.5/3.5'
     '</p><p>Oran 1,5/2,5/3,5</p></div>', 'en', 'piksel_ondalik_tutarliligi', False,
     lambda d, o: d.olcum['ondalik_sayisi'] == {'virgul': 3, 'nokta': 3}),
    ('ondalik_ayri_paneller_tr_noktali_KIRMIZI', '<div class="panel"><p>Tank basıncı '
     '35,5 bar</p></div><div class="card"><p>Alt sınır 36.3 bar</p></div>', 'tr',
     'piksel_ondalik_tutarliligi', False,
     lambda d, o: d.olcum['karisik_panel_sayisi'] == 0
     and d.olcum['yanlis_ayrac_kirmizi'] is True),
    ('ondalik_ayri_paneller_en_raporlanir', '<div class="panel"><p>Tank pressure '
     '35.5 bar</p></div><div class="card"><p>Lower bound 36,3 bar</p></div>', 'en',
     'piksel_ondalik_tutarliligi', True,
     lambda d, o: d.olcum['yanlis_ayracli_ondalik_sayisi'] == 1),
    ('ondalik_tr_tek_noktali_cumle', '<div class="panel"><p>Pressure is 3.5 bar</p>'
     '</div>', 'tr', 'piksel_ondalik_tutarliligi', False, None),
    ('ondalik_muaf', '<div class="panel"><p>Tank basıncı 35,5 bar</p>'
     '<input type="number" value="3.5"><p>HRMA v2.6.27 · Tablo 8-2 · §8.9</p>'
     '<svg width="200" height="40"><rect x="1.5" y="2.5" width="10" height="10"/>'
     '</svg><span class="hd-metric-note">verdict_safety_factor: 0.81</span></div>',
     'tr', 'piksel_ondalik_tutarliligi', True,
     lambda d, o: d.olcum['ondalik_sayisi'] == {'virgul': 1, 'nokta': 0}),
    # --- (c) taşma -------------------------------------------------------
    ('tasan_kutu', '<div style="width:120px;white-space:nowrap">'
     'minimum_earned_safety_factor: null</div>', 'tr', 'piksel_oge_tasmasi', False,
     lambda d, o: d.olcum['kirmizilar'][0]['sinif'] == 'tasan'),
    ('elips_basliksiz', '<div style="%s">çok uzun bir künye metni burada</div>'
     % _ELIPS, 'tr', 'piksel_oge_tasmasi', False, None),
    ('elips_baslikli', '<div style="%s" title="tam metin">çok uzun bir künye '
     'metni burada</div>' % _ELIPS, 'tr', 'piksel_oge_tasmasi', True, None),
    ('erisim_etiketi_ve_kaydirmali', '<span style="position:absolute;width:1px;'
     'height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap">Yanma '
     'simülasyonu</span><div style="width:120px;overflow-x:auto;white-space:nowrap">'
     'kaydırmalı uzun bir tablo satırı metni</div>', 'tr', 'piksel_oge_tasmasi', True,
     lambda d, o: set(d.olcum['siniflar']) == {'erisim_gizli', 'kaydirmali'}),
    # a2 (c): kırpılmış satır içi metin GEOMETRİ girdisine de girmez (Range
    # yedeği kırpmayla kesişir) — kapalı akordeondaki dar kutu taşma sayılmaz.
    ('tasma_akordeonda_kirpik_satir_ici_olculmez', '<div style="max-height:0;'
     'overflow:hidden"><div style="width:100px;white-space:nowrap"><span>çok uzun '
     'bir satır içi metin burada duruyor</span></div></div>', 'tr',
     'piksel_oge_tasmasi', True, lambda d, o: d.olcum['tasma_sayisi'] == 0),
    ('tasma_akordeon_acik_satir_ici_olculur', '<div style="max-height:200px;'
     'overflow:hidden"><div style="width:100px;white-space:nowrap"><span>çok uzun '
     'bir satır içi metin burada duruyor</span></div></div>', 'tr',
     'piksel_oge_tasmasi', False, None),
    ('temiz_kutu', '<div style="width:300px">kısa bir metin</div>', 'tr',
     'piksel_oge_tasmasi', True, None),
    ('ebeveyn_asimi', '<div style="width:120px"><div style="display:inline-block;'
     'white-space:nowrap">t = 0,00 s / 10,00 s zaman çubuğu</div></div>', 'tr',
     'piksel_ebeveyn_asimi', False,
     lambda d, o: d.olcum['asimlar'][0]['sinif'] == 'tasan'),
    ('ebeveyn_kaydirmali', '<div style="width:120px;overflow-x:auto"><div style='
     '"display:inline-block;white-space:nowrap">uzun uzun bir sekme dizisi</div>'
     '</div>', 'tr', 'piksel_ebeveyn_asimi', True, None),
    ('yatay_kaydirma', '<div style="width:1400px">geniş kutu</div>', 'tr',
     'piksel_yatay_kaydirma', False, lambda d, o: o['sayfa']['kok_suclu_sayisi'] >= 1),
    ('dv_tooltip', '<label>Basınç <span style="position:relative"><span style='
     '"visibility:hidden;position:absolute;left:600px;width:500px">ipucu balonu'
     '</span></span></label>', 'tr', 'piksel_yatay_kaydirma', False,
     lambda d, o: o['sayfa']['gizli_suclu_sayisi'] >= 1),
    ('kirpilan_ve_sabit_kaydirmaz', '<div style="width:200px;overflow:hidden"><div '
     'style="width:3000px">x</div></div><svg width="300" height="40"><text x="10" '
     'y="20">uzun bir svg metni uzun bir svg metni uzun bir svg metni uzun</text>'
     '</svg><div style="position:fixed;left:700px;width:900px">sabit</div>', 'tr',
     'piksel_yatay_kaydirma', True, None),
)


def _sentetik_olcum(baglam, govde, dil):
    p = baglam.new_page()
    try:
        p.set_content('<!doctype html><html lang="%s"><head><meta charset="utf-8">'
                      '<script>window.I18N = {lang: "%s"};</script>'
                      '<style>body{margin:8px;font:14px sans-serif}</style>'
                      '</head><body>%s</body></html>' % (dil, dil, govde))
        return piksel.piksel_olc(p)
    finally:
        p.close()


def test_olcum_katmani_canli_sentetik_vakalar():
    """Her denetim için kusurlu → KIRMIZI, temiz → yeşil, muaf → yeşil —
    ölçüm betiğinin (JS_PIKSEL) gerçek Chromium'daki ölçümüyle."""
    if importlib.util.find_spec('playwright') is None:
        pytest.skip('playwright paketi bu ortamda yok (find_spec): tarayıcı '
                    'katmanı ölçülemez; hüküm katmanı yukarıda koştu')
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        try:
            tarayici, kanal, _ = tur._tarayici_ac(pw, 'auto', False)
        except Exception as hata:
            pytest.skip('Chromium yapısı açılamadı (%s) — denenen: paketli, '
                        'chrome, msedge' % str(hata)[:200])
        kalan = []
        try:
            baglam = tarayici.new_context(viewport={'width': 800, 'height': 600})
            for ad, govde, dil, denetim_adi, beklenen, ek in CANLI_VAKALAR:
                olcum = _sentetik_olcum(baglam, govde, dil)
                if olcum.get('hata'):
                    kalan.append('%s: ölçüm hatası %s' % (ad, olcum['hata'][:200]))
                    continue
                d = _hukum(denetimler.piksel_denetimleri(olcum, dil), denetim_adi)
                if d.gecti is not beklenen:
                    kalan.append('%s: %s beklenen %s, çıkan %s — %s'
                                 % (ad, denetim_adi, beklenen, d.gecti, d.ozet[:200]))
                elif ek is not None and not ek(d, olcum):
                    kalan.append('%s: ek sınama tutmadı — %s' % (ad, d.ozet[:200]))
            # Yanlış dilde açılmış sayfa: fail-closed.
            olcum = _sentetik_olcum(baglam, '<p>Oda basıncı</p>', 'en')
            d = denetimler.dil_safligi_denetimi(olcum, 'tr')
            if d.gecti or 'AÇILMADI' not in d.ozet:
                kalan.append('yanlis_dil_fail_closed: %s' % d.ozet[:200])
        finally:
            tarayici.close()
    assert not kalan, ('%d/%d canlı vaka tutmadı (%s):\n  '
                       % (len(kalan), len(CANLI_VAKALAR) + 1, kanal)
                       + '\n  '.join(kalan))


def test_canli_vaka_tablosu_her_denetimi_iki_yonde_kapsiyor():
    """Tablo çürümesin: her piksel denetimi için en az bir KIRMIZI ve bir
    yeşil beklenen vaka olmalı (tarayıcısız da koşar)."""
    for ad in denetimler.PIKSEL_DENETIM_ADLARI:
        beklenenler = {v[4] for v in CANLI_VAKALAR if v[3] == ad}
        assert beklenenler == {True, False}, (ad, beklenenler)
