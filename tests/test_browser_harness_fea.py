"""``tools/browser_harness/`` — FEA panellerinin denetim bekçileri.

Neden bu dosya var
------------------
FEA ürün turu bugün ELLE yapıldı: üç panel (hibrit yapısal, hibrit termal,
katı tane kesiti) tarayıcıda açılıp koşturuldu, çizimler ve rozetler gözle
doğrulandı. Elle yapılan denetim bir kez doğrular; kalıcı bekçi her sürümde
doğrular. Bu dosya, o kalıcı bekçinin KENDİSİNİ sınar.

Sınanan şey uygulamanın FEA çözümü DEĞİL — iskelenin doğru hüküm verip
vermediğidir:

* Ölçüm yoksa hüküm KALIR (sessiz yeşil rapor yasağı).
* "Çizim var" üç ölçüte birden bağlıdır: kap görünür + Plotly kabı +
  içinde svg/canvas düğümü. Biri eksikse KALIR.
* Rozet imzaları ürünün SÖZLÜĞÜNE bağlıdır: metin yeniden yazılırsa tur
  sessizce yeşile dönmez, buradaki bekçi kırmızı verir.
* Eski birleşik kalite alarmı ("outside the acceptable range") ekranda
  yeniden görünürse tur KALIR.

Hiçbir test uygulamanın bugünkü FİZİK sonucunu kilitlemez: yakınsama,
emniyet katsayısı, sıcaklık gibi büyüklükler tasarım noktasının fiziğidir.
Rozetin RENGİ de bu yüzden hükme girmez, yalnız rapora yazılır.

Tarayıcı AÇILMAZ: buradaki her girdi elle kurulmuş ölçüm sözlüğüdür.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
from typing import Any, Dict, List

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.browser_harness import (  # noqa: E402
    denetimler, esikler, run_tour, sayfalar, tur,
)

#: Sözlük değerini yakalayan desen: ``'anahtar': 'değer',`` — kaçışlı
#: tırnak taşıyan değerler de tek parça okunur.
_DEGER_DESENI = r"'((?:[^'\\]|\\.)*)'"

#: Anahtarların yaşadığı sözlük dosyaları (ikisi de taranır: ``fea.*`` ve
#: ``feaT.*`` ortak sözlükte, ``solid.fea.*`` sayfa sözlüğünde).
SOZLUK_DOSYALARI = ('hrma/static/js/i18n_common.js',
                    'hrma/static/js/i18n_pages.js')


def sozluk_degerleri(anahtar: str) -> List[str]:
    """Bir anahtarın TÜM dil karşılıklarını (EN + TR) döner."""
    degerler: List[str] = []
    kalip = re.compile(r"'%s':\s*%s" % (re.escape(anahtar), _DEGER_DESENI))
    for dosya in SOZLUK_DOSYALARI:
        metin = (ROOT / dosya).read_text(encoding='utf-8')
        degerler.extend(m.group(1) for m in kalip.finditer(metin))
    return degerler


# ---------------------------------------------------------------------------
# Ölçüm kurucuları (gerçek turun sadeleştirilmiş hâli)
# ---------------------------------------------------------------------------

def cizim_olcumu(**degisiklikler) -> Dict[str, Any]:
    """Ekranda çizilmiş bir Plotly kabının ölçümü."""
    temel = {'mevcut': True, 'gorunur': True, 'plotly_kabi': True,
             'svg_sayisi': 3, 'canvas_sayisi': 0,
             'genislik': 1560, 'yukseklik': 340}
    temel.update(degisiklikler)
    return temel


def rozet(metin: str, tur_adi: str = 'info') -> Dict[str, Any]:
    return {'tur': tur_adi, 'metin': metin}


#: Hibrit yapısal panelinin SAĞLIKLI ölçümü — 2026-08-15 turunda gerçekten
#: okunan rozet ve süre değerleri (rapor: ``olcumler.fea.yapisal``).
#: Uydurma sayı yok: sentetik olan yalnız BOZULMUŞ varyantlardır.
def yapisal_olcum(**degisiklikler) -> Dict[str, Any]:
    temel = {
        'ad': 'yapisal', 'panel': 'feaPanel', 'api': 'FeaPanel',
        'panel_var': True, 'panel_gorunur': True, 'api_var': True,
        'yuk_var': True, 'mesgul': False, 'basladi': True,
        'asama': 'tamam', 'kosum_s': 0.14, 'cip_metni': '',
        'zaman_asimi_ms': esikler.FEA_KOSUM_ZAMAN_ASIMI_MS,
        'kosum_secicisi': '#fea_run',
        'rozetler': [
            rozet('ENGINE: HYBRID'),
            rozet('MESH 1024 elements / 1105 nodes'),
            rozet('PEAK von MISES 16.8 MPa (Gauss points)'),
            rozet('MIN SAFETY FACTOR 12.83 (Gauss points)', 'ok'),
            rozet('CONVERGED in 3 rounds to 0.55%', 'ok'),
            rozet('MESH DISTORTION (scaled Jacobian < 0.5): 0/1024 flagged', 'ok'),
            rozet('ELONGATED ELEMENTS (aspect ratio > 4): 1024/1024 — expected '
                  'where a thin wall is swept along a long contour, not a '
                  'distortion alarm'),
        ],
        'rozet_sayisi': 7,
        'cizimler': {k: cizim_olcumu()
                     for k in sayfalar.YAPISAL_FEA.cizim_kimlikleri},
        'panel_plotly_kap_sayisi': 4,
    }
    temel.update(degisiklikler)
    return temel


def termal_olcum(**degisiklikler) -> Dict[str, Any]:
    """Aynı turun termal paneli (``olcumler.fea.termal``)."""
    temel = {
        'ad': 'termal', 'panel': 'thermalFeaPanel', 'api': 'ThermalFeaPanel',
        'panel_var': True, 'panel_gorunur': True, 'api_var': True,
        'yuk_var': True, 'mesgul': False, 'basladi': True,
        'asama': 'tamam', 'kosum_s': 0.12, 'cip_metni': '',
        'zaman_asimi_ms': esikler.FEA_TERMAL_KOSUM_ZAMAN_ASIMI_MS,
        'kosum_secicisi': '#fea_t_run',
        'rozetler': [
            rozet('ENGINE: HYBRID'),
            rozet('MESH 64 elements / 85 nodes'),
            rozet('PEAK WALL T 3056 K at t = 10.00 s'),
            rozet('EXCEEDS MELTING POINT (1673 K) — the material would not '
                  'survive this burn', 'err'),
            rozet('ENERGY RESIDUAL 4.6e-15 (relative)'),
            rozet('TIME STEP CONVERGED', 'ok'),
        ],
        'rozet_sayisi': 6,
        'cizimler': {k: cizim_olcumu()
                     for k in sayfalar.TERMAL_FEA.cizim_kimlikleri},
        'panel_plotly_kap_sayisi': 3,
    }
    temel.update(degisiklikler)
    return temel


def tane_olcum(**degisiklikler) -> Dict[str, Any]:
    """Aynı turun tane kesiti paneli (``olcumler.fea.tane``)."""
    temel = {
        'ad': 'tane', 'panel': 'grainFeaPanel', 'api': 'GrainFeaPanel',
        'panel_var': True, 'panel_gorunur': True, 'api_var': True,
        'yuk_var': True, 'mesgul': False, 'basladi': True,
        'asama': 'tamam', 'kosum_s': 0.23, 'cip_metni': '',
        'zaman_asimi_ms': esikler.FEA_KOSUM_ZAMAN_ASIMI_MS,
        'kosum_secicisi': '#grainfea_run',
        'rozetler': [
            rozet('SECTION: BATES · 1/8 slice'),
            rozet('MESH 6144 elements / 6369 nodes'),
            rozet('PEAK von MISES 0.073 MPa (Gauss points)'),
            rozet('MAX BORE STRAIN 1.00% of 35.0% capability'),
            rozet('STRAIN MARGIN 35.01 (capability / peak strain)', 'ok'),
            rozet('ACCEPTANCE METRIC (bore strain) CONVERGED — last change '
                  '0.0007914% (tolerance 1%)', 'ok'),
            rozet('PEAK vM still refining 2.019% — not the acceptance basis'),
            rozet('MESH DISTORTION (scaled Jacobian < 0.5): 0/6144 flagged', 'ok'),
            rozet('ELONGATED ELEMENTS (aspect ratio > 4): 6144/6144 — '
                  'expected for a thin web meshed in layers around the port '
                  'contour, not a distortion alarm'),
        ],
        'rozet_sayisi': 9,
        'cizimler': {k: cizim_olcumu()
                     for k in sayfalar.TANE_FEA.cizim_kimlikleri},
        'panel_plotly_kap_sayisi': 3,
    }
    temel.update(degisiklikler)
    return temel


# ---------------------------------------------------------------------------
# 1. Sayfa/panel tanımları ürünle uyumlu mu
# ---------------------------------------------------------------------------

class TestPanelTanimlari:
    """Kimlikler üründe gerçekten var mı? (tarayıcı açmadan, saniyeler içinde)"""

    def test_hangi_sayfada_hangi_panel(self):
        """Hibritte iki panel, katıda bir, sıvıda BİR (yapısal).

        ESKİ SÖZLEŞME sıvıda sıfırdı (köşe tekilliği borcu — koşum
        yakınsamıyordu). Borç 2026-08-15'te mesh_axisym'in dış yüzey
        eğrilik tabanıyla kapandı ve panel liquid.html'e bağlandı; termal
        ve tane panelleri sıvıya BİLEREK eklenmedi (termal zincir sayfada
        yok, tane katıya özgü) — bu bekçi o ikisinin hayalet olarak
        sızmadığını da kilitler.
        """
        assert [p.ad for p in sayfalar.SAYFALAR['hybrid'].fea_panelleri] == \
            ['yapisal', 'termal']
        assert [p.ad for p in sayfalar.SAYFALAR['solid'].fea_panelleri] == ['tane']
        assert [p.ad for p in sayfalar.SAYFALAR['liquid'].fea_panelleri] == \
            ['yapisal']

    @pytest.mark.parametrize('tanim,kaynak', [
        (sayfalar.YAPISAL_FEA, 'hrma/static/js/fea_panel.js'),
        (sayfalar.TERMAL_FEA, 'hrma/static/js/thermal_fea_panel.js'),
        (sayfalar.TANE_FEA, 'hrma/static/js/fea_panel.js'),
    ])
    def test_kimlikler_panel_kaynaginda_var(self, tanim, kaynak):
        """Panel kimliği/düğmesi/kapları yeniden adlandırılırsa tur körleşir.

        Bu bekçi o körleşmeyi tarayıcı açmadan yakalar: her kimlik panelin
        HTML iskeletinde ``id="..."`` olarak aranır.
        """
        metin = (ROOT / kaynak).read_text(encoding='utf-8')
        beklenen = [tanim.panel_kimligi, tanim.mesgul_kimligi,
                    tanim.cip_kimligi, tanim.rozet_kimligi]
        beklenen += list(tanim.cizim_kimlikleri)
        beklenen.append(tanim.kosum_secicisi.lstrip('#'))
        for kimlik in beklenen:
            assert 'id="%s"' % kimlik in metin, (tanim.ad, kimlik)

    @pytest.mark.parametrize('tanim,kaynak', [
        (sayfalar.YAPISAL_FEA, 'hrma/static/js/fea_panel.js'),
        (sayfalar.TERMAL_FEA, 'hrma/static/js/thermal_fea_panel.js'),
        (sayfalar.TANE_FEA, 'hrma/static/js/fea_panel.js'),
    ])
    def test_panel_apisi_window_uzerine_asiliyor(self, tanim, kaynak):
        """Hüküm ``window.<API>.payload``ye bakar; o kanal kapanırsa fark et."""
        metin = (ROOT / kaynak).read_text(encoding='utf-8')
        assert 'window.%s = {' % tanim.api_adi in metin, tanim.api_adi
        assert 'get payload()' in metin

    def test_paneller_sayfa_sablonunda_kuruluyor(self):
        """Panel dosyası var ama sayfada init edilmiyorsa tur boşa gezer."""
        adv = (ROOT / 'hrma/templates/advanced.html').read_text(encoding='utf-8')
        assert 'FeaPanel.init(' in adv
        assert 'ThermalFeaPanel.init(' in adv
        katı = (ROOT / 'hrma/templates/solid.html').read_text(encoding='utf-8')
        assert 'GrainFeaPanel.init(' in katı

    def test_termal_panel_ortam_alani_on_dolu(self):
        """293,15 K ön-dolu gelir; tur ona DOKUNMAZ (varsayılan yol denetlenir)."""
        metin = (ROOT / 'hrma/static/js/thermal_fea_panel.js').read_text(
            encoding='utf-8')
        assert 'id="fea_t_ambient" value="293.15"' in metin

    def test_denetim_adlari_sayfa_icinde_benzersiz(self):
        """İki panelin denetimi aynı adı taşırsa rapor okunamaz hâle gelir."""
        for sayfa in sayfalar.SAYFALAR.values():
            adlar = []
            for tanim in sayfa.fea_panelleri:
                adlar += [d.ad for d in denetimler.fea_denetimleri(tanim, None)]
            assert len(adlar) == len(set(adlar)), (sayfa.ad, adlar)


# ---------------------------------------------------------------------------
# 2. Rozet imzaları ürünün sözlüğüne bağlı mı
# ---------------------------------------------------------------------------

class TestRozetImzalari:
    """İmza tablosu ile ürünün bastığı cümle arasındaki bağ.

    Tur ``en-US`` yereliyle koşar, ama imza tablosu TR karşılığını da
    taşır; iki dilin de tabloya bağlanması, arayüz dili değişince turun
    sessizce körleşmesini engeller.
    """

    @pytest.mark.parametrize('imza', ['mesh_bozulmasi', 'uzamis_elemanlar',
                                      'kabul_olcutu', 'tepe_cidar_sicakligi'])
    def test_imza_sozlukteki_her_dilde_geciyor(self, imza):
        tanim = esikler.ROZET_IMZALARI[imza]
        varyantlar = tanim['varyantlar']
        assert varyantlar, imza
        for anahtar in tanim['sozluk_anahtarlari']:
            degerler = sozluk_degerleri(anahtar)
            assert len(degerler) >= 2, (
                '%s sözlükte iki dilde bulunmalı, bulunan: %d'
                % (anahtar, len(degerler)))
            for deger in degerler:
                assert any(v in deger for v in varyantlar), (
                    'imza %r, %s karşılığında geçmiyor: %r'
                    % (varyantlar, anahtar, deger))

    @pytest.mark.parametrize('imza', ['mesh_bozulmasi', 'uzamis_elemanlar',
                                      'kabul_olcutu', 'tepe_cidar_sicakligi'])
    def test_imza_ingilizce_yedekte_de_geciyor(self, imza):
        """Sözlük yüklenmezse panel YEDEK metni basar; imza orada da olmalı."""
        tanim = esikler.ROZET_IMZALARI[imza]
        for dosya in tanim['kaynak_dosyalar']:
            metin = (ROOT / dosya).read_text(encoding='utf-8')
            assert any(v in metin for v in tanim['varyantlar']), (imza, dosya)

    def test_eski_birlesik_rozet_anahtari_sozlukten_kalkti(self):
        """Ayrışmanın kanıtı: eski anahtar sözlükte artık yok."""
        for anahtar in esikler.ROZET_IMZALARI[
                'birlesik_kalite_alarmi']['eski_anahtarlar']:
            assert sozluk_degerleri(anahtar) == [], anahtar

    def test_tanimsiz_imza_sessizce_gecmez(self):
        with pytest.raises(KeyError):
            denetimler.imza_varyantlari('boyle_bir_imza_yok')

    def test_sayfalarin_kullandigi_imzalar_tabloda_tanimli(self):
        for sayfa in sayfalar.SAYFALAR.values():
            for tanim in sayfa.fea_panelleri:
                for imza in tuple(tanim.beklenen_imzalar) + tuple(tanim.yasak_imzalar):
                    assert denetimler.imza_varyantlari(imza)

    def test_eslesme_buyuk_kucuk_harf_duyarli(self):
        """"acceptance" kelimesinin cümlede geçmesi rozet demek değildir."""
        rozetler = [rozet('the acceptance metric is described below')]
        assert denetimler.imza_eslesen_rozetler(rozetler, 'kabul_olcutu') == []


# ---------------------------------------------------------------------------
# 3. Koşum hükmü
# ---------------------------------------------------------------------------

class TestKosumDenetimi:

    def test_saglikli_kosum_gecer(self):
        hukum = denetimler.fea_kosum_denetimi('yapisal', yapisal_olcum())
        assert hukum.gecti is True
        assert 'yük yayımlandı' in hukum.ozet
        assert hukum.kesinlik == 'dogrudan'

    def test_olcum_yoksa_kalir(self):
        """Ölçülemeyen panel "geçti" sayılamaz."""
        hukum = denetimler.fea_kosum_denetimi('yapisal', None)
        assert hukum.gecti is False
        assert 'ölçülemedi' in hukum.ozet

    def test_panel_yoksa_kalir(self):
        hukum = denetimler.fea_kosum_denetimi(
            'yapisal', yapisal_olcum(panel_var=False, yuk_var=False))
        assert hukum.gecti is False
        assert 'sayfada YOK' in hukum.ozet
        assert 'feaPanel' in hukum.ozet

    def test_panel_gorunmuyorsa_kalir(self):
        """Panel DOM'da olup ekranda olmaması kullanıcı için "yok" demektir."""
        hukum = denetimler.fea_kosum_denetimi(
            'yapisal', yapisal_olcum(panel_gorunur=False, yuk_var=False))
        assert hukum.gecti is False
        assert 'GÖRÜNMÜYOR' in hukum.ozet

    def test_dugme_yoksa_secici_yazilir(self):
        hukum = denetimler.fea_kosum_denetimi(
            'yapisal', yapisal_olcum(asama='dugme_yok', yuk_var=False))
        assert hukum.gecti is False
        assert '#fea_run' in hukum.ozet

    def test_zaman_asimi_ayri_gerekce_yazar(self):
        hukum = denetimler.fea_kosum_denetimi(
            'termal', termal_olcum(asama='zaman_asimi', yuk_var=False,
                                   mesgul=True, cip_metni=''))
        assert hukum.gecti is False
        assert 'BİTMEDİ' in hukum.ozet
        assert str(esikler.FEA_TERMAL_KOSUM_ZAMAN_ASIMI_MS) in hukum.ozet

    def test_kosum_hic_baslamadiysa_ayri_gerekce(self):
        """Sayfada motor sonucu yoksa ``run()`` fetch'e hiç gitmez."""
        hukum = denetimler.fea_kosum_denetimi(
            'yapisal', yapisal_olcum(
                basladi=False, yuk_var=False, asama='tamam',
                cip_metni='RUN FAILED — no field is drawn No motor result on '
                          'this page yet'))
        assert hukum.gecti is False
        assert 'BAŞLAMADI' in hukum.ozet
        assert 'RUN FAILED' in hukum.ozet, 'panelin kendi gerekçesi kopyalanmalı'

    def test_uc_hata_dondurduyse_yuk_yok_hukmu(self):
        hukum = denetimler.fea_kosum_denetimi(
            'tane', tane_olcum(yuk_var=False, rozetler=[], rozet_sayisi=0,
                               cip_metni='RUN FAILED — grain FEA endpoint '
                                         'returned an error'))
        assert hukum.gecti is False
        assert 'YÜK YAYIMLANMADI' in hukum.ozet
        assert 'GrainFeaPanel' in hukum.ozet

    def test_hukum_dayanak_beyan_eder(self):
        """Sahte veri yasağı: hükmün okunduğu kanal yazılmak zorunda."""
        for olcum in (yapisal_olcum(), termal_olcum(), tane_olcum()):
            sozluk = denetimler.fea_kosum_denetimi(olcum['ad'], olcum).sozluk()
            assert sozluk['dayanak']
            assert sozluk['kesinlik'] == 'dogrudan'


