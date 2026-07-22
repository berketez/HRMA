"""Su koçu (water hammer) besleme hattı analizi doğrulama testleri.

El-hesabı çapaları (Wylie & Streeter, "Fluid Transients"; Joukowsky 1898):

- Rijit borudaki ses hızı a = sqrt(K/rho): su için ~1481 m/s (K=2.19 GPa,
  rho=998) — literatürle uyumlu.
- Klasik çelik boru örneği (K=2.19 GPa, rho=998, D=0.5 m, t=5 mm, E=200 GPa):
  esneklik düzeltmeli a ~= 1023.4 m/s, dv=2 m/s -> dP ~= 20.43 bar.
- Joukowsky dP = rho*a*dv birim tutarlılığı (rho=1000, a=1200, dv=2 -> 2.4 MPa).
- Yavaş kapanma limitleri: t_close -> t_c iken ani değere, t_close -> sonsuz
  iken sıfıra.
"""

import math

import pytest

from hrma.analysis.water_hammer import (
    WaterHammerAnalyzer,
    wave_speed,
    joukowsky_pressure_rise,
    critical_closure_time,
    slow_closure_pressure_rise,
    FLUID_PROPERTIES,
)


# ===========================================================================
# Modül-düzeyi analitik yardımcılar (saf el hesabı)
# ===========================================================================
class TestWaveSpeed:
    def test_rigid_water_matches_sound_speed(self):
        """Rijit borulu su hızı a = sqrt(K/rho) ~= 1481 m/s (K=2.19 GPa)."""
        a_el, a_rigid = wave_speed(2.19e9, 998.0, 0.5, 0.005, 200e9)
        assert a_rigid == pytest.approx(math.sqrt(2.19e9 / 998.0), rel=1e-12)
        assert a_rigid == pytest.approx(1481.35, rel=1e-3)

    def test_elasticity_reduces_wave_speed(self):
        """Esneklik düzeltmesi dalga hızını DAİMA düşürür (a_el < a_rigid)."""
        a_el, a_rigid = wave_speed(2.19e9, 998.0, 0.5, 0.005, 200e9)
        assert a_el < a_rigid
        # Klasik çelik boru örneği el-hesabı: ~1023.4 m/s
        assert a_el == pytest.approx(1023.45, rel=1e-3)

    def test_stiffer_pipe_approaches_rigid_speed(self):
        """Daha sert/kalın boru (E*t büyük) rijit hıza yaklaşır."""
        a_thin, a_rigid = wave_speed(2.19e9, 998.0, 0.5, 0.005, 200e9)
        a_thick, _ = wave_speed(2.19e9, 998.0, 0.5, 0.050, 200e9)
        assert a_thin < a_thick < a_rigid

    def test_lower_bulk_modulus_lowers_speed(self):
        """Düşük bulk modül (N2O) su hızının çok altında dalga hızı verir."""
        a_water, _ = wave_speed(2.19e9, 998.0, 0.5, 0.005, 200e9)
        a_n2o, _ = wave_speed(0.19e9, 785.0, 0.5, 0.005, 200e9)
        assert a_n2o < a_water

    def test_wave_speed_rejects_nonpositive(self):
        for bad in ((0.0, 998.0, 0.5, 0.005, 200e9),
                    (2.19e9, 0.0, 0.5, 0.005, 200e9),
                    (2.19e9, 998.0, -0.5, 0.005, 200e9),
                    (2.19e9, 998.0, 0.5, 0.0, 200e9),
                    (2.19e9, 998.0, 0.5, 0.005, 0.0)):
            with pytest.raises(ValueError):
                wave_speed(*bad)


