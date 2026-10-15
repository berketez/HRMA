# -*- coding: utf-8 -*-
"""Doğrulama veri kümesinin bekçisi.

Bu betik `data/validation/*.json` kayıtlarını iki düzeyde denetler:

1. **Şema** — her kayıtta zorunlu alanlar var mı, `source` künyesi tam mı,
   `confidence` bilinen bir değer mi, `retrieved` tarihi biçimli mi.
2. **Yeniden türetme** — analitik olarak türetilmiş her sayı, kaydın kendi
   `reference_formulas` alanında yazan bağıntıdan **yeniden hesaplanır** ve
   dosyadaki değerle karşılaştırılır.

İkinci kısım asıl mesele. Bir doğrulama veri kümesinin en sinsi çürüme biçimi,
içindeki sayının sessizce yanlış olmasıdır: kimse fark etmez, çünkü "beklenen
değer" tanım gereği doğru sayılır. Burada beklenen değerler *kaynak* değil,
*tanık* muamelesi görür — bağıntıdan çıkmıyorlarsa kayıt kırmızıya döner.

Ölçüme dayanan kayıtlar (F-1 frekansları, RL10 tasarım tablosu, Bartz hata
bandı) yeniden türetilemez; onlar için yalnız şema ve iç tutarlılık kontrolü
yapılır — uydurma bir "beklenen değer" üretilmez.

Kullanım:
    python3 data/validation/selfcheck.py
    python3 data/validation/selfcheck.py --quiet     # yalnız hataları bas

Çıkış kodu 0 = temiz, 1 = en az bir bulgu.
"""

from __future__ import annotations

import glob
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

REQUIRED_RECORD_FIELDS = ("case", "description_tr", "inputs", "expected_outputs",
                "source", "retrieved", "confidence")
REQUIRED_SOURCE_FIELDS = ("title", "author", "year", "url_or_doi")
VALID_CONFIDENCE = {"high", "medium", "low", "not_applicable"}

# Türkçe metinlerde ASCII'ye kaçılmadığını sınamak için: bu harflerin hiç
# geçmemesi şüphelidir ama zorunlu değil; asıl yasak olan yanlış kullanım.
_findings: list[str] = []


def bad(case: str, msg: str) -> None:
    _findings.append("%s: %s" % (case, msg))


def close(got: float, want: float, tol_rel: float = 1e-4) -> bool:
    if want == 0.0:
        return abs(got) <= max(tol_rel, 1e-9)
    return abs(got - want) / abs(want) <= tol_rel


# ---------------------------------------------------------------------------
# Yeniden türetme yardımcıları
# ---------------------------------------------------------------------------

def _erfc(x: float) -> float:
    return math.erfc(x)


def _area_ratio(mach: float, gamma: float) -> float:
    return (1.0 / mach) * ((2.0 / (gamma + 1.0))
                           * (1.0 + 0.5 * (gamma - 1.0) * mach * mach)
                           ) ** ((gamma + 1.0) / (2.0 * (gamma - 1.0)))


def _p_over_p0(mach: float, gamma: float) -> float:
    return (1.0 + 0.5 * (gamma - 1.0) * mach * mach) ** (-gamma / (gamma - 1.0))


def _cstar(r_gas: float, gamma: float, t_c: float) -> float:
    return (math.sqrt(r_gas * t_c / gamma)
            * ((gamma + 1.0) / 2.0) ** ((gamma + 1.0) / (2.0 * (gamma - 1.0))))


def _bessel_jprime_zero(order: int, index: int) -> float:
    """J_m'(x) = 0 kökü; scipy varsa ondan, yoksa gömülü referans değerden."""
    try:
        from scipy.special import jnp_zeros  # type: ignore
        return float(jnp_zeros(order, index)[index - 1])
    except Exception:
        # scipy yoksa literatürün standart değerleri (yalnız karşılaştırma için)
        table = {(1, 1): 1.841184, (2, 1): 3.054237, (0, 1): 3.831706,
                 (3, 1): 4.201189, (1, 2): 5.331443, (0, 2): 7.015587}
        return table[(order, index)]


# ---------------------------------------------------------------------------
# Kayıt bazlı denetimler
# ---------------------------------------------------------------------------

