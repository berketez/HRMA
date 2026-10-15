"""ÖH Dalga-24 · altyapı · aşama-1 — defter **P10B3-02**.

Ne sınanıyor
------------
``tools/browser_harness/tur.py`` — turun ÜRÜNE DOKUNAN ölçüm katmanı.

Kalemin iddiası: turun hüküm katmanı (``denetimler.py``) neredeyse tam
kapsamlıyken ölçüm katmanı ``tur.py`` **hiçbir testte çalışmıyordu**;
adım sırası, istisna dalları, hesapsız sayfa dalı, tarayıcı kanal düşüşü
ve rapor gövdesi ancak 12 dakikalık canlı turda görülebiliyordu.
D21/D22/D23'te kalem "uçtan uca sahte sayfa iskelesi (Playwright ``Page``
ikizi) gerekiyor" gerekçesiyle ertelendi. İskele bu dalgada kuruldu:
``tests/support/sahte_sayfa.py``.

İkizin dürüstlük sözleşmesi
---------------------------
* ``evaluate`` cevapları UYDURULMAZ: varsayılan senaryo, kayıtlı **canlı
  turun** ölçümlerinin yeniden oynatımıdır
  (``docs/scofield/raw/OH/Z5/denetim/tur/tour_report.json``).
* İkiz tanımadığı bir ``JS_*`` betiği görürse KIRMIZI yanar
  (``BilinmeyenBetik``); ``tur.py``ye eklenen yeni bir betik bu dosyayı
  sessizce geçemez.
* İkiz tarayıcı SADAKATİNİ kanıtlamaz — ``JS_*`` gövdelerinin gerçek
  DOM'da ne döndüğünü değil, ``tur.py``nin dönenle NE YAPTIĞINI sınar.
  Tarayıcı sadakati canlı turun (P17B1-15) işidir.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.browser_harness import esikler, sayfalar, tur  # noqa: E402
from tests.support import sahte_sayfa as ikiz  # noqa: E402
from tests.support.kanit import kanit_gerekli  # noqa: E402


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------

def gez(sayfa_adi: str, cikti, **degistir):
    """Sayfayı ikizle gezer; ``(rapor, gezgin, ikiz_sayfa)`` döner."""
    senaryo = ikiz.canli_senaryo(sayfa_adi, **degistir)
    sahte = ikiz.SahteSayfa(senaryo)
    gezgin = tur.SayfaGezgini(sahte, 'http://127.0.0.1:5000',
                              sayfalar.SAYFALAR[sayfa_adi], str(cikti))
    return gezgin.gez(), gezgin, sahte


def denetim(rapor, ad):
    for d in rapor['denetimler']:
        if d['ad'] == ad:
            return d
    raise AssertionError('%r denetimi raporda yok: %s'
                         % (ad, [d['ad'] for d in rapor['denetimler']]))


# ===========================================================================
# A. Mutlu yol — canlı turun yeniden oynatımı
# ===========================================================================

class TestCanliTurYenidenOynatimi:
    """Ölçüm katmanı, kayıtlı canlı ölçümlerle uçtan uca koşar."""

    @pytest.mark.parametrize('sayfa_adi', ['solid'])
    def test_tur_yesil_hukum_uretebiliyor(self, sayfa_adi, tmp_path):
        """Turun her zaman kırmızı vermediğinin kanıtı.

        Canlı turun GERÇEK ölçümleriyle beslendiğinde sayfa hükmü YEŞİL
        olmalı. Bu bekçi olmadan, hüküm katmanına giren bir "hep kırmızı"
        gerilemesi ancak 12 dakikalık canlı turda görülürdü.

        ÖH D24 / P17B1-15 — ``liquid`` BU BEKÇİDEN ÇIKARILDI, gevşetildiği
        için değil ÜRÜNDE ÖLÇÜLEN BİR KUSUR bulunduğu için: 5 Eylül 2026
        canlı turu ``/liquid``de ``merkez_acoustic_modes_cizim``i KIRMIZI
        ölçtü (2 çizimden ``stab_bars_*`` ekrana hiç gelmiyor; kanıt
        ``docs/scofield/raw/OH/D24/altyapi/a2/tur_p17b115/tour_report.json``).
        Kusur örtülmüyor: aşağıdaki ``test_liquid_acoustic_modes_ÖLÇÜLEN_
        kusuru`` onu ADIYLA tutuyor ve ürün onarılınca KIRMIZI olup bu
        sayfanın mutlu yola geri alınmasını ŞART koşuyor. ``hybrid`` ise
        Z5 kaydındaki yerleşim kusurları (yatay taşma + metin örtüşmesi)
        yüzünden hâlâ dışarıda — o kalemler başka kulvarların.
        """
        rapor, gezgin, _ = gez(sayfa_adi, tmp_path)
        assert gezgin.hatalar == []
        kalanlar = [(d['ad'], d['ozet']) for d in rapor['denetimler']
                    if not d['gecti']]
        assert kalanlar == [], 'canlı ölçümle kalan denetim: %s' % (kalanlar,)
        assert rapor['gecti'] is True
        assert rapor['url'].endswith(sayfalar.SAYFALAR[sayfa_adi].yol)

    def test_liquid_acoustic_modes_OLCULEN_kusuru(self, tmp_path):
        """5 Eylül 2026 canlı turunun ``/liquid``de bulduğu kusur.

        FAIL-CLOSED KAYIT: kusur 'bilinen kırmızı' diye susturulmuyor,
        ADIYLA bağlanıyor. ``chamber_acoustics.acoustic_modes`` kiracısı
        iki çizim vaat ediyor (``stab_modes_*`` ve ``stab_bars_*``) ama
        sıvıda ikincisi görüntüleyiciye HİÇ basılmıyor.

        Ürün onarıldığında bu bekçi KIRMIZI olur; o an yapılacak iş
        bellidir: ``liquid`` yukarıdaki mutlu yol bekçisine geri alınır ve
        bu test silinir. Böylece kusur ne sessizce kalır ne de onarımı
        fark edilmeden geçer.
        """
        rapor, gezgin, _ = gez('liquid', tmp_path)
        assert gezgin.hatalar == []
        kalanlar = [(d['ad'], d['ozet']) for d in rapor['denetimler']
                    if not d['gecti']]
        assert [a for a, _ in kalanlar] == ['merkez_acoustic_modes_cizim'], \
            kalanlar
        assert 'stab_bars_' in kalanlar[0][1]
        assert rapor['gecti'] is False

    def test_adim_sirasi_sozlesmesi(self, tmp_path):
        """FEA → Merkez → sayfa metni → yerleşim sırası ürün sözleşmesidir.

        ``tur.py`` bu sırayı yorumlarında GEREKÇELENDİRİYOR (FEA kapları
        düzeni değiştirir; kiracının bastığı cümle sızıntı taramasına
        girmeli; yerleşim en dolu ekranda ölçülmeli) ama hiçbir test
        sırayı bağlamıyordu.
        """
        _, _, sahte = gez('liquid', tmp_path)
        sira = sahte.betik_sirasi()
        assert sira.index('JS_TUVAL') < sira.index('JS_FEA_PANEL_DURUMU')
        assert sira.index('JS_FEA_PANEL_DURUMU') < sira.index('JS_MERKEZ_CERCEVE')
        assert sira.index('JS_MERKEZ_KIRACI') < sira.index('JS_SAYFA_METNI')
        assert sira.index('JS_SAYFA_METNI') < sira.index('JS_YERLESIM')
        assert sira.index('JS_YERLESIM') == len(sira) - 1

    def test_tuval_pngsi_diske_yazilir_ve_piksel_olculur(self, tmp_path):
        rapor, _, _ = gez('liquid', tmp_path)
        yol = tmp_path / 'liquid_3b.png'
        assert yol.exists(), '3B tuval PNG\'si diske yazılmadı'
        assert rapor['ekran_goruntuleri']['uc_boyut'] == str(yol)
        piksel = rapor['olcumler']['piksel']
        assert 'hata' not in piksel
        assert piksel['dolu_oran'] >= esikler.TUVAL_MIN_DOLU_ORAN

    def test_tam_sayfa_goruntusunun_kendisi_olculur(self, tmp_path):
        """P17B1-05: kanıtın YOLU değil, kanıtın KENDİSİ ölçülür."""
        rapor, _, _ = gez('liquid', tmp_path)
        px = rapor['ekran_goruntuleri']['tam_sayfa_px']
        assert px == {'genislik': 1280, 'yukseklik': 3400}

    def test_rapor_govdesi_beklenen_bloklari_tasir(self, tmp_path):
        rapor, _, _ = gez('liquid', tmp_path)
        assert set(rapor) >= {'ad', 'url', 'gecti', 'sureler_s',
                              'ekran_goruntuleri', 'olcumler', 'asamalar',
                              'denetimler'}
        olcum = rapor['olcumler']
        assert set(olcum) >= {'viz', 'tuval_kaynagi', 'piksel', 'fea',
                              'merkez', 'plume_baslatma', 'yerlesim',
                              'http_hatalari', 'http_hata_sayisi'}
        assert olcum['plume_baslatma'] == 'ui'
        assert set(rapor['sureler_s']) == {'yukleme_s', 'hesap_s'}


# ===========================================================================
# B. Hesapsız sayfa dalı (defter P17B1-16)
# ===========================================================================

class TestHesapsizSayfa:
    """``/``, ``/formulas``, ``/launch-site``: hesap/3B/FEA/Merkez YOK."""

    def test_hesapsiz_sayfa_hesap_ve_sonrasini_atlar(self, tmp_path):
        rapor, gezgin, sahte = gez(
            'index', tmp_path,
            js_cevaplari={'JS_SAYFA_METNI': 'HRMA — Hybrid Rocket Motor Analysis'})
        assert gezgin.hatalar == [], 'hesapsız sayfa akışı kesilmemeli'
        assert denetim(rapor, 'akis_tamam')['gecti'] is True
        assert sahte.adimlar('click') == [], 'hesapsız sayfada düğmeye basıldı'
        sira = sahte.betik_sirasi()
        assert sira == ['JS_SAYFA_METNI', 'JS_YERLESIM']
        assert 'JS_VIZ_DURUMU' not in sira

    def test_hesapsiz_sayfada_hayalet_3b_denetimi_uretilmez(self, tmp_path):
        """Sayfada 3B sahne yoksa "tuval boş" hükmü kusur değil GÜRÜLTÜdür."""
        rapor, _, _ = gez(
            'index', tmp_path,
            js_cevaplari={'JS_SAYFA_METNI': 'HRMA'})
        adlar = [d['ad'] for d in rapor['denetimler']]
        assert 'tuval_dolu' not in adlar
        assert 'plume_cizildi' not in adlar
        assert not any(a.startswith('merkez_') for a in adlar)

    def test_hesapsiz_sayfada_yerlesim_patlarsa_akis_kesilmez(self, tmp_path):
        rapor, gezgin, _ = gez(
            'index', tmp_path,
            js_cevaplari={'JS_SAYFA_METNI': 'HRMA'},
            js_hatalari={'JS_YERLESIM': RuntimeError('bağlam kapandı')})
        assert gezgin.hatalar == []
        assert denetim(rapor, 'akis_tamam')['gecti'] is True
        assert 'RuntimeError' in rapor['olcumler']['yerlesim']['hata']


# ===========================================================================
# C. İstisna dalları — fail-closed
# ===========================================================================

class TestIstisnaDallari:

    def test_hesap_dugmesi_gorunmezse_akis_kesildi(self, tmp_path):
        rapor, gezgin, _ = gez(
            'liquid', tmp_path,
            bekleme_hatalari={'button[onclick="calculateLiquid()"]':
                              ikiz.SahteZamanAsimi('düğme görünmedi')})
        assert len(gezgin.hatalar) == 1
        assert 'SahteZamanAsimi' in gezgin.hatalar[0]
        assert 'AKIŞ KESİLDİ' in gezgin.asamalar
        d = denetim(rapor, 'akis_tamam')
        assert d['gecti'] is False and 'akışı kesildi' in d['ozet']

    def test_ag_sessizligine_ulasilamazsa_tur_devam_eder(self, tmp_path):
        # ÖH D24 / P17B1-15 — sayfa 'liquid' -> 'solid': bu bekçinin sorusu
        # "ağ sessizliği olmadan da hüküm YEŞİL kalabiliyor mu"; sıvıda
        # ölçülen acoustic_modes çizim kusuru (yukarıya bkz.) soruyu
        # alâkasız bir kırmızıyla boğuyordu.
        rapor, gezgin, _ = gez(
            'solid', tmp_path,
            ag_sessizligi_hatasi=ikiz.SahteZamanAsimi('networkidle yok'))
        assert gezgin.hatalar == []
        assert 'ağ sessizliğine ulaşılamadı (devam edildi)' in gezgin.asamalar
        assert rapor['gecti'] is True

    def test_ekran_goruntusu_alinamazsa_hata_kaydi_dusulur(self, tmp_path):
        rapor, gezgin, _ = gez(
            'liquid', tmp_path,
            ekran_goruntusu_hatasi=OSError('disk dolu'))
        assert any('tam sayfa görüntüsü alınamadı' in h for h in gezgin.hatalar)
        assert rapor['ekran_goruntuleri']['tam_sayfa'] is None
        assert rapor['ekran_goruntuleri']['tam_sayfa_px'] is None
        assert denetim(rapor, 'akis_tamam')['gecti'] is False

    def test_yerlesim_olcumu_patlarsa_hukum_fail_closed(self, tmp_path):
        rapor, gezgin, _ = gez(
            'liquid', tmp_path,
            js_hatalari={'JS_YERLESIM': RuntimeError('ölçüm patladı')})
        assert gezgin.hatalar == [], 'yerleşim istisnası akışı KESMEMELİ'
        assert 'RuntimeError' in rapor['olcumler']['yerlesim']['hata']
        assert denetim(rapor, 'yerlesim_yatay_tasma')['gecti'] is False

    def test_bozuk_tuval_veri_urlu_sayi_uydurtmaz(self, tmp_path):
        rapor, gezgin, _ = gez(
            'liquid', tmp_path,
            js_cevaplari={'JS_TUVAL': {'kaynak': 'MotorViz3D.snapshot()',
                                       'hata': 'bağlam kayboldu'}})
        assert gezgin.hatalar == []
        assert rapor['ekran_goruntuleri']['uc_boyut'] is None
        assert rapor['olcumler']['tuval_hatasi'] == 'bağlam kayboldu'
        assert denetim(rapor, 'tuval_dolu')['gecti'] is False


# ===========================================================================
# D. 3B sahne kurulumu ve yanma başlatma
# ===========================================================================

class TestSahneVeYanma:

    def test_sahne_kendiliginden_kurulmazsa_acma_dugmesi_denenir(self, tmp_path):
        secici = 'button[onclick="show3DVisualization()"]'
        durumlar = iter([False, True])
        rapor, gezgin, sahte = gez(
            'solid', tmp_path,
            js_cevaplari={'JS_SAHNE_KURULDU': lambda arg: next(durumlar, True)},
            secici_sayilari={secici: 1}, gorunurluk={secici: True})
        assert ('click', secici) in sahte.gunluk
        assert '3B açma düğmesine basıldı: %s' % secici in gezgin.asamalar
        assert '3B sahne kuruldu' in gezgin.asamalar

    def test_acma_dugmesi_tiklanamazsa_asamaya_yazilir(self, tmp_path):
        secici = 'button[onclick="show3DVisualization()"]'
        rapor, gezgin, _ = gez(
            'solid', tmp_path,
            js_cevaplari={'JS_SAHNE_KURULDU': False},
            secici_sayilari={secici: 1}, gorunurluk={secici: True},
            tiklama_hatalari={secici: RuntimeError('öğe kayboldu')})
        assert any('3B açma düğmesi tıklanamadı' in a for a in gezgin.asamalar)
        assert '3B sahne KURULMADI' in gezgin.asamalar

    def test_sahne_hic_kurulmazsa_kurulmadi_yazilir(self, tmp_path):
        _, gezgin, _ = gez(
            'liquid', tmp_path, js_cevaplari={'JS_SAHNE_KURULDU': False})
        assert '3B sahne KURULMADI' in gezgin.asamalar

    def test_yanma_ui_dugmesi_yoksa_apiye_dusulur(self, tmp_path):
        viz = dict(ikiz.canli_olcumler('liquid')['viz'])
        sonmus = dict(viz, oynatiliyor=False)
        cevaplar = iter([sonmus, viz])
        rapor, gezgin, _ = gez(
            'liquid', tmp_path,
            js_cevaplari={'JS_VIZ_DURUMU': lambda arg: next(cevaplar, viz)},
            secici_sayilari={'button.viz-play': 0})
        assert rapor['olcumler']['plume_baslatma'] == 'api'
        assert 'yanma MotorViz3D.play() ile başlatıldı' in gezgin.asamalar

    def test_olcumden_once_sonen_yanma_yeniden_baslatilir(self, tmp_path):
        """Zamanlama kusuru KUSUR sayılmaz: bir kez daha başlatılıp ölçülür."""
        viz = dict(ikiz.canli_olcumler('liquid')['viz'])
        sonmus = dict(viz, oynatiliyor=False)
        # 1) _yanmayi_baslat okuması (oynuyor), 2) gez() okuması (sönmüş),
        # 3) yeniden başlatma sonrası okuma (oynuyor).
        cevaplar = iter([viz, sonmus, viz])
        _, gezgin, _ = gez(
            'liquid', tmp_path,
            js_cevaplari={'JS_VIZ_DURUMU': lambda arg: next(cevaplar, viz)})
        assert 'yanma sönmüştü, yeniden başlatıldı' in gezgin.asamalar

    def test_yanma_dugmesi_patlarsa_asamaya_yazilir(self, tmp_path):
        _, gezgin, _ = gez(
            'liquid', tmp_path,
            tiklama_hatalari={'button.viz-play': RuntimeError('öğe gitti')})
        assert any('yanma düğmesi tıklanamadı' in a for a in gezgin.asamalar)


# ===========================================================================
# E. FEA panelleri
# ===========================================================================

class TestFeaPanelleri:

    def test_panel_yoksa_asama_panel_yok(self, tmp_path):
        rapor, gezgin, _ = gez(
            'liquid', tmp_path,
            js_cevaplari={'JS_FEA_PANEL_DURUMU': {'panel_var': False}})
        olcum = rapor['olcumler']['fea']['yapisal']
        assert olcum['asama'] == 'panel_yok'
        assert 'FEA paneli yok: #feaPanel' in gezgin.asamalar

    def test_panel_gorunmezse_asama_panel_gorunmez(self, tmp_path):
        rapor, gezgin, _ = gez(
            'liquid', tmp_path,
            js_cevaplari={'JS_FEA_PANEL_DURUMU': {'panel_var': True,
                                                  'panel_gorunur': False}})
        assert rapor['olcumler']['fea']['yapisal']['asama'] == 'panel_gorunmez'

    def test_kosum_dugmesi_yoksa_asama_dugme_yok(self, tmp_path):
        rapor, gezgin, _ = gez(
            'liquid', tmp_path, secici_sayilari={'#fea_run': 0})
        assert rapor['olcumler']['fea']['yapisal']['asama'] == 'dugme_yok'
        assert 'FEA koşum düğmesi yok: #fea_run' in gezgin.asamalar

    def test_kosum_zaman_asiminda_olcum_yine_yayimlanir(self, tmp_path):
        rapor, gezgin, _ = gez(
            'liquid', tmp_path,
            bekleme_hatalari={'JS_FEA_BITTI': ikiz.SahteZamanAsimi('bitmedi')})
        olcum = rapor['olcumler']['fea']['yapisal']
        assert olcum['asama'] == 'zaman_asimi'
        assert any('zaman aşımına uğradı' in a for a in gezgin.asamalar)

    def test_mesgul_gostergesi_gorulmezse_baslamadi_yazilir(self, tmp_path):
        rapor, gezgin, _ = gez(
            'liquid', tmp_path,
            bekleme_hatalari={'JS_FEA_MESGUL': ikiz.SahteZamanAsimi('yok')})
        assert rapor['olcumler']['fea']['yapisal']['basladi'] is False
        assert 'FEA meşgul göstergesi görülmedi (yapisal)' in gezgin.asamalar

    def test_bir_panel_patlasa_digeri_olculur(self, tmp_path):
        """Hibritte termal panel patlarsa yapısal panelin ölçümü elde kalır."""
        gercek = ikiz.canli_olcumler('hybrid')['fea']

        def cevap(arg):
            if arg['panel'] == 'thermalFeaPanel':
                raise RuntimeError('panel çöktü')
            return dict(gercek['yapisal'])

        rapor, gezgin, _ = gez(
            'hybrid', tmp_path, js_cevaplari={'JS_FEA_PANEL_DURUMU': cevap})
        fea = rapor['olcumler']['fea']
        assert fea['termal']['asama'] == 'olcum_hatasi'
        assert 'RuntimeError' in fea['termal']['ayrinti']
        assert fea['yapisal'].get('yuk_var') is True
        assert any('FEA paneli ölçülemedi (termal)' in a for a in gezgin.asamalar)

    def test_yapilandirma_sozlugu_tanimdan_uretilir(self, tmp_path):
        """JS gövdesi hiçbir panelin kimliğini KENDİ içinde bilmez."""
        _, _, sahte = gez('liquid', tmp_path)
        cagrilar = [a for ad, a in sahte.evaluate_cagrilari
                    if ad == 'JS_FEA_PANEL_DURUMU']
        assert cagrilar, 'FEA panel durumu hiç ölçülmedi'
        tanim = sayfalar.SAYFALAR['liquid'].fea_panelleri[0]
        assert cagrilar[0] == {
            'panel': tanim.panel_kimligi, 'api': tanim.api_adi,
            'mesgul': tanim.mesgul_kimligi, 'cip': tanim.cip_kimligi,
            'rozet': tanim.rozet_kimligi,
            'cizimler': list(tanim.cizim_kimlikleri),
            'min_kenar': esikler.FEA_CIZIM_MIN_KENAR_PX,
        }


# ===========================================================================
# F. Analiz Merkezi
# ===========================================================================

class TestAnalizMerkezi:

    def test_merkezsiz_sayfada_merkez_blogu_bos(self, tmp_path):
        rapor, _, sahte = gez('index', tmp_path,
                              js_cevaplari={'JS_SAYFA_METNI': 'HRMA'})
        assert rapor['olcumler']['merkez'] == {}
        assert 'JS_MERKEZ_CERCEVE' not in sahte.betik_sirasi()

    def test_cerceve_olculemezse_fail_closed_kalir(self, tmp_path):
        rapor, gezgin, _ = gez(
            'liquid', tmp_path,
            js_hatalari={'JS_MERKEZ_CERCEVE': RuntimeError('panel gitti')})
        cerceve = rapor['olcumler']['merkez']['cerceve']
        assert cerceve['panel_var'] is None
        assert 'RuntimeError' in cerceve['olcum_hatasi']
        assert any('Analiz Merkezi ölçülemedi' in a for a in gezgin.asamalar)
        assert denetim(rapor, 'merkez_cerceve')['gecti'] is False

    def test_satir_agacta_yoksa_asama_satir_yok(self, tmp_path):
        cerceve = dict(ikiz.canli_olcumler('liquid')['merkez']['cerceve'])
        cerceve['satirlar'] = [s for s in cerceve['satirlar']
                               if s['anahtar'] != 'nozzle_flow.cfd']
        rapor, gezgin, _ = gez('liquid', tmp_path,
                               js_cevaplari={'JS_MERKEZ_CERCEVE': cerceve})
        kiraci = rapor['olcumler']['merkez']['kiracilar']['cfd']
        assert kiraci['asama'] == 'satir_yok'
        assert 'Merkez satırı ağaçta yok: nozzle_flow.cfd' in gezgin.asamalar

    def test_satir_hazir_degilse_kosum_denenmez(self, tmp_path):
        cerceve = dict(ikiz.canli_olcumler('liquid')['merkez']['cerceve'])
        cerceve['satirlar'] = [
            dict(s, durum='blocked', neden='motor sonucu yok')
            if s['anahtar'] == 'nozzle_flow.cfd' else s
            for s in cerceve['satirlar']]
        rapor, gezgin, sahte = gez('liquid', tmp_path,
                                   js_cevaplari={'JS_MERKEZ_CERCEVE': cerceve})
        kiraci = rapor['olcumler']['merkez']['kiracilar']['cfd']
        assert kiraci['asama'] == 'satir_hazir_degil'
        assert kiraci['satir_nedeni'] == 'motor sonucu yok'
        assert ('click', '#ac_row_nozzle_flow_cfd') not in sahte.gunluk

    def test_kosum_dugmesi_kurulmazsa_asama_dugme_yok(self, tmp_path):
        rapor, gezgin, _ = gez(
            'liquid', tmp_path,
            bekleme_hatalari={'#ac_run': ikiz.SahteZamanAsimi('kurulmadı')})
        kiraci = rapor['olcumler']['merkez']['kiracilar']['cfd']
        assert kiraci['asama'] == 'dugme_yok'
        assert 'Merkez koşum düğmesi kurulmadı: #ac_run' in gezgin.asamalar

    def test_kosum_zaman_asiminda_olcum_yayimlanir(self, tmp_path):
        rapor, gezgin, _ = gez(
            'liquid', tmp_path,
            bekleme_hatalari={'JS_MERKEZ_KOSUM_BITTI':
                              ikiz.SahteZamanAsimi('bitmedi')})
        assert rapor['olcumler']['merkez']['kiracilar']['cfd']['asama'] == 'zaman_asimi'

    def test_kiraci_patlasa_cerceve_olcumu_elde_kalir(self, tmp_path):
        rapor, gezgin, _ = gez(
            'liquid', tmp_path,
            js_hatalari={'JS_MERKEZ_KIRACI': RuntimeError('kiracı çöktü')})
        merkez = rapor['olcumler']['merkez']
        assert merkez['cerceve']['panel_var'] is True
        assert merkez['kiracilar']['cfd']['asama'] == 'olcum_hatasi'
        assert any('Merkez kiracısı ölçülemedi (cfd)' in a
                   for a in gezgin.asamalar)

    def test_gecmis_esigi_kosumdan_ONCE_okunur(self, tmp_path):
        """Eşik koşumdan sonra okunsaydı "yeni kayıt" hükmü hep yeşil olurdu."""
        _, _, sahte = gez('liquid', tmp_path)
        sira = [k for k in sahte.gunluk
                if k[0] in ('evaluate', 'click')
                and k[1] in ('JS_MERKEZ_GECMIS_UZUNLUGU', '#ac_run')]
        assert sira[0] == ('evaluate', 'JS_MERKEZ_GECMIS_UZUNLUGU')
        assert sira[1] == ('click', '#ac_run')

    def test_kiraci_yapilandirmasi_kiracidan_uretilir(self, tmp_path):
        """P10B3-03: JS gövdesi hiçbir kiracının alan adını BİLMEZ."""
        _, _, sahte = gez('liquid', tmp_path)
        cfg = [a for ad, a in sahte.evaluate_cagrilari
               if ad == 'JS_MERKEZ_KIRACI'][0]
        kiraci = sayfalar.SAYFALAR['liquid'].merkez_kiracilari[0]
        assert cfg['yuk_anahtari'] == kiraci.yuk_anahtari
        assert cfg['yuk_alanlari'] == [list(a) for a in kiraci.yuk_alanlari]
        assert cfg['cizim_secici'] == kiraci.cizim_secicisi
        assert cfg['kok'] == esikler.MERKEZ_GORUNTULEYICI_KOKU


# ===========================================================================
# G. Olay dinleyicileri (konsol / pageerror / HTTP)
# ===========================================================================

class TestOlayDinleyicileri:

    def test_konsol_ve_sayfa_hatalari_toplanir(self, tmp_path):
        iletiler = [
            ikiz.SahteKonsolIletisi('error', 'Uncaught TypeError: x is null',
                                    {'url': 'app.js', 'lineNumber': 12}),
            ikiz.SahteKonsolIletisi('warning', 'deprecated API'),
        ]
        rapor, gezgin, _ = gez('liquid', tmp_path,
                               konsol_iletileri=iletiler,
                               sayfa_hatalari=[ValueError('patladı')])
        tipler = [k['tip'] for k in gezgin.kayitlar]
        assert tipler == ['error', 'warning', 'pageerror']
        assert gezgin.kayitlar[0]['konum'].startswith('{')
        assert denetim(rapor, 'konsol_temiz')['gecti'] is False

    def test_uzun_konsol_metni_kisaltilir(self, tmp_path):
        uzun = 'x' * 900
        _, gezgin, _ = gez(
            'liquid', tmp_path,
            konsol_iletileri=[ikiz.SahteKonsolIletisi('log', uzun)])
        metin = gezgin.kayitlar[0]['metin']
        assert len(metin) == 401 and metin.endswith('…')

    def test_400_ustu_cevaplar_http_hatasi_sayilir(self, tmp_path):
        cevaplar = [ikiz.SahteCevap(200, '/static/app.js'),
                    ikiz.SahteCevap(404, '/static/yok.js'),
                    ikiz.SahteCevap(500, '/api/patlak')]
        rapor, gezgin, _ = gez('liquid', tmp_path, cevaplar=cevaplar)
        assert rapor['olcumler']['http_hata_sayisi'] == 2
        assert [h['durum'] for h in gezgin.http_hatalari] == [404, 500]

    def test_okunamayan_cevap_turu_kesmez(self, tmp_path):
        """Kapanmış cevabın ``status``'u patlar; tur bunu YUTAR."""
        cevaplar = [ikiz.SahteCevap(500, '/api/x', durum_patlar=True),
                    ikiz.SahteCevap(404, '/api/y')]
        rapor, gezgin, _ = gez('liquid', tmp_path, cevaplar=cevaplar)
        assert gezgin.hatalar == []
        assert rapor['olcumler']['http_hata_sayisi'] == 1


