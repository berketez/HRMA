"""
Gerçek Zamanlı Validasyon ve Uyarı Sistemi
Rocket motor tasarım parametrelerinin doğruluğunu kontrol eder
"""

import math
import numpy as np
from typing import List, Dict, Optional, Tuple
import warnings

# ÖH D29 / P15B2-01: deger katmani kapilarinin TEK KAYNAGI.
from hrma.utils.input_guard import finite_positive

# ---------------------------------------------------------------------------
# Chug ΔP/Pc eşiği: TEK SAYISAL TANIM hrma/analysis/acoustic_modes.py'dedir.
#
# ÖH Z5S / P10-A (P10B2-14) — ÖLÇÜLDÜ: bu dosya eşiğin BEŞİNCİ bağımsız
# kopyasını taşıyordu (``'pressure_drop_ratio': (0.10, 0.35)``) ve alt sınırı
# tek kaynağın 0,15'iyle ÇELİŞİYORDU. Sonuç, iki ayrı doğruluk tanımıydı:
# enjektör modülü 0,15-0,20'ye göre boyutlandırıyor, doğrulayıcı 0,10'a göre
# hüküm veriyordu. Alt sınır artık ithal edilir; YENİ EŞİK İCAT EDİLMEZ.
#
# Üst sınır (0,35) chug ölçütü DEĞİLDİR: chug alt sınırı kararlılık
# gerekçesiyle, üst sınır besleme basıncı/pompa işi (kütle bütçesi)
# gerekçesiyle konur. acoustic_modes böyle bir tavan tanımlamaz, o yüzden
# buradaki sayı KORUNUR ve gerekçesi adıyla beyan edilir — bir tavan
# uydurmak da, chug alt sınırını tavan yerine kullanmak da yanlış olurdu.
# ---------------------------------------------------------------------------
from hrma.analysis.acoustic_modes import (
    CHUG_DP_RATIO_MINIMUM,
    CHUG_DP_RATIO_RECOMMENDED,
    CHUG_THRESHOLD_CITATION,
)

#: ΔP/Pc üst sınırı — kararlılık değil, besleme sistemi maliyeti ölçütü.
#: (Sutton & Biblarz 9. baskı Böl. 8.5: tipik enjektör ΔP bandının üst ucu;
#: bunun ötesinde tank/pompa işi artar, kararlılık kazancı yoktur.) Chug
#: eşiğiyle AYNI ŞEY DEĞİLDİR, bu yüzden ayrı adı vardır. v3.0.1 (21 Eki):
#: eski "/ NASA SP-8089" atfı kaldırıldı — bant o belgede sayfa sayfa
#: doğrulanmadı (gerekçe: acoustic_modes.CHUG_THRESHOLD_SOURCE).
INJECTOR_DP_PC_CEILING = 0.35

#: ``comprehensive_validation`` raporunda ölçülemeyen eksenin künyesi.
DP_RATIO_AXIS = 'pressure_drop_ratio'

#: v3.0.1 — son port zarfı ⟷ kamara iç çapı karşılaştırmasının kayan nokta
#: toleransı (bağıl). Fizik eşiği DEĞİLDİR: motor zarfı aynı formülle
#: (k(N)·D_son + 2·t_artık) kurduğu için eşitlik tasarım gereğidir; tolerans
#: yalnız yeniden hesaplamadaki yuvarlama farkını yutar.
PORT_ENVELOPE_COMPARE_REL_TOL = 1e-9


def _finite_positive(value) -> Optional[float]:
    """Sonlu ve pozitif bir sayıysa float, değilse ``None``.

    ``bool`` sayı SAYILMAZ (``True`` 1,0'a çökerdi). "Verilmedi" ile "0"
    ayrımı korunur: ikisi de ``None`` döner çünkü sıfır kamara basıncına
    bölme zaten hüküm üretemez.

    ÖH D29 / app-api-dogrulama a1 · defter P15B2-01 — MERKEZE BAĞLANDI:
    kural ``hrma.utils.input_guard.finite_positive``tadır. Yerel kopya
    ``numpy.bool_``u eleyemiyordu (merkez eler).
    """
    return finite_positive(value)


