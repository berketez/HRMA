# -*- coding: utf-8 -*-
"""Enjektör tasarım modülü doğrulamaları (docs/10_Enjektor_ARGE.md Bölüm E).

Assert'ler analitik/literatür bazlıdır — uydurma referans yok:
- Ö1: SPI kapalı form (su, soğuk akış) — elle hesaplanmış 0.1825 kg/s
- Ö2: doymuş N₂O NHNE — κ=1 kesinliği, orta-nokta özdeşliği, HEM<NHNE<SPI
- Ö3: LOX/RP-1 unlike doublet — MR=0.49, Rupe=0.70 (uyarı senaryosu)
- Cd tablosu (SP-8089), Nurick flip kuralı, SP-8089 chug kuralı,
  Giffen–Muraszew swirl özdeşlikleri, Cheng pintle açısı, manifold kuralları
"""

import numpy as np
import pytest

from hrma.engines.injector_design import (
    design_injector, spi_mass_flow, nhne_mass_flow, discharge_coefficient,
    hydraulic_flip_risk, smd_elkotb, smd_lefebvre_swirl, smd_impinging,
    swirl_solve, swirl_K_from_theta, pintle_spray_angle,
)

N2O_T = 293.15          # K — Ö2 koşulu
N2O_PSAT_BAR = 50.4     # bar (±0.5 bandında doğrulanır)


def _o3_spec(**kw):
    """Ö3 girdileri: LOX/RP-1 doublet, n=16/16 sabit (spec A.10)."""
    spec = {
        'motor_type': 'liquid', 'injector_type': 'impinging_doublet',
        'mdot_ox': 1.20, 'mdot_fuel': 0.50,
        'rho_ox': 1141.0, 'rho_fuel': 810.0,
        'Pc_bar': 20.0, 'dp_ratio_ox': 0.20, 'dp_ratio_fuel': 0.20,
        'n_orifices_ox': 16, 'n_orifices_fuel': 16,
    }
    spec.update(kw)
    return spec


# ---------------------------------------------------------------------------
# 1) SPI kapalı form (Ö1)
# ---------------------------------------------------------------------------

class TestSPI:
    def test_spi_closed_form(self):
        """Ö1: su, ΔP=10 bar, Cd=0.65, 8×1.0 mm → ṁ=0.1825 kg/s, v=29.1 m/s."""
        area = 8 * np.pi * (0.5e-3) ** 2
        mdot = spi_mass_flow(0.65, area, 998.0, 10e5)
        assert mdot == pytest.approx(0.1825, abs=1e-3)
        v = 0.65 * np.sqrt(2 * 10e5 / 998.0)
        assert v == pytest.approx(29.1, abs=0.1)
        # ṁ = ρ·A·v özdeşliği (binde bir)
        assert mdot == pytest.approx(998.0 * area * v, rel=1e-3)


# ---------------------------------------------------------------------------
# 2-3) N₂O NHNE
# ---------------------------------------------------------------------------

