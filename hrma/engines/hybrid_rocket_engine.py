import numpy as np
from typing import Dict
from scipy.optimize import fminbound, minimize_scalar, brentq
from hrma.engines.combustion_analysis import CombustionAnalyzer
from hrma.engines.nozzle_design import NozzleDesigner
from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
from hrma.analysis.structural_analysis import StructuralAnalyzer
from hrma.analysis.regression_analysis import RegressionAnalyzer
from hrma.data.external_data_fetcher import data_fetcher
from hrma.data.propellant_database import (
    HYBRID_REGRESSION_COEFFICIENTS,
    N2O_LIQUID_DENSITY_SAT_25C,
)
from hrma.constants import (G_0, LAMBDA_BELL, LAMBDA_PARABOLIC,
                            LAMBDA_CONICAL_15DEG, C_STAR_PLAUSIBLE_BAND_MPS,
                            C_STAR_BAND_DEFAULT_MPS)
import warnings

# --- Kamara boyu bölümlendirme katsayıları (v2.5.2 L* modeli) ---
# Ön-yanma odası boyu = PRE_CHAMBER_D_FACTOR · D_kamara (sabit oran).
# Art-yanma odası boyu L* hacminden çözülür; aşağıdaki oranlarla
# kelepçelenir (çok kısa = yanma tamamlanmaz, çok uzun = ölü ağırlık).
# Kaynak: Sutton & Biblarz 9. baskı Böl. 8/16; Chiaverini & Kuo (2007).
# Yanma integrasyonu adım sayısı ÜST SINIRI (2026-07-23 kararlılık denetimi).
# Adım sayısı t_b ve port çapından türetiliyor ve tavansızdı: uç girdilerde
# (burn_time=1e12 -> 5.6 trilyon adım) süreç fiilen kilitleniyor, dakikalarca
# dönüp megabaytlarca uyarı günlüğü üretiyordu. Geçerli tasarım aralığının en
# kötü hâli ~17 000 adımdır; bu tavan onun on katından fazla olduğu için
# meşru hesapların çözünürlüğünü ETKİLEMEZ, yalnız kilitlenmeyi keser.
MAX_BURN_INTEGRATION_STEPS = 200_000

PRE_CHAMBER_D_FACTOR = 0.5
POST_CHAMBER_D_FACTOR_MIN = 0.3
POST_CHAMBER_D_FACTOR_MAX = 3.0


def _w(code: str, severity: str = "warning", **params) -> Dict:
    """i18n uyarısı: dile bağlı sabit metin YERİNE yapısal kayıt.

    Sözleşme solid_rocket_engine.py::_w ile BİREBİR aynıdır:
    ``{"code", "params", "severity"}``, severity ∈ {critical, warning, info}.
    Kod adlandırması: ``warn.hybrid.<slug>``.

    v2.6.2 GEREKÇE (Codex denetim bulgusu): hibrit motorda kullanıcıya uyarı
    ULAŞTIRAN KANAL YOKTU — her uyarı ``warnings.warn`` ile sunucu konsoluna
    gidiyordu. Enjektör modülü çöküp basit Bernoulli hesabına düşse bile
    kullanıcı bunu göremiyordu. Artık tüm uyarılar sonuç sözlüğündeki
    ``warnings`` listesine de konur (katı/sıvı motorlarla aynı sözleşme).
    """
    return {"code": code, "params": params, "severity": severity}


# Regresyon katsayısı tablosunun (hrma/data/propellant_database.py ->
# HYBRID_REGRESSION_COEFFICIENTS) her satırının HANGİ OKSİTLEYİCİ ile
# ölçüldüğü. Sayısal değil, kaynak/kapsam meta verisidir; o dosyadaki atıf
# yorumlarından birebir okunur:
#   htpb    -> N2O  (Doran et al., AIAA 2007-5352)
#   abs     -> N2O  (Whitmore & Peterson, JPP 29(3) 2013)
#   paraffin-> GOX  (Karabeyoglu et al., JPP 20(6) 2004 SP-1a;
#                    Zilliac & Karabeyoglu AIAA 2006-4504 Tablo 2)
#   pe      -> O2   (HDPE/O2, Zilliac & Karabeyoglu Tablo 2)
#   pmma    -> O2   (Greiner & Frederick verisi, aynı tablo)
# v2.6.2 fizik denetimi bulgusu F020: kod bugüne dek oksitleyiciyi HİÇ
# kullanmıyordu; N2O katsayılarını LOX/GOX motorlarına sessizce uyguluyordu.
# Hibrit regresyon oksitleyiciye kuvvetle bağlıdır (alev sıcaklığı, blowing
# parametresi ve radyasyon payı farklıdır; HTPB/GOX ile HTPB/N2O arasında a
# tipik olarak 2 kata varan fark gösterir) — Sutton & Biblarz 9. baskı Böl. 16;
# Chiaverini & Kuo, AIAA Progress Vol. 218 (2007).
REGRESSION_COEFF_OXIDIZER_BASIS = {
    'htpb': 'n2o',
    'abs': 'n2o',
    'paraffin': 'gox',
    'pe': 'o2',
    'pmma': 'o2',
}

# Aynı tabloda "yayınlanmış, hakemli bir korelasyon bulunamadı" notuyla
# DOĞRULANMAMIŞ olarak korunan yakıtlar. Tasarım için kullanılmamalıdır;
# kullanıcı bunu görmeliydi ama hiçbir yerde söylenmiyordu (F020 eki).
UNVALIDATED_REGRESSION_FUELS = ('pla', 'carbon', 'aluminum', 'al2o3')

# HTPB katsayısının doğrulama veritabanına karşı ÖLÇÜLEN sapması (F019).
# n=0.555 sabit tutulup DB'nin HTPB kayıtlarına (n=43 test, carmicino2013 ve
# rezaei2018 kampanyaları) en iyi a arandığında a=6.24e-5 çıkıyor; koddaki
# 3.68e-5 değerinin 1.70 KATI. Bu, koddaki modelin HTPB regresyonunu
# sistematik olarak DÜŞÜK tahmin ettiği anlamına gelir (bias −%39.5,
# medAPE %46.6) — ve bu GÜVENLİ OLMAYAN yöndür: yakıt debisi düşük, O/F
# yüksek tahmin edilir, grain ~%25 fazla uzun boyutlandırılır ve web
# gerçekte tahminden ~%25 ERKEN tükenir.
# Katsayı DEĞİŞTİRİLMEDİ (birincil kaynak Doran et al. AIAA 2007-5352'nin
# tam metni doğrulanamadı; "asla uydurma" ilkesi gereği ölçülen sapma
# uyarı olarak bildirilir, sessizce yeni bir sayı uydurulmaz).
HTPB_COEFF_DB_BIAS_PCT = -39.5
HTPB_COEFF_DB_MEDAPE_PCT = 46.6

# Port çapının kamara iç çapına oranı için üst sınır. Yakıt grain'i portu
# SARDIĞINDAN port her zaman kamaradan küçüktür; kalan et kalınlığı
# (D_ch − D_port)/2 yapısal ve yanma açısından gereklidir. Web tükenmesi bu
# orana ulaşınca ilan edilir. TEK TANIM YERİ (CLAUDE.md kural 11): hem
# time-marching sınırı hem de girdi doğrulaması bu sabiti kullanır.
PORT_TO_CHAMBER_MAX_RATIO = 0.8

# Tasarım noktasında grain BOYU ile regresyon hızı arasındaki sabit-nokta
# iterasyonunun durdurma ölçütleri (v2.6.2 fizik denetimi, bulgu F133).
# TEK TANIM YERİ (CLAUDE.md kural 11). Bağıl tolerans, iç (r_dot) çözücünün
# 1e-6 bağıl toleransından belirgin biçimde gevşek TUTULMAZ ama onun sayısal
# gürültüsünün altına da inilmez: 1e-8, iki mertebe altında kalıp iç çözücünün
# adım-sayısı sıçramalarından etkilenmeyecek güvenli aralıktır.
GRAIN_LENGTH_FIXED_POINT_TOL = 1e-8
GRAIN_LENGTH_FIXED_POINT_MAX_ITER = 60


#: Arayüzdeki "Include Cooling Channels" seçeneklerinin ısı transferi
#: modelindeki soğutma tipine eşlemesi (v2.6.25).
#:
#: HeatTransferAnalyzer._coolant_side_coefficient üç sınıf tanır ve her birine
#: bir soğutucu-tarafı film katsayısı verir: doğal taşınım 25, zorlanmış hava
#: 100, sıvı rejeneratif 20 000 W/(m²·K) (Huzel & Huang Böl. 4). Arayüz ise
#: kanal GEOMETRİSİ soruyor (radyal / sarmal). Her iki geometri de cidara
#: sıvı soğutucu dolaştırır, yani ikisi de rejeneratif sınıfa girer;
#: aralarındaki fark bu modelin çözünürlüğünün altındadır (kanal en-boy oranı,
#: hız ve basınç düşüşü girdi olarak alınmıyor).
#:
#: Bu yüzden kanal seçildiğinde ayrıca warn.hybrid.cooling_channels_assumed
#: uyarısı verilir: film katsayısı literatür aralığından ALINMIŞTIR, soğutucu
#: debisi ve kaynama marjı DOĞRULANMAMIŞTIR.
COOLING_CHANNEL_TO_TYPE = {
    'none': 'natural',
    'radial': 'regenerative',
    'spiral': 'regenerative',
    # Doğrudan ısı-transferi terimleri de kabul edilir (API çağrıları)
    'natural': 'natural',
    'forced': 'forced',
    'regenerative': 'regenerative',
}

#: Cidar kalınlığı için kabul edilen aralık [m]. Arayüz mm gönderir; dönüşüm
#: app.py'de yapılır. 0.5 mm altı imal edilemez, 100 mm üstü bu sınıf motorda
#: girdi hatasıdır (birim karışıklığının işareti).
# Kullanıcının GİRDİĞİ cidar kalınlığı için kabul alt sınırı [m].
# Sıvı motordaki WALL_THICKNESS_MANUFACTURING_MIN_M ile KARIŞTIRILMAMALI:
# o, hesaplanan kalınlığın altına inemeyeceği İMALAT tabanıdır (2 mm);
# bu ise kullanıcının elle girebileceği en ince değerdir (0.5 mm).
# İkisi farklı kavram olduğu için ayrı adlandırıldı (aynı ad iki
# dosyada iki farklı anlamda kullanılıyordu).
WALL_THICKNESS_INPUT_MIN_M = 0.0005
WALL_THICKNESS_MAX_M = 0.100

#: Tasarım emniyet katsayısı için kabul edilen aralık. Arayüz 2-6 sunar;
#: API daha geniş kabul eder ama 1.05 altı (fiilen emniyet payı yok) ve
#: 10 üstü (kütle cezası anlamsız) girdi hatasıdır.
SAFETY_FACTOR_MIN = 1.05
SAFETY_FACTOR_MAX = 10.0

#: Lüle (boğaz) malzemesinin soğutma varsayımı. Arayüzün KENDİ etiketi
#: "Copper (Regeneratively Cooled)" olduğu için bakır rejeneratif soğutmalı
#: kabul edilir; grafit/tungsten/C-C soğutmasız (ısı emici + ışıma) çalışır.
#: Bu bir modelleme kararı değil, arayüzün beyanının okunmasıdır.
NOZZLE_MATERIAL_COOLING = {
    'graphite': 'natural',
    'tungsten': 'natural',
    'carbon_carbon': 'natural',
    'molybdenum_tzm': 'natural',
    'niobium_c103': 'natural',
    'copper': 'regenerative',
    'cucrzr': 'regenerative',
}
#: Arayüz enjektör tipi -> ``engines/injector_design.py`` sözcüğü.
#: İki modül aynı kavram için farklı ad kullanıyor; eşleme olmadan devre
#: modeli ValueError atıyor ve motor uydurma yedeğe düşüyordu.
#:  - 'impingement': arayüz tek akışkanlı (yalnız oksitleyici) çarpışmalı
#:    enjektör sunar; modülün karşılığı 'like_impinging' (benzer-akışkan
#:    doublet). 'impinging_doublet' FARKLI-akışkan çarpışmasıdır ve hibritte
#:    yakıt sıvı olmadığı için uygulanamaz.
#:
#: 'coaxial' BİLEREK eşlenmemiştir: devre modeli hibritte koaksiyel
#: desteklemiyor ("'coax_swirl' hibritte desteklenmez (tek akışkan)";
#: 'gas_gas_coaxial' yalnız sıvı kademeli yanma motorları için). Zorlama bir
#: eşleme kullanıcıya "gas_gas_coaxial yalnız sıvı motor içindir" gibi
#: sormadığı bir tipe dair hata gösterirdi. Bu tipte devre ayrıntısı
#: üretilmez ve nedeni söylenir; enjektörün kendisi ``utils/injector_design``
#: içindeki tek akışkanlı koaksiyel modelle (iç jet + dış anülüs) yine
#: boyutlandırılır, yani kullanıcı sonuçsuz kalmaz.
INJECTOR_TYPE_TO_MODULE = {
    'impingement': 'like_impinging',
}

#: Lüle termal profilinde kullanılan istasyon sayısı. Boğaz istasyonunun
#: çözünürlüğü için 20 yeterli (ölçüldü: 12 ve 20 istasyonda boğaz denge
#: cidar sıcaklığı aynı, 2971 K).
NOZZLE_THERMAL_STATIONS = 20
#: Lüle cidar kalınlığı verilmediğinde kullanılan pay: boğaz insertinde
#: et kalınlığı kamara cidarıyla aynı mertebededir; ayrı bir girdi
#: olmadığı için kamara cidarı kullanılır ve rapor bunu AÇIKÇA yazar.


