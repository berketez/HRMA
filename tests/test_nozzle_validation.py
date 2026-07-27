"""
Nozzle tasarım modülü doğrulama testleri (kalıcı pytest).

Referans kaynaklar:
- Sutton & Biblarz, "Rocket Propulsion Elements", 9th ed.
    * Eq. 3-30  : İtki katsayısı CF (momentum + basınç terimi)
    * Eq. 3-32  : c* (karakteristik hız)
    * Eq. 3-34, Table 3-3 : Diverjans verimi lambda (konik)
    * Ch.3      : Ayrık nozzle kayıp faktörleri (sürtünme, iki-fazlı, kinetik)
    * sec. 3.5  : İki-fazlı (partikül) akış kaybı
- NASA SP-8120 "Liquid Rocket Engine Nozzles"
- RocketCEA (NASA CEA arayüzü) ile bağımsız çapraz doğrulama

Bilinen vaka: gamma=1.2, eps=10, Pc=40 bar (adapte/tutarlı çıkış basıncı).
"""

import numpy as np
import pytest
from scipy.optimize import brentq

from hrma.engines.nozzle_design import NozzleDesigner


# ---------------------------------------------------------------------------
# Yardımcılar — bilinen vaka için tutarlı çıkış basıncı (izentropik alan-Mach)
# ---------------------------------------------------------------------------
def _exit_pressure(gamma: float, eps: float, Pc: float) -> float:
    """eps ve gamma'dan izentropik çıkış basıncını döndürür (Sutton Eq. 3-14)."""
    exp = (gamma + 1.0) / (2.0 * (gamma - 1.0))

    def area_ratio(M):
        return (1.0 / M) * ((2.0 / (gamma + 1.0)) *
                            (1.0 + 0.5 * (gamma - 1.0) * M * M)) ** exp

    Me = brentq(lambda M: area_ratio(M) - eps, 1.001, 50.0)
    return Pc / ((1.0 + (gamma - 1.0) / 2.0 * Me ** 2) ** (gamma / (gamma - 1.0)))


def _cf_momentum(gamma: float, Pe: float, Pc: float) -> float:
    """Sutton & Biblarz 9th ed. Eq. 3-30 momentum terimi (analitik referans)."""
    return np.sqrt(
        2.0 * gamma ** 2 / (gamma - 1.0)
        * (2.0 / (gamma + 1.0)) ** ((gamma + 1.0) / (gamma - 1.0))
        * (1.0 - (Pe / Pc) ** ((gamma - 1.0) / gamma))
    )


# Bilinen vaka sabitleri
GAMMA = 1.2
EPS = 10.0
PC = 40.0
PE = _exit_pressure(GAMMA, EPS, PC)


@pytest.fixture(scope="module")
def designer():
    return NozzleDesigner()


class TestThrustCoefficient:
    """CF (momentum/ideal) izentropik formül doğrulaması — Sutton Eq. 3-30."""

    def test_cf_momentum_matches_sutton_formula(self, designer):
        # design_nozzle'a gerçek gamma=1.2 geçilir; sonuç analitik Sutton ile eşleşmeli
        res = designer.design_nozzle(0.001, EPS, PC, PE, 'bell', gamma=GAMMA)
        cf_mom = res['performance']['thrust_coefficient_momentum']
        cf_ref = _cf_momentum(GAMMA, PE, PC)
        assert cf_mom == pytest.approx(cf_ref, rel=1e-6), (
            f"CF_momentum {cf_mom:.5f} != Sutton referans {cf_ref:.5f}"
        )

    def test_cf_momentum_in_expected_range(self, designer):
        # gamma=1.2, eps=10 için Sutton/CEA tipik aralığı ~1.55-1.65
        res = designer.design_nozzle(0.001, EPS, PC, PE, 'bell', gamma=GAMMA)
        cf_mom = res['performance']['thrust_coefficient_momentum']
        assert 1.55 < cf_mom < 1.66, f"CF {cf_mom:.4f} beklenen aralık dışında"

    def test_cf_actual_le_ideal(self, designer):
        # Verim < 1 olduğundan gerçek CF ideal CF'ten küçük olmalı (konservatif)
        res = designer.design_nozzle(0.001, EPS, PC, PE, 'bell', gamma=GAMMA)
        p = res['performance']
        assert p['thrust_coefficient_actual'] < p['thrust_coefficient_ideal']


