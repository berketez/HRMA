"""Validation tests for the pressurant (pressurizing gas) sizing model.

Hand-computed anchors (Sutton 9th ed. Ch. 6; Huzel & Huang Ch. 5).
Specific gas constants: R_u = 8314.462618 J/(kmol.K).
    R_N2 = 8314.462618 / 28.0134 = 296.803 J/(kg.K)
    R_He = 8314.462618 / 4.002602 = 2077.264 J/(kg.K)

Regulated case V_p=0.1 m^3, P_tank=30 bar, T0=293.15 K, N2:
    isothermal  m = P_tank*V_p/(R*T0) = 3e5/(296.803*293.15) = 3.4480 kg
    adiabatic (P_store=200 bar): T_final = T0*(30/200)^(0.4/1.4) = 170.49 K
                m = 3e5/(296.803*170.49) = 5.929 kg  (> isothermal)

Blowdown case P0=50 bar, V_u0=0.05 m^3, V_p=0.05 m^3, N2:
    n=1.0 : P_final = 50*(0.05/0.10)^1 = 25 bar, blowdown ratio 2.0, T_final=T0.
"""

import math

import pytest

from hrma.analysis.pressurant_sizing import (
    regulated_pressurant, blowdown_pressurant, analyze_pressurant,
    gas_properties, compressibility_factor, GAS_PROPERTIES, R_UNIVERSAL,
)

# CoolProp kuruluysa gerçek gaz yolu aktif; değilse Z=1 + beyan (skip nedeni).
HAS_COOLPROP = compressibility_factor('helium', 300e5, 293.15)[1]


class TestGasConstants:
    def test_nitrogen_specific_gas_constant(self):
        assert GAS_PROPERTIES['nitrogen']['R'] == pytest.approx(296.803, rel=1e-4)
        assert GAS_PROPERTIES['nitrogen']['gamma'] == pytest.approx(1.40, rel=1e-6)

    def test_helium_specific_gas_constant(self):
        assert GAS_PROPERTIES['helium']['R'] == pytest.approx(2077.26, rel=1e-4)
        assert GAS_PROPERTIES['helium']['gamma'] == pytest.approx(1.667, rel=1e-6)

    def test_specific_constant_is_universal_over_molar_mass(self):
        for props in GAS_PROPERTIES.values():
            assert props['R'] == pytest.approx(R_UNIVERSAL / props['M'], rel=1e-12)

    def test_gas_aliases_resolve(self):
        assert gas_properties('He')[0] == 'helium'
        assert gas_properties('N2')[0] == 'nitrogen'
        assert gas_properties('GN2')[0] == 'nitrogen'

    def test_unknown_gas_raises(self):
        with pytest.raises(ValueError):
            gas_properties('argon')


class TestRegulatedIsothermal:
    def test_isothermal_ideal_gas_hand_calc(self):
        r = regulated_pressurant(propellant_volume=0.1, tank_pressure=30e5,
                                 gas='nitrogen', initial_temperature=293.15,
                                 storage_pressure=200e5)
        assert r['isothermal']['gas_mass_kg'] == pytest.approx(3.4480, rel=1e-3)
        assert r['isothermal']['final_temperature_K'] == pytest.approx(293.15)

    def test_isothermal_density_is_P_over_RT(self):
        r = regulated_pressurant(propellant_volume=0.1, tank_pressure=30e5,
                                 gas='nitrogen', initial_temperature=293.15)
        R = GAS_PROPERTIES['nitrogen']['R']
        assert r['isothermal']['gas_density_kgm3'] == pytest.approx(
            30e5 / (R * 293.15), rel=1e-9)

    def test_mass_scales_linearly_with_volume(self):
        base = regulated_pressurant(0.1, 30e5, gas='nitrogen')
        dbl = regulated_pressurant(0.2, 30e5, gas='nitrogen')
        assert dbl['isothermal']['gas_mass_kg'] == pytest.approx(
            2.0 * base['isothermal']['gas_mass_kg'], rel=1e-9)

    def test_helium_isothermal_hand_calc(self):
        r = regulated_pressurant(propellant_volume=0.1, tank_pressure=30e5,
                                 gas='helium', initial_temperature=293.15)
        # 3e5 / (2077.264*293.15) = 0.49257 kg
        assert r['isothermal']['gas_mass_kg'] == pytest.approx(0.49257, rel=1e-3)


