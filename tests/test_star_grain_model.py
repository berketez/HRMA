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
from hrma.utils.numeric_compat import trapezoid


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


class TestMassConservationAllGrains:
    """∫ṁdt ≈ ρ·V_grain — 2026-07-13 formül teyidi regresyonları.

    Kilitlenen hatalar: star web_progression_factor çifte-sayımı (+%44),
    wagon_wheel sınırsız çevre (3× ihlal), end_burner radyal-web kesmesi
    (yakıtın %93'ü yanmadan sonlanıyordu), annulus kütle tabanı (yanlış Isp).
    """

    @pytest.mark.parametrize('grain_type', [
        'bates', 'star', 'wagon_wheel', 'end_burner'])
    def test_burned_mass_matches_loaded_mass(self, grain_type):
        m = SolidRocketEngine(
            grain_type=grain_type, propellant_type='apcp',
            chamber_diameter=100, grain_length=500, core_diameter=30,
            chamber_pressure=40)
        curve = m.calculate_thrust_curve()
        burned = trapezoid(curve['mass_flow'], curve['time'])
        available = m._propellant_volume() * m.rho_p
        assert available > 0
        # dt ayrıklaştırması + son adım kuyruğu için %2 tolerans
        assert burned == pytest.approx(available, rel=0.02)

    def test_isp_physical_band_for_apcp(self):
        """Tüm grain tiplerinde APCP deniz seviyesi Isp fiziksel bantta."""
        # V301/T-ÇAPA-A: tam çözüm (calculate_performance) K-A port
        # kapısından geçer; 30 mm çekirdekte bates ve wagon_wheel portu
        # boğuluyor (A_p/A_t 0,950 / 0,747 -> 422). Çekirdek tek tanımdan
        # (48 mm: bates 2,218, wagon_wheel 1,915). Konu Isp bandıdır.
        #
        # V301/K-D (T-çapa-A DEVİR 3) — FİZİK İNCELEMESİ, BANT YERİNE OTURDU.
        # Bant (200-280 s) TASARIM NOKTASININ bandıdır: APCP, 40 bar, lüle o
        # basınca göre genişletilmiş. Eski bekçi onu YANMA ORTALAMASINA
        # uyguluyordu. Ölçüldü (docs/scofield/raw/OH/V301/kati-sivi/K-D/
        # wagon_isp_olcum.json; bu gövde): wagon_wheel'de tepe/ortalama itki
        # 5,18; boğaz Kn_max'ta boyutlandığı için yakıtın %86,9'u tepe
        # basıncın yarısının altında yanıyor (kütle ağırlıklı Pc 15,6 bar),
        # örneklerin %67,9'unda lüle içi ayrılma var; sabit lüle bu basınçta
        # aşırı genişlemiş çalışır (kütle ağırlıklı CF 1,2215 ⟷ tepede
        # 1,5240). Yayımlanan 196,46 s, çözücünün CF işlevi KULLANILMADAN
        # (izentropik alan-Mach + Eş. 3-30 + Summerfield 0,4·P_a kesilmiş
        # lüle; Sutton & Biblarz 9. bs. Böl. 3) aynı basınç geçmişinden
        # 197,22 s olarak yeniden kurulur (%0,39). Düşüş modelin değil
        # fiziğin sonucudur; bandın yanma ortalaması için dayanağı yoktur.
        # Bekçi artık (1) bandı tasarım noktası Isp'sine (c*·CF(P_tepe)/g0)
        # uygular, (2) yanma ortalamasının tasarım noktasını aşmadığını
        # sınar (bütün örneklerde Pc ≤ P_tepe ve sabit ε'da CF(Pc) artandır),
        # (3) yanma ortalamasını bağımsız lüle yeniden kurulumuna bağlar.
        # Eski bandın iki ucu değişmedi; (3)'ün payı (%1) ölçülen en büyük
        # ayrışmanın (%0,39) üstündedir.
        from hrma.constants import G_0
        from hrma.engines.solid_rocket_engine import (
            SOLID_DEFAULT_GEOMETRY_MM, SUMMERFIELD_SEPARATION_RATIO)
        for gt in ['bates', 'star', 'wagon_wheel', 'end_burner']:
            m = SolidRocketEngine(
                grain_type=gt, propellant_type='apcp',
                chamber_diameter=100, grain_length=500,
                core_diameter=SOLID_DEFAULT_GEOMETRY_MM['core_diameter'],
                chamber_pressure=40)
            r = m.calculate_performance()
            c = m.calculate_thrust_curve()
            t = np.asarray(c['time'], float)
            p = np.asarray(c['pressure'], float)
            md = np.asarray(c['mass_flow'], float)
            cf = np.where(p > 0, np.asarray(c['thrust'], float)
                          / np.maximum(p * 1e5 * np.asarray(
                              c['throat_area_series'], float), 1e-30), 0.0)
            i = int(np.argmax(p))
            isp_tasarim = float(m.c_star) * float(cf[i]) / G_0
            assert 200 < isp_tasarim < 280, f"{gt}: tasarım Isp={isp_tasarim}"
            assert r['specific_impulse'] <= isp_tasarim * (1 + 1e-9), gt
            g = float(m._nozzle_gamma())
            pa = float(m.ambient_pressure_bar)
            eps = float(m._estimate_expansion_ratio())
            cf_b = np.array([_cf_bagimsiz(x, pa, eps, g,
                                          SUMMERFIELD_SEPARATION_RATIO)
                             for x in p])
            cf_b = cf_b * (cf[i] / cf_b[i])      # sabit lüle verimi
            isp_b = (float(m.c_star) * float(trapezoid(cf_b * md, t)
                                             / trapezoid(md, t)) / G_0)
            assert r['specific_impulse'] == pytest.approx(isp_b, rel=1e-2), (
                gt, r['specific_impulse'], isp_b)

    def test_end_burner_burn_time_axial(self):
        """End-burner yanma süresi L_grain/r mertebesinde olmalı (eksenel)."""
        m = SolidRocketEngine(
            grain_type='end_burner', propellant_type='apcp',
            chamber_diameter=100, grain_length=500, core_diameter=30,
            chamber_pressure=40)
        curve = m.calculate_thrust_curve()
        t_b = curve['time'][-1]
        r_avg = np.mean(curve['burn_rate'])
        assert t_b == pytest.approx(0.5 / r_avg, rel=0.05)


