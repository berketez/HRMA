# -*- coding: utf-8 -*-
"""Gaz-gaz (sıkıştırılabilir) enjeksiyon testleri — FFSC/staged combustion.

Kapsam:
  - Sıkıştırılabilir orifis akışı: choked/unchoked ayrımı, kritik basınç
    oranı, süreklilik ve monotonluk (Anderson Böl. 3 / NASA SP-8089).
  - Birim sanity: hava benzeri gaz için analitik choked debi.
  - Raptor mertebesi gaz-gaz coax: eleman sayısı/çapı, ΔP/Pc, J, VR.
  - Girdi doğrulama: ön yakıcı koşulları zorunlu (varsayılan sabit YOK).
  - Gaz-gaz'da SMD None (sahte damlacık sayısı dönmez).
  - Mevcut sıvı-faz API'sinin kırılmadığı (smoke).
"""

import numpy as np
import pytest

from hrma.engines.injector_design import (
    critical_pressure_ratio,
    compressible_orifice_flow,
    design_injector,
    GAS_GAS_J_GOOD,
    GAS_DP_PC_MIN,
)


# ---------------------------------------------------------------------------
# 1. Sıkıştırılabilir orifis akışı — saf fizik
# ---------------------------------------------------------------------------

class TestCompressibleOrifice:

    def test_critical_pressure_ratio_air(self):
        # γ=1.4 → P*/P0 = 0.5283 (bilinen değer)
        assert critical_pressure_ratio(1.4) == pytest.approx(0.5283, abs=1e-3)

    def test_air_choked_mass_flow_analytic(self):
        # γ=1.4, R=287, T0=300 K, P0=10 bar, A=1 cm², Cd=0.85 → boğulmuş.
        # Analitik: ṁ = Cd·A·P0·√(γ/(R·T0))·(2/(γ+1))^((γ+1)/(2(γ-1)))
        g, R, T0 = 1.4, 287.0, 300.0
        A, Cd, P0 = 1e-4, 0.85, 10e5
        analytic = (Cd * A * P0 * np.sqrt(g / (R * T0))
                    * (2.0 / (g + 1.0)) ** ((g + 1.0) / (2.0 * (g - 1.0))))
        st = compressible_orifice_flow(Cd, A, P0, T0, g, R, p_back_pa=1e5)
        assert st['choked'] is True
        assert st['mdot_kg_s'] == pytest.approx(analytic, rel=1e-9)
        # ~0.2 kg/s mertebesi, analitikle ±%1
        assert st['mdot_kg_s'] == pytest.approx(0.198, rel=0.01)

    def test_choked_independent_of_back_pressure(self):
        # Kritik oranın altında: debi arka basınçtan BAĞIMSIZ (sabit).
        g, R, T0, P0, Cd, A = 1.3, 300.0, 700.0, 300e5, 0.85, 1e-4
        prc = critical_pressure_ratio(g)
        # Boğulma bölgesinde birkaç arka basınç
        backs = np.array([0.1, 0.3, 0.5]) * P0
        assert (backs / P0 < prc).all()
        mdots = [compressible_orifice_flow(Cd, A, P0, T0, g, R, pb)['mdot_kg_s']
                 for pb in backs]
        assert np.allclose(mdots, mdots[0], rtol=1e-12)

    def test_unchoked_depends_on_back_pressure_monotonic(self):
        # Kritik oranın üstünde: debi arka basınçla azalır (monoton).
        g, R, T0, P0, Cd, A = 1.3, 300.0, 700.0, 300e5, 0.85, 1e-4
        prc = critical_pressure_ratio(g)
        prs = np.linspace(prc + 1e-3, 0.98, 25)
        mdots = [compressible_orifice_flow(Cd, A, P0, T0, g, R, pr * P0)['mdot_kg_s']
                 for pr in prs]
        # Arka basınç arttıkça (pr↑) debi azalır
        assert all(mdots[i] > mdots[i + 1] for i in range(len(mdots) - 1))

    def test_continuity_at_critical(self):
        # İki dal kritik oranda sürekli (izentropik akı maksimumu boğulmada).
        g, R, T0, P0, Cd, A = 1.25, 320.0, 800.0, 250e5, 0.9, 2e-4
        prc = critical_pressure_ratio(g)
        below = compressible_orifice_flow(Cd, A, P0, T0, g, R, (prc - 1e-4) * P0)
        above = compressible_orifice_flow(Cd, A, P0, T0, g, R, (prc + 1e-4) * P0)
        assert below['choked'] is True
        assert above['choked'] is False
        assert below['mdot_kg_s'] == pytest.approx(above['mdot_kg_s'], rel=2e-3)

    def test_unchoked_mach_below_one(self):
        g, R, T0, P0, Cd, A = 1.3, 277.0, 750.0, 330e5, 0.85, 1e-4
        st = compressible_orifice_flow(Cd, A, P0, T0, g, R, p_back_pa=300e5)
        assert st['choked'] is False
        assert 0.0 < st['mach'] < 1.0
        # Çıkış basıncı = arka basınç (subsonik)
        assert st['p_exit_pa'] == pytest.approx(300e5, rel=1e-12)

    def test_choked_exit_is_sonic(self):
        g, R, T0, P0, Cd, A = 1.3, 277.0, 750.0, 330e5, 0.85, 1e-4
        st = compressible_orifice_flow(Cd, A, P0, T0, g, R, p_back_pa=50e5)
        assert st['choked'] is True
        assert st['mach'] == pytest.approx(1.0)
        # Boğazda sonik hız = √(γ R T*)
        t_star = T0 * 2.0 / (g + 1.0)
        assert st['v_exit_m_s'] == pytest.approx(np.sqrt(g * R * t_star), rel=1e-9)