class TestJoukowsky:
    def test_hand_calc_pressure_rise(self):
        """dP = rho*a*dv birim tutarlılığı: 1000*1200*2 = 2.4 MPa (tam)."""
        dp = joukowsky_pressure_rise(1000.0, 1200.0, 2.0)
        assert dp == pytest.approx(2.4e6, rel=1e-12)

    def test_uses_absolute_velocity_change(self):
        """Negatif hız değişimi (yön) aynı büyüklükte basınç verir."""
        assert (joukowsky_pressure_rise(1000.0, 1200.0, -2.0)
                == pytest.approx(2.4e6, rel=1e-12))

    def test_classic_steel_pipe_example(self):
        """Klasik çelik boru su vakası: dP ~= 20.43 bar (el hesabı)."""
        a_el, _ = wave_speed(2.19e9, 998.0, 0.5, 0.005, 200e9)
        dp = joukowsky_pressure_rise(998.0, a_el, 2.0)
        assert dp / 1e5 == pytest.approx(20.428, rel=1e-3)

    def test_rejects_nonpositive(self):
        with pytest.raises(ValueError):
            joukowsky_pressure_rise(0.0, 1200.0, 2.0)
        with pytest.raises(ValueError):
            joukowsky_pressure_rise(1000.0, 0.0, 2.0)


class TestCriticalTime:
    def test_hand_calc(self):
        """t_c = 2L/a: L=1000 m, a=1000 m/s -> 2.0 s (tam)."""
        assert critical_closure_time(1000.0, 1000.0) == pytest.approx(2.0, rel=1e-12)

    def test_rejects_nonpositive(self):
        with pytest.raises(ValueError):
            critical_closure_time(0.0, 1000.0)
        with pytest.raises(ValueError):
            critical_closure_time(1000.0, 0.0)


class TestSlowClosure:
    def test_returns_instant_at_or_below_critical(self):
        """t_close <= t_c -> tam Joukowsky (ani) değeri döner."""
        assert slow_closure_pressure_rise(1e6, 1.0, 1.0) == pytest.approx(1e6)
        assert slow_closure_pressure_rise(1e6, 1.0, 0.5) == pytest.approx(1e6)

    def test_approaches_instant_as_tclose_to_tc(self):
        """t_close -> t_c^+ iken yavaş değer ani değere yaklaşır."""
        dp = 1e6
        near = slow_closure_pressure_rise(dp, 1.0, 1.0 + 1e-6)
        assert near == pytest.approx(dp, rel=1e-5)

    def test_approaches_zero_as_tclose_large(self):
        """t_close -> sonsuz iken yavaş basınç artışı sıfıra gider."""
        dp = 1e6
        assert slow_closure_pressure_rise(dp, 1.0, 1e9) == pytest.approx(1e-3, abs=1e-6)

    def test_monotonic_decreasing(self):
        """Kapanma süresi arttıkça basınç artışı azalır (t_close > t_c bölgesi)."""
        dp = 1e6
        vals = [slow_closure_pressure_rise(dp, 1.0, tc) for tc in (2, 5, 10, 50)]
        assert all(vals[i] > vals[i + 1] for i in range(len(vals) - 1))

    def test_michaud_arithmetic_form(self):
        """dP_slow = dP*(t_c/t_close) = 2*rho*L*dv/t_close (iki form özdeş)."""
        rho, L, dv, a = 998.0, 100.0, 2.0, 1000.0
        t_c = 2.0 * L / a
        dp_inst = rho * a * dv
        t_close = 5.0 * t_c
        form1 = slow_closure_pressure_rise(dp_inst, t_c, t_close)
        form2 = 2.0 * rho * L * dv / t_close
        assert form1 == pytest.approx(form2, rel=1e-12)

    def test_rejects_nonpositive(self):
        with pytest.raises(ValueError):
            slow_closure_pressure_rise(1e6, 1.0, 0.0)
        with pytest.raises(ValueError):
            slow_closure_pressure_rise(1e6, 0.0, 5.0)