# ---------------------------------------------------------------------------
# 4. Çizim hükmü
# ---------------------------------------------------------------------------

class TestCizimDenetimi:

    def test_dort_cizim_ekrandaysa_gecer(self):
        hukum = denetimler.fea_cizim_denetimi(
            'yapisal', yapisal_olcum(), sayfalar.YAPISAL_FEA.cizim_kimlikleri)
        assert hukum.gecti is True
        assert 'fea_plot_quality' in hukum.ozet

    def test_kap_yoksa_kalir(self):
        cizimler = dict(yapisal_olcum()['cizimler'])
        cizimler['fea_plot_sf'] = {'mevcut': False}
        hukum = denetimler.fea_cizim_denetimi(
            'yapisal', yapisal_olcum(cizimler=cizimler),
            sayfalar.YAPISAL_FEA.cizim_kimlikleri)
        assert hukum.gecti is False
        assert 'kap sayfada yok' in hukum.ozet
        assert 'fea_plot_sf' in hukum.ozet

    def test_gizli_kap_cizim_sayilmaz(self):
        """Gizli kaptaki eski çizim EKRANDA değildir."""
        cizimler = dict(yapisal_olcum()['cizimler'])
        cizimler['fea_plot_conv'] = cizim_olcumu(gorunur=False, genislik=0,
                                                 yukseklik=0)
        hukum = denetimler.fea_cizim_denetimi(
            'yapisal', yapisal_olcum(cizimler=cizimler),
            sayfalar.YAPISAL_FEA.cizim_kimlikleri)
        assert hukum.gecti is False
        assert 'kap ekranda değil' in hukum.ozet
        # Ölçülen kutu ve eşik birlikte yazılır: "kap kapalı" ile "eşik
        # yanlış" ayrımı hükmü okuyanda kalmasın.
        assert str(esikler.FEA_CIZIM_MIN_KENAR_PX) in hukum.ozet

    def test_bos_kap_cizim_sayilmaz(self):
        """Kap açık ama Plotly çizim atmışsa içinde svg/canvas yoktur."""
        cizimler = dict(termal_olcum()['cizimler'])
        cizimler['fea_t_plot_hist'] = cizim_olcumu(svg_sayisi=0, canvas_sayisi=0)
        hukum = denetimler.fea_cizim_denetimi(
            'termal', termal_olcum(cizimler=cizimler),
            sayfalar.TERMAL_FEA.cizim_kimlikleri)
        assert hukum.gecti is False
        assert 'svg/canvas yok' in hukum.ozet

    def test_webgl_cizimi_de_gecerli_sayilir(self):
        """Plotly bazı izleri canvas'a çizer; svg yok diye "boş" denmez."""
        cizimler = {k: cizim_olcumu(svg_sayisi=0, canvas_sayisi=1)
                    for k in sayfalar.TANE_FEA.cizim_kimlikleri}
        hukum = denetimler.fea_cizim_denetimi(
            'tane', tane_olcum(cizimler=cizimler),
            sayfalar.TANE_FEA.cizim_kimlikleri)
        assert hukum.gecti is True

    def test_plotly_disi_kap_kalir(self):
        cizimler = dict(tane_olcum()['cizimler'])
        cizimler['grainfea_plot_bore'] = cizim_olcumu(plotly_kabi=False)
        hukum = denetimler.fea_cizim_denetimi(
            'tane', tane_olcum(cizimler=cizimler),
            sayfalar.TANE_FEA.cizim_kimlikleri)
        assert hukum.gecti is False
        assert 'Plotly ile çizilmemiş' in hukum.ozet

    def test_olcum_yoksa_kalir(self):
        hukum = denetimler.fea_cizim_denetimi(
            'termal', None, sayfalar.TERMAL_FEA.cizim_kimlikleri)
        assert hukum.gecti is False
        assert 'ölçülemedi' in hukum.ozet

    def test_kusur_ozeti_cip_gerekcesini_tasir(self):
        """Çizim yoksa sebebi genelde koşumdadır; panelin çipi onu söyler."""
        cizimler = {k: {'mevcut': True, 'gorunur': False, 'plotly_kabi': False,
                        'svg_sayisi': 0, 'canvas_sayisi': 0,
                        'genislik': 0, 'yukseklik': 0}
                    for k in sayfalar.YAPISAL_FEA.cizim_kimlikleri}
        hukum = denetimler.fea_cizim_denetimi(
            'yapisal',
            yapisal_olcum(cizimler=cizimler, yuk_var=False,
                          cip_metni='NOT MODELLED — the solver result does not '
                                    'carry the inputs the FEA needs'),
            sayfalar.YAPISAL_FEA.cizim_kimlikleri)
        assert hukum.gecti is False
        assert 'NOT MODELLED' in hukum.ozet
        assert '4/4' in hukum.ozet