class TestRegulatedAdiabatic:
    def test_adiabatic_temperature_hand_calc(self):
        r = regulated_pressurant(propellant_volume=0.1, tank_pressure=30e5,
                                 gas='nitrogen', initial_temperature=293.15,
                                 storage_pressure=200e5)
        gamma = 1.40
        T_expected = 293.15 * (30e5 / 200e5) ** ((gamma - 1.0) / gamma)
        assert r['adiabatic']['final_temperature_K'] == pytest.approx(
            T_expected, rel=1e-9)
        assert T_expected == pytest.approx(170.49, rel=1e-3)

    def test_adiabatic_mass_hand_calc(self):
        r = regulated_pressurant(propellant_volume=0.1, tank_pressure=30e5,
                                 gas='nitrogen', initial_temperature=293.15,
                                 storage_pressure=200e5)
        assert r['adiabatic']['gas_mass_kg'] == pytest.approx(5.929, rel=1e-3)

    def test_adiabatic_exceeds_isothermal(self):
        for gas in ('nitrogen', 'helium'):
            r = regulated_pressurant(0.1, 30e5, gas=gas, storage_pressure=200e5)
            assert r['adiabatic']['gas_mass_kg'] > r['isothermal']['gas_mass_kg']

    def test_helium_needs_less_mass_than_nitrogen(self):
        he = regulated_pressurant(0.1, 30e5, gas='helium')
        n2 = regulated_pressurant(0.1, 30e5, gas='nitrogen')
        assert he['isothermal']['gas_mass_kg'] < n2['isothermal']['gas_mass_kg']


class TestCollapseFactor:
    def test_collapse_factor_scales_mass(self):
        base = regulated_pressurant(0.1, 30e5, gas='nitrogen', collapse_factor=1.0)
        corr = regulated_pressurant(0.1, 30e5, gas='nitrogen', collapse_factor=1.3)
        assert corr['isothermal']['gas_mass_kg'] == pytest.approx(
            1.3 * base['isothermal']['gas_mass_kg'], rel=1e-9)
        assert corr['adiabatic']['gas_mass_kg'] == pytest.approx(
            1.3 * base['adiabatic']['gas_mass_kg'], rel=1e-9)


class TestStorageSizing:
    def test_stored_equals_delivered_plus_residual(self):
        r = regulated_pressurant(0.1, 30e5, gas='nitrogen', storage_pressure=200e5)
        s = r['storage']
        assert s['stored_mass_kg'] == pytest.approx(
            r['recommended_delivered_mass_kg'] + s['residual_mass_kg'], rel=1e-9)

    def test_bottle_count_is_ceiling(self):
        r = regulated_pressurant(0.1, 30e5, gas='nitrogen', storage_pressure=200e5,
                                 standard_bottle_volume=0.05)
        s = r['storage']
        assert s['bottle_count'] == math.ceil(
            s['bottle_water_volume_m3'] / 0.05)
        assert s['bottle_count'] >= 1

    def test_higher_storage_pressure_smaller_bottle(self):
        r200 = regulated_pressurant(0.1, 30e5, gas='nitrogen',
                                    storage_pressure=200e5)
        r300 = regulated_pressurant(0.1, 30e5, gas='nitrogen',
                                    storage_pressure=300e5)
        assert (r300['storage']['bottle_water_volume_m3']
                < r200['storage']['bottle_water_volume_m3'])

    def test_residual_pressure_above_tank(self):
        r = regulated_pressurant(0.1, 30e5, gas='nitrogen', storage_pressure=200e5,
                                 regulator_margin=0.10)
        assert r['storage']['min_usable_pressure_Pa'] == pytest.approx(
            1.10 * 30e5, rel=1e-9)


