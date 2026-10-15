"""ÖH Faz 0 — görsel kapı genişlemesinin MUTASYON KANITLI bekçileri.

P17 savcısının ölçtüğü boşluk: turun taban ayırt ediciliği 87 mutasyonda
%8,0 idi — hüküm rozetini SİLMEK, sayısını BOZMAK ve YEŞİLE çevirmek
turdan geçiyordu (P17B1-20). Reçete: hüküm imzaları (Kural B) + rozet⟷yük
çaprazı (Kural D, fail-closed) + yerleşim denetimleri (yatay taşma
P17B1-19 + metin örtüşmesi).

Defter kuralı (P14): bir bekçi, kusuru gördüğü MUTASYONLA gösterilmedikçe
"var" sayılmaz. Bu dosya tam olarak o gösterimdir: her kural için
(a) sağlıklı ölçüm GEÇER, (b) kusur mutasyonu KALIR, (c) dürüst değişim
(yük ve ekran birlikte değişir) YAKALANMAZ — savcının kontrol-grubu deseni
(raw/P17/S1-olcum-04.py: 29 dürüst değişimde 0 yanlış alarm).

Tarayıcı AÇILMAZ: girdiler elle kurulmuş ölçüm sözlükleridir.
"""

from __future__ import annotations

import copy
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.browser_harness import denetimler, esikler, sayfalar  # noqa: E402

from tests.test_browser_harness_fea import (  # noqa: E402
    rozet, tane_olcum, termal_olcum, yapisal_olcum,
)
from tests.test_browser_harness_merkez import yerlesim_olcumu  # noqa: E402


def capraz(panel_adi, olcum):
    return denetimler.fea_yuk_caprazi_denetimi(panel_adi, olcum)


# ---------------------------------------------------------------------------
# 1. Rozet ⟷ yük çaprazı — sağlıklı taban
# ---------------------------------------------------------------------------

class TestCaprazTaban:

    def test_uc_panelde_de_saglikli_olcum_gecer(self):
        for panel_adi, olcum in (('yapisal', yapisal_olcum()),
                                 ('termal', termal_olcum()),
                                 ('tane', tane_olcum())):
            hukum = capraz(panel_adi, olcum)
            assert hukum is not None and hukum.gecti, (panel_adi, hukum.ozet)

    def test_yuk_yokken_denetim_uretilmez(self):
        """Hayalet kırmızı yasağı: yük yoksa kök zaten koşumda kırmızı."""
        assert capraz('yapisal', yapisal_olcum(yuk_var=False)) is None
        assert capraz('tane', None) is None

    def test_yuk_icerigi_kaydedilmemisse_fail_closed(self):
        """Kanal var kapı yok desenine izin yok: içeriksiz yük = KIRMIZI."""
        olcum = yapisal_olcum()
        del olcum['yuk_ozeti']
        hukum = capraz('yapisal', olcum)
        assert hukum is not None and hukum.gecti is False
        assert 'FAIL-CLOSED' in hukum.ozet

    def test_hukum_turetilemeyen_icerik_fail_closed(self):
        """Süzgeçten geçen ama HÜKÜM taşımayan içerik = KIRMIZI.

        ÖH D18 / altyapi (P17B1-20 ŞART) — FİKSTÜR GÜNCELLENDİ, iddia
        değişmedi: eski fikstür ``{'mesh_info': {'n_elems': 1024}}``
        kullanıyordu, çünkü o gün ağ boyu bir beklenti ÜRETMİYORDU. Artık
        üretiyor (ekrandaki `MESH n elements / m nodes` sayıları yükle
        çaprazlanıyor), yani o girdi "hüküm türetilemeyen içerik" örneği
        olmaktan çıktı. Örnek, süzgeçten geçen ama hiçbir rozete
        bağlanmayan bir bloğa taşındı; sınanan davranış aynı.
        """
        hukum = capraz('yapisal', yapisal_olcum(
            yuk_ozeti={'limits': {'max_elements': 20000}}))
        assert hukum is not None and hukum.gecti is False
        assert 'FAIL-CLOSED' in hukum.ozet


# ---------------------------------------------------------------------------
# 2. Rozet ⟷ yük çaprazı — P17'nin üç mutasyon kipi (savcı S1-olcum-03/-04)
# ---------------------------------------------------------------------------