# ---------------------------------------------------------------------------
# 2. Gaz-gaz coax tasarımı — Raptor mertebesi
# ---------------------------------------------------------------------------

def _raptor_spec(**over):
    spec = {
        'motor_type': 'liquid',
        'injector_type': 'gas_gas_coaxial',
        'mdot_ox': 705.0,     # kg/s (ox-zengin ön yakıcıdan ~tüm ox)
        'mdot_fuel': 195.0,   # kg/s (yakıt-zengin ön yakıcıdan ~tüm yakıt)
        'Pc_bar': 300.0,      # ana oda basıncı (arka basınç)
        'gas_ox': {'T0_K': 750.0, 'P0_bar': 330.0, 'gamma': 1.3, 'MW': 30.0},
        'gas_fuel': {'T0_K': 800.0, 'P0_bar': 330.0, 'gamma': 1.3, 'MW': 18.0},
    }
    spec.update(over)
    return spec


class TestGasGasCoaxDesign:

    def test_raptor_scale_success(self):
        r = design_injector(_raptor_spec())
        assert r['status'] == 'success'
        assert r['injector_type'] == 'gas_gas_coaxial'

    def test_dp_pc_is_ten_percent(self):
        # P0=330, Pc=300 → ΔP/Pc = 30/300 = 0.10
        r = design_injector(_raptor_spec())
        assert r['ox_circuit']['dp_pc_ratio'] == pytest.approx(0.10, rel=1e-6)
        assert r['fuel_circuit']['dp_pc_ratio'] == pytest.approx(0.10, rel=1e-6)

    def test_element_count_and_diameter_reasonable(self):
        # "yüzlerce eleman, mm mertebesi çaplar"
        r = design_injector(_raptor_spec())
        geo = r['gas_gas_geometry']
        n = geo['n_elements']
        d_in = geo['inner_post_d_mm']
        gap = geo['annulus_gap_mm']
        assert 50 <= n <= 5000
        assert 0.5 <= d_in <= 15.0        # mm mertebesi iç post
        assert gap > 0.0                  # pozitif anülüs boşluğu
        assert geo['element_outer_d_mm'] > d_in

    def test_unchoked_at_ten_percent_dp(self):
        # ΔP/Pc=%10 çok küçük → subsonik (boğulmamış) akış beklenir
        r = design_injector(_raptor_spec())
        assert r['ox_circuit']['choked'] is False
        assert r['fuel_circuit']['choked'] is False

    def test_momentum_flux_ratio_and_velocity_ratio(self):
        r = design_injector(_raptor_spec())
        mom = r['momentum']
        assert mom['momentum_ratio'] is not None
        assert mom['velocity_ratio'] is not None
        # Bu senaryoda J ~ O(1), VR > 1 (hafif gaz daha hızlı)
        assert 0.2 < mom['momentum_ratio'] < 20.0
        assert mom['velocity_ratio'] > 1.0

    def test_smd_is_none_for_gas_gas(self):
        # Atomizasyon/SMD gaz-gaz için anlamsız → None (sahte sayı yok)
        r = design_injector(_raptor_spec())
        atom = r['atomization']
        assert atom['smd_ox_um'] is None
        assert atom['smd_fuel_um'] is None
        assert atom['correlation'] == 'not_modelled'

    def test_high_dp_gives_choked(self):
        # P0'ı çok yükseltince (P0/Pc kritik oranı geçer) boğulma başlar
        spec = _raptor_spec()
        spec['gas_ox'] = {'T0_K': 750.0, 'P0_bar': 900.0, 'gamma': 1.3, 'MW': 30.0}
        r = design_injector(spec)
        assert r['status'] == 'success'
        assert r['ox_circuit']['choked'] is True

    def test_references_present(self):
        r = design_injector(_raptor_spec())
        refs = ' '.join(r['references'])
        assert 'Anderson' in refs
        assert 'SP-8089' in refs


