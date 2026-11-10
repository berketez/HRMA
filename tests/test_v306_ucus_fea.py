"""V306/UÇUŞ-FEA — 6-DOF atmosfer katmanı ve yörünge faz saatleri.

Kalem 4 (ÖLÇÜT gözlem 1): ``six_dof_trajectory._atmosphere_full`` katman
döngüsü H'nin altındaki her katmanı kendi gradyanıyla H'ye uzatıyordu;
H > 44,33 km'de troposfer uzantısı T'yi negatife çekip (T/T_b)^(kesir)'te
NaN üretiyordu (44 km üstü 6-DOF koşusunda 5 451-11 191 RuntimeWarning).
Son katman üzerine yazdığı için sayı doğruydu; onarım sonucu bit-aynı
bıraktı (15 tur vakası, ``docs/scofield/raw/OH/V306/ucus-fea/olcum/``).

Kalem 5 (ÖLÇÜT gözlem 3): yanıtta iki "apogee_time" vardı —
``performance.phase_breakdown.apogee_time`` ateşlemeden (uçuş saati),
``trajectory.phases.coasting.apogee_time`` serbest fazın kendi saatinden
(yanma sonu + 2 s geçiş payında başlar). Faz alanı
``apogee_time_from_phase_start`` oldu; ``coasting_time`` artık yanma
sonundan apojeye (eskisi geçiş payı kadar, tam 2 s kısaydı).
"""
import warnings

import numpy as np
import pytest

from hrma.analysis import six_dof_trajectory as sdt
from hrma.analysis.trajectory_analysis import (
    POWERED_PHASE_MARGIN_S, TrajectoryAnalyzer)
from hrma.constants import ISA_LAYERS, ISA_TABLE_TOP_M, isa_temperature

# Troposfer satırının uzantısının T = 0'a indiği geopotansiyel irtifa
# (tablodan türetilir: T_0 / |lapse_0|; 44 330,8 m).
H_TROPO_SIFIR = ISA_LAYERS[0][1] / -ISA_LAYERS[0][2]


def _geometrik(H):
    """Geopotansiyel H -> geometrik h (modülün kendi R'siyle)."""
    R = sdt.R_GEOPOTENTIAL
    return H * R / (R - H)


class TestAltiSerbestlikAtmosferKatmani:

    @pytest.mark.parametrize('H', [0.0, 10_999.0, 11_000.0, 25_000.0,
                                   H_TROPO_SIFIR + 1.0, 50_000.0, 60_000.0,
                                   80_000.0, ISA_TABLE_TOP_M - 1.0])
    def test_tablo_icinde_uyari_ve_nan_yok(self, H):
        """Gerçek bir NaN uyarısı gürültüye gömülmesin: tablo içinde HİÇ
        uyarı yok. numpy skaleri (entegratörün verdiği tür) ile sınanır —
        eski döngü 44,33 km üstünde burada 'invalid value' veriyordu."""
        h = np.float64(_geometrik(H))
        with warnings.catch_warnings():
            warnings.simplefilter('error')
            rho, a, P, T = sdt._atmosphere_full(h)
        assert all(np.isfinite(v) and v > 0 for v in (rho, a, P, T))

    @pytest.mark.parametrize('H', [0.0, 5_000.0, 11_000.0, 15_000.0,
                                   20_000.0, 32_000.0, 47_000.0, 50_000.0,
                                   51_000.0, 71_000.0, 80_000.0])
    def test_sicaklik_merkezi_katmanla_ayni(self, H):
        """Katman seçimi ve sıcaklık merkezî ISA ile birebir (tek tablo,
        tek seçici)."""
        h = _geometrik(H)
        Hm = h * sdt.R_GEOPOTENTIAL / (sdt.R_GEOPOTENTIAL + h)
        T = sdt._atmosphere_full(h)[3]
        assert T == pytest.approx(isa_temperature(Hm), rel=1e-12)

    def test_eski_dongunun_son_katmaniyla_bit_ayni(self):
        """Sayı değişmedi: eski döngünün SON yazdığı değer = yeni değer
        (eski döngü burada kâhin olarak yeniden kurulur, uyarılar susturulur)."""
        def eski(H):
            T, P = ISA_LAYERS[0][1], ISA_LAYERS[0][3]
            for base, T_b, lapse, P_b in ISA_LAYERS:
                if H >= base:
                    if lapse == 0.0:
                        T = T_b
                        P = P_b * np.exp(-sdt.G0 * (H - base)
                                         / (sdt.R_AIR * T_b))
                    else:
                        T = T_b + lapse * (H - base)
                        P = P_b * (T / T_b) ** (-sdt.G0 / (lapse * sdt.R_AIR))
            return float(T), float(P)

        for H in np.linspace(0.0, ISA_TABLE_TOP_M, 97):
            h = np.float64(_geometrik(H))
            Hm = h * sdt.R_GEOPOTENTIAL / (sdt.R_GEOPOTENTIAL + h)
            with np.errstate(invalid='ignore'):
                T0, P0 = eski(Hm)
            _rho, _a, P, T = sdt._atmosphere_full(h)
            assert (T, P) == (max(T0, 150.0), max(P0, 1e-9)), H


# Yörünge fizik bekçisinin motoru (tek tanım; ikinci kopya yazılmaz).
from tests.test_trajectory_physics_v262 import MOTOR as YORUNGE_MOTORU  # noqa: E402


@pytest.fixture(scope='module')
def yorunge():
    ta = TrajectoryAnalyzer()
    ta.set_vehicle_parameters(mass_dry=20.0, diameter=0.15,
                              drag_coefficient=0.5)
    return ta.calculate_trajectory(YORUNGE_MOTORU, {
        'launch_angle': 85.0, 'launch_altitude': 0.0,
        'wind_speed': 0.0, 'wind_direction': 0.0})


class TestYorungeFazSaatleri:

    def test_apogee_time_adi_yanitta_tek_tanimli(self, yorunge):
        co = yorunge['trajectory']['phases']['coasting']
        assert 'apogee_time' not in co, (
            'serbest faz yine "apogee_time" adını kendi saatiyle taşıyor')
        pb = yorunge['performance']['phase_breakdown']
        t0 = float(yorunge['trajectory']['phases']['powered']['time'][-1])
        assert co['apogee_reached'] is True
        assert pb['apogee_time'] == t0 + float(co['apogee_time_from_phase_start'])
        # Faz saati yanma sonu + geçiş payında başlar (künyede beyanlı).
        assert t0 == pytest.approx(YORUNGE_MOTORU['burn_time'] + POWERED_PHASE_MARGIN_S)
        assert 'ignition' in pb['time_basis']

    def test_faz_sureleri_ucus_saatini_toplar(self, yorunge):
        """yanma + serbest uçuş = apoje anı (eski serbest süre geçiş payı
        kadar kısaydı: toplam 2 s eksik)."""
        pb = yorunge['performance']['phase_breakdown']
        assert pb['powered_flight_time'] + pb['coasting_time'] == \
            pytest.approx(pb['apogee_time'], abs=1e-9)
        t = np.asarray(yorunge['trajectory']['time'])
        z = np.asarray(yorunge['trajectory']['altitude'])
        assert pb['apogee_time'] == pytest.approx(
            float(t[int(np.argmax(z))]), abs=0.05)