# ---------------------------------------------------------------------------
# 5. Rozet hükmü
# ---------------------------------------------------------------------------

class TestRozetDenetimi:

    def test_beklenen_imzalar_varsa_gecer(self):
        hukum = denetimler.fea_rozet_denetimi(
            'yapisal', yapisal_olcum(), sayfalar.YAPISAL_FEA.beklenen_imzalar,
            sayfalar.YAPISAL_FEA.yasak_imzalar)
        assert hukum.gecti is True
        assert 'mesh_bozulmasi' in hukum.ozet
        assert 'uzamis_elemanlar' in hukum.ozet

    def test_rozet_rengi_ozete_yazilir_ama_hukme_girmez(self):
        """Renk tasarım noktasının fiziğidir; kırmızı rozet kapıyı kapatmaz.

        Ölçülen gerçek durum: termal panelde "EXCEEDS MELTING POINT" rozeti
        kırmızıdır (3056 K > 1673 K). Bu bir ARAYÜZ kusuru değil, motorun
        sonucudur — tur onu raporlar, hükmü değiştirmez.
        """
        hukum = denetimler.fea_rozet_denetimi(
            'termal', termal_olcum(), sayfalar.TERMAL_FEA.beklenen_imzalar)
        assert hukum.gecti is True
        assert any(r['tur'] == 'err' for r in termal_olcum()['rozetler'])
        assert '[info]' in hukum.ozet   # eşleşen rozetin rengi yazılır

    def test_eksik_imza_kalir_ve_aranani_yazar(self):
        rozetler = [r for r in yapisal_olcum()['rozetler']
                    if 'Jacobian' not in r['metin']]
        hukum = denetimler.fea_rozet_denetimi(
            'yapisal', yapisal_olcum(rozetler=rozetler),
            sayfalar.YAPISAL_FEA.beklenen_imzalar)
        assert hukum.gecti is False
        assert 'mesh_bozulmasi' in hukum.ozet
        assert 'Jacobian' in hukum.ozet, 'aranan imza hükümde yazmalı'

    @pytest.mark.parametrize('eski_metin', [
        'MESH QUALITY 192/192 elements outside the acceptable range',
        'MESH KALİTESİ 192/192 eleman kabul aralığı dışında',
    ])
    def test_eski_birlesik_alarm_geri_gelirse_kalir(self, eski_metin):
        """Ayrışma geri alınırsa tur KIRMIZI verir — iki dilde de."""
        rozetler = yapisal_olcum()['rozetler'] + [rozet(eski_metin, 'err')]
        hukum = denetimler.fea_rozet_denetimi(
            'yapisal', yapisal_olcum(rozetler=rozetler),
            sayfalar.YAPISAL_FEA.beklenen_imzalar,
            sayfalar.YAPISAL_FEA.yasak_imzalar)
        assert hukum.gecti is False
        assert 'YASAK imza' in hukum.ozet

    def test_kabul_olcutu_rozeti_tane_panelinde_aranir(self):
        """Tane kesitinde hüküm port lif gerinimindedir, tepe vM'de değil."""
        hukum = denetimler.fea_rozet_denetimi(
            'tane', tane_olcum(), sayfalar.TANE_FEA.beklenen_imzalar,
            sayfalar.TANE_FEA.yasak_imzalar)
        assert hukum.gecti is True
        assert 'kabul_olcutu [ok]' in hukum.ozet, 'yeşil hüküm rapora yazılmalı'

    def test_kabul_rozeti_yoksa_kalir(self):
        """Sunucu kabul bloğunu yayımlamayı bırakırsa panel eski rozete düşer;
        bu SESSİZ bir gerileme olurdu — tur onu görmeli."""
        rozetler = [r for r in tane_olcum()['rozetler']
                    if 'ACCEPTANCE METRIC' not in r['metin']]
        rozetler.append(rozet('CONVERGED in 4 rounds to 5.59%', 'ok'))
        hukum = denetimler.fea_rozet_denetimi(
            'tane', tane_olcum(rozetler=rozetler),
            sayfalar.TANE_FEA.beklenen_imzalar)
        assert hukum.gecti is False
        assert 'kabul_olcutu' in hukum.ozet

    def test_hic_rozet_yoksa_kalir(self):
        hukum = denetimler.fea_rozet_denetimi(
            'termal', termal_olcum(rozetler=[], rozet_sayisi=0),
            sayfalar.TERMAL_FEA.beklenen_imzalar)
        assert hukum.gecti is False

    def test_okunan_rozetler_kusur_ozetine_yazilir(self):
        """Kaldı diyen bir hüküm, ekranda NE OLDUĞUNU da söylemeli."""
        hukum = denetimler.fea_rozet_denetimi(
            'termal',
            termal_olcum(rozetler=[rozet('MESH 64 elements / 85 nodes')],
                         rozet_sayisi=1),
            sayfalar.TERMAL_FEA.beklenen_imzalar)
        assert hukum.gecti is False
        assert 'MESH 64 elements' in hukum.ozet

    def test_olcum_yoksa_kalir(self):
        hukum = denetimler.fea_rozet_denetimi(
            'tane', None, sayfalar.TANE_FEA.beklenen_imzalar)
        assert hukum.gecti is False
        assert 'ölçülemedi' in hukum.ozet


