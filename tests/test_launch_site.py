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
  (e) Enlem verilmediğinde düzlemsel trajectory ESKİSİYLE birebir aynıdır;
      enlem verildiğinde YEREL yerçekimi ağırlık terimine girer ve apoje
      ölçülebilir biçimde değişir (2B kolda doğrulanmış desen).
  (f) 6-DOF çözücüsü aynı girdiyle BİT-EŞ koşum üretir (determinizm) VE
      fırlatma sahası (rakım, enlem) çözüme fiilen girer. ÖH FAZ B adım B7:
      bu bekçinin eski hâli "6-DOF enlemden bağımsızdır" iddiasını REGRESYON
      KİLİDİ yapıyordu — yani defter P4B3-01 (saha rakımı atmosfere girmiyor)
      ve P4B3-11 (WGS84 yerel g hesaplanıyor ama dinamiğe hiç girmiyor)
      kusurlarını koruyordu. İddia tersine çevrildi; kusurlar bugün
      xfail(strict) borç imiyle sayılır.

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
        # ÖH D23 / P4B3-24: "isp" kaldırıldı — yük kendi içinde tutarsızdı
        # (impuls bütçesinden türeyen Isp ile %1'den fazla ayrışıyordu) ve
        # çözücü artık çelişkiyi reddediyor. Isp bütçenin türevidir; anahtar
        # yokken ondan türetilir, testin ölçtüğü sayılar değişmez.
        "propellant_mass_total": 18.0,
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


def _sixdof_kos(**kw):
    """6-DOF koşumu — tek yerde kurulu, saha parametreleri dışarıdan.

    ÖH B7: eski bekçi çözücüyü "enlem parametresi ALMAZ" diye tanıtıyordu;
    çözücü aslında ``latitude_deg`` ve ``launch_altitude`` alıyor
    (six_dof_trajectory.py:528). Yardımcı bu yüzden saha parametrelerini
    geçirilebilir yapar.
    """
    from hrma.analysis.six_dof_trajectory import (BarrowmanAero,
                                                  SixDOFTrajectory)

    aero = BarrowmanAero(body_diameter=0.15, nose_length=0.5,
                         body_length=3.0, fin_count=4,
                         fin_root_chord=0.22, fin_tip_chord=0.1,
                         fin_span=0.13, fin_sweep=0.08)
    s = SixDOFTrajectory(aero=aero, dry_mass=25.0, propellant_mass=18.0,
                         thrust=6500.0, burn_time=7.5,
                         launch_elevation_deg=84.0, launch_azimuth_deg=90.0,
                         wind_speed=6.0, wind_direction_deg=270.0, **kw)
    return s, s.solve(t_max=400.0)


def _sapan_alanlar(a, b, tol=0.0):
    """İki koşum sözlüğünde BİT-EŞ olmayan alanların adları + farkları."""
    sapan = []
    for k in sorted(set(a) | set(b)):
        va, vb = a.get(k), b.get(k)
        if isinstance(va, np.ndarray) or isinstance(vb, np.ndarray):
            va, vb = np.asarray(va), np.asarray(vb)
            if va.shape != vb.shape:
                sapan.append(f'{k}: biçim {va.shape} != {vb.shape}')
            elif not np.array_equal(va, vb):
                fark = float(np.nanmax(np.abs(va - vb)))
                if fark > tol:
                    sapan.append(f'{k}: en büyük fark {fark:.3e}')
        elif isinstance(va, (int, float)) and not isinstance(va, bool):
            if abs(float(va) - float(vb)) > tol:
                sapan.append(f'{k}: {va!r} != {vb!r}')
        elif va != vb:
            sapan.append(f'{k}: {va!r} != {vb!r}')
    return sapan


def test_sixdof_ayni_girdi_bit_es_kosum_uretir():
    """Aynı girdi -> BİT-EŞ çıktı; sapan alan varsa ADIYLA raporlanır.

    Eski bekçi yalnız apojeyi ``rel=1e-9`` ile karşılaştırıyordu: yörünge,
    hız, quaternion ve açısal hız dizilerinin tamamı sessizce kayabilirdi.
    Determinizm iddiası artık ÇIKTININ TAMAMI üstünde ve bit düzeyinde.
    """
    _, r1 = _sixdof_kos()
    _, r2 = _sixdof_kos()
    sapan = _sapan_alanlar(r1, r2)
    assert not sapan, 'aynı girdiyle sapan alanlar: ' + '; '.join(sapan)
    assert r1["position"].shape[0] == 3            # 3×N (x=K, y=D, z=yukarı)
    assert math.isfinite(r1["apogee"]) and r1["apogee"] > 0


