"""``tools/browser_harness/`` — Analiz Merkezi + CFD kiracısı bekçileri.

Neden bu dosya var
------------------
Analiz Merkezi (``analysis_center.js``) ve ilk kiracısı CFD paneli
(``panels/cfd_panel.js``) 16 Ağustos 2026'da ürüne girdi. Parti 21'de FEA
panelleri için kurulan desen buraya genişletildi: panel başına koşum /
çizim / rozet üçlüsü + Merkez'in KENDİ çerçeve denetimi.

Sınanan şey CFD çözümü DEĞİL — iskelenin doğru hüküm verip vermediğidir:

* Ölçüm yoksa hüküm KALIR (sessiz yeşil rapor yasağı).
* Merkez'in kural 1'i ölçülür: kiracısı olmayan satır GİZLENMEZ, gri durur
  ve nedeni ADIYLA yazılır. Nedensiz gri satır kusurdur.
* "Çizim var" üç ölçüte birden bağlıdır: kap görünür + Plotly kabı + içinde
  ``svg``. CFD'de ``svg`` ARANIR (FEA'da svg VEYA canvas kabul edilir);
  gerekçesi ölçülmüştür — panelin üç grafiğinin izleri de SVG üretir.
* Rozet imzaları ürünün SÖZLÜĞÜNE bağlıdır: metin yeniden yazılırsa tur
  sessizce yeşile dönmez, buradaki bekçi kırmızı verir.
* RENK DÜRÜSTLÜĞÜ kuralları: yakınsamayan koşuya kabul rengi, şüpheli
  hükme kabul rengi, eşiği yayımlanmayan sayıya renk YASAK.
* Emekli sözleşme (giriş Mach eşiğine bakan "INLET ADVISORY" rozeti ve
  ``threshold_mach`` alanı) ekranda görünürse tur KALIR.

Hiçbir test bugünkü FİZİĞİ kilitlemez: koşunun yakınsaması, akışın
ayrılması, uyarının ateşlemesi tasarım noktasının fiziğidir. Turun ölçtüğü
şey o beyanların EKRANDA ve DÜRÜST olup olmadığıdır.

Tarayıcı AÇILMAZ: buradaki her girdi elle kurulmuş ölçüm sözlüğüdür ve
sayıları CANLI TURDAN gelir (16 Ağu 2026, üç sayfa, paketli Chromium,
alt süreç sunucusu — raporun ``olcumler.merkez`` bloğu).
"""

from __future__ import annotations

import json
import pathlib
import sys
from typing import Any, Dict, List

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.browser_harness import (  # noqa: E402
    denetimler, esikler, run_tour, sayfalar, tur,
)
from tests.test_browser_harness_fea import sozluk_degerleri  # noqa: E402

#: Merkez çerçevesinin ve kiracısının yaşadığı ürün dosyaları.
MERKEZ_KAYNAGI = 'hrma/static/js/analysis_center.js'
KIRACI_KAYNAGI = 'hrma/static/js/panels/cfd_panel.js'

#: Merkez'i kuran şablonlar (sayfa adı → dosya).
SABLONLAR = {'hybrid': 'hrma/templates/advanced.html',
             'solid': 'hrma/templates/solid.html',
             'liquid': 'hrma/templates/liquid.html'}

#: Turda ölçülen CFD imzaları (yasak olanlar ayrı sınanır).
CFD_IMZALARI = ('cfd_yakinsama_hukmu', 'cfd_yakinsadi', 'cfd_ayrilma_hukmu',
                'cfd_ayrilma_yok', 'cfd_kutle_artigi', 'cfd_enerji_artigi',
                'cfd_cekirdek', 'cfd_sok_sensoru', 'cfd_sinirlayici',
                'cfd_sure', 'cfd_butce_uyarisi', 'cfd_ayrilma_supheli')


def kod_satirlari(metin: str) -> List[str]:
    """Yorumları atar; geriye kod kalır.

    Amaç dar: emekli bir dizgenin kaynakta YORUM olarak (nöbet değişimi
    notu) durması meşrudur, KOD olarak durması değildir. Bu yüzden hem
    ``//`` satır yorumları hem ``/* … */`` blokları düşülür — CFD panelinin
    dosya başı sözleşmesi tek büyük bloktur ve emekli sözleşmeyi orada
    ANLATIR; satır başına bakan naif bir eleme onu kod sanardı.
    """
    kalanlar: List[str] = []
    blokta = False
    for satir in metin.splitlines():
        parca = satir
        if blokta:
            son = parca.find('*/')
            if son < 0:
                continue
            parca = parca[son + 2:]
            blokta = False
        while True:
            bas = parca.find('/*')
            if bas < 0:
                break
            son = parca.find('*/', bas + 2)
            if son < 0:
                parca = parca[:bas]
                blokta = True
                break
            parca = parca[:bas] + parca[son + 2:]
        kirp = parca.strip()
        if kirp.startswith('//'):
            continue
        kalanlar.append(parca)
    return kalanlar


# ---------------------------------------------------------------------------
# Ölçüm kurucuları — CANLI TURUN ölçtüğü sayılar
# ---------------------------------------------------------------------------

def rozet(metin: str, tur_adi: str = 'info') -> Dict[str, Any]:
    return {'tur': tur_adi, 'metin': metin}


def cizim(kimlik: str, **degisiklikler) -> Dict[str, Any]:
    temel = {'kimlik': kimlik, 'gorunur': True, 'plotly_kabi': True,
             'svg_sayisi': 12, 'canvas_sayisi': 0,
             'genislik': 485, 'yukseklik': 300}
    temel.update(degisiklikler)
    return temel


#: Hibrit sayfasının ÇERÇEVE ölçümü (canlı tur): altı satır, biri canlı.
#: 'blocked' satır katı tanesinin düzlemsel FEA'sıdır (hibrit motora
#: uygulanmaz), 'absent' satırlar henüz Merkez'e taşınmamış analizlerdir.
HIBRIT_SATIRLARI = (
    ('chamber_nozzle_wall.structural', 'absent',
     'This analysis has not been moved into the Analysis Center yet; it '
     'still runs in its own panel.'),
    ('chamber_nozzle_wall.thermal', 'absent',
     'This analysis has not been moved into the Analysis Center yet; it '
     'still runs in its own panel.'),
    ('grain_section.planar_grain', 'blocked',
     'This analysis does not apply to a hybrid motor.'),
    ('nozzle_flow.cfd', 'ready', ''),
    ('feed_structure.module_cards', 'absent',
     'This analysis has not been moved into the Analysis Center yet; it '
     'still runs in its own panel.'),
    ('chamber_acoustics.acoustic_modes', 'absent',
     'This analysis has not been moved into the Analysis Center yet; it '
     'still runs in its own panel.'),
)


def cerceve_olcumu(**degisiklikler) -> Dict[str, Any]:
    temel = {
        'panel': esikler.MERKEZ_PANEL_KIMLIGI,
        'panel_var': True, 'panel_gorunur': True,
        'sutunlar': {k: {'mevcut': True, 'gorunur': True}
                     for k in esikler.MERKEZ_SUTUN_KIMLIKLERI},
        'gecmis_var': True, 'api_var': True,
        'motor_metni': 'Motor context: hybrid',
        'satirlar': [{'anahtar': a, 'durum': d, 'neden': n, 'gorunur': True}
                     for a, d, n in HIBRIT_SATIRLARI],
        'satir_sayisi': len(HIBRIT_SATIRLARI),
        'metin': 'Analysis Center Component tree Run card Result viewer',
    }
    temel.update(degisiklikler)
    return temel


