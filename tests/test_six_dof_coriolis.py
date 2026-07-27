"""Coriolis 6-DOF (v2.6.2 B1) doğrulama testleri.

Çapalar (ARGE turu + codex xhigh türetmesi):
- HANDEDNESS: (N,E,U) sol-elli, np.cross sağ-elli → naif −2·cross(Ω,v) dik
  atışta YANLIŞ işaret (doğu) verir; doğru BATI. _coriolis_acceleration'ın
  ENU-çevir-hesapla-geri kalıbı bunu düzeltir.
- solve() APOJEDE biter → iniş sapması ölçülemez; testler apoje durumuna bakar.
- Büyüklük çapası: birinci mertebe vE(t) = −2Ω cosφ·z(t) KESİN → apojede
  velocity_east ≈ −2Ω cosφ·apogee (sürtünme/itki profilinden bağımsız, sıkı).
  Kapalı-form konum sapması apojede (2/3)Ω cosφ·v0³/g² (iniş değeri 4/3 DEĞİL).
- Coriolis iş yapmaz (v'ye dik) → enerji korunur.
- cosφ çift → dik atış her iki yarıkürede de BATI; sinφ tek → yatay-hızlı
  atışın çapraz sapması yarıkürede işaret değiştirir.

Ağa çıkmaz; saf sayısal entegrasyon.
"""

import numpy as np
import pytest

from hrma.analysis.six_dof_trajectory import (
    BarrowmanAero, SixDOFTrajectory, _coriolis_acceleration, OMEGA_EARTH,
)

G0 = 9.80665


def _standard_rocket():
    """Kanatlı temsili araç (kanatsız araç tumble_event ile anında biter)."""
    return BarrowmanAero(
        body_diameter=0.10, nose_length=0.40, body_length=2.0,
        nose_type='ogive', fin_count=4, fin_root_chord=0.20,
        fin_tip_chord=0.10, fin_span=0.11, fin_sweep=0.08)


def _fly(latitude_deg, elevation_deg=90.0, azimuth_deg=0.0, coriolis=True):
    """Rüzgârsız, sürtünmesiz (cd0=0) atış — yatay hareket YALNIZ Coriolis'ten.

    Yüksek impuls (apoje ~km) Coriolis sapmasını integratör gürültüsünün
    (rtol=1e-5) çok üstüne çıkarır.
    """
    solver = SixDOFTrajectory(
        aero=_standard_rocket(), dry_mass=8.0, propellant_mass=4.0,
        thrust=1200.0, burn_time=6.0, cd0=0.0,
        wind_speed=0.0, wind_direction_deg=0.0,
        launch_elevation_deg=elevation_deg, launch_azimuth_deg=azimuth_deg,
        latitude_deg=latitude_deg, coriolis=coriolis)
    return solver.solve(t_max=300.0)


# --------------------------------------------------------------------------
# T1-T3: dik atış — işaret + büyüklük (kuzey yarıküre)
# --------------------------------------------------------------------------

def test_T1_vertical_shot_deflects_west():
    """Dik atış kuzey yarıkürede APOJEDE batıya sapar (position East < 0).

    Handedness bugı olsaydı (naif cross) doğuya (>0) saptırırdı → bu test
    dürüst düz-Dünya'dan daha kötü olan yanlış-işaret sürümünü kilitler.
    """
    res = _fly(latitude_deg=45.0)
    east_at_apogee = res['position'][1][-1]
    assert east_at_apogee < 0.0, \
        f"Dik atış batıya (East<0) sapmalı; East={east_at_apogee:.2f} m"


def test_T2_east_velocity_first_order_magnitude():
    """Sıkı çapa: apojede doğu-hızı ≈ −2Ω cosφ·apogee (birinci mertebe kesin).

    vE(t) = −2Ω cosφ·z(t) ilişkisi sürtünme z'yi düşürse bile korunur;
    apojede z=apogee. Bu, kapalı-form (2/3)'ten çok daha sıkı ve gürültüsüz.
    """
    res = _fly(latitude_deg=45.0)
    vE_apogee = res['velocity'][1][-1]
    expected = -2.0 * OMEGA_EARTH * np.cos(np.radians(45.0)) * res['apogee']
    assert vE_apogee == pytest.approx(expected, rel=0.10), \
        f"vE={vE_apogee:.4f}, beklenen≈{expected:.4f} (−2Ω cosφ·apogee)"