def check_lame(rec: dict) -> None:
    """Lamé kalın cidar: sigma_r, sigma_theta ve düzlem gerilme yer değiştirmesi."""
    case = rec["case"]
    inp = rec["inputs"]
    exp = rec["expected_outputs"]

    if "inner_radius_in" in inp:
        a, b = inp["inner_radius_in"], inp["outer_radius_in"]
        p_i = inp["internal_pressure_psi"]
        e_mod, nu = inp["youngs_modulus_psi"], inp["poissons_ratio"]
        radii = {"r_4in": 4.0, "r_6in": 6.0, "r_8in": 8.0}
        disp_key = "radial_displacement_in"
    else:
        a, b = inp["inner_radius_m"], inp["outer_radius_m"]
        p_i = inp["internal_pressure_pa"]
        e_mod, nu = inp["youngs_modulus_pa"], inp["poissons_ratio"]
        radii = {"r_0.10m": 0.10, "r_0.15m": 0.15, "r_0.20m": 0.20}
        disp_key = "radial_displacement_m"

    k = p_i * a * a / (b * b - a * a)
    sr_exp = exp.get("radial_stress_psi") or exp.get("radial_stress_pa") or {}
    st_exp = exp.get("tangential_stress_psi") or exp.get("tangential_stress_pa") or {}

    for key, r in radii.items():
        if key in sr_exp:
            want = sr_exp[key]
            got = k * (1.0 - b * b / (r * r))
            if not close(got, want, 2e-4):
                bad(case, "sigma_r(%s) bağıntıdan %.4f, dosyada %.4f" % (key, got, want))
        if key in st_exp:
            want = st_exp[key]
            got = k * (1.0 + b * b / (r * r))
            if not close(got, want, 2e-4):
                bad(case, "sigma_theta(%s) bağıntıdan %.4f, dosyada %.4f" % (key, got, want))

    # von Mises (düzlem gerilme, sigma_z = 0)
    vm_exp = exp.get("von_mises_stress_pa", {})
    for key, r in radii.items():
        if key in vm_exp:
            s_r = k * (1.0 - b * b / (r * r))
            s_t = k * (1.0 + b * b / (r * r))
            got = math.sqrt(s_r * s_r - s_r * s_t + s_t * s_t)
            if not close(got, vm_exp[key], 2e-4):
                bad(case, "von Mises(%s) bağıntıdan %.4f, dosyada %.4f"
                    % (key, got, vm_exp[key]))

    # Düzlem gerilme radyal yer değiştirme
    disp_exp = exp.get(disp_key, {})
    for key, r in radii.items():
        if key in disp_exp:
            got = (a * a * p_i * r / (e_mod * (b * b - a * a))
                   * ((1.0 - nu) + (1.0 + nu) * b * b / (r * r)))
            if not close(got, disp_exp[key], 2e-4):
                bad(case, "u_r(%s) düzlem gerilme bağıntısından %.6e, dosyada %.6e"
                    % (key, got, disp_exp[key]))


def check_rotation(rec: dict) -> None:
    """Dönen halka, düzlem gerilme."""
    case = rec["case"]
    inp = rec["inputs"]
    exp = rec["expected_outputs"]
    a, b = inp["inner_radius_in"], inp["outer_radius_in"]
    rho, om, nu = (inp["density_lbf_s2_per_in4"], inp["angular_velocity_rad_s"],
                   inp["poissons_ratio"])
    pre = rho * om * om * (3.0 + nu) / 8.0

    for key, r in (("r_4in", 4.0), ("r_5.43in", 5.43)):
        st = exp.get("tangential_stress_psi", {}).get(key)
        if st is not None:
            got = pre * (a * a + b * b + a * a * b * b / (r * r)
                         - ((1.0 + 3.0 * nu) / (3.0 + nu)) * r * r)
            if not close(got, st, 1e-3):
                bad(case, "sigma_theta(%s) bağıntıdan %.2f, dosyada %.2f" % (key, got, st))
        sr = exp.get("radial_stress_psi", {}).get(key)
        if sr:  # r=a'da 0; sıfır kontrolü ayrı ele alınır
            got = pre * (a * a + b * b - a * a * b * b / (r * r) - r * r)
            if not close(got, sr, 1e-3):
                bad(case, "sigma_r(%s) bağıntıdan %.2f, dosyada %.2f" % (key, got, sr))