#: Hibritte CANLI ölçülen kiracı durumu: koşu 16592 iterasyonda YAKINSADI,
#: ayrılma YOK, bütçe uyarısı ATEŞLEDİ (ölçülen yavaş bant, CR 13,72).
#: "Uyarı hüküm değildir" cümlesinin canlı kanıtı bu satırdır: turuncu
#: uyarı rozeti ile yeşil yakınsama rozeti AYNI ekranda duruyor.
def cfd_olcumu(**degisiklikler) -> Dict[str, Any]:
    rozetler = [
        rozet('CONVERGED — 16592 iterations', 'ok'),
        rozet('NO SEPARATION — the minimum wall pressure is 2.58x the '
              'threshold', 'ok'),
        rozet('ITERATION BUDGET ADVISORY — measured runs near contraction '
              'ratio 13.72 spend most of the budget', 'warn'),
        rozet('MASS IMBALANCE 9.37e-10 (relative)'),
        rozet('ENERGY IMBALANCE 8.42e-10 (relative)'),
        rozet('KERNEL numba'),
        rozet('SHOCK SENSOR — 4 flagged columns'),
        rozet('LIMITER FROZEN at iteration 16250 (1x)'),
        rozet('RUNTIME 10.3 s (solver 10.0 s)', 'dim'),
    ]
    temel = {
        'ad': 'cfd',
        'satir_anahtari': 'nozzle_flow.cfd',
        'satir_secicisi': '#ac_row_nozzle_flow_cfd',
        'satir_durumu': 'ready', 'satir_nedeni': '',
        'kok_var': True, 'kok_gorunur': True,
        'basladi': True, 'asama': 'tamam', 'kosum_s': 10.36,
        'gecmis_esigi': 0, 'gecmis_uzunlugu': 1,
        'zaman_asimi_ms': esikler.MERKEZ_KOSUM_ZAMAN_ASIMI_MS,
        'son_kosum': {'ok': True, 'seconds': 10.3, 'satir': 'nozzle_flow.cfd',
                      'hata': None,
                      'hukum_anahtari': 'panel.cfd.verdictConverged',
                      'hukum_sinifi': 'ok'},
        'yuk': {'converged': True, 'iterations': 16592, 'kernel': 'numba',
                'judgment_confidence': 'firm', 'separated': False,
                'bridge_refused': False, 'budget_advisory': True,
                'budget_advisory_reasons': ['measured_slow_band'],
                'contraction_ratio': 13.721770926966528,
                'alan_bloklu': True, 'kalinti_noktalari': 400,
                'resolution': 'coarse'},
        'cizimler': [cizim('cfd_wall_1'),
                     cizim('cfd_field_1', svg_sayisi=13, yukseklik=320),
                     cizim('cfd_res_1', svg_sayisi=13, yukseklik=260)],
        'cizim_sayisi': 3,
        'rozetler': rozetler,
        'rozet_sayisi': len(rozetler),
        'durum_metni': 'Completed in 10.3 s.',
        'metin': ' '.join(r['metin'] for r in rozetler),
    }
    temel.update(degisiklikler)
    return temel


#: Sıvı sayfasının CANLI ölçümü — AYRI bir fizik dalı: koşu yakınsıyor ama
#: akış AYRILIYOR (%29,1) ve bütçe uyarısı ateşlemiyor. Aynı denetimlerin
#: başka bir tasarım noktasında da yeşil kaldığının kanıtı.
def cfd_olcumu_sivi(**degisiklikler) -> Dict[str, Any]:
    rozetler = [
        rozet('CONVERGED — 2915 iterations', 'ok'),
        rozet('FLOW SEPARATION PREDICTED — 29.1% of the divergent length '
              '(0.100401 m, 17 stations below the threshold)', 'warn'),
        rozet('MASS IMBALANCE 6.89e-11 (relative)'),
        rozet('ENERGY IMBALANCE 8.83e-11 (relative)'),
        rozet('KERNEL numba'),
        rozet('SHOCK SENSOR — 10 flagged columns'),
        rozet('LIMITER NEVER FROZEN'),
        rozet('RUNTIME 1.6 s (solver 1.6 s)', 'dim'),
    ]
    temel = cfd_olcumu(
        kosum_s=1.72,
        son_kosum={'ok': True, 'seconds': 1.7, 'satir': 'nozzle_flow.cfd',
                   'hata': None,
                   'hukum_anahtari': 'panel.cfd.verdictConverged',
                   'hukum_sinifi': 'ok'},
        yuk={'converged': True, 'iterations': 2915, 'kernel': 'numba',
             'judgment_confidence': 'firm', 'separated': True,
             'bridge_refused': False, 'budget_advisory': False,
             'budget_advisory_reasons': [],
             'contraction_ratio': 3.924721598332682,
             'alan_bloklu': True, 'kalinti_noktalari': 400,
             'resolution': 'coarse'},
        rozetler=rozetler, rozet_sayisi=len(rozetler),
        durum_metni='Completed in 1.7 s.',
        metin=' '.join(r['metin'] for r in rozetler))
    temel.update(degisiklikler)
    return temel


def merkez_olcumu(cerceve=None, kiraci=None) -> Dict[str, Any]:
    """Tam Merkez ölçümü — ``tur.py``nin rapora yazdığı yapı.

    ``test_browser_harness_fea.py`` bunu içe aktarır: FEA denetimlerini
    ölçen testler Merkez yüzünden kırmızıya düşmesin diye sağlıklı bir
    Merkez ölçümüyle koşarlar.
    """
    return {'cerceve': cerceve if cerceve is not None else cerceve_olcumu(),
            'kiracilar': {'cfd': kiraci if kiraci is not None else cfd_olcumu()}}


# ---------------------------------------------------------------------------
# 1. Tanımlar ürünle uyumlu mu
# ---------------------------------------------------------------------------