# ===========================================================================
# H. Tarayıcı açılışı ve tur sürücüsü
# ===========================================================================

class TestTarayiciVeSurucu:

    def test_kanal_sirasi_denenir_ve_denemeler_yazilir(self):
        """P17B1-07: paketli Chromium'dan sistem Chrome'una SESSİZ düşüş yok."""
        chromium = ikiz.SahteChromium(
            lambda: ikiz.SahteTarayici(lambda: None),
            acilabilir_kanallar=('chrome',))
        pw = ikiz.SahtePlaywright(chromium)
        tarayici, kullanilan, denemeler = tur._tarayici_ac(pw, 'auto', False)
        assert kullanilan == 'chrome'
        assert [d['kanal'] for d in denemeler] == [tur.PAKETLI_KANAL_ADI, 'chrome']
        assert denemeler[0]['acildi'] is False and denemeler[0]['hata']
        assert denemeler[1]['acildi'] is True and denemeler[1]['hata'] is None

    def test_acik_kanal_istenirse_sira_denenmez(self):
        chromium = ikiz.SahteChromium(lambda: ikiz.SahteTarayici(lambda: None),
                                      acilabilir_kanallar=('msedge',))
        _, kullanilan, denemeler = tur._tarayici_ac(ikiz.SahtePlaywright(chromium),
                                                    'msedge', True)
        assert kullanilan == 'msedge' and len(denemeler) == 1
        assert chromium.denemeler == [{'headless': False, 'channel': 'msedge'}]

    def test_hicbir_kanal_acilmazsa_patlar(self):
        chromium = ikiz.SahteChromium(lambda: ikiz.SahteTarayici(lambda: None),
                                      acilabilir_kanallar=())
        with pytest.raises(RuntimeError) as hata:
            tur._tarayici_ac(ikiz.SahtePlaywright(chromium), 'auto', False)
        for kanal in ('chrome', 'msedge', tur.PAKETLI_KANAL_ADI):
            assert kanal in str(hata.value)

    def test_turu_kos_her_sayfaya_TEMIZ_baglam_acar(self, tmp_path, monkeypatch):
        """Bir sayfanın localStorage devri diğerinin ölçümünü kirletmemeli."""
        uretilen = []

        # ÖH D24 / P17B1-15 — sayfa 'liquid' -> 'solid': bu bekçinin sorusu
        # bağlam temizliği; sıvıda ölçülen acoustic_modes çizim kusuru
        # (bkz. TestCanliTurYenidenOynatimi) hükmü alâkasız yerden
        # kırmızıya çekiyordu.
        def sayfa_uret():
            s = ikiz.SahteSayfa(ikiz.canli_senaryo('solid'))
            uretilen.append(s)
            return s

        tarayici = ikiz.SahteTarayici(sayfa_uret)
        chromium = ikiz.SahteChromium(lambda: tarayici, acilabilir_kanallar=('',))
        import playwright.sync_api as pw_api
        monkeypatch.setattr(pw_api, 'sync_playwright',
                            ikiz.sahte_sync_playwright(chromium))

        tanim = sayfalar.SAYFALAR['solid']
        raporlar, kunye = tur.turu_kos('http://127.0.0.1:5000', [tanim, tanim],
                                       str(tmp_path / 'cikti'))
        assert len(raporlar) == 2 and all(r['gecti'] for r in raporlar)
        assert len(uretilen) == 2
        assert len(tarayici.baglamlar) == 2
        assert all(b.kapandi for b in tarayici.baglamlar)
        assert tarayici.kapandi is True
        assert tarayici.baglamlar[0].acilis == {
            'viewport': esikler.GORUNTU_ALANI, 'locale': esikler.TARAYICI_YERELI}
        assert kunye['kanal'] == tur.PAKETLI_KANAL_ADI
        assert kunye['surum'] == '999.0.0-ikiz'
        assert kunye['istenen_kanal'] == 'auto'
        assert kunye['denemeler'] == [{'kanal': tur.PAKETLI_KANAL_ADI,
                                       'acildi': True, 'hata': None}]

    def test_turu_kos_sayfa_patlasa_da_tarayiciyi_kapatir(self, tmp_path,
                                                          monkeypatch):
        def sayfa_uret():
            raise RuntimeError('bağlam kurulamadı')

        tarayici = ikiz.SahteTarayici(sayfa_uret)
        chromium = ikiz.SahteChromium(lambda: tarayici, acilabilir_kanallar=('',))
        import playwright.sync_api as pw_api
        monkeypatch.setattr(pw_api, 'sync_playwright',
                            ikiz.sahte_sync_playwright(chromium))
        with pytest.raises(RuntimeError):
            tur.turu_kos('http://x', [sayfalar.SAYFALAR['liquid']],
                         str(tmp_path / 'c'))
        assert tarayici.kapandi is True
        assert tarayici.baglamlar[0].kapandi is True


