"""``tools/browser_harness/`` — iskelenin KENDİSİNİN bekçileri.

Neden bu dosya var
------------------
Tarayıcı denetim iskelesi bir kapıya bağlanacak. Kapıya bağlanan bir aracın
en tehlikeli hâli, kusuru göremediği hâlde "geçti" demesidir: o andan sonra
yeşil rapor, denetimin yapıldığının değil YAPILMADIĞININ kanıtı olur.

Bu yüzden iskele iki parçaya ayrıldı:

* ``tur.py``        tarayıcıyı sürer, yalnız ÖLÇER;
* ``denetimler.py`` ölçümden HÜKÜM üretir, tarayıcı gerektirmez.

Buradaki testler ikinci parçayı — yani hükmü — tarayıcı açmadan sınar.
Sınanan şey uygulamanın davranışı DEĞİL, iskelenin doğru hüküm verip
vermediğidir. Bu ayrım bilinçli: iskelenin testi, uygulamanın bugünkü
kusurlarını kilitlememelidir.

Ölçülen dayanak (gerçek tur, Chrome 150.0.7871.188)
---------------------------------------------------
İskele aynı gün, 27 dakika arayla iki kez koşturuldu. Aradaki tek fark
katı motorun nozul çıkış verisinin sahneye bağlanmasıydı:

    tur   zaman (UTC)          sayfa    doluluk / entropi   egzoz çizim aralığı
    1     2026-08-03T21:11Z    hybrid   %18,79 / 3,07 bit   900  (_plumeInfo var)
    1     2026-08-03T21:11Z    solid    %40,86 / 3,15 bit     0  (_plumeInfo YOK)
    1     2026-08-03T21:11Z    liquid   %46,62 / 3,70 bit   900  (_plumeInfo var)
    2     2026-08-03T21:38Z    solid    %42,26 / 3,28 bit   900  (_plumeInfo var)

Yani iskele önce katıdaki kusuru raporladı ("egzoz çizilmiyor: çözücünün
nozul çıkış durumu sahneye ulaşmamış"), onarımdan sonra aynı sayfayı
geçirdi. Aradaki farkı gören şey ``drawRange.count``tur.

Bu dosyadaki sentetik girdiler o iki ölçümün sadeleştirilmiş hâlidir.
Test hiçbir uygulama kusurunu KİLİTLEMEZ; kilitlediği şey şudur: **çizim
aralığı 0 iken iskele KALDI demek ve gerekçeyi yazmak zorundadır.**
"""

from __future__ import annotations

import io
import json
import os
import pathlib
import re
import sys

import numpy as np
import pytest
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.browser_harness import (  # noqa: E402
    denetimler, esikler, run_tour, sayfalar, sunucu, tur,
)


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------

def png_baytlari(dizi: np.ndarray) -> bytes:
    """RGBA dizisini PNG baytlarına çevirir (tarayıcının verdiği biçim)."""
    tampon = io.BytesIO()
    Image.fromarray(dizi, 'RGBA').save(tampon, format='PNG')
    return tampon.getvalue()


def bos_tuval(kenar: int = 120) -> bytes:
    """Hiçbir şey çizilmemiş WebGL tuvali: her piksel alfa = 0."""
    return png_baytlari(np.zeros((kenar, kenar, 4), dtype=np.uint8))