# ---------------------------------------------------------------------------
# V301/PANEL (C-5, H-PANEL DEVİR 5) — ΔP/Pc TAVANI AŞIMININ CÜMLESİ KÖKTE,
# BESLEME TİPİNE GÖRE. Tavan (``injector_limits['pressure_drop_ratio']``,
# Sutton & Biblarz Böl. 8.5) besleme basıncı maliyetinin ölçütüdür; bedelin
# NE olduğu besleme tipine bağlıdır. ÖLÇÜLDÜ (H-PANEL, örnek hibrit): bu
# kural her motora "pompa işi artar" diyordu, uç hibritte sonradan yeniden
# adlandırıyordu. Artık cümle burada kurulur:
#   pump_fed          → pompa işi ve besleme basıncı (warning);
#   pressure_fed      → tank basıncı / tank cidarı kütlesi, pompa yok (warning);
#   self_pressurised  → kendinden basınçlı N2O: ΔP = P_sat(T_tank) − Pc bir
#                       seçim değildir, bilgi düzeyi (info);
#   bilinmiyor        → bedel adlandırılmaz (pompa ya da tank iddiası yok).
DP_PC_HIGH_CODE_BY_FEED = {
    'pump_fed': ('warn.validation.dp_pc_high', 'warning'),
    'pressure_fed': ('warn.validation.dp_pc_high_pressure_fed', 'warning'),
    'self_pressurised': ('warn.validation.dp_pc_self_pressurised', 'info'),
}
DP_PC_HIGH_FEED_NOT_STATED = ('warn.validation.dp_pc_high_feed_not_stated',
                              'warning')


def _w(code: str, severity: str = "warning", **params) -> Dict:
    """i18n uyarısı: dile bağlı sabit metin YERİNE yapısal kayıt.

    Dönen sözlük ``{"code", "params", "severity"}``. Dil tamamen frontend'e
    taşınır; frontend ``TF(code, params)`` ile yerelleştirilmiş metni kurar.
    ``severity`` ∈ {"critical", "warning", "info"} — kritik/uyarı ayrımı
    artık metin içeriğinden DEĞİL bu alandan yapılır (dil sızıntısı yok).
    """
    return {"code": code, "params": params, "severity": severity}