def test_T3_position_deflection_closed_form_order():
    """Konum sapması apoje kapalı-formuyla aynı 2-katı bandında (2/3, iniş 4/3 DEĞİL).

    ΔE_apoje ≈ −(2/3)Ω cosφ·v0³/g², v0 = burnout dikey hızı. Gevşek band
    (0.4×–2.5×): sürtünme/değişken itki profili tam eşitliği bozar ama
    mertebeyi korur; asıl amaç 'iniş 4/3 formülü apojede kullanılmasın'.
    """
    res = _fly(latitude_deg=45.0)
    # burnout hızı: yanma sonu indisinde dikey hız (t≈burn_time=6 s)
    t = res['time']
    i_burn = int(np.searchsorted(t, 6.0))
    i_burn = min(i_burn, len(t) - 1)
    v0 = res['velocity'][2][i_burn]  # dikey (Up) hız, burnout
    closed = (2.0 / 3.0) * OMEGA_EARTH * np.cos(np.radians(45.0)) * v0**3 / G0**2
    dE = abs(res['position'][1][-1])
    assert 0.4 * closed < dE < 2.5 * closed, \
        f"ΔE={dE:.1f} m, kapalı-form≈{closed:.1f} m (band 0.4×–2.5×)"


# --------------------------------------------------------------------------
# T4: Coriolis iş yapmaz (fonksiyon düzeyi, makine hassasiyeti)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("phi_deg", [-60.0, -12.0, 0.0, 23.5, 67.9])
def test_T4_coriolis_does_no_work(phi_deg):
    """a_cor ⊥ v her zaman → dot(a_cor, v) = 0 (Coriolis enerji katmaz).

    N↔E takası ortonormal olduğundan iç-çarpımı korur; cross ⊥ v garanti.
    """
    phi = np.radians(phi_deg)
    cos_lat, sin_lat = np.cos(phi), np.sin(phi)
    rng = np.random.default_rng(12345 + int(phi_deg))
    for _ in range(20):
        v = rng.standard_normal(3) * 500.0
        a = _coriolis_acceleration(v, cos_lat, sin_lat)
        denom = np.linalg.norm(a) * np.linalg.norm(v) + 1e-30
        assert abs(float(np.dot(a, v))) < 1e-12 * denom


def test_T4b_coriolis_sign_vertical():
    """Fonksiyon düzeyi işaret: dik tırmanış (v=+U) → ivme BATI (aE<0).

    v2.6.25 DÜZELTMESİ — TESTİN İNDİSİ YANLIŞTI, KOD DOĞRUYDU.
    Bu test Doğu bileşenini ``a[1]``'de arıyordu; bu, çerçeve (N,E,U)
    sıralıyken doğruydu. v2.6.2'nin F167 refaktörü entegrasyon çerçevesini
    baştan sağ-elli (E,N,U) yaptı, dolayısıyla Doğu artık ``a[0]``.
    ``a[1]`` Kuzey bileşeni ve dik atışta ZATEN sıfırdır — test −0.0 okuyup
    "Coriolis çalışmıyor" diye kırılıyordu.

    El hesabı (φ=45°, v=(0,0,300) m/s, ENU):
        Ω_enu = Ω·(0, cosφ, sinφ)
        Ω × v = (Ω·cosφ·300 − Ω·sinφ·0,  −(0·300 − Ω·sinφ·0),  0·0 − Ω·cosφ·0)
              = (300·Ω·cosφ, 0, 0)
        a = −2·(Ω × v) = (−600·Ω·cosφ, 0, 0)
    Yani Doğu bileşeni negatif (BATI), Kuzey ve Yukarı bileşenleri tam sıfır.
    """
    phi = np.radians(45.0)
    a = _coriolis_acceleration(np.array([0.0, 0.0, 300.0]),
                               np.cos(phi), np.sin(phi))
    assert a[0] < 0.0, f"Dik tırmanışta Coriolis batıya (aE<0) olmalı; aE={a[0]}"
    # Beklenen büyüklük −2Ω cosφ·vU
    assert a[0] == pytest.approx(
        -2.0 * OMEGA_EARTH * np.cos(phi) * 300.0, rel=1e-12)
    # Dik atışta yatay-kuzey ve düşey bileşen tam sıfır (el hesabı yukarıda)
    assert a[1] == pytest.approx(0.0, abs=1e-18)
    assert a[2] == pytest.approx(0.0, abs=1e-18)


# --------------------------------------------------------------------------
# T5-T7: yarıküre (sinφ/cosφ) davranışı
# --------------------------------------------------------------------------

def test_T5_hemisphere_crossrange_sign_flips():
    """Doğu-azimutlu atışın çapraz (Kuzey) sapması yarıkürede işaret değiştirir.

    Doğu hızı vE için a_N = −2Ω sinφ·vE → saf sinφ terimi. Kuzey yarıkürede
    (φ>0) güneye (position North<0), güney yarıkürede (φ<0) kuzeye (>0).
    """
    res_nh = _fly(latitude_deg=45.0, elevation_deg=45.0, azimuth_deg=90.0)
    res_sh = _fly(latitude_deg=-45.0, elevation_deg=45.0, azimuth_deg=90.0)
    north_nh = res_nh['position'][0][-1]
    north_sh = res_sh['position'][0][-1]
    assert north_nh < 0.0, f"KY doğu-atışı güneye sapmalı; N={north_nh:.2f}"
    assert north_sh > 0.0, f"GY doğu-atışı kuzeye sapmalı; N={north_sh:.2f}"


