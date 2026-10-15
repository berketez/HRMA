"""
Structural Analysis Module
Wall thickness calculation and safety factor analysis for hybrid rocket motors
"""

import numpy as np
import json
from typing import Dict, List, Tuple, Optional

from hrma.constants import STEFAN_BOLTZMANN, P_SEA_LEVEL_PA
from hrma.utils.input_guard import is_json_number
from hrma.data.materials_db import build_materials_view
# Cıvata mukavemet sınıfı tablosu (ISO 898-1:2013 Table 3) — depodaki TEK
# kaynak. Aynı tablo /api/bolted-joint ucunu da besler; motor sonucundaki
# cıvata bloğu artık ondan habersiz değil (v2.6.26).
from hrma.analysis.bolted_joint import (PROOF_SF_ACCEPTANCE_LIMIT,
                                        _bolt_class_props)

# Kullanıcı tasarım emniyet katsayısı vermediğinde cıvata boyutlandırmasında
# kullanılan BEYAN EDİLEN varsayılan (literatür kaynağı yoktur; eski
# sürümdeki 4.0 davranışı korunur ki girdisiz koşularda sonuç değişmesin).
_BOLT_SAFETY_FACTOR_DEFAULT = 4.0

# Cidar sicakligi bilinmedigi durumda kullanilan radyasyon-denge tahmini:
# sogutmasiz gaz-tarafi cidar, malzemenin kisa-sureli servis sinirinin bu
# kadarina kadar isinir varsayilir (bkz. _estimate_wall_delta_T). Gercek
# deger her zaman isi transferi modulunden alinmalidir.
WALL_TEMP_SERVICE_FRACTION = 0.9

# İmalat/korozyon payı: boyutlandırma (size) modunda kod-minimum kalınlığa
# uygulanan pay. BU BİR EMNİYET FAKTÖRÜ DEĞİLDİR — toleranslı sac/boru
# temini, tornalama payı ve korozyon payı için ayrılmış malzeme kalınlığıdır
# (ASME BPVC VIII-1 UG-25 korozyon payı deseni; sayısal değer kod
# zorunluluğu değil, BEYAN EDİLEN tasarım kabulüdür — kaynak yok).
# F003 (2026-07-25): eskiden 1.2 çarpanı fonksiyon gövdesine gömülüydü ve
# raporlanan emniyet faktörünü doğrudan şişiriyordu; artık ayrı isimli sabit
# olarak çıktıda beyan edilir.
MANUFACTURING_ALLOWANCE_FACTOR = 1.2

#: İnce-cidar (membran) varsayımının geçerlilik sınırı, t/r. Bu değerin
#: ÜSTÜNDE gerilme Lame kalın-cidar tepe değerinden hesaplanır
#: (Shigley "Mechanical Engineering Design"; Roark's Formulas Ch. 13).
#: ÖH D15 / P5B1-08: sayı iki yerde (boyutlandırma ve doğrulama) çıplak
#: 0.1 olarak yazılıydı; tek kaynağa alındı ki boyutlandırma ile
#: değerlendirme AYNI rejim eşiğini kullansın.
THIN_WALL_T_OVER_R_LIMIT = 0.1

# ---------------------------------------------------------------------------
# V3 yapi-sf (7 Eki 2026, §28-21) — BOYUTLANDIRMA ISIL YÜKÜ DE TAŞIR.
#
# ÖLÇÜLDÜ (main 393960ce, örnek "Example Hybrid N2O-HTPB 3kN"): cidar
# 23,08 mm ``sizing_feasible = True`` ile "SF 4 hedefiyle boyutlandırıldı"
# olarak yayımlanıyor, aynı cidarda yayımlanan ``safety_factor_total``
# 0,8267 idi. Boyutlandırma yalnız BASINÇ hoop gerilmesini hedefe
# oturtuyordu (14,375 MPa → SF 4,80), değerlendirme ise üstüne ısıl hoop
# gerilmesini (69,09 MPa) ekliyordu. "Boyutlandırılmış cidar kendi hedefini
# aynı modelde tutturur" sözleşmesi bozuktu.
#
# Düzeltme: boyutlandırma DEĞERLENDİRMENİN KULLANDIĞI toplam hoop modelini
# (basınç: ince cidar / Lame tepe, artı ısıl) çözer. Isıl gradyan cidar
# kalınlığıyla büyür: sabit ısı akısında iletim düşüşü ΔT = q·t/k
# (Sutton & Biblarz 9. baskı Denk. (8–13), s. 311: Q/A = −κ·dT/dL ≈
# −κ·ΔT/t_w — yerel metin kitap-metin/sutton9_sayfali.txt satır 14169,
# sayfa başlığı satır 14153; Incropera & DeWitt düzlem duvar R = t/k,
# sayfa doğrulanmadı). Gradyanın
# HANGİ cidarda hesaplandığı biliniyorsa (referans kalınlık) boyutlandırma
# ΔT'yi o oranla ölçekler; bilinmiyorsa ΔT verildiği değerde TUTULUR ve bu
# ADIYLA beyan edilir. Hedef hiçbir kalınlıkta tutmuyorsa
# ``sizing_feasible = False`` ve gerekçe (mevcut fail-closed desen).
#
#: Toplam hoop boyutlandırmasında kalınlık taraması: t/r log aralığı ve
#: nokta sayısı. Sayısal çözüm ayarıdır (fizik sabiti değildir); tarama,
#: hedefi sağlayan İLK (en ince) kalınlığı bulur, ikiye bölme onu inceltir.
SIZING_SCAN_T_OVER_R_MIN = 1e-5
SIZING_SCAN_T_OVER_R_MAX = 1e2
SIZING_SCAN_POINTS = 4001
SIZING_BISECTION_ITERS = 100
#: Isıl referans cidarı ile değerlendirilen cidarın "aynı cidar" sayıldığı
#: bağıl fark: mm ⟷ m gidiş-dönüşünün kayan nokta artığıdır (ölçekleme
#: katsayısı tam 1,0 alınır, sayı biti oynamaz).
THERMAL_REFERENCE_SAME_WALL_REL_TOL = 1e-12
#: Gaz sıcaklığından TAHMİN yolunda (``_estimate_wall_delta_T`` yol 2)
#: çağıran ``wall_thickness`` vermediğinde kullanılan cidar [m]. Tek tanım:
#: hem tahmin hem de o tahminin referans kalınlığı buradan okunur.
ESTIMATE_WALL_THICKNESS_DEFAULT_M = 0.005

# ASME BPVC VIII-2 Part 5.2.2 / Section III NB-3222.2 gerilme sınıflandırması:
#   birincil membran (P)      -> sınır Sm
#   birincil+ikincil (P+Q)    -> sınır 3*Sm (shakedown / plastik uyum)
# Sm, ASME Section II-D (1999+) kriteriyle min(Su/3, Sy/1.5) alınır.
ASME_SM_UTS_DIVISOR = 3.0
ASME_SM_YIELD_DIVISOR = 1.5
ASME_SHAKEDOWN_MULTIPLIER = 3.0

# ---------------------------------------------------------------------------
# Yapısal hüküm sözlüğü — TEK tanım noktası (v2.6.27, F4-2).
# Hükmü ÜRETEN yer burasıdır, dolayısıyla sözcükler de burada tanımlanır.
# ``ONAY`` sayılan hükümler kazanılmamışsa ``NOT_EVALUATED``'e çekilir;
# 'MARGINAL' / 'UNSAFE' bir TEHLİKE BİLDİRİMİDİR ve asla susturulmaz.
# ---------------------------------------------------------------------------
#: Kazanılmamışsa geri çekilen (onay niteliğindeki) hükümler.
STRUCTURAL_APPROVAL_VERDICTS = ('SAFE', 'ACCEPTABLE')
#: Onay geri çekildiğinde yazılan tavan hüküm.
STRUCTURAL_VERDICT_NOT_EVALUATED = 'NOT_EVALUATED'

# ---------------------------------------------------------------------------
# V3 yapi-sf 2. tur (12 Eki 2026) — MODEL GEÇERLİLİK SINIRI
# (karar §28-24, Astra danışmalı: v3.0'da seçenek (C)).
#
# ÖLÇÜLDÜ (örnek "Example Hybrid N2O-HTPB 3kN", dal fd198efe): kamara cidarı
# ısı modülünün ÇIPLAK CİDAR, KARARLI HÂL dengesinde 3368,5 K (iç) /
# 3347,97 K (yöneten senaryonun düşürme sıcaklığı) değerlendiriliyor;
# steel_4130'un erime noktası 1705 K, düşürme eğrisinin son noktası 700 °C.
# Dayanım eğrinin son değerinde (0,15) SABİTLENİYOR; yayımlanan SF 0,8267,
# 23,08 mm cidar ve 82,6 kg kamara kütlesi bu değerlendirmeden geliyor.
#
# (C) kararı: bugünkü ısıl model KALIR (tane/astar korumalı kasa (A)
# gelistirme'de). Şartları: "ulaşılamaz" ifadesi gerçek motorun olanaksızlığı
# DEĞİL, MEVCUT MODELİN sınırı olarak açıklanır; erime noktası (ya da
# düşürme verisinin sonu) üstünde hesaplanan dayanım, SF ve kütle GEÇERLİ
# TASARIM ÇIKTISI gibi sunulmaz, model geçerlilik sınırının aşıldığı yazılır.
#
# Ölçüt TEK yerdedir: ``structural_model_validity``. İki dalın karşılaştırması
# ``_derate_strength`` içinde (``exceeds_melting_point``: T ≥ T_erime;
# ``above_curve_envelope``: T > eğrinin son noktası) zaten yapılıyor; bu
# fonksiyon her değerlendirilen senaryonun kaydını o iki bayrakla okur ve
# hükmü verir. Sonuç: OLUMLU hüküm ve SAYISAL tasarım hükmü verilmez
# (fail-closed); sayılar tanı amaçlı, açık künyeyle kalır.
#
#: Yapısal hükmün geri çekilme gerekçe kodu
#: (``safety_analysis.verdict_withheld_reasons``).
STRUCTURAL_MODEL_VALIDITY_WITHHELD_REASON = 'model_validity_limit_exceeded'
#: Geçerlilik sınırının iki dalı (``model_validity_reasons`` kodları).
MODEL_VALIDITY_REASON_MELTING = 'wall_temperature_at_or_above_melting_point'
MODEL_VALIDITY_REASON_DERATING_DATA = (
    'wall_temperature_above_derating_curve_data')
#: Geçerlilik künyesi (sabit metin; EN = TR çevirisi i18n_charts.js'te).
MODEL_VALIDITY_BASIS = (
    'TRUE means: a wall temperature used in this structural evaluation is at '
    'or above the melting point of the material, or above the last point of '
    'its strength-derating data. Above that point the strength is held at '
    'the last curve value (an upper bound, not a conservative value), and at '
    'or above melting the section has no load-carrying capacity at all. The '
    'strength, safety factors, wall thickness and masses computed from this '
    'evaluation are therefore outside the validity limit of the structural '
    'model: they are published as diagnostic numbers only, not as valid '
    'design outputs, and no acceptance and no numeric design verdict is '
    'issued. When the wall temperature comes from the heat-transfer module '
    '(wall_temperature_source = heat_transfer_module) it is a bare-wall '
    'steady-state estimate in which protection by the propellant grain, '
    'liner or insulation is not modelled, so an unreachable or failing '
    'result is a limit of the current model, not a statement that a real '
    'motor of this design is impossible.')
#: Boyutlandırma gerekçesinin BAŞINA eklenen model sınırı cümlesi (sabit).
MODEL_VALIDITY_SIZING_NOTE = (
    'MODEL LIMIT, NOT A PROPERTY OF THE REAL MOTOR: this wall is evaluated '
    'outside the validity limit of the structural model (see '
    'model_validity_limit_exceeded and model_validity_reasons), so the '
    'unreachable result stated next is a failure of the current model, not '
    'a finding that a real motor of this design is impossible; the strength, '
    'safety factors and masses behind it are diagnostic only.')
#: Geçerlilik dışı değerlendirmede hazne SF künyesinin yerine geçen metin.
MODEL_VALIDITY_SAFETY_FACTOR_BASIS = (
    'DIAGNOSTIC ONLY, NOT A VALID DESIGN OUTPUT: this safety factor was '
    'computed at a wall temperature outside the validity limit of the '
    'structural model (chamber_analysis.model_validity_limit_exceeded, '
    'model_validity_reasons). How the wall was chosen is stated in '
    'design_mode, sizing_feasible and sizing_infeasible_reason.')
#: Geçerlilik dışı değerlendirmede kütle dökümünün künyesi.
MODEL_VALIDITY_MASS_BASIS = (
    'DIAGNOSTIC ONLY, NOT A VALID DESIGN OUTPUT: the chamber wall thickness '
    'behind these masses comes from a structural evaluation outside the '
    'validity limit of the structural model '
    '(chamber_analysis.model_validity_limit_exceeded).')
#: Geçerlilik dışı değerlendirmede hüküm gerekçesi
#: (``minimum_safety_factor_verdict_basis``; sabit metin).
MODEL_VALIDITY_VERDICT_BASIS = (
    'No acceptance and no numeric design verdict is issued: the chamber was '
    'evaluated outside the validity limit of the structural model (see '
    'chamber_analysis.model_validity_limit_exceeded). The safety factors in '
    'this response are diagnostic numbers. A remaining MARGINAL or UNSAFE '
    'status is a warning from the CURRENT model and is never suppressed, but '
    'it is not a statement that a real motor of this design is impossible.')


def structural_model_validity(evaluated_deratings: Dict) -> Dict:
    """Yapısal değerlendirmenin model geçerlilik sınırı içinde olup olmadığı.

    V3 yapi-sf 2. tur (karar §28-24 (C)) — ölçütün TEK yeri.

    ``evaluated_deratings``: {senaryo_adı: ``_derate_strength`` kaydı} —
    yayımlanan cidarın değerlendirildiği HER ısıl senaryo. Bir senaryo bile
    erime noktasında/üstünde ya da düşürme verisinin son noktasının üstünde
    değerlendirildiyse sınır aşılmıştır: o senaryonun dayanımı bir üst
    sınırdır, dolayısıyla senaryolar arası en küçük SF seçimi de
    güvenilmezdir.

    Döner: ``model_validity_limit_exceeded`` (bool), ``model_validity_reasons``
    (sıralı kod listesi) ve senaryo başına ölçüm
    (``model_validity_evaluations``).
    """
    nedenler = set()
    olcumler = {}
    for ad in sorted(evaluated_deratings):
        der = evaluated_deratings[ad] or {}
        erime = bool(der.get('exceeds_melting_point'))
        veri_disi = bool(der.get('above_curve_envelope'))
        if erime:
            nedenler.add(MODEL_VALIDITY_REASON_MELTING)
        if veri_disi:
            nedenler.add(MODEL_VALIDITY_REASON_DERATING_DATA)
        egri_son_C = der.get('curve_max_temp_C')
        olcumler[ad] = {
            'wall_temperature_K': der.get('wall_temperature_K'),
            'melting_point_K': der.get('melting_point_K'),
            'derating_curve_last_point_K': (
                float(egri_son_C) + 273.15 if egri_son_C is not None
                else None),
            'at_or_above_melting_point': erime,
            'above_derating_curve_data': veri_disi,
        }
    return {
        'model_validity_limit_exceeded': bool(nedenler),
        'model_validity_reasons': sorted(nedenler),
        'model_validity_evaluations': olcumler,
    }


# ---------------------------------------------------------------------------
# V3 yapi-sf 3. tur Bölüm B (12 Eki 2026) — (C) SIVI VE KATI ÇAĞRI NOKTALARI
# (karar §28-37 Ş2-3 (a), v3.0 BLOKLAYICI).
#
# ÖLÇÜLDÜ (yeniden denetim-2; main 5131995d ve dal 4b4f4ccd'de bit-aynı,
# kanıt docs/scofield/raw/OH/V3/yapi-sf/kanit/t3_C_sivi_kati_once.json):
#   sıvı  F1 ``varyant:liquid:cooling_type=radiative``: inconel_718 cidarı
#         1800 K'de (erime 1533 K, düşürme eğrisinin sonu 1173,15 K)
#         değerlendiriliyor; akma 385 MPa, hoop_safety_factor 2,5128 ve
#         2,5 mm cidar TASARIM diye yayımlanıyordu;
#   katı  aluminum_6061, yalıtım 0, end_burner 1500 mm, 3200 K, kasa 4 mm:
#         ısı modelinin kasa sıcaklığı 1636,8 K (erime 855 K); vessel_status
#         PASS, SF 7,333 "verified" yayımlanıyordu.
# İkisi de yanlış bir güvenlik hükmüdür (temel ilke §28-33).
#
# Ölçüt İKİNCİ KEZ YAZILMAZ: çağrı noktası her cidar sıcaklığı için düşürme
# kaydını hibritle AYNI üreticiden (``StructuralAnalyzer._derate_strength``)
# alır ve AYNI ölçütten (``structural_model_validity``) geçirir. Aşağıdaki
# fonksiyon yalnız bu iki adımı birleştirir; kendi karşılaştırması YOKTUR.
# Ölçüt uygulanamıyorsa (kayıt, eğri ya da erime noktası yok; sıcaklık sonlu
# değil) sonuç "geçerli" İLAN EDİLMEZ: bayrak None + gerekçe.
#
#: Sıvı ``chamber_structure`` geçerlilik künyesi (sabit metin).
LIQUID_MODEL_VALIDITY_BASIS = (
    'TRUE means: the hot-wall temperature this chamber wall was evaluated at '
    '(wall_temperature: the cooling-type default or your maximum wall '
    'temperature input) is at or above the melting point of the chamber '
    'material, or above the last point of its strength-derating data. Above '
    'that point the derated yield strength is held at the last curve value '
    '(an upper bound, not a conservative value), and at or above melting the '
    'wall has no load-carrying capacity at all. The yield strength at wall '
    'temperature, the allowable stress, stress_margin, hoop_safety_factor '
    'and the wall thickness chosen from them are therefore outside the '
    'validity limit of the structural model: they are published as '
    'diagnostic numbers only, not as valid design outputs, and no acceptance '
    'and no numeric design verdict is issued.')
#: Geçerlilik dışı sıvı haznede ``safety_factor_basis``in yerine geçen metin.
LIQUID_MODEL_VALIDITY_SAFETY_FACTOR_BASIS = (
    'DIAGNOSTIC ONLY, NOT A VALID DESIGN OUTPUT: hoop_safety_factor, '
    'stress_margin and the wall thickness were computed at a chamber wall '
    'temperature outside the validity limit of the structural model '
    '(chamber_structure.model_validity_limit_exceeded, '
    'model_validity_reasons). safety_factor is still the design target read '
    'back (safety_factor_source); how the wall was chosen is stated in '
    'design_mode and wall_thickness_source.')
#: Katı kasa geçerlilik künyesi (``case_analysis`` ve ``pressure_safety``).
SOLID_CASE_MODEL_VALIDITY_BASIS = (
    'TRUE means: the case wall temperature computed by the heat-transfer '
    'model (see model_validity_evaluations: the end-of-burn case temperature '
    'through the insulation and liner) is at or above the melting point of '
    'the case material, or above the last point of its strength-derating '
    'data. The case stresses, safety factors and burst pressure in this '
    'response use the room-temperature strength of the case material, so at '
    'that temperature they are an upper bound, and at or above melting the '
    'case has no load-carrying capacity at all. They are therefore outside '
    'the validity limit of the structural model: published as diagnostic '
    'numbers only, not as valid design outputs, and no acceptance (no PASS) '
    'and no numeric design verdict is issued. A remaining FAIL or MARGINAL '
    'vessel status is a warning and is never suppressed.')
#: Geçerlilik dışı kasada ``case_analysis.safety_factor_basis`` metni.
SOLID_CASE_MODEL_VALIDITY_SAFETY_FACTOR_BASIS = (
    'DIAGNOSTIC ONLY, NOT A VALID DESIGN OUTPUT: this safety factor uses the '
    'room-temperature case strength while the computed case wall '
    'temperature is outside the validity limit of the structural model '
    '(case_analysis.model_validity_limit_exceeded, model_validity_reasons). '
    'How the wall was chosen is stated in design_mode and '
    'wall_thickness_source.')
#: Ölçüt uygulanamadığında (bayrak None) yazılan künye.
MODEL_VALIDITY_NOT_EVALUATED_BASIS = (
    'NOT EVALUATED: the model validity check needs the melting point and the '
    'strength-derating data of the material and a finite wall temperature; '
    'one of them is missing on this run, so nothing is claimed about the '
    'validity limit (model_validity_limit_exceeded = null) and this '
    'structural result carries no model-validity check.')


def structural_model_validity_at(mat_props, wall_temperatures_K) -> Optional[Dict]:
    """(C) ölçütünü bir motor çağrı noktasının cidar sıcaklıklarında uygular.

    V3 yapi-sf 3. tur Bölüm B (karar §28-37 Ş2-3 (a)) — sıvı
    ``chamber_structure`` ve katı ``case_analysis`` / ``pressure_safety``.

    ``mat_props``: materials_db kaydı (``derating_curve``, ``melting_point``,
    ``yield_strength``, ``ultimate_strength``).
    ``wall_temperatures_K``: {senaryo_adı: cidar sıcaklığı [K]}.

    Döner: ``structural_model_validity`` sözlüğü; ölçüt UYGULANAMIYORSA None
    (fail-closed: "geçerli" denmez, çağıran ``model_validity_publication``
    ile bayrağı None ve ``MODEL_VALIDITY_NOT_EVALUATED_BASIS`` yazar).
    """
    if not isinstance(mat_props, dict) or not mat_props.get('derating_curve'):
        return None
    for anahtar in ('melting_point', 'yield_strength', 'ultimate_strength'):
        deger = mat_props.get(anahtar)
        if isinstance(deger, bool):
            return None
        try:
            if not np.isfinite(float(deger)):
                return None
        except (TypeError, ValueError):
            return None
    if not isinstance(wall_temperatures_K, dict) or not wall_temperatures_K:
        return None
    analizor = StructuralAnalyzer()
    kayitlar = {}
    for ad, sicaklik in wall_temperatures_K.items():
        if isinstance(sicaklik, bool):
            return None
        try:
            T = float(sicaklik)
        except (TypeError, ValueError):
            return None
        if not np.isfinite(T) or T <= 0.0:
            return None
        kayitlar[ad] = analizor._derate_strength(mat_props, T)
    return structural_model_validity(kayitlar)


def model_validity_publication(gecerlilik, basis) -> Dict:
    """Çağrı noktasının yayımladığı geçerlilik alanları (sıvı ve katı ortak).

    Her zaman: ``model_validity_limit_exceeded`` (bool ya da None),
    ``model_validity_reasons``, ``model_validity_limit_exceeded_basis``;
    ölçülebildiyse ``model_validity_evaluations``. Sınır AŞILDIYSA ek olarak
    ``verdict_withheld = True`` ve ``verdict_withheld_reasons`` (hibritle
    aynı gerekçe kodu, ``STRUCTURAL_MODEL_VALIDITY_WITHHELD_REASON``).
    """
    if gecerlilik is None:
        return {'model_validity_limit_exceeded': None,
                'model_validity_reasons': [],
                'model_validity_limit_exceeded_basis':
                    MODEL_VALIDITY_NOT_EVALUATED_BASIS}
    yayim = dict(gecerlilik)
    yayim['model_validity_limit_exceeded_basis'] = basis
    if gecerlilik['model_validity_limit_exceeded']:
        yayim['verdict_withheld'] = True
        yayim['verdict_withheld_reasons'] = [
            STRUCTURAL_MODEL_VALIDITY_WITHHELD_REASON]
    return yayim


# ---------------------------------------------------------------------------
# V3 yapi-sf 7. tur (14 Eki; karar §28-44, 6. tur devir 1) — GEÇERLİLİK
# SINIRI AŞILDIYSA ANA HÜKMÜN YANINDAKİ ONAYLAR DA YAYIMLANMAZ.
#
# ÖLÇÜLDÜ (YP6 devri; dal 6afdb869): örnek hibrit ``/calculate`` yanıtında
# ``motor.structural_analysis.safety_analysis.model_validity_limit_exceeded``
# true iken ``design_target_assessment`` 'SAFE · VERY LOW' ve
# ``buckling_analysis.axial_buckling_status`` 'SAFE'. 6. tur aynı geri
# çekmeyi YALNIZ ``/analyze_structural_safety`` ucunda yapıyordu; motorun
# kendi çıktısı (ve ``/advanced`` yapısal kolu) açık kalıyordu. Kural artık
# hükmü ÜRETEN yerde, tek işlevde: ``_analyze_safety_factors``in geçerlilik
# bloğu bu işlevi çağırır. Ölçüt ikinci kez kurulmaz (bayrak o blokta
# hesaplanıyor), ONAY (``STRUCTURAL_APPROVAL_VERDICTS``) ``NOT_EVALUATED``
# tavanına çekilir, MARGINAL / UNSAFE / CRITICAL dokunulmaz (F4-2), sayılar
# tanı olarak yerinde kalır.
#
#: Geri çekilen onay yüzeyleri: (blok yolu, hüküm alanı, eş risk alanı ya
#: da None). Yol ``analyze_structure`` yanıtının köküne göredir;
#: ``safety_analysis.model_validity_approvals_withheld`` bu yolları yazar.
#: Burkulmanın dış basınç modu ve birleşik hükmü de aynı sıcaklıkta
#: değerlendirilen kabuktan çıkar (dış basınç beyan edilmişse SAFE olabilir).
MODEL_VALIDITY_APPROVAL_FIELDS = (
    ('safety_analysis.design_target_assessment', 'status', 'risk_level'),
    ('fatigue_analysis', 'fatigue_status', None),
    ('buckling_analysis', 'axial_buckling_status', None),
    ('buckling_analysis', 'external_buckling_status', None),
    ('buckling_analysis', 'buckling_status', None),
)
#: Geri çekilen hüküm alanının yanına yazılan gerekçe alanının soneki.
MODEL_VALIDITY_WITHHELD_SUFFIX = '_withheld_because'


def withhold_model_validity_approvals(blocks: Dict) -> List[str]:
    """Geçerlilik dışı değerlendirmede onay yüzeylerini geri çeker.

    ``blocks``: {``MODEL_VALIDITY_APPROVAL_FIELDS`` blok yolu: sözlük}. Yalnız
    onay (SAFE/ACCEPTABLE) olan hüküm ``NOT_EVALUATED`` olur (eş risk alanı
    da), yanına ``<alan>_withheld_because`` yazılır. Dönüş: geri çekilen
    alanların ``<blok yolu>.<alan>`` listesi (boşsa hiçbir şey değişmedi).
    Çağıran YALNIZ geçerlilik bayrağı True iken çağırır.
    """
    geri_cekilen = []
    for yol, hukum, risk in MODEL_VALIDITY_APPROVAL_FIELDS:
        blok = blocks.get(yol)
        if not (isinstance(blok, dict) and str(
                blok.get(hukum, '')).upper() in STRUCTURAL_APPROVAL_VERDICTS):
            continue
        blok[hukum] = STRUCTURAL_VERDICT_NOT_EVALUATED
        if risk is not None:
            blok[risk] = STRUCTURAL_VERDICT_NOT_EVALUATED
        blok[hukum + MODEL_VALIDITY_WITHHELD_SUFFIX] = (
            STRUCTURAL_MODEL_VALIDITY_WITHHELD_REASON)
        geri_cekilen.append(yol + '.' + hukum)
    return geri_cekilen

# ---------------------------------------------------------------------------
# ÖH D31 / P5B1-15 — BURKULMA HÜKMÜNÜN KAPSAMI ADIYLA YAZILIR.
#
# ÖLÇÜLDÜ (taban ``9d70e9ed``, ``a1/once.json`` K1; steel_4130, r = 0,5 m,
# L = 2,0 m):
#     t = 0,5 mm -> critical_external_pressure_bar = 0,000539
#     t = 1,0 mm -> 0,004315
#     t = 5,0 mm -> 0,539316
# ÜÇÜNDE DE ``buckling_status = 'SAFE'`` ve
# ``axial_buckling_safety_factor = inf`` yayımlanıyordu; dış basınç modu
# HİÇBİR uygulanan basınçla karşılaştırılmıyordu (ölçülen karşılaştırma
# alanı sayısı: 0). Yani 1 atm'lik bir dış fark bile kabuğu çökertecekken
# ürün "SAFE" basıyordu — kazanılmamış bir onay.
#
# 28 Ağustos 2026 Berke kararı (madde 4, D31 karar dosyası §2 seçenek (a)):
#   * uygulanan dış basınç ZARFI ``max(p_dis - p_ic_min, 0)`` ile kurulur;
#   * ``p_uygulanan == 0`` (ya da yük durumu hiç beyan edilmemiş) ise hüküm
#     ``not_evaluated``dır — ``SAFE`` + ``inf`` YASAK;
#   * yöneten senaryolar YER senaryolarıdır (soğuma-yoğuşma, kapalı drenaj);
#     bu yüzden yük durumu ÇAĞIRANDAN gelir, modül kendi senaryosunu
#     UYDURMAZ (ÖK-16: beyan edilmemiş zarf icat edilmez).
#
#: Burkulma modlarının ayrı ayrı ve birleşik hükmünde kullanılan tavan.
BUCKLING_VERDICT_NOT_EVALUATED = STRUCTURAL_VERDICT_NOT_EVALUATED
#: Burkulma emniyet katsayısı -> durum eşiği (v2.6.26'dan beri kodda olan
#: 1,0 / 2,0 ikilisi; yeni sayı değildir, yalnız adlandırıldı ve TEK
#: yerden hem eksenel hem dış basınç moduna uygulanır).
BUCKLING_SF_CRITICAL_BELOW = 1.0
BUCKLING_SF_MARGINAL_BELOW = 2.0
#: ``_check_buckling`` dış basınç yük durumu beyan edilmediğinde çağırana
#: önerilen YER zarfının referans basıncı (ISA deniz seviyesi, tek kaynak
#: ``hrma.constants.P_SEA_LEVEL_PA``). Modül bunu KENDİLİĞİNDEN uygulamaz;
#: yalnız künyede adıyla önerilir.
BUCKLING_GROUND_REFERENCE_PRESSURE_PA = P_SEA_LEVEL_PA

#: Emniyet katsayısı -> (durum, risk) merdiveni. TEK tanım noktası: hem
#: KAZANILMIŞ katsayının hükmü hem de tasarım HEDEFİNİN kıyas notu aynı
#: merdivenden okunur (Z4 onarımı yeni eşik icat etmez; bu üç sayı
#: v2.6.26'dan beri bu fonksiyonun gövdesindeydi, yalnız adlandırıldı).
STRUCTURAL_RISK_LADDER = (
    (2.0, 'UNSAFE', 'HIGH'),
    (3.0, 'MARGINAL', 'MEDIUM'),
    (4.0, 'ACCEPTABLE', 'LOW'),
)
#: Merdivenin üstü (en yüksek basamak).
STRUCTURAL_RISK_TOP = ('SAFE', 'VERY LOW')


def classify_safety_factor(safety_factor):
    """Emniyet katsayısını (durum, risk) çiftine çevirir.

    Sayı sonlu değilse ``(None, None)`` döner — sınıflandırılamayan bir
    girdiden hüküm ÜRETİLMEZ (fail-closed; ``None`` girdiyi ``0`` sayıp
    'UNSAFE' basmak da bir uydurmadır).
    """
    try:
        value = float(safety_factor)
    except (TypeError, ValueError):
        return None, None
    if not np.isfinite(value):
        # +inf meşrudur (yük yoksa burkulma SF'si sonsuzdur): en üst basamak.
        if value == float('inf'):
            return STRUCTURAL_RISK_TOP
        return None, None
    for esik, durum, risk in STRUCTURAL_RISK_LADDER:
        if value < esik:
            return durum, risk
    return STRUCTURAL_RISK_TOP


#: Lüle kütlesi geometri yokken kamara kütlesinin bu kesri kabul edilir.
#: KAYNAKSIZ mühendislik başparmak kuralıdır (geometri hesabı değil); yalnız
#: çağıran çizilen lülenin kütlesini veremediğinde YEDEK olarak kullanılır
#: ve ``nozzle_weight_source`` alanında adıyla beyan edilir.
NOZZLE_MASS_RULE_OF_THUMB_FRACTION = 0.3


#: Çizilen lüle kütlesinin künyesi (V3 yapi-sf 2. tur Ş6: SABİT metin —
#: sayılar künyeye gömülmez, yanıttaki kendi alanlarından okunur; böylece
#: EN = TR sözlük karşılığı kurulabilir, i18n_charts.js).
DRAWN_NOZZLE_MASS_BASIS = (
    'DRAWN SOLID (single source): the nozzle shell drawn by the CAD export - '
    'inner contour from nozzle_design.sample_nozzle_inner_contour, wall '
    'nozzle_geometry.wall_thickness added outward, density of the selected '
    'nozzle material (nozzle_material). The same number is '
    'cad_design.performance_summary.mass_breakdown.nozzle_mass and '
    'nozzle_geometry.estimated_mass. The former 30%-of-chamber rule of thumb '
    'is no longer used.')
