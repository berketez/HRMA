"""
Yanma (combustion) modülü doğrulama testleri — NASA CEA çapraz-doğrulaması.

Bu dosya CombustionAnalyzer'ın iki yeni özelliğini ve mevcut oda (chamber)
termokimya doğruluğunu (regresyon koruması) doğrular:

  1. c* (yanma) verimi: eta_c_star opsiyonel parametresi. TEORİK c_star
     korunur (anahtar değişmez); c_star_delivered = eta_c_star * c_star_teorik
     ayrı anahtarla raporlanır. Gerçek hibrit motorlarda ölçülen c* verimi
     tipik 0.90-0.97'dir (Chiaverini & Kuo, AIAA Prog. Astro. & Aero. Vol. 218,
     2007, Böl. 1 ve 10; Sutton & Biblarz 9. baskı, Eş. 3-31).

  2. Frozen vs shifting-equilibrium Isp: enerji denklemiyle (v_e =
     sqrt(2*(h0 - h_e)); Sutton & Biblarz 9. baskı Eş. 3-15b; NASA RP-1311
     Part I) hem dondurulmuş (frozen, oda bileşimi) hem yeniden-dengeli
     (shifting) genişleme hesaplanır ve ayrı anahtarlarla raporlanır.

DOĞRULAMA REFERANSI (kritik):
  HRMA Isp'i SADECE çıkış hızına dayanır (v_e/g0, basınç-itki terimi yok).
  Buna karşılık gelen DOĞRU CEA değeri, çıkışın ortam basıncına (P_e=1 bar)
  TAM genişlediği optimum durumdur: RocketCEA estimate_Ambient_Isp(Pamb=P_e).
  Bu sayısal olarak M_çıkış * a_çıkış / g0 'a eşittir.
  DİKKAT: get_Isp(eps) varsayılan VAKUM Isp'i döndürür (sonsuz genişleme
  basınç-itki terimiyle), v_e/g0 ile DOĞRUDAN kıyaslanamaz — bu yaygın hatadır.

TOLERANS GEREKÇESİ:
  Frozen/shifting genişleme MANTIĞI CEA tanımıyla birebir uyumludur. Kalan
  ~%2-3 sapma, oda denge çözümünün c*/T_c belirsizliğinin (gri30 mekanizması
  fuel-rich N2O/HTPB için T_c'yi ~%3.4 düşük verir; c* %0-1.5 doğrulanmış)
  Isp'e taşınmasından gelir; Isp ~ sqrt(T_c) olduğundan -%3.4 T_c ~ -%1.7 Isp
  tabanı yaratır. T_c'yi/Isp'i DÜŞÜK vermek motor boyutlandırmada KONSERVATİF
  (güvenli) yöndür. Bu yüzden mutlak Isp testleri %3.5, oda c*/gamma/T_c
  regresyonu %2.5-3 toleransla denetlenir; MANTIK (frozen<=shifting sıralaması,
  birim tutarlılığı) sıkı denetlenir.

Kaynaklar:
  - NASA RocketCEA (CEA, Gordon & McBride, NASA RP-1311) — bağımsız referans.
  - Sutton & Biblarz, Rocket Propulsion Elements, 9th ed., Böl. 3.
"""

import numpy as np
import pytest

from hrma.engines.combustion_analysis import CombustionAnalyzer
from hrma.constants import G_0
from tests.bagimlilik_kapisi import kapi