class TestDivergenceEfficiency:
    """Diverjans verimi lambda — Sutton & Biblarz 9th ed. Eq. 3-34, Table 3-3."""

    def test_conical_15deg_matches_sutton_table(self, designer):
        # Sutton Table 3-3: 15° konik → lambda = 0.983
        res = designer.design_nozzle(0.001, EPS, PC, PE, 'conical', gamma=GAMMA)
        lam = res['performance']['divergence_efficiency']
        assert lam == pytest.approx(0.983, abs=1e-3), (
            f"Konik 15° lambda {lam:.4f} != Sutton 0.983"
        )

    def test_bell_better_than_conical(self, designer):
        # Bell nozzle akışı çıkışta eksenel döndürür → diverjans kaybı daha az
        bell = designer.design_nozzle(0.001, EPS, PC, PE, 'bell', gamma=GAMMA)
        conical = designer.design_nozzle(0.001, EPS, PC, PE, 'conical', gamma=GAMMA)
        assert (bell['performance']['divergence_efficiency'] >
                conical['performance']['divergence_efficiency'])

    def test_bell_lambda_range(self, designer):
        """lambda, GENİŞLEME ORANINA bağlı olmalı (Rao) — sabit 8° değil.

        v2.6.2 fizik denetimi (F051): bell nozul çıkış açısı theta_e KODA
        SABİT 8 derece yazılıydı, oysa Rao'nun %80 bell tasarımında hem
        theta_n hem theta_e genişleme oranının fonksiyonudur (Rao 1958;
        Sutton & Biblarz 9. baskı Şekil 3-14; Huzel & Huang Şekil 4-15).
        Sabit 8 derece ancak eps ~ 50-100 için doğrudur.

        Bu test eskiden eps=10'da lambda=0.9951 bekliyordu — yani eps~100'ün
        değerini. Doğrusu eps=10'da theta_e ~ 14 derece ve lambda ~ 0.985.
        """
        res = designer.design_nozzle(0.001, EPS, PC, PE, 'bell', gamma=GAMMA)
        lam = res['performance']['divergence_efficiency']
        # lambda = 0.5*(1+cos theta_e) -> theta_e = arccos(2*lambda-1)
        theta_e = np.degrees(np.arccos(2.0 * lam - 1.0))
        assert 11.0 <= theta_e <= 17.0, (
            f'eps={EPS} icin theta_e={theta_e:.1f} derece — Rao bandi disinda')
        assert lam == pytest.approx(0.9851, abs=2e-3)

    def test_lambda_increases_with_expansion_ratio(self, designer):
        """Asıl regresyon bekçisi: lambda eps ile DEĞİŞMELİ.

        Sabit theta_e geri gelirse bu test kırılır — tek bir nokta değerini
        kilitlemek yerine eps bağımlılığının kendisini kilitler.
        """
        lams = [designer.design_nozzle(0.001, e, PC, _exit_pressure(GAMMA, e, PC),
                                       'bell', gamma=GAMMA
                                       )['performance']['divergence_efficiency']
                for e in (10.0, 25.0, 50.0, 100.0)]
        assert all(b > a for a, b in zip(lams, lams[1:])), (
            f'lambda genisleme oraniyla artmiyor: {lams} '
            '(theta_e yine sabitlenmis olabilir)')
        # Yuksek eps'te Rao ucu ~8 dereceye yaklasir (eski sabit deger)
        assert lams[-1] == pytest.approx(0.9957, abs=3e-3)


class TestDiscreteLossModel:
    """Ayrık kayıp modeli: eta_nozzle = lambda·eta_fric·eta_2ph·eta_kin."""

    def test_eta_nozzle_is_product_of_components(self, designer):
        res = designer.design_nozzle(0.001, EPS, PC, PE, 'bell', gamma=GAMMA)
        p = res['performance']
        expected = (p['divergence_efficiency'] * p['friction_efficiency'] *
                    p['two_phase_efficiency'] * p['kinetic_efficiency'])
        assert p['nozzle_efficiency'] == pytest.approx(expected, rel=1e-9)

    def test_default_matches_legacy_098_at_high_expansion(self, designer):
        """Eski tek-faktör 0.98 değeri artık YÜKSEK eps'te karşılanmalı.

        v2.6.2 (F051): bu test eskiden eps=10'da eta=0.98 bekliyordu. O beklenti
        theta_e'nin SABİT 8 derece olmasına dayanıyordu — yani legacy 0.98'in
        kendisi de eps~100 geometrisinden türemişti. theta_e artık Rao'ya göre
        eps ile değiştiği için eps=10'da gerçek eta ~0.970, eps=100'de ~0.981.

        Yani legacy değer YANLIŞ DEĞİLDİ, YANLIŞ YERE UYGULANIYORDU.
        """
        high = designer.design_nozzle(0.001, 100.0, PC,
                                      _exit_pressure(GAMMA, 100.0, PC),
                                      'bell', gamma=GAMMA)
        assert high['performance']['nozzle_efficiency'] == pytest.approx(
            0.98, abs=2.0e-3)

        # Dusuk eps'te daha dusuk olmali (daha genis cikis acisi = daha cok kayip)
        low = designer.design_nozzle(0.001, EPS, PC, PE, 'bell', gamma=GAMMA)
        assert low['performance']['nozzle_efficiency'] < high['performance'][
            'nozzle_efficiency']
        assert low['performance']['nozzle_efficiency'] == pytest.approx(
            0.97042, abs=2.0e-3)

    def test_legacy_efficiency_override(self, designer):
        # efficiency=<sayı> geçilirse legacy tek-faktör davranışı korunmalı
        res = designer.design_nozzle(0.001, EPS, PC, PE, 'bell',
                                     efficiency=0.95, gamma=GAMMA)
        assert res['performance']['nozzle_efficiency'] == pytest.approx(0.95, abs=1e-9)

    def test_gas_phase_no_two_phase_loss(self, designer):
        # partikül kütle kesri verilmezse (gaz-faz) iki-fazlı verim = 1.0
        res = designer.design_nozzle(0.001, EPS, PC, PE, 'bell', gamma=GAMMA)
        assert res['performance']['two_phase_efficiency'] == pytest.approx(1.0)

    def test_two_phase_loss_metallized(self, designer):
        # Al2O3 ~%30 kütle kesri → ~%2-4 kayıp (Sutton sec. 3.5); k=0.12 → 0.964
        res = designer.design_nozzle(0.001, EPS, PC, PE, 'bell', gamma=GAMMA,
                                     particle_mass_fraction=0.30)
        e2 = res['performance']['two_phase_efficiency']
        assert e2 == pytest.approx(0.964, abs=1e-3)
        # Toplam verim partikülsüz vakadan DÜŞÜK olmalı (konservatif)
        gas = designer.design_nozzle(0.001, EPS, PC, PE, 'bell', gamma=GAMMA)
        assert (res['performance']['nozzle_efficiency'] <
                gas['performance']['nozzle_efficiency'])

    def test_all_efficiencies_physical(self, designer):
        # Tüm verim bileşenleri (0, 1] aralığında olmalı
        res = designer.design_nozzle(0.001, EPS, PC, PE, 'bell', gamma=GAMMA,
                                     particle_mass_fraction=0.30)
        p = res['performance']
        for k in ('divergence_efficiency', 'friction_efficiency',
                  'two_phase_efficiency', 'kinetic_efficiency', 'nozzle_efficiency'):
            assert 0.0 < p[k] <= 1.0, f"{k}={p[k]} fiziksel aralık dışında"


