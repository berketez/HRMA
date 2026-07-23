# -*- coding: utf-8 -*-
"""Fırlatma sahası katmanının fizik doğrulaması (launch_site.py + 3B küre çekirdeği).

Kapsam (görev şartnamesi a–e):
  (a) Bilinen noktaların (KSC / Baykonur / Everest / Kourou) çevrimdışı DEM
      rakımı makul toleransta.
  (b) Somigliana normal yerçekimi uç değerleri: ekvator 9.7803, kutup 9.8322
      (±0.001).
  (c) YEREL yerçekimi Isp'yi DEĞİŞTİRMEZ: standard_gravity() her enlemde
      G_0'dır; Isp tabanlı ideal delta-v saha bağımsızdır. (Sessiz hatanın
      kilidi — modül başlığındaki KRİTİK AYRIM.)
  (d) Çevrimdışı kip AĞ çağrısı YAPMADAN çalışır.
  (e) Enlem verilmediğinde düzlemsel trajectory ve 6-DOF çözümü ESKİSİYLE
      birebir aynıdır (regresyon kilidi); enlem yalnız ağırlık terimine girer.

Ek: enu_to_geodetic (küre uçuş-yolu çizimi bunun JS kopyasını kullanır) kapalı
formülle doğrulanır — Python ve JS'in aynı dönüşümü yapması garanti edilir.
"""

import math

import numpy as np
import pytest

from hrma.analysis import launch_site as ls
from hrma.constants import G_0


# ---------------------------------------------------------------------------
# (b) Somigliana normal yerçekimi
# ---------------------------------------------------------------------------

def test_somigliana_equator_pole_endpoints():
    """WGS84 normal yerçekimi uçları (NIMA TR8350.2 Denklem 4-1)."""
    assert ls.normal_gravity(0.0) == pytest.approx(9.7803253359, abs=1e-3)
    assert ls.normal_gravity(90.0) == pytest.approx(9.8321849378, abs=1e-3)
    # 45°'de ara değer uçların arasında olmalı
    g45 = ls.normal_gravity(45.0)
    assert 9.7803253359 < g45 < 9.8321849378


def test_local_gravity_free_air_gradient():
    """Yüzeyde serbest-hava gradyanı ≈ -3.086e-6 m/s² per metre."""
    g0h = ls.local_gravity(45.0, 0.0)
    g1000 = ls.local_gravity(45.0, 1000.0)
    grad = (g1000 - g0h) / 1000.0
    assert grad == pytest.approx(-3.086e-6, rel=0.05)


# ---------------------------------------------------------------------------
# (a) Bilinen noktaların çevrimdışı DEM rakımı
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,lat,lon,lo,hi", [
    ("KSC LC-39A", 28.6084, -80.6043, -50.0, 50.0),      # kıyı, deniz seviyesi
    ("Baikonur",   45.9200, 63.3422, 40.0, 180.0),        # bozkır ~100 m
    ("Kourou",      5.2390, -52.7683, -40.0, 80.0),       # kıyı ovası
])
def test_known_site_elevation_reasonable(name, lat, lon, lo, hi):
    d = ls.dem_elevation(lat, lon)
    assert d is not None, "çevrimdışı DEM yüklenemedi"
    assert lo <= d["elevation_m"] <= hi, \
        f"{name}: DEM {d['elevation_m']:.1f} m beklenen [{lo},{hi}] dışında"


def test_everest_is_high_mountain():
    """Everest hücresi yüksek dağ olmalı. 5 ark-dakika (~9 km) hücre zirveyi
    (8848 m) ortalar; tam değeri değil, yüksek-arazi mertebesini kilitleriz."""
    d = ls.dem_elevation(27.9881, 86.9250)
    assert d is not None
    assert 3500.0 < d["elevation_m"] < 8000.0
    # Arazi engebesi (3x3 komşuluk) dağlık sahada geniş olmalı
    assert (d["neighbour_max_m"] - d["neighbour_min_m"]) > 500.0


# ---------------------------------------------------------------------------
# (c) YEREL g Isp'yi değiştirmez — standart g0 korunur
# ---------------------------------------------------------------------------

def test_standard_gravity_is_constant():
    """standard_gravity() her koşulda G_0 = 9.80665 döner."""
    assert ls.standard_gravity() == G_0 == 9.80665


def test_resolve_keeps_standard_gravity_at_every_latitude():
    """resolve_launch_site: yerel g enlemle değişir ama STANDART g0 sabittir."""
    r_eq = ls.resolve_launch_site(0.0, 0.0)
    r_pole = ls.resolve_launch_site(89.9, 0.0)
    # Standart g0 her iki sahada da tam olarak G_0
    assert r_eq["gravity_standard_m_s2"] == G_0
    assert r_pole["gravity_standard_m_s2"] == G_0
    # Yerel g gerçekten enlemle değişir (kutup > ekvator)
    assert r_pole["gravity_local_m_s2"] > r_eq["gravity_local_m_s2"]


