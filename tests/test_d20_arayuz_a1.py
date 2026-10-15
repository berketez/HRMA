"""ÖH Dalga-20 · kulvar **arayuz**, aşama 1 — bekçiler.

Kapsanan kalemler:
  * **P17B1-03** — renk dürüstlüğü kuralı dört rozet yolunun HEPSİNDE.
  * **P17B1-05** — turun tek insan-okur kanıtı (tam sayfa PNG) gerçek mi.
  * **P17B1-07** — tur hangi tarayıcıda koştu; sessiz düşüş yasağı.

Her sınıfın başında ÖLÇÜLEN kusur sayıyla yazılıdır; ham ölçüm
``docs/scofield/raw/OH/D20/arayuz/a1/`` altındadır.
"""
from __future__ import annotations

import pathlib
import struct
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / 'tools') not in sys.path:
    sys.path.insert(0, str(ROOT / 'tools'))


# ===========================================================================
# P17B1-03 — RENK DÜRÜSTLÜĞÜ DÖRT ROZET YOLUNDA
# ---------------------------------------------------------------------------
# ÖLÇÜLEN KUSUR (raw/OH/D20/arayuz/a1/once_p17b1_03.json, taban 14acd1d):
# "kabul rengi yalnız oturmuş bir hükme verilebilir" kuralı depoda YAZILI ve
# ÇALIŞIYORDU ama yalnız merkez (CFD) kiracısına bağlıydı; aynı dosyada 250
# satır ötede ``fea_rozet_denetimi`` açıkça "rengi ... hükme girmez" diyordu.
# 9 bozmalık süpürmede (yeşil basılmış olumsuz/eksik beyanlar ve akma altı
# emniyet katsayısı) ÜÇ FEA panelinde yakalama 0/9 = %0,0.
# ONARIM SONRASI (sonra_p17b1_03.json): 9/9 = %100,0; yanlış alarm 0/3.
# ===========================================================================
def esikler_kabul_rengi():
    """Kabul rengi TEK KAYNAKTAN okunur (ÖK-04: sabit iki yere yazılmaz)."""
    from tools.browser_harness import esikler
    return esikler.MERKEZ_KABUL_ROZET_SINIFI