#: Kesik koni yaklaşımının (lüle tasarımcısının kendi geometrisi) künyesi.
FRUSTUM_APPROXIMATION_MASS_BASIS = (
    "conical frustum annulus over the nozzle designer's OWN convergent cone "
    "(its own chamber radius, not this motor's chamber) and divergent "
    'section - a different geometry from the drawn nozzle, kept only for '
    'traceability')
#: Hibrit kuru kütle künyesi (çizilen lüle dökümü).
DRY_MASS_BASIS_DRAWN_NOZZLE = (
    'AUTHORITATIVE dry mass for the flight chain (.eng, trajectory, T/W): '
    'structural_analysis.weight_analysis.total_weight = chamber shell (real '
    'wall thickness x material density) + end closures + the DRAWN nozzle '
    '(same number as cad_design.performance_summary.mass_breakdown.'
    'nozzle_mass). SCOPE LIMIT: the injector is NOT included; the CAD mass '
    'breakdown total (cad_design.performance_summary.mass_breakdown.'
    'total_dry_mass) includes the injector but omits the closures, so the two '
    'totals differ by exactly those two items.')
#: Aynı künye, kamara değerlendirmesi model geçerlilik sınırı dışındayken
#: (karar §28-24 (C)): kütle tanı amaçlıdır.
DRY_MASS_BASIS_DRAWN_NOZZLE_OUTSIDE_VALIDITY = (
    DRY_MASS_BASIS_DRAWN_NOZZLE + ' DIAGNOSTIC ONLY, NOT A VALID DESIGN '
    'OUTPUT: the chamber wall thickness behind this mass comes from a '
    'structural evaluation outside the validity limit of the structural '
    'model (structural_analysis.chamber_analysis.'
    'model_validity_limit_exceeded); the flight-chain numbers derived from '
    'it carry the same limit.')


def drawn_nozzle_shell_mass_kg(points_mm, wall_m, density_kg_m3):
    """ÇİZİLEN lüle kabuğunun kütlesi [kg] — V3 yapi-sf, tek kaynak.

    ``points_mm``: ``nozzle_design.sample_nozzle_inner_contour`` iç kontur
    noktaları [(z_mm, r_mm), ...]; cidar iç kontura DIŞARI eklenir, her
    dilim halka hacmi π·((r_ort + t)² − r_ort²)·|dz| (kesik koni halkası,
    docs/BICIMSEL_ISPATLAR.md ``HRMA.frustumAnnulusVolume_eq_integral``).
    Aritmetik, CAD kütle dökümünün (``cad_visualization`` lüle dalı)
    işlem sırasının AYNISIDIR ki iki yol aynı yanıtta bit-eşit sayı versin;
    bekçi: tests/test_v3_yapi_sf.py.
    """
    volume = 0.0
    for (z0, r0), (z1, r1) in zip(points_mm[:-1], points_mm[1:]):
        dz = (z1 - z0) / 1000.0
        r_mid = (r0 + r1) / 2000.0
        volume += np.pi * ((r_mid + wall_m) ** 2 - r_mid ** 2) * abs(dz)
    return volume * density_kg_m3


def published_material_record(mat_props):
    """materials_db kaydının YANITA konan biçimi — beyanlarıyla birlikte.

    İki modül (yapısal analiz + ısı transferi) AYNI kaydı yayımlıyor. Metin
    iki yerde yazılırsa biri güncellenip diğeri eskiyor; tek kaynak burasıdır.

    Yayımlanan iki beyan:

    ``safety_factor_basis``
        Ad çakışması: ``safety_factor`` materials_db'nin bu malzeme için
        ÖNERDİĞİ tasarım katsayısıdır (çelik 4,0; inconel 3,0), kullanıcının
        girdiği tasarım emniyet katsayısı DEĞİLDİR. Değer doğru, sunum
        yanıltıcıydı: kullanıcı SF=6 girip burada 4,0 görünce "girdim yutuldu"
        diye okuyordu.

    ``derating_curve``
        v2.6.26 SABİT ÇIKTI DÜZELTMESİ. Eğri ham sözlük olarak
        (``{20: 1.00, 200: 0.92, ...}``) yayımlanıyordu; JSON'da anahtar
        metne dönüşünce yaprağın ADI sayının kendisi oluyordu
        (``derating_curve.20``). 20 °C noktası HER malzemede tam 1.0
        olduğundan bu yaprak her koşuda sabit çıkıyor, adı da hiçbir şey
        anlatmadığı için neden sabit olduğu okunamıyordu. Artık adlandırılmış
        iki dizi + gerekçe olarak yayımlanır. Hesap zinciri bu biçimi DEĞİL,
        materials_db kaydının kendisini okur (``_derate_strength``,
        ``pressure_vessel``); burada yalnız SUNUM değişir.
    """
    if not isinstance(mat_props, dict):
        return mat_props
    published = dict(
        mat_props,
        safety_factor_basis=(
            'materials_db recommended design factor for this material - NOT '
            'the design safety factor entered by the user'),
    )
    curve = mat_props.get('derating_curve')
    if isinstance(curve, dict) and curve:
        try:
            points = sorted((float(t), float(r)) for t, r in curve.items())
        except (TypeError, ValueError):
            return published
        published['derating_curve'] = {
            'temperatures_c': [p[0] for p in points],
            'yield_retention': [p[1] for p in points],
            'basis': (
                'tabulated yield-strength retention of this material versus '
                'metal temperature, read from the materials_db record '
                '(MMPDS / MIL-HDBK-5 derating pattern). temperatures_c and '
                'yield_retention are DATABASE values, not computed from this '
                'design; the first point is the room-temperature reference '
                'where the retention is 1.0 by definition, because the curve '
                'is normalised to the room-temperature yield strength. '
                'Intermediate temperatures are linearly interpolated and the '
                'ends are clamped.'),
        }
    return published


def _mk_warning(code: str, severity: str = 'info', **params) -> Dict:
    """Yapılandırılmış iki-dilli uyarı/öneri kaydı (D-track sözleşmesi).

    Backend dilsiz kalır; frontend ``TF(code, params)`` ile metni kurar.
    Şema: ``{code: 'warn.<subsystem>.<slug>', params: {...}, severity: ...}``.
    Öneri metinleri artık sabit İngilizce string DEĞİL; i18n sözlüğü koda
    göre TR/EN metni üretir. Katalog: docs/v262_specs/D_codes_analysis.md.
    """
    return {'code': code, 'params': params, 'severity': severity}


def _shigley_fatigue_strength_fraction(s_ut_pa: float) -> float:
    """Shigley Fig. 6-18 yorulma dayanımı kesri f(S_ut).

    v2.6.2 fizik denetimi, bulgu F181. Kod bu kesri SABİT 0.9 alıyordu ve
    docstring'inde bunu "S_u <= ~490 MPa için" diye kabul ediyordu, ama zarf
    hiç zorlanmıyordu: steel_4130 (730 MPa), inconel_718 ve titanyum
    alaşımlarında gerçek f ~0.77-0.82'dir.

    f'in fazla alınması Basquin çapasını (10^3 çevrimdeki gerilme) yükseltir
    ve sonlu ömrü OLDUĞUNDAN UZUN gösterir — konservatif olmayan yön.

    Shigley's Mechanical Engineering Design, 10. baskı, Fig. 6-18'den
    okunan çapa noktaları (S_ut kpsi -> f), aralarında doğrusal enterpolasyon:
        70 kpsi  (483 MPa) -> 0.90
       100 kpsi  (689 MPa) -> 0.82
       150 kpsi (1034 MPa) -> 0.79
       200 kpsi (1379 MPa) -> 0.77
    Bant dışında uçtaki değer korunur (eğri yataylaşır).
    """
    import numpy as _np
    s_mpa = float(s_ut_pa) / 1e6
    pts_mpa = [483.0, 689.0, 1034.0, 1379.0]
    pts_f = [0.90, 0.82, 0.79, 0.77]
    return float(_np.interp(s_mpa, pts_mpa, pts_f))


#: ÖH D22 / P5B1-16 — MODÜL SEVİYESİ GİRDİ KAPISI.
#:
#: ÖLÇÜLDÜ (``once.json`` P5B1-16_18; ``StructuralAnalyzer().analyze_structure``
#: doğrudan çağrıldı, uç kapısı devrede DEĞİL):
#:
#:   ``chamber_diameter = -0.1``  -> istisna YOK, ``status = None``,
#:                                   önerilen cidar **-3,139994 mm**,
#:                                   toplam ağırlık 3,4300 kg
#:   ``chamber_pressure = -40``   -> ``status = 'UNSAFE'``, minSF **0,0**,
#:                                   önerilen cidar -3,139994 mm,
#:                                   toplam ağırlık **NaN**
#:   ``chamber_pressure = 0``     -> ham ``ZeroDivisionError``
#:                                   ("float division by zero")
#:
#: Yani modül negatif çaplı / negatif basınçlı bir motorun tam hükmünü
#: üretiyor ve NaN ağırlık yayımlıyordu. Kapı FAIL-CLOSED'dır: değer
#: GÖNDERİLMİŞ ama fiziksel değilse (sonlu değil ya da <= 0) hüküm
#: kazanılmaz, sayı uydurulmaz, alan ADIYLA reddedilir.
#:
#: KAPSAM BİLEREK DAR: alan YOKSA reddedilmez — yokluk ayrı bir kalemdir
#: (P5B1-18) ve orada BEYAN edilir. Böylece motor çözücülerinin
#: (hibrit/katı/sıvı) bugünkü çağrıları bit-aynı kalır; yalnız fiziksel
#: olmayan DEĞER reddedilir. Eşik İCAT EDİLMEZ: "> 0" bu büyüklüklerin
#: tanımıdır (çap, uzunluk, basınç), deponun kendi ``_positive_float`` /
#: ``_REGRESSION_POSITIVE_FIELDS`` ilkesiyle aynı.
STRUCTURAL_POSITIVE_INPUTS = (
    'chamber_pressure', 'chamber_diameter', 'chamber_length',
    'throat_diameter',
)

#: Her alanın kendi fiziği — tek cümle, alanın KENDİ gerekçesi.
STRUCTURAL_POSITIVE_REASONS = {
    'chamber_pressure': (
        'Chamber pressure sets every stress in this module and divides the '
        'wall sizing; a non-positive pressure has no physical meaning.'),
    'chamber_diameter': (
        'The chamber diameter is a diameter; a non-positive value would '
        'publish a negative wall thickness.'),
    'chamber_length': (
        'The chamber length is a length; it multiplies the shell mass.'),
    'throat_diameter': (
        'The throat diameter is a diameter and divides the nozzle wall '
        'sizing.'),
}

#: ÖH D22 / P5B1-18 — SESSİZ VARSAYILANLARIN KAYNAĞI TEK YERDE.
#: Sayılar ``analyze_structure``ın kendi ``motor_data.get(<ad>, <yedek>)``
#: satırlarından buraya TAŞINDI (ikinci kez yazılmadı, Doktrin 4): çağrı
#: satırları artık bu tabloyu okur ve hangi alanın varsayılandan geldiği
#: ``inputs_defaulted`` ile ADIYLA beyan edilir.
STRUCTURAL_INPUT_DEFAULTS = {
    'chamber_pressure': (20.0, 'bar'),
    'chamber_diameter': (0.1, 'm'),
    'chamber_length': (0.5, 'm'),
    'throat_diameter': (0.02, 'm'),
    'nozzle_type': ('conical', ''),
}


class NonPhysicalStructuralInput(ValueError):
    """``analyze_structure`` girdi kapısı reddi (ÖH D22 / P5B1-16).

    ``invalid_fields`` makine-okur ret kayıtlarını taşır; uç katmanı onu
    kendi 422 gövdesine olduğu gibi koyabilir.
    """

    def __init__(self, invalid_fields):
        self.invalid_fields = list(invalid_fields)
        adlar = ', '.join(sorted({k['field'] for k in self.invalid_fields}))
        super().__init__(
            'Structural analysis inputs are not physical (%s). No value was '
            'assumed and no analysis was attempted.' % adlar)


def _structural_input_gate(motor_data):
    """(gecersiz, varsayilan_kunyeleri) — kapı + varsayılan beyanı.

    Kapı YALNIZ gönderilmiş değere bakar (P5B1-16); yokluk reddedilmez,
    ``inputs_defaulted`` ile beyan edilir (P5B1-18).
    """
    gecersiz = []
    for alan in STRUCTURAL_POSITIVE_INPUTS:
        if alan not in motor_data:
            continue
        ham = motor_data.get(alan)
        if ham is None:
            continue
        # ÖH D31 / P15B2-01 (OH-D30-08 dağıtımı, satır
        # ``structural_analysis.py::_structural_input_gate``): "bu değer bir
        # JSON sayısı mı?" sorusu ARTIK MERKEZDEN sorulur
        # (``hrma.utils.input_guard.is_json_number``). Kural aynıydı
        # (``bool`` sayı değildir; yalnız ``int``/``float`` kabul) ama
        # KOPYAYDI: aynı kötü girdi modüle göre ayrışabiliyordu. Hüküm
        # BİT-AYNI kalır, tek değişen kuralın nereden okunduğudur.
        if not is_json_number(ham):
            gecersiz.append({
                'field': alan, 'reason': 'not_a_number',
                'received_type': type(ham).__name__,
                'detail': STRUCTURAL_POSITIVE_REASONS[alan],
            })
            continue
        deger = float(ham)
        if not np.isfinite(deger):
            gecersiz.append({
                'field': alan, 'reason': 'not_finite', 'value': repr(ham),
                'detail': STRUCTURAL_POSITIVE_REASONS[alan],
            })
            continue
        if deger <= 0:
            gecersiz.append({
                'field': alan, 'reason': 'not_positive', 'value': deger,
                'detail': STRUCTURAL_POSITIVE_REASONS[alan],
            })
    kunye = {}
    for alan, (yedek, birim) in STRUCTURAL_INPUT_DEFAULTS.items():
        if motor_data.get(alan) is None:
            kunye[alan] = {
                'value': yedek, 'unit': birim,
                'reason': ('not supplied by the caller; this module applied '
                           'its own documented default. The numbers below '
                           'describe THAT value, not a motor you specified.'),
            }
    return gecersiz, kunye