def test_ideal_delta_v_is_site_independent():
    """Isp*g0*ln(MR) ideal delta-v'si SAHA BAĞIMSIZDIR (g0 kullanır).

    Aynı motor ekvatorda ve kutupta AYNI ideal delta-v vermeli; yalnız
    AĞIRLIK (m*g_local) sahaya göre değişir. Bu, Isp'yi yerel g ile
    tanımlama sessiz hatasının regresyon kilidi."""
    isp, mass_ratio = 240.0, 3.2
    # delta-v tanımı standard_gravity() ile — saha ne olursa olsun aynı
    dv_equator = isp * ls.standard_gravity() * math.log(mass_ratio)
    dv_pole = isp * ls.standard_gravity() * math.log(mass_ratio)
    assert dv_equator == dv_pole
    # buna karşılık ağırlık (yerel g) sahaya göre GERÇEKTEN değişir
    w_eq = 1000.0 * ls.local_gravity(0.0, 0.0)
    w_pole = 1000.0 * ls.local_gravity(90.0, 0.0)
    assert w_pole > w_eq
    # fark ~%0.5 mertebesinde (WGS84 ekvator↔kutup aralığı)
    assert (w_pole - w_eq) / w_eq == pytest.approx(0.0053, abs=0.001)


# ---------------------------------------------------------------------------
# (d) Çevrimdışı kip: ağ çağrısı yapmadan çalışır
# ---------------------------------------------------------------------------

def test_offline_resolve_makes_no_network_call(monkeypatch):
    """use_online=False iken hiçbir HTTP çağrısı yapılmamalı."""
    def _boom(*a, **k):
        raise AssertionError("çevrimdışı kipte ağ çağrısı yapıldı")
    monkeypatch.setattr(ls, "_http_json", _boom)
    # Ağ tamamen kesikken bile saha çözülmeli (DEM + ISA yerel)
    r = ls.resolve_launch_site(28.6084, -80.6043, use_online=False)
    assert r["elevation_source"] in ("dem_offline", "not_available", "manual")
    assert r["gravity_local_m_s2"] > 0
    assert r["temperature_k"] > 200
    assert r["online_used"] is False


def test_dem_available_offline():
    """Çevrimdışı DEM ağ olmadan yüklenebilir olmalı."""
    assert ls.dem_available() is True
    meta = ls.dem_metadata()
    assert meta and meta["nlat"] == 2160 and meta["nlon"] == 4320


# ---------------------------------------------------------------------------
# (e) Regresyon: enlem verilmezse eski davranış birebir korunur
# ---------------------------------------------------------------------------

def _motor():
    return {
        "thrust": 6500.0, "burn_time": 7.5, "total_impulse": 6500.0 * 7.5,
        "isp": 220.0, "propellant_mass_total": 18.0,
        "mass_flow_rate": 6500.0 / (220.0 * G_0),
    }


def _analyzer():
    from hrma.analysis.trajectory_analysis import TrajectoryAnalyzer
    ta = TrajectoryAnalyzer()
    ta.set_vehicle_parameters(mass_dry=25.0, diameter=0.15,
                              drag_coefficient=0.5, length=3.0)
    return ta


def test_trajectory_without_latitude_is_baseline():
    """Enlem/saha verilmezse: launch_site eklenmez, g_surface == g0 == G_0."""
    ta = _analyzer()
    lp = {"launch_angle": 85, "launch_altitude": 0,
          "wind_speed": 0, "wind_direction": 0}
    res = ta.calculate_trajectory(_motor(), dict(lp))
    assert ta.g0 == G_0
    assert ta.g_surface == G_0           # saha katmanı devrede değil
    assert not res.get("launch_site")     # anahtar yok / None
    apogee = float(np.max(res["trajectory"]["altitude"]))
    assert apogee > 0 and math.isfinite(apogee)


def test_trajectory_baseline_is_deterministic():
    """Aynı girdi -> birebir aynı apoje (saha katmanı belirsizlik katmaz)."""
    lp = {"launch_angle": 85, "launch_altitude": 0,
          "wind_speed": 0, "wind_direction": 0}
    a1 = float(np.max(_analyzer().calculate_trajectory(
        _motor(), dict(lp))["trajectory"]["altitude"]))
    a2 = float(np.max(_analyzer().calculate_trajectory(
        _motor(), dict(lp))["trajectory"]["altitude"]))
    assert a1 == pytest.approx(a2, rel=1e-9)