class TestCaprazMutasyonlari:
    """Taban turdan GEÇEN üç kip artık geçemez: sil / sayı boz / yeşile çevir."""

    def _rozetsiz(self, olcum, cekirdek):
        kopya = copy.deepcopy(olcum)
        kopya['rozetler'] = [r for r in kopya['rozetler']
                             if cekirdek not in r['metin']]
        kopya['rozet_sayisi'] = len(kopya['rozetler'])
        return kopya

    def _degistir(self, olcum, cekirdek, **alanlar):
        kopya = copy.deepcopy(olcum)
        for r in kopya['rozetler']:
            if cekirdek in r['metin']:
                r.update(alanlar)
        return kopya

    # -- SİL: P17B1-20 "rozeti TAMAMEN silmek de geçiyor" ------------------
    def test_sf_rozetini_silmek_yakalanir(self):
        hukum = capraz('yapisal',
                       self._rozetsiz(yapisal_olcum(), 'MIN SAFETY FACTOR'))
        assert hukum.gecti is False
        assert 'YÜKTE VAR EKRANDA YOK' in hukum.ozet

    def test_erime_hukmunu_silmek_yakalanir(self):
        hukum = capraz('termal',
                       self._rozetsiz(termal_olcum(), 'EXCEEDS MELTING POINT'))
        assert hukum.gecti is False

    def test_gerinim_marjini_silmek_yakalanir(self):
        hukum = capraz('tane',
                       self._rozetsiz(tane_olcum(), 'STRAIN MARGIN'))
        assert hukum.gecti is False

    # -- SAYI BOZ: taban turda 0/19 yakalanıyordu --------------------------
    def test_sf_sayisini_bozmak_yakalanir(self):
        hukum = capraz('yapisal', self._degistir(
            yapisal_olcum(), 'MIN SAFETY FACTOR',
            metin='MIN SAFETY FACTOR 0.12 (Gauss points)'))
        assert hukum.gecti is False
        assert 'SAYI yükle tutmuyor' in hukum.ozet

    def test_tepe_sicakligi_bozmak_yakalanir(self):
        hukum = capraz('termal', self._degistir(
            termal_olcum(), 'PEAK WALL T',
            metin='PEAK WALL T 459 K at t = 10.00 s'))
        assert hukum.gecti is False

    # -- YEŞİLE ÇEVİR: taban turda 0/22 yakalanıyordu ----------------------
    def test_erime_hukmunu_yesile_cevirmek_yakalanir(self):
        hukum = capraz('termal', self._degistir(
            termal_olcum(), 'EXCEEDS MELTING POINT', tur='ok'))
        assert hukum.gecti is False
        assert 'RENK yükle tutmuyor' in hukum.ozet

    def test_kirmizi_sf_yesile_cevrilemez(self):
        """SF 0,85'lik dürüst kırmızı yük, ekranda 'ok' rozetiyle örtülemez."""
        olcum = yapisal_olcum()
        olcum['yuk_ozeti']['scalars']['min_safety_factor'] = 0.85
        olcum = self._degistir(olcum, 'MIN SAFETY FACTOR',
                               metin='MIN SAFETY FACTOR 0.85 (Gauss points)',
                               tur='ok')
        hukum = capraz('yapisal', olcum)
        assert hukum.gecti is False
        assert 'RENK yükle tutmuyor' in hukum.ozet

    # -- DÜRÜST DEĞİŞİM: yakalanmamalı (yanlış alarm 0/29 sözleşmesi) ------
    def test_durust_kirmizi_yakalanmaz(self):
        """Fizik kötüleşti, panel DOĞRU basıyor: yük ve ekran birlikte."""
        olcum = yapisal_olcum()
        olcum['yuk_ozeti']['scalars']['min_safety_factor'] = 0.85
        # ÖH D18 (P17B1-20 ŞART): yük ve ekran BİRLİKTE değişmeli. Eskiden
        # yalnız `converged` çevriliyor, rozet metnine ise 11 tur / %8,20
        # yazılıyordu; yük hâlâ 3 tur / %0,55 diyordu. Çapraz tur sayısını
        # sormadığı için bu tutarsızlık görünmüyordu — testin adı "dürüst
        # kırmızı" olduğu hâlde fikstür dürüst DEĞİLDİ. Artık yük de aynı
        # koşumun sayılarını taşıyor.
        olcum['yuk_ozeti']['convergence'].update(
            converged=False, rounds=11, final_rel_change_pct=8.20)
        for r in olcum['rozetler']:
            if 'MIN SAFETY FACTOR' in r['metin']:
                r['metin'] = 'MIN SAFETY FACTOR 0.85 (Gauss points)'
                r['tur'] = 'err'
            if 'CONVERGED' in r['metin']:
                r['metin'] = 'NOT CONVERGED after 11 rounds (last change 8.20%)'
                r['tur'] = 'warn'
        hukum = capraz('yapisal', olcum)
        assert hukum.gecti is True, hukum.ozet

    def test_durust_sinir_icinde_hali_yakalanmaz(self):
        olcum = termal_olcum()
        olcum['yuk_ozeti']['scalars']['peak_wall_T_K'] = 431.0
        olcum['yuk_ozeti']['material_limits'].update(
            exceeds_melting=False, exceeds_allowable=False)
        olcum['rozetler'] = [
            rozet('ENGINE: HYBRID'),
            rozet('MESH 64 elements / 85 nodes'),
            rozet('PEAK WALL T 431 K at t = 10.00 s'),
            rozet('WITHIN ALLOWABLE 1073 K', 'ok'),
            # ÖH D18 (P17B1-20 ŞART): yükte `energy.residual_rel` DURUYOR,
            # dolayısıyla ekranda da durmalı. Eski liste bu rozeti düşürüyor
            # ama yükten silmiyordu; çapraz enerji artığını sormadığı için
            # "yükte var ekranda yok" kaçıyordu.
            rozet('ENERGY RESIDUAL 4.6e-15 (relative)'),
            rozet('TIME STEP CONVERGED', 'ok'),
        ]
        olcum['rozet_sayisi'] = len(olcum['rozetler'])
        hukum = capraz('termal', olcum)
        assert hukum.gecti is True, hukum.ozet