class TestRegulatedValidation:
    def test_storage_below_tank_raises(self):
        with pytest.raises(ValueError):
            regulated_pressurant(0.1, 200e5, gas='nitrogen', storage_pressure=50e5)

    def test_min_pressure_above_storage_raises(self):
        # P_tank high enough that (1+margin)*P_tank >= P_store
        with pytest.raises(ValueError):
            regulated_pressurant(0.1, 190e5, gas='nitrogen',
                                 storage_pressure=200e5, regulator_margin=0.10)

    @pytest.mark.parametrize("kw", [
        dict(propellant_volume=-0.1, tank_pressure=30e5),
        dict(propellant_volume=0.1, tank_pressure=0.0),
    ])
    def test_nonpositive_inputs_raise(self, kw):
        with pytest.raises(ValueError):
            regulated_pressurant(gas='nitrogen', **kw)


class TestBlowdown:
    def test_isothermal_final_pressure_hand_calc(self):
        b = blowdown_pressurant(propellant_volume=0.05, initial_ullage_volume=0.05,
                                initial_pressure=50e5, gas='nitrogen',
                                polytropic_n=1.0)
        assert b['final_pressure'] == pytest.approx(25e5, rel=1e-9)
        assert b['blowdown_ratio'] == pytest.approx(2.0, rel=1e-9)
        assert b['final_temperature_K'] == pytest.approx(293.15, rel=1e-9)

    def test_final_pressure_matches_polytropic_law(self):
        P0, Vu0, Vp, n = 50e5, 0.05, 0.03, 1.25
        b = blowdown_pressurant(Vp, Vu0, P0, gas='nitrogen', polytropic_n=n)
        expected = P0 * (Vu0 / (Vu0 + Vp)) ** n
        assert b['final_pressure'] == pytest.approx(expected, rel=1e-12)

    def test_final_temperature_matches_polytropic_law(self):
        P0, Vu0, Vp, n, T0 = 50e5, 0.05, 0.05, 1.3, 300.0
        b = blowdown_pressurant(Vp, Vu0, P0, gas='nitrogen',
                                initial_temperature=T0, polytropic_n=n)
        expected = T0 * (b['final_pressure'] / P0) ** ((n - 1.0) / n)
        assert b['final_temperature_K'] == pytest.approx(expected, rel=1e-12)

    def test_gas_mass_is_trapped_inventory(self):
        # C5 (2026-08-15): hapsolmuş kütle artık gerçek gazla,
        # m = P0*V_u0/(Z0*R*T0); ideal karşılığı ayrı alanda raporlanır.
        b = blowdown_pressurant(0.05, 0.05, 50e5, gas='nitrogen',
                                initial_temperature=293.15)
        R = GAS_PROPERTIES['nitrogen']['R']
        Z0 = b['compressibility_factor_initial']
        assert b['gas_mass_kg'] == pytest.approx(
            50e5 * 0.05 / (Z0 * R * 293.15), rel=1e-9)
        assert b['gas_mass_ideal_gas_kg'] == pytest.approx(
            50e5 * 0.05 / (R * 293.15), rel=1e-9)
        # İç tutarlılık: m_ideal = Z0 * m_gerçek (durum denkleminin doğrudan
        # sonucu — alanlar birbirinden bağımsız uydurulmuş olamaz).
        assert b['gas_mass_ideal_gas_kg'] == pytest.approx(
            Z0 * b['gas_mass_kg'], rel=1e-9)

    def test_final_pressure_monotonic_decreasing_in_n(self):
        """Fixed geometry: higher polytropic n -> lower final pressure."""
        pfs = []
        for n in (1.0, 1.1, 1.2, 1.3, 1.4):
            b = blowdown_pressurant(0.05, 0.05, 50e5, gas='nitrogen',
                                    polytropic_n=n)
            pfs.append(b['final_pressure'])
        assert all(pfs[i] > pfs[i + 1] for i in range(len(pfs) - 1))

    def test_blowdown_ratio_monotonic_increasing_in_n(self):
        ratios = []
        for n in (1.0, 1.1, 1.2, 1.3, 1.4):
            b = blowdown_pressurant(0.05, 0.05, 50e5, gas='nitrogen',
                                    polytropic_n=n)
            ratios.append(b['blowdown_ratio'])
        assert all(ratios[i] < ratios[i + 1] for i in range(len(ratios) - 1))

    def test_final_temperature_drops_for_adiabatic(self):
        iso = blowdown_pressurant(0.05, 0.05, 50e5, gas='nitrogen',
                                  polytropic_n=1.0)
        adia = blowdown_pressurant(0.05, 0.05, 50e5, gas='nitrogen',
                                   polytropic_n=1.4)
        assert adia['final_temperature_K'] < iso['final_temperature_K']

    def test_blowdown_validation(self):
        with pytest.raises(ValueError):
            blowdown_pressurant(-0.05, 0.05, 50e5, gas='nitrogen')