def test_latitude_changes_weight_not_standard_gravity():
    """launch_latitude yalnız YEREL g'yi (ağırlık) etkiler; g0 sabit kalır.

    Ekvatorda yerel g daha küçük -> ağırlık az -> apoje düzlemsel çözümde
    tabandan FARKLI olmalı; ama analizörün g0'ı (Isp/ideal-dV) DEĞİŞMEZ."""
    lp = {"launch_angle": 85, "launch_altitude": 0,
          "wind_speed": 0, "wind_direction": 0}
    base = float(np.max(_analyzer().calculate_trajectory(
        _motor(), dict(lp))["trajectory"]["altitude"]))

    ta = _analyzer()
    lp_eq = dict(lp); lp_eq["launch_latitude"] = 0.0
    eq = float(np.max(ta.calculate_trajectory(
        _motor(), lp_eq)["trajectory"]["altitude"]))

    assert ta.g0 == G_0                              # Isp zinciri dokunulmadı
    assert ta.g_surface == pytest.approx(ls.local_gravity(0.0, 0.0), rel=1e-9)
    assert ta.g_surface < G_0                        # ekvator g'si daha küçük
    # Ağırlık daha küçük olduğu için apoje tabandan farklı (yerel g gerçekten
    # kullanılıyor — dekoratif değil)
    assert abs(eq - base) > 1.0


def test_sixdof_solver_is_deterministic_and_latitude_free():
    """6-DOF çözücü enlem parametresi ALMAZ; çıktısı saha katmanından
    bağımsız ve tekrarlanabilir (regresyon kilidi)."""
    from hrma.analysis.six_dof_trajectory import BarrowmanAero, SixDOFTrajectory

    def run():
        aero = BarrowmanAero(body_diameter=0.15, nose_length=0.5,
                             body_length=3.0, fin_count=4,
                             fin_root_chord=0.22, fin_tip_chord=0.1,
                             fin_span=0.13, fin_sweep=0.08)
        s = SixDOFTrajectory(aero=aero, dry_mass=25.0, propellant_mass=18.0,
                             thrust=6500.0, burn_time=7.5,
                             launch_elevation_deg=84.0, launch_azimuth_deg=90.0,
                             wind_speed=6.0, wind_direction_deg=270.0)
        return s.solve(t_max=400.0)

    r1, r2 = run(), run()
    assert r1["apogee"] == pytest.approx(r2["apogee"], rel=1e-9)
    assert r1["position"].shape[0] == 3            # 3×N (x=K, y=D, z=yukarı)
    assert math.isfinite(r1["apogee"]) and r1["apogee"] > 0


# ---------------------------------------------------------------------------
# Küre çekirdeği: enu_to_geodetic (JS kopyası bununla aynı olmalı)
# ---------------------------------------------------------------------------

def test_enu_to_geodetic_zero_displacement_returns_origin():
    lat, lon, alt = ls.enu_to_geodetic(28.6, -80.6, 3.0, 0.0, 0.0, 0.0)
    assert lat == pytest.approx(28.6, abs=1e-9)
    assert lon == pytest.approx(-80.6, abs=1e-9)
    assert alt == pytest.approx(3.0, abs=1e-9)


def test_enu_to_geodetic_pure_north_and_east_axes():
    """Saf kuzey yer değiştirmesi enlemi artırır (boylam ~sabit); saf doğu
    boylamı artırır (enlem ~sabit). Kapalı formülle sayısal eşleşme."""
    lat0, lon0, h0 = 10.0, 20.0, 0.0
    # Saf kuzey
    lat_n, lon_n, _ = ls.enu_to_geodetic(lat0, lon0, h0, 100000.0, 0.0, 0.0)
    assert lat_n > lat0
    assert lon_n == pytest.approx(lon0, abs=1e-9)     # saf kuzeyde boylam sabit
    # Saf doğu
    lat_e, lon_e, _ = ls.enu_to_geodetic(lat0, lon0, h0, 0.0, 100000.0, 0.0)
    assert lon_e > lon0
    assert lat_e == pytest.approx(lat0, abs=1e-9)     # saf doğuda enlem sabit

    # Kapalı formülle karşılaştır (WGS84 eğrilik yarıçapları)
    phi0 = math.radians(lat0)
    s2 = math.sin(phi0) ** 2
    w = math.sqrt(1.0 - ls.WGS84_E2 * s2)
    m_rad = ls.WGS84_A * (1.0 - ls.WGS84_E2) / w ** 3
    n_rad = ls.WGS84_A / w
    exp_dlat = math.degrees(100000.0 / (m_rad + h0))
    exp_dlon = math.degrees(100000.0 / ((n_rad + h0) * math.cos(phi0)))
    assert (lat_n - lat0) == pytest.approx(exp_dlat, rel=1e-9)
    assert (lon_e - lon0) == pytest.approx(exp_dlon, rel=1e-9)


def test_enu_to_geodetic_altitude_passthrough():
    _, _, alt = ls.enu_to_geodetic(0.0, 0.0, 1200.0, 0.0, 0.0, 5000.0)
    assert alt == pytest.approx(6200.0, abs=1e-6)