# ---------------------------------------------------------------------------
# 3. Kural B — hüküm imzaları artık beklenen-imza (silme imza katmanında da
#    yakalanır; çapraz devre dışıyken bile)
# ---------------------------------------------------------------------------

class TestHukumImzalari:

    def test_sf_hukmu_beklenen_imzalarda(self):
        assert 'sf_hukmu' in sayfalar.YAPISAL_FEA.beklenen_imzalar
        assert 'termal_sinir_hukmu' in sayfalar.TERMAL_FEA.beklenen_imzalar
        assert 'tane_gerinim_marji_hukmu' in sayfalar.TANE_FEA.beklenen_imzalar

    def test_sf_rozeti_silinince_imza_denetimi_de_kalir(self):
        olcum = yapisal_olcum()
        olcum['rozetler'] = [r for r in olcum['rozetler']
                             if 'MIN SAFETY FACTOR' not in r['metin']]
        hukum = denetimler.fea_rozet_denetimi(
            'yapisal', olcum, sayfalar.YAPISAL_FEA.beklenen_imzalar)
        assert hukum.gecti is False

    def test_yayimlanmadi_beyani_da_imzayi_tatmin_eder(self):
        """Dürüst 'yayımlanmadı' hâli aile imzasını taşır — yanlış alarm yok."""
        olcum = yapisal_olcum()
        for r in olcum['rozetler']:
            if 'MIN SAFETY FACTOR' in r['metin']:
                r['metin'] = ('SAFETY FACTOR NOT PUBLISHED (no yield strength '
                              'in the material record)')
                r['tur'] = 'dim'
        hukum = denetimler.fea_rozet_denetimi(
            'yapisal', olcum, sayfalar.YAPISAL_FEA.beklenen_imzalar)
        assert hukum.gecti is True, hukum.ozet


# ---------------------------------------------------------------------------
# 4. Yerleşim — yatay taşma (P17B1-19) + metin örtüşmesi
# ---------------------------------------------------------------------------

class TestYerlesim:

    def test_saglikli_yerlesim_gecer(self):
        for hukum in denetimler.yerlesim_denetimleri(yerlesim_olcumu()):
            assert hukum.gecti, hukum.ozet

    def test_olculen_282_px_tasma_yakalanir(self):
        """P17B1-19'un ölçtüğü gerçek vaka artık kırmızı."""
        hukum = denetimler.yerlesim_tasma_denetimi(yerlesim_olcumu(
            yatay_tasma_px=282, belge_genisligi=1882))
        assert hukum.gecti is False
        assert '282 px' in hukum.ozet

    def test_tolerans_alti_tasma_gecer(self):
        hukum = denetimler.yerlesim_tasma_denetimi(yerlesim_olcumu(
            yatay_tasma_px=esikler.YATAY_TASMA_TOLERANS_PX))
        assert hukum.gecti is True

    def test_ortusme_yakalanir_ve_ornek_yazilir(self):
        hukum = denetimler.yerlesim_ortusme_denetimi(yerlesim_olcumu(
            ortusmeler=[{'a': 'Min SF 1,69', 'b': 'UNSAFE — HIGH risk',
                         'alan': 480, 'konum': [412, 1180]}]))
        assert hukum.gecti is False
        assert 'Min SF 1,69' in hukum.ozet
        assert 'UNSAFE' in hukum.ozet

    def test_olcum_yoksa_fail_closed(self):
        for hukum in denetimler.yerlesim_denetimleri(None):
            assert hukum.gecti is False
            assert 'FAIL-CLOSED' in hukum.ozet

    def test_js_hatasi_fail_closed(self):
        for hukum in denetimler.yerlesim_denetimleri({'hata': 'ReferenceError'}):
            assert hukum.gecti is False

    def test_kirpilmis_tarama_ozete_yazilir(self):
        """Kırpılan tarama sessiz kalamaz: sayı alt sınırdır, rapor söyler."""
        hukum = denetimler.yerlesim_ortusme_denetimi(yerlesim_olcumu(
            yaprak_sayisi=esikler.ORTUSME_TARAMA_UST_SINIRI, kirpildi=True))
        assert hukum.gecti is True
        assert 'KIRPILDI' in hukum.ozet