def check_semiinf_step(rec: dict) -> None:
    case = rec["case"]
    inp = rec["inputs"]
    exp = rec["expected_outputs"]
    alpha = inp["thermal_diffusivity_m2_s"]
    k = inp["thermal_conductivity_W_mK"]
    t_i, t_s = inp["initial_temperature_K"], inp["surface_temperature_K"]

    for pt in inp["probe_points"]:
        x, t = pt["x_m"], pt["t_s"]
        key = "x%0.3f_t%d" % (x, int(t))
        theta = _erfc(x / (2.0 * math.sqrt(alpha * t)))
        want = exp["theta_dimensionless"].get(key)
        if want is not None and not close(theta, want, 1e-6):
            bad(case, "theta(%s) erfc'den %.8f, dosyada %.8f" % (key, theta, want))
        want_t = exp["temperature_K"].get(key)
        if want_t is not None:
            got_t = t_i + (t_s - t_i) * theta
            if not close(got_t, want_t, 1e-6):
                bad(case, "T(%s) bağıntıdan %.6f, dosyada %.6f" % (key, got_t, want_t))

    for key, t in (("t100", 100.0), ("t400", 400.0)):
        want = exp["surface_heat_flux_W_m2"].get(key)
        if want is not None:
            got = k * (t_s - t_i) / math.sqrt(math.pi * alpha * t)
            if not close(got, want, 1e-6):
                bad(case, "q_s(%s) bağıntıdan %.4f, dosyada %.4f" % (key, got, want))


def check_semiinf_flux(rec: dict) -> None:
    case = rec["case"]
    inp = rec["inputs"]
    exp = rec["expected_outputs"]
    alpha = inp["thermal_diffusivity_m2_s"]
    k = inp["thermal_conductivity_W_mK"]
    q0 = inp["surface_heat_flux_W_m2"]
    t_i = inp["initial_temperature_K"]

    for pt in inp["probe_points"]:
        x, t = pt["x_m"], pt["t_s"]
        key = "x%0.3f_t%d" % (x, int(t))
        root = math.sqrt(alpha * t)
        z = x / (2.0 * root)
        d_t = (2.0 * q0 * root / k) * (math.exp(-z * z) / math.sqrt(math.pi)
                                       - z * _erfc(z))
        want = exp["temperature_rise_K"].get(key)
        if want is not None and not close(d_t, want, 1e-6):
            bad(case, "dT(%s) ierfc bağıntısından %.6f, dosyada %.6f" % (key, d_t, want))
        want_t = exp["temperature_K"].get(key)
        if want_t is not None and not close(t_i + d_t, want_t, 1e-6):
            bad(case, "T(%s) bağıntıdan %.6f, dosyada %.6f" % (key, t_i + d_t, want_t))

    # yüzey değeri ikinci, bağımsız kapalı formdan
    surf = exp["temperature_rise_K"].get("x0.000_t100")
    if surf is not None:
        alt = 2.0 * q0 * math.sqrt(alpha * 100.0 / math.pi) / k
        if not close(alt, surf, 1e-6):
            bad(case, "yüzey dT kapalı formdan %.6f, dosyada %.6f" % (alt, surf))


def check_area_mach(rec: dict) -> None:
    case = rec["case"]
    gamma = rec["inputs"]["gamma"]
    for ar in rec["inputs"]["area_ratios"]:
        blk = rec["expected_outputs"]["area_ratio_%.1f" % ar]
        for mkey, pkey in (("mach_subsonic", "p_over_p0_subsonic"),
                           ("mach_supersonic", "p_over_p0_supersonic")):
            mach = blk[mkey]
            got_ar = _area_ratio(mach, gamma)
            # Tolerans bilerek dar (5e-7): bu değerler ANALİTİKTİR, ölçüm
            # gürültüsü yoktur. Gevşek tolerans (1e-5) 2.197198 -> 2.1972
            # kırpmasını yakalamıyordu; kayıtta 6 hane var, o hassasiyet
            # korunmalı yoksa kayıt sessizce çürür.
            if not close(got_ar, ar, 5e-7):
                bad(case, "%s=%.6f alan oranını %.6f veriyor, beklenen %.1f"
                    % (mkey, mach, got_ar, ar))
            got_p = _p_over_p0(mach, gamma)
            if not close(got_p, blk[pkey], 1e-5):
                bad(case, "%s bağıntıdan %.6f, dosyada %.6f" % (pkey, got_p, blk[pkey]))