# ---------------------------------------------------------------------------
# 6. Üçlü hüküm ve tur akışına bağlanma
# ---------------------------------------------------------------------------

class TestAkisaBaglanma:

    def test_panel_basina_uc_hukum(self):
        hukumler = denetimler.fea_denetimleri(sayfalar.YAPISAL_FEA,
                                              yapisal_olcum())
        assert [h.ad for h in hukumler] == ['fea_yapisal_kosum',
                                            'fea_yapisal_cizim',
                                            'fea_yapisal_rozet']
        assert all(h.gecti for h in hukumler)

    def test_olcum_yoksa_uc_hukum_de_kalir(self):
        hukumler = denetimler.fea_denetimleri(sayfalar.TANE_FEA, None)
        assert len(hukumler) == 3
        assert not any(h.gecti for h in hukumler)

    def _gezgin(self, sayfa_adi: str):
        # Tarayıcı nesnesi None: ``_rapor`` sayfaya DOKUNMAZ, yalnız
        # toplanmış ölçümlerden hüküm üretir.
        return tur.SayfaGezgini(None, 'http://127.0.0.1:1',
                                sayfalar.SAYFALAR[sayfa_adi], '/tmp')

    def _tam_rapor(self, sayfa_adi: str, fea: Dict[str, Any], merkez=None):
        """FEA'ya odaklı rapor — Merkez ölçümü SAĞLIKLI varsayılır.

        Üç sayfanın üçünde de Analiz Merkezi kurulu (16 Ağu 2026); ölçümü
        verilmezse Merkez'in dört denetimi haklı olarak KALIR ve FEA'yı
        ölçen bu testler onun yüzünden kırmızıya düşerdi. Merkez'in kendi
        bekçileri ``tests/test_browser_harness_merkez.py``de.
        """
        from tests.test_browser_harness_merkez import merkez_olcumu
        gezgin = self._gezgin(sayfa_adi)
        return gezgin._rapor(
            sureler={'yukleme_s': 0.7, 'hesap_s': 3.1},
            viz={'erisim': 'motorviz3d', 'cizim_araligi': 900,
                 'plume_bilgisi_var': True, 'oynatiliyor': True,
                 'plume_acik': True, 'partikul_tavani': 900},
            tuval_ham={'kaynak': 'MotorViz3D.snapshot()'},
            piksel={'dolu_oran': 0.19, 'icerik_entropi_bit': 3.07,
                    'parlak_oran': 0.01},
            metin='Chamber Pressure 20.0 bar', plume_baslatma='ui',
            goruntuler={'tam_sayfa': None, 'uc_boyut': None}, fea=fea,
            merkez=merkez_olcumu() if merkez is None else merkez)

    def test_hibrit_raporu_iki_paneli_de_denetler(self):
        rapor = self._tam_rapor('hybrid', {'yapisal': yapisal_olcum(),
                                           'termal': termal_olcum()})
        adlar = [d['ad'] for d in rapor['denetimler']]
        assert adlar[:5] == ['akis_tamam', 'tuval_dolu', 'plume_cizildi',
                             'konsol_temiz', 'sizinti_yok']
        assert adlar[5:11] == ['fea_yapisal_kosum', 'fea_yapisal_cizim',
                               'fea_yapisal_rozet', 'fea_termal_kosum',
                               'fea_termal_cizim', 'fea_termal_rozet']
        # NÖBET DEĞİŞİMİ (16 Ağu 2026): FEA üçlülerinden SONRA Analiz
        # Merkezi'nin dörtlüsü geliyor. Eski sözleşme "adlar[5:] yalnız
        # FEA" diyordu; Merkez ürüne girince o cümle YALANCI olurdu.
        assert adlar[11:] == ['merkez_cerceve', 'merkez_cfd_kosum',
                              'merkez_cfd_cizim', 'merkez_cfd_rozet']
        assert rapor['gecti'] is True
        assert rapor['olcumler']['fea']['termal']['kosum_s'] == 0.12

    def test_tek_fea_denetimi_kalirsa_sayfa_kalir(self):
        """FEA denetimi ESKİ denetimlerle aynı ağırlıkta: biri kalırsa sayfa kalır."""
        rapor = self._tam_rapor('solid', {'tane': tane_olcum(yuk_var=False)})
        assert rapor['gecti'] is False
        kalanlar = [d['ad'] for d in rapor['denetimler'] if not d['gecti']]
        assert kalanlar == ['fea_tane_kosum']

    def test_sivi_sayfasinda_yapisal_fea_denetlenir(self):
        """Sıvı raporu yapısal FEA üçlüsünü taşır; ölçümsüz hüküm KALIR.

        ESKİ SÖZLEŞME: sıvıda panel bilerek yoktu ve tur hayalet denetim
        üretmezdi. Panel 2026-08-15'te bağlandı (dış yüzey eğrilik tabanı);
        yeni sözleşme üç şeyi kilitler: (1) fea_yapisal_* üçlüsü sıvı
        raporunda VAR, (2) ölçüm yokken üçü de KALIR — panel ekrandan
        düşerse tur sessiz yeşile dönmez, (3) termal/tane hayaleti YOK.
        """
        rapor = self._tam_rapor('liquid', {})
        adlar = [d['ad'] for d in rapor['denetimler']]
        assert adlar[5:8] == ['fea_yapisal_kosum', 'fea_yapisal_cizim',
                              'fea_yapisal_rozet']
        assert not any(a.startswith(('fea_termal', 'fea_tane'))
                       for a in adlar)
        assert rapor['gecti'] is False
        kalanlar = [d['ad'] for d in rapor['denetimler'] if not d['gecti']]
        assert kalanlar == ['fea_yapisal_kosum', 'fea_yapisal_cizim',
                            'fea_yapisal_rozet']
        # Sağlıklı ölçümle sıvı raporu yeşile döner (ölçüm sözlüğü sentetik
        # test altyapısıdır; imza denetimleri panel adına değil rozet
        # metnine bakar, iki sayfada da aynı panel JS'i üretir).
        saglam = self._tam_rapor('liquid', {'yapisal': yapisal_olcum()})
        assert saglam['gecti'] is True

    def test_fea_olcumu_rapora_yazilir(self):
        rapor = self._tam_rapor('solid', {'tane': tane_olcum()})
        assert rapor['olcumler']['fea']['tane']['rozet_sayisi'] == 9
        assert json.dumps(rapor, ensure_ascii=False)

    def test_yapilandirma_sozlugu_panel_tanimindan_uretilir(self):
        cfg = self._gezgin('hybrid')._fea_yapilandirmasi(sayfalar.TERMAL_FEA)
        assert cfg == {'panel': 'thermalFeaPanel', 'api': 'ThermalFeaPanel',
                       'mesgul': 'fea_t_busy', 'cip': 'fea_t_chip',
                       'rozet': 'fea_t_badges',
                       'cizimler': list(sayfalar.TERMAL_FEA.cizim_kimlikleri),
                       'min_kenar': esikler.FEA_CIZIM_MIN_KENAR_PX}