class TestNHNE:
    def test_nhne_saturated_is_midpoint(self):
        """Doymuş giriş (P₁=P_sat): κ=1 KESİN, NHNE=(SPI+HEM)/2 KESİN,
        sıralama HEM < NHNE < SPI (spec Ö2)."""
        area = np.pi * (0.75e-3) ** 2
        psat = None
        # psat'ı modülün kendi tablosundan türet (bağımsız sabit yazmadan):
        r_probe = nhne_mass_flow(0.66, area, 100.0, 30.0, 100.0, N2O_T)
        # p1=pv=100 sahte — gerçek psat'ı hibrit yolundan al:
        d = design_injector({'motor_type': 'hybrid', 'mdot_ox': 0.5,
                             'Pc_bar': 30.0, 'fluid_ox': 'n2o',
                             'T_ox_K': N2O_T})
        psat = d['ox_circuit']['nhne']['p_sat_bar']
        r = nhne_mass_flow(0.66, area, psat, 30.0, psat, N2O_T)
        assert r['kappa'] == pytest.approx(1.0, abs=1e-12)
        mid = 0.5 * (r['mdot_spi_kg_s'] + r['mdot_hem_kg_s'])
        assert r['mdot_kg_s'] == pytest.approx(mid, rel=1e-12)
        assert r['mdot_hem_kg_s'] < r['mdot_kg_s'] < r['mdot_spi_kg_s']
        # Ö2 mertebe kontrolü: SPI ~0.065 kg/s civarı (tablo psat'ına bağlı)
        assert r['mdot_spi_kg_s'] == pytest.approx(0.0654, rel=0.05)

    def test_nhne_subcooled_limit(self):
        """Kuvvetli az-soğutma (P₂ > P_v): flaşlama yok → NHNE → SPI
        (oran ≥ 0.97; burada tam 1.0)."""
        area = np.pi * (0.75e-3) ** 2
        psat = 50.5
        r = nhne_mass_flow(0.66, area, psat + 30.0, psat + 5.0, psat, N2O_T)
        assert r['mdot_kg_s'] / r['mdot_spi_kg_s'] >= 0.97
        assert r['quality_out'] == 0.0

    def test_nhne_flashing_between_models(self):
        """Az-soğutulmuş ama flaşlayan durumda (P₂ < P_v < P₁):
        HEM ≤ NHNE ≤ SPI ve κ > 1 (SPI'a doğru ağırlık)."""
        area = np.pi * (0.75e-3) ** 2
        psat = 50.5
        r = nhne_mass_flow(0.66, area, psat + 30.0, 30.0, psat, N2O_T)
        assert r['kappa'] > 1.0
        assert r['mdot_hem_kg_s'] <= r['mdot_kg_s'] <= r['mdot_spi_kg_s']


# ---------------------------------------------------------------------------
# 4-5) Cd tablosu ve hydraulic flip
# ---------------------------------------------------------------------------

class TestOrificeHydraulics:
    def test_cd_table(self):
        cd, why = discharge_coefficient('sharp', 0.5)
        assert 0.61 <= cd <= 0.65 and why
        cd, why = discharge_coefficient('sharp', 4.0)
        assert 0.75 <= cd <= 0.85 and why
        cd, why = discharge_coefficient('radiused', 4.0)
        assert 0.88 <= cd <= 0.95 and why

    def test_cd_invalid_inlet(self):
        with pytest.raises(ValueError):
            discharge_coefficient('conical', 4.0)

    def test_hydraulic_flip_flag(self):
        assert hydraulic_flip_risk('sharp', 3.0, 1.2) is True
        assert hydraulic_flip_risk('radiused', 3.0, 1.2) is False
        assert hydraulic_flip_risk('sharp', 8.0, 1.2) is False
        assert hydraulic_flip_risk('sharp', 3.0, 2.5) is False


# ---------------------------------------------------------------------------
# 6) Chug guard
# ---------------------------------------------------------------------------

class TestStability:
    def test_chug_guard_low_dp(self):
        d = design_injector({
            'motor_type': 'liquid', 'mdot_ox': 1.0, 'mdot_fuel': 0.4,
            'rho_ox': 1141.0, 'rho_fuel': 810.0, 'Pc_bar': 20.0,
            'dp_ratio_ox': 0.08, 'dp_ratio_fuel': 0.08})
        assert d['stability']['chug_ok'] is False
        assert any('chug' in w.lower() for w in d['warnings_tr'])

    def test_chug_guard_ok(self):
        d = design_injector({
            'motor_type': 'liquid', 'mdot_ox': 1.0, 'mdot_fuel': 0.4,
            'rho_ox': 1141.0, 'rho_fuel': 810.0, 'Pc_bar': 20.0,
            'dp_ratio_ox': 0.20, 'dp_ratio_fuel': 0.20})
        assert d['stability']['chug_ok'] is True


# ---------------------------------------------------------------------------
# 7) Doublet momentum + Rupe (Ö3 — uyarı senaryosu)
# ---------------------------------------------------------------------------

