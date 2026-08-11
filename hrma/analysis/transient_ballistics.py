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
t_max aşıldı / boğaz erozyonla ε ≤ 1.2'ye büyüdü (erozyon açıkken).

Boğaz erozyonu (Dalga 3, opsiyonel — varsayılan KAPALI): ThroatErosionModel
ampirik ṙ = a_ref·(Pc/70 bar)^0.8 modeliyle her adımda d_t büyütülür; Pc ve
F eğrileri buna göre düşer. Kapalıyken çözüm eski davranışla bit-özdeştir.
"""

import numpy as np

from hrma.analysis.regression_analysis import RegressionAnalyzer
from hrma.analysis.tank_blowdown import N2OTankBlowdown
from hrma.data.materials_db import get_material
# Ayrılma eşiği TEK tanım noktasından okunur (sayı kopyalanmaz); aynı sabiti
# hibrit motor da bu addan alır.
from hrma.flow.separation import SUMMERFIELD_FACTOR_DEFAULT

# SP-8089 enjektör kararlılık eşikleri (ΔP/P_c)
DP_RATIO_WARN = 0.15      # bunun altında chugging riski uyarısı
DP_RATIO_UNSTABLE = 0.05  # bunun altında yarı-kararlı model geçersiz → dur


# ---------------------------------------------------------------------------
# Boğaz erozyonu (Dalga 3, 2026-07-14) — ampirik, model-değiştirilebilir API
# ---------------------------------------------------------------------------
# Model:  ṙ_ero = a_ref · (Pc / Pc_ref)^0.8   [mm/s],  Pc_ref = 70 bar
#
# Fiziksel dayanak: grafit/C-C boğaz gerilemesi tipik motor koşullarında
# DİFÜZYON-KONTROLLÜ oksidasyon rejimindedir (H2O/CO2 türlerinin cidara
# taşınımı sınırlar); gerileme hızı konvektif ısı/kütle taşınım katsayısıyla
# ölçeklenir ve Bartz korelasyonunda h_g ∝ Pc^0.8'dir. Kaynaklar:
#   - Bartz, D.R., "A Simple Equation for Rapid Estimation of Rocket Nozzle
#     Convective Heat Transfer Coefficients", Jet Propulsion 27(1), 1957
#     (Pc^0.8 ölçeklemesinin kaynağı).
#   - Thakre, P., Yang, V., "Chemical Erosion of Graphite and Refractory
#     Metal Nozzles in Solid-Propellant Rocket Motors", J. Propulsion and
#     Power 24(4), 2008 — grafit gerilemesi ~0.1 mm/s sınıfı @ ~7 MPa
#     AP/HTPB; erozyon difüzyon-sınırlı → basınçla yaklaşık lineer-altı artar.
#   - Geisler, R.L., AIAA katı motor nozul malzemesi derlemeleri — grafit
#     bandı ~0.05–0.25 mm/s (motor sınıfına göre).
#
# a_ref bantları @ 70 bar sınıfı APPROXIMATE'tir: gerçek hız itki gazı
# oksitleyici kesrine (H2O+CO2+OH), alev sıcaklığına ve malzeme yoğunluğuna
# güçlü bağlıdır; ±%50 saçılım normaldir. Varsayılan = bandın KONSERVATİF
# (üst) ucu. Kesin tasarım için test verisi şarttır.
THROAT_EROSION_MATERIALS = {
    'graphite': {
        'db_key': 'graphite',            # materials_db kaydı (görünen ad için)
        'display': 'Graphite (isostatic, nozzle insert grade)',
        'a_ref_band_mm_s': (0.05, 0.15),
        'a_ref_default_mm_s': 0.15,      # konservatif üst uç
        'recommended': True,
        'source': ('Thakre & Yang 2008 (J. Prop. Power 24-4): ~0.1 mm/s '
                   'class at ~7 MPa AP/HTPB; Geisler AIAA graphite band '
                   '0.05-0.25 mm/s. Band approximate.'),
    },
    'carbon_carbon': {
        'db_key': None,                  # materials_db'de kayıt yok
        'display': 'Carbon-carbon composite (C-C)',
        'a_ref_band_mm_s': (0.02, 0.10),
        'a_ref_default_mm_s': 0.10,      # konservatif üst uç
        'recommended': True,
        'source': ('Thakre & Yang 2008: dense C-C erodes measurably less '
                   'than bulk polycrystalline graphite (higher density, '
                   'fewer open pores). Band approximate.'),
    },
    'steel': {
        'db_key': 'steel',
        'display': 'Steel (uncooled)',
        'a_ref_band_mm_s': None,
        'a_ref_default_mm_s': None,
        'recommended': False,
        'warning': ('Uncooled steel throat is NOT RECOMMENDED: wall softens '
                    'and melts far below flame temperature (see materials_db '
                    'max_service_temp); the empirical Pc^0.8 oxidation model '
                    'is not valid for melting metals. Use graphite or C-C, '
                    'or supply a test-derived a_ref explicitly.'),
        'source': 'Engineering judgement; no validated coefficient.',
    },
    'copper': {
        'db_key': 'copper',
        'display': 'Copper (uncooled heat sink)',
        'a_ref_band_mm_s': None,
        'a_ref_default_mm_s': None,
        'recommended': False,
        'warning': ('Uncooled copper throat is NOT RECOMMENDED for sustained '
                    'burns: copper is a short-duration heat sink only '
                    '(melting point 1358 K, materials_db); the empirical '
                    'Pc^0.8 oxidation model is not valid for melting metals. '
                    'Use graphite or C-C, or supply a test-derived a_ref '
                    'explicitly.'),
        'source': 'Engineering judgement; no validated coefficient.',
    },
}

# Yaygın ad/alias'lar → erozyon tablosu anahtarı
_EROSION_ALIASES = {
    'c-c': 'carbon_carbon', 'c_c': 'carbon_carbon', 'cc': 'carbon_carbon',
    'carbon-carbon': 'carbon_carbon', 'carboncarbon': 'carbon_carbon',
    'steel_4130': 'steel', 'ss_304': 'steel', 'ss_316': 'steel',
    'stainless': 'steel', 'stainless_304': 'steel', 'stainless_316': 'steel',
    'cucrzr': 'copper', 'cu_cr_zr': 'copper', 'cu': 'copper',
}


class ThroatErosionModel:
    """Ampirik boğaz erozyon modeli:  ṙ = a_ref·(Pc/Pc_ref)^exponent.

    Model-değiştirilebilir API: TransientBallistics kuplajı yalnız
    ``rate_m_s(Pc_pa)`` çağırır — aynı imzayı sağlayan HERHANGİ bir nesne
    (ör. Thakre-Yang tarzı kinetik model, test-verisi interpolasyonu)
    ``erosion_model=`` argümanıyla takılabilir.

    Varsayılan katsayı ve üs için kaynaklar modül başındaki blokta
    (Bartz 1957; Thakre & Yang 2008; Geisler). Bantlar approximate'tir.
    """

    def __init__(self, a_ref_mm_s, pc_ref_bar=70.0, exponent=0.8,
                 material='custom', material_display=None,
                 a_ref_band_mm_s=None,
                 source='user-supplied coefficient', warnings=None):
        a = float(a_ref_mm_s)
        if not np.isfinite(a) or a <= 0.0:
            raise ValueError("a_ref_mm_s must be a positive finite number")
        pc_ref = float(pc_ref_bar)
        if not np.isfinite(pc_ref) or pc_ref <= 0.0:
            raise ValueError("pc_ref_bar must be a positive finite number")
        self.a_ref_mm_s = a
        self.pc_ref_bar = pc_ref
        self.exponent = float(exponent)
        self.material = str(material)
        self.material_display = material_display or str(material)
        self.a_ref_band_mm_s = (tuple(a_ref_band_mm_s)
                                if a_ref_band_mm_s else None)
        self.source = source
        self.warnings = list(warnings or [])

    @classmethod
    def for_material(cls, material, a_ref_mm_s=None):
        """Malzeme adından model kurar (tablo + materials_db görünen adı).

        Önerilmeyen malzemelerde (çelik/bakır soğutmasız) a_ref override'ı
        verilmemişse ValueError yükseltir; override verilirse model kurulur
        ama 'not recommended' uyarısı taşınır.
        """
        key = str(material).strip().lower().replace(' ', '_')
        key = _EROSION_ALIASES.get(key, key)
        if key not in THROAT_EROSION_MATERIALS:
            raise ValueError(
                f"No throat erosion data for material '{material}'. "
                f"Available: {sorted(THROAT_EROSION_MATERIALS)} "
                f"(or pass a_ref_mm_s for a custom material)")
        rec = THROAT_EROSION_MATERIALS[key]

        display = rec['display']
        if rec.get('db_key'):
            try:
                # Merkezi malzeme DB'sindeki görünen adı kullan (tek kaynak).
                display = get_material(rec['db_key'])['name']
            except KeyError:
                pass

        warns = []
        if not rec['recommended']:
            warns.append(rec['warning'])
            if a_ref_mm_s is None:
                raise ValueError(
                    f"Throat material '{key}': {rec['warning']}")
        a = a_ref_mm_s if a_ref_mm_s is not None else rec['a_ref_default_mm_s']
        return cls(a, material=key, material_display=display,
                   a_ref_band_mm_s=rec.get('a_ref_band_mm_s'),
                   source=rec['source'], warnings=warns)

    def rate_mm_s(self, pc_bar):
        """Erozyon hızı [mm/s] (yarıçapta gerileme), Pc [bar]."""
        pc = float(pc_bar)
        if pc <= 0.0:
            return 0.0
        return self.a_ref_mm_s * (pc / self.pc_ref_bar) ** self.exponent

    def rate_m_s(self, pc_pa):
        """Erozyon hızı [m/s] (yarıçapta gerileme), Pc [Pa]."""
        return self.rate_mm_s(float(pc_pa) / 1e5) / 1000.0

    def describe(self):
        """JSON-uyumlu model özeti (rapor/endpoint için)."""
        return {
            'model': (f"r_dot = a_ref*(Pc/{self.pc_ref_bar:g} bar)"
                      f"^{self.exponent:g} (empirical)"),
            'a_ref_mm_s': self.a_ref_mm_s,
            'pc_ref_bar': self.pc_ref_bar,
            'exponent': self.exponent,
            'material': self.material,
            'material_display': self.material_display,
            'a_ref_band_mm_s': (list(self.a_ref_band_mm_s)
                                if self.a_ref_band_mm_s else None),
            'source': self.source,
            'warnings': list(self.warnings),
        }


class TransientBallistics:
    """Boyutlandırılmış bir HybridRocketEngine'i zamanda yürütür."""

    def __init__(self, engine, feed_mode='regulated',
                 tank_temperature=293.15, liquid_fill_fraction=0.85,
                 n_steps=400, t_max_factor=1.6,
                 erosion_enabled=False, throat_material='graphite',
                 erosion_model=None):
        """
        Args:
            engine: calculate() çağrılmış HybridRocketEngine örneği
            feed_mode: 'regulated' | 'blowdown'
            tank_temperature: blowdown başlangıç tank sıcaklığı [K]
            liquid_fill_fraction: tank sıvı doluluk oranı (ullage payı)
            n_steps: nominal yanma süresi için adım sayısı
            t_max_factor: t_max = factor · t_b (blowdown uzayabilir)
            erosion_enabled: True → boğaz erozyonu kuplajı (her adımda d_t
                büyür, Pc/F eğrisi düşer). Varsayılan KAPALI — geriye dönük
                uyum: kapalıyken çözüm eski davranışla bit-özdeştir.
            throat_material: erozyon malzemesi ('graphite' | 'carbon_carbon';
                çelik/bakır soğutmasız → not-recommended, a_ref şart)
            erosion_model: opsiyonel özel model — rate_m_s(Pc_pa) sağlayan
                herhangi bir nesne (verilirse throat_material yok sayılır ve
                erozyon etkinleşir; model-değiştirilebilir API)
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

        # Boğaz erozyonu (Dalga 3): varsayılan KAPALI — geriye dönük uyum.
        # erosion_model verilirse malzeme tablosuna bakılmaz (rate_m_s(Pc_pa)
        # sağlayan her nesne kabul edilir — model-değiştirilebilir API).
        self.erosion = None
        if erosion_model is not None:
            self.erosion = erosion_model
        elif erosion_enabled:
            self.erosion = ThroatErosionModel.for_material(throat_material)

        # Kaç adımda C_F ayrılma tabanına oturdu (kalem 3). Sıfırdan büyükse
        # eğrinin bir bölümü ekli-akış modelinin GEÇERLİLİK ARALIĞI DIŞINDA
        # geçmiştir ve bu sonuçta beyan edilir.
        self._separation_limited_steps = 0
        # Ekli-akış ifadesi negatife düşüp sıfıra kırpılan adım sayısı.
        self._negative_cf_steps = 0

    # ---------------- nozul yardımcıları ----------------

    @staticmethod
    def _exit_pressure_ratio(gamma, eps):
        """Sabit ε için süpersonik dal P_e/P_c oranı (izentropik)."""
        from scipy.optimize import brentq

        def area_ratio(M):
            return (1.0 / M) * ((2.0 / (gamma + 1.0))
                                * (1.0 + (gamma - 1.0) / 2.0 * M * M)) \
                   ** ((gamma + 1.0) / (2.0 * (gamma - 1.0))) - eps

        # Alt sınır 1 DEĞİL 1.0001: alan oranı M=1'de dönüm yapar ve tipik
        # ε > 1 için denklemin İKİ kökü vardır (biri subsonik, biri
        # süpersonik). 1'in kesin üstünde başlayan aralık subsonik dalı
        # dışarıda bırakır; kalan aralıkta fonksiyon kesin monoton artan
        # olduğu için kök tektir. İkisi de Lean ile ispatlandı:
        # HRMA.areaRatio_strictMonoOn, HRMA.bracket_excludes_subsonic
        # (bkz. docs/BICIMSEL_ISPATLAR.md).
        Me = brentq(area_ratio, 1.0001, 50.0)
        return (1.0 + (gamma - 1.0) / 2.0 * Me * Me) ** (-gamma / (gamma - 1.0))

    @staticmethod
    def _momentum_cf(gamma, pe_ratio):
        """C_F'in momentum kısmı (Sutton Eq. 3-30, basınç-itki terimi hariç)."""
        return np.sqrt(2.0 * gamma ** 2 / (gamma - 1.0)
                       * (2.0 / (gamma + 1.0)) ** ((gamma + 1.0) / (gamma - 1.0))
                       * (1.0 - pe_ratio ** ((gamma - 1.0) / gamma)))

    @staticmethod
    def _mach_from_pressure_ratio(p_over_p0, gamma):
        """İzentropik p/p0 → Mach (kapalı form). Aralık dışıysa None."""
        if not (p_over_p0 > 0.0) or p_over_p0 > 1.0:
            return None
        return float(np.sqrt(2.0 / (gamma - 1.0)
                             * ((1.0 / p_over_p0) ** ((gamma - 1.0) / gamma)
                                - 1.0)))

    @staticmethod
    def _area_ratio_from_mach(M, gamma):
        """Süpersonik dal alan oranı A/A* (kapalı form)."""
        if M is None or not (M > 0.0):
            return None
        return float((1.0 / M)
                     * ((2.0 / (gamma + 1.0))
                        * (1.0 + 0.5 * (gamma - 1.0) * M * M))
                     ** ((gamma + 1.0) / (2.0 * (gamma - 1.0))))

    def _separation_limited_cf(self, Pc_pa, gamma, Pa_pa):
        """Ayrılma istasyonunda kesilmiş lülenin C_F'i — fiziksel ALT SINIR.

        Aşırı genişlemiş lülede sınır tabaka P_e < k·P_a olduğunda ayrılır
        (Summerfield, k = 0,40; sabit hrma/flow/separation.py'de tanımlı).
        Ayrılma istasyonundan sonrası itkiye katkı vermediği için gerçek C_F,
        aynı lülenin O İSTASYONDA kesilmiş hâlinin C_F'inden aşağı inemez.
        Çözülemezse None döner ve taban UYGULANMAZ (sayı uydurulmaz).
        """
        if not (Pa_pa > 0.0 and Pc_pa > 0.0):
            return None
        M_sep = self._mach_from_pressure_ratio(
            SUMMERFIELD_FACTOR_DEFAULT * Pa_pa / Pc_pa, gamma)
        # Ayrılma istasyonu ancak SÜPERSONİK dalda anlamlıdır. M_sep <= 1
        # ise ayrılma noktası boğazın gerisine düşer, yani lüle o basınçta
        # zaten süpersonik akmıyordur — taban uydurulmaz, None döner.
        if M_sep is None or M_sep <= 1.0:
            return None
        eps_sep = self._area_ratio_from_mach(M_sep, gamma)
        if eps_sep is None or not np.isfinite(eps_sep) or eps_sep <= 1.0:
            return None
        try:
            pe_sep = self._exit_pressure_ratio(gamma, eps_sep)
            cfm_sep = self._momentum_cf(gamma, pe_sep)
        except (ValueError, FloatingPointError):
            return None
        cf = (self._lambda * cfm_sep + eps_sep * pe_sep
              - eps_sep * Pa_pa / Pc_pa)
        return float(cf) if np.isfinite(cf) else None

    def _thrust_coefficient(self, Pc_pa, eps=None, pe_ratio=None,
                            cf_momentum=None):
        """C_F(P_c): sabit ε'da yalnız basınç-itki terimi değişir.

        Erozyon açıkken boğaz büyür → ε = A_e/A_t küçülür; çağıran güncel
        (eps, pe_ratio, cf_momentum) üçlüsünü geçirir. None → tasarım
        değerleri (eski davranış; erozyon kapalıyken bit-özdeş yol).

        v2.6.27 B1 (kalem 3) — AYRILMA TABANI. Eski ifadenin hiçbir alt
        sınırı yoktu ve Pc düştükçe ``− ε·P_a/P_c`` terimi sınırsız büyüyordu.
        ÖLÇÜLDÜ (ε = 25, P_a = 1 bar):
            Pc = 20 bar -> C_F = +0,5304
            Pc = 10 bar -> C_F = −0,7196
            Pc =  5 bar -> C_F = −3,2196
            Pc =  1 bar -> C_F = −23,2196
        Yani model, basınç düştükçe lülenin motoru GERİYE ittiğini söylüyordu.
        Gerçekte o rejimde akış çoktan ayrılmıştır ve C_F, ayrılma
        istasyonundaki değerin altına inemez. Taban yalnız ayrılma
        öngörüldüğünde devreye girer; ekli akışta sonuç bit-özdeştir.
        """
        if eps is None:
            eps = float(self.e.epsilon)
            pe_ratio = self._pe_ratio
            cf_momentum = self._cf_momentum
        Pa_pa = float(self.e.P_a) * 1e5
        if not (Pc_pa and np.isfinite(Pc_pa) and Pc_pa > 0.0):
            # Basınç sıfır/negatif/NaN ise C_F tanımsızdır. Eskiden burada
            # sessizce ±inf ya da NaN üretilip itki dizisine akıyordu.
            return 0.0
        cf_ekli = (self._lambda * cf_momentum
                   + eps * pe_ratio - eps * Pa_pa / Pc_pa)
        Pe_pa = pe_ratio * Pc_pa
        if Pa_pa > 0.0 and Pe_pa < SUMMERFIELD_FACTOR_DEFAULT * Pa_pa:
            cf_sep = self._separation_limited_cf(
                Pc_pa, float(self.e.gamma), Pa_pa)
            if cf_sep is not None and cf_sep > cf_ekli:
                self._separation_limited_steps += 1
                return float(max(cf_sep, 0.0))
        if not np.isfinite(cf_ekli):
            return 0.0
        if cf_ekli < 0.0:
            # SON DURAK. Bir roket lülesi aracı GERİYE itemez: negatif C_F
            # her zaman ekli-akış modelinin geçerlilik aralığı dışında
            # uygulanmasının bir eseridir. Sıfıra kırpmak sessiz kalmak
            # DEĞİLDİR: adım sayılır ve sonuçta beyan edilir. Pratikte bu dal
            # yalnız P_c ortam basıncının altına düştüğünde görülür ve solve()
            # o durumda zaten 'chamber_below_ambient' olayıyla durur.
            self._negative_cf_steps += 1
            return 0.0
        return float(cf_ekli)

    # ---------------- ana çözüm ----------------

    def solve(self):
        e = self.e
        dt = self.dt
        D_port = float(e.D_port_initial)
        D_max = float(getattr(e, 'D_ch', D_port * 10)) * 0.8  # web sınırı
        fuel_available = float(getattr(e, 'm_fuel', None) or
                               e.rho_f * np.pi / 4.0
                               * (D_max ** 2 - D_port ** 2) * e.L_grain)

        # Boğaz durumu (Dalga 3): erozyon kapalıyken At tasarım değerinde
        # SABİT kalır (eski davranışla bit-özdeş aritmetik); açıkken her
        # adımda büyür → Pc = ṁ·c*/(Cd·At) düşer, ε = A_e/A_t küçülür.
        At = float(e.At)
        d_throat = 2.0 * np.sqrt(At / np.pi)
        d_throat0 = d_throat
        A_exit = float(e.epsilon) * At   # nozul çıkışı rijit (sabit alan)
        eps_cur = None    # None → tasarım ε / Pe-oranı / momentum-CF üçlüsü
        pe_cur = None
        cfm_cur = None

        t_arr, Pc_arr, F_arr = [], [], []
        mdot_ox_arr, mdot_f_arr, of_arr, D_arr = [], [], [], []
        dthr_arr = []
        tankP_arr, tankT_arr = [], []
        warnings_list = []
        if self.erosion is not None:
            warnings_list.extend(getattr(self.erosion, 'warnings', []))
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
                          / (self._cd_nozzle * At))
                if abs(Pc_new - Pc_pa) < 100.0:  # 1 mbar yakınsama
                    Pc_pa = Pc_new
                    break
                Pc_pa = Pc_new

            if mdot_ox <= 0.0:
                event = 'feed_pressure_lost'
                break

            # Hazne basıncı ortamın altına düştüyse lüle artık dışarı akış
            # süremez: yarı-kararlı süpersonik lüle modeli GEÇERSİZDİR.
            # Eskiden burada durak yoktu ve model, basınç düştükçe giderek
            # daha negatif bir C_F (ölçüldü: Pc=1 bar'da −23,2) üretmeye
            # devam ediyordu. Sayı uydurmak yerine çözüm durur.
            Pa_pa_stop = float(self.e.P_a) * 1e5
            if Pa_pa_stop > 0.0 and Pc_pa <= Pa_pa_stop:
                event = 'chamber_below_ambient'
                warnings_list.append(
                    f"t={t:.2f}s: Pc={Pc_pa/1e5:.2f} bar fell to or below the "
                    f"ambient pressure ({Pa_pa_stop/1e5:.2f} bar); the nozzle "
                    f"can no longer sustain supersonic outflow, simulation "
                    f"stopped")
                break

            # SP-8089 enjektör kararlılığı (yalnız blowdown'da anlamlı)
            if self.feed_mode == 'blowdown':
                dp_ratio = (self.tank.pressure - Pc_pa) / Pc_pa
                if dp_ratio < DP_RATIO_UNSTABLE:
                    event = 'injector_unstable'
                    # EN üretilir; TR çevirisi i18n_charts.js MSG_PATTERNS'te
                    warnings_list.append(
                        f"t={t:.2f}s: ΔP/Pc={dp_ratio:.3f} < "
                        f"{DP_RATIO_UNSTABLE} — combustion instability "
                        f"limit, simulation stopped")
                    break
                if dp_ratio < DP_RATIO_WARN and not any(
                        'chugging' in w for w in warnings_list):
                    warnings_list.append(
                        f"t={t:.2f}s: ΔP/Pc={dp_ratio:.2f} < {DP_RATIO_WARN} "
                        f"— chugging risk (SP-8089)")

            F = self._thrust_coefficient(Pc_pa, eps_cur, pe_cur, cfm_cur) \
                * Pc_pa * At

            # --- kayıt ---
            t += dt
            t_arr.append(t)
            Pc_arr.append(Pc_pa)
            F_arr.append(F)
            mdot_ox_arr.append(mdot_ox)
            mdot_f_arr.append(mdot_f)
            of_arr.append(of_inst)
            D_arr.append(D_port)
            dthr_arr.append(d_throat)
            if self.tank is not None:
                tankP_arr.append(self.tank.pressure)
                tankT_arr.append(self.tank.T)

            # --- durum ilerlet ---
            D_port += 2.0 * r_dot * dt
            fuel_burned += mdot_f * dt

            # Boğaz erozyonu: d_t büyür → At büyür → sonraki adımda Pc düşer.
            # Sabit çıkış alanlı (rijit) nozulda ε = A_e/A_t küçülür; Pe/Pc
            # ve momentum-CF izentropik bağıntılardan yeniden hesaplanır.
            if self.erosion is not None:
                r_ero = float(self.erosion.rate_m_s(Pc_pa))  # m/s (yarıçap)
                if r_ero > 0.0:
                    d_throat += 2.0 * r_ero * dt
                    At = np.pi * (d_throat / 2.0) ** 2
                    eps_new = A_exit / At
                    if eps_new <= 1.2:
                        event = 'throat_erosion_limit'
                        warnings_list.append(
                            f"t={t:.2f}s: throat eroded to expansion ratio "
                            f"{eps_new:.2f} <= 1.2 — nozzle no longer "
                            f"effective, simulation stopped")
                        break
                    eps_cur = eps_new
                    pe_cur = self._exit_pressure_ratio(float(e.gamma), eps_cur)
                    cfm_cur = self._momentum_cf(float(e.gamma), pe_cur)

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

        # Ayrılma tabanı devreye girdiyse SESSİZ KALINMAZ: eğrinin o bölümü
        # ekli-akış modelinin geçerlilik aralığı dışında geçmiştir.
        if self._separation_limited_steps:
            warnings_list.append(
                f"{self._separation_limited_steps} of {len(t_arr)} steps ran "
                f"over-expanded past the Summerfield separation limit "
                f"(P_e < {SUMMERFIELD_FACTOR_DEFAULT}*P_a); the attached-flow "
                f"thrust coefficient is invalid there and C_F was floored at "
                f"its separation-station value")

        return {
            'time': t_arr,
            'chamber_pressure': Pc_arr,            # Pa
            'thrust': F_arr,                       # N
            'mdot_ox': np.array(mdot_ox_arr),
            'mdot_fuel': np.array(mdot_f_arr),
            'of_ratio': np.array(of_arr),
            'port_diameter': np.array(D_arr),
            'throat_diameter': np.array(dthr_arr),  # m (erozyon kapalı→sabit)
            'erosion': {
                'enabled': self.erosion is not None,
                'initial_throat_diameter_mm': d_throat0 * 1000.0,
                # Özet, KAYDEDİLEN dizinin son elemanından okunur — döngü
                # kayıt→ilerletme sıralı olduğundan d_throat değişkeni diziden
                # bir adım ilerideydi (2026-07-15 Dalga 3 test ajanı bulgusu)
                'final_throat_diameter_mm': float(dthr_arr[-1]) * 1000.0,
                # Gerileme yarıçapta ölçülür: (d_son - d_ilk)/2
                'total_recession_mm': (float(dthr_arr[-1]) - d_throat0) / 2.0 * 1000.0,
                'model': (self.erosion.describe()
                          if hasattr(self.erosion, 'describe') else None),
            },
            'tank_pressure': np.array(tankP_arr),  # Pa (blowdown)
            'tank_temperature': np.array(tankT_arr),
            'feed_mode': self.feed_mode,
            'flow_separation': {
                'criterion': 'summerfield',
                'factor': float(SUMMERFIELD_FACTOR_DEFAULT),
                'steps_floored': int(self._separation_limited_steps),
                'steps_zero_clamped': int(self._negative_cf_steps),
                'steps_total': int(len(t_arr)),
                'basis': (
                    'the attached-flow thrust coefficient is only valid while '
                    'the nozzle flows full. Where P_e falls below '
                    'factor*P_a the flow separates and C_F is floored at the '
                    'value of the same nozzle truncated at the separation '
                    'station, because the divergent section downstream of it '
                    'no longer produces thrust. steps_floored = 0 means the '
                    'whole curve stayed inside the attached-flow range and '
                    'the result is bit-identical to the unfloored model. '
                    'steps_zero_clamped counts the steps where even the '
                    'separation floor was unavailable and a negative '
                    'attached-flow C_F was clamped to zero — a rocket nozzle '
                    'cannot push the vehicle backwards.'),
            },
            'end_event': event,
            'burn_duration': float(t_arr[-1]) if len(t_arr) else 0.0,
            'total_impulse': total_impulse,
            'average_thrust': (total_impulse / float(t_arr[-1])
                               if len(t_arr) else 0.0),
            'warnings': warnings_list,
        }