class TestP17B1_03RenkDurustluguDortYolda:

    @staticmethod
    def _panel(ad):
        from tools.browser_harness import sayfalar
        from tests.test_browser_harness_fea import (
            yapisal_olcum, termal_olcum, tane_olcum)
        return {
            'yapisal': (yapisal_olcum, sayfalar.YAPISAL_FEA),
            'termal': (termal_olcum, sayfalar.TERMAL_FEA),
            'tane': (tane_olcum, sayfalar.TANE_FEA),
        }[ad]

    @classmethod
    def _gecti(cls, ad, olcum):
        from tools.browser_harness import denetimler
        _, panel = cls._panel(ad)
        sonuc = [denetimler.fea_rozet_denetimi(
            ad, olcum, panel.beklenen_imzalar,
            getattr(panel, 'yasak_imzalar', ()))]
        capraz = denetimler.fea_yuk_caprazi_denetimi(ad, olcum)
        if capraz is not None:
            sonuc.append(capraz)
        return all(d.gecti for d in sonuc)

    @staticmethod
    def _ekle(olcum, metin, tur):
        from tests.test_browser_harness_fea import rozet
        olcum['rozetler'] = list(olcum['rozetler']) + [rozet(metin, tur)]
        olcum['rozet_sayisi'] = len(olcum['rozetler'])
        return olcum

    def test_temiz_fikstur_ucunde_de_yesil(self):
        """Yanlış-kapanma ikizi: kural sağlıklı ekranı kapatmamalı."""
        for ad in ('yapisal', 'termal', 'tane'):
            kurucu, _ = self._panel(ad)
            assert self._gecti(ad, kurucu()), f'{ad} tabanı kırmızıya döndü'

    #: (panel, ekrana eklenen rozet metni, rengi) — hepsi KABUL rengiyle
    #: basılmış olumsuz/eksik beyan ya da eşik altı hüküm sayısı.
    BOZMALAR = [
        ('yapisal', 'ENGINE’S OWN SAFETY FACTOR 0.87 — the structural run '
                    'reports 14.75x higher because thermal stress and '
                    'strength derating are not modelled here; the lower '
                    'number governs the design', 'ok'),
        ('yapisal', 'SAFETY FACTOR NOT PUBLISHED (no yield strength in the '
                    'material record)', 'ok'),
        ('yapisal', 'CONTOUR UNAVAILABLE — node point map drawn instead', 'ok'),
        ('yapisal', 'MESH DISTORTION NOT PUBLISHED (the response carries no '
                    'scaled Jacobian, so no distortion verdict is issued)',
         'ok'),
        ('tane', 'STRAIN MARGIN 0.42', 'ok'),
        ('tane', 'STRAIN MARGIN NOT PUBLISHED', 'ok'),
        ('termal', 'HEAT TRANSFER NOT VALIDATED against a measured case', 'ok'),
        ('termal', 'NO FILM COEFFICIENT PUBLISHED — adiabatic wall assumed',
         'ok'),
        ('termal', 'EXCEEDS ALLOWABLE 800 K', 'ok'),
    ]

    @pytest.mark.parametrize('ad,metin,tur', BOZMALAR,
                             ids=[f'{b[0]}-{b[1][:28]}' for b in BOZMALAR])
    def test_kabul_rengi_oturmamis_hukme_verilemez(self, ad, metin, tur):
        kurucu, _ = self._panel(ad)
        olcum = self._ekle(kurucu(), metin, tur)
        assert not self._gecti(ad, olcum), (
            f'{ad}: {metin[:60]!r} KABUL rengiyle basıldı ve kapı geçti')

    def test_ayni_rozet_notr_renkle_gecer(self):
        """Kusur RENKTEDİR, beyanın kendisinde değil: aynı cümle nötr
        renkle basıldığında kapı kapanmamalı (aşırı-kapanma ikizi)."""
        kurucu, _ = self._panel('yapisal')
        olcum = self._ekle(kurucu(),
                           'CONTOUR UNAVAILABLE — node point map drawn '
                           'instead', 'dim')
        assert self._gecti('yapisal', olcum), (
            'nötr renkli dürüst beyan kapıyı kapattı — kural aşırı geniş')

    # -- DÖRDÜNCÜ YOL: Merkez/CFD ----------------------------------------
    # ÖH D26 · Fable-D20 ŞARTI. Yukarıdaki bekçiler üç FEA yolunu
    # (yapısal/termal/tane) sınıyordu; kalemin başlığı ise kuralın DÖRT
    # rozet yolundan yalnız birine bağlı olduğunu söylüyordu. Dördüncü yol
    # ``merkez_rozet_denetimi``dir ve ÖLÇÜLDÜ (a4/mutasyon.json,
    # ``M2b_renk_durustlugu_merkez``): denetimin içindeki
    # ``renk_durustlugu_kusurlari(...)`` çağrısı ``[]`` ile değiştirildiğinde
    # bu sınıfın 12 testi de, ``test_browser_harness_merkez.py`` +
    # ``test_gorsel_kapi_faz0.py`` ile birlikte 157 testin tamamı da YEŞİL
    # kalıyordu. Yani dördüncü yolun kapısı bekçisizdi.

    #: Fable ŞARTININ istediği iki rozet: biri "yedeğe düşüldü" beyanı,
    #: biri "yayımlanmadı" beyanı. İkisi de KABUL rengiyle basılamaz.
    MERKEZ_BOZMALARI = (
        ('CONTOUR UNAVAILABLE — node point map drawn instead', 'UNAVAILABLE'),
        ('SAFETY FACTOR NOT PUBLISHED (no yield strength in the material '
         'record)', 'NOT PUBLISHED'),
    )

    @staticmethod
    def _merkez_hukmu(olcum):
        from tools.browser_harness import denetimler, sayfalar
        K = sayfalar.CFD_KIRACISI
        return denetimler.merkez_rozet_denetimi(
            'cfd', olcum, K.beklenen_imzalar, K.yasak_imzalar, K.notr_imzalar)

    @staticmethod
    def _merkez_olcumu(tur_adi):
        """Sağlıklı CFD ölçümü + ŞARTIN istediği iki rozet, verilen renkte."""
        from tests.test_browser_harness_merkez import cfd_olcumu
        from tests.test_browser_harness_merkez import rozet as merkez_rozeti
        olcum = cfd_olcumu()
        olcum['rozetler'] = list(olcum['rozetler']) + [
            merkez_rozeti(metin, tur_adi)
            for metin, _ in TestP17B1_03RenkDurustluguDortYolda.MERKEZ_BOZMALARI]
        olcum['rozet_sayisi'] = len(olcum['rozetler'])
        return olcum

    def test_merkez_cfd_taban_hukmu_yesil(self):
        """Yanlış-kapanma ikizi: dokunulmamış Merkez ölçümü geçmeli."""
        from tests.test_browser_harness_merkez import cfd_olcumu
        hukum = self._merkez_hukmu(cfd_olcumu())
        assert hukum.gecti is True, hukum.ozet

    def test_dorduncu_yol_merkez_cfd_de_bagli(self):
        """ŞART: kabul rengiyle basılan olumsuz beyan Merkez'de de kapatır."""
        hukum = self._merkez_hukmu(self._merkez_olcumu(
            esikler_kabul_rengi()))
        assert hukum.gecti is False, (
            'merkez/cfd yolunda kabul rengiyle basılmış olumsuz beyan '
            'kapıdan geçti: %s' % hukum.ozet)
        assert 'RENK DÜRÜSTLÜĞÜ: merkez/cfd' in hukum.ozet, hukum.ozet
        for _, cekirdek in self.MERKEZ_BOZMALARI:
            assert cekirdek in hukum.ozet, (
                '%r çekirdeği özete yazılmadı: %s' % (cekirdek, hukum.ozet))

    def test_dorduncu_yol_ikizi_notr_renkle_gecer(self):
        """Aşırı-kapanma ikizi: kusur RENKTE, beyanın kendisinde değil."""
        hukum = self._merkez_hukmu(self._merkez_olcumu('dim'))
        assert hukum.gecti is True, (
            'nötr renkli dürüst beyan Merkez kapısını kapattı: %s' % hukum.ozet)

    def test_kural_tek_fonksiyondan_gelir(self):
        """Dört yol AYNI kaynaktan okur (merkez + üç FEA)."""
        from tools.browser_harness import denetimler, esikler
        kusur = denetimler.renk_durustlugu_kusurlari(
            [{'tur': esikler.MERKEZ_KABUL_ROZET_SINIFI,
              'metin': 'NOT CONVERGED after 11 rounds (last change 3.2%)'}],
            'birim')
        assert kusur, 'ortak kural olumsuz beyanı yeşilken yakalamıyor'
        assert not denetimler.renk_durustlugu_kusurlari(
            [{'tur': 'warn',
              'metin': 'NOT CONVERGED after 11 rounds (last change 3.2%)'}],
            'birim')