class TestThermodynamicParameters:
    """Hardcoded gamma/R/Tc yerine opsiyonel parametre — varsayılan eski davranış."""

    def test_default_gamma_is_legacy_125(self, designer):
        # gamma geçilmezse c* eski hardcoded 1.25/300/3000 ile hesaplanmalı
        res = designer.design_nozzle(0.001, EPS, PC, PE, 'bell')
        gamma, R, Tc = 1.25, 300.0, 3000.0
        cstar_ref = np.sqrt(R * Tc / gamma) / (
            (2 / (gamma + 1)) ** ((gamma + 1) / (2 * (gamma - 1))))
        assert res['performance']['characteristic_velocity'] == pytest.approx(
            cstar_ref, rel=1e-9)

    def test_real_gamma_changes_cstar(self, designer):
        # Gerçek termodinamik değerler c*'ı değiştirmeli (parametre etkin)
        legacy = designer.design_nozzle(0.001, EPS, PC, PE, 'bell')
        real = designer.design_nozzle(0.001, EPS, PC, PE, 'bell',
                                      gamma=1.15, R_specific=350, T_chamber=3200)
        assert (real['performance']['characteristic_velocity'] !=
                pytest.approx(legacy['performance']['characteristic_velocity'], rel=1e-3))

    def test_flow_properties_reads_gamma(self, designer):
        # calculate_nozzle_flow_properties artık chamber_conditions['gamma'] okur
        res = designer.design_nozzle(0.001, EPS, PC, PE, 'bell', gamma=GAMMA)
        fp = designer.calculate_nozzle_flow_properties(
            res, 1.0, {'gamma': 1.2, 'gas_constant': 320,
                       'temperature': 2800, 'pressure': 40})
        assert fp['exit']['mach_number'] > 1.0  # supersonik çıkış


class TestApiPreservation:
    """Public imza + dönen sözlük anahtarları korunmalı (hybrid/solid/liquid kullanıyor)."""

    REQUIRED_TOP = {'basic_dimensions', 'geometry', 'contour',
                    'performance', 'nozzle_type'}
    REQUIRED_PERF = {'characteristic_velocity', 'thrust_coefficient_momentum',
                     'thrust_coefficient_ideal', 'thrust_coefficient_actual',
                     'specific_impulse', 'exit_velocity', 'nozzle_efficiency',
                     'pressure_ratio', 'expansion_ratio'}

    def test_legacy_positional_call_works(self, designer):
        # Hybrid motorun kullandığı eski pozisyonel imza kırılmamalı
        res = designer.design_nozzle(0.001, 10.0, 40.0, 0.5, 'bell')
        assert self.REQUIRED_TOP.issubset(res.keys())

    def test_performance_keys_preserved(self, designer):
        res = designer.design_nozzle(0.001, EPS, PC, PE, 'bell')
        assert self.REQUIRED_PERF.issubset(res['performance'].keys())

    def test_new_keys_are_additive(self, designer):
        # Yeni anahtarlar eklendi ama eskiler silinmedi
        res = designer.design_nozzle(0.001, EPS, PC, PE, 'bell')
        new_keys = {'divergence_efficiency', 'friction_efficiency',
                    'two_phase_efficiency', 'kinetic_efficiency'}
        assert new_keys.issubset(res['performance'].keys())


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main([__file__, '-v']))
