"""Cıvatalı bağlantı (flanş/kapak) analizi — Shigley yöntemi (Dalga 3).

Basınçlı kap kapak/flanş cıvatalarının ön-yük, tork, yük paylaşımı,
ayrılma (separation) ve emniyet faktörü hesabı. Tüm formüller literatür
referanslıdır:

  Ön-yük        : F_i = 0.75·F_p (yeniden kullanılabilir bağlantı) veya
                  0.90·F_p (kalıcı bağlantı), F_p = A_t·S_p
                  → Shigley's Mechanical Engineering Design, 10th ed.,
                    Sec. 8-7, Eq. (8-31)/(8-32).
  Tork          : T = K·F_i·d, K = 0.20 (kuru) / 0.15 (yağlı)
                  → Shigley Eq. (8-27); K değerleri yaygın "nut factor"
                    pratiği (Machinery's Handbook; NASA-STD-5020 sınıfı
                    uygulama; Shigley Table 8-15 bandı 0.09–0.30 içinde).
                    Tork-kontrollü sıkmada ön-yük saçılımı ±%25 raporlanır
                    (Shigley Sec. 8-8 / NASA-STD-5020 tipik değeri).
  Rijitlikler   : k_b = A_t·E_b/l (tam diş gövde varsayımı, basit model);
                  k_m = E_m·d·A·exp(B·d/l)
                  → Wileman, Choudury, Green (1991), Shigley Eq. (8-23),
                    Table 8-8 (çelik: A=0.78715, B=0.62873;
                    alüminyum: A=0.79670, B=0.63816).
  Yük paylaşımı : C = k_b/(k_b + k_m); F_b = F_i + C·P, F_m = F_i − (1−C)·P
                  → Shigley Eq. (8-24)…(8-26).
  Emniyetler    : proof SF n_p = S_p·A_t/F_b            (Eq. 8-28)
                  aşırı-yük faktörü n_L = (S_p·A_t − F_i)/(C·P)  (Eq. 8-29)
                  ayrılma faktörü n_0 = F_i/(P·(1−C))    (Eq. 8-30)
                  YÖNETEN değerler ön-yük saçılımının UÇLARINDA hesaplanır
                  (F031, 2026-07-25): akma/proof için F_i_max = 1.25·F_i,
                  ayrılma için F_i_min = 0.75·F_i.
                  → NASA-STD-5020A "Requirements for Threaded Fastening
                    Systems in Spaceflight Hardware" Sec. 6.2;
                    Shigley 10th ed. Sec. 8-8.
  Diş alanları  : ISO 898-1:2013 Table A.1 (= Shigley Table 8-1, kaba diş).
  Sınıf dayanımı: ISO 898-1:2013 Table 3 (8.8/10.9/12.9);
                  A2-70 → ISO 3506-1 (R_m ≥ 700, R_p0.2 ≥ 450 MPa).

Malzeme (E modülü) verisi merkezi hrma/data/materials_db.py'den alınır
(parametre tutarlılığı kuralı) — yerel malzeme tablosu YOKTUR; bu modül
yalnız cıvata SINIF dayanımlarını (ISO standart değerleri) taşır.

Kullanıcıya görünen metinler İngilizce'dir.
"""

import numpy as np
from typing import Dict, Optional

from hrma.data.materials_db import get_material

# ---------------------------------------------------------------------------
# ISO 898-1:2013 Table A.1 — kaba diş (coarse pitch) gerilme alanları [mm^2]
# (Shigley 10th ed. Table 8-1 ile aynı değerler.)
# ---------------------------------------------------------------------------
#: Cıvata proof (akma) emniyet katsayısının KABUL eşiği — TEK KAYNAK.
#:
#: Bu bir "marj bandı" DEĞİLDİR, modelin kendi hüküm sınırıdır: maksimum
#: ön-yükte (F_i_max = 1,25·F_i, tork saçılımı) cıvata gerilmesi proof
#: dayanımını AŞMAMALIDIR, yani n_proof_min >= 1,0 (NASA-STD-5020A
#: "Requirements for Threaded Fastening Systems in Spaceflight Hardware"
#: Sec. 6.2; Shigley 10th ed. Sec. 8-8, Eq. 8-28). Standart bu sınırın
#: ÜSTÜNDE ayrıca bir "marjinal" bandı tanımlamaz.
#:
#: ÖH D17 / P5B1-06 (Fable-D15 ŞARTI): ``structural_analysis`` ayrı bir
#: ``proof_SF_min < 1.2 -> MARGINAL`` eşiği yazıyordu; depoda o 1,2'nin
#: kaynağı YOKTU (bu modülde tek eşik 1,0). Kaynaksız eşik kaldırıldı ve
#: iki üretici de bu sabiti okuyor (doktrin 4: tek kaynak).
PROOF_SF_ACCEPTANCE_LIMIT: float = 1.0

