# -*- coding: utf-8 -*-
"""Star grain geometrik ofset modeli doğrulamaları (2026-07-13).

Model: yanan yüzey = başlangıç port profilinin web kadar normal ofseti
(Huygens ilkesi, shapely buffer). Buradaki testler modeli ANALİTİK
sonuçlara karşı doğrular — uydurma referans yok:
  1) Dairesel portta çevre(w) = 2π(r0+w) (kesin analitik ofset)
  2) Başlangıç star çevresi = 2N·kenar (kosinüs teoremi, birebir)
  3) Süreklilik/monotonluk ve doğal sönüm (port kasaya ulaşınca 0)
  4) Uç sayısı fiziğe yansır (N artınca başlangıç yanma alanı artar)
"""

import numpy as np
import pytest

pytest.importorskip('shapely')
from shapely.geometry import Point

from hrma.engines.solid_rocket_engine import SolidRocketEngine


def _make(star_points=6, star_radius=15.0, **kw):
    args = dict(grain_type='star', chamber_diameter=100, grain_length=500,
                core_diameter=30, chamber_pressure=40)
    args.update(kw)
    return SolidRocketEngine(
        overrides={'star_points': star_points, 'star_radius': star_radius},
        **args)


class TestStarOffsetModel:
    def test_circular_port_matches_analytic_offset(self):
        """Dairesel portta model 2π(r0+w) analitik sonucunu vermeli."""
        m = _make()
        r0 = 0.020
        m._star_port_polygon = lambda: Point(0.0, 0.0).buffer(r0, quad_segs=256)
        for w in (0.0, 0.005, 0.010, 0.015):
            beklenen = 2.0 * np.pi * (r0 + w)
            hesap = m._star_burn_perimeter(w)
            assert abs(hesap - beklenen) / beklenen < 5e-3, \
                f'w={w}: {hesap:.6f} != {beklenen:.6f}'

    def test_initial_star_perimeter_matches_hand_formula(self):
        """Başlangıç çevresi = 2N·kenar; kenar kosinüs teoreminden."""
        n_pts, depth_mm = 6, 15.0
        m = _make(star_points=n_pts, star_radius=depth_mm)
        r_i = 0.030 / 2
        r_p = r_i + depth_mm / 1000.0
        kenar = np.sqrt(r_p**2 + r_i**2
                        - 2 * r_p * r_i * np.cos(np.pi / n_pts))
        beklenen = 2 * n_pts * kenar
        hesap = m._star_port_polygon().boundary.length
        assert abs(hesap - beklenen) / beklenen < 1e-9

    def test_perimeter_continuous_and_burns_out(self):
        """Çevre süreklidir, NaN üretmez ve port kasayı doldurunca söner."""
        m = _make()
        r_go = m.D_chamber / 2
        ws = np.linspace(0.0, r_go, 60)
        pers = [m._star_burn_perimeter(w) for w in ws]
        assert all(np.isfinite(p) and p >= 0 for p in pers)
        # süreklilik: ardışık adımlar arasında patlama yok
        for p0, p1 in zip(pers, pers[1:]):
            assert abs(p1 - p0) < 0.5
        # yakıt bitti: son web değerinde yanan çevre 0
        assert pers[-1] < 1e-6

    def test_more_points_more_burn_area(self):
        """Uç sayısı artınca başlangıç yanma alanı artmalı (fizik kablolu)."""
        a4 = _make(star_points=4).calculate_burn_area(0.0)
        a10 = _make(star_points=10).calculate_burn_area(0.0)
        assert a10 > a4 > 0

    def test_full_performance_runs_for_star(self):
        """Star grain ile uçtan uca performans hesabı çalışır ve tutarlıdır."""
        r = _make().calculate_performance()
        assert not r.get('error')
        assert r['average_thrust'] > 0 and r['burn_time'] > 0
        assert np.isfinite(r['specific_impulse'])
        gd = r['grain_design']
        assert gd['star_points'] == 6
        assert 'Huygens' in gd.get('model_note', '')

    def test_report_and_physics_share_parameters(self):
        """Rapor ve fizik aynı parametre kaynağını kullanır (8 uç örneği)."""
        r = _make(star_points=8, star_radius=10.0).calculate_performance()
        assert r['grain_design']['star_points'] == 8
        assert r['grain_design']['point_depth'] == pytest.approx(10.0)
