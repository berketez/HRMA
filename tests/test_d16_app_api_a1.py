"""ÖH Dalga-16 / kulvar app-api, aşama 1 — onarım bekçileri.

Her sınıf TEK bir defter kalemini bağlar ve ters-mutasyonla kırmızıya
döndüğü ölçülmüştür (kanıt: docs/scofield/raw/OH/D16/app-api/a1/).

- P10B2-05  CSV başlık parantezindeki birim sessizce atılıyordu:
            ``Thrust (kgf)`` newton sayılıyor, hüküm "excellent" ⟷ "poor"
            arasında dönüyordu.
- P10B2-01  Yayımlanan korelasyon tablosunun in-sample künyesi
            serileştiricide düşüyordu: 27/27 girişi fitin KENDİ kaynak
            verisi olan satır bağımsız doğrulama gibi görünüyordu.
"""

import numpy as np
import pytest

from hrma.validation.user_data_validation import parse_thrust_csv, compare
from hrma.validation import status_report as sr


# ---------------------------------------------------------------------------
# P10B2-05 — birim beyanı iki yoldan da SI'ya çevrilir
# ---------------------------------------------------------------------------
class TestP10B2_05BaslikBirimi:
    """El hesabı çapaları: kgf = 9,80665 N (CGPM 1901 g_n),
    lbf = 4,4482216152605 N (NIST SP 811), kN = 1000 N, ms = 1e-3 s."""

    def test_baslik_parantezindeki_kgf_newtona_cevrilir(self):
        out = parse_thrust_csv("Time (s),Thrust (kgf)\n0,0\n1,100\n2,0\n")
        # 100 kgf = 980,665 N — taban davranışı 100,0 N idi (ölçüldü)
        assert out['thrust'].max() == pytest.approx(980.665, rel=1e-12)
        assert out['units']['thrust']['declared'] == 'kgf'
        assert out['units']['thrust']['factor_applied'] == pytest.approx(
            9.80665, rel=1e-12)
        assert out['units']['thrust']['source'] == 'header'

    def test_baslik_parantezindeki_lbf_newtona_cevrilir(self):
        out = parse_thrust_csv("Time (s),Thrust (lbf)\n0,0\n1,100\n2,0\n")
        assert out['thrust'].max() == pytest.approx(444.82216152605,
                                                    rel=1e-12)

    def test_baslik_parantezindeki_ms_saniyeye_cevrilir(self):
        out = parse_thrust_csv("Time (ms),Thrust (N)\n0,0\n1000,50\n2000,0\n")
        # taban: son zaman 2000,0 "s" idi
        assert out['time'].max() == pytest.approx(2.0, rel=1e-12)
        assert out['units']['time']['declared'] == 'ms'

    def test_birim_satiri_da_ayni_tablodan_cevrilir(self):
        """Aynı bilgi, ikinci yol: ayrı birim satırı. İki yol AYNI sonucu
        vermelidir (taban: satır yolu uyarı basıyor ama çevirmiyordu)."""
        satir = parse_thrust_csv("time;thrust\ns;kgf\n0;0\n1;100\n2;0\n")
        baslik = parse_thrust_csv("Time (s),Thrust (kgf)\n0,0\n1,100\n2,0\n")
        assert np.allclose(satir['thrust'], baslik['thrust'])
        assert satir['units']['thrust']['source'] == 'unit row'

    def test_cevrim_kunyeyle_ve_uyariyla_bildirilir(self):
        out = parse_thrust_csv("Time (s),Thrust (kgf)\n0,0\n1,100\n2,0\n")
        assert any('kgf' in w and 'converted' in w for w in out['warnings'])

    def test_beyansiz_dosya_hic_cevrilmez(self):
        """Fail-closed'un diğer yüzü: beyan YOKSA çarpan da uydurulmaz."""
        out = parse_thrust_csv("time,thrust\n0,0\n1,100\n2,0\n")
        assert out['thrust'].max() == pytest.approx(100.0)
        assert out['units']['thrust']['declared'] is None
        assert out['units']['thrust']['factor_applied'] == 1.0
        assert out['warnings'] == []

    def test_hukum_birim_yuzunden_donmez(self):
        """Kalemin ürün etkisi: 100 kgf'lik gerçek eğri, 980,665 N tepe
        veren tahmine karşı 'excellent' olmalıdır; taban 'poor' diyordu."""
        tahmin = {'time': [0.0, 1.0, 2.0], 'thrust': [0.0, 980.665, 0.0]}
        kgf = compare(
            parse_thrust_csv("Time (s),Thrust (kgf)\n0,0\n1,100\n2,0\n"),
            tahmin)
        si = compare(
            parse_thrust_csv("Time (s),Thrust (N)\n0,0\n1,980.665\n2,0\n"),
            tahmin)
        assert kgf['grade'] == si['grade'] == 'excellent'

    def test_ucta_units_kunyesi_yayimlanir(self):
        """/api/validation/upload-csv gövdesi künyeyi taşır."""
        from hrma.app import app
        app.config['TESTING'] = True
        istemci = app.test_client()
        r = istemci.post('/api/validation/upload-csv',
                         json={'csv_text':
                               "Time (s),Thrust (kgf)\n0,0\n1,100\n2,0\n"})
        assert r.status_code == 200
        govde = r.get_json()
        birimler = govde['parsed']['units']
        assert birimler['thrust']['declared'] == 'kgf'
        assert birimler['thrust']['factor_applied'] == pytest.approx(9.80665)
        assert max(govde['parsed']['thrust']) == pytest.approx(980.665)