class TestTanimlar:
    """Kimlikler/seçiciler üründe gerçekten var mı? (tarayıcısız)"""

    def test_uc_sayfada_da_merkez_ve_cfd_kiracisi(self):
        for ad in ('hybrid', 'solid', 'liquid'):
            sayfa = sayfalar.SAYFALAR[ad]
            assert sayfa.merkez_var is True, ad
            assert [k.ad for k in sayfa.merkez_kiracilari] == ['cfd'], ad

    def test_merkez_uc_sayfa_sablonunda_kuruluyor(self):
        """Dosya var ama sayfada init edilmiyorsa tur boşa gezer."""
        for ad, yol in SABLONLAR.items():
            metin = (ROOT / yol).read_text(encoding='utf-8')
            assert 'AnalysisCenter.init(' in metin, ad
            assert '/static/js/analysis_center.js' in metin, ad
            assert '/static/js/panels/cfd_panel.js' in metin, ad

    def test_cerceve_kimlikleri_urunde_var(self):
        """Çerçeve kimliği yeniden adlandırılırsa tur körleşir."""
        metin = (ROOT / MERKEZ_KAYNAGI).read_text(encoding='utf-8')
        assert 'id="%s"' % esikler.MERKEZ_PANEL_KIMLIGI in metin
        for kimlik in (esikler.MERKEZ_SUTUN_KIMLIKLERI
                       + (esikler.MERKEZ_GECMIS_KIMLIGI,
                          esikler.MERKEZ_KOSUM_DUGMESI_KIMLIGI,
                          esikler.MERKEZ_DURUM_KIMLIGI,
                          esikler.MERKEZ_GORUNTULEYICI_KOKU)):
            assert "'%s'" % kimlik in metin or 'id="%s"' % kimlik in metin, kimlik
        # Satır düğmesinin kimlik öneki ve durum/neden öznitelikleri
        assert esikler.MERKEZ_SATIR_KIMLIK_ONEKI in metin
        for oznitelik in ('data-ac-row', 'data-ac-state', 'data-ac-reason'):
            assert oznitelik in metin, oznitelik

    def test_satir_secicisi_urunun_kimlik_kuralindan_turuyor(self):
        """``#ac_row_nozzle_flow_cfd`` elle yazılmış bir dize değildir.

        Ürün kuralı: ``ac_row_`` + ``componentId + '_' + analysisId``
        (analysis_center.js ``domKey``). Kiracının kimlikleri de kendi
        SPEC'inde durur; ikisi ayrışırsa tur var olmayan bir satıra
        tıklardı.
        """
        kiraci = (ROOT / KIRACI_KAYNAGI).read_text(encoding='utf-8')
        assert "componentId: 'nozzle_flow'" in kiraci
        assert "analysisId: 'cfd'" in kiraci
        merkez = (ROOT / MERKEZ_KAYNAGI).read_text(encoding='utf-8')
        assert "(componentId + '_' + analysisId).replace(" in merkez
        beklenen = '#%snozzle_flow_cfd' % esikler.MERKEZ_SATIR_KIMLIK_ONEKI
        assert sayfalar.CFD_KIRACISI.satir_secicisi == beklenen
        assert sayfalar.CFD_KIRACISI.satir_anahtari == 'nozzle_flow.cfd'

    def test_cizim_ve_rozet_seciciler_kiraci_kaynaginda_var(self):
        metin = (ROOT / KIRACI_KAYNAGI).read_text(encoding='utf-8')
        assert 'data-cfd-plot' in metin
        assert 'data-cfd-badge' in metin
        for onek in sayfalar.CFD_KIRACISI.cizim_onekleri:
            assert "'%s' + drawSeq" % onek in metin, onek

    def test_kiraci_merkeze_kaydoluyor(self):
        """Kiracı kaydolmazsa satır 'absent' kalır ve koşum hiç başlamaz."""
        metin = (ROOT / KIRACI_KAYNAGI).read_text(encoding='utf-8')
        assert 'AnalysisCenter.register(SPEC)' in metin
        assert "endpoint: ENDPOINT" in metin
        assert "const ENDPOINT = '/api/cfd/nozzle'" in metin

    def test_cozunurluk_varsayilani_coarse(self):
        """Tur alanlara DOKUNMAZ; koşum panelin kendi varsayılanıyla olur.

        'coarse' seçimi süre künyesine bağlıdır (uç ölçümü: en kötü hâl
        10,2/14,9 s). Varsayılan 'standard'a kayarsa tur iki katına çıkar
        ve bu sessizce olmamalı.
        """
        metin = (ROOT / KIRACI_KAYNAGI).read_text(encoding='utf-8')
        assert "['resolution', 'Grid resolution', 'coarse'," in metin

    def test_denetim_adlari_sayfa_icinde_benzersiz(self):
        for sayfa in sayfalar.SAYFALAR.values():
            adlar = [d.ad for d in denetimler.merkez_denetimleri(
                sayfa, merkez_olcumu())]
            for tanim in sayfa.fea_panelleri:
                adlar += [d.ad for d in denetimler.fea_denetimleri(tanim, None)]
            assert len(adlar) == len(set(adlar)), (sayfa.ad, adlar)

    def test_merkezsiz_sayfada_denetim_uretilmez(self):
        """Merkez kurulmayan sayfaya hayalet kırmızı basılmaz."""
        sahte = sayfalar.Sayfa(ad='x', yol='/x', hesapla_secici='button',
                               sonuc_kosulu='() => true')
        assert denetimler.merkez_denetimleri(sahte, {}) == []


# ---------------------------------------------------------------------------
# 2. İmzalar ürünün sözlüğüne bağlı mı
# ---------------------------------------------------------------------------