# ---------------------------------------------------------------------------
# 7. Ölçüm betikleri
# ---------------------------------------------------------------------------

class TestOlcumBetikleri:

    def test_betik_dogrudan_dayanaklari_okur(self):
        for parca in ('payload', '[data-badge]', 'js-plotly-plot',
                      'getBoundingClientRect', 'getComputedStyle'):
            assert parca in tur.JS_FEA_PANEL_DURUMU, parca

    def test_mesgul_betikleri_yalnizca_gorunurluge_bakar(self):
        """Meşgul göstergesi METİNLE değil, görünürlükle okunur (i18n)."""
        for betik in (tur.JS_FEA_MESGUL, tur.JS_FEA_BITTI):
            assert 'display' in betik
            assert 'textContent' not in betik

    def test_gosterge_yoksa_kosum_bitmis_sayilir(self):
        """``JS_FEA_BITTI`` gösterge bulunamazsa ``true`` döner: sonsuz
        bekleme yerine hüküm YÜKE bakar (o da yoksa denetim kalır)."""
        assert 'return true' in tur.JS_FEA_BITTI

    def test_esik_kunyesi_fea_esiklerini_tasir(self):
        """Eşik sonradan değişse bile eski rapor doğru yorumlanabilsin."""
        kunye = run_tour.esik_kunyesi()
        assert kunye['FEA_CIZIM_MIN_KENAR_PX'] == esikler.FEA_CIZIM_MIN_KENAR_PX
        assert kunye['FEA_TERMAL_KOSUM_ZAMAN_ASIMI_MS'] == \
            esikler.FEA_TERMAL_KOSUM_ZAMAN_ASIMI_MS
        assert 'mesh_bozulmasi' in kunye['ROZET_IMZALARI']
        assert json.dumps(kunye, ensure_ascii=False)

    def test_her_imzanin_gerekcesi_yazili(self):
        """"Böyle olsun" diye konmuş imza yok: her biri neden orada, yazar."""
        for ad, tanim in esikler.ROZET_IMZALARI.items():
            assert tanim.get('gerekce'), ad
            assert tanim.get('varyantlar'), ad