#: Ayrılma (separation) faktörünün KABUL eşiği — aynı standardın aynı
#: bölümü; ``n_separation_min < 1,0`` eklem açılıyor demektir.
SEPARATION_SF_ACCEPTANCE_LIMIT: float = 1.0

# ---------------------------------------------------------------------------
# Kapak/flanş cıvata birleşiminin VARSAYILAN kabulleri — TEK KAYNAK
# ---------------------------------------------------------------------------
#: ÖH D18 (kalem P15B2-09). Bu sözleşme ÜÇ motor dosyasında üç kez yazılıydı
#: (hybrid_rocket_engine.CLOSURE_JOINT_DEFAULTS,
#: LiquidRocketEngine.LIQUID_CLOSURE_JOINT_DEFAULTS,
#: SolidRocketEngine.SOLID_CLOSURE_JOINT_DEFAULTS). ÖLÇÜLDÜ
#: (docs/scofield/raw/OH/D18/hibrit/a1/once.json, P15B2_09; taban 9071a64):
#: üç kopyanın ORTAK üç alanı (size / property_class / bolt_count_range)
#: bugün ayrışmıyor (ayrışan alan sayısı 0) ama eşitliği sınayan bekçi
#: YOKTU — sessiz ayrışma serbestti. Tanım artık burada; kopyalar buradan
#: türetilir ya da buna karşı denetlenir
#: (tests/test_d18_hibrit_a1.py::TestP15B209KapakBirlesimiTekKaynak).
#:
#: Bunlar HESAP DEĞİL, kullanıcı girdisi verilmediğinde kullanılan beyanlı
#: sözleşme değerleridir ve çıktıda adıyla beyan edilirler. Cıvata
#: SAYISI'nın varsayılanı YOKTUR — sayı verilmezse birleşim
#: boyutlandırılmaz (uydurma cıvata sayısı yasak); ``bolt_count_range``
#: yalnız kullanıcının verdiği sayının kabul bandıdır.
CLOSURE_JOINT_DEFAULTS: Dict = {
    'size': 'M8',
    'property_class': '8.8',
    'bolt_count_range': (1, 200),
}

#: Birleşimin ÜYE malzemesi için beyanlı varsayılan. Katı motor bunu
#: BİLEREK KULLANMAZ: ÖH D15 / P2B2-12'de üye malzemesi kasa malzemesinden
#: türetildi (Shigley Böl. 8: üye rijitliği k_m kasanın E modülünden gelir)
#: ve sessizce alüminyuma düşmek yasaklandı — bu yüzden katı motorun
#: kopyasında bu anahtar YOKTUR ve olmaması DOĞRUDUR. Hibrit ve sıvı
#: motorda henüz bir üye-malzemesi girdi kanalı bulunmadığı için değer
#: beyanlı varsayılan olarak kalır.
CLOSURE_JOINT_MEMBER_MATERIAL_DEFAULT: str = 'aluminum_6061'

THREAD_STRESS_AREA_MM2: Dict[str, float] = {
    'M4': 8.78,
    'M5': 14.2,
    'M6': 20.1,
    'M8': 36.6,
    'M10': 58.0,
    'M12': 84.3,
    'M14': 115.0,
    'M16': 157.0,
    'M18': 192.0,
    'M20': 245.0,
    'M22': 303.0,
    'M24': 353.0,
}

# Wileman/Choudury/Green (1991) üye rijitliği eğri uydurma sabitleri
# (Shigley Eq. 8-23, Table 8-8). d/l ~ 0.1–2.0 aralığında geçerli fit.
_WILEMAN_CONSTANTS = {
    'steel': {'A': 0.78715, 'B': 0.62873},
    'aluminum': {'A': 0.79670, 'B': 0.63816},
}

#: Altıköşe cıvata BASMA (yatak) yüzeyinin dış çapı d_w [mm] — ISO 4014 /
#: DIN EN ISO 4014 Tablo 2 "d_w min" sütunu. Yatak gerilmesinin hesaplandığı
#: halka bu çap ile delik çapı arasındadır (VDI 2230 Blatt 1 §5.5.4).
BOLT_BEARING_FACE_DIAMETER_MM = {
    'M4': 5.9, 'M5': 6.9, 'M6': 8.9, 'M8': 11.6, 'M10': 14.6, 'M12': 16.6,
    'M14': 19.6, 'M16': 22.5, 'M18': 25.3, 'M20': 28.2, 'M22': 31.7,
    'M24': 33.6,
}

#: Cıvata deliği çapı [mm] — ISO 273 "medium" (orta) geçme sınıfı. Yatak
#: halkasının İÇ çapıdır; delik büyüdükçe yatak alanı küçülür.
BOLT_CLEARANCE_HOLE_DIAMETER_MM = {
    'M4': 4.5, 'M5': 5.5, 'M6': 6.6, 'M8': 9.0, 'M10': 11.0, 'M12': 13.5,
    'M14': 15.5, 'M16': 17.5, 'M18': 20.0, 'M20': 22.0, 'M22': 24.0,
    'M24': 26.0,
}