# ===========================================================================
# Sıvı özellik tablosu
# ===========================================================================
class TestFluidTable:
    def test_required_fluids_present(self):
        for key in ('water', 'n2o', 'rp1', 'lox'):
            assert key in FLUID_PROPERTIES

    def test_source_and_band_fields(self):
        """Her kaydın kaynak, bant, güven ve pozitif fiziksel değerleri olmalı."""
        for key, rec in FLUID_PROPERTIES.items():
            assert rec.get('source'), f"{key} missing source"
            assert rec['bulk_modulus_Pa'] > 0
            assert rec['density_kg_m3'] > 0
            assert rec.get('confidence') in ('high', 'medium', 'low')
            band = rec.get('bulk_modulus_band_Pa')
            assert band is not None and band[0] <= rec['bulk_modulus_Pa'] <= band[1]

    def test_propellants_marked_approximate(self):
        """Kriyojen/N2O/RP-1 kayıtları 'approximate' notu taşımalı."""
        for key in ('n2o', 'rp1', 'lox'):
            assert 'APPROXIMATE' in FLUID_PROPERTIES[key]['source'].upper()

    def test_water_high_confidence(self):
        assert FLUID_PROPERTIES['water']['confidence'] == 'high'

    def test_water_sound_speed_physical(self):
        """K/rho'dan su ses hızı literatür aralığında (~1480 m/s)."""
        rec = FLUID_PROPERTIES['water']
        a = math.sqrt(rec['bulk_modulus_Pa'] / rec['density_kg_m3'])
        assert 1450.0 < a < 1520.0


# ===========================================================================
# Tam analiz (analyze)
# ===========================================================================
class TestAnalyze:
    def _steel_water(self, **kw):
        params = dict(
            fluid='water', line_length_m=100.0, line_id_mm=500.0,
            wall_thickness_mm=5.0, working_pressure_bar=10.0,
            flow_velocity_m_s=2.0, pipe_material='steel_4130',
        )
        params.update(kw)
        return WaterHammerAnalyzer().analyze(**params)

    def test_classic_wave_speed_and_rise(self):
        """steel_4130 (E=200 GPa) klasik su vakası: a~1023 m/s, dP~20.4 bar."""
        out = self._steel_water()
        assert out['wave_speed_m_s'] == pytest.approx(1023.45, rel=2e-3)
        assert out['joukowsky_pressure_rise_bar'] == pytest.approx(20.43, rel=3e-3)
        assert out['wave_speed_m_s'] < out['wave_speed_rigid_m_s']

    def test_unit_consistency_pa_bar(self):
        """bar alanları Pa alanlarıyla 1e5 çarpanında tutarlı; tepe = çalışma+artış."""
        out = self._steel_water()
        assert out['applied_pressure_rise_bar'] * 1e5 == pytest.approx(
            out['applied_pressure_rise_Pa'], rel=1e-9)
        assert out['peak_pressure_bar'] == pytest.approx(
            out['working_pressure_bar'] + out['applied_pressure_rise_bar'], rel=1e-9)
        assert out['peak_pressure_Pa'] == pytest.approx(
            out['peak_pressure_bar'] * 1e5, rel=1e-9)

    def test_velocity_from_mdot(self):
        """mdot verildiğinde v = mdot/(rho*A) türetilir; hıza eşdeğer sonuç."""
        rho = FLUID_PROPERTIES['water']['density_kg_m3']
        D = 0.5
        area = math.pi * D * D / 4.0
        v = 2.0
        mdot = rho * v * area
        out = self._steel_water(flow_velocity_m_s=None, mdot_kg_s=mdot)
        assert out['flow_velocity_m_s'] == pytest.approx(v, rel=1e-9)
        # Hız yolu ile aynı basınç artışı
        out_v = self._steel_water()
        assert out['joukowsky_pressure_rise_bar'] == pytest.approx(
            out_v['joukowsky_pressure_rise_bar'], rel=1e-9)

    def test_slow_closure_below_instant(self):
        """Yavaş kapanma (t_close > t_c) ani değerin altında basınç verir."""
        out_fast = self._steel_water(valve_closure_time_ms=None)
        t_c_ms = out_fast['critical_closure_time_ms']
        out_slow = self._steel_water(valve_closure_time_ms=10.0 * t_c_ms)
        assert out_slow['closure_regime'] == 'slow'
        assert out_slow['applied_pressure_rise_bar'] < out_fast['applied_pressure_rise_bar']
        # 10x kritik süre -> ~1/10 basınç
        assert out_slow['applied_pressure_rise_bar'] == pytest.approx(
            out_fast['applied_pressure_rise_bar'] / 10.0, rel=1e-6)

    def test_rapid_closure_is_full_joukowsky(self):
        """t_close <= t_c -> tam Joukowsky (ani) tepe basıncı."""
        out_fast = self._steel_water(valve_closure_time_ms=None)
        t_c_ms = out_fast['critical_closure_time_ms']
        out_rapid = self._steel_water(valve_closure_time_ms=0.5 * t_c_ms)
        assert out_rapid['closure_regime'] == 'rapid'
        assert out_rapid['applied_pressure_rise_bar'] == pytest.approx(
            out_fast['applied_pressure_rise_bar'], rel=1e-9)

    def test_n2o_wave_speed_below_water(self):
        """N2O (düşük bulk modül) su hattından çok daha düşük dalga hızı."""
        out_w = self._steel_water()
        out_n = self._steel_water(fluid='n2o')
        assert out_n['wave_speed_m_s'] < out_w['wave_speed_m_s']

    def test_default_pipe_material_fallback(self):
        """Bilinmeyen boru malzemesi -> paslanmaz (ss_304) + uyarı."""
        out = self._steel_water(pipe_material='unobtanium')
        assert out['pipe']['material'] == 'ss_304'
        assert any('falling back' in w.lower() for w in out['warnings'])

    def test_custom_fluid_override(self):
        """bulk_modulus_Pa + density_kg_m3 ile özel sıvı tanımlanabilir."""
        out = WaterHammerAnalyzer().analyze(
            fluid='mystery', line_length_m=50.0, line_id_mm=100.0,
            wall_thickness_mm=3.0, working_pressure_bar=20.0,
            flow_velocity_m_s=3.0, pipe_material='ss_304',
            bulk_modulus_Pa=1.5e9, density_kg_m3=900.0)
        assert out['fluid_properties']['bulk_modulus_Pa'] == 1.5e9
        assert out['fluid_properties']['density_kg_m3'] == 900.0
        expect_rigid = math.sqrt(1.5e9 / 900.0)
        assert out['wave_speed_rigid_m_s'] == pytest.approx(expect_rigid, rel=1e-9)

    def test_model_note_and_assumptions(self):
        out = self._steel_water()
        assert out['model_note']
        assert isinstance(out['assumptions'], list) and len(out['assumptions']) >= 4
        assert 'Joukowsky' in out['model_note']


