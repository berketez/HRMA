"""Kullanıcı CSV doğrulama + karşılaştırma + comparative plot onarım testleri.

El hesabı çapaları:
- Sabit 100 N / 10 s eğri: I_t = 0.5*(100+100)*10 = 1000 N·s (yamuk kuralı,
  Sutton Eq. 2-1). Sabit 90 N tahmine karşı: impuls farkı 100/900 = +%11.11,
  RMSE = 10 N, NRMSE = 10/90 = %11.11.
- Yamuk itki profili t=[0,1,9,10], F=[0,100,100,0], eşik = tepe*%5 = 5 N
  (NFPA 1125): kesişimler t=0.05 ve t=9.95 → yanma süresi 9.9 s.
- Üçgen profil t=[0,1,2], F=[0,100,0]: I_t = 100 N·s.
"""

import json

import numpy as np
import pytest

from hrma.validation.user_data_validation import (
    parse_thrust_csv, compare, BURN_TIME_THRESHOLD_FRACTION,
)
from hrma.visualization.visualization import create_comparative_analysis_plot


# ---------------------------------------------------------------------------
# parse_thrust_csv
# ---------------------------------------------------------------------------
class TestParseThrustCsv:
    def test_simple_comma_csv_with_header(self):
        out = parse_thrust_csv("time,thrust\n0,0\n1,100\n2,0\n")
        assert np.allclose(out['time'], [0, 1, 2])
        assert np.allclose(out['thrust'], [0, 100, 0])
        assert out['n_points'] == 3
        assert out['warnings'] == []

    def test_semicolon_with_turkish_decimal_comma(self):
        out = parse_thrust_csv("zaman;itki\n0,0;0,0\n0,5;120,3\n1,0;0,0\n")
        assert np.allclose(out['time'], [0.0, 0.5, 1.0])
        assert np.allclose(out['thrust'], [0.0, 120.3, 0.0])

    def test_uppercase_header_with_units_and_spaces(self):
        out = parse_thrust_csv("Time (s), Thrust (N)\n0, 0\n1, 50\n")
        assert np.allclose(out['thrust'], [0, 50])

    def test_tab_delimited_short_aliases(self):
        out = parse_thrust_csv("t\tF\n0\t0\n1\t10\n")
        assert np.allclose(out['time'], [0, 1])
        assert np.allclose(out['thrust'], [0, 10])

    def test_whitespace_delimited_headerless(self):
        out = parse_thrust_csv("0.0 0.0\n1.0 5.0\n2.0 0.0\n")
        assert np.allclose(out['thrust'], [0, 5, 0])
        assert any('No header row' in w for w in out['warnings'])

    def test_unit_row_after_header_is_skipped(self):
        out = parse_thrust_csv("time,thrust\ns,N\n0,0\n1,10\n")
        assert np.allclose(out['time'], [0, 1])
        assert any('Unit row' in w for w in out['warnings'])

    def test_non_si_unit_row_produces_warning(self):
        out = parse_thrust_csv("time;thrust\nms;kN\n0;0\n1;10\n")
        assert np.allclose(out['thrust'], [0, 10])  # dönüşüm YOK
        assert any('non-SI' in w for w in out['warnings'])

    def test_blank_lines_tolerated(self):
        out = parse_thrust_csv("time,thrust\n\n0,0\n\n1,10\n\n")
        assert out['n_points'] == 2

    def test_bom_tolerated(self):
        out = parse_thrust_csv("﻿time,thrust\n0,0\n1,10\n")
        assert out['n_points'] == 2

    def test_extra_column_selected_by_header(self):
        text = "t,pressure,thrust\n0,10,0\n1,12,100\n2,9,0\n"
        out = parse_thrust_csv(text)
        assert np.allclose(out['thrust'], [0, 100, 0])  # basınç değil itki

    def test_comma_delimiter_with_decimal_comma_pairs(self):
        # Excel TR tuzağı: ayraç da ondalık da virgül -> alan çiftleri
        out = parse_thrust_csv("time,thrust\n0,5,100,2\n1,5,80,4\n")
        assert np.allclose(out['time'], [0.5, 1.5])
        assert np.allclose(out['thrust'], [100.2, 80.4])
        assert any('decimal' in w for w in out['warnings'])

    def test_non_numeric_row_skipped_with_warning(self):
        out = parse_thrust_csv("time,thrust\n0,0\nbad,data\n1,10\n")
        assert out['n_points'] == 2
        assert any('Skipped 1' in w for w in out['warnings'])

    def test_unsorted_time_reordered_with_warning(self):
        out = parse_thrust_csv("time,thrust\n2,0\n0,0\n1,100\n")
        assert np.allclose(out['time'], [0, 1, 2])
        assert np.allclose(out['thrust'], [0, 100, 0])
        assert any('not sorted' in w for w in out['warnings'])

    def test_duplicate_time_stamps_removed(self):
        out = parse_thrust_csv("time,thrust\n0,0\n1,50\n1,60\n2,0\n")
        assert np.allclose(out['time'], [0, 1, 2])
        assert np.allclose(out['thrust'], [0, 50, 0])  # ilk değer korunur
        assert any('Duplicate' in w for w in out['warnings'])

    def test_negative_thrust_warns_but_keeps_values(self):
        out = parse_thrust_csv("time,thrust\n0,-5\n1,100\n")
        assert np.allclose(out['thrust'], [-5, 100])
        assert any('Negative thrust' in w for w in out['warnings'])

    def test_empty_file_raises_clear_error(self):
        with pytest.raises(ValueError, match='empty'):
            parse_thrust_csv("")

    def test_garbage_file_raises_clear_error(self):
        with pytest.raises(ValueError, match='at least 2 numeric'):
            parse_thrust_csv("hello world\nthis is not a csv\n")

    def test_single_data_row_raises(self):
        with pytest.raises(ValueError, match='at least 2 numeric'):
            parse_thrust_csv("time,thrust\n1,50\n")

    def test_non_string_input_raises(self):
        with pytest.raises(ValueError, match='text'):
            parse_thrust_csv(12345)


