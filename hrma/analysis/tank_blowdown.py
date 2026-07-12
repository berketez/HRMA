"""N₂O kendinden-basınçlı (self-pressurizing) tank blowdown modeli.

Hibrit motorlarda N₂O tankı regülatörsüz çalışır: sıvı çekildikçe tank
basıncı doygunluk basıncını izler, buharlaşma gizli ısısı sıvıyı soğutur ve
basınç yanma boyunca düşer. Bu modül literatürdeki DENGE (equilibrium)
blowdown modelini uygular (Whitmore & Chandler, JPP 27(4) 2011; Fernandez,
MSc 2009): tank içeriği her an tek sıcaklıkta doygun iki-faz kabul edilir.

Durum değişkenleri: (T, m_l, m_v). Her adımda:
  1. Enjektöre giden sıvı kütlesi düşülür (h_l entalpisiyle ayrılır),
  2. Sabit hacim + kalan iç enerji için yeni denge sıcaklığı çözülür:
       V_tank = m_l·v_l(T) + m_v·v_v(T)
       U      = m_l·u_l(T) + m_v·u_v(T)
     (T üzerinde bisection; U(T) sabit m,V'de monoton artan).

Sıvı tükenince faz 'vapor'a geçer ve kalan buhar adyabatik ideal-gaz
genleşmesiyle (γ≈1.27) modellenir — hibrit tasarımında sıvı tükenmesi
fiilen yanma sonudur, buhar fazı yalnızca kuyruk (tail-off) tahminidir.

Özellik kaynağı: CoolProp (NIST REFPROP tabanlı) varsa doğrudan; yoksa
CoolProp'tan üretilmiş gömülü doygunluk tablosu (240-306 K) ile doğrusal
interpolasyon. Tablo değerleri Span-Wagner EOS'tan gelir; 293 K'de
Psat = 50.5 bar (literatürle uyumlu).

Varsayımlar ve sınırlar:
- Tank duvarı adyabatik (duvar ısıl kütlesi yok) → soğuma hafif fazla,
  basınç düşüşü hafif konservatif tahmin edilir.
- Faz dengesi anlık (denge modeli); gerçek tanklarda buharlaşma gecikmesi
  başlangıçta birkaç bar'lık geçici sapma yaratabilir.
- Geçerlilik bandı 240-306 K (kritik nokta 309.52 K'ye yaklaşma modellenmez).
"""

import numpy as np

try:
    from CoolProp.CoolProp import PropsSI
    COOLPROP_AVAILABLE = True
except ImportError:
    COOLPROP_AVAILABLE = False

# N₂O kritik nokta (NIST): modelin üst geçerlilik sınırı olarak kullanılır
N2O_T_CRIT = 309.52   # K
N2O_GAMMA_VAPOR = 1.27  # buhar fazı adyabatik üssü (kuyruk tahmini için)

# CoolProp/Span-Wagner'dan üretilmiş doygunluk tablosu (2026-07-12):
# T[K], Psat[Pa], rho_l, rho_v [kg/m³], h_l, h_v, u_l, u_v [J/kg]
_SAT_TABLE = np.array([
    (240.0, 1187771, 1049.7, 30.72, 98561, 398554, 97429, 359885),
    (243.0, 1310850, 1038.3, 33.89, 104249, 399174, 102987, 360496),
    (246.0, 1443032, 1026.7, 37.33, 109995, 399691, 108590, 361037),
    (249.0, 1584711, 1014.9, 41.06, 115802, 400101, 114241, 361503),
    (252.0, 1736292, 1002.8, 45.09, 121676, 400394, 119944, 361889),
    (255.0, 1898181, 990.4, 49.46, 127621, 400562, 125705, 362187),
    (258.0, 2070797, 977.6, 54.20, 133646, 400596, 131527, 362390),
    (261.0, 2254565, 964.6, 59.34, 139755, 400484, 137418, 362489),
    (264.0, 2449922, 951.1, 64.92, 145959, 400215, 143383, 362475),
    (267.0, 2657315, 937.2, 70.98, 152266, 399773, 149431, 362335),
    (270.0, 2877210, 922.8, 77.58, 158688, 399140, 155570, 362055),
    (273.0, 3110088, 907.8, 84.79, 165238, 398297, 161812, 361618),
    (276.0, 3356453, 892.3, 92.69, 171932, 397217, 168170, 361005),
    (279.0, 3616836, 876.0, 101.37, 178791, 395870, 174662, 360191),
    (282.0, 3891804, 859.0, 110.96, 185839, 394217, 181309, 359143),
    (285.0, 4181966, 840.9, 121.62, 193110, 392207, 188137, 357821),
    (288.0, 4487988, 821.7, 133.56, 200647, 389773, 195186, 356171),
    (291.0, 4810614, 801.0, 147.09, 208511, 386823, 202506, 354117),
    (294.0, 5150691, 778.5, 162.63, 216790, 383225, 210174, 351553),
    (297.0, 5509221, 753.4, 180.85, 225621, 378772, 218308, 348310),
    (300.0, 5887437, 724.7, 202.91, 235239, 373120, 227115, 344104),
    (303.0, 6286974, 690.1, 231.06, 246116, 365590, 237005, 338381),
    (306.0, 6710279, 643.6, 271.21, 259488, 354458, 249062, 329716),
])

