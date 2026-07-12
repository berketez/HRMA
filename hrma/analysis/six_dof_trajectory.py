"""6 serbestlik dereceli (6-DOF) rijit gövde uçuş dinamiği.

Mevcut trajectory_analysis (düzlemsel nokta-kütle) korunur; bu modül
BAĞIMSIZ bir 6-DOF katmanı ekler: tutum (quaternion), açısal hız, rüzgâra
tepki (weathercocking) ve statik stabilite. Aerodinamik katsayılar
Barrowman yöntemiyle (Barrowman 1967; OpenRocket teknik dokümantasyonu,
Niskanen 2009) gövde+kanat geometrisinden türetilir.

Durum vektörü (13): [r(3), v(3), q(4), ω(3)]
  r, v : atış-yeri eksenli düz-Dünya ataleti (z yukarı, x kuzey, y doğu)
  q    : gövde→atalet birim quaternion'u (skaler-önce: w,x,y,z)
  ω    : gövde eksenli açısal hız [rad/s]
Kütle ve itki zamana bağlı dış girdi (sabit itki ya da transient eğri).

Kuvvetler:
  - Yerçekimi: ters-kare g(h), atalet -z
  - İtki: gövde +x ekseni boyunca (jimbal yok)
  - Aero: hava-bağıl hız u = v − w_rüzgâr üzerinden;
      eksenel: -q̄·S·C_A (Mach-bağımlı C_A ≈ C_d eğrisi)
      normal : -q̄·S·C_Nα·α, u'nun enine bileşeni yönünde
    Normal kuvvet CP'de etkir; CP−CG kolu momenti üretir (statik marj
    pozitifse rüzgâra dönme/weathercocking restoratif olur).
  - Sönüm: pitch/yaw için C_mq ≈ −C_Nα·((x_cp−x_cg)/d)² yaklaşımı
    (kuyruk hacim katkısı baskın; Niskanen §4.2.3 basitleştirmesi).

Sınırlar (dürüst beyan):
  - Düz-Dünya ataleti (Coriolis yok) — sounding roket menzilinde ihmal
  - Jimbal/rüzgâr türbülansı/aeroelastisite yok; roll dinamiği pasif
    (kanat cant açısı modellenmez, küçük roll sönümü uygulanır)
  - Barrowman küçük-α lineer aerodinamiği (α ≲ 10-15°); büyük α'da
    yalnızca eğilim/kararlılık göstergesi olarak yorumlanmalı
"""

import numpy as np
from scipy.integrate import solve_ivp

from hrma.constants import ISA_LAYERS  # merkezi USSA 1976 tablosu

G0 = 9.80665          # m/s²
R_EARTH = 6_371_000.0  # m
R_AIR = 287.053        # J/(kg·K)
GAMMA_AIR = 1.4


# ---------------------------------------------------------------------------
# Atmosfer (merkezi ISA_LAYERS tablosundan yoğunluk + ses hızı)
# ---------------------------------------------------------------------------

def _atmosphere(h):
    """USSA 1976: (rho [kg/m³], a_ses [m/s]). h geometrik irtifa [m].

    ISA_LAYERS kayıt formatı: (h_taban, T_taban, lapse, P_taban) —
    constants.py'deki sırayla birebir (karıştırma NaN üretir!).
    """
    h = max(h, 0.0)
    H = h * R_EARTH / (R_EARTH + h)  # geopotansiyel
    T, P = 288.15, 101325.0
    for base, T_base, lapse, P_base in ISA_LAYERS:
        if H >= base:
            if lapse == 0.0:
                T = T_base
                P = P_base * np.exp(-G0 * (H - base) / (R_AIR * T_base))
            else:
                T = T_base + lapse * (H - base)
                P = P_base * (T / T_base) ** (-G0 / (lapse * R_AIR))
    rho = P / (R_AIR * T)
    return rho, np.sqrt(GAMMA_AIR * R_AIR * T)


def _drag_coefficient_mach(mach, cd0):
    """Mach-bağımlı eksenel katsayı (trajectory_analysis ile aynı şekil):
    subsonik plato, transonik tepe ~1.5·Cd0 @ M≈1.05, süpersonik sönüm."""
    if mach < 0.8:
        return cd0
    if mach < 1.05:
        return cd0 * (1.0 + 2.0 * (mach - 0.8))       # 0.8→1.05: 1→1.5
    return cd0 * (1.05 + 0.45 * np.exp(-1.3 * (mach - 1.05)))