class TestImzalar:

    @pytest.mark.parametrize('imza', CFD_IMZALARI)
    def test_imza_sozlukteki_her_dilde_geciyor(self, imza):
        tanim = esikler.ROZET_IMZALARI[imza]
        varyantlar = tanim['varyantlar']
        assert varyantlar, imza
        assert tanim['sozluk_anahtarlari'], imza
        for anahtar in tanim['sozluk_anahtarlari']:
            degerler = sozluk_degerleri(anahtar)
            assert len(degerler) >= 2, (
                '%s sözlükte iki dilde bulunmalı, bulunan: %d'
                % (anahtar, len(degerler)))
            for deger in degerler:
                assert any(v in deger for v in varyantlar), (
                    'imza %r, %s karşılığında geçmiyor: %r'
                    % (varyantlar, anahtar, deger))

    @pytest.mark.parametrize('imza', CFD_IMZALARI)
    def test_imza_ingilizce_yedekte_de_geciyor(self, imza):
        """Sözlük yüklenmezse panel YEDEK metni basar; imza orada da olmalı."""
        tanim = esikler.ROZET_IMZALARI[imza]
        assert tanim['kaynak_dosyalar'], imza
        for dosya in tanim['kaynak_dosyalar']:
            metin = (ROOT / dosya).read_text(encoding='utf-8')
            assert any(v in metin for v in tanim['varyantlar']), (imza, dosya)

    def test_dar_yakinsama_imzasi_yakinsamayani_yakalamaz(self):
        """İngilizcede 'NOT CONVERGED' dizesi 'CONVERGED'i İÇERİR.

        Renk kuralı dar imzaya bağlı; negatif bağlam olmadan kural yanlış
        rozete uygulanır ve "yakınsamayan koşu yeşil basılmış" hükmü ASLA
        ateşlemezdi.
        """
        for deger in sozluk_degerleri('panel.cfd.badgeNotConverged'):
            assert not denetimler.imza_eslesen_rozetler([rozet(deger)],
                                                        'cfd_yakinsadi'), deger
            assert denetimler.imza_eslesen_rozetler([rozet(deger)],
                                                    'cfd_yakinsama_hukmu'), deger

    def test_dar_ayrilma_imzasi_koprunun_reddini_yakalamaz(self):
        """'NO SEPARATION JUDGEMENT' bir KABUL değil, hüküm REDDİdir."""
        for deger in sozluk_degerleri('panel.cfd.badgeSepRefused'):
            assert not denetimler.imza_eslesen_rozetler([rozet(deger)],
                                                        'cfd_ayrilma_yok'), deger
            assert denetimler.imza_eslesen_rozetler([rozet(deger)],
                                                    'cfd_ayrilma_hukmu'), deger

    def test_genis_yakinsama_imzasi_iki_dali_da_yakalar(self):
        for anahtar in ('panel.cfd.badgeConverged', 'panel.cfd.badgeNotConverged'):
            for deger in sozluk_degerleri(anahtar):
                assert denetimler.imza_eslesen_rozetler(
                    [rozet(deger)], 'cfd_yakinsama_hukmu'), (anahtar, deger)

    def test_ayrilma_imzasi_dort_dali_da_yakalar(self):
        for anahtar in esikler.ROZET_IMZALARI['cfd_ayrilma_hukmu'][
                'sozluk_anahtarlari']:
            for deger in sozluk_degerleri(anahtar):
                assert denetimler.imza_eslesen_rozetler(
                    [rozet(deger)], 'cfd_ayrilma_hukmu'), (anahtar, deger)

    def test_emekli_giris_uyarisi_anahtarlari_sozlukte_yok(self):
        """Nöbet değişiminin kanıtı: emekli anahtarlar sözlükten kalktı."""
        for anahtar in esikler.ROZET_IMZALARI[
                'cfd_bayat_giris_uyarisi']['eski_anahtarlar']:
            assert sozluk_degerleri(anahtar) == [], anahtar

    @pytest.mark.parametrize('imza', ['cfd_bayat_giris_uyarisi',
                                      'cfd_bayat_mach_esigi'])
    def test_emekli_imza_kaynakta_KOD_olarak_yok(self, imza):
        """Yorumda tarihçe olarak durabilir, kodda duramaz.

        İkisi de ``panels/cfd_panel.js``de nöbet değişimi notu olarak
        geçiyor; kod satırlarında geçmesi emekli sözleşmenin döndüğü
        anlamına gelir.
        """
        kod = '\n'.join(kod_satirlari(
            (ROOT / KIRACI_KAYNAGI).read_text(encoding='utf-8')))
        for varyant in esikler.ROZET_IMZALARI[imza]['varyantlar']:
            assert varyant not in kod, (imza, varyant)

    def test_sayfalarin_kullandigi_imzalar_tabloda_tanimli(self):
        for sayfa in sayfalar.SAYFALAR.values():
            for kiraci in sayfa.merkez_kiracilari:
                imzalar = (tuple(kiraci.beklenen_imzalar)
                           + tuple(kiraci.yasak_imzalar)
                           + tuple(kiraci.notr_imzalar))
                for imza in imzalar:
                    assert denetimler.imza_varyantlari(imza), imza

    def test_notr_imzalar_beklenen_kumesinin_alt_kumesi(self):
        """Renk kuralı ancak EKRANDA ARANAN bir rozete uygulanabilir."""
        k = sayfalar.CFD_KIRACISI
        assert set(k.notr_imzalar) <= set(k.beklenen_imzalar)

    def test_tanimsiz_imza_sessizce_gecmez(self):
        with pytest.raises(KeyError):
            denetimler.imza_haric_varyantlari('boyle_bir_imza_yok')

    def test_metin_taramasi_negatif_baglami_uygular(self):
        """Serbest metin taraması da hariç varyantları saymalı."""
        metin = 'NOT CONVERGED — residual 5.2e-02 after 20000 iterations'
        assert not denetimler.imza_metinde_var(metin, 'cfd_yakinsadi')
        assert denetimler.imza_metinde_var(metin, 'cfd_yakinsama_hukmu')
        assert not denetimler.imza_metinde_var(None, 'cfd_yakinsadi')


# ---------------------------------------------------------------------------
# 3. Çerçeve hükmü
# ---------------------------------------------------------------------------

class TestCerceveDenetimi:

    def _hukum(self, olcum=None, kiracilar=(sayfalar.CFD_KIRACISI,)):
        return denetimler.merkez_cerceve_denetimi(
            cerceve_olcumu() if olcum is None else olcum, kiracilar)

    def test_saglikli_cerceve_gecer(self):
        hukum = self._hukum()
        assert hukum.gecti is True
        assert 'ready×1' in hukum.ozet
        assert 'nozzle_flow.cfd' in hukum.ozet

    def test_olcum_yoksa_kalir(self):
        hukum = denetimler.merkez_cerceve_denetimi(None,
                                                   (sayfalar.CFD_KIRACISI,))
        assert hukum.gecti is False
        assert 'ölçülemedi' in hukum.ozet

    def test_panel_yoksa_kalir(self):
        hukum = self._hukum(cerceve_olcumu(panel_var=False))
        assert hukum.gecti is False
        assert 'sayfada YOK' in hukum.ozet
        assert esikler.MERKEZ_PANEL_KIMLIGI in hukum.ozet

    def test_panel_gorunmuyorsa_kalir(self):
        hukum = self._hukum(cerceve_olcumu(panel_gorunur=False))
        assert hukum.gecti is False
        assert 'GÖRÜNMÜYOR' in hukum.ozet

    def test_sutun_dusunce_kalir(self):
        sutunlar = {k: {'mevcut': True, 'gorunur': True}
                    for k in esikler.MERKEZ_SUTUN_KIMLIKLERI}
        sutunlar['ac_view'] = {'mevcut': True, 'gorunur': False}
        hukum = self._hukum(cerceve_olcumu(sutunlar=sutunlar))
        assert hukum.gecti is False
        assert 'ac_view sütunu ekranda değil' in hukum.ozet

    def test_gecmis_seridi_yoksa_kalir(self):
        hukum = self._hukum(cerceve_olcumu(gecmis_var=False))
        assert hukum.gecti is False
        assert 'koşum geçmişi' in hukum.ozet

    def test_api_yoksa_kalir(self):
        """Koşum kaydı okunamıyorsa hüküm de ölçülemez."""
        hukum = self._hukum(cerceve_olcumu(api_var=False))
        assert hukum.gecti is False
        assert 'history()' in hukum.ozet

    def test_kiraci_satiri_gri_ise_kalir_ve_neden_yazilir(self):
        satirlar = [dict(s) for s in cerceve_olcumu()['satirlar']]
        for s in satirlar:
            if s['anahtar'] == 'nozzle_flow.cfd':
                s['durum'] = 'blocked'
                s['neden'] = ('This result does not carry a nozzle contour, '
                              'so there is nothing to solve on.')
        hukum = self._hukum(cerceve_olcumu(satirlar=satirlar))
        assert hukum.gecti is False
        assert 'CANLI DEĞİL' in hukum.ozet
        assert 'nozzle contour' in hukum.ozet, 'ürünün gerekçesi taşınmalı'

    def test_kiraci_satiri_agacta_yoksa_kalir(self):
        satirlar = [s for s in cerceve_olcumu()['satirlar']
                    if s['anahtar'] != 'nozzle_flow.cfd']
        hukum = self._hukum(cerceve_olcumu(satirlar=satirlar))
        assert hukum.gecti is False
        assert 'ağaçta YOK' in hukum.ozet

    def test_beyansiz_gri_satir_kalir(self):
        """Kural 1: gri satır GİZLENMEZ ama nedeni ADIYLA yazılır."""
        satirlar = [dict(s) for s in cerceve_olcumu()['satirlar']]
        satirlar[0]['neden'] = '   '
        hukum = self._hukum(cerceve_olcumu(satirlar=satirlar))
        assert hukum.gecti is False
        assert 'nedeni yazılmamış' in hukum.ozet
        assert 'chamber_nozzle_wall.structural' in hukum.ozet

    def test_beyansiz_ret_emniyet_agi_ekrandaysa_kalir(self):
        """Çerçevenin kendi "nedenini adlandırmadı" cümlesi görünmemeli."""
        metin = ('Analysis Center The analysis reported that it does not '
                 'apply, but named no reason.')
        hukum = self._hukum(cerceve_olcumu(metin=metin))
        assert hukum.gecti is False
        assert 'beyansız ret' in hukum.ozet

    def test_hic_satir_yoksa_kalir(self):
        hukum = self._hukum(cerceve_olcumu(satirlar=[], satir_sayisi=0))
        assert hukum.gecti is False
        assert 'hiç satır yok' in hukum.ozet

    def test_kiracisiz_merkez_de_denetlenir(self):
        """Kiracısı olmayan bir Merkez de DOĞRU kurulmuş olmalı."""
        hukum = self._hukum(kiracilar=())
        assert hukum.gecti is True