class TestBlowdownRealGas:
    """C5 bekçileri — blowdown dalında gerçek gaz (Z) düzeltmesi.

    ÖLÇÜLDÜ (2026-08-15, CoolProp 6.8.0 = NIST REFPROP tabanlı;
    Helium: Ortiz-Vega 2013 EOS, Nitrogen: Span 2000 EOS; T0 = 293.15 K):
        He 300 bar: Z0 = 1.1413 -> ideal hapsolmuş kütle %14.13 FAZLA
        N2 300 bar: Z0 = 1.1401 -> ideal hapsolmuş kütle %14.01 FAZLA
        He  20 bar: Z0 = 1.0097 -> fark %0.97 (ihmal edilir)
        N2  20 bar: Z0 = 0.9961 -> fark %0.39 (ihmal edilir)
        Z_final (n=1.2, V_u0=10 L, V_p=40 L, 300 bar): He 1.0298, N2 0.9337
    m_ideal / m_gerçek = Z0 olduğundan bağıl fark tam olarak Z0 - 1'dir;
    tolerans bantları bu ölçümlerin etrafına konuldu.
    """

    #: 300 bar sınıfı blowdown örneği: V_p=40 L, V_u0=10 L, T0=293.15 K.
    KW_300BAR = dict(propellant_volume=0.040, initial_ullage_volume=0.010,
                     initial_pressure=300e5, initial_temperature=293.15)

    @pytest.mark.skipif(not HAS_COOLPROP, reason="CoolProp kurulu değil")
    def test_300bar_helium_ideal_vs_real_measurable(self):
        b = blowdown_pressurant(gas='helium', **self.KW_300BAR)
        rel = (b['gas_mass_ideal_gas_kg'] - b['gas_mass_kg']) / b['gas_mass_kg']
        assert 0.10 < rel < 0.18  # ölçülen: 0.1413

    @pytest.mark.skipif(not HAS_COOLPROP, reason="CoolProp kurulu değil")
    def test_300bar_nitrogen_ideal_vs_real_measurable(self):
        b = blowdown_pressurant(gas='nitrogen', **self.KW_300BAR)
        rel = (b['gas_mass_ideal_gas_kg'] - b['gas_mass_kg']) / b['gas_mass_kg']
        assert 0.10 < rel < 0.18  # ölçülen: 0.1401

    @pytest.mark.skipif(not HAS_COOLPROP, reason="CoolProp kurulu değil")
    def test_z_fields_present_and_physical(self):
        b = blowdown_pressurant(gas='helium', **self.KW_300BAR)
        assert b['real_gas'] is True
        assert 1.05 < b['compressibility_factor_initial'] < 1.25  # ölçülen 1.1413
        assert 0.90 < b['compressibility_factor_final'] < 1.20    # ölçülen 1.0298
        assert 'CoolProp' in b['real_gas_model']
        assert 'Z=' in b['model_note']

    @pytest.mark.skipif(not HAS_COOLPROP, reason="CoolProp kurulu değil")
    def test_z_final_physical_for_nitrogen(self):
        b = blowdown_pressurant(gas='nitrogen', **self.KW_300BAR)
        assert 0.90 < b['compressibility_factor_final'] < 1.20    # ölçülen 0.9337

    @pytest.mark.skipif(not HAS_COOLPROP, reason="CoolProp kurulu değil")
    def test_low_pressure_ideal_and_real_agree(self):
        # 20 bar'da ideal ile gerçek gaz farkı küçük olmalı.
        kw = dict(self.KW_300BAR, initial_pressure=20e5)
        he = blowdown_pressurant(gas='helium', **kw)
        rel_he = abs(he['gas_mass_ideal_gas_kg'] - he['gas_mass_kg']) / he['gas_mass_kg']
        assert rel_he < 0.015  # ölçülen: 0.0097
        n2 = blowdown_pressurant(gas='nitrogen', **kw)
        rel_n2 = abs(n2['gas_mass_ideal_gas_kg'] - n2['gas_mass_kg']) / n2['gas_mass_kg']
        assert rel_n2 < 0.010  # ölçülen: 0.0039

    def test_mutation_fixed_z_would_break_guard(self, monkeypatch):
        """MUTASYON DENETİMİ: Z'yi 1.0'a sabitleyen mutant, 300 bar
        bekçisinin dayandığı farkı sıfırlar — yani o bekçi bu mutantı KIRAR.
        (Mutantı burada bilerek kurup bekçi koşulunun artık sağlanmadığını
        gösteriyoruz; bekçinin kendisi mutantsız üstteki testlerde koşuyor.)
        """
        import hrma.analysis.pressurant_sizing as ps
        monkeypatch.setattr(ps, 'compressibility_factor',
                            lambda *a, **k: (1.0, True))
        b = ps.blowdown_pressurant(gas='helium', **self.KW_300BAR)
        rel = (b['gas_mass_ideal_gas_kg'] - b['gas_mass_kg']) / b['gas_mass_kg']
        # Mutant altında gerçek-gaz farkı yok olur...
        assert rel == pytest.approx(0.0, abs=1e-12)
        # ...ve 300 bar bekçisinin koşulu (0.10 < rel < 0.18) sağlanamaz.
        assert not (0.10 < rel < 0.18)
        assert b['compressibility_factor_initial'] == 1.0

    def test_no_coolprop_declares_ideal_gas(self, monkeypatch):
        """CoolProp yok senaryosu: sessiz düşüş yasak — Z=1, real_gas=False
        ve model notunda açık beyan (regüle dalla aynı disiplin)."""
        import hrma.analysis.pressurant_sizing as ps
        monkeypatch.setattr(ps, '_COOLPROP', False)
        b = ps.blowdown_pressurant(gas='helium', **self.KW_300BAR)
        assert b['real_gas'] is False
        assert b['compressibility_factor_initial'] == 1.0
        assert b['compressibility_factor_final'] == 1.0
        assert b['gas_mass_kg'] == pytest.approx(
            b['gas_mass_ideal_gas_kg'], rel=1e-12)
        assert 'ideal gas' in b['real_gas_model']
        assert 'CoolProp unavailable' in b['model_note']


class TestDispatch:
    def test_analyze_pressurant_regulated(self):
        r = analyze_pressurant('regulated', propellant_volume=0.1,
                               tank_pressure=30e5, gas='helium')
        assert r['gas'] == 'helium'
        assert 'isothermal' in r and 'adiabatic' in r

    def test_analyze_pressurant_blowdown(self):
        b = analyze_pressurant('blowdown', propellant_volume=0.05,
                               initial_ullage_volume=0.05, initial_pressure=50e5,
                               gas='nitrogen')
        assert b['blowdown_ratio'] > 1.0

    def test_bad_mode_raises(self):
        with pytest.raises(ValueError):
            analyze_pressurant('turbopump')