def _pozitif_sonlu(alan: str, deger) -> float:
    """Sonlu ve kesin pozitif sayı; değilse ``ValueError`` (alan adıyla)."""
    if isinstance(deger, bool):
        raise ValueError(f"'{alan}' must be a number, not a boolean")
    try:
        sayi = float(deger)
    except (TypeError, ValueError):
        raise ValueError(f"'{alan}' must be a number (got {deger!r})")
    if not np.isfinite(sayi):
        raise ValueError(f"'{alan}' must be finite (got {deger!r})")
    if sayi <= 0:
        raise ValueError(
            f"'{alan}' must be strictly positive (got {deger!r}). Zero is not "
            "a measurement and a negative diameter is not a small one: it "
            "enters the load through its SQUARE, so the sign disappears and "
            "the result is indistinguishable from the positive case.")
    return sayi


def seal_diameter_max_mm() -> float:
    """Sızdırmazlık çapı üst sınırı [mm] — YENİ EŞİK DEĞİL.

    Tek kaynak ``MotorDataValidator.limits['chamber_diameter']`` (max 5,0 m).
    Cıvatalı kapak bir hazne/tank kapağıdır; sızdırmazlık çapı hazne ölçeğinde
    bir uzunluktur. Sayı deponun kendi kanonik tablosundan okunur (doktrin 4).
    """
    from hrma.validation.motor_validation import MotorDataValidator
    return float(MotorDataValidator().limits['chamber_diameter']['max']) * 1e3


def _bolt_class_props(property_class: str, d_mm: float) -> Dict:
    """Cıvata sınıfı mukavemet değerleri [Pa].

    Kaynaklar:
      8.8 / 10.9 / 12.9 → ISO 898-1:2013 Table 3 (S_p = proof stress,
        S_y = R_p0.2, S_u = R_m). 8.8'de d≤16 / d>16 ayrımı standarttan.
      A2-70 → ISO 3506-1 (R_m ≥ 700 MPa, R_p0.2 ≥ 450 MPa). ISO 3506
        ayrıca 'proof stress' tanımlamaz; S_p ≈ 0.9·R_p0.2 alınır — ISO
        898-1 sınıflarındaki S_p/R_p0.2 ≈ 0.88–0.91 oranıyla tutarlı
        (approximate).
    """
    pc = str(property_class).strip().upper().replace('_', '-')
    if pc == '8.8':
        if d_mm <= 16.0:
            return {'S_p': 580e6, 'S_y': 640e6, 'S_u': 800e6,
                    'stainless': False,
                    'source': 'ISO 898-1:2013 Table 3 (class 8.8, d <= 16 mm)'}
        return {'S_p': 600e6, 'S_y': 660e6, 'S_u': 830e6,
                'stainless': False,
                'source': 'ISO 898-1:2013 Table 3 (class 8.8, d > 16 mm)'}
    if pc == '10.9':
        return {'S_p': 830e6, 'S_y': 940e6, 'S_u': 1040e6,
                'stainless': False,
                'source': 'ISO 898-1:2013 Table 3 (class 10.9)'}
    if pc == '12.9':
        return {'S_p': 970e6, 'S_y': 1100e6, 'S_u': 1220e6,
                'stainless': False,
                'source': 'ISO 898-1:2013 Table 3 (class 12.9)'}
    if pc in ('A2-70', 'A270'):
        return {'S_p': 405e6, 'S_y': 450e6, 'S_u': 700e6,
                'stainless': True,
                'source': ('ISO 3506-1 class 70 (Rm >= 700, Rp0.2 >= 450 '
                           'MPa); S_p ~ 0.9*Rp0.2 (approximate)')}
    raise ValueError(
        f"Unknown bolt property class '{property_class}'. "
        f"Available: 8.8, 10.9, 12.9, A2-70")


