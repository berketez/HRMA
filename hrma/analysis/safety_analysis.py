"""
Comprehensive Safety Analysis Module
Safety, hazard, and risk assessment for rocket motor systems
"""

import numpy as np
import json
import re
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

from hrma.constants import G_0 as _G_0
from hrma.utils.input_guard import finite_number
from hrma.constants import STEFAN_BOLTZMANN as _STEFAN_BOLTZMANN
from hrma.data.materials_db import get_material


def _mk_warning(code: str, severity: str = 'info', **params) -> Dict:
    """Yapılandırılmış iki-dilli uyarı/öneri kaydı (D-track sözleşmesi).

    Backend dilsiz kalır; frontend ``TF(code, params)`` ile metni kurar.
    Şema: ``{code: 'warn.<subsystem>.<slug>', params: {...}, severity: ...}``.
    Katalog: docs/v262_specs/D_codes_analysis.md.
    """
    return {'code': code, 'params': params, 'severity': severity}


# ---------------------------------------------------------------------------
# Emniyet modelinin KALİBRASYON sabitleri — TEK tanım noktası.
#
# ÖH D18 / P5B2-18 — KÜNYE ÖLÇÜLEBİLİR BİÇİMDE YANLIŞTI. Burada eskiden
# "Bu blok dışında sayısal sabit yazılmaz; testler de buradan okur." yazıyordu.
# ÖLÇÜLDÜ (taban 9071a64, AST ile; betik
# ``docs/scofield/raw/OH/D18/yapisal-sistem/a1/olcum_p5b218.py``, çıktı
# ``once_p5b218.json``): bu blok DIŞINDA 246 sayısal değişmez, 58 farklı
# değer var. İddia tutmuyordu ve tutamazdı: bu sayıların ezici çoğunluğu
# KALİBRASYON DEĞİL cebirsel/birim sabitidir (0, 1, 2, 3, 4 kuvvet ve indis
# olarak 122 kez; 1000 birim çarpanı olarak 8 kez; 100 yüzde olarak 7 kez).
#
# Bu blok bu yüzden ne olduğunu SÖYLER: modelin KALİBRASYON sabitlerinin —
# eşiklerin, ampirik kesirlerin, beyan edilmiş varsayımların — tek tanım
# noktasıdır. Cebirsel ve birim sabitleri kapsamında DEĞİLDİR.
#
# İki KAZANILMIŞ değişmez, ``tests/test_d18_yapisal_sistem_a1.py`` içindeki
# ``TestP5B218SafetyModelKunyesi`` tarafından ölçülür:
#   1. Buradaki HER anahtar gövdede gerçekten OKUNUR (ölü kalibrasyon
#      sabiti yok). Ölçüldü: taban 15 anahtardan İKİSİ ölüydü —
#      ``loose_motor_range_cap_m`` (5000,0) ve
#      ``relief_setting_fraction_of_design`` (0,85; künyesi "emniyet valfi
#      ayarı tasarım basıncının bu oranıdır" diyor ama hiçbir yerde emniyet
#      valfi ayarı hesaplanmıyordu). İkisi de kaldırıldı: değerleri hiçbir
#      yerde ikinci bir kopya olarak da geçmiyordu (AST taraması), yani ürün
#      davranışı değişmez.
#   2. Blok dışı değişmez sayısı BEYAN EDİLEN tavanı aşamaz (mandal). 252
#      sayısını 135'e indirmek P15 borcudur (çapraz tutarlılık süpürmesi);
#      mandal, borcun sessizce büyümesini engeller.
#
# ÖH D24 / P5B2-18 (Fable-D18 ŞARTı, yol (a) seçildi). D18'de künye
# daraltılmıştı ama "eşiklerin tek tanım noktası" iddiası gövdede HÂLÂ
# tutmuyordu: ÖLÇÜLDÜ (taban 88a29d3, AST; betik
# ``docs/scofield/raw/OH/D24/yapisal-sistem/a1/olcum_p5b218.py``, çıktı
# ``once_p5b218.json``) blok DIŞINDA 50 karşılaştırma literali vardı;
# bunların 12'si 0 ve 4'ü 1 (cebirsel işaret/birim kontrolü), KALAN 34'ü
# gerçek KALİBRASYON eşiğiydi. O 34 literal bu bloğa adlı anahtar olarak
# taşındı ve gövde artık ``SAFETY_MODEL['…']`` ile okuyor. Kalan 16
# karşılaştırma literali yalnız 0 ve 1'dir.
#
# ÜÇÜNCÜ kazanılmış değişmez (aynı sınıfta ölçülür):
#   3. Blok dışı KARŞILAŞTIRMA literali sayısı ``P5B218_ESIK_TAVANI``yı
#      aşamaz. Bir eşiği yerel literale geri koymak sayıyı bir artırır ve
#      bekçi kırmızıya döner (ters mutasyonla gösterildi:
#      ``mutasyon.json``). ÖH D27 fix-26a: tavan 16 -> 19; gelen ÜÇ
#      literalin ÜÇÜ de ``0.0`` ve üçü de P5B2-05 onarımının cebirsel
#      işaret kontrolüdür (Z > 0, hedef basınç > 0, küp kök tanımlı).
#      Kalibrasyon literali (0/1 dışı) sayısı DEĞİŞMEDİ: 0.
#
#   4. ÖH D27 fix-26a — FONKSİYON GÖVDESİNDEKİ farklı değer sayısı
#      ``P5B218_GOVDE_FARKLI_DEGERLER`` kümesine yeni değer
#      EKLEYEMEZ (tek yönlü: çıkarmak serbest). Bu, üçüncü değişmezin
#      dar ve asıl hâlidir: modül düzeyinde ADI OLAN sabit künyeyi
#      çiğnemez, gövdeye gömülü ADSIZ sayı çiğner. Aynı P5B2-05
#      değişikliğinde bu sayı 55 -> 50 DÜŞTÜ (el tablosu gövdeden çıktı).
#
# BUGÜNKÜ ÖLÇÜM (aynı betik, bu ağaç): blok dışında 232 sayısal değişmez,
# 66 farklı değer; gövde içinde 50 farklı değer. (Eşiklerin taşınmasıyla
# 246 -> 212 ve 58 -> 55 düşmüştü;
# ÖH D26 / P5B2-05 patlama modelini elle yazılmış Z tablosundan Kinney-Graham
# BAĞINTISINA çevirince 212 -> 227 ve 55 -> 60 çıktı: bağıntının katsayıları
# ve çözüm aralığı artık modülde ADIYLA duruyor — tablo yerine model.
# ÖH D29 / OH-D28-08 hibrit TNT eşdeğerini LOX/RP-1 tablosundan ÇEKİP ALIP
# oksitleyicinin ayrışma entalpisinden TÜRETİNCE 227 -> 235 ve 60 -> 66
# oldu. Sekiz yeni değişmezin HEPSİ modül düzeyinde ADI OLAN literatür
# sabitidir (dH_G iki değer, molar kütle iki değer, TNT tanım referansı,
# makalenin yayımladığı iki doğrulama düğümü, cal/kcal ölçek çarpanı) —
# mandalın asıl derdi olan GÖVDEYE GÖMÜLÜ ADSIZ sayı 50'de KALDI:
# ``_resolve_hybrid_explosive_class`` gövdesinde tek bir sayısal literal
# yoktur, katsayı türetimden gelir.
# ÖH D36 / onemli2-sivi a2: künye 235 diyordu, taban ağacında ölçüm 234'tü
# (bekçi zaten kırmızıydı); a2 yanma süresi yedeklerini (iki
# ``get('burn_time', 10)``, bir ``or 10``, iki ``burn_time=10.0`` imza
# varsayılanı) kaldırınca 234 -> 229 oldu. Farklı değer sayısı (66) ve
# gövde içindeki farklı değer sayısı (50) değişmedi: 10 başka yerlerde de
# geçiyor.
# ÖH D37 A1b panel-js 6. tur (14 Eki): katı katalog kuralı ve geri çekme
# iletileri üç yeni literal getirdi (iki ``[:60]`` ad kırpma uzunluğu, bir
# ``[0]`` dizini) → 229 -> 232. Farklı değer sayısı (66) ve gövde içindeki
# farklı değer sayısı (50) değişmedi: 60 ve 0 başka yerlerde de geçiyor.
# Sayı düşerse ya da yükselirse künye BAYATLAR, bu yüzden
# ``tests/test_d20_yapisal_sistem_a1.py::TestP5B218KunyeOlcumleSenkron``
# künyeyi ölçümle karşılaştırır.)
# ---------------------------------------------------------------------------
SAFETY_MODEL = {
    # Ortam / radyasyon
    'ambient_temperature_k': 293.15,
    # v2.6.27: merkezî tanımdan (hrma/constants.py) — yerel kopya kaldırıldı.
    'stefan_boltzmann': _STEFAN_BOLTZMANN,   # W/m²K⁴ (CODATA 2018)
    'default_surface_emissivity': 0.80,      # oksitlenmiş metal dış yüzey
    'radiant_pain_threshold_w_m2': 2500.0,   # ISO 13732-1 acı eşiği (~2.5 kW/m²)
    # 2. derece yanık doz eşiği: ~1000 (kW/m²)^(4/3)·s  (Eisenberg probit /
    # API 521 termal doz birimi, TDU). Maruziyet süresi yanma süresidir.
    'second_degree_burn_tdu': 1000.0,
    'min_hazard_distance_m': 3.0,
    # Işıyan yüzey alanı bilinmiyorsa varsayılan narinlik (L/D). Sonuç
    # 'radiating_area_basis' alanında AÇIKÇA beyan edilir.
    'assumed_length_to_diameter': 5.0,
    # Kasa kütle kesri — yalnız geometri verilmediğinde kullanılan ampirik
    # yedek; kullanıldığında 'case_mass_basis' alanında beyan edilir.
    'fallback_case_mass_fraction': 0.15,
    'gurney_velocity_ms': 2700.0,            # √(2E), çelik kılıf tipik
    'fragment_drag_limited_range_m': 2000.0,
    'lethal_fragment_mass_kg': 0.01,
    'lethal_kinetic_energy_j': 79.0,         # NATO STANAG 2920
    # ÖH D18 / P5B2-18: 'loose_motor_range_cap_m' (5000,0) ve
    # 'relief_setting_fraction_of_design' (0,85) BURADAN KALDIRILDI — ikisini
    # de gövdenin hiçbir yeri okumuyordu ve değerleri ikinci bir kopya
    # olarak da geçmiyordu (AST taraması). İkincisinin künyesi üstelik
    # yapılmayan bir hesabı ("emniyet valfi ayarı") ilan ediyordu.
    'gravity_m_s2': _G_0,      # hrma.constants (ÖH P10B3-10)

    # -- ÖH D24 / P5B2-18 (ŞART, yol (a)): gövdedeki 34 EŞİK literali
    # buraya adlı anahtar olarak taşındı. Değerlerin HİÇBİRİ değişmedi
    # (çapa A1/A2/A3 + /analyze_safety bit-aynı); taşınan yalnız TANIM
    # NOKTASIdır. Her anahtarın altındaki not, taşındığı yerde zaten
    # yazılı olan dayanağı taşır — yeni bir kaynak İDDİA EDİLMEZ.

    # Yapısal hüküm bantları (akma emniyet katsayısı). Basınçlı kap
    # pratiğiyle uyumlu KABA merdiven; ampirik, tek bir standarttan
    # alınmadı. 'structural_integrity', muayene aralığı ve yapısal risk
    # ekseni AYNI bantları okur.
    'sf_band_safe': 4.0,          # SAFE / 12 aylık muayene / risk 1
    'sf_band_intermediate': 3.0,  # 6 aylık muayene / risk 2
    'sf_band_marginal': 2.0,      # MARGINAL alt sınırı / risk 3
    'sf_band_critical': 1.5,      # yalnız risk ekseni: altı risk 5

    # Basınçlı kap sınıfı (bar, oda basıncı). Sınıf yalnız muayene/cihaz
    # ÖNERİSİ üretir, hüküm üretmez.
    'vessel_high_pressure_bar': 100.0,
    'vessel_medium_pressure_bar': 20.0,

    # Toplam risk skoru bantları (eksen skorları 1..5 ölçeğinde).
    'risk_score_low_max': 2.0,
    'risk_score_medium_max': 3.0,
    'risk_score_high_max': 4.0,

    # Kopma marjı (burst_margin = kopma basıncı / çalışma basıncı).
    'burst_margin_critical': 1.25,
    'burst_margin_adequate': 2.0,

    # TNT eşdeğeri bantları (kg). HD sınıfları ADR/DOT terimleridir;
    # sayısal sınırlar bu modülün kaba kabulüdür, mevzuat alıntısı DEĞİL.
    'tnt_mass_explosion_kg': 100.0,   # risk ekseni: 5
    'tnt_major_blast_kg': 10.0,       # risk ekseni: 4
    'tnt_mass_fire_kg': 5.0,          # HD 1.3 üst sınırı
    'tnt_minor_hazard_kg': 0.5,       # HD 1.4 sınırı = magazin/taşıma tetiği

    # Toksik bulut tehlike mesafesi bantları (m).
    'toxic_high_distance_m': 300.0,
    'toxic_medium_distance_m': 75.0,

    # Sıcak gaz kendiliğinden tutuşma eşiği (K) — katı/hibrit egzozunun
    # yakındaki yanıcıyı tutuşturma riski için kaba ayrım noktası.
    'autoignition_hot_gas_k': 2500.0,

    # Yakıt kütlesine bağlı yangın önlemleri (kg).
    'fire_spread_high_mass_kg': 100.0,
    'fire_spread_medium_mass_kg': 10.0,
    'fixed_deluge_mass_kg': 50.0,
}

# ---------------------------------------------------------------------------
# Hüküm sözcükleri (ÖH Z3) — depo genelinde AYNI sözcük kullanılır:
# app.py'de ``STRUCTURAL_VERDICT_NOT_EVALUATED`` ve
# ``THERMAL_VERDICT_NOT_EVALUATED`` de bu dizeyi taşır. 'LOW'/'ACCEPTABLE'
# sırasına GİRMEZ: paneller bilinmeyen değeri nötr rozetle çizer, yani
# ekranda yeşil onay görünmez.
# ---------------------------------------------------------------------------
THERMAL_VERDICT_NOT_EVALUATED = 'NOT_EVALUATED'
#: ÖH D35 / OH-ON-06 — kazanılmamış yangın/tutuşma hükmünün damgası. Değer
#: termal/toksik eksenlerle AYNI dizedir (tek kaynak): panel ve rapor bu
#: damgayı tek bir kuralla tanır.
FIRE_CLASS_NOT_EVALUATED = THERMAL_VERDICT_NOT_EVALUATED
AUTO_IGNITION_NOT_EVALUATED = THERMAL_VERDICT_NOT_EVALUATED
THERMAL_VERDICT_ISSUED = 'issued'
THERMAL_VERDICT_WITHHELD = 'withheld'

#: ``_resolve_wall_temperatures`` yedek dalının künye ÖNEKİ. Hem künyeyi
#: yazan hem okuyan taraf bu tek sabiti kullanır (dize eşleşmesi kopmasın).
WALL_TEMP_NOT_COMPUTED = 'NOT COMPUTED'

# ---------------------------------------------------------------------------
# ÖH D36 / onemli2-sivi a2 — YANMA SÜRESİ VERİLMEDİYSE VARSAYIM YOK
#
# ÖLÇÜLDÜ (``docs/scofield/raw/OH/D36/onemli2-sivi/a2/once.json`` K3, kulvar
# ``04cf6336``): ``motor_data`` içinde ``burn_time`` YOKKEN bu modül iki
# yerde ``motor_data.get('burn_time', 10)`` ile 10 s UYDURUYORDU ve sayı
# yanıta kullanıcının girdisi gibi giriyordu: ``inputs_used.burn_time_s =
# 10``, termal ``exposure_duration_s = 10,0``, ikinci derece yanık mesafesi
# 0,0565 m, serbest kalan motorun toplam impulsu 250 000 N·s (itki x 10 s),
# yanma sonu hızı 135,78 m/s. LU-1 (Berke onaylı) ile sıvı çözücü süre
# verilmediğinde ``burn_time`` YAYIMLAMIYOR; yol varsayılan akışta erişilir
# hâle geldi.
#
# Kural (eksen bazlı geri çekme, ÖH Z5S / D35 OH-ON-06 deseni): süreye BAĞLI
# her kol ADIYLA geri çekilir (değer ``None`` + durum damgası + gerekçe);
# süreden BAĞIMSIZ kollar (yapısal, basınçlı kap, cidar sıcaklığı ve termal
# gerilme, ışınım tehlike mesafesi, TNT eşdeğeri, toksik, yangın, bağlama
# kuvveti) AYNEN kalır. Süre verildiğinde yayımlanan her sayı bit-aynıdır
# (``a2/sonra.json`` K3).
# ---------------------------------------------------------------------------
#: Geri çekilen kolun durum damgası — deponun hüküm sözcüğü (yukarıdaki
#: blok: termal/toksik/yangın aynı dizeyi taşır; ikinci bir sözcük açılmaz).
BURN_TIME_NOT_EVALUATED = THERMAL_VERDICT_NOT_EVALUATED
#: Geri çekilen her kolun ortak gerekçesi — TEK tanım noktası.
BURN_TIME_NOT_SUPPLIED_REASON = (
    'burn time not supplied: motor_data carries no burn_time and no '
    'duration is assumed (the previous code silently used 10 s), so the '
    'quantities that depend on it were not evaluated. Supply burn_time [s] '
    'to get them.')
#: Süre yokken geri çekilen TERMAL alanlar (``thermal_safety`` içinde).
#: ``thermal_protection_required`` bu demette DEĞİLDİR: ışınım kolu onu
#: KAZANDIYSA (mesafe asgariyi aşıyor) uyarı korunur, kazanmadıysa ayrıca
#: geri çekilir (``_analyze_thermal_safety``).
THERMAL_BURN_TIME_FIELDS = (
    'exposure_duration_s',
    'second_degree_burn_distance_m',
    'recommended_minimum_standoff_m',
)
#: Süre yokken geri çekilen SERBEST KALAN MOTOR alanları (toplam impuls =
#: itki x süre ve ondan türeyenler). Bağlama kuvveti (itki x SF) ve
#: ortalama uçuş kütlesi süreye bağlı DEĞİLDİR, kalır.
UNRESTRAINED_BURN_TIME_FIELDS = (
    'total_impulse_ns',
    'burnout_velocity_ms',
    'kinetic_energy_j',
)