# ---------------------------------------------------------------------------
# RocketCEA kapısı — ÜÇ DURUMLU (ÖH FAZ A / A1, defter P13B1-01)
# ---------------------------------------------------------------------------
# ESKİ HÂLİ (yalan gerekçe):
#
#     try:
#         from rocketcea.cea_obj import CEA_Obj
#         ROCKETCEA_AVAILABLE = True
#     except Exception:            # <-- HER hatayı "kurulu değil"e çevirir
#         ROCKETCEA_AVAILABLE = False
#     @pytest.mark.skipif(not ROCKETCEA_AVAILABLE,
#                         reason="RocketCEA kurulu değil; ... atlanıyor.")
#
# Ölçülen kusur (P13/S1-savci §1.4a): rocketcea KURULUYKEN ithal yolu
# bozulduğunda (derlenmiş Fortran uzantısı gitmiş, OSError/RuntimeError)
# ``except Exception`` bunu da yakalıyor ve 31 bekçi "RocketCEA kurulu değil"
# YALANIYLA atlanıyordu. Sabotaj RuntimeError ile de OSError ile de birebir
# aynı sonucu veriyordu (1 failed, 30 passed, 31 skipped) ve tek kırmızı
# KAZA eseriydi (yedek not metninin sözcük seçimi).
#
# YENİ HÂLİ: ``tests/bagimlilik_kapisi.kapi`` üç durumlu sözleşmesi —
#
#     kurulu DEĞİL               -> ATLA   (gerekçe find_spec ile DOĞRULANIR)
#     kurulu + ithal ÇALIŞIYOR   -> KOŞ
#     KURULU ama ithal KIRIK     -> KIRMIZI (atlanamaz; ortam/ürün kusuru)
#
# Kapı, "kurulu mu" sorusunu ithal denemesine DEĞİL importlib.util.find_spec'e
# sorar; ithal denemesi yalnız "yol açık mı" sorusunu yanıtlar.
try:
    from rocketcea.cea_obj import CEA_Obj
    ROCKETCEA_YOLU_ACIK = True
    ROCKETCEA_ITHAL_HATASI = ''
except ImportError as _rc_exc:      # pragma: no cover - ortama bağlı
    # Kurulu değilse de, kurulu ama alt bağımlılığı eksikse de buraya düşer;
    # ikisini AYIRAN merci aşağıdaki kapıdır (find_spec), bu blok değil.
    ROCKETCEA_YOLU_ACIK = False
    ROCKETCEA_ITHAL_HATASI = f'{type(_rc_exc).__name__}: {_rc_exc}'
except Exception as _rc_exc:        # pragma: no cover - ortama bağlı
    # OSError / RuntimeError / ... : bunlar KURULUM sorusunun yanıtı DEĞİLDİR.
    # Eski kapı tam olarak burayı "kurulu değil" diye raporluyordu.
    ROCKETCEA_YOLU_ACIK = False
    ROCKETCEA_ITHAL_HATASI = f'{type(_rc_exc).__name__}: {_rc_exc}'


def _rocketcea_kirik_aciklamasi() -> str:
    return (
        'rocketcea KURULU (dağıtım bulundu) ama '
        '`from rocketcea.cea_obj import CEA_Obj` yüklenemedi:\n'
        f'    {ROCKETCEA_ITHAL_HATASI or "(ithal hatası kaydedilmedi)"}\n'
        'CEA çapraz-doğrulaması bu ortamda KOŞMUYOR. Bu, atlanacak değil '
        'DÜZELTİLECEK bir durumdur (kurulum bozuk: gfortran / derlenmiş CEA '
        'uzantısı). Eskiden bu durum "RocketCEA kurulu değil" gerekçesiyle '
        'SESSİZCE atlanıyordu — ÖH defter P13B1-01, ölçüm: 31 bekçi.')


@pytest.fixture
def cea_kapisi():
    """Üç durumlu rocketcea kapısı (bkz. yukarıdaki blok)."""
    kapi('rocketcea', ROCKETCEA_YOLU_ACIK, _rocketcea_kirik_aciklamasi())


#: CEA gerektiren sınıf/testlerin imi. ``skipif`` DEĞİL: atlama kararını
#: kurulum sorusunu GERÇEKTEN soran kapı verir.
needs_cea = pytest.mark.usefixtures('cea_kapisi')

FT_TO_M = 0.3048           # ft -> m
PSIA_PER_BAR = 14.5037738  # 1 bar -> psia