# ---------------------------------------------------------------------------
# P10B2-01 — bağımlılık künyesi yayımlanan yola taşınır
# ---------------------------------------------------------------------------
def _sentetik_hucre(**ek):
    hucre = {
        "motor_type": "solid", "quantity": "burn_rate",
        "n": 27, "n_campaigns": 2, "n_in_sample": 27,
        "n_weak_evidence": 0, "n_with_measurement_u": 0,
        "median_measurement_u_pct": None,
        "median_abs_normalized_error": None,
        "bias_pct": -0.4, "rms_pct": 2.0, "median_ape_pct": 0.51,
        "mape_pct": 0.6,
        "min": {"error_pct": -2.0, "test_id": "sol-a"},
        "max": {"error_pct": 1.0, "test_id": "sol-b"},
    }
    hucre.update(ek)
    return hucre


def _sentetik_sonuc(hucreler):
    return {
        "runner_version": "t", "adapter_version": "t",
        "db_content_hash": "deadbeef", "n_records": 27,
        "status_counts": {"ok": 27},
        "records": [],
        "statistics": {"cells": hucreler, "low_confidence_cells": [],
                       "anomaly_entries": []},
    }


class TestP10B2_01BagimlilikKunyesi:
    def test_duz_hucre_in_sample_sayisini_tasir(self):
        (duz,) = sr.correlation_cells(
            _sentetik_sonuc([_sentetik_hucre()])["statistics"])
        # taban: düz hücre 9 anahtar taşıyordu, n_in_sample YOKTU (ölçüldü)
        assert duz["n_in_sample"] == 27
        assert duz["n_campaigns"] == 2
        assert "27/27 in-sample" in duz["dependence"]

    def test_yayimlanan_tablo_dependence_sutunu_tasir(self):
        bolum = sr.generate_status_section(
            _sentetik_sonuc([_sentetik_hucre()]), generated_on="2026-01-01")
        # taban: 'in-sample' yayımlanan bölümde HİÇ geçmiyordu (ölçüldü)
        assert "Dependence" in bolum
        assert "27/27 in-sample" in bolum

    def test_kunye_metni_correlation_runner_ile_ayni_kaynaktan(self):
        """TEK KAYNAK: künye cümlesi ikinci kez yazılmaz."""
        from hrma.validation.correlation_runner import _dependence_label
        hucre = _sentetik_hucre()
        (duz,) = sr.correlation_cells(
            _sentetik_sonuc([hucre])["statistics"])
        assert duz["dependence"] == _dependence_label(hucre)

    def test_bagimsiz_hucrede_kunye_tire_kalir(self):
        """Bayrak taşımayan hücrede uydurma künye basılmaz."""
        (duz,) = sr.correlation_cells(
            _sentetik_sonuc([_sentetik_hucre(n_in_sample=0)])["statistics"])
        assert duz["dependence"] == "-"

    def test_sutun_sayisi_basligla_satirda_esit(self):
        bolum = sr.generate_status_section(
            _sentetik_sonuc([_sentetik_hucre()]), generated_on="2026-01-01")
        satirlar = [s for s in bolum.splitlines() if s.startswith("|")]
        assert len(satirlar) >= 3
        genisilikler = {s.count("|") for s in satirlar}
        assert len(genisilikler) == 1, satirlar