# ---------------------------------------------------------------------------
# 4. Koşum hükmü
# ---------------------------------------------------------------------------

class TestKosumDenetimi:

    def test_saglikli_kosum_gecer(self):
        hukum = denetimler.merkez_kosum_denetimi('cfd', cfd_olcumu())
        assert hukum.gecti is True
        assert '16592 iterasyon' in hukum.ozet
        assert 'numba' in hukum.ozet
        assert hukum.kesinlik == 'dogrudan'

    def test_olcum_yoksa_kalir(self):
        hukum = denetimler.merkez_kosum_denetimi('cfd', None)
        assert hukum.gecti is False
        assert 'ölçülemedi' in hukum.ozet

    def test_satir_hazir_degilse_gerekce_tasinir(self):
        hukum = denetimler.merkez_kosum_denetimi('cfd', cfd_olcumu(
            asama='satir_hazir_degil', satir_durumu='blocked',
            satir_nedeni='No calculation result on this page yet — run the '
                         'motor calculation first.'))
        assert hukum.gecti is False
        assert 'hazır değil' in hukum.ozet
        assert 'run the motor calculation first' in hukum.ozet

    def test_satir_yoksa_secici_yazilir(self):
        hukum = denetimler.merkez_kosum_denetimi('cfd',
                                                 cfd_olcumu(asama='satir_yok'))
        assert hukum.gecti is False
        assert '#ac_row_nozzle_flow_cfd' in hukum.ozet

    def test_kosum_dugmesi_kurulmadiysa_kalir(self):
        hukum = denetimler.merkez_kosum_denetimi('cfd',
                                                 cfd_olcumu(asama='dugme_yok'))
        assert hukum.gecti is False
        assert esikler.MERKEZ_KOSUM_DUGMESI_KIMLIGI in hukum.ozet

    def test_kayit_dusmediyse_kalir(self):
        """Eksik zorunlu alan hâlinde istek HİÇ gönderilmez; durum satırı
        gerekçeyi yazar ve hüküm onu taşır."""
        hukum = denetimler.merkez_kosum_denetimi('cfd', cfd_olcumu(
            son_kosum=None, yuk=None, basladi=False,
            durum_metni='Required fields are empty: Ambient pressure [Pa]. '
                        'The request was NOT sent — a blank field is not a '
                        'value.'))
        assert hukum.gecti is False
        assert 'koşum kaydı YOK' in hukum.ozet
        assert 'NOT sent' in hukum.ozet

    def test_zaman_asimi_ayri_gerekce_yazar(self):
        hukum = denetimler.merkez_kosum_denetimi('cfd', cfd_olcumu(
            asama='zaman_asimi', son_kosum=None, yuk=None))
        assert hukum.gecti is False
        assert 'BİTMEDİ' in hukum.ozet
        assert str(esikler.MERKEZ_KOSUM_ZAMAN_ASIMI_MS) in hukum.ozet

    def test_uc_hata_dondurduyse_gerekce_kopyalanir(self):
        hukum = denetimler.merkez_kosum_denetimi('cfd', cfd_olcumu(
            son_kosum={'ok': False, 'seconds': 0.4, 'satir': 'nozzle_flow.cfd',
                       'hata': 'HTTP 422: nozzle_contour is required; the '
                               'endpoint has no default contour.',
                       'hukum_anahtari': None, 'hukum_sinifi': None},
            yuk=None, rozetler=[], rozet_sayisi=0, cizimler=[], cizim_sayisi=0))
        assert hukum.gecti is False
        assert 'BAŞARISIZ' in hukum.ozet
        assert 'no default contour' in hukum.ozet

    def test_cfd_blogu_yoksa_kalir(self):
        """200 dönen ama çizilecek blok taşımayan yanıt sessizce geçmez."""
        hukum = denetimler.merkez_kosum_denetimi('cfd', cfd_olcumu(yuk=None))
        assert hukum.gecti is False
        assert 'data.cfd yok' in hukum.ozet

    def test_baska_satirin_kaydi_kanit_sayilmaz(self):
        son = dict(cfd_olcumu()['son_kosum'])
        son['satir'] = 'chamber_nozzle_wall.structural'
        hukum = denetimler.merkez_kosum_denetimi('cfd', cfd_olcumu(son_kosum=son))
        assert hukum.gecti is False
        assert 'BAŞKA satıra ait' in hukum.ozet

    def test_hukum_dayanak_beyan_eder(self):
        sozluk = denetimler.merkez_kosum_denetimi('cfd', cfd_olcumu()).sozluk()
        assert 'history()' in sozluk['dayanak']
        assert sozluk['kesinlik'] == 'dogrudan'


# ---------------------------------------------------------------------------
# 5. Çizim hükmü
# ---------------------------------------------------------------------------

ONEKLER = sayfalar.CFD_KIRACISI.cizim_onekleri


class TestCizimDenetimi:

    def test_uc_cizim_ekrandaysa_gecer(self):
        hukum = denetimler.merkez_cizim_denetimi('cfd', cfd_olcumu(), ONEKLER)
        assert hukum.gecti is True
        assert 'cfd_wall_1' in hukum.ozet
        assert 'cfd_field_1' in hukum.ozet
        assert 'cfd_res_1' in hukum.ozet

    def test_kok_yoksa_kalir(self):
        hukum = denetimler.merkez_cizim_denetimi(
            'cfd', cfd_olcumu(kok_var=False, cizimler=[], cizim_sayisi=0),
            ONEKLER)
        assert hukum.gecti is False
        assert esikler.MERKEZ_GORUNTULEYICI_KOKU in hukum.ozet

    def test_eksik_cizim_onekle_adlandirilir(self):
        cizimler = [c for c in cfd_olcumu()['cizimler']
                    if not c['kimlik'].startswith('cfd_res_')]
        hukum = denetimler.merkez_cizim_denetimi(
            'cfd', cfd_olcumu(cizimler=cizimler, cizim_sayisi=2), ONEKLER)
        assert hukum.gecti is False
        assert 'cfd_res_*' in hukum.ozet

    def test_gizli_kap_cizim_sayilmaz(self):
        cizimler = [dict(c) for c in cfd_olcumu()['cizimler']]
        cizimler[1].update({'gorunur': False, 'genislik': 0, 'yukseklik': 0})
        hukum = denetimler.merkez_cizim_denetimi(
            'cfd', cfd_olcumu(cizimler=cizimler), ONEKLER)
        assert hukum.gecti is False
        assert 'kap ekranda değil' in hukum.ozet
        assert str(esikler.MERKEZ_CIZIM_MIN_KENAR_PX) in hukum.ozet

    def test_plotly_disi_kap_kalir(self):
        cizimler = [dict(c) for c in cfd_olcumu()['cizimler']]
        cizimler[0]['plotly_kabi'] = False
        hukum = denetimler.merkez_cizim_denetimi(
            'cfd', cfd_olcumu(cizimler=cizimler), ONEKLER)
        assert hukum.gecti is False
        assert 'Plotly ile çizilmemiş' in hukum.ozet

    def test_svg_yoksa_canvas_kurtarmaz(self):
        """Bu kapıda ölçüt DAR: üç grafiğin izleri de SVG üretir.

        CFD panelinde WebGL'e düşen iz yok (scatter / carpet /
        contourcarpet). Canvas'a düşmüş bir kap, çizimin beklenen yoldan
        çıktığını söyler ve sessizce geçmemelidir.
        """
        cizimler = [dict(c) for c in cfd_olcumu()['cizimler']]
        cizimler[2].update({'svg_sayisi': 0, 'canvas_sayisi': 1})
        hukum = denetimler.merkez_cizim_denetimi(
            'cfd', cfd_olcumu(cizimler=cizimler), ONEKLER)
        assert hukum.gecti is False
        assert 'içinde svg yok' in hukum.ozet
        assert esikler.MERKEZ_CIZIM_SVG_ZORUNLU is True

    def test_olcum_yoksa_kalir(self):
        hukum = denetimler.merkez_cizim_denetimi('cfd', None, ONEKLER)
        assert hukum.gecti is False
        assert 'ölçülemedi' in hukum.ozet