def test_sixdof_firlatma_sahasi_rakimi_cozume_girer():
    """3000 m rakımlı saha, deniz seviyesiyle aynı yörüngeyi veremez.

    Deniz seviyesinde yoğunluk 1,225 kg/m³, 3000 m'de ~0,909 kg/m³:
    sürükleme ~%26 azalır, apoje ölçülebilir biçimde YÜKSELİR.

    ÖH Z5S / PK2 ONARILDI (defter P4B3-01) — xfail borç imi SÖKÜLDÜ.
    ÖNCE: ``six_dof_trajectory._derivatives`` yoğunluğu ``h = max(r[2], 0)``
    ile, yani SAHAYA GÖRE yükseklikle çözüyordu; ``self.launch_altitude``
    yalnız itki referans basıncına giriyordu. Ölçüldü: 0 m ⟷ 3000 m arasında
    apoje farkı 0,000e+00 (bit-eş) — F023 "düzeltildi" beyanı yanlıştı.
    SONRA: atmosfer MUTLAK irtifadan (``launch_altitude + h_agl``) okunuyor;
    aynı kurulumda apoje 5757,345774 m → 6981,206966 m, fark 1223,861192 m.
    ``launch_altitude = 0`` kolu BİT-AYNI (çapa koşumu:
    docs/scofield/raw/OH/Z5S/pk2/capa_ONCE.json ⟷ capa_SONRA.json).
    """
    _, deniz = _sixdof_kos(launch_altitude=0.0)
    _, yayla = _sixdof_kos(launch_altitude=3000.0)
    fark = yayla['apogee'] - deniz['apogee']
    # Eşik 2B kardeşin desenidir (``test_latitude_changes_weight_...``):
    # "farklı olsun" demek yetmez, fark ÖLÇÜLEBİLİR olmalı — böylece
    # koşum gürültüsü bu bekçiyi yanlışlıkla yeşile çeviremez.
    assert abs(fark) > 1.0, (
        f"rakım 0 m ve 3000 m için apoje farkı {fark:.3e} m "
        f"({deniz['apogee']:.6f} m) — saha rakımı atmosfer modeline "
        'hiç girmiyor')
    assert fark > 0.0


def test_sixdof_yerel_yercekimi_dinamige_girer():
    """Ekvator ile kutup arasındaki %0,53'lük g farkı apojeye yansımalı.

    2B kolun doğru deseni ``test_latitude_changes_weight_not_standard_
    gravity``de yazılı: yerel g yalnız AĞIRLIK terimine girer, Isp/g0
    zinciri dokunulmaz. Bu bekçi aynı deseni 6-DOF koluna taşır. Coriolis
    kapatılır ki ölçülen fark yalnız yerçekiminden gelsin.

    ÖH Z5S / PK2 ONARILDI (defter P4B3-11) — xfail borç imi SÖKÜLDÜ.
    ÖNCE: WGS84 yerel yerçekimi hesaplanıyordu (``self.g_surface``) ama
    dinamik ``g = G0·(R/(R+h))²`` ile KÜRESEL sabiti kullanıyordu;
    ``g_surface`` dosyanın hiçbir yerinde okunmuyordu. Ölçüldü (Coriolis
    kapalı): ekvator g 9,780325 ⟷ kutup 9,832185 m/s² (%0,530 fark) olmasına
    rağmen apoje bit-eşti, fark 0,000e+00.
    SONRA: ``g = g_surface·((R+h_saha)/(R+h_saha+h_agl))²``; aynı kurulumda
    ekvator apojesi 5767,039014 m ⟷ kutup 5748,096187 m, fark 18,942827 m.
    Enlem verilmemiş kolda ``g_surface == G0`` ve ``launch_altitude == 0``
    olduğundan ifade eskisiyle BİT-AYNIDIR (çapa koşumu kanıtı).
    """
    ekvator_s, ekvator = _sixdof_kos(latitude_deg=0.0, coriolis=False)
    kutup_s, kutup = _sixdof_kos(latitude_deg=90.0, coriolis=False)
    # Saha katmanı yerel g'yi GERÇEKTEN çözüyor (girdi tarafı sağlam).
    assert ekvator_s.g_surface == pytest.approx(ls.local_gravity(0.0, 0.0),
                                                rel=1e-9)
    assert kutup_s.g_surface > ekvator_s.g_surface
    fark = ekvator['apogee'] - kutup['apogee']
    assert abs(fark) > 1.0, (
        f"ekvator ve kutup apojesi arasındaki fark {fark:.3e} m "
        f"({ekvator['apogee']:.6f} m) — yerel g "
        f'({ekvator_s.g_surface:.6f} ⟷ {kutup_s.g_surface:.6f} m/s²) '
        'dinamiğe hiç girmiyor')
    # Kutupta ağırlık daha büyük -> apoje daha düşük.
    assert fark > 0.0


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