# ---------------------------------------------------------------------------
# Barrowman aerodinamiği
# ---------------------------------------------------------------------------

class BarrowmanAero:
    """Gövde+kanat için C_Nα [1/rad] ve CP konumu (burundan) [m].

    Barrowman (1967) lineer teorisi; referans alan gövde kesiti π·d²/4.
    """

    def __init__(self, body_diameter, nose_length, body_length,
                 nose_type='ogive', fin_count=4, fin_root_chord=0.0,
                 fin_tip_chord=0.0, fin_span=0.0, fin_sweep=0.0,
                 fin_position=None):
        """
        Args:
            body_diameter: gövde çapı d [m]
            nose_length: burun uzunluğu [m]
            body_length: TOPLAM araç uzunluğu (burun dahil) [m]
            nose_type: 'ogive' | 'conical' | 'parabolic'
            fin_count: kanat sayısı (3 veya 4)
            fin_root_chord/tip_chord/span: kanat kök/uç veteri, açıklık [m]
            fin_sweep: kök hücum kenarından uç hücum kenarına eksenel
                       kayma m_sweep [m]
            fin_position: kanat kök hücum kenarının burundan mesafesi [m]
                          (None → kuyruğa dayalı: L − c_root)
        """
        self.d = float(body_diameter)
        self.S_ref = np.pi * self.d ** 2 / 4.0
        self.L = float(body_length)

        # --- Burun (Barrowman: tüm burun tipleri için C_Nα = 2/rad) ---
        cn_nose = 2.0
        xcp_factor = {'conical': 2.0 / 3.0, 'ogive': 0.466,
                      'parabolic': 0.5}.get(nose_type, 0.466)
        xcp_nose = xcp_factor * float(nose_length)

        # --- Kanatlar (varsa) ---
        cn_fins, xcp_fins = 0.0, 0.0
        if fin_count and fin_span > 0 and fin_root_chord > 0:
            n = int(fin_count)
            s = float(fin_span)
            cr, ct = float(fin_root_chord), float(fin_tip_chord)
            m = float(fin_sweep)
            xf = (self.L - cr) if fin_position is None else float(fin_position)
            # Orta-veter hattı uzunluğu l (hücum kenarı süpürmesiyle)
            l_mid = np.sqrt(s ** 2 + (m + (ct - cr) / 2.0) ** 2)
            cn_fins = (4.0 * n * (s / self.d) ** 2) / \
                (1.0 + np.sqrt(1.0 + (2.0 * l_mid / (cr + ct)) ** 2))
            # Gövde girişim faktörü
            R_body = self.d / 2.0
            cn_fins *= 1.0 + R_body / (s + R_body)
            # Kanat CP'si (Barrowman standart ifadesi)
            xcp_rel = (m * (cr + 2.0 * ct)) / (3.0 * (cr + ct)) \
                + (1.0 / 6.0) * (cr + ct - cr * ct / (cr + ct))
            xcp_fins = xf + xcp_rel

        self.cn_alpha = cn_nose + cn_fins            # [1/rad]
        self.x_cp = (cn_nose * xcp_nose + cn_fins * xcp_fins) / self.cn_alpha
        self.cn_alpha_nose, self.cn_alpha_fins = cn_nose, cn_fins

    def static_margin(self, x_cg):
        """Statik marj [kalibre]: (x_cp − x_cg)/d. Pozitif → kararlı."""
        return (self.x_cp - x_cg) / self.d


# ---------------------------------------------------------------------------
# Quaternion yardımcıları (skaler-önce, birim)
# ---------------------------------------------------------------------------

def _quat_to_dcm(q):
    """Gövde→atalet dönüşüm matrisi."""
    w, x, y, z = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
        [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
        [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
    ])


def _quat_derivative(q, omega_body):
    """q̇ = ½·q⊗[0,ω]"""
    w, x, y, z = q
    p, qy, r = omega_body
    return 0.5 * np.array([
        -x * p - y * qy - z * r,
        w * p + qy * z - r * y,
        w * qy + r * x - p * z,
        w * r + p * y - qy * x,
    ])