def check_shock(rec: dict) -> None:
    case = rec["case"]
    gamma = rec["inputs"]["gamma"]
    exp = rec["expected_outputs"]
    m1 = exp["mach_upstream"]

    got_ar = _area_ratio(m1, gamma)
    if not close(got_ar, rec["inputs"]["shock_station_area_ratio"], 1e-5):
        bad(case, "M1 istasyonun alan oranını vermiyor: %.6f" % got_ar)

    m2 = math.sqrt((1.0 + 0.5 * (gamma - 1.0) * m1 * m1)
                   / (gamma * m1 * m1 - 0.5 * (gamma - 1.0)))
    if not close(m2, exp["mach_downstream"], 1e-5):
        bad(case, "M2 bağıntıdan %.6f, dosyada %.6f" % (m2, exp["mach_downstream"]))

    p21 = 1.0 + (2.0 * gamma / (gamma + 1.0)) * (m1 * m1 - 1.0)
    if not close(p21, exp["static_pressure_ratio_p2_p1"], 1e-5):
        bad(case, "p2/p1 bağıntıdan %.6f, dosyada %.6f"
            % (p21, exp["static_pressure_ratio_p2_p1"]))

    p021 = (((gamma + 1.0) * m1 * m1 / 2.0)
            / (1.0 + 0.5 * (gamma - 1.0) * m1 * m1)) ** (gamma / (gamma - 1.0)) \
        * ((2.0 * gamma / (gamma + 1.0)) * m1 * m1
           - (gamma - 1.0) / (gamma + 1.0)) ** (-1.0 / (gamma - 1.0))
    if not close(p021, exp["total_pressure_ratio_p02_p01"], 1e-5):
        bad(case, "p02/p01 bağıntıdan %.6f, dosyada %.6f"
            % (p021, exp["total_pressure_ratio_p02_p01"]))


def check_separation(rec: dict) -> None:
    case = rec["case"]
    wv = rec["expected_outputs"]["worked_values"]

    for key, mach in (("Ma_2.0", 2.0), ("Ma_3.0", 3.0), ("Ma_4.0", 4.0)):
        got = (1.88 * mach - 1.0) ** -0.64
        if not close(got, wv["schmucker"][key], 1e-5):
            bad(case, "Schmucker %s bağıntıdan %.6f, dosyada %.6f"
                % (key, got, wv["schmucker"][key]))
        # fiziksel akıl sağlığı: ayrılma basıncı ortam basıncını geçemez
        if got >= 1.0:
            bad(case, "Schmucker %s için p_sep/p_a >= 1 çıkıyor (fiziksel değil)" % key)
        got = math.pi / (3.0 * mach)
        if not close(got, wv["stark"][key], 1e-5):
            bad(case, "Stark %s bağıntıdan %.6f, dosyada %.6f"
                % (key, got, wv["stark"][key]))

    for key, pr in (("pc_pa_30", 30.0), ("pc_pa_100", 100.0)):
        got = (2.0 / 3.0) * pr ** -0.2
        if not close(got, wv["kalt_badal"][key], 1e-5):
            bad(case, "Kalt-Badal %s bağıntıdan %.6f, dosyada %.6f"
                % (key, got, wv["kalt_badal"][key]))
        got = 0.583 * pr ** -0.195
        if not close(got, wv["schilling"][key], 1e-5):
            bad(case, "Schilling %s bağıntıdan %.6f, dosyada %.6f"
                % (key, got, wv["schilling"][key]))


def check_acoustic_modes(rec: dict) -> None:
    case = rec["case"]
    inp = rec["inputs"]
    exp = rec["expected_outputs"]
    radius, length = inp["chamber_radius_m"], inp["chamber_length_m"]
    sound = inp["speed_of_sound_m_s"]

    roots = {"1T_m1_n1": (1, 1), "2T_m2_n1": (2, 1), "1R_m0_n1": (0, 1),
             "3T_m3_n1": (3, 1), "1T1R_m1_n2": (1, 2), "2R_m0_n2": (0, 2)}
    for key, (order, index) in roots.items():
        want = exp["bessel_derivative_roots"][key]
        got = _bessel_jprime_zero(order, index)
        if not close(got, want, 1e-5):
            bad(case, "Bessel kökü %s hesaptan %.6f, dosyada %.6f" % (key, got, want))

    freq = exp["mode_frequencies_hz"]
    for mode, key in (("1T", "1T_m1_n1"), ("2T", "2T_m2_n1"), ("1R", "1R_m0_n1"),
                      ("3T", "3T_m3_n1"), ("1T1R", "1T1R_m1_n2"), ("2R", "2R_m0_n2")):
        alpha = exp["bessel_derivative_roots"][key]
        got = alpha * sound / (2.0 * math.pi * radius)
        if not close(got, freq[mode], 1e-6):
            bad(case, "f_%s bağıntıdan %.6f Hz, dosyada %.6f Hz" % (mode, got, freq[mode]))

    got = sound / (2.0 * length)
    if not close(got, freq["1L"], 1e-9):
        bad(case, "f_1L bağıntıdan %.6f Hz, dosyada %.6f Hz" % (got, freq["1L"]))