def _yanma_suresi(value):
    """Verilmiş yanma süresi [s] ya da ``None`` (verilmedi) — varsayım YOK.

    Yalnız "verilmedi" ile "verildi" ayrılır; verilen değerin fizik kapısı
    çağıranın işidir (``analyze_comprehensive_safety`` başındaki
    ``_fizik_disi_degilse``). ``None`` ve boş dize "verilmedi" demektir.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return float(value)


# ---------------------------------------------------------------------------
# ÖH D26 / P5B2-05 — PATLAMA AŞIRI-BASINCI: KİNNEY-GRAHAM (TEK KAYNAK)
#
# Kaynak: G. F. Kinney & K. J. Graham, *Explosive Shocks in Air*, 2. baskı,
# Springer 1985, Böl. 5 — serbest-hava (free-air) küresel TNT patlaması için
# tepe aşırı-basıncı ile Hopkinson-Cranz ölçekli mesafesi arasındaki kapalı
# bağıntı. UFC 3-340-02 (2008) aynı ölçeklemeyi kullanır.
#
#     P_s / P_0 = 808 [1 + (Z/4,5)^2]
#                 / sqrt{ [1+(Z/0,048)^2] [1+(Z/0,32)^2] [1+(Z/1,35)^2] }
#
# BOYUT ANALİZİ: Z = R / W^(1/3), [m] / [kg]^(1/3) = m·kg^(-1/3). Bağıntının
# hem payı hem paydası boyutsuzdur (Z bölü boyutsuz katsayılar), dolayısıyla
# P_s/P_0 boyutsuzdur ve P_s, P_0 ile aynı birimdedir (kPa). Katsayılar
# (4,5 / 0,048 / 0,32 / 1,35) m·kg^(-1/3) biriminde ölçekli mesafelerdir.
#
# DOĞRULAMA DÜĞÜMÜ: Z = 1 m/kg^(1/3) -> P_s = 1008 kPa (yayımlanmış referans
# değer). ``kinney_graham_overpressure_kpa`` bu düğümü sağlar; bekçi
# (``tests/test_safety_honesty.py``) bağıntıyı BAĞIMSIZ olarak yeniden kurar
# ve aynı düğümle kendi aracını sınar — kopya değil, çapraz doğrulamadır.
#
# Bu sabitler modülün TEK aşırı-basınç kaynağıdır: ``_calculate_blast_
# distances`` elle yazılmış bir Z tablosu tutmaz, Z'yi buradan ÇÖZER.
# ---------------------------------------------------------------------------
KINNEY_GRAHAM_AMBIENT_KPA = 101.325
KINNEY_GRAHAM_NUMERATOR_COEFF = 808.0
KINNEY_GRAHAM_NUMERATOR_Z = 4.5
KINNEY_GRAHAM_DENOMINATOR_Z = (0.048, 0.32, 1.35)

#: Yayımlanan hasar seviyeleri ve HEDEF tepe aşırı-basınçları [kPa].
#: Seviye adları ve eşikler değişmedi (P05 taban davranışı); değişen tek şey
#: bu hedeflere karşılık gelen mesafenin nereden geldiğidir.
BLAST_OVERPRESSURE_TARGETS_KPA = {
    'lethal': 100.0,
    'serious_injury': 35.0,
    'minor_injury': 7.0,
    'property_damage': 2.0,
}

BLAST_MODEL_BASIS = (
    'Free-air spherical TNT peak overpressure, Kinney & Graham, Explosive '
    'Shocks in Air, 2nd ed. (1985), ch. 5; Hopkinson-Cranz scaling '
    'Z = R / W^(1/3). The scaled distance is solved from that correlation '
    'for the stated target overpressure, not read from a hand-written table.'
)

#: Z çözümünün arandığı aralık [m/kg^(1/3)]. Alt uç yakın-alan (Z=0,05'te
#: bağıntı ~1e5 kPa verir), üst uç uzak-alan (Z=500'de ~0,15 kPa). Aralığın
#: dışına düşen bir hedef basınç için sayı UYDURULMAZ (ValueError).
KINNEY_GRAHAM_Z_BRACKET = (0.05, 500.0)


def kinney_graham_overpressure_kpa(scaled_distance: float) -> float:
    """Ölçekli mesafede tepe aşırı-basıncı [kPa] (Kinney & Graham 1985).

    ``scaled_distance`` Z = R / W^(1/3) [m/kg^(1/3)]. Doğrulama düğümü:
    ``kinney_graham_overpressure_kpa(1.0) ~= 1008 kPa``.
    """
    z = float(scaled_distance)
    if not np.isfinite(z) or z <= 0.0:
        raise ValueError(
            'scaled distance must be a positive finite number; got %r' % (
                scaled_distance,))
    numerator = KINNEY_GRAHAM_NUMERATOR_COEFF * (
        1.0 + (z / KINNEY_GRAHAM_NUMERATOR_Z) ** 2)
    denominator = 1.0
    for zc in KINNEY_GRAHAM_DENOMINATOR_Z:
        denominator *= 1.0 + (z / zc) ** 2
    return KINNEY_GRAHAM_AMBIENT_KPA * numerator / np.sqrt(denominator)


def scaled_distance_for_overpressure(target_kpa: float) -> float:
    """Hedef tepe aşırı-basıncını veren ölçekli mesafe Z [m/kg^(1/3)].

    :func:`kinney_graham_overpressure_kpa` Z'de KESİN AZALANDIR (yakın alanda
    payda Z^3 gibi, pay Z^2 gibi büyür), bu yüzden ikiye bölme yakınsar ve
    çözüm tektir. Hedef, aralığın dışına düşerse sayı uydurulmaz.
    """
    hedef = float(target_kpa)
    if not np.isfinite(hedef) or hedef <= 0.0:
        raise ValueError(
            'target overpressure must be a positive finite number; got %r'
            % (target_kpa,))
    alt, ust = KINNEY_GRAHAM_Z_BRACKET
    if not (kinney_graham_overpressure_kpa(ust) <= hedef
            <= kinney_graham_overpressure_kpa(alt)):
        raise ValueError(
            'target overpressure %.6g kPa is outside the bracket this '
            'correlation is solved on (Z in [%g, %g] -> [%.4g, %.4g] kPa); '
            'no distance is published for it' % (
                hedef, alt, ust,
                kinney_graham_overpressure_kpa(ust),
                kinney_graham_overpressure_kpa(alt)))
    for _ in range(200):
        orta = 0.5 * (alt + ust)
        if kinney_graham_overpressure_kpa(orta) > hedef:
            alt = orta
        else:
            ust = orta
    return 0.5 * (alt + ust)


class NonPhysicalSafetyInput(ValueError):
    """Emniyet hükmü fizik dışı bir büyüklükten ÜRETİLMEZ (ÖH D15 / a3).

    **P5B2-15 / P5B2-16 / P5B2-17 — ÖLÇÜLEN KUSUR** (taban ``8bc001b``,
    kanıt ``docs/scofield/raw/OH/D15/yapisal-sistem/a3/once.json``): ucun
    kapısı Z5S'te kapandı ama MODÜL yüzü açık kaldı; kütüphaneyi doğrudan
    çağıran her yol ya ÇÖKÜYOR ya SESSİZCE hüküm üretiyordu:

    ============================  =========================================
    girdi                          modülün ölçülen davranışı
    ============================  =========================================
    ``wall_thickness = 0``         ``ZeroDivisionError`` (çıplak)
    ``wall_thickness = -0.003``    ``ZeroDivisionError`` (çıplak)
    ``chamber_diameter = 0``       ``ZeroDivisionError`` (çıplak)
    ``propellant_mass = -6``       ``TypeError: '>' not supported between
                                   instances of 'complex' and 'int'``
    ``thrust = -4000``             HÜKÜM: ``required_restraint_force_n =
                                   0,0`` — sessizce 0'a kırpıldı
    ``burn_time = -6``             HÜKÜM: ``total_impulse_ns = 0,0`` ama
                                   ``required_restraint_force_n = 16000``
    ``wall_temperature_hot=-500``  HÜKÜM: SF ``inf`` + 'Selected material
                                   acceptable' + termal risk 2,0 (EN
                                   GÜVENLİ hüküm)
    ``wall_temperature_hot=1e9``   HÜKÜM (uçta da HTTP 200)
    ============================  =========================================

    Çıplak ``ZeroDivisionError`` de sessiz kırpma da aynı kusurun iki
    yüzüdür: kullanıcı hangi ALANIN reddedildiğini öğrenemiyor. Bu istisna
    alanın ADINI ve nedenini taşır; uç katmanı onu 422 +
    ``invalid_fields`` olarak yayımlar (``/analyze_safety`` deseni).
    """

    def __init__(self, field, reason, value=None):
        self.field = field
        self.reason = reason
        self.value = value
        super().__init__(
            f"{field!r} is not physical ({reason}; got {value!r}), so no "
            "safety verdict was computed. A non-physical input is not a "
            "conservative input: silently clipping it to zero would publish "
            "a verdict the motor never earned.")


def _fizik_disi_degilse(field, value, *, izin_sifir=False):
    """Pozitif sonlu sayı bekler; değilse ``NonPhysicalSafetyInput``.

    ``bool`` bir ölçüm değildir (``float(True) == 1,0`` sessizce yutulur).
    """
    # ÖH D31 / P15B2-01 (OH-D30-08 dağıtımı, satır
    # ``safety_analysis.py::_fizik_disi_degilse``): "sonlu sayı mı?" sorusu
    # ARTIK MERKEZDEN sorulur (``hrma.utils.input_guard.finite_number``;
    # ``bool`` orada da sayı değildir). Hüküm BİT-AYNI: çevrilemeyen ->
    # not_a_number, çevrilebilen ama sonsuz/NaN -> not_finite. Değişen tek
    # şey kuralın tek kaynaktan okunmasıdır.
    if isinstance(value, bool):
        raise NonPhysicalSafetyInput(field, 'not_a_number', value)
    try:
        sayi = float(value)
    except (TypeError, ValueError):
        raise NonPhysicalSafetyInput(field, 'not_a_number', value)
    if finite_number(sayi) is None:
        raise NonPhysicalSafetyInput(field, 'not_finite', value)
    if sayi < 0 or (sayi == 0 and not izin_sifir):
        raise NonPhysicalSafetyInput(
            field,
            'must_be_non_negative' if izin_sifir else 'must_be_positive',
            value)
    return sayi


def sicaklik_bandi_K():
    """Deponun KANONİK sıcaklık bandı [K] — yeni eşik İCAT EDİLMEZ.

    Tek kaynak ``hrma.validation.motor_validation.MotorDataValidator.limits
    ['temperature']`` (200-5000 K; tablonun kendi künyesi: "real-world
    constraints"). Aynı tablo ``app.py::_ust_sinir_bandi`` üzerinden
    ``/analyze_safety`` ucunda ZATEN ``chamber_temperature`` üst sınırı
    olarak uygulanıyor (``FIELD_ALIASES``); modül yüzü şimdi aynı kaynağı
    okur, yani uç ile kütüphane aynı sayıyı savunur (doktrin 4).

    ALT uç bilerek 200 K'ye ÇEKİLMEZ: rejeneratif soğutulan bir cidar
    meşru biçimde 200 K'nin altında olabilir (kardeş ``pressure_vessel``
    20 K kriyo koşumunu kabul ediyor ve a2'nin P5B1-09 bekçisi bunu
    ölçüyor). Modül tarafında alt sınır MUTLAK SIFIRDIR — bu bir eşik
    değil, termodinamiğin kendisidir.
    """
    from hrma.validation.motor_validation import MotorDataValidator
    limit = MotorDataValidator().limits['temperature']
    return float(limit['min']), float(limit['max'])


def _sicaklik_kapisi(field, value):
    """Mutlak sıfır < T <= kanonik üst sınır; değilse fail-closed."""
    sayi = _fizik_disi_degilse(field, value)
    _alt, ust = sicaklik_bandi_K()
    if sayi > ust:
        raise NonPhysicalSafetyInput(field, 'above_physical_maximum', value)
    return sayi

#: Toksik hükmün KAZANILMADIĞI durumda ``toxic_hazard_level``e yazılan değer
#: (ÖH Z5S / S6, P7B3-21 kritiği). ``'NONE'``/``'LOW'`` sırasına GİRMEZ ve
#: ``_score_toxic_risk`` bu değer için ``None`` döner: eksen maksimuma
#: girmez, ``risks_not_evaluated`` listesine adıyla yazılır ve kazanılmamış
#: ``ACCEPTABLE`` geri çekilir (mekanizma: ``_assess_overall_risk``).
TOXIC_LEVEL_NOT_EVALUATED = THERMAL_VERDICT_NOT_EVALUATED

#: ``propellant_type``ın TANINAN sınıfları. Liste ürünün gerçekten
#: gönderebildiği kümedir: ``static/js/panels/safety_panel.js::PROPELLANTS``
#: ile birebir aynı altı anahtar. Bu kümenin DIŞINDAKİ her değer
#: ÇÖZÜLEMEMİŞTİR ve toksik hüküm üretmez.
#: OH-D28-08 (ÖH D29): ``propellant_tnt_equivalents`` artık bu kümenin
#: ÜST KÜMESİDİR — panelin SEÇTİRDİĞİ sınıflar ile motor tipinden
#: ÇÖZÜLEBİLEN sınıflar farklı kavramlardır. Hibrit sınıfları (türetilmiş)
#: panelde bir seçenek değildir; ``motor_type='hybrid'`` ile ya da
#: oksitleyici adı yazılarak çözülür.
KNOWN_PROPELLANT_CLASSES = (
    'composite', 'double_base', 'composite_db',
    'liquid_biprop', 'liquid_monoprop', 'solid_monoprop',
)

# ---------------------------------------------------------------------------
# ÖH D37 A1b panel-js 5. tur (14 Eki) — 'MODELLENMEDİ' BEYANI
#
# ÖLÇÜLEN KUSUR (KAB 14 Eki ``dock.json``; ölçüm
# ``docs/scofield/raw/OH/A1b/panel-js/a1/t5/once.json``): güvenlik paneli
# katı VE hibrit motoru ``propellant_type='composite'`` (APCP/HTPB) diye
# gönderiyordu. Örnek N2O/HTPB hibritte sonuç: sınıf ``composite``, TNT
# 5,435 kg, ölümcül parça menzili ve patlama tahliyesi 1600 m, genel hüküm
# CRITICAL. Örnek KNDX katıda (şeker itici) sınıf yine ``composite``, TNT
# 1,011 kg, tahliye 1600 m. İkisinde de yayımlanan sayı KATI KOMPOZİT
# iticinin sayısıydı; motorun kendi iticisinin değil.
#
# Bu değer bir itici SINIFI DEĞİLDİR (TNT çarpanı da toksik kuralı da
# yoktur); bu yüzden ``KNOWN_PROPELLANT_CLASSES`` ve
# ``propellant_tnt_equivalents`` içine GİRMEZ. Anlamı: "bu motorun
# iticisi için HRMA'da birincil kaynaklı bir patlayıcı modeli yok". Uç bu
# değeri alınca patlayıcı ekseni ADIYLA geri çekilir (TNT eşdeğeri, patlama
# mesafeleri, QD şartları) ve şarjı patlayıcı sayan Gurney parça hızı ile
# ondan türeyen tahliye mesafesi de yayımlanmaz. Sayı UYDURULMAZ; kaynaksız
# katsayı YOK.
#
# Hangi motorlar: (1) şeker/KNO3 iticiler (KNDX, KNSB, KNSU, KNER) ve kara
# barut — deponun hiçbir sözlüğünde TNT eşdeğeri yok (taranan:
# ``propellant_tnt_equivalents``, ``hrma/data/*``); (2) hibrit motorun
# KAMARA değerlendirmesi — yakıt tanesi atıl polimerdir, patlayıcı enerji
# oksitleyici TANKINDAKİ N2O ayrışmasından gelir. Modülün türetilmiş
# ``hybrid_n2o`` sınıfı (Karabeyoglu vd. 2008) OKSİTLEYİCİ KÜTLESİ
# başınadır; panelin elindeki kütle ise toplam itici kütlesidir (atıl tane
# dahil) ve geometri tankın değil kamaranın geometrisidir. Temel uyuşmazlığı
# yüzünden panel bu sınıfı hibrit kamarasına uygulamaz; API'nin
# ``motor_type='hybrid'`` yolu AYNEN kalır (D29 bekçileri).
# ---------------------------------------------------------------------------
PROPELLANT_CLASS_NOT_MODELLED = 'not_modelled'

#: Geri çekme gerekçesinin makine kodu motor tipine göre (panel bu kodla
#: kendi i18n metnini basar; EN = TR). Sözlükte olmayan motor tipi
#: ``EXPLOSIVE_NOT_MODELLED_DEFAULT_CODE`` alır.
EXPLOSIVE_NOT_MODELLED_CODE_BY_MOTOR = {
    'hybrid': 'hybrid_oxidiser_tank',
    'solid': 'solid_no_sourced_tnt',
}
EXPLOSIVE_NOT_MODELLED_DEFAULT_CODE = 'no_sourced_tnt'

#: Kodların uç gerekçesi (İngilizce; TR karşılığı ``i18n_charts.js``).
EXPLOSIVE_NOT_MODELLED_REASONS = {
    'hybrid_oxidiser_tank': (
        "propellant_type 'not_modelled' was declared for a hybrid motor, so "
        "the explosive verdict was not evaluated. The hybrid fuel grain is "
        "an inert polymer and is not an explosive on its own; the explosive "
        "hazard is the decomposition of the oxidiser held in the oxidiser "
        "tank, a separate vessel whose oxidiser mass and geometry are not "
        "inputs of this assessment. No TNT equivalent, blast distance, "
        "fragment throw range or evacuation distance is published."),
    'solid_no_sourced_tnt': (
        "propellant_type 'not_modelled' was declared for a solid motor, so "
        "the explosive verdict was not evaluated. HRMA has no "
        "primary-sourced TNT equivalent for this propellant family "
        "(potassium nitrate/sugar propellants such as KNDX, KNSB, KNSU and "
        "KNER, or black powder). No TNT equivalent, blast distance, fragment "
        "throw range or evacuation distance is published."),
    'no_sourced_tnt': (
        "propellant_type 'not_modelled' was declared, so the explosive "
        "verdict was not evaluated: HRMA has no primary-sourced TNT "
        "equivalent for this propellant. No TNT equivalent, blast distance, "
        "fragment throw range or evacuation distance is published."),
}

#: Gurney parça hızından türeyen alanlar (şarjı PATLAYICI sayar; parça
#: hızı = √(2E)·√(C/(M + C/2)), C = itici kütlesi). Modellenmeyen itici
#: için bu üç alan ve onlardan türeyen patlama tahliyesi YAYIMLANMAZ.
GURNEY_FRAGMENT_FIELDS = ('fragment_velocity_ms', 'maximum_range_m',
                          'lethal_fragment_range_m')

#: Patlama tahliyesinin geri çekildiği alanın yolu (geri çekme kaydında
#: ve acil durum bloğunda aynı ad).
EVACUATION_DISTANCE_PATH = (
    'emergency_procedures.explosion_response.evacuation_distance')


#: Geri çekilen alanların listesi (beyan ve katalog kaydında AYNI).
EXPLOSIVE_NOT_MODELLED_FIELDS = (
    ('tnt_equivalent_kg', 'blast_distances', 'qd_requirements')
    + GURNEY_FRAGMENT_FIELDS + (EVACUATION_DISTANCE_PATH,))


def explosive_not_modelled(propellant_type, motor_type) -> Optional[Dict]:
    """'Modellenmedi' beyanının geri çekme kaydı; beyan değilse ``None``.

    Tek kaynak: ``_resolve_explosive_class`` (sınıf),
    ``_analyze_explosive_hazards`` (Gurney alanları) ve
    ``_generate_emergency_procedures`` (tahliye) aynı kaydı okur.
    """
    if str(propellant_type or '').strip().lower() != \
            PROPELLANT_CLASS_NOT_MODELLED:
        return None
    mt = str(motor_type or '').strip().lower()
    kod = EXPLOSIVE_NOT_MODELLED_CODE_BY_MOTOR.get(
        mt, EXPLOSIVE_NOT_MODELLED_DEFAULT_CODE)
    return {
        'status': THERMAL_VERDICT_NOT_EVALUATED,
        'code': kod,
        'reason': EXPLOSIVE_NOT_MODELLED_REASONS[kod],
        'not_evaluated': list(EXPLOSIVE_NOT_MODELLED_FIELDS),
    }


# ---------------------------------------------------------------------------
# ÖH D37 A1b panel-js 6. tur (14 Eki) — KATI MOTORDA SINIF KATALOG AİLESİNDEN
#
# ÖLÇÜLEN KUSUR (devir 14; ölçüm ``docs/scofield/raw/OH/A1b/panel-js/a1/
# t6/once.json``): ``POST /analyze_safety`` ve ``pdf_safety.build_pdf_safety``
# ``motor_type='solid'`` + ``propellant_type='kndx'`` (depoda TANINAN şeker
# itici) isteğinde ``MOTOR_TYPE_TO_EXPLOSIVE_CLASS['solid'] = 'composite'``
# yedeğine düşüp KATI KOMPOZİT iticinin TNT eşdeğerini, patlama
# mesafelerini ve Gurney tahliyesini yayımlıyordu. Panel yolu 5. turda
# kapandı (``safety_panel.js::propellantClassFromMotor`` katı kolu).
#
# KURAL (panelle AYNI; ikinci kural yok): katı motorun sınıfı merkezi katı
# kataloğundaki (``propellants_db``; panelin ``/api/propellants`` ->
# ``HRMAPropellants.get`` ile okuduğu AYNI kayıtlar, anahtar + takma ad
# çözümü ``propellants_db.resolve`` ile JS ``resolve``in ikizi) AİLE adıdır;
# aile ``KNOWN_PROPELLANT_CLASSES`` içinde bir sınıfsa (composite,
# double_base) o, değilse (sugar, other) ya da ad katalogda çözülmezse
# 'modellenmedi' (FAIL-CLOSED: bilinmeyen kimlik ürün varsayılanına
# ÇEVRİLMEZ). Eşleme tablosu YAZILMAZ: aile adı ile sınıf anahtarı aynı
# sözcüktür, üyelik sınanır.
# ---------------------------------------------------------------------------

#: Katalogdan türeyen geri çekme kodları (beyan kodlarının kardeşi; uçta
#: ``explosive_not_modelled.code``). Gerekçe şablonları aşağıda.
EXPLOSIVE_CATALOG_FAMILY_CODE = 'solid_catalog_family_no_sourced_tnt'
EXPLOSIVE_CATALOG_UNRESOLVED_CODE = 'solid_not_in_catalog'

_EXPLOSIVE_CATALOG_REASON_TEMPLATES = {
    EXPLOSIVE_CATALOG_FAMILY_CODE: (
        "propellant_type {ad} resolves in HRMA's central solid propellant "
        "catalog to the record '{anahtar}' of the '{aile}' family, which has "
        "no primary-sourced TNT equivalent in HRMA, so the explosive verdict "
        "was not evaluated. The motor_type 'solid' fallback class is NOT "
        "applied: it would publish a composite propellant's numbers for this "
        "propellant. No TNT equivalent, blast distance, fragment throw range "
        "or evacuation distance is published."),
    EXPLOSIVE_CATALOG_UNRESOLVED_CODE: (
        "propellant_type {ad} does not resolve to a record (key or alias) of "
        "HRMA's central solid propellant catalog, so the propellant family "
        "and its TNT-equivalent class were not won and the explosive verdict "
        "was not evaluated. The motor_type 'solid' fallback class is NOT "
        "applied to an unidentified solid propellant. Name a catalog "
        "propellant or a tabulated class to have the explosive verdict "
        "computed. No TNT equivalent, blast distance, fragment throw range "
        "or evacuation distance is published."),
}


def solid_catalog_explosive_class(propellant_type
                                  ) -> Tuple[str, Optional[str],
                                             Optional[str]]:
    """Katı motor iticisinin patlayıcı sınıfı: ``(sınıf, katalog anahtarı,
    aile)``.

    ``sınıf`` aile bir sınıfsa aile adı, değilse
    ``PROPELLANT_CLASS_NOT_MODELLED``. Panel ikizi:
    ``safety_panel.js::propellantClassFromMotor`` (katı kolu). Katalog
    okunamazsa da 'modellenmedi' döner (fail-closed).

    Ad çözümü katı motorun KENDİ merkezi katalog çözücüsüdür
    (``solid_rocket_engine._catalog_key_from_text``: anahtar, takma ad,
    motor anahtarı, kaydın tam adı, ayraçtan önceki baş). Panelin
    ``HRMAPropellants.get``i (anahtar + takma ad) bunun alt kümesidir ve
    panel her zaman motor sonucunun ANAHTARINI gönderir; API ve belge ise
    serbest ad da taşır (ölçüldü: katı yanıtının ``propellant_name`` alanı
    'KNDX - Potassium Nitrate/Dextrose 65/35'). Yeni ad/eşleme icat edilmez.
    """
    try:
        from hrma.data.propellants_db import PROPELLANTS, resolve
        from hrma.engines.solid_rocket_engine import _catalog_key_from_text
        ham = _catalog_key_from_text(propellant_type)
        if not ham:
            return PROPELLANT_CLASS_NOT_MODELLED, None, None
        anahtar = resolve(ham)
        aile = PROPELLANTS[anahtar].get('family')
    except Exception:
        return PROPELLANT_CLASS_NOT_MODELLED, None, None
    if isinstance(aile, str) and aile in KNOWN_PROPELLANT_CLASSES:
        return aile, anahtar, aile
    return PROPELLANT_CLASS_NOT_MODELLED, anahtar, aile


def solid_catalog_not_modelled(propellant_type) -> Optional[Dict]:
    """Katı motorda katalogdan türeyen geri çekme kaydı; sınıf kazanıldıysa
    ``None``. Kayıt biçimi ``explosive_not_modelled`` ile AYNI (üç tüketici
    aynı alanları okur)."""
    sinif, anahtar, aile = solid_catalog_explosive_class(propellant_type)
    if sinif != PROPELLANT_CLASS_NOT_MODELLED:
        return None
    ham = str(propellant_type or '').strip()
    ad = repr(ham[:60]) if ham else '(not supplied)'
    kod = (EXPLOSIVE_CATALOG_FAMILY_CODE if anahtar is not None
           else EXPLOSIVE_CATALOG_UNRESOLVED_CODE)
    return {
        'status': THERMAL_VERDICT_NOT_EVALUATED,
        'code': kod,
        'reason': _EXPLOSIVE_CATALOG_REASON_TEMPLATES[kod].format(
            ad=ad, anahtar=anahtar, aile=aile),
        'catalog_key': anahtar,
        'catalog_family': aile,
        'not_evaluated': list(EXPLOSIVE_NOT_MODELLED_FIELDS),
    }

class UnresolvedChamberMaterial(ValueError):
    """Kamara malzemesi ``materials_db``de çözülemedi — hüküm ÜRETİLMEZ.

    **P5B2-03 (KRİTİK) — ÖLÇÜLEN KUSUR** (taban ``e88d096``, kanıt
    ``docs/scofield/raw/OH/D15/yapisal-sistem/a1/once.json``): bu modülün üç
    ayrı yerinde ``except KeyError: get_material('steel_4130')`` yazıyordu.
    Ölçüldü (70 bar, 120 mm çap, 3 mm cidar):

    ====================  ==========  ========  ==========
    istenen ``material``  kullanılan  akma MPa  akma SF
    ====================  ==========  ========  ==========
    ``aluminum_6061``     alüminyum   275,0     **1,9643**
    ``aluminum6061``      **çelik**   460,0     **3,2857**
    ``AL6061``            **çelik**   460,0     **3,2857**
    ``unobtainium``       **çelik**   460,0     **3,2857**
    ``''``                **çelik**   460,0     **3,2857**
    ====================  ==========  ========  ==========

    Yani tek bir alt çizgi eksikliği alüminyum kabı ÇELİK olarak
    değerlendiriyor, emniyet katsayısını %67 şişiriyor ve hükmü
    ``UNSAFE`` → ``MARGINAL`` yönüne çeviriyordu. Yön EMNİYETSİZ ve
    SESSİZ: yanıtta ne uyarı ne künye vardı.

    Fail-closed kural: çözülemeyen bir malzeme adı için emniyet hükmü
    KAZANILAMAZ. ``/analyze_safety`` ucu bu adı zaten
    ``_resolve_material_request`` ile 422 yapıyor (ölçüldü: ``aluminum6061``
    → HTTP 422 ``unresolved_material``); modül düzeyi artık aynı hükmü
    veriyor, yani kütüphaneyi doğrudan çağıran yol da sessiz çeliğe
    düşmüyor.
    """

    def __init__(self, requested, available):
        self.requested = requested
        self.available = list(available)
        super().__init__(
            f"Chamber material {requested!r} is not in the material "
            "database, so no safety verdict was computed. An unrecognised "
            "material is not a default material. Available keys: "
            f"{self.available}")


#: Toksik hüküm geri çekildiğinde antidot satırının yerine geçen metin
#: (P5B2-02). Tavsiye DEĞİL, hükmün yokluğunun beyanıdır.
ANTIDOTE_WITHHELD = (
    'NOT EVALUATED - no toxic inventory could be identified for this '
    'propellant, so no antidote requirement was determined. This is NOT '
    'a statement that no antidote is needed: name the propellant '
    'components and consult the propellant SDS and the responsible '
    'occupational physician.')

#: ``_classify_toxic_inventory`` çözünürlük kodları.
TOXIC_RESOLUTION_TABULATED = 'tabulated'
TOXIC_RESOLUTION_UNDETERMINED = 'class_inventory_undetermined'
TOXIC_RESOLUTION_NOT_TABULATED = 'class_inventory_not_tabulated'
TOXIC_RESOLUTION_UNRECOGNISED = 'unrecognised_propellant_class'

# ---------------------------------------------------------------------------
# ÖH D29 / OH-D28-08 — HİBRİT (N2O) TNT EŞDEĞERİ: TÜRETİLİR, SEÇİLMEZ
#
# ÖLÇÜLEN KUSUR (taban ``4dc63c11``, kanıt
# ``docs/scofield/raw/OH/D29/yapisal-sistem/a1/once.json``): ürünün başlıca
# hibrit yakıtı ``'htpb'`` TNT tablosunda YOKTU ve hibrit motor
# ``MOTOR_TYPE_TO_EXPLOSIVE_CLASS['hybrid'] = 'liquid_biprop'`` üzerinden
# LOX/RP-1 SIVI ÇİFT-İTİCİSİNİN sayısını (0,35) ödünç alıyordu. Ölçüldü
# (5 kg itici, motor_type='hybrid'):
#
#   propellant_type='htpb'   -> sınıf liquid_biprop, faktör 0,35, TNT 1,75 kg
#   propellant_type='sihir'  -> AYNI üç sayı (yakıt adı hiçbir bilgi taşımıyor)
#   liquid_biprop + 'liquid' -> AYNI faktör (hibrit ile sıvı ayırt edilemiyor)
#
# Yani hibritin patlayıcı hükmü bir SIVI motorun hükmüydü ve ürünün beş
# hibrit yakıtının (htpb, paraffin, pe, pmma, abs) hiçbiri tabloda yoktu.
#
# FİZİK: hibritte yakıt grain'i (HTPB, parafin, PE, PMMA, ABS) oksitleyici
# İÇERMEYEN atıl bir polimerdir; tek başına ayrışıp patlamaz. Patlayıcı
# enerji OKSİTLEYİCİDEN gelir: N2O pozitif oluşum entalpisine sahiptir ve
# monopropellant gibi ekzotermik ayrışır. Kaynak bu mekanizmayı adıyla
# koyar: "Nitrous oxide has a positive heat of formation and decomposes
# into the reference species N2 and O2 by releasing substantial heat...
# it also introduces the most important safety hazard associated with this
# substance" (Karabeyoglu vd. 2008, Böl. III.B).
#
# KAYNAK (birincil, ölçümle okundu):
#   A. Karabeyoglu, J. Dyer, J. Stevens, B. Cantwell, "Modeling of N2O
#   Decomposition Events", AIAA 2008-4933, 44th AIAA/ASME/SAE/ASEE Joint
#   Propulsion Conference & Exhibit, 21-23 Temmuz 2008, Hartford CT.
#   DOI 10.2514/6.2008-4933.
#     Denklem (2):  N2O -> N2 + 1/2 O2 ,  dH_G = 19,61 kcal/mol
#     Denklem (17): H2O2 -> H2O + 1/2 O2 , dH_G = 23,44 kcal/mol
#   Makalenin kendi özet cümlesi: "the energies associated with the
#   decomposition of 100% H2O2 and N2O are 689 cal/g and 446 [cal/g]".
#
# TÜRETİM (sayı SEÇİLMEDİ, bölmeyle ÇIKTI):
#
#     e_ox = dH_G / M            [kcal/mol] / [g/mol] = [kcal/g]
#     TNT_eq = e_ox / e_TNT      [cal/g] / [cal/g]    = BOYUTSUZ
#
# BOYUT ANALİZİ: pay ve payda aynı birimde (cal/g) olduğu için oran
# boyutsuzdur; termokimyasal kalori pay ve paydada sadeleşir, yani sonuç
# kalori tanımından BAĞIMSIZDIR. TNT referansı bir ÖLÇÜM değil bir
# TANIMDIR: 1 ton TNT = 1e9 cal_th (NIST SP 811, 2008; termokimyasal
# kalori = 4,184 J tam tanım — deponun tek kaynağı
# ``hrma.engines.cea_bridge.CAL_TO_J``), dolayısıyla 1 g TNT = 1000 cal_th.
#
# DOĞRULAMA DÜĞÜMLERİ (Kinney-Graham Z=1 düğümüyle aynı ruh): türetim
# makalenin KENDİ yayımladığı iki özgül enerjiyi yeniden üretmek zorundadır
# — N2O 446 cal/g, H2O2 689 cal/g. ``hybrid_oxidizer_specific_energy_cal_g``
# 445,55 ve 689,13 verir (bağıl sapma < %0,1). H2O2 bu modülde bir sınıf
# DEĞİLDİR; yalnız türetimin çapraz doğrulama düğümüdür.
#
# KAPSAM / AÇIK BORÇ: ``/analyze_safety`` ucu ``oxidizer_type`` alanını
# KABUL ETMİYOR (ürünün hibrit uçları kabul ediyor, varsayılan 'n2o' —
# ``hrma/engines/hybrid_rocket_engine.py``). Oksitleyici adı istek metninde
# geçmiyorsa sınıf ürünün KENDİ varsayılan oksitleyicisinden çözülür ve bu
# künyede ADIYLA yazılır; peroksit hibriti daha enerjiktir (689/446 = 1,55x)
# ve ancak adı yazılırsa ayrı hüküm alabilir. Ucun alanı kabul etmesi
# app-api sahasıdır (OH-D29-YS-01 adlı borç).
# ---------------------------------------------------------------------------

#: Oksitleyicinin global ayrışma reaksiyonunun molar ısısı [kcal/mol].
#: Karabeyoglu vd. 2008, Denklem (2) ve (17). SAYI BURADAN BAŞKA YERDE
#: YAZILMAZ (tek kaynak).
HYBRID_OXIDIZER_DECOMPOSITION_KCAL_PER_MOL = {
    'n2o': 19.61,
    'h2o2': 23.44,
}

#: Molar kütleler [g/mol] — IUPAC 2021 atom ağırlıklarından
#: (N 14,007 / O 15,999 / H 1,008).
HYBRID_OXIDIZER_MOLAR_MASS_G_PER_MOL = {
    'n2o': 44.013,
    'h2o2': 34.0147,
}

#: TNT referans özgül enerjisi [cal_th/g]. ÖLÇÜM DEĞİL TANIM: 1 ton TNT
#: 1e9 termokimyasal kalori olarak TANIMLIDIR (NIST SP 811, 2008).
TNT_REFERENCE_CAL_PER_G = 1000.0

#: Makalenin kendi yayımladığı özgül enerjiler [cal/g] — türetimin
#: DOĞRULAMA DÜĞÜMLERİ. Bekçi türetimi bunlara karşı sınar; tutmazsa
#: sayı kalibrasyona kaymış demektir.
HYBRID_OXIDIZER_PUBLISHED_CAL_PER_G = {
    'n2o': 446.0,
    'h2o2': 689.0,
}

#: ``/analyze_safety`` oksitleyiciyi ADIYLA çözebilsin diye tanınan
#: eş anlamlılar. Yeni takma ad İCAT EDİLMEZ; bunlar maddenin kendi
#: adları/formülleridir.
HYBRID_OXIDIZER_ALIASES = {
    'n2o': 'n2o',
    'nitrous': 'n2o',
    'h2o2': 'h2o2',
    'hp': 'h2o2',
    'peroxide': 'h2o2',
}

#: Ürünün hibrit motorunun VARSAYILAN oksitleyicisi. Tek kaynak
#: ``hrma/engines/hybrid_rocket_engine.py`` (``oxidizer_type='n2o'``) ve
#: ``hrma/app.py`` (``data.get('oxidizer_type', 'n2o')``); bekçi ikisinin
#: ayrışmadığını sınar.
HYBRID_DEFAULT_OXIDIZER = 'n2o'

#: Ürünün hibrit yakıt tablosunun anahtarları (atıl polimerler). Tek kaynak
#: ``hrma.analysis.regression_analysis.RegressionAnalyzer.fuel_properties``;
#: bekçi ayrışmayı yakalar. Bu adlar TNT eşdeğerini BELİRLEMEZ (grain atıl),
#: yalnız "hibrit yakıt adı yazılmış" olduğunu söyler.
HYBRID_INERT_FUEL_NAMES = ('htpb', 'paraffin', 'pe', 'pmma', 'abs')


def hybrid_oxidizer_from_text(metin) -> Optional[str]:
    """Serbest metinde ADIYLA geçen hibrit oksitleyicinin kanonik anahtarı.

    ÖH D33-3 / OH-D33-30 — TEK KAYNAK. Bu soru ("kullanıcının yazdığı metin
    bu modülün TNT türetimini olan bir oksitleyiciyi anıyor mu?") bugüne
    kadar YALNIZ ``_resolve_hybrid_explosive_class``ın gövdesinde, satır
    içinde yanıtlanıyordu; uç katmanı aynı soruyu soramadığı için
    ``/analyze_safety`` çözülemeyen adı REDDEDEMİYOR, ürünün varsayılan
    oksitleyicisine düşüp sayı yayımlıyordu (ölçüldü, ``a1/once.json`` K1:
    ``oxidizer_type='peynir'`` -> ``hybrid_n2o`` + 22,2775 kg TNT).

    Kural DEĞİŞMEDİ: metin sözcüklerine ayrılır ve
    ``HYBRID_OXIDIZER_ALIASES``ta ADIYLA aranır (yeni takma ad icat
    edilmez). Çözülemezse ``None`` döner — çağıran fail-closed davranır.
    """
    ham = '' if metin is None else str(metin)
    for parca in re.split(r'[^a-z0-9]+', ham.strip().lower()):
        if parca in HYBRID_OXIDIZER_ALIASES:
            return HYBRID_OXIDIZER_ALIASES[parca]
    return None


def hybrid_oxidizer_specific_energy_cal_g(oxidizer: str) -> float:
    """Oksitleyicinin ayrışma özgül enerjisi [cal/g] — dH_G / M.

    Karabeyoglu vd. 2008 Denklem (2)/(17). Tablo dışı bir ad için sayı
    UYDURULMAZ: ``KeyError`` yükselir (fail-closed).
    """
    key = str(oxidizer).strip().lower()
    kcal_mol = HYBRID_OXIDIZER_DECOMPOSITION_KCAL_PER_MOL[key]
    g_mol = HYBRID_OXIDIZER_MOLAR_MASS_G_PER_MOL[key]
    return 1000.0 * kcal_mol / g_mol


def hybrid_oxidizer_tnt_equivalent(oxidizer: str) -> float:
    """Oksitleyicinin TNT eşdeğeri [boyutsuz] — e_ox / e_TNT."""
    return (hybrid_oxidizer_specific_energy_cal_g(oxidizer)
            / TNT_REFERENCE_CAL_PER_G)


#: Hibrit patlayıcı sınıflarının TNT eşdeğerleri — LİTERAL DEĞİL, TÜRETİLMİŞ.
#: Türetimi olan HER oksitleyici sınıf olur; oksitleyici istek metninde
#: adıyla geçiyorsa kendi sınıfını alır, geçmiyorsa ürünün varsayılanı
#: KÜNYEDE BEYAN EDİLEREK kullanılır (yukarıdaki kapsam notu).
HYBRID_EXPLOSIVE_CLASSES = {
    'hybrid_%s' % ox: hybrid_oxidizer_tnt_equivalent(ox)
    for ox in HYBRID_OXIDIZER_DECOMPOSITION_KCAL_PER_MOL
}

# motor_type -> TNT eşdeğeri sınıfı. Kullanıcının seçtiği motor tipi,
# propellant_type serbest metin olduğunda patlayıcı sınıfını belirler.
MOTOR_TYPE_TO_EXPLOSIVE_CLASS = {
    'solid': 'composite',
    # OH-D28-08: yakıt grain'i tek başına atıldır, olay OKSİTLEYİCİ
    # kaynaklıdır — bu yüzden hibrit artık sıvı çift-iticinin sayısını
    # ÖDÜNÇ ALMAZ, kendi türetilmiş sınıfını kullanır.
    'hybrid': 'hybrid_%s' % HYBRID_DEFAULT_OXIDIZER,
    'liquid': 'liquid_biprop',
}


@dataclass
class SafetyMargins:
    """Safety margin requirements for different components"""
    structural_safety_factor: float = 4.0
    pressure_safety_factor: float = 1.5
    temperature_safety_factor: float = 1.3
    flow_safety_margin: float = 0.2
    minimum_burst_pressure_ratio: float = 2.0

@dataclass
class HazardDistance:
    """Hazard distance calculations"""
    debris_distance: float  # meters
    blast_distance: float   # meters
    thermal_distance: float # meters
    toxic_distance: float   # meters

class SafetyAnalyzer:
    """Comprehensive safety analysis for rocket motor systems"""
    
    def __init__(self):
        self.safety_margins = SafetyMargins()
        # ÖH D30 / app-api-uc a1 · OH-D29-01 — İSTEKTEKİ OKSİTLEYİCİ.
        # Hibritte TNT eşdeğerini oksitleyici belirler; ürünün hibrit uçları
        # ``oxidizer_type`` alanını kabul ediyordu, ``/analyze_safety``
        # ETMİYORDU (modül başındaki 'KAPSAM / AÇIK BORÇ' notu). Alan artık
        # uçtan buraya geçer ve ÜÇ tüketici de (patlayıcı, yangın, depolama)
        # aynı sınıfı görür — sınıf kararı TEK yerde kalır.
        self._requested_oxidizer = None
        
        # Explosive classifications (TNT equivalent)
        self.propellant_tnt_equivalents = {
            'composite': 0.42,     # APCP/HTPB
            'double_base': 0.55,   # Nitrocellulose/Nitroglycerin
            'composite_db': 0.48,  # Composite double base
            'liquid_biprop': 0.35, # LOX/RP-1, LOX/LH2
            'liquid_monoprop': 0.28, # Hydrazine, N2O4
            'solid_monoprop': 0.33   # Ammonium perchlorate
        }
        # OH-D28-08: hibrit sınıfı LİTERAL DEĞİL, oksitleyicinin ayrışma
        # entalpisinden TÜRETİLİR (Karabeyoglu vd. 2008; modül başındaki
        # türetim bloğu). Ayrı sözlükten gelir ki sayı iki yerde yazılmasın.
        self.propellant_tnt_equivalents.update(HYBRID_EXPLOSIVE_CLASSES)
        
        # Toxic hazard data
        self.toxic_hazards = {
            'n2o4': {'lc50': 115, 'immediately_dangerous': 25, 'twa': 5},  # ppm
            'mmh': {'lc50': 825, 'immediately_dangerous': 50, 'twa': 0.01},
            'udmh': {'lc50': 622, 'immediately_dangerous': 25, 'twa': 0.01},
            'hydrazine': {'lc50': 570, 'immediately_dangerous': 50, 'twa': 0.01},
            'n2o': {'asphyxiant': True, 'inerting_concentration': 30000}  # ppm
        }
    
    @staticmethod
    def _resolve_chamber_material(material) -> Tuple[Dict, str]:
        """(materials_db kaydı, çözülen anahtar) — çözülemezse REDDEDER.

        P5B2-03'ün tek kaynağı: modülün üç ayrı ``except KeyError ->
        steel_4130`` yedeği bu yardımcıyla değiştirildi. Kural
        ``regression_analysis.resolve_fuel_key`` ile aynı ruhtadır: yeni
        takma ad İCAT EDİLMEZ, ``materials_db``nin kendi çözümleyicisi
        neyi tanıyorsa o tanınır.
        """
        try:
            return get_material(material), str(material)
        except KeyError as exc:
            try:
                from hrma.data.materials_db import MATERIALS as _M
                mevcut = sorted(_M)
            except Exception:                       # pragma: no cover
                mevcut = []
            raise UnresolvedChamberMaterial(material, mevcut) from exc

    def analyze_comprehensive_safety(self, motor_data: Dict, propellant_mass: float,
                                   propellant_type: Optional[str] = None,
                                   facility_type: str = 'test_stand',
                                   material: str = 'steel_4130',
                                   motor_type: Optional[str] = None,
                                   oxidizer_type: Optional[str] = None) -> Dict:
        """
        Complete safety analysis including all hazard types

        Args:
            motor_data: Motor performance and design data
            propellant_mass: Total propellant mass (kg)
            propellant_type: Type of propellant system. ÖH D35 / OH-ON-06:
                bu alanın ``'composite'`` VARSAYILANI KALDIRILDI. Verilmeyen
                bir itici kimliği sessizce KATI KOMPOZİT sayılmaz; sınıf
                motor_type + oxidizer_type kimliğinden kazanılır, kazanılamazsa
                patlayıcı ekseni ADIYLA geri çekilir (doktrin 1).
            facility_type: 'test_stand', 'manufacturing', 'transport', 'launch'
            material: Chamber material key (hrma.data.materials_db); the
                structural-safety hoop check uses this material's real
                yield/ultimate strengths instead of a fixed generic steel.
            motor_type: 'solid' | 'hybrid' | 'liquid'. Selects the explosive
                (TNT-equivalent) class when propellant_type is not one of the
                tabulated class keys. Also read from motor_data['motor_type'].
            oxidizer_type: OH-D29-01 — hibrit oksitleyicinin adı. Hibritte
                TNT eşdeğerini yakıt grain'i değil OKSİTLEYİCİ belirler;
                verilirse sınıf ondan çözülür, verilmezse ürünün varsayılan
                oksitleyicisi ADIYLA BEYAN EDİLEREK kullanılır (mevcut kol).

        Returns:
            Comprehensive safety analysis results
        """
        # OH-D29-01: istek alanı, sınıfı çözen üç tüketicinin ortak
        # kaynağına konur (patlayıcı / yangın / depolama aynı sınıfı görür).
        self._requested_oxidizer = oxidizer_type

        # --- FİZİK KAPISI (ÖH D15 / a3; P5B2-15, P5B2-16, P5B2-17) --------
        # Uç katmanı bu kapıyı Z5S'te aldı; MODÜL yüzü açıktı. Ölçüldü
        # (a3/once.json): ``wall_thickness = 0`` / ``chamber_diameter = 0``
        # -> çıplak ``ZeroDivisionError``; ``propellant_mass = -6`` ->
        # ``TypeError`` (karmaşık sayı); ``thrust = -4000`` -> HÜKÜM basılıp
        # bağlama kuvveti sessizce 0,0. Üçü de artık ALANIYLA reddedilir.
        # ``propellant_mass = 0`` ise BOŞ bir motor değil, ölçülmemiş bir
        # motordur: kapı sıfıra da kapalıdır (uç zaten öyle davranıyor).
        _fizik_disi_degilse('propellant_mass', propellant_mass)
        for _ad in ('chamber_diameter', 'wall_thickness', 'chamber_pressure',
                    'thrust', 'burn_time'):
            if motor_data.get(_ad) is not None:
                _fizik_disi_degilse(_ad, motor_data[_ad])
        for _ad in ('chamber_temperature', 'wall_temperature_hot',
                    'wall_temperature_cold', 'ambient_temperature'):
            if motor_data.get(_ad) is not None:
                _sicaklik_kapisi(_ad, motor_data[_ad])

        # Extract motor parameters
        chamber_pressure = motor_data.get('chamber_pressure', 20.0)  # bar
        thrust = motor_data.get('thrust', 1000)  # N
        # ÖH D36 / onemli2-sivi a2: süre verilmediyse None — 10 s UYDURULMAZ;
        # süreye bağlı kollar adıyla geri çekilir (THERMAL_/UNRESTRAINED_
        # BURN_TIME_FIELDS, sonuçta ``burn_time_dependent_not_evaluated``).
        # Verildiyse değer HAM hâliyle geçer (yayımlanan sayı bit-aynı);
        # verilen değer yukarıdaki fizik kapısından zaten geçti.
        burn_time = motor_data.get('burn_time')      # s | None
        if motor_type is None:
            motor_type = motor_data.get('motor_type')

        # Structural safety analysis
        structural_safety = self._analyze_structural_safety(motor_data, material)

        # Pressure vessel safety — gerçek cidar/malzeme ile (kopma basıncı
        # PressureVesselAnalyzer'dan, sabit çarpanlardan değil).
        pressure_safety = self._analyze_pressure_vessel_safety(
            chamber_pressure, motor_data.get('chamber_diameter', 0.1),
            wall_thickness=motor_data.get('wall_thickness', 0.005),
            material=material,
        )

        # Thermal safety analysis — cidar sıcaklığı ısı transferi modülünden,
        # termal gerilme seçilen malzemenin gerçek E/alfa/nu değerlerinden.
        thermal_safety = self._analyze_thermal_safety(motor_data, material)

        # --- P5B2-13 (ÖH D15 / a3): TERMAL GERİLME YAPISAL HÜKME GİRER ---
        # ÖLÇÜLDÜ (a3/once.json; steel_4130, cidar 2801/400 K, 70 bar,
        # Ø120 mm, 3 mm): ``thermal_stress_mpa = 4045,52`` (akmanın 8,79
        # katı) yanıtta dururken ``structural_integrity`` **MARGINAL**,
        # ``yield_safety_factor`` 3,2857 kalıyordu — çünkü yapısal kol
        # YALNIZ çember gerilmesini görüyordu (140,0 MPa). İki gerilme aynı
        # bölümde AYNI ANDA vardır; kardeş modül ``structural_analysis``
        # onları zaten topluyor (``chamber_analysis['hoop_safety_factor']``
        # "TERMAL+BASINC toplam gerilme" der). Burada da toplanır: yeni bir
        # katsayı YOK, yalnız iki mevcut sayının aynı bölüme uygulanması.
        self._merge_thermal_stress_into_structural(
            structural_safety, thermal_safety)

        # Explosive hazard analysis
        explosive_hazards = self._analyze_explosive_hazards(
            propellant_mass, propellant_type, thrust, burn_time,
            motor_type=motor_type, motor_data=motor_data, material=material
        )

        # Toxic hazard analysis
        toxic_hazards = self._analyze_toxic_hazards(
            propellant_type, propellant_mass, facility_type,
            motor_type=motor_type
        )
        
        # Fire hazard analysis
        # P5B2-04: yangın sınıfı motor tipini görmek zorunda (motor_data
        # bu bilgiyi taşımıyorsa uçtan gelen motor_type kullanılır).
        _fire_md = dict(motor_data or {})
        if motor_type and not _fire_md.get('motor_type'):
            _fire_md['motor_type'] = motor_type
        fire_hazards = self._analyze_fire_hazards(
            propellant_type, propellant_mass, _fire_md
        )
        
        # Operational safety procedures
        operational_safety = self._generate_operational_safety_procedures(
            motor_data, propellant_type, facility_type
        )
        
        # Emergency response procedures
        emergency_procedures = self._generate_emergency_procedures(
            explosive_hazards, toxic_hazards, fire_hazards
        )
        
        # Safety equipment requirements
        safety_equipment = self._determine_safety_equipment_requirements(
            explosive_hazards, toxic_hazards, fire_hazards, facility_type
        )
        
        # Overall risk assessment
        risk_assessment = self._calculate_overall_risk(
            structural_safety, pressure_safety, thermal_safety,
            explosive_hazards, toxic_hazards, fire_hazards
        )
        
        sonuc = {
            'structural_safety': structural_safety,
            'pressure_safety': pressure_safety,
            'thermal_safety': thermal_safety,
            'explosive_hazards': explosive_hazards,
            'toxic_hazards': toxic_hazards,
            'fire_hazards': fire_hazards,
            'operational_safety': operational_safety,
            'emergency_procedures': emergency_procedures,
            'safety_equipment': safety_equipment,
            'risk_assessment': risk_assessment,
            'compliance': self._check_safety_compliance(risk_assessment),
            'recommendations': self._generate_safety_recommendations(risk_assessment),
            # Hangi girdinin gerçekten kullanıldığı kullanıcıya görünür olsun
            # (eskiden motor_type/thrust/burn_time sessizce düşüyordu).
            'inputs_used': {
                'motor_type': motor_type if motor_type else 'not supplied',
                'thrust_n': thrust,
                'burn_time_s': burn_time,
                'chamber_material': material,
                'propellant_type': propellant_type,
                'facility_type': facility_type,
            },
        }
        if burn_time is None:
            # ÖH D36 / onemli2-sivi a2: geri çekilen HER kol tek yerde,
            # yanıttaki noktalı yoluyla sayılır (bloklar kendi damgalarını da
            # taşır). Blok gerçekten geri çektiyse listeye girer — ad listesi
            # uydurulmaz, blokların kendi beyanından kurulur.
            _um = ((explosive_hazards.get('fragment_hazards') or {})
                   .get('unrestrained_motor') or {})
            sonuc['burn_time_dependent_not_evaluated'] = {
                'status': BURN_TIME_NOT_EVALUATED,
                'reason': BURN_TIME_NOT_SUPPLIED_REASON,
                'fields': (
                    ['inputs_used.burn_time_s']
                    + ['thermal_safety.' + ad for ad in
                       thermal_safety.get('burn_time_not_evaluated') or []]
                    + ['explosive_hazards.fragment_hazards.'
                       'unrestrained_motor.' + ad
                       for ad in _um.get('not_evaluated') or []]),
            }
        return sonuc
    
    def _analyze_structural_safety(self, motor_data: Dict,
                                   material: str = 'steel_4130') -> Dict:
        """Analyze structural safety factors and failure modes.

        Dalga 0 (2026-07-14): Eski sürüm sabit 250/400 MPa jenerik çelikle
        hesaplıyordu; structural_analysis aynı motor için 4130'da 460 MPa +
        derating kullanınca iki panel farklı SF gösteriyordu. Artık malzeme
        dayanımları merkezi hrma/data/materials_db.py kaydından okunur.
        """

        chamber_pressure = motor_data.get('chamber_pressure', 20.0) * 1e5  # Pa
        chamber_diameter = motor_data.get('chamber_diameter', 0.1)  # m
        wall_thickness = motor_data.get('wall_thickness', 0.005)  # m

        # Malzeme dayanımları merkezi DB'den. P5B2-03: bilinmeyen ad
        # SESSİZCE steel_4130'a düşüyordu (SF 1,9643 -> 3,2857); artık
        # hüküm üretilmez.
        mat, material_key = self._resolve_chamber_material(material)
        yield_strength = mat['yield_strength']        # Pa
        ultimate_strength = mat['ultimate_strength']  # Pa

        # Hoop stress calculation
        hoop_stress = chamber_pressure * (chamber_diameter/2) / wall_thickness
        
        # Safety factors
        yield_safety_factor = yield_strength / hoop_stress
        ultimate_safety_factor = ultimate_strength / hoop_stress
        
        # Nitel arıza olabilirlik sınıfı — SF eşiklerinden türeyen vekil.
        # DENETİM DÜZELTMESİ (2026-07-28, SAFE-PROB-2): eski kod SF'den
        # basamak fonksiyonuyla SAYISAL olasılık (0.1/0.01/0.001) üretip
        # bunu sabit 0.3/0.5/0.2 paylarıyla arıza modlarına dağıtıyordu.
        # Bu sayıların hiçbirinin kaynağı yoktu: yük/dayanım dağılımı, COV,
        # Weibull, stress-strength girişimi — hiçbiri modellenmiyor.
        # Deterministik bir SF'den kalibre edilmiş olasılığa geçilemez;
        # sayı KALDIRILDI, yerine SF bandına bağlı nitel sınıf ve dayanak
        # beyanı raporlanır.
        if yield_safety_factor < SAFETY_MODEL['sf_band_marginal']:
            failure_likelihood_class = 'HIGH'
        elif yield_safety_factor < SAFETY_MODEL['sf_band_safe']:
            failure_likelihood_class = 'MEDIUM'
        else:
            failure_likelihood_class = 'LOW'
        failure_likelihood = {
            'likelihood_class': failure_likelihood_class,
            'basis': ('deterministic safety-factor proxy - '
                      'not a calibrated probability'),
        }

        # Olası arıza modları — jenerik basınçlı kap kontrol listesi.
        # Mod başına sayısal olasılık bilinçli olarak YOKTUR (eski
        # 0.3/0.5/0.2 payları uydurmaydı); şiddet sınıfı niteldir.
        failure_modes = [
            {
                'mode': 'Catastrophic Rupture',
                'consequences': 'Complete vessel destruction, debris field',
                'severity': 'CRITICAL'
            },
            {
                'mode': 'Crack Propagation',
                'consequences': 'Gradual pressure loss, possible flame jet',
                'severity': 'HIGH'
            },
            {
                'mode': 'Seal Failure',
                'consequences': 'Pressure loss, possible fire',
                'severity': 'MEDIUM'
            }
        ]

        return {
            'hoop_stress_mpa': hoop_stress / 1e6,
            'material': material_key,
            'material_name': mat.get('name', material_key),
            'yield_strength_mpa': yield_strength / 1e6,
            'ultimate_strength_mpa': ultimate_strength / 1e6,
            'yield_safety_factor': yield_safety_factor,
            'ultimate_safety_factor': ultimate_safety_factor,
            'failure_likelihood': failure_likelihood,
            'failure_modes': failure_modes,
            'failure_modes_basis': ('generic pressure-vessel failure-mode '
                                    'checklist - not motor-specific; no '
                                    'per-mode probabilities are computed'),
            'structural_integrity': (
                'SAFE'
                if yield_safety_factor >= SAFETY_MODEL['sf_band_safe']
                else 'MARGINAL'
                if yield_safety_factor >= SAFETY_MODEL['sf_band_marginal']
                else 'UNSAFE'),
            'recommended_inspection_interval': self._calculate_inspection_interval(yield_safety_factor)
        }

    @staticmethod
    def _merge_thermal_stress_into_structural(structural_safety: Dict,
                                              thermal_safety: Dict) -> None:
        """Termal gerilmeyi yapısal hükme kat (P5B2-13). Yerinde günceller.

        Çember (basınç) gerilmesi ile termal gradyan gerilmesi aynı cidar
        kesitinde aynı anda yaşar. Birleşik emniyet katsayısı DERATE
        EDİLMİŞ akmaya göre alınır (sıcak cidarın gerçek dayanımı); ikisi
        de bu modülün ZATEN yayımladığı sayılardır.

        Kazanılmamış onay geri çekilir, kazanılmış uyarı korunur: birleşik
        katsayı yayımlanan katsayıdan DÜŞÜKSE hüküm birleşik değere göre
        yeniden verilir. Termal kol hüküm üretmediyse (cidar
        hesaplanmadı) hiçbir şey değişmez ve bu ADIYLA yazılır.
        """
        sigma_th_mpa = thermal_safety.get('thermal_stress_mpa')
        derated_mpa = thermal_safety.get('derated_yield_strength_MPa')
        hoop_mpa = structural_safety.get('hoop_stress_mpa')
        if (not isinstance(sigma_th_mpa, (int, float))
                or isinstance(sigma_th_mpa, bool)
                or not isinstance(derated_mpa, (int, float))
                or not isinstance(hoop_mpa, (int, float))
                or not np.isfinite(sigma_th_mpa)
                or not np.isfinite(derated_mpa)):
            structural_safety['combined_stress_mpa'] = None
            structural_safety['combined_safety_factor'] = None
            structural_safety['combined_stress_basis'] = (
                'NOT EVALUATED: the thermal chain did not produce a wall '
                'gradient, so the thermal stress could not be added to the '
                'hoop stress. The published yield_safety_factor therefore '
                'covers the PRESSURE load only.')
            return

        combined = float(hoop_mpa) + float(sigma_th_mpa)
        combined_sf = (float(derated_mpa) / combined if combined > 0
                       else float('inf'))
        structural_safety['thermal_stress_mpa'] = float(sigma_th_mpa)
        structural_safety['combined_stress_mpa'] = combined
        structural_safety['combined_safety_factor'] = combined_sf
        structural_safety['combined_stress_basis'] = (
            'combined_safety_factor = derated yield at the hot wall / '
            '(hoop stress + thermal gradient stress). yield_safety_factor '
            'above is the PRESSURE-ONLY factor against room-temperature '
            'yield and is kept for continuity; the verdict below is issued '
            'on the lower of the two.')
        if combined_sf < float(structural_safety.get(
                'yield_safety_factor', float('inf'))):
            structural_safety['governing_safety_factor'] = combined_sf
            structural_safety['structural_integrity'] = (
                'SAFE' if combined_sf >= SAFETY_MODEL['sf_band_safe']
                else 'MARGINAL'
                if combined_sf >= SAFETY_MODEL['sf_band_marginal']
                else 'UNSAFE')
        else:
            structural_safety['governing_safety_factor'] = float(
                structural_safety.get('yield_safety_factor'))

    def _calculate_inspection_interval(self, yield_safety_factor: float) -> str:
        """Emniyet katsayısına göre önerilen muayene aralığı.

        Basınçlı kap pratiğiyle uyumlu kaba merdiven: katsayı düştükçe
        muayene sıklaşır; 2'nin altı zaten 'UNSAFE' sınıfında raporlanıyor.
        """
        if yield_safety_factor >= SAFETY_MODEL['sf_band_safe']:
            return 'Every 12 months (visual), hydrostatic every 5 years'
        if yield_safety_factor >= SAFETY_MODEL['sf_band_intermediate']:
            return 'Every 6 months (visual), hydrostatic every 3 years'
        if yield_safety_factor >= SAFETY_MODEL['sf_band_marginal']:
            return 'Before each test campaign (visual + dye penetrant)'
        return 'Do not operate — redesign required (SF < 2)'

    def _analyze_pressure_vessel_safety(self, chamber_pressure: float, diameter: float,
                                        wall_thickness: float = 0.005,
                                        material: str = 'steel_4130') -> Dict:
        """Analyze pressure vessel safety requirements.

        DENETİM DÜZELTMESİ (2026-07-19): eskiden yalnız MEOP × sabit çarpanlar
        raporlanıyordu; kabın GERÇEKTEN kaç barda patladığı hiç hesaplanmıyordu,
        yani cidar kalınlığı ve malzeme bu panele hiç girmiyordu. Gerçek kopma
        basıncı artık merkezi PressureVesselAnalyzer'dan (Faupel kalın-cidar +
        ince-cidar plastik limit, sıcaklık derating'i) gelir — yapısal panelle
        aynı kaynak.
        """

        # Design pressure with safety factor
        design_pressure = chamber_pressure * self.safety_margins.pressure_safety_factor

        # Burst pressure requirement
        required_burst_pressure = chamber_pressure * self.safety_margins.minimum_burst_pressure_ratio

        # Pressure test requirements
        hydrostatic_test_pressure = design_pressure * 1.5
        proof_pressure = design_pressure * 1.25

        # --- GERÇEK kopma basıncı (malzeme + cidar kalınlığı + çap) ---
        actual_burst_pressure = None
        burst_margin = None
        burst_margin_vs_meop = None
        burst_margin_definition = None
        # ÖH D31 / OH-D30-13: künye de TEK KAYNAKTAN taşınır.
        actual_burst_pressure_basis = None
        vessel_status = None
        vessel_warnings: List[str] = []
        try:
            from hrma.analysis.pressure_vessel import PressureVesselAnalyzer
            pv = PressureVesselAnalyzer().analyze(
                meop_bar=max(float(chamber_pressure), 1e-6),
                inner_diameter_mm=max(float(diameter), 1e-6) * 1e3,
                material=material,
                wall_thickness_mm=max(float(wall_thickness), 1e-9) * 1e3,
            )
            actual_burst_pressure = pv['actual_burst_pressure_bar']
            burst_margin = pv['burst_margin']
            # ÖH D31 / OH-D30-13: 'actual' ÖLÇÜLMÜŞ demek değildir; künye
            # PressureVesselAnalyzer'dan olduğu gibi taşınır (metin burada
            # İCAT EDİLMEZ, tek kaynak orasıdır).
            actual_burst_pressure_basis = pv.get('actual_burst_pressure_basis')
            # ÖH D15 / P5B2-09: oranın TANIMI da taşınır (tek kaynak:
            # PressureVesselAnalyzer). Ölçüm ve gerekçe orada.
            burst_margin_vs_meop = pv.get('burst_margin_vs_meop')
            burst_margin_definition = pv.get('burst_margin_definition')
            vessel_status = pv['status']
            vessel_warnings = list(pv.get('warnings', []))
        except Exception as exc:      # malzeme/geometri geçersizse sessiz kalma
            vessel_warnings.append(
                f"Actual burst pressure could not be computed for this "
                f"geometry/material ({exc}); only code-required pressures are "
                f"shown.")

        # Pressure vessel classification
        if chamber_pressure > SAFETY_MODEL['vessel_high_pressure_bar']:
            vessel_class = 'HIGH_PRESSURE'
            inspection_requirements = 'Annual visual, 5-year hydrostatic'
        elif chamber_pressure > SAFETY_MODEL['vessel_medium_pressure_bar']:
            vessel_class = 'MEDIUM_PRESSURE'
            inspection_requirements = '2-year visual, 10-year hydrostatic'
        else:
            vessel_class = 'LOW_PRESSURE'
            inspection_requirements = '5-year visual, 15-year hydrostatic'
        
        result = {
            'operating_pressure_bar': chamber_pressure,
            'design_pressure_bar': design_pressure,
            'required_burst_pressure_bar': required_burst_pressure,
            'hydrostatic_test_pressure_bar': hydrostatic_test_pressure,
            'proof_pressure_bar': proof_pressure,
            'vessel_classification': vessel_class,
            'inspection_requirements': inspection_requirements,
            'applicable_codes': ['ASME BPVC Section VIII', 'EN 13445', 'AS 1210'],
            'safety_devices_required': self._determine_pressure_safety_devices(chamber_pressure),
            # Gerçek kap kapasitesi (malzeme + cidar kalınlığı + çap)
            'material': material,
            'wall_thickness_mm': float(wall_thickness) * 1e3,
            'inner_diameter_mm': float(diameter) * 1e3,
            'actual_burst_pressure_bar': actual_burst_pressure,
            # OH-D30-13: aynı sayı, dürüst adıyla + künyesiyle.
            'predicted_burst_pressure_bar': actual_burst_pressure,
            'actual_burst_pressure_basis': actual_burst_pressure_basis,
            'burst_margin': burst_margin,
            # ÖH D15 / P5B2-09: aynı anahtar adının iki tanımı taşımasına
            # son. Sayı değişmedi; tanım artık adında.
            'burst_margin_vs_required_burst': burst_margin,
            'burst_margin_vs_meop': burst_margin_vs_meop,
            'burst_margin_definition': burst_margin_definition,
            'design_pressure_basis': (
                'design_pressure_bar = MEOP x '
                f'{self.safety_margins.pressure_safety_factor:g} '
                '(SafetyMargins.pressure_safety_factor). The solid-motor '
                'result publishes a design pressure built on a DIFFERENT '
                'multiplier under the same key name, so the multiplier is '
                'named here.'),
            'vessel_status': vessel_status,
            'vessel_warnings': vessel_warnings,
            'burst_pressure_source': (
                'Faupel thick-wall / thin-wall plastic limit '
                '(hrma.analysis.pressure_vessel)'),
        }
        return result

    def _analyze_thermal_safety(self, motor_data: Dict,
                                material: str = 'steel_4130') -> Dict:
        """Analyze thermal safety and heat-related hazards.

        DENETİM DÜZELTMESİ (2026-07-19). Eski sürümdeki üç uydurma kaldırıldı:
          (a) cidar sıcaklığı = 0.3 × hazne sıcaklığı sabit katsayısı,
          (b) termal gerilme sabit çelik özellikleriyle (E=200 GPa, alfa=12e-6)
              ve tam ankastre varsayımıyla — malzeme seçimi sonucu hiç
              değiştirmiyordu,
          (c) radyan tehlike mesafesine ışıyan ALAN yerine cidar kalınlığının
              100 katının geçilmesi (birim hatası; cidar kalınlaştıkça tehlike
              mesafesi büyüyordu).

        Yeni zincir:
          1) Cidar sıcaklığı: motor_data['wall_temperature_hot'/'cold']
             sözleşmesi (ısı transferi modülünün GERÇEK sonucu) varsa o;
             yoksa HeatTransferAnalyzer (Bartz + yüzey enerji dengesi)
             burada çağrılır. Yapısal panel ile aynı kaynak.
          2) Termal gerilme: seçilen malzemenin materials_db değerleriyle
             klasik cidar-gradyan formu sigma = E*alfa*dT/(2(1-nu))
             (Timoshenko/Boley-Weiner; structural_analysis ile AYNI form).
          3) Radyan tehlike: gerçek dış yüzey alanı ve DIŞ CİDAR sıcaklığı
             (hazne gazı sıcaklığı değil). Uzunluk verilmemişse varsayım
             'radiating_area_basis' alanında açıkça beyan edilir.

        ÖH Z3 / P5B2-01 (kritik) — **HESAPLANMAYAN CİDARDAN HÜKÜM ÇIKMAZ.**
        ÖLÇÜLDÜ (2026-08-27, HEAD b54a66b): ısı zinciri girdisi eksik olan her
        çağrıda (``chamber_length`` ya da boğaz ölçeği yoksa)
        ``_resolve_wall_temperatures`` ortam sıcaklığına düşüyor ve bu modül
        293,15 K'yi GERÇEK cidar gibi işleyip tam bir termal hüküm
        yayımlıyordu::

            gaz 3000 K, alüminyum (limit 477 K), ısı zinciri KOŞMADI
              -> estimated_wall_temperature_k = 293,15
              -> material_thermal_safety_factor = 1,627
              -> material_recommendation = 'Selected material acceptable'
              -> cooling_required = False, termal risk ekseni = 2,0

        Yani cidar sıcaklığı hiç hesaplanmadığı hâlde malzeme ONAYLANIYORDU;
        üstelik yedeğin kendi künyesi ("NOT COMPUTED ... must not be used for
        design") bunu yasaklıyordu — künye yazılıyor, kimse okumuyordu.
        Sözleşme artık deponun kardeş kapılarıyla aynı: ONAY geri çekilir,
        anahtarlar SİLİNMEZ (panel ve sözleşme testleri onları okuyor),
        hesaplanmamış sayı ``None`` olur ve nedeni makine-okur alanlarda
        yazılır (``thermal_verdict`` / ``thermal_verdict_withheld_because`` /
        ``thermal_not_evaluated``).
        """
        # --- FİZİK KAPISI (ÖH D15 / a3; P5B2-17) --------------------------
        # ÖLÇÜLDÜ (a3/once.json, aluminum_6061): cidar sıcaklığı olarak
        # -500 K verildiğinde bu fonksiyon ``material_thermal_safety_factor
        # = inf``, ``material_recommendation = 'Selected material
        # acceptable'`` ve termal risk ekseninde 2,0 (kümenin EN GÜVENLİ
        # hükmü) üretiyordu; +1e9 K verildiğinde ise uçta HTTP 200 ile tam
        # bir termal hüküm basılıyordu. İki uç da fizik dışıdır ve fizik
        # dışı girdiden hüküm kazanılmaz — bant deponun KENDİ kanonik
        # tablosundan okunur (``sicaklik_bandi_K``), yeni eşik yoktur.
        for _ad in ('chamber_temperature', 'wall_temperature_hot',
                    'wall_temperature_cold', 'ambient_temperature'):
            if motor_data.get(_ad) is not None:
                _sicaklik_kapisi(_ad, motor_data[_ad])

        chamber_temperature = float(motor_data.get('chamber_temperature', 3000))
        wall_thickness = float(motor_data.get('wall_thickness', 0.005) or 0.005)
        chamber_diameter = float(motor_data.get('chamber_diameter', 0.1) or 0.1)
        # ÖH D36 / onemli2-sivi a2: ``get('burn_time', 10) or 10`` kalktı —
        # süre verilmediyse None; ona bağlı üç alan (THERMAL_BURN_TIME_FIELDS)
        # aşağıda adıyla geri çekilir. Verildiyse float'a çevrilir (eskisiyle
        # aynı sayı).
        burn_time = _yanma_suresi(motor_data.get('burn_time'))
        ambient = float(motor_data.get('ambient_temperature',
                                       SAFETY_MODEL['ambient_temperature_k']))

        # P5B2-03: termal kolun da sessiz çelik yedeği vardı.
        mat, material_key = self._resolve_chamber_material(material)

        # --- 1) Gerçek cidar sıcaklıkları -----------------------------------
        wall_hot, wall_cold, wall_source = self._resolve_wall_temperatures(
            motor_data, material_key, wall_thickness, ambient)

        # --- Malzeme sıcaklık sınırları (materials_db, sabit 800/600 K değil)
        # ÖH D37 A2-1 termal 8. tur (karar §28-31 Ş5 (a); Astra §3 "diğer
        # tüketiciler", §28-24 tek eşik): SEÇİLEN malzemenin sınırı da tek
        # eşik fonksiyonunun İZİN basamağıdır. ÖLÇÜLDÜ (yeniden denetim-7):
        # bu satır ham ``max_service_temp``i okuyordu (ss_304 / ss_316 1143,
        # carbon_carbon 2273 K) — aynı bloğun steel/aluminum referansları 7.
        # turdan beri kanonik (aşağıda) ve motorun ısı zinciri 1073 / 1920 K
        # kullanıyordu: bir yanıtta aynı malzeme için iki eşik. Basamak yoksa
        # (kayıtta iki alan da yok) kıyas YAPILMAZ: nan (eski davranışla aynı).
        from hrma.data.materials_db import temperature_limits as _tek_esik
        _izin_K = _tek_esik(mat)['allowable_K']
        selected_limit = (float(_izin_K) if _izin_K is not None else np.nan)
        # ``or np.nan``: kaydında erime noktası olmayan (ya da 0 yazılmış) bir
        # malzemede kıyas YAPILMAZ — hüküm 'bilinmiyor'a düşer, 0 K'lik bir
        # erime noktası uydurulmaz. Bugün 24 malzemenin 24'ünde alan dolu.
        melting_point = float(mat.get('melting_point') or np.nan)
        # ÖH D37 A2-1 termal 7. tur (karar §28-24 §3): referans sınırlar da
        # TEK EŞİK fonksiyonundan (izin basamağı). Bugün sayı bit-aynı:
        # steel_4130 min(1000, 811) = 811, aluminum_6061 477 (ölçüldü).
        steel_limit = float(_tek_esik('steel_4130')['allowable_K'])
        aluminum_limit = float(_tek_esik('aluminum_6061')['allowable_K'])

        # --- 3) Işıyan yüzey: GEOMETRİDİR, ısı zincirine bağlı değildir -----
        # (Cidar sıcaklığı hesaplanamasa bile alan ve dayanağı doğrudur.)
        area, area_basis = self._radiating_surface_area(
            chamber_diameter, wall_thickness, motor_data)
        emissivity = float(mat.get('emissivity',
                                   SAFETY_MODEL['default_surface_emissivity']))

        # Her iki dalda da AYNI anahtar kümesi döner: panel/sözleşme
        # tüketicileri anahtar arar, kapı yalnız DEĞERİ geri çeker.
        sonuc = {
            'chamber_temperature_k': chamber_temperature,
            'wall_temperature_source': wall_source,
            'material': material_key,
            'material_name': mat.get('name', material_key),
            'material_max_service_temp_k': selected_limit,
            'material_melting_point_k': melting_point,
            'thermal_stress_formula': (
                'sigma_th = E*alpha*dT/(2*(1-nu)) with the selected material '
                'and the through-wall gradient'),
            'radiating_area_m2': area,
            'radiating_area_basis': area_basis,
            'surface_emissivity': emissivity,
            'exposure_duration_s': burn_time,
            'thermal_verdict': THERMAL_VERDICT_ISSUED,
            'thermal_verdict_withheld_because': None,
            'thermal_not_evaluated': [],
        }

        if not self._wall_temperature_was_computed(wall_source):
            # KAPI: cidar sıcaklığı HESAPLANMADI. Ortam sıcaklığından
            # türetilen her sayı bu motoru değil, oda sıcaklığındaki bir
            # boruyu anlatır; yayımlanmaz.
            sonuc['thermal_not_evaluated'] = [
                'estimated_wall_temperature_k', 'inner_wall_temperature_k',
                'outer_wall_temperature_k', 'wall_delta_T_k',
                'material_thermal_safety_factor', 'melting_safety_factor',
                'steel_thermal_safety_factor', 'aluminum_thermal_safety_factor',
                'thermal_stress_mpa', 'thermal_stress_safety_factor',
                'material_yield_strength_MPa',
                'derated_yield_strength_MPa',
                'radiating_surface_temperature_k',
                'radiant_heat_hazard_distance_m',
                'radiant_flux_at_hazard_distance_kw_m2',
                'second_degree_burn_distance_m',
                'recommended_minimum_standoff_m', 'material_recommendation',
                'cooling_required', 'thermal_protection_required',
            ]
            sonuc.update({key: None for key in sonuc['thermal_not_evaluated']})
            sonuc.update({
                'material_recommendation': THERMAL_VERDICT_NOT_EVALUATED,
                'wall_exceeds_melting_point': None,
                'thermal_verdict': THERMAL_VERDICT_WITHHELD,
                'thermal_verdict_withheld_because': (
                    'The wall temperature was not computed for this motor, so '
                    'no thermal verdict is issued. The values that used to '
                    'appear here were the ambient fallback (a room-temperature '
                    'wall), not a computed one, and a material cannot be '
                    'accepted against a temperature that was never evaluated. '
                    'Supply the heat-chain inputs (chamber_length and one of '
                    'throat_diameter / throat_area / mdot_total) or the '
                    'wall_temperature_hot/cold pair. Solver report: '
                    + str(wall_source)),
            })
            if burn_time is None:
                self._burn_time_kolunu_geri_cek(sonuc, THERMAL_BURN_TIME_FIELDS)
            return sonuc

        # --- 2) Termal gerilme: seçilen malzeme + gerçek cidar gradyanı -----
        delta_T_wall = max(0.0, wall_hot - wall_cold)
        E = float(mat['elastic_modulus'])
        alpha = float(mat['thermal_expansion'])
        nu = float(mat['poisson_ratio'])
        thermal_stress_estimate = E * alpha * delta_T_wall / (2.0 * (1.0 - nu))

        # --- P5B2-13 (ÖH D15 / a3): TERMAL GERİLME BİR HÜKÜM ÜRETİR ------
        # ÖLÇÜLDÜ (a3/once.json; steel_4130, cidar 2801/400 K, 70 bar):
        # ``thermal_stress_mpa = 4045,52`` yayımlanıyordu — malzemenin
        # 460 MPa akmasının 8,79 KATI — ama hiçbir hükme girmiyordu.
        # Ayırt edici kanıt: skorlayıcıya gerilme 1,0 / 4045,5 / hiç
        # verilmediğinde ÜÇÜNDE DE skor 5,0 çıkıyordu, yani sayı
        # okunmuyordu bile. Bir bölüm kendi termal gerilmesiyle akıyorsa
        # o motorun termal ekseni "değerlendirildi" sayılamaz.
        #
        # Kıyas tabanı DERATE EDİLMİŞ akma dayanımıdır (sıcak cidarın
        # gerçek dayanımı) ve kaynağı deponun KENDİ tek noktasıdır:
        # ``PressureVesselAnalyzer._derate_strength`` — bu modülün kopma
        # basıncını da aynı sınıf veriyor. Yeni sabit yazılmadı.
        derated_yield_pa = None
        try:
            from hrma.analysis.pressure_vessel import PressureVesselAnalyzer
            derated_yield_pa = float(
                PressureVesselAnalyzer()._derate_strength(mat, wall_hot)
                ['derated_yield_strength_Pa'])
        except Exception:                       # derating okunamadı: uydurma
            derated_yield_pa = None             # yapılmaz, SF None kalır
        thermal_stress_sf = (
            derated_yield_pa / thermal_stress_estimate
            if (derated_yield_pa is not None and thermal_stress_estimate > 0)
            else (float('inf') if derated_yield_pa is not None else None))

        steel_thermal_safety = steel_limit / wall_hot if wall_hot > 0 else float('inf')
        aluminum_thermal_safety = (aluminum_limit / wall_hot
                                   if wall_hot > 0 else float('inf'))
        selected_thermal_safety = (selected_limit / wall_hot
                                   if wall_hot > 0 else float('inf'))
        # Erime marjı: servis sınırı BOZULMA, erime noktası YOK OLMA sınırıdır.
        # İkisi ayrı büyüklüktür ve materials_db ikisini de yayımlıyor.
        melting_safety = (melting_point / wall_hot if wall_hot > 0
                          else float('inf'))

        radiant_heat_distance = self._calculate_radiant_heat_distance(
            wall_cold, area, emissivity=emissivity, ambient=ambient)

        # Maruziyet dozu: yanma süresi burada GERÇEKTEN kullanılıyor.
        flux_at_distance = self._radiant_flux_at(
            wall_cold, area, radiant_heat_distance, emissivity, ambient)
        # ÖH D36 / onemli2-sivi a2: süre yoksa doz mesafesi HESAPLANMAZ
        # (eskiden 10 s ile hesaplanıyordu); ondan türeyen önerilen duruş
        # mesafesi de yayımlanmaz. Işınım tehlike mesafesi ve akısı süreye
        # bağlı DEĞİLDİR, kalır.
        burn_distance = (None if burn_time is None
                         else self._burn_dose_distance(
                             wall_cold, area, burn_time, emissivity, ambient))
        radyan_asiyor = (radiant_heat_distance
                         > SAFETY_MODEL['min_hazard_distance_m'])

        sonuc.update({
            'estimated_wall_temperature_k': wall_hot,
            'inner_wall_temperature_k': wall_hot,
            'outer_wall_temperature_k': wall_cold,
            'wall_delta_T_k': delta_T_wall,
            'material_thermal_safety_factor': selected_thermal_safety,
            'melting_safety_factor': melting_safety,
            'wall_exceeds_melting_point': bool(
                np.isfinite(melting_point) and wall_hot >= melting_point),
            'steel_thermal_safety_factor': steel_thermal_safety,
            'aluminum_thermal_safety_factor': aluminum_thermal_safety,
            'thermal_stress_mpa': thermal_stress_estimate / 1e6,
            # P5B2-13: gerilmenin KIYASI da yayımlanır — sayının yanında
            # onu hükme çeviren oran durur.
            'thermal_stress_safety_factor': thermal_stress_sf,
            'material_yield_strength_MPa': float(mat['yield_strength']) / 1e6,
            'derated_yield_strength_MPa': (None if derated_yield_pa is None
                                           else derated_yield_pa / 1e6),
            'thermal_stress_basis': (
                'thermal_stress_safety_factor = derated yield strength at the '
                'hot-wall temperature / sigma_th. The derating comes from the '
                'same source as the burst pressure '
                '(pressure_vessel._derate_strength, MMPDS derating curve). '
                'A factor below 1 means the wall yields from the thermal '
                'gradient alone, before any pressure load is applied.'),
            'radiating_surface_temperature_k': wall_cold,
            'radiant_heat_hazard_distance_m': radiant_heat_distance,
            'radiant_flux_at_hazard_distance_kw_m2': flux_at_distance / 1000.0,
            'second_degree_burn_distance_m': burn_distance,
            'recommended_minimum_standoff_m': (None if burn_distance is None
                                               else max(
                radiant_heat_distance, burn_distance,
                SAFETY_MODEL['min_hazard_distance_m'])),
            'material_recommendation': (
                'Selected material acceptable'
                if selected_thermal_safety
                > self.safety_margins.temperature_safety_factor
                else 'Insulation or a higher-temperature alloy required'),
            'cooling_required': bool(
                wall_hot > selected_limit
                / self.safety_margins.temperature_safety_factor),
            # Süre yokken: ışınım kolu uyarıyı KAZANDIYSA korunur (True);
            # kazanmadıysa "gerekmez" demek süreye bağlı olurdu -> None.
            'thermal_protection_required': (
                bool(radyan_asiyor
                     or burn_distance > SAFETY_MODEL['min_hazard_distance_m'])
                if burn_distance is not None
                else (True if radyan_asiyor else None)),
        })
        if burn_time is None:
            self._burn_time_kolunu_geri_cek(
                sonuc, THERMAL_BURN_TIME_FIELDS + (
                    ('thermal_protection_required',)
                    if sonuc['thermal_protection_required'] is None else ()))
        return sonuc

    @staticmethod
    def _burn_time_kolunu_geri_cek(blok: Dict, adlar) -> None:
        """Süre verilmediğinde ``adlar`` kolunu ADIYLA geri çeker (yerinde).

        ÖH D36 / onemli2-sivi a2. Değer ``None`` olur; blok, hangi alanı
        neden yayımlamadığını makine-okur üç alanla söyler
        (``burn_time_not_evaluated`` / ``burn_time_status`` /
        ``burn_time_reason``). Süre verildiğinde bu işlev ÇAĞRILMAZ ve blok
        bit-aynı kalır. ``thermal_not_evaluated`` listesine DOKUNULMAZ: o
        liste cidar sıcaklığı kapısının beyanıdır ve panel gerekçesini
        ``thermal_verdict_withheld_because``tan okur.
        """
        for ad in adlar:
            blok[ad] = None
        blok['burn_time_not_evaluated'] = list(adlar)
        blok['burn_time_status'] = BURN_TIME_NOT_EVALUATED
        blok['burn_time_reason'] = BURN_TIME_NOT_SUPPLIED_REASON

    @staticmethod
    def _wall_temperature_was_computed(wall_source) -> bool:
        """Cidar sıcaklığı GERÇEKTEN hesaplandı mı?

        Tek doğruluk kaynağı ``_resolve_wall_temperatures``ın künyesidir:
        yedek dala düştüğünde künye ``WALL_TEMP_NOT_COMPUTED`` öneki ile
        başlar. Sayının kendisine bakmak (293,15 K mi?) yanıltıcı olurdu —
        gerçekten oda sıcaklığında bir cidar da olabilir.
        """
        return not str(wall_source or '').startswith(WALL_TEMP_NOT_COMPUTED)

    # ------------------------------------------------------------------
    # Termal emniyet yardımcıları
    # ------------------------------------------------------------------
    def _resolve_wall_temperatures(self, motor_data: Dict, material: str,
                                   wall_thickness: float,
                                   ambient: float) -> Tuple[float, float, str]:
        """(T_ic, T_dis, kaynak) — sabit katsayı YOK.

        Öncelik:
          1) motor_data['wall_temperature_hot'/'wall_temperature_cold']
             (motor zincirlerinin doldurduğu sözleşme)
          2) HeatTransferAnalyzer.analyze_heat_transfer (Bartz + yüzey enerji
             dengesi) — projedeki tek gerçek cidar sıcaklığı kaynağı
          3) Hiçbiri çalışmazsa ortam sıcaklığı + AÇIK uyarı (uydurma sayı
             döndürmek yerine hesaplanamadığını söyler)

        ÖH Z3 / P5B2-01: üçüncü dalın künyesi artık ``WALL_TEMP_NOT_COMPUTED``
        önekiyle başlar ve ÇAĞIRAN bunu okur — yedek sayı hüküm üretemez
        (bkz. ``_wall_temperature_was_computed``). Önek bir sabittir; künye
        metni değişse bile kapı çalışmaya devam eder.
        """
        hot = motor_data.get('wall_temperature_hot')
        cold = motor_data.get('wall_temperature_cold')
        if hot is not None and cold is not None:
            return (float(hot), float(cold),
                    'motor_data wall_temperature_hot/cold contract')

        try:
            from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
            ht = HeatTransferAnalyzer().analyze_heat_transfer(
                motor_data, material=material,
                wall_thickness=max(float(wall_thickness), 1e-6),
                ambient_temp=ambient,
                cooling_type=motor_data.get('cooling_type', 'natural'))
            wall = ht['wall_analysis']
            return (float(wall['inner_temperature']),
                    float(wall['outer_temperature']),
                    'HeatTransferAnalyzer (Bartz gas side + surface energy balance)')
        except Exception as exc:
            return (float(ambient), float(ambient),
                    f'{WALL_TEMP_NOT_COMPUTED} - heat transfer chain failed '
                    f'({exc}); wall temperature defaulted to ambient and must '
                    f'not be used for design')

    def _radiating_surface_area(self, chamber_diameter: float,
                                wall_thickness: float,
                                motor_data: Dict) -> Tuple[float, str]:
        """Motor gövdesinin dış ışıyan yüzey alanı [m²] ve dayanağı.

        A = pi*D_dis*L + 2*(pi/4)*D_dis²  (silindir + iki uç kapak).
        Uzunluk verilmemişse varsayılan narinlik kullanılır ve bu, dönen
        metinde AÇIKÇA beyan edilir — sessiz varsayım bırakılmaz.
        """
        d_outer = float(chamber_diameter) + 2.0 * float(wall_thickness)
        length = motor_data.get('chamber_length') or motor_data.get('motor_length')
        if length:
            length = float(length)
            basis = 'computed from chamber_diameter, wall_thickness and chamber_length'
        else:
            length = SAFETY_MODEL['assumed_length_to_diameter'] * float(chamber_diameter)
            basis = (f"ASSUMED L/D = {SAFETY_MODEL['assumed_length_to_diameter']:.0f} "
                     f"(chamber_length was not supplied)")
        area = np.pi * d_outer * length + 2.0 * (np.pi / 4.0) * d_outer ** 2
        return float(area), basis

    def _radiant_flux_at(self, surface_temperature: float, area: float,
                         distance: float, emissivity: float,
                         ambient: float) -> float:
        """Verilen mesafede radyan akı [W/m²] (nokta kaynak yaklaşımı)."""
        sigma = SAFETY_MODEL['stefan_boltzmann']
        power = emissivity * sigma * max(
            surface_temperature ** 4 - ambient ** 4, 0.0) * max(area, 0.0)
        if distance <= 0:
            return 0.0
        return float(power / (4.0 * np.pi * distance ** 2))

    def _analyze_explosive_hazards(self, propellant_mass: float, propellant_type: str,
                                   thrust: float,
                                   burn_time: Optional[float] = None,
                                   motor_type: Optional[str] = None,
                                   motor_data: Optional[Dict] = None,
                                   material: str = 'steel_4130') -> Dict:
        """Analyze explosive hazards and calculate safety distances.

        DENETİM DÜZELTMESİ (2026-07-19): motor_type artık patlayıcı sınıfını
        seçiyor (eskiden tamamen düşüyordu) ve thrust/burn_time serbest kalan
        motor tehlikesinde GERÇEKTEN kullanılıyor (eski imza thrust'ı alıp
        gövdede hiç kullanmıyordu).
        """

        # TNT equivalent calculation — sınıf çözümü motor tipini de dikkate alır
        class_key, class_basis = self._resolve_explosive_class(
            propellant_type, motor_type)

        # Parçacık tehlikesi TNT eşdeğerine DEĞİL, kütle/itki/geometriye
        # bakar; sınıf kazanılmasa da hak edilmiş bir ölçüdür ve kardeş
        # eksen sözleşmesi uyarınca geri çekilmez (ÖH Z5S eksen-bazlı geri
        # çekme: kazanılmayan EKSEN adıyla çekilir, kazanılan yayımlanır).
        fragment_hazards = self._calculate_fragment_hazards(
            propellant_mass, thrust, burn_time, motor_data, material)

        # --- ÖH D35 / OH-ON-06 · KAZANILMAYAN PATLAYICI EKSENİ -----------
        # Sınıf çözülemediyse TNT eşdeğeri, patlama mesafeleri, QD şartları,
        # HD sınıflandırması ve depolama/taşıma şartlarının TNT'ye bağlı
        # maddeleri YAYIMLANMAZ (doktrin 1). Yanıt 200 kalır: yangın, toksik
        # ve yapısal eksenler hâlâ anlamlı olabilir ve onların hükmü bu
        # eksenin eksikliği yüzünden kullanıcıdan esirgenmez (OH-D30-11'in
        # 422 denemesinin ÖLÇÜMLE geri alınma gerekçesi).
        if class_key is None:
            # Eksen-bazlı geri çekmenin bedeli, KAZANILMIŞ içeriği de
            # yutmak DEĞİLDİR. Depolama/taşıma listelerinin koşulsuz
            # maddeleri (ayrı depolama, topraklama, ADR/DOT künyesi) ne
            # TNT eşdeğerine ne de itici kimliğine bakar — onlar her motor
            # için geçerlidir ve yayımlanır. Yalnız EŞİĞE bağlı maddeler
            # (magazin/QD yerleşimi, Sınıf 1 güzergâh şartı) ve sıvıya özel
            # madde geri çekilir; ölçülemeyen bir eşik karşılaştırması
            # "eşiğin altında" diye SESSİZCE geçilemez.
            beyan = self._explosive_not_modelled(propellant_type,
                                                 motor_type)
            if beyan is not None:
                # ÖH D37 A1b panel-js 5. tur: Gurney bağıntısı itici
                # kütlesini PATLAYICI ŞARJ sayar (C). Patlayıcı modeli
                # olmayan iticide parça hızı, menzil ve onlardan türeyen
                # tahliye de kazanılmamıştır; anahtarlar SİLİNMEZ
                # (tüketiciler anahtar arar), değer None + durum + gerekçe.
                # Kasa kütlesi ve serbest kalan motor (impuls/itki) şarjdan
                # bağımsızdır, AYNEN kalır.
                fragment_hazards = dict(fragment_hazards)
                for alan in GURNEY_FRAGMENT_FIELDS:
                    fragment_hazards[alan] = None
                fragment_hazards['fragment_throw_status'] = beyan['status']
                fragment_hazards['fragment_throw_reason'] = beyan['reason']
            geri_cekme = {
                'propellant_mass_kg': propellant_mass,
                'explosive_class': None,
                'explosive_class_basis': class_basis,
                'explosive_verdict_withheld_because': class_basis,
                'fragment_hazards': fragment_hazards,
                'storage_requirements': self._determine_storage_requirements(
                    None, None),
                'transport_requirements':
                    self._determine_transport_requirements(None, None),
                'requirements_scope': (
                    'Unconditional items only: the TNT-threshold items '
                    '(magazine siting, Class 1 routing) are withheld with '
                    'the explosive verdict.'),
            }
            # Anahtar YALNIZ beyan varken eklenir: çözülemeyen ad kolunun
            # yanıtı (OH-ON-06 / OH-AS-03 bekçileri) bayt bayt aynı kalır.
            if beyan is not None:
                geri_cekme['explosive_not_modelled'] = beyan
            return geri_cekme

        tnt_factor = self.propellant_tnt_equivalents[class_key]
        tnt_equivalent = propellant_mass * tnt_factor

        # Blast overpressure distances (Hopkinson-Cranz law)
        distances = self._calculate_blast_distances(tnt_equivalent)

        # Quantity-distance (Q-D) requirements
        qd_requirements = self._calculate_qd_requirements(tnt_equivalent)

        return {
            'propellant_mass_kg': propellant_mass,
            'tnt_equivalent_kg': tnt_equivalent,
            'tnt_equivalent_factor': tnt_factor,
            'explosive_class': class_key,
            'explosive_class_basis': class_basis,
            'blast_distances': distances,
            'fragment_hazards': fragment_hazards,
            'qd_requirements': qd_requirements,
            'explosive_classification': self._classify_explosive_hazard(tnt_equivalent),
            'storage_requirements': self._determine_storage_requirements(tnt_equivalent, propellant_type),
            'transport_requirements': self._determine_transport_requirements(tnt_equivalent, propellant_type)
        }
    
    def _analyze_toxic_hazards(self, propellant_type: str,
                               propellant_mass: float,
                               facility_type: str,
                               motor_type=None) -> Dict:
        """Analyze toxic hazard exposure and safety distances.

        ÖH Z5S / S6 (P7B3-21, KRİTİK) — hüküm KAZANILIR. Sınıflandırma
        ``_classify_toxic_inventory``tan gelir ve üç ayrı sonuç üretir:
        envanter çözüldüyse tam hüküm, sınıf çözülmediyse/envanteri
        belirlenemiyorsa ``NOT_EVALUATED`` (fail-closed), tablolu bileşeni
        olmayan tanınan sınıfta ise KAPSAMI beyan edilmiş ``'NONE'``.
        """

        kunye = self._classify_toxic_inventory(propellant_type, motor_type)
        toxic_components = list(kunye['components'])
        cozunurluk = kunye['resolution']

        if not toxic_components:
            # Hüküm geri çekilen iki dal: çözülemeyen sınıf ve envanteri
            # sınıf adından belirlenemeyen sınıf. Bilinmeyen bir itici
            # "toksik değil" DEĞİLDİR; seviye yayımlanmaz.
            geri_cekildi = cozunurluk in (TOXIC_RESOLUTION_UNRECOGNISED,
                                          TOXIC_RESOLUTION_UNDETERMINED)
            govde = {
                'toxic_hazard_level': (TOXIC_LEVEL_NOT_EVALUATED
                                       if geri_cekildi else 'NONE'),
                'toxic_components': [],
                'exposure_limits': {},
                # Envanter yoksa da tesis PPE'si vardır: eski kod bu dalda
                # boş liste basıyordu ve "hiç koruyucu gerekmez" gibi
                # okunuyordu. Aynı yardımcı (``_determine_toxic_ppe_
                # requirements``) boş envanter için standart tezgâh PPE'si
                # döndürüyordu ama HİÇ ÇAĞRILMIYORDU.
                'ppe_requirements': self._determine_toxic_ppe_requirements([]),
                'toxic_inventory_resolution': cozunurluk,
                'toxic_inventory_basis': kunye['basis'],
                'propellant_class': kunye['propellant_class'],
                'propellant_class_source': kunye.get(
                    'propellant_class_source'),
                'known_propellant_classes': kunye['known_propellant_classes'],
                'resolvable_propellant_classes': kunye[
                    'resolvable_propellant_classes'],
                'guidance_basis': self._toxic_guidance_basis(),
                'disclaimer_code': 'warn.safety.guidance_not_authoritative',
            }
            if geri_cekildi:
                govde['detection_required'] = TOXIC_LEVEL_NOT_EVALUATED
                govde['toxic_hazard_level_withheld_because'] = (
                    'No toxic inventory could be identified for this '
                    'propellant, so no toxic hazard level was computed. '
                    'A hazard that was not assessed is not an absent hazard.')
            else:
                govde['detection_required'] = False
            return govde

        # Calculate worst-case release scenario
        release_scenarios = []
        for component in toxic_components:
            scenario = self._calculate_toxic_release_scenario(
                component, propellant_mass, facility_type
            )
            release_scenarios.append(scenario)
        
        # Determine detection requirements
        detection_requirements = self._determine_toxic_detection_requirements(toxic_components)
        
        # PPE requirements
        ppe_requirements = self._determine_toxic_ppe_requirements(toxic_components)
        
        return {
            'toxic_hazard_level': self._assess_toxic_hazard_level(release_scenarios),
            'toxic_components': toxic_components,
            'release_scenarios': release_scenarios,
            'detection_requirements': detection_requirements,
            'ppe_requirements': ppe_requirements,
            'exposure_monitoring': self._determine_exposure_monitoring(toxic_components),
            'emergency_treatment': self._determine_emergency_treatment(toxic_components),
            # Hükmün NEREDEN kazanıldığı (ÖH Z5S / S6): hangi sınıfa
            # çözüldüğü ve envanterin hangi kuralla belirlendiği.
            'toxic_inventory_resolution': cozunurluk,
            'toxic_inventory_basis': kunye['basis'],
            'propellant_class': kunye['propellant_class'],
            'propellant_class_source': kunye.get('propellant_class_source'),
            'known_propellant_classes': kunye['known_propellant_classes'],
            'resolvable_propellant_classes': kunye[
                'resolvable_propellant_classes'],
            # SAFE-TEXT-3 (2026-07-28): PPE/tıbbi/mesafe metinleri genel
            # emniyet pratiğinden derlenmiş kontrol listeleridir; belirli bir
            # standart maddesine veya SDS'e bağlanmamıştır. Compliance
            # rozetlerindeki NOT_EVALUATED + disclaimer_code deseninin
            # danışma-metni karşılığı: içerik korunur, dayanağı beyan edilir.
            'guidance_basis': self._toxic_guidance_basis(),
            'disclaimer_code': 'warn.safety.guidance_not_authoritative',
        }

    @staticmethod
    def _toxic_guidance_basis() -> Dict:
        """Toksik tehlike danışma metinlerinin yapılandırılmış kaynak beyanı."""
        return {
            'release_scenarios': ('generic sqrt(mass) scaling with '
                                  'tool-chosen coefficients - not an '
                                  'ERG/dispersion-model result'),
            'ppe_requirements': ('general hypergolic/toxic handling '
                                 'practice - not tied to a specific '
                                 'standard clause'),
            'emergency_treatment': ('general first-aid checklist - NOT '
                                    'medical advice; this software is not '
                                    'a physician'),
            'verification_required': ('confirm against the propellant SDS, '
                                      'current DOT Emergency Response '
                                      'Guidebook guidance and the '
                                      'responsible occupational physician / '
                                      'industrial-hygiene assessment '
                                      'before use'),
        }
    
    def _analyze_fire_hazards(self, propellant_type: str, propellant_mass: float, motor_data: Dict) -> Dict:
        """Analyze fire hazards and suppression requirements"""
        
        # Fire classification
        fire_class = self._classify_fire_hazard(
            propellant_type, motor_data.get('motor_type'))
        
        # Auto-ignition analysis
        # P5B2-14: motor tipi tutuşma koluna da geçer (sınıf çözümü için).
        auto_ignition_risk = self._assess_auto_ignition_risk(
            propellant_type, motor_data.get('chamber_temperature', 3000),
            motor_type=motor_data.get('motor_type')
        )
        
        # Fire spread analysis
        fire_spread = self._analyze_fire_spread_potential(propellant_mass, propellant_type)
        
        # Suppression requirements
        suppression_system = self._determine_fire_suppression_system(
            fire_class, propellant_mass, auto_ignition_risk
        )
        
        return {
            'fire_classification': fire_class,
            'auto_ignition_risk': auto_ignition_risk,
            'fire_spread_potential': fire_spread,
            'suppression_system': suppression_system,
            'fire_safety_distances': self._calculate_fire_safety_distances(propellant_mass),
            'ignition_sources_control': self._identify_ignition_sources_control(),
            'fire_fighting_procedures': self._generate_fire_fighting_procedures(fire_class)
        }
    
    def _calculate_blast_distances(self, tnt_equivalent: float) -> Dict:
        """Aşırı-basınç seviyelerinin mesafeleri — Kinney-Graham'dan TÜRETİLİR.

        ÖH D26 / P5B2-05 (yüksek) — ÖLÇÜLDÜ (D26 tabanı 7751531, kanıt
        ``docs/scofield/raw/OH/D26/yapisal-sistem/a1/once.json``; 5 kg
        hidrazin -> 2,1 kg TNT). Modül mesafeleri Kinney-Graham'a ATIF
        VEREREK yayımlıyordu ama sayıları elle yazılmış bir Z tablosundan
        alıyordu ve tablo o bağıntıyla UYUŞMUYORDU — üstelik hepsi KISA
        tarafta::

            seviye            yayımlanan   Kinney-Graham   o mesafede    hata
            lethal (100 kPa)    3,0734 m       3,5209 m     136,247 kPa  -12,7 %
            serious (35 kPa)    5,7626 m       5,8139 m      35,597 kPa   -0,9 %
            minor (7 kPa)      13,4461 m      17,0053 m       9,369 kPa  -20,9 %
            property (2 kPa)   25,6116 m      54,2554 m       4,393 kPa  -52,8 %

        Kodun kendi yorumu "değerler konservatif (biraz büyük) tarafta"
        diyordu; ÖLÇÜM tam TERSİNİ söylüyor. Bir emniyet mesafesinin kısa
        yayımlanması, kullanıcıyı 100 kPa sandığı yerde 136 kPa'ya
        yerleştirir.

        ONARIM: tablo SÖKÜLDÜ. Z artık atıf verilen bağıntının kendisinden
        sayısal olarak çözülür (:func:`kinney_graham_overpressure_kpa` ters
        çevrilir), yani yayımlanan mesafe ile beyan edilen model arasında
        sapma YAPISAL OLARAK doğamaz. Yeni bir sayı kalibre EDİLMEDİ:
        hedef aşırı-basınçlar (100/35/7/2 kPa) aynen korundu, değişen tek
        şey o hedeflere KARŞILIK GELEN mesafenin nereden geldiğidir.

        Yayımlanan kayıt artık dayanağını da taşır (``basis``,
        ``scaled_distance_m_per_kg13``): mesafeyi okuyan kullanıcı hangi
        modelden geldiğini ve hangi Z'ye denk düştüğünü görebilir.
        """
        w13 = float(tnt_equivalent) ** (1.0 / 3.0) if tnt_equivalent > 0 else 0.0

        distances = {}
        for level, target_kpa in BLAST_OVERPRESSURE_TARGETS_KPA.items():
            z = scaled_distance_for_overpressure(target_kpa)
            distances[level] = {
                'distance_m': z * w13,
                'overpressure_kpa': target_kpa,
                'scaled_distance_m_per_kg13': z,
                'basis': BLAST_MODEL_BASIS,
            }

        return distances
    
    def _resolvable_propellant_classes(self):
        """Bir isteğin ÇÖZÜLEBİLECEĞİ bütün sınıflar (sıralı liste).

        P16B3-24 (ÖH D30) — ÖLÇÜLEN KUSUR (taban ``ab7cf68b``, kanıt
        ``docs/scofield/raw/OH/D30/yapisal-sistem/a1/once.json`` K4):
        ``/analyze_safety`` künyesi ``propellant_class`` ile birlikte
        ``known_propellant_classes`` yayımlıyor, ama D29'un P16B3-24
        onarımı (OH-D28-08, ``4b689a56``) hibrit sınıflarını TÜRETİLMİŞ
        olarak eklediği için çözülen sınıf o listede YOK. Ölçüldü (10
        istek, 50 kg, ``motor_type='hybrid'``): **9/10** istekte
        yayımlanan ``propellant_class`` (``'hybrid_n2o'``) yanıtın
        yayımladığı HİÇBİR sınıf listesinde geçmiyordu — künye kendini
        yalanlıyordu ve üyelik sınayan bir tüketici her hibrit istekte
        düşüyordu.

        ``KNOWN_PROPELLANT_CLASSES`` panelin SEÇTİRDİĞİ kümedir ve öyle
        KALIR (kendi künyesi bunu söylüyor). Bu liste ise motor tipinden
        ya da addan ÇÖZÜLEBİLEN kümedir; tek kaynağı
        ``self.propellant_tnt_equivalents`` anahtarlarıdır, yani yeni bir
        sınıf tablodan gelir, burada İKİNCİ KEZ YAZILMAZ (doktrin 4).
        """
        return sorted(self.propellant_tnt_equivalents)

    def _explosive_not_modelled(self, propellant_type,
                                motor_type) -> Optional[Dict]:
        """Patlayıcı ekseninin 'modellenmedi' kaydı (TEK işlev).

        İki kaynak: (1) ``propellant_type='not_modelled'`` beyanı (panel,
        5. tur); (2) 6. tur — KATI motorda, TNT tablosunda olmayan ad için
        merkezi katalog ailesi bir sınıf değilse ya da ad katalogda
        çözülmezse (``solid_catalog_not_modelled``; panelin katı kuralı).
        Sınıf çözümü, Gurney geri çekmesi, tahliye ve toksik yedek bu
        kaydı okur.
        """
        beyan = explosive_not_modelled(propellant_type, motor_type)
        if beyan is not None:
            return beyan
        if str(motor_type or '').strip().lower() != 'solid':
            return None
        if str(propellant_type or '').strip().lower() in \
                self.propellant_tnt_equivalents:
            return None
        return solid_catalog_not_modelled(propellant_type)

    def _motor_type_fallback_class(self, propellant_type, mt) -> str:
        """TNT tablosunda olmayan adın motor tipinden sınıfı (tek kaynak).

        Katıda sınıf katalog ailesidir (``solid_catalog_explosive_class``;
        çağıran 'modellenmedi' kolunu önce ``_explosive_not_modelled`` ile
        ayırmıştır), diğer tiplerde ``MOTOR_TYPE_TO_EXPLOSIVE_CLASS``.
        """
        if mt == 'solid':
            return solid_catalog_explosive_class(propellant_type)[0]
        return MOTOR_TYPE_TO_EXPLOSIVE_CLASS[mt]

    def _resolve_explosive_class(self, propellant_type: str,
                                 motor_type: Optional[str]) -> Tuple[str, str]:
        """(TNT eşdeğeri sınıfı, dayanak metni).

        propellant_type tablo anahtarlarından biriyse doğrudan kullanılır.
        Değilse (ör. 'apcp', 'n2o_htpb' gibi serbest ad) motor tipi sınıfı
        belirler — bu, motor_type girdisinin GERÇEK kullanım yeridir.
        """
        key = str(propellant_type or '').strip().lower()
        mt = str(motor_type or '').strip().lower()

        # ÖH D37 A1b panel-js 5. tur — 'MODELLENMEDİ' BEYANI her koldan
        # ÖNCE gelir: oksitleyici adı ya da motor tipi yedeği bu beyanı
        # bir sınıfa ÇEVİREMEZ (sınıf kazanılmadı; gerekçe adıyla).
        # 6. tur: katı motorda katalog ailesinden türeyen geri çekme de
        # aynı kapıdan geçer (``_explosive_not_modelled``; tek işlev).
        beyan = self._explosive_not_modelled(propellant_type, motor_type)
        if beyan is not None:
            return None, beyan['reason']

        # OH-D29-01 — HİBRİTTE SINIFI OKSİTLEYİCİ BELİRLER. ÖLÇÜLDÜ
        # (``D30/app-api-uc/a1/once.json`` K4, taban ``ab7cf68b``):
        # ``motor_type='hybrid'`` + ``oxidizer_type='h2o2'`` isteği sınıf
        # ``composite`` / TNT 2,100 kg alıyordu, çünkü ``propellant_type``in
        # ürün varsayılanı (``'composite'``) tabloyla EŞLEŞİP kolu bitiriyordu;
        # aynı motor peroksidi ``propellant_type='h2o2_htpb'`` diye yazınca
        # ``hybrid_h2o2`` / TNT 3,446 kg alıyordu (%64 fark). Alan ADIYLA
        # geldiyse serbest metin tablosundan ÖNCE gelir. (6. tur: ADIYLA
        # verilip çözülmeyen ad varsayılan kola düşmez — aşağıda; beyanlı
        # varsayılan kol yalnız alan HİÇ verilmediğinde çalışır.)
        if mt == 'hybrid' and str(self._requested_oxidizer or '').strip():
            # ÖH D37 A1b panel-js 6. tur (OH-AS-03 PDF ayağı, N3): ADIYLA
            # verilmiş ama türetimi olan hiçbir oksitleyiciye çözülmeyen ad
            # ürünün varsayılan oksitleyicisine ÇEVRİLMEZ (uç bu adı zaten
            # 400 ile reddediyor; belge yolu kapısız modülden geçer).
            if hybrid_oxidizer_from_text(self._requested_oxidizer) is None:
                return None, (
                    f"oxidizer_type {str(self._requested_oxidizer)[:60]!r} "
                    "names no hybrid oxidiser with a derived TNT "
                    "equivalence (derived: "
                    + ', '.join(sorted(
                        HYBRID_OXIDIZER_DECOMPOSITION_KCAL_PER_MOL))
                    + "), so no TNT-equivalent class was won. The product "
                    "default oxidiser is NOT substituted for a named "
                    "oxidiser HRMA cannot identify.")
            return self._resolve_hybrid_explosive_class(
                self._requested_oxidizer, alan_adi='oxidizer_type')

        if key in self.propellant_tnt_equivalents:
            return key, f"propellant_type '{key}' matched the TNT-equivalent table"

        if mt == 'hybrid':
            return self._resolve_hybrid_explosive_class(propellant_type)
        if mt in MOTOR_TYPE_TO_EXPLOSIVE_CLASS:
            resolved = self._motor_type_fallback_class(propellant_type, mt)
            return resolved, (
                f"propellant_type '{propellant_type}' is not a tabulated class; "
                f"motor_type '{mt}' selected the '{resolved}' class")

        # --- ÖH D35 / OH-ON-06 · SINIF KAZANILMADIYSA YAYIMLANMAZ --------
        # ÖLÇÜLEN KUSUR (``D35/onemli-pdf-guvenlik/a1/once.json`` K1, taban
        # ``32e98e9a``): GERÇEK bir N2O/HTPB hibrit koşumunun PDF'i
        # (``/calculate`` -> ``exportReport``) patlayıcı sınıfı
        # ``composite``, TNT çarpanı 0,42 ve **5,7106 kg TNT** basıyordu.
        # Belgenin KENDİ yapılandırma tablosu aynı sayfada "Motor Type:
        # not supplied in the analysis payload" diyordu; yani ürün motor
        # tipini bilmediğini İTİRAF ederken güvenlik bölümü bir KATI
        # kompozit hükmü yayımlıyordu (HD 1.1 + 'Class 1.3-type solid
        # propellant fire'). Sayı buraya ``propellant_type``ın uç/çözümleyici
        # varsayılanı olan ``'composite'``ten geliyordu ve dayanak metni
        # "matched the TNT-equivalent table" diyerek kullanıcının HİÇ
        # vermediği bir değeri eşleşmiş gibi gösteriyordu.
        #
        # Doktrin 1 (fail-closed): kimlik kazanılmadıysa sınıf da
        # kazanılmamıştır. ``None`` döner; çağıran TNT eşdeğerini, patlama
        # mesafelerini ve QD şartlarını YAYIMLAMAZ ve nedeni ADIYLA yazar.
        # 'Muhafazakâr varsayım' savunulamaz: ölçüldü, ``composite`` (0,42)
        # bu motorun kazandığı ``hybrid_n2o`` sınıfından (0,44555) DAHA
        # DÜŞÜK bir eşdeğer verir, yani yayımlanan emniyet mesafesi KISA
        # taraftadır (D26/P5B2-05 ile aynı yanlış yön).
        return None, (
            f"propellant_type '{propellant_type}' is not a tabulated class "
            f"and no motor_type was supplied, so no TNT-equivalent class was "
            f"won. Tabulated classes: "
            f"{', '.join(sorted(self.propellant_tnt_equivalents))}. Supply "
            f"motor_type ('solid' | 'hybrid' | 'liquid') or a tabulated "
            f"propellant_type to have the explosive verdict computed.")

    def _resolve_hybrid_explosive_class(
            self, propellant_type, alan_adi: str = 'propellant_type'
    ) -> Tuple[str, str]:
        """Hibrit motorun (sınıf, dayanak) ikilisi — OH-D28-08.

        Hibritte yakıt grain'i (HTPB, parafin, PE, PMMA, ABS) oksitleyici
        içermeyen atıl bir polimerdir; TNT eşdeğerini OKSİTLEYİCİ belirler.
        Bu yüzden burada aranan şey yakıt adı DEĞİL, oksitleyici adıdır.
        Sayı modül başındaki türetimden gelir (Karabeyoglu vd. 2008), bu
        gövdede hiçbir katsayı yazılı değildir.
        """
        ham = '' if propellant_type is None else str(propellant_type)
        anahtar = ham.strip().lower()
        parcalar = [p for p in re.split(r'[^a-z0-9]+', anahtar) if p]

        # Oksitleyici İSTEK METNİNDE adıyla geçiyor mu? (tam sözcük)
        # OH-D33-30: aynı soruyu uç katmanı da soruyor, bu yüzden kural
        # modül düzeyindeki ``hybrid_oxidizer_from_text``e taşındı — iki
        # kopya olmasın (doktrin 4). Davranış bit-aynı.
        adli_ox = hybrid_oxidizer_from_text(ham)

        yakit_adli = [p for p in parcalar if p in HYBRID_INERT_FUEL_NAMES]
        grain_notu = (
            ("the fuel grain named (%s) is an inert polymer and contributes "
             "no TNT equivalence" % ', '.join(f"'{f}'" for f in yakit_adli))
            if yakit_adli else
            "the hybrid fuel grain carries no oxidiser and contributes no "
            "TNT equivalence")

        if adli_ox is not None and ('hybrid_%s' % adli_ox) in \
                self.propellant_tnt_equivalents:
            sinif = 'hybrid_%s' % adli_ox
            return sinif, (
                f"{alan_adi} '{ham}' is not a tabulated class; the "
                f"hybrid oxidiser '{adli_ox}' was read from it and selected "
                f"the '{sinif}' class. The equivalence is derived from the "
                f"oxidiser decomposition enthalpy (Karabeyoglu, Dyer, "
                f"Stevens & Cantwell, AIAA 2008-4933, eq. 2), not from a "
                f"liquid-bipropellant table: {grain_notu}.")

        # Oksitleyici ADIYLA çözülemedi. Ürünün KENDİ varsayılan
        # oksitleyicisi kullanılır ve bu ADIYLA beyan edilir; hangi
        # alternatifin ne kadar yüksek olduğu da yazılır ki kullanıcı
        # eksik girdinin hükmü nereye taşıdığını görsün.
        sinif = 'hybrid_%s' % HYBRID_DEFAULT_OXIDIZER
        alternatifler = ', '.join(
            "%s = %.3f" % (ox, hybrid_oxidizer_tnt_equivalent(ox))
            for ox in sorted(HYBRID_OXIDIZER_DECOMPOSITION_KCAL_PER_MOL)
            if ox != HYBRID_DEFAULT_OXIDIZER)
        return sinif, (
            f"{alan_adi} '{ham}' is not a tabulated class and names no "
            f"hybrid oxidiser; motor_type 'hybrid' selected the '{sinif}' "
            f"class from the product default oxidiser "
            f"'{HYBRID_DEFAULT_OXIDIZER}'. This is an ASSUMPTION about your "
            f"motor, not something you supplied: name the oxidiser in "
            f"propellant_type (for example "
            f"'{HYBRID_DEFAULT_OXIDIZER}_htpb') to have it resolved. Other "
            f"tabulated hybrid oxidisers give a HIGHER equivalence "
            f"({alternatifler} vs "
            f"{hybrid_oxidizer_tnt_equivalent(HYBRID_DEFAULT_OXIDIZER):.3f}); "
            f"note that {grain_notu}.")

    def _estimate_case_mass(self, propellant_mass: float,
                            motor_data: Optional[Dict],
                            material: str) -> Tuple[float, str]:
        """(kasa kütlesi kg, dayanak). Geometri varsa GERÇEK kabuk kütlesi.

        m = rho * [pi*D_ort*L*t + 2*(pi/4)*D_dis^2*t]  (silindir + uç kapaklar)
        Geometri yoksa ampirik kütle kesri kullanılır ve bu beyan edilir.
        """
        md = motor_data or {}
        diameter = md.get('chamber_diameter')
        thickness = md.get('wall_thickness')
        length = md.get('chamber_length') or md.get('motor_length')
        if diameter and thickness:
            # P5B2-03: kasa kütlesi de bilinmeyen malzemede sessizce
            # çeliğin yoğunluğunu kullanıyordu (ölçüldü: 'unobtainium'
            # -> 6,0473 kg).
            rho = float(self._resolve_chamber_material(material)[0]['density'])
            d = float(diameter)
            t = float(thickness)
            if length:
                L = float(length)
                basis = 'shell mass from chamber diameter, length and wall thickness'
            else:
                L = SAFETY_MODEL['assumed_length_to_diameter'] * d
                basis = ("shell mass from chamber diameter and wall thickness "
                         f"with an ASSUMED L/D = "
                         f"{SAFETY_MODEL['assumed_length_to_diameter']:.0f} "
                         "(chamber_length was not supplied)")
            d_outer = d + 2.0 * t
            volume = (np.pi * (d + t) * L * t
                      + 2.0 * (np.pi / 4.0) * d_outer ** 2 * t)
            return float(rho * volume), basis

        frac = SAFETY_MODEL['fallback_case_mass_fraction']
        return (float(propellant_mass) * frac,
                f"EMPIRICAL case mass fraction {frac:.2f} of propellant mass "
                f"(chamber geometry was not supplied)")

    def _calculate_fragment_hazards(self, propellant_mass: float, thrust: float,
                                    burn_time: Optional[float] = None,
                                    motor_data: Optional[Dict] = None,
                                    material: str = 'steel_4130') -> Dict:
        """Calculate fragment throw distances and hazards.

        DENETİM DÜZELTMESİ (2026-07-19): kasa kütlesi artık gerçek kabuk
        geometrisinden hesaplanır (eski sabit %15 kesri yalnız geometri
        yokken, beyan edilerek kullanılır) ve thrust/burn_time serbest kalan
        motor tehlikesinde gerçekten kullanılır.
        """

        # --- P5B2-16 (ÖH D15 / a3): SESSİZ KIRPMA KALDIRILDI -------------
        # ÖLÇÜLDÜ (``a3/once.json``): ``thrust = -4000 N`` verilen 4 kN'lık
        # bir motor için bu fonksiyon ``required_restraint_force_n = 0,0``
        # ve ``total_impulse_ns = 0,0`` yayımlıyordu — yani "bağlama
        # kuvveti gerekmiyor" diyen bir test standı hükmü, tek bir uyarı
        # olmadan. Daha kötüsü ``burn_time = -6`` vakası: impuls 0,0'a
        # kırpılırken bağlama kuvveti 16000 N kalıyordu, yani AYNI yanıtın
        # iki sayısı birbirini yalanlıyordu. ``max(x, 0)`` bir emniyet
        # önlemi değil, girdinin sessizce yok sayılmasıdır.
        _fizik_disi_degilse('propellant_mass', propellant_mass)
        _fizik_disi_degilse('thrust', thrust)
        # ÖH D36 / onemli2-sivi a2: imza varsayılanı 10,0 s idi (doğrudan
        # çağıran süre vermezse uydurulurdu). Süre verilmediyse None kalır ve
        # serbest kalan motorun süreye bağlı üç alanı aşağıda adıyla geri
        # çekilir; verildiyse kapı AYNEN uygulanır.
        if burn_time is not None:
            _fizik_disi_degilse('burn_time', burn_time)

        case_mass, case_mass_basis = self._estimate_case_mass(
            propellant_mass, motor_data, material)

        # Fragment velocity estimation (Gurney equation approximation).
        # Gurney silindir formu: V = √(2E)·√(C/(M + C/2)); C = şarj (yakıt),
        # M = kılıf (metal) kütlesi. ESKİ HATA: payda propellant + case/2
        # (C + M/2) yazılmıştı → M ve C rolleri ters. Doğru payda M + C/2.
        gurney_velocity = SAFETY_MODEL['gurney_velocity_ms']  # m/s (√(2E))
        fragment_velocity = gurney_velocity * np.sqrt(
            propellant_mass / (case_mass + propellant_mass / 2)) \
            if (case_mass + propellant_mass / 2) > 0 else 0.0

        # Fragment range. Vakum/45° menzili (v²/g) aerodinamik sürüklemeyi
        # ihmal eder ve ~2600 m/s parça için ~700 km gibi FİZİKSEL OLMAYAN
        # değer verir. Gerçek roket parçaları sürükleme-sınırlıdır; pratik
        # üst sınırla kırpılır (tahliye mesafesi hesabına saçma değer gitmesin).
        g0 = SAFETY_MODEL['gravity_m_s2']
        vacuum_range = fragment_velocity ** 2 / g0
        max_range = min(vacuum_range, SAFETY_MODEL['fragment_drag_limited_range_m'])

        # Lethal fragment analysis
        lethal_fragment_mass = SAFETY_MODEL['lethal_fragment_mass_kg']
        lethal_kinetic_energy = SAFETY_MODEL['lethal_kinetic_energy_j']
        lethal_velocity = np.sqrt(2 * lethal_kinetic_energy / lethal_fragment_mass)

        # --- Serbest kalan motor tehlikesi: thrust ve burn_time BURADA gerçekten
        # kullanılıyor. Test standından kopan motor bir mermi gibi davranır;
        # toplam impuls onu hızlandırır (Sutton & Biblarz Böl. 2 impuls-momentum).
        # P5B2-16: kırpma yok — girdi kapıdan geçtiyse zaten pozitiftir.
        # ÖH D36 / onemli2-sivi a2: süre yoksa impuls (ve ondan türeyen hız
        # ile enerji) HESAPLANMAZ; ortalama kütle ve bağlama kuvveti süreye
        # bağlı değildir, kalır.
        total_impulse = (None if burn_time is None
                         else float(thrust) * float(burn_time))
        # Ortalama uçuş kütlesi: kasa + yakıtın yarısı (yanma boyunca ortalama)
        mean_mass = max(case_mass + propellant_mass / 2.0, 1e-6)
        loose_velocity = (None if total_impulse is None
                          else total_impulse / mean_mass)             # m/s
        loose_energy = (None if loose_velocity is None
                        else 0.5 * mean_mass * loose_velocity ** 2)   # J
        # Bağlama elemanlarının karşılaması gereken kuvvet (yapısal emniyet
        # katsayısıyla) — itkinin doğrudan emniyet karşılığı.
        restraint_force = (float(thrust)
                           * self.safety_margins.structural_safety_factor)

        serbest_motor = {
            'total_impulse_ns': total_impulse,
            'mean_flight_mass_kg': mean_mass,
            'burnout_velocity_ms': loose_velocity,
            'kinetic_energy_j': loose_energy,
            'required_restraint_force_n': restraint_force,
            'note': ('If the motor breaks free of its restraint it becomes '
                     'a projectile: burnout speed is total impulse divided '
                     'by mean flight mass. The tie-down must react the '
                     'thrust with the structural safety factor. No '
                     'trajectory range is quoted because it depends on '
                     'drag and attitude, which this model does not solve.'),
        }
        if burn_time is None:
            # Adıyla geri çekme — anahtarlar SİLİNMEZ (tüketiciler anahtar
            # arar), değer None + durum + gerekçe + hangi alanlar.
            serbest_motor.update({
                'status': BURN_TIME_NOT_EVALUATED,
                'reason': BURN_TIME_NOT_SUPPLIED_REASON,
                'not_evaluated': list(UNRESTRAINED_BURN_TIME_FIELDS),
            })

        return {
            'estimated_case_mass_kg': case_mass,
            'case_mass_basis': case_mass_basis,
            'unrestrained_motor': serbest_motor,
            'fragment_velocity_ms': fragment_velocity,
            'maximum_range_m': max_range,
            'lethal_fragment_range_m': max_range * 0.8,  # Conservative estimate
            # ÖH D23 / P5B2-21 — ADI BİRİMİNİ SÖYLÜYOR.
            # ``case_mass / (pi * R^2)`` bir KÜTLE yüzey yoğunluğudur
            # [kg/m^2]; eski ad (``fragment_density_per_m2``) parça SAYISI
            # yoğunluğu ima ediyordu ve panel bunu ``1/m²`` diye
            # etiketliyordu. ÖLÇÜLDÜ (taban ef527ae, ``once.json``
            # P5B2-21_24): 3000 kg kasa -> 2,38732414637843e-04 — sayı
            # olarak "m² başına 0,0002 parça" okunuyordu, oysa değer
            # kg/m². Parça SAYISI bu modülde hesaplanmıyor (parçalanma
            # spektrumu modellenmiyor), o yüzden sayı yoğunluğu
            # YAYIMLANMAZ; yayımlanan büyüklük adıyla ve birimiyle
            # anılır.
            'fragment_areal_mass_density_kg_m2': (
                case_mass / (np.pi * max_range ** 2)),
            'fragment_areal_mass_density_basis': (
                'case mass spread uniformly over the disc of radius '
                'maximum_range_m: sigma = m_case / (pi * R^2) [kg/m^2]. '
                'This is an AREAL MASS density, NOT a fragment COUNT '
                'density: this module does not model the fragmentation '
                'spectrum, so it cannot say how many pieces land per '
                'square metre.'),
            'lethal_velocity_threshold_ms': lethal_velocity,
            # ÖH D23 / P5B2-24 — UYDURMA DAĞILIM GERİ ÇEKİLDİ.
            # ÖLÇÜLDÜ (taban ef527ae, ``once.json`` P5B2-21_24): kasa
            # kütlesi 0,75 kg -> 3000 kg (4000 kat) ve parça hızı
            # değişirken ``fragment_size_distribution`` BİREBİR aynı
            # kalıyordu ({0.1-1, 1-10, 10-100} g), kaynak beyanı da
            # yoktu. Motordan bağımsız bir sabit, o motorun analiz
            # sonucuymuş gibi yayımlanıyordu (doktrin 6: sahte veri).
            # Gerçek parça kütle dağılımı Mott/Gurney tipi bir
            # parçalanma modeli ister (kasa kalınlığı, malzeme süneklik
            # dağılımı, patlayıcı yükleme oranı); bu modülde YOKTUR.
            # FAIL-CLOSED: hüküm kazanılmadığı için sayı yayımlanmaz,
            # yerine geri çekme gerekçesi konur.
            'fragment_size_distribution': None,
            'fragment_size_distribution_withheld': (
                'not computed: a fragment mass distribution requires a '
                'fragmentation model (Mott/Gurney: case thickness, '
                'material ductility, explosive loading ratio), which '
                'this module does not solve. The previously published '
                '0.1-1 / 1-10 / 10-100 g bins were a fixed constant '
                'identical for every motor, so they were withdrawn '
                'rather than presented as an analysis result.'),
        }
    
    def _calculate_qd_requirements(self, tnt_equivalent: float) -> Dict:
        """Calculate quantity-distance requirements for different exposed sites"""
        
        # NATO STANAG 4123 / DOD 6055.9-STD ilişkileri, R = K·W^(1/3).
        # DDESB/UFC 3-340-02 K-faktörleri klasik olarak ft/lb^(1/3)
        # birimindedir; bu modül W'yi kg, R'yi m ile kullandığından metrik
        # eşdeğere çevrildi (çarpan 0.3048/0.4536^(1/3) = 0.3966 m·lb^(1/3)/
        # (ft·kg^(1/3))). ESKİ HATA: imperial 40/18/... değerleri doğrudan
        # metrik girdiye uygulanıp mesafeler ~2.5x abartılıyordu.
        # Örn. IBD: 40 ft/lb^(1/3) → 15.9 m/kg^(1/3).
        _IMP_TO_METRIC = 0.3966
        k_factors = {
            'inhabited_building':   40 * _IMP_TO_METRIC,   # ≈15.9 (IBD)
            'public_traffic_route': 18 * _IMP_TO_METRIC,   # ≈7.14 (PTRD)
            'explosives_facility':  12 * _IMP_TO_METRIC,   # ≈4.76
            'personnel_facility':   22 * _IMP_TO_METRIC,   # ≈8.73
            'ammunition_storage':   12 * _IMP_TO_METRIC,   # ≈4.76
        }
        
        qd_distances = {}
        for site_type, k_factor in k_factors.items():
            # Distance = K * W^(1/3), minimum 30m
            distance = max(30, k_factor * (tnt_equivalent ** (1/3)))
            qd_distances[site_type] = {
                'distance_m': distance,
                'k_factor': k_factor
            }
        
        return qd_distances
    
    def _generate_operational_safety_procedures(self, motor_data: Dict, 
                                              propellant_type: str, facility_type: str) -> Dict:
        """Generate operational safety procedures"""
        
        procedures = {
            'pre_operation_checks': [
                'Verify all safety systems functional',
                'Confirm personnel evacuation complete',
                'Check weather conditions acceptable',
                'Verify emergency response teams ready',
                'Test communication systems',
                'Confirm fire suppression systems armed'
            ],
            'operation_procedures': [
                'Maintain minimum safe distance',
                'Monitor pressure and temperature continuously',
                'Have abort procedures ready',
                'Maintain constant communication',
                'Document all anomalies immediately'
            ],
            'post_operation_procedures': [
                'Allow minimum cooling time before approach',
                'Check for unexploded ordnance',
                'Document all observations',
                'Secure facility and equipment',
                'Conduct post-test inspection'
            ],
            'personnel_limits': self._determine_personnel_limits(motor_data, facility_type),
            'qualification_requirements': self._determine_qualification_requirements(facility_type),
            'training_requirements': self._determine_training_requirements(propellant_type, facility_type)
        }
        
        return procedures
    
    def _generate_emergency_procedures(self, explosive_hazards: Dict, 
                                     toxic_hazards: Dict, fire_hazards: Dict) -> Dict:
        """Generate comprehensive emergency response procedures"""

        # ÖH D37 A1b panel-js 5. tur: patlayıcı modeli olmayan itici için
        # tahliye mesafesi KAZANILMAMIŞTIR (iki girdisi de — patlama
        # mesafesi ve Gurney parça menzili — geri çekildi). Eski ifade
        # ``max(.., 100)`` iki girdi de yokken 100 m'lik UYDURMA bir mesafe
        # basardı; beyanlı kolda değer None + durum + gerekçe yayımlanır.
        beyan = explosive_hazards.get('explosive_not_modelled')
        if beyan:
            patlama_tahliyesi = None
        else:
            patlama_tahliyesi = max(
                explosive_hazards.get('blast_distances', {}).get('serious_injury', {}).get('distance_m', 100),
                explosive_hazards.get('fragment_hazards', {}).get('lethal_fragment_range_m', 100)
            )

        prosedurler = {
            'explosion_response': {
                'immediate_actions': [
                    'Sound evacuation alarm immediately',
                    'Evacuate to minimum safe distance',
                    'Account for all personnel',
                    'Contact emergency services',
                    'Establish incident command post'
                ],
                'evacuation_distance': patlama_tahliyesi,
                're-entry_criteria': [
                    'Minimum 2-hour cooling period',
                    'EOD clearance if required',
                    'Structural damage assessment',
                    'Environmental monitoring complete'
                ]
            },
            'fire_response': {
                'immediate_actions': [
                    'Activate fire suppression system',
                    'Sound fire alarm',
                    'Evacuate upwind',
                    'Call fire department',
                    'Prepare for secondary explosions'
                ],
                'suppression_method': fire_hazards.get('suppression_system', {}).get('primary_agent', 'Water/Foam'),
                'evacuation_distance': fire_hazards.get('fire_safety_distances', {}).get('radiant_heat_m', 50)
            },
            'toxic_release_response': {
                'immediate_actions': [
                    'Don appropriate PPE',
                    'Evacuate downwind areas',
                    'Activate gas detection systems',
                    'Contact HAZMAT team',
                    'Establish decontamination procedures'
                ],
                'evacuation_distance': max([
                    scenario.get('hazard_distance_m', 50) 
                    for scenario in toxic_hazards.get('release_scenarios', [])
                ] + [50]),  # Default 50m minimum
                'decontamination': toxic_hazards.get('emergency_treatment', {})
            },
            'medical_response': {
                'on_site_capabilities': 'Basic first aid, oxygen, decontamination',
                'hospital_notification': 'Notify trauma center of potential casualties',
                'antidotes_required': self._determine_required_antidotes(toxic_hazards),
                'treatment_protocols': self._generate_treatment_protocols(toxic_hazards),
                # SAFE-TEXT-3 (2026-07-28): buradaki antidot/tedavi satırları
                # (piridoksin protokolü, 24-48 saat gözlem, dekontaminasyon)
                # genel acil-durum planlama kontrol listesidir; bu yazılım
                # hekim değildir ve metinlerin tıbbi atfı yoktur. İçerik
                # korunur, çerçevesi açıkça beyan edilir.
                'basis': ('general emergency-planning checklist - NOT '
                          'medical advice; every item must be confirmed '
                          'against the propellant SDS and with the '
                          'responsible occupational physician before it is '
                          'relied upon'),
                'disclaimer_code': 'warn.safety.medical_guidance_requires_physician',
            }
        }
        if beyan:
            yanit = prosedurler['explosion_response']
            yanit['evacuation_distance_status'] = beyan['status']
            yanit['evacuation_distance_reason'] = beyan['reason']
        return prosedurler
    
    def _calculate_overall_risk(self, structural_safety: Dict, pressure_safety: Dict,
                               thermal_safety: Dict, explosive_hazards: Dict,
                               toxic_hazards: Dict, fire_hazards: Dict) -> Dict:
        """Calculate overall risk assessment matrix"""
        
        # Risk scoring (1-5 scale)
        structural_risk = self._score_structural_risk(structural_safety)
        pressure_risk = self._score_pressure_risk(pressure_safety)
        thermal_risk = self._score_thermal_risk(thermal_safety)
        explosive_risk = self._score_explosive_risk(explosive_hazards)
        toxic_risk = self._score_toxic_risk(toxic_hazards)
        fire_risk = self._score_fire_risk(fire_hazards)
        
        # Genel risk = EN KÖTÜ EKSEN (max).
        # DENETİM DÜZELTMESİ (2026-07-28, SAFE-PROB-2): eski kod kaynaksız
        # 0.25/0.20/0.15/0.20/0.10/0.10 ağırlıklarıyla ortalama alıyordu.
        # Ağırlıkların hiçbir atfı/kalibrasyonu yoktu ve ortalama, KRİTİK
        # tek bir ekseni sulandırıyordu: yapısal risk 5.0 iken diğerleri
        # düşükse genel skor ~2 çıkıp motor 'LOW/ACCEPTABLE' damgalanıyordu.
        # Emniyet pratiğinde kabul edilebilirliği azaltılmamış EN KÖTÜ
        # tehlike yönetir; max birleşimi uydurma sayı içermez ve mevcut
        # sınıflandırma eşikleriyle (<=2 LOW ... >4 CRITICAL) uyumludur.
        #
        # ÖH Z3 / OH-B2-03: bir eksen DEĞERLENDİRİLEMEMİŞ olabilir (skor
        # ``None``). Böyle bir eksen maksimuma girmez — ama sessizce de
        # düşmez: adı ``risks_not_evaluated`` alanında yazılır, genel skor
        # KISMİ olarak imlenir ve kazanılmamış ONAY geri çekilir.
        eksenler = {
            'structural': structural_risk, 'pressure': pressure_risk,
            'thermal': thermal_risk, 'explosive': explosive_risk,
            'toxic': toxic_risk, 'fire': fire_risk,
        }
        degerlendirilmeyen = [ad for ad, skor in eksenler.items()
                              if skor is None]
        olculen = [skor for skor in eksenler.values() if skor is not None]
        overall_risk_score = max(olculen) if olculen else None

        # Risk level classification
        if overall_risk_score is None:
            risk_level = THERMAL_VERDICT_NOT_EVALUATED
            acceptability = THERMAL_VERDICT_NOT_EVALUATED
        elif overall_risk_score <= SAFETY_MODEL['risk_score_low_max']:
            risk_level = 'LOW'
            acceptability = 'ACCEPTABLE'
        elif overall_risk_score <= SAFETY_MODEL['risk_score_medium_max']:
            risk_level = 'MEDIUM'
            acceptability = 'ACCEPTABLE_WITH_CONTROLS'
        elif overall_risk_score <= SAFETY_MODEL['risk_score_high_max']:
            risk_level = 'HIGH'
            acceptability = 'REQUIRES_MITIGATION'
        else:
            risk_level = 'CRITICAL'
            acceptability = 'UNACCEPTABLE'

        sonuc = {
            'individual_risks': eksenler,
            'risks_not_evaluated': degerlendirilmeyen,
            'overall_risk_score': overall_risk_score,
            'overall_risk_score_is_partial': bool(degerlendirilmeyen),
            'risk_level': risk_level,
            'acceptability': acceptability,
            'aggregation_basis': ('worst-axis (max of individual risk '
                                  'scores) - uncalibrated weighted '
                                  'averaging removed 2026-07-28; axes that '
                                  'could not be evaluated are excluded from '
                                  'the maximum and listed in '
                                  'risks_not_evaluated'),
            'risk_matrix': self._generate_risk_matrix(),
            'mitigation_priority': self._determine_mitigation_priority(
                **eksenler),
            'mitigation_priority_not_evaluated': degerlendirilmeyen,
        }

        if degerlendirilmeyen:
            # ONAY geri çekilir, UYARI çekilmez (kardeş kural:
            # app.py::_withhold_unearned_structural_verdict). Eksik bir eksen
            # varken 'ACCEPTABLE' bir kazanılmamış onaydır; 'REQUIRES_
            # MITIGATION' / 'UNACCEPTABLE' ise gerçek bir uyarıdır ve
            # susturulmaz.
            sonuc['risk_level_is_partial'] = True
            sonuc['partial_assessment_basis'] = (
                'The overall score is the worst of the axes that COULD be '
                'evaluated; '
                + ', '.join(degerlendirilmeyen)
                + ' did not run, so the true worst axis may be higher. A '
                  'missing evaluation is not a low risk.')
            if acceptability in ('ACCEPTABLE', 'ACCEPTABLE_WITH_CONTROLS'):
                sonuc['acceptability'] = THERMAL_VERDICT_NOT_EVALUATED
                sonuc['acceptability_withheld_because'] = (
                    sonuc['partial_assessment_basis'])
        return sonuc
    
    # Helper methods for risk scoring
    def _score_structural_risk(self, structural_safety: Dict) -> float:
        # P5B2-13: YÖNETEN katsayı — birleşik (basınç + termal) katsayı
        # hesaplanabildiyse odur, yoksa basınç-tek katsayısı. Eksen artık
        # 4045 MPa'lık bir termal gerilmeyi görmezden gelmiyor.
        safety_factor = structural_safety.get('governing_safety_factor')
        if not isinstance(safety_factor, (int, float)) or isinstance(
                safety_factor, bool):
            safety_factor = structural_safety.get('yield_safety_factor', 1.0)
        if safety_factor >= SAFETY_MODEL['sf_band_safe']:
            return 1.0
        elif safety_factor >= SAFETY_MODEL['sf_band_intermediate']:
            return 2.0
        elif safety_factor >= SAFETY_MODEL['sf_band_marginal']:
            return 3.0
        elif safety_factor >= SAFETY_MODEL['sf_band_critical']:
            return 4.0
        else:
            return 5.0
    
    def _score_pressure_risk(self, pressure_safety: Dict) -> Optional[float]:
        """Basınç riski: sınıf tabanı + GERÇEK kopma marjı.

        Eskiden yalnız basınç sınıfına bakıyordu; kasa duvarı ince veya
        malzeme zayıf olsa bile skor değişmiyordu. Artık gerçek kopma
        marjı (actual_burst / required_burst) skoru yönetir.

        **P5B2-11 (ÖH D15 / a3) — FAIL-OPEN KAPATILDI.** ÖLÇÜLDÜ
        (``a3/once.json``): kopma basıncı HESAPLANAMADIĞINDA
        (``burst_margin is None``) eksen sınıf TABANINA düşüyordu —
        ``MEDIUM_PRESSURE`` için **2,0**. Aynı sınıfta marjı GERÇEKTEN
        ölçülmüş ince bir kasa (marj 1,5) **3,0** alıyordu. Yani
        "değerlendirilemedi", bilinen-kötüden DAHA GÜVENLİ görünüyordu ve
        bu 2,0 doğrudan ``ACCEPTABLE`` hükmüne gidiyordu.

        Kardeş eksenlerin (``_score_thermal_risk``, ``_score_toxic_risk``)
        zaten uyguladığı sözleşme burada da geçerlidir: ölçülemeyen eksen
        ``None`` döner, ``_calculate_overall_risk`` onu maksimuma SOKMAZ,
        ``risks_not_evaluated`` listesine adıyla yazar, genel skoru KISMİ
        imler ve kazanılmamış ``ACCEPTABLE`` onayını geri çeker. Eksik bir
        hesap düşük risk DEĞİLDİR.
        """
        vessel_class = pressure_safety.get('vessel_classification', 'MEDIUM_PRESSURE')
        if vessel_class == 'LOW_PRESSURE':
            base = 1.0
        elif vessel_class == 'MEDIUM_PRESSURE':
            base = 2.0
        else:
            base = 3.0

        margin = pressure_safety.get('burst_margin')
        if margin is None:
            return None
        if margin < 1.0:
            return 5.0
        if margin < SAFETY_MODEL['burst_margin_critical']:
            return max(base, 4.0)
        if margin < SAFETY_MODEL['burst_margin_adequate']:
            return max(base, 3.0)
        return base
    
    def _score_thermal_risk(self, thermal_safety: Dict) -> Optional[float]:
        """Termal risk ekseni — GERÇEK cidar/malzeme kıyasından.

        ÖH Z3 / OH-B2-03 (yüksek) — ÖLÇÜLDÜ (2026-08-27, HEAD b54a66b,
        ``/analyze_safety``): eksen ``chamber_temperature`` 3000 K → 1e6 K
        değişiminde **2,0'da sabit** kalıyordu. Sebep iki katmanlıydı:
        (a) skor yalnız iki BAYRAKTAN türüyordu ve (b) o uçta ısı zinciri hiç
        koşmadığı için iki bayrak da ``False`` doğuyordu — yani "değerlendirme
        yapılmadı" hâli ekranda "düşük risk" diye görünüyordu.

        Merdiven artık modülün KENDİ yayımladığı sayılara bağlı ve yeni bir
        fiziksel eşik İÇERMEZ; ikisi de materials_db'nin kendi sınırlarıdır:

        ==========================================  =====
        koşul                                       skor
        ==========================================  =====
        cidar erime noktasında ya da üstünde         5,0
        cidar servis sınırının üstünde (SF < 1)      4,0
        SF < ``temperature_safety_factor`` (1,3)     4,0  (eski cooling_required)
        radyan tehlike asgari mesafeyi aşıyor        3,0  (eski TPS dalı)
        yukarıdakilerin hiçbiri                      2,0
        ==========================================  =====

        Cidar sıcaklığı hesaplanmadıysa ``None`` döner: değerlendirilmeyen bir
        eksen "düşük risk" DEĞİLDİR ve sahte bir 2,0 basılmaz (kardeş kural:
        ``app.py::_withhold_unevaluated_thermal_verdict`` — "A missing
        computation is not a low risk").
        """
        if thermal_safety.get('thermal_verdict') == THERMAL_VERDICT_WITHHELD:
            return None

        wall_hot = thermal_safety.get('estimated_wall_temperature_k')
        if not isinstance(wall_hot, (int, float)) or isinstance(wall_hot, bool):
            return None

        melting_point = thermal_safety.get('material_melting_point_k')
        if (isinstance(melting_point, (int, float))
                and np.isfinite(melting_point) and wall_hot >= melting_point):
            # Cidar erime noktasında: bu bir bozulma değil, kaybolmadır.
            return 5.0

        # --- P5B2-13 (ÖH D15 / a3): TERMAL GERİLME EKSENE GİRER ----------
        # Cidar erimiyor ve servis sınırını da aşmıyor olabilir; ama termal
        # gradyanın kendisi bölümü AKITIYORSA (SF < 1) bu, basınç yükü hiç
        # uygulanmadan gerçekleşen bir yetmezliktir. Eşik 1,0'dır ve
        # icat edilmemiştir: akma tanımının kendisidir.
        stress_sf = thermal_safety.get('thermal_stress_safety_factor')
        if (isinstance(stress_sf, (int, float))
                and not isinstance(stress_sf, bool)
                and np.isfinite(stress_sf) and stress_sf < 1.0):
            return 5.0

        selected_sf = thermal_safety.get('material_thermal_safety_factor')
        if isinstance(selected_sf, (int, float)) and np.isfinite(selected_sf):
            if selected_sf < 1.0:
                # Servis sınırının ÜSTÜ: dayanım beyanları geçersiz.
                return 4.0
            if selected_sf < self.safety_margins.temperature_safety_factor:
                return 4.0
        elif thermal_safety.get('cooling_required'):
            return 4.0

        if thermal_safety.get('thermal_protection_required'):
            return 3.0
        # ÖH D36 / onemli2-sivi a2: 3,0 ile 2,0 arasındaki karar yanma
        # süresine bağlı doz mesafesindedir. Süre verilmediyse ve ışınım
        # kolu uyarıyı kazanmadıysa bu alan ADIYLA geri çekilmiştir; en düşük
        # basamak (2,0) kazanılmamış bir onay olurdu -> eksen skorlanmaz
        # (``risks_not_evaluated``, kardeş kural). Süre verildiğinde alan
        # daima bool'dur ve bu dal hiç çalışmaz (skor bit-aynı).
        if 'thermal_protection_required' in (
                thermal_safety.get('burn_time_not_evaluated') or ()):
            return None
        return 2.0

    def _score_explosive_risk(self, explosive_hazards: Dict) -> Optional[float]:
        # ÖH D35 / OH-ON-06: patlayıcı sınıfı kazanılmadıysa TNT eşdeğeri
        # YOKTUR. Eski ``.get(..., 0)`` yedeği eksik ölçüyü 0 kg sayıp
        # eksene 2,0 (en düşük) risk yazıyordu — yani ölçülemeyen bir
        # tehlike 'düşük' diye puanlanıyordu. ``None`` deponun kendi
        # kanalıdır (``_calculate_overall_risk`` -> ``risks_not_evaluated``):
        # eksen maksimuma girmez, adıyla geri çekilir ve genel hüküm
        # KISMİ imlenir. Kardeş desen: ``_score_toxic_risk``.
        if explosive_hazards.get('explosive_verdict_withheld_because'):
            return None
        tnt_equivalent = explosive_hazards.get('tnt_equivalent_kg')
        if tnt_equivalent is None:
            return None
        if tnt_equivalent > SAFETY_MODEL['tnt_mass_explosion_kg']:
            return 5.0
        elif tnt_equivalent > SAFETY_MODEL['tnt_major_blast_kg']:
            return 4.0
        elif tnt_equivalent > 1:
            return 3.0
        else:
            return 2.0
    
    def _score_toxic_risk(self, toxic_hazards: Dict) -> Optional[float]:
        hazard_level = toxic_hazards.get('toxic_hazard_level', 'NONE')
        # ÖH Z5S / S6 (P7B3-21): hüküm geri çekildiyse eksen SKORLANMAZ.
        # ``None`` deponun kendi kanalıdır (``_assess_overall_risk``):
        # eksen maksimuma girmez, ``risks_not_evaluated`` içinde adıyla
        # yazılır, genel skor KISMİ imlenir ve kazanılmamış ``ACCEPTABLE``
        # geri çekilir. Uydurma bir 5,0 basmak da bir hüküm olurdu.
        if hazard_level == TOXIC_LEVEL_NOT_EVALUATED:
            return None
        if hazard_level == 'NONE':
            return 1.0
        elif hazard_level == 'LOW':
            return 2.0
        elif hazard_level == 'MEDIUM':
            return 3.0
        elif hazard_level == 'HIGH':
            return 4.0
        else:
            return 5.0
    
    def _score_fire_risk(self, fire_hazards: Dict) -> Optional[float]:
        auto_ignition = fire_hazards.get('auto_ignition_risk', {}).get('risk_level', 'LOW')
        # ÖH D35 / OH-ON-06: değerlendirilemeyen eksen SKORLANMAZ; deponun
        # kendi kanalı (``risks_not_evaluated``) onu adıyla geri çeker.
        if auto_ignition == AUTO_IGNITION_NOT_EVALUATED:
            return None
        if auto_ignition == 'LOW':
            return 2.0
        elif auto_ignition == 'MEDIUM':
            return 3.0
        else:
            return 4.0
    
    # Additional helper methods would continue here...
    # For brevity, I'll include key remaining methods
    
    def _check_safety_compliance(self, risk_assessment: Dict) -> Dict:
        """Mevzuat uygunluğunun DEĞERLENDİRİLMEDİĞİNİ açıkça bildirir.

        Bu fonksiyon eskiden ``nfpa_compliance``/``osha_compliance``/
        ``dot_compliance`` alanlarını koşulsuz ``True`` döndürüyordu; kod
        yorumları ("Would check specific NFPA requirements") gerçek bir kontrol
        yapılmadığını zaten söylüyordu. Arayüz bunları yeşil "NFPA: OK" rozeti
        olarak çiziyordu — motorun büyüklüğünden, iticisinden ve kullanım
        yerinden tamamen bağımsız olarak. Bu, kullanıcıda yanlış bir otorite
        algısı yaratıyordu.

        Gerçek uygunluk değerlendirmesi madde-madde requirement karşılaştırması,
        tesis/saha bilgisi, yerel mevzuat ve yetkili bir değerlendirici gerektirir;
        bunların hiçbiri yazılıma girdi olarak verilmiyor. Bu yüzden alanlar
        ``NOT_EVALUATED`` döner ve arayüz bunu yetkiliye yönlendiren nötr bir
        bilgi olarak gösterir.

        Uygunluk hükmü üretmek isteyen bir sürüm, önce requirement kimliği,
        kanıt ve değerlendirici alanlarını şemaya eklemek zorundadır.
        """
        return {
            # Risk skoru kabul edilebilirliği MODELİN kendi ölçütüdür;
            # mevzuat uygunluğu DEĞİLDİR. Ad bu ayrımı taşır.
            'model_risk_acceptability': risk_assessment['acceptability'],
            'nfpa_compliance': 'NOT_EVALUATED',
            'osha_compliance': 'NOT_EVALUATED',
            'dot_compliance': 'NOT_EVALUATED',
            'local_regulations': 'NOT_EVALUATED',
            'insurance_requirements': 'NOT_EVALUATED',
            'disclaimer_code': 'warn.safety.compliance_not_evaluated',
        }
    
    @staticmethod
    def _risk_at_least(risk_assessment: Dict, eksen: str, esik: float) -> bool:
        """Eksen skoru eşiği aşıyor mu — DEĞERLENDİRİLMEMİŞ eksen False.

        ÖH Z5S / S6: ``_score_toxic_risk`` (kardeşi ``_score_thermal_risk``
        gibi) artık ``None`` dönebiliyor. Çıplak ``>=`` karşılaştırması bu
        durumda ``TypeError`` atıp ucu 500'e düşürüyordu; ``None`` "eşiğin
        altında" DEĞİL "ölçülmedi" demektir ve ayrı bir dalda ele alınır.
        """
        skor = (risk_assessment.get('individual_risks') or {}).get(eksen)
        return skor is not None and skor >= esik

    def _generate_safety_recommendations(self, risk_assessment: Dict) -> List[str]:
        """Generate prioritized safety recommendations"""

        recommendations = []

        if risk_assessment['acceptability'] == 'UNACCEPTABLE':
            recommendations.append(_mk_warning(
                'warn.safety.do_not_proceed', 'critical'))
            recommendations.append(_mk_warning(
                'warn.safety.redesign_required', 'critical'))

        if self._risk_at_least(risk_assessment, 'structural', 4.0):
            recommendations.append(_mk_warning(
                'warn.safety.increase_structural_sf', 'warning'))
            recommendations.append(_mk_warning(
                'warn.safety.higher_strength_materials', 'warning'))

        if self._risk_at_least(risk_assessment, 'explosive', 4.0):
            recommendations.append(_mk_warning(
                'warn.safety.blast_resistant_design', 'warning'))
            recommendations.append(_mk_warning(
                'warn.safety.increase_safety_distances', 'warning'))

        # Toksik eksen: ölçülmüş yüksek risk VE ölçülememiş eksen AYNI
        # tavsiyeyi doğurur (fail-closed). Değerlendirilmemiş bir toksik
        # eksende gaz algılama/PPE önerisini SUSTURMAK, kazanılmamış bir
        # "gerek yok" hükmü olurdu. Yeni çeviri anahtarı AÇILMADI: iki kod
        # da bu dosyada zaten kullanılıyordu.
        _toksik_olculmedi = 'toxic' in (
            risk_assessment.get('risks_not_evaluated') or [])
        if self._risk_at_least(risk_assessment, 'toxic', 3.0) or _toksik_olculmedi:
            recommendations.append(_mk_warning(
                'warn.safety.toxic_gas_detection', 'warning'))
            recommendations.append(_mk_warning(
                'warn.safety.ppe_and_training', 'info'))

        # Add more recommendations based on specific risks...

        return recommendations
    
    # Deterministik yardımcı hesaplar (2026-07-14'te gerçek
    # implementasyonla dolduruldu; danışma amaçlı büyüklük kestirimleri)
    def _calculate_radiant_heat_distance(self, temperature: float, area: float,
                                         emissivity: Optional[float] = None,
                                         ambient: Optional[float] = None) -> float:
        """Acı eşiği (2.5 kW/m²) radyan tehlike mesafesi [m].

        Args:
            temperature: IŞIYAN YÜZEYİN sıcaklığı [K] — hazne gazı değil, dış
                cidar. (Eski çağrı hazne gazını geçiyordu; T^4 nedeniyle akı
                ~100x şişiyordu.)
            area: Işıyan dış yüzey ALANI [m²]. (Eski çağrı buraya cidar
                kalınlığının 100 katını geçiyordu — birim hatası.)
            emissivity: Yüzey yayınırlığı; None ise varsayılan.
            ambient: Ortam sıcaklığı [K]; None ise varsayılan.

        Model: P = eps*sigma*(T^4 - T_amb^4)*A yayılan güç, izotropik nokta
        kaynak yaklaşımıyla q(r) = P/(4*pi*r²). r, q = 2.5 kW/m² için çözülür.
        """
        eps = (SAFETY_MODEL['default_surface_emissivity']
               if emissivity is None else float(emissivity))
        t_amb = (SAFETY_MODEL['ambient_temperature_k']
                 if ambient is None else float(ambient))
        sigma = SAFETY_MODEL['stefan_boltzmann']
        emitted_flux = eps * sigma * max(float(temperature) ** 4 - t_amb ** 4, 0.0)
        threshold = SAFETY_MODEL['radiant_pain_threshold_w_m2']
        distance = np.sqrt(emitted_flux * max(float(area), 0.0)
                           / (4.0 * np.pi * threshold))
        return float(max(distance, SAFETY_MODEL['min_hazard_distance_m']))

    def _burn_dose_distance(self, surface_temperature: float, area: float,
                            exposure_time_s: float, emissivity: float,
                            ambient: float) -> float:
        """2. derece yanık DOZ mesafesi [m] — maruziyet süresini kullanır.

        Termal doz birimi (API 521 / Eisenberg probit):
            TDU = t * (q [kW/m²])^(4/3)
        2. derece yanık eşiği ~1000 (kW/m²)^(4/3)·s. Eşik akı:
            q_esik = (TDU_esik / t)^(3/4)  [kW/m²]
        ve mesafe q(r) = P/(4*pi*r²) tersinden çözülür. Yanma süresi uzadıkça
        aynı akı daha tehlikeli olur, yani mesafe BÜYÜR.
        """
        t_exp = max(float(exposure_time_s), 1e-3)
        sigma = SAFETY_MODEL['stefan_boltzmann']
        power = emissivity * sigma * max(
            float(surface_temperature) ** 4 - float(ambient) ** 4, 0.0) * max(
                float(area), 0.0)
        q_threshold_kw = (SAFETY_MODEL['second_degree_burn_tdu'] / t_exp) ** 0.75
        q_threshold = q_threshold_kw * 1000.0  # W/m²
        if power <= 0 or q_threshold <= 0:
            return 0.0
        # Hesaplanan değer KIRPILMADAN döner; asgari duruş mesafesi önerisi
        # ayrı alanda (recommended_minimum_standoff_m) verilir. Kırpma burada
        # yapılırsa maruziyet süresinin etkisi görünmez olur.
        return float(np.sqrt(power / (4.0 * np.pi * q_threshold)))


    def _identify_toxic_components(self, propellant_type: str,
                                   motor_type=None) -> List[str]:
        """Toksik bileşen listesi (geriye dönük imza).

        Sınıflandırmanın TEK kaynağı ``_classify_toxic_inventory``; bu
        sarmalayıcı yalnız bileşen listesini verir ve çözünürlük künyesini
        atar. Hüküm üreten yol künyeye BAKMAK ZORUNDA olduğu için
        ``_analyze_toxic_hazards`` sınıflandırıcıyı doğrudan çağırır.
        """
        return list(self._classify_toxic_inventory(
            propellant_type, motor_type)['components'])

    def _classify_toxic_inventory(self, propellant_type,
                                  motor_type=None) -> Dict:
        """``propellant_type``ı toksik envanter sınıfına çözer (ÖH Z5S / S6).

        **P7B3-21 (KRİTİK) — ÖLÇÜLEN KUSUR** (taban ``df67bce``,
        ``POST /analyze_safety``, kanıt
        ``docs/scofield/raw/OH/Z5S/s6/once_supurme.json``): eski kod
        ``toxic_map.get(propellant_type, [])`` yazıyordu, yani

        * TANINMAYAN her değer (``'peynir'``, ``'hydrazine'``, ``''``, alan
          hiç yok) sessizce BOŞ envantere düşüyor ve ``toxic_hazard_level``
          ``'NONE'`` + ``ppe_requirements: []`` basılıyordu. Bilinmeyen bir
          itici için "toksik tehlike YOK" bir hükümdür ve kazanılmamıştır —
          **fail-open**.
        * ``'liquid_biprop'`` ve ``'solid_monoprop'`` dallarındaki koşul
          ÖLÜ KODDU: ``toxic_map`` anahtarı TAM eşleşme ile seçildiği için
          ``propellant_type`` tam olarak ``'liquid_biprop'`` olmak
          zorundaydı, o dizede de ``'n2o4'`` alt dizesi asla bulunmaz.
          Yani panelin gönderdiği sıvı çift-itici koşumu her zaman
          ``'NONE'`` alıyordu (LOX/RP-1 ile N2O4/MMH aynı hükmü görüyordu).
        * Yalnız ``'liquid_monoprop'`` gerçekten ateşliyordu (ölçüldü:
          ``MEDIUM``, üç bileşen, dolu PPE) — bu yüzden kalemin "panelin
          gönderebildiği HER değer NONE" başlığı ölçümle YANLIŞ; kusur
          bilinmeyende fail-open ve ölü daldır.

        Sözleşme:

        ``tabulated``
            Bileşenler ``self.toxic_hazards`` tablosundan ADIYLA çözüldü;
            hüküm KAZANILIR.
        ``class_inventory_undetermined``
            Sınıf tanınıyor ama envanteri sınıf adından belirlenemiyor
            (bir sıvı çift-iticinin toksisitesi hangi itici çiftinin
            kullanıldığına bağlıdır). Hüküm GERİ ÇEKİLİR.
        ``class_inventory_not_tabulated``
            Sınıf tanınıyor ve HRMA'da tablolu toksik bileşeni YOK (katı
            kompozit aileleri). ``'NONE'`` korunur ama KAPSAMI beyan edilir:
            yanma ÜRÜNLERİ (ör. AP'den HCl) envantere dâhil değildir.
        ``unrecognised_propellant_class``
            Değer tanınan altı sınıftan biri değil. Hüküm GERİ ÇEKİLİR.

        Serbest metin: ``'liquid_biprop n2o4'`` gibi sınıf adıyla BAŞLAYAN
        bir dize sınıfına çözülür ve alt dize araması ölü olmaktan çıkar.
        """
        ham = '' if propellant_type is None else str(propellant_type)
        anahtar = ham.strip().lower()

        # --- ADIM 0 (P5B2-02): serbest metinde TABLOLU bileşen adı ara ----
        # ÖLÇÜLEN KUSUR (taban e88d096, once.json): ürünün gerçekten
        # gönderdiği adların HİÇBİRİ çözülmüyordu — 'n2o4_mmh', 'mmh',
        # 'n2o4', 'hydrazine', 'udmh', 'nto_mmh' altısı da
        # ``unrecognised_propellant_class`` ile hükümsüz kalıyordu. Oysa
        # kardeş kol (``_resolve_explosive_class``) aynı serbest metni
        # ÇÖZÜYOR. Envanterin tek kaynağı ``self.toxic_hazards``dır; metin
        # alfasayısal olmayan ayraçlarda parçalanıp TAM SÖZCÜK eşleşmesi
        # aranır ('n2o4' içinde 'n2o' yakalanmaz).
        parcalar = [p for p in re.split(r'[^a-z0-9]+', anahtar) if p]
        adli = [p for p in parcalar if p in self.toxic_hazards]
        if adli:
            gorulen = []
            for p in adli:
                if p not in gorulen:
                    gorulen.append(p)
            return {
                'components': gorulen,
                'resolution': TOXIC_RESOLUTION_TABULATED,
                'propellant_class': None,
                'propellant_class_source': 'propellant_type',
                'known_propellant_classes': list(KNOWN_PROPELLANT_CLASSES),
                'resolvable_propellant_classes':
                    self._resolvable_propellant_classes(),
                'basis': (
                    "propellant_type named "
                    + ', '.join(f"'{p}'" for p in gorulen)
                    + ", which is in the tabulated exposure-limit list."),
            }

        sinif = None
        if anahtar in KNOWN_PROPELLANT_CLASSES:
            sinif = anahtar
        else:
            # Uzun ad önce: 'composite_db' 'composite'ten önce denenmeli.
            for aday in sorted(KNOWN_PROPELLANT_CLASSES, key=len, reverse=True):
                if anahtar.startswith(aday):
                    sinif = aday
                    break

        sinif_kaynagi = 'propellant_type' if sinif is not None else None

        # ÖH D37 A1b panel-js 5. tur: 'modellenmedi' beyanı motor tipi
        # yedeğiyle bir sınıfa ÇEVRİLMEZ (katı motorda 'composite' envanteri
        # şeker iticiye yazılırdı); sınıf yok -> toksik hüküm adıyla geri
        # çekilir (aşağıdaki tanınmayan sınıf kolu).
        if (sinif is None and motor_type is not None
                and self._explosive_not_modelled(propellant_type,
                                                 motor_type) is None):
            # P5B2-02: patlayıcı kolun kullandığı AYNI eşleme (tek kaynak).
            # 'lox_rp1' + motor_type='liquid' artık "tanınmayan" değil,
            # "sınıfı belli ama envanteri adından belirlenemeyen" duruma
            # düşer — hüküm yine GERİ ÇEKİLİR ama gerekçe doğrudur ve
            # kullanıcıya ne yazması gerektiğini söyler.
            mt = str(motor_type).strip().lower()
            if mt in MOTOR_TYPE_TO_EXPLOSIVE_CLASS:
                sinif = self._motor_type_fallback_class(propellant_type, mt)
                sinif_kaynagi = 'motor_type'

        # --- ÖH D15 birleştirme (1 Eyl 2026) — ADIN ÇÖZÜLMEDİĞİ SÖYLENİR --
        # ÖLÇÜLDÜ (birleşik ağaç, ``/analyze_safety``): motor_type yedeği
        # devreye girdiği için ``propellant_type='peynir'``, ``'APCP'``,
        # ``'ZZZ'`` ÜÇÜ de ``propellant_class: 'liquid_biprop'`` künyesiyle
        # dönüyordu ve yanıtın HİÇBİR yerinde kullanıcının yazdığı adın
        # tanınmadığı yazmıyordu. Seviye doğru şekilde geri çekiliyordu
        # (fail-closed korunuyor) ama gerekçe kullanıcıya BAŞKA bir şey
        # anlatıyor: APCP katı bir kompozittir, "sıvı çift-itici" değil.
        # Yedek KALIR (yapısal kulvarın P5B2-02 gerekçesi geçerli: sınıf
        # motor_type'tan gerçekten bilinir), ama künye artık kaynağını ve
        # çözülemeyen adı ADIYLA taşır. Sayı/eşik değişmez.
        _ad_notu = ''
        if sinif_kaynagi == 'motor_type':
            _ad_notu = (
                f"The value sent in propellant_type ({ham.strip()!r}) is not "
                "one of the propellant classes HRMA has a toxic inventory "
                "rule for and no tabulated component name was found in it, "
                f"so the class below was taken from motor_type "
                f"({str(motor_type).strip()!r}), NOT from what you typed. ")

        if sinif is None:
            return {
                'components': [],
                'resolution': TOXIC_RESOLUTION_UNRECOGNISED,
                'propellant_class': None,
                'propellant_class_source': None,
                'known_propellant_classes': list(KNOWN_PROPELLANT_CLASSES),
                'resolvable_propellant_classes':
                    self._resolvable_propellant_classes(),
                'basis': (
                    "propellant_type did not resolve to any propellant class "
                    "HRMA has a toxic inventory rule for, so no toxic "
                    "inventory was identified. An unidentified propellant is "
                    "not a non-toxic propellant: no toxic hazard level is "
                    "published for it."),
            }

        if sinif == 'liquid_monoprop':
            return {
                'components': ['mmh', 'udmh', 'hydrazine'],
                'resolution': TOXIC_RESOLUTION_TABULATED,
                'propellant_class': sinif,
                'propellant_class_source': sinif_kaynagi,
                'known_propellant_classes': list(KNOWN_PROPELLANT_CLASSES),
                'resolvable_propellant_classes':
                    self._resolvable_propellant_classes(),
                'basis': ('liquid monopropellant: the hydrazine family '
                          '(MMH / UDMH / N2H4) is inventoried from the '
                          'tabulated exposure limits.'),
            }

        # OH-D28-08: hibrit sınıfı da BU dala girer. Girmezse aşağıdaki
        # 'tablolu toksik bileşeni yok' dalına düşer ve kazanılmamış bir
        # ``'NONE'`` yayımlanırdı — P7B3-21'in fail-open kusuru geri
        # gelirdi. Ölçüldü (once.json/sonra.json K5): htpb + hybrid için
        # çözünürlük ÖNCE de SONRA da ``class_inventory_undetermined``.
        imler = {'liquid_biprop': 'n2o4', 'solid_monoprop': 'n2o',
                 'hybrid_n2o': 'n2o'}
        if sinif in imler:
            im = imler[sinif]
            # Alt dize araması TAM METİNDE yapılır (eski kod yalnız sınıf
            # adına bakıyordu ve dal asla girilmiyordu).
            if im in anahtar:
                return {
                    'components': [im],
                    'resolution': TOXIC_RESOLUTION_TABULATED,
                    'propellant_class': sinif,
                    'propellant_class_source': sinif_kaynagi,
                    'known_propellant_classes': list(KNOWN_PROPELLANT_CLASSES),
                    'resolvable_propellant_classes':
                        self._resolvable_propellant_classes(),
                    'basis': (f"the request named '{im}', which is in the "
                              "tabulated exposure-limit list."),
                }
            return {
                'components': [],
                'resolution': TOXIC_RESOLUTION_UNDETERMINED,
                'propellant_class': sinif,
                'propellant_class_source': sinif_kaynagi,
                'known_propellant_classes': list(KNOWN_PROPELLANT_CLASSES),
                'resolvable_propellant_classes':
                    self._resolvable_propellant_classes(),
                'basis': (
                    _ad_notu
                    + f"'{sinif}' names a propellant CLASS, not a propellant: "
                    "the toxic inventory depends on which propellants are "
                    "actually used (LOX/RP-1 and N2O4/MMH are both liquid "
                    "bipropellants and are not comparable; a hybrid's "
                    "inventory is set by its oxidiser). Name the "
                    "propellant in propellant_type (for example "
                    f"'{sinif} {im}') to get an inventory."),
            }

        # composite / double_base / composite_db
        return {
            'components': [],
            'resolution': TOXIC_RESOLUTION_NOT_TABULATED,
            'propellant_class': sinif,
            'propellant_class_source': sinif_kaynagi,
            'known_propellant_classes': list(KNOWN_PROPELLANT_CLASSES),
            'resolvable_propellant_classes':
                self._resolvable_propellant_classes(),
            'basis': (
                _ad_notu
                + f"'{sinif}' has no tabulated toxic component in HRMA, so no "
                "toxic inventory is reported. SCOPE: this covers the stored "
                "propellant only. Combustion PRODUCTS (for example HCl and "
                "alumina from ammonium-perchlorate composites) are NOT "
                "inventoried by this analysis."),
        }

    # ------------------------------------------------------------------
    # 2026-07-14: /analyze_safety 500 veriyordu — sınıfın çağırdığı 25
    # yardımcı metot hiç yazılmamıştı ("Many more helper methods would be
    # implemented here..."). Aşağıdakiler genel emniyet pratiğine dayalı
    # deterministik sınıflandırma/tavsiye merdivenleridir; tesise özgü
    # mevzuat yerine geçmez, danışma amaçlıdır.
    # ------------------------------------------------------------------

    def _determine_pressure_safety_devices(self, chamber_pressure: float) -> List[Dict]:
        # {code,params,severity} kaydı döner (D-track); safety_panel bunları
        # TF() ile çevirir. safety_devices_required alanı frontend'de gösterilir.
        devices = [
            _mk_warning('warn.safety.relief_valve_full_flow', 'info'),
            _mk_warning('warn.safety.burst_disc_secondary', 'info'),
        ]
        if chamber_pressure > SAFETY_MODEL['vessel_medium_pressure_bar']:
            devices.append(_mk_warning('warn.safety.remote_pressure_abort', 'info'))
        if chamber_pressure > SAFETY_MODEL['vessel_high_pressure_bar']:
            devices.append(_mk_warning('warn.safety.redundant_transducers', 'info'))
        return devices

    def _classify_explosive_hazard(self, tnt_equivalent: float) -> str:
        if tnt_equivalent < SAFETY_MODEL['tnt_minor_hazard_kg']:
            return 'HD 1.4 equivalent — minor hazard, local effects only'
        if tnt_equivalent < SAFETY_MODEL['tnt_mass_fire_kg']:
            return 'HD 1.3 equivalent — mass fire / minor blast hazard'
        return 'HD 1.1 equivalent treatment recommended — mass explosion potential'

    def _determine_storage_requirements(self, tnt_equivalent, propellant_type) -> List[str]:
        # ÖH D35 / OH-ON-06: ``tnt_equivalent`` ve ``propellant_type``
        # ``None`` olabilir (patlayıcı ekseni geri çekildi). Eşiğe bağlı
        # madde o hâlde EKLENMEZ — ölçülemeyen bir karşılaştırma "eşiğin
        # altında" sayılmaz.
        reqs = ['Segregate oxidizer and fuel storage', 'Grounded, ventilated storage area',
                'No ignition sources within exclusion zone']
        if tnt_equivalent is not None and \
                tnt_equivalent >= SAFETY_MODEL['tnt_minor_hazard_kg']:
            reqs.append('Dedicated magazine with quantity-distance siting')
        if 'liquid' in str(propellant_type or '').lower():
            reqs.append('Secondary containment and leak detection for liquid propellants')
        return reqs

    def _determine_transport_requirements(self, tnt_equivalent, propellant_type) -> List[str]:
        # ÖH D35 / OH-ON-06 — yukarıdaki kardeşiyle aynı kural.
        reqs = ['Transport per ADR/DOT dangerous goods rules', 'Documented and placarded load']
        if tnt_equivalent is not None and \
                tnt_equivalent >= SAFETY_MODEL['tnt_minor_hazard_kg']:
            reqs.append('Class 1 explosives routing and escort requirements apply')
        if 'liquid' in str(propellant_type or '').lower():
            reqs.append('Pressure-rated, relief-equipped transport containers')
        return reqs

    def _calculate_toxic_release_scenario(self, component: str, propellant_mass: float,
                                          facility_type: str) -> Dict:
        # Kaba korunma mesafesi: kütle ile karekök ölçekleme, bileşene göre katsayı
        katsayi = {'n2o4': 60.0, 'mmh': 80.0, 'udmh': 80.0, 'hydrazine': 90.0, 'n2o': 15.0}
        base = katsayi.get(component, 30.0)
        distance_m = base * max(propellant_mass, 0.1) ** 0.5
        return {
            'component': component,
            'release_mass_kg': propellant_mass,
            'protective_action_distance_m': round(distance_m, 0),
            'hazard_distance_m': round(distance_m, 0),  # tüketici bu adı okuyor
            'facility_type': facility_type,
            'scenario': 'Worst-case full inventory release, neutral weather (F stability)',
            # SAFE-TEXT-3 (2026-07-28): katsayıların ERG/NIOSH/SDS atfı YOK.
            # Sayı korunur (planlama için tamamen silmek kullanıcıyı bilgisiz
            # bırakır) ama dayanağı açıkça beyan edilir; doğrulama şartı
            # disclaimer_code ile arayüze taşınır.
            'source': ('generic sqrt(mass) scaling with tool-chosen '
                       'per-component coefficients - not an ERG/dispersion-'
                       'model result; verify against the propellant SDS and '
                       'current DOT Emergency Response Guidebook guidance'),
            'disclaimer_code': 'warn.safety.toxic_distance_basis_unverified',
        }

    def _determine_toxic_detection_requirements(self, toxic_components: List[str]) -> List[str]:
        if not toxic_components:
            return []
        return ['Fixed gas detection for: ' + ', '.join(toxic_components),
                'Portable detectors for entry teams',
                'Alarm setpoints at 50% of exposure limit']

    def _determine_toxic_ppe_requirements(self, toxic_components: List[str]) -> List[str]:
        if not toxic_components:
            return ['Standard test-stand PPE (eye/ear protection, flame-resistant clothing)']
        agir = any(c in ('mmh', 'udmh', 'hydrazine', 'n2o4') for c in toxic_components)
        if agir:
            return ['SCBA or supplied-air respirator for transfer operations',
                    'Chemical splash suit (Level B) for hypergolic handling',
                    'Butyl rubber gloves; emergency shower/eyewash within 10 s reach']
        return ['Half-mask respirator with appropriate cartridge available',
                'Chemical splash goggles and gloves']

    def _assess_toxic_hazard_level(self, release_scenarios: List[Dict]) -> str:
        if not release_scenarios:
            return 'LOW'
        d = max(s.get('hazard_distance_m', 0) for s in release_scenarios)
        if d >= SAFETY_MODEL['toxic_high_distance_m']:
            return 'HIGH'
        if d >= SAFETY_MODEL['toxic_medium_distance_m']:
            return 'MEDIUM'
        return 'LOW'

    def _determine_exposure_monitoring(self, toxic_components: List[str]) -> List[str]:
        if not toxic_components:
            return []
        return ['Personal dosimetry/badge sampling for exposed personnel',
                'Post-operation area sampling before re-entry',
                'Medical surveillance program for routine handlers']

    def _determine_emergency_treatment(self, toxic_components: List[str]) -> Dict:
        tedavi = {}
        for c in toxic_components:
            if c in ('mmh', 'udmh', 'hydrazine'):
                tedavi[c] = 'Remove from exposure, oxygen, pyridoxine (B6) protocol per physician'
            elif c == 'n2o4':
                tedavi[c] = 'Fresh air, oxygen; observe 24-48 h for delayed pulmonary edema'
            elif c == 'n2o':
                tedavi[c] = 'Fresh air, oxygen if hypoxic symptoms'
            else:
                tedavi[c] = 'Decontaminate, supportive care, consult poison control'
        return tedavi

    def _classify_fire_hazard(self, propellant_type: str,
                              motor_type=None) -> str:
        """Yangın sınıfı — itici ADI değil, ÇÖZÜLEN sınıf belirler.

        **P5B2-04 (YÜKSEK) — ÖLÇÜLEN KUSUR** (taban ``e88d096``, kanıt
        ``once.json``): eski kod ``'liquid' in propellant_type`` diye
        SERBEST METİNDE alt dizge arıyordu. Ölçüldü —

        ==================  ===============================================
        ``propellant_type``  eski sınıf
        ==================  ===============================================
        ``lox_rp1``          **Class 1.3 katı yakıt (söndürülemez)**
        ``n2o4_mmh``         **Class 1.3 katı yakıt (söndürülemez)**
        ``n2o_htpb``         **Class 1.3 katı yakıt (söndürülemez)**
        ``liquid_biprop``    Class B (yalnız iç sınıf adı yazılırsa)
        ==================  ===============================================

        Yani LOX/RP-1 sıvı motoruna "kendi oksijenini taşır, söndürülemez"
        deniyor ve müdahale listesine ``'Let solid propellant burn out'``
        yazılıyordu; köpük/AFFF dalı hiç tetiklenmiyordu. Bir sıvı yakıt
        dökülme yangınında ekibe "yanmasını bekleyin" demek yanlış YÖNDE
        bir hatadır.

        Çözüm tek kaynaklıdır: sınıfı ``_resolve_explosive_class`` çözer —
        patlayıcı kolun zaten kullandığı ``propellant_tnt_equivalents``
        anahtarları + ``MOTOR_TYPE_TO_EXPLOSIVE_CLASS`` eşlemesi. Hibrit,
        eşlemede ``liquid_biprop``a düştüğü için motor tipinden ayrıca
        ayrılır (yakıt grain'i Class A'dır).
        """
        mt = str(motor_type or '').strip().lower()
        if mt == 'hybrid':
            return 'Class A fuel grain + oxidizer-enhanced burning'
        sinif, _dayanak = self._resolve_explosive_class(propellant_type,
                                                        motor_type)
        if sinif in ('liquid_biprop', 'liquid_monoprop'):
            return 'Class B (flammable liquid) with oxidizer-enhanced burning'
        if 'hybrid' in str(propellant_type or '').lower():
            return 'Class A fuel grain + oxidizer-enhanced burning'
        # ÖH D35 / OH-ON-06: sınıf kazanılmadıysa (``None``) eski kod buraya
        # DÜŞÜP 'Class 1.3-type solid propellant fire' basıyordu — ölçüldü,
        # bir N2O/HTPB hibritin PDF'i tam bu satırı taşıyordu. Kimlik
        # yokken yangın sınıfı da yoktur.
        if sinif is None:
            return FIRE_CLASS_NOT_EVALUATED
        return 'Class 1.3-type solid propellant fire (self-oxidized, cannot be smothered)'


    def _assess_auto_ignition_risk(self, propellant_type: str,
                                   chamber_temperature: float,
                                   motor_type: Optional[str] = None) -> Dict:
        """Otomatik tutuşma riski — itici ADI değil, ÇÖZÜLEN sınıf.

        **P5B2-14 (ÖH D15 / a3) — ÖLÇÜLEN KUSUR** (``a3/once.json``): eski
        kod ``'solid' in propellant_type`` / ``'liquid' in propellant_type``
        diye SERBEST METİNDE alt dizge arıyordu. Kardeş kalem P5B2-04'te
        yangın SINIFI aynı sebeple yanlıştı ve ``_resolve_explosive_class``
        ile onarıldı; bu fonksiyon o onarımın dışında kalmıştı, yani AYNI
        yanıtta sınıf doğru, tutuşma riski yanlış çıkıyordu:

        =================  ==============  ===========  ==============
        ``propellant_type`` yangın sınıfı   eski risk    sabit deluge
        =================  ==============  ===========  ==============
        ``lox_rp1``         Class B         **LOW**      **hayır**
        ``n2o4_mmh``        Class B         **LOW**      **hayır**
        ``apcp`` (2900 K)   Class 1.3       **LOW**      **hayır**
        ``liquid_biprop``   Class B         MEDIUM       evet
        =================  ==============  ===========  ==============

        Yani ``liquid_biprop`` yazan kullanıcı sabit uzaktan kumandalı
        deluge önerisi alıyor, AYNI motoru ``lox_rp1`` diye yazan almıyordu
        (yangın risk ekseni 3,0 yerine 2,0). Çözüm tek kaynaklıdır: sınıfı
        ``_resolve_explosive_class`` çözer.
        """
        # _score_fire_risk 'risk_level' anahtarını okuyor — dict sözleşmesi
        sinif, dayanak = self._resolve_explosive_class(propellant_type,
                                                       motor_type)
        mt = str(motor_type or '').strip().lower()
        # ÖH D35 / OH-ON-06: sınıf kazanılmadıysa eski kod son dala düşüp
        # ``LOW`` + 'Controlled ignition sources only' yazıyordu. Bir
        # tutuşma riskini 'düşük' ilan etmek, ölçülmemiş olduğunu söylemek
        # DEĞİLDİR; ``_score_fire_risk`` onu 2,0 puanlıyor ve genel hükmü
        # yumuşatıyordu. Kardeş desen: toksik eksenin NOT_EVALUATED kanalı.
        if sinif is None and mt not in ('solid', 'hybrid', 'liquid'):
            return {'risk_level': AUTO_IGNITION_NOT_EVALUATED,
                    'note': ('Auto-ignition risk was not assessed: the '
                             'propellant class was not won from the request '
                             'identity.'),
                    'resolved_class': None, 'basis': dayanak}
        if sinif in ('liquid_biprop', 'liquid_monoprop'):
            return {'risk_level': 'MEDIUM',
                    'note': ('Vapor accumulation near hot components; '
                             'ventilate before approach'),
                    'resolved_class': sinif, 'basis': dayanak}
        try:
            sicak = (float(chamber_temperature)
                     > SAFETY_MODEL['autoignition_hot_gas_k'])
        except (TypeError, ValueError):
            sicak = False
        if sicak and (mt in ('solid', 'hybrid')
                      or sinif in ('composite', 'double_base', 'composite_db',
                                   'solid_monoprop')):
            return {'risk_level': 'MEDIUM',
                    'note': ('Residual grain can reignite from hot surfaces; '
                             'enforce cooldown'),
                    'resolved_class': sinif, 'basis': dayanak}
        return {'risk_level': 'LOW',
                'note': 'Controlled ignition sources only',
                'resolved_class': sinif, 'basis': dayanak}

    def _analyze_fire_spread_potential(self, propellant_mass: float, propellant_type: str) -> str:
        if propellant_mass > SAFETY_MODEL['fire_spread_high_mass_kg']:
            return 'HIGH — radiant heating can ignite adjacent structures; wide firebreak needed'
        if propellant_mass > SAFETY_MODEL['fire_spread_medium_mass_kg']:
            return 'MEDIUM — local spread possible; clear combustibles within safety distance'
        return 'LOW — limited to immediate test area'

    def _determine_fire_suppression_system(self, fire_class: str,
                                           propellant_mass: float,
                                           auto_ignition_risk: Dict) -> Dict:
        """Yangın bastırma sistemi önerisi.

        ÖH D23 / P5B2-25 — TİP İPUCU GÖVDEYLE ÇELİŞİYORDU. ÖLÇÜLDÜ (taban
        ``ef527ae``, ``once.json`` P5B2-25): imza
        ``auto_ignition_risk: str`` diyordu, gövde ise
        ``auto_ignition_risk.get('risk_level')`` çağırıyordu. İpucuna UYAN
        çağrı (``fn('Class B', 5.0, 'HIGH')``)
        ``AttributeError: 'str' object has no attribute 'get'`` ile
        patlıyor, tek gerçek çağıran (``satır 1247``) ise
        ``_assess_auto_ignition_risk`` sözlüğünü geçiriyordu. İpucu
        gövdeye uyduruldu: parametre ``{'risk_level': ...}`` sözlüğüdür.

        Args:
            fire_class: NFPA yangın sınıfı metni ('Class B ...').
            propellant_mass: Toplam itici kütlesi [kg].
            auto_ignition_risk: ``_assess_auto_ignition_risk`` sözlüğü;
                ``'risk_level'`` anahtarı okunur.
        """
        sistemler = ['Water deluge for cooling structures (note: solid propellant fires are not extinguishable — protect exposures and let burn)']
        primary = 'Water deluge (exposure protection)'
        if 'Class B' in fire_class:
            sistemler.append('Foam or CO2 capability for liquid fuel spill fires')
            primary = 'Foam (AFFF) on liquid spill; water for cooling'
        if (propellant_mass > SAFETY_MODEL['fixed_deluge_mass_kg']
                or auto_ignition_risk.get('risk_level') in ('HIGH', 'MEDIUM')):
            sistemler.append('Fixed remote-actuated deluge over test stand')
        sistemler.append('Rated portable extinguishers at all egress points')
        return {'primary_agent': primary, 'systems': sistemler}

    def _calculate_fire_safety_distances(self, propellant_mass: float) -> Dict:
        # Kaba kübik-kök ölçekleme (kütle ↑ → mesafe ↑), min 15 m
        base = max(propellant_mass, 1.0) ** (1.0 / 3.0)
        return {
            'personnel_distance_m': round(max(15.0, 20.0 * base), 0),
            'equipment_distance_m': round(max(10.0, 10.0 * base), 0),
            'public_distance_m': round(max(60.0, 60.0 * base), 0),
            # _generate_emergency_procedures bu anahtarı okuyor
            'radiant_heat_m': round(max(15.0, 20.0 * base), 0),
            # SAFE-TEXT-3 (2026-07-28): 20*m^(1/3) katsayılarının NFPA/QD
            # tablosu atfı yok. Sayılar korunur, dayanağı beyan edilir.
            'source': ('generic cube-root mass scaling chosen for this '
                       'tool - not taken from NFPA or quantity-distance '
                       'tables; verify against the applicable range safety '
                       'rules before use'),
            'disclaimer_code': 'warn.safety.fire_distance_basis_unverified',
        }

    def _identify_ignition_sources_control(self) -> List[str]:
        return ['Hot work permit system within exclusion zone',
                'Bonding/grounding of all transfer equipment',
                'Non-sparking tools for propellant handling',
                'ATEX/intrinsically-safe electrical equipment in vapor zones',
                'No smoking / no open flame policy with physical enforcement']

    def _generate_fire_fighting_procedures(self, fire_class: str) -> List[str]:
        adimlar = ['Evacuate to safety distance and account for personnel',
                   'Actuate remote deluge; do NOT approach burning propellant',
                   'Notify fire brigade with propellant data sheet']
        if 'not be smothered' in fire_class or 'solid' in fire_class.lower():
            adimlar.append('Let solid propellant burn out; cool surroundings only')
        adimlar.append('Re-enter only after thermal + toxic clearance measurements')
        return adimlar

    def _determine_safety_equipment_requirements(self, explosive_hazards: Dict,
                                                 toxic_hazards: Dict, fire_hazards: Dict,
                                                 facility_type: str) -> Dict:
        return {
            'fixed_systems': ['Remote firing and abort system', 'Blast barrier or berm',
                              'Fixed deluge (per fire analysis)', 'Area gas detection (per toxic analysis)'],
            'personal_equipment': ['Flame-resistant clothing', 'Hearing and eye protection',
                                   'Hard hats in mechanical hazard areas'] +
                                  toxic_hazards.get('ppe_requirements', []),
            'emergency_equipment': ['First aid + burn kit', 'Emergency shower/eyewash',
                                    'Backup communications', 'Fire blankets and extinguishers'],
            'facility_type': facility_type,
        }

    def _determine_personnel_limits(self, motor_data: Dict, facility_type: str) -> Dict:
        return {
            'test_cell_during_operation': 0,
            'control_room': 'Essential test crew only',
            'observation_area': 'Authorized personnel behind rated barrier',
            'note': 'No personnel inside exclusion zone from pressurization to safing',
        }

    def _determine_qualification_requirements(self, facility_type: str) -> List[str]:
        return ['Documented propellant-handling qualification for operators',
                'Test conductor certified on abort procedures',
                'Annual requalification and emergency drill participation']

    def _determine_training_requirements(self, propellant_type: str, facility_type: str) -> List[str]:
        egitim = ['Propellant hazards and compatibility training',
                  'Emergency response and evacuation drills',
                  'Pressure systems safety awareness']
        if 'liquid' in str(propellant_type or '').lower():
            egitim.append('Cryogenic/toxic liquid transfer procedures (as applicable)')
        return egitim

    def _determine_required_antidotes(self, toxic_hazards: Dict) -> List[str]:
        """Antidot listesi — toksik hüküm GERİ ÇEKİLDİYSE tavsiye verilmez.

        **P5B2-02 (KRİTİK) — ÖLÇÜLEN KUSUR** (taban ``e88d096``, kanıt
        ``docs/scofield/raw/OH/D15/yapisal-sistem/a1/once.json``): toksik
        sınıflandırma ``NOT_EVALUATED`` dediği 12 vakanın 12'sinde bu
        fonksiyon yine de ``'No specific antidote required — supportive
        care'`` basıyordu. Bu, DEĞERLENDİRİLMEMİŞ bir tehlike hakkında
        verilmiş TIBBİ bir hükümdür ve kazanılmamıştır: envanteri
        çözülemeyen bir itici için "antidot gerekmiyor" denemez. Boş
        envanter iki farklı şey olabilir — "baktık, tablolu toksik bileşen
        yok" (hüküm kazanıldı) ve "bakamadık" (hüküm yok); eski kod ikisini
        aynı cümleye indiriyordu.
        """
        bilesenler = toxic_hazards.get('toxic_components', []) or []
        antidot = []
        if any(c in ('mmh', 'udmh', 'hydrazine') for c in bilesenler):
            antidot.append('Pyridoxine (vitamin B6) IV protocol available on site/nearby')
        if 'n2o4' in bilesenler:
            antidot.append('Oxygen therapy capability; bronchodilators per physician')
        if antidot:
            return antidot
        if toxic_hazards.get('toxic_hazard_level') == TOXIC_LEVEL_NOT_EVALUATED:
            return [ANTIDOTE_WITHHELD]
        return ['No specific antidote required — supportive care']

    def _generate_treatment_protocols(self, toxic_hazards: Dict) -> List[str]:
        return ['Decontaminate (remove clothing, flush 15 min) before transport',
                'Transport with propellant safety data sheet',
                'Observe gas-exposure casualties for delayed symptoms (24-48 h)']

    def _generate_risk_matrix(self) -> Dict:
        return {
            'axes': {'likelihood': ['Rare', 'Unlikely', 'Possible', 'Likely', 'Frequent'],
                     'severity': ['Negligible', 'Minor', 'Major', 'Critical', 'Catastrophic']},
            'acceptance': {'LOW': 'Acceptable with routine controls',
                           'MEDIUM': 'Acceptable with documented mitigations',
                           'HIGH': 'Requires risk reduction before test',
                           'CRITICAL': 'Unacceptable — redesign or re-site'},
        }

    def _determine_mitigation_priority(self, structural: float, pressure: float,
                                       thermal: Optional[float], explosive: float,
                                       toxic: float, fire: float) -> List[Dict]:
        """Azaltım önceliği — yalnız DEĞERLENDİRİLEN eksenler sıralanır.

        ÖH Z3: skoru olmayan eksen bu listeye uydurma bir sayıyla giremez
        (sıralama sayısal). Adı ``mitigation_priority_not_evaluated`` alanında
        ayrıca yayımlanır, yani listeden düşmesi sessiz kalmaz.
        """
        adlar = [('structural', structural), ('pressure', pressure),
                 ('thermal', thermal), ('explosive', explosive),
                 ('toxic', toxic), ('fire', fire)]
        olculen = [(ad, sk) for ad, sk in adlar if sk is not None]
        sirali = sorted(olculen, key=lambda x: x[1], reverse=True)
        return [{'area': ad, 'risk_score': round(sk, 2), 'priority': i + 1}
                for i, (ad, sk) in enumerate(sirali)]
    # This is a representative sample of the complete safety analysis system