class TestDoublet:
    def test_doublet_momentum_and_rupe(self):
        d = design_injector(_o3_spec())
        m = d['momentum']
        assert m is not None
        assert m['momentum_ratio'] == pytest.approx(0.49, abs=0.02)
        assert m['rupe_factor'] == pytest.approx(0.70, abs=0.03)
        assert m['ok'] is False
        assert any('momentum' in w.lower() for w in d['warnings_tr'])
        # Ö3 delik çapları (n=16 sabitken, Cd tablo değeriyle ölçekli)
        assert d['ox_circuit']['n_orifices'] == 16
        assert d['fuel_circuit']['n_orifices'] == 16


# ---------------------------------------------------------------------------
# 8) Delik kısıtları
# ---------------------------------------------------------------------------

class TestOrificePlan:
    def test_orifice_constraints(self):
        d = design_injector({
            'motor_type': 'liquid', 'mdot_ox': 2.0, 'mdot_fuel': 0.8,
            'rho_ox': 1141.0, 'rho_fuel': 810.0, 'Pc_bar': 20.0,
            'orifice_constraints': {'n_max': 8}})
        ox = d['ox_circuit']
        assert ox['n_orifices'] <= 8
        # Alan toplamı istenen debiyi ±%1 sağlar: ṁ = Cd·A·√(2ρΔP)
        a = ox['total_area_mm2'] * 1e-6
        mdot = spi_mass_flow(ox['cd'], a, 1141.0,
                             ox['delta_p_bar'] * 1e5)
        assert mdot == pytest.approx(2.0, rel=0.01)
        # 2 kg/s'yi 8 delikte geçirmek tercih bandını (≤2.5 mm) aşar → uyarı
        assert any('band' in w.lower() or 'çap' in w.lower()
                   for w in d['warnings_tr'])


# ---------------------------------------------------------------------------
# 9) Pintle
# ---------------------------------------------------------------------------

class TestPintle:
    def test_pintle_spray_angle_formula(self):
        """Cheng 2017: TMR=1 → θ = arccos(1/2) = 60° (kesin)."""
        assert pintle_spray_angle(1.0) == pytest.approx(60.0, abs=1e-9)
        assert pintle_spray_angle(0.0) == pytest.approx(0.0, abs=1e-9)

    def test_pintle_geometry(self):
        # TMR = (ṁv)_f/(ṁv)_ox = 1 hedefi: v ∝ √(ΔP/ρ) olduğundan
        # ṁ_f·√(ΔP_f/ρ_f) = ṁ_ox·√(ΔP_ox/ρ_ox) sağlayacak debiler seçildi
        rho_ox, rho_f, pc = 1141.0, 810.0, 20.0
        v_ratio = np.sqrt(rho_ox / rho_f)   # aynı ΔP'de v_f/v_ox
        mdot_ox = 1.0
        mdot_f = mdot_ox / v_ratio          # (ṁv)_f = (ṁv)_ox
        d = design_injector({
            'motor_type': 'liquid', 'injector_type': 'pintle',
            'mdot_ox': mdot_ox, 'mdot_fuel': mdot_f,
            'rho_ox': rho_ox, 'rho_fuel': rho_f, 'Pc_bar': pc})
        pg = d['pintle_geometry']
        assert pg is not None
        assert d['momentum']['tmr'] == pytest.approx(1.0, abs=0.02)
        assert d['atomization']['spray_cone_half_angle_deg'] == \
            pytest.approx(60.0, abs=5.0)
        assert pg['bf'] == pytest.approx(0.58, abs=0.05)
        assert 0.7 <= pg['ls_over_dp'] <= 1.0
        assert pg['annulus_gap_mm'] > 0
        assert pg['n_radial_holes'] >= 4

    def test_pintle_rejected_for_hybrid(self):
        with pytest.raises(ValueError):
            design_injector({'motor_type': 'hybrid', 'injector_type': 'pintle',
                             'mdot_ox': 1.0, 'Pc_bar': 30.0,
                             'fluid_ox': 'n2o', 'T_ox_K': N2O_T})