# ---------------------------------------------------------------------------
# compare — el hesabı çapalı metrikler
# ---------------------------------------------------------------------------
class TestCompare:
    def test_identical_curves_all_diffs_zero_grade_excellent(self):
        t = np.array([0.0, 1.0, 9.0, 10.0])
        f = np.array([0.0, 100.0, 100.0, 0.0])
        out = compare((t, f), (t, f))
        m = out['metrics']
        assert m['total_impulse_diff_pct'] == pytest.approx(0.0, abs=1e-12)
        assert m['peak_thrust_diff_pct'] == pytest.approx(0.0, abs=1e-12)
        assert m['rmse_n'] == pytest.approx(0.0, abs=1e-12)
        assert m['burn_time_diff_s'] == pytest.approx(0.0, abs=1e-12)
        assert out['grade'] == 'excellent'
        assert 'agreement' in out['assessment']

    def test_constant_curve_hand_anchor(self):
        # user: 100 N sabit, pred: 90 N sabit, 0..10 s
        t = np.array([0.0, 10.0])
        out = compare((t, np.array([100.0, 100.0])),
                      (t, np.array([90.0, 90.0])))
        m = out['metrics']
        assert m['total_impulse_user_ns'] == pytest.approx(1000.0)
        assert m['total_impulse_predicted_ns'] == pytest.approx(900.0)
        assert m['total_impulse_diff_pct'] == pytest.approx(100.0 / 9.0)
        assert m['peak_thrust_diff_pct'] == pytest.approx(100.0 / 9.0)
        assert m['mean_thrust_user_n'] == pytest.approx(100.0)
        assert m['mean_thrust_predicted_n'] == pytest.approx(90.0)
        assert m['mean_thrust_diff_pct'] == pytest.approx(100.0 / 9.0)
        assert m['rmse_n'] == pytest.approx(10.0)
        assert m['nrmse_pct'] == pytest.approx(100.0 / 9.0)
        assert m['burn_time_diff_s'] == pytest.approx(0.0, abs=1e-12)
        assert out['grade'] == 'fair'  # %11.1 -> fair kovası

    def test_burn_time_trapezoid_hand_anchor(self):
        # Eşik = 100*0.05 = 5 N; kesişimler 0.05 s ve 9.95 s -> 9.9 s
        assert BURN_TIME_THRESHOLD_FRACTION == 0.05
        t = np.array([0.0, 1.0, 9.0, 10.0])
        f = np.array([0.0, 100.0, 100.0, 0.0])
        out = compare((t, f), (t, f))
        assert out['metrics']['burn_time_user_s'] == pytest.approx(9.9)
        assert out['metrics']['burn_time_predicted_s'] == pytest.approx(9.9)

    def test_triangle_total_impulse_hand_anchor(self):
        t = np.array([0.0, 1.0, 2.0])
        f = np.array([0.0, 100.0, 0.0])
        out = compare((t, f), (t, f))
        assert out['metrics']['total_impulse_user_ns'] == pytest.approx(100.0)

    def test_dict_and_tuple_inputs_equivalent(self):
        t = np.array([0.0, 1.0, 2.0])
        f = np.array([0.0, 100.0, 0.0])
        out_tuple = compare((t, f), (t, f * 0.9))
        out_dict = compare({'time': t, 'thrust': f},
                           {'time': t, 'thrust': f * 0.9})
        assert (out_dict['metrics']['total_impulse_diff_pct']
                == pytest.approx(
                    out_tuple['metrics']['total_impulse_diff_pct']))

    def test_parse_output_feeds_compare_directly(self):
        parsed = parse_thrust_csv("time,thrust\n0,0\n1,100\n2,0\n")
        out = compare(parsed, (np.array([0.0, 1.0, 2.0]),
                               np.array([0.0, 100.0, 0.0])))
        assert out['metrics']['rmse_n'] == pytest.approx(0.0, abs=1e-12)

    def test_grade_buckets(self):
        t = np.array([0.0, 10.0])
        pred = (t, np.array([100.0, 100.0]))

        def scaled(pct):
            return (t, np.array([100.0 + pct, 100.0 + pct]))

        assert compare(scaled(4.0), pred)['grade'] == 'excellent'
        assert compare(scaled(8.0), pred)['grade'] == 'good'
        assert compare(scaled(15.0), pred)['grade'] == 'fair'
        assert compare(scaled(30.0), pred)['grade'] == 'poor'

    def test_assessment_text_is_english_and_quantitative(self):
        t = np.array([0.0, 10.0])
        out = compare((t, np.array([108.0, 108.0])),
                      (t, np.array([100.0, 100.0])))
        text = out['assessment']
        assert 'total impulse differs by' in text
        assert 'RMSE' in text
        assert '+8.0%' in text

    def test_non_overlapping_time_ranges_raise(self):
        with pytest.raises(ValueError, match='overlap'):
            compare((np.array([0.0, 1.0]), np.array([10.0, 10.0])),
                    (np.array([5.0, 6.0]), np.array([10.0, 10.0])))

    def test_single_point_curve_rejected(self):
        with pytest.raises(ValueError, match='at least 2'):
            compare((np.array([0.0]), np.array([10.0])),
                    (np.array([0.0, 1.0]), np.array([10.0, 10.0])))

    def test_bad_dict_keys_rejected(self):
        with pytest.raises(ValueError, match="'time'"):
            compare({'x': [0, 1], 'y': [1, 2]},
                    (np.array([0.0, 1.0]), np.array([10.0, 10.0])))

    def test_zero_predicted_curve_rejected(self):
        t = np.array([0.0, 1.0])
        with pytest.raises(ValueError):
            compare((t, np.array([10.0, 10.0])), (t, np.array([0.0, 0.0])))


