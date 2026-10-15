"""
Trajectory Analysis Module for Hybrid Rocket Motors
Detailed flight trajectory calculations and analysis

KONVANSIYON / SIGN & AXIS CONVENTION
====================================
2B (dikey düzlem) nokta-kütle modeli:
  - x : yatay (downrange) konum [m], pozitif rüzgaraltı/menzil yönü
  - z : irtifa [m], pozitif YUKARI
  - vx, vz : ilgili hız bileşenleri [m/s]

LAUNCH ANGLE (fırlatma açısı) = YÜKSELİŞ AÇISI (elevation), UFUKTAN ölçülür:
  - 90° = tam DİKEY yukarı  -> vertical = sin(90°)=1, horizontal = cos(90°)=0
  - 85° = hafif eğik (dikeyden 5° sapma) -> vertical = sin(85°)=0.996
  -  0° = yatay
Bu, havacılık/balistik standart "elevation angle" tanımıdır
(McCoy, "Modern Exterior Ballistics", 1999; standart trajectory literatürü).

DÜZELTME NOTU (2026-06): Eski kod sin/cos'u TERS kullanıyordu
(vertical=cos, horizontal=sin), bu yüzden 90° fırlatma TÜM iticiyi yatay
yöne veriyordu (apogee=0, roket yere paralel gidiyordu). Aşağıdaki kod
yükseliş açısı konvansiyonunu kullanır: vertical=sin(theta), horiz=cos(theta).

RÜZGAR YÖNÜ: ``wind_direction`` rüzgârın GELDİĞİ yöndür (meteorolojik
standart, WMO). Hava kütlesi hız vektörü bu yönün tersidir:
v_hava = −V·(cos φ, sin φ). Kardeş 6-DOF modülü aynı konvansiyonu kullanır.

RÜZGAR: Aerodinamik kuvvetler HAVAYA GÖRE bağıl hızdan hesaplanır.
  v_rel = v_arac - v_ruzgar ;  Drag = -0.5*rho*Cd*A*|v_rel|*v_rel
İtki ve yerçekimi atalet çerçevesinde etki eder; yalnızca sürükleme
bağıl hızı kullanır (standart formülasyon, McCoy 1999; Sutton & Biblarz
"Rocket Propulsion Elements" 9. baskı, Bölüm 4).
"""

import numpy as np
# ÖH D26 / OH-D25-14: ``np.trapz`` NumPy 2.0'da ad alanından
# KALDIRILDI (np.trapezoid); ad TEK YERDE çözülür.
from hrma.utils.numeric_compat import trapezoid as _trapezoid
from scipy.integrate import solve_ivp
from typing import Dict, List, Tuple, Optional

# Merkezi fiziksel sabitler (magic-number tutarsızlığını önler).
# ISA_LAYERS: U.S. Standard Atmosphere 1976 katman tablosu.
from hrma.constants import (
    G_0,
    ISA_LAYERS,
    ISA_TABLE_BOTTOM_M,
    ISA_TABLE_TOP_M,
    M_AIR,
    R_STAR_ICAO,
)

# Kuru hava için izentropik üs ve özgül gaz sabiti (ses hızı için).
# gamma_air = 1.4 (iki-atomlu gaz), R_air = R*/M_air ile uyumlu olması için
# R_specific_air = 287.053 J/(kg*K) (CRC Handbook; ISO 2533).
GAMMA_AIR = 1.4
R_SPECIFIC_AIR = R_STAR_ICAO / M_AIR  # = 8.31432/0.0289644 ≈ 287.05 J/(kg*K)

#: Aynı yanmayı iki ayrı yoldan tarif eden girdiler arasında kabul edilen
#: bağıl ayrışma. ÖH D22 / P4B3-24 (doktrin-4 TEK KAYNAK): sayı ``hrma/app.py``
#: içinde ``_TRAJECTORY_PROPELLANT_REL_TOL`` adıyla yazılıydı ve yalnız HTTP
#: ucunu koruyordu; kütüphane API'si (``calculate_trajectory``) aynı çelişkiyi
#: hiç denetlemiyordu. Tanım artık burada, uç buradan ithal eder.
TRAJECTORY_PROPELLANT_REL_TOL = 0.01

#: ISA deniz seviyesi ses hızı [m/s] — a = sqrt(gamma * R_spec * T_0),
#: T_0 = ISA_LAYERS[0][1]. TÜRETİLİR, yazılmaz.
ISA_SEA_LEVEL_SPEED_OF_SOUND = float(
    np.sqrt(GAMMA_AIR * R_SPECIFIC_AIR * ISA_LAYERS[0][1]))

#: ÖH D24 / termo-ucus a2 — ATIŞ KOŞULU BANTLARI, TEK KAYNAK (P4B3-16,
#: Fable-D18 ŞART).
#:
#: ÖLÇÜLDÜ (``a2/once.json`` K2, taban 88a29d3): bant tablosu
#: ``hrma/app.py`` içinde ``_LP_BANTLAR`` adıyla YALNIZ
#: ``/api/trajectory-analysis``in gövdesinde yaşıyordu; kardeş
#: ``/api/six-dof-analysis`` kendi ``ranges=`` sözlüğünü ayrıca yazıyordu ve
#: kütüphaneyi DOĞRUDAN çağıran yol (``/calculate`` → ``calculate_trajectory``)
#: hiç bant görmüyordu. Aynı büyüklük üç ayrı yerde tanımlıydı.
#:
#: Tablo bir SÖZLÜKTÜR: alan -> (alt, üst, birim, dayanak). Bantların hiçbiri
#: keyfî değildir; her biri ya bir TANIM KÜMESİ ya da bu depoda TANIMLI bir
#: büyüklüktür:
#:   * ``launch_angle``: ufuktan yükseliş açısı; 90° = dik yukarı (bu modülün
#:     kendi konvansiyonu, bkz. ``calculate_trajectory``). Negatif açı yere
#:     doğru atıştır ve bu çözücünün modeli değildir.
#:   * ``wind_direction``: pusula yönü, [0, 360] tanım kümesi.
#:   * enlem/boylam: WGS84 ondalık derece tanım kümesi (negatif MEŞRUDUR).
#:   * ``altitude``: ISA tablosunun KENDİ geçerlilik aralığı —
#:     ``ISA_TABLE_BOTTOM_M`` (USSA 1976 tablo tabanı, −5 km geopotansiyel)
#:     ile ``ISA_TABLE_TOP_M`` (84,852 km). Alt uç, ``_atm_full``in fiilen
#:     reddettiği sınırın TA KENDİSİDİR (tek sabit, iki tüketici); üst uç
#:     tablonun tepesidir. Eski ``(-500, 80000)`` çifti hiçbir büyüklüğe
#:     bağlı değildi.
#:   * ``wind_speed``: rüzgâr bu çözücüde hava kütlesinin YARI-DURAĞAN hızıdır
#:     ve araç hızına doğrudan eklenir. Ses hızını aşan bir "rüzgâr" artık
#:     rüzgâr değildir (kendi başına bir şok taşır) ve sürükleme modelinin
#:     bağıl-Mach kabulünü geçersiz kılar; üst uç bu yüzden ISA deniz seviyesi
#:     SES HIZINA bağlanmıştır — türetilmiş bir büyüklük, ikinci kez yazılan
#:     bir sayı değil. Ölçek için: Yer yüzeyinde ölçülmüş EN YÜKSEK rüzgâr
#:     113,2 m/s'dir (WMO Archive of Weather and Climate Extremes, Barrow
#:     Island, Avustralya, 10 Nisan 1996), yani bant gerçek meteorolojiye göre
#:     bilerek GENİŞTİR: görevi rüzgâr olmayan sayıları reddetmektir.
#:     Eski 150 m/s'nin dayanağı yazılı değildi.
LAUNCH_CONDITION_BANDS = {
    'launch_angle': (0.0, 90.0, 'degree',
                     'elevation above the horizon; 90 deg is straight up '
                     '(this solver convention)'),
    'wind_speed': (0.0, ISA_SEA_LEVEL_SPEED_OF_SOUND, 'meter_per_second',
                   'quasi-steady air-mass speed added to the vehicle '
                   'velocity; the upper end is the ISA sea-level speed of '
                   'sound sqrt(gamma*R*T_0), above which a "wind" is not a '
                   'wind. Highest surface wind ever measured: 113.2 m/s '
                   '(WMO, Barrow Island 1996)'),
    'wind_direction': (0.0, 360.0, 'degree',
                       'meteorological compass bearing the wind comes FROM'),
    'latitude': (-90.0, 90.0, 'degree', 'WGS84 decimal degrees'),
    'longitude': (-180.0, 180.0, 'degree', 'WGS84 decimal degrees'),
    'altitude': (ISA_TABLE_BOTTOM_M, ISA_TABLE_TOP_M, 'meter',
                 'the validity range of the USSA 1976 layer table this '
                 'solver integrates the atmosphere from; the lower end is '
                 'the same constant _atm_full refuses below'),
}

#: Çözücünün ``launch_params`` anahtarlarını yukarıdaki banda bağlayan eşleme.
#: HTTP uçları kendi alan adlarını kendi eşlemeleriyle bağlar; tablo TEKTİR.
LAUNCH_PARAM_BAND_KEYS = {
    'launch_angle': 'launch_angle',
    'launch_altitude': 'altitude',
    'wind_speed': 'wind_speed',
    'wind_direction': 'wind_direction',
    'launch_latitude': 'latitude',
    'launch_longitude': 'longitude',
}


class TrajectoryInputError(ValueError):
    """Çözücünün girdi reddi — ALAN LİSTESİ taşıyan İSTEMCİ hatası.

    ÖH D16 / termo-ucus a1, defter P16B3-14. ÖLÇÜLDÜ (``once.json`` K1):
    ``_guard_solver_inputs`` doğru şeyi yapıyordu — geçersiz girdide
    ``ValueError`` atıyordu — ama ``/api/trajectory-analysis`` bunu
    ``except Exception`` dalında yakalayıp **HTTP 500** veriyor ve tam
    traceback'i sunucu çıktısına basıyordu. Üç vaka ölçüldü
    (``thrust=-1000``, ``burn_time=-10``, ``final_mass=-10``): üçü de 500,
    üçü de stdout'a traceback (1.133-1.141 bayt). Kullanıcı hatası sunucu
    arızası gibi görünüyordu ve gövdede alan adı YOKTU — yalnız Türkçe bir
    istisna metni vardı (İngilizce API'de).

    ``ValueError`` türevidir: onu yakalamayan eski çağıranlar (``/calculate``
    ``_butce_ile_kos`` dalı, tarama uçları) ESKİSİ GİBİ davranır. Yakalayan
    uç ``problems`` listesinden makine-okur ``invalid_fields`` üretir.

    ``problems``: ``{'field': ..., 'reason': ..., 'value': ...}`` kayıtları.
    ``field`` ÇÖZÜCÜ adıdır (``motor_data.thrust``, ``vehicle_mass_dry``);
    isteğin alan adına çeviri UÇ katmanının işidir — çözücü kendisini kimin
    çağırdığını bilmez ve istek sözlüğünü uydurmaz.
    """

    def __init__(self, message, problems=None):
        super().__init__(message)
        self.problems = list(problems or [])

# --- KURTARMA SİSTEMİ (paraşüt) varsayılanları ---------------------------
# F080 (v2.6.2): paraşüt alanı eskiden ``_calculate_descent_flight`` içine
# 2.0 m² olarak SABİT KODLANMIŞTI ve kullanıcı girdisi yoktu; buna rağmen
# ``landing_velocity`` bir GÜVENLİK metriği olarak raporlanıyordu.
# ÖLÇÜLDÜ (20 kg kuru araç): raporlanan iniş hızı 10.70 m/s; alan 0.5 m²
# olsaydı ~21 m/s, 5 m² olsaydı ~6.8 m/s — yani metrik tamamen sabit koda
# bağlıydı. Artık alan kullanıcı girdisidir; verilmezse aşağıdaki değer
# AÇIKÇA "varsayım" olarak işaretlenir ve uyarı üretilir (uydurma bir
# araç-ölçekli tasarım kuralı türetilmez).
DEFAULT_PARACHUTE_AREA_M2 = 2.0

# Paraşüt sürükleme katsayısı. ALAN KONVANSİYONU: İZDÜŞÜM (projected)
# alanı S_p. İçi boş yarımküre için Cd_p ≈ 1.42 (Hoerner, "Fluid-Dynamic
# Drag", 1965, Böl. 3). DİKKAT: Knacke, "Parachute Recovery Systems Design
# Manual" (1992) tabloları NOMİNAL alan S_0 tabanlıdır ve aynı paraşüt için
# Cd_0 ≈ 0.62-0.80 verir; iki sayı farklı alan tanımına aittir. Eski kod
# Cd=1.4'ü Knacke'ye atfediyordu — atıf yanlıştı, sayı (izdüşüm alanıyla
# kullanıldığı sürece) doğru. Kullanıcı Knacke tabanlı Cd_0 girmek isterse
# alanı da nominal alan olarak vermelidir.
DEFAULT_PARACHUTE_CD = 1.4

# Apojeden sonra paraşütün açılmasına kadar geçen gecikme [s] (modelin
# kendi varsayımı; gerçek sistemde zaman gecikmeli/barometrik ayırma).
DEFAULT_PARACHUTE_DEPLOY_DELAY_S = 2.0

# ÖH D22 / OH-D18-05 — İNİŞ HÜKMÜNÜN GERİ ÇEKİLME GEREKÇESİ (tek kaynak).
# Paraşüt izdüşüm alanı verilmediğinde iniş fazı ÇÖZÜLMEZ ve iniş hükmünü
# taşıyan bütün yapraklar ``None`` kalır. Metin hem faz sözlüğünde hem üst
# düzey ``recovery`` özetinde aynı yerden okunur — aynı gerekçeyi iki
# yerde iki cümleyle yazmak, kullanıcıya iki farklı sebep söylemektir.
# DİKKAT: ``DEFAULT_PARACHUTE_AREA_M2`` sabiti SİLİNMEDİ; kullanıcı alanı
# açıkça o değere ayarlarsa eski sayı birebir üretilebilsin diye
# (regresyon kilidi) ve yukarıdaki F080 kaydının ölçümü okunabilir kalsın
# diye duruyor. Artık hiçbir kod yoluna SESSİZCE girmiyor.
LANDING_WITHHELD_NO_PARACHUTE = (
    'NOT_MODELLED: the descent was not solved because '
    'launch_params["parachute_area"] (parachute PROJECTED area, m2) was not '
    'supplied. Landing velocity, landing time, landing point, total flight '
    'time and range all scale directly with that area, so none of them is '
    'published. Supply the area to obtain a descent solution.')

# --- KALKIŞ EŞİĞİ (ÖH D17 / P4B3-13) --------------------------------------
# "Araç pedden ayrıldı mı?" sorusunun TEK EŞİĞİ. Sayısal bir gürültü payıdır
# (yer düzleminde başlayan çözümde z tam 0,0 değil ±1e−15 mertebesinde
# gezinir), fizik eşiği değildir. Kardeş altı-serbestlik çözücüsü bu sabiti
# BURADAN ithal eder — aynı hükmü iki modülde iki sayıyla vermek, aynı
# uçuşa iki farklı "kalktı/kalkmadı" cevabı vermek demektir.
LIFTOFF_ALTITUDE_EPS_M = 1e-6

# --- RÜZGÂR BİLEŞENİ GÜRÜLTÜ TABANI (ÖH D17 / P4B3-14) --------------------
# ``sin(pi)`` tam 0,0 değil −1,22e−16'dır; 180°'lik (tamamen düzlem-içi) bir
# rüzgârda çapraz bileşen bu yüzden −1,84e−15 m/s çıkıyor. Bu SAYISAL
# gürültüdür, modellenmeyen bir fizik değil — hüküm (menzil alt sınır mı?)
# ona bakarak verilemez. Bağıl taban, projenin kayan nokta gürültü tabanıyla
# aynı mertebededir (1e−12).
WIND_COMPONENT_NOISE_REL = 1e-12

# --- ÇÖZÜCÜ PENCERELERİ (zaman-aşımı tavanları) ---------------------------
# Bu üç sayı ENTEGRASYON UFKUDUR, sonuç değildir. Faz 5 / B1'de ölçüldü:
# olay (apoje / yere temas) tetiklenmediğinde kod pencerenin SON noktasını
# "apoje" ve "iniş" diye yayımlıyordu — 30° atışta apoje −54 722 m, uçuş
# süresi tam olarak (t_b+2)+300+1000 = 1306 s çıkıyordu, yani üç tavanın
# toplamı. Artık her fazın hangi OLAYLA bittiği ``end_reason`` ile
# yayımlanır ve tavana çarpan koşuda türetilmiş büyüklükler None olur.
POWERED_PHASE_MARGIN_S = 2.0     # yanma sonrası geçiş payı
COASTING_TIME_LIMIT_S = 300.0    # yanma-sonu → apoje penceresi
# İniş penceresi 1000 s -> 3600 s. GEREKÇE (ölçülmüş): 20 kg araç + 20 m²
# paraşütte iniş hızı 3,41 m/s'dir ve 4 km'den inmek 1071 s sürer — yani
# TAMAMEN GERÇEKÇİ bir kurtarma tasarımı eski 1000 s tavanını aşıyordu ve
# kod tavanı "iniş" diye yayımlıyordu. Tavan bir sonuç değil, sayısal
# ufuktur; geniş tutulması hiçbir uçuşun sayısını DEĞİŞTİRMEZ (yere temas
# olayı zaten daha önce sonlandırır), yalnız "bilinmiyor" hâllerini azaltır.
# Maliyet ölçüldü: 50 m² paraşütte 0,097 s -> 0,169 s.
DESCENT_TIME_LIMIT_S = 3600.0    # apoje → yere temas penceresi

# Yer teması olayının "kurulma" anı [s]. Araç t=0'da tam olarak yer
# düzlemindedir (z = launch_altitude); olay fonksiyonu bu anda sıfır
# olduğundan kalkışta hemen tetiklenmesin diye ilk anlarda pozitif ofset
# uygulanır. Kardeş 6-DOF modülü aynı deseni kullanır
# (``six_dof_trajectory.solve.hit_ground``: ``y[2] + 1e-6 if t < 1.0``).
GROUND_EVENT_ARM_S = 0.05


def _mk_warning(code, severity='warning', **params):
    """Uyarı sözleşmesi: ``{code, params, severity}`` (v2.6.2 D-track)."""
    return {'code': code, 'params': params, 'severity': severity}