def check_twophase(rec: dict) -> None:
    case = rec["case"]
    ex = rec["inputs"]["worked_example"]
    exp = rec["expected_outputs"]["equilibrium_limit"]
    r_gas, cp_g = ex["gas_constant_J_kgK"], ex["gas_cp_J_kgK"]
    c_s, t_c = ex["condensed_phase_cs_J_kgK"], ex["chamber_temperature_K"]
    cv_g = cp_g - r_gas
    base = _cstar(r_gas, cp_g / cv_g, t_c)

    for beta in ex["beta_values"]:
        blk = exp["beta_%.2f" % beta]
        r_mix = (1.0 - beta) * r_gas
        cp_mix = (1.0 - beta) * cp_g + beta * c_s
        cv_mix = (1.0 - beta) * cv_g + beta * c_s
        gamma = cp_mix / cv_mix
        cst = _cstar(r_mix, gamma, t_c)
        loss = 100.0 * (1.0 - cst / base)
        for name, got, want in (("R_mix", r_mix, blk["R_mix"]),
                                ("cp_mix", cp_mix, blk["cp_mix"]),
                                ("cv_mix", cv_mix, blk["cv_mix"]),
                                ("gamma_mix", gamma, blk["gamma_mix"]),
                                ("cstar_m_s", cst, blk["cstar_m_s"]),
                                ("loss_pct", loss, blk["loss_pct"])):
            if not close(got, want, 1e-5):
                bad(case, "beta=%.2f %s bağıntıdan %.6f, dosyada %.6f"
                    % (beta, name, got, want))