def cizili_tuval(kenar: int = 120, tohum: int = 7) -> bytes:
    """Gölgeli/ayrıntılı bir çizim: dolu oran yüksek, entropi yüksek."""
    uretec = np.random.default_rng(tohum)
    dizi = np.zeros((kenar, kenar, 4), dtype=np.uint8)
    ic = slice(kenar // 6, kenar - kenar // 6)
    dizi[ic, ic, :3] = uretec.integers(0, 256, (kenar - 2 * (kenar // 6),
                                                kenar - 2 * (kenar // 6), 3),
                                       dtype=np.uint8)
    dizi[ic, ic, 3] = 255
    return png_baytlari(dizi)


def duz_blok_tuvali(kenar: int = 120, renk=(70, 70, 70)) -> bytes:
    """Yer tutucu: tuvalin çoğu dolu ama TEK renk — entropi sıfır."""
    dizi = np.zeros((kenar, kenar, 4), dtype=np.uint8)
    dizi[5:-5, 5:-5, :3] = renk
    dizi[5:-5, 5:-5, 3] = 255
    return png_baytlari(dizi)


def viz_olcumu(**degisiklikler):
    """``tur.JS_VIZ_DURUMU``nun döndürdüğü sözlüğün sağlıklı hâli."""
    temel = {
        'erisim': 'motorviz3d', 'webgl_destegi': True,
        'plume_nesnesi_var': True, 'plume_gorunur': True,
        'cizim_araligi': 900, 'partikul_tavani': 900,
        'plume_bilgisi_var': True, 'genisleme_durumu': 'ideal',
        'cikis_hizi_ms': 1882.6, 'elmas_araligi_mm': 134.1,
        'nozul_cikisi_var': True, 'oynatiliyor': True, 'plume_acik': True,
        'sanal_zaman': 1.2, 'yanma_suresi': 10,
    }
    temel.update(degisiklikler)
    return temel


# ---------------------------------------------------------------------------
# 1. Piksel ölçümü ve tuval hükmü
# ---------------------------------------------------------------------------

class TestTuvalDenetimi:
    """Boş tuvalle dolu tuvali ayırt edebiliyor muyuz?"""

    def test_bos_tuval_sifir_doluluk_verir(self):
        olcum = denetimler.piksel_olcumu(bos_tuval())
        assert olcum['dolu_piksel'] == 0
        assert olcum['dolu_oran'] == 0.0
        assert olcum['icerik_entropi_bit'] == 0.0

    def test_bos_tuval_denetimi_kalir(self):
        hukum = denetimler.tuval_denetimi(denetimler.piksel_olcumu(bos_tuval()))
        assert hukum.gecti is False
        assert 'BOŞ' in hukum.ozet

    def test_cizili_tuval_gecer(self):
        olcum = denetimler.piksel_olcumu(cizili_tuval())
        assert olcum['dolu_oran'] > esikler.TUVAL_MIN_DOLU_ORAN
        assert olcum['icerik_entropi_bit'] > esikler.TUVAL_MIN_ICERIK_ENTROPI_BIT
        assert denetimler.tuval_denetimi(olcum).gecti is True

    def test_duz_renkli_yer_tutucu_kalir(self):
        """Doluluk tek başına yetmemeli: düz blok "çizim" sayılmaz."""
        olcum = denetimler.piksel_olcumu(duz_blok_tuvali())
        assert olcum['dolu_oran'] > esikler.TUVAL_MIN_DOLU_ORAN  # tuval dolu
        assert olcum['icerik_entropi_bit'] < esikler.TUVAL_MIN_ICERIK_ENTROPI_BIT
        hukum = denetimler.tuval_denetimi(olcum)
        assert hukum.gecti is False
        assert 'DÜZ' in hukum.ozet

    def test_opak_tuvalde_arkaplan_baskin_renkten_cikarilir(self):
        """Alfa kanalı işe yaramadığında (Plotly yedeği) doluluk yine ölçülür."""
        kenar = 120
        dizi = np.zeros((kenar, kenar, 4), dtype=np.uint8)
        dizi[:, :, :3] = (17, 17, 34)          # opak arka plan
        dizi[:, :, 3] = 255
        uretec = np.random.default_rng(3)
        dizi[40:80, 40:80, :3] = uretec.integers(0, 256, (40, 40, 3), dtype=np.uint8)
        olcum = denetimler.piksel_olcumu(png_baytlari(dizi))
        assert olcum['arkaplan_rengi'] == [17, 17, 34]
        # 40x40 / 120x120 = %11,1 — kuantalama payıyla birlikte %10'un üstünde
        assert olcum['dolu_oran'] > 0.10
        assert denetimler.tuval_denetimi(olcum).gecti is True

    def test_olcum_alinamadiysa_denetim_kalir(self):
        """Ölçülemeyen şey "geçti" sayılamaz — sessiz yeşil rapor yasak."""
        for girdi in (None, b'', b'bu bir PNG degil'):
            olcum = denetimler.piksel_olcumu(girdi)
            assert 'hata' in olcum
            assert denetimler.tuval_denetimi(olcum).gecti is False

    def test_olcumun_her_alani_dayanak_beyan_eder(self):
        olcum = denetimler.piksel_olcumu(cizili_tuval())
        assert set(olcum['_dayanak']) >= {
            'dolu_oran', 'icerik_entropi_bit', 'parlak_oran'}
        assert all(olcum['_dayanak'].values())


# ---------------------------------------------------------------------------
# 2. Egzoz (plume) hükmü
# ---------------------------------------------------------------------------

class TestPlumeDenetimi:
    """Egzoz çizim aralığı hükmü — iskelenin en kritik kararı."""

    def test_cizim_araligi_varsa_gecer(self):
        hukum = denetimler.plume_denetimi(viz_olcumu(cizim_araligi=900))
        assert hukum.gecti is True
        assert hukum.kesinlik == 'dogrudan'
        assert 'drawRange' in hukum.dayanak

    def test_tek_parcacik_bile_gecer(self):
        assert denetimler.plume_denetimi(viz_olcumu(cizim_araligi=1)).gecti is True

    def test_cizim_araligi_sifirsa_kalir(self):
        """Aralık 0 = egzoz HİÇ çizilmiyor. Gerekçesi ne olursa olsun KALIR."""
        hukum = denetimler.plume_denetimi(
            viz_olcumu(cizim_araligi=0, plume_gorunur=False))
        assert hukum.gecti is False

    def test_nozul_cikisi_yoksa_gerekce_yazilir(self):
        """1. turda katı motorda ÖLÇÜLEN durum: ``_plumeInfo`` yok, aralık 0.

        Çizimin atlanması uydurma alev yasağının bilinçli sonucudur, ama
        kullanıcı ekranda egzoz görmüyorsa denetim KALMALI ve gerekçe
        "çözücünün nozul çıkış durumu ulaşmamış" olarak yazılmalıdır.
        (2. turda aynı sayfa onarılıp geçti; bu test o onarımdan
        etkilenmez — sınadığı şey iskelenin hükmüdür.)
        """
        hukum = denetimler.plume_denetimi(viz_olcumu(
            cizim_araligi=0, plume_gorunur=False, plume_bilgisi_var=False,
            genisleme_durumu=None, cikis_hizi_ms=None, elmas_araligi_mm=None,
            nozul_cikisi_var=False))
        assert hukum.gecti is False
        assert 'nozul çıkış durumu' in hukum.ozet
        assert hukum.kesinlik == 'dogrudan'

    def test_yanma_duraklamissa_gerekce_ayrisir(self):
        hukum = denetimler.plume_denetimi(viz_olcumu(
            cizim_araligi=0, plume_gorunur=False, oynatiliyor=False))
        assert hukum.gecti is False
        assert 'duraklat' in hukum.ozet

    def test_plume_anahtari_kapaliysa_gerekce_ayrisir(self):
        hukum = denetimler.plume_denetimi(viz_olcumu(
            cizim_araligi=0, plume_gorunur=False, plume_acik=False))
        assert hukum.gecti is False
        assert 'anahtar' in hukum.ozet

    def test_sahne_kurulmadiysa_vekil_olcut_dolayli_isaretlenir(self):
        piksel = denetimler.piksel_olcumu(cizili_tuval())
        hukum = denetimler.plume_denetimi({'erisim': 'sahne_kurulmadi'}, piksel)
        assert hukum.kesinlik == 'dolayli'
        assert 'VEKİL' in hukum.ozet

    def test_vekil_olcut_parlak_bolge_yoksa_kalir(self):
        piksel = denetimler.piksel_olcumu(bos_tuval())
        hukum = denetimler.plume_denetimi({'erisim': 'modul_yok'}, piksel)
        assert hukum.gecti is False
        assert hukum.kesinlik == 'dolayli'

    def test_hicbir_olcum_yoksa_kalir(self):
        for viz in (None, {}, {'erisim': 'modul_yok'}):
            assert denetimler.plume_denetimi(viz, None).gecti is False

    def test_aralik_okunamadiysa_kalir(self):
        """Sahne var ama egzoz nesnesi yok: ölçüm None gelir, hüküm KALIR."""
        hukum = denetimler.plume_denetimi(
            viz_olcumu(cizim_araligi=None, plume_nesnesi_var=False))
        assert hukum.gecti is False
        assert 'okunamadı' in hukum.ozet


# ---------------------------------------------------------------------------
# 3. Konsol hükmü
# ---------------------------------------------------------------------------

class TestKonsolDenetimi:

    def test_temiz_konsol_gecer(self):
        kayitlar = [{'tip': 'log', 'metin': 'HRMA hazır'},
                    {'tip': 'info', 'metin': 'i18n yüklendi'}]
        assert denetimler.konsol_denetimi(kayitlar).gecti is True

    def test_hata_kalir(self):
        hukum = denetimler.konsol_denetimi(
            [{'tip': 'error', 'metin': 'Uncaught TypeError: x is not a function'}])
        assert hukum.gecti is False
        assert 'TypeError' in hukum.ozet

    def test_sayfa_hatasi_da_kalir(self):
        hukum = denetimler.konsol_denetimi(
            [{'tip': 'pageerror', 'metin': 'ReferenceError: MotorViz3D yok'}])
        assert hukum.gecti is False

    def test_uyari_kapiyi_kapatmaz_ama_sayilir(self):
        """Ölçülen gerçek uyarı (Chrome 150, /solid): Canvas2D readback notu."""
        hukum = denetimler.konsol_denetimi([{
            'tip': 'warning',
            'metin': 'Canvas2D: Multiple readback operations using getImageData'}])
        assert hukum.gecti is True
        assert hukum.olcum['uyari_sayisi'] == 1

    def test_yoksayilan_desen_gecirir_ama_gizlemez(self):
        hukum = denetimler.konsol_denetimi([{
            'tip': 'error',
            'metin': 'Failed to load resource: /favicon.ico 404 (NOT FOUND)'}])
        assert hukum.gecti is True
        assert hukum.olcum['yoksayilan_sayisi'] == 1
        assert hukum.olcum['hata_sayisi'] == 0

    def test_yoksayma_listesi_kisa_kalir(self):
        """Susturma listesi büyürse denetim anlamını yitirir.

        Bugün tek satır var (site simgesi 404'ü — denetim ortamının
        gürültüsü). Liste büyüyecekse her satırın yanına hangi ekranda
        ölçüldüğü yazılmalı; bu test o kararı bilinçli hâle getirir.
        """
        assert len(esikler.KONSOL_YOKSAY) <= 3


# ---------------------------------------------------------------------------
# 4. Sızıntı taraması
# ---------------------------------------------------------------------------

class TestSizintiDenetimi:

    def test_temiz_metin_gecer(self):
        metin = 'Chamber Pressure 20.0 bar\nSpecific Impulse 185.6 s'
        assert denetimler.sizinti_denetimi(metin).gecti is True

    @pytest.mark.parametrize('metin', [
        'Motor: [object Object] — çıkış',
        'Motor: [OBJECT OBJECT]',
        'Motor: [object   Object]',
    ])
    def test_object_object_yakalanir(self, metin):
        hukum = denetimler.sizinti_denetimi(metin)
        assert hukum.gecti is False
        assert hukum.olcum['desen_sayimlari']['object_object'] >= 1

    def test_undefined_ve_nan_yakalanir(self):
        hukum = denetimler.sizinti_denetimi('Isp: undefined s, Thrust: NaN N')
        assert hukum.gecti is False
        assert hukum.olcum['desen_sayimlari'] == {'undefined': 1, 'nan': 1}

    @pytest.mark.parametrize('metin', [
        'Nanotube composite casing',        # NaN bir kelimenin içinde değil
        'Undefined Terms glossary',         # büyük harfli meşru başlık
        'undefined_field_name',             # alt çizgiyle bitişik
        'sundefined',                       # harfe bitişik
    ])
    def test_yanlis_pozitif_uretmez(self, metin):
        assert denetimler.sizinti_denetimi(metin).gecti is True

    def test_isabetin_baglami_raporlanir(self):
        hukum = denetimler.sizinti_denetimi('Toplam impuls: NaN N·s (hesap yok)')
        ornek = hukum.olcum['ornekler'][0]
        assert ornek['desen'] == 'nan'
        assert 'Toplam impuls' in ornek['baglam']

    def test_metin_okunamadiysa_kalir(self):
        assert denetimler.sizinti_denetimi(None).gecti is False


# ---------------------------------------------------------------------------
# 5. Toplu hüküm ve çıkış kodu
# ---------------------------------------------------------------------------

def sahte_sayfa(ad: str, gecti_listesi):
    liste = [denetimler.Denetim(ad='d%d' % i, gecti=g, ozet='özet',
                                dayanak='sahte ölçüm')
             for i, g in enumerate(gecti_listesi)]
    return {'ad': ad, 'url': 'http://x/%s' % ad,
            'gecti': denetimler.sayfa_hukmu(liste),
            'denetimler': [d.sozluk() for d in liste]}


class TestTopluHukum:

    def test_tum_denetimler_gecerse_sayfa_gecer(self):
        assert denetimler.sayfa_hukmu(
            [denetimler.Denetim('a', True, 'x', 'y'),
             denetimler.Denetim('b', True, 'x', 'y')]) is True

    def test_tek_denetim_kalirsa_sayfa_kalir(self):
        assert denetimler.sayfa_hukmu(
            [denetimler.Denetim('a', True, 'x', 'y'),
             denetimler.Denetim('b', False, 'x', 'y')]) is False

    def test_bos_denetim_listesi_gecmez(self):
        """Hiç denetim üretilmediyse ölçüm yapılamamıştır; yeşil sayılmaz."""
        assert denetimler.sayfa_hukmu([]) is False

    def test_bos_sayfa_listesi_kapiyi_acmaz(self):
        assert denetimler.rapor_hukmu({'sayfalar': []}) is False
        assert denetimler.cikis_kodu({'sayfalar': []}) == 1

    def test_kalan_denetim_cikis_kodunu_bire_cevirir(self):
        rapor = {'sayfalar': [sahte_sayfa('a', [True, True]),
                              sahte_sayfa('b', [True, False])]}
        assert denetimler.cikis_kodu(rapor) == 1

    def test_hepsi_gecerse_cikis_kodu_sifir(self):
        rapor = {'sayfalar': [sahte_sayfa('a', [True]), sahte_sayfa('b', [True])]}
        assert denetimler.cikis_kodu(rapor) == 0


# ---------------------------------------------------------------------------
# 6. Sayfa tanımları uygulamayla uyumlu mu
# ---------------------------------------------------------------------------

class TestSayfaTanimlari:

    def test_sayfa_kumesi_test_envanteriyle_ayni(self):
        """Sayfa eklenip iskeleye yazılmazsa denetim o sayfayı hiç görmez."""
        from tests.support.inventory import PAGES
        assert set(sayfalar.SAYFALAR) == set(PAGES)
        assert set(sayfalar.VARSAYILAN_SIRA) == set(PAGES)

    def test_yollar_uygulamada_gercekten_var(self):
        """``/hybrid`` yolu değişirse tur sessizce 404 gezmesin."""
        from hrma.app import app
        kurallar = {str(k.rule) for k in app.url_map.iter_rules()}
        for tanim in sayfalar.SAYFALAR.values():
            assert tanim.yol in kurallar, tanim.yol

    @pytest.mark.parametrize('sayfa_adi,sablon', [
        ('hybrid', 'advanced.html'),
        ('solid', 'solid.html'),
        ('liquid', 'liquid.html'),
    ])
    def test_hesap_dugmesi_sablonda_var(self, sayfa_adi, sablon):
        """Seçicideki ``onclick`` gerçekten o şablonda mı?

        Düğme adı değişirse tur "hesap düğmesi bulunamadı" diye patlar; bu
        test o kırılmayı tarayıcı açmadan, saniyeler içinde yakalar.
        """
        tanim = sayfalar.SAYFALAR[sayfa_adi]
        eslesme = re.search(r'onclick="([^"]+)"', tanim.hesapla_secici)
        assert eslesme, tanim.hesapla_secici
        metin = (ROOT / 'hrma/templates' / sablon).read_text(encoding='utf-8')
        assert 'onclick="%s"' % eslesme.group(1) in metin

    def test_viz_acma_secicileri_sablonda_var(self):
        sablonlar = {'hybrid': 'advanced.html', 'solid': 'solid.html',
                     'liquid': 'liquid.html'}
        for ad, tanim in sayfalar.SAYFALAR.items():
            if not tanim.viz_acma_secicileri:
                continue
            metin = (ROOT / 'hrma/templates' / sablonlar[ad]).read_text(encoding='utf-8')
            for secici in tanim.viz_acma_secicileri:
                anahtar = secici.lstrip('#') if secici.startswith('#') else \
                    re.search(r'onclick="([^"]+)"', secici).group(1)
                assert anahtar in metin, (ad, secici)

    def test_hibritte_sahne_kendiliginden_kurulur(self):
        """Hibritte açma düğmesi BİLEREK yok — tur yan etki yaratmamalı.

        ``#generateCADBtn`` tam tasarım paketi üretip ``window.open`` ile
        popup açar. Turun ona basmaması, sahnenin sonuç akışında
        kendiliğinden kurulmasına dayanır (``app.js`` -> ``mountMotorViz``).
        O çağrı kaldırılırsa bu dayanak çöker ve test uyarır.
        """
        assert sayfalar.SAYFALAR['hybrid'].viz_acma_secicileri == ()
        metin = (ROOT / 'hrma/static/js/app.js').read_text(encoding='utf-8')
        assert 'mountMotorViz(' in metin

    def test_yanma_dugmesi_sinifi_her_iki_arayuzde_var(self):
        """Yanmayı başlatan ``button.viz-play`` seçicisi tek noktadan çalışır.

        Hibrit sayfası düğmeyi şablonda, katı/sıvı güvertesi
        ``motor_viz_deck.js`` içinde üretir. İkisi de aynı sınıfı
        kullanmazsa tur yanmayı başlatamaz ve egzoz denetimi anlamsızlaşır.
        """
        assert 'class="viz-play"' in (ROOT / 'hrma/templates/advanced.html').read_text(
            encoding='utf-8')
        assert "viz-play" in (ROOT / 'hrma/static/js/motor_viz_deck.js').read_text(
            encoding='utf-8')

    def test_bilinmeyen_sayfa_sessizce_atlanmaz(self):
        with pytest.raises(ValueError):
            sayfalar.sayfalari_coz('hybrid,yok_boyle_bir_sayfa')
        with pytest.raises(ValueError):
            sayfalar.sayfalari_coz('  ')

    def test_liste_sirasi_korunur(self):
        cozum = sayfalar.sayfalari_coz('liquid,hybrid')
        assert [s.ad for s in cozum] == ['liquid', 'hybrid']


# ---------------------------------------------------------------------------
# 7. Ölçüm betikleri ve veri taşıma
# ---------------------------------------------------------------------------

class TestOlcumBetikleri:

    def test_viz_betigi_dogrudan_dayanagi_okur(self):
        """Hüküm ``drawRange``den geliyor; betik onu okumayı bırakırsa fark et."""
        assert 'drawRange' in tur.JS_VIZ_DURUMU
        assert '_plumeInfo' in tur.JS_VIZ_DURUMU
        assert 'nozzleExit' in tur.JS_VIZ_DURUMU

    def test_tuval_betiginde_yer_tutucu_kalmadi(self):
        """Eşik metne gömülüyor; gömme başarısız olursa JS sözdizimi bozulur."""
        assert '__MIN_KENAR__' not in tur.JS_TUVAL
        assert str(esikler.TUVAL_MIN_KENAR_PX) in tur.JS_TUVAL

    def test_tuval_betigi_once_snapshot_dener(self):
        """``snapshot()`` çizip okur; düz ``toDataURL`` boş kare verebilir."""
        assert tur.JS_TUVAL.index('snapshot') < tur.JS_TUVAL.index('toDataURL')

    @pytest.mark.parametrize('girdi', [
        None, '', 'http://example.com/a.png', 'data:image/png,abc',
        'data:image/png;base64,!!!', 12345,
    ])
    def test_bozuk_veri_urlden_olcum_uretilmez(self, girdi):
        assert tur.veri_url_baytlari(girdi) is None

    def test_gecerli_veri_url_cozulur(self):
        baytlar = cizili_tuval(64)
        import base64
        url = 'data:image/png;base64,' + base64.b64encode(baytlar).decode()
        assert tur.veri_url_baytlari(url) == baytlar


# ---------------------------------------------------------------------------
# 8. Sunucu ömrü (süreç başlatmadan)
# ---------------------------------------------------------------------------

class TestSunucuOmru:

    def test_komut_hrma_run_modulunu_cagirir(self):
        assert sunucu.komut() == [sys.executable, '-m', 'hrma.run']
        assert sunucu.komut('/usr/bin/python3')[0] == '/usr/bin/python3'

    def test_ortam_portu_zorlar(self):
        """``HRMA_PORT`` verilmezse ``hrma/run.py`` 8080-8090'ı tarar ve
        iskele hangi porta bağlanıldığını bilemez."""
        ortam = sunucu.ortam(51234, temel={})
        assert ortam['HRMA_PORT'] == '51234'

    def test_ortam_gercek_tarayici_acilmasini_engeller(self):
        """``hrma/run.py`` açılışta ``webbrowser.open`` çağırır (run.py:88).

        Denetim koşusunda kullanıcının ekranına pencere açılmamalı;
        ``BROWSER`` değişkeni zinciri ilk adımda başarıyla bitirir.
        """
        assert sunucu.ortam(51234, temel={})['BROWSER'] == 'echo'

    def test_ortam_depo_kokunu_yola_ekler(self):
        ortam = sunucu.ortam(1, temel={'PYTHONPATH': '/onceki'})
        assert ortam['PYTHONPATH'].startswith(sunucu.DEPO_KOKU)
        assert '/onceki' in ortam['PYTHONPATH']

    def test_depo_koku_dogru_cozulur(self):
        assert os.path.isdir(os.path.join(sunucu.DEPO_KOKU, 'hrma'))
        assert os.path.isfile(os.path.join(sunucu.DEPO_KOKU, 'hrma', 'run.py'))

    def test_saglik_yolu_uygulamada_var(self):
        from hrma.app import app
        kurallar = {str(k.rule) for k in app.url_map.iter_rules()}
        assert sunucu.SAGLIK_YOLU in kurallar

    def test_hazir_mi_yalnizca_200e_evet_der(self):
        class SahteCevap:
            def __init__(self, kod):
                self.status = kod

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

        assert sunucu.hazir_mi('http://x', lambda *a, **k: SahteCevap(200)) is True
        assert sunucu.hazir_mi('http://x', lambda *a, **k: SahteCevap(500)) is False

    def test_ag_hatasi_hazir_degil_demektir(self):
        def patlat(*_a, **_k):
            raise OSError('bağlantı reddedildi')

        assert sunucu.hazir_mi('http://x', patlat) is False


# ---------------------------------------------------------------------------
# 9. Rapor üretimi
# ---------------------------------------------------------------------------

class TestRapor:

    def test_rapor_kalan_denetimleri_listeler(self):
        rapor = run_tour.rapor_olustur(
            'http://127.0.0.1:1', {'kaynak': 'harici'}, {'motor': 'chromium'},
            [sahte_sayfa('hybrid', [True, True]), sahte_sayfa('solid', [True, False])])
        assert rapor['gecti'] is False
        assert rapor['ozet']['gecen_sayfa'] == 1
        assert rapor['ozet']['kalan_denetim_sayisi'] == 1
        assert rapor['ozet']['kalan_denetimler'][0]['sayfa'] == 'solid'

    def test_rapor_esikleri_kendi_icine_yazar(self):
        """Eşik sonradan değişse bile eski rapor doğru yorumlanabilsin."""
        rapor = run_tour.rapor_olustur('http://x', {}, {}, [sahte_sayfa('a', [True])])
        assert rapor['esikler']['TUVAL_MIN_DOLU_ORAN'] == esikler.TUVAL_MIN_DOLU_ORAN
        assert rapor['esikler']['PLUME_MIN_CIZIM_ARALIGI'] == \
            esikler.PLUME_MIN_CIZIM_ARALIGI

    def test_rapor_json_serilesir(self):
        rapor = run_tour.rapor_olustur('http://x', {}, {}, [sahte_sayfa('a', [False])])
        metin = json.dumps(rapor, ensure_ascii=False)
        assert 'kalan_denetimler' in metin

    def test_her_denetim_dayanak_beyan_eder(self):
        """Sahte veri yasağı: hükmü üreten ölçümün kaynağı yazılmak zorunda."""
        uretilenler = [
            denetimler.tuval_denetimi(denetimler.piksel_olcumu(cizili_tuval())),
            denetimler.plume_denetimi(viz_olcumu()),
            denetimler.konsol_denetimi([]),
            denetimler.sizinti_denetimi('temiz'),
        ]
        for hukum in uretilenler:
            sozluk = hukum.sozluk()
            assert sozluk['dayanak'], hukum.ad
            assert sozluk['kesinlik'] in ('dogrudan', 'dolayli')

    def test_ozet_yazimi_kalanlari_gosterir(self):
        rapor = run_tour.rapor_olustur('http://x', {}, {}, [sahte_sayfa('a', [False])])
        akis = io.StringIO()
        run_tour.ozeti_yaz(rapor, akis)
        cikti = akis.getvalue()
        assert 'KAPI KAPALI' in cikti
        assert 'KALDI' in cikti

    def test_varsayilan_argumanlar_uc_sayfayi_gezer(self):
        args = run_tour.argumanlari_coz(['--out', '/tmp/x'])
        assert set(args.pages.split(',')) == set(sayfalar.SAYFALAR)
        assert args.base_url is None
        assert args.channel == 'auto'
        assert args.headed is False

    def test_out_zorunlu(self):
        with pytest.raises(SystemExit):
            run_tour.argumanlari_coz([])

    def test_rapor_adi_sabit(self):
        """Kapıya bağlanan betik bu adı bekler; sessizce değişmesin."""
        assert run_tour.RAPOR_ADI == 'tour_report.json'