# --- Referans tasarım vakaları (Pc=20 bar, deniz seviyesi P_e=1 bar) ---
# HRMA tarafı yakıt anahtarı / CEA tarafı yakıt adı eşleşmesi:
#   RP-1, HRMA propellant_specs'inde 'paraffin' (C12H26) ile yaklaşıklanır.
CASES = [
    # (label, ceaOx, ceaFuel, hrmaOx, hrmaFuel, Pc_bar, OF)
    ("N2O/HTPB", "N2O", "HTPB", "N2O", {"htpb": 100.0}, 20.0, 6.0),
    ("LOX/RP-1", "LOX", "RP-1", "LOX", {"paraffin": 100.0}, 20.0, 2.5),
]

ISP_TOL = 3.5    # % — mutlak Isp (oda c* belirsizliği taşınır)
CSTAR_TOL = 2.5  # % — oda c* regresyon koruması (validated %0-1.5 bandı + pay)
TC_TOL = 3.5     # % — oda T_c regresyon koruması
GAMMA_TOL = 2.0  # % — oda shifting-eq gamma regresyon koruması


# Kitap uyum p1a / B16 (ÖNEMLİ, 6 Eki 2026) — KÂHİNİN N₂O GİRİŞ DURUMU.
# HRMA artık N₂O'yu varsayılan giriş durumunda (hibrit
# ``TANK_TEMPERATURE_DEFAULT_K`` = 293,15 K, doymuş SIVI) yakıyor. CEA kâhini
# RocketCEA'nın gaz kartıyla ('N2O', 298,15 K ideal gaz) koşulmaya devam
# etseydi iki yan FARKLI reaktan entalpisiyle karşılaştırılırdı (sıvı
# düzeltmesi −11,23 kJ/mol). Kâhin aynı fiziksel duruma getirildi: kendi gaz
# kartı + CoolProp'tan DOĞRUDAN alınan sıvı düzeltmesi (h_doymuş_sıvı(T) −
# h_ig(298,15 K); h_ig düşük yoğunluk limitinden — ürünün
# ``hrma/engines/oxidizer_inlet.py`` yolundan BAĞIMSIZ). Toleranslar
# DEĞİŞMEDİ. Ayrıntı: docs/scofield/raw/OH/KITAP/p1a/rapor.md.
_CEA_N2O_SIVI_KARTI = 'N2O_SIVI_P1A'


def _cea_oksitleyici(cea_ox):
    """'N2O' kâhin kartını HRMA'nın varsayılan giriş durumuna getirir."""
    if cea_ox != 'N2O':
        return cea_ox
    from rocketcea.cea_obj import add_new_oxidizer
    import rocketcea.input_cards as _ic
    # V3 kararlılık K-2 (karar §28-33): kart yalnız YOKSA tanıtılır. RocketCEA
    # aynı adlı kart yeniden tanımlanınca süreç-global sonuç önbelleğini
    # bütünüyle boşaltır (rocketcea/cea_obj.py:144-146); bu yardımcı her
    # çağrıda yeniden tanımladığı için aynı süreçteki başka testlerin
    # önbellekli CEA nesnelerini bayatlatıyordu (12 Eki dilim 2, 18 düğüm;
    # docs/scofield/raw/OH/V3/kararlilik/rapor.md). Kart içeriği süreç
    # boyunca sabittir (T ve CoolProp düzeltmesi değişmez), beklenti aynı.
    if _CEA_N2O_SIVI_KARTI in _ic.oxCards:
        return _CEA_N2O_SIVI_KARTI
    from CoolProp.CoolProp import PropsSI
    from hrma.engines.hybrid_rocket_engine import TANK_TEMPERATURE_DEFAULT_K
    T = float(TANK_TEMPERATURE_DEFAULT_K)
    metin = ' '.join(_ic.oxCards['N2O'])
    h_gaz_kj = float(metin.split('h,cal=')[1].split()[0]) * 4.184 / 1000.0
    duzeltme_kj = (PropsSI('Hmolar', 'T', T, 'Q', 0, 'N2O')
                   - PropsSI('Hmolar', 'T', 298.15, 'Dmolar', 1e-6, 'N2O')
                   ) / 1000.0
    add_new_oxidizer(
        _CEA_N2O_SIVI_KARTI,
        ' oxid NitrousOxide N 2.0 O 1.0 wt%=100.00 \n'
        f' h,kj={h_gaz_kj + duzeltme_kj:.5f} t(k)={T} ')
    return _CEA_N2O_SIVI_KARTI