# ---------------------------------------------------------------------------
# 10) Swirl (Giffen–Muraszew)
# ---------------------------------------------------------------------------

class TestSwirl:
    def test_swirl_solution(self):
        sw = swirl_solve(1.0)
        X, cd, theta = sw['X'], sw['cd'], sw['theta_deg']
        assert 0.0 < X < 1.0
        assert cd < 0.5
        # K↔X bağıntısı: K = √(32/π²)·√((1−X)³/X²)
        K_back = np.sqrt(32 / np.pi ** 2) * np.sqrt((1 - X) ** 3 / X ** 2)
        assert K_back == pytest.approx(1.0, rel=1e-6)
        # sinθ = (π/2)·Cd/(K·(1+√X)) özdeşliği
        sin_t = (np.pi / 2) * cd / (1.0 * (1 + np.sqrt(X)))
        assert np.sin(np.radians(theta)) == pytest.approx(sin_t, rel=1e-9)
        # Cd = √((1−X)³/(1+X)) özdeşliği
        assert cd == pytest.approx(np.sqrt((1 - X) ** 3 / (1 + X)), rel=1e-9)

    def test_swirl_theta_target_solved(self):
        """Ulaşılabilir hedef (15°, bağıntı tavanı ~18°): çözüm ±3° tutturur.

        Not: spec'in 45° varsayılan hedefi Giffen–Muraszew sinθ bağıntısının
        tavanının üstündedir; modül bu durumda K=1'e düşüp uyarı verir
        (aşağıdaki test) — bu bilinçli bir sapmadır, ARGE raporundaki formül
        korunmuştur.
        """
        K = swirl_K_from_theta(15.0)
        assert swirl_solve(K)['theta_deg'] == pytest.approx(15.0, abs=3.0)

    def test_swirl_unreachable_theta_falls_back(self):
        d = design_injector({
            'motor_type': 'hybrid', 'injector_type': 'swirl',
            'mdot_ox': 1.2, 'Pc_bar': 30.0, 'fluid_ox': 'n2o',
            'T_ox_K': N2O_T, 'swirl': {'theta_target_deg': 45.0}})
        sg = d['swirl_geometry']
        assert sg is not None
        assert sg['K'] == pytest.approx(1.0)
        assert any('tavan' in w for w in d['warnings_tr'])
        # Cd_swirl tipik bantta (0.2-0.45) ve film kalınlığı pozitif
        assert 0.2 <= sg['cd_swirl'] <= 0.45
        assert sg['film_thickness_mm'] > 0


# ---------------------------------------------------------------------------
# 11) SMD korelasyonları
# ---------------------------------------------------------------------------

class TestSMD:
    def test_smd_monotonic_swirl(self):
        lo = smd_lefebvre_swirl(0.02, 2e-4, 1.0, 20e5, 5.0)
        hi = smd_lefebvre_swirl(0.02, 2e-4, 1.0, 5e5, 5.0)
        assert lo < hi  # ΔP arttıkça damla küçülür

    def test_smd_elkotb_physical_band(self):
        """Ö1 koşulları (su, ΔP=10 bar): 20-1000 µm fiziksel bandında."""
        nu = 2e-4 / 998.0
        smd = smd_elkotb(nu, 0.02, 998.0, 5.0, 10e5)
        assert 20e-6 < smd < 1000e-6

    def test_smd_impinging_we_scaling(self):
        """D₃₂ = C·d·We^(−1/3): hız 8× → We 64× → SMD 4× küçülür."""
        d1 = smd_impinging(1e-3, 10.0, 1000.0, 0.02)
        d2 = smd_impinging(1e-3, 80.0, 1000.0, 0.02)
        assert d1 / d2 == pytest.approx(4.0, rel=1e-6)


# ---------------------------------------------------------------------------
# 12) Manifold kuralları
# ---------------------------------------------------------------------------

