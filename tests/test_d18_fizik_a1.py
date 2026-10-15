"""ÖH Dalga-18 · fizik kulvarı · aşama 1 — bekçiler.

Kapsam
------
B3-05  Boğaz istasyonu kayan-denge sonik noktadan gelir ve c* süreklilik
       özdeşliği (c* = P_c/(ρ_t v_t), NASA RP-1311 Part I eş. 6.11) AYNI
       YANIT içinde kapanır.
B3-02  Çıkış istasyonu ile çıkış hızı TEK modelden gelir: ε = G_t/G_e
       (süreklilik) ve çıkış durumu oda izentropunun üstündedir; üçlü Isp
       yayını (CEA nfz kipleri) sıralı ve beyanlıdır.

Kaynaklar (docs/scofield/raw/OH/D18/oturum-devri/d18_fizik_literatur.md §2):
  NASA RP-1311 Part I (Gordon & McBride 1994) §6.2.2, §6.2.6 eş. 6.11,
  §6.3.3; RPA v2.3 kullanım kılavuzu s.19; Sutton & Biblarz 9. baskı
  Böl. 5 Tablo 5-5 (kayan denge +%1…4, donmuş −%1…4); MIT 16.512 Ders 14
  (SSME: donmuş 435 s, denge 451 s, vakum 465 s).

Ölçüm dosyaları: docs/scofield/raw/OH/D18/fizik/a1/{once_f1.json,
sonra_f1.json} — onarım öncesi boğaz sapması −%0,95…−%1,37 (T_t),
c* kapanışı −%0,72…−%1,02; çıkış T_e +%0,27…+%28,13, ε kapanışı
−%2,31…+%0,79. Onarım sonrası hepsi ≲1e-5 %.
"""
import math

import pytest

from hrma.engines.combustion_analysis import CombustionAnalyzer
from tests.bagimlilik_kapisi import kapi
from tests.test_combustion_cea_validation import CANTERA_YOLU_KIRIK

# P01 B3-yanma-cea.md ölçüm tablosuyla aynı vakalar.
VAKALAR = [
    ({'htpb': 100.0}, 'n2o', 6.0, 20.0),
    ({'htpb': 100.0}, 'n2o', 8.0, 40.0),
    ({'htpb': 100.0}, 'lox', 2.1, 30.0),
    ({'paraffin': 100.0}, 'n2o', 7.0, 25.0),
    ({'pe': 100.0}, 'lox', 2.4, 50.0),
]
EPSILONLAR = [2.0, 4.0, 8.0, 16.0, 40.0]

# Süreklilik kapanışı ölçütü (D18 planı: |ṁ_boğaz − ṁ_c*| bağıl < 1e-6).
# Ürün yapı gereği makine hassasiyetinde kapatır; eşik onarım ÖNCESİ
# ölçülen −%0,72…−%1,02 açığın 7 000 katı altındadır.
SUREKLILIK_TOL = 1e-6
# ε kapanışı: kesen çözücünün bağıl kapanış ölçütü 1e-10, ölçülen ~1e-9.
EPS_TOL = 1e-6


@pytest.fixture(scope='module')
def analiz():
    ca = CombustionAnalyzer()
    # Bağımlılık kapısı: cantera YOKSA atla, KURULU ama mekanizma zinciri
    # yüklenemiyorsa KIRMIZI — ürün kusuru atlanamaz (test_ci_kapsam_kapisi).
    kapi('cantera', ca.cantera_available, CANTERA_YOLU_KIRIK)
    return ca


def _bogaz_yogunlugu(sonuc):
    """Yayımlanan boğaz basıncı/sıcaklığı ve R_t'den ρ_t [kg/m³]."""
    P_t = sonuc['conditions']['throat']['P'] * 1e5
    T_t = sonuc['conditions']['throat']['T']
    R_t = sonuc['performance']['gas_constants']['throat']
    return P_t / (R_t * T_t)