def _cea_ambient_isp(cea_ox, cea_fuel, Pc_bar, OF, frozen, frozenAtThroat):
    """CEA'nın P_e=1 bar'a tam genişlemiş (optimum) Isp'i [s].

    estimate_Ambient_Isp(Pamb=P_e) == M_çıkış * a_çıkış / g0 == v_e/g0.
    Bu, HRMA'nın enerji-denklemi Isp'iyle birebir karşılaştırılabilir.
    """
    c = CEA_Obj(oxName=_cea_oksitleyici(cea_ox), fuelName=cea_fuel)
    Pc_psia = Pc_bar * PSIA_PER_BAR
    Pamb_psia = 1.0 * PSIA_PER_BAR
    # P_e=1 bar veren optimum alan oranı (eps)
    eps = c.get_eps_at_PcOvPe(Pc=Pc_psia, MR=OF, PcOvPe=Pc_bar / 1.0,
                              frozen=frozen, frozenAtThroat=frozenAtThroat)
    isp, _mode = c.estimate_Ambient_Isp(Pc=Pc_psia, MR=OF, eps=eps,
                                        Pamb=Pamb_psia,
                                        frozen=frozen,
                                        frozenAtThroat=frozenAtThroat)
    return float(isp)


def _cea_chamber(cea_ox, cea_fuel, Pc_bar, OF):
    """CEA oda c* [m/s] ve T_c [K]."""
    c = CEA_Obj(oxName=_cea_oksitleyici(cea_ox), fuelName=cea_fuel)
    Pc_psia = Pc_bar * PSIA_PER_BAR
    cstar = c.get_Cstar(Pc=Pc_psia, MR=OF) * FT_TO_M     # ft/s -> m/s
    Tc = c.get_Tcomb(Pc=Pc_psia, MR=OF) * 5.0 / 9.0      # degR -> K
    _mw, gamma = c.get_Chamber_MolWt_gamma(Pc=Pc_psia, MR=OF, eps=2.0)
    return cstar, Tc, float(gamma)


#: Ürün yolu kapalıyken basılacak teşhis. Tek kaynak: aşağıdaki fixture ile
#: ``test_combustion.py``'nin iki fixture'ı aynı metni kullanır.
CANTERA_YOLU_KIRIK = (
    'CombustionAnalyzer.cantera_available False döndü: '
    'hrma/engines/combustion_analysis.py içindeki MECHANISM_CHAIN '
    'mekanizmalarının HİÇBİRİ ct.Solution ile yüklenemedi. Çözücü ampirik '
    'yola düşer ve ürün bileşimi itici çiftinden bağımsız hale gelir '
    '(v2.6.2 F005 kusuru). Bu, atlanacak değil DÜZELTİLECEK bir durumdur.')


@pytest.fixture(scope="module")
def analyzer():
    ca = CombustionAnalyzer()
    # Bağımlılık kapısı: cantera YOKSA atla, KURULU ama yol kapalıysa KIRMIZI.
    # Eskiden ikisi de "Cantera kurulu değil" gerekçesiyle atlanıyordu
    # (parti 31 / T2-2; ölçüm: bozuk mekanizma zinciriyle 39 sessiz atlama).
    kapi('cantera', ca.cantera_available, CANTERA_YOLU_KIRIK)
    return ca


@pytest.fixture(scope="module")
def results(analyzer):
    """Her referans vaka için HRMA analizini bir kez hesapla, önbelleğe al."""
    out = {}
    for label, _co, _cf, hox, hfuel, Pc, OF in CASES:
        out[label] = analyzer.analyze_combustion(hfuel, hox, OF, Pc, None)
    return out