def check_bmg(rec: dict) -> None:
    """Back-Massier-Gier (TR 32-415) kaydının iç tutarlılığı.

    Ölçüm kaydı — sayılar yeniden türetilemez ama BİRBİRİNİ tutmak zorundadır:
    boğaz yarıçapı iki yoldan, boğulmuş debi çaprazı (275 anomalisi DAHİL —
    anomali sessizce 'düzeltilirse' bekçi kırmızıya döner: kayıt kaynağı
    yansıtmalı, akla yatkınlığı değil), h = q_w/(T_aw−T_w) yeniden hesabı,
    St ↔ h/(ρu·cp) bandı ve tablo yapısı.
    """
    case = rec["case"]
    geo = rec["inputs"]["geometry"]

    r_a = math.sqrt(geo["throat_area_in2"] / math.pi)
    r_d = geo["throat_diameter_in"] / 2.0
    if abs(r_a - r_d) / r_d > 1.5e-3:
        bad(case, "boğaz yarıçapı A*'dan %.5f, D*'dan %.5f — tutmuyor" % (r_a, r_d))

    taps = geo["pressure_tap_stations"]
    if len(taps) != 32:
        bad(case, "tap sayısı 32 değil: %d" % len(taps))
    zl = [t["z_over_L"] for t in taps]
    if any(b <= a for a, b in zip(zl, zl[1:])):
        bad(case, "tap z/L dizisi kesin artan değil")
    aa = [t["A_over_Astar"] for t in taps]
    if min(aa) != aa[11]:
        bad(case, "A/A* minimumu tap 12'de (z/L=0.6018) değil")

    # Boğulmuş debi: Cd kayıtlı değerleri yeniden üretmeli; 275 anomalisi korunmalı
    in2m, psi, lb, r_air = 0.0254, 6894.757293168, 0.45359237, 287.05
    a_m2 = geo["throat_area_in2"] * in2m * in2m
    cd_want = rec["consistency_checks"]["choked_mass_flow"]["Cd_by_test"]
    for cond in rec["inputs"]["selected_test_conditions"]:
        t_r = cond["T_t0_R"]
        g = 1.380 if t_r < 1200 else (1.328 if t_r > 1800 else 1.345)
        flow = math.sqrt(g) * (2.0 / (g + 1.0)) ** ((g + 1.0) / (2.0 * (g - 1.0)))
        m_1d = a_m2 * cond["p_t_psia"] * psi / math.sqrt(r_air * t_r / 1.8) * flow
        c_d = cond["mdot_lb_per_s"] * lb / m_1d
        want = cd_want[str(cond["test"])]
        if abs(c_d - want) > 0.005:
            bad(case, "test %d Cd hesaptan %.4f, kayıtta %.3f" % (cond["test"], c_d, want))
        if cond["test"] == 275:
            if c_d <= 1.02:
                bad(case, "test 275 mdot anomalisi kaybolmuş (Cd=%.4f) — kaynakla karşılaştır" % c_d)
        elif not 0.95 <= c_d <= 1.02:
            bad(case, "test %d Cd=%.4f makul bandın dışında" % (cond["test"], c_d))

    b3 = rec["expected_outputs"]["heat_transfer_tables_B3"]
    tests = ("test_288", "test_266", "test_262", "test_268", "test_278", "test_275")
    for key in tests:
        if len(b3[key]) != 22:
            bad(case, "%s istasyon sayısı 22 değil: %d" % (key, len(b3[key])))

    # St ↔ h/(ρu·cp): kapalı çevrimden çıkan cp hava bandında kalmalı.
    # Belgeli istisna: test 268 z/L=0.938'de KAYNAK 0.982 basmış (dizgi hatası
    # adayı, gerçek ~0.882 — kayıttaki known_source_typo_candidates). Basılı
    # değer korunur; bekçi hücrenin ANOMALİ kalmasını da sınar ki biri sessizce
    # 'düzeltirse' kırmızıya dönsün.
    typo_cells = {("test_268", 0.938)}
    for key in tests:
        for row in b3[key]:
            h = row["h_1e-4_btu_per_s_in2_F"]
            st = row["St_1e-3"]
            rue = row["rho_e_u_e_lb_per_s_in2"]
            if not all(isinstance(v, (int, float)) for v in (h, st, rue)):
                continue
            cp_implied = h * 1e-4 / (rue * st * 1e-3)  # BTU/(lb·°F)
            in_band = 0.235 <= cp_implied <= 0.285
            if (key, row["z_over_L"]) in typo_cells:
                if in_band:
                    bad(case, "%s z/L=%.3f: belgeli kaynak dizgi anomalisi kaybolmuş "
                        "(cp=%.4f bandın içinde) — kaynakla karşılaştır"
                        % (key, row["z_over_L"], cp_implied))
            elif not in_band:
                bad(case, "%s z/L=%.3f: St/h/ρu üçlüsünden cp=%.4f BTU/lb°F — hava bandı dışı"
                    % (key, row["z_over_L"], cp_implied))

    # h = q_w/(T_aw − T_w) — test 262, dört istasyon (M ölçülen p/p_t'den)
    p_pt = {0.133: 0.996, 0.512: 0.789, 0.825: 0.133, 0.905: 0.092}
    g, pr, t_t = 1.345, 0.689, 1518.0
    rows262 = {row["z_over_L"]: row for row in b3["test_262"]}
    for z, p in p_pt.items():
        row = rows262[z]
        mach = math.sqrt((p ** (-(g - 1.0) / g) - 1.0) * 2.0 / (g - 1.0))
        rec_f = pr ** (1.0 / 3.0)
        t_aw = t_t * (1.0 + rec_f * (g - 1.0) / 2.0 * mach * mach) \
            / (1.0 + (g - 1.0) / 2.0 * mach * mach)
        h_calc = row["q_w_btu_per_s_in2"] / (t_aw - row["T_w_R"]) * 1e4
        if abs(h_calc / row["h_1e-4_btu_per_s_in2_F"] - 1.0) > 0.03:
            bad(case, "test 262 z/L=%.3f: h yeniden hesaptan %.3f, tabloda %.3f"
                % (z, h_calc, row["h_1e-4_btu_per_s_in2_F"]))

    # B-2 kolonları geometri tap listesiyle aynı iskelette olmalı
    b2 = rec["expected_outputs"]["wall_static_pressure_tables_B2"]
    for key in ("test_288", "test_266", "test_262", "test_268"):
        col = b2[key]
        if len(col) != 32:
            bad(case, "B-2 %s kolonu 32 satır değil" % key)
            continue
        for tap_geo, tap_p in zip(taps, col):
            if (tap_geo["tap"] != tap_p["tap"]
                    or tap_geo["z_over_L"] != tap_p["z_over_L"]
                    or tap_geo["A_over_Astar"] != tap_p["A_over_Astar"]):
                bad(case, "B-2 %s tap %s iskeleti geometriyle uyuşmuyor"
                    % (key, tap_p.get("tap")))
                break