# ---------------------------------------------------------------------------
# P10B1-08 — görünür viskozite alanı ÖLÇÜLDÜ: canlı (kalem çürütüldü),
# bekçisi yoktu; regresyona karşı burada kilitleniyor.
# ---------------------------------------------------------------------------
class TestP10B1_08ViskoziteAlaniCanli:
    """Defterin iddiası: 50.000 kat aralıkta ``reynolds_number`` bit-aynı.

    ÖH D16 ölçümü (taban 6fde52b, docs/scofield/raw/OH/D16/app-api/a1/
    once_P10B1-08.json): dört viskozitede DÖRT AYRI Reynolds
    (1,65e7 / 8,27e4 / 1,65e4 / 3,31e2) — kusur artık üremiyor; Z1
    ``_resolve_viscosity`` onarımı hem ezmeyi hem künye eksiğini
    (P10B1-09) kapatmış. Bekçi yoktu: bu sınıf odur.
    """

    @staticmethod
    def _tasarim(**kw):
        import contextlib
        import io as _io
        from hrma.utils.injector_design import InjectorDesign
        with contextlib.redirect_stdout(_io.StringIO()):
            d = InjectorDesign(mdot_ox=0.5, chamber_pressure=30.0,
                               oxidizer_type='n2o', **kw)
            return d, d.calculate()

    def test_kullanicinin_viskozitesi_reynoldsa_gecer(self):
        reynolds = []
        for mu in (1e-6, 2e-4, 1e-3, 0.05):
            d, res = self._tasarim(oxidizer_viscosity=mu)
            assert d.mu_ox == pytest.approx(mu, rel=1e-12), (
                'kullanıcının viskozitesi EZİLDİ')
            reynolds.append(res['reynolds_number'])
        # Re = rho*v*d/mu — mu 50.000 kat değişince Re de değişmeli.
        assert len(set(round(r, 6) for r in reynolds)) == 4, reynolds
        assert reynolds[0] / reynolds[-1] == pytest.approx(0.05 / 1e-6,
                                                           rel=1e-9)

    def test_viskozite_kaynagi_kunyeye_yazilir(self):
        _, kullanici = self._tasarim(oxidizer_viscosity=2e-4)
        assert kullanici['viscosity_basis'] == 'user input'
        _, beyansiz = self._tasarim()
        # Beyan yoksa referans tablosu; künye NEREDEN geldiğini söyler.
        assert beyansiz['viscosity_basis'] != 'user input'
        assert 'N2O' in beyansiz['viscosity_basis']