# ---------------------------------------------------------------------------
# 1) Yapı / API koruması (CEA gerektirmez)
# ---------------------------------------------------------------------------
class TestStructureAndKeys:
    """Hibrit motorun bağlı olduğu sözlük anahtarları KORUNMALI."""

    @pytest.mark.parametrize("label", [c[0] for c in CASES])
    def test_required_keys_present(self, results, label):
        r = results[label]
        perf = r["performance"]
        ch = r["compositions"]["chamber"]
        # hybrid_rocket_engine.py'nin doğrudan kullandığı anahtarlar:
        assert "c_star" in perf
        assert "gamma" in ch and "molecular_weight" in ch and "temperature" in ch
        # Yeni anahtarlar:
        assert "c_star_delivered" in perf
        assert "eta_c_star" in perf
        assert "isp_frozen" in perf and "isp_shifting" in perf

    @pytest.mark.parametrize("label", [c[0] for c in CASES])
    def test_isp_equals_shifting(self, results, label):
        """Mevcut 'isp' anahtarı shifting-equilibrium değerine eşit kalmalı."""
        perf = results[label]["performance"]
        assert perf["isp"] == pytest.approx(perf["isp_shifting"], rel=1e-9)


# ---------------------------------------------------------------------------
# 2) c* (yanma) verimi: eta_c_star özelliği
# ---------------------------------------------------------------------------
class TestCStarEfficiency:
    """eta_c_star teorik c*'ı BOZMADAN teslim edilen c*'ı raporlamalı."""

    def test_default_none_means_theoretical(self, analyzer):
        r = analyzer.analyze_combustion({"htpb": 100.0}, "N2O", 6.0, 20.0, None)
        perf = r["performance"]
        assert perf["eta_c_star"] is None
        # eta verilmezse teslim == teorik
        assert perf["c_star_delivered"] == pytest.approx(perf["c_star"], rel=1e-12)

    @pytest.mark.parametrize("eta", [0.90, 0.93, 0.97])
    def test_efficiency_applied_to_delivered_only(self, analyzer, eta):
        base = analyzer.analyze_combustion({"htpb": 100.0}, "N2O", 6.0, 20.0, None)
        r = analyzer.analyze_combustion({"htpb": 100.0}, "N2O", 6.0, 20.0,
                                        eta_c_star=eta)
        perf = r["performance"]
        # Teorik c_star DEĞİŞMEMELİ (eta None vakasıyla aynı)
        assert perf["c_star"] == pytest.approx(base["performance"]["c_star"], rel=1e-9)
        # Teslim edilen = eta * teorik
        assert perf["c_star_delivered"] == pytest.approx(eta * perf["c_star"], rel=1e-9)
        # Teslim < teorik (verim < 1, konservatif)
        assert perf["c_star_delivered"] < perf["c_star"]

    def test_typical_efficiency_in_literature_band(self, analyzer):
        """eta=0.95 ile teslim c*, fiziksel hibrit bandında kalmalı."""
        r = analyzer.analyze_combustion({"htpb": 100.0}, "N2O", 6.0, 20.0,
                                        eta_c_star=0.95)
        cstd = r["performance"]["c_star_delivered"]
        # Hibrit N2O/HTPB teslim c* tipik ~1400-1750 m/s (Chiaverini & Kuo)
        assert 1300.0 < cstd < 1800.0


# ---------------------------------------------------------------------------
# 3) Frozen / shifting fiziksel tutarlılık (CEA gerektirmez)
# ---------------------------------------------------------------------------
class TestFrozenShiftingConsistency:
    """shifting >= frozen olmalı (genişlerken yeniden birleşme entalpi geri kazanır)."""

    @pytest.mark.parametrize("label", [c[0] for c in CASES])
    def test_shifting_ge_frozen(self, results, label):
        perf = results[label]["performance"]
        assert perf["isp_shifting"] >= perf["isp_frozen"] > 0.0

    @pytest.mark.parametrize("label", [c[0] for c in CASES])
    def test_isp_in_physical_band(self, results, label):
        """Deniz seviyesi hibrit/sıvı Isp fiziksel bandı (~180-300 s)."""
        perf = results[label]["performance"]
        assert 180.0 < perf["isp_frozen"] < 300.0
        assert 180.0 < perf["isp_shifting"] < 300.0