class TestManifold:
    def test_manifold_rule(self):
        for spec in [
            {'motor_type': 'hybrid', 'mdot_ox': 1.2, 'Pc_bar': 30.0,
             'fluid_ox': 'n2o', 'T_ox_K': N2O_T},
            _o3_spec(),
        ]:
            d = design_injector(spec)
            for circ in (d['ox_circuit'], d['fuel_circuit']):
                if circ is None:
                    continue
                assert circ['manifold']['v_ratio'] <= 0.2
                assert circ['manifold']['area_ratio'] >= 4.0


# ---------------------------------------------------------------------------
# 13-14) Motor tipi yolları ve doğrulama
# ---------------------------------------------------------------------------

class TestMotorPaths:
    def test_hybrid_path(self):
        d = design_injector({'motor_type': 'hybrid', 'mdot_ox': 1.2,
                             'Pc_bar': 30.0, 'fluid_ox': 'n2o',
                             'T_ox_K': N2O_T})
        assert d['fuel_circuit'] is None
        ox = d['ox_circuit']
        assert ox['flow_model'] == 'NHNE'
        assert ox['nhne']['p_sat_bar'] == pytest.approx(N2O_PSAT_BAR, abs=0.5)
        # Doymuş tank varsayılanı: κ = 1 (P₁ = P_sat)
        assert ox['nhne']['kappa'] == pytest.approx(1.0, abs=1e-9)
        assert d['status'] == 'success'

    def test_liquid_requires_fuel(self):
        with pytest.raises(ValueError) as exc:
            design_injector({'motor_type': 'liquid', 'mdot_ox': 1.0,
                             'rho_ox': 1141.0, 'Pc_bar': 20.0})
        assert 'mdot_fuel' in str(exc.value)

    def test_invalid_motor_type(self):
        with pytest.raises(ValueError):
            design_injector({'motor_type': 'ion', 'mdot_ox': 1.0,
                             'Pc_bar': 20.0})

    def test_contract_keys_present(self):
        """B.2 şemasının üst düzey anahtarları eksiksiz."""
        d = design_injector(_o3_spec())
        for key in ('status', 'motor_type', 'injector_type', 'ox_circuit',
                    'fuel_circuit', 'pattern', 'atomization', 'momentum',
                    'pintle_geometry', 'swirl_geometry', 'stability',
                    'warnings_tr', 'assumptions_tr', 'references'):
            assert key in d, f'şema anahtarı eksik: {key}'
        for key in ('mdot_kg_s', 'delta_p_bar', 'dp_pc_ratio', 'velocity_m_s',
                    'cd', 'cd_basis', 'n_orifices', 'orifice_d_mm',
                    'total_area_mm2', 'flow_model', 'nhne',
                    'cavitation_number', 'hydraulic_flip_risk', 'manifold'):
            assert key in d['ox_circuit'], f'devre anahtarı eksik: {key}'


# ---------------------------------------------------------------------------
# 15) Endpoint sözleşmesi (backend kablolandıysa)
# ---------------------------------------------------------------------------

class TestEndpoint:
    def test_endpoint_contract(self):
        from hrma.app import app
        client = app.test_client()
        body = {'motor_type': 'liquid', 'injector_type': 'impinging_doublet',
                'mdot_ox': 1.2, 'mdot_fuel': 0.5, 'rho_ox': 1141.0,
                'rho_fuel': 810.0, 'Pc_bar': 20.0}
        resp = client.post('/api/injector-design', json=body)
        if resp.status_code == 404:
            pytest.skip('/api/injector-design henüz kablolanmadı '
                        '(backend ajanı bekleniyor)')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'success'
        assert isinstance(data['design']['ox_circuit']['n_orifices'], int)
        # Bozuk gövde → 400
        resp = client.post('/api/injector-design',
                           json={'motor_type': 'liquid'})
        assert resp.status_code == 400
        assert resp.get_json()['status'] == 'error'