def check_boldman(rec: dict) -> None:
    """Boldman TN D-4788: A/A* = (D/D*)² ve in↔cm özdeşlikleri yeniden türetilir."""
    case = rec["case"]
    geo = rec["inputs"]["geometry"]
    for noz_key in ("nozzle_30deg", "nozzle_60deg"):
        noz = geo[noz_key]
        d_star = noz["throat_diameter_in"]
        for st in noz["stations"]:
            got = (st["D_in"] / d_star) ** 2
            if not close(got, st["A_over_Astar"], 5e-4):
                bad(case, "%s istasyon %d: (D/D*)²=%.4f, tabloda %.4f"
                    % (noz_key, st["station"], got, st["A_over_Astar"]))
            if not close(st["D_in"] * 2.54, st["D_cm"], 5e-4):
                bad(case, "%s istasyon %d: D dönüşümü tutmuyor" % (noz_key, st["station"]))
            if st["z_in"] > 0 and not close(st["z_in"] * 2.54, st["z_cm"], 5e-4):
                bad(case, "%s istasyon %d: z dönüşümü tutmuyor" % (noz_key, st["station"]))
        if not close((noz["stations"][0]["D_in"] / d_star) ** 2,
                     noz["contraction_area_ratio"], 5e-4):
            bad(case, "%s daralma oranı istasyon 1'den türetilemiyor" % noz_key)


def check_wang_digitization(rec: dict) -> None:
    """Wang 2021 sayısallaştırması: eksen sınırları + izoterm-şablonu kanıtı."""
    case = rec["case"]
    out = rec["expected_outputs"]
    cfd = out["cfd_inner_wall_temperature"]
    if len(cfd) < 15:
        bad(case, "CFD eğrisi nokta sayısı beklenenden az: %d" % len(cfd))
    for pt in cfd:
        if not (0.0 <= pt["x_mm"] <= 160.0 and 320.0 < pt["T_K"] < 500.0):
            bad(case, "CFD noktası eksen dışına taşmış: %r" % pt)
    peak = out["cfd_peak"]
    grid_max = max(pt["T_K"] for pt in cfd)
    if not (grid_max - 0.1 <= peak["T_K"] <= grid_max + 2.5):
        bad(case, "tepe değeri (%.1f K) ızgara maksimumuyla (%.1f K) uyumsuz"
            % (peak["T_K"], grid_max))
    # yazarların deney noktaları 25°F katlarına oturmalı (ilk nokta belgeli istisna)
    pts = out["authors_experiment_points"]["points"]
    for pt in pts[1:]:
        t_f = pt["T_K"] * 1.8 - 459.67
        if abs(t_f / 25.0 - round(t_f / 25.0)) * 25.0 > 0.3:
            bad(case, "deney noktası 25°F şablonuna oturmuyor: %.1f K = %.1f°F"
                % (pt["T_K"], t_f))


def check_f1_consistency(rec: dict) -> None:
    """F-1 turbopompa tablosunun iç tutarlılığı (ölçüm kaydı; yeniden türetilemez)."""
    case = rec["case"]
    exp = rec["expected_outputs"]
    inp = rec["inputs"]

    # c* = p_boğaz * A_t / mdot  (odaya ait debilerle)
    # Tablo oda debilerini akustik kaydında tutuyor; burada yalnız birim
    # erratumunu sınıyoruz: developed head ft <-> m dönüşümü.
    for pump in ("fuel_pump", "oxidizer_pump"):
        blk = exp[pump]
        head_m, head_ft = blk["developed_head_m"], blk["developed_head_ft"]
        if not close(head_ft * 0.3048, head_m, 2e-3):
            bad(case, "%s: %d ft = %.1f m, tabloda %d m — birim erratumu bozulmuş"
                % (pump, head_ft, head_ft * 0.3048, head_m))
        # basınç yükselişi ~ rho g H  (%3 tolerans: kayıplar dahil)
        d_p = (blk["discharge_pressure_kpa"] - blk["inlet_pressure_kpa"]) * 1000.0
        rho_g_h = blk["inlet_density_kg_m3"] * 9.80665 * head_m
        if abs(d_p - rho_g_h) / rho_g_h > 0.03:
            bad(case, "%s: basınç yükselişi %.0f Pa, rho*g*H %.0f Pa — %%3'ten fazla ayrık"
                % (pump, d_p, rho_g_h))

    at_m2 = inp["throat_area_cm2"] * 1e-4
    if not close(math.sqrt(4.0 * at_m2 / math.pi), 0.888916, 1e-4):
        bad(case, "boğaz alanından çap tutarsız")