class ValidationSystem:
    """Gerçek zamanlı validasyon ve uyarı sistemi"""
    
    def __init__(self):
        # Sutton & Biblarz, NASA SP-8089, ve AIAA standartları
        self.performance_limits = {
            'specific_impulse': {
                'n2o_htpb': (180, 250),    # s
                'n2o_paraffin': (190, 260),
                'lox_htpb': (220, 280),
            },
            'chamber_pressure': (5, 100),   # bar
            # ÖH D33-3 · OH-D33-11 (Berke kararı, 16 Eylül 2026) — BANT
            # DÜZELTİLDİ, GEVŞETİLMEDİ. ÖLÇÜLDÜ (kılavuz ekran turu,
            # docs/scofield/raw/OH/KILAVUZ/ekran/kayit.json): sayfanın
            # varsayılan O/F'si 7,5 (advanced.html:1728; kaynağı
            # ``optimum_of_ratio`` referans tablosu, aynı sayı) eski üst uç
            # 6,0'ın DIŞINDA kalıyordu, yani programı açıp hiçbir şeyi
            # değiştirmeden hesap yapan HER kullanıcı "kullanılabilir
            # aralığın dışında" uyarısı alıyordu. Karşı ölçüm: O/F 2,5'te bu
            # uyarı susuyor ama c* 1331 m/s ⟷ (1350, 1650) bandı deliniyor;
            # eski bantla İKİ bandı birden sağlayan O/F YOKTU.
            #
            # LİTERATÜR (kanıt: docs/scofield/raw/OH/D33-3/
            # OH-D33-11_kanit_taslagi.md): N2O'nun özgül impulsu O/F 7-8'de
            # TEPE yapar ve yaklaşık 4-12 bandında yüksek/düz kalır — itkinin
            # ~2/3'ü N2O'nun ekzotermik ayrışmasından, ~1/3'ü yakıttaki
            # oksijenle yanmadan gelir; bu yüzden depolanabilir oksitleyiciler
            # (N2O, H2O2) YÜKSEK O/F'de optimize olur (LOX ~2).
            #
            # YÖN: bu bir tolerans büyütmesi DEĞİLDİR. Üst uç 6,0 → 12,0
            # optimumu banda alır; ALT uç 0,5 → 4,0 ise bandı DARALTIR ve
            # O/F 2,5 gibi aşırı yakıt-zengin tasarımlar ARTIK uyarı alır
            # (eskiden sessizdi). Sayı teste gömülmez; tek kaynak burasıdır.
            'of_ratio': {
                'n2o_htpb': (4.0, 12.0),
                # n2o_paraffin: tablo optimumu 8,0 tam ÜST KENARDA duruyordu;
                # aynı literatür ailesi (depolanabilir oksitleyici platosu).
                'n2o_paraffin': (4.0, 12.0),
            },
            'c_star': {
                'n2o_htpb': (1350, 1650),  # m/s
                'n2o_paraffin': (1400, 1700),
            },
            'gamma': (1.10, 1.35),
            'gas_constant': (200, 500),     # J/kg·K
            'temperature': (2500, 3500),    # K
        }
        
        self.injector_limits = {
            'reynolds_number': (1000, 200000),
            # ΔP/Pc — alt sınır acoustic_modes'un TEK tanımından ithal;
            # üst sınır ayrı gerekçeli (yukarıdaki modül başlığına bakınız).
            'pressure_drop_ratio': (CHUG_DP_RATIO_MINIMUM,
                                    INJECTOR_DP_PC_CEILING),
            'exit_velocity': (10, 100),           # m/s
            # ÖH D37 A2 hibrit · YB-03 (F-10 temizliği): ölü 'hole_diameter' (0,2/5,0) bandı KALDIRILDI — hiçbir yerde okunmuyordu, künyesi yoktu; delik çapı bandının tek kaynağı hrma.constants.ORIFICE_D_BAND_MM.
        }
        #: Bandın nereden geldiği — rapor bunu künye olarak taşır ki
        #: kullanıcı "bu 0,15 kimin sayısı" sorusunu cevaplayabilsin.
        self.injector_limit_sources = {
            'pressure_drop_ratio': (
                f'lower bound = hrma.analysis.acoustic_modes.'
                f'CHUG_DP_RATIO_MINIMUM ({CHUG_DP_RATIO_MINIMUM:.2f}, chug '
                f'stability, {CHUG_THRESHOLD_CITATION}; recommended '
                f'{CHUG_DP_RATIO_RECOMMENDED:.2f}); upper bound = '
                f'INJECTOR_DP_PC_CEILING ({INJECTOR_DP_PC_CEILING:.2f}, feed '
                f'system cost, not a stability criterion)'),
        }
        
        self.geometry_limits = {
            # ÖH D35 / OH-ON-02 — SABİT (4, 250) BANDI KALDIRILDI.
            #
            # ÖLÇÜLDÜ (``docs/scofield/raw/OH/D35/onemli-hibrit-fizik/a1/
            # once.json``): ürünün KENDİ tam adapte lülesi kendi bandının
            # dışında sayılıyordu.
            #   Pc = 20 bar, Pa = 1,013 bar, γ = 1,1457 -> ε = 3,9041,
            #       çıkış basıncı = ortam (TAM ADAPTE) ama uyarı YANDI.
            #   Pc =  5 bar (deniz seviyesi)            -> ε = 1,5310,
            #       yine tam adapte, yine uyarı YANDI.
            #   Pc = 20 bar, ε = 50 (AĞIR AŞIRI GENLEŞME, ayrılma var)
            #                                            -> uyarı YANMADI.
            # Yani bant, doğru lüleleri suçlayıp yanlış lüleyi geçiriyordu:
            # deniz seviyesinde ε ≥ 4 için Pc ≳ 21-22 bar gerekir, dolayısıyla
            # 20 bar ve altındaki HER deniz seviyesi motoru (kılavuzun demo
            # motoru dâhil) yanlış uyarı alıyordu. OH-D33-11'in (O/F bandı)
            # birebir kardeşi.
            #
            # YENİ BANT İCAT EDİLMEDİ: ε'nin makul olup olmadığı ORTAM
            # BASINCINA göre belirlenir ve hüküm koşumun KENDİ Summerfield
            # ekranından (``motor.nozzle_expansion_screen``) okunur — o ekran
            # ε_ayrılma'yı izentropik alan-Mach bağıntısıyla (Sutton &
            # Biblarz 9. baskı Eş. 3-25/3-26) çözer ve k = 0,40 sabitini
            # ``hrma/flow/separation.py``den alır. Burada İKİNCİ bir ölçüt
            # yazılmaz (tek kaynak).
            #
            # Geriye kalan tek SAYI, literatür bandı değil GEOMETRİ tabanıdır:
            # yakınsak-ıraksak bir lülede ses-üstü çıkış için A_e/A_t > 1
            # olmak zorundadır (aynı izentropik bağıntı M = 1'de ε = 1 verir).
            'expansion_ratio_supersonic_floor': 1.0,
            'port_diameter_initial': (5, 100),    # mm
            'port_diameter_final': (10, 200),     # mm
            'chamber_length': (50, 2000),         # mm
        }
    
    def validate_performance_data(self, data: Dict, propellant_combo: str) -> List[str]:
        """Performans verilerini doğrula"""
        warnings_list = []
        
        # Specific Impulse
        isp = data.get('isp', 0)
        isp_limits = self.performance_limits['specific_impulse'].get(propellant_combo, (150, 300))
        if not (isp_limits[0] <= isp <= isp_limits[1]):
            sev = "critical" if isp < isp_limits[0] * 0.8 or isp > isp_limits[1] * 1.2 else "warning"
            warnings_list.append(_w("warn.validation.isp_out_of_range", sev,
                                    isp=round(float(isp), 1),
                                    lo=isp_limits[0], hi=isp_limits[1]))

        # C-star
        c_star = data.get('c_star', 0)
        c_star_limits = self.performance_limits['c_star'].get(propellant_combo, (1200, 1800))
        if not (c_star_limits[0] <= c_star <= c_star_limits[1]):
            sev = "critical" if c_star < c_star_limits[0] * 0.9 else "warning"
            warnings_list.append(_w("warn.validation.cstar_out_of_range", sev,
                                    cstar=round(float(c_star), 0),
                                    lo=c_star_limits[0], hi=c_star_limits[1]))

        # Gamma
        gamma = data.get('gamma', 0)
        gamma_limits = self.performance_limits['gamma']
        if not (gamma_limits[0] <= gamma <= gamma_limits[1]):
            warnings_list.append(_w("warn.validation.gamma_out_of_range", "warning",
                                    gamma=round(float(gamma), 3),
                                    lo=gamma_limits[0], hi=gamma_limits[1]))

        # O/F Ratio
        of_ratio = data.get('of_ratio', 0)
        of_limits = self.performance_limits['of_ratio'].get(propellant_combo, (0.5, 8.0))
        if not (of_limits[0] <= of_ratio <= of_limits[1]):
            warnings_list.append(_w("warn.validation.of_out_of_range", "warning",
                                    of=round(float(of_ratio), 2),
                                    lo=of_limits[0], hi=of_limits[1]))

        return warnings_list
    
    def validate_injector_data(self, data: Dict,
                               chamber_pressure: Optional[float] = None,
                               assessment: Optional[Dict] = None,
                               feed_system: Optional[str] = None,
                               feed_pressure_source: Optional[str] = None
                               ) -> List[str]:
        """İnjektör verilerini doğrula.

        ``feed_system`` (V301/PANEL, C-5): ``'pump_fed'`` | ``'pressure_fed'``
        | ``'self_pressurised'`` | ``None``. ΔP/Pc tavanı aşıldığında cümle ve
        önem buradan kurulur (``DP_PC_HIGH_CODE_BY_FEED``); bilinmiyorsa
        bedel adlandırılmaz. ``feed_pressure_source`` çağıranın künyesidir
        ve kayda aynen yazılır.

        ``chamber_pressure`` [bar] ΔP/Pc ölçütünün paydasıdır ve ÇAĞIRANDAN
        gelir; enjektör sözlüğünde de bulunabilir. ``assessment`` verilirse
        eksen künyeleri oraya yazılır (hüküm verildi mi, hangi bantla,
        paydanın kaynağı ne).

        ÖH Z5S / P10-A (P10B2-04, KRİTİK) — ÖLÇÜLDÜ (28 Ağustos 2026,
        ``olcum_once.json``): burada ``chamber_pressure = data.get(
        'chamber_pressure', 20)`` yazıyordu ve ÇAĞIRAN sözlükte
        (``injector_results``) böyle bir anahtar HİÇ yoktu. Yani ΔP/Pc oranı
        HER KOŞUMDA uydurma 20 bar'a bölünüyordu:

            Pc = 40 bar, ΔP = 8 bar  → gerçek oran 0,20 (SP-8089'un tam
                                        önerdiği değer), basılan oran 0,40
                                        → SAHTE ``dp_pc_high`` uyarısı
            Pc = 10 bar, ΔP = 2 bar  → gerçek oran 0,20, basılan 0,10
                                        (bandın tam kenarı) → gerçek chug
                                        riski olan bir tasarımda SESSİZLİK

        Payda artık uydurulmaz. Çözülemezse hüküm VERİLMEZ (fail-closed) ve
        eksik alan ADIYLA beyan edilir; bir sayı icat edilip "geçti" denmez.
        """
        warnings_list = []
        pc = _finite_positive(chamber_pressure)
        pc_source = 'caller'
        if pc is None:
            pc = _finite_positive(data.get('chamber_pressure'))
            pc_source = 'injector record' if pc is not None else None

        # Reynolds Number
        reynolds = data.get('reynolds_number', 0)
        re_limits = self.injector_limits['reynolds_number']
        if not (re_limits[0] <= reynolds <= re_limits[1]):
            if reynolds < re_limits[0]:
                warnings_list.append(_w("warn.validation.reynolds_laminar", "critical",
                                        re=round(float(reynolds), 0), min=re_limits[0]))
            else:
                warnings_list.append(_w("warn.validation.reynolds_high", "warning",
                                        re=round(float(reynolds), 0), max=re_limits[1]))
        
        # Pressure Drop — ΔP/Pc chug ölçütü (payda UYDURULMAZ)
        drop_limits = self.injector_limits['pressure_drop_ratio']
        pressure_drop = _finite_positive(data.get('pressure_drop'))
        kunye = {
            'axis': DP_RATIO_AXIS,
            'band': [drop_limits[0], drop_limits[1]],
            'band_source': self.injector_limit_sources[DP_RATIO_AXIS],
        }
        if pc is None or pressure_drop is None:
            eksik = []
            if pc is None:
                eksik.append('chamber_pressure')
            if pressure_drop is None:
                eksik.append('pressure_drop')
            kunye.update({
                'status': 'not_evaluated',
                'missing_inputs': eksik,
                'reason': (
                    'the injector pressure-drop ratio needs a finite positive '
                    'chamber pressure [bar] and pressure drop [bar]; the '
                    'verdict is withheld rather than computed against a '
                    'substituted value'),
                'ratio': None,
                'chamber_pressure_bar': pc,
                'pressure_drop_bar': pressure_drop,
            })
        else:
            drop_ratio = pressure_drop / pc
            kunye.update({
                'status': 'evaluated',
                'ratio': round(float(drop_ratio), 4),
                'chamber_pressure_bar': pc,
                'chamber_pressure_source': pc_source,
                'pressure_drop_bar': pressure_drop,
            })
            if not (drop_limits[0] <= drop_ratio <= drop_limits[1]):
                if drop_ratio < drop_limits[0]:
                    warnings_list.append(_w("warn.validation.dp_pc_low", "critical",
                                            ratio=round(float(drop_ratio), 2), min=drop_limits[0]))
                else:
                    kod, onem = DP_PC_HIGH_CODE_BY_FEED.get(
                        feed_system, DP_PC_HIGH_FEED_NOT_STATED)
                    kayit = _w(kod, onem, ratio=round(float(drop_ratio), 2),
                               max=drop_limits[1])
                    kayit['feed_system'] = (feed_system
                                            if feed_system in DP_PC_HIGH_CODE_BY_FEED
                                            else None)
                    kayit['feed_pressure_source'] = feed_pressure_source
                    warnings_list.append(kayit)
            kunye['feed_system'] = (feed_system
                                    if feed_system in DP_PC_HIGH_CODE_BY_FEED
                                    else None)
        if assessment is not None:
            assessment[DP_RATIO_AXIS] = kunye

        # Exit Velocity
        exit_velocity = data.get('exit_velocity', 0)
        vel_limits = self.injector_limits['exit_velocity']
        if not (vel_limits[0] <= exit_velocity <= vel_limits[1]):
            warnings_list.append(_w("warn.validation.exit_velocity_out_of_range", "warning",
                                    v=round(float(exit_velocity), 1),
                                    lo=vel_limits[0], hi=vel_limits[1]))

        return warnings_list
    
    def validate_geometry_data(self, data: Dict,
                               assessment: Optional[Dict] = None) -> List[str]:
        """Geometri verilerini doğrula.

        ``assessment`` verilirse genleşme oranı ekseni künyesiyle oraya
        yazılır (ÖH D35 / OH-ON-02) — ölçülmeyen eksen 'normal' basamaz.
        """
        warnings_list = []
        
        # Port Diameters
        d_port_initial = data.get('port_diameter_initial', 0) * 1000  # m to mm
        d_port_final = data.get('port_diameter_final', 0) * 1000
        d_chamber = data.get('chamber_diameter', 0) * 1000
        
        port_limits = self.geometry_limits['port_diameter_initial']
        if d_port_initial > 0 and not (port_limits[0] <= d_port_initial <= port_limits[1]):
            warnings_list.append(_w("warn.validation.port_initial_out_of_range", "warning",
                                    d=round(float(d_port_initial), 1),
                                    lo=port_limits[0], hi=port_limits[1]))

        # Port Growth Check
        if d_port_initial > 0 and d_port_final > 0:
            growth_ratio = d_port_final / d_port_initial
            if growth_ratio < 1.2:
                warnings_list.append(_w("warn.validation.port_growth_low", "warning",
                                        ratio=round(float(growth_ratio), 2)))
            elif growth_ratio > 3.0:
                warnings_list.append(_w("warn.validation.port_growth_high", "critical",
                                        ratio=round(float(growth_ratio), 2)))

        # Chamber vs Port Diameter
        # v3.0.1 (Ayberk tur 1, port kulvarının çapraz kırılması): eski kural
        # ``d_port_final > 0.8 * d_chamber`` kaynaksızdı. Motordan sökülen
        # 0,8·D_ch kırpmasının ikinci kopyasıydı. Grain dış çapı artık yanma
        # sonu portlarından boyutlanıyor: artık et 0 iken D_son = D_kamara ve
        # bu tasarım gereği. O yüzden eski kural HER varsayılan hibrit
        # tasarımda yanlış 'kritik' basıyordu (ölçüldü: 1 kN, O/F 6).
        # Hüküm artık motorun KENDİ geometrik zarfından gelir: son portların
        # zarfı k(N)·D_son + 2·t_artık kamara iç çapını AŞARSA delinme var.
        # Tolerans yalnız kayan nokta karşılaştırması içindir, fizik eşiği
        # değildir.
        if d_chamber > 0 and d_port_final > 0:
            from hrma.engines.hybrid_rocket_engine import (
                grain_port_layout_factor)
            try:
                n_port = int(data.get('port_count') or 1)
            except (TypeError, ValueError):
                n_port = 1
            n_port = max(n_port, 1)
            t_artik_mm = _finite_positive(data.get('residual_web_mm')) or 0.0
            zarf_mm = (grain_port_layout_factor(n_port) * d_port_final
                       + 2.0 * t_artik_mm)
            if zarf_mm > d_chamber * (1.0 + PORT_ENVELOPE_COMPARE_REL_TOL):
                warnings_list.append(_w("warn.validation.port_exceeds_chamber", "critical"))

        # --- Genleşme oranı: hüküm FİZİKTEN, sabit banttan DEĞİL --------
        # (ÖH D35 / OH-ON-02 — gerekçe ``geometry_limits`` künyesinde.)
        expansion_ratio = _finite_positive(data.get('expansion_ratio'))
        if expansion_ratio is not None:
            warnings_list.extend(self._genlesme_hukmu(
                expansion_ratio, data, assessment))

        return warnings_list

    #: Bu eksenin ``comprehensive_validation`` künyesindeki adı.
    EXPANSION_AXIS = 'expansion_ratio'

    def _genlesme_hukmu(self, eps: float, data: Dict,
                        assessment: Optional[Dict]) -> List[Dict]:
        """ε hükmü — koşumun KENDİ Summerfield ekranından okunur.

        Hüküm sırası:
          1. ε <= 1 → ses-üstü çıkış geometrik olarak imkânsız (KRİTİK).
          2. Ekran çözülmüş → hüküm KAZANILMIŞTIR; ayrılma öngörüldüyse
             uyarıyı motorun kendi zinciri basar
             (``warn.hybrid.nozzle_flow_separation``) ve BURADA İKİNCİ KEZ
             basılmaz (tek kaynak); künye hükmü taşır.
          3. Ekran yok / çözülememiş → hüküm GERİ ÇEKİLİR ve nedeni adıyla
             yazılır (fail-closed). Sabit bir banda düşülmez.
        """
        uyarilar: List[Dict] = []
        taban = self.geometry_limits['expansion_ratio_supersonic_floor']
        # Ölçüt SAYILARI burada KOPYALANMAZ (tek kaynak): Summerfield k'sı
        # ve ayrılma basıncı aynı yanıttaki ``motor.nozzle_expansion_screen``
        # bloğunda zaten yayımlıdır; ses-üstü tabanı geometriktir ve
        # aşağıdaki künye metninde adıyla söylenir. İkinci bir kopya,
        # sabit ikiye ayrıldığında sessizce ayrışırdı.
        kunye = {
            'axis': self.EXPANSION_AXIS,
            'expansion_ratio': round(float(eps), 4),
            'criterion_source': (
                'run-specific Summerfield over-expansion screen '
                '(motor.nozzle_expansion_screen carries the factor k, the '
                'separation pressure and the separation-limit area ratio; k '
                'is defined once in hrma/flow/separation.py and the '
                'area-Mach relation is Sutton & Biblarz 9th ed. Eq. '
                '3-25/3-26). No fixed literature band is applied: the '
                'acceptable expansion ratio depends on the ambient pressure '
                'of THIS run. The only fixed number here is the geometric '
                'floor A_e/A_t > %g, below which a converging-diverging '
                'nozzle cannot reach supersonic exit.' % taban),
        }

        if eps <= taban:
            kunye.update({'status': 'evaluated', 'verdict': 'not_supersonic'})
            uyarilar.append(_w('warn.validation.expansion_ratio_not_supersonic',
                               'critical', eps=round(float(eps), 4),
                               floor=taban))
            if assessment is not None:
                assessment[self.EXPANSION_AXIS] = kunye
            return uyarilar

        ekran = data.get('nozzle_expansion_screen')
        ayrilma = (ekran.get('separation_predicted')
                   if isinstance(ekran, dict) else None)
        if not isinstance(ekran, dict) or ayrilma is None:
            kunye.update({
                'status': 'not_evaluated',
                'verdict': None,
                'missing_inputs': ['nozzle_expansion_screen'],
                'reason': (
                    'whether this expansion ratio is acceptable depends on '
                    'the ambient pressure, the chamber pressure and gamma of '
                    'this run; the over-expansion screen that solves it was '
                    'not published, so the verdict is withheld rather than '
                    'taken from a fixed band that does not know the ambient '
                    'pressure'),
            })
            uyarilar.append(_w('warn.validation.expansion_ratio_not_evaluated',
                               'warning', eps=round(float(eps), 4)))
            if assessment is not None:
                assessment[self.EXPANSION_AXIS] = kunye
            return uyarilar

        kunye.update({
            'status': 'evaluated',
            'separation_predicted': bool(ayrilma),
            'verdict': ('over_expanded_separated' if ayrilma
                        else 'attached_flow'),
            'ambient_pressure_bar': ekran.get('ambient_pressure_bar'),
            'exit_pressure_bar': ekran.get('exit_pressure_bar'),
            'separation_limit_expansion_ratio': ekran.get(
                'separation_limit_expansion_ratio'),
        })
        if ayrilma:
            # Uyarı motorun kendi zincirinde ZATEN var; ikinci kopya
            # basılmaz, nereye devredildiği künyede yazılıdır.
            kunye['warning_issued_by'] = 'warn.hybrid.nozzle_flow_separation'
        if assessment is not None:
            assessment[self.EXPANSION_AXIS] = kunye
        return uyarilar
    
    def check_sutton_biblarz_criteria(self, data: Dict) -> List[str]:
        """Sutton & Biblarz kitabından kritik tasarım kriterleri"""
        warnings_list = []
        
        # Kısık yüklenmesi tutarlılık kontrolü:
        # F/At ≡ CF·Pc özdeşliği geçerlidir (Sutton & Biblarz 9. baskı, Denk. 3-31).
        # Eski sabit "2.0 N/mm²" eşiği fiziksel bir tasarım kriteri değildi:
        # CF≈1.5 için Pc > ~13 bar olan her normal motoru hatalı biçimde KRITIK
        # işaretliyordu. Bunun yerine ima edilen itki katsayısı
        # CF_ima = (F/At)/Pc hesaplanır ve teorik sınırlarla karşılaştırılır.
        # Üst sınır: gamma=1.2 için sonsuz genleşmeli vakum CF limiti ≈ 2.246
        # (Sutton & Biblarz 9. baskı, Denk. 3-30 limiti / Şekil 3-6).
        thrust = data.get('thrust', 0)
        throat_area = data.get('throat_area', 0)
        chamber_pressure_bar = data.get('chamber_pressure', 0)  # bar
        if thrust > 0 and throat_area > 0 and chamber_pressure_bar > 0:
            throat_loading = thrust / (throat_area * 1e6)  # N/mm² (= MPa)
            implied_cf = throat_loading / (chamber_pressure_bar * 0.1)  # Pc: bar → MPa
            if implied_cf > 2.25:
                warnings_list.append(_w("warn.validation.cf_too_high", "critical",
                                        cf=round(float(implied_cf), 2), limit=2.25))
            elif implied_cf < 0.8:
                warnings_list.append(_w("warn.validation.cf_too_low", "warning",
                                        cf=round(float(implied_cf), 2), limit=0.8))

        # L* kontrolü (Karakteristik uzunluk)
        l_star = data.get('l_star', 0)
        if l_star > 0:
            if l_star < 0.5:
                warnings_list.append(_w("warn.validation.lstar_low", "critical",
                                        lstar=round(float(l_star), 2)))
            elif l_star > 2.0:
                warnings_list.append(_w("warn.validation.lstar_high", "warning",
                                        lstar=round(float(l_star), 2)))

        # Regresyon hızı kontrolü
        regression_rate = data.get('regression_rate', 0) * 1000  # m/s to mm/s
        if regression_rate > 0:
            if regression_rate < 0.5:
                warnings_list.append(_w("warn.validation.regression_low", "warning",
                                        rate=round(float(regression_rate), 2)))
            elif regression_rate > 5.0:
                warnings_list.append(_w("warn.validation.regression_high", "critical",
                                        rate=round(float(regression_rate), 2)))

        return warnings_list
    
    def comprehensive_validation(self, motor_data: Dict, injector_data: Dict,
                               propellant_combo: str = 'n2o_htpb',
                               feed_system: Optional[str] = None,
                               feed_pressure_source: Optional[str] = None
                               ) -> Dict:
        """Kapsamlı validasyon.

        ÖH Z5S / P10-A: ΔP/Pc ölçütünün paydası (kamara basıncı [bar]) artık
        MOTOR sonuçlarından gelir. Enjektör sözlüğü kendi kamara basıncını
        taşıyorsa o kazanır (çağıran açıkça koymuştur); yoksa motorunki
        kullanılır. Hiçbiri yoksa o EKSEN ölçülmez ve rapor bunu ADIYLA
        söyler — 'geçti' demez.
        """
        all_warnings = []
        assessment: Dict = {}

        pc = None
        if isinstance(injector_data, dict):
            pc = _finite_positive(injector_data.get('chamber_pressure'))
        if pc is None and isinstance(motor_data, dict):
            pc = _finite_positive(motor_data.get('chamber_pressure'))

        # Tüm validasyonları çalıştır
        all_warnings.extend(self.validate_performance_data(motor_data, propellant_combo))
        all_warnings.extend(self.validate_injector_data(
            injector_data, chamber_pressure=pc, assessment=assessment,
            feed_system=feed_system,
            feed_pressure_source=feed_pressure_source))
        all_warnings.extend(self.validate_geometry_data(
            motor_data, assessment=assessment))
        all_warnings.extend(self.check_sutton_biblarz_criteria(motor_data))

        # Kritik/uyarı ayrımı — ARTIK severity alanından (dil-bağımsız), eskiden
        # metin içindeki 'KRITIK'/'UYARI' string'inden parse ediliyordu.
        critical_warnings = [w for w in all_warnings if w.get('severity') == 'critical']
        # V301/PANEL (C-5): bilgi düzeyli kayıt (kendinden basınçlı N2O'nun
        # ΔP/Pc notu) uyarı listesinde GÖRÜNÜR kalır (uç yeniden adlandırırken
        # de oradaydı), ama genel durumu "uyarı"ya çekmez: bir bilgi notu
        # uyarı değildir.
        regular_warnings = [w for w in all_warnings
                            if w.get('severity') in ('warning', 'info')]
        uyari_var = any(w.get('severity') == 'warning'
                        for w in regular_warnings)

        # ÖLÇÜLMEYEN EKSEN 'NORMAL' BASAMAZ (fail-closed / sahte gösterge
        # yasağı): girdisi olmadığı için hüküm verilemeyen bir eksen varken
        # yeşil "normal" rozeti, kullanıcının hiç yapılmamış bir denetimi
        # yapılmış sanmasıdır. Yeni i18n anahtarı İCAT EDİLMEZ (sözlük bu
        # partinin dosyası değil): mevcut 'status.warnings' kodu kullanılır,
        # eksik ekseni ADIYLA söyleyen künye ise makine-okur alanda taşınır.
        withheld = sorted(ad for ad, k in assessment.items()
                          if k.get('status') != 'evaluated')
        assessment_complete = not withheld

        # Genel değerlendirme — status da i18n kodu ({code}); frontend TF ile çevirir.
        if critical_warnings:
            overall_status = _w("status.critical", "critical")
        elif uyari_var or withheld:
            overall_status = _w("status.warnings", "warning")
        else:
            overall_status = _w("status.normal", "info")

        return {
            'overall_status': overall_status,
            'critical_warnings': critical_warnings,
            'regular_warnings': regular_warnings,
            'total_warnings': len(all_warnings),
            'validation_passed': (len(critical_warnings) == 0
                                  and assessment_complete),
            # Hangi eksen NEYLE ölçüldü — hüküm kazanılmıştır, varsayılmamıştır.
            'injector_assessment': assessment,
            'assessment_complete': assessment_complete,
            'axes_not_evaluated': withheld,
        }

# Global instance
validator = ValidationSystem()