# ---------------------------------------------------------------------------
# 4) NASA CEA çapraz-doğrulaması (RocketCEA gerekir)
# ---------------------------------------------------------------------------
@needs_cea
class TestCEACrossValidation:
    """HRMA frozen/shifting Isp ve oda c*/T_c/gamma, CEA'ya yakın olmalı."""

    @pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
    def test_frozen_isp_matches_cea(self, results, case):
        label, cea_ox, cea_fuel, _hox, _hf, Pc, OF = case
        # HRMA oda bileşimini DONDURUR -> CEA frozenAtThroat=1 (oda'da dondur)
        cea_fz = _cea_ambient_isp(cea_ox, cea_fuel, Pc, OF,
                                  frozen=1, frozenAtThroat=1)
        hrma_fz = results[label]["performance"]["isp_frozen"]
        dev = 100.0 * (hrma_fz - cea_fz) / cea_fz
        assert abs(dev) <= ISP_TOL, (
            f"{label} frozen Isp: HRMA={hrma_fz:.2f}s CEA={cea_fz:.2f}s "
            f"sapma={dev:+.2f}% (tol={ISP_TOL}%)"
        )

    @pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
    def test_shifting_isp_matches_cea(self, results, case):
        label, cea_ox, cea_fuel, _hox, _hf, Pc, OF = case
        cea_eq = _cea_ambient_isp(cea_ox, cea_fuel, Pc, OF,
                                  frozen=0, frozenAtThroat=0)
        hrma_eq = results[label]["performance"]["isp_shifting"]
        dev = 100.0 * (hrma_eq - cea_eq) / cea_eq
        assert abs(dev) <= ISP_TOL, (
            f"{label} shifting Isp: HRMA={hrma_eq:.2f}s CEA={cea_eq:.2f}s "
            f"sapma={dev:+.2f}% (tol={ISP_TOL}%)"
        )

    @pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
    def test_chamber_cstar_regression(self, results, case):
        """Oda c* doğruluğu KORUNMALI (yeni Isp mantığı bunu bozmamalı)."""
        label, cea_ox, cea_fuel, _hox, _hf, Pc, OF = case
        cea_cstar, _Tc, _g = _cea_chamber(cea_ox, cea_fuel, Pc, OF)
        hrma_cstar = results[label]["performance"]["c_star"]
        dev = 100.0 * (hrma_cstar - cea_cstar) / cea_cstar
        assert abs(dev) <= CSTAR_TOL, (
            f"{label} c*: HRMA={hrma_cstar:.1f} CEA={cea_cstar:.1f} "
            f"sapma={dev:+.2f}% (tol={CSTAR_TOL}%)"
        )

    @pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
    def test_chamber_temperature_regression(self, results, case):
        label, cea_ox, cea_fuel, _hox, _hf, Pc, OF = case
        _cs, cea_Tc, _g = _cea_chamber(cea_ox, cea_fuel, Pc, OF)
        hrma_Tc = results[label]["compositions"]["chamber"]["temperature"]
        dev = 100.0 * (hrma_Tc - cea_Tc) / cea_Tc
        assert abs(dev) <= TC_TOL, (
            f"{label} T_c: HRMA={hrma_Tc:.1f}K CEA={cea_Tc:.1f}K "
            f"sapma={dev:+.2f}% (tol={TC_TOL}%)"
        )

    @pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
    def test_chamber_gamma_regression(self, results, case):
        """Shifting-equilibrium oda gamma'sı CEA'ya yakın kalmalı."""
        label, cea_ox, cea_fuel, _hox, _hf, Pc, OF = case
        _cs, _Tc, cea_g = _cea_chamber(cea_ox, cea_fuel, Pc, OF)
        hrma_g = results[label]["compositions"]["chamber"]["gamma"]
        dev = 100.0 * (hrma_g - cea_g) / cea_g
        assert abs(dev) <= GAMMA_TOL, (
            f"{label} gamma: HRMA={hrma_g:.4f} CEA={cea_g:.4f} "
            f"sapma={dev:+.2f}% (tol={GAMMA_TOL}%)"
        )


