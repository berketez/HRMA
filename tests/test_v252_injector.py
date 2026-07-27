# -*- coding: utf-8 -*-
"""v2.5.2 enjektör + görselleştirme sözleşmeleri.

Kapsam (2026-07-19 dalgası):
1. hrma.utils.injector_design.InjectorDesign.calculate() TÜM tiplerde ortak
   rapor sözleşmesini döndürür (app.js 'Injector Design' tablosu bunu okur).
2. Hibrit pintle (tek akışkan, ox-merkezli) çalışır ve BF ∈ (0,1).
3. Üretilen plotly JSON'unda binary 'bdata' bloğu YOKTUR — vendor
   plotly.js 1.58.5 onu çözemiyor, seri boş çiziliyordu.
4. Eksenel kesit enjektör tipine göre FARKLI trace üretir.
"""

import json

import numpy as np
import pytest

from hrma.utils.injector_design import (
    InjectorDesign, SIGMA_OX, SIGMA_OX_DEFAULT,
    DP_SOURCE_AUTO, DP_SOURCE_USER, DENSITY_SOURCE_USER,
)
from hrma.engines.injector_design import design_injector
from hrma.visualization.visualization import (
    create_performance_plots, create_improved_motor_cross_section,
    create_improved_injector_design, resolve_injector_type,
)

# Ortak rapor sözleşmesi anahtarları (app.js bu adlarla okur)
CONTRACT_KEYS = (
    'discharge_coefficient', 'l_d_ratio', 'injection_area', 'weber_number',
    'pressure_drop_bar', 'pressure_drop_source', 'density_source',
)

UTILS_TYPES = ('showerhead', 'pintle', 'swirl', 'impingement', 'coaxial')


def _injector(injector_type, **kw):
    kwargs = dict(mdot_ox=1.2, chamber_pressure=30.0, tank_pressure=55.0,
                  oxidizer_density=786.0, injector_type=injector_type)
    kwargs.update(kw)
    return InjectorDesign(**kwargs)


# ---------------------------------------------------------------------------
# 1) Utils zinciri çıktı sözleşmesi
# ---------------------------------------------------------------------------