class TestB305BogazIstasyonu:
    """B3-05 — boğaz kayan-dengeden; c* süreklilik özdeşliği kapanır."""

    @pytest.mark.parametrize('yakit,oks,of,pc', VAKALAR)
    def test_c_star_sureklilik_kapanisi(self, analiz, yakit, oks, of, pc):
        """c*_yayımlanan == P_c/(ρ_t·v_t) — aynı yanıt içinde.

        Onarım öncesi bu özdeşlik −%0,72…−%1,02 açık veriyordu: c* tek-γ
        kapalı formundan, boğaz istasyonu ise BAŞKA bir tek-γ bağıntısından
        geliyordu (P01 B3-05). Şimdi ikisi de tek bir çözülmüş istasyondan
        gelir, dolayısıyla ṁ = P_c A_t/c* ile ṁ = ρ_t v_t A_t özdeştir.
        """
        r = analiz.analyze_combustion(yakit, oks, of, pc)
        perf = r['performance']
        assert r['conditions']['throat']['basis'] == 'shifting_equilibrium'
        assert perf['c_star_basis'] == 'shifting_equilibrium_throat'
        rho_t = _bogaz_yogunlugu(r)
        v_t = perf['velocities']['throat']
        c_star_istasyon = (pc * 1e5) / (rho_t * v_t)
        assert c_star_istasyon == pytest.approx(perf['c_star'],
                                                rel=SUREKLILIK_TOL)

    @pytest.mark.parametrize('yakit,oks,of,pc', VAKALAR)
    def test_bogaz_sonik_denge_noktasi(self, analiz, yakit, oks, of, pc):
        """Boğazda v = a_eq (denge ses hızı) — RP-1311 §6.3.3.

        Tek-γ kritik oranı boğazı 30-50 K SOĞUK, ρ_t'yi %1,4-2,0 YÜKSEK
        veriyordu; sonik koşul o istasyonda sağlanmıyordu.
        """
        r = analiz.analyze_combustion(yakit, oks, of, pc)
        perf = r['performance']
        v_t = perf['velocities']['throat']
        a_t = perf['throat_sound_speed']
        assert a_t > 0.0
        assert abs(v_t / a_t - 1.0) < 1e-4
        # Beyan edilen artık, ölçülen artıkla tutarlı olmalı (uydurma değil).
        assert perf['throat_sonic_residual'] == pytest.approx(
            abs(v_t / a_t - 1.0), abs=1e-9)

    @pytest.mark.parametrize('yakit,oks,of,pc', VAKALAR)
    def test_bogaz_kutle_akisi_maksimumdur(self, analiz, yakit, oks, of, pc):
        """G = ρv boğazda MAKSİMUM (A/A_t minimumu ⇔ u = a).

        Komşu basınçlarda kütle akısı daha büyük olamaz; olsaydı boğaz
        yanlış yerde çözülmüş olurdu.
        """
        r = analiz.analyze_combustion(yakit, oks, of, pc)
        perf = r['performance']
        G_t = perf['throat_mass_flux']
        comp = analiz._elements_to_cantera_composition(
            r['elemental_composition'])
        ist = analiz._solve_equilibrium_throat(
            comp, r['conditions']['chamber']['T'], pc,
            r['conditions']['throat']['P'])
        assert ist is not None
        P_t = ist['bogaz']['P']
        for k in (0.97, 0.99, 1.01, 1.03):
            komsu = analiz._equilibrium_isentrope_state(
                ist['s0'], ist['h0'], P_t * k)
            assert komsu['G'] <= G_t * (1.0 + 1e-9)