_T_MIN, _T_MAX = float(_SAT_TABLE[0, 0]), float(_SAT_TABLE[-1, 0])


class N2OSaturation:
    """N₂O doygunluk özellikleri: CoolProp varsa EOS, yoksa gömülü tablo."""

    def __init__(self, use_coolprop=True):
        self.use_coolprop = bool(use_coolprop and COOLPROP_AVAILABLE)

    def _interp(self, T, col):
        T = float(np.clip(T, _T_MIN, _T_MAX))
        return float(np.interp(T, _SAT_TABLE[:, 0], _SAT_TABLE[:, col]))

    def _cp(self, T, output, quality):
        return PropsSI(output, 'T', float(T), 'Q', quality, 'N2O')

    def psat(self, T):
        return self._cp(T, 'P', 0) if self.use_coolprop else self._interp(T, 1)

    def rho_l(self, T):
        return self._cp(T, 'D', 0) if self.use_coolprop else self._interp(T, 2)

    def rho_v(self, T):
        return self._cp(T, 'D', 1) if self.use_coolprop else self._interp(T, 3)

    def h_l(self, T):
        return self._cp(T, 'H', 0) if self.use_coolprop else self._interp(T, 4)

    def h_v(self, T):
        return self._cp(T, 'H', 1) if self.use_coolprop else self._interp(T, 5)

    def u_l(self, T):
        return self._cp(T, 'U', 0) if self.use_coolprop else self._interp(T, 6)

    def u_v(self, T):
        return self._cp(T, 'U', 1) if self.use_coolprop else self._interp(T, 7)