class TestUtilsContract:
    @pytest.mark.parametrize('injector_type', UTILS_TYPES)
    def test_contract_keys_present(self, injector_type):
        """v2.6.2 güncellemesi (fizik denetimi F043): eski test TÜM tiplerde
        Cd=0.7 (düz orifis girdisi) bekliyordu. Basınç-swirl atomizörde deşarj
        katsayısı bağımsız bir girdi DEĞİLDİR — Giffen–Muraszew çözümünden
        gelir (Cd = √((1−X)³/(1+X)); Lefebvre & McDonell Böl. 6, tipik simplex
        bandı 0.2-0.45). Bu yüzden swirl'de Cd artık GM değeridir ve
        'discharge_coefficient_basis' alanıyla raporlanır; diğer tiplerde
        yapıcının düz orifis Cd'si (0.7) korunur."""
        r = _injector(injector_type).calculate()
        for key in CONTRACT_KEYS:
            assert key in r, f'{injector_type}: sözleşme anahtarı eksik: {key}'
        if injector_type == 'swirl':
            assert 0.2 <= r['discharge_coefficient'] <= 0.45
            assert 'Giffen-Muraszew' in r['discharge_coefficient_basis']
        else:
            assert r['discharge_coefficient'] == pytest.approx(0.7)
        # Enjeksiyon alanı mm² ve pozitif; tüm tiplerde AYNI anahtar
        assert r['injection_area'] > 0
        assert r['weber_number'] > 0
        assert r['pressure_drop_bar'] == pytest.approx(r['pressure_drop'])

    @pytest.mark.parametrize('injector_type', UTILS_TYPES)
    def test_no_valueerror_for_any_selectable_type(self, injector_type):
        """UI'da seçilebilen her tip /calculate'i düşürmeden çözülmeli."""
        r = _injector(injector_type).calculate()
        assert r['type'] == injector_type
        assert r['exit_velocity'] > 0
        assert r['reynolds_number'] > 0

    def test_l_d_ratio_lowercase_and_consistent(self):
        """JS küçük harfli 'l_d_ratio' okuyor; showerhead'de eski
        'L_D_ratio' ile aynı değeri taşımalı (N/A regresyonu)."""
        r = _injector('showerhead').calculate()
        assert r['l_d_ratio'] == pytest.approx(r['L_D_ratio'])
        assert r['l_d_ratio'] > 0
        # Anüler geçitlerde L/D tanımsızdır → None (sıfır DEĞİL)
        assert _injector('pintle').calculate()['l_d_ratio'] is None

    def test_weber_number_formula(self):
        """We = rho·v²·d/sigma — showerhead'de delik çapıyla kapalı form."""
        r = _injector('showerhead').calculate()
        d_h = r['hole_diameter'] * 1e-3
        sigma = SIGMA_OX['n2o']
        expected = 786.0 * r['exit_velocity'] ** 2 * d_h / sigma
        assert r['weber_number'] == pytest.approx(expected, rel=1e-9)
        assert r['surface_tension'] == pytest.approx(sigma)

    def test_surface_tension_table(self):
        """N2O kritik noktaya yakın olduğu için çok düşük yüzey gerilimine
        sahiptir (~1.75 mN/m @ 293 K); LOX ondan bir mertebe büyüktür."""
        assert 0.0015 < SIGMA_OX['n2o'] < 0.0021
        assert 0.010 < SIGMA_OX['lox'] < 0.016
        assert SIGMA_OX_DEFAULT > SIGMA_OX['lox']

    def test_pressure_drop_source_reported(self):
        auto = _injector('showerhead').calculate()
        assert auto['pressure_drop_source'] == DP_SOURCE_AUTO
        assert auto['pressure_drop_bar'] == pytest.approx(0.20 * 30.0)
        user = _injector('showerhead', pressure_drop=9.0).calculate()
        assert user['pressure_drop_source'] == DP_SOURCE_USER
        assert user['pressure_drop_bar'] == pytest.approx(9.0)

    def test_user_density_wins_over_nist(self):
        """Kullanıcının verdiği yoğunluk NIST/CoolProp tarafından EZİLMEZ.

        v2.6.2 güncellemesi (fizik denetimi F042): eski test ideal (vena
        contracta) Bernoulli hızını v = √(2ΔP/ρ) bekliyordu; raporlanan alan
        GEOMETRİK alan (A = ṁ/(Cd√(2ρΔP))) olduğu için o hız 'injection_area'
        ile tutarsızdı (ṁ = ρ·A·v sağlanmıyordu). Doğru rapor hızı
        süreklilikten v = ṁ/(ρA) = Cd·√(2ΔP/ρ)'dir (Sutton & Biblarz Böl. 8;
        kardeş modül engines/injector_design.py::_solve_circuit ile aynı
        tanım). ρ bağımlılığı (1/√ρ) aynen korunur — testin asıl amacı olan
        'kullanıcı yoğunluğu kazanır' iddiası hâlâ bu satırla sınanıyor."""
        r = _injector('showerhead', oxidizer_density=900.0).calculate()
        assert r['density_source'] == DENSITY_SOURCE_USER
        # Süreklilik hızı: v = ṁ/(ρA) = Cd·√(2ΔP/ρ)
        expected_v = r['discharge_coefficient'] * np.sqrt(
            2 * r['pressure_drop_bar'] * 1e5 / 900.0)
        assert r['exit_velocity'] == pytest.approx(expected_v, rel=1e-9)

    def test_oxidizer_type_is_configurable(self):
        """Constructor artık 'n2o' hardcoded değil — LOX seçilince Weber
        sayısı LOX yüzey gerilimiyle hesaplanır."""
        r = _injector('showerhead', oxidizer_type='lox',
                      oxidizer_density=1141.0).calculate()
        assert r['oxidizer_type'] == 'lox'
        assert r['surface_tension'] == pytest.approx(SIGMA_OX['lox'])

    def test_impingement_reports_angle_and_mixing_note(self):
        r = _injector('impingement').calculate()
        assert r['impingement_angle_deg'] == pytest.approx(60.0)
        assert r['n_holes'] == 2 * r['n_pairs']
        assert r['axial_velocity'] < r['exit_velocity']
        assert 'Rupe' in r['mixing_note']

    def test_coaxial_split_is_conserved(self):
        r = _injector('coaxial').calculate()
        assert 0.1 <= r['inner_flow_fraction'] <= 0.9
        assert r['annulus_outer_diameter'] > r['annulus_inner_diameter'] \
            > r['inner_jet_diameter']
        assert r['recess_length'] > 0

    def test_unknown_type_still_raises(self):
        with pytest.raises(ValueError):
            _injector('plasma').calculate()