# ===========================================================================
# P17B1-05 — TAM SAYFA PNG'İ GERÇEK Mİ
# ---------------------------------------------------------------------------
# ÖLÇÜLEN KUSUR (raw/P17/B1-tur-09.py): üç sayfanın PNG'i de Chromium'un
# 16.384 px tek-kare tavanını aşıyordu; 83.478 px'in 34.326 px'i (%41,1) üst
# bandın BİREBİR tekrarıydı (maks piksel farkı 0). Hibritte sayfanın %52,5'i
# hiçbir koşumda görüntülenmemişti. ``tur.py:520-529`` görüntüyü alıp yolunu
# rapora yazıyor, hiçbir denetim YÜKSEKLİĞİNE bakmıyordu (0 denetim).
# ===========================================================================
def _png_yaz(yol, genislik, yukseklik):
    """IHDR başlığı yeterli — ``png_boyutu`` ilk 24 baytı okur."""
    with open(yol, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n')
        f.write(struct.pack('>I', 13) + b'IHDR')
        f.write(struct.pack('>II', genislik, yukseklik))


class TestP17B1_05TamSayfaGoruntusuGercek:

    def test_yukseklik_olculuyor(self, tmp_path):
        from tools.browser_harness import tur
        yol = tmp_path / 'a.png'
        _png_yaz(yol, 1600, 34476)
        assert tur.png_boyutu(str(yol)) == {'genislik': 1600,
                                            'yukseklik': 34476}

    def test_bozuk_dosyadan_olcum_uydurulmaz(self, tmp_path):
        from tools.browser_harness import tur
        yol = tmp_path / 'b.png'
        yol.write_bytes(b'bu bir png degil')
        assert tur.png_boyutu(str(yol)) is None
        assert tur.png_boyutu(str(tmp_path / 'yok.png')) is None

    def test_tavani_asan_goruntu_kapiyi_kapatir(self):
        from tools.browser_harness import denetimler, esikler
        tavan = esikler.CHROMIUM_TEK_KARE_TAVANI_PX
        d = denetimler.tam_sayfa_goruntusu_denetimi(
            {'tam_sayfa': '/x/hybrid_tam.png',
             'tam_sayfa_px': {'genislik': 1600, 'yukseklik': tavan + 1}})
        assert not d.gecti, 'tavanı aşan sahte kanıt kapıdan geçti'
        assert 'SAHTE KANIT' in d.ozet

    def test_tavanin_altindaki_goruntu_gecer(self):
        from tools.browser_harness import denetimler, esikler
        d = denetimler.tam_sayfa_goruntusu_denetimi(
            {'tam_sayfa': '/x/solid_tam.png',
             'tam_sayfa_px': {'genislik': 1600,
                              'yukseklik': esikler.CHROMIUM_TEK_KARE_TAVANI_PX}})
        assert d.gecti, d.ozet

    def test_olculmemis_goruntu_fail_closed(self):
        from tools.browser_harness import denetimler
        for goruntuler in ({}, {'tam_sayfa': None},
                           {'tam_sayfa': '/x/a.png', 'tam_sayfa_px': None}):
            d = denetimler.tam_sayfa_goruntusu_denetimi(goruntuler)
            assert not d.gecti, f'ölçülmeyen kanıt temiz sayıldı: {goruntuler!r}'
            assert 'FAIL-CLOSED' in d.ozet

    def test_denetim_sayfa_hukmune_bagli(self):
        """Kanal var kapı yok deseni yasak: denetim gerçekten koşuyor."""
        import inspect
        from tools.browser_harness import tur
        kaynak = inspect.getsource(tur.SayfaGezgini._rapor)
        assert 'tam_sayfa_goruntusu_denetimi' in kaynak, (
            'denetim sayfa hüküm listesine bağlanmamış')


# ===========================================================================
# P17B1-07 — TUR HANGİ TARAYICIDA KOŞTU
# ---------------------------------------------------------------------------
# ÖLÇÜLEN KUSUR: paketli Chromium hiç açılamıyordu (playwright sürücüsü 1181
# isterken diskte 1208 vardı); tur SESSİZCE sistem Chrome'una düşüyor, künye
# yalnız KAZANAN kanalı taşıyor, özet tarayıcıyı hiç anmıyordu — ve rapor
# hükmü (``rapor_hukmu``) yalnız sayfa listesine bakıyordu, yani tarayıcıyla
# ilgili hiçbir kural kapıyı kapatamıyordu.
# ===========================================================================
class TestP17B1_07TarayiciBeyanEdilir:

    def test_kunye_yoksa_kapi_kapanir(self):
        # ÖH D26 · Fable-D20 ŞARTI — son iki vaka EKLENDİ. Ölçüldü (taban
        # ağacı, a4/once.json ``P17B1_07a``): ``denemeler: []`` ve
        # ``denemeler: None`` künyeleri kapıdan GEÇİYOR ve özete "düşüş yok"
        # yazıyordu. Boş/None kayıt "düşüş olmadı" demek değildir; deneme
        # kaydının hiç TUTULMADIĞI anlamına gelir — fail-closed olmalı.
        from tools.browser_harness import denetimler
        for kunye in (None, {}, {'motor': 'chromium'},
                      {'kanal': 'chrome', 'surum': '1.2'},
                      {'kanal': 'chrome', 'surum': '1.2', 'denemeler': []},
                      {'kanal': 'chrome', 'surum': '1.2', 'denemeler': None}):
            d = denetimler.tarayici_denetimi(kunye)
            assert not d.gecti, f'eksik künye geçti: {kunye!r}'
            assert 'FAIL-CLOSED' in d.ozet

    def test_liste_olmayan_deneme_kaydi_cokertmez(self):
        """Ölçülen yan bulgu: ``denemeler`` liste değilse tur ÇÖKÜYORDU.

        Taban ağacında ``{'denemeler': 'yok'}`` künyesi
        ``AttributeError: 'str' object has no attribute 'get'`` yükseltiyordu
        (a4/once.json ``P17B1_07a``); hüküm katmanı istisna atarsa kapı
        değil TUR ölür. Artık liste olmayan değer eksik alan sayılır.
        """
        from tools.browser_harness import denetimler
        for bozuk in ('yok', {}, 0, 3.14):
            d = denetimler.tarayici_denetimi(
                {'kanal': 'chrome', 'surum': '1.2', 'denemeler': bozuk})
            assert not d.gecti, f'liste olmayan deneme kaydı geçti: {bozuk!r}'
            assert 'denemeler' in d.ozet

    def test_dusus_beyanli_olmak_zorunda(self):
        from tools.browser_harness import denetimler
        d = denetimler.tarayici_denetimi({
            'kanal': 'chrome', 'surum': '141.0',
            'denemeler': [
                {'kanal': '(paketli chromium)', 'acildi': False,
                 'hata': "Executable doesn't exist … chromium-1181"},
                {'kanal': 'chrome', 'acildi': True, 'hata': None}]})
        assert d.gecti, d.ozet
        assert 'BEYANLI DÜŞÜŞ' in d.ozet and 'chromium-1181' in d.ozet

    def test_dussuz_kosum_sade_gecer(self):
        from tools.browser_harness import denetimler
        d = denetimler.tarayici_denetimi({
            'kanal': '(paketli chromium)', 'surum': '141.0',
            'denemeler': [{'kanal': '(paketli chromium)', 'acildi': True,
                           'hata': None}]})
        assert d.gecti and 'düşüş yok' in d.ozet

    def test_rapor_hukmu_rapor_duzeyini_de_okur(self):
        from tools.browser_harness import denetimler
        temel = {'sayfalar': [{'gecti': True}]}
        assert denetimler.rapor_hukmu(temel)
        assert not denetimler.rapor_hukmu(
            dict(temel, denetimler=[{'ad': 'tarayici_kunyesi', 'gecti': False}]))
        assert denetimler.rapor_hukmu(
            dict(temel, denetimler=[{'ad': 'tarayici_kunyesi', 'gecti': True}]))

    def test_acilis_denemeleri_kaydediliyor(self):
        """``_tarayici_ac`` her denemeyi (açıldı/hata) kayda geçirmeli."""
        class _SahteTarayici:
            version = '141.0'

        class _SahteChromium:
            def __init__(self):
                self.cagrilar = []

            def launch(self, **kw):
                self.cagrilar.append(kw)
                if kw.get('channel') != 'chrome':
                    raise RuntimeError("Executable doesn't exist … "
                                       'chromium-1181')
                return _SahteTarayici()

        class _SahtePw:
            def __init__(self):
                self.chromium = _SahteChromium()

        from tools.browser_harness import tur
        pw = _SahtePw()
        tarayici, kullanilan, denemeler = tur._tarayici_ac(pw, None, False)
        assert kullanilan == 'chrome'
        assert [d['acildi'] for d in denemeler] == [False, True]
        assert denemeler[0]['kanal'] == tur.PAKETLI_KANAL_ADI
        assert 'chromium-1181' in denemeler[0]['hata']
        # Sessiz düşüş yok: kayıt denetimden geçince BEYANLI düşüş olur.
        from tools.browser_harness import denetimler
        d = denetimler.tarayici_denetimi(
            {'kanal': kullanilan, 'surum': tarayici.version,
             'denemeler': denemeler})
        assert d.gecti and 'BEYANLI DÜŞÜŞ' in d.ozet

    # -- ÜRETİCİ BAĞI (Fable-D20 ŞARTI, ÖH D26) ---------------------------
    # Yukarıdaki bekçiler hüküm fonksiyonlarını TEK TEK sınıyordu
    # (``tarayici_denetimi``, ``rapor_hukmu``, ``ozeti_yaz``). Raporu
    # ÜRETEN yer ise ``run_tour.rapor_olustur``tur ve orada kopan bir tel
    # hiçbir bekçiye yakalanmıyordu: ÖLÇÜLDÜ (a4/mutasyon.json,
    # ``M4b_rapor_duzeyi_denetim``) — ``'denetimler'`` alanı boş listeye
    # çevrildiğinde bu sınıfın 6 testi de YEŞİL kalıyordu. Yani "kanal var
    # kapı yok" değil, "kapı var ama üreticiye bağlı değil" deseni.

    @staticmethod
    def _sahte_sayfa(ad, gecti_listesi):
        """Sayfa raporu ikizi — hüküm katmanı yalnız bu alanları okur."""
        return {
            'ad': ad, 'url': 'http://127.0.0.1:1/%s' % ad,
            'gecti': all(gecti_listesi),
            'denetimler': [
                {'ad': 'sahte_%d' % i, 'gecti': g, 'ozet': 'ikiz',
                 'kesinlik': 'dogrudan'}
                for i, g in enumerate(gecti_listesi)],
        }

    def test_rapor_olusturucu_tarayici_hukmunu_gercekten_basiyor(self):
        """ŞART: eksik künyeyle üretilen rapor GEÇEMEZ ve nedenini yazar."""
        from tools.browser_harness import run_tour
        rapor = run_tour.rapor_olustur(
            'http://127.0.0.1:1', {'kaynak': 'harici'}, {'motor': 'chromium'},
            [self._sahte_sayfa('hybrid', [True, True])])
        assert rapor['gecti'] is False, (
            'sayfaların hepsi geçti diye rapor da geçti; tarayıcı künyesi '
            'eksik olmasına rağmen kapı açık kaldı')
        assert rapor['denetimler'], 'rapor düzeyi denetim listesi BOŞ'
        assert rapor['denetimler'][0]['ad'] == 'tarayici_kunyesi'
        assert rapor['denetimler'][0]['gecti'] is False
        rapor_satirlari = [k for k in rapor['ozet']['kalan_denetimler']
                           if k.get('sayfa') == '(rapor)']
        assert rapor_satirlari, (
            "kalan denetimler listesinde '(rapor)' satırı yok: %r"
            % rapor['ozet']['kalan_denetimler'])
        assert rapor_satirlari[0]['denetim'] == 'tarayici_kunyesi'
        # Tek kaynak: gövdedeki özet ile kalan listesindeki özet AYNI
        # nesneden gelmeli (ÖH D26 temizliği: hüküm iki kez hesaplanıyordu).
        assert rapor_satirlari[0]['ozet'] == rapor['denetimler'][0]['ozet']

    def test_rapor_olusturucu_saglikli_kunyeyle_gecer(self):
        """Aşırı-kapanma ikizi: künye tamsa rapor düzeyi kapıyı kapatmaz."""
        from tools.browser_harness import run_tour
        rapor = run_tour.rapor_olustur(
            'http://127.0.0.1:1', {'kaynak': 'harici'},
            {'motor': 'chromium', 'kanal': 'chrome', 'surum': '141.0',
             'denemeler': [{'kanal': 'chrome', 'acildi': True, 'hata': None}]},
            [self._sahte_sayfa('hybrid', [True, True])])
        assert rapor['gecti'] is True, rapor['ozet']['kalan_denetimler']
        assert rapor['denetimler'][0]['gecti'] is True
        assert not [k for k in rapor['ozet']['kalan_denetimler']
                    if k.get('sayfa') == '(rapor)']

    def test_ozet_tarayiciyi_aniyor(self):
        """P17'nin ölçtüğü ikinci yarı: insan-okur özet tarayıcıyı anmıyordu."""
        import io as _io
        from tools.browser_harness import run_tour
        akis = _io.StringIO()
        run_tour.ozeti_yaz({
            'temel_url': 'http://127.0.0.1:8080',
            'denetimler': [{'ad': 'tarayici_kunyesi', 'gecti': True,
                            'ozet': 'tarayıcı: chrome 141.0 — BEYANLI DÜŞÜŞ'}],
            'sayfalar': [], 'ozet': {}}, akis=akis)
        metin = akis.getvalue()
        assert 'tarayici_kunyesi' in metin and 'chrome 141.0' in metin