# ---------------------------------------------------------------------------
# 6. Rozet hükmü (beyan + renk dürüstlüğü + koşullu beyan)
# ---------------------------------------------------------------------------

K = sayfalar.CFD_KIRACISI


def rozet_hukmu(olcum):
    return denetimler.merkez_rozet_denetimi(
        'cfd', olcum, K.beklenen_imzalar, K.yasak_imzalar, K.notr_imzalar)


class TestRozetDenetimi:

    def test_saglikli_hibrit_gecer(self):
        hukum = rozet_hukmu(cfd_olcumu())
        assert hukum.gecti is True
        assert 'cfd_yakinsama_hukmu [ok]' in hukum.ozet
        assert 'cfd_sure [dim]' in hukum.ozet

    def test_saglikli_sivi_de_gecer(self):
        """Aynı denetim, BAŞKA fizik: ayrılma var, bütçe uyarısı yok."""
        hukum = rozet_hukmu(cfd_olcumu_sivi())
        assert hukum.gecti is True
        assert 'cfd_ayrilma_hukmu [warn]' in hukum.ozet

    def test_uyari_ile_yakinsama_ayni_ekranda_durabilir(self):
        """"Uyarı hüküm değildir" — canlı ölçümün kilitlendiği yer.

        Hibritte bütçe uyarısı ATEŞLEDİ (turuncu) ve koşu YAKINSADI
        (yeşil). Bir gün biri diğerini bastırırsa bu bekçi kırmızı verir.
        """
        olcum = cfd_olcumu()

        def renk(onek):
            for r in olcum['rozetler']:
                if r['metin'].startswith(onek):
                    return r['tur']
            raise AssertionError('rozet yok: %s' % onek)

        assert renk('CONVERGED') == 'ok'
        assert renk('ITERATION BUDGET ADVISORY') == 'warn'
        assert olcum['yuk']['budget_advisory'] is True
        assert olcum['yuk']['converged'] is True
        assert rozet_hukmu(olcum).gecti is True

    def test_eksik_beyan_kalir_ve_aranani_yazar(self):
        rozetler = [r for r in cfd_olcumu()['rozetler']
                    if 'SHOCK SENSOR' not in r['metin']]
        hukum = rozet_hukmu(cfd_olcumu(rozetler=rozetler,
                                       rozet_sayisi=len(rozetler)))
        assert hukum.gecti is False
        assert 'cfd_sok_sensoru' in hukum.ozet
        assert 'SHOCK SENSOR' in hukum.ozet

    def test_hic_rozet_yoksa_kalir(self):
        hukum = rozet_hukmu(cfd_olcumu(rozetler=[], rozet_sayisi=0, metin=''))
        assert hukum.gecti is False

    @pytest.mark.parametrize('eski_metin', [
        'INLET ADVISORY — the inlet Mach 0.043 is below the measured '
        'threshold 0.15',
    ])
    def test_emekli_giris_uyarisi_rozeti_geri_gelirse_kalir(self, eski_metin):
        rozetler = cfd_olcumu()['rozetler'] + [rozet(eski_metin, 'warn')]
        hukum = rozet_hukmu(cfd_olcumu(rozetler=rozetler,
                                       rozet_sayisi=len(rozetler)))
        assert hukum.gecti is False
        assert 'YASAK imza' in hukum.ozet
        assert 'cfd_bayat_giris_uyarisi' in hukum.ozet

    def test_emekli_alan_adi_panel_metninde_gorunurse_kalir(self):
        """``threshold_mach`` rozette değil, girdi yankısı tablosunda döner."""
        olcum = cfd_olcumu()
        hukum = rozet_hukmu(cfd_olcumu(
            metin=olcum['metin'] + ' threshold_mach 0.15'))
        assert hukum.gecti is False
        assert 'cfd_bayat_mach_esigi → panel metninde' in hukum.ozet

    def test_yakinsamayan_kosuya_kabul_rengi_yasak(self):
        """converged=false iken yakınsama rozeti YEŞİL basılamaz."""
        rozetler = [dict(r) for r in cfd_olcumu()['rozetler']]
        rozetler[0] = rozet('CONVERGED — 20000 iterations', 'ok')
        yuk = dict(cfd_olcumu()['yuk'], converged=False)
        hukum = rozet_hukmu(cfd_olcumu(rozetler=rozetler, yuk=yuk,
                                       metin=' '.join(r['metin'] for r in rozetler)))
        assert hukum.gecti is False
        assert 'RENK DÜRÜSTLÜĞÜ' in hukum.ozet
        assert 'YAKINSAMADI' in hukum.ozet

    def test_yakinsamama_dogru_renkle_basilirsa_gecer(self):
        """Yakınsamamak FİZİKTİR: doğru beyan edildiği sürece kapı açık."""
        rozetler = [dict(r) for r in cfd_olcumu()['rozetler']]
        rozetler[0] = rozet('NOT CONVERGED — residual 5.20e-2 after 20000 '
                            'iterations', 'warn')
        yuk = dict(cfd_olcumu()['yuk'], converged=False)
        hukum = rozet_hukmu(cfd_olcumu(rozetler=rozetler, yuk=yuk,
                                       metin=' '.join(r['metin'] for r in rozetler)))
        assert hukum.gecti is True

    def test_supheli_hukme_kabul_rengi_yasak(self):
        """Oturmamış alana uygulanmış ölçüt "temiz" sayılamaz."""
        rozetler = [dict(r) for r in cfd_olcumu()['rozetler']]
        rozetler.append(rozet('SEPARATION JUDGEMENT SUSPECT — the field it '
                              'was applied to did not settle', 'warn'))
        yuk = dict(cfd_olcumu()['yuk'], judgment_confidence='suspect')
        hukum = rozet_hukmu(cfd_olcumu(rozetler=rozetler, yuk=yuk,
                                       rozet_sayisi=len(rozetler),
                                       metin=' '.join(r['metin'] for r in rozetler)))
        assert hukum.gecti is False
        assert "'suspect'" in hukum.ozet

    def test_supheli_hukum_dim_renkle_gecer(self):
        rozetler = [dict(r) for r in cfd_olcumu()['rozetler']]
        rozetler[1] = rozet('NO SEPARATION — the minimum wall pressure is '
                            '2.58x the threshold', 'dim')
        rozetler.append(rozet('SEPARATION JUDGEMENT SUSPECT — the field it '
                              'was applied to did not settle', 'warn'))
        yuk = dict(cfd_olcumu()['yuk'], judgment_confidence='suspect')
        hukum = rozet_hukmu(cfd_olcumu(rozetler=rozetler, yuk=yuk,
                                       rozet_sayisi=len(rozetler),
                                       metin=' '.join(r['metin'] for r in rozetler)))
        assert hukum.gecti is True

    def test_supheli_etiketi_ekranda_yoksa_kalir(self):
        """Şüphe etiketi yutulursa kullanıcı hükmü temiz sanır."""
        rozetler = [dict(r) for r in cfd_olcumu()['rozetler']]
        rozetler[1] = rozet('NO SEPARATION — the minimum wall pressure is '
                            '2.58x the threshold', 'dim')
        yuk = dict(cfd_olcumu()['yuk'], judgment_confidence='suspect')
        hukum = rozet_hukmu(cfd_olcumu(rozetler=rozetler, yuk=yuk,
                                       metin=' '.join(r['metin'] for r in rozetler)))
        assert hukum.gecti is False
        assert 'şüpheli hüküm etiketi' in hukum.ozet

    def test_butce_uyarisi_atesledi_ama_rozet_yoksa_kalir(self):
        rozetler = [r for r in cfd_olcumu()['rozetler']
                    if 'BUDGET ADVISORY' not in r['metin']]
        hukum = rozet_hukmu(cfd_olcumu(rozetler=rozetler,
                                       rozet_sayisi=len(rozetler),
                                       metin=' '.join(r['metin'] for r in rozetler)))
        assert hukum.gecti is False
        assert 'bütçe uyarısı' in hukum.ozet
        assert 'EKRANDA YOK' in hukum.ozet

    def test_yanitta_olmayan_uyari_ekranda_ise_kalir(self):
        """Beyan yankısı uydurulamaz: rozet uçtan gelmeyen bir şey diyemez."""
        yuk = dict(cfd_olcumu()['yuk'], budget_advisory=False,
                   budget_advisory_reasons=[])
        hukum = rozet_hukmu(cfd_olcumu(yuk=yuk))
        assert hukum.gecti is False
        assert 'yanıtta olmayan bütçe uyarısı' in hukum.ozet

    @pytest.mark.parametrize('renk', ['ok', 'err', 'warn'])
    def test_esiksiz_sayi_renkli_basilirsa_kalir(self, renk):
        """Kütle/enerji artığının yayımlanmış KABUL EŞİĞİ yok."""
        rozetler = [dict(r) for r in cfd_olcumu()['rozetler']]
        for r in rozetler:
            if r['metin'].startswith('MASS IMBALANCE'):
                r['tur'] = renk
        hukum = rozet_hukmu(cfd_olcumu(rozetler=rozetler))
        assert hukum.gecti is False
        assert 'eşiği yayımlanmayan sayı renkli' in hukum.ozet
        assert 'cfd_kutle_artigi' in hukum.ozet

    def test_ekranda_nan_kalir(self):
        olcum = cfd_olcumu()
        hukum = rozet_hukmu(cfd_olcumu(
            metin=olcum['metin'] + ' Minimum wall pressure [Pa] / margin NaN'))
        assert hukum.gecti is False
        assert 'NaN' in hukum.ozet

    def test_kok_yoksa_kalir(self):
        hukum = rozet_hukmu(cfd_olcumu(kok_var=False, rozetler=[],
                                       rozet_sayisi=0, metin=''))
        assert hukum.gecti is False
        assert 'görüntüleyici kabı' in hukum.ozet

    def test_olcum_yoksa_kalir(self):
        hukum = rozet_hukmu(None)
        assert hukum.gecti is False
        assert 'ölçülemedi' in hukum.ozet

    def test_esik_kunyesi_kurallari_tasir(self):
        """Eşik sonradan değişse bile eski rapor doğru yorumlanabilsin."""
        esik = rozet_hukmu(cfd_olcumu()).sozluk()['esik']
        assert esik['notr_siniflar'] == list(esikler.MERKEZ_NOTR_ROZET_SINIFLARI)
        assert esik['kabul_sinifi'] == esikler.MERKEZ_KABUL_ROZET_SINIFI
        assert 'cfd_yakinsadi' in esik['imza_varyantlari']
        assert 'cfd_ayrilma_supheli' in esik['imza_varyantlari']