# ---------------------------------------------------------------------------
# 2) ARGE zinciri: hibrit pintle
# ---------------------------------------------------------------------------

class TestHybridPintle:
    def _design(self, **kw):
        spec = {'motor_type': 'hybrid', 'injector_type': 'pintle',
                'mdot_ox': 1.0, 'Pc_bar': 30.0, 'fluid_ox': 'n2o',
                'T_ox_K': 293.15}
        spec.update(kw)
        return design_injector(spec)

    def test_hybrid_pintle_succeeds(self):
        d = self._design()
        assert d['status'] == 'success'
        assert d['fuel_circuit'] is None, 'hibritte yakıt devresi olmamalı'

    def test_bf_within_unit_interval(self):
        pg = self._design()['pintle_geometry']
        assert 0.0 < pg['bf'] < 1.0
        assert pg['single_fluid'] is True

    def test_annulus_and_skip_distance_reported(self):
        pg = self._design()['pintle_geometry']
        assert pg['annulus_gap_mm'] > 0
        assert pg['skip_distance_mm'] == pytest.approx(pg['d_pintle_mm'])

    def test_radial_fraction_drives_spray_angle(self):
        """TMR = f/(1−f): pay büyüdükçe koni açılır (Cheng 2017)."""
        a = self._design(pintle={'radial_fraction': 0.4})
        b = self._design(pintle={'radial_fraction': 0.7})
        assert b['momentum']['tmr'] > a['momentum']['tmr']
        assert (b['atomization']['spray_cone_half_angle_deg']
                > a['atomization']['spray_cone_half_angle_deg'])

    def test_no_fuel_flow_required(self):
        """mdot_fuel verilmeden çözülmeli (yakıt grain'den gelir)."""
        d = self._design()
        assert d['momentum']['tmr'] is not None
        assert d['pintle_geometry']['n_radial_holes'] >= 4


# ---------------------------------------------------------------------------
# 3) Plotly bdata regresyonu
# ---------------------------------------------------------------------------

MOTOR = {
    'mdot_total': 1.5, 'mdot_ox': 1.2, 'mdot_f': 0.3,
    'chamber_pressure': 30.0, 'tank_pressure': 55.0, 'burn_time': 10.0,
    'chamber_length': 0.3, 'chamber_diameter': 0.1,
    'throat_diameter': 0.02, 'exit_diameter': 0.08,
    'port_diameter_initial': 0.03, 'port_diameter_final': 0.05,
    'port_history': {'time': [0.0, 2.5, 5.0, 7.5, 10.0],
                     'port_diameter': [0.030, 0.035, 0.040, 0.045, 0.050]},
}
INJECTOR = {'pressure_drop': 6.0, 'exit_velocity': 30.0}