def _quat_from_elevation_azimuth(elevation_deg, azimuth_deg):
    """Gövde +x'ini verilen yükseliş/azimut doğrultusuna çeviren quaternion.

    elevation 90° = dik atış. Azimut kuzeyden saat yönünde (x=K, y=D).
    """
    el = np.radians(elevation_deg)
    az = np.radians(azimuth_deg)
    # Hedef doğrultu (atalet)
    target = np.array([np.cos(el) * np.cos(az),
                       np.cos(el) * np.sin(az),
                       np.sin(el)])
    xb = np.array([1.0, 0.0, 0.0])
    v = np.cross(xb, target)
    c = float(np.dot(xb, target))
    if np.linalg.norm(v) < 1e-12:
        return np.array([1.0, 0, 0, 0]) if c > 0 else np.array([0.0, 0, 1, 0])
    s = np.sqrt((1.0 + c) * 2.0)
    q = np.array([s / 2.0, v[0] / s, v[1] / s, v[2] / s])
    return q / np.linalg.norm(q)


# ---------------------------------------------------------------------------
# 6-DOF çözücü
# ---------------------------------------------------------------------------

class SixDOFTrajectory:
    def __init__(self, aero, dry_mass, propellant_mass,
                 thrust_curve=None, thrust=None, burn_time=None,
                 x_cg_full=None, x_cg_empty=None,
                 cd0=0.5, wind_speed=0.0, wind_direction_deg=0.0,
                 launch_elevation_deg=90.0, launch_azimuth_deg=0.0,
                 rail_length=5.0, roll_damping=0.05):
        """
        Args:
            aero: BarrowmanAero örneği
            dry_mass / propellant_mass: kg
            thrust_curve: {'time': [...], 'thrust': [...]} (transient çıktısı)
                          ya da None → sabit thrust/burn_time kullanılır
            x_cg_full/empty: dolu/boş CG konumu (burundan) [m];
                             None → 0.55·L / 0.5·L kaba tahmini
            cd0: subsonik eksenel katsayı
            wind_speed: yatay rüzgâr [m/s]; wind_direction_deg RÜZGÂRIN
                        GELDİĞİ yön (meteoroloji konvansiyonu, kuzeyden)
            rail_length: atış rayı boyu [m] — ray üstünde tutum kilitli
            roll_damping: pasif roll sönüm katsayısı
        """
        self.aero = aero
        self.m_dry = float(dry_mass)
        self.m_prop = float(propellant_mass)

        if thrust_curve is not None:
            t = np.asarray(thrust_curve['time'], dtype=float)
            F = np.asarray(thrust_curve['thrust'], dtype=float)
            if t[0] > 0.0:
                t = np.insert(t, 0, 0.0)
                F = np.insert(F, 0, F[0])
            self._t_thrust, self._F_thrust = t, F
            self.t_burn = float(t[-1])
            self._impulse = float(np.trapz(F, t))
        else:
            if not thrust or not burn_time:
                raise ValueError("thrust_curve yoksa thrust ve burn_time zorunlu")
            self._t_thrust = np.array([0.0, float(burn_time)])
            self._F_thrust = np.array([float(thrust), float(thrust)])
            self.t_burn = float(burn_time)
            self._impulse = float(thrust) * float(burn_time)

        L = aero.L
        self.x_cg_full = float(x_cg_full) if x_cg_full else 0.55 * L
        self.x_cg_empty = float(x_cg_empty) if x_cg_empty else 0.50 * L
        self.cd0 = float(cd0)
        # Rüzgârın GELDİĞİ yönden esen yatay rüzgâr vektörü (hava hareketi)
        wd = np.radians(wind_direction_deg)
        self.wind = -float(wind_speed) * np.array([np.cos(wd), np.sin(wd), 0.0])
        self.q0 = _quat_from_elevation_azimuth(launch_elevation_deg,
                                               launch_azimuth_deg)
        self.rail_length = float(rail_length)
        self.roll_damping = float(roll_damping)

    # ---- zamana bağlı büyüklükler ----

    def _thrust_at(self, t):
        if t >= self.t_burn:
            return 0.0
        return float(np.interp(t, self._t_thrust, self._F_thrust))

    def _mass_at(self, t):
        """Yakıt, itki eğrisiyle orantılı tüketilir (∝ birikmiş impuls)."""
        if t >= self.t_burn:
            return self.m_dry
        # birikmiş impuls oranı
        ti = np.clip(t, self._t_thrust[0], self._t_thrust[-1])
        mask = self._t_thrust <= ti
        t_part = np.append(self._t_thrust[mask], ti)
        F_part = np.append(self._F_thrust[mask], self._thrust_at(ti))
        frac = np.trapz(F_part, t_part) / max(self._impulse, 1e-9)
        return self.m_dry + self.m_prop * (1.0 - frac)

    def _cg_at(self, t):
        m = self._mass_at(t)
        frac = (m - self.m_dry) / max(self.m_prop, 1e-9)
        return self.x_cg_empty + (self.x_cg_full - self.x_cg_empty) * frac

    def _inertia(self, m):
        """Narin gövde yaklaşımı: I_t = m(3r²+L²)/12, I_x = m·r²/2."""
        r = self.aero.d / 2.0
        I_t = m * (3.0 * r * r + self.aero.L ** 2) / 12.0
        I_x = 0.5 * m * r * r
        return I_x, I_t

    # ---- dinamik ----

    def _derivatives(self, t, y):
        r = y[0:3]
        v = y[3:6]
        q = y[6:10]
        q = q / np.linalg.norm(q)
        w_b = y[10:13]

        m = self._mass_at(t)
        I_x, I_t = self._inertia(m)
        C_bi = _quat_to_dcm(q)          # gövde→atalet
        x_body_i = C_bi[:, 0]           # gövde ekseninin atalet ifadesi

        h = max(r[2], 0.0)
        rho, a_snd = _atmosphere(h)
        g = G0 * (R_EARTH / (R_EARTH + h)) ** 2

        # --- kuvvetler ---
        F_i = np.array([0.0, 0.0, -m * g])
        F_i += self._thrust_at(t) * x_body_i

        u_i = v - self.wind                      # hava-bağıl hız (atalet)
        u_mag = np.linalg.norm(u_i)
        M_b = np.zeros(3)
        if u_mag > 0.5:
            u_b = C_bi.T @ u_i                   # gövde ekseninde
            mach = u_mag / a_snd
            qbar = 0.5 * rho * u_mag ** 2
            S = self.aero.S_ref
            ca = _drag_coefficient_mach(mach, self.cd0)

            # Eksenel kuvvet (harekete karşı)
            F_ax_b = -qbar * S * ca * np.sign(u_b[0]) * np.array([1.0, 0, 0])

            # Normal kuvvet: enine akış bileşenine karşı, CP'de
            u_t = np.array([0.0, u_b[1], u_b[2]])
            u_t_mag = np.linalg.norm(u_t)
            F_n_b = np.zeros(3)
            if u_t_mag > 1e-6:
                alpha = np.arctan2(u_t_mag, abs(u_b[0]))
                F_n_mag = qbar * S * self.aero.cn_alpha * alpha
                F_n_b = -F_n_mag * (u_t / u_t_mag)

            F_aero_b = F_ax_b + F_n_b
            F_i += C_bi @ F_aero_b

            # --- momentler (CP−CG kolu; gövde ekseninde) ---
            x_cg = self._cg_at(t)
            arm = self.aero.x_cp - x_cg          # +x burun yönünde ölçülür
            r_cp_b = np.array([-arm, 0.0, 0.0])  # CP, CG'nin arkasında ise −x
            M_b = np.cross(r_cp_b, F_n_b)
            # Pitch/yaw sönümü: C_mq ≈ −C_Nα·(arm/d)² (kuyruk baskın terim)
            c_mq = -self.aero.cn_alpha * (arm / self.aero.d) ** 2
            d = self.aero.d
            M_b[1] += qbar * S * d * c_mq * (w_b[1] * d / (2.0 * u_mag))
            M_b[2] += qbar * S * d * c_mq * (w_b[2] * d / (2.0 * u_mag))
            M_b[0] += -qbar * S * d * self.roll_damping * \
                (w_b[0] * d / (2.0 * u_mag))

        # Ray fazı: tutum ve açısal hız kilitli (yalnız eksen boyu ivme)
        dist = np.linalg.norm(r - self._r0)
        on_rail = dist < self.rail_length and t < self.t_burn
        if on_rail:
            # Kuvveti ray doğrultusuna izdüşür
            rail_dir = _quat_to_dcm(self.q0)[:, 0]
            F_i = np.dot(F_i, rail_dir) * rail_dir
            if np.dot(F_i, rail_dir) < 0:        # rampada geri kayma yok
                F_i = np.zeros(3)
            q_dot = np.zeros(4)
            w_dot = np.zeros(3)
        else:
            q_dot = _quat_derivative(q, w_b)
            I = np.array([I_x, I_t, I_t])
            w_dot = (M_b - np.cross(w_b, I * w_b)) / I

        return np.concatenate([v, F_i / m, q_dot, w_dot])

    def solve(self, t_max=400.0, max_step=0.1):
        """Kalkıştan APOJEYE kadar entegre eder.

        6-DOF katmanının amacı stabilite/weathercock/apoje analizidir;
        apoje sonrası balistik takla (kurtarma sistemi modellenmediğinden)
        hem fiziksel olarak anlamsız hem de sayısal olarak katı (yüksek ω →
        adım çökmesi) olduğu için apojede sonlanır. Kararsız araçlarda
        |ω| > 15 rad/s (takla) tespiti de erken sonlandırır — Barrowman
        lineer aerodinamiği o rejimde zaten geçersizdir.
        """
        self._r0 = np.zeros(3)
        y0 = np.concatenate([
            self._r0, np.zeros(3), self.q0, np.zeros(3)])

        def hit_ground(t, y):
            return y[2] + 1e-6 if t < 1.0 else y[2]
        hit_ground.terminal = True
        hit_ground.direction = -1

        def apogee_event(t, y):
            # Yanma bitip ray aşıldıktan sonra dikey hız sıfırı keserse dur
            return y[5] if (t > self.t_burn and y[2] > self.rail_length) else 1.0
        apogee_event.terminal = True
        apogee_event.direction = -1

        def tumble_event(t, y):
            return 15.0 - np.linalg.norm(y[10:13])
        tumble_event.terminal = True
        tumble_event.direction = -1

        sol = solve_ivp(self._derivatives, (0.0, t_max), y0,
                        method='RK45', max_step=max_step,
                        events=[hit_ground, apogee_event, tumble_event],
                        dense_output=False, rtol=1e-5, atol=1e-7)
        end_reason = 'time_limit'
        if sol.t_events[0].size:
            end_reason = 'ground'
        elif sol.t_events[1].size:
            end_reason = 'apogee'
        elif sol.t_events[2].size:
            end_reason = 'tumble_detected'

        t = sol.t
        r = sol.y[0:3]
        v = sol.y[3:6]
        q = sol.y[6:10]
        w = sol.y[10:13]

        # Türetilmiş büyüklükler
        speed = np.linalg.norm(v, axis=0)
        alt = r[2]
        i_apogee = int(np.argmax(alt))
        alpha_hist, mach_hist = [], []
        for k in range(len(t)):
            qk = q[:, k] / np.linalg.norm(q[:, k])
            C = _quat_to_dcm(qk)
            u_i = v[:, k] - self.wind
            um = np.linalg.norm(u_i)
            _, a_snd = _atmosphere(max(alt[k], 0.0))
            mach_hist.append(um / a_snd)
            if um > 0.5:
                u_b = C.T @ u_i
                alpha_hist.append(np.degrees(np.arctan2(
                    np.hypot(u_b[1], u_b[2]), abs(u_b[0]))))
            else:
                alpha_hist.append(0.0)

        sm_full = self.aero.static_margin(self.x_cg_full)
        sm_empty = self.aero.static_margin(self.x_cg_empty)
        alpha_arr = np.array(alpha_hist)
        # Yanma sonrası apoje öncesi maksimum α — kararlılık göstergesi
        burn_mask = (t > 1.0) & (t < t[i_apogee]) if i_apogee > 0 else t > 1.0
        max_alpha = float(alpha_arr[burn_mask].max()) if burn_mask.any() else 0.0

        return {
            'time': t,
            'position': r,                    # 3×N [m] (x=K, y=D, z=yukarı)
            'velocity': v,
            'quaternion': q,
            'angular_velocity': w,
            'altitude': alt,
            'speed': speed,
            'mach': np.array(mach_hist),
            'alpha_deg': alpha_arr,
            'apogee': float(alt[i_apogee]),
            'apogee_time': float(t[i_apogee]),
            'max_speed': float(speed.max()),
            'max_mach': float(np.max(mach_hist)),
            'max_alpha_deg': max_alpha,
            'end_reason': end_reason,
            'lateral_drift_at_end': float(np.hypot(r[0, -1], r[1, -1])),
            'static_margin_full': float(sm_full),
            'static_margin_empty': float(sm_empty),
            'stable': bool(sm_full > 1.0 and sm_empty > 1.0 and
                           max_alpha < 15.0),
            'cn_alpha': float(self.aero.cn_alpha),
            'x_cp': float(self.aero.x_cp),
        }