# ---------------------------------------------------------------------------
# 7. Dörtlü hüküm ve tur akışına bağlanma
# ---------------------------------------------------------------------------

class TestAkisaBaglanma:

    def _gezgin(self, sayfa_adi: str):
        # Tarayıcı nesnesi None: ``_rapor`` sayfaya DOKUNMAZ.
        return tur.SayfaGezgini(None, 'http://127.0.0.1:1',
                                sayfalar.SAYFALAR[sayfa_adi], '/tmp')

    def _tam_rapor(self, sayfa_adi: str, fea, merkez):
        gezgin = self._gezgin(sayfa_adi)
        return gezgin._rapor(
            sureler={'yukleme_s': 0.7, 'hesap_s': 3.1},
            viz={'erisim': 'motorviz3d', 'cizim_araligi': 900,
                 'plume_bilgisi_var': True, 'oynatiliyor': True,
                 'plume_acik': True, 'partikul_tavani': 900},
            tuval_ham={'kaynak': 'MotorViz3D.snapshot()'},
            piksel={'dolu_oran': 0.41, 'icerik_entropi_bit': 3.42,
                    'parlak_oran': 0.01},
            metin='Chamber Pressure 20.0 bar', plume_baslatma='ui',
            goruntuler={'tam_sayfa': None, 'uc_boyut': None},
            fea=fea, merkez=merkez)

    def test_merkez_dortlusu_her_sayfada_ayni_sirada(self):
        from tests.test_browser_harness_fea import (tane_olcum, termal_olcum,
                                                    yapisal_olcum)
        beklenen = ['merkez_cerceve', 'merkez_cfd_kosum', 'merkez_cfd_cizim',
                    'merkez_cfd_rozet']
        for sayfa_adi, fea in (('hybrid', {'yapisal': yapisal_olcum(),
                                           'termal': termal_olcum()}),
                               ('solid', {'tane': tane_olcum()}),
                               ('liquid', {'yapisal': yapisal_olcum()})):
            rapor = self._tam_rapor(sayfa_adi, fea, merkez_olcumu())
            adlar = [d['ad'] for d in rapor['denetimler']]
            assert adlar[-4:] == beklenen, sayfa_adi
            assert rapor['gecti'] is True, sayfa_adi

    def test_sayfa_basina_denetim_sayisi(self):
        """CANLI TURUN ölçtüğü sayı: 15 + 12 + 12 = 39.

        Sayı bir hedef değil, sözleşmenin toplamıdır: 5 temel + FEA
        paneli başına 3 + Merkez çerçevesi 1 + kiracı başına 3. Bir
        denetim sessizce düşerse burada görünür.
        """
        from tests.test_browser_harness_fea import (tane_olcum, termal_olcum,
                                                    yapisal_olcum)
        beklenen = {'hybrid': 15, 'solid': 12, 'liquid': 12}
        fealer = {'hybrid': {'yapisal': yapisal_olcum(),
                             'termal': termal_olcum()},
                  'solid': {'tane': tane_olcum()},
                  'liquid': {'yapisal': yapisal_olcum()}}
        toplam = 0
        for sayfa_adi, sayi in beklenen.items():
            rapor = self._tam_rapor(sayfa_adi, fealer[sayfa_adi],
                                    merkez_olcumu())
            assert len(rapor['denetimler']) == sayi, sayfa_adi
            toplam += len(rapor['denetimler'])
        assert toplam == 39

    def test_merkez_olcumu_kalirsa_sayfa_kalir(self):
        """Merkez denetimi ESKİ denetimlerle aynı ağırlıkta."""
        from tests.test_browser_harness_fea import yapisal_olcum
        rapor = self._tam_rapor('liquid', {'yapisal': yapisal_olcum()},
                                merkez_olcumu(kiraci=cfd_olcumu(yuk=None)))
        assert rapor['gecti'] is False
        kalanlar = [d['ad'] for d in rapor['denetimler'] if not d['gecti']]
        assert kalanlar == ['merkez_cfd_kosum']

    def test_merkez_hic_olculmediyse_dordu_de_kalir(self):
        from tests.test_browser_harness_fea import yapisal_olcum
        rapor = self._tam_rapor('liquid', {'yapisal': yapisal_olcum()}, {})
        kalanlar = [d['ad'] for d in rapor['denetimler'] if not d['gecti']]
        assert kalanlar == ['merkez_cerceve', 'merkez_cfd_kosum',
                            'merkez_cfd_cizim', 'merkez_cfd_rozet']

    def test_merkez_olcumu_rapora_yazilir(self):
        from tests.test_browser_harness_fea import tane_olcum
        rapor = self._tam_rapor('solid', {'tane': tane_olcum()},
                                merkez_olcumu())
        merkez = rapor['olcumler']['merkez']
        assert merkez['kiracilar']['cfd']['rozet_sayisi'] == 9
        assert merkez['cerceve']['satir_sayisi'] == 6
        assert json.dumps(rapor, ensure_ascii=False)

    def test_yapilandirma_sozlukleri_tanimdan_uretilir(self):
        gezgin = self._gezgin('hybrid')
        assert gezgin._merkez_yapilandirmasi() == {
            'panel': esikler.MERKEZ_PANEL_KIMLIGI,
            'sutunlar': list(esikler.MERKEZ_SUTUN_KIMLIKLERI),
            'gecmis': esikler.MERKEZ_GECMIS_KIMLIGI,
            'dugme': esikler.MERKEZ_KOSUM_DUGMESI_KIMLIGI,
            'durum': esikler.MERKEZ_DURUM_KIMLIGI}
        assert gezgin._merkez_kiraci_yapilandirmasi(sayfalar.CFD_KIRACISI) == {
            'kok': esikler.MERKEZ_GORUNTULEYICI_KOKU,
            'cizim_secici': '[data-cfd-plot]',
            'rozet_secici': '[data-cfd-badge]',
            'rozet_ozniteligi': 'data-cfd-badge',
            'dugme': esikler.MERKEZ_KOSUM_DUGMESI_KIMLIGI,
            'durum': esikler.MERKEZ_DURUM_KIMLIGI,
            'min_kenar': esikler.MERKEZ_CIZIM_MIN_KENAR_PX}

    def test_esik_kunyesi_merkez_esiklerini_tasir(self):
        kunye = run_tour.esik_kunyesi()
        assert kunye['MERKEZ_KOSUM_ZAMAN_ASIMI_MS'] == \
            esikler.MERKEZ_KOSUM_ZAMAN_ASIMI_MS
        assert kunye['MERKEZ_NOTR_ROZET_SINIFLARI'] == \
            list(esikler.MERKEZ_NOTR_ROZET_SINIFLARI)
        assert 'cfd_yakinsadi' in kunye['ROZET_IMZALARI']
        assert json.dumps(kunye, ensure_ascii=False)

    def test_kunye_on_bir_soruyu_sayar(self):
        """run_tour künyesi turun kaç soru sorduğunu söyler; ayrışmasın."""
        belge = run_tour.__doc__ or ''
        assert 'on bir soruyu' in belge
        for numara in range(1, 12):
            assert '\n%2d.' % numara in belge, numara

    def test_cizim_esigi_fea_ile_ayni_kaynaktan(self):
        """Aynı kavram iki sayıyla tanımlanmaz (parametre tutarlılığı)."""
        assert esikler.MERKEZ_CIZIM_MIN_KENAR_PX is esikler.FEA_CIZIM_MIN_KENAR_PX
        assert esikler.MERKEZ_KOSUM_BASLAMA_ZAMAN_ASIMI_MS is \
            esikler.FEA_BASLAMA_ZAMAN_ASIMI_MS