# ===========================================================================
# I. Saf yardımcılar — bozuk veriden ölçüm uydurulmaz
# ===========================================================================

class TestSafYardimcilar:

    def test_png_boyutu_gercek_dosyadan_okunur(self, tmp_path):
        yol = tmp_path / 'x.png'
        yol.write_bytes(ikiz._png_uret(320, 240, (0, 0, 0, 255)))
        assert tur.png_boyutu(str(yol)) == {'genislik': 320, 'yukseklik': 240}

    @pytest.mark.parametrize('govde', [b'', b'not-a-png', b'\x89PNG\r\n\x1a\n' + b'\x00' * 16])
    def test_png_olmayan_dosyadan_boyut_uydurulmaz(self, tmp_path, govde):
        yol = tmp_path / 'bozuk.png'
        yol.write_bytes(govde)
        assert tur.png_boyutu(str(yol)) is None

    def test_olmayan_dosya_none_doner(self, tmp_path):
        assert tur.png_boyutu(str(tmp_path / 'yok.png')) is None

    @pytest.mark.parametrize('girdi', [None, '', 'http://x/y.png',
                                       'data:image/png,abc', 123])
    def test_bozuk_veri_urlundan_bayt_uydurulmaz(self, girdi):
        assert tur.veri_url_baytlari(girdi) is None

    def test_gecerli_veri_urlu_cozulur(self):
        baytlar = tur.veri_url_baytlari(ikiz.veri_url(16, 16, 0.5))
        assert baytlar and baytlar.startswith(b'\x89PNG')