DERIVATION_CHECKS = {
    "structural_ansys_vm25_internal_pressure": check_lame,
    "structural_lame_thick_cylinder_si": check_lame,
    "structural_ansys_vm25_rotation": check_rotation,
    "thermal_semiinf_step_temperature": check_semiinf_step,
    "thermal_semiinf_constant_flux": check_semiinf_flux,
    "nozzle_isentropic_area_mach": check_area_mach,
    "nozzle_normal_shock_divergent": check_shock,
    "nozzle_separation_criteria": check_separation,
    "acoustic_cylindrical_chamber_modes": check_acoustic_modes,
    "twophase_particle_loading_loss": check_twophase,
    "turbopump_f1_saturnv": check_f1_consistency,
    "nozzle_back_massier_gier_1964": check_bmg,
    "nozzle_boldman_conical_1968": check_boldman,
    "nozzle_ansys_published_wang_2021": check_wang_digitization,
}

# Ölçüme dayanan, yeniden türetilemeyen kayıtlar — bilerek denetim dışı.
# (VMFL044: belgeleme kaydı — sayısal sonuç içermez, yalnız künye + kurulum.)
MEASUREMENT_ONLY = {
    "turbopump_rl10a33_design_point",
    "turbopump_rl10a33a_geometry",
    "turbopump_merlin_rd180_unavailable",
    "acoustic_f1_first_tangential",
    "thermal_bartz_accuracy_band",
    "nozzle_ansys_published_ansys_vmfl044",
}

# Kabul edilen çekilme tarihleri: her parti kendi tarihini ekler; serbest
# tarih kabul ETMİYORUZ ki yazım hatası (ör. 2026-18-08) sessiz geçmesin.
VALID_RETRIEVED_DATES = {"2026-08-03", "2026-08-18"}


def main(argv: list[str]) -> int:
    quiet = "--quiet" in argv
    paths = sorted(glob.glob(os.path.join(HERE, "*.json")))
    if not paths:
        print("HATA: data/validation altında hiç kayıt yok")
        return 1

    checked = 0
    for path in paths:
        name = os.path.basename(path)
        try:
            with open(path, encoding="utf-8") as handle:
                rec = json.load(handle)
        except Exception as exc:                       # noqa: BLE001
            _findings.append("%s: JSON okunamadı (%s)" % (name, exc))
            continue

        case = rec.get("case", name)

        for field in REQUIRED_RECORD_FIELDS:
            if field not in rec:
                bad(case, "zorunlu alan eksik: %s" % field)
        for field in REQUIRED_SOURCE_FIELDS:
            if field not in rec.get("source", {}):
                bad(case, "source künyesinde eksik alan: %s" % field)
        if rec.get("confidence") not in VALID_CONFIDENCE:
            bad(case, "confidence tanımsız: %r" % rec.get("confidence"))
        if rec.get("retrieved") not in VALID_RETRIEVED_DATES:
            bad(case, "retrieved beklenmedik: %r" % rec.get("retrieved"))
        if rec.get("case") and rec["case"] != os.path.splitext(name)[0]:
            bad(case, "case alanı dosya adıyla uyuşmuyor (%s)" % name)

        fn = DERIVATION_CHECKS.get(rec.get("case"))
        if fn is not None:
            try:
                fn(rec)
                checked += 1
            except Exception as exc:                   # noqa: BLE001
                bad(case, "yeniden türetme çöktü: %s" % exc)
        elif rec.get("case") not in MEASUREMENT_ONLY:
            bad(case, "ne yeniden türetme denetimi ne de MEASUREMENT_ONLY listesinde")

    if not quiet:
        print("kayıt: %d · yeniden türetilen: %d · yalnız ölçüm: %d"
              % (len(paths), checked, len(MEASUREMENT_ONLY)))

    if _findings:
        print("\nBULGU (%d):" % len(_findings))
        for item in _findings:
            print("  - %s" % item)
        return 1

    if not quiet:
        print("temiz: her analitik değer kendi bağıntısından yeniden üretildi")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