class TestB302CikisIstasyonu:
    """B3-02 — ε denge ile boyutlandırılır, çıkış hızıyla aynı modelden."""

    @pytest.mark.parametrize('eps', EPSILONLAR)
    def test_epsilon_sureklilikten_kapanir(self, analiz, eps):
        """ε_istenen == G_t/(ρ_e·v_e) — A_e artık denge ile boyutlanır.

        Onarım öncesi kapanış −%2,31…+%0,79 sapıyordu, çünkü p_e tek-γ
        alan-Mach bağıntısından, v_e ise kayan-dengeden geliyordu.
        """
        r = analiz.analyze_combustion({'htpb': 100.0}, 'n2o', 6.0, 20.0,
                                      expansion_ratio=eps)
        perf = r['performance']
        assert r['conditions']['exit']['basis'] == 'expansion_ratio_equilibrium'
        P_e = r['conditions']['exit']['P'] * 1e5
        T_e = r['conditions']['exit']['T']
        R_e = perf['gas_constants']['exit']
        rho_e = P_e / (R_e * T_e)
        v_e = perf['velocities']['exit']
        eps_hesap = perf['throat_mass_flux'] / (rho_e * v_e)
        assert eps_hesap == pytest.approx(eps, rel=EPS_TOL)

    @pytest.mark.parametrize('eps', EPSILONLAR)
    def test_cikis_istasyonu_oda_izentropunda(self, analiz, eps):
        """Yayımlanan (P_e, T_e) oda izentropunun üstündedir.

        Onarım öncesi T_e tek-γ bağıntısından geliyor ve aynı p_e'deki denge
        sıcaklığından +%0,27…+%28,13 sapıyordu (ε ile büyüyen hata).
        """
        r = analiz.analyze_combustion({'htpb': 100.0}, 'n2o', 6.0, 20.0,
                                      expansion_ratio=eps)
        comp = analiz._elements_to_cantera_composition(
            r['elemental_composition'])
        ist = analiz._solve_equilibrium_throat(
            comp, r['conditions']['chamber']['T'], 20.0,
            r['conditions']['throat']['P'])
        assert ist is not None
        P_e = r['conditions']['exit']['P'] * 1e5
        denge = analiz._equilibrium_isentrope_state(ist['s0'], ist['h0'], P_e)
        assert denge['T'] == pytest.approx(r['conditions']['exit']['T'],
                                           rel=1e-6)
        assert denge['v'] == pytest.approx(
            r['performance']['velocities']['exit'], rel=1e-6)

    @pytest.mark.parametrize('eps', EPSILONLAR)
    def test_uclu_isp_yayini_sirali_ve_beyanli(self, analiz, eps):
        """nfz=1 < nfz=2 < denge; anahtarlar ve künye yerinde.

        Sektör kipleri (CEA): 'frozen_at_chamber' mutlak alt sınır,
        'frozen_at_throat' kötümser referans, 'equilibrium' üst referans.
        Kinetik verim bandı frozen@throat–equilibrium arasıdır.
        """
        r = analiz.analyze_combustion({'htpb': 100.0}, 'n2o', 6.0, 20.0,
                                      expansion_ratio=eps)
        p = r['performance']
        for anahtar in ('isp_equilibrium', 'isp_frozen_throat',
                        'isp_frozen_chamber', 'isp_reference_basis'):
            assert anahtar in p, anahtar
        assert (p['isp_frozen_chamber'] < p['isp_frozen_throat']
                < p['isp_equilibrium'])
        # Eski anahtarlar sektör kiplerine bağlandı (kinetik verim bandı).
        assert p['isp_frozen'] == pytest.approx(p['isp_frozen_throat'],
                                                rel=1e-12)
        assert p['isp_shifting'] == pytest.approx(p['isp_equilibrium'],
                                                  rel=1e-12)
        assert p['isp'] == pytest.approx(p['isp_equilibrium'], rel=1e-12)
        assert 'nfz=2' in p['isp_reference_basis']['isp_frozen']
        assert 'RP-1311' in p['isp_reference_basis']['source']

    def test_denge_donmus_bandi_literatur_zarfinda(self, analiz):
        """(Isp_eq − Isp_nfz2)/Isp_eq literatür zarfında.

        Sutton & Biblarz 9. baskı Tablo 5-5: kayan denge +%1…4, donmuş
        −%1…4 (CSU ders notları üzerinden ikincil aktarım; güven
        orta-yüksek). Ölçülen (htpb/N2O O/F=6 Pc=20 bar):
            ε=2 → %1,29 · ε=4 → %2,00 · ε=8 → %2,46 · ε=16 → %2,81 ·
            ε=40 → %3,21
        Zarf [%0,3; %8] bu bandı rahatça kapsar; dışına çıkması kip
        tanımının bozulduğunu gösterir.
        """
        for eps in EPSILONLAR:
            p = analiz.analyze_combustion(
                {'htpb': 100.0}, 'n2o', 6.0, 20.0,
                expansion_ratio=eps)['performance']
            band = (p['isp_equilibrium'] - p['isp_frozen_throat']) \
                / p['isp_equilibrium']
            assert 0.003 < band < 0.08, (eps, band)

    def test_epsilonsuz_cikis_da_denge_izentropunda(self, analiz):
        """ε verilmese bile çıkış istasyonu tek-γ'dan gelmez.

        Basınç ISA deniz seviyesine çapalı kalır (F034 sözleşmesi), ama
        sıcaklık/hız kayan-denge izentropundan okunur ve bu ``basis`` ile
        beyan edilir.
        """
        r = analiz.analyze_combustion({'htpb': 100.0}, 'n2o', 6.0, 20.0)
        assert r['conditions']['exit']['basis'] == \
            'sea_level_default_equilibrium'
        assert r['conditions']['exit']['P'] == pytest.approx(1.01325,
                                                             rel=1e-9)


class TestIstasyonTabaniBeyani:
    """Denge çözücüsü kullanılamadığında ürün SESSİZCE tek-γ'ya düşmez."""

    def test_cantera_kapaliyken_taban_beyan_edilir(self, analiz):
        ca = CombustionAnalyzer()
        ca.cantera_available = False
        r = ca.analyze_combustion({'htpb': 100.0}, 'n2o', 6.0, 20.0,
                                  expansion_ratio=4.0)
        assert r['conditions']['throat']['basis'] == 'single_gamma_chamber'
        assert r['performance']['c_star_basis'] == 'single_gamma_closed_form'
        assert r['conditions']['exit']['basis'] == 'expansion_ratio'
        # Ampirik yolda üçlü yayın YAPILMAZ (uydurma referans üretilmez).
        assert 'isp_equilibrium' not in r['performance']

    def test_denge_yolunda_izentropik_verim_bir(self, analiz):
        """η_s = 1 — istasyon tablosu artık kendi içinde tutarlı.

        ``_calculate_isentropic_efficiency`` bir DONANIM kaybı değil,
        tablolanan çıkış istasyonunun entropi üretimini ölçer (kendi
        künyesi böyle diyor). Çıkış istasyonu oda izentropunun üstüne
        oturduğu için entropi üretimi sıfırdır ve oran 1 çıkar. Onarım
        öncesi 0,87-0,93 arası değerler, tek-γ istasyonunun kayan-denge
        entalpisiyle karıştırılmasının ARTIĞIYDI.
        """
        for eps in (4.0, 10.0, 25.0, 60.0):
            r = analiz.analyze_combustion({'htpb': 100.0}, 'n2o', 6.0, 20.0,
                                          expansion_ratio=eps)
            eta = r['performance']['thermodynamic_properties'][
                'isentropic_efficiency']
            assert math.isclose(eta, 1.0, rel_tol=1e-6), (eps, eta)