# ===========================================================================
# J. İkizin kendi bekçisi
# ===========================================================================

class TestIkizinSozlesmesi:
    """İkiz sessiz yeşil ÜRETEMEZ."""

    def test_tanimsiz_betik_kirmizi_yakar(self):
        sahte = ikiz.SahteSayfa(ikiz.Senaryo(js_cevaplari={}))
        with pytest.raises(ikiz.BilinmeyenBetik):
            sahte.evaluate('() => 42')

    def test_senaryoda_cevabi_olmayan_betik_kirmizi_yakar(self):
        sahte = ikiz.SahteSayfa(ikiz.Senaryo(js_cevaplari={}))
        with pytest.raises(ikiz.BilinmeyenBetik):
            sahte.evaluate(tur.JS_VIZ_DURUMU)

    def test_canli_tur_raporu_deponun_icinde_ve_okunur(self):
        assert kanit_gerekli(ikiz.CANLI_TUR_RAPORU).is_file(), (
            'ikizin ölçüm kaynağı depoda yok: %s' % ikiz.CANLI_TUR_RAPORU)
        olcum = ikiz.canli_olcumler('liquid')
        assert olcum['viz']['erisim'] == 'motorviz3d'
        assert olcum['merkez']['cerceve']['panel_var'] is True

    def test_turun_her_JS_sabiti_senaryoda_karsiligini_bulur(self):
        """``tur.py``ye yeni bir ``JS_*`` eklenirse bu bekçi kırmızı yanar."""
        senaryo = ikiz.canli_senaryo('hybrid')
        sabitler = {ad for ad in dir(tur) if ad.startswith('JS_')}
        # Bekleme betikleri (``wait_for_function``) cevap tablosuna girmez.
        beklemeler = {'JS_FEA_MESGUL', 'JS_FEA_BITTI', 'JS_MERKEZ_MESGUL',
                      'JS_MERKEZ_KOSUM_BITTI'}
        eksik = sabitler - beklemeler - set(senaryo.js_cevaplari)
        assert eksik == set(), 'senaryoda karşılığı olmayan betik: %s' % eksik