# ---------------------------------------------------------------------------
# create_comparative_analysis_plot — şema esnetme onarımı
# ---------------------------------------------------------------------------
class TestComparativePlot:
    FULL = {
        'Motor A': {'thrust': 1000.0, 'isp': 220.0,
                    'total_impulse': 5000.0, 'total_mass': 12.0},
        'Motor B': {'thrust': 1500.0, 'isp': 235.0,
                    'total_impulse': 8000.0, 'total_mass': 18.0},
    }

    def test_full_schema_still_produces_four_traces(self):
        fig = json.loads(create_comparative_analysis_plot(self.FULL))
        assert len(fig['data']) == 4

    def test_missing_total_impulse_no_keyerror(self):
        configs = {name: {k: v for k, v in cfg.items()
                          if k != 'total_impulse'}
                   for name, cfg in self.FULL.items()}
        fig = json.loads(create_comparative_analysis_plot(configs))
        # total_impulse paneli boş; thrust + isp + mass-eff kalır
        assert len(fig['data']) == 3

    def test_partial_key_presence_plots_available_configs(self):
        configs = {
            'A': {'thrust': 1000.0, 'isp': 220.0},
            'B': {'thrust': 1500.0},  # isp yok
        }
        fig = json.loads(create_comparative_analysis_plot(configs))
        bar_lengths = sorted(len(tr['x']) for tr in fig['data'])
        # thrust barında 2, isp barında 1 config
        assert bar_lengths == [1, 2]

    def test_only_thrust_key_works(self):
        configs = {'A': {'thrust': 100.0}, 'B': {'thrust': 200.0}}
        fig = json.loads(create_comparative_analysis_plot(configs))
        assert len(fig['data']) == 1

    def test_empty_configs_clear_error(self):
        with pytest.raises(ValueError, match='non-empty'):
            create_comparative_analysis_plot({})

    def test_non_dict_config_clear_error(self):
        with pytest.raises(ValueError, match="'Motor X'"):
            create_comparative_analysis_plot({'Motor X': 42})

    def test_non_numeric_metric_clear_error(self):
        with pytest.raises(ValueError, match="'thrust'"):
            create_comparative_analysis_plot(
                {'A': {'thrust': 'big'}, 'B': {'thrust': 10.0}})

    def test_no_known_metrics_clear_error(self):
        with pytest.raises(ValueError, match='No plottable metrics'):
            create_comparative_analysis_plot(
                {'A': {'foo': 1.0}, 'B': {'bar': 2.0}})


