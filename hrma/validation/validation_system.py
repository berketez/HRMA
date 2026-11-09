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
        self.performance_limits = {
            # V306 (6 Kas, ana model — HİBRİT-SAYI AÇIK KALANLAR + ÖLÇÜT DEVİR):
            # KAYNAKSIZ HÜKÜM BANTLARI KALDIRILDI. 'Sutton & Biblarz, NASA SP-8089,
            # AIAA' genel atfı sayfa/tablo taşımıyordu. Sabit Isp bandı
            # (n2o_htpb 180-250 s, varsayılan 150-300) ölçek ve verime bağlı bir
            # büyüklüğe sabit hüküm veriyordu: GERÇEK ölçülmüş Carmicino t01
            # motoru (147,4 s) 'beklenen aralık dışında' uyarısı alıyordu
            # (SAYI emsali ``test_kaynaksiz_hukum_bandi_YOK``). Isp'nin
            # tutarlılığı kaynaklı iki ölçütle zaten denetleniyor: c* (koşunun
            # kuramsal c*'ı × çiftin ÖLÇÜLMÜŞ η_c* bandı, aşağıda) ve nozulun
            # kendi CF modeli. γ (1,10-1,35) bandı da kaynaksızdı; γ'nın
            # tanım aralığı tek kaynakta (heat_transfer_analysis.GAMMA_BAND_MIN/
            # MAX, Bartz bağıntılarının tanım aralığı) ve dışında modeller
            # hata verir. 'chamber_pressure', 'gas_constant', 'temperature'
            # hiçbir yerde okunmuyordu (ölü ayar).
            # V306/HİBRİT-SAYI (M-HIBRIT-23 + M-HIBRIT-12) — 'of_ratio' ve
            # 'c_star' BANTLARI BURADAN KALKTI (tek kaynağa taşındı).
            #
            # O/F: ÖLÇÜLDÜ (docs/scofield/raw/OH/V306/hibrit-sayi/olcum/
            # sayi_once.json, L3 LOX/parafin): tabloda olmayan çift uçta
            # 'n2o_htpb'ye düşüyor ve N2O'nun 4-12 bandını alıyordu;
            # programın kendi optimumu (2,48) "kullanılabilir aralık dışında"
            # uyarısı aldı. Bant artık ``hybrid_rocket_engine.hybrid_of_band``
            # (N2O çiftlerinin 4-12'si ÖH D33-3 / OH-D33-11 kararıyla —
            # literatür künyesi orada — aynen oraya taşındı) ve koşunun
            # kendi ``optimum_analysis.of_range_searched``ından okunur:
            # optimum hangi bantta arandıysa uyarı o banttır.
            #
            # c*: ÖLÇÜLDÜ (aynı dosya, CARM_t01): kullanıcının ölçülmüş
            # η_c* 0,79'u (HRMA'nın kendi ölçülmüş aralığı 0,77-0,99) c*
            # 1215 m/s ile kaynaksız 1350-1650 bandının altında kaldı ve
            # KRİTİK aldı. Beklenen c* artık koşunun KENDİ kuramsal c*'ı ×
            # çiftin ölçülmüş η_c* bandı
            # (``hybrid_rocket_engine.hybrid_c_star_efficiency_band``,
            # kaynaklı varsayılanla aynı kayıt).
        }
        
        self.injector_limits = {
            # V306 (6 Kas, ana model): 'reynolds_number' (1000-200000) ve
            # 'exit_velocity' (10-100 m/s) KALDIRILDI. Reynolds metni ekranda
            # "kullanılan bağıntı aralığının üst sınırı" diyordu, oysa HRMA'nın
            # Cd'si Re'ye bağlı bir bağıntı değil (injector_design.CD_TABLE:
            # giriş biçimi + L/D) — iddia kaynaksızdı ve N2O enjektörlerinde
            # (Re ~1e5-1e6) her tasarımda yanıyordu (tur L1-L5'in beşi). Laminer
            # eşiği de iki sayıydı (burada 1000 KRİTİK, enjektör modülünde
            # 4000 not). Çıkış hızı bandı enjektör modülündeki BEYANLI HRMA
            # buluşsalının (INJECTION_VELOCITY_HEURISTIC_BAND_M_S, 20-50) ikinci,
            # farklı sayılı ve "Nozul çıkış hızı" diye yanlış adlı kopyasıydı.
            # Tek kaynak enjektör modülünün kendi notlarıdır.
            # ΔP/Pc — alt sınır acoustic_modes'un TEK tanımından ithal;
            # üst sınır ayrı gerekçeli (yukarıdaki modül başlığına bakınız).
            'pressure_drop_ratio': (CHUG_DP_RATIO_MINIMUM,
                                    INJECTOR_DP_PC_CEILING),
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
            # V306 (6 Kas, ana model): port 5-100 / 10-200 mm ve oda boyu
            # 50-2000 mm bantları kaynaksızdı ve ölçeğe bağlıydı (100 kN
            # hibritte ilk port 100,3 mm 'beklenen 5-100' uyarısı aldı); son
            # port ve oda boyu bantları hiç okunmuyordu. Kalan geometri
            # hükümleri fizikseldir: port zarfı > oda (aşağıda) ve ε tabanı.
        }
    
    def validate_performance_data(self, data: Dict, propellant_combo: str) -> List[str]:
        """Performans verilerini doğrula"""
        warnings_list = []
        
        # V306 (6 Kas): kaynaksız Isp bandı hükmü kalktı (künye: __init__).

        ox, _, yakit = str(propellant_combo or '').partition('_')

        # C-star — V306/HİBRİT-SAYI (M-HIBRIT-12): beklenen teslim c*
        # aralığı = koşunun kuramsal c*'ı × çiftin ÖLÇÜLMÜŞ η_c* bandı
        # (kaynaklı varsayılanla aynı kayıt). Kullanıcının η_c*'ı HRMA'nın
        # kendi ölçülmüş aralığındaysa uyarı YOK; dışındaysa 'warning'
        # (ölçülmüş bir verim KRİTİK değildir). Kuramsal c* ya da η
        # yayımlanmamışsa bu eksende hüküm verilmez (sayı uydurulmaz).
        c_star = _finite_positive(data.get('c_star'))
        c_th = _finite_positive(data.get('c_star_theoretical'))
        _cs = data.get('c_star_efficiency')
        eta = _finite_positive(_cs.get('eta_c_star')) if isinstance(
            _cs, dict) else None
        if c_star is not None and c_th is not None and eta is not None:
            from hrma.engines.hybrid_rocket_engine import (
                hybrid_c_star_efficiency_band)
            eb = hybrid_c_star_efficiency_band(ox, yakit)
            e_lo, e_hi = eb['band']
            if not (e_lo <= eta <= e_hi):
                warnings_list.append(_w(
                    "warn.validation.cstar_outside_eta_band", "warning",
                    cstar=round(float(c_star), 0),
                    lo=round(e_lo * c_th, 0), hi=round(e_hi * c_th, 0),
                    eta=round(float(eta), 3), eta_lo=e_lo, eta_hi=e_hi,
                    n=eb['n_tests']))

        # V306 (6 Kas): kaynaksız γ bandı hükmü kalktı (künye: __init__).

        # O/F Ratio — V306/HİBRİT-SAYI (M-HIBRIT-23): bant TEK kaynaktan.
        # Koşunun optimumu hangi bantta arandıysa (``optimum_analysis.
        # of_range_searched``; stokiyometriğe genişlemiş hâli dahil) uyarı
        # o banttır — programın kendi optimumu kendi uyarısını alamaz. Arama
        # yapılmamışsa (ör. belirsizlik örneği) aynı tablo
        # (``hybrid_of_band``) okunur. Kaynaklı kullanılabilir bandı olan
        # çift (N2O) 'of_out_of_range', olmayan çift
        # 'of_outside_search_band' alır (iki ayrı cümle, aynı bant kaynağı).
        of_ratio = data.get('of_ratio', 0)
        from hrma.engines.hybrid_rocket_engine import hybrid_of_band
        _ob = hybrid_of_band(ox, yakit)
        of_limits = _ob['band']
        _oa = data.get('optimum_analysis')
        _ar = _oa.get('of_range_searched') if isinstance(_oa, dict) else None
        if (isinstance(_ar, (list, tuple)) and len(_ar) == 2
                and all(_finite_positive(v) is not None for v in _ar)):
            of_limits = (float(_ar[0]), float(_ar[1]))
        if not (of_limits[0] <= of_ratio <= of_limits[1]):
            _kod = ("warn.validation.of_out_of_range"
                    if _ob['kind'] == 'usable'
                    else "warn.validation.of_outside_search_band")
            warnings_list.append(_w(_kod, "warning",
                                    of=round(float(of_ratio), 2),
                                    lo=round(of_limits[0], 2),
                                    hi=round(of_limits[1], 2)))

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

        # V306 (6 Kas): Reynolds hükmü kalktı (künye: __init__ injector_limits).
        
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

        # V306 (6 Kas): çıkış hızı hükmü kalktı (künye: __init__ injector_limits).

        return warnings_list
    
    def validate_geometry_data(self, data: Dict,
                               assessment: Optional[Dict] = None) -> List[str]:
        """Geometri verilerini doğrula.

        ``assessment`` verilirse genleşme oranı ekseni künyesiyle oraya
        yazılır (ÖH D35 / OH-ON-02) — ölçülmeyen eksen 'normal' basamaz.
        """
        warnings_list = []
        
        # V306 (6 Kas, ana model): ilk port 5-100 mm bandı ve büyüme oranı
        # 1,2 / 3,0 eşikleri kaynaksızdı (künye: __init__ geometry_limits).
        # Port zarfı > oda iç çapı fiziksel imkânsızlık hükmü aşağıda kalır.
        d_port_final = data.get('port_diameter_final', 0) * 1000  # m to mm
        d_chamber = data.get('chamber_diameter', 0) * 1000

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
        # (Eski üst sınır: yalnız gamma=1.2 için sonsuz genleşmeli vakum CF ≈ 2.246;
        # Sutton & Biblarz 9. baskı, Denk. 3-30 / Şekil 3-6 — V306 notu aşağıda.)
        thrust = data.get('thrust', 0)
        throat_area = data.get('throat_area', 0)
        chamber_pressure_bar = data.get('chamber_pressure', 0)  # bar
        if thrust > 0 and throat_area > 0 and chamber_pressure_bar > 0:
            throat_loading = thrust / (throat_area * 1e6)  # N/mm² (= MPa)
            implied_cf = throat_loading / (chamber_pressure_bar * 0.1)  # Pc: bar → MPa
            # V306 (6 Kas, ana model): üst sınır koşunun KENDİ γ'sıyla
            # (sonsuz genleşmeli vakum CF'si, Denk. 3-30, p_e = p_a = 0; tek
            # kaynak ``nozzle_flow_1d.ideal_thrust_coefficient``). Sabit 2,25
            # yalnız γ = 1,2 içindi: γ = 1,15'te sınır ~2,50, γ = 1,25'te ~2,08.
            # γ okunamıyorsa bu eksende hüküm verilmez (sabit γ varsayılmaz).
            # Alt eşik (CF < 0,8), L* (0,5 / 2,0 m) ve regresyon (0,5 / 5 mm/s)
            # bantları kaynaksızdı ve kalktı: aşırı genleşme Summerfield
            # ekranında, regresyon yasasının geçerlilik aralığı kendi künyesinde.
            gamma = _finite_positive(data.get('gamma'))
            if gamma is not None and gamma > 1.0:
                from hrma.analysis.nozzle_flow_1d import ideal_thrust_coefficient
                cf_limit = ideal_thrust_coefficient(gamma, 0.0, 0.0, 1.0)
                if implied_cf > cf_limit:
                    warnings_list.append(_w("warn.validation.cf_too_high", "critical",
                                            cf=round(float(implied_cf), 2),
                                            limit=round(float(cf_limit), 3),
                                            gamma=round(float(gamma), 3)))

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