class TestNoBinaryData:
    def test_performance_plots_have_no_bdata(self):
        s = create_performance_plots(MOTOR, INJECTOR)
        assert '"bdata"' not in s, 'plotly binary kodlaması sızdı'
        assert 'bdata' not in s
        json.loads(s)  # geçerli JSON

    def test_cross_section_has_no_bdata(self):
        s = create_improved_motor_cross_section(MOTOR)
        assert 'bdata' not in s
        json.loads(s)

    @pytest.mark.parametrize('injector_type', UTILS_TYPES)
    def test_injector_design_plot_has_no_bdata(self, injector_type):
        data = _injector(injector_type).calculate()
        s = create_improved_injector_design(data)
        assert 'bdata' not in s
        json.loads(s)

    def test_regression_series_actually_reaches_json(self):
        """Boş 'Regression Rate & Port Growth' bugının kalıcı koruması:
        port çapı serisi mm cinsinden JSON'da sayı listesi olarak durmalı."""
        fig = json.loads(create_performance_plots(MOTOR, INJECTOR))
        port = [t for t in fig['data']
                if t.get('name') == 'Port Diameter Growth']
        assert port, 'port çapı serisi figürde yok'
        ys = port[0]['y']
        assert isinstance(ys, list) and len(ys) >= 3
        assert all(isinstance(v, (int, float)) for v in ys)
        assert ys[-1] > ys[0]  # port yanma boyunca büyür


class TestPressureDistribution:
    def test_tank_bar_uses_real_tank_pressure(self):
        fig = json.loads(create_performance_plots(MOTOR, INJECTOR))
        bars = [t for t in fig['data'] if t.get('type') == 'bar'
                and 'Tank' in (t.get('x') or [])]
        assert bars
        x = list(bars[0]['x'])
        y = list(bars[0]['y'])
        assert y[x.index('Tank')] == pytest.approx(55.0)

    def test_tank_bar_falls_back_when_missing(self):
        md = dict(MOTOR)
        md.pop('tank_pressure')
        fig = json.loads(create_performance_plots(md, INJECTOR))
        bars = [t for t in fig['data'] if t.get('type') == 'bar'
                and 'Tank' in (t.get('x') or [])]
        x = list(bars[0]['x'])
        y = list(bars[0]['y'])
        assert y[x.index('Tank')] == pytest.approx(36.0)  # Pc + dP


# ---------------------------------------------------------------------------
# 4) Kesit çizimi enjektör tipine göre dallanıyor
# ---------------------------------------------------------------------------

def _cross_section_names(injector_type):
    md = dict(MOTOR)
    md['injector_design'] = {'injector_type': injector_type,
                             'number_of_orifices': 14}
    fig = json.loads(create_improved_motor_cross_section(md))
    return [t.get('name') for t in fig['data']]


class TestCrossSectionByType:
    def test_type_aliases_resolve(self):
        assert resolve_injector_type(
            {'injector_design': {'injector_type': 'impinging_doublet'}}) \
            == 'impingement'
        assert resolve_injector_type(
            {'injector_design': {'injector_type': 'coax_swirl'}}) == 'coaxial'
        assert resolve_injector_type({}) == 'showerhead'

    def test_showerhead_draws_orifices(self):
        assert 'Orifices' in _cross_section_names('showerhead')

    def test_pintle_differs_from_showerhead(self):
        head = _cross_section_names('showerhead')
        pin = _cross_section_names('pintle')
        assert head != pin
        assert 'Pintle post' in pin
        assert any('Annulus gap' in (n or '') for n in pin)

    def test_swirl_differs_from_showerhead(self):
        head = _cross_section_names('showerhead')
        sw = _cross_section_names('swirl')
        assert head != sw
        assert 'Tangential slots' in sw
        assert any('Spray cone' in (n or '') for n in sw)

    def test_impingement_and_coaxial_have_own_marks(self):
        imp = _cross_section_names('impingement')
        cox = _cross_section_names('coaxial')
        assert any('Impinging pairs' in (n or '') for n in imp)
        assert 'Inner jet' in cox and 'Outer annulus' in cox

    def test_no_turkish_trace_names(self):
        """v2.5.2 dil birliği: kullanıcıya görünen trace adları İngilizce."""
        turkish = set('çğışöüÇĞİŞÖÜ')
        for t in ('showerhead', 'pintle', 'swirl', 'impingement', 'coaxial'):
            for name in _cross_section_names(t):
                if not name:
                    continue
                assert not (set(name) & turkish), f'Türkçe trace adı: {name}'