# ---------------------------------------------------------------------------
# 5) Yakıt-zengin bölge + GOX çapraz-doğrulaması (v2.5.0 G4 bekçileri)
# ---------------------------------------------------------------------------
# Neden var (2026-07-18 fizik incelemesi): eski CEA doğrulaması yalnız tasarım
# O/F'sini (6.0) görüyordu; korelasyon DB'sindeki kayıtların TAMAMI yakıt-zengin
# bölgede (O/F 1.5-4.6) yaşıyor ve HTPB Hf hatası ile 'gox' oksijensiz-denge
# bugı bu yüzden hiçbir testte görünmedi. Bu satırlar o boşluğu kapatır.
#
# Tolerans gerekçesi (ölçülmüş sapmalar, 2026-07-18, Hf+gox düzeltmesi sonrası):
#   N2O/HTPB OF=3.0: c* -2.15%, T_c -4.13%  (gri30'da C(gr) yok; O/F<3.5'te
#     yoğun-faz karbon modellenmiyor — bilinen, dokümante sınır)
#   N2O/HTPB OF=4.5: c* -0.22%, T_c -1.87%
#   (N₂O satırları kitap p1a B16'da yeniden ölçüldü: iki yan da 293,15 K
#   doymuş SIVI girişle — docs/scofield/raw/OH/KITAP/p1a/kanit/
#   cea_sapma_sonra.json. Eski gaz ⟷ gaz değerleri: c* -2.1/+0.1%,
#   T_c -3.6/-1.8%. Toleranslar DEĞİŞMEDİ.)
#   GOX/RP-1 OF=2.3: c* +0.8%, T_c -1.2%
FUELRICH_CASES = [
    # (label, ceaOx, ceaFuel, hrmaOx, hrmaFuel, Pc_bar, OF, cstar_tol, tc_tol)
    ("N2O/HTPB rich OF=3.0", "N2O", "HTPB", "n2o", {"htpb": 100.0},
     20.0, 3.0, 3.5, 5.0),
    ("N2O/HTPB OF=4.5", "N2O", "HTPB", "n2o", {"htpb": 100.0},
     20.0, 4.5, 2.5, 3.5),
    ("GOX/RP-1 OF=2.3", "GOX", "RP-1", "gox", {"paraffin": 100.0},
     20.0, 2.3, 2.5, 3.5),
]


@needs_cea
class TestFuelRichAndGoxCEA:
    """Korelasyon DB'sinin yaşadığı yakıt-zengin bölge CEA'ya karşı denetlenir."""

    @pytest.mark.parametrize("case", FUELRICH_CASES,
                             ids=[c[0] for c in FUELRICH_CASES])
    def test_chamber_cstar(self, analyzer, case):
        label, cox, cfu, hox, hf, Pc, OF, cstar_tol, _tc_tol = case
        cea_cstar, _tc, _g = _cea_chamber(cox, cfu, Pc, OF)
        hrma = analyzer.analyze_combustion(hf, hox, OF, Pc, None)
        dev = 100.0 * (hrma["performance"]["c_star"] - cea_cstar) / cea_cstar
        assert abs(dev) <= cstar_tol, (
            f"{label} c*: HRMA={hrma['performance']['c_star']:.1f} "
            f"CEA={cea_cstar:.1f} sapma={dev:+.2f}% (tol={cstar_tol}%)")

    @pytest.mark.parametrize("case", FUELRICH_CASES,
                             ids=[c[0] for c in FUELRICH_CASES])
    def test_chamber_temperature(self, analyzer, case):
        label, cox, cfu, hox, hf, Pc, OF, _cstar_tol, tc_tol = case
        _cs, cea_tc, _g = _cea_chamber(cox, cfu, Pc, OF)
        hrma = analyzer.analyze_combustion(hf, hox, OF, Pc, None)
        tc = hrma["compositions"]["chamber"]["temperature"]
        dev = 100.0 * (tc - cea_tc) / cea_tc
        assert abs(dev) <= tc_tol, (
            f"{label} T_c: HRMA={tc:.0f}K CEA={cea_tc:.0f}K "
            f"sapma={dev:+.2f}% (tol={tc_tol}%)")


