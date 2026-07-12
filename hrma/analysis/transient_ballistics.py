"""Hibrit motor zaman-çözümlü (transient) iç balistik: Pc(t) ve F(t).

Tasarım çözücüsü (HybridRocketEngine.calculate) sabit nokta etrafında
boyutlandırma yapar; bu modül boyutlandırılmış motoru zamanda yürüterek
GERÇEK kamara basıncı ve itki eğrilerini üretir:

  - Port büyümesi: Marxman G_total kapanışı (RegressionAnalyzer ile aynı
    fizik — tek tanım noktası, kopya formül yok)
  - Anlık O/F → anlık c*: motorun 0.05-çözünürlüklü denge önbelleği
    (HybridRocketEngine._instantaneous_performance) kullanılır
  - Yarı-kararlı kamara: P_c = ṁ_toplam · c* / (C_D · A_t)
    (kamara doldurma süresi ~L*/c_ses ≈ ms mertebesi; yanma süresi ~s
    mertebesinde olduğundan yarı-kararlılık geçerlidir)
  - İtki: F = C_F(P_c) · P_c · A_t. Sabit geometri (ε sabit) ve sabit γ'da
    P_e/P_c oranı sabittir; C_F'in basınca bağımlılığı yalnız basınç-itki
    teriminden gelir: C_F = C_F,mom + ε·(P_e/P_c) − ε·P_a/P_c

Besleme modları:
  'regulated' : ṁ_ox sabit (regülatörlü/süperşarjlı besleme; tasarım değeri)
  'blowdown'  : N₂O kendinden-basınçlı tank (tank_blowdown.N2OTankBlowdown).
                Enjektör SPI orifis modeli: ṁ_ox = K·√(2·ρ_l(T)·ΔP),
                ΔP = P_tank − P_c. Etkin K = C_d·A_inj, t=0'da tasarım
                debisi + gerçek tank basıncından kalibre edilir (tasarım
                noktası tutarlılığı garanti).

Durdurma olayları: yakıt web'i bitti / tank sıvısı bitti / ΔP kararlılık
sınırının altına düştü (SP-8089: ΔP/P_c < 0.05 → yanma kararsızlığı) /
t_max aşıldı.
"""

import numpy as np

from hrma.analysis.regression_analysis import RegressionAnalyzer
from hrma.analysis.tank_blowdown import N2OTankBlowdown

# SP-8089 enjektör kararlılık eşikleri (ΔP/P_c)
DP_RATIO_WARN = 0.15      # bunun altında chugging riski uyarısı
DP_RATIO_UNSTABLE = 0.05  # bunun altında yarı-kararlı model geçersiz → dur