class StructuralAnalyzer:
    """Structural analysis for hybrid rocket motor chambers.

    DENETIM DUZELTMESI (2026-06): Onceki surum termal gerilmeyi, sicaklikla
    mukavemet derating'ini ve burkulmayi (buckling) TAMAMEN ihmal ediyordu.
    Bu, emniyet faktorunu (SF) gercegin cok ustunde gosteriyordu (3000 K cidar
    sicakliginda gercek SF < 1'e dusebilir). Asagidaki eklemeler bu tehlikeyi
    konservatif yonde duzeltir:
      1) Termal hoop gerilme (radyal sicaklik gradyani)  -> Timoshenko & Goodier,
         Boley & Weiner, Roark's Formulas for Stress & Strain 9th ed. Ch. 16.
      2) Sicakliga bagli yield/ultimate derating          -> MMPDS / MIL-HDBK-5
         Fig. 2.3.1.1.1 (AISI dusuk-alasimli celikler, kisa sureli maruziyet).
      3) Eksenel + dis-basinc burkulmasi                  -> NASA SP-8007.
      4) Ince-cidar varsayimi gecerlilik kontrolu (t/r<0.1) -> Shigley / Roark.
    """

    def __init__(self):
        # Malzeme veritabanı — MERKEZİ kaynaktan (Dalga 0, 2026-07-14).
        #
        # Eski yerel tablo hrma/data/materials_db.py'ye taşındı: mekanik +
        # termal özellikler artık TEK kayıtta (parametre tutarlılığı kuralı;
        # heat_transfer/safety modülleriyle aynı değerler). Alanlar ve
        # derating eğrileri kaynaklarıyla birlikte orada belgelidir.
        # Anahtar uyumluluğu: steel_4130 / aluminum_6061 / inconel_718 /
        # titanium_6al4v aynen korunur; ek malzemeler (ss_304, ss_316,
        # copper, cucrzr, graphite, ablative, steel) de seçilebilir.
        self.materials = build_materials_view()

    # ------------------------------------------------------------------
    # YENI YARDIMCI FONKSIYONLAR (DENETIM DUZELTMESI 2026-06)
    # ------------------------------------------------------------------
    def _derate_strength(self, mat_props: Dict, wall_temp_K: float) -> Dict:
        """Sicakliga bagli mukavemet derating'i.

        Yield ve ultimate dayanim, cidar sicakligi ile DUSER. Onceki surum bunu
        ihmal ediyordu -> 3000 K alev sicakliginda celik yine oda-sicakligi
        dayanimiyla hesaplaniyordu (tehlikeli, gercek-disi).

        Kaynak: MMPDS / MIL-HDBK-5 Fig. 2.3.1.1.1 (AISI dusuk-alasimli celikler,
        kisa-sureli maruziyet); malzeme bazli derating_curve sozlugunden
        lineer interpolasyon yapilir. Egri disina dusen sicakliklarda en yakin
        ucta sabitlenir.

        ÖH Z4 (P15B1-01) — ZARF İHLALİ ARTIK SESSİZ DEĞİL.
        Eski yorum satırı üst uçtaki sabitlemeyi "konservatif" ilan
        ediyordu; DEĞİLDİR. Eğrinin son noktası çelikte 700 °C / 0,15'tir.
        Sabit tutmak, o sıcaklığın üstünde dayanımın DÜŞMEYİ BIRAKTIĞINI
        varsaymaktır; oysa akma dayanımı erime noktasında tanım gereği
        sıfırdır (çelikte 1705 K), yani eğrinin ötesindeki gerçek değer
        her zaman 0,15'in ALTINDADIR. Sabitleme bu yüzden dayanımı
        OLDUĞUNDAN YÜKSEK gösterir — tam olarak yasak yön. (Eğrinin
        SAYILARI bu kalemde değiştirilmedi: hangi malzeme için hangi
        noktaların doğru olduğu ``materials_db`` kalemidir ve literatür
        kaynağı orada durur.)
        Ölçülen sonucu: aynı hazne iki üründe farklı retention alıyor
        (hibrit ürün koşumu T_iç = 3283,9 K -> 0,150000, ısı zinciri
        koşmayan uç 300 K -> 0,996956) ve ikisinin arasındaki 6,6× fark
        hiçbir alanda beyan edilmiyordu.
        Sayı DEĞİŞTİRİLMEDİ (eğri ``materials_db``in malısıdır ve bu
        fonksiyonun kapsamı dışındadır); zarfın dışına çıkıldığı, hangi
        sıcaklıkta çıkıldığı ve sabitlemenin yönü ADIYLA yayımlanır —
        kardeş modülün alt uçta zaten yaptığı gibi
        (``pressure_vessel._derate_strength``: ``below_curve_envelope`` /
        ``curve_min_temp_C``).

        Args:
            mat_props: Malzeme ozellik sozlugu (derating_curve icermeli).
            wall_temp_K: Yapisal cidar sicakligi [K].

        Returns:
            Derating sonuclari: derate edilmis yield/ultimate, retention
            faktoru ve zarf beyanlari.
        """
        wall_temp_C = wall_temp_K - 273.15

        curve = mat_props.get('derating_curve')
        curve_min_C = curve_max_C = None
        below_envelope = above_envelope = False
        if not curve:
            # ÖH D23 / P5B1-23 — FAIL-CLOSED (doktrin 1).
            #
            # ÖLÇÜLDÜ (taban ``ef527ae``, ``once.json`` P5B1-23; eğrisiz
            # sahte malzeme kaydı, yield 400 MPa, cidar 300 K):
            #   retention = 0,5 · derated_yield = 200 000 000,0 Pa
            #   retention_basis = "strength retention interpolated from the
            #                      material derating_curve (MMPDS / MIL-HDBK-5
            #                      Fig. 2.3.1.1.1 pattern)"
            # Yani dayanım SESSİZCE yarıya iniyor ve künye, hiç var olmayan
            # bir eğriden "interpolasyon" yapıldığını SÖYLÜYORDU.
            # materials_db'deki 24/24 malzemenin eğrisi dolu olduğu için bu
            # dal ürün yolunda ÖLÜ KODDUR (aynı ölçüm: egrisiz_malzeme_
            # sayisi = 0); yalnız kendi malzeme kaydını enjekte eden bir
            # çağıran buraya düşer ve %50 kaybın nedenini göremez.
            #
            # 0,5 bir mühendislik hükmü değil, kaynağı olmayan bir
            # varsayımdır: derating eğrisi olmayan malzeme için sıcaklığa
            # bağlı dayanım hükmü KAZANILMAMIŞTIR. Sayı uydurulmaz, alan
            # ADIYLA reddedilir.
            raise ValueError(
                "material record has no 'derating_curve', so no "
                "temperature-dependent strength verdict can be earned for "
                f"a wall temperature of {wall_temp_C:.1f} C. The previous "
                "behaviour silently applied a 0.5 retention factor (a 50% "
                "strength cut with no published source) and then labelled "
                "it as interpolated from a curve that did not exist. "
                "Supply a 'derating_curve' ({temperature_C: retention}) "
                "for this material, or run at the room-temperature "
                "reference where the retention is 1.0 by definition.")
        else:
            temps = sorted(curve.keys())
            facs = [curve[t] for t in temps]
            curve_min_C, curve_max_C = float(temps[0]), float(temps[-1])
            if wall_temp_C <= temps[0]:
                retention = facs[0]
                below_envelope = wall_temp_C < temps[0]
            elif wall_temp_C >= temps[-1]:
                # Egri ustunde: son (en dusuk) faktorde SABITLENIR. Bu bir
                # EKSTRAPOLASYONDUR ve konservatif DEGILDIR (bkz. docstring);
                # asagida adiyla beyan edilir.
                retention = facs[-1]
                above_envelope = wall_temp_C > temps[-1]
            else:
                retention = float(np.interp(wall_temp_C, temps, facs))

        derated_yield = mat_props['yield_strength'] * retention
        derated_ultimate = mat_props['ultimate_strength'] * retention

        melting_K = mat_props.get('melting_point')
        try:
            exceeds_melting = bool(melting_K is not None
                                   and float(wall_temp_K) >= float(melting_K))
        except (TypeError, ValueError):
            melting_K, exceeds_melting = None, False

        return {
            'wall_temperature_C': wall_temp_C,
            'wall_temperature_K': wall_temp_K,
            'strength_retention_factor': retention,
            # --- zarf beyanlari (P15B1-01) -------------------------------
            'curve_min_temp_C': curve_min_C,
            'curve_max_temp_C': curve_max_C,
            'below_curve_envelope': below_envelope,
            'above_curve_envelope': above_envelope,
            'melting_point_K': melting_K,
            'exceeds_melting_point': exceeds_melting,
            'retention_basis': (
                'strength retention interpolated from the material '
                'derating_curve (MMPDS / MIL-HDBK-5 Fig. 2.3.1.1.1 pattern)'
                if not (below_envelope or above_envelope) else
                'EXTRAPOLATED: the wall temperature is BELOW the first point '
                f'of the derating curve ({curve_min_C} C), so '
                'room-temperature strength is used'
                if below_envelope else
                'EXTRAPOLATED AND NOT CONSERVATIVE: the wall temperature '
                f'({wall_temp_C:.1f} C) is ABOVE the last point of the '
                f'derating curve ({curve_max_C} C), so the factor is HELD at '
                f'the last value ({retention}). A real metal keeps losing '
                'strength above that point and reaches zero at melting, so '
                'the strength used here is an UPPER bound, not a '
                'conservative one'
                + (f'. The wall temperature is at or above the melting point '
                   f'of this material ({melting_K} K): the section has no '
                   'load-carrying capacity at all and every safety factor '
                   'derived from it is meaningless.'
                   if exceeds_melting else '.')),
            'derated_yield_strength': derated_yield,            # Pa
            'derated_ultimate_strength': derated_ultimate,      # Pa
            'derated_yield_strength_MPa': derated_yield / 1e6,
            'derated_ultimate_strength_MPa': derated_ultimate / 1e6,
            'room_temp_yield_MPa': mat_props['yield_strength'] / 1e6,
            'exceeds_max_service_temp': bool(
                wall_temp_K > mat_props.get('max_service_temp', float('inf'))
            )
        }

    def _thermal_hoop_stress(self, mat_props: Dict, delta_T: float) -> Dict:
        """Radyal sicaklik gradyaninin yarattigi termal hoop gerilme.

        Ince cidarli silindirde cidar boyunca lineer sicaklik gradyani (ic yuz
        sicak, dis yuz soguk; delta_T = T_ic - T_dis) icin yuzey termal
        gerilmesinin klasik buyuklugu:

            sigma_thermal = E * alpha * delta_T / (2 * (1 - nu))

        Kaynak: Timoshenko & Goodier "Theory of Elasticity" (uzun silindir,
        eksenel kisitli hal); Boley & Weiner "Theory of Thermal Stresses"
        Ch.10-11; Roark's Formulas for Stress & Strain 9th ed. Ch.16.

        DUZELTME (v2.5.2): onceki surum "konservatif olmak icin" 2 faktorunu
        dusurmuyor, yani gerilmeyi sistematik olarak 2 KAT sisiriyordu. Bu
        muhafazakarlik degil hataydi: her sicak motorun von Mises SF'si 1'in
        altina dusuyor, tasarim penceresi kayboluyordu. Klasik yuzey degeri
        geri konuldu; muhafazakarlik, gradyanin (delta_T) tahmininde ve
        sicaklik derating'inde korunur.

        delta_T <= 0 (sogutmasiz/izotermal cidar) ise termal gerilme 0 alinir.
        """
        E = mat_props['elastic_modulus']
        alpha = mat_props['thermal_expansion']
        nu = mat_props['poisson_ratio']

        dT = max(0.0, delta_T)
        sigma_thermal = E * alpha * dT / (2.0 * (1.0 - nu))

        return {
            'delta_T': dT,                          # K  (kullanilan cidar gradyani)
            'thermal_hoop_stress': sigma_thermal,   # Pa (tensile, dis yuzde)
            'thermal_hoop_stress_MPa': sigma_thermal / 1e6,
            'formula': 'sigma_th = E*alpha*dT/(2*(1-nu))  [Timoshenko/Boley-Weiner/Roark Ch.16]'
        }

    def _estimate_wall_delta_T(self, motor_data: Dict, mat_props: Dict) -> Tuple[float, float]:
        """Cidar ic/dis sicaklik degerlerini tahmin et.

        Tercih sirasi:
          1) motor_data['wall_temperature_hot'] / 'wall_temperature_cold'
             (isi transferi modulunun cidar analizinden gelen GERCEK degerler;
             hybrid/liquid/solid motor zincirleri bu anahtarlari doldurur)
          2) chamber_temperature'tan radyasyon-denge TAHMINI: sogutmasiz cidar
             ic yuzu alev sicakligina degil, isi kaybiyla dengelendigi bir
             ara sicakliga oturur.

        Returns:
            (T_inner_wall_K, T_outer_wall_K)
        """
        # 1) Dogrudan cidar sicakligi verilmisse kullan
        T_hot = motor_data.get('wall_temperature_hot')
        T_cold = motor_data.get('wall_temperature_cold')
        if T_hot is not None and T_cold is not None:
            return float(T_hot), float(T_cold)

        # 2) chamber_temperature'tan konservatif tahmin
        T_chamber = motor_data.get('chamber_temperature')
        T_ambient = motor_data.get('ambient_temperature', 300.0)
        if T_chamber is None:
            # Sicaklik bilgisi yok -> termal etki devre disi (eski davranis korunur).
            return T_ambient, T_ambient

        # DUZELTME (v2.5.2): eski tahmin ic yuzu min(T_hazne, max_service_temp)
        # aliyordu, yani cidar sicakligi bilinmeyen HER motor tam olarak
        # malzeme servis sinirinda varsayiliyordu. Bu, hem derating'i hem
        # gradyani ayni anda en kotu degerine sabitleyip her sicak motoru
        # CRITICAL yapiyordu. Kisa sureli atesleme + radyasyon/iletim kaybi
        # altinda cidar servis sinirina TAM oturmaz; servis sinirinin bir
        # miktar altinda dengelenir. Tahmin bu nedenle servis sinirinin
        # WALL_TEMP_SERVICE_FRACTION kati ile sinirlanir (yine alev
        # sicakligini asamaz). Gercek deger her zaman isi transferi
        # modulunden (secenek 1) gelmelidir.
        # ÖH ONARIMI (defter P5B1-02, YÜKSEK) — TAHMİN ALEVDEN GELİR.
        # Yukarıdaki v2.5.2 çözümü cidarı malzemenin KENDİ servis sınırına
        # bağlıyordu: T_iç = min(T_hazne, 0,9 x max_service_temp). Ölçüldü
        # (steel_4130, servis sınırı 811 K): chamber_temperature 1000 /
        # 3000 / 10000 K -> peak_wall_temperature_K ÜÇÜNDE DE 729,90 K ve
        # thermal_margin_ratio ÜÇÜNDE DE TAM 0,900000. Aynı 3000 K alevde
        # malzeme değişince tahmin de değişiyordu (aluminum_6061 429,30 K,
        # inconel_718 879,30 K) — yani sayı ALEVE değil MALZEMEYE bakıyordu.
        # Bu yolda ``exceeds_max_service_temp_peak`` TANIM GEREĞİ True
        # olamıyordu: termal UNSAFE bandı ölüydü, hüküm MARGINAL tavanında
        # kilitliydi. Bir malzemeyi kendi sınırıyla sınamak totolojidir.
        #
        # DOKTRİN (ÖH karar 10+11, ASİMETRİK T_aw): kurtarma/alev sıcaklığı
        # TERMODİNAMİK ÜST SINIRDIR — soğutmasız bir cidar ondan sıcak
        # olamaz. Soğutma verisi YOKKEN (bu yol) yayımlanabilecek dürüst
        # tek sayı o üst sınırdır:
        #   * üst sınır <= servis sınırı -> SAFE KAZANILIR (üst sınır bile
        #     altındaysa cidar güvenlidir; soğutma verisi gerekmez),
        #   * üst sınır >  servis sınırı -> hüküm kazanılmaz ve sayı
        #     fail-closed yönde (sıcak) yayımlanır; gerçekleşmiş sıcaklık
        #     DEĞİLDİR, künyesi bunu söyler.
        # Gerçek değer her zaman ısı transferi modülünden (seçenek 1)
        # gelmelidir; bu dal yalnız o veri yokken çalışır.
        #
        # UYGULAMA — İKİ EKSEN, İKİ AD (tek sayıyı iki anlamda kullanmak
        # P4B1-14'ün ta kendisidir; o yüzden AYRIŞTIRILDI):
        #   * GRADYAN ekseni (aşağıdaki T_inner/T_outer, termal gerilme):
        #     soğutmasız ince cidar tahmini KORUNUR. Bu bir kabuldür ve
        #     gerilme hesabının girdisidir; alevi doğrudan kullanmak,
        #     bilinmeyen bir gradyanı "ölçülmüş" gibi yayımlardı.
        #   * SERVİS SINIRI ekseni: hüküm artık bu tahminden DEĞİL,
        #     ``_wall_temperature_bound_K``in verdiği ÜST SINIRdan okunur
        #     (bkz. ``_analyze_safety_factors``). Kusurun kalbi oradaydı:
        #     malzemeyi kendi sınırıyla sınamak.
        T_cap = mat_props.get('max_service_temp', float(T_chamber)) * WALL_TEMP_SERVICE_FRACTION
        T_inner = min(float(T_chamber), T_cap)

        # DUZELTME (v2.5.2, ikinci tur): dis yuzu DOGRUDAN ortam sicakligina
        # esitlemek fiziksel degildi. Cidar sicakligi bilinmeyen motor
        # "sogutmasiz" kabul edilmelidir; sogutmasiz ince metal cidarda
        # kesit boyunca gradyan KUCUKTUR, cunku iletim direnci (t/k) dis
        # yuzey kayip direncinden kat kat kucuktur. Dis yuzey enerji dengesi:
        #
        #   k/t * (T_ic - T_dis) = h_konv * (T_dis - T_ortam)
        #                          + eps * sigma * (T_dis^4 - T_ortam^4)
        #
        # 5 mm celikte (k/t = 9000 W/m^2K) bu denge ~2 K'lik bir gradyan
        # verir; eski varsayim 430 K veriyordu, yani gercek olmayan bir
        # rejeneratif sogutma (3.9 MW/m^2 atim) varsayiyordu. Sonuc: cidar
        # sicakligi verilmeyen HER motor sahte CRITICAL cikiyordu.
        # Gercek sogutmali degerler yol 1'den (isi transferi modulu) gelir.
        t_wall = self._estimate_reference_thickness_m(motor_data)
        k_wall = float(mat_props.get('thermal_conductivity', 45.0) or 45.0)
        emissivity = float(mat_props.get('emissivity', 0.3) or 0.3)
        h_conv_out = 10.0        # W/m^2K, dogal konveksiyon (durgun hava)
        # v2.6.27: merkezî tanımdan (hrma/constants.py) — yerel kopya kalktı.
        SIGMA_SB = STEFAN_BOLTZMANN

        T_amb = float(T_ambient)
        T_outer = T_inner        # baslangic: izotermal
        for _ in range(60):      # sabit nokta iterasyonu (monoton, hizli yakinsar)
            q_loss = (h_conv_out * (T_outer - T_amb)
                      + emissivity * SIGMA_SB * (T_outer ** 4 - T_amb ** 4))
            T_new = T_inner - q_loss * t_wall / k_wall
            T_new = min(T_inner, max(T_amb, T_new))
            if abs(T_new - T_outer) < 1e-3:
                T_outer = T_new
                break
            T_outer = 0.5 * (T_outer + T_new)   # gevsetme (radyasyon T^4 icin)

        return T_inner, T_outer

    @staticmethod
    def _wall_temperature_source(motor_data: Dict) -> str:
        """Cidar sicakliklarinin NEREDEN geldigini adlandirir (v2.6.27, A3).

        ``_estimate_wall_delta_T`` uc farkli yoldan cikabiliyor ama ciktisi
        her uc durumda da iki sayidan ibaret; disaridan bakan hicbir katman
        "bu sicaklik hesaplandi mi yoksa termal model kapali miydi?" sorusunu
        cevaplayamiyordu. Olculdu: sicaklik girdisi verilmeyen bir istekte
        ic ve dis cidar 300,0 K donuyor ve bu deger yanitta HESAPLANMIS bir
        tepe cidar sicakligi gibi duruyordu (bkz. app.py
        ``_withhold_unearned_structural_verdict`` B3 gerekcesi).

        Doner:
            ``'heat_transfer_module'``  — cagiran gercek cidar sicakliklarini
                (wall_temperature_hot/cold) verdi; termal yol KOSTU.
            ``'chamber_temperature_estimate'`` — yalniz gaz sicakligi verildi;
                cidar radyasyon-denge TAHMINI ile bulundu.
            ``'not_evaluated'`` — hicbir sicaklik girdisi yok; termal etki
                kapali, iki cidar da ortam sicakligina esit.
        """
        if (motor_data.get('wall_temperature_hot') is not None
                and motor_data.get('wall_temperature_cold') is not None):
            return 'heat_transfer_module'
        if motor_data.get('chamber_temperature') is not None:
            return 'chamber_temperature_estimate'
        return 'not_evaluated'

    def _check_buckling(self, pressure: float, radius: float, thickness: float,
                        length: float, mat_props: Dict,
                        axial_compression_force: float = 0.0,
                        external_pressure: Optional[float] = None,
                        internal_pressure_min: Optional[float] = None) -> Dict:
        """Ince-cidarli silindir burkulma kontrolu (NASA SP-8007).

        Iki mod kontrol edilir:
          A) Eksenel basma burkulmasi (itki/montaj/ucus basma yuku):
             sigma_cl = E / sqrt(3(1-nu^2)) * (t/r)      [klasik]
             sigma_cr = gamma * sigma_cl                  [tasarim]
             gamma = 1 - 0.901*(1 - exp(-phi)),  phi = (1/16)*sqrt(r/t)
          B) Dis basinc burkulmasi (uzun silindir, klasik elastik):
             p_cl = E/(4(1-nu^2)) * (t/r)^3

        Kaynak: NASA SP-8007 "Buckling of Thin-Walled Circular Cylinders"
        (revised 1968), NTRS 19680026348.

        DENETIM DUZELTMESI (#203): Eski surum, burkulma emniyetini kapali-uc
        IC BASINC boylamsal gerilmesiyle (p*r/2t) karsilastiriyordu. Bu gerilme
        CEKMEdir — kabuk burkulmaz, aksine stabilize olur (SP-8007 basincli
        silindirlerde knockdown'in IYILESTIGINI soyler). Dogru burkulma yuku
        GERCEK eksenel BASMAdir (itki, montaj on-yuku, ucus ataleti):
            sigma_basma = F / (2*pi*r*t)
            net = max(sigma_basma - p*r/(2t), 0)   [basinc cekmesi kredisi]
        Basinc-stabilizasyon gamma iyilesmesi muhafazakarlik icin ALINMAZ;
        yalnizca net-kesit gerilme kredisi kullanilir. Basma yuku yoksa
        (F=0) net=0 -> eksenel burkulma bu yuk durumunda olusmaz, SF=inf.

        FIZIK DENETIMI F075 (2026-07-25) — ZARF DUZELTMESI (formuller dogruydu).
        Denklemler NASA SP-8007 ile birebir uyusuyor; sorun YUK DURUMU
        zarfindaydi:
          (a) IKI YUK DURUMU degerlendirilir. Burkulma gercekte BASINCSIZ
              durumda (nakliye, montaj on-yuku, ates oncesi/kapanis, ucus
              atalet yuku) kritiktir; eski surum yalnizca basincli duruma
              bakiyordu. Artik hem basincli hem basincsiz durum hesaplanir ve
              YONETEN (dusuk SF'li) olan raporlanir. Basincsiz durumda cekme
              kredisi yoktur, dolayisiyla o durum daima yonetir; basincli
              durum tani amaciyla ayrica raporlanir.
          (b) STABILIZE KREDI ALT SINIR BASINCTAN alinir. Eski surum krediyi
              tasarim basinci (1.5*Pc) ile hesapliyordu; kredi CIKARILDIGI
              icin daha yuksek tasarim basinci NET BASMAYI AZALTIYOR, yani
              konservatif olmuyordu. Cagiran artik MEOP'u (Pc) gecer.
          (c) 'length' argumani artik cikti tanisinda kullanilir: dis basinc
              formulu UZUN silindir varsayimidir (uzunluktan bagimsiz), kisa
              silindirlerde gercek kritik basinc daha yuksektir -> bu form
              konservatiftir. L/r orani raporlanarak varsayim BEYAN edilir.
        Uretim yolu notu: cagirici zincirin 'thrust' anahtarini gecirmesi
        gerekir; gecirilmezse F=0 ve eksenel burkulma her zaman SAFE cikar.

        ÖH D31 / P5B1-15 — DIS BASINC MODU ARTIK BIR HUKUM URETIR.
        Eski surumde (B) modunun kritik basinci yayimlaniyor ama HICBIR
        uygulanan basincla karsilastirilmiyordu; genel ``buckling_status``
        ise yalniz (A) eksenel modundan geliyor ve kosulsuz 'SAFE'
        diyebiliyordu. Olculdu (a1/once.json K1): t = 0,5 / 1,0 / 5,0 mm
        icin kritik dis basinc 0,000539 / 0,004315 / 0,539316 bar
        (ucu de 1 atm ALTINDA) iken ucunde de 'SAFE'.

        Yeni sozlesme (28 Agustos 2026 Berke karari):
          * ``external_pressure``  : uygulanan DIS basinc [Pa] (ortam).
          * ``internal_pressure_min``: ayni yuk durumundaki EN DUSUK ic
            basinc [Pa]; verilmezse 0 (tam bosluk) alinir, cunku 0 bu
            zarfin ust sinir (en konservatif) halidir.
          * Zarf: ``p_uygulanan = max(p_dis - p_ic_min, 0)``.
          * ``external_pressure`` beyan edilmediyse ya da zarf 0 cikarsa
            dis basinc hukmu ``NOT_EVALUATED``dir; emniyet katsayisi
            ``inf`` DEGIL ``None`` olur (kazanilmamis onay yayimlanmaz).
          * ``axial_buckling_status`` eksenel modun KENDI adiyla yazilmis
            hukmudur; ``buckling_status`` ikisinin BIRLESIK hukmudur ve
            bir mod degerlendirilmediyse 'SAFE' DIYEMEZ.
        Modul kendi yuk durumunu UYDURMAZ: yer senaryosu referansi
        ``BUCKLING_GROUND_REFERENCE_PRESSURE_PA`` adiyla kunyede ONERILIR,
        kendiliginden uygulanmaz.
        """
        E = mat_props['elastic_modulus']
        nu = mat_props['poisson_ratio']

        # A) Eksenel basma burkulmasi
        if thickness > 0 and radius > 0:
            sigma_cl = E / np.sqrt(3.0 * (1.0 - nu**2)) * (thickness / radius)
            phi = (1.0 / 16.0) * np.sqrt(radius / thickness)
            gamma_kd = 1.0 - 0.901 * (1.0 - np.exp(-phi))
            sigma_cr_axial = gamma_kd * sigma_cl
        else:
            sigma_cl = float('inf')
            gamma_kd = 1.0
            sigma_cr_axial = float('inf')

        # Uygulanan NET eksenel BASMA gerilmesi (bkz. docstring #203):
        # basma (F/2πrt) eksi ic-basinc boylamsal CEKME kredisi (p*r/2t).
        # F075: kredi YALNIZ basincli yuk durumunda gecerlidir; basincsiz
        # durumda (nakliye/montaj/atesleme oncesi) kredi YOKTUR.
        if thickness > 0 and radius > 0:
            sigma_compression = (axial_compression_force
                                 / (2.0 * np.pi * radius * thickness))
            sigma_pressure_tension = pressure * radius / (2.0 * thickness)
            applied_pressurized = max(
                sigma_compression - sigma_pressure_tension, 0.0)
            applied_unpressurized = max(sigma_compression, 0.0)
        else:
            sigma_compression = float('inf')
            sigma_pressure_tension = 0.0
            applied_pressurized = float('inf')
            applied_unpressurized = float('inf')

        def _sf(applied: float) -> float:
            return (sigma_cr_axial / applied if applied > 0 else float('inf'))

        sf_pressurized = _sf(applied_pressurized)
        sf_unpressurized = _sf(applied_unpressurized)
        # Yoneten yuk durumu: dusuk SF'li olan (kredi yalnizca yardim ettigi
        # icin pratikte daima basincsiz durum).
        if sf_unpressurized <= sf_pressurized:
            governing_case = 'unpressurized'
            applied_axial_stress = applied_unpressurized
            axial_buckling_sf = sf_unpressurized
        else:
            governing_case = 'pressurized'
            applied_axial_stress = applied_pressurized
            axial_buckling_sf = sf_pressurized

        # B) Dis basinc burkulmasi (uzun silindir klasik)
        # Konservatif olarak uygulanan dis basinci = tasarim basincinin
        # buyuklugu kadar alinabilir; burada referans olarak 1 atm dis ortam
        # (kapali kazan ic basinci ic'e dogru cidari destekler, ancak vakum/
        # dis basinc senaryosu icin kritik dis basinc raporlanir).
        p_cr_external = E / (4.0 * (1.0 - nu**2)) * (thickness / radius)**3 if radius > 0 else float('inf')
        # F075(c): bu form UZUN silindir varsayimidir (L'den bagimsiz). Kisa
        # silindirlerde gercek kritik dis basinc daha yuksektir, dolayisiyla
        # form konservatiftir; varsayim L/r ile birlikte BEYAN edilir.
        length_over_radius = (float(length) / radius
                              if radius > 0 and length else None)

        # --- P5B1-15: UYGULANAN DIS BASINC ZARFI ---------------------------
        # max(p_dis - p_ic_min, 0). Yuk durumu beyan edilmediyse hukum YOK.
        def _sonlu(x):
            try:
                f = float(x)
            except (TypeError, ValueError):
                return None
            return f if np.isfinite(f) else None

        p_ext_ortam = _sonlu(external_pressure)
        p_ic_min = _sonlu(internal_pressure_min)
        if p_ext_ortam is None:
            applied_external = None
            external_case_basis = (
                'not evaluated: no external-pressure load case was declared. '
                'Pass external_pressure (applied ambient pressure, Pa) and '
                'internal_pressure_min (lowest internal pressure in that '
                'case, Pa) to obtain a verdict. This module does not invent '
                'a load case; the ground reference pressure is published as '
                'ground_reference_external_pressure_bar for the caller to '
                'use deliberately.')
        else:
            p_ic_kullanilan = 0.0 if p_ic_min is None else p_ic_min
            applied_external = max(p_ext_ortam - p_ic_kullanilan, 0.0)
            external_case_basis = (
                'applied external differential = max(external_pressure - '
                'internal_pressure_min, 0) = max(%.6g - %.6g, 0) Pa'
                % (p_ext_ortam, p_ic_kullanilan))

        if applied_external is None or applied_external <= 0.0:
            external_buckling_sf = None
            external_buckling_status = BUCKLING_VERDICT_NOT_EVALUATED
            if applied_external is not None and applied_external <= 0.0:
                external_case_basis += (
                    '. The envelope collapses to zero (the internal pressure '
                    'is at or above the external one), so this load case '
                    'cannot buckle the shell inwards and NO verdict is '
                    'earned: the status is NOT_EVALUATED, not SAFE.')
        elif np.isfinite(p_cr_external):
            external_buckling_sf = float(p_cr_external / applied_external)
            if external_buckling_sf < BUCKLING_SF_CRITICAL_BELOW:
                external_buckling_status = 'CRITICAL'
            elif external_buckling_sf < BUCKLING_SF_MARGINAL_BELOW:
                external_buckling_status = 'MARGINAL'
            else:
                external_buckling_status = 'SAFE'
        else:
            external_buckling_sf = None
            external_buckling_status = BUCKLING_VERDICT_NOT_EVALUATED

        # Eksenel modun KENDI adiyla yazilmis hukmu (eski 'buckling_status'
        # bu sayidan geliyordu ve adi butun burkulmayi iddia ediyordu).
        if axial_buckling_sf < BUCKLING_SF_CRITICAL_BELOW:
            axial_buckling_status = 'CRITICAL'
        elif axial_buckling_sf < BUCKLING_SF_MARGINAL_BELOW:
            axial_buckling_status = 'MARGINAL'
        else:
            axial_buckling_status = 'SAFE'

        # BIRLESIK hukum (fail-closed): bir mod degerlendirilmediyse
        # 'SAFE' KAZANILMAMISTIR.
        mod_hukumleri = (axial_buckling_status, external_buckling_status)
        if 'CRITICAL' in mod_hukumleri:
            buckling_status = 'CRITICAL'
        elif 'MARGINAL' in mod_hukumleri:
            buckling_status = 'MARGINAL'
        elif BUCKLING_VERDICT_NOT_EVALUATED in mod_hukumleri:
            buckling_status = BUCKLING_VERDICT_NOT_EVALUATED
        else:
            buckling_status = 'SAFE'

        return {
            'classical_axial_buckling_stress_MPa': (sigma_cl / 1e6
                                                    if np.isfinite(sigma_cl) else float('inf')),
            'knockdown_factor_gamma': gamma_kd,
            'critical_axial_buckling_stress_MPa': (sigma_cr_axial / 1e6
                                                   if np.isfinite(sigma_cr_axial) else float('inf')),
            'applied_axial_stress_MPa': (applied_axial_stress / 1e6
                                         if np.isfinite(applied_axial_stress) else float('inf')),
            'axial_buckling_safety_factor': axial_buckling_sf,
            'critical_external_pressure_bar': (p_cr_external / 1e5
                                               if np.isfinite(p_cr_external) else float('inf')),
            # --- P5B1-15: DIS BASINC MODU ARTIK BIR HUKME BAGLI ----------
            'applied_external_pressure_bar': (None if applied_external is None
                                              else applied_external / 1e5),
            'external_buckling_safety_factor': external_buckling_sf,
            'external_buckling_status': external_buckling_status,
            'external_buckling_case_basis': external_case_basis,
            # NOT: yer referans basinci SAYISAL YAPRAK OLARAK
            # yayimlanmaz. tests/test_field_wiring_layer_b.py::
            # test_no_fabricated_constant_outputs sifir esikli bir sabit
            # yaprak envanteridir ve girdiden bagimsiz her sayisal yapragi
            # yakalar; mesru bir referans sabiti bile o envanteri bozar
            # (OK-22: saglikli envanter GEVSETILMEZ). Deger METIN olarak
            # adiyla ve kaynagiyla beyan edilir, makine tarafi ayni sayiyi
            # hrma.constants.P_SEA_LEVEL_PA'dan okur.
            'ground_reference_source': (
                'Ground reference for the external-pressure load case: the '
                'ISA / U.S. Standard Atmosphere 1976 sea-level pressure, '
                '%.5f bar (hrma.constants.P_SEA_LEVEL_PA). It is a '
                'REFERENCE for the ground scenarios (cooling condensation, '
                'closed drain) and is NOT applied automatically; pass it as '
                'external_pressure to obtain a verdict.'
                % (BUCKLING_GROUND_REFERENCE_PRESSURE_PA / 1e5)),
            # Eksenel modun kendi adiyla yazilmis hukmu.
            'axial_buckling_status': axial_buckling_status,
            'buckling_status': buckling_status,
            'buckling_status_scope': (
                'buckling_status is the COMBINED verdict over both modes '
                'checked here: axial compression (axial_buckling_status) and '
                'external-pressure collapse (external_buckling_status). It '
                'is SAFE only when BOTH modes were evaluated and both are '
                'safe; if either mode has no declared load case the combined '
                'verdict is NOT_EVALUATED, never SAFE. Modes NOT covered by '
                'this function at all: local/panel buckling, stiffened-shell '
                'and cutout effects, and combined bending plus pressure.'),
            # #203 sonrasi eklenen tanilar: uygulanan basma kuvveti ve
            # ic-basinc cekme kredisi (raporlanan applied = NET basma)
            'axial_compression_force_N': axial_compression_force,
            'pressure_stabilizing_stress_MPa': (sigma_pressure_tension / 1e6
                                                if np.isfinite(sigma_pressure_tension) else 0.0),
            # F075: iki yuk durumu ayri ayri raporlanir; yoneten olan
            # yukaridaki 'axial_buckling_safety_factor' alanina yazilir.
            'axial_buckling_safety_factor_pressurized': sf_pressurized,
            'axial_buckling_safety_factor_unpressurized': sf_unpressurized,
            'applied_axial_stress_pressurized_MPa': (
                applied_pressurized / 1e6
                if np.isfinite(applied_pressurized) else float('inf')),
            # v2.6.26 — SABİT ÇIKTI BEYANI. Bu alan sık sık TAM 0.0 çıkar ve
            # okuyucu "hesaplanmadı" sanır; oysa hesaplanır ve TABANA KENETLİ
            # (max(...,0)) çıkar: ic-basinc boylamsal cekmesi eksenel basmayi
            # asinca net basma sifirdir.
            'applied_axial_stress_pressurized_basis': (
                'net axial compression in the pressurised load case: '
                'max(thrust compression F/(2*pi*r*t) - internal pressure '
                'longitudinal tension p*r/(2t), 0). A value of exactly zero '
                'is the clamp, not a missing model: the pressure tension '
                'exceeds the axial compression, so this load case cannot '
                'buckle the shell and the unpressurised case governs. Both '
                'contributors are published next to this field '
                '(axial_compression_force_N, '
                'pressure_stabilizing_stress_MPa).'),
            'applied_axial_stress_unpressurized_MPa': (
                applied_unpressurized / 1e6
                if np.isfinite(applied_unpressurized) else float('inf')),
            'governing_load_case': governing_case,
            'stabilizing_pressure_bar': pressure / 1e5,
            # F075(c): dis basinc formu uzunluktan bagimsiz (uzun silindir);
            # kisa silindirlerde konservatif.
            'length_over_radius': length_over_radius,
            'external_pressure_model': (
                'long-cylinder classical form (length-independent); '
                'conservative for short cylinders'),
            'source': 'NASA SP-8007 (1968), NTRS 19680026348'
        }
    
    def analyze_structure(self, motor_data: Dict, material: str = 'steel_4130',
                         design_pressure_factor: float = 1.5,
                         design_safety_factor: Optional[float] = None,
                         actual_wall_thickness: Optional[float] = None,
                         actual_throat_thickness: Optional[float] = None,
                         actual_end_cap_thickness: Optional[float] = None) -> Dict:
        """
        Complete structural analysis

        Args:
            motor_data: Motor performance and geometry data
            material: Material type
            design_pressure_factor: Safety factor for design pressure
            design_safety_factor: Tasarım emniyet katsayısı hedefi (v2.6.26 —
                arayüzün 'Safety Factor' alanı; _analyze_chamber_wall bunu
                zaten destekliyordu ama buradan İLETİLMİYORDU, alan ölüydü).
                None -> malzeme kaydındaki eski varsayılan.
            actual_wall_thickness: Kullanıcının GERÇEK cidar kalınlığı [m].
                Verilirse hazne cidarı DOĞRULAMA modunda değerlendirilir
                (SF gerçek cidardan); None -> eski boyutlandırma modu.
            actual_throat_thickness: Kullanıcının GERÇEK boğaz cidarı [m].
                v2.6.27 (F4-2): ``_analyze_nozzle_structure`` bu argümanı
                zaten destekliyordu ama BURADAN İLETİLMİYORDU, yani lüle
                hiçbir girdiyle doğrulama moduna geçemiyordu ve totolojik
                SF'siyle genel hükmü çiviliyordu. None -> boyutlandırma modu
                (eski davranış birebir).
            actual_end_cap_thickness: Kullanıcının GERÇEK kapak kalınlığı [m].
                Aynı gerekçe; ``_analyze_end_caps`` argümanı destekliyordu,
                çağrı satırı geçirmiyordu. None -> boyutlandırma modu.

        Returns:
            Structural analysis results
        """
        
        # --- ÖH D22 / P5B1-16 + P5B1-18: KAPI ve VARSAYILAN BEYANI -----
        # Kapı: gönderilmiş ama fiziksel OLMAYAN değer reddedilir (ölçüm
        # ``once.json`` P5B1-16_18: -0,1 m çap sessizce -3,14 mm cidar,
        # -40 bar NaN ağırlık, 0 bar ham ZeroDivisionError üretiyordu).
        # Beyan: gönderilmemiş alanın modül varsayılanından geldiği
        # ``inputs_defaulted`` ile ADIYLA yazılır — sayı susmaz, kaynağını
        # söyler. Varsayılan sayılar ``STRUCTURAL_INPUT_DEFAULTS`` tek
        # kaynağından okunur (Doktrin 4).
        _gecersiz, inputs_defaulted = _structural_input_gate(motor_data)
        if _gecersiz:
            raise NonPhysicalStructuralInput(_gecersiz)

        # Extract motor parameters
        _vars = STRUCTURAL_INPUT_DEFAULTS
        chamber_pressure = (
            motor_data.get('chamber_pressure', _vars['chamber_pressure'][0])
            * 1e5)                                                      # Pa
        chamber_diameter = motor_data.get(
            'chamber_diameter', _vars['chamber_diameter'][0])           # m
        chamber_length = motor_data.get(
            'chamber_length', _vars['chamber_length'][0])               # m
        throat_diameter = motor_data.get(
            'throat_diameter', _vars['throat_diameter'][0])             # m
        nozzle_type = motor_data.get('nozzle_type', _vars['nozzle_type'][0])
        # ÖH D15 / P5B1-10: ``burn_time`` BURADAN KALDIRILDI. Okunuyor,
        # yokken 10 s uyduruluyor ve tek tüketicisi olan ``_analyze_fatigue``
        # tarafından HİÇ KULLANILMIYORDU (o parametrenin kendi belgesi
        # "bilgi amaçlı; çevrim sayılmaz" diyordu). ÖLÇÜLDÜ (taban
        # ``once.json``; Pc 50 bar, D 150 mm, cidar 5 mm, steel_4130):
        # burn_time 0,5 / 10 / 1000 / 1 000 000 s için ``analyze_structure``
        # çıktısının JSON serileştirmesi BİREBİR AYNI (17 648 bayt, tek imza),
        # n_f sabit 3,65, design_cycles sabit 25. Yanma süresi bu modelde
        # basınçlandırma ÇEVRİMİ üretmez (R=0 çevrim sayısı ``design_cycles``
        # ile gelir), dolayısıyla sessiz varsayılan da tüketicisi olmayan
        # parametre de kaldırıldı: model yanma süresini GÖRDÜĞÜNÜ artık
        # iddia etmiyor. (Uçtaki pozitiflik kapısı GEVŞETİLMEDİ — ÖK-22.)

        # Design pressure
        design_pressure = chamber_pressure * design_pressure_factor

        # Get material properties
        mat_props = self.materials.get(material, self.materials['steel_4130'])

        # DENETIM DUZELTMESI: Cidar sicakligini tahmin et (termal gerilme +
        # derating icin). motor_data 'wall_temperature_hot/cold' veya
        # 'chamber_temperature' tasiyabilir; yoksa termal etki devre disi kalir.
        T_inner_wall, T_outer_wall = self._estimate_wall_delta_T(motor_data, mat_props)

        # --- ÖH ONARIMI (defter P5B1-02, YÜKSEK): SERVİS SINIRI EKSENİ ----
        # Kusur: cidar sıcaklığı TAHMİNİ malzemenin kendi servis sınırından
        # çıkıyordu (T_iç = min(T_alev, 0,9 x max_service_temp)), bu yüzden
        # servis-sınırı kontrolü malzemeyi KENDİ SINIRIYLA sınıyordu.
        # ÖLÇÜLDÜ (steel_4130, sınır 811 K): chamber_temperature 1000 /
        # 3000 / 10000 K -> peak_wall_temperature_K üçünde de 729,90 K,
        # thermal_margin_ratio üçünde de TAM 0,900000; aynı 3000 K alevde
        # malzeme değişince oran yine TAM 0,900000 (aluminum_6061 429,30 K,
        # inconel_718 879,30 K). Termal UNSAFE bandı ölüydü ve
        # ``exceeds_max_service_temp_peak`` tanım gereği True olamıyordu.
        #
        # DOKTRİN (ÖH karar 10+11, asimetrik T_aw): alev/kurtarma sıcaklığı
        # soğutmasız cidar için TERMODİNAMİK ÜST SINIRDIR. Soğutma verisi
        # yokken servis-sınırı hükmü o ÜST SINIRDAN okunur:
        #   * sınır altındaysa hüküm KAZANILIR (üst sınır bile güvenliyse
        #     cidar güvenlidir; soğutma verisi gerekmez),
        #   * sınır üstündeyse hüküm fail-closed yönde konuşur ve sayının
        #     ÜST SINIR olduğu ``peak_wall_temperature_basis`` künyesinde
        #     ADIYLA yazılır (gerçekleşmiş sıcaklık DEĞİLDİR).
        # Gerçek cidar sıcaklığı verildiğinde (ısı transferi modülü) bu dal
        # HİÇ çalışmaz ve ölçülmüş sayı kullanılır — eski davranış aynen.
        _cidar_verildi = (motor_data.get('wall_temperature_hot') is not None
                          and motor_data.get('wall_temperature_cold')
                          is not None)
        _T_alev = motor_data.get('chamber_temperature')
        if _cidar_verildi or _T_alev is None:
            T_peak_service = T_inner_wall
            peak_wall_temperature_basis = (
                'measured wall temperature supplied by the caller '
                '(wall_temperature_hot); the service-limit check uses it '
                'directly'
                if _cidar_verildi else
                'no chamber temperature was supplied: the thermal axis is '
                'inactive and the ambient temperature is echoed')
        else:
            T_peak_service = float(_T_alev)
            peak_wall_temperature_basis = (
                'UPPER BOUND, not a realised temperature: no cooled wall '
                'temperature was supplied, so the service-limit check uses '
                'the chamber (recovery) temperature %.1f K - an uncooled '
                'wall cannot exceed it. Below the service limit this bound '
                'EARNS the verdict; above it the verdict is a fail-closed '
                'warning and a real wall temperature '
                '(wall_temperature_hot/cold, from the heat-transfer module) '
                'is required to replace it. The gradient/derating axis '
                'keeps its own uncooled thin-wall estimate '
                '(wall_temperature_inner_K = %.2f K); the two are separate '
                'questions and are published under separate names.'
                % (float(_T_alev), T_inner_wall))

        # OPUS DENETIM DUZELTMESI (major): Eski kod AYNI ANDA hem "cidar
        # servis sicakligina isinmis" (agir derating) hem de "tam soguk
        # gradyan" (tam termal gerilme) varsayiyordu — fiziksel olarak
        # celiskili iki uc durumun yigilmasi her sicak motoru SF~0.10'a
        # cokertiyordu. Iki TUTARLI senaryo ayri degerlendirilir, kritik
        # (dusuk SF'li) olan tasarimi yonetir:
        #   A) Sicak-soak (sogutmasiz kararli hal): cidar ~izotermal sicak
        #      -> derating T_ic'te, gradyan kucuk artik deger (0.15x)
        #   B) Sogutmali gradyan: ic yuz sicak, ortalama cidar daha soguk
        #      -> derating ORTALAMA cidar sicakliginda, gradyan tam
        scenarios = {}
        dT_full = T_inner_wall - T_outer_wall
        senaryo_tanim = {
            'hot_soak': (T_inner_wall, 0.15 * dT_full),
            'cooled_gradient': (0.5 * (T_inner_wall + T_outer_wall), dT_full),
        }
        # --- V3 yapi-sf (7 Eki 2026): ORTAK CİDAR, İKİ SENARYO -----------
        # Eskiden her senaryo KENDİ cidarını boyutlandırıyor ve yöneten
        # senaryonun cidarı yayımlanıyordu; öbür senaryo o cidarda HİÇ
        # değerlendirilmiyordu (``thermal_scenarios`` onun kendi cidarındaki
        # sayısını basıyordu). Yayımlanan cidar tektir: boyutlandırma iki
        # senaryoyu BİRLİKTE sağlar, ikisi de o cidarda değerlendirilir.
        # Gradyanın hangi cidarda hesaplandığı (ölçekleme referansı):
        thermal_ref_t = self._thermal_reference_thickness_m(motor_data)
        deratings = {name: self._derate_strength(mat_props, T_derate)
                     for name, (T_derate, _dT) in senaryo_tanim.items()}
        # Doğrulama kipinde de önerilen cidar (öğüt) aynı ortak
        # boyutlandırmadan gelir.
        _sf_hedef = (float(design_safety_factor)
                     if design_safety_factor is not None
                     else mat_props['safety_factor'])
        ortak_boyut = self._size_chamber_wall(
            design_pressure, chamber_diameter / 2, _sf_hedef,
            [(name, deratings[name]['derated_yield_strength'],
              self._thermal_hoop_stress(mat_props, dT)
              ['thermal_hoop_stress'])
             for name, (_T, dT) in senaryo_tanim.items()],
            thermal_ref_t)
        # --- V3 yapi-sf 2. tur (karar §28-24 (C)): MODEL GEÇERLİLİK SINIRI
        # Yayımlanan cidar iki senaryoda da değerlendirildiği için ölçüt iki
        # senaryonun düşürme kaydını birlikte okur (tek yer:
        # ``structural_model_validity``).
        gecerlilik = structural_model_validity(deratings)
        if (gecerlilik['model_validity_limit_exceeded']
                and not ortak_boyut['sizing_feasible']):
            # "Ulaşılamaz" gerçek motorun değil MODELİN sınırıdır: cümle
            # gerekçenin BAŞINA konur ki okuyan ilk onu görsün.
            ortak_boyut['sizing_infeasible_reason'] = (
                MODEL_VALIDITY_SIZING_NOTE + ' '
                + (ortak_boyut['sizing_infeasible_reason'] or ''))
        for name, (T_derate, dT) in senaryo_tanim.items():
            der = deratings[name]
            ana = self._analyze_chamber_wall(
                design_pressure, chamber_diameter, chamber_length, mat_props,
                derating=der, wall_delta_T=dT,
                actual_thickness=actual_wall_thickness,
                design_safety_factor=design_safety_factor,
                thermal_reference_thickness=thermal_ref_t,
                sizing=ortak_boyut,
            )
            scenarios[name] = {'analysis': ana, 'derating': der,
                               'derating_temp_K': T_derate, 'delta_T_K': dT}

        # Yoneten senaryo: dusuk von Mises SF'li olan
        governing = min(
            scenarios,
            key=lambda k: scenarios[k]['analysis'].get(
                'von_mises_safety_factor', float('inf')))
        chamber_analysis = scenarios[governing]['analysis']
        chamber_analysis['governing_thermal_scenario'] = governing
        # V3 yapi-sf 2. tur (C): geçerlilik bayrağı + künye. CAD kulvarının
        # imalat SF kapısı ``chamber_analysis.model_validity_limit_exceeded``
        # alanını okur (True = ret).
        chamber_analysis.update(gecerlilik)
        chamber_analysis['model_validity_limit_exceeded_basis'] = (
            MODEL_VALIDITY_BASIS)
        if gecerlilik['model_validity_limit_exceeded']:
            # Sayı KALIR (tanı amaçlı); künyesi geçerli tasarım çıktısı
            # olmadığını söyler.
            chamber_analysis['safety_factor_basis'] = (
                MODEL_VALIDITY_SAFETY_FACTOR_BASIS)
        chamber_analysis['thermal_scenarios'] = {
            k: {'von_mises_safety_factor':
                v['analysis'].get('von_mises_safety_factor'),
                # V3 yapi-sf 2. tur (Ş1/Ş7): iki senaryo AYNI cidarda
                # değerlendirildiği için o cidardaki toplam-hoop SF'si de
                # senaryo başına yayımlanır (bağlayan senaryo hedef × payı
                # tutar, öbürü üstündedir).
                'hoop_safety_factor':
                    v['analysis'].get('hoop_safety_factor'),
                'derating_temp_K': v['derating_temp_K'],
                'delta_T_K': v['delta_T_K'],
                'delta_T_at_evaluated_wall_K':
                    v['analysis'].get('wall_delta_T_at_evaluated_wall_K')}
            for k, v in scenarios.items()}
        derating = scenarios[governing]['derating']
        wall_temp_structural = scenarios[governing]['derating_temp_K']
        wall_delta_T = scenarios[governing]['delta_T_K']

        # Burkulma kontrolu (NASA SP-8007) - hazne cidari geometrisiyle.
        # #203: eksenel BASMA yuku olarak motor itkisi kullanilir (ucus/montaj
        # basmasinin ust sinari — itkinin tamami kabuktan gecer varsayimi,
        # muhafazakar). motor_data'da thrust yoksa 0 -> saf ic basinc
        # eksenel burkulma yaratamaz (cekme), SF=inf/SAFE raporlanir.
        # FIZIK DENETIMI F075(b) (2026-07-25): stabilize eden ic basinc
        # kredisi ALT SINIR basinctan (MEOP = Pc) alinir, tasarim basincindan
        # (1.5*Pc) DEGIL. Kredi net basmadan CIKARILDIGI icin daha yuksek bir
        # basinc kullanmak net basmayi azaltir, yani konservatif olmaz.
        # OLCULDU (Pc=50 bar, D=150 mm, F=500 kN, T_ic=860 K): kredi
        # 27.74 MPa -> 18.49 MPa; basincli durum SF 181.09 -> 161.66.
        # Kaynak: NASA SP-8007 (1968) — basinc stabilizasyonu yalnizca fiilen
        # mevcut olan basinctan kredi alir.
        # v2.6.26: burkulma DEĞERLENDİRİLEN cidarla yapılır — doğrulama
        # modunda kullanıcının gerçek cidarı, boyutlandırma modunda önerilen
        # kalınlık (o modda iki değer zaten aynıdır).
        chamber_t = chamber_analysis['wall_thickness_used_mm'] / 1000.0  # m
        axial_force = float(motor_data.get('thrust', 0.0) or 0.0)  # N
        # P5B1-15: dis basinc yuk durumu KULLANICIDAN gelir. Beyan
        # edilmediyse dis basinc modu NOT_EVALUATED kalir ve birlesik
        # 'buckling_status' de SAFE diyemez (kazanilmamis onay yayimlanmaz).
        # Sayi UYDURULMAZ: modul kendi yer senaryosunu uygulamaz.
        buckling_analysis = self._check_buckling(
            chamber_pressure, chamber_diameter / 2.0, chamber_t,
            chamber_length, mat_props,
            axial_compression_force=axial_force,
            external_pressure=motor_data.get('external_pressure'),
            internal_pressure_min=motor_data.get('internal_pressure_min'),
        )
        
        # Nozzle analysis
        # v2.6.26 — TASARIM EMNİYET KATSAYISI ARTIK BURAYA DA GEÇİYOR.
        # Üç fonksiyon (lüle, kapak, cıvata) kullanıcının SF girdisini
        # destekliyordu ama çağrı satırları onu geçmiyordu; sonuçta
        # kullanıcının 'Safety Factor' alanı YALNIZ hazne cidarına
        # uygulanıyor, lüle ve kapak malzeme kaydının kendi katsayısında
        # (çelikte 4.0) kilitli kalıyordu. ÖLÇÜLDÜ: safety_factor=2.0
        # girildiğinde nozzle_analysis.safety_factor ve
        # end_cap_analysis.head_safety_factor 4.0'da SABİT kaldı — tek
        # motorda iki farklı tasarım emniyet katsayısı kullanılıyordu.
        # v2.6.27 (F4-2): gerçek boğaz cidarı da artık İLETİLİYOR — verilirse
        # lüle doğrulama moduna geçer ve SF'si totolojik olmaktan çıkar.
        nozzle_analysis = self._analyze_nozzle_structure(
            design_pressure, throat_diameter, chamber_diameter, mat_props,
            nozzle_type, design_safety_factor=design_safety_factor,
            actual_throat_thickness=actual_throat_thickness
        )

        # End cap analysis
        end_cap_analysis = self._analyze_end_caps(
            design_pressure, chamber_diameter, mat_props,
            design_safety_factor=design_safety_factor,
            actual_thickness=actual_end_cap_thickness
        )

        # Bolt/fastener analysis
        # P5B1-06: sıkma boyu ve üye malzemesi ön-yük modeline İLETİLİR.
        # Sıkma boyu GERÇEK bir kullanıcı girdisidir (uydurulmaz); yoksa
        # cıvata bloğu hüküm vermez (fail-closed).
        _grip = motor_data.get('closure_grip_length_m')
        try:
            _grip = float(_grip) if _grip is not None else None
        except (TypeError, ValueError):
            _grip = None
        fastener_analysis = self._analyze_fasteners(
            design_pressure, chamber_diameter, mat_props,
            design_safety_factor=design_safety_factor,
            bolt_property_class=motor_data.get('bolt_property_class'),
            grip_length_m=_grip,
            member_material=material,
        )
        
        # Fatigue analysis
        # P5B1-03: yöneten senaryonun derating kaydı yorulmaya da GEÇER.
        # (Kayıt zaten burada duruyordu; yorulma onu görmüyordu.)
        fatigue_analysis = self._analyze_fatigue(
            chamber_analysis['hoop_stress'], mat_props,
            derating=derating
        )
        
        # Weight analysis
        weight_analysis = self._calculate_weight(
            chamber_analysis, nozzle_analysis, end_cap_analysis, mat_props
        )
        # V3 yapi-sf 2. tur (C): kütle dökümü de geçerlilik bayrağını taşır
        # (kamara kütlesi geçerlilik dışı değerlendirmenin cidarından).
        weight_analysis['model_validity_limit_exceeded'] = bool(
            gecerlilik['model_validity_limit_exceeded'])
        if gecerlilik['model_validity_limit_exceeded']:
            weight_analysis['model_validity_limit_exceeded_basis'] = (
                MODEL_VALIDITY_MASS_BASIS)
        
        # Safety analysis (burkulma da dahil edilir)
        # FIZIK DENETIMI F074 (2026-07-25): dayanim derating'i KESIT ORTALAMA
        # sicakliginda (yoneten senaryonun derating sicakligi) yapilir, ancak
        # SERVIS SINIRI / yumusama / surunme kontrolu TEPE (ic yuz) metal
        # sicakliginda yapilmalidir. Eski cagri yalnizca wall_temp_structural
        # geciyordu; 'cooled_gradient' yonettiginde bu ORTALAMA cidar
        # sicakligidir ve sicak yuz servis sinirini astiginda bile bayrak
        # False kaliyordu. OLCULDU (T_ic=860 K, T_dis=560 K, steel_4130,
        # servis siniri 811 K): oran 0.8755 -> 1.0604, exceeds False -> True.
        # Kaynak: MMPDS / malzeme ureticisi kisa-sureli maruziyet sinirlari.
        safety_analysis = self._analyze_safety_factors(
            chamber_analysis, nozzle_analysis, end_cap_analysis, mat_props,
            buckling_analysis=buckling_analysis,
            wall_temperature_K=wall_temp_structural,
            peak_wall_temperature_K=T_peak_service,
            peak_wall_temperature_basis=peak_wall_temperature_basis,
            model_validity=gecerlilik,
            # 7. tur: geçerlilik bloğu yorulma onayını da geri çekebilsin.
            fatigue_analysis=fatigue_analysis,
        )

        return {
            # --- ÖH D22 / P5B1-18: SESSİZ VARSAYILAN ARTIK KONUŞUYOR -----
            # ÖLÇÜLDÜ (``once.json``): BOŞ sözlükten tam bir sayı takımı
            # çıkıyordu (30,0 bar tasarım basıncı, 100 mm çap, 1,5700 mm
            # önerilen cidar, 95,5416 MPa hoop, 2,7278 kg ağırlık) ve hangi
            # girdinin varsayılandan geldiğini söyleyen TEK bir alan yoktu.
            # Alan HER koşumda yayımlanır: BOŞ sözlük de bir beyandır
            # ("hiçbir girdi varsayılandan gelmedi"), yokluğu ile
            # karıştırılmaz.
            'inputs_defaulted': inputs_defaulted,
            'inputs_defaulted_basis': (
                'Fields the caller did not supply, for which this module '
                'applied its own documented default (see '
                'STRUCTURAL_INPUT_DEFAULTS). An empty object means every '
                'geometry/pressure input below came from the caller. A '
                'value that was supplied but is not physical is REJECTED '
                '(NonPhysicalStructuralInput), never defaulted.'),
            'chamber_analysis': chamber_analysis,
            'nozzle_analysis': nozzle_analysis,
            'end_cap_analysis': end_cap_analysis,
            'fastener_analysis': fastener_analysis,
            'fatigue_analysis': fatigue_analysis,
            'weight_analysis': weight_analysis,
            'safety_analysis': safety_analysis,
            # İki SF raporu (Dalga 0, 2026-07-14): üst seviyede de raporlanır
            # ki UI/rapor katmanı chamber_analysis'e inmek zorunda kalmasın.
            # safety_factor = safety_factor_total (geriye dönük tek-SF alanı).
            'safety_factor_pressure': chamber_analysis.get('safety_factor_pressure'),
            'safety_factor_total': chamber_analysis.get('safety_factor_total'),
            'safety_factor': chamber_analysis.get('safety_factor_total'),
            # V3 yapi-sf 2. tur (C): üst seviye SF alanlarının geçerlilik
            # bayrağı (kanonik alan chamber_analysis'tedir; bu bir yansıdır).
            'model_validity_limit_exceeded': bool(
                gecerlilik['model_validity_limit_exceeded']),
            # YENI (DENETIM DUZELTMESI 2026-06)
            'thermal_analysis': {
                'wall_temperature_inner_K': T_inner_wall,
                'wall_temperature_outer_K': T_outer_wall,
                'wall_delta_T_K': wall_delta_T,
                # V3 yapi-sf 2. tur Ş3 (denetim U3): ``wall_delta_T_K``
                # sıcaklıkların HESAPLANDIĞI (referans) cidara aittir — iç/dış
                # sıcaklıklarla aynı cidar. Isıl hoop gerilmesini süren ΔT
                # DEĞERLENDİRİLEN cidardakidir; boyutlandırma kipinde ikisi
                # sabit akı ölçeklemesiyle ayrışır. İki sayı ve iki cidar
                # ayrı adla yayımlanır (panel ikisini ayrı satırda basar).
                'wall_delta_T_at_evaluated_wall_K':
                    chamber_analysis.get('wall_delta_T_at_evaluated_wall_K'),
                'thermal_reference_wall_thickness_mm':
                    chamber_analysis.get('thermal_reference_wall_thickness_mm'),
                'evaluated_wall_thickness_mm':
                    chamber_analysis.get('wall_thickness_used_mm'),
                'strength_derating': derating,
                'thermal_hoop_stress_MPa': chamber_analysis.get('thermal_hoop_stress', 0.0),
                # F074: strength_derating['exceeds_max_service_temp'] KESIT
                # ORTALAMA sicakliginda hesaplanir (derating icin dogru taban),
                # bu yuzden sicak yuz limiti astiginda False kalabilir. Servis
                # siniri kararinin dogru tabani TEPE (ic yuz) sicakligidir.
                'exceeds_max_service_temp_peak':
                    safety_analysis.get('exceeds_max_service_temp_peak', False),
                'service_temperature_basis': (
                    'peak (inner-wall) metal temperature; strength derating '
                    'uses the section-average temperature'),
                # v2.6.27 (A3) — SICAKLIGIN KAYNAGI. 'not_evaluated' iken
                # yukaridaki iki sicaklik HESAPLANMIS DEGILDIR: ikisi de
                # ortam sicakligidir ve termal etki kapalidir. Cagiran katman
                # bu alani okuyup hesaplanmamis sayiyi yayimlamamalidir.
                'wall_temperature_source':
                    self._wall_temperature_source(motor_data),
                'thermal_model_ran': bool(
                    self._wall_temperature_source(motor_data)
                    != 'not_evaluated'),
            },
            'buckling_analysis': buckling_analysis,
            # v2.6.26 — AD CAKISMASI BEYAN EDILIYOR.
            # mat_props['safety_factor'] materials_db'nin bu malzeme icin
            # ONERDIGI tasarim katsayisidir (celik 4,0; inconel 3,0).
            # Kullanicinin girdigi tasarim emniyet katsayisi DEGILDIR ama
            # ayni adi tasiyor: kullanici SF=6 girip bu alanda 4,0 gorunce
            # 'girdim yutuldu' diye okuyor. Deger dogru, sunum yaniltici.
            'material_properties': published_material_record(mat_props),
            'design_parameters': {
                'material': material,
                'design_pressure': design_pressure / 1e5,  # bar
                'design_pressure_factor': design_pressure_factor,
                # v2.6.26 — SABİT ÇIKTI BEYANI. Bu çarpan çağıran motorun
                # geçtiği bir SABİTTİR (hibritte hybrid_rocket_engine.py
                # analyze_structure çağrısında design_pressure_factor=1.5) ve
                # kullanıcının emniyet katsayısı DEĞİLDİR: ikisi çarpışır.
                'design_pressure_factor_basis': (
                    'design pressure = chamber pressure x this design '
                    'pressure factor. The factor is passed in as a constant '
                    'by the calling engine, it is NOT computed here and it is '
                    'NOT the safety_factor entered by the user - it is a '
                    'separate multiplier that compounds with it (proof/burst '
                    'pressure margin over MEOP).'),
                'wall_temperature_K': wall_temp_structural
            }
        }
    
    @staticmethod
    def _thickness_for_hoop_allowable(pressure: float, radius: float,
                                      allowable: float) -> float:
        """``allowable`` izin verilen gerilmesini LAME tepe hoop'uyla
        sağlayan cidar kalınlığı [m]; çözüm yoksa ``inf``.

        Lame (iç basınç, iç yüzey tepe değeri, b = a + t):
            σ = P (b² + a²) / (b² − a²) = S
          ⇒ b² (S − P) = a² (S + P)
          ⇒ t = a · ( √((S + P)/(S − P)) − 1 )
        S <= P ise hiçbir kalınlık yetmez (σ, t → ∞ iken P'ye asimptot
        yapar) — ``inf`` döner ve çağıran bunu ADIYLA beyan eder.
        Kaynak: Lame (1833); Roark's Formulas for Stress & Strain 9. baskı
        Tablo 13.5.
        """
        if not (pressure > 0.0 and radius > 0.0 and allowable > 0.0):
            return float('inf')
        if allowable <= pressure:
            return float('inf')
        return radius * (np.sqrt((allowable + pressure)
                                 / (allowable - pressure)) - 1.0)

    @staticmethod
    def _estimate_reference_thickness_m(motor_data: Dict) -> float:
        """Tahmin yolunun (``_estimate_wall_delta_T`` yol 2) gradyanı hangi
        cidarda hesapladığı [m] — tek tanım (V3 yapi-sf)."""
        return float(motor_data.get('wall_thickness',
                                    ESTIMATE_WALL_THICKNESS_DEFAULT_M)
                     or ESTIMATE_WALL_THICKNESS_DEFAULT_M)

    @staticmethod
    def _thermal_reference_thickness_m(motor_data: Dict) -> Optional[float]:
        """Cidar sıcaklık gradyanının HESAPLANDIĞI cidar kalınlığı [m].

        V3 yapi-sf. Gradyan sabit ısı akısında kalınlıkla doğru orantılıdır
        (ΔT = q·t/k); boyutlandırma ΔT'yi ölçeklemek için gradyanın hangi
        cidara ait olduğunu bilmek zorundadır.
          * Isı modülü sıcaklıkları verildiyse: çağıranın beyan ettiği
            ``wall_temperature_reference_thickness`` [m] (yoksa None:
            gradyan verildiği değerde TUTULUR ve beyan edilir);
          * yalnız gaz sıcaklığı verildiyse: tahmin yolunun kendi cidarı;
          * hiçbiri yoksa: None (ısıl yol kapalı, gradyan sıfır).
        """
        if (motor_data.get('wall_temperature_hot') is not None
                and motor_data.get('wall_temperature_cold') is not None):
            ref = motor_data.get('wall_temperature_reference_thickness')
            try:
                ref = float(ref) if ref is not None else None
            except (TypeError, ValueError):
                ref = None
            if ref is not None and np.isfinite(ref) and ref > 0.0:
                return ref
            return None
        if motor_data.get('chamber_temperature') is not None:
            return StructuralAnalyzer._estimate_reference_thickness_m(
                motor_data)
        return None

    @staticmethod
    def _thermal_scale(thickness: float,
                       reference_thickness: Optional[float]) -> float:
        """Isıl gradyanın ``thickness`` cidarındaki / referanstaki oranı.

        Sabit ısı akısında iletim düşüşü kalınlıkla doğru orantılıdır
        (düzlem duvar R = t/k). Referans bilinmiyorsa 1,0 (gradyan
        TUTULUR). Aynı cidar (kayan nokta gidiş-dönüşü) tam 1,0 verir.
        """
        if reference_thickness is None or not reference_thickness > 0.0:
            return 1.0
        if (abs(thickness - reference_thickness)
                <= THERMAL_REFERENCE_SAME_WALL_REL_TOL * reference_thickness):
            return 1.0
        return thickness / reference_thickness

    @staticmethod
    def _evaluated_pressure_hoop(pressure: float, radius: float,
                                 thickness: float) -> float:
        """Değerlendirmenin KULLANDIĞI basınç hoop gerilmesi [Pa].

        ``_analyze_chamber_wall`` değerlendirmesiyle aynı model: t/r <
        THIN_WALL_T_OVER_R_LIMIT ise ince cidar P·r/t, üstünde
        max(ince cidar, Lame iç yüzey tepe). Boyutlandırma bu fonksiyonu
        çözer ki iki taraf aynı modelden konuşsun.
        """
        thin = pressure * radius / thickness
        if thickness / radius < THIN_WALL_T_OVER_R_LIMIT:
            return thin
        b_outer = radius + thickness
        lame = (pressure * (b_outer**2 + radius**2)
                / (b_outer**2 - radius**2))
        return max(thin, lame)

    @staticmethod
    def _total_hoop_grid(pressure: float, radius: float, cases,
                         reference_thickness, izgara):
        """Tarama ızgarasında (``izgara`` [m]) her kalınlık için
        min_durum(izinli/toplam) oranı ve "her durumda toplam <= izinli"
        uygunluğu — 3. tur Ş2-6.

        ``_evaluated_pressure_hoop`` ve ``_thermal_scale``'in vektör hâli;
        işlem sırası skaler yolla aynıdır. Karşılaştırma anlamı da korunur:
        ``max(ince, lame)`` yalnız ``lame > ince`` iken Lame'i seçer, ``min``
        yalnız ``v < m`` iken günceller, uygunluk ``toplam > izinli`` ile
        bozulur (NaN'da Python yolunun kararı).
        """
        t = np.asarray(izgara, dtype=float)
        ince = pressure * radius / t
        b_outer = radius + t
        # Kare libm pow() ile alınır (skaler yolun ``b_outer**2``'si gibi):
        # numpy'ın ``dizi**2`` kısayolu b*b çarpımıdır ve pow()'dan 1 ulp
        # ayrışabilir (ölçüldü: rastgele 2·10⁶ değerin %0,13'ünde). Üs dizi
        # verilince ufunc döngüsü pow()'u çağırır — skalerle bit-eşit.
        b_kare = np.power(b_outer, np.full_like(b_outer, 2.0))
        lame = (pressure * (b_kare + radius**2)
                / (b_kare - radius**2))
        basinc = np.where(t / radius < THIN_WALL_T_OVER_R_LIMIT, ince,
                          np.where(lame > ince, lame, ince))
        if reference_thickness is None or not reference_thickness > 0.0:
            olcek = np.ones_like(t)
        else:
            ayni = (np.abs(t - reference_thickness)
                    <= THERMAL_REFERENCE_SAME_WALL_REL_TOL
                    * reference_thickness)
            olcek = np.where(ayni, 1.0, t / reference_thickness)
        oranlar = None
        bozuk = np.zeros(t.shape, dtype=bool)
        for izinli, sigma_th, _y in cases:
            toplam = basinc + sigma_th * olcek
            oran = izinli / toplam
            oranlar = oran if oranlar is None else np.where(
                oran < oranlar, oran, oranlar)
            bozuk |= toplam > izinli
        return oranlar, ~bozuk

    def _thickness_for_total_hoop_allowable(self, pressure: float,
                                            radius: float, cases,
                                            reference_thickness):
        """Her durumda TOPLAM hoop (basınç + ısıl) <= izinli olan EN İNCE
        cidar [m] ve ulaşılabilir en büyük emniyet oranı.

        ``cases``: [(izinli_gerilme_Pa, ısıl_gerilme_referansta_Pa,
        akma_Pa), ...]. Isıl gerilme ``_thermal_scale`` ile kalınlığa
        ölçeklenir. Döner ``(t_m | inf, en_iyi_oran, t_en_iyi_m)``;
        en_iyi_oran, taranan kalınlıklar üzerinde min_durum(izinli/toplam)'ın
        en büyüğü (1'den küçükse hedef hiçbir kalınlıkta tutmaz),
        t_en_iyi_m o en büyüğün ulaşıldığı tarama kalınlığı (2. tur Ş1:
        ulaşılamaz vakada sınırlayan senaryo orada adlandırılır).
        """
        def _ok(t):
            for izinli, sigma_th, _y in cases:
                toplam = (self._evaluated_pressure_hoop(pressure, radius, t)
                          + sigma_th * self._thermal_scale(
                              t, reference_thickness))
                if toplam > izinli:
                    return False
            return True

        izgara = radius * np.logspace(np.log10(SIZING_SCAN_T_OVER_R_MIN),
                                      np.log10(SIZING_SCAN_T_OVER_R_MAX),
                                      SIZING_SCAN_POINTS)
        # 3. tur Ş2-6 (yeniden denetim-2 U4): tarama ızgarası numpy ile
        # vektörleştirildi. Eskiden ızgaranın her noktasında skaler oran ve
        # uygunluk Python döngüsüyle hesaplanıyordu (UQ'da 4,8 milyon çağrı,
        # örnek başına +%14). Tarama noktaları, bisection ve aritmetik
        # sırası AYNI; yayımlanan sayılar bit-eşit (kanıt: rapor 3. tur Ş2-6).
        oranlar, uygun = self._total_hoop_grid(pressure, radius, cases,
                                               reference_thickness, izgara)
        en_iyi = 0.0
        t_en_iyi = None
        # Skaler döngünün anlamı: ilk "oran > en_iyi" güncellemesi, yani
        # 0'dan büyük en büyük oranın İLK konumu; NaN hiçbir zaman seçilmez.
        aday = np.where(np.isnan(oranlar), -np.inf, oranlar)
        k = int(np.argmax(aday))
        if aday[k] > en_iyi:
            en_iyi, t_en_iyi = float(oranlar[k]), float(izgara[k])
        ilk = int(np.argmax(uygun)) if bool(uygun.any()) else None
        if ilk is None:
            return float('inf'), en_iyi, t_en_iyi
        if ilk == 0:
            return float(izgara[0]), en_iyi, t_en_iyi
        lo, hi = float(izgara[ilk - 1]), float(izgara[ilk])
        for _ in range(SIZING_BISECTION_ITERS):
            orta = 0.5 * (lo + hi)
            if orta <= lo or orta >= hi:
                break
            if _ok(orta):
                hi = orta
            else:
                lo = orta
        return hi, en_iyi, t_en_iyi

    def _total_hoop_controlling_case(self, pressure: float, radius: float,
                                     names, cases, thickness: float,
                                     reference_thickness):
        """``thickness`` cidarında toplam-hoop oranı izinli/toplam en küçük
        olan senaryonun adı (2. tur Ş1). Toplam modeli
        ``_thickness_for_total_hoop_allowable`` ile AYNIDIR; eşitlikte ilk
        senaryo (``senaryo_tanim`` sırası) kazanır."""
        oranlar = [
            izinli / (self._evaluated_pressure_hoop(pressure, radius,
                                                    thickness)
                      + sigma_th * self._thermal_scale(thickness,
                                                       reference_thickness))
            for izinli, sigma_th, _y in cases]
        return names[int(np.argmin(oranlar))]

    def _size_chamber_wall(self, pressure: float, radius: float,
                           safety_factor: float, cases,
                           reference_thickness: Optional[float]) -> Dict:
        """Hazne cidarını BOYUTLANDIRIR — değerlendirmeyle aynı modelden.

        ``cases``: [(ad, derate_akma_Pa, ısıl_hoop_referansta_Pa), ...] —
        tek motorun ısıl senaryoları. Cidar HEPSİNİ birlikte sağlamalıdır
        (yayımlanan tek cidar her senaryoda değerlendirilir).

        1) Basınç-yalnız boyutlandırma (P5B1-08 akışı, değiştirilmedi):
           ısıl gerilme yoksa sonuç BİT-AYNIDIR.
        2) Isıl gerilme varsa (V3 yapi-sf): toplam hoop (basınç + kalınlıkla
           ölçeklenen ısıl) hedefe oturtulur. Hedef hiçbir kalınlıkta
           tutmuyorsa basınç-yalnız kalınlık AYNEN yayımlanır,
           ``sizing_feasible = False`` ve gerekçe adıyla yazılır (yeni bir
           cidar uydurulmaz).
        """
        sonuc = None
        for ad, yield_for_design, _sigma_th in cases:
            allowable_stress = yield_for_design / safety_factor
            min_thickness = pressure * radius / allowable_stress
            recommended_thickness = (min_thickness
                                     * MANUFACTURING_ALLOWANCE_FACTOR)
            sizing_stress_model = 'thin_wall'
            sizing_feasible = True
            sizing_infeasible_reason = None
            if recommended_thickness / radius >= THIN_WALL_T_OVER_R_LIMIT:
                sizing_stress_model = 'lame_thick_wall'
                S_rec = allowable_stress / MANUFACTURING_ALLOWANCE_FACTOR
                t_rec_lame = self._thickness_for_hoop_allowable(
                    pressure, radius, S_rec)
                t_min_lame = self._thickness_for_hoop_allowable(
                    pressure, radius, allowable_stress)
                if np.isfinite(t_rec_lame) and np.isfinite(t_min_lame):
                    recommended_thickness = float(t_rec_lame)
                    min_thickness = float(t_min_lame)
                else:
                    # Fail-closed: hiçbir kalınlık hedefi tutturamaz (Lame
                    # tepe hoop'u t → ∞ iken basınca asimptot yapar, yani
                    # ulaşılabilir en büyük SF = σ_akma/P'dir). Uydurma bir
                    # kalınlık yayımlamak yerine yetmezlik ADIYLA beyan
                    # edilir; emniyet katsayısı ÖLÇÜLMÜŞ değerdir.
                    sizing_feasible = False
                    erisilebilir = (yield_for_design / pressure
                                    if pressure > 0 else float('inf'))
                    sizing_infeasible_reason = (
                        'no wall thickness can reach the requested safety '
                        'factor at this pressure: the Lame peak hoop stress '
                        'tends to the internal pressure '
                        f'({pressure / 1e6:.1f} MPa) as the wall grows, so the '
                        'largest achievable hoop safety factor is '
                        f'yield/pressure = {erisilebilir:.3f} (requested '
                        f'{safety_factor * MANUFACTURING_ALLOWANCE_FACTOR:.3f}). '
                        'The thickness reported here is the thin-wall value '
                        'and does NOT meet the target — lower the pressure, '
                        'choose a stronger material, or accept a lower safety '
                        'factor.')
            aday = {
                'minimum_thickness': min_thickness,
                'recommended_thickness': recommended_thickness,
                'sizing_stress_model': sizing_stress_model,
                'sizing_feasible': sizing_feasible,
                'sizing_infeasible_reason': sizing_infeasible_reason,
                'sizing_controlling_case': ad,
            }
            if sonuc is None:
                sonuc = aday
            else:
                # Ortak cidar: en kalını yöneten; uygunluk HEPSİNİN birlikte
                # sağlanmasıdır.
                uygun = sonuc['sizing_feasible'] and sizing_feasible
                gerekce = [g for g in (sonuc['sizing_infeasible_reason'],
                                       sizing_infeasible_reason) if g]
                if recommended_thickness > sonuc['recommended_thickness']:
                    sonuc = aday
                sonuc['minimum_thickness'] = max(sonuc['minimum_thickness'],
                                                 min_thickness)
                sonuc['sizing_feasible'] = uygun
                sonuc['sizing_infeasible_reason'] = (
                    gerekce[0] if gerekce else None)
        # 2. tur Ş6: alan adı ``_model`` sonekini TAŞIMAZ — panelin kaynak
        # defteri (analysis_dock.js ``SRC_DECL_SUFFIX``) ``*_model``
        # metnini bir beyan sayıp değeri olmayan ('missing') bir satır
        # basıyordu. Değer makine kodudur: 'pressure_only' |
        # 'pressure_plus_thermal'.
        sonuc['sizing_load'] = 'pressure_only'
        sonuc['sizing_thermal_reference_thickness_mm'] = (
            reference_thickness * 1000.0
            if reference_thickness is not None else None)

        if not any(sigma_th > 0.0 for _ad, _y, sigma_th in cases):
            return sonuc

        # --- Isıl yük DAHİL (V3 yapi-sf) ----------------------------------
        sonuc['sizing_load'] = 'pressure_plus_thermal'
        adlar = [ad for ad, _y, _sigma_th in cases]
        rec_cases = [(y / safety_factor / MANUFACTURING_ALLOWANCE_FACTOR,
                      sigma_th, y) for _ad, y, sigma_th in cases]
        min_cases = [(y / safety_factor, sigma_th, y)
                     for _ad, y, sigma_th in cases]
        t_rec, en_iyi_rec, t_en_iyi_rec = (
            self._thickness_for_total_hoop_allowable(
                pressure, radius, rec_cases, reference_thickness))
        t_min, _en_iyi_min, _t_en_iyi_min = (
            self._thickness_for_total_hoop_allowable(
                pressure, radius, min_cases, reference_thickness))
        if np.isfinite(t_rec) and np.isfinite(t_min) and sonuc[
                'sizing_feasible']:
            sonuc['recommended_thickness'] = float(t_rec)
            sonuc['minimum_thickness'] = float(t_min)
            sonuc['sizing_stress_model'] = (
                'thin_wall' if t_rec / radius < THIN_WALL_T_OVER_R_LIMIT
                else 'lame_thick_wall')
            # 2. tur Ş1 (denetim U1): ortak cidarı BAĞLAYAN senaryo,
            # önerilen cidarda toplam-hoop izinli/toplam oranı en küçük
            # olandır. Eskiden alan yalnız basınç-yalnız birleştirmede
            # kuruluyor, bu dalda hiç güncellenmiyordu: (500/495),
            # (600/590), (700/690) K'de 'hot_soak' yazıyordu, oysa hedefi
            # bağlayan cooled_gradient'ti (ölçüm: denetim 7 Eki).
            sonuc['sizing_controlling_case'] = (
                self._total_hoop_controlling_case(
                    pressure, radius, adlar, rec_cases, float(t_rec),
                    reference_thickness))
            return sonuc
        # Ulaşılamaz: ulaşılabilir en büyük toplam-hoop SF'yi SINIRLAYAN
        # senaryo (en iyi tarama kalınlığında oranı en küçük olan).
        if t_en_iyi_rec is not None:
            sonuc['sizing_controlling_case'] = (
                self._total_hoop_controlling_case(
                    pressure, radius, adlar, rec_cases, t_en_iyi_rec,
                    reference_thickness))
        # Fail-closed: toplam hoop hedefi hiçbir kalınlıkta tutmuyor.
        # en_iyi_rec = max_t min_durum(izinli/toplam); ulaşılabilir en büyük
        # toplam-hoop emniyet katsayısı = hedef x pay x en_iyi_rec.
        erisilebilir_sf = (safety_factor * MANUFACTURING_ALLOWANCE_FACTOR
                           * en_iyi_rec)
        olcekleme = ('the through-wall temperature difference was scaled '
                     'with thickness (fixed heat flux, conduction drop '
                     'q*t/k) from the wall it was computed on '
                     f'({reference_thickness * 1000.0:.3f} mm), so a thicker '
                     'wall carries a larger thermal stress'
                     if reference_thickness is not None else
                     'the through-wall temperature difference was HELD at the '
                     'supplied value because the wall it was computed on is '
                     'not known; in reality it grows with thickness, so the '
                     'true achievable factor is lower')
        termal_gerekce = (
            'no wall thickness can reach the requested safety factor once '
            'the thermal hoop stress is included: sizing solves the SAME '
            'total hoop stress (pressure + thermal) that the published '
            'safety factor uses, and the largest total-hoop safety factor '
            f'any thickness reaches is about {erisilebilir_sf:.3f} '
            f'(requested {safety_factor * MANUFACTURING_ALLOWANCE_FACTOR:.3f}'
            f' including the manufacturing allowance); {olcekleme}. The '
            'thickness reported here is the PRESSURE-ONLY sized value and '
            'does NOT meet the target - the published safety factor is a '
            'measurement on that wall. Reduce the wall temperature (thermal '
            'protection / cooling), choose a stronger or more conductive '
            'material, or accept a lower safety factor.')
        onceki = sonuc['sizing_infeasible_reason']
        sonuc['sizing_feasible'] = False
        sonuc['sizing_infeasible_reason'] = (
            termal_gerekce if not onceki else onceki + ' ' + termal_gerekce)
        return sonuc

    def _analyze_chamber_wall(self, pressure: float, diameter: float,
                            length: float, mat_props: Dict,
                            derating: Optional[Dict] = None,
                            wall_delta_T: float = 0.0,
                            actual_thickness: Optional[float] = None,
                            design_safety_factor: Optional[float] = None,
                            thermal_reference_thickness: Optional[float] = None,
                            sizing: Optional[Dict] = None) -> Dict:
        """Hazne cidarı: BOYUTLANDIR (size) veya DOĞRULA (verify).

        DENETIM DUZELTMESI (2026-06): Artik TERMAL gerilme ve sicaklik
        DERATING'i dahil edilir. Onceki surum:
          - termal hoop gerilmeyi tamamen ihmal ediyordu,
          - oda-sicakligi yield'ini kullaniyordu (3000 K cidarda gercek-disi).
        Bu, SF'yi gercegin cok ustunde gosteriyordu. Toplam gerilme:
            sigma_total_hoop = sigma_pressure_hoop + sigma_thermal
        ve SF'ler DERATE EDILMIS yield'e gore hesaplanir.

        FİZİK DENETİMİ F003 (2026-07-25) — DÖNGÜSEL MANTIK KALDIRILDI.
        Eski akış şuydu:
            allowable = sigma_y_der / SF_mal
            t_rec     = 1.2 * P*r/allowable
            sigma     = P*r/t_rec
            SF        = sigma_y_der / sigma
        Bu cebirsel olarak SF = SF_mal * 1.2 verir; P, r, D, tasarım basınç
        faktörü ve malzeme dayanımı TAMAMEN sadeleşir. ÖLÇÜLDÜ (steel_4130,
        D=150 mm): Pc = 5 / 20 / 50 bar için SF hep 4.8000, hoop hep
        95.54 MPa; tasarım basınç faktörü 1.0 -> 1.5 değişince de SF sabit.
        Yani kullanıcıya "emniyet faktörü" diye kendi girdisi geri okunuyordu.

        Doğru yapı İKİ AYRI MODDUR (aynı desen bu depoda
        ``pressure_vessel.py::analyze`` içinde zaten doğru kurulmuştur;
        ASME BPVC VIII-1 UG-27 t hesabı + UG-98/MAWP mevcut-t geri hesabı):
          * ``actual_thickness is None`` -> **size**: t_req = P*r/(sigma_all)
            hesaplanır, imalat payıyla önerilir. Bu modda raporlanan emniyet
            faktörü TANIM GEREĞİ hedef SF x imalat payıdır — çıktıda
            ``safety_factor_is_tautological=True`` ile açıkça işaretlenir.
          * ``actual_thickness`` verilirse -> **verify**: gerilme KULLANICININ
            GERÇEK cidarından hesaplanır (sigma = P*r/t_gerçek veya kalın
            cidarda Lame) ve SF = sigma_y_der/sigma gerçek bir doğrulamadır;
            basınç, çap ve malzeme artık sadeleşmez.

        Ayrıca materials_db'deki ``safety_factor`` bir MALZEME ÖZELLİĞİ
        DEĞİL tasarım/otorite kararıdır; ``design_safety_factor`` argümanıyla
        çağırana taşındı (None -> geriye dönük uyum için malzeme kaydı).

        Args:
            derating: _derate_strength sonucu (None ise oda-sicakligi yield).
            wall_delta_T: Cidar boyunca termal gradyan [K] (>0 sicak ic yuz).
            actual_thickness: Kullanıcının GERÇEK cidar kalınlığı [m].
                Verilirse doğrulama modu; None ise boyutlandırma modu.
            design_safety_factor: Tasarım emniyet faktörü hedefi (çağıranın
                kararı). None -> mat_props['safety_factor'] (eski davranış).
            thermal_reference_thickness: ``wall_delta_T``'nin HESAPLANDIĞI
                cidar [m] (V3 yapi-sf). Boyutlandırma kipinde ısıl gradyan
                sabit akı varsayımıyla bu cidardan değerlendirilen cidara
                ölçeklenir; None ise gradyan verildiği değerde tutulur.
                Doğrulama kipinde ölçekleme YOKTUR (gradyan kullanıcının
                cidarına aittir).
            sizing: ``_size_chamber_wall`` sonucu (çağıran birden çok ısıl
                senaryoyu ORTAK cidarla boyutlandırdıysa). None ise bu
                senaryonun kendi boyutlandırması yapılır.
        """

        radius = diameter / 2
        yield_strength = mat_props['yield_strength']
        safety_factor = (float(design_safety_factor)
                         if design_safety_factor is not None
                         else mat_props['safety_factor'])

        # Derate edilmis yield (varsa). Termal degerlendirme bu deger uzerinden.
        if derating is not None:
            yield_for_design = derating['derated_yield_strength']
            derated_ultimate = derating['derated_ultimate_strength']
        else:
            yield_for_design = yield_strength
            derated_ultimate = mat_props['ultimate_strength']

        # Required wall thickness (thin wall approximation)
        # t = P*r / (sigma_allow). DERATE edilmis yield kullanilir -> daha kalin
        # cidar gerekebilir (konservatif).
        allowable_stress = yield_for_design / safety_factor

        # --- ÖH D15 / P5B1-08: BOYUTLANDIRMA ⟷ DOĞRULAMA AYNI MODELDEN ---
        # ÖLÇÜLDÜ (once_b1.json; steel_4130, D = 100 mm, SF hedefi 4,0,
        # imalat payı 1,2 → beklenen 4,80): 200 bar'da ulaşılan 4,0737,
        # 3000 bar'da 0,9585 — kalınlık ince-cidar formülünden seçilip
        # gerilme Lame'den hesaplanıyordu. Düzeltme ``_size_chamber_wall``
        # içinde (aynı akış, değiştirilmedi).
        # --- V3 yapi-sf (7 Eki 2026): ISIL YÜK DE AYNI MODELDEN ----------
        # Boyutlandırma artık değerlendirmenin toplam hoop gerilmesini
        # (basınç + ısıl) hedefe oturtur; bkz. modül başındaki not.
        thermal_ref_stress = self._thermal_hoop_stress(
            mat_props, wall_delta_T)['thermal_hoop_stress']
        if sizing is None:
            sizing = self._size_chamber_wall(
                pressure, radius, safety_factor,
                [('this_scenario', yield_for_design, thermal_ref_stress)],
                thermal_reference_thickness)
        min_thickness = sizing['minimum_thickness']
        recommended_thickness = sizing['recommended_thickness']
        sizing_stress_model = sizing['sizing_stress_model']
        sizing_feasible = sizing['sizing_feasible']
        sizing_infeasible_reason = sizing['sizing_infeasible_reason']

        # F003: gerilme hesabında KULLANILAN kalınlık — doğrulama modunda
        # kullanıcının gerçek cidarı, boyutlandırma modunda önerilen kalınlık.
        if actual_thickness is not None and float(actual_thickness) > 0:
            design_mode = 'verify'
            evaluated_thickness = float(actual_thickness)
        else:
            design_mode = 'size'
            evaluated_thickness = recommended_thickness

        # Ince-cidar varsayimi gecerlilik kontrolu (t/r < 0.1, yani D/t > 20)
        # -> Shigley "Mechanical Engineering Design", Roark's Formulas Ch.13.
        t_over_r = evaluated_thickness / radius if radius > 0 else float('inf')
        thin_wall_valid = bool(t_over_r < THIN_WALL_T_OVER_R_LIMIT)

        # Basinc kaynakli HOOP gerilme.
        #
        # DENETIM DUZELTMESI (2026-06): Ince-cidar formulu sigma=p*r/t (ic yaricap)
        # t/r >= 0.1 oldugunda GERCEK tepe gerilmeyi OLDUGUNDAN AZ gosterir
        # (Lame cozumune gore ~%5 (t/r=0.1) ... ~%11 (t/r=0.2) dusuk). Tehlikeyi az
        # gostermek YASAK -> t/r >= 0.1 ise basinc hoop'unu LAME kalin-cidar tepe
        # degeriyle (ic yuzey) hesaplariz; bu daima ince-cidar degerinden buyuktur
        # (konservatif). Kaynak: Lame (1833); Timoshenko & Goodier "Theory of
        # Elasticity" Art.28; Roark's Formulas for Stress & Strain 9th ed. Tablo 13.5
        # (kalin silindir, ic basinc): sigma_hoop(ic) = p*(b^2+a^2)/(b^2-a^2).
        thin_pressure_hoop = pressure * radius / evaluated_thickness
        a_inner = radius                              # ic yaricap (silindir ici)
        b_outer = radius + evaluated_thickness        # dis yaricap
        if b_outer > a_inner:
            lame_peak_hoop = pressure * (b_outer**2 + a_inner**2) / (b_outer**2 - a_inner**2)
        else:
            lame_peak_hoop = thin_pressure_hoop
        if not thin_wall_valid:
            # Kalin-cidar rejimi: konservatif olarak Lame tepe degerini kullan.
            pressure_hoop_stress = max(thin_pressure_hoop, lame_peak_hoop)
        else:
            pressure_hoop_stress = thin_pressure_hoop

        longitudinal_stress = pressure * radius / (2 * evaluated_thickness)

        # TERMAL hoop gerilme (radyal gradyan). delta_T<=0 ise 0.
        thermal = self._thermal_hoop_stress(mat_props, wall_delta_T)
        thermal_hoop_stress = thermal['thermal_hoop_stress']
        # V3 yapi-sf: boyutlandırma kipinde gradyan, hesaplandığı cidardan
        # DEĞERLENDİRİLEN cidara ölçeklenir (sabit akı, ΔT ∝ t) — böylece
        # boyutlandırmanın çözdüğü model ile burada yayımlanan sayı aynıdır.
        # Aynı cidarda katsayı tam 1,0'dır (sayı biti oynamaz). Doğrulama
        # kipinde gradyan kullanıcının cidarına aittir, ölçeklenmez.
        thermal_scale = (self._thermal_scale(evaluated_thickness,
                                             thermal_reference_thickness)
                         if design_mode == 'size' else 1.0)
        if thermal_scale != 1.0:
            thermal_hoop_stress = thermal_hoop_stress * thermal_scale

        # TOPLAM hoop gerilme = basinc + termal (dis yuzde ikisi de tensile,
        # konservatif olarak toplanir).
        hoop_stress = pressure_hoop_stress + thermal_hoop_stress

        # Von Mises esdeger gerilme (toplam hoop ile).
        # OPUS DENETIM DUZELTMESI (minor): kalin cidarda ic yuzeyde radyal
        # gerilme sigma_r = -p ihmal edilirse von Mises %5-17 DUSUK cikar
        # (non-konservatif yon). Kalin-cidar rejiminde 3 eksenli form kullanilir.
        if not thin_wall_valid:
            sigma_r = -pressure
            von_mises_stress = np.sqrt(0.5 * (
                (hoop_stress - longitudinal_stress) ** 2
                + (longitudinal_stress - sigma_r) ** 2
                + (sigma_r - hoop_stress) ** 2
            ))
        else:
            von_mises_stress = np.sqrt(
                hoop_stress**2 - hoop_stress * longitudinal_stress + longitudinal_stress**2
            )

        # Safety factors -> DERATE EDILMIS yield'e gore
        hoop_safety_factor = yield_for_design / hoop_stress if hoop_stress > 0 else float('inf')
        von_mises_safety_factor = yield_for_design / von_mises_stress if von_mises_stress > 0 else float('inf')

        # İKİ SF RAPORU (Dalga 0, 2026-07-14): basınç-yalnız (birincil yük)
        # ve basınç+termal (toplam). Termal gerilme İKİNCİL (deplasman
        # kontrollü) yüktür; ayrı raporlanması tasarımcıya hangi etkinin
        # domine ettiğini gösterir. safety_factor_total, mevcut
        # hoop_safety_factor ile aynıdır (geriye dönük uyum).
        safety_factor_pressure = (yield_for_design / pressure_hoop_stress
                                  if pressure_hoop_stress > 0 else float('inf'))
        safety_factor_total = hoop_safety_factor

        # Basınç-YALNIZ von Mises (birincil yük). Termal terim çıkarılınca
        # aynı 2B/3B form uygulanır — F026 gereği emniyet sepetinde birincil
        # yük kullanılabilsin diye ayrıca raporlanır.
        if not thin_wall_valid:
            sigma_r = -pressure
            von_mises_pressure = np.sqrt(0.5 * (
                (pressure_hoop_stress - longitudinal_stress) ** 2
                + (longitudinal_stress - sigma_r) ** 2
                + (sigma_r - pressure_hoop_stress) ** 2))
        else:
            von_mises_pressure = np.sqrt(
                pressure_hoop_stress**2
                - pressure_hoop_stress * longitudinal_stress
                + longitudinal_stress**2)
        von_mises_sf_pressure = (yield_for_design / von_mises_pressure
                                 if von_mises_pressure > 0 else float('inf'))

        # --- ASME gerilme SINIFLANDIRMASI (F026, 2026-07-25) --------------
        # Basınç hoop'u BİRİNCİL (P, yük kontrollü); termal gradyan gerilmesi
        # İKİNCİL (Q, deplasman kontrollü) gerilmedir. İkisini toplayıp AKMA
        # dayanımıyla oranlamak yanlıştır: ikincil gerilme akma üstünde
        # plastik uyumla (shakedown) kendini sınırlar, kırılma yaratmaz.
        # ÖLÇÜLDÜ (rejeneratif cidar, T_ic=800 K, T_dis=500 K, Pc=50 bar,
        # steel_4130, D=150 mm): P=70.7 MPa, Q=505.5 MPa, P+Q=576.2 MPa ->
        # eski tek kriter SF=0.556 ve status='UNSAFE' veriyordu. ASME
        # kriteri: Sm=243.3 MPa; P/Sm=0.291 (KABUL), (P+Q)/3Sm=0.789
        # (shakedown SAĞLANIYOR). Yani tamamen normal bir rejeneratif hazne
        # yanlış şekilde UNSAFE ilan ediliyordu.
        # Kaynak: ASME BPVC VIII-2 (2021) Part 5.2.2 (gerilme sınıflandırma)
        # ve 5.5.6; ASME III NB-3222.2 (3Sm shakedown kuralı).
        # NOT: termal tepe çekme DIŞ yüzeyde, Lame basınç tepesi İÇ
        # yüzeydedir — toplama konservatiftir ama eş-konumlu değildir.
        Sm = min(derated_ultimate / ASME_SM_UTS_DIVISOR,
                 yield_for_design / ASME_SM_YIELD_DIVISOR)
        primary_ratio = pressure_hoop_stress / Sm if Sm > 0 else float('inf')
        shakedown_ratio = (hoop_stress / (ASME_SHAKEDOWN_MULTIPLIER * Sm)
                           if Sm > 0 else float('inf'))

        return {
            'minimum_thickness': min_thickness * 1000,  # mm
            'recommended_thickness': recommended_thickness * 1000,  # mm
            # F003: hangi modda çalışıldı ve gerilme hangi kalınlıktan çıktı
            'design_mode': design_mode,                 # 'size' | 'verify'
            'wall_thickness_used_mm': evaluated_thickness * 1000,
            'design_safety_factor_target': safety_factor,
            'manufacturing_allowance_factor': MANUFACTURING_ALLOWANCE_FACTOR,
            # v2.6.26 — SABİT ÇIKTI BEYANI: bu çarpan bu tasarımdan
            # hesaplanmaz, modül sabitidir (structural_analysis.py:35).
            'manufacturing_allowance_factor_basis': (
                'manufacturing allowance constant (structural_analysis.py '
                'MANUFACTURING_ALLOWANCE_FACTOR): recommended thickness = '
                'minimum thickness x this factor. It is NOT computed from '
                'this design and it is NOT a safety factor - it is stock '
                'tolerance, machining and corrosion allowance taken from '
                'general tube/plate manufacturing practice (ASME BPVC VIII-1 '
                'UG-25 corrosion-allowance pattern).'),
            'safety_factor_is_tautological': bool(design_mode == 'size'),
            # --- P14H1-C4 (ÖH Z4): BAYRAĞIN TANIMI ALANIN YANINDA ---------
            # Ölçülen belirsizlik: gerçek hibrit koşumunda ``design_mode =
            # 'size'``, ``wall_thickness_used_mm == recommended_thickness``
            # BİREBİR ve ``safety_factor_is_tautological = True`` iken
            # yayımlanan ``hoop_safety_factor`` 1,7173'tü — hedef 4,0
            # DEĞİL. Yani bayrak "sayı hedefin kendisidir" demiyor;
            # "cidarı HRMA seçti" diyor. İki cümle aynı şey değildir ve
            # tüketiciler (ihraç, panel) birincisini varsayıyordu.
            # Kesin ölçüt ayrı bir alanda ve tek anlamlı:
            'safety_factor_is_tautological_basis': (
                'TRUE means: the evaluated wall was chosen by HRMA to meet '
                'the design safety factor target, so this section was not '
                'checked against a thickness you supplied. It does NOT by '
                'itself mean the published safety factor equals the target: '
                'sizing puts the TOTAL hoop stress (pressure + thermal, at '
                'the derated strength) on the target; when no thickness can '
                'reach it, sizing_feasible is false and the published factor '
                'is a measurement below the target. '
                'Use safety_factor_reads_back_target for that question.'),
            # Sayının hedefin geri okunması OLUP OLMADIĞI (kesin ölçüt):
            # boyutlandırılmış bir kesitin katsayısı hedefin ALTINA
            # düşmüşse, boyutlandırmanın kapsamadığı bir yük onu aşağı
            # çekmiştir; o sayı bir ÖLÇÜMDÜR.
            'safety_factor_reads_back_target': bool(
                design_mode == 'size'
                and hoop_safety_factor >= safety_factor * (1.0 - 1e-9)),
            # v2.6.27 (A3) — DEĞERLENDİRİLEN CİDARIN KAYNAĞI ADIYLA YAZILIR.
            # ``design_mode`` bu bilgiyi zaten taşıyordu ama okuyucunun onu
            # "kim verdi" sorusuna çevirmesi gerekiyordu; çağıran katmanın
            # (app.py) hüküm kapısı bu alanı doğrudan okur.
            'wall_thickness_source': ('user_supplied' if design_mode == 'verify'
                                      else 'sized_by_hrma'),
            # ÖH D15 / P5B1-08: künye artık HANGİ MODELDEN boyutlandırıldığını
            # ve hedefin tutturulup tutturulmadığını söyler. Eski metin
            # kalın-cidar rejiminde YALANDI ("SF = target x allowance"
            # derken sayı 3,4556 idi).
            'safety_factor_basis': (
                ('no wall thickness was supplied by the user, so HRMA sized '
                 'the wall with the SAME stress model used to evaluate it '
                 f'({sizing_stress_model}); the resulting SF reads back '
                 'target_SF x manufacturing allowance and is NOT an '
                 'independent verification'
                 if sizing_feasible else
                 # 2. tur Ş6: sabit metin (EN = TR sözlükte). Eski metin
                 # "at this pressure" diyordu; ulaşılamazlık ısıl yükten
                 # de gelebilir (sizing_load).
                 'no wall thickness was supplied by the user and the '
                 'requested safety factor is UNREACHABLE for the sizing '
                 'load (see sizing_load and sizing_infeasible_reason), so '
                 'the reported thickness does not meet the target; the '
                 'safety factor below is a MEASUREMENT, not a read-back')
                if design_mode == 'size' else
                'verified against user-supplied wall thickness'),
            # Boyutlandırmanın kullandığı gerilme modeli — değerlendirmede
            # kullanılan ``pressure_hoop_model`` ile AYNI olmak zorundadır.
            'sizing_stress_model': (sizing_stress_model
                                    if design_mode == 'size' else None),
            'sizing_feasible': bool(sizing_feasible),
            'sizing_infeasible_reason': sizing_infeasible_reason,
            # V3 yapi-sf: boyutlandırmanın hangi YÜKÜ hedefe oturttuğu
            # ('pressure_only' ısıl gerilme yokken; aksi hâlde
            # 'pressure_plus_thermal') ve ortak cidarı hangi ısıl senaryonun
            # yönettiği. ``sizing_feasible`` gibi iki kipte de yayımlanır:
            # doğrulama kipinde ÖNERİLEN cidarın (minimum/recommended)
            # künyesidir.
            'sizing_load': sizing.get('sizing_load'),
            'sizing_controlling_case': sizing.get('sizing_controlling_case'),
            # Isıl gradyanın hesaplandığı cidar ve değerlendirilen cidardaki
            # gradyan (sabit akı ölçeklemesi; doğrulama kipinde katsayı 1).
            'thermal_reference_wall_thickness_mm': (
                thermal_reference_thickness * 1000.0
                if thermal_reference_thickness is not None else None),
            # (Ölçek katsayısının kendisi yayımlanmaz: hibrit sabit
            # noktasında tanım gereği 1,0'dır ve girdiden bağımsız bir
            # "sabit çıktı" gibi görünürdü — test_field_wiring_layer_b.
            # Bilgi iki alandan geri okunur: ΔT_değerlendirilen/ΔT_ref.)
            'wall_delta_T_at_evaluated_wall_K': (
                thermal['delta_T'] * thermal_scale),
            # 2. tur Ş6 (denetim U5): künye DEĞERİ OLAN alana bağlandı.
            # Eski ad (``thermal_gradient_scale_basis``) değeri kaldırılmış
            # bir alanı tarif ediyordu; panel defteri onu 'missing' çipiyle
            # basıyordu. Düzlem duvar iletimi: Sutton & Biblarz 9. baskı
            # Denk. (8–13), s. 311 (Q/A = −κ·dT/dL ≈ −κ·ΔT/t_w).
            'wall_delta_T_at_evaluated_wall_K_basis': (
                'The through-wall temperature difference was computed on the '
                'wall named in thermal_reference_wall_thickness_mm. In size '
                'mode it is scaled to the evaluated wall by the thickness '
                'ratio (fixed heat flux, planar conduction drop q*t/k), so '
                'the sized wall and its published thermal stress come from '
                'the same model (equal values mean the same wall). '
                'With no reference wall the difference is held at the '
                'supplied value. In verify mode the difference belongs to '
                'the supplied wall and is not scaled.'),
            # F026: ASME birincil / birincil+ikincil sınıflandırması
            'asme_Sm_MPa': Sm / 1e6,
            'asme_primary_membrane_ratio': primary_ratio,      # P/Sm  (<=1 kabul)
            'asme_shakedown_ratio': shakedown_ratio,           # (P+Q)/3Sm (<=1 kabul)
            'asme_primary_ok': bool(primary_ratio <= 1.0),
            'asme_shakedown_ok': bool(shakedown_ratio <= 1.0),
            'von_mises_safety_factor_pressure': von_mises_sf_pressure,
            'von_mises_stress_pressure': von_mises_pressure / 1e6,  # MPa
            'hoop_stress': hoop_stress / 1e6,  # MPa (TOPLAM: basinc+termal)
            'pressure_hoop_stress': pressure_hoop_stress / 1e6,  # MPa (sadece basinc; Lame ise tepe)
            'thin_wall_pressure_hoop_MPa': thin_pressure_hoop / 1e6,  # MPa (referans: ince-cidar p*r/t)
            'lame_peak_pressure_hoop_MPa': lame_peak_hoop / 1e6,  # MPa (kalin-cidar Lame tepe, ic yuzey)
            'pressure_hoop_model': 'lame_thick_wall' if not thin_wall_valid else 'thin_wall',
            'thermal_hoop_stress': thermal_hoop_stress / 1e6,  # MPa (sadece termal)
            'longitudinal_stress': longitudinal_stress / 1e6,  # MPa
            'von_mises_stress': von_mises_stress / 1e6,  # MPa
            'hoop_safety_factor': hoop_safety_factor,
            'von_mises_safety_factor': von_mises_safety_factor,
            # İki SF raporu (Dalga 0): basınç-yalnız ve basınç+termal
            'safety_factor_pressure': safety_factor_pressure,
            'safety_factor_total': safety_factor_total,
            'allowable_stress': allowable_stress / 1e6,  # MPa (derate edilmis)
            'yield_strength_used_MPa': yield_for_design / 1e6,  # derate edilmis yield
            'thin_wall_ratio_t_over_r': t_over_r,
            'thin_wall_valid': thin_wall_valid,
            'diameter': diameter * 1000,  # mm
            'length': length * 1000  # mm
        }
    
    def _analyze_nozzle_structure(self, pressure: float, throat_diameter: float,
                                chamber_diameter: float, mat_props: Dict, nozzle_type: str,
                                derating: Optional[Dict] = None,
                                design_safety_factor: Optional[float] = None,
                                actual_throat_thickness: Optional[float] = None) -> Dict:
        """Boğaz bölgesi yapısal kontrolü (boyutlandır / doğrula).

        FİZİK DENETİMİ F027 (2026-07-25) — İKİ KUSUR GİDERİLDİ:
        (1) TAUTOLOJİ: effective_stress = SCF*P*r_t/(min_t*SCF) = allowable
            olduğundan safety_factor = yield/allowable = SF_mal her zaman.
            ÖLÇÜLDÜ: Pc 5..500 bar ve tüm malzemeler için SF = 4.0000 sabit.
            Bu bir doğrulama değil, girdinin geri okunmasıdır — hazne
            cidarıyla (F003) aynı size/verify ayrımı uygulandı.
        (2) DERATING YOK: boğaz motorun EN SICAK istasyonudur (Bartz tepe ısı
            akısı orada) ama yield ODA SICAKLIĞI değeriyle alınıyordu; aynı
            çağrıda hazne cidarı derate ediliyordu. ÖLÇÜLDÜ: T_c=3200 K'de
            hazne retention=0.537 (yield 460 -> 247 MPa) iken boğaz izin
            verilen gerilmesi 1.86 kat FAZLA gösteriliyordu. Boğaz artık aynı
            _derate_strength çıktısını kullanır.
        Kaynak: ince-cidar hoop — Sutton & Biblarz "Rocket Propulsion
        Elements" Ch. 8 / Roark's Ch. 13; derating — MMPDS / MIL-HDBK-5
        Fig. 2.3.1.1.1.

        NOT (kapsam dışı, beyan): boğaz termal gradyan gerilmesi (rejeneratif
        boğazda genellikle baskın yük) bu fonksiyonda hesaplanmaz.
        """

        throat_radius = throat_diameter / 2
        chamber_radius = chamber_diameter / 2
        yield_strength = mat_props['yield_strength']
        safety_factor = (float(design_safety_factor)
                         if design_safety_factor is not None
                         else mat_props['safety_factor'])
        if derating is not None:
            yield_for_design = derating['derated_yield_strength']
        else:
            yield_for_design = yield_strength

        # Throat section is critical (smallest diameter, highest stress)
        allowable_stress = yield_for_design / safety_factor
        min_throat_thickness = pressure * throat_radius / allowable_stress

        # Boğaz geçiş bölgesi gerilme yığılması. 2.0 (konik) / 1.5 (çan)
        # değerleri BEYAN EDİLEN tasarım kabulüdür: iç basınçlı kabuk geçiş
        # bölgesi için tipik K_t bandı (1.5-3.0) içindedir, ancak gerçek
        # geometriden (yakınsak koni açısı, boğaz fileto yarıçapı R_c/R_t)
        # türetilmemiştir — Peterson'da "konik nozul boğazı = 2.0" diye bir
        # tablo girdisi yoktur (F182). Doğrulama modunda bu katsayı SF'yi
        # doğrudan etkiler; geometriden hesaplanan K_t ile değiştirilmelidir.
        stress_concentration_factor = 2.0 if nozzle_type == 'conical' else 1.5

        # Required thickness considering stress concentration
        required_throat_thickness = min_throat_thickness * stress_concentration_factor

        # Effective (peak) stress at throat.
        # DUZELTME (2026-07-16): Eski kod effective_stress'u min_throat_thickness
        # (yigilma payi OLMADAN) uzerinden hesaplayip SCF ile carpiyordu:
        #     effective_stress = P*r_t/min_t*SCF = allowable*SCF
        # burada P ve r_t TAMAMEN sadelesiyor -> bogaz gerilmesi ve emniyet
        # faktoru (=SF_mat/SCF) gercek basinc/geometriden BAGIMSIZ bir SABIT
        # cikiyordu (totoloji). Dogrusu: ONERILEN (SCF payli) kalinliktaki gercek
        # tepe gerilmeyi, ince-cidar hoop'una (P*r_t/t) yigilma faktorunu
        # uygulayarak hesapla -> boylece raporlanan gerilme ile kullanilan
        # kalinlik TUTARLI olur ve SCF yalnizca BIR kez sayilir. Sized bogaz
        # icin sonuc allowable'a esittir, dolayisiyla SF = SF_mat (malzeme emniyet
        # faktoru) olarak dogru raporlanir. Kaynak: Peterson "Stress Concentration
        # Factors"; ince-cidar hoop Sutton & Biblarz / Roark's Ch.13.
        # F027: gerilme, DEĞERLENDİRİLEN kalınlıktan hesaplanır. Doğrulama
        # modunda bu kullanıcının gerçek boğaz cidarıdır; boyutlandırma
        # modunda önerilen (SCF paylı) kalınlıktır ve o durumda sonuç tanım
        # gereği allowable'a eşittir -> tautolojik olarak işaretlenir.
        if (actual_throat_thickness is not None
                and float(actual_throat_thickness) > 0):
            design_mode = 'verify'
            evaluated_thickness = float(actual_throat_thickness)
        else:
            design_mode = 'size'
            evaluated_thickness = required_throat_thickness

        if evaluated_thickness > 0:
            effective_stress = (stress_concentration_factor * pressure * throat_radius
                                / evaluated_thickness)
        else:
            effective_stress = float('inf')

        # Nozzle wall thickness variation
        chamber_thickness = pressure * chamber_radius / allowable_stress

        return {
            'throat_diameter': throat_diameter * 1000,  # mm
            'min_throat_thickness': min_throat_thickness * 1000,  # mm
            'required_throat_thickness': required_throat_thickness * 1000,  # mm
            'throat_thickness_used_mm': evaluated_thickness * 1000,
            'design_mode': design_mode,                 # 'size' | 'verify'
            'chamber_thickness': chamber_thickness * 1000,  # mm
            'stress_concentration_factor': stress_concentration_factor,
            'stress_concentration_basis': ('declared design assumption, not '
                                           'derived from throat fillet geometry'),
            'throat_stress': effective_stress / 1e6,  # MPa
            # F027: derate edilmiş akmaya göre (hazne cidarıyla AYNI taban)
            'safety_factor': (yield_for_design / effective_stress
                              if effective_stress > 0 else float('inf')),
            'yield_strength_used_MPa': yield_for_design / 1e6,
            'safety_factor_is_tautological': bool(design_mode == 'size'),
            # P14H1-C4: bayrağın kesin ölçütü (hazne bloğuyla AYNI tanım).
            'safety_factor_reads_back_target': bool(
                design_mode == 'size'
                and effective_stress > 0
                and (yield_for_design / effective_stress)
                >= safety_factor * (1.0 - 1e-9)),
            'nozzle_type': nozzle_type
        }
    
    def _analyze_end_caps(self, pressure: float, diameter: float, mat_props: Dict,
                          derating: Optional[Dict] = None,
                          design_safety_factor: Optional[float] = None,
                          actual_thickness: Optional[float] = None) -> Dict:
        """Kapak (baş / enjektör tarafı) kalınlığı ve gerçek kapak gerilmesi.

        FİZİK DENETİMİ F004 (2026-07-25) — SİLİNDİR FORMÜLÜ DÜZ PLAKADAN
        KALDIRILDI. Eski kod kapak emniyet faktörünü şöyle üretiyordu:

            bolt_circle_stress = P * (D_civata/2) / t_duz
            head_safety_factor = allowable / bolt_circle_stress

        ``P*R/t`` bir SİLİNDİR ince-cidar hoop bağıntısıdır; düz dairesel
        kapağa, üstelik cıvata dairesi yarıçapıyla uygulanmasının Roark,
        Shigley veya ASME'de karşılığı YOKTUR. ÖLÇÜLDÜ (steel_4130,
        D=150 mm): gerçek kapak SF'si her basınçta 4.00 iken kod 5 bar'da
        10.28 (2.57x FAZLA), 150 bar'da 1.878, 300 bar'da 1.328 (3.01x AZ —
        tehlikeli yön) veriyordu; sqrt(allowable/P) gibi ölçekleniyordu.
        Daha kötüsü Pc >= 50 bar'da bu uydurma sayı minimum_safety_factor'ü
        yönetiyor, Pc >= 150 bar'da tüm motoru UNSAFE ilan ediyordu.

        Doğrusu, kapağın KENDİ eğilme/membran gerilmesidir:
          * Düz dairesel kapak (üniform basınç, kenar basit mesnetli):
                sigma_max = 3*P*a^2*(3+nu) / (8*t^2)
            Kaynak: Roark's Formulas for Stress and Strain, Tablo 11.2
            (uniform yüklü dairesel plaka). Bu kalınlık ASME BPVC VIII-1
            UG-34 cıvatalı düz kapak formu t = d*sqrt(C*P/(S*E)), C=0.30 ile
            %1 içinde örtüşür (çapraz kontrol olarak da raporlanır).
          * 2:1 elipsoidal (dished) kapak: ASME UG-32(d) denkleminin tersi
                sigma = P*(D/t + 0.2) / (2*E)
        Emniyet faktörü ÖNERİLEN kapak tipinin gerilmesinden ve DİĞER
        istasyonlarla AYNI referans dayanımdan (derate edilmiş akma)
        hesaplanır — eski sürüm allowable (=yield/SF) tabanlıydı, bu yüzden
        emniyet sepetinde tanım gereği SF_mal kat daha küçük çıkıp min()'i
        neredeyse her zaman kazanıyordu (bulgu F073).

        Args:
            derating: _derate_strength sonucu (None -> oda sıcaklığı).
            design_safety_factor: tasarım SF hedefi (None -> malzeme kaydı).
            actual_thickness: gerçek kapak kalınlığı [m]; verilirse doğrulama
                modu (F003 ile aynı size/verify ayrımı).
        """

        radius = diameter / 2
        yield_strength = mat_props['yield_strength']
        safety_factor = (float(design_safety_factor)
                         if design_safety_factor is not None
                         else mat_props['safety_factor'])
        if derating is not None:
            yield_for_design = derating['derated_yield_strength']
        else:
            yield_for_design = yield_strength

        poisson_ratio = mat_props['poisson_ratio']
        allowable_stress = yield_for_design / safety_factor

        # Flat head thickness
        flat_head_thickness = radius * np.sqrt((3 * pressure * (3 + poisson_ratio)) / (8 * allowable_stress))
        
        # Dished head thickness — ASME BPVC VIII-1 UG-32(d): 2:1 yari-elipsoidal baslik.
        # DUZELTME (2026-07-16): Eski formul pressure*radius/(2*allowable) = P*D/(4S)
        # idi; bu bir YARIMKURE (hemispherical) kalinligidir, 2:1 elipsoidal DEGIL.
        # 2:1 elipsoidal baslik silindir govdeyle yaklasik ayni kalinligi gerektirir
        # (P*D/(2S)), yarisini degil -> eski deger belirtilen baslik tipi icin 2x
        # ince, non-konservatif. Dogru ASME UG-32(d) formulu:
        #     t = P*D / (2*S*E - 0.2*P),  K = 1.0 (2:1 orani icin)
        # D = ic cap (= diameter), S = allowable_stress, E = kaynak verimi
        # (1.0; dikissiz / tam-radyografi varsayimi).
        joint_efficiency = 1.0
        dished_head_thickness = (pressure * diameter
                                 / (2 * allowable_stress * joint_efficiency - 0.2 * pressure))

        # ASME BPVC VIII-1 UG-34 çapraz kontrolü (cıvatalı düz kapak):
        #     t = d * sqrt(C*P/(S*E)),  C = 0.30
        # İkinci terim (1.9*W*h_G/(S*E*d^3), cıvata momenti) BURADA YOKTUR:
        # flanş cıvata yükü W ve conta kolu h_G bu fonksiyonun girdisi değil.
        # Terim atlandığı için UG-34 değeri gerçek cıvatalı kapaktan İNCE
        # çıkar; bu yüzden yalnız çapraz kontrol olarak raporlanır, kalınlık
        # önerisi Roark plaka eğilmesinden verilir (ikisi %1 içinde örtüşür).
        UG34_C_BOLTED_FLAT = 0.30
        ug34_flat_thickness = diameter * np.sqrt(
            UG34_C_BOLTED_FLAT * pressure / (allowable_stress * joint_efficiency))

        recommended_type = ('dished' if dished_head_thickness < flat_head_thickness
                            else 'flat')

        # Değerlendirilen kapak kalınlığı: doğrulama modunda kullanıcının
        # gerçek kapağı, boyutlandırma modunda önerilen tipin kalınlığı.
        sized_thickness = (dished_head_thickness if recommended_type == 'dished'
                           else flat_head_thickness)
        if actual_thickness is not None and float(actual_thickness) > 0:
            design_mode = 'verify'
            evaluated_thickness = float(actual_thickness)
        else:
            design_mode = 'size'
            evaluated_thickness = sized_thickness

        # --- ÖH D32 / OH-FT-06: DEĞERLENDİRİLEN KALINLIK KİMİN? ----------
        # ÖLÇÜLDÜ (taban ``dd1dcddc``, ``docs/scofield/raw/OH/D32/
        # yapisal-sistem/a1/once.json`` bölüm A/B/C): blok HÜKMÜ kapak
        # TİPİNE GÖRE adıyla yayımlıyor (``head_safety_factor_by_type``,
        # ``head_stress_by_type_MPa`` ve künyesi
        # ``head_safety_factor_by_type_basis``) ama KALINLIĞI tek bir
        # ``head_thickness_used_mm`` ile yayımlıyordu: o sayının hangi kapak
        # tipine ait olduğunu söyleyen alan YOKTU (``tip_alani_var =
        # false``) ve sayının kendi künyesi de YOKTU (``kunye_alani_var =
        # false``) — oysa aynı modülün kütle bloğundaki üç kardeş sayının
        # üçü de künyesiyle geliyor (``chamber_weight_basis``,
        # ``nozzle_weight_basis``, ``end_caps_weight_basis``). Ölçülen sonuç:
        #
        #   /calculate_solid (Ø100 mm / 40 bar / çelik)
        #       head_thickness_used_mm            =  3,008744 mm  (dished)
        #       ihraç katmanının imalata soktuğu  = 15,180585 mm  (FLAT)
        #       oran                              =  5,045490
        #
        # ve doğrulama kipinde ``head_thickness_used_mm = 8,0`` iki
        # boyutlandırma çıktısının HİÇBİRİNE eşit değildir (flat 9,949874 /
        # dished 1,605136), yani tüketici tipi değerlerden de çıkaramaz.
        # 'used' adı "imalata giden kalınlık" diye okunuyor; gerçekte
        # DEĞERLENDİRME kalınlığıdır. Sayı DOĞRUDUR ve değişmez; eski ad
        # geriye dönük uyum için kalır, ne anlama geldiği artık MAKİNE-OKUR
        # biçimde (tip + künye + alan adı eşlemesi) yayımlanır.
        head_thickness_used_type = ('user_supplied' if design_mode == 'verify'
                                    else recommended_type)

        # GERÇEK kapak gerilmesi (önerilen tipe göre):
        if recommended_type == 'flat':
            # Roark Tablo 11.2 — üniform yüklü dairesel plaka, basit mesnet:
            #     sigma_max = 3*P*a^2*(3+nu)/(8*t^2)
            head_stress = (3.0 * pressure * radius**2 * (3.0 + poisson_ratio)
                           / (8.0 * evaluated_thickness**2))
            stress_model = ('flat circular plate bending, simply supported '
                            '(Roark Table 11.2)')
        else:
            # ASME UG-32(d) 2:1 elipsoidal başlık denkleminin tersi:
            #     t = P*D/(2SE - 0.2P)  ->  sigma = P*(D/t + 0.2)/(2E)
            head_stress = (pressure * (diameter / evaluated_thickness + 0.2)
                           / (2.0 * joint_efficiency))
            stress_model = ('2:1 ellipsoidal head membrane, inverse of '
                            'ASME VIII-1 UG-32(d)')

        # Bolt circle geometrisi (yalnız yerleşim bilgisi). Eski sürümdeki
        # 'bolt_circle_stress' bir SİLİNDİR hoop formülüydü ve kapak emniyet
        # faktörünü yönetiyordu — kaldırıldı; alan geriye dönük uyumluluk
        # için kapağın GERÇEK gerilmesiyle doldurulur.
        bolt_circle_diameter = diameter + 0.05  # 50 mm larger than chamber

        head_safety_factor = (yield_for_design / head_stress
                              if head_stress > 0 else float('inf'))

        # --- ÖH D18 / P9B1-17: HER TİP İÇİN AYRI HÜKÜM -------------------
        # ÖLÇÜLDÜ (taban 9071a64): bu blok ``head_safety_factor``ı YALNIZ
        # ÖNERİLEN tip için hesaplıyordu. İhraç katmanı
        # (``hrma/export/cad_visualization.py::_front_cap_design``) katıyı
        # DÜZ kapak olarak modelliyor ve ``flat_head_thickness``ı çiziyor;
        # öneri 'dished' olduğunda çizilen parçanın emniyet katsayısı
        # HİÇBİR YERDE yayımlanmıyordu — okuyucu, çizilenden BAŞKA bir
        # parçanın hükmünü görüyordu.
        #
        # İki formül de zaten burada. Değerlendirilen kalınlıkta İKİ tipin
        # de gerilmesi ve emniyet katsayısı yayımlanır; hangi tipin
        # üretileceğine karar veren katman kendi parçasının hükmünü ADIYLA
        # okuyabilir. Hüküm uydurulmaz: ikisi de aynı referans dayanımdan
        # (derate edilmiş akma) ve aynı ``evaluated_thickness``ten gelir.
        _flat_stress = (3.0 * pressure * radius**2 * (3.0 + poisson_ratio)
                        / (8.0 * evaluated_thickness**2))
        _dished_stress = (pressure * (diameter / evaluated_thickness + 0.2)
                          / (2.0 * joint_efficiency))
        _sf_by_type = {
            'flat': (yield_for_design / _flat_stress
                     if _flat_stress > 0 else float('inf')),
            'dished': (yield_for_design / _dished_stress
                       if _dished_stress > 0 else float('inf')),
        }

        return {
            'flat_head_thickness': flat_head_thickness * 1000,  # mm
            'dished_head_thickness': dished_head_thickness * 1000,  # mm
            'asme_ug34_flat_head_thickness': ug34_flat_thickness * 1000,  # mm
            'recommended_type': recommended_type,
            'design_mode': design_mode,                    # 'size' | 'verify'
            'head_thickness_used_mm': evaluated_thickness * 1000,
            # ÖH D32 / OH-FT-06 — DEĞERLENDİRME KALINLIĞININ KİMLİĞİ.
            # 'dished' | 'flat' (boyutlandırma kipi, = recommended_type) ya
            # da 'user_supplied' (doğrulama kipi: sayı çağıranın gerçek
            # kapağıdır ve iki boyutlandırma çıktısının hiçbirine eşit
            # olmak zorunda değildir).
            'head_thickness_used_type': head_thickness_used_type,
            # Tipe göre KALINLIK ALANININ ADI. Sayı BURAYA KOPYALANMAZ
            # (tek kaynak: ``flat_head_thickness`` / ``dished_head_
            # thickness``); yayımlanan şey yalnızca eşlemenin kendisidir,
            # böylece kendi tipini bilen bir tüketici kalınlığını ADIYLA
            # okur — hükmü ``head_safety_factor_by_type[tip]`` ile ADIYLA
            # okuduğu gibi.
            'head_thickness_field_by_type': {
                'flat': 'flat_head_thickness',
                'dished': 'dished_head_thickness',
            },
            'head_thickness_used_basis': (
                'head_thickness_used_mm is the thickness at which THIS '
                'block evaluated the head stress and safety factor; it is '
                'NOT a statement about which head thickness goes to '
                'manufacturing. The legacy field name says "used"; read it '
                'as "evaluated". In size mode it is the sized thickness of '
                'recommended_type, in verify mode it is the actual '
                'thickness supplied by the caller and then it equals '
                'neither sizing output; head_thickness_used_type names '
                'which of the two it is ("flat", "dished" or '
                '"user_supplied"). A layer that draws, exports or '
                'manufactures a specific head type must take that type '
                'thickness by name through '
                'head_thickness_field_by_type[type] - the CAD/STEP export '
                'models a FLAT head and therefore takes '
                'flat_head_thickness, which is a different quantity from '
                'head_thickness_used_mm whenever recommended_type is '
                '"dished" - and must quote head_safety_factor_by_type['
                'type] for the verdict of that same part.'),
            'bolt_circle_diameter': bolt_circle_diameter * 1000,  # mm
            'head_stress': head_stress / 1e6,              # MPa (GERÇEK kapak gerilmesi)
            # Geriye dönük alan adı; artık silindir hoop'u DEĞİL, kapağın
            # kendi gerilmesi (bkz. F004).
            'bolt_circle_stress': head_stress / 1e6,       # MPa
            'head_stress_model': stress_model,
            'head_safety_factor': head_safety_factor,
            # ÖH D18 / P9B1-17: değerlendirilen kalınlıkta HER İKİ kapak
            # tipinin gerilmesi ve emniyet katsayısı. ``head_safety_factor``
            # bunlardan ``recommended_type``a karşılık gelenidir; imalatta
            # başka bir tip çiziliyorsa (ihraç katmanı DÜZ kapak modelliyor)
            # o tipin hükmü buradan okunur, ötekinden ödünç alınmaz.
            'head_stress_by_type_MPa': {
                'flat': _flat_stress / 1e6,
                'dished': _dished_stress / 1e6,
            },
            'head_safety_factor_by_type': dict(_sf_by_type),
            'head_safety_factor_by_type_basis': (
                'Both verdicts are evaluated at head_thickness_used_mm with '
                'the SAME reference strength (derated yield): flat from the '
                'Roark Table 11.2 simply-supported circular plate bending '
                'stress, dished from the inverse of ASME VIII-1 UG-32(d) for '
                'a 2:1 ellipsoidal head. head_safety_factor is the entry for '
                'recommended_type; a layer that manufactures or draws the '
                'other type must quote that type entry instead of borrowing '
                'this one.'),
            'yield_strength_used_MPa': yield_for_design / 1e6,
            'safety_factor_is_tautological': bool(design_mode == 'size'),
            # P14H1-C4: bayrağın kesin ölçütü (hazne bloğuyla AYNI tanım).
            'safety_factor_reads_back_target': bool(
                design_mode == 'size'
                and head_safety_factor >= safety_factor * (1.0 - 1e-9)),
        }
    
    #: Kapak cıvatalarının varsayılan mukavemet sınıfı. ISO 898-1:2013
    #: sınıflarından 8.8 en yaygın makine cıvatasıdır; kullanıcı/çağıran
    #: sınıfı geçerse o kullanılır. Bu bir kalibrasyon sabiti DEĞİL, beyan
    #: edilen varsayılan malzeme seçimidir ve çıktıda adıyla raporlanır.
    _DEFAULT_BOLT_PROPERTY_CLASS = '8.8'

    #: ÖH P5B1-21 — cıvata deseni için ASGARİ ADIM ÇARPANI (aralık / çap).
    #: Cıvatalar birbirine giremez (oran > 1) ve pratikte anahtar boşluğu +
    #: kenar mesafesi bunun epey üstünü ister. 2,5 değeri BEYAN EDİLEN bir
    #: flanş pratiğidir (Taylor Forge / ASME VIII-1 Ek 2 cıvatalı flanş
    #: uygulaması), kalibrasyon sabiti DEĞİLDİR ve çıktıda adıyla
    #: (``bolt_min_pitch_factor``) yayımlanır.
    _BOLT_MIN_PITCH_FACTOR = 2.5

    #: Yerleşim kapanmadığında denenecek cıvata sayıları (azalan yönde
    #: aranır; dolan çevre sqrt(n) ile büyüdüğü için AZ sayı iyileştirir).
    #: Basınç flanşlarında dörtten az cıvata kullanılmaz.
    _BOLT_COUNT_LADDER = (8, 6, 4)

    def _analyze_fasteners(self, pressure: float, diameter: float,
                           mat_props: Dict,
                           design_safety_factor: Optional[float] = None,
                           bolt_property_class: Optional[str] = None,
                           grip_length_m: Optional[float] = None,
                           member_material: Optional[str] = None) -> Dict:
        """Kapak cıvatalarının statik çekme boyutlandırması.

        v2.6.26 — İKİ KAYNAKSIZ SABİT KALDIRILDI:

        (1) ``bolt_allowable_stress = 400 MPa``. Kodun kendi yorumu bu değerin
            "LİTERATÜR KAYNAĞI YOKTUR" diye beyan ediyordu ve aynı yorum
            çözümü de gösteriyordu: sınıf bazlı proof gerilmesi ``S_p``
            depoda ZATEN var (``hrma/analysis/bolted_joint._bolt_class_props``,
            ISO 898-1:2013 Table 3). Cıvata izin verilen çekme gerilmesi
            sınıfa göre 400 MPa ile 970 MPa arasında değişir; tek sabit
            kullanmak gerekli cıvata çapını yanlış boyutlandırıyordu.
            Artık izin verilen gerilme = S_p (proof stress) ve hangi sınıftan
            geldiği çıktıda kaynağıyla yazılır.

        (2) ``bolt_safety_factor = 4.0``. Kullanıcının 'Safety Factor' girdisi
            hazne cidarına uygulanırken cıvataya HİÇ ulaşmıyordu — ÖLÇÜLDÜ:
            safety_factor=2.0 ile bu alan 4.0 kaldı. Artık tasarım yükü
            kullanıcının katsayısıyla çarpılır; katsayı verilmezse beyan
            edilen 4.0 varsayılanı korunur.

        ÖH D15 / P5B1-06 — İKİ ÜRETİCİ TEK CEVABA BAĞLANDI.

        Eskiden bu blok ``bolt_safety_factor = 4.0`` yayımlıyordu; o sayı bir
        KAPASİTE değil, tasarım katsayısı GİRDİSİDİR, ama alan adı emniyet
        katsayısı olduğunu söylüyor ve önerilen cıvata boyunun yanında
        duruyordu. Aynı depodaki ön-yük modeli AYNI bağlantı için çok daha
        kötü bir hüküm veriyordu — ÖLÇÜLDÜ (once_b1.json, steel_4130, cidar
        6 mm, sıkma boyu 20 mm, çelik üyeler):

            Pc =  40 bar D = 100 mm | motor yolu 8 x M10, bolt_safety_factor
                                      = 4,0   ⟷ ön-yük proof_SF_min = 1,0392
            Pc =  60 bar D = 150 mm | 8 x M16, 4,0 ⟷ 1,0232
            Pc = 100 bar D = 150 mm | 8 x M20, 4,0 ⟷ 1,0188

        yani tek motorda iki farklı cevap. Eski docstring bunu "sıkma boyu bu
        fonksiyonun girdisi olmadığı için çağrılamaz" diye beyan ediyordu;
        beyan, yayımlanan 4,0 sayısını yanlış olmaktan kurtarmıyordu.

        Düzeltme (fail-closed): sıkma boyu ARTIK bir girdidir
        (``grip_length_m``, motor verisinde ``closure_grip_length_m``). Boy
        verilirse ``bolted_joint.analyze_bolted_joint`` ÇAĞRILIR ve onun
        hükmü (ayrılma + proof) bu bloğun ``fastener_status``ünü yönetir —
        tek cevap. Boy verilmezse ön-yük fizikleri koşamaz ve bu blok
        HÜKÜM VERMEZ: ``fastener_status = 'NOT_EVALUATED'`` + eksik alanın
        adı. ``bolt_safety_factor`` alanı sözleşme gereği kalır ama artık
        ``bolt_safety_factor_is_design_input = True`` ile birlikte gider.

        Args:
            design_safety_factor: tasarım emniyet katsayısı (None -> 4.0).
            bolt_property_class: '8.8' | '10.9' | '12.9' | 'A2-70'
                (None -> _DEFAULT_BOLT_PROPERTY_CLASS).
        """

        # Total force on end cap
        total_force = pressure * np.pi * (diameter/2)**2  # N

        # Assume 8-12 bolts depending on diameter
        if diameter < 0.1:
            num_bolts = 6
        elif diameter < 0.2:
            num_bolts = 8
        else:
            num_bolts = 12
        bolt_count_initial = num_bolts

        # F072 (2026-07-25) — ETİKET/BİRİM YANILTICISI GİDERİLDİ.
        # Eski sürüm 'force_per_bolt' adıyla TASARIM yükünü (gerçek yükün 4
        # katı) döndürüyordu; UI bunu "cıvata başına" diye gösteriyordu.
        # ÖLÇÜLDÜ (P_design=90 bar, D=150 mm): total=159.0 kN, raporlanan
        # force_per_bolt=79.52 kN, GERÇEK cıvata başına dış yük 19.88 kN
        # (4.00x şişirilmiş etiket). Artık ikisi ayrı alan.
        # v2.6.26: emniyet katsayısı kullanıcının tasarım katsayısıdır;
        # verilmezse eski beyan edilen 4.0 varsayılanı korunur (bkz. docstring).
        bolt_safety_factor = (float(design_safety_factor)
                              if design_safety_factor is not None
                              else _BOLT_SAFETY_FACTOR_DEFAULT)
        bolt_safety_factor_source = ('design input (safety factor)'
                                     if design_safety_factor is not None
                                     else 'declared default (no user value)')
        # Bolt sizing (assume steel bolts, 400 MPa allowable stress).
        # DUZELTME (2026-07-16): Civata cekme kapasitesi NOMINAL kesitten degil,
        # dis dibindeki GERILME ALANI A_t uzerinden tasinir. ISO 898-1 / Shigley
        # Tablo 8-1: A_t ~ 0.75*(pi/4*d_nom^2) (or. M10: A_t=58 mm^2 vs
        # pi/4*10^2=78.5, oran ~0.74). Eski kod gerekli alani dogrudan tam-dolu
        # daireye (pi/4*d^2) ceviriyordu -> civatayi sqrt(0.75)~0.87 kat KUCUK
        # seciyordu (non-konservatif). Dogrusu: gerekli A_t'yi guvenli nominal
        # capa cevir -> A_nom = A_t / 0.75.
        #
        # v2.6.26: izin verilen gerilme artık ISO 898-1:2013 Table 3 PROOF
        # gerilmesidir (bolted_joint._bolt_class_props — depodaki tek cıvata
        # mukavemet kaynağı). 8.8 sınıfında S_p, d <= 16 mm için 580 MPa,
        # d > 16 mm için 600 MPa'dır; çap çözümün kendi sonucu olduğu için
        # küçük sabit-nokta yinelemesiyle kapatılır.
        THREAD_STRESS_AREA_RATIO = 0.75  # A_t / (pi/4*d_nom^2), ISO 898-1 yaklasik
        bolt_class = str(bolt_property_class
                         or self._DEFAULT_BOLT_PROPERTY_CLASS)
        try:
            bolt_props = _bolt_class_props(bolt_class, 16.0)
        except ValueError:
            bolt_class = self._DEFAULT_BOLT_PROPERTY_CLASS
            bolt_props = _bolt_class_props(bolt_class, 16.0)
        # Bolt circle
        bolt_circle_radius = (diameter/2) + 0.025  # 25mm from chamber edge

        def _boyutlandir(n):
            """n cıvata için gerekli çapı ve yerleşim aralığını çözer."""
            f_bolt = total_force / n
            f_design = f_bolt * bolt_safety_factor
            props = _bolt_class_props(bolt_class, 16.0)
            d_req = 0.0
            for _ in range(3):
                s_p = float(props['S_p'])                 # Pa (proof)
                a_stress = f_design / s_p
                a_nom = a_stress / THREAD_STRESS_AREA_RATIO
                d_req = 2 * np.sqrt(a_nom / np.pi)
                nxt = _bolt_class_props(bolt_class, d_req * 1000.0)
                if nxt['S_p'] == props['S_p']:
                    break
                props = nxt
            spacing = 2 * np.pi * bolt_circle_radius / n
            return {'n': n, 'force_per_bolt': f_bolt,
                    'design_force_per_bolt': f_design, 'props': props,
                    'required_bolt_diameter': d_req, 'spacing': spacing,
                    'ratio': (spacing / d_req if d_req > 0 else float('inf'))}

        # --- ÖH ONARIMI (defter P5B1-21): CIVATA YERLEŞİMİ DENETLENİR -----
        # Eskiden cıvata sayısı YALNIZ hazne çapından seçiliyordu (6/8/12) ve
        # yerleşim hiç sınanmıyordu. ÖLÇÜLDÜ (Pc = 1000 bar, D = 400 mm):
        # gerekli cıvata çapı 133,33 mm iken aralık 117,81 mm — oran 0,884,
        # yani ürün BİRBİRİNİN İÇİNE GİREN bir cıvata deseni yayımlıyor ve
        # tek uyarı vermiyordu. (Pc 40/200/1000 bar oranları: 7,093 / 2,195 /
        # 0,884.)
        #
        # Geometri: toplam gerekli gerilme alanı yükten sabittir, yani
        # d ∝ 1/sqrt(n) ve dolan çevre n*k*d ∝ sqrt(n) — cıvata sayısını
        # ARTIRMAK yerleşimi KÖTÜLEŞTİRİR, azaltmak iyileştirir. Bu yüzden
        # arama merdiveni AŞAĞI doğru yürür ve mevcut sayı zaten sığıyorsa
        # HİÇ DEĞİŞMEZ (nominal tasarımlar bit-aynı kalır).
        secilen = _boyutlandir(num_bolts)
        bolt_layout_adjusted = False
        if secilen['ratio'] < self._BOLT_MIN_PITCH_FACTOR:
            adaylar = [secilen]
            for n in self._BOLT_COUNT_LADDER:
                if n < num_bolts:
                    adaylar.append(_boyutlandir(n))
            uygun = [c for c in adaylar
                     if c['ratio'] >= self._BOLT_MIN_PITCH_FACTOR]
            if uygun:
                # Yükü taşıyan ve sığan en ÇOK cıvatalı desen (yük dağılımı
                # için sayı fazla olan tercih edilir).
                yeni = max(uygun, key=lambda c: c['n'])
            else:
                # Hiçbiri istenen adımı sağlamıyor: en iyi oranı veren desen
                # seçilir ve yetmezlik ADIYLA beyan edilir (fail-closed).
                yeni = max(adaylar, key=lambda c: c['ratio'])
            bolt_layout_adjusted = (yeni['n'] != secilen['n'])
            secilen = yeni

        num_bolts = secilen['n']
        force_per_bolt = secilen['force_per_bolt']            # GERÇEK dış yük
        design_force_per_bolt = secilen['design_force_per_bolt']
        bolt_props = secilen['props']
        bolt_allowable_stress = float(bolt_props['S_p'])
        required_bolt_diameter = secilen['required_bolt_diameter']
        bolt_spacing_m = secilen['spacing']
        bolt_pitch_ratio = secilen['ratio']
        bolt_layout_ok = bool(bolt_pitch_ratio >= self._BOLT_MIN_PITCH_FACTOR)
        bolt_layout_interferes = bool(bolt_pitch_ratio <= 1.0)

        # Standard bolt sizes (in meters) — ISO 261 kaba diş serisi. M14 /
        # M18 / M22 EKLENDİ (defter P5B1-21): ikinci tercih boylar olsalar da
        # gerçek ve tedarik edilebilir çaplardır; listede olmamaları ürünü
        # bir üst boya zıplatıyordu.
        standard_sizes = [0.006, 0.008, 0.010, 0.012, 0.014, 0.016, 0.018,
                          0.020, 0.022, 0.024, 0.030, 0.036,
                          0.042]  # M6 to M42
        suitable_sizes = [size for size in standard_sizes if size >= required_bolt_diameter]

        if suitable_sizes:
            recommended_bolt_size = min(suitable_sizes)
        else:
            # If required diameter exceeds largest standard size, use largest available
            recommended_bolt_size = max(standard_sizes)
            # Add warning about custom bolt requirement

        # Warning if custom bolt needed
        bolt_warning = None
        if not suitable_sizes:
            bolt_warning = f"Required bolt diameter ({required_bolt_diameter*1000:.1f}mm) exceeds largest standard size. Custom bolts needed."

        # YERLEŞİM YETMEZLİĞİ BEYANI — kodlu uyarı YERİNE adlı alan.
        # ``_mk_warning`` yeni bir uyarı KODU açmayı gerektirir ve o kodun
        # hrma/static/js/i18n_*.js sözlüğünde karşılığı olmalıdır (ölçüldü:
        # tests/test_i18n_common.py::test_every_used_key_exists_in_dictionary
        # sözlüksüz kodu KIRMIZI yapar); sözlük bu paketin mülkü değildir.
        # Hüküm bu yüzden ``bolt_layout_status`` + kardeş alanlarda ADIYLA
        # yayımlanır; i18n dalgası buraya bir uyarı kodu takabilir.
        if bolt_layout_interferes:
            bolt_layout_status = 'BOLTS_OVERLAP'
        elif not bolt_layout_ok:
            bolt_layout_status = 'BELOW_MINIMUM_PITCH'
        else:
            bolt_layout_status = 'OK'

        # --- ÖH D15 / P5B1-06: ÖN-YÜK MODELİ AYNI BAĞLANTIYI ÇÖZER -------
        preload = None
        preload_basis = None
        fastener_status = 'NOT_EVALUATED'
        if grip_length_m is None or not (float(grip_length_m) > 0.0):
            preload_basis = (
                "preload physics NOT evaluated: the clamped grip length of "
                "the closure joint was not supplied (motor field "
                "'closure_grip_length_m'). Without it the bolt/member "
                "stiffness ratio C is unknown, so joint separation — which "
                "is the governing criterion for a preloaded flange — cannot "
                "be checked. bolt_safety_factor below is the DESIGN INPUT "
                "read back, not a verified capacity.")
        elif not member_material:
            preload_basis = (
                "preload physics NOT evaluated: the clamped member material "
                "was not supplied, so the member stiffness k_m is unknown "
                "(see P5B1-05 — assuming one flips the separation verdict).")
        else:
            try:
                from hrma.analysis.bolted_joint import analyze_bolted_joint
                _bj = analyze_bolted_joint(
                    pressure_bar=pressure / 1e5,
                    seal_diameter_mm=diameter * 1000.0,
                    bolt_count=int(num_bolts),
                    size=f"M{int(recommended_bolt_size * 1000)}",
                    property_class=bolt_class,
                    grip_length_mm=float(grip_length_m) * 1000.0,
                    member_material=str(member_material))
                _sep = _bj.get('separation', {})
                _sf = _bj.get('safety_factors', {})
                preload = {
                    'separated': bool(_sep.get('separated')),
                    'separation_margin': _sep.get('margin'),
                    'proof_SF_min': _sf.get('proof_SF_min'),
                    'overload_factor_nL_min': _sf.get('overload_factor_nL_min'),
                    'grip_length_mm': float(grip_length_m) * 1000.0,
                    'member_material': str(member_material),
                    'warnings': list(_bj.get('warnings', [])),
                    'source': _bj.get('source'),
                }
                preload_basis = (
                    'preload physics evaluated by '
                    'hrma.analysis.bolted_joint (Shigley Eq. 8-24...8-30, '
                    'NASA-STD-5020A Sec. 6.2) on THIS bolt pattern — the '
                    'fastener verdict below comes from that model, not from '
                    'the design factor.')
                _proof = preload['proof_SF_min']
                # ÖH D17 / P5B1-06 (Fable-D15 ŞARTI): eskiden burada
                # ``_proof < 1.2 -> 'MARGINAL'`` diye ÜÇÜNCÜ bir bant
                # vardı; o 1,2'nin depoda KAYNAĞI YOKTU (ön-yük modelinin
                # kendi tek eşiği 1,0 idi, bkz.
                # ``bolted_joint.PROOF_SF_ACCEPTANCE_LIMIT``) ve docstring
                # de gerekçe vermiyordu. Kaynaksız eşik KALDIRILDI: hüküm
                # artık ön-yük modelinin kendi sınırından okunur
                # (doktrin 4 — tek kaynak; yeni eşik icat edilmez).
                if preload['separated']:
                    fastener_status = 'CRITICAL'
                elif (isinstance(_proof, float)
                      and _proof < PROOF_SF_ACCEPTANCE_LIMIT):
                    fastener_status = 'CRITICAL'
                elif isinstance(_proof, float):
                    fastener_status = 'SAFE'
            except Exception as _e:            # fail-closed: hüküm verilmez
                preload = None
                preload_basis = (
                    'preload physics could not be evaluated '
                    f'({type(_e).__name__}: {str(_e)[:120]}); no fastener '
                    'verdict is published.')

        return {
            'total_force': total_force / 1000,  # kN
            'num_bolts': num_bolts,
            # F072: artık GERÇEK cıvata başına dış yük (eski değer 4x fazlaydı)
            'force_per_bolt': force_per_bolt / 1000,  # kN
            'design_force_per_bolt_N': design_force_per_bolt,  # N (SF'li)
            'external_force_per_bolt_N': force_per_bolt,       # N (gerçek)
            'required_bolt_diameter': required_bolt_diameter * 1000,  # mm
            'recommended_bolt_size': f"M{int(recommended_bolt_size*1000)}",
            'bolt_circle_radius': bolt_circle_radius * 1000,  # mm
            'bolt_spacing': bolt_spacing_m * 1000,  # mm
            # --- ÖH P5B1-21: yerleşim hükmü ADIYLA yayımlanır -------------
            'bolt_pitch_ratio': bolt_pitch_ratio,
            'bolt_min_pitch_factor': self._BOLT_MIN_PITCH_FACTOR,
            'bolt_layout_ok': bolt_layout_ok,
            'bolt_layout_interferes': bolt_layout_interferes,
            'bolt_layout_status': bolt_layout_status,
            'bolt_count_initial': bolt_count_initial,
            'bolt_count_adjusted': bolt_layout_adjusted,
            'bolt_layout_basis': (
                'bolt spacing = pi*D_bolt_circle/n compared with the '
                'required bolt diameter; the minimum pitch factor %.2g is a '
                'DECLARED flange practice value (wrench clearance and edge '
                'distance; Taylor Forge / ASME VIII-1 App.2 bolted-flange '
                'practice), not a calibration constant. Bolt count is chosen '
                'from the diameter rule first and only reduced when the '
                'layout does not close - the occupied circumference goes '
                'like sqrt(n), so fewer, larger bolts fit where many small '
                'ones do not. bolt_layout_ok=false means the published '
                'pattern does not meet that pitch; bolt_layout_interferes='
                'true means the bolts overlap outright.'
                % self._BOLT_MIN_PITCH_FACTOR),
            'bolt_safety_factor': bolt_safety_factor,
            'bolt_safety_factor_source': bolt_safety_factor_source,
            # ÖH D15 / P5B1-06: bu sayı bir DOĞRULAMA değil, tasarım
            # katsayısı girdisinin geri okunmasıdır. Hüküm aşağıdaki
            # ``fastener_status``tedir ve ön-yük modelinden gelir.
            'bolt_safety_factor_is_design_input': True,
            'preload_analysis': preload,
            'preload_analysis_basis': preload_basis,
            'fastener_status': fastener_status,
            'bolt_allowable_stress_MPa': bolt_allowable_stress / 1e6,
            # v2.6.26 dürüstlük alanları: izin verilen gerilmenin hangi cıvata
            # sınıfından ve hangi standarttan geldiği çıktıda taşınır.
            'bolt_property_class': bolt_class,
            'bolt_allowable_stress_basis': bolt_props['source'],
            'sizing_basis': ('static tensile sizing only: F_design = SF * P/n '
                             'over thread stress area, allowable = ISO 898-1 '
                             'proof stress S_p; preload and separation are '
                             'NOT modelled here'),
            'warning': bolt_warning,
            # ÖN-YÜK FİZİĞİ YOK: ön-yüklü bağlantıda cıvata yükü F_i + C*P'dir,
            # SF*P/n değil; asıl kritik kriter AYRILMA (F_i/(P(1-C))) burada
            # hiç kontrol edilmez. Doğru model aynı depoda
            # hrma/analysis/bolted_joint.py'dedir (Shigley Eq. 8-24...8-30);
            # sıkma boyu (grip length) ve cıvata sınıfı bu fonksiyonun girdisi
            # olmadığı için buradan otomatik çağrılamaz — kullanıcı yönlendirilir.
            'warnings': [_mk_warning(
                'warn.structural.fastener_preload_not_modeled', 'warning',
                module='bolted_joint')],
        }
    
    def _analyze_fatigue(self, stress: float,
                         mat_props: Dict,
                         design_cycles: Optional[int] = None,
                         derating: Optional[Dict] = None) -> Dict:
        """Yorulma analizi — Goodman ortalama-gerilme düzeltmesi (R≈0).

        DALGA 3 DÜZELTMESİ (2026-07-14) — eski sürümün üç hatası giderildi:
          1. BİRİM HATASI: 'stress' MPa cinsinden gelir (analyze_structure,
             chamber_analysis['hoop_stress'] MPa döndürür) ama Pa cinsinden
             fatigue_limit ile oranlanıyordu → SF ~1e6 kat şişkin çıkıyor,
             yorulma daima 'SAFE' görünüyordu (tehlikeyi az gösterme).
          2. GENLİK=TEPE HATASI: tam σ_max 'amplitude' sayılıyor, ortalama
             gerilme etkisi (Goodman) hiç uygulanmıyordu. Basınçlı kap her
             ateşlemede 0 → P → 0 yüklenir (R = σ_min/σ_max ≈ 0); bu
             çevrimde σ_a = σ_m = σ_max/2'dir.
          3. 'Basquin b=10' sabiti ve saniyede-1-tam-çevrim sayımı fiziksel
             dayanaksızdı (yanma içi kamara osilasyonları tam R=0
             basınçlandırma çevrimi DEĞİLDİR, genlikleri Pc'nin küçük bir
             yüzdesidir — çevrim sayılmaz).

        Model (Shigley's Mechanical Engineering Design, 10th ed., Böl. 6):
          Düzeltilmiş Goodman doğrusu (Eq. 6-46):
              1/n_f = σ_a/S_e + σ_m/S_u
          S_e : malzeme kaydındaki fatigue_limit (materials_db — kaynaklı,
                malzemeye özgü değer; jenerik 0.5·S_u kuralı yerine merkezi
                DB değeri kullanılır → parametre tutarlılığı)
          S_u : materials_db 'ultimate_strength'
          Sonlu ömür (n_f < 1): Goodman eşdeğer tam-ters genliği
              σ_ar = σ_a/(1 − σ_m/S_u)
          ile Basquin S-N eğrisi (Shigley Eq. 6-14/6-15):
              S_f = a·N^b,  a = (f·S_u)²/S_e,  b = −log10(f·S_u/S_e)/3,
              f ≈ 0.9 (Fig. 6-18 yaklaşımı — approximate)

        Args:
            stress: σ_max [MPa] — hoop gerilme (analyze_structure MPa yollar)
            (ÖH D15 / P5B1-10: ``burn_time`` parametresi KALDIRILDI. Bu
                model yanma süresinden çevrim TÜRETMEZ — R≈0 basınçlandırma
                çevrimi ateşleme başına birdir, süreyle değil — ve parametre
                gövdede hiç okunmuyordu. Ölçüm ``analyze_structure``
                içindeki P5B1-10 notunda.)
            mat_props: get_material() kaydı (fatigue_limit, ultimate_strength)
            design_cycles: tasarım basınçlandırma çevrimi sayısı (hidrotest +
                test kampanyası + uçuş). None → 25 (approximate varsayım;
                endpoint/çağıran geçersiz kılabilir).
        """
        sigma_max_pa = max(float(stress), 0.0) * 1e6   # MPa → Pa
        S_e_room = float(mat_props['fatigue_limit'])       # Pa (materials_db)
        S_u_room = float(mat_props['ultimate_strength'])   # Pa (materials_db)

        # --- ÖH D15 / P5B1-03: YORULMA ARTIK CİDAR SICAKLIĞINI GÖRÜYOR ---
        # ÖLÇÜLDÜ (once_b1.json; steel_4130, Pc = 80 bar, cidar 4 mm):
        #   T = 300 K -> yapısal yield_used 458,60 MPa | S_e 230,0  n_f 2,3319
        #   T = 700 K -> yapısal yield_used 276,43 MPa | S_e 230,0  n_f 2,3319
        #   T = 800 K -> yapısal yield_used 183,87 MPa | S_e 230,0  n_f 2,3319
        #   T = 811 K -> yapısal yield_used 176,28 MPa | S_e 230,0  n_f 2,3319
        # Yani hazne cidarı %61 derate edilirken yorulma değerlendirmesi HİÇ
        # kıpırdamıyordu (konservatif OLMAYAN yön) ve 800 K'de ürün, AYNI
        # yanıtta, sonsuz-ömür dayanım sınırını (230,0 MPa) derate edilmiş
        # AKMA dayanımından (183,87 MPa) BÜYÜK yayımlıyordu — fiziksel olarak
        # imkânsız bir çift; hüküm yine 'SAFE' idi.
        #
        # Düzeltme: dayanım derating'i (MMPDS/MIL-HDBK-5 retention eğrisi,
        # ``_derate_strength``) hem S_e'ye hem S_u'ya uygulanır. Retention
        # eğrisi AKMA için tablolanmıştır; yorulma dayanımına aynı çarpanla
        # taşımak bir YAKLAŞIMDIR (approximate) ve çıktıda böyle beyan
        # edilir. Yön konservatiftir: metallerin sonsuz-ömür dayanımı
        # sıcaklıkla en az akma kadar düşer (Shigley 10. baskı Böl. 6-7,
        # sıcaklık düzeltme çarpanı k_d ile aynı fikir).
        retention = None
        if derating is not None:
            try:
                r = float(derating.get('strength_retention_factor'))
                if np.isfinite(r) and 0.0 < r <= 1.0:
                    retention = r
            except (TypeError, ValueError):
                retention = None
        if retention is not None:
            S_e = S_e_room * retention
            S_u = S_u_room * retention
            derating_basis = (
                'endurance limit and ultimate strength are derated to '
                f'{retention * 100:.0f}% of their room-temperature values '
                'using the material temperature-retention curve evaluated at '
                'the governing wall temperature (Shigley 10th ed. Sec. 6-7 '
                'temperature factor k_d; the tabulated curve is a YIELD '
                'retention curve, so carrying it to the endurance limit is '
                'approximate)')
        else:
            S_e = S_e_room
            S_u = S_u_room
            derating_basis = (
                'NO temperature derating was applied: the caller supplied no '
                'wall-temperature derating record, so room-temperature '
                'strengths are used. This is NOT conservative for a hot '
                'wall — supply the derating record to evaluate fatigue at '
                'temperature.')
        if design_cycles is None:
            design_cycles = 25  # hidrotest + test kampanyası + uçuş (approx.)
        design_cycles = max(1, int(design_cycles))

        # R ≈ 0 basınç çevrimi: σ_a = σ_m = σ_max/2
        sigma_a = sigma_max_pa / 2.0
        sigma_m = sigma_max_pa / 2.0

        if sigma_a <= 0.0:
            goodman_utilization = 0.0
            fatigue_safety_factor = float('inf')
        else:
            goodman_utilization = sigma_a / S_e + sigma_m / S_u
            fatigue_safety_factor = 1.0 / goodman_utilization

        # Sonlu ömür tahmini — yalnız Goodman doğrusu aşıldıysa (n_f < 1)
        estimated_life = 'Infinite'
        cycle_margin = 'Infinite'
        lcf_warning = None
        if fatigue_safety_factor < 1.0:
            if sigma_m < S_u:
                sigma_ar = sigma_a / (1.0 - sigma_m / S_u)  # Goodman eşdeğeri
                # v2.6.2 fizik denetimi, bulgu F181: f SABİT 0.9 alınıyordu.
                # Shigley Fig. 6-18'de f, S_ut'ye BAĞLIDIR ve yüksek dayanımlı
                # malzemelerde belirgin biçimde düşer. f'in fazla alınması
                # 10^3 çevrimdeki gerilme çapasını yükseltir, dolayısıyla
                # sonlu ömrü FAZLA gösterir — KONSERVATİF OLMAYAN yön.
                # Bu kod tabanında steel_4130 (S_u=730 MPa), inconel_718 ve
                # titanyum alaşımları zarfın dışındaydı.
                # Kaynak: Shigley's Mechanical Engineering Design 10. baskı,
                # Fig. 6-18 (f–S_ut eğrisi), Eq. 6-14/6-15 (Basquin a, b).
                f_frac = _shigley_fatigue_strength_fraction(S_u)
                a_basq = (f_frac * S_u) ** 2 / S_e          # Eq. 6-14
                b_basq = -np.log10(f_frac * S_u / S_e) / 3.0  # Eq. 6-15
                N = float(max((sigma_ar / a_basq) ** (1.0 / b_basq), 1.0))
            else:
                N = 0.0  # ortalama gerilme çekme dayanımını aşıyor → statik kırılma
            estimated_life = N
            cycle_margin = N / design_cycles
            if N < 1e3:
                lcf_warning = ('Low-cycle fatigue regime (N < 1000): Basquin '
                               'extrapolation is approximate; strain-life '
                               'method recommended')

        # Durum eşikleri: Goodman SF sonsuz ömre karşı ölçülür. n_f >= 1.5
        # tipik yorulma saçılım payıdır (approximate practice). n_f < 1 ama
        # tahmini ömür tasarım çevriminin >= 10 katıysa MARGINAL (sonlu ömür
        # kabulü), aksi halde CRITICAL.
        if fatigue_safety_factor >= 1.5:
            fatigue_status = 'SAFE'
        elif fatigue_safety_factor >= 1.0:
            fatigue_status = 'MARGINAL'
        elif (isinstance(estimated_life, float)
              and estimated_life / design_cycles >= 10.0):
            fatigue_status = 'MARGINAL'
        else:
            fatigue_status = 'CRITICAL'

        result = {
            # Eski anahtarlar korunur (sözleşme testleri) — anlamları düzeltildi
            'stress_amplitude': sigma_a / 1e6,   # MPa (σ_a = σ_max/2, R=0)
            'fatigue_limit': S_e / 1e6,          # MPa
            'fatigue_safety_factor': fatigue_safety_factor,  # Goodman n_f
            # v2.6.26 — 'estimated_cycles' ARTIK TAHMİNDİR.
            # Bu alan tasarım GİRDİSİNİ (design_cycles) geri döndürüyordu:
            # 'tahmini çevrim' adını taşıyan bir alan hiçbir bilgi taşımıyor,
            # kullanıcı ise bunu bir ömür tahmini sanıyordu (aynı sözlükte
            # 'design_cycles' zaten aynı sayıyı veriyor). Artık hesaplanan
            # ömürle (Basquin/Goodman çözümü) aynı değeri taşır; tasarım
            # hedefi 'design_cycles' alanında durur.
            'estimated_cycles': estimated_life,  # çevrim | 'Infinite' (hesap)
            'estimated_cycles_basis': (
                'predicted life for the computed stress state '
                '(Goodman + Basquin); the design target is design_cycles'),
            'estimated_life': estimated_life,    # çevrim sayısı | 'Infinite'
            'fatigue_status': fatigue_status,
            # Yeni alanlar (Dalga 3)
            'max_stress': sigma_max_pa / 1e6,    # MPa (σ_max)
            'mean_stress': sigma_m / 1e6,        # MPa (σ_m = σ_max/2)
            'stress_ratio_R': 0.0,               # basınç çevrimi 0→P→0
            # v2.6.26 — SABİT ÇIKTI BEYANI: R tanım gereği sabittir, çünkü
            # çevrim modeli 0→P→0 seçilmiştir (aşağıdaki 'assumptions').
            'stress_ratio_R_basis': (
                'stress ratio R = sigma_min/sigma_max is fixed at zero BY '
                'THE CYCLE MODEL, not computed: every firing is treated as '
                'one full 0 -> P -> 0 pressure cycle, so the minimum stress '
                'is zero. If your duty cycle keeps the chamber pressurised '
                'between firings (or preloads it), R is not zero and this '
                'Goodman evaluation does not apply.'),
            'ultimate_strength': S_u / 1e6,      # MPa
            # P5B1-03: oda sıcaklığı taban değerleri ADIYLA korunur ki
            # kullanıcı derating'in ne kadar götürdüğünü görebilsin.
            'fatigue_limit_room_MPa': S_e_room / 1e6,
            'ultimate_strength_room_MPa': S_u_room / 1e6,
            'strength_retention_factor': retention,
            'strength_derating_basis': derating_basis,
            'goodman_utilization': goodman_utilization,  # σa/Se + σm/Su
            'cycle_margin': cycle_margin,        # tahmini ömür / tasarım çevrimi
            'design_cycles': design_cycles,
            'model': ('Modified Goodman mean-stress correction, R=0 pressure '
                      'cycle (Shigley 10th ed. Eq. 6-46)'),
            'assumptions': [
                'Each firing = one full 0 -> P -> 0 pressure cycle (R = 0)',
                'sigma_a = sigma_m = sigma_max/2',
                'S_e taken from central material record '
                '(materials_db fatigue_limit)',
                'Combustion oscillations are not counted as full cycles',
                f'Design cycle count = {design_cycles} (proof test + test '
                f'campaign + flight; approximate, override via parameter)',
            ],
        }
        if lcf_warning:
            result['warning'] = lcf_warning
        return result
    
    def _calculate_weight(self, chamber_analysis: Dict, nozzle_analysis: Dict,
                        end_cap_analysis: Dict, mat_props: Dict) -> Dict:
        """Calculate structural weight"""
        
        density = mat_props['density']

        # v2.6.26 — KÜTLE DEĞERLENDİRİLEN CİDARDAN HESAPLANIR.
        # Burada `recommended_thickness` kullanılıyordu: kullanıcı 5 mm cidar
        # girse bile kütle, modülün ÖNERDİĞİ 15,9 mm'den hesaplanıyordu
        # (ölçüldü: 230,7 kg yerine 67,9 kg olmalıydı). Doğrulama modunda
        # kullanıcının tasarımı geçerlidir; boyutlandırma modunda iki değer
        # zaten aynıdır. Aynı hata burkulma kontrolünde de vardı ve bu
        # sürümde düzeltildi — kütle kalemi atlanmıştı.
        chamber_thickness = (
            chamber_analysis.get('wall_thickness_used_mm')
            or chamber_analysis['recommended_thickness']) / 1000  # m
        chamber_diameter = chamber_analysis['diameter'] / 1000  # m
        chamber_length = chamber_analysis['length'] / 1000  # m

        chamber_volume = np.pi * ((chamber_diameter/2 + chamber_thickness)**2 - (chamber_diameter/2)**2) * chamber_length
        chamber_weight = chamber_volume * density

        # Lüle kütlesi: kamara kütlesinin %30'u kabul edilir. Bu bir GEOMETRİ
        # HESABI DEĞİL, mühendislik başparmak kuralıdır; lülenin kendi
        # malzemesi (grafit 1800 vs çelik 7850 kg/m³) burada hiç görünmez.
        # Çıktıda 'nozzle_weight_basis' ile AÇIKÇA beyan edilir ki kullanıcı
        # bunu hesaplanmış bir sayı sanmasın. Gerçek lüle kütlesi
        # nozzle_design modülünün geometri+malzeme çözümünden gelir.
        nozzle_weight = chamber_weight * NOZZLE_MASS_RULE_OF_THUMB_FRACTION
        
        # End caps weight
        #
        # ÖH ONARIMI (defter P5B1-11) — KAPAK KÜTLESİ DEĞERLENDİRİLEN
        # KAPAKTAN HESAPLANIR. Burada ``min(flat_head_thickness,
        # dished_head_thickness)`` kullanılıyordu; o ikisi BOYUTLANDIRMA
        # çıktısıdır (modülün önerdiği kalınlıklar) ve kullanıcının GİRDİĞİ
        # kapak kalınlığından bağımsızdır. Sonuç ölçüldü: 2 mm ile 50 mm
        # kapak (25 kat) aynı ``end_caps_weight`` = 0,265554 kg ve aynı
        # toplamı veriyordu — kütle kalemi kapak kalınlığına KÖR idi.
        # Kardeşi ``chamber_thickness`` bu dersi v2.6.26'da zaten öğrenmişti
        # (yukarıdaki not); kapak kalemi o turda atlanmıştı.
        # ``head_thickness_used_mm`` doğrulama modunda kullanıcının
        # kalınlığı, boyutlandırma modunda önerilen kalınlıktır — yani iki
        # modda da DOĞRU değer odur.
        #
        # ÖH D32 / OH-FT-06 — HANGİ KAPAK TARTILDI? Künye bu kütlenin
        # ``head_thickness_used_mm``ten geldiğini söylüyordu ama o kalınlığın
        # hangi kapak TİPİNE ait olduğunu söylemiyordu (ölçüldü:
        # ``once.json`` bölüm C, ``kutle_tip_alani_var = false``). Ölçülen
        # tipik koşumda (Ø100 mm / 40 bar / çelik, boyutlandırma kipi)
        # tartılan kalınlık 2,622378 mm (dished öneri) iken ihraç katmanının
        # çizdiği DÜZ kapak 12,646962 mm'dir: okuyucu, kütlenin hangi
        # tasarımın kütlesi olduğunu bu bloktan göremiyordu. Sayı DEĞİŞMEZ
        # (kütle değerlendirilen kapaktan hesaplanmaya devam eder); tipin
        # ADI yayımlanır.
        _kapak_kullanilan = end_cap_analysis.get('head_thickness_used_mm')
        if _kapak_kullanilan is None or float(_kapak_kullanilan) <= 0.0:
            _kapak_kullanilan = min(end_cap_analysis['flat_head_thickness'],
                                    end_cap_analysis['dished_head_thickness'])
            end_cap_thickness_type = 'fallback_min_of_sized'
            end_cap_thickness_basis = (
                'FALLBACK: head_thickness_used_mm was not published, so the '
                'smaller of the two sized head thicknesses was used; this '
                'mass does NOT reflect a user-supplied cap thickness '
                '(end_cap_thickness_used_type = "fallback_min_of_sized")')
        else:
            end_cap_thickness_type = (
                end_cap_analysis.get('head_thickness_used_type')
                or end_cap_analysis.get('recommended_type'))
            end_cap_thickness_basis = (
                'evaluated cap thickness (head_thickness_used_mm) — the '
                'user thickness in verify mode, the sized thickness in size '
                'mode; flat/dished sizing outputs are NOT used for mass. '
                'The head type this mass belongs to is named in '
                'end_cap_thickness_used_type (' + str(end_cap_thickness_type)
                + '); a layer that draws or manufactures another head type '
                'is weighing a different part and must size it from that '
                'type own thickness field (end_cap_analysis.'
                'head_thickness_field_by_type).')
        end_cap_thickness = float(_kapak_kullanilan) / 1000
        end_cap_area = np.pi * (chamber_diameter/2 + chamber_thickness)**2
        end_caps_weight = 2 * end_cap_area * end_cap_thickness * density  # Two end caps

        # Total weight
        total_weight = chamber_weight + nozzle_weight + end_caps_weight
        
        return {
            'chamber_weight': chamber_weight,  # kg
            'nozzle_weight': nozzle_weight,    # kg
            'end_caps_weight': end_caps_weight,  # kg
            'total_weight': total_weight,      # kg
            'wall_thickness_used_mm': chamber_thickness * 1000,
            # ÖH P5B1-11: kütlenin hangi kapak kalınlığından çıktığı adıyla.
            'end_cap_thickness_used_mm': end_cap_thickness * 1000,
            # ÖH D32 / OH-FT-06: ve o kalınlığın hangi kapak TİPİNE ait
            # olduğu adıyla ('flat' | 'dished' | 'user_supplied' |
            # 'fallback_min_of_sized').
            'end_cap_thickness_used_type': end_cap_thickness_type,
            'end_caps_weight_basis': end_cap_thickness_basis,
            'chamber_weight_basis': (
                'cylindrical shell volume x material density, using the '
                'evaluated wall thickness'),
            'nozzle_weight_basis': (
                'ESTIMATE: 30% of chamber weight (engineering rule of thumb, '
                'not a geometry calculation; the nozzle material is not '
                'reflected here)'),
            # V3 yapi-sf: kütlenin hangi yoldan geldiği makinece okunur.
            # Motor zinciri çizilen lülenin kütlesini verdiğinde
            # ``apply_drawn_nozzle_mass`` bu alanı 'drawn_solid' yapar ve
            # başparmak kuralı yanıtta HİÇ kalmaz (tek kaynak).
            'nozzle_weight_source': 'rule_of_thumb_fraction_of_chamber',
            'weight_breakdown': {
                'chamber_percent': chamber_weight / total_weight * 100,
                'nozzle_percent': nozzle_weight / total_weight * 100,
                'end_caps_percent': end_caps_weight / total_weight * 100
            }
        }
    
    @staticmethod
    def apply_drawn_nozzle_mass(weight_analysis: Dict, nozzle_mass_kg: float,
                                nozzle_mass_basis: str) -> Dict:
        """Kütle dökümünün lüle kalemini ÇİZİLEN katının kütlesiyle kurar.

        V3 yapi-sf (7 Eki 2026). ÖLÇÜLDÜ (main 393960ce, örnek 3 kN
        hibrit): aynı yanıtta üç lüle kütlesi — 0,4275 kg (CAD dökümü,
        çizilen katı), 0,3248 kg (``nozzle_geometry.estimated_mass``,
        lüle tasarımcısının KENDİ yakınsak konisiyle kesik koni) ve
        24,78 kg (``weight_analysis.nozzle_weight`` = kamara kütlesinin
        %30'u; 23,08 mm'lik kamara cidarı 82,61 kg verdiği için). Kuru
        kütle 108,21 kg'ın 24,78 kg'ı bu kuraldı. Çağıran (motor zinciri)
        çizilen lülenin kütlesini verdiğinde döküm onu kullanır; toplam ve
        yüzdeler yeniden kurulur, başparmak kuralı yanıtta kalmaz.
        """
        w = dict(weight_analysis)
        chamber_weight = w['chamber_weight']
        end_caps_weight = w['end_caps_weight']
        nozzle_weight = float(nozzle_mass_kg)
        total_weight = chamber_weight + nozzle_weight + end_caps_weight
        w['nozzle_weight'] = nozzle_weight
        w['total_weight'] = total_weight
        w['nozzle_weight_source'] = 'drawn_solid'
        w['nozzle_weight_basis'] = nozzle_mass_basis
        w['weight_breakdown'] = {
            'chamber_percent': chamber_weight / total_weight * 100,
            'nozzle_percent': nozzle_weight / total_weight * 100,
            'end_caps_percent': end_caps_weight / total_weight * 100
        }
        return w

    def _analyze_safety_factors(self, chamber_analysis: Dict, nozzle_analysis: Dict,
                              end_cap_analysis: Dict, mat_props: Dict,
                              buckling_analysis: Optional[Dict] = None,
                              wall_temperature_K: Optional[float] = None,
                              peak_wall_temperature_K: Optional[float] = None,
                              peak_wall_temperature_basis: Optional[str] = None,
                              model_validity: Optional[Dict] = None,
                              fatigue_analysis: Optional[Dict] = None
                              ) -> Dict:
        """Analyze overall safety factors.

        DENETIM DUZELTMESI (2026-06): Burkulma (buckling) emniyet faktoru de
        minimum SF hesabina dahil edilir. chamber_analysis['hoop_safety_factor']
        artik TERMAL+BASINC toplam gerilmeye ve DERATE edilmis yield'e gore
        hesaplanmis olarak gelir; dolayisiyla minimum SF gercekci-konservatif olur.

        FIZIK DENETIMI F074 (2026-07-25) — IKI FARKLI SICAKLIK, IKI FARKLI AMAC.
        Eski surum servis-sinir kontrolunu ``wall_temperature_K`` ile, yani
        YONETEN SENARYONUN DERATING SICAKLIGI ile yapiyordu. 'cooled_gradient'
        senaryosu yonettiginde bu deger ORTALAMA cidar sicakligidir
        (0.5*(T_ic + T_dis)); oysa servis sinirinin asilmasi IC (sicak) yuzde
        olur. Dayanim derating'i icin kesit ortalamasi makul (tasima
        kapasitesini o belirler), ancak SERVIS SINIRI / yumusama / surunme
        kontrolu TEPE metal sicakliginda yapilmalidir.
        Kaynak: MMPDS / malzeme ureticisi kisa-sureli maruziyet sinirlari
        (tepe metal sicakligina uygulanir).
        OLCULDU: T_sicak=860 K, T_soguk=560 K, steel_4130 (servis siniri 811 K)
        -> eski kod T=710 K, oran 0.8755, exceeds=False; tepe tabanli dogru
        deger 860/811 = 1.0604 (>1 -> UNSAFE) ve exceeds=True.

        ÖH Z4 (P5B1-01, kritik) — HÜKÜM KAZANILMIŞ SF'DEN ÇIKAR.
        Sepetin minimumu ürün yolunda daima HRMA'nın kendi boyutlandırdığı
        istasyonlardan geliyordu, yani hüküm kullanıcının SF HEDEFİNİN geri
        okunmasıydı. Ayrıntılı ölçüm ve yeni sözleşme gövdedeki Z4 blokunda.
        Özet: ``status``/``risk_level`` yalnız KAZANILMIŞ (kullanıcının
        verdiği kalınlığa karşı ölçülmüş) katsayılardan üretilir; hedeften
        türeyen sayılar ``design_target_assessment`` içinde AYRI notlanır;
        kazanılmış istasyon yoksa hüküm fail-closed olarak
        ``NOT_EVALUATED``'dir.

        Args:
            wall_temperature_K: dayanim derating'inin yapildigi sicaklik
                (yoneten senaryonun kesit sicakligi) — raporlanir.
            peak_wall_temperature_K: TEPE (ic yuz) cidar sicakligi — servis
                siniri karsilastirmasi bundan yapilir. Verilmezse geriye donuk
                davranis icin wall_temperature_K'ye duser.
            model_validity: ``structural_model_validity`` sonucu (V3 yapi-sf
                2. tur, karar §28-24 (C)). Sınır aşıldıysa OLUMLU hüküm ve
                SAYISAL tasarım hükmü (verdict/headline SF) verilmez; uyarı
                (MARGINAL/UNSAFE) susturulmaz. None -> eski davranış.
        """

        sf_candidates = {
            'chamber_hoop': chamber_analysis['hoop_safety_factor'],
            'chamber_von_mises': chamber_analysis['von_mises_safety_factor'],
            'nozzle': nozzle_analysis['safety_factor'],
            'end_cap': end_cap_analysis['head_safety_factor']
        }
        # --- F4-2 (v2.6.27, bebek-Scofield): HÜKÜM TOTOLOJİK SF'DEN TÜREMEZ --
        # Alt analizlerin her biri kendi ``safety_factor_is_tautological``
        # bayrağını ZATEN yazıyordu; bu fonksiyon onları OKUMUYOR, hepsinin
        # minimumunu alıp oradan status/risk_level üretiyordu.
        #
        # ÖLÇÜLDÜ (HEAD f9d95eb; steel_4130, Pc = 40 bar, D = 100 mm,
        # d_boğaz = 20 mm, F = 3 kN):
        #   SF hedefi 2,0 -> minimum_safety_factor = 2,000000, UNSAFE/HIGH
        #   SF hedefi 3,0 -> minimum_safety_factor = 3,000000, ACCEPTABLE/LOW
        #   SF hedefi 4,0 -> minimum_safety_factor = 4,000000, ACCEPTABLE/LOW
        # yani altı basamak boyunca kullanıcının kendi girdisi. Daha ağırı:
        # kullanıcı GERÇEK cidar verse bile (doğrulama modu) hüküm değişmiyor,
        # çünkü lüle ve kapak çağrıları gerçek kalınlık ALMIYOR, hep 'size'
        # modunda kalıyor ve minimumu onlar çiviliyor:
        #   cidar  2 mm -> hazne SF  3,057 ... minimum_safety_factor = 3,000
        #   cidar  5 mm -> hazne SF  7,643 ... minimum_safety_factor = 3,000
        #   cidar 10 mm -> hazne SF 13,783 ... minimum_safety_factor = 3,000
        # Kullanıcının kazandığı doğrulama, iki totolojik aday tarafından
        # tamamen maskeleniyordu. app.py'deki uç kapısı bunu göremez: o yalnız
        # ``chamber_analysis.design_mode``'a bakar ve burada 'verify' yazar.
        #
        # SÖZLEŞME (defterdeki vessel_status PASS -> NOT_EVALUATED deseniyle
        # AYNI): ONAY geri çekilir, UYARI çekilmez. Minimum SF ve sayıların
        # tamamı KALIR (gerçekten hesaplandılar, ayrıca uyarıları onlar
        # üretir); yalnız HÜKÜM, minimumu belirleyen adayın kazanılmış olup
        # olmadığına bağlanır.
        # Varsayılan True'dur ve bu BİLİNÇLİDİR: bayrağı olmayan bir emniyet
        # katsayısının kazanıldığı KANITLANAMAZ, dolayısıyla ondan onay
        # çıkarılamaz. Alt analiz bayrağı düşürürse hüküm geri çekilir —
        # sessizce kabule dönmez.
        sf_tautological = {
            'chamber_hoop': bool(
                chamber_analysis.get('safety_factor_is_tautological', True)),
            'chamber_von_mises': bool(
                chamber_analysis.get('safety_factor_is_tautological', True)),
            'nozzle': bool(
                nozzle_analysis.get('safety_factor_is_tautological', True)),
            'end_cap': bool(
                end_cap_analysis.get('safety_factor_is_tautological', True)),
        }
        # ÖH P5B1-17: KESKİN harita — "sayı hedefin geri okunması mı?".
        # Her alt blok bu soruyu KENDİ ``safety_factor_reads_back_target``
        # alanında zaten yanıtlıyordu (P14H1-C4 / Z4); burada tek haritada
        # toplanır ve yayımlanan ``safety_factor_is_tautological`` bu
        # haritadan doldurulur. Hazne iki adayı (hoop, von Mises) aynı
        # bloğun cevabını paylaşır; von Mises hoop'tan TÜREDİĞİ için ayrı
        # bir geri-okuma sorusu doğurmaz.
        _hazne_geri = bool(
            chamber_analysis.get('safety_factor_reads_back_target', False))
        sf_reads_back_target = {
            'chamber_hoop': _hazne_geri,
            'chamber_von_mises': _hazne_geri,
            'nozzle': bool(
                nozzle_analysis.get('safety_factor_reads_back_target', False)),
            'end_cap': bool(
                end_cap_analysis.get('safety_factor_reads_back_target',
                                     False)),
        }
        if buckling_analysis is not None:
            sf_candidates['buckling_axial'] = buckling_analysis['axial_buckling_safety_factor']
            # Burkulma, hazne cidarının DEĞERLENDİRİLEN kalınlığıyla çözülür;
            # o kalınlık HRMA tarafından boyutlandırıldıysa burkulma hükmü de
            # kazanılmamıştır (girdi zinciri aynı).
            sf_tautological['buckling_axial'] = sf_tautological['chamber_hoop']
            # Keskin eksende de AYNI girdi zinciri: burkulma katsayısı
            # hazne cidarından çözülür. (Sayısı hedefin ÜSTÜNDE olabilir —
            # ölçüldü 2.911 → 19.589.976 — ama bu onu "hedefin geri
            # okunması" yapmaz; hareket eden bir sayı totoloji değildir.)
            sf_reads_back_target['buckling_axial'] = \
                sf_reads_back_target['chamber_hoop']

        min_safety_factor = min(sf_candidates.values())

        # Minimumu belirleyen aday(lar): hepsi totolojikse hüküm kazanılmamış.
        binding = [k for k, v in sf_candidates.items()
                   if v <= min_safety_factor * (1.0 + 1e-12)]
        binding_tautological = bool(
            binding and all(sf_tautological.get(k, True) for k in binding))
        earned = {k: v for k, v in sf_candidates.items()
                  if not sf_tautological.get(k, True)}
        target_derived = {k: v for k, v in sf_candidates.items()
                          if sf_tautological.get(k, True)}
        min_earned_safety_factor = min(earned.values()) if earned else None

        # --- Z4 / P5B1-01: HÜKÜM KAZANILMIŞ SF'DEN, HEDEF YALNIZ KIYAS -----
        # F4-2 hükmü sepetin MİNİMUMUNDAN üretiyordu ve o minimumu ürün
        # yolunda daima HRMA'nın kendi boyutlandırdığı istasyonlar (lüle,
        # kapak) çiviliyordu. Sonuç ölçüldü (HEAD 09f3207, çelik 4130,
        # Pc = 40 bar, D = 100 mm, d_boğaz = 20 mm, cidar 20 mm):
        #   SF hedefi 1,0 -> minimum 1,0000 -> UNSAFE/HIGH  (kazanılmış 21,58)
        #   SF hedefi 2,0 -> minimum 2,0000 -> UNSAFE/HIGH  (kazanılmış 21,58)
        #   SF hedefi 2,5 -> minimum 2,5000 -> MARGINAL     (kazanılmış 21,58)
        # yani hüküm, kullanıcının KENDİ hedefinin geri okunmasıydı; ve
        # sabit hedefte cidar kalınlaştıkça hüküm KÖTÜLEŞİYORDU (2,5 mm
        # ACCEPTABLE -> 20 mm NOT_EVALUATED), çünkü kalın cidarda minimumu
        # totolojik adaylar devralıyordu.
        #
        # Yeni sözleşme üç sayıyı ADIYLA ayırır ve hiçbirini silmez:
        #   * ``minimum_safety_factor``      — sepetin minimumu (değişmedi),
        #   * ``verdict_safety_factor``      — hükmün ÇIKTIĞI sayı,
        #   * ``design_target_assessment``   — hedefin kendi notu (kıyas).
        #
        # Hüküm kuralı (F4-2'nin "onay geri çekilir, uyarı çekilmez"
        # ilkesi KAZANILMIŞ sayılara uygulanmış hâlidir):
        #   1. Hiçbir istasyon kazanılmadıysa -> NOT_EVALUATED (fail-closed).
        #   2. Kazanılmış minimum bir UYARI (MARGINAL/UNSAFE) üretiyorsa ->
        #      yayımlanır; bu ÖLÇÜLMÜŞ bir tehlikedir, asla susturulmaz.
        #   3. Kazanılmış minimum bir ONAY (SAFE/ACCEPTABLE) üretiyorsa
        #      ancak ve ancak SEPETTEKİ HER İSTASYON kazanılmışsa verilir;
        #      biri bile HRMA tarafından boyutlandırıldıysa onay o istasyon
        #      için kazanılmamıştır -> NOT_EVALUATED + gerekçe.
        # Kısmi kapsamın kendi notu ``measured_scope_status`` alanında durur;
        # manşete çıkmaz, çünkü değerlendirilmemiş istasyonu kapsamaz.
        #
        # ÖNEMLİ AYRIM (ölçüldü, hibrit ürün koşumu 09f3207): "boyutlandırma
        # modu" sayının HEDEFİN GERİ OKUNMASI olduğunu KENDİLİĞİNDEN
        # göstermez. Boyutlandırma yalnız BASINÇ hoop'unu hedefe oturtur;
        # yayımlanan emniyet katsayısı termal hoop'u da içerir. Gerçek koşum:
        # hedef 4,0 iken ``chamber_hoop = 1,7173`` (T_iç = 3283,9 K) — bu sayı
        # ÇİZİLEN cidarda hesaplanmıştır ve hedefin ALTINDADIR, yani ölçülmüş
        # bir yetmezliktir. Onu "totolojik" sayıp susturmak, F4-2'nin
        # korumak istediği ŞEYİ yok ederdi (gerçek uyarı susturulamaz).
        # Ayrım: boyutlandırılmış bir istasyonun sayısı HEDEFİN ÜSTÜNDEYSE
        # tavanı hedeftir (geri okuma); ALTINDAYSA boyutlandırmanın
        # kapsamadığı bir yük onu aşağı çekmiştir (ölçüm).
        hedef_sf = chamber_analysis.get('design_safety_factor_target')
        try:
            hedef_sf = float(hedef_sf)
            if not np.isfinite(hedef_sf) or hedef_sf <= 0:
                hedef_sf = None
        except (TypeError, ValueError):
            hedef_sf = None
        readback, deficient = {}, {}
        for ad, deger in target_derived.items():
            # Hedef bilinmiyorsa sayı geri okuma SAYILMAZ (fail-closed:
            # bilinmeyen bir sayıyı susturmak yerine hükme sokarız; onay
            # zaten kazanılmış katsayı ister).
            if hedef_sf is not None and deger >= hedef_sf * (1.0 - 1e-9):
                readback[ad] = deger
            else:
                deficient[ad] = deger
        # Hükmü besleyen havuz: kazanılmış + hedefin altına düşmüş ölçümler.
        measured = dict(earned)
        measured.update(deficient)
        min_measured = min(measured.values()) if measured else None

        verdict_scope = sorted(measured)
        verified_stations = sorted(earned)
        stations_not_verified = sorted(target_derived)
        stations_reading_back_target = sorted(readback)
        measured_status, measured_risk = classify_safety_factor(min_measured)

        verdict_withheld_reasons = []
        if min_measured is None:
            status = risk_level = STRUCTURAL_VERDICT_NOT_EVALUATED
            verdict_withheld_reasons.append('no_station_verified')
        else:
            status, risk_level = measured_status, measured_risk
            if (status in STRUCTURAL_APPROVAL_VERDICTS
                    and stations_not_verified):
                # ONAY tam kapsam ister: bir istasyon bile HRMA tarafından
                # boyutlandırıldıysa o istasyon için kabul KAZANILMAMIŞTIR.
                status = risk_level = STRUCTURAL_VERDICT_NOT_EVALUATED
                verdict_withheld_reasons.append('stations_not_verified')
        # --- V3 yapi-sf 2. tur (karar §28-24 (C)): MODEL GEÇERLİLİK SINIRI
        # Hazne geçerlilik sınırı dışında değerlendirildiyse (erime noktası
        # ya da düşürme verisinin sonu üstü) o değerlendirmeden ONAY ve
        # SAYISAL tasarım hükmü çıkmaz: gerekçe eklenir, onay tavana çekilir,
        # ``verdict_safety_factor``/``headline_safety_factor`` None olur
        # (verdict_withheld). UYARI susturulmaz (F4-2 ilkesi) ama künye onun
        # MEVCUT MODELİN uyarısı olduğunu söyler.
        model_validity_exceeded = bool(
            model_validity
            and model_validity.get('model_validity_limit_exceeded'))
        if model_validity_exceeded:
            verdict_withheld_reasons.append(
                STRUCTURAL_MODEL_VALIDITY_WITHHELD_REASON)
            if status in STRUCTURAL_APPROVAL_VERDICTS:
                status = risk_level = STRUCTURAL_VERDICT_NOT_EVALUATED
            if measured_status in STRUCTURAL_APPROVAL_VERDICTS:
                measured_status = measured_risk = (
                    STRUCTURAL_VERDICT_NOT_EVALUATED)
        verdict_withheld = bool(verdict_withheld_reasons)

        verdict_safety_factor = (None if verdict_withheld else min_measured)
        # Hedefin kendi notu: SAYININ NE OLDUĞU söylenerek. Bu bir hüküm
        # DEĞİLDİR — HRMA'nın kendi boyutlandırdığı istasyonlar hedefi
        # sağlayacak şekilde çizildiği için sayı hedefin ta kendisidir;
        # merdiven burada TASARIM HEDEFİNİ notlandırır, donanımı değil.
        min_readback = min(readback.values()) if readback else None
        target_status, target_risk = classify_safety_factor(min_readback)
        design_target_assessment = {
            'design_safety_factor_target': hedef_sf,
            'target_derived_minimum_safety_factor': min_readback,
            'stations': stations_reading_back_target,
            'status': target_status,
            'risk_level': target_risk,
            'basis': (
                'These stations were SIZED by HRMA to meet the design safety '
                'factor target, so their safety factor is that target read '
                'back (target x allowances), not a measurement. The status '
                'above grades THE TARGET, not the hardware: it says what the '
                'sized sections would achieve if built exactly as HRMA sized '
                'them. Supply the real thickness of each station to turn it '
                'into a verification.'),
        }
        # V3 yapi-sf 7. tur (karar §28-44): aynı geçerlilik bloğunun devamı —
        # hedef notu, yorulma ve burkulma ONAYLARI da yayımlanmaz (TEK işlev:
        # ``withhold_model_validity_approvals``; bayrak FALSE iken çağrılmaz,
        # yani geçerlilik içi bit-aynı).
        model_validity_approvals_withheld = (
            withhold_model_validity_approvals({
                'safety_analysis.design_target_assessment':
                    design_target_assessment,
                'fatigue_analysis': fatigue_analysis,
                'buckling_analysis': buckling_analysis,
            }) if model_validity_exceeded else [])

        # SICAKLIK MARJI (v2.5.2): gerilme emniyet faktoru tek basina
        # yeterli degil. Sogutmasiz ince metal cidar kesit boyunca neredeyse
        # IZOTERMALDIR (bkz. _estimate_wall_delta_T), yani termal gradyan
        # gerilmesi kucuk kalir ve SF yuksek cikar; asil tehlike cidarin
        # butun olarak malzeme servis sinirina yaklasmasidir (yumusama,
        # surunme, ani mukavemet kaybi). Onceki surumler bu tehlikeyi
        # fiziksel olmayan bir gradyan varsayimiyla dolayli isaret ediyordu;
        # simdi dogrudan sicaklik marjindan degerlendirilir.
        T_derate = wall_temperature_K or chamber_analysis.get('wall_temperature_K')
        # F074: servis siniri TEPE (ic yuz) sicaklikta sinanir.
        T_peak = (peak_wall_temperature_K
                  or chamber_analysis.get('wall_temperature_inner_K')
                  or T_derate)
        T_service = mat_props.get('max_service_temp')
        thermal_margin_ratio = None
        exceeds_service_temp_peak = False
        if T_peak and T_service:
            thermal_margin_ratio = float(T_peak) / float(T_service)
            exceeds_service_temp_peak = bool(float(T_peak) > float(T_service))
            severity = None
            if thermal_margin_ratio >= 1.0:
                severity = ('UNSAFE', 'HIGH')
            elif thermal_margin_ratio >= 0.85:
                severity = ('MARGINAL', 'MEDIUM')
            elif thermal_margin_ratio >= 0.70:
                severity = ('ACCEPTABLE', 'LOW')
            if severity is not None:
                rank = {'SAFE': 0, 'ACCEPTABLE': 1, 'MARGINAL': 2, 'UNSAFE': 3}
                if status == STRUCTURAL_VERDICT_NOT_EVALUATED:
                    # Hüküm geri çekilmişken termal değerlendirme yalnız
                    # UYARI yönünde konuşabilir. Termal marj cidar
                    # kalınlığından bağımsızdır, yani totolojik değildir;
                    # MARGINAL/UNSAFE gerçek bir tehlikedir ve tavanı deler.
                    # 'ACCEPTABLE' ise bir onaydır ve geri çekilmiş hükmü
                    # yeniden ayağa kaldıramaz.
                    if severity[0] in ('MARGINAL', 'UNSAFE'):
                        status, risk_level = severity
                elif rank[severity[0]] > rank[status]:
                    status, risk_level = severity

        # UNSAFE durumunda hangi yükün domine ettiğini açıkla (Dalga 0):
        # termal gerilme basınç gerilmesini aşıyorsa sorun soğutma/malzeme
        # kaynaklıdır, cidar kalınlaştırmak tek başına çözmez.
        explanation = ''
        if status == 'UNSAFE':
            thermal = chamber_analysis.get('thermal_hoop_stress', 0.0)
            pressure = chamber_analysis.get('pressure_hoop_stress', 0.0)
            explanation = ('thermal-dominated' if thermal > pressure
                           else 'pressure-dominated')

        # Hükmün gerekçesi — DÖRT dal, hepsi hangi SAYIdan konuşulduğunu
        # adıyla söyler (kimse "bu bir doğrulamadır" derken hedefi geri
        # okumaz).
        _kapsam = ', '.join(verdict_scope) or 'none'
        _dis = ', '.join(stations_not_verified) or 'none'
        _eko = ', '.join(stations_reading_back_target) or 'none'
        if model_validity_exceeded:
            verdict_basis_text = MODEL_VALIDITY_VERDICT_BASIS
        elif 'no_station_verified' in verdict_withheld_reasons:
            verdict_basis_text = (
                'No acceptance is issued and no verdict is issued at all: '
                'every safety factor in this response ('
                + _eko + ') is the design target read back - HRMA sized those '
                'sections to meet the target, so the number cannot fall below '
                'it and carries no information about a wall you built. Supply '
                'the real wall / throat / head thickness to earn a verdict; '
                'the target itself is graded in design_target_assessment.')
        elif 'stations_not_verified' in verdict_withheld_reasons:
            verdict_basis_text = (
                'No acceptance is issued: the measured sections (' + _kapsam
                + ') would pass, but ' + _dis + ' were sized by HRMA and '
                'therefore not verified. An acceptance that does not cover '
                'every station is not an acceptance. The measured-scope '
                'result is published separately in measured_scope_status.')
        elif status in ('MARGINAL', 'UNSAFE'):
            verdict_basis_text = (
                'The verdict comes from verdict_safety_factor, the lowest '
                'safety factor actually measured on a drawn wall (' + _kapsam
                + '). This is a measured warning and is never suppressed. '
                'Sections not verified: ' + _dis + '; of those, ' + _eko
                + ' only read the design target back.')
        else:
            verdict_basis_text = (
                'Every station in the basket was evaluated against a '
                'user-supplied thickness (' + _kapsam + '), so the verdict is '
                'an independent verification drawn from '
                'verdict_safety_factor.')

        # Öneriler artık {code, params, severity} kaydı olarak döner (D-track):
        # sabit İngilizce metin sızmasını önler, frontend TF() ile çevirir.
        recommendations = []
        # Z4: "cidarı kalınlaştır" ÖĞÜDÜ de hükümle aynı sayıdan çıkar.
        # Eskiden sepet minimumundan çıkıyordu; 20 mm cidarı olan (kazanılmış
        # SF 21,58) bir kullanıcı, YALNIZCA SF hedefi 2,0 olduğu için
        # "cidarı kalınlaştır" öğüdü alıyordu — kusurun yarattığı zararın ta
        # kendisi (kalınlaştırınca hüküm daha da kötüleşiyordu).
        # --- ÖH D22 / OH-Z4-03: ÖĞÜT DE ÖLÇÜLMÜŞ SAYIDAN ÇIKAR ---------
        # Z4 zararlı vakayı kapatmıştı (kalın cidarlı kullanıcı artık
        # "cidarı kalınlaştır" öğüdü almıyor), ama HİÇBİR istasyon
        # ölçülmemişken öğüt hâlâ hedef EKOSUNDAN çıkabiliyordu.
        # ÖLÇÜLDÜ (``once.json`` OH-Z4-03; cidar VERİLMEDEN, yani
        # ``verdict_scope = []``, ``verdict_withheld = true``):
        #   SF hedefi 1,5 -> minimum 1,5000 -> 4 öneri
        #                    (increase_wall_thickness, higher_strength_material,
        #                     increase_chamber_wall, increase_nozzle_throat)
        #   SF hedefi 2,0 -> minimum 2,0000 -> aynı 4 öneri
        #   SF hedefi 4,0 -> minimum 4,0000 -> 0 öneri
        # Yani ekrandaki öğüt kullanıcının CİDARINI değil, kendi HEDEFİNİ
        # tarif ediyordu: hedefini 1,5 yazan kullanıcıya, hiç cidar
        # göndermemişken "cidarı kalınlaştır" deniyordu.
        #
        # Kural, hükümle AYNI kuraldır (fail-closed): öğüt ancak ÖLÇÜLMÜŞ
        # bir sayıdan verilir. Hedefin geri okunduğu istasyon için öğüt
        # ÜRETİLMEZ; nedeni ``recommendation_basis`` ile ADIYLA yazılır ve
        # hedefin kendi notu ``design_target_assessment``te zaten durur.
        # UYARI SUSTURULMAZ: ölçülmüş bir istasyonun düşük sayısı eskisi
        # gibi öğüt üretir (yeni bir eşik ya da metin YOK).
        _olculdu = {ad: not sf_reads_back_target.get(ad, False)
                    for ad in ('chamber_hoop', 'nozzle', 'end_cap')}
        recommendation_sf = min_measured
        if recommendation_sf is not None and recommendation_sf < 3.0:
            recommendations.append(_mk_warning(
                'warn.structural.increase_wall_thickness', 'warning'))
            recommendations.append(_mk_warning(
                'warn.structural.higher_strength_material', 'warning'))
        if (_olculdu['chamber_hoop']
                and chamber_analysis['hoop_safety_factor'] < 3.0):
            recommendations.append(_mk_warning(
                'warn.structural.increase_chamber_wall', 'warning'))
        if _olculdu['nozzle'] and nozzle_analysis['safety_factor'] < 3.0:
            recommendations.append(_mk_warning(
                'warn.structural.increase_nozzle_throat', 'warning'))
        recommendation_basis = (
            'Thickness / material recommendations are drawn ONLY from safety '
            'factors measured on a drawn wall. Stations whose factor is the '
            'design target read back (' + (', '.join(
                ad for ad, olc in sorted(_olculdu.items()) if not olc)
                or 'none') + ') issue no advice, because the number '
            'describes the target you typed, not the hardware; the target '
            'itself is graded in design_target_assessment. Supply the real '
            'wall / throat / head thickness to earn advice for those '
            'stations.')
        # YENI uyarilar (termal + burkulma + ince-cidar)
        if chamber_analysis.get('thermal_hoop_stress', 0.0) > chamber_analysis.get('pressure_hoop_stress', 0.0):
            recommendations.append(_mk_warning(
                'warn.structural.thermal_stress_dominates', 'warning'))
        if not chamber_analysis.get('thin_wall_valid', True):
            recommendations.append(_mk_warning(
                'warn.structural.thin_wall_invalid', 'warning'))
        if buckling_analysis is not None and buckling_analysis['axial_buckling_safety_factor'] < 2.0:
            recommendations.append(_mk_warning(
                'warn.structural.axial_buckling_risk', 'warning'))
        derate = chamber_analysis.get('yield_strength_used_MPa')
        if derate is not None and derate < mat_props['yield_strength'] / 1e6 * 0.7:
            recommendations.append(_mk_warning(
                'warn.structural.severe_derating', 'warning'))

        if thermal_margin_ratio is not None and thermal_margin_ratio >= 0.85:
            recommendations.append(_mk_warning(
                'warn.structural.thermal_margin_service_limit', 'warning'))

        return {
            'minimum_safety_factor': min_safety_factor,
            'risk_level': risk_level,
            'status': status,
            'explanation': explanation,
            'safety_factors': sf_candidates,
            # --- F4-2 (v2.6.27): hükmün KAZANILIP kazanılmadığı -----------
            # Sayılar silinmez; ne oldukları adıyla yazılır.
            #
            # ÖH ONARIMI (defter P5B1-17) — BU HARİTA ARTIK KESKİN ÖLÇÜTLE
            # DOLDURULUR. Eskiden ``design_mode == 'size'`` tek ölçüttü ve
            # harita FAZLA İDDİA ediyordu: bir totoloji "girdinin geri
            # okunması"dır, dolayısıyla TASARIMLA HAREKET EDEMEZ; oysa
            # ölçüldü (REF_MOTOR, SF hedefi 4,80) — bayrak beş adayda da
            # True iken Pc 40 → 3000 bar'da chamber_hoop 5,7600 → 0,9741,
            # chamber_von_mises 6,6511 → 0,5747 hareket ediyordu. Sayı
            # hedefin ALTINA düşmüşse boyutlandırmanın kapsamadığı bir yük
            # (termal hoop, derating) onu aşağı çekmiştir: o bir ÖLÇÜMDÜR,
            # susturulacak bir geri okuma değil. Keskin ölçüt her alt blokta
            # Z4'ten beri VARDI (``safety_factor_reads_back_target``);
            # burada yalnız yayımlanan haritaya BAĞLANDI.
            #
            # ESKİ ANLAM KAYBOLMADI: "bu istasyonun cidarını HRMA mı seçti?"
            # sorusu ``safety_factor_station_sized_by_hrma`` adıyla, yani
            # ADI KADAR iddia eden bir alanla yayımlanır ve HÜKÜM MAKİNESİ
            # (earned / target_derived / verdict_withheld) DEĞİŞMEDEN o
            # haritayı okumaya devam eder — fail-closed davranış ve Z4
            # kazanımı korunur.
            'safety_factor_is_tautological': sf_reads_back_target,
            'safety_factor_station_sized_by_hrma': sf_tautological,
            'safety_factor_is_tautological_basis': (
                'per-station map, SHARP definition: true only when the '
                'station was sized by HRMA AND the published factor reads '
                'the design target back (factor >= target). A sized station '
                'whose factor fell BELOW the target is a measurement (a '
                'load the sizing did not cover pulled it down) and is NOT '
                'marked tautological. The looser question - "did HRMA pick '
                'this wall?" - is published as '
                'safety_factor_station_sized_by_hrma and is what the verdict '
                'machinery uses (fail-closed).'),
            'binding_safety_factors': binding,
            'binding_safety_factor_is_tautological': binding_tautological,
            # --- P14H1-C4 / Z4-B UZLAŞMASI: İKİ SORU, İKİ ALAN ------------
            # Panel ölçümü (Z4-B, 27 Ağu) aynı ekranda iki beyanın
            # çeliştiğini gösterdi: hibrit varsayılan yükünde
            # ``binding_safety_factor_is_tautological: true`` basılırken
            # binding istasyon (``chamber_hoop``, 1,7173) geri-okuma
            # envanterinde YOKTU. Ölçüldü ve kök doğrulandı: iki alan AYNI
            # soruyu sormuyor.
            #   * ``..._is_tautological``  -> "bu istasyonun cidarını HRMA mı
            #     seçti?" (``design_mode == 'size'``). Hibritte EVET.
            #   * ``..._reads_back_target`` -> "yayımlanan sayı tasarım
            #     hedefinin geri okunması mı?" Hibritte HAYIR: hedef 4,0,
            #     sayı 1,7173 — termal hoop gerilmesi onu hedefin ALTINA
            #     çekmiş, yani sayı ölçülmüştür.
            # İkisi soğuk koşumlarda ÇAKIŞIR (sayı hedefe oturur), sıcak
            # cidarda AYRIŞIR. Hüküm ve ekran ikincisini okumalıdır;
            # birincisi "kimin cidarı" sorusunun cevabıdır ve F4-2'den beri
            # ihraç/PDF katmanı onu o anlamda kullanıyor (adı bu yüzden
            # DEĞİŞTİRİLMEDİ; anlamı burada yazılı).
            'binding_safety_factor_reads_back_target': bool(
                binding and all(k in readback for k in binding)),
            'binding_safety_factor_is_tautological_basis': (
                "'tautological' here means the binding station's wall was "
                'SIZED by HRMA (design_mode == size), i.e. it was not checked '
                'against a thickness you supplied. It does NOT mean the '
                'number equals the design target: sizing puts the TOTAL '
                'hoop stress (pressure + thermal) on the target, and where no '
                'thickness reaches it the chamber reports sizing_feasible = '
                'false and the published factor is a measurement below the '
                'target. The sharp answer is '
                'binding_safety_factor_reads_back_target; the per-station '
                'inventory is stations_reading_back_target.'),
            'minimum_earned_safety_factor': min_earned_safety_factor,
            # ÖH D22 / OH-Z4-03: öğüt hangi sayıdan çıktı.
            'recommendation_basis': recommendation_basis,
            'verdict_withheld': verdict_withheld,
            # --- Z4 (P5B1-01): hükmün ÇIKTIĞI sayı ve kapsamı -------------
            # ``minimum_safety_factor`` sepetin minimumudur ve KALIR (uyarı
            # üretimi, panel geçmişi, ihraç zinciri onu okuyor). Hükmün
            # dayandığı sayı ayrı bir addır; ikisi ayrışabilir ve ayrıştığı
            # yerde okuyucu hangisinin ne olduğunu alan adından görür.
            'minimum_safety_factor_basis': (
                'lowest of all computed safety factors, including the '
                'sections HRMA sized itself; it is NOT the number the verdict '
                'is drawn from (see verdict_safety_factor)'),
            # --- ÖH D22 / P7B3-23: MANŞET SAYISI TEK ADLA ---------------
            # ÖLÇÜLDÜ (``once.json`` P7B3-23; Pc 40 bar, Ø100 mm,
            # d_boğaz 20 mm, steel_4130): cidar 5/15/25/35/45 mm için
            # ``minimum_safety_factor`` SABİT 3,9999999999999996 (kullanıcının
            # SF hedefinin geri okunması) iken ``minimum_earned_safety_factor``
            # 7,6433 -> 17,9935 -> 24,4657 -> 28,7890 -> 31,8224 çıkıyordu.
            # İki sayı da yayımlanıyor ve ikisi de künyeli; kusurun kalan
            # ayağı, hangisinin MANŞET olduğunu söyleyen bir alanın
            # OLMAMASIydı — panel, PDF ve STEP notu üç ayrı katmanda kendi
            # seçimini yapıyordu ve "SF 4,0" ile "kazanılmış 25,46" aynı
            # rapordan okunabiliyordu.
            #
            # Kural hükümle AYNI kuraldır (fail-closed): manşete yalnız
            # KAZANILMIŞ hüküm sayısı çıkar. Hüküm geri çekilmişse manşet
            # sayısı YOKTUR (None) — hedefin geri okunması manşete
            # terfi ettirilmez. Yeni bir sayı hesaplanmaz: alan yalnız
            # var olan ``verdict_safety_factor``ı ADIYLA manşete bağlar.
            'headline_safety_factor': verdict_safety_factor,
            'headline_safety_factor_source': (
                'verdict_safety_factor (lowest safety factor measured on a '
                'drawn wall, full basket scope)'
                if verdict_safety_factor is not None else
                'none: the verdict is withheld ('
                + (', '.join(verdict_withheld_reasons) or 'unknown')
                + '), so no safety factor is promoted to the headline. '
                  'minimum_safety_factor is the basket minimum and can be '
                  'the design target read back; minimum_earned_safety_factor '
                  'covers only the stations that were actually measured. '
                  'Neither is a headline verdict.'),
            'verdict_safety_factor': verdict_safety_factor,
            'verdict_safety_factor_source': (
                'lowest safety factor actually measured on a drawn wall '
                '(user-supplied thickness, or an HRMA-sized station whose '
                'safety factor fell BELOW its own design target)'
                if verdict_safety_factor is not None
                else 'none (verdict withheld)'),
            'verdict_scope': verdict_scope,
            'verified_stations': verified_stations,
            'stations_not_verified': stations_not_verified,
            'stations_reading_back_target': stations_reading_back_target,
            'verdict_withheld_reasons': verdict_withheld_reasons,
            # Kısmi kapsamın kendi notu: ÖLÇÜLMÜŞ istasyonlar için ne
            # çıktığı. Manşet DEĞİLDİR (kapsamadığı istasyon var). Ad
            # bilerek 'earned' değil: havuz kazanılmış katsayılara ek
            # olarak hedefinin altına düşmüş boyutlandırılmış istasyonları
            # da içerir (``minimum_earned_safety_factor`` KATI anlamını
            # korur).
            'measured_scope_status': measured_status,
            'measured_scope_risk_level': measured_risk,
            # Geriye dönük ALIAS (aynı değer, eski ad). Yapısal panel bu
            # dalgada ``earned_scope_*`` adıyla bağlandı; ad
            # ``measured_scope_*`` olarak düzeltildi (havuz yalnız
            # kazanılmış katsayıları değil, hedefinin altına düşmüş
            # boyutlandırılmış istasyonları da içeriyor ve
            # ``minimum_earned_safety_factor``ın KATI anlamıyla
            # karıştırılmamalı). Panel yeni adı okuyunca bu iki satır
            # düşer — o zamana dek ekranın fail-closed '—' basmaması için
            # duruyor.
            'earned_scope_status': measured_status,
            'earned_scope_risk_level': measured_risk,
            'design_target_assessment': design_target_assessment,
            # NOT: anahtar adı bilerek ``verdict_basis`` DEĞİL — uç katmanı
            # (app.py::_withhold_unearned_structural_verdict) o adı kendi
            # metniyle doldurur ve yalnız hazne moduna bakar. İki metin
            # çakışırsa okuyucu hangisinin doğru olduğunu bilemez; modülün
            # gerekçesi kendi adıyla durur.
            'minimum_safety_factor_verdict_basis': verdict_basis_text,
            # V3 yapi-sf 2. tur (C): hükmün geçerlilik bayrağı (kanonik alan
            # chamber_analysis.model_validity_limit_exceeded).
            'model_validity_limit_exceeded': model_validity_exceeded,
            # 7. tur: geri çekilen onayların yolları (yalnız boş değilse).
            **({'model_validity_approvals_withheld':
                model_validity_approvals_withheld}
               if model_validity_approvals_withheld else {}),
            # Cidar sicakligi / malzeme servis siniri. 1.0'i asmasi sicaklik
            # kaynakli yetmezlik demektir; gerilme SF'si yuksek olsa bile.
            # F074: oran TEPE (ic yuz) cidar sicakligindan hesaplanir.
            'thermal_margin_ratio': thermal_margin_ratio,
            'peak_wall_temperature_K': T_peak,
            # ÖH P5B1-02: sayının ÜST SINIR mı ÖLÇÜM mü olduğu adıyla.
            'peak_wall_temperature_basis': peak_wall_temperature_basis,
            'derating_wall_temperature_K': T_derate,
            'max_service_temperature_K': T_service,
            'exceeds_max_service_temp_peak': exceeds_service_temp_peak,
            'recommendations': recommendations
        }