class HybridRocketEngine:
    def __init__(self, thrust=None, burn_time=None, total_impulse=None, of_ratio=1.0, chamber_pressure=20.0,
                 atmospheric_pressure=1.0, chamber_temperature=None,
                 gamma=1.15, gas_constant=None, l_star=1.0,
                 expansion_ratio=0, nozzle_type='conical',
                 thrust_coefficient=0, regression_a=None,
                 regression_n=None, fuel_density=None, 
                 combustion_type='infinite', chamber_diameter_input=0,
                 contraction_ratio=0,
                 fuel_type='htpb', motor_name='', motor_description='',
                 initial_gox=None, flux_mode='ox', track_performance=True,
                 oxidizer_type='n2o', uq_mode=False, combustion_analyzer=None,
                 eta_c_star=None, precomputed_optimum_of=None,
                 injector_type='showerhead', initial_port_diameter=None,
                 tank_temperature=None, port_count=1,
                 throat_erosion_rate=None,
                 chamber_material='steel_4130', wall_thickness=None,
                 cooling_type='natural',
                 safety_factor=None, chamber_length_override=None,
                 nozzle_material=None, ambient_temperature=None,
                 plate_thickness=None, orifice_inlet=None):
        
        # Tasarım uyarıları (v2.6.2): kullanıcıya ULAŞAN kanal. Liste her
        # şeyden ÖNCE kurulur; aksi hâlde erken üretilen uyarılar kaybolur
        # (katı motorda aynı tuzağa düşülmüştü, bkz. solid __init__ yorumu).
        self.design_warnings = []
        # Varsayılan/eksik girdiyle mi çalışıldı? design_summary.status bu
        # bayrağı okur — eksik girdiyle "OPTIMIZED" demek yanlıştır.
        self._defaults_used = []
        # Bir alt modül çöküp yedek (fallback) yola düşüldü mü?
        self._fallback_used = []

        # --- Termal sınır koşulları (v2.6.25'te bağlandı) -------------------
        # Bunlar önceden analyze_heat_transfer çağrısında sabit yazılıydı;
        # kullanıcının seçtiği malzeme/kalınlık/soğutma termal modele hiç
        # ulaşmıyordu. Ayrıntılı gerekçe o çağrının başındaki yorumda.
        self.chamber_material = self._resolve_chamber_material(chamber_material)
        # v2.6.26 — KURUCU VARSAYILANI "KULLANICI GİRDİSİ" SAYILMAZ.
        # İmzada `wall_thickness=0.005` yazıyordu ve bu değer yapısal modüle
        # `actual_wall_thickness` olarak gidiyordu; modül de DOĞRULAMA moduna
        # geçip "verified against user-supplied wall thickness" diye
        # raporluyordu. Oysa kimse bir kalınlık vermemişti — 5 mm kurucunun
        # kendi varsayımıydı. Kullanıcının tasarımı ile motorun varsayımı
        # arasındaki fark, bu sürümde kapattığımız hata sınıfının ta kendisi.
        # Artık: değer verilmediyse termal model yine 5 mm ile çalışır (bir
        # kalınlık olmadan ısı iletimi çözülemez) ama yapısal modüle None
        # geçilir ve modül BOYUTLANDIRMA modunda kalır.
        self.wall_thickness_user_supplied = wall_thickness is not None
        self.wall_thickness = self._resolve_wall_thickness(wall_thickness)
        self.cooling_type = self._resolve_cooling_type(cooling_type)

        # --- v2.6.26'da bağlanan üç ölü girdi ---------------------------------
        # Üçü de arayüzde VARDI, kullanıcı değerini giriyordu ve hiçbiri
        # hiçbir hesaba ulaşmıyordu (Katman A taraması: 0 yaprak değişimi).
        #   safety_factor          -> yapısal analizin tasarım SF hedefi
        #   chamber_length_override-> L* ile türetilen kamara boyunu ezer
        #   nozzle_material        -> boğaz termal + erozyon değerlendirmesi
        self.design_safety_factor = self._resolve_safety_factor(safety_factor)
        self.chamber_length_override = self._resolve_chamber_length_override(
            chamber_length_override)
        self.nozzle_material = self._resolve_nozzle_material(nozzle_material)

        # --- v2.6.26 ikinci tur: iki sözleşme girdisi -----------------------
        # ambient_temperature [K]: ısı ve yapısal modüller AYNI ortam
        #   sıcaklığını görmelidir. Verilmezse None kalır ve ısı modülünün
        #   kendi varsayılanı tek kaynak olur (buradan sayı uydurulmaz).
        # plate_thickness [m]: enjektör plaka kalınlığı. Orifis L/D = t/d
        #   oranı deşarj katsayısını (Cd) belirler; verilmezse devre çözücüsü
        #   kendi beyan edilen L/D varsayımında kalır.
        self.ambient_temperature = self._resolve_ambient_temperature(
            ambient_temperature)
        self.injector_plate_thickness = self._resolve_plate_thickness(
            plate_thickness)
        self.injector_orifice_inlet = self._resolve_orifice_inlet(
            orifice_inlet)

        # Handle thrust/burn_time vs total_impulse input
        if total_impulse is None:
            # Bu dalda eksik girdi yerine sabit yer tutucu (1000 N / 10 s)
            # kullanılır; kullanıcı bunun bir TASARIM olmadığını bilmelidir.
            if thrust is None:
                self._defaults_used.append('thrust')
            if burn_time is None:
                self._defaults_used.append('burn_time')
        elif thrust is None and burn_time is None:
            self._defaults_used.append('burn_time')
        if total_impulse is not None:
            self.I_total = total_impulse  # N*s
            if thrust is not None:
                self.F = thrust  # N
                self.t_b = total_impulse / thrust  # s
            elif burn_time is not None:
                self.t_b = burn_time  # s
                self.F = total_impulse / burn_time  # N
            else:
                # Default assumption: moderate thrust for given impulse
                self.F = total_impulse / 10  # Default 10s burn time
                self.t_b = 10  # s
        else:
            self.F = thrust if thrust else 1000  # N
            self.t_b = burn_time if burn_time else 10  # s
            self.I_total = self.F * self.t_b  # N*s
        
        self.OF = of_ratio
        self.P_c = chamber_pressure  # bar
        self.P_a = atmospheric_pressure  # bar
        self.fuel_type = fuel_type  # Set fuel_type early
        self.oxidizer_type = oxidizer_type  # 'n2o' | 'lox' | 'h2o2' ...

        # Regresyon akı modu (denetim bulgusu #1): 'total' = Marxman
        # G_total = G_ox + G_fuel (VARSAYILAN); 'ox' = eski G_ox-only (geriye
        # uyum). Marxman & Gilbert (1963); Sutton & Biblarz 9th ed., Böl. 16.
        self.flux_mode = flux_mode if flux_mode in ('total', 'ox') else 'total'
        # O/F kayması -> anlık c*/Isp izleme (denetim bulgusu #2). False ise
        # performans tasarım O/F'sinde donar (eski hızlı davranış).
        self.track_performance = bool(track_performance)
        # Anlık O/F->c*/Isp tablo önbelleği (pahalı denge çözümünü tekrarlamaz)
        self._perf_cache = {}
        
        # Use None as marker for default values to be set by fuel type
        self.T_c = chamber_temperature  # K
        self.gamma = gamma
        self.R = gas_constant  # J/kg·K
        self.L_star = l_star  # m
        self.epsilon = expansion_ratio if expansion_ratio > 0 else None
        self.nozzle_type = nozzle_type
        self.CF = thrust_coefficient if thrust_coefficient > 0 else None
        self.a = regression_a
        self.n = regression_n
        self.rho_f = fuel_density  # kg/m³
        self.combustion_type = combustion_type
        # v2.6.26: kullanıcının kontraksiyon oranı girdisi. Eskiden motora
        # HİÇ geçirilmiyordu (app.py /calculate bu anahtarı okumuyordu bile),
        # dolayısıyla arayüzdeki alan tamamen ölüydü.
        self.contraction_ratio_input = contraction_ratio
        self.chamber_diameter_input = chamber_diameter_input / 1000 if chamber_diameter_input > 0 else 0  # Convert mm to m
        self.motor_name = motor_name
        self.motor_description = motor_description

        # Başlangıç port oksitleyici kütle akısı G_ox [kg/m²·s] — TASARIM
        # parametresidir (denetim bulgusu #1): port kesit alanı bu akıdan
        # boyutlandırılır (A_port = mdot_ox / G_ox). Enjektör orifis akısıyla
        # KARIŞTIRILMAZ. Tipik N2O/HTPB başlangıç değeri 100-500 kg/m²·s,
        # flooding sınırı ~600-700 kg/m²·s (Sutton & Biblarz, Rocket Propulsion
        # Elements 9. baskı, Böl. 16 — hibrit itki).
        if initial_gox is not None and initial_gox > 0:
            self.G_ox_design = float(initial_gox)
            if self.G_ox_design > 600:
                warnings.warn(
                    f"G_ox = {self.G_ox_design:.0f} kg/m²·s flooding sınırına "
                    "(~600-700 kg/m²·s) yakın/üstünde — Sutton & Biblarz 9. baskı, Böl. 16"
                )
        else:
            self.G_ox_design = 350.0  # kg/m²·s — tipik tasarım orta noktası

        # --- v2.5.2 kullanıcı girdisi bağlantıları (UI sözleşmesi) ---
        # Eskiden bu üç büyüklük hesap zincirinde SABİT gömülüydü: enjektör
        # her zaman 'showerhead' tasarlanıyor, N2O tank sıcaklığı hep 293.15 K
        # varsayılıyor ve başlangıç port çapı yalnızca G_ox tasarım akısından
        # türetiliyordu. Kullanıcı arayüzde bunları değiştirse bile sonuç
        # değişmiyordu (kullanıcı şikayeti).
        self.injector_type = (injector_type or 'showerhead').lower()
        # Başlangıç port çapı [m]: verilirse A_port doğrudan bundan gelir ve
        # G_ox_design türetmesi devre dışı kalır (bkz. _design_fuel_grain).
        if initial_port_diameter is not None and float(initial_port_diameter) > 0:
            self.initial_port_diameter = float(initial_port_diameter)
        else:
            self.initial_port_diameter = None
        # Oksitleyici tank sıcaklığı [K]: N2O doyma özellikleri (Dyer NHNE)
        # buna bağlıdır. None ise enjektör modülü varsayılanı kullanılır.
        self.tank_temperature = (float(tank_temperature)
                                 if tank_temperature is not None else None)

        # --- Port sayısı N (v2.6.2 fizik denetimi, bulgu F046) ---
        # Eskiden model TÜM grain'leri tek dairesel port varsayıyordu; port
        # sayısı ne girdi ne çıktıydı. N portlu grain'de her portun akısı
        # G_ox = mdot_ox/(N·A_tek_port), yanma çevresi ise N·π·D'dir. Tek-port
        # varsayımı N portlu geometride G_ox'u N kat büyütür, çevreyi N kat
        # küçültür: r ∝ N^n, mdot_f ∝ N^(n−1) (n=0.555, N=4 için r ~2.2 kat
        # yüksek, mdot_f ~%45 düşük). Doğrulama DB'sinde çok portlu kayıt VAR
        # (hyb-amroc1993-htpb-lox-dm01-*), bunlar tek-port modeliyle koşuluyordu.
        # Kaynak: Sutton & Biblarz 9. baskı Böl. 16 (çok portlu grain akı
        # dağılımı); Story, "Large-Scale Hybrid Motor Testing", NTRS 20060047689.
        try:
            self.port_count = int(port_count) if port_count else 1
        except (TypeError, ValueError):
            self.port_count = 1
        if self.port_count < 1:
            raise ValueError(
                f"port_count must be a positive integer (got {port_count}); "
                "a hybrid grain needs at least one combustion port.")
        if self.port_count > 1:
            # Çok portlu grain'de portlar arası etkileşim, kanat (web) kalınlığı
            # ve merkezi port yerleşimi modellenmiyor: N eşdeğer dairesel port
            # varsayılır. Bu, alan/çevre ölçeklemesini DOĞRU yapar ama port
            # birleşmesini (burn-through) yakalamaz.
            self.design_warnings.append(_w(
                'warn.hybrid.multi_port_equivalent_model', 'info',
                port_count=self.port_count))

        # --- Boğaz erozyonu [m/s, YARIÇAP artış hızı] (bulgu F047) ---
        # Hibritte grafit/fenolik boğaz oksitleyici-zengin akışta erozyona
        # uğrar; At büyüdükçe Pc = mdot·c*/At düşer, CF ve Isp düşer. Katı
        # motor modülünde erozyon modeli var, hibritte YOKTU ve tasarım noktası
        # sabit-Pc raporladığı için kullanıcı bu düşüşü hiç görmüyordu.
        # None/0 => modellenmiyor (açık uyarı üretilir).
        if throat_erosion_rate is None:
            self.throat_erosion_rate = 0.0
        else:
            self.throat_erosion_rate = max(0.0, float(throat_erosion_rate))

        self.g0 = G_0  # m/s^2 (BIPM standart, hrma.constants)

        # --- UQ modu (v2.5.0, ARGE spec 2.3/6.2) ---
        # uq_mode=True: danışma amaçlı find_optimum_of_ratio araması (profilde
        # ~%70 süre) ve irtifa/itki-irtifa tabloları ATLANIR — ana çıktılar
        # (Isp, c*, CF, geometri, grain, kütleler) bire bir aynı kalır (bu
        # eşdeğerlik test kilidi altındadır). Varsayılan False: nominal
        # davranış değişmez.
        self.uq_mode = bool(uq_mode)
        # Nominal koşudan enjekte edilebilir optimum-O/F sonucu: uq_mode'da
        # arama atlanınca çıktı sözleşmesindeki optimum_of alanını doldurmak
        # için (None ise alan atlanır ve nota düşülür).
        self._precomputed_optimum_of = precomputed_optimum_of
        # c* (yanma) verimi: None => teorik denge c*'ı (mevcut davranış).
        # Verilirse teslim edilen c* = eta_c_star * c*_teorik tüm performans
        # zincirine (Isp, mdot, boğaz) uygulanır. Tipik hibrit 0.85-0.95
        # (Sutton & Biblarz 9. baskı, Böl. 5/16; Chiaverini & Kuo 2007).
        self.eta_c_star = None if eta_c_star is None else float(eta_c_star)
        if self.eta_c_star is not None and not (0.5 <= self.eta_c_star <= 1.05):
            warnings.warn(
                f"eta_c_star = {self.eta_c_star:.3f} fiziksel bandın "
                "(0.5-1.05) dışında — yine de uygulanacak"
            )

        # Initialize advanced analysis modules
        # combustion_analyzer enjeksiyonu (UQ): örnekler arası paylaşılan
        # memoizasyonlu CombustionAnalyzer geçirilebilir; None ise her motor
        # kendi analizörünü kurar (mevcut davranış).
        self.combustion_analyzer = (combustion_analyzer
                                    if combustion_analyzer is not None
                                    else CombustionAnalyzer())
        self.nozzle_designer = NozzleDesigner()
        self.heat_transfer_analyzer = HeatTransferAnalyzer()
        self.structural_analyzer = StructuralAnalyzer()
        
        # Set fuel-specific properties
        self._set_fuel_properties()
    
    def _set_fuel_properties(self):
        """Set fuel-specific regression rate parameters and density

        Regresyon katsayıları (a, n) merkezi tablodan gelir:
        hrma/data/propellant_database.py -> HYBRID_REGRESSION_COEFFICIENTS
        (SI birimler: r [m/s] = a * (G_ox [kg/m²·s])^n; kaynak atıfları orada).
        """
        # Default properties for different fuel types
        fuel_properties = {
            'htpb': {
                'density': 920,  # kg/m³
                'combustion_temp': 3200,  # K
                'gas_constant': 415  # J/kg·K
            },
            'pe': {  # Polyethylene
                'density': 950,
                'combustion_temp': 3100,
                'gas_constant': 420
            },
            'pmma': {  # PMMA
                'density': 1180,
                'combustion_temp': 2900,
                'gas_constant': 380
            },
            'paraffin': {
                'density': 900,
                'combustion_temp': 3000,
                'gas_constant': 450
            },
            'abs': {
                'density': 1040,
                'combustion_temp': 2800,
                'gas_constant': 390
            },
            'pla': {
                'density': 1250,
                'combustion_temp': 2700,
                'gas_constant': 370
            },
            'carbon': {
                'density': 2200,
                'combustion_temp': 3500,
                'gas_constant': 350
            },
            'aluminum': {
                'density': 2700,
                'combustion_temp': 3800,
                'gas_constant': 320
            },
            'al2o3': {
                'density': 3950,
                'combustion_temp': 3400,
                'gas_constant': 300
            }
        }

        # Get properties for selected fuel type (default to HTPB if not found)
        fuel_key = self.fuel_type.lower()
        # v2.6.2: bilinmeyen yakıt SESSİZCE HTPB'ye düşüyordu. Kullanıcı
        # "PLA seçtim" sanırken HTPB regresyon katsayılarıyla koşuyordu;
        # design_summary.status bunu 'OPTIMIZED' diye rapor ediyordu.
        if fuel_key not in fuel_properties:
            self._defaults_used.append(f'fuel_properties({fuel_key}->htpb)')
        if (fuel_key not in HYBRID_REGRESSION_COEFFICIENTS
                and (self.a is None or self.n is None)):
            # (a, n) kullanıcıdan gelmediyse ve tabloda karşılığı yoksa
            # HTPB katsayısı KULLANILIYOR demektir — sessiz kalmak yasak.
            self._defaults_used.append(f'regression_coefficients({fuel_key}->htpb)')
            self.design_warnings.append(_w(
                'warn.hybrid.fuel_regression_fallback', 'warning',
                fuel=fuel_key))
        # v2.6.2 (F020 eki): UNVALIDATED_REGRESSION_FUELS listesi tanımlıydı ama
        # HİÇ OKUNMUYORDU. Tabloda karşılığı OLAN ama hakemli kaynağı OLMAYAN
        # yakıtlar (pla/carbon/aluminum/al2o3) sessizce tasarım için
        # kullanılıyor, kullanıcı katsayının doğrulanmamış olduğunu hiçbir
        # yerde görmüyordu.
        if (fuel_key in UNVALIDATED_REGRESSION_FUELS
                and (self.a is None or self.n is None)):
            self.design_warnings.append(_w(
                'warn.hybrid.unvalidated_regression_fuel', 'warning',
                fuel=fuel_key))
        # v2.6.2 (F019): HTPB katsayısının doğrulama veritabanına karşı ÖLÇÜLEN
        # sapması. Sabitler tanımlıydı ama hiçbir uyarıya bağlanmamıştı; katsayı
        # bilinçli olarak DEĞİŞTİRİLMEDİĞİ için (bkz. HTPB_COEFF_DB_BIAS_PCT
        # yorumu) sapmanın kullanıcıya bildirilmesi tek dürüst yoldur.
        if fuel_key in ('htpb', 'abs') and (self.a is None or self.n is None):
            self.design_warnings.append(_w(
                'warn.hybrid.htpb_coeff_bias', 'warning',
                bias_pct=HTPB_COEFF_DB_BIAS_PCT,
                medape_pct=HTPB_COEFF_DB_MEDAPE_PCT))
        props = fuel_properties.get(fuel_key, fuel_properties['htpb'])
        regression = HYBRID_REGRESSION_COEFFICIENTS.get(
            fuel_key, HYBRID_REGRESSION_COEFFICIENTS['htpb']
        )

        # Set properties - use fuel-specific values if user didn't provide them
        if self.rho_f is None:
            self.rho_f = props['density']
        if self.a is None:
            self.a = regression['a']
        if self.n is None:
            self.n = regression['n']
        if self.T_c is None:
            self.T_c = props['combustion_temp']
        if self.R is None:
            self.R = props['gas_constant']
        
    def _resolve_chamber_material(self, name):
        """Malzeme adını doğrular; tanınmıyorsa 4130'a düşer ve UYARIR.

        Sessiz yedeğe düşmek yasak: kullanıcı Inconel seçip çelik sonucu
        görürse bunu fark etmesinin hiçbir yolu olmaz.
        """
        from hrma.data.materials_db import get_material
        aday = str(name or '').strip() or 'steel_4130'
        try:
            get_material(aday)
            return aday
        except (KeyError, ValueError):
            self.design_warnings.append(_w(
                'warn.hybrid.chamber_material_unknown', 'warning',
                requested=aday, used='steel_4130'))
            return 'steel_4130'

    def _resolve_wall_thickness(self, value):
        """Cidar kalınlığını [m] doğrular; aralık dışıysa 5 mm'ye düşer."""
        try:
            t = float(value)
        except (TypeError, ValueError):
            t = 0.005
        if not (WALL_THICKNESS_INPUT_MIN_M <= t <= WALL_THICKNESS_MAX_M):
            self.design_warnings.append(_w(
                'warn.hybrid.wall_thickness_out_of_range', 'warning',
                requested_mm=round(t * 1000.0, 3),
                min_mm=WALL_THICKNESS_INPUT_MIN_M * 1000.0,
                max_mm=WALL_THICKNESS_MAX_M * 1000.0))
            return 0.005
        return t

    def _resolve_cooling_type(self, value):
        """Arayüzün kanal seçimini ısı transferi soğutma tipine çevirir.

        Kanal seçildiğinde film katsayısının literatürden alındığını ve
        soğutucu debisinin doğrulanmadığını AÇIKÇA bildirir.
        """
        ham = str(value or 'none').strip().lower()
        tip = COOLING_CHANNEL_TO_TYPE.get(ham)
        if tip is None:
            self.design_warnings.append(_w(
                'warn.hybrid.cooling_type_unknown', 'warning',
                requested=ham, used='natural'))
            return 'natural'
        if tip == 'regenerative':
            self.design_warnings.append(_w(
                'warn.hybrid.cooling_channels_assumed', 'warning',
                geometry=ham, h_coolant=20000))
        return tip

    def _resolve_safety_factor(self, value):
        """Tasarım emniyet katsayısını doğrular; aralık dışıysa UYARIR.

        None döndürmek 'kullanıcı vermedi' demektir; o durumda yapısal modül
        eski davranışını (malzeme kaydındaki değer) sürdürür. Bilinçli bir
        varsayılan enjekte edilmez ki kullanıcının girdiği ile motorun
        varsaydığı ayrılabilsin.
        """
        if value is None or value == '':
            return None
        try:
            sf = float(value)
        except (TypeError, ValueError):
            self.design_warnings.append(_w(
                'warn.hybrid.safety_factor_invalid', 'warning',
                requested=str(value)))
            return None
        if not (SAFETY_FACTOR_MIN <= sf <= SAFETY_FACTOR_MAX):
            self.design_warnings.append(_w(
                'warn.hybrid.safety_factor_out_of_range', 'warning',
                requested=round(sf, 3),
                min_value=SAFETY_FACTOR_MIN, max_value=SAFETY_FACTOR_MAX))
            return None
        return sf

    def _resolve_ambient_temperature(self, value):
        """Ortam sıcaklığını [K] doğrular; geçersizse None döner.

        None = 'kullanıcı vermedi'. O durumda ısı transferi modülünün kendi
        varsayılanı kullanılır ve AYNI değer yapısal modüle geri okunur —
        iki modülün farklı ortam sıcaklığı varsayması bu sürümde kapatılan
        kusur sınıfıdır (ölçüldü: ısı 293,15 K, yapısal 300,0 K).
        """
        if value is None or value == '':
            return None
        try:
            T = float(value)
        except (TypeError, ValueError):
            self._defaults_used.append(f'ambient_temperature(invalid:{value!r})')
            return None
        # Fiziksel zarf: Dünya yüzeyi çalışma bandının cömert bir üst kümesi
        # (Vostok -89 °C ... Ölüm Vadisi +57 °C). Dışı birim karışıklığının
        # işaretidir (kullanıcı °C girmiş olabilir).
        if not (180.0 <= T <= 340.0):
            self._defaults_used.append(
                f'ambient_temperature(out_of_range:{T:.2f}K)')
            return None
        return T

    def _resolve_plate_thickness(self, value):
        """Enjektör plaka kalınlığını [m] doğrular; geçersizse None döner."""
        if value is None or value == '':
            return None
        try:
            t = float(value)
        except (TypeError, ValueError):
            self._defaults_used.append(f'plate_thickness(invalid:{value!r})')
            return None
        if not (0.0002 <= t <= 0.1):   # 0,2 mm - 100 mm
            self._defaults_used.append(
                f'plate_thickness(out_of_range:{t * 1000.0:.3f}mm)')
            return None
        return t

    def _resolve_orifice_inlet(self, value):
        """Orifis giriş tipini ('sharp'/'radiused') doğrular; yoksa None."""
        if value is None or value == '':
            return None
        aday = str(value).strip().lower()
        if aday in ('sharp', 'radiused'):
            return aday
        self._defaults_used.append(f'orifice_inlet(unknown:{aday})')
        return None

    def _resolve_chamber_length_override(self, value):
        """Kullanıcının kamara boyu ezmesini [m] doğrular.

        Geometrik tutarlılık (override >= L_grain + L_pre) burada
        BİLİNEMEZ — grain daha hesaplanmamıştır. Bu yüzden burada yalnız
        işaret/birim kontrolü yapılır; geometrik kapı geometri kurulduktan
        sonra _apply_chamber_length_override'da uygulanır.
        """
        if value is None or value == '':
            return None
        try:
            L = float(value)
        except (TypeError, ValueError):
            self.design_warnings.append(_w(
                'warn.hybrid.chamber_length_override_invalid', 'warning',
                requested=str(value)))
            return None
        if L <= 0:
            return None  # 0/boş = otomatik (L* ile türet) — uyarı gerekmez
        if L > 20.0:
            # 20 m üstü bu sınıf motorda birim karışıklığının işareti
            # (kullanıcı mm yerine m girmiş olabilir).
            self.design_warnings.append(_w(
                'warn.hybrid.chamber_length_override_out_of_range', 'warning',
                requested_m=round(L, 3), max_m=20.0))
            return None
        return L

    def _resolve_nozzle_material(self, name):
        """Lüle/boğaz malzemesini doğrular; tanınmıyorsa grafite düşer + UYARIR.

        None döndürmez: lüle termal değerlendirmesi her koşuda yapılır.
        Grafit varsayılanı seçilirken bunun bir VARSAYIM olduğu
        _defaults_used ile işaretlenir.
        """
        from hrma.data.materials_db import get_material
        if name is None or str(name).strip() == '':
            self._defaults_used.append('nozzle_material')
            return 'graphite'
        aday = str(name).strip().lower().replace(' ', '_')
        try:
            get_material(aday)
            return aday
        except (KeyError, ValueError):
            self.design_warnings.append(_w(
                'warn.hybrid.nozzle_material_unknown', 'warning',
                requested=aday, used='graphite'))
            return 'graphite'

    def _kinetic_efficiency(self, combustion_results):
        """(η_kinetik, teşhis) — sonlu-hız kimyası (rekombinasyon) kaybı.

        v2.6.26 — ÇAPRAZ-MOTOR TUTARSIZLIĞI KAPATILDI. Aynı fiziksel kayıp
        SIVI motorda gerçekten hesaplanıyordu
        (``liquid_rocket_engine._kinetic_efficiency`` ->
        ``hrma.analysis.kinetic_efficiency.KineticEfficiency``), hibritte ise
        ``design_nozzle`` imza varsayılanı olan SABİT 0,995 geçiyordu — 18/18
        koşuda hiç değişmedi. Oysa modelin iki girdisi (donmuş ve kayan denge
        Isp'si) hibritin kendi yanma çözümünde ZATEN üretiliyor
        (``combustion_analysis`` performance.isp_frozen / isp_shifting).

        Gerçek lüle akışı donmuş (ODF) ile kayan denge (ODE) arasındadır;
        harman kesri Damköhler benzeri bir parametreden gelir (oda kalış
        süresi t_res = L*·ρ_c·c*/P_c, Sutton & Biblarz 9. baskı Eş. 8-9;
        üç-cisimli rekombinasyon zamanı ∝ P^-2, Bray 1959). Buradaki hiçbir
        katsayı bu görevde ayarlanmadı — modül bu görevden ÖNCE yazılmış ve
        kaynaklandırılmıştır.

        Donmuş/kayan çift çözülemezse η = 1,0 ve 'not_modelled' döner:
        uydurma bir kayıp uygulanmaz (sıvı yolun sözleşmesiyle aynı).
        """
        perf = (combustion_results or {}).get('performance') or {}
        isp_frozen = perf.get('isp_frozen')
        isp_shifting = perf.get('isp_shifting')
        if (not isp_frozen or not isp_shifting
                or isp_frozen >= isp_shifting):
            return 1.0, {
                'model': 'not_modelled',
                'note': ('frozen/shifting expansion pair unavailable; the '
                         'finite-rate (kinetic) loss is not resolved and no '
                         'loss is applied.')}
        try:
            from hrma.analysis.kinetic_efficiency import KineticEfficiency
            res = KineticEfficiency().evaluate(
                combustion_results=combustion_results,
                fidelity='engineering',
                chamber_pressure=float(self.P_c),
                characteristic_length=float(self.L_star),
                throat_diameter=float(getattr(self, 'd_t', 0.0)) or None)
            eta = float(res['isp_predicted']) / float(isp_shifting)
        except Exception as exc:  # korelasyon kurulamadı -> kayıp uygulanmaz
            return 1.0, {'model': 'not_modelled',
                         'note': f'kinetic correlation unavailable ({exc})'}
        return eta, {
            'model': 'kinetic_efficiency (engineering, JANNAF-style blend)',
            'isp_shifting_s': float(isp_shifting),
            'isp_frozen_s': float(isp_frozen),
            'isp_predicted_s': float(res['isp_predicted']),
            'kinetic_loss_pct': float(res['kinetic_loss_pct']),
            'loss_band_pct': list(res['loss_band_pct']),
            'damkohler': res['diagnostics'].get('damkohler'),
            'note': res['model_note'],
        }

    def _analyze_nozzle_material(self, heat_transfer_results=None):
        """Seçilen lüle/boğaz malzemesinin termal ve erozyon değerlendirmesi.

        v2.6.26 — arayüzdeki 'Nozzle Material' seçicisi bu sürüme kadar
        hiçbir hesaba girmiyordu (grafit / tungsten / bakır seçmek hiçbir
        çıktıyı değiştirmiyordu). Bu fonksiyon o alanı iki gerçek çıktıya
        bağlar:

        1) **Boğaz cidar sıcaklığı ve malzeme sınırı.** Bartz tabanlı eksenel
           profil BOĞAZ istasyonunda çözülür; profil LÜLE malzemesiyle
           koşulur (kamara malzemesiyle değil — ikisi farklı parçadır).
           Soğutma varsayımı arayüzün kendi beyanından gelir
           (NOZZLE_MATERIAL_COOLING; "Copper (Regeneratively Cooled)").
           Denge cidar sıcaklığı malzemenin izin verilen sıcaklığıyla
           karşılaştırılır.

        2) **Erozyon.** Yayımlanmış katsayı bandı OLAN malzemeler için
           (grafit, C-C) ThroatErosionModel ile gerileme hızı ve yanma
           süresince toplam boğaz büyümesi hesaplanır. Bandı olmayan
           malzemede (tungsten) katsayı UYDURULMAZ; 'no published data'
           denir. Soğutmasız metal boğaz için modelin geçerli olmadığı
           açıkça bildirilir.

        Ölçüm gerekçesi: aynı motorda grafit 2971 K denge sıcaklığında
        3300 K sınırının altında kalırken tungsten (2473 K) ve soğutmasız
        bakır (1000 K) sınırı aşar — yani seçim sonucu gerçekten değiştirir.
        """
        from hrma.data.materials_db import get_material

        material = self.nozzle_material
        cooling = NOZZLE_MATERIAL_COOLING.get(material)
        if cooling is None:
            # Tabloda yoksa soğutmasız kabul edilir (konservatif) ve bu
            # varsayım raporda görünür.
            cooling = 'natural'
        try:
            mat = get_material(material)
        except (KeyError, ValueError):
            return {'status': 'not_analyzed',
                    'reason': f"material '{material}' not in materials_db"}

        result = {
            'status': 'analyzed',
            'material': material,
            'material_name': mat.get('name', material),
            'cooling_assumption': cooling,
            'cooling_assumption_basis': (
                'regeneratively cooled (declared by the material selection)'
                if cooling == 'regenerative'
                else 'uncooled heat-sink / radiation-cooled throat'),
            'wall_thickness_mm': self.wall_thickness * 1000.0,
            'wall_thickness_basis': (
                'chamber wall thickness input (no separate nozzle wall '
                'thickness field exists)'),
            'warnings': [],
        }

        # --- 1. Boğaz termal durumu -----------------------------------------
        try:
            profile = self.heat_transfer_analyzer.analyze_axial_profile(
                {
                    'chamber_pressure': self.P_c,
                    'chamber_temperature': self.T_c,
                    'chamber_diameter': self.D_ch,
                    'chamber_length': self.L,
                    'burn_time': self.t_b,
                    'mdot_total': self.mdot_total,
                    'throat_diameter': self.d_t,
                    'nozzle_type': self.nozzle_type,
                },
                n_stations=NOZZLE_THERMAL_STATIONS,
                material=material,
                wall_thickness=self.wall_thickness,
                cooling_type=cooling,
            )
            i = int(profile['throat_index'])
            t_wall = float(profile['T_wall_eq'][i])
            q_throat = float(profile['q_MW'][i])
            t_recovery = float(profile['T_recovery'][i])
        except Exception as exc:  # profil çözülemezse sessiz kalınmaz
            self._fallback_used.append('nozzle_thermal_profile')
            result['throat_thermal'] = {
                'status': 'not_analyzed',
                'reason': f'axial thermal profile failed: {exc}'}
        else:
            allowable = mat.get('allowable_temperature')
            if allowable is None:
                allowable = mat.get('max_service_temp')
            thermal = {
                'status': 'analyzed',
                'throat_wall_temperature_K': t_wall,
                'gas_recovery_temperature_K': t_recovery,
                'throat_heat_flux_MW_m2': q_throat,
                'allowable_temperature_K': (float(allowable)
                                            if allowable else None),
            }
            if allowable:
                allowable = float(allowable)
                thermal['temperature_margin_K'] = allowable - t_wall
                thermal['utilization'] = (t_wall / allowable
                                         if allowable > 0 else None)
                thermal['verdict'] = ('SAFE' if t_wall <= allowable
                                      else 'EXCEEDS_ALLOWABLE')
                if t_wall > allowable:
                    result['warnings'].append(_w(
                        'warn.hybrid.nozzle_material_over_temp', 'critical',
                        material=result['material_name'],
                        wall_K=round(t_wall),
                        allowable_K=round(allowable),
                        cooling=cooling))
            else:
                thermal['verdict'] = 'NOT_EVALUATED'
                thermal['reason'] = (
                    'no allowable temperature in the material record')
            result['throat_thermal'] = thermal

        # --- 2. Erozyon ------------------------------------------------------
        from hrma.analysis.transient_ballistics import ThroatErosionModel
        try:
            model = ThroatErosionModel.for_material(material)
        except ValueError as exc:
            # Yayımlanmış bant yok (tungsten) veya soğutmasız metal için
            # model geçersiz (çelik/bakır). Katsayı UYDURULMAZ.
            result['erosion'] = {
                'status': 'no_published_data',
                'reason': str(exc),
                'assumption': 'rigid throat (no erosion applied)',
            }
        else:
            rate_mm_s = model.rate_mm_s(self.P_c)
            recession_mm = rate_mm_s * self.t_b
            r0 = self.d_t / 2.0
            r1 = r0 + recession_mm / 1000.0
            area_growth = (r1 / r0) ** 2 - 1.0 if r0 > 0 else 0.0
            result['erosion'] = {
                'status': 'analyzed',
                'radial_recession_rate_mm_s': rate_mm_s,
                'total_radial_recession_mm': recession_mm,
                'throat_diameter_initial_mm': self.d_t * 1000.0,
                'throat_diameter_final_mm': 2.0 * r1 * 1000.0,
                'throat_area_growth_fraction': area_growth,
                'coupled_to_performance': False,
                'coupling_note': (
                    'Reported only; the steady-state performance solution '
                    'assumes a rigid throat. Use the transient solver for '
                    'erosion-coupled thrust and pressure histories.'),
                'model': model.describe(),
            }
            if model.warnings:
                result['erosion']['material_warnings'] = list(model.warnings)
        return result

    def _apply_chamber_length_override(self, L_auto, L_grain, L_pre):
        """Kamara boyu ezmesini geometrik kapıdan geçirerek uygular.

        Döndürür: (L_kullanılan, L_post_kullanılan). Ezme yoksa otomatik
        değerler aynen döner.

        Fiziksel alt sınır L_grain + L_pre'dir: yakıt grain'i ve ön-yanma
        odası kamaranın İÇİNDE olmak zorundadır. Altında bir değer verilirse
        sessizce kırpmak yerine ezme REDDEDİLİR ve neden söylenir — çünkü
        kırpılmış bir değer kullanıcının girdiğinden farklı bir motor demektir
        ve kullanıcı bunu ekranda göremez.
        """
        if self.chamber_length_override is None:
            return L_auto, L_auto - L_grain - L_pre
        L_user = self.chamber_length_override
        L_min = L_grain + L_pre
        if L_user < L_min:
            self.design_warnings.append(_w(
                'warn.hybrid.chamber_length_override_too_short', 'warning',
                requested_mm=round(L_user * 1000.0, 1),
                min_mm=round(L_min * 1000.0, 1),
                grain_mm=round(L_grain * 1000.0, 1),
                pre_mm=round(L_pre * 1000.0, 1)))
            return L_auto, L_auto - L_grain - L_pre
        # Ezme kabul edildi: art-yanma odası kalan boydan gelir.
        return L_user, L_user - L_grain - L_pre

    def calculate(self):
        # Calculate characteristic velocity
        self.C_star = self._calculate_c_star()
        
        # Calculate expansion ratio if not provided
        if self.epsilon is None:
            self.epsilon = self._calculate_expansion_ratio()
        
        # Calculate thrust coefficient if not provided
        if self.CF is None:
            self.CF = self._calculate_thrust_coefficient()
        
        # Calculate specific impulse FIRST (before mass flow)
        self.Isp = self.CF * self.C_star / self.g0
        
        # Calculate mass flow rates using correct rocket equation
        # F = mdot * g0 * Isp => mdot = F / (g0 * Isp)
        self.mdot_total = self.F / (self.g0 * self.Isp)
        
        # Split mass flow between oxidizer and fuel
        self.mdot_ox = self.mdot_total * self.OF / (1 + self.OF)
        self.mdot_f = self.mdot_total / (1 + self.OF)
        
        # Calculate throat geometry using correct formula
        # At = mdot * C* / (Pc * CD) where CD is discharge coefficient
        CD = 0.98  # Typical discharge coefficient
        self.At = self.mdot_total * self.C_star / (self.P_c * 1e5 * CD)  # m²
        self.d_t = 2 * np.sqrt(self.At / np.pi)
        
        # Calculate exit geometry
        self.Ae = self.At * self.epsilon
        self.d_e = 2 * np.sqrt(self.Ae / np.pi)
        
        # Calculate chamber volume
        self.V_c = self.L_star * self.At
        
        # Design fuel grain
        self._design_fuel_grain()
        
        # Calculate chamber dimensions
        if self.chamber_diameter_input > 0:
            self.D_ch = self.chamber_diameter_input
        else:
            # N portlu grain'de kamara, N portun TOPLAM alanını sarmalıdır:
            # eşdeğer port çapı sqrt(N)·D_tek (F046).
            self.D_ch = self.D_port_final * np.sqrt(self.port_count) * 1.5
        # v2.5.2 (Codex bulgusu hybrid:827) — SON kapı: grain portu sarmalı.
        # Yüklenen yakıt kütlesi (π/4)·(D_ch² − D_port_ilk²)·L_grain ile
        # hesaplandığından D_ch <= D_port_ilk durumunda NEGATİF kütle çıkar.
        # Time-marching girişindeki doğrulama bunu zaten reddeder; burası
        # kullanıcı kamara çapı vermeyip portun beklenmedik biçimde büyüdüğü
        # yolları da kapatır. Sessiz kırpma YOK — açık hata.
        if self.D_ch <= self.D_port_initial:
            raise ValueError(
                f"Chamber diameter {self.D_ch * 1000:.1f} mm is not larger "
                f"than the initial port diameter "
                f"{self.D_port_initial * 1000:.1f} mm; the fuel grain would "
                f"have negative volume. Increase the chamber diameter or "
                f"reduce the port diameter / oxidizer mass flux."
            )
        # --- Kamara boyu (v2.5.2 L* modeli) ---
        # ESKİ MODEL: L = max(4·V_c/(π·D_ch²), L_grain). Hibritte grain boyu
        # neredeyse her zaman baskın olduğundan max(...) daima L_grain'i
        # seçiyor ve L* girdisi geometriyi HİÇ değiştirmiyordu (kullanıcı
        # şikayeti: "L* geometriyi değiştirmiyor").
        #
        # YENİ MODEL — hibrit kamara üç bölümden oluşur:
        #     L = L_grain + L_pre + L_post
        #   L_pre  : ön-yanma odası (pre-combustion chamber). Enjektör
        #            püskürtmesinin gelişmesi ve akışın düzelmesi için
        #            standart mühendislik ölçüsü ~0.5·D_ch.
        #   L_post : art-yanma odası (post-combustion chamber). Karışmamış
        #            yakıt/oksitleyicinin yanmasını tamamlaması için gereken
        #            EK hacimden gelir: L* karakteristik boyu toplam kamara
        #            hacmini (V_c = L*·At) belirler; portun içerdiği hacim
        #            düşülünce kalan hacim art-yanma odasına verilir.
        # Böylece L* ARTTIKÇA kamara boyu ölçülebilir biçimde artar.
        # Kaynak: Sutton & Biblarz 9. baskı Böl. 8/16; Chiaverini & Kuo,
        # "Fundamentals of Hybrid Rocket Combustion and Propulsion" (2007),
        # ön/art-yanma odası boyutlandırma pratiği.
        A_ch = np.pi / 4.0 * self.D_ch ** 2
        L_pre = PRE_CHAMBER_D_FACTOR * self.D_ch
        D_port_avg = 0.5 * (self.D_port_initial + self.D_port_final)
        V_port_avg = np.pi / 4.0 * D_port_avg ** 2 * self.L_grain
        L_post_raw = (self.V_c - V_port_avg) / A_ch if A_ch > 0 else 0.0
        L_post = float(np.clip(L_post_raw,
                               POST_CHAMBER_D_FACTOR_MIN * self.D_ch,
                               POST_CHAMBER_D_FACTOR_MAX * self.D_ch))
        L_auto = self.L_grain + L_pre + L_post
        # v2.6.26: "Chamber Length Override (mm)" alanı bu sürüme kadar
        # tamamen ölüydü (arayüzde vardı, hiçbir yere gitmiyordu). Artık
        # L* ile türetilen boyu ezer; geometrik alt sınır kapısı
        # _apply_chamber_length_override içinde.
        self.L, L_post = self._apply_chamber_length_override(
            L_auto, self.L_grain, L_pre)
        self.L_pre_chamber = L_pre
        self.L_post_chamber = L_post
        self.chamber_length_auto = L_auto
        # v2.6.26 — ETİKET ÜÇÜNCÜ DURUMU DA SÖYLÜYOR.
        # Eskiden yalnız iki değer vardı ve ezme yoksa her koşuda
        # 'l_star_derived' yazıyordu. Oysa hibritte port hacmi çoğu zaman
        # istenen L*'ın gerektirdiği hacmi TEK BAŞINA aşar; o durumda art-yanma
        # odası geometrik alt sınıra kelepçelenir ve kamara boyu fiilen
        # GRAIN UZUNLUĞUNDAN gelir, L*'tan değil. Ölçüldü: varsayılan koşuda
        # L_post/D_ch tam 0,3000 (alt sınırın kendisi) çıkarken etiket hâlâ
        # "L* ile türetildi" diyordu. l_star_note bu durumu zaten dürüstçe
        # anlatıyordu ama makinece okunan alan yanlış cevap veriyordu.
        if abs(self.L - L_auto) > 1e-9:
            self.chamber_length_source = 'user_override'
        elif abs(L_post - POST_CHAMBER_D_FACTOR_MIN * self.D_ch) < 1e-9:
            self.chamber_length_source = 'grain_limited'
        elif abs(L_post - POST_CHAMBER_D_FACTOR_MAX * self.D_ch) < 1e-9:
            self.chamber_length_source = 'post_chamber_clamped_high'
        else:
            self.chamber_length_source = 'l_star_derived'

        # GERÇEKLEŞEN L*: hibritte port hacmi tek başına büyük olduğundan
        # istenen L* çoğu zaman geometrik alt sınırın ALTINDA kalır; bu
        # durumda kamara küçültülemez ve gerçekleşen L* istenenden büyüktür.
        # Sessiz kalmak yerine dürüstçe raporlanır (kullanıcı "L* hiçbir şeyi
        # değiştirmiyor" derken tam olarak bu kelepçeyi görüyordu).
        V_chamber_actual = V_port_avg + (L_pre + L_post) * A_ch
        self.V_c_actual = V_chamber_actual
        self.L_star_achieved = (V_chamber_actual / self.At
                                if self.At > 0 else self.L_star)
        # Not: bu durum hibritlerde KURALDIR (port hacmi büyüktür), bu yüzden
        # her koşuda uyarı üretmek gürültü olur; bilgi sonuç sözlüğüne not
        # olarak konur ve arayüz gösterir.
        if self.L_star_achieved > self.L_star * 1.02:
            self.l_star_note = (
                f"Requested L* = {self.L_star:.2f} m is below the volume the "
                f"grain port geometry already provides; achieved L* is "
                f"{self.L_star_achieved:.2f} m. Increase L* above that value "
                f"to lengthen the post-combustion chamber."
            )
        else:
            self.l_star_note = ''

        # Calculate propellant masses
        self.m_ox = self.mdot_ox * self.t_b
        # Yakıt kütlesi grain geometrisinden (denetim bulgusu #6):
        # m_f = rho_f · (π/4) · (D_final² − D_initial²) · L_grain.
        # Eski mdot_f·t_b değeri grain'in fiilen ürettiği kütleyle
        # eşitlenmiyordu (3-4 kat tutarsızlık).
        self.m_f = self.m_f_grain
        self.m_total = self.m_ox + self.m_f
        # OPUS DENETİM DÜZELTMESİ (major): m_f YANAN yakıttır; grain dış
        # çapı kamara iç çapına kadar döküldüğünden YÜKLENEN yakıt daha
        # büyüktür (yanmayan sliver kalır). İkisi ayrı raporlanır ki araç
        # kütle bütçesi (yüklenen) ile performans bütçesi (yanan)
        # karıştırılmasın.
        r_grain_outer = self.D_ch / 2.0
        self.m_f_loaded = self.rho_f * np.pi / 4.0 * (
            (2.0 * r_grain_outer) ** 2 - self.D_port_initial ** 2
        ) * self.L_grain
        self.fuel_sliver_fraction = max(
            0.0, 1.0 - self.m_f / max(self.m_f_loaded, 1e-9))
        
        # Advanced combustion analysis with Cantera (kendi yanma çözücümüz)
        fuel_composition = {self.fuel_type: 100.0}  # Simplified for now
        ox = getattr(self, 'oxidizer_type', None) or 'N2O'
        # v2.6.26 — GENİŞLEME ORANI ARTIK GEÇİRİLİYOR.
        # `analyze_combustion` bu argümanı ZATEN destekliyordu; verilmediğinde
        # çıkış basıncını ISA deniz seviyesine (1,01325 bar) çapalıyor ve bunu
        # `exit_pressure_basis: 'sea_level_default'` ile dürüstçe bildiriyor.
        # Ama hibrit çağrısı hiç göndermediği için "İrtifa Performansı" paneli
        # her zaman "deniz seviyesinde tam genişlemiş nozul" varsayıyordu:
        # ölçüldü, ε 2/4/8/16 süpürüldüğünde sea_level_isp ve vacuum_isp 15
        # hane boyunca SABİT kaldı (191,976 / 211,809 s) ve ε=16'da motor
        # paneli Isp 125,8 s derken irtifa paneli 192,0 s gösteriyordu (%53).
        # Kullanıcı nozul genişlemesini büyütüp irtifa kazancını göremiyordu.
        combustion_results = self.combustion_analyzer.analyze_combustion(
            fuel_composition, ox, self.OF, self.P_c, None,
            eta_c_star=self.eta_c_star,
            expansion_ratio=self.epsilon
        )

        # Gerçek termodinamik değerler CombustionAnalyzer denge çözümünden alınır.
        # DİKKAT: gamma/MW/sıcaklık 'compositions'->'chamber' altındadır
        # ('conditions'->'chamber' yalnızca {'P','T'} içerir; eski kod yanlış
        # anahtara baktığı için bu güncelleme hiç çalışmıyordu).
        if 'compositions' in combustion_results and 'chamber' in combustion_results['compositions']:
            chamber_data = combustion_results['compositions']['chamber']
            if 'gamma' in chamber_data:
                self.gamma = chamber_data['gamma']  # shifting-equilibrium isentropik üs
            if 'molecular_weight' in chamber_data:
                self.R = self.combustion_analyzer.R_universal / chamber_data['molecular_weight']
            if 'temperature' in chamber_data:
                self.T_c = chamber_data['temperature']  # HP dengesinden alev sıcaklığı
        
        # Advanced nozzle design — gerçek yanma değerlerini (gamma, R, T_c)
        # geçir; aksi halde design_nozzle eski hardcoded 1.25/300/3000'e düşer
        # ve CF/Isp motorun geri kalanıyla tutarsız olur (entegrasyon gap fix).
        # v2.6.26 — İKİ ÖLÇÜLMÜŞ KOPUKLUK burada kapatıldı:
        #
        # 1) contraction_area_ratio geçirilmiyordu: lüle tasarımcısı kendi
        #    varsayılanına (A_c/A_t = 2.25) düşüyor, kullanıcının daralma
        #    oranı yakınsak kontura hiç ulaşmıyordu. Aynı yanıtta iki farklı
        #    daralma oranı görünüyordu.
        # 2) wall_material geçirilmiyordu: cidar kalınlığı/kütlesi ne seçilirse
        #    seçilsin ÇELİKTEN (7850 kg/m³, 250 MPa) hesaplanıyordu. Kullanıcı
        #    tungsten seçtiğinde sonuçta 'nozzle_material: tungsten' yazarken
        #    lüle kütlesi çelik yoğunluğundan çıkıyordu. nozzle_design.py:730
        #    bu hatayı kendi yorumunda tarif etmiş ama çağıran düzeltilmemişti.
        #
        # 3) (v2.6.26, ikinci tur) wall_safety_factor ve kinetic_efficiency
        #    geçirilmiyordu:
        #    - Lüle cidarı DAİMA malzeme kaydının kendi emniyet katsayısıyla
        #      (çelikte 4,0) boyutlanıyordu; kullanıcının 'Safety Factor'
        #      girdisi hazne cidarına uygulanırken lüleye hiç ulaşmıyordu.
        #      ÖLÇÜLDÜ: safety_factor=2,0 ile wall_safety_factor 4,0 kaldı.
        #    - Kinetik (sonlu-hız kimyası) verimi imza varsayılanı 0,995'te
        #      sabitti; oysa AYNI büyüklük sıvı motorda gerçekten hesaplanıyor
        #      (liquid_rocket_engine._kinetic_efficiency -> KineticEfficiency).
        _cr, _ = self._resolve_contraction_ratio()
        eta_kin, kin_diag = self._kinetic_efficiency(combustion_results)
        nozzle_results = self.nozzle_designer.design_nozzle(
            self.At, self.epsilon, self.P_c, self.P_a, self.nozzle_type,
            gamma=self.gamma, R_specific=self.R, T_chamber=self.T_c,
            contraction_area_ratio=_cr,
            wall_material=getattr(self, 'nozzle_material', None),
            wall_safety_factor=self.design_safety_factor,
            kinetic_efficiency=eta_kin,
        )
        # Kinetik verimin NEREDEN geldiği çıktıda taşınır (sıvı motordaki
        # 'kinetic' teşhis bloğuyla aynı sözleşme). Çözülemediğinde eta=1,0
        # ve 'not_modelled' denir — sessizce 0,995 uydurulmaz.
        try:
            nozzle_results['performance']['kinetic'] = kin_diag
        except (KeyError, TypeError):
            pass
        
        # Altitude performance — uq_mode'da atlanır (danışma tablosu; ana
        # çıktıları beslemez, MC örneğinde gereksiz maliyet — ARGE spec 6.2)
        altitude_performance = None
        if not self.uq_mode:
            altitudes = [0, 1000, 5000, 10000, 15000, 20000]  # m
            altitude_performance = self.combustion_analyzer.calculate_altitude_performance(
                {
                    'chamber_pressure': self.P_c,
                    'gas_constants': combustion_results['performance']['gas_constants'],
                    'conditions': combustion_results['conditions'],
                    'performance': combustion_results['performance'],
                    'gamma_avg': combustion_results['performance']['gamma_avg'],
                    'mdot_total': self.mdot_total
                },
                altitudes
            )

        # Optimum O/F ratio — oksitleyiciyi 'ox' (self.oxidizer_type) ile geçir
        # (denetim bulgusu #294). Eski 'N2O' sabiti LOX/H2O2 motorlarında yanlış
        # kimya/stokiyometri kullanıp optimum O/F'yi ve max Isp'yi kaydırıyordu
        # (HTPB stok. O/F: N2O~7-8, LOX~2). combustion analyzer adı .lower() ile
        # normalize ettiğinden n2o motorlarında sonuç değişmez (test güvenli).
        # uq_mode'da bu DANIŞMA amaçlı arama atlanır (profilde tek hesabın
        # ~%70'i); nominal koşudan enjekte edilen sonuç varsa o kullanılır.
        if self.uq_mode:
            optimum_of = self._precomputed_optimum_of
        else:
            # v2.6.26 — GENİŞLEME ORANI OPTİMUM O/F ARAMASINA DA GEÇİYOR.
            # Ana çağrı (yukarıda) ε'yi alıyordu ama bu arama almıyordu:
            # her O/F noktası çıkış istasyonunu ISA deniz seviyesine
            # çapalıyor, dolayısıyla ε=16 seçen kullanıcının optimum O/F
            # tablosu hâlâ ε≈1 koşullarında hesaplanıyordu. ÖLÇÜLDÜ
            # (HTPB/N2O, Pc=20 bar): ε yokken O/F* = 6,845 ve çıkış basıncı
            # 1,01325 bar SABİT; ε=4 -> O/F* = 6,661 / 0,9567 bar;
            # ε=16 -> O/F* = 7,841 / 0,1613 bar. Aynı yanıtta iki çelişkili
            # genişleme varsayımı vardı.
            optimum_of = self.combustion_analyzer.find_optimum_of_ratio(
                fuel_composition, ox, self.P_c,
                expansion_ratio=self.epsilon
            )

        # Total impulse to thrust at altitudes — uq_mode'da atlanır (danışma)
        thrust_altitude_analysis = None
        if not self.uq_mode and hasattr(self, 'I_total') and self.I_total > 0:
            altitudes_thrust = [0, 1000, 5000, 10000, 15000, 20000]  # m
            thrust_altitude_analysis = self.combustion_analyzer.calculate_thrust_at_altitudes(
                self.I_total, {
                    'performance': combustion_results['performance'],
                    'conditions': combustion_results['conditions'],
                    'chamber_pressure': self.P_c,
                    'burn_time': self.t_b
                }, altitudes_thrust
            )
        
        # Isı transferi analizi
        #
        # v2.6.25 DÜZELTMESİ — ÜÇ KULLANICI GİRDİSİ BURAYA HİÇ ULAŞMIYORDU.
        # Bu çağrıda malzeme 'steel_4130', cidar 5 mm ve soğutma 'natural'
        # SABİT YAZILMIŞTI. Hibrit sayfasındaki "Chamber Material",
        # "Wall Thickness" ve "Include Cooling Channels" seçicileri
        # serileştirilip sunucuya gidiyor, ama termal model onları hiç
        # görmüyordu: kullanıcı Inconel 718 + 8 mm cidar + radyal kanal seçse
        # bile hesap 5 mm 4130 çelik ve soğutmasız yapılıyordu.
        #
        # Sonucu sessiz değildi, YANLIŞTI: soğutucu tarafı film katsayısı
        # doğal taşınımda 25 W/m²K'dır, yani ısıyı dışarı atacak yol yok
        # sayılır. Denge cidar sıcaklığı adyabatik alev sıcaklığına yapışıyor
        # (warn.thermal.wall_pinned_adiabatic) ve GERÇEKÇİ HER TASARIM
        # "cidar eriyor" kritiği veriyordu. Kullanıcı soğutma ekleyerek bunu
        # düzeltmeye çalıştığında ekranda hiçbir şey değişmiyordu.
        #
        # Not: arayüzün 'steel_304' değeri materials_db'de yoktu (kayıt adı
        # 'ss_304'); takma ad v2.6.25'te eklendi, aksi hâlde varsayılan
        # malzeme seçimi burada çözülemezdi.
        # v2.6.26 — SÖZLEŞME BOŞLUĞU KAPATILDI. Bu çağrı yalnız altı anahtar
        # gönderiyordu; ısı modülü bulamadığı büyüklükleri KENDİ genel
        # varsayılanlarından türetiyordu ve motorun gerçek çözümüyle
        # çelişiyordu (ölçüldü, aynı koşu):
        #     c*     motor 1325,00 m/s  <-> ısı modülü 1251,38 m/s  (-%5,6)
        #     boğaz  motor   48,69 mm   <-> ısı modülü   46,85 mm   (-%3,8)
        #     gamma  motor    1,2378    <-> ısı modülü    1,20      (varsayılan)
        #     MW     motor   20,94 g/mol<-> ısı modülü   24,0       (varsayılan)
        # Bileşik Bartz etkisi ~%20 h_g sapması; ayrıca termal panelin
        # gösterdiği boğaz çapı nozul panelininkiyle çelişiyordu.
        # Aynı dosyadaki _analyze_nozzle_material çağrısı boğaz çapını ZATEN
        # doğru geçiriyordu — yani sözleşme bir çağrıda kurulu, diğerinde
        # atlanmıştı.
        ht_input = {
            'chamber_pressure': self.P_c,
            'chamber_temperature': self.T_c,
            'chamber_diameter': self.D_ch,
            'chamber_length': self.L,
            'burn_time': self.t_b,
            'mdot_total': self.mdot_total,
            'throat_diameter': self.d_t,
            'throat_area': self.At,
            'c_star': self.C_star,
            'gamma': self.gamma,
        }
        # Molekül ağırlığı: R spesifikten türetilir (M = R_evrensel/R).
        # Yoksa GÖNDERİLMEZ — ısı modülü kendi Bartz tahminine düşer ve bunu
        # kendi içinde beyan eder; buradan uydurma bir sayı geçirmek yasak.
        if getattr(self, 'R', None):
            ht_input['molecular_weight'] = 8314.462618 / self.R
        # v2.6.26 — ORTAM SICAKLIĞI TEK KAYNAK. Kullanıcı bir değer verdiyse
        # o geçirilir; vermediyse ısı modülünün KENDİ varsayılanı kullanılır
        # (buradan ikinci bir sayı uydurulmaz). Aşağıda yapısal modüle
        # geçirilen değer, ısı modülünün fiilen kullandığı sayıdan geri
        # okunur — eskiden burada 300,0 K SABİT yazılıydı ve tek motor
        # sonucunda iki farklı ortam sıcaklığı (293,15 K ısı / 300 K yapısal)
        # dolaşıyordu.
        ht_kwargs = {}
        if self.ambient_temperature is not None:
            ht_kwargs['ambient_temp'] = float(self.ambient_temperature)
        heat_transfer_results = self.heat_transfer_analyzer.analyze_heat_transfer(
            ht_input,
            material=self.chamber_material,
            wall_thickness=self.wall_thickness,
            cooling_type=self.cooling_type,
            **ht_kwargs
        )
        
        # Structural analysis — chamber_temperature GEÇİLMELİ; aksi halde
        # structural modülü ortam (300 K) varsayıp termal gerilme=0 ve
        # mukavemet deratingi=yok ile çalışır, emniyet faktörünü tehlikeli
        # şekilde yüksek gösterir (entegrasyon gap fix). Mümkünse ısı transferi
        # modülünün hesapladığı gerçek cidar sıcaklıklarını geçir; yoksa T_c'den
        # konservatif tahmin yapılır.
        # Ortam sıcaklığı ısı modülünün FİİLEN kullandığı değerden okunur
        # (tek kaynak; bkz. yukarıdaki not). Isı sonucu yoksa anahtar hiç
        # gönderilmez ve yapısal modül kendi varsayılanını beyan eder.
        ambient_used = None
        try:
            ambient_used = float(
                heat_transfer_results['design_parameters']['ambient_temperature'])
        except (KeyError, TypeError, ValueError):
            ambient_used = self.ambient_temperature
        struct_input = {
            'chamber_pressure': self.P_c,
            'chamber_temperature': self.T_c,
            'chamber_diameter': self.D_ch,
            'chamber_length': self.L,
            'throat_diameter': self.d_t,
            'nozzle_type': self.nozzle_type,
            'burn_time': self.t_b,
            # v2.6.26: EKSENEL İTKİ YÜKÜ. structural_analysis.py:523 burkulma
            # kontrolü için bunu `motor_data['thrust']` diye okuyor; anahtar
            # burada olmadığı için her motorda 0 N geliyordu. Sonuç: uygulanan
            # eksenel gerilme 0, burkulma emniyet katsayısı SONSUZ ve durum
            # DAİMA "SAFE" — yani NASA SP-8007 burkulma kontrolü fiilen
            # kapalıydı. İnce cidarlı uzun bir kamarada burkulma yöneten yük
            # olabilir; sessizce "güvenli" demek en tehlikeli yanlıştır.
            'thrust': self.F,
        }
        if ambient_used is not None:
            struct_input['ambient_temperature'] = float(ambient_used)
        # ISI -> YAPISAL ZİNCİR (Dalga 0, 2026-07-14): Isı analizinin
        # hesapladığı GERÇEK iç/dış cidar sıcaklıkları yapısal modüle
        # aktarılır. structural_analysis._estimate_wall_delta_T bu
        # anahtarları birinci öncelikle okur; verilmezse T_c'den hayali,
        # aşırı karamsar bir gradyan tahmini yapıyordu (iki modül aynı
        # motor için farklı cidar sıcaklığı varsayıyordu).
        try:
            wall = heat_transfer_results['wall_analysis']
            t_hot = float(wall['inner_temperature'])
            t_cold = float(wall['outer_temperature'])
            if np.isfinite(t_hot) and np.isfinite(t_cold) and t_hot > 0:
                struct_input['wall_temperature_hot'] = t_hot
                struct_input['wall_temperature_cold'] = max(t_cold, 0.0)
        except (KeyError, TypeError, ValueError):
            pass  # ısı sonucu yoksa eski konservatif T_c tahmini devrede kalır
        # v2.6.26 — İKİ KOPUKLUK BURADA KAPANDI:
        #
        # 1) material='steel_4130' SABİT yazılıydı. Kullanıcının seçtiği kamara
        #    malzemesi (v2.6.25'te termal modele bağlanmıştı) yapısal modüle
        #    hâlâ ULAŞMIYORDU: Inconel 718 seçen kullanıcının emniyet katsayısı
        #    4130 çeliğinden hesaplanıyordu. Termal ve yapısal modüller aynı
        #    motor için FARKLI malzeme varsayıyordu.
        #
        # 2) 'Safety Factor' ve gerçek cidar kalınlığı geçilmiyordu. Yapısal
        #    modül bu ikisini zaten destekliyor (design_safety_factor,
        #    actual_wall_thickness) ama çağrı onları vermediği için modül
        #    BOYUTLANDIRMA modunda kalıyordu; o modda raporlanan SF tanım
        #    gereği "hedef SF x imalat payı"dır, yani kullanıcının kendi
        #    girdisinin geri okunmasıdır (bkz. _analyze_chamber_wall F003
        #    yorumu). Gerçek cidar geçilince modül DOĞRULAMA moduna geçer ve
        #    SF gerçekten basınç, çap, malzeme ve kalınlıktan çıkar.
        structural_results = self.structural_analyzer.analyze_structure(
            struct_input,
            material=self.chamber_material,
            design_pressure_factor=1.5,
            design_safety_factor=self.design_safety_factor,
            # Yalnız kullanıcı GERÇEKTEN bir kalınlık verdiyse doğrulama modu.
            actual_wall_thickness=(self.wall_thickness
                                   if self.wall_thickness_user_supplied
                                   else None)
        )

        # Lüle/boğaz malzemesinin termal + erozyon değerlendirmesi (v2.6.26'da
        # bağlanan üçüncü ölü girdi).
        nozzle_material_results = self._analyze_nozzle_material(
            heat_transfer_results)

        return self._compile_results(combustion_results, nozzle_results,
                                   altitude_performance, optimum_of, thrust_altitude_analysis,
                                   heat_transfer_results, structural_results,
                                   nozzle_material_results)
    
    def _calculate_c_star(self):
        """Karakteristik hızı (c*) KENDİ yanma çözücümüzle hesaplar.

        Hibrit motor termokimyası CombustionAnalyzer (Cantera gri30 dengesi +
        shifting-equilibrium isentropik üs) ile çözülür. NASA CEA'ya BAĞLI
        DEĞİLDİR — kod kendi kimyasal dengesini kurar; CEA yalnızca bağımsız
        doğrulama referansıdır. Bu çözücünün c*'ı N2O/LOX/H2O2 ile HTPB,
        paraffin, PE, PMMA, ABS, PLA için NASA CEA'ya %0-1.5 içinde doğrulanmıştır
        (tasarım O/F bandı, Pc=20 bar). Eski sürüm RocketCEA'yı doğrudan çağırıp
        sonucu c* olarak alıyordu (CEA bağımlılığı) — bu kaldırıldı.
        """
        fuel_composition = {self.fuel_type: 100.0}
        ox = getattr(self, 'oxidizer_type', None) or 'n2o'

        # T_c=None geçilir ki CombustionAnalyzer adyabatik alev sıcaklığını
        # KENDİ HP dengesinden hesaplasın (sabit tablo değeri yerine).
        results = self.combustion_analyzer.analyze_combustion(
            fuel_composition, ox, self.OF, self.P_c, None
        )
        perf = results['performance']
        chamber = results['compositions']['chamber']

        # Gerçek denge değerlerini sınıfa aktar (shifting-eq. gamma, doğru T_c, MW)
        self.gamma = chamber['gamma']
        self.R = self.combustion_analyzer.R_universal / chamber['molecular_weight']
        self.T_c = chamber['temperature']

        c_star = perf['c_star']

        # c* validasyonu — oksitleyici-farkında fiziksel bant (v2.5.0 G4).
        # Eski tek bant (1000-1900) N2O-merkezliydi: GOX/LOX'ta meşru ~1830
        # değerler tavana dayanıyor, N2O'da 1700+ gerçek anomaliler kaçıyordu.
        band = C_STAR_PLAUSIBLE_BAND_MPS.get(str(ox).lower(),
                                             C_STAR_BAND_DEFAULT_MPS)
        if not (band[0] < c_star < band[1]):
            warnings.warn(
                f"Anormal c* değeri: {c_star:.0f} m/s "
                f"({ox} için beklenen bant {band[0]:.0f}-{band[1]:.0f} m/s)")

        # c* verimi (v2.5.0 UQ): teslim edilen c* = eta * c*_teorik. Teorik
        # değer ayrıca saklanır (raporlama). eta None ise davranış değişmez.
        self.C_star_theoretical = c_star
        if self.eta_c_star is not None:
            c_star = self.eta_c_star * c_star

        return c_star

    def _instantaneous_performance(self, of_ratio):
        """Anlık O/F'den anlık (c*, Isp) döndürür (denetim bulgusu #2).

        O/F kayması performansa yansıtılır: yanma çözücü her O/F için c*'ı
        verir; Isp ise mevcut CF (nozul geometrisi sabit) ile c*'tan ölçeklenir
        (Isp = CF · c* / g0). CF burada O/F ile küçük değiştiği için tasarım
        CF'si kullanılır — bu, c*'taki (çok daha büyük) O/F duyarlılığını
        yakalamak için yeterlidir ve nozul yeniden çözümünden kaçınır.

        O/F değerleri 0.05 çözünürlükte yuvarlanıp önbelleğe alınır
        (Cantera denge çözümünü her time-marching adımında tekrarlamamak için).
        """
        of_key = round(float(of_ratio) / 0.05) * 0.05
        if of_key in self._perf_cache:
            return self._perf_cache[of_key]

        try:
            fuel_composition = {self.fuel_type: 100.0}
            ox = getattr(self, 'oxidizer_type', None) or 'n2o'
            results = self.combustion_analyzer.analyze_combustion(
                fuel_composition, ox, max(of_key, 0.1), self.P_c, None
            )
            cstar_inst = results['performance']['c_star']
            # c* verimi tasarım noktasıyla tutarlı uygulanır (v2.5.0 UQ)
            if self.eta_c_star is not None:
                cstar_inst = self.eta_c_star * cstar_inst
        except Exception:
            cstar_inst = getattr(self, 'C_star', 1500.0)

        # CF tasarım değeri (calculate() önce CF'yi hesaplar); yoksa nominal.
        cf = getattr(self, 'CF', None)
        if cf is None or not np.isfinite(cf):
            cf = 1.5  # tipik hibrit deniz seviyesi CF (Sutton & Biblarz 9th ed.)
        isp_inst = cf * cstar_inst / self.g0
        self._perf_cache[of_key] = (cstar_inst, isp_inst)
        return cstar_inst, isp_inst
    
    def _calculate_expansion_ratio(self):
        """Calculate optimal expansion ratio using correct isentropic formula"""
        pressure_ratio = self.P_c / self.P_a  # Pc/Pe
        gamma = self.gamma
        
        # Correct isentropic formula: optimal expansion for Pe = Pa
        # Calculate Mach number from pressure ratio: Pc/Pe = [1 + (γ-1)/2 * Me²]^(γ/(γ-1))
        # Then area ratio: ε = (1/Me) * [(2/(γ+1)) * (1 + (γ-1)/2 * Me²)]^((γ+1)/(2*(γ-1)))
        
        # Iterative solution: find Mach number
        from scipy.optimize import fsolve
        
        def pressure_mach_relation(M):
            return (1 + (gamma - 1) / 2 * M**2)**(gamma / (gamma - 1)) - pressure_ratio
        
        # Initial guess: high Mach number
        M_exit_guess = np.sqrt(2 / (gamma - 1) * (pressure_ratio**((gamma - 1) / gamma) - 1))
        M_exit = fsolve(pressure_mach_relation, max(1.1, M_exit_guess))[0]
        
        # Calculate area ratio (correct isentropic formula)
        epsilon = (1 / M_exit) * ((2 / (gamma + 1)) * (1 + (gamma - 1) / 2 * M_exit**2))**((gamma + 1) / (2 * (gamma - 1)))
        
        # Eslenik (matched, Pe = Pa) genlesme orani oldugu gibi kullanilir
        # (denetim bulgusu #8): eski max(4, ...) tabani, Pc/Pa orani kucuk
        # motorlarda nozulu tasarim noktasinda asiri genlesmis hale getiriyordu.
        # Alt sinir yalnizca matematiksel gecerlilik icindir (suporsonik nozul
        # icin Ae/At > 1); ust sinir 250 vakum nozullari icin pratik limittir.
        # Kullanici epsilon verirse bu fonksiyon zaten cagrilmaz (calculate()).
        return max(1.01, min(epsilon, 250))
    
    def _calculate_thrust_coefficient(self, epsilon=None, chamber_pressure=None):
        """Calculate thrust coefficient using isentropic nozzle flow (Sutton Eq. 3-30).

        Exit Mach number is solved from the area-Mach relation via Brent's method,
        then Pe is computed from isentropic pressure relation.  The old code set
        Pe = Pa (perfect expansion) which zeroed out the pressure thrust term.

        v2.6.2 (bulgu F047): epsilon / chamber_pressure DIŞARIDAN verilebilir.
        Boğaz erozyonu At'yi büyüttüğünde geometri (Ae sabit) ε'yi ve kütle
        dengesi Pc'yi değiştirir; CF bu yeni noktada YENİDEN hesaplanmalıdır.
        Argüman verilmezse tasarım noktası (self.epsilon, self.P_c) kullanılır
        ve davranış birebir eskisiyle aynı kalır.
        """
        # Diverjans duzeltme faktorleri (hrma.constants'tan):
        #   bell      -> 0.985 (Rao optimize)
        #   parabolic -> 0.975
        #   conical   -> 0.983 (15 deg, (1+cos(15°))/2 = 0.98296)
        # Onceki kodda conical icin 0.955 yaziliyordu; bu 30 deg'lik kabaca bir
        # degerdi ve (1+cos(15°))/2 formuluyle uyumsuzdu. Sutton & Biblarz 9th ed.
        # Tablo 3-3 ile uyumlu olarak 0.983 kullanilir.
        if self.nozzle_type == 'bell':
            lambda_eff = LAMBDA_BELL
        elif self.nozzle_type == 'parabolic':
            lambda_eff = LAMBDA_PARABOLIC
        else:
            lambda_eff = LAMBDA_CONICAL_15DEG

        # Store for results output
        self.lambda_eff = lambda_eff

        gamma = self.gamma
        eps = self.epsilon if epsilon is None else float(epsilon)
        P_c = self.P_c if chamber_pressure is None else float(chamber_pressure)

        # --- Step 1: Solve exit Mach number from area-Mach relation ---
        # A/A* = (1/Me) * [ (2/(gamma+1)) * (1 + (gamma-1)/2 * Me^2) ]^((gamma+1)/(2*(gamma-1)))
        gp1 = gamma + 1
        gm1 = gamma - 1
        exponent = gp1 / (2.0 * gm1)

        def area_mach_residual(M):
            """Returns A/A*(M) - epsilon.  Root at M = Me (supersonic branch)."""
            return (1.0 / M) * ((2.0 / gp1) * (1.0 + 0.5 * gm1 * M**2))**exponent - eps

        # Supersonic root lies in (1, ~large).  Upper bound from epsilon.
        # For very high expansion ratios the Mach number can be large;
        # eps < 250 (clamped elsewhere) so Me < ~25 is safe.
        try:
            Me = brentq(area_mach_residual, 1.0 + 1e-6, 50.0, xtol=1e-10, maxiter=200)
        except ValueError:
            # Fallback: if brentq fails (e.g. epsilon < 1), use subsonic solution
            try:
                Me = brentq(area_mach_residual, 1e-4, 1.0 - 1e-6, xtol=1e-10, maxiter=200)
            except ValueError:
                Me = 1.0  # sonic -- degenerate case

        # --- Step 2: Exit pressure from isentropic relation ---
        # Pe = Pc * (1 + (gamma-1)/2 * Me^2) ^ (-gamma/(gamma-1))
        Pe = self.P_c * (1.0 + 0.5 * gm1 * Me**2) ** (-gamma / gm1)

        # --- Step 3: Thrust coefficient (Sutton Eq. 3-30) ---
        # CF = lambda * sqrt( (2*gamma^2/(gamma-1)) * (2/(gamma+1))^((gamma+1)/(gamma-1))
        #                      * (1 - (Pe/Pc)^((gamma-1)/gamma)) )
        #      + (Pe - Pa) * epsilon / Pc
        gamma_term = 2.0 * gamma**2 / gm1
        isentropic_term = (2.0 / gp1) ** (gp1 / gm1)
        pressure_ratio_term = 1.0 - (Pe / self.P_c) ** (gm1 / gamma)

        CF_momentum = lambda_eff * np.sqrt(gamma_term * isentropic_term * pressure_ratio_term)
        CF_pressure = (Pe - self.P_a) * eps / self.P_c

        return CF_momentum + CF_pressure
    
    def _get_oxidizer_density(self):
        """Sıvı oksitleyici besleme yoğunluğu [kg/m³] — self.oxidizer_type'a göre.

        Faz, O/F oranından DEĞİL besleme (tank) koşulundan belirlenir
        (denetim bulgusu #2): sıvı-faz besleme varsayılır. Yoğunluk enjeksiyon
        hızına (v=√(2ΔP/ρ)) ve orifis alanına (A=mdot/(Cd·√(2ρΔP))) beslendiği
        için oksitleyiciye göre DOĞRU değer kullanılmalıdır (denetim bulgusu
        #550): eski kod her oksitleyicide N2O yoğunluğu döndürüp LOX/H2O2
        enjektör hız/orifis boyutunu ~%20-30 hatalı veriyordu.

        - N2O: self-pressurized, 25°C doygun sıvı. Birincil kaynak
          external_data_fetcher (CoolProp/NIST, yoksa Span-Wagner EOS);
          erişilemezse N2O_LIQUID_DENSITY_SAT_25C (≈745 kg/m³, NIST WebBook,
          Lemmon & Span 2006).
        - LOX / H2O2 / diğer: merkezi oksitleyici tablosundan
          (PropellantDatabase) işletme sıvı yoğunluğu (LOX≈1141 kg/m³ @ 90 K,
          H2O2 %98 ≈1450 kg/m³ @ 25°C). fetch_nist_oxidizer_properties bu
          akışkanları desteklemeyip sessizce N2O'ya düştüğünden (ve LOX 25°C'de
          kritik-üstü/gaz olacağından) tek doğruluk kaynağı olarak merkezi
          tablo okunur — magic-number tekrarından da kaçınılır.
        """
        ox_name = (getattr(self, 'oxidizer_type', None) or 'n2o').lower()

        if ox_name == 'n2o':
            T_tank = 298.15  # K — 25°C referans tank sıcaklığı (yer işletmesi)
            # Doygunluk basıncının (~56.6 bar @ 298 K) üzerinde besleme basıncı
            # ver ki CoolProp sıvı dalı çözsün; sıvı sıkıştırılabilirliği düşük
            # olduğundan yoğunluk doygun sıvıya çok yakındır.
            P_feed = max(1.2 * self.P_c, 60.0)  # bar
            try:
                props = data_fetcher.fetch_nist_oxidizer_properties(
                    'n2o', temperature=T_tank, pressure=P_feed
                )
                rho = float(props.get('density', 0.0))
                # Sıvı faz makulluk penceresi: doygun sıvı N2O 25°C'de ~745,
                # 20°C'de ~785 kg/m³ (NIST WebBook). Pencere dışı → fallback.
                if 500.0 < rho < 1000.0:
                    return rho
            except Exception:
                pass
            return N2O_LIQUID_DENSITY_SAT_25C  # NIST WebBook (Lemmon & Span 2006)

        # LOX / H2O2 / diğer: merkezi tablodan işletme sıvı yoğunluğu.
        try:
            from hrma.data.propellant_database import PropellantDatabase
            props = PropellantDatabase().get_propellant_properties(ox_name)
            if props and props.get('density'):
                rho = float(props['density'])
                if 300.0 < rho < 2000.0:  # sıvı oksitleyici makulluk penceresi
                    return rho
        except Exception:
            pass

        warnings.warn(
            f"Bilinmeyen/erişilemeyen oksitleyici yoğunluğu '{ox_name}' — "
            "N2O değerine düşürüldü; enjektör boyutlandırması yaklaşık olabilir"
        )
        return N2O_LIQUID_DENSITY_SAT_25C

    def _design_fuel_grain(self):
        """Design fuel grain geometry using correct hybrid rocket equations.

        Port oksitleyici akısı G_ox = mdot_ox / A_port bir TASARIM
        parametresidir ve enjektör orifis akısından (rho·v_enjeksiyon)
        tamamen ayrıdır (denetim bulgusu #1). Grain boyu, yakıt üretim
        kapanışından çözülür: mdot_f = rho_f · π · D_port · L · r_dot
        (Sutton & Biblarz 9. baskı, Böl. 16, yakıt üretim denklemi).
        """
        # --- Enjektör parametreleri (YALNIZ enjektör tasarımı için) ---
        delta_P = 0.2 * self.P_c  # bar — tipik %20 enjektör basınç düşümü (Sutton & Biblarz 9. baskı, Böl. 8)
        rho_ox = self._get_oxidizer_density()  # kg/m³ — oxidizer_type'a göre sıvı besleme yoğunluğu
        # Bernoulli: v = sqrt(2·ΔP/ρ) — yoğunluk, akan akışkanın yoğunluğuyla
        # TUTARLI (denetim bulgusu #3; eski kodda 1220 hardcoded idi)
        injection_velocity = np.sqrt(2 * delta_P * 1e5 / rho_ox)  # m/s

        # Store injector parameters for results output
        self._inj_delta_P = delta_P          # bar
        self._inj_velocity = injection_velocity  # m/s
        self._inj_rho_ox = rho_ox            # kg/m³

        # --- Port boyutlandırma ---
        # Öncelik (v2.5.2): kullanıcı başlangıç port ÇAPINI verdiyse geometri
        # doğrudan ondan gelir; G_ox tasarım akısı bu durumda SONUÇtur
        # (G_ox = mdot_ox / A_port), girdi değil. Çap verilmediyse eski yol:
        # G_ox = mdot_ox / A_port  =>  A_port = mdot_ox / G_ox_design
        # (bulgu #1 düzeltmesi; G_ox_design varsayılanı 350 kg/m²·s).
        # v2.6.2 (F046): N portlu grain. D_port TEK portun çapıdır; akı toplam
        # port alanından hesaplanır: G_ox = mdot_ox / (N · A_tek).
        N_port = self.port_count
        if self.initial_port_diameter is not None:
            self.D_port_initial = self.initial_port_diameter
            A_single_initial = np.pi * (self.D_port_initial / 2.0) ** 2
            A_port_initial = N_port * A_single_initial
            G_ox_initial = self.mdot_ox / A_port_initial
            self.G_ox_design = G_ox_initial
            if G_ox_initial > 600:
                warnings.warn(
                    f"G_ox = {G_ox_initial:.0f} kg/m²·s flooding sınırına "
                    "(~600-700 kg/m²·s) yakın/üstünde — başlangıç port çapını "
                    "büyütün (Sutton & Biblarz 9. baskı, Böl. 16)"
                )
        else:
            G_ox_initial = self.G_ox_design  # kg/m²·s
            A_port_initial = self.mdot_ox / G_ox_initial   # TOPLAM port alanı
            A_single_initial = A_port_initial / N_port
            self.D_port_initial = 2 * np.sqrt(A_single_initial / np.pi)

        # --- Regresyon hızı: Marxman toplam-akı bağıntısı (denetim bulgusu) ---
        # r = a · G_total^n, G_total = G_ox + G_fuel (Marxman & Gilbert 1963;
        # Sutton & Biblarz 9th ed., Böl. 16). Yalnız G_ox kullanmak (eski kod)
        # yakıt akısının önemli olduğu düşük-O/F rejiminde r'yi DÜŞÜK tahmin
        # eder -> web tükenme süresini iyimser gösterir (güvenli olmayan yön).
        # G_fuel, r'ye bağlı olduğundan iteratif kapanış yapılır.
        # flux_mode='ox' verilirse eski davranış (geriye uyum).
        # Not: ilk grain boyu tahmini gerektiğinden, L_grain'i önce mdot_f
        # hedefinden (tasarım O/F) türetip sonra Marxman ile tutarlılaştırırız.
        # Başlangıç L_grain tahmini (yalnız G_ox ile, alt sınır):
        # N portlu grain'de yanma çevresi N·π·D'dir (F046).
        r_dot_ox_only = self.a * G_ox_initial ** self.n
        self.L_grain = self.mdot_f / (
            self.rho_f * N_port * np.pi * self.D_port_initial * r_dot_ox_only
        )

        # --- Grain boyu <-> regresyon hızı SABİT-NOKTA kapanışı ---
        # v2.6.2 fizik denetimi, bulgu F133: flux_mode='total' iken L_grain ile
        # r_dot KARŞILIKLI bağımlıdır — L → mdot_f → G_fuel → G_total → r → L.
        # Eski kod bu çevrimi TEK GEÇİŞ yapıyordu: r_dot yalnız-G_ox ile
        # kurulan (daha uzun) başlangıç L'sinde bir kez hesaplanıyor, ardından
        # L bu r ile yeniden çözülüyor ama r GERİ GÜNCELLENMİYORDU. Sonuçta
        # saklanan (r_dot_initial, G_total_initial) ikilisi saklanan L_grain
        # ile tutarsız kalıyor, yakıt üretim kapanışı
        # mdot_f = rho_f·N·π·D·L·r_dot bozuluyordu.
        # Çevrim şu haritanın sabit noktasıyla kapatılır:
        #     L_{k+1} = mdot_f / (rho_f · N · π · D · r(L_k))
        # Harita büzülmedir: d ln r / d ln L = n·φ/(1 − n·φ) (φ = G_fuel/G_total,
        # tasarım noktasında φ ≈ (sf/OF)/(1 + sf/OF), O/F=6 için ~0.08), yani
        # eğim |−x| « 1 ve birkaç adımda yakınsar.
        # flux_mode='ox' iken r, L'den bağımsızdır: harita ilk adımda sabit
        # noktaya oturur, eski davranış BİREBİR korunur (etki sıfır).
        # Kaynak: iç tutarlılık gereği (yakıt üretim kapanışı, Sutton & Biblarz
        # 9. baskı Böl. 16) — harici katsayı/korelasyon eklenmemiştir.
        L_iter = self.L_grain
        reg0 = None
        grain_iterations = 0
        grain_converged = False
        for grain_iterations in range(1, GRAIN_LENGTH_FIXED_POINT_MAX_ITER + 1):
            reg0 = RegressionAnalyzer.regression_rate(
                self.a, self.n, G_ox_initial,
                rho_f=self.rho_f, port_diameter=self.D_port_initial,
                grain_length=L_iter, flux_mode=self.flux_mode
            )
            L_next = self.mdot_f / (
                self.rho_f * N_port * np.pi * self.D_port_initial
                * reg0['r_dot']
            )
            rel_change = abs(L_next - L_iter) / max(abs(L_next), 1e-12)
            L_iter = L_next
            if rel_change < GRAIN_LENGTH_FIXED_POINT_TOL:
                grain_converged = True
                break

        self.L_grain = L_iter
        # Yakınsanan L ile SON değerlendirme: saklanan r_dot/G_total artık
        # saklanan L_grain'in tam karşılığıdır (tutarsızlık kalmaz).
        reg0 = RegressionAnalyzer.regression_rate(
            self.a, self.n, G_ox_initial,
            rho_f=self.rho_f, port_diameter=self.D_port_initial,
            grain_length=self.L_grain, flux_mode=self.flux_mode
        )
        self.r_dot_initial = reg0['r_dot']
        self.r_dot = self.r_dot_initial  # For compatibility
        self.G_total_initial = reg0['G_total']
        self._grain_length_iterations = grain_iterations
        self._grain_length_converged = bool(grain_converged)
        if not grain_converged:
            # Sessiz yakınsamama yasak: son iterat kullanılıyorsa kullanıcı
            # bunu bilmeli (aynı sözleşme regression_analysis.py'de de var).
            warnings.warn(
                f"Grain boyu <-> regresyon hızı sabit-nokta iterasyonu "
                f"{GRAIN_LENGTH_FIXED_POINT_MAX_ITER} adımda yakınsamadı "
                f"(n={self.n}, son bağıl değişim {rel_change:.2e}); son "
                f"iterat kullanılıyor.",
                RuntimeWarning
            )
            self.design_warnings.append(_w(
                'warn.hybrid.grain_length_not_converged', 'warning',
                max_iter=GRAIN_LENGTH_FIXED_POINT_MAX_ITER,
                n=round(float(self.n), 3),
                rel_change=float(f"{rel_change:.3e}")))

        # --- Euler time-marching (denetim bulgusu #5 düzeltmesi) ---
        # Sabit 10 adım yerine dt = t_b/200 taban çözünürlüğü; ek olarak ilk
        # adımdaki çap artışı başlangıç çapının %1'ini geçmeyecek şekilde adım
        # sayısı artırılır (ilk adım sıçraması koruması).
        # ÜST SINIR ZORUNLU (2026-07-23 kararlılık denetimi): bu ifade tavansızdı
        # ve uç girdilerde programı fiilen kilitliyordu — burn_time=1e12 için
        # 5.6 TRİLYON adım, thrust=1e-9 için 56 milyon adım hesaplanıyor, süreç
        # dakikalarca dönüp megabaytlarca hata günlüğü üretiyordu (paketli
        # uygulamada bu, kullanıcının Belgeler klasörüne akıyor).
        # 200 000 adım, geçerli tasarım aralığının en kötü hâlinin (~17 000)
        # on katından fazlasıdır; sayısal çözünürlük kaybı yok, kilitlenme yok.
        # Sınıra dayanılırsa sessiz geçilmez: uyarı üretilir.
        num_steps = max(
            200,
            int(np.ceil(self.t_b * 2 * self.r_dot_initial / (0.01 * self.D_port_initial)))
        )
        if num_steps > MAX_BURN_INTEGRATION_STEPS:
            warnings.warn(
                f"Yanma integrasyonu {num_steps:,} adım isteyecekti; "
                f"{MAX_BURN_INTEGRATION_STEPS:,} adımda sınırlandırıldı. "
                "Bu, girdilerin (yanma süresi / itki / port çapı) fiziksel "
                "aralık dışında olduğunu gösterir; sonuçlar güvenilir değildir."
            )
            num_steps = MAX_BURN_INTEGRATION_STEPS
        dt = self.t_b / num_steps
        D_port = self.D_port_initial

        # Fiziksel sınır: port çapı kamara çapının %80'ini geçmemeli.
        # Eski koddaki hasattr(self, 'D_ch') kontrolü İLK çağrıda her zaman
        # False idi (D_ch grain tasarımından SONRA atanıyor) → ölü kod; ikinci
        # çağrıda ise bayat D_ch kullanılıyordu. Düzeltme: sınır yalnızca
        # kullanıcı kamara çapı verdiyse uygulanabilir; verilmediyse kamara
        # çapı port sonundan türetildiği için (D_ch = 1.5·D_port_final,
        # yani D_port_final ≈ 0.67·D_ch < 0.8·D_ch) sınır kendiliğinden sağlanır.
        if self.chamber_diameter_input > 0:
            # N portlu grain'de sınır ALAN üzerinden kurulur: toplam port alanı
            # kamara kesitinin (0.8)² katını geçmemeli. Tek port çapı cinsinden
            # bu, D_tek <= 0.8·D_ch/sqrt(N) demektir (N=1'de eski ifadeyle
            # birebir aynı).
            max_port = (PORT_TO_CHAMBER_MAX_RATIO
                        * self.chamber_diameter_input / np.sqrt(N_port))
            if max_port <= self.D_port_initial:
                # v2.5.2 DÜZELTMESİ (Codex bulgusu, hybrid:827): eski kod
                # burada UYARIP sınırı sonsuza çekiyordu. Bu, imkansız
                # geometriyi (port >= kamara) hesaba devam ettiriyordu:
                # yüklenen yakıt kütlesi m_f_loaded = rho·(π/4)·(D_ch² −
                # D_port_ilk²)·L_grain olduğundan D_port_ilk > D_ch iken
                # NEGATİF kütle, negatif sliver ve anlamsız kamara hacmi
                # üretiliyordu. Sessizce devam etmek yerine reddedilir;
                # /calculate ve /api/quick-geometry bunu HTTP 400'e çevirir.
                raise ValueError(
                    f"Chamber diameter {self.chamber_diameter_input * 1000:.1f} mm "
                    f"is too small for the initial port diameter "
                    f"{self.D_port_initial * 1000:.1f} mm. The fuel grain must "
                    f"surround the port, so the chamber diameter has to exceed "
                    f"the port diameter divided by "
                    f"{PORT_TO_CHAMBER_MAX_RATIO:g} "
                    f"(minimum "
                    f"{self.D_port_initial * np.sqrt(N_port) / PORT_TO_CHAMBER_MAX_RATIO * 1000:.1f} mm "
                    f"for {N_port} port(s)). "
                    f"Increase the chamber diameter or reduce the port "
                    f"diameter / oxidizer mass flux."
                )
        else:
            max_port = np.inf

        # O/F kayması izleme: anlık mdot_f / O/F / c* / Isp her adımda.
        # Anlık c*/Isp, anlık O/F'den combustion analyzer ile hesaplanır
        # (denetim bulgusu #2): O/F kayması performansa YANSITILIR; eski kod
        # c*/Isp'yi tasarım O/F'sinde donduruyordu. Pahalı denge çözümünü her
        # adımda tekrarlamamak için O/F->c*/Isp tablosu önbelleğe alınır
        # (track_performance=True ise).
        web_exhausted = False
        self._of_history = []
        self._cstar_history = []
        self._isp_history = []
        self._time_history = []
        # Port çapı zaman serisi: 3D yanma animasyonu D_port(t)'yi buradan okur
        # (track_performance'dan bağımsız tutulur — geometri her zaman lazım)
        self._port_time_history = []
        self._port_diameter_history = []
        # v2.6.26 — İTKİ-ZAMAN EĞRİSİ. Katı motorda bu eğri vardı, hibritte
        # YOKTU; oysa zaman-adımlı çözücü gereken her şeyi zaten hesaplıyordu
        # (anlık yakıt debisi, anlık c*, anlık Isp) ve yalnızca dışarı
        # vermiyordu. Eğri UYDURULMAZ: her nokta bu döngünün kendi
        # durumundan gelir.
        #     ṁ_toplam(t) = ṁ_ox + ṁ_yakıt(t)          (süreklilik)
        #     F(t)        = ṁ_toplam(t)·Isp(t)·g0       (itki tanımı)
        #     Pc(t)       = ṁ_toplam(t)·c*(t)/At        (c* tanımı)
        # Hibritte ṁ_ox sabit, ṁ_yakıt port çapıyla değişir; eğrinin
        # regresif/progresif biçimi bu fizikten çıkar, elle çizilmez.
        self._mdot_total_history = []
        self._thrust_history = []
        self._pc_history = []

        for i in range(num_steps):
            t_now = i * dt
            self._port_time_history.append(t_now)
            self._port_diameter_history.append(D_port)
            A_port = N_port * np.pi * (D_port / 2)**2   # TOPLAM port alanı
            G_ox = self.mdot_ox / A_port  # kg/m²·s oksitleyici akış yoğunluğu

            # Marxman regresyon hızı: r = a · G_total^n (G_total iteratif).
            reg = RegressionAnalyzer.regression_rate(
                self.a, self.n, G_ox,
                rho_f=self.rho_f, port_diameter=D_port,
                grain_length=self.L_grain, flux_mode=self.flux_mode
            )
            r_dot = reg['r_dot']  # m/s

            # Anlık yakıt üretimi ve O/F (kayma izleme) — N portun toplamı
            mdot_f_inst = (self.rho_f * N_port * np.pi * D_port
                           * self.L_grain * r_dot)
            of_inst = self.mdot_ox / mdot_f_inst if mdot_f_inst > 0 else self.OF

            # Anlık c*/Isp (O/F shift -> performans, bulgu #2). Tablo
            # önbelleği ile (track_performance açıkken).
            if self.track_performance:
                cstar_inst, isp_inst = self._instantaneous_performance(of_inst)
                self._of_history.append(of_inst)
                self._cstar_history.append(cstar_inst)
                self._isp_history.append(isp_inst)
                self._time_history.append(t_now)

                # İtki ve oda basıncı, bu adımın KENDİ durumundan türer.
                # At bu noktada hesaplanmıştır (calculate() sırası:
                # At -> _design_fuel_grain); yine de savunmacı davranılır,
                # çünkü At yoksa Pc uydurulamaz — o nokta atlanır.
                mdot_total_inst = self.mdot_ox + mdot_f_inst
                self._mdot_total_history.append(mdot_total_inst)
                self._thrust_history.append(
                    mdot_total_inst * isp_inst * self.g0)
                # Pc BAR cinsinden saklanır: katı motorun thrust_curve
                # sözleşmesi bar kullanıyor (ölçüldü) ve tek bir çizim kodu
                # üç sayfayı da beslediği için birimler AYNI olmak zorunda.
                # c* tanımı Pa verir; 1e5'e bölünür.
                at = getattr(self, 'At', None)
                self._pc_history.append(
                    mdot_total_inst * cstar_inst / at / 1e5
                    if at and at > 0 else float('nan'))

            # Port yarıçapını artır (çap artışı = 2 · yarıçap artışı)
            D_port += 2 * r_dot * dt

            if D_port >= max_port:
                D_port = max_port
                web_exhausted = True
                warnings.warn(
                    "Port çapı 0.8·D_kamara sınırına ulaştı — web yanma süresi "
                    "bitmeden tükendi, grain tasarımını gözden geçirin"
                )
                # v2.6.2: bu, tasarımın İSTENEN yanma süresini tutturamadığı
                # anlamına gelir; design_summary.status bunu okur.
                self.design_warnings.append(_w(
                    'warn.hybrid.web_exhausted_early', 'critical',
                    t_web=round(float(t_now + dt), 2),
                    t_burn=round(float(self.t_b), 2)))
                break

        self.D_port_final = D_port
        # Seriye son noktayı ekle (erken web tükenmesinde son adım zamanı)
        t_end = t_now + dt if web_exhausted else self.t_b
        self.t_burn_effective = t_end
        self._port_time_history.append(t_end)
        self._port_diameter_history.append(D_port)

        # Final oxidizer flux hesaplama (TOPLAM port alanı, F046)
        A_port_final = N_port * np.pi * (self.D_port_final / 2)**2
        self.G_ox_final = self.mdot_ox / A_port_final

        # Yanma sonu Marxman regresyonu ve anlık yakıt debisi / O/F (bulgu #6)
        reg_final = RegressionAnalyzer.regression_rate(
            self.a, self.n, self.G_ox_final,
            rho_f=self.rho_f, port_diameter=self.D_port_final,
            grain_length=self.L_grain, flux_mode=self.flux_mode
        )
        r_dot_final = reg_final['r_dot']
        self.G_total_final = reg_final['G_total']
        self.mdot_f_final = (self.rho_f * N_port * np.pi * self.D_port_final
                             * self.L_grain * r_dot_final)
        self.OF_final = self.mdot_ox / self.mdot_f_final if self.mdot_f_final > 0 else self.OF

        # --- Ortalama regresyon hızı (v2.6.2 FİZİK DENETİMİ, bulgu F045) ---
        # ESKİ TANIM: uç noktaların ARİTMETİK ORTALAMA AKISINDA değerlendirilen
        # ANLIK regresyon (r = a·G_ort^n). Bu, deneysel literatürün ve
        # doğrulama veritabanının measured.regression_rate_avg alanının
        # raporladığı büyüklük DEĞİLDİR; oradaki büyüklük UZAY-ZAMAN
        # ORTALAMASIDIR: r̄ = (D_final − D_initial)/(2·t_b).
        # İki tanım aynı değildir: (i) r = a·G^n, n<1 için G'de içbükeydir,
        # Jensen eşitsizliği gereği a·ort(G)^n >= ort(a·G^n); (ii) G_ox(t) ∝ D⁻²
        # azalan-dışbükey olduğundan uç nokta aritmetik ortalaması gerçek zaman
        # ortalamasının üstündedir. Sonuç: eski tanım modelin gerçek sapmasını
        # sistematik olarak MASKELİYORDU.
        # DOĞRULAMA: veritabanında hem r̄ hem D_i/D_f/t_b veren 4 kayıtta
        # (D_f−D_i)/(2·t_b) ile yayımlanan r̄ arasındaki medAPE %0.11 —
        # yani ölçülen büyüklüğün tanımı budur, tartışmaya yer yok.
        # Model D_final'ı ZATEN hesapladığı için bu tanım bedelsiz ve tam
        # tutarlıdır (aynı zamanda m_f_grain ile birebir uyumludur).
        # Kaynak: Chiaverini & Kuo, "Fundamentals of Hybrid Rocket Combustion
        # and Propulsion", AIAA Progress Vol. 218 (2007), Böl. 2; Karabeyoglu
        # et al., JPP 20(6) 2004 — veri indirgeme (çap ölçümü) bölümü.
        # Web erken tükendiyse GERÇEK yanma süresi kullanılır (aksi hâlde
        # ortalama, hiç yaşanmamış bir süreye bölünürdü).
        self.r_dot_avg = ((self.D_port_final - self.D_port_initial)
                          / (2.0 * t_end)) if t_end > 0 else self.r_dot_initial
        # Akı-ortalama tanımı da şeffaflık için saklanır (eski çıktı; hangi
        # tanımın raporlandığı karşılaştırılabilsin diye).
        G_ox_avg = (G_ox_initial + self.G_ox_final) / 2
        reg_avg = RegressionAnalyzer.regression_rate(
            self.a, self.n, G_ox_avg,
            rho_f=self.rho_f, port_diameter=(self.D_port_initial + self.D_port_final) / 2,
            grain_length=self.L_grain, flux_mode=self.flux_mode
        )
        self.r_dot_at_avg_flux = reg_avg['r_dot']

        # Grain'in fiilen ürettiği yakıt kütlesi (denetim bulgusu #6):
        # m_f = rho_f · N · (V_port_final − V_port_initial)
        #     = rho_f · N · (π/4) · (D_final² − D_initial²) · L_grain
        self.m_f_grain = (
            self.rho_f * N_port * (np.pi / 4.0)
            * (self.D_port_final**2 - self.D_port_initial**2)
            * self.L_grain
        )
        self._web_exhausted = web_exhausted

        # Store for results
        self.G_ox_initial = G_ox_initial
    
    def _resolve_contraction_ratio(self):
        """(A_c/A_t, kaynak) — daralma oranının TEK tanım noktası.

        Kullanıcı bir değer verdiyse o geçerlidir; vermediyse oda kesiti grain
        dış zarfından bilindiği için geometriden türetilir.

        v2.6.26: bu çözüm yalnız `_finite_area_combustor` içinde duruyordu ve
        lüle tasarımcısına HİÇ geçirilmiyordu. Ölçüldü: kullanıcı 4.0
        girdiğinde yanıtın bir yerinde `finite_area_combustor.contraction_ratio
        = 4.0 (user input)` yazarken lüle konturunda
        `convergent.contraction_ratio = 2.25` kalıyor ve yakınsak koni boyu hiç
        değişmiyordu — tek sonuçta iki çelişkili daralma oranı. Tek kaynağa
        indirildi.
        """
        cr_user = getattr(self, 'contraction_ratio_input', None)
        cr_geom = None
        if getattr(self, 'D_ch', 0) and getattr(self, 'd_t', 0):
            cr_geom = (self.D_ch / self.d_t) ** 2
        kullanici_verdi = bool(cr_user and float(cr_user) > 1.0)
        cr = float(cr_user) if kullanici_verdi else cr_geom
        if not cr or cr <= 1.0:
            return None, None
        return cr, ('user input' if kullanici_verdi else 'chamber geometry')

    def _finite_area_combustor(self):
        """Sonlu alanlı yanma odası: kontraksiyon oranından basınç kaybı.

        v2.6.26 — ÖLÜ ALAN DÜZELTMESİ. Arayüzdeki ``combustion_type``
        seçicisi ve ``contraction_ratio`` alanı ölçümde çıktının HİÇBİR
        yaprağını değiştirmiyordu: ``self.combustion_type`` sınıfta yalnız
        bir kez ATANIYOR, hiç okunmuyordu; ``contraction_ratio`` ise motora
        hiç geçirilmiyordu. Kullanıcı bir yanma modeli seçtiğini sanıyordu.

        Fizik (Sutton & Biblarz, Roket Tahrik Elemanları, Böl. 3; Huzel &
        Huang, NASA SP-125, Böl. 4): sonsuz alanlı oda varsayımında odadaki
        akış hızı sıfır kabul edilir ve enjektör yüzü basıncı ile nozul
        durgunluk basıncı eşittir. Gerçek odada kesit sonludur; akış boğaza
        doğru hızlanır, odada sonlu bir Mach sayısı oluşur ve enjektör
        yüzündeki basınç nozul girişindekinden YÜKSEKTİR. Oda Mach sayısı,
        izentropik alan bağıntısının ses altı kökünden gelir:

            A_c/A_t = (1/M)·[ (2/(g+1))·(1 + (g-1)/2·M²) ]^((g+1)/(2(g-1)))

        Enjektör yüzü / nozul durgunluk basıncı oranı ise sıkıştırılabilir
        akışın durgunluk bağıntısıdır:

            p_inj/p_c = (1 + (g-1)/2·M_c²)^(g/(g-1))

        CR büyüdükçe M_c -> 0 ve oran -> 1; yani sonsuz alan çözümü bu
        modelin limit hâlidir. Bu, bir uydurma düzeltme katsayısı DEĞİL,
        aynı denklemin sonlu kesit için çözülmüş hâlidir.

        Döndürür: ``None`` (model uygulanmadı) veya sonuç sözlüğü.
        """
        if str(getattr(self, 'combustion_type', 'infinite')).lower() != 'finite':
            return None
        gamma = float(getattr(self, 'gamma', 1.2) or 1.2)
        if not (1.0 < gamma < 2.0):
            return None

        # Kontraksiyon oranı TEK KAYNAKTAN (_resolve_contraction_ratio):
        # eskiden bu blok yalnız buradaydı ve lüle konturu aynı sayıyı
        # görmüyordu — aynı yanıtta iki farklı daralma oranı çıkıyordu.
        cr, source = self._resolve_contraction_ratio()
        if not cr:
            return None

        # İzentropik alan bağıntısının SES ALTI kökü (ikiye bölme; A/A* alan
        # oranı M<1 bölgesinde M ile monoton azalır, kök tektir).
        exponent = (gamma + 1.0) / (2.0 * (gamma - 1.0))

        def area_ratio(mach):
            return (1.0 / mach) * ((2.0 / (gamma + 1.0))
                                   * (1.0 + 0.5 * (gamma - 1.0) * mach ** 2)) ** exponent

        lo, hi = 1e-6, 1.0
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            if area_ratio(mid) > cr:
                lo = mid
            else:
                hi = mid
        mach_c = 0.5 * (lo + hi)

        stagnation_ratio = (1.0 + 0.5 * (gamma - 1.0) * mach_c ** 2) ** (
            gamma / (gamma - 1.0))
        injector_face_bar = self.P_c * stagnation_ratio

        # Çok küçük kontraksiyonda oda tıkanmaya yaklaşır — uyar, kırpma.
        if cr < 2.0:
            self.design_warnings.append(_w(
                'warn.hybrid.contraction_ratio_low', 'warning',
                contraction_ratio=round(cr, 2),
                chamber_mach=round(mach_c, 3)))

        return {
            'model': 'finite-area combustor',
            'contraction_ratio': round(cr, 3),
            'contraction_ratio_source': source,
            'chamber_mach': round(mach_c, 4),
            'injector_face_pressure_bar': round(injector_face_bar, 3),
            'stagnation_pressure_ratio': round(stagnation_ratio, 5),
            'pressure_loss_percent': round((stagnation_ratio - 1.0) * 100.0, 3),
            'basis': ('Isentropic area-Mach relation (subsonic root) plus the '
                      'compressible stagnation relation; Sutton & Biblarz Ch.3, '
                      'Huzel & Huang NASA SP-125 Ch.4. The infinite-area '
                      'assumption is the CR -> infinity limit of this model.'),
        }

    def _compile_results(self, combustion_results=None, nozzle_results=None,
                        altitude_performance=None, optimum_of=None, thrust_altitude_analysis=None,
                        heat_transfer_results=None, structural_results=None,
                        nozzle_material_results=None):
        """Compile all results into a comprehensive dictionary"""
        
        # Basic performance and geometry
        basic_results = {
            # Performance
            'thrust': self.F,
            'total_impulse': self.I_total,
            'isp': self.Isp,
            'c_star': self.C_star,
            'cf': self.CF,
            'mdot_total': self.mdot_total,
            'mdot_ox': self.mdot_ox,
            'mdot_f': self.mdot_f,
            
            # Geometry
            'throat_area': self.At,
            'throat_diameter': self.d_t,
            'exit_area': self.Ae,
            'exit_diameter': self.d_e,
            'expansion_ratio': self.epsilon,
            'chamber_volume': self.V_c,
            'chamber_diameter': self.D_ch,
            'chamber_length': self.L,
            # L* modeli (v2.5.2): kamara boyu = grain + ön-yanma + art-yanma.
            'pre_chamber_length': getattr(self, 'L_pre_chamber', 0.0),
            'post_chamber_length': getattr(self, 'L_post_chamber', 0.0),
            'l_star': self.L_star,
            'l_star_achieved': getattr(self, 'L_star_achieved', self.L_star),
            'l_star_note': getattr(self, 'l_star_note', ''),
            # v2.6.26: kamara boyunun kullanıcı ezmesinden mi L*'dan mı
            # geldiği görünür olmalı (ezme kabul edilmediyse kullanıcı bunu
            # uyarıdan ve bu alandan anlar).
            'chamber_length_source': getattr(self, 'chamber_length_source',
                                             'l_star_derived'),
            'chamber_length_auto': getattr(self, 'chamber_length_auto',
                                           self.L),
            'design_safety_factor_input': self.design_safety_factor,
            'nozzle_material': self.nozzle_material,
            'chamber_volume_actual': getattr(self, 'V_c_actual', self.V_c),
            
            # Fuel grain
            'port_diameter_initial': self.D_port_initial,
            'port_diameter_final': self.D_port_final,
            'regression_rate': self.r_dot,
            'regression_rate_avg': self.r_dot_avg,
            'g_ox_initial': self.G_ox_initial,
            'g_ox_final': self.G_ox_final,
            
            # Propellant
            'propellant_mass_total': self.m_total,
            'oxidizer_mass': self.m_ox,
            'fuel_mass': self.m_f,                      # YANAN yakıt (performans bütçesi)
            'fuel_mass_loaded': getattr(self, 'm_f_loaded', self.m_f),  # yüklenen (kütle bütçesi)
            'fuel_sliver_fraction': getattr(self, 'fuel_sliver_fraction', 0.0),
            
            # Operating conditions
            'chamber_pressure': self.P_c,
            'chamber_temperature': self.T_c,
            'burn_time': self.t_b,
            'of_ratio': self.OF,

            # O/F kayması (denetim bulgusu #6): port büyüdükçe mdot_f değişir;
            # başlangıç O/F tasarım değeridir, yanma sonu O/F time-marching
            # içindeki anlık mdot_f'den gelir.
            'of_ratio_initial': self.OF,
            'of_ratio_final': self.OF_final,
            'fuel_mass_flow_final': self.mdot_f_final,
            'grain_length': self.L_grain,
            'g_ox_design': self.G_ox_design,

            # Marxman toplam akı (denetim bulgusu #1): regresyon G_total ile
            # hesaplanır; G_ox-only'ye göre düşük-O/F rejiminde daha yüksek
            # (konservatif) r verir.
            'regression_flux_mode': self.flux_mode,
            'g_total_initial': getattr(self, 'G_total_initial', self.G_ox_initial),
            'g_total_final': getattr(self, 'G_total_final', self.G_ox_final),
        }

        # gamma + molecular_weight ÜST SEVİYEDE (Dalga 0, 2026-07-14):
        # Bartz ve lüle tüketicileri artık compositions->chamber'a inmek
        # ya da varsayılana (gamma=1.20, MW=24) düşmek zorunda kalmaz.
        # Öncelik: yanma dengesinin chamber kaydı; yoksa sınıf değerleri
        # (self.gamma, MW = R_evrensel / self.R).
        gamma_top = self.gamma
        mw_top = None
        if getattr(self, 'R', None):
            mw_top = self.combustion_analyzer.R_universal / self.R  # g/mol
        if combustion_results:
            chamber_comp = combustion_results.get(
                'compositions', {}).get('chamber', {})
            gamma_top = chamber_comp.get('gamma', gamma_top)
            mw_top = chamber_comp.get('molecular_weight', mw_top)
        basic_results['gamma'] = gamma_top
        basic_results['molecular_weight'] = mw_top

        # --- UQ modu izleri (v2.5.0): atlanan danışma blokları dürüstçe not
        # edilir; ana çıktılar uq_mode'dan ETKİLENMEZ (test kilidi altında).
        if self.uq_mode:
            basic_results['uq_mode'] = True
            if optimum_of is None:
                basic_results['optimum_of_note'] = (
                    'optimum O/F search skipped in uq_mode (advisory output); '
                    'inject precomputed_optimum_of from the nominal run to '
                    'populate optimum_analysis/optimum_of_ratio.'
                )
        # c* verimi raporu: teslim edilen c* basic_results['c_star'] içindedir;
        # teorik değer ayrıca verilir ki verim varsayımı şeffaf kalsın.
        if self.eta_c_star is not None:
            basic_results['eta_c_star'] = self.eta_c_star
            basic_results['c_star_theoretical'] = getattr(
                self, 'C_star_theoretical', self.C_star)

        # O/F kaymasının performansa etkisi (denetim bulgusu #2): time-marching
        # boyunca anlık O/F'den hesaplanan c*/Isp dizileri ve zaman-ortalamaları.
        if self.track_performance and getattr(self, '_cstar_history', None):
            cstar_hist = self._cstar_history
            isp_hist = self._isp_history
            basic_results['of_shift_performance'] = {
                'time': list(self._time_history),
                'of_ratio': list(self._of_history),
                'c_star': list(cstar_hist),
                'isp': list(isp_hist),
                'c_star_time_avg': float(np.mean(cstar_hist)) if cstar_hist else self.C_star,
                'isp_time_avg': float(np.mean(isp_hist)) if isp_hist else self.Isp,
                'c_star_design_of': self.C_star,
                'isp_design_of': self.Isp,
            }

        # İtki-zaman eğrisi (v2.6.26). Katı motorla AYNI sözleşme
        # ({time, thrust, pressure, mass_flow}) kullanılır ki üç sayfa aynı
        # çizim kodunu paylaşabilsin. Değerlerin tamamı zaman-adımlı
        # çözücünün kendi durumundan gelir; şekil verilmez.
        if getattr(self, '_thrust_history', None):
            basic_results['thrust_curve'] = {
                'time': [float(x) for x in self._time_history],
                'thrust': [float(x) for x in self._thrust_history],
                'pressure': [float(x) for x in self._pc_history],
                'mass_flow': [float(x) for x in self._mdot_total_history],
                'basis': ('time-marching solution: F = mdot_total(t)*Isp(t)*g0, '
                          'Pc = mdot_total(t)*c_star(t)/At; oxidiser flow is '
                          'constant, fuel flow follows the regressing port'),
            }

        # Port çapı zaman serisi (3D yanma animasyonu için, metre + saniye).
        # Yanıt boyutunu sınırlamak için ~200 noktaya seyreltilir.
        if getattr(self, '_port_diameter_history', None):
            pt = self._port_time_history
            pd = self._port_diameter_history
            stride = max(1, len(pt) // 200)
            idx = list(range(0, len(pt), stride))
            if idx[-1] != len(pt) - 1:
                idx.append(len(pt) - 1)
            basic_results['port_history'] = {
                'time': [float(pt[i]) for i in idx],
                'port_diameter': [float(pd[i]) for i in idx],
            }

        # --- 1. Nozzle Angles ---
        nozzle_type = self.nozzle_type
        basic_results['nozzle_angles'] = {
            'convergent_half_angle_deg': 30.0 if nozzle_type == 'conical' else 45.0,
            'divergent_half_angle_deg': 15.0 if nozzle_type == 'conical' else 11.0,
            'nozzle_type': nozzle_type,
            'divergence_efficiency': self.lambda_eff,
        }

        # --- 2. Grain Design ---
        # Grain boyu yakıt üretim kapanışından gelir (denetim bulgusu #6),
        # kamara boyundan DEĞİL: mdot_f = rho_f·π·D_port·L_grain·r_dot
        fuel_length = self.L_grain
        chamber_diameter = self.D_ch
        basic_results['grain_design'] = {
            'grain_type': 'cylindrical_bore',
            'web_thickness_mm': (self.D_port_final - self.D_port_initial) / 2 * 1000,
            'port_diameter_initial_mm': self.D_port_initial * 1000,
            'port_diameter_final_mm': self.D_port_final * 1000,
            'grain_length_mm': fuel_length * 1000,
            'grain_outer_diameter_mm': chamber_diameter * 1000,
            'number_of_segments': max(1, int(fuel_length / 0.3)),
            'inhibitor': 'outer_surface',
            'L_over_D': fuel_length / chamber_diameter if chamber_diameter > 0 else 0,
        }

        # --- 3. Injector Design ---
        # Gerçek tasarım: injector_design modülü (docs/10_Enjektor_ARGE.md).
        # N2O'da Dyer NHNE iki-faz debisi, Cd gerekçesi, delik planı, SMD,
        # chug/flip kontrolleri. Modül hata verirse eski basit Bernoulli
        # hesabına düşülür (hesap zinciri kırılmaz).
        delta_P_inj = self._inj_delta_P  # bar (stored from _design_fuel_grain)
        rho_ox = self._inj_rho_ox        # kg/m³
        try:
            from hrma.engines.injector_design import design_injector
            inj_spec = {
                'motor_type': 'hybrid',
                # v2.5.2: kullanıcının seçtiği enjektör tipi (eskiden sabit
                # 'showerhead' idi, seçim sonucu hiç etkilemiyordu)
                # v2.6.26: ARAYÜZ SÖZCÜĞÜ İLE MODÜL SÖZCÜĞÜ AYRIYDI. Arayüz
                # 'impingement' / 'coaxial' gönderiyor, bu modül
                # 'like_impinging' / 'gas_gas_coaxial' bekliyor. Eşleme
                # olmadığı için beş enjektör tipinin İKİSİNDE çağrı
                # ValueError atıyor ve aşağıdaki yedek yola düşülüyordu —
                # yedek yol da 12 delikli showerhead SABİTİ üretiyordu.
                # Yani pintle-dışı iki tipte kullanıcı, seçtiği tipin
                # etiketini taşıyan uydurma bir showerhead sonucu görüyordu.
                'injector_type': INJECTOR_TYPE_TO_MODULE.get(
                    self.injector_type, self.injector_type),
                'mdot_ox': self.mdot_ox,
                'rho_ox': rho_ox,
                'Pc_bar': self.P_c,
                'dp_ratio_ox': delta_P_inj / self.P_c if self.P_c > 0 else 0.20,
            }
            # v2.6.26 — DEŞARJ KATSAYISI ARTIK GEOMETRİDEN GELİYOR.
            # Devre çözücüsü Cd'yi discharge_coefficient(giriş, L/D) ile
            # ZATEN seçiyordu, ama hibrit sözlüğü ne 'inlet_ox' ne
            # 'orifice_length_m' anahtarını taşıdığı için her koşuda
            # giriş='sharp', L/D=4,0 varsayımına düşülüyor ve Cd 0,78'de
            # SABİT kalıyordu (17/17 koşu). Cd doğrudan delik alanına girer
            # (A = ṁ/(Cd·√(2ρΔP))): tablonun 0,63-0,92 bandı uçtan uca
            # ~%46 alan farkı demektir. Plaka kalınlığı arayüzde ZATEN var.
            if self.injector_plate_thickness:
                inj_spec['orifice_length_m'] = self.injector_plate_thickness
            if self.injector_orifice_inlet:
                inj_spec['inlet_ox'] = self.injector_orifice_inlet
            ox_name = (getattr(self, 'oxidizer_type', None) or 'n2o').lower()
            if ox_name == 'n2o':
                # Tank sıcaklığı v2.5.2'de motor girdisi; verilmezse doymuş
                # depolama 293.15 K varsayımı (transient/blowdown ile aynı)
                inj_spec['fluid_ox'] = 'n2o'
                inj_spec['T_ox_K'] = (self.tank_temperature
                                      if self.tank_temperature is not None
                                      else 293.15)
            # Oda gazı yoğunluğu (SMD için): T_c ve MW = R_evrensel/R_spesifik
            if getattr(self, 'T_c', None) and getattr(self, 'R', None):
                inj_spec['T_c_K'] = self.T_c
                inj_spec['mw_gas'] = 8314.462618 / self.R
            detail = design_injector(inj_spec)
            if detail.get('status') != 'success':
                raise ValueError(detail.get('error', 'enjektör tasarım hatası'))
            oxc = detail['ox_circuit']
            basic_results['injector_design'] = {
                # Kullanıcının SEÇTİĞİ ad birincil; modülün iç sözcüğü ayrı
                # alanda verilir (eşleme yapıldığında kullanıcı 'impingement'
                # seçip sonuçta 'like_impinging' görmemeli).
                'injector_type': self.injector_type,
                'model_injector_type': detail['injector_type'],
                'oxidizer_flow_rate_kg_s': self.mdot_ox,
                'injection_velocity_m_s': oxc['velocity_m_s'],
                'number_of_orifices': oxc['n_orifices'],
                'orifice_diameter_mm': oxc['orifice_d_mm'],
                'injection_pressure_drop_bar': oxc['delta_p_bar'],
                'manifold_diameter_mm': oxc['manifold']['d_mm'],
                'discharge_coefficient': oxc['cd'],
                'total_injector_area_mm2': oxc['total_area_mm2'],
            }
            basic_results['injector_design_detail'] = detail
        except Exception as _inj_err:
            # v2.6.26 — UYDURMA YEDEK KALDIRILDI.
            #
            # Eski yedek yol, devre modeli hata verdiğinde şu SABİTLERİ
            # üretiyordu: n_orifices = 12 ("typical showerhead pattern"),
            # Cd = 0.65 ve manifold çapı = 2 x başlangıç port çapı. Bu
            # sayıların hiçbiri kullanıcının seçtiği enjektör tipinden
            # gelmiyordu; yine de sonuç ``injector_type`` alanında
            # kullanıcının seçimiyle ETİKETLENİYORDU. Yani pintle/swirl
            # dışındaki iki tipte kullanıcı, "coaxial" yazan bir 12 delikli
            # showerhead görüyordu. Uyarı yalnız ``warnings.warn`` ile
            # sunucu günlüğüne gidiyordu; ekranda hiçbir iz yoktu.
            #
            # Yeni sözleşme: delik planı üretilemiyorsa ÜRETİLMEZ. Blok
            # 'status: not_analyzed' ile ve nedeniyle döner, uyarı
            # kullanıcıya ULAŞIR. Geometri uydurmak, geometri vermemekten
            # daha kötüdür — kullanıcı bu sayıları imalata götürüyor.
            self._fallback_used.append('injector_design_detail')
            self.design_warnings.append(_w(
                'warn.hybrid.injector_detail_unavailable', 'warning',
                injector_type=self.injector_type,
                reason=str(_inj_err)[:200]))
            basic_results['injector_design'] = {
                'status': 'not_analyzed',
                'injector_type': self.injector_type,
                'reason': (f'the detailed injector circuit model could not '
                           f'size this injector: {_inj_err}'),
                # Cozucunun GERCEKTEN hesapladiklari korunur; uydurulan
                # (delik sayisi, delik capi, manifold capi, Cd) verilmez.
                'oxidizer_flow_rate_kg_s': self.mdot_ox,
                'injection_pressure_drop_bar': delta_P_inj,
            }

        # --- 4. Design Summary ---
        # Total motor length estimate: chamber + convergent + divergent sections
        conv_half_angle = basic_results['nozzle_angles']['convergent_half_angle_deg']
        div_half_angle = basic_results['nozzle_angles']['divergent_half_angle_deg']
        L_conv = (chamber_diameter / 2 - self.d_t / 2) / np.tan(np.radians(conv_half_angle))
        L_div = (self.d_e / 2 - self.d_t / 2) / np.tan(np.radians(div_half_angle))
        total_motor_length = self.L + L_conv + L_div
        # Total mass estimate: propellant + dry mass (~25% of propellant for small motors)
        # v2.6.26 — KURU KÜTLE ARTIK GEOMETRİDEN HESAPLANIYOR.
        #
        # Burada `dry_mass_est = 0.25 * m_total` yazıyordu: itergaç kütlesinin
        # dörtte biri alınan bir başparmak kuralı. Kullanıcının cidar
        # kalınlığından, malzemesinden ve motorun kendi geometrisinden
        # TAMAMEN kopuktu — ölçüldü: cidar 3 mm'den 20 mm'ye çıkarıldığında
        # bu sayı 1,366 kg'da SABİT kaldı, malzeme değişimi de etkilemedi.
        # Aynı koşuda CAD kütle dökümü gerçek geometri × yoğunlukla
        # 32,02 kg veriyordu; iki sayı 23 KAT farklıydı ve ikisi de "kuru
        # kütle" adıyla kullanıcıya gösteriliyordu. İtki/ağırlık oranı bu
        # sayıdan çıktığı için uçuş bütçesi de yanlış oluyordu.
        #
        # Yeni davranış: yapısal analizin hesapladığı GERÇEK kamara kütlesi
        # kullanılır. Yapısal sonuç yoksa sayı UYDURULMAZ — None döner ve
        # nedeni beyan edilir (0 yazmak "kütlesiz motor" demek olurdu).
        dry_mass_est = None
        dry_mass_basis = 'structural analysis not available'
        try:
            weight = (structural_results or {}).get('weight_analysis') or {}
            for key in ('total_mass', 'total_weight', 'total_structural_mass'):
                candidate = weight.get(key)
                if candidate is not None and np.isfinite(float(candidate)):
                    dry_mass_est = float(candidate)
                    dry_mass_basis = (
                        'structural analysis: chamber + nozzle + closures '
                        'from real geometry and material density')
                    break
        except (TypeError, ValueError, AttributeError):
            dry_mass_est = None
        total_mass = (self.m_total + dry_mass_est
                      if dry_mass_est is not None else None)

        basic_results['design_summary'] = {
            'title': f'{self.motor_name or "Hybrid Motor"} - Optimal Design',
            'status': 'OPTIMIZED',
            'key_dimensions': {
                'chamber_diameter_mm': chamber_diameter * 1000,
                'chamber_length_mm': self.L * 1000,
                'nozzle_throat_diameter_mm': self.d_t * 1000,
                'nozzle_exit_diameter_mm': self.d_e * 1000,
                'total_motor_length_mm': total_motor_length * 1000,
                'total_mass_kg': total_mass,
                'dry_mass_estimate_kg': dry_mass_est,
                # Kütlenin nereden geldiği görünür olmalı: eskiden bu alan
                # bir başparmak kuralıydı ve kullanıcı bunu bilmiyordu.
                'dry_mass_basis': dry_mass_basis,
            },
            'performance': {
                'thrust_N': self.F,
                'specific_impulse_s': self.Isp,
                'burn_time_s': self.t_b,
                'total_impulse_Ns': self.I_total,
                'characteristic_velocity_m_s': self.C_star,
                'thrust_coefficient': self.CF,
            },
            'nozzle': {
                'convergent_length_mm': L_conv * 1000,
                'divergent_length_mm': L_div * 1000,
            },
            'recommendation': ('Optimised design for the given parameters. '
                               'Nozzle angles and grain geometry are sized to the design point.'),
        }

        # Add advanced analysis results if available
        if combustion_results:
            basic_results['combustion_analysis'] = combustion_results
            basic_results['stoichiometric_of'] = combustion_results['stoichiometric_of']
            basic_results['equivalence_ratio'] = combustion_results['equivalence_ratio']
            basic_results['mass_fractions'] = combustion_results['compositions']
        
        if nozzle_results:
            basic_results['nozzle_design'] = nozzle_results
            basic_results['nozzle_geometry'] = nozzle_results['geometry']
            basic_results['nozzle_contour'] = nozzle_results['contour']
        
        if altitude_performance:
            basic_results['altitude_performance'] = altitude_performance
            basic_results['sea_level_isp'] = altitude_performance['sea_level_isp']
            basic_results['vacuum_isp'] = altitude_performance['vacuum_isp']
        
        if optimum_of:
            basic_results['optimum_analysis'] = optimum_of
            basic_results['optimum_of_ratio'] = optimum_of['optimum_of_ratio']
            basic_results['maximum_isp'] = optimum_of['maximum_isp']
        
        if thrust_altitude_analysis:
            basic_results['thrust_altitude_analysis'] = thrust_altitude_analysis
        
        if heat_transfer_results:
            basic_results['heat_transfer_analysis'] = heat_transfer_results
        
        if structural_results:
            basic_results['structural_analysis'] = structural_results

        if nozzle_material_results:
            basic_results['nozzle_material_analysis'] = nozzle_material_results

        # v2.6.26: hibrit motor uyarıları TOPLUYOR ama sonuç sözlüğüne HİÇ
        # koymuyordu; ``self.design_warnings`` listesi nesneyle birlikte
        # ölüyordu. Ölçüldü: chamber_material='ZIRVAAA' gönderilen bir istek
        # HTTP 200 dönüyor, sessizce steel_4130 kullanılıyor ve kullanıcıya
        # HİÇBİR uyarı ulaşmıyordu — yani "sessiz yedeğe düşme yasak" diyen
        # _resolve_chamber_material'ın uyarısı fiilen yok hükmündeydi.
        # Katı motorda olduğu gibi iki adla birden verilir: arayüz panelleri
        # 'warnings', dış tüketiciler 'design_warnings' okuyor.
        finite_area = self._finite_area_combustor()
        if finite_area:
            basic_results['finite_area_combustor'] = finite_area

        warnings_list = list(getattr(self, 'design_warnings', []) or [])
        basic_results['design_warnings'] = warnings_list
        basic_results['warnings'] = warnings_list

        return basic_results