def test_T6_vertical_shot_west_in_both_hemispheres():
    """Dik atış İKİ yarıkürede de batıya sapar (cosφ çift; E/W FLIP ETMEZ).

    Yaygın yanılgı 'güney yarıkürede doğuya sapar' — YANLIŞ. Bu test onu kilitler.
    """
    res_nh = _fly(latitude_deg=45.0)
    res_sh = _fly(latitude_deg=-45.0)
    assert res_nh['position'][1][-1] < 0.0, "KY dik atış batıya"
    assert res_sh['position'][1][-1] < 0.0, "GY dik atış da batıya (cosφ çift)"


def test_T7_equator_maximum_horizontal_coriolis():
    """Ekvatorda (φ=0, cosφ=1) dik atış Coriolis'i MAKSİMUM, 'kapalı' DEĞİL.

    latitude_deg=0 varsayılanının Coriolis'i kapatmadığını kilitler.
    """
    res = _fly(latitude_deg=0.0)
    assert res['position'][1][-1] < 0.0, \
        "Ekvatorda dik atış batıya sapmalı (max yatay Coriolis)"


def test_coriolis_flag_off_no_deflection():
    """coriolis=False → yatay sapma yok (düz-Dünya geriye dönük davranış)."""
    res = _fly(latitude_deg=45.0, coriolis=False)
    r = res['position']
    lateral = np.hypot(r[0][-1], r[1][-1])
    assert lateral < 1e-6 * res['apogee'], \
        f"coriolis=False'ta yatay sapma ~0 olmalı; yanal={lateral:.3e} m"


# --------------------------------------------------------------------------
# C1: _mass_at bit-aynılığı (birikimli impuls yeniden formülasyonu)
# --------------------------------------------------------------------------

def test_C1_mass_at_bit_identical_to_trapz():
    """Yeni _mass_at (cum_impulse) eski np.trapz uygulamasıyla ~bit-aynı.

    A1'in gerçek ~300-nokta transient eğrisini taklit eden gürültülü eğride
    her t için yeni _mass_at ile referans trapz-tabanlı hesap karşılaştırılır.
    """
    rng = np.random.default_rng(7)
    n = 300
    t_curve = np.sort(rng.uniform(0, 8.0, n))
    t_curve[0] = 0.0
    F_curve = 1500.0 + 300.0 * rng.standard_normal(n)
    F_curve = np.abs(F_curve)  # itki negatif olmaz
    solver = SixDOFTrajectory(
        aero=_standard_rocket(), dry_mass=8.0, propellant_mass=4.0,
        thrust_curve={'time': t_curve.tolist(), 'thrust': F_curve.tolist()},
        cd0=0.45, launch_elevation_deg=90.0)

    def _ref_mass_at(t):
        """Eski algoritma: her çağrıda tam np.trapz."""
        if t >= solver.t_burn:
            return solver.m_dry
        ti = np.clip(t, solver._t_thrust[0], solver._t_thrust[-1])
        mask = solver._t_thrust <= ti
        t_part = np.append(solver._t_thrust[mask], ti)
        F_part = np.append(solver._F_thrust[mask], solver._thrust_at(ti))
        frac = np.trapz(F_part, t_part) / max(solver._impulse, 1e-9)
        return solver.m_dry + solver.m_prop * (1.0 - frac)

    for t in np.linspace(0.0, solver.t_burn * 1.05, 500):
        new = solver._mass_at(t)
        ref = _ref_mass_at(t)
        # Bit-aynıya çok yakın: ≤3 ULP (pairwise-vs-sıralı toplam) → mutlak
        # kütle ~12 kg için 1e-9 fazlasıyla sıkı; çözücü rtol=1e-5'in altında.
        assert abs(new - ref) < 1e-9, \
            f"t={t:.4f}: yeni={new:.12f} ref={ref:.12f} Δ={new-ref:.2e}"


# --------------------------------------------------------------------------
# B3: bozuk thrust_curve → net ValueError (500 değil 400)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [
    {'time': [], 'thrust': []},                 # boş
    {'time': [0.0], 'thrust': [1000.0]},        # tek nokta
    {'time': [0.0, 1.0], 'thrust': [1000.0]},   # uyumsuz uzunluk
])
def test_B3_bad_thrust_curve_raises_valueerror(bad):
    """Boş/tek-nokta/uyumsuz thrust_curve → ValueError (endpoint 400), IndexError→500 DEĞİL."""
    with pytest.raises(ValueError):
        SixDOFTrajectory(
            aero=_standard_rocket(), dry_mass=8.0, propellant_mass=4.0,
            thrust_curve=bad, cd0=0.45, launch_elevation_deg=90.0)