def _finite_or_none(value) -> Optional[float]:
    """Sonlu bir float ise değeri, değilse None döndürür (sessiz yedek YOK)."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if np.isfinite(f) else None


def _as_list(values) -> list:
    """Plotly izlerine giren diziyi düz Python listesine çevirir.

    Plotly 6.x numpy dizilerini JSON'a base64 'bdata' bloğu olarak yazar;
    uygulamada yüklü plotly.js 1.58.5 bu formatı tanımadığı için grafik
    BOŞ çizilir (v2.5.2 sistemik düzeltmesi).
    """
    if isinstance(values, np.ndarray):
        return [float(v) for v in values.tolist()]
    return [float(v) for v in values]


def normalize_thrust_curve(thrust_curve):
    """``{'time': [...], 'thrust': [...]}`` -> ``(t, F, toplam_impuls)``.

    TEK KAYNAK (ÖH D16 / termo-ucus a1, defter OH-D15-08 + P12bB2-09).
    Bu doğrulama zinciri kardeş 6-DOF çözücüsünde zaten yazılıydı
    (``six_dof_trajectory.SixDOFTrajectory.__init__``) ve o modül eğriyi
    2026'dan beri tüketiyor; düzlemsel çözücü ise ``motor_data['thrust']``i
    SKALER okuyup dikdörtgen bir profil kuruyordu. Aynı sözleşmenin ikinci
    bir kopyasını yazmak yerine doğrulama buraya taşındı ve 6-DOF buradan
    çağırıyor — iki çözücü aynı eğriyi aynı kurallarla okur.

    Kurallar (kardeş modülden AYNEN):
      * ``time``/``thrust`` 1B ve eşit uzunlukta, en az 2 nokta;
      * hepsi sonlu;
      * ``t[0] > 0`` ise başa ``(0, F[0])`` eklenir (motor t=0'da yanıyor
        kabul edilir — eğri geç başlamışsa boşluk UYDURULMAZ, ilk değer
        taşınır ve bu davranış kardeş modülde de böyledir).

    Hata durumunda :class:`TrajectoryInputError` atılır: alan adı
    ``thrust_curve``, gerekçe makine-okur. Böylece uç katmanı 500 değil
    422 verir (P16B3-14 ile aynı taşıyıcı).
    """
    def _red(reason, detail):
        raise TrajectoryInputError(
            'Yörünge çözücüsü geçersiz itki eğrisiyle çağrıldı: ' + detail,
            problems=[{'field': 'thrust_curve', 'reason': reason}])

    try:
        t = np.asarray(thrust_curve['time'], dtype=float)
        F = np.asarray(thrust_curve['thrust'], dtype=float)
    except (TypeError, ValueError, KeyError, IndexError):
        _red('not_a_thrust_curve',
             "thrust_curve 'time' ve 'thrust' sayı dizileri olmalı")
    if t.ndim != 1 or F.ndim != 1:
        _red('not_1d', "thrust_curve 'time' ve 'thrust' 1B dizi olmalı")
    if t.size != F.size:
        _red('length_mismatch',
             "thrust_curve 'time' ve 'thrust' aynı uzunlukta olmalı "
             f'(time={t.size}, thrust={F.size})')
    if t.size < 2:
        _red('too_few_points',
             "thrust_curve en az 2 nokta içermeli "
             "('time' boş ya da tek noktalı)")
    if not (np.all(np.isfinite(t)) and np.all(np.isfinite(F))):
        _red('not_finite',
             "thrust_curve 'time'/'thrust' sonlu olmayan değer içeriyor")
    if np.any(np.diff(t) <= 0.0):
        _red('time_not_increasing',
             "thrust_curve 'time' kesin artan olmalı")
    if np.any(F < 0.0):
        _red('negative_thrust',
             "thrust_curve 'thrust' negatif değer içeriyor")
    # NEGATİF ZAMAN (ÖH D18 / OH-D15-08 ŞART, Fable-D16 termo-ucus).
    #
    # Yayımlanmış bir itki eğrisi t < 0'da başlayamaz. Gerekçe adı
    # ``hrma/importers/motor_file.py`` (RASP/RSE içe aktarımı) içindeki
    # kardeş kapıyla AYNEN AYNIDIR (``negative_time``): iki kanal da aynı
    # sözleşmeyi konuşur, tüketici tek bir ad öğrenir.
    #
    # ÖLÇÜLDÜ (``once.json`` K1, taban 9071a64):
    # ``{'time': [-0.1, 0.0, 1.0], 'thrust': [0.0, 100.0, 100.0]}`` KABUL
    # ediliyordu ve toplam impuls 105,0 N·s çıkıyordu — t >= 0 dilimin
    # gerçek impulsü 100,0 N·s (%5,0 fazla). Negatif dilim ayrıca
    # aşağıdaki örtük ateşleme kuralını (``t[0] > 0`` -> başa ``(0, F[0])``
    # ekle) devre dışı bırakıyordu. Kardeş 6-DOF çözücüsü bu fonksiyonu
    # çağırdığı için (``six_dof_trajectory.SixDOFTrajectory.__init__``)
    # ret oraya da iner — tek kaynak.
    if np.any(t < 0.0):
        _red('negative_time',
             "thrust_curve 'time' negatif değer içeriyor "
             f'(en küçük {float(np.min(t)):g} s); bir itki eğrisi '
             't = 0 s ya da sonrasında başlamalıdır')
    if t[0] > 0.0:
        t = np.insert(t, 0, 0.0)
        F = np.insert(F, 0, F[0])
    impulse = float(_trapezoid(F, t))
    if not (impulse > 0.0):
        _red('zero_impulse',
             'thrust_curve toplam impulsü sıfır — yanmayan bir motorun '
             'yörüngesi hesaplanamaz')
    return t, F, impulse


class TrajectoryAnalyzer:
    """Complete trajectory analysis for hybrid rocket motors"""

    def __init__(self):
        # Earth parameters
        self.g0 = G_0  # Standard gravity (m/s²) -- hrma.constants.G_0 ile tutarlı
        self.R_earth = 6371000  # Earth radius (m)
        # Geopotential height conversion için referans yarıçap (US Std Atm 1976)
        self.R_geopotential = 6356766.0  # m

        # --- Fırlatma sahası katmanı (v1, 2026-07-22) -------------------
        # g_surface: SAHADAKİ yerel yerçekimi (enlem + rakım). Yalnız ağırlık
        # ve T/W'ye girer. self.g0 (=9.80665) DEĞİŞMEZ: Isp tanımı, ideal
        # delta-v ve USSA 1976 basınç formülleri onunla yazılır.
        # Varsayılanlar tam olarak eski davranışı verir (regresyon kilidi:
        # g_surface == g0, sıcaklık kayması 0, basınç oranı 1).
        self.g_surface = G_0        # m/s², saha yerel yerçekimi
        self.site_temp_offset_k = 0.0   # ölçülen/standart-dışı gün ΔT
        self.site_pressure_ratio = 1.0  # ölçülen yüzey basıncı / ISA
        self.launch_site = None     # launch_site.resolve_launch_site() çıktısı
        # ÖH D15 (P4B3-05): saha kotu (yer düzlemi) [m ASL]. Metrik katmanı
        # oranları bu DATUMLA kurar; koşu öncesi 0,0'dır (deniz seviyesi).
        self.ground_level_m = 0.0

        self.atmosphere_model = 'standard'  # 'standard' or 'custom'

        # Default vehicle parameters
        self.vehicle_mass_dry = 50  # kg
        self.vehicle_diameter = 0.15  # m
        # NOT: drag_coefficient artık SUBSONIK referans Cd0 olarak kullanılır.
        # Gerçek Cd Mach sayısına göre _drag_coefficient_mach() ile ölçeklenir.
        self.drag_coefficient = 0.5
        self.vehicle_length = 2.0  # m

        # --- Kurtarma sistemi (F080) ------------------------------------
        # None = kullanıcı vermedi -> varsayım kullanılır ve işaretlenir.
        self.parachute_area = None          # m² (izdüşüm alanı)
        self.parachute_cd = DEFAULT_PARACHUTE_CD
        self.parachute_deploy_delay = DEFAULT_PARACHUTE_DEPLOY_DELAY_S
        # v2.6.26 — Cd ve gecikme için de "kullanıcı verdi mi" bayrağı.
        # Alan için `parachute_area is None` bu bilgiyi taşıyordu; Cd ve
        # gecikmenin varsayılanı sayısal olduğu için ayırt edilemiyordu ve
        # varsayım SESSİZ kalıyordu.
        self._parachute_cd_supplied = False
        self._parachute_delay_supplied = False

        # --- İTKİ EĞRİSİ (ÖH D16 / OH-D15-08) ---------------------------
        # None = eğri VERİLMEDİ -> itki skaler okunur ve yanma boyunca
        # dikdörtgen profil uygulanır (eski davranış, BİT-AYNI).
        # Doldurulduğunda: (t[], F[], toplam_impuls). Kardeş 6-DOF
        # çözücüsündeki ``thrust_curve=`` yapıcı argümanının düzlemsel
        # karşılığıdır — açık bir API'dir, motor sözlüğünden sessizce
        # kazılmaz (``/calculate`` yolunun davranışı değişmez).
        self._thrust_curve = None

        # --- İTKİNİN İRTİFA TELAFİSİ (ÖH D18 / P4B3-22) ------------------
        # F(h) = F_ref + (P_ref − P_amb(h))·A_e  (Sutton & Biblarz, "Rocket
        # Propulsion Elements", Böl. 3). Nozul çıkış alanı BİLİNMEDEN bu
        # düzeltme yapılamaz ve UYDURULMAZ: A_e bir tasarım büyüklüğüdür,
        # itki ve yanma süresinden türetilemez. Kardeş 6-DOF çözücüsü aynı
        # sözleşmeyi kullanır (``six_dof_trajectory._thrust_at_altitude``,
        # ``nozzle_exit_area`` / ``thrust_reference_pressure``); orada
        # verilmediğinde ``warn.sixdof.thrust_not_altitude_compensated``
        # üretiliyor, düzlemsel çözücüde ise TEK BİR beyan bile yoktu
        # (ölçüldü: ``once.json`` K7 — uyarı kodları arasında irtifa
        # telafisine dair hiçbir şey yok).
        self.nozzle_exit_area = None
        self.thrust_reference_pressure = None

        # Bu koşuda üretilen uyarılar ({code, params, severity})
        self.warnings = []

    def set_nozzle_exit(self, exit_area_m2, reference_pressure_pa=None
                        ) -> None:
        """Nozul çıkış alanı + itkinin ölçüldüğü ortam basıncı (P4B3-22).

        Verilirse güçlü faz itkiyi irtifayla telafi eder:
        ``F(h) = F_ref + (P_ref − P_amb(h))·A_e``. ``reference_pressure_pa``
        verilmezse fırlatma irtifasındaki ISA basıncı alınır — bu bir
        UYDURMA değil, "verilen itki sahada ölçüldü" sözleşmesidir ve
        kardeş 6-DOF çözücüsünün yaptığının aynısıdır
        (``_pressure_at(self.launch_altitude)``).

        ``exit_area_m2`` None/0/negatifse telafi KAPALI kalır (alan
        türetilmez) ve ``calculate_trajectory``
        ``warn.trajectory.thrust_not_altitude_compensated`` üretir.
        """
        alan = _finite_or_none(exit_area_m2)
        self.nozzle_exit_area = alan if (alan is not None and alan > 0.0) \
            else None
        basinc = _finite_or_none(reference_pressure_pa)
        self.thrust_reference_pressure = (
            basinc if (basinc is not None and basinc >= 0.0) else None)

    def set_thrust_curve(self, thrust_curve) -> None:
        """İtki-zaman eğrisini ayarlar — ÖH D16 / OH-D15-08 + P12bB2-09.

        ÖLÇÜLDÜ (``once.json`` K2, onarımdan önce): ``thrust_curve`` adı bu
        modülün kaynağında BİR KEZ BİLE geçmiyordu (0 geçiş) ve
        ``/api/trajectory-analysis``e tepe/ortalama oranı **3,0** olan
        gerçek bir eğri gönderildiğinde apoje, aynı ortalama itkinin
        dikdörtgen profiliyle **birebir aynı** çıkıyordu (11.854,442870054 m,
        bağıl fark 0,0). Yani eğri gönderiliyor, uç onu yankılamıyor bile,
        çözücü görmüyordu: panel tek skaler ``average_thrust`` göndersin ya
        da 401 noktalı gerçek eğriyi göndersin, sonuç DEĞİŞMİYORDU.

        ``thrust_curve``: ``{'time': [s...], 'thrust': [N...]}`` — kardeş
        6-DOF çözücüsüyle AYNI sözleşme (``normalize_thrust_curve``).
        ``None`` verilirse eğri kalkar ve skaler yola dönülür.

        Eğri kurulduğunda çözücü:
          * itkiyi ``F(t)`` ile (doğrusal ara değer) uygular;
          * kütle debisini ``ṁ(t) = m_p·F(t)/I_toplam`` alır — yani yakıt
            İTKİYLE ORANTILI harcanır ve integrali TAM ``m_p`` eder
            (kardeş 6-DOF'un birikimli impuls kütlesiyle aynı doktrin).
            Dikdörtgen profilin sabit ``m_p/t_b`` debisi bir eğride
            yanlıştır: tepe anında gerçekte üç kat yakıt akar.
        """
        if thrust_curve is None:
            self._thrust_curve = None
            return
        self._thrust_curve = normalize_thrust_curve(thrust_curve)

    def set_recovery_parameters(self, parachute_area: Optional[float] = None,
                                parachute_cd: Optional[float] = None,
                                deploy_delay: Optional[float] = None) -> None:
        """Kurtarma (paraşüt) parametrelerini ayarlar — F080.

        parachute_area: paraşüt İZDÜŞÜM alanı [m²]. None/geçersiz -> varsayım.
        parachute_cd:   izdüşüm alanı tabanlı Cd (varsayılan 1.4, Hoerner).
        deploy_delay:   apojeden sonra açılma gecikmesi [s].
        """
        if parachute_area is not None:
            try:
                a = float(parachute_area)
            except (TypeError, ValueError):
                a = float('nan')
            self.parachute_area = a if np.isfinite(a) and a > 0.0 else None
        if parachute_cd is not None:
            try:
                c = float(parachute_cd)
            except (TypeError, ValueError):
                c = float('nan')
            if np.isfinite(c) and c > 0.0:
                self.parachute_cd = c
                self._parachute_cd_supplied = True
        if deploy_delay is not None:
            try:
                t = float(deploy_delay)
            except (TypeError, ValueError):
                t = float('nan')
            if np.isfinite(t) and t >= 0.0:
                self.parachute_deploy_delay = t
                self._parachute_delay_supplied = True

    def set_vehicle_parameters(self, mass_dry: float, diameter: float,
                               drag_coefficient: float = 0.5, length: float = 2.0):
        """Set vehicle physical parameters.

        drag_coefficient: SUBSONIK (M<0.8) referans sürükleme katsayısı Cd0.
        Transonik/supersonik bantlarda Mach'a bağlı olarak ölçeklenir.
        """
        self.vehicle_mass_dry = mass_dry
        self.vehicle_diameter = diameter
        self.drag_coefficient = drag_coefficient
        self.vehicle_length = length

    # ------------------------------------------------------------------
    # FIRLATMA SAHASI: konum -> yerel g + yüzey atmosfer datumu
    # ------------------------------------------------------------------
    def set_launch_site(self, site: Optional[Dict]) -> None:
        """hrma.analysis.launch_site.resolve_launch_site() çıktısını uygular.

        Etkisi YALNIZCA üç yerdedir:
          1. Ağırlık terimi (dinamikteki g) -> g_surface
          2. İtki/ağırlık oranı              -> g_surface
          3. Atmosfer datumu (ΔT, P oranı)   -> ISA profili kaydırılır

        DOKUNULMAYANLAR: Isp, ideal delta-v ve USSA 1976 basınç bağıntıları
        standart g0 = 9.80665 ile hesaplanmaya devam eder.

        site None ya da boşsa tüm alanlar varsayılana döner ve sonuçlar
        saha katmanı hiç eklenmemiş gibi BİREBİR aynı olur.
        """
        if not site:
            self.g_surface = G_0
            self.site_temp_offset_k = 0.0
            self.site_pressure_ratio = 1.0
            self.launch_site = None
            return
        self.launch_site = site
        g_local = site.get('gravity_local_m_s2')
        if not g_local and site.get('latitude_deg') is not None:
            # ÖH D15 / P4B3-06 — SAHA SÖZLÜĞÜNÜN İKİ BİÇİMİ AYNI g'yi verir.
            # Sözleşme "resolve_launch_site() çıktısı YA DA en az
            # {'latitude_deg','longitude_deg'} taşıyan sözlük" diyor; ham
            # biçimde ``gravity_local_m_s2`` yoktur ve g sessizce standart
            # g0'a düşüyordu. ÖLÇÜLDÜ (/calculate, 38°K, 2000 m): motor
            # bloğu gravity_local_m_s2 = 9,793759 yayımlarken aynı yanıtın
            # yörünge T/W'si 9,80665 ile hesaplanıyordu. Yerel g artık
            # motorunkiyle AYNI fonksiyondan (launch_site.local_gravity,
            # NIMA TR8350.2 Denk. 4-3) türetilir — tek kaynak.
            try:
                from hrma.analysis.launch_site import local_gravity
                g_local = local_gravity(
                    float(site['latitude_deg']),
                    float(site.get('elevation_m') or 0.0))
            except (TypeError, ValueError, KeyError):
                g_local = None
        self.g_surface = float(g_local) if g_local else G_0
        self.site_temp_offset_k = float(site.get('temperature_offset_k', 0.0) or 0.0)
        ratio = site.get('pressure_ratio', 1.0)
        self.site_pressure_ratio = float(ratio) if ratio else 1.0

    # ------------------------------------------------------------------
    # AERODİNAMİK: Mach-bağımlı sürükleme katsayısı
    # ------------------------------------------------------------------
    def _drag_coefficient_mach(self, mach: float) -> float:
        """Mach-bağımlı sürükleme katsayısı (ince, kanatçıklı sounding rocket).

        Sabit Cd FİZİKSEL OLARAK YANLIŞ: transonik bölgede dalga sürüklemesi
        nedeniyle Cd belirgin biçimde yükselir (transonik tepe), supersonikte
        düşerek yeni bir platoya oturur. Burada Cd0 = subsonik referans
        (set_vehicle_parameters ile verilen, varsayılan 0.5) alınır ve
        aşağıdaki bant oranlarıyla ölçeklenir.

        Bant oranları amatör/sounding roket aerodinamik verisinden
        (OpenRocket Technical Documentation; G. A. Crowell, "The Descriptive
        Geometry of Nose Cones"; S. F. Hoerner, "Fluid-Dynamic Drag", 1965,
        Bölüm 16; Box, Bishop & Hunt, "Estimating the dynamic and aerodynamic
        parameters of passively controlled high power rockets", 2009):
          - Subsonik  (M < 0.8)        : Cd ≈ Cd0          (sabit plato)
          - Transonik (0.8 ≤ M < 1.2)  : Cd0 -> ~1.5*Cd0 dalga sürükleme tepesi
                                          (tepe M≈1.05-1.1 civarı)
          - Supersonik(M ≥ 1.2)        : tepeden ~1.05*Cd0 platosuna doğru düşer

        Mach tepesinde Cd ~1.5x subsonik değer (Hoerner; OpenRocket) — sayısal
        olarak konservatif (drag'i abartmak güvenli yönde DEĞİLDİR irtifa için,
        ama tehlikeyi az gösteren = irtifayı abartan davranış engellenir:
        transonik tepe modellenerek apogee tahmini şişirilmez).

        Args:
            mach: Bağıl hıza karşılık gelen Mach sayısı (>= 0)

        Returns:
            Cd (boyutsuz)
        """
        cd0 = self.drag_coefficient
        m = max(float(mach), 0.0)

        # Bant oranları (subsonik Cd0'a göre çarpan)
        TRANSONIC_PEAK = 1.5   # transonik tepe çarpanı (Hoerner/OpenRocket)
        SUPERSONIC_PLATEAU = 1.05  # yüksek supersonik plato çarpanı

        if m < 0.8:
            # Subsonik plato: Cd ≈ Cd0 (basınç+sürtünme sürüklemesi sabit)
            factor = 1.0
        elif m < 1.05:
            # Subsonik -> transonik tepe: lineer yükseliş (0.8..1.05)
            frac = (m - 0.8) / (1.05 - 0.8)
            factor = 1.0 + frac * (TRANSONIC_PEAK - 1.0)
        elif m < 1.2:
            # Transonik tepe -> supersonik geçiş başlangıcı (1.05..1.2)
            frac = (m - 1.05) / (1.2 - 1.05)
            # Tepeden, M=1.2'de ara değere (1.3*Cd0) doğru hafif düşüş
            mid = 1.3
            factor = TRANSONIC_PEAK + frac * (mid - TRANSONIC_PEAK)
        else:
            # Supersonik: M=1.2'de 1.3*Cd0'dan başlayıp ~1.05*Cd0 platosuna
            # üstel azalış (dalga sürüklemesinin Mach ile zayıflaması).
            mid = 1.3
            # tau: M arttıkça platoya yaklaşma hızı (amatör roket verisi)
            tau = 2.0
            factor = SUPERSONIC_PLATEAU + (mid - SUPERSONIC_PLATEAU) * np.exp(-(m - 1.2) / tau)

        return cd0 * factor

    # ------------------------------------------------------------------
    # RÜZGAR yardımcıları
    # ------------------------------------------------------------------
    @staticmethod
    def _wind_vector(wind_speed: float, wind_direction_rad: float) -> Tuple[float, float]:
        """Rüzgar hız vektörünü (yatay, dikey) döndürür.

        KONVANSIYON (F082 düzeltmesi, v2.6.2): ``wind_direction`` rüzgârın
        GELDİĞİ yöndür (meteorolojik standart: "kuzey rüzgârı" = kuzeyden
        esen). Dolayısıyla hava kütlesinin hız vektörü o yönün TERSİDİR:

            v_hava = −V · (cos φ, sin φ)

        Eski kod ``+V·cos φ`` kullanıyor ve docstring'inde rüzgârın "ESTİĞİ
        yön" diyordu; kardeş modül ``six_dof_trajectory.__init__`` ise doğru
        konvansiyonu (``self.wind = −V·[cos, sin, 0]``) uyguluyordu. Aynı
        üründe aynı isimli girdi iki panelde TERS anlam taşıyordu.

        ÖLÇÜLDÜ (15 m/s rüzgâr, 85° atış, 20 kg araç): wind_direction=0 için
        menzil +6395.9 m raporlanıyordu; doğru konvansiyonda −6395.9 m
        (rüzgâr kuzeyden estiği için araç güneye sürüklenir). Konvansiyon
        işareti yüzünden iniş noktası ~10.5 km ötelenmiş oluyordu.

        Dikey rüzgar ihmal (vz_wind=0) çünkü meteorolojik rüzgâr yataydır.

        BOYUT (ÖH D17 / P4B3-14): bu çözücü DÜZLEMSELDİR — durum vektörü
        ``(x, z, vx, vz)``, yani TEK yatay eksen taşır. Dönen ikilinin ilk
        yuvası o düzlem-içi eksen, ikinci yuvası DİKEY eksendir; ``sin φ``
        ile verilen çapraz-menzil bileşeni bu modelde TAŞINAMAZ.
        Docstring'in ``−V·(cos φ, sin φ)`` yazması (iki YATAY bileşen)
        kodun yaptığı işle uyuşmuyordu ve düşen bileşen hiçbir yerde
        beyan edilmiyordu: ÖLÇÜLDÜ (once.json K6) — 15 m/s rüzgâr,
        yön 90° -> ``_wind_vector`` (−9,18e−16, 0,0), yani rüzgârın TAMAMI
        sessizce düşüyor ve menzil rüzgârsız koşumla birebir aynı çıkıyor.
        Beyan ``_wind_components`` üzerinden yapılır; çapraz bileşeni
        gerçekten entegre eden model altı-serbestlik çözücüsüdür
        (``six_dof_trajectory``, üç boyutlu ``self.wind``).

        Kaynak: WMO rüzgâr yönü tanımı (rüzgâr yönü = geldiği yön);
        McCoy, "Modern Exterior Ballistics", 1999 (aynı konvansiyon).
        """
        vx_wind = -wind_speed * np.cos(wind_direction_rad)
        vz_wind = 0.0  # yatay rüzgar varsayımı
        return vx_wind, vz_wind

    @staticmethod
    def _wind_components(wind_speed: float,
                         wind_direction_rad: float) -> Dict:
        """Rüzgârın düzlem-içi ve MODELLENMEYEN çapraz bileşenini ölçer.

        TEK KAYNAK: düzlem-içi bileşen ``_wind_vector``in ta kendisinden
        okunur (ikinci bir ``cos`` yazılmaz); çapraz bileşen aynı
        konvansiyonun ``sin`` ayağıdır (hava kütlesi hızı = −V·yön).

        Dönen sözlük ÜRÜN YÜZÜNE çıkar: kullanıcı 90°'lik bir rüzgâr girip
        menzilin hiç değişmediğini gördüğünde bunun modelin boyutundan
        geldiğini okuyabilmelidir.
        """
        in_plane, vertical = TrajectoryAnalyzer._wind_vector(
            wind_speed, wind_direction_rad)
        cross_plane = -float(wind_speed) * float(np.sin(wind_direction_rad))
        # Gürültü mü gerçek bileşen mi? (bkz. WIND_COMPONENT_NOISE_REL)
        _taban = WIND_COMPONENT_NOISE_REL * max(abs(float(wind_speed)), 1.0)
        anlamli = abs(cross_plane) > _taban
        return {
            'wind_speed_m_s': float(wind_speed),
            'wind_direction_deg': float(np.degrees(wind_direction_rad)),
            'in_plane_component_m_s': float(in_plane),
            'cross_plane_component_m_s': cross_plane,
            # ÖH D24 / termo-ucus a2 (OH-Z5-02) — UYDURMA SABİT YAPRAK
            # SÖKÜLDÜ. Buradaki eski satır
            # ``'vertical_component_m_s': float(vertical)`` idi ve ÖLÇÜLDÜ
            # (``a2/once.json`` K6, taban 88a29d3): beş ayrı (hız, yön)
            # çiftinde değer HEP 0,0 — çünkü ``_wind_vector`` düşey bileşeni
            # HESAPLAMIYOR, ``vz_wind = 0.0`` diye VARSAYIYOR (yatay rüzgâr
            # kabulü). Yani sayı bir ölçümün sonucu değil, bir kabulün
            # sayıya çevrilmiş hâliydi ve okuyucuya "düşey rüzgâr ölçüldü,
            # sıfır çıktı" diye görünüyordu. Kabul artık kabul olarak
            # yayımlanır: kardeş ``cross_plane_modelled`` ile AYNI desen.
            'vertical_component_modelled': False,
            'cross_plane_modelled': False,
            # Ham sayı yuvarlanmaz (ölçüm ölçümdür); hükmü taşıyan ayrı bir
            # bool vardır ve gürültü tabanının üstünü sorar.
            'cross_plane_significant': bool(anlamli),
            'cross_plane_noise_floor_m_s': float(_taban),
            'basis': (
                'this solver is PLANAR: the state is (x, z, vx, vz), so it '
                'carries one horizontal axis only. The in-plane component '
                '(-V*cos(direction)) is integrated; the cross-plane '
                'component (-V*sin(direction)) is NOT modelled and is '
                'reported here so the omission is visible. The VERTICAL '
                'component is not modelled either and no number is '
                'published for it: the wind vector is built from a '
                'horizontal-wind assumption, so updraughts, downdraughts '
                'and mountain waves are outside this solution entirely '
                '(vertical_component_modelled = false). Wind blowing '
                'across the launch plane therefore changes nothing in this '
                'solution — send the same case to the 6-DOF endpoint '
                '(/api/six-dof-analysis), whose wind vector is three '
                'dimensional, if the cross-range matters.'),
        }

    # ------------------------------------------------------------------
    # GİRDİ MUHAFIZI — sonlu-değer denetimi (Faz 5 / B7)
    # ------------------------------------------------------------------
    def _guard_solver_inputs(self, motor_data: Dict, launch_params: Dict) -> None:
        """Çözücüye girmeden ÖNCE sonlu-değer ve pozitiflik denetimi.

        ÖLÇÜLDÜ (Faz 5 / B7, HEAD 9d3728e): ``thrust = NaN`` ile çağrılan
        ``calculate_trajectory`` 45 saniyede DÖNMEDİ (``timeout`` çıkış kodu
        124). Sebep: NaN türevler adım kabul kriterini hiçbir zaman
        sağlamıyor, RK45 adımı sonsuza kadar küçültüyor. Tek istek bir işçi
        iş parçacığını süresiz tutar — masaüstü paketinde uygulama kilitlenir.
        Aynı hata kardeş 6-DOF çözücüsünde de ölçüldü (o da düzeltildi).

        Fail-closed: sonlu olmayan ya da fiziksel olarak imkânsız girdide
        ``ValueError`` atılır; sessizce "makul" bir yedek değer KONMAZ.
        """
        problems = []
        kayitlar = []

        def _check(name, value, *, positive=False, non_negative=False):
            f = _finite_or_none(value)
            if f is None:
                problems.append(f"{name}={value!r} sonlu bir sayı değil")
                kayitlar.append({'field': name, 'reason': 'not_finite',
                                 'value': value})
                return None
            if positive and f <= 0.0:
                problems.append(f"{name}={f!r} pozitif olmalı")
                kayitlar.append({'field': name, 'reason': 'must_be_positive',
                                 'value': f})
            elif non_negative and f < 0.0:
                problems.append(f"{name}={f!r} negatif olamaz")
                kayitlar.append({'field': name,
                                 'reason': 'must_be_non_negative',
                                 'value': f})
            return f

        # Motor: dinamiğe DOĞRUDAN giren üç büyüklük.
        _check('motor_data.thrust', motor_data.get('thrust'), non_negative=True)
        _check('motor_data.burn_time', motor_data.get('burn_time'),
               positive=True)                 # mdot = m_p / t_b → sıfır bölen
        _check('motor_data.propellant_mass_total',
               motor_data.get('propellant_mass_total'), non_negative=True)
        # Araç: kütle bölen olarak kullanılıyor (a = F/m).
        _check('vehicle_mass_dry', self.vehicle_mass_dry, positive=True)
        _check('vehicle_diameter', self.vehicle_diameter, positive=True)
        _check('drag_coefficient', self.drag_coefficient, non_negative=True)

        # Fırlatma parametreleri: yalnız VERİLENLER denetlenir.
        for key in ('launch_angle', 'launch_altitude', 'wind_speed',
                    'wind_direction', 'launch_latitude', 'parachute_area',
                    'parachute_cd', 'parachute_deploy_delay',
                    'launch_rail_length'):
            if launch_params.get(key) is not None:
                _check(f'launch_params.{key}', launch_params.get(key))

        # ÖH D24 / termo-ucus a2 (P4B3-16, Fable-D18 ŞART) — BANT KAPISI
        # ÇÖZÜCÜNÜN KENDİSİNDE.
        #
        # ÖLÇÜLDÜ (``a2/once.json`` K2, taban 88a29d3): bant tablosu YALNIZ
        # ``/api/trajectory-analysis``in gövdesindeydi (``_LP_BANTLAR``).
        # Kütüphaneyi doğrudan çağıran her yol — ``/calculate``in yörünge
        # bloğu, parametrik tarama, betikler, gömülü kullanım — bant
        # görmüyordu: ``launch_angle = -88`` sonlu olduğu için buradaki
        # denetimi geçiyor ve yere doğru bir atıştan apoje yayımlanıyordu.
        # Kapı artık burada; uç ``TrajectoryInputError``ı 422 +
        # ``invalid_fields`` olarak geçirir (kardeş desen: isp ⟷ impuls
        # bütçesi çelişkisi, P4B3-24).
        for _anahtar, _bant_adi in LAUNCH_PARAM_BAND_KEYS.items():
            _ham = launch_params.get(_anahtar)
            if _ham is None:
                continue
            _deger = _finite_or_none(_ham)
            if _deger is None:
                continue          # sonluluk denetimi yukarıda konuştu
            _alt, _ust, _birim, _dayanak = LAUNCH_CONDITION_BANDS[_bant_adi]
            if not (_alt <= _deger <= _ust):
                problems.append(
                    f'launch_params.{_anahtar} = {_deger!r} bandın dışında '
                    f'[{_alt}, {_ust}] {_birim}')
                kayitlar.append({
                    'field': f'launch_params.{_anahtar}',
                    'reason': 'out_of_range',
                    'value': float(_deger),
                    'accepted_range': [_alt, _ust],
                    'unit': _birim,
                    'band_basis': _dayanak,
                })

        if problems:
            raise TrajectoryInputError(
                'Yörünge çözücüsü geçersiz girdiyle çağrıldı: '
                + '; '.join(problems), problems=kayitlar)

    @staticmethod
    def _resolve_rail_length(launch_params: Dict) -> Optional[float]:
        """Fırlatma rayı boyunu çözer — VERİLMEDİYSE None (uydurma yok).

        Faz 5 / B2: model rayı hiç bilmiyordu, itki 1 m/s'lik keyfi bir
        eşikte hız vektörüne kilitleniyordu. Ray boyu bir GİRDİDİR; yoksa
        modellenmemiş sayılır ve bu açıkça beyan edilir.
        """
        for key in ('launch_rail_length', 'rail_length'):
            if launch_params.get(key) is not None:
                length = _finite_or_none(launch_params.get(key))
                if length is not None and length > 0.0:
                    return length
        return None

    def calculate_trajectory(self, motor_data: Dict, launch_params: Dict) -> Dict:
        """
        Calculate complete trajectory from launch to landing

        Args:
            motor_data: Motor performance data from HybridRocketEngine
            launch_params: Launch parameters (angle, location, etc.)

        Returns:
            Complete trajectory data with analysis
        """

        # B7 — çözücüye girmeden önce sonlu-değer kapısı (fail-closed).
        self._guard_solver_inputs(motor_data, launch_params)

        # Extract motor parameters
        # ÖH D16 / OH-D15-08 — İTKİ ARTIK SKALER OLMAK ZORUNDA DEĞİL.
        # ``set_thrust_curve`` ile bir eğri kurulduysa yanma süresi eğrinin
        # KENDİ son zamanıdır ve skaler ``thrust`` yalnız künye/raporlama
        # için kalır; dinamiğe F(t) girer (bkz. _calculate_powered_flight).
        # Eğri yoksa iki satır da eskisi gibi okunur (davranış BİT-AYNI).
        egri = getattr(self, '_thrust_curve', None)
        thrust = motor_data['thrust']  # N
        burn_time = motor_data['burn_time']  # s
        if egri is not None:
            burn_time = float(egri[0][-1])
        total_impulse = motor_data['total_impulse']  # N*s
        propellant_mass = motor_data['propellant_mass_total']  # kg
        # ÖH D22 / P4B3-24 — isp ARTIK YA TÜRETİLİR YA DENETLENİR.
        #
        # ÖLÇÜLDÜ (taban b84b10a, ``once.json`` P4B3-24; F = 5000 N,
        # t_b = 10 s, I = 50 000 N·s, m_p = 8 kg, kuru 20 kg, D = 0,15 m):
        #   isp = 220 s   -> apoje 21083,11167515079 m
        #   isp = 1 s     -> apoje 21083,11167515079 m   (BİT-AYNI)
        #   isp = 1e9 s   -> apoje 21083,11167515079 m   (BİT-AYNI)
        #   anahtar yok   -> KeyError: 'isp'
        # Yani anahtar ZORUNLUYDU, sonucu HİÇ etkilemiyordu ve
        # ``/api/trajectory-analysis`` yanıtı ``engine_data.isp`` olarak onu
        # yayımlayıp yörüngenin o Isp ile çözüldüğü izlenimini veriyordu.
        # Aynı girdide bütçeden türeyen gerçek Isp 637,3226 s'dir — yani
        # kullanıcının gönderdiği 220 s sessizce çöpe gidiyordu.
        #
        # Çözücü kütle bütçesini (m_p, t_b) entegre eder; Isp bu bütçenin
        # TÜREVİDİR. İki durum:
        #   * isp verilmedi -> entegre edilen bütçeden TÜRETİLİR (uydurma
        #     yok, künyesi ``isp_basis`` ile taşınır);
        #   * isp verildi   -> bütçeyle çelişiyorsa hangi yörüngenin doğru
        #     olduğu KAZANILMAMIŞTIR; sayı seçilmez, ikisi de adıyla
        #     reddedilir (fail-closed, HTTP ucunda 422).
        isp_turetilen = (total_impulse / (propellant_mass * self.g0)
                         if propellant_mass > 0 else None)
        isp = motor_data.get('isp')
        isp_ham_verildi = isp is not None
        isp_basis = None
        if isp is None:
            if isp_turetilen is None:
                raise TrajectoryInputError(
                    "motor_data['isp'] verilmedi ve türetilemiyor: "
                    "propellant_mass_total > 0 olmalı.",
                    problems=[{'field': 'motor_data.isp',
                               'reason': 'not_derivable',
                               'value': None}])
            isp = isp_turetilen
            isp_basis = ('derived from the impulse budget actually '
                         'integrated (total_impulse / (m_p * g0)), because '
                         'isp was not supplied')
        isp_verilen = None
        isp_sapmasi = None
        if isp is not None and isp_turetilen is not None and isp_turetilen > 0:
            isp_verilen = float(isp)
            isp_sapmasi = abs(isp_verilen - isp_turetilen) / isp_turetilen
            if isp_sapmasi > TRAJECTORY_PROPELLANT_REL_TOL:
                # ÖH D23 / P4B3-24 KALAN AYAK — ÇELİŞKİ ARTIK REDDEDİLİYOR.
                #
                # D22'de bu dal yumuşak davranıyordu: gönderilen Isp sessizce
                # bütçeden türetilenle DEĞİŞTİRİLİYOR, künye (``isp_basis`` +
                # ``isp_supplied_s``) durumu anlatıyor ve yörünge yine de
                # DÖNÜYORDU. Beyan çözüm değildir (doktrin-1): yanma İKİ KEZ
                # tarif edilmiş ve iki tarif birbirini tutmuyorsa hangi
                # yörüngenin doğru olduğu KAZANILMAMIŞTIR — sayı seçilmez.
                #
                # HTTP ucu (``/api/trajectory-analysis``,
                # ``inconsistent_propellant_budget``) bu reddi zaten
                # veriyordu; kapı YALNIZ UÇTAYDI. Kütüphaneyi doğrudan
                # çağıran her yol (motor uçlarının yörünge katmanı,
                # parametrik tarama, betikler, gömülü kullanım) çelişkili
                # yükü sessizce kabul etmeye devam ediyordu. Kapı artık
                # çözücünün kendisindedir; uç ``TrajectoryInputError``ı
                # 422 + ``invalid_fields`` olarak geçirir (bkz. app.py
                # ``except TrajectoryInputError``).
                raise TrajectoryInputError(
                    "motor_data['isp'] ile entegre edilen impuls bütçesi "
                    "çelişiyor: yanma iki kez tarif edilmiş ve iki tarif "
                    "aynı motoru anlatmıyor.",
                    problems=[{
                        'field': 'motor_data.isp',
                        'reason': 'inconsistent_propellant_budget',
                        'value': isp_verilen,
                        'isp_from_impulse_budget_s': isp_turetilen,
                        'relative_disagreement': isp_sapmasi,
                        'accepted_relative_disagreement':
                            TRAJECTORY_PROPELLANT_REL_TOL,
                        'detail': (
                            'The solver integrates the mass/impulse budget '
                            '(total_impulse, propellant_mass_total), so the '
                            'specific impulse it actually flies is '
                            f'{isp_turetilen:.6g} s. The supplied isp '
                            f'({isp_verilen:.6g} s) disagrees by '
                            f'{isp_sapmasi:.1%}. Publishing a trajectory here '
                            'would silently discard one of the two '
                            'descriptions of the burn. Fix one of them; no '
                            'trajectory was computed.'),
                    }])
            else:
                isp = isp_verilen
        isp = float(isp)
        # P4B3-24: künye ÇAĞIRANIN sözlüğüne YERİNDE yazılır. Kopya
        # çıkarmak yasak: ``result['motor_data']`` tarihsel olarak GİRDİ
        # SÖZLÜĞÜNÜN KENDİSİDİR ve çağıran (``hrma/app.py``) çağrıdan sonra
        # ona alan eklemeye devam eder (ölçüldü: kopyalayınca hibrit
        # ``/calculate`` yanıtından ``trajectory.motor_data.fuel_type``
        # DÜŞTÜ). Kimlik korunur, yalnız alan eklenir.
        motor_data['isp'] = isp
        motor_data['isp_role'] = (
            'budget-derived: the solver integrates the mass/impulse budget '
            '(m_p, t_b, I_total); isp is a consistent restatement of that '
            'budget, not an independent input to the dynamics')
        if isp_basis:
            motor_data['isp_basis'] = isp_basis
            # ÖH D23 / P4B3-24 — ``isp_supplied_s`` YALNIZ GERÇEKTEN
            # GÖNDERİLDİYSE yazılır. ÖLÇÜLDÜ (taban ef527ae, once.json
            # P4B3_24.isp_yok): anahtar HİÇ verilmediğinde bile
            # ``isp_supplied_s = 637,3226331112052`` yayımlanıyordu — yani
            # çözücünün kendi türettiği sayı "kullanıcının gönderdiği değer"
            # adıyla geri veriliyordu. Kullanıcı bir şey göndermediyse
            # gönderdiği bir sayı da yoktur.
            if motor_data.get('isp') is not None and isp_verilen is not None \
                    and isp_ham_verildi:
                motor_data['isp_supplied_s'] = isp_verilen
                motor_data['isp_supplied_relative_disagreement'] = isp_sapmasi

        # --- Fırlatma sahası (opsiyonel) ---------------------------------
        # 'launch_site' anahtarı verilmişse (launch_site.resolve_launch_site
        # çıktısı) yerel g + saha rakımı + yüzey T/P datumu uygulanır.
        # Yalnız 'launch_latitude' verilmişse enlemden yerel g türetilir.
        # Hiçbiri yoksa hiçbir şey değişmez (regresyon kilidi).
        site = launch_params.get('launch_site')
        if site is None and launch_params.get('launch_latitude') is not None:
            from hrma.analysis.launch_site import local_gravity
            site = {
                'gravity_local_m_s2': local_gravity(
                    float(launch_params['launch_latitude']),
                    float(launch_params.get('launch_altitude', 0) or 0.0)),
                'latitude_deg': float(launch_params['launch_latitude']),
            }
        self.set_launch_site(site)

        # Extract launch parameters
        # launch_angle = YÜKSELİŞ AÇISI (ufuktan), 90° = dikey yukarı.
        launch_angle = np.radians(launch_params.get('launch_angle', 85))  # degrees to radians
        launch_altitude = launch_params.get('launch_altitude', 0)  # m
        if site and site.get('elevation_m') is not None and \
                launch_params.get('launch_altitude') is None:
            launch_altitude = float(site['elevation_m'])
        wind_speed = launch_params.get('wind_speed', 0)  # m/s
        wind_direction = np.radians(launch_params.get('wind_direction', 0))  # degrees to radians

        # Rüzgar vektörü (atalet çerçevesinde, hava kütlesi hızı)
        wind_vec = self._wind_vector(wind_speed, wind_direction)
        # ÖH D17 / P4B3-14: modelin TAŞIMADIĞI çapraz bileşen ölçülür ve
        # sonuçta beyan edilir (aşağıda ``result['wind_model']``).
        wind_model = self._wind_components(wind_speed, wind_direction)

        # Kurtarma sistemi girdileri (F080). launch_params'ta verilmişse
        # setter üzerinden uygulanır; verilmemişse önceki set_recovery_
        # parameters çağrısı ya da varsayım geçerli kalır.
        #
        # DURUM SIZINTISI KORUMASI: bir anahtar AÇIKÇA verilmişse o alan
        # TAMAMEN bu isteğin girdisinden belirlenir — önce varsayılana
        # döndürülür, sonra verilen değer uygulanır. Gerekçe: uygulama
        # katmanı modül düzeyinde TEK bir TrajectoryAnalyzer örneği
        # paylaşıyor; reset olmadan bir önceki isteğin paraşütü sonraki
        # isteğe sızar ve kullanıcı ``parachute_area: null`` gönderse bile
        # kendi girmediği bir alandan türetilmiş iniş hızı görür. Anahtar
        # HİÇ yoksa (eski çağıranlar) davranış birebir eskisi gibidir.
        self.warnings = []
        _recovery_defaults = (
            ('parachute_area', 'parachute_area', None),
            ('parachute_cd', 'parachute_cd', DEFAULT_PARACHUTE_CD),
            ('parachute_deploy_delay', 'parachute_deploy_delay',
             DEFAULT_PARACHUTE_DEPLOY_DELAY_S),
        )
        # v2.6.26 — SIFIRLAMA KOŞULSUZ.
        #
        # Ölçülmüş hata: bu blok eskiden yalnız launch_params'ta paraşüt
        # anahtarı VARSA çalışıyordu, üstelik yalnız VERİLEN anahtarları
        # sıfırlıyordu. TrajectoryAnalyzer app.py:667'de modül düzeyinde TEKİL
        # nesne olduğu için, bir istekte verilen paraşüt bir SONRAKİ isteğe
        # sızıyordu. Ölçüm (aynı süreçte ardışık istekler):
        #     1. taban                  -> iniş 22,62 m/s, assumed=True
        #     2. parachute_area=9.0     -> iniş 10,65 m/s, assumed=False
        #     3. taban (1'in AYNISI)    -> iniş 10,65 m/s, assumed=False
        # Yani birebir aynı istek %53 farklı sonuç veriyor ve `_assumed`
        # bayrağı uydurulmuş değeri "kullanıcı verdi" diye işaretliyor —
        # yanlış sayıdan da kötüsü, DÜRÜSTLÜK BAYRAĞININ kendisi bozuluyor.
        # Masaüstü paketinde süreç ömrü boyunca sürer; sunucuda kullanıcılar
        # arasında sızar.
        #
        # Muhafız çağıranın davranışına bağlı kalmamalı: her koşuda önce
        # varsayılana dönülür, sonra istekte NE VARSA o uygulanır.
        # (set_recovery_parameters None'ı zaten doğru işliyor: :146-165.)
        # KOŞULLU sıfırlama — programatik sözleşme korunur.
        #
        # `set_recovery_parameters` bir API'dir: kullanıcı onu çağırıp değer
        # bıraktıysa, sonraki `calculate_trajectory` o değeri KORUMALIDIR
        # (test_trajectory_physics_v262::test_setter_value_survives_when_key_absent
        # bunu sözleşme olarak kilitliyor). Bu yüzden burada koşulsuz
        # sıfırlamak yanlış: paylaşılan nesnedeki sızıntı bu metodun değil,
        # NESNENİN PAYLAŞILMASININ sorunuydu ve orada çözüldü — app.py artık
        # her istekte taze analizör kuruyor.
        #
        # Kalan iş: launch_params kurtarma anahtarı taşıyorsa ÜÇÜNÜ BİRDEN
        # sıfırla. Eski kod yalnız VERİLEN anahtarı sıfırlıyordu; bir istekte
        # alan, sonrakinde Cd verilince alan hâlâ eskisinden kalıyordu.
        if any(k in launch_params for k, _a, _d in _recovery_defaults):
            for _key, attr, default in _recovery_defaults:
                setattr(self, attr, default)
            self._parachute_cd_supplied = False
            self._parachute_delay_supplied = False
            self.set_recovery_parameters(
                parachute_area=launch_params.get('parachute_area'),
                parachute_cd=launch_params.get('parachute_cd'),
                deploy_delay=launch_params.get('parachute_deploy_delay'))

        # Calculate vehicle parameters
        total_mass_loaded = self.vehicle_mass_dry + propellant_mass
        cross_sectional_area = np.pi * (self.vehicle_diameter / 2) ** 2

        # --- YER DÜZLEMİ (Faz 5 / B3) -----------------------------------
        # Zemin, FIRLATMA SAHASI kotudur — deniz seviyesi değil. Araç bu
        # kotun altına inemez; temas bir SONLANDIRMA olayıdır. Ölçüldü
        # (HEAD 9d3728e, 30° atış): güçlü faz z = −140,67 m'de bitiyordu,
        # serbest faz −54 722 m'ye iniyordu, iniş fazı −65 802 m'de duruyordu;
        # ``_atm_full`` negatif irtifayı 0'a kırptığı için araç 65 km yer
        # altında deniz seviyesi yoğunluğunda "uçuyordu".
        ground_level = float(launch_altitude)
        # Metrik katmanı (irtifa verimi) ve grafik katmanı aynı datumu
        # okumak zorunda — TEK KAYNAK burasıdır (ÖH D15, P4B3-05/-03).
        self.ground_level_m = ground_level

        # --- FIRLATMA RAYI (Faz 5 / B2) ---------------------------------
        rail_length = self._resolve_rail_length(launch_params)
        if rail_length is None:
            self.warnings.append(_mk_warning(
                'warn.trajectory.launch_rail_not_modelled', 'warning'))

        # --- İTKİNİN İRTİFA TELAFİSİ (ÖH D18 / P4B3-22) ------------------
        # A_e motor sözlüğünde geliyorsa telafi AÇILIR; gelmiyorsa
        # açıkça beyan edilir. Sessiz sabit itki bir daha olmaz.
        if self.nozzle_exit_area is None:
            _ae_md = _finite_or_none(motor_data.get('nozzle_exit_area'))
            if _ae_md is not None and _ae_md > 0.0:
                self.set_nozzle_exit(
                    _ae_md,
                    motor_data.get('thrust_reference_pressure'))
        if self.nozzle_exit_area is None:
            # Kardeş 6-DOF'un ``warn.sixdof.thrust_not_altitude_compensated``
            # uyarısının düzlemsel karşılığı — aynı olay, aynı ad kalıbı.
            self.warnings.append(_mk_warning(
                'warn.trajectory.thrust_not_altitude_compensated', 'warning'))

        # Phase 1: Powered flight (motor burning)
        powered_flight = self._calculate_powered_flight(
            thrust, burn_time, total_mass_loaded, propellant_mass,
            launch_angle, launch_altitude, cross_sectional_area, wind_vec,
            rail_length=rail_length, ground_level=ground_level,
            thrust_curve=egri
        )

        # Phase 2: Coasting flight (after burnout)
        # Güçlü faz yerle temasla bittiyse sonraki fazlar HİÇ koşmaz —
        # araç zaten yerdedir; "apoje" ve "iniş" diye ayrı bir sayı üretmek
        # olmayan bir uçuşu raporlamak olurdu.
        if powered_flight['end_reason'] == 'ground':
            coasting_flight = self._skipped_coasting_phase(
                powered_flight['final_state'], 'ground_impact_in_powered_flight')
            descent_flight = self._skipped_descent_phase(
                powered_flight['final_state'], 'ground_impact_in_powered_flight')
        else:
            coasting_flight = self._calculate_coasting_flight(
                powered_flight['final_state'], cross_sectional_area, wind_vec,
                ground_level=ground_level
            )
            if coasting_flight['end_reason'] == 'ground':
                descent_flight = self._skipped_descent_phase(
                    coasting_flight['apogee_state'],
                    'ground_impact_in_coasting_flight')
            elif self.parachute_area is None:
                # Phase 3 ÇÖZÜLMEZ — ÖH D22 / OH-D18-05 (fail-closed).
                # Kurtarma sistemi girdisi yok: inişi süren tek büyüklük
                # eksik. Eskiden burada DEFAULT_PARACHUTE_AREA_M2
                # uyduruluyor, iniş hükmü YİNE DE yayımlanıyor, uyarı
                # basılıyordu. Ölçüldü: kullanıcı girdisi sabitken yalnız
                # o modül sabiti oynatılınca 15 yaprak kıpırdıyordu.
                descent_flight = self._unmodelled_descent_phase(
                    coasting_flight['apogee_state'], 'recovery_not_supplied')
            else:
                # Phase 3: Descent with recovery
                descent_flight = self._calculate_descent_flight(
                    coasting_flight['apogee_state'], cross_sectional_area,
                    wind_vec, ground_level=ground_level
                )

        # Combine all phases
        trajectory_data = self._combine_flight_phases(
            powered_flight, coasting_flight, descent_flight
        )

        # --- UÇUŞ HÜKMÜ (Faz 5 / B1 + B6) -------------------------------
        flight_status = self._resolve_flight_status(
            powered_flight, coasting_flight, descent_flight)

        # Calculate performance metrics
        performance_metrics = self._calculate_performance_metrics(
            trajectory_data, motor_data, launch_params, flight_status
        )

        result = {
            'flight_status': flight_status,
            'launch_rail': {
                'modelled': rail_length is not None,
                'length_m': rail_length,
                'exit_velocity_m_s': powered_flight.get('rail_exit_velocity'),
                'exit_time_s': powered_flight.get('rail_exit_time'),
                'basis': (
                    'launch rail modelled: attitude locked along the rail '
                    'until the vehicle has travelled rail length'
                    if rail_length is not None else
                    'NOT_MODELLED: launch_rail_length was not supplied, so no '
                    'rail constraint and no attitude dynamics are modelled; '
                    'thrust is held along the launch attitude for the whole '
                    'burn and the pitch-over is NOT computed'),
            },
            # ÖH D18 / P4B3-22 — İTKİNİN İRTİFA TELAFİSİ ADIYLA BEYAN EDİLİR.
            # ÖLÇÜLDÜ (``once.json`` K7, taban 9071a64): sonuç sözlüğünde
            # itkinin irtifayla sabit tutulduğunu söyleyen TEK bir alan ya da
            # uyarı yoktu; kardeş 6-DOF ise aynı varsayımı her koşumda
            # ``warn.sixdof.thrust_not_altitude_compensated`` ile söylüyordu.
            'thrust_altitude_compensation': {
                'modelled': self.nozzle_exit_area is not None,
                'nozzle_exit_area_m2': self.nozzle_exit_area,
                'reference_pressure_pa': (
                    self.thrust_reference_pressure
                    if self.nozzle_exit_area is None else
                    float(self._atm_full(launch_altitude)[1])
                    if self.thrust_reference_pressure is None
                    else self.thrust_reference_pressure),
                'basis': (
                    'F(h) = F_ref + (P_ref - P_amb(h)) * A_e (Sutton & '
                    'Biblarz, Rocket Propulsion Elements, Ch. 3)'
                    if self.nozzle_exit_area is not None else
                    'NOT_MODELLED: nozzle_exit_area was not supplied, so the '
                    'thrust is held at its reference value for the whole '
                    'burn. A_e is a design quantity and is NOT derived from '
                    'thrust and burn time; supply motor_data'
                    '["nozzle_exit_area"] to model the compensation.'),
            },
            'trajectory': trajectory_data,
            'performance': performance_metrics,
            'motor_data': motor_data,
            'vehicle_parameters': {
                'mass_dry': self.vehicle_mass_dry,
                'mass_loaded': total_mass_loaded,
                'diameter': self.vehicle_diameter,
                'drag_coefficient': self.drag_coefficient,
                'cross_sectional_area': cross_sectional_area
            }
        }
        # --- KURTARMA SİSTEMİ ÖZETİ (T68, 2026-08-03) --------------------
        # Ölçülen kusur: iniş fazı bir PARAŞÜTLE çözülüyor ama bunu söyleyen
        # hiçbir üst düzey alan yoktu; bilgi yalnız
        # ``trajectory.phases.descent`` içine gömülüydü. Sonuç: 4,11 km'lik
        # apojeden sonra 750 s süren bir iniş, kullanıcının girdiği gövde
        # sürüklemesiyle (Cd 0,5 / A 0,008 m²) açıklanamıyordu — balistik
        # iniş ~30 s sürerdi. Panel, grafik etiketi ve dışa aktarım bu bloğu
        # okuyabilsin diye özet çözümün KENDİSİNDEN türetilir; hiçbir sayı
        # varsayılmaz, olmayan büyüklük None kalır.
        result['recovery'] = self._recovery_summary(
            powered_flight, coasting_flight, descent_flight, trajectory_data)

        # --- RÜZGÂR MODELİNİN BOYUTU (ÖH D17 / P4B3-14) ------------------
        # Düzlemsel çözücü rüzgârın yalnız düzlem-içi bileşenini entegre
        # eder. Bu bir modelleme SINIRIDIR ve sessiz kalamaz: kullanıcı
        # 90°'lik rüzgâr girip menzilin rüzgârsız koşumla bit-aynı çıkmasını
        # "rüzgârın etkisi yok" diye okur. Blok her koşuda yayımlanır
        # (rüzgârsız koşumda da: çapraz bileşen 0,0'dır ve bunu söylemek
        # bedava), sayılar ÖLÇÜLENLERDİR.
        result['wind_model'] = dict(wind_model)
        if wind_model['cross_plane_significant']:
            # Menzil, PEDDEN uzaklık değil DÜZLEM-İÇİ menzildir; çapraz
            # bileşen entegre edilmediği için gerçek iniş noktası bu
            # sayıdan daha uzaktadır. Sayı silinmez (ölçüm ölçümdür),
            # ALT SINIR olarak damgalanır — kardeş 6-DOF çözücüsünün
            # ``peak_values_are_lower_bounds`` sözleşmesiyle aynı desen.
            _tm = result['performance']['trajectory_metrics']
            _tm['range_distance_is_lower_bound'] = True
            _tm['range_distance_basis'] = (
                'IN-PLANE range only. A cross-plane wind component of '
                '%.4g m/s was supplied but this planar solver cannot carry '
                'it, so the distance from the pad is larger than the number '
                'above. See wind_model for the full decomposition.'
                % wind_model['cross_plane_component_m_s'])
            # Beyan bir UYARI KODU değil VERİ ALANIDIR: yeni bir i18n
            # anahtarı bu kulvarın sahası dışındadır ve çevrilmemiş bir kod
            # ekranda ham anahtar olarak görünürdü (aynı gerekçe: D15 /
            # P4B3-02 ``apogee_withheld_because``).
            result['wind_model']['cross_plane_dropped'] = True

        # --- İTKİ GİRDİSİNİN KÜNYESİ (ÖH D16 / OH-D15-08) ----------------
        # Eğri VERİLMEDİĞİNDE anahtar EKLENMEZ: skaler yolun gövdesi
        # bit-aynı kalır (regresyon kilidi). Eğri verildiğinde yörüngenin
        # NEYDEN entegre edildiği adıyla yayımlanır — kullanıcı ekranda
        # gördüğü apojenin ortalama itkinin dikdörtgeninden mi yoksa gerçek
        # eğriden mi çıktığını okuyabilmelidir (P12bB2-09'un tam derdi).
        if egri is not None:
            _t_e, _F_e, _imp_e = egri
            _ort_e = _imp_e / float(_t_e[-1] - _t_e[0])
            result['thrust_input'] = {
                'source': 'thrust_curve',
                'points': int(_t_e.size),
                'burn_time_s': float(_t_e[-1]),
                'peak_thrust_N': float(np.max(_F_e)),
                'average_thrust_N': _ort_e,
                'peak_to_average_ratio': (float(np.max(_F_e)) / _ort_e
                                          if _ort_e > 0 else None),
                'total_impulse_Ns': _imp_e,
                'basis': (
                    'the trajectory was integrated from the supplied '
                    'thrust-time curve: F(t) by linear interpolation and '
                    'mdot(t) = m_p * F(t) / I_total, so propellant is spent '
                    'in proportion to thrust. A single average thrust would '
                    'flatten the peak and change the flight.'),
            }

        # Fırlatma sahası uygulandıysa çözümün hangi konumda yapıldığı
        # sonuçla birlikte döner (rapor/UI bunu gösterir); saha yoksa anahtar
        # eklenmez ve çıktı sözleşmesi eskisiyle birebir aynı kalır.
        if self.launch_site:
            result['launch_site'] = self.launch_site
        # v2.6.2 uyarı sözleşmesi: {code, params, severity} listesi.
        # Uyarı yoksa anahtar EKLENMEZ (çıktı sözleşmesi eskisiyle aynı kalır).
        if self.warnings:
            result['warnings'] = list(self.warnings)
        return result

    def _recovery_summary(self, powered: Dict, coasting: Dict, descent: Dict,
                          trajectory: Dict) -> Dict:
        """Kurtarma sisteminin ÜST DÜZEY özeti — T68 (2026-08-03).

        İniş fazının hangi modelle çözüldüğü buradan tek bakışta okunur:
        paraşüt açıldı mı, ne zaman, hangi alan/Cd ile, bunların kaçı
        VARSAYIM ve inişin kendisi ne kadar sürdü. Bütün sayılar çözümden
        ölçülür; iniş tamamlanmadıysa (zaman sınırı/çözücü hatası) ilgili
        alanlar ``None`` kalır — zaman ufkunun son noktası "iniş" diye
        yayımlanmaz.
        """
        deployed = bool(descent.get('recovery_deployed', False))
        if not deployed:
            # İki AYRI "kurtarma yok" hâli var ve gerekçeleri aynı cümleyle
            # anlatılamaz (ÖH D22 / OH-D18-05):
            #   * ``skipped``      -> araç apojeye varmadan yere çarptı;
            #                         iniş sayıları BİLİNİYOR (balistik).
            #   * ``not_modelled`` -> paraşüt alanı verilmedi; iniş fazı hiç
            #                         çözülmedi, sayılar BİLİNMİYOR.
            # Eski tek cümle ("the vehicle reached the ground earlier")
            # ikincisi için düpedüz YANLIŞTI.
            withheld = descent.get('landing_withheld_because')
            ozet = {
                'deployed': False,
                'reason': (descent.get('reason')
                           or descent.get('skipped_reason')
                           or descent.get('end_reason')),
                'descent_model': 'NOT_MODELLED',
                'landing_withheld_because': withheld,
                'basis': (withheld if withheld else
                          'the descent phase did not run (the vehicle reached '
                          'the ground earlier), so no recovery system is part '
                          'of this solution'),
            }
            # SÖZLEŞME ŞEKLİ İKİ DALDA DA AYNI (ÖH D22 / OH-D18-05).
            # Bu dal eskiden anahtarları hiç KOYMUYORDU; nadir bir yoldu
            # (araç apojeden önce yere çarpar) ama artık paraşütsüz her
            # koşumda geçiliyor. ``rec['landing_velocity_m_s']`` okuyan bir
            # tüketici KeyError alırdı — sayının yokluğu, ALANIN yokluğu
            # gibi görünürdü. Doktrin: alan adıyla durur, değeri None'dır
            # ve gerekçesi yanındadır; sayı uydurulmaz.
            for anahtar in ('deploy_time_s', 'descent_start_time_s',
                            'descent_duration_s', 'mean_descent_rate_m_s',
                            'descent_height_m', 'landing_velocity_m_s',
                            'parachute_area_m2', 'parachute_cd',
                            'parachute_deploy_delay_s'):
                ozet[anahtar] = None
            ozet['assumed'] = {'area': False, 'cd': False,
                               'deploy_delay': False}
            # Saha kotu inişten bağımsız olarak BİLİNİR; hükümle birlikte
            # geri çekilmesi için bir sebep yok.
            ozet['ground_level_m'] = float(
                getattr(self, 'ground_level_m', 0.0) or 0.0)
            return ozet

        # İniş fazının uçuş zaman ekseni üzerindeki başlangıcı
        t_descent_start = (float(powered['time'][-1])
                           + float(coasting['time'][-1]))
        delay = descent.get('parachute_deploy_delay_s')
        t_deploy = (t_descent_start + float(delay)) if delay is not None else None

        landing_time = descent.get('landing_time')
        descent_duration = (float(landing_time)
                            if landing_time is not None else None)
        apogee_altitude = None
        try:
            apogee_altitude = float(coasting['position_z'][-1])
        except (KeyError, IndexError, TypeError, ValueError):
            apogee_altitude = None
        # --- ORTALAMA İNİŞ HIZININ DATUMU (ÖH D17 / P4B3-15) ------------
        # Pay ve payda AYNI datumdan ölçülmek zorundadır. Eski kod payı
        # DENİZ SEVİYESİNDEN (``coasting.position_z`` mutlak irtifadır),
        # paydayı ise sahadan yere inen süreden alıyordu: araç yalnız
        # apoje ile SAHA KOTU arasındaki yüksekliği düşerken, sayı sahanın
        # altındaki hiç uçulmamış kotu da düşülmüş sayıyordu. ÖLÇÜLDÜ
        # (docs/scofield/raw/OH/D17/termo-ucus/a1/once.json, K7_P4B3_15_inis):
        # saha 1500 m -> yayımlanan 16,836785 m/s, saha datumuyla gerçek
        # 13,117193 m/s (+%28,36 şişme); saha 0 m'de iki sayı BİREBİR aynıdır
        # (12,012426 m/s — regresyon kilidi). Datum tek kaynaktan gelir:
        # ``self.ground_level_m`` (P4B3-05'in kurduğu aynı alan).
        _datum = float(getattr(self, 'ground_level_m', 0.0) or 0.0)
        descent_height = (None if apogee_altitude is None
                          else float(apogee_altitude) - _datum)
        mean_rate = None
        if (descent_duration and descent_duration > 0.0
                and descent_height is not None and descent_height > 0.0):
            mean_rate = descent_height / descent_duration

        return {
            'deployed': True,
            'descent_model': 'parachute',
            'deploy_time_s': t_deploy,
            'descent_start_time_s': t_descent_start,
            'descent_duration_s': descent_duration,
            'mean_descent_rate_m_s': mean_rate,
            'descent_height_m': descent_height,
            'ground_level_m': _datum,
            'mean_descent_rate_basis': (
                'descent height divided by descent duration, BOTH measured '
                'from the launch site datum (%.4g m ASL) — not from mean sea '
                'level: the vehicle only falls from apogee to the site, so a '
                'site at altitude must not inflate the rate.' % _datum),
            'landing_velocity_m_s': descent.get('landing_velocity'),
            'parachute_area_m2': descent.get('parachute_area_m2'),
            'parachute_cd': descent.get('parachute_cd'),
            'parachute_deploy_delay_s': delay,
            'assumed': {
                'area': bool(descent.get('parachute_area_assumed')),
                'cd': bool(descent.get('parachute_cd_assumed')),
                'deploy_delay': bool(descent.get('parachute_deploy_delay_assumed')),
            },
            'basis': ('the descent is solved with a parachute, NOT with the '
                      'body drag entered for the ascent: after the deploy '
                      'delay the drag area switches to the parachute area at '
                      'the parachute Cd. Any component flagged in "assumed" '
                      'is a model default, not a qualified recovery design, '
                      'and the descent time scales directly with it'),
        }

    def _aero_drag_components(self, vx: float, vz: float, rho: float,
                             altitude: float, area: float, cd_override: Optional[float],
                             wind_vec: Tuple[float, float]) -> Tuple[float, float]:
        """Bağıl hızdan sürükleme kuvveti bileşenlerini hesaplar.

        v_rel = v_arac - v_ruzgar ; Drag = -0.5*rho*Cd*A*|v_rel|*v_rel
        (McCoy "Modern Exterior Ballistics" 1999; Sutton & Biblarz 9. baskı.)

        cd_override None ise Mach-bağımlı Cd kullanılır; aksi halde verilen
        sabit Cd kullanılır (ör. paraşüt fazı).
        """
        vx_wind, vz_wind = wind_vec
        # Havaya göre bağıl hız
        vrx = vx - vx_wind
        vrz = vz - vz_wind
        v_rel = np.sqrt(vrx * vrx + vrz * vrz)

        if v_rel <= 1e-9:
            return 0.0, 0.0

        if cd_override is None:
            # Yerel ses hızı: a = sqrt(gamma * R * T)
            _, _, _, a_sound = self._atm_full(altitude)
            mach = v_rel / a_sound if a_sound > 0 else 0.0
            cd = self._drag_coefficient_mach(mach)
        else:
            cd = cd_override

        drag_magnitude = 0.5 * rho * v_rel * v_rel * cd * area
        # Bağıl hız yönüne ters
        Fx_drag = -drag_magnitude * (vrx / v_rel)
        Fz_drag = -drag_magnitude * (vrz / v_rel)
        return Fx_drag, Fz_drag

    def _calculate_powered_flight(self, thrust: float, burn_time: float,
                                  total_mass: float, propellant_mass: float,
                                  launch_angle: float, launch_altitude: float,
                                  cross_sectional_area: float,
                                  wind_vec: Tuple[float, float],
                                  rail_length: Optional[float] = None,
                                  ground_level: float = 0.0,
                                  thrust_curve=None) -> Dict:
        """Calculate powered flight phase (motor burning).

        FIRLATMA RAYI VE TUTUM (Faz 5 / B2 düzeltmesi)
        ----------------------------------------------
        Eski kod itki yönünü ``v > 1.0 m/s`` olur olmaz hız vektörüne
        kilitliyordu (yerçekimi dönüşü). Bu eşik FİZİKSEL DEĞİL, keyfiydi:
        ``dγ/dt = −g·cos γ / v`` bağıntısı v→0 iken ıraksar, bu yüzden model
        kalkıştan hemen sonra roketi yatırıyordu. ÖLÇÜLDÜ (HEAD 9d3728e,
        F=600 N, T/W=2,19, 85° atış): yanma daha bitmeden γ = −0,52°, güçlü
        faz z = −48 m'de bitiyor, apoje 13,86 m çıkıyordu; aynı atmosfer ve
        sürükleme fonksiyonuyla bağımsız referans 279,96-286,86 m veriyor
        (20 kat fark). Gerçek roket bu bölgede fırlatma rayının normal
        kuvvetiyle kısıtlıdır.

        İki AÇIKÇA BEYAN EDİLMİŞ rejim vardır — ikisinde de sihirli sayı yok:

        1. ``rail_length`` VERİLDİ: ray boyunca hareket ray eksenine
           kısıtlanır (net kuvvetin ray doğrultusuna izdüşümü alınır, dik
           bileşenleri ray normal kuvveti karşılar), tutum ray açısında
           kilitlidir. Araç ray boyunu katedince serbest bırakılır ve
           itki hız vektörüne döner (yerçekimi dönüşü) — bu noktada hız
           artık sıfırdan uzaktır, yani bağıntı iyi tanımlıdır.
           Kardeş 6-DOF modülü aynı sözleşmeyi kullanır
           (``six_dof_trajectory._derivatives``: ``on_rail`` izdüşümü).

        2. ``rail_length`` VERİLMEDİ: tutum dinamiği MODELLENMEZ. İtki tüm
           yanma boyunca fırlatma doğrultusunda tutulur ve sonuç
           ``launch_rail.modelled = False`` ile damgalanır. Uydurma bir ray
           boyu ya da uydurma bir hız eşiği KONMAZ.
        """

        # Ray/fırlatma doğrultusu birim vektörü (yükseliş açısı konvansiyonu).
        rail_ux = float(np.cos(launch_angle))
        rail_uz = float(np.sin(launch_angle))
        rail_modelled = rail_length is not None and rail_length > 0.0

        # İrtifa telafisi katsayıları — türev fonksiyonunun DIŞINDA bir kez
        # çözülür (P4B3-22). A_e yoksa None kalır ve blok hiç koşmaz.
        _ae_telafi = self.nozzle_exit_area
        _p_ref_telafi = None
        if _ae_telafi is not None:
            _p_ref_telafi = self.thrust_reference_pressure
            if _p_ref_telafi is None:
                # Referans basıncı verilmediyse itkinin FIRLATMA
                # İRTİFASINDA ölçüldüğü varsayılır — kardeş 6-DOF ile aynı
                # sözleşme (``_pressure_at(self.launch_altitude)``).
                _p_ref_telafi = float(self._atm_full(launch_altitude)[1])

        def powered_flight_dynamics(t, y):
            """Dynamics during powered flight"""
            x, z, vx, vz, mass = y

            # Current altitude
            altitude = z

            # Atmospheric properties (rho, g)
            rho, g = self._get_atmospheric_properties(altitude)

            # Mass flow rate
            #
            # ÖH D16 / OH-D15-08: eğri VERİLDİYSE itki F(t) ile okunur ve
            # yakıt itkiyle ORANTILI harcanır (∫ṁ dt = m_p tam olarak).
            # Eğri yoksa iki satır da eskisi gibi çalışır — sabit debi,
            # dikdörtgen itki (BİT-AYNI regresyon kilidi).
            if t <= burn_time:
                if thrust_curve is None:
                    mdot = propellant_mass / burn_time
                    thrust_current = thrust
                else:
                    _t_arr, _F_arr, _impulse = thrust_curve
                    thrust_current = float(np.interp(t, _t_arr, _F_arr))
                    mdot = propellant_mass * thrust_current / _impulse
            else:
                mdot = 0
                thrust_current = 0

            # İRTİFA TELAFİSİ (ÖH D18 / P4B3-22). A_e verilmediyse blok
            # HİÇ çalışmaz ve davranış bit-aynı kalır — uydurma alan yok.
            # ṁ ortam basıncından BAĞIMSIZDIR (kardeş 6-DOF ile aynı
            # doktrin: yalnız itki değişir), bu yüzden yukarıdaki mdot'a
            # dokunulmaz.
            if _ae_telafi is not None and thrust_current > 0.0:
                _p_amb = self._atm_full(altitude)[1]
                thrust_current = thrust_current + (_p_ref_telafi
                                                   - _p_amb) * _ae_telafi
                if thrust_current < 0.0:
                    thrust_current = 0.0

            # İtki yönü — bkz. metot docstring'i (B2).
            # KONVANSIYON: vertical = sin(theta_elev), horizontal = cos(theta_elev).
            on_rail = False
            if rail_modelled:
                # Ray üzerinde katedilen mesafe (fırlatma noktasından).
                s_rail = np.hypot(x - 0.0, z - launch_altitude)
                on_rail = bool(s_rail < rail_length and t <= burn_time)

            if on_rail or not rail_modelled:
                # Ray üstünde ya da tutum modellenmiyorken: fırlatma doğrultusu
                thrust_direction_x = rail_ux
                thrust_direction_z = rail_uz
            else:
                # Raydan çıktı: yerçekimi dönüşü (itki hız vektörü boyunca).
                # Ray çıkış hızı sıfırdan uzak olduğu için bağıntı iyi tanımlı.
                v_mag = np.sqrt(vx ** 2 + vz ** 2)
                if v_mag > 0.0:
                    thrust_direction_x = vx / v_mag
                    thrust_direction_z = vz / v_mag
                else:
                    thrust_direction_x = rail_ux
                    thrust_direction_z = rail_uz

            # Thrust force
            Fx_thrust = thrust_current * thrust_direction_x
            Fz_thrust = thrust_current * thrust_direction_z

            # Drag force (Mach-bağımlı Cd, bağıl hızdan)
            Fx_drag, Fz_drag = self._aero_drag_components(
                vx, vz, rho, altitude, cross_sectional_area,
                cd_override=None, wind_vec=wind_vec
            )

            # Gravity force
            Fz_gravity = -mass * g

            # Total forces
            Fx_total = Fx_thrust + Fx_drag
            Fz_total = Fz_thrust + Fz_drag + Fz_gravity

            if on_rail:
                # Ray kısıtı: hareket ray eksenine kilitli. Net kuvvetin ray
                # doğrultusundaki bileşeni kalır; dik bileşenleri ray normal
                # kuvveti karşılar (ideal, sürtünmesiz ray).
                f_parallel = Fx_total * rail_ux + Fz_total * rail_uz
                if f_parallel < 0.0 and np.hypot(vx, vz) <= 1e-9:
                    # Araç rampada DURUYOR ve net kuvvet aşağı: ray tutucusu
                    # ağırlığı karşılar (T/W < 1 → kalkış YOK). Hareket
                    # başladıktan sonra negatif kuvvet yavaşlatma olarak
                    # aynen etkir — serbest yolculuk verilmez.
                    f_parallel = 0.0
                Fx_total = f_parallel * rail_ux
                Fz_total = f_parallel * rail_uz

            # Accelerations
            ax = Fx_total / mass
            az = Fz_total / mass

            # Mass change
            dmdt = -mdot

            return [vx, vz, ax, az, dmdt]

        # Initial conditions
        y0 = [0, launch_altitude, 0, 0, total_mass]  # x, z, vx, vz, mass

        # Time span (extend beyond burn time for transition)
        t_end = burn_time + POWERED_PHASE_MARGIN_S
        t_span = (0, t_end)
        t_eval = np.linspace(0, t_end, max(int(t_end * 50), 10))

        # B3 — YER TEMASI SONLANDIRMA OLAYI.
        # Araç t=0'da tam olarak yer düzlemindedir; olay ilk anlarda
        # "kurulmamış" tutulur (GROUND_EVENT_ARM_S), aksi halde kalkışta
        # hemen tetiklenirdi.
        def ground_event(t, y):
            gap = y[1] - ground_level
            return gap + 1.0 if t < GROUND_EVENT_ARM_S else gap
        ground_event.terminal = True
        ground_event.direction = -1

        # Solve ODE -- RK45 (solve_ivp) ile tutarlı çözücü
        sol = solve_ivp(powered_flight_dynamics, t_span, y0, t_eval=t_eval,
                        method='RK45', rtol=1e-8, atol=1e-9,
                        events=ground_event)

        # Çözücü hükmü (B1): hangi olay bitirdi?
        if not sol.success:
            end_reason = 'solver_failed'
        elif sol.t_events[0].size:
            end_reason = 'ground'
        else:
            end_reason = 'burn_window_complete'

        # Ray çıkışı: ray doğrultusunda katedilen mesafe ray boyunu geçtiği an.
        rail_exit_time = None
        rail_exit_velocity = None
        if rail_modelled and sol.t.size:
            s_hist = np.hypot(sol.y[0] - 0.0, sol.y[1] - launch_altitude)
            beyond = np.nonzero(s_hist >= rail_length)[0]
            if beyond.size:
                k = int(beyond[0])
                rail_exit_time = float(sol.t[k])
                rail_exit_velocity = float(np.hypot(sol.y[2][k], sol.y[3][k]))

        # YANMA-SONU (burnout) ÖRNEKLEME — v2.6.2 fizik denetimi (bulgu F028).
        #
        # Güçlü faz bilerek burn_time + 2 s'ye kadar entegre ediliyor (geçiş
        # payı). Fakat yanma-sonu büyüklükleri bu aralığın SONUNDAN veya
        # TEPESİNDEN okunuyordu: ``max_altitude_powered = np.max(sol.y[1])``
        # 2 saniyelik serbest tırmanışı da içerdiği için yanma-sonu irtifası
        # değil, o penceredeki en yüksek nokta oluyordu.
        #
        # ÖLÇÜLDÜ (F=3000 N, t_b=4 s, m_kuru=20 kg, m_yakıt=8 kg, 85°):
        #   gerçek yanma-sonu irtifa 806.7 m  -> raporlanan 1487.0 m (+%84.3)
        #   gerçek yanma-sonu hız    399.7 m/s -> raporlanan 300.8 m/s (−%24.7)
        # İrtifa şişerken hızın düşmesi, iki büyüklüğün FARKLI anlardan
        # okunmasındandı (biri tepe, diğeri pencere sonu).
        #
        # Doğrusu: yanma-sonu = motor kesme anı; hepsi t = burn_time'da ve
        # AYNI anda örneklenir (Sutton & Biblarz, Böl. 4 burnout tanımı).
        t_bo = float(np.clip(burn_time, sol.t[0], sol.t[-1]))
        bo = {name: float(np.interp(t_bo, sol.t, arr))
              for name, arr in (('x', sol.y[0]), ('z', sol.y[1]),
                                ('vx', sol.y[2]), ('vz', sol.y[3]),
                                ('mass', sol.y[4]))}

        return {
            'time': sol.t,
            'position_x': sol.y[0],
            'position_z': sol.y[1],
            'velocity_x': sol.y[2],
            'velocity_z': sol.y[3],
            'mass': sol.y[4],
            'final_state': [sol.y[0][-1], sol.y[1][-1], sol.y[2][-1], sol.y[3][-1], sol.y[4][-1]],
            # Pencere tepesi — yanma-sonu DEĞİL; adı bunu açıkça söylüyor.
            'max_altitude_powered': float(np.max(sol.y[1])),
            'burnout_time': burn_time,
            # t = burn_time'da eşzamanlı örneklenmiş gerçek yanma-sonu durumu
            'burnout_state': [bo['x'], bo['z'], bo['vx'], bo['vz'], bo['mass']],
            'burnout_altitude': bo['z'],
            'burnout_velocity': float(np.hypot(bo['vx'], bo['vz'])),
            # B1/B3: fazın hangi OLAYLA bittiği sonucun parçasıdır.
            'end_reason': end_reason,
            # Yanma-sonu gerçekten görüldü mü (yoksa faz daha önce yerle mi
            # bitti)? burnout_* alanları bu durumda çarpma anını taşır.
            'burnout_reached': bool(sol.t.size and float(sol.t[-1]) >= burn_time),
            'lifted_off': bool(sol.y[1].size and
                               float(np.max(sol.y[1])) >
                               ground_level + LIFTOFF_ALTITUDE_EPS_M),
            # B2: ray modellendi mi, çıkış hangi anda/hızda oldu?
            'rail_modelled': bool(rail_modelled),
            'rail_length_m': float(rail_length) if rail_modelled else None,
            'rail_exit_time': rail_exit_time,
            'rail_exit_velocity': rail_exit_velocity,
            'solver_message': str(getattr(sol, 'message', '') or ''),
        }

    # ------------------------------------------------------------------
    # ATLANAN FAZLAR — uçuş yerle bittiğinde (B3)
    # ------------------------------------------------------------------
    @staticmethod
    def _skipped_coasting_phase(final_state: List, reason: str) -> Dict:
        """Tek noktalı (dejenere) serbest faz — hiç koşmadı.

        Araç güçlü fazda yere çarptıysa "apoje" diye bir an yoktur. Faz
        tek noktalı bir dizi olarak döner; ``_combine_flight_phases`` zaten
        ``[1:]`` dilimlediği için birleşik yörüngeye HİÇBİR nokta eklemez.
        """
        x, z, vx, vz, mass = (float(v) for v in final_state[:5])
        return {
            'time': np.array([0.0]),
            'position_x': np.array([x]),
            'position_z': np.array([z]),
            'velocity_x': np.array([vx]),
            'velocity_z': np.array([vz]),
            'apogee_time': 0.0,
            'apogee_altitude': z,
            'apogee_state': [x, z, vx, vz, mass],
            'apogee_reached': False,
            'end_reason': 'skipped',
            'skipped_reason': reason,
        }

    @staticmethod
    def _skipped_descent_phase(final_state: List, reason: str) -> Dict:
        """Tek noktalı (dejenere) iniş fazı — kurtarma sistemi hiç açılmadı.

        Araç apojeye varmadan yere çarptı: "iniş hızı" burada balistik
        ÇARPMA hızıdır, paraşütten türetilmiş bir güvenlik metriği değildir.
        Bu ayrım ``landing_velocity_basis`` ile açıkça beyan edilir.
        """
        x, z, vx, vz, _mass = (float(v) for v in final_state[:5])
        return {
            'time': np.array([0.0]),
            'position_x': np.array([x]),
            'position_z': np.array([z]),
            'velocity_x': np.array([vx]),
            'velocity_z': np.array([vz]),
            'landing_time': 0.0,
            'landing_velocity': float(np.hypot(vx, vz)),
            'landing_position_x': x,
            'landed': True,
            'recovery_deployed': False,
            'end_reason': 'skipped',
            'skipped_reason': reason,
            # Paraşüt HİÇ devreye girmedi: alan/Cd sayıları bu sonuca
            # girmediği için yayımlanmaz (uydurma değer konmaz).
            'parachute_area_m2': None,
            'parachute_cd': None,
            'parachute_deploy_delay_s': None,
            'parachute_area_assumed': False,
            'parachute_cd_assumed': False,
            'parachute_deploy_delay_assumed': False,
            'landing_velocity_basis': (
                'ballistic ground impact before apogee; the recovery system '
                'was never deployed in this run'),
        }

    @staticmethod
    def _unmodelled_descent_phase(apogee_state: List, reason: str) -> Dict:
        """İniş fazı MODELLENMEDİ — kurtarma sistemi girdisi verilmedi.

        ÖH D22 / OH-D18-05 — FAIL-CLOSED İNİŞ HÜKMÜ.

        Bu, ``_skipped_descent_phase``ten FARKLI bir hâldir ve ikisi
        karıştırılamaz:

        * ``_skipped_descent_phase``: araç apojeye varmadan YERE ÇARPTI.
          İniş anı ve hızı BİLİNİYOR (balistik çarpma), yalnız paraşütten
          gelmiyor. Sayılar yayımlanır.
        * bu metot: araç apojededir ve oradan sonrası ÇÖZÜLMEDİ, çünkü
          inişi süren tek büyüklük — paraşüt izdüşüm alanı — verilmedi.
          İniş anı, hızı ve noktası BİLİNMİYOR; yayımlanmaz.

        Neden varsayıma düşülmüyor (ÖLÇÜLDÜ, ``once.json`` B bloğu):
        kullanıcının bütün girdileri sabit tutulup YALNIZ modül sabiti
        ``DEFAULT_PARACHUTE_AREA_M2`` 1,0 -> 2,0 -> 4,0 m² yapıldığında
        yanıt ağacında **15 yaprak** oynuyordu — iniş hızı, toplam uçuş
        süresi, menzil, ortalama iniş hızı ve uyarının kendi
        ``params.area`` yaprağı dâhil. Yani yayımlanan iniş hükmü
        kullanıcının HİÇBİR girdisinin değil, araçla ilgisi olmayan bir
        modül sabitinin fonksiyonuydu. Beyan (``parachute_area_assumed``
        bayrağı + uyarı) bunu dürüstçe söylüyordu ama sayıyı kazanılmış
        hâle getirmiyordu: beyan çözüm değildir.

        Paraşüt alanı bir TASARIM büyüklüğüdür (araç kütlesine ve hedef
        iniş hızına göre boyutlandırılır); modelin literatürden türetip
        koyabileceği bir varsayılanı yoktur. Cd ve açılma gecikmesi
        farklıdır: alan VERİLDİĞİNDE kullanıcı bir kurtarma sistemi beyan
        etmiştir ve model onlara belgeli literatür değerleri (Hoerner
        Cd_p ~ 1,4) atayıp künyesini yazabilir. Bu yüzden kapı yalnız
        ALAN üstündedir.
        """
        x, z, vx, vz, _mass = (float(v) for v in apogee_state[:5])
        return {
            # Tek noktalı dizi: ``_combine_flight_phases`` [1:] dilimlediği
            # için birleşik yörüngeye HİÇBİR nokta eklenmez — uçuş apojede
            # biter ve ondan sonrası çizilmez.
            'time': np.array([0.0]),
            'position_x': np.array([x]),
            'position_z': np.array([z]),
            'velocity_x': np.array([vx]),
            'velocity_z': np.array([vz]),
            # İNİŞ HÜKMÜ YAYIMLANMAZ.
            'landing_time': None,
            'landing_velocity': None,
            'landing_position_x': None,
            'landed': False,
            'recovery_deployed': False,
            'end_reason': 'not_modelled',
            'skipped_reason': reason,
            'final_altitude_m': z,
            'parachute_area_m2': None,
            'parachute_cd': None,
            'parachute_deploy_delay_s': None,
            'parachute_area_assumed': False,
            'parachute_cd_assumed': False,
            'parachute_deploy_delay_assumed': False,
            'landing_velocity_basis': None,
            # Hükmün NEDEN geri çekildiği, alan adıyla. Kardeş 6-DOF
            # çözücüsünün ``apogee_withheld_because`` alanıyla aynı desen
            # (D15 / P4B3-02): beyan bir UYARI KODU değil VERİ ALANIDIR,
            # çünkü yeni bir i18n anahtarı bu kulvarın sahası dışındadır
            # (ölçüldü: ``hrma/static/js/i18n_common.js`` bu dalgada arayuz
            # kulvarında) ve çevrilmemiş bir kod ekranda ham anahtar
            # görünürdü.
            'landing_withheld_because': LANDING_WITHHELD_NO_PARACHUTE,
        }

    def _calculate_coasting_flight(self, initial_state: List, cross_sectional_area: float,
                                   wind_vec: Tuple[float, float],
                                   ground_level: float = 0.0) -> Dict:
        """Calculate coasting flight phase (ballistic trajectory to apogee)"""

        mass = initial_state[4]  # Constant mass after burnout

        def coasting_dynamics(t, y):
            """Dynamics during coasting flight"""
            x, z, vx, vz = y

            # Atmospheric properties
            rho, g = self._get_atmospheric_properties(z)

            # Drag force (Mach-bağımlı Cd, bağıl hızdan)
            Fx_drag, Fz_drag = self._aero_drag_components(
                vx, vz, rho, z, cross_sectional_area,
                cd_override=None, wind_vec=wind_vec
            )

            # Gravity force
            Fz_gravity = -mass * g

            # Accelerations
            ax = Fx_drag / mass
            az = (Fz_drag + Fz_gravity) / mass

            return [vx, vz, ax, az]

        # Initial conditions from powered flight
        y0 = initial_state[:4]  # x, z, vx, vz

        # Time span (until apogee - when vz becomes zero)
        def apogee_event(t, y):
            return y[3]  # vz = 0
        apogee_event.terminal = True
        apogee_event.direction = -1

        # B3 — yer teması bu fazda da sonlandırma olayıdır. Araç serbest faza
        # zaten alçalarak girdiyse (vz < 0) apoje olayı HİÇ tetiklenmez;
        # eskiden entegrasyon 300 s tavanına kadar yeraltında sürüyordu.
        def ground_event(t, y):
            return y[1] - ground_level
        ground_event.terminal = True
        ground_event.direction = -1

        t_span = (0, COASTING_TIME_LIMIT_S)

        # Solve ODE
        sol = solve_ivp(coasting_dynamics, t_span, y0,
                        events=[apogee_event, ground_event],
                        method='RK45', rtol=1e-8, atol=1e-9, dense_output=True,
                        max_step=0.5)

        # B1 — ÇÖZÜCÜ HÜKMÜ. Eskiden hiçbir olay denetimi yoktu: olay
        # tetiklenmediğinde ``sol.t[-1]`` (= 300 s tavanı) "apoje anı",
        # ``sol.y[1][-1]`` "apoje irtifası" diye yayımlanıyordu.
        if not sol.success:
            end_reason = 'solver_failed'
        elif sol.t_events[0].size:
            end_reason = 'apogee'
        elif sol.t_events[1].size:
            end_reason = 'ground'
        else:
            end_reason = 'time_limit'

        apogee_reached = (end_reason == 'apogee')

        return {
            'time': sol.t,
            'position_x': sol.y[0],
            'position_z': sol.y[1],
            'velocity_x': sol.y[2],
            'velocity_z': sol.y[3],
            # DİKKAT: apoje anı/irtifası YALNIZ ``apogee_reached`` True iken
            # gerçek apojedir. Diğer hâllerde fazın SON noktasıdır ve
            # ``end_reason`` bunu açıkça söyler; tüketici hükmü okumalıdır.
            'apogee_time': sol.t[-1],
            'apogee_altitude': sol.y[1][-1],
            'apogee_state': [sol.y[0][-1], sol.y[1][-1], sol.y[2][-1], sol.y[3][-1], initial_state[4]],
            'apogee_reached': bool(apogee_reached),
            'end_reason': end_reason,
            'time_limit_s': COASTING_TIME_LIMIT_S,
            'solver_message': str(getattr(sol, 'message', '') or ''),
        }

    def _calculate_descent_flight(self, apogee_state: List, cross_sectional_area: float,
                                  wind_vec: Tuple[float, float],
                                  ground_level: float = 0.0) -> Dict:
        """Calculate descent flight phase (with recovery system).

        F080 (v2.6.2): paraşüt alanı/Cd artık KULLANICI GİRDİSİDİR
        (``set_recovery_parameters`` ya da launch_params['parachute_area']).
        Verilmezse DEFAULT_PARACHUTE_AREA_M2 kullanılır, sonuç
        ``parachute_area_assumed=True`` ile işaretlenir ve uyarı üretilir —
        çünkü ``landing_velocity`` bir güvenlik metriği olarak okunuyor ve
        araçtan bağımsız sabit bir alandan türetilmiş olması gizlenemez.
        """

        mass = apogee_state[4]  # constant during descent

        # Kurtarma parametrelerinin çözümü
        #
        # v2.6.26 — VARSAYIM BAYRAĞI ÜÇÜ İÇİN DE. Eskiden yalnız ALAN için
        # `_assumed` bayrağı ve uyarı üretiliyordu; Cd ve açılma gecikmesi
        # sessizce varsayılana düşüyordu. Ölçüldü: aynı paraşüt alanında
        # Cd beyan edilmediği için %37 fark oluşuyor (Cd 1,4 -> 0,75 ile
        # iniş hızı 10,65 -> 14,56 m/s). İniş hızı bir GÜVENLİK metriği
        # olarak okunuyor; hangi bileşeninin varsayım olduğu gizlenemez.
        # ÖH D22 / OH-D18-05 — ALAN UYDURULMAZ. Bu metot yalnız alan
        # VERİLDİĞİNDE çağrılır (bkz. ``calculate_trajectory`` fazı 3);
        # eksik alanla çağrılırsa sessizce varsayılana düşmez, yükselir.
        # Kapıyı iki yere koymak gereksiz değil: çözücü kendi ön koşulunu
        # kendisi korumazsa, ileride eklenecek ikinci bir çağıran aynı
        # uydurmayı sessizce geri getirebilir.
        if self.parachute_area is None:
            raise TrajectoryInputError(
                'descent phase requires a parachute area; it is not '
                'defaulted (see LANDING_WITHHELD_NO_PARACHUTE)',
                problems=[{'field': 'launch_params.parachute_area',
                           'reason': 'required_for_descent_solution',
                           'value': None}])
        area_assumed = False
        chute_area = float(self.parachute_area)
        cd_assumed = self._parachute_cd_supplied is not True
        delay_assumed = self._parachute_delay_supplied is not True
        chute_cd = float(self.parachute_cd)
        deploy_delay = float(self.parachute_deploy_delay)

        def descent_dynamics(t, y):
            """Dynamics during descent"""
            x, z, vx, vz = y

            # Atmospheric properties
            rho, g = self._get_atmospheric_properties(z)

            # Kurtarma sistemi açılınca sürükleme paraşüte geçer. Paraşüt için
            # SABİT Cd uygundur (Mach düşük). Cd izdüşüm alanı tabanlıdır
            # (Hoerner 1965: içi boş yarımküre Cd_p ≈ 1.42) — bkz.
            # DEFAULT_PARACHUTE_CD notu.
            if t > deploy_delay:
                cd_override = chute_cd
                area_current = chute_area
            else:
                # Henüz açılmamış: gövde sürüklemesi, Mach-bağımlı.
                cd_override = None
                area_current = cross_sectional_area

            # Drag force (bağıl hızdan)
            Fx_drag, Fz_drag = self._aero_drag_components(
                vx, vz, rho, z, area_current,
                cd_override=cd_override, wind_vec=wind_vec
            )

            # Gravity force
            Fz_gravity = -mass * g

            # Accelerations
            ax = Fx_drag / mass
            az = (Fz_drag + Fz_gravity) / mass

            return [vx, vz, ax, az]

        # Initial conditions at apogee
        y0 = apogee_state[:4]

        # Ground impact event — zemin FIRLATMA SAHASI kotudur (B3), deniz
        # seviyesi değil. Saha rakımı verilmemişse ground_level = 0 olduğu
        # için eski davranış birebir korunur.
        def ground_event(t, y):
            return y[1] - ground_level
        ground_event.terminal = True
        ground_event.direction = -1

        t_span = (0, DESCENT_TIME_LIMIT_S)  # paraşütlü iniş uzun sürebilir

        # Solve ODE
        sol = solve_ivp(descent_dynamics, t_span, y0, events=ground_event,
                        method='RK45', rtol=1e-8, atol=1e-9, max_step=1.0)

        # B1 — İNİŞ FAZINDA DA ÇÖZÜCÜ HÜKMÜ. Ölçüldü (HEAD 9d3728e):
        # paraşüt alanı 20 m² olduğunda araç 1000 s sonunda hâlâ 185,11 m
        # havadaydı; kod yine de ``landing_time = 1000,00 s`` ve
        # ``landing_velocity = 3,412 m/s`` yayımlıyor, uyarı üretmiyordu.
        if not sol.success:
            end_reason = 'solver_failed'
        elif sol.t_events[0].size:
            end_reason = 'ground'
        else:
            end_reason = 'time_limit'
        landed = (end_reason == 'ground')

        return {
            'time': sol.t,
            'position_x': sol.y[0],
            'position_z': sol.y[1],
            'velocity_x': sol.y[2],
            'velocity_z': sol.y[3],
            # Yere temas ölçülmediyse iniş anı/hızı BİLİNMİYOR: entegrasyon
            # ufkunun son noktası "iniş" diye yayımlanmaz.
            'landing_time': float(sol.t[-1]) if landed else None,
            'landing_velocity': (
                float(np.hypot(sol.y[2][-1], sol.y[3][-1])) if landed else None),
            'landing_position_x': float(sol.y[0][-1]) if landed else None,
            'landed': bool(landed),
            'recovery_deployed': True,
            'end_reason': end_reason,
            'time_limit_s': DESCENT_TIME_LIMIT_S,
            'solver_message': str(getattr(sol, 'message', '') or ''),
            'final_altitude_m': float(sol.y[1][-1]),
            # F080: iniş hızının hangi kurtarma sisteminden çıktığı görünür
            'parachute_area_m2': chute_area,
            'parachute_cd': chute_cd,
            'parachute_deploy_delay_s': deploy_delay,
            'parachute_area_assumed': bool(area_assumed),
            'parachute_cd_assumed': bool(cd_assumed),
            'parachute_deploy_delay_assumed': bool(delay_assumed),
            'parachute_area_basis': (
                'projected-area recovery assumption; NOT sized against a '
                'landing-velocity requirement'
                if area_assumed else 'parachute area supplied by the caller'),
            'parachute_cd_basis': (
                'parachute drag coefficient Cd = 1.4 on PROJECTED area '
                '(Hoerner 1965, hollow hemisphere); a model default, not a '
                'measured canopy value'
                if cd_assumed else 'parachute cd supplied by the caller'),
            'parachute_deploy_delay_basis': (
                'parachute deploy delay after apogee is a model assumption; '
                'not derived from a recovery-system timeline'
                if delay_assumed else 'deploy delay supplied by the caller'),
        }

    def _combine_flight_phases(self, powered: Dict, coasting: Dict, descent: Dict) -> Dict:
        """Combine all flight phases into complete trajectory"""

        # Time offsets
        coasting_time_offset = powered['time'][-1]
        descent_time_offset = coasting_time_offset + coasting['time'][-1]

        # Combine time arrays
        time_powered = powered['time']
        time_coasting = coasting['time'] + coasting_time_offset
        time_descent = descent['time'] + descent_time_offset

        # Complete trajectory
        complete_time = np.concatenate([time_powered, time_coasting[1:], time_descent[1:]])
        complete_x = np.concatenate([powered['position_x'], coasting['position_x'][1:], descent['position_x'][1:]])
        complete_z = np.concatenate([powered['position_z'], coasting['position_z'][1:], descent['position_z'][1:]])
        complete_vx = np.concatenate([powered['velocity_x'], coasting['velocity_x'][1:], descent['velocity_x'][1:]])
        complete_vz = np.concatenate([powered['velocity_z'], coasting['velocity_z'][1:], descent['velocity_z'][1:]])

        # Calculate derived quantities
        complete_velocity = np.sqrt(complete_vx ** 2 + complete_vz ** 2)
        # OPUS DENETİM DÜZELTMESİ (minor): yük faktörü |a| vektör büyüklüğüdür;
        # eski skaler d|v|/dt dönüşlerde ivmeyi eksik gösterir.
        _ax = np.gradient(complete_vx, complete_time)
        _az = np.gradient(complete_vz, complete_time)
        complete_acceleration = np.sqrt(_ax ** 2 + _az ** 2)
        complete_altitude = complete_z

        return {
            'time': complete_time,
            'position_x': complete_x,
            'position_z': complete_z,
            'altitude': complete_altitude,
            'velocity_x': complete_vx,
            'velocity_z': complete_vz,
            'velocity_magnitude': complete_velocity,
            'acceleration': complete_acceleration,
            'phases': {
                'powered': powered,
                'coasting': coasting,
                'descent': descent
            }
        }

    # ------------------------------------------------------------------
    # UÇUŞ HÜKMÜ (Faz 5 / B1 + B3 + B6)
    # ------------------------------------------------------------------
    def _resolve_flight_status(self, powered: Dict, coasting: Dict,
                               descent: Dict) -> Dict:
        """Üç fazın ``end_reason``'larından tek bir uçuş hükmü çıkarır.

        Ayrım ÖNEMLİ, çünkü iki farklı başarısızlık sınıfı var:

        * ``time_limit`` / ``solver_failed`` → SAYI BİLİNMİYOR. Entegrasyon
          ufkunun son noktası apoje ya da iniş DEĞİLDİR; ondan türetilen
          büyüklükler yayımlanmaz (None). Faz 5 / B1 ve B6 tam olarak budur.
        * ``ground`` → SAYI BİLİNİYOR ama TASARIM BAŞARISIZ. Araç apojeye
          varmadan yere çarptı; hesaplanan irtifa/menzil/süre gerçek uçuşun
          gerçek sayılarıdır, sonuç ``error`` şiddetiyle damgalanır.
        """
        reasons = {
            'powered': powered.get('end_reason'),
            'coasting': coasting.get('end_reason'),
            'descent': descent.get('end_reason'),
        }
        broken = {phase: reason for phase, reason in reasons.items()
                  if reason in ('time_limit', 'solver_failed')}

        # Hangi türetilmiş büyüklük bilinmiyor?
        apogee_unknown = reasons['coasting'] in ('time_limit', 'solver_failed')
        # ÖH D22 / OH-D18-05 — ``not_modelled`` da bir "bilinmiyor"dur.
        # ``time_limit``/``solver_failed``ten farkı: çözücü BAŞARISIZ
        # olmadı, hiç ÇAĞRILMADI (girdi eksik). Bu yüzden ``broken``
        # kümesine GİRMEZ — uçuş ``valid`` kalır ve ``solver_no_event``
        # hata uyarısı basılmaz; ama inişten türeyen her sayı (iniş hızı,
        # toplam uçuş süresi, menzil) yayımlanmaz.
        landing_unknown = (
            apogee_unknown
            or reasons['descent'] in ('time_limit', 'solver_failed',
                                      'not_modelled')
            or reasons['powered'] in ('time_limit', 'solver_failed'))

        ground_impact_phase = None
        if reasons['powered'] == 'ground':
            ground_impact_phase = 'powered'
        elif reasons['coasting'] == 'ground':
            ground_impact_phase = 'coasting'

        if broken:
            end_reason = next(iter(broken.values()))
        elif ground_impact_phase is not None:
            end_reason = 'ground_impact_before_apogee'
        elif reasons['descent'] == 'ground':
            end_reason = 'landed'
        else:
            end_reason = reasons['descent'] or 'unknown'

        for phase, reason in broken.items():
            limit = {'coasting': COASTING_TIME_LIMIT_S,
                     'descent': DESCENT_TIME_LIMIT_S}.get(phase)
            self.warnings.append(_mk_warning(
                'warn.trajectory.solver_no_event', 'error',
                phase=phase, reason=reason, time_limit_s=limit))
        if ground_impact_phase is not None:
            self.warnings.append(_mk_warning(
                'warn.trajectory.ground_impact_before_apogee', 'error',
                phase=ground_impact_phase,
                lifted_off=bool(powered.get('lifted_off', True))))

        return {
            'valid': not broken,
            'end_reason': end_reason,
            'phase_end_reasons': reasons,
            'apogee_reached': bool(coasting.get('apogee_reached', False)),
            'landed': bool(descent.get('landed', False)),
            'ground_impact_phase': ground_impact_phase,
            'lifted_off': bool(powered.get('lifted_off', True)),
            'apogee_unknown': bool(apogee_unknown),
            'landing_unknown': bool(landing_unknown),
            # Hüküm geri çekildiyse SEBEBİ adıyla; çekilmediyse anahtar
            # None kalır (çıktı sözleşmesi her koşuda aynı şekli taşır).
            'landing_withheld_because': descent.get('landing_withheld_because'),
            'basis': (
                'each ODE phase reports the event that ended it; a phase that '
                'ran into its integration time limit is NOT a result and its '
                'derived quantities are published as null'),
        }

    def _calculate_performance_metrics(self, trajectory: Dict, motor_data: Dict,
                                       launch_params: Dict,
                                       flight_status: Optional[Dict] = None) -> Dict:
        """Calculate trajectory performance metrics"""

        # B1 — bilinmeyen büyüklükler YAYIMLANMAZ. flight_status verilmediyse
        # (eski çağıranlar) davranış eskisi gibidir.
        status = flight_status or {}
        apogee_unknown = bool(status.get('apogee_unknown', False))
        landing_unknown = bool(status.get('landing_unknown', False))

        # Basic trajectory metrics
        max_altitude = None if apogee_unknown else np.max(trajectory['altitude'])
        # Tepe hız ve tepe ivme yanma fazında oluşur; serbest/iniş fazı
        # tavana çarpsa bile bu iki sayı GERÇEKTİR, bu yüzden korunur.
        max_velocity = np.max(trajectory['velocity_magnitude'])
        max_acceleration = np.max(trajectory['acceleration'])
        total_flight_time = None if landing_unknown else trajectory['time'][-1]
        range_distance = None if landing_unknown else trajectory['position_x'][-1]

        # Motor performance metrics
        # Kalkış itki-ağırlık oranı BRÜT (yüklü) kütleyle hesaplanır:
        # T/W = F / (m_0·g0), m_0 = m_kuru + m_yakıt (Sutton & Biblarz, Böl. 4;
        # standart fırlatma aracı konvansiyonu). Kuru (yanma-sonu) kütle
        # kullanmak T/W'yi (m_kuru+m_yakıt)/m_kuru katı şişirir → ray-çıkış
        # >1.5 stabilite kuralına karşı TEHLİKELİ derecede iyimser sonuç verir.
        # AĞIRLIK terimi saha yerçekimini kullanır (W = m·g_yerel). Saha
        # verilmemişse g_surface == g0 → eski sayı birebir korunur.
        loaded_mass = self.vehicle_mass_dry + motor_data['propellant_mass_total']
        # ÖH D16 / OH-D15-08: T/W bir KALKIŞ büyüklüğüdür. Eğri verildiğinde
        # ortalama itkiyle hesaplamak ray-çıkış hükmünü doğrudan yanıltır
        # (ölçülen tepe/ortalama oranları 1,0033 ile 3,71 arasında). Eğri
        # yoksa satır eskisiyle birebir aynıdır.
        _egri_tw = getattr(self, '_thrust_curve', None)
        _kalkis_itkisi = (float(_egri_tw[1][0]) if _egri_tw is not None
                          else motor_data['thrust'])
        thrust_to_weight = _kalkis_itkisi / (loaded_mass * self.g_surface)
        total_impulse_to_weight = motor_data['total_impulse'] / (loaded_mass * self.g_surface)

        # Efficiency metrics — YANMA-SONU (F028, v2.6.2)
        # Eski kod iki büyüklüğü FARKLI anlardan okuyordu:
        #   irtifa  <- max_altitude_powered (burn_time+2 s penceresinin TEPESİ)
        #   hız     <- pencerenin SON adımı (burn_time+2 s)
        # ÖLÇÜLDÜ (F=3000 N, t_b=4 s, m_kuru=20 kg, m_yakıt=8 kg, 85°):
        #   raporlanan 1487.0 m / 300.8 m/s; gerçek yanma-sonu 806.7 m /
        #   399.7 m/s. altitude_efficiency de aynı oranda şişiyordu (%37.8).
        # _calculate_powered_flight artık t=burn_time'da EŞZAMANLI örneklenmiş
        # burnout_altitude/burnout_velocity üretiyor; metrikler onu okur.
        powered = trajectory['phases']['powered']
        burnout_altitude = float(powered['burnout_altitude'])
        burnout_velocity = float(powered['burnout_velocity'])
        # İrtifa oranlarının DATUMU: fırlatma sahası kotu (ÖH D15, P4B3-05).
        _datum = float(getattr(self, 'ground_level_m', 0.0) or 0.0)

        # Safety metrics
        descent = trajectory['phases']['descent']
        landing_velocity = None if landing_unknown else descent['landing_velocity']
        # Yük faktörü (g cinsinden ivme) STANDART g0 ile ifade edilir —
        # havacılık konvansiyonu; saha yerçekimiyle ölçeklenmez.
        max_g_force = max_acceleration / self.g0

        return {
            'trajectory_metrics': {
                'max_altitude': max_altitude,
                # ÖH D18 / termo-ucus a1 (P4B3-21) — APOJENİN DATUMU ADIYLA.
                # ÖLÇÜLDÜ (``once.json`` K6, taban 9071a64): bu sayı z
                # eksenidir, yani DENİZ SEVİYESİNDEN ölçülür (fırlatma
                # irtifası başlangıç koşuludur); kardeş 6-DOF ise apojeyi
                # SAHA ÜSTÜNDEN yayımlar (``alt`` = h_agl). İki panel aynı
                # "Apoje" başlığı altında iki farklı datum gösteriyordu ve
                # hiçbiri datumunu söylemiyordu. Sayı DEĞİŞMEDİ; datumu ve
                # kardeş okuması adıyla eklendi.
                'max_altitude_datum': 'mean_sea_level',
                'launch_site_elevation_m': float(_datum),
                'max_altitude_above_launch_site_m': (
                    None if max_altitude is None
                    else float(max_altitude - _datum)),
                'max_velocity': max_velocity,
                'max_acceleration': max_acceleration,
                'max_g_force': max_g_force,
                'total_flight_time': total_flight_time,
                'range_distance': range_distance,
                'landing_velocity': landing_velocity,
                # F080: iniş hızı hangi paraşütten çıktı — varsayımsa görünür
                'parachute_area_m2': descent.get('parachute_area_m2'),
                'parachute_cd': descent.get('parachute_cd'),
                'landing_velocity_assumed': bool(
                    descent.get('parachute_area_assumed', False)),
                # v2.6.26 — VARSAYIM BAYRAKLARI BU BLOKTA DA.
                # Beyan yalnız `phases.descent` altında duruyordu; bu metrik
                # bloğunu TEK BAŞINA okuyan bir tüketici (PDF, dışa aktarım,
                # panel) iniş hızının varsayımdan geldiğini göremiyordu.
                'parachute_area_assumed': bool(
                    descent.get('parachute_area_assumed', False)),
                'parachute_cd_assumed': bool(
                    descent.get('parachute_cd_assumed', False)),
                'parachute_area_basis': descent.get('parachute_area_basis'),
                'parachute_cd_basis': descent.get('parachute_cd_basis'),
                # B1/B3: iniş hızının hangi olaydan çıktığı (paraşütlü iniş mi,
                # balistik çarpma mı, yoksa hiç ölçülmedi mi) görünür olmalı.
                'landing_velocity_basis': descent.get(
                    'landing_velocity_basis',
                    'parachute descent integrated to ground contact'
                    if descent.get('landed') else None),
                'recovery_deployed': descent.get('recovery_deployed'),
            },
            'motor_performance': {
                'thrust_to_weight_ratio': thrust_to_weight,
                'total_impulse_to_weight': total_impulse_to_weight,
                'burnout_altitude': burnout_altitude,
                'burnout_velocity': burnout_velocity,
                # Apoje bilinmiyorsa ya da pozitif değilse oran TANIMSIZDIR.
                # Eski kod bu durumda 0.0 yayımlıyordu — hesaplanmamış bir
                # sayıyı "sıfır verim" gibi göstermek yanıltıcıdır.
                #
                # ÖH D15 / P4B3-05 — DATUM. Pay ve payda DENİZ SEVİYESİNDEN
                # ölçülüyordu, oysa z fırlatma kotundan başlıyor (:868). Aynı
                # araç aynı motorla, YALNIZ saha taşındığında "verim"
                # değişiyordu. ÖLÇÜLDÜ: saha 0 m -> %18,634 (doğru);
                # saha 1500 m -> yayımlanan %27,255, gerçek (saha üstü)
                # %17,139 — 1,59 KAT şişme. Oran artık iki ucundan da saha
                # kotu düşülmüş, yani UÇUŞUN kendi yüksekliği üzerinden
                # kurulur; deniz seviyesi sahada ikisi birebir aynıdır
                # (regresyon kilidi: ground_level_m = 0 -> eski sayı).
                'altitude_efficiency': (
                    (burnout_altitude - _datum) / (max_altitude - _datum) * 100
                    if (max_altitude is not None
                        and (max_altitude - _datum) > 0) else None),
                'altitude_efficiency_basis': (
                    'burnout height divided by apogee height, BOTH measured '
                    'above the launch site (datum = %.4g m ASL), not above '
                    'mean sea level: the ratio describes the flight, so a '
                    'site at altitude must not inflate it.' % _datum)
            },
            'phase_breakdown': {
                'powered_flight_time': powered['burnout_time'],
                'coasting_time': (None if apogee_unknown
                                  else trajectory['phases']['coasting']['apogee_time']),
                'descent_time': None if landing_unknown else descent['landing_time'],
                # F028: apoje zamanı MUTLAK uçuş zamanıdır. Serbest faz
                # t = powered['time'][-1] = burn_time + 2 s'de başlar (güçlü
                # faz geçiş payıyla entegre edilir), fakat eski kod ofset
                # olarak burnout_time (=burn_time) kullanıyordu → apoje 2 s
                # ERKEN raporlanıyordu. ÖLÇÜLDÜ: raporlanan 24.47 s,
                # birleşik yörüngenin gerçek tepe zamanı 26.47 s.
                # _combine_flight_phases zaten powered['time'][-1] ofsetini
                # kullanıyor; burası artık onunla TUTARLI.
                # Serbest faz apoje olayıyla bitmediyse (araç güçlü fazda
                # tepe yapıp yere çarptı) yukarıdaki toplam ÇARPMA anını
                # verirdi — "apoje" etiketiyle yanlış sayı olurdu. O hâlde
                # birleşik yörüngenin gerçek tepe anı okunur.
                'apogee_time': (
                    None if apogee_unknown else
                    (float(powered['time'][-1]) +
                     float(trajectory['phases']['coasting']['apogee_time']))
                    if trajectory['phases']['coasting'].get('apogee_reached')
                    else float(trajectory['time'][
                        int(np.argmax(trajectory['altitude']))]))
            }
        }

    # ------------------------------------------------------------------
    # ATMOSFER: U.S. Standard Atmosphere 1976 (hrma.constants.ISA_LAYERS)
    # ------------------------------------------------------------------
    def _atm_full(self, altitude: float) -> Tuple[float, float, float, float]:
        """Tam ISA atmosfer: (rho, P, T, ses_hizi) verir.

        hrma.constants.ISA_LAYERS tablosunu kullanır — solid/liquid motor
        modülleriyle TUTARLI (US Standard Atmosphere 1976, NOAA/NASA/USAF
        Tablo 4). 20 km üzerinde DOĞRU katman tablosu (eski kod 20 km üstünü
        keyfi exp(-(h-20000)/8000) ile yaklaşıyordu — bu YANLIŞTI).

        Geopotansiyel yükseklik dönüşümü:
          H = h * R_geo / (R_geo + h)   (US Std Atm 1976)
        """
        # ÖH D24 / termo-ucus a2 (OH-D23-07) — 0 m ALTI ARTIK KIRPILMIYOR.
        #
        # Buradaki eski iki satır ``if altitude < 0: altitude = 0.0`` idi ve
        # deniz seviyesi altındaki HER irtifayı deniz seviyesine yapıştırıyordu.
        # ÖLÇÜLDÜ (``a2/once.json`` K1, taban 88a29d3):
        #   _atm_full(-400) = _atm_full(-500) = _atm_full(0) = 101325,0 Pa
        #   hrma.constants.isa_pressure(-400)               = 106223,74 Pa
        # yani AYNI depoda aynı irtifanın İKİ ISA okuması vardı ve −400 m'de
        # %4,61, −5000 m'de %43,0 ayrışıyorlardı. Ölüdeniz (−430 m), Turfan
        # (−154 m) ve Danakil (−125 m) gerçek fırlatma sahalarıdır; bu kırpma
        # onların havasını deniz seviyesi havası sayıyordu.
        #
        # Kırpma yerine ISA tablosunun KENDİ tabanı: USSA 1976 tabloları −5 km
        # geopotansiyelden başlar (``ISA_TABLE_BOTTOM_M``) ve troposfer
        # katmanının aşağı uzantısı bu aralıkta TANIMLIDIR — aşağıdaki katman
        # yürüyüşü ``ISA_LAYERS[0]``ı zaten seçer, yani sonuç
        # ``constants.isa_pressure`` ile AYNI bağıntıdan gelir (bekçi:
        # tests/test_d24_termo_ucus_a2.py, iki okumanın 1e-12 içinde eşitliği).
        # Tablonun ALTI ise modellenmemiştir: sayı UYDURULMAZ, reddedilir
        # (fail-closed) — kardeş üst sınır tablonun tepesinde izotermal
        # uzantıyla ele alınıyor, alt uçta böyle bir uzantı YOKTUR.
        # KULLANICININ verdiği irtifa tablonun altındaysa çözüm HİÇ
        # BAŞLAMAZ: kapı ``_guard_solver_inputs``tadır (LAUNCH_CONDITION_BANDS
        # ['altitude'] alt ucu TAM OLARAK ``ISA_TABLE_BOTTOM_M``dir), yani
        # fail-closed hüküm ürün yüzünde verilir. Burada raise EDİLMEZ ve
        # bunun gerekçesi ÖLÇÜLDÜ: ``solve_ivp`` iniş fazında yerin çok
        # altındaki noktalarda türev deniyor (ölçüldü: −237.981 m ve
        # −1,466e15 m; tests/test_trajectory_validation.py). O noktalar bir
        # UÇUŞ DURUMU değil, entegratörün deneme adımlarıdır; orada istisna
        # atmak çözücüyü kırar. Tablonun altında tablonun EN ALT satırının
        # havası kullanılır — kırpma tablonun KENARINDADIR, eskisi gibi
        # tablonun ORTASINDA (0 m) değil.
        if altitude < ISA_TABLE_BOTTOM_M:
            altitude = ISA_TABLE_BOTTOM_M

        # Geopotansiyel yükseklik (katman tablosu geopotansiyel tabanlıdır)
        H = altitude * self.R_geopotential / (self.R_geopotential + altitude)

        # US Standard Atmosphere 1976 tablo üst sınırı = 84.852 km geopotansiyel.
        # ISA_LAYERS son katmanı (71 km, lapse=-0.002) bu yüksekliğe kadar
        # geçerli; üzerinde gradyan formülü sıcaklığı NEGATİFE çekerdi
        # (T = T_base + lapse*(H-h_base)) ve kesirli üs karmaşık sayı verirdi.
        # Bu nedenle tablo üstünü ayrı, fizksel olarak tutarlı bir izotermal
        # uzantı ile ele alıyoruz. (Sürükleme bu irtifalarda ihmal edilebilir;
        # amaç sayısal kararlılık ve negatif yoğunluk/sıcaklık önlemek.)
        # ÖH D20 / altyapi (P10B4-15): yerel 84852.0 literali KALKTI —
        # hrma.constants.ISA_TABLE_TOP_M ile BİT-AYNI ikinci tanımdı.
        H_TABLE_TOP = ISA_TABLE_TOP_M  # m, USSA 1976 üst geopotansiyel sınır

        if H <= H_TABLE_TOP:
            # İlgili katmanı seç (ISA_LAYERS: (h_taban, T_taban, lapse, P_taban))
            layer = ISA_LAYERS[0]
            for candidate in ISA_LAYERS:
                if H >= candidate[0]:
                    layer = candidate
                else:
                    break
            h_base, T_base, lapse, P_base = layer

            if lapse == 0.0:
                # İzotermal katman: P = P_b * exp(-g0*M*(H-h_b)/(R*T_b))
                T = T_base
                P = P_base * np.exp(-self.g0 * M_AIR * (H - h_base) / (R_STAR_ICAO * T_base))
            else:
                # Gradyan katman: P = P_b * (T/T_b)^(-g0*M/(R*lapse))
                T = T_base + lapse * (H - h_base)
                P = P_base * (T / T_base) ** (-self.g0 * M_AIR / (R_STAR_ICAO * lapse))
        else:
            # Tablo üstü (>84.852 km): izotermal uzantı, T = T(84.852 km).
            # 71 km katmanından 84.852 km'ye lapse=-0.002 ile inilen sıcaklık:
            #   T_top = 214.65 + (-0.002)*(84852-71000) = 186.946 K (~187 K mezopoz)
            # Bu noktadaki basınç P_top'tan üstel sönümle devam (izotermal):
            #   P = P_top * exp(-g0*M*(H - H_top)/(R*T_top))
            # ÖH D22 / P4B3-23..25 (doktrin-4 TEK KAYNAK): bu üç sayı
            # (214,65 K / −0,002 K·m⁻¹ / 3,95642 Pa) SABİT KODLUYDU. Değerler
            # ``hrma.constants.ISA_LAYERS`` son katmanının aynısıydı, yani
            # bugün sayısal fark yoktu (ölçüldü: |ΔP|/P ≤ 2,5e-7, bkz.
            # ``docs/scofield/raw/OH/D22/termo-ucus/a1/once.json``); kusur
            # AYRIŞMAYA AÇIK KAPIYDI — ISA tablosu güncellenirse bu dal
            # sessizce eski tabana demirli kalır ve kardeş 6-DOF çözücüsü
            # (``six_dof_trajectory``, ISA_LAYERS[-1]'i okur) ile aynı irtifada
            # iki farklı atmosfer yayımlanırdı. Kayıt biçimi
            # (h_taban, T_taban, lapse, P_taban) — constants.py sırasıyla.
            h_71, T_71, lapse_71, P_71 = ISA_LAYERS[-1]
            T_top = T_71 + lapse_71 * (H_TABLE_TOP - h_71)
            # P_top: son katmandan 84.852 km'ye gradyan formülüyle
            P_top = P_71 * (T_top / T_71) ** (-self.g0 * M_AIR / (R_STAR_ICAO * lapse_71))
            T = T_top
            P = P_top * np.exp(-self.g0 * M_AIR * (H - H_TABLE_TOP) / (R_STAR_ICAO * T_top))

        # Saha datumu (standart-dışı gün): sıcaklık profili sabit ΔT ile
        # kaydırılır, basınç profili ölçülen yüzey basıncı oranıyla ölçeklenir
        # (MIL-STD-210 sıcak/soğuk gün mantığı; OpenRocket/RASAero paritesi).
        # Varsayılan (0.0, 1.0) sonucu DEĞİŞTİRMEZ.
        T = float(T) + self.site_temp_offset_k
        P = float(P) * self.site_pressure_ratio

        # Sayısal güvenlik tabanı: T ve P fiziksel olarak pozitif kalmalı.
        T = max(float(T), 150.0)   # mezosfer/termosfer alt sınırı (~150-190 K)
        P = max(float(P), 1e-9)    # vakuma yakın taban (negatif/sıfır engelle)

        # Yoğunluk (ideal gaz): rho = P / (R_specific * T)
        rho = P / (R_SPECIFIC_AIR * T)

        # Ses hızı: a = sqrt(gamma * R_specific * T)
        a_sound = np.sqrt(GAMMA_AIR * R_SPECIFIC_AIR * T)

        return rho, P, T, a_sound

    def _get_atmospheric_properties(self, altitude: float) -> Tuple[float, float]:
        """Get atmospheric density and gravity at given altitude.

        Geriye uyum: (rho, g) ikilisi döndürür (eski imza korunur).
        Yoğunluk artık tam ISA_LAYERS tablosundan (>20 km dahil doğru).
        """
        rho, _P, _T, _a = self._atm_full(altitude)

        # Gravity variation with altitude (ters kare yasası).
        # Taban değer SAHA yerçekimidir (enlem bağımlı, WGS84 Somigliana);
        # saha ayarlanmamışsa g_surface == G_0 olduğundan eski sonuç birebir
        # korunur. Isp/ideal-dV bu değeri KULLANMAZ (bkz. set_launch_site).
        g = self.g_surface * (self.R_earth / (self.R_earth + max(altitude, 0.0))) ** 2

        return rho, g

    def create_trajectory_plots(self, trajectory_data: Dict) -> str:
        """Create comprehensive trajectory visualization plots"""

        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        trajectory = trajectory_data['trajectory']
        performance = trajectory_data['performance']

        # Create subplots
        fig = make_subplots(
            rows=3, cols=2,
            # BAŞLIK ÇAKIŞMASI (T67, 2026-08-03) — altıncı hücrenin künyesi
            # BİLEREK boş. Ölçüldü: gösterge kendi başlığını
            # ('Maximum Altitude (km)') hücrenin tepesine yazıyor, künye
            # ('Performance Summary') ise annotations[5]'te x=0,775 y=0,22222
            # ile TAM AYNI noktada duruyordu; iki metin üst üste biniyordu.
            # Gösterge başlığı birimi de taşıdığı için daha bilgili olan odur
            # ve göstergenin İKİ dalı (apoje var / yok) da kendi başlığını
            # zaten yazar — künye her hâlükârda gereksizdi.
            subplot_titles=(
                'Trajectory Profile', 'Altitude vs Time',
                'Velocity Profile', 'Acceleration Profile',
                'Flight Phases', ''
            ),
            specs=[
                [{'type': 'scatter'}, {'type': 'scatter'}],
                [{'type': 'scatter'}, {'type': 'scatter'}],
                [{'type': 'scatter'}, {'type': 'indicator'}]
            ]
        )

        # 1. Trajectory profile (altitude vs range)
        # NOT (v2.5.2): tum eksen dizileri _as_list ile listeye cevrilir;
        # numpy dizisi Plotly 6.x'te base64 'bdata' olur ve eski plotly.js
        # 1.58.5 grafigi BOS cizer.
        fig.add_trace(
            go.Scatter(
                x=_as_list(trajectory['position_x'] / 1000),  # Convert to km
                y=_as_list(trajectory['altitude'] / 1000),  # Convert to km
                mode='lines',
                name='Flight Path',
                line=dict(color='blue', width=3),
                hovertemplate='Range: %{x:.2f} km<br>Altitude: %{y:.2f} km'
            ),
            row=1, col=1
        )

        # Mark important points
        powered_phase = trajectory['phases']['powered']
        coasting_phase = trajectory['phases']['coasting']

        # Burnout point
        # ÖH D15 / P4B3-03 — F028'in GRAFİKTE sağ kalan ayağı.
        # İşaretçi güçlü faz PENCERESİNİN SON adımını (burn_time + 2 s)
        # okuyordu; metrik ise t = burn_time'da eşzamanlı örneklenmiş
        # ``burnout_state``i okuyor. ÖLÇÜLDÜ (aynı yanıt): metrik
        # burnout_altitude = 3321,6 m ⟷ grafik işaretçisi 4417,0 m
        # (+%32,98); metrik burnout_velocity = 599,0 m/s ⟷ grafik
        # noktası 502,8 m/s (−%16,07). İşaretçi artık METRİKLE AYNI
        # kaynaktan (burnout_state = [x, z, vx, vz, m]) beslenir.
        _bo_state = powered_phase.get('burnout_state')
        if _bo_state is not None:
            _bo_x = float(_bo_state[0]) / 1000.0
            _bo_z = float(_bo_state[1]) / 1000.0
        else:
            _bo_x = float(powered_phase['position_x'][-1] / 1000)
            _bo_z = float(powered_phase['position_z'][-1] / 1000)
        fig.add_trace(
            go.Scatter(
                x=[_bo_x],
                y=[_bo_z],
                mode='markers',
                name='Motor Burnout',
                marker=dict(color='red', size=10, symbol='circle'),
                hovertemplate='Burnout<br>Range: %{x:.2f} km<br>Altitude: %{y:.2f} km'
            ),
            row=1, col=1
        )

        # Apogee point
        fig.add_trace(
            go.Scatter(
                x=[float(coasting_phase['position_x'][-1] / 1000)],
                y=[float(coasting_phase['position_z'][-1] / 1000)],
                mode='markers',
                name='Apogee',
                marker=dict(color='green', size=12, symbol='triangle-up'),
                hovertemplate='Apogee<br>Range: %{x:.2f} km<br>Altitude: %{y:.2f} km'
            ),
            row=1, col=1
        )

        # 2. Altitude vs time
        fig.add_trace(
            go.Scatter(
                x=_as_list(trajectory['time']),
                y=_as_list(trajectory['altitude'] / 1000),  # Convert to km
                mode='lines',
                name='Altitude',
                line=dict(color='green', width=3),
                hovertemplate='Time: %{x:.1f} s<br>Altitude: %{y:.2f} km'
            ),
            row=1, col=2
        )

        # 2b. KURTARMA SİSTEMİ GÖRÜNÜR OLSUN (T68, 2026-08-03)
        # ------------------------------------------------------------------
        # Ölçülen kusur: 'Altitude vs Time' grafiğinde 4,11 km'lik apojeden
        # sonra 750 saniyelik bir iniş çizgisi vardı ve hiçbir yerde bunun
        # bir PARAŞÜTten geldiği yazmıyordu. Kullanıcı panele Cd 0,5 /
        # A 0,008 m² girmişti; o değerlerle balistik iniş ~30 s sürer, yani
        # grafik kullanıcının kendi girdisiyle açıklanamıyordu. Açılma anı
        # artık işaretlenir ve ölçülen paraşüt parametreleri (varsayım
        # olanlar işaretiyle) üstüne yazılır. Sayı yoksa işaret KONMAZ.
        recovery = trajectory_data.get('recovery') or {}
        if recovery.get('deployed') and recovery.get('deploy_time_s') is not None:
            t_dep = float(recovery['deploy_time_s'])
            _t_axis = _as_list(trajectory['time'])
            _alt_axis = _as_list(trajectory['altitude'])
            z_dep = None
            for _t, _z in zip(_t_axis, _alt_axis):
                if _t >= t_dep:
                    z_dep = float(_z)
                    break
            if z_dep is not None:
                _assumed = recovery.get('assumed') or {}
                _flag = ' (assumed)' if _assumed.get('area') or _assumed.get('cd') else ''
                _area = recovery.get('parachute_area_m2')
                _cd = recovery.get('parachute_cd')
                _rate = recovery.get('mean_descent_rate_m_s')
                _label = 'Parachute deploy'
                _detail = 'Parachute deploy at %.1f s' % t_dep
                if _area is not None and _cd is not None:
                    _detail += ' — %.3f m2 at Cd %.2f%s' % (_area, _cd, _flag)
                if _rate is not None:
                    _detail += '; mean descent %.1f m/s' % _rate
                fig.add_trace(
                    go.Scatter(
                        x=[t_dep], y=[z_dep / 1000.0],
                        mode='markers',
                        name=_label,
                        marker=dict(color='magenta', size=11, symbol='diamond'),
                        hovertemplate=_detail.replace('%', '%%'),
                    ),
                    row=1, col=2
                )

        # 3. Velocity profile
        fig.add_trace(
            go.Scatter(
                x=_as_list(trajectory['time']),
                y=_as_list(trajectory['velocity_magnitude']),
                mode='lines',
                name='Total Velocity',
                line=dict(color='red', width=3),
                hovertemplate='Time: %{x:.1f} s<br>Velocity: %{y:.1f} m/s'
            ),
            row=2, col=1
        )

        fig.add_trace(
            go.Scatter(
                x=_as_list(trajectory['time']),
                y=_as_list(trajectory['velocity_z']),
                mode='lines',
                name='Vertical Velocity',
                line=dict(color='orange', width=2, dash='dash'),
                hovertemplate='Time: %{x:.1f} s<br>Vertical Velocity: %{y:.1f} m/s'
            ),
            row=2, col=1
        )

        # 4. Acceleration profile
        fig.add_trace(
            go.Scatter(
                x=_as_list(trajectory['time'][1:]),  # Skip first point for gradient
                y=_as_list(trajectory['acceleration'][1:] / self.g0),  # Convert to g's
                mode='lines',
                name='Acceleration',
                line=dict(color='purple', width=3),
                hovertemplate='Time: %{x:.1f} s<br>Acceleration: %{y:.1f} g'
            ),
            row=2, col=2
        )

        # 5. Flight phases
        # ÖH D15 / P4B3-03 — apoje ANI metrikle aynı ofsetten kurulur.
        # Serbest faz t = powered['time'][-1] = burn_time + POWERED_PHASE_
        # MARGIN_S'te başlar; grafik ofset olarak burnout_time (= burn_time)
        # kullanıyordu, yani apoje işaretçisi TAM 2,0000 s ERKEN çiziliyordu
        # (ölçüldü: metrik 41,7328 s ⟷ grafik 39,7328 s). F028 metrik yolda
        # düzeltilmiş, grafik yolda kalmıştı.
        _coast_offset = (float(powered_phase['time'][-1])
                         if len(powered_phase.get('time', [])) else
                         float(powered_phase['burnout_time']))
        # Kalkış ve iniş noktaları YER KOTUNDADIR, 0,0 km değil: 1500 m
        # sahada grafik kalkışı ve inişi deniz seviyesine çiziyordu
        # (ölçüldü: [0.0, 4.417, 10.929, 0.0] km).
        _yer_km = float(trajectory['altitude'][0]) / 1000.0
        phase_times = _as_list([0, powered_phase['burnout_time'],
                                _coast_offset + coasting_phase['apogee_time'],
                                trajectory['time'][-1]])
        # T68: iniş paraşütle çözüldüyse etiket bunu SÖYLER — 'Landing' tek
        # başına, uçuşun son yarısının bir kurtarma sisteminden geldiğini
        # gizliyordu.
        # ÖH D22 / OH-D18-05 — GRAFİKTE OLMAYAN İNİŞ İŞARETLENMEZ.
        # ``landing_unknown`` iken dizinin son noktası bir İNİŞ DEĞİLDİR:
        # ya entegrasyon ufkunun son anıdır (``time_limit``), ya da iniş
        # fazı hiç çözülmediği için apojenin ta kendisidir
        # (``not_modelled``, paraşüt verilmedi). Eski kod ikisine de
        # 'Landing' etiketi koyuyordu — ikincisinde işaretçi apojenin
        # üstüne biniyor ve kullanıcı hesaplanmamış bir inişi grafikte
        # görüyordu. Uydurma veri grafikte de uydurmadır.
        _landing_unknown = bool(
            (trajectory_data.get('flight_status') or {}).get('landing_unknown'))
        _landing_label = ('Landing under parachute'
                          if (trajectory_data.get('recovery') or {}).get('deployed')
                          else 'Flight end' if _landing_unknown else 'Landing')
        phase_names = ['Launch', 'Burnout', 'Apogee', _landing_label]
        phase_altitudes = _as_list([_yer_km, _bo_z,
                                    coasting_phase['position_z'][-1] / 1000,
                                    float(trajectory['altitude'][-1]) / 1000.0])
        # İniş fazı hiç koşmadıysa dördüncü nokta apojenin KOPYASIDIR
        # (birleşik dizi apojede biter); tekrarlanan noktayı çizmek yerine
        # seri Apoje'de biter.
        if (_landing_unknown
                and abs(phase_times[3] - phase_times[2]) <= 1e-9
                and abs(phase_altitudes[3] - phase_altitudes[2]) <= 1e-9):
            phase_times = phase_times[:3]
            phase_names = phase_names[:3]
            phase_altitudes = phase_altitudes[:3]
        # Faz zamanları monoton olmalı; uçuş erken sonlandıysa (yere çarpma /
        # zaman aşımı) yukarıdaki dört nokta artık sıralı değildir. Böyle bir
        # koşuda apoje/iniş işaretçisi ÇİZİLMEZ — olmayan bir olayı grafikte
        # göstermek uydurma veridir.
        if not all(phase_times[i] <= phase_times[i + 1]
                   for i in range(len(phase_times) - 1)):
            cut = 2 if phase_times[1] <= phase_times[-1] else 1
            phase_times = phase_times[:cut] + [float(trajectory['time'][-1])]
            phase_altitudes = (phase_altitudes[:cut] +
                               [float(trajectory['altitude'][-1] / 1000)])
            phase_names = phase_names[:cut] + ['Flight end']

        fig.add_trace(
            go.Scatter(
                x=phase_times,
                y=phase_altitudes,
                mode='lines+markers',
                name='Flight Phases',
                line=dict(color='black', width=2),
                marker=dict(size=8, color='red'),
                text=phase_names,
                textposition='top center',
                hovertemplate='%{text}<br>Time: %{x:.1f} s<br>Altitude: %{y:.2f} km'
            ),
            row=3, col=1
        )

        # 6. Performance summary gauge
        # B1: apoje bilinmiyorsa (çözücü olayı tetiklenmedi) göstergeye SAYI
        # KONMAZ. Uydurma 0 km yazmak "roket hiç yükselmedi" demek olurdu.
        _max_alt_raw = performance['trajectory_metrics'].get('max_altitude')
        if _max_alt_raw is None:
            # Sayı yok: gösterge boş bırakılır, başlık nedeni söyler.
            fig.add_trace(
                go.Indicator(
                    mode="number",
                    value=None,
                    title={'text': "Maximum Altitude — NOT AVAILABLE "
                                   "(solver did not reach apogee)"},
                    domain={'x': [0, 1], 'y': [0, 1]},
                ),
                row=3, col=2
            )
        else:
            max_altitude_km = float(_max_alt_raw / 1000)
            # BOŞ DELTA SÖKÜLDÜ (T67, 2026-08-03): mode 'gauge+number+delta'
            # idi ama delta.reference HİÇ verilmiyordu. Ölçüldü (uygulama
            # 8084, /api/trajectory-analysis): iz 8 = Indicator,
            # mode='gauge+number+delta', 'delta' anahtarı yok, value=6,5951 km
            # -> Plotly sayının altına referansı olmayan bir değişim alanı
            # çiziyordu; ekranda içi boş bir yer tutucu kalıyordu. Uydurma bir
            # referans (0 km, hedef apoje vb.) KONMAZ: karşılaştırılacak bir
            # sayı yoksa alan da olmaz. Anlamlı bir referans (ör. kullanıcının
            # hedef apojesi) çözücüye bağlandığı gün mode'a 'delta' geri
            # eklenip delta={'reference': hedef} ile BİRLİKTE verilmelidir.
            fig.add_trace(
                go.Indicator(
                    mode="gauge+number",
                    value=max_altitude_km,
                    title={'text': "Maximum Altitude (km)"},
                    domain={'x': [0, 1], 'y': [0, 1]},
                    gauge={
                        'axis': {'range': [0, max(10, max_altitude_km * 1.2)]},
                        'bar': {'color': "darkblue"},
                        'steps': [
                            {'range': [0, max_altitude_km * 0.5], 'color': "lightgray"},
                            {'range': [max_altitude_km * 0.5, max_altitude_km * 0.8], 'color': "yellow"},
                            {'range': [max_altitude_km * 0.8, max_altitude_km * 1.2], 'color': "green"}
                        ],
                        'threshold': {
                            'line': {'color': "red", 'width': 4},
                            'thickness': 0.75,
                            'value': max_altitude_km
                        }
                    }
                ),
                row=3, col=2
            )

        # Update layout
        fig.update_layout(
            title=dict(
                text="Complete Trajectory Analysis",
                x=0.5,
                font=dict(size=18, family='Arial')
            ),
            showlegend=True,
            height=900,
            hovermode='closest'
        )

        # Update axes labels
        fig.update_xaxes(title_text="Range (km)", row=1, col=1)
        fig.update_yaxes(title_text="Altitude (km)", row=1, col=1)
        fig.update_xaxes(title_text="Time (s)", row=1, col=2)
        fig.update_yaxes(title_text="Altitude (km)", row=1, col=2)
        fig.update_xaxes(title_text="Time (s)", row=2, col=1)
        fig.update_yaxes(title_text="Velocity (m/s)", row=2, col=1)
        fig.update_xaxes(title_text="Time (s)", row=2, col=2)
        fig.update_yaxes(title_text="Acceleration (g)", row=2, col=2)
        fig.update_xaxes(title_text="Time (s)", row=3, col=1)
        fig.update_yaxes(title_text="Altitude (km)", row=3, col=1)

        # Tembel import: dongusel bagimlilik riskine karsi modul yerine
        # fonksiyon icinde (engines -> analysis -> visualization zinciri).
        from hrma.visualization.visualization import _fig_json, _match_time_axes

        # Senkron zoom (v2.5.5): zaman ekseni paylasan dort panel birbirine
        # 'matches' ile baglanir — birinde yakinlastirma hepsine uygulanir.
        # Menzil ekseni (1,1) BILEREK haric: birimi km, zaman degil.
        # plotly.js 1.58.5 'matches' destegi 1.45.0'dan beri var (teyitli).
        _match_time_axes(fig, [(1, 2), (2, 1), (2, 2), (3, 1)])

        # _fig_json: bdata'siz duz JSON — vendor plotly.js 1.58.5 uyumu
        # (tek JSON kapisi, v2.5.5).
        return _fig_json(fig)