# ---------------------------------------------------------------------------
# 6) GOX/bilinmeyen-anahtar regresyon bekçileri (CEA gerektirmez)
# ---------------------------------------------------------------------------
class TestOxidizerKeyGuards:
    """'gox' oksijensiz-denge bugının (2026-07-18) geri gelmesini engeller."""

    def test_gox_ve_lox_ayni_elemental_katkiyi_verir(self, analyzer):
        """GOX ve LOX aynı ELEMENTAL katkıyı vermeli; entalpileri farklıdır.

        ÖH D15/hibrit-a1 (31 Ağu 2026) — BEKÇİ ÇEVRİLDİ.
        Bu test eskiden GOX ile LOX'un c*'ını BİREBİR EŞİT olmaya zorluyordu
        ve böylece kusuru KİLİTLİYORDU (P1B3-03): sıvı oksijen 298,15 K'deki
        gaz O2 referansıyla yakılıyor, kriyojenik entalpi (CEA LOX kartı
        O2(L) h,cal=-3102 t(k)=90.18 -> -405,60 kJ/kg) hiç düşülmüyordu.
        Testin KORUDUĞU asıl regresyon 2026-07-18'in "gox hiçbir dala
        girmiyor, elemental O = 0 kalıyor, c* ~%40 şişiyor" hatasıdır; o
        hata bu iki oksitleyicinin ELEMENTAL katkısıyla ilgilidir,
        entalpileriyle değil. Bu yüzden eşitlik iddiası elemental bileşime
        taşındı ve c* için "yakın ama LOX daha DÜŞÜK" hükmü kondu:
        sıvıyı buharlaştırmak enerji ister, bu bedava sayılamaz.
        Ölçüldü: paraffin/O2 O/F 2,3 Pc 20 -> GOX 1821,88 ⟷ LOX 1802,01 m/s
        (%1,09; eskiden ikisi de 1821,88 idi).
        """
        r_gox = analyzer.analyze_combustion({"paraffin": 100.0}, "gox", 2.3, 20.0, None)
        r_lox = analyzer.analyze_combustion({"paraffin": 100.0}, "lox", 2.3, 20.0, None)
        # 1) Elemental katkı (bugın gerçek konusu) BİREBİR aynı olmalı.
        assert (r_gox["elemental_composition"]
                == r_lox["elemental_composition"])
        assert r_gox["stoichiometric_of"] == pytest.approx(
            r_lox["stoichiometric_of"], rel=1e-12)
        c_gox = r_gox["performance"]["c_star"]
        c_lox = r_lox["performance"]["c_star"]
        # 2) Kriyojenik entalpi düşüldüğü için LOX KESİNLİKLE daha düşük...
        assert c_lox < c_gox, (
            f"LOX c* ({c_lox:.2f}) gaz O2'ninkinden ({c_gox:.2f}) düşük "
            f"olmalı: O2(L) buharlaşma entalpisi bedava enerji değildir")
        # 3) ...ama fark buharlaşma entalpisi mertebesinde (%2'nin altında),
        #    yani oksijensiz-denge bugının %40'lık sapması DEĞİL.
        assert abs(c_gox / c_lox - 1.0) < 0.02

    def test_gox_cstar_physical(self, analyzer):
        """Bug durumunda c* ~2500+ çıkıyordu; fiziksel bant korunmalı."""
        r = analyzer.analyze_combustion({"paraffin": 100.0}, "gox", 2.3, 20.0, None)
        assert 1600.0 < r["performance"]["c_star"] < 1980.0

    def test_unknown_oxidizer_raises(self, analyzer):
        with pytest.raises(ValueError, match="Unsupported oxidizer key"):
            analyzer.analyze_combustion({"paraffin": 100.0}, "nytrox", 2.3, 20.0, None)

    def test_unknown_fuel_raises(self, analyzer):
        with pytest.raises(ValueError, match="Unsupported fuel key"):
            analyzer.analyze_combustion({"pp": 100.0}, "lox", 2.3, 20.0, None)


if __name__ == "__main__":  # elle hızlı çalıştırma
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