# ===========================================================================
# Emniyet durumu + öneri
# ===========================================================================
class TestSafetyAndRecommendation:
    def _run(self, **kw):
        params = dict(
            fluid='water', line_length_m=100.0, line_id_mm=100.0,
            wall_thickness_mm=6.0, working_pressure_bar=10.0,
            flow_velocity_m_s=2.0, pipe_material='steel_4130',
        )
        params.update(kw)
        return WaterHammerAnalyzer().analyze(**params)

    def test_safe_when_peak_within_mawp(self):
        """Yüksek basınç sınıflı boru -> tepe MAWP altında -> SAFE."""
        out = self._run(pipe_mawp_bar=500.0)
        assert out['status'] == 'SAFE'
        assert out['peak_pressure_bar'] < out['pipe']['mawp_bar']

    def test_unsafe_when_peak_exceeds_yield(self):
        """Çok düşük MAWP + ince cidar -> tepe akmayı aşar -> UNSAFE."""
        out = self._run(fluid='water', wall_thickness_mm=0.3,
                        pipe_mawp_bar=5.0, working_pressure_bar=4.0,
                        flow_velocity_m_s=5.0)
        assert out['status'] == 'UNSAFE'
        assert out['peak_pressure_bar'] > out['pipe']['hoop_yield_pressure_bar']

    def test_marginal_band(self):
        """MAWP < tepe <= akma -> MARGINAL."""
        base = self._run(pipe_mawp_bar=500.0)
        peak = base['peak_pressure_bar']
        yield_p = base['pipe']['hoop_yield_pressure_bar']
        # MAWP'yi tepe ile akma arasına yerleştir
        mawp = 0.5 * (peak + min(yield_p, peak * 1.5))
        mawp = max(min(mawp, peak - 0.1), 0.1)
        if mawp >= peak or peak > yield_p:
            pytest.skip("geometri bu vakada MARGINAL bandı üretmiyor")
        out = self._run(pipe_mawp_bar=mawp)
        assert out['status'] == 'MARGINAL'

    def test_recommendation_none_when_instant_safe(self):
        """Ani kapanma zaten MAWP içindeyse süre kısıtlaması gerekmez."""
        out = self._run(pipe_mawp_bar=500.0)
        assert out['recommended_closure_time_ms'] is None
        assert 'no closure-time restriction' in out['recommendation'].lower()

    def test_recommendation_slower_than_x_ms(self):
        """Tepe MAWP'yi aşıyorsa 'valve closure slower than X ms' önerilir."""
        out = self._run(pipe_mawp_bar=15.0)
        assert out['recommended_closure_time_ms'] is not None
        assert 'valve closure slower than' in out['recommendation'].lower()
        # Önerilen süre kritik süreden büyük olmalı
        assert out['recommended_closure_time_ms'] >= out['critical_closure_time_ms']

    def test_recommended_time_brings_peak_to_mawp(self):
        """Önerilen kapanma süresi uygulanınca tepe ~ MAWP'ye iner."""
        out = self._run(pipe_mawp_bar=15.0)
        t_rec = out['recommended_closure_time_ms']
        # Önerilen süre kritik süreden büyükse yavaş rejim geçerlidir
        if t_rec <= out['critical_closure_time_ms'] * (1 + 1e-9):
            pytest.skip("öneri kritik süreyle sınırlı; ani zaten güvenli değil")
        out2 = self._run(pipe_mawp_bar=15.0, valve_closure_time_ms=t_rec)
        assert out2['peak_pressure_bar'] == pytest.approx(
            out2['pipe']['mawp_bar'], rel=1e-3)

    def test_hoop_pressures_ordered(self):
        """Akma basıncı < kopma basıncı (sigma_y < sigma_u); MAWP <= akma."""
        out = self._run()
        assert (out['pipe']['hoop_yield_pressure_bar']
                < out['pipe']['hoop_burst_pressure_bar'])
        assert out['pipe']['mawp_bar'] <= out['pipe']['hoop_yield_pressure_bar'] + 1e-9