class TransientBallistics:
    """Boyutlandırılmış bir HybridRocketEngine'i zamanda yürütür."""

    def __init__(self, engine, feed_mode='regulated',
                 tank_temperature=293.15, liquid_fill_fraction=0.85,
                 n_steps=400, t_max_factor=1.6):
        """
        Args:
            engine: calculate() çağrılmış HybridRocketEngine örneği
            feed_mode: 'regulated' | 'blowdown'
            tank_temperature: blowdown başlangıç tank sıcaklığı [K]
            liquid_fill_fraction: tank sıvı doluluk oranı (ullage payı)
            n_steps: nominal yanma süresi için adım sayısı
            t_max_factor: t_max = factor · t_b (blowdown uzayabilir)
        """
        required = ('At', 'epsilon', 'gamma', 'D_port_initial', 'L_grain',
                    'rho_f', 'a', 'n', 'mdot_ox', 'C_star', 'P_c', 'P_a')
        missing = [attr for attr in required
                   if getattr(engine, attr, None) is None]
        if missing:
            raise ValueError(
                f"Motor boyutlandırılmamış görünüyor (calculate() çağrıldı mı?); "
                f"eksik: {missing}")
        if feed_mode not in ('regulated', 'blowdown'):
            raise ValueError("feed_mode 'regulated' ya da 'blowdown' olmalı")

        self.e = engine
        self.feed_mode = feed_mode
        self.dt = engine.t_b / n_steps
        self.t_max = t_max_factor * engine.t_b

        # Nozul sabitleri (sabit geometri): P_e/P_c oranı ve momentum C_F'i
        g = float(engine.gamma)
        eps = float(engine.epsilon)
        self._pe_ratio = self._exit_pressure_ratio(g, eps)
        self._cf_momentum = self._momentum_cf(g, self._pe_ratio)
        # Diverjans kaybı: motorun kendi λ'sı (nozul tipine göre)
        self._lambda = getattr(engine, 'lambda_divergence', None) or \
            {'conical': 0.983, 'bell': 0.985,
             'parabolic': 0.975}.get(getattr(engine, 'nozzle_type', 'conical'), 0.983)
        self._cd_nozzle = 0.98  # boğaz debi katsayısı (tasarımla aynı)

        # Blowdown tankı + enjektör kalibrasyonu
        self.tank = None
        self._K_inj = None
        if feed_mode == 'blowdown':
            self.tank = N2OTankBlowdown.from_oxidizer_mass(
                oxidizer_mass=float(engine.m_ox),
                initial_temperature=tank_temperature,
                liquid_fill_fraction=liquid_fill_fraction)
            P_tank0 = self.tank.pressure                    # Pa
            Pc0 = float(engine.P_c) * 1e5                   # Pa
            dP0 = P_tank0 - Pc0
            if dP0 <= 0:
                raise ValueError(
                    f"Tank basıncı ({P_tank0/1e5:.1f} bar) tasarım kamara "
                    f"basıncının ({engine.P_c:.1f} bar) altında — blowdown "
                    f"beslemesi mümkün değil. Kamara basıncını düşürün ya da "
                    f"tankı ısıtın.")
            rho0 = self.tank.props.rho_l(tank_temperature)
            # Etkin C_d·A: t=0'da tasarım debisini gerçek ΔP'de verir
            self._K_inj = float(engine.mdot_ox) / np.sqrt(2.0 * rho0 * dP0)

    # ---------------- nozul yardımcıları ----------------

    @staticmethod
    def _exit_pressure_ratio(gamma, eps):
        """Sabit ε için süpersonik dal P_e/P_c oranı (izentropik)."""
        from scipy.optimize import brentq

        def area_ratio(M):
            return (1.0 / M) * ((2.0 / (gamma + 1.0))
                                * (1.0 + (gamma - 1.0) / 2.0 * M * M)) \
                   ** ((gamma + 1.0) / (2.0 * (gamma - 1.0))) - eps

        Me = brentq(area_ratio, 1.0001, 50.0)
        return (1.0 + (gamma - 1.0) / 2.0 * Me * Me) ** (-gamma / (gamma - 1.0))

    @staticmethod
    def _momentum_cf(gamma, pe_ratio):
        """C_F'in momentum kısmı (Sutton Eq. 3-30, basınç-itki terimi hariç)."""
        return np.sqrt(2.0 * gamma ** 2 / (gamma - 1.0)
                       * (2.0 / (gamma + 1.0)) ** ((gamma + 1.0) / (gamma - 1.0))
                       * (1.0 - pe_ratio ** ((gamma - 1.0) / gamma)))

    def _thrust_coefficient(self, Pc_pa):
        """C_F(P_c): sabit ε'da yalnız basınç-itki terimi değişir."""
        eps = float(self.e.epsilon)
        Pa_pa = float(self.e.P_a) * 1e5
        return (self._lambda * self._cf_momentum
                + eps * self._pe_ratio - eps * Pa_pa / Pc_pa)

    # ---------------- ana çözüm ----------------

    def solve(self):
        e = self.e
        dt = self.dt
        D_port = float(e.D_port_initial)
        D_max = float(getattr(e, 'D_ch', D_port * 10)) * 0.8  # web sınırı
        fuel_available = float(getattr(e, 'm_fuel', None) or
                               e.rho_f * np.pi / 4.0
                               * (D_max ** 2 - D_port ** 2) * e.L_grain)

        t_arr, Pc_arr, F_arr = [], [], []
        mdot_ox_arr, mdot_f_arr, of_arr, D_arr = [], [], [], []
        tankP_arr, tankT_arr = [], []
        warnings_list = []
        event = 'time_limit'

        Pc_pa = float(e.P_c) * 1e5   # yarı-kararlı iterasyon başlangıcı
        t = 0.0
        fuel_burned = 0.0

        while t < self.t_max:
            A_port = np.pi * (D_port / 2.0) ** 2

            # --- besleme + kamara yarı-kararlı kapanışı ---
            # Pc ↔ mdot_ox (blowdown'da ΔP üzerinden) sabit-nokta iterasyonu
            mdot_ox = float(e.mdot_ox)
            for _ in range(6):
                if self.feed_mode == 'blowdown':
                    dP = self.tank.pressure - Pc_pa
                    if dP <= 0:
                        mdot_ox = 0.0
                        break
                    rho_l = self.tank.props.rho_l(self.tank.T)
                    mdot_ox = self._K_inj * np.sqrt(2.0 * rho_l * dP)

                G_ox = mdot_ox / A_port
                reg = RegressionAnalyzer.regression_rate(
                    e.a, e.n, G_ox, rho_f=e.rho_f, port_diameter=D_port,
                    grain_length=e.L_grain, flux_mode=e.flux_mode)
                r_dot = reg['r_dot']
                mdot_f = e.rho_f * r_dot * np.pi * D_port * e.L_grain
                of_inst = mdot_ox / max(mdot_f, 1e-9)
                cstar_inst, _ = e._instantaneous_performance(of_inst)
                Pc_new = ((mdot_ox + mdot_f) * cstar_inst
                          / (self._cd_nozzle * e.At))
                if abs(Pc_new - Pc_pa) < 100.0:  # 1 mbar yakınsama
                    Pc_pa = Pc_new
                    break
                Pc_pa = Pc_new

            if mdot_ox <= 0.0:
                event = 'feed_pressure_lost'
                break

            # SP-8089 enjektör kararlılığı (yalnız blowdown'da anlamlı)
            if self.feed_mode == 'blowdown':
                dp_ratio = (self.tank.pressure - Pc_pa) / Pc_pa
                if dp_ratio < DP_RATIO_UNSTABLE:
                    event = 'injector_unstable'
                    warnings_list.append(
                        f"t={t:.2f}s: ΔP/Pc={dp_ratio:.3f} < "
                        f"{DP_RATIO_UNSTABLE} — yanma kararsızlığı sınırı, "
                        f"simülasyon durduruldu")
                    break
                if dp_ratio < DP_RATIO_WARN and not any(
                        'chugging' in w for w in warnings_list):
                    warnings_list.append(
                        f"t={t:.2f}s: ΔP/Pc={dp_ratio:.2f} < {DP_RATIO_WARN} "
                        f"— chugging riski (SP-8089)")

            F = self._thrust_coefficient(Pc_pa) * Pc_pa * e.At

            # --- kayıt ---
            t += dt
            t_arr.append(t)
            Pc_arr.append(Pc_pa)
            F_arr.append(F)
            mdot_ox_arr.append(mdot_ox)
            mdot_f_arr.append(mdot_f)
            of_arr.append(of_inst)
            D_arr.append(D_port)
            if self.tank is not None:
                tankP_arr.append(self.tank.pressure)
                tankT_arr.append(self.tank.T)

            # --- durum ilerlet ---
            D_port += 2.0 * r_dot * dt
            fuel_burned += mdot_f * dt
            if D_port >= D_max or fuel_burned >= fuel_available:
                event = 'web_exhausted'
                break
            if self.feed_mode == 'blowdown':
                self.tank.step(mdot_ox, dt)
                if self.tank.phase == 'vapor':
                    event = 'oxidizer_depleted'
                    break
            elif t >= e.t_b - 0.5 * dt:
                event = 'burn_time_reached'
                break

        t_arr = np.array(t_arr)
        F_arr = np.array(F_arr)
        Pc_arr = np.array(Pc_arr)
        total_impulse = float(np.trapz(F_arr, t_arr)) if len(t_arr) > 1 else 0.0

        return {
            'time': t_arr,
            'chamber_pressure': Pc_arr,            # Pa
            'thrust': F_arr,                       # N
            'mdot_ox': np.array(mdot_ox_arr),
            'mdot_fuel': np.array(mdot_f_arr),
            'of_ratio': np.array(of_arr),
            'port_diameter': np.array(D_arr),
            'tank_pressure': np.array(tankP_arr),  # Pa (blowdown)
            'tank_temperature': np.array(tankT_arr),
            'feed_mode': self.feed_mode,
            'end_event': event,
            'burn_duration': float(t_arr[-1]) if len(t_arr) else 0.0,
            'total_impulse': total_impulse,
            'average_thrust': (total_impulse / float(t_arr[-1])
                               if len(t_arr) else 0.0),
            'warnings': warnings_list,
        }