# ---------------------------------------------------------------------------
# 3. Girdi doğrulama — varsayılan sabit YOK
# ---------------------------------------------------------------------------

class TestGasGasValidation:

    def test_missing_gas_ox_raises(self):
        spec = _raptor_spec()
        del spec['gas_ox']
        with pytest.raises(ValueError, match='gas_ox'):
            design_injector(spec)

    def test_missing_p0_raises(self):
        spec = _raptor_spec()
        del spec['gas_ox']['P0_bar']
        with pytest.raises(ValueError, match='P0_bar'):
            design_injector(spec)

    def test_missing_mw_and_r_raises(self):
        spec = _raptor_spec()
        del spec['gas_ox']['MW']
        with pytest.raises(ValueError, match="R.*MW|MW"):
            design_injector(spec)

    def test_r_overrides_mw(self):
        # R doğrudan verilince MW gölgede kalır (aynı sonuç)
        spec_mw = _raptor_spec()
        spec_r = _raptor_spec()
        spec_r['gas_ox'] = {'T0_K': 750.0, 'P0_bar': 330.0, 'gamma': 1.3,
                            'R': 8314.462618 / 30.0}
        r_mw = design_injector(spec_mw)
        r_r = design_injector(spec_r)
        assert (r_mw['ox_circuit']['exit_density_kg_m3']
                == pytest.approx(r_r['ox_circuit']['exit_density_kg_m3'], rel=1e-9))

    def test_missing_fuel_flow_raises(self):
        spec = _raptor_spec()
        spec['mdot_fuel'] = 0.0
        with pytest.raises(ValueError, match='mdot_fuel'):
            design_injector(spec)

    def test_p0_below_pc_raises(self):
        spec = _raptor_spec()
        spec['gas_ox']['P0_bar'] = 250.0  # < Pc=300
        with pytest.raises(ValueError, match='oda basınc|ΔP'):
            design_injector(spec)

    def test_hybrid_motor_rejected(self):
        spec = _raptor_spec()
        spec['motor_type'] = 'hybrid'
        with pytest.raises(ValueError, match='gas_gas_coaxial'):
            design_injector(spec)


# ---------------------------------------------------------------------------
# 4. Mevcut sıvı-faz API'si kırılmadı (smoke)
# ---------------------------------------------------------------------------

class TestLiquidApiUnbroken:

    def test_liquid_impinging_still_designs(self):
        r = design_injector({
            'motor_type': 'liquid',
            'injector_type': 'impinging_doublet',
            'mdot_ox': 10.0, 'mdot_fuel': 4.0,
            'rho_ox': 1140.0, 'rho_fuel': 810.0,
            'Pc_bar': 60.0,
        })
        assert r['status'] == 'success'
        assert r['injector_type'] == 'impinging_doublet'
        # Sıvıda SMD hesaplanır (gaz-gaz'dan farklı)
        assert r['atomization']['smd_ox_um'] is not None

    def test_liquid_showerhead_hybrid_still_designs(self):
        r = design_injector({
            'motor_type': 'hybrid',
            'injector_type': 'showerhead',
            'mdot_ox': 2.0,
            'Pc_bar': 30.0,
            'rho_ox': 800.0,
        })
        assert r['status'] == 'success'
