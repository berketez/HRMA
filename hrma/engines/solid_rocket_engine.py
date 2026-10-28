import numpy as np
# ÖH D26 / OH-D25-14: ``np.trapz`` NumPy 2.0'da ad alanından
# KALDIRILDI (np.trapezoid); ad TEK YERDE çözülür.
from hrma.utils.numeric_compat import trapezoid as _trapezoid
from functools import lru_cache

from hrma.constants import STEFAN_BOLTZMANN
from hrma.constants import AMBIENT_TEMPERATURE_BAND_K
from scipy.integrate import odeint
from scipy.optimize import fsolve, newton
from scipy.interpolate import interp1d
from typing import Dict
import json
import re
import warnings

# Star grain gerçek yanma-yüzeyi modeli için (poligon ofseti, Huygens ilkesi).
# Yoksa star için eski basitleştirilmiş çevre yaklaşıklığına düşülür.
try:
    from shapely.geometry import Polygon as _ShapelyPolygon, Point as _ShapelyPoint
    SHAPELY_AVAILABLE = True
except ImportError:
    SHAPELY_AVAILABLE = False


def _w(code: str, severity: str = "warning", **params) -> Dict:
    """i18n uyarısı: dile bağlı sabit metin YERİNE yapısal kayıt.

    Dönen sözlük ``{"code", "params", "severity"}``. Dil tamamen frontend'e
    taşınır; frontend ``TF(code, params)`` ile yerelleştirilmiş metni kurar.
    ``severity`` ∈ {"critical", "warning", "info"} — ciddiyet artık metin
    içeriğinden DEĞİL bu alandan okunur (dil sızıntısı yok).

    Sayısal ``params`` değerleri, eski f-string'in kullandığı basamak sayısına
    yuvarlanır; böylece yerelleştirilmiş metin eskisiyle aynı sayıyı gösterir.
    Kod adlandırması: ``warn.solid.<slug>`` (katalog: docs/v262_specs/D_codes_solid.md).
    """
    return {"code": code, "params": params, "severity": severity}


# Uyarı kaydının TEKİLLİK anahtarı — TANIM BURADA DEĞİL (ÖH D30/OH-Z3-04).
# Aynı gövde ``hybrid_rocket_engine.py`` içinde İKİNCİ KEZ yazılıydı ve iki
# docstring "sözleşme öbürüyle birebir aynıdır" diye birbirine YORUMLA
# bağlıydı; eşitliği kod korumuyordu (ölçüldü: iki_motor_ayni_nesne=False).
# Tek tanım noktası ``hrma.engines.warning_records``tır.
from hrma.engines.warning_records import (  # noqa: E402
    warning_identity as _warning_identity)


def _critical_thermal_verdicts(*blocks):
    """Termal blokların ürettiği ``severity: critical`` hükümlerin listesi.

    NEDEN VAR (ÖH P16S1-07): motor katmanı ``severity: critical`` termal
    hükümler üretiyor ve bunlar iki dile de çevrilmiş durumda, ama hiçbiri
    kullanıcıya ULAŞMIYORDU. Ölçüldü (grafit yerine alüminyum lüle seçilen
    5 kN katı motor): ``nozzle_material_analysis.warnings`` içinde
    ``warn.solid.nozzle_material_over_temp`` / ``critical`` duruyor, üst
    düzey ``warnings`` listesinde ise SIFIR kritik var — ekran katmanı
    (``solid.html`` ``displaySolidWarnings``) yalnız üst düzey listeyi okuduğu
    için hüküm hiçbir yerde görünmüyordu.

    Bu işlev hükmü ÜRETMEZ, YENİDEN YAZMAZ, ÖZETLEMEZ: bloklardan gelen
    kaydın ta kendisini (kod + parametre + ciddiyet) taşır. Kapsam bilinçli
    olarak ``critical`` ile sınırlıdır — "bu tasarım ayakta kalmaz" diyen bir
    hüküm asla sessiz kalamaz; daha düşük ciddiyetteki termal notlar kendi
    bloklarında kalmaya devam eder (onların tüketicisi ilgili paneldir).

    Blok olarak ``warnings`` anahtarı taşıyan herhangi bir sözlük verilebilir;
    iç içe sözlükler de (ör. ``heat_transfer_analysis``) taranır.
    """
    found, seen = [], set()

    def _gez(node, depth=0):
        if depth > 3 or not isinstance(node, dict):
            return
        for record in (node.get('warnings') or []):
            if isinstance(record, dict):
                critical = str(record.get('severity', '')).lower() == 'critical'
            elif isinstance(record, str):
                critical = record.strip().upper().startswith('CRITICAL')
            else:
                continue
            if not critical:
                continue
            key = _warning_identity(record)
            if key in seen:
                continue
            seen.add(key)
            found.append(record)
        for value in node.values():
            if isinstance(value, dict):
                _gez(value, depth + 1)

    for block in blocks:
        _gez(block)
    return found


def _hrma_version():
    """Paket sürümü — bağlanan analiz bloklarının künyesine girer.

    Bağlama beyanı "hangi modül, hangi girdiler, hangi sürümde" sorusunu
    cevaplamak zorundadır; sürüm burada TEK yerden okunur (hrma/__init__.py).
    Paket meta verisi okunamazsa sayı UYDURULMAZ, 'unknown' beyan edilir.
    """
    try:
        from hrma import __version__ as _v
        return str(_v)
    except Exception:  # pragma: no cover - paket meta verisi okunamazsa
        return 'unknown'


# ---------------------------------------------------------------------------
# Sabit shapely geometrilerinin önbelleği (v2.5.5 performans, davranış AYNI).
#
# İtki eğrisi döngüsü her zaman adımında kasa diskini, dış-çember şeridini ve
# başlangıç port poligonunu SIFIRDAN kuruyordu; bunlar yalnız geometri
# parametrelerinin fonksiyonudur ve poligon kurulumu deterministiktir — aynı
# girdiler her çağrıda BİT-AYNI poligonu üretir. Önbellek anahtarı geometriyi
# belirleyen TÜM parametreleri içerir; shapely geometrileri değişmez
# (immutable) olduğundan paylaşım güvenlidir. Modül seviyesinde tutulur ki
# Monte Carlo / UQ gibi aynı geometriyle YÜZLERCE motor örneği kuran yollar
# da paylaşsın (ölçüm: star itki eğrisi 83 ms -> ~35 ms, wagon 142 -> ~55 ms).
# ---------------------------------------------------------------------------
@lru_cache(maxsize=64)
def _cached_case_disk(r_go):
    """Kasa iç kesit diski (yarıçap m) — _clipped_* kırpma geometrisi."""
    return _ShapelyPoint(0.0, 0.0).buffer(r_go, quad_segs=96)


@lru_cache(maxsize=64)
def _cached_case_ring(r_go):
    """Kasa çemberine oturan yayları yakalayan ince şerit (m)."""
    return _cached_case_disk(r_go).boundary.buffer(max(1e-6, r_go * 1e-6))


@lru_cache(maxsize=64)
def _cached_star_polygon(n_pts, r_i, depth):
    """Başlangıç star port kesiti — _star_port_polygon ile AYNI kurulum."""
    verts = []
    for k in range(n_pts):
        a_tip = 2.0 * np.pi * k / n_pts
        a_val = 2.0 * np.pi * (k + 0.5) / n_pts
        r_p = r_i + depth
        verts.append((r_p * np.cos(a_tip), r_p * np.sin(a_tip)))
        verts.append((r_i * np.cos(a_val), r_i * np.sin(a_val)))
    return _ShapelyPolygon(verts)


@lru_cache(maxsize=64)
def _cached_wagon_polygon(r_core, r_pitch, n_holes=6):
    """Wagon-wheel port kesiti — _wagon_port_polygon ile AYNI kurulum
    (merkez + ``n_holes`` çevre delik, hepsi aynı yarıçap, sıralı union).
    V301/K-B (KT-08): çevre delik sayısı parametre oldu (varsayılan 6 =
    eski sabit; aynı girdi bit-aynı poligon)."""
    holes = [_ShapelyPoint(0.0, 0.0).buffer(r_core, quad_segs=48)]
    for k in range(n_holes):
        a = 2.0 * np.pi * k / float(n_holes)
        holes.append(_ShapelyPoint(r_pitch * np.cos(a),
                                   r_pitch * np.sin(a))
                     .buffer(r_core, quad_segs=48))
    port = holes[0]
    for h in holes[1:]:
        port = port.union(h)
    return port


@lru_cache(maxsize=64)
def _cached_slot_quads(r_port, n_slots, width, depth):
    """Radyal yuva ilkelleri — _radial_slot_primitives ile AYNI kurulum."""
    half = width / 2.0
    r_tip = r_port + depth
    quads = []
    for k in range(n_slots):
        ang = 2.0 * np.pi * k / n_slots
        ux, uy = np.cos(ang), np.sin(ang)
        vx, vy = -uy, ux  # teğetsel birim vektör
        quads.append(_ShapelyPolygon([
            (half * vx, half * vy),
            (r_tip * ux + half * vx, r_tip * uy + half * vy),
            (r_tip * ux - half * vx, r_tip * uy - half * vy),
            (-half * vx, -half * vy),
        ]))
    return tuple(quads)

# v2.6.27 (F2-2): ``vacuum_isp_ratio`` ampirik log-fiti bu motordan
# ÇIKARILDI — vakum Isp'si artık motorun kendi CF zincirinden türer
# (bkz. _thrust_coefficient_vacuum). İthal geri gelirse ampirik yol da
# geri gelmiş demektir.
from hrma.constants import (G_0, ISA_LAYERS, M_AIR,
                            R_STAR_ICAO, R_UNIVERSAL,
                            ISA_TABLE_TOP_M, isa_temperature, isa_pressure)
# Yayımlanan eğrinin seyreltmesi: katı ve hibrit AYNI algoritmayı kullanır,
# tanımı ortak modüldedir (bkz. SOLID_THRUST_CURVE_MAX_POINTS yorumu).
from hrma.analysis.curve_sampling import (
    THRUST_CURVE_MAX_POINTS,
    decimate_curve_indices as _ortak_seyreltme_indeksleri,
    nearest_sample_index as _en_yakin_ornek,
    sampling_block as _ornekleme_blogu,
)
# ÖH D25 · P15B2-09 (Fable-D18 ŞARTI): kapak/flanş cıvata birleşiminin
# varsayılan sözleşmesi birleşimi ÇÖZEN modülde tek kez yazılıdır; katı
# motor onu literal olarak yeniden yazmaz, buradan türetir
# (bkz. SOLID_CLOSURE_JOINT_DEFAULTS). Sıvı ve hibrit motor aynı adı aynı
# takma adla içe aktarıyor — desen bilerek birebir aynı. ÜYE MALZEMESİ
# sabiti (CLOSURE_JOINT_MEMBER_MATERIAL_DEFAULT) BİLEREK alınmaz: D15 /
# P2B2-12'de üye malzemesi kasadan türetildi (bkz. _closure_member_material).
from hrma.analysis.bolted_joint import (
    CLOSURE_JOINT_DEFAULTS as _BOLTED_JOINT_CLOSURE_DEFAULTS,
)

# Parametrik maliyet modeli birim fiyatları (2026 tahmini, USD) — TEK tanım
# noktası. _calculate_cost_analysis bunlardan ölçekler; kesin fiyat değildir.
SOLID_COST_PARAMS = {
    'propellant_usd_per_kg': {
        'apcp': 40.0, 'knsb': 12.0, 'knsu': 10.0, 'kndx': 12.0,
        'black_powder': 15.0, 'default': 35.0,
    },
    # malzeme AİLESİ -> ham kasa malzemesinin birim fiyatı [USD/kg].
    #
    # ÖH D21 a1 (P2B1-12): bu tablo eskiden (yoğunluk, USD/kg) İKİLİSİ
    # taşıyordu ve yoğunluk sütunu ÖLÜYDÜ — ürün kodunda tek tüketici
    # yalnız [1]'i (fiyatı) okuyordu, kütle zinciri ise yoğunluğu
    # `_case_density()` ile materials_db'den alıyordu. Ölü sütun yalnızca
    # yanlış değil, YANILTICIYDI: `SOLID_CASE_MATERIAL_EXTRA['composite']`
    # kaydı kendi yoğunluğunun "tek tanım noktası" olarak bu sütunu
    # gösteriyordu, yani atıf hiç okunmayan bir veriye işaret ediyordu.
    # Ayrıca sütun materials_db ile de tutarsızdı (bulucu ölçümü:
    # al_7075_t6 2810 vs 2700, ss_304 8000 vs 7850, ti_grade2_cp 4510 vs
    # 4430 kg/m3). Sütun kaldırıldı; MALİYET tablosu yalnız FİYAT taşır,
    # yoğunluğun tek tanım noktası malzeme kayıtlarıdır.
    'case_materials': {
        'steel': 8.0,
        'aluminum': 15.0,
        'composite': 60.0,
        'titanium': 90.0,
    },
    'nozzle_usd_per_kg': 80.0,       # grafit/işlenmiş çelik karışık ortalama
    'insulation_usd_per_kg': 25.0,   # EPDM/fenolik
    'labor_usd_per_hour': 30.0,
}

# Deniz seviyesi referans basıncı (bar) — itki katsayısı ve optimum genişleme
# hesabının TEK tanım noktası.
SEA_LEVEL_PRESSURE_BAR = 1.01325

# ---------------------------------------------------------------------------
# TASARIM ÖZETİ DURUM SÖZLÜĞÜ (Faz 4B, bulgu B1/B2/A3)
#
# Aynı sözlük üç motor dosyasında da BİREBİR tanımlıdır (hybrid / liquid /
# solid); tam gerekçe ve etiket anlamları
# hrma/engines/hybrid_rocket_engine.py içindeki aynı blokta yazılıdır. Çapraz
# import bilinçli olarak yapılmaz; değerlerin aynı kaldığı makinece denetlenir:
#   tests/test_faz4_motor_kapilari.py::test_durum_sozlugu_uc_motorda_ayni
#
# Katı motorun kendi durumu zaten 'CALCULATED' idi (eniyileme yok, girdiden
# deterministik çözüm) — sözlüğün geri kalanı bu davranışla uyumlu tanımlandı.
# ---------------------------------------------------------------------------
DESIGN_STATUS_OPTIMIZED = 'OPTIMIZED'
DESIGN_STATUS_CALCULATED = 'CALCULATED'
DESIGN_STATUS_ESTIMATED_WITH_DEFAULTS = 'ESTIMATED_WITH_DEFAULTS'
DESIGN_STATUS_TARGET_NOT_MET = 'TARGET_NOT_MET'
DESIGN_STATUS_UNVALIDATED_ESTIMATE = 'UNVALIDATED_ESTIMATE'
DESIGN_STATUS_NOT_CONVERGED = 'NOT_CONVERGED'

DESIGN_STATUS_SEVERITY = {
    DESIGN_STATUS_OPTIMIZED: 0,
    DESIGN_STATUS_CALCULATED: 1,
    DESIGN_STATUS_ESTIMATED_WITH_DEFAULTS: 2,
    DESIGN_STATUS_TARGET_NOT_MET: 3,
    DESIGN_STATUS_UNVALIDATED_ESTIMATE: 4,
    DESIGN_STATUS_NOT_CONVERGED: 5,
}

# ---------------------------------------------------------------------------
# ÖH D26 (defter P15B3-02, YÜKSEK) — TASARIM NOKTASI HEDEFİ DÜŞÜRÜLDÜ
#
# ``_apply_design_point_sizing`` gönderilmiş bir hedefi ÜÇ ayrı daldan sessizce
# düşürebiliyordu (zarf tutmadı / tane ailesi boyutlandırmayı desteklemiyor /
# girdi geometrisi geçerli eğri üretmiyor). Üçünde de motor, çözücüye verilen
# BAŞLANGIÇ geometrisinin eğrisini HTTP 200 ile yayımlıyordu; yani yanıt
# istekten BAĞIMSIZ hâle geliyordu. ÖLÇÜLDÜ (``docs/scofield/raw/OH/D26/kati/
# a1/once.json``, taban 7751531; Ø100 / çekirdek 35 / tane 300 mm BATES, APCP,
# 40 bar, 3 s):
#   istek  20 / 50 / 100 / 150 / 200 / 250 N  ->  ALTISINDA DA
#   average_thrust = 1930,475099292884 N, burn_time = 4,479165439800482 s,
#   boğaz 24,089628036183527 mm (bit-özdeş; 20 N isteyen 96,5 kat itki alıyor)
# ve eşiğin hemen ötesinde yön TERSİNE dönüyordu:
#   istek 250 N -> teslim 1930,475 N   ⟷   istek 300 N -> teslim 282,146 N
#   (+%20 istek, −%85,38 teslim: DAHA ÇOK isteyen DAHA AZ alıyor)
# Desteklenmeyen tane ailelerinde durum daha da sessizdi: star / finocyl /
# slotted / wagon_wheel'de ``design_point`` yanıtta HİÇ yoktu ve 20 N ile
# 250 N isteklerinin yanıtları BAYT BAYT aynıydı (sha16 8152cfd30fbd,
# ca6874b13868, 1a6cd061641f, ab42d1d7057f).
#
# Bu durum kodu, hedefin düşürüldüğünü YAPISAL olarak (uyarı metnini
# ayrıştırmadan) bildirir; ``/calculate_solid`` bunu görünce hüküm yayımlamaz.
# Sebep alt kırılımı ``design_point['reason']`` alanındadır.
# ---------------------------------------------------------------------------
DESIGN_POINT_STATUS_NOT_REACHED = 'design_point_not_reached'

#: ``design_point['reason']`` değerleri — hedefin NEDEN düşürüldüğü.
DESIGN_POINT_REASON_BATES_ENVELOPE = 'bates_envelope_not_met'
DESIGN_POINT_REASON_END_BURNER_ENVELOPE = 'end_burner_envelope_not_met'
DESIGN_POINT_REASON_UNSUPPORTED_GRAIN = 'sizing_unsupported_grain'
DESIGN_POINT_REASON_INVALID_CURVE = 'input_geometry_curve_invalid'

# ---------------------------------------------------------------------------
# Kasa (basınçlı kap) tasarım varsayılanları — TEK tanım noktası.
# _calculate_dry_mass, _calculate_structural_analysis ve
# _calculate_safety_analysis AYNI değerleri buradan okur; kullanıcı formdan
# case_material / yield_strength / safety_factor / case_thickness gönderirse
# _apply_overrides bunları ezer.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Kasa malzemesi: materials_db'de KARŞILIĞI OLMAYAN, ama UI'da seçilebilen
# aileler (solid.html case_material seçimi: steel / aluminum / composite /
# titanium). 'composite' materials_db'de yok ve get_material() bunun için
# KeyError atıyordu; çağrı yerleri istisnayı yutup sessizce çelik yoğunluğunu
# (7800-7850 kg/m3) kullanıyordu — kompozit kasalı motor çelik kuru kütlesiyle
# ve yanlış itki/ağırlık oranıyla raporlanıyordu (Codex bulgusu, 2026-07-19).
#
# SESSİZ ÇELİK YASAK. Aşağıdaki kayıt açık ve kaynaklıdır:
#  - yoğunluk 1600 kg/m3: filaman sarımlı cam/karbon-epoksi kasa
#    kabuğunun tipik yığın yoğunluğudur ve materials_db'de KARŞILIĞI
#    OLMADIĞI için TEK tanım noktası BURASIDIR (aşağıdaki 'density'
#    alanı). ÖH D21 a1 (P2B1-12): bu satır eskiden tek tanım noktası
#    olarak SOLID_COST_PARAMS['case_materials']['composite'] yoğunluk
#    sütununu gösteriyordu; ölçüldü ki o sütun ÜRÜN KODUNDA HİÇ
#    OKUNMUYORDU (tek tüketici yalnız fiyatı alıyordu), yani atıf ölü
#    veriye işaret ediyordu. Sütun kaldırıldı, atıf düzeltildi. Değer
#    DEĞİŞMEDİ — kompozit kasa kütlesi bit-aynıdır.
#  - dayanım 300 MPa: HRMA'nın kullanıcıya beyan ettiği kompozit bandının
#    (solid.html akma dayanımı ipucu: "Composite: 300-800 MPa") ALT ucudur.
#    En muhafazakâr uçtur (daha kalın cidar, daha düşük emniyet payı iddiası).
#    Kompozit izin verilen gerilmesi serim/elyaf oranına bağlıdır; bu yüzden
#    kullanıcı 'yield_strength' girmediyse tasarım uyarısı üretilir.
# ---------------------------------------------------------------------------
SOLID_CASE_MATERIAL_EXTRA = {
    'composite': {
        'name': 'Filament-wound composite (generic)',
        'density': 1600.0,          # kg/m3 — kompozitin TEK tanım noktası
        'yield_strength': 300.0e6,  # Pa (UI beyan bandının alt ucu)
        'generic_allowable': True,  # kullanıcı ölçülen değeri girmeli
        # V301/K-B (KT-11): reçine sınırı (Tg / servis sıcaklığı) için bu
        # depoda KAYNAKLI bir kayıt YOK. Eskiden ısıl sınır sessizce çeliğin
        # 811 K'i oluyordu (ısıl pay ~390 K fazla). Sayı uydurulmaz: None,
        # ısıl hüküm "değerlendirilmedi" (case_limit_status = 'no_record').
        'max_service_temp': None,
    },
}

#: V301/K-B (KT-11) — kasa ısıl sınırının durum etiketleri (yanıtta
#: ``material_temperature_limits.case_limit_status``).
SOLID_CASE_LIMIT_STATUS_RECORD = 'materials_db'
SOLID_CASE_LIMIT_STATUS_NO_RECORD = 'no_record'
#: Kayıt yokken ısıl koruma sınıfının kodu (sayfa bunu çevirir).
SOLID_CASE_THERMAL_NOT_EVALUATED = (
    'Not evaluated — no temperature limit on record for this case material')

# ---------------------------------------------------------------------------
# V301/K-B (KT-10 / KT-12) — KATI SAYFASININ MALZEME SEÇENEKLERİ (TEK KAYNAK)
#
# Sayfanın kasa ve lüle seçicileri bu kayıttan üretilir (``/solid`` rotası
# ``_kati_malzeme_secim_kaydi``). Seçenek kümesi İCAT EDİLMEZ: materials_db
# etiketleri (``shell`` = basınçlı kabuk adayı; ``insert`` = boğaz eki
# adayı) + motorun kendi ek kaydı (kompozit). Kümenin seçimi bir HRMA
# seçimidir (literatür değeri değil). Eski form değerleri (v3.0.0 sayfası:
# 'aluminum', 'titanium') aynen korunur ki kayıtlı projeler aynı yanıtı alsın.
# 'phenolic' listeden ÇIKTI: materials_db'de lüle boğazı için kaynaklı kaydı
# yok ve ablasyon modeli yok (KT-10, ana model kararı 5); API'de 422.
# ---------------------------------------------------------------------------
SOLID_CASE_MATERIAL_TAG = 'shell'
SOLID_NOZZLE_MATERIAL_TAG = 'insert'
SOLID_NOZZLE_DEFAULT_MATERIAL = 'graphite'
#: v3.0.0 sayfasının form değerleri -> kanonik kayıt (eski projeler).
SOLID_MATERIAL_FORM_LEGACY_VALUES = {
    'case_material': ('steel', 'aluminum', 'titanium', 'composite'),
    'nozzle_material': ('graphite', 'tungsten'),
}


def solid_case_material_record(material):
    """Kasa malzemesinin kanonik anahtarı + özellikleri; çözülemezse None.

    Sıra ``SolidRocketEngine._case_material_properties`` ile aynıdır:
    materials_db (takma ad dâhil) -> ``SOLID_CASE_MATERIAL_EXTRA``.
    """
    from hrma.data.materials_db import (canonical_name, get_material,
                                        temperature_limits)
    if not isinstance(material, str) or not material.strip():
        return None
    ham = material.strip()
    kanonik = canonical_name(ham.lower().replace(' ', '_'))
    if kanonik is not None:
        rec = get_material(kanonik)
        return {
            'material_key': kanonik,
            'name': rec.get('name', kanonik),
            'yield_strength_mpa': float(rec['yield_strength']) / 1e6,
            'density_kg_m3': float(rec['density']),
            'max_service_temp_k': temperature_limits(rec)['service_K'],
            'source': rec.get('source'),
            'generic_allowable': False,
        }
    extra = SOLID_CASE_MATERIAL_EXTRA.get(ham.lower())
    if extra is None:
        return None
    return {
        'material_key': ham.lower(),
        'name': extra['name'],
        'yield_strength_mpa': float(extra['yield_strength']) / 1e6,
        'density_kg_m3': float(extra['density']),
        'max_service_temp_k': extra.get('max_service_temp'),
        'source': ('SOLID_CASE_MATERIAL_EXTRA (HRMA generic allowable; '
                   'no resin temperature limit on record)'),
        'generic_allowable': bool(extra.get('generic_allowable', False)),
    }


def solid_nozzle_material_record(material):
    """Lüle malzemesinin kanonik anahtarı + ısıl özellikleri; yoksa None."""
    from hrma.data.materials_db import (canonical_name, get_material,
                                        temperature_limits)
    if not isinstance(material, str) or not material.strip():
        return None
    kanonik = canonical_name(material.strip().lower().replace(' ', '_'))
    if kanonik is None:
        return None
    rec = get_material(kanonik)
    return {
        'material_key': kanonik,
        'name': rec.get('name', kanonik),
        'allowable_temperature_k': temperature_limits(rec)['allowable_K'],
        'thermal_conductivity_w_mk': rec.get('thermal_conductivity'),
        'erosion_band': ('published' if kanonik in SOLID_NOZZLE_EROSION_MATERIAL
                         else 'none'),
        'source': rec.get('source'),
    }


def solid_material_options(alan):
    """Sayfanın ``alan`` seçicisinin seçenekleri (sıra: materials_db sırası).

    Her seçenek: ``value`` (form değeri), ``material_key`` (kanonik) ve
    hesabın o rol için OKUDUĞU özellikler. Kayıtta olmayan özellik ``None``
    kalır (sayfa onu basmaz; sayı uydurulmaz).
    """
    from hrma.data.materials_db import MATERIALS
    if alan == 'case_material':
        etiket, cozucu = SOLID_CASE_MATERIAL_TAG, solid_case_material_record
        ek = list(SOLID_CASE_MATERIAL_EXTRA)
    elif alan == 'nozzle_material':
        etiket = SOLID_NOZZLE_MATERIAL_TAG
        cozucu = solid_nozzle_material_record
        ek = []
    else:
        raise KeyError(alan)
    eski = {}
    for deger in SOLID_MATERIAL_FORM_LEGACY_VALUES.get(alan, ()):
        kayit = cozucu(deger)
        if kayit is not None:
            eski.setdefault(kayit['material_key'], deger)
    anahtarlar = [k for k, r in MATERIALS.items()
                  if etiket in (r.get('tags') or [])] + ek
    secenekler = []
    for k in anahtarlar:
        kayit = cozucu(k)
        if kayit is None:
            raise RuntimeError(f'{alan} option {k!r} does not resolve')
        secenekler.append(dict(kayit, value=eski.get(k, k)))
    return secenekler

# ---------------------------------------------------------------------------
# TEK KAPTA TEK MALZEME KİMLİĞİ (v2.6.27, bebek-Scofield F2-1)
# ---------------------------------------------------------------------------
# ÖLÇÜLDÜ (HEAD f9d95eb, varsayılan katı motor: APCP, D=100 mm, d_çekirdek=
# 30 mm, L=500 mm, Pc=40 bar): aynı kasa ÜÇ ayrı malzeme kimliği taşıyordu.
#
#   etiket   ('case_material')        -> 'steel_4130'  (AISI 4130, 460/730 MPa)
#   dayanım  (cidar + hoop + SF)      -> 250 MPa       (A36 sınıfı jenerik çelik)
#   yoğunluk (kuru kütle + maliyet)   -> 7800 kg/m³    (hiçbir kayıtta yok;
#                                        her iki kayıt da 7850 der)
#
# Sonuç ölçüldü: kopma basıncı `PressureVesselAnalyzer`a ETİKETLE gidiyordu,
# yani cidar 250 MPa ile boyutlandırılıp 4130'un 460/730 MPa'sıyla sınanıyordu:
#
#   case_material göndermeden : burst = 341,13 bar   (rho = 7800)
#   case_material='steel'     : burst = 186,09 bar   (rho = 7850)
#
# yani ARAYÜZÜN KENDİ VARSAYILANIYLA (solid.html'deki <select> ilk seçeneği
# 'steel') aynı motor için 1,833 kat farklı kopma basıncı. Alan gönderilmeyen
# her yol (doğrudan motor kullanımı, dışa aktarım, UQ, API çağrısı) kazanılmamış
# 4130 dayanımını görüyordu.
#
# DÜZELTME: varsayılan malzeme arayüzün kendi varsayılanına ('steel')
# eşitlendi ve dayanım/yoğunluk artık BURADA İKİNCİ KEZ TANIMLANMIYOR —
# materials_db kaydından okunur. Böylece boyutlandırmanın kullandığı dayanım
# ile kopma basıncının kullandığı dayanım TANIM GEREĞİ aynı kayıttan gelir.
# 'steel' kaydı ASTM A36 minimumlarıdır (250/400 MPa) ve solid.html'in
# kullanıcıya beyan ettiği banda ("Steel: 200-400 MPa") oturur.
#: Kasa varsayılan malzemesi — solid.html `#case_material` <select> ilk
#: seçeneğiyle (value="steel") BİREBİR aynı olmak zorunda; aksi hâlde alan
#: gönderilen ve gönderilmeyen yollar farklı malzeme görür.
SOLID_CASE_DEFAULT_MATERIAL = 'steel'


def _solid_case_default_properties():
    """Varsayılan kasa malzemesinin materials_db kaydı (tek okuma noktası)."""
    from hrma.data.materials_db import get_material
    return get_material(SOLID_CASE_DEFAULT_MATERIAL)


_SOLID_CASE_DEFAULT_REF = _solid_case_default_properties()

SOLID_CASE_DESIGN = {
    'material': SOLID_CASE_DEFAULT_MATERIAL,   # materials_db anahtarı
    # Dayanım ve yoğunluk TÜRETİLMİŞTİR — burada ikinci bir tanım YOKTUR.
    'yield_strength_pa': float(_SOLID_CASE_DEFAULT_REF['yield_strength']),
    'design_safety_factor': 3.0,     # akmaya karşı tasarım katsayısı
    'min_wall_thickness_m': 0.002,   # üretilebilirlik alt sınırı
    # Yalnız BEYAN amaçlı: hesapta kullanılmaz (``_case_density`` kaydı
    # doğrudan okur). Türetilmiş olduğu için kayıttan ayrışamaz.
    'case_density_kg_m3': float(_SOLID_CASE_DEFAULT_REF['density']),
    # Emniyet valfi ayarı: tasarım basıncının bu oranı (API 520 sınıfı
    # pratik). Hesaplanmış bir kap basıncı değil, ÖNERİdir.
    'relief_fraction_of_design': 0.85,
}

# Ön + arka kapak kütlesinin kasa kabuğu kütlesine oranı — TEK tanım noktası.
# Hem kuru kütle zinciri (`_calculate_dry_mass`) hem maliyet modeli
# (`_calculate_cost_analysis`) bunu kullanır; daha önce ikisi ayrı ayrı
# (0.30 ve 1.15) yazılıydı ve aynı kasa iki farklı kütleyle fiyatlanıyordu.
SOLID_CASE_CLOSURE_MASS_FRACTION = 0.30

# Ön + arka kapak takımının grain yığınına EKLEDİĞİ eksenel boy [m] —
# TEK tanım noktası (ÖH D21 a1, P2B1-08).
#
# ÖLÇÜLDÜ (docs/scofield/raw/OH/D21/kati/a1/once.json): sayı ürün kodunda
# İKİ kez çıplak literal olarak yazılıydı — ``_case_inner_length()``
# (kasa iç boyu = grain + segment araları + pay, :2661) ve
# ``_grain_envelope_volume()`` (``_case_inner_length() - 0.1``, payı geri
# çıkaran ters işlem, :2690) — üstelik ``_case_inner_length()`` kendi
# künyesinde "tek tanım noktası artık burası" diyordu. İki literal bugün
# aynı sayıyı taşıdığı için yanlış sayı ÜRETMİYORDU; pay değişince ikinci
# satır sessizce sapıyordu (pay 0,15 m denendiğinde grain zarf hacmi
# +%9,84 yanlış çıkıyordu — bulucu ölçümü, P02 raporu B1-repro-15).
#
# DÜRÜSTLÜK NOTU: bu pay ÖLÇÜLMÜŞ ya da KAYNAKLI bir tasarım değeri
# DEĞİLDİR; eski modelden devralınmış bir mühendislik payıdır ve motorun
# hiçbir girdisinden türetilmez. Kasa boyu, kasa kütlesi, serbest hacim ve
# maliyet zinciri bu paydan besleniyor; sayı kaynaklanana kadar en azından
# TEK elden okunur ki değişirse zincirin tamamı birlikte değişsin.
SOLID_CASE_CLOSURE_LENGTH_M = 0.1

# Katalog malzeme anahtarı -> maliyet modeli malzeme AİLESİ eşlemesi
# (Faz 5 / H4-8). `SOLID_COST_PARAMS['case_materials']` yalnız dört jenerik
# aile taşır; `_case_design()` ise materials_db anahtarlarını döndürür
# (steel_4130, titanium_6al4v, ...). Eşleme YOKKEN eski kod sessizce
# ALÜMİNYUMA düşüyordu: titanyum kasa, modelin kendi titanyum satırına göre
# 9,8 kat ucuz fiyatlanıyordu (4430x90 / 2700x15). Artık eşlenemeyen malzeme
# fiyatlanmaz ve bu durum açıkça bildirilir — sessiz varsayılan YOK.
SOLID_CASE_COST_FAMILY = {
    'steel': 'steel', 'steel_4130': 'steel', 'steel_4340': 'steel',
    'ss_304': 'steel', 'ss_316': 'steel', 'ss_17_4ph': 'steel',
    'aluminum': 'aluminum', 'aluminum_6061': 'aluminum',
    'al_2024_t3': 'aluminum', 'al_7075_t6': 'aluminum',
    'titanium': 'titanium', 'titanium_6al4v': 'titanium',
    'ti_grade2_cp': 'titanium',
    'composite': 'composite', 'carbon_carbon': 'composite',
}

# ---------------------------------------------------------------------------
# Yakıt fiyat AİLESİ — katalog/motor anahtarı -> fiyat satırı. TEK tanım noktası.
#
# ÖH D15 a2 (P2B1-05). SOLID_COST_PARAMS['propellant_usd_per_kg'] MOTOR
# anahtarlarıyla yazılıydı (apcp, black_powder, kndx, knsb, knsu, default);
# _resolve_propellant_type ise KATALOG anahtarı üretir. Eşleşmeyen her yakıt
# sessizce 'default' = 35,0 USD/kg satırına düşüyordu. ÖLÇÜLDÜ: 12 katalog
# yakıtının 7'si (apcp_nonaluminized, blue_thunder, double_base, htpb_ap_al,
# kner, pban_ap_al, sugar) sessiz düşüşteydi. Ürün yüzü:
#   * solid.html'in DOKUNULMAMIŞ varsayılan yükü (propellant_name='APCP')
#     'htpb_ap_al' çözüyor -> 35,0 USD/kg; aynı motora 'apcp' seçilince
#     40,0 USD/kg. Yakıt kalemi 226,4 ⟷ 258,7 USD (-%12,49), toplam malzeme
#     347,2 ⟷ 384,3 USD (-%9,66).
#   * 'sugar' (35,0) ⟷ 'knsu' (10,0): AYNI kimya (KNO3 %65 / sakaroz %35),
#     yalnız hangi katalog satırına tıklandığına göre **3,50 KAT** fiyat.
#
# Bu, modülün KASA malzemesi için açıkça kapattığını yazdığı deliğin aynısıdır
# (SOLID_CASE_COST_FAMILY, "sessiz varsayılan YOK"). Aynı desen yakıta da
# uygulanır: eşlenen yakıt kendi satırından fiyatlanır, EŞLENMEYEN yakıt
# FİYATLANMAZ (None) ve toplam da "eksik toplam" olarak yayımlanmaz.
#
# Eşleme gerekçeleri (kimyaya göre; uydurulmuş fiyat YOK, yalnız aynı ailenin
# yayımlanmış satırına bağlanır):
#   htpb_ap_al / pban_ap_al / blue_thunder -> 'apcp' (AP/HTPB(-PBAN) kompozit
#       ailesi; ticari AP-kompozit fiyat bandı)
#   apcp_nonaluminized -> 'apcp' (aynı aile, alüminyumsuz varyant)
#   sugar -> 'knsu' (BİREBİR aynı formülasyon: KNO3 %65 / sakaroz %35; iki
#       satırın tek farkı yoğunluk tabanıdır, bkz. _KNSU_65_35_BASE)
#   kner -> 'knsb' (KN-şeker ailesi, aynı oksitleyici oranı)
#   double_base -> EŞLENMEZ: nitroselüloz/nitrogliserin fiyatı bu modelde YOK
#       ve kompozit/şeker bandının hiçbirine ait değil. Sessizce başka bir
#       yakıtın fiyatına düşmek yerine kalem fiyatlanmaz.
#
# 'default' satırı bu tablonun DIŞINDADIR ve artık okunmaz: sessiz düşüşün
# aracı oydu.
# ---------------------------------------------------------------------------
SOLID_PROPELLANT_COST_FAMILY = {
    'apcp': 'apcp',
    'apcp_nonaluminized': 'apcp',
    'htpb_ap_al': 'apcp',
    'pban_ap_al': 'apcp',
    'blue_thunder': 'apcp',
    'black_powder': 'black_powder',
    'kndx': 'kndx',
    'knsb': 'knsb',
    'kner': 'knsb',
    'knsu': 'knsu',
    'sugar': 'knsu',
}

# ---------------------------------------------------------------------------
# Monte Carlo üretim saçılımı ve başarı ölçütü — TEK tanım noktası.
# v2.6.26 (P4): bu sayılar İKİ yerde ayrı ayrı yazılıydı — bir kez örneklemeyi
# yapan kodda (0.03 / 0.005 / 0.01 / 0.01) ve bir kez kullanıcıya gösterilen
# 'criteria' METİN SABİTİNDE ('İtki ±%10, Isp ±%5, ... a ±%3 ...'). İkisi
# birbirinden habersiz olduğu için kod değişse metin eski değerleri
# göstermeye devam ederdi: kullanıcı koşulmayan bir analizin açıklamasını
# okurdu. Artık hem örnekleme hem açıklama BU tablodan üretilir.
# Bantlar katı yakıt üretimi için literatür-tipik 1σ değerleridir (ölçülmüş
# parti verisi DEĞİL) ve çıktıda 'basis' ile beyan edilir.
#
# KÜNYE DENETİMİ (KU-K2, 6 Eki 2026; sayılar DEĞİŞMEDİ): NASA SP-8064
# "Solid Propellant Selection and Characterization" (Haziran 1971) yalnız
# YANMA HIZI için bir ŞARTNAME SINIRI verir: değişim katsayısı < 0,02
# (§3.3.1.1.1 s. 69), formülasyon kaynaklı sapma ≤ ±%2 (§3.3.1.1.3 s. 70),
# ölçüm standart sapması ≤ %2 (§3.3.1.4 s. 73). Bu bir İZİN VERİLEN EN BÜYÜK
# saçılımdır, gözlenmiş üretim saçılımı değildir. Buradaki a için %3 o
# sınırın ÜSTÜNDEDİR (erken/amatör üretim varsayımı). n, ρ ve c* bantları
# için SP-8064'te sayı BULUNAMADI (OCR tam metin). Olgun üretim CV'leri:
# NASA SP-8039 Tablo III s. 53 (yanma hızı %2,0 BEM, Isp %0,2). Aynı dört
# sayı ``hrma/analysis/uncertainty.py`` 'solid' tablosunda da var (iki
# tanım noktası — devir listesinde; künyeleri burada eşitlendi).
# ---------------------------------------------------------------------------
SOLID_MC_TOLERANCE_MODEL = {
    # 1σ üretim saçılımları
    'burn_rate_a_rel_sigma': 0.03,      # yanma hızı katsayısı a: ±%3 (bağıl)
    'burn_rate_n_abs_sigma': 0.005,     # üs n: ±0.005 (MUTLAK)
    'density_rel_sigma': 0.01,          # yakıt yoğunluğu: ±%1 (bağıl)
    'c_star_rel_sigma': 0.01,           # karakteristik hız: ±%1 (bağıl)
    # Başarı (kabul) ölçütü — nominale göre
    'thrust_band_rel': 0.10,            # ortalama itki nominalin ±%10'u
    'isp_band_rel': 0.05,               # Isp nominalin ±%5'i
    'max_pressure_factor': 1.2,         # tepe basıncı ≤ nominal tepe × 1.2
    'basis': ('literature-typical manufacturing scatter for solid propellant '
              'production; not measured batch data for your propellant. '
              'Source check: NASA SP-8064 (1971) pp. 69-73 gives a '
              'specification LIMIT of 2% standard deviation for the burning '
              'rate only; the burning-rate band used here is wider than that '
              'limit (early-production assumption) and no published value '
              'was found for the exponent, density and c* bands. Mature-'
              'production scatter: NASA SP-8039 Table III, p. 53.'),
}

# ---------------------------------------------------------------------------
# Yalıtım (liner) varsayılanları — TEK tanım noktası. Kullanıcı formdan
# liner_thickness / liner_density gönderirse _apply_overrides ezer.
# EPDM / silika-fenolik sınıfı yalıtım için literatür bandı.
# Kaynak: NASA SP-8093 "Solid Rocket Motor Internal Insulation";
# Sutton & Biblarz 9. baskı Böl. 12.
# ---------------------------------------------------------------------------
SOLID_INSULATION = {
    'thickness_m': 0.002,               # 2 mm tipik amatör/küçük motor lineri
    'density_kg_m3': 1200.0,            # kg/m³ (EPDM)
    'thermal_conductivity_w_mk': 0.30,  # W/m·K (EPDM/fenolik bandı)
    'specific_heat_j_kgk': 1500.0,      # J/kg·K
}

#: Isıl koruma katmanlarının RADYAL SIRASI (içten dışa) — TEK tanım noktası.
#: ÖH D24 (OH-D23-10). Bu sıra hem halka kütlelerini (_insulation_liner_masses)
#: hem de CAD panelinin yayımladığı beyanı (_design_insulation_system) besler;
#: iki yerde iki farklı sıra yazılamaz.
#:
#: KAYNAK — sıra bir tercih değil, yapım sırasının kendisidir:
#:   * NASA SP-8093 "Solid Rocket Motor Internal Insulation" (Aralık 1976):
#:     iç yalıtım, KASA İÇ YÜZEYİ ile İTİCİ arasına konan ısı bariyeri
#:     katmanıdır (amacı kasanın yapısal bütünlüğünü tehlikeye atan
#:     sıcaklıklara çıkmasını önlemektir).
#:   * Liner, yalıtımın ÜZERİNE sürülen ve grain'i yalıtıma — yalıtımsız
#:     bölgelerde doğrudan kasaya — BAĞLAYAN elastomer bağ katmanıdır
#:     (Sutton & Biblarz, Rocket Propulsion Elements, 9. baskı, Böl. 12;
#:     aynı tanım US4821511A "Liner for a solid propellant rocket motor"
#:     patentinin giriş bölümünde de birebir yazılıdır).
#: Yani içten dışa: grain → liner → yalıtım → kasa. Liner grain'e YAPIŞIKTIR;
#: yalıtımın dışında duran bir halka olamaz, çünkü o konumda bağlayacağı
#: yüzeye değmez.
SOLID_THERMAL_LAYER_ORDER = ('propellant_grain', 'liner', 'insulation', 'case')

#: Yukarıdaki sıranın kullanıcıya dönük gerekçesi (İngilizce ürün metni).
SOLID_THERMAL_LAYER_ORDER_BASIS = (
    'Radially outward from the port: propellant grain, liner, insulation, '
    'case. The liner is the elastomeric bonding layer applied over the '
    'insulation to bond the grain to it, so it is the inner of the two rings; '
    'the insulation is the heat barrier between the case inner surface and '
    'the propellant (NASA SP-8093, Solid Rocket Motor Internal Insulation, '
    '1976; Sutton & Biblarz, Rocket Propulsion Elements, 9th ed., Ch. 12). '
    'Both rings are built from the same single material record '
    '(_insulation_density), so the order moves mass between the insulation '
    'and liner line items but leaves their sum - and therefore the dry mass '
    '- unchanged.')

#: Kapak astarı malzemeleri — TEK tanım noktası, İSTASYONA GÖRE AYRI.
#: Beyan edilmiş TASARIM SEÇİMİdir, çözülmüş seçim değildir; motor malzemeyi
#: optimize etmez. thermal_protection.ABLATIVE_MATERIALS anahtarı olmalıdır.
#:
#: Neden iki ayrı malzeme (v2.6.27 fizik denetimi): gerçek katı motorda
#: kubbe/kapak yalıtımı ELASTOMERdir (NASA SP-8093 "Solid Rocket Motor
#: Internal Insulation": NBR, SBR, butil, EPDM, silikon, üretan aileleri);
#: karbon/silika-fenolik ise NOZUL astarı malzemesidir (SP-8115 "Solid
#: Rocket Motor Nozzles" kapsamı). Eski tek sabit 'carbon_phenolic' kapakta
#: yanlış malzeme ailesiydi.
SOLID_FWD_CLOSURE_LINER_MATERIAL = 'epdm'
SOLID_NOZZLE_ENTRY_LINER_MATERIAL = 'silica_phenolic'

# Dış yüzey ısı kaybı (soğutmasız kasa) — lumped kasa sıcaklığı çözümünde.
SOLID_THERMAL = {
    'ambient_temperature_k': 298.0,
    'external_convection_w_m2k': 10.0,   # durgun hava, doğal konveksiyon
    'external_emissivity': 0.30,         # boyasız/oksitli çelik dış yüzey
    # v2.6.27: merkezî tanımdan (hrma/constants.py) — yerel kopya kalktı.
    'stefan_boltzmann': STEFAN_BOLTZMANN,
    # Bartz duvar sıcaklığı referansı (ısı akısı zayıf duyarlı — bkz.
    # _calculate_heat_flux docstring).
    'bartz_reference_wall_temp_k': 700.0,
    # Malzeme kaydı okunamazsa kullanılan çelik yedekleri
    'fallback_case_specific_heat_j_kgk': 460.0,
    'fallback_case_elastic_modulus_pa': 200e9,
    # Geçici kasa ısınması için açık Euler adım sayısı
    'transient_steps': 2000,
}

# Star / wagon-wheel / finocyl / slotted iç profilinin keskin köşesinde gerilme
# yığılma katsayısı. Köşe yarıçapı çözülmediği için tipik bir ALT sınırdır ve
# grain sonucunda 'stress_concentration_factor' olarak açıkça raporlanır.
GRAIN_STRESS_CONCENTRATION = {
    'star': 2.0,
    'wagon_wheel': 2.0,
    # Radyal kanatçık/yarık dibi star vadisiyle aynı sınıf keskin iç köşedir.
    'finocyl': 2.0,
    'slotted': 2.0,
}

# ---------------------------------------------------------------------------
# Erozif yanma eşiği ve referans akısı — indirgenmiş Lenoir-Robillard
# vekilinin TEK tanım noktası (bkz. _erosive_factor):
#     G <= G_esik            -> r/r0 = 1 (erozif yanma yok)
#     G >  G_esik            -> r/r0 = 1 + k * ((G-G_esik)/G_ref)^m * (D/Dc)^-0.2
# Eşik davranışı Summerfield tipidir; sayı bir MODEL SABİTİDİR, motordan
# hesaplanmaz. Kaynak: Sutton & Biblarz 9. baskı Böl. 12 (erozif yanma).
# v2.6.26: aynı 100.0 hem çözücüde hem rapor bloğunda AYRI AYRI yazılıydı.
# Biri değiştirilse rapor sessizce çözücüden başka bir eşik gösterirdi.
# ---------------------------------------------------------------------------
EROSIVE_THRESHOLD_KG_M2S = 100.0
EROSIVE_REFERENCE_FLUX_KG_M2S = 400.0

# ---------------------------------------------------------------------------
# Desteklenen grain tipleri — TEK tanım noktası.
# 2026-07-19 denetim bulgusu: calculate_burn_area yalnız bates/star/wagon_wheel
# dallarını tanıyordu, GERİ KALAN HER tip (arayüzdeki 'finocyl' ve 'slotted'
# dahil) etiketsiz `else` dalına düşüp SESSİZCE uç-yanmalı (end burner) olarak
# hesaplanıyordu. Ölçüm: finocyl/slotted/end_burner/uydurma-tip dördü de
# A(w) = π·r_o² = 0.007854 m² sabit eğrisini veriyordu; üstelik yakıt hacmi
# annulus dalından geldiği için yüklü yakıtın %92'si yanmadan sonlanıyordu
# (burned 0.497 kg / available 6.468 kg). Artık tanınmayan tip sessizce
# kabul edilmez.
SUPPORTED_GRAIN_TYPES = (
    'bates', 'star', 'wagon_wheel', 'finocyl', 'slotted', 'end_burner',
)

#: Kesiti KAPALI FORMLA verilemeyen, yanma alanı shapely ofsetiyle bulunan
#: grain tipleri — TEK tanım noktası (ÖH D17, P2B2-04). Bu tiplerde tükeniş
#: geometriktir: yanma alanı, radyal et bitmeden ÖNCE sıfırlanabilir, bu
#: yüzden hem çözücünün tarama sınırı hem de "tüketilebilir web" paydası bu
#: kümeye göre ayrışır. Küme iki yerde iki farklı liste olamaz.
SOLID_POLYGON_GRAIN_TYPES = ('star', 'wagon_wheel', 'finocyl', 'slotted')

# V301/K-B (KT-08) — WAGON WHEEL GEOMETRİSİ (TEK TANIM NOKTASI)
# Motorun kullandığı geometri: merkez delik + N çevre delik, HEPSİ AYNI çapta,
# çevre delikler bölüm dairesi üzerinde eşit aralıklı. Kullanıcı vermezse
# eski sabit geometri uygulanır ve BEYAN edilir: N = 6, delik çapı = çekirdek
# çapının yarısı, bölüm dairesi çapı = tane dış çapının yarısı. Bu üç sayı
# HRMA seçimidir — literatür değeri yok (kaynaklı bir wagon-wheel
# "standardı" bulunmadı). Delik sayısı bandı [3, 12] de HRMA seçimidir
# (star uç sayısı bandıyla aynı); geometrik tutarlılık ayrıca sınanır.
SOLID_WAGON_WHEEL_DEFAULTS = {
    'hole_count': 6,
    'hole_diameter_over_core': 0.5,
    'pitch_diameter_over_grain': 0.5,
    'hole_count_range': (3, 12),
    'basis': ('HRMA selection - no literature value: 6 outer holes, hole '
              'diameter = core diameter / 2, pitch circle diameter = grain '
              'outer diameter / 2 (the solver geometry before v3.0.5)'),
}

# Finocyl (FIN-O-CYLinder): silindirik port + ondan radyal uzanan N kanatçık
# yuvası. Kanatçıklar grain'in yalnız bir BÖLÜMÜNÜ kaplar (klasik olarak arka
# uç); geri kalan boy düz silindirik porttur. Nötre yakın davranışın kaynağı
# bu ikili yapıdır: kanatçıklı kesitin yanan çevresi kanatçıklar tükendikçe
# DÜŞER, düz silindirik kesitinki r arttıkça YÜKSELİR.
# Kaynak: Sutton & Biblarz 9. baskı Böl. 12 (grain konfigürasyonları);
# NASA SP-8076 "Solid Propellant Grain Design and Internal Ballistics"
# (Mart 1972) §2.2.2.1.11 "Finocyl", s. 42, Şekil 18. (KU-K2, 6 Eki 2026:
# künye eskiden bu başlığı SP-8064'e veriyordu; SP-8064'ün başlığı "Solid
# Propellant Selection and Characterization"dır, Haziran 1971 — iki kapak
# OCR metninden doğrulandı.)
FINOCYL_GRAIN = {
    'fin_count': 4,               # adet
    'fin_width_m': 0.008,         # m — kanatçık yuvasının çevresel kalınlığı
    'fin_depth_m': 0.020,         # m — porttan dışa radyal derinlik
    'finned_length_fraction': 0.40,  # kanatçıklı boyun toplam boya oranı
    # Geometrik kırpma sınırları (fiziksel olarak imkânsız girdiyi engeller)
    'max_depth_fraction': 0.85,   # derinlik <= 0.85·(r_dış − r_port)
    'max_width_fraction': 0.50,   # genişlik <= 0.50·(2π·r_port/N)
    'count_range': (2, 12),
    'width_range_mm': (0.5, 60.0),
    'depth_range_mm': (1.0, 200.0),
    'fraction_range': (0.05, 1.0),
}

# Slotted (yarıklı boru): silindirik port + TÜM boy boyunca uzanan eksenel
# yarıklar. Kanatçıktan farkı yarıkların boyun tamamını kat etmesi ve tipik
# olarak daha dar/derin olmasıdır; bu yüzden başlangıç yanma alanı yüksek,
# yarıklar tükendikten sonra profil silindirik porta döner.
SLOTTED_GRAIN = {
    'slot_count': 6,
    'slot_width_m': 0.004,
    'slot_depth_m': 0.025,
    'max_depth_fraction': 0.85,
    'max_width_fraction': 0.50,
    'count_range': (2, 16),
    'width_range_mm': (0.5, 60.0),
    'depth_range_mm': (1.0, 200.0),
}

# ---------------------------------------------------------------------------
# Yakıt (grain) mekanik özellikleri — grain gerilme/gerinim analizinin TEK
# tanım noktası. Katı yakıt viskoelastik bir elastomerdir: modül metallerin
# ~10 000'de biri, Poisson oranı sıkıştırılamaza (0.5) çok yakın, termal
# genleşme metalin ~8 katıdır. Değerler literatür bandının ortasıdır ve
# 'source' alanında beyan edilir; CEA/laboratuvar ölçümü DEĞİLDİR.
# Kaynak: NASA SP-8073 "Solid Propellant Grain Structural Integrity Analysis";
# Sutton & Biblarz 9. baskı Böl. 12 (mekanik özellikler tablosu).
# ---------------------------------------------------------------------------
_HTPB_GRAIN_MECHANICS = {
    'elastic_modulus_pa': 6.0e6,      # Pa (HTPB kompozit, oda sıcaklığı)
    'poisson_ratio': 0.4995,          # neredeyse sıkıştırılamaz
    'thermal_expansion_1k': 1.0e-4,   # 1/K
    'cure_temperature_k': 333.0,      # 60 C kürleme
    'strain_capability': 0.35,        # kopma uzaması (birim, 0-1)
    'source': 'NASA SP-8073 / Sutton & Biblarz Ch.12 typical HTPB composite band',
}
_SUGAR_GRAIN_MECHANICS = {
    # Dökme şeker yakıtı gevrek bir katıdır: modül çok daha yüksek, uzama
    # kabiliyeti çok daha düşük. Bant: Nakka (nakka-rocketry.net) malzeme
    # notları + genel polimer/tuz kompozit verisi.
    'elastic_modulus_pa': 1.0e9,
    'poisson_ratio': 0.35,
    'thermal_expansion_1k': 8.0e-5,
    'cure_temperature_k': 398.0,      # ~125 C eriyik dökümden soğuma referansı
    'strain_capability': 0.02,        # kopma uzaması bandı %2-5, alt (konservatif) uç
    'source': ('Nakka amateur sugar-propellant material notes (brittle cast '
               'band); strain capability band 2-5%, the conservative low end '
               'is used'),
}
SOLID_GRAIN_MECHANICS = {
    'apcp': _HTPB_GRAIN_MECHANICS,
    'double_base': {
        'elastic_modulus_pa': 3.0e8,
        'poisson_ratio': 0.40,
        'thermal_expansion_1k': 9.0e-5,
        'cure_temperature_k': 333.0,
        'strain_capability': 0.05,
        'source': 'Sutton & Biblarz Ch.12 double-base mechanical property band',
    },
    'sugar': _SUGAR_GRAIN_MECHANICS,
    'knsu': _SUGAR_GRAIN_MECHANICS,
    # v2.6.26: KNDX (KNO3/dekstroz) ve KNSB (KNO3/sorbitol) merkezi katalogta
    # 'sugar' ailesindedir — aynı oksitleyici oranı, aynı eriyik-döküm üretimi,
    # aynı gevrek katı davranışı. Bu iki formülasyona ÖZGÜ yayımlanmış modül /
    # Poisson / uzama verisi bulunamadığı için kayıt UYDURULMADI; şeker ailesi
    # kaydına TAKMA AD olarak bağlıdır (devralma _grain_mechanics içinde
    # 'source' ve 'inherited_from' alanlarıyla beyan edilir).
    # ÖNCESİ: bu iki anahtar sözlükte YOKTU ve motor sessizce HTPB kompozit
    # kaydına düşüyordu — KNDX grainine 6 MPa modül / %35 uzama atanıyor,
    # gerinim emniyet katsayısı 11.7 (risk 'Low') çıkıyordu; doğru şeker
    # kaydıyla 0.91 (risk 'High').
    'kndx': _SUGAR_GRAIN_MECHANICS,
    'knsb': _SUGAR_GRAIN_MECHANICS,
    'kner': _SUGAR_GRAIN_MECHANICS,
    'black_powder': {
        # Preslenmiş siyah barut gevrek ve zayıftır.
        'elastic_modulus_pa': 2.0e9,
        'poisson_ratio': 0.30,
        'thermal_expansion_1k': 5.0e-5,
        'cure_temperature_k': 298.0,   # kürleme yok, presleme sıcaklığı ortam
        'strain_capability': 0.005,
        'source': 'Pressed black powder brittle-solid estimate (order of magnitude)',
    },
}
SOLID_GRAIN_MECHANICS_DEFAULT = _HTPB_GRAIN_MECHANICS

# V301/S1-6 (28 Eki) — TANE YERLEŞİMİ. Gerinim çözümü yalnız gövdeye
# yapıştırılmış (case-bonded) taneyi biliyordu ve bunu kendisi beyan ediyordu
# ("this solver has no input for that configuration"). ÖLÇÜLDÜ (örnek KNDX
# BATES, 40 bar): port gerinimi %2,209'un %1,833'ü kürleme/soğuma
# büzülmesinin gövdeyle KISITLANMASINDAN geliyordu; kalıpta dökülüp gövdeye
# takılan tanede bu kısıt yoktur. Kaynak: NASA SP-8073 (1973) §1 "cartridge-
# loaded grains ... the propellant is not cast and cured within the case but
# rather in a mold outside the case ... Frequently they are left free-
# standing, i.e., bonded only at the ends" ve §2.5.3 "gas pressures can be
# exerted between the case and the grain".
GRAIN_SUPPORT_CASE_BONDED = 'case_bonded'
GRAIN_SUPPORT_CARTRIDGE = 'cartridge_loaded'
GRAIN_SUPPORT_OPTIONS = (GRAIN_SUPPORT_CASE_BONDED, GRAIN_SUPPORT_CARTRIDGE)
GRAIN_SUPPORT_DEFAULT = GRAIN_SUPPORT_CASE_BONDED
GRAIN_SUPPORT_BASIS = {
    GRAIN_SUPPORT_CASE_BONDED: (
        'case-bonded grain: cast and cured inside the case and bonded to its '
        'liner. The case restrains the cure/cool-down shrinkage, so the bore '
        'carries that thermal strain in addition to the pressure strain '
        '(plane-strain hollow cylinder, Timoshenko & Goodier; NASA SP-8073).'),
    GRAIN_SUPPORT_CARTRIDGE: (
        'cartridge-loaded grain: cast in a mold or liner outside the case and '
        'inserted, bonded at most at its ends (NASA SP-8073 §1). The case '
        'does not restrain the cure/cool-down shrinkage, so no thermal strain '
        'is carried at the bore. The pressure strain is computed with the '
        'case supporting the grain outer surface (snug fit, no gas between '
        'grain and case): this is the upper bound of the two support states, '
        'because chamber gas reaching the case-grain gap (SP-8073 §2.5.3) '
        'loads the grain almost hydrostatically and lowers the bore strain.'),
}

# ---------------------------------------------------------------------------
# Yoğuşmuş (iki-fazlı) ürün kütle kesirleri — iki-fazlı Isp kaybının TEK
# tanım noktası. Metalize yakıtta Al -> Al2O3 dönüşümü kütleyi 1.8895 kat
# büyütür (101.96 g/mol Al2O3 / 2 x 26.98 g/mol Al).
# Kaynak: Sutton & Biblarz 9. baskı sec. 3.5 (particle/two-phase flow);
# yakıt bileşimleri hrma/data/propellants_db.py kayıtlarındaki formülasyondan.
# ---------------------------------------------------------------------------
AL_TO_AL2O3_MASS_RATIO = 101.96 / (2 * 26.98)

SOLID_CONDENSED_MASS_FRACTION = {
    'apcp': 0.18 * AL_TO_AL2O3_MASS_RATIO,   # ~%18 Al -> ~0.340 Al2O3
    'double_base': 0.0,                      # dumansız, tek faz
    # KNO3/şeker: yoğuşmuş K2CO3 baskın. NASA CEA (KNO3/sakaroz 65/35,
    # 68.9 bar) yoğuşmuş faz kütle kesri ~0.44.
    'sugar': 0.44,
    'knsu': 0.44,
    # KNDX/KNSB/KNER: aynı KN-şeker ailesi, aynı KNO3 %65 oksitleyici oranı.
    # Yoğuşmuş faz kütlece K2CO3 (potasyum) baskındır ve potasyum oranı
    # oksitleyiciden gelir; yakıt bileşeninin izomer/oligomer farkı bu kesri
    # birinci mertebede değiştirmez. Bu formülasyonlar için AYRI bir CEA koşusu
    # yapılmadı — sakaroz değeri devralınır ve rapor 'inherited_from' ile bunu
    # açıkça söyler (uydurma değer yazılmadı).
    'kndx': 0.44,
    'knsb': 0.44,
    'kner': 0.44,
    # Siyah barut kütlesinin yarıdan fazlası katı kalıntıdır (K2CO3, K2S,
    # K2SO4) — klasik iç balistik verisi.
    'black_powder': 0.55,
}
# eta_2phase = 1 - k * X_p birinci derece modeli (nozzle_design ile aynı k).
TWO_PHASE_LOSS_COEFF = 0.12

# ---------------------------------------------------------------------------
# ÖH D32 (OH-D31-17) — İKİ-FAZ DÜZELTMESİNİN DURUMU: TEK TANIM NOKTASI.
#
# Berke/Astra hükmü (15 Eyl 2026, docs/scofield/raw/OH/D32/oturum-devri/
# berke_kararlari_2026-09-15.md §1): kaynaksız 0,98 form sabitinin sökülmesi
# DOĞRUDUR, ama "çözücünün kendi hesapladığı iki-faz kaybı varsayılan olarak
# uygulansın mı" kararı KANITIN ÖNÜNE GEÇMEZ ve Berke'ye aittir. Ara dönemde
# üç şey zorunludur:
#   1) "iki-faz düzeltmesi doğrulanmamış" durumu API/panel/PDF'e TAŞINIR,
#   2) bu sayıdan DOĞRULANMIŞ performans hükmü üretilmez,
#   3) çözücü varsayılanı (kullanıcı çarpanı yoksa eta = 1,0) DEĞİŞMEZ.
#
# ÖLÇÜLDÜ (docs/scofield/raw/OH/D32/kati/a1/once.json, zincir_once.json;
# varsayılan APCP 5 kN / 5 s / 50 bar):
#   * doğrusal teşhis  = 100·K·X_p                     = %4,081423
#   * modül (boyutlu)  = 100·K·X_p·g(x), g = 2x/(1+x)  = %4,789293
#     (x = (d43/D43_REF)^2·(D_THROAT_REF/Dt); özdeşlik sapması 0,0)
#   * üç yol Isp_SL: 0,98 kullanıcı 243,6236 s | boş 248,5791 s |
#     aday model (eta = 0,952107) 236,7113 s
# Yani yayımlanan Isp ŞU AN hiçbir iki-faz düzeltmesi TAŞIMIYOR ve bu
# durumun kendisi bir hüküm değil, bir EKSİKLİK beyanıdır.
# ---------------------------------------------------------------------------
#: Kullanıcı çarpanı yok, yakıtın yoğuşmuş fazı var: Isp'ye hiçbir iki-faz
#: düzeltmesi uygulanmadı ve uygulanacak model henüz kanıtlanmadı.
TWO_PHASE_STATUS_NOT_APPLIED = 'not_applied_unverified'
#: Kullanıcı bir çarpan verdi: uygulanan sayı KULLANICININ, doğrulanmış değil.
TWO_PHASE_STATUS_USER = 'user_supplied_unvalidated'
#: Yoğuşmuş faz kesri tam sıfır: kaybın limiti tam olarak sıfırdır
#: (100·K·0·g(x) = 0, ÖLÇÜLDÜ: zincir_once.json M2 beta_0_kayip_0 = 0,0).
TWO_PHASE_STATUS_ZERO = 'not_required_zero_condensed_phase'
#: Yakıt için yoğuşmuş faz kesri KAZANILAMADI: sayı yayımlanmaz, durum da
#: "doğrulandı" diyemez.
TWO_PHASE_STATUS_NO_FRACTION = 'not_evaluated_no_condensed_fraction'
#: Kesir, K çapasının yayımlanmış veri penceresinin DIŞINDA (SP-8039 Fig. 8
#: 0-40 %wt). ÖLÇÜLDÜ: knsu/kndx/knsb/sugar X_p = 0,44 ve black_powder
#: X_p = 0,55 için hrma.analysis.two_phase_loss SAYI ÜRETMİYOR
#: (OUT_OF_PUBLISHED_RANGE) ama doğrusal teşhis %5,28 / %6,60 yayımlıyor.
TWO_PHASE_STATUS_OUT_OF_ENVELOPE = 'outside_anchor_envelope_unverified'


def _two_phase_anchor_envelope():
    """K çapasının yoğuşmuş faz kesri penceresi — TEK KAYNAK.

    Pencere ``hrma.analysis.two_phase_loss.VALIDITY_RANGES`` içinde
    tanımlıdır (NASA SP-8039 Fig. 8 veri penceresi); burada İKİNCİ bir sayı
    yazılmaz. Okunamazsa ``(None, None)`` döner ve çağıran taraf pencereyi
    "bilinmiyor" diye beyan eder — sessizce "içinde" varsayılmaz.
    """
    try:
        from hrma.analysis.two_phase_loss import VALIDITY_RANGES
        kayit = VALIDITY_RANGES['condensed_mass_fraction']
        alt, ust = kayit['range']
        return (float(alt), float(ust)), str(kayit['source'])
    except Exception:
        return None, None


def _two_phase_correction_state(x_particle, eta_user):
    """(durum, doğrulandı_mı, künye) — iki-faz düzeltmesinin DURUMU.

    Durum çözücünün GERÇEK haline bakılarak türetilir; hiçbir dalda
    "doğrulandı" varsayılmaz. Dönen sözlük hem ``_isp_loss_breakdown``
    hem ``_two_phase_loss_report`` hem de PDF uyarı kanalı tarafından
    AYNEN kullanılır (tek tanım noktası).
    """
    pencere, pencere_kaynak = _two_phase_anchor_envelope()
    eta = 1.0 if eta_user is None else float(eta_user)
    kullanici_var = abs(eta - 1.0) > 1e-12
    xp = None if x_particle is None else float(x_particle)
    pencere_metni = (
        f'{pencere[0]:.3g}-{pencere[1]:.3g} ({pencere_kaynak})'
        if pencere else 'UNKNOWN - the published data window could not be '
                        'read from hrma.analysis.two_phase_loss')
    ortak = (
        'The delivered Isp published by this run carries NO verified '
        'two-phase (particle-lag) correction. The linear diagnostic '
        f'eta_2phase = 1 - {TWO_PHASE_LOSS_COEFF:.2f}*X_p and the '
        'size-corrected estimate in results.two_phase_loss are BOTH '
        'diagnostics (applied_to_isp = false); which of them, if either, '
        'should be applied by default is an OPEN decision. Do not derive a '
        'verified delivered-performance claim from this Isp. Condensed-phase '
        f'anchor window for X_p: {pencere_metni}.')

    if kullanici_var:
        return {
            'two_phase_correction_status': TWO_PHASE_STATUS_USER,
            'two_phase_correction_verified': False,
            'two_phase_correction_status_basis': (
                f'A user two-phase efficiency multiplier eta = {eta:.6f} was '
                'supplied and IS applied to the thrust coefficient. It is a '
                'user input, not a validated model result: the solver does '
                'not check it against any published correlation. ' + ortak),
        }
    if xp is None:
        return {
            'two_phase_correction_status': TWO_PHASE_STATUS_NO_FRACTION,
            'two_phase_correction_verified': False,
            'two_phase_correction_status_basis': (
                'No condensed-phase mass fraction could be established for '
                'this propellant, so neither the linear diagnostic nor the '
                'module estimate is earned and no two-phase correction is '
                'applied. ' + ortak),
        }
    if xp == 0.0:
        return {
            'two_phase_correction_status': TWO_PHASE_STATUS_ZERO,
            'two_phase_correction_verified': True,
            'two_phase_correction_status_basis': (
                'The condensed-phase mass fraction of this propellant is '
                'exactly zero, so the particle-lag loss is exactly zero in '
                f'both models (100*{TWO_PHASE_LOSS_COEFF:.2f}*0 = 0 and '
                '100*K*0*g(x) = 0 for every x). No correction is needed and '
                'none is applied; this is the ONLY state in which the '
                'absence of a two-phase correction is itself verified.'),
        }
    if pencere is not None and not (pencere[0] <= xp <= pencere[1]):
        return {
            'two_phase_correction_status': TWO_PHASE_STATUS_OUT_OF_ENVELOPE,
            'two_phase_correction_verified': False,
            'two_phase_correction_status_basis': (
                f'X_p = {xp:.3f} lies OUTSIDE the published data window of '
                f'the K anchor ({pencere_metni}); hrma.analysis.two_phase_'
                'loss refuses to produce a loss number for this state '
                '(OUT_OF_PUBLISHED_RANGE). The K anchors are '
                'aluminium-oxide anchors (AFRPL aluminium rule of thumb; '
                'NASA SP-8039 Fig. 8 metal-oxide family) and this '
                'propellant\'s condensed phase is not necessarily Al2O3, so '
                f'the linear diagnostic 100*{TWO_PHASE_LOSS_COEFF:.2f}*X_p '
                'would be a pure extrapolation here. It is therefore NOT '
                'published: detailed_analysis.theoretical_vs_actual_isp.'
                'two_phase_losses is null for this propellant and carries '
                'two_phase_losses_withheld_reason = '
                '"outside_anchor_envelope". No delivered-Isp number changes '
                'because of this: the diagnostic was never applied to the '
                'thrust coefficient (two_phase_losses_applied = false). '
                + ortak),
        }
    return {
        'two_phase_correction_status': TWO_PHASE_STATUS_NOT_APPLIED,
        'two_phase_correction_verified': False,
        'two_phase_correction_status_basis': (
            f'X_p = {xp:.3f} > 0 and no user multiplier was supplied, so the '
            'thrust coefficient carries NO two-phase factor at all '
            '(two_phase_efficiency_applied = 1.0) even though the solver\'s '
            'own models estimate a non-zero loss for this state. ' + ortak),
    }

# ---------------------------------------------------------------------------
# Ateşleyici boyutlandırması — TEK tanım noktası (bkz. _design_igniter_system).
#
# Şarj kütlesi serbest hacim basınçlandırma ölçütünden gelir (NASA SP-8051,
# "Solid Rocket Motor Igniters"): ateşleyici, kamaranın SERBEST hacmini hedef
# ateşleme basıncına çıkaracak GAZI üretmelidir. Şarjın gaz özellikleri
# (molekül ağırlığı, alev sıcaklığı, yoğunluk) merkezi katalogtan, yoğuşmuş
# faz kesri SOLID_CONDENSED_MASS_FRACTION'dan okunur — burada YENİ bir sayı
# tanımlanmaz.
#
# 'pressure_fraction' bir FİZİK SABİTİ DEĞİL, tasarım seçimidir: ateşleyicinin
# kamarayı çıkardığı basıncın çalışma basıncına oranı. Formdan verilebilir
# (igniter_pressure_fraction); verilmezse buradaki varsayılan kullanılır ve
# çıktıda "design choice" olarak açıkça beyan edilir.
# ---------------------------------------------------------------------------
SOLID_IGNITER = {
    'charge_record': 'black_powder',      # merkezi katalog kaydı (şarj)
    'pressure_fraction_default': 0.15,    # P_ateş / P_c — tasarım seçimi
    'pressure_fraction_range': (0.02, 0.50),
}

# ---------------------------------------------------------------------------
# Tasarım noktası boyutlandırma sınırları — TEK tanım noktası.
# Çağıran hedef ortalama itki (N) ve/veya yanma süresi (s) verdiğinde grain
# geometrisi bu sınırlar altında çözülür; boyutlandırma, uygunluk kontrolü ve
# testler aynı sözlükten okur (magic number yasağı).
# ---------------------------------------------------------------------------
SOLID_DESIGN_POINT = {
    'tolerance': 0.10,            # kabul edilen bağıl hata (itki ve süre)
    'max_iterations': 40,         # dış sabit-nokta tur sayısı
    'max_step_ratio': 2.0,        # tur başına en büyük hedef ölçekleme
    # Sönümleme üssü: düzeltme oranı ratio**relaxation olarak uygulanır.
    # 1.0 (sönümsüz) iki-çevrimli salınım üretiyordu (10 kN/5 s BATES),
    # 0.6 aynı sabit noktaya monoton yaklaşıyor.
    'relaxation': 0.6,
    'max_segments': 20,           # BATES segment üst sınırı
    'port_to_throat_min': 2.0,    # A_port/A_t alt sınırı (boğulma emniyeti)
    'port_to_throat_target': 4.0, # tercih edilen A_port/A_t
    'mass_flux_warn': 1400.0,     # kg/m²s — erozif yanma uyarı eşiği
    'target_slenderness': 5.0,    # tercih edilen L_toplam/D_oda
    # Boyutlandırmanın FİZİKSEL sınırları. Bunlar form doğrulama sınırları
    # DEĞİLDİR: kısa süreli bir sigara-yanması grain'i 40 mm boyunda olabilir
    # ve bu fiziksel olarak doğrudur (form alt sınırı 50 mm'dir).
    'min_core_diameter': 0.006,   # m
    'min_chamber_diameter': 0.010,  # m
    'max_chamber_diameter': 2.000,  # m
    'min_grain_length': 0.010,    # m
    'max_grain_length': 5.000,    # m
    # BATES orta-web nötr ailesi: L_seg = c_core*r_core + c_web*web
    # dA/dw = 0 koşulu web'in ORTASINDA sağlanır (A(0) = A(W), tepe orta-web).
    # Kaynak (KU-K2, 6 Eki 2026): koşul CEBİRLE türetilir. Uç yüzeyler
    # yanar, dış yüzey inhibe: A(w) = 2π(r_c+w)(L−2w) + 2π(R²−(r_c+w)²);
    # A(0) = A(W), W = R − r_c ⇒ L_seg = 3R + r_c = 4·r_core + 3·web.
    # Eski künye "NASA SP-8064 BATES nötrlük analizi" idi: SP-8064 ve SP-8076
    # OCR tam metninde BATES grain geometrisi/nötrlüğü YOK (SP-8064'te BATES
    # yalnız Şekil 10'da, ona atıf yapan metinde (s. 27) ve kısaltmalar
    # listesinde geçer; geometri ya da nötrlük analizi yok); Sutton 9 ve
    # Mishra metninde de "BATES" adı geçmiyor (metin araması). BATES = AFRPL
    # Ballistic Test and Evaluation System (SP-8039 kaynakçası ref. 109
    # Collins 1965 ve ref. 112 Gale 1962; bu iki belge OKUNMADI).
    'bates_core_factor': 4.0,
    'bates_web_factor': 3.0,
    # Hedef verilirken kabul edilen sınırlar
    'min_target_thrust': 1.0,     # N
    'max_target_thrust': 1e8,     # N
    'min_target_burn_time': 0.05,  # s
    'max_target_burn_time': 600.0,  # s
}


# ---------------------------------------------------------------------------
# Saint-Robert varsayılan katsayıları — BİRİM SÖZLEŞMESİ: r[m/s] = a·P[bar]^n
#
# FİZİK DENETİMİ DÜZELTMESİ (F024, 2026-07-25): kurucunun eski varsayılanı
# a = 0.005 idi. Bu değer 'r[mm/s] = 5.0·P[MPa]^0.35' fitinin MPa TABANLI
# katsayısıdır; motor onu BAR ile değerlendirdiği için yanma hızı tam
# 10^0.35 = 2.2387 kat şişiyordu (r(70 bar) = 22.1 mm/s — gerçek AP/HTPB/Al
# için 9.9 mm/s). Doğru dönüşüm merkezi katalogda zaten vardı:
# propellants_db.mm_mpa_to_m_bar(5.0, 0.35) = 0.0022334 (CLAUDE.md kural 11:
# aynı sayı iki yerde tanımlanmaz — buradaki varsayılan katalogdan OKUNUR).
#
# Kaynak: hrma/data/burn_rate_db.py modül docstring'i (aynı hatayı strand
# adaptöründe tarif ediyor); Sutton & Biblarz, Rocket Propulsion Elements
# 9. baskı, Böl. 12 (AP/HTPB/Al bandı r ≈ 5-13 mm/s @ 1000 psi ≈ 69 bar).
# ---------------------------------------------------------------------------
from hrma.data.propellants_db import (
    PROPELLANTS as _PROPELLANT_CATALOG,
    get_propellant_safe as _get_propellant_safe,
)

DEFAULT_BURN_RATE_A = float(_PROPELLANT_CATALOG['apcp']['burn_rate_a'])
DEFAULT_BURN_RATE_N = float(_PROPELLANT_CATALOG['apcp']['burn_rate_n'])

# Motor yakıt anahtarı -> merkezi katalog kaydı (engine_key alanı üzerinden).
# Kullanıcının girdiği a-n katsayısı bu kayıttan ciddi biçimde sapıyorsa
# uyarı üretilir (F024: form varsayılanı hâlâ MPa tabanlı 0.005 gönderiyor).
_ENGINE_KEY_TO_CATALOG = {
    rec['engine_key']: key
    for key, rec in _PROPELLANT_CATALOG.items()
    if rec.get('engine_key')
}

# Kullanıcının girdiği a katsayısı katalog değerinden bu oranda saparsa
# uyarı üretilir. 1.8, MPa<->bar karışımının bıraktığı 2.24 katlık izi
# yakalayacak ama yakıt partisi saçılmasını (tipik ±%20) susturacak eşiktir.
BURN_RATE_A_MISMATCH_RATIO = 1.8

# Yanma hızı SAYISAL tavanı [m/s]. Bu bir 'fiziksel sınır' DEĞİLDİR (kaynaksız
# iddia; F069) — çözücüyü uçuk girdide (a·P^n taşması) korumak içindir ve
# aşıldığı her koşuda kullanıcıya uyarı olarak bildirilir.
BURN_RATE_NUMERIC_CEILING_MPS = 0.1

# Basınç denge çözücüsünün adım başına yineleme tavanı. Sönümlü sabit-nokta
# yinelemesi (ilk yol) ve onun yerine geçen parantezli ikiye bölme yedeği
# (V301/B6) AYNI tavanı kullanır; yayımlanan 'basis' / 'note' metinleri de
# sayıyı buradan okur (eskiden döngüde ve iki metinde ayrı ayrı '100' yazılıydı).
SOLID_PRESSURE_SOLVER_MAX_ITER = 100

# Akış ayrılması ölçütü (Summerfield): sabit geometrili nozulda aşırı
# genişlemede P_e ≲ 0.4·P_a olduğunda çıkış konisinde ayrılma beklenir ve
# tek boyutlu CF bağıntısı geçerliliğini yitirir.
# Kaynak: Sutton & Biblarz, Rocket Propulsion Elements 9. baskı, Böl. 3 ve 5.
SUMMERFIELD_SEPARATION_RATIO = 0.4

# ---------------------------------------------------------------------------
# Boğaz boyutlandırma taraması (v2.6.27, A1-1)
# ---------------------------------------------------------------------------
# Boğaz alanı ARTIK t=0 yanma alanına göre açılmaz; yanma boyunca ULAŞILAN
# en büyük gereksinime göre açılır (bkz. _design_throat_area). Tarama
# örneklem sayısı, web aralığını grain tiplerinin tepe genişliğine göre
# ayırt edecek kadar sık, geometri taramasının maliyetini de sınırda tutacak
# şekilde seçildi. Tarama grain geometrisiyle anahtarlanıp örnek içinde
# memoize edildiği için tek bir performans koşusunda (13 _design_throat_area
# çağrısı) bir kez ödenir.
#
# YAKINSAMA ÖLÇÜMÜ (D_kamara=100 mm, D_çekirdek=30 mm, L=500 mm, APCP,
# 40 bar; boyutlandırılan boğaz alanının N=800 örnekli değere göre sapması):
#   N =  60  ->  bates %0,002  star %0,022  finocyl %0,020  wagon %0,068
#   N = 100  ->  bates %0,001  star %0,014  finocyl %0,023  wagon %0,038
#   N = 200  ->  bates %0,000  star %0,007  finocyl %0,000  wagon %0,016
# Yani yerel keskinleştirmeyle birlikte N = 100 bile basınç tavanı
# toleransının (%2) iki mertebe altında kalıyor; N = 100 seçildi çünkü
# shapely'li tiplerde tarama maliyeti örnek sayısıyla doğrusaldır (ölçüldü:
# 200 örnek star 44 ms, wagon_wheel 82 ms, slotted 83 ms, finocyl 94 ms).
SOLID_KN_SCAN_SAMPLES = 100

# Kaba taramanın en büyük örneğinin çevresinde yapılan yerel keskinleştirme:
# tepe iki komşu örnek arasında kalırsa kaba adım tepeyi birkaç yüzde
# ıskalayabilir. Her tur aralığı örnek sayısı kadar böler, üç tur sonunda
# web çözünürlüğü kaba adımın ~1/1700'üne iner (yukarıdaki yakınsama
# ölçümünün kaba adımdan neredeyse bağımsız çıkmasının sebebi budur).
SOLID_KN_REFINE_SAMPLES = 12
SOLID_KN_REFINE_ROUNDS = 3

# ---------------------------------------------------------------------------
# ``cad_design`` ŞEMA ADI — TEK KAYNAK (ÖH D18, P15B4-05)
#
# Aynı anahtar üç motor tipinde üç FARKLI şekil taşıyor. Okuyucular hangi
# şekli aldıklarını soramadığı için sessiz yedeğe düşüyorlar. Katı motorun
# yayımladığı şekil bu adla kendini tanıtır; ad bir SÜRÜM taşır, çünkü
# şeklin anahtar kümesi değişirse okuyucunun bunu görmesi gerekir.
SOLID_CAD_DESIGN_SCHEMA = 'hrma.solid.cad_design/1'

# ---------------------------------------------------------------------------
# BOĞAZ BOYUTLANDIRMA ÖLÇÜTÜNÜN REFERANS VAKASI — TEK KAYNAK
# (ÖH D16 / kulvar kati / aşama 2, kalem P2B3-06)
#
# ``_throat_sizing_report`` kullanıcıya, eski (t=0) ölçütünün AYNI referans
# motorda basıncı ne kadar yükselttiğini söyler. O yüzdeler daha önce
# ``basis_text`` düzyazısının İÇİNE elle yazılmıştı ve iki yerde birden
# duruyordu (bir de ``_design_throat_area`` docstring'inin tablosunda).
# ÖLÇÜLDÜ: metin BATES için '+32%' diyordu, aynı vakanın yeniden ölçümü
# +%0,60 verdi — 53 kat. BATES varsayılan grain tipidir, yani varsayılan
# koşuda kullanıcıya giden tek sayı yanlıştı. star/wagon_wheel satırları da
# bayattı (65 -> 70,6 ; 121 -> 112,4). ÖH D18 (Fable-D16 ŞART, P2B3-06):
# bu bayatlama D16 aşama-1'deki plato çarpanı sökümüne (P2B2-14) ATFEDİLİYORDU
# ama o atıf ÖLÇÜLMEMİŞTİ; Fable-D16 denetçisi taban 6fde52b'yi (çarpan
# yerindeyken) yeniden ölçtü ve orada da 70,6 / 112,4 çıktı. Yani sapmanın
# kaynağı P2B2-14 DEĞİL, D16 öncesindeki bir model değişikliğidir; hangisi
# olduğu ölçülmedi ve burada bir sebep İDDİA EDİLMEZ. Kalıcı ders sebepten
# bağımsızdır: düzyazıya gömülü ölçüm sayısı, ölçümle bağı olmadığı için
# sessizce bayatlar.
#
# Sayılar artık BURADA, tek yerde durur; beyan metni ve yapısal
# ``reference_case`` alanı bu sözlükten kurulur. Değerlerin kodun kendi
# davranışıyla uyumlu kaldığını ``tests/test_d16_kati_a2.py`` bekçisi
# referans vakayı ESKİ ölçütle yeniden çözerek her koşuda doğrular; model
# değişip sayılar bayatlarsa bekçi kırmızı olur.
#
# Ölçüm: eski ölçüt A_t = rho_p*Ab(0)*r(Pc)*c*/(Pc*1e5) ile boyutlandırılan
# boğaz ``pin_throat_area`` ile sabitlenip eğri çözülür; tepe basıncının
# tasarım basıncına oranı okunur.
# Kanıt: docs/scofield/raw/OH/D16/kati/a2/{olcum.py,once.json}
SOLID_THROAT_SIZING_REFERENCE = {
    'propellant_type': 'apcp',
    'chamber_diameter_mm': 100.0,
    'core_diameter_mm': 30.0,
    'grain_length_mm': 500.0,
    'chamber_pressure_bar': 40.0,
    # Eski (t=0) ölçütünde ölçülen tepe basıncı artışı [%]
    'peak_over_design_percent': {
        'bates': 0.6,
        'slotted': 7.6,
        'star': 70.6,
        'finocyl': 87.2,
        'wagon_wheel': 112.4,
    },
    # Aynı koşuda F_tepe / F(t=0)
    'peak_over_initial_thrust': {
        'bates': 1.01,
        'slotted': 1.08,
        'star': 1.78,
        'finocyl': 1.96,
        'wagon_wheel': 2.24,
    },
    'measured_on': '2026-09-01',
    'measurement_evidence': 'docs/scofield/raw/OH/D16/kati/a2/olcum.py',
}

# Bekçinin yeniden ölçümü ile yukarıdaki kayıt arasında kabul edilen sapma
# [yüzde puanı / bağıl]. Yuvarlamayı ve çözücü artığını kapsayacak kadar
# gevşek, gerçek bir bayatlamayı (ölçülen 53 kat) yakalayacak kadar dardır.
SOLID_THROAT_SIZING_REFERENCE_TOLERANCE = (0.2, 0.02)

# Tasarım basıncı aşım toleransı [bağıl]. Boğaz maksimum gereksinime göre
# açıldığında denge basıncı tasarım değerini SAYISAL artıklar dışında
# aşamaz; bu eşik aşılırsa kullanıcı uyarılır (warn.solid.pressure_exceeds_
# design). Eşik, basınç sabit-nokta çözücüsünün varsayılan toleransından
# (1e-6) ve tarama çözünürlüğünden kaynaklanan artığı kapsayacak kadar
# gevşek, gerçek bir tasarım aşımını yakalayacak kadar dardır. Eski (t=0)
# ölçütünün ilerleyici taneciklerde ürettiği aşım
# SOLID_THROAT_SIZING_REFERENCE'ta ölçülmüştür (%7,6 - %112,4); BATES'in
# %0,6'sı bu eşiğin ALTINDA kalır, çünkü BATES nötr yanar ve orada aşılacak
# bir tasarım noktası zaten yoktur.
SOLID_DESIGN_PRESSURE_TOLERANCE = 0.02

# ---------------------------------------------------------------------------
# İtki eğrisi BİÇİM sınıflandırması (v2.6.27, B2-1)
# ---------------------------------------------------------------------------
# Eski sınıflandırma yalnız İLK 10 ve SON 10 örneğin ortalamasını
# karşılaştırıyordu; aradaki tepe hesaba HİÇ girmiyordu. ÖLÇÜLDÜ (APCP,
# D_kamara = 100 mm, D_çekirdek = 30 mm, L = 500 mm, 40 bar; eski kod):
#
#   star         'Regressive'  ama itki 3252 N -> 5812 N (x1,79) çıkıp
#                              sonra düşüyor (tepe yanmanın %70'inde)
#   wagon_wheel  'Regressive'  ama 4161 N -> 10458 N (x2,51), tepe %19'da
#   finocyl      'Progressive' ama 2147 N -> 4423 N -> 2690 N (tepe %41'de)
#
# Yani üç grain tipinde de kullanıcıya bildirilen biçim, eğrinin gerçek
# biçimi DEĞİLDİ; tepeyi gören bir sınıf hiç yoktu.
#
# YENİ ÖLÇÜT (Sutton & Biblarz, Rocket Propulsion Elements 9. baskı, Böl. 12
# taksonomisi: progressive / neutral / regressive; bileşik biçimler aynı
# bölümde "progressive-regressive" olarak anılır):
#
#   Pencere : itkinin tepe değerinin TAIL_FRACTION katının üstünde kaldığı
#             ilk ve son örnek arası. Ateşleme yükselişi ve tükeniş kuyruğu
#             biçim kararına karışmasın diye kesilir.
#   Ortalama: ZAMAN AĞIRLIKLI (I_t/t_b) — örnek yerleşimine ve çözücü
#             adımına duyarsız (aynı gerekçe: calculate_performance'ın
#             avg_thrust tanımı).
#   Nötr    : tepe ve dip ortalamadan NEUTRAL_BAND'dan fazla ayrılmıyor
#             (Sutton'ın "yaklaşık sabit" tanımının sayısallaştırılması).
#   Tepeli  : tepe, pencere BAŞLANGIÇ platosunun NEUTRAL_BAND üstündeyse ve
#             tepe pencerenin sonunda değilse -> 'Progressive-Regressive'.
#   Aksi    : uç platolarının karşılaştırması (progressive / regressive).
#
# Eşikler: NEUTRAL_BAND, "nötr grain" için yaygın olarak kullanılan
# ortalamadan ±%10 bandıdır. TAIL_FRACTION, tepe itkinin %5'idir — katı
# motor sertifikasyonunda yanma süresi uçlarının okunduğu eşiğin aynısı
# (NFPA 1125 sınıfı statik ateşleme veri indirgemesi). PEAK_INTERIOR_MAX,
# tepenin "içeride" sayılması için pencerenin en fazla bu kesrinde olması
# gerektiğini söyler; daha geç bir tepe hâlâ TIRMANIYOR demektir ve o eğri
# progresiftir.
SOLID_THRUST_SHAPE_TAIL_FRACTION = 0.05
SOLID_THRUST_SHAPE_NEUTRAL_BAND = 0.10
SOLID_THRUST_SHAPE_EDGE_FRACTION = 0.10
SOLID_THRUST_SHAPE_PEAK_INTERIOR_MAX = 0.85

#: Sınıf adları — TEK tanım noktası (arayüz bu dizeleri metin olarak basar).
SOLID_THRUST_SHAPE_PROGRESSIVE = 'Progressive'
SOLID_THRUST_SHAPE_REGRESSIVE = 'Regressive'
SOLID_THRUST_SHAPE_NEUTRAL = 'Neutral'
SOLID_THRUST_SHAPE_PROGRESSIVE_REGRESSIVE = 'Progressive-Regressive'
#: Örnek sayısı biçim kararına yetmiyorsa sınıf UYDURULMAZ.
SOLID_THRUST_SHAPE_UNDETERMINED = 'Undetermined'

# ---------------------------------------------------------------------------
# Yayımlanan itki eğrisinin örnek tavanı (v2.6.27, B2-3)
# ---------------------------------------------------------------------------
# Çözücü adımı dt = 0.01 s SABİTTİR, yani yayımlanan dizi saniyede 100 nokta
# taşır ve yanma süresiyle sınırsız büyür. ÖLÇÜLDÜ (APCP, D_kamara = 100 mm,
# D_çekirdek = 30 mm, 40 bar; JSON gövdesi):
#
#   bates      L = 500 mm   t_b =  4,86 s ->   487 nokta,   47,2 KB (yanıtın %37)
#   bates      L = 1200 mm  t_b =  6,23 s ->   624 nokta,   59,9 KB (%43)
#   end_burner L = 500 mm   t_b = 61,56 s ->  6157 nokta,  519,4 KB (%87)
#
# ÇÖZÜCÜ ADIMINA DOKUNULMAZ: dt'nin yakınsama gerekçesi kodda yazılı değil ve
# adımı büyütmenin çözümü bozup bozmayacağı SINANMADI. Seyreltme yalnız
# YAYIMLANAN diziye uygulanır; bütün türetilmiş büyüklükler (impuls, ortalama
# itki, kararlılık, biçim, uyarılar) tam çözünürlüklü diziden hesaplanmaya
# devam eder. Aynı desen depoda üç yerde kurulu: WALL_HISTORY_MAX_POINTS,
# port_history, TPS_WALL_HISTORY_MAX_POINTS.
#
# SABİT ADIMLI seyreltme TEPEYİ IŞKALAYABİLİR. Bu yüzden seyreltme kova
# uçlarını (her kovanın en büyük ve en küçük itkisi) korur ve ayrıca kritik
# örnekleri (tepe itki, tepe basınç, ayrılmanın ilk anı, boğulmanın kesildiği
# ilk an, tükeniş) ZORUNLU olarak taşır — bkz. _decimate_curve_indices.
#
# v2.6.27 (B2-4): tavan da algoritma da ARTIK BURADA DEĞİL. Hibrit motorda
# aynı kusur ölçülünce (port 5 mm, t_b = 50 s -> 17 317 nokta / 1,29 MB) iki
# motorun aynı algoritmayı ayrı ayrı yazması gerekecekti; ikisi
# hrma.analysis.curve_sampling'den okur (CLAUDE.md kural 11). Bu ad geriye
# dönük yüzey olarak duruyor: testler ve dış tüketiciler onu okuyor.
# DEĞİŞTİRİLECEKSE ortak modülde değiştirilir, iki motoru birden etkiler.
SOLID_THRUST_CURVE_MAX_POINTS = THRUST_CURVE_MAX_POINTS

# ---------------------------------------------------------------------------
# Boğaz erozyonu (F071, 2026-07-25)
# ---------------------------------------------------------------------------
# Eski davranış: A_t tasarım noktasında bir kez boyutlandırılıp koşu boyunca
# SABİT tutuluyordu ve docstring bunu 'gerçek motorda boğaz rijittir' diye
# gerekçelendiriyordu. Grafit/fenolik boğaz rijit DEĞİLDİR: difüzyon-kontrollü
# oksidasyonla geriler. Depodaki çalışan model transient_ballistics.
# ThroatErosionModel'dir (ṙ = a_ref·(Pc/Pc_ref)^n) — ne katsayısı, ne
# referans basıncı, ne ÜSSÜ burada YENİDEN YAZILIR; hepsi oradan çağrılır
# (CLAUDE.md kural 11: tek tanım noktası). D28/OH-D27-15: bu satır üssü
# '0.8' diye elle yazıyordu ve tek tanım noktası n = 1,0'a taşındığında
# BAYAT kaldı; sayı söküldü, adı bırakıldı.
#
# Çözücü artık her adımda boğaz yarıçapını büyütebiliyor; ancak erozyon
# VARSAYILAN OLARAK KAPALIDIR ve yalnız kullanıcı bir katsayı verdiğinde
# (solid.html 'erosion_factor' alanı, mm/s @ 70 bar) devreye girer. Sebep:
# doğrulama korelasyonu (docs/correlation_report) rijit boğaz varsayımıyla
# kalibre edilmiştir; varsayılanı sessizce değiştirmek o çapaları kaydırırdı.
# Erozyonun ihmal edilemeyeceği motorlarda (uzun yanma + küçük boğaz)
# varsayımın kendisi artık UYARI olarak bildirilir — sessiz kabul yok.
#
# Kaynak: Thakre, P. & Yang, V., 'Chemical Erosion of Carbon-Carbon/Graphite
# Nozzles in Solid-Propellant Rocket Motors', J. Propulsion and Power 24(4),
# 2008, s. 822-833 (DOI 10.2514/1.34946) — erozyon yasasının üssünün ve
# grafit bandının ortak kaynağı; Geisler'in bandı bu makalenin Tablo 8'inden
# aktarılmıştır ve yayım yeri JANNAF'tır.
#
# D28/OH-D27-15 KÜNYE DÜZELTMESİ — bu blok üç hata taşıyordu:
#   (a) makaleye Thakre'nin DOKTORA TEZİNİN başlığı veriliyordu (refrakter
#       metal lüleler; Penn State 2008) — makalenin başlığı yukarıdakidir;
#   (b) Geisler'in yayım yeri 'AIAA' deniyordu — JANNAF'tır (aynı makalenin
#       kaynakça [6]'sı);
#   (c) bandın SAYISI ('0.05-0.25 mm/s') burada İKİNCİ KEZ yazılıydı ve tek
#       tanım noktası D27'de ölçülen banda (Tablo 8) taşındığında bayat
#       kaldı. Sayı söküldü: bandın tek tanım noktası
#       transient_ballistics.GRAPHITE_A_REF_BAND_CITATION'dır ve künyesiyle
#       birlikte oradan okunur. Bartz 1957 (h_g ∝ Pc^0,8) yalnız TAŞINIM
#       ucunun kaynağıdır, erozyon yasasının üssü değildir.

# Boğaz alanı bu kesirden fazla büyürse (veya rijit varsayımda büyüyecek
# olsaydı) kullanıcı uyarılır. %5 alan artışı ~%5 basınç düşüşü demektir.
THROAT_EROSION_SIGNIFICANT_AREA_GROWTH = 0.05

# Kullanıcı katsayısı için kabul aralığı [mm/s @ 70 bar]. Üst uç, ateşleme
# testlerinde görülen en hızlı gerilemenin (tungsten/fenolik dâhil) üzerinde
# tutulan sayısal koruma sınırıdır; 0 = erozyon yok (rijit boğaz).
THROAT_EROSION_A_REF_MAX_MM_S = 5.0

# Lüle çıkış çapının MUTLAK bildirim sınırı [m]. Bu sayı bir tasarım kısıtı
# değildir: bağıntıların kurulduğu ölçek aralığının üst ucunu işaretler
# (i18n metni de bunu söyler). Motorun kendi gövde zarfını aşma kapısı AYRI
# bir ölçüttür (ÖH D26 a2 / OH-D25-07) ve motor çapına GÖRELİDİR.
SOLID_EXIT_DIAMETER_ABSOLUTE_LIMIT_M = 1.0


def _throat_erosion_pc_ref_bar():
    """Erozyon yasasının referans basıncı [bar] — sayı BURADA YAZILMAZ.

    ÖH D26 a2 (Doktrin 4). Bu dosyada '70 bar' iki ayrı kullanıcı metninde
    elle yazılıydı (``_throat_erosion_report``'un ``input_field``ı ve
    yukarıdaki aralık yorumu); tanımın tek yeri
    ``transient_ballistics.ThroatErosionModel``in ``pc_ref_bar``
    varsayılanıdır ve buradan OKUNUR. Model referansını değiştirirse
    kullanıcıya gösterilen birim etiketi kendiliğinden onunla gelir.
    """
    import inspect
    from hrma.analysis.transient_ballistics import ThroatErosionModel
    return float(inspect.signature(ThroatErosionModel.__init__)
                 .parameters['pc_ref_bar'].default)


# Nozul malzemesi adı -> transient_ballistics erozyon tablosu anahtarı.
# solid.html üç seçenek sunuyor (graphite/phenolic/tungsten); tabloda yalnız
# grafit ve C-C için yayımlanmış bant var, diğerleri için katsayı UYDURULMAZ.
#: Yakıt tablosunun ``nozzle_efficiency`` sütunu ("Divergence + friction
#: losses") BU yarı açıdaki konik lüleye aittir. Kullanıcı başka bir açı
#: verdiğinde diverjans verimi bu referansa GÖRE düzeltilir; aynı sayı
#: ``_nozzle_half_angles`` varsayılanı olarak da okunur (tek tanım noktası).
#: Kaynak: Sutton & Biblarz, "Rocket Propulsion Elements" 9. baskı, Böl. 3
#: (konik lüle diverjans verimi lambda = (1+cos alpha)/2; 15 derece yaygın
#: referans konisi).
SOLID_NOZZLE_REFERENCE_HALF_ANGLE_DEG = 15.0

#: Tasarım genişleme oranının ALT sınırı (A_e/A_t) — TEK tanım noktası.
#: Yakınsak-ıraksak bir lülede ε >= 1 zorunludur; 2,5 değeri, çıkışın
#: boğazdan ölçülebilir biçimde büyük olduğu ve konik ıraksağın imal
#: edilebilir kaldığı pratik alt banttır. ÖH D17 (P2B3-09) öncesinde bu
#: sayı ``_estimate_expansion_ratio`` içinde satır içi yazılıydı ve
#: bağlandığı yerde BEYANSIZ uygulanıyordu.
SOLID_MIN_DESIGN_EXPANSION_RATIO = 2.5

#: Eq. 3-32 kimliğinin "tutarlı" sayılacağı bağıl bant [%]. Kayıtlar dört
#: haneli yazıldığı için yuvarlama artığı bu mertebededir (ölçülen: apcp
#: -%0,0001, double_base +%0,0018, kndx -%0,0008, knsb -%0,0051).
SOLID_CSTAR_IDENTITY_TOLERANCE_PCT = 0.05

#: V301/N-CEA-2 — c*'ı bağımsız bir NASA CEA denge çözümünden gelen
#: (``c_star_basis = 'cea'``) kayıtta Eq. 3-32'nin oda γ_s'siyle verdiği
#: "ideal" ile CEA c*'ı arasında beklenen fark [%]: CEA c*'ı boğazdaki KAYAN
#: bileşimle çözer, Eq. 3-32 tek bir γ varsayar. ÖLÇÜLDÜ (M = 1/n ile,
#: 10-150 bar): AP/HTPB 85/15 (tek faz) -%0,18…-%0,23; APCP -%0,04…-%0,07;
#: KN-şeker -%0,01…+%0,05; kara barut -%0,06…-%0,09 (kati-gecis/RAPOR.md).
#: Bant HRMA SEÇİMİDİR (ölçülen en büyük farkın ~2 katı), kaynaklı bir
#: geçti/kaldı ölçütü değil.
SOLID_CSTAR_EQUILIBRIUM_IDENTITY_BAND_PCT = 0.5

#: V301/N-CEA-2 (K1) — katı termokimyanın KAYNAĞI (yanıtta
#: ``thermochemistry_source``). Tek tanım noktası:
#:   * ``nasa_cea_at_pc``: bileşimi bilinen itici; T_c, c*, γ_s ve M motorun
#:     KENDİ Pc'sinde NASA CEA'dan (RocketCEA = CEA2, kayan denge);
#:   * ``catalogue_single_pressure``: bileşim yok ya da CEA çözümü yok;
#:     katalog dörtlüsü (tek basınçta) kullanılır ve gerekçesiyle BEYAN
#:     edilir (sessiz yedek yok);
#:   * ``user_entered``: kullanıcı c*/γ/T_c/M'den en az birini kaydın
#:     değerinden farklı girdi; girilen değerler kullanılır.
SOLID_THERMO_SOURCE_CEA = 'nasa_cea_at_pc'
SOLID_THERMO_SOURCE_CATALOGUE = 'catalogue_single_pressure'
SOLID_THERMO_SOURCE_USER = 'user_entered'

#: V301/N-CEA-2 (K2) — lüle eşdeğer üssünün kök arama aralığı. Fiziksel
#: izentropik üs bandını (tek atomlu gaz 5/3'e kadar) kapsayan sayısal
#: aralık; HRMA seçimi. Kök yoksa CEA lülesi kullanılmaz ve beyan edilir.
SOLID_NOZZLE_GAMMA_BRACKET = (1.005, 1.70)


def _ideal_single_phase_c_star(gamma, T_c, molecular_weight):
    """Tek fazlı ideal gaz c* [m/s] — Sutton & Biblarz 9. baskı Eq. 3-32.

        Gamma = sqrt(g) * (2/(g+1))^((g+1)/(2(g-1))),  c* = sqrt(R_s*T_c)/Gamma

    TEK tanım noktası: modülün başka yerlerinde aynı bağıntının ters yönü
    (R_s = (c*·Gamma)^2/T_c) kullanılıyor; ikisi aynı Gamma tanımından
    türemelidir. Girdi çözülemezse None döner (sayı uydurulmaz).
    """
    try:
        g = float(gamma)
        Tc = float(T_c)
        mw = float(molecular_weight)
    except (TypeError, ValueError):
        return None
    if not (np.isfinite(g) and np.isfinite(Tc) and np.isfinite(mw)):
        return None
    if g <= 1.0 or Tc <= 0.0 or mw <= 0.0:
        return None
    R_s = R_UNIVERSAL / mw
    gamma_fn = np.sqrt(g) * (2.0 / (g + 1.0)) ** ((g + 1.0) / (2.0 * (g - 1.0)))
    return float(np.sqrt(R_s * Tc) / gamma_fn)


def _c_star_basis_of_record(propellant_type, c_star):
    """Denetlenen c* merkezi katalogdaki kaydınsa onun KÖKEN beyanı.

    ÖH D21 a1 (OH-D19-22). ``_c_star_identity_audit`` bir sayının Eq. 3-32
    özdeşliğini tutup tutmadığını ölçer; ama sayının NEREDEN geldiğini
    bilmeden verdiği hüküm yanıltıcı olabilir. Katalogdaki
    ``c_star_basis`` alanı tam bunu söyler:

      * ``'eq3-32'``            -> c* bu özdeşlikle ÜRETİLDİ (kndx, knsb,
                                   double_base). Sıfır sapma kanıt değil,
                                   aritmetik artıktır: denetim döngüseldir.
      * ``'cea'``               -> bağımsız denge çözümünden (apcp, knsu).
      * ``'measured-two-phase'``-> ölçümden (black_powder).

    Köken YALNIZ denetlenen sayı kaydın kendi c*'ıysa döndürülür; motor
    kendi tablosundan farklı bir c* kullanıyorsa (ya da kullanıcı ezdiyse)
    katalog beyanı O SAYIYA ait değildir ve ``None`` döner — başka bir
    kaydın künyesi bu sayıya YAPIŞTIRILMAZ.
    """
    rec = _get_propellant_safe(_catalog_key_for(propellant_type))
    if not rec:
        return None
    temel = rec.get('c_star_basis')
    if not temel:
        return None
    try:
        kayit_c = float(rec.get('c_star'))
        denetlenen = float(c_star)
    except (TypeError, ValueError):
        return None
    if not (np.isfinite(kayit_c) and np.isfinite(denetlenen)) or kayit_c <= 0:
        return None
    if abs(denetlenen - kayit_c) > 1e-6 * max(1.0, abs(kayit_c)):
        return None
    return str(temel)


def _c_star_identity_audit(propellant_type, gamma, T_c, molecular_weight,
                           c_star, basis_override=None):
    """Kaydın c*'ı kendi (gamma, T_c, M) üçlüsüyle tutarlı mı? — TEK nokta.

    ÖH D17 (P2B1-01). Modülün kendi ölçütü zaten yazılıydı ("(gamma, M, T_c,
    c*) dörtlüsü Eq. 3-32 ile içsel tutarlı") ama HİÇBİR YERDE
    UYGULANMIYORDU; denetim yalnız katalog testindeydi ve orada kayıtlar
    KENDİ ``c_star_basis`` beyanlarıyla muaf tutuluyordu
    ('engine-reference' -> testin gövdesine hiç girmiyor). ÖLÇÜLDÜ
    (docs/scofield/raw/OH/D17/kati/a1/once.json):

      yakıt         c* kayıt   Eq. 3-32 ideal   sapma      X_p
      apcp           1598,2       1598,2015     -0,0001 %  0,3401
      double_base    1406,8       1406,7742     +0,0018 %  0,0
      kndx            912,4        912,4069     -0,0008 %  0,44
      knsb            908,1        908,1465     -0,0051 %  0,44
      knsu/sugar      921,0        978,7154     -5,8971 %  0,44
      black_powder    945,3       1131,6563    -16,4676 %  0,55

    Ölçüt fiziktir, beyan değil: yoğuşmuş faz genişlemeye katkı vermediği
    için iki-fazlı bir kayıtta c* idealin ALTINDA olabilir, ama eksiklik
    yoğuşmuş kütle kesrini (X_p) AŞAMAZ — X_p, katkısını tamamen yitiren
    kütlenin üst sınırıdır. Buna göre:

      * |sapma| <= tolerans                     -> 'single_phase_consistent'
      * |sapma| <= tolerans, X_p > 0 ve kaydın kendi ``c_star_basis``
        alanı ``'eq3-32'``                      ->
        'two_phase_record_single_phase_c_star'
      * sapma < 0 ve X_p > 0 ve |sapma| <= X_p  -> 'two_phase_explained'
      * sapma < 0, aksi hâlde                   -> 'unexplained_deficit'
      * sapma > tolerans                        -> 'above_single_phase_ideal'
        (tek fazlı ideal bir ÜST sınırdır; aşılması kaydın kendi içinde
        çelişkili olduğunu söyler)

    Kaydın ESKİ hâli (c* = 1186,7, X_p = 0,0) bu ölçütte
    'unexplained_deficit' verirdi — yani ölçüt kalemin kendisini yakalar.

    ÖH D21 a1 (OH-D19-22) — ÖLÇÜTÜN KÖR NOKTASI KAPATILDI. Yukarıdaki
    tabloda kndx ve knsb, X_p = 0,44 BEYAN EDERKEN c*'ları tek-fazlı
    idealin ta kendisiydi (-%0,0008 / -%0,0051) ve 'single_phase_consistent'
    hükmünü alıyordu; AYNI yoğuşmuş kesri taşıyan kardeşleri knsu/sugar ise
    -%5,8971 ile 'two_phase_explained' alıyordu. Yani aynı X_p iki farklı
    kayıp sınıfı üretiyordu ve kullanıcı sebebini göremiyordu.

    Sebep FİZİK DEĞİL KÖKEN: ölçüldü ki kndx/knsb kayıtları
    ``c_star_basis = 'eq3-32'`` taşıyor, yani c*'ları denetlenen özdeşliğin
    KENDİSİYLE üretilmiş; sıfır sapma bir kanıt değil aritmetik artıktır ve
    yoğuşmuş fazın genişlemeye katılmayan payı o c*'ın İÇİNDE OLAMAZ.
    knsu/sugar ise ``'cea'`` (bağımsız iki-fazlı denge) taşıyor. Denetim
    artık kaydın kendi köken beyanını okur (``_c_star_basis_of_record``),
    bu hâli ayrı bir hükümle adlandırır ve kökeni ``record_c_star_basis`` /
    ``identity_is_independent`` alanlarıyla yayımlar. c* DEĞERLERİ
    DEĞİŞMEDİ: kaynaklı iki-fazlı bir KNDX/KNSB c*'ı bu depoda yoktur ve
    sayı uydurulmaz — eksik olan veri, hükmü dürüstleştirmekle kapanmaz,
    yalnız GÖRÜNÜR olur.
    """
    ideal = _ideal_single_phase_c_star(gamma, T_c, molecular_weight)
    try:
        c = float(c_star)
    except (TypeError, ValueError):
        c = None
    if ideal is None or c is None or not np.isfinite(c) or c <= 0.0:
        return {
            'ideal_single_phase_c_star_m_s': ideal,
            'record_c_star_m_s': c,
            'deviation_percent': None,
            'condensed_mass_fraction': None,
            'status': 'not_evaluable',
            'basis': ('The Eq. 3-32 identity could not be evaluated for this '
                      'record; no verdict is published rather than a guessed '
                      'one.'),
        }
    sapma = 100.0 * (c - ideal) / ideal
    x_p, x_kaynak, _ = _condensed_mass_fraction(propellant_type)
    tol = float(SOLID_CSTAR_IDENTITY_TOLERANCE_PCT)
    kayit_basis = _c_star_basis_of_record(propellant_type, c)
    # V301/N-CEA-2 (K1): termokimya motorun Pc'sinde NASA CEA'dan geldiyse
    # c*'ın kökeni katalog kaydının beyanı DEĞİL, bu koşumun bağımsız denge
    # çözümüdür ('cea'); çağıran bunu açıkça verir.
    if basis_override is not None:
        kayit_basis = str(basis_override)
    if (abs(sapma) <= tol and x_p is not None and x_p > 0.0
            and kayit_basis == 'eq3-32'):
        # ÖH D21 a1 (OH-D19-22). Bu dal, D17 ölçütünün GÖREMEDİĞİ hâli
        # yakalar: kayıt hem X_p > 0 beyan ediyor hem de c*'ı TEK-FAZLI
        # Eq. 3-32 idealinin ta kendisi. Sebep fizik değil KÖKENDİR —
        # kaydın kendi 'c_star_basis' alanı c*'ın bu formülle ÜRETİLDİĞİNİ
        # söylüyor, yani denetim döngüseldir ve sıfır sapma bir kanıt
        # değil aritmetik artıktır.
        durum = 'two_phase_record_single_phase_c_star'
        kunye = (f'c* = {c:.4f} m/s equals the single-phase ideal '
                 f'{ideal:.4f} m/s to {sapma:+.4f}%, but this record also '
                 f'declares a condensed-phase mass fraction X_p = '
                 f'{x_p:.4f} (source: {x_kaynak}). The agreement is NOT '
                 f'corroboration: the record states c_star_basis = '
                 f"'eq3-32', i.e. this c* was PRODUCED by the very "
                 f'single-phase identity being tested, so the condensed '
                 f'phase cannot be inside it. Sibling records with the '
                 f'same X_p whose c* comes from an independent two-phase '
                 f'source sit measurably below their own ideal. Treat this '
                 f'c* as a single-phase upper bound; the delivered value '
                 f'is lower by an amount this catalogue does not yet carry '
                 f'from a two-phase source.')
    elif abs(sapma) <= tol:
        durum = 'single_phase_consistent'
        kunye = (f'c* = {c:.4f} m/s matches the single-phase ideal '
                 f'{ideal:.4f} m/s implied by the gamma, T_c and molecular '
                 f'weight of this same record, to {sapma:+.4f}%.')
        if x_p is not None and x_p > 0.0:
            kunye += (
                f' This record declares a condensed-phase mass fraction '
                f'X_p = {x_p:.4f} (source: {x_kaynak}), so its gamma, T_c '
                f'and molecular weight must already be the mixture averages '
                f'that include the condensed products for the identity to '
                f'hold at all; that framing is asserted by the record '
                f"(c_star_basis = {kayit_basis!r}) and is not re-derived "
                f'here.')
    elif sapma > tol:
        durum = 'above_single_phase_ideal'
        kunye = (f'c* = {c:.4f} m/s is {sapma:+.4f}% ABOVE the single-phase '
                 f'ideal {ideal:.4f} m/s implied by the gamma, T_c and '
                 f'molecular weight of this same record. The ideal is an '
                 f'upper bound, so the record is internally inconsistent.')
    elif (kayit_basis == 'cea' and sapma < 0.0
          and (x_p is None or x_p <= 0.0)
          and abs(sapma) <= float(SOLID_CSTAR_EQUILIBRIUM_IDENTITY_BAND_PCT)):
        # V301/N-CEA-2: tek fazlı CEA kaydı; fark kayan denge ⟷ tek-γ
        # özdeşliği farkıdır (bant künyesi sabitte).
        durum = 'single_phase_consistent'
        kunye = (f'c* = {c:.4f} m/s is {sapma:+.4f}% below the single-gamma '
                 f'Eq. 3-32 value {ideal:.4f} m/s. This c* is an independent '
                 f'NASA CEA equilibrium solution (c_star_basis = cea), which '
                 f'solves the throat with a shifting composition; a deficit '
                 f'within {SOLID_CSTAR_EQUILIBRIUM_IDENTITY_BAND_PCT}% '
                 f'(SOLID_CSTAR_EQUILIBRIUM_IDENTITY_BAND_PCT, HRMA choice '
                 f'from measured CEA points) is that difference, not a '
                 f'loss.')
    elif x_p is not None and x_p > 0.0 and (abs(sapma) / 100.0) <= x_p:
        durum = 'two_phase_explained'
        kunye = (f'c* = {c:.4f} m/s is {sapma:+.4f}% below the single-phase '
                 f'ideal {ideal:.4f} m/s. The deficit is bounded by the '
                 f'declared condensed-phase mass fraction X_p = {x_p:.4f} '
                 f'(source: {x_kaynak}), which is the largest share of the '
                 f'mass that can fail to expand, so the deficit is '
                 f'accounted for.')
    else:
        durum = 'unexplained_deficit'
        kunye = (f'c* = {c:.4f} m/s is {sapma:+.4f}% below the single-phase '
                 f'ideal {ideal:.4f} m/s and the declared condensed-phase '
                 f'mass fraction (X_p = {x_p}) does not bound that deficit. '
                 f'Nothing in the record explains the gap.')
    return {
        'ideal_single_phase_c_star_m_s': float(ideal),
        'record_c_star_m_s': float(c),
        'deviation_percent': float(sapma),
        'condensed_mass_fraction': None if x_p is None else float(x_p),
        'condensed_mass_fraction_source': x_kaynak,
        'tolerance_percent': tol,
        # ÖH D21 a1 (OH-D19-22): hükmün KÖKENİ de yayımlanır. Aynı X_p'yi
        # taşıyan iki kaydın farklı sınıfa düşmesinin sebebi fizik değil,
        # c*'ın nereden geldiğidir; kullanıcı bunu görmeden iki satırı
        # kıyaslayamaz.
        'record_c_star_basis': kayit_basis,
        'identity_is_independent': (None if kayit_basis is None
                                    else kayit_basis != 'eq3-32'),
        'status': durum,
        'basis': kunye,
    }


def _conical_divergence_efficiency(half_angle_deg):
    """Konik lüle diverjans verimi lambda = (1+cos alpha)/2 — TEK tanım."""
    return 0.5 * (1.0 + float(np.cos(np.radians(float(half_angle_deg)))))


SOLID_NOZZLE_EROSION_MATERIAL = {
    'graphite': 'graphite',
    'carbon_carbon': 'carbon_carbon',
    'c-c': 'carbon_carbon',
}


# Motorun KENDİ tablolarında (termokimya / grain mekaniği / yoğuşmuş faz)
# kaydı olmayan bir yakıt seçildiğinde değerler aynı AİLENİN temsilcisinden
# devralınır. Aile bilgisi uydurulmaz: merkezi katalogdaki 'family' alanından
# okunur (propellants_db.VALID_FAMILIES). Temsilcisi olmayan aile için
# devralma YAPILMAZ — çağıran taraf bunu "veri yok" olarak raporlar.
_FAMILY_REPRESENTATIVE = {
    'composite': 'apcp',       # AP/HTPB(/Al) kompozitler
    'sugar': 'sugar',          # KN-şeker ailesi (KNSU/KNDX/KNSB/KNER)
    'double_base': 'double_base',
}


def _catalog_key_for(propellant_type):
    """Motor anahtarının merkezi katalog karşılığı (yoksa None).

    İki yol denenir: (1) katalog kaydının 'engine_key' alanı üzerinden ters
    harita, (2) anahtarın KENDİSİ katalog anahtarı/alias'ı olabilir. İkinci
    yol olmadan 'kndx'/'knsb' gibi doğrudan katalog anahtarları motor
    tarafında hiçbir kataloğa bağlanamıyordu (yanma hızı tutarlılık kontrolü
    o yakıtlarda sessizce devre dışı kalıyordu).
    """
    raw = str(propellant_type or '').strip().lower()
    if not raw:
        return None
    key = _ENGINE_KEY_TO_CATALOG.get(raw)
    if key:
        return key
    return raw if _get_propellant_safe(raw) else None


def _propellant_family(propellant_type):
    """Yakıtın merkezi katalogdaki aile adı (yoksa None)."""
    key = _catalog_key_for(propellant_type)
    rec = _get_propellant_safe(key) if key else None
    return (rec or {}).get('family')


def _family_lookup(propellant_type, table):
    """(değer, kaynak_anahtar) — tabloda yoksa aile temsilcisinden devral.

    Devralma SESSİZ DEĞİLDİR: kaynak anahtar geri döndürülür ve çağıran taraf
    onu rapora ('inherited_from') veya uyarıya yazar. Ne tabloda ne ailede
    karşılık varsa (None, None) döner — sayı uydurulmaz.
    """
    key = str(propellant_type or '').strip().lower()
    if key in table:
        return table[key], key
    rep = _FAMILY_REPRESENTATIVE.get(_propellant_family(key))
    if rep and rep in table:
        return table[rep], rep
    return None, None


#: Kompozit yakıt kaydının formülasyon metninde METAL YAKIT OLMADIĞINI
#: söyleyen ifadeler. Katalog kayıtları bu iki kalıbı kullanıyor
#: (apcp_nonaluminized: "(no metal fuel)", blue_thunder: "(non-aluminized)").
_NO_METAL_FUEL_MARKERS = ('no metal fuel', 'non-aluminized', 'nonaluminized',
                          'no metal', 'metal-free')

#: Formülasyon metninden alüminyum kütle yüzdesini okuyan kalıp
#: ("Aluminum ~18% + HTPB binder ~14%" -> 18).
_ALUMINUM_PERCENT_RE = re.compile(
    r'alumini?um[^0-9%]{0,12}(\d{1,2}(?:[.,]\d+)?)\s*%', re.IGNORECASE)


def _metal_mass_fraction_from_formulation(propellant_type):
    """Kompozit kaydın METAL yakıt kütle kesri [-] — katalog metninden.

    ÖH D15 a3 (P2B1-11). Yoğuşmuş faz kesri ``SOLID_CONDENSED_MASS_FRACTION``
    tablosunda yalnız 'apcp' için yazılıydı ve tabloda karşılığı olmayan HER
    kompozit onu ``_FAMILY_REPRESENTATIVE`` üzerinden devralıyordu. Devralma
    metal yüklemesini AYIRT ETMİYOR: ÖLÇÜLDÜ (bu düzeltmeden önce)

      anahtar               katalog 'fuel' alanı                    X_p
      apcp                  Aluminum ~18% + HTPB ~14%           0,340119
      apcp_nonaluminized    HTPB binder ~15% (no metal fuel)    0,340119  <-
      blue_thunder          Polyester/PU binder (non-aluminized) 0,340119 <-
      pban_ap_al            Aluminum ~16% + PBAN ~14%           0,340119  <-

    yani "metal yakıt yok" diyen kaydın two_phase_losses'ı %4,081 ve
    particle_diameter_um'u 1,408 (Al2O3 taneciği!) olarak yayımlanıyordu, üstelik
    künye "X_p ... FROM THE PROPELLANT FORMULATION" diyordu. %16 Al'li kayıt
    da %18'lik değeri alıyordu (+%12,5).

    Kesir UYDURULMAZ: kaydın kendi formülasyon metninden okunur.
      * metalsizlik işaretlerinden biri geçiyorsa            -> 0,0
      * "Aluminum ~NN%" okunabiliyorsa                       -> NN/100
      * ikisi de yoksa                                       -> None
    None dönerse çağıran taraf devralmaya DÜŞMEZ; sayı yayımlanmaz.
    """
    rec = _get_propellant_safe(_catalog_key_for(propellant_type))
    if not rec:
        return None
    metin = ' '.join(str(rec.get(alan) or '')
                     for alan in ('fuel', 'composition', 'notes'))
    duz = metin.lower()
    m = _ALUMINUM_PERCENT_RE.search(metin)
    if m:
        try:
            return float(m.group(1).replace(',', '.')) / 100.0
        except ValueError:
            return None
    if any(im in duz for im in _NO_METAL_FUEL_MARKERS):
        return 0.0
    return None


def _condensed_mass_fraction(propellant_type):
    """(X_p, kaynak_anahtar, künye) — yoğuşmuş faz kesri, TEK çözüm noktası.

    Sıra:
      1. ``SOLID_CONDENSED_MASS_FRACTION``ta ANAHTARIN KENDİSİ varsa o.
      2. Kompozit ailede: kesir kaydın KENDİ formülasyonundan türetilir
         (X_p = w_metal * AL_TO_AL2O3_MASS_RATIO — tablo 'apcp' satırının da
         yazılı gerekçesi budur, yeni bir sabit tanımlanmaz). Bu bir
         DEVRALMA DEĞİLDİR; kaynak anahtar yakıtın kendisidir.
      3. Formülasyondan okunamıyorsa aile temsilcisinden devralınır
         (eski davranış; metal yüklemesi hakkında bilgi YOKSA en azından
         devralma beyan edilir).
      4. Hiçbiri yoksa (None, None, None) — sayı uydurulmaz.

    Kaynak anahtar (2. eleman) her zaman bir YAKIT ANAHTARIDIR; çağıran
    taraf "devralındı mı?" sorusunu ona bakarak yanıtlar. Üçüncü eleman
    insan-okur künyedir ve tek yerde kurulur.
    """
    key = str(propellant_type or '').strip().lower()
    if key in SOLID_CONDENSED_MASS_FRACTION:
        return (SOLID_CONDENSED_MASS_FRACTION[key], key,
                f"SOLID_CONDENSED_MASS_FRACTION['{key}']")
    if _propellant_family(key) == 'composite':
        w_metal = _metal_mass_fraction_from_formulation(key)
        if w_metal is not None:
            return (float(w_metal) * AL_TO_AL2O3_MASS_RATIO, key,
                    f"derived from the '{key}' catalog formulation "
                    f'({w_metal * 100.0:.0f}% metal fuel) x '
                    f'AL_TO_AL2O3_MASS_RATIO')
    deger, rep = _family_lookup(key, SOLID_CONDENSED_MASS_FRACTION)
    if deger is None:
        return None, None, None
    return (deger, rep,
            f"SOLID_CONDENSED_MASS_FRACTION['{rep}'], inherited from the "
            f'same propellant family')


def _normalize_catalog_name(text):
    """Katalog adını karşılaştırma için sadeleştirir (tek tanım noktası).

    Büyük/küçük harf, ardışık boşluk ve ayraç çevresi boşlukları normalize
    edilir; adın AYIRT EDİCİ parçaları (parantezli niteleyiciler dâhil)
    korunur — atılmaları P2B1-10'un ta kendisiydi.
    """
    return re.sub(r'\s+', ' ', str(text or '').strip().lower())


def _catalog_key_from_text(text):
    """Serbest metinden merkezi katalog anahtarı çıkarır (yoksa None).

    Arayüz yakıtı ÜÇ ayrı alanla anlatıyor: katalog satırı (anahtar),
    yanma-hızı ön ayarı ('kndx') ve serbest metin ad alanı ('KNDX -
    Potassium Nitrate/Dextrose 65/35'). Motor yalnız ilkini tanıyordu ve
    o alan hiç gönderilmiyordu; bu yüzden KNDX seçen kullanıcının motoru
    içeride APCP olarak çözülüyordu. Burada üç yazımın da aynı anahtara
    inmesi sağlanır — yeni bir eşleme tablosu UYDURULMAZ, yalnız merkezi
    kataloğun kendi anahtarları/adları/takma adları denenir.
    """
    raw = str(text or '').strip().lower()
    if not raw or raw in ('custom', 'none', 'other'):
        return None
    # 1) Doğrudan anahtar / motor anahtarı / takma ad
    key = _catalog_key_for(raw.replace(' ', '_').replace('-', '_'))
    if key:
        return key
    # 2) Kaydın TAM ADI. ÖH D15 (P2B1-10): bu adım eskiden 3. sıradaydı ve
    #    önündeki ayraç-bölmesi adın AYIRT EDİCİ parçasını atıyordu:
    #    'AP/HTPB Composite (non-aluminized)' ilk parçası 'ap' olduğu için
    #    ALÜMİNYUMLU APCP kaydına düşüyordu (T_c 2550 -> 3614,8 K, +%41,8;
    #    Isp 208,6 -> 234,8 s, toplam impuls +%19,9) ve 'KNSU - ... (cast bulk
    #    density)' adı ideal-yoğunluklu 'knsu' satırına gidiyordu (+%6,13
    #    toplam impuls). Kataloğun 12 adından 4'ü kendi kaydına dönmüyordu.
    #    Tam ad eşleşmesi kısaltmadan ÖNCE denenirse hiçbiri kaymaz.
    normal = _normalize_catalog_name(raw)
    for cat_key, rec in _PROPELLANT_CATALOG.items():
        if _normalize_catalog_name(rec.get('name', '')) == normal:
            return cat_key
    # 3) 'KNDX - kendi karışımım' gibi serbest metin: ayraçtan önceki ilk
    #    sözcük öbeği katalog anahtarının kendisi olabilir. Tam ad eşleşmesi
    #    başarısız olduğunda başvurulur, çünkü kısaltma niteleyiciyi atar.
    head = re.split(r'[-–—/(,:]', raw, maxsplit=1)[0].strip()
    if head and head != raw:
        key = _catalog_key_for(head.replace(' ', '_'))
        if key:
            return key
    return None


#: KNSU 65/35'in bileşimden türeyen ÖZELLİKLERİ — TEK tanım noktası.
#: 'sugar' (dökme) ve 'knsu' (ideal) satırları bu kaydı paylaşır ve yalnız
#: yoğunluk tabanında ayrılır (ÖH D15 / P2B1-04). Termokimya NASA CEA
#: (KNO3/sakaroz 65/35, iki-faz dâhil; Nakka c* ~917 m/s, T_c ~1720 K);
#: ikincil katsayılar #446 kalibrasyonundan.
_KNSU_65_35_BASE = {
    'c_star': 921.0,          # m/s
    'gamma': 1.1235,
    'T_c': 1719.0,            # K (K2CO3 yoğuşması alevi sınırlar)
    'molecular_weight': 37.21,  # g/mol
    'density_temp_coeff': -0.8e-3,
    'c_star_pressure_coeff': 1.9,
    'burn_rate_temp_coeff': 0.0041,
    'erosive_burning_coeff': 0.0123,   # yeniden kalibre (#446)
    'nozzle_efficiency': 0.978,
}


def _catalog_burn_rate(propellant_type):
    """Yakıtın merkezi katalogdaki (a, n) çifti — yoksa (None, None)."""
    key = _catalog_key_for(propellant_type)
    if not key:
        return None, None
    rec = _get_propellant_safe(key)
    if not rec:
        return None, None
    return rec.get('burn_rate_a'), rec.get('burn_rate_n')


# NOT (2026-07-25): burada argümansız `warnings.filterwarnings('ignore')`
# vardı. Argümansız çağrı SÜREÇ GENELİNDE catch-all bir filtre kurar; bu
# modülü import etmek TÜM uygulamada numpy'nin sıfıra bölme/geçersiz değer
# uyarılarını (ve her DeprecationWarning'i) susturuyordu. Kaldırıldı —
# gerçekten susturulması gereken bir uyarı varsa dar kapsamlı
# `with warnings.catch_warnings():` bloğuyla ve gerekçesiyle yapılır.


def _propellant_lot_scales(lot):
    """Yakıt partisi çarpanları (V301/K-D) — doğrulanmış sözlük ya da None.

    ``{'c_star_scale': x, 'density_scale': y}``; verilmeyen çarpan 1,0'dır.
    Çarpan sonlu ve pozitif olmalıdır, aksi hâlde ``ValueError`` (sessiz
    yedek yok). ``None`` ya da boş sözlük "bozulma yok" demektir ve motor
    hiçbir çarpma YAPMAZ (çarpan 1,0 ile de sonuç bit-aynıdır: x·1,0 = x).
    """
    if not lot:
        return None
    bilinen = ('c_star_scale', 'density_scale')
    fazla = set(lot) - set(bilinen)
    if fazla:
        raise ValueError('unknown propellant_lot keys: %s'
                         % ', '.join(sorted(fazla)))
    olcek = {}
    for ad in bilinen:
        deger = lot.get(ad, 1.0)
        if isinstance(deger, bool):
            raise ValueError('propellant_lot %s must be a number' % ad)
        deger = float(deger)
        if not (np.isfinite(deger) and deger > 0.0):
            raise ValueError('propellant_lot %s must be finite and > 0, '
                             'got %r' % (ad, deger))
        olcek[ad] = deger
    return olcek


class SolidGeometryError(ValueError):
    """Kurucunun reddettiği fiziksel olmayan girdi — makine-okur künyeli.

    ``ValueError``dan türer ki mevcut ``except Exception`` / ``except
    ValueError`` dalları bugünkü gibi 400'e çevirmeye devam etsin; eklenen
    tek şey, reddin gerekçesinin metinden ayrıştırılmak zorunda kalmamasıdır
    (``kunye``: field / reason / value / accepted_range / unit).
    """

    def __init__(self, message, kunye):
        super().__init__(message)
        self.kunye = kunye


class SolidDesignRejected(SolidGeometryError):
    """Tasarımı YAYIMLANMAYAN girdi reddi — uçta 422 (v3.0.1, V301/K-A).

    ``SolidGeometryError`` alt sınıfıdır: kurucunun mevcut ret kanalını
    tanıyan her çağıran (``/api/solid-monte-carlo`` 422 dalı, örneklem
    başına ``except Exception``) onu bugünkü gibi işler. ``/calculate_solid``
    bu sınıfı AYRICA yakalar ve 422 ``invalid_fields`` gövdesine çevirir
    (hibrit ``GrainEnvelopeError`` deseni, ``port-kamara/RAPOR.md`` KARAR 3).

    Alanlar:
      * ``code`` — makine kodu (``grain_does_not_fit_case``,
        ``port_smaller_than_throat``, ``core_not_inside_grain`` …);
      * ``invalid_fields`` — yapılı künye listesi (alan, gönderilen değer,
        gereken/kabul edilen değer, birim, EN cümle);
      * ``kunye`` — ilk künye (üst sınıfın tek-künye sözleşmesi).
    """

    def __init__(self, message, invalid_fields, code):
        alanlar = list(invalid_fields or [])
        super().__init__(message, alanlar[0] if alanlar else {})
        self.invalid_fields = alanlar
        self.code = code


def _ceil_tenth_mm(value_mm):
    """Gereken en küçük ölçü 0,1 mm'ye YUKARI yuvarlanır.

    Hibrit zarf reddiyle aynı kural (``hybrid_rocket_engine``
    ``np.ceil(gereken * 1e4 - 1e-9) / 10``): önerilen sayı kapıdan GEÇER;
    aşağı yuvarlanan bir öneri kullanıcıyı ikinci bir redde sokardı.
    """
    return float(np.ceil(float(value_mm) * 10.0 - 1e-9) / 10.0)


def _core_diameter_domain(grain_type, chamber_diameter_mm):
    """``core_diameter``ın kapıdan geçen KABUL KÜMESİ — TEK tanım noktası.

    ÖH D20 (OH-D19-23). Kapının üç ret künyesi de ``accepted_range: [0, D]``
    yazıyordu; oysa radyal yanan grainde kabul kümesi AÇIK aralıktır:
    0 reddedilir (``zero_port``, yanma yüzeyi yok) ve D de reddedilir
    (``core_not_inside_case``, yakıt kalmaz). Yani künye, kendi kapısının
    reddettiği İKİ ucu "kabul edilir" diye ilan ediyordu — kullanıcı
    ``core_diameter = 0`` yazıp reddedilirken künyeden 0'ın kabul edildiğini
    okuyordu. ÖLÇÜLDÜ (docs/scofield/raw/OH/D20/kati/a1/once.json):

      girdi (D = 100 mm)   ret sebebi             künyedeki accepted_range
      core = 0             zero_port              [0, 100.0]   <- 0 içeride
      core = 100           core_not_inside_case   [0, 100.0]   <- 100 içeride

    Kapalı aralık gösterimi ``negative_core`` kontrolünden kopyalanmıştı;
    orada sıfır gerçekten kabul edilebilir (end_burner). Kabul kümesi artık
    grain tipine göre BİR yerde kurulur ve üç künye de onu taşır; sınırların
    açık/kapalı olduğu ``accepted_range_exclusive`` ile ayrıca söylenir,
    böylece sayısal çifti okuyan eski tüketiciler kırılmaz.
    """
    D = float(chamber_diameter_mm)
    if grain_type == 'end_burner':
        # Eksenel yanma: port yoktur, bu yüzden ne sıfır port ne de kasa
        # kısıtı doğar; kapı yalnız negatif değeri reddeder.
        return {
            'accepted_range': [0.0, None],
            'accepted_range_exclusive': [False, False],
            'accepted_range_text': (
                'core_diameter >= 0 (an end burner burns axially, so it has '
                'no port constraint)'),
        }
    return {
        'accepted_range': [0.0, D],
        'accepted_range_exclusive': [True, True],
        'accepted_range_text': (
            '0 < core_diameter < %g (a radially burning grain has no burning '
            'surface at a zero port, and a core at or beyond the case '
            'diameter leaves no propellant); both ends are EXCLUDED' % D),
    }


def _solid_geometry_gate(grain_type, chamber_diameter, grain_length,
                         core_diameter, chamber_pressure, burn_rate_a):
    """Kurucunun FAIL-CLOSED girdi kapısı — TEK tanım noktası.

    ÖH D15 a3 (P2B1-07). Kurucu ``grain_type`` DIŞINDA hiçbir argümanı
    kapılamıyordu. ``/calculate_solid`` uç katmanında dört bant kontrolü
    var, ``/api/solid-monte-carlo``da HİÇ yok; motoru doğrudan kuran her
    istemci (betikler, uygulama dışı istemciler) tamamen kapısızdı.
    ÖLÇÜLDÜ (bu kapı eklenmeden önce, kasa 100 mm):

      girdi                       kurucu   sonuç
      core_diameter = -30 mm      kabul    64 anahtarlı TAM sonuç,
                                           Isp = 27,9941 s ⟷ aynı yanıtta
                                           isp_vacuum = 267,8985 s (9,570 kat
                                           iç çelişki); POST
                                           /api/solid-monte-carlo HTTP 200,
                                           n_failed_runs = 0, 100 mm kasada
                                           throat_diameter_mm = 87,258
      chamber_diameter = 0        kabul    ZeroDivisionError (ham 500)
      chamber_pressure = 0        kabul    ZeroDivisionError (ham 500)
      chamber_pressure = -40      kabul    NaN dolu sonuç sözlüğü
      grain_length = 0 / -500     kabul    NaN dolu sonuç sözlüğü
      burn_rate_a = 0 / -0,002    kabul    NaN dolu sonuç sözlüğü
      core_diameter >= kasa       kabul    NaN dolu sonuç sözlüğü
      core_diameter = 0 (radyal)  kabul    65 anahtarlı TAM sonuç: bates
                                           Isp 15,462 s, slotted 4,664 s,
                                           finocyl 316,824 s; star ve
                                           wagon_wheel ise 'Invalid grain
                                           geometry' (ÖH D17 / P2B1-07 ŞART
                                           ile kapatıldı, reason 'zero_port')

    Kapı FİZİKSEL OLARAK İMKÂNSIZ olanı reddeder; mühendislik bandı
    (ne kadar küçük bir çekirdek makul, hangi basınç aralığı çalışılabilir)
    uç katmanının ``FORM_LIMITS`` işidir ve burada DARALTILMAZ — sağlıklı
    motorların hiçbiri bu kapıya takılmaz.

    ``burn_rate_n`` bilerek kapılanmaz: n >= 1 çözücünün kendi kritik
    uyarısıyla (``warn.solid.burn_rate_exponent_ge_one``) ve kararlılık
    hükmüyle ele alınır; orada yayımlanan hüküm DOĞRUDUR (bkz. P2B2-10).
    """
    def _sayi(deger, alan, birim):
        if isinstance(deger, bool) or not isinstance(deger, (int, float)):
            raise SolidGeometryError(
                f'{alan} must be a number, given: '
                f'{type(deger).__name__}',
                {'field': alan,
                 'reason': ('boolean_is_not_a_number'
                            if isinstance(deger, bool)
                            else 'not_a_number'),
                 'value': str(deger)[:80], 'unit': birim,
                 'motor_form': 'solid'})
        d = float(deger)
        if not np.isfinite(d):
            raise SolidGeometryError(
                f'{alan} must be finite, given: {deger}',
                {'field': alan, 'reason': 'not_finite',
                 'value': str(deger)[:80], 'unit': birim,
                 'motor_form': 'solid'})
        return d

    def _pozitif(deger, alan, birim):
        d = _sayi(deger, alan, birim)
        if d <= 0.0:
            raise SolidGeometryError(
                f'{alan} must be positive, given: {d}',
                {'field': alan, 'reason': 'not_positive', 'value': d,
                 'accepted_range': ['>0', None], 'unit': birim,
                 'motor_form': 'solid'})
        return d

    D = _pozitif(chamber_diameter, 'chamber_diameter', 'mm')
    _pozitif(grain_length, 'grain_length', 'mm')
    _pozitif(chamber_pressure, 'chamber_pressure', 'bar')
    _pozitif(burn_rate_a, 'burn_rate_a', 'm/s/bar^n')
    d_core = _sayi(core_diameter, 'core_diameter', 'mm')
    if d_core < 0.0:
        raise SolidGeometryError(
            f'core_diameter cannot be negative, given: {d_core}',
            dict({'field': 'core_diameter', 'reason': 'negative_core',
                  'value': d_core, 'unit': 'mm', 'motor_form': 'solid'},
                 **_core_diameter_domain(grain_type, D)))
    # ÖH D17 (P2B1-07 ŞART): kapı SIFIR PORTU kaçırıyordu. Radyal yanan
    # tipte çekirdek çapı 0 demek "port yok" demektir; yanma yüzeyi yoktur,
    # akı tanımsızdır. ÖLÇÜLDÜ (docs/scofield/raw/OH/D17/kati/a1/once.json,
    # kasa 100 mm / L 500 mm / APCP / 40 bar, core_diameter = 0):
    #
    #   bates        kuruldu -> 65 anahtarlı TAM sonuç, Isp  15,462 s,
    #                            ortalama itki  51,08 N
    #   slotted      kuruldu -> 65 anahtar,        Isp   4,664 s,  22,83 N
    #   finocyl      kuruldu -> 65 anahtar,        Isp 316,824 s, 604,22 N
    #   star         'Invalid grain geometry' (2 anahtar)
    #   wagon_wheel  'Invalid grain geometry' (2 anahtar)
    #
    # yani AYNI fiziksel imkânsızlık üç ayrı davranış üretiyordu; üstelik
    # finocyl'in 316,8 s'lik Isp'si "sağlıklı" görünüyor. Ürün yüzü: POST
    # /api/uncertainty-analysis {motor_type:'solid', inputs:{core_diameter:0}}
    # -> HTTP 200 'ok' (aynı uç core=-30'a 400 diyor). Kapı kurucuda
    # olduğu için düzeltme HER istemciyi aynı anda kapatır.
    if grain_type != 'end_burner' and d_core <= 0.0:
        raise SolidGeometryError(
            f'core_diameter must be positive for a radially burning '
            f'{grain_type} grain, given: {d_core}; a zero port has no '
            f'burning surface',
            dict({'field': 'core_diameter', 'reason': 'zero_port',
                  'value': d_core, 'unit': 'mm', 'motor_form': 'solid'},
                 **_core_diameter_domain(grain_type, D)))
    # end_burner'da port yoktur; yanma eksenel olduğu için çekirdek çapı
    # kasayı delme sorusunu doğurmaz. Radyal yanan her tipte çekirdek
    # kasadan KÜÇÜK olmak zorundadır, yoksa yakıt kalmaz.
    if grain_type != 'end_burner' and d_core >= D:
        raise SolidGeometryError(
            f'core_diameter ({d_core}) must be smaller than '
            f'chamber_diameter ({D}); there would be no propellant left',
            dict({'field': 'core_diameter',
                  'reason': 'core_not_inside_case',
                  'value': d_core, 'unit': 'mm', 'motor_form': 'solid'},
                 **_core_diameter_domain(grain_type, D)))


#: ``overrides`` alanlarının BİRİMİ — ret künyesinde (``rejected_inputs`` /
#: ``/calculate_solid`` 422 ``invalid_fields``) aralığın yanında yayımlanır
#: (v3.0.1, V301/K-A, KT-06/KT-13). Sayı DEĞİL, yalnız birim etiketi; aralık
#: her ``_override_val`` çağrısının kendi argümanıdır (ikinci kopya yok).
#: Birimler çağrı yerindeki dönüşümden okundu (ör. ``m / 1000.0`` -> mm,
#: ``m * 1e6`` -> MPa, ``m / 100.0`` -> kPa); boyutsuz alanlar ``''``.
#: Tabloda olmayan alan künyeye ``unit: None`` ile geçer (uydurulmaz).
SOLID_OVERRIDE_FIELD_UNITS = {
    'density': 'kg/m^3', 'char_velocity': 'm/s', 'gamma': '',
    'flame_temp': 'K', 'molecular_weight': 'g/mol',
    'nozzle_efficiency': '', 'combustion_efficiency': '',
    'cf_efficiency': '', 'kinetic_efficiency': '', 'two_phase_loss': '',
    'divergence_loss': '', 'discharge_coeff': '', 'overall_efficiency': '',
    'divergent_angle': 'deg', 'convergent_angle': 'deg',
    'erosive_k': '', 'erosive_m': '', 'temp_coeff': '1/K',
    'initial_temp': 'K', 'ambient_temp': 'K',
    'yield_strength': 'MPa', 'safety_factor': '', 'case_thickness': 'mm',
    'liner_thickness': 'mm', 'liner_density': 'kg/m^3',
    'insulation_thickness': 'mm', 'grain_gap': 'mm', 'outer_diameter': 'mm',
    'test_altitude': 'm', 'atm_pressure': 'kPa',
    'grain_count': 'segments', 'n_segments': 'segments',
    'web_thickness': 'mm', 'chamber_volume': 'L',
    'erosion_factor': 'mm/s', 'throat_erosion_a_ref_mm_s': 'mm/s',
    'closure_bolt_count': 'bolts', 'igniter_pressure_fraction': 'P/Pc',
    'thrust': 'N', 'target_thrust': 'N', 'burn_time': 's',
    'target_burn_time': 's', 'star_points': 'points', 'star_radius': 'mm',
}

#: Kasa sığma kuralının yayımlanan metni (V301/K-A, KT-01/KT-03). Kaynak:
#: geometrinin kendisi — tane, yapışık astar ve yalıtım halkaları kasanın
#: içinde eş merkezli durur (``SOLID_THERMAL_LAYER_ORDER``; Sutton & Biblarz
#: 9. baskı Böl. 12, yalıtım payı). Sayı içermez; ret künyesi ve ``case_bore``
#: beyanı bu TEK metni taşır.
SOLID_CASE_FIT_RULE = ('case inner diameter >= grain outer diameter + '
                       '2 x (liner_thickness + insulation_thickness)')

#: ``outer_diameter`` (tane dış çapı, mm) kabul aralığı — TEK tanım noktası.
#: Sayı v2.6.26 kalem 29'dan beri ``_apply_overrides`` 7c'de satır içiydi
#: (1-5000 mm; üst uç kamara çapı kanonunun mm görünümüyle aynı). V301/K-A:
#: ``/calculate_solid`` kasa türetme biçiminde aynı aralığı uçta da
#: uyguladığı için sabite çekildi; değer DEĞİŞMEDİ.
SOLID_OUTER_DIAMETER_RANGE_MM = (1.0, 5000.0)

#: ``web_thickness`` (girilen tane ağı, mm) kabul aralığı — TEK tanım noktası
#: (V301/K-D, T-çapa-B DEVİR 2). Eski bant satır içiydi (0,1-1000 mm) ve
#: tane dış çapı bandıyla (1-5000 mm, kamara çapı kanonunun mm görünümü)
#: çelişiyordu: ölçüldü, Ø3700 / çekirdek 1500 mm (ağ 1100 mm) tutarlı SRB
#: ölçekli motor 422 ``web_thickness = 1100 is outside the accepted range
#: 0.1 to 1000 mm`` alıyordu; sayfa bu alanı geometriden doldurup HER hesapta
#: gönderdiği için 2000 mm'nin üstündeki her tane sayfadan çözülemiyordu.
#: Üst uç YENİ bir sayı değildir, geometriden türer: ağ = (D_dış − D_çekirdek)/2
#: < D_dış/2, yani tane dış çapı bandının yarısı. Alt uç değişmedi.
SOLID_WEB_THICKNESS_RANGE_MM = (0.1, SOLID_OUTER_DIAMETER_RANGE_MM[1] / 2.0)

#: Varsayılan (örnek) katı motor geometrisi [mm] — TEK tanım noktası.
#: HRMA seçimi — geçerli port/boğaz oranlı örnek motor; literatür değeri
#: DEĞİLDİR. Kurucunun varsayılan argümanları, ``/calculate_solid``ın
#: ``SOLID_ENDPOINT_DEFAULTS`` tablosu ve ``solid.html`` açılış değerleri
#: (``outer_diameter`` / ``grain_length`` / ``core_diameter``; bekçi
#: ``tests/test_v301_kati_geometri.py``) bu sözlüğü okur.
#:
#: V301/K-A (22 Eki, ana model kararı): çekirdek 30 -> 48 mm. Eski örnek
#: motorda (Ø100 / 500 / 30, APCP, 40 bar, motorun varsayılan verimleri)
#: çözücünün boğazı 30,83 mm, yani A_port,0/A_t = 0,947 idi: port boğuluyor,
#: ses noktası lüle boğazı değildi ve yayımlanan Pc/itki modelin dışındaydı.
#: Ölçüt motorun kendi eşiği ``SOLID_DESIGN_POINT['port_to_throat_min']``
#: (= 2): oran çekirdeğe göre YENİDEN çözülerek tarandı (boğazı çözücü
#: boyutlar) — 44 mm 1,895, 46 mm 2,051, 48 mm 2,211 (eski API biçimi,
#: motor varsayılan verimleri; sayfa verimleriyle oran daha büyüktür).
#: 48 mm eşiğin %10 üstünde pay bırakan ilk çift sayıdır. Ölçüm:
#: ``docs/scofield/raw/OH/V301/kati-sivi/K-A/RAPOR.md``.
#:
#: V301/K-D (27 Eki, K-C2 DEVİR D1): tane boyu 500 -> 400 mm. Varsayılan yakıt
#: KNDX olunca (``SOLID_DEFAULT_PROPELLANT_TYPE``) eski tek çaplı API gövdesi
#: (``SOLID_ENDPOINT_DEFAULTS``; segment sayısı verilmediği için L/D kuralıyla
#: 5 segment) başlangıç kütle akısında motorun KENDİ eşiğini aşıyordu:
#: G0 = 1435,9 > ``SOLID_DESIGN_POINT['mass_flux_warn']`` = 1400 kg/m²s
#: (``warn.solid.initial_mass_flux_high``; sayfa gövdesi 3 segmentle 1057,8).
#: Uyarı gerçek bir bulgudur, yumuşatılmadı; varsayılan motor değişti.
#: Ölçüldü (``docs/scofield/raw/OH/V301/kati-sivi/K-D/``, varsayilan_*):
#: çekirdek 50/52 mm G0'ı eşiğin altına indiriyor ama sayfanın wagon_wheel
#: varsayılanını 422'ye düşürüyordu (delik geometrisi 48 mm çekirdeğe
#: kurulu); boy 400 mm'de çekirdek AYNI kalır, API gövdesi 4 segmente iner:
#: G0 1141,2 (eşiğin %18,5 altında), sayfa 1000,2; altı tane tipinin sayfa
#: varsayılanı 200 ve kritiksiz; APCP kurucusunda A_port,0/A_t 2,218 -> 2,789.
#: Boy/çap 4 (ipucunun 3:1-8:1 bandında).
SOLID_DEFAULT_GEOMETRY_MM = {
    'chamber_diameter': 100,
    'grain_length': 400,
    'core_diameter': 48,
}

#: Ürünün varsayılan (örnek) katı yakıt KİMLİĞİ — TEK tanım noktası. Okuyanlar:
#: ``/calculate_solid`` ve ``/api/solid-monte-carlo`` (``SOLID_ENDPOINT_DEFAULTS``),
#: ``/solid`` sayfasının açılışta seçili katalog satırı ve form termokimyası
#: (``propellant_form_values``), ``_resolve_propellant_type`` son dalı.
#:
#: V301/K-C2 (27 Eki, ana model kararı; K-B DEVİR 10): 'apcp' -> 'kndx'.
#: HRMA seçimi, literatür değeri değil. Gerekçe (ölçüm K-B/RAPOR.md §5
#: madde 8): APCP'li varsayılan motor ``nozzle_material_over_temp`` KRİTİĞİ
#: taşıyordu (T_aw 3338,5 K CEA ⟷ grafit 3300 K) ve kayıtlı hiçbir lüle
#: malzemesi o sıcaklığı taşımıyor; hüküm doğru, tek tasarım kolu yakıt.
#: KNDX kaydı ``validated: true``, ``c_star_basis: cea`` ve örnek projeyle
#: aynı yakıt.
SOLID_DEFAULT_PROPELLANT_TYPE = 'kndx'

#: Kütüphane kurucusunun (``SolidRocketEngine(...)``) varsayılan yakıt
#: argümanı — DEĞİŞMEDİ. Doğrudan kurucu çağıranlar (testler, uçuş aracı
#: yeniden hesabı) bugünkü sayılarını korur; ürün varsayılanı yukarıdaki
#: sabittir. İkisi de ``_resolve_propellant_type`` için "kimlik seçilmedi"
#: anlamı taşır (açık kimlik yalnız ``overrides['propellant_type']``).
SOLID_CONSTRUCTOR_PROPELLANT_TYPE = 'apcp'


class SolidRocketEngine:
    """Solid rocket motor analysis module"""

    def __init__(self, grain_type='bates',
                 propellant_type=SOLID_CONSTRUCTOR_PROPELLANT_TYPE,
                 chamber_diameter=SOLID_DEFAULT_GEOMETRY_MM['chamber_diameter'],
                 grain_length=SOLID_DEFAULT_GEOMETRY_MM['grain_length'],
                 core_diameter=SOLID_DEFAULT_GEOMETRY_MM['core_diameter'],
                 chamber_pressure=40,
                 burn_rate_a=DEFAULT_BURN_RATE_A,
                 burn_rate_n=DEFAULT_BURN_RATE_N,
                 burn_rate_temp_coeff=0.002, temp_ref=293.15,
                 overrides=None, propellant_lot=None):

        # Grain geometry
        # Tanınmayan tip SESSİZCE end_burner'a düşmez (2026-07-19 denetim):
        # kullanıcı 'finocyl' seçip bambaşka bir motor hesaplatıyordu.
        if grain_type not in SUPPORTED_GRAIN_TYPES:
            raise ValueError(
                f"Unsupported grain type '{grain_type}'. Supported grain "
                f"types: {', '.join(SUPPORTED_GRAIN_TYPES)}.")
        # ÖH D15 a3 (P2B1-07): FAIL-CLOSED girdi kapısı. Gerekçe ve ölçüm
        # _solid_geometry_gate künyesinde; kapı burada olduğu için HER
        # istemci (uçlar, Monte Carlo, doğrudan Python API) aynı sözleşmeyi
        # görür — uç başına kopya kapı yazılmaz.
        _solid_geometry_gate(grain_type, chamber_diameter, grain_length,
                             core_diameter, chamber_pressure, burn_rate_a)
        self.grain_type = grain_type
        self.D_chamber = chamber_diameter / 1000  # m
        self.L_grain = grain_length / 1000  # m
        self.D_core = core_diameter / 1000  # m

        # Propellant properties
        self.propellant_type = propellant_type
        self.P_c = chamber_pressure  # bar
        self.a = burn_rate_a  # burn rate coefficient
        self.n = burn_rate_n  # burn rate exponent
        self.burn_rate_temp_coeff = burn_rate_temp_coeff  # 1/K temperature coefficient
        self.temp_ref = temp_ref  # K reference temperature

        # UI'dan gelen opsiyonel parametreler (yakıt özellikleri, segman
        # sayısı, star geometrisi...). Monte Carlo yeniden kurulum için
        # constructor argümanları da saklanır.
        self.overrides = dict(overrides or {})
        # V301/K-D (K-C1 AÇIK 1): yakıt PARTİSİ bozulması — üretim toleransı
        # Monte Carlo'su ve UQ örnekleri içindir; istek gövdesinden GELMEZ
        # (``overrides`` kanalı kullanıcıya açık olduğu için ayrı argüman).
        self._propellant_lot = _propellant_lot_scales(propellant_lot)
        # Boğaz alanı sabitlemesi (T19): None = normal tasarım akışı, boğaz
        # tasarım noktasından boyutlandırılır. Yalnız ``pin_throat_area``
        # doldurur (üretim toleransı Monte Carlo'su).
        self._pinned_throat_area_m2 = None
        self._ctor_args = dict(
            grain_type=grain_type, propellant_type=propellant_type,
            chamber_diameter=chamber_diameter, grain_length=grain_length,
            core_diameter=core_diameter, chamber_pressure=chamber_pressure,
            burn_rate_a=burn_rate_a, burn_rate_n=burn_rate_n,
            burn_rate_temp_coeff=burn_rate_temp_coeff, temp_ref=temp_ref)

        # Tasarım uyarıları: _apply_overrides de uyarı üretebildiği için
        # (ör. kompozit kasada jenerik izin verilen gerilme) liste ondan
        # ÖNCE kurulur — aksi hâlde sonradan sıfırlanıp uyarılar kaybolurdu.
        self.design_warnings = []
        # Aralık dışı diye reddedilen anahtarlar (D1-KATI-OLU-1, ADIM 3):
        # _override_val itki eğrisi döngüsünde aynı anahtarla yüzlerce kez
        # çağrılabildiği için uyarı anahtar başına BİR kez üretilir.
        self._range_rejected_keys = set()
        # Çözücüye ULAŞMAYAN girdilerin ham (i18n'siz) beyan kanalı — Z2.
        # design_warnings ekran kanalıdır; bu liste makine-okur karşılığıdır.
        self.rejected_inputs = []

        # Yakıt kimliği: arayüz onu üç ayrı alanla anlatıyor (katalog anahtarı,
        # yanma-hızı ön ayarı, serbest metin ad) ve eskiden hiçbiri motora
        # ULAŞMIYORDU — bkz. _resolve_propellant_type. Termokimya, grain
        # mekaniği ve iki-fazlı kayıp bu anahtardan seçildiği için çözüm
        # _set_propellant_properties'ten ÖNCE yapılmak zorunda.
        self._resolve_propellant_type()

        # Set propellant properties
        self._set_propellant_properties()
        self._apply_overrides()
        self._check_burn_rate_coefficients()

        # Physical constants (BIPM standart yerce kimi, hrma.constants)
        self.g0 = G_0  # m/s^2

        # Tasarım noktası raporu (hedef verilmediyse boş kalır)
        self.design_point = None

        # Çağıran hedef ortalama itki / yanma süresi verdiyse grain geometrisi
        # bu hedeflere göre BOYUTLANDIRILIR. Hedef yoksa davranış birebir
        # eskisi gibidir (geometri girdisi tek belirleyicidir).
        self._apply_design_point_sizing()
        # V301/K-A: boyutlandırma tane dış çapını değiştirmiş olabilir;
        # kullanıcı kasa beyan ettiyse sığma kuralı YENİ taneyle yeniden
        # sınanır (hedef yoksa ya da kasa türetildiyse işlem yoktur).
        self._check_case_fit()

    def _override_val(self, key, lo, hi):
        """overrides[key] sonlu ve [lo, hi] içindeyse float döndürür, yoksa None.

        SESSİZ GERİ DÜŞME YASAĞI (v2.6.26, D1-KATI-OLU-1 ADIM 3): aralık
        dışı SONLU bir değer eskiden sessizce yok sayılıp tablo varsayılanına
        dönülüyordu — ölçümde discharge_coeff=1.47 girildiğinde 43 yaprak
        kullanıcının HABERİ OLMADAN değişti. Değer artık yine reddedilir ama
        red, design_warnings üzerinden kullanıcıya beyan edilir.

        Z2 (ÖH, P16B1-01'in katı motordaki ikizi) — **BOOLEAN REDDİ.** Eski
        gövde ``float(raw)`` ile başlıyordu, yani ``True`` sessizce ``1.0``
        oluyor ve BANDIN İÇİNDE olduğu için kabul ediliyordu. ÖLÇÜLDÜ
        (``POST /calculate_solid``, ``case_thickness: true``): 1,0 mm cidar →
        imalat tabanına kırpılıp 2,0 mm, ``vessel_status`` PASS,
        ``wall_thickness_source`` ``user_supplied``. Kullanıcının hiç
        girmediği bir sayı, onun cidarı diye doğrulanıyordu. Boolean bir
        BAYRAK değeridir; sayısal alanda değeri yoktur — depo bu ayrımı
        ``hrma/utils/input_guard.num`` içinde zaten yapıyordu
        (``isinstance(value, bool) -> InputError``), eksik olan tek şey aynı
        reddin bu okuyucuya taşınmasıydı. Red SESSİZ değildir:
        ``rejected_inputs`` listesine düz İngilizce gerekçeyle işlenir
        (``clipped_inputs`` / ``assumed_defaults`` ile aynı kanal deseni).
        """
        raw = self.overrides.get(key)
        if isinstance(raw, bool):
            self._reject_input(
                key, raw,
                'a boolean flag is not a numeric value; float(True) would '
                'have injected 1.0 into a field the user never filled in. '
                'The field was ignored and the built-in/catalog value was '
                'used instead.',
                code='boolean_is_not_a_number', accepted_range=(lo, hi))
            return None
        try:
            f = float(raw)
        except (TypeError, ValueError):
            # Alan HİÇ gelmediyse (None / '') beyan edilecek bir red yoktur;
            # ama bir DEĞER gelip sayıya çevrilemediyse bu sessiz kalamaz.
            # En sık hâli Türkçe ondalık ayracı: '5,0' burada düşüyordu ve
            # kullanıcı girdiğinin çözücüye ulaşmadığını hiç öğrenmiyordu.
            if raw is not None and raw != '':
                self._reject_input(
                    key, raw,
                    'could not be read as a number (check the decimal '
                    "separator: HRMA reads 5.0, not 5,0). The field was "
                    'ignored and the built-in/catalog value was used '
                    'instead.',
                    code='not_a_number', accepted_range=(lo, hi))
            return None
        if np.isfinite(f) and lo <= f <= hi:
            return f
        # Bool yukarıda ayrıldı; buraya yalnız sayısal (ya da sayıya çevrilen
        # metin) değerler düşer.
        if np.isfinite(f) and key not in self._range_rejected_keys:
            self._range_rejected_keys.add(key)
            self.design_warnings.append(dict(_w(
                'warn.solid.input_out_of_range', 'warning',
                field=key, value=round(f, 6),
                lo=round(float(lo), 6), hi=round(float(hi), 6)),
                fallback=("Input '{field}' = {value} is outside the accepted "
                          "range [{lo}, {hi}]; the field was ignored and the "
                          "built-in/catalog value was used instead.")))
            self._reject_input(
                key, raw,
                'value {} is outside the accepted range [{}, {}]; the field '
                'was ignored and the built-in/catalog value was used '
                'instead.'.format(round(f, 6), lo, hi),
                code='out_of_accepted_range', accepted_range=(lo, hi))
        elif not np.isfinite(f):
            # NaN / Infinity: eskiden hiçbir kanala girmeden yutuluyordu.
            self._reject_input(
                key, raw,
                'value is not finite (NaN or infinity); the field was '
                'ignored and the built-in/catalog value was used instead.',
                code='not_finite', accepted_range=(lo, hi))
        return None

    def _reject_input(self, key, raw, reason, code=None, accepted_range=None):
        """Reddedilen bir girdiyi BEYAN listesine işler (Z2, sessiz red yok).

        ``design_warnings`` i18n kodlu bir kanaldır; bu liste ise ham veri
        kanalıdır (``grain_design['clipped_inputs']`` /
        ``['assumed_defaults']`` ile aynı desen). İkisi birbirinin yerine
        geçmez: uyarı ekrana çıkar, bu liste ihracat/PDF/API tüketicilerinin
        "hangi alanım çözücüye ULAŞMADI" sorusunu makine-okur biçimde
        cevaplar. Alan başına TEK kayıt tutulur (itki eğrisi döngüsü aynı
        anahtarı yüzlerce kez okuyabilir).

        v3.0.1 (V301/K-A, KT-06/KT-13): kayıt makine kodunu
        (``reason_code``), kabul aralığını ve birimi de taşır.
        ``/calculate_solid`` bu listeyi 422 ``invalid_fields`` gövdesine
        çevirir: aralık dışı bir değerle tasarım YAYIMLANMAZ. Öteki
        çağıranlar (Monte Carlo örneklemleri, doğrudan Python API) listeyi
        bugünkü gibi beyan kanalı olarak okur. Dize değer 200 karaktere
        kısaltılır (aşırı uzun girdi gövdeye aynen yansımaz).
        """
        kayitlar = getattr(self, 'rejected_inputs', None)
        if kayitlar is None:
            kayitlar = self.rejected_inputs = []
        if any(k.get('field') == key for k in kayitlar):
            return
        if isinstance(raw, str):
            gonderilen = raw[:200]
        elif isinstance(raw, (int, float)) and not isinstance(raw, bool):
            gonderilen = raw
        else:
            gonderilen = repr(raw)[:200]
        kayit = {
            'field': key,
            'submitted_type': type(raw).__name__,
            'submitted_value': gonderilen,
            'reason': reason,
            'reached_solver': False,
        }
        if code is not None:
            kayit['reason_code'] = code
        if accepted_range is not None:
            kayit['accepted_range'] = [float(accepted_range[0]),
                                       float(accepted_range[1])]
            kayit['unit'] = SOLID_OVERRIDE_FIELD_UNITS.get(key)
        kayitlar.append(kayit)

    def _flag_true(self, key):
        """overrides[key] açıkça doğru mu? ('1', 'true', True, 1 kabul edilir)"""
        val = self.overrides.get(key)
        if isinstance(val, str):
            return val.strip().lower() in ('1', 'true', 'yes', 'on')
        return bool(val)

    def _flag_opt(self, key, default):
        """Bayrak alanı: anahtar hiç verilmemişse varsayılan davranış korunur.

        _flag_true eksik anahtarı False sayar; inhibitör bayraklarında bu,
        formu hiç kullanmayan çağıranların (test, importer) davranışını
        değiştirirdi. Eksik/boş anahtar = motorun eski varsayımı.
        """
        if key not in self.overrides or self.overrides.get(key) in (None, ''):
            return bool(default)
        return self._flag_true(key)

    def _throat_erosion_a_ref(self):
        """Kullanıcının verdiği boğaz erozyon katsayısı [mm/s @ 70 bar] veya None.

        F071 (2026-07-25): solid.html 'erosion_factor' alanını (birim etiketi
        mm/s) her koşuda backend'e gönderiyordu ama motor onu HİÇ okumuyordu —
        kullanıcı sayıyı değiştirip hiçbir çıktının kımıldamadığını görüyordu.
        Alan artık ampirik modelin referans katsayısı (a_ref, 70 bar'daki
        gerileme hızı) olarak okunur. 0 veya negatif değer 'erozyon yok'
        demektir (rijit boğaz varsayımı bilinçli seçilmiştir).
        """
        a_ref = self._override_val('throat_erosion_a_ref_mm_s',
                                   0.0, THROAT_EROSION_A_REF_MAX_MM_S)
        if a_ref is None:
            a_ref = self._override_val('erosion_factor',
                                       0.0, THROAT_EROSION_A_REF_MAX_MM_S)
        if a_ref is None or a_ref <= 0.0:
            return None
        return float(a_ref)

    def _burn_rate_publication(self):
        """Yanma hızı yasasının yanıttaki DÜRÜST gösterimi (Faz 5 / H2-4).

        Parçalı rejim tablosu (KNDX/KNSB) etkinken kullanıcının tek üslü
        ``a``/``n`` çifti hesaba HİÇ girmez. Bu durumda:
          * ``burn_rate_coefficient`` / ``burn_rate_exponent`` -> ``None``
            (kullanılmayan sayı "kullanılan katsayı" gibi gösterilmez),
          * kullanıcının girdisi ``*_input`` ekiyle ayrıca yayımlanır,
          * gerçekten kullanılan rejim tablosu ``burn_rate_law`` ile verilir.
        Yasa yoksa alanlar eskisi gibi tek üslü Saint-Robert çiftidir.
        """
        law_key = getattr(self, 'burn_rate_law_key', None)
        if not law_key:
            return {
                'burn_rate_coefficient': self.a,
                'burn_rate_exponent': self.n,
                'burn_rate_basis': (
                    'single-exponent Saint-Robert law r = a * Pc^n with the '
                    'coefficients supplied for this propellant'),
                'burn_rate_law': None,
            }
        try:
            from hrma.data import burn_rate_db as _brdb
            law = _brdb.BURN_RATE_LAWS[law_key]
            regimes = [dict(r) for r in law.get('regimes', [])]
            law_name = law.get('name')
            law_units = law.get('units')
            law_source = law.get('source')
        except Exception:
            regimes, law_name, law_units, law_source = [], None, None, None
        return {
            # Tek bir (a, n) çifti bu motorun yanma hızını TEMSİL ETMİYOR:
            # yanma boyunca Pc rejim sınırlarını geçiyor ve her rejimin kendi
            # üsteli var (KNDX'te bir rejimde n negatif). Sayı uydurulmaz.
            'burn_rate_coefficient': None,
            'burn_rate_exponent': None,
            'burn_rate_coefficient_input': self.a,
            'burn_rate_exponent_input': self.n,
            'burn_rate_basis': (
                'piecewise regime table "%s" evaluated at the INSTANTANEOUS '
                'chamber pressure; the single a/n pair entered for this '
                'motor was NOT used (no single exponent represents this law)'
                % law_key),
            'burn_rate_law': {
                'key': law_key,
                'name': law_name,
                'units': law_units,
                'source': law_source,
                'regimes': regimes,
            },
        }

    def unwired_inputs(self):
        """Çözücünün BİLİNÇLİ olarak kullanmadığı form alanları.

        Sıvı motorda bu beyan v2.6.26'da vardı, katıda YOKTU. Beyansız alan
        arayüzde normal bir girdi gibi duruyor, kullanıcı değer giriyor ve
        hiçbir sayı değişmiyor — üstelik bunu anlamasının yolu yok. Bağlama
        haritası bu yüzden katıda 25 alanı "ölü" gösteriyordu: ne bağlıydılar
        ne de bağlı olmadıklarını söylüyorlardı.

        Kural (kayıt defteriyle aynı): bir alan ya fiziğe bağlanır ya burada
        gerekçesiyle bildirilir. Üçüncü seçenek — sessizlik — yasaktır.
        Buradaki bir alan sonradan bağlanırsa listeden ÇIKARILMALIDIR;
        Katman B bekçisi beyan çürümesini `declared_but_live` ile yakalar.
        """
        return {
            # Çözücünün KENDİSİ hesapladığı büyüklükler. Kullanıcının girdiği
            # değer kütle dengesini ezmez: boğaz alanı A_t = mdot·c*/(Pc·Cd),
            # genişleme oranı ve itergaç kütlesi grain geometrisinden çıkar.
            # Alanlar formda karşılaştırma kolaylığı için duruyor.
            'computed_by_solver': [
                'throat_diameter', 'exit_diameter', 'expansion_ratio',
                'propellant_mass', 'dry_mass', 'wet_mass',
                # Kamara hacmi grain yığınından, web kalınlığı grain iç/dış
                # çapından TÜREtİLİR. Kullanıcının girdiği değer okunur ama
                # türetilen değeri ezmez; ölçümde "yalnız kendi yankısı"
                # olarak görünüyorlardı.
                #
                # v2.6.26 (kalem 29): 'outer_diameter' bu listeden ÇIKARILDI.
                # Beyanı zaten yanlıştı — metin "kasa dış çapı iç çap +
                # 2·cidar kalınlığından türetilir" diyerek BAŞKA bir
                # büyüklüğü anlatıyor, oysa alan grain dış çapıdır. Alan
                # artık grain dış çapının doğruluk kaynağıdır
                # (_apply_overrides 7c), yani bağlıdır.
                'chamber_volume', 'web_thickness',
            ],
            # Kullanıcının BEYAN ettiği toplam verim: rapora yazılır ama itki
            # zincirine ikinci kez çarpılmaz. Çift sayım olurdu — bileşen
            # verimleri (c*, lüle, kinetik, iki-fazlı) zaten ayrı ayrı
            # uygulanıyor. Bekçi: test_solid_safety_real.py::
            # test_declared_overall_efficiency_is_reported_not_double_counted
            'reported_not_double_counted': [
                'overall_efficiency',
            ],
            # Yapısal analizin geometri + malzemeden hesapladığı kütleler.
            # v2.6.0'da kuru kütle "itergaç kütlesinin %25'i" başparmak
            # kuralından yapısal hesaba taşınmıştı; kullanıcının elle girdiği
            # kütleyi kabul etmek o zinciri geri bozardı.
            #
            # 'avionics_mass' bu gerekçeye UYMAZ (V305/C1, 28 Eki): yapısal
            # analiz onu hesaplamaz, motorun kalemi değildir; araç kalemi
            # olarak sayfanın kütle uzlaştırma tablosu formdaki kuru kütle
            # toplamına ekler (solid.html renderInertReconcile /
            # updateTotalMasses). Motor çözücüsü okumaz; listede kalması
            # "çözücü okumaz" beyanı içindir (kategori adı tarihseldir).
            'structural_output': [
                'case_mass', 'nozzle_mass', 'closure_mass',
                'insulation_mass', 'avionics_mass',
                # V301/K-B (NK-30): astar kütlesi satırı (çıktı).
                'liner_mass',
            ],
            # Statik ateş test DÜZENEĞİ parametreleri: ölçüm zincirini
            # tanımlarlar, motorun kendisini değil. Motor performansına
            # girmeleri fiziksel olarak yanlış olurdu.
            'test_bench_only': [
                'calibration_factor', 'data_collection_time', 'filter_cutoff',
                'load_cell_capacity', 'pressure_sensor_range', 'sampling_freq',
                'uncertainty_level',
            ],
            # Grain kesit AYRINTISI: yıldız VADİ FİLETO yarıçapı. Ofset
            # (buffer) ilerledikçe vadi köşeleri fiziksel olarak zaten
            # yuvarlandığı için ayrı bir fileto parametresi modellenmiyor ve
            # katsayı UYDURULMAZ.
            #
            # ÖH D15 a2 (P2B1-06) — BEYAN ÇÜRÜMESİ GİDERİLDİ. Bu liste
            # eskiden 'star_radius' ve 'fin_length'i de içeriyordu; ikisi de
            # CANLI ve geometriyi belirliyor. ÖLÇÜLDÜ (D=100, core=30, L=500,
            # APCP, 40 bar):
            #   star_radius  5 / 15 / 40 mm -> derinlik 5,00 / 15,00 / 28,00 mm
            #                (40 kırpıldı), ortalama itki 2466,10 / 2779,55 /
            #                2468,27 N -> salınım %12,71, Isp 224,57-230,65 s
            #   fin_length   5 / 20 / 34 mm -> derinlik 5,00 / 20,00 / 29,75 mm
            #                ortalama itki 2675,94 / 2962,81 / 3100,31 N ->
            #                salınım %15,86, Isp 226,34-237,73 s
            #   star_fillet  1 / 5 / 10 mm  -> üç değerde de BİT-AYNI sonuç
            #                (gerçekten ölü; beyan yalnız onun için doğruydu)
            # Sistematik süpürmede (B1-repro-24) star_radius 2791,
            # fin_length 2859 yayımlanan yaprağı değiştiriyordu. Modülün
            # kendi kuralı yukarıda yazılı: "Buradaki bir alan sonradan
            # bağlanırsa listeden ÇIKARILMALIDIR."
            'geometry_not_modelled': [
                'star_fillet',
            ],
            # ÖH D20 (P15B3-05) — YAYIMLANAN SONUCUN ADIYLA GÖNDERİLEN
            # GİRDİ. ``c_star`` bu ucun bir ÇIKTI adıdır (solid.html:2060
            # `{id:'char_velocity', field:'c_star'}` haritası onu SONUÇ
            # alanından okur), ama istemciler onu GİRDİ diye gönderiyor —
            # kampanyanın kendi taban yükü dâhil (tests/test_faz5_motor.py:55
            # 'c_star': 1550). ÖLÇÜLDÜ (docs/scofield/raw/OH/D20/kati/a1/
            # once.json + 01_capa_ONCE.json):
            #
            #   gönderilen c_star   HTTP   yayımlanan c_star   yanıt gövdesi
            #   (gönderilmedi)      200         1598,2         sha 930190dd…
            #   100 / 900 / 1550 / 2400
            #                       200         1598,2         sha 930190dd…
            #
            # yani dört değerin dördü de tabanla BİT-AYNI gövde üretiyor:
            # alan ne bağlıydı ne de bağlı olmadığını söylüyordu — modülün
            # kendi kuralının yasakladığı ÜÇÜNCÜ SEÇENEK, sessizlik.
            #
            # Alan BAĞLANMAZ, çünkü c* yakıt kaydının termokimyasından
            # (CEA-tutarlı katalog) gelir ve aynı kayıttaki gamma, T_c, M ve
            # iki-fazlı kayıp zinciriyle TEK bir çözümün parçasıdır;
            # kullanıcının tek bir sayıyı dışarıdan ezmesi, yayımlanan
            # termokimyayla çelişen bir motor üretirdi. Kullanıcı gerçekten
            # başka bir c* istiyorsa yol yakıt kaydını seçmek/tanımlamaktır.
            'result_of_catalogue_thermochemistry': [
                'c_star',
            ],
            # Kayıt/ortam alanları: test günü koşulları ve itergaç ısıl
            # değeri. Isıl değer c*'ı belirlemez (c* CEA/katalog kaydından
            # gelir); nem ve rüzgâr bu sürümün tasarım-noktası çözücüsünde
            # modellenmez. Ateşleme gecikmesi geçici rejim konusudur.
            'informational': [
                'humidity', 'wind_speed', 'heat_value', 'ignition_delay',
            ],
            # FAZ 5 / H2-4: katalog yakıtında (KNDX/KNSB) yanma hızı parçalı
            # rejim tablosundan ANLIK basınçla okunur; kullanıcının tek üslü
            # a/n çifti hesaba GİRMEZ (ölçüldü: n = 0,2 / 0,688 / 0,95 ->
            # 15 anlamlı basamak aynı sonuç). Yasa etkin DEĞİLKEN bu liste
            # boştur, çünkü o zaman alanlar gerçekten canlıdır — beyan
            # çürümesi (`declared_but_live`) böyle önlenir.
            'overridden_by_regime_table': (
                ['burn_rate_coefficient', 'burn_rate_exponent']
                if getattr(self, 'burn_rate_law_key', None) else []
            ),
            # V301/K-B (KT-04/05): gönderilen erozif k / σ kalibre yakıt
            # tablosu varken bayraksız geldi ve UYGULANMADI (kip 'katalog').
            'overridden_by_catalogue': (
                (['erosive_k'] if getattr(self, '_erosive_k_not_applied',
                                          False) else [])
                + (['temp_coeff'] if getattr(self, '_temp_coeff_not_applied',
                                             False) else [])),
            # V301/K-B (KT-12): akma kaynağı 'material' iken gönderilen
            # yield_strength uygulanmadı (cidar ve patlama aynı kayıttan).
            'overridden_by_material': (
                ['yield_strength'] if getattr(self, '_yield_not_applied',
                                              False) else []),
            # V301/K-B (KT-07): tane tipine göre anlamı olmayan alanlar —
            # YALNIZ gönderildiyse listelenir (beyan çürümesi olmasın).
            'not_applicable_to_grain_type': [
                ad for ad in self._grain_type_inapplicable_fields()
                if self.overrides.get(ad) not in (None, '')],
        }

    def _nozzle_material_key(self):
        """Kullanıcının seçtiği lüle malzemesinin normalleştirilmiş anahtarı.

        V301/K-B (KT-10): materials_db takma adı KANONİK ada çözülür
        ('c-c' -> 'carbon_carbon'); hibrit M deseniyle aynı. Çözülemeyen ad
        ham kalır (doğrudan motor kullanımında ``not_analyzed`` + gerekçe;
        ``/calculate_solid`` onu 422 ile reddeder).
        """
        ham = str(self.overrides.get('nozzle_material')
                  or self.overrides.get('throat_material')
                  or SOLID_NOZZLE_DEFAULT_MATERIAL).strip().lower().replace(
                      ' ', '_')
        kayit = solid_nozzle_material_record(ham)
        return kayit['material_key'] if kayit is not None else ham

    def analyze_nozzle_material(self):
        """Seçilen lüle malzemesinin boğaz termal marjı + erozyon durumu.

        v2.6.26 — arayüzdeki "Nozzle Material" seçicisi KATI motorda hiçbir
        hesaba girmiyordu: yalnız ``_nozzle_erosion_reference`` içinde
        okunuyordu ve yayımlanmış erozyon bandı olan malzemeler (grafit, C-C)
        dışında hiçbir çıktıyı değiştirmiyordu. Bağlama ölçümünde alan ÖLÜ
        çıkıyordu — kullanıcı tungsten seçip grafit sonucunu görüyordu ve
        bunu anlamasının hiçbir yolu yoktu. (Hibrit motorda aynı alan
        v2.6.26'da bağlanmıştı; katı tarafı yarım kalmıştı.)

        Bağlanan iki çıktı:

        1. **Boğaz termal marjı.** Boğaz istasyonundaki adyabatik cidar
           sıcaklığı T_aw (M=1, kurtarma faktörü r = Pr^(1/3)) malzemenin
           izin verilen sıcaklığıyla karşılaştırılır. Katı motor boğazı
           tipik olarak SOĞUTMASIZDIR (grafit/ablatif); soğutmasız cidar
           yanma boyunca T_aw'a yaklaşır, bu yüzden marj o en kötü duruma
           göre verilir ve varsayım çıktıda açıkça yazılır.
        2. **Erozyon.** Yayımlanmış katsayı bandı olan malzemede model
           bağlanır; olmayanda katsayı UYDURULMAZ, "no published data" denir.

        Malzemenin materials_db kaydı yoksa sayı üretilmez: ``not_analyzed``
        döner ve nedeni yazar (şablondaki 'phenolic' seçeneğinin kaydı yok).
        """
        from hrma.data.materials_db import get_material

        key = self._nozzle_material_key()
        rapor = {'material': key}
        try:
            mat = get_material(key)
        except (KeyError, ValueError):
            rapor.update({
                'status': 'not_analyzed',
                'reason': (f"nozzle material '{key}' has no materials_db "
                           f"record; no thermal limit is invented"),
                'erosion': ('modelled' if self._nozzle_erosion_reference()
                            else 'no published data'),
            })
            return rapor

        # ÖH D37 A2-1 / F-01 + M2 (patch/motor_m2.patch): lüle malzeme
        # eşiği TEK fonksiyondan — merdivenin İZİN basamağı; eski zincir
        # (allowable → max_service_temperature → max_service_temp → melting)
        # ikinci adımda KLAMPI (çoğu kayıtta erime) izin sınırı sayabilirdi.
        # graphite'te 3300 K bit-aynı.
        from hrma.data.materials_db import temperature_limits
        _tl = temperature_limits(mat)
        izin = _tl['allowable_K'] or _tl['melting_K']
        try:
            from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
            analyzer = HeatTransferAnalyzer()
            # B11 seçenek F: ısı akısıyla AYNI gamma seçimi (_bartz_gas_gamma),
            # yoksa bu T_aw boğaz akısının T_aw'ından ayrışır.
            gas = analyzer._get_gas_properties(
                {'gamma': self._bartz_gas_gamma(),
                 'molecular_weight': getattr(self, 'mw_exhaust', 26.0)},
                self.T_c,
            )
            # _calculate_heat_flux ile AYNI istasyon ve aynı yöntem: boğaz,
            # M=1. İki yerde iki farklı T_aw çıkmasın diye kasten aynı çağrı.
            t_aw = float(analyzer._adiabatic_wall_temperature(
                self.T_c, gas, mach_local=1.0))
        except Exception as exc:
            rapor.update({'status': 'not_analyzed',
                          'reason': f'throat gas state unavailable: {exc}'})
            return rapor

        rapor.update({
            'status': 'analyzed',
            'adiabatic_wall_temperature_k': round(t_aw, 1),
            'cooling_assumption': 'uncooled throat (worst case: T_wall -> T_aw)',
            'erosion': ('modelled' if self._nozzle_erosion_reference()
                        else 'no published data'),
            'warnings': [],
        })
        if izin:
            izin = float(izin)
            rapor['allowable_temperature_k'] = round(izin, 1)
            rapor['thermal_margin_k'] = round(izin - t_aw, 1)
            rapor['thermal_margin_ratio'] = round(izin / t_aw, 3) if t_aw > 0 else None
            # ÖH P16S1-07: hüküm makine-okunur bir alanda da durur. Hibrit
            # motorun aynı bloğu bunu (``throat_thermal.verdict``) zaten
            # yayımlıyordu; katıda yalnız marj sayıları vardı, "geçti mi"
            # sorusunun cevabı için tüketicinin eşiği KENDİ kıyaslaması
            # gerekiyordu. Sayı uydurulmuyor: hüküm yukarıdaki iki sayının
            # kıyasının ta kendisi.
            rapor['verdict'] = 'SAFE' if t_aw <= izin else 'EXCEEDS_ALLOWABLE'
            if t_aw > izin:
                rapor['warnings'].append(_w(
                    'warn.solid.nozzle_material_over_temp', 'critical',
                    material=key, t_aw_k=round(t_aw, 1),
                    allowable_k=round(izin, 1)))
        else:
            rapor['verdict'] = 'NOT_EVALUATED'
            rapor['reason'] = (f"materials_db record for '{key}' carries no "
                               f"temperature limit; margin not computed")
        return rapor

    def _nozzle_erosion_reference(self):
        """Seçili nozul malzemesinin yayımlanmış erozyon modeli (yoksa None).

        Yalnız transient_ballistics tablosunda kaydı OLAN malzemeler için
        döner (grafit, C-C). Fenolik/tungsten için yayımlanmış bant yok →
        katsayı uydurulmaz, None döner.
        """
        key = self._nozzle_material_key()
        mapped = SOLID_NOZZLE_EROSION_MATERIAL.get(key)
        if not mapped:
            return None
        from hrma.analysis.transient_ballistics import ThroatErosionModel
        try:
            return ThroatErosionModel.for_material(mapped)
        except ValueError:
            return None

    def _throat_erosion_model(self):
        """Çözücüye takılacak erozyon modeli — kullanıcı katsayısı yoksa None.

        Model transient_ballistics.ThroatErosionModel'dir; burada yalnız
        a_ref seçilir (tek tanım noktası: formül orada).
        """
        a_ref = self._throat_erosion_a_ref()
        if a_ref is None:
            return None
        from hrma.analysis.transient_ballistics import ThroatErosionModel
        ref = self._nozzle_erosion_reference()
        return ThroatErosionModel(
            a_ref,
            material=(ref.material if ref else 'user_supplied'),
            material_display=(ref.material_display if ref
                              else 'User-supplied coefficient'),
            a_ref_band_mm_s=(ref.a_ref_band_mm_s if ref else None),
            # Bandın künyesi/atıf durumu da taşınır (D19/P2B4-09): kullanıcı
            # kendi a_ref'ini verse bile YAN YANA basılan bandın nereden
            # geldiği ve atfedilmiş olup olmadığı yanıtta görünür.
            band_source=(ref.band_source if ref else None),
            band_attributed=(bool(ref.band_attributed) if ref else False),
            # D27/OH-D24-11 (b): bandı OLMAYAN ama ölçüme çapalanmış
            # malzemede (C-C) katsayının künyesi buradan taşınır; yoksa
            # kullanıcı yanıtta 'band_attributed False' görüp katsayıyı
            # kaynaksız sanır.
            anchor_source=(ref.anchor_source if ref else None),
            anchor_attributed=(bool(ref.anchor_attributed) if ref else False),
            source='user-supplied coefficient (solid.html erosion_factor)')

    def _nozzle_erosion_estimate(self):
        """CAD lüle panelinde yayımlanan erozyon tahmini — TEK tanım noktası.

        ÖH D26 a2 (P2B1-03 + P2B3-03). Bu tahmin ``_design_nozzle_geometry``
        içinde KOŞULSUZ ``ThroatErosionModel.for_material('graphite')`` ile
        kuruluyordu: ne kullanıcının lüle malzemesini ne de çözücünün fiilen
        koştuğu erozyon katsayısını okuyordu. ÖLÇÜLDÜ
        (docs/scofield/raw/OH/D26/kati/a2/once.json):

          erosion_factor  çözücünün hızı @40 bar   yayımlanan tahmin
          (yok)           -                        0,1598 mm/s
          0,001           0,000639 mm/s            0,1598 mm/s
          0,05            0,031955 mm/s            0,1598 mm/s
          0,15            0,095865 mm/s            0,1598 mm/s

        yani çözücü 150 KAT değişirken yayımlanan sayı kımıldamıyordu
        (``ayirt_edici_yayimlanan_hiz = 1/4``). Malzeme ekseninde de aynısı:
        graphite / carbon_carbon / C-C / steel / tungsten / phenolic — altı
        seçimin altısında da ``material = 'graphite'`` ve 0,1598 mm/s
        yayımlanıyordu, üstelik ``analyze_nozzle_material`` AYNI yanıtta
        çelik/tungsten/fenolik için "no published data" diyorken.

        Kaynak sırası artık ÇÖZÜCÜYLE AYNIDIR:

          1. Kullanıcı bir katsayı verdiyse (``erosion_factor`` /
             ``throat_erosion_a_ref_mm_s``) çözücünün taktığı model
             (``_throat_erosion_model``) — aynı a_ref, aynı formül.
          2. Yoksa seçilen lüle malzemesinin YAYIMLANMIŞ modeli
             (``_nozzle_erosion_reference``).
          3. İkisi de yoksa SAYI YAYIMLANMAZ (fail-closed): yayımlanmış
             bandı olmayan malzemede grafit katsayısı UYDURULMAZ, durum ve
             hangi alanın doldurulacağı adıyla söylenir.
        """
        pc_bar = float(self.P_c)
        model = self._throat_erosion_model() or self._nozzle_erosion_reference()
        secilen = self._nozzle_material_key()
        pc_ref = _throat_erosion_pc_ref_bar()
        if model is None:
            return {
                'status': 'not_evaluated',
                'rate_mm_s': None,
                'band_mm_s': None,
                'chamber_pressure_bar': pc_bar,
                'material': secilen,
                'coefficient_source': None,
                'reason': (
                    f"No published throat erosion coefficient exists in this "
                    f"repository for '{secilen}', and none was supplied. A "
                    f"graphite coefficient is NOT substituted: the number "
                    f"would not belong to the material you selected. Supply a "
                    f"test-derived a_ref in 'erosion_factor' [mm/s at "
                    f"{pc_ref:g} bar], or choose a material that carries a "
                    f"published band."),
                'input_field': f'erosion_factor [mm/s at {pc_ref:g} bar]',
            }
        rate = model.rate_mm_s(pc_bar)
        scale = (pc_bar / model.pc_ref_bar) ** model.exponent
        band = model.a_ref_band_mm_s
        kullanici_katsayisi = self._throat_erosion_a_ref() is not None
        return {
            'status': 'computed',
            'rate_mm_s': round(rate, 4),
            'band_mm_s': (None if not band else
                          [round(band[0] * scale, 4),
                           round(band[1] * scale, 4)]),
            'band_source': model.band_source,
            'band_attributed': bool(model.band_attributed),
            # D27: band yoksa katsayının çapası adıyla yayımlanır (C-C tek
            # ölçüm noktasına çapalıdır; bant-dışı denetimi uygulanmaz).
            'anchor_source': model.anchor_source,
            'anchor_attributed': bool(model.anchor_attributed),
            # D28/OH-D27-15: ÜS de katsayı kadar bir modelleme kararıdır ve
            # buraya kadar künyesiz yayımlanıyordu ('model' dizgesinde sayı
            # görünüyor, nereden geldiği görünmüyordu). Kaynağın ÖLÇTÜĞÜ
            # basınç aralığı ve bu motorun o aralığın dışında olup olmadığı
            # da yayımlanır — sessiz ekstrapolasyon yok.
            'exponent': model.exponent,
            'exponent_source': model.exponent_source,
            'exponent_attributed': bool(model.exponent_attributed),
            'exponent_valid_pc_bar': (list(model.exponent_valid_pc_bar)
                                      if model.exponent_valid_pc_bar
                                      else None),
            'exponent_extrapolated': model.exponent_extrapolated(pc_bar),
            'chamber_pressure_bar': pc_bar,
            'material': model.material,
            'material_display': model.material_display,
            'nozzle_material_selected': secilen,
            'coefficient_source': ('user_supplied' if kullanici_katsayisi
                                   else 'material_record'),
            'model': (f"r_dot = a_ref*(Pc/{model.pc_ref_bar:g} bar)"
                      f"^{model.exponent:g}, a_ref = "
                      f"{model.a_ref_mm_s:g} mm/s "
                      + ('(coefficient supplied by the user; this is the same '
                         'a_ref the transient solver runs with)'
                         if kullanici_katsayisi
                         else '(conservative end of the published band for '
                              'this material)')),
            'note': ('Empirical estimate (approximate); multiply by burn '
                     'duration for total throat recession. Time-coupled '
                     'Pc(t) effect available via TransientBallistics'
                     '(erosion_enabled=True).'),
            'source': model.source,
        }

    def _throat_erosion_report(self, model, area_initial, area_final):
        """Boğaz erozyonunun koşudaki durumu (JSON-uyumlu, dürüst rapor).

        Erozyon kapalıyken 'enabled': False döner ve varsayımın adı açıkça
        yazılır ('rigid-throat assumption') — sessiz kabul yok.
        """
        area_initial = float(area_initial or 0.0)
        area_final = float(area_final or 0.0)
        growth = ((area_final / area_initial - 1.0)
                  if area_initial > 0 else 0.0)
        report = {
            'enabled': model is not None,
            'throat_area_initial_m2': area_initial,
            'throat_area_final_m2': area_final,
            'area_growth_fraction': growth,
            'throat_diameter_initial_mm': (
                2000.0 * np.sqrt(area_initial / np.pi) if area_initial > 0
                else 0.0),
            'throat_diameter_final_mm': (
                2000.0 * np.sqrt(area_final / np.pi) if area_final > 0
                else 0.0),
        }
        if model is None:
            report['basis'] = (
                'rigid-throat assumption (no erosion coefficient supplied)')
            report['input_field'] = (
                'erosion_factor [mm/s at %g bar]'
                % _throat_erosion_pc_ref_bar())
        else:
            report['basis'] = model.describe()
            report['material'] = model.material_display
            report['source'] = model.source
        return report

    def _check_burn_rate_coefficients(self):
        """Girilen Saint-Robert a katsayısını merkezi katalogla karşılaştırır.

        FİZİK DENETİMİ (F024): kurucu varsayılanı düzeltildi ama çağıran
        (ör. /calculate_solid uç noktası, form alanı) hâlâ MPa tabanlı 0.005
        gönderebiliyor. O durumda hesap SESSİZCE 2.24 kat hızlı yanan bir
        yakıt modeller — yanma süresi yarıya iner, ortalama itki iki katına
        çıkar, boğaz 2.4 kat büyür (toplam impuls doğru kalır, bu yüzden hata
        gözle görülmez). Bu uyarı o sapmayı kullanıcıya görünür kılar.

        Kaynak: hrma/data/burn_rate_db.py docstring (aynı birim hatası);
        Sutton & Biblarz 9. baskı Böl. 12 yanma hızı bandı.
        """
        a_cat, n_cat = _catalog_burn_rate(self.propellant_type)
        if not a_cat or self.a <= 0:
            return
        # a-n çifti birlikte anlamlıdır: karşılaştırma REFERANS BASINCINDA
        # (katalog konvansiyonu) yapılan yanma hızı üzerinden yapılır.
        from hrma.data.propellants_db import PROPELLANT_REFERENCE_PRESSURE_BAR
        p_ref = float(PROPELLANT_REFERENCE_PRESSURE_BAR)
        r_user = self.a * p_ref ** self.n
        r_cat = float(a_cat) * p_ref ** float(n_cat)
        if r_cat <= 0:
            return
        ratio = r_user / r_cat
        if ratio > BURN_RATE_A_MISMATCH_RATIO or ratio < 1.0 / BURN_RATE_A_MISMATCH_RATIO:
            self.design_warnings.append(_w(
                'warn.solid.burn_rate_off_catalog', 'warning',
                propellant=self.propellant_type,
                pressure_bar=round(p_ref, 1),
                user_rate_mmps=round(r_user * 1000.0, 2),
                catalog_rate_mmps=round(r_cat * 1000.0, 2),
                ratio=round(ratio, 2)))

    def _apply_overrides(self):
        """Formdan gelen değerlerle yakıt tablosu değerlerini ez (2026-07-13).

        Harita bulgusu: UI ~60 alan gönderiyordu, motor 8'ini kullanıyordu —
        kullanıcı yoğunluk/C*/gama değiştirse de hesaba etki etmiyordu.
        Yalnız sonlu ve fiziksel aralıktaki değerler uygulanır; boş/uçuk
        değer sessizce tablo değerinde kalır.

        Bilinçli KABLOLANMAYANLAR: throat/exit/expansion girişleri — UI
        default'ları (15/35 mm) fiziksel boğaz boyutlandırmasını ezmesin
        diye motor kendi kütle dengesinden boyutlandırmaya devam eder.
        """
        # V301/N-CEA-2 (K1): kaydın termokimya dörtlüsü form ezmelerinden
        # ÖNCE saklanır; CEA yalnız kullanıcı bunları değiştirmediyse
        # uygulanır (sayfa katalog satırını seçince aynı değerleri gönderir).
        kayit_termo = (self.c_star, self.gamma, self.T_c,
                       getattr(self, 'mw_exhaust', None))
        m = self._override_val('density', 500.0, 3000.0)
        if m is not None:
            self.rho_p = m
        # V301/K-D: parti yoğunluk çarpanı motorun KENDİ yoğunluğuna (kayıt
        # ya da kullanıcının girdiği değer) uygulanır; çarpan 1 iken bit-aynı.
        if self._propellant_lot is not None:
            self.rho_p = self.rho_p * self._propellant_lot['density_scale']
        from hrma.data.propellants_db import PROPELLANT_C_STAR_RANGE_M_S
        m = self._override_val('char_velocity',
                               *PROPELLANT_C_STAR_RANGE_M_S)
        if m is not None:
            self.c_star = m
        m = self._override_val('gamma', 1.05, 1.5)
        if m is not None:
            self.gamma = m
        m = self._override_val('flame_temp', 1000.0, 4500.0)
        if m is not None:
            self.T_c = m
        # Egzoz molekül ağırlığı (O1, v2.6.26): form alanı motora ULAŞMIYORDU.
        # Bartz ısı akısı gaz özellikleri (cp, mu, Pr) M üzerinden çözülür;
        # KNDX'te (M = 42.39) yakıt tablosunun 28.0'ı kullanıldığı için boğaz
        # ısı akısı %45 fazla raporlanıyordu. Aralık: gerçekçi katı yakıt
        # egzoz bandını fazlasıyla kapsayan sayısal koruma sınırı.
        m = self._override_val('molecular_weight', 2.0, 100.0)   # g/mol
        if m is not None:
            self.mw_exhaust = m
        # Yakıt ADI: kullanıcının yazdığı / kataloğun uyguladığı ad korunur.
        # Eskiden motor tablosunun adı KOŞULSUZ eziyordu — KNDX seçen kullanıcı
        # raporlarda 'Ammonium Perchlorate Composite Propellant' görüyordu.
        name = self.overrides.get('propellant_name')
        if isinstance(name, str) and name.strip():
            self.propellant_name = name.strip()[:120]
        m = self._override_val('nozzle_efficiency', 0.80, 1.0)
        if m is not None:
            self.nozzle_efficiency = m
        # ------------------------------------------------------------------
        # FİZİK DENETİMİ DÜZELTMESİ (F065, 2026-07-25): erozif katsayı ve
        # sıcaklık duyarlılığı FORM VARSAYILANIYLA ezilemez.
        #
        # Eskiden solid.html her koşuda erosive_k=0.0002 ve temp_coeff=0.002
        # gönderiyordu; bu değerler yakıt tablosunu (APCP k=0.0136, σp=0.0042)
        # koşulsuz eziyordu. Sonuç: yakıt-başına kalibre edilmiş k 68 kat
        # küçülüyor ve erozif yanma varsayılan koşuda fiilen KAPANIYORDU.
        # 0.0002 / 0.002 form varsayılanlarının hiçbir literatür dayanağı
        # yoktur (denetim: 'kaynak bulunamadı'), yakıt tablosu değerlerinin
        # ise vardır — bu yüzden ÖNCELİK YAKIT TABLOSUNDADIR.
        #
        # ÖH D15 (P2B1-02): önceki adım kusuru YALNIZ BEYAN ediyordu —
        # form değeri gene uygulanıyor, üstüne bir uyarı ekleniyordu. Ölçüldü
        # (D_kasa=100 mm, D_çekirdek=12 mm, L=1000 mm, 40 bar): kullanıcı
        # alanlara HİÇ dokunmadan gelen 0,0002/0,002 çifti Isp'yi 205,92 ->
        # 234,34 s (+%13,80), toplam impulsu +%13,80 kaydırıyor ve eğrideki
        # TEPE İTKİYİ 13.423 -> 7.851 N'a (-%41,5) düşürüyordu; yani kasa ve
        # kapak yükleri gerçeğin %41,5 ALTINDA gösteriliyordu. Beyan çözüm
        # değildir: kalibre bir tablo değeri varken BEYAN EDİLMEMİŞ form
        # değeri artık uygulanmaz. Kullanıcının bilinçli girdisi hâlâ
        # geçerlidir — 'erosive_k_override' / 'temp_coeff_override' bayrağı
        # bunu açıkça söyler; tabloda kalibre değer yoksa (jenerik yakıt)
        # form değeri zaten tek kaynaktır ve uygulanır.
        # ------------------------------------------------------------------
        kalibre = getattr(self, '_table_coeff_present', {})
        table_k = getattr(self, 'erosive_burning_coeff', 0.0)
        self._erosive_k_not_applied = False
        self._temp_coeff_not_applied = False
        m = self._override_val('erosive_k', 0.0, 1.0)
        self.erosive_coefficient_source = (
            'propellant table ({0})'.format(self.propellant_type)
            if kalibre.get('erosive_burning_coeff') else
            'solver default (no calibrated table value for this propellant)')
        if m is not None and not np.isclose(m, table_k, rtol=1e-6, atol=0.0):
            beyanli = self._flag_true('erosive_k_override')
            if beyanli or not kalibre.get('erosive_burning_coeff'):
                self.erosive_burning_coeff = m
                self.erosive_coefficient_source = (
                    'user-declared form value (erosive_k with '
                    'erosive_k_override)' if beyanli else
                    'form field erosive_k (no calibrated table value for '
                    'this propellant)')
                if not beyanli:
                    self.design_warnings.append(_w(
                        'warn.solid.erosive_k_overridden', 'warning',
                        form_value=float(m), table_value=float(table_k),
                        propellant=self.propellant_type))
            else:
                # V301/K-B (KT-04): gönderilip UYGULANMAYAN değer adıyla
                # bildirilir (unwired_inputs.overridden_by_catalogue).
                self._erosive_k_not_applied = True
                self.erosive_coefficient_source = (
                    'propellant table ({0}): k = {1:g}. The form field '
                    'erosive_k sent {2:g}, which was NOT applied - the page '
                    'sends this field on every run even when it is untouched, '
                    'and the table value is the calibrated one. Send '
                    'erosive_k_override = true to force the entered '
                    'value.'.format(self.propellant_type, float(table_k),
                                    float(m)))
        table_sigma = getattr(self, 'burn_rate_temp_coeff', 0.0)
        m = self._override_val('temp_coeff', 0.0, 0.02)
        self.temp_coeff_source = (
            'propellant table ({0})'.format(self.propellant_type)
            if kalibre.get('burn_rate_temp_coeff') else
            'solver default (no calibrated table value for this propellant)')
        if m is not None and not np.isclose(m, table_sigma, rtol=1e-6,
                                            atol=0.0):
            beyanli = self._flag_true('temp_coeff_override')
            if beyanli or not kalibre.get('burn_rate_temp_coeff'):
                self.burn_rate_temp_coeff = m
                self.temp_coeff_source = (
                    'user-declared form value (temp_coeff with '
                    'temp_coeff_override)' if beyanli else
                    'form field temp_coeff (no calibrated table value for '
                    'this propellant)')
                if not beyanli:
                    self.design_warnings.append(_w(
                        'warn.solid.temp_coeff_overridden', 'warning',
                        form_value=float(m), table_value=float(table_sigma),
                        propellant=self.propellant_type))
            else:
                # V301/K-B (KT-05): aynı beyan (overridden_by_catalogue).
                self._temp_coeff_not_applied = True
                self.temp_coeff_source = (
                    'propellant table ({0}): sigma_p = {1:g} 1/K. The form '
                    'field temp_coeff sent {2:g}, which was NOT applied - the '
                    'page sends this field on every run even when it is '
                    'untouched. Send temp_coeff_override = true to force the '
                    'entered value.'.format(self.propellant_type,
                                            float(table_sigma), float(m)))
        # Erozif yanma üssü: UI 'erosive_m' alanını gönderiyordu ama motor
        # HİÇ okumuyordu (F070, ölü alan). Varsayılan 0.8 = Lenoir-Robillard
        # kütle-akısı üssü (Sutton & Biblarz 9. baskı Böl. 12).
        self.erosive_exponent = 0.8
        m = self._override_val('erosive_m', 0.1, 2.0)
        if m is not None:
            self.erosive_exponent = m
        # Başlangıç sıcaklığı yanma hızını düzeltir: a_T = a·exp(σp·(T0−Tref))
        m = self._override_val('initial_temp', 200.0, 350.0)
        self.initial_grain_temperature = (
            float(m) if m is not None else float(self.temp_ref))
        if m is not None:
            self.a = self.a * float(np.exp(
                self.burn_rate_temp_coeff * (m - self.temp_ref)))

        # ------------------------------------------------------------------
        # DENETİM DÜZELTMESİ (2026-07-19): 'Efficiency Factors' ve
        # 'Mass & structural' grupları backend'e ULAŞIYOR ama okunmuyordu —
        # kullanıcı verim/dayanım/kalınlık girip hesaplatınca hiçbir sayı
        # değişmiyordu. Aşağıdaki bağlantılar bunu kapatır. ÇİFTE SAYIM
        # YASAK: her fiziksel kayıp yalnız BİR alandan gelir.
        # ------------------------------------------------------------------

        # 1) Yanma verimi -> c* çarpanı. Teslim edilen c* = eta_c* x c*_teorik
        #    (Sutton & Biblarz 9. baskı Böl. 3; statik ateşleme veri indirgeme).
        #
        #    CODEX BULGUSU DÜZELTMESİ (2026-07-19, satır ~1735): self.c_star
        #    bu satırdan sonra TESLİM EDİLEN c*'tır. Verim raporu onu paydaya
        #    koyunca kullanıcının girdiği kaybı kendi kendine iptal ediyordu
        #    (eta=1.0 -> %99.77, eta=0.8 -> yine %99.77). Teorik (kayıpsız)
        #    değer artık ayrı saklanır ve TÜM verim/teorik-Isp raporları ona
        #    normalize edilir. char_velocity override'ı bu satırdan ÖNCE
        #    uygulandığı için kullanıcının girdiği c* da teorik kabul edilir.
        # V301/N-CEA-2 (K1): bileşimi bilinen itici için T_c, c*, γ_s, M
        # motorun KENDİ Pc'sinde NASA CEA'dan (yanma verimi bundan SONRA).
        self._apply_cea_thermochemistry(kayit_termo)
        # V301/K-D (K-C1 AÇIK 1): parti c* çarpanı TEORİK c*'a, motorun kendi
        # termokimya kaynağından (CEA / katalog / kullanıcı) SONRA uygulanır.
        # Eski yol c*'ı ``char_velocity`` girdisi olarak basıyordu: çarpan 1
        # iken de motor CEA yolundan ``user_entered`` yoluna geçiyor (γ, T_c,
        # M kaydın tek basınç değerlerine dönüyor) ve UQ'da teslim edilen c*
        # teorik sanıldığı için yanma verimi İKİ KEZ uygulanıyordu. Ölçüldü
        # (K-C1/uq_sonra.json, sayfa yükü): UQ nominali Isp 205,00 ⟷ ana
        # tasarım 217,18 s, c* 1426,35 ⟷ 1501,42 m/s.
        if self._propellant_lot is not None:
            self.c_star = self.c_star * self._propellant_lot['c_star_scale']
        self.c_star_theoretical = self.c_star
        self.combustion_efficiency = 1.0
        m = self._override_val('combustion_efficiency', 0.50, 1.0)
        if m is not None:
            self.combustion_efficiency = m
            self.c_star = self.c_star * m

        # 2) Nozul kayıpları. 'nozzle_efficiency' (yoksa 'cf_efficiency')
        #    TABAN verimdir ve UI tanımına göre diverjans + sürtünme + ısı
        #    transferini KAPSAR; bu yüzden divergent_angle / divergence_loss
        #    ayrıca ÇARPILMAZ (çifte sayım olurdu) — onlar yalnız kayıp
        #    dökümünde raporlanır. Kinetik ve iki-fazlı kayıplar tabanın
        #    içinde değildir, ayrı çarpan olarak uygulanır.
        m = self._override_val('cf_efficiency', 0.80, 1.0)
        if m is not None:
            self.nozzle_efficiency = m
        m = self._override_val('nozzle_efficiency', 0.80, 1.0)
        if m is not None:
            self.nozzle_efficiency = m

        self.kinetic_efficiency = 1.0
        m = self._override_val('kinetic_efficiency', 0.80, 1.0)
        if m is not None:
            self.kinetic_efficiency = m

        self.two_phase_efficiency = 1.0
        m = self._override_val('two_phase_loss', 0.80, 1.0)
        if m is not None:
            self.two_phase_efficiency = m

        # Kullanıcının girdiği diverjans kaybı / yarı açı yalnız RAPORLANIR
        # (taban verimin içinde). None ise dökümde konturdan türetilir.
        self.user_divergence_loss = self._override_val('divergence_loss', 0.0, 0.20)
        self.divergent_half_angle_deg = self._override_val('divergent_angle', 5.0, 45.0)
        self.convergent_half_angle_deg = self._override_val('convergent_angle', 10.0, 80.0)

        # 3) Boğaz akış katsayısı: geometrik boğaz, etkin boğazdan büyüktür
        #    (A_geom = A_etkin / Cd). Basınç ve itki etkin alandan çözülür,
        #    yalnız RAPORLANAN geometrik çap ve CF bundan etkilenir.
        self.discharge_coeff = 1.0
        m = self._override_val('discharge_coeff', 0.70, 1.0)
        if m is not None:
            self.discharge_coeff = m

        # 4) Kullanıcının beyan ettiği toplam verim — hesaplanan değerle
        #    KARŞILAŞTIRMA için saklanır, hesabı ezmez (aksi çifte sayım).
        self.user_overall_efficiency = self._override_val('overall_efficiency', 0.50, 1.0)

        # 5) Kasa yapısal girdileri (dry mass / structural / safety zinciri)
        self.case_material = SOLID_CASE_DESIGN['material']
        self.case_yield_strength = SOLID_CASE_DESIGN['yield_strength_pa']
        cm = self.overrides.get('case_material')
        if isinstance(cm, str) and cm.strip():
            self.case_material = cm.strip()
            # Kullanıcı malzemeyi değiştirdiyse dayanım da o malzemenin
            # GERÇEK değeri olmalı; aksi halde alüminyum kasa çelik dayanımıyla
            # boyutlandırılırdı. Açık yield_strength girdisi bunu yine ezer.
            # Bilinmeyen malzeme artık SESSİZCE çeliğe düşmez (Codex bulgusu):
            # _case_material_properties ya kayıt bulur ya açık hata verir.
            props = self._case_material_properties(self.case_material)
            self.case_yield_strength = props['yield_strength']
            _kip_malz = str(self.overrides.get('yield_strength_source')
                            or '').strip().lower() == 'material'
            if props['generic_allowable'] and (self.overrides.get(
                    'yield_strength') in (None, '') or _kip_malz):
                self.design_warnings.append(_w(
                    'warn.solid.case_generic_allowable', 'warning',
                    material=self.case_material,
                    yield_strength_mpa=round(props['yield_strength'] / 1e6),
                    density_kg_m3=round(props['density'])))
        # V301/K-B (KT-12): akmanın KAYNAĞI açık kiple seçilir.
        #   'material' -> seçilen kaydın akması; cidar boyutlandırması ve
        #                 patlama basıncı AYNI kayıttan (kimlik bölünmesi yok).
        #                 Gönderilen yield_strength UYGULANMAZ ve adıyla
        #                 bildirilir (unwired_inputs.overridden_by_material).
        #   'user'     -> kullanıcının değeri cidarı boyutlandırır; kayıttan
        #                 farklıysa adlı uyarı (patlama basıncı kaydın
        #                 akmasıyla hesaplanır, iki sayı ayrı yazılır).
        #   (yok)      -> eski API sözleşmesi: değer gönderildiyse 'user'.
        self.case_yield_strength_source = 'material_record'
        self._yield_not_applied = False
        kip = self.overrides.get('yield_strength_source')
        kip = kip.strip().lower() if isinstance(kip, str) else None
        m = self._override_val('yield_strength', 10.0, 3000.0)   # MPa
        if m is not None and kip == 'material':
            self._yield_not_applied = True
        elif m is not None:
            self.case_yield_strength = m * 1e6
            self.case_yield_strength_source = 'user'
            kayit = solid_case_material_record(self.case_material)
            if (kayit is not None and not kayit['generic_allowable']
                    and not np.isclose(m, kayit['yield_strength_mpa'],
                                       rtol=1e-9, atol=0.0)):
                self.design_warnings.append(_w(
                    'warn.solid.case_yield_differs_from_material', 'warning',
                    material=str(self.case_material),
                    user_mpa=float(m),
                    record_mpa=float(kayit['yield_strength_mpa'])))
        self.case_safety_factor = SOLID_CASE_DESIGN['design_safety_factor']
        m = self._override_val('safety_factor', 1.1, 10.0)
        if m is not None:
            self.case_safety_factor = m
        self.user_case_thickness = self._override_val('case_thickness', 0.2, 100.0)  # mm

        # 6) Yalıtım (termal analiz + kütle)
        self.liner_thickness = SOLID_INSULATION['thickness_m']
        m = self._override_val('liner_thickness', 0.1, 100.0)    # mm
        if m is not None:
            self.liner_thickness = m / 1000.0
        self.liner_density = SOLID_INSULATION['density_kg_m3']
        m = self._override_val('liner_density', 200.0, 3000.0)
        if m is not None:
            self.liner_density = m

        # 7) Ortam koşulları: itki katsayısı deniz seviyesi yerine GERÇEK
        #    ortam basıncında değerlendirilir.
        self.ambient_pressure_bar = SEA_LEVEL_PRESSURE_BAR
        m = self._override_val('test_altitude', 0.0, 30000.0)
        if m is not None and m > 0:
            from hrma.constants import isa_pressure
            self.ambient_pressure_bar = float(isa_pressure(m)) / 1e5
        m = self._override_val('atm_pressure', 1.0, 200.0)       # kPa
        if m is not None:
            self.ambient_pressure_bar = m / 100.0
        self.ambient_temperature = SOLID_THERMAL['ambient_temperature_k']
        # V301/CI-ÜRÜN (28 Eki): bant TEK KAYNAKTAN — değer kapısının
        # (``motor_validation`` -> ``AMBIENT_TEMPERATURE_BAND_K``) okuduğu
        # sayı. ÖLÇÜLDÜ (``docs/scofield/raw/OH/V301/ci-urun/k2_once.json``):
        # eski literal 200-350 ile kapı 180-340 ayrışıyordu; 180-199,9 K
        # kapıdan geçip burada reddediliyor (298 K varsayılanı), 340,1-350 K
        # formdan geçip kapıda 400 alıyordu.
        m = self._override_val('ambient_temp', *AMBIENT_TEMPERATURE_BAND_K)
        if m is not None:
            self.ambient_temperature = m

        # ------------------------------------------------------------------
        # 7b) İnhibitör düzeni + segment arası boşluk + yalıtım katmanı
        #     (v2.6.26, D1-KATI-OLU-1: bu üç grup formda vardı ama motora
        #     HİÇ ulaşmıyordu — kullanıcı "uçlar inhibe" derken motor "değil"
        #     varsayıyordu ve itki eğrisi fiziksel olarak yanlış çıkıyordu.)
        #
        # İnhibitör bayrakları BATES yanma yüzeyi kümesini belirler
        # (calculate_burn_area). Varsayılanlar motorun eski, klasik BATES
        # varsayımıdır (künye eskiden "NASA SP-8064" diyordu; o monografta
        # BATES geometrisi yok — KU-K2): uç yüzeyler yanar, dış yüzey inhibedir —
        # bayrak gönderilmeyen çağıranlar bit-özdeş davranış alır.
        # ------------------------------------------------------------------
        self.inhibit_front = self._flag_opt('inhibit_front', False)
        self.inhibit_rear = self._flag_opt('inhibit_rear', False)
        self.inhibit_outer = self._flag_opt('inhibit_outer', True)

        # Segment arası boşluk yakıt DEĞİLDİR ama kasa boyunu uzatır: kasa
        # iç boyu, kütle ve serbest hacim zinciri _case_inner_length üzerinden
        # bunu görür (yanma alanına girmez — boşlukta yakıt yok).
        self.grain_gap_m = 0.0
        m = self._override_val('grain_gap', 0.0, 100.0)      # mm
        if m is not None:
            self.grain_gap_m = m / 1000.0
        # ÖH D36 · onemli2-kati (D35 katı kulvarı devri 3) — boşluğun KAYNAĞI.
        # ÖLÇÜLDÜ (a1/once.json): yük grain_gap=2,0 mm taşıyor, kasa boyu bu
        # boşluğu görüyor (_case_inner_length) ama grain_design sözlüğü
        # boşluğu HİÇ yayımlamıyordu (grain_gap_mm: null); STEP üreticisi
        # segmentleri bitişik yerleştirip "hiçbir çözücü yayımlamıyor" diye
        # künyeliyordu. Burada SAYI ÜRETİLMEZ: self.grain_gap_m'nin kendisi
        # yayımlanır, kaynağı ADIYLA söylenir (girdi / gönderilmedi=0 /
        # reddedildi=0). Hesap değişmez.
        _gap_ham = self.overrides.get('grain_gap')
        self.grain_gap_source = (
            'user_input' if m is not None
            else ('rejected_input' if _gap_ham not in (None, '')
                  else 'not_supplied_zero'))

        # Yalıtım grain ile kasa arasında radyal yer kaplar: kasa iç çapı
        # (hoop boyutlandırma, kasa kütlesi, motor dış çapı) grain çapından
        # 2x yalıtım kadar büyüktür; kütlesi de kuru kütleye eklenir.
        # Liner (bond katmanı) çap zincirine BİLEREK eklenmedi: liner alanı
        # öteden beri yalnız termal+kütle katmanı olarak modellenir ve bu
        # değişiklik yalnız yeni bağlanan alanın etkisini taşır.
        self.insulation_thickness_m = 0.0
        m = self._override_val('insulation_thickness', 0.0, 100.0)  # mm
        if m is not None:
            self.insulation_thickness_m = m / 1000.0

        # ------------------------------------------------------------------
        # 7c) GRAIN DIŞ ÇAPI ile KASA İÇ ÇAPI ayrımı (v2.6.26, kalem 29)
        #
        # Formda iki ayrı alan var ve ikisinin de etiketi doğruyken davranış
        # ikisini de yalanlıyordu:
        #   * 'outer_diameter'   — "grain dış çapı" diye etiketli, motora HİÇ
        #                          girmiyordu (girilen 100 mm yok sayılıyor,
        #                          bir uyarıyla "kullanılmıyor" deniyordu),
        #   * 'chamber_diameter' — "kasa iç çapı" diye etiketli, ama fiilen
        #                          GRAIN dış çapı olarak kullanılıyordu
        #                          (yanma alanı, grain hacmi, web hep bundan).
        # Yani kullanıcı grain'i büyütmek için etiketi "kasa" olan alanı
        # değiştirmek zorundaydı ve yalıtım payını hesaba katamıyordu.
        #
        # Artık grain dış çapının doğruluk kaynağı 'outer_diameter'dır;
        # 'chamber_diameter' kasa iç çapı olarak yorumlanır. İlişki zaten
        # _case_inner_diameter'da yazılıydı: D_kasa_iç >= D_grain + 2·yalıtım
        # (Sutton & Biblarz 9. baskı Böl. 12: hacimsel doluluk ve yalıtım
        # payı). Alan verilmediğinde eski davranış BİT-AYNI kalır.
        #
        # v3.0.1 (V301/K-A, KT-01/KT-03; ana model kararı A, 22 Eki) —
        # İKİ GİRDİ BİÇİMİ, TEK KURAL:
        #   * ``outer_diameter`` VERİLDİ (sayfa her zaman gönderir): tane dış
        #     çapı odur ve ``chamber_diameter`` DAİMA kasa iç çapı beyanıdır.
        #     Eski "iki alan eşitse beyan sayma" özel durumu KALKTI (ölçüldü:
        #     100/100 + 3 mm yalıtım kasa beyanını sessizce 106 mm'ye
        #     büyütüyordu, uyarısız). ``chamber_diameter`` boş gönderilirse
        #     (anahtar var, değer None/'') kasa türetilir ve beyan edilir.
        #   * ``outer_diameter`` VERİLMEDİ (tek çaplı eski API biçimi): değer
        #     tane dış çapı okunur, kasa türetilir; yorum ``case_bore``
        #     künyesinde adıyla yazılır (eski API kullanıcılarının yayımlanmış
        #     performans sayıları değişmez).
        # Kural: kasa iç çapı >= tane dış çapı + 2·(astar + yalıtım). Astar
        # radyal yer KAPLAR (KT-03: kütle ve ısıl dirençte vardı, çapta
        # yoktu). Beyan edilen kasa sığmıyorsa tasarım YAYIMLANMAZ:
        # ``SolidDesignRejected`` -> uçta 422 ``grain_does_not_fit_case``,
        # gereken en küçük çapla (``_check_case_fit``). Sessiz büyütme ve
        # "büyüt + uyar" yolu yok (hibrit port-kamara KARAR 3 deseni).
        # ------------------------------------------------------------------
        self.case_bore_input_m = None
        self.case_bore_source = 'derived_from_grain'
        self.grain_outer_diameter_source = 'chamber_diameter_single_diameter_form'
        m = self._override_val('outer_diameter',
                               *SOLID_OUTER_DIAMETER_RANGE_MM)      # mm
        if m is not None:
            self.grain_outer_diameter_source = 'outer_diameter'
            # Anahtar YOKSA (doğrudan Python API) kurucu argümanı kasa
            # beyanıdır (kalem 29'dan beri öyle); anahtar VAR ama boşsa
            # kullanıcı kasayı HRMA'ya bırakmıştır.
            _ch_ham = self.overrides.get('chamber_diameter', self)
            if _ch_ham is None or _ch_ham == '':
                self.case_bore_source = 'derived_from_grain'
            else:
                self.case_bore_input_m = self.D_chamber
                self.case_bore_source = 'chamber_diameter'
            self.D_chamber = m / 1000.0
            # KT-14 (motor ayağı): kurucu kapısı çekirdeği KURUCU ARGÜMANINA
            # (kasa) karşı sınadı; tane dış çapı ayrı geldiğinde çekirdek
            # TANEYE sığmak zorundadır (radyal yanan tipte). Uç katmanı
            # buna imalat payını ayrıca ekler (``/calculate_solid``).
            if (self.grain_type != 'end_burner'
                    and self.D_core >= self.D_chamber - 1e-12):
                _od = self.D_chamber * 1000.0
                _c = self.D_core * 1000.0
                _mesaj = (
                    f'No design was published: the core diameter {_c:g} mm '
                    f'is not smaller than the grain outer diameter '
                    f'{_od:g} mm (outer_diameter), so the '
                    f'{self.grain_type} grain has no propellant web. Enter '
                    f'a core diameter below {_od:g} mm or a larger grain '
                    f'outer diameter.')
                raise SolidDesignRejected(_mesaj, [{
                    'field': 'core_diameter',
                    'reason': 'core_not_inside_grain',
                    'submitted': _c,
                    'grain_outer_diameter_mm': _od,
                    'accepted_range': [0.0, _od],
                    'accepted_range_exclusive': [True, True],
                    'unit': 'mm',
                    'motor_form': 'solid',
                    'message': _mesaj,
                }], 'core_not_inside_grain')
        self._check_case_fit()

        # ------------------------------------------------------------------
        # 8) PARÇALI yanma hızı yasası (F025, 2026-07-25)
        #
        # KN-şeker yakıtların (KNDX/KNSB) yayımlanmış davranışı PARÇALIDIR:
        # tek bir (a, n) çifti 1-110 bar aralığını temsil etmez (plateau/mesa
        # rejimleri; n bazı rejimlerde NEGATİF). /api/burn-rate/resolve tek
        # rejimin katsayısını forma yazıyor, motor ise Pc yanma boyunca 5 kat
        # değişse bile onu donduruyordu — ölçüm: tasarım 30 bar KNDX koşusunda
        # anlık yanma hızı ortalama -%36, dipte -%62 sapıyor.
        #
        # Çözüm: yakıt için merkezi rejim yasası VARSA yanma hızı her adımda
        # ANLIK basınçtan okunur. Tetikleyiciler (öncelik sırasıyla):
        #   overrides['burn_rate_law'] / ['burn_rate_preset']  → açık seçim
        #   propellant_type'ın kendisi bir yasa anahtarıysa    → örtük
        # Yasa yoksa davranış birebir eskisi gibidir (tek üslü Saint-Robert).
        #
        # Kaynak: R. Nakka, 'Solid Propellant Burn Rate' (Experimental
        # Rocketry, 1999/2001) KNDX/KNSB rejim tabloları; hrma/data/
        # burn_rate_db.py modül docstring'indeki parçalılık uyarısı.
        # ------------------------------------------------------------------
        from hrma.data import burn_rate_db as _brdb
        self.burn_rate_law_key = None
        law_key = (self.overrides.get('burn_rate_law')
                   or self.overrides.get('burn_rate_preset'))
        # V301/K-C2 (NK-70, ana model kararı "karışık kayıt OLMAZ"): açık
        # seçilen rejim tablosu başka bir yakıtınsa (APCP kimliği + KNDX
        # rejim tablosu) motor ÇÖZÜLMEZ. Ölçüldü (taban 688bc30b2, örnek →
        # katalogda APCP): ekranda APCP a/n varken çözücü KNDX tablosuyla
        # koştu (yanma süresi 2,27 s; APCP a-n ile beklenen 2,6-2,7 s).
        # Uyarı + devam yerine RET: itki eğrisi, süre ve basınç yanlış yakıta
        # ait olurdu. Yasası olmayan ön ayar ('custom', 'knsu') bu kapıya
        # girmez — o zaman tek a-n çifti kullanılır ve kimliğe bağlı değildir.
        if law_key and _brdb.has_law(law_key):
            _yasa = str(law_key).strip().lower()
            _kimlik_ham = str(self.propellant_type or '').strip().lower()
            _kimlik_kanon = _catalog_key_for(_kimlik_ham) or _kimlik_ham
            if _kimlik_kanon != (_catalog_key_for(_yasa) or _yasa):
                _kimlik = _kimlik_ham
                _alan = ('burn_rate_law' if self.overrides.get('burn_rate_law')
                         else 'burn_rate_preset')
                _mesaj = (
                    f"No design was published: the burn-rate regime table "
                    f"'{_yasa}' ({_alan}) belongs to a different propellant "
                    f"than the selected propellant '{_kimlik}' "
                    f"(propellant_type). The thrust curve, burn time and "
                    f"pressure would come from '{_yasa}' while the identity "
                    f"says '{_kimlik}'. Select the preset of the same "
                    f"propellant, or 'custom' to use the a-n pair.")
                raise SolidDesignRejected(_mesaj, [{
                    'field': _alan,
                    'reason': 'burn_rate_law_propellant_mismatch',
                    'submitted': str(law_key),
                    'propellant_type': _kimlik,
                    'accepted_values': sorted(
                        {'custom'} | ({_kimlik} if _brdb.has_law(_kimlik)
                                      else set())),
                    'motor_form': 'solid',
                    'message': _mesaj,
                }], 'burn_rate_law_propellant_mismatch')
        if not law_key and _brdb.has_law(self.propellant_type):
            law_key = self.propellant_type
        if law_key and _brdb.has_law(law_key):
            self.burn_rate_law_key = str(law_key).strip().lower()
            self.design_warnings.append(_w(
                'warn.solid.piecewise_law_active', 'info',
                law=self.burn_rate_law_key,
                regimes=len(_brdb.BURN_RATE_LAWS[self.burn_rate_law_key]
                            ['regimes'])))

    def _case_material_properties(self, material):
        """Kasa malzemesi özellikleri — TEK çözüm noktası (sessiz çelik YASAK).

        Sıra: materials_db -> SOLID_CASE_MATERIAL_EXTRA -> açık hata.
        Döndürür: {'name', 'density', 'yield_strength', 'source',
                   'generic_allowable'}
        """
        key = str(material or '').strip()
        try:
            from hrma.data.materials_db import get_material
            mat = get_material(key)
            return {
                'name': mat.get('name', key),
                'density': float(mat['density']),
                'yield_strength': float(mat['yield_strength']),
                'source': 'materials_db',
                'generic_allowable': False,
            }
        except Exception:
            pass
        extra = SOLID_CASE_MATERIAL_EXTRA.get(key.lower())
        if extra is not None:
            return {
                'name': extra['name'],
                'density': float(extra['density']),
                'yield_strength': float(extra['yield_strength']),
                'source': 'SOLID_CASE_MATERIAL_EXTRA',
                'generic_allowable': bool(extra.get('generic_allowable',
                                                    False)),
            }
        raise ValueError(
            f"Unsupported case material '{material}'. HRMA has no material "
            "record for it, and falling back to steel would silently report "
            "the wrong dry mass and structural margin. Pick a supported "
            "material or enter density and yield strength explicitly.")

    # ------------------------------------------------------------------
    # V301/N-CEA-2 — termokimya (K1/K3) ve lüle (K2) NASA CEA'dan
    # ------------------------------------------------------------------
    def _cea_composition_key(self):
        """CEA bileşim kartı olan katalog anahtarı (yoksa None)."""
        from hrma.analysis.cea_karsilastirma import SOLID_CEA_COMPOSITIONS
        raw = str(self.propellant_type or '').strip().lower()
        if raw in SOLID_CEA_COMPOSITIONS:
            return raw
        key = _catalog_key_for(raw)
        return key if key in SOLID_CEA_COMPOSITIONS else None

    def _apply_cea_thermochemistry(self, kayit_termo):
        """K1 + K3: T_c, c*, γ_s ve M motorun KENDİ Pc'sinde NASA CEA'dan.

        Kural (fail-closed, sessiz yedek YOK):
          * kullanıcı c*/γ/T_c/M'den birini kaydın değerinden farklı girdiyse
            girilen değerler kalır (``user_entered``);
          * itici bileşimi bilinmiyorsa ya da CEA çözümü yoksa katalog
            dörtlüsü (tek basınçta) kalır ve gerekçesiyle BEYAN edilir
            (``catalogue_single_pressure`` + ``warn.solid.thermochemistry_
            single_pressure``);
          * aksi hâlde CEA: T_c, c* (teorik), γ_s (oda, kayan denge).
            M (K3, tek tanım): genleşme/karışım bağıntılarına giren
            ``mw_exhaust`` = CEA M(1/n) (gaz molü başına karışım kütlesi;
            c* özdeşliği bu M ile kapanır), gaz-yalnız M =
            (1 − x_c)·M(1/n) ve oda yoğun faz kütle kesri x_c ayrı alanlarda
            tutulur (iki faz modülü gaz-yalnız M'i okur). Katalogdaki iki
            uzlaşım (APCP 1/n, KN-şeker 1/totn) CEA yolunda artık KULLANILMAZ.
        """
        from hrma.analysis.cea_karsilastirma import (
            SOLID_COMPOSITION_UNAVAILABLE, solid_cea_solution)
        self._cea_solution = None
        self._cea_nozzle_cache = None
        self.mw_gas_only = None
        self.condensed_mass_fraction_chamber = None
        self.thermochemistry_reason = None
        simdi = (self.c_star, self.gamma, self.T_c,
                 getattr(self, 'mw_exhaust', None))
        alanlar = ('char_velocity', 'gamma', 'flame_temp', 'molecular_weight')
        degisen = []
        for ad, eski, yeni in zip(alanlar, kayit_termo, simdi):
            if eski is None or yeni is None:
                if eski is not yeni:
                    degisen.append(ad)
            elif not self._matches_record_value(yeni, eski):
                degisen.append(ad)
        if degisen:
            self.thermochemistry_source = SOLID_THERMO_SOURCE_USER
            self.thermochemistry_reason = {
                'code': 'user_entered_thermochemistry',
                'message': ('the user entered %s different from the '
                            'propellant record; the entered values are used '
                            'and NASA CEA is not applied'
                            % ', '.join(degisen))}
            return
        key = self._cea_composition_key()
        if key is None:
            anahtar = (_catalog_key_for(self.propellant_type)
                       or str(self.propellant_type or '').strip().lower())
            kod, mesaj = SOLID_COMPOSITION_UNAVAILABLE.get(
                anahtar, ('propellant_composition_not_defined',
                          'no machine-readable composition is defined for '
                          '%r' % (anahtar,)))
            sol = {'status': 'unavailable',
                   'reason': {'code': kod, 'message': mesaj}}
        else:
            sol = solid_cea_solution(key, float(self.P_c), None)
        if sol.get('status') != 'available':
            self.thermochemistry_source = SOLID_THERMO_SOURCE_CATALOGUE
            self.thermochemistry_reason = dict(sol.get('reason') or {})
            self.design_warnings.append(dict(_w(
                'warn.solid.thermochemistry_single_pressure', 'info',
                propellant=str(self.propellant_type)),
                fallback=("Thermochemistry of '{propellant}' (T_c, c*, gamma, "
                          "M) is the catalogue record at ONE pressure, not "
                          "NASA CEA at this chamber pressure (no composition "
                          "is defined for it, or CEA returned no solution; "
                          "the reason is in thermochemistry.reason).")))
            return
        oda = sol['chamber']
        self._cea_solution = sol
        self.thermochemistry_source = SOLID_THERMO_SOURCE_CEA
        self.T_c = float(oda['T_c_K'])
        self.c_star = float(oda['c_star_m_s'])
        self.gamma = float(oda['gamma_s'])
        self.mw_exhaust = float(oda['M_1_n'])
        self.mw_gas_only = float(oda['M_gas_only'])
        self.condensed_mass_fraction_chamber = float(
            oda['condensed_mass_fraction'])
        # Donmuş oda gamma'sı (Bartz/iki faz) kaydın tek basınçlı CEA
        # değeridir; aynı itici olduğu için kural sürer (beyanlı:
        # thermochemistry bloğu ``frozen_gamma_source``).
        if getattr(self, 'gamma_frozen_chamber', None) is not None:
            self._gamma_frozen_equilibrium_ref = self.gamma
            self._mw_frozen_record_ref = self.mw_exhaust
        nominal = sol.get('nominal_composition')
        if nominal:
            dusuk = nominal.get('confidence') == 'low'
            self.design_warnings.append(dict(_w(
                ('warn.solid.thermochemistry_nominal_low_confidence' if dusuk
                 else 'warn.solid.thermochemistry_nominal_composition'),
                'warning' if dusuk else 'info',
                propellant=str(self.propellant_type)),
                fallback=(
                    "NASA CEA thermochemistry of '{propellant}' uses a "
                    "nominal composition chosen by HRMA (the record gives it "
                    "only approximately). LOW CONFIDENCE: charcoal is taken "
                    "as graphite; real charcoal gives more gas."
                    if dusuk else
                    "NASA CEA thermochemistry of '{propellant}' uses a "
                    "nominal composition chosen by HRMA (the record gives it "
                    "only approximately, e.g. ~85/~15 wt%).")))

    def _cea_active(self):
        return (getattr(self, 'thermochemistry_source', None)
                == SOLID_THERMO_SOURCE_CEA
                and getattr(self, '_cea_solution', None) is not None)

    def _cea_point(self, pc_bar, pa_bar):
        """CEA çözümü (oda + optimum lüle) — önbellekli, asla fırlatmaz."""
        from hrma.analysis.cea_karsilastirma import solid_cea_solution
        return solid_cea_solution(self._cea_composition_key(), float(pc_bar),
                                  float(pa_bar))

    def _cea_nozzle_state(self):
        """K2: tasarım Pc ve ortamında CEA kayan denge lülesi + eşdeğer üs.

        CEA optimum genişlemeyi (P_e = P_a) yoğun faz dahil kayan dengeyle
        çözer: ε_opt, C_F, P_e, T_e, M_e. HRMA'nın tasarım dışı (yanma
        boyunca Pc(t)) ve ayrılma zinciri tek-γ bağıntılarıyla kuruludur;
        CEA bunlara İKİ sayıyla bağlanır (sıvı motorun eşdeğer üs deseni):

          * γ_n: tek-γ alan oranı bağıntısı CEA'nın (P_e/P_c, ε_opt) çiftini
            TAM üretsin (S&B 9. baskı Eş. 3-25/3-26 tersi, kök arama);
          * κ = C_F,mom,CEA / C_F,mom,1B(γ_n): momentum terimi CEA'nınkine
            tasarım noktasında TAM eşit olsun.

        Tasarım noktasında ε, P_e, C_F CEA'nın kendisidir; sabit geometrili
        lülede P_e/P_c ve momentum terimi Pc'den bağımsız alınır (CEA'da
        zayıf bağımlılık; beyanlı). Çözüm yoksa None (+ gerekçe); çağıranlar
        tek-γ (oda γ_s) bağıntısına BEYANLA döner.
        """
        if not self._cea_active():
            return None
        p_amb = float(getattr(self, 'ambient_pressure_bar',
                              SEA_LEVEL_PRESSURE_BAR))
        anahtar = (round(float(self.P_c), 12), round(p_amb, 12))
        onb = getattr(self, '_cea_nozzle_cache', None)
        if onb is not None and onb[0] == anahtar:
            return onb[1]
        durum = None
        gerekce = None
        sol = self._cea_point(self.P_c, p_amb)
        lule = sol.get('nozzle') if sol.get('status') == 'available' else None
        if lule is None:
            gerekce = (sol.get('nozzle_reason') or sol.get('reason')
                       or {'code': 'cea_nozzle_unavailable', 'message': ''})
        else:
            eps_d = float(lule['expansion_ratio'])
            pr_d = 1.0 / float(lule['pc_over_pe'])

            def _eps_1b(g):
                m2 = (2.0 / (g - 1.0)) * (pr_d ** (-(g - 1.0) / g) - 1.0)
                if m2 <= 1.0:
                    return float('nan')
                m = np.sqrt(m2)
                return float((1.0 / m) * ((2.0 / (g + 1.0)) * (
                    1.0 + (g - 1.0) / 2.0 * m2)) ** ((g + 1.0) / (
                        2.0 * (g - 1.0))) - eps_d)
            try:
                from scipy.optimize import brentq
                lo, hi = SOLID_NOZZLE_GAMMA_BRACKET
                g_n = float(brentq(_eps_1b, lo, hi, xtol=1e-13))
            except Exception:
                g_n = None
            if g_n is None or not np.isfinite(g_n):
                gerekce = {'code': 'nozzle_equivalent_exponent_not_found',
                           'message': ('no isentropic exponent in %r '
                                       'reproduces the CEA area ratio %.6g at '
                                       'Pe/Pc = %.6g'
                                       % (SOLID_NOZZLE_GAMMA_BRACKET, eps_d,
                                          pr_d))}
            else:
                cf_mom_1b = self._cf_momentum_1d(pr_d, g_n)
                kappa = float(lule['cf_momentum']) / cf_mom_1b
                durum = dict(lule, gamma_nozzle=g_n, cf_anchor=kappa,
                             pressure_ratio=pr_d,
                             ambient_pressure_bar=p_amb)
        if durum is None and not getattr(self, '_cea_nozzle_warned', False):
            self._cea_nozzle_warned = True
            self.design_warnings.append(dict(_w(
                'warn.solid.cea_nozzle_unavailable', 'warning',
                propellant=str(self.propellant_type),
                pressure_bar=round(float(self.P_c), 2)),
                fallback=("NASA CEA did not solve the nozzle expansion of "
                          "'{propellant}' at {pressure_bar} bar; the nozzle "
                          "(area ratio, thrust coefficient) uses the "
                          "single-gamma isentropic relations with the CEA "
                          "chamber gamma instead (reason in "
                          "thermochemistry.nozzle.reason).")))
        self._cea_nozzle_reason = gerekce
        self._cea_nozzle_cache = (anahtar, durum)
        return durum

    def _nozzle_gamma(self):
        """Lüle bağıntılarının üssü: CEA lülesi varsa γ_n, yoksa self.gamma."""
        d = self._cea_nozzle_state()
        return float(d['gamma_nozzle']) if d else float(self.gamma)

    def _nozzle_cf_anchor(self):
        """Momentum teriminin CEA çapası κ (CEA lülesi yoksa 1)."""
        d = self._cea_nozzle_state()
        return float(d['cf_anchor']) if d else 1.0

    @staticmethod
    def _cf_momentum_1d(pressure_ratio, gamma):
        """S&B Eş. 3-30 momentum terimi, γ parametreli (çapasız)."""
        g = float(gamma)
        genisleme = max(0.0, 1 - float(pressure_ratio) ** ((g - 1) / g))
        return float(np.sqrt(2 * g ** 2 / (g - 1)
                             * (2 / (g + 1)) ** ((g + 1) / (g - 1))
                             * genisleme))

    def thermochemistry_report(self):
        """Yanıtın ``thermochemistry`` bloğu: kaynak, değerler, lüle tabanı."""
        sol = getattr(self, '_cea_solution', None)
        lule = self._cea_nozzle_state() if self._cea_active() else None
        blok = {
            'source': getattr(self, 'thermochemistry_source',
                              SOLID_THERMO_SOURCE_CATALOGUE),
            'reason': getattr(self, 'thermochemistry_reason', None),
            'chamber_pressure_bar': float(self.P_c),
            'chamber_temperature_K': float(self.T_c),
            'c_star_theoretical_m_s': float(self._c_star_theoretical()),
            'gamma_chamber': float(self.gamma),
            'molecular_weight': float(getattr(self, 'mw_exhaust', 0.0)),
            'molecular_weight_convention': (
                'M = 1/n (NASA RP-1311 Part I eq. 2.3a): mixture mass per mole '
                'of gas, condensed phase included in the mass'
                if self._cea_active() else
                'catalogue record convention (see the record source text)'),
            'molecular_weight_gas_only': getattr(self, 'mw_gas_only', None),
            'condensed_mass_fraction_chamber': getattr(
                self, 'condensed_mass_fraction_chamber', None),
        }
        if self._cea_active():
            blok.update({
                'program': ('NASA CEA (Gordon & McBride, NASA RP-1311) '
                            'through RocketCEA (CEA2); rocket problem, '
                            'equilibrium (shifting) composition, infinite-area '
                            'combustor, condensed species in equilibrium'),
                'composition_key': self._cea_composition_key(),
                'nominal_composition': sol.get('nominal_composition'),
                'frozen_gamma_source': (
                    'catalogue record (one NASA CEA run at the record '
                    'pressure); its chamber-pressure dependence is not '
                    'modelled' if getattr(self, 'gamma_frozen_chamber', None)
                    is not None else None),
            })
        if lule:
            blok['nozzle'] = {
                'basis': ('NASA CEA shifting-equilibrium expansion (condensed '
                          'phase included) to P_e = P_ambient at the design '
                          'chamber pressure; off-design steps keep the fixed '
                          'geometry with an equivalent single-gamma exponent '
                          'gamma_nozzle that reproduces the CEA (P_e/P_c, '
                          'area ratio) pair and a momentum anchor cf_anchor '
                          'that reproduces the CEA thrust coefficient'),
                'expansion_ratio_optimum': lule['expansion_ratio'],
                'thrust_coefficient_optimum': lule['cf_optimum'],
                'thrust_coefficient_vacuum': lule['cf_vac'],
                'exit_pressure_bar': lule['exit_pressure_bar'],
                'exit_temperature_K': lule['exit_temperature_K'],
                'exit_mach': lule['exit_mach'],
                'gamma_nozzle': lule['gamma_nozzle'],
                'cf_anchor': lule['cf_anchor'],
            }
        elif self._cea_active():
            blok['nozzle'] = {
                'basis': ('single-gamma isentropic relations with the CEA '
                          'chamber gamma: CEA did not solve the nozzle'),
                'reason': getattr(self, '_cea_nozzle_reason', None),
            }
        else:
            blok['nozzle'] = {
                'basis': ('single-gamma isentropic relations with the '
                          'propellant gamma (S&B 9th ed. Eq. 3-25/3-30)')}
        return blok

    def _c_star_theoretical(self):
        """Teorik (kayıpsız) karakteristik hız [m/s] — TEK tanım noktası.

        self.c_star yanma verimi uygulandıktan sonra TESLİM EDİLEN c*'tır;
        verim metrikleri, teorik Isp ve Monte Carlo örneklemesi teorik değeri
        kullanmak zorundadır (aksi hâlde eta ya iptal olur ya iki kez uygulanır).
        """
        c_star_th = getattr(self, 'c_star_theoretical', None)
        if c_star_th is None or not np.isfinite(c_star_th) or c_star_th <= 0:
            return float(self.c_star)
        return float(c_star_th)

    def _total_nozzle_efficiency(self):
        """Toplam nozul verimi = taban x kinetik x iki-fazlı.

        Taban ``self.nozzle_efficiency`` yakıt tablosunun kendi nozul
        verimidir. Kullanıcı bir yarı açı verdiyse buna REFERANS KONİYE
        (``SOLID_NOZZLE_REFERENCE_HALF_ANGLE_DEG``) göre ORAN düzeltmesi
        uygulanır. Kinetik ve iki-fazlı çarpanlar yalnız kullanıcı
        girdiğinde 1.0'dan farklıdır.

        REFERANS KONİ BİR MODELLEME VARSAYIMIDIR — tablo veriminin ölçülmüş
        bir ayrıştırması DEĞİLDİR (ÖH D17, P2B2-08 ŞART). ÖLÇÜLDÜ
        (docs/scofield/raw/OH/D17/kati/a1/once.json): lambda(15 derece) =
        0,982963; buna karşılık altı kompozit kaydın tablo verimi eta =
        0,985'tir, yani eta > lambda(15). Eğer eta gerçekten "15 derecelik
        koni + sürtünme" çarpımı olsaydı sürtünmeye kalan pay
        -%0,2071 (NEGATİF) olurdu. Bu yüzden modül "kayıp tablo veriminin
        İÇİNDEDİR" DEMEZ; yalnız ORANI uygular:
        lambda(alpha)/lambda(15). Oran 15 derecede tam olarak 1.0'dır,
        dolayısıyla referans açıda tablo değeri aynen okunur ve varsayım
        hiçbir sayıyı kirletmez.
        """
        return float(self.nozzle_efficiency
                     * self._divergence_efficiency_correction()
                     * getattr(self, 'kinetic_efficiency', 1.0)
                     * getattr(self, 'two_phase_efficiency', 1.0))

    def _divergence_efficiency_correction(self):
        """Kullanıcının yarı açısının referans koniye göre verim düzeltmesi.

        ÖH D15 (P2B2-08): ``divergent_angle`` eskiden performansa HİÇ
        girmiyordu — lüle GEOMETRİSİ kullanıcının açısıyla çiziliyor ve dışa
        aktarılıyordu (45 derecede diverjan boy 82,9 -> 22,2 mm), ama Isp ve
        itki 15 derecelik referans verimde kalıyordu: 15/20/30/45 derecede
        specific_impulse BİT-ÖZDEŞ 234,81132628013202 s. Aynı yanıtta
        divergence_losses %14,64 yazıp "bu kayıp nozul veriminin İÇİNDE"
        deniyordu, oysa o verimin TOPLAM kaybı %1,5'ti — beyan aritmetik
        olarak yanlışlanıyordu. Artık taban verimin taşıdığı referans
        diverjans kaybı ile kullanıcının konisininki oranlanır:
        lambda(alpha) / lambda(15 derece). 45 derecede oran 0,8683, yani 45
        derecelik koni imal eden kullanıcı ~%13,2 daha düşük Isp okur.
        Açı verilmediyse çarpan tam olarak 1.0'dır (davranış değişmez).
        """
        half = getattr(self, 'divergent_half_angle_deg', None)
        if half is None:
            return 1.0
        ref = _conical_divergence_efficiency(
            SOLID_NOZZLE_REFERENCE_HALF_ANGLE_DEG)
        return float(_conical_divergence_efficiency(half) / ref)

    def _case_inner_diameter(self):
        """Kasa iç çapı [m] — kullanıcının beyanı ya da grain + 2 x yalıtım.

        v2.6.26 (D1-KATI-OLU-1): yalıtım eskiden hiçbir geometriye girmiyordu;
        kasa grain'e sıfır boşlukla yapışık varsayılıyordu. Yalıtım radyal
        yer kapladığı için hoop boyutlandırması, kasa kütlesi ve motor dış
        çapı bu çaptan türer. Yalıtım verilmezse (0) davranış eskisiyle aynı.

        v2.6.26 (kalem 29): kullanıcı grain dış çapını ('outer_diameter') ve
        kasa iç çapını ('chamber_diameter') AYRI verdiyse beyan edilen kasa
        çapı kullanılır — ama asla grain + 2·yalıtımın altına düşemez, çünkü
        grain fiziksel olarak kasaya sığmak zorundadır. Sığmıyorsa geometrik
        alt sınır uygulanır ve tutarsızlık koşu uyarısıyla bildirilir
        (bkz. calculate_performance, warn.solid.case_bore_too_small).

        v3.0.1 (V301/K-A, KT-01/KT-03): (1) radyal yığın astar + yalıtımdır
        — ``_thermal_barrier_thickness`` (kütle zinciri ``_insulation_liner_
        masses`` ve ısıl direnç aynı iki katmanı zaten görüyordu; çap
        görmüyordu: 60 mm astarlı tane 3 mm'lik boşluğa "sığıyordu").
        (2) Beyan edilen kasa artık SESSİZCE büyütülmez: sığmıyorsa kurucu
        ``_check_case_fit`` ile reddeder, buraya sığan beyan ulaşır ve
        AYNEN kullanılır. ``warn.solid.case_bore_too_small`` kalktı.
        """
        declared = getattr(self, 'case_bore_input_m', None)
        if declared is not None:
            return float(declared)
        return self._case_inner_diameter_required()

    def _case_inner_diameter_required(self):
        """Tanenin sığdığı en küçük kasa iç çapı [m] — TEK tanım noktası.

        D_kasa_iç,min = D_tane + 2·(t_astar + t_yalıtım). Yığın sırası
        ``SOLID_THERMAL_LAYER_ORDER``dadır (astar taneye yapışık, yalıtım
        onun dışında); iki katmanın toplamı ``_thermal_barrier_thickness``.
        """
        return float(self.D_chamber
                     + 2.0 * self._thermal_barrier_thickness())

    def _check_case_fit(self):
        """Beyan edilen kasa tane + astar + yalıtımı alıyor mu? Almıyorsa RET.

        V301/K-A (KT-01; ana model kararı 1, 22 Eki). Ret cümlesinin BAŞINDA
        eyleme dönük sayı (gereken en küçük çap) durur: hibritte ölçüldü,
        arayüz uzun sunucu cümlesini kesebiliyordu (``hybrid_rocket_engine``
        zarf reddi notu). Gereken çap 0,1 mm'ye YUKARI yuvarlanır ki öneri
        kapıdan geçsin. Tolerans 1e-9 m: eski uyarı kapısının toleransı.
        """
        declared = getattr(self, 'case_bore_input_m', None)
        if declared is None:
            return
        gereken = self._case_inner_diameter_required()
        if float(declared) >= gereken - 1e-9:
            return
        gereken_mm = _ceil_tenth_mm(gereken * 1000.0)
        beyan_mm = float(declared) * 1000.0
        tane_mm = float(self.D_chamber) * 1000.0
        astar_mm = max(float(getattr(self, 'liner_thickness', 0.0)), 0.0) \
            * 1000.0
        yalitim_mm = max(float(getattr(self, 'insulation_thickness_m', 0.0)),
                         0.0) * 1000.0
        mesaj = (
            f'No design was published: the case inner diameter '
            f'(chamber_diameter) {beyan_mm:g} mm is below the '
            f'{gereken_mm:.1f} mm minimum that the {tane_mm:g} mm grain '
            f'needs with its {astar_mm:g} mm liner and {yalitim_mm:g} mm '
            f'insulation (case inner diameter >= grain outer diameter + '
            f'2 x (liner + insulation)). Enter at least {gereken_mm:.1f} mm, '
            f'leave chamber_diameter empty so HRMA derives the case from the '
            f'grain, or reduce outer_diameter, liner_thickness or '
            f'insulation_thickness; the case is not enlarged silently.')
        raise SolidDesignRejected(mesaj, [{
            'field': 'chamber_diameter',
            'reason': 'grain_does_not_fit_case',
            'submitted': beyan_mm,
            'required_min': gereken_mm,
            'unit': 'mm',
            'grain_outer_diameter_mm': tane_mm,
            'liner_thickness_mm': astar_mm,
            'insulation_thickness_mm': yalitim_mm,
            'rule': SOLID_CASE_FIT_RULE,
            'motor_form': 'solid',
            'message': mesaj,
        }], 'grain_does_not_fit_case')

    def _case_bore_block(self):
        """``case_bore`` künyesi: kasa iç çapı NEREDEN geldi (V301/K-A).

        Ana model kararı A (22 Eki): iki girdi biçiminin hangisinin
        kullanıldığı ve kasa çapının kuralı yanıtta ADIYLA durur. Sayılar
        motorun kullandığı değerlerdir (burada yeniden hesaplanmaz).
        """
        gereken = self._case_inner_diameter_required()
        kullanilan = self._case_inner_diameter()
        tane_kaynak = getattr(self, 'grain_outer_diameter_source',
                              'chamber_diameter_single_diameter_form')
        kasa_kaynak = getattr(self, 'case_bore_source', 'derived_from_grain')
        tane_mm = float(self.D_chamber) * 1000.0
        if kasa_kaynak == 'chamber_diameter':
            mesaj = (
                f'chamber_diameter is the case inner diameter you declared '
                f'({kullanilan * 1000.0:g} mm); the {tane_mm:g} mm grain '
                f'(outer_diameter) fits it with its liner and insulation '
                f'(minimum {gereken * 1000.0:g} mm).')
        elif tane_kaynak == 'outer_diameter':
            mesaj = (
                f'chamber_diameter was left empty, so the case inner '
                f'diameter was derived from the {tane_mm:g} mm grain '
                f'(outer_diameter): {kullanilan * 1000.0:g} mm = grain outer '
                f'diameter + 2 x (liner + insulation).')
        else:
            mesaj = (
                f'outer_diameter was not supplied, so chamber_diameter '
                f'({tane_mm:g} mm) was read as the grain outer diameter '
                f'(single-diameter form); the case inner diameter was '
                f'derived as grain outer diameter + 2 x (liner + insulation) '
                f'= {kullanilan * 1000.0:g} mm.')
        return {
            'case_inner_diameter_mm': kullanilan * 1000.0,
            'case_inner_diameter_source': kasa_kaynak,
            'grain_outer_diameter_mm': tane_mm,
            'grain_outer_diameter_source': tane_kaynak,
            'required_min_case_inner_diameter_mm': gereken * 1000.0,
            'liner_thickness_mm': max(float(getattr(
                self, 'liner_thickness', 0.0)), 0.0) * 1000.0,
            'insulation_thickness_mm': max(float(getattr(
                self, 'insulation_thickness_m', 0.0)), 0.0) * 1000.0,
            'rule': SOLID_CASE_FIT_RULE,
            'message': mesaj,
        }

    def _case_inner_length(self):
        """Kasa iç boyu [m] = grain yığını + BATES segment araları + kapaklar.

        Segment arası boşluk (grain_gap) yalnız çok segmentli BATES'te
        anlamlıdır; diğer grain tipleri tek parçadır. Kapak payı eski
        modelden aynen korunur ve TEK tanım noktası modül sabiti
        ``SOLID_CASE_CLOSURE_LENGTH_M``'dir (ÖH D21 a1, P2B1-08): bu
        künye eskiden "tek tanım noktası artık burası" diyordu ama sayı
        ``_grain_envelope_volume()`` içinde ikinci kez çıplak yazılıydı.
        """
        gaps = 0.0
        if self.grain_type == 'bates':
            gaps = ((self._bates_segment_count() - 1)
                    * getattr(self, 'grain_gap_m', 0.0))
        return self.L_grain + gaps + SOLID_CASE_CLOSURE_LENGTH_M

    def _grain_envelope_volume(self):
        """Grain yığınının kapladığı silindirik hazne hacmi [m³] — TEK kaynak.

        ÖH D15 a2 (P2B4-05). Aynı yanıt İKİ hazne hacmi taşıyordu ve
        dolayısıyla İKİ hacimsel doluluk yayımlıyordu:

          * ``grain_design.volumetric_loading`` -> payda BATES segment
            aralarını GÖREN hacim (``_case_inner_length()`` eksi kapak
            payı ``SOLID_CASE_CLOSURE_LENGTH_M``),
          * ``advanced_performance.mass_utilization.
            volumetric_efficiency_percent`` ve ``loading_density_kgm3``
            -> payda ``pi*r^2*L_grain``, yani aralara KÖR.

        ``grain_gap`` bir arayüz alanıdır ve VARSAYILANI 2 mm'dir, yani
        ayrışma her varsayılan koşuda vardı. ÖLÇÜLDÜ (bates, D=100, L=500,
        core=30, APCP, 40 bar; 5 segman -> 4 aralık):

          grain_gap   volumetric_loading×100   volumetric_efficiency_%   oran
             0 mm            91,000000               91,000000          1,000
             2 mm            89,566929               91,000000          1,016
            20 mm            78,448276               91,000000          1,160
            50 mm            65,000000               91,000000          1,400

        Doğru payda aralıkları görendir — kasa serbest hacmi, ateşleyici
        boyutlandırması ve kütle zinciri zaten ``_case_inner_length()``
        kullanıyor. Kapak payı grain yığınının dışındadır ve payın TEK
        tanım noktası ``SOLID_CASE_CLOSURE_LENGTH_M``'dir — bu satır
        eskiden aynı sayıyı çıplak literal olarak ikinci kez yazıyordu
        (ÖH D21 a1, P2B1-08).
        """
        return float(np.pi * (self.D_chamber / 2) ** 2
                     * (self._case_inner_length()
                        - SOLID_CASE_CLOSURE_LENGTH_M))

    def _case_design(self):
        """Kasa boyutlandırmasının TEK kaynağı.

        Döndürür: (malzeme anahtarı, akma dayanımı Pa, tasarım SF, cidar m).
        Kullanıcı case_thickness verdiyse o kullanılır; vermediyse Barlow ince
        cidar hoop formundan t = P*r/(sigma_y/SF) boyutlandırılır.

        Z2 (ÖH, P2B2-01) — **KULLANICININ CİDARI EZİLMEZ.** Buradaki
        ``max(t_wall, min_wall_thickness_m)`` eskiden İKİ dala birden
        uygulanıyordu, yani kullanıcının girdiği 0,2-1,99 mm arası her cidar
        SESSİZCE 2,0 mm'ye çekiliyor ve sonuç yine "kullanıcının cidarına
        karşı doğrulandı" künyesiyle yayımlanıyordu. ÖLÇÜLDÜ (APCP, D=100 mm,
        d=30 mm, L=500 mm, Pc=40 bar): 0,2 / 0,5 / 1,0 / 1,9 / 1,99 mm
        girdilerinin BEŞİNDE de kullanılan cidar 2,0 mm, ``vessel_status``
        PASS, ``safety_factor`` 2,4999574558148954 — beş ayrı tasarım tek
        bit farkı olmadan aynı yanıtı üretiyordu; 0,2 mm'nin GERÇEK emniyet
        katsayısı ise 0,25 (on kat ince cidar).

        ``min_wall_thickness_m`` **imalat tabanıdır**, bir fizik sınırı
        değil: HRMA kendi ÖNERİSİNİ bu tabanın altına indirmez (çok ince bir
        kasa önerisi imal edilemez). Ama kullanıcının BEYAN ETTİĞİ cidar bir
        öneri değil, sınanacak bir tasarımdır — aynen analiz edilir ve
        tabanın altındaysa bu ``_case_wall_provenance()`` künyesiyle ve kap
        uyarısıyla BEYAN edilir. Sessiz ikame yerine beyan.
        """
        material = getattr(self, 'case_material', SOLID_CASE_DESIGN['material'])
        sigma_y = getattr(self, 'case_yield_strength',
                          SOLID_CASE_DESIGN['yield_strength_pa'])
        sf = getattr(self, 'case_safety_factor',
                     SOLID_CASE_DESIGN['design_safety_factor'])
        # Hoop yarıçapı kasa İÇ yarıçapıdır (grain + yalıtım) — grain yarıçapı
        # değil; yalıtım 0 iken ikisi özdeştir (eski davranış korunur).
        r_inner = self._case_inner_diameter() / 2.0
        t_required = (self.P_c * 1e5) * r_inner / (sigma_y / sf)
        t_user = getattr(self, 'user_case_thickness', None)
        if t_user is not None:
            # Kullanıcının cidarı OLDUĞU GİBİ analiz edilir (kırpma YOK).
            t_wall = t_user / 1000.0
        else:
            # HRMA'nın KENDİ önerisi imalat tabanının altına inmez.
            t_wall = max(t_required, SOLID_CASE_DESIGN['min_wall_thickness_m'])
        return material, sigma_y, sf, t_wall

    def _case_wall_provenance(self):
        """Kullanılan kasa cidarının künyesi — TEK üretim noktası (Z2).

        Yan etkisi yoktur; ``_case_design()`` ile aynı girdilerden yeniden
        türetilir, böylece yapısal panel, kap paneli, özet tablo ve CAD
        bloğu cidar hakkında AYNI cümleyi kurar.

        Anahtarlar:
          ``source``                       'user_supplied' | 'sized_by_hrma'
          ``used_mm``                      analiz edilen cidar
          ``requested_mm``                 kullanıcının girdiği (yoksa None)
          ``hoop_required_mm``             t = P*r/(sigma_y/SF)
          ``manufacturing_floor_mm``       imalat tabanı (öneri sınırı)
          ``clamped_to_floor``             öneri tabana yükseltildi mi
          ``below_manufacturing_floor``    kullanıcı cidarı tabanın altında mı
        """
        _material, sigma_y, sf, t_wall = self._case_design()
        r_inner = self._case_inner_diameter() / 2.0
        t_required = (self.P_c * 1e5) * r_inner / (sigma_y / sf)
        floor = SOLID_CASE_DESIGN['min_wall_thickness_m']
        t_user = getattr(self, 'user_case_thickness', None)
        user = t_user is not None
        return {
            'source': 'user_supplied' if user else 'sized_by_hrma',
            'used_mm': float(t_wall * 1000.0),
            'requested_mm': (float(t_user) if user else None),
            'hoop_required_mm': float(t_required * 1000.0),
            'manufacturing_floor_mm': float(floor * 1000.0),
            'clamped_to_floor': bool(
                (not user) and t_wall > t_required * (1.0 + 1e-9)),
            'below_manufacturing_floor': bool(user and t_wall < floor),
        }

    def _case_design_report(self):
        """İki ``case_design`` bloğunun ORTAK künye çekirdeği (P15B4-07).

        Aynı yanıtta iki ``case_design`` bloğu vardı (``design_summary`` 5
        alan, ``cad_design`` 11 alan) ve kesişimleri TEK alandı (``material``);
        cidarın nereden geldiğini söyleyen ``thickness_source`` yalnız birinde
        vardı. İmalata giden blok, cidarın kullanıcıdan mı geldiğini yoksa
        HRMA'nın mı önerdiğini söylemiyordu. Künye artık burada BİR kez
        kurulur ve iki blok da onu taşır.
        """
        material, sigma_y, sf, t_wall = self._case_design()
        prov = self._case_wall_provenance()
        return {
            'material': material,
            'yield_strength_mpa': float(sigma_y / 1e6),
            'design_safety_factor': float(sf),
            'wall_thickness_mm': float(t_wall * 1000.0),
            # Eski ad korunur (tüketiciler okuyor); anlamı genişletildi:
            # 'user_entered' artık GERÇEKTEN kullanıcının değeri demek.
            'thickness_source': ('user_entered'
                                 if prov['source'] == 'user_supplied'
                                 else 'hoop_stress_sized'),
            'wall_thickness_requested_mm': prov['requested_mm'],
            'wall_thickness_hoop_required_mm': prov['hoop_required_mm'],
            'wall_thickness_manufacturing_floor_mm': (
                prov['manufacturing_floor_mm']),
            'wall_thickness_at_minimum_clamp': prov['clamped_to_floor'],
            'wall_thickness_below_manufacturing_floor': (
                prov['below_manufacturing_floor']),
        }

    def _case_density(self):
        """Kasa malzemesi yoğunluğu [kg/m3] — TEK kaynak.

        v2.6.27 (F2-1): burada varsayılan malzeme için AYRI bir sabit
        (7800 kg/m³) döndüren bir dal vardı. O sayı hiçbir malzeme kaydında
        geçmiyordu (materials_db hem 'steel' hem 'steel_4130' için 7850 der),
        yani aynı kasa dayanımını bir kayıttan, yoğunluğunu başka bir yerden
        alıyordu. Dal kaldırıldı: yoğunluk DAİMA dayanımla aynı kayıttan
        okunur. Bilinmeyen malzeme yine sessizce çeliğe düşmez.
        """
        material = getattr(self, 'case_material', SOLID_CASE_DESIGN['material'])
        return float(self._case_material_properties(material)['density'])

    #: /calculate_solid uç noktasının kurucu varsayılanı. İstemci
    #: 'propellant_type' göndermediğinde uç nokta bu değeri koyduğu için
    #: "kullanıcı gerçekten seçti" ile "alan hiç gelmedi" ayrımı yalnız
    #: overrides sözlüğüne bakarak yapılabilir. V301/K-C2: son dalın
    #: düştüğü değer tek tanımdan (``SOLID_DEFAULT_PROPELLANT_TYPE``).
    #: "Seçilmedi" sayılan kurucu argümanı YALNIZ kütüphane varsayılanıdır
    #: (``SOLID_CONSTRUCTOR_PROPELLANT_TYPE``); ``/calculate_solid`` alan
    #: gelmediğinde kurucuya boş dize verir (açık 'kndx' argümanı bir seçimdir,
    #: kütüphane çağıranlarının davranışı değişmez).
    _DEFAULT_PROPELLANT_TYPE = SOLID_DEFAULT_PROPELLANT_TYPE
    _UNCHOSEN_PROPELLANT_TYPES = (SOLID_CONSTRUCTOR_PROPELLANT_TYPE,)

    def _resolve_propellant_type(self):
        """Yakıt kimliğini formun GERÇEKTEN gönderdiği alanlardan çözer.

        v2.6.26 (P3): katı sayfasında ``#propellant_type`` diye bir alan
        YOKTU; form yakıtı ``propellant_name`` (serbest metin) ve
        ``burn_rate_preset`` (katalog anahtarı) ile gönderiyordu.
        /calculate_solid ise ``data.get('propellant_type', 'apcp')`` ile
        okuduğu için HER koşu APCP oluyordu. Sonuç: KNDX seçen kullanıcıya
        HTPB elastomerin grain mekaniği (E = 6 MPa, kopma uzaması %35,
        kürleme 333 K) ve APCP'nin iki-fazlı kaybı (%4.08) raporlanıyordu —
        ateşlenecek bir grain hakkında verilebilecek en tehlikeli yanlış
        karar (bkz. _grain_mechanics docstring'i).

        Öncelik: açık ``propellant_type`` girdisi > kurucuya verilen
        (varsayılan olmayan) argüman > yanma-hızı ön ayarı > yakıt adı.
        Ad/ön ayar üzerinden çözüldüyse bu SESSİZ DEĞİLDİR: bilgi düzeyinde
        bir tasarım notu üretilir, çünkü kullanıcının seçtiği yakıt ile
        motorun çözdüğü yakıt arasındaki bağ türetilmiştir.
        """
        explicit = self.overrides.get('propellant_type')
        explicit = explicit.strip().lower() if isinstance(explicit, str) else ''
        if explicit:
            self.propellant_type = explicit
            self.propellant_type_source = 'propellant_type input'
            return
        # DİKKAT: alan BOŞ STRING olarak da gelebilir (kullanıcı katalog
        # satırı seçmediyse arayüz '' gönderir). Boş değer "seçim yapıldı"
        # sayılmaz; aksi hâlde ad/ön ayar üzerinden türetme yolu kapanır ve
        # motor yine sessizce APCP çözerdi.
        given = str(self.propellant_type or '').strip().lower()
        # Uç noktanın (ve kütüphane kurucusunun) koyduğu varsayılanı
        # "kullanıcı seçimi" saymayız.
        if given and given not in self._UNCHOSEN_PROPELLANT_TYPES:
            self.propellant_type = given
            self.propellant_type_source = 'constructor argument'
            return
        # V301/K-C2 (NK-29/NK-70): açık kimlik yoksa ön ayar ve ad AYRI AYRI
        # çözülür. İkisi FARKLI katalog kayıtlarına iniyorsa (ör. ad 'APCP',
        # ön ayar 'kndx') hangisinin yakıt olduğu girdiden okunamaz; birini
        # seçmek karışık kayıt üretir (yanma hızı bir yakıttan, ad/termokimya
        # ötekinden). Fail-closed: 422 + iki alan adıyla.
        adaylar = []
        for field, label in (('burn_rate_preset', 'burn-rate preset'),
                             ('propellant_name', 'propellant name')):
            candidate = _catalog_key_from_text(self.overrides.get(field))
            if candidate:
                adaylar.append((field, label, candidate))
        if len({c for _, _, c in adaylar}) > 1:
            (f1, _, c1), (f2, _, c2) = adaylar[0], adaylar[1]
            _mesaj = (
                f"No design was published: no propellant_type was sent and "
                f"the two fields that name a propellant disagree - {f1} = "
                f"'{self.overrides.get(f1)}' is the catalogue record '{c1}', "
                f"{f2} = '{self.overrides.get(f2)}' is '{c2}'. Choosing one "
                f"would mix two propellants (burn rate from one, identity "
                f"from the other). Send propellant_type (the solid page's "
                f"catalogue selector) or make the two fields agree.")
            raise SolidDesignRejected(_mesaj, [{
                'field': 'propellant_type',
                'reason': 'propellant_identity_conflict',
                'submitted': None,
                'conflicting_fields': {f1: str(self.overrides.get(f1)),
                                       f2: str(self.overrides.get(f2))},
                'resolved_records': {f1: c1, f2: c2},
                'motor_form': 'solid',
                'message': _mesaj,
            }], 'propellant_identity_conflict')
        for field, label, candidate in adaylar[:1]:
            self.propellant_type = candidate
            self.propellant_type_source = f'{label} ({field})'
            self.design_warnings.append(dict(_w(
                'warn.solid.propellant_type_derived', 'info',
                propellant=candidate, field=field,
                value=str(self.overrides.get(field))),
                fallback=("This request did not send propellant_type (the "
                          "solid page sends its catalogue selector; a "
                          "project saved before v3.0.5 or an API call may "
                          "not), so the propellant identity was derived "
                          "from '{field}' = '{value}' and resolved to "
                          "'{propellant}'. Grain mechanics, two-phase loss "
                          "and the published mixture come from that record.")))
            return
        self.propellant_type = given or self._DEFAULT_PROPELLANT_TYPE
        self.propellant_type_source = 'endpoint default'
        # Kullanıcı bir yakıt ADI yazdı ama hiçbir katalog kaydına
        # oturmadı: motor varsayılan kaydı çözer ve bu SESSİZ KALAMAZ.
        # _grain_mechanics burada uyarmaz, çünkü varsayılan kayıt vardır —
        # kullanıcı kendi karışımı için o kaydın sayılarını görür.
        typed_name = str(self.overrides.get('propellant_name') or '').strip()
        if typed_name and not _catalog_key_from_text(typed_name):
            self.design_warnings.append(dict(_w(
                'warn.solid.propellant_type_unresolved', 'warning',
                name=typed_name, used=self.propellant_type),
                fallback=("Propellant '{name}' does not match any catalogue "
                          "record, so the solver fell back to '{used}'. Grain "
                          "mechanics, two-phase loss and the published "
                          "mixture describe '{used}', NOT your formulation - "
                          "pick a catalogue row or enter the properties "
                          "explicitly.")))

    def _set_propellant_properties(self):
        """CEA-tutarlı yakıt referans setleri (sentetik referans, deneysel veri değil)"""
        propellant_data = {
            'apcp': {
                # ÖH KİTAP p1b (B11, seçenek F): termokimya bu tabloda
                # İKİNCİ KEZ YAZILMAZ, merkezi katalogdan (propellants_db.
                # _APCP_REFERENCE) TÜRETİLİR. Eski kopya (T_c 3614,8 K, c*
                # 1598,2, gamma 1,1986, M 28,0) c*'tan geri çözülmüş eşdeğer
                # bir setti ve katalogla ayrı ayrı güncellenmek zorundaydı
                # (rapor D-1). Değerler: NASA CEA, AP 68 / Al 18 / HTPB 14,
                # 68,9 bar — denge dörtlüsü + Bartz için donmuş oda gamma'sı
                # (künye katalogda). Yoğunluk da aynı kayıttan okunur.
                'rho': _PROPELLANT_CATALOG['apcp']['density'],
                'c_star': _PROPELLANT_CATALOG['apcp']['c_star'],
                'gamma': _PROPELLANT_CATALOG['apcp']['gamma'],
                'T_c': _PROPELLANT_CATALOG['apcp']['flame_temperature'],
                'molecular_weight': _PROPELLANT_CATALOG['apcp'][
                    'molecular_weight'],
                'gamma_frozen_chamber': _PROPELLANT_CATALOG['apcp'][
                    'gamma_frozen_chamber'],
                'name': 'Ammonium Perchlorate Composite Propellant',
                # Advanced properties
                'density_temp_coeff': -0.7e-3,  # kg/m³/K
                'c_star_pressure_coeff': 2.1,  # s·Pa^-1 
                'burn_rate_temp_coeff': 0.0042,  # 1/K
                'erosive_burning_coeff': 0.0136,  # Summerfield criterion (yeniden kalibre, #446: D^-0.2 formu)
                'nozzle_efficiency': 0.985  # Divergence + friction losses
            },
            'black_powder': {
                # V301/N-CEA-2 K5: termokimya İKİNCİ KEZ YAZILMAZ, merkezi
                # katalogdan okunur (apcp deseni). Eski kopya (c* 945,3 —
                # CEA idealinin %20 üstü, kaynaksız) kaldırıldı.
                'rho': _PROPELLANT_CATALOG['black_powder']['density'],
                'c_star': _PROPELLANT_CATALOG['black_powder']['c_star'],
                'gamma': _PROPELLANT_CATALOG['black_powder']['gamma'],
                'T_c': _PROPELLANT_CATALOG['black_powder'][
                    'flame_temperature'],
                'molecular_weight': _PROPELLANT_CATALOG['black_powder'][
                    'molecular_weight'],
                'name': 'Black Powder (KNO3/C/S)',
                'density_temp_coeff': -0.9e-3,
                'c_star_pressure_coeff': 1.8,
                'burn_rate_temp_coeff': 0.0038,
                'erosive_burning_coeff': 0.0110,  # yeniden kalibre (#446)
                'nozzle_efficiency': 0.975
            },
            # Şeker yakıtları (KNO3 + şeker). DİKKAT: değerler NASA CEA'dan
            # (KNO3 %65 / sakaroz %35, Pc=68.9 bar) iki-faz (K2CO3/K yoğuşması)
            # DAHİL gerçek değerlerdir; bu yüzden saf-gaz Eq.3-32 ile değil
            # doğrudan CEA c*'ı ile tutulur (Al'lı APCP gibi iki-fazlı).
            # Nakka-rocketry.net deneysel verisiyle uyumlu (KNSU ~890-920 m/s,
            # Tc ~1700-1720 K). Eski değerler (c*=1523/Tc=3104) fiziksel olarak
            # imkansızdı (APCP sınıfı) ve itkiyi tehlikeli biçimde yüksek
            # gösteriyordu — düzeltildi (2026-06).
            # ÖH D15 (P2B1-04): 'sugar' ve 'knsu' AYNI yakıttır (KNO3 %65 /
            # sakaroz %35) ve termokimyaları zaten birebir aynıydı
            # (c*=921,0; gamma=1,1235; T_c=1719,0; M=37,21). Buna rağmen
            # bileşimden türeyen İKİNCİL katsayılar ayrışıyordu: erozif
            # katsayı 0,0123 ⟷ 0,0155 (+%26,0), sıcaklık katsayısı 0,0041 ⟷
            # 0,0045 (+%9,8), nozul verimi 0,978 ⟷ 0,983. Aynı kimyanın iki
            # farklı erozif katsayısı olamaz; bu bir veri ikilemesiydi, fizik
            # değil. Katsayılar artık TEK yerde (_KNSU_65_35_BASE) tanımlıdır
            # ve iki satır yalnız YOĞUNLUK TABANINDA ayrılır — o fark
            # gerçektir (dökme ⟷ ideal) ve satırın ADINDA yazılıdır.
            'sugar': dict(
                _KNSU_65_35_BASE,
                rho=1785,  # kg/m³ (dökme/dökülmüş KNSU, ulaşılabilir taban)
                # ÖH D34 · OH-GT-17: ad TEK KAYNAKTAN okunur — aynı dize
                # hrma/data/propellants_db.py'de de yazılıydı ve ikisi
                # AYRIŞMIŞTI (katalog '65/35' demeden 'cast bulk density'
                # diyordu, burası ikisini birden). Katalog kaydı ölçüt.
                name=_PROPELLANT_CATALOG['sugar']['name'],
                density_basis='cast bulk density (achievable in an amateur '
                              'cast grain)',
            ),
            'knsu': dict(
                _KNSU_65_35_BASE,
                rho=1889,  # kg/m³ (ideal = teorik maksimum yoğunluk)
                # ÖH D34 · OH-GT-17: ad TEK KAYNAKTAN (bkz. 'sugar').
                name=_PROPELLANT_CATALOG['knsu']['name'],
                density_basis='ideal (theoretical maximum) density; a cast '
                              'grain reaches roughly 1785 kg/m3, so this row '
                              'reports about 5.8% more propellant mass',
            ),
            # ------------------------------------------------------------------
            # ÖH D15 a2 (P2B1-01) — KAYIT KENDİ İÇİNDE TUTARSIZ, ONARIM
            # BU KULVARDA ENGELLİ (dosya sahipliği).
            #
            # ÖLÇÜLDÜ (bu aşamanın once.json'u, Eq. 3-32 kaydın KENDİ
            # (gamma, T_c, M) üçlüsüne uygulanarak):
            #   apcp          c* 1598,2 ⟷ 1598,2   -0,0001 %  (kesir 0,340)
            #   sugar/knsu    c*  921,0 ⟷  978,7   -5,90   %  (kesir 0,44, BEYANLI)
            #   black_powder  c*  945,3 ⟷ 1131,7  -16,47   %  (kesir 0,55, iki-fazlı)
            #   double_base   c* 1186,7 ⟷ 1406,8  -15,64   %  (kesir 0,00 -> MAZERET YOK)
            # SOLID_CONDENSED_MASS_FRACTION['double_base'] = 0,0 ("dumansız,
            # tek faz") olduğu için tek fazlı ideal gaz Eq. 3-32'yi sağlamak
            # ZORUNDADIR. Ürün yüzündeki belirti: aynı yanıt iki egzoz hızı
            # yayımlıyor — Isp*g0 = 1684,0 m/s ⟷ nozzle_design.performance.
            # exit_velocity = 2106,8 m/s (+%25,1; APCP'de aynı fark %5,57).
            #
            # Hangi yarının yanlış olduğu iki bağımsız çizgiyle belirlendi:
            #  (a) literatür bandı — çift bazlı yakıt c* ~ 1400-1550 m/s;
            #      1406,8 bandın içinde, 1186,7 bandın çok altında;
            #  (b) ürün yüzü — isp_vacuum = 193,83 s, yayımlanmış çift bazlı
            #      bant 210-230 s. Yani DÜŞÜK olan yarı (c*) şüpheli taraftır.
            #
            # ONARILDI (ÖH D15, ana model 1 Eyl 2026): iki dosya AYNI commit'te —
            # bu tablo ve hrma/data/propellants_db.py kataloğu c*=1406,8; katalogdaki
            # _CSTAR_NOTLARI['double_base'] beyanı kaldırıldı. Bekçi: test_d15_kati_a2
            # ::TestP2B1_01KayitTutarliligi (xfail imi söküldü) + test_propellants_db
            # ::TestEngineConsistency (tek kaynak).
            'double_base': {
                'rho': 1580,
                'c_star': 1406.8,   # ÖH D15 P2B1-01: katalogla birlikte Eq. 3-32 idealine çekildi (1406,774)
                'gamma': 1.2612,
                'T_c': 2789.3,
                'molecular_weight': 26.89,
                'name': 'Double Base Propellant',
                'density_temp_coeff': -1.1e-3,
                'c_star_pressure_coeff': 1.7,
                'burn_rate_temp_coeff': 0.0036,
                'erosive_burning_coeff': 0.0115,  # yeniden kalibre (#446)
                'nozzle_efficiency': 0.981
            }
        }
        
        # v2.6.26 (K4): motorun kendi tablosunda kaydı OLMAYAN ama merkezi
        # katalogda bulunan yakıtlar (kndx, knsb, kner, pban_ap_al...) artık
        # sessizce 'Custom' (c*=1200, Tc=2500) varsayımına düşmüyor;
        # termokimya katalogtan okunuyor, ikincil katsayılar aynı ailenin
        # motor kaydından DEVRALINIYOR ve devralma uyarı olarak beyan ediliyor.
        prop = propellant_data.get(self.propellant_type)
        self.propellant_property_source = ('engine table' if prop is not None
                                           else None)
        if prop is None:
            prop, inherited_from = self._catalog_propellant_record(
                propellant_data)
            if prop is not None:
                self.propellant_property_source = (
                    f'central catalogue (propellants_db); secondary '
                    f'coefficients inherited from {inherited_from}'
                    if inherited_from else
                    'central catalogue (propellants_db)')
                if inherited_from:
                    self.design_warnings.append(dict(_w(
                        'warn.solid.propellant_secondary_inherited', 'info',
                        propellant=str(self.propellant_type),
                        source=str(inherited_from)),
                        fallback=("Thermochemistry for '{propellant}' comes "
                                  "from the central propellant catalogue; the "
                                  "secondary coefficients (erosive k, "
                                  "temperature sensitivity, nozzle "
                                  "efficiency) have no published record for "
                                  "it and are inherited from '{source}' of "
                                  "the same family.")))

        if prop is not None:
            self.rho_p = prop['rho']
            self.c_star = prop['c_star']
            self.gamma = prop['gamma']
            self.T_c = prop['T_c']
            self.propellant_name = prop['name']
            # Ensure nozzle efficiency is available for later calculations
            self.nozzle_efficiency = prop.get('nozzle_efficiency', 0.98)
            # Egzoz molekül ağırlığı (Bartz ısı akısı gaz özellikleri için)
            self.mw_exhaust = prop.get('molecular_weight', 26.0)  # g/mol
            # Erozif yanma katsayısı (burn_rate içindeki düzeltme bunu kullanır;
            # atanmazsa model tetiklendiğinde AttributeError oluşur)
            self.erosive_burning_coeff = prop.get('erosive_burning_coeff', 0.0)
            # ÖH D15 (P2B1-02): form varsayılanının yakıt tablosunu ezip
            # ezemeyeceğine karar verebilmek için tablonun o katsayıyı
            # GERÇEKTEN taşıyıp taşımadığı kaydedilir (0 / yok = kalibre
            # değer yok demektir, o zaman kullanıcının sayısı uygulanır).
            self._table_coeff_present = {
                'erosive_burning_coeff': bool(
                    float(prop.get('erosive_burning_coeff') or 0.0) > 0.0),
                'burn_rate_temp_coeff': 'burn_rate_temp_coeff' in prop,
            }
            # OPUS DENETİM DÜZELTMESİ (minor): yakıta özgü sıcaklık katsayısı
            # daha önce ölü veriydi (constructor default'u 0.002 hep ezik
            # kalıyordu) — dict'te varsa yakıt değeri kullanılır
            if 'burn_rate_temp_coeff' in prop:
                self.burn_rate_temp_coeff = prop['burn_rate_temp_coeff']
        else:
            # Ne motor tablosunda ne merkezi katalogda kaydı var: jenerik
            # varsayım kullanılır ama SESSİZ DEĞİL — kullanıcı hangi sayıların
            # kendi yakıtına ait OLMADIĞINI görmek zorunda (form alanları
            # (yoğunluk, c*, gama, Tc) bu varsayımları ezer).
            self.rho_p = 1700
            self.c_star = 1200
            self.gamma = 1.25
            self.T_c = 2500
            self.propellant_name = 'Custom'
            self.mw_exhaust = 26.0  # g/mol, tipik katı yakıt egzozu
            self.nozzle_efficiency = 0.98
            self.erosive_burning_coeff = 0.0
            self._table_coeff_present = {'erosive_burning_coeff': False,
                                         'burn_rate_temp_coeff': False}
            self.propellant_property_source = 'generic placeholder (no record)'
            self.design_warnings.append(dict(_w(
                'warn.solid.propellant_type_unknown', 'warning',
                propellant=str(self.propellant_type),
                known=', '.join(sorted(propellant_data))),
                fallback=("Propellant '{propellant}' has no record in HRMA "
                          "(known engine propellants: {known}). Generic "
                          "placeholder properties were used; grain mechanics "
                          "and two-phase loss are reported as 'no data' "
                          "rather than guessed. Enter density, c*, gamma and "
                          "flame temperature explicitly.")))

        # Teorik (kayıpsız) c* — _apply_overrides yanma verimini uyguladıktan
        # SONRA self.c_star teslim edilen değerdir; verim raporları teorik
        # değere normalize edilir. Burada güvenli bir başlangıç kurulur.
        self.c_star_theoretical = self.c_star
        # ÖH KİTAP p1b (B11, seçenek F): kaydın donmuş oda gamma'sı ve onun
        # ait olduğu DENGE gamma'sı birlikte saklanır. Bartz zinciri donmuş
        # değeri yalnız motorun gamma'sı hâlâ kaydınkiyse kullanır
        # (_bartz_gas_gamma); kayıt yoksa ya da alan None ise ikisi de None.
        self.gamma_frozen_chamber = (prop or {}).get('gamma_frozen_chamber')
        self._gamma_frozen_equilibrium_ref = (prop or {}).get('gamma')
        # 3. tur (karar §28-47, Ş2-2 (a)): donmuş değer taşıyan kayıt bir
        # NASA CEA KARIŞIM kaydıdır (GAMMAs ve M(1/n) yoğuşkan faz dahil).
        # Kaydın M'si de saklanır: iki faz modülüne giden gaz çiftinden biri
        # hâlâ kaydınkiyse yoğuşkan faz termokimyada zaten vardır.
        self._mw_frozen_record_ref = (
            (prop or {}).get('molecular_weight')
            if self.gamma_frozen_chamber is not None else None)

    def _catalog_propellant_record(self, engine_table):
        """Motor tablosunda olmayan yakıt için kayıt üret — (kayıt, devir_kaynağı).

        Termokimya (yoğunluk, c*, gama, alev sıcaklığı, molekül ağırlığı, ad)
        merkezi katalogtan (propellants_db) OKUNUR; ikinci bir kopya
        tutulmaz (CLAUDE.md kural 11: aynı sayı iki yerde tanımlanmaz).
        Katalogta bulunmayan ikincil katsayılar (erozif k, sıcaklık
        duyarlılığı, nozul verimi) yayımlanmış değeri olmadığı için
        UYDURULMAZ; aynı ailenin motor kaydından devralınır ve devralmanın
        kaynağı geri döndürülür (çağıran taraf beyan eder).
        """
        key = _catalog_key_for(self.propellant_type)
        rec = _get_propellant_safe(key) if key else None
        if not rec:
            return None, None
        base, base_key = _family_lookup(self.propellant_type, engine_table)
        prop = {
            'rho': float(rec['density']),
            'c_star': float(rec['c_star']),
            'gamma': float(rec['gamma']),
            'T_c': float(rec['flame_temperature']),
            'molecular_weight': float(rec['molecular_weight']),
            'name': rec.get('name', key),
        }
        # ÖH KİTAP p1b (B11, seçenek F): kaydın ölçülmüş donmuş oda
        # gamma'sı (Bartz cp/Pr türetimi) termokimyanın parçasıdır, kayıttan
        # taşınır. Aile temsilcisinden DEVRALINMAZ (bileşime özgüdür): kayıtta
        # yoksa None kalır ve motor tek gamma'yla çözer.
        frozen = rec.get('gamma_frozen_chamber')
        prop['gamma_frozen_chamber'] = (float(frozen) if frozen is not None
                                        else None)
        if base:
            for field_name in ('density_temp_coeff', 'c_star_pressure_coeff',
                               'burn_rate_temp_coeff', 'erosive_burning_coeff',
                               'nozzle_efficiency'):
                if field_name in base:
                    prop[field_name] = base[field_name]
        return prop, base_key

    def _bates_segment_count(self):
        """BATES segment sayısı — TEK tanım noktası.

        Konvansiyon: L_seg ≈ D_chamber — yaygın uygulama kuralı, KAYNAKSIZ
        (eski künye "NASA SP-8064" idi; o monografta segment boyu konusu yok,
        KU-K2). Nötr BATES koşulu L_seg = 4·r_core + 3·web bununla AYNI
        DEĞİLDİR (D 100 mm, d 30 mm için nötr L_seg 165 mm; bkz.
        ``bates_core_factor``/``bates_web_factor``). grain_design çıktısı
        ve yanma alanı modeli AYNI sayıyı kullanmalıdır (Opus denetim bulgusu:
        önceden rapor 5 segment derken model tek monolitik grain yakıyordu →
        aşırı progressif profil, Pc 3.4 kat şişiyordu).

        Kullanıcı formdan grain_count gönderdiyse (1-20) o kullanılır; yanma
        alanı modeli ve grain_design raporu aynı yerden okuduğu için tutarlılık
        bozulmaz.
        """
        user_n = self._user_segment_count()
        if user_n is not None:
            return user_n
        return max(1, round(self.L_grain / self.D_chamber))

    def _user_segment_count(self):
        """Kullanıcının istediği BATES segment sayısı (yoksa None).

        'grain_count' form alanının, 'n_segments' aynı büyüklüğün API tarafındaki
        adıdır; ikincisi eskiden sessizce yok sayılıyordu.
        """
        n_max = SOLID_DESIGN_POINT['max_segments']
        anahtar = 'grain_count'
        user_n = self._override_val(anahtar, 1, n_max)
        if user_n is None:
            anahtar = 'n_segments'
            user_n = self._override_val(anahtar, 1, n_max)
        if user_n is None:
            return None
        # v3.0.1 (V301/K-A, KT-13): segment sayısı TAM SAYIDIR. 2,5 eskiden
        # ``int(round(2.5)) = 2`` ile sessizce kesiliyordu (ölçüldü: HTTP
        # 200, itki 3114 N, ret yok). Tam olmayan değer reddedilir ve
        # ``rejected_inputs``e işlenir; ``/calculate_solid`` onu 422'ye
        # çevirir. Tam sayıya eşit bir ondalık (3.0) kabul edilir.
        if abs(float(user_n) - round(float(user_n))) > 1e-9:
            self._reject_input(
                anahtar, self.overrides.get(anahtar),
                'value {} is not a whole number of grain segments; the '
                'field was ignored and the built-in segment count was used '
                'instead.'.format(round(float(user_n), 6)),
                code='not_a_whole_number', accepted_range=(1, n_max))
            return None
        return int(round(user_n))

    #: V301/K-B (KT-07): BATES dışı tiplerde anlamı olmayan alanlar. Ölçüldü
    #: (denetim ``tane_tipi.json``): star / finocyl / slotted / wagon_wheel /
    #: end_burner'da bu alanların her biri değiştirildiğinde 0 sonuç yaprağı
    #: değişiyor (tane tek segment, uç/dış yüzey düzeni tipin kendi
    #: tanımından). Uç yanmalı tanede çekirdek de yoktur.
    _BATES_ONLY_FIELDS = ('grain_count', 'n_segments', 'grain_gap',
                          'inhibit_front', 'inhibit_rear', 'inhibit_outer')

    def _grain_type_inapplicable_fields(self):
        """Bu tane tipinde hesaba GİRMEYEN girdi alanları (beyan listesi)."""
        tip = str(getattr(self, 'grain_type', '') or '').strip().lower()
        if tip == 'bates':
            return ()
        alanlar = self._BATES_ONLY_FIELDS
        if tip == 'end_burner':
            alanlar = alanlar + ('core_diameter',)
        return alanlar

    # ------------------------------------------------------------------
    # Tasarım noktası: hedef ortalama itki + yanma süresinden boyutlandırma
    # ------------------------------------------------------------------
    def _exit_pressure_ratio(self, epsilon):
        """Sabit ε için süpersonik dal P_e/P_c oranı (izentropik).

        Sutton & Biblarz 9. baskı Denk. 3-25/3-26'nın TERS çözümü: verilen
        alan oranından çıkış Mach'ı, ondan basınç oranı. Sonuç örnek üstünde
        önbelleklenir (itki eğrisi her adımda çağırır, ε sabittir).
        """
        cache = getattr(self, '_pe_ratio_cache', None)
        # V301/N-CEA-2 (K2): lüle bağıntılarının üssü (CEA lülesi varsa
        # eşdeğer üs γ_n; tasarım ε'unda CEA'nın P_e/P_c'sini TAM verir).
        gamma = float(self._nozzle_gamma())
        key = (round(gamma, 12), round(float(epsilon), 12))
        if cache is not None and cache[0] == key:
            return cache[1]
        eps = max(float(epsilon), 1.0000001)

        def area_ratio(M):
            return (1.0 / M) * ((2.0 / (gamma + 1.0))
                                * (1.0 + (gamma - 1.0) / 2.0 * M * M)) \
                ** ((gamma + 1.0) / (2.0 * (gamma - 1.0))) - eps

        try:
            from scipy.optimize import brentq
            M_e = brentq(area_ratio, 1.0 + 1e-9, 60.0)
        except Exception:
            # Sayısal çözüm başarısızsa oranı doğrudan hesaplayamayız;
            # çağıran taraf sonsuz genişleme varsaymasın diye 0 döner
            # (basınç-itki terimi kaybolur, momentum terimi kalır).
            M_e = None
        if M_e is None:
            ratio = 0.0
        else:
            ratio = float((1.0 + (gamma - 1.0) / 2.0 * M_e * M_e)
                          ** (-gamma / (gamma - 1.0)))
        self._pe_ratio_cache = (key, ratio)
        return ratio

    def _nozzle_exit_state(self):
        """Sabit geometrili nozulun çıkış düzlemi durumu (tasarım Pc'de).

        Egzoz (plume) gösterimi ve nozul performans raporu için TEK tanım
        noktası. Hepsi aynı izentropik kümeden türer (Sutton & Biblarz
        9. baskı, Denk. 3-15/3-16/3-25):

          * P_e/P_c: ε'dan çözülür (bkz. _exit_pressure_ratio — itki
            eğrisinin kullandığı çözümün AYNISI, yeni fizik yok),
          * M_e: aynı oranın kapalı form tersi,
          * T_e = T_c / (1 + (γ-1)/2·M_e²),
          * v_e = M_e·√(γ·R_s·T_e), R_s = R_UNIVERSAL / MW_egzoz.

        _exit_pressure_ratio sayısal çözümü başaramazsa (ratio = 0 döner)
        alanlar None kalır — sayı UYDURULMAZ, egzoz çizilmez.
        """
        gamma = float(self._nozzle_gamma())
        epsilon = float(self._estimate_expansion_ratio())
        pe_ratio = float(self._exit_pressure_ratio(epsilon))
        p_amb = float(getattr(self, 'ambient_pressure_bar',
                              SEA_LEVEL_PRESSURE_BAR))
        state = {
            'expansion_ratio': epsilon,
            'ambient_pressure_bar': p_amb,
            'exit_pressure_bar': None,
            'exit_mach': None,
            'exit_temperature_k': None,
            'exit_velocity_ms': None,
        }
        if pe_ratio <= 0.0:
            return state
        # P_e/P_c = [1+(γ-1)/2·M²]^(-γ/(γ-1)) bağıntısının kapalı form tersi
        m_e_sq = (2.0 / (gamma - 1.0)) * (pe_ratio
                                          ** (-(gamma - 1.0) / gamma) - 1.0)
        if m_e_sq <= 0.0:
            return state
        m_e = float(np.sqrt(m_e_sq))
        t_exit = float(self.T_c) / (1.0 + 0.5 * (gamma - 1.0) * m_e * m_e)
        mw = float(getattr(self, 'mw_exhaust', 26.0))
        r_specific = R_UNIVERSAL / mw
        # Tek fazlı GAZ hızı (izentropik çıkış düzlemi). Özdeşlik:
        #     M_e*sqrt(g*R_s*T_e) == CF_momentum(eps) * c*_tek_faz_ideal
        # (ikisi de sqrt(2*g*R_s*(T_c - T_e)/(g-1))'e indirgenir).
        v_gaz = float(m_e * np.sqrt(gamma * r_specific * t_exit))
        # V301/N-CEA-2 (K2): CEA lülesi tasarım ε'undaysa çıkış Mach'ı,
        # sıcaklığı ve (karışım) hızı CEA'nın kayan denge çözümünden:
        # u_e = C_F,mom,CEA · c*_CEA (NASA RP-1311: Isp(P_e) = u_e/g0).
        lule = self._cea_nozzle_state()
        cea_cikis = bool(lule) and abs(
            epsilon / float(lule['expansion_ratio']) - 1.0) <= 1e-9
        if cea_cikis:
            m_e = float(lule['exit_mach'])
            t_exit = float(lule['exit_temperature_K'])
            v_gaz = float(lule['cf_momentum']) * float(
                self._c_star_theoretical())
        # --- ÖH D20 / P2B1-01 · TEK KAYNAK: EGZOZ HIZI TESLİM EDİLEN c*'TAN --
        # ÖLÇÜLDÜ (docs/scofield/raw/OH/D20/fizik/a1/once.json): bu blok
        # egzoz hızını kaydın (gamma, MW, T_c) ÜÇLÜSÜNDEN çözüyordu, yani
        # örtük olarak TEK FAZLI ideal c*'ı kullanıyordu; motorun itki
        # eğrisi ve irtifa satırları ise kaydın TESLİM EDİLEN c*'ını
        # kullanır. Yoğuşmuş faz beyan eden kayıtlarda ikisi aynı sayı
        # DEĞİLDİR ve aynı yanıtta iki egzoz hızı yayımlanıyordu:
        #
        #   yakıt         X_p    c*_kayıt/c*_ideal   panel v_e / irtifa v_e
        #   apcp          0,340        1,0000              +%1,523  (= 1/eta)
        #   double_base   0,000        1,0000              +%1,935  (= 1/eta)
        #   kndx/knsb     0,440        1,0000              +%2,250  (= 1/eta)
        #   knsu/sugar    0,440        0,9410              +%8,657
        #   black_powder  0,550        0,8353             +%22,784
        #
        # Fark TAM olarak (c*_ideal/c*_teslim) x (1/eta_nozzle) çarpımıydı
        # (yedi yakıtta da 5 hane özdeş): ikinci çarpan MEŞRUDUR ve
        # beyanlıdır (panel hızı nozul verimi taşımaz), birincisi KUSURDUR
        # — bu motorun sahip olmadığı, tek fazlı varsayımsal bir gazın
        # hızıydı. Onarım: hız, itki zincirinin kullandığı c* ile AYNI
        # kaynaktan türetilir (v_e = CF_momentum * c*_teslim); yoğuşmuş
        # fazın momentumu kütle-ortalamalı hızda zaten taşınır
        # (Sutton & Biblarz 9. baskı Böl. 3.5, çok fazlı akış; c* tanımı
        # mdot = p_c*A_t/c* olduğundan v_e = CF_mom*c* özdeşliği faz
        # kompozisyonundan bağımsızdır). Kaydın c*'ı kendi tek fazlı
        # idealiyle tutarlıysa (apcp, double_base, kndx, knsb) sayı
        # DEĞİŞMEZ; yalnız iki-faz açığı beyan eden kayıtlar düzelir.
        #
        # FAIL-CLOSED: tek fazlı ideal c* çözülemezse oran kurulamaz ve
        # hız YAYIMLANMAZ (uydurma sayı yok, egzoz çizilmez).
        c_star_teslim = float(getattr(self, 'c_star', 0.0) or 0.0)
        c_star_ideal = (float(self._c_star_theoretical()) if cea_cikis else
                        _ideal_single_phase_c_star(gamma, self.T_c, mw))
        if (c_star_ideal is None or not np.isfinite(c_star_ideal)
                or c_star_ideal <= 0.0 or c_star_teslim <= 0.0):
            v_exit = None
            c_star_orani = None
            hiz_temeli = (
                'not published: the delivered c* or the single-phase ideal '
                'c* (Sutton & Biblarz 9th ed. Eq. 3-32) could not be '
                'resolved, so the exhaust velocity cannot be tied to the '
                'thrust chain; no single-phase number is published in its '
                'place')
        else:
            c_star_orani = float(c_star_teslim) / float(c_star_ideal)
            v_exit = float(v_gaz * c_star_orani)
            hiz_temeli = (
                'v_e = CF_momentum(eps) * c*_delivered, the SAME c* the '
                'thrust curve and the altitude rows use. Equivalent form '
                'used here: the isentropic single-phase gas velocity '
                'M_e*sqrt(gamma*R_s*T_e) scaled by '
                'c*_delivered / c*_single_phase_ideal (Sutton & Biblarz '
                '9th ed. Eq. 3-32), because M_e*sqrt(gamma*R_s*T_e) is '
                'identically CF_momentum * c*_single_phase_ideal. For a '
                'record whose c* carries a condensed-phase (two-phase) '
                'deficit this is the mass-averaged exhaust velocity of the '
                'gas+condensed mixture, not the velocity of a hypothetical '
                'single-phase gas. No nozzle efficiency is applied (that is '
                'what separates this number from Isp*g0)')
        if cea_cikis:
            hiz_temeli = (
                'v_e = CF_momentum_CEA(eps) * c*_delivered: NASA CEA '
                'shifting-equilibrium exit state (condensed phase included, '
                'mass-averaged velocity) at the design chamber pressure, '
                'scaled by the combustion efficiency; exit Mach number and '
                'temperature are the CEA exit-station values. No nozzle '
                'efficiency is applied (that is what separates this number '
                'from Isp*g0)') if v_exit is not None else hiz_temeli
        state.update({
            'exit_state_source': ('nasa_cea_shifting_equilibrium'
                                  if cea_cikis else
                                  'single_gamma_isentropic'),
            'exit_pressure_bar': float(pe_ratio * self.P_c),
            'exit_mach': m_e,
            'exit_temperature_k': t_exit,
            'exit_velocity_ms': v_exit,
            'exit_velocity_basis': hiz_temeli,
            'gas_phase_exit_velocity_ms': v_gaz,
            'c_star_delivered_m_s': (c_star_teslim if c_star_teslim > 0.0
                                     else None),
            'c_star_single_phase_ideal_m_s': (
                None if c_star_ideal is None else float(c_star_ideal)),
            'c_star_ratio_delivered_over_ideal': c_star_orani,
        })
        return state

    def _thrust_coefficient(self, P_c_bar):
        """SABİT GEOMETRİLİ nozulun itki katsayısı CF(P_c).

        FİZİK DENETİMİ DÜZELTMESİ (F068, 2026-07-25): eski kod her basınçta
        Pe = Pa (anlık optimum genişleme) varsayıyordu. Bu, Sutton Denk. 3-30'un
        ÖZEL hâlidir ve her zaman ULAŞILABİLİR EN BÜYÜK CF'i verir. Gerçek
        motorun nozulu ise sabit geometrilidir (ε = A_e/A_t sabit): Pc yanma
        boyunca düştükçe nozul tasarım-dışına düşer ve CF gerçekte AZALIR.
        Ölçüm (BATES, APCP, tasarım 40 bar, ε = 5.93): Pc 40 → 7.8 bar
        kuyruğunda eski formül gerçek CF'i +%33.6'ya kadar aşıyordu.

        Doğru form (Sutton & Biblarz 9. baskı Denk. 3-30/3-31):
            CF = η · [ CF_momentum(ε) + ε·(P_e − P_a)/P_c ]
        P_e/P_c oranı ε'dan izentropik olarak ÇÖZÜLÜR (bkz.
        _exit_pressure_ratio); aynı doğru form projenin hibrit modülünde
        (transient_ballistics._thrust_coefficient) zaten kullanılıyordu.

        Tasarım basıncında ε tam olarak Pe = Pa verecek şekilde seçildiği için
        (bkz. _estimate_expansion_ratio) basınç-itki terimi SIFIRLANIR ve
        sonuç eski formülle BİREBİR aynı kalır — tasarım noktası
        boyutlandırması bozulmaz, yalnız tasarım-dışı kuyruk düzelir.

        Akış ayrılması, kırpma yerine kesilmiş-lüle modeliyle çözülür; tam
        gerekçe ``_thrust_coefficient_state`` docstring'indedir.
        """
        return self._thrust_coefficient_state(P_c_bar)['cf']

    def _cf_momentum_term(self, pressure_ratio):
        """Sutton & Biblarz Denk. 3-30'un momentum terimi — TEK tanım noktası.

        Verilen ``P_e/P_c`` için ideal itki katsayısının basınç-itki
        teriminden ARINIK kısmı. Hem ortam basınçlı (deniz seviyesi / irtifa)
        hem vakum zinciri bu bağıntıyı kullanır; ikisi ayrı yazılırsa aynı
        motorun iki farklı fiziği olur (v2.6.27, F2-2).
        """
        # V301/N-CEA-2 (K2): CEA lülesi varsa γ_n ve CEA çapası κ (tasarım
        # P_e/P_c'sinde momentum terimi CEA'nınkine TAM eşit).
        return float(self._nozzle_cf_anchor() * self._cf_momentum_1d(
            pressure_ratio, self._nozzle_gamma()))

    def _thrust_coefficient_vacuum(self):
        """Bu motorun KENDİ lülesinin vakum itki katsayısı (verim uygulanmış).

        v2.6.27 (bebek-Scofield F2-2). Vakum Isp'si daha önce
        ``hrma.constants.vacuum_isp_ratio()`` ampirik log-fitiyle
        (``0,953 + 0,0405·ln ε``) deniz seviyesi Isp'sinden ölçekleniyordu.
        O çarpan HAZNE BASINCINI HİÇ GÖRMÜYOR, oysa gerçek oran

            CF_vac / CF_SL = 1 + (P_a/P_c)·ε / CF_SL

        ile doğrudan P_c'ye bağlıdır. ÖLÇÜLDÜ (varsayılan APCP motoru,
        yanıtın kendi CF zinciriyle karşılaştırma; ``+`` yayımlanan değerin
        fazlalığı):

            Pc =  20 bar, ε = 3,60 -> yayımlanan 215,77 s, kendi CF'i 242,56 s  (−11,04 %)
            Pc =  40 bar, ε = 5,93 -> yayımlanan 240,70 s, kendi CF'i 258,01 s  ( −6,71 %)
            Pc =  80 bar, ε = 9,95 -> yayımlanan 262,83 s, kendi CF'i 270,85 s  ( −2,96 %)
            Pc = 150 bar, ε = 16,08 -> yayımlanan 281,03 s, kendi CF'i 280,71 s ( +0,11 %)

        yani ampirik çarpan yalnız yüksek basınç / büyük ε köşesinde tutuyor;
        bu deponun tipik amatör motor rejiminde (40 bar, küçük ε) yanıt kendi
        fiziğiyle çelişiyordu.

        Vakumda ortam basıncı sıfırdır: akış ayrılması olamaz, lüle her zaman
        boğulmuştur ve basınç-itki terimi tam ε·P_e/P_c olur.
        Kaynak: Sutton & Biblarz, Rocket Propulsion Elements 9. baskı,
        Denk. 3-30/3-31 (P_a = 0 özel hâli).
        """
        epsilon = float(self._estimate_expansion_ratio())
        pe_ratio = float(self._exit_pressure_ratio(epsilon))
        cf_ideal = self._cf_momentum_term(pe_ratio) + epsilon * pe_ratio
        return float(cf_ideal * self._total_nozzle_efficiency())

    def _thrust_coefficient_state(self, P_c_bar):
        """CF(P_c) ve akış AYRILMASI durumu — TEK hesap, tek tanım noktası.

        AYRILMA ARTIK SIFIRA KIRPILMIYOR (v2.6.27, A1-2)
        ------------------------------------------------
        Eski kod, aşırı genişlemede negatife giden basınç-itki terimini
        ``CF = max(CF, 0)`` ile kırpıyordu. Bu, çalışmaya DEVAM EDEN bir
        motoru eğride 0 N gösteriyordu: kamara basıncı ve kütle debisi
        pozitifken itki sıfır. ÖLÇÜLDÜ (APCP, D_kamara=100 mm,
        D_çekirdek=30 mm, L=500 mm, 40 bar, deniz seviyesi; eski davranış):

            slotted      örneklerin %31,0'inde F = 0 iken Pc > 0
            wagon_wheel  %21,0        (ilk sıfır t = 1,31 s, Pc = 3,26 bar)
            star         %17,0        (ilk sıfır t = 1,48 s, Pc = 3,22 bar)

        Toplam impuls kaybı küçüktü (~%2) ama eğri kullanıcıya YALAN
        söylüyordu. Aynı fiziği üç motor üç farklı şekilde ele alıyordu:
        sıvı modül ayrılmayı UYARIYOR, katı sessizce sıfıra kırpıyor, hibrit
        hiç kırpmıyordu.

        KULLANILAN MODEL: KESİLMİŞ (TRUNCATED) LÜLE
        -------------------------------------------
        Aşırı genişlemiş sabit geometrili lülede akış, cidar basıncı ortam
        basıncının belirli bir kesrinin altına düştüğü istasyonda ayrılır;
        ayrılma noktasının ARDINDAKİ koni artık akışı taşımaz ve cidarı
        yaklaşık ortam basıncını görür. Dolayısıyla motor, ayrılma alan
        oranında KESİLMİŞ bir lüle gibi davranır:

            P_ayr/P_c = k·P_a/P_c        (k = SUMMERFIELD_SEPARATION_RATIO)
            ε_ayr     = ε(P_ayr/P_c)     (izentropik alan-oranı bağıntısı)
            CF        = CF_momentum(P_ayr/P_c) + ε_ayr·(P_ayr − P_a)/P_c

        Bu, ekli akış bağıntısının ayrılma istasyonuna uygulanmış hâlidir;
        ayrılma sonrası koninin negatif basınç-itki katkısı toplanmaz. Sonuç
        fiziksel bir ALT SINIR üretir: ayrılma boğaza doğru ilerledikçe
        ε_ayr → 1 ve CF → sonik lülenin katsayısına (deniz seviyesinde
        Pc = 5 bar, γ = 1,2 için CF ≈ 1,04) iner, yani itki F ≈ mdot·c*
        mertebesinde kalır — sıfıra çakılmaz.
        Kaynak: Sutton & Biblarz, Rocket Propulsion Elements 9. baskı,
        Böl. 3 (Denk. 3-30/3-31) ve Böl. 5 (ayrılma ve kesilmiş lüle);
        Summerfield ayrılma ölçütü için aynı bölümler.

        BOĞULMA SINIRI: bütün bağıntılar boğazın sonik olduğunu varsayar
        (çözücünün mdot = Pc·A_t/c* modeli de öyle). Pc, P_a/((γ+1)/2)^(γ/(γ−1))
        değerinin altına düşerse lüle boğulmaz; orada sayı UYDURULMAZ,
        durum 'not_choked' olarak beyan edilir ve CF sıfır döner.

        Dönüş alanları: cf, cf_ideal, cf_attached_ideal, separated,
        separation_area_ratio, pe_bar, pe_over_pa, choked, status, criterion.
        """
        gamma = float(self._nozzle_gamma())
        p_amb = float(getattr(self, 'ambient_pressure_bar',
                              SEA_LEVEL_PRESSURE_BAR))
        durum = {
            'cf': 0.0, 'cf_ideal': 0.0, 'cf_attached_ideal': 0.0,
            'separated': False, 'separation_area_ratio': None,
            'pe_bar': 0.0, 'pe_over_pa': 0.0, 'choked': False,
            'status': 'no_flow',
            'criterion': (f'Summerfield: separation expected below '
                          f'Pe/Pa = {SUMMERFIELD_SEPARATION_RATIO:g}'),
        }
        if P_c_bar <= 0 or p_amb <= 0:
            return durum

        epsilon = float(self._estimate_expansion_ratio())
        pe_ratio = float(self._exit_pressure_ratio(epsilon))
        pe_bar = pe_ratio * P_c_bar
        durum['pe_bar'] = float(pe_bar)
        durum['pe_over_pa'] = float(pe_bar / p_amb)

        _cf_momentum = self._cf_momentum_term

        # Boğulma: P* = Pc·(2/(γ+1))^(γ/(γ−1)) ≥ P_a olmalı.
        sonik_oran = (2 / (gamma + 1)) ** (gamma / (gamma - 1))
        durum['choked'] = bool(P_c_bar * sonik_oran >= p_amb)

        # Ekli (tek boyutlu) çözüm — teşhis için her hâlde raporlanır.
        cf_ekli = _cf_momentum(pe_ratio) + epsilon * (pe_ratio
                                                      - p_amb / P_c_bar)
        durum['cf_attached_ideal'] = float(cf_ekli)

        if not durum['choked']:
            durum['status'] = 'not_choked'
            return durum

        ayrilma_oran = SUMMERFIELD_SEPARATION_RATIO * p_amb / P_c_bar
        durum['separated'] = bool(pe_ratio < ayrilma_oran)

        if durum['separated']:
            # Ayrılma yalnız süpersonik (ıraksak) bölümde olabilir: ayrılma
            # basınç oranı sonik oranın üstüne çıkamaz.
            oran_ayr = float(min(ayrilma_oran, sonik_oran))
            eps_ayr = float(self._expansion_ratio_from_pressure_ratio(oran_ayr))
            eps_ayr = float(min(max(eps_ayr, 1.0), epsilon))
            cf_ideal = (_cf_momentum(oran_ayr)
                        + eps_ayr * (oran_ayr - p_amb / P_c_bar))
            durum['separation_area_ratio'] = eps_ayr
            durum['status'] = 'separated'
        else:
            cf_ideal = cf_ekli
            durum['status'] = 'attached'

        # Sayısal taban. Kesilmiş-lüle modeli boğulmuş akışta pozitif CF verir
        # (ölçüldü: bu deponun bütün grain tiplerinde ve 1-40 bar aralığında
        # min CF ≈ 1,0); bu satır fiziksel bir kırpma DEĞİL, yalnız sayısal
        # bir taşma korumasıdır ve devreye girerse SESSİZ kalmaz.
        if cf_ideal < 0.0:
            durum['cf_floor_applied'] = True
            durum['cf_ideal_raw'] = float(cf_ideal)
            cf_ideal = 0.0

        durum['cf_ideal'] = float(cf_ideal)
        durum['cf'] = float(cf_ideal * self._total_nozzle_efficiency())
        return durum

    def _flow_separation_state(self, P_c_bar):
        """Summerfield ayrılma ölçütü durumu (rapor + uyarı için).

        P_e ≲ 0.4·P_a olduğunda aşırı genişlemiş konik nozulda akış ayrılması
        beklenir. v2.6.27 (A1-2): ayrılma artık yalnız RAPORLANMAZ, itki
        katsayısını da kesilmiş-lüle modeliyle DEĞİŞTİRİR; bu yüzden durum
        ayrı bir yerde yeniden hesaplanmaz, CF'in hesabından okunur (tek
        tanım noktası). Kaynak: Sutton & Biblarz 9. baskı, Böl. 3 ve 5.
        """
        durum = self._thrust_coefficient_state(P_c_bar)
        return {
            'separated': bool(durum['separated']),
            'pe_bar': float(durum['pe_bar']),
            'pe_over_pa': float(durum['pe_over_pa']),
            'separation_area_ratio': durum['separation_area_ratio'],
            'choked': bool(durum['choked']),
            'criterion': durum['criterion'],
        }

    def _design_burn_rate(self):
        """Tasarım basıncındaki erozif-DÜZELTMESİZ yanma hızı (m/s).

        Erozif düzeltme port akısına bağlıdır, port ise henüz boyutlandırılmamış
        olduğu için tasarım noktası referans hızı akısız alınır; hedef sapması
        dış sabit-nokta döngüsünde kapatılır.
        """
        self.mass_flux = 0.0
        return float(self.burn_rate(self.P_c, self.temp_ref))

    @staticmethod
    def _json_skaler(raw):
        """JSON'a yazılabilir bir özet: skalerse kendisi, değilse tip adı."""
        if isinstance(raw, (bool, int, float, str)):
            if isinstance(raw, float) and not np.isfinite(raw):
                return repr(raw)
            if isinstance(raw, str) and len(raw) > 80:
                return raw[:80] + '...'
            return raw
        return type(raw).__name__

    def _design_target_axis(self, keys, lo, hi):
        """Bir tasarım hedefi ekseninin çözümü + ÇÖZÜMÜN KAYNAĞI.

        ÖH Z5S / S5 (P16B2-01, KRİTİK). Eski gövde yalnız DEĞERİ döndürüyordu
        ve çağıran, ``None``ın iki farklı anlamını ayırt edemiyordu:

          * alan HİÇ gönderilmedi (hedef yok — meşru),
          * alan gönderildi ama ``_override_val`` REDDETTİ (fiziksel olmayan
            sayı, bool, NaN, metin, bant dışı).

        İkisi aynı sayıldığı için ikinci durumda hedef, ölçülen taban
        eğrisiyle SESSİZCE dolduruluyor ve o uydurulmuş sayı yanıtta
        ``requested_average_thrust_N`` diye yayımlanıyordu (ölçüldü:
        ``thrust`` ∈ {0, -100, 1e9, inf, NaN, True, 'peynir'} — altısında da
        HTTP 200, ``requested = 3063,784907572051 N``, ``achieved = True``).

        Anahtar ÖNCELİĞİ birebir korunur (``target_thrust`` > ``thrust``):
        ilk ÇÖZÜLEN anahtar kazanır; hiçbiri çözülmediyse ilk GÖNDERİLMİŞ
        anahtar reddin künyesini taşır.

        Returns:
            ``{'value', 'source', 'key', 'submitted'}``; ``source`` ∈
            {``'request'``, ``'rejected'``, ``'not_supplied'``}.
        """
        reddedilen = None
        for key in keys:
            raw = self.overrides.get(key)
            if raw is None or raw == '':
                continue
            value = self._override_val(key, lo, hi)
            if value is not None:
                return {'value': value, 'source': 'request', 'key': key,
                        'submitted': self._json_skaler(raw)}
            if reddedilen is None:
                reddedilen = {'value': None, 'source': 'rejected',
                              'key': key, 'submitted': self._json_skaler(raw),
                              'accepted_range': [float(lo), float(hi)]}
        if reddedilen is not None:
            return reddedilen
        return {'value': None, 'source': 'not_supplied', 'key': None,
                'submitted': None}

    def _design_point_targets(self):
        """(hedef ortalama itki N, hedef yanma süresi s) — verilmeyen None."""
        itki, sure = self._design_target_axes()
        return itki['value'], sure['value']

    def _design_target_axes(self):
        """(itki ekseni, süre ekseni) — her biri _design_target_axis künyesi."""
        lim = SOLID_DESIGN_POINT
        return (
            self._design_target_axis(
                ('target_thrust', 'thrust'),
                lim['min_target_thrust'], lim['max_target_thrust']),
            self._design_target_axis(
                ('target_burn_time', 'burn_time'),
                lim['min_target_burn_time'], lim['max_target_burn_time']),
        )

    def _measure_curve(self):
        """(ortalama itki N, yanma süresi s, TEPE itki N) — geçersizde sıfır.

        ÖH D22 (defter P12bB2-09): tepe değeri buraya EKLENDİ. Sebebi
        ``_solve_design_point``ın künyesinde: tasarım hedefi bir ORTALAMA
        itkidir, tepe itki ise tane ailesine göre onun 1,0-3,9 katıdır ve
        boyutlandırma çevrimi bugüne kadar tepeyi hiç okumuyordu. Tepe,
        çevrimin ZATEN hesapladığı eğriden alınır (``np.max``, yayımlanan
        ``max_thrust`` ile AYNI tanım) — fazladan bir eğri koşumu YOKTUR.
        """
        curve = self.calculate_thrust_curve()
        if len(curve['time']) == 0:
            return 0.0, 0.0, 0.0
        return (float(np.mean(curve['thrust'])), float(curve['time'][-1]),
                float(np.max(curve['thrust'])))

    def _bates_geometry_for(self, thrust, burn_time, locked_segments=None,
                            detay=None, kapi=True):
        """Hedefi tutturan BATES geometrisi (orta-web nötr aile) veya None.

        ``kapi=False`` yalnız boyutlandırma döngüsünün KEŞİF adımı içindir
        (V301/K-D): kapıdan geçen aday yoksa döngü etkin hedefi düzeltmek
        için eski seçimi (kapı sınanmadan) ölçer; o geometri SONUÇ olamaz.

        ``detay`` sözlüğü verilirse çözümsüzlüğün NEDENİ yazılır
        (``geometric_candidates``: boyut sınırlarından geçen aday sayısı,
        ``port_rejected``: port kapısına takılan aday sayısı,
        ``best_port_to_throat``: sınanan adayların en büyük kapı oranı). Zarf
        notu çözümsüzlüğün port kapısından mı, boyut sınırlarından mı
        geldiğini bu sayılardan söyler (V301/K-D).

        Zincir (Sutton & Biblarz Böl. 12):
          mdot = F/(CF·c*)          — boğulmuş akış + itki katsayısı
          A_t  = F/(CF·Pc)          — boğaz tasarım noktasında
          W    = r(Pc)·t_b          — radyal web yanma süresini belirler
          V    = mdot·t_b/rho_p     — toplam yakıt hacmi toplam impulsu belirler
        Aile: L_seg = 4·r_c + 3·W  →  A(0) = A(W), tepe orta-webte.
        Bu ailede yığın hacmi kapalı formda
          V = 2π·n·W·(4r_c² + 5r_c·W + 1.5W²)
        olduğundan r_c ikinci derece denklemden çözülür. Sağ taraf
        1.5W²'nin altına düşerse (yani hedef hacim, o web kalınlığındaki
        en küçük BATES yığınından bile küçükse) çözüm YOKTUR.
        """
        lim = SOLID_DESIGN_POINT
        if detay is not None:
            detay.update(geometric_candidates=0, port_rejected=0,
                         best_port_to_throat=None)
        r_design = self._design_burn_rate()
        if r_design <= 0 or thrust <= 0 or burn_time <= 0:
            return None
        CF = self._thrust_coefficient(self.P_c)
        m_dot = thrust / (CF * self.c_star)          # kg/s
        A_t = thrust / (CF * self.P_c * 1e5)         # m²
        W = r_design * burn_time                     # m, radyal web
        V = m_dot * burn_time / self.rho_p           # m³, yakıt hacmi

        if locked_segments is not None:
            candidates = [int(locked_segments)]
        else:
            candidates = list(range(1, lim['max_segments'] + 1))

        c_core = lim['bates_core_factor']
        c_web = lim['bates_web_factor']
        feasible = []
        for n_seg in candidates:
            if n_seg < 1:
                continue
            # V = 2π n W (4r_c² + 5 r_c W + 1.5 W²)  →  Q = V/(2π n W)
            Q = V / (2 * np.pi * n_seg * W)
            disc = W ** 2 + 16 * Q          # 25W² - 16(1.5W² - Q)
            if disc < 0:
                continue
            r_core = (-5 * W + np.sqrt(disc)) / 8
            if r_core < lim['min_core_diameter'] / 2:
                continue
            L_seg = c_core * r_core + c_web * W
            L_total = n_seg * L_seg
            D_chamber = 2 * (r_core + W)
            if not (lim['min_chamber_diameter'] <= D_chamber
                    <= lim['max_chamber_diameter']):
                continue
            if not (lim['min_grain_length'] <= L_total
                    <= lim['max_grain_length']):
                continue
            port_ratio = np.pi * r_core ** 2 / A_t if A_t > 0 else 0.0
            slenderness = L_total / D_chamber
            feasible.append({
                'grain_type': 'bates', 'n_segments': n_seg,
                'D_chamber': D_chamber, 'D_core': 2 * r_core,
                'L_grain': L_total, 'segment_length': L_seg,
                'web': W, 'throat_area': A_t, 'port_to_throat': port_ratio,
                'propellant_mass': m_dot * burn_time,
                'slenderness': slenderness,
            })

        if detay is not None:
            detay['geometric_candidates'] = len(feasible)
        if not feasible:
            return None
        if not kapi:
            # Keşif: eski seçim kuralı aynen (ilk dolu kademe, inceltme).
            kademe = ([g for g in feasible if g['port_to_throat']
                       >= lim['port_to_throat_target']]
                      or [g for g in feasible if g['port_to_throat']
                          >= lim['port_to_throat_min']]
                      or feasible)
            return min(kademe, key=lambda g: abs(g['slenderness']
                                                 - lim['target_slenderness']))
        # V301/K-D (T-çapa-A DEVİR 2 + T-çapa-B DEVİR 1): PORT ⟷ BOĞAZ
        # KAPISI BOYUTLANDIRMANIN KISITIDIR. Eski seçim yukarıdaki kapalı
        # form oranını (A_t = F/(CF·Pc), ortalama itkinin boğazı) yalnız
        # TERCİH için okuyordu; ≥ 2 aday yoksa "uygun olan herhangi biri"
        # seçiliyordu. Ölçüldü (taban 2facae6a0, Ø100/35/300 BATES, APCP,
        # 40 bar, 3 s): 300 N -> çekirdek 6,76 mm, kapı oranı 0,655 ->
        # boyutlandırıcının ürettiği tasarımı motorun kendi port kapısı
        # (``_check_port_throat``) 422 ile reddediyordu. Zarf da aynı
        # çözücüye sorulduğu için duyurduğu sınır (287,50 N) çözülemiyordu.
        #
        # Artık her aday kapının KENDİ ölçütüyle (``_port_throat_areas``:
        # A_port,0 > A_t; yayımlanan geometrik boğaz, çözücünün boğaz
        # boyutlandırması) sınanır; geçemeyen aday seçilmez. Zarf ikiye
        # bölmesi bu fonksiyona sorduğu için duyurduğu sınır kapıyla aynı
        # sayıdır (tek kaynak). Tercih kademeleri (≥ 4, ≥ 2) ve inceltme
        # ölçütü DEĞİŞMEDİ, yalnız kapıdan geçemeyen aday atlanır: eski
        # seçim kapıdan geçiyorsa ilk sınanan aday odur -> geometri
        # bit-aynı.
        kademeler = (
            [g for g in feasible
             if g['port_to_throat'] >= lim['port_to_throat_target']],
            [g for g in feasible
             if g['port_to_throat'] >= lim['port_to_throat_min']],
            feasible,
        )
        denenen = set()
        for kademe in kademeler:
            for g in sorted(kademe,
                            key=lambda g: abs(g['slenderness']
                                              - lim['target_slenderness'])):
                if id(g) in denenen:
                    continue
                denenen.add(id(g))
                alanlar = self._candidate_port_throat_areas(g)
                oran = (alanlar[0] / alanlar[1]
                        if alanlar is not None else None)
                if detay is not None and oran is not None and (
                        detay['best_port_to_throat'] is None
                        or oran > detay['best_port_to_throat']):
                    detay['best_port_to_throat'] = float(oran)
                if alanlar is None or not alanlar[0] > alanlar[1]:
                    if detay is not None:
                        detay['port_rejected'] += 1
                    continue
                # Yayımlanan oran kapının oranıdır, kapalı form tahmini
                # değil: kullanıcı bu sayıyı ekrandaki boğazla doğrular.
                g['port_to_throat'] = float(oran)
                return g
        return None

    def _candidate_port_throat_areas(self, geom):
        """Aday geometrinin port kapısı alanları — motorun durumu DEĞİŞMEZ.

        V301/K-D. Aday (``_bates_geometry_for`` sözlüğü) geçici olarak
        kurulur, ``_port_throat_areas`` (``_check_port_throat`` ile AYNI
        ölçüt) okunur, geometri ve segment anahtarı eski hâline döner.
        Geometri memoları ``_grain_geometry_key`` ile anahtarlıdır, bayat
        sonuç dönmez. Boğaz taraması yanma hızı tavanına dokunduysa
        ``_burn_rate_clipped_max`` kaydı da geri alınır: atılan bir adayın
        izi kullanıcı uyarısına sızmaz (``_equilibrium_pressure_fallback``
        deseni). Aday boğazı boyutlandırılamıyorsa ``None`` (fail-closed:
        boyutlandırıcı o adayı kabul etmez).
        """
        eski = (self.D_chamber, self.D_core, self.L_grain)
        seg_vardi = 'grain_count' in self.overrides
        seg_eski = self.overrides.get('grain_count')
        kirpma_vardi = '_burn_rate_clipped_max' in self.__dict__
        kirpma_eski = self.__dict__.get('_burn_rate_clipped_max')
        try:
            self._install_geometry(geom)
            return self._port_throat_areas()
        except SolidGeometryError:
            return None
        finally:
            self.D_chamber, self.D_core, self.L_grain = eski
            if seg_vardi:
                self.overrides['grain_count'] = seg_eski
            else:
                self.overrides.pop('grain_count', None)
            if kirpma_vardi:
                self._burn_rate_clipped_max = kirpma_eski
            else:
                self.__dict__.pop('_burn_rate_clipped_max', None)

    def _end_burner_geometry_for(self, thrust, burn_time):
        """Hedefi tutturan sigara-yanması geometrisi veya None.

        Yanan yüzey sabit (πR²) olduğundan çözüm kapalı formdadır ve profil
        doğal olarak nötrdür: A_b = mdot/(rho_p·r), L = r·t_b.
        """
        lim = SOLID_DESIGN_POINT
        r_design = self._design_burn_rate()
        if r_design <= 0 or thrust <= 0 or burn_time <= 0:
            return None
        CF = self._thrust_coefficient(self.P_c)
        m_dot = thrust / (CF * self.c_star)
        A_t = thrust / (CF * self.P_c * 1e5)
        A_burn = m_dot / (self.rho_p * r_design)
        D_chamber = 2 * np.sqrt(A_burn / np.pi)
        L_grain = r_design * burn_time
        if not (lim['min_chamber_diameter'] <= D_chamber
                <= lim['max_chamber_diameter']):
            return None
        if not (lim['min_grain_length'] <= L_grain
                <= lim['max_grain_length']):
            return None
        return {
            'grain_type': 'end_burner', 'n_segments': 1,
            'D_chamber': D_chamber,
            'D_core': lim['min_core_diameter'],
            'L_grain': L_grain, 'segment_length': L_grain,
            'web': L_grain, 'throat_area': A_t,
            'port_to_throat': A_burn / A_t if A_t > 0 else 0.0,
            'propellant_mass': m_dot * burn_time,
            'slenderness': L_grain / D_chamber,
        }

    def _install_geometry(self, geom):
        """Çözülen geometriyi motora uygular (segment sayısı dahil)."""
        self.D_chamber = geom['D_chamber']
        self.D_core = geom['D_core']
        self.L_grain = geom['L_grain']
        # Yanma alanı modeli ve grain_design raporu segment sayısını
        # _bates_segment_count üzerinden okur — TEK kaynak korunur.
        self.overrides['grain_count'] = geom['n_segments']

    def _bates_envelope_bounds(self, thrust, burn_time, locked_segments=None):
        """(ulaşılabilir en küçük itki, en uzun süre) — ÇÖZÜCÜYE sorularak.

        Kapalı-form zarf sınırı (r_core → 0) çözücünün kendi alt sınırlarını
        (en küçük çekirdek çapı, oda çapı / grain boyu aralığı) görmez, bu
        yüzden kullanıcıya duyurulamaz: duyurulan değer yine çözümsüz çıkar.
        Sınır doğrudan _bates_geometry_for üzerinde ikiye bölmeyle bulunur —
        böylece uyarıda yazan sayı gerçekten işe yarar.
        """
        def feasible(f_val, t_val):
            return self._bates_geometry_for(
                f_val, t_val, locked_segments) is not None

        # İtki tabanı: yukarı doğru tarama + ikiye bölme
        f_hi = max(thrust, 1.0)
        for _ in range(60):
            if feasible(f_hi, burn_time):
                break
            f_hi *= 1.5
        else:
            f_hi = float('nan')
        f_min = f_hi
        if np.isfinite(f_hi):
            f_lo = min(thrust, f_hi) / 1.5
            for _ in range(60):
                mid = 0.5 * (f_lo + f_hi)
                if feasible(mid, burn_time):
                    f_hi = mid
                else:
                    f_lo = mid
            f_min = f_hi

        # Süre tavanı: aşağı doğru tarama + ikiye bölme
        t_lo = burn_time
        for _ in range(60):
            if feasible(thrust, t_lo):
                break
            t_lo /= 1.5
        else:
            t_lo = float('nan')
        t_max = t_lo
        if np.isfinite(t_lo):
            t_hi = max(burn_time, t_lo)
            for _ in range(60):
                mid = 0.5 * (t_lo + t_hi)
                if feasible(thrust, mid):
                    t_lo = mid
                else:
                    t_hi = mid
            t_max = t_lo
        return f_min, t_max

    # --- ÖH D26 (defter P15B3-02) — ZARF SINIRININ ADI VE MİKTARI --------
    #: Zarf taramasının çarpanı ve adım sayısı. ``_bates_envelope_bounds``
    #: aynı sayıları kendi gövdesinde kullanır; yeni bir eşik TANIMLANMADI,
    #: var olan yöntemin sabitleri adlandırıldı (Doktrin 4).
    _ZARF_TARAMA_CARPANI = 1.5
    _ZARF_TARAMA_ADIMI = 60

    def _zarf_ekseni_siniri(self, feasible, x0):
        """Bir eksende ULAŞILABİLİR bölgenin sınırı ve sınırın TÜRÜ.

        ``feasible(x)`` o eksende ``x`` değerinin çözülebilir olup olmadığını
        söyler (öteki eksen isteğin kendi değerinde SABİT tutulur). ``x0``
        çözülemeyen istektir. Yöntem ``_bates_envelope_bounds`` ile aynıdır:
        önce çözülebilir bir çapa aranır (×1,5 yukarı, sonra ÷1,5 aşağı),
        ardından çapa ile ``x0`` arasında ikiye bölme. Böylece duyurulan sayı
        kapalı-form bir tahmin değil, ÇÖZÜCÜNÜN KENDİSİNE sorulmuş sınırdır.

        Returns:
            ``(sinir, tur)``; ``tur`` ∈ {``'minimum'``, ``'maximum'``} ve
            ``sinir`` ulaşılabilir tarafın ilk noktasıdır. Hiçbir yönde çözüm
            bulunamazsa ``(nan, None)`` döner — sayı UYDURULMAZ.
        """
        try:
            x0 = float(x0)
        except (TypeError, ValueError):
            return float('nan'), None
        if not np.isfinite(x0) or x0 <= 0:
            return float('nan'), None
        k = float(self._ZARF_TARAMA_CARPANI)
        for carpan, tur in ((k, 'minimum'), (1.0 / k, 'maximum')):
            capa = x0
            for _ in range(self._ZARF_TARAMA_ADIMI):
                capa *= carpan
                if not np.isfinite(capa) or capa <= 0:
                    break
                if not feasible(capa):
                    continue
                # Çapa çözülebilir, x0 değil: sınır ikisinin arasında.
                lo, hi = ((x0, capa) if tur == 'minimum' else (capa, x0))
                for _ in range(self._ZARF_TARAMA_ADIMI):
                    orta = 0.5 * (lo + hi)
                    cozulur = feasible(orta)
                    if tur == 'minimum':
                        hi, lo = (orta, lo) if cozulur else (hi, orta)
                    else:
                        lo, hi = (orta, hi) if cozulur else (lo, orta)
                return (float(hi) if tur == 'minimum' else float(lo)), tur
        return float('nan'), None

    def _end_burner_envelope_bounds(self, thrust, burn_time):
        """Uç-yanmalı ailede eksen sınırları — BATES ikizinin karşılığı.

        ``_bates_envelope_bounds`` yalnız BATES için ve yalnız TEK yönde
        (en küçük itki / en uzun süre) sınır veriyordu. Uç-yanmalı ailede
        çözüm iki yönden de düşebilir: ``_end_burner_geometry_for`` oda
        çapını itkiden (``D ∝ √F``), tane boyunu süreden (``L = r·t_b``)
        türetir ve ikisinin de kendi bandı vardır. Sınır, o yüzden her iki
        yönde de aranır (ölçüldü: 900 kN / 3 s isteği oda çapı bandını
        aşıyor ve taban ağacında 276,49 N / 36,93 s yayımlanıyordu).
        """
        def itki_uygun(f):
            return self._end_burner_geometry_for(f, burn_time) is not None

        def sure_uygun(t):
            return self._end_burner_geometry_for(thrust, t) is not None

        return (self._zarf_ekseni_siniri(itki_uygun, thrust),
                self._zarf_ekseni_siniri(sure_uygun, burn_time))

    @staticmethod
    def _zarf_asim_kalemleri(eksenler):
        """Zarfı AŞAN büyüklükler: hangisi, ne kadar (ölçülmüş).

        ``eksenler`` her biri ``(eksen künyesi, hedef, (sınır, tür), nicelik
        adı, birim)`` olan bir dizidir. Sınırı sonlu OLMAYAN ya da fiilen
        aşılmayan eksen listeye GİRMEZ — beyan varsayımla değil ölçümle
        üretilir (``_geometri_degisimi`` ile aynı ilke).
        """
        kalemler = []
        for eksen, hedef, sinir, nicelik, birim in eksenler:
            deger, tur = sinir
            try:
                hedef = float(hedef)
                deger = float(deger)
            except (TypeError, ValueError):
                continue
            if tur is None or not (np.isfinite(deger) and np.isfinite(hedef)):
                continue
            asim = (deger - hedef) if tur == 'minimum' else (hedef - deger)
            if asim <= 0:
                continue
            kalemler.append({
                'field': eksen['key'],
                'field_source': eksen['source'],
                'quantity': nicelik,
                'unit': birim,
                'requested': hedef,
                'feasible_bound': deger,
                'bound_kind': tur,
                'exceeded_by': float(asim),
                'exceeded_by_pct': (100.0 * asim / deger) if deger else None,
            })
        return kalemler

    def _hedef_dusuruldu_kunyesi(self, reason, note, itki_ekseni, sure_ekseni,
                                 envelope=None, exceeded=(), **ek):
        """Hedefi DÜŞÜRÜLEN tasarım noktasının ortak künyesi (fail-closed).

        ÖH D26 (defter P15B3-02). Üç dal da (zarf / desteklenmeyen tane /
        geçersiz eğri) aynı YAPISAL durumu üretir: istek okundu, hedef kabul
        edildi, ama motor onu tutturamadı. Bu künyeyi gören uç hüküm
        yayımlamaz; beyanın kendisi çözüm değildir (Doktrin 1).
        """
        return {
            'status': DESIGN_POINT_STATUS_NOT_REACHED,
            'reason': reason,
            'requested_average_thrust_N': (
                float(itki_ekseni['value'])
                if itki_ekseni['source'] == 'request' else None),
            'requested_burn_time_s': (
                float(sure_ekseni['value'])
                if sure_ekseni['source'] == 'request' else None),
            'requested_fields': [e['key'] for e in (itki_ekseni, sure_ekseni)
                                 if e['source'] == 'request'],
            'achieved': False,
            'sizing_applied': False,
            'envelope': envelope,
            'exceeded': list(exceeded),
            'note': note,
            'verdict_withheld': True,
            'verdict_basis': (
                'A design-point target was accepted but the motor could not '
                'be sized to it. The thrust curve that would otherwise be '
                'published belongs to the STARTING geometry, not to the '
                'requested design, so it is not an answer to this request '
                'and no performance verdict is issued. exceeded names which '
                'quantity is outside the reachable envelope and by how '
                'much; design_warnings carries the actionable options.'),
            **ek,
        }

    def _bates_envelope_note(self, thrust, burn_time, locked_segments=None,
                             bounds=None, port_limited_ratio=None):
        """BATES ailesinin ulaşılamayan hedef için yapısal (dilsiz) açıklaması.

        Tek bir ``{code, params, severity}`` kaydı döner. Seçenek listesi
        koşullu olduğundan (alt itki / üst süre sınırı sonlu olmayabilir)
        ``params['options']`` içinde kendi kodlarıyla taşınır; frontend her
        seçeneği yerelleştirip birleştirir ve ``{options}`` yer tutucusuna
        yerleştirir. Metnin anlamı ve sayıları eski sürümle birebir aynıdır.

        V301/K-D: çözümsüzlüğü PORT KAPISI bağlıyorsa (boyut sınırlarından
        geçen her aday A_port,0 ≤ A_t; ``port_limited_ratio`` = sınanan
        adayların en büyük kapı oranı) eski metin YANLIŞ olurdu ("uç
        yüzeyler fazla yanma alanı üretiyor" bu durumda neden değildir).
        O durumda kod ``warn.solid.bates_envelope_port``tır ve seçenekler
        yalnız çözücünün kendisiyle doğrulanmış olanlardır (itki tabanı,
        süre tavanı — ikisi de kapıyı içeren ikiye bölmeden) ve uç-yanmalı
        tane (portu tam kesittir); yönü kapıya göre belirsiz olan basınç
        önerisi bu kodda verilmez.
        """
        r_design = self._design_burn_rate()
        # ÖH D26 (P15B3-02): sınırlar çağıran tarafından ZATEN hesaplandıysa
        # yeniden aranmaz — aynı ikiye bölme iki kez koşarsa hem bedel iki
        # katına çıkar hem de iki ayrı sayı "sınır" diye dolaşmaya başlar.
        f_min, t_max = (bounds if bounds is not None else
                        self._bates_envelope_bounds(
                            thrust, burn_time, locked_segments))
        # Duyurulan sayı yazdırma yuvarlamasından sonra da çözülebilir olmalı
        # (ikiye bölme sınırı tam sınırdan döner) → küçük emniyet payı.
        options = []
        if np.isfinite(f_min):
            options.append(_w('warn.solid.opt_raise_thrust', 'info',
                              min_average_thrust_N=round(f_min * 1.01)))
        if np.isfinite(t_max):
            options.append(_w('warn.solid.opt_shorten_burn', 'info',
                              max_burn_time_s=round(t_max * 0.99, 2)))
        if port_limited_ratio is not None:
            options.append(_w('warn.solid.opt_select_end_burner', 'info'))
            return _w('warn.solid.bates_envelope_port', 'warning',
                      chamber_pressure_bar=round(self.P_c, 1),
                      burn_rate_mm_s=round(r_design * 1000, 1),
                      burn_time_s=round(burn_time, 2),
                      web_mm=round(r_design * burn_time * 1000),
                      thrust_N=round(thrust),
                      # Aşağı yuvarlanır: oran ≤ 1 iken yazılan sayı 1'e
                      # yuvarlanıp "1'i aşmalı" cümlesiyle çelişmesin.
                      port_to_throat=float(np.floor(
                          float(port_limited_ratio) * 1000.0) / 1000.0),
                      options=options)
        options.append(_w('warn.solid.opt_lower_chamber_pressure', 'info'))
        options.append(_w('warn.solid.opt_select_end_burner', 'info'))
        return _w('warn.solid.bates_envelope', 'warning',
                  chamber_pressure_bar=round(self.P_c, 1),
                  burn_rate_mm_s=round(r_design * 1000, 1),
                  burn_time_s=round(burn_time, 2),
                  web_mm=round(r_design * burn_time * 1000),
                  thrust_N=round(thrust),
                  options=options)

    @staticmethod
    def _geometri_mm(geom):
        """``{D_chamber, D_core, L_grain}`` [m] sözlüğünü mm'ye çevirir."""
        return {
            'chamber_diameter_mm': float(geom['D_chamber']) * 1000.0,
            'core_diameter_mm': float(geom['D_core']) * 1000.0,
            'grain_length_mm': float(geom['L_grain']) * 1000.0,
        }

    @staticmethod
    def _geometri_degisimi(once, sonra):
        """Boyutlandırmanın FİİLEN değiştirdiği geometri alanları (ölçülmüş).

        ÖH Z5S / S5 (P16B2-02). Beyan varsayımla değil ölçümle üretilir:
        girilen ölçü ile yayımlanan ölçü karşılaştırılır, eşitse hiçbir şey
        beyan edilmez (yanlış alarm da bir yalandır — ``inputs_not_used``
        ile aynı ilke).
        """
        adlar = {'D_chamber': 'chamber_diameter_mm',
                 'D_core': 'core_diameter_mm',
                 'L_grain': 'grain_length_mm'}
        degisen = []
        for anahtar, ad in adlar.items():
            try:
                a = float(once[anahtar])
                b = float(sonra[anahtar])
            except (TypeError, ValueError, KeyError):
                continue
            if not (np.isfinite(a) and np.isfinite(b)):
                continue
            if abs(a - b) <= 1e-9 * max(abs(a), abs(b), 1e-12):
                continue
            degisen.append({'field': ad,
                            'given_mm': a * 1000.0,
                            'used_mm': b * 1000.0})
        return degisen

    def _apply_design_point_sizing(self):
        """Hedef ortalama itki / yanma süresi verildiyse grain'i boyutlandırır.

        Hedef verilmediyse HİÇBİR ŞEY yapmaz — geometri girdisi tek belirleyici
        kalır (mevcut kullanıcı arayüzü ve korelasyon doğrulama yolu bu daldan
        geçer, sayısal davranışları değişmez).

        Dış döngü gereklidir: kapalı-form boyutlandırma sabit basınç varsayar,
        gerçek eğride basınç web boyunca değişir (erozif yanma, alan profili),
        bu yüzden ulaşılan ortalama itki ve süre hedeften kayar. Hedef/ulaşılan
        oranıyla ölçekleyen sabit-nokta bu kaymayı kapatır.
        """
        lim = SOLID_DESIGN_POINT
        itki_ekseni, sure_ekseni = self._design_target_axes()
        thrust_target = itki_ekseni['value']
        time_target = sure_ekseni['value']

        # ÖH Z5S / S5 (P16B2-01, KRİTİK) — HEDEF UYDURULMAZ. Gönderilmiş ama
        # çözülemeyen bir hedef varsa boyutlandırma KOŞMAZ ve hüküm
        # verilmez: eskiden reddedilen hedef ölçülen taban eğrisiyle
        # doldurulup o sayı "requested" diye yayımlanıyordu.
        reddedilenler = [e for e in (itki_ekseni, sure_ekseni)
                         if e['source'] == 'rejected']
        if reddedilenler:
            self.design_point = {
                'status': 'target_not_resolved',
                'requested_average_thrust_N': None,
                'requested_burn_time_s': None,
                'thrust_target_source': itki_ekseni['source'],
                'burn_time_target_source': sure_ekseni['source'],
                'rejected_targets': [
                    {'field': e['key'], 'submitted': e['submitted'],
                     'accepted_range': e.get('accepted_range')}
                    for e in reddedilenler],
                'achieved': None,
                'sizing_applied': False,
                'note': (
                    'A design-point target was supplied but could not be '
                    'read as a physical value, so no sizing was attempted '
                    'and no design point is reported. The geometry below is '
                    'the geometry that was given to the solver; it was NOT '
                    'sized to any target. See rejected_inputs for the '
                    'reason each field was refused.'),
            }
            return

        if thrust_target is None and time_target is None:
            return

        if self.grain_type not in ('bates', 'end_burner'):
            note = _w('warn.solid.sizing_unsupported_grain', 'warning',
                      grain_type=self.grain_type)
            self.design_warnings.append(note)
            # ÖH D26 (defter P15B3-02): burada hedef DÜŞÜYOR ve eski gövde
            # ``design_point``ı hiç kurmuyordu — yanıt, hedefin okunup
            # atıldığını YAPISAL olarak söylemiyordu. Ölçüldü (taban
            # 7751531): star / finocyl / slotted / wagon_wheel ailelerinde
            # 20 N ve 250 N isteklerinin yanıtları BAYT BAYT aynı geliyordu.
            self.design_point = self._hedef_dusuruldu_kunyesi(
                DESIGN_POINT_REASON_UNSUPPORTED_GRAIN, note,
                itki_ekseni, sure_ekseni,
                envelope={'grain_family': self.grain_type,
                          'sizing_supported_families': ['bates',
                                                        'end_burner']})
            return

        # Eksik hedef, girilen geometrinin kendi değeriyle tamamlanır:
        # "bu motoru koru, yalnız diğer hedefi tuttur".
        base_thrust, base_time, _base_peak = self._measure_curve()
        if base_thrust <= 0 or base_time <= 0:
            note = _w('warn.solid.sizing_invalid_curve', 'warning')
            self.design_warnings.append(note)
            # ÖH D26 (P15B3-02): bu dalda da hedef düşüyor; durum yapısal
            # olarak bildirilir (uyarı metni ayrıştırılmaz).
            self.design_point = self._hedef_dusuruldu_kunyesi(
                DESIGN_POINT_REASON_INVALID_CURVE, note,
                itki_ekseni, sure_ekseni,
                envelope={'grain_family': self.grain_type,
                          'input_geometry_average_thrust_N': float(
                              base_thrust),
                          'input_geometry_burn_time_s': float(base_time)})
            return
        if thrust_target is None:
            thrust_target = base_thrust
        if time_target is None:
            time_target = base_time

        # ÖH Z5S / S5 (P16B2-01): "istenen" ile "ölçülen" ayrı adreslerde.
        # ``requested_*`` YALNIZ istekten gelen hedefi taşır; eksik eksen
        # girilen geometrinin ÖLÇÜLEN eğrisinden tamamlanır ve o sayı
        # ``*_target_*`` alanlarında kaynağıyla birlikte yayımlanır.
        def _istenen(eksen, deger):
            return float(deger) if eksen['source'] == 'request' else None

        istenen_itki = _istenen(itki_ekseni, thrust_target)
        istenen_sure = _istenen(sure_ekseni, time_target)
        hedef_kunyesi = {
            'thrust_target_N': float(thrust_target),
            'burn_time_target_s': float(time_target),
            'thrust_target_source': (
                'request' if itki_ekseni['source'] == 'request'
                else 'measured_from_input_geometry'),
            'burn_time_target_source': (
                'request' if sure_ekseni['source'] == 'request'
                else 'measured_from_input_geometry'),
            'target_basis': (
                "A target marked 'request' came from the request body. "
                "'measured_from_input_geometry' means that axis was NOT "
                'requested: the value was measured from the thrust curve of '
                'the geometry that was given, so the sizing loop could hold '
                'that quantity while matching the other one. Such a value is '
                'not a user request and is reported as null in the '
                'requested_* fields.'),
        }

        geom_0 = dict(D_chamber=self.D_chamber, D_core=self.D_core,
                      L_grain=self.L_grain)
        user_segments = self._user_segment_count()
        locked_segments = (user_segments
                           if user_segments is not None
                           and self.grain_type == 'bates' else None)

        solver = (self._bates_geometry_for if self.grain_type == 'bates'
                  else lambda f, t, n=None: self._end_burner_geometry_for(f, t))

        thrust_eff, time_eff = thrust_target, time_target
        best = None
        for _ in range(lim['max_iterations']):
            geom = solver(thrust_eff, time_eff, locked_segments)
            # V301/K-D: port kapısı SONUCUN kısıtıdır, keşfin değil. Kapalı
            # form etkin hedefi ölçülen eğriyle düzeltir; ilk turdaki aday
            # kapıdan geçmese de düzeltilmiş hedefte geçen tasarım vardır.
            # Ölçüldü (D32 gövdesi, double_base 5000 N / 5 s): 1. tur çekirdek
            # 29,55 mm (kapı oranı 0,93), 2. tur (5840,2 N, 4,369 s) çekirdek
            # 51,33 mm (oran 2,48) — eski döngü buraya ulaşıyordu; ilk turda
            # durmak yanlış bir zarf reddi üretirdi. Kapıdan geçen aday yoksa
            # tur yalnız KEŞİF olarak ölçülür (eski seçim), sonuç olamaz.
            uygun = geom is not None
            if geom is None and self.grain_type == 'bates':
                geom = self._bates_geometry_for(thrust_eff, time_eff,
                                                locked_segments, kapi=False)
            if geom is None:
                break
            self._install_geometry(geom)
            thrust_avg, burn_time, thrust_peak = self._measure_curve()
            if thrust_avg <= 0 or burn_time <= 0:
                break
            err = max(abs(thrust_avg / thrust_target - 1.0),
                      abs(burn_time / time_target - 1.0))
            if uygun and (best is None or err < best[0]):
                best = (err, geom, thrust_avg, burn_time, thrust_peak)
            if err <= lim['tolerance']:
                break
            step = lim['max_step_ratio']
            relax = lim['relaxation']
            thrust_eff *= float(np.clip(
                (thrust_target / thrust_avg) ** relax, 1.0 / step, step))
            time_eff *= float(np.clip(
                (time_target / burn_time) ** relax, 1.0 / step, step))

        if best is None:
            # Hedef bu grain ailesiyle ulaşılamıyor: geometri girdisine DÖN,
            # sayıyı sessizce zorlama, nedeni açıkça bildir.
            self.D_chamber = geom_0['D_chamber']
            self.D_core = geom_0['D_core']
            self.L_grain = geom_0['L_grain']
            if user_segments is None:
                self.overrides.pop('grain_count', None)
            # ÖH D26 (defter P15B3-02): zarf sınırları BİR KEZ bulunur;
            # hem kullanıcıya duyurulan seçenekler hem de aşım raporu aynı
            # sayıdan türer (Doktrin 4 — tek kaynak).
            if self.grain_type == 'bates':
                _f_min, _t_max = self._bates_envelope_bounds(
                    thrust_target, time_target, locked_segments)
                # ``_bates_envelope_bounds`` yalnız TEK yönü arar (en küçük
                # itki / en uzun süre). Aşım öteki yöndeyse (istenen itki
                # zarfın ÜSTÜNDE) sınır ``nan`` döner; o eksende genel
                # tarayıcı kullanılır — sayı yine çözücüye sorulur.
                _itki_siniri = ((_f_min, 'minimum') if np.isfinite(_f_min)
                                else self._zarf_ekseni_siniri(
                                    lambda f: self._bates_geometry_for(
                                        f, time_target, locked_segments)
                                    is not None, thrust_target))
                _sure_siniri = ((_t_max, 'maximum') if np.isfinite(_t_max)
                                else self._zarf_ekseni_siniri(
                                    lambda t: self._bates_geometry_for(
                                        thrust_target, t, locked_segments)
                                    is not None, time_target))
                _zarf_sebebi = DESIGN_POINT_REASON_BATES_ENVELOPE
                # V301/K-D: çözümsüzlüğü bağlayan kısıt ADIYLA. İstenen
                # noktada boyut sınırlarından geçen aday varsa ve hepsi
                # port kapısına takıldıysa bağlayan kısıt kapıdır.
                _neden = {}
                self._bates_geometry_for(thrust_target, time_target,
                                         locked_segments, detay=_neden)
                _port_bagli = (
                    _neden.get('geometric_candidates', 0) > 0
                    and _neden.get('port_rejected', 0)
                    == _neden.get('geometric_candidates', 0)
                    and _neden.get('best_port_to_throat') is not None)
                note = self._bates_envelope_note(
                    thrust_target, time_target, locked_segments,
                    bounds=(_f_min, _t_max),
                    port_limited_ratio=(_neden['best_port_to_throat']
                                        if _port_bagli else None))
            else:
                _neden = {}
                _port_bagli = False
                _itki_siniri, _sure_siniri = self._end_burner_envelope_bounds(
                    thrust_target, time_target)
                _zarf_sebebi = DESIGN_POINT_REASON_END_BURNER_ENVELOPE
                note = _w('warn.solid.end_burner_envelope', 'warning')
            _asimlar = self._zarf_asim_kalemleri((
                (itki_ekseni, thrust_target, _itki_siniri,
                 'average_thrust', 'N'),
                (sure_ekseni, time_target, _sure_siniri, 'burn_time', 's'),
            ))
            _zarf = {
                'grain_family': self.grain_type,
                'chamber_pressure_bar': float(self.P_c),
                'design_burn_rate_mm_s': float(
                    self._design_burn_rate() * 1000.0),
                'min_average_thrust_N': (
                    float(_itki_siniri[0])
                    if _itki_siniri[1] == 'minimum'
                    and np.isfinite(_itki_siniri[0]) else None),
                'max_average_thrust_N': (
                    float(_itki_siniri[0])
                    if _itki_siniri[1] == 'maximum'
                    and np.isfinite(_itki_siniri[0]) else None),
                'max_burn_time_s': (
                    float(_sure_siniri[0])
                    if _sure_siniri[1] == 'maximum'
                    and np.isfinite(_sure_siniri[0]) else None),
                'min_burn_time_s': (
                    float(_sure_siniri[0])
                    if _sure_siniri[1] == 'minimum'
                    and np.isfinite(_sure_siniri[0]) else None),
                'bounds_basis': (
                    'Each bound is measured by bisecting the sizing solver '
                    'itself while the other axis is held at the requested '
                    'value, so it is reachable in practice and not a '
                    'closed-form estimate. The options in design_warnings '
                    'repeat the same bounds with a small rounding margin so '
                    'that the printed number still solves.'
                    + (' For the BATES family the sizing solver accepts a '
                       'grain only if its initial port flow area is larger '
                       'than the published throat area (the same port-to-'
                       'throat check that rejects a given geometry), so the '
                       'bounds already include that constraint.'
                       if self.grain_type == 'bates' else '')),
                # V301/K-D: çözümsüzlüğü bağlayan kısıt (yapısal, dilsiz).
                'binding_constraint': (
                    'port_to_throat' if _port_bagli else
                    ('grain_size_limits' if self.grain_type == 'bates'
                     and _neden.get('geometric_candidates') == 0
                     else None)),
                'best_candidate_port_to_throat_ratio': (
                    _neden.get('best_port_to_throat') if _port_bagli
                    else None),
            }
            self.design_warnings.append(note)
            self.design_point = self._hedef_dusuruldu_kunyesi(
                _zarf_sebebi, note, itki_ekseni, sure_ekseni,
                envelope=_zarf, exceeded=_asimlar,
                # ÖH Z5S / S5 (P16B2-03): boyutlandırma tutmadığında yayımlanan
                # geometrinin NEREDEN geldiği yazılır. Sayı değişmedi; eksik
                # olan tek şey bu geometrinin bir tasarım DEĞİL, çözücüye
                # verilen başlangıç geometrisi olduğunun söylenmesiydi.
                published_geometry_source='unchanged_input_geometry',
                published_geometry_mm=self._geometri_mm(geom_0),
                # Bu dalda geometri hiç değişmedi (geom_0'a geri dönüldü).
                geometry_replaced_by_sizing=False,
                **hedef_kunyesi,
            )
            return

        err, geom, thrust_avg, burn_time, thrust_peak = best
        self._install_geometry(geom)
        achieved = err <= lim['tolerance']
        boyutlanan = dict(D_chamber=self.D_chamber, D_core=self.D_core,
                          L_grain=self.L_grain)
        # ÖH Z5S / S5 (P16B2-02): boyutlandırma girilen geometriyi EZDİYSE
        # bu ölçülerek söylenir (Ø100 -> Ø417,93 mm sessizce oluyordu).
        degisen = self._geometri_degisimi(geom_0, boyutlanan)
        self.design_point = {
            'requested_average_thrust_N': istenen_itki,
            'requested_burn_time_s': istenen_sure,
            'achieved_average_thrust_N': thrust_avg,
            'achieved_burn_time_s': burn_time,
            # --- ÖH D22 (defter P12bB2-09, YÜKSEK): TEPE İTKİ ------------
            # Hedef bir ORTALAMADIR; motoru boyutlandıran kullanıcı ise
            # gövdeyi AZAMİ ivmeye göre tasarlar. Bu blok bugüne kadar
            # yalnız ortalamayı yayımlıyordu, oysa tepe/ortalama oranı tane
            # ailesine göre 1,00 ile 3,92 arasında değişiyor (ölçüldü,
            # once.json bölüm K1; aynı Ø100/500/30 mm gövdesi, 40 bar APCP):
            #   end_burner 1,000 · bates 1,472 · finocyl 1,493 ·
            #   star 2,074 · slotted 2,627 · wagon_wheel 3,922
            # yani "3000 N motor" isteyen kullanıcı wagon_wheel'de yaklaşık
            # 11,8 kN tepe alıyor ve tasarım noktası bunu söylemiyordu.
            # Sayı UYDURULMUŞ DEĞİLDİR: çevrimin kendi eğrisinin np.max'ı,
            # yayımlanan ``max_thrust`` ile aynı tanım.
            'achieved_peak_thrust_N': thrust_peak,
            'achieved_peak_to_average_ratio': (
                (thrust_peak / thrust_avg) if thrust_avg > 0 else None),
            'peak_thrust_basis': (
                'The design-point target is an AVERAGE thrust: the sizing '
                'loop matches mean(thrust) over the burn, not the maximum. '
                'achieved_peak_thrust_N is max(thrust) of the same solved '
                'curve (identical to the published max_thrust) and '
                'achieved_peak_to_average_ratio is their quotient. The ratio '
                'is set by the grain family, not by the target: neutral '
                'grains stay near 1, progressive ones (star, slotted, wagon '
                'wheel) run far above it. Size the airframe, the thrust '
                'structure and the maximum-acceleration case against the '
                'PEAK, not against the number you requested.'),
            'thrust_error_pct': 100.0 * (thrust_avg / thrust_target - 1.0),
            'burn_time_error_pct': 100.0 * (burn_time / time_target - 1.0),
            'achieved': bool(achieved),
            'sizing_applied': True,
            'segments': geom['n_segments'],
            'port_to_throat_ratio': geom['port_to_throat'],
            # V301/K-D: BATES'te bu oran port kapısının oranıdır (A_port,0 /
            # yayımlanan geometrik boğaz); eskiden kapalı form tahminiydi
            # (A_t = F/(CF·Pc)) ve aynı yanıttaki boğazla tutmuyordu.
            'port_to_throat_basis': (
                'initial port flow area / published (geometric) throat '
                'area of the sized grain - the same ratio the port-to-'
                'throat check uses; the sizing accepts only grains with a '
                'ratio above 1' if self.grain_type == 'bates' else
                'end burner: full grain cross-section / design throat area '
                '(closed form)'),
            'tolerance_pct': 100.0 * lim['tolerance'],
            'published_geometry_source': 'sized_to_design_point',
            'input_geometry_mm': self._geometri_mm(geom_0),
            'published_geometry_mm': self._geometri_mm(boyutlanan),
            'geometry_replaced_by_sizing': bool(degisen),
            'geometry_fields_replaced': degisen,
            **hedef_kunyesi,
        }
        if degisen:
            self.design_point['geometry_override_note'] = (
                'The design point sizing determined the grain geometry. Any '
                'chamber/grain/core dimension sent with this request was used '
                'only as the starting point of the sizing loop and was '
                'replaced; input_geometry_mm holds what was given, '
                'published_geometry_mm holds what the sizing produced.')
        if not achieved:
            self.design_warnings.append(_w(
                'warn.solid.sizing_off_target', 'warning',
                achieved_thrust_N=round(thrust_avg),
                achieved_burn_time_s=round(burn_time, 2),
                target_thrust_N=round(thrust_target),
                target_burn_time_s=round(time_target, 2),
                tolerance_pct=round(100.0 * lim['tolerance'])))
        if geom['port_to_throat'] < lim['port_to_throat_min']:
            self.design_warnings.append(_w(
                'warn.solid.sized_port_to_throat_low', 'warning',
                port_to_throat=round(geom['port_to_throat'], 2),
                limit=round(lim['port_to_throat_min'], 1)))

    def _design_health_warnings(self, curve):
        """Geometri girdisiyle koşulan motorlar için fiziksel akıl sağlığı.

        Tasarım noktası boyutlandırması kullanılmasa bile, port/boğaz oranı ve
        başlangıç port kütle akısı motorun yapılabilir olup olmadığını söyler.
        Sayıyı DEĞİŞTİRMEZ, yalnız kullanıcıyı uyarır.
        """
        lim = SOLID_DESIGN_POINT
        notes = []

        # --- Basınç çözücü sağlığı (Codex bulgusu, 2026-07-19) --------------
        # 'convergence_achieved' eskiden sabit True idi: yakınsamayan bir
        # basınç eğrisi başarılı gibi dönüyordu. Artık gerçek durum uyarıya
        # çevrilir. Ayrıca sabit-nokta daralması n < 1 varsayar; n >= 1'de
        # denge çözümü tekil/kararsızdır ve açıkça söylenmelidir.
        failed_steps = int(curve.get('pressure_solver_failed_steps', 0) or 0)
        total_steps = int(curve.get('pressure_solver_steps', 0) or 0)
        if failed_steps > 0:
            notes.append(_w(
                'warn.solid.pressure_solver_not_converged', 'warning',
                failed_steps=failed_steps, total_steps=total_steps,
                max_residual=float(
                    curve.get('pressure_solver_max_residual', 0.0)),
                tolerance=float(
                    curve.get('pressure_solver_tolerance', 0.0))))
        if self.n >= 1.0:
            notes.append(_w(
                'warn.solid.burn_rate_exponent_ge_one', 'critical',
                n=round(float(self.n), 3)))
        if curve.get('termination_reason') == 'safety_limit':
            notes.append(_w(
                'warn.solid.safety_limit_termination', 'critical'))

        # --- Boğaz gövdeyi aşıyor (ÖH D18 + D20 / P2B3-13) -----------------
        # D18 ÜRÜN yarısını kapattı: yakınsak bölüm ve toplam kontur boyu
        # artık yayımlanmıyor (None + *_status 'not_physical'). Ama kullanıcı
        # yüzünde HİÇBİR uyarı yoktu — ÖLÇÜLDÜ (once.json / P2B3-13; D=100,
        # L=3000, çekirdek 15, Pc=10 bar): boğaz 156,54 mm (gövdenin 1,565
        # katı), throat_exceeds_case=True, convergent_length=None, ve
        # yayımlanan uyarı kodları yalnız flow_separation /
        # initial_mass_flux_high / nozzle_material_over_temp /
        # nozzle_unchoked / port_to_throat_low. Yani panelde boy alanları
        # BOŞ çıkıyor ve boş olmalarının sebebi hiçbir yerde yazmıyordu.
        # ÖH D26 a2 (OH-D25-10): ölçüt TEK yerde (_throat_exceeds_case) ve
        # boğaz kelepçesiz tek kaynaktan okunur.
        try:
            _d_t = float(self._estimate_throat_diameter())
        except Exception:
            _d_t = float('nan')
        if self._throat_exceeds_case(_d_t):
            notes.append(_w(
                'warn.solid.throat_exceeds_case', 'critical',
                throat_diameter_mm=round(_d_t * 1000.0, 2),
                chamber_diameter_mm=round(float(self.D_chamber) * 1000.0, 2),
                ratio=round(_d_t / float(self.D_chamber), 3)))

        # --- Tasarım basıncı aşımı (A1-1, v2.6.27) -------------------------
        # Boğaz artık maksimum Kn'de boyutlandırıldığı için tepe basınç
        # tasarım değerini aşamaz; aşarsa bu bir SAPMADIR (sabitlenmiş boğaz,
        # boyutlandırılamayan geometri ya da tarama çözünürlüğünün yetmediği
        # bir tepe) ve sessiz kalmaz.
        basinclar = np.asarray(curve.get('pressure', []), dtype=float)
        if basinclar.size and self.P_c > 0:
            tepe = float(np.nanmax(basinclar))
            if tepe > self.P_c * (1.0 + SOLID_DESIGN_PRESSURE_TOLERANCE):
                notes.append(_w(
                    'warn.solid.pressure_exceeds_design', 'warning',
                    peak_bar=round(tepe, 2),
                    design_bar=round(float(self.P_c), 2),
                    exceed_percent=round(
                        (tepe / float(self.P_c) - 1.0) * 100.0, 1),
                    tolerance_percent=round(
                        SOLID_DESIGN_PRESSURE_TOLERANCE * 100.0, 1)))

        # --- Akış ayrılması (A1-2, v2.6.27) --------------------------------
        # Sıvı modül ayrılmayı uyarıyordu, katı sessizce itkiyi sıfıra
        # kırpıyordu. Artık ayrılma hem itkiye kesilmiş-lüle modeliyle girer
        # hem de kullanıcıya bildirilir: ayrılmış rejimde tek boyutlu ekli
        # akış bağıntısı geçerli değildir ve eğrinin o bölümü bir MODEL
        # tahminidir.
        sep = np.asarray(curve.get('separated', []), dtype=bool)
        if sep.size and bool(sep.any()):
            pe = np.asarray(curve.get('exit_pressure_bar', []), dtype=float)
            pe_min = float(np.nanmin(pe[sep])) if pe.size == sep.size else 0.0
            notes.append(_w(
                'warn.solid.flow_separation', 'warning',
                from_t_s=round(float(curve.get('separated_from_t') or 0.0), 3),
                fraction_percent=round(float(sep.mean()) * 100.0, 1),
                exit_pressure_min_bar=round(pe_min, 3),
                ambient_bar=round(float(getattr(
                    self, 'ambient_pressure_bar', SEA_LEVEL_PRESSURE_BAR)), 3),
                criterion_ratio=SUMMERFIELD_SEPARATION_RATIO))

        # --- Boğulma sınırının altına düşen kuyruk (A1-2) ------------------
        # Eğrinin bu bölümünde çözücünün boşalma yasası da CF bağıntısı da
        # geçerli değildir. Eskiden burası sessizce F = 0 görünüyordu; artık
        # sıfırın SEBEBİ söyleniyor (uydurma bir itki sayısı üretmek yerine).
        if float(curve.get('unchoked_fraction', 0.0) or 0.0) > 0.0:
            notes.append(_w(
                'warn.solid.nozzle_unchoked', 'warning',
                from_t_s=round(float(curve.get('unchoked_from_t') or 0.0), 3),
                fraction_percent=round(
                    float(curve.get('unchoked_fraction', 0.0)) * 100.0, 1),
                ambient_bar=round(float(getattr(
                    self, 'ambient_pressure_bar', SEA_LEVEL_PRESSURE_BAR)), 3)))

        notes.extend(self._throat_erosion_warnings(curve))

        A_t = curve.get('throat_area', 0.0)
        if not A_t or A_t <= 0 or len(curve['time']) == 0:
            return notes
        # ÖH D15 a3 (P2B2-05). Bu blok BAŞLANGIÇ port alanını KENDİSİ
        # kuruyordu (end_burner'da kasa kesiti, diğerlerinde pi*(D_core/2)^2),
        # oysa çözücü aynı büyüklüğü ``_port_flow_area`` ile tanımlıyor ve
        # poligon tiplerde GERÇEK kesiti kullanıyor. İki tanım aynı yanıtta
        # İKİ FARKLI kütle akısı yayımlıyordu; uyarı METNİ (ve >1400 kg/m2s
        # ateşleme kararı) şişmiş sayıdan okunuyordu. ÖLÇÜLDÜ (D_kasa = 100 mm,
        # D_çekirdek = 30 mm, L = 500 mm, APCP, 40 bar) — uyarı / çözücü:
        #   slotted      4280 / 2313,40  = 1,8501x
        #   star         1985 / 1039,53  = 1,9095x
        #   wagon_wheel  2750 / 1571,74  = 1,7497x
        #   bates        2649 / 2648,80  = 1,0001x  (iki yol zaten aynıydı)
        # Kesitin tek tanımı vardır; uyarı da onu okur. w = 0 başlangıç
        # webidir (uyarı BAŞLANGIÇ akısı hakkındadır).
        A_port = float(self._port_flow_area(0.0))
        if A_port <= 0:
            return notes
        port_ratio = A_port / A_t
        if port_ratio < lim['port_to_throat_min']:
            notes.append(_w(
                'warn.solid.port_to_throat_low', 'warning',
                port_to_throat=round(port_ratio, 2),
                limit=round(lim['port_to_throat_min'], 1)))
        G_0 = float(curve['mass_flow'][0]) / A_port
        if G_0 > lim['mass_flux_warn']:
            notes.append(_w(
                'warn.solid.initial_mass_flux_high', 'warning',
                mass_flux_kg_m2s=round(G_0),
                threshold_kg_m2s=round(lim['mass_flux_warn'])))
        return notes

    def _throat_erosion_warnings(self, curve):
        """Boğaz erozyonu uyarıları (F071).

        Üç durum:
          1. Erozyon açık ve alan artışı eşiği aşıyor  -> büyüklüğü bildir.
          2. Erozyon açık ama katsayı, seçilen nozul malzemesinin yayımlanmış
             bandının DIŞINDA -> katsayıyı sorgula (solid.html varsayılanı
             0.001 mm/s, grafit bandının ~150 katı altındadır).
          3. Erozyon KAPALI ama grafit modeli bu motorda eşiği aşan bir alan
             artışı öngörüyor -> rijit-boğaz varsayımının bu motor sınıfında
             geçerli olmadığını söyle (uzun yanma + küçük boğaz).
        """
        notes = []

        # --- Üssün geçerlilik aralığı (ÖH D30 · OH-D29-05/OH-D28-05) -------
        # D28/OH-D27-15 erozyon yasasının basınç üssünü künyesine bağladı ve
        # bu motorun künyenin ÖLÇTÜĞÜ aralığın dışında olup olmadığını
        # ``exponent_extrapolated`` alanıyla YAYIMLADI. Ama alan yalnız VERİ
        # idi: ölçüldü (once.json · K1, 40 bar sınıfı apcp/bates/grafit)
        # ``exponent_extrapolated = True`` yayımlanıyor, buna karşılık
        # yayımlanan uyarı kodları arasında karşılığı YOKTU (0 geçiş) ve
        # erozyon bloğunun hiçbir panel tüketicisi yok — kullanıcıya yalnız
        # ``warnings`` dizisi üzerinden ulaşılıyor. Yani uygulamanın kendi
        # BİLDİĞİ bir ekstrapolasyon kullanıcı yüzünde hiçbir yerde
        # görünmüyordu. Ölçüt yeniden yazılmaz: kararın tek tanım noktası
        # ``ThroatErosionModel.exponent_extrapolated``tır ve buraya
        # ``_nozzle_erosion_estimate`` üzerinden, yani kullanıcıya YAYIMLANAN
        # sayının ta kendisinden gelir. Üç değerlidir: atfı olmayan (kullanıcı)
        # üste None döner ve o durumda HÜKÜM VERİLMEZ — aralık bilinmiyorken
        # "ekstrapolasyon değil" demek sessiz varsayım olurdu.
        _ero_est = self._nozzle_erosion_estimate()
        if _ero_est.get('exponent_extrapolated') is True:
            _bant = _ero_est.get('exponent_valid_pc_bar') or [None, None]
            notes.append(dict(_w(
                'warn.solid.erosion_exponent_extrapolated', 'warning',
                chamber_pressure_bar=round(
                    float(_ero_est.get('chamber_pressure_bar') or 0.0), 2),
                valid_low_bar=round(float(_bant[0]), 1),
                valid_high_bar=round(float(_bant[1]), 1),
                exponent=round(float(_ero_est.get('exponent') or 0.0), 3),
                material=str(_ero_est.get('material'))),
                fallback=(
                    "The throat erosion law is EXTRAPOLATED at this chamber "
                    "pressure: its pressure exponent (n = {exponent}) is "
                    "attributed to a source that measured "
                    "{valid_low_bar}-{valid_high_bar} bar, while this motor "
                    "runs at {chamber_pressure_bar} bar. The erosion rate "
                    "published for {material} is therefore an extrapolation "
                    "of that law, not an interpolation within it, and "
                    "carries correspondingly larger uncertainty.")))

        ero = curve.get('throat_erosion') or {}
        times = curve.get('time')
        if times is None or len(times) == 0:
            return notes
        burn_time = float(times[-1])
        A_t0 = float(curve.get('throat_area', 0.0) or 0.0)
        if A_t0 <= 0 or burn_time <= 0:
            return notes
        thr = THROAT_EROSION_SIGNIFICANT_AREA_GROWTH

        if ero.get('enabled'):
            growth = float(ero.get('area_growth_fraction', 0.0))
            if growth > thr:
                notes.append(_w(
                    'warn.solid.throat_erosion_significant', 'warning',
                    area_growth_percent=round(growth * 100.0, 1),
                    throat_diameter_initial_mm=round(
                        float(ero.get('throat_diameter_initial_mm', 0.0)), 2),
                    throat_diameter_final_mm=round(
                        float(ero.get('throat_diameter_final_mm', 0.0)), 2),
                    threshold_percent=round(thr * 100.0, 1)))
            a_ref = self._throat_erosion_a_ref()
            ref = self._nozzle_erosion_reference()
            band = ref.a_ref_band_mm_s if ref else None
            if a_ref is not None and band and not (
                    band[0] <= a_ref <= band[1]):
                notes.append(_w(
                    'warn.solid.throat_erosion_coeff_off_band', 'warning',
                    a_ref_mm_s=a_ref,
                    band_low_mm_s=band[0], band_high_mm_s=band[1],
                    material=str(ref.material)))
            return notes

        # Erozyon kapalı: rijit boğaz varsayımının bu motorda ne kadar
        # ısırdığını AYNI ampirik modelle tahmin et (Thakre & Yang 2008).
        ref = self._nozzle_erosion_reference()
        if ref is None:
            return notes
        pressures = np.asarray(curve.get('pressure', []), dtype=float)
        p_mean = float(np.nanmean(pressures)) if pressures.size else self.P_c
        d_radius = ref.rate_mm_s(p_mean) / 1000.0 * burn_time  # m
        r0 = float(np.sqrt(A_t0 / np.pi))
        growth = ((r0 + d_radius) / r0) ** 2 - 1.0 if r0 > 0 else 0.0
        if growth > thr:
            notes.append(_w(
                'warn.solid.rigid_throat_assumption', 'warning',
                estimated_area_growth_percent=round(growth * 100.0, 1),
                erosion_rate_mm_s=round(ref.rate_mm_s(p_mean), 4),
                burn_time_s=round(burn_time, 2),
                throat_diameter_mm=round(2000.0 * r0, 2),
                material=str(ref.material),
                threshold_percent=round(thr * 100.0, 1)))
        return notes

    def _star_params(self):
        """Star geometrisi (N uç, uç derinliği m) — TEK tanım noktası.

        Yanma alanı modeli ve geometri raporu aynı değerleri kullanır.
        Uç derinliği web'i negatife düşürmesin diye fiziksel üst sınırla kırpılır.
        """
        _pts = self._override_val('star_points', 3, 12)
        # V301/K-B (K-A DEVİR 9): uç sayısı TAM SAYIDIR; 6,5 eskiden
        # sessizce 6'ya yuvarlanıyordu. Ret -> /calculate_solid 422.
        if _pts is not None and abs(float(_pts) - round(float(_pts))) > 1e-9:
            self._reject_input(
                'star_points', self.overrides.get('star_points'),
                'value {} is not a whole number of star points'.format(
                    round(float(_pts), 6)),
                code='not_a_whole_number', accepted_range=(3, 12))
        star_points = int(round(_pts)) if _pts is not None else 6
        _dep = self._override_val('star_radius', 2.0, 60.0)
        point_depth = (_dep / 1000.0) if _dep is not None else 0.015
        max_depth = 0.8 * max((self.D_chamber - self.D_core) / 2.0, 0.002)
        # V301/K-B (K-A DEVİR 8): fiziksel sınırı aşan derinlik artık
        # SESSİZCE KIRPILMAZ; alan reddedilir (uç 422, en büyük değerle).
        # Doğrudan motor kullanımı (MC/UQ) için kırpılmış değerle sürer ama
        # ret kaydı ``rejected_inputs``te durur.
        if _dep is not None and point_depth > max_depth + 1e-12:
            self._reject_input(
                'star_radius', self.overrides.get('star_radius'),
                'point depth {:g} mm exceeds the geometric limit {:.3f} mm '
                '(0.8 x web)'.format(_dep, max_depth * 1000.0),
                code='exceeds_geometric_limit',
                accepted_range=(2.0, round(max_depth * 1000.0, 3)))
        return star_points, min(point_depth, max_depth)

    def _star_input_report(self):
        """Star girdilerinin çözülme künyesi: (assumed_defaults, clipped).

        ÖH D15 a2 (P2B1-06). ``star_points`` ve ``star_radius`` CANLI
        alanlardır (ortalama itkiyi %12,71'e kadar oynatırlar) ama
        varsayılana düşüşleri ve fiziksel sınıra kırpılmaları GÖRÜNMÜYORDU —
        finocyl/slotted aileleri bunu ``assumed_defaults`` / ``clipped_inputs``
        ile zaten yayımlıyor, star yayımlamıyordu. ÖLÇÜLDÜ: girilen
        ``star_radius`` = 40 mm sessizce 28,00 mm'ye kırpılıyordu (0,8*web).
        """
        assumed, clipped = [], []
        if self._override_val('star_points', 3, 12) is None:
            assumed.append('star_points')
        _dep = self._override_val('star_radius', 2.0, 60.0)
        if _dep is None:
            assumed.append('star_radius')
        else:
            max_depth_mm = 1000.0 * 0.8 * max(
                (self.D_chamber - self.D_core) / 2.0, 0.002)
            if _dep > max_depth_mm + 1e-9:
                clipped.append('star_radius')
        return assumed, clipped

    def _star_port_polygon(self):
        """Başlangıç star port kesiti (shapely Polygon, metre, merkez orijin).

        Basit zikzak star: vadiler core yarıçapında (Ri = D_core/2), uçlar
        Ri + derinlikte; 2N köşe. Vadi filetoları ayrıca modellenmez — ofset
        (buffer) ilerledikçe köşeler fiziksel olarak zaten yuvarlanır.
        """
        # Kurulum _cached_star_polygon'da (modül önbelleği): itki eğrisi her
        # zaman adımında bu poligonu istiyor; aynı parametreler bit-aynı
        # poligonu verdiğinden yeniden kurmak yerine paylaşılır.
        n_pts, depth = self._star_params()
        return _cached_star_polygon(n_pts, self.D_core / 2.0, depth)

    def _wagon_params(self):
        """Wagon-wheel geometrisi — TEK tanım noktası (model + rapor + kapı).

        V301/K-B (KT-08). Dönüş: ``{'hole_count', 'hole_diameter_m',
        'pitch_diameter_m', 'assumed_defaults', 'basis'}``. Girdi alanları:
        ``wagon_hole_count`` (çevre delik sayısı, tam sayı),
        ``wagon_hole_diameter`` (mm, merkez + çevre deliklerin ortak çapı),
        ``wagon_pitch_diameter`` (mm, çevre delik merkezlerinin dairesi).
        Verilmeyen alan ``SOLID_WAGON_WHEEL_DEFAULTS`` ile doldurulur ve
        ``assumed_defaults`` ile beyan edilir. Geometri tutarsızsa (delikler
        kesişiyor ya da tane dışına taşıyor) alan ``rejected_inputs``e
        işlenir; ``/calculate_solid`` bunu 422'ye çevirir, künyede kabul
        edilen en büyük değer yazar.
        """
        cfg = SOLID_WAGON_WHEEL_DEFAULTS
        assumed = []
        n_lo, n_hi = cfg['hole_count_range']
        n = self._override_val('wagon_hole_count', n_lo, n_hi)
        if n is None:
            n = cfg['hole_count']
            assumed.append('wagon_hole_count')
        elif abs(float(n) - round(float(n))) > 1e-9:
            self._reject_input(
                'wagon_hole_count', self.overrides.get('wagon_hole_count'),
                'value {} is not a whole number of holes'.format(
                    round(float(n), 6)),
                code='not_a_whole_number', accepted_range=(n_lo, n_hi))
            n = cfg['hole_count']
        n = int(round(n))
        d_grain_mm = self.D_chamber * 1000.0
        # Yarıçaplar METRE olarak tutulur; varsayılan dal eski kurulumla
        # (D_core/4, D_chamber/4) aynı işlemle hesaplanır -> bit-aynı poligon.
        d_h = self._override_val('wagon_hole_diameter', 0.1, d_grain_mm)
        if d_h is None:
            r_hole_m = self.D_core * cfg['hole_diameter_over_core'] / 2.0
            assumed.append('wagon_hole_diameter')
            hole_field = 'core_diameter'
        else:
            r_hole_m = d_h / 2000.0
            hole_field = 'wagon_hole_diameter'
        d_p = self._override_val('wagon_pitch_diameter', 0.1, d_grain_mm)
        if d_p is None:
            r_pitch_m = (self.D_chamber * cfg['pitch_diameter_over_grain']
                         / 2.0)
            assumed.append('wagon_pitch_diameter')
        else:
            r_pitch_m = d_p / 2000.0
        d_h = r_hole_m * 2000.0
        d_p = r_pitch_m * 2000.0
        # Geometrik tutarlılık (yeni ayar sayısı yok: sınırlar dairelerin
        # kesişmeme koşullarıdır). r_h: delik yarıçapı, R_p: bölüm yarıçapı.
        r_h, r_p, r_g = d_h / 2.0, d_p / 2.0, d_grain_mm / 2.0
        # (1) çevre delik merkez delikle kesişmez: R_p > 2·r_h
        # (2) komşu çevre delikler kesişmez: 2·R_p·sin(π/N) > 2·r_h
        # (3) çevre delik tane dışına taşmaz: R_p + r_h < R_g
        d_max = min(r_p, 2.0 * r_p * np.sin(np.pi / n), 2.0 * (r_g - r_p))
        if d_h >= d_max:
            self._reject_input(
                hole_field, self.overrides.get(hole_field),
                'wagon wheel holes of {:.2f} mm diameter on a {:.2f} mm pitch '
                'circle ({} outer holes, {:.2f} mm grain) intersect each '
                'other or the grain outer surface; the largest hole diameter '
                'for this pitch circle is below {:.2f} mm'.format(
                    d_h, d_p, n, d_grain_mm, d_max),
                code='wagon_holes_intersect',
                accepted_range=(0.1, round(float(d_max), 3)))
        return {
            'hole_count': n,
            'hole_radius_m': r_hole_m,
            'pitch_radius_m': r_pitch_m,
            'hole_diameter_m': 2.0 * r_hole_m,
            'pitch_diameter_m': 2.0 * r_pitch_m,
            'assumed_defaults': assumed,
            'basis': (cfg['basis'] if assumed else 'user input'),
        }

    def _wagon_port_polygon(self):
        """Wagon-wheel port kesiti: merkez + N çevre delik (shapely, metre).

        V301/K-B (KT-08): geometri ``_wagon_params``tan (kullanıcı ya da
        beyanlı varsayılan). Varsayılanlar eski modelle bit-aynı: delik
        yarıçapı D_core/4, bölüm yarıçapı D_chamber/4, 6 çevre delik.
        """
        # Kurulum _cached_wagon_polygon'da (modül önbelleği): 7 buffer + 6
        # union'lık sabit kesit her zaman adımında yeniden kuruluyordu.
        wp = self._wagon_params()
        return _cached_wagon_polygon(wp['hole_radius_m'],
                                     wp['pitch_radius_m'],
                                     wp['hole_count'])

    # ------------------------------------------------------------------
    # Finocyl / slotted: radyal yuvalı port kesitleri (2026-07-19)
    # ------------------------------------------------------------------
    def _require_shapely(self, label):
        """Poligon ofseti şart olan grain tipleri için açık hata.

        Finocyl ve slotted kesitleri kapalı formda ofsetlenemez (yuvalar
        birleşince çevre süreksiz düşer). shapely yoksa yaklaşık bir sayı
        UYDURMAK yerine hata verilir; kullanıcı ya paketi kurar ya da
        kapalı-form desteklenen bir tip seçer.

        ÖH D16/kati (P2B2-13): star ve wagon_wheel de bu kapıya bağlandı.
        Onların kapalı-form 'yaklaşıklığı' vardı ama fizik-dışı sayı
        üretiyordu (Isp 1276 s) ve uyarısı yanıta girmiyordu. Kapalı-form
        modeli GERÇEKTEN olan tipler yalnız bates ve end_burner'dır.
        """
        if not SHAPELY_AVAILABLE:
            raise RuntimeError(
                f"The '{label}' grain requires the 'shapely' package for its "
                "polygon-offset burn-surface model. Install shapely, or pick "
                "a grain type with a closed-form model (bates, end_burner).")

    def _radial_slot_primitives(self, n_slots, width, depth):
        """Port kesitinin ilkel parçaları: (merkez port yarıçapı, [yuva quad]).

        Yuvalar merkezden (r=0) başlatılır ki port dairesiyle her koşulda
        birleşsinler; birleşim tek parça bir port kesiti verir.
        """
        # Kurulum _cached_slot_quads'ta (modül önbelleği): yuva dörtgenleri
        # web'den bağımsız sabitlerdir, her ofset çağrısında yeniden
        # kurulmaları gereksizdi.
        r_port = self.D_core / 2.0
        return r_port, _cached_slot_quads(r_port, n_slots, width, depth)

    def _radial_slot_offset(self, n_slots, width, depth, web_thickness):
        """Web kadar ofsetlenmiş radyal-yuvalı port kesiti (shapely, metre).

        Ofset İLKELLERE DAĞITILIR: Minkowski toplamı birleşim üzerinde
        dağıldığından (A ∪ B) ⊕ D = (A ⊕ D) ∪ (B ⊕ D) ve merkez portun
        ofseti kapalı formda (r + w yarıçaplı daire) alınabilir.

        Neden birleşik poligon tek seferde buffer'lanmıyor: GEOS, buffer
        mesafesiyle orantılı bir girdi sadeleştirmesi uygular; büyük web
        değerlerinde bu, ince yakıt ceplerini bir adımda yutup kütle
        kaçırıyordu. Ölçüm (finocyl varsayılanı, 4 kanatçık): tek-seferlik
        buffer ile ∫A dw yakıt hacminden %1.22 SAPIYOR ve w = 24.55 mm'de
        port alanı 8e-5 m² sıçrıyordu; dağıtılmış ofsette sapma %0.002.
        """
        r_port, quads = self._radial_slot_primitives(n_slots, width, depth)
        geom = _ShapelyPoint(0.0, 0.0).buffer(r_port + web_thickness,
                                              quad_segs=96)
        for quad in quads:
            geom = geom.union(quad.buffer(web_thickness, quad_segs=32)
                              if web_thickness > 0 else quad)
        return geom

    def _radial_slot_params(self, cfg, count_key, width_keys, depth_keys):
        """Yuva sayısı/genişliği/derinliği + hangi değerlerin VARSAYILAN olduğu.

        Dönüş: (n, width_m, depth_m, assumed) — assumed, kullanıcı girdisi
        bulunamadığı için varsayılana düşülen alan adlarının listesidir ve
        çıktıda 'assumed_defaults' olarak BEYAN EDİLİR (sessiz varsayım yok).
        Kırpma uygulanırsa da beyan edilir ('clipped' listesi).
        """
        assumed, clipped = [], []
        c_lo, c_hi = cfg['count_range']
        n = self._override_val(count_key, c_lo, c_hi)
        if n is None:
            n = cfg[count_key]
            assumed.append(count_key)
        elif abs(float(n) - round(float(n))) > 1e-9:
            # V301/K-B (K-A DEVİR 9): sayı alanları tam sayıdır; sessiz
            # yuvarlama yok, ret (uç 422).
            self._reject_input(
                count_key, self.overrides.get(count_key),
                'value {} is not a whole number'.format(round(float(n), 6)),
                code='not_a_whole_number', accepted_range=(c_lo, c_hi))
        n = int(round(n))

        w_lo, w_hi = cfg['width_range_mm']
        width = None
        for key in width_keys:
            width = self._override_val(key, w_lo, w_hi)
            if width is not None:
                width /= 1000.0
                break
        if width is None:
            width = cfg['slot_width_m'] if 'slot_width_m' in cfg else cfg['fin_width_m']
            assumed.append(width_keys[0])

        d_lo, d_hi = cfg['depth_range_mm']
        depth = None
        for key in depth_keys:
            depth = self._override_val(key, d_lo, d_hi)
            if depth is not None:
                depth /= 1000.0
                break
        if depth is None:
            depth = cfg['slot_depth_m'] if 'slot_depth_m' in cfg else cfg['fin_depth_m']
            assumed.append(depth_keys[0])

        # Fiziksel kırpma: yuva dibi kasa cidarına dayanmamalı, komşu yuvalar
        # port yarıçapında çakışmamalı.
        r_port = max(self.D_core / 2.0, 1e-4)
        r_outer = self.D_chamber / 2.0
        # V301/K-B (K-A DEVİR 8): sınırı aşan KULLANICI değeri sessizce
        # kırpılmaz; ret kaydı düşer (uç 422 + en büyük değer). Doğrudan motor
        # kullanımı kırpılmış değerle sürer, ret ``rejected_inputs``te durur.
        # Varsayılan (beyanlı) değer sınırı aşarsa eski kırpma + beyan sürer.
        max_depth = cfg['max_depth_fraction'] * max(r_outer - r_port, 1e-4)
        if depth > max_depth:
            if depth_keys[0] not in assumed:
                self._reject_input(
                    depth_keys[0], self.overrides.get(depth_keys[0]),
                    'depth {:.3f} mm exceeds the geometric limit {:.3f} mm'
                    .format(depth * 1000.0, max_depth * 1000.0),
                    code='exceeds_geometric_limit',
                    accepted_range=(d_lo, round(max_depth * 1000.0, 3)))
            depth = max_depth
            clipped.append(depth_keys[0])
        max_width = cfg['max_width_fraction'] * (2.0 * np.pi * r_port / n)
        if width > max_width:
            if width_keys[0] not in assumed:
                self._reject_input(
                    width_keys[0], self.overrides.get(width_keys[0]),
                    'width {:.3f} mm exceeds the geometric limit {:.3f} mm'
                    .format(width * 1000.0, max_width * 1000.0),
                    code='exceeds_geometric_limit',
                    accepted_range=(w_lo, round(max_width * 1000.0, 3)))
            width = max_width
            clipped.append(width_keys[0])
        return n, width, depth, assumed, clipped

    def _finocyl_params(self):
        """Finocyl geometrisi — TEK tanım noktası (model + rapor aynı değerler).

        Dönüş: (n_fins, fin_width_m, fin_depth_m, finned_fraction,
                assumed_defaults, clipped_fields)
        Arayüz alan adları: fin_count, fin_width (mm), fin_length (mm, radyal
        derinlik). Kanatçıklı boy oranı için arayüzde alan YOKTUR; varsayılan
        kullanılır ve 'assumed_defaults' içinde beyan edilir.
        """
        cfg = FINOCYL_GRAIN
        n, width, depth, assumed, clipped = self._radial_slot_params(
            cfg, 'fin_count', ('fin_width',), ('fin_length', 'fin_depth'))
        f_lo, f_hi = cfg['fraction_range']
        frac = self._override_val('finned_length_fraction', f_lo, f_hi)
        if frac is None:
            frac = self._override_val('fin_length_fraction', f_lo, f_hi)
        if frac is None:
            frac = cfg['finned_length_fraction']
            assumed.append('finned_length_fraction')
        return n, width, depth, float(frac), assumed, clipped

    def _slotted_params(self):
        """Slotted geometrisi — TEK tanım noktası.

        Arayüz alan adları: slot_count, slot_width (mm), slot_depth (mm).
        Bu alanlar formda yoksa varsayılanlar kullanılır ve beyan edilir.
        """
        return self._radial_slot_params(
            SLOTTED_GRAIN, 'slot_count', ('slot_width',), ('slot_depth',))

    def _finocyl_offset_polygon(self, web_thickness):
        """Finocyl'in KANATÇIKLI kesiti, web kadar ofsetlenmiş (shapely, m).

        Ofset _radial_slot_offset üzerinden İLKELLERE DAĞITILARAK alınır;
        birleşik poligonu tek seferde buffer'lamak ince yakıt ceplerini
        yutup kütle kaçırır (ölçüm: %1.22 sapma — _radial_slot_offset
        docstring'i). web=0 başlangıç kesitini verir.
        """
        self._require_shapely('finocyl')
        n, width, depth, _frac, _a, _c = self._finocyl_params()
        return self._radial_slot_offset(n, width, depth, web_thickness)

    def _finocyl_port_polygon(self):
        """Finocyl'in kanatçıklı BAŞLANGIÇ kesiti (web=0)."""
        return self._finocyl_offset_polygon(0.0)

    def _finocyl_plain_offset_polygon(self, web_thickness):
        """Finocyl'in kanatçıksız (düz silindirik) kesiti, web ofsetli.

        Dairesel portun ofseti kapalı formdadır: r → r + w. Aynı quad_segs
        ile üretilir ki alan ve çevre AYNI poligon ailesinden gelsin
        (kütle korunumu bu tutarlılığa dayanır).
        """
        self._require_shapely('finocyl')
        return _ShapelyPoint(0.0, 0.0).buffer(
            self.D_core / 2.0 + web_thickness, quad_segs=96)

    def _finocyl_plain_polygon(self):
        """Finocyl'in kanatçıksız BAŞLANGIÇ kesiti (web=0)."""
        return self._finocyl_plain_offset_polygon(0.0)

    def _finocyl_section_lengths(self):
        """(kanatçıklı boy m, düz boy m) — toplamları L_grain."""
        _n, _wid, _d, frac, _a, _c = self._finocyl_params()
        l_fin = self.L_grain * frac
        return l_fin, self.L_grain - l_fin

    def _slotted_offset_polygon(self, web_thickness):
        """Slotted kesiti, web kadar ofsetlenmiş (shapely, m).

        Yarıklar boyun tamamını kat ettiği için tek kesit yeterlidir.
        Ofset yine ilkellere dağıtılır (bkz. _radial_slot_offset).

        Performans (v2.5.5): itki eğrisinin HER adımı aynı web ile iki kez
        çağırır (calculate_burn_area + _port_flow_area). Tek girdilik memo
        ikinci kurulumu atlar; aynı girdiler bit-aynı poligonu verdiğinden
        davranış değişmez.
        """
        self._require_shapely('slotted')
        n, width, depth, _a, _c = self._slotted_params()
        key = (self.D_core, n, width, depth, web_thickness)
        memo = getattr(self, '_slot_offset_memo', None)
        if memo is not None and memo[0] == key:
            return memo[1]
        geom = self._radial_slot_offset(n, width, depth, web_thickness)
        self._slot_offset_memo = (key, geom)
        return geom

    def _slotted_port_polygon(self):
        """Slotted BAŞLANGIÇ port kesiti (web=0)."""
        return self._slotted_offset_polygon(0.0)

    def _grain_port_polygon(self):
        """Grain tipine göre başlangıç port kesiti (shapely) — yoksa None."""
        if not SHAPELY_AVAILABLE:
            return None
        if self.grain_type == 'star':
            return self._star_port_polygon()
        if self.grain_type == 'wagon_wheel':
            return self._wagon_port_polygon()
        if self.grain_type == 'slotted':
            return self._slotted_port_polygon()
        if self.grain_type == 'finocyl':
            # Finocyl eksenel olarak İKİ kesitlidir; tek poligon temsil
            # etmez. Hacim ve tükenme _propellant_volume içinde ayrıca
            # ele alınır, burada kanatçıklı kesit döner (en geniş port).
            return self._finocyl_port_polygon()
        return None

    def _port_burn_perimeter(self, port0, web_thickness):
        """Bir port kesitinin yanan çevresi (m), web ilerlemesine göre.

        Huygens ilkesi: yanan yüzey, başlangıç yüzeyinin web kadar normal
        ofsetidir → poligon buffer'ı bunu birebir üretir. Port grain dış
        yarıçapına (D_chamber/2) ulaştığı yerlerde yakıt bitmiştir; dış
        çembere oturan yay uzunluğu yanan çevreden düşülür.
        Doğrulama: dairesel portta 2π(r0+w) analitik sonucunu binde-bir
        hassasiyetle verir (test_star_grain_model testleri).
        """
        return self._clipped_burn_perimeter(
            self._simple_offset(port0, web_thickness))

    def _simple_offset(self, port0, web_thickness):
        """Tek-seferlik buffer ofseti (star / wagon_wheel yolu, DEĞİŞMEDİ).

        Radyal yuvalı kesitlerde (finocyl / slotted) bu yol KULLANILMAZ;
        orada ofset ilkellere dağıtılır (bkz. _radial_slot_offset).
        """
        return port0.buffer(web_thickness, quad_segs=32) \
            if web_thickness > 0 else port0

    def _clipped_burn_perimeter(self, port_w):
        """ÖNCEDEN ofsetlenmiş bir kesitin yanan çevresi (m).

        Kasa dışına taşan bölge kırpılır; dış çembere oturan yay yakıtı
        bitmiş demektir ve yanan çevreden düşülür.
        """
        r_go = self.D_chamber / 2.0
        # Disk ve şerit sabittir — modül önbelleğinden okunur (her zaman
        # adımında yeniden buffer'lamak profil ölçümünde en pahalı kalemdi).
        disk = _cached_case_disk(r_go)
        inter = port_w.intersection(disk)
        if inter.is_empty:
            return 0.0
        per_total = inter.boundary.length
        # Dış çembere değen (yakıtı bitmiş) yaylar: ince halka kesişimi
        ring = _cached_case_ring(r_go)
        touching = inter.boundary.intersection(ring)
        per_burn = per_total - getattr(touching, 'length', 0.0)
        return max(per_burn, 0.0)

    def _clipped_port_area(self, port_w):
        """ÖNCEDEN ofsetlenmiş kesitin kasa içinde kalan alanı (m²).

        _clipped_burn_perimeter ile AYNI geometri; orada çevre, burada alan
        alınır. Kütle korunumu bu ikisinin aynı poligondan gelmesine dayanır
        (d(alan)/dw = yanan çevre).
        """
        r_go = self.D_chamber / 2.0
        inter = port_w.intersection(_cached_case_disk(r_go))
        return float(inter.area) if not inter.is_empty else np.pi * r_go ** 2

    def _offset_port_area(self, port0, web_thickness):
        """Ofsetlenmiş portun kasa içinde kalan kesit alanı (m²)."""
        return self._clipped_port_area(
            self._simple_offset(port0, web_thickness))

    def _port_flow_area(self, web_thickness):
        """Erozif yanma kütle akısının bölündüğü port akış kesiti (m²).

        Tip başına kesit tanımı:
          - end_burner: kasa kesiti (port yok, tüm kesit akar)
          - bates: port GERÇEKTEN dairedir → π(r_c+w)² kapalı formu
          - star / wagon_wheel / slotted: kesit poligondur, gerçek (kırpılmış
            ofset) alan kullanılır
          - finocyl: kanatçıksız (düz) bölüm en dar kesittir ve akı orada
            en yüksektir; erozif düzeltme o kesitten okunur → dairesel form

        ÖH D15 (P2B2-06): star ve wagon_wheel eskiden π(r_c+w)² ile geçiyordu
        ve bu, aynı fonksiyonun slotted için AÇIKÇA reddettiği yaklaşıklıktı.
        Ölçüldü (D=100/30 mm): star w=0'da 7,069 cm² kullanılıyordu, gerçek
        poligon 13,500 cm² (akı 1,910× şişik); wagon_wheel w=5 mm'de 12,566 ⟷
        34,357 cm² (2,734×). Şişen akı yalnız raporlanmıyordu — erozif yanma
        çarpanına girip basınç/itki eğrisini de kaydırıyordu. Aynı grain'in
        YANAN ÇEVRESİ zaten gerçek poligondan hesaplanıyordu; artık kesitin
        tek bir tanımı var.
        """
        if self.grain_type == 'end_burner':
            return np.pi * (self.D_chamber / 2) ** 2
        if self.grain_type == 'slotted' and SHAPELY_AVAILABLE:
            return self._clipped_port_area(
                self._slotted_offset_polygon(web_thickness))
        if self.grain_type in ('star', 'wagon_wheel') and SHAPELY_AVAILABLE:
            port0 = (self._star_port_polygon() if self.grain_type == 'star'
                     else self._wagon_port_polygon())
            return self._offset_port_area(port0, web_thickness)
        return np.pi * (self.D_core / 2 + web_thickness) ** 2

    def _star_burn_perimeter(self, web_thickness):
        """Star portun yanan çevresi (m) — _port_burn_perimeter sarmalayıcısı."""
        return self._port_burn_perimeter(self._star_port_polygon(),
                                         web_thickness)

    def _propellant_volume(self):
        """Grain tipine göre GERÇEK yakıt hacmi (m³).

        Isp = I_toplam/(m_p·g0) tabanı bu hacimden gelir; tüm tipler için
        dairesel annulus kullanmak star'da %10, end-burner'da %8 hata,
        wagon'da belirsiz hata veriyordu (2026-07-13 formül teyidi, K2).

        Performans (v2.5.5): calculate_performance zinciri bu saf fonksiyonu
        7+ kez çağırır; shapely'li tiplerde her çağrı kırpılmış poligon alanı
        hesaplıyordu. Sonuç, hacmi belirleyen TÜM geometri parametreleriyle
        anahtarlanıp örnek içinde memoize edilir — aynı anahtar bit-aynı
        değeri döndürür, davranış değişmez.
        """
        key = (self.grain_type, self.D_chamber, self.D_core, self.L_grain)
        if self.grain_type == 'star':
            key += self._star_params()
        elif self.grain_type == 'finocyl':
            key += tuple(self._finocyl_params()[:4])
        elif self.grain_type == 'slotted':
            key += tuple(self._slotted_params()[:3])
        memo = getattr(self, '_prop_volume_memo', None)
        if memo is not None and memo[0] == key:
            return memo[1]
        vol = self._propellant_volume_uncached()
        self._prop_volume_memo = (key, vol)
        return vol

    def _propellant_volume_uncached(self):
        """_propellant_volume'un gerçek hesabı (memo katmanı olmadan)."""
        r_outer = self.D_chamber / 2.0
        disk_area = np.pi * r_outer ** 2
        if self.grain_type == 'end_burner':
            # Core'suz tam silindir (sigara yanması)
            return disk_area * self.L_grain
        if self.grain_type == 'finocyl':
            # Eksenel olarak iki kesit: kanatçıklı bölüm + düz silindirik
            # bölüm. Tek bir poligonla temsil edilemez.
            # Kesit alanları yanma alanıyla AYNI kırpma yolundan okunur
            # (_clipped_port_area); kütle korunumu d(alan)/dw = yanan çevre
            # özdeşliğine dayanır, iki taraf farklı geometriden gelirse
            # bozulur.
            self._require_shapely('finocyl')
            l_fin, l_plain = self._finocyl_section_lengths()
            a_fin = self._clipped_port_area(self._finocyl_offset_polygon(0.0))
            a_plain = self._clipped_port_area(
                self._finocyl_plain_offset_polygon(0.0))
            return (max(disk_area - a_fin, 0.0) * l_fin
                    + max(disk_area - a_plain, 0.0) * l_plain)
        if self.grain_type == 'slotted':
            self._require_shapely('slotted')
            a0 = self._clipped_port_area(self._slotted_offset_polygon(0.0))
            return max(disk_area - a0, 0.0) * self.L_grain
        # ÖH D16/kati (P2B2-13): yanan yüzey zinciriyle AYNI kapı. Hacim
        # yolunda star sessizce BATES annulusuna, wagon_wheel ise
        # çakışmasız 7-daire toplamına düşüyordu — yani kütle korunumunun
        # iki tarafı (hacim ve yanan alan) farklı geometrilerden geliyordu.
        if self.grain_type in ('star', 'wagon_wheel'):
            self._require_shapely(self.grain_type)
        port0 = self._grain_port_polygon()
        if port0 is not None:  # star / wagon_wheel
            return max(disk_area - port0.area, 0.0) * self.L_grain
        # bates: dairesel annulus
        r_inner = self.D_core / 2.0
        return np.pi * (r_outer ** 2 - r_inner ** 2) * self.L_grain

    def calculate_burn_area(self, web_thickness):
        """Calculate burn area based on grain geometry"""
        if self.grain_type == 'bates':
            # OPUS DENETİM DÜZELTMESİ (major): n-segmentli BATES.
            # v2.6.26 (D1-KATI-OLU-1): yanan yüzey kümesi artık kullanıcının
            # inhibitör düzeninden gelir — eskiden form bayrakları hiç
            # okunmuyor, "uçlar yanar + dış inhibe" SABİT varsayılıyordu.
            #
            # Model (kütle korunumlu, tek web parametresi w):
            #   - Segmentler arası yüzeyler (grain boşluğuna bakan) HER ZAMAN
            #     yanar; yalnız yığının en ön ve en arka yüzü inhibe
            #     edilebilir. faces = yanan uç yüzey sayısı.
            #   - Uçtan yanma toplam boyu faces·w kadar kısaltır
            #     (L_top(w) = L0 − faces·w) — böylece −dV/dw = A_toplam
            #     özdeşliği her bayrak kombinasyonunda sağlanır.
            #   - Dış yüzey inhibe DEĞİLSE dış cephe de w ile içeri geriler
            #     (r_dis(w) = R0 − w) ve dış silindir alanı yanan yüzeye
            #     eklenir; web iki cepheden tükenir.
            # Varsayılan bayraklar (uçlar yanar, dış inhibe) eski formüle
            # bit-özdeş indirgenir (klasik BATES geometrisi; eski künye
            # "NASA SP-8064 / Sutton" idi — ikisinde de BATES geometrisi yok,
            # KU-K2).
            n_seg = self._bates_segment_count()
            outer_burns = not getattr(self, 'inhibit_outer', True)
            faces = 2 * n_seg
            if getattr(self, 'inhibit_front', False):
                faces -= 1
            if getattr(self, 'inhibit_rear', False):
                faces -= 1

            r_inner = self.D_core / 2 + web_thickness
            r_outer = (self.D_chamber / 2 - web_thickness
                       if outer_burns else self.D_chamber / 2)
            L_total = self.L_grain - faces * web_thickness

            # Web tükenme koşulu: radyal (r_i >= r_o) VEYA eksenel (L <= 0)
            if r_inner >= r_outer or L_total <= 0:
                return 0  # Grain burned out

            A_core = 2 * np.pi * r_inner * L_total
            A_ends = faces * np.pi * (r_outer**2 - r_inner**2)
            A_outer = (2 * np.pi * r_outer * L_total) if outer_burns else 0.0
            return A_core + A_ends + A_outer
            
        elif self.grain_type == 'star':
            # Gerçek model (2026-07-13): yanan çevre, başlangıç star
            # profilinin web kadar geometrik ofsetinden hesaplanır (Huygens).
            # Uç sayısı ve derinliği artık itki eğrisine tam yansır.
            # ÖH D16/kati (P2B2-13) — FAIL-CLOSED. Eskiden shapely yoksa
            # `π·D_core·2.5` kaba yaklaşıklığına düşülüyor ve uyarı yalnız
            # `warnings.warn` ile veriliyordu; uyarı YANITA HİÇ girmiyordu
            # (ölçüm once.json P2B2-13: `yanit_uyarisi_var: false`). Bedeli
            # sessiz ve fizik-dışıydı: aynı motorda toplam impuls 13.314 ->
            # 17.722 N·s (1,33x) ve Isp 230,7 -> 279,4 s. Kaba sayı artık
            # UYDURULMAZ: finocyl/slotted ile AYNI kapı kullanılır.
            self._require_shapely('star')
            return self._star_burn_perimeter(web_thickness) * self.L_grain
            
        elif self.grain_type == 'wagon_wheel':
            # Gerçek model (2026-07-13): star ile aynı Huygens ofset makinesi,
            # 7 delikli port poligonuyla. Eski 7·2π(r+w) formu delik-delik
            # çakışmasını ve dış yarıçap kesmesini görmüyordu → kasadaki
            # yakıtın 3 katı yakılıyordu (kütle korunumu ihlali).
            # ÖH D16/kati (P2B2-13) — FAIL-CLOSED, star ile aynı gerekçe.
            # Sınırsız-çevre yaklaşıklığı delik-delik çakışmasını ve dış
            # yarıçap kesmesini görmüyordu; ölçülen bedel bu dosyadaki en
            # büyük sessiz sapmaydı: toplam impuls 12.321 -> 74.952 N·s
            # (6,08x) ve Isp 209,8 -> 1276,3 s — hiçbir katı yakıtın
            # ulaşamayacağı bir sayı yanıta 200 ile giriyordu.
            self._require_shapely('wagon_wheel')
            return self._port_burn_perimeter(
                self._wagon_port_polygon(), web_thickness) * self.L_grain

        elif self.grain_type == 'finocyl':
            # GERÇEK MODEL (2026-07-19). Önceden bu tip etiketsiz `else`
            # dalına düşüp uç-yanmalı gibi hesaplanıyordu.
            # İki eksenel kesit, ikisi de aynı Huygens ofset makinesiyle:
            #   A(w) = per_kanatçıklı(w)·L_fin + per_düz(w)·L_plain
            # Kanatçık yan yüzeyleri ve dipleri per_kanatçıklı içindedir;
            # kanatçıklar tükendiğinde kesit kendiliğinden saf silindirik
            # porta döner (buffer birleşmesi) — nötr/progresif geçişin
            # fiziksel kaynağı budur. Uçlar ve dış yüzey inhibitörlüdür
            # (star/wagon_wheel ile aynı kabul).
            self._require_shapely('finocyl')
            l_fin, l_plain = self._finocyl_section_lengths()
            a_fin = self._clipped_burn_perimeter(
                self._finocyl_offset_polygon(web_thickness)) * l_fin
            a_plain = self._clipped_burn_perimeter(
                self._finocyl_plain_offset_polygon(web_thickness)) * l_plain
            return a_fin + a_plain

        elif self.grain_type == 'slotted':
            # GERÇEK MODEL (2026-07-19): silindirik port + tüm boyu kat eden
            # eksenel yarıklar. Yanan yüzey = port + yarık yan yüzeyleri +
            # yarık dipleri; hepsi ofsetlenmiş kesitin çevresinde yer alır.
            self._require_shapely('slotted')
            return self._clipped_burn_perimeter(
                self._slotted_offset_polygon(web_thickness)) * self.L_grain

        elif self.grain_type == 'end_burner':
            # Sigara yanması: sabit dairesel yüzey; web EKSENEL ilerler
            # (sonlanma koşulu calculate_thrust_curve'de web >= L_grain).
            r_outer = self.D_chamber / 2
            return np.pi * r_outer**2

        # Sessiz fallback YOK: tanınmayan tip buraya gelemez (constructor
        # doğrular) ama savunma amaçlı açık hata verilir.
        raise ValueError(
            f"Unsupported grain type '{self.grain_type}'. Supported grain "
            f"types: {', '.join(SUPPORTED_GRAIN_TYPES)}.")
    
    def _erosive_factor(self, mass_flux, port_diameter_ratio=1.0):
        """Erozif yanma çarpanı r/r0 — TEK tanım noktası.

        F067 (2026-07-25): bu çarpan eskiden yalnız burn_rate() içinde
        gömülüydü; rapor (_calculate_erosive_effects) ise onunla hiç ilgisi
        olmayan uydurma bir doğrudan ('min(25, G/100*5)') sayı üretiyordu.
        Artık hem çözücü hem rapor bu fonksiyonu çağırır, dolayısıyla
        kullanıcıya gösterilen artış hesaba GİREN artıştır.

        Formun kendisi ve bilinen sınırları için burn_rate() docstring'i
        (Lenoir-Robillard indirgenmiş vekili; Sutton & Biblarz 9. baskı
        Böl. 12).
        """
        try:
            G = float(mass_flux)
        except (TypeError, ValueError):
            return 1.0
        # Eşik ve referans akı modül sabitidir (EROSIVE_THRESHOLD_KG_M2S /
        # EROSIVE_REFERENCE_FLUX_KG_M2S); rapor bloğu AYNI sabiti yayımlar.
        if not np.isfinite(G) or G <= EROSIVE_THRESHOLD_KG_M2S:
            return 1.0
        m_ero = getattr(self, 'erosive_exponent', 0.8)
        reynolds_factor = ((G - EROSIVE_THRESHOLD_KG_M2S)
                           / EROSIVE_REFERENCE_FLUX_KG_M2S) ** m_ero
        geom_factor = max(port_diameter_ratio, 0.05) ** -0.2
        return 1.0 + self.erosive_burning_coeff * reynolds_factor * geom_factor

    def burn_rate(self, pressure, temperature=None, port_diameter_ratio=1.0):
        """High-precision burn rate with Saint-Robert's law + corrections (99.8% accuracy)"""
        # Saint-Robert yasası: r = a * P^n with advanced corrections
        # Birim kontrolü: a (m/s/bar^n), P (bar), sonuç (m/s)
        # OPUS DENETİM DÜZELTMESİ (#434): sıcaklık referansı TEK noktaya
        # (self.temp_ref) sabitlendi. Önceden buradaki lineer düzeltme 298.15 K,
        # initial_temp override'ı (a·exp(σp·(T0−temp_ref))) ise 293.15 K referansı
        # kullanıyordu — aynı fiziksel sıcaklık-duyarlılığı iki farklı referansla
        # ölçekleniyordu. Referans verilmezse temp_ref alınır → çarpan 1.0 (nötr,
        # eski varsayılan davranışla sayısal olarak özdeş).
        if temperature is None:
            temperature = self.temp_ref

        if pressure <= 0.1:  # Minimum combustion pressure threshold
            return 0.0

        # Base Saint-Robert's law calculation
        # F025 DÜZELTMESİ (2026-07-25): yakıt için yayımlanmış PARÇALI rejim
        # yasası varsa taban hız her çağrıda ANLIK basınçtan okunur (tek üslü
        # yasa dondurulmaz). Yasa yoksa klasik Saint-Robert r = a·P^n.
        # Kaynak: Nakka 1999/2001 KNDX/KNSB rejim tabloları (burn_rate_db).
        law_key = getattr(self, 'burn_rate_law_key', None)
        if law_key:
            from hrma.data import burn_rate_db as _brdb
            # burn_rate_db konvansiyonu: r[mm/s] = a·P[MPa]^n → m/s ve bar
            base_rate = _brdb.burn_rate_mmps(law_key, pressure / 10.0) / 1000.0
            # initial_temp override'ı self.a'yı ölçeklediği için parçalı yolda
            # aynı ölçek taban hıza uygulanır (aksi hâlde sıcaklık düzeltmesi
            # parçalı yasada sessizce kaybolurdu).
            base_rate *= float(np.exp(
                self.burn_rate_temp_coeff
                * (getattr(self, 'initial_grain_temperature', self.temp_ref)
                   - self.temp_ref)))
            # --------------------------------------------------------------
            # ÖH D15 a2 (P2B3-02) — PARTİ SAÇILIMI PARÇALI YASADA DA CANLI.
            # Tek üslü yolda üretim toleransı a ve n'e uygulanır:
            #   r' = a(1+eps_a) * P^(n+d_n) = (a*P^n) * (1+eps_a) * P^d_n
            # Yani AYNI tolerans, taban hıza uygulanan (1+eps_a)*P^d_n
            # çarpanına birebir eşittir. Parçalı yasada a/n hesaba hiç
            # girmediği için Monte Carlo örneklediği toleransı buraya koyar;
            # böylece iki yol AYNI fonksiyonel bozulmayı görür.
            # Varsayılan (1.0, 0.0) -> çarpan tam 1.0, davranış bit-aynı.
            lot_scale = float(getattr(self, '_burn_rate_lot_scale', 1.0))
            lot_shift = float(getattr(self, '_burn_rate_lot_exponent_shift',
                                      0.0))
            if lot_scale != 1.0 or lot_shift != 0.0:
                base_rate *= lot_scale * (pressure ** lot_shift)
        else:
            base_rate = self.a * (pressure ** self.n)  # m/s

        # Sıcaklık etkisi düzeltmesi. F066 DÜZELTMESİ (2026-07-25): aynı
        # fiziksel duyarlılık (σp) iki FARKLI fonksiyonel formla uygulanıyordu
        # — initial_temp override'ında ÜSTEL exp(σp·ΔT), burada LİNEER
        # (1 + σp·ΔT). Birinci mertebede eşdeğerler ama ΔT = 30 K, σp = 0.0042
        # için %0.74 ayrışırlar. Tek form (üstel) tutulur; referans yine
        # self.temp_ref'tir, dolayısıyla ΔT = 0'da çarpan tam 1.0 kalır.
        # Kaynak: Sutton & Biblarz 9. baskı Böl. 12 — r = r_ref·exp(σp·(T−T_ref)).
        temp_correction = float(np.exp(
            self.burn_rate_temp_coeff * (temperature - self.temp_ref)))

        # ÖH D16/kati (P2B2-14) — KAYNAKSIZ 'pressure plateau' ÇARPANI
        # SÖKÜLDÜ. Eski satırlar 100 bar üstünde tabana
        # ``1 - 0.02*log10(P/100)`` uyguluyor ve gerekçe olarak yalnız
        # "verified from test data" yazıyordu (hangi veri, hangi yakıt,
        # hangi kaynak — yok). İki somut zarar ÖLÇÜLDÜ (once.json P2B2-14):
        #   * Yayımlanan künye YANLIŞLANIYORDU. ``_burn_rate_publication``
        #     "single-exponent Saint-Robert law r = a * Pc^n with the
        #     coefficients supplied for this propellant" diyor; ölçüm
        #     150 bar'da r_ürün/r_SaintRobert = 0,99648, 300 bar'da 0,99046.
        #     Yani kullanıcının kendi (a, n) çifti beyansız detune ediliyor.
        #   * KAYNAKLI plateau modelinin ÜSTÜNE biniyordu. Plateau/mesa
        #     rejimi bu depoda zaten PARÇALI yasayla (Nakka KNDX/KNSB
        #     rejim tabloları, ``hrma.data.burn_rate_db``) modelleniyor.
        #     Ölçüm: kndx @150 bar, yasa tabanı 0,01582195 m/s, ürün
        #     0,01576624 m/s — kaynaklı tablonun sonucu kaynaksız çarpanla
        #     bir kez daha eziliyordu (çift sayım).
        # Plateau/mesa isteyen kullanıcı yolu tek ve KAYNAKLI kalır:
        # ``burn_rate_law`` / ``burn_rate_preset`` rejim tablosu.
        pressure_plateau = 1.0

        # Erosive burning correction (Summerfield / Lenoir-Robillard).
        # Baskın terim kütle-akısı bağımlılığı reynolds_factor = (G/500)^0.8;
        # eşik G > 100 kg/m²s (Summerfield tipi eşik davranışı: düşük akıda
        # erozyon yok). DENETİM DÜZELTMESİ (#446): eski kod geometrik çarpan
        # olarak port_diameter_ratio'yu DOĞRUDAN kullanıyordu — web açıldıkça
        # (~0.37→1) BÜYÜR, yani erozyonu yanma SONUNDA güçlendirirdi. Fiziksel
        # gerçek tam tersi: erozyon küçük port/yüksek G'de (yanma BAŞI) en
        # güçlüdür; Lenoir-Robillard geometrik bağımlılığı ~D^-0.2'dir
        # (Sutton & Biblarz 9. baskı Böl. 12; L-R ikinci terim ∝ G^0.8/L^0.2).
        # Yeni çarpan (D_port/D_ch)^-0.2: yanma başı ~1.22 → sonu 1.0, tekdüze
        # AZALAN — G^0.8 ile birlikte doğru monotonluk. Çarpanın mutlak ölçeği
        # ~O(1) korunduğundan erosive_burning_coeff kalibrasyon ölçeği bozulmaz.
        # Codex GPT-5.5 çapraz teyidi (2026-07-16): işaret/üs doğru, form
        # L-R indirgenmiş vekili olarak savunulabilir; tek eleştirisi G=100'deki
        # SERT eşiğin ~%0.6-0.9 süreksizlik yaratmasıydı → excess-flux formuna
        # geçildi: ((G-100)/400)^0.8, eşikte 0'dan sürekli başlar ve G=500
        # kalibrasyon çapasında eski değere eşittir (1.0) — k yeniden
        # kalibrasyon gerektirmez. Statik ateşleme kalibrasyonu yine önerilir.
        #
        # F070 (2026-07-25): erozif üs artık UI'nın 'erosive_m' alanından
        # okunur (eskiden alan gönderiliyor ama motorda HİÇ kullanılmıyordu;
        # kod 0.8'i sabitlemişti). Varsayılan 0.8 = Lenoir-Robillard kütle-akısı
        # üssü. Modelin BİLİNEN sınırı: yayımlanmış erozif yanma verisinde
        # G ≈ 1000-2000 kg/m²s'de r/r0 tipik 1.2-2.0 iken bu indirgenmiş vekil
        # +%3-6 verir, yani büyüklüğü sistematik olarak DÜŞÜK tahmin eder.
        # Sınır aşıldığında _design_health_warnings kullanıcıyı uyarır; k'nın
        # kendisi kaynaksız (statik ateşleme kalibrasyonu şart) olduğu için
        # katsayı KÖRLEMESİNE büyütülmedi (bkz. denetim F070).
        erosive_factor = self._erosive_factor(
            getattr(self, 'mass_flux', 0.0), port_diameter_ratio)

        # Final burn rate with all corrections
        corrected_rate = base_rate * temp_correction * pressure_plateau * erosive_factor

        # Physical limits enforcement.
        # F069 DÜZELTMESİ (2026-07-25): kırpma artık SESSİZ değil. app.py
        # burn_rate_a'yı 0.1'e kadar kabul ediyor, yani sınır tamamen meşru
        # girdiyle aşılabiliyor; eskiden kullanıcı girdiği katsayının yok
        # sayıldığını hiçbir yerde göremiyordu (a=0.05, n=0.35, 40 bar → ham
        # 182 mm/s, döndürülen 100 mm/s, uyarı listesi BOŞ). 100 mm/s'nin
        # 'fiziksel sınır' olduğu iddiası KAYNAKSIZDIR — katalize kompozit ve
        # çift-tabanlı yakıtlarda daha yüksek hızlar yayımlanmıştır; bu yüzden
        # sınır bir doğruluk çapası değil sayısal taşma koruması olarak
        # tutulur ve aşıldığı her koşuda kullanıcıya bildirilir.
        max_rate = BURN_RATE_NUMERIC_CEILING_MPS
        if corrected_rate > max_rate:
            self._burn_rate_clipped_max = max(
                float(getattr(self, '_burn_rate_clipped_max', 0.0)),
                float(corrected_rate))
            return max_rate
        return corrected_rate
    
    def calculate_altitude_performance(self, altitudes):
        """High-precision altitude performance (ICAO Standard Atmosphere + corrections)"""
        altitude_data = []
        
        # ICAO Standard Atmosphere (ISO 2533) - verified to 99.95% accuracy
        for alt in altitudes:
            # Geopotential height conversion
            H = alt * 6356766 / (6356766 + alt)  # Geopotential height
            
            # Katman tablosu merkezi sabit modülünden alınır (hrma.constants.ISA_LAYERS)
            # Kaynak: U.S. Standard Atmosphere 1976 (NOAA/NASA/USAF), Tablo 4
            # Her kayıt: (h_taban [m], T_taban [K], lapse [K/m], P_taban [Pa])
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
                pressure_atm = P_base * np.exp(
                    -self.g0 * M_AIR * (H - h_base) / (R_STAR_ICAO * T_base)
                )
            else:
                # Gradyan katman: P = P_b * (T/T_b)^(-g0*M/(R*lapse))
                T = T_base + lapse * (H - h_base)
                pressure_atm = P_base * (T / T_base) ** (
                    -self.g0 * M_AIR / (R_STAR_ICAO * lapse)
                )
            
            # Convert Pa to bar
            pressure_atm = pressure_atm / 100000
            
            # Space vacuum conditions
            # v2.6.26 — 100 km satiri ELLE YAZILMIS sayilarla doluyordu:
            #   pressure_atm = 1e-6 ; T = 1000
            # Oysa fonksiyonun kendi belgesi ICAO/ISO 2533 dogrulugu iddia
            # ediyor ve tablonun diger 7 satiri gercek ISA'dan geliyor.
            # Olculdu: 100 km'de deponun KENDI isa_temperature'i 186,95 K,
            # isa_pressure'i 2,344e-07 bar. Yani sicaklik 5,3 kat, basinc
            # 4,3 kat yanlisti ve tek yanitta ayni buyuklugun iki farkli
            # kaynagi vardi. Ayni yardimcilar hrma/analysis/launch_site.py
            # tarafindan zaten kullaniliyor — tek kaynaga baglaniyor.
            # ISA tablosu 84,852 km'de biter; ustunde izotermal uzanti
            # uygulanir ve bu durum cikti satirinda beyan edilir.
            #
            # ÖH D15 a3 (P2B2-11): bu dal GEOMETRİK ``alt`` ile çağrılıyordu,
            # oysa aynı fonksiyonun tablo dalı (yukarıda) GEOPOTANSİYEL ``H``
            # kullanıyor ve ``hrma.constants`` yardımcılarının kendi
            # belgeleri de geopotansiyel istiyor ("US Standard Atmosphere
            # 1976 ..., geopotansiyel irtifa [m]"). ``ISA_TABLE_TOP_M`` de
            # geopotansiyel bir sınırdır. İki irtifa tanımının tablo
            # tepesinde çarpışması ÖLÇÜLDÜ (bates, 100/500/30 mm, 40 bar):
            #   alt = 84850 m -> P = 4,576024e-06 bar, T = 189,185 K  (H yolu)
            #   alt = 84853 m -> P = 3,733153e-06 bar, T = 186,946 K  (alt yolu)
            # yani ÜÇ METREDE basınç %18,42 düşüyor ve sıcaklık 2,239 K
            # sıçrıyordu. Mutlak sapma da tek yönlü: yayımlanan / doğru
            # oranı 90 km'de 0,7948, 100 km'de 0,7535, 120 km'de 0,6661.
            # Sınır karşılaştırması ve çağrı artık aynı büyüklüktedir; süreklilik
            # cebirsel olarak sağlanır (aynı H, aynı yardımcı).
            if H > ISA_TABLE_TOP_M:
                T = isa_temperature(H)
                pressure_atm = isa_pressure(H) / 1e5   # Pa -> bar
                atmosphere_basis = ('ISA isothermal extension above '
                                    '84.852 km geopotential (US Std Atm 1976 '
                                    'table top); the ISA helpers are called '
                                    'with the geopotential height H, the same '
                                    'quantity the layer table below is indexed '
                                    'by, so the two branches meet without a '
                                    'jump at the table top')
            else:
                atmosphere_basis = 'ISA / US Std Atm 1976 (geopotential height)'
            
            # Optimal nozzle design for this altitude:
            # Tam izentropik Mach-alan bağıntısı (Sutton & Biblarz 9. baskı,
            # Denk. 3-25/3-26). Pe = Pa (optimal genişleme) alınarak çıkış Mach
            # sayısı basınç oranından kapalı formda çözülür; iterasyon gerekmez.
            # V301/N-CEA-2 (K2): lüle bağıntılarının üssü (CEA lülesi varsa
            # eşdeğer üs γ_n; yoksa self.gamma — bit-aynı eski yol).
            gamma = self._nozzle_gamma()
            Pe_Pc_opt = max(pressure_atm, 1e-6) / self.P_c
            epsilon_opt = self._expansion_ratio_from_pressure_ratio(Pe_Pc_opt)
            # v2.6.26 — KIRPMA BEYAN EDİLİYOR.
            # Bu kelepçe 80 ve 100 km satırlarında kabul edilebilir girdi
            # uzayının TAMAMINDA doymuş durumda: gamma=1,5 / Pc=5 bar
            # köşesinde ham değerler 1754 ve 8394 çıkıyor, yani o iki satır
            # hiçbir girdiyle 500'den ayrılamıyor. Kullanıcı "bu irtifadaki
            # optimum genişleme oranı" diye okuyor; gördüğü optimum değil
            # TAVAN. Sayı uydurma değil (model çıktısının kırpılmışı) ama
            # etiketi yanıltıyordu. 50 km satırında aynı kelepçe doymuyor
            # (ölçüldü: 100 - 456 arası), orası zaten canlı.
            epsilon_uncapped = float(epsilon_opt)
            epsilon_opt = max(2.5, min(epsilon_opt, 500))  # Physical limits
            epsilon_clamped = abs(epsilon_opt - epsilon_uncapped) > 1e-9
            
            # High-precision thrust coefficient with nozzle efficiency
            Pe_Pc = pressure_atm / self.P_c
            Pe_Pc = max(Pe_Pc, 1e-6)  # Avoid division by zero

            # ÖH D15 (P2B2-09): CF eskiden HER satırda optimum genişleme
            # (Pe = Pa) formülünden kuruluyordu, ama yayımlanan ε
            # [2,5; 500] bandına kırpılıyordu. Kırpılan satırda ε bir
            # lüleye, CF/Isp BAŞKA bir lüleye aitti: Pc=5 bar / gamma=1,5
            # köşesinde 0 m satırı ε=2,5 yayımlarken CF=1,08658 ve
            # Isp=177,080 s basıyordu; ε=2,5 lülesinin gerçeği CF=0,96801 ve
            # Isp=157,758 s, yani yayımlanan %12,25 FAZLA. Üst uçta (ε 500'e
            # kırpılınca) 80 km satırı %4,55 fazla veriyordu. CF artık
            # satırın KENDİ ε'sinden çözülür: kırpma yoksa Pe = Pa olduğu
            # için sayı bit-aynı kalır; kırpma varsa basınç-itki terimi
            # (Pe - Pa)/Pc * ε dâhil edilir (Sutton & Biblarz 9. baskı,
            # Denk. 3-30). Çıkış basıncı ε'dan tek kaynaktan çözülür
            # (NozzleDesigner.exit_pressure_from_expansion).
            gamma_term = 2 * gamma**2 / (gamma - 1)
            stagnation_term = (2 / (gamma + 1)) ** ((gamma + 1) / (gamma - 1))
            if epsilon_clamped:
                from hrma.engines.nozzle_design import NozzleDesigner
                Pe_row = NozzleDesigner.exit_pressure_from_expansion(
                    epsilon_opt, gamma, self.P_c)      # bar (girdiyle aynı)
                Pe_Pc_row = min(max(Pe_row / self.P_c, 1e-9), 0.999999)
                pressure_thrust_term = (
                    (Pe_Pc_row - pressure_atm / self.P_c) * epsilon_opt)
            else:
                Pe_Pc_row = Pe_Pc
                pressure_thrust_term = 0.0
            expansion_term = 1 - Pe_Pc_row ** ((gamma - 1) / gamma)

            CF_momentum_ideal = np.sqrt(
                gamma_term * stagnation_term * expansion_term)
            if self._cea_nozzle_state():
                # V301/N-CEA-2 (K2): momentum terimi itki zincirinin TEK
                # tanımından (γ_n + CEA çapası κ); deniz seviyesi satırı
                # CEA'nın optimum C_F'üne eşittir.
                CF_momentum_ideal = self._cf_momentum_term(Pe_Pc_row)
            CF_ideal = CF_momentum_ideal + pressure_thrust_term
            
            # Nozul verimi — ana itki eğrisiyle (satır ~1777) TUTARLI olmalı.
            # OPUS DENETİM DÜZELTMESİ (#530, diverjans ÇİFT SAYIMI):
            # self.nozzle_efficiency yakıt tablosunda zaten "Divergence + friction
            # losses" içeriyor (bkz. satır ~145, 0.985). Önceki kod eta_nozzle =
            # divergence_loss·bl_loss·heat_loss·nozzle_efficiency kurarak 15° konik
            # diverjans kaybını (λ=(1+cosα)/2, Sutton & Biblarz Böl. 3) ve
            # sürtünmeyi İKİNCİ kez uyguluyordu → irtifa Isp'i ~%1.7 düşük çıkıyor,
            # headline deniz-seviyesi Isp (yalnız nozzle_efficiency kullanır) ile
            # tutarsız oluyordu. Diverjans tek yerde (nozzle_efficiency) uygulanır.
            eta_nozzle = self.nozzle_efficiency
            
            CF_actual = CF_ideal * eta_nozzle
            
            # Specific impulse at this altitude
            isp_altitude = CF_actual * self.c_star / self.g0

            # Çıkış hızı — bu satırın KENDİ modeliyle tutarlı: satır o
            # irtifada optimum genişlemiş (Pe = Pa) nozulu analiz eder;
            # optimum genişlemede basınç-itki terimi sıfırdır, dolayısıyla
            # v_e = F/mdot = CF·c* = Isp·g0 (Sutton & Biblarz 9. baskı,
            # Denk. 2-16/3-30 özel hâli). Egzoz gösterimi (readNozzleExit)
            # dizinin ilk elemanından bu alanı okur.
            # Çıkış hızı momentum teriminden gelir; kırpılmamış (optimum)
            # satırda basınç-itki terimi sıfır olduğu için sayı eskisiyle
            # BİT-AYNIdır ve v_e = Isp*g0 özdeşliği orada aynen sürer.
            exit_velocity = CF_momentum_ideal * eta_nozzle * self.c_star

            altitude_data.append({
                'altitude': alt,
                'temperature': T,
                'pressure': pressure_atm,
                # ÖH D15 a3 (P2B2-11): ``atmosphere_basis`` yukarıda
                # kuruluyor ama HİÇBİR YERE yazılmıyordu (ölü değişken) —
                # satırın hangi ISA dalından geldiği okunamıyordu. İki dalın
                # ayrıştığı kusur giderildikten sonra hangi dalın kullanıldığı
                # da beyan edilir.
                'atmosphere_basis': atmosphere_basis,
                'expansion_ratio': epsilon_opt,
                # Kırpma olduysa AÇIKÇA söylenir; ham değer de taşınır ki
                # kullanıcı "optimum" ile "tavan" arasındaki farkı görsün.
                'expansion_ratio_clamped': bool(epsilon_clamped),
                'expansion_ratio_uncapped': (float(epsilon_uncapped)
                                             if epsilon_clamped else None),
                'expansion_ratio_basis': (
                    'clamped to the 2.5-500 model range; the uncapped optimum '
                    'for this altitude is reported separately. The thrust '
                    'coefficient and Isp in this row belong to the CLAMPED '
                    'nozzle (pressure-thrust term included), not to the '
                    'uncapped optimum'
                    if epsilon_clamped else
                    'optimum expansion for ambient pressure at this altitude'),
                'thrust_coefficient': CF_actual,
                'pressure_thrust_term': float(pressure_thrust_term),
                'thrust_coefficient_basis': (
                    'CF = CF_momentum(eps of THIS row) + (Pe - Pa)/Pc * eps, '
                    'times the nozzle efficiency; Pe is solved from the row '
                    'expansion ratio (NozzleDesigner.'
                    'exit_pressure_from_expansion). The pressure-thrust term '
                    'is exactly zero where the row is optimally expanded'),
                'nozzle_efficiency': eta_nozzle,
                'specific_impulse': isp_altitude,
                'exit_velocity': float(exit_velocity),  # m/s
                'exit_velocity_basis': (
                    'v_e = CF_momentum * c* with the delivered c* and the '
                    'nozzle efficiency applied. Where the row is optimally '
                    'expanded (Pe = Pa) the pressure thrust is zero and this '
                    'is exactly Isp*g0; where the expansion ratio was clamped '
                    'the two differ by the pressure-thrust term, which is '
                    'published in the same row'),
                'thrust_ratio': 1.0  # deniz seviyesine göre normalize edilir (aşağıda)
            })

        # OPUS DENETİM DÜZELTMESİ (#538): 'thrust_ratio' önceden
        # CF_actual/(CF_ideal·nozzle_efficiency) idi; CF_ideal sadeleşince
        # irtifadan BAĞIMSIZ bir sabit (~0.98) veriyordu ("Thrust variation with
        # altitude" etiketi yanıltıcıydı). Gerçek itki değişimini yansıtmak için
        # her irtifadaki itki katsayısını en düşük irtifadakine (≈deniz seviyesi)
        # oranlıyoruz → CF_actual, expansion_term (1−(Pe/Pc)^((γ−1)/γ)) üzerinden
        # ortam basıncı düştükçe artar, dolayısıyla oran irtifayla >1'e çıkar.
        if altitude_data:
            ref_idx = min(range(len(altitude_data)),
                          key=lambda k: altitude_data[k]['altitude'])
            cf_ref = altitude_data[ref_idx]['thrust_coefficient']
            if cf_ref > 0:
                for d in altitude_data:
                    d['thrust_ratio'] = d['thrust_coefficient'] / cf_ref

        return altitude_data
    
    def _calculate_detailed_analysis(self, curve):
        """Comprehensive technical analysis like hybrid/liquid systems"""
        avg_pressure = np.mean(curve['pressure'])
        # ÖH D15 a3 (P2B2-03). ``combustion_smoothness`` KIRPILMAMIŞ
        # duruyordu: aynı sözlükteki ikizi ``thrust_stability`` [0, 100]'e
        # kırpılıp kırpması ``thrust_stability_was_clamped`` ile beyan
        # edilirken, bu alanın ne kırpması ne künyesi vardı ve ARAYÜZDE
        # YÜZDE olarak basılıyordu (templates/solid.html, 'Combustion
        # Smoothness: %'). ÖLÇÜLDÜ (slotted, D_kasa = 100 mm,
        # D_çekirdek = 30 mm, APCP): L = 1500 mm / 70 bar -> -5,218;
        # L = 2000 / 70 -> -7,098; L = 2500 / 70 -> -8,820; L = 1500 / 40 ->
        # -0,614; L = 2000 / 40 -> -2,284; L = 2500 / 40 -> -3,562. Yani
        # kullanıcı NEGATİF bir "düzgünlük yüzdesi" okuyordu.
        #
        # Kırpma bilgi KAYBETMEZ: kırpılmamış büyüklüğün kendisi
        # ('pressure_oscillations_percent') aynı sözlükte adıyla yayımlanır.
        # Ortalama basınç pozitif değilse oran tanımsızdır ve sayı
        # UYDURULMAZ (None) — kardeş alanla birebir aynı sözleşme.
        if float(avg_pressure) > 0.0:
            pressure_oscillations = float(
                np.std(curve['pressure']) / avg_pressure * 100.0)
            _ham_smoothness = 100.0 - pressure_oscillations
            smoothness = float(min(100.0, max(0.0, _ham_smoothness)))
            smoothness_clamped = bool(_ham_smoothness < 0.0
                                      or _ham_smoothness > 100.0)
        else:
            pressure_oscillations = None
            smoothness = None
            smoothness_clamped = False
        
        # Thrust coefficient analysis
        # CF tanımı boğaz alanını kullanır: CF = F / (Pc * A_t)
        # (Sutton & Biblarz 9. baskı, Denk. 3-31) — oda kesiti DEĞİL
        A_t_ref = curve.get('throat_area', 0.0)
        if not A_t_ref or A_t_ref <= 0:
            d_t = self._estimate_throat_diameter()
            A_t_ref = np.pi * (d_t / 2) ** 2
        avg_thrust_coeff = np.mean([t / (p * 1e5 * A_t_ref)
                                   for t, p in zip(curve['thrust'], curve['pressure']) if p > 0])
        
        # Mass flow efficiency
        theoretical_mass_flow = np.mean(curve['mass_flow'])
        
        # Combustion efficiency metrics
        # DENETİM DÜZELTMESİ (#572): η_c* artık GERÇEK tanımıyla hesaplanıyor —
        # teslim edilen c*'ın AYNI yakıtın teorik c*'ına oranı (Sutton & Biblarz
        # 9. baskı, Eş. 3-32 civarı; statik ateşleme veri-indirgeme standardı):
        #     c*_teslim = ∫Pc·A_t dt / m_yakıt ,  η_c* = c*_teslim / c*_teorik
        # Eski kod self.c_star'ı SABİT 1600 m/s'ye (APCP ideali) bölüyordu; bu,
        # düşük-enerjili ama tam-verimli yakıtı (şeker c*≈921 → %57.6) "verimsiz"
        # gösteren anlamsız bir metrikti. Yeni tanımda ideal (kayıpsız) simülasyon
        # ~%100 verir — doğru; kullanıcı CSV doğrulama paneliyle GERÇEK test
        # eğrisi yüklediğinde bu metrik gerçek yanma verimine dönüşür.
        m_propellant = self._propellant_volume() * self.rho_p  # kg
        if m_propellant > 0 and len(curve['time']) > 1:
            pressure_integral = _trapezoid(
                np.asarray(curve['pressure']) * 1e5, curve['time'])  # Pa·s
            c_star_delivered = pressure_integral * A_t_ref / m_propellant  # m/s
            # Payda TEORİK c*'tır (kullanıcının yanma verimi UYGULANMAMIŞ
            # hâli). Teslim edilen c*'ı teslim edilen c*'a bölmek kaybı
            # sıfırlıyordu — Codex bulgusu, 2026-07-19.
            c_star_efficiency = (c_star_delivered
                                 / self._c_star_theoretical() * 100.0)
        else:
            c_star_efficiency = 100.0  # veri yok → ideal varsayım (kayıpsız sim)

        # --- Teorik Isp + künyesi (ÖH D21 a1, P2B4-10) --------------------
        # Teorik Isp motorun fiilen çalıştığı ORTALAMA basınçta değerlendirilir.
        # Ortam basıncı o basınca eşit ya da ondan büyükse optimal genişleme
        # tanımsızdır ve _calculate_theoretical_isp None döner — sayı
        # kırpılarak UYDURULMAZ, alan boş kalır ve gerekçe burada yazar.
        teorik_isp = self._calculate_theoretical_isp(avg_pressure)
        _amb_bar = float(getattr(self, 'ambient_pressure_bar',
                                 SEA_LEVEL_PRESSURE_BAR))
        if teorik_isp is None:
            teorik_isp_kunye = (
                f'Not computable: the ambient pressure ({_amb_bar:.4f} bar) '
                f'is not below the mean chamber pressure of this burn '
                f'({float(avg_pressure):.4f} bar), so the exit-to-chamber '
                f'pressure ratio of an optimally expanded nozzle is >= 1 and '
                f'Sutton & Biblarz Eq. 3-30 has no solution. No number is '
                f'reported rather than a clamped one: the previous code '
                f'pinned the ratio at 0.999 and handed every such motor the '
                f'same specific impulse regardless of its chamber pressure.')
        else:
            teorik_isp_kunye = (
                f'CF_ideal * c*_theoretical / g0 (Sutton & Biblarz Eq. 3-32 '
                f'with the ideal thrust coefficient of Eq. 3-30), evaluated '
                f'at the MEAN chamber pressure of this burn '
                f'({float(avg_pressure):.4f} bar) against an ambient '
                f'pressure of {_amb_bar:.4f} bar, so it is comparable with '
                f'the delivered Isp of the same run. It is the LOSSLESS '
                f'reference: the combustion efficiency supplied by the user '
                f'is deliberately NOT applied here, because the same loss is '
                f'already reported as combustion_losses below.')

        # --- İtki profili (B2-1, B2-2) ------------------------------------
        # Biçim sınıfı ARTIK tepeyi görüyor; ölçüler kararın yanında
        # yayımlanır ki etiket doğrulanabilsin.
        shape = self._thrust_shape_report(curve['thrust'], curve['time'])
        # Kararlılık: değişim katsayısı (CV = std/ortalama). ESKİ KUSUR
        # (B2-2): alan '100 - CV*100' idi ve alt sınırı YOKTU; CV 1'i aşınca
        # NEGATİFE geçiyordu. ÖLÇÜLDÜ (APCP, D_kamara = 100 mm,
        # D_çekirdek = 30 mm, L = 500 mm, 40 bar): slotted grainde
        # thrust_stability = -1,44 (%), wagon_wheel = 5,45, star = 28,12.
        # Kullanıcı yüzde birimli bir panelde "-1,4 %" görüyordu.
        #
        # KARAR: alanın adı ve birimi KORUNUR (arayüz onu yüzde olarak
        # basıyor), tanımı [0, 100] aralığına KIRPILIR ve kırpmanın olduğu
        # SÖYLENİR. Kırpma bilgi kaybetmez, çünkü kırpılmamış büyüklüğün
        # kendisi ('thrust_variation_coefficient_percent') aynı sözlükte
        # adıyla yayımlanır: 0 değeri "CV >= 1" demektir ve gerçek genliği
        # okuyucu oradan görür.
        thrust_arr = np.asarray(curve['thrust'], dtype=float)
        thrust_mean = float(np.mean(thrust_arr)) if thrust_arr.size else 0.0
        if thrust_mean > 0.0:
            cv_percent = float(np.std(thrust_arr) / thrust_mean * 100.0)
            stability = float(min(100.0, max(0.0, 100.0 - cv_percent)))
            stability_clamped = bool(cv_percent > 100.0 or cv_percent < 0.0)
        else:
            # Ortalama itki sıfır/negatif: CV tanımsızdır, sayı uydurulmaz.
            cv_percent = None
            stability = None
            stability_clamped = False
        # Sınıf KARARLAŞTIRILAMADIYSA arayüze İngilizce bir sözcük ('Undetermined')
        # gönderilmez: alan None döner ve solid.html'in dürüst biçimlendiricisi
        # (fmtTextField -> 'not classified', gerekçeyi <key>_basis'ten okur)
        # yerelleştirilmiş metni kendisi kurar. Makine okuyucusu için sınıf
        # 'thrust_curve_shape.shape' altında adıyla durur.
        belirlendi = shape['shape'] != SOLID_THRUST_SHAPE_UNDETERMINED
        return {
            'thrust_profile_analysis': {
                'thrust_curve_type': shape['shape'] if belirlendi else None,
                'thrust_curve_type_basis': shape['basis'],
                'thrust_curve_shape': shape,
                'thrust_stability': stability,
                'thrust_variation_coefficient_percent': cv_percent,
                'thrust_stability_was_clamped': stability_clamped,
                'thrust_stability_basis': (
                    'thrust_stability = 100 - CV[%] clamped to [0, 100], '
                    'where CV is the coefficient of variation (standard '
                    'deviation / mean) of the full-resolution thrust samples. '
                    'A reported 0 means CV >= 100%, i.e. the spread is at '
                    'least as large as the mean - read '
                    "'thrust_variation_coefficient_percent' for the unclamped "
                    'magnitude. Null means the mean thrust is not positive, '
                    'so the ratio is undefined and no number is invented.'),
                'pressure_oscillations_percent': pressure_oscillations,
                'combustion_smoothness': smoothness,
                'combustion_smoothness_was_clamped': smoothness_clamped,
                'combustion_smoothness_basis': (
                    'combustion_smoothness = 100 - '
                    'pressure_oscillations_percent clamped to [0, 100], where '
                    'pressure_oscillations_percent is the coefficient of '
                    'variation (standard deviation / mean) of the solved '
                    'chamber-pressure samples. A reported 0 means the '
                    'oscillation amplitude is at least as large as the mean '
                    'pressure - read \'pressure_oscillations_percent\' in '
                    'this same dictionary for the unclamped magnitude. Null '
                    'means the mean pressure is not positive, so the ratio is '
                    'undefined and no number is invented. This is the same '
                    'contract as thrust_stability above.'),
            },
            'performance_metrics': {
                'average_thrust_coefficient': avg_thrust_coeff,
                'c_star_efficiency_percent': c_star_efficiency,
                'theoretical_vs_actual_isp': dict(
                    {
                        # Teorik Isp, motorun fiilen çalıştığı ortalama basınçta
                        # değerlendirilir ki gerçek Isp ile karşılaştırma
                        # anlamlı olsun
                        'theoretical_isp': teorik_isp,
                        # ÖH D21 a1 (P2B4-10): sayı KAZANILAMADIYSA alan
                        # boş kalır ve gerekçesi burada yazar; eskiden
                        # Pe/Pc sessizce 0,999'a kırpılıyor ve ortam
                        # basıncı hazne basıncını aşan HER motor aynı
                        # sahte Isp'yi alıyordu.
                        'theoretical_isp_basis': teorik_isp_kunye,
                    },
                    **self._isp_loss_breakdown(c_star_efficiency)
                )
            },
            'grain_regression_analysis': {
                'burn_rate_consistency': self._analyze_burn_rate_consistency(curve),
                'web_thickness_utilization': self._web_utilization_percent(curve),
                'web_thickness_utilization_basis': (
                    'consumed web / consumable web x 100, clamped to '
                    '[0, 100]. The numerator is the time integral of the '
                    'burn rate over the solved curve (the same integral '
                    "published as grain_design.web_burnout_mm); the "
                    'denominator is the web the solver itself can consume: '
                    'for the polygon grain types (star, wagon wheel, '
                    'finocyl, slotted) it is the thickness at which the '
                    'burning area vanishes, because those cross-sections '
                    'stop burning before the radial web is used up; for '
                    'bates and the closed-form fallbacks it is '
                    '(D_chamber - D_core)/2, and for an end burner the '
                    'grain length. It is NOT the solver scan bound '
                    'grain_design.web_available_mm, which is deliberately '
                    'wider for the polygon grain types. Which of these the '
                    'denominator actually came from in THIS run is published '
                    'as web_consumable_basis: when the geometric burnout web '
                    'cannot be established the radial web is used instead, '
                    'and that substitution is named there rather than left '
                    'to this sentence.'),
                'web_consumable_mm': float(
                    self._available_web_thickness() * 1000.0),
                # ÖH D20 (OH-D19-23): paydanın HANGİ hükümle kurulduğu.
                # Yukarıdaki düzyazı poligon tiplerde paydanın "yanan alanın
                # sıfırlandığı kalınlık" olduğunu söylüyor; geometrik tükeniş
                # kazanılamazsa radyal ete düşülüyordu ve düzyazı yine aynı
                # şeyi söylüyordu. Kaynak artık makinece okunur.
                'web_consumable_basis': getattr(
                    self, '_available_web_basis', None),
                'erosive_burning_effects': self._calculate_erosive_effects(curve)
            }
        }

    def _isp_loss_breakdown(self, c_star_efficiency_percent):
        """Isp kayıp dökümü [%] — hepsi hesaplanır, sabit değil.

        DENETİM DÜZELTMESİ (2026-07-19): combustion 3.2 / nozzle 2.1 /
        two_phase 1.8 sabitleri kaldırıldı. Metalize APCP ile şeker yakıtı
        arasında hiç fark yoktu; kullanıcı bu dağılıma bakıp nozul mu yanma mı
        iyileştireceğine karar veriyordu.

        - combustion_losses: hesaplanan c* veriminden (100 - eta_c*).
        - nozzle_losses: itki katsayısına FİİLEN uygulanan toplam nozul
          veriminden (yakıt tablosu + kullanıcı override'ları).
        - two_phase_losses: yoğuşmuş faz kütle kesrinden
          (eta = 1 - k*X_p, Sutton & Biblarz sec. 3.5). Bu kalem itki
          katsayısına UYGULANMAZ — 'two_phase_losses_applied' alanı bunu
          açıkça söyler; yalıtsız raporlanırsa çifte sayım olurdu.
        - divergence_losses: kullanıcı yarı açı verdiyse lambda=(1+cos a)/2
          konik diverjans kaybı; vermediyse taban verimin içinde olduğu
          beyan edilir.
        """
        combustion_losses = max(0.0, 100.0 - float(c_star_efficiency_percent))
        nozzle_losses = max(0.0, 100.0 * (1.0 - self._total_nozzle_efficiency()))

        # ÖH D15 a3 (P2B1-11): çözüm TEK noktadan (_condensed_mass_fraction)
        # — kompozit ailede kesir artık kaydın KENDİ formülasyonundan gelir,
        # metal yüklemesi ayırt edilmeden apcp'den devralınmaz.
        x_particle, x_source, x_kunye = _condensed_mass_fraction(
            self.propellant_type)
        # ÖH D32 (OH-D31-17) / ÖH D33 (OH-D32-17): durum TEK tanım
        # noktasından gelir ve artık SAYININ YAYIMLANIP YAYIMLANMAYACAĞINI
        # da o belirler — iki karar (durum ⟷ sayı) ayrışamaz.
        eta_2phase_user = float(getattr(self, 'two_phase_efficiency', 1.0))
        durum = _two_phase_correction_state(x_particle, eta_2phase_user)
        zarf_disi = (durum['two_phase_correction_status']
                     == TWO_PHASE_STATUS_OUT_OF_ENVELOPE)
        two_phase_withheld_reason = None
        if x_particle is None:
            two_phase_losses = 0.0
            two_phase_basis = (
                f"No condensed-phase mass fraction is tabulated for "
                f"'{self.propellant_type}'; two-phase loss reported as zero "
                f"rather than guessed.")
        elif zarf_disi:
            # ÖH D33 · OH-D32-17 — BERKE KARARI (15 Eyl 2026, hüküm-21c):
            # K çapasının yayımlanmış veri penceresi DIŞINDA kalan yakıtlar
            # için doğrusal teşhis SAYISI GERİ ÇEKİLİR; beyan (durum künyesi)
            # kalır. ÖLÇÜLDÜ (a1/once.json · K3, taban 56f88e70): knsu/kndx/
            # knsb/sugar (X_p = 0,44) %5,28 ve black_powder (X_p = 0,55)
            # %6,60 yayımlıyordu; AYNI durumda hrma.analysis.two_phase_loss
            # modülü SAYI ÜRETMİYOR (OUT_OF_PUBLISHED_RANGE, SP-8039 Fig. 8
            # penceresi 0-0,40). Yani aynı yanıt aynı büyüklük için hem
            # "ölçülemez" hem de bir sayı diyordu.
            #
            # Fail-closed doktrini (Doktrin 1): pencere dışında hüküm
            # KAZANILMAMIŞTIR, dolayısıyla sayı yayımlanmaz. Bu bir
            # gizleme değil ADLANDIRMADIR: alan ``None`` döner, gerekçesi
            # ``two_phase_losses_withheld_reason`` ile makine-okur biçimde
            # ve künyede insan diliyle verilir. Yayımlanan Isp ETKİLENMEZ —
            # bu kalem zaten itki katsayısına UYGULANMIYORDU
            # (two_phase_losses_applied = False), bu yüzden hiçbir
            # performans sayısı değişmez.
            two_phase_losses = None
            two_phase_withheld_reason = 'outside_anchor_envelope'
            two_phase_basis = (
                f"WITHHELD (reason: outside_anchor_envelope). The linear "
                f"diagnostic eta_2phase = 1 - {TWO_PHASE_LOSS_COEFF:.2f}*X_p "
                f"is an ALUMINIUM-OXIDE anchor (AFRPL aluminium rule of "
                f"thumb; NASA SP-8039 Fig. 8 metal-oxide family) and this "
                f"propellant's X_p = {x_particle:.3f} lies outside its "
                f"published data window, where hrma.analysis.two_phase_loss "
                f"itself refuses to produce a number "
                f"(OUT_OF_PUBLISHED_RANGE). Publishing the extrapolated "
                f"percentage anyway would have been a number this solver "
                f"has not earned, so no number is published; see "
                f"two_phase_correction_status_basis for the full "
                f"declaration. X_p source: {x_kunye}")
        else:
            two_phase_losses = 100.0 * TWO_PHASE_LOSS_COEFF * x_particle
            # ÖH D15 a3 (P2B1-11): "devralındı mı?" sorusu artık KAYNAK
            # ANAHTARDAN yanıtlanıyor; kaydın kendi formülasyonundan
            # türetilen kesir DEVRALMA DEĞİLDİR ve öyle beyan edilmez.
            two_phase_basis = (
                f"eta_2phase = 1 - {TWO_PHASE_LOSS_COEFF:.2f} * X_p with "
                f"X_p = {x_particle:.3f} (condensed mass fraction from the "
                f"propellant formulation; Sutton & Biblarz sec. 3.5); "
                f"source: {x_kunye}")

        half_angle = getattr(self, 'divergent_half_angle_deg', None)
        if half_angle is not None:
            divergence_losses = 100.0 * (
                1.0 - _conical_divergence_efficiency(half_angle))
            # ÖH D15 (P2B2-08): künye eskiden "zaten nozul veriminin içinde"
            # diyordu; yarı açı ~14,1 dereceyi geçtiği anda bu aritmetik
            # olarak yanlıştı (45 derecede %14,64 kayıp, verimin toplam
            # kaybı %1,5). Referans koninin kaybı tabanın içindedir, ONA GÖRE
            # fazlası ise CF'e FİİLEN uygulanır.
            lambda_ref = _conical_divergence_efficiency(
                SOLID_NOZZLE_REFERENCE_HALF_ANGLE_DEG)
            ref_losses = 100.0 * (1.0 - lambda_ref)
            eta_table = float(self.nozzle_efficiency)
            # ÖH D17 (P2B2-08 ŞART): künye "tablo verimi 15 derecelik koniyi
            # ZATEN İÇERİR" diyordu; bu, eta > lambda(15) olan kayıtlarda
            # (altı kompozit kayıtta eta = 0,985 > 0,982963) aritmetik olarak
            # yanlıştı — sürtünmeye kalan pay negatif çıkıyordu. Sayı
            # değişmez (uygulanan yalnız ORANDIR); beyan artık kendi
            # verilerini yazıyor ve doğrulanabilir.
            residual_pct = 100.0 * (1.0 - eta_table / lambda_ref)
            divergence_basis = (
                f"lambda = (1+cos {half_angle:.1f} deg)/2 conical divergence "
                f"= {divergence_losses:.4f}% total. The "
                f"{SOLID_NOZZLE_REFERENCE_HALF_ANGLE_DEG:.0f} deg reference "
                f"cone is a MODELLING ASSUMPTION, not a measured "
                f"decomposition of the propellant table's nozzle efficiency: "
                f"that table value is eta = {eta_table:.4f} while "
                f"lambda({SOLID_NOZZLE_REFERENCE_HALF_ANGLE_DEG:.0f}) = "
                f"{lambda_ref:.6f} ({ref_losses:.4f}% loss), so the residual "
                f"eta would leave for friction and every other nozzle loss "
                f"is {residual_pct:+.4f}%"
                + (" - NEGATIVE, i.e. eta is above the reference cone alone "
                   "and cannot contain it as a factor. "
                   if residual_pct < 0.0 else ". ")
                + f"Only the RATIO is applied to the thrust coefficient: "
                f"lambda({half_angle:.1f})/lambda("
                f"{SOLID_NOZZLE_REFERENCE_HALF_ANGLE_DEG:.0f}) = "
                f"{self._divergence_efficiency_correction():.6f}, which is "
                f"exactly 1.0 at the reference angle, so Isp follows the "
                f"half angle you entered and equals the table value at "
                f"{SOLID_NOZZLE_REFERENCE_HALF_ANGLE_DEG:.0f} deg")
        else:
            user_div = getattr(self, 'user_divergence_loss', None)
            divergence_losses = 100.0 * user_div if user_div is not None else 0.0
            lambda_ref = _conical_divergence_efficiency(
                SOLID_NOZZLE_REFERENCE_HALF_ANGLE_DEG)
            eta_table = float(self.nozzle_efficiency)
            residual_pct = 100.0 * (1.0 - eta_table / lambda_ref)
            divergence_basis = (
                f"No half angle was supplied, so the divergence multiplier "
                f"applied to the thrust coefficient is exactly 1.0 and Isp "
                f"carries the propellant table's nozzle efficiency "
                f"eta = {eta_table:.4f} as tabulated. The "
                f"{SOLID_NOZZLE_REFERENCE_HALF_ANGLE_DEG:.0f} deg reference "
                f"cone (lambda = {lambda_ref:.6f}) is only the MODELLING "
                f"ASSUMPTION the half-angle correction is measured against; "
                f"it is not claimed to be a factor inside eta - the residual "
                f"that claim would leave for friction here is "
                f"{residual_pct:+.4f}%")

        # İki-fazlı kayıp İKİ ayrı sayıdır ve karıştırılmamalıdır:
        #  * two_phase_losses          : yakıt formülasyonundan HESAPLANAN
        #                                kayıp (yalnız teşhis; Isp'ye
        #                                uygulanmaz — kullanıcının girdisiyle
        #                                çifte sayım olurdu),
        #  * two_phase_efficiency_applied: kullanıcının 'two_phase_loss'
        #                                alanından gelen ve CF'e FİİLEN
        #                                uygulanan verim çarpanı.
        # O9 (v2.6.26): arayüzün kayıp tablosu bu kalemi hiç göstermiyordu,
        # bu yüzden "%4.08 kayıp raporlandı ama nereye gitti?" sorusu
        # cevapsız kalıyordu. Alanlar artık ikisini de adıyla veriyor.
        # ÖH D32 (OH-D31-17): "uygulandı mı?" sorusunun yanıtı (False) ile
        # "uygulanması gereken düzeltme DOĞRULANDI mı?" sorusunun yanıtı
        # AYNI ŞEY DEĞİLDİR. İkincisi bugüne kadar hiçbir kanalda
        # yayımlanmıyordu (ÖLÇÜLDÜ: once.json Z4, üç kanalda da eşleşme 0),
        # bu yüzden eta = 1,0 okuyan kullanıcı "iki-faz kaybı yok" ile
        # "iki-faz düzeltmesi yapılmadı"yı ayırt edemiyordu. Durum artık
        # TEK tanım noktasından (_two_phase_correction_state) gelir ve
        # YUKARIDA, sayının yayımlanıp yayımlanmayacağına karar verildiği
        # yerde hesaplanır (ÖH D33 · OH-D32-17).
        return {
            'combustion_losses': float(combustion_losses),
            'nozzle_losses': float(nozzle_losses),
            # ÖH D33 · OH-D32-17: pencere dışında SAYI YOK — ``None``
            # "hesaplanamadı" demektir ve gerekçesi aşağıdaki alandadır.
            # Arayüz bu alanı ``fmtField`` ile okur: sayı yoksa "not
            # computed" yazar ve künyeyi başlık olarak gösterir (uydurma
            # sayı basmaz).
            'two_phase_losses': (None if two_phase_losses is None
                                 else float(two_phase_losses)),
            'two_phase_losses_withheld_reason': two_phase_withheld_reason,
            'two_phase_losses_applied': False,
            'two_phase_efficiency_applied': eta_2phase_user,
            'two_phase_user_losses': float(100.0 * (1.0 - eta_2phase_user)),
            'two_phase_losses_basis': two_phase_basis,
            **durum,
            'divergence_losses': float(divergence_losses),
            'divergence_losses_basis': divergence_basis,
            # Yarı açıdan gelen ve CF'e FİİLEN uygulanan çarpan (referans
            # koniye göre); açı verilmediyse 1.0.
            'divergence_efficiency_applied': float(
                self._divergence_efficiency_correction()),
            'divergence_reference_half_angle_deg': float(
                SOLID_NOZZLE_REFERENCE_HALF_ANGLE_DEG),
            'nozzle_efficiency_applied': float(self._total_nozzle_efficiency()),
        }

    # =====================================================================
    # v2.6.27 — DOĞRULANMIŞ ANALİZ MODÜLLERİNİN KATI MOTORA BAĞLANMASI
    #
    # Aşağıdaki bloklar hrma/analysis ve hrma/flow altındaki, kendi
    # doğrulama testleriyle gelen modülleri katı motorun GERÇEK çözüm
    # durumuna bağlar. Ortak kurallar:
    #
    #   1. Modüle giden her girdi çözücünün hesabından gelir. Bir girdi
    #      yoksa modül ÇAĞRILMAZ ve blok, eksik girdiyi ADIYLA anan bir
    #      NOT_MODELLED beyanıyla döner — literatür/varsayılan değer
    #      uydurulup modül "çalışır" gösterilmez.
    #   2. Her blok kendi künyesini taşır: hangi modül, hangi girdiler,
    #      hangi sürüm (_basis).
    #   3. Hiçbiri Isp'ye, itki katsayısına ya da geometriye GERİ
    #      BESLENMEZ — bloklar teşhis amaçlıdır ve bunu açıkça söyler.
    #      (Mevcut verim çarpanlarıyla çift sayım yasağı.)
    # =====================================================================

    def _chamber_gas_residence_time_ms(self):
        """Ortalama kamara gazı kalış süresi [ms] — ÇÖZÜCÜNÜN kendi bağıntısı.

        Kalış süresi tanım gereği tau = m_gaz / mdot'tir. Çözücü boğulmuş
        akışı mdot = Pc·A_t/c* ile (calculate_thrust_curve ve
        _design_throat_area aynı bağıntıyı kullanır), kamara gazını ideal
        gazla rho_c = Pc/(R·T_c) ile kurar (nozul çıkış durumu ve Bartz ısı
        akışı da aynı R = R_evrensel/MW_egzoz değerini kullanır). İkisi
        birleştiğinde Pc sadeleşir:

            tau = rho_c · V_serbest / mdot = V_serbest · c* / (R · T_c · A_t)

        Bu YENİ bir fizik ya da yeni bir sayı değildir: dört çarpanın da
        kaynağı çözücünün hâlihazırda ürettiği büyüklüklerdir
        (_case_free_volume, self.c_star, self.T_c + self.mw_exhaust,
        _design_throat_area). Hermsen (1981) tanecik çapı bağıntısının
        istediği "ortalama kamara kalış süresi" tam olarak budur
        (AIAA 96-2779'daki yeniden basımda tau, milisaniye).

        Çarpanlardan biri üretilemiyorsa None döner — varsayılan uydurulmaz.
        """
        try:
            v_free = float(self._case_free_volume())
            a_t = float(self._design_throat_area()[0])
            c_star = float(self.c_star)
            t_c = float(self.T_c)
            mw = float(getattr(self, 'mw_exhaust', 0.0) or 0.0)
        except Exception:
            return None
        if min(v_free, a_t, c_star, t_c, mw) <= 0.0:
            return None
        r_gas = R_UNIVERSAL / mw                      # J/(kg·K)
        tau_s = v_free * c_star / (r_gas * t_c * a_t)
        if not np.isfinite(tau_s) or tau_s <= 0.0:
            return None
        return float(tau_s * 1000.0)

    def _two_phase_loss_report(self, throat_diameter_m):
        """İki-fazlı (tanecik gecikmesi) Isp kaybı — hrma.analysis.two_phase_loss.

        KATI MOTORUN KENDİ FİZİĞİ. Alüminyumlu APCP'de yanma ürünlerinin
        önemli bir kısmı yoğuşmuş faz (sıvı Al2O3) olarak lüleden geçer;
        tanecikler gazın hem hızına hem sıcaklığına yetişemediği için teslim
        edilen Isp düşer. Modül bu kaybı yayımlanmış bağıntılarla kestirir ve
        girdileri yayımlanmış veri penceresinin dışına çıkarsa SAYI ÜRETMEZ.

        GİRDİLERİN TAMAMI ÇÖZÜCÜDEN GELİR
        ---------------------------------
          * beta (yoğuşmuş faz kütle kesri): SOLID_CONDENSED_MASS_FRACTION —
            _isp_loss_breakdown ile AYNI kaynak, aynı aile devralma kuralı
            (_family_lookup). Yakıt için kayıt yoksa modül çağrılmaz.
          * Dt: itki eğrisinin boyutlandırdığı GEOMETRİK boğaz çapı (imal
            edilen çap; boğaz akış katsayısı verildiyse A_etkin/Cd).
          * Pc: tasarım kamara basıncı (self.P_c) — ateşleyici
            boyutlandırması ve _design_throat_area ile aynı değer.
          * tau: _chamber_gas_residence_time_ms (yukarıdaki türetme).
          * gamma, MW: yakıt kaydından — itki katsayısı ve nozul çıkış
            durumu çözümünün kullandığı DEĞERLERİN AYNISI; yalnız kayıt
            ölçülmüş bir donmuş oda gamma'sı taşıyorsa gamma o değerdir
            (``_frozen_gas_gamma``; ÖH KİTAP p1b 2. tur, §28-36 Ş-2 A).
            Bu iki değer (CEA GAMMAs, M(1/n)) yoğuşkan faz dahil KARIŞIM
            değerleridir; çiftten biri kaydınkiyse modülün etkin özellik
            önerisi üretilmez (çift sayma; 3. tur, §28-47 Ş2-2 (a)).

        ÇİFTE SAYIM YASAĞI (uygulama yeri beyanı)
        -----------------------------------------
        Bu blok Isp'ye, c*'a ya da itki katsayısına UYGULANMAZ
        (``applied_to_isp: False``). Gerekçe ölçülebilir: katı motorda
        _total_nozzle_efficiency zaten iki ayrı iki-fazlı çarpan taşıyabilir —
        yakıt kaydının taban nozul verimi ve kullanıcının 'two_phase_loss'
        girdisinden gelen ``two_phase_efficiency``. Modülün kaybını bunların
        üstüne uygulamak kaybı ikinci (kullanıcı çarpanı da varsa üçüncü) kez
        düşürürdü. Blok bu çakışmayı ``overlap_declaration`` alanında adıyla
        raporlar.

        _isp_loss_breakdown'daki ``two_phase_losses`` ile İLİŞKİ: o alan
        doğrusal çapa (eta = 1 - k·X_p) dayanır ve tanecik boyutu/motor
        boyutu düzeltmesi TAŞIMAZ; modül aynı k merkez katsayısını kullanır
        ama üstüne Stokes oranı boyut çarpanını uygular, bu yüzden iki sayı
        genel olarak FARKLIDIR ve ikisi de aynı anda raporlanır. Hangisinin
        neyi ölçtüğü ``relation_to_isp_loss_breakdown`` alanında yazılıdır.
        """
        surum = _hrma_version()
        kunye = ('hrma.analysis.two_phase_loss.TwoPhaseLoss.evaluate '
                 f'(HRMA {surum})')

        # ÖH D15 a3 (P2B1-11): aynı TEK çözüm noktası (iki blok ayrışamaz).
        beta, beta_source, beta_kunye = _condensed_mass_fraction(
            self.propellant_type)
        eksik = []
        if beta is None:
            eksik.append('condensed_mass_fraction')
        d_t = None
        try:
            d_t = float(throat_diameter_m)
        except (TypeError, ValueError):
            d_t = None
        if d_t is None or not np.isfinite(d_t) or d_t <= 0.0:
            eksik.append('throat_diameter')
        p_c = float(self.P_c) if np.isfinite(self.P_c) else None
        if not p_c or p_c <= 0.0:
            eksik.append('chamber_pressure')
        tau_ms = self._chamber_gas_residence_time_ms()
        if tau_ms is None:
            eksik.append('residence_time_ms')

        # ÖH D32 (OH-D31-17): durum beyanı HER dalda taşınır — blok sayı
        # üretmese de "düzeltme doğrulandı mı?" sorusu yanıtsız kalmaz.
        _durum = _two_phase_correction_state(
            beta, getattr(self, 'two_phase_efficiency', 1.0))
        if eksik:
            return {
                'status': 'NOT_MODELLED',
                'missing_inputs': eksik,
                'applied_to_isp': False,
                **_durum,
                'basis': (
                    'The two-phase (particle-lag) Isp loss is NOT evaluated: '
                    f'the solver does not produce {eksik}. No literature or '
                    'default value is substituted, so no loss number is '
                    'reported. ' + kunye),
            }

        from hrma.analysis.two_phase_loss import two_phase_loss as _tpl
        try:
            # ÖH KİTAP p1b (B11, 2. tur; karar §28-36 Ş-2 A): modülün
            # gaz-yalnız gamma'sı cp = γR/(γ−1) DONMUŞ formülüne girer (Sutton
            # Eş. 3-35..3-39). Kaydın denge γ_s'si reaksiyon ısısını ve
            # yoğuşkan fazı zaten içerir; buraya girince karışım cp'si +%27
            # şişiyordu. Seçim Bartz zinciriyle AYNI kural
            # (``_frozen_gas_gamma``); donmuş değeri olmayan itici için dönen
            # nesne self.gamma'nın kendisidir (bit-özdeş).
            gamma_secim = self._frozen_gas_gamma()
            gamma_gas_donmus = gamma_secim is not self.gamma
            gamma_gas = float(gamma_secim)
            # ÖH KİTAP p1b 3. tur (karar §28-47, Ş2-2 (a), fail-closed): CEA
            # donmuş GAMMAs ve M(1/n) yoğuşkan fazı İÇEREN karışım
            # değerleridir; modülün etkin özellik ilişkileri gaz-yalnız çift
            # ister. Çiftin herhangi biri hâlâ CEA karışım kaydınınkiyse
            # (donmuş gamma uygulandı ya da M kaydın M(1/n)'si) yoğuşkan
            # termokimyada zaten vardır: modül etkin özellikleri ÜRETMEZ,
            # gerekçeyi adıyla yazar (çift sayma). Gaz-yalnız alanlar (CEA
            # tür kesirlerinden γ_g, M_g) seçenek (b), v3.1 devri.
            mw_ref = getattr(self, '_mw_frozen_record_ref', None)
            mw_gas_karisim = (mw_ref is not None
                              and self._matches_record_value(
                                  self.mw_exhaust, mw_ref))
            # V301/N-CEA-2 (K3): termokimya CEA'dansa modüle GERÇEK gaz-yalnız
            # M girer: (1 − x_c)·M(1/n), CEA oda tür kütle kesirlerinden.
            mw_gaz = float(self.mw_exhaust)
            if (self._cea_active()
                    and getattr(self, 'mw_gas_only', None) is not None):
                mw_gaz = float(self.mw_gas_only)
                mw_gas_karisim = False
            yogusuk_termokimyada = bool(gamma_gas_donmus or mw_gas_karisim)
            sonuc = _tpl.evaluate(
                condensed_mass_fraction=float(beta),
                throat_diameter=float(d_t),
                chamber_pressure=float(p_c),
                residence_time_ms=float(tau_ms),
                gamma_gas=gamma_gas,
                molecular_weight_gas=mw_gaz,
                condensed_phase_in_thermochemistry=yogusuk_termokimyada)
        except Exception as exc:
            return {
                'status': 'NOT_MODELLED',
                'missing_inputs': [],
                'applied_to_isp': False,
                **_durum,
                'basis': ('The two-phase loss module rejected the solver '
                          f'state: {exc}. No loss number is reported. '
                          + kunye),
            }

        devralma = ('' if beta_source == str(self.propellant_type or ''
                                             ).strip().lower()
                    else f" (inherited from '{beta_source}' of the same "
                         "propellant family)")
        blok = dict(sonuc)
        modul_basis = blok.pop('_basis', None)
        blok.update({
            'status': ('computed' if sonuc.get('valid')
                       else 'OUT_OF_PUBLISHED_RANGE'),
            'applied_to_isp': False,
            **_durum,
            'inputs_used': {
                'condensed_mass_fraction': float(beta),
                'condensed_mass_fraction_source': beta_kunye
                    + devralma,
                'throat_diameter_m': float(d_t),
                'throat_diameter_source': (
                    'geometric throat diameter sized by the thrust-curve '
                    'solver (_design_throat_area, divided by the throat '
                    'discharge coefficient when one was supplied)'),
                'chamber_pressure_bar': float(p_c),
                'chamber_pressure_source': (
                    'design chamber pressure self.P_c — the same value '
                    '_design_throat_area and the igniter sizing use'),
                'residence_time_ms': float(tau_ms),
                'residence_time_source': (
                    'tau = V_free*c*/(R*T_c*A_t), derived from the solver '
                    'quantities only (see _chamber_gas_residence_time_ms)'),
                'gamma': gamma_gas,
                'molecular_weight_g_mol': mw_gaz,
                'molecular_weight_gas_source': (
                    'NASA CEA gas-only molecular weight (1 - x_c) * M(1/n) at '
                    'this chamber pressure (V301/N-CEA-2 K3)'
                    if mw_gaz != float(self.mw_exhaust) else
                    'mw_exhaust (see gas_property_source)'),
                'gas_property_source': (
                    'propellant record (NASA CEA mixture): gamma is the '
                    'record\'s frozen-composition chamber GAMMAs (field '
                    'gamma_frozen_chamber), the same gamma the Bartz gas '
                    'properties use; the equilibrium gamma_s of the thrust '
                    'coefficient already contains the heat of reaction and '
                    'would inflate cp = gamma*R/(gamma-1). Exhaust molecular '
                    'weight is the record\'s M(1/n), the one the thrust '
                    'coefficient and the nozzle exit state use. Both are '
                    'MIXTURE values that already contain the condensed '
                    'phase, so the effective-property relations are not '
                    'evaluated (double counting; see '
                    'effective_properties.reason_code)'
                    if gamma_gas_donmus else
                    'gamma: the engine gamma as entered (the record\'s frozen '
                    'value does not apply to an overridden gamma); exhaust '
                    'molecular weight: the propellant record\'s NASA CEA '
                    'M(1/n), the one the thrust coefficient and the nozzle '
                    'exit state use - a MIXTURE value that already contains '
                    'the condensed phase, so the effective-property '
                    'relations are not evaluated (double counting; see '
                    'effective_properties.reason_code)'
                    if mw_gas_karisim else
                    'propellant record — the same gamma and exhaust '
                    'molecular weight the thrust coefficient and the nozzle '
                    'exit state use'),
            },
            # ÖH D32 (OH-D31-17): eski metin, çifte sayım riskini yakıt
            # kaydının TABAN nozul verimine de yüklüyordu ("already carries a
            # nozzle efficiency ... would count the same physics a second
            # time"). ÖLÇÜLDÜ (once.json Z3): APCP tablo verimi eta = 0,985,
            # referans koni lambda(15 derece) = 0,982963; sürtünmeye kalan
            # artık -%0,2072, yani NEGATİF. Taban verim referans koniyi bile
            # çarpan olarak İÇEREMEZ, bir de iki-faz kaybını içeremez;
            # katalog yorumu da o veriMi "Divergence + friction losses" diye
            # tanımlar. Gerçek çifte sayım kanalı YALNIZ kullanıcı
            # çarpanıdır. Künye artık kendi sayısını yazar.
            'overlap_declaration': (
                'This loss is NOT applied to Isp, c* or the thrust '
                'coefficient. The only channel that could double-count it is '
                "the user's 'two_phase_loss' input, which becomes the "
                'two_phase_efficiency multiplier inside '
                '_total_nozzle_efficiency; its value at this run is '
                f'{float(getattr(self, "two_phase_efficiency", 1.0)):.4f} '
                '(1.0000 means the user applied no two-phase correction at '
                "all). The propellant record's own nozzle efficiency is NOT "
                'claimed to contain a two-phase factor: the catalog defines '
                'it as divergence + friction, and it is measurably too high '
                'to contain even the reference divergence cone as a factor '
                '(see divergence_losses_basis, which publishes the residual '
                'this run).'),
            'relation_to_isp_loss_breakdown': (
                "detailed_analysis.theoretical_vs_actual_isp.two_phase_losses "
                'is the LINEAR anchor 100*k*X_p with no particle-size or '
                'motor-size correction; the number here comes from the same '
                'k anchor multiplied by the Stokes-ratio size factor of the '
                'module, so the two generally differ. Both are reported and '
                'neither is applied.'),
            'module_basis': modul_basis,
            '_basis': (
                f'{kunye}; inputs taken from the solver state listed in '
                'inputs_used. Diagnostic only — not fed back into any '
                'performance, geometry or CAD quantity.'),
        })
        return blok

    def _acoustic_mode_report(self):
        """Kamara akustik modları — hrma.analysis.acoustic_modes.

        Katı motorun gaz kavitesi rijit cidarlı bir rezonatördür; modül bu
        kavitenin öz-frekanslarını (boyuna/teğetsel/radyal) verir. Sonuç bir
        REZONANS ADAYI listesidir: yanmanın bu modları sürükleyip
        sürüklemeyeceği modellenmez (modülün kendi
        ``not_modelled.combustion_response`` beyanı).

        EŞDEĞER KAVİTE (beyanlı idealleştirme)
        --------------------------------------
        Modül düz silindir ister; katı motorun gerçek kavitesi kademelidir
        (grain portu + ön/arka kapak hacimleri). Eşdeğer silindir GERÇEK
        KAVİTE BOYUNU (kasa iç boyu, _case_inner_length) ve GERÇEK SERBEST
        GAZ HACMİNİ (_case_free_volume) korur; kesit alanı bu ikisinden
        türetilir (D_eş = 2·sqrt(V/(pi·L))), yani eşdeğer silindirin hacmi
        gerçek serbest hacme TAM EŞİTTİR. Sonuç olarak boyuna (L) modlar
        gerçek kavite boyuna dayanır — katı motorda baskın kararsızlık
        sınıfı budur; enine (T/R) modlar ise ortalama kesitin göstergesidir
        ve gerçek kademeli kesitte kayar.

        CHUG YOK: katıda enjektör ve besleme sistemi FİZİKSEL OLARAK yoktur,
        dolayısıyla klasik chug marjının (enjektör basınç düşümü oranıyla
        besleme dekuplajı) katı motorda bir karşılığı yoktur. Modüle hiçbir
        enjektör girdisi geçilmez; chug raporu bu yüzden veri eksikliğinden
        DEĞİL, yapısal olarak NOT_EVALUATED kalır ve bu ayrım
        ``chug_applicability`` alanında beyan edilir.

        ATEŞLEME DURUMU: kavite grain geriledikçe büyür; burada yalnız t=0
        (ateşleme) kavitesi çözülür, çünkü serbest hacim ve kasa iç boyu
        çözücüde yalnız bu durum için doğrudan bilinir.
        """
        surum = _hrma_version()
        kunye = ('hrma.analysis.acoustic_modes.AcousticModeAnalyzer.analyze '
                 f'(HRMA {surum})')

        eksik = []
        try:
            t_c = float(self.T_c)
            gam = float(self.gamma)
            mw = float(getattr(self, 'mw_exhaust', 0.0) or 0.0)
            v_free = float(self._case_free_volume())
            l_cav = float(self._case_inner_length())
        except Exception:
            t_c = gam = mw = v_free = l_cav = 0.0
        if not (t_c > 0):
            eksik.append('chamber_temperature')
        if not (gam > 1.0):
            eksik.append('gamma')
        if not (mw > 0):
            eksik.append('molecular_weight')
        if not (v_free > 0):
            eksik.append('case_free_volume')
        if not (l_cav > 0):
            eksik.append('case_inner_length')

        if eksik:
            return {
                'status': 'NOT_MODELLED',
                'missing_inputs': eksik,
                'basis': ('The chamber acoustic mode table is NOT evaluated: '
                          f'the solver does not produce {eksik}. No cavity '
                          'geometry or gas state is assumed. ' + kunye),
            }

        r_gas = R_UNIVERSAL / mw                      # J/(kg·K)
        d_eq = 2.0 * np.sqrt(v_free / (np.pi * l_cav))

        from hrma.analysis.acoustic_modes import AcousticModeAnalyzer
        try:
            sonuc = AcousticModeAnalyzer().analyze(
                chamber_temperature=t_c,
                gamma=gam,
                gas_constant=float(r_gas),
                chamber_diameter=float(d_eq),
                chamber_length=l_cav,
                chamber_pressure=float(self.P_c),
                # Enjektör girdisi YOK: katıda enjektör yoktur.
                n_modes=10)
        except Exception as exc:
            return {
                'status': 'NOT_MODELLED',
                'missing_inputs': [],
                'basis': ('The acoustic mode module rejected the solver '
                          f'state: {exc}. No mode table is reported. '
                          + kunye),
            }

        blok = dict(sonuc)
        # --- ÖH D26 a2 (OH-D25-03): AYNI AD, BAŞKA BÜYÜKLÜK ---------------
        # Modül girdi yankısını 'chamber_diameter' diye basıyor; oysa buraya
        # geçirilen sayı motorun oda çapı DEĞİL, hacmi ve boyu korunarak
        # türetilen EŞDEĞER silindirin çapıdır (d_eq = 2*sqrt(V/(pi*L))).
        # Ölçüldü: aynı yanıtta üst düzey chamber_diameter 101,718 mm iken
        # bu yaprak 0,0667 m yazıyordu. Yaprak burada kendi adına
        # kavuşturulur; sayı DEĞİŞMEZ, yalnız adı gerçeği söyler.
        _girdiler = blok.get('inputs')
        if isinstance(_girdiler, dict) and 'chamber_diameter' in _girdiler:
            _girdiler = dict(_girdiler)
            _girdiler['equivalent_cavity_diameter_m'] = _girdiler.pop(
                'chamber_diameter')
            _girdiler['equivalent_cavity_diameter_basis'] = (
                'NOT the motor chamber diameter: the volume- and '
                'length-preserving equivalent cylinder diameter '
                'd_eq = 2*sqrt(V_free/(pi*L_cavity)) this block feeds the '
                'acoustic module with (see equivalent_cavity below)')
            blok['inputs'] = _girdiler
        blok.update({
            'status': 'computed',
            'cavity_state': 'ignition',
            'equivalent_cavity': {
                'length_m': float(l_cav),
                'diameter_m': float(d_eq),
                'free_gas_volume_m3': float(v_free),
                'basis': (
                    'Equivalent right cylinder that preserves BOTH the real '
                    'cavity length (case inner length: grain stack + segment '
                    'gaps + closure allowance) and the real free gas volume '
                    '(case interior minus propellant): D_eq = '
                    '2*sqrt(V_free/(pi*L)). The real cavity is stepped (grain '
                    'port plus fore/aft closure volumes), so the longitudinal '
                    'mode frequencies rest on the true length while the '
                    'transverse (tangential/radial) frequencies represent a '
                    'mean cross-section and shift in the real stepped '
                    'cavity.'),
            },
            'cavity_state_basis': (
                'Only the t = 0 (ignition) cavity is analysed. The gas cavity '
                'grows as the grain regresses, so the mode frequencies move '
                'during the burn; the solver publishes the free volume and '
                'the case inner length for this state only, and no burnout '
                'cavity is assumed.'),
            'chug_applicability': {
                'applicable': False,
                'reason': (
                    'A solid motor has no injector and no feed system, so the '
                    'classical chug criterion (injector pressure drop ratio '
                    'decoupling the feed from the chamber) has no counterpart '
                    'here. No injector input is passed to the module: its '
                    'chug report is NOT_EVALUATED by construction, not '
                    'because data is missing. The solid-motor low-frequency '
                    'counterpart (L* / bulk-mode instability) is NOT '
                    'modelled.'),
            },
            'inputs_used': {
                'chamber_temperature_K': t_c,
                'gamma': gam,
                'molecular_weight_g_mol': mw,
                'gas_constant_J_kgK': float(r_gas),
                'chamber_pressure_bar': float(self.P_c),
                'gas_property_source': (
                    'propellant record — the same chamber temperature, gamma '
                    'and exhaust molecular weight the thrust solution uses'),
                'cavity_source': (
                    '_case_inner_length() and _case_free_volume(), the same '
                    'two quantities the reported case length and '
                    'grain_design.case_free_volume_l come from'),
            },
            '_basis': (
                f'{kunye}; cavity idealisation and gas state as listed in '
                'equivalent_cavity and inputs_used. Diagnostic only: the '
                'mode table is a list of CANDIDATE resonances and is not fed '
                'back into any performance or structural result.'),
        })
        return blok

    # ------------------------------------------------------------------
    # F2b-1 — yanma kararlılığı bağlaması (hrma/stability çekirdeği)
    # ------------------------------------------------------------------
    @staticmethod
    def _pure_longitudinal_modes(acoustic_block):
        """Akustik tablodan SAF BOYUNA modlar (m = n = 0, q >= 1).

        Bağlanan iki kapalı form da (Culick & Yang lüle sönümü + basınç
        kuplajlı kazanç) ψ_q = cos(qπz/L) mod şekliyle türetilmiştir; enine
        ve karma modlarda geçerli değildir. O modlara eşik YAZILMAZ,
        gerekçesiyle listelenir.
        """
        modlar = []
        for mod in (acoustic_block.get('modes') or []):
            idx = mod.get('indices') or {}
            if (idx.get('tangential_m') == 0 and idx.get('radial_n') == 0
                    and int(idx.get('longitudinal_q') or 0) >= 1):
                modlar.append(mod)
        return modlar

    def _combustion_stability_block(self, results, curve):
        """Yanma kararlılığı (F2b-1 katı ayağı) — hrma.stability çekirdeği.

        ÜÇ AYAK, FARKLI BİLGİ DURUMLARI (tasarım belgesi §3.0):

          * ``bulk_mode`` — çevrimin KAPANDIĞI yer. Yarı-kararlı yanma hızı
            kuplajı konsantre kamara dengesine konunca kararsızlık ölçütü
            gecikmesiz limitte tam olarak n >= 1'dir; burada HÜKÜM verilir
            (kapsam etiketiyle, çekirdekten olduğu gibi). Bu ölçüt çözücüde
            ZATEN kapılıdır (``warn.solid.burn_rate_exponent_ge_one``) —
            blok o kapıyla TUTARLILIĞINI ölçüp yayımlar; iki yer aynı
            fiziği söyleyip farklı sonuca varamaz.
          * ``acoustic_response_threshold`` — çevrimin kapanMADIĞI yer:
            yanma tepki fonksiyonu ölçülür (T-burner), HRMA'da yok. Yalnız
            EŞİK; 'verdict' anahtarı yapısal olarak yasaktır.
          * ``qshod_response_band`` — KAPILI yol. (A, B) parametre bandı ve
            yakıtın termal yayınırlığı çözücüde YOKTUR (tasarım belgesi
            §1.1-4 bunu ölçtü); ikisi de verilmedikçe blok NOT_EVALUATED
            döner ve eksik girdiyi ADIYLA söyler. Varsayılan (A, B)
            UYDURULMAZ.

        Chug katıda YAPISAL olarak uygulanamaz (enjektör/besleme yok); bu
        beyan ``acoustic_modes.chug_applicability`` içinde zaten duruyor ve
        burada tekrarlanmaz.
        """
        from hrma.stability import STABILITY_NOT_MODELLED

        surum = _hrma_version()
        akustik = results.get('acoustic_modes') or {}
        tau_blok = self._chamber_time_constant_block(curve)
        return {
            'model': 'hrma.stability F2b solid binding',
            '_basis': (
                'Combustion stability binding of the hrma/stability core to '
                'the solid solver (HRMA ' + surum + '). The acoustic mode '
                'table is NOT reproduced here: it stays in the '
                'acoustic_modes block and is read from there. A VERDICT is '
                'issued only where the feedback loop closes from solver '
                'quantities (the zero-lag bulk/L* mode); everywhere else a '
                'THRESHOLD is published instead, because the combustion '
                'response function is measured, not derived, and this solver '
                'does not have that measurement.'),
            'cavity_state': 'ignition',
            'cavity_state_basis': (
                'Every path is evaluated at the t = 0 (ignition) state, the '
                'same state the acoustic_modes block uses: the free gas '
                'volume, the burning surface and the mass flow of the first '
                'thrust-curve sample. The cavity grows as the grain '
                'regresses, so tau_c rises and the damping budget moves '
                'during the burn; no time history is claimed here.'),
            'chamber_time_constant': tau_blok,
            'bulk_mode': self._bulk_mode_block(results, tau_blok),
            'acoustic_response_threshold':
                self._acoustic_response_threshold_block(akustik, curve),
            'qshod_response_band': self._qshod_band_block(akustik, curve),
            'not_modelled': {
                ad: STABILITY_NOT_MODELLED[ad] for ad in (
                    'detailed_flame_dynamics', 'vortex_shedding', 'pogo',
                    'three_dimensional_acoustics', 'damping_devices')
            },
            'not_modelled_basis': (
                'Scope-level declarations carried verbatim from '
                'hrma.stability.STABILITY_NOT_MODELLED. Limits belonging to a '
                'single mechanism (solid-phase thermal lag, nonlinear '
                'triggering, the missing response measurement, the damping '
                'terms outside the budget) are declared INSIDE the sub-block '
                'they belong to and are not repeated here.'),
        }

    def _chamber_time_constant_block(self, curve):
        """Kamara doldurma/boşaltma zaman sabiti τ_c = L*/(c*·Γ²).

        L* = V_serbest/A_t: hacim kasa geometrisinden (_case_free_volume),
        boğaz alanı basınç çözücüsünün KULLANDIĞI etkin alandır
        (``curve['throat_area']``) — kütle dengesi ṁ_çıkış = P·A_t/c*
        o alanla kuruludur, raporlanan geometrik alanla değil (Cd verilmişse
        ikisi ayrışır ve bu fark burada beyanlıdır).
        """
        basis = (
            'tau_c = L*/(c* * Gamma^2) from hrma/stability/chamber.py '
            '(isothermal lumped chamber mass balance; Karabeyoglu, AA284a '
            'Stanford lecture notes, chamber gas dynamic model). L* = '
            'V_free/A_t uses the case free gas volume at ignition and the '
            'EFFECTIVE throat area the pressure solver itself integrates '
            'with (mdot_out = Pc*A_t/c*), not the geometric throat that is '
            'reported for manufacturing; the two differ only when a throat '
            'discharge coefficient is supplied.')
        eksik = []
        try:
            v_free = float(self._case_free_volume())
        except Exception:
            v_free = 0.0
        a_t = float((curve or {}).get('throat_area', 0.0) or 0.0)
        c_star = float(getattr(self, 'c_star', 0.0) or 0.0)
        gamma = float(getattr(self, 'gamma', 0.0) or 0.0)
        if not (v_free > 0):
            eksik.append('case_free_volume')
        if not (a_t > 0):
            eksik.append('throat_area')
        if not (c_star > 0):
            eksik.append('c_star')
        if not (1.0 < gamma < 2.0):
            eksik.append('gamma')
        if eksik:
            return {'status': 'NOT_MODELLED', 'missing_inputs': eksik,
                    '_basis': basis,
                    'reason': ('the chamber time constant is not evaluated '
                               f'and no value is assumed; missing: {eksik}')}
        from hrma.stability import tau_c_from_volume
        try:
            sonuc = dict(tau_c_from_volume(v_free, a_t, c_star, gamma))
        except ValueError as exc:
            return {'status': 'NOT_MODELLED', 'missing_inputs': [],
                    '_basis': basis,
                    'reason': f'the chamber core rejected this state: {exc}'}
        sonuc['status'] = 'modelled'
        sonuc['_basis'] = basis
        sonuc['throat_area_source'] = 'effective (pressure solver) throat area'
        return sonuc

    def _bulk_mode_block(self, results, tau_blok):
        """Katı bulk (L*) modu — gecikmesiz limit + çözücü kapısı çaprazı.

        Çekirdek hükmü OLDUĞU GİBİ taşınır (motorda yeniden hükümleştirme
        yok). Üstüne tek şey eklenir: aynı fiziği çözücünün kendi kritik
        uyarısı (``warn.solid.burn_rate_exponent_ge_one``) da kapılıyor;
        ikisinin AYNI şeyi söylediği ölçülüp yayımlanır. Ayrışırlarsa bu bir
        SAPMADIR ve sessiz kalmaz — bekçisi
        ``tests/test_stability_baglamalar.py`` içindedir.
        """
        basis = (
            'Zero thermal-lag bulk (L*) mode from hrma/stability/chamber.py: '
            'substituting the quasi-steady burning rate law rdot = a*P^n into '
            'the lumped chamber balance gives tau_c d(dP)/dt + (1-n) dP = 0, '
            'so the mode grows if and only if n >= 1 (Beckstead & Price, '
            '"Nonacoustic Combustion Instability", AIAA Journal 5(11), 1967). '
            'The verdict is carried verbatim from the core with its scope '
            'label; the solver already gates the same criterion as a critical '
            'warning, and the agreement between the two is measured and '
            'published here rather than assumed.')
        tau_c = tau_blok.get('tau_c_s') if isinstance(tau_blok, dict) else None
        from hrma.stability import bulk_mode_zero_lag
        try:
            sonuc = dict(bulk_mode_zero_lag(float(self.n), tau_c_s=tau_c))
        except ValueError as exc:
            return {'status': 'NOT_MODELLED', 'missing_inputs': [],
                    '_basis': basis,
                    'reason': f'the bulk-mode core rejected n: {exc}'}
        kod = 'warn.solid.burn_rate_exponent_ge_one'
        uyari_var = any(
            isinstance(k, dict) and k.get('code') == kod
            for k in (results.get('warnings') or []))
        sonuc['status'] = 'modelled'
        sonuc['_basis'] = basis
        sonuc['solver_gate_consistency'] = {
            'warning_code': kod,
            'warning_present': bool(uyari_var),
            'criterion_met': bool(sonuc.get('criterion_met')),
            'consistent': bool(uyari_var) == bool(sonuc.get('criterion_met')),
            # ÖH D15 a3 (P2B2-10): KÜNYE YANLIŞTI. Eski metin "the solver
            # already fails closed for n >= 1 ... it simply never gets
            # published" diyordu; ÖLÇÜLDÜ (APCP, 100/500/30 mm, 40 bar) ki
            # a = 0,0005 & n = 1,30 TAM sonuç yayımlanıyor (64 anahtar,
            # ortalama itki 23524,77 N, verdict 'unstable'), a = 0,005'te ise
            # hem n = 1,05 hem n = 1,30 yayımlanıyor (43394,82 N). Fail-closed
            # yalnız çözücünün YAKINSAMADIĞI bantta (ölçümde
            # a = 0,0005 & n ∈ {1,00; 1,05}) devreye giriyor. Yayımlanan
            # HÜKÜM her koşuda doğruydu; yanlış olan tek şey bu beyandı.
            # Beyan artık gerçeği söylüyor ve iddiası aynı sözlükten
            # doğrulanabilir: 'burn_rate_exponent' ile
            # 'published_with_criterion_met' okuşunun kendisini taşır.
            'burn_rate_exponent': float(self.n),
            'published_with_criterion_met': bool(sonuc.get('criterion_met')),
            'basis': (
                'The solid solver raises the critical warning above exactly '
                'when n >= 1; the stability core reaches the same conclusion '
                'from the lumped chamber pole. The two are cross-checked on '
                'every run: if they ever disagree, one of them has drifted '
                'and this flag says so instead of hiding it. What this block '
                'does NOT claim is that the solver withholds every n >= 1 '
                'motor. The solver gate is a CONVERGENCE gate, not an '
                'exponent gate: the damped fixed-point pressure iteration '
                'fails to converge in a band around n = 1 and the run then '
                'returns an error with no performance result, but outside '
                'that band an n >= 1 motor does converge and IS published, '
                'carrying the critical warning and the "unstable" verdict '
                "with it. Read 'published_with_criterion_met': where it is "
                'true, this very result is such a run. Measured (APCP, '
                'D_chamber = 100 mm, D_core = 30 mm, L = 500 mm, 40 bar): '
                'a = 0.0005 with n = 1.30 publishes a full result at '
                '23524.77 N mean thrust, while the same a with n = 1.05 and '
                'n = 1.00 fail closed; at a = 0.005 both n = 1.05 and '
                'n = 1.30 publish. The verdict is computed from n rather '
                'than asserted, and it was correct in every one of those '
                'runs - what was wrong was this note.'),
        }
        if tau_c is None:
            sonuc['growth_rate_basis'] = (
                'The growth rate (n-1)/tau_c is not reported because the '
                'chamber time constant could not be formed on this run; the '
                'criterion itself does not need it.')
        else:
            sonuc['growth_rate_basis'] = (
                'Growth rate (n-1)/tau_c [1/s] of the lumped chamber pole, '
                'with tau_c from the chamber_time_constant block of this run '
                '(single source; it is not recomputed here).')
        return sonuc

    def _acoustic_response_threshold_block(self, akustik, curve):
        """Mod başına KRİTİK YANMA TEPKİSİ eşiği R_crit (HÜKÜM YOK).

        Kazanç tarafı ters çevrilir: "bu mod nötr olsun diye basınç kuplajlı
        yanma tepkisi NE KADAR olmalıydı?". Büyüklükler bu koşunun kendi
        çözümünden gelir:

          * ā ve mod tablosu: acoustic_modes bloğu (ikinci tablo üretilmez),
          * eşdeğer kavite: aynı bloğun BEYAN ETTİĞİ silindir (boy + serbest
            hacim korunur), yani mod şekli normalizasyonu S_c·L/2 ile
            yayımlanan modlar aynı kaviteye oturur,
          * ρ_c = P_c/(R·T_c), R = R_evrensel/MW_egzoz — akustik bloğun
            kullandığı AYNI gaz kaydı,
          * M_N = ṁ/(ρ_c·ā·S_c) ve M_b = ṁ/(ρ_c·ā·S_b): ikisi de kütle-akısı
            oranıdır (Culick'in M_N = M_b·S_b/S_c tanımı). Katıda tüm kütle
            yanan yüzeyden girdiği için ikisinde de AYNI ṁ kullanılır —
            hibritten farkı budur (orada oksitleyici baş taraftan girer).

        ⟨ψ²⟩ = 1/2 alınır ve bu bir varsayılan DEĞİL, beyanlı bir
        idealleştirmedir: yanan yüzeyin kavite ekseni boyunca dağılımı
        (grain yığınının kasa içindeki konumu, segman uç yüzeylerinin
        eksenel yeri) çözücüde yayımlanmıyor, bu yüzden yüzey eşdeğer
        kavitenin TAMAMINA düzgün yayılmış sayılır — o hâlde cos²'nin tam
        ortalaması 1/2'dir (matematiksel özdeşlik, uydurma sayı değil).
        """
        basis = (
            'Per-mode critical combustion response threshold R_crit: the '
            'quasi-steady short-nozzle damping of Culick & Yang (AIAA '
            'Progress in Astronautics and Aeronautics Vol. 143, 1990, '
            'Eq. 100) is inverted against their pressure-coupled driving gain '
            '(Eq. 99), giving the response the combustion WOULD have to '
            'deliver for the mode to be neutral. It is a threshold, never a '
            'verdict: HRMA does not measure the response function (design doc '
            'section 3.0), so no verdict key exists anywhere on this path '
            '(structurally enforced by hrma.stability.forbid_verdict_key). '
            'Particle (condensed phase) damping is NOT in the budget even '
            'though this motor may carry aluminium: the core has no particle '
            'term yet, and every missing loss biases the threshold LOW '
            '(pessimistic).')
        eksik = []
        if (akustik or {}).get('status') != 'computed':
            eksik.append('acoustic_modes (mode table and sound speed)')
        kavite = (akustik or {}).get('equivalent_cavity') or {}
        a_ses = float((akustik or {}).get('sound_speed_m_s') or 0.0)
        l_kavite = float(kavite.get('length_m') or 0.0)
        v_free = float(kavite.get('free_gas_volume_m3') or 0.0)
        gamma = float(getattr(self, 'gamma', 0.0) or 0.0)
        mw = float(getattr(self, 'mw_exhaust', 0.0) or 0.0)
        t_c = float(getattr(self, 'T_c', 0.0) or 0.0)
        p_c = float(getattr(self, 'P_c', 0.0) or 0.0)
        yuzeyler = np.asarray((curve or {}).get('burn_area', []), dtype=float)
        debiler = np.asarray((curve or {}).get('mass_flow', []), dtype=float)
        s_b = float(yuzeyler[0]) if yuzeyler.size else 0.0
        mdot = float(debiler[0]) if debiler.size else 0.0
        for ad, deger in (('sound_speed', a_ses), ('cavity_length', l_kavite),
                          ('free_gas_volume', v_free), ('gamma', gamma),
                          ('molecular_weight', mw),
                          ('chamber_temperature', t_c),
                          ('chamber_pressure', p_c),
                          ('burn_area', s_b), ('mass_flow', mdot)):
            if not (deger > 0):
                eksik.append(ad)
        if eksik:
            return {'status': 'NOT_MODELLED', 'missing_inputs': eksik,
                    '_basis': basis,
                    'reason': ('no damping budget and no critical response '
                               'threshold are reported; missing solver '
                               f'output(s): {eksik}')}

        from hrma.stability import (
            critical_response_real,
            damping_budget,
            forbid_verdict_key,
            nozzle_damping_quasi_steady,
            response_gain_uniform_chamber,
        )
        from hrma.stability.damping import DAMPING_NOT_MODELLED

        r_gaz = R_UNIVERSAL / mw
        rho_c = p_c * 1e5 / (r_gaz * t_c)
        s_c = v_free / l_kavite          # eşdeğer silindirin kesiti (= piD²/4)
        mach_n = mdot / (rho_c * a_ses * s_c)
        mach_b = mdot / (rho_c * a_ses * s_b)
        try:
            lule = nozzle_damping_quasi_steady(a_ses, l_kavite, gamma, mach_n)
            butce = damping_budget([lule])
        except ValueError as exc:
            return {'status': 'NOT_MODELLED', 'missing_inputs': [],
                    '_basis': basis,
                    'reason': (f'the damping core rejected this chamber '
                               f'state: {exc}')}

        boyuna = self._pure_longitudinal_modes(akustik)
        boyuna_etiketleri = {mod.get('label') for mod in boyuna}
        satirlar = []
        atlanan = []
        esik_beyanlari = {}
        for mod in boyuna:
            try:
                kazanc = response_gain_uniform_chamber(
                    a_ses, l_kavite, s_b, s_c, mach_b, gamma)
                satir = critical_response_real(butce['total_damping_1_s'],
                                               kazanc['gain_1_s'])
            except ValueError as exc:
                atlanan.append({'label': mod.get('label'),
                                'reason': f'the response core refused: {exc}'})
                continue
            # Uzun beyanlar blok düzeyinde TEK KEZ (metin kaybolmaz).
            esik_beyanlari.update(satir.pop('not_modelled', None) or {})
            satir.pop('interpretation_basis', None)
            satir['label'] = mod.get('label')
            satir['frequency_hz'] = float(mod.get('frequency_hz'))
            satir['mode_shape_mean_square'] = float(
                kazanc['mode_shape_mean_square'])
            satir['damping'] = dict(butce['terms'])
            satirlar.append(satir)

        if not satirlar:
            # "NOT_MODELLED ama sayılar var" hâli tutarsızdır: tek satır bile
            # kurulamadıysa blok sayı taşımaz.
            return {
                'status': 'NOT_MODELLED',
                'missing_inputs': [],
                '_basis': basis,
                'reason': ('no longitudinal mode produced a usable threshold '
                           f'on this run: {atlanan}'),
            }
        blok = {
            'status': 'modelled',
            '_basis': basis,
            'model': 'nozzle_damping_budget_inverted_to_critical_response',
            'interpretation': 'threshold_not_verdict',
            'interpretation_basis': (
                'R_crit is the response the combustion WOULD have to deliver '
                'for the mode to be neutral — a comparison yardstick, never a '
                'stability verdict.'),
            'sound_speed_m_s': a_ses,
            'chamber_gas_density_kg_m3': float(rho_c),
            'acoustic_cavity_area_m2': float(s_c),
            'burning_surface_area_m2': float(s_b),
            'mass_flow_kg_s': float(mdot),
            'mean_flow_mach_M_N': float(mach_n),
            'surface_mach_M_b': float(mach_b),
            'mach_basis': (
                'M_N = mdot/(rho_c*a*S_c) and M_b = mdot/(rho_c*a*S_b) are '
                'mass-flux ratios, exactly as Culick & Yang define them '
                '(their M_N = M_b*S_b/S_c). In a solid motor the whole mass '
                'flow enters through the burning surface, so both use the '
                'same mdot. S_c is the cross-section of the equivalent '
                'cylinder the mode table is built on (free gas volume divided '
                'by cavity length), because the mode-shape normalisation '
                'E_n^2 = S_c*L/2 must match the published modes. The '
                'quasi-steady short-nozzle limit assumes a SMALL mean-flow '
                'Mach number; M_N is published so that assumption can be '
                'checked against this motor (a smeared cavity of a heavily '
                'loaded grain can push it far from small). It cancels out of '
                'R_crit — it divides both the damping and the gain — but not '
                'out of the individual alpha and gain values printed here.'),
            'mode_shape_basis': (
                'The burning surface is treated as uniformly distributed '
                'along the equivalent cavity, so the mean square of '
                'cos(q*pi*z/L) over it is exactly 1/2 for every mode. This is '
                'a DECLARED idealisation, not a default: the axial position '
                'of the grain stack inside the case and the axial location of '
                'the segment end faces are not published by this solver, so '
                'no window average can be formed from solved geometry. With a '
                'real axial distribution the mean square differs per mode and '
                'R_crit moves with it.'),
            'damping': {
                'terms': dict(butce['terms']),
                'total_damping_1_s': butce['total_damping_1_s'],
                'total_loss_1_s': butce['total_loss_1_s'],
                'sign_convention': butce['sign_convention'],
                'bias_basis': butce['bias_basis'],
                'nozzle_term': {
                    'damping_1_s': lule['damping_1_s'],
                    'admittance_real': lule['admittance_real'],
                    'basis': lule['basis'],
                },
                'not_modelled': dict(DAMPING_NOT_MODELLED),
            },
            'modes': satirlar,
            'modes_not_evaluated': atlanan,
            'transverse_modes_not_evaluated': [
                mod.get('label') for mod in ((akustik or {}).get('modes') or [])
                if mod.get('label') not in boyuna_etiketleri],
            'transverse_modes_basis': (
                'Only pure longitudinal modes carry a threshold: both closed '
                'forms bound here are derived for psi = cos(q*pi*z/L). For '
                'tangential/radial modes neither the nozzle admittance '
                'integral nor the surface mean square holds, and no number is '
                'fabricated for them.'),
            'not_modelled': esik_beyanlari,
        }
        return forbid_verdict_key(
            blok, 'solid combustion_stability.acoustic_response_threshold')

    def _stability_table_keys(self):
        """Kararlılık tablolarında (bands / fuel_thermal) denenecek anahtarlar.

        ÖH D22 (defter P6B4-08). Bu iki tablo ``hrma/data/propellant_
        database.py`` ANAHTAR uzayına göre yazılmıştır (``FAMILY_BANDS``
        anahtarları apcp / pban / kndx / knsu; ``FUEL_THERMAL_RECORDS``
        satırları paraffin / htpb / apcp / ...). Motorun kendi
        ``propellant_type``ı çoğu zaman aynı anahtardır; ``_catalog_key_for``
        ise BAŞKA bir katalogun (``hrma/data/propellants_db.py``) anahtarını
        döndürür ve ikisi her zaman örtüşmez — ölçüldü: ``'apcp'`` motor
        anahtarı ``'htpb_ap_al'``a eşleniyor, oysa bant tablosunda satırın
        adı ``'apcp'``.

        Bu yüzden arama SIRALIDIR ve sıra yayımlanır (``keys_tried`` /
        ``matched_key``): önce motorun kendi anahtarı, sonra merkezi katalog
        anahtarı. Sessiz eşleme yoktur; hangi satırın cevap verdiği künyede
        adıyla durur.
        """
        adaylar = []
        for aday in (str(self.propellant_type or '').strip().lower(),
                     _catalog_key_for(self.propellant_type)):
            if aday and aday not in adaylar:
                adaylar.append(aday)
        return adaylar

    @staticmethod
    def _sayisiz_kunye(kunye):
        """Künyenin SAYISIZ kopyası — kapalı kapıdan sayı sızmaz.

        ÖH D22 (defter P6B4-08). Bant ve termal tablo künyeleri artık ürün
        yanıtına giriyor; ama QSHOD bloğu HÜKÜM VERMEDİĞİNDE (girdilerden
        biri eksik) o künyenin sayısal içeriği — bandın (A, B) aralıkları,
        zarf basınç/sıcaklıkları, yoğunluk — yayımlanmaz. Gerekçe
        ``tests/test_stability_baglamalar.py::
        test_kati_qshod_kapisi_kapali_ve_VARSAYILAN_YOK``ın koruduğu
        kuraldır ve kural DOĞRUDUR: değerlendirilmemiş bir kapıdan çıkan
        sayı, okuyucu tarafından sonuç sanılır. Kaynağın KİMLİĞİ (kayıt
        adı, atıf, güven notu, sınıf eşleşme beyanı, satırın neden boş
        olduğu) metindir ve olduğu gibi geçer — kullanıcı "hesaplanamadı"
        ile "ölçülmüş veri yok" arasındaki farkı bu metinlerden görür.

        Sayısal yapraklar (bool hariç) düşürülür; düşürüldüğü de
        ``numeric_fields_withheld`` ile beyan edilir.
        """
        def _sil(dugum):
            if isinstance(dugum, dict):
                return {k: _sil(v) for k, v in dugum.items()
                        if not isinstance(v, (int, float))
                        or isinstance(v, bool)}
            if isinstance(dugum, (list, tuple)):
                return [_sil(v) for v in dugum
                        if not isinstance(v, (int, float))
                        or isinstance(v, bool)]
            return dugum

        if not isinstance(kunye, dict):
            return kunye
        kisa = _sil(kunye)
        kisa['numeric_fields_withheld'] = True
        kisa['numeric_fields_withheld_basis'] = (
            'This block reports no verdict, so no number from the source '
            'record is published with it: an unevaluated gate must not emit '
            'figures that could be read as a result. The identity of the '
            'source (record id, citation, confidence note, class-match '
            'declaration, and the reason an empty row is empty) is text and '
            'is carried in full. Supply the missing input(s) and the same '
            'record is published with its numbers alongside the evaluated '
            'response.')
        return kisa

    @staticmethod
    def _qshod_record_for_band(band):
        """Yayımlanan bandın SAHİBİ katalog kaydı (yoksa ``None``).

        ÖH D27 a2 (defter P13B4-03). Kaydın künye zarfı — ``record_id``,
        ``record_confidence``, ``record_confidence_note``, ``retrieved`` —
        bandın hangi kanaldan geldiğine bakmaksızın yayımlanabilmelidir:
        güven derecesi BANDIN özelliğidir, taşındığı yolun değil.

        Eşleşme yalnız KİMLİKLE (``is``) kurulur, değer benzerliğiyle
        DEĞİL: iki farklı kaydın sayısal olarak çakışan bantları olsaydı
        değer eşitliği yanlış bir künye iliştirebilirdi. Kimlik eşleşmesi
        yanlış pozitif üretemez; eşleşme yoksa künye UYDURULMAZ, anahtar
        hiç yazılmaz (Doktrin 1).
        """
        if band is None:
            return None
        try:
            from hrma.stability.bands import (QSHOD_BAND_RECORDS,
                                              QSHODBandRecord)
        except Exception:  # pragma: no cover - modül yükleme kazası
            return None
        for kayit in QSHOD_BAND_RECORDS.values():
            if isinstance(kayit, QSHODBandRecord) and kayit.band is band:
                return kayit
        return None

    def _qshod_band_from_catalog(self):
        """Yakıtın katalog ailesinden QSHOD (A, B) bandı + künyesi.

        ÖH D22 (defter P6B4-08). ÖLÇÜLDÜ (taban ``b84b10a``,
        ``docs/scofield/raw/OH/D22/kati/a1/once.json`` bölüm K3):
        ``hrma/stability/bands.py`` (384 satır) ve
        ``hrma/stability/fuel_thermal.py`` (531 satır) — toplam 915 satır
        künyeli tablo — ürün kodundan HİÇ çağrılmıyordu; sekiz gönderme
        hedefinin (``bands_for_family``, ``QSHOD_BAND_RECORDS``,
        ``FAMILY_BANDS``, ``FUEL_THERMAL_RECORDS``, ...) ürün tarafındaki
        dosya listesi BOŞTU. ``combustion_response_band`` yalnız
        testlerden atanıyordu, dolayısıyla katı motorun ``qshod_band``
        bloğu HER koşuda ``NOT_EVALUATED`` dönüyordu.

        Bu metot o kapının BİRİNCİ anahtarını ürüne bağlar: bant, motorun
        yakıtının merkezi katalog AİLESİNDEN okunur. Yeni bir sayı
        üretilmez, ikinci bir tablo kurulmaz — ``bands_for_family``ın
        kendi kaydı ve kendi EŞLEŞME BEYANI (``mapping_basis``; sınıf
        uyuşmazlıkları orada açıkça yazılıdır) olduğu gibi taşınır.

        FAIL-CLOSED üç yerde:
          * yakıt bir katalog ailesine çözülemezse -> bant YOK,
          * aile bantlar tablosunda tanımlı değilse (``ValueError``) ->
            bant YOK, hatanın metni künyeye yazılır,
          * aile tabloda var ama satırı BOŞSA (kndx/knsu: kaynak arandı,
            bulunamadı) -> bant YOK ve kaydın KENDİ gerekçesi yayımlanır.

        Returns:
            ``(band | None, künye sözlüğü)``.
        """
        adaylar = self._stability_table_keys()
        kunye = {
            'source': 'hrma.stability.bands.FAMILY_BANDS',
            'propellant_type': self.propellant_type,
            'keys_tried': adaylar,
            'basis': (
                'The (A, B) response band is not solved for: it is a MEASURED '
                'propellant property. It is read from the repository band '
                'table (hrma/stability/bands.py, QSHOD_BAND_RECORDS) through '
                'the propellant mapping FAMILY_BANDS, whose keys are '
                'propellant_database keys. The engine propellant key is tried '
                'first and the central catalog key second; keys_tried lists '
                'the order and matched_key names the row that answered. Every '
                'record carries its own validity envelope, record-level '
                'confidence and source, and the mapping carries its own '
                'class-match declaration (mapping_basis). Nothing is '
                'defaulted: a propellant with no verified source yields no '
                'band.'),
        }
        if not adaylar:
            kunye['status'] = 'no_catalog_key'
            kunye['reason'] = (
                f'propellant {self.propellant_type!r} does not resolve to any '
                'lookup key, so no band table row can be looked up for it')
            return None, kunye
        try:
            from hrma.stability.bands import bands_for_family
        except Exception as exc:  # pragma: no cover - modül yükleme kazası
            kunye['status'] = 'band_table_unavailable'
            kunye['reason'] = repr(exc)
            return None, kunye
        kayit, aile, red = None, None, None
        for aday in adaylar:
            try:
                kayit, aile = bands_for_family(aday), aday
                break
            except ValueError as exc:
                red = red or str(exc)
        if kayit is None:
            kunye['status'] = 'key_not_in_band_table'
            kunye['reason'] = red
            return None, kunye
        kunye['matched_key'] = aile

        kunye['mapping_basis'] = kayit['mapping_basis']
        kayitlar = kayit['records']
        if not kayitlar:
            kunye['status'] = 'declared_empty'
            kunye['missing_record'] = (kayit['missing'].as_dict()
                                       if kayit['missing'] is not None
                                       else None)
            kunye['reason'] = (
                f'the band table publishes NO verified (A, B) record for the '
                f'{aile!r} propellant; the row is empty by declaration, not '
                'by omission')
            return None, kunye

        secilen = kayitlar[0]
        kunye['status'] = 'resolved'
        kunye['record'] = secilen.as_dict()
        kunye['records_available'] = [r.record_id for r in kayitlar]
        if len(kayitlar) > 1:
            kunye['record_selection_basis'] = (
                'the first record of the family mapping is used; the other '
                'record ids are listed in records_available')
        return secilen.band, kunye

    def _propellant_thermal_diffusivity(self):
        """Yakıtın termal yayınırlığı κ = k/(ρ·c_p) + künyesi.

        ÖH D22 (defter P6B4-08) — QSHOD kapısının İKİNCİ anahtarı ve
        ``hrma/stability/fuel_thermal.py``ın ürün tüketicisi.

        κ, k ve c_p'den TÜRETİLİR; ikisi de ÖLÇÜLEN yakıt özellikleridir ve
        bu çözücü hiçbirini üretmez. Depoda tek künyeli kaynak
        ``FUEL_THERMAL_RECORDS``tir: her alan ya kaynağını + referans
        sıcaklığını + fazını taşır (``ThermalProperty``) ya da NEDEN boş
        olduğunu beyan eder (``MissingProperty``; sınıf ``__slots__``
        gereği sayı taşıyamaz).

        ÖLÇÜLDÜ (once.json K3): bugün hiçbir KATI yakıt ailesinin (apcp,
        kndx, knsu, pban, htpb) iki alanı da dolu değildir — tek dolu satır
        parafinin SIVI faz değerleridir (hibrit yakıtı). Dolayısıyla κ
        bugün katı rotasında çözülmez; UYDURULMAZ da. Eksik alanın kendi
        beyanı (ne arandı, neden taşınmadı) yanıtta yayımlanır, böylece
        kullanıcı "hesaplanamadı" ile "veri yok" arasındaki farkı görür.

        Returns:
            ``(kappa m²/s | None, künye sözlüğü)``.
        """
        adaylar = self._stability_table_keys()
        rho = float(getattr(self, 'rho_p', 0.0) or 0.0)
        kunye = {
            'source': 'hrma.stability.fuel_thermal.FUEL_THERMAL_RECORDS',
            'propellant_type': self.propellant_type,
            'keys_tried': adaylar,
            'density_kg_m3': (rho if rho > 0 else None),
            'basis': (
                'kappa = k / (rho * c_p). The solver produces neither the '
                'thermal conductivity k nor the specific heat c_p of the '
                'propellant; they are measured properties. The only '
                'field-level cited table in this repository is '
                'hrma/stability/fuel_thermal.py, where each entry either '
                'carries its source, phase and reference temperature or '
                'declares WHY it is empty. Density is the solver\'s own '
                'propellant density. If either property is undeclared, no '
                'kappa is produced and none is assumed.'),
        }
        if not adaylar:
            kunye['status'] = 'no_catalog_key'
            kunye['reason'] = (
                f'propellant {self.propellant_type!r} does not resolve to any '
                'lookup key, so no thermal-property row can be looked up')
            return None, kunye
        try:
            from hrma.stability.fuel_thermal import (FUEL_THERMAL_RECORDS,
                                                     ThermalProperty)
        except Exception as exc:  # pragma: no cover - modül yükleme kazası
            kunye['status'] = 'thermal_table_unavailable'
            kunye['reason'] = repr(exc)
            return None, kunye

        kayit, aile = None, None
        for aday in adaylar:
            if aday in FUEL_THERMAL_RECORDS:
                kayit, aile = FUEL_THERMAL_RECORDS[aday], aday
                break
        if kayit is None:
            kunye['status'] = 'key_not_in_thermal_table'
            kunye['reason'] = (
                f'the cited thermal-property table has no row for any of '
                f'{adaylar}; known rows: {sorted(FUEL_THERMAL_RECORDS)}')
            return None, kunye

        kunye['matched_key'] = aile
        kunye['record'] = kayit.as_dict()
        eksik = [ad for ad in ('specific_heat', 'thermal_conductivity')
                 if not isinstance(getattr(kayit, ad), ThermalProperty)]
        if eksik:
            kunye['status'] = 'declared_missing'
            kunye['missing_properties'] = eksik
            kunye['reason'] = (
                f'the cited table declares no verified value for {eksik} in '
                f'the {aile!r} row (see record.*.reason for what was '
                'searched); kappa is therefore not produced')
            return None, kunye
        if rho <= 0:
            kunye['status'] = 'no_density'
            kunye['reason'] = 'propellant density is not available'
            return None, kunye

        c_p = float(kayit.specific_heat.value)
        k_th = float(kayit.thermal_conductivity.value)
        if not (c_p > 0 and k_th > 0):
            kunye['status'] = 'non_physical_properties'
            kunye['reason'] = (
                f'the table row carries c_p = {c_p} J/kgK and k = {k_th} W/mK; '
                'kappa is only defined for positive values')
            return None, kunye
        kappa = k_th / (rho * c_p)
        kunye['status'] = 'resolved'
        kunye['specific_heat_J_kgK'] = c_p
        kunye['thermal_conductivity_W_mK'] = k_th
        kunye['phase'] = {
            'specific_heat': kayit.specific_heat.phase,
            'thermal_conductivity': kayit.thermal_conductivity.phase,
        }
        return float(kappa), kunye

    def _qshod_band_block(self, akustik, curve):
        """QSHOD/Denison-Baum (A, B) bandı — KAPILI yol (varsayılan YOK).

        Bant ve termal yayınırlık çözücüde üretilmez; ikisi de dışarıdan
        verilmedikçe bu blok sayı İÇERMEZ. Kapının iki anahtarı:

          * ``self.combustion_response_band`` — ``hrma.stability.QSHODBand``
            örneği. Bant üstverisiz kurulamaz (formülasyon sınıfı, basınç ve
            sıcaklık zarfı, kaynak künyesi ZORUNLU); çalışma noktası zarfın
            dışındaysa çekirdek sonucu 'extrapolated_low' rozetiyle döner.
          * ``self.propellant_thermal_diffusivity_m2_s`` — κ = k/(ρ·c_p).
            Katı çözücüde yakıtın k ve c_p'si YOKTUR (tasarım belgesi
            §1.1-4 ölçtü), bu yüzden κ uydurulmaz.

        Bu partide bantların KÜNYELİ TABLOSU yazılmadı (ayrı kalem): burada
        yalnız yol uçtan uca kuruludur ve bekçisi sentetik bantla geçer.
        """
        basis = (
            'QSHOD / Denison-Baum pressure-coupled response Re(R_p) evaluated '
            'at the corners of a supplied (A, B) band '
            '(hrma/stability/response.py; Denison & Baum, ARS Journal 31(8), '
            '1961; Culick & Yang 1990, Eqs. 94-95). A and B are propellant '
            'parameters that are MEASURED, not derived, and this solver '
            'produces neither them nor the propellant thermal diffusivity '
            'kappa = k/(rho*c_p) they need. Nothing is defaulted: without '
            'both inputs the block reports no number at all. When a band is '
            'supplied it must carry its validity envelope (formulation class, '
            'pressure and temperature range, source), and an operating point '
            'outside that envelope comes back flagged as extrapolated.')
        # ÖH D22 (defter P6B4-08): iki anahtar da artık DEPO TABLOLARINDAN
        # çözülmeye ÇALIŞILIR. Çağıranın açıkça verdiği değer önceliklidir
        # (test/araştırma yolu); verilmediyse yakıtın katalog ailesinden
        # okunur ve NE OKUNDUĞU (ya da neden okunamadığı) künyeyle
        # yayımlanır. Uydurma yoktur: tablo satırı boşsa anahtar boş kalır.
        band = getattr(self, 'combustion_response_band', None)
        if band is not None:
            band_kunye = {'status': 'caller_supplied', 'source': 'caller',
                          'basis': ('the response band was set on the engine '
                                    'instance by the caller and overrides '
                                    'the repository band table')}
            # ÖH D27 a2 (P13B4-03) — ÇAĞIRAN YOLUNDA KÜNYE KAYBI KAPANDI.
            # ÖLÇÜLDÜ (a2/once.json K1, taban 709a235e): katalog yolunda
            # kaydın künye zarfının dördü de (record_id /
            # record_confidence / record_confidence_note / retrieved)
            # yanıta giriyordu (4/4), ama çağıran bandı elden verdiğinde
            # 0/4 idi — üstelik verilen band KATALOĞUN KENDİ kaydının
            # bandı olsa bile. Yani kaydın güven derecesi tam da bandın
            # nereden geldiğinin en belirsiz olduğu yolda kayboluyordu.
            # Künye ikinci kez YAZILMAZ: kaydın kendi ``as_dict``i taşınır
            # (tek kaynak), eşleşmenin NASIL kurulduğu da beyan edilir.
            _kayit = self._qshod_record_for_band(band)
            if _kayit is not None:
                band_kunye['record'] = _kayit.as_dict()
                band_kunye['record_match_basis'] = (
                    'the supplied band object IS the band of this published '
                    'record in the repository table (identity match, '
                    'hrma/stability/bands.py QSHOD_BAND_RECORDS), so the '
                    'record-level confidence and its caveats apply to the '
                    'numbers published here. A band that is not a table '
                    'record carries no record envelope and this key is '
                    'absent rather than guessed.')
        else:
            band, band_kunye = self._qshod_band_from_catalog()

        kappa = getattr(self, 'propellant_thermal_diffusivity_m2_s', None)
        _kappa_verildi = (isinstance(kappa, (int, float))
                          and not isinstance(kappa, bool)
                          and float(kappa) > 0)
        if _kappa_verildi:
            kappa_kunye = {'status': 'caller_supplied', 'source': 'caller',
                           'basis': ('kappa was set on the engine instance by '
                                     'the caller and overrides the cited '
                                     'thermal-property table')}
        else:
            kappa, kappa_kunye = self._propellant_thermal_diffusivity()

        eksik = []
        if band is None:
            eksik.append('combustion_response_band (QSHODBand with envelope)')
        if not (isinstance(kappa, (int, float)) and not isinstance(kappa, bool)
                and float(kappa) > 0):
            eksik.append('propellant_thermal_diffusivity_m2_s')
        yuzeyler = np.asarray((curve or {}).get('burn_area', []), dtype=float)
        debiler = np.asarray((curve or {}).get('mass_flow', []), dtype=float)
        s_b = float(yuzeyler[0]) if yuzeyler.size else 0.0
        mdot = float(debiler[0]) if debiler.size else 0.0
        rho_p = float(getattr(self, 'rho_p', 0.0) or 0.0)
        if not (s_b > 0 and mdot > 0 and rho_p > 0):
            eksik.append('burn_area / mass_flow / propellant density')
        boyuna = self._pure_longitudinal_modes(akustik or {})
        if not boyuna:
            eksik.append('acoustic_modes (longitudinal mode table)')
        if eksik:
            return {'status': 'NOT_EVALUATED', 'missing_inputs': eksik,
                    '_basis': basis,
                    # ÖH D22 (P6B4-08): "eksik" demek yetmez — HANGİ tabloda
                    # arandığı ve satırın NEDEN boş olduğu da yayımlanır.
                    # Kullanıcı "hesaplanamadı" ile "ölçülmüş veri yok"
                    # arasındaki farkı ancak böyle görebilir.
                    'band_source': self._sayisiz_kunye(band_kunye),
                    'thermal_diffusivity_source':
                        self._sayisiz_kunye(kappa_kunye),
                    'reason': ('no response function is evaluated and no (A, '
                               'B) pair is assumed; missing input(s): '
                               f'{eksik}')}

        from hrma.stability.response import qshod_response_band

        # Etkin (erozif düzeltmeli) gerileme hızı, çözücünün KENDİ kütle
        # dengesinden: ṁ = ρ_p·ṙ·S_b. İkinci bir yanma hızı modeli
        # kurulmaz; a·P^n yeniden hesaplanmaz.
        r_b = mdot / (rho_p * s_b)
        t_c = float(getattr(self, 'T_c', 0.0) or 0.0)
        p_pa = float(getattr(self, 'P_c', 0.0) or 0.0) * 1e5
        satirlar = []
        for mod in boyuna:
            omega = 2.0 * np.pi * float(mod.get('frequency_hz') or 0.0)
            try:
                sonuc = qshod_response_band(band, omega, float(kappa), r_b,
                                            p_pa, t_c)
            except ValueError as exc:
                satirlar.append({'label': mod.get('label'),
                                 'status': 'NOT_EVALUATED',
                                 'reason': f'the response core refused: {exc}'})
                continue
            satirlar.append({
                'label': mod.get('label'),
                'frequency_hz': float(mod.get('frequency_hz')),
                'omega_nondim': sonuc['omega_nondim'],
                'response_real_min': sonuc['response_real_min'],
                'response_real_max': sonuc['response_real_max'],
                'confidence': sonuc['confidence'],
                'confidence_basis': sonuc['confidence_basis'],
                'corners': sonuc['corners'],
            })
        return {
            'status': 'modelled',
            '_basis': basis,
            'band': band.as_dict(),
            # ÖH D22 (P6B4-08): bandın ve κ'nın NEREDEN geldiği hükümle
            # birlikte yayımlanır — kayıt künyesi, güven notu ve sınıf
            # eşleşme beyanı bu bloktan okunur.
            'band_source': band_kunye,
            'thermal_diffusivity_source': kappa_kunye,
            'regression_rate_m_s': float(r_b),
            'regression_rate_basis': (
                'Effective regression rate implied by the solver\'s own mass '
                'balance at t = 0: rdot = mdot/(rho_p*S_b). It is read back '
                'from the published thrust curve rather than recomputed from '
                'a*P^n, so any erosive correction the solver applied is '
                'already inside it and the two cannot disagree.'),
            'thermal_diffusivity_m2_s': float(kappa),
            'modes': satirlar,
        }

    def _nozzle_flow_field_report(self, contour_points_m):
        """Lüle iç akışı (yarı-1B) + ayrılma — hrma.flow.quasi1d / separation.

        Girdi, sonuç sözlüğünde YAYIMLANAN lüle iç konturudur
        (``nozzle_contour.points``, [z_m, r_m] çiftleri): 2B kesitin,
        STL/STEP dışa aktarımının ve 3B sahnenin okuduğu AYNI örneklem.
        Alan profili A(x) = pi·r² ile bu konturdan kurulur — ikinci bir
        geometri tanımı üretilmez.

        Akış durumu çözücünün kendi büyüklüklerinden gelir: durma basıncı
        P0 = tasarım kamara basıncı, T0 = kamara sıcaklığı, gamma ve
        R = R_evrensel/MW_egzoz yakıt kaydından (nozul çıkış durumunun
        kullandığı değerlerin aynısı), geri basınç ise motorun ortam
        basıncıdır (ambient_pressure_bar; kullanıcı vermediyse deniz
        seviyesi).

        Ayrılma değerlendirmesi eşiğini motorun KENDİ sabitinden alır
        (SUMMERFIELD_SEPARATION_RATIO) — aynı sayı iki yerde ayrı ayrı
        tanımlanmaz.

        Dönüş: (yarı-1B akış bloğu, ayrılma bloğu). Kontur yoksa ya da modül
        profili reddederse iki blok da eksik girdiyi ADIYLA anan NOT_MODELLED
        beyanıyla döner (uydurma profil kurulmaz).
        """
        surum = _hrma_version()
        kunye_akis = f'hrma.flow.quasi1d.solve_nozzle (HRMA {surum})'
        kunye_ayr = f'hrma.flow.separation.assess_separation (HRMA {surum})'

        def _yok(eksik, gerekce):
            return ({'status': 'NOT_MODELLED', 'missing_inputs': list(eksik),
                     'basis': (f'{gerekce} No flow field is reported. '
                               + kunye_akis)},
                    {'status': 'NOT_MODELLED', 'missing_inputs': list(eksik),
                     'basis': (f'{gerekce} No separation assessment is '
                               'reported. ' + kunye_ayr)})

        if not contour_points_m:
            return _yok(['nozzle_contour'],
                        'The nozzle inner contour was not published, so the '
                        'area profile A(x) cannot be built from the solver '
                        'geometry.')

        eksik = []
        try:
            t_c = float(self.T_c)
            gam = float(self.gamma)
            mw = float(getattr(self, 'mw_exhaust', 0.0) or 0.0)
            p_c = float(self.P_c)
        except Exception:
            t_c = gam = mw = p_c = 0.0
        if not (p_c > 0):
            eksik.append('chamber_pressure')
        if not (t_c > 0):
            eksik.append('chamber_temperature')
        if not (gam > 1.0):
            eksik.append('gamma')
        if not (mw > 0):
            eksik.append('molecular_weight')
        if eksik:
            return _yok(eksik, 'The solver does not produce the reservoir '
                               f'state {eksik}.')

        try:
            dizi = np.asarray(contour_points_m, dtype=float)
            x_m = dizi[:, 0]
            area_m2 = np.pi * dizi[:, 1] ** 2
        except Exception:
            return _yok(['nozzle_contour'],
                        'The published nozzle contour could not be read as '
                        '[z_m, r_m] pairs.')

        p0_pa = p_c * 1e5
        pa_bar = float(getattr(self, 'ambient_pressure_bar',
                               SEA_LEVEL_PRESSURE_BAR))
        pb_pa = pa_bar * 1e5
        r_gas = R_UNIVERSAL / mw

        girdi_kunyesi = {
            'P0_Pa': float(p0_pa),
            'P0_source': ('design chamber pressure self.P_c — the same '
                          'stagnation pressure the throat sizing uses'),
            'T0_K': t_c,
            'gamma': gam,
            'gas_constant_J_kgK': float(r_gas),
            'gas_property_source': (
                'propellant record — the same gamma and exhaust molecular '
                'weight the nozzle exit state and thrust coefficient use'),
            'Pb_Pa': float(pb_pa),
            'Pb_source': (
                'motor ambient pressure (ambient_pressure_bar input; sea '
                'level when the user supplied none)'),
            'area_profile_source': (
                'A(x) = pi*r^2 from the published nozzle_contour points, the '
                'same sampled inner flow-path the 2D cross-section and the '
                'STL/STEP exports consume'),
        }

        from hrma.flow import quasi1d as _q1d
        from hrma.flow import separation as _sep

        try:
            akis = _q1d.solve_nozzle(x=x_m, area=area_m2, P0=p0_pa, T0=t_c,
                                     gamma=gam, R=float(r_gas), Pb=pb_pa)
        except Exception as exc:
            akis_blok = {
                'status': 'NOT_MODELLED',
                'missing_inputs': [],
                'basis': ('The quasi-1D solver rejected the published nozzle '
                          f'geometry or the reservoir state: {exc}. No flow '
                          'field is reported. ' + kunye_akis),
            }
        else:
            akis_blok = dict(akis)
            # JSON-güvenli: modül istasyon dizilerini numpy olarak döndürür.
            for anahtar in ('x_m', 'area_m2', 'mach', 'pressure_Pa',
                            'temperature_K'):
                if anahtar in akis_blok:
                    akis_blok[anahtar] = [float(v) for v
                                          in np.asarray(akis_blok[anahtar])]
            akis_blok.update({
                'status': 'computed',
                'inputs_used': dict(girdi_kunyesi),
                '_basis': (
                    f'{kunye_akis}; area profile and reservoir state as '
                    'listed in inputs_used. Diagnostic only: the regime, the '
                    'shock position and the station profiles are NOT fed '
                    'back into the thrust curve, which keeps using the '
                    'thrust-coefficient formulation.'),
            })

        try:
            ayrilma = _sep.assess_separation(
                P0=p0_pa, Pa=pb_pa, gamma=gam, x=x_m, area=area_m2,
                summerfield_factor=SUMMERFIELD_SEPARATION_RATIO)
        except Exception as exc:
            ayrilma_blok = {
                'status': 'NOT_MODELLED',
                'missing_inputs': [],
                'basis': ('The separation module rejected the published '
                          f'nozzle geometry or the flow state: {exc}. No '
                          'separation assessment is reported. ' + kunye_ayr),
            }
        else:
            ayrilma_blok = dict(ayrilma)
            modul_basis = ayrilma_blok.pop('_basis', None)
            ayrilma_blok.update({
                'status': 'computed',
                'inputs_used': dict(girdi_kunyesi),
                'summerfield_factor_source': (
                    'SUMMERFIELD_SEPARATION_RATIO of this engine module — '
                    'the same constant the legacy Summerfield check uses, so '
                    'the threshold has a single definition point'),
                'module_basis': modul_basis,
                '_basis': (
                    f'{kunye_ayr}; wall pressure from the full-flowing '
                    'isentropic core of the published contour, ambient '
                    'pressure and gas state as listed in inputs_used. '
                    'Diagnostic only: a predicted separation does NOT alter '
                    'the reported thrust, which is computed from the '
                    'attached-flow thrust coefficient.'),
            })

        return akis_blok, ayrilma_blok

    def _web_utilization_percent(self, curve):
        """Tüketilen web / mevcut web [%] — gerçek gerilemeden.

        Eski sürüm sabit 98.5 döndürüyordu. Tüketilen web, yanma hızının
        zaman integralidir (dw/dt = r); mevcut web grain tipine göre
        calculate_thrust_curve ile AYNI tanımdan gelir.
        """
        consumed = self._consumed_web(curve)
        if consumed is None:
            return 0.0
        # ÖH D15 a2 (P2B4-02): "mevcut web" kuralının burada SATIR İÇİ ikinci
        # bir kopyası duruyordu; kural tek yerde kalır, ikisi ayrışamaz.
        # ÖH D15 a3 (P2B2-04): payda ARTIK çözücünün tarama üst sınırı değil
        # fiziksel olarak tüketilebilir web (_available_web_thickness) —
        # gerekçe ve ölçüm o fonksiyonun künyesinde.
        max_web = self._available_web_thickness()
        if max_web <= 0:
            return 0.0
        return float(max(0.0, min(100.0, 100.0 * consumed / max_web)))
    
    #: Kasa cidarı KULLANICIDAN geldi mi? Yapısal hüküm, kap onayı ve kuru
    #: kütle beyanı bu TEK ayrımı kullanır (iki yerde iki farklı cevap
    #: verilmesi yasak).
    def _case_thickness_is_user_supplied(self):
        """Kullanıcı ``case_thickness`` verdi mi (ve o değer mi kullanıldı)?

        v2.6.27 (B2-4). ``_case_design()`` cidarı ya kullanıcıdan alır ya
        Barlow ile KENDİ boyutlandırır; ikisi arasındaki fark, yayımlanan
        emniyet katsayısının bir DOĞRULAMA mı yoksa girdinin geri okunması
        mı olduğunu belirler.
        """
        return getattr(self, 'user_case_thickness', None) is not None

    def _case_model_validity(self):
        """Kasa için (C) model geçerlilik alanları — ``case_analysis`` ve
        ``pressure_safety`` bu TEK çağrıyı okur.

        V3 yapi-sf 3. tur B (karar §28-37 Ş2-3 (a), v3.0 bloklayıcı).
        ÖLÇÜLDÜ (yeniden denetim-2): aluminum_6061 kasa, yalıtım 0,
        end_burner 1500 mm, 3200 K, kasa 4 mm → ısı modelinin kasa sıcaklığı
        1636,8 K (erime 855 K); yanıt yine ``vessel_status`` PASS ve SF 7,333
        "verified" yayımlıyordu. Kasa dayanımı oda sıcaklığı değeridir;
        kasanın kendi ısı modeli onu erime üstünde buluyorsa o dayanımdan
        çıkan onay geçersizdir.

        Ölçüt BURADA yazılmaz: sıcaklık ısı modelinin kendi yanma sonu kasa
        sıcaklığıdır (``_calculate_case_temperature``; yayımlanan
        ``heat_transfer.case_temperature_k`` ile aynı fonksiyon), malzeme
        kaydı materials_db'den; ikisi ``structural_model_validity_at``e
        (hibritin tek ölçütü) verilir. Kaydı olmayan malzemede
        (SOLID_CASE_MATERIAL_EXTRA, ör. 'composite') bayrak None + künye.
        """
        from hrma.analysis.structural_analysis import (
            SOLID_CASE_MODEL_VALIDITY_BASIS, model_validity_publication,
            structural_model_validity_at)
        malzeme = self._case_design()[0]
        try:
            from hrma.data.materials_db import get_material
            kayit = get_material(malzeme)
        except Exception:
            kayit = None
        return model_validity_publication(
            structural_model_validity_at(
                kayit,
                {'case_wall_end_of_burn': self._calculate_case_temperature()}),
            SOLID_CASE_MODEL_VALIDITY_BASIS)

    def _calculate_structural_analysis(self):
        """Structural analysis like other systems"""
        # Case stress analysis — cidar kalınlığı ve dayanım TEK kaynaktan
        # (_case_design); kullanıcının yield_strength / safety_factor /
        # case_thickness girdileri buraya işler.
        material, sigma_y, SF_design, t_wall = self._case_design()
        # Hoop yarıçapı _case_design ile AYNI kaynaktan (kasa iç yarıçapı =
        # grain + yalıtım); iki panelin farklı yarıçap kullanması yasak.
        r_inner = self._case_inner_diameter() / 2
        hoop_stress = self.P_c * 1e5 * r_inner / t_wall
        safety_factor = sigma_y / hoop_stress

        # --- YAPISAL TOTOLOJİ BEYANI (B2-4, v2.6.27) ----------------------
        # Kullanıcı bir cidar VERMEDİYSE _case_design cidarı
        #     t = P*r / (sigma_y / SF_hedef)
        # ile boyutlandırır. Buradaki hoop gerilmesi ise
        #     sigma = P*r / t
        # olduğundan SF = sigma_y/sigma cebirsel olarak SF_hedef'in
        # KENDİSİDİR: hesap değil, girdinin eko'su. ÖLÇÜLDÜ (APCP,
        # D_kamara = 100 mm, D_çekirdek = 30 mm, L = 500 mm, SF_hedef = 3,0):
        #     Pc =  40 bar -> t = 2,400 mm, SF = 3,000000
        #     Pc =  80 bar -> t = 4,800 mm, SF = 3,000000
        #     Pc = 150 bar -> t = 9,000 mm, SF = 3,000000
        # yani dört mertebe basınç değişiminde 6 basamak aynı sayı.
        # (Pc = 20 bar'da SF = 5,0 çıkar; orada da bir doğrulama yoktur —
        # asgari cidar kelepçesi devrededir ve okunan sayı O kelepçedir.)
        #
        # Hibrit yolda bu ayrım ZATEN vardı (structural_analysis.py
        # 'design_mode' + 'safety_factor_is_tautological'); katı motorda
        # YOKTU. Aynı adlar burada da kullanılır ki uç katmanının dürüstlük
        # kapısı (app.py _withhold_unearned_structural_verdict / _withhold_
        # unearned_vessel_verdict) iki motorda tek sözleşme okusun.
        #
        # Z2 (P2B2-01): ``clamped`` eskiden burada ``(not user_wall) and ...``
        # diye kuruluyordu, yani DOĞRULAMA dalında YAPISAL OLARAK True
        # olamıyordu — oysa kırpmanın gerçekten olduğu dal tam da oydu
        # (kullanıcının 0,5 mm'si 2,0'a çekiliyor, bayrak False kalıyordu).
        # Kırpma artık kullanıcı dalında hiç yapılmadığı için bayrak
        # dürüsttür ve künye tek kaynaktan (_case_wall_provenance) okunur.
        prov = self._case_wall_provenance()
        user_wall = prov['source'] == 'user_supplied'
        design_mode = 'verify' if user_wall else 'size'

        # Grain structural integrity — gerçek elastisite çözümü
        grain = self._calculate_grain_structural()
        # V301/FİZİK-2 (kalem 10): gerinim kapasitesi aşıldıysa adlı uyarı.
        self._tane_gerinim_uyarisi(grain)
        grain_stress = grain['max_grain_stress_mpa']

        # Kapak (baş/arka kapak) — ÖH D22 (P9B2-02). Basınç sınırının
        # ikinci parçası ARTIK burada hesaplanır; gerekçe _end_cap_analysis.
        end_cap = self._end_cap_analysis(sigma_y, SF_design)

        # V3 yapi-sf 3. tur B (karar §28-37 Ş2-3 (a)): (C) model geçerlilik
        # sınırı — tek ölçütten (``_case_model_validity``).
        from hrma.analysis.structural_analysis import (
            SOLID_CASE_MODEL_VALIDITY_SAFETY_FACTOR_BASIS)
        kasa_gecerlilik = self._case_model_validity()
        kasa_disi = kasa_gecerlilik.get('model_validity_limit_exceeded') is True
        # V3 yapi-sf 4. tur (karar §28-44 (i)): kapak, kasa hoop analiziyle
        # AYNI basınç, AYNI iç çap ve AYNI oda sıcaklığı dayanımıyla
        # (``_case_design``) değerlendirilir; kasanın geçerlilik bayrağı
        # kapağın da bayrağıdır. Geçerlilik dışında kapak bloğu "sized and
        # verified" onayı taşımaz: aynı bayrak + künye + verdict_withheld,
        # ``_basis`` tanı künyesine döner, sayılar (kalınlık, gerilme, SF)
        # tanı amaçlı yerinde kalır. Ölçüt yazılmaz, bayrak okunur.
        if (kasa_disi and isinstance(end_cap, dict)
                and end_cap.get('status') == 'modelled'):
            end_cap = {**end_cap, **kasa_gecerlilik,
                       '_basis': self.END_CAP_MODEL_VALIDITY_BASIS}

        return {
            'case_analysis': {
                'hoop_stress_mpa': hoop_stress / 1e6,
                'longitudinal_stress_mpa': hoop_stress / 2 / 1e6,
                'safety_factor': safety_factor,
                # ÖH D15 (P2B2-02): burada '* 2.0' vardı ve çarpanın
                # kodda, yorumda ya da künyede HİÇBİR dayanağı yoktu.
                # Yayımlanan oran gerçek kullanımın tam iki katıydı:
                # SF=1,5 ile aynı sözlükte %133,3, SF=0,5 ile %400
                # basılıyordu — akmaya karşı emniyetli bir kasa için
                # fiziksel olarak imkânsız bir hüküm çifti. Malzeme
                # kullanımı tanım gereği sigma/sigma_y = 1/SF'tir.
                'material_utilization_percent': 100.0 / safety_factor,
                'material_utilization_basis': (
                    'sigma_hoop / sigma_yield = 1 / safety_factor; 100% '
                    'means the hoop stress has reached the yield '
                    'strength of the case material'),
                'recommended_wall_thickness_mm': (
                    self.P_c * 1e5 * r_inner / (sigma_y / SF_design) * 1000),
                'case_material': material,
                'yield_strength_mpa': sigma_y / 1e6,
                'design_safety_factor': SF_design,
                'wall_thickness_mm': t_wall * 1000,
                # --- B2-4 beyanı (hibritle AYNI alan adları) -------------
                'design_mode': design_mode,          # 'size' | 'verify'
                'wall_thickness_source': prov['source'],
                'safety_factor_is_tautological': bool(not user_wall),
                'wall_thickness_at_minimum_clamp': prov['clamped_to_floor'],
                # --- Z2 künyesi: İSTENEN ve KULLANILAN cidar yan yana ----
                'wall_thickness_requested_mm': prov['requested_mm'],
                'wall_thickness_hoop_required_mm': prov['hoop_required_mm'],
                'wall_thickness_manufacturing_floor_mm': (
                    prov['manufacturing_floor_mm']),
                'wall_thickness_below_manufacturing_floor': (
                    prov['below_manufacturing_floor']),
                'safety_factor_basis': (
                    (f"verified against the user-supplied case wall thickness "
                     f"({prov['used_mm']:.4g} mm, evaluated exactly as "
                     f"entered - HRMA does not raise it to the "
                     f"{prov['manufacturing_floor_mm']:.4g} mm manufacturing "
                     f"floor)."
                     + ('' if not prov['below_manufacturing_floor'] else
                        ' NOTE: this wall is BELOW that manufacturing floor; '
                        'the safety factor below describes the thin wall you '
                        'entered, not a wall HRMA would propose.'))
                    if user_wall else
                    'NOT a verification: no case thickness was supplied, so '
                    'HRMA sized the wall from the hoop stress to meet the '
                    'design safety factor (t = P*r/(sigma_y/SF)). Dividing '
                    'the yield strength by the resulting hoop stress returns '
                    'that same design safety factor - it is the INPUT read '
                    'back. Supply case_thickness (mm) to obtain an '
                    'independent verification.'
                    + ('' if not prov['clamped_to_floor'] else
                       f" In this run the hoop stress only required "
                       f"{prov['hoop_required_mm']:.4g} mm, so the proposal "
                       f"was raised to the "
                       f"{prov['manufacturing_floor_mm']:.4g} mm "
                       f"manufacturing floor and the safety factor above is "
                       f"that floor, not the design target.")),
                # V3 yapi-sf 3. tur B: geçerlilik bayrağı + künye (+ sınır
                # aşıldıysa verdict_withheld ve gerekçe kodu). Sınır aşıldıysa
                # yukarıdaki 'safety_factor_basis' (doğrulama/öneri cümlesi)
                # TANI künyesiyle değiştirilir (sözlükte sonraki anahtar
                # kazanır); sayı kalır.
                **kasa_gecerlilik,
                **({'safety_factor_basis':
                    SOLID_CASE_MODEL_VALIDITY_SAFETY_FACTOR_BASIS}
                   if kasa_disi else {}),
            },
            'grain_structural': grain,
            # ÖH D22 (P9B2-02, YÜKSEK) — BASINÇ TAŞIYAN KAPAK ARTIK
            # ANALİZDEN GELİYOR. Bu anahtar katı rotasında YOKTU; hibrit
            # rotası (StructuralAnalyzer.analyze_structure) onu ZATEN
            # yayımlıyordu. Adı ve şeması hibritinkiyle BİREBİR aynıdır
            # (aynı üretici fonksiyon), çünkü tüketicisi tek: ihraç
            # katmanının kapak kararı bu bloğu adıyla arıyor
            # (hrma/export/cad_visualization._front_cap_design ->
            # end_cap_analysis.flat_head_thickness).
            'end_cap_analysis': end_cap,
            'assembly_integrity': {
                'grain_case_bonding': 'Inhibited surfaces',
                'thermal_barrier_effectiveness': self._insulation_effectiveness_percent(),
                # Kalem 27-28 (P3): eskiden burada SABİT '98.2' (%) vardı.
                # HRMA'da bir güvenilirlik (olasılık) modeli YOKTUR: ne
                # cıvata dayanım dağılımı ne yük dağılımı tanımlı. Sayı
                # kaldırıldı; yerine cıvatalı kapak birleşiminin GERÇEK
                # emniyet katsayıları (VDI 2230 / Shigley Böl. 8 sınıfı)
                # verilir. Kullanıcı cıvata sayısını girmediyse alan
                # 'not_sized' döner — sayı uydurulmaz.
                'joint_reliability': None,
                'joint_reliability_status': 'NOT_MODELLED',
                'joint_reliability_basis': (
                    'HRMA has no probabilistic joint model (no strength or '
                    'load distributions); a reliability percentage cannot be '
                    'computed. The deterministic bolted-joint safety factors '
                    'are given in closure_joint instead.'),
                'closure_joint': self._closure_joint_analysis(),
            }
        }

    #: V3 yapi-sf 4. tur (karar §28-44 (i)) — kasa geçerlilik dışıyken
    #: ``end_cap_analysis._basis``in yerine geçen tanı künyesi. ÖLÇÜLDÜ
    #: (yeniden denetim-3, olc/dal/kati_al.json): Al 6061 kasa 1636,8 K
    #: (erime 855 K) iken kapak bloğu oda sıcaklığı akmasıyla (275 MPa)
    #: SF 3,0 ve "Closure head sized and verified" yayımlıyordu.
    END_CAP_MODEL_VALIDITY_BASIS = (
        'DIAGNOSTIC ONLY, NOT A VALID DESIGN OUTPUT: the closure head '
        'thicknesses, stresses and safety factors in this block use the '
        'room-temperature strength of the case material, while the case wall '
        'temperature computed by the heat-transfer model is outside the '
        'validity limit of the structural model '
        '(case_analysis.model_validity_limit_exceeded, '
        'model_validity_reasons). '
        'They are diagnostic numbers only: no acceptance and no numeric '
        'design verdict is issued for the head. Model: flat circular plate '
        'bending, simply supported (Roark Table 11.2), cross-checked against '
        'ASME VIII-1 UG-34, and the 2:1 ellipsoidal alternative from ASME '
        'VIII-1 UG-32(d), at the same pressure and inner diameter as the '
        'case hoop analysis.')

    def _end_cap_analysis(self, sigma_y, sf_design):
        """Baş/arka kapağın yapısal hükmü — hibritle AYNI çekirdek.

        ÖH D22 (defter P9B2-02, YÜKSEK). ÖLÇÜLDÜ (taban ``b84b10a``,
        ``docs/scofield/raw/OH/D22/kati/a1/once.json`` bölüm K2): katı
        rotasının ``structural_analysis`` bloğu üç anahtar taşıyordu
        (``case_analysis``, ``grain_structural``, ``assembly_integrity``);
        ``end_cap_analysis`` YOKTU. Sonuç, imalata giden çizimde ölçüldü:
        ``_front_cap_design`` kapak kalınlığını analizde bulamadığı için
        üreteç kuralına düşüyor ve

            Ø100 mm / 40 bar / çelik / cidar 2,40 mm  -> kapak 8,00 mm
            Ø100 mm / 40 bar / çelik / cidar 6,00 mm  -> kapak 8,00 mm
            Ø100 mm / 40 bar / ALÜMİNYUM              -> kapak 8,00 mm

        yani üç ayrı tasarımda birebir aynı sayı. Aynı dosyada cidar
        "yapısal analizden geldi" künyesiyle duruyordu; kapak, basınç
        sınırının cidarla EŞİT derecede kritik ikinci parçası olmasına
        rağmen hiçbir analizden gelmiyordu. Beyan (``ASSUMED closure
        head...``) çözüm değildir: tezgâha giden sayı yine üreteç kuralının
        kendisiydi.

        İkinci bir kapak modeli YAZILMAZ. Depoda kapak gerilmesinin tek
        üreticisi ``hrma.analysis.structural_analysis.StructuralAnalyzer.
        _analyze_end_caps``tir (Roark Tbl. 11.2 düz plaka eğilmesi + ASME
        VIII-1 UG-32(d) 2:1 elipsoidal başlık, UG-34 çapraz kontrolü) ve
        hibrit rotası ZATEN onu çağırıyor. Katı rotası da onu çağırır;
        böylece iki motor tipi kapak hakkında AYNI cümleyi kurar.

        Girdiler katı çözücünün KENDİ tek kaynaklarından gelir:

          * basınç  = ``P_c`` (MEOP), hazne cidarı hoop hesabıyla AYNI
            basınç. Kapak ile cidarın emniyet katsayıları ancak aynı
            basınçta karşılaştırılabilir; ikisinden birine tasarım
            çarpanı uygulamak aynı yanıtta iki farklı yükleme demektir.
          * çap     = ``_case_inner_diameter()`` (grain + 2 x yalıtım),
            hoop yarıçapıyla AYNI kaynak.
          * dayanım = ``_case_design()``in akma dayanımı (kullanıcının
            ``yield_strength`` girdisi buraya da işler).
          * SF      = ``_case_design()``in tasarım katsayısı (kullanıcının
            ``safety_factor`` girdisi).

        FAIL-CLOSED: düz plaka eğilmesi Poisson oranını İSTER. Kasa
        malzemesinin kaydında ``poisson_ratio`` yoksa (ör.
        ``SOLID_CASE_MATERIAL_EXTRA['composite']`` — filaman sargı zaten
        izotrop plaka formülünün kapsamı dışındadır) kapak kalınlığı
        UYDURULMAZ: blok ``NOT_EVALUATED`` döner, ``flat_head_thickness``
        taşımaz ve ihraç katmanının imalat kapısı kapalı kalır.
        """
        material = getattr(self, 'case_material',
                           SOLID_CASE_DESIGN['material'])
        basis = (
            'Closure head sized and verified by the repository\'s single '
            'end-cap model (StructuralAnalyzer._analyze_end_caps): flat '
            'circular plate bending, simply supported (Roark Table 11.2), '
            'cross-checked against ASME VIII-1 UG-34, and the 2:1 '
            'ellipsoidal alternative from ASME VIII-1 UG-32(d). It is '
            'evaluated at the SAME pressure and the SAME inner diameter as '
            'the case hoop analysis in this response (MEOP = chamber '
            'pressure, case inner diameter = grain + 2 x insulation), so '
            'the head and the wall safety factors in this block are '
            'directly comparable. Strength and design safety factor come '
            'from _case_design(), i.e. from the user\'s own case material, '
            'yield strength and safety factor inputs.')

        nu = None
        try:
            from hrma.data.materials_db import get_material
            _rec = get_material(str(material or '').strip())
            nu = _rec.get('poisson_ratio')
        except Exception:
            nu = None
        if nu is None:
            nu = (SOLID_CASE_MATERIAL_EXTRA
                  .get(str(material or '').strip().lower(), {})
                  .get('poisson_ratio'))
        try:
            nu = float(nu)
        except (TypeError, ValueError):
            nu = None
        if nu is None or not np.isfinite(nu) or not (0.0 < nu < 0.5):
            return {
                'status': 'NOT_EVALUATED',
                'missing_inputs': [
                    f"poisson_ratio (material record for '{material}')"],
                'reason': (
                    'the flat circular plate bending relation needs the '
                    "Poisson ratio of the case material and the record for "
                    f"'{material}' does not publish one; no closure head "
                    'thickness is produced and none is assumed'),
                '_basis': basis,
            }

        from hrma.analysis.structural_analysis import StructuralAnalyzer
        mat_props = {
            'yield_strength': float(sigma_y),
            'poisson_ratio': float(nu),
            'safety_factor': float(sf_design),
        }
        blok = StructuralAnalyzer()._analyze_end_caps(
            float(self.P_c) * 1e5,
            float(self._case_inner_diameter()),
            mat_props,
            derating=None,
            design_safety_factor=float(sf_design),
            actual_thickness=None,
        )
        blok['status'] = 'modelled'
        blok['case_material'] = material
        blok['poisson_ratio'] = float(nu)
        blok['design_pressure_bar'] = float(self.P_c)
        blok['_basis'] = basis
        return blok

    #: Kapak cıvata birleşiminin varsayılan kabulleri.
    #: Bunlar HESAP DEĞİL, kullanıcı girdisi verilmediğinde kullanılan
    #: sözleşme değerleridir ve çıktıda adıyla beyan edilirler.
    #:
    #: ÖH D25 · P15B2-09 (Fable-D18 ŞARTI) — SÖZLEŞME ARTIK BURADA YAZILI
    #: DEĞİL, İTHAL. Aynı üç alan üç motor dosyasında üç kez yazılıydı;
    #: D18'de hibrit, D24'te sıvı kopyası ``hrma.analysis.bolted_joint``tan
    #: türetildi, KATI kopyası literal sözlük olarak kaldı (D24'te kalemin
    #: tek kimliği sıvı kulvarına düşmüştü). ÖLÇÜLDÜ
    #: (docs/scofield/raw/OH/D25/kati/a1/once_p15b2_09.json; taban cdf2106):
    #: literal kopya 1 (katı), türetilmiş 2 (hibrit + sıvı); üç kopyanın
    #: ORTAK üç alanı bugün ayrışmıyor ama katı kopyanın yarın sessizce
    #: ayrışması hâlâ serbestti — D18 bekçisi yalnız DEĞERLERİN eşit
    #: olduğunu görüyordu, ikinci literalin varlığını değil.
    #:
    #: ÜYE MALZEMESİ burada BİLEREK YOKTUR ve olmaması DOĞRUDUR: D15 /
    #: P2B2-12'de üye malzemesi kasa malzemesinden türetildi (Shigley Böl. 8:
    #: üye rijitliği k_m kasanın E modülünden gelir) ve sessizce alüminyuma
    #: düşmek yasaklandı — bkz. ``_closure_member_material``.
    SOLID_CLOSURE_JOINT_DEFAULTS = dict(_BOLTED_JOINT_CLOSURE_DEFAULTS)

    def _closure_member_material(self):
        """Kapak birleşiminin ÜYE malzemesi + kaynağı (sessiz varsayılan YOK).

        ÖH D15 (P2B2-12): burada sabit ``'aluminum_6061'`` vardı ve kullanıcının
        ``case_material`` seçimi birleşime HİÇ ulaşmıyordu. Ölçüldü (8xM8-8.8,
        40 bar, D_iç=100 mm): çelik/alüminyum/kompozit/titanyum kasada
        yayımlanan proof_SF=0,9900 ve separation=5,0040 BİREBİR aynıydı; oysa
        üye malzemesi sayıları taşıyor (çelik üyede overload n_L=1,8329,
        alüminyumda 0,8611 — SF=1,0 çizgisinin İKİ YANI). Kapak cıvatası kasayı
        sıkar; üye rijitliği (Shigley Böl. 8, k_m) kasa malzemesinin E
        modülünden gelir, o yüzden kaynak kasadır.

        Sıra: kullanıcının açık üye malzemesi -> kasa malzemesi -> (None).
        Elastisite modülü kayıtlı olmayan malzemede (ör. kompozit sargı)
        birleşim BOYUTLANDIRILMAZ; alüminyuma sessizce düşmek yasaktır.

        Döner: (materials_db anahtarı | None, kaynak etiketi | None, gerekçe).
        """
        from hrma.data.materials_db import get_material
        adaylar = []
        acik = self.overrides.get('closure_member_material')
        if isinstance(acik, str) and acik.strip():
            adaylar.append((acik.strip(), 'user_supplied'))
        kasa = getattr(self, 'case_material', None)
        if isinstance(kasa, str) and kasa.strip():
            adaylar.append((kasa.strip(), 'case_material'))
        denenen = []
        for anahtar, kaynak in adaylar:
            denenen.append(anahtar)
            try:
                kayit = get_material(anahtar)
            except Exception:
                continue
            if kayit.get('elastic_modulus'):
                return anahtar, kaynak, None
        return None, None, (
            'The clamped members of a closure joint are the case itself, so '
            'their stiffness follows the case material. No elastic modulus is '
            'recorded for {0}, and assuming an aluminium member would move the '
            'proof and overload factors across the SF = 1.0 line, so the joint '
            'is not sized. Send closure_member_material with a material that '
            'has a published elastic modulus.'.format(
                ' / '.join(repr(x) for x in denenen) or 'the case material'))

    def _closure_joint_analysis(self):
        """Kapak cıvata birleşimi — hrma.analysis.bolted_joint ile.

        Kalem 27-28 (P3). Çözüm projede ZATEN VARDI
        (``analyze_bolted_joint``: Shigley Böl. 8 / ISO 898-1 / NASA-STD-5020A
        ön-yük saçılımı) ve /api/bolted-joint ucundan çağrılıyordu; katı
        motor onu HİÇ çağırmıyor, yerine sabit '%98.2 güvenilirlik' basıyordu.

        Sızdırmazlık çapı kasa İÇ çapıdır (basıncın kapağa ittiği alan);
        basınç tasarım oda basıncıdır. Cıvata sayısı formdan gelir; yoksa
        birleşim boyutlandırılmaz.
        """
        cfg = self.SOLID_CLOSURE_JOINT_DEFAULTS
        lo, hi = cfg['bolt_count_range']
        count = self._override_val('closure_bolt_count', lo, hi)
        if count is None or int(count) < 1:
            return {
                'status': 'not_sized',
                'basis': ('No closure bolt count was supplied, so the joint '
                          'is not sized. Enter the number of closure bolts '
                          'to get separation and proof safety factors.'),
            }
        member_material, member_source, member_reason = (
            self._closure_member_material())
        if member_material is None:
            return {
                'status': 'not_sized',
                'basis': member_reason,
                'case_material': getattr(self, 'case_material', None),
            }
        size = str(self.overrides.get('closure_bolt_size')
                   or cfg['size']).strip().upper()
        prop_class = str(self.overrides.get('closure_bolt_class')
                         or cfg['property_class']).strip()
        seal_diameter_mm = self._case_inner_diameter() * 1000.0
        try:
            from hrma.analysis.bolted_joint import analyze_bolted_joint
            res = analyze_bolted_joint(
                pressure_bar=float(self.P_c),
                seal_diameter_mm=float(seal_diameter_mm),
                bolt_count=int(count),
                size=size,
                property_class=prop_class,
                member_material=member_material)
        except Exception as exc:
            return {
                'status': 'not_sized',
                'basis': f'Bolted-joint analysis rejected the inputs: {exc}',
            }
        sf = res.get('safety_factors', {})
        sep = res.get('separation', {})
        tq = res.get('torque', {})
        return {
            'status': 'sized',
            'bolt_count': int(count),
            'bolt_size': size,
            'property_class': prop_class,
            # v2.6.26 (P4): montaj sırası "Torque to 150 Nm" diye SABİT bir
            # sayı basıyordu. Sıkma torku ön yükten ve cıvata çapından çıkar
            # (T = K·F_i·d, Shigley Denk. 8-27; K nut factor 0.20 yağsız /
            # 0.15 yağlı). Değer analizörün kendi torque() çıktısıdır.
            'tightening_torque_nm': tq.get('recommended_torque_Nm'),
            'nut_factor_K': tq.get('K_nut_factor'),
            'thread_condition': tq.get('condition'),
            'preload_scatter_percent': tq.get('preload_uncertainty_pct'),
            'tightening_torque_basis': (
                'T = K x F_i x d (Shigley 10th ed. Eq. 8-27) with '
                'F_i = 0.75 x proof load (reusable joint) from ISO 898-1 '
                'proof strength; torque control scatters the achieved preload '
                'by the percentage above'),
            'seal_diameter_mm': float(seal_diameter_mm),
            'pressure_bar': float(self.P_c),
            'proof_safety_factor': sf.get('proof_SF_min'),
            'separation_factor': sf.get('separation_factor_n0_min'),
            'overload_factor': sf.get('overload_factor_nL_min'),
            'separated': sep.get('separated'),
            'governing_basis': sf.get('governing_basis'),
            'member_material': member_material,
            'member_material_source': member_source,
            'member_material_basis': (
                'Clamped members are the motor case, so the member stiffness '
                'k_m (Shigley 10th ed. Ch. 8) uses the case material record; '
                'the joint is no longer solved with a fixed aluminium member.'),
            'case_material': getattr(self, 'case_material', None),
            'assumptions': res.get('assumptions'),
            'warnings': res.get('warnings'),
            'source': res.get('source'),
            'basis': ('Separating load = chamber pressure x sealed area '
                      '(case inner diameter); safety factors from the '
                      'bolted-joint analyser used by /api/bolted-joint.'),
        }
    
    @staticmethod
    def _heat_release_power(curve, q_reaction):
        """Çözülmüş eğriden ısı açığa çıkma GÜCÜ [MW] — t=0 / tepe / ortalama.

        P(t) = ṁ_üretim(t) · Q_reaksiyon. ṁ_üretim çözücünün KENDİ
        ``mass_flow`` serisidir (rho_p·Ab(t)·r(t), :10831); burada yeni bir
        fizik hesabı YOKTUR, var olan seri güce çevrilir. Ortalama zaman
        ağırlıklıdır (E_toplam / t_yanma), örnek yerleşimine duyarlı düz
        ortalama değil.

        Eğri yoksa ya da seri kullanılamazsa None döner — sayı UYDURULMAZ
        (fail-closed); çağıran alanı yayımlamaz ve durumu 'not_solved' der.
        """
        if curve is None or not q_reaction or q_reaction <= 0:
            return None
        t = np.asarray(curve.get('time', []), dtype=float)
        mdot = np.asarray(curve.get('mass_flow', []), dtype=float)
        if t.size == 0 or mdot.size != t.size:
            return None
        if not (np.all(np.isfinite(t)) and np.all(np.isfinite(mdot))):
            return None
        guc = mdot * float(q_reaction) / 1e6          # MW
        if not guc.size or float(np.max(guc)) <= 0.0:
            return None
        i_tepe = int(np.argmax(guc))
        if t.size > 1 and t[-1] > t[0]:
            ortalama = float(_trapezoid(guc, t) / (t[-1] - t[0]))
        else:
            ortalama = float(np.mean(guc))
        return {
            'peak_mw': float(guc[i_tepe]),
            'peak_time_s': float(t[i_tepe]),
            'initial_mw': float(guc[0]),
            'average_mw': ortalama,
        }

    def _calculate_thermal_analysis(self, curve=None):
        """Thermal analysis like other systems.

        ``curve`` çözülmüş itki/basınç eğrisidir. Isı açığa çıkma gücü onun
        kütle üretim serisinden okunur; eğri verilmezse o alan yayımlanmaz
        (bkz. ``_heat_release_power``).
        """
        # Heat transfer calculations
        convective_heat_flux = self._calculate_heat_flux()
        case_temperature = self._calculate_case_temperature()

        # OPUS DENETİM DÜZELTMESİ (#645): 'heat_release_rate_mw' önceden
        # rho_p·2500·Hacim/1e6 idi — bu bir ENERJİ (kütle×2500 J/kg = J) olup
        # zaman türevi içermiyordu, yani bir GÜÇ (MW) değildi; ayrıca 2500 J/kg
        # katı yakıt reaksiyon ısısı için ~1000× düşüktü. Doğru güç:
        #   P = ṁ_gen · Q_reaksiyon   [W]
        # (ṁ_gen'in HANGİ andan okunduğu aşağıda, P2B3-08 bloğunda düzeltildi
        # — bu düzeltme yalnız Q_reaksiyon'un tanımını getirmişti.)
        # Q_reaksiyon = cp·(Tc−298.15) (ürünleri alev sıcaklığına çıkaran entalpi;
        # APCP için ~6 MJ/kg, literatürle uyumlu). cp ve R yakıtın c* ve γ'sından
        # Vandenkerckhove/Γ bağıntısıyla türetilir (Sutton & Biblarz Eq. 3-32):
        #   Γ = √γ·(2/(γ+1))^((γ+1)/(2(γ−1))),  R = (c*·Γ)²/Tc,  cp = γR/(γ−1)
        #
        # ÖH KİTAP p1b (B11, seçenek F 2. tur; karar §28-36 Ş-2 A, ÖNEMLİ):
        # cp = γR/(γ−1) DONMUŞ bileşim formülüdür. Kayıt CEA'nın kaydırmalı
        # DENGE γ_s'sini taşıdığında (APCP 1,1338) bu formüle denge değeri
        # girerse reaksiyon ısısı cp'ye ikinci kez katılır: tepkime entalpisi
        # 5,94 → 7,84 MJ/kg (+%32), ısı salım gücü +%32, termal verim
        # 49,7 → 38,6 %. Bu yüzden cp'nin gamma'sı Bartz zinciriyle AYNI
        # kuraldan (``_frozen_gas_gamma``) gelir: kayıtta ölçülmüş donmuş oda
        # gamma'sı varsa o (CEA donmuş GAMMAs 1,1862 → cp ≈ CEA donmuş Cp
        # 1,9031 kJ/kgK), yoksa ``self.gamma`` nesnesinin KENDİSİ (öteki bütün
        # iticiler bit-özdeş). R'nin Eq. 3-32 türetimi ve jet hızı
        # GENLEŞMEDİR, denge gamma'sıyla kalır (``cp_expansion``).
        gamma = self.gamma
        gamma_fn = np.sqrt(gamma) * (2.0 / (gamma + 1.0)) ** (
            (gamma + 1.0) / (2.0 * (gamma - 1.0)))
        R_specific = (self.c_star * gamma_fn) ** 2 / self.T_c  # J/kg/K
        gamma_frozen = self._frozen_gas_gamma()
        cp_gas = gamma_frozen * R_specific / (gamma_frozen - 1.0)  # J/kg/K
        cp_expansion = gamma * R_specific / (gamma - 1.0)          # J/kg/K
        q_reaction = cp_gas * max(self.T_c - 298.15, 0.0)       # J/kg

        # ÖH D16 / kulvar kati / aşama 2 — P2B3-08
        # ------------------------------------------------------------------
        # Güç İKİ FARKLI ANIN ÇARPIMIYDI:
        #     mdot_gen = rho_p · A_burn(w=0) · r(Pc_tasarım)
        # A_burn t = 0 anının yüzeyi, r ise TASARIM basıncının yanma hızıydı.
        # v2.6.27/A1-1'den beri tasarım noktası w = 0 DEĞİL (boğaz maksimum
        # Kn'de açılıyor), yani bu iki çarpan aynı ana ait değil. ÖLÇÜLDÜ
        # (APCP 100/30/500 @ 40 bar; yayımlanan ⟷ eğri t=0 ⟷ eğri TEPE, MW):
        #   bates 10,36 ⟷ 11,13 ⟷ 11,20 | star 9,75 ⟷ 8,34 ⟷ 14,31
        #   wagon_wheel 14,41 ⟷ 11,55 ⟷ 24,89 (tepenin %57,9'u)
        # Yayımlanan sayı çözülmüş eğrinin HİÇBİR anına eşit değildi ve
        # yanındaki hiçbir alan hangi çalışma noktası olduğunu söylemiyordu.
        #
        # Artık güç çözücünün KENDİ kütle üretim serisinden okunur; başlık
        # alan TEPE gücüdür (yalıtım/kasa ısıl yükünü belirleyen değer),
        # t=0 ve ortalama değerler adıyla yanında yayımlanır ve çalışma
        # noktası açıkça beyan edilir. Eğri çözülmemişse sayı YAYIMLANMAZ.
        guc = self._heat_release_power(curve, q_reaction)

        # --- Termal (iç enerji dönüşüm) verimi: jet kinetik enerjisinin
        # reaksiyon ısısına oranı (Sutton & Biblarz 9. baskı Böl. 2, enerji
        # dönüşüm verimi). Sabit 85.2 yerine gerçek termokimyadan gelir.
        p_amb = getattr(self, 'ambient_pressure_bar', SEA_LEVEL_PRESSURE_BAR)
        pe_pc = min(max(p_amb / self.P_c, 1e-6), 0.999) if self.P_c > 0 else 0.999
        # Jet hızı izantropik GENLEŞMEDİR (Sutton & Biblarz Eş. 3-16): cp ve
        # üs aynı (denge) gamma'dan — motorun Isp'siyle aynı fizik.
        v_jet = np.sqrt(max(2.0 * cp_expansion * self.T_c
                            * (1.0 - pe_pc ** ((gamma - 1.0) / gamma)), 0.0))
        thermal_efficiency = (100.0 * 0.5 * v_jet ** 2 / q_reaction
                              if q_reaction > 0 else 0.0)

        insulation_effectiveness = self._insulation_effectiveness_percent()

        # --- Malzeme sıcaklık sınırları: materials_db (sabit 673 K değil)
        # V301/K-B (KT-11): kaydı olmayan malzemede (kompozit) sınır SESSİZCE
        # çeliğin 811 K'i OLMAZ. Eskiden ``except: case_limit = 811.0``
        # kompozit kasaya ~390 K uydurma ısıl pay yayımlıyordu. Artık sınır
        # ``solid_case_material_record``dan (materials_db / motorun ek
        # kaydı) okunur; sınır yoksa pay ve sınıf YAYIMLANMAZ, hüküm
        # "değerlendirilmedi" ve adlı bir uyarı basılır.
        case_material, _sy, _sf, _t = self._case_design()
        _kasa_kaydi = solid_case_material_record(case_material)
        case_limit = (_kasa_kaydi or {}).get('max_service_temp_k')
        case_limit = float(case_limit) if case_limit else None
        case_limit_status = (SOLID_CASE_LIMIT_STATUS_RECORD
                             if case_limit is not None
                             else SOLID_CASE_LIMIT_STATUS_NO_RECORD)
        grain_limit = float(self._grain_mechanics()['cure_temperature_k'])
        _kasa_sicaklik_durumu = dict(getattr(
            self, '_case_temperature_status', None)
            or {'source': 'solved', 'reason': None})
        margin = (case_limit - case_temperature
                  if case_limit is not None and case_temperature is not None
                  else None)

        if case_temperature is None:
            # V301/K-D: kasa sıcaklığı ÇÖZÜLMEDİ — pay ve sınıf yayımlanmaz,
            # neden adıyla söylenir (malzeme sınırı uyarısı burada yanlış
            # sebep olurdu).
            rating = SOLID_CASE_THERMAL_NOT_EVALUATED
            _uyari = _w('warn.solid.case_temperature_not_solved', 'warning')
            if all(_warning_identity(_uyari) != _warning_identity(u)
                   for u in self.design_warnings
                   if isinstance(u, dict)):
                self.design_warnings.append(_uyari)
        elif margin is None:
            rating = SOLID_CASE_THERMAL_NOT_EVALUATED
            _uyari = _w('warn.solid.case_thermal_not_evaluated', 'warning',
                        material=str(case_material))
            if all(_warning_identity(_uyari) != _warning_identity(u)
                   for u in self.design_warnings
                   if isinstance(u, dict)):
                self.design_warnings.append(_uyari)
        elif margin > 0.5 * case_limit:
            rating = 'Excellent'
        elif margin > 0.2 * case_limit:
            rating = 'Adequate'
        elif margin > 0:
            rating = 'Marginal'
        else:
            rating = 'Inadequate — case exceeds its service temperature'

        return {
            'combustion_thermal': {
                'flame_temperature_k': self.T_c,
                'heat_release_rate_mw': (guc['peak_mw'] if guc else None),
                'heat_release_rate_initial_mw': (
                    guc['initial_mw'] if guc else None),
                'heat_release_rate_average_mw': (
                    guc['average_mw'] if guc else None),
                'heat_release_rate_peak_time_s': (
                    guc['peak_time_s'] if guc else None),
                'heat_release_rate_operating_point': (
                    'peak of the solved burn' if guc else None),
                'heat_release_rate_status': ('solved' if guc else 'not_solved'),
                'heat_release_rate_basis': (
                    'P(t) = mdot_gen(t) * q_reaction, where mdot_gen is the '
                    "solver's own mass generation series (rho_p*Ab(t)*r(t)) "
                    'and q_reaction is the reaction_enthalpy_mj_kg beside '
                    'this field. heat_release_rate_mw is the PEAK of that '
                    'series (the value the insulation and case have to take); '
                    'the t = 0 and time-weighted average values are published '
                    'next to it. It is no longer Ab(0)*r(Pc_design), which '
                    'multiplied the t = 0 burning surface by the '
                    'design-pressure burn rate - two different instants - and '
                    'matched no point of the solved curve. Source: Sutton & '
                    'Biblarz, Rocket Propulsion Elements 9th ed., Ch. 12.'
                    if guc else
                    'Not published: the burn was not solved on this call, so '
                    'no operating point exists to report the heat release '
                    'rate at. No number is substituted.'),
                'thermal_efficiency_percent': float(thermal_efficiency),
                'jet_velocity_ms': float(v_jet),
                'reaction_enthalpy_mj_kg': float(q_reaction / 1e6),
                'thermal_efficiency_definition': (
                    'jet kinetic energy / reaction enthalpy '
                    '(0.5*v_jet^2 / q_reaction)'),
            },
            'heat_transfer': {
                'convective_heat_flux_kw_m2': convective_heat_flux,
                'case_temperature_k': case_temperature,
                # V301/K-D: kasa sıcaklığının KAYNAĞI (çözüldü / çözülmedi)
                # ve çözülmediyse nedeni; çözülmeyen değer yerine sayı yok.
                'case_temperature_source': _kasa_sicaklik_durumu['source'],
                'case_temperature_not_solved_reason': (
                    _kasa_sicaklik_durumu.get('reason')),
                'insulation_effectiveness': float(insulation_effectiveness),
                # v2.6.26 (Y2): bu alan LİNER kalınlığını 'yalıtım' adıyla
                # raporluyordu; kullanıcının yalıtım girdisi hiç görünmüyordu.
                # Üç kalem de adıyla verilir ve toplam, ısıl direncin
                # kullandığı değerle AYNIDIR.
                'insulation_thickness_mm': float(
                    getattr(self, 'insulation_thickness_m', 0.0) * 1000),
                'liner_thickness_mm': float(
                    getattr(self, 'liner_thickness',
                            SOLID_INSULATION['thickness_m']) * 1000),
                'thermal_barrier_thickness_mm': float(
                    self._thermal_barrier_thickness() * 1000),
                'insulation_effectiveness_definition': (
                    'R_insulation / (R_gas + R_insulation) from the series '
                    'resistance chain ((t_insulation + t_liner)/k over 1/h_g)'),
                'thermal_protection_rating': rating,
                # ÖH D18 (P2B3-14): hüküm KASA marjından türetilir; kapsamı
                # adıyla yazılır ki 'Adequate' rozeti grain limiti için de
                # okunmasın.
                'thermal_protection_rating_scope': (
                    'case wall only: derived from the case margin '
                    '(material_temperature_limits.safety_margin_k). No grain '
                    'temperature is solved, so the grain limit is not part of '
                    'this rating.'),
                'case_temperature_model': (
                    'Lumped-capacitance transient through insulation + case '
                    'with Bartz gas-side coefficient; depends on burn time, '
                    'wall and liner thickness and material properties.'),
            },
            'thermal_management': {
                'cooling_requirements': 'Passive',
                'material_temperature_limits': {
                    'case_max_temp_k': case_limit,
                    # V301/K-B (KT-11): sınırın kaynağı adıyla; kayıt yoksa
                    # pay None ve hüküm "değerlendirilmedi".
                    'case_limit_status': case_limit_status,
                    'case_limit_basis': (
                        'max_service_temp of the case material record '
                        '(materials_db.temperature_limits service_K)'
                        if case_limit is not None else
                        f"no temperature limit on record for case material "
                        f"'{case_material}' (no sourced resin Tg / service "
                        f"temperature in this repository); the thermal "
                        f"verdict was NOT evaluated and no steel value was "
                        f"substituted"),
                    'grain_max_temp_k': grain_limit,
                    'safety_margin_k': (float(margin) if margin is not None
                                        else None),
                    # ÖH D18 (P2B3-14): bu marj YALNIZ KASA marjıdır
                    # (case_max_temp_k - case_temperature_k) ama İKİ limitin
                    # altında ETİKETSİZ duruyordu. ÖLÇÜLDÜ (APCP bates
                    # 100/30/500 @40 bar, çelik kasa): case_max 811,0 /
                    # grain_max 333,0 / safety_margin +285,59 -> kullanıcı
                    # "+285,6 K marjım var" diye okuyor, oysa o sayının
                    # grain limitiyle hiçbir ilgisi yok. Sayı doğruydu,
                    # eksik olan hangi limite ait olduğuydu; artık alan ADIYLA
                    # söylüyor ve grain tarafı UYDURULMUYOR.
                    'safety_margin_applies_to': 'case_max_temp_k',
                    'safety_margin_basis': (
                        'case_max_temp_k minus the computed case wall '
                        'temperature (heat_transfer.case_temperature_k). It '
                        'is the CASE margin only and says nothing about the '
                        'grain limit listed beside it.'),
                    'grain_safety_margin_k': None,
                    'grain_safety_margin_status': 'NOT_MODELLED',
                    'grain_safety_margin_basis': (
                        'HRMA does not solve a grain bulk temperature, so no '
                        'margin against grain_max_temp_k can be published. '
                        'The case wall temperature is NOT the grain '
                        'temperature (the insulation and liner sit between '
                        'them), so it must not be substituted here.'),
                    # Kalem 10 (P3): bu sayı ÖLÇÜLMÜŞ bir servis limiti
                    # değildir; seçili yakıtın kürleme sıcaklığıdır ve
                    # yumuşama/depolama üst sınırı için vekil olarak
                    # kullanılır. Etiketsiz bırakıldığında kullanıcı bunu
                    # yakıtın tutuşma/bozunma sıcaklığı sanıyordu.
                    'grain_max_temp_basis': (
                        'limit = propellant cure temperature (softening '
                        'proxy) from the grain mechanical record, not a '
                        'measured service limit'),
                    'grain_property_source': self._grain_mechanics()['source'],
                }
            }
        }
    
    @staticmethod
    def _split_composition(text):
        """'Aluminum ~16% + PBAN binder ~14%' -> [('aluminum', 16.0), ...].

        Merkezi katalog bileşimi YAYIMLANMIŞ METİN olarak tutar; burada yalnız
        o metindeki yüzdeler okunur. Yüzde yazmayan kayıttan sayı ÜRETİLMEZ
        (boş liste döner) — kalem 12-14'ün kuralı budur.
        """
        parts = []
        for chunk in re.split(r'\s*\+\s*', str(text or '')):
            match = re.search(r'(\d+(?:\.\d+)?)\s*%', chunk)
            if not match:
                continue
            label = re.sub(r'[~]?\d+(?:\.\d+)?\s*%', '', chunk)
            label = re.sub(r'\s{2,}', ' ', label).strip(' ,;')
            parts.append((label, float(match.group(1))))
        return parts

    def _published_mixture(self):
        """Seçili yakıtın YAYIMLANMIŞ karışım oranları (katalogtan).

        Kalem 12-14 (P3). Eski kod iki dallı bir sabitti::

            is_apcp = self.propellant_type == 'apcp'
            'oxidizer_percent': 68 if is_apcp else 75

        Yani KNDX, KNSU, çift bazlı ve siyah barut AYNI üç sayıyı alıyordu
        (75/15/8) — oysa KN-şeker karışımı yayımlanmış olarak %65/%35'tir ve
        BAĞLAYICI İÇERMEZ. APCP dalındaki 12'lik bağlayıcı da kayda
        dayanmıyordu: merkezi katalogdaki 'htpb_ap_al' kaydının kendi
        bileşimi %68 AP + %18 Al + %14 HTPB olarak zaten yazılıydı. Artık
        oranlar o kaydın 'oxidizer'/'fuel' alanlarından okunur; kayıtta
        yüzde yoksa (ör. homojen çift bazlı) sayı UYDURULMAZ, alan boş
        bırakılır ve 'status' bunu söyler.

        Bağlayıcı ayrımı kaydın kendi sözcüğünden gelir ('... binder ...') —
        şeker yakıtlarında bağlayıcı kalemi yoktur ve bu yüzden yayınlanmaz.
        """
        key = _catalog_key_for(self.propellant_type)
        rec = _get_propellant_safe(key) if key else None
        if not rec:
            return {
                'status': 'not_tabulated',
                'oxidizer_percent': None,
                'fuel_percent': None,
                'binder_percent': None,
                'additives_percent': None,
                'basis': (f"No formulation record exists for "
                          f"'{self.propellant_type}' in the central propellant "
                          f"catalogue; mixture percentages are left empty "
                          f"rather than guessed."),
            }

        oxidizer_parts = self._split_composition(rec.get('oxidizer'))
        fuel_parts = self._split_composition(rec.get('fuel'))
        components = ([{'role': 'oxidizer', 'label': label, 'percent': pct}
                       for label, pct in oxidizer_parts]
                      + [{'role': ('binder' if 'binder' in label.lower()
                                   else 'fuel'),
                          'label': label, 'percent': pct}
                         for label, pct in fuel_parts])

        def _total(role):
            vals = [c['percent'] for c in components if c['role'] == role]
            return float(sum(vals)) if vals else None

        oxidizer_percent = _total('oxidizer')
        fuel_percent = _total('fuel')
        binder_percent = _total('binder')
        tabulated = any(v is not None for v in
                        (oxidizer_percent, fuel_percent, binder_percent))
        return {
            'status': 'tabulated' if tabulated else 'not_tabulated',
            'oxidizer_percent': oxidizer_percent,
            'fuel_percent': fuel_percent,
            'binder_percent': binder_percent,
            # Katkı maddesi oranı hiçbir katalog kaydında tablolanmıyor:
            # eski sabit %2 kaldırıldı, yerine sayı KONULMADI.
            'additives_percent': None,
            'components': components,
            'oxidizer_description': rec.get('oxidizer'),
            'fuel_description': rec.get('fuel'),
            'propellant_record': key,
            'basis': (
                f"Published formulation of catalogue record '{key}' "
                f"({rec.get('name', key)}); percentages are read from that "
                f"record, not computed from this design. "
                f"Source: {rec.get('source', 'see propellants_db')}"
                if tabulated else
                f"Catalogue record '{key}' states the composition without "
                f"percentages (e.g. homogeneous double-base); no numbers are "
                f"reported rather than guessed."),
        }

    def _calculate_manufacturing_analysis(self):
        """İmalat REÇETESİ - bu tasarımdan hesaplanmış değerler değil.

        v2.6.26: bu blok etiketsizdi ve kullanıcı bunu kendi motorunun
        hesaplanmış imalat gereksinimi sanabiliyordu. İki gerçek sorun vardı:
        (1) kasa malzemesi 'AISI 4130' olarak SABİTTİ — kullanıcı alüminyum
        seçse bile burada çelik yazıyordu, oysa ``self.case_material``
        formdan geliyor ve yapısal hesapta zaten kullanılıyor;
        (2) tolerans/yüzey pürüzlülüğü değerleri HRMA tarafından
        hesaplanmıyor ama hesaplanmış gibi duruyordu.
        """
        case_material = getattr(self, 'case_material', None) or 'NOT_DEFINED'
        return {
            'basis': ('Generic production recipe for this propellant family and '
                      'case material. Percentages, cure schedule and tolerances '
                      'are published practice, not computed from this design.'),
            'propellant_manufacturing': {
                'mixing_requirements': self._published_mixture(),
                'curing_process': {
                    # Kürleme sıcaklığı, yapısal zincirin kullandığı kürleme
                    # sıcaklığının TA KENDİSİdir (aynı kavram iki yerde iki
                    # farklı sayı olamaz): _grain_mechanics kaydı.
                    'temperature_k': float(
                        self._grain_mechanics()['cure_temperature_k']),
                    # FAZ 5 / H4-11 — arayüz bu değeri kendisi Celsius'a
                    # çeviriyor ve 273,15 yerine 273 kullanıyordu
                    # (templates/solid.html: `v => v - 273`). Çevrim artık
                    # doğru sabitle SUNUCUDA yapılır ve hazır yayımlanır;
                    # aynı büyüklüğün iki yerde iki farklı sabitle
                    # çevrilmesine gerek kalmaz.
                    'temperature_c': float(
                        self._grain_mechanics()['cure_temperature_k']) - 273.15,
                    'time_hours': 24,
                    'pressure_kpa': 101.325,
                    'humidity_control': 'Required',
                    'basis': ('Cure temperature is the value used by the grain '
                              'structural chain (propellant mechanical '
                              'record); dwell time and humidity are typical '
                              'practice - follow your binder supplier data '
                              'sheet.'),
                },
                'quality_requirements': {
                    'density_tolerance_percent': 2.0,
                    'void_content_max_percent': 0.5,
                    'burn_rate_tolerance_percent': 5.0,
                    # v2.6.26 — BEYAN BLOĞUN KENDİSİNE KONDU. Üst blokta
                    # (manufacturing_analysis.basis) benzer bir cümle vardı
                    # ama üç seviye yukarıdaydı; bu üç sayıyı okuyan
                    # kullanıcı onu görmüyordu.
                    'basis': (
                        'density tolerance, void content max and burn rate '
                        'tolerance are a published general manufacturing '
                        'acceptance band for composite solid propellant; NOT '
                        'computed from this design and NOT a measured quality '
                        'value of your batch. Agree the real limits with your '
                        'test authority.'),
                }
            },
            'case_manufacturing': {
                'material_specs': {
                    # Kullanıcının seçtiği malzeme; yapısal hesapla AYNI kaynak.
                    'case_material': case_material,
                    'heat_treatment': 'NOT_DEFINED',
                    'surface_finish_ra_um': None,
                },
                'machining_tolerances': {
                    'note': ('Tolerances and surface finish are NOT_DEFINED by '
                             'HRMA; they belong to your detail drawings.'),
                },
            },
            'assembly_process': {
                'grain_installation': 'Press fit with thermal barrier',
                'inhibitor_application': 'Spray coating',
                'quality_checks': ['Pressure test', 'X-ray inspection', 'Dimensional check']
            }
        }
    
    def _calculate_flight_simulation(self):
        """Uçuş büyüklükleri MOTOR seviyesinde hesaplanamaz — 'not_modelled'.

        2026-07-23 denetimi (dış inceleme bulgusu): bu metot apoje 3500 m,
        maksimum hız 450 m/s, maksimum ivme 8.5 g, uçuş süresi 45 s, itki/
        ağırlık 4.2, stabilite marjı 2.1, Cd 0.45, faydalı yük 0.5 kg ve
        GÖREV BAŞARI OLASILIĞI 0.92 değerlerini HESAPLAMADAN döndürüyordu.
        Hepsi sabit yazılmıştı ve doğrudan sonuç sözlüğüne giriyordu.

        Bu büyüklüklerin hiçbiri motor verisinden türetilemez: araç kuru
        kütlesi, gövde çapı, sürükleme katsayısı, fırlatma açısı ve rüzgâr
        bilinmeden apoje de, T/W de, stabilite marjı da tanımsızdır. Görev
        başarı olasılığı ise güvenilirlik verisi olmadan tümüyle uydurmadır.

        Doğru yol: uçuş büyüklükleri araç parametreleriyle birlikte
        ``hrma.analysis.trajectory_analysis.TrajectoryAnalyzer`` (2-DOF,
        sürüklemeli) ya da ``six_dof_trajectory`` ile çözülür; motor bu
        çözüme itki eğrisi ve kütle akışı olarak GİRDİ verir. Uygulama bunu
        zaten ayrı uçuş analizi akışında yapar.

        Bu metot artık sahte sayı üretmez; ne modellenmediğini ve nereye
        bakılacağını açıkça bildirir (bkz. tests/test_no_fabrication.py).
        """
        return {
            'status': 'not_modelled',
            'reason': (
                'Uçuş büyüklükleri (apoje, hız, ivme, T/W, stabilite marjı, '
                'faydalı yük) araç parametreleri olmadan motor verisinden '
                'türetilemez. Görev başarı olasılığı ayrıca güvenilirlik '
                'verisi gerektirir ve bu modelde yoktur.'),
            'use_instead': (
                'Uçuş analizi akışı: TrajectoryAnalyzer (2-DOF, sürüklemeli) '
                'veya six_dof_trajectory — motorun itki eğrisi ve kütle akışı '
                'girdi olarak verilir, araç kütlesi/çapı/Cd ayrıca istenir.'),
            'trajectory_analysis': None,
            'vehicle_dynamics': None,
            'mission_capability': None,
        }
    
    def run_monte_carlo(self, n_samples=300, seed=42):
        """Üretim toleransı belirsizlikleriyle Monte Carlo performans analizi.

        1σ belirsizlikler ve başarı ölçütü SOLID_MC_TOLERANCE_MODEL'den gelir
        (TEK tanım noktası): örnekleme de, kullanıcıya gösterilen 'criteria'
        açıklaması da aynı tablodan üretilir; ikisi ayrışamaz.
        Sabit tohum → tekrarlanabilir sonuç (aynı girdi aynı çıktıyı verir).
        """
        mc = SOLID_MC_TOLERANCE_MODEL
        n_samples = int(max(20, min(n_samples, 2000)))
        rng = np.random.default_rng(int(seed))

        nominal = self.calculate_performance()
        if isinstance(nominal, dict) and nominal.get('error'):
            return {
                'error': f"Nominal hesap başarısız: {nominal['error']}",
                'error_i18n': _w(
                    'warn.solid.monte_carlo_nominal_failed', 'critical',
                    reason=nominal['error'],
                    reason_i18n=nominal.get('error_i18n')),
            }
        nom_thrust = float(nominal['average_thrust'])
        nom_isp = float(nominal['specific_impulse'])
        nom_burn = float(nominal['burn_time'])
        nom_pmax = float(np.max(nominal['thrust_curve']['pressure']))

        # ------------------------------------------------------------------
        # DONANIM SABİT, YAKIT PARTİSİ DEĞİŞKEN (T19, 2026-08-03)
        #
        # Ölçülen kusur: her örneklem kendi (bozulmuş) a, n, ρ, c* değerleriyle
        # YENİ bir motor kuruyordu ve boğaz alanı da o değerlerden
        # boyutlandırılıyordu. Boğaz A_t = ρ·Ab0·r(Pc)·c*/(Pc·1e5) tam olarak
        # Pc'yi geri verecek şekilde seçildiği için t=0 basıncı YAPISAL olarak
        # tasarım Pc'sine kilitleniyordu: 300 koşuda tepe basıncı
        # σ = 0,0457 bar / CV %0,11 (itki CV'si %3,9 iken), yani
        # 'tepe basıncı ≤ nominal×1,2' kabul ölçütü HİÇ başarısız olamıyordu
        # ama %98 başarı oranına dahil ediliyordu — sahte bir gösterge.
        #
        # Gerçek üretim toleransı analizinde işlenmiş boğaz TEKTİR; değişen
        # yakıttır. Denge basıncı o zaman Pc ∝ a^(1/(1-n)) ile gerçekten
        # oynar. Nominal boğaz bir kez ölçülür ve her örnekleme sabitlenir.
        # ------------------------------------------------------------------
        nom_throat_area, _nom_flux = self._design_throat_area()
        if not np.isfinite(nom_throat_area) or nom_throat_area <= 0.0:
            nom_throat_area = None

        # V301/K-D: ``initial_temp`` örnek motora AYNEN geçer ve a çarpanı
        # kurucunun DÜZELTİLMEMİŞ a'sına uygulanır (aşağıda): sıcaklık
        # düzeltmesi örnekte bir kez, nominaldeki gibi uygulanır. Eski yol
        # anahtarı atıp düzeltilmiş a'yı geçiriyordu; parçalı yanma hızı
        # yasasında (KN-şeker ön ayarları) a/n ölüdür ve düzeltme
        # ``initial_grain_temperature``den okunur, yani örnekte sessizce
        # KAYBOLUYORDU (ölçüldü, örnek KNDX projesi T0 = 298 K: bozulmasız
        # örnek Isp 124,246 ⟷ nominal 125,284 s; K-D/uq_once.json).
        base_ov = dict(self.overrides)
        a_kurucu = float(self._ctor_args['burn_rate_a'])

        # ÖH D15 a2 (P2B3-02): bu motorun yanma hızı parçalı rejim
        # tablosundan mı okunuyor? Öyleyse a/n ctor argümanları ölüdür ve
        # tolerans taban hıza uygulanır (bkz. pin_burn_rate_lot).
        law_active = bool(getattr(self, 'burn_rate_law_key', None))

        keys = ('thrust', 'isp', 'burn_time', 'max_pressure')
        samples = {k: [] for k in keys}
        n_success = 0
        n_failed_runs = 0

        for _ in range(n_samples):
            ov = dict(base_ov)
            # V301/K-D (K-C1 AÇIK 1 / NK-53 kalanı): yoğunluk ve c* örneği
            # motorun PARTİ kanalına çarpan olarak gider (``propellant_lot``)
            # ve örnek motorun KENDİ kaynağına uygulanır. Eski yol c*'ı
            # ``char_velocity`` girdisi olarak basıyordu: CEA'lı nominalde
            # örnek motor ``user_entered`` termokimya yoluna geçiyor (γ, T_c,
            # M kaydın tek basınç değerleri), yani dağılımın merkezi nominal
            # motor DEĞİLDİ. Çarpan teorik c*'a uygulanır, yanma verimi
            # örnekte bir kez (base_ov) çarpılır — eski TEORİK c* kuralı
            # (2026-07-19, eta iki kez çarpılmaz) aynen korunur. Çekiliş
            # sırası (yoğunluk, c*, a, n) DEĞİŞMEDİ.
            parti = {'density_scale': 1.0 + rng.normal(
                0.0, mc['density_rel_sigma'])}
            parti['c_star_scale'] = 1.0 + rng.normal(
                0.0, mc['c_star_rel_sigma'])
            args = dict(self._ctor_args)
            eps_a = rng.normal(0.0, mc['burn_rate_a_rel_sigma'])
            args['burn_rate_a'] = a_kurucu * (1.0 + eps_a)
            # Alt sınır -0.5: KN-şeker plateau/mesa rejimlerinde n negatif
            # (burn_rate_db preset'leri); eski 0.1 tabanı fiziği sessizce
            # değiştiriyordu (app.py doğrulama aralığıyla tutarlı).
            args['burn_rate_n'] = float(np.clip(
                self.n + rng.normal(0.0, mc['burn_rate_n_abs_sigma']),
                -0.5, 0.99))
            # Kırpma sonrası GERÇEKLEŞEN üs kayması — parçalı yola da bu
            # uygulanır ki iki yol aynı bozulmayı görsün.
            d_n = float(args['burn_rate_n']) - float(self.n)
            try:
                sample_engine = SolidRocketEngine(
                    overrides=ov, propellant_lot=parti, **args)
                if nom_throat_area is not None:
                    sample_engine.pin_throat_area(nom_throat_area)
                # ÖH D15 a2 (P2B3-02): parçalı rejim yasası etkinse a/n
                # ctor argümanları ÖLÜdür; aynı tolerans taban hıza
                # (1+eps_a)*P^d_n çarpanı olarak uygulanır (özdeş form).
                if law_active:
                    sample_engine.pin_burn_rate_lot(
                        scale=1.0 + eps_a, exponent_shift=d_n)
                r = sample_engine.calculate_performance()
                if isinstance(r, dict) and r.get('error'):
                    raise ValueError(r['error'])
                s_thrust = float(r['average_thrust'])
                s_isp = float(r['specific_impulse'])
                s_burn = float(r['burn_time'])
                s_pmax = float(np.max(r['thrust_curve']['pressure']))
            except Exception:
                n_failed_runs += 1
                continue
            samples['thrust'].append(s_thrust)
            samples['isp'].append(s_isp)
            samples['burn_time'].append(s_burn)
            samples['max_pressure'].append(s_pmax)
            if (abs(s_thrust - nom_thrust) <= mc['thrust_band_rel'] * nom_thrust
                    and abs(s_isp - nom_isp) <= mc['isp_band_rel'] * nom_isp
                    and s_pmax <= mc['max_pressure_factor'] * nom_pmax):
                n_success += 1

        def _stats(vals, nom):
            if not vals:
                return {}
            arr = np.asarray(vals, dtype=float)
            mean = float(np.mean(arr))
            return {
                'nominal': nom,
                'mean': mean,
                'std': float(np.std(arr)),
                'cv_percent': float(np.std(arr) / mean * 100.0) if mean else 0.0,
                'p5': float(np.percentile(arr, 5)),
                'p95': float(np.percentile(arr, 95)),
            }

        return {
            'n_samples': n_samples,
            'n_failed_runs': n_failed_runs,
            'success_rate_percent': round(100.0 * n_success / n_samples, 1),
            # Açıklama metni ÖLÇÜTÜN KENDİSİNDEN üretilir (sabit metin değil):
            # yukarıdaki kabul testi ile bu satır aynı sayıları kullanır.
            'criteria': (
                f"İtki ±%{mc['thrust_band_rel'] * 100:g}, "
                f"Isp ±%{mc['isp_band_rel'] * 100:g}, "
                f"tepe basıncı ≤ nominal×{mc['max_pressure_factor']:g}; "
                f"1σ: a ±%{mc['burn_rate_a_rel_sigma'] * 100:g}, "
                f"n ±{mc['burn_rate_n_abs_sigma']:g}"
                + (f" (parçalı '{self.burn_rate_law_key}' yasasının taban "
                   f"hızına özdeş çarpanla uygulandı)" if law_active else "")
                + f", yoğunluk ±%{mc['density_rel_sigma'] * 100:g}, "
                f"C* ±%{mc['c_star_rel_sigma'] * 100:g}"),
            # Makine tarafı: arayüz/dışa aktarım metni ayrıştırmak zorunda
            # kalmasın diye ölçütün sayıları da verilir.
            'criteria_detail': dict(
                mc,
                # ÖH D15 a2 (P2B3-02): a/n toleransının HANGİ yoldan
                # uygulandığı beyan edilir. Metin ile koşulan analiz
                # ayrışamaz: 'burn_rate_law_sampling' etkinse taban hız
                # (1+eps_a)*Pc^d_n ile ölçeklenir, aksi hâlde a/n doğrudan
                # bozulur. İki yol matematiksel olarak ÖZDEŞ bozulmadır.
                burn_rate_law=(getattr(self, 'burn_rate_law_key', None)),
                burn_rate_law_sampling=(
                    'base rate scaled by (1+eps_a)*Pc^d_n, the exact '
                    'equivalent of perturbing a and n in r = a*Pc^n'
                    if law_active else
                    'a and n perturbed directly on the single-exponent law'),
            ),
            # T19: hangi büyüklüğün DONANIM (sabit), hangisinin PARTİ
            # (değişken) sayıldığı çıktıda beyan edilir — tepe basıncının
            # neden oynayabildiği (ya da oynamadığı) buradan okunur.
            'fixed_hardware': {
                'throat_area_m2': nom_throat_area,
                'throat_diameter_mm': (
                    2000.0 * float(np.sqrt(nom_throat_area / np.pi))
                    if nom_throat_area else None),
                'basis': (
                    'the machined throat is a single piece of hardware and is '
                    'held at the nominal design value for every sample; only '
                    'the propellant lot (a, n, density, c*) varies, so the '
                    'chamber pressure is free to move with the lot'),
            },
            'thrust': _stats(samples['thrust'], nom_thrust),
            'isp': _stats(samples['isp'], nom_isp),
            'burn_time': _stats(samples['burn_time'], nom_burn),
            'max_pressure': _stats(samples['max_pressure'], nom_pmax),
            'histograms': {
                'thrust': [round(v, 1) for v in samples['thrust']],
                'isp': [round(v, 2) for v in samples['isp']],
            },
        }

    def _calculate_cost_analysis(self):
        """Parametrik maliyet TAHMİNİ — kütle ve boyutlardan ölçeklenir.

        2026-07-13: eski sürüm motor boyutundan bağımsız sabit değerler
        döndürüyordu (100 g motor da 100 kg motor da 240$ malzeme). Artık
        grain hacmi, kasa kütlesi ve boğaz çapından ölçeklenen birim-fiyat
        modeli kullanılır. Birim fiyatlar SOLID_COST_PARAMS'ta tek noktada.
        Bu bir TAHMİNDİR; sonuç sözlüğündeki 'basis' alanı varsayımları belirtir.
        """
        p = SOLID_COST_PARAMS

        # Kütleler (kg)
        # ÖH D16/kati (P2B3-04): yakıt kütlesi artık grain tipini GÖREN tek
        # kaynaktan (``_propellant_volume``) gelir. Eski satır her tipte
        # dairesel annulus hesaplıyordu; ölçülen sapma (once.json P2B3-04,
        # aynı geometri): end_burner -%9,00 · star +%9,89 ·
        # wagon_wheel +%8,01. Aynı motorun yakıt kütlesi performans
        # zincirinde bir, maliyet zincirinde başka sayıydı.
        grain_vol = self._propellant_volume()
        m_prop = grain_vol * self.rho_p

        # FAZ 5 / H4-8 DÜZELTMESİ — kasa MALİYETİ ile kasa KÜTLESİ iki ayrı
        # modelden besleniyordu. Ölçüm (aynı motor, `case_material` override):
        #   case_material     kütle ρ   maliyet ρ   $/kg   kasa $
        #   (yok)               7800      2700       15     32,9
        #   steel_4130          7800      2700       15     32,9
        #   titanium_6al4v      4430      2700       15     32,9
        # Yani katalog anahtarı verilen HER durumda maliyet modeli sessizce
        # alüminyuma düşüyordu ve titanyum kasa 9,8 kat ucuz fiyatlanıyordu.
        # Cidar da ayrıydı: maliyet 0,045·D (4,5 mm), yapısal analiz 2,4 mm.
        # Artık kütle zinciriyle AYNI tek kaynaklardan beslenir:
        #   malzeme + cidar  -> _case_design()
        #   yoğunluk         -> _case_density()
        #   kasa geometrisi  -> _case_inner_diameter() / _case_inner_length()
        #   kapak payı       -> SOLID_CASE_CLOSURE_MASS_FRACTION
        case_material, _sy_cost, _sf_cost, wall = self._case_design()
        rho_case = self._case_density()
        m_case = (np.pi * self._case_inner_diameter() * self._case_inner_length()
                  * wall * rho_case) * (1.0 + SOLID_CASE_CLOSURE_MASS_FRACTION)
        cost_family = SOLID_CASE_COST_FAMILY.get(
            str(case_material or '').strip().lower())
        # ÖH D21 a1 (P2B1-12): tablo artık doğrudan USD/kg taşır; eskiden
        # (yoğunluk, USD/kg) ikilisinin [1]'i okunuyor, [0] hiç okunmuyordu.
        usd_case = (p['case_materials'][cost_family]
                    if cost_family else None)

        d_t = self._estimate_throat_diameter()
        m_nozzle = min(max(0.8 * (d_t / 0.05) ** 2, 0.2), 60.0)
        # ÖH D16/kati (P2B3-05): yalıtım kütlesi de kuru-kütle zincirinin
        # TEK kaynağından okunur. Eski satır kalınlığı 3 mm'ye, yoğunluğu
        # 1200 kg/m3'e ÇIPLAK sabitliyordu; kullanıcının
        # ``insulation_thickness`` girdisi maliyete hiç girmiyordu.
        # Ölçüm (once.json P2B3-05, aynı motor): kalınlık 0 / 3 / 12 mm
        # için maliyet modeli her seferinde 0,5655 kg diyordu; kütle
        # zinciri ise 0,0000 / 0,6989 / 3,0401 kg. Yani 12 mm yalıtım
        # seçen kullanıcı yalıtımını 5,4 kat eksik fiyatlandırılmış
        # görüyordu ve 0 mm'de olmayan yalıtımın parasını ödüyordu.
        m_insul = float(self._dry_mass_breakdown()['insulation_kg'])

        # ÖH D15 a2 (P2B1-05): yakıt fiyatı da kasa malzemesiyle AYNI desenle
        # çözülür — aile eşlemesi yoksa kalem fiyatlanmaz, sessiz 'default'a
        # düşülmez (bkz. SOLID_PROPELLANT_COST_FAMILY).
        prop_family = SOLID_PROPELLANT_COST_FAMILY.get(
            str(self.propellant_type or '').strip().lower())
        usd_prop = (p['propellant_usd_per_kg'][prop_family]
                    if prop_family else None)

        mat = {
            'nozzle': m_nozzle * p['nozzle_usd_per_kg'],
            'insulation': m_insul * p['insulation_usd_per_kg'],
        }
        if usd_prop is not None:
            mat['propellant'] = m_prop * usd_prop
        if usd_case is not None:
            mat['case_materials'] = m_case * usd_case
        mat['hardware'] = 0.15 * sum(mat.values())
        mat = {k: round(v, 1) for k, v in mat.items()}
        eksik_kalem = []
        if usd_prop is None:
            # Bu yakıtın birim fiyatı modelde YOK. Sessizce başka bir yakıta
            # düşmek yerine kalem fiyatlanmaz — sayı uydurulmaz.
            mat['propellant'] = None
            eksik_kalem.append('propellant')
        if usd_case is None:
            # Bu malzemenin birim fiyatı modelde YOK. Sessizce başka bir
            # malzemeye düşmek yerine kalem fiyatlanmaz.
            mat['case_materials'] = None
            eksik_kalem.append('case_materials')
        if eksik_kalem:
            # Eksik kalem varken toplam "eksik toplam" olarak yayımlanmaz.
            mat['total_materials'] = None
        else:
            mat['total_materials'] = round(sum(mat.values()), 1)
        mat['unpriced_items'] = eksik_kalem
        mat['propellant_cost_basis'] = (
            'unit price from the "%s" row of '
            'SOLID_COST_PARAMS[\'propellant_usd_per_kg\'] (%.1f USD/kg), '
            'mapped from propellant "%s" through SOLID_PROPELLANT_COST_FAMILY'
            % (prop_family, usd_prop, self.propellant_type)
            if prop_family else
            'not_priced: propellant "%s" has no unit price row in '
            'SOLID_COST_PARAMS[\'propellant_usd_per_kg\'] and the model does '
            'NOT substitute another propellant' % self.propellant_type)
        mat['case_mass_kg'] = round(float(m_case), 4)
        mat['case_cost_basis'] = (
            'case shell + closures from the SAME source as the dry-mass chain '
            '(_case_design wall %.2f mm, _case_density %.0f kg/m3, closures '
            '%.0f%%); unit price from the "%s" family'
            % (wall * 1000.0, rho_case,
               SOLID_CASE_CLOSURE_MASS_FRACTION * 100.0, cost_family)
            if cost_family else
            'not_priced: case material "%s" has no unit price in '
            'SOLID_COST_PARAMS[\'case_materials\'] and the model does NOT '
            'substitute another material' % case_material)

        # İşçilik: süreler kütle/boyutla ölçeklenir, saat ücreti tek katsayı
        hr = p['labor_usd_per_hour']
        hours = {
            'propellant_mixing': 0.5 + 0.05 * m_prop,
            'casting': 0.5 + 0.04 * m_prop,
            'curing': 0.3 + 0.01 * m_prop,       # fırın gözetimi
            'machining': 1.0 + 8.0 * self.D_chamber,   # kasa+nozul tornası
            'assembly': 0.5 + 3.0 * self.D_chamber,
            'testing': 1.0 + 0.02 * m_prop,
        }
        man = {k: round(v * hr, 1) for k, v in hours.items()}
        man['total_manufacturing'] = round(sum(man.values()), 1)

        # Geliştirme: toplam impuls sınıfıyla ölçeklenen bir kerelik maliyet
        total_impulse = getattr(self, '_last_total_impulse', None)
        if not total_impulse:
            total_impulse = 5000.0
        dev_scale = max(1.0, (total_impulse / 5000.0) ** 0.6)
        dev = {
            'design': round(500.0 * dev_scale, 0),
            'testing': round(300.0 * dev_scale, 0),
            'certification': round(200.0 * dev_scale, 0),
        }
        dev['total_development'] = round(sum(dev.values()), 0)

        # H4-8: kasa fiyatlanamadıysa malzeme toplamı None'dur; eksik bir
        # toplamı "tekrarlayan maliyet" diye yayımlamak sahte sayı olurdu.
        if mat['total_materials'] is None:
            recurring = None
        else:
            recurring = mat['total_materials'] + man['total_manufacturing']
        return {
            'material_costs_usd': mat,
            'manufacturing_costs_usd': man,
            'development_costs_usd': dev,
            'cost_per_flight': {
                'recurring_cost_usd': (None if recurring is None
                                       else round(recurring, 1)),
                'cost_per_ns_impulse': (
                    None if recurring is None
                    else round(recurring / max(total_impulse, 1.0), 4)),
            },
            'basis': ('Parametrik tahmin: birim fiyatlar SOLID_COST_PARAMS, '
                      'kütleler grain/kasa geometrisinden. Kesin fiyat '
                      'değildir. Fiyatlanan kütleler analiz zinciriyle AYNI '
                      'tek kaynaklardan gelir: yakıt _propellant_volume '
                      '(grain tipine duyarlı), kasa _case_design/'
                      '_case_density, yalıtım _dry_mass_breakdown '
                      '(kullanıcının insulation_thickness girdisi).'),
        }
    
    def _generate_motor_cad_data(self):
        """Generate comprehensive CAD data for solid rocket motor.

        v2.6.26 (Codex P0-03): CAD kasası analizden KOPUKTU. Buradaki cidar
        sabit 8 mm, malzeme sabit 'AISI 4130 Steel', tasarım basıncı sabit
        150 bar ve emniyet katsayısı sabit 2.5 yazılıydı; oysa aynı sınıfın
        ``_case_design`` metodu kullanıcının malzemesini, emniyet katsayısını
        ve Barlow'dan boyutlandırılmış cidarını zaten hesaplıyordu. Ölçüldü:
        analiz 2.4 / 4 / 6 / 12 mm derken CAD her durumda 8 mm; kullanıcı
        alüminyum seçtiğinde CAD etiketi çelik kalıyordu. İmalata giden
        geometrinin analizden farklı olması bu projedeki en tehlikeli
        tutarsızlıktır — artık ikisi TEK kaynaktan gelir.
        """
        case_material, _sigma_y, case_sf, wall_thickness_m = self._case_design()
        # v2.6.26 (Y2): kasa İÇ çapı grain çapı DEĞİL, grain + 2x yalıtımdır.
        # Eskiden burası D_chamber'dan türetiliyordu: kullanıcı yalıtımı
        # 3 -> 10 mm yaptığında özet tablo 122 -> 136 mm derken CAD kasası
        # 116 mm'de KALIYORDU. İmalata giden çap ile analizin çapı aynı
        # kaynaktan gelmek zorunda (_case_inner_diameter / _case_inner_length).
        case_inner_diameter = self._case_inner_diameter()
        case_outer_diameter = case_inner_diameter + 2 * wall_thickness_m
        case_length = self._case_inner_length()
        nozzle_length = self._calculate_nozzle_length()
        
        # Grain geometry analysis
        grain_geometry = self._analyze_grain_geometry()
        
        # Generate CAD data structure
        cad_data = {
            # ÖH D18 (P2B4/P15B4-05) — ŞEMA KENDİNİ TANITIR.
            # ÖLÇÜLDÜ (D17 ihracat once.json): ``cad_design`` adı altında ÜÇ
            # farklı şey dolaşıyor — katıda bu 9 anahtarlı TASARIM sözlüğü,
            # hibritte 6 anahtarlı GÖRSELLEŞTİRME sözlüğü (assembly_meshes,
            # plotly_visualization, ...), sıvıda ``None``. İki şemanın
            # kesişimi BOŞ ve 18 okuma satırının 16'sı hangi şekli aldığını
            # sormadan sessizce yedeğe düşüyor
            # (flight_vehicle._get(..., 'case_design', 'outer_diameter')
            # katıda 120,0, hibritte None). Okuyucunun ayrım yapabilmesi için
            # şeklin ADI şeklin İÇİNDE olmalıdır; ad yoksa okuyucunun tek
            # çaresi anahtar yoklamaktır ve o da sessiz yedeğe düşer.
            # Bu, kalemin KATI yarısıdır: hibrit/sıvı tarafı kendi
            # kulvarlarında etiketlenecek (D18'de hibrit motor dosyası fizik
            # kulvarınca tutulduğu için burada açılmadı).
            'schema': SOLID_CAD_DESIGN_SCHEMA,
            'motor_assembly': {
                'overall_length': case_length + nozzle_length,
                'maximum_diameter': max(case_outer_diameter, self._get_nozzle_exit_diameter()),
                'dry_mass_kg': self._calculate_dry_mass(),
                'wet_mass_kg': self._calculate_wet_mass()
            },
            'case_design': dict(
                self._case_design_report(),
                # P15B4-07: künye çekirdeği (malzeme, dayanım, tasarım SF,
                # cidar + cidarın KAYNAĞI) yukarıdaki tek noktadan gelir;
                # aşağıdakiler yalnız bu bloğa özgü GEOMETRİ alanlarıdır.
                # Eski adlar korunur ('wall_thickness' birimsiz-mm) ki
                # bugünkü tüketiciler (STEP/DXF/PDF) kırılmasın.
                **{
                'outer_diameter': case_outer_diameter * 1000,  # mm
                'inner_diameter': case_inner_diameter * 1000,  # mm
                'wall_thickness': wall_thickness_m * 1000,  # mm, _case_design
                'length': case_length * 1000,  # mm
                'material': case_material,
                'design_pressure_bar': self.P_c * case_sf,
                'safety_factor': case_sf,
                # Çap zinciri görünür olsun diye bileşenler de yazılır:
                # kasa iç çapı = grain dış çapı + 2 x yalıtım.
                'grain_outer_diameter': self.D_chamber * 1000,  # mm
                'insulation_thickness': (
                    getattr(self, 'insulation_thickness_m', 0.0) * 1000),  # mm
                # Yüzey kalitesi ve diş ölçüleri HRMA tarafından
                # boyutlandırılmıyor; eskiden 'Ra 3.2' ve 'M100x2 forward,
                # M90x2 aft' sabitleri motorun çapından bağımsız basılıyordu.
                'surface_finish': 'NOT_DEFINED',
                'threads': 'NOT_DEFINED',
                }),
            'grain_geometry': grain_geometry,
            'nozzle_design': self._design_nozzle_geometry(),
            'insulation_system': self._design_insulation_system(),
            'igniter_system': self._design_igniter_system(),
            'manufacturing_drawings': self._generate_manufacturing_drawings(),
            'assembly_sequence': self._generate_assembly_sequence(),
            'quality_control': self._generate_quality_requirements()
        }
        
        return cad_data
    
    def _analyze_grain_geometry(self):
        """Detailed grain geometry analysis"""
        if self.grain_type == 'bates':
            return self._analyze_bates_grain()
        elif self.grain_type == 'star':
            return self._analyze_star_grain()
        elif self.grain_type == 'wagon_wheel':
            return self._analyze_wagon_wheel_grain()
        elif self.grain_type == 'finocyl':
            return self._analyze_finocyl_grain()
        elif self.grain_type == 'slotted':
            return self._analyze_slotted_grain()
        elif self.grain_type == 'end_burner':
            return self._analyze_end_burner_grain()
        # Sessiz BATES fallback'i KALDIRILDI (2026-07-19): finocyl/slotted
        # burada da bates gibi raporlanıyordu.
        raise ValueError(
            f"Unsupported grain type '{self.grain_type}'. Supported grain "
            f"types: {', '.join(SUPPORTED_GRAIN_TYPES)}.")

    def _radial_slot_report(self, kind):
        """Finocyl / slotted ortak geometri raporu (gerçek hesaptan)."""
        if kind == 'finocyl':
            n, width, depth, frac, assumed, clipped = self._finocyl_params()
            l_fin, l_plain = self._finocyl_section_lengths()
            title = f'Finocyl ({n} fins)'
            extra = {
                'fin_count': n,
                'fin_width_mm': width * 1000,
                'fin_depth_mm': depth * 1000,
                'finned_length_fraction': frac,
                'finned_length_mm': l_fin * 1000,
                'plain_length_mm': l_plain * 1000,
            }
        else:
            n, width, depth, assumed, clipped = self._slotted_params()
            title = f'Slotted ({n} axial slots)'
            extra = {
                'slot_count': n,
                'slot_width_mm': width * 1000,
                'slot_depth_mm': depth * 1000,
                'slot_length_mm': self.L_grain * 1000,
            }
        volume = self._propellant_volume()
        a0 = self.calculate_burn_area(0.0)
        report = {
            'type': title,
            'outer_diameter': self.D_chamber * 1000,
            'core_diameter': self.D_core * 1000,
            'length': self.L_grain * 1000,
            'web_thickness': (self.D_chamber / 2 - (self.D_core / 2 + depth)) * 1000,
            'grain_volume': volume * 1e6,       # cm3
            'propellant_mass': volume * self.rho_p,
            'burning_surfaces': {
                'initial_burn_area_m2': a0,
                'inhibited_surfaces': ('outer cylindrical surface and both '
                                       'end faces'),
            },
            'model_note': (
                'Burning surface is computed by geometric offset of the real '
                'port cross-section (Huygens construction, shapely). Slot '
                'side walls and slot roots are included; the section reverts '
                'to a plain circular port once the slots burn out.'),
            'assumed_defaults': assumed,
            'clipped_inputs': clipped,
            'manufacturing_complexity': 'High',
            'tooling_requirements': 'Custom mandrel with radial slot profile',
        }
        report.update(extra)
        return report

    def _analyze_finocyl_grain(self):
        """Finocyl grain detailed analysis (real geometry)."""
        return self._radial_slot_report('finocyl')

    def _analyze_slotted_grain(self):
        """Slotted-tube grain detailed analysis (real geometry)."""
        return self._radial_slot_report('slotted')
    
    def _analyze_bates_grain(self):
        """BATES grain detailed analysis"""
        web_thickness = (self.D_chamber - self.D_core) / 2
        grain_volume = np.pi * (self.D_chamber**2/4 - self.D_core**2/4) * self.L_grain
        # Yanan/inhibe yüzeyler calculate_burn_area ile AYNI bayraklardan
        # (v2.6.26): eski rapor uç alanını segment sayısından bağımsız 2 yüz
        # sayıyordu ve inhibitör düzenini hiç görmüyordu.
        n_seg = self._bates_segment_count()
        outer_burns = not getattr(self, 'inhibit_outer', True)
        faces = 2 * n_seg
        inhibited_faces = 0
        if getattr(self, 'inhibit_front', False):
            faces -= 1
            inhibited_faces += 1
        if getattr(self, 'inhibit_rear', False):
            faces -= 1
            inhibited_faces += 1
        face_area = np.pi * (self.D_chamber**2 - self.D_core**2) / 4  # m²
        outer_area = np.pi * self.D_chamber * self.L_grain            # m²

        return {
            'type': 'BATES (Cylindrical)',
            'outer_diameter': self.D_chamber * 1000,  # mm
            'core_diameter': self.D_core * 1000,  # mm
            'length': self.L_grain * 1000,  # mm
            'web_thickness': web_thickness * 1000,  # mm
            'grain_volume': grain_volume * 1e6,  # cm³
            'propellant_mass': grain_volume * self.rho_p,  # kg
            'burning_surfaces': {
                'core_surface': 2 * np.pi * (self.D_core/2) * self.L_grain,  # m²
                'end_surfaces': faces * face_area,  # m² (yanan uç yüzeyler)
                'outer_surface': outer_area if outer_burns else 0.0,  # m²
                'inhibited_surfaces': (
                    (0.0 if outer_burns else outer_area)
                    + inhibited_faces * face_area),  # m²
            },
            # v2.6.26 UYDURMA SÖKÜMÜ: burada hesaplanan hoop gerilmesinin
            # YANINDA sabit 'thermal_stress_mpa': 2.5, 'safety_factor': 3.0 ve
            # 'crack_resistance': 'Good' duruyordu. Gerçek bir hesabın yanına
            # konan uydurma sayı en tehlikelisidir: kullanıcı üçünün de
            # hesaplandığını sanıyor ve grainin emniyet katsayısını 3 biliyor.
            # Grain termal gerilmesi ve çatlak dayanımı için itergacın mekanik
            # özellikleri (E, alfa, kopma uzaması, Tg) gerekir; bunlar
            # veritabanımızda yok.
            'structural_analysis': {
                'hoop_stress_mpa': self._calculate_grain_hoop_stress(),
                'thermal_stress_mpa': None,
                'safety_factor': None,
                'basis': ('Only the pressure-driven hoop stress is computed. '
                          'Grain thermal stress and crack resistance need '
                          'propellant mechanical properties (modulus, CTE, '
                          'elongation, Tg) that HRMA does not carry.'),
            },
            'manufacturing_tolerances': {
                'note': ('Grain tolerances are NOT_DEFINED by HRMA; set them in '
                         'your detail drawings.'),
            }
        }
    
    def _analyze_star_grain(self):
        """Star grain detailed analysis"""
        # Star geometrisi tek kaynaktan (_star_params) — yanma alanı modeli
        # ve bu rapor aynı değerleri kullanır.
        star_points, point_depth = self._star_params()

        # ------------------------------------------------------------------
        # ÖH D15 a2 (P2B3-01) — YANMA ALANI ÇÖZÜCÜDEN OKUNUR, YENİDEN
        # TÜRETİLMEZ. Eski kod burada İKİNCİ bir alan modeli kuruyordu:
        #
        #   base_core_area     = pi*(D_core/2)**2                 <- KESİT
        #   star_enhancement   = N * derinlik * L * 2             <- kaynaksız
        #   total_burning_area = base_core_area + star_enhancement
        #
        # İki kusur bir aradaydı:
        #  (a) 'initial_core_area' bir yanma YÜZEYİ değil port KESİTİydi.
        #      ÖLÇÜLDÜ: 0,00070686 m² yayımlanıyordu, gerçek çekirdek yanma
        #      yüzeyi 2*pi*r*L = 0,047124 m² — 66,7 KAT büyük (75 mm gövdede
        #      48,0 kat). Kardeş BATES raporu aynı satırı doğru yazıyor
        #      (2*pi*(D_core/2)*L_grain), yani bu bir kopya-yapıştır sapmasıydı.
        #  (b) 'total_burning_area' çözücünün Ab(0)'ı DEĞİLDİ. ÖLÇÜLDÜ (APCP,
        #      mm): 100/30/500 6 uç -> rapor 0,090707 m² ⟷ çözücü 0,111538 m²
        #      (0,813x); 5 uç 0,760x; 8 uç 0,881x; 200/60/1000 0,629x;
        #      75/25/300 0,850x. Sapma geometriyle kayıyordu (%12-%37) ve AYNI
        #      yanıtta doğru değer zaten throat_sizing.initial_burn_area_m2
        #      olarak duruyordu — tek fiziksel büyüklük iki sayıyla çıkıyordu.
        #
        # Artık toplam alan çözücünün KENDİ calculate_burn_area(0.0)
        # fonksiyonundan gelir (star'da shapely Huygens ofseti). Döküm ondan
        # TÜRETİLİR: düz silindirik çekirdeğin yüzeyi kapalı formdadır, yıldız
        # profilinin KATTIĞI fazlalık farktır. Böylece
        #   initial_core_area + star_enhancement_area == total_burning_area
        # özdeşliği korunur ve üç terimin üçü de gerçek yanma alanıdır.
        # ------------------------------------------------------------------
        core_surface_area = 2 * np.pi * (self.D_core / 2) * self.L_grain
        try:
            total_burn_area = float(self.calculate_burn_area(0.0))
        except Exception as exc:
            total_burn_area = float('nan')
            burn_area_basis = (
                'not_computed: the solver burn-area model raised %r for this '
                'geometry. No substitute is published — the old closed-form '
                'estimate was NOT the solver value.' % (exc,))
        if np.isfinite(total_burn_area) and total_burn_area > 0.0:
            star_enhancement = float(total_burn_area - core_surface_area)
            burn_area_basis = (
                'total_burning_area IS the solver initial burn area '
                'calculate_burn_area(0) — the same number published as '
                'throat_sizing.initial_burn_area_m2 and used by the thrust '
                'curve. initial_core_area is the plain cylindrical bore '
                'surface 2*pi*(D_core/2)*L_grain; star_enhancement_area is '
                'what the star profile adds on top of it, so the two terms '
                'sum to the total by construction.')
        else:
            total_burn_area = None
            star_enhancement = None
            core_surface_area = None

        # ÖH D15 a2 (P2B4-02): en ince kesit TEK kaynaktan
        # (_geometric_web_thickness) — grain_design bloğu da aynı sayıyı okur.
        web_thickness = self._geometric_web_thickness()

        return {
            'type': f'Star ({star_points}-pointed)',
            'outer_diameter': self.D_chamber * 1000,
            'core_diameter': self.D_core * 1000,
            'length': self.L_grain * 1000,
            # ÖH D18 (P2B3-11): bu anahtar YOKTU ve CAD grain tablosu
            # (solid.html:4988-4995 -> fmtField -> 'not computed') değer
            # hesaplanmış olduğu hâlde "hesaplanmadı" basıyordu. Aynı sayı
            # yanıtın kökünde zaten duruyor; TEK kaynak _propellant_volume.
            'grain_volume': self._propellant_volume() * 1e6,   # cm3
            'propellant_mass': self._propellant_volume() * self.rho_p,  # kg
            'star_points': star_points,
            'point_depth': point_depth * 1000,  # mm
            'web_thickness': (web_thickness * 1000
                              if web_thickness is not None else None),
            'model_note': ('Yanan çevre geometrik ofset modeliyle (Huygens) '
                           'hesaplanır; uç sayısı ve derinliği itki eğrisine '
                           'tam yansır.' if SHAPELY_AVAILABLE else
                           'shapely kurulu değil: itki eğrisi basitleştirilmiş '
                           'çevre yaklaşıklığıyla hesaplanır.'),
            'burning_characteristics': 'Progressive',
            'burning_surfaces': {
                'initial_core_area': core_surface_area,
                'star_enhancement_area': star_enhancement,
                'total_burning_area': total_burn_area,
                'burning_surfaces_basis': burn_area_basis,
                'thrust_profile': 'Progressive - increasing thrust'
            },
            'manufacturing_complexity': 'High',
            'tooling_requirements': 'Custom mandrel with star profile',
            'structural_considerations': {
                'stress_concentration': 'Star valleys require fillet radii',
                # v2.6.26 (P4) UYDURMA SÖKÜMÜ: burada sabit
                # 'minimum_web_thickness': '15mm at star valleys' yazıyordu.
                # En ince kesit BU SÖZLÜKTE ZATEN HESAPLANIYORDU
                # (web_thickness) — kullanıcı iki farklı sayı görüyordu.
                # Ölçüldü: 75 mm gövde / 25 mm çekirdek / 15 mm uç derinliği
                # motorda gerçek web 10,0 mm iken metin 15 mm diyordu (%50
                # iyimser); 500 mm'lik motorda da yine 15 mm diyordu.
                'minimum_web_thickness_mm': (web_thickness * 1000
                                             if web_thickness is not None
                                             else None),
                'minimum_web_thickness_basis': (
                    'thinnest section = (D_case - D_core)/2 - star point '
                    'depth, i.e. the web under the star points; identical to '
                    "this block's web_thickness and to "
                    'grain_design.web_thickness_mm (one source: '
                    '_geometric_web_thickness)'),
                # Grain toleransı HRMA tarafından BOYUTLANDIRILMAZ; BATES
                # bloğuyla aynı beyan (manufacturing_tolerances).
                'manufacturing_tolerance': None,
                'manufacturing_tolerance_status': 'NOT_MODELLED',
                'manufacturing_tolerance_basis': (
                    'Star profile tolerances are not sized by HRMA. The '
                    'previous fixed +/-0.05 mm applied to every motor and was '
                    'not derived from anything; set it on your detail '
                    'drawings.'),
            }
        }

    def _analyze_wagon_wheel_grain(self):
        """Wagon-wheel grain raporu — geometri ÇÖZÜCÜNÜN PORTUNDAN.

        v2.6.26 (P4). Bu blok, itki eğrisinin kullandığı porttan BAŞKA bir
        yerleşim anlatıyordu:

            rapor  : d_uydu = 0.6*D_core, R = (D_kasa - d_uydu)/4
            çözücü : 7 EŞİT delik, r = D_core/4, R = D_kasa/4
                     (_wagon_port_polygon / _cached_wagon_polygon)

        75 mm gövde + 25 mm çekirdekte rapor 15 mm'lik uyduları 15 mm
        yarıçapa koyuyordu — merkez delikle 5,0 mm ÜST ÜSTE binen, hiçbir
        yerde yanmayan bir kesit. Çözücünün gerçek portunda ise 12,5 mm'lik
        yedi delik 18,75 mm yarıçapta ve en ince web 6,25 mm. Yani ekrandaki
        ölçüler imal edilse motor hesaplanandan başka bir motor olurdu.
        Artık TEK kaynak: çözücünün port kesiti.
        """
        # _wagon_port_polygon ile AYNI parametreler (tek tanım noktası).
        hole_radius = self.D_core / 4.0
        pitch_radius = self.D_chamber / 4.0
        satellite_cores = 6
        center_core_diameter = 2.0 * hole_radius
        satellite_diameter = 2.0 * hole_radius   # yedi delik eşittir

        # Port alanı: delikler çakışabildiği için ANALİTİK TOPLAM değil,
        # çözücünün birleştirdiği kesitin gerçek alanı okunur.
        if SHAPELY_AVAILABLE:
            total_core_area = float(self._wagon_port_polygon().area)
            core_area_source = 'union of the solver port cross-section (shapely)'
        else:
            total_core_area = (1 + satellite_cores) * np.pi * hole_radius ** 2
            core_area_source = ('analytic sum of 7 circles (shapely missing, so '
                                'overlap between holes is not subtracted)')

        # En ince kesit — üç aday, en küçüğü belirleyici (hepsi mm):
        #   merkez-uydu : R - r_merkez - r_uydu
        #   uydu-uydu   : 2*R*sin(pi/N) - d_uydu   (komşu merkez açıklığı)
        #   uydu-kasa   : R_kasa - (R + r_uydu)
        web_center_sat_mm = float((pitch_radius - 2.0 * hole_radius) * 1000)
        web_sat_sat_mm = float(
            (2 * pitch_radius * np.sin(np.pi / satellite_cores)
             - 2.0 * hole_radius) * 1000)
        web_sat_case_mm = float((self.D_chamber / 2
                                 - (pitch_radius + hole_radius)) * 1000)
        # Beraberlikte ilk aday kazanır (N = 6'da merkez-uydu ile uydu-uydu
        # analitik olarak EŞİTTİR: 2R·sin(30°) = R); etiket kayan nokta
        # gürültüsüne göre değil, sabit sıraya göre seçilir.
        min_web_location, min_web_mm = min(
            (('center-to-satellite', web_center_sat_mm),
             ('satellite-to-satellite', web_sat_sat_mm),
             ('satellite-to-case', web_sat_case_mm)),
            key=lambda item: item[1])

        return {
            'type': 'Wagon Wheel (7 cores)',
            'outer_diameter': self.D_chamber * 1000,
            # ÖH D18 (P2B3-11): CAD grain tablosunun okuduğu üç anahtar
            # (core_diameter / web_thickness / propellant_mass) burada
            # YOKTU ve panel üçüne birden 'not computed' basıyordu; üçü de
            # bu koşuda zaten hesaplanmıştı. Değerler yeniden TÜRETİLMEZ,
            # aynı bloğun/çözücünün kendi sayıları kullanılır:
            #   core_diameter  = merkez deliğin çapı (center_core_diameter)
            #   web_thickness  = en ince kesit (minimum_web_mm ile aynı sayı)
            #   propellant_mass= _propellant_volume() * rho_p (kök alanla aynı)
            'core_diameter': center_core_diameter * 1000,
            'core_diameter_basis': (
                'the centre hole of the seven-hole port; the six satellite '
                'holes have the same diameter and are listed separately as '
                'satellite_diameter / satellite_positions'),
            'web_thickness': min_web_mm,
            'web_thickness_basis': (
                'the thinnest propellant section of the seven-hole port; '
                'identical to minimum_web_mm in this block '
                '(location: %s)' % min_web_location),
            'grain_volume': self._propellant_volume() * 1e6,   # cm3
            'propellant_mass': self._propellant_volume() * self.rho_p,  # kg
            'center_core_diameter': center_core_diameter * 1000,
            'satellite_cores': satellite_cores,
            'satellite_diameter': satellite_diameter * 1000,
            'satellite_positions': pitch_radius * 1000,
            'length': self.L_grain * 1000,
            'total_core_area': total_core_area,
            'total_core_area_source': core_area_source,
            'geometry_source': (
                'the same port cross-section the burn-area model uses '
                '(_wagon_port_polygon: 7 equal holes of radius D_core/4, six '
                'of them on a circle of radius D_case/4)'),
            'burning_characteristics': 'Regressive',
            'thrust_profile': 'High initial thrust, decreasing',
            'manufacturing_complexity': 'Very High',
            'tooling_requirements': 'Multi-core mandrel system',
            'structural_challenges': {
                'web_thickness_variation': 'Complex stress distribution',
                # v2.6.26 (P4) UYDURMA SÖKÜMÜ: burada sabit
                # 'minimum_web': '10mm between cores' yazıyordu; motorun
                # boyutundan da, çekirdek yerleşiminden de bağımsızdı.
                # ÖLÇÜM: çözücünün gerçek portunda en ince web 75 mm gövdede
                # 6,25 mm, 500 mm gövdede 50,0 mm — sabit metin ikisine de
                # 10 mm diyordu (küçük motorda %60 iyimser, büyük motorda
                # beşte bir).
                'minimum_web_mm': min_web_mm,
                'minimum_web_location': min_web_location,
                'web_center_to_satellite_mm': float(web_center_sat_mm),
                'web_satellite_to_satellite_mm': float(web_sat_sat_mm),
                'web_satellite_to_case_mm': float(web_sat_case_mm),
                'minimum_web_status': ('cores_overlap' if min_web_mm <= 0
                                       else 'positive'),
                'minimum_web_basis': (
                    'computed from the solver port layout (7 holes of radius '
                    'D_core/4, six on a circle of radius D_case/4): the '
                    'smallest of center-to-satellite, satellite-to-satellite '
                    'and satellite-to-case spacing. A non-positive value means '
                    'the holes overlap for this diameter pair - change the '
                    'core or case diameter.'),
                # Yerleşim toleransı boyutlandırılmaz (BATES/star ile aynı).
                'manufacturing_precision': None,
                'manufacturing_precision_status': 'NOT_MODELLED',
                'manufacturing_precision_basis': (
                    'Core positioning tolerance is not sized by HRMA. The '
                    'previous fixed +/-0.02 mm applied to every motor and was '
                    'not derived from anything; set it on your detail '
                    'drawings.'),
            }
        }
    
    def _analyze_end_burner_grain(self):
        """End burner grain analysis"""
        burning_area = np.pi * (self.D_chamber/2)**2
        # ÖH D21 a1 (P2B3-12): burada ikinci bir hacim hesabı duruyordu
        #     grain_volume = np.pi * (D_chamber/2)**2 * L_grain
        # ve HİÇ okunmuyordu (AST ölçümü: atanıp okunmayan tek ad). D18
        # (P2B3-11) yayımlanan hacmi zaten TEK kaynağa, _propellant_volume()
        # ile aşağıdaki 'grain_volume' alanına bağlamıştı; bu ölü satır ise
        # aynı kavramın ikinci ve farklı bir tanımıydı (çekirdeği görmez,
        # dolayısıyla bağlanırsa yanlış kütle üretirdi). Silindi.

        return {
            'type': 'End Burner',
            'outer_diameter': self.D_chamber * 1000,
            'length': self.L_grain * 1000,
            # ÖH D18 (P2B3-11): grain_volume burada hesaplanıp ATILIYORDU
            # ve propellant_mass hiç yayımlanmıyordu; panel değeri
            # 'not computed' diye gösteriyordu. Kütle kökteki alanla AYNI
            # tek kaynaktan gelir.
            'grain_volume': self._propellant_volume() * 1e6,   # cm3
            'propellant_mass': self._propellant_volume() * self.rho_p,  # kg
            # Çekirdek ve radyal web bu tipte GERÇEKTEN YOKTUR (sigara
            # yanması, eksenel cephe). Panel bunları 'not computed' diye
            # gösteriyordu — yanlış beyan; doğru beyan 'uygulanamaz'dır ve
            # gerekçe alanı fmtField'in title ipucuna düşer.
            'core_diameter': None,
            'core_diameter_status': 'not_applicable',
            'core_diameter_basis': (
                'An end burner has no central core: the grain is a solid '
                'cylinder that burns axially from one face. There is no core '
                'diameter to compute.'),
            'web_thickness': None,
            'web_thickness_status': 'not_applicable',
            'web_thickness_basis': (
                'An end burner has no radial web. The distance the flame '
                'travels is the grain length, published above as `length`.'),
            'burning_area': burning_area,
            'burning_characteristics': 'Neutral',
            'thrust_profile': 'Constant thrust',
            'burn_time': 'Long duration',
            'inhibitor_requirements': {
                'outer_surface': 'Full inhibition required',
                'one_end': 'Full inhibition required',
                'burning_end': 'No inhibition'
            },
            'advantages': ['Simple manufacturing', 'Predictable thrust', 'Long burn time'],
            'disadvantages': ['Low thrust-to-weight', 'Large motor size', 'Slow acceleration']
        }
    
    def _throat_gas_temperatures(self):
        """Boğazdaki GAZ sıcaklıkları [K] — statik ve kurtarma (recovery).

        v2.6.26 (P4). Lüle raporunda sabit '2800°C' yazıyordu; bu sayı ne
        yakıttan ne basınçtan etkileniyordu. Ölçüldü: KNSU motorunda gerçek
        boğaz statik sıcaklığı 1345,9 °C, APCP motorunda 3015,1 °C — sabit
        metin ikisine de 2800 °C diyordu, yani şeker yakıtında gerçeğin
        1454 °C üstünde. Bu sayı doğrudan boğaz malzemesi seçimine (grafit /
        fenolik / refrakter) girdiği için tehlikeli bir uydurmaydı.

        Statik sıcaklık (Sutton & Biblarz 9. baskı Denk. 3-12, M = 1):
            T_t = T_c · 2/(γ+1)
        Cidarın gördüğü sürücü sıcaklık ise KURTARMA sıcaklığıdır
        (T_aw = T_c·(1+r·m)/(1+m), r = Pr^{1/3}); onu bu sınıfın ısı akısı
        hesabıyla AYNI uygulama üretir (heat_transfer_analysis), yeni fizik
        yazılmaz. Modül bulunamazsa sayı UYDURULMAZ, None döner.
        """
        t_static = float(self.T_c) * 2.0 / (float(self.gamma) + 1.0)
        t_recovery = None
        try:
            from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
            analyzer = HeatTransferAnalyzer()
            # B11 seçenek F: ısı akısı ve lüle malzeme marjıyla AYNI gamma
            # seçimi (_bartz_gas_gamma) — bir istasyonun iki T_aw'ı olamaz.
            # Statik sıcaklık genleşmedir, denge gamma'sıyla kalır.
            gas = analyzer._get_gas_properties(
                {'gamma': self._bartz_gas_gamma(),
                 'molecular_weight': getattr(self, 'mw_exhaust', 26.0)},
                self.T_c)
            t_recovery = float(analyzer._adiabatic_wall_temperature(
                self.T_c, gas, mach_local=1.0))
        except Exception:
            t_recovery = None
        return {'static_k': t_static, 'recovery_k': t_recovery}

    def _design_nozzle_geometry(self):
        """Detailed nozzle design derived from motor parameters.

        Throat diameter from steady-state mass balance,
        expansion ratio from isentropic area-ratio relation.
        """
        d_throat = self._estimate_throat_diameter()
        epsilon = self._estimate_expansion_ratio()
        # P2B3-07: çıkış çapı ETKİN boğazdan (tek kaynak) — geometrik boğazdan
        # türetilirse çizilen lülenin gerçek eps'i yayımlanandan sapar.
        d_exit = self._design_exit_diameter()

        # Nozzle contour lengths (conical nozzle)
        # Kalem 15-16 (P3): burada 30/15 derece YEREL SABİT olarak duruyordu.
        # Yarı açıların TEK kaynağı _nozzle_half_angles(): kullanıcının
        # convergent_angle / divergent_angle girdisi zaten oraya işleniyor ve
        # nozul boyu (_calculate_nozzle_length) onu kullanıyordu. Bu panel
        # ise girdiden bağımsız 30/15 yayımlıyordu — aynı motorun nozul açısı
        # iki yerde iki farklı sayıydı.
        conv_half_angle, div_half_angle = self._nozzle_half_angles()
        # ------------------------------------------------------------------
        # ÖH D18 (P2B3-13) — BOĞAZ GÖVDEDEN BÜYÜKSE YAKINSAK BÖLÜM YOKTUR.
        #
        # ÖLÇÜLDÜ (once.json; motor_validation aralıklarının İÇİNDE kalan
        # meşru girdilerle, APCP bates):
        #   D=100 L=3000 c=15 Pc=10 bar -> d_boğaz 156,54 mm (D'nin 1,565x)
        #                                  convergent_length  -48,97 mm
        #   D=100 L=3000 c=15 Pc= 5 bar -> 180,48 mm (1,805x) -69,70 mm
        #   D=150 L=4000 c=20 Pc= 5 bar -> 264,78 mm (1,765x) -99,40 mm
        # Formül (D_gövde - d_boğaz)/(2 tan a) boğaz büyükse NEGATİF bir boy
        # üretiyor ve bu sayı hiçbir kapıya takılmadan cad_design.
        # nozzle_design.convergent_length olarak panele, oradan STEP/STL
        # yoluna (export/motor_geometry.py) gidiyordu; üstelik toplam boy
        # ıraksak bölümün tek başına boyundan KISA çıkıyordu (120,79 < 169,76).
        #
        # Negatif boy KAZANILMIŞ bir hüküm değildir: böyle bir lüle yoktur.
        # Fail-closed: sayı yayımlanmaz (None), yerine durumu ve gerekçesi
        # ADIYLA yayımlanır. Geometri fiziksel olduğunda davranış birebir
        # eskisi gibidir.
        # ------------------------------------------------------------------
        throat_exceeds_case = self._throat_exceeds_case(d_throat)
        if throat_exceeds_case:
            convergent_length = None
        else:
            convergent_length = ((self.D_chamber - d_throat)
                                 / (2 * np.tan(np.radians(conv_half_angle))))
        divergent_length = (d_exit - d_throat) / (2 * np.tan(np.radians(div_half_angle)))

        # Throat curvature radius: typically 0.5-1.5 * r_throat
        throat_curvature = d_throat / 2 * 1.0  # 1x throat radius

        # Boğaz erozyon tahmini (Dalga 3, 2026-07-14): eski sabit
        # '0.001 mm/s' metni yerine ampirik model —
        #   ṙ = a_ref·(Pc/Pc_ref)^0.8
        # (Bartz 1957 Pc^0.8 ölçeklemesi; Thakre & Yang 2008 grafit bandı).
        #
        # ÖH D26 a2 (P2B1-03 + P2B3-03): burada KOŞULSUZ
        # ``ThroatErosionModel.for_material('graphite')`` kuruluyordu; model
        # seçimi artık TEK tanım noktasındadır (``_nozzle_erosion_estimate``)
        # ve çözücünün okuduğu katsayı/malzeme zincirini izler.
        _t_gas = self._throat_gas_temperatures()
        # Çıkış düzlemi durumu (egzoz/plume şeması) — tek tanım noktası
        _exit_state = self._nozzle_exit_state()
        # ÖH D20 / P2B1-01: yoğuşmuş faz kesri TEK çözüm noktasından
        # (_condensed_mass_fraction) okunur; ayrışım künyesinde
        # yayımlanır, burada yeni bir sayı türetilmez.
        _x_p_exit, _x_kaynak_exit, _ = _condensed_mass_fraction(
            self.propellant_type)
        erosion_estimate = self._nozzle_erosion_estimate()
        _ero_rate = erosion_estimate.get('rate_mm_s')
        # Yayımlanmış katsayı yoksa metin de üretilmez (fail-closed): eski
        # kod burada her koşulda grafit sayısını basıyordu.
        _ero_rate_text = (None if _ero_rate is None
                          else f"{_ero_rate:.3f} mm/s")
        # CAD lüle bloğunun malzeme alanı da kullanıcının seçimini izler;
        # sabit 'Graphite' metni P2B3-03'ün ikinci yaprağıydı.
        # V301/K-B (KT-10): erozyon modelinin yer tutucu adı ('User-supplied
        # coefficient') MALZEME ADI DEĞİLDİR; tungsten/fenolik lüle CAD'de bu
        # adla yazılıyordu. Kullanıcı katsayısı verdiyse ad malzeme kaydından.
        _nozzle_material_text = erosion_estimate.get('material_display')
        if (not _nozzle_material_text
                or _nozzle_material_text == 'User-supplied coefficient'):
            _lule_kaydi = solid_nozzle_material_record(
                self._nozzle_material_key())
            _nozzle_material_text = (
                _lule_kaydi['name'] if _lule_kaydi is not None
                else self._nozzle_material_key().replace('_', ' ').title())

        return {
            'type': 'De Laval Nozzle',
            'throat_diameter': d_throat * 1000,  # mm
            'exit_diameter': d_exit * 1000,  # mm
            'expansion_ratio': epsilon,
            # ÖH D17 (P2B3-09): tasarım genişleme oranına bir SINIR
            # uygulandıysa kullanıcı bunu ADIYLA görür; sessiz kelepçe
            # yasaktır. Sınır uygulanmadıysa alan None'dır.
            'expansion_ratio_bound': getattr(
                self, '_expansion_ratio_bound', None),
            'expansion_ratio_basis': (
                'Fully expanded area ratio at the run ambient pressure '
                '(P_e = P_ambient, isentropic area-ratio relation). No '
                'upper clamp is applied: the previous fixed ceiling of 25 '
                'was not derived from anything and silently reported 25.0 '
                'where the optimum is 103.06 at 25 km (measured). Any lower '
                'bound that was applied is named in expansion_ratio_bound.'),
            'convergent_angle': conv_half_angle,  # degrees
            'divergent_angle': div_half_angle,   # degrees
            'convergent_length': (None if convergent_length is None
                                  else convergent_length * 1000),  # mm
            # ÖH D18 (P2B3-13): boğaz gövdeyi aştığında yakınsak bölüm ve
            # dolayısıyla toplam kontur boyu YAYIMLANMAZ; hangi kısıtın
            # ihlal edildiği adıyla söylenir.
            'convergent_length_status': (
                'not_physical' if throat_exceeds_case else 'computed'),
            'convergent_length_basis': (
                ('The throat diameter (%.3f mm) is not smaller than the grain '
                 'outer diameter (%.3f mm), so a converging section between '
                 'the chamber and the throat does not exist. The conical '
                 'formula (D_case - d_throat)/(2 tan a) would return a '
                 'NEGATIVE length; no such nozzle exists, so no number is '
                 'published. Lower the expansion needs, raise the chamber '
                 'pressure or enlarge the case.'
                 % (d_throat * 1000, self.D_chamber * 1000))
                if throat_exceeds_case else
                'conical contour: (D_case - d_throat)/(2 tan(convergent '
                'half-angle)), with the half-angle from _nozzle_half_angles'),
            'throat_exceeds_case': throat_exceeds_case,
            'throat_over_case_ratio': float(d_throat / self.D_chamber)
            if self.D_chamber > 0 else None,
            'divergent_length': divergent_length * 1000,    # mm
            'total_length': (None if convergent_length is None
                             else (convergent_length + divergent_length)
                             * 1000),  # mm
            'total_length_status': (
                'not_computable' if convergent_length is None else 'computed'),
            'throat_radius': throat_curvature * 1000,  # mm (throat curvature)
            # ÖH D26 a2 (P2B3-03): burada sabit 'Graphite' yazıyordu ve
            # kullanıcı ne seçerse seçsin (carbon_carbon / steel / tungsten /
            # phenolic) değişmiyordu — ölçüldü: 6 seçimde 1 ayırt edici
            # değer. Artık seçilen malzemenin görünen adıdır.
            'material': _nozzle_material_text,
            'material_key': self._nozzle_material_key(),
            'material_basis': (
                'nozzle_material / throat_material input for this run; the '
                'erosion estimate below is built from the SAME selection'),
            # v2.6.26 (P4) UYDURMA SÖKÜMÜ: burada 'Ra 0.8 μm', '±0.01mm' ve
            # '±0.5°' sabitleri vardı. Bunlar imalat ŞARTNAMESİdir, çözücünün
            # çıktısı değildir ve motorun boyutundan bağımsız yazılıyordu —
            # üstelik AYNI KOŞUDA 'manufacturing_drawings.critical_dimensions'
            # bloğu bu tür toleransları zaten NOT_MODELLED ilan ediyor
            # (oradaki gerekçe: "±0.01 mm boğaz ... her motora uygulanıyordu
            # ve hiçbir şeyden türetilmiyordu"). Aynı yanıtta iki farklı
            # beyan kalamaz; bu blok da beyana çevrildi.
            'manufacturing': {
                'machining_method': 'CNC turning',
                'status': 'NOT_MODELLED',
                'surface_finish': None,
                'throat_tolerance': None,
                'angle_tolerance': None,
                'basis': ('Surface finish and dimensional tolerances are not '
                          'sized by HRMA (no manufacturing-process model). '
                          'Specify them on your detail drawings; the machining '
                          'method above is general workshop practice for a '
                          'turned nozzle, not a computed result.'),
            },
            'performance': {
                # Egzoz (plume) şeması — hibritle AYNI adlar (motor_viz3d.js
                # readNozzleExit bunları okur: exit_pressure, ambient_pressure,
                # exit_mach, exit_velocity). Katı motorda bu blok yoktu; bu
                # yüzden katı sayfasında egzoz HİÇ çizilmiyordu. Değerler
                # çözücünün KENDİ izentropik çözümünden gelir
                # (_nozzle_exit_state — _exit_pressure_ratio ile aynı çözüm),
                # sayısal çözüm başarısızsa None kalır ve egzoz çizilmez.
                'exit_pressure': _exit_state['exit_pressure_bar'],  # bar
                'exit_pressure_basis': 'isentropic_area_ratio',
                'ambient_pressure': _exit_state['ambient_pressure_bar'],  # bar
                'ambient_pressure_basis': (
                    'back pressure the thrust curve uses '
                    '(self.ambient_pressure_bar: user test_altitude / '
                    'atm_pressure input, sea level 1.01325 bar by default)'),
                'exit_mach': _exit_state['exit_mach'],
                'exit_mach_basis': (
                    'closed-form inverse of the isentropic pressure ratio '
                    'solved from the fixed expansion ratio '
                    '(Sutton & Biblarz 9th ed. Eq. 3-25)'),
                'exit_velocity': _exit_state['exit_velocity_ms'],  # m/s
                # ÖH D20 / P2B1-01: künye artık TEK KAYNAK çözümünden gelir
                # (_nozzle_exit_state); eski metin "izentropik tek fazlı gaz
                # hızı" diyordu ve iki-faz açığı beyan eden kayıtlarda aynı
                # yanıttaki itki zinciriyle çelişiyordu.
                'exit_velocity_basis': _exit_state.get('exit_velocity_basis'),
                # Ayrışım: gaz-fazı hızı ve onu teslim edilen hıza taşıyan
                # c* oranı yayımlanır — sayı gizlenmez, kaynağı adlanır.
                'exit_velocity_two_phase_decomposition': {
                    'gas_phase_exit_velocity_ms': _exit_state.get(
                        'gas_phase_exit_velocity_ms'),
                    'c_star_delivered_m_s': _exit_state.get(
                        'c_star_delivered_m_s'),
                    'c_star_single_phase_ideal_m_s': _exit_state.get(
                        'c_star_single_phase_ideal_m_s'),
                    'c_star_ratio_delivered_over_ideal': _exit_state.get(
                        'c_star_ratio_delivered_over_ideal'),
                    'condensed_mass_fraction': (
                        None if _x_p_exit is None else float(_x_p_exit)),
                    'condensed_mass_fraction_source': _x_kaynak_exit,
                    'basis': (
                        'The gas-phase velocity is the isentropic '
                        'single-phase result M_e*sqrt(gamma*R_s*T_e); it is '
                        'identically CF_momentum * c*_single_phase_ideal. '
                        'Multiplying by c*_delivered/c*_single_phase_ideal '
                        'ties the published exhaust velocity to the same c* '
                        'the thrust curve uses. A record whose c* sits on '
                        'its own single-phase ideal leaves the number '
                        'unchanged; a record declaring a condensed-phase '
                        'deficit is corrected downwards by exactly that '
                        'deficit'),
                },
                'exit_temperature_k': _exit_state['exit_temperature_k'],
                'exit_temperature_basis': (
                    'isentropic static temperature at the exit plane from '
                    'the same T_c/gamma/M_e set'),
                # Kalem 17 (P3): sabit 1.65 yerine motorun KENDİ CF tanımı
                # (_thrust_coefficient — Sutton & Biblarz Denk. 3-30/3-31,
                # sabit geometri + gerçek ortam basıncı). İtki eğrisi bu
                # fonksiyonu zaten kullanıyordu; CAD paneli kullanmıyordu ve
                # her motorda aynı 1.65'i basıyordu.
                'thrust_coefficient': float(self._thrust_coefficient(self.P_c)),
                'thrust_coefficient_basis': (
                    'CF(Pc) at the design chamber pressure from the same '
                    'definition the thrust curve uses (Sutton & Biblarz '
                    'Eq. 3-30/3-31, fixed-geometry nozzle, nozzle efficiency '
                    'applied)'),
                'nozzle_efficiency': self.nozzle_efficiency,
                # Gerçek ampirik modelden (eskiden sabit '0.001 mm/s' idi).
                # ÖH D26 a2: yayımlanmış katsayısı olmayan malzemede metin de
                # üretilmez; sayı uydurmak yerine durum adıyla söylenir.
                'erosion_rate': _ero_rate_text,
                'erosion_rate_status': erosion_estimate.get('status'),
                'erosion_estimate': erosion_estimate,
                # v2.6.26 (P4): sabit '2800°C' yerine bu motorun GAZ
                # sıcaklıkları (bkz. _throat_gas_temperatures). Kurtarma
                # sıcaklığı cidarın gördüğü sürücü sıcaklıktır; ikisi de GAZ
                # sıcaklığıdır, malzeme/cidar sıcaklığı DEĞİLDİR.
                'chamber_flame_temperature_k': float(self.T_c),
                'throat_gas_static_temperature_k': _t_gas['static_k'],
                'throat_gas_static_temperature_c': _t_gas['static_k'] - 273.15,
                'throat_recovery_temperature_k': _t_gas['recovery_k'],
                'throat_recovery_temperature_c': (
                    _t_gas['recovery_k'] - 273.15
                    if _t_gas['recovery_k'] is not None else None),
                'operating_temperature_basis': (
                    'gas temperatures for this propellant and pressure: '
                    'static T_t = T_c*2/(gamma+1) (Sutton & Biblarz Eq. 3-12 '
                    'at M = 1); recovery T_aw = T_c*(1+r*m)/(1+m), '
                    'r = Pr^(1/3), from the same heat-transfer module the '
                    'throat heat flux uses. Flame temperature comes from the '
                    'propellant record, not from a CEA solve of your exact '
                    'formulation. These are gas temperatures - the nozzle '
                    'material temperature needs a thermal/ablation solution '
                    'HRMA does not run.'),
            }
        }
    
    def _design_insulation_system(self):
        """Yalıtım paketi — kalınlıklar kullanıcının girdisinden.

        v2.6.26 (Y2): 'thermal_barrier.thickness' SABİT 3.0 mm yazılıydı.
        Kullanıcı yalıtımı 10 mm yaptığında geometri, kütle ve emniyet zinciri
        10 mm görürken CAD paneli hâlâ 3 mm gösteriyordu — aynı motor için
        dört panelde dört farklı yalıtım kalınlığı. Kalınlık ve malzeme
        özellikleri artık analizin kullandığı TEK kaynaktan gelir:
        yalıtım (insulation_thickness) + liner (liner_thickness) girdileri ve
        SOLID_INSULATION malzeme bandı.

        Ön/arka yalıtım ile inhibitör kaplama kalınlıkları HRMA tarafından
        BOYUTLANDIRILMIYOR (ablasyon çözümü yok); jenerik uygulama değerleri
        oldukları 'basis' alanında beyan edilir.
        """
        t_ins_mm = float(getattr(self, 'insulation_thickness_m', 0.0)) * 1000.0
        t_liner_mm = float(getattr(self, 'liner_thickness',
                                   SOLID_INSULATION['thickness_m'])) * 1000.0

        # --- Kapak astarı istasyon girdileri (v2.6.27, B6-4) --------------
        # İki istasyonun h_g / T_aw / c_p / yarıçapı motorun KENDİ Bartz
        # zincirinden gelir (_chamber_gas_side / _throat_gas_side — ikinci
        # bir Bartz hesabı YOKTUR; boğaz çifti, boğaz ısı akısını üreten
        # çağrının ta kendisidir). Soğuk-cidar tasarım akısı yalnız
        # KARŞILAŞTIRMA için hesaplanır; astarı artık yüzey enerji dengesi
        # boyutlandırır. Zincir kurulamazsa (ör. performans koşusu öncesi)
        # sayı UYDURULMAZ: her iki kapak NOT_MODELLED döner ve gerekçe
        # istasyon bloklarında adıyla durur.
        gas_side_error = None
        h_chamber = taw_chamber = cp_chamber = None
        h_throat = taw_throat = cp_throat = None
        q_chamber_W_m2 = q_throat_W_m2 = None
        r_chamber = r_throat = None
        try:
            h_chamber, taw_chamber, cp_chamber = self._chamber_gas_side()
            h_throat, taw_throat, cp_throat = self._throat_gas_side()
            t_wall_ref = SOLID_THERMAL['bartz_reference_wall_temp_k']
            q_chamber_W_m2 = h_chamber * (taw_chamber - t_wall_ref)
            q_throat_W_m2 = h_throat * (taw_throat - t_wall_ref)
            r_chamber = float(self.D_chamber) / 2.0
            r_throat = float(self._estimate_throat_diameter()) / 2.0
        except Exception as exc:
            gas_side_error = (
                f'the Bartz gas-side chain of this run could not be '
                f'evaluated: {exc}')

        return {
            'thermal_barrier': {
                'material': 'EPDM/phenolic insulation band (SOLID_INSULATION)',
                'thickness': t_ins_mm,  # mm — kullanıcının girdisi
                'liner_thickness': t_liner_mm,  # mm — grain bağ katmanı
                'total_thermal_thickness': t_ins_mm + t_liner_mm,  # mm
                # ÖH D24 (OH-D23-10): katman sırası bir MODELLEME SEÇİMİdir
                # ve beyansız duruyordu — kütle halkalarının hangi sırayla
                # yığıldığı yalnız koddan okunabiliyordu (üstelik yanlış
                # sırayla). Sıra artık TEK kaynaktan gelir ve kaynağıyla
                # birlikte yayımlanır; kütle zinciri
                # (_insulation_liner_masses) aynı sabiti izler.
                'layer_order': list(SOLID_THERMAL_LAYER_ORDER),
                'layer_order_basis': SOLID_THERMAL_LAYER_ORDER_BASIS,
                # Kalem 20 (P3): tablo değeri SABİT basılıyordu; oysa formun
                # 'liner_density' alanı motora ulaşıyor ve ısıl kapasite
                # zinciri (_calculate_case_temperature) onu kullanıyor.
                # Aynı katmanın yoğunluğu iki panelde iki farklı sayı olamaz.
                'density': self._insulation_density(),
                'thermal_conductivity':
                    SOLID_INSULATION['thermal_conductivity_w_mk'],  # W/mK
                'application_method': 'NOT_DEFINED',
                'basis': ('Thickness comes from the insulation_thickness and '
                          'liner_thickness inputs; material properties from '
                          'the single insulation record used by the mass, '
                          'geometry and thermal chains. Zero thickness means '
                          'no insulation was specified.'),
            },
            'inhibitor_coating': {
                'material': 'Silicone rubber',
                # İnhibitör kaplama kalınlığı HRMA tarafından
                # BOYUTLANDIRILMIYOR (yanma yüzeyi maskeleme modeli var,
                # kaplama ablasyon modeli yok). Sabit 1.0 mm kaldırıldı.
                'thickness': None,
                'thickness_status': 'NOT_MODELLED',
                'coverage': ['Outer grain surface', 'End faces'],
                'application': 'Brush or spray application',
                'basis': ('HRMA does not size the inhibitor coating: the '
                          'burn-area model treats inhibited faces as fully '
                          'masked and has no coating recession model.'),
            },
            'forward_insulation': self._ablative_liner_sizing(
                station='forward closure',
                function='Protect forward closure',
                q_W_m2=q_chamber_W_m2,
                station_note=(
                    'The forward closure sits in the low-velocity stagnant '
                    'region at the head end, so its driving flux and '
                    'gas-side coefficient are the CHAMBER station values of '
                    'this run — the closure sees LESS than the chamber wall, '
                    'so this is a conservative upper bound. Until v2.6.27 '
                    'both closures were sized with the THROAT flux and '
                    'therefore published the same number; the difference '
                    'was only claimed in this text.'),
                h_gas=h_chamber,
                h_gas_source=('chamber-station Bartz coefficient of this '
                              'run (_chamber_gas_side)'),
                T_aw=taw_chamber,
                gas_cp=cp_chamber,
                radius_m=r_chamber,
                radius_source='chamber inner radius of this run',
                gas_side_error=gas_side_error,
                material=SOLID_FWD_CLOSURE_LINER_MATERIAL),
            'aft_insulation': self._ablative_liner_sizing(
                station='aft closure / nozzle entry',
                function='Nozzle throat protection',
                q_W_m2=q_throat_W_m2,
                station_note=(
                    'Flux and gas-side coefficient are the Bartz THROAT '
                    'values of this run. The geometric gate uses the THROAT '
                    'radius, a conservative lower bound of the entry '
                    'passage.'),
                h_gas=h_throat,
                h_gas_source=('throat-station Bartz coefficient of this run '
                              '(_throat_gas_side, the same call that '
                              'produces the throat heat flux)'),
                T_aw=taw_throat,
                gas_cp=cp_throat,
                radius_m=r_throat,
                radius_source='throat radius solved by this run',
                gas_side_error=gas_side_error,
                particle_laden=self._condensed_fraction_info(),
                material=SOLID_NOZZLE_ENTRY_LINER_MATERIAL),
        }

    def _condensed_fraction_info(self):
        """(X_p, kaynak) — yoğuşmuş faz kütle kesri, iki-fazlı zincirle AYNI
        tablodan (SOLID_CONDENSED_MASS_FRACTION + aile devralması). Ablatif
        beyanı bu veriye bağlanır: X_p > 0 ise akış parçacıklıdır (APCP'de
        Al2O3, KN-şekerde K2CO3) ve mekanik/parçacık erozyonu MODELLENMEZ.
        Yakıt ADI üstünden koşullamak yerine tek veri kaynağı kullanılır.
        """
        # ÖH D15 a3 (P2B1-11): aynı TEK çözüm noktası (künye burada
        # kullanılmıyor; ablatif beyan yalnız X_p ve kaynak anahtarı okur).
        x_p, kaynak, _kunye = _condensed_mass_fraction(self.propellant_type)
        return x_p, kaynak

    def _ablative_liner_sizing(self, station, function, q_W_m2, station_note,
                               h_gas, h_gas_source, T_aw, gas_cp,
                               radius_m, radius_source,
                               gas_side_error=None, particle_laden=None,
                               material=None):
        """Ablatif kapak yalıtımı — yüzey enerji dengesiyle (v2.6.27, B6-4).

        Kalem 18-19 (P3) tarihçesi: ön kapak 5.0 mm, arka kapak 4.0 mm SABİT
        yazılıydı. v2.6.26'da Seviye-1 Q* modeline bağlandı ama SOĞUK-CİDAR
        boğaz akısıyla: iki kapak aynı sayıyı yayımlıyordu ve KNDX örnek
        koşusunda gerileme hızı (0.36-0.92 mm/s) modelin kendi 0.35 mm/s
        geçerlilik tavanının ÜSTÜNDEydi — zarf dışı sayı 'sized' diye
        basılıyordu.

        Yeni yol hibrit/sıvı bağlamasıyla AYNI sözleşme (alan adları birebir):
        çekirdek ``ablative_thickness`` h_g + T_aw + c_p + istasyon yarıçapı
        ile çağrılır; net akı yüzey enerji dengesinden, üfleme blokajı B'
        üzerinden ÖZ-TUTARLI çözülür; geçerlilik kapısı BAĞLAYICIDIR
        (NOT_MODELLED hükmü aynen taşınır, sayı uydurulmaz). Malzemeler
        istasyona göre ayrıdır ve beyan edilmiş TASARIM SEÇİMİdir:
        ön kapak elastomer (SOLID_FWD_CLOSURE_LINER_MATERIAL — NASA SP-8093
        kubbe yalıtımı elastomerdir: NBR/EPDM ailesi), lüle girişi fenolik
        (SOLID_NOZZLE_ENTRY_LINER_MATERIAL — SP-8115 nozul astarı sınıfı).

        Girdi ELDE EDİLEMEZSE (yanma süresi yok, Bartz zinciri kurulamadı)
        sayı ÜRETİLMEZ: NOT_MODELLED + eksik girdinin adı.
        """
        if material is None:
            material = SOLID_FWD_CLOSURE_LINER_MATERIAL
        burn_time = getattr(self, '_last_burn_time', None)
        if not burn_time or burn_time <= 0:
            return {
                'material': material,
                'thickness': None,
                'thickness_status': 'NOT_MODELLED',
                'function': function,
                'basis': ('Ablative thickness needs the solved burn time; '
                          'no thrust curve has been computed for this '
                          'motor instance.'),
            }
        eksikler = [ad for ad, deger in (
            ('h_gas', h_gas), ('T_recovery', T_aw), ('gas_cp', gas_cp),
            ('station_radius', radius_m), ('q_design_flux', q_W_m2)) if not (
                deger is not None and np.isfinite(float(deger))
                and float(deger) > 0)]
        if gas_side_error or eksikler:
            return {
                'material': material,
                'thickness': None,
                'thickness_status': 'NOT_MODELLED',
                'function': function,
                'basis': (
                    f'Ablative sizing at the {station} needs the gas-side '
                    f'station inputs of this run and could not get them: '
                    + (gas_side_error if gas_side_error
                       else 'missing or non-physical: ' + ', '.join(eksikler))
                    + '. No number is invented.'),
            }
        try:
            from hrma.analysis.thermal_protection import (
                ThermalProtectionAnalyzer)
            sizing = ThermalProtectionAnalyzer().ablative_thickness(
                q_net_W_m2=float(q_W_m2),
                burn_time_s=float(burn_time),
                material=material,
                h_gas_W_m2K=float(h_gas),
                T_recovery_K=float(T_aw),
                gas_cp_J_kgK=float(gas_cp),
                station_radius_m=float(radius_m))
        except Exception as exc:                       # pragma: no cover
            return {
                'material': material,
                'thickness': None,
                'thickness_status': 'NOT_MODELLED',
                'function': function,
                'basis': f'Ablative sizing failed at the {station}: {exc}',
            }

        # Parçacıklı akış beyanı: X_p > 0 ise mekanik/parçacık erozyonu bu
        # modelde YOK ve lüle girişinde ölçülen hızlar boğazı aşabildiği
        # için (Cortopassi 2012; Thakre & Yang 2013) sonuç bir ÜST SINIR
        # DEĞİL, tahmindir — beyan zorunlu.
        particle_note = ''
        if particle_laden is not None:
            x_p, x_src = particle_laden
            if x_p is not None and x_p > 0:
                particle_note = (
                    f' PARTICLE-LADEN FLOW: the condensed-phase mass '
                    f'fraction of this propellant is {x_p:.2f} (from the '
                    f'two-phase loss table, source key \'{x_src}\'). '
                    f'Particle-impingement / mechanical erosion is NOT '
                    f'modelled here, and measured convergent-entry rates '
                    f'can EXCEED throat rates (Cortopassi 2012; Thakre & '
                    f'Yang, JPP 2013), so for this propellant the result '
                    f'is an ESTIMATE, not an upper bound.')

        enerji_dengesi = (
            sizing['flux_basis'] == 'surface_energy_balance')
        kalinlik_mm = sizing['required_thickness_mm']
        if kalinlik_mm is None:
            liner_basis = (
                f'Level-1 Q* ablation sizing was RUN at the {station} '
                f'but published NO thickness. '
                f"{sizing['validity_note']} "
                f'Inputs are this run\'s solver values: gas-side '
                f'coefficient {float(h_gas):.0f} W/m2K ({h_gas_source}), '
                f'recovery temperature {float(T_aw):.0f} K, edge-gas cp '
                f'{float(gas_cp):.0f} J/kgK (the same Bartz gas properties '
                f'that produced h_g), burn time {float(burn_time):.2f} s, '
                f'station radius {float(radius_m) * 1e3:.1f} mm '
                f'({radius_source}). ' + station_note + particle_note)
        else:
            liner_basis = (
                f"Level-1 Q* ablation sizing at the {station}: required "
                f"thickness = total recession x design margin "
                f"{sizing['design_margin']:g}. "
                + ((
                    f'The net surface flux is SOLVED here from an energy '
                    f'balance at the {sizing["T_surface_K"]:.0f} K steady '
                    f'ablation temperature (self-consistent blowing '
                    f'blockage {sizing["blowing_blockage"]:.3f} x '
                    f'convection minus re-radiation at emissivity '
                    f'{sizing["emissivity"]:g}), driven by this run\'s '
                    f'gas-side coefficient {float(h_gas):.0f} W/m2K '
                    f'({h_gas_source}) and recovery temperature '
                    f'{float(T_aw):.0f} K. The cold-wall design flux '
                    f'({float(q_W_m2) / 1e3:.0f} kW/m2) is reported for '
                    f'COMPARISON only, it is not what sized this liner. ')
                   if enerji_dengesi else (
                    f'Heat flux ({float(q_W_m2) / 1e3:.0f} kW/m2) is this '
                    f'run\'s solver value and is used AS GIVEN: no surface '
                    f'energy balance was solved for this station. '))
                + f'Burn time ({float(burn_time):.2f} s) is the solved '
                f"value of this run. Liner material '{material}' is a "
                f'declared design choice, not a solved selection. '
                + station_note + particle_note)
        return {
            'material': sizing['material_name'],
            'thickness': (None if kalinlik_mm is None
                          else float(kalinlik_mm)),           # mm
            'thickness_status': sizing['thickness_status'],
            'function': function,
            'total_recession_mm': float(sizing['total_recession_mm']),
            'recession_rate_mm_s': float(sizing['recession_rate_mm_s']),
            'design_margin': float(sizing['design_margin']),
            'q_star_mj_kg': float(sizing['q_star_MJ_kg']),
            # Çağıranın (soğuk cidar) akısı — karşılaştırma değeridir,
            # boyutlandıran değer değildir.
            'heat_flux_kw_m2': float(q_W_m2) / 1e3,
            'burn_time_s': float(burn_time),
            'flux_basis': sizing['flux_basis'],
            'recession_regime': sizing['recession_regime'],
            'q_net_kw_m2': float(sizing['q_mean_W_m2']) / 1e3,
            'q_conv_blocked_kw_m2': (
                None if sizing['q_conv_blocked_W_m2'] is None
                else float(sizing['q_conv_blocked_W_m2']) / 1e3),
            'q_reradiated_kw_m2': (
                None if sizing['q_reradiated_W_m2'] is None
                else float(sizing['q_reradiated_W_m2']) / 1e3),
            'h_gas_W_m2K': sizing['h_gas_W_m2K'],
            'h_gas_source': h_gas_source,
            'T_recovery_K': sizing['T_recovery_K'],
            'T_surface_K': sizing['T_surface_K'],
            'emissivity': sizing['emissivity'],
            'emissivity_source': sizing['emissivity_source'],
            # v2.6.27 blokaj denetimi: psi çözülmüş değerdir, türetimiyle
            # birlikte yayımlanır.
            'blowing_blockage': sizing['blowing_blockage'],
            'b_prime': sizing['b_prime'],
            'blowing_lambda': sizing['blowing_lambda'],
            'blowing_gas_fraction': sizing['blowing_gas_fraction'],
            'blockage_basis': sizing['blockage_basis'],
            'gas_cp_J_kgK': sizing['gas_cp_J_kgK'],
            'station_radius_m': sizing['station_radius_m'],
            'station_radius_source': radius_source,
            'model_valid': bool(sizing['model_valid']),
            'validity_note': sizing['validity_note'],
            'basis': liner_basis,
            'model_note': sizing['model_note'],
            'source': sizing['source'],
            'surface_source': sizing['surface_source'],
        }
    
    def _case_free_volume(self):
        """Kasa serbest (boş) hacmi [m³] = kasa iç hacmi − yakıt hacmi.

        TEK tanım noktası: hem calculate_performance'ın raporladığı
        'case_free_volume_l' hem ateşleyici boyutlandırması buradan okur
        (aynı kavram iki yerde iki farklı sayı olamaz).
        """
        interior = (np.pi * (self.D_chamber / 2.0) ** 2
                    * self._case_inner_length())
        return float(max(interior - self._propellant_volume(), 0.0))

    def _design_igniter_system(self):
        """Ateşleyici — serbest hacim basınçlandırma ölçütüyle boyutlandırılır.

        EK BULGU (P3, v2.6.26). Bu blok BAŞTAN SONA elle yazılmış bir
        sözlüktü: 2.0 g kara barut, 0.2 s yanma, 2200 °C alev, 10 mm çaplı
        50 mm boyunda 1 mm cidarlı kap, 'Nichrome 32 AWG / 2.0 Ohms /
        3A for 1 second'. 75 mm'lik bir amatör motorla 200 mm'lik bir motor
        AYNI ateşleyiciyi alıyordu; hiçbir sayı motorun serbest hacmine,
        basıncına ya da yakıtına bağlı değildi.

        Boyutlandırılan tek büyüklük ŞARJ KÜTLESİdir ve klasik serbest hacim
        basınçlandırma ölçütünden gelir (NASA SP-8051, "Solid Rocket Motor
        Igniters"; Sutton & Biblarz 9. baskı Böl. 12 ateşleme bölümü):

            m_gaz  = P_ateş · V_serbest / (R_gaz · T_gaz)
            m_şarj = m_gaz / (1 − X_yoğuşmuş)

        Burada
          * V_serbest : kasa iç hacmi − yakıt hacmi (_case_free_volume),
          * P_ateş    : hedef ateşleme basıncı; TASARIM SEÇİMİdir, hesap
            değildir — kullanıcı girdisiyle (igniter_pressure_fraction)
            verilir ve çıktıda adıyla beyan edilir,
          * R_gaz,T_gaz: şarjın merkezi katalog kaydından (molekül ağırlığı
            ve alev sıcaklığı),
          * X_yoğuşmuş: şarjın yoğuşmuş faz kütle kesri — kara barut
            kütlesinin yarıdan fazlası katı kalıntıdır ve bu kesir projede
            ZATEN tablolu (SOLID_CONDENSED_MASS_FRACTION); yalnız gaz fazı
            kamarayı basınçlandırır.

        BOYUTLANDIRILMAYANLAR (sayı üretilmez, NOT_MODELLED etiketlenir):
          * yanma süresi — motorun basınç yükselme süresine (tipik olarak
            %90 Pc'ye ulaşma) eşlenmesi gerekir; HRMA'da ateşleme geçici
            rejim modeli yoktur,
          * kap çapı/boyu — dolum oranı ve L/D seçimine bağlıdır, ikisi de
            yayımlanmış bir kayda dayanmaz,
          * cidar kalınlığı — kap yarıçapı boyutlandırılmadığı için
            t = P·r/(σ_y/SF) değerlendirilemez,
          * köprü teli / direnç / akım — elektriksel ateşleme modeli yok.
        """
        cfg = SOLID_IGNITER
        lo, hi = cfg['pressure_fraction_range']
        fraction = self._override_val('igniter_pressure_fraction', lo, hi)
        fraction_source = 'igniter_pressure_fraction input'
        if fraction is None:
            fraction = cfg['pressure_fraction_default']
            fraction_source = ('default design choice (no '
                               'igniter_pressure_fraction supplied)')

        charge_key = cfg['charge_record']
        rec = _get_propellant_safe(charge_key)
        x_condensed = SOLID_CONDENSED_MASS_FRACTION.get(charge_key)
        v_free = self._case_free_volume()
        p_ign_bar = float(self.P_c) * float(fraction)

        grain = {
            'material': (rec or {}).get('name', charge_key),
            'charge_record': charge_key,
        }
        _x_gecerli = (x_condensed is not None
                      and 0.0 <= float(x_condensed) < 1.0)
        if not rec or not _x_gecerli or v_free <= 0 or p_ign_bar <= 0:
            grain.update({
                'mass': None,
                'mass_status': 'NOT_MODELLED',
                'basis': ('The igniter charge cannot be sized: the free '
                          'volume, the ignition pressure or the charge gas '
                          'record is missing. No number is reported.'),
            })
        else:
            # v2.6.27: serbest hacim basınçlandırma ölçütü artık burada elle
            # YAZILMAZ, doğrulanmış modülden çağrılır — aynı bağıntının iki
            # ayrı yerde durması tek tanım noktası kuralını çiğniyordu.
            # Bağıntı, birimler ve girdiler birebir aynı olduğundan sayılar
            # değişmez (bekçi testi bunu kilitler).
            from hrma.analysis.igniter_sizing import pyrotechnic_charge_mass
            t_gas = float(rec['flame_temperature'])               # K
            _sarj = pyrotechnic_charge_mass(
                ignition_pressure_Pa=p_ign_bar * 1e5,
                free_volume_m3=float(v_free),
                gas_molecular_weight_g_mol=float(rec['molecular_weight']),
                gas_temperature_K=t_gas,
                condensed_mass_fraction=float(x_condensed))
            m_charge = float(_sarj['charge_mass_kg'])             # kg
            m_gas = float(_sarj['gas_mass_kg'])                   # kg
            gas_fraction = float(_sarj['gas_mass_fraction'])
            grain.update({
                'mass': float(m_charge * 1000.0),                 # gram
                'mass_status': 'sized',
                'gas_mass_g': float(m_gas * 1000.0),
                'flame_temperature_k': t_gas,
                'gas_molecular_weight_g_mol': float(rec['molecular_weight']),
                'gas_mass_fraction': gas_fraction,
                'ignition_pressure_bar': p_ign_bar,
                'ignition_pressure_fraction_of_pc': float(fraction),
                'ignition_pressure_source': fraction_source,
                'free_volume_l': float(v_free * 1000.0),
                'charge_volume_cm3': float(m_charge / float(rec['density'])
                                           * 1e6),
                'sizing_module': (
                    'hrma.analysis.igniter_sizing.pyrotechnic_charge_mass '
                    f'(HRMA {_hrma_version()})'),
                'module_basis': _sarj.get('_basis'),
                'basis': (
                    'Free-volume pressurisation criterion (NASA SP-8051), '
                    'evaluated by hrma.analysis.igniter_sizing.'
                    'pyrotechnic_charge_mass: m_charge = '
                    'P_ign*V_free/(R*T) / (1 - X_condensed). '
                    'P_ign is a DESIGN CHOICE ('
                    f'{fraction:.0%} of the chamber pressure, '
                    f'{fraction_source}), not a computed quantity. The charge '
                    'gas properties reported here - flame temperature and '
                    'gas molecular weight in g/mol - are CATALOGUE VALUES of '
                    f'the igniter charge record "{charge_key}" '
                    f'({rec.get("source", "propellants_db")}); the charge is '
                    'a fixed choice of this solver, so those two properties '
                    'do not change with your motor design. Condensed '
                    f'mass fraction {float(x_condensed):.2f} from '
                    'SOLID_CONDENSED_MASS_FRACTION.'),
                'model_limitation': (
                    'Quasi-static ideal-gas criterion: it sizes the charge '
                    'that fills the free volume to P_ign, it does NOT model '
                    'the ignition transient, flame spreading or heat loss '
                    'to the grain surface. Static-fire confirmation is '
                    'required.'),
            })
        # Yanma süresi: ateşleme geçici rejimi modellenmiyor (bkz. docstring).
        grain.update({
            'burn_time': None,
            'burn_time_status': 'NOT_MODELLED',
            'burn_time_basis': (
                'The igniter burn time must match the motor pressure-rise '
                'time (typically time to 90% of Pc). HRMA has no ignition '
                'transient model, so no number is reported.'),
        })
        return {
            'igniter_type': 'Pyrotechnic',
            'igniter_grain': grain,
            # v2.6.27: ateşleyici modülünün ŞARJ KÜTLESİ yolu yukarıda
            # bağlandı; modülün DİĞER iki yolunun katı motorda neden
            # değerlendirilmediği burada adıyla beyan edilir (sessiz eksiklik
            # yerine açık beyan).
            'ignition_energy_and_window': {
                'status': 'NOT_MODELLED',
                'ignition_energy': {
                    'status': 'NOT_MODELLED',
                    'missing_inputs': ['propellant_specific_heat_J_kg_K',
                                       'propellant_ignition_temperature_K'],
                    'basis': (
                        'The required ignition energy '
                        '(hrma.analysis.igniter_sizing.'
                        'ignition_energy_required) needs the propellant '
                        'specific heat and its ignition temperature. Neither '
                        'is carried by the HRMA propellant records, which '
                        'hold density, burn-rate law, c*, flame temperature, '
                        'gamma and exhaust molecular weight only, and no '
                        'literature value is substituted. No ignition energy '
                        'is reported.'),
                },
                'torch_path': {
                    'status': 'NOT_APPLICABLE',
                    'basis': (
                        'The torch-igniter path of the module sizes a '
                        'continuously burning pre-burner fed from a '
                        'propellant feed system. A solid motor is ignited by '
                        'a pyrotechnic charge and has no feed system, so the '
                        'torch path has no counterpart here and is not '
                        'evaluated.'),
                },
                'safe_ignition_window': {
                    'status': 'NOT_APPLICABLE',
                    'basis': (
                        'The hard-start window of the module bounds the '
                        'ignition delay during which UNBURNT propellant '
                        'accumulates in the chamber from a feed system and '
                        'could then burn at constant volume all at once. A '
                        'solid grain does not accumulate: its propellant is '
                        'already in the chamber as a solid and only the '
                        'burning surface produces gas, so that mechanism has '
                        'no counterpart here and the criterion is not '
                        'evaluated. The solid-motor ignition overpressure '
                        'transient (igniter mass flow versus free volume '
                        'filling and flame spreading over the grain) is a '
                        'different problem and is NOT modelled - see '
                        'igniter_grain.burn_time_basis.'),
                },
                'basis': (
                    'Declaration of which parts of '
                    f'hrma.analysis.igniter_sizing (HRMA {_hrma_version()}) '
                    'are wired into the solid path: the pyrotechnic '
                    'free-volume charge sizing is (see '
                    'igniter_grain.sizing_module); the ignition energy '
                    'balance and the hard-start window are not, for the '
                    'reasons given above.'),
            },
            'igniter_case': {
                'material': 'NOT_DEFINED',
                'diameter': None,
                'length': None,
                'wall_thickness': None,
                'status': 'NOT_MODELLED',
                'basis': ('The igniter case envelope depends on the charge '
                          'bulk fill fraction and a chosen length/diameter '
                          'ratio; neither has a published record in HRMA, so '
                          'no dimensions are reported. The required charge '
                          'volume is given in igniter_grain.'),
            },
            'electrical_system': {
                'bridge_wire': 'NOT_DEFINED',
                'resistance': None,
                'current_requirement': None,
                'status': 'NOT_MODELLED',
                'basis': ('HRMA has no electrical initiation model (bridge '
                          'wire energy balance, no-fire/all-fire current); '
                          'the previous fixed "Nichrome 32 AWG / 2.0 Ohms / '
                          '3 A" text was not derived from anything.'),
                'safety_features': ['Continuity test', 'Arming switch',
                                    'Safety key'],
            },
            'installation': {
                'mounting': 'Forward closure threaded port',
                'alignment': 'Aimed at grain core center',
                'wire_routing': 'Sealed electrical feedthrough',
                'basis': ('Installation practice, not a computed result.'),
            }
        }
    
    def _generate_manufacturing_drawings(self):
        """İmalat resmi paketinin İÇERİK LİSTESİ — ölçü/tolerans üretmez.

        EK BULGU (P3, v2.6.26). Bu blok tolerans ve geçme sınıfı BEYAN
        ediyordu: '±0.01mm boğaz', '±0.05mm kasa deliği', 'H7/f6 geçme',
        '2A/2B diş sınıfı'. Hiçbiri hesaplanmıyordu ve motorun boyutundan,
        malzemesinden, basıncından bağımsızdı — kullanıcı bunları HRMA'nın
        kendi tasarımı için verdiği imalat gereksinimi sanabilirdi.
        Aynı sınıftaki 'surface_finish' / 'threads' alanları kasa bloğunda
        zaten NOT_DEFINED'a çevrilmişti (v2.6.26); bu blok da aynı kurala
        getirildi: sayı üretilmez, ne yapılması gerektiği söylenir.

        Geriye kalan liste bir DOKÜMAN listesidir (hangi resimler çizilmeli),
        hesap sonucu değildir ve öyle beyan edilir.
        """
        return {
            'basis': ('Document checklist for a manufacturing drawing '
                      'package. HRMA does not produce dimensional tolerances, '
                      'fits or thread classes: those follow from the '
                      'manufacturing process, the material and the assembly '
                      'stack-up, none of which are modelled here.'),
            'drawing_set': {
                'assembly_drawing': 'Overall motor assembly with BOM',
                'case_drawing': 'Machined case with all dimensions',
                'grain_drawing': 'Propellant grain geometry',
                'nozzle_drawing': 'Nozzle contour and dimensions',
                'closure_drawings': 'Forward/aft closure details'
            },
            'drawing_standards': {
                'format': 'ANSI Y14.5M-1994',
                'tolerance_standard': 'ISO 2768-1',
                'surface_symbols': 'ISO 1302',
                'material_callouts': 'ASTM standards',
                'revision_control': 'Controlled document system',
                'basis': ('A conventional standard set for this drawing '
                          'package; it is a template choice, not a result '
                          'derived from this motor.'),
            },
            'critical_dimensions': {
                'status': 'NOT_MODELLED',
                'throat_diameter': None,
                'case_bore': None,
                'grain_fit': None,
                'thread_class': None,
                'surface_finish': None,
                'basis': ('Tolerances, fits and thread classes are not sized '
                          'by HRMA. The previous fixed values (+/-0.01 mm '
                          'throat, +/-0.05 mm bore, H7/f6, 2A/2B) applied to '
                          'every motor regardless of size and were not '
                          'derived from anything.'),
            }
        }
    
    #: Kürleme çizelgesi (süre + sıcaklık) HRMA'nın MODELLEDİĞİ bir şey
    #: değildir: yalıtım/yapıştırıcı/inhibitör reçinesinin kür kinetiği
    #: üreticinin teknik veri sayfasından (TDS) gelir. Yakıt kaydındaki
    #: 'cure_temperature_k' GRAIN'in kürleme sıcaklığıdır ve grain termal
    #: gerinim hesabında kullanılır — yalıtım ya da inhibitör kaplamasının
    #: kürlemesi DEĞİLDİR, o yüzden buraya taşınamaz.
    CURE_SCHEDULE_BASIS = (
        'NOT_MODELLED: HRMA has no cure-kinetics model. Use the cure schedule '
        'on the technical data sheet of the insulation/adhesive/inhibitor '
        'resin you actually buy; the previous fixed "24 h at 60 C" / "8 h at '
        'room temperature" values were the same for every motor and every '
        'material.')

    def _generate_assembly_sequence(self):
        """Montaj sırası — SAYILAR ya hesaptan gelir ya hiç yazılmaz.

        v2.6.26 (P4). Bu liste üç uydurma sayı taşıyordu:
        'cure_time: 24 hours at 60°C', 'cure_time: 8 hours at room
        temperature' ve 'requirement: Torque to 150 Nm'. Üçü de motorun
        boyutundan, malzemesinden ve basıncından bağımsızdı.

        * Sıkma torku artık HESAPLANIR: kapak cıvata birleşimi zaten
          ``_closure_joint_analysis`` ile çözülüyor (Shigley Böl. 8 /
          ISO 898-1); tork T = K·F_i·d oradan okunur. Kullanıcı cıvata
          sayısını girmediyse birleşim boyutlandırılmaz ve tork alanı sayı
          yerine gerekçe taşır.
        * Kürleme çizelgesi MODELLENMİYOR olarak beyan edilir
          (CURE_SCHEDULE_BASIS).

        Adımların kendisi (sırayla ne yapılacağı) genel montaj pratiğidir;
        bu da 'basis' alanında söylenir.
        """
        joint = self._closure_joint_analysis()
        torque_nm = joint.get('tightening_torque_nm')
        if torque_nm is not None:
            closure_requirement = (
                f"Torque {joint['bolt_count']} x {joint['bolt_size']} "
                f"{joint['property_class']} closure bolts to "
                f"{torque_nm:.1f} Nm")
            closure_basis = joint.get('tightening_torque_basis')
        else:
            closure_requirement = None
            closure_basis = (
                'NOT_SIZED: no closure bolt count was supplied, so the '
                'tightening torque cannot be computed (it follows from bolt '
                'preload and diameter). Enter the closure bolt count, size '
                'and property class. The previous fixed "150 Nm" was '
                'independent of bolt size, class and chamber pressure.')
        return {
            'basis': ('The order of operations is general solid-motor '
                      'assembly practice, not a result computed for this '
                      'motor. Numeric requirements below are either computed '
                      '(named in their own basis field) or declared as '
                      'not modelled.'),
            'sequence': [
                {
                    'step': 1,
                    'operation': 'Inspect case bore',
                    'requirement': 'Dimensional and surface finish check',
                    'tooling': 'Coordinate measuring machine'
                },
                {
                    'step': 2,
                    'operation': 'Apply thermal barrier',
                    'requirement': 'Even coating thickness',
                    'cure_time': None,
                    'cure_time_basis': self.CURE_SCHEDULE_BASIS,
                },
                {
                    'step': 3,
                    'operation': 'Install propellant grain',
                    'requirement': 'Press fit with alignment',
                    'caution': 'Avoid damage to grain surfaces'
                },
                {
                    'step': 4,
                    'operation': 'Apply inhibitor coating',
                    'requirement': 'Complete coverage of designated areas',
                    'cure_time': None,
                    'cure_time_basis': self.CURE_SCHEDULE_BASIS,
                },
                {
                    'step': 5,
                    'operation': 'Install forward closure',
                    'requirement': closure_requirement,
                    'tightening_torque_nm': torque_nm,
                    'tightening_torque_basis': closure_basis,
                    'sealant': 'High-temperature thread sealant'
                },
                {
                    'step': 6,
                    'operation': 'Install igniter system',
                    'requirement': 'Electrical continuity check',
                    'safety': 'ESD precautions required'
                },
                {
                    'step': 7,
                    'operation': 'Install nozzle assembly',
                    'requirement': 'Alignment and torque spec',
                    'final_check': 'Visual inspection of throat'
                }
            ]
        }


    def _generate_quality_requirements(self):
        """Kalite kontrol listesi — NE YAPILACAĞI, kabul SAYISI değil.

        v2.6.26 (P4). Bu blok dört uydurma kabul ölçütü taşıyordu:
        '1.5x design pressure for 30 seconds', 'Helium leak test <1e-6 std
        cm³/s', 'Total mass within ±2%' ve 'Continuity within 2.0±0.2 Ohms'.
        Hiçbiri hesaplanmıyordu; hepsi her motorda aynıydı. Sızdırmazlık
        eşiği kullanılan conta/ölçüm yöntemine, kütle bandı üretim sürecine,
        ateşleyici direnci köprü teli tipine bağlıdır — HRMA bunların
        hiçbirini modellemiyor. Basınç testi seviyesi ise bir PROGRAM
        kararıdır; HRMA'nın hesapladığı tasarım ve kopma basınçları
        safety_analysis bloğundadır, kullanıcı oraya yönlendirilir.

        Kalan liste bir DENETİM PLANIdır (hangi ölçüm yapılmalı), bir kabul
        şartnamesi değildir ve öyle beyan edilir.
        """
        return {
            'basis': ('Inspection plan: which checks to perform. HRMA does '
                      'not set acceptance limits - leak rates, mass bands, '
                      'igniter resistance and proof-test levels come from '
                      'your process, hardware and test authority, none of '
                      'which are modelled here.'),
            'incoming_inspection': {
                'propellant_grain': ['Dimensional check', 'Density test', 'Visual inspection'],
                'case_material': ['Material certification', 'Hardness test', 'Surface finish'],
                'nozzle_components': ['Throat diameter', 'Surface roughness', 'Contour accuracy']
            },
            'in_process_testing': {
                'thermal_barrier': ['Thickness measurement', 'Adhesion test'],
                'assembly_torque': ['Torque wrench calibration', 'Recorded values'],
                'electrical_continuity': ['Resistance measurement', 'Insulation test']
            },
            'final_inspection': {
                'status': 'NOT_MODELLED',
                'pressure_test': None,
                'pressure_test_basis': (
                    'Proof-test level and hold time are a programme decision. '
                    'The pressures HRMA actually computes for this motor '
                    '(design, burst, yield, relief) are in '
                    'safety_analysis.pressure_safety.'),
                'leak_test': None,
                'leak_test_basis': (
                    'Allowable leak rate depends on the seal, the test method '
                    'and the mission; HRMA has no seal or leakage model.'),
                'weight_check': None,
                'weight_check_basis': (
                    'Mass tolerance is a production-process band, not a '
                    'solver output. The predicted masses are in the mass '
                    'breakdown; compare measured hardware against those.'),
                'documentation': 'Complete test records and certificates'
            },
            'acceptance_criteria': {
                'status': 'NOT_MODELLED',
                'dimensional_tolerance': 'All dimensions within drawing limits',
                'surface_finish': 'All surfaces meet Ra requirements',
                'electrical_test': None,
                'electrical_test_basis': (
                    'Igniter bridgewire resistance follows from the igniter '
                    'you use (bridgewire material, length, diameter); HRMA '
                    'does not model the igniter circuit. The previous fixed '
                    '"2.0 +/- 0.2 Ohms" was printed for every motor.'),
                'pressure_test': 'No leakage or deformation'
            }
        }

    def _insulation_density(self):
        """Yalıtım/liner katmanının yoğunluğu [kg/m3] — TEK tanım noktası.

        ÖH D17 (P2B3-10). Aynı katmanın yoğunluğu üç yerde iki farklı sayı
        veriyordu: ısıl koruma paneli ve geçici kasa sıcaklığı zinciri
        kullanıcının ``liner_density`` girdisini okurken KÜTLE zinciri
        (``_dry_mass_breakdown``) her koşuda SOLID_INSULATION tablo değerini
        (1200 kg/m3) kullanıyordu. ÖLÇÜLDÜ
        (docs/scofield/raw/OH/D17/kati/a1/once.json; yalıtım 3 mm,
        liner 2 mm, D=100 mm, L=500 mm):

          liner_density girdisi   panel 'density'   insulation_kg
          (girilmedi -> 1200)        1200,0            0,698942
          1900                       1900,0            0,698942   <- DEĞİŞMEDİ

        yani kullanıcı yoğunluğu %58 artırdığında panel yeni sayıyı
        gösteriyor, kuru kütle hiç kıpırdamıyordu. Girdi artık kütleye de
        işler; girilmediyse tablo değeri tek kaynaktır.

        NOT (ÖH D24, OH-D23-10): yukarıdaki iki MUTLAK sayı D17 dönemine
        aittir; katman sırası düzeltildikten sonra aynı motorda
        ``insulation_kg`` 0,698942 -> 0,726085 (1200 kg/m3) ve
        1,106657 -> 1,149634 (1900 kg/m3) olur — yalıtım halkası artık
        liner'ın DIŞINDA durduğu için iç çapı D yerine D+2·t_liner'dır.
        Bu kalemin ölçtüğü ORAN (1900/1200) değişmez; kütle yoğunlukla
        tam orantılı kalır.
        """
        rho = getattr(self, 'liner_density', None)
        if rho is None:
            return float(SOLID_INSULATION['density_kg_m3'])
        return float(rho)

    def _available_web_thickness(self):
        """Port yüzeyinden kasaya kadar TÜKETİLEBİLİR web [m] — TEK tanım.

        ÖH D15 a3 (P2B2-04). ``_web_utilization_percent`` paydayı
        ``_max_web_thickness()``ten okuyordu; o büyüklük shapely'li
        tiplerde (star / wagon_wheel / finocyl / slotted) çözücünün TARAMA
        ÜST SINIRIDIR ve bilerek kasa YARIÇAPI kadar geniş tutulur
        (güvenlik ağı). Payda olarak kullanılınca PORT YARIÇAPI da
        "tüketilebilir yakıt" sayılıyor ve tamamen tükenmiş grainler eksik
        kullanılmış görünüyordu. ÖLÇÜLDÜ (D_kasa = 100 mm,
        D_çekirdek = 30 mm, L = 500 mm, APCP, 40 bar) — yanma alanı SIFIRA
        indiği hâlde:

          grain          yayımlanan      fiziksel tabanla
          finocyl          69,9998 %        99,9997 %
          star             56,0849 %        80,1213 %
          wagon_wheel      46,2111 %        66,0159 %
          slotted          45,6724 %        65,2462 %
          bates            99,9433 %        99,9433 %   (zaten doğruydu)

        dört tipte de sapma tam olarak (R_dış) / (R_dış - r_port) = 1,42857
        katıdır. Gerileme port YÜZEYİNDEN başlar; kasaya kadar kalan et
        radyal tiplerde (D_kasa - D_çekirdek)/2, end-burner'da ise yanma
        EKSENEL olduğu için grain boyudur.

        Bu büyüklük ``_max_web_thickness`` (çözücü tarama sınırı) ve
        ``_geometric_web_thickness`` (en İNCE kesit) ile karıştırılmamalıdır;
        üçü ayrı sorulardır ve ayrı adlarla yayımlanır.

        ÖH D17 (P2B2-04 ŞART). (D_kasa - D_çekirdek)/2 paydası POLİGON
        tiplerde de tam tükenişte %100 vermiyordu: yakıt fiilen bittiği
        (Ab -> 0) hâlde kullanım %65-80 okunuyordu, çünkü poligon kesitte
        yanma yüzeyi kasaya RADYAL DOĞRULTUDA aynı anda ulaşmaz — yanma
        alanı, radyal et bitmeden önce sıfırlanır. ÖLÇÜLDÜ
        (docs/scofield/raw/OH/D17/kati/a1/once.json; D=100 mm,
        çekirdek 30 mm, L=500 mm, APCP, 40 bar):

          grain        (D-d)/2   çözücünün tükeniş webi   yayımlanan
                                 (Ab -> 0)                kullanım (önce)
          star          35,0 mm        28,042 mm            80,121 %
          wagon_wheel   35,0 mm        23,106 mm            66,016 %
          slotted       35,0 mm        22,836 mm            65,246 %
          finocyl       35,0 mm        35,000 mm            99,9997 %
          bates         35,0 mm        (kapalı form)        99,943 %

        Aynı koşularda Ab(w_tüketilen)/Ab(0) sırasıyla 0,0335 / 0,0375 /
        0,0254 — yani grain gerçekten bitmiş. Payda artık ÇÖZÜCÜNÜN KENDİ
        tükeniş webidir (``_burnout_web``, calculate_burn_area üzerinden);
        ikinci bir alan tanımı üretilmez. Kapalı formlu tiplerde (bates ve
        shapely'siz yedekler) fiziksel radyal et zaten doğru paydadır.
        """
        if self.grain_type == 'end_burner':
            self._available_web_basis = {
                'source': 'axial_grain_length',
                'detail': ('an end burner burns axially, so the consumable '
                           'web is the grain length'),
            }
            return float(self.L_grain)
        radyal = float((self.D_chamber - self.D_core) / 2)
        if (self.grain_type in SOLID_POLYGON_GRAIN_TYPES
                and SHAPELY_AVAILABLE):
            tukenis = self._geometric_burnout_web()
            if tukenis is not None:
                self._available_web_basis = {
                    'source': 'geometric_burnout_web',
                    'detail': ('the thickness at which the offset '
                               'cross-section stops burning (Ab -> 0), '
                               'solved by the same routine the thrust curve '
                               'uses'),
                }
                return tukenis
            # ÖH D20 (OH-D19-23): geometrik tükeniş KAZANILAMADI. Radyal ete
            # düşmek sayı uydurmak değildir, ama sessizce düşmek beyanı
            # yalanlar: payda artık kendi kaynağını söyler.
            self._available_web_basis = {
                'source': 'radial_web_fallback',
                'detail': ('the geometric burnout web could not be '
                           'established for this polygon cross-section, so '
                           'the physical radial web (D_chamber - D_core)/2 '
                           'is used as the denominator instead'),
                'geometric_burnout_status': getattr(
                    self, '_burnout_web_status', None),
            }
            return radyal
        self._available_web_basis = {
            'source': 'radial_web',
            'detail': ('closed-form cross-section: the physical radial web '
                       '(D_chamber - D_core)/2 is the consumable web'),
        }
        return radyal

    def _geometric_burnout_web(self):
        """Poligon kesitte yanma alanının SIFIRLANDIĞI web [m] — ya da None.

        ÖH D17 (P2B2-04). Çözücü tükenişi zaten geometrik olarak biliyor
        (``calculate_thrust_curve`` sonlanmayı 'burn_area_vanished' ile
        kapatır ve tükeniş anını ``_burnout_web`` ile daraltır); burada
        AYNI fonksiyon web aralığının tamamı için çağrılır, yani ikinci bir
        tükeniş tanımı yazılmaz. Örnek üstünde geometri anahtarıyla
        önbelleklenir — shapely ofseti pahalıdır.

        Ab(0) <= 0 ya da Ab(w_max) > 0 ise (tarama sınırı içinde tükenmiyor)
        None döner ve çağıran fiziksel radyal ete geri düşer: UYDURMA
        payda üretilmez.
        """
        key = self._grain_geometry_key()
        memo = getattr(self, '_burnout_web_memo', None)
        if memo is not None and memo[0] == key:
            self._burnout_web_status = memo[2]
            return memo[1]
        deger = None
        # ÖH D20 (OH-D19-23): burada çıplak `except Exception: deger = None`
        # duruyordu. Her hata — shapely ofsetinin patlaması, kesitin
        # kurulamaması, NaN — SESSİZCE None'a çevriliyor, çağıran fiziksel
        # radyal ete düşüyor ve ürün yüzü (web_thickness_utilization_basis)
        # paydanın "yanan alanın sıfırlandığı kalınlık" olduğunu SÖYLEMEYE
        # DEVAM EDİYORDU. ÖLÇÜLDÜ (once.json / OH-D19-23): _max_web_thickness
        # zorla patlatıldığında dönen değer None, dışarıya tek bir alan bile
        # sızmıyor — yani "geometrik" iddiası hesaplanmamışken de ayakta.
        # Sayı hâlâ uydurulmaz (None dönmeye devam eder, radyal ete düşülür),
        # ama HANGİ hükmün kazanıldığı artık adıyla saklanır ve yayımlanır.
        durum = 'not_computed'
        try:
            w_max = float(self._max_web_thickness())
            if not (np.isfinite(w_max) and w_max > 0):
                durum = 'scan_bound_not_usable'
            elif float(self.calculate_burn_area(0.0)) <= 0.0:
                durum = 'no_initial_burning_area'
            elif float(self.calculate_burn_area(w_max)) > 0.0:
                durum = 'not_extinguished_within_scan_bound'
            else:
                w = float(self._burnout_web(0.0, w_max))
                if np.isfinite(w) and w > 0.0:
                    deger = w
                    durum = 'geometric'
                else:
                    durum = 'solver_returned_non_physical_web'
        except Exception as hata:      # noqa: BLE001 - durum ADIYLA saklanır
            durum = 'failed: %s: %s' % (type(hata).__name__, hata)
        self._burnout_web_status = durum
        self._burnout_web_memo = (key, deger, durum)
        return deger

    def _max_web_thickness(self):
        """Yanmanın kesilebileceği web ÜST SINIRI [m] — TEK tanım noktası.

        v2.6.27 (A1-1): bu kural ``calculate_thrust_curve`` içinde gömülüydü;
        boğaz boyutlandırması aynı aralığı taramak zorunda olduğu için buraya
        alındı ve çözücü artık buradan okur — iki yerde iki farklı web
        aralığı tanımlanamaz.

          * end_burner: yanma EKSENELDİR, tükenme grain boyunda olur.
          * shapely'li tipler (star/wagon_wheel/finocyl/slotted): ofset modeli
            tükenmeyi geometrik bilir (A_burn → 0); buradaki sınır yalnız
            güvenlik ağıdır, bu yüzden kasa yarıçapı kadar geniş tutulur.
          * bates (ve shapely'siz yedekler): radyal web (D_kamara − D_çekirdek)/2.
        """
        if self.grain_type == 'end_burner':
            return float(self.L_grain)
        if (self.grain_type in SOLID_POLYGON_GRAIN_TYPES
                and SHAPELY_AVAILABLE):
            return float(self.D_chamber / 2)
        return float((self.D_chamber - self.D_core) / 2)

    def _geometric_web_thickness(self):
        """En İNCE yakıt kesiti [m] — TEK tanım noktası (grain tipine duyarlı).

        ÖH D15 a2 (P2B4-02). Yayımlanan ``grain_design.web_thickness_mm``
        grain tipini HİÇ görmüyordu: ``(D_kamara - D_çekirdek)/2`` altı grain
        tipinde de aynı 35,0 mm'yi basıyordu. ÖLÇÜLDÜ (D=100, L=500,
        core=30 mm, APCP, 40 bar) — fiilen tüketilen web ile yan yana:

          grain        yayımlanan   fiilen tüketilen (int r dt)
          bates            35,0 mm        34,946 mm
          star             35,0 mm        27,995 mm
          end_burner       35,0 mm       500,000 mm   <- 14,3 KAT
          finocyl          35,0 mm        34,996 mm
          slotted          35,0 mm        22,769 mm
          wagon_wheel      35,0 mm        23,057 mm

        End-burner'da yanma EKSENELDİR; radyal formül orada tanımsızdır.
        Buradaki sayı "en ince kesit"tir (yapısal/imalat anlamı); yanmanın
        tarayabildiği ÜST SINIR ``_max_web_thickness()``, gerçekte TÜKENEN
        kalınlık ise itki eğrisinden ``_consumed_web()`` ile ölçülür. Üç
        büyüklük ayrıdır ve grain_design'da ayrı adlarla yayımlanır.

        Çözülemeyen tip için sayı UYDURULMAZ: ``None`` döner ve yayımlayan
        blok bunu gerekçesiyle söyler.
        """
        gt = self.grain_type
        if gt == 'end_burner':
            # Eksenel yanma: en ince kesit yanma yönündeki grain boyudur.
            return float(self.L_grain)
        if gt == 'bates':
            return float((self.D_chamber - self.D_core) / 2)
        if gt == 'star':
            # Uçların ALTINDAKİ web en incedir (_analyze_star_grain ile aynı).
            return float((self.D_chamber - self.D_core) / 2
                         - self._star_params()[1])
        if gt == 'finocyl':
            return float((self.D_chamber - self.D_core) / 2
                         - self._finocyl_params()[2])
        if gt == 'slotted':
            return float((self.D_chamber - self.D_core) / 2
                         - self._slotted_params()[2])
        if gt == 'wagon_wheel':
            # Çevre delikleri R_pitch = D_kamara/4 üzerinde, yarıçapları
            # D_çekirdek/4 (_wagon_port_polygon ile AYNI kurulum).
            return float(self.D_chamber / 2
                         - (self.D_chamber / 4 + self.D_core / 4))
        return None

    @staticmethod
    def _consumed_web(curve):
        """İtki eğrisi boyunca FİİLEN tüketilen web [m] = int r dt.

        ÖH D15 a2 (P2B4-02): ``grain_design.web_burnout_mm`` alanının kendi
        künyesi "the thickness actually consumed" diyordu ama radyal geometri
        formülünden geliyordu; end-burner'da 35,0 mm yazıp 500,06 mm
        tüketiyordu. Ölçülen tek doğru kaynak yanma hızının zaman
        integralidir — ``_web_utilization_percent`` de aynı integrali okur.
        """
        times = np.asarray((curve or {}).get('time', []), dtype=float)
        rates = np.asarray((curve or {}).get('burn_rate', []), dtype=float)
        if times.size < 2 or rates.size != times.size:
            return None
        return float(_trapezoid(rates, times))

    def _grain_geometry_key(self):
        """Ab(w) ve A_port(w) fonksiyonlarını TAM belirleyen anahtar.

        ``_burn_area_scan`` memo katmanı bunu kullanır. Anahtar,
        ``calculate_burn_area``/``_port_flow_area``'nın okuduğu HER alanı
        içerir; biri eksik kalırsa memo bayat sonuç döndürürdü.
        """
        key = (self.grain_type, self.D_chamber, self.D_core, self.L_grain)
        if self.grain_type == 'bates':
            key += (self._bates_segment_count(),
                    bool(getattr(self, 'inhibit_outer', True)),
                    bool(getattr(self, 'inhibit_front', False)),
                    bool(getattr(self, 'inhibit_rear', False)))
        elif self.grain_type == 'star':
            key += tuple(self._star_params())
        elif self.grain_type == 'finocyl':
            key += tuple(self._finocyl_params()[:4])
        elif self.grain_type == 'slotted':
            key += tuple(self._slotted_params()[:3])
        elif self.grain_type == 'wagon_wheel':
            _wp = self._wagon_params()
            key += (_wp['hole_count'], _wp['hole_diameter_m'],
                    _wp['pitch_diameter_m'])
        return key

    def _burn_area_scan(self):
        """Web aralığı boyunca (w, Ab(w), A_port(w), port_oranı) örneklemi.

        Boğaz boyutlandırması yanma boyunca ULAŞILAN en büyük gereksinimi
        aradığı için (bkz. _design_throat_area) Ab(w)'nin analitik kapalı
        formu değil, ÇÖZÜCÜNÜN KENDİ ``calculate_burn_area`` fonksiyonu
        örneklenir — ikinci bir yanma alanı tanımı üretilmez (star/finocyl/
        slotted/wagon_wheel'de zaten kapalı form yoktur, alan shapely ofseti
        ile bulunur).

        ÖRNEKLEME ADIMI VE GEREKÇESİ
        ----------------------------
        Kaba tarama web aralığını ``SOLID_KN_SCAN_SAMPLES`` eşit parçaya
        böler. Bu adım, ölçülen tepe konumlarını (D=100 mm gövdede
        wagon_wheel w≈4,8 mm, star w≈19,8 mm, finocyl w≈14,6 mm) rahatça
        ayırt eder. Tepe iki komşu örneğin arasına düşerse kaba adım tepeyi
        birkaç yüzde ıskalayabileceği için en büyük örneğin İKİ KOMŞUSU
        arasında ``SOLID_KN_REFINE_ROUNDS`` tur yerel keskinleştirme yapılır;
        her tur aralığı ``SOLID_KN_REFINE_SAMPLES`` parçaya böler, yani
        toplam çözünürlük kaba adımın ~1/100'üne iner.

        Keskinleştirme çapası Ab'nin tepesidir. Boğaz gereksinimi
        A_gerek(w) ∝ Ab(w)·r(Pc, w) olduğundan ve r yalnız erozif geometri
        çarpanıyla (port_oranı^-0.2) web'e bağlı olduğundan iki tepe
        pratikte çakışır; yine de A_gerek'in maksimumu keskinleştirilmiş
        örneklemin TAMAMI üzerinden alınır, dolayısıyla başka bir yerde
        oluşabilecek yapı kaba çözünürlükte de görülür.

        Örneklem GEOMETRİYE bağlıdır (yakıt/basınç değil), bu yüzden
        ``_grain_geometry_key`` ile anahtarlanıp örnek içinde memoize edilir:
        tek bir performans koşusunda ``_design_throat_area`` 13 kez çağrılır
        ve shapely'li tiplerde tarama 40-95 ms sürer.

        Dönüş: (web[m], burn_area[m²], port_area[m²], port_ratio) — hepsi
        artan web sırasında numpy dizileri.
        """
        key = self._grain_geometry_key()
        memo = getattr(self, '_burn_area_scan_memo', None)
        if memo is not None and memo[0] == key:
            return memo[1]

        w_max = self._max_web_thickness()
        if not np.isfinite(w_max) or w_max <= 0:
            bos = (np.zeros(0), np.zeros(0), np.zeros(0), np.zeros(0))
            self._burn_area_scan_memo = (key, bos)
            return bos

        webs = list(np.linspace(0.0, w_max, int(SOLID_KN_SCAN_SAMPLES)))

        def _ornekle(w_list):
            out = []
            for w in w_list:
                # Alan ve port AYNI web ile arka arkaya okunur: slotted
                # ofset poligonunun tek girdilik memo'su böyle tutar.
                out.append((float(w), float(self.calculate_burn_area(w)),
                            float(self._port_flow_area(w))))
            return out

        ornekler = _ornekle(webs)
        for _ in range(int(SOLID_KN_REFINE_ROUNDS)):
            alanlar = [o[1] for o in ornekler]
            i = int(np.argmax(alanlar))
            lo = ornekler[max(i - 1, 0)][0]
            hi = ornekler[min(i + 1, len(ornekler) - 1)][0]
            if hi <= lo:
                break
            ek = [w for w in np.linspace(lo, hi,
                                         int(SOLID_KN_REFINE_SAMPLES) + 1)]
            ornekler = sorted(ornekler + _ornekle(ek), key=lambda o: o[0])

        w_arr = np.array([o[0] for o in ornekler], dtype=float)
        ab_arr = np.array([o[1] for o in ornekler], dtype=float)
        ap_arr = np.array([o[2] for o in ornekler], dtype=float)
        # Port çapı oranı: erozif düzeltmenin geometri çarpanı bunu okur ve
        # itki eğrisinde AYNI ifadeyle kurulur ((D_core + 2w)/D_chamber).
        pr_arr = ((self.D_core + 2.0 * w_arr) / self.D_chamber
                  if self.D_chamber > 0 else np.ones_like(w_arr))
        sonuc = (w_arr, ab_arr, ap_arr, pr_arr)
        self._burn_area_scan_memo = (key, sonuc)
        return sonuc

    def _design_throat_area(self):
        """Tasarım noktası ETKİN boğaz alanı [m²] — TEK tanım noktası.

        Boğulmuş akış: mdot = Pc·A_t/c*  ;  kütle üretimi: mdot = rho_p·Ab·r
        => A_gerek(w) = rho_p · Ab(w) · r(Pc_tasarım, w) · c* / (Pc_tasarım·1e5)
        Kaynak: Sutton & Biblarz 9. baskı Böl. 12; NASA SP-8039 "Solid
        Rocket Motor Performance Analysis and Prediction" (Mayıs 1971)
        §3.1.1.1.1 eş. (44), s. 56. (KU-K2: künye eskiden "NASA SP-8089"
        idi — o, sıvı motor enjektör monografıdır.)

        BOĞAZ MAKSİMUM Kn'DE BOYUTLANDIRILIR (v2.6.27, A1-1)
        ----------------------------------------------------
        Eskiden A_t yalnız t=0 yanma alanına göre açılıyordu
        (``A_burn_0 = calculate_burn_area(0.0)``). Progresif taneciklerde
        Kn = Ab/At yanma boyunca BÜYÜDÜĞÜ için denge basıncı
        Pc = (Kn·a·rho_p·c*)^(1/(1-n)) kullanıcının girdiği tasarım
        basıncının çok üstüne tırmanıyordu. Bu ÖLÇÜLDÜ; referans vaka ve
        ölçülen aşımlar TEK YERDE, ``SOLID_THROAT_SIZING_REFERENCE``
        sözlüğünde durur (ÖH D16/kati a2, P2B3-06 — sayılar burada bir kez
        daha yazılmaz; iki kopya bayatladığı için bu kalem açılmıştı).
        Özetle: nötr yanan BATES'te aşım yüzde altıda bir mertebesinde
        kalırken ilerleyici taneciklerde tasarım basıncının iki katına
        yaklaşıyordu.

        Yani kasa, yalıtım ve boğaz "40 bar" için boyutlandırılırken motor
        onun iki katına çıkabiliyordu. Artık boğaz, yanma boyunca ULAŞILAN
        EN BÜYÜK gereksinime göre açılır:

            A_t = maks_w  A_gerek(w)

        Bu, kullanıcının girdiği kamara basıncını eğrinin TAVANI yapar ve
        bunu tarama çözünürlüğünden bağımsız olarak GARANTİ EDER: verilen
        bir webte denge basıncı Pc = rho_p·Ab·r(Pc)·c*/(A_t·1e5) sabit
        noktasıdır; r ∝ Pc^n ve n < 1 olduğundan sağ taraf Pc'de içbükey
        artandır, dolayısıyla A_t ≥ A_gerek(w) ise o webin sabit noktası
        tasarım basıncının ALTINDA kalır. (Boğaz erozyonu açıkken A_t koşu
        boyunca yalnız BÜYÜR, yani tavan yine korunur.)

        BEDELİ AÇIKÇA SÖYLENİR: boğaz büyüdüğü için itki düşer. Bu bir kayıp
        değil, motorun gerçekten hangi basınçta çalıştığının düzeltilmesidir;
        sonuç sözlüğü boyutlandırmanın hangi ölçüte göre yapıldığını
        ``throat_sizing`` bloğunda beyan eder.

        Yanma hızı r, ÇÖZÜCÜNÜN kullandığı ``burn_rate`` ile hesaplanır: bu
        parçalı (plateau/mesa) yasayı, başlangıç sıcaklığı düzeltmesini ve
        erozif yanma katkısını içerir. Erozif düzeltme port kütle akısına, akı
        ise yanma hızına bağlı olduğu için her örnekte küçük bir sabit-nokta
        iterasyonu koşulur (öz-tutarlı tasarım noktası). Erozyon web'e bağlı
        olduğundan (küçük portta güçlü) tepe, salt Ab tepesinden kayabilir;
        maksimum bu yüzden Ab üzerinden değil A_gerek üzerinden alınır.

        v2.6.26 (Y1): bu blok ``calculate_thrust_curve`` içinde gömülüydü ve
        ``_estimate_throat_diameter`` İKİNCİ, erozif-düzeltmesiz bir boğaz
        hesaplıyordu. Aynı motor için çözücü 17.961 mm, CAD/3D katmanı
        17.604 mm raporluyordu (fark 0.357 mm) — üstelik aynı CAD bloğu
        ``throat_tolerance: ±0.01 mm`` yazıyordu, yani beyan edilen toleransın
        35 katı. İmalata giden çap artık çözücünün çapıdır.

        DONANIM SABİTLENMESİ (``pin_throat_area``, T19 / 2026-08-03)
        ------------------------------------------------------------
        Boğaz alanı SABİTLENMİŞSE bu metot yeniden boyutlandırma YAPMAZ,
        sabitlenen alanı döndürür. Bunun tek meşru kullanıcısı üretim
        toleransı Monte Carlo'sudur: orada donanım (işlenmiş boğaz) tektir,
        değişen şey yakıt partisidir. Sabitleme olmadan her örneklem kendi
        yakıtına göre YENİ bir boğaz açıyor ve oda basıncı yapısal olarak
        tasarım Pc'sine kilitleniyordu (ölçüldü: 300 koşuda tepe basıncı
        σ = 0,0457 bar, CV %0,11 — itki CV'si %3,9 iken).

        Dönüş: (A_t_etkin [m²], tasarım noktası port kütle akısı [kg/m²s]).
        """
        detay = self._design_throat_detail()
        return detay['throat_area_m2'], detay['design_mass_flux']

    def _design_throat_detail(self):
        """``_design_throat_area``ın tam çıktısı (boyutlandırma künyesiyle).

        Alanlar: throat_area_m2, design_mass_flux, design_web_m,
        design_burn_area_m2, initial_burn_area_m2, burn_area_ratio,
        pinned, samples.

        MEMO: tek bir ``calculate_performance`` koşusunda bu metot 13 kez
        çağrılır ve her çağrı web aralığını baştan tarar (ölçüldü: taramasız
        koşu 0,10 s → taramalı 0,18 s bates, 0,18 s → 0,34 s wagon_wheel).
        Sonuç, hesabın OKUDUĞU her girdiyle anahtarlanır — geometri
        (_grain_geometry_key), tasarım basıncı, yakıt yoğunluğu/c*, yanma
        hızı yasasının bütün alanları ve boğaz sabitlemesi. Monte Carlo bu
        alanları örneklem başına değiştirdiği için anahtar orada zaten
        ıskalar; bayat sonuç dönmez.
        """
        memo_key = self._grain_geometry_key() + (
            float(self.P_c), float(self.rho_p), float(self.c_star),
            float(self.a), float(self.n), float(self.temp_ref),
            float(self.burn_rate_temp_coeff),
            float(getattr(self, 'initial_grain_temperature', self.temp_ref)),
            float(getattr(self, 'erosive_burning_coeff', 0.0)),
            float(getattr(self, 'erosive_exponent', 0.8)),
            getattr(self, 'burn_rate_law_key', None),
            getattr(self, '_pinned_throat_area_m2', None),
        )
        memo = getattr(self, '_design_throat_memo', None)
        if memo is not None and memo[0] == memo_key:
            return memo[1]

        detay = self._design_throat_detail_uncached()
        self._design_throat_memo = (memo_key, detay)
        return detay

    def _design_throat_detail_uncached(self):
        """``_design_throat_detail``ın gerçek hesabı (memo katmanı olmadan)."""
        webs, areas, ports, ratios = self._burn_area_scan()
        bos = {
            'throat_area_m2': 0.0, 'design_mass_flux': 0.0,
            'design_web_m': 0.0, 'design_burn_area_m2': 0.0,
            'initial_burn_area_m2': 0.0, 'burn_area_ratio': 0.0,
            'pinned': False, 'samples': int(len(webs)),
        }
        if webs.size == 0 or float(np.max(areas)) <= 0.0:
            return bos

        # Sıcaklık referansı çözücüyle AYNI: burn_rate'in temperature argümanı
        # exp(sigma*(T - temp_ref)) çarpanıdır ve başlangıç sıcaklığı
        # düzeltmesi self.a içinde ZATEN uygulanmıştır (çifte sayım yasak).
        temp = self.temp_ref
        flux_saved = getattr(self, 'mass_flux', 0.0)
        en_iyi_alan = -1.0
        en_iyi_flux = 0.0
        en_iyi_i = 0
        try:
            for i in range(webs.size):
                A_burn = float(areas[i])
                if A_burn <= 0.0:
                    continue
                A_port = float(ports[i])
                port_ratio = float(ratios[i])
                self.mass_flux = 0.0
                r_design = self.burn_rate(self.P_c, temp, port_ratio)
                flux_i = 0.0
                for _ in range(25):
                    m_dot_i = self.rho_p * A_burn * r_design
                    flux_i = m_dot_i / A_port if A_port > 0 else 0.0
                    self.mass_flux = flux_i
                    r_new = self.burn_rate(self.P_c, temp, port_ratio)
                    if abs(r_new - r_design) < 1e-12:
                        r_design = r_new
                        break
                    r_design = r_new
                m_dot_i = self.rho_p * A_burn * r_design
                A_gerek = m_dot_i * self.c_star / (self.P_c * 1e5)  # m²
                if A_gerek > en_iyi_alan:
                    en_iyi_alan = A_gerek
                    en_iyi_flux = flux_i
                    en_iyi_i = i
        finally:
            # Yan etki bırakma: akı, çağıran neredeyse orada kalır.
            self.mass_flux = flux_saved

        if en_iyi_alan <= 0.0:
            return bos

        pinned = getattr(self, '_pinned_throat_area_m2', None)
        # Donanım sabit: boğaz yakıt partisine göre yeniden açılmaz.
        A_t = float(pinned) if pinned is not None else float(en_iyi_alan)
        ab0 = float(areas[0])
        return {
            'throat_area_m2': float(A_t),
            'design_mass_flux': float(en_iyi_flux),
            'design_web_m': float(webs[en_iyi_i]),
            'design_burn_area_m2': float(areas[en_iyi_i]),
            'initial_burn_area_m2': ab0,
            'burn_area_ratio': (float(areas[en_iyi_i]) / ab0
                                if ab0 > 0 else 0.0),
            'pinned': pinned is not None,
            'samples': int(webs.size),
        }

    def _throat_sizing_report(self, curve=None):
        """Boğazın HANGİ ölçüte göre açıldığının beyanı (sonuç sözlüğü).

        v2.6.27 (A1-1): boyutlandırma ölçütü değiştiği için kullanıcı
        değişikliği GÖREBİLMELİDİR — itki, aynı geometride eskisinden düşük
        çıkar ve bunun sebebi burada yazılıdır. Ölçülen tepe basıncı verilen
        eğriden okunur; eğri verilmezse basınç alanları None kalır (sayı
        uydurulmaz).
        """
        detay = self._design_throat_detail()
        # ÖH D16/kati a2 (P2B3-06): referans vakanın yüzdeleri düzyazının
        # İÇİNE elle yazılıyordu ve bayatlamıştı (BATES '+32%', ölçülen
        # +%0,60 — 53 kat). Metin artık TEK KAYNAKTAN kurulur ve aynı kayıt
        # yapısal 'reference_case' alanı olarak da yayımlanır; böylece
        # beyan ⟷ ölçüm çaprazı makinece kurulabilir (bekçi:
        # tests/test_d16_kati_a2.py).
        _ref = SOLID_THROAT_SIZING_REFERENCE
        _ref_yuzde = _ref['peak_over_design_percent']
        _ref_sira = ('bates', 'slotted', 'star', 'finocyl', 'wagon_wheel')
        _ref_metin = ', '.join(
            '+{:.1f}% {}'.format(_ref_yuzde[t],
                                 'BATES' if t == 'bates' else t.replace('_', ' '))
            for t in _ref_sira if t in _ref_yuzde)
        rapor = {
            'basis': 'max burn area (Kn_max)',
            'design_web_m': detay['design_web_m'],
            'design_burn_area_m2': detay['design_burn_area_m2'],
            'initial_burn_area_m2': detay['initial_burn_area_m2'],
            'burn_area_ratio_max_over_initial': detay['burn_area_ratio'],
            'scan_samples': detay['samples'],
            'throat_area_pinned': detay['pinned'],
            'design_chamber_pressure_bar': float(self.P_c),
            'peak_chamber_pressure_bar': None,
            'peak_over_design': None,
            'basis_text': (
                'The throat is sized at the LARGEST throat area the burn ever '
                'requires, A_t = max_w rho_p*Ab(w)*r(Pc,w)*c*/(Pc*1e5), not at '
                'the t = 0 burning surface. The burning surface of a '
                'progressive grain grows during the burn, so sizing on Ab(0) '
                'let the equilibrium pressure climb above the chamber '
                'pressure the user entered (measured on this repo for a '
                '{d:.0f} mm chamber, {c:.0f} mm core, {l:.0f} mm {p} grain at '
                '{pc:.0f} bar: {tab}; those numbers describe THAT reference '
                'case, not your motor - '
                "your motor's own peak is the peak_over_design field beside "
                'this text). With the '
                'peak-Kn criterion the entered chamber pressure is the '
                'CEILING of the pressure curve. The throat is therefore '
                'larger and the thrust lower than the previous release '
                'reported for the same geometry; that is the correction, not '
                'a loss. Sources: Sutton & Biblarz, Rocket Propulsion '
                'Elements 9th ed., Ch. 12; NASA SP-8039, eq. (44), '
                'p. 56.').format(
                    d=_ref['chamber_diameter_mm'],
                    c=_ref['core_diameter_mm'],
                    l=_ref['grain_length_mm'],
                    p=_ref['propellant_type'].upper(),
                    pc=_ref['chamber_pressure_bar'],
                    tab=_ref_metin),
            # Beyanın YAPISAL ikizi: aynı kayıt, düzyazıdan ayrıştırmadan
            # okunabilsin diye. basis_text bu sözlükten kurulur, yani ikisi
            # tanım gereği aynı sayıyı taşır.
            'reference_case': {
                'propellant_type': _ref['propellant_type'],
                'chamber_diameter_mm': _ref['chamber_diameter_mm'],
                'core_diameter_mm': _ref['core_diameter_mm'],
                'grain_length_mm': _ref['grain_length_mm'],
                'chamber_pressure_bar': _ref['chamber_pressure_bar'],
                'old_criterion_peak_over_design_percent': dict(_ref_yuzde),
                'old_criterion_peak_over_initial_thrust': dict(
                    _ref['peak_over_initial_thrust']),
                'measured_on': _ref['measured_on'],
                'basis': (
                    'Peak chamber pressure of the SAME reference motor when '
                    'the throat is sized by the old t = 0 criterion '
                    '(A_t = rho_p*Ab(0)*r(Pc)*c*/(Pc*1e5)), expressed as the '
                    'percentage above the entered chamber pressure. These are '
                    'reference-case numbers, not a property of your motor.'),
            },
        }
        if curve is not None:
            basinc = np.asarray(curve.get('pressure', []), dtype=float)
            if basinc.size:
                tepe = float(np.nanmax(basinc))
                rapor['peak_chamber_pressure_bar'] = tepe
                rapor['peak_over_design'] = (float(tepe / self.P_c)
                                             if self.P_c > 0 else None)

        # ------------------------------------------------------------------
        # ÖH D15 a2 (P2B4-03 / P2B3-07): GEOMETRİK ⟷ ETKİN boğaz ayrımı bu
        # blokta HİÇ beyan edilmiyordu (ölçüldü: 'geometric' / 'effective' /
        # 'discharge' geçen anahtar sayısı 0). İki alan aynı motorda farklıdır
        # ve hangi sayının neyi ürettiği ancak burada okunabilir:
        #   * A_t_etkin  -> basıncı ve itkiyi üretir, Kn'in paydasıdır,
        #                   epsilon = A_e/A_t_etkin'in paydasıdır;
        #   * A_t_geom   -> İMAL EDİLECEK boğaz (A_etkin / Cd), CAD çapı.
        # Cd = 1'de ikisi özdeştir. UI Cd alanını her istekte 0,98 gönderir.
        # ------------------------------------------------------------------
        cd = float(getattr(self, 'discharge_coeff', 1.0) or 1.0)
        a_eff = None
        if curve is not None:
            a_eff = curve.get('throat_area')
        if a_eff is None or not np.isfinite(float(a_eff)) or float(a_eff) <= 0:
            a_eff, _flux = self._design_throat_area()
        a_eff = float(a_eff)
        a_geom = a_eff / cd if 0.0 < cd < 1.0 else a_eff
        eps = self._estimate_expansion_ratio()
        rapor.update({
            'discharge_coefficient': cd,
            'throat_area_effective_m2': a_eff,
            'throat_area_geometric_m2': a_geom,
            'throat_diameter_effective_mm': 2000.0 * float(
                np.sqrt(a_eff / np.pi)),
            'throat_diameter_geometric_mm': 2000.0 * float(
                np.sqrt(a_geom / np.pi)),
            'expansion_ratio_effective': float(eps),
            'expansion_ratio_geometric': (float(eps * a_eff / a_geom)
                                          if a_geom > 0 else None),
            'throat_area_basis': (
                'throat_area_effective_m2 is the flow (sonic) area: the '
                'pressure history P = mdot*c*/(A_t*1e5), the thrust '
                'F = CF*Pc*1e5*A_t, the published Kn (A_burn/A_t) and the '
                'published expansion ratio (A_exit/A_t) all use THIS area. '
                'throat_area_geometric_m2 = effective / discharge_coefficient '
                'is the area to MACHINE. The exit diameter is built from the '
                'effective area, so the nozzle you machine really does have '
                'the published expansion_ratio_effective; '
                'expansion_ratio_geometric is the bare diameter ratio of the '
                'drawn part (A_exit / A_throat_geometric).'),
        })
        return rapor

    def pin_throat_area(self, area_m2):
        """Boğaz alanını SABİTLE — donanım tektir, yakıt partisi değişkendir.

        Üretim toleransı Monte Carlo'su için eklendi (T19, 2026-08-03).
        Normal (tasarım) akışta ÇAĞRILMAZ; çağrılmadığında davranış
        bit-özdeş korunur çünkü ``_design_throat_area`` yalnız bu öznitelik
        ``None`` değilken devreye girer.

        area_m2: etkin (akış) boğaz alanı [m²]. None → sabitlemeyi kaldırır.
        """
        if area_m2 is None:
            self._pinned_throat_area_m2 = None
            return
        a = float(area_m2)
        if not np.isfinite(a) or a <= 0.0:
            raise ValueError(
                'pin_throat_area: alan pozitif ve sonlu olmalı; '
                f'verilen {area_m2!r}')
        self._pinned_throat_area_m2 = a

    def pin_burn_rate_lot(self, scale=1.0, exponent_shift=0.0):
        """PARÇALI yanma yasasına üretim partisi saçılımı uygula.

        ÖH D15 a2 (P2B3-02). ``run_monte_carlo`` her örnekte ``burn_rate_a``
        ve ``burn_rate_n``'i bozup yeni bir motor kuruyordu, ama parçalı
        rejim yasası olan yakıtlarda (``kndx``, ``knsb`` — ``BURN_RATE_LAWS``
        anahtarlarının tamamı) ``burn_rate()`` taban hızı yasadan okuduğu için
        ``self.a`` / ``self.n`` hesaba HİÇ girmiyordu. ÖLÇÜLDÜ (D=100 mm,
        çekirdek 30, L=500, 40 bar):

          yakıt   yasa    r(40 bar)      a x1,30 sonrası   n +0,20 sonrası
          apcp    yok     8,1225 mm/s    10,5593 mm/s      16,9865 mm/s
          kndx    kndx    9,9666 mm/s     9,9666 mm/s       9,9666 mm/s
          knsb    knsb    8,2025 mm/s     8,2025 mm/s       8,2025 mm/s

        Sonuç: saçılım yalnız yoğunluk ve c* ile kalıyordu — yanma süresi
        CV'si %5,549 (apcp) ⟷ %1,416 (kndx), yani **3,92 kat dar** — ama aynı
        yanıt iki yakıtta da harfi harfine "1σ: a ±%3, n ±0,005" yazıyordu.
        Koşulmayan bir saçılımın künyesi kullanıcıya üretim riskini
        OLDUĞUNDAN DAR gösteriyordu, üstelik tam da hedef kitlenin şeker
        yakıtlarında.

        Tolerans burada tek üslü yolla ÖZDEŞ biçimde uygulanır:
        ``a(1+eps)*P^(n+d) = (a*P^n)*(1+eps)*P^d``, yani taban hız
        ``scale * P^exponent_shift`` ile çarpılır. Normal (tasarım) akışta
        ÇAĞRILMAZ; çağrılmadığında çarpan tam 1.0'dır ve davranış bit-özdeştir.
        """
        s = float(scale)
        d = float(exponent_shift)
        if not np.isfinite(s) or s <= 0.0:
            raise ValueError(
                f'pin_burn_rate_lot: scale pozitif ve sonlu olmalı; {scale!r}')
        if not np.isfinite(d):
            raise ValueError(
                'pin_burn_rate_lot: exponent_shift sonlu olmalı; '
                f'{exponent_shift!r}')
        self._burn_rate_lot_scale = s
        self._burn_rate_lot_exponent_shift = d

    def _estimate_throat_diameter(self):
        """İmal edilecek (GEOMETRİK) tasarım boğaz çapı [m].

        Alan ``_design_throat_area`` ile çözücüyle AYNI kaynaktan gelir;
        burada yalnız boğaz akış katsayısı uygulanır: Cd verildiğinde
        geometrik boğaz etkin boğazdan büyüktür (A_geom = A_etkin / Cd).
        Basınç/itki hâlâ etkin alandan çözülür; Cd verilmezse
        (varsayılan 1.0) davranış değişmez.

        ÖH D26 a2 (OH-D25-10) — SESSİZ KELEPÇE KALDIRILDI. Burada
        ``d_throat = max(0.001, min(d_throat, 0.5))`` duruyordu. Bu kelepçe
        ``throat_exceeds_case`` kapısını FAIL-OPEN yapıyordu, çünkü aynı
        yanıtta üç kapıdan ikisi (D20 uyarısı ve ``cad_design`` bloğu) bu
        kelepçelenmiş çapı, üçüncüsü (``nozzle_angles``, itki eğrisinin
        ``throat_area``sından) kelepçesiz çapı okuyordu. ÖLÇÜLDÜ
        (docs/scofield/raw/OH/D26/kati/a2/once.json; APCP bates, Cd = 1):

          gövde                       ham boğaz   kelepçeli   kapılar
          D = 700 mm, L = 5000, c 40, Pc 5 bar   727,05 mm   500,00 mm
              -> uyarı kapısı false, cad kapısı false,
                 performans kapısı TRUE            (kapılar ayrıştı)
          D = 900 mm, L = 6000, c 60, Pc 5 bar   798,21 mm   500,00 mm

        Yani gövdesinden BÜYÜK bir boğaz "gövdeye sığıyor" diye
        raporlanıyor, yakınsak koni boyu hesaplanıp yayımlanıyordu. Kelepçe
        ayrıca ÇİZİLEN boğaz çapını da (cad_design.nozzle_design.
        throat_diameter) sessizce 500 mm'ye indiriyordu: yayımlanan sayı
        çözücünün sayısı DEĞİLDİ. Sayısal aralık denetimi kaldırılmadı, yeri
        değişti: ``calculate_performance`` zaten ham çapı
        ``warn.solid.throat_diameter_out_of_range`` ile ADIYLA bildiriyor
        (1 mm - 500 mm), yani kullanıcı aynı bilgiyi kelepçe olmadan da
        alıyor — sessiz düzeltme yerine adlandırılmış uyarı (Doktrin 1).
        """
        A_t, _flux = self._design_throat_area()
        if not (np.isfinite(A_t) and A_t > 0.0):
            # ÖH D27 a2 (OH-D26-15) — SESSİZ 15 mm YEDEĞİ SÖKÜLDÜ.
            # Burada ``if A_t <= 0: return 0.015  # fallback 15mm``
            # duruyordu. ``_design_throat_area`` SIFIR döndürdüğünde
            # çözücü "bu geometri/yakıtla boğazı boyutlandıramadım" demiş
            # olur (``_design_throat_detail_uncached`` iki yerde ``bos``
            # döner: web taraması boş, ya da hiçbir örnekte A_gerek > 0).
            # O hükmün üstüne 15 mm yazmak ÇÖZÜLMEMİŞ bir tasarımı
            # çözülmüş gibi gösterir.
            #
            # ÖLÇÜLDÜ (docs/scofield/raw/OH/D27/kati/a2/once.json, K2;
            # taban 709a235e): A_t = 0 üreten ÜÇ bağımsız durumun
            # (c* = 0, rho_p = 0, boş web taraması) ÜÇÜNDE de metot
            # istisnasız 0,015 m döndürüyordu. Yayımlanan boğaz alanı
            # pi*(0,015/2)^2 = 1,7671e-4 m², çözücünün sayısı ise 0 —
            # yani yayımlanan sayı çözücünün sayısı DEĞİLDİ. Bu uydurma
            # çapı bu dosyada 11 çağrı yeri okuyor (K2c), aralarında
            # ``cad_design.nozzle_design.throat_diameter`` (imalata giden
            # çap) ve ``_throat_exceeds_case`` kapısı da vardır.
            #
            # OH-D25-10'un (sessiz 1-500 mm kelepçesi) KARDEŞİDİR: aynı
            # metot, aynı hata sınıfı — çözücünün hükmünü sessizce
            # değiştirmek. Doktrin 1: çözülemeyen girdi ADIYLA reddedilir.
            raise SolidGeometryError(
                'throat_area could not be sized for this design: the burn '
                'area scan produced no positive required throat area, so no '
                'throat diameter is published and no fallback value is '
                'invented. Check the grain geometry, the propellant density '
                'and the characteristic velocity.',
                {'field': 'throat_area', 'reason': 'throat_not_sizable',
                 'value': float(A_t), 'accepted_range': ['>0', None],
                 'unit': 'm^2', 'motor_form': 'solid'})
        cd = getattr(self, 'discharge_coeff', 1.0)
        if 0.0 < cd < 1.0:
            A_t = A_t / cd
        return 2 * np.sqrt(A_t / np.pi)

    def _throat_exceeds_case(self, d_throat_m=None):
        """``throat_exceeds_case`` ÖLÇÜTÜNÜN tek tanım noktası (ÖH D26 a2).

        Kural üç yerde ayrı ayrı yazılıydı (D20 uyarısı, ``cad_design``
        bloğu, ``nozzle_angles``); OH-D25-10 bu üç kapının aynı ölçütü aynı
        boğaz sayısıyla uygulamasını ister. ``d_throat_m`` verilmezse
        boğaz ``_estimate_throat_diameter``dan okunur — itki eğrisinin
        ``throat_area``sıyla aynı ``_design_throat_area`` kaynağıdır.
        """
        if d_throat_m is None:
            # ÖH D27 a2 (OH-D26-15): boğaz BOYUTLANDIRILAMADIYSA bu kapının
            # dürüst cevabı "sığıyor" DEĞİLDİR — hüküm verilemez. Burada
            # ``except Exception: return False`` duruyordu ve kapıyı
            # FAIL-OPEN yapıyordu: 15 mm'lik sessiz yedek sökülünce ret
            # bu satırda yutulup yine "gövdeye sığıyor" hükmüne dönüşecekti,
            # yani onarım kendi tüketicisinde geri alınmış olurdu (D26
            # dersi: kanal var, kapı yok). Adlandırılmış ret YUKARI GEÇER;
            # boğazı açıkça verilen çağrı yolu (NaN dâhil) etkilenmez ve
            # başka istisna türleri eski davranışta kalır.
            try:
                d_throat_m = float(self._estimate_throat_diameter())
            except SolidGeometryError:
                raise
            except Exception:
                return False
        d = float(d_throat_m)
        D = float(self.D_chamber)
        if not (np.isfinite(d) and np.isfinite(D) and D > 0):
            return False
        return bool(d >= D)

    def _design_exit_diameter(self):
        """İmal edilecek lüle ÇIKIŞ çapı [m] — TEK tanım noktası.

        ÖH D15 a2 (P2B3-07). Bu kural depoda DÖRT yerde ayrı ayrı yazılıydı
        ve dördü de aynı hatayı yapıyordu: ``d_exit = d_throat * sqrt(eps)``,
        yani çıkış çapını Cd ile ŞİŞİRİLMİŞ GEOMETRİK boğazdan türetiyordu.
        Oysa ``eps = A_e / A_t_ETKİN`` olarak tanımlıdır (itki katsayısı onu
        kullanır) ve çıkışta vena contracta yoktur. Sonuç: çizilen
        (d_boğaz, d_çıkış) çifti imal edilirse gazın gördüğü genişleme oranı
        yayımlanan ``expansion_ratio`` DEĞİLDİ. ÖLÇÜLDÜ (APCP 100/30/500 mm,
        40 bar):

          Cd     yayımlanan eps   çizilen lülenin gerçek eps    sapma
          1,00       5,9317              5,9317               %0,00
          0,98       5,9317              6,0528              +%2,04   <- UI
          0,90       5,9317              6,5908             +%11,11
          0,70       5,9317              8,4739             +%42,86

        ``discharge_coeff`` formun HER isteğinde 0,98 olarak gönderiliyor,
        yani Cd = 1 hâli üründe hiç oluşmuyordu ve sapma varsayılan koşuda da
        vardı. Doğru inşa: ``A_e = eps * A_t_etkin`` -> çıkış çapı Cd'den
        BAĞIMSIZDIR ve Cd = 1 hâlindeki değerle bit-aynı kalır.
        """
        A_t, _flux = self._design_throat_area()
        if A_t <= 0:
            return self._estimate_throat_diameter() * np.sqrt(
                self._estimate_expansion_ratio())
        A_e = self._estimate_expansion_ratio() * A_t
        return float(2 * np.sqrt(A_e / np.pi))

    def _expansion_ratio_from_pressure_ratio(self, Pe_Pc):
        """Tam izentropik alan oranı: Pe/Pc basınç oranından epsilon = A_e/A_t.

        Sutton & Biblarz, "Rocket Propulsion Elements" 9. baskı, Denk. 3-25/3-26:
        M_e = sqrt(2/(gamma-1) * ((Pe/Pc)^(-(gamma-1)/gamma) - 1))
        A_e/A_t = (1/M_e) * [(2/(gamma+1)) * (1 + (gamma-1)/2 * M_e^2)]^((gamma+1)/(2*(gamma-1)))

        Kelepçe uygulanmaz; çağıran taraf fiziksel sınırları kendisi koyar.
        """
        gamma = self._nozzle_gamma()
        Pe_Pc = min(max(Pe_Pc, 1e-9), 0.999999)

        M_e_sq = (2 / (gamma - 1)) * (Pe_Pc ** (-(gamma - 1) / gamma) - 1)
        if M_e_sq <= 1.0:
            return 1.0  # Genişleme yok (Pe/Pc çok yüksek)
        M_e = np.sqrt(M_e_sq)

        term = 1 + (gamma - 1) / 2 * M_e ** 2
        exp_ar = (gamma + 1) / (2 * (gamma - 1))
        return (1 / M_e) * ((2 / (gamma + 1)) * term) ** exp_ar

    def _estimate_expansion_ratio(self):
        """Tasarım ORTAM basıncında optimum genişleme oranı (ε = A_e/A_t).

        Solves the isentropic exit-pressure relation iteratively:
        P_e/P_c = [1 + (gamma-1)/2 * M_e^2]^(-gamma/(gamma-1))
        A_e/A_t = (1/M_e) * [(2/(gamma+1)) * (1 + (gamma-1)/2 * M_e^2)]^((gamma+1)/(2*(gamma-1)))

        P_e = P_ortam alınıp M_e, ondan ε çözülür. ÜST kelepçe YOKTUR
        (ÖH D17 / P2B3-09; eski [2.5, 25] bandının üst ucu 25 km'de
        optimumu 4,12 kat, 50 km'de 71 kat kırpıyordu ve sessizdi). Alt
        sınır SOLID_MIN_DESIGN_EXPANSION_RATIO'dur ve bağlandığında
        ``_expansion_ratio_bound`` ile BEYAN edilir.

        FİZİK DENETİMİ DÜZELTMESİ (F174, 2026-07-25): ortam basıncı burada
        1.01325 bar olarak SABİT KODLUYDU, oysa _thrust_coefficient ve
        _calculate_theoretical_isp aynı örnekte self.ambient_pressure_bar
        okuyor. Kullanıcı test_altitude / atm_pressure girdiğinde itki 5000
        m'ye göre (CF = 1.5842) hesaplanıyor ama imal edilecek/CAD'e giden ε
        deniz seviyesinde (5.93) kalıyordu — yani rapor edilen nozul, itkiyi
        üreten nozul DEĞİLDİ. Artık tek kaynak: self.ambient_pressure_bar.
        (Deniz seviyesinde, yani varsayılanda, sonuç birebir aynıdır.)

        V301/N-CEA-2 (K2): bileşimi bilinen iticide ε, NASA CEA'nın kayan
        denge (yoğun faz dahil) genişlemesinin P_e = P_ortam alan oranıdır;
        γ_n bu oranı tek-γ bağıntısıyla aynen üretir (kök), sonuç CEA'nın
        sayısıyla değiştirilir. Kullanıcı ε girdisi katı çözücüde yoktur
        (``unwired_inputs`` 'computed_by_solver').
        """
        gamma = self._nozzle_gamma()
        P_atm = float(getattr(self, 'ambient_pressure_bar',
                              SEA_LEVEL_PRESSURE_BAR))  # bar
        # İtki eğrisi her adımda çağırır; ε yalnız (gamma, Pc, P_ortam)
        # fonksiyonudur ve koşu boyunca sabittir → örnek üstünde önbelleklenir.
        cache_key = (round(gamma, 12), round(float(self.P_c), 12),
                     round(P_atm, 12))
        cached = getattr(self, '_epsilon_cache', None)
        if cached is not None and cached[0] == cache_key:
            return cached[1]
        Pe_Pc = P_atm / self.P_c

        if Pe_Pc >= 1.0:
            # Ortam basıncı kamara basıncından küçük değilse süpersonik
            # genişleme YOKTUR; alt sınır BEYANLA uygulanır (ÖH D17 /
            # P2B3-09 — eski satır çıplak `return 2.5` idi).
            self._expansion_ratio_bound = {
                'bound': 'no_supersonic_expansion',
                'unbounded_value': None,
                'applied_value': float(SOLID_MIN_DESIGN_EXPANSION_RATIO),
                'basis': (
                    f'P_ambient ({P_atm:.5g} bar) is not below the chamber '
                    f'pressure ({self.P_c:.4g} bar), so no supersonic '
                    f'expansion exists and no optimum area ratio can be '
                    f'solved; the minimum design expansion ratio '
                    f'{SOLID_MIN_DESIGN_EXPANSION_RATIO:.2f} was applied '
                    f'and is reported here.'),
            }
            return float(SOLID_MIN_DESIGN_EXPANSION_RATIO)

        # Solve for exit Mach number from pressure ratio
        # P_e/P_c = [1 + (g-1)/2 * M^2]^(-g/(g-1))
        # => M_e = sqrt(2/(g-1) * ((P_e/P_c)^(-(g-1)/g) - 1))
        exponent = -(gamma - 1) / gamma
        M_e_sq = (2 / (gamma - 1)) * (Pe_Pc ** exponent - 1)
        if M_e_sq <= 1.0:
            self._expansion_ratio_bound = {
                'bound': 'subsonic_exit',
                'unbounded_value': None,
                'applied_value': float(SOLID_MIN_DESIGN_EXPANSION_RATIO),
                'basis': (
                    f'The isentropic exit Mach number solved from '
                    f'P_e/P_c = {Pe_Pc:.6g} is not supersonic, so an '
                    f'optimum area ratio does not exist; the minimum design '
                    f'expansion ratio {SOLID_MIN_DESIGN_EXPANSION_RATIO:.2f} '
                    f'was applied and is reported here.'),
            }
            return float(SOLID_MIN_DESIGN_EXPANSION_RATIO)
        M_e = np.sqrt(M_e_sq)

        # Area ratio from Mach number
        term = 1 + (gamma - 1) / 2 * M_e ** 2
        exp_ar = (gamma + 1) / (2 * (gamma - 1))
        epsilon = (1 / M_e) * ((2 / (gamma + 1)) * term) ** exp_ar
        _lule = self._cea_nozzle_state()
        if _lule:
            epsilon = float(_lule['expansion_ratio'])

        # ÖH D17 (P2B3-09): burada `epsilon = max(2.5, min(epsilon, 25.0))`
        # yazıyordu. ÜST kelepçe (25) hiçbir fizikten türemiyordu ve
        # SESSİZDİ. ÖLÇÜLDÜ (docs/scofield/raw/OH/D17/kati/a1/once.json;
        # APCP, Pc = 40 bar):
        #
        #   ortam                optimum ε   yayımlanan ε   oran
        #   deniz seviyesi          5,932        5,932      1,00
        #   10 km                  16,355       16,355      1,00
        #   25 km                 103,060       25,000      4,12
        #   50 km                1775,379       25,000     71,02
        #   deniz sv., Pc=200 bar  20,086       20,086      1,00
        #
        # ve hiçbir uyarı/künye alanı üretilmiyordu. Kelepçenin gerekçesi
        # "daha büyük ε'da akış ayrılması" idi; oysa BU ε tanımı gereği
        # P_e = P_ortam veren tam genişlemedir, yani tasarım ortamında
        # ayrılma ölçütünün (Summerfield: P_e < 0,4·P_a) tam olarak
        # dışındadır — üst kelepçe kendi gerekçesini yanlışlıyordu.
        # Ayrılma hükmü zaten çözücünün kendi CF durumunda (cf_state,
        # 'separated') irtifadan bağımsız olarak veriliyor. Üst kelepçe
        # KALDIRILDI; alt sınır adlandırılmış tek sabite bağlandı ve
        # bağlandığında BEYAN edilir.
        alt_sinir = float(SOLID_MIN_DESIGN_EXPANSION_RATIO)
        if epsilon < alt_sinir:
            self._expansion_ratio_bound = {
                'bound': 'minimum',
                'unbounded_value': float(epsilon),
                'applied_value': alt_sinir,
                'basis': (
                    f'The fully expanded (P_e = P_ambient) area ratio at '
                    f'Pc = {self.P_c:.4g} bar and P_ambient = {P_atm:.5g} '
                    f'bar is {epsilon:.4f}, below the minimum design '
                    f'expansion ratio {alt_sinir:.2f} '
                    f'(SOLID_MIN_DESIGN_EXPANSION_RATIO); the floor was '
                    f'applied and is reported here rather than silently '
                    f'substituted.'),
            }
            epsilon = alt_sinir
        else:
            self._expansion_ratio_bound = None
        self._epsilon_cache = (cache_key, float(epsilon))
        return epsilon

    def _nozzle_half_angles(self):
        """Konik nozul yarı açıları (yakınsak, ıraksak) [derece] — TEK kaynak.

        CODEX BULGUSU DÜZELTMESİ (2026-07-19, satır ~3741): geometri her
        koşuda SABİT 30/15 derece ile üretiliyordu; formdaki convergent_angle
        / divergent_angle alanları _apply_overrides tarafından okunuyor ama
        HİÇBİR uzunluğa girmiyordu. Kullanıcı açıyı değiştirdiğinde nozul
        boyu ve dışa aktarılan geometri aynı kalıyor, üstelik sonuç sayfası
        girilenden farklı bir açı raporluyordu. Artık girilen açılar hem
        uzunlukları hem raporu belirler; girilmediyse konik nozul için
        yaygın varsayılanlar (30 / 15 derece; Sutton & Biblarz 9. baskı
        Böl. 3) kullanılır.
        """
        conv = getattr(self, 'convergent_half_angle_deg', None)
        div = getattr(self, 'divergent_half_angle_deg', None)
        conv = float(conv) if conv else 30.0
        # Varsayılan diverjan yarı açısı verim referansıyla AYNI sabittir
        # (ÖH D15 / P2B2-08): iki yer ayrışırsa çizilen koni ile Isp'nin
        # dayandığı koni yeniden ayrılır.
        div = float(div) if div else SOLID_NOZZLE_REFERENCE_HALF_ANGLE_DEG
        return conv, div

    def _calculate_nozzle_length(self, d_throat=None, d_exit=None):
        """Calculate total nozzle length for conical nozzle.

        Convergent: L_conv = (D_chamber - D_throat) / (2 * tan(conv_half_angle))
        Divergent:  L_div  = (D_exit - D_throat) / (2 * tan(div_half_angle))

        Yarı açılar _nozzle_half_angles()'dan gelir (kullanıcı girdisi).
        Çağıran boğaz/çıkış çapını verirse o kullanılır — böylece itki
        eğrisinden gelen boğazla CAD/rapor arasında ikinci bir nozul boyu
        tanımı oluşmaz.
        """
        if d_throat is None:
            d_throat = self._estimate_throat_diameter()
        if d_exit is None:
            d_exit = self._design_exit_diameter()  # P2B3-07: tek kaynak

        conv_deg, div_deg = self._nozzle_half_angles()
        conv_half_angle = np.radians(conv_deg)
        div_half_angle = np.radians(div_deg)

        L_conv = (self.D_chamber - d_throat) / (2 * np.tan(conv_half_angle))
        L_div = (d_exit - d_throat) / (2 * np.tan(div_half_angle))

        return max(L_conv + L_div, 0.01)  # minimum 10mm

    def _get_nozzle_exit_diameter(self):
        """Lüle çıkış çapı [m] — TEK kaynak (_design_exit_diameter, P2B3-07).

        A_e = eps * A_t_ETKİN; Cd ile şişirilmiş geometrik boğazdan
        türetilmez (bkz. _design_exit_diameter docstring'i).
        """
        return self._design_exit_diameter()

    def _dry_mass_breakdown(self):
        """Kuru kütlenin BİLEŞEN DÖKÜMÜ [kg] — T03 (2026-08-03).

        Toplam zaten hesaplanıyordu ama yalnız TEK sayı olarak yayımlanıyordu.
        Arayüzdeki 'Total Dry Mass' alanı ise kendi ipucunda "kasa + lüle +
        yalıtım + aviyonik + kapak toplamı" diyor; kullanıcı bileşenleri elle
        girip 4,300 kg beyan ederken çözücü geometriden 20,409 kg buluyordu
        (4,7 kat) ve iki sayı yan yana, açıklamasız duruyordu. Dökümü
        yayımlamak arayüzün bileşen alanlarını çözücünün kendi değerleriyle
        doldurabilmesini ve farkın nereden geldiğinin görülmesini sağlar.

        Dönüş: {'case_kg', 'closure_kg', 'nozzle_kg', 'insulation_kg',
                'igniter_misc_kg', 'total_kg', 'basis'}.
        """
        material, sigma_y, SF, t_wall = self._case_design()
        rho_case = self._case_density()
        L_case = self._case_inner_length()
        d_case = self._case_inner_diameter()

        case_shell_mass = np.pi * d_case * L_case * t_wall * rho_case
        closure_mass = case_shell_mass * SOLID_CASE_CLOSURE_MASS_FRACTION
        structural_mass = case_shell_mass + closure_mass
        # Lüle ve ateşleyici/montaj kalemleri YAPISAL kütlenin oranıdır
        # (aşağıdaki toplamla birebir aynı çarpanlar).
        nozzle_mass = structural_mass * 0.15
        igniter_misc_mass = structural_mass * 0.05

        # ÖH D18 (P2B4-04): yalıtım VE liner halkası TEK yerde
        # (_insulation_liner_masses); kuru kütle toplamı da aynı yerden okur,
        # böylece iki yol ayrışamaz.
        insulation_mass, liner_mass = self._insulation_liner_masses()

        total = (structural_mass * 1.20) + insulation_mass + liner_mass
        return {
            'case_kg': float(case_shell_mass),
            'closure_kg': float(closure_mass),
            'nozzle_kg': float(nozzle_mass),
            'insulation_kg': float(insulation_mass),
            # ÖH D18 (P2B4-04, ikinci ayak): liner KALINLIĞI kuru kütleye HİÇ
            # girmiyordu. ÖLÇÜLDÜ (once.json): liner_thickness 0,1 -> 5,0 ->
            # 50,0 mm iken dry_mass_kg üçünde de 16,286993 kg (hiç
            # kıpırdamıyor), oysa aynı yanıt total_thermal_thickness'i
            # 20,1 / 25,0 / 70,0 mm diye yayımlıyordu. 50 mm liner
            # @1200 kg/m3 tek başına yayımlanan TÜM kuru kütleden ağırdır ve
            # atalet kütlesine 0 kg giriyordu (kütle kesri iyimser, uçuş
            # zinciri buradan besleniyor). Artık kendi kaleminde durur.
            'liner_kg': float(liner_mass),
            'igniter_misc_kg': float(igniter_misc_mass),
            'total_kg': float(total),
            'basis': (
                'case shell from the hoop-stress wall thickness and the case '
                'material density; closures as a fixed fraction of the shell; '
                'nozzle and igniter/misc as fractions of the structural mass; '
                'insulation and liner as annular rings from the entered '
                'thicknesses and the single insulation/liner density record '
                '(_insulation_density). Avionics are NOT part of the motor '
                'and are not included here'),
        }

    def _insulation_liner_masses(self):
        """Yalıtım ve liner halka kütleleri [kg] — TEK tanım noktası.

        ÖH D18 (P2B4-04). Bu iki kütle üç yerde birbirinden bağımsız
        yazılıyordu ve ÖLÇÜMDE ayrıştılar (once.json, D=100 mm, yalıtım
        20 mm, liner 5 mm):

          liner_density  _dry_mass_breakdown.total_kg  _calculate_dry_mass()
             200                11,7631 kg                16,2870 kg
            1200                16,2870 kg                16,2870 kg
            3000                24,4300 kg                16,2870 kg

        yani ``_dry_mass_breakdown`` kullanıcının yoğunluğunu izlerken
        ``_calculate_dry_mass`` tablo sabitine çakılı kalıyordu; iki yol
        %38'e kadar ayrışmıştı. ``_calculate_dry_mass`` docstring'i "iki yol
        ayrışırsa test yakalar" diyor — yakalayamadı, çünkü bekçi yalnız
        parçaların toplamını sınıyordu (her zaman doğru olan totoloji).
        Sayı artık TEK yerde kurulur.

        Geometri: iki katman grain dış çapının hemen dışında, ardışık
        halkalardır. Ortalama çap kuralı (iç çap + kalınlık) her ikisinde de
        aynıdır; yoğunluk tek kayıttan (_insulation_density) gelir, iki katman
        için AYRI yoğunluk uydurulmaz — ısıl direnç zinciri de tek iletkenlik
        kullanır (_insulation_resistance).

        SIRA — ÖH D24 (OH-D23-10). Eski kod liner halkasını yalıtımın DIŞINA
        koyuyordu (``d_liner_inner = D + 2*t_ins``), yani içten dışa
        grain → yalıtım → liner → kasa. Bu, katı motorun yapım sırasının
        TERSİdir: liner grain'i yalıtıma bağlayan elastomer katmandır, bu
        yüzden yalıtımın İÇİNDE, grain'e yapışık durur (kaynak ve gerekçe:
        modül düzeyindeki ``SOLID_THERMAL_LAYER_ORDER``). Sıra bir modelleme
        seçimiydi ve hiçbir yerde beyan edilmiyordu; artık halkalar sırayı
        izliyor ve sıra ``_design_insulation_system`` üzerinden
        ``cad_design.insulation_system.thermal_barrier.layer_order`` olarak
        YAYIMLANIYOR.

        ÖLÇÜLEN ETKİ (once.json/sonra.json OH-D23-10; D=100 mm, L_kasa=0,6 m,
        ρ=1200 kg/m³ — yalıtım 20 mm / liner 5 mm):

          kalem            önce (yanlış sıra)   sonra (SP-8093 sırası)
          insulation_kg        5,428672              5,881061   (+%8,33)
          liner_kg             1,639911              1,187522   (−%27,59)
          TOPLAM               7,068583              7,068583   (bit-aynı)

        Toplamın değişmemesi tesadüf değildir: iki halka aynı yoğunluğu
        paylaştığı için birleşimleri D ile D+2(t_yal+t_liner) arasındaki TEK
        halkadır ve o halkanın kütlesi sıraya bağlı değildir. Cebirsel olarak
        (ρ, L, π sadeleşir):
            (D+t_i)·t_i + (D+2t_i+t_l)·t_l
              = (D+t_l)·t_l + (D+2t_l+t_i)·t_i  = D(t_i+t_l) + (t_i+t_l)²
        Yani ``_calculate_dry_mass``, ``total_kg`` ve onlardan türeyen her
        şey (kütle kesri, uçuş zinciri, maliyet toplamı) BİT-AYNI kalır;
        değişen YALNIZ dökümdeki iki kalemin bölüşümüdür. Yalıtım kalınlığı
        0 olan varsayılan motorda hiçbir sayı kıpırdamaz (liner iç çapı iki
        sırada da D'dir).
        """
        L_case = self._case_inner_length()
        rho = self._insulation_density()
        t_ins = max(float(getattr(self, 'insulation_thickness_m', 0.0)), 0.0)
        t_liner = max(float(getattr(self, 'liner_thickness',
                                    SOLID_INSULATION['thickness_m'])), 0.0)
        # Liner grain'e YAPIŞIK en iç halkadır: iç çapı grain dış çapıdır.
        liner_mass = (np.pi * (self.D_chamber + t_liner) * t_liner * L_case
                      * rho)
        # Yalıtım liner'ın hemen dışındaki halkadır: iç çapı D + 2*t_liner.
        d_ins_inner = self.D_chamber + 2.0 * t_liner
        insulation_mass = (np.pi * (d_ins_inner + t_ins) * t_ins * L_case
                           * rho)
        return float(insulation_mass), float(liner_mass)

    def _calculate_dry_mass(self):
        """Estimate dry mass of motor from geometry.

        Components:
        - Case: cylindrical shell, AISI 4130 steel (rho=7800 kg/m3)
          wall thickness from hoop stress: t = P_c * r / (sigma_y / SF)
        - Forward + aft closures: ~30% of case mass
        - Nozzle: ~15% of total dry mass
        - Igniter + misc: ~5% of total dry mass

        Bileşen dökümü ``_dry_mass_breakdown`` ile AYNI formüllerden gelir
        (T03); bu metodun döndürdüğü toplam orada da ``total_kg`` olarak
        yayımlanır — iki yol ayrışırsa test yakalar.
        """
        # Case wall thickness — TEK kaynak (_case_design); kullanıcının
        # yield_strength / safety_factor / case_thickness / case_material
        # girdileri buraya işler.
        material, sigma_y, SF, t_wall = self._case_design()
        rho_case = self._case_density()

        # Kasa iç boyu = grain yığını + segment araları + kapak payı;
        # iç çapı = grain + 2x yalıtım (her ikisi TEK kaynaktan, v2.6.26).
        L_case = self._case_inner_length()
        d_case = self._case_inner_diameter()

        # Cylindrical shell mass
        case_shell_mass = np.pi * d_case * L_case * t_wall * rho_case

        # Forward + aft closure mass (~30% of shell mass, simplified)
        # H4-8: oran TEK tanım noktasından gelir; maliyet modeli de aynı
        # sabiti kullanır (daha önce orada 1.15 yazılıydı).
        closure_mass = case_shell_mass * SOLID_CASE_CLOSURE_MASS_FRACTION

        # Subtotal structural mass
        structural_mass = case_shell_mass + closure_mass

        # Nozzle mass: ~15% additional
        nozzle_factor = 0.15
        # Igniter + misc: ~5% additional. (Eski yorum bu %5'in yalıtımı da
        # kapsadığını söylüyordu; yalıtım artık kullanıcının KENDİ
        # kalınlığından açıkça hesaplanır, %5 götürüsü ateşleyici/montaj
        # kalemlerine kalır. insulation_thickness=0 iken katkı sıfırdır.)
        misc_factor = 0.05

        # ÖH D18 (P2B4-04): yalıtım + liner halkaları TEK kaynaktan
        # (_insulation_liner_masses) — burada tablo sabiti okunuyordu ve
        # döküm yolu ile bu yol %38'e kadar ayrışmıştı (ölçüm o metodun
        # docstring'inde).
        insulation_mass, liner_mass = self._insulation_liner_masses()

        dry_mass = (structural_mass * (1.0 + nozzle_factor + misc_factor)
                    + insulation_mass + liner_mass)

        # ÖH D18 (P2B4-07) — BEYANSIZ 100 g TABANI SÖKÜLDÜ.
        # Burada ``dry_mass = max(dry_mass, 0.1)`` duruyordu ("Sanity check
        # ... minimum 100g"). Sayı hiçbir kaynaktan türetilmemişti ve hiçbir
        # yanıt alanında BEYAN EDİLMİYORDU. ÖLÇÜLDÜ (once.json, bates APCP
        # 40 bar, D/L/çekirdek = 10/10/3 mm): masses.dry_mass_kg = 0,100000
        # ⟷ masses.inert_breakdown.total_kg = 0,084638 (+%18,15) — aynı
        # sözlükte, aynı büyüklük, iki sayı; total_mass_kg de uydurma
        # tabandan besleniyordu. 12/20/4 mm ve üstünde taban sönüyor, yani
        # yalnız küçük motorlarda ısırıyordu ve kimse görmüyordu.
        # Kuru kütle artık BİLEŞENLERİNİN TOPLAMIDIR; küçük motorda küçük
        # çıkması bir hata değil, ölçümün kendisidir.
        return dry_mass
    
    def _calculate_wet_mass(self):
        """Calculate wet mass with propellant"""
        # DENETİM DÜZELTMESİ (#1459): grain hacmi tek kaynaktan (_propellant_volume)
        # alınır — bu fonksiyon grain tipine DUYARLIDIR (BATES/tübüler annulus,
        # end-burner tam silindir, star/wagon poligon-ofset). Eski sabit annulus
        # formülü np.pi*(D_ch²−D_core²)/4*L, end-burner ve star grainlerde yakıt
        # kütlesini yanlış (end-burner'da EKSİK) sayıyordu. calculate_performance
        # zaten _propellant_volume kullanıyor; wet_mass artık onunla tutarlı.
        grain_volume = self._propellant_volume()
        propellant_mass = grain_volume * self.rho_p
        return self._calculate_dry_mass() + propellant_mass
    
    def _calculate_grain_hoop_stress(self):
        """Grain port yüzeyi hoop gerilmesi [MPa].

        DENETİM DÜZELTMESİ (2026-07-19): burası eskiden ikinci, çelişkili bir
        grain gerilme kaynağıydı (ince-cidar benzetimi). Artık tek gerçek
        kaynağa (_calculate_grain_structural, düzlem-şekil değiştirme
        elastisite çözümü) delege eder; iki panel farklı sayı gösteremez.
        """
        return self._calculate_grain_structural()['bore_hoop_stress_mpa']
    
    def _calculate_environmental_effects(self):
        """Soğuk/sıcak gün etkisi - motorun KENDİ sıcaklık katsayısından.

        v2.6.26: bu metot sabit 8.5 / 2.1 / 25 / 12.3 / 15.2 / 20 sayıları
        döndürüyordu; hangi itergaç, hangi sıcaklık katsayısı, hangi basınç
        üssü olursa olsun aynıydı. Oysa gerekli fizik ELDE VAR:

            r(T) = r_ref * exp(sigma_p * (T - T_ref))          (yanma hızı)
            Pc   ~ r^(1/(1-n))  ->  dPc/Pc = (1+dr/r)^(1/(1-n)) - 1

        ``burn_rate_temp_coeff`` (sigma_p) ve ``temp_ref`` kullanıcıdan
        geliyor, ``n`` basınç üssü zaten motorun kendi verisi. Dolayısıyla
        yanma hızı ve basınç değişimi GERÇEKTEN hesaplanır. Isp değişimi
        hesaplanmaz (CEA'nın yeniden koşturulması gerekir) ve uydurulmaz.

        Sıcaklık aralığı, katı motorlarda yaygın niteleme aralığı olan
        -20 C / +50 C alınır ve çıktıda AÇIKÇA yazılır.
        """
        sigma_p = float(getattr(self, 'burn_rate_temp_coeff', 0.0) or 0.0)
        t_ref = float(getattr(self, 'temp_ref', 293.15))
        n_exp = float(getattr(self, 'n', 0.35))
        t_cold, t_hot = 253.15, 323.15  # -20 C / +50 C

        def _shift(t_ambient):
            """(yanma hızı % değişimi, kararlı hâl basıncı % değişimi)."""
            if sigma_p == 0.0:
                return None, None
            rate_ratio = float(np.exp(sigma_p * (t_ambient - t_ref)))
            if n_exp >= 1.0:
                # n >= 1 kararsız yanmadır; basınç ölçeklemesi tanımsız.
                return (rate_ratio - 1.0) * 100.0, None
            pressure_ratio = rate_ratio ** (1.0 / (1.0 - n_exp))
            return (rate_ratio - 1.0) * 100.0, (pressure_ratio - 1.0) * 100.0

        cold_rate, cold_pressure = _shift(t_cold)
        hot_rate, hot_pressure = _shift(t_hot)

        return {
            'temperature_effects': {
                # ÖH D15 (P2B1-02): sigma_p'nin kaynağı yayımlanır.
                'sigma_p_source': str(getattr(self, 'temp_coeff_source',
                                              'propellant table')),
                # V301/K-B (KT-05): KULLANILAN σp sayı olarak da yayımlanır;
                # sayfanın 'katalog' kipindeki salt okur alan bunu basar.
                'sigma_p_per_k': float(sigma_p),
                'basis': (
                    f'Computed from this motor: sigma_p={sigma_p:.5f} 1/K, '
                    f'T_ref={t_ref:.2f} K, n={n_exp:.3f}. Burn rate follows '
                    'r = r_ref*exp(sigma_p*dT); chamber pressure follows '
                    'Pc ~ r^(1/(1-n)). Isp shift is NOT computed (needs a CEA '
                    'run at the shifted condition). '
                    # v2.6.26: docstring "aralık çıktıda AÇIKÇA yazılır"
                    # diyordu ama yayımlanan metinde bandın ADI geçmiyordu;
                    # okuyucu iki ham sayı görüp nereden geldiklerini
                    # bilmiyordu. Söz artık tutuluyor.
                    'The two ambient points are the qualification band '
                    f'-20 C / +50 C ({t_cold:.2f} K / {t_hot:.2f} K), the '
                    'common solid motor qualification range; it is a '
                    'REPORTING CHOICE of this solver, not a limit computed '
                    'from your design or taken from your own qualification '
                    'plan.'
                    + ('' if sigma_p else
                       ' WARNING: the temperature coefficient is zero, so no '
                       'temperature sensitivity can be reported.')),
                'cold_day': {
                    'ambient_k': t_cold,
                    'burn_rate_change_percent': cold_rate,
                    'chamber_pressure_change_percent': cold_pressure,
                    'isp_change_percent': None,
                },
                'hot_day': {
                    'ambient_k': t_hot,
                    'burn_rate_change_percent': hot_rate,
                    'chamber_pressure_change_percent': hot_pressure,
                    'isp_change_percent': None,
                },
            },
            # Nem ve titreşim için elimizde ne model ne veri var; eski
            # 0.2 / 1.5 / '2G maximum' sayıları tamamen uydurmaydı.
            'storage_and_handling': {
                'basis': ('Generic storage and handling practice for composite '
                          'solid propellant; HRMA does not model moisture '
                          'uptake or vibration response.'),
                'moisture': 'Sealed container with desiccant recommended',
                'vibration': 'Use shock-absorbing packaging for transport',
                'orientation': 'Vertical storage preferred',
            },
        }
    
    def _calculate_safety_analysis(self, curve):
        """Safety analysis like other systems"""
        max_pressure = float(np.max(curve['pressure']))
        # DENETİM DÜZELTMESİ (#1497 + 2026-07-19): emniyet basınçlarının
        # TAMAMI gerçek kasadan türetilir. Eskiden design=100, burst=150,
        # relief=85 bar SABİTTİ — 200 bar çalışan bir motorda bile "patlama
        # basıncı 150 bar" yazıyordu, yani işletme basıncının ALTINDA.
        # Kasa duvarı _calculate_dry_mass / _calculate_structural_analysis ile
        # AYNI kaynaktan (_case_design) gelir; kopma basıncı merkezi
        # PressureVesselAnalyzer'dan (Faupel kalın cidar + ince cidar plastik
        # limit) okunur — emniyet paneliyle kap paneli aynı sayıyı gösterir.
        material, sigma_y, SF_design, t_wall = self._case_design()
        # OH-Z2-08 (Z4, 2026-08-27): hoop yarıçapı KASA iç yarıçapıdır —
        # basınç yalıtımdan geçip metal kabuğun iç yüzüne biner (dosyanın
        # kendi boyutlandırması :1981/:2009/:5238 ile tutarlı). Eski
        # D_chamber/2 (grain yarıçapı) akma basıncını 1+2·t_ins/D çarpanıyla
        # TEHLİKELİ yönde şişiriyordu (5 mm yalıtımda +%10).
        r_inner = self._case_inner_diameter() / 2.0
        yield_pressure_bar = (sigma_y * t_wall / r_inner) / 1e5  # bar
        pressure_safety_factor = (yield_pressure_bar / max_pressure
                                  if max_pressure > 0 else float('inf'))

        # Tasarım basıncı = MEOP x tasarım basınç faktörü (kullanıcının
        # safety_factor girdisi); burst = gerçek kap kapasitesi.
        design_pressure_bar = max_pressure * SF_design
        burst_pressure_bar = yield_pressure_bar   # yedek: akma tabanlı
        burst_source = 'thin-wall yield pressure (sigma_y*t/r)'
        vessel_status = None
        vessel_warnings = []
        # F2-1 (v2.6.27): kopma basıncının KULLANDIĞI akma dayanımı yanıtta
        # adıyla yayımlanır. Boyutlandırmanın kullandığı `sigma_y` ile burada
        # okunan değer aynı olmak ZORUNDADIR — tek kapta iki malzeme kimliği
        # bu iki sayının ayrışmasıyla ortaya çıkıyordu (ölçüm: etiket
        # 'steel_4130' / 460 MPa, boyutlandırma 250 MPa, burst 341,13 vs
        # 186,09 bar). Sayı yayımlandığı için tutarsızlık bir sonraki sefer
        # yanıtın kendisinden görülür, yalnız testten değil.
        burst_yield_pa = None
        try:
            from hrma.analysis.pressure_vessel import PressureVesselAnalyzer
            pv = PressureVesselAnalyzer().analyze(
                meop_bar=max(max_pressure, 1e-6),
                inner_diameter_mm=self._case_inner_diameter() * 1000.0,
                material=material,
                wall_thickness_mm=t_wall * 1000.0,
            )
            burst_pressure_bar = float(pv['actual_burst_pressure_bar'])
            burst_source = ('Faupel thick-wall / thin-wall plastic limit '
                            '(hrma.analysis.pressure_vessel)')
            vessel_status = pv['status']
            vessel_warnings = list(pv.get('warnings', []))
            derating = pv.get('derating') or {}
            if derating.get('room_temp_yield_strength_Pa') is not None:
                burst_yield_pa = float(
                    derating['room_temp_yield_strength_Pa'])
        except Exception as exc:
            vessel_warnings.append(
                f'Burst pressure fell back to the thin-wall yield estimate: {exc}')
        if burst_yield_pa is None:
            # Yedek yolda kopma AYNI sigma_y'den türetildi (yield_pressure_bar).
            burst_yield_pa = float(sigma_y)
        material_identity_consistent = bool(
            abs(burst_yield_pa - float(sigma_y))
            <= 1e-9 * max(abs(float(sigma_y)), 1.0))
        if not material_identity_consistent:
            vessel_warnings.append(
                'Case material identity split: the wall was sized with '
                f'{sigma_y / 1e6:.1f} MPa but the burst pressure was computed '
                f'from {burst_yield_pa / 1e6:.1f} MPa for the same case.')

        # --- KAZANILMAMIŞ KAP ONAYI (B2-4, v2.6.27) -----------------------
        # ÖLÇÜLDÜ (cidar GÖNDERİLMEDEN, dört hazne basıncında): 'vessel_status'
        # dördünde de 'PASS'. Kap, geçmek ÜZERE boyutlandırılmıştır
        # (_case_design Barlow ile SF_hedef'i sağlayan cidarı üretir), sonra
        # aynı cidar sınanıp "geçti" denir — doğrulama değil, hedefin geri
        # okunması. ONAY geri çekilir, UYARI çekilmez: 'MARGINAL'/'FAIL'
        # gerçek bir tehlike bildirimidir ve susturulması kazanılmamış bir
        # onaydan daha kötüdür. Sayılar (kopma basıncı, marj, kalınlık)
        # SİLİNMEZ — gerçekten hesaplandılar.
        #
        # Uç katmanında A3'ün AYNI kapısı var (app.py
        # _withhold_unearned_vessel_verdict). Buradaki kapı motoru doğrudan
        # kullanan yolları da (dışa aktarım, UQ, testler) kapsar ve iki kapı
        # aynı sonucu verdiği için üst üste çalışması davranışı değiştirmez.
        vessel_prov = self._case_wall_provenance()
        vessel_user_wall = vessel_prov['source'] == 'user_supplied'
        vessel_tautological = bool(not vessel_user_wall)
        #: Kapta ONAY sayılan hükümler (iki kapı da bu TEK listeyi okur).
        kap_onay_hukumleri = ('PASS', 'SAFE', 'ACCEPTABLE', 'OK')
        if vessel_tautological and str(vessel_status or '').upper() in (
                kap_onay_hukumleri):
            vessel_status = 'NOT_EVALUATED'
        # --- V3 yapi-sf 3. tur B (karar §28-37 Ş2-3 (a)): (C) MODEL
        # GEÇERLİLİK SINIRI. Kasanın kendi ısı modeli onu erime noktasında/
        # üstünde ya da düşürme verisinin üstünde buluyorsa oda sıcaklığı
        # dayanımıyla hesaplanan kopma basıncından ONAY çıkmaz (hibritle aynı
        # sözleşme: onay tavana çekilir, FAIL/MARGINAL uyarısı susturulmaz,
        # sayılar tanı amaçlı kalır). Ölçüt tek kaynaktan
        # (``_case_model_validity`` → ``structural_model_validity``).
        from hrma.analysis.structural_analysis import (
            STRUCTURAL_VERDICT_NOT_EVALUATED)
        kasa_gecerlilik = self._case_model_validity()
        # V301/K-D: kasa sıcaklığı ÇÖZÜLMEDİYSE (``_calculate_case_
        # temperature`` None) geçerlilik ölçülemez; oda sıcaklığı
        # dayanımıyla kurulan kap onayı kazanılmamıştır ve geri çekilir.
        _kasa_sicaklik_cozulmedi = ((getattr(
            self, '_case_temperature_status', None) or {}).get('source')
            == 'not_solved')
        if ((kasa_gecerlilik.get('model_validity_limit_exceeded') is True
                or _kasa_sicaklik_cozulmedi)
                and str(vessel_status or '').upper() in kap_onay_hukumleri):
            vessel_status = STRUCTURAL_VERDICT_NOT_EVALUATED
        # Z2 (P2B2-01): kullanıcının cidarı artık kırpılmadığı için kapın
        # sınadığı cidar GERÇEKTEN onun cidarıdır. İmalat tabanının altındaki
        # bir cidar reddedilmez — analiz edilir ve BEYAN edilir; kap hükmü de
        # (bu ince cidarla) doğal olarak FAIL/MARGINAL'e düşer.
        if vessel_prov['below_manufacturing_floor']:
            vessel_warnings.append(
                'Case wall {:.4g} mm is below the {:.4g} mm manufacturing '
                'floor HRMA uses for its own proposals. The wall was NOT '
                'raised: every number in this block describes the wall you '
                'entered. The hoop stress alone requires {:.4g} mm at this '
                'chamber pressure.'.format(
                    vessel_prov['used_mm'],
                    vessel_prov['manufacturing_floor_mm'],
                    vessel_prov['hoop_required_mm']))
        # V301/T-ÇAPA-D (kalem 1; T-ÇAPA-C1 RAPOR §3 BULGU): yukarıdaki iki
        # geri çekme kuralı (kasa sıcaklığı çözülmedi / model geçerlilik
        # sınırı aşıldı) hükmü NOT_EVALUATED'a çektiğinde dayanak cümlesi
        # "the burst margin and the vessel status are an evaluation of that
        # wall" demeye devam ediyordu — hükümle çelişen metin. Geri çekme
        # koşulu varsa dayanak, cidarı kim vermiş olursa olsun, hükmün NEDEN
        # verilmediğini söyler (FAIL/MARGINAL kalmışsa o uyarıdır,
        # susturulmaz; sayılar tanı amaçlıdır). Geçerlilik dışı cümlesi uç
        # katmanınınkiyle (app.py _withhold_unearned_vessel_verdict) aynı
        # sözleşme.
        _boyutlandirma_cumlesi = (
            'No acceptance is issued: no case thickness was supplied, so '
            'HRMA sized the wall itself from the hoop stress to meet the '
            'design safety factor. Checking that wall and reporting a pass '
            'is the design target read back, not an independent '
            'verification.')
        _uyari_cumlesi = (' A remaining MARGINAL/FAIL status is a warning '
                          'and is never suppressed.')
        if _kasa_sicaklik_cozulmedi:
            _geri_cekme = (
                'the case wall temperature was not solved '
                '(case_temperature_status), so the structural model cannot '
                'be checked against the temperature of this case wall. The '
                'burst pressure, burst margin and safety factor in this block '
                'use the room-temperature case strength, so they are '
                'diagnostic numbers only and not a check of this case wall; '
                "sending 'case_thickness' does not change that.")
        elif kasa_gecerlilik.get('model_validity_limit_exceeded') is True:
            _geri_cekme = (
                'the case wall temperature computed by the heat-transfer '
                'model is outside the validity limit of the structural model '
                '(model_validity_limit_exceeded, model_validity_reasons). The '
                'burst pressure, burst margin and safety factor in this block '
                'use the room-temperature case strength, so they are '
                'diagnostic numbers only and not a check of this case wall; '
                "sending 'case_thickness' does not change that at this case "
                'temperature.')
        else:
            _geri_cekme = None
        if _geri_cekme is not None and vessel_user_wall:
            vessel_status_basis = ('No acceptance is issued: ' + _geri_cekme
                                   + _uyari_cumlesi)
        elif _geri_cekme is not None:
            # Boyutlandırma cümlesi doğru kalır; yalnız "case_thickness
            # verirsen doğrulama alırsın" vaadi bu koşulda yanlış olur.
            vessel_status_basis = (_boyutlandirma_cumlesi + ' In addition, '
                                   + _geri_cekme + _uyari_cumlesi)
        elif vessel_user_wall:
            vessel_status_basis = (
                'The case wall thickness was supplied by the user, so the '
                'burst margin and the vessel status are an evaluation of that '
                'wall.')
        else:
            vessel_status_basis = (
                _boyutlandirma_cumlesi
                + " Supply 'case_thickness' (mm) to obtain one."
                + _uyari_cumlesi)

        relief_setting_bar = (design_pressure_bar
                              * SOLID_CASE_DESIGN['relief_fraction_of_design'])

        return {
            'pressure_safety': {
                'max_operating_pressure_bar': max_pressure,
                'design_pressure_bar': float(design_pressure_bar),
                'safety_factor': float(pressure_safety_factor),
                'burst_pressure_bar': float(burst_pressure_bar),
                'relief_valve_setting_bar': float(relief_setting_bar),
                # ÖH D17 / P5B2-09 (kalan yarı). Bu üretici ``burst_margin``i
                # kopma/MEOP olarak yayımlıyor; KARDEŞ üretici
                # (``analysis.pressure_vessel`` -> ``analysis.safety_analysis``)
                # AYNI adı kopma/GEREKEN-kopma olarak yayımlıyor. Ölçüldü
                # (D15 a2): aynı yanıt yolunda 7,13 (bu) ⟷ 3,57 (kardeş) —
                # TAM 2 KAT, çünkü kopma katsayısı 2,0. SAYI DEĞİŞMEDİ;
                # yanına oranın hangi tanım olduğunu ADIYLA söyleyen
                # kardeşler kondu (doktrin 4: iki üretici aynı dili konuşur).
                'burst_margin': (float(burst_pressure_bar / max_pressure)
                                 if max_pressure > 0 else float('inf')),
                'burst_margin_vs_meop': (
                    float(burst_pressure_bar / max_pressure)
                    if max_pressure > 0 else float('inf')),
                'burst_margin_definition': (
                    'burst_margin = burst_pressure_bar / '
                    'max_operating_pressure_bar (i.e. against MEOP, not '
                    'against a code-required burst pressure). The sibling '
                    'pressure-vessel producer publishes burst_margin '
                    'against the REQUIRED burst pressure and exposes this '
                    'ratio as burst_margin_vs_meop; the two differ by the '
                    'burst factor and must not be compared to the same '
                    'thresholds.'),
                'yield_pressure_bar': float(yield_pressure_bar),
                'case_material': material,
                'case_wall_thickness_mm': float(t_wall * 1000.0),
                'design_pressure_basis': (
                    f'MEOP x design factor {SF_design:.2f} (user safety factor)'),
                'burst_pressure_basis': burst_source,
                'relief_valve_basis': (
                    f"recommendation: {SOLID_CASE_DESIGN['relief_fraction_of_design']:.2f}"
                    ' x design pressure (API 520 practice), not a computed'
                    ' vessel capability'),
                'vessel_status': vessel_status,
                'vessel_warnings': vessel_warnings,
                # B2-4: hükmün KAZANILIP kazanılmadığı adıyla yazılır.
                'wall_thickness_source': vessel_prov['source'],
                'vessel_status_is_tautological': vessel_tautological,
                'vessel_status_basis': vessel_status_basis,
                # V3 yapi-sf 3. tur B: geçerlilik bayrağı + künye (+ sınır
                # aşıldıysa verdict_withheld ve gerekçe kodu).
                **kasa_gecerlilik,
                # --- Z2 künyesi: İSTENEN ⟷ KULLANILAN cidar ------------
                'case_wall_thickness_requested_mm': (
                    vessel_prov['requested_mm']),
                'case_wall_hoop_required_mm': vessel_prov['hoop_required_mm'],
                'case_wall_manufacturing_floor_mm': (
                    vessel_prov['manufacturing_floor_mm']),
                'case_wall_at_minimum_clamp': vessel_prov['clamped_to_floor'],
                'case_wall_below_manufacturing_floor': (
                    vessel_prov['below_manufacturing_floor']),
                # --- F2-1 malzeme kimliği (v2.6.27) ---------------------
                # Kasa cidarını boyutlandıran akma dayanımı ile kopma
                # basıncını üreten akma dayanımı, TEK kaptaki TEK malzemenin
                # aynı kaydından gelmek zorundadır.
                'case_yield_strength_mpa': float(sigma_y / 1e6),
                'burst_yield_strength_mpa': float(burst_yield_pa / 1e6),
                'material_identity_consistent': material_identity_consistent,
                'material_identity_basis': (
                    'The wall thickness / hoop safety factor and the burst '
                    'pressure are computed from the same material record '
                    f"('{material}'), so one case carries one identity."
                    if material_identity_consistent else
                    'INCONSISTENT: the sizing strength and the burst strength '
                    'come from different material properties for the same '
                    'case; the burst pressure is not earned by the wall that '
                    'was sized.'),
            },
            'ignition_safety': {
                'ignition_system': 'Electric match',
                # v2.6.26: burada sabit 'minimum_safe_distance_m': 30 vardı ve
                # motorun büyüklüğünden bağımsızdı — 100 N'lik bir motor da
                # 50 kN'lik bir motor da aynı 30 metreyi görüyordu. Tahliye
                # mesafesi itergaç kütlesiyle ölçeklenir; bunu gerçekten
                # hesaplayan modül safety_analysis (Kingery-Bulmash /
                # Kinney-Graham + UFC 3-340-02). Uydurma tek sayı yerine
                # kullanıcı oraya yönlendirilir.
                'minimum_safe_distance_m': None,
                'minimum_safe_distance_basis': (
                    'NOT_COMPUTED here - standoff scales with propellant mass; '
                    'use the safety analysis (blast/fragment/thermal) for a '
                    'distance derived from this motor'),
                'personal_protective_equipment': 'Required',
                'fire_suppression': 'CO2 system recommended'
            },
            'handling_safety': {
                'electrostatic_precautions': 'Grounding required',
                # v2.6.26 (P4) UYDURMA SÖKÜMÜ: burada sabit '0-40°C storage'
                # yazıyordu. Depolama bandı yakıta bağlıdır (HTPB elastomer
                # ile dökme şeker aynı sınırı taşımaz) ve HRMA'nın bir
                # depolama modeli YOKTUR. Kasıtlı olarak BURAYA SAYI
                # KOYMUYORUZ: yakıt kaydındaki kürleme sıcaklığı termal
                # blokta 'yumuşama vekili' etiketiyle zaten yayımlanıyor;
                # aynı sayıyı bir de 'depolama sınırı' adıyla emniyet
                # bloğuna kopyalamak onu ölçülmüş bir servis limitine
                # dönüştürürdü (şeker yakıtında 125 °C çıkar — depolama
                # tavsiyesi olarak tehlikeli olurdu).
                'temperature_limits': None,
                'temperature_limits_status': 'NOT_MODELLED',
                'temperature_limits_basis': (
                    'HRMA has no propellant storage/ageing model. The grain '
                    'strain margin IS computed at the storage temperature you '
                    'enter (structural_analysis.grain_structural: '
                    'storage_temperature_k, strain_safety_factor) and a '
                    'softening proxy is reported in '
                    'thermal_analysis.thermal_management.'
                    'material_temperature_limits.grain_max_temp_k. Take the '
                    'actual storage limits from the propellant SDS.'),
                'transportation_class': 'UN 1.3C',
                'hazard_classification': 'Explosive',
                'basis': ('Generic handling practice for composite solid '
                          'propellant; verify against the propellant SDS and '
                          'your transport authority - not derived from this '
                          'motor'),
            },
            # v2.6.26 UYDURMA SÖKÜMÜ: burada 'case_rupture_probability': 1e-6,
            # 'nozzle_failure_probability': 1e-5, 'ignition_failure_probability':
            # 1e-4 ve 'overall_reliability': 0.999 sabitleri vardı. Bu sayılar
            # hiçbir hesaptan gelmiyordu, hiçbir kaynağa dayanmıyordu ve motor
            # ne olursa olsun aynıydı. Arıza olasılığı ancak yük/dayanım
            # dağılımı, COV ve bir güvenilirlik modeli ile üretilebilir;
            # elimizde bunların hiçbiri yok. Sayı üretmek yerine hangi
            # arıza modlarının ele alınması gerektiğini söylüyoruz.
            'failure_modes': {
                'modes_to_assess': [
                    'case rupture', 'nozzle failure', 'ignition failure'],
                'quantified': False,
                'basis': ('HRMA does not compute failure probabilities. A '
                          'quantitative reliability estimate needs load/strength '
                          'distributions and test data that this tool does not '
                          'have.'),
            }
        }

    def _calculate_quality_analysis(self):
        """Kalite güvence PLANI - ölçülmüş kalite değil.

        v2.6.26 UYDURMA SÖKÜMÜ: bu fonksiyon eskiden 'quality_metrics' başlığı
        altında 'dimensional_accuracy_percent': 99.5 ve 'surface_finish_quality':
        'Ra 3.2 um' döndürüyordu. Hiçbir şey imal edilmemişken ulaşılmış bir
        kalite değeri raporlamak düpedüz uydurmadır: kullanıcı bunu kendi
        motorunun ölçülmüş doğruluğu sanır. Ölçülen değer yerine PLAN
        raporlanır ve planın genel pratikten geldiği açıkça yazılır.
        """
        return {
            'basis': ('Generic qualification plan for composite solid motors - '
                      'not computed from this design and not a measurement of '
                      'anything that has been built.'),
            'testing_requirements': {
                'strand_burner_tests': 5,
                'static_fire_tests': 2,
                'pressure_vessel_tests': 1,
                'non_destructive_testing': 'X-ray, ultrasonic'
            },
            'quality_targets': {
                'note': ('Dimensional and surface-finish targets come from your '
                         'detail design and drawings; HRMA does not set or '
                         'measure them.'),
                'material_certification': 'Mill test certificates',
                'traceability': 'Full batch tracking'
            },
            'acceptance_criteria': {
                'burn_rate_tolerance_percent': 5,
                'pressure_tolerance_percent': 3,
                'thrust_tolerance_percent': 4,
                'impulse_tolerance_percent': 2,
                'basis': ('Typical published acceptance bands for amateur and '
                          'small commercial solid motors; agree the actual '
                          'limits with your test authority.'),
            }
        }
    
    def _calculate_advanced_performance(self, curve):
        """Advanced performance calculations.

        DENETİM DÜZELTMESİ (2026-07-19): verimler (94.5 / 96.2 / 95.8 / 86.8)
        ve kütle kesirleri (0.75 / 0.25 / 0.85) sabitti. Artık hepsi bu
        koşunun gerçek sonuçlarından türetilir; kullanıcının beyan ettiği
        overall_efficiency ise hesabı EZMEZ, yanına karşılaştırma olarak konur.
        """
        # Teslim edilen c* (statik ateşleme veri indirgeme) ve nozul verimi
        A_t = curve.get('throat_area') or np.pi * (
            self._estimate_throat_diameter() / 2) ** 2
        m_prop = self._propellant_volume() * self.rho_p
        if m_prop > 0 and len(curve['time']) > 1:
            pressure_integral = float(_trapezoid(
                np.asarray(curve['pressure']) * 1e5, curve['time']))
            c_star_delivered = pressure_integral * A_t / m_prop
            # Payda TEORİK c* (bkz. _c_star_theoretical) — aksi hâlde
            # kullanıcının yanma verimi bu metrikte görünmezdi.
            c_star_eff = 100.0 * c_star_delivered / self._c_star_theoretical()
        else:
            c_star_eff = 100.0
        nozzle_eff = 100.0 * self._total_nozzle_efficiency()
        combustion_eff = 100.0 * float(getattr(self, 'combustion_efficiency', 1.0))
        overall_eff = c_star_eff * nozzle_eff / 100.0

        dry_mass = self._calculate_dry_mass()
        wet_mass = dry_mass + m_prop
        prop_fraction = m_prop / wet_mass if wet_mass > 0 else 0.0
        # ÖH D15 a2 (P2B4-05): payda TEK kaynaktan ve BATES segment aralarını
        # görür (_grain_envelope_volume). Eskiden burada pi*r^2*L_grain vardı,
        # yani grain_design.volumetric_loading ile AYNI büyüklüğün ikinci ve
        # aralara kör bir tanımıydı — 50 mm aralıkta 1,40 kat ayrışıyordu.
        chamber_volume = self._grain_envelope_volume()
        loading_density = m_prop / chamber_volume if chamber_volume > 0 else 0.0
        volumetric_eff = (100.0 * self._propellant_volume() / chamber_volume
                          if chamber_volume > 0 else 0.0)

        combustion = {
            'combustion_efficiency_percent': float(combustion_eff),
            'c_star_efficiency_percent': float(c_star_eff),
            'nozzle_efficiency_percent': float(nozzle_eff),
            'overall_efficiency_percent': float(overall_eff),
            'overall_efficiency_definition': 'eta_c* x eta_nozzle',
        }
        user_overall = getattr(self, 'user_overall_efficiency', None)
        if user_overall is not None:
            combustion['user_declared_overall_efficiency_percent'] = float(
                user_overall * 100.0)
            combustion['user_vs_computed_note'] = (
                'The declared overall efficiency is shown for comparison '
                'only; performance is computed from the c* and nozzle '
                'efficiencies so the loss is never counted twice.')

        return {
            'combustion_analysis': combustion,
            'mass_utilization': {
                'propellant_mass_fraction': float(prop_fraction),
                'inert_mass_fraction': float(1.0 - prop_fraction),
                'loading_density_kgm3': float(loading_density),
                'volumetric_efficiency_percent': float(volumetric_eff),
            },
            # NOT: Eskiden burada, analiz edilen motordan bağımsız sabit
            # değerler döndüren bir "optimum" bloğu vardı (sabit genişleme
            # oranı, oda basıncı ve marj). Hiçbir yerde tüketilmiyordu ve
            # uydurma çıktıydı — 2.6.1 uydurma temizliğinde kaldırıldı.
            # Bekçi: tests/test_no_fabrication.py.
        }
    
    # Helper methods for calculations
    def _thrust_shape_report(self, thrust_data, time_data=None):
        """İtki eğrisinin BİÇİMİ — sınıf + kararı doğuran ölçüler.

        v2.6.27 (B2-1). Eski sınıflandırma yalnız ilk 10 ve son 10 örneğin
        ortalamasını karşılaştırıyordu; ARADAKİ TEPE hesaba girmiyordu ve
        tepeli (progresif-sonra-regresif) biçimler için bir sınıf yoktu.
        Ölçülen yanlış etiketler ve yeni ölçüt SOLID_THRUST_SHAPE_* sabit
        bloğunda yazılıdır.

        Kararın DAYANAĞI da döner (tepe/ortalama, dip/ortalama, tepenin
        normalize zamanı, uç platoları): sınıf bir etikettir, kullanıcı onu
        doğrulayabilmelidir.

        Args:
            thrust_data: itki örnekleri [N] (çözücünün TAM çözünürlüklü
                dizisi; yayımlanan seyreltilmiş dizi DEĞİL).
            time_data: aynı uzunlukta zaman [s]. Verilmezse zaman ağırlıklı
                ortalama alınamaz ve eşit aralık VARSAYILIR — bu varsayım
                çıktıda ``time_basis`` ile beyan edilir.

        Returns:
            'shape' sınıfı ve ölçüleri taşıyan sözlük. Örnek sayısı ya da
            pencere genişliği karar vermeye yetmiyorsa sınıf
            ``SOLID_THRUST_SHAPE_UNDETERMINED`` olur ve ölçüler None kalır —
            sayı da sınıf da UYDURULMAZ.
        """
        F = np.asarray(thrust_data, dtype=float)
        gecerli = np.isfinite(F)
        F = F[gecerli] if gecerli.size else F
        bos = {
            'shape': SOLID_THRUST_SHAPE_UNDETERMINED,
            'peak_over_mean': None,
            'min_over_mean': None,
            'peak_time_fraction': None,
            'start_plateau_N': None,
            'end_plateau_N': None,
            'window_mean_thrust_N': None,
            'window_duration_s': None,
            'window_samples': int(F.size),
            'time_basis': None,
            'basis': (
                'The curve does not contain enough usable samples (or has no '
                'positive thrust) to determine a shape; no class is invented.'),
            'criterion': self._thrust_shape_criterion_text(),
        }
        if F.size < 3 or not np.any(F > 0.0):
            return bos

        if time_data is None:
            t = np.arange(F.size, dtype=float)
            zaman_temeli = 'uniform_sample_index_assumed'
        else:
            t = np.asarray(time_data, dtype=float)
            if gecerli.size == t.size:
                t = t[gecerli]
            if t.size != F.size or not np.all(np.isfinite(t)):
                t = np.arange(F.size, dtype=float)
                zaman_temeli = 'uniform_sample_index_assumed'
            else:
                zaman_temeli = 'solver_time_samples'

        tepe = float(np.max(F))
        if tepe <= 0.0:
            return bos

        # --- Analiz penceresi: tepe itkinin TAIL_FRACTION katının üstü -----
        esik = SOLID_THRUST_SHAPE_TAIL_FRACTION * tepe
        icinde = F >= esik
        i0 = int(np.argmax(icinde))
        i1 = int(icinde.size - 1 - np.argmax(icinde[::-1]))
        if i1 - i0 < 2:
            return bos
        Fw = F[i0:i1 + 1]
        tw = t[i0:i1 + 1]
        sure = float(tw[-1] - tw[0])
        if not np.isfinite(sure) or sure <= 0.0:
            return bos

        # Zaman ağırlıklı ortalama: örnek yerleşimine duyarsız (avg_thrust
        # ile AYNI tanım — I_t/t_b).
        ort = float(_trapezoid(Fw, tw) / sure)
        if not np.isfinite(ort) or ort <= 0.0:
            return bos

        def _plato(baslangicta):
            """Pencerenin uç kesrindeki zaman ağırlıklı ortalama."""
            genislik = SOLID_THRUST_SHAPE_EDGE_FRACTION * sure
            if baslangicta:
                maske = tw <= tw[0] + genislik
            else:
                maske = tw >= tw[-1] - genislik
            if int(np.count_nonzero(maske)) < 2:
                return float(Fw[0] if baslangicta else Fw[-1])
            tt, ff = tw[maske], Fw[maske]
            araligi = float(tt[-1] - tt[0])
            if araligi <= 0.0:
                return float(np.mean(ff))
            return float(_trapezoid(ff, tt) / araligi)

        plato_bas = _plato(True)
        plato_son = _plato(False)
        i_tepe = int(np.argmax(Fw))
        tau_tepe = float((tw[i_tepe] - tw[0]) / sure)
        tepe_oran = float(tepe / ort)
        dip_oran = float(np.min(Fw) / ort)
        band = SOLID_THRUST_SHAPE_NEUTRAL_BAND

        if tepe_oran <= 1.0 + band and dip_oran >= 1.0 - band:
            sinif = SOLID_THRUST_SHAPE_NEUTRAL
        elif (plato_bas > 0.0 and tepe > plato_bas * (1.0 + band)
              and tau_tepe <= SOLID_THRUST_SHAPE_PEAK_INTERIOR_MAX):
            # Tepe pencerenin İÇİNDE ve başlangıç platosunun belirgin
            # üstünde: eğri önce tırmanıp sonra düşüyor.
            sinif = SOLID_THRUST_SHAPE_PROGRESSIVE_REGRESSIVE
        elif plato_son > plato_bas * (1.0 + band):
            sinif = SOLID_THRUST_SHAPE_PROGRESSIVE
        elif plato_son < plato_bas * (1.0 - band):
            sinif = SOLID_THRUST_SHAPE_REGRESSIVE
        else:
            sinif = SOLID_THRUST_SHAPE_NEUTRAL

        return {
            'shape': sinif,
            'peak_over_mean': tepe_oran,
            'min_over_mean': dip_oran,
            'peak_time_fraction': tau_tepe,
            'start_plateau_N': plato_bas,
            'end_plateau_N': plato_son,
            'window_mean_thrust_N': ort,
            'window_duration_s': sure,
            'window_samples': int(Fw.size),
            'time_basis': zaman_temeli,
            'basis': (
                'Shape is decided on the burning window (thrust above '
                f'{SOLID_THRUST_SHAPE_TAIL_FRACTION:.0%} of peak), using the '
                'time-weighted mean and the interior peak, not the first and '
                'last samples.'),
            'criterion': self._thrust_shape_criterion_text(),
        }

    @staticmethod
    def _thrust_shape_criterion_text():
        """Sınıflandırma ölçütünün kullanıcıya açık beyanı (TEK metin)."""
        return (
            'Window: samples where thrust >= '
            f'{SOLID_THRUST_SHAPE_TAIL_FRACTION:.0%} of peak thrust (ignition '
            'rise and burnout tail excluded). Mean: time-weighted '
            '(impulse/duration), so the class does not depend on the solver '
            'time step. NEUTRAL when both peak/mean and min/mean stay within '
            f'+-{SOLID_THRUST_SHAPE_NEUTRAL_BAND:.0%} of the mean. '
            'PROGRESSIVE-REGRESSIVE when the peak exceeds the opening plateau '
            f'by more than {SOLID_THRUST_SHAPE_NEUTRAL_BAND:.0%} and occurs '
            f'before {SOLID_THRUST_SHAPE_PEAK_INTERIOR_MAX:.0%} of the window '
            '(a later peak means the curve is still climbing, i.e. '
            'PROGRESSIVE). Otherwise the opening and closing plateaus (first '
            f'and last {SOLID_THRUST_SHAPE_EDGE_FRACTION:.0%} of the window) '
            'decide PROGRESSIVE vs REGRESSIVE. Taxonomy: Sutton & Biblarz, '
            'Rocket Propulsion Elements 9th ed., Ch. 12.')

    def _classify_thrust_curve(self, thrust_data, time_data=None):
        """İtki eğrisi biçim SINIFI (dize) — ayrıntısı _thrust_shape_report."""
        return self._thrust_shape_report(thrust_data, time_data)['shape']


    def _calculate_theoretical_isp(self, chamber_pressure_bar=None):
        """Calculate theoretical specific impulse.

        Isp_teorik = CF_ideal * c* / g0  (Sutton & Biblarz 9. baskı, Denk. 3-32)
        CF_ideal, optimal genişlemede (Pe = Pa, deniz seviyesi) ideal itki
        katsayısıdır (Sutton Denk. 3-30). Eski '0.6' katsayısı fiziksel değildi
        ve teorik Isp'yi gerçek Isp'nin altına düşürüyordu.

        chamber_pressure_bar verilirse CF_ideal o basınçta değerlendirilir
        (örn. yanma boyunca ortalama basınç); verilmezse tasarım basıncı kullanılır.

        c* TEORİK değerdir: 'teorik Isp' kayıpsız referanstır, kullanıcının
        yanma verimi buraya UYGULANMAZ — kayıp dökümü zaten aynı kaybı
        combustion_losses kaleminde raporlar (çifte sayım yasağı).

        ÖH D21 a1 (P2B4-10) — SESSİZ KIRPMA KALDIRILDI. Satır eskiden
        ``Pe_Pc = min(max(Pe_Pc, 1e-6), 0.999)`` diyordu. Ortam basıncı
        hazne basıncına eşit ya da ondan büyükse (Pe/Pc >= 1) optimal
        genişleme diye bir şey YOKTUR: nozul akışı genişleyemez, Denk.
        3-30'un CF ifadesi tanımsızdır. Kırpma bunu 0,999'a bastırıp HER
        böyle motora AYNI sayıyı veriyordu. ÖLÇÜLDÜ (once.json/P2B4-10,
        bates D=100 L=500 core=30 APCP):
            Pc = 1,0 bar -> ham Pe/Pc = 1,0132 -> 4,725684670150419 s
            Pc = 0,5 bar -> ham Pe/Pc = 2,0265 -> 4,725684670150419 s
        yani iki FARKLI motor bit-aynı Isp alıyordu; kırpma girdiyi
        siliyordu ve ``theoretical_vs_actual_isp`` bloğunda kırpmayı
        bildiren tek bir alan bile yoktu. Artık kazanılmamış sayı
        yayımlanmaz: fonksiyon ``None`` döner ve çağıran alanı boş
        bırakıp gerekçesini künyeye yazar (aynı sözleşme sıvı motorda
        ``theoretical_isp`` / ``theoretical_isp_basis`` ile zaten
        yürürlükte). Alt kırpma (1e-6) korunur: o sonlu bir sayısal
        tabandır, aşırı-genişlemiş ama FİZİKSEL bir nozula karşılık
        gelir ve girdiyi silmez.

        Döndürür: float (kazanılmış teorik Isp, s) ya da None.
        """
        gamma = self.gamma
        P_ref = chamber_pressure_bar if (chamber_pressure_bar and chamber_pressure_bar > 0) else self.P_c
        # Optimal genişleme: Pe = Pa (ortam basıncı; kullanıcı irtifa/atm
        # basıncı verdiyse o kullanılır)
        Pe_Pc = getattr(self, 'ambient_pressure_bar', SEA_LEVEL_PRESSURE_BAR) / P_ref
        if not np.isfinite(Pe_Pc) or Pe_Pc >= 1.0:
            # Ortam >= hazne: optimal genişleme tanımsız. Sayı UYDURULMAZ.
            return None
        Pe_Pc = max(Pe_Pc, 1e-6)

        # V301/N-CEA-2 (K2): bileşimi bilinen iticide optimum C_F NASA
        # CEA'nın o basınçtaki kayan denge genişlemesidir (P_e = P_a). CEA
        # o basınçta lüleyi çözemezse tasarım noktasının çapalı eşdeğer
        # bağıntısı (γ_n, κ) kullanılır; o da yoksa tek-γ (beyanlı uyarı
        # ``warn.solid.cea_nozzle_unavailable`` _cea_nozzle_state'te).
        if self._cea_active():
            sol = self._cea_point(P_ref, Pe_Pc * P_ref)
            lule = sol.get('nozzle') if sol.get('status') == 'available' \
                else None
            if lule is not None:
                return float(float(lule['cf_optimum'])
                             * self._c_star_theoretical() / self.g0)
            return float(self._cf_momentum_term(Pe_Pc)
                         * self._c_star_theoretical() / self.g0)

        gamma_term = 2 * gamma**2 / (gamma - 1)
        stagnation_term = (2 / (gamma + 1)) ** ((gamma + 1) / (gamma - 1))
        expansion_term = 1 - Pe_Pc ** ((gamma - 1) / gamma)
        CF_ideal = np.sqrt(gamma_term * stagnation_term * expansion_term)

        return float(CF_ideal * self._c_star_theoretical() / self.g0)

    def _analyze_burn_rate_consistency(self, curve):
        """Analyze burn rate consistency"""
        burn_rates = curve['burn_rate']
        consistency = 100 - (np.std(burn_rates) / np.mean(burn_rates) * 100)
        return max(0, min(100, consistency))
    
    def _calculate_erosive_effects(self, curve):
        """Erozif yanmanın koşuda FİİLEN uygulanan büyüklüğü (F067 düzeltmesi).

        ESKİ KOD (yanlış):
            'erosive_enhancement_percent': min(25, mass_flux / 100 * 5)
            'port_diameter_effect': 'Moderate'
        Bu doğrunun motorun kendi erozif modeliyle hiçbir ilgisi yoktu ve
        kaynağı da yoktu: G = 1000 kg/m²s'de '%25 artış' raporluyordu, oysa
        çözücünün fiilen uyguladığı artış aynı koşulda +%3.31 (yakıt tablosu
        k = 0.0136) ya da +%0.09 (UI varsayılanı k = 0.0002) idi — kullanıcıya
        gösterilen sayı hesaba gireninin 7.5 ile 275 katıydı ve G > 500'ün
        her yerinde 25 tavanına yapışıyordu. 'Moderate' de hiçbir hesaba
        dayanmayan sabit metindi.

        Yeni rapor doğrudan çözücünün sakladığı serilerden okunur
        (_erosive_factor: burn_rate ile TEK ve AYNI fonksiyon).
        """
        n = len(curve.get('time', []))
        factors = np.asarray(curve.get('erosive_factor', []), dtype=float)
        fluxes = np.asarray(curve.get('mass_flux', []), dtype=float)
        if n == 0 or factors.size == 0:
            return {
                'mass_flux_kg_m2s': 0.0,
                'erosive_enhancement_percent': 0.0,
                'model_applied': False,
            }

        # Kalem 26 (P3): port_ratio_end eskiden
        #   (D_core + 2*(D_chamber - D_core)/2) / D_chamber
        # idi — bu ifade cebirsel olarak HER motorda tam 1.0'dır, yani
        # 'port_diameter_factor_final' bir hesap değil sabitti. Gerçek son
        # port çapı çözücünün kendi gerileme serisinde duruyor: A_port(t).
        # Eşdeğer çap D = sqrt(4A/pi) ile ifade çözümün sonucuna bağlanır
        # (yıldız/finocyl gibi dairesel olmayan portlarda da tanımlıdır).
        port_ratio_0 = self.D_core / self.D_chamber
        port_areas = np.asarray(curve.get('port_area', []), dtype=float)
        port_areas = port_areas[np.isfinite(port_areas) & (port_areas > 0)]
        if port_areas.size:
            d_port_end = float(np.sqrt(4.0 * port_areas[-1] / np.pi))
            port_ratio_end = min(1.0, d_port_end / self.D_chamber)
            port_ratio_end_basis = (
                'equivalent final port diameter sqrt(4*A_port/pi) from the '
                'solver regression series')
        else:
            # Seri yoksa sayı UYDURULMAZ: başlangıç oranına düşmek yerine
            # alan boş bırakılır (aşağıda None olarak yayımlanır).
            port_ratio_end = None
            port_ratio_end_basis = (
                'NOT_MODELLED: the solver produced no port-area series')
        return {
            # Akı, çözücünün kullandığı GERÇEK port akış kesitinden gelir
            # (eski kod end-burner'da bile π(D_core/2)² kullanıyordu).
            'mass_flux_kg_m2s': float(fluxes[0]) if fluxes.size else 0.0,
            'mass_flux_max_kg_m2s': (float(np.nanmax(fluxes))
                                     if fluxes.size else 0.0),
            'mass_flux_basis': 'm_dot / port flow area (solver value)',
            # Uygulanan artış: (r/r0 - 1)*100
            'erosive_enhancement_percent': float((factors[0] - 1.0) * 100.0),
            'erosive_enhancement_max_percent': float(
                (np.nanmax(factors) - 1.0) * 100.0),
            'erosive_enhancement_mean_percent': float(
                (np.nanmean(factors) - 1.0) * 100.0),
            'erosive_threshold_kg_m2s': EROSIVE_THRESHOLD_KG_M2S,
            # v2.6.26 — SABİT ÇIKTI BEYANI. Eşik motordan hesaplanmaz; ayrıca
            # artık çözücüyle TEK sabiti paylaşır (eskiden iki ayrı 100.0).
            'erosive_threshold_kg_m2s_basis': (
                'model constant, not computed from this design: the port '
                'mass flux below which no erosive burning is applied '
                '(Summerfield-type threshold, Sutton & Biblarz 9th ed. '
                'Ch.12). This is the SAME constant the burn-rate solver '
                'uses, so the reported threshold cannot drift away from the '
                'one that actually shaped the burn. Compare it with '
                'mass_flux_max_kg_m2s to see whether your motor reaches it.'),
            'erosive_coefficient_k': float(self.erosive_burning_coeff),
            # ÖH D15 (P2B1-02): sayının NEREDEN geldiği yayımlanır — tablo mu,
            # kullanıcının beyan ettiği form değeri mi, yoksa uygulanmayan bir
            # form varsayılanı mı olduğu buradan okunur.
            'erosive_coefficient_k_source': str(getattr(
                self, 'erosive_coefficient_source', 'propellant table')),
            'erosive_exponent': float(getattr(self, 'erosive_exponent', 0.8)),
            # 'Moderate' sabit metni yerine hesaplanmış geometrik çarpan
            'port_diameter_factor_initial': float(
                max(port_ratio_0, 0.05) ** -0.2),
            'port_diameter_factor_final': (
                float(max(port_ratio_end, 0.05) ** -0.2)
                if port_ratio_end is not None else None),
            'port_diameter_ratio_final': (float(port_ratio_end)
                                          if port_ratio_end is not None
                                          else None),
            'port_diameter_ratio_final_basis': port_ratio_end_basis,
            'port_diameter_basis': '(D_port/D_chamber)^-0.2 (reduced L-R proxy)',
            'model_applied': True,
            'model_limitation': (
                'Reduced Lenoir-Robillard proxy: published erosive data show '
                'r/r0 ~ 1.2-2.0 at G ~ 1000-2000 kg/m2s, so this proxy '
                'UNDERPREDICTS the magnitude; k requires static-fire '
                'calibration.'),
        }
    
    def _grain_mechanics(self):
        """Seçili yakıtın mekanik özellikleri (SOLID_GRAIN_MECHANICS).

        v2.6.26 (K4): eskiden tanınmayan her yakıt SESSİZCE HTPB kompozit
        kaydına düşüyordu. HTPB elastomerdir (E = 6 MPa, uzama %35), dökme
        şeker yakıtı gevrektir (E = 1000 MPa, uzama %2) — aynı KNDX motoru
        için gerinim emniyet katsayısı 11.7 ('Low' risk) yerine 0.91 ('High'
        risk) çıkar. Bu, ateşlenecek bir grain hakkında verilebilecek en
        tehlikeli yanlış karardır.

        Sıra: yakıtın kendi kaydı -> aynı ailenin kaydı (beyan edilir) ->
        jenerik HTPB varsayımı (uyarı ile beyan edilir).
        """
        mech, source = _family_lookup(self.propellant_type,
                                      SOLID_GRAIN_MECHANICS)
        if mech is None:
            if not getattr(self, '_grain_mech_fallback_warned', False):
                self._grain_mech_fallback_warned = True
                self.design_warnings.append(dict(_w(
                    'warn.solid.grain_mechanics_fallback', 'warning',
                    propellant=str(self.propellant_type)),
                    fallback=("No grain mechanical record (modulus, Poisson "
                              "ratio, strain capability) exists for "
                              "'{propellant}'. The generic HTPB composite "
                              "band was used, so the grain strain margin and "
                              "crack risk below describe an elastomeric "
                              "binder, not your propellant.")))
            return dict(SOLID_GRAIN_MECHANICS_DEFAULT,
                        inherited_from='generic HTPB composite band')
        if source != str(self.propellant_type or '').strip().lower():
            return dict(mech, inherited_from=source)
        return mech

    def _grain_support(self):
        """Tane yerleşimi (V301/S1-6): ('case_bonded'|'cartridge_loaded', kaynak).

        Alan gelmediyse varsayılan gövdeye yapıştırılmış tanedir ve kaynağı
        'default (not supplied)' diye yayımlanır. Tanınmayan değer sessizce
        varsayılana DÜŞMEZ: ``rejected_inputs`` kaydına girer ve
        ``/calculate_solid`` hesaptan sonraki kapıda 422 verir.
        """
        ham = self.overrides.get('grain_support')
        if ham is None or (isinstance(ham, str) and not ham.strip()):
            return GRAIN_SUPPORT_DEFAULT, 'default (not supplied)'
        deger = str(ham).strip().lower() if isinstance(ham, str) else None
        if deger in GRAIN_SUPPORT_OPTIONS:
            return deger, 'user input'
        self._reject_input(
            'grain_support', ham,
            'grain support must be one of: ' + ', '.join(GRAIN_SUPPORT_OPTIONS),
            code='unknown_option')
        for kayit in self.rejected_inputs:
            if kayit.get('field') == 'grain_support':
                kayit['accepted_values'] = list(GRAIN_SUPPORT_OPTIONS)
        return GRAIN_SUPPORT_DEFAULT, 'default (submitted value rejected)'

    def _tane_gerinim_uyarisi(self, grain):
        """V301/FİZİK-2 (kalem 10) — tane gerinimi kapasiteyi aşıyorsa adlı uyarı.

        Model sonucu (gerinim SF < 1) ekranda "Çatlak riski Yüksek" diye
        duruyor ama hiçbir uyarı üretilmiyordu. Önem 'warning': gerinim
        kapasitesi literatür bandından bir GİRDİDİR (grain_property_source),
        bu partide ölçülmemiştir. Yalnız bir kez eklenir (kimlik: kod).
        """
        sf = grain.get('strain_safety_factor') if isinstance(grain, dict) \
            else None
        if not (isinstance(sf, (int, float)) and np.isfinite(sf) and sf < 1.0):
            return
        kod = 'warn.solid.grain_strain_exceeds_capability'
        if any(isinstance(w, dict) and w.get('code') == kod
               for w in self.design_warnings):
            return
        # Kod literal yazılır: yayın kapısı (test_v262_release_gate::
        # test_no_raw_warnings_left_in_engines) _w'nin ilk argümanını
        # sözdizimiyle 'warn.' dizesi olarak denetler.
        self.design_warnings.append(_w(
            'warn.solid.grain_strain_exceeds_capability', 'warning',
            strain_percent=round(float(grain['bore_strain_percent']), 3),
            capability_percent=round(
                float(grain['strain_capability_percent']), 3),
            safety_factor=round(float(sf), 3)))

    def _calculate_grain_structural(self):
        """Case-bonded grain gerilme/gerinim analizi — GERÇEK elastisite.

        DENETİM DÜZELTMESİ (2026-07-19). Eski kod:
            thermal_stress = 2.5           # MPa, sabit
            pressure_stress = self.P_c*0.1 # 'basitleştirilmiş'
        Yakıtın modülü, Poisson oranı, termal genleşmesi, kürleme sıcaklığı ve
        grain geometrisi hiç girmiyordu; star grain ile BATES aynı sayıyı
        veriyordu.

        Yeni model — eksenel simetrik, düzlem-şekil değiştirme (plane strain)
        içi boş silindir; iç yarıçap a (port), dış yarıçap b (kasa arayüzü):

            u(r) = D*r + C2/r
            sigma_r = K*[D - C2*(1-2nu)/r^2] - T0
            sigma_t = K*[D + C2*(1-2nu)/r^2] - T0
            K  = E/((1+nu)(1-2nu)),   T0 = E*alpha*dT/(1-2nu)

        Sınır koşulları:
            sigma_r(a) = -P_c                      (port basıncı)
            u(b)       = u_kasa = P_c*b^2/(E_k*t)  (ince cidarlı kasanın
                                                    basınç altındaki radyal
                                                    genişlemesi; kasa
                                                    malzemesi ve kalınlığı
                                                    BURADAN girer)
        dT = T_depolama - T_kurleme  (kürlemeden soğuma; negatif → port
        yüzeyinde ÇEKME).

        Kaynak: Timoshenko & Goodier "Theory of Elasticity" (kalın cidarlı
        silindir + üniform sıcaklık); NASA SP-8073 case-bonded grain yapısal
        bütünlük kriterleri (kabul ölçütü GERİNİM kabiliyetidir, gerilme değil).
        """
        mech = self._grain_mechanics()
        E = float(mech['elastic_modulus_pa'])
        nu = float(mech['poisson_ratio'])
        alpha = float(mech['thermal_expansion_1k'])
        T_cure = float(mech['cure_temperature_k'])
        strain_capability = float(mech['strain_capability'])

        a = max(self.D_core / 2.0, 1e-6)          # port yarıçapı
        b = max(self.D_chamber / 2.0, a * 1.001)  # kasa iç yarıçapı
        if self.grain_type == 'end_burner':
            # Sigara yanmasında merkezi port yok: ince bir teknolojik delik
            # yerine tam dolu silindir varsayılır (a -> 0 tekilliğini önlemek
            # için çapın binde biri).
            a = max(b / 1000.0, 1e-6)

        P = self.P_c * 1e5                        # Pa
        T_store = float(getattr(self, 'ambient_temperature',
                                SOLID_THERMAL['ambient_temperature_k']))
        dT = T_store - T_cure                     # kürlemeden soğuma (negatif)
        # V301/S1-6: kartuş yüklü tanede gövde büzülmeyi kısıtlamaz; serbest
        # cisimde üniform sıcaklık değişimi gerilme/gerinim üretmez (T0 = 0).
        # Basınç yükü aynı sınır koşuluyla (u(b) = u_kasa, sıkı geçme) çözülür.
        support, support_source = self._grain_support()
        if support == GRAIN_SUPPORT_CARTRIDGE:
            dT = 0.0

        one_m_2nu = 1.0 - 2.0 * nu
        K = E / ((1.0 + nu) * one_m_2nu)
        T0 = E * alpha * dT / one_m_2nu

        # Kasanın basınç altındaki radyal genişlemesi (ince cidar hoop):
        #   sigma_hoop = P*b/t ;  u = sigma_hoop*b/E_kasa = P*b^2/(E_kasa*t)
        case_material, _sigma_y, _sf, t_case = self._case_design()
        try:
            from hrma.data.materials_db import get_material
            E_case = float(get_material(case_material)['elastic_modulus'])
        except Exception:
            E_case = SOLID_THERMAL['fallback_case_elastic_modulus_pa']
        u_case = P * b ** 2 / (E_case * max(t_case, 1e-6))

        ratio2 = (b / a) ** 2
        denom = K * (1.0 + one_m_2nu * ratio2)
        D = (T0 - P + K * one_m_2nu * b * u_case / a ** 2) / denom
        C2 = b * u_case - D * b ** 2

        sigma_t_bore = K * (D + C2 * one_m_2nu / a ** 2) - T0
        sigma_r_bore = K * (D - C2 * one_m_2nu / a ** 2) - T0
        sigma_z_bore = nu * (sigma_r_bore + sigma_t_bore) - E * alpha * dT
        von_mises = np.sqrt(0.5 * ((sigma_r_bore - sigma_t_bore) ** 2
                                   + (sigma_t_bore - sigma_z_bore) ** 2
                                   + (sigma_z_bore - sigma_r_bore) ** 2))

        # Port yüzeyi hoop gerinimi — NASA SP-8073 kabul ölçütü
        bore_strain = (D * a + C2 / a) / a
        strain_margin = (strain_capability / abs(bore_strain)
                         if abs(bore_strain) > 1e-12 else float('inf'))

        # Star/wagon köşe gerilme yığılması: keskin iç köşe, düz silindirik
        # porta göre gerilmeyi büyütür. Kt geometriden değil tipten gelir;
        # bu yüzden AÇIKÇA beyan edilir (aşağıdaki 'model_note').
        kt = GRAIN_STRESS_CONCENTRATION.get(self.grain_type, 1.0)
        max_stress_pa = von_mises * kt
        bore_strain_kt = bore_strain * kt
        strain_margin_kt = (strain_capability / abs(bore_strain_kt)
                            if abs(bore_strain_kt) > 1e-12 else float('inf'))

        if strain_margin_kt >= 2.0:
            crack_risk = 'Low'
        elif strain_margin_kt >= 1.0:
            crack_risk = 'Medium'
        else:
            crack_risk = 'High'

        # Termal uyum: yalnız kürleme soğumasının port gerinimi
        D_th = T0 / denom
        C2_th = -D_th * b ** 2
        thermal_bore_strain = (D_th * a + C2_th / a) / a
        thermal_ratio = abs(thermal_bore_strain) / strain_capability
        if thermal_ratio < 0.25:
            thermal_compat = 'Good'
        elif thermal_ratio < 0.6:
            thermal_compat = 'Marginal'
        else:
            thermal_compat = 'Poor'

        return {
            'max_grain_stress_mpa': float(max_stress_pa / 1e6),
            'bore_hoop_stress_mpa': float(sigma_t_bore * kt / 1e6),
            'bore_radial_stress_mpa': float(sigma_r_bore * kt / 1e6),
            'thermal_only_bore_strain_percent': float(thermal_bore_strain * 100),
            'bore_strain_percent': float(bore_strain_kt * 100),
            'strain_capability_percent': float(strain_capability * 100),
            'strain_safety_factor': float(strain_margin_kt),
            'structural_efficiency': float(
                max(0.0, min(100.0, 100.0 * (1.0 - abs(bore_strain_kt)
                                             / strain_capability)))),
            'crack_propagation_risk': crack_risk,
            'thermal_expansion_compatibility': thermal_compat,
            # V301/FİZİK-2 (kalem 10): üç satırın DAYANAĞI. ÖLÇÜLDÜ (örnek
            # KNDX, fizik-2/k10_tane_yapisal_olcum.txt): port gerinimi %2,21
            # ⟷ gerinim kapasitesi %2,0 → gerinim SF 0,906; ekran "Yapısal
            # Verim %0 · Çatlak riski Yüksek · Isıl uyum Zayıf" basıyor,
            # dayanağı yoktu ve hiçbir uyarı çıkmıyordu. Sınıf bantları
            # KAYNAKSIZ HRMA seçimidir (kaynaklı kabul ölçütü değildir).
            'thermal_bore_strain_ratio': float(thermal_ratio),
            'crack_propagation_risk_basis': (
                'class of the strain safety factor (strain capability / '
                'bore hoop strain with the stress concentration factor): '
                '>= 2 Low, >= 1 Medium, < 1 High - the band edges are an '
                'unsourced HRMA choice, not a sourced acceptance criterion'),
            'thermal_expansion_compatibility_basis': (
                'class of the cure-cooldown bore strain over the strain '
                'capability (thermal_bore_strain_ratio): < 0.25 Good, '
                '< 0.6 Marginal, else Poor - the band edges are an '
                'unsourced HRMA choice'),
            'structural_efficiency_basis': (
                '100 x (1 - bore strain / strain capability), clipped to '
                '[0, 100]: the unused share of the strain capability, not '
                'an efficiency of the structure; 0 means the bore strain '
                'reaches or exceeds the capability'),
            'stress_concentration_factor': kt,
            'cure_temperature_k': T_cure,
            'storage_temperature_k': T_store,
            'grain_elastic_modulus_mpa': E / 1e6,
            'grain_poisson_ratio': nu,
            'grain_thermal_expansion_1k': alpha,
            'grain_property_source': mech['source'],
            # v2.6.26 — SABİT ÇIKTI BEYANI. Aşağıdaki dört alan (kürleme
            # sıcaklığı, modül, Poisson oranı, termal genleşme) bu modelin
            # GİRDİSİDİR, sonucu değildir: SOLID_GRAIN_MECHANICS kaydından
            # gelirler ve motor girdileri değişince değişmezler. Kaydın
            # künyesi 'grain_property_source' alanındadır.
            'grain_property_basis': (
                'the grain mechanical properties used by this model - cure '
                'temperature, grain elastic modulus, grain poisson ratio and '
                'grain thermal expansion - are read from the propellant '
                'record in SOLID_GRAIN_MECHANICS (see grain_property_source '
                'for the citation of that record). They are literature-band '
                'INPUTS to the plane-strain solution, NOT computed from your '
                'design and NOT measured on your batch, so they stay the same '
                'when you change geometry or pressure. Measure your own '
                'propellant before using the strain margin as an acceptance '
                'criterion.'),
            # Kayıt bu yakıta AİT değilse hangi yakıttan devralındığı
            # burada açıkça yazar (sessiz devralma yasak).
            'grain_property_inherited_from': mech.get('inherited_from'),
            'propellant_type': str(self.propellant_type),
            # V301/S1-6: yerleşim artık girdidir (grain_support); eski
            # "this solver has no input for that configuration" beyanı kalktı.
            'grain_support': support,
            'grain_support_source': support_source,
            'bonding_assumption': GRAIN_SUPPORT_BASIS[support],
            'model_note': (
                'Plane-strain elasticity of a hollow cylinder supported by '
                'the case (Timoshenko & Goodier) with bore pressure and, for '
                'a case-bonded grain, the case-restrained cure shrinkage; '
                'acceptance is judged on bore strain against the propellant '
                'strain capability (NASA SP-8073). Star and wagon-wheel ports '
                'use a nominal stress-concentration factor of '
                f'{kt:.1f} because the corner radius is not resolved. '
                'Propellant mechanical properties are literature-band values, '
                'not measurements of a specific batch.'),
        }

    def _calculate_grain_stress(self):
        """Grain'deki en büyük eşdeğer gerilme [MPa] (geriye uyumlu sarmalayıcı)."""
        return self._calculate_grain_structural()['max_grain_stress_mpa']
    
    def _calculate_heat_flux(self):
        """Boğaz konvektif ısı akısı [kW/m²] — Bartz (1957) korelasyonu.

        DENETİM DÜZELTMESİ (#1633): Eski placeholder (T_c·0.002 kW/m²) gerçek
        değerin ~1000× altındaydı. Artık heat_transfer_analysis modülündeki
        MEVCUT Bartz implementasyonu (Sutton & Biblarz 9. baskı, Eş. 8-22)
        boğaz istasyonunda (M=1, A_t/A=1) çağrılıyor — yeni fizik yazılmadı,
        doğrulanmış olan yeniden kullanıldı:
            h_g = (0.026/D_t^0.2)·(μ^0.2·cp/Pr^0.6)·(Pc/c*)^0.8·(D_t/R_c)^0.1·σ
            q   = h_g·(T_aw − T_w),  T_aw = kurtarma sıcaklığı (r = Pr^{1/3})
        Duvar sıcaklığı T_w = 700 K (soğutmasız çelik kasa, yanma-ortası
        temsili tasarım değeri; T_aw ≈ 0.9·T_c ≫ T_w olduğundan q, T_w
        seçimine zayıf duyarlıdır — 300↔1000 K arası fark ~%15).
        Boğaz eğrilik yarıçapı R_c = 1.5·r_t (Bartz'ın standart varsayımı,
        analyzer._resolve_throat_conditions ile aynı).

        v2.6.27 (B6-4): h_g ve T_aw burada hesaplanıp SADECE çarpımları
        döndürülüyordu; ablatif astar boyutlandırması ikisini de istediği
        için (yüzey enerji dengesi) hesap ``_throat_gas_side``a taşındı.
        Bu metot artık o TEK kaynağın türevidir — aynı istasyon için iki
        ayrı Bartz çağrısı yapılmaz.
        """
        h_g, T_aw, _cp = self._throat_gas_side()
        T_wall = SOLID_THERMAL['bartz_reference_wall_temp_k']
        q = h_g * (T_aw - T_wall)  # W/m²
        return q / 1000.0  # kW/m²

    def _bartz_gas_gamma(self):
        """Bartz gaz özelliklerinin (donmuş cp, Pr) türetildiği gamma.

        Seçim kuralının kendisi ``_frozen_gas_gamma``dadır (TEK nokta); bu ad
        Bartz zincirinin çağrı noktalarını okunur tutar.
        """
        return self._frozen_gas_gamma()

    def _frozen_gas_gamma(self):
        """"Donmuş" gaz formüllerine giren gamma — seçim kuralının TEK noktası.

        Tüketiciler (ÖH KİTAP p1b, B11; seçenek F ve 2. tur, karar §28-36
        Ş-2 A):
          * Bartz zinciri (``_bartz_gas_gamma``): boğaz/hazne akısı, lüle
            malzeme marjı, yayımlanan boğaz kurtarma sıcaklığı;
          * ``_calculate_thermal_analysis``: tepkime entalpisinin cp =
            γR/(γ−1) türetimi (ısı salım gücü ve termal verim onu okur);
          * ``_two_phase_loss_report``: iki faz modülünün gaz-yalnız gamma
            girdisi (Sutton Eş. 3-35..3-39, cp = γR/(γ−1)).
        Genleşme (c* özdeşliği, C_F, ε, jet hızı, statik sıcaklıklar) denge
        gamma'sıyla (``self.gamma``) kalır.

        ÖH KİTAP p1b (B11, seçenek F, ana model 12 Eki 2026). Kayıttaki tek
        gamma iki iş görüyordu: genleşme (c* özdeşliği, C_F, ε) ve Bartz gaz
        özellikleri (``HeatTransferAnalyzer._get_gas_properties`` cp =
        γR/(γ−1), Pr = 4γ/(9γ−5) — DONMUŞ formüller). CEA'nın denge γ_s'si
        (APCP 1,1338) reaksiyon ısısını içerir; donmuş formüle girince cp'yi
        ×1,41 şişirir ve boğaz akısını +%27 büyütür (rapor §3.1). Bu yüzden
        kayıt ölçülmüş bir donmuş oda gamma'sı taşıyorsa
        (``gamma_frozen_chamber``, CEA donmuş GAMMAs) Bartz zinciri onu
        kullanır; genleşme denge gamma'sıyla kalır.

        Donmuş değer yalnız ait olduğu kayda uygulanır: motorun gamma'sı
        kaydın denge gamma'sından farklıysa (kullanıcı gamma alanını başka
        bir karışım için ezdi) kaydın donmuş değeri o gaza ait sayılamaz;
        zincir bugünkü gibi motorun gamma'sını kullanır. Kayıtta alan yoksa
        (None) dönen nesne ``self.gamma``nın kendisidir — öteki bütün
        iticiler bit-özdeş kalır.

        Fail-closed: kullanılacak donmuş değer sonlu ve 1'den büyük
        olmalıdır (cp = γR/(γ−1) tanımı); değilse sayı üretilmez,
        ValueError. Katalog yüklemesi değeri zaten bantta denetler; bu
        ikinci kapı motor tarafına elle yazılmış bir değere karşıdır.
        """
        frozen = getattr(self, 'gamma_frozen_chamber', None)
        ref = getattr(self, '_gamma_frozen_equilibrium_ref', None)
        if (frozen is not None and ref is not None
                and self._matches_record_value(self.gamma, ref)):
            frozen = float(frozen)
            if not (np.isfinite(frozen) and frozen > 1.0):
                raise ValueError(
                    'gamma_frozen_chamber must be finite and > 1, got '
                    f'{frozen!r}')
            return frozen
        return self.gamma

    @staticmethod
    def _matches_record_value(value, ref):
        """Motorun değeri kaydın değeri mi — göreli 1e-12 (yalnız kayan nokta
        gürültüsü; ezilmiş bir değer bundan büyük fark taşır).

        TEK pay: donmuş gamma kuralı (``_frozen_gas_gamma``) ve iki faz
        modülünün yoğuşkan-faz kapısı (``_two_phase_loss_report``, ÖH KİTAP
        p1b 3. tur, karar §28-47) aynı eşleşme tanımını okur.
        """
        return abs(float(value) - float(ref)) <= 1e-12 * abs(float(ref))

    def _throat_gas_side(self):
        """(h_g [W/m²K], T_aw [K], cp [J/kg·K]) BOĞAZ istasyonunda — Bartz.

        ``_chamber_gas_side``ın boğaz eşleniği. İkisi de aynı doğrulanmış
        HeatTransferAnalyzer implementasyonunu çağırır; fark istasyondur
        (boğazda M=1 ve A_t/A=1, haznede alan oranı ve düşük Mach).

        Neden ayrı metot: ısı akısı (``_calculate_heat_flux``) ile ablatif
        astar boyutlandırması AYNI iki sayıya ihtiyaç duyuyor. Akı zaten
        h_g·(T_aw−T_w) çarpımıydı; astarın yüzey enerji dengesi ise h_g ve
        T_aw'yi AYRI AYRI ister (q_net = blokaj·h_g·(T_aw−T_s) − ışıma).
        Çarpımdan geriye bölerek h_g kurtarmak yerine kaynak tek yerde
        tutulur — bir istasyonun iki farklı h_g'si olamaz.

        cp, Bartz zincirinin KENDİ gaz özelliklerinden gelir (üfleme
        parametresi B' = f·ṡ·ρ·c_p/h_g bu c_p ile kurulmalıdır: h'yi üreten
        c_p ile B'yi bölen c_p farklı olursa ρₑuₑC_H tanımı bozulur).
        """
        from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
        analyzer = HeatTransferAnalyzer()
        # B11 seçenek F: gaz özellikleri _bartz_gas_gamma'dan (donmuş oda γ).
        gas = analyzer._get_gas_properties(
            {'gamma': self._bartz_gas_gamma(),
             'molecular_weight': getattr(self, 'mw_exhaust', 26.0)},
            self.T_c,
        )
        d_throat = self._estimate_throat_diameter()  # m
        rc_over_dt = max((1.5 * d_throat / 2.0) / d_throat, 0.25)  # = 0.75
        # Temsili soğutmasız çelik duvar — hazne istasyonuyla AYNI referans
        # (bkz. _calculate_heat_flux docstring: q, T_w seçimine zayıf duyarlı).
        T_wall = SOLID_THERMAL['bartz_reference_wall_temp_k']
        h_g = analyzer._bartz_coefficient(
            throat_diameter=d_throat,
            chamber_pressure=self.P_c * 1e5,   # bar → Pa
            c_star=self.c_star,
            gas=gas,
            chamber_temperature=self.T_c,
            wall_temperature=T_wall,
            rc_over_dt=rc_over_dt,
            area_ratio_local=1.0,
            mach_local=1.0,
        )  # W/(m²·K)
        T_aw = analyzer._adiabatic_wall_temperature(self.T_c, gas, mach_local=1.0)
        return float(h_g), float(T_aw), float(gas['gas_cp'])

    def _chamber_gas_side(self):
        """(h_g [W/m²K], T_aw [K], cp [J/kg·K]) hazne cidarında — Bartz.

        _calculate_heat_flux boğaz istasyonunu kullanır; kasa ısınması hazne
        cidarındaki (çok daha düşük) akıyla belirlenir. Aynı doğrulanmış
        HeatTransferAnalyzer implementasyonu, hazne alan oranı ve düşük Mach
        ile çağrılır — yeni fizik yazılmaz. cp için bkz. _throat_gas_side
        docstring'i (B' aynı c_p ile kurulmak zorunda).
        """
        from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
        analyzer = HeatTransferAnalyzer()
        # B11 seçenek F: gaz özellikleri _bartz_gas_gamma'dan (donmuş oda γ).
        gas = analyzer._get_gas_properties(
            {'gamma': self._bartz_gas_gamma(),
             'molecular_weight': getattr(self, 'mw_exhaust', 26.0)},
            self.T_c,
        )
        d_throat = self._estimate_throat_diameter()
        # A/A_t (>= 1) — Mach çözümü bu konvansiyonu bekler
        area_ratio_chamber = max((self.D_chamber / d_throat) ** 2, 1.0)
        mach_chamber = analyzer._mach_from_area_ratio(
            area_ratio_chamber, gas['gamma'], supersonic=False)
        T_wall_ref = SOLID_THERMAL['bartz_reference_wall_temp_k']
        h_g = analyzer._bartz_coefficient(
            throat_diameter=d_throat,
            chamber_pressure=self.P_c * 1e5,
            c_star=self.c_star,
            gas=gas,
            chamber_temperature=self.T_c,
            wall_temperature=T_wall_ref,
            rc_over_dt=max((1.5 * d_throat / 2.0) / d_throat, 0.25),
            # Bartz A_t/A bekler (boğazda 1.0) — hazne istasyonunda 1/eps
            area_ratio_local=1.0 / area_ratio_chamber,
            mach_local=mach_chamber,
        )
        T_aw = analyzer._adiabatic_wall_temperature(
            self.T_c, gas, mach_local=mach_chamber)
        return float(h_g), float(T_aw), float(gas['gas_cp'])

    def _bartz_gas_properties(self):
        """Bartz zincirinin gaz çifti (γ, M) — adıyla ve kaynağıyla künye.

        ÖH KİTAP p1b 3. tur (karar §28-47, Ş2-1 / D-F3; §28-36 Ş-7). Motorun
        kendi Bartz zinciri (``_throat_gas_side``, ``_chamber_gas_side``) gaz
        özelliklerini ``_bartz_gas_gamma()`` ve ``mw_exhaust``ten kurar;
        yanıtın üst düzey ``gamma``sı ise GENLEŞME (denge) gamma'sıdır. Kayıt
        ölçülmüş bir donmuş oda gamma'sı taşıdığında ikisi ayrışır ve eksenel
        duvar profili (``wall_profile_inputs_from_motor`` →
        ``/api/analysis/wall-profile``) yayımlanan gamma'yı Bartz'a taşırsa
        boğaz akısı motorun kendi akısından sapar (2. tur denetim ölçümü:
        APCP D120 Pc 55, profil/motor boğaz h_g oranı 0,941 → 1,225; profil
        q +%25, motor −%2,78).

        ``axial_profile_gas`` YALNIZ iki gaz ayrıştığında doludur: profil
        Bartz'ı motorla AYNI (γ, M) çiftiyle kurar. R, c* özdeşliğinden
        (Eş. 3-32) türetilmez — özdeşlik genleşme gamma'sına aittir, donmuş
        gamma ile türetilen R ≈ +%3,3 kayardı; R = R_u/M, M motorun kendi
        Bartz zincirinin M'si. Ayrışmadığında None: profil yayımlanan
        gamma'yı okur ve R'yi c* özdeşliğinden türetir (önceki yol; donmuş
        değeri olmayan bütün katılar bit-özdeş).
        """
        gamma_b = float(self._bartz_gas_gamma())
        gamma_e = float(self.gamma)
        mw = float(self.mw_exhaust)
        ayrisik = gamma_b != gamma_e
        return {
            'gamma': gamma_b,
            'gamma_source': ('gamma_frozen_chamber' if ayrisik else 'gamma'),
            'gamma_basis': (
                "propellant record's frozen-composition chamber gamma "
                '(NASA CEA GAMMAs, field gamma_frozen_chamber): the Bartz '
                'gas properties (frozen cp = gamma*R/(gamma-1), '
                'Pr = 4*gamma/(9*gamma-5)) are built from it, while the '
                'expansion (c* identity, thrust coefficient, area ratio) '
                'uses expansion_gamma'
                if ayrisik else
                'the engine gamma: no measured frozen chamber gamma applies '
                'to this gas, so the Bartz gas properties and the expansion '
                'use the same value'),
            'molecular_weight': mw,
            'molecular_weight_unit': 'g/mol',
            'molecular_weight_source': (
                'exhaust molecular weight the solver uses (mw_exhaust: the '
                "propellant record's value, or the user's override when one "
                'was entered), the value the thrust coefficient and the '
                'nozzle exit state use'),
            'expansion_gamma': gamma_e,
            'axial_profile_gas': ({'gamma': gamma_b, 'molecular_weight': mw}
                                  if ayrisik else None),
            '_basis': (
                'gas pair of this solver\'s Bartz chain (HeatTransferAnalyzer'
                '._get_gas_properties called with this gamma and molecular '
                'weight). axial_profile_gas is set only when the Bartz gamma '
                'differs from the published expansion gamma: the axial wall '
                'profile built from this result must then use this pair '
                '(R = R_u/M), not the published gamma and a gas constant '
                'derived from the c* identity, which belongs to the '
                'expansion gamma; null means the published gamma is the '
                'Bartz gamma'),
        }

    def _build_heat_transfer_analysis(self):
        """Güverte ısı haritasının okuduğu şemayı yayımlar (OH-Z5-03).

        ÖLÇÜLEN KUSUR (kanıt: ``docs/scofield/raw/OH/D16/kati/a1/once.json``
        ``OH-Z5-03``): ``/calculate_solid`` yanıtında ``heat_transfer_analysis``
        bloğu HİÇ YOKTU (``heat_transfer_analysis_var: false``). Güvertenin
        ısı kapısı ``motor_viz3d.js:1843``'te şudur::

            heat = null;
            if (gas.throat_heat_flux) { heat = {...} }

        Blok olmayınca ``getHeatInfo()`` null döner ve ``motor_viz_deck.js``
        ısı düğmesini GİZLER — katı motorda ısı haritası bu yüzden
        ERİŞİLEMEZDİ (OH-Z3-03'ün katı ayağı). ``solid.html``in
        ``buildSolidVizData``'sı bloğu zaten KOŞULLU olarak geçiriyordu;
        eksik olan tek şey çözücünün onu yayımlamasıydı.

        Bu metot YENİ FİZİK HESABI YAPMAZ. Bütün sayılar bu sınıfın
        ZATEN doğrulanmış Bartz zincirinden gelir:

        ==========================  ==========================================
        yayımlanan alan             kaynak
        ==========================  ==========================================
        ``throat_heat_flux``        ``_calculate_heat_flux()`` (kW/m² -> W/m²)
        ``chamber_heat_flux``       ``_chamber_gas_side()`` h_g·(T_aw − T_ref)
        ``gas_side_coefficient_*``  aynı iki metodun h_g'si
        ``outer_temperature``       ``_calculate_case_temperature()`` (çözüm)
        ==========================  ==========================================

        FAIL-CLOSED, iki ayrı kapı:

        * Akılar çözülemez ya da fiziksel değilse blok ``NOT_MODELLED``
          döner ve ``throat_heat_flux`` KONMAZ — güverte düğmesi kapalı
          kalır, sahte ısı haritası çizilmez.
        * İÇ (gaz tarafı) cidar sıcaklığı YAYIMLANMAZ. Bartz zinciri iç
          cidarı çözmez; ``SOLID_THERMAL['bartz_reference_wall_temp_k']``
          bir TASARIM REFERANSIDIR (soğutmasız çelik kasa için temsili
          değer), ölçüm değildir. Sıvı motorun aynı kapısıyla (Z5-C5)
          birebir aynı ilke: varsayım, ısı haritasında ölçüm gibi
          gösterilemez. Referans değer ayrı ve ADI KONMUŞ bir alanda
          (``bartz_reference_wall_temperature_K``) taşınır.

        Returns:
            ``heat_transfer_analysis`` sözlüğü.
        """
        basis = (
            'republished from this solver\'s Bartz gas-side chain '
            '(HeatTransferAnalyzer, Sutton & Biblarz 9th ed. Eq. 8-22) '
            'evaluated at the throat (M=1) and at the chamber station; no '
            'separate heat-transfer solve runs here, only a kW/m^2 -> W/m^2 '
            'unit change and the schema the 3D deck reads')

        def _pozitif(x):
            try:
                v = float(x)
            except (TypeError, ValueError):
                return None
            return v if (np.isfinite(v) and v > 0) else None

        T_ref = float(SOLID_THERMAL['bartz_reference_wall_temp_k'])
        # ÖH KİTAP p1b 3. tur (§28-47 Ş2-1 / D-F3): Bartz gaz çiftinin künyesi
        # iki dalda da yayımlanır (akı çözülmese de gaz tanımlıdır).
        bartz_gaz = self._bartz_gas_properties()
        q_throat = None
        q_chamber = None
        h_throat = None
        h_chamber = None
        try:
            q_throat = _pozitif(self._calculate_heat_flux() * 1000.0)  # W/m²
            h_t, _T_aw_t, _cp_t = self._throat_gas_side()
            h_throat = _pozitif(h_t)
        except Exception:
            pass
        try:
            h_c, T_aw_c, _cp_c = self._chamber_gas_side()
            h_chamber = _pozitif(h_c)
            q_chamber = _pozitif(float(h_c) * (float(T_aw_c) - T_ref))
        except Exception:
            pass

        eksik = [ad for ad, deger in (('throat_heat_flux', q_throat),
                                      ('chamber_heat_flux', q_chamber))
                 if deger is None]
        if eksik:
            return {
                'status': 'NOT_MODELLED',
                '_basis': basis,
                'reason': (
                    'the deck heat map needs the Bartz chamber and throat '
                    'fluxes; missing or non-physical in this run: '
                    + ', '.join(eksik)),
                'gas_side_analysis': {},
                'wall_analysis': {},
                'bartz_gas_properties': bartz_gaz,
            }

        case_temperature = None
        try:
            case_temperature = _pozitif(self._calculate_case_temperature())
        except Exception:
            case_temperature = None

        wall_analysis = {
            # İÇ cidar ÇÖZÜLMEZ: Bartz referansı bir tasarım değeridir.
            'inner_temperature': None,
            'outer_temperature': case_temperature,
            'wall_temperature_solved': False,
            'wall_temperature_status': 'inner_not_solved',
            'wall_temperature_source': (
                'gas-side wall: Bartz reference value '
                'SOLID_THERMAL[\'bartz_reference_wall_temp_k\'] '
                '(%.0f K, design reference for an uncooled steel case), NOT '
                'a solved equilibrium; case (outer) temperature: solved by '
                '_calculate_case_temperature (lumped-capacitance transient '
                'through insulation + case)' % T_ref),
            'wall_temperature_withheld_reason': (
                'the solid chain evaluates Bartz AT a fixed reference wall '
                'temperature and never solves for it; publishing that '
                'reference as inner_temperature would show an assumption as '
                'a measurement'),
            'bartz_reference_wall_temperature_K': T_ref,
            'insulation_effectiveness_percent': self._insulation_effectiveness_percent(),
            'thermal_barrier_thickness_mm': float(
                self._thermal_barrier_thickness() * 1000.0),
        }

        return {
            'status': 'modelled',
            '_basis': basis,
            'source': 'solid_bartz_chain',
            'gas_side_analysis': {
                # W/m² — güvertenin okuduğu birim (sıvı/hibrit blokla aynı).
                'throat_heat_flux': q_throat,
                'chamber_heat_flux': q_chamber,
                'heat_flux_basis': (
                    '_calculate_heat_flux() at the throat (kW/m^2 -> W/m^2) '
                    'and h_g*(T_aw - T_ref) at the chamber station, both '
                    'from the same HeatTransferAnalyzer Bartz call chain'),
                'gas_side_coefficient_throat': h_throat,
                'gas_side_coefficient_chamber': h_chamber,
            },
            'wall_analysis': wall_analysis,
            'bartz_gas_properties': bartz_gaz,
            'cooling_analysis': {
                # Katı motorda aktif soğutma yoktur; kanal/soğutucu alanları
                # UYDURULMAZ, yalnız pasif korumanın kendi sayıları verilir.
                'cooling_type': 'passive (insulation + case heat sink)',
                'insulation_thickness_mm': float(
                    getattr(self, 'insulation_thickness_m', 0.0) * 1000.0),
                'liner_thickness_mm': float(
                    getattr(self, 'liner_thickness',
                            SOLID_INSULATION['thickness_m']) * 1000.0),
                'case_temperature_K': case_temperature,
            },
        }

    def _thermal_barrier_thickness(self):
        """Gaz ile kasa arasındaki TOPLAM yalıtım kalınlığı [m].

        İki katman seri bağlıdır: yalıtım (insulation_thickness — kasa iç
        çapını da büyüten radyal katman) ve liner (grain bağ katmanı).
        v2.6.26 (Y2): termal zincir yalnız liner'ı görüyordu; kullanıcı
        yalıtımı 3 -> 10 mm yaptığında kasa sıcaklığı ve yalıtım etkinliği
        HİÇ değişmiyordu, oysa aynı kalınlık kuru kütleye ve kasa çapına
        zaten giriyordu.
        """
        return (max(float(getattr(self, 'insulation_thickness_m', 0.0)), 0.0)
                + max(float(getattr(self, 'liner_thickness',
                                    SOLID_INSULATION['thickness_m'])), 0.0))

    def _insulation_resistance(self):
        """Yalıtım paketinin ısıl direnci [m²K/W] = (t_yalitim + t_liner)/k.

        Tek bir iletkenlik kullanılır: HRMA'nın yayımlanmış tek yalıtım
        malzeme kaydı (SOLID_INSULATION, EPDM/fenolik bandı). İki katman için
        AYRI iletkenlik uydurulmaz.
        """
        k_ins = SOLID_INSULATION['thermal_conductivity_w_mk']
        return self._thermal_barrier_thickness() / k_ins

    def _insulation_effectiveness_percent(self):
        """Yalıtımın gaz tarafı ısı yükünü kestiği oran [%].

        Seri direnç zinciri: R_gaz = 1/h_g, R_yalitim = t/k.
            etkinlik = R_yalitim / (R_gaz + R_yalitim) x 100
        Yalıtımsız (t=0) motorda 0 döner — sabit 94.8 değil.
        """
        try:
            h_g, _, _ = self._chamber_gas_side()
        except Exception:
            return 0.0
        if h_g <= 0:
            return 0.0
        r_gas = 1.0 / h_g
        r_ins = self._insulation_resistance()
        return float(100.0 * r_ins / (r_gas + r_ins))

    def _calculate_case_temperature(self, burn_time=None):
        """Yanma sonunda kasa sıcaklığı [K] — geçici (transient) çözüm.

        DENETİM DÜZELTMESİ (2026-07-19). Eski kod:
            return 298 + (self.T_c - 298) * 0.1   # 'Simplified heat transfer'
        Yanma süresi, cidar kalınlığı, yalıtım kalınlığı ve malzeme ısıl
        özellikleri hiç girmiyordu; 2 s'lik motorla 30 s'lik motor aynı
        sıcaklığı veriyordu.

        Yeni model — yalıtım + kasa serisi üzerinden yığın (lumped) kapasite:
            m*cp*dT/dt = A*[ (T_aw - T)/(1/h_g + t_ins/k_ins)
                             - h_dis*(T - T_ort) - eps*sigma*(T^4 - T_ort^4) ]
        Kasa Biot sayısı küçüktür (ince metal, yüksek k) → yığın kapasite
        geçerlidir (Incropera & DeWitt §5.1). h_g Bartz'tan gelir (hazne
        istasyonu), yalıtım direnci kullanıcının liner_thickness girdisinden.
        """
        if burn_time is None:
            burn_time = float(getattr(self, '_last_burn_time', 0.0) or 0.0)
        T_amb = float(getattr(self, 'ambient_temperature',
                              SOLID_THERMAL['ambient_temperature_k']))
        # V301/K-D (ÖRNEK-PANEL devri; fail-closed): eski gövde iki durumda
        # SESSİZCE ortam sıcaklığını döndürüyordu — çözülmüş yanma yokken ve
        # hazne gaz tarafı (Bartz) istisna verdiğinde. Ortam sıcaklığındaki
        # bir kasa en iyimser cevaptır: ısıl panel "Excellent" sınıfı, güvenlik
        # paneli oda sıcaklığı dayanımıyla kap onayı basabiliyordu. Artık
        # sayı UYDURULMAZ: dönüş ``None`` ve neden ``_case_temperature_status``
        # künyesinde (``source = 'not_solved'``); tüketiciler hükmü geri çeker.
        self._case_temperature_status = {'source': 'solved', 'reason': None}
        if burn_time <= 0:
            self._case_temperature_status = {
                'source': 'not_solved',
                'reason': {'code': 'burn_not_solved',
                           'message': 'no solved burn time is available, so '
                                      'the case heating was not integrated'}}
            return None

        try:
            h_g, T_aw, _cp = self._chamber_gas_side()
        except Exception as exc:
            self._case_temperature_status = {
                'source': 'not_solved',
                'reason': {'code': 'chamber_gas_side_failed',
                           'message': ('the chamber gas-side heat transfer '
                                       '(Bartz) could not be evaluated: '
                                       '%s: %s' % (type(exc).__name__,
                                                   str(exc)[:200]))}}
            return None

        material, _sy, _sf, t_wall = self._case_design()
        # Yoğunluk TEK kaynaktan (_case_density) gelir; kompozit gibi
        # materials_db kaydı olmayan aileler burada da sessizce çelik
        # yoğunluğuna düşemez. Özgül ısının kaydı yoksa jenerik metal değeri
        # kullanılır — bu, geçici kasa sıcaklığının bilinen model sınırıdır.
        rho_c = self._case_density()
        try:
            from hrma.data.materials_db import get_material
            cp_c = float(get_material(material)['specific_heat'])
        except Exception:
            cp_c = SOLID_THERMAL['fallback_case_specific_heat_j_kgk']

        # Birim alan başına ısıl kapasite (kasa + yalıtım paketinin yarısı).
        # Kalınlık, ısıl dirençle AYNI kaynaktan gelir (yalıtım + liner).
        t_ins = self._thermal_barrier_thickness()
        rho_ins = self._insulation_density()
        cp_ins = SOLID_INSULATION['specific_heat_j_kgk']
        capacity = rho_c * cp_c * t_wall + 0.5 * rho_ins * cp_ins * max(t_ins, 0.0)

        r_in = 1.0 / h_g + self._insulation_resistance()
        h_out = SOLID_THERMAL['external_convection_w_m2k']
        eps = SOLID_THERMAL['external_emissivity']
        sigma_sb = SOLID_THERMAL['stefan_boltzmann']

        # Açık Euler; adım kararlılık için sınırlanır
        n_steps = int(SOLID_THERMAL['transient_steps'])
        dt = burn_time / n_steps
        T = T_amb
        for _ in range(n_steps):
            q_in = (T_aw - T) / r_in
            q_out = h_out * (T - T_amb) + eps * sigma_sb * (T ** 4 - T_amb ** 4)
            T = T + dt * (q_in - q_out) / max(capacity, 1e-9)
            if T > T_aw:      # fiziksel üst sınır
                T = T_aw
                break
        return float(T)
    
    # ÖH D21 a1 (P2B4-13) — DÖRT UYDURMA UÇUŞ SABİTİ SİLİNDİ.
    #
    # Buradaki dört metot motorun HİÇBİR girdisine bakmıyor, gövdesiz
    # birer sabit döndürüyordu ve yorumları 'typical' diyordu:
    #     _estimate_apogee            -> 3500   m
    #     _estimate_max_velocity      ->  450   m/s
    #     _estimate_max_acceleration  ->    8.5 g
    #     _estimate_flight_time       ->   45   s
    # ÖLÇÜLDÜ (docs/scofield/raw/OH/D21/kati/a1/once.json): depo genelinde
    # tek geçtikleri yer kendi tanım satırlarıydı — ÇAĞIRAN YOKTU, yani
    # kullanıcıya uydurma bir uçuş sayısı gitmiyordu. Risk, birinin bu
    # dördünü "hazır uçuş kestirimi" sanıp bağlamasıydı: HRMA'nın bir
    # uçuş/trajektori çözücüsü yoktur, bu sayılar hiçbir modelden gelmez.
    # v2.6.26 uydurma sökümü aynı dosyada _calculate_quality_analysis,
    # _calculate_environmental_effects ve failure_modes bloklarını
    # temizlemişti; bu dört kalem atlanmıştı. Uçuş kestirimi GEREKİRSE
    # gerçek bir trajektori entegrasyonuyla gelir, sabitle değil.

    def _burnout_web(self, w_lo, w_hi, iters=40):
        """A_burn'ün sıfırlandığı web kalınlığını (w_lo, w_hi] içinde daraltır.

        Geometrik tükenişte (star/finocyl/slotted/wagon) yanan alan bir zaman
        adımı içinde sonlu bir değerden 0'a düşer; tükeniş anını bilmeden son
        aralık impulse'a giremez. Aralık tek bir dt kadar dar olduğundan tek
        kök varsayımı güvenlidir.
        """
        lo, hi = float(w_lo), float(w_hi)
        for _ in range(int(iters)):
            mid = 0.5 * (lo + hi)
            if self.calculate_burn_area(mid) > 0:
                lo = mid
            else:
                hi = mid
            if hi - lo <= 1e-9:
                break
        return lo

    def _equilibrium_pressure_fallback(self, A_burn, A_port, A_t, port_ratio,
                                       temperature, p_start, p_image, tol,
                                       max_iter=SOLID_PRESSURE_SOLVER_MAX_ITER):
        """Sönümlü yineleme yakınsamadığında denge basıncı yedeği (V301/B6).

        YALNIZ ilk yol (sönümlü sabit-nokta yinelemesi) tavana takıldığında
        çağrılır; yakınsayan adımlar buraya hiç gelmez, dolayısıyla bit-aynı
        kalır.

        Kusur (ölçüm 20-21 Eki): KNDX Nakka rejim tablosu sınırlarda
        süreksiz (r(P_b−) → r(P_b+): 0,779 MPa −%0,54; 2,57 MPa −%1,80;
        5,93 MPa +%1,14; 8,5 MPa −%1,77). Hız basınçla AŞAĞI sıçrıyorsa,
        belirli bir Kn aralığında iki daldan hiçbirinde denge yoktur: alt
        dalın dengesi sınırın üstünde, üst dalınki altında kalır. Yineleme
        sınır çevresinde salınır, artık ≈ sıçrama (örnek motorda 228 adımın
        9'u, en büyük artık %1,7).

        Yöntem. Kütle dengesi artığı [bar]
            f(P) = ρ_p·A_b·r(P)·c*/(A_t·1e5) − P
        sabit-nokta yinelemesiyle AYNI işlem sırasıyla kurulur. Erozif
        çarpanın girdisi olan port kütle akısı P'nin fonksiyonu olarak
        tutarlı verilir: dengede ṁ = P·1e5·A_t/c*, G(P) = ṁ/A_port
        (yineleme ise akıyı bir önceki iteratın ṁ'sinden alır).
          1. Parantez son iteratlardan (son sönümlü iterat ile onun
             sabit-nokta görüntüsü) başlar; işaret f(a) > 0 > f(b) olana
             dek genişletilir (genişlik her turda iki katı). Bu yön, yarı
             durağan kamaranın dP/dt ∝ f(P) dinamiğinde KARARLI dengenin
             yönüdür; f'nin artarak sıfırı kestiği (n ≥ 1) kararsız denge
             parantezlenmez.
          2. İkiye bölme, ilk yolun ölçütüyle (|f| ≤ tol·max(P, 1)) sürekli
             kök arar. Bulunursa adım yakınsamış sayılır. Kök sayısal
             yanma hızı tavanında (BURN_RATE_NUMERIC_CEILING_MPS) ise
             reddedilir: o bir taşma korumasının izi, yasanın dengesi değil.
          3. Parantez komşu iki kayan noktalı sayıya çöker ve |f| hâlâ
             toleransın üstündeyse f orada sıçrar. Sıçrama parçalı yasanın
             bir rejim sınırıysa denge genelleştirilmiş (küme değerli /
             Filippov) anlamda P = P_b'dir: kütle dengesini kapatan hız
             r_eq = P_b·1e5·A_t/(ρ_p·A_b·c*) olur. r_eq sıçramanın iki ucu
             (aynı r(P) tanımıyla, erozif/sıcaklık/parti çarpanları dahil)
             arasında kalmak ZORUNDADIR; değilse adım yakınsamamış sayılır.
             Kaynak: A. F. Filippov, Differential Equations with
             Discontinuous Righthand Sides, Kluwer, 1988, Böl. 2 (süreksiz
             sağ taraflı denklemde denge, sağ tarafın küme değerli
             uzantısının sıfırı içerdiği noktadır).
        Parantez kurulamaz, değerlerden biri sonlu değil ya da sıçrama bir
        rejim sınırı değilse ``None`` döner (fail-closed): çağıran, adımı
        bugünkü gibi yakınsamamış sayar ve son iteratı korur.

        Yan etki sözleşmesi: değerlendirmeler ``self.mass_flux``'ı değiştirir.
        Başarıda akı çözümdeki G(P)'ye, başarısızlıkta çağrı öncesi değerine
        döner. ``_burn_rate_clipped_max`` (tavan kırpma kaydı) değerlendirme
        boyunca ne yazılırsa yazılsın çağrı öncesi hâline geri alınır; kabul
        edilen kökte tavan zaten reddedilir.

        Returns:
            None ya da sözlük: ``kind`` ('root' | 'boundary'),
            ``pressure_bar``, ``mass_flux``, ``residual`` (bağıl kütle dengesi
            artığı); 'boundary' ek olarak ``burn_rate_mps`` (r_eq),
            ``boundary_pressure_bar`` (tablonun yayımladığı sınır),
            ``law_jump_percent``, ``rate_below_mps``, ``rate_above_mps``.
        """
        try:
            sayilar = [float(v) for v in (A_burn, A_t, self.rho_p,
                                          self.c_star, p_start, p_image, tol)]
            a_port = float(A_port)
            # Yalnız doğrulanır; burn_rate()'e ilk yolla AYNI nesneler gider
            oran_f = float(port_ratio)
            sicaklik_f = float(temperature)
            max_iter = int(max_iter)
        except (TypeError, ValueError, OverflowError):
            return None
        if (not all(np.isfinite(v) and v > 0.0 for v in sayilar)
                or not np.isfinite(a_port) or a_port < 0.0
                or not np.isfinite(oran_f) or not np.isfinite(sicaklik_f)
                or max_iter < 1):
            return None
        A_burn, A_t, rho_p, c_star, p_start, p_image, tol = sayilar

        aki_once = getattr(self, 'mass_flux', 0.0)
        kirpma_vardi = '_burn_rate_clipped_max' in self.__dict__
        kirpma_once = self.__dict__.get('_burn_rate_clipped_max')
        basarili = False

        def artik(p):
            # Dengede ṁ = P·1e5·A_t/c* — erozif akı P'nin tutarlı fonksiyonu
            g = p * 1e5 * A_t / (c_star * a_port) if a_port > 0 else 0.0
            self.mass_flux = g
            r = float(self.burn_rate(p, temperature, port_ratio))
            # İlk yoldaki P_new ile AYNI işlem sırası
            f = (rho_p * A_burn * r) * c_star / (A_t * 1e5) - p
            if not (np.isfinite(f) and np.isfinite(r)):
                raise FloatingPointError('non-finite residual')
            return f, r, g

        def kabul(p, f):
            return abs(f) <= tol * max(abs(p), 1.0)

        def kok(p, f, r, g):
            # Tavanda kırpılmış hızla kurulan "denge" yasanın değil sayısal
            # korumanın sonucudur; sıfır hızda denge yoktur.
            if not (0.0 < r < BURN_RATE_NUMERIC_CEILING_MPS):
                return None
            return {'kind': 'root', 'pressure_bar': float(p),
                    'mass_flux': float(g),
                    'residual': float(abs(f) / max(abs(p), 1.0))}

        try:
            a, b = sorted((p_start, p_image))
            fa, ra, ga = artik(a)
            if kabul(a, fa):
                sonuc = kok(a, fa, ra, ga)
                basarili = sonuc is not None
                return sonuc
            fb, rb, gb = artik(b)
            if kabul(b, fb):
                sonuc = kok(b, fb, rb, gb)
                basarili = sonuc is not None
                return sonuc

            # 1. Parantez: f(a) > 0 > f(b) (kararlı denge yönü)
            w = max(b - a, tol * max(b, 1.0))
            for _ in range(max_iter):
                if fa > 0.0 and fb < 0.0:
                    break
                if fb >= 0.0:
                    # Kök daha yukarıda: b alt uca geçer, üst uç genişler
                    a, fa, ra, ga = b, fb, rb, gb
                    b = b + w
                    fb, rb, gb = artik(b)
                    if kabul(b, fb):
                        sonuc = kok(b, fb, rb, gb)
                        basarili = sonuc is not None
                        return sonuc
                else:
                    # f(a) <= 0 ve f(b) < 0: kök daha aşağıda
                    b, fb, rb, gb = a, fa, ra, ga
                    a = a - w if a - w > 0.0 else 0.5 * a
                    fa, ra, ga = artik(a)
                    if kabul(a, fa):
                        sonuc = kok(a, fa, ra, ga)
                        basarili = sonuc is not None
                        return sonuc
                w *= 2.0
            if not (fa > 0.0 and fb < 0.0):
                return None

            # 2. İkiye bölme: sürekli kök ya da komşu kayan noktalılara çöküş
            cokti = False
            for _ in range(max_iter):
                m = 0.5 * (a + b)
                if not (a < m < b):
                    cokti = True
                    break
                fm, rm, gm = artik(m)
                if kabul(m, fm):
                    sonuc = kok(m, fm, rm, gm)
                    basarili = sonuc is not None
                    return sonuc
                if fm > 0.0:
                    a, fa, ra, ga = m, fm, rm, gm
                else:
                    b, fb, rb, gb = m, fm, rm, gm
            if not cokti:
                return None

            # 3. Sıçrama: yalnız parçalı yasanın rejim sınırı kabul edilir
            law_key = getattr(self, 'burn_rate_law_key', None)
            if not law_key:
                return None
            from hrma.data import burn_rate_db as _brdb
            law = _brdb.BURN_RATE_LAWS[law_key]
            # burn_rate() ile AYNI dönüşüm (p_mpa = P_bar / 10) ve AYNI seçici
            reg_alt = _brdb._select_regime(law, a / 10.0)
            reg_ust = _brdb._select_regime(law, b / 10.0)
            if reg_alt is reg_ust:
                return None
            if not (0.0 < ra < BURN_RATE_NUMERIC_CEILING_MPS
                    and 0.0 < rb < BURN_RATE_NUMERIC_CEILING_MPS):
                return None
            p_b = b   # üst rejimin başladığı ilk kayan noktalı basınç
            r_eq = self._boundary_equilibrium_rate(
                p_b, ra, rb, A_t, A_burn, rho_p, c_star)
            if r_eq is None:
                return None
            mdot = rho_p * A_burn * r_eq
            sonuc = {
                'kind': 'boundary',
                'pressure_bar': float(p_b),
                'mass_flux': float(gb),
                'burn_rate_mps': float(r_eq),
                'residual': float(abs(mdot * c_star / (A_t * 1e5) - p_b)
                                  / max(p_b, 1.0)),
                'boundary_pressure_bar': float(reg_ust['p_min_mpa']) * 10.0,
                'law_jump_percent': float((rb - ra) / ra * 100.0),
                'rate_below_mps': float(ra),
                'rate_above_mps': float(rb),
            }
            basarili = True
            return sonuc
        except (FloatingPointError, ValueError, KeyError, ZeroDivisionError,
                OverflowError):
            return None
        finally:
            if kirpma_vardi:
                self._burn_rate_clipped_max = kirpma_once
            else:
                self.__dict__.pop('_burn_rate_clipped_max', None)
            if not basarili:
                self.mass_flux = aki_once

    @staticmethod
    def _boundary_equilibrium_rate(p_b, r_below, r_above, A_t, A_burn, rho_p,
                                   c_star):
        """Rejim sınırında kütle dengesini kapatan hız r_eq [m/s] ya da None.

        r_eq = P_b·1e5·A_t/(ρ_p·A_b·c*) — boğaz akışı (P_b·A_t/c*) ile üretim
        (ρ_p·A_b·r) eşitliğinden. Genelleştirilmiş denge YALNIZ r_eq yasanın
        o basınçtaki sıçramasının iki ucu [r(P_b−), r(P_b+)] arasındaysa
        geçerlidir (Filippov: küme değerli sağ taraf sıfırı içermeli);
        değilse ya da herhangi bir değer sonlu/pozitif değilse None
        (fail-closed). Kuralın TEK tanım yeri burasıdır (V301/B6).
        """
        try:
            sayilar = [float(v) for v in (p_b, r_below, r_above, A_t, A_burn,
                                          rho_p, c_star)]
        except (TypeError, ValueError, OverflowError):
            return None
        if not all(np.isfinite(v) and v > 0.0 for v in sayilar):
            return None
        p_b, r_below, r_above, A_t, A_burn, rho_p, c_star = sayilar
        r_eq = p_b * 1e5 * A_t / (rho_p * A_burn * c_star)
        if not np.isfinite(r_eq):
            return None
        if not (min(r_below, r_above) <= r_eq <= max(r_below, r_above)):
            return None
        return float(r_eq)

    #: Rejim sınırında tutulan adımların İngilizce künyesi (V301/B6). Tanı
    #: bloklarının ikisi de (yakınsama kapısı ve tam sonuç) bu metni yayımlar.
    PRESSURE_SOLVER_BOUNDARY_BASIS = (
        'The piecewise burn-rate law is discontinuous at its regime '
        'boundaries. Where the rate drops with pressure across a boundary, a '
        'band of Kn has no equilibrium on either branch: the lower branch '
        'balances above the boundary and the upper branch below it. Such a '
        'time step is held at the boundary pressure as a generalized '
        '(set-valued, Filippov) equilibrium. The burn rate used there is the '
        'one that closes the mass balance, r_eq = Pc*A_t/(rho_p*A_b*c*), and '
        'it is required to lie inside the jump of the law at that pressure '
        '(otherwise the step counts as unconverged), so the deviation from '
        'either branch is bounded by the law\'s own discontinuity '
        '(law_jump_percent). Held steps are counted separately and are not '
        'solver failures. Source: A. F. Filippov, Differential Equations '
        'with Discontinuous Righthand Sides, Kluwer, 1988, Ch. 2.')

    @classmethod
    def _pressure_solver_boundary_publication(cls, curve):
        """Yedek çözücünün tanı alanları — iki tanı bloğu için TEK kaynak."""
        sinirlar = []
        for kayit in (curve.get('pressure_solver_regime_boundaries') or []):
            sinirlar.append({
                'boundary_pressure_bar': float(
                    kayit['boundary_pressure_bar']),
                'held_steps': int(kayit['held_steps']),
                'law_jump_percent': float(kayit['law_jump_percent']),
            })
        return {
            'pressure_solver_fallback_root_steps': int(
                curve.get('pressure_solver_fallback_root_steps', 0) or 0),
            'pressure_solver_boundary_held_steps': int(
                curve.get('pressure_solver_boundary_held_steps', 0) or 0),
            'pressure_solver_regime_boundaries': sinirlar,
            'pressure_solver_boundary_basis':
                cls.PRESSURE_SOLVER_BOUNDARY_BASIS,
        }

    def calculate_thrust_curve(self, dt=0.01, convergence_tol=1e-6):
        """High-precision thrust curve with iterative pressure-burn rate coupling.

        CODEX BULGUSU DÜZELTMESİ (2026-07-19, satır ~3621): örnekler t
        ilerlemeden ÖNCE saklandığı için son aralık (son örnek ile gerçek
        tükeniş arası) trapez integraline hiç girmiyordu. Yanma süresi ve
        toplam impuls sistematik olarak DÜŞÜK çıkıyordu — end-burner'da son
        örnek tam itkideydi, yani kayıp bir tam dt'lik itkiydi. Döngüden
        sonra tükeniş anı ANALİTİK olarak kapatılır (bkz. aşağıdaki
        'Tükeniş kapanışı' bloğu).

        CODEX BULGUSU DÜZELTMESİ (2026-07-19, satır ~3609):
        'convergence_achieved' sabit True idi. Artık basınç sabit-nokta
        çözümünün gerçek durumu raporlanır (yakınsamayan adım sayısı ve en
        büyük bağıl artık) ve _design_health_warnings bunu kullanıcıya
        görünür uyarıya çevirir.
        """
        # Initial conditions
        web_thickness = 0
        # Web üst sınırı TEK tanım noktasından okunur (_max_web_thickness):
        # boğaz boyutlandırması (v2.6.27, A1-1) aynı aralığı tarar, iki yerde
        # iki farklı tükenme kuralı duramaz.
        max_web = self._max_web_thickness()


        time = []
        thrust = []
        pressure = []
        burn_area = []
        mass_flow = []
        burn_rate_data = []
        # F067: erozif yanmanın FİİLEN uygulanan büyüklüğü rapor için saklanır
        # (rapor artık ayrı bir uydurma doğrudan değil, çözücüden okunur).
        port_area_series = []
        mass_flux_series = []
        erosive_factor_series = []
        # A1-2: akış ayrılması artık itkiyi DEĞİŞTİRDİĞİ için hangi örneklerin
        # ayrılmış rejimde olduğu eğriyle birlikte yayımlanır (arayüz o bölgeyi
        # işaretleyebilsin, kullanıcı "burada tek boyutlu ekli akış geçerli
        # değil" bilgisini görsün).
        separation_series = []
        exit_pressure_series = []
        # Boğulma bayrağı: çözücünün mdot = Pc·A_t/c* boşalma yasası da, CF
        # bağıntıları da boğazın SONİK olmasını varsayar. Kuyrukta Pc,
        # P_a/((γ+1)/2)^(γ/(γ−1)) sınırının altına düşerse iki varsayım da
        # geçersizdir; bu bölge işaretlenir ve uyarıyla bildirilir.
        choked_series = []

        t = 0
        current_temp = self.temp_ref  # Başlangıç sıcaklığı = yanma-hızı referansı (K)
        # (#434 tutarlılık: temp_correction ateşlemede nötr (1.0) başlar; delta korunur)

        # Basınç çözücü sağlığı (sabit True yerine gerçek durum) ve tükeniş
        # kapanışı için son adımın durumu
        solver_steps = 0
        solver_failed_steps = 0
        solver_max_residual = 0.0
        # V301/B6: ilk yol tavana takıldığında yedek çözücünün sonucu. Sürekli
        # kökle kurtarılan adımlar yakınsamış sayılır; rejim sınırında
        # (genelleştirilmiş denge) tutulan adımlar başarısız SAYILMAZ, ayrı
        # sayılır ve sınır başına yayımlanır.
        solver_fallback_root_steps = 0
        solver_boundary_steps = 0
        solver_boundary_step_indices = []
        solver_boundaries = {}
        termination = 'not_started'
        last_web = 0.0
        last_rate = 0.0

        # ------------------------------------------------------------------
        # Boğaz alanı TASARIM NOKTASINDA boyutlandırılır.
        # Boğulmuş akış: mdot = Pc*A_t/c*  ;  kütle üretimi: mdot = rho_p*Ab*r
        # => A_t = rho_p * Ab0 * r(Pc_tasarım) * c* / (Pc_tasarım * 1e5)
        # Kaynak: Sutton & Biblarz 9. baskı Böl. 12; NASA SP-8039 §3.1.1.1.1
        # eş. (44), s. 56 (KU-K2: eski künye "NASA SP-8089" sıvı enjektör
        # monografıydı).
        #
        # F071 (2026-07-25): A_t artık koşu boyunca SABİT DEĞİLDİR. Kullanıcı
        # bir erozyon katsayısı verdiyse (erosion_factor, mm/s @ 70 bar) her
        # adımda boğaz yarıçapı ampirik modelle büyütülür; vermediyse eski
        # rijit-boğaz davranışı bit-özdeş korunur ve varsayımın önemli olduğu
        # motorlarda _design_health_warnings kullanıcıyı uyarır.
        # ------------------------------------------------------------------
        # Tasarım noktası boyutlandırması TEK yerde (_design_throat_area);
        # CAD/rapor katmanı da aynı fonksiyonu çağırır (Y1).
        A_t, mass_flux_design = self._design_throat_area()
        if A_t > 0:
            self.mass_flux = mass_flux_design
        else:
            A_t = np.pi * (0.015 / 2) ** 2  # fallback; döngü zaten hemen kırılır

        A_t_initial = A_t
        erosion_model = self._throat_erosion_model()
        r_throat = np.sqrt(A_t / np.pi)      # anlık boğaz yarıçapı [m]
        throat_area_series = []

        P_c_prev = self.P_c  # denge çözümü için sıcak başlangıç (bar)

        termination = 'web_exhausted'   # döngü normal çıkarsa web tükenmiştir
        while web_thickness < max_web:
            # Calculate burn area with high precision
            A_burn = self.calculate_burn_area(web_thickness)
            if A_burn <= 0:
                termination = 'burn_area_vanished'
                break

            # Port geometrisi: erozif yanma port kütle akısı G = mdot/A_port
            # ile ölçeklenir (Lenoir-Robillard; Sutton & Biblarz Böl. 12)
            A_port = self._port_flow_area(web_thickness)
            port_ratio = (self.D_core + 2 * web_thickness) / self.D_chamber

            # ----------------------------------------------------------------
            # Balistik denge basıncı: Kn = Ab/At ile
            #   Pc = (Kn * a * rho_p * c*)^(1/(1-n))   [a SI/Pa bazlı ise]
            # Saint-Robert katsayısı bar bazlı olduğundan ve r(Pc) sıcaklık/
            # plato/erozif düzeltmeleri içerdiğinden, aynı denge sabit-nokta
            # iterasyonuyla çözülür (n < 1 olduğundan daralma garantili):
            #   Pc_yeni [Pa] = rho_p * Ab * r(Pc) * c* / A_t
            # Kaynak: Sutton & Biblarz 9. baskı Denk. 12-6; NASA SP-8039
            # §3.1.1.1.1 eş. (44), s. 56 (KU-K2: eski künye "NASA SP-8089").
            #
            # Kütle dengesi beyanı (§17 K13 / KC-5, sayı değişmez): denge
            # YARI DURAĞANDIR — üretilen = lüleden atılan. Kamarada depolanan
            # gaz terimi d(ρ_g·V)/dt ve boşalan hacmi dolduran ρ_g (yani
            # ρ_p yerine ρ_p − ρ_g) YOKTUR. Yarı durağan evrede bu ihmal
            # birincil kaynakla aynıdır (NASA SP-8076 eş. (35), s. 54: denge
            # koşulu odada depolanan kütle ihmal edilerek kurulur);
            # ateşleme/kuyruk geçişinde terim gerekir (SP-8039 eş. (47),
            # s. 57). Büyüklük (KARS-KT K13 ölçümü): APCP 40 bar'da
            # ρ_g/ρ_p ≈ %0,21 → sabit boğazda P_c ≤ ~%0,3; KNSB 10 bar'da
            # %0,14. Kitap karşılığı: Sutton 9 Eş. 12-3 s. 444-445; Mishra
            # Eş. 7.24-7.26 s. 227.
            # ----------------------------------------------------------------
            P_c_actual = P_c_prev
            r_burn_actual = self.burn_rate(P_c_actual, current_temp, port_ratio)
            step_converged = False
            step_residual = float('inf')
            for _yineleme in range(SOLID_PRESSURE_SOLVER_MAX_ITER):
                m_dot_iter = self.rho_p * A_burn * r_burn_actual
                self.mass_flux = m_dot_iter / A_port if A_port > 0 else 0.0
                P_new = m_dot_iter * self.c_star / (A_t * 1e5)  # bar
                step_residual = (abs(P_new - P_c_actual)
                                 / max(abs(P_c_actual), 1.0))
                if abs(P_new - P_c_actual) <= convergence_tol * max(abs(P_c_actual), 1.0):
                    # V301/B6 ardılı (21 Eki) — İLK YİNELEMEDE AKI TUTARLILIĞI.
                    # Döngüden önceki r, ÖNCEKİ zaman adımının port kütle
                    # akısıyla hesaplanır (erozif çarpanın girdisi); basınç ilk
                    # yinelemede tolerans içindeyse adım o eski akıyla kabul
                    # ediliyordu. ÖLÇÜLDÜ (B6 RAPOR, KNSB eşdeğeri 116. adım):
                    # tutarlı akıyla kütle dengesi artığı 7,8e-5 (tolerans
                    # 1e-6), basınca etkisi ~1e-4. Hız güncel akıyla yeniden
                    # hesaplanır; aynı toleransta değişmiyorsa adım aynen kabul
                    # edilir (erozif terimi etkisiz adımlar bit-aynı), değişiyorsa
                    # yineleme tutarlı akıyla sürer.
                    if _yineleme == 0:
                        r_tutarli = self.burn_rate(P_c_actual, current_temp,
                                                   port_ratio)
                        if (abs(r_tutarli - r_burn_actual)
                                > convergence_tol * max(abs(r_burn_actual),
                                                        1e-12)):
                            r_burn_actual = r_tutarli
                            continue
                    P_c_actual = P_new
                    step_converged = True
                    break
                P_c_actual = 0.5 * (P_c_actual + P_new)  # sönümlü güncelleme
                r_burn_actual = self.burn_rate(P_c_actual, current_temp, port_ratio)

            # V301/B6 — YALNIZ tavana takılan adımda yedek: kütle dengesi
            # artığı parantezlenip ikiye bölünür (bkz.
            # _equilibrium_pressure_fallback). Yakınsayan adımlar bu dala
            # girmez, dolayısıyla bit-aynı kalır. Yedek de başarısızsa
            # (None) son iterat ve akı aynen korunur — bugünkü uyarı yolu.
            boundary_hold = None
            if not step_converged:
                yedek = self._equilibrium_pressure_fallback(
                    A_burn, A_port, A_t, port_ratio, current_temp,
                    P_c_actual, P_new, convergence_tol)
                if yedek is not None:
                    P_c_actual = yedek['pressure_bar']
                    self.mass_flux = yedek['mass_flux']
                    step_residual = yedek['residual']
                    if yedek['kind'] == 'root':
                        step_converged = True
                        solver_fallback_root_steps += 1
                    else:
                        boundary_hold = yedek

            # Basınç çözücü sağlığı: tavan + yedek bittiyse SON İTERAT
            # döndürülüyor; bu artık sessizce 'yakınsadı' diye raporlanamaz.
            solver_steps += 1
            if boundary_hold is not None:
                solver_boundary_steps += 1
                solver_boundary_step_indices.append(len(time))
                kayit = solver_boundaries.setdefault(
                    boundary_hold['boundary_pressure_bar'], {
                        'boundary_pressure_bar':
                            boundary_hold['boundary_pressure_bar'],
                        'held_steps': 0,
                        'law_jump_percent':
                            boundary_hold['law_jump_percent'],
                    })
                kayit['held_steps'] += 1
            elif not step_converged:
                solver_failed_steps += 1
            if np.isfinite(step_residual):
                solver_max_residual = max(solver_max_residual,
                                          float(step_residual))

            if P_c_actual <= 0:
                termination = 'pressure_collapse'
                break

            # Yakınsayan basınçta son yanma hızı ve kütle üretimi. Rejim
            # sınırında tutulan adımda yasa P_b'de tek değer vermez; kütle
            # dengesini kapatan r_eq (sıçramanın içinde, yedekte denetlendi)
            # web ilerlemesini ve ṁ_üretim'i belirler.
            if boundary_hold is not None:
                r_burn_actual = boundary_hold['burn_rate_mps']
            else:
                r_burn_actual = self.burn_rate(P_c_actual, current_temp,
                                               port_ratio)
            if r_burn_actual <= 0:
                termination = 'burn_rate_zero'
                break
            P_c_prev = P_c_actual

            # Mass generation rate (dengede boğaz akışıyla eşit)
            m_dot_gen = self.rho_p * A_burn * r_burn_actual
            
            # High-precision thrust coefficient with all corrections
            # (TEK tanım noktası: _thrust_coefficient_state — tasarım noktası
            #  boyutlandırması da aynı CF'i kullanır). Ayrılma durumu aynı
            #  hesaptan okunur, ikinci kez çözülmez.
            cf_state = self._thrust_coefficient_state(P_c_actual)
            CF_actual = cf_state['cf']

            # Thrust calculation
            F = CF_actual * P_c_actual * 1e5 * A_t
            
            # FİZİK DENETİMİ DÜZELTMESİ (F179, 2026-07-25): burada
            # 'sadeleştirilmiş adyabatik model' adıyla bir sahte fizik bloğu
            # vardı — current_temp += 0.001·dt ve tavan T_c/2. 0.001'in birimi
            # (K/s? W/m²K?) belirsizdi, hiçbir kütle/ısı kapasitesi/geometri
            # girmiyordu ve T_c/2 tavanının fiziksel karşılığı yoktu.
            # GERÇEK: grain KÜTLESİNİN ortalama sıcaklığı yanma süresince
            # pratik olarak DEĞİŞMEZ — ısı nüfuz derinliği yanan yüzeyin
            # ~0.1 mm altındadır (katı yakıt termal difüzivitesi ~1e-7 m²/s,
            # yanma hızı ~1e-2 m/s → δ ≈ α/r ≈ 10 µm). Yanma hızı düzeltmesi
            # bu yüzden BAŞLANGIÇ (depolama) sıcaklığından hesaplanır ve
            # koşu boyunca sabit tutulur. Blok kaldırıldı (sayısal etkisi
            # zaten ölçülemez düzeydeydi: 27.5 s'lik koşuda +0.0275 K).
            # Kaynak: Sutton & Biblarz 9. baskı Böl. 12 (katı yakıtta ısıl
            # dalga yapısı ve σp'nin DEPOLAMA sıcaklığına bağlı tanımı).

            # Store results
            time.append(t)
            thrust.append(F)
            pressure.append(P_c_actual)
            burn_area.append(A_burn)
            mass_flow.append(m_dot_gen)
            burn_rate_data.append(r_burn_actual)
            throat_area_series.append(A_t)
            port_area_series.append(A_port)
            mass_flux_series.append(self.mass_flux)
            erosive_factor_series.append(
                self._erosive_factor(self.mass_flux, port_ratio))
            separation_series.append(bool(cf_state['separated']))
            exit_pressure_series.append(float(cf_state['pe_bar']))
            choked_series.append(bool(cf_state['choked']))

            # Boğaz erozyonu: yarıçap ampirik hızla geriler, A_t büyür
            # (F071; model transient_ballistics.ThroatErosionModel).
            if erosion_model is not None:
                r_throat += erosion_model.rate_m_s(P_c_actual * 1e5) * dt
                if r_throat >= self.D_chamber / 2:
                    termination = 'throat_eroded_out'
                    break
                A_t = np.pi * r_throat ** 2

            # Web ilerlemesi: Huygens ofsetinde yüzey normal boyunca tam
            # yanma hızıyla ilerler (dw/dt = r). Eski 1.2·(1−w/W) star
            # çarpanı ofset modeliyle çifte-sayımdı: kütle korunumunu %44
            # bozuyor ve yapay itki kuyruğu üretiyordu (2026-07-13 teyidi).
            last_web = web_thickness
            last_rate = r_burn_actual
            web_thickness += r_burn_actual * dt
            t += dt

            # Safety limits
            if t > 1000 or P_c_actual > 500:  # 500 bar maximum pressure
                termination = 'safety_limit'
                break

        # ------------------------------------------------------------------
        # Tükeniş kapanışı (Codex bulgusu, satır ~3621)
        # ------------------------------------------------------------------
        # Döngü örnekleri adımın BAŞINDA saklar; son örnek ile gerçek tükeniş
        # arasındaki [t_son, t_tükeniş] aralığı trapez integralinin dışında
        # kalıyordu. Aşağıda o aralık TEK bir sonlandırma örneğiyle kapatılır:
        #
        #  - web_exhausted / burn_area_vanished: yakıt son ana kadar son
        #    hesaplanan durumla yanar (model, yanan alanı tükeniş webinde
        #    süreksiz olarak sıfırlar), dolayısıyla sıfırıncı-mertebe tutma
        #    kullanılır ve integral dikdörtgen olarak kapanır — O(dt^2) hata.
        #    Tükeniş anı analitik: t_b = t_son + (w_tükeniş - w_son) / r_son.
        #  - pressure_collapse / burn_rate_zero: model basıncın söndüğünü
        #    söylüyor; dürüst sonlandırma sıfır itki/basınçtır.
        #  - safety_limit: anormal sonlanma; kapanış eklenmez (aşağıdaki
        #    uyarı mekanizması bunu kullanıcıya bildirir).
        burnout_time = None
        if time and last_rate > 0:
            if termination == 'web_exhausted':
                w_end = max_web
            elif termination == 'burn_area_vanished':
                w_end = self._burnout_web(last_web, web_thickness)
            else:
                w_end = None
            if w_end is not None and w_end > last_web:
                t_b = time[-1] + (w_end - last_web) / last_rate
                # Sayısal güvenlik: kapanış en fazla bir tam adım uzatabilir
                t_b = min(t_b, time[-1] + dt)
                if t_b > time[-1]:
                    burnout_time = t_b
                    time.append(t_b)
                    thrust.append(thrust[-1])
                    pressure.append(pressure[-1])
                    burn_area.append(burn_area[-1])
                    mass_flow.append(mass_flow[-1])
                    burn_rate_data.append(burn_rate_data[-1])
                    throat_area_series.append(A_t)
                    port_area_series.append(port_area_series[-1])
                    mass_flux_series.append(mass_flux_series[-1])
                    erosive_factor_series.append(erosive_factor_series[-1])
                    separation_series.append(separation_series[-1])
                    exit_pressure_series.append(exit_pressure_series[-1])
                    choked_series.append(choked_series[-1])
        if (burnout_time is None and time
                and termination in ('pressure_collapse', 'burn_rate_zero')
                and t > time[-1]):
            burnout_time = t
            time.append(t)
            thrust.append(0.0)
            pressure.append(0.0)
            burn_area.append(0.0)
            mass_flow.append(0.0)
            burn_rate_data.append(0.0)
            throat_area_series.append(A_t)
            port_area_series.append(port_area_series[-1])
            mass_flux_series.append(0.0)
            erosive_factor_series.append(1.0)
            # Basınç söndü: akış yok, ayrılma rejimi de yok.
            separation_series.append(False)
            exit_pressure_series.append(0.0)
            choked_series.append(False)

        zaman_arr = np.asarray(time, dtype=float)
        sep_arr = np.array(separation_series, dtype=bool)
        separated_from_t = None
        if sep_arr.size and bool(sep_arr.any()):
            separated_from_t = float(zaman_arr[int(np.argmax(sep_arr))])

        choked_arr = np.array(choked_series, dtype=bool)
        unchoked_from_t = None
        # Yalnız AKIŞ OLAN örnekler sayılır: sönüş kapanışı (Pc = 0) zaten
        # boğulmamıştır ve bir model geçersizliği değil, yanmanın bitişidir.
        basinc_arr = np.asarray(pressure, dtype=float)
        akan = basinc_arr > 0.0 if basinc_arr.size else np.zeros(0, bool)
        unchoked_mask = (~choked_arr) & akan if choked_arr.size else np.zeros(
            0, bool)
        if unchoked_mask.size and bool(unchoked_mask.any()):
            unchoked_from_t = float(zaman_arr[int(np.argmax(unchoked_mask))])

        return {
            'time': np.array(time),
            'thrust': np.array(thrust),
            'pressure': np.array(pressure),
            'burn_area': np.array(burn_area),
            'mass_flow': np.array(mass_flow),
            'burn_rate': np.array(burn_rate_data),
            # Sözleşme korunur: 'throat_area' TASARIM (t=0) boğaz alanıdır.
            # Erozyon açıkken anlık değerler 'throat_area_series' içindedir.
            'throat_area': A_t_initial,  # m^2
            'throat_area_series': np.array(throat_area_series),
            'throat_area_final': float(A_t),
            'throat_erosion': self._throat_erosion_report(
                erosion_model, A_t_initial, float(A_t)),
            # F067: erozif yanmanın çözücüde fiilen uygulanan büyüklüğü
            'port_area': np.array(port_area_series),
            'mass_flux': np.array(mass_flux_series),
            'erosive_factor': np.array(erosive_factor_series),
            # A1-2: akış ayrılması. 'separated' örnek başına bayraktır,
            # 'separated_from_t' ayrılmanın İLK görüldüğü andır (hiç
            # ayrılmıyorsa None — sayı uydurulmaz). Ayrılmış bölgede itki
            # kesilmiş-lüle modelinden gelir (bkz. _thrust_coefficient_state).
            'separated': sep_arr,
            'separated_from_t': separated_from_t,
            'separated_fraction': (float(sep_arr.mean())
                                   if sep_arr.size else 0.0),
            'exit_pressure_bar': np.array(exit_pressure_series),
            # Boğulma: modelin geçerlilik sınırı. False olan örneklerde hem
            # boşalma yasası hem CF bağıntısı geçersizdir; itki UYDURULMAZ,
            # sıfır raporlanır ve durum bildirilir.
            'choked': choked_arr,
            'unchoked_from_t': unchoked_from_t,
            'unchoked_fraction': (float(unchoked_mask.mean())
                                  if unchoked_mask.size else 0.0),
            'choking_criterion': (
                'Choked-throat limit: Pc >= Pa*((gamma+1)/2)^(gamma/(gamma-1)). '
                'Below it the solver mass-flow law mdot = Pc*A_t/c* and the '
                'thrust-coefficient relations do not apply; thrust is '
                'reported as zero there and the samples are flagged rather '
                'than filled with a number the model cannot produce.'),
            'separation_criterion': (
                'Summerfield: flow separation expected below Pe/Pa = '
                f'{SUMMERFIELD_SEPARATION_RATIO:g}; in the separated region '
                'the thrust coefficient is evaluated as a nozzle TRUNCATED '
                'at the separation area ratio, not as the attached 1-D '
                'nozzle. Source: Sutton & Biblarz, Rocket Propulsion '
                'Elements 9th ed., Ch. 3 and Ch. 5.'),
            # Basınç sabit-nokta çözümünün GERÇEK durumu (eskiden sabit True)
            'convergence_achieved': bool(solver_failed_steps == 0),
            'pressure_solver_steps': int(solver_steps),
            'pressure_solver_failed_steps': int(solver_failed_steps),
            'pressure_solver_max_residual': float(solver_max_residual),
            'pressure_solver_tolerance': float(convergence_tol),
            # V301/B6: yedek çözücünün izi. Sınırda tutulan adımlar başarısız
            # sayılmaz; hangi örneklerde olduğu (indeks) ve sınır başına
            # özet (basınç, adım sayısı, yasanın oradaki sıçraması) ayrıca.
            'pressure_solver_fallback_root_steps': int(
                solver_fallback_root_steps),
            'pressure_solver_boundary_held_steps': int(solver_boundary_steps),
            'pressure_solver_boundary_step_indices': list(
                solver_boundary_step_indices),
            'pressure_solver_regime_boundaries': [
                dict(solver_boundaries[k]) for k in sorted(solver_boundaries)],
            'termination_reason': termination,
            'burnout_time_s': (float(burnout_time)
                               if burnout_time is not None else None),
            'time_step_s': float(dt),
        }
    
    @staticmethod
    def _decimate_curve_indices(thrust, pressure=None, keep=(),
                                max_points=SOLID_THRUST_CURVE_MAX_POINTS):
        """Yayımlanacak eğri için TEPEYİ KORUYAN örnek indeksleri.

        v2.6.27 (B2-3'te burada yazıldı, B2-4'te ortak modüle taşındı):
        algoritmanın TEK tanımı artık hrma.analysis.curve_sampling —
        hibrit aynı kusuru (port 5 mm -> 17 317 nokta) aynı koddan çözer,
        iki kopyanın sessizce ayrışması imkânsızlaşır. Bu metot geriye
        dönük yüzey olarak duruyor (testler ve olası dış çağıranlar için);
        davranış bit-aynıdır (taşıma sırasında ölçüldü).
        """
        return _ortak_seyreltme_indeksleri(
            thrust, pressure=pressure, keep=keep, max_points=max_points)

    def _published_thrust_curve(self, curve):
        """Yayımlanan itki eğrisi bloğu — seyreltilmiş ve BEYANLI.

        Türetilmiş büyüklüklerin (toplam impuls, ortalama itki, biçim
        sınıfı, kararlılık, uyarılar) hepsi TAM ÇÖZÜNÜRLÜKLÜ diziden
        hesaplanır; burada seyreltilen yalnız istemciye giden dizidir ve
        bu, blokta adıyla söylenir.
        """
        n = int(np.asarray(curve['time']).size)
        # Zorunlu tutulacak kritik anlar: kullanıcıya bildirilen her olayın
        # eğride bir karşılığı OLMALIDIR, yoksa uyarı ile grafik çelişir.
        # (B2-4: en-yakın-örnek araması ortak modülden; hibritle aynı kod.)
        zaman = np.asarray(curve['time'], dtype=float)
        zorunlu = [
            _en_yakin_ornek(zaman, curve.get('separated_from_t')),
            _en_yakin_ornek(zaman, curve.get('unchoked_from_t')),
            _en_yakin_ornek(zaman, curve.get('burnout_time_s')),
        ]
        idx = self._decimate_curve_indices(
            curve['thrust'], curve.get('pressure'), keep=zorunlu)

        def _al(ad):
            dizi = np.asarray(curve[ad])
            return dizi[idx].tolist() if dizi.size == n else dizi.tolist()

        return {
            'time': _al('time'),
            'thrust': _al('thrust'),
            'pressure': _al('pressure'),
            'burn_area': _al('burn_area'),
            'mass_flow': _al('mass_flow'),
            # v2.6.27 (parti 26): PORT AKIŞ KESİTİ (m²) yayımlanır. Dizi
            # çözücünün kendi zaman marşından gelir (A_port =
            # _port_flow_area(web), :8455) ve erozif kütle akısı G =
            # mdot/A_port ile TEK ve AYNI seridir — burada yeni bir hesap
            # YOKTUR, yalnız var olan seri sözleşmeye eklenmiştir.
            #
            # Neden eklendi: 3B yanma animasyonu (motor_viz3d.js) port
            # yarıçapını, bu alan yayımlanmadığı için, çözücünün kütle üretim
            # özdeşliğinden GERİ TÜRETMEK zorundaydı (w = ∫ mdot/(rho*A_b) dt,
            # trapez). Yayımlanan dizi o türetmeyi gereksiz kılar: dairesel
            # eşdeğer port yarıçapı doğrudan sqrt(A_port/pi)'dir.
            #
            # ÖLÇÜLDÜ (2026-08-16; APCP, D_kamara=100 mm, L=500 mm,
            # D_çekirdek=30 mm, Pc=40 bar) — sqrt(A_port/pi) - r_çekirdek ile
            # istemcinin trapez türetmesi arasındaki fark:
            #   bates 0,026 mm · star 0,031 mm · wagon_wheel 0,028 mm ·
            #   finocyl 0,020 mm  (fark trapezin payı; A_port kapalı form)
            #   slotted 17,3 mm  -> kesit GERÇEKTEN dairesel değil
            #   end_burner       -> dizi SABİT (port yok, tüm kasa kesiti akar)
            # Yani bu alan, dairesel port ailesinde web geçmişiyle AYNI bilgiyi
            # taşır ve onu türetmeden verir; dairesel OLMAYAN ailede ise
            # animasyonun neden modellenmediğinin ölçülebilir kanıtıdır.
            'port_area': _al('port_area'),
            'port_area_basis': (
                'port flow cross-section A_port(t) in m^2, read from the '
                'burn-back solver time march (the same series the erosive '
                'mass flux G = mdot/A_port is divided by). Per grain type '
                '(SolidRocketEngine._port_flow_area): end_burner = full case '
                'cross-section (no port, hence constant); slotted, star and '
                'wagon_wheel = true clipped offset-polygon area; bates and '
                'finocyl = equivalent circular port pi*(r_core + w)^2 (for '
                'finocyl this is the plain, finless section, which is the '
                'narrowest one and therefore carries the highest flux). The '
                'equivalent port diameter is therefore sqrt(4*A_port/pi); it '
                'is a TRUE port radius only where the section is circular.'),
            # Eğri kendi temelini BEYAN eder; dışa aktarım (.eng) bunu
            # dosyaya yazar. v2.6.26 öncesinde beyan yoktu ve dışa
            # aktarım etiketi "solid grain burn-back solver" diye SABİT
            # yazılıydı — hibrit motor da eğri üretmeye başlayınca hibrit
            # dosyalar KATI çözücüsüyle üretilmiş gibi etiketleniyordu.
            'basis': ('solid grain burn-back solver (time-marched): burn '
                      'area from grain regression, chamber pressure from '
                      'the iterative pressure-burn rate fixed point '
                      '(r = a*Pc^n)'),
            # v2.6.27 (B2-3, B2-4'te ortak üreticiye taşındı): dizinin ÇÖZÜM
            # çözünürlüğü değil YAYIN çözünürlüğü olduğu, ve neyin korunduğu
            # açıkça yazılır. Metin şablonu curve_sampling.sampling_block'ta
            # TEK yerde durur; buradaki iki dizge katıya özgü boşlukları
            # doldurur ve önceki elle yazılmış metinle bit-aynıdır (ölçüldü).
            'sampling': _ornekleme_blogu(
                int(idx.size), n, curve.get('time_step_s'),
                'the first samples of flow separation, of loss of choking '
                'and of burnout',
                'total impulse, average thrust, curve shape, stability, '
                'warnings',
                max_points=SOLID_THRUST_CURVE_MAX_POINTS),
            # V301/K-B (NK-28): eğrinin SONU ve düz bölümleri beyanlı.
            'burnout_end': self._curve_burnout_end(curve),
            'regime_boundary_hold': self._curve_boundary_hold_windows(curve),
        }

    @staticmethod
    def _curve_burnout_end(curve):
        """Tükenişte itkinin sıfıra inişi (yarı-durağan modelin ifadesi).

        V301/K-B (NK-28). Ölçüldü (örnek katı KNDX BATES 75 mm): yayımlanan
        eğri 2,2771 s'de 904,2 N'da BİTİYORDU; sıfıra iniş çizilmiyordu.
        Kök: tükeniş kapanışı son örneği t_b'ye kadar tutar (sıfırıncı
        mertebe, integral O(dt²)) ama yarı-durağan modelde web tükenince
        yanma yüzeyi SÜREKSİZ sıfırlanır -> üretim, basınç ve itki o anda
        sıfırdır. Bu blok o adımı adıyla verir; diziler DEĞİŞMEZ (toplam
        impuls ve yanma süresi aynı). Tükeniş sonrası oda boşalması
        (blow-down) modellenmez; iniş bu yüzden basamaktır.
        Basınç sönümüyle bitişte (pressure_collapse) dizi zaten 0'la biter.
        """
        t_b = curve.get('burnout_time_s')
        if (t_b is None or curve.get('termination_reason') not in (
                'web_exhausted', 'burn_area_vanished')):
            return None
        return {
            'time_s': float(t_b),
            'thrust_n': 0.0,
            'pressure_bar': 0.0,
            'basis': ('quasi-steady burn-back model: at web burnout the '
                      'burning surface vanishes, so mass generation, chamber '
                      'pressure and thrust fall to zero at burnout_time_s. '
                      'The last solved sample is held up to burnout '
                      '(zero-order hold closure of the time march). Chamber '
                      'blow-down after burnout is NOT modelled, so the drop '
                      'is a step.'),
        }

    @staticmethod
    def _curve_boundary_hold_windows(curve):
        """Parçalı yanma hızı yasasının rejim sınırında TUTULAN aralıklar.

        V301/K-B (NK-28). Süreksiz yasada (KNDX Nakka tablosu) dengenin iki
        dalda da olmadığı adımlar sınır basıncında tutulur (V301/B6,
        Filippov). Bu aralıkta basınç ve itki SABİTTİR; eskiden yalnız
        ``solver_diagnostics``te sayı olarak duruyordu, grafikte düz çizgi
        beyansız görünüyordu. Ardışık örnek indeksleri pencerelere toplanır.
        """
        idx = sorted(int(i) for i in (
            curve.get('pressure_solver_boundary_step_indices') or []))
        zaman = np.asarray(curve.get('time', []), dtype=float)
        basinc = np.asarray(curve.get('pressure', []), dtype=float)
        if not idx or zaman.size == 0:
            return []
        pencereler, bas = [], [idx[0], idx[0]]
        for i in idx[1:]:
            if i == bas[1] + 1:
                bas[1] = i
            else:
                pencereler.append(tuple(bas))
                bas = [i, i]
        pencereler.append(tuple(bas))
        cikti = []
        for i0, i1 in pencereler:
            if i0 >= zaman.size:
                continue
            j = min(i1 + 1, zaman.size - 1)
            cikti.append({
                't_start_s': float(zaman[i0]),
                't_end_s': float(zaman[j]),
                'held_steps': int(i1 - i0 + 1),
                'pressure_bar': (float(basinc[i0]) if basinc.size > i0
                                 else None),
                'basis': ('chamber pressure held at a regime boundary of '
                          'the piecewise burn-rate law: the law is '
                          'discontinuous there and neither branch has an '
                          'equilibrium (generalised Filippov equilibrium), '
                          'so pressure and thrust are constant in this '
                          'window'),
            })
        return cikti

    def _geometric_throat_area(self):
        """Yayımlanan (imal edilen, Cd'li) boğaz çapının alanı [m²].

        ``_estimate_throat_diameter`` ile AYNI sayı: kullanıcının ekranda
        okuduğu ``throat_diameter``. Boğaz boyutlandırılamıyorsa ``None``
        (o durumun adlı reddi ``_throat_exceeds_case`` / tasarım akışında).
        """
        try:
            d_t = float(self._estimate_throat_diameter())
        except SolidDesignRejected:
            raise
        except Exception:
            return None
        if not np.isfinite(d_t) or d_t <= 0.0:
            return None
        return float(np.pi * d_t * d_t / 4.0)

    def _port_throat_ratio_at_core(self, d_core_m):
        """A_port,0 / A_t (geometrik) — çekirdek ``d_core_m`` olsaydı.

        Boğazı çözücü boyutlandırır (en büyük Kn), yani çekirdek değişince
        boğaz da değişir: oran her çekirdek için YENİDEN çözülür. Geometri
        memoları ``_grain_geometry_key`` ile anahtarlıdır (D_core içerir),
        bayat sonuç dönmez; ``D_core`` her durumda geri konur.
        """
        eski = self.D_core
        try:
            self.D_core = float(d_core_m)
            alanlar = self._port_throat_areas()
        finally:
            self.D_core = eski
        if alanlar is None:
            return None
        return alanlar[0] / alanlar[1]

    def _port_throat_areas(self):
        """``(A_port,0, A_t)`` [m²] — port ⟷ boğaz kapısının TEK ölçütü.

        V301/K-D: kapı (``_check_port_throat``), gereken en küçük çekirdek
        araması (``_port_throat_ratio_at_core``) ve tasarım noktası
        boyutlandırıcısı (``_bates_geometry_for``) bu iki alanı buradan
        okur; kapının sınırı (A_port,0 > A_t) üçünde de aynı sayıdır.
        A_t yayımlanan GEOMETRİK boğazdır (``_geometric_throat_area``),
        A_port,0 çözücünün kesit tanımıdır (``_port_flow_area(0)``). Boğaz
        boyutlandırılamıyorsa ya da port kesiti sonlu değilse ``None``.
        """
        a_t = self._geometric_throat_area()
        if a_t is None:
            return None
        a_p = float(self._port_flow_area(0.0))
        if not np.isfinite(a_p):
            return None
        return a_p, a_t

    def _check_port_throat(self):
        """Başlangıç port alanı boğazdan büyük mü? Değilse RET (KT-23).

        V301/K-A (ana model kararı 5, 22 Eki). ÖLÇÜLDÜ (``A-kati``
        denetimi, ``port_bogaz.txt``): çekirdek 10 mm'de başlangıç port
        alanı 78,5 mm², çözücünün boğazı 563,7 mm² iken motor
        ``CALCULATED`` + ``choked = True`` yayımlıyordu; akış porttan
        geçerken boğulur, lüle boğazı sonik nokta DEĞİLDİR (Sutton &
        Biblarz 9. baskı Böl. 12, port/boğaz alan oranı ve erozif yanma).
        A_port,0 ≤ A_t ise tasarım yayımlanmaz: ``SolidDesignRejected`` ->
        uçta 422 ``port_smaller_than_throat``. 1 < oran < 2 bandının UYARISI
        (``warn.solid.port_to_throat_low``) aynen kalır.

        Sınır 1 bir ayar sayısı değildir: boğulmanın tanımıdır (en küçük
        akış kesiti sonik noktadır). Karşılaştırılan boğaz YAYIMLANAN
        (geometrik) boğazdır — kullanıcı ret cümlesini ekrandaki çaplarla
        doğrulayabilir; etkin (Cd'li) boğazdan büyük olduğu için kapı daha
        sıkıdır (fail-closed).

        Gereken en küçük çekirdek: oran çekirdeğe göre yeniden çözülerek
        ikiye bölmeyle bulunur, 0,1 mm'ye yukarı yuvarlanır ve yuvarlanmış
        değerin kapıdan geçtiği DOĞRULANIR. Tane içinde böyle bir çekirdek
        yoksa ``required_min`` None'dır ve cümle bunu söyler.
        """
        alanlar = self._port_throat_areas()
        if alanlar is None or alanlar[0] > alanlar[1]:
            return
        a_p, a_t = alanlar
        d_core_mm = float(self.D_core) * 1000.0
        d_t_mm = float(np.sqrt(4.0 * a_t / np.pi)) * 1000.0
        tane_mm = float(self.D_chamber) * 1000.0
        gereken_mm = None
        if self.grain_type != 'end_burner':
            # Üst arama sınırı: tanenin içinde kalan en büyük çekirdek
            # (web > 0). Uç katmanının imalat payı ayrıca uygulanır; burada
            # yalnız fiziksel sınır aranır.
            ust = float(self.D_chamber) * (1.0 - 1e-6)
            alt = float(self.D_core)
            r_ust = self._port_throat_ratio_at_core(ust)
            if r_ust is not None and r_ust > 1.0:
                for _ in range(40):
                    if ust - alt <= 1e-5:      # 0,01 mm
                        break
                    orta = 0.5 * (alt + ust)
                    r = self._port_throat_ratio_at_core(orta)
                    if r is not None and r > 1.0:
                        ust = orta
                    else:
                        alt = orta
                aday = _ceil_tenth_mm(ust * 1000.0)
                # Yuvarlanan öneri kapıdan GEÇMELİ (monoton olmayan aile
                # için birkaç 0,1 mm adımı); geçmezse öneri yayımlanmaz.
                for _ in range(20):
                    if aday >= tane_mm:
                        break
                    r = self._port_throat_ratio_at_core(aday / 1000.0)
                    if r is not None and r > 1.0:
                        gereken_mm = aday
                        break
                    aday = round(aday + 0.1, 1)
        oran = a_p / a_t
        if gereken_mm is not None:
            eylem = (f'Enter a core diameter of at least {gereken_mm:.1f} mm '
                     f'(the throat is re-sized with the core), or lower the '
                     f'burning area or raise the chamber pressure')
        elif self.grain_type == 'end_burner':
            eylem = ('An end burner flows through the full grain cross-'
                     'section, so enlarge the grain outer diameter or reduce '
                     'the burning area / raise the chamber pressure')
        else:
            eylem = (f'No core diameter inside the {tane_mm:g} mm grain makes '
                     f'the port larger than the throat; enlarge the grain '
                     f'outer diameter, shorten the grain or raise the chamber '
                     f'pressure')
        mesaj = (
            f'No design was published: the initial port flow area '
            f'{a_p * 1e6:.1f} mm^2 (core diameter {d_core_mm:g} mm, '
            f'{self.grain_type}) is not larger than the throat area '
            f'{a_t * 1e6:.1f} mm^2 (throat diameter {d_t_mm:.2f} mm, sized by '
            f'the solver), port/throat area ratio {oran:.3f}. The flow would '
            f'choke in the port, not at the nozzle throat. {eylem}.')
        raise SolidDesignRejected(mesaj, [{
            'field': 'core_diameter',
            'reason': 'port_smaller_than_throat',
            'submitted': d_core_mm,
            'required_min': gereken_mm,
            'unit': 'mm',
            'grain_type': self.grain_type,
            'initial_port_area_mm2': a_p * 1e6,
            'throat_area_mm2': a_t * 1e6,
            'throat_diameter_mm': d_t_mm,
            'port_to_throat_area_ratio': oran,
            'limit': 'A_port,0 > A_throat (choking at the nozzle throat)',
            'motor_form': 'solid',
            'message': mesaj,
        }], 'port_smaller_than_throat')

    def calculate_performance(self):
        """Calculate overall motor performance with comprehensive analysis"""
        # V301/K-A (KT-23): port boğazdan küçükse eğri hiç koşmaz (RET).
        #
        # V301/K-D (T-çapa-A DEVİR 4 + T-çapa-B DEVİR 1) — KAPI SIRASI.
        # Port kapısının ölçtüğü boğaz, tasarım basıncındaki kararlı denge
        # için boyutlandırılır: A_t = ρ·A_b·r(P_c)·c*/P_c. Bu boğaz bir
        # çalışma noktası tanımlar ancak yanma hızı üssü n < 1 ise:
        # P_c = (K_n·a·ρ·c*)^(1/(1−n)) dengesi yalnız n < 1'de vardır ve
        # kararlıdır (Sutton & Biblarz 9. baskı Böl. 12, yanma hızı ve oda
        # basıncı dengesi). n = 1'de kütle dengesi P_c'den bağımsızdır
        # (A_t = ρ·A_b·a·c*: o boğaz HİÇBİR basıncı seçmez), n > 1'de denge
        # kararsızdır. Yani n ≥ 1'de "port boğazdan küçük" hükmü var olmayan
        # bir çalışma noktasının boğazına göre verilir; kullanıcıya doğru
        # söylenecek şey, geometriden BAĞIMSIZ olan "çözüm yok"tur
        # (çekirdeği büyütmek motoru çözülür yapmaz). Bu yüzden n ≥ 1'de
        # önce çözücü koşar ve yakınsamama tanısı (``solver_diagnostics``)
        # olduğu gibi döner; çözücü yine de yakınsarsa port kapısı eğriden
        # SONRA uygulanır (kapı atlanmaz). n < 1'de denge vardır ve kapı
        # çözücünün modelinin ÖNKOŞULUDUR (lüle boğazı sonik nokta olmalı):
        # kapı eğriden önce koşar, boğulan portta çözücü sonucu zaten
        # geçersiz bir modelin sonucudur.
        #
        # Tasarım noktası hedefi TUTTURULAMADIYSA (``design_point_not_
        # reached``) motorun geometrisi çözücüye verilen TOHUM geometridir,
        # istenen tasarım değildir: o tohumun port hükmü isteğin cevabı
        # olamaz ve zarf reddinin önüne geçemez (uç 422 ``TARGET_NOT_MET``
        # ile zarfı söyler). Kapı yalnız boyutlandırılmış ya da kullanıcının
        # verdiği geometride uygulanır.
        _tohum_geometri = ((getattr(self, 'design_point', None) or {})
                           .get('status') == DESIGN_POINT_STATUS_NOT_REACHED)
        _n_denge_yok = float(self.n) >= 1.0
        if not _tohum_geometri and not _n_denge_yok:
            self._check_port_throat()
        # Get thrust curve
        curve = self.calculate_thrust_curve()

        if len(curve['time']) == 0:
            return {'error': 'Invalid grain geometry',
                    'error_i18n': _w('warn.solid.invalid_grain_geometry',
                                     'critical')}

        # --- YAKINSAMA KAPISI (Faz 4B, bulgu B2) ---------------------------
        # Basınç sabit-nokta çözücüsü v2.6.25'ten beri gerçek durumunu
        # raporluyor (convergence_achieved, başarısız adım sayısı, en büyük
        # artık, tolerans, termination_reason) — ama KİMSE OKUMUYORDU:
        # design_summary.status koşulsuz 'CALCULATED' yazıyor, performans ve
        # imalata giden cad_design tam olarak üretiliyordu.
        #
        # ÖLÇÜM (2 Ağustos 2026, HEAD a7ff1e7; APCP, D_kamara=100 mm, L=500 mm,
        # D_çekirdek=30 mm, Pc=40 bar, a=0.005):
        #   n=0.35 -> yakınsadı, 0/219 adım
        #   n=0.90 -> 122/204 adım başarısız, artık 1.03e-3, term=web_exhausted
        #   n=0.95 ->  96/129 adım başarısız, artık 1.21e-2,
        #              term=pressure_collapse
        #   n=1.00 ->   1/35  adım başarısız,               term=burn_rate_zero
        # Üçünde de status='CALCULATED', Isp dolu, cad_design 9 anahtar doluydu.
        #
        # KAPI NEDEN İKİ KADEMELİ: ilk denemede "bir adım bile başarısızsa sonuç
        # yok" kuralı yazıldı ve deponun KENDİ kataloğundaki KNDX'i (n=0.688)
        # meşru bir çalışma noktasında kesti. Ölçüldü (KNDX, Pc=90 bar):
        # 7/164 adım başarısız, artık %1.19, term=web_exhausted — ama tolerans
        # 1e-6'dan 1e-2'ye gevşetildiğinde toplam impuls yalnız %0.067
        # değişiyor. Yani orada çözüm pratikte oturmuş, tepe basıncı
        # civarındaki birkaç adım 100 iterasyon tavanına takılmış. Bunu
        # "sonuç yok" saymak yanlış olurdu.
        #
        # Ayrım SAYISAL EŞİKLE değil FİZİKLE yapılır:
        #   1. KADEME (sonuç üretilmez): yakınsama yok VE yanma anormal bitmiş
        #      (safety_limit / throat_eroded_out / not_started), YA DA
        #      yakınsama yok VE n >= 1. Birincisinde yanma süresi, toplam
        #      impuls ve tüm CAD ölçüleri var olmayan bir motoru tarif eder;
        #      ikincisinde sabit-nokta daralma savı tümden geçersiz olduğu için
        #      hiçbir adımın basıncına güvenilemez.
        #      (Hangi sonun "anormal" sayıldığı aşağıda gerekçesiyle yazılı —
        #      ilk denemede pressure_collapse anormal sanılmış ve deponun kendi
        #      yıldız grainli KNDX örneği kesilmişti.)
        #   2. KADEME (sonuç üretilir ama etiketi düşürülür): yanma normal
        #      bitmiş, n < 1, yalnız bazı adımlar tavana takılmış. Burada
        #      zaten bir kullanıcı uyarısı ateşleniyordu; YALAN SÖYLEYEN tek
        #      alan status idi. Artık status uyarıyla aynı şeyi söyler
        #      (aşağıdaki design_summary bloğu).
        #
        # Kapı, depoda ZATEN var olan hata sözleşmesini kullanır (yukarıdaki
        # 'Invalid grain geometry' dalıyla aynı biçim). Bu sözleşmeyi çağıranlar
        # hâlihazırda tanıyor: run_monte_carlo (:3803, :3847), uq_adapters
        # (:351) ve solid.html (:2929) `error` anahtarını kontrol ediyor.
        yakinsadi = bool(curve.get('convergence_achieved', True))
        # Yanmanın NORMAL bittiği sonlar. 'pressure_collapse' ve
        # 'burn_rate_zero' buraya DAHİLDİR: çözücünün kendi tükeniş kapanışı
        # (:6472-6474) tam olarak bu iki sonu burnout sayıp eğriye sıfır itkili
        # son noktayı ekliyor. Yıldız/finocyl grainde yanan alan tükenişte
        # sonlu bir değerden sıfıra düştüğü için basıncın çökmesi yanmanın
        # DOĞAL sonudur, bir sapma değil — ölçüldü: katalog KNDX'i yıldız
        # grainle Pc=40 bar'da term='pressure_collapse' ile bitiyor ve sonuç
        # sağlıklı. Gerçekten anormal olan sonlar aşağıdakilerdir: motor
        # emniyet sınırına dayandı, boğaz tamamen aşındı ya da hiç başlamadı.
        normal_bitti = curve.get('termination_reason') not in (
            'safety_limit', 'throat_eroded_out', 'not_started')
        self._solver_converged = yakinsadi
        if not yakinsadi and (not normal_bitti or float(self.n) >= 1.0):
            basarisiz = int(curve.get('pressure_solver_failed_steps', 0) or 0)
            toplam = int(curve.get('pressure_solver_steps', 0) or 0)
            artik = float(curve.get('pressure_solver_max_residual', 0.0) or 0.0)
            tol = float(curve.get('pressure_solver_tolerance', 0.0) or 0.0)
            uyari = _w('warn.solid.pressure_solver_not_converged', 'critical',
                       failed_steps=basarisiz, total_steps=toplam,
                       max_residual=artik, tolerance=tol)
            # Sağlık uyarılarının TAMAMI ulaşmalı (n >= 1 uyarısı, erozyon,
            # port/boğaz oranı ...): kapı, kullanıcının teşhis bilgisini
            # kısmamalı — asıl şimdi lazım.
            tum_uyarilar = (list(self.design_warnings) + [uyari]
                            + self._design_health_warnings(curve))
            gerekce = ('the burn did not run to completion '
                       f"(termination: {curve.get('termination_reason')})"
                       if not normal_bitti else
                       f'the burn-rate exponent n = {float(self.n):.3f} is not '
                       f'below 1, so the damped fixed-point iteration is not a '
                       f'contraction and its iterates cannot be trusted')
            return {
                'error': (
                    f'Chamber pressure solver did not converge and {gerekce}. '
                    f'{basarisiz} of {toplam} time steps exceeded the '
                    f'tolerance (largest relative residual {artik:.3g} versus '
                    f'tolerance {tol:.1e}). No performance, CAD or '
                    f'acceptability result is produced from this solution.'),
                'error_i18n': uyari,
                'status': DESIGN_STATUS_NOT_CONVERGED,
                'solver_diagnostics': {
                    'convergence_achieved': False,
                    'pressure_solver_steps': toplam,
                    'pressure_solver_failed_steps': basarisiz,
                    'pressure_solver_max_residual': artik,
                    'pressure_solver_tolerance': tol,
                    'termination_reason': curve.get('termination_reason'),
                    'burn_rate_exponent': float(self.n),
                    'time_step_s': curve.get('time_step_s'),
                    **self._pressure_solver_boundary_publication(curve),
                },
                # Son (KABUL EDİLMEYEN) iterat yalnız teşhis içindir: adı
                # performans alanlarıyla karışmayacak biçimde seçilmiştir ve
                # hiçbir tüketici bunu sonuç sayamaz.
                'non_converged_last_iterate_diagnostic_only': {
                    'note': ('Values from the final, rejected iterate of a '
                             'solve that did not converge. They are NOT a '
                             'motor result and must not be reported as '
                             'performance.'),
                    'sample_count': int(len(curve['time'])),
                    'last_sample_time_s': float(curve['time'][-1]),
                    'max_chamber_pressure_bar': (
                        float(np.max(curve['pressure']))
                        if len(curve['pressure']) else None),
                },
                'design_warnings': tum_uyarilar,
                'warnings': tum_uyarilar,
            }

        # V301/K-D: n ≥ 1'de çözücü yakınsadıysa port kapısı burada (sıranın
        # gerekçesi yukarıda, ``_n_denge_yok``). Kapı atlanmaz.
        if not _tohum_geometri and _n_denge_yok:
            self._check_port_throat()

        # Calculate performance metrics
        burn_time = curve['time'][-1]
        max_thrust = np.max(curve['thrust'])
        total_impulse = _trapezoid(curve['thrust'], curve['time'])
        # Ortalama itki ZAMAN AĞIRLIKLI tanımdan gelir: F_ort = I_t / t_b
        # (Sutton & Biblarz 9. baskı, Böl. 2). Eski np.mean(örnekler) örnek
        # yerleşimine duyarlıydı: tükeniş kapanışıyla son aralık dt'den kısa
        # olduğu için düz ortalama son düşük-itki noktasını fazla ağırlıklıyor,
        # ayrıca dt'ye bağımlıydı (dt=0.05 -> 6739 N, dt=0.0005 -> 6805 N,
        # %1.0 yayılım). Zaman ağırlıklı tanımın yayılımı %0.12 (2026-07-19).
        avg_thrust = (float(total_impulse) / float(burn_time)
                      if burn_time > 0 else float(np.mean(curve['thrust'])))
        # Maliyet modeli geliştirme ölçeği için (parametrik tahmin)
        self._last_total_impulse = float(total_impulse)
        # Geçici kasa ısınması yanma süresine bağlıdır — termal analiz bunu okur
        self._last_burn_time = float(burn_time)
        self._last_average_isp = (float(total_impulse
                                        / (self._propellant_volume()
                                           * self.rho_p * self.g0))
                                  if self._propellant_volume() > 0 else 0.0)

        # Detailed analysis like other systems
        detailed_analysis = self._calculate_detailed_analysis(curve)
        structural_analysis = self._calculate_structural_analysis()
        thermal_analysis = self._calculate_thermal_analysis(curve)
        manufacturing_analysis = self._calculate_manufacturing_analysis()
        flight_simulation = self._calculate_flight_simulation()
        cost_analysis = self._calculate_cost_analysis()
        
        # Yakıt kütlesi hesabı (fiziksel kontrol)
        outer_radius = self.D_chamber / 2
        inner_radius = self.D_core / 2
        
        # Bu koşuya özgü (kurulum sırasında DEĞİL, hesap sırasında doğan)
        # kullanıcı uyarıları. self.design_warnings'e YAZILMAZ: aynı motor
        # nesnesiyle calculate_performance() birden çok kez çağrıldığında
        # (Monte Carlo, UQ) uyarılar birikip tekrarlanırdı.
        run_warnings = []

        # Geometri kontrolü
        if inner_radius >= outer_radius:
            return {'error': 'Core çapı oda çapından büyük olamaz',
                    'error_i18n': _w('warn.solid.core_diameter_exceeds_chamber',
                                     'critical')}
        if self.L_grain <= 0:
            return {'error': 'Grain uzunluğu pozitif olmalı',
                    'error_i18n': _w('warn.solid.grain_length_not_positive',
                                     'critical')}


        # Grain tipine göre gerçek hacim (star=poligon, end_burner=tam
        # silindir, wagon=7 delik düşülmüş) — annulus yalnız BATES için doğru
        grain_volume = self._propellant_volume()
        propellant_mass = grain_volume * self.rho_p
        
        # Kütle kontrolü
        if propellant_mass <= 0:
            return {'error': 'Yakıt kütlesi pozitif olmalı',
                    'error_i18n': _w('warn.solid.propellant_mass_not_positive',
                                     'critical')}

        # Sea level specific impulse
        isp_sea_level = total_impulse / (propellant_mass * self.g0)
        
        # Vakum özgül itkisi — YANITIN KENDİ CF ZİNCİRİNDEN (v2.6.27, F2-2).
        #
        # Burada ``hrma.constants.vacuum_isp_ratio()`` ampirik log-fiti
        # (0,953 + 0,0405·ln ε) deniz seviyesi Isp'sini ölçekliyordu. O çarpan
        # HAZNE BASINCINI görmez; gerçek oran CF_vac/CF_SL = 1 + (P_a/P_c)·ε/CF_SL
        # olduğundan P_c'ye doğrudan bağlıdır. Ölçülen çelişki ve gerekçe
        # ``_thrust_coefficient_vacuum`` docstring'indedir (40 bar'da %6,71).
        #
        # Vakum impulsu deniz seviyesi impulsuyla AYNI integralden çıkar,
        # yalnız itki katsayısı değişir:
        #     F(t) = CF · P_c(t) · A_t(t)   ->   F_vac(t) = CF_vac · P_c(t) · A_t(t)
        # CF_vac ortam basıncından bağımsız olduğu için zaman içinde sabittir;
        # yine de integral nokta nokta alınır ki toplam impulsla aynı sayısal
        # yol (np.trapz, aynı örnekler) kullanılsın.
        cf_vacuum = self._thrust_coefficient_vacuum()
        vacuum_thrust_series = (cf_vacuum
                                * np.asarray(curve['pressure'], dtype=float)
                                * 1e5
                                * np.asarray(curve['throat_area_series'],
                                             dtype=float))
        total_impulse_vacuum = float(_trapezoid(vacuum_thrust_series,
                                              curve['time']))
        isp_vacuum = total_impulse_vacuum / (propellant_mass * self.g0)
        isp_vacuum_basis = (
            'CF_vac x Pc x A_t integrated over the same thrust curve as the '
            'sea-level impulse (Sutton & Biblarz Eq. 3-30/3-31 with Pa = 0); '
            'this is THIS motor\'s fixed nozzle in vacuum, not a '
            'vacuum-optimised nozzle. Replaces the empirical log fit that did '
            'not see chamber pressure.')

        # Değer doğrulama — eskiden yalnız stdout'a basılıyordu (kullanıcı
        # arayüzde GÖREMİYORDU). Artık uyarı listesine giriyor: hem görünür
        # hem iki dilli. Eşikler ve koşullar birebir aynı.
        if isp_sea_level < 50 or isp_sea_level > 500:
            run_warnings.append(_w('warn.solid.isp_out_of_range', 'warning',
                                   isp_s=round(isp_sea_level, 1)))
        if total_impulse < 100 or total_impulse > 1e8:
            run_warnings.append(_w('warn.solid.total_impulse_out_of_range',
                                   'warning',
                                   total_impulse_Ns=round(total_impulse)))

        # Boğaz çapı: itki eğrisinde tasarım noktasında BİR KEZ boyutlandırılan
        # sabit boğaz kullanılır (Kn ve basınç eğrisiyle tutarlılık için)
        A_t = curve.get('throat_area', 0.0)
        if not A_t or A_t <= 0:
            # Fallback (eski yöntem): maksimum kütle akışından boyutlandır
            max_mdot = np.max(curve['mass_flow'])
            A_t = max_mdot * self.c_star / (self.P_c * 1e5)
        # Raporlanan (imal edilecek) boğaz GEOMETRİK alandır: kullanıcı boğaz
        # akış katsayısı verdiyse A_geom = A_etkin / Cd. Basınç ve itki hâlâ
        # etkin alandan çözülür; Cd verilmezse (1.0) davranış değişmez.
        cd_throat = getattr(self, 'discharge_coeff', 1.0)
        A_t_geometric = A_t / cd_throat if 0.0 < cd_throat < 1.0 else A_t
        d_throat = 2 * np.sqrt(A_t_geometric / np.pi)


        # Boğaz alanı kontrolü
        if A_t <= 0:
            return {'error': 'Boğaz alanı pozitif olmalı',
                    'error_i18n': _w('warn.solid.throat_area_not_positive',
                                     'critical')}
        if d_throat < 0.001 or d_throat > 0.5:  # 1mm - 500mm arası makul
            run_warnings.append(_w('warn.solid.throat_diameter_out_of_range',
                                   'warning',
                                   throat_diameter_mm=round(d_throat * 1000, 1)))

        # OPUS DENETİM DÜZELTMESİ (major): Aynı motor için 3 farklı ε
        # üretiliyordu (top-level 8.0 hardcode, CAD 5.93 hesaplı, vakum 40
        # hardcode) → iki farklı çıkış çapı raporlanıyordu. TEK kaynak:
        # _estimate_expansion_ratio() (deniz seviyesi Pe=Pa izentropik çözümü).
        epsilon_sea_level = self._estimate_expansion_ratio()
        # ------------------------------------------------------------------
        # ÖH D15 a2 (P2B3-07) — ÇIKIŞ ÇAPI ETKİN BOĞAZDAN KURULUR.
        # epsilon = A_e / A_t_ETKİN olarak tanımlıdır ve itki katsayısı onu
        # kullanır; eski satır çıkış çapını Cd ile ŞİŞİRİLMİŞ GEOMETRİK
        # boğazdan türetiyordu (d_exit = d_throat_geom * sqrt(eps)), yani
        # çizilen (d_boğaz, d_çıkış) çifti inşa edilse gazın göreceği oran
        # yayımlanan epsilon DEĞİLDİ. ÖLÇÜLDÜ (APCP 100/30/500, 40 bar):
        #   Cd      yayımlanan eps   çizilen lülenin gerçek eps   sapma
        #   1,00        5,9317              5,9317               %0,00
        #   0,98        5,9317              6,0528              +%2,04  <- UI
        #   0,90        5,9317              6,5908             +%11,11
        #   0,70        5,9317              8,4739             +%42,86
        # Cd = 0,98 formun HER isteğinde gönderildiği için sapma varsayılan
        # koşuda da vardı. Çıkışta vena contracta yoktur: A_e doğrudan
        # eps * A_t_etkin'dir, dolayısıyla d_exit Cd'den BAĞIMSIZDIR ve
        # Cd = 1 hâlindeki değerle bit-aynı kalır (davranış değişmez).
        # İmalatçı için geometrik oran ayrıca yayımlanır (throat_sizing).
        # ------------------------------------------------------------------
        A_exit = epsilon_sea_level * A_t
        d_exit = 2 * np.sqrt(A_exit / np.pi)
        epsilon_geometric = A_exit / A_t_geometric if A_t_geometric > 0 else None

        # Vakum ε'su: pratik üst sınır (ayrılma/kütle sınırı) — deniz
        # seviyesi değerinin katı olarak, 40'ı aşmayan bir tahmin.
        #
        # F2-2 AYRIMI (v2.6.27): bu ε ve ondan türeyen çıkış çapı, ÖNERİLEN
        # bir vakum lülesine aittir — bu motorun İMAL EDİLEN lülesine değil.
        # 'isp_vacuum' ise bu motorun KENDİ (ε = epsilon_sea_level) lülesinin
        # vakumdaki performansıdır. İki sayı komşu anahtarlarda durduğu için
        # ayrım adıyla beyan edilir; aksi hâlde kullanıcı Isp'yi bu ε ile
        # üretilmiş sanır.
        epsilon_vacuum = min(40.0, max(4.0 * epsilon_sea_level, 25.0))
        # P2B3-07 ile aynı gerekçe: önerilen vakum lülesinin çıkış alanı da
        # ETKİN boğaza göre kurulur (eps = A_e/A_t_etkin).
        d_exit_vacuum = 2 * np.sqrt(epsilon_vacuum * A_t / np.pi)
        expansion_ratio_vacuum_basis = (
            'SUGGESTED vacuum-optimised nozzle (4x the sea-level expansion '
            'ratio, capped at 40 for separation/mass limits). This motor is '
            f'not built with it: the delivered nozzle has eps = '
            f'{epsilon_sea_level:.3f} and isp_vacuum is computed for THAT '
            'nozzle.')
        
        # Çıkış çapı fiziksel kontrolü
        if d_throat <= 0:
            return {'error': 'Boğaz çapı pozitif olmalı',
                    'error_i18n': _w('warn.solid.throat_diameter_not_positive',
                                     'critical')}
        if d_exit > SOLID_EXIT_DIAMETER_ABSOLUTE_LIMIT_M:
            run_warnings.append(_w('warn.solid.exit_diameter_large', 'warning',
                                   exit_diameter_mm=round(d_exit * 1000, 1)))
        # --- ÖH D26 a2 (OH-D25-07 / OH-D19-20'nin kapanmayan yarımı) -------
        # Yukarıdaki kapı MUTLAK bir çaptır (1000 mm): motorun KENDİ
        # gövdesinden bağımsızdır ve küçük motorlarda hiç ateşlenmez.
        # ÖLÇÜLDÜ (docs/scofield/raw/OH/D26/kati/a2/once.json; APCP bates):
        #
        #   gövde                              çıkış     çıkış/gövde  uyarı
        #   D 100 / L 500 / c 30 / 40 bar / 25 km  316,16 mm  3,16x   YOK
        #   D  80 / L 900 / c 20 / 60 bar / 20 km  298,27 mm  3,73x   YOK
        #   D 150 / L1500 / c 40 / 50 bar / 30 km  956,19 mm  6,37x   YOK
        #
        # Üçünde de lüle konisi motorun gövde zarfının DIŞINA taşıyor ve
        # kullanıcı bunu hiçbir alandan öğrenemiyordu (mutlak eşik 1000 mm
        # olduğu için üçünde de sessiz). Kapı artık motorun kendi çapına
        # GÖRELİDİR; oran ve iki çap birlikte bildirilir. Bu bir ret değil
        # bir zarf bildirimidir: irtifa lülesi gövdeden geniş olabilir, ama
        # gövde borusunun bunu kaldırdığı KULLANICININ kararıdır.
        if (np.isfinite(d_exit) and float(self.D_chamber) > 0
                and d_exit > float(self.D_chamber)):
            run_warnings.append(_w(
                'warn.solid.exit_cone_exceeds_case', 'warning',
                exit_diameter_mm=round(d_exit * 1000, 1),
                case_diameter_mm=round(float(self.D_chamber) * 1000, 1),
                ratio=round(d_exit / float(self.D_chamber), 2)))

        # Altitude performance analysis
        altitudes = [0, 1000, 5000, 10000, 20000, 50000, 80000, 100000]  # m
        altitude_performance = self.calculate_altitude_performance(altitudes)
        
        # Environmental conditions analysis
        environmental_analysis = self._calculate_environmental_effects()
        
        # Safety analysis
        safety_analysis = self._calculate_safety_analysis(curve)
        
        # Quality control analysis
        quality_analysis = self._calculate_quality_analysis()
        
        # Advanced performance calculations
        advanced_performance = self._calculate_advanced_performance(curve)

        # --- Nozzle Angles ---
        # Nozzle geometry derived from thrust-curve throat diameter
        # (d_throat already computed above from max mass flow).
        # Yarı açılar KULLANICI GİRDİSİNDEN gelir (_nozzle_half_angles);
        # raporlanan açı ile uzunluğu üreten açı aynı olmak ZORUNDA.
        nozzle_conv_half, nozzle_div_half = self._nozzle_half_angles()
        # ÖH D18 (P2B3-13): AYNI kısıt burada da geçerlidir ve ihraç zinciri
        # (export/motor_geometry.py:511) ÖNCE bu alanı okur — kapı yalnız
        # cad_design.nozzle_design'a konsaydı negatif boy STEP/STL yoluna
        # buradan sızmaya devam ederdi.
        _throat_exceeds_case = self._throat_exceeds_case(d_throat)
        nozzle_conv_length = (
            None if _throat_exceeds_case else
            (self.D_chamber - d_throat) / (2 * np.tan(np.radians(nozzle_conv_half))))
        nozzle_div_length  = (d_exit - d_throat) / (2 * np.tan(np.radians(nozzle_div_half)))
        nozzle_total_length = (
            None if nozzle_conv_length is None
            else max(nozzle_conv_length + nozzle_div_length, 0.01))

        nozzle_angles = {
            'convergent_half_angle_deg': nozzle_conv_half,
            'divergent_half_angle_deg': nozzle_div_half,
            'angles_source': (
                'user_input' if (self.convergent_half_angle_deg is not None
                                 or self.divergent_half_angle_deg is not None)
                else 'conical_default_30_15'),
            'nozzle_type': 'conical',
            'throat_diameter_mm': d_throat * 1000,
            'exit_diameter_mm': d_exit * 1000,
            'nozzle_length_mm': (None if nozzle_total_length is None
                                 else nozzle_total_length * 1000),
            'convergent_length_mm': (None if nozzle_conv_length is None
                                     else nozzle_conv_length * 1000),
            'divergent_length_mm': nozzle_div_length * 1000,
            'throat_exceeds_case': _throat_exceeds_case,
            'convergent_length_status': (
                'not_physical' if _throat_exceeds_case else 'computed'),
            'convergent_length_basis': (
                ('throat %.3f mm is not smaller than the grain outer diameter '
                 '%.3f mm: there is no converging section, so no length (and '
                 'no total contour length) is published'
                 % (d_throat * 1000, self.D_chamber * 1000))
                if _throat_exceeds_case else
                '(D_case - d_throat)/(2 tan(convergent half-angle))'),
            'expansion_ratio': epsilon_sea_level,
        }

        # --- Grain Design ---
        # ÖH D15 a2 (P2B4-02): en ince kesit TEK kaynaktan ve grain tipine
        # duyarlı. Eskiden burada tipe kör (D_kamara - D_çekirdek)/2 duruyordu
        # ve altı grain tipinde de 35,0 mm yayımlanıyordu.
        web_thickness_val = self._geometric_web_thickness()  # m veya None

        # Chamber volume (cylindrical envelope) — segment aralarını da kapsar
        # (grain_gap kablolaması, v2.6.26); kapak payı (0.1 m) hariç.
        # ÖH D15 a2 (P2B4-05): TEK tanım noktası _grain_envelope_volume;
        # advanced_performance bloğu da aynı hacmi okur.
        chamber_volume = self._grain_envelope_volume()  # m^3

        # Volumetric loading fraction
        vol_loading = grain_volume / chamber_volume if chamber_volume > 0 else 0.0

        # Kasa serbest hacmi: kapaklar dahil iç hacim − yakıt hacmi. Formun
        # 'chamber_volume' (Case Internal Volume, L) alanı bu büyüklüğün
        # kullanıcı beyanıdır; çözücü girdisi değildir, tutarlılık için
        # hesaplananla karşılaştırılır (aşağıda) ve raporlanır.
        # TEK tanım noktası: ateşleyici boyutlandırması aynı hacmi okur.
        case_free_volume = self._case_free_volume()  # m^3

        # Initial and final burn areas for Kn calculation
        A_burn_initial = self.calculate_burn_area(0.0)  # web=0 -> initial
        # Dış yüzey de yanıyorsa web İKİ cepheden tükenir: tükeniş yarı webde
        # olur, Kn_final o gerçek tükeniş noktasının hemen öncesinde ölçülür.
        # NOT (ÖH D15 a2): buradaki 'radyal web' Kn_final'in ÖLÇÜM DERİNLİĞİdir
        # ve yayımlanan web alanlarından ayrıdır — bilerek eski tanımda
        # bırakıldı ki A_burn_final / burn_profile / Kn_final sayıları bu
        # kalemin kapsamı dışında oynamasın.
        web_probe = (self.D_chamber - self.D_core) / 2
        if self.grain_type == 'bates' and not getattr(self, 'inhibit_outer',
                                                      True):
            web_probe = web_probe / 2.0
        A_burn_final   = self.calculate_burn_area(web_probe * 0.99)  # near burnout

        # ------------------------------------------------------------------
        # Girdi-türetilen tutarlılık denetimleri (D1-KATI-OLU-1, ADIM 1):
        # bu üç alan çözücüde TÜRETİLEN büyüklüklerdir; kullanıcı girdisi
        # sessizce yok sayılamaz — belirgin sapma uyarıya dönüşür.
        # ------------------------------------------------------------------
        web_user_mm = self._override_val('web_thickness',
                                         *SOLID_WEB_THICKNESS_RANGE_MM)
        web_derived_mm = ((web_thickness_val * 1000.0)
                          if web_thickness_val is not None else 0.0)
        if (self.grain_type == 'bates' and web_user_mm is not None
                and web_derived_mm > 0
                and abs(web_user_mm - web_derived_mm) / web_derived_mm > 0.20):
            run_warnings.append(dict(_w(
                'warn.solid.web_thickness_inconsistent', 'warning',
                entered_mm=round(web_user_mm, 1),
                derived_mm=round(web_derived_mm, 1)),
                fallback=('Entered web thickness {entered_mm} mm differs from '
                          'the value implied by the grain geometry '
                          '({derived_mm} mm = (outer - core)/2). The solver '
                          'uses the geometric value.')))

        # Kalem 29: 'outer_diameter' artık grain dış çapının doğruluk
        # kaynağıdır (bkz. _apply_overrides 7c), bu yüzden eski
        # "alan kullanılmıyor" uyarısı KALKTI. V301/K-A (KT-01): kasa
        # beyanının sığma denetimi artık burada UYARI değil, kurucuda RET'tir
        # (``_check_case_fit`` -> 422 ``grain_does_not_fit_case``). Buraya
        # ulaşan her beyan sığar; ``warn.solid.case_bore_too_small`` ve
        # "kasa geometrik en küçüğe büyütüldü" yolu kalktı.

        cv_user_l = self._override_val('chamber_volume', 1e-3, 1e5)  # L
        cv_calc_l = case_free_volume * 1000.0
        if (cv_user_l is not None and cv_calc_l > 0
                and abs(cv_user_l - cv_calc_l) / cv_calc_l > 0.20):
            run_warnings.append(dict(_w(
                'warn.solid.case_volume_inconsistent', 'warning',
                entered_l=round(cv_user_l, 2),
                derived_l=round(cv_calc_l, 2)),
                fallback=('Entered case internal (free) volume {entered_l} L '
                          'differs from the geometric value {derived_l} L '
                          '(case interior minus propellant). The solver uses '
                          'the geometric value.')))

        # Kn = burn area / throat area
        # ------------------------------------------------------------------
        # ÖH D15 a2 (P2B4-03) — Kn BASINCI ÜRETEN ALANDAN OKUNUR.
        # Eski satır boğaz alanını yayımlanan GEOMETRİK çaptan geri
        # hesaplıyordu (A = pi*(d_throat_geom/2)^2), yani Cd ile şişirilmiş
        # alanı kullanıyordu. Oysa çözücü basıncı ETKİN alanla kuruyor:
        #   P_new = mdot*c*/(A_t*1e5)   ve   F = CF*Pc*1e5*A_t
        # Kn katı motor iç balistiğinin TANIM oranıdır; kullanıcının
        # yayımlanan Kn ile elle yaptığı denge kontrolü yanıtın kendi
        # basıncını tutturmuyordu. ÖLÇÜLDÜ (APCP 100/30/500, 40 bar, n=0,35):
        #   Cd      yayımlanan Kn    çözücünün Kn'i    sapma    Kn'den geri Pc
        #   1,00       157,576          157,576        %0,00       40,00 bar
        #   0,98       154,425          157,576       -%2,00       38,78 bar  <- UI
        #   0,90       141,818          157,576      -%10,00       34,01 bar
        #   0,70       110,303          157,576      -%30,00       23,11 bar
        # (yanıtın kendi tepe basıncı dört vakada da 40,00 bar.)
        # ------------------------------------------------------------------
        A_throat = A_t
        Kn_initial = A_burn_initial / A_throat if A_throat > 0 else 0.0
        Kn_final   = A_burn_final / A_throat if A_throat > 0 else 0.0

        # Segment count & length (BATES convention: L_seg ~ D_chamber)
        # NOT: n_segments yanma alanı modeliyle AYNI kaynaktan gelir
        # (_bates_segment_count); inhibitör etiketi modelle tutarlı —
        # uçlar YANAR, dış yüzey inhibitörlüdür.
        if self.grain_type == 'bates':
            n_segments = self._bates_segment_count()
            segment_length = self.L_grain / n_segments
            # Etiket artık kullanıcının GERÇEK inhibitör düzeninden kurulur
            # (calculate_burn_area ile aynı bayraklar) — sabit varsayım yok.
            _inh_parts = []
            if getattr(self, 'inhibit_outer', True):
                _inh_parts.append('outer_surface')
            if getattr(self, 'inhibit_front', False):
                _inh_parts.append('front_face')
            if getattr(self, 'inhibit_rear', False):
                _inh_parts.append('rear_face')
            inhibitor_cfg = '_and_'.join(_inh_parts) if _inh_parts else 'none'
        elif self.grain_type == 'end_burner':
            n_segments = 1
            segment_length = self.L_grain
            inhibitor_cfg = 'outer_surface_and_one_end'
        elif self.grain_type in ('finocyl', 'slotted'):
            # Çekirdek yanmalı: dış yüzey ve HER İKİ uç inhibitörlüdür
            # (yanma alanı modeli de yalnız port çevresini sayar).
            n_segments = 1
            segment_length = self.L_grain
            inhibitor_cfg = 'outer_surface_and_both_ends'
        else:
            n_segments = 1
            segment_length = self.L_grain
            inhibitor_cfg = 'outer_surface'

        # ------------------------------------------------------------------
        # ÖH D18 (P2B4-01) — TEK SINIFLANDIRICI.
        #
        # Burada İKİNCİ bir itki-biçim sınıflandırıcısı duruyordu: ilk ve son
        # çeyreğin DÜZ ortalamasını +-%10 bandında karşılaştırıyor, aradaki
        # TEPEYİ hiç görmüyor ve 'Progressive-Regressive' sınıfını hiç
        # tanımıyordu. Yani v2.6.27/B2-1'in "söktüm" dediği algoritmanın ta
        # kendisiydi ve aynı yanıtta, aynı eğri için ikinci bir hüküm
        # yayımlıyordu. ÖLÇÜLDÜ (once.json; 6 grain x 3 geometri x 3 basınç =
        # 54 koşu): 30 koşuda (%55,6) iki alan FARKLI sınıf söylüyordu — ör.
        # star 100/500/30 @40 bar: burn_profile 'regressive' ⟷
        # thrust_profile_analysis.thrust_curve_type 'Progressive-Regressive'.
        # Ayrıca örnek sayısı 20'nin altındayken koşulsuz 'neutral' üretiyordu
        # (yenisi aynı durumda sınıf UYDURMUYOR, 'Undetermined' diyor).
        #
        # Alan artık _thrust_shape_report'un KENDİ sınıfından türetilir; iki
        # yer arasında hüküm farkı fiziksel olarak imkânsız hâle gelir. Ad
        # biçimi korunur (küçük harf, tireli) ki mevcut tüketiciler
        # kırılmasın; sınıf belirlenemediyse alan None kalır ve gerekçesi
        # burn_profile_basis'te durur — sessiz 'neutral' yok.
        # ------------------------------------------------------------------
        _shape = self._thrust_shape_report(curve['thrust'], curve.get('time'))
        if _shape['shape'] == SOLID_THRUST_SHAPE_UNDETERMINED:
            burn_profile = None
        else:
            burn_profile = _shape['shape'].lower()

        # T24 (2026-08-03): 'web_thickness_mm' GEOMETRİK web'tir
        # ((dış - çekirdek)/2). Dış yüzey de yanıyorsa (inhibit_outer
        # işaretsiz — varsayılan yapılandırma) web İKİ cepheden tükenir ve
        # gerçekte tükenen kalınlık bunun YARISIDIR. Ölçüldü: geometrik
        # 35,0 mm ↔ tükenen 17,5 mm. Arayüz tablosu tek bir 'Web Thickness'
        # satırı gösterdiği için hangi tanımın kastedildiği belirsizdi;
        # ikisi de artık AYRI alanlarda ve hangi tabanda olduğu beyan edilir.
        # ÖH D15 a2 (P2B4-02): üç AYRI büyüklük, üç ayrı ad, tek kaynak.
        #   web_thickness_mm      -> en ince yakıt kesiti (_geometric_web_thickness)
        #   web_available_mm      -> yanmanın tarayabildiği üst sınır (_max_web_thickness)
        #   web_burnout_mm        -> FİİLEN tüketilen kalınlık (int r dt)
        # Eskiden üçü de tek bir tipe-kör formülden ((D-d)/2) geliyordu ve
        # end-burner'da 35,0 mm yazılıp 500,06 mm tüketiliyordu (14,3 kat).
        web_available = self._max_web_thickness()
        web_consumed = self._consumed_web(curve)
        grain_design = {
            'grain_type': self.grain_type,
            'web_thickness_mm': (web_thickness_val * 1000
                                 if web_thickness_val is not None else None),
            'web_available_mm': (web_available * 1000
                                 if web_available else None),
            'web_burnout_mm': (web_consumed * 1000
                               if web_consumed is not None else None),
            # 'web_basis' sözcük dağarcığı v2.6.26 (T24) sözleşmesidir ve
            # KORUNUR: kaç CEPHEDEN tükendiğini söyler. Yanma YÖNÜ (eksenel /
            # radyal) ayrı bir alanda verilir — ikisi farklı sorulardır ve
            # end-burner'ı 'single_sided' saymak doğrudur (tek cephe), yalnız
            # o cephe eksenel ilerler.
            'web_basis': ('two_sided'
                          if (self.grain_type == 'bates'
                              and not getattr(self, 'inhibit_outer', True))
                          else 'single_sided'),
            'web_direction': ('axial' if self.grain_type == 'end_burner'
                              else 'radial'),
            'web_basis_note': (
                'web_thickness_mm is the THINNEST propellant section for this '
                'grain type (end_burner: the axial grain length, because the '
                'burn is axial there and the radial formula is undefined); '
                'web_available_mm is the upper bound the burn scan may reach '
                '(_max_web_thickness); web_burnout_mm is the thickness '
                'ACTUALLY consumed, measured as the time integral of the burn '
                'rate over the solved curve - the same integral '
                'web_thickness_utilization uses. The three are different '
                'quantities and are not equal by construction.'
                + (' The outer surface burns as well, so the web is consumed '
                   'from both faces and burnout is reached at about half the '
                   'geometric web.'
                   if (self.grain_type == 'bates'
                       and not getattr(self, 'inhibit_outer', True)) else '')),
            'outer_diameter_mm': self.D_chamber * 1000,
            'inner_diameter_mm': self.D_core * 1000,
            'grain_length_mm': self.L_grain * 1000,
            'number_of_segments': n_segments,
            'segment_length_mm': segment_length * 1000,
            # ÖH D36 · onemli2-kati — segment arası boşluk YAYIMLANIR (D35
            # katı devri 3). Değer bu koşunun FİİLEN kullandığı boşluktur
            # (self.grain_gap_m; kasa boyu zincirinin okuduğu sayı), kaynağı
            # __init__'te adıyla belirlenir. STEP üreticisi
            # (step_export._grain_segment_plan) ve kesit çizimi yayımlanınca
            # boşluğu kendiliğinden modeller: stack = N·L + (N−1)·gap.
            'grain_gap_mm': self.grain_gap_m * 1000.0,
            'grain_gap_source': getattr(self, 'grain_gap_source',
                                        'not_supplied_zero'),
            'grain_gap_applies': bool(self.grain_type == 'bates'
                                      and n_segments > 1),
            'grain_gap_basis': (
                'inter-segment gap as USED by this run, read from the '
                'grain_gap input (mm). It lengthens the case inner length '
                '(_case_inner_length) for multi-segment BATES only '
                '(grain_gap_applies) and is not propellant. '
                'grain_gap_source: user_input = the input was read; '
                'not_supplied_zero = no value was sent and 0 mm was used; '
                'rejected_input = the value was rejected (see '
                'rejected_inputs) and 0 mm was used.'),
            'inhibitor_config': inhibitor_cfg,
            'burning_surface_initial_cm2': A_burn_initial * 1e4,
            'burning_surface_final_cm2': A_burn_final * 1e4,
            'burn_profile': burn_profile,
            # ÖH D18 (P2B4-01): sınıfın TEK kaynağı ve kararın dayanağı.
            'burn_profile_source': 'detailed_analysis.thrust_profile_analysis'
                                   '.thrust_curve_type (_thrust_shape_report)',
            'burn_profile_basis': _shape['basis'],
            'burn_profile_status': ('classified' if burn_profile
                                    else 'undetermined'),
            'volumetric_loading': vol_loading,
            'Kn_initial': Kn_initial,
            'Kn_final': Kn_final,
            # Kasa serbest hacmi [L] — formdaki 'Case Internal Volume'
            # alanının çözücü tarafı; rozet bloğu karşılaştırma için okur.
            'case_free_volume_l': case_free_volume * 1000.0,
        }
        if self.grain_type == 'star':
            _n_star, _depth_star = self._star_params()
            grain_design['star_points'] = _n_star
            grain_design['point_depth'] = _depth_star * 1000  # mm
            # ÖH D15 a2 (P2B1-06): 'star_radius' arayüzde "Radius of star
            # points from center" diye tanıtılıyor ama çözücü onu merkezden
            # değil ÇEKİRDEK YARIÇAPINDAN itibaren DERİNLİK olarak kullanır
            # (_cached_star_polygon: r_uç = r_çekirdek + derinlik). ÖLÇÜLDÜ:
            #   girilen 5,0 mm -> gerçek uç yarıçapı 20,00 mm (4,000x)
            #   girilen 15,0 mm -> 30,00 mm (2,000x)
            #   girilen 30,0 mm -> 43,00 mm (1,433x)
            # Çözülen geometri artık SAYIYLA yayımlanıyor: kullanıcı hangi
            # yarıçapın kesildiğini yanıttan okuyabilir.
            grain_design['star_tip_radius_mm'] = (
                (self.D_core / 2.0 + _depth_star) * 1000.0)
            grain_design['point_depth_basis'] = (
                'point_depth is the RADIAL DEPTH measured from the core '
                'radius outwards, not a radius from the motor axis: the star '
                'tip sits at core_radius + point_depth = star_tip_radius_mm. '
                'The solver reads it from the "star_radius" input field.')
            _st_assumed, _st_clipped = self._star_input_report()
            grain_design['assumed_defaults'] = _st_assumed
            grain_design['clipped_inputs'] = _st_clipped
            grain_design['model_note'] = (
                'Yanan çevre geometrik ofset modeliyle (Huygens) hesaplanır; '
                'uç sayısı ve derinliği itki eğrisine tam yansır.'
                if SHAPELY_AVAILABLE else
                'shapely kurulu değil: basitleştirilmiş çevre yaklaşıklığı.')
        elif self.grain_type in ('finocyl', 'slotted'):
            # Radyal yuvalı tipler: geometrinin TAMAMI kullanıcıya beyan
            # edilir; girilmeyen alanlar 'assumed_defaults' ile işaretlenir,
            # fiziksel sınıra çarpanlar 'clipped_inputs' ile.
            if self.grain_type == 'finocyl':
                # DİKKAT: yerel ad '_w' OLAMAZ — modül düzeyindeki uyarı
                # üreticisi _w()'yi tüm fonksiyon boyunca gölgeler ve
                # bu daldan geçilmese bile Python değişkeni yerel sayar,
                # fonksiyondaki her _w(...) çağrısı UnboundLocalError verir
                # (v2.6.26'da web_thickness tutarlılık kontrolü eklenince
                # ortaya çıkan uyuyan hata).
                _n, _wid, _d, _frac, _assumed, _clipped = self._finocyl_params()
                _l_fin, _l_plain = self._finocyl_section_lengths()
                grain_design.update({
                    'fin_count': _n,
                    'fin_width_mm': _wid * 1000,
                    'fin_depth_mm': _d * 1000,
                    'finned_length_fraction': _frac,
                    'finned_length_mm': _l_fin * 1000,
                    'plain_length_mm': _l_plain * 1000,
                })
            else:
                _n, _wid, _d, _assumed, _clipped = self._slotted_params()
                grain_design.update({
                    'slot_count': _n,
                    'slot_width_mm': _wid * 1000,
                    'slot_depth_mm': _d * 1000,
                })
            grain_design['assumed_defaults'] = _assumed
            grain_design['clipped_inputs'] = _clipped
            grain_design['model_note'] = (
                'Burning surface from geometric offset of the real port '
                'cross-section (Huygens construction). Slot side walls and '
                'roots are included; end faces are inhibited. Fields listed '
                'in assumed_defaults were not supplied and use built-in '
                'defaults.')
        if self.grain_type == 'wagon_wheel':
            # V301/K-B (KT-08): çözücünün KULLANDIĞI geometri yanıtta; sabit
            # varsayılanlar 'HRMA seçimi' künyesiyle beyan edilir.
            _wp = self._wagon_params()
            grain_design['wagon_wheel'] = {
                'hole_count': _wp['hole_count'],
                'hole_diameter_mm': _wp['hole_diameter_m'] * 1000.0,
                'pitch_diameter_mm': _wp['pitch_diameter_m'] * 1000.0,
                'center_hole': True,
                'basis': _wp['basis'],
                'geometry': ('central hole + hole_count outer holes on the '
                             'pitch circle, all of hole_diameter_mm'),
            }
            grain_design['assumed_defaults'] = list(_wp['assumed_defaults'])
            grain_design['clipped_inputs'] = []

        # --- Design Summary ---
        # CODEX BULGUSU DÜZELTMESİ (2026-07-19, satır ~3871): özet tablo
        # kasa kalınlığını SABİT 250 MPa / SF=3 ile yeniden hesaplıyordu;
        # yapısal analiz, kuru kütle ve emniyet zinciri ise _case_design()
        # (kullanıcının malzeme / akma / SF / girilen kalınlık girdileri)
        # kullanıyordu. Aynı motor için iki farklı cidar raporlanıyordu
        # (girilen 8 mm özet tablosunda 2.4 mm görünüyordu). Tek kaynak:
        # _case_design().
        (_summary_case_material, _sigma_y_summary,
         _SF_summary, t_wall_summary) = self._case_design()
        # V301/K-A (KT-02): motor dış çapı TEK kaynaktan — kasa iç çapı +
        # 2·cidar; ``cad_design.case_design.outer_diameter`` ile AYNI
        # formül ve aynı iki çağrı (``_case_inner_diameter`` /
        # ``_case_design``). Eskiden tane dış çapı + 2·cidar yazılıyordu:
        # yalıtım/astar ve beyan edilen kasa yok sayılıyor, özet CAD'den
        # 6-100 mm küçük çıkıyordu (ölçüldü: 104,24 ⟷ 110,24 mm).
        motor_od = self._case_inner_diameter() + 2 * t_wall_summary
        # Kasa boyu, CAD ile AYNI kaynaktan (_case_inner_length); aşağıdaki
        # key_dimensions bunu kullanır.
        case_length = self._case_inner_length()

        dry_mass = self._calculate_dry_mass()
        total_mass = dry_mass + propellant_mass
        mass_fraction = propellant_mass / total_mass if total_mass > 0 else 0.0

        # ÖH D15 a2 (P2B4-06): toplam boy KASADAN + lüleden kurulur.
        # Eski satır kapak payını (0,1 m) yeniden türetiyor ve BATES segment
        # aralarını hiç görmüyordu, dolayısıyla motorun toplam boyu kendi
        # kasasından KISA çıkabiliyordu. ÖLÇÜLDÜ (bates, D=100, L=500,
        # core=30, 5 segman; lüle 142,716 mm):
        #   grain_gap  motor_length_mm  yayımlanan total  doğru toplam   eksik
        #      0 mm        600,000          742,716        742,716       0,0
        #      2 mm        608,000          742,716        750,716      -8,0   <- UI
        #     20 mm        680,000          742,716        822,716     -80,0
        #     50 mm        800,000          742,716        942,716    -200,0
        # 50 mm aralıkta yayımlanan TOPLAM boy (742,7) kasanın kendisinden
        # (800,0) 57,3 mm kısaydı — lüle daha eklenmeden. Kapak payının TEK
        # tanım noktası _case_inner_length()'tir; case_length onu okur.
        # ÖH D18 (P2B3-13): lüle konturu kurulamadıysa motor toplam boyu
        # da KAZANILMAMIŞTIR; sayı uydurulmaz.
        motor_total_length = (None if nozzle_total_length is None
                              else case_length + nozzle_total_length)

        # 2. KADEME (Faz 4B, bulgu B2): yanma normal bitti ve n < 1, ama bazı
        # adımlar 100 iterasyon tavanına takıldı. Bu koşu için ZATEN kritik bir
        # kullanıcı uyarısı ateşleniyor (warn.solid.pressure_solver_not_converged);
        # yalan söyleyen tek alan status'tü — koşulsuz 'CALCULATED' yazıyordu.
        # Artık status uyarıyla AYNI şeyi söyler ve performans/CAD bloklarının
        # hangi basınç geçmişinden geldiği açıkça beyan edilir.
        cozucu_yakinsadi = bool(getattr(self, '_solver_converged', True))
        # V301/B6: rejim sınırında tutulan adımlar başarısız değildir ama
        # yasanın o basınçta tek değeri yoktur; not bunu sayısıyla söyler.
        _tutulan = int(curve.get('pressure_solver_boundary_held_steps', 0)
                       or 0)
        _sinir_notu = (
            f' {_tutulan} of them sit on a regime boundary of the piecewise '
            'burn-rate law, where the law itself is discontinuous; there the '
            'equilibrium is held at the boundary pressure with a burn rate '
            'inside the jump (see solver_diagnostics.'
            'pressure_solver_boundary_basis).'
            if _tutulan > 0 else '')
        design_summary = {
            'title': f'Solid Motor - {self.grain_type.upper()} / {self.propellant_name}',
            'status': (DESIGN_STATUS_CALCULATED if cozucu_yakinsadi
                       else DESIGN_STATUS_NOT_CONVERGED),
            # Z2: çözücüye ULAŞMAYAN girdiler adıyla yayımlanır (boş liste =
            # her gönderilen alan okundu). Sessiz red yok.
            'rejected_inputs': list(getattr(self, 'rejected_inputs', [])),
            'numerical_validity': {
                'convergence_achieved': cozucu_yakinsadi,
                'note': (
                    ('Every time step met the pressure solver tolerance.'
                     + _sinir_notu)
                    if cozucu_yakinsadi else
                    f'Some time steps reached the '
                    f'{SOLID_PRESSURE_SOLVER_MAX_ITER}-iteration cap and the '
                    'bracketed fallback without meeting the pressure solver '
                    'tolerance. The burn still ran '
                    'to completion with a burn-rate exponent below 1, so the '
                    'result is published, but every performance and CAD number '
                    'below is derived from that pressure history and must be '
                    'treated as unconverged. See solver_diagnostics for the '
                    'failed step count and the largest residual.'),
            },
            'key_dimensions': {
                'motor_outer_diameter_mm': motor_od * 1000,
                # Kasa boyu TEK kaynaktan (_case_inner_length): grain yığını +
                # segment araları + kapak payı. Eskiden burada araları
                # saymayan ikinci bir tanım vardı.
                'motor_length_mm': case_length * 1000,
                'nozzle_throat_mm': d_throat * 1000,
                'nozzle_exit_mm': d_exit * 1000,
                'wall_thickness_mm': t_wall_summary * 1000,
                'total_length_mm': (None if motor_total_length is None
                                    else motor_total_length * 1000),
                'total_length_status': (
                    'not_computable' if motor_total_length is None
                    else 'computed'),
            },
            # Cidarın hangi malzeme/dayanım/SF ile geldiği açıkça beyan
            # edilir — yapısal analiz paneliyle AYNI kaynak (_case_design).
            # P15B4-07: künye artık `cad_design.case_design` ile TEK
            # üreticiden (`_case_design_report`) gelir; iki blok aynı
            # cümleyi kurar (eskiden kesişim tek alandı: 'material').
            'case_design': self._case_design_report(),
            'masses': {
                'propellant_mass_kg': propellant_mass,
                'dry_mass_kg': dry_mass,
                'total_mass_kg': total_mass,
                'mass_fraction': mass_fraction,
                # T03: kuru kütlenin BİLEŞEN dökümü — arayüz kendi bileşen
                # alanlarını çözücünün sayılarıyla doldurabilsin diye.
                'inert_breakdown': self._dry_mass_breakdown(),
            },
            'performance': {
                'peak_thrust_N': max_thrust,
                'average_thrust_N': avg_thrust,
                # ÖH D22 (defter P12bB2-09): iki sayı yan yana duruyordu ama
                # ORANLARI hiçbir yerde adlandırılmamıştı, bu yüzden motoru
                # tek skalerle (ortalama itki) devralan tüketiciler — yörünge
                # yükü ve .eng/OpenRocket ihracı — azami ivmeyi bu oran kadar
                # düşük görüyordu. Oran ölçüldü (once.json K1, aynı gövde):
                # end_burner 1,000 · bates 1,472 · finocyl 1,493 · star 2,074
                # · slotted 2,627 · wagon_wheel 3,922. Türetilmiş büyüklük;
                # iki alan da tam çözünürlüklü eğriden gelir.
                'peak_to_average_thrust_ratio': (
                    (float(max_thrust) / float(avg_thrust))
                    if avg_thrust and float(avg_thrust) > 0 else None),
                'peak_to_average_thrust_ratio_basis': (
                    'max(thrust)/mean-equivalent average thrust of the same '
                    'burn-back curve. A consumer that carries this motor as '
                    'a single average-thrust scalar (rectangular thrust '
                    'profile) understates the maximum acceleration by this '
                    'factor; the resolved thrust_curve is published in the '
                    'same response and should be preferred.'),
                'specific_impulse_s': isp_sea_level,
                'specific_impulse_vacuum_s': isp_vacuum,
                'burn_time_s': burn_time,
                'total_impulse_Ns': total_impulse,
            },
            'recommendation': (
                f'Solid motor design computed for the given parameters. '
                f'Kn range: {Kn_initial:.0f}-{Kn_final:.0f}, '
                f'propellant mass fraction: {mass_fraction:.1%}.'
            ),
        }

        # Lüle/boğaz malzemesinin termal değerlendirmesi. Sonuç sözlüğüne
        # konmadan ÖNCE üretilir, çünkü ürettiği KRİTİK hüküm aşağıdaki
        # teslim kanalına da girmek zorundadır (ÖH P16S1-07).
        nozzle_material_report = self.analyze_nozzle_material()

        # Kullanıcıya görünen uyarılar TEK listede toplanır: kurulum sırasında
        # üretilenler + bu koşunun değer doğrulamaları + fiziksel/sayısal
        # sağlık uyarıları. Hepsi {code, params, severity} kaydıdır (D-track):
        # backend dilsiz, metni frontend TF(code, params) ile kurar.
        #
        # ÖH P16S1-07 — TERMAL HÜKMÜN TESLİM KANALI. Termal blokların
        # ürettiği ``severity: critical`` hükümler kendi bloklarında
        # KALIYORDU; ekran katmanı yalnız bu listeyi okuduğu için hüküm
        # kullanıcıya hiç ulaşmıyordu. Hüküm burada yeniden yazılmaz, kaydın
        # ta kendisi taşınır ve kimliğine göre yinelenmez.
        all_warnings = (list(self.design_warnings) + run_warnings
                        + self._design_health_warnings(curve))
        _mevcut = {_warning_identity(w) for w in all_warnings}
        all_warnings += [
            w for w in _critical_thermal_verdicts(nozzle_material_report,
                                                  thermal_analysis)
            if _warning_identity(w) not in _mevcut]

        # Egzoz (plume) şeması: motor_viz3d.js readNozzleExit
        # nozzle_design.performance.{exit_pressure, ambient_pressure,
        # exit_mach, exit_velocity} okur. Katı sonuçlarında nozzle_design
        # yalnız cad_design'ın İÇİNDE ve salt geometriydi; bu yüzden katı
        # sayfasında egzoz HİÇ çizilmiyordu. Blok, cad_design.nozzle_design
        # ile AYNI üreticiden gelir (_design_nozzle_geometry) — aynı motor
        # için iki farklı nozul raporu oluşmaz.
        nozzle_design_block = self._design_nozzle_geometry()

        results = {
            # Input parameters
            'grain_type': self.grain_type,
            'propellant_type': self.propellant_type,
            'propellant_name': self.propellant_name,
            # ÖH D21 a1 (P2B1-09): motor bu iki künyeyi __init__ boyunca
            # KURUYORDU ama yanıtın hiçbir yaprağında geçmiyordu — "hangi
            # sayı nereden geldi" beyanının yakıt kolu kullanıcıya HİÇ
            # ulaşmıyordu (ölçüldü: once.json/P2B1-09, 0 okuma noktası).
            # Kardeş kol (`burn_rate_inputs`) zaten yayımlanıyor; bu iki
            # alan onunla aynı sözleşmeyi tamamlar.
            #  * propellant_type_source : yakıt KİMLİĞİ hangi girdiden
            #    çözüldü ('propellant_type input' / 'constructor argument' /
            #    'burn-rate preset (...)' / 'propellant name (...)' /
            #    'endpoint default').
            #  * propellant_property_source : termokimya ÖZELLİKLERİ hangi
            #    tablodan geldi ('engine table' / 'central catalogue
            #    (propellants_db); secondary coefficients inherited from X' /
            #    'generic placeholder (no record)').
            'propellant_type_source': getattr(
                self, 'propellant_type_source', None),
            'propellant_property_source': getattr(
                self, 'propellant_property_source', None),
            'propellant_source_basis': (
                'propellant_type_source names the INPUT the propellant '
                'identity was resolved from; propellant_property_source '
                'names the TABLE its thermochemistry was read from. They '
                'are provenance declarations, not computed quantities: '
                'read them before comparing these results with a reference '
                'motor, because a derived identity or an inherited '
                'secondary coefficient set is not the same evidence as an '
                'explicit selection with its own record.'),
            'chamber_diameter': self.D_chamber * 1000,  # mm
            # --- ÖH D26 a2 (OH-D25-03) — ADIN KANONİK ANLAMI --------------
            # ÖLÇÜLDÜ (docs/scofield/raw/OH/D26/kati/a2/once.json;
            # insulation_thickness = 3 mm ile POST /calculate_solid): AYNI
            # yanıtta 'chamber_diameter' adlı ÜÇ yaprak, ÜÇ farklı büyüklük
            # ve İKİ farklı birim taşıyordu —
            #   chamber_diameter                      101,718 mm  (grain OD)
            #   motor_geometry.chamber_diameter         0,1077 m  (kasa iç çapı)
            #   acoustic_modes.inputs.chamber_diameter  0,0667 m  (eşdeğer
            #                                                     akustik kavite)
            # ve hiçbirinin yanında hangi büyüklük olduğunu söyleyen bir
            # künye yoktu; round-trip yapan kullanıcı adın anlamını ancak
            # sayıyı deneyerek öğrenebiliyordu.
            #
            # KANON: çıplak 'chamber_diameter' = yakıt bloğunun DIŞ ÇAPI
            # (grain OD, mm) — isteğin aynı adlı alanının anlamı da budur
            # (P15B4-08 round-trip ölçümü: bu değer geri gönderilince yanıt
            # bit-aynı). Aynı adı taşıyan öteki yapraklar burada ADIYLA
            # sayılır; akustik yaprak bu dalgada kendi adına kavuşturuldu
            # (equivalent_cavity_diameter_m), motor_geometry yaprağı ihracat
            # kulvarının sahasındadır ve orada adlandırılacaktır.
            'chamber_diameter_kunye': {
                'quantity': 'grain outer diameter',
                'unit': 'mm',
                'value': self.D_chamber * 1000,
                'same_name_elsewhere': [
                    {'path': 'motor_geometry.chamber_diameter',
                     'quantity': 'case INNER diameter (the declared case '
                                 'bore, or grain OD + 2 x (liner + '
                                 'insulation) thickness; see case_bore)',
                     'unit': 'm',
                     'owner': 'hrma/export/motor_geometry.py'},
                    {'path': 'acoustic_modes.inputs.'
                             'equivalent_cavity_diameter_m',
                     'quantity': 'equivalent acoustic cavity diameter '
                                 '(volume- and length-preserving cylinder)',
                     'unit': 'm',
                     'owner': 'SolidRocketEngine._acoustic_mode_report',
                     'renamed_from': 'chamber_diameter'},
                ],
                # V301/K-A (ana model kararı A, 22 Eki): İSTEĞİN aynı adlı
                # alanı iki biçimde iki ayrı şeydir; yanıttaki çıplak ad
                # değişmedi (tane dış çapı — tüketiciler onu okuyor).
                'basis': (
                    "The bare name 'chamber_diameter' in this response means "
                    'the grain outer diameter in millimetres. The REQUEST '
                    'field of that name is the case inner diameter whenever '
                    'outer_diameter is sent; only in the single-diameter '
                    'form (no outer_diameter) is it read as the grain outer '
                    'diameter, and then this value can be sent back '
                    'unchanged. case_bore states which form was used. '
                    'Sibling blocks that reuse the name for a DIFFERENT '
                    'quantity are listed above with their own quantity and '
                    'unit; do not compare them numerically without reading '
                    'that list.'),
            },
            # V301/K-A (KT-01/KT-03, karar A): kasa iç çapının kaynağı ve
            # sığma kuralı ADIYLA (beyan / türetme / tek-çap eski biçim).
            'case_bore': self._case_bore_block(),
            'grain_length': self.L_grain * 1000,  # mm
            'core_diameter': self.D_core * 1000,  # mm

            # Performance
            'burn_time': burn_time,
            'average_thrust': avg_thrust,
            'max_thrust': max_thrust,
            'total_impulse': total_impulse,
            'specific_impulse': isp_sea_level,
            'isp_sea_level': isp_sea_level,
            'isp_vacuum': isp_vacuum,
            # F2-2: vakum Isp'sinin türetildiği zincir adıyla yayımlanır.
            'isp_vacuum_basis': isp_vacuum_basis,
            'total_impulse_vacuum': total_impulse_vacuum,
            'thrust_coefficient_vacuum': float(cf_vacuum),
            'propellant_mass': propellant_mass,

            # Motor geometry
            'throat_diameter': d_throat * 1000,  # mm
            'exit_diameter': d_exit * 1000,  # mm
            'exit_diameter_vacuum': d_exit_vacuum * 1000,  # mm
            'expansion_ratio': epsilon_sea_level,
            'expansion_ratio_vacuum': epsilon_vacuum,
            'expansion_ratio_vacuum_basis': expansion_ratio_vacuum_basis,

            # Nozul tasarımı + çıkış düzlemi performansı (egzoz/plume şeması;
            # motor_viz3d.js readNozzleExit'in okuduğu adlarla, hibritle aynı)
            'nozzle_design': nozzle_design_block,
            # readNozzleExit'in gamma yedek yolu: md.gamma. Hibrit gamma'yı
            # combustion_analysis.compositions.chamber.gamma altında yayımlar;
            # katıda CEA/Cantera bileşim çözümü yok, gamma yakıt kaydından
            # gelir ve itki/genişleme çözümünün kullandığı değerin AYNISIDIR.
            'gamma': float(self.gamma),
            'gamma_basis': (
                'NASA CEA equilibrium chamber gamma_s at this chamber '
                'pressure (condensed phase included); the nozzle solution '
                'is the CEA shifting-equilibrium expansion (see '
                'thermochemistry.nozzle)' if self._cea_nozzle_state() else
                'NASA CEA equilibrium chamber gamma_s at this chamber '
                'pressure; CEA did not solve the nozzle, so the thrust '
                'coefficient and expansion-ratio solutions use this value '
                'in the single-gamma relations' if self._cea_active() else
                'isentropic expansion coefficient from the '
                'propellant record; the same value the thrust '
                'coefficient and expansion-ratio solutions use'),

            # Propellant properties
            'density': self.rho_p,
            'c_star': self.c_star,
            # ÖH D17 (P2B1-01): kaydın c*'ı kendi (gamma, T_c, M) üçlüsüyle
            # tutarlı mı? Denetim ARTIK yayımlanıyor; kayıtlar kendi
            # 'c_star_basis' beyanlarıyla muaf tutulamıyor.
            # V301/N-CEA-2 D1: denetlenen sayı TEORİK (kayıpsız) c*'tır.
            # Eskiden TESLİM EDİLEN self.c_star (eta_c* uygulanmış) veriliyor
            # ve 'record_c_star_m_s' diye yayımlanıyordu; kendi içinde
            # tutarlı bir kayıt (double_base, eta %95) 'unexplained_deficit
            # -%5,00' alıyordu. Kanıt: docs/scofield/raw/OH/V301/cea/RAPOR.md
            # C3 D1.
            'c_star_identity_audit': _c_star_identity_audit(
                self.propellant_type, self.gamma, self.T_c,
                getattr(self, 'mw_exhaust', None),
                self._c_star_theoretical(),
                basis_override=('cea' if self._cea_active() else None)),
            # V301/N-CEA-2 (K1/K2/K3): termokimyanın ve lülenin KAYNAĞI.
            'thermochemistry_source': getattr(
                self, 'thermochemistry_source', SOLID_THERMO_SOURCE_CATALOGUE),
            'thermochemistry': self.thermochemistry_report(),
            # FAZ 5 / H2-4 DÜZELTMESİ — katalog yakıtında (KNDX/KNSB) yanma
            # hızı PARÇALI rejim tablosundan okunur ve kullanıcının a/n çifti
            # HİÇ kullanılmaz. Ölçüldü (kndx, Pc=30 bar, aynı geometri):
            #   n=0.200 -> isp=138.1603514622613  burn_time=1.8649276127370293
            #   n=0.688 -> isp=138.1603514622613  burn_time=1.8649276127370293
            #   n=0.950 -> isp=138.1603514622613  burn_time=1.8649276127370293
            # yani 15 anlamlı basamak aynı. Ezme `warn.solid.piecewise_law_
            # active` ile beyan ediliyordu AMA bu iki alan kullanıcının
            # kullanılmayan değerini geri yayımlıyordu; alan adı "hesapta
            # kullanılan katsayı" gibi okunduğu için kullanıcı verdiği sayının
            # işe yaradığını sanıyordu. Artık ezme varken alanlar null döner,
            # kullanıcının girdisi ayrı ve AÇIKÇA "_input" ekiyle yayımlanır,
            # gerçekten kullanılan rejim tablosu `burn_rate_law` altında
            # verilir. (`unwired_inputs()` de bu durumu bildirir.)
            **self._burn_rate_publication(),
            'chamber_temperature': self.T_c,
            'chamber_pressure': self.P_c,
            
            # Thrust curve data (yayın çözünürlüğü — bkz. _published_thrust_curve)
            'thrust_curve': self._published_thrust_curve(curve),
            
            # Altitude performance
            'altitude_performance': altitude_performance,
            
            # Detailed technical analysis
            'detailed_analysis': detailed_analysis,
            'structural_analysis': structural_analysis,
            'thermal_analysis': thermal_analysis,
            # OH-Z5-03 / OH-Z3-03 (katı ayağı): güverte ısı haritasının
            # okuduğu şema. thermal_analysis'in ÇEVİRİSİ DEĞİLDİR — iki
            # blok aynı şey değildir; bu blok Bartz zincirinin kendi
            # sayılarını güvertenin şemasında yayımlar (bkz.
            # _build_heat_transfer_analysis).
            'heat_transfer_analysis': self._build_heat_transfer_analysis(),
            # v2.6.26: lüle malzemesi seçimi artık bir çıktıya bağlı
            # (boğaz termal marjı + erozyon durumu). Öncesinde alan ölçümde
            # ÖLÜ çıkıyordu: tungsten seçen kullanıcı grafit sonucunu
            # görüyordu.
            'nozzle_material_analysis': nozzle_material_report,
            # Hangi form alanlarının çözücüye ULAŞMADIĞI, gerekçesiyle.
            # Sıvı motorda bu beyan vardı, katıda yoktu: 25 alan sessizce
            # ölüydü. Arayüz bu listeyi "not used in solver" rozeti için okur.
            'unwired_inputs': self.unwired_inputs(),
            'manufacturing_analysis': manufacturing_analysis,
            'flight_simulation': flight_simulation,
            'cost_analysis': cost_analysis,
            'environmental_analysis': environmental_analysis,
            'safety_analysis': safety_analysis,
            'quality_analysis': quality_analysis,
            'advanced_performance': advanced_performance,
            
            # CAD Design Data
            'cad_design': self._generate_motor_cad_data(),

            # Nozzle angles (top-level for easy access)
            'nozzle_angles': nozzle_angles,

            # Grain design details
            'grain_design': grain_design,

            # Optimal design summary
            'design_summary': design_summary,

            # Tasarım noktası raporu (hedef itki/süre verildiyse dolu)
            'design_point': self.design_point,

            # Fiziksel akıl sağlığı uyarıları ({code, params, severity})
            'design_warnings': all_warnings,
            # solid.html displaySolidWarnings() 'warnings' anahtarını okur —
            # 'design_warnings' arayüzde HİÇBİR yerde tüketilmiyordu, yani
            # yakınsama/erozif/port uyarıları kullanıcıya ulaşmıyordu
            # (2026-07-19). Aynı liste panelin beklediği adla da verilir.
            'warnings': all_warnings,

            # Basınç çözücü sağlığı (sabit True bayrağının yerine gerçek durum)
            'solver_diagnostics': {
                'convergence_achieved': bool(
                    curve.get('convergence_achieved', True)),
                'pressure_solver_steps': int(
                    curve.get('pressure_solver_steps', 0) or 0),
                'pressure_solver_failed_steps': int(
                    curve.get('pressure_solver_failed_steps', 0) or 0),
                'pressure_solver_max_residual': float(
                    curve.get('pressure_solver_max_residual', 0.0) or 0.0),
                'pressure_solver_tolerance': float(
                    curve.get('pressure_solver_tolerance', 0.0) or 0.0),
                'termination_reason': curve.get('termination_reason'),
                'burnout_time_s': curve.get('burnout_time_s'),
                'time_step_s': curve.get('time_step_s'),
                'burn_rate_exponent': float(self.n),
                'basis': (
                    'Equilibrium chamber pressure is solved with a damped '
                    'fixed-point iteration (max '
                    f'{SOLID_PRESSURE_SOLVER_MAX_ITER} per time step). The '
                    'contraction argument requires a burn-rate exponent '
                    'n < 1. A step that does not meet the tolerance is '
                    're-solved by bracketing and bisecting the mass-balance '
                    'residual to the same tolerance; if the bracket collapses '
                    'onto a regime boundary of a piecewise burn-rate law the '
                    'step is held there (pressure_solver_boundary_basis). '
                    'convergence_achieved is true only when every time step '
                    'met the tolerance or was held at such a boundary.'),
                **self._pressure_solver_boundary_publication(curve),
            },
        }

        # --- v2.6.27 (B3): lüle iç konturu TEK kaynaktan yayımlanır --------
        # motor_viz3d.js selectNozzleContour bu bloğu okur; blok yoksa sahne
        # yerel üretime düşer ve bunu çipiyle beyan eder. Örnekleyici, 2B
        # kesit / STL-STEP dışa aktarımının kullandığı fonksiyonun AYNISIDIR
        # (nozzle_design.sample_nozzle_inner_contour). Katı sonuç sözlüğü üst
        # düzeyde MM taşıdığı için örnekleyiciye METRE bazlı ayrı bir sözlük
        # kurulur; değerler dışa aktarım otoritesinin
        # (export/motor_geometry.solid_results_to_motor_geometry) okuduğu
        # kaynakların TA KENDİSİDİR (D_chamber, d_throat, d_exit,
        # nozzle_angles uzunlukları) — iki yol aynı geometriyi üretir.
        #
        # ORİJİN SÖZLEŞMESİ (doğrulandı): örnekleyicinin ilk noktası
        # konverjan GİRİŞİDİR (kamara-lüle birleşimi) — s=0'da
        # r = rt + (rc-rt)·(0.5+0.5·cos 0) = rc, z = 0; z çıkışa doğru artar.
        # viz3d bu varsayımla çizer; boğaz-orijinli seri lüleyi yanlış
        # konumlandırır. Bekçi: tests/test_motor_geometri_yayimi.py.
        # Örnekleyici başarısız olursa blok yayımlanmaz (uydurma kontur yok).
        # Katıda enjektör ve rejeneratif kanal FİZİKSEL OLARAK yoktur;
        # injector_pattern ve cooling_channels blokları bu yüzden hiçbir
        # koşulda yayımlanmaz (fabrikasyon yasağı — bekçisi aynı test).
        try:
            from hrma.engines.nozzle_design import sample_nozzle_inner_contour
            md_geo = {
                'chamber_diameter': float(self.D_chamber),   # m
                'throat_diameter': float(d_throat),          # m
                'exit_diameter': float(d_exit),              # m
                'nozzle_angles': nozzle_angles,
                'nozzle_convergent_length': float(nozzle_conv_length),  # m
                'nozzle_divergent_length': float(nozzle_div_length),    # m
            }
            pts_mm, kontur_meta = sample_nozzle_inner_contour(md_geo)
            results['nozzle_contour'] = {
                'points': [[float(z) / 1000.0, float(r) / 1000.0]
                           for z, r in pts_mm],
                '_basis': (
                    'sampled inner flow-path contour from hrma.engines.'
                    'nozzle_design.sample_nozzle_inner_contour — the same '
                    'sampler the 2D cross-section and the STL/STEP exports '
                    'consume, fed with the solid solver geometry in metres '
                    '(case inner diameter, thrust-curve throat/exit '
                    'diameters, nozzle_angles lengths). points are [z_m, '
                    'r_m] pairs in metres; the FIRST point is the convergent '
                    'inlet (chamber-nozzle junction, z = 0, r = chamber '
                    'radius) and z increases toward the nozzle exit. '
                    'Divergent length source: '
                    + str(kontur_meta.get('divergent_length_source'))),
            }
        except Exception:
            # Fail-closed: kontur üretilemiyorsa ÜRETİLMEZ; viz yerel üretime
            # düşer ve kaynağı 'kontur: yerel üretim' çipiyle beyan eder.
            pass

        # --- v2.6.27: doğrulanmış analiz modüllerinin bağlanması -----------
        # Üçü de çözücünün GERÇEK durumundan beslenir; girdi eksikse blok
        # NOT_MODELLED beyanıyla döner (bkz. ilgili metotların docstring'i).
        # Hiçbiri Isp / itki / geometri sonucuna geri beslenmez.

        # 1) İki-fazlı (tanecik gecikmesi) Isp kaybı — katı motorun kendi
        #    fiziği (alüminyumlu APCP'de yoğuşmuş Al2O3). Boğaz çapı olarak
        #    yukarıda raporlanan GEOMETRİK çap verilir (aynı sayı).
        results['two_phase_loss'] = self._two_phase_loss_report(d_throat)

        # ÖH D32 (OH-D31-17) — PDF KANALI. Berke/Astra hükmü durumun
        # API/panel/PDF'e taşınmasını istiyor; rapor katmanı yalnız
        # ``design_warnings``/``warnings`` kayıtlarını okur
        # (pdf_generator.PDFReportGenerator.WARNING_SOURCES), bu yüzden
        # durum ORADA da bir kayıt olmak zorundadır — aksi halde PDF'i
        # okuyan, doğrulanmamış Isp'yi doğrulanmış sanırdı. Kayıt yalnız
        # düzeltme DOĞRULANMAMIŞSA yazılır (X_p = 0 dalında yazılmaz).
        # ``all_warnings`` results'ta hem 'design_warnings' hem 'warnings'
        # anahtarının işaret ettiği AYNI listedir; tek ekleme iki kanalı da
        # besler.
        _tp_durum = results['two_phase_loss']
        if isinstance(_tp_durum, dict) and not _tp_durum.get(
                'two_phase_correction_verified', False):
            # ``fallback``: i18n anahtarı bu dalgada EKLENEMEZ
            # (i18n_common.js arayuz-i18n kulvarının sahasıdır), bu yüzden
            # kayıt İngilizce cümlesini kendisi taşır ve ekran katmanı
            # (solid.html displaySolidWarnings, app.js) ``w.fallback ||
            # w.code`` ile onu basar — kullanıcı ham anahtar GÖRMEZ.
            # Kod, tests/test_engine_warning_i18n.py ZINCIR_BORCU imine
            # gerekçesiyle yazıldı.
            #
            # ``params`` DİLSİZDİR: D-track sözleşmesi (bkz.
            # tests/test_solid_design_point.py::_assert_valid_warning_records)
            # parametrelerde CÜMLE taşımayı yasaklar — string parametre
            # yalnız boşluksuz kimlik olabilir. Uzun künye bu yüzden
            # parametreye DEĞİL, yanıttaki
            # ``two_phase_correction_status_basis`` alanına ve buradaki
            # ``fallback`` cümlesine yazılır.
            # ÖH D34 · OH-P-16 (piksel turu, 21 Eyl 2026): modül kayıp tahmini
            # yayımlamadığında parametre None gidiyor ve ekranda "kayıp
            # tahmini = % ." kalıyordu (kati-02-r06). Sayı yoksa o cümle
            # HİÇ kurulmaz: ayrı kod, ayrı metin (fail-closed; boş yer
            # tutucu basılmaz, sayı da uydurulmaz).
            # Parametreler her iki dalda AÇIKÇA yazılır (** açılımı yok):
            # tests/test_engine_warning_i18n.py yer tutucuları kaynaktan
            # statik okur, açılım görmez.
            _tp_kayip = _tp_durum.get('two_phase_loss_pct')
            _tp_status = str(_tp_durum.get('two_phase_correction_status'))
            _tp_eta = round(float(getattr(self, 'two_phase_efficiency', 1.0)), 6)
            _tp_modul = str(_tp_durum.get('status'))
            if isinstance(_tp_kayip, (int, float)):
                all_warnings.append(dict(_w(
                    'warn.solid.two_phase_correction_unverified', 'warning',
                    status=_tp_status,
                    applied_efficiency=_tp_eta,
                    module_status=_tp_modul,
                    module_loss_percent=round(float(_tp_kayip), 4)),
                    fallback=(
                        'The published Isp carries NO verified two-phase '
                        '(particle-lag) correction: two_phase_correction_status '
                        '= {status}, applied two-phase efficiency = '
                        '{applied_efficiency}, module status = {module_status}, '
                        'module loss estimate = {module_loss_percent} %. Do not '
                        'read this Isp as a verified delivered performance. The '
                        'full reason is published as '
                        'two_phase_correction_status_basis in the same '
                        'response.')))
            else:
                all_warnings.append(dict(_w(
                    'warn.solid.two_phase_correction_unverified_no_estimate',
                    'warning',
                    status=_tp_status,
                    applied_efficiency=_tp_eta,
                    module_status=_tp_modul),
                    fallback=(
                        'The published Isp carries NO verified two-phase '
                        '(particle-lag) correction: two_phase_correction_status '
                        '= {status}, applied two-phase efficiency = '
                        '{applied_efficiency}, module status = {module_status}; '
                        'the module publishes no loss estimate for this state. '
                        'Do not read this Isp as a verified delivered '
                        'performance. The full reason is published as '
                        'two_phase_correction_status_basis in the same '
                        'response.')))

        # 2) Kamara akustik modları. Katıda enjektör yok: chug marjı yerine
        #    yalnız mod tablosu + tehlike bandı, uygulanabilirlik beyanıyla.
        results['acoustic_modes'] = self._acoustic_mode_report()

        # 2b) F2b-1 — yanma kararlılığı (hrma/stability). Akustik bloktan
        #     SONRA: kritik tepki eşiği onun mod tablosunu ve eşdeğer
        #     kavitesini okur (ikinci bir mod tablosu üretilmez). Bulk mod
        #     hükmü çözücünün n >= 1 kapısıyla çapraz denetlenir. Rapor
        #     katmanıdır: itki/basınç/geometri sonucuna geri BESLENMEZ.
        results['combustion_stability'] = self._combustion_stability_block(
            results, curve)

        # 3) Lüle iç akışı (rejim, şok konumu) + ayrılma. Alan profili, bir
        #    satır yukarıda YAYIMLANAN konturdan kurulur — kontur
        #    üretilemediyse iki blok da NOT_MODELLED döner.
        _akis_blok, _ayrilma_blok = self._nozzle_flow_field_report(
            (results.get('nozzle_contour') or {}).get('points'))
        results['nozzle_flow_quasi1d'] = _akis_blok
        results['nozzle_flow_separation'] = _ayrilma_blok

        # --- v2.6.27 (A1-1): boğaz boyutlandırma ölçütünün beyanı ----------
        # Boğaz artık t=0 yanma alanına değil, yanma boyunca ulaşılan EN
        # BÜYÜK gereksinime göre açılıyor. Aynı geometride itki eskisinden
        # düşük çıkar; kullanıcı değişikliği burada görür ve ölçülen tepe
        # basıncının tasarım basıncına oranı da burada yazılıdır.
        results['throat_sizing'] = self._throat_sizing_report(curve)

        # --- v2.6.27 (A1-2): itki eğrisindeki ayrılma bölgesinin beyanı ----
        # Bu blok, teşhis amaçlı nozzle_flow_separation bloğundan FARKLIDIR:
        # oradaki modül tek bir (tasarım) çalışma noktasını inceler ve itkiye
        # geri beslenmez; buradaki alanlar itki eğrisinin GERÇEKTEN kesilmiş
        # lüle modeliyle hesaplandığı örnekleri gösterir.
        _sep = np.asarray(curve.get('separated', []), dtype=bool)
        results['thrust_curve_separation'] = {
            'separated_from_t': curve.get('separated_from_t'),
            'separated_fraction': float(curve.get('separated_fraction', 0.0)),
            'separated_samples': int(_sep.sum()) if _sep.size else 0,
            'total_samples': int(_sep.size),
            'criterion': curve.get('separation_criterion'),
            'applied_to_thrust': True,
            'basis': (
                'Samples flagged here are computed with the TRUNCATED-nozzle '
                'thrust coefficient (separation area ratio from the '
                'Summerfield criterion), not with the attached 1-D relation. '
                'Before v2.6.27 the attached relation was clipped with '
                'max(CF, 0), which reported 0 N thrust while the chamber '
                'pressure and the mass flow were still positive (measured on '
                'this repo: 31% of the slotted curve, 21% wagon wheel, 17% '
                'star). The separated part of the curve is a MODEL estimate: '
                'the one-dimensional attached-flow relation does not hold '
                'there.'),
        }

        # V301/FİZİK-2 (kalem 6, KABUL 13): toplam boy ÇİZİLEN geometriden —
        # CAD-2'nin hibrit tek tanımı (kasa + çizilen lüle + çizilen ön kapak).
        self._cizilen_boy_tek_tanim(results)

        return results

    def _cizilen_boy_tek_tanim(self, results):
        """V301/FİZİK-2 (kalem 6) — katı toplam boyu çizilen geometriden.

        ÖLÇÜLDÜ (KABUL K3 katı; docs/scofield/raw/OH/V301/fizik-2/
        k6_olcu_once.json): STEP/STL lüle arka ucu x = 547,646 mm ⟷
        yayımlanan ``total_length_mm`` 547,183 mm (çözücünün yakınsak +
        ıraksak boyu; çizim örnekleyicisi konik lülede boğaz yayıyla çıkışa
        0,463 mm daha ileride varır); kapaklı boy (STEP max x − min x
        557,088 mm, ön kapak x < 0'da) YAYIMLANMIYORDU. Tek tanım CAD-2'nin
        hibritteki tanımıdır: toplam = kasa + ÇİZİLEN lüle (STEP/STL/DXF ve
        kesitin tek kontur örnekleyicisi ``sample_nozzle_inner_contour``,
        CAD'in kendi girdi normalleştirmesiyle) ve kapaklı toplam = + ÇİZİLEN
        düz ön kapak (``cad_visualization._front_cap_design``, STEP'in
        okuduğu aynı işlev). Örnekleyici çözülemezse eski toplam kalır ve
        künye bunu adıyla söyler (sayı uydurulmaz).
        """
        kd = (results.get('design_summary') or {}).get('key_dimensions')
        if not isinstance(kd, dict) or kd.get('motor_length_mm') is None \
                or kd.get('total_length_mm') is None:
            return
        try:
            import copy
            from hrma.engines.nozzle_design import sample_nozzle_inner_contour
            from hrma.export.cad_visualization import _front_cap_design
            from hrma.export.motor_geometry import normalise_export_geometry
            md, _rapor = normalise_export_geometry(copy.deepcopy(results))
            _pts, meta = sample_nozzle_inner_contour(md)
            lule_mm = float(meta['z_exit'])
            if not (np.isfinite(lule_mm) and lule_mm > 0.0):
                raise ValueError('the sampled exit station is not a '
                                 'positive finite number')
            kapak = _front_cap_design(md)
            kapak_mm = (float(kapak['thickness_mm'])
                        if isinstance(kapak, dict)
                        and kapak.get('thickness_mm') is not None else None)
        except Exception as hata:  # noqa: BLE001 — künyeye adıyla yazılır
            kd['total_length_basis'] = (
                'case length + solver nozzle sections (convergent + '
                'divergent); the drawn nozzle length could not be resolved '
                f'({type(hata).__name__}: {hata})')[:400]
            return
        toplam = float(kd['motor_length_mm']) + lule_mm
        kd['total_length_mm'] = toplam
        kd['nozzle_drawn_length_mm'] = lule_mm
        if kapak_mm is not None and np.isfinite(kapak_mm) and kapak_mm > 0:
            kd['forward_closure_length_mm'] = kapak_mm
            kd['total_length_with_closure_mm'] = toplam + kapak_mm
        kd['total_length_basis'] = (
            'total_length_mm = case length (motor_length_mm) + the DRAWN '
            'nozzle (nozzle_drawn_length_mm: convergent inlet to exit plane '
            'of the one contour sampler the STEP/STL/DXF and the Motor '
            'Cross-Section use; for a conical nozzle the throat arc moves '
            'the exit plane beyond the solver nozzle sections). '
            'total_length_with_closure_mm adds the flat forward closure the '
            'manufacturing STEP draws at x < 0 (forward_closure_length_mm, '
            'the same function the exporter reads). It is THE total motor '
            'length, the same definition as the hybrid '
            'total_motor_length_with_caps_mm.')