class BoltedJointAnalyzer:
    """Flanş/kapak cıvata bağlantısı analizörü (Shigley 10th ed., Ch. 8).

    Girdi: bağlantı tanımı (cıvata boyutu/sınıfı/sayısı, sıkma boyu, üye
    malzemesi) + yük durumu (kap iç basıncı × kapak/sızdırmazlık alanı).
    Çıktı: cıvata başına yük, önerilen tork, ayrılma marjı, emniyet
    faktörleri (İngilizce alan adlarıyla, JSON-uyumlu sözlük).
    """

    K_DRY = 0.20          # kuru montaj nut factor (Shigley Eq. 8-27 pratiği)
    K_LUBRICATED = 0.15   # yağlı montaj nut factor
    TORQUE_PRELOAD_UNCERTAINTY = 0.25  # ±%25 ön-yük saçılımı (tork kontrolü)

    def __init__(self, size: str = 'M8', property_class: str = '8.8',
                 bolt_count: int = 8, grip_length_mm: float = 20.0,
                 member_material: Optional[str] = None,
                 lubricated: bool = False, reusable: bool = True):
        """
        Args:
            size: metrik kaba diş boyutu, 'M4'…'M24' (ISO 898-1 Table A.1)
            property_class: '8.8' | '10.9' | '12.9' | 'A2-70'
            bolt_count: cıvata sayısı (>= 1)
            grip_length_mm: sıkma boyu l (flanş + kapak kalınlığı) [mm]
            member_material: sıkılan üyelerin malzemesi — materials_db
                anahtarı (E modülü ve Wileman sabit seçimi için). ZORUNLU:
                ÖH D15 / P5B1-05 öncesinde bu alan sessizce 'aluminum_6061'
                varsayıyordu ve varsayılan AYRILMA HÜKMÜNÜ ÇEVİRİYORDU
                (ölçüldü, once_b1.json: M10 / 8.8 / 8 cıvata / sıkma boyu
                30 mm / sızdırmazlık çapı 160 mm; 95 / 100 / 110 bar'da
                alüminyum marj 1,2438 / 1,1816 / 1,0742 ile "açılmıyor"
                derken gerçek çelik flanşta 0,9504 / 0,9029 / 0,8208 ile
                AYRILMA çıkıyordu — separated bayrağı False ↔ True). Üye
                malzemesi k_m'yi (dolayısıyla C = k_b/(k_b+k_m) yük dağılım
                oranını) doğrudan belirler ve ayrılma modülün kendi
                beyanına göre ASIL kriterdir; bilinmeyen bir üye malzemesi
                için hüküm KAZANILAMAZ. None -> ValueError.
            lubricated: True → K = 0.15, False → K = 0.20
            reusable: True → F_i = 0.75·F_p, False (kalıcı) → 0.90·F_p
        """
        size_key = str(size).strip().upper()
        if size_key not in THREAD_STRESS_AREA_MM2:
            raise ValueError(
                f"Unknown bolt size '{size}'. "
                f"Available: {sorted(THREAD_STRESS_AREA_MM2)}")
        n = int(bolt_count)
        if n < 1:
            raise ValueError("bolt_count must be >= 1")
        grip = float(grip_length_mm)
        if not np.isfinite(grip) or grip <= 0:
            raise ValueError("grip_length_mm must be a positive number")

        self.size = size_key
        self.d_mm = float(size_key[1:])          # nominal çap [mm]
        self.A_t_mm2 = THREAD_STRESS_AREA_MM2[size_key]
        self.property_class = str(property_class).strip()
        self.props = _bolt_class_props(self.property_class, self.d_mm)
        self.bolt_count = n
        self.grip_length_mm = grip
        self.lubricated = bool(lubricated)
        self.reusable = bool(reusable)

        # Üye malzemesi merkezi DB'den (E_m + Wileman sabiti seçimi).
        # ÖH D15 / P5B1-05: fail-closed — üye malzemesi uydurulmaz.
        if member_material is None or str(member_material).strip() == '':
            raise ValueError(
                "'member_material' is required: the clamped members' Young "
                "modulus sets the member stiffness k_m and therefore the "
                "load factor C, which governs the joint-separation verdict. "
                "Supplying no material would silently assume one and can "
                "flip 'separated' from False to True (measured: aluminium "
                "default said the joint stays closed at 95-110 bar where "
                "real steel flanges separate). Pass a materials_db key, "
                "e.g. 'steel_4130' or 'aluminum_6061'.")
        self.member_material = str(member_material)
        self._member = get_material(self.member_material)

        # Cıvata E modülü de merkezi DB'den: karbon çeliği sınıfları →
        # 'steel' kaydı; A2-70 → 'ss_304' (östenitik paslanmaz) kaydı.
        bolt_mat_key = 'ss_304' if self.props['stainless'] else 'steel'
        self._bolt_E = float(get_material(bolt_mat_key)['elastic_modulus'])

    # ------------------------------------------------------------------
    # Alt hesaplar
    # ------------------------------------------------------------------

    def preload(self) -> Dict:
        """Ön-yük ve proof yükü (Shigley Eq. 8-31/8-32).

        F_p = A_t·S_p ; F_i = 0.75·F_p (yeniden kullanılabilir) / 0.90·F_p
        (kalıcı bağlantı).
        """
        A_t = self.A_t_mm2 * 1e-6                       # m^2
        F_p = A_t * self.props['S_p']                   # N
        frac = 0.75 if self.reusable else 0.90
        return {'proof_load_N': F_p, 'preload_N': frac * F_p,
                'preload_fraction': frac}

    def torque(self) -> Dict:
        """Önerilen sıkma torku T = K·F_i·d (Shigley Eq. 8-27).

        K = 0.20 kuru / 0.15 yağlı (nut factor). Tork-kontrollü sıkmada
        gerçekleşen ön-yük ±%25 saçılır; bant raporlanır.
        """
        F_i = self.preload()['preload_N']
        K = self.K_LUBRICATED if self.lubricated else self.K_DRY
        d = self.d_mm * 1e-3
        T = K * F_i * d
        u = self.TORQUE_PRELOAD_UNCERTAINTY
        return {
            'recommended_torque_Nm': T,
            'K_nut_factor': K,
            'condition': 'lubricated' if self.lubricated else 'dry',
            'preload_uncertainty_pct': u * 100.0,
            'preload_scatter_band_N': [(1.0 - u) * F_i, (1.0 + u) * F_i],
        }

    def stiffness(self) -> Dict:
        """Cıvata/üye rijitlikleri ve yük paylaşım katsayısı C.

        k_b = A_t·E_b/l : tam diş gövde varsayımı (basit model; kısmen dişli
        cıvatada gerçek k_b biraz daha yüksek → C hafif yüksek olur; ayrılma
        marjı için konservatif, cıvata yük payı için hafif iyimser —
        approximate, ±~%10).
        k_m = E_m·d·A·exp(B·d/l) : Wileman/Choudury/Green FEA fit'i
        (Shigley Eq. 8-23, Table 8-8).
        """
        l = self.grip_length_mm * 1e-3                  # m
        d = self.d_mm * 1e-3                            # m
        A_t = self.A_t_mm2 * 1e-6                       # m^2
        k_b = A_t * self._bolt_E / l

        E_m = float(self._member['elastic_modulus'])
        member_name = str(self._member.get('name', '')).lower()
        if 'aluminum' in member_name or 'aluminium' in member_name:
            const_key = 'aluminum'
        else:
            const_key = 'steel'
        cc = _WILEMAN_CONSTANTS[const_key]
        k_m = E_m * d * cc['A'] * np.exp(cc['B'] * d / l)
        C = k_b / (k_b + k_m)

        notes = []
        if const_key == 'steel' and 'steel' not in member_name:
            notes.append(
                'Wileman constants for steel members used as approximation '
                'for this member material')
        ratio = d / l
        if not (0.1 <= ratio <= 2.0):
            notes.append(
                f'd/l = {ratio:.2f} outside Wileman fit range (0.1-2.0); '
                f'member stiffness approximate')
        return {'k_bolt_N_per_m': k_b, 'k_member_N_per_m': k_m,
                'joint_constant_C': C,
                'member_constants': const_key, 'notes': notes}

    # ------------------------------------------------------------------
    # Ana analiz
    # ------------------------------------------------------------------

    def analyze(self, pressure_bar: Optional[float] = None,
                seal_diameter_mm: Optional[float] = None,
                external_axial_load_n: Optional[float] = None) -> Dict:
        """Yük durumu analizi.

        Yük iki şekilde verilebilir (ikisi birden verilirse toplanır):
          - pressure_bar + seal_diameter_mm: kapak basınç yükü
            P_total = p · π/4 · D_seal²  (D_seal: sızdırmazlık/etkin çap)
          - external_axial_load_n: doğrudan toplam eksenel yük [N]

        Dönen sözlük: cıvata başına yük, önerilen tork (±%25 ön-yük
        saçılımıyla), ayrılma marjı ve emniyet faktörleri
        (Shigley Eq. 8-24…8-30).
        """
        total_load = 0.0
        pressure_pa = None
        if pressure_bar is not None:
            if seal_diameter_mm is None:
                raise ValueError(
                    "seal_diameter_mm is required when pressure_bar is given")
            pressure_pa = float(pressure_bar) * 1e5
            if pressure_pa < 0:
                raise ValueError("pressure_bar must be >= 0")
            # --- P5B1-13 (ÖH D15 / a3): SIZDIRMAZLIK ÇAPI KAPISI ---------
            # ÖLÇÜLDÜ (``a3/once.json``; M10 / 8.8 / 8 cıvata / sıkma boyu
            # 30 mm / 60 bar): çap KARESİNE girdiği için işaret kayboluyordu
            # ve -160 mm ile +160 mm BİREBİR AYNI sonucu veriyordu
            # (120637,15789784805 N, ayrılma marjı 1,504767406275233,
            # ``separated = False``; dört alanın dördü de özdeş). 0 mm çap
            # "sonsuz ayrılma marjı" + ``separated = False`` üretiyordu, yani
            # sızdırmazlığı OLMAYAN bir kapak "açılmıyor" diye onaylanıyordu.
            # 1e9 mm (1000 km) kabul ediliyor, yük 4,7e18 N çıkıyordu. Üçü de
            # ürün yüzünde HTTP 200 idi.
            cap = _pozitif_sonlu('seal_diameter_mm', seal_diameter_mm)
            if cap > seal_diameter_max_mm():
                raise ValueError(
                    f"'seal_diameter_mm' = {seal_diameter_mm} mm is outside "
                    f"the repository's own chamber-diameter band (max "
                    f"{seal_diameter_max_mm():g} mm, from "
                    "MotorDataValidator.limits['chamber_diameter']). A "
                    "sealing diameter is a chamber-scale dimension; no new "
                    "threshold is introduced here.")
            A_cap = np.pi / 4.0 * (cap * 1e-3) ** 2
            total_load += pressure_pa * A_cap
        if external_axial_load_n is not None:
            total_load += float(external_axial_load_n)
        if total_load < 0:
            raise ValueError("Total external load must be >= 0")

        pre = self.preload()
        tq = self.torque()
        st = self.stiffness()

        F_i = pre['preload_N']
        C = st['joint_constant_C']
        A_t = self.A_t_mm2 * 1e-6
        S_p = self.props['S_p']

        P_bolt = total_load / self.bolt_count          # cıvata başına dış yük
        F_bolt = F_i + C * P_bolt                      # Shigley Eq. 8-24
        F_member = F_i - (1.0 - C) * P_bolt            # Shigley Eq. 8-25

        # --- FİZİK DENETİMİ F031 (2026-07-25): ÖN-YÜK SAÇILIMI ------------
        # Tork kontrollü sıkmada gerçekleşen ön-yük ±%25 saçılır. Eski sürüm
        # bu bandı torque() içinde RAPORLUYOR ama emniyet faktörlerine HİÇ
        # uygulamıyordu; tüm SF'ler nominal F_i ile hesaplanıyordu.
        # Standart uygulama (NASA-STD-5020A Sec. 6.2; Shigley 10th ed.
        # Sec. 8-8):
        #   - akma/proof kontrolü  MAKSİMUM ön-yükle (F_i_max = 1.25*F_i)
        #   - ayrılma (separation) kontrolü MİNİMUM ön-yükle (F_i_min = 0.75*F_i)
        # ÖLÇÜLDÜ (M10 8.8, l=30 mm, çelik üye, 8 cıvata, 60 bar x 160 mm):
        #   nominal n_proof = 1.213 -> maks. ön-yükle 0.988 (cıvata proof
        #   dayanımını AŞIYOR); nominal n_0 = 2.006 -> min. ön-yükle 1.505.
        u = self.TORQUE_PRELOAD_UNCERTAINTY
        F_i_max = (1.0 + u) * F_i
        F_i_min = (1.0 - u) * F_i
        F_bolt_max = F_i_max + C * P_bolt              # kritik: akma/proof
        F_member_min = F_i_min - (1.0 - C) * P_bolt    # kritik: ayrılma

        sigma_bolt = F_bolt / A_t
        n_proof = S_p / sigma_bolt if sigma_bolt > 0 else float('inf')
        sigma_bolt_max = F_bolt_max / A_t
        n_proof_min = (S_p / sigma_bolt_max if sigma_bolt_max > 0
                       else float('inf'))
        if C * P_bolt > 0:
            n_overload = (S_p * A_t - F_i) / (C * P_bolt)   # Eq. 8-29
            # Aşırı-yük faktörü de maksimum ön-yükte en düşüktür; ön-yük
            # zaten proof yükünü aşıyorsa faktör negatife düşer -> 0'da kırp.
            n_overload_min = max((S_p * A_t - F_i_max) / (C * P_bolt), 0.0)
        else:
            n_overload = float('inf')
            n_overload_min = float('inf') if S_p * A_t > F_i_max else 0.0
        if P_bolt * (1.0 - C) > 0:
            n_separation = F_i / (P_bolt * (1.0 - C))       # Eq. 8-30
            n_separation_min = F_i_min / (P_bolt * (1.0 - C))
        else:
            n_separation = float('inf')
            n_separation_min = float('inf')
        # Ayrılma kararı MİNİMUM ön-yükte verilir (konservatif; F031).
        separated = bool(F_member_min <= 0.0)
        separated_nominal = bool(F_member <= 0.0)

        # --- P5B1-14 (ÖH D15 / a3): ÜYE EZİLMESİ / YATAK GERİLMESİ -------
        # ÖLÇÜLDÜ (``a3/once.json``; M24 / 12.9 / 8 cıvata / 60 bar x 160 mm):
        # magnezyum üyede (akma 220 MPa) modül 330,4 kN cıvata yükü ve
        # 1232,676 N·m tork ÖNERİYOR, ama çıktının hiçbir yerinde
        # ``bearing``/``crush`` geçen TEK bir alan yok (düz anahtar taraması:
        # 0 eşleşme) ve ``assumptions`` listesinde de beyan yok. Yani
        # modelin kapsamadığı bir yetmezlik modu vardı ve o modun
        # YÖNETTİĞİ bir malzemede tam bir tork reçetesi yayımlanıyordu.
        # Onarım BEYAN DEĞİL MODELDİR: yatak gerilmesi gerçekten hesaplanır.
        #
        #   A_yatak = pi/4 (d_w^2 - d_h^2)    [ISO 4014 d_w, ISO 273 delik]
        #   sigma_yatak = F_civata_max / A_yatak
        #   SF = uye_akma / sigma_yatak       [VDI 2230 Blatt 1 §5.5.4]
        d_w = BOLT_BEARING_FACE_DIAMETER_MM.get(self.size)
        d_h = BOLT_CLEARANCE_HOLE_DIAMETER_MM.get(self.size)
        member_yield = self._member.get('yield_strength')
        if d_w and d_h and d_w > d_h and member_yield:
            A_bearing = np.pi / 4.0 * ((d_w * 1e-3) ** 2 - (d_h * 1e-3) ** 2)
            sigma_bearing = F_bolt_max / A_bearing
            n_bearing = float(member_yield) / sigma_bearing
            bearing = {
                'bearing_face_diameter_mm': d_w,
                'clearance_hole_diameter_mm': d_h,
                'bearing_area_mm2': A_bearing * 1e6,
                'bearing_stress_MPa': sigma_bearing / 1e6,
                'member_yield_strength_MPa': float(member_yield) / 1e6,
                'bearing_safety_factor': n_bearing,
                'member_crushing': bool(n_bearing < 1.0),
                'basis': (
                    'sigma_bearing = bolt load at MAXIMUM preload / the '
                    'annulus between the ISO 4014 bearing face (d_w) and the '
                    'ISO 273 medium clearance hole (d_h); compared with the '
                    'clamped member yield strength (VDI 2230 Blatt 1 '
                    'Sec. 5.5.4). A washer or a larger bearing face raises '
                    'this factor; this model assumes NO washer.'),
            }
        else:
            bearing = {
                'bearing_face_diameter_mm': d_w,
                'clearance_hole_diameter_mm': d_h,
                'bearing_area_mm2': None,
                'bearing_stress_MPa': None,
                'member_yield_strength_MPa': (
                    None if not member_yield else float(member_yield) / 1e6),
                'bearing_safety_factor': None,
                'member_crushing': None,
                'basis': (
                    'NOT EVALUATED: no ISO 4014 bearing-face / ISO 273 hole '
                    'entry or no member yield strength for this combination, '
                    'so member crushing was not checked. This is not a '
                    'statement that the member does not crush.'),
            }

        warnings = list(st['notes'])
        if bearing['member_crushing']:
            warnings.append(
                'MEMBER CRUSHING: bearing stress under the bolt head '
                f'({bearing["bearing_stress_MPa"]:.1f} MPa at maximum '
                f'preload) exceeds the clamped member yield strength '
                f'({bearing["member_yield_strength_MPa"]:.1f} MPa, '
                f'{self.member_material}). The recommended torque cannot be '
                'applied as-is: embed a washer, enlarge the bearing face, '
                'or reduce preload. The preload will also relax as the '
                'member embeds, which invalidates the separation margin '
                'computed above.')
        elif (bearing['bearing_safety_factor'] is not None
                and bearing['bearing_safety_factor'] < 1.5):
            warnings.append(
                f'Bearing safety factor {bearing["bearing_safety_factor"]:.2f} '
                '< 1.5 against member yield: local embedding is likely and '
                'will relax the preload')
        elif bearing['bearing_safety_factor'] is None:
            warnings.append(
                'Member bearing/crushing was NOT evaluated for this bolt '
                'size or member material — see bearing.basis')
        if self.props['stainless'] and self.d_mm > 20.0:
            warnings.append(
                'A2-70 property class is commonly limited to <= M20 '
                '(cold-worked austenitic, ISO 3506-1); verify supplier '
                'certificate for larger sizes')
        if separated or n_separation_min < SEPARATION_SF_ACCEPTANCE_LIMIT:
            warnings.append(
                'JOINT SEPARATION: external load exceeds preload capacity at '
                f'minimum preload ({(1.0 - u) * 100:.0f}% of nominal) — '
                'increase bolt count/size or preload')
        elif n_separation_min < 1.5:
            warnings.append(
                f'Separation factor {n_separation_min:.2f} < 1.5 at minimum '
                f'preload ({(1.0 - u) * 100:.0f}% of nominal) — low margin '
                f'against joint opening')
        if n_proof_min < PROOF_SF_ACCEPTANCE_LIMIT:
            warnings.append(
                f'Bolt stress exceeds proof strength at maximum preload '
                f'({(1.0 + u) * 100:.0f}% of nominal, torque-control scatter, '
                f'NASA-STD-5020A Sec. 6.2): proof SF = {n_proof_min:.3f} — '
                'increase bolt size/class or use a preload-indicating method')
        if n_overload_min < 1.0:
            warnings.append(
                'Bolt exceeds proof strength under external load at maximum '
                'preload — increase bolt size/class')

        return {
            'bolt': {
                'size': self.size,
                'property_class': self.property_class,
                'count': self.bolt_count,
                'nominal_diameter_mm': self.d_mm,
                'stress_area_mm2': self.A_t_mm2,
                'proof_strength_MPa': S_p / 1e6,
                'yield_strength_MPa': self.props['S_y'] / 1e6,
                'ultimate_strength_MPa': self.props['S_u'] / 1e6,
                'strength_source': self.props['source'],
            },
            'preload': {
                'proof_load_N': pre['proof_load_N'],
                'preload_N': F_i,
                # F031: tork saçılımı bandı (SF'lerde fiilen kullanılan uçlar)
                'preload_min_N': F_i_min,
                'preload_max_N': F_i_max,
                'preload_scatter_fraction': u,
                'preload_fraction_of_proof': pre['preload_fraction'],
                'basis': ('reusable connection, F_i = 0.75*F_p'
                          if self.reusable else
                          'permanent connection, F_i = 0.90*F_p')
                         + ' (Shigley 10th ed. Sec. 8-7)',
            },
            'torque': tq,
            'stiffness': {
                'k_bolt_N_per_m': st['k_bolt_N_per_m'],
                'k_member_N_per_m': st['k_member_N_per_m'],
                'joint_constant_C': C,
                'member_material': self.member_material,
                'model': ('k_b = A_t*E_b/l (fully threaded, simple); '
                          'k_m = Wileman exponential fit '
                          '(Shigley Eq. 8-23, Table 8-8)'),
            },
            'loads': {
                'pressure_bar': (pressure_pa / 1e5
                                 if pressure_pa is not None else None),
                'total_external_load_N': total_load,
                'external_load_per_bolt_N': P_bolt,
                'bolt_total_load_N': F_bolt,
                'member_clamp_load_N': F_member,
                # F031: saçılım uçlarındaki kritik yükler
                'bolt_total_load_max_preload_N': F_bolt_max,
                'member_clamp_load_min_preload_N': F_member_min,
            },
            'safety_factors': {
                # Nominal ön-yükle (geriye dönük alanlar):
                'proof_SF': n_proof,               # S_p*A_t / F_bolt (Eq. 8-28)
                'overload_factor_nL': n_overload,  # Eq. 8-29
                'separation_factor_n0': n_separation,  # Eq. 8-30
                # YÖNETEN değerler (F031, NASA-STD-5020A Sec. 6.2):
                # proof/akma -> maksimum ön-yük, ayrılma -> minimum ön-yük.
                'proof_SF_min': n_proof_min,
                'overload_factor_nL_min': n_overload_min,
                'separation_factor_n0_min': n_separation_min,
                'governing_basis': (
                    'proof/yield evaluated at maximum preload '
                    f'(+{u * 100:.0f}%), separation at minimum preload '
                    f'(-{u * 100:.0f}%) per NASA-STD-5020A Sec. 6.2 / '
                    'Shigley Sec. 8-8'),
            },
            'separation': {
                # Karar minimum ön-yükte verilir (konservatif, F031).
                'separated': separated,
                'separated_nominal_preload': separated_nominal,
                'separation_load_per_bolt_N': (
                    F_i_min / (1.0 - C) if C < 1.0 else float('inf')),
                'separation_load_per_bolt_nominal_N': (
                    F_i / (1.0 - C) if C < 1.0 else float('inf')),
                'margin': n_separation_min,
                'margin_nominal': n_separation,
            },
            # P5B1-14: üye ezilmesi artık MODELLENİR (beyan değil, hesap).
            'bearing': bearing,
            'warnings': warnings,
            'assumptions': [
                'Axial, concentric loading; no prying action',
                'Fully threaded bolt stiffness k_b = A_t*E_b/l (approximate)',
                'Member bearing (crushing) is checked WITHOUT a washer: the '
                'bearing annulus is the ISO 4014 head face against the '
                'ISO 273 medium clearance hole. A hardened washer enlarges '
                'that annulus and raises bearing.bearing_safety_factor',
                'No gasket (metal-to-metal or o-ring face seal joint); '
                'a soft gasket invalidates the Wileman member stiffness',
                'Preload from torque control scatters about +/-25% '
                '(Shigley Sec. 8-8); proof/yield safety is evaluated at the '
                'upper bound and separation at the lower bound '
                '(NASA-STD-5020A Sec. 6.2)',
            ],
            'source': ('Shigley\'s Mechanical Engineering Design 10th ed. '
                       'Ch. 8; ISO 898-1:2013; ISO 3506-1; Wileman et al. '
                       '(1991) J. Mech. Design 113'),
        }


def analyze_bolted_joint(pressure_bar: float, seal_diameter_mm: float,
                         bolt_count: int, size: str = 'M8',
                         property_class: str = '8.8',
                         grip_length_mm: float = 20.0,
                         member_material: Optional[str] = None,
                         lubricated: bool = False,
                         reusable: bool = True,
                         external_axial_load_n: Optional[float] = None) -> Dict:
    """Tek çağrılık kolaylık sarmalayıcısı (gelecekteki endpoint için).

    BoltedJointAnalyzer kurar ve analyze() sonucunu döndürür.
    """
    analyzer = BoltedJointAnalyzer(
        size=size, property_class=property_class, bolt_count=bolt_count,
        grip_length_mm=grip_length_mm, member_material=member_material,
        lubricated=lubricated, reusable=reusable)
    return analyzer.analyze(pressure_bar=pressure_bar,
                            seal_diameter_mm=seal_diameter_mm,
                            external_axial_load_n=external_axial_load_n)