# ---------------------------------------------------------------------------
# P17B1-20 — tur hüküm katmanının mutasyon ayırt ediciliği
#
# Defterin ölçümü (P17 H1, 26 Ağu): 63 mutasyonun 58'i KAÇIYORDU; başlıkta
# ayrıca "SF/CONVERGED rozetlerini SİLMEK de geçiyor" deniyordu.
# ÖH D16 ölçümü (taban 6fde52b, once_P17B1-20.json): 56 mutasyonun 25'i
# yakalanıyor (%44,6) ve HÜKÜM rozetlerinin silinmesi ARTIK GEÇMİYOR —
# ÖH Faz 0'da eklenen `sf_hukmu` / `termal_sinir_hukmu` /
# `tane_gerinim_marji_hukmu` imzaları ile `fea_yuk_caprazi_denetimi`
# bu boşluğu kapatmış.
#
# Bu sınıf o kazanımı KİLİTLER: hüküm taşıyan rozetlerin silinmesi, yeşile
# çevrilmesi ve sayısının bozulması KIRMIZI vermek zorundadır.
#
# ÖH D18 / altyapi a1 (P17B1-20 ŞART) — KALAN BOŞLUK KAPANDI:
# `_capraz_beklentileri` artık BİLGİ rozetlerinin sayılarını da yükten
# türetiyor (flags.counts n/N + eşik, convergence.rounds/pct, acceptance
# rel_change_pct/tol_pct, mesh_info n_elems/n_nodes, energy.residual_rel,
# engine_layout/grain_type kimliği). Aynı süpürme (olcum_p17b1_20.py):
#   ÖNCE  25/56 (%44,6)  →  SONRA 55/56 (%98,2)
#   kip kırılımı: sil 13→22/22, renk 5→15/15, sayı 7→18/19.
# Tek kaçan: `SECTION: BATES · 1/8 slice` sayı mutasyonu — bozulan sayı
# ŞABLON LİTERALİDİR ('1/{n} slice'), yükte karşılığı yoktur; payload⟷ekran
# çaprazı onu yapısal olarak göremez (imzaya bağlamak, ürün
# symmetry_fraction yayımlamadığında YANLIŞ kırmızı verirdi).
#
# Aşağıdaki `test_kalan_bosluk_olculdu` D16'da boşluğun BOYUNU donduruyordu
# (mutasyon GEÇMELİ diyordu); ŞART gereği TERSİNE ÇEVRİLDİ: 512/1024
# mutasyonu artık KIRMIZI vermek zorunda.
# ---------------------------------------------------------------------------
class TestP17B1_20HukumKatmaniMutasyonu:
    @staticmethod
    def _denetle(ad, olcum, panel):
        from tools.browser_harness import denetimler
        sonuc = [denetimler.fea_rozet_denetimi(
            ad, olcum, panel.beklenen_imzalar,
            getattr(panel, 'yasak_imzalar', ()))]
        capraz = denetimler.fea_yuk_caprazi_denetimi(ad, olcum)
        if capraz is not None:
            sonuc.append(capraz)
        return all(d.gecti for d in sonuc)

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

    # (panel, rozet metninde aranan parça) — hüküm TAŞIYAN rozetler
    HUKUM_ROZETLERI = [
        ('yapisal', 'MIN SAFETY FACTOR'),
        ('yapisal', 'CONVERGED in'),
        ('termal', 'EXCEEDS MELTING POINT'),
        ('termal', 'PEAK WALL T'),
        ('tane', 'STRAIN MARGIN'),
    ]

    @pytest.mark.parametrize('panel_adi,parca', HUKUM_ROZETLERI)
    def test_hukum_rozetini_silmek_yakalanir(self, panel_adi, parca):
        import copy
        kurucu, panel = self._panel(panel_adi)
        taban = kurucu()
        assert self._denetle(panel_adi, taban, panel), 'taban yeşil değil'
        idx = [i for i, r in enumerate(taban['rozetler'])
               if parca in r.get('metin', '')]
        assert idx, f'{panel_adi}: {parca!r} rozeti fikstürde yok'
        olcum = copy.deepcopy(taban)
        del olcum['rozetler'][idx[0]]
        olcum['rozet_sayisi'] = len(olcum['rozetler'])
        assert not self._denetle(panel_adi, olcum, panel), (
            f'{panel_adi}/{parca}: hüküm rozetinin SİLİNMESİ turdan geçti')

    @pytest.mark.parametrize('panel_adi,parca', [
        ('termal', 'EXCEEDS MELTING POINT'),
        ('tane', 'STRAIN MARGIN'),
    ])
    def test_hukum_rozetini_yesile_cevirmek_yakalanir(self, panel_adi, parca):
        import copy
        kurucu, panel = self._panel(panel_adi)
        taban = kurucu()
        olcum = copy.deepcopy(taban)
        idx = [i for i, r in enumerate(olcum['rozetler'])
               if parca in r.get('metin', '')]
        assert idx, f'{panel_adi}: {parca!r} rozeti fikstürde yok'
        if olcum['rozetler'][idx[0]].get('tur') == 'ok':
            pytest.skip('rozet zaten yeşil — renk mutasyonu tanımsız')
        olcum['rozetler'][idx[0]]['tur'] = 'ok'
        assert not self._denetle(panel_adi, olcum, panel), (
            f'{panel_adi}/{parca}: kırmızı hükmün YEŞİLE çevrilmesi geçti')

    @pytest.mark.parametrize('panel_adi,parca,bozuk', [
        ('yapisal', 'MIN SAFETY FACTOR',
         'MIN SAFETY FACTOR 0.12 (Gauss points)'),
        ('termal', 'PEAK WALL T', 'PEAK WALL T 305 K at t = 10.00 s'),
    ])
    def test_hukum_sayisini_bozmak_yakalanir(self, panel_adi, parca, bozuk):
        import copy
        kurucu, panel = self._panel(panel_adi)
        olcum = copy.deepcopy(kurucu())
        idx = [i for i, r in enumerate(olcum['rozetler'])
               if parca in r.get('metin', '')]
        assert idx, f'{panel_adi}: {parca!r} rozeti fikstürde yok'
        olcum['rozetler'][idx[0]]['metin'] = bozuk
        assert not self._denetle(panel_adi, olcum, panel), (
            f'{panel_adi}/{parca}: hüküm SAYISININ bozulması geçti '
            '(rozet⟷yük çaprazı bu sayıyı sormuyor)')

    def test_kalan_bosluk_olculdu(self):
        """ÖH D18'de TERSİNE ÇEVRİLDİ (P17B1-20 ŞART).

        D16'da bu iddia boşluğun BOYUNU donduruyordu: "MESH DISTORTION
        sayacını bozmak GEÇİYOR". ŞART o boşluğun kapatılmasını istedi;
        kapatıldı (`denetimler._capraz_beklentileri` → `_kalite_beklentileri`)
        ve iddia tersine çevrildi. Sayaç yükten türetiliyor, dolayısıyla
        512/1024 yazmak KIRMIZI vermek zorunda.

        Tolerans tuzağı da burada kapandı: sayaçlar 'tam' kipiyle sorulur.
        Ondalık toleransıyla (0 basamak → ±0,5) sorulsaydı metindeki
        `scaled Jacobian < 0.5` eşiği "0 bayraklı" beklentisini karşılar,
        mutasyon yine kaçardı.
        """
        import copy
        kurucu, panel = self._panel('yapisal')
        olcum = copy.deepcopy(kurucu())
        assert self._denetle('yapisal', olcum, panel), 'taban yeşil değil'
        idx = [i for i, r in enumerate(olcum['rozetler'])
               if 'MESH DISTORTION' in r.get('metin', '')][0]
        olcum['rozetler'][idx]['metin'] = (
            'MESH DISTORTION (scaled Jacobian < 0.5): 512/1024 flagged')
        assert not self._denetle('yapisal', olcum, panel), (
            'BİLGİ ROZETİ SAYACI ÇAPRAZLANMIYOR: 1024 elemanın 512\'sini '
            'bayraklı göstermek turdan geçti — P17B1-20 gerilemesi')