# ---------------------------------------------------------------------------
# 8. Ölçüm betikleri
# ---------------------------------------------------------------------------

class TestOlcumBetikleri:

    def test_cerceve_betigi_oznitelikleri_okur(self):
        """Durum METİNLE değil ÖZNİTELİKLE okunur (arayüz çevrilebilir)."""
        for parca in ('data-ac-row', 'data-ac-state', 'data-ac-reason',
                      'getBoundingClientRect', 'getComputedStyle'):
            assert parca in tur.JS_MERKEZ_CERCEVE, parca

    def test_mesgul_betigi_metne_bakmaz(self):
        assert 'disabled' in tur.JS_MERKEZ_MESGUL
        assert 'textContent' not in tur.JS_MERKEZ_MESGUL

    def test_bitis_betigi_iki_cikisi_da_taniyor(self):
        """(1) geçmişe kayıt düştü, (2) istek hiç gönderilmedi.

        İkincisi olmasaydı boş alanlı bir kart turu zaman aşımına kadar
        bekletirdi ve kusur "takıldı" diye görünürdü.
        """
        assert 'history().length > c.gecmis_esigi' in tur.JS_MERKEZ_KOSUM_BITTI
        assert '!b.disabled' in tur.JS_MERKEZ_KOSUM_BITTI

    def test_kiraci_betigi_dogrudan_dayanaklari_okur(self):
        for parca in ('AnalysisCenter', 'history()', 'son.data.cfd',
                      'js-plotly-plot', "querySelectorAll('svg')",
                      'judgment_confidence', 'budget_advisory'):
            assert parca in tur.JS_MERKEZ_KIRACI, parca

    def test_kiraci_betigi_hesap_yapmaz(self):
        """Ölçüm betiği YALNIZ okur: türetilmiş sayı üretmez."""
        for yasak in ('Math.random', 'setTimeout', 'setInterval',
                      'toFixed', 'parseFloat'):
            assert yasak not in tur.JS_MERKEZ_KIRACI, yasak