# ---------------------------------------------------------------------------
# V301/K-D — bağımsız 1B lüle bağıntısı (çözücünün CF işlevi KULLANILMAZ):
# izentropik alan-Mach (Sutton & Biblarz 9. bs. Eş. 3-25), itki katsayısı
# Eş. 3-30; aşırı genişlemede Summerfield ölçütüyle kesilmiş lüle, boğulma
# yoksa CF = 0 (Eş. 3-20 kritik basınç oranı).
# ---------------------------------------------------------------------------
def _alan_orani(pr, g):
    a = ((g + 1) / 2) ** (1 / (g - 1)) * pr ** (1 / g)
    b = np.sqrt((g + 1) / (g - 1) * (1 - pr ** ((g - 1) / g)))
    return 1.0 / (a * b)


def _basinc_orani(eps, g):
    lo, hi = 1e-8, 0.5
    for _ in range(200):
        orta = np.sqrt(lo * hi)
        if _alan_orani(orta, g) > eps:
            lo = orta
        else:
            hi = orta
    return float(np.sqrt(lo * hi))


def _cf_momentum(pr, g):
    return float(np.sqrt(2 * g * g / (g - 1)
                         * (2 / (g + 1)) ** ((g + 1) / (g - 1))
                         * (1 - pr ** ((g - 1) / g))))


def _cf_bagimsiz(pc, pa, eps, g, k):
    if pc <= pa * ((g + 1) / 2) ** (g / (g - 1)):
        return 0.0
    pe = _basinc_orani(eps, g) * pc
    if pe >= k * pa:
        return _cf_momentum(pe / pc, g) + eps * (pe - pa) / pc
    pr = k * pa / pc
    return _cf_momentum(pr, g) + _alan_orani(pr, g) * (pr * pc - pa) / pc