class N2OTankBlowdown:
    """Denge iki-faz N₂O tank blowdown simülatörü.

    Kullanım:
        tank = N2OTankBlowdown.from_oxidizer_mass(m_ox=16.5, T_init=293.15)
        state = tank.step(mdot_out=1.2, dt=0.05)   # her çağrıda ilerler
        # veya: hist = tank.simulate(mdot_out=1.2, duration=10.0, dt=0.05)
    """

    def __init__(self, tank_volume, initial_temperature=293.15,
                 liquid_fill_fraction=0.85, use_coolprop=True):
        if not (_T_MIN <= initial_temperature <= _T_MAX):
            raise ValueError(
                f"Tank sıcaklığı {initial_temperature:.1f} K model bandı "
                f"[{_T_MIN:.0f}, {_T_MAX:.0f}] K dışında")
        if not (0.05 <= liquid_fill_fraction <= 0.98):
            raise ValueError("liquid_fill_fraction 0.05-0.98 bandında olmalı "
                             "(ullage hacmi şart — sıvıyla tam dolu tank "
                             "termal genleşmede patlama riskidir)")
        self.props = N2OSaturation(use_coolprop=use_coolprop)
        self.V = float(tank_volume)              # m³
        self.T = float(initial_temperature)      # K
        V_l = self.V * liquid_fill_fraction
        V_v = self.V - V_l
        self.m_l = V_l * self.props.rho_l(self.T)   # kg sıvı
        self.m_v = V_v * self.props.rho_v(self.T)   # kg buhar (ullage)
        self.phase = 'two_phase'
        self._history = []

    @classmethod
    def from_oxidizer_mass(cls, oxidizer_mass, initial_temperature=293.15,
                           liquid_fill_fraction=0.85, use_coolprop=True):
        """Gerekli oksitleyici kütlesinden tank hacmini boyutlandırır."""
        props = N2OSaturation(use_coolprop=use_coolprop)
        rho_l = props.rho_l(initial_temperature)
        tank_volume = (oxidizer_mass / rho_l) / liquid_fill_fraction
        return cls(tank_volume, initial_temperature,
                   liquid_fill_fraction, use_coolprop)

    # ---- iç enerji / hacim tutarlılığı ----

    def _split_masses(self, T, m_total):
        """Verilen T'de sabit hacim kısıtıyla sıvı/buhar ayrışımı.

        V = m_l·v_l + m_v·v_v ve m = m_l + m_v →
        m_l = (V − m·v_v) / (v_l − v_v)
        """
        v_l = 1.0 / self.props.rho_l(T)
        v_v = 1.0 / self.props.rho_v(T)
        m_l = (self.V - m_total * v_v) / (v_l - v_v)
        m_v = m_total - m_l
        return m_l, m_v

    def _internal_energy(self, T, m_total):
        m_l, m_v = self._split_masses(T, m_total)
        return m_l * self.props.u_l(T) + m_v * self.props.u_v(T), m_l, m_v

    @property
    def pressure(self):
        """Anlık tank basıncı [Pa]."""
        if self.phase == 'vapor':
            return self._vapor_pressure
        return self.props.psat(self.T)

    @property
    def liquid_mass(self):
        return max(self.m_l, 0.0)

    @property
    def vapor_mass(self):
        return max(self.m_v, 0.0)

    def step(self, mdot_out, dt):
        """Tankı dt kadar ilerletir; enjektöre mdot_out·dt sıvı verir.

        Dönen sözlük: {'time_step': dt, 'P': Pa, 'T': K, 'm_liquid': kg,
        'm_vapor': kg, 'phase': str, 'mdot_delivered': kg/s}
        Sıvı biterse kalan kütle buhar fazından (azaltılmış debiyle) verilir.
        """
        dm = float(mdot_out) * float(dt)

        if self.phase == 'vapor':
            return self._vapor_step(dm, dt, mdot_out)

        if dm >= self.m_l:
            # Bu adımda sıvı tükeniyor → buhar fazına geçiş
            dm = self.m_l
            delivered = dm / dt if dt > 0 else 0.0
            self._begin_vapor_phase()
            self.m_l = 0.0
            return self._pack_state(dt, delivered)

        # 1) Sıvı çek: kütle ve iç enerji düşer (çıkan akış h_l taşır)
        h_l = self.props.h_l(self.T)
        U_target = (self.m_l * self.props.u_l(self.T)
                    + self.m_v * self.props.u_v(self.T)) - dm * h_l
        m_total = self.m_l + self.m_v - dm

        # 2) Yeni denge sıcaklığı: U(T; m,V) = U_target, T üzerinde bisection.
        #    U(T) sabit (m, V)'de monoton arttığı için kök tekildir.
        T_lo, T_hi = _T_MIN, min(self.T + 2.0, _T_MAX)
        f_lo, _, _ = self._internal_energy(T_lo, m_total)
        f_lo -= U_target
        f_hi, _, _ = self._internal_energy(T_hi, m_total)
        f_hi -= U_target
        if f_lo > 0:
            # Hedef enerji bandın altında (aşırı soğuma) → banda kenetle
            self.T = T_lo
        elif f_hi < 0:
            self.T = T_hi
        else:
            for _ in range(60):
                T_mid = 0.5 * (T_lo + T_hi)
                f_mid, _, _ = self._internal_energy(T_mid, m_total)
                f_mid -= U_target
                if abs(f_mid) < 1.0:  # 1 J mutlak tolerans
                    break
                if f_mid > 0:
                    T_hi = T_mid
                else:
                    T_lo = T_mid
            self.T = 0.5 * (T_lo + T_hi)

        _, self.m_l, self.m_v = self._internal_energy(self.T, m_total)
        if self.m_l <= 0.0:
            self._begin_vapor_phase()
            self.m_l = 0.0

        return self._pack_state(dt, mdot_out)

    def _begin_vapor_phase(self):
        """Sıvı tükendi: kalan buharı adyabatik ideal-gaz olarak modelle."""
        self.phase = 'vapor'
        self._vapor_pressure = self.props.psat(self.T)
        self._vapor_T = self.T
        self._vapor_m0 = max(self.m_v, 1e-9)
        self._vapor_P0 = self._vapor_pressure

    def _vapor_step(self, dm, dt, mdot_requested):
        """Buhar (kuyruk) fazı: sabit hacimde kütle çekilen adyabatik gaz.

        Sabit V'de P/P0 = (m/m0)^γ (adyabatik + ideal gaz) yaklaşımı.
        """
        dm = min(dm, 0.8 * self.m_v)  # buharın tamamı tek adımda çekilemez
        self.m_v -= dm
        ratio = max(self.m_v / self._vapor_m0, 1e-6)
        self._vapor_pressure = self._vapor_P0 * ratio ** N2O_GAMMA_VAPOR
        self.T = self._vapor_T * ratio ** (N2O_GAMMA_VAPOR - 1.0)
        delivered = dm / dt if dt > 0 else 0.0
        return self._pack_state(dt, delivered)

    def _pack_state(self, dt, mdot_delivered):
        state = {
            'time_step': dt,
            'P': self.pressure,
            'T': self.T,
            'm_liquid': self.liquid_mass,
            'm_vapor': self.vapor_mass,
            'phase': self.phase,
            'mdot_delivered': mdot_delivered,
        }
        self._history.append(state)
        return state

    def simulate(self, mdot_out, duration, dt=0.05):
        """Sabit debiyle blowdown; zaman serilerini döndürür."""
        n = max(int(round(duration / dt)), 1)
        t, P, T, ml, mv = [], [], [], [], []
        for i in range(n):
            s = self.step(mdot_out, dt)
            t.append((i + 1) * dt)
            P.append(s['P'])
            T.append(s['T'])
            ml.append(s['m_liquid'])
            mv.append(s['m_vapor'])
        return {
            'time': np.array(t),
            'pressure': np.array(P),
            'temperature': np.array(T),
            'liquid_mass': np.array(ml),
            'vapor_mass': np.array(mv),
            'phase': self.phase,
        }