# ===========================================================================
# K. Kalan dallar — ölçüm katmanının SESSİZ köşeleri
# ===========================================================================

class TestKalanDallar:
    """Kapsam ölçümünün gösterdiği son karanlık dallar.

    Her biri "kusur burada görünmeden geçebilir" köşesiydi: sıfır boyutlu
    PNG, çözülemeyen base64, tıklanamayan açma düğmesi, ölçülemeyen viz
    durumu, kurulmayan Merkez satırı. Hiçbiri turu KESMEMELİ ama hiçbiri
    de sessizce YEŞİL olmamalı.
    """

    def test_sifir_boyutlu_ihdr_olcum_uydurtmaz(self, tmp_path):
        ham = bytearray(ikiz._png_uret(8, 8, (0, 0, 0, 255)))
        ham[16:24] = b'\x00' * 8  # IHDR genişlik/yükseklik = 0
        yol = tmp_path / 'sifir.png'
        yol.write_bytes(bytes(ham))
        assert tur.png_boyutu(str(yol)) is None

    def test_cozulemeyen_base64_govdesi_none_doner(self):
        assert tur.veri_url_baytlari('data:image/png;base64,A') is None
        assert tur.veri_url_baytlari('data:image/png;base64,') is None

    def test_gorunmeyen_acma_dugmesi_atlanir(self, tmp_path):
        secici = 'button[onclick="show3DVisualization()"]'
        _, gezgin, sahte = gez(
            'solid', tmp_path,
            js_cevaplari={'JS_SAHNE_KURULDU': False},
            secici_sayilari={secici: 1}, gorunurluk={secici: False})
        assert ('click', secici) not in sahte.gunluk
        assert '3B sahne KURULMADI' in gezgin.asamalar

    def test_acma_dugmesine_basildi_ama_sahne_kurulmadi(self, tmp_path):
        """Düğmeye basıldı, sahne yine kurulmadı — sessiz yeşil YASAK."""
        secici = 'button[onclick="show3DVisualization()"]'
        _, gezgin, sahte = gez(
            'solid', tmp_path,
            js_cevaplari={'JS_SAHNE_KURULDU': False},
            secici_sayilari={secici: 1}, gorunurluk={secici: True},
            bekleme_hatalari={'JS_SAHNE_KURULDU':
                              ikiz.SahteZamanAsimi('kurulmadı')})
        assert ('click', secici) in sahte.gunluk
        assert '3B açma düğmesine basıldı: %s' % secici in gezgin.asamalar
        assert '3B sahne kuruldu' not in gezgin.asamalar
        assert '3B sahne KURULMADI' in gezgin.asamalar

    def test_gorunmeyen_yanma_dugmesi_atlanip_apiye_dusulur(self, tmp_path):
        viz = dict(ikiz.canli_olcumler('liquid')['viz'])
        cevaplar = iter([dict(viz, oynatiliyor=False), viz])
        rapor, gezgin, sahte = gez(
            'liquid', tmp_path,
            js_cevaplari={'JS_VIZ_DURUMU': lambda arg: next(cevaplar, viz)},
            secici_sayilari={'button.viz-play': 2},
            gorunurluk={'button.viz-play': False,
                        'button.viz-play#1': False})
        assert ('click', 'button.viz-play') not in sahte.gunluk
        assert ('click', 'button.viz-play#1') not in sahte.gunluk
        assert not any('yanma düğmesine basıldı' in a for a in gezgin.asamalar)
        assert rapor['olcumler']['plume_baslatma'] == 'api'

    def test_viz_durumu_olculemezse_yanma_baslatilamadi_yazilir(self, tmp_path):
        rapor, gezgin, _ = gez(
            'liquid', tmp_path,
            js_hatalari={'JS_VIZ_DURUMU': RuntimeError('bağlam gitti')})
        assert any('yanma başlatılamadı' in a for a in gezgin.asamalar)
        # Gezinti gövdesindeki ikinci okuma da patlar → akış KESİLİR.
        assert any('RuntimeError' in h for h in gezgin.hatalar)
        assert denetim(rapor, 'akis_tamam')['gecti'] is False

    def test_yanma_yalniz_gezde_dirilirse_yol_api_olur(self, tmp_path):
        """``_yanmayi_baslat`` 'yok' dönmüşse, gez()'deki diriltme 'api' yazar."""
        viz = dict(ikiz.canli_olcumler('liquid')['viz'])
        # 1) _yanmayi_baslat: oynuyor → API'ye düşülmez, yol='yok'
        # 2) gez(): sönmüş → JS_OYNAT → 3) yeniden ölçüm: oynuyor
        cevaplar = iter([viz, dict(viz, oynatiliyor=False), viz])
        rapor, gezgin, _ = gez(
            'liquid', tmp_path,
            js_cevaplari={'JS_VIZ_DURUMU': lambda arg: next(cevaplar, viz)},
            secici_sayilari={'button.viz-play': 0})
        assert rapor['olcumler']['plume_baslatma'] == 'api'
        assert 'yanma sönmüştü, yeniden başlatıldı' in gezgin.asamalar

    def test_merkezsiz_tanimda_merkez_olcumu_hic_kosmaz(self, tmp_path):
        import dataclasses
        tanim = dataclasses.replace(sayfalar.SAYFALAR['liquid'],
                                    merkez_var=False)
        sahte = ikiz.SahteSayfa(ikiz.canli_senaryo('liquid'))
        gezgin = tur.SayfaGezgini(sahte, 'http://x', tanim, str(tmp_path))
        assert gezgin._merkezi_kostur() == {}
        assert sahte.betik_sirasi() == []

    def test_merkez_satir_dugmesi_yoksa_asama_satir_yok(self, tmp_path):
        rapor, gezgin, sahte = gez(
            'liquid', tmp_path,
            secici_sayilari={'#ac_row_nozzle_flow_cfd': 0})
        kiraci = rapor['olcumler']['merkez']['kiracilar']['cfd']
        assert kiraci['asama'] == 'satir_yok'
        assert ('click', '#ac_row_nozzle_flow_cfd') not in sahte.gunluk

    def test_merkez_mesgul_gostergesi_gorulmezse_baslamadi_kalir(self, tmp_path):
        rapor, gezgin, _ = gez(
            'liquid', tmp_path,
            bekleme_hatalari={'JS_MERKEZ_MESGUL':
                              ikiz.SahteZamanAsimi('görünmedi')})
        kiraci = rapor['olcumler']['merkez']['kiracilar']['cfd']
        assert kiraci['basladi'] is False
        assert 'Merkez meşgul göstergesi görülmedi (cfd)' in gezgin.asamalar