# ===========================================================================
# Geçersiz girdiler
# ===========================================================================
class TestInvalidInputs:
    def _ok(self):
        return dict(
            fluid='water', line_length_m=100.0, line_id_mm=100.0,
            wall_thickness_mm=5.0, working_pressure_bar=10.0,
            flow_velocity_m_s=2.0)

    def test_unknown_fluid(self):
        p = self._ok(); p['fluid'] = 'plasma'
        with pytest.raises(ValueError):
            WaterHammerAnalyzer().analyze(**p)

    def test_missing_flow_definition(self):
        p = self._ok(); p.pop('flow_velocity_m_s')
        with pytest.raises(ValueError):
            WaterHammerAnalyzer().analyze(**p)

    def test_nonpositive_length(self):
        p = self._ok(); p['line_length_m'] = 0.0
        with pytest.raises(ValueError):
            WaterHammerAnalyzer().analyze(**p)

    def test_nonpositive_diameter(self):
        p = self._ok(); p['line_id_mm'] = -1.0
        with pytest.raises(ValueError):
            WaterHammerAnalyzer().analyze(**p)

    def test_nonpositive_wall(self):
        p = self._ok(); p['wall_thickness_mm'] = 0.0
        with pytest.raises(ValueError):
            WaterHammerAnalyzer().analyze(**p)

    def test_nonpositive_working_pressure(self):
        p = self._ok(); p['working_pressure_bar'] = -5.0
        with pytest.raises(ValueError):
            WaterHammerAnalyzer().analyze(**p)

    def test_nonpositive_closure_time(self):
        p = self._ok(); p['valve_closure_time_ms'] = 0.0
        with pytest.raises(ValueError):
            WaterHammerAnalyzer().analyze(**p)

    def test_nonpositive_mdot(self):
        p = self._ok(); p.pop('flow_velocity_m_s'); p['mdot_kg_s'] = -1.0
        with pytest.raises(ValueError):
            WaterHammerAnalyzer().analyze(**p)

    def test_nan_rejected(self):
        p = self._ok(); p['flow_velocity_m_s'] = float('nan')
        with pytest.raises(ValueError):
            WaterHammerAnalyzer().analyze(**p)
