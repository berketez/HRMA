"""6 serbestlik dereceli (6-DOF) rijit gövde uçuş dinamiği.

Mevcut trajectory_analysis (düzlemsel nokta-kütle) korunur; bu modül
BAĞIMSIZ bir 6-DOF katmanı ekler: tutum (quaternion), açısal hız, rüzgâra
tepki (weathercocking) ve statik stabilite. Aerodinamik katsayılar
Barrowman yöntemiyle (Barrowman 1967; OpenRocket teknik dokümantasyonu,
Niskanen 2009) gövde+kanat geometrisinden türetilir.

Durum vektörü (13): [r(3), v(3), q(4), ω(3)]
  r, v : atış-yeri çapalı DÖNEN teğet düzlem çerçevesi. ENTEGRASYON ÇERÇEVESİ
         SAĞ-ELLİ (E,N,U)'dur: x=doğu, y=kuzey, z=yukarı (E×N=U).
         Coriolis ivmesi serbest uçuşta entegre edilir (opsiyonel, coriolis
         bayrağı); merkezkaç WGS84 normal yerçekimine katlanmıştır;
         yalnız taşıma (frame carry-along) hızı kapsam dışıdır.
  q    : gövde→atalet birim quaternion'u (skaler-önce: w,x,y,z)
  ω    : gövde eksenli açısal hız [rad/s]
Kütle ve itki zamana bağlı dış girdi (sabit itki ya da transient eğri).

ÇERÇEVE EL-YÖNÜ (v2.6.2 fizik denetimi, bulgu F167): modül eskiden durumu
(N,E,U) sırasında tutuyordu. O sıralama SOL-ellidir (fiziksel olarak N×E=−U)
oysa ``np.cross`` sağ-elli çapraz çarpım verir. Sonuç: yalnız Coriolis terimi
geçici bir (E,N,U) takasıyla düzeltilmiş, dönme dinamiği (M=r×F, ω×Iω,
quaternion kinematiği) ayna-görüntüsü bir dünyada çözülmüştü. Roll hiç
uyarılmadığı için (p≡0 → ω×Iω≡0) ve pitch/yaw alt-problemi düzlemsel/ayna
simetrik olduğu için sayısal etkisi ölçülemiyordu; ama kanat cant açısı veya
herhangi bir roll tahriki eklendiğinde GERÇEK hataya dönüşecekti. Çözüm
kataloğun önerdiği gibi çerçeveyi baştan (E,N,U) yapmaktır — artık modülün
TAMAMI tek ve sağ-elli bir çerçevede çalışır, ``np.cross`` her yerde geçerli.
Kaynak: vektör analizi — sol-elli ortonormal tabanda (a×b) bileşenleri
= −np.cross(a,b).

ÇIKTI SÖZLEŞMESİ DEĞİŞMEDİ: ``solve()`` sözlüğündeki 'position' / 'velocity'
dizileri hâlâ (N,E,U) satır sırasındadır (satır 0 = kuzey, 1 = doğu, 2 = yukarı)
— çağıran katman (app.py 'north'/'east') aynen çalışır. Değişen tek dış görünen
şey 'quaternion' çıktısının artık gövde→(E,N,U) dönüşümünü temsil etmesidir
(hiçbir çağıran onu tüketmiyor).

Kuvvetler:
  - Yerçekimi: ters-kare g(h), atalet -z
  - İtki: gövde +x ekseni boyunca (jimbal yok)
  - Aero: hava-bağıl hız u = v − w_rüzgâr üzerinden;
      eksenel: -q̄·S·C_A (Mach-bağımlı C_A ≈ C_d eğrisi)
      normal : -q̄·S·C_Nα·α, u'nun enine bileşeni yönünde
    Normal kuvvet CP'de etkir; CP−CG kolu momenti üretir (statik marj
    pozitifse rüzgâra dönme/weathercocking restoratif olur).
  - Sönüm: pitch/yaw için C_mq = −2·C_Nα·((x_cp−x_cg)/d)² (kuyruk hacim
    katkısı baskın). Türetme _derivatives içinde yazılıdır. NOT (v2.6.2):
    burada eskiden "Niskanen §4.2.3" atfı vardı; o bölüm numarası
    doğrulanamadığı için kaldırıldı — formül kendi türetmesiyle verilir.

Sınırlar (dürüst beyan):
  - Dönen teğet düzlem: Coriolis ivmesi (−2·Ω×v) serbest uçuşta entegre
    edilir (coriolis=True, enlem parametreli; ekvator = maksimum Coriolis).
    Dünya dönüşünün TAŞIMA hızı (≈465·cos φ m/s doğuya) fiziğe bağlanmaz —
    kalkışta v=0 kabulü; menzil/iniş noktası için gerekir, apoje/Δv için değil.
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
# USSA 1976 geopotansiyel dönüşüm yarıçapı. ORTALAMA Dünya yarıçapı (R_EARTH)
# DEĞİLDİR: standart atmosfer H = h·r0/(r0+h) dönüşümünü r0 = 6 356 766 m
# "etkin yarıçap" ile tanımlar (U.S. Standard Atmosphere 1976, geopotansiyel
# yükseklik tanımı). Kardeş trajectory_analysis._atm_full aynı değeri kullanır
# (self.R_geopotential) — iki modül aynı atmosferi versin diye burada da aynı
# sabit kullanılmalı (F165; sayısal etki 47 km'de ~0.4 m, tutarlılık meselesi).
R_GEOPOTENTIAL = 6_356_766.0  # m
# Dünya dönüş açısal hızı (Coriolis ivmesi için). launch_site.py:OMEGA_EARTH
# ile AYNI değer (IERS Konvansiyonları 2010, ω_E = 7.292115e-5 rad/s);
# modüller arası zorunlu bağımlılık yaratmamak için burada yerel tanımlı
# (rule#11 çapraz-referans). Biri değişirse ikisi birlikte güncellenmeli.
OMEGA_EARTH = 7.292115e-5  # rad/s
R_AIR = 287.053        # J/(kg·K)
GAMMA_AIR = 1.4

# Entegrasyon (atalet) çerçevesinin eksen etiketleri — bileşen sırası.
# SAĞ-ELLİ: E×N=U, yani np.cross bu çerçevede fiziksel çapraz çarpımla
# ÖZDEŞTİR (F167). Testler bu sabiti okuyup el-yönünü kilitler; sıralamayı
# değiştiren biri testi de kırar.
INERTIAL_AXES = ('east', 'north', 'up')
# Çıktı sözlüğündeki 'position'/'velocity' satır sırası (geriye dönük (N,E,U)).
_OUTPUT_ROW_ORDER = (1, 0, 2)


# ---------------------------------------------------------------------------
# Atmosfer (merkezi ISA_LAYERS tablosundan yoğunluk + ses hızı)
# ---------------------------------------------------------------------------

def _atmosphere_full(h):
    """USSA 1976: (rho [kg/m³], a_ses [m/s], P [Pa], T [K]).

    ``_atmosphere`` bunun (rho, a) ikilisini döndüren ince sarmalıdır; basınç
    itkinin irtifa telafisi için gerekli (F081), aynı fizikten okunur —
    ikinci bir atmosfer uygulaması YOK (rule#11).

    h geometrik irtifa [m] (DENİZ SEVİYESİNDEN; saha rakımı çağıran tarafta
    eklenir).

    ISA_LAYERS kayıt formatı: (h_taban, T_taban, lapse, P_taban) —
    constants.py'deki sırayla birebir (karıştırma NaN üretir!).

    Tablo üstü (>84.852 km geopotansiyel) izotermal uzantıyla ele alınır
    (kardeş trajectory_analysis._atm_full ile TUTARLI). USSA 1976 tablosu
    84.852 km'de biter; 71 km katmanının lapse=-0.002 gradyanını sonsuza
    uzatmak sıcaklığı ~178 km'de negatife çeker → (T/T_base)^(...) kesirli
    üssü karmaşık/NaN üretir. Bu nedenle tablo üstünde T o noktadaki değere
    (~187 K, mezopoz) sabitlenir ve basınç izotermal sönümle azalır.
    """
    h = max(h, 0.0)
    # Geopotansiyel dönüşüm USSA 1976 etkin yarıçapıyla (6 356 766 m) yapılır;
    # ortalama Dünya yarıçapı DEĞİL (F165 düzeltmesi, kardeş modülle tutarlı).
    H = h * R_GEOPOTENTIAL / (R_GEOPOTENTIAL + h)  # geopotansiyel
    H_TABLE_TOP = 84852.0            # m, USSA 1976 üst geopotansiyel sınır

    if H <= H_TABLE_TOP:
        T, P = 288.15, 101325.0
        for base, T_base, lapse, P_base in ISA_LAYERS:
            if H >= base:
                if lapse == 0.0:
                    T = T_base
                    P = P_base * np.exp(-G0 * (H - base) / (R_AIR * T_base))
                else:
                    T = T_base + lapse * (H - base)
                    P = P_base * (T / T_base) ** (-G0 / (lapse * R_AIR))
    else:
        # Tablo üstü: son katmandan (71 km) 84.852 km'ye inilen sıcaklıkta
        # izotermal uzantı. Katsayılar ISA_LAYERS son katmanından türetilir
        # (magic number yok; _atm_full ile birebir aynı fizik).
        base_top, T_base_top, lapse_top, P_base_top = ISA_LAYERS[-1]
        T_top = T_base_top + lapse_top * (H_TABLE_TOP - base_top)
        P_top = P_base_top * (T_top / T_base_top) ** (-G0 / (lapse_top * R_AIR))
        T = T_top
        P = P_top * np.exp(-G0 * (H - H_TABLE_TOP) / (R_AIR * T_top))

    # Sayısal güvenlik tabanı (kardeş _atm_full ile aynı): T, P pozitif kalsın.
    T = max(float(T), 150.0)
    P = max(float(P), 1e-9)
    rho = P / (R_AIR * T)
    return rho, np.sqrt(GAMMA_AIR * R_AIR * T), P, T


def _atmosphere(h):
    """USSA 1976: (rho [kg/m³], a_ses [m/s]) — geriye dönük ince sarmal."""
    rho, a_snd, _P, _T = _atmosphere_full(h)
    return rho, a_snd


def _pressure_at(h):
    """USSA 1976 ortam basıncı [Pa], geometrik irtifa h [m] (deniz sev.)."""
    return _atmosphere_full(h)[2]


# Mach bandı çarpanları — kardeş trajectory_analysis._drag_coefficient_mach
# ile BİREBİR AYNI değerler (rule#11 tek-kaynak; test_six_dof_trajectory
# içindeki iki-modül karşılaştırma testi bunu kilitler).
_CD_TRANSONIC_PEAK = 1.5      # transonik tepe çarpanı (Hoerner 1965 Böl.16)
_CD_SUPERSONIC_MID = 1.3      # M=1.2 ara değeri
_CD_SUPERSONIC_PLATEAU = 1.05  # yüksek süpersonik plato
_CD_SUPERSONIC_TAU = 2.0      # platoya yaklaşma zaman sabiti [Mach]


def _drag_coefficient_mach(mach, cd0):
    """Mach-bağımlı eksenel katsayı.

    DÜZELTME (F064, v2.6.2): eski uygulama 4 bantlı kardeş eğri yerine
    M>1.05'te tek üstel sönüm kullanıyordu; docstring "trajectory_analysis
    ile aynı şekil" diyordu ama DEĞİLDİ — aynı araç 2B ve 6-DOF panellerinde
    M=1.20'de %9.25, M=3.0'da −%5.73 farklı sürükleme görüyordu. Bantlar artık
    kardeş modülle birebir aynı: subsonik plato → M=1.05'te 1.5·Cd0 transonik
    tepe → M=1.2'de 1.3·Cd0 → 1.05·Cd0 platosuna üstel iniş.

    Kaynak: eğrinin ŞEKLİ Hoerner, "Fluid-Dynamic Drag" (1965) Böl. 16 ve
    OpenRocket teknik dokümantasyonundaki transonik ~1.5x mertebesiyle
    uyumludur; sayısal bant katsayıları amatör/sounding roket verisine
    dayanan mühendislik uydurmasıdır ve belirli bir yayına izlenebilir DEĞİLDİR
    (uydurma kaynak yazılmadı).
    """
    m = max(float(mach), 0.0)
    if m < 0.8:
        factor = 1.0
    elif m < 1.05:
        frac = (m - 0.8) / (1.05 - 0.8)
        factor = 1.0 + frac * (_CD_TRANSONIC_PEAK - 1.0)
    elif m < 1.2:
        frac = (m - 1.05) / (1.2 - 1.05)
        factor = _CD_TRANSONIC_PEAK + frac * (_CD_SUPERSONIC_MID
                                              - _CD_TRANSONIC_PEAK)
    else:
        factor = _CD_SUPERSONIC_PLATEAU + \
            (_CD_SUPERSONIC_MID - _CD_SUPERSONIC_PLATEAU) * \
            np.exp(-(m - 1.2) / _CD_SUPERSONIC_TAU)
    return cd0 * factor


# Kanat sıkıştırılabilirlik bandı sınırları (transonik harman aralığı)
_FIN_M_SUB = 0.8   # altında saf Prandtl-Glauert
_FIN_M_SUP = 1.2   # üstünde saf lineerleştirilmiş süpersonik teori


def _fin_compressibility_factor(mach):
    """Kanat normal-kuvvet eğimi için sıkıştırılabilirlik çarpanı k(M).

    Barrowman (1967) lineer teorisi SIKIŞTIRILAMAZ akış sonucudur; kod tüm
    Mach'larda tek sabit C_Nα kullanıyordu (F059). İnce profil 2B eğimi:
      - subsonik : dC_N/dα = 2π/β,  β = sqrt(1−M²)   (Prandtl-Glauert)
      - süpersonik: dC_N/dα = 4/β,  β = sqrt(M²−1)   (Ackeret lineer teorisi)
    Sıkıştırılamaz referansa (2π) göre çarpan:
      k_sub(M) = 1/sqrt(1−M²) ,  k_sup(M) = (4/2π)/sqrt(M²−1)
    M=0.8'de k=1.667, M=1.2'de k=0.960, M=2'de k=0.368 (kanat etkinliği
    süpersonikte ~%60 düşer — audit'in beklediği mertebe).

    Transonik bant (0.8 ≤ M ≤ 1.2) her iki lineer teorinin de geçersiz olduğu
    bölgedir; burada iki uç arasında DOĞRUSAL harman uygulanır. Bu harmanın
    kendisi mühendislik enterpolasyonudur, belirli bir yayına dayanmaz
    (uydurma kaynak yazılmadı); uçlardaki değerler kaynaklıdır.

    Kaynak: Anderson, "Fundamentals of Aerodynamics", sıkıştırılabilirlik
    düzeltmesi (Prandtl-Glauert) ve lineerleştirilmiş süpersonik (Ackeret)
    bölümleri; Niskanen 2009 OpenRocket Technical Documentation —
    kanat C_Nα'sının sıkıştırılabilirlikle ölçeklenmesi.

    NOT: Burun terimine (C_Nα = 2) uygulanmaz. O değer narin-cisim (slender
    body) teorisinden gelir ve birinci mertebede Mach'tan bağımsızdır.
    """
    m = max(float(mach), 0.0)
    if m <= 0.0:
        return 1.0
    if m < _FIN_M_SUB:
        return 1.0 / np.sqrt(1.0 - m * m)
    k_sub = 1.0 / np.sqrt(1.0 - _FIN_M_SUB ** 2)
    k_sup = (4.0 / (2.0 * np.pi)) / np.sqrt(_FIN_M_SUP ** 2 - 1.0)
    if m <= _FIN_M_SUP:
        frac = (m - _FIN_M_SUB) / (_FIN_M_SUP - _FIN_M_SUB)
        return k_sub + frac * (k_sup - k_sub)
    return (4.0 / (2.0 * np.pi)) / np.sqrt(m * m - 1.0)


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

        self.cn_alpha = cn_nose + cn_fins            # [1/rad], M→0 (Barrowman)
        self.x_cp = (cn_nose * xcp_nose + cn_fins * xcp_fins) / self.cn_alpha
        self.cn_alpha_nose, self.cn_alpha_fins = cn_nose, cn_fins
        self._xcp_nose, self._xcp_fins = xcp_nose, xcp_fins

    def at_mach(self, mach):
        """(C_Nα, x_cp) ikilisini verilen Mach'ta döndürür (F059 düzeltmesi).

        Kanat terimi _fin_compressibility_factor(M) ile ölçeklenir; burun terimi
        (narin-cisim, C_Nα=2) Mach'tan bağımsız kalır. Kanat payı değiştiği için
        ağırlıklı CP de Mach'a bağlıdır: süpersonikte kanat etkinliği düşer →
        CP burna doğru kayar → statik marj AZALIR. Eski kod tüm Mach'larda
        sabit C_Nα kullanıp süpersonik kararlılığı fazla iyimser gösteriyordu.

        ``self.cn_alpha`` / ``self.x_cp`` M→0 (sıkıştırılamaz Barrowman)
        değerleri olarak KALIR — statik marj konvansiyon gereği düşük hızda
        beyan edilir ve raporlanan sayı eskisiyle birebir aynıdır.
        """
        k = _fin_compressibility_factor(mach)
        cn_fins = self.cn_alpha_fins * k
        cn = self.cn_alpha_nose + cn_fins
        if cn <= 0.0:
            return self.cn_alpha, self.x_cp
        x_cp = (self.cn_alpha_nose * self._xcp_nose
                + cn_fins * self._xcp_fins) / cn
        return cn, x_cp

    def static_margin(self, x_cg, mach=0.0):
        """Statik marj [kalibre]: (x_cp − x_cg)/d. Pozitif → kararlı.

        mach verilirse o Mach'taki sıkıştırılabilirlik düzeltmeli CP kullanılır
        (varsayılan 0 → sıkıştırılamaz Barrowman, eski davranışla birebir).
        """
        if mach:
            _, x_cp = self.at_mach(mach)
        else:
            x_cp = self.x_cp
        return (x_cp - x_cg) / self.d


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
    """q̇ = ½·q⊗[0,ω] — Hamilton çarpımı, vektör kısmı w·ω + v×ω.

    Dikkat: ters sıra (½·ω⊗q) çapraz terimlerin işaretini çevirir ve yalnız
    dönme ekseni fırlatma quaternion'ının ekseniyle paralelken aynı sonucu
    verir; düzlem-dışı rüzgârda yön asimetrisi yaratır (2026-07-13 bulgusu).
    """
    w, x, y, z = q
    p, qy, r = omega_body
    return 0.5 * np.array([
        -x * p - y * qy - z * r,
        w * p + y * r - z * qy,
        w * qy + z * p - x * r,
        w * r + x * qy - y * p,
    ])


def _quat_from_elevation_azimuth(elevation_deg, azimuth_deg):
    """Gövde +x'ini verilen yükseliş/azimut doğrultusuna çeviren quaternion.

    elevation 90° = dik atış. Azimut kuzeyden saat yönünde ölçülür.

    F167: hedef vektör SAĞ-ELLİ entegrasyon çerçevesinde (E,N,U) yazılır —
    doğu = cosθ·sin(az), kuzey = cosθ·cos(az). (Eski (N,E,U) sırasında
    bileşenler yer değiştirmişti; sayısal sonuç aynıydı ama çerçeve sol-elliydi.)
    """
    el = np.radians(elevation_deg)
    az = np.radians(azimuth_deg)
    # Hedef doğrultu (atalet, E,N,U)
    target = np.array([np.cos(el) * np.sin(az),
                       np.cos(el) * np.cos(az),
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
# Coriolis ivmesi (dönen teğet düzlem)
# ---------------------------------------------------------------------------

def _coriolis_acceleration(v_enu, cos_lat, sin_lat):
    """Coriolis fiktif ivmesi a = −2·Ω × v_rel, (E,N,U) çerçevesinde.

    F167 (v2.6.2 fizik denetimi): entegrasyon çerçevesi artık BAŞTAN sağ-elli
    (E,N,U) olduğu için buradaki eski "geçici (E,N,U)'ya taşı, hesapla, (N,E,U)
    sırasına geri döndür" takası kaldırıldı — çapraz çarpım doğrudan çerçevenin
    kendisinde yapılıyor. Sayısal sonuç birebir aynıdır (takas ortonormal bir
    permütasyondu); kazanç, modülün geri kalanındaki çapraz çarpımların
    (M=r×F, ω×Iω, quaternion kinematiği) artık AYNI el-yönünü paylaşmasıdır.

    Ω yerel bileşenleri enlem φ'de (E,N,U): (0, Ω·cosφ, Ω·sinφ). Ekvatorda
    (φ=0) yatay bileşen maksimum → dik atışta Coriolis en güçlü. v_rel serbest
    uçuşta aracın atalet hızıdır (rüzgâr değil); merkezkaç/taşıma hızı BURADA
    yok (merkezkaç WGS84 yerçekimine katlanmış, taşıma hızı kapsam dışı).

    Args:
        v_enu: hız vektörü (vE, vN, vU) [m/s]
        cos_lat, sin_lat: enlem φ'nin kosinüs/sinüsü (önhesaplı)
    Returns:
        (E,N,U) çerçevesinde Coriolis ivmesi [m/s²]
    """
    omega_enu = OMEGA_EARTH * np.array([0.0, cos_lat, sin_lat])
    return -2.0 * np.cross(omega_enu, np.asarray(v_enu, dtype=float))


def _alpha_deg_series(q, v, wind):
    """Hücum açısı α [°] zaman serisi — vektörleştirilmiş (F163).

    ``_derivatives`` içindeki skaler α tanımının birebir aynısı, N nokta için
    tek seferde: u = v − w_rüzgâr (atalet), u_b = C(q)ᵀ·u (gövde),
    α = atan2(‖(u_b,y, u_b,z)‖, |u_b,x|). |u| ≤ 0.5 m/s'de α = 0 — çözücüdeki
    aerodinamik eşiğin AYNISI (o hızın altında dinamik basınç ihmal edilir).

    Args:
        q: 4×N gövde→atalet quaternion (skaler-önce), normalize edilmemiş olabilir
        v: 3×N atalet hızı [m/s] (entegrasyon çerçevesi)
        wind: (3,) hava-kütlesi hızı [m/s] (entegrasyon çerçevesi)
    """
    q = np.atleast_2d(np.asarray(q, dtype=float))
    v = np.atleast_2d(np.asarray(v, dtype=float))
    nrm = np.linalg.norm(q, axis=0)
    nrm = np.where(nrm > 0.0, nrm, 1.0)
    w, x, y, z = q[0] / nrm, q[1] / nrm, q[2] / nrm, q[3] / nrm
    u = v - np.asarray(wind, dtype=float).reshape(3, 1)
    u0, u1, u2 = u[0], u[1], u[2]
    # C = _quat_to_dcm(q) bileşenleri (gövde→atalet); u_b = Cᵀ·u
    c00 = 1 - 2 * (y * y + z * z)
    c01 = 2 * (x * y - w * z)
    c02 = 2 * (x * z + w * y)
    c10 = 2 * (x * y + w * z)
    c11 = 1 - 2 * (x * x + z * z)
    c12 = 2 * (y * z - w * x)
    c20 = 2 * (x * z - w * y)
    c21 = 2 * (y * z + w * x)
    c22 = 1 - 2 * (x * x + y * y)
    ub0 = c00 * u0 + c10 * u1 + c20 * u2
    ub1 = c01 * u0 + c11 * u1 + c21 * u2
    ub2 = c02 * u0 + c12 * u1 + c22 * u2
    alpha = np.degrees(np.arctan2(np.hypot(ub1, ub2), np.abs(ub0)))
    return np.where(np.linalg.norm(u, axis=0) > 0.5, alpha, 0.0)


# ---------------------------------------------------------------------------
# 6-DOF çözücü
# ---------------------------------------------------------------------------

def _mk_warning(code, severity='warning', **params):
    """Uyarı sözleşmesi: ``{code, params, severity}`` (bkz. safety_analysis)."""
    return {'code': code, 'params': params, 'severity': severity}


def _require_finite(**values):
    """Sonlu-değer kapısı (Faz 5 / B7) — sonlu değilse ``ValueError``.

    ÖLÇÜLDÜ (HEAD 9d3728e): ``thrust = NaN`` ile kurulan çözücüde
    ``solve(t_max=400)`` 60 saniyede DÖNMEDİ (``timeout`` çıkış kodu 124);
    sağlıklı çağrı 0,09 s sürüyor. Sebep: NaN türevler RK45'in adım kabul
    ölçütünü hiçbir zaman sağlamaz, adım sonsuza kadar küçülür. Tek istek
    bir işçi iş parçacığını süresiz tutar (masaüstü paketinde kilitlenme).

    Eski muhafız (``if not thrust or not burn_time``) bunu yakalamıyordu:
    ``not float('nan')`` Python'da ``False``'tur, yani NaN "verilmiş geçerli
    değer" sayılıyordu. Flask'ın JSON çözümleyicisi de ``NaN``/``Infinity``
    literallerini kabul ediyor, yani girdi uçtan gelebiliyor.
    """
    bad = []
    for name, value in values.items():
        if value is None:
            bad.append(f"{name}=None")
            continue
        try:
            f = float(value)
        except (TypeError, ValueError):
            bad.append(f"{name}={value!r}")
            continue
        if not np.isfinite(f):
            bad.append(f"{name}={f!r}")
    if bad:
        raise ValueError(
            "6-DOF çözücüsü sonlu olmayan girdiyle çağrıldı: " + ", ".join(bad))


class SixDOFTrajectory:
    def __init__(self, aero, dry_mass, propellant_mass,
                 thrust_curve=None, thrust=None, burn_time=None,
                 x_cg_full=None, x_cg_empty=None,
                 cd0=0.5, wind_speed=0.0, wind_direction_deg=0.0,
                 launch_elevation_deg=90.0, launch_azimuth_deg=0.0,
                 latitude_deg=None, coriolis=True, launch_altitude=0.0,
                 nozzle_exit_area=None, thrust_reference_pressure=None,
                 rail_length=5.0, roll_damping=0.05, components=None):
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
            latitude_deg: atış sahası enlemi [°] — Coriolis ivmesinin gücünü
                          ve yerel yerçekimini belirler. VERİLMEZSE (None)
                          Coriolis KENDİLİĞİNDEN KAPANIR ve uyarı üretilir:
                          eski varsayılan 0.0 idi, yani enlem bilgisi olmayan
                          her kullanıcı sessizce EKVATOR (maksimum yatay
                          Coriolis) alıyordu — 39.9°N sahada sürüklenme %30.5
                          fazla çıkıyordu (F060).
            coriolis: True → serbest uçuşta −2·Ω×v Coriolis ivmesi entegre
                      edilir (enlem verilmişse). False → kapalı
                      (izotropi/karşılaştırma senaryoları ve düz-Dünya geriye
                      dönük davranışı için).
            launch_altitude: fırlatma sahası rakımı (deniz seviyesinden) [m].
                      Atmosfer MUTLAK irtifanın fonksiyonudur (USSA 1976); eski
                      kod her sahayı deniz seviyesinde varsayıyordu ve 1500 m
                      rakımlı sahada apojeyi %7.65 EKSİK tahmin ediyordu (F023).
            nozzle_exit_area: nozul çıkış alanı A_e [m²] — verilirse itki
                      ortam basıncıyla düzeltilir: F(h) = F_ref +
                      (P_ref − P_amb(h))·A_e (Sutton & Biblarz Böl.3).
                      None → eski davranış (irtifadan bağımsız sabit itki).
            thrust_reference_pressure: verilen itki eğrisinin ölçüldüğü ortam
                      basıncı [Pa]; None → saha rakımındaki USSA 1976 basıncı
                      (deniz seviyesi test standı varsayımı yerine sahanın
                      kendi basıncı).
            rail_length: atış rayı boyu [m] — ray üstünde tutum kilitli
            roll_damping: pasif roll sönüm katsayısı
            components: opsiyonel bileşen listesi
                        [{'mass': kg, 'x': m (burundan), 'propellant': bool}];
                        verilirse pitch/yaw ataleti nokta-kütle toplamı +
                        gövde ince-silindir düzeltmesiyle kurulur (bkz.
                        _inertia). None → tekdüze narin-gövde modeli
                        (geriye dönük birebir aynı sonuç).
        """
        # B7 — SONLU-DEĞER KAPISI, çözücüye girmeden önce (fail-closed).
        # Kütle bölen olarak kullanılır (a = F/m), bu yüzden pozitiflik de
        # burada denetlenir; NaN kütle de aynı süresiz kilitlenmeyi yapar.
        _require_finite(dry_mass=dry_mass, propellant_mass=propellant_mass,
                        cd0=cd0, wind_speed=wind_speed,
                        wind_direction_deg=wind_direction_deg,
                        launch_elevation_deg=launch_elevation_deg,
                        launch_azimuth_deg=launch_azimuth_deg,
                        launch_altitude=launch_altitude or 0.0,
                        rail_length=rail_length, roll_damping=roll_damping)
        if latitude_deg is not None:
            _require_finite(latitude_deg=latitude_deg)
        if nozzle_exit_area is not None:
            _require_finite(nozzle_exit_area=nozzle_exit_area)
        if thrust_reference_pressure is not None:
            _require_finite(thrust_reference_pressure=thrust_reference_pressure)
        if float(dry_mass) + float(propellant_mass) <= 0.0 or float(dry_mass) <= 0.0:
            raise ValueError(
                "6-DOF çözücüsü pozitif kuru kütle ister "
                f"(dry_mass={dry_mass!r}, propellant_mass={propellant_mass!r})")

        self.aero = aero
        self.m_dry = float(dry_mass)
        self.m_prop = float(propellant_mass)

        if thrust_curve is not None:
            t = np.asarray(thrust_curve['time'], dtype=float)
            F = np.asarray(thrust_curve['thrust'], dtype=float)
            if not (np.all(np.isfinite(t)) and np.all(np.isfinite(F))):
                raise ValueError(
                    "thrust_curve 'time'/'thrust' sonlu olmayan değer içeriyor")
            # B3: net doğrulama — boş/tek-nokta/uyumsuz uzunluk çağıran
            # katmanda anlaşılır ValueError (endpoint 400) olsun; aksi halde
            # t[0] IndexError → 500 sızıyordu.
            if t.ndim != 1 or F.ndim != 1:
                raise ValueError(
                    "thrust_curve 'time' ve 'thrust' 1B dizi olmalı")
            if t.size != F.size:
                raise ValueError(
                    "thrust_curve 'time' ve 'thrust' aynı uzunlukta olmalı "
                    f"(time={t.size}, thrust={F.size})")
            if t.size < 2:
                raise ValueError(
                    "thrust_curve en az 2 nokta içermeli "
                    "('time' boş ya da tek noktalı)")
            if t[0] > 0.0:
                t = np.insert(t, 0, 0.0)
                F = np.insert(F, 0, F[0])
            self._t_thrust, self._F_thrust = t, F
            self.t_burn = float(t[-1])
            self._impulse = float(np.trapz(F, t))
        else:
            # DİKKAT: ``not thrust`` NaN'ı yakalamaz (``not float('nan')`` =
            # False). Sonlu-değer kapısı bu yüzden AYRI çağrılır (B7).
            _require_finite(thrust=thrust, burn_time=burn_time)
            if not thrust or not burn_time:
                raise ValueError("thrust_curve yoksa thrust ve burn_time zorunlu")
            if float(burn_time) <= 0.0:
                raise ValueError(f"burn_time pozitif olmalı (burn_time={burn_time!r})")
            self._t_thrust = np.array([0.0, float(burn_time)])
            self._F_thrust = np.array([float(thrust), float(thrust)])
            self.t_burn = float(burn_time)
            self._impulse = float(thrust) * float(burn_time)

        # C1 (perf): birikimli impuls önhesabı. Eski _mass_at her türev
        # değerlendirmesinde O(N) trapz + 2 dizi allocation yapıyordu; A1'in
        # ~300 noktalık gerçek eğrisiyle bu solve boyunca binlerce kez koşar.
        # cum_impulse[i] = trapz(F[:i+1], t[:i+1]) → _mass_at O(log N) interp'e
        # düşer. ÇIKTI BİT-AYNI: segment alanı np.trapz ile BİREBİR aynı işlem
        # sırasında hesaplanır (d·(y0+y1)/2.0 — 0.5·(y0+y1)·d DEĞİL; ikisi 1 ULP
        # sapabilir). ≤128 nokta için sonuç np.trapz ile tam bit-aynı (numpy
        # np.sum blocksize=128 altında sıralı toplar = np.cumsum). Daha büyük
        # eğride pairwise-vs-sıralı toplamdan ≤3 ULP fark kalır (makine epsilon;
        # rtol=1e-5 çözücüde etkisiz). Bkz. test_six_dof_coriolis bit testi.
        _seg = (np.diff(self._t_thrust)
                * (self._F_thrust[1:] + self._F_thrust[:-1]) / 2.0)
        self._cum_impulse = np.concatenate(([0.0], np.cumsum(_seg)))

        L = aero.L
        # Verilen CG kullanılır (UI bileşen tablosu x_cg_full/x_cg_empty
        # gönderir); yoksa/0 ise kaba L kesri tahminine düşülür — 0 m (burun
        # ucu) fiziksel olarak anlamsız olduğundan eksik girdi sayılır.
        self.x_cg_full = float(x_cg_full) if x_cg_full else 0.55 * L
        self.x_cg_empty = float(x_cg_empty) if x_cg_empty else 0.50 * L
        self.cd0 = float(cd0)
        # Rüzgârın GELDİĞİ yönden esen yatay rüzgâr vektörü (hava hareketi).
        # DİKKAT (F167): ``self.wind`` GERİYE DÖNÜK olarak (N,E,U) sırasındadır —
        # kardeş 2B modelle (trajectory_analysis._wind_vector) karşılaştıran
        # sözleşme testi wind[0]'ı KUZEY bileşeni kabul eder. Entegrasyon ise
        # sağ-elli (E,N,U) çerçevesinde yapıldığı için ``self._wind_i`` kullanılır;
        # ikisi aynı fiziksel vektörün iki bileşen sırasıdır.
        wd = np.radians(wind_direction_deg)
        self.wind = -float(wind_speed) * np.array([np.cos(wd), np.sin(wd), 0.0])
        self._wind_i = self.wind[list(_OUTPUT_ROW_ORDER)]   # (N,E,U) → (E,N,U)
        self.q0 = _quat_from_elevation_azimuth(launch_elevation_deg,
                                               launch_azimuth_deg)
        self.rail_length = float(rail_length)
        self.roll_damping = float(roll_damping)

        self.warnings = []

        # --- Fırlatma sahası rakımı (F023) --------------------------------
        # Atmosfer MUTLAK irtifanın fonksiyonudur (USSA 1976 profil tanımı);
        # yer-üstü (AGL) yüksekliğin değil. Durum vektöründeki r[2] sahaya
        # göre ölçülür, atmosfere girerken launch_altitude eklenir.
        self.launch_altitude = float(launch_altitude or 0.0)

        # Coriolis (dönen teğet düzlem). latitude_deg = atış sahası enlemi.
        # F060: enlem VERİLMEDİYSE Coriolis kapatılır. Eski varsayılan 0.0
        # (ekvator) yatay Coriolis'i MAKSİMUM yapıyordu ve enlem geçmeyen her
        # çağıran sessizce ekvator fiziği alıyordu; "bilinmeyen enlem" için
        # dürüst davranış, uydurma bir enlem seçmek değil, terimi kapatmaktır.
        self.coriolis = bool(coriolis)
        if latitude_deg is None:
            self.latitude_deg = None
            self._cos_lat = 0.0
            self._sin_lat = 0.0
            if self.coriolis:
                self.coriolis = False
                self.warnings.append(_mk_warning(
                    'warn.sixdof.coriolis_disabled_no_latitude', 'info'))
        else:
            self.latitude_deg = float(latitude_deg)
            _phi = np.radians(self.latitude_deg)
            self._cos_lat = float(np.cos(_phi))
            self._sin_lat = float(np.sin(_phi))

        # --- Yerel yerçekimi (F063) ---------------------------------------
        # Modül docstring'i "merkezkaç WGS84 normal yerçekimine katlanmıştır"
        # diyordu ama kod enlemden bağımsız 9.80665 kullanıyordu (beyan edilen
        # ama gerçekleşmeyen fizik). Enlem verilmişse taban g artık WGS84
        # Somigliana/serbest-hava değeridir (launch_site.local_gravity,
        # NIMA TR8350.2 Denk. 4-3). Ekvator/kutup farkı ±%0.27 → apojede aynı
        # mertebede sistematik sapma. Enlem yoksa 9.80665 (≈45° standart).
        if self.latitude_deg is None:
            self.g_surface = G0
        else:
            from hrma.analysis.launch_site import local_gravity
            self.g_surface = float(local_gravity(self.latitude_deg,
                                                 self.launch_altitude))

        # --- İtkinin irtifa telafisi (F081) --------------------------------
        # F(h) = F_ref + (P_ref − P_amb(h))·A_e (Sutton & Biblarz, "Rocket
        # Propulsion Elements" Böl.3: F = ṁ·v_e + (p_e − p_a)·A_e). Eski kod
        # deniz seviyesi itkisini TÜM irtifalarda sabit kullanıyordu → apoje
        # sistematik EKSİK. A_e verilmezse davranış eskisiyle birebir aynıdır
        # (uydurma A_e türetilmez; alan gerçekten bilinmiyorsa terim yok).
        self.nozzle_exit_area = None
        _ae = nozzle_exit_area
        if _ae is not None:
            _ae = float(_ae)
            if np.isfinite(_ae) and _ae > 0.0:
                self.nozzle_exit_area = _ae
        if thrust_reference_pressure is not None:
            self.thrust_reference_pressure = float(thrust_reference_pressure)
        else:
            # Referans yoksa itki eğrisinin SAHADA ölçüldüğü varsayılır.
            self.thrust_reference_pressure = _pressure_at(self.launch_altitude)
        if self.nozzle_exit_area is None:
            self.warnings.append(_mk_warning(
                'warn.sixdof.thrust_not_altitude_compensated', 'info'))

        # Opsiyonel bileşen listesi → pitch/yaw ataleti bileşen toplamından.
        # Geçersiz/negatif kayıtlar sessizce elenir; liste boş kalırsa None
        # (tekdüze model) kullanılır. Yakıt işaretli bileşenlerin kütlesi
        # uçuş sırasında kalan yakıt oranıyla ölçeklenir.
        self.components = None
        if components:
            comps = []
            for c in components:
                try:
                    m_i = float(c.get('mass', 0.0))
                    x_i = float(c.get('x', 0.0))
                except (TypeError, ValueError, AttributeError):
                    continue
                if m_i > 0.0 and np.isfinite(m_i) and np.isfinite(x_i):
                    comps.append((m_i, x_i, bool(c.get('propellant', False))))
            if comps:
                self.components = comps

    # ---- zamana bağlı büyüklükler ----

    def _thrust_at(self, t):
        """REFERANS itki (eğrinin ölçüldüğü ortam basıncında) [N].

        Kütle tüketimi bu eğriden okunur: ṁ ortam basıncından bağımsızdır,
        yalnız itki değişir (bkz. _thrust_at_altitude).
        """
        if t >= self.t_burn:
            return 0.0
        return float(np.interp(t, self._t_thrust, self._F_thrust))

    def _thrust_at_altitude(self, t, p_amb):
        """Ortam basıncına göre düzeltilmiş itki [N] (F081).

        F(h) = F_ref + (P_ref − P_amb(h))·A_e — Sutton & Biblarz, "Rocket
        Propulsion Elements" Böl.3. A_e bilinmiyorsa düzeltme uygulanmaz
        (uydurma alan türetilmez); o durumda eski sabit-itki davranışı sürer
        ve kurucu 'warn.sixdof.thrust_not_altitude_compensated' uyarısı verir.
        """
        F_ref = self._thrust_at(t)
        if self.nozzle_exit_area is None or F_ref <= 0.0:
            return F_ref
        return F_ref + (self.thrust_reference_pressure - p_amb) \
            * self.nozzle_exit_area

    def _mdot_at(self, t):
        """Anlık propelan kütle debisi [kg/s] (jet sönümü için, F062).

        Kütle tüketimi itkiyle orantılı modellendiğinden (bkz. _mass_at)
        ṁ(t) = m_prop · F_ref(t) / I_toplam.
        """
        if t >= self.t_burn or self._impulse <= 0.0:
            return 0.0
        return self.m_prop * self._thrust_at(t) / self._impulse

    def _mass_at(self, t):
        """Yakıt, itki eğrisiyle orantılı tüketilir (∝ birikmiş impuls).

        C1: birikmiş impuls _cum_impulse'ten okunur (önhesap), yalnız ti'nin
        düştüğü SON segmentin kısmi yamuk alanı eklenir. Eski uygulamayla
        BİT-AYNI: cum_impulse[k] = trapz(F[:k+1], t[:k+1]) ve kısmi terim
        0.5·(F[k]+F(ti))·(ti−t[k]) — eski np.trapz(F_part, t_part) ifadesinin
        toplam-terimleriyle birebir aynı (aynı segment alanları, aynı sıra).
        """
        if t >= self.t_burn:
            return self.m_dry
        ti = np.clip(t, self._t_thrust[0], self._t_thrust[-1])
        # ti'yi içeren segment [t[k], t[k+1]] (t kesin artan). ti < t_burn
        # burada garanti (t >= t_burn erken döndü) → k ∈ [0, N−2].
        k = int(np.searchsorted(self._t_thrust, ti, side='right')) - 1
        k = min(max(k, 0), self._t_thrust.size - 2)
        F_ti = self._thrust_at(ti)               # = interp(ti); eskiyle aynı
        # np.trapz işlem sırası: d·(y0+y1)/2.0 (bit-aynılık için birebir).
        partial = (ti - self._t_thrust[k]) * (self._F_thrust[k] + F_ti) / 2.0
        impulse_ti = self._cum_impulse[k] + partial
        frac = impulse_ti / max(self._impulse, 1e-9)
        return self.m_dry + self.m_prop * (1.0 - frac)

    def _cg_at(self, t):
        m = self._mass_at(t)
        frac = (m - self.m_dry) / max(self.m_prop, 1e-9)
        return self.x_cg_empty + (self.x_cg_full - self.x_cg_empty) * frac

    def _inertia(self, m, x_cg=None):
        """Pitch/yaw (I_t) ve roll (I_x) ataleti.

        components verilmişse: I_t = Σ m_i·(x_i − x_cg)² nokta-kütle toplamı
        + m·(3r²)/12 gövde ince-çubuk (narin silindir) radyal öz-terimi —
        tekdüze modeldeki 3r² terimiyle aynı; ayrıca tüm bileşenler aynı
        konumdaysa bile ataletin sıfıra çökmesini önler. Yakıt işaretli
        bileşenlerin kütlesi kalan yakıt oranıyla ölçeklenir; konumları
        sabittir (tank/port CG'si yaklaşık sabit varsayımı).

        components yoksa tekdüze narin gövde yaklaşımı + PARALEL EKSEN:
        I_t = m(3r²+L²)/12 + m·(x_cg − L/2)², I_x = m·r²/2.

        F162 DÜZELTMESİ: m(3r²+L²)/12 silindirin GEOMETRİK MERKEZİNDEN geçen
        enine ataletidir; oysa Euler denklemleri ve momentler CG etrafında
        yazılıyor (r_cp_b = x_cp − x_cg). Huygens-Steiner (paralel eksen)
        terimi eksikti: varsayılan x_cg = 0.55·L ile I_t %3.0 EKSİK çıkıyordu
        (pitch doğal frekansı %1.5 yüksek). Kaynak: paralel eksen teoremi;
        tekdüze silindir atalet momenti standart tablo.

        A6 (v2.6.26): F162 yalnız DOCSTRING'i güncellemişti; paralel eksen
        terimi components-yok dalına HİÇ girmemişti (``git show ea6582b``
        farkında bu dalın gövdesi değişmiyor). İki dal aynı aracı farklı
        tarif edildiğinde farklı I_t üretiyordu: tekdüze bir çubuğu nokta
        kütlelere bölüp ``components`` olarak versen Σ m_i(x_i − x_cg)²
        = mL²/12 + m(x_cg − L/2)² çıkar, yani components dalı Steiner
        terimini ZATEN içeriyordu. ÖLÇÜM (m = 25 kg, r = 0.05 m, L = 2 m,
        x_cg = 0.55·L): eski 8.348958 kg·m², yeni 8.598958 kg·m² — eski
        değer %2.91 EKSİKTİ (pitch doğal frekansı %1.5 yüksek). Yukarıdaki
        F162 notundaki %3.0 aynı farkın ESKİ değere bölünmüşüdür
        (0.25/8.348958); %2.91 ise doğru değere bölünmüşüdür (0.25/8.598958).

        Sınır (dürüst beyan): bileşenler nokta kütle sayılır; uzun bir
        bileşenin kendi boyuna öz-ataleti (m·l²/12) hesaba katılmaz, bu da
        I_t'yi bir miktar EKSİK tahmin eder. Roll ataleti her iki modelde de
        tekdüze silindir kabulüdür (bileşenlerden etkilenmez).

        İkinci sınır (dürüst beyan): her iki dal da ataleti BEYAN EDİLEN
        x_cg noktası etrafında, kütle modelini burun-referanslı [0, L]
        çerçevesinde alır. Tekdüze bir çubuğun kendi ağırlık merkezi L/2'dir;
        x_cg ≠ L/2 verildiğinde dağılım fiilen tekdüze DEĞİLDİR ve bu sayı
        bir kestirimdir. Motoru kıçta toplu bir araçta gerçek merkezcil
        atalet bu değerden büyük, kütlesi öne doğru düzgün artan bir araçta
        küçük çıkar; sapma mertebesi m·(x_cg − L/2)² kadardır.
        """
        r = self.aero.d / 2.0
        I_x = 0.5 * m * r * r
        if x_cg is None:
            x_cg = self.x_cg_full
        if self.components is None:
            # Merkezcil (geometrik merkezden geçen) terim + Huygens-Steiner
            # kaydırması. Euler denklemleri ve aerodinamik moment kolu
            # (r_cp_b = x_cp − x_cg) x_cg etrafında yazıldığı için atalet de
            # aynı nokta etrafında olmalı; components dalıyla bu sayede
            # birebir aynı sözleşmeyi kullanır.
            d_cg = x_cg - 0.5 * self.aero.L
            I_t = m * (3.0 * r * r + self.aero.L ** 2) / 12.0 \
                + m * d_cg * d_cg
            return I_x, I_t
        frac = min(max((m - self.m_dry) / max(self.m_prop, 1e-9), 0.0), 1.0)
        I_t = m * (3.0 * r * r) / 12.0
        for m_i, x_i, is_prop in self.components:
            m_eff = m_i * frac if is_prop else m_i
            I_t += m_eff * (x_i - x_cg) ** 2
        return I_x, I_t

    # ---- dinamik ----

    def _derivatives(self, t, y):
        r = y[0:3]
        v = y[3:6]
        q = y[6:10]
        q = q / np.linalg.norm(q)
        w_b = y[10:13]

        m = self._mass_at(t)
        x_cg = self._cg_at(t)
        I_x, I_t = self._inertia(m, x_cg)
        C_bi = _quat_to_dcm(q)          # gövde→atalet
        x_body_i = C_bi[:, 0]           # gövde ekseninin atalet ifadesi

        h = max(r[2], 0.0)
        rho, a_snd = _atmosphere(h)
        g = G0 * (R_EARTH / (R_EARTH + h)) ** 2

        # --- kuvvetler ---
        F_i = np.array([0.0, 0.0, -m * g])
        F_i += self._thrust_at(t) * x_body_i

        # Hava-bağıl hız (atalet). ``self._wind_i`` KULLANILIR, ``self.wind``
        # DEĞİL: v entegrasyon çerçevesinde (E,N,U), ``self.wind`` ise dış
        # sözleşme gereği (N,E,U) sırasındadır (bkz. __init__ F167 notu).
        # İkisini karıştırmak rüzgârı NE köşegeni etrafında aynalar
        # (azimut θ → 90°−θ): kuzey rüzgârı doğu rüzgârı gibi etki eder.
        u_i = v - self._wind_i
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
            arm = self.aero.x_cp - x_cg          # +x burun yönünde ölçülür
            r_cp_b = np.array([-arm, 0.0, 0.0])  # CP, CG'nin arkasında ise −x
            M_b = np.cross(r_cp_b, F_n_b)
            # Pitch/yaw sönümü (F061 düzeltmesi, v2.6.2):
            #   C_mq = −2·C_Nα·(arm/d)²   (kuyruk baskın terim)
            # Türetme: q pitch hızı CP'de Δα = q·l/V indükler → normal kuvvet
            # ΔF_N = q̄·S·C_Nα·(q·l/V), kolu l → M = −q̄·S·C_Nα·l²·q/V.
            # Standart boyutsuzlaştırma M = q̄·S·d·C_mq·(q·d/2V) ile eşitlenince
            #   C_mq·d²/2 = −C_Nα·l²  →  C_mq = −2·C_Nα·(l/d)².
            # Eski kod 2 çarpanını düşürmüştü, yani sönümü TAM YARIYA
            # indiriyordu. ÖLÇÜLDÜ (α=0, q=1 rad/s, V=250 m/s, h=1000 m,
            # standart araç): kod −2.7810 N·m, analitik −5.5621 N·m,
            # oran tam 0.5000. Uçuş zarfındaki etkisi küçüktür (apoje
            # ~%0.03, max α ~%0.3) çünkü α quasi-statik trim'e hakimdir;
            # ama katsayı kesin yanlıştı ve gust/rüzgâr kesmesi
            # senaryolarında salınım sönümü belirleyici olur.
            # Kaynak: standart pitch-damping türevi (Barrowman tabanlı model
            # roket stabilite formülasyonu; Mandell, Caporaso & Bengen,
            # "Topics in Advanced Model Rocketry", sönüm momenti katsayısı).
            c_mq = -2.0 * self.aero.cn_alpha * (arm / self.aero.d) ** 2
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
            a_i = F_i / m
        else:
            q_dot = _quat_derivative(q, w_b)
            I = np.array([I_x, I_t, I_t])
            w_dot = (M_b - np.cross(w_b, I * w_b)) / I
            a_i = F_i / m
            # Coriolis fiktif ivmesi F_i/m SONRASI eklenir; YALNIZ serbest
            # uçuşta (rayda kısıt karşılar, v≈0). v_rel = atalet hızı v
            # (rüzgâr değil). Merkezkaç/taşıma hızı eklenmez.
            if self.coriolis:
                a_i = a_i + _coriolis_acceleration(
                    v, self._cos_lat, self._sin_lat)

        return np.concatenate([v, a_i, q_dot, w_dot])

    def solve(self, t_max=400.0, max_step=0.1):
        """Kalkıştan APOJEYE kadar entegre eder.

        6-DOF katmanının amacı stabilite/weathercock/apoje analizidir;
        apoje sonrası balistik takla (kurtarma sistemi modellenmediğinden)
        hem fiziksel olarak anlamsız hem de sayısal olarak katı (yüksek ω →
        adım çökmesi) olduğu için apojede sonlanır. Kararsız araçlarda
        |ω| > 15 rad/s (takla) tespiti de erken sonlandırır — Barrowman
        lineer aerodinamiği o rejimde zaten geçersizdir.
        """
        # Bu KOŞUYA ait uyarılar. ``self.warnings`` (kuruluş uyarıları)
        # BOZULMAZ: solve() birden çok kez çağrılabilir ve aynı uyarının
        # üst üste birikmesi sayım/gösterimi bozar.
        solve_warnings = list(self.warnings)

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
        # B5 — ÇÖZÜCÜ BAŞARISI DENETLENİR (v2.6.26). Eski kod ``sol.success``
        # ve ``sol.message`` alanlarını HİÇ okumuyordu: adım küçültmede
        # tıkanan (``status = −1``) bir entegrasyonda ``sol.y`` yine de
        # kesildiği ana kadarki kısmi yörüngeyi taşıdığı için, çökmenin
        # olduğu yükseklik "apoje", o ana kadarki α ise "kararlılık hükmü"
        # diye yayımlanabiliyordu. Artık türetilmiş büyüklükler yalnız
        # yakınsayan çözümde yayımlanır.
        converged = bool(sol.success)
        solver_message = str(getattr(sol, 'message', '') or '')
        if not converged:
            end_reason = 'solver_failed'
        elif sol.t_events[0].size:
            end_reason = 'ground'
        elif sol.t_events[1].size:
            end_reason = 'apogee'
        elif sol.t_events[2].size:
            end_reason = 'tumble_detected'
        else:
            end_reason = 'time_limit'

        t = sol.t
        # Entegrasyon çerçevesi (E,N,U) — tüm iç hesaplar bu sırada yapılır.
        r = sol.y[0:3]
        v = sol.y[3:6]
        q = sol.y[6:10]
        w = sol.y[10:13]

        # Türetilmiş büyüklükler
        speed = np.linalg.norm(v, axis=0)
        alt = r[2]
        # Çözücü ilk adımda çökerse ``sol.t`` yalnız t0'ı taşıyabilir; en kötü
        # ihtimalle boş dizide argmax ValueError atar. Kısmi seri yine
        # yayımlanır ama türetilmiş skaler HİÇBİRİ (bkz. aşağıdaki
        # ``converged`` bloğu) geçerli sonuç gibi verilmez.
        i_apogee = int(np.argmax(alt)) if alt.size else 0
        alpha_hist, mach_hist = [], []
        for k in range(len(t)):
            qk = q[:, k] / np.linalg.norm(q[:, k])
            C = _quat_to_dcm(qk)
            u_i = v[:, k] - self._wind_i     # ikisi de (E,N,U); bkz. _derivatives
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
        # Yanma sonrası apoje öncesi maksimum α — kararlılık göstergesi.
        # α YALNIZ araç aerodinamik otoriteye sahipken (yeterli hız → dinamik
        # basınç q=½ρv²) anlamlıdır. Apoje yakınında hız→0 olunca herhangi bir
        # minik yanal hız bileşeni (Coriolis, rüzgâr, itki hizasızlığı) α'yı
        # ~90°'ye fırlatır ama orada q≈0 → kararlılıkla ilgisiz. Bu yüzden
        # max_alpha yalnız hızın tepe hızın %10'unun üstünde olduğu aralıkta
        # ölçülür. (Coriolis'ten ÖNCE bu latent'ti: tam dikey atışta yanal hız
        # sıfır olduğundan apojede bile α=0 kalıyor, sahte 'kararsız' gizliydi.)
        _v_floor = 0.10 * float(speed.max()) if speed.size else 0.0
        burn_mask = (t > 1.0) & (speed > _v_floor)
        if i_apogee > 0:
            burn_mask &= (t < t[i_apogee])
        max_alpha = float(alpha_arr[burn_mask].max()) if burn_mask.any() else 0.0

        # --- ÇIKTI ÇERÇEVESİ: (E,N,U) → (N,E,U) ---------------------------
        # Dış sözleşme (modül docstring'i, app.py 'north'/'east' eşlemesi,
        # launch_site.enu_to_geodetic(n, e, u) çağrısı) satır 0 = KUZEY,
        # satır 1 = DOĞU kabul eder. F167 çerçeveyi sağ-elli (E,N,U) yapmış
        # ama bu geri dönüşümü YAZMAMIŞTI: 'position'/'velocity' satırları
        # entegrasyon sırasında (doğu, kuzey, yukarı) olarak dışarı sızıyordu,
        # yani kuzey ve doğu kanalları TAKAS olmuş durumdaydı. Ölçüldü
        # (45°K dik atış, sürtünmesiz): Coriolis'in batı sapması −138.07 m
        # 'north' kanalında raporlanıyordu; 'east' kanalında ise yalnız ikinci
        # mertebe kuzey terimi (+0.40 m) görünüyordu. Rüzgâr girdisindeki
        # ikizi (aşağıdaki _wind_i düzeltmesi) hatayı testlerde maskeliyordu:
        # iki takas birbirini götürüyordu, ama Coriolis doğrudan entegrasyon
        # çerçevesinde eklendiği için maskeleme orada çalışmıyordu.
        _rows = list(_OUTPUT_ROW_ORDER)
        r_out = r[_rows]
        v_out = v[_rows]

        out = {
            'time': t,
            'position': r_out,                # 3×N [m] (x=K, y=D, z=yukarı)
            'velocity': v_out,
            # DİKKAT: 'quaternion' gövde→(E,N,U) (ENTEGRASYON çerçevesi), yani
            # position/velocity'nin (N,E,U) satır sırasıyla AYNI tabanda
            # değildir. Bilinçli: (N,E,U) sol-ellidir, sağ-elli tabandan ona
            # geçiş bir dönme DEĞİL (determinant −1) ve quaternion'la
            # temsil edilemez. Tüketen çağıran yok (yalnız norm testi).
            'quaternion': q,
            'angular_velocity': w,            # gövde ekseni (çerçeveden bağımsız)
            'altitude': alt,
            'speed': speed,
            'mach': np.array(mach_hist),
            'alpha_deg': alpha_arr,
            'apogee': float(alt[i_apogee]) if alt.size else None,
            'apogee_time': float(t[i_apogee]) if t.size else None,
            'max_speed': float(speed.max()) if speed.size else None,
            'max_mach': float(np.max(mach_hist)) if mach_hist else None,
            'max_alpha_deg': max_alpha,
            'end_reason': end_reason,
            # Yatay sapmanın normu satır sırasından bağımsızdır (permütasyon
            # ortonormal) ama tutarlılık için çıktı dizisinden okunur.
            'lateral_drift_at_end': (
                float(np.hypot(r_out[0, -1], r_out[1, -1]))
                if r_out.shape[1] else None),
            # Statik marj / C_Nα / CP SAF GEOMETRİDİR: entegrasyondan değil
            # Barrowman kapalı formundan gelir, bu yüzden çözücü çökse bile
            # geçerlidir ve None'a çevrilmez.
            'static_margin_full': float(sm_full),
            'static_margin_empty': float(sm_empty),
            'stable': bool(sm_full > 1.0 and sm_empty > 1.0 and
                           max_alpha < 15.0),
            'cn_alpha': float(self.aero.cn_alpha),
            'x_cp': float(self.aero.x_cp),
            # B5: çözücü hükmü sonucun bir parçasıdır, çağıran okuyabilsin.
            'converged': converged,
            'solver_message': solver_message,
        }
        if not converged:
            # Entegrasyon çökmüş: apoje, tepe hız/Mach, maksimum α ve
            # kararlılık hükmü YAYIMLANMAZ. Kısmi zaman serileri (çözücünün
            # çöküşe kadar gerçekten ürettiği değerler) korunur ama
            # 'end_reason' = 'solver_failed' ile açıkça damgalıdır; hiçbir
            # yerde uydurma yedek değer konmaz.
            for _key in ('apogee', 'apogee_time', 'max_speed', 'max_mach',
                         'max_alpha_deg', 'stable', 'lateral_drift_at_end'):
                out[_key] = None
        elif end_reason == 'time_limit':
            # B6 (Faz 5) — ZAMAN SINIRI SONUÇ DEĞİLDİR.
            #
            # Eski kod alanları YALNIZ ``converged == False`` iken None
            # yapıyordu. Zaman sınırında ``sol.success`` True olduğu için
            # ``apogee = max(alt)`` — yani ENTEGRASYON UFKUNUN sonundaki
            # irtifa — "apoje" diye yayımlanıyordu. ÖLÇÜLDÜ (HEAD 9d3728e):
            #   t_max = 1 s      -> apogee = 46,19 m  @ apogee_time = 1,0 s
            #   thrust = 1e7 N   -> apogee = 787 781 371 m @ 400,0 s
            # İki koşuda da araç HÂLÂ TIRMANIYORDU; verilen sayı bir apoje
            # değil, ufkun kestiği yerdeki irtifadır.
            #
            # Zirveye varılmadığı için apoje ve apoje anı YAYIMLANMAZ.
            # ``stable`` de yayımlanmaz: hüküm ``max_alpha < 15°`` koşulunu
            # içerir ve bu koşul yalnız ufkun İÇİNDE ölçülmüştür — kalan
            # uçuşta aşılıp aşılmadığı bilinmiyor.
            # Tepe hız / Mach / α ufuk içindeki GERÇEK ölçümlerdir ama üst
            # sınır değil ALT SINIRDIR; ayrı bir bayrakla damgalanır.
            for _key in ('apogee', 'apogee_time', 'stable'):
                out[_key] = None
            out['peak_values_are_lower_bounds'] = True
            out['t_max_s'] = float(t_max)
            solve_warnings.append(_mk_warning(
                'warn.sixdof.integration_time_limit', 'error',
                t_max_s=float(t_max)))
        out['warnings'] = solve_warnings
        return out