# ---------------------------------------------------------------------------
# /api/comparative-analysis endpoint'i (test_client — port BAĞLANMAZ)
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


class TestComparativeEndpoint:
    BASE = {
        'Motor A': {'thrust': 1000.0, 'isp': 220.0, 'total_mass': 12.0},
        'Motor B': {'thrust': 1500.0, 'isp': 235.0, 'total_mass': 18.0},
    }

    def test_endpoint_without_total_impulse_200(self, client):
        # Onarım öncesi: KeyError('total_impulse') -> 500 dönüyordu
        r = client.post('/api/comparative-analysis',
                        json={'motor_configs': self.BASE})
        assert r.status_code == 200, r.get_json()
        j = r.get_json()
        assert j['status'] == 'success'
        assert j['analysis']['total_configs'] == 2

    def test_endpoint_with_full_schema_200(self, client):
        configs = {name: dict(cfg, total_impulse=5000.0)
                   for name, cfg in self.BASE.items()}
        r = client.post('/api/comparative-analysis',
                        json={'motor_configs': configs})
        assert r.status_code == 200
        assert r.get_json()['status'] == 'success'

    def test_endpoint_single_config_still_400(self, client):
        r = client.post('/api/comparative-analysis',
                        json={'motor_configs': {'Only': {'thrust': 1.0}}})
        assert r.status_code == 400
