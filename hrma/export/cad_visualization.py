"""
3D CAD Visualization Module for Hybrid Rocket Motors
Combines motor assembly visualization (MotorCADDesigner) and
detailed engineering cross-section views (DetailedCADGenerator).

Both classes use Plotly for interactive 3D rendering.
MotorCADDesigner also uses trimesh for mesh-based geometry.
"""

import numpy as np
import trimesh

from hrma.constants import G_0
from hrma.data.materials_db import get_material
from hrma.engines.nozzle_design import sample_nozzle_inner_contour
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from typing import Dict, List, Tuple, Optional
import json
import base64
import math
from io import BytesIO


# =============================================================================
# MotorCADDesigner - 3D Motor Assembly (trimesh + Plotly)
# Originally from cad_design.py
# =============================================================================

def _real_nested(d, path):
    """İç içe dict'ten sonlu pozitif float çek (yoksa None)."""
    cur = d
    for k in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    try:
        v = float(cur)
    except (TypeError, ValueError):
        return None
    return v if (np.isfinite(v) and v > 0) else None


# ---------------------------------------------------------------------------
# Çıktı etiketleri — TEK tanım noktası (CLAUDE.md kural 11).
# Bir imalat değeri çözücüden gelmiyorsa sabit sayı UYDURULMAZ; alan bu
# metinle işaretlenir, kullanıcı neyin hesaplanmadığını görür.
# ---------------------------------------------------------------------------
NOT_AVAILABLE_SPEC = 'NOT AVAILABLE - not produced by this analysis run'

# Yapısal analiz yoksa 3B mesh ve kütle hesabı AYNI yedek cidar kuralını
# kullanır (görsel ile kütlenin çelişmemesi için tek sabit).
CHAMBER_WALL_FALLBACK_FRACTION = 0.045  # cidar / kamara çapı

# 3B mesh üretiminde delik sayısı üst sınırı (boolean kararlılığı). YALNIZ
# mesh için geçerlidir; teknik çizim ve spesifikasyon çıktısı gerçek sayıyı
# yazar (bkz. _injector_spec).
MESH_MAX_INJECTOR_ORIFICES = 16

# Nitel imalat zorluğu (beceri seviyesi, özel takım) atölye deneyimi
# kaynaklıdır; motorun hesabından türetilmez ve çıktıda böyle etiketlenir.
MANUFACTURING_EFFORT_BASIS = ('typical machine-shop experience for this size '
                              'class; not computed from the analysis')

# Termin (işleme/montaj süresi) alanları v2.6.26'da KALDIRILDI — V2.6.26
# planı §2.2. Arayüz boş hücre yerine bu açıklamayı basabilsin diye alanın
# yokluğu açıkça raporlanır (sıvı motordaki MANUFACTURING_COST_STATUS deseni).
MANUFACTURING_EFFORT_STATUS = (
    'not calculated: HRMA has no machine-shop routing, labour-rate or '
    'programme schedule data. Machining and assembly durations were removed '
    'because the previous values ("24-48 hours", "4-6 hours") were fixed '
    'literals, identical for a 500 N amateur motor and a 50 kN motor')

# İmalat notlarında SAYILAR çözücüden gelir; adımların kendisi (tornalama,
# delme, çapak alma, sızdırmazlık) genel atölye pratiğidir ve bu motorun
# analizinden türetilmez. MANUFACTURING_EFFORT_BASIS ile aynı desen.
MANUFACTURING_NOTE_BASIS = ('numeric values in the steps above come from this '
                            'analysis run (source named inline); the process '
                            'steps themselves are general machine-shop practice '
                            'and are not computed for this motor')

# ANSI B1.1 / AWS D1.1 gerçek standartlardır, ancak "bu tasarıma uygulanır"
# iddiası bu yazılım tarafından DOĞRULANMAZ; referans olarak listelenir.
MANUFACTURING_STANDARD_BASIS = ('the standards cited (ANSI B1.1 threads, '
                                'AWS D1.1 welding) are real published standards '
                                'listed for reference only; this analysis does '
                                'not verify that they are the applicable '
                                'standards for this design')

# Yüzey pürüzlülüğü bu yazılımın tasarım çıktısı DEĞİLDİR; standart atölye
# değeridir ve çizim sözlüğünde kaynağıyla (finish_basis) birlikte verilir.
# v2.6.26 (P4): DRAWING_TOLERANCE_BASIS kaldırıldı — künyesi ("ISO 2768-m")
# ile yanında yazılan sabit sayılar ('+-0.1 mm' / '+-0.5 mm') birbirini
# tutmuyordu. Tolerans artık ölçüden aranır: bkz. _iso2768_tolerance_block.
DRAWING_SURFACE_FINISH_BASIS = ('ISO 1302 typical machined finish (workshop '
                                'standard, not computed by this analysis)')
DRAWING_SURFACE_FINISH_CHAMBER = 'Ra 3.2 um'
DRAWING_SURFACE_FINISH_NOZZLE = 'Ra 1.6 um'
DRAWING_SURFACE_FINISH_INJECTOR = 'Ra 0.8 um'


def _real_scalar(value):
    """Sonlu pozitif float döndürür; aksi halde None (uydurma varsayılan yok)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if (np.isfinite(v) and v > 0) else None


def _iso2768_tolerance_block(bore_mm, outer_mm, length_mm):
    """Kamara çizimi için ISO 2768-1 genel tolerans bloğu.

    v2.6.26 (P4). Öncesi: sabit '+-0.1 mm' çap / '+-0.5 mm' boy. Bu iki sayı
    75 mm'lik amatör motorla 500 mm'lik motora aynıydı VE yanlarındaki künye
    "ISO 2768-m" diyordu — oysa o standardın tablosu ölçüye göre değişir.
    Yani sayılar gösterilen kaynağa uymuyordu.

    Tablo BU DOSYADA TEKRAR TANIMLANMAZ: proje içinde tek tanım noktası
    ``hrma.engines.liquid_rocket_engine`` içindedir (sıvı motorun kritik
    tolerans bloğu onu kullanır). Modül okunamazsa sayı UYDURULMAZ; blok
    'NOT_AVAILABLE' durumu döner.

    İşlenmiş yatak yüzeyleri hassas (f), gövde/montaj ölçüleri orta (m)
    sınıfta aranır — sıvı motordaki aynı gerekçe.
    """
    try:
        from hrma.engines.liquid_rocket_engine import (
            ISO2768_GRADE_GENERAL, ISO2768_GRADE_PRECISION,
            ISO2768_TOLERANCE_BASIS, _iso2768_feature)
    except Exception as exc:                       # pragma: no cover
        return {'status': 'NOT_AVAILABLE',
                'basis': f'ISO 2768-1 tolerance table unavailable: {exc}'}

    def _feature(nominal, grade):
        # Ölçü yoksa tolerans da yoktur; komşu alanlarla aynı etiket kullanılır.
        return _iso2768_feature(nominal, grade) or NOT_AVAILABLE_SPEC

    return {
        # Grain/kapak bu deliğe oturur: işlenmiş yatak -> hassas sınıf
        'diameter': _feature(bore_mm, ISO2768_GRADE_PRECISION),
        'outer_diameter': _feature(outer_mm, ISO2768_GRADE_GENERAL),
        'length': _feature(length_mm, ISO2768_GRADE_GENERAL),
        'basis': ISO2768_TOLERANCE_BASIS,
        'source': ('ISO 2768-1 Table 1 (permissible deviations for linear '
                   'dimensions), classes f and m'),
    }


def _nozzle_half_angles(motor_data):
    """Lüle yarı açılarını ÇÖZÜCÜ çıktısından okur.

    Döner: (konverjan_derece|None, diverjan_derece|None, lüle_tipi)
    Kaynak sırası: nozzle_angles -> nozzle_contour.divergent. Bell lülede
    diverjan açısı boğaz çıkış açısıdır (tek bir konik açı yoktur), bu yüzden
    tip de döndürülür ve çizim etiketinde kullanılır. Değer yoksa None döner —
    çağıran sabit 15°/12° uydurmak yerine açıyı hiç etiketlemez.
    """
    md = motor_data or {}
    angles = md.get('nozzle_angles') or {}
    divergent = (md.get('nozzle_contour') or {}).get('divergent') or {}

    conv = _real_scalar(angles.get('convergent_half_angle_deg'))
    noz_type = (divergent.get('type') or angles.get('nozzle_type') or '').lower()

    div = _real_scalar(angles.get('divergent_half_angle_deg'))
    if noz_type == 'bell':
        # Bell: boğaz çıkış açısı gerçek imalat açısıdır
        div = _real_scalar(divergent.get('throat_angle')) or div
    elif div is None:
        div = _real_scalar(divergent.get('half_angle'))

    return conv, div, (noz_type or 'conical')


def _nozzle_length_m(motor_data):
    """Lüle boyu [m] — sonuçta varsa oradan, yoksa GERÇEK kontur uzunluğundan.

    Sabit 0.15 m yedeği kullanılmaz: sample_nozzle_inner_contour zaten motorun
    kendi geometrisinden çıkarılmış konturu döndürür.
    """
    md = motor_data or {}
    length = _real_scalar(md.get('nozzle_length'))
    if length is not None:
        return length
    try:
        _pts, meta = sample_nozzle_inner_contour(md)
        return float(meta['z_exit']) / 1000.0
    except Exception:
        return None


def _first_real(mapping, *keys):
    """Verilen anahtarlardan İLK sonlu-pozitif değeri döndürür (yoksa None)."""
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        value = _real_scalar(mapping.get(key))
        if value is not None:
            return value
    return None


def _injector_spec(motor_data):
    """Enjektör için TEK doğruluk kaynağı.

    Döner: {'n_orifices', 'orifice_diameter_mm', 'plate_diameter_mm',
            'type', 'pressure_drop_bar', 'source'}
    Aynı motor koşusunda ekran grafiği, teknik çizim PDF'i ve CAD sözlüğü
    farklı delik sayıları gösteriyordu (2026-07-19 denetimi, kritik bulgu);
    bütün CAD/çizim katmanı artık bu tek fonksiyondan okur. Değer yoksa
    None bırakılır — sabit sayı uydurulmaz.

    KAYNAK KARIŞTIRMA YASAĞI (v2.6.26, K2 denetimi). Hibrit ``/calculate``
    İKİ bağımsız enjektör çözücüsü koşturur:
      1. Enjektör paneli (``injector_results``) — ekran tablosu ve 2B şema,
      2. Motorun kendi devre modeli (``injector_design`` /
         ``injector_design_detail``) — N2O'da doyma basıncını kullanır.
    Eski kod delik sayısını (1)'den, basınç düşümünü (2)'den okuyabiliyordu.
    Ölçüldü: panel 125 delik x 0,957 mm / ΔP 4,00 bar derken çizim sözlüğü
    aynı satırda ΔP 30,37 bar yazıyordu — 7,6 kat. Böyle bir enjektör HİÇBİR
    çözücüde yoktur; melez spesifikasyon uydurmadır. Artık bir kaynak seçilir
    ve BÜTÜN alanlar o kaynaktan okunur; kaynakta olmayan alan None kalır.
    """
    md = motor_data or {}
    detail = md.get('injector_design_detail') or {}
    if not isinstance(detail, dict):
        detail = {}
    ox = detail.get('ox_circuit') or {}

    # Öncelik: kullanıcının enjektör panelinden gelen sonuç (ΔP/hız hedefleri
    # oradan giriliyor) motor sonucuna eklenmişse o kazanır; yoksa motorun
    # kendi devre modeli.
    panel = md.get('injector_results') or {}
    if panel:
        n = _first_real(panel, 'number_of_orifices', 'n_holes', 'n_elements')
        d_mm = _first_real(panel, 'orifice_diameter_mm', 'hole_diameter',
                           'orifice_diameter')
        dp = _first_real(panel, 'injection_pressure_drop_bar',
                         'pressure_drop_bar', 'pressure_drop')
        # Enjektör TİPİ iki çözücüde de aynı kullanıcı seçimidir (boyutlandırma
        # değil, kimlik alanıdır); panelde adı 'type' ile de gelebilir.
        inj_type = panel.get('injector_type') or panel.get('type')
        source_name = 'injector panel (injector_results)'
    else:
        inj = md.get('injector_design') or md.get('injector') or {}
        n = (_first_real(inj, 'number_of_orifices', 'n_holes', 'n_elements')
             or _first_real(ox, 'n_orifices'))
        d_mm = (_first_real(inj, 'orifice_diameter_mm', 'hole_diameter')
                or _first_real(ox, 'orifice_d_mm'))
        dp = (_first_real(inj, 'injection_pressure_drop_bar')
              or _first_real(ox, 'delta_p_bar'))
        inj_type = (inj.get('injector_type') or inj.get('type')
                    or detail.get('injector_type'))
        source_name = 'motor result injector_design'

    plate_mm = _real_scalar(md.get('chamber_diameter'))
    plate_mm = plate_mm * 1000.0 if plate_mm is not None else None

    return {
        'n_orifices': int(round(n)) if n else None,
        'orifice_diameter_mm': d_mm,
        'plate_diameter_mm': plate_mm,
        'type': inj_type,
        'pressure_drop_bar': dp,
        'source': source_name if n else 'not available',
    }


#: Yapısal analiz sonucunda kamara/kasa cidarının yaşadığı ÜÇ ayrı şema.
#: Motor tipleri aynı büyüklüğü farklı adla yayımlıyor — imalata giden STEP
#: yalnız ilkini tanıdığı için katı ve sıvı motorda cidarı BULAMIYOR ve
#: 0.045·D geometrik yedeğine düşüyordu (Faz 4B / A8).
#: Ölçüm (Ø100 mm katı motor, HEAD a7ff1e7): analiz
#: case_analysis.wall_thickness_mm = 2.40 mm, STEP'in ürettiği cidar 4.50 mm.
#: Her giriş: (blok_adı, as_designed_anahtar, önerilen_anahtar,
#: as_designed_kesin_mi) — değerler mm.
#: Son alan: blokta ``design_mode`` yoksa as-designed kalınlığın gerilmelerin
#: GERÇEKTEN hesaplandığı kalınlık olduğunu bildirir. Katıda
#: ``hoop_stress = P·r/t_wall`` doğrudan ``_case_design()``in verdiği
#: ``wall_thickness_mm`` ile, sıvıda ``chamber_structure.wall_thickness`` ile
#: hesaplanır; önerilen/gerekli kalınlık ayrı bir alandır. Öneriyi çizmek
#: kullanıcının tasarımını sessizce değiştirirdi (hibritte Y5 ile kapatılan
#: kusurun aynısı).
CHAMBER_WALL_SCHEMAS = (
    # hibrit / ortak yapısal modül (analysis/structural_analysis.py)
    ('chamber_analysis', 'wall_thickness_used_mm', 'recommended_thickness',
     False),
    # katı motor (engines/solid_rocket_engine.py::_calculate_structural_analysis)
    ('case_analysis', 'wall_thickness_mm', 'recommended_wall_thickness_mm',
     True),
    # sıvı motor (engines/liquid_rocket_engine.py::_calculate_structural_loads)
    ('chamber_structure', 'wall_thickness', 'required_wall_thickness', True),
)


def _chamber_wall_block(struct):
    """Yapısal sonuçtaki cidar bloğunu şema sırasına göre bulur.

    Döner: (blok_sözlüğü, as_designed_mm|None, önerilen_mm|None, blok_adı|None,
            as_designed_kesin_mi)
    """
    struct = struct or {}
    for block_name, used_key, recommended_key, as_designed_is_authoritative \
            in CHAMBER_WALL_SCHEMAS:
        block = struct.get(block_name)
        if not isinstance(block, dict):
            continue
        used_mm = _real_nested(struct, (block_name, used_key))
        recommended_mm = _real_nested(struct, (block_name, recommended_key))
        if used_mm is None and recommended_mm is None:
            continue
        return (block, used_mm, recommended_mm, block_name,
                as_designed_is_authoritative)
    return {}, None, None, None, False


def _chamber_wall_design(motor_data):
    """Kamara cidarı: ÇİZİLECEK kalınlık + yapısal öneri + hangi SF'nin geçerli olduğu.

    v2.6.26 denetimi (Y5): CAD çizimi ve 3B katı, kullanıcının girdiği cidar
    kalınlığını YOK SAYIP her zaman yapısal analizin ÖNERDİĞİ kalınlığı
    çiziyordu. Ölçüldü: kullanıcı 3 / 5 / 10 / 20 mm girse de çizim 15,92 mm
    ve kamara kütlesi 232,04 kg SABİT kalıyordu. Malzeme değişiminde sapma
    daha büyüktü: Alüminyum 6061'de çizim 49,92 mm cidar gösterirken yapısal
    panel kullanıcının 5 mm'si için SF 0,466 ("güvensiz") diyordu — yani
    ekrandaki emniyet katsayısı ÇİZİLEN parçaya ait değildi.

    Çözüm tek kurala indirgenir: **gerilmelerin hesaplandığı kalınlık çizilir.**
    ``structural_analysis.chamber_analysis`` bunu zaten ayırıyor:
      * ``design_mode == 'verify'`` -> kullanıcı bir cidar girdi; gerilmeler ve
        emniyet katsayıları O kalınlığa aittir -> ``wall_thickness_used_mm``.
      * ``design_mode == 'size'``   -> kullanıcı girmedi; yazılım boyutlandırdı
        ve ``wall_thickness_used_mm == recommended_thickness``.
    Böylece çizilen geometri ile ekrandaki emniyet katsayısı AYNI parçayı
    anlatır. Öneri ayrıca ``recommended_mm`` alanında taşınır ve ikisi
    farklıysa ``note`` alanı bunu AÇIKÇA söyler (imalatçı hangi kalınlığın
    hangi SF'ye ait olduğunu görmeden torna tezgâhına gitmemeli).

    Döner sözlük:
        thickness_m     -> çizilecek/kütlelenecek kalınlık [m] (None olabilir)
        source          -> insan okur kaynak etiketi
        as_designed_mm  -> gerilmelerin ait olduğu kalınlık [mm] (None olabilir)
        recommended_mm  -> yapısal analizin önerdiği kalınlık [mm] (None olabilir)
        design_mode     -> 'verify' | 'size' | None
        safety_factor   -> as_designed kalınlığa ait toplam emniyet katsayısı
        note            -> çizilen ile önerilen farklıysa uyarı metni, yoksa None
    """
    struct = (motor_data or {}).get('structural_analysis') or {}
    # Üç motor tipinin üç ayrı şeması tek yerden çözülür (A8).
    (chamber, used_mm, recommended_mm, block_name,
     as_designed_is_authoritative) = _chamber_wall_block(struct)
    design_mode = chamber.get('design_mode')
    safety_factor = (_real_scalar(chamber.get('safety_factor_total'))
                     or _real_scalar(chamber.get('hoop_safety_factor'))
                     or _real_scalar(chamber.get('safety_factor')))

    # Kullanıcının cidarı YALNIZ 'verify' modunda açıkça bildirilmiştir.
    # Mod bilinmiyorsa (eski sözlükler) eski davranış korunur: öneri çizilir.
    if (used_mm is not None
            and (design_mode == 'verify' or as_designed_is_authoritative)):
        thickness_mm = used_mm
        # Sayı yine yapısal analizin çıktı alanından (wall_thickness_used_mm /
        # wall_thickness_mm / wall_thickness) gelir; bu, gerilmelerin
        # hesaplandığı as-designed cidardır.
        source = ('structural analysis (as-designed wall thickness, '
                  f'verified against the pressure load) [{block_name}]')
    elif recommended_mm is not None:
        thickness_mm = recommended_mm
        source = f'structural analysis (recommended thickness) [{block_name}]'
    elif used_mm is not None:
        thickness_mm = used_mm
        source = ('structural analysis (thickness used in the stress check) '
                  f'[{block_name}]')
    else:
        thickness_mm = None
        source = 'not available'

    note = None
    if (thickness_mm is not None and recommended_mm is not None
            and abs(thickness_mm - recommended_mm) > 1e-6):
        note = (f'drawn wall is the as-designed {thickness_mm:.2f} mm; the '
                f'structural sizing recommends {recommended_mm:.2f} mm. '
                f'Safety factors reported for this motor belong to the '
                f'as-designed {thickness_mm:.2f} mm wall, NOT to the '
                f'recommended one.')

    return {
        'thickness_m': (thickness_mm / 1000.0) if thickness_mm is not None else None,
        'source': source,
        'as_designed_mm': used_mm,
        'recommended_mm': recommended_mm,
        'design_mode': design_mode,
        'safety_factor': safety_factor,
        'note': note,
        'schema': block_name,
    }


def _chamber_wall_thickness_m(motor_data):
    """Kamara cidar kalınlığı [m] — çizilen/kütlelenen kalınlık.

    Döner: (kalınlık_m|None, kaynak_etiketi). Ayrıntı için
    :func:`_chamber_wall_design`.
    """
    design = _chamber_wall_design(motor_data)
    return design['thickness_m'], design['source']


def _chamber_wall_effective_m(motor_data, chamber_diameter_m):
    """3B katının ve kütle dökümünün GERÇEKTEN kullandığı cidar [m].

    Yapısal sonuç yoksa CAD katmanı geometrik yedek kurala düşer; mesh, kütle
    ve zarf çapı bu TEK fonksiyondan okur ki üçü çelişmesin. Yedek kural
    kullanıldığında çizim sözlüğü yine de sayı yazmaz (bkz.
    ``_generate_technical_drawings``) — imalata giden ölçü uydurulmaz.
    """
    design = _chamber_wall_design(motor_data)
    wall_m = design['thickness_m']
    if wall_m is not None:
        return wall_m, design['source']
    d = _real_scalar(chamber_diameter_m)
    if d is None:
        return None, design['source']
    return (max(0.004, CHAMBER_WALL_FALLBACK_FRACTION * d),
            'geometric fallback (no structural result in this run)')


def _chamber_material(motor_data):
    """Kamara malzemesi — yapısal analizde SEÇİLEN kayıt.

    Döner: (materials_db kaydı|None, görünen_ad, yoğunluk_kg_m3|None)
    """
    struct = (motor_data or {}).get('structural_analysis') or {}
    props = struct.get('material_properties') or {}
    key = ((struct.get('design_parameters') or {}).get('material')
           or (motor_data or {}).get('chamber_material'))
    name = props.get('name')
    density = _real_scalar(props.get('density'))
    if key and not (name and density):
        try:
            rec = get_material(str(key))
            name = name or rec.get('name')
            density = density or _real_scalar(rec.get('density'))
        except Exception:
            pass
    return key, name, density


def _cad_material(db_key, fields, color):
    """Merkezi materials_db kaydından CAD tablosu girdisi üretir.

    Sayısal alanlar (density, yield_strength, melting_point...) TEK
    doğruluk kaynağından (hrma/data/materials_db.py) okunur; yalnız
    görsel alanlar (color) bu modülde yerel kalır. Önceki yerel tablo
    merkezle çelişiyordu (Inconel 1034 vs 1100 MPa, grafit 2200 vs
    1800 kg/m^3 vb.).
    """
    rec = get_material(db_key)
    entry = {f: rec[f] for f in fields}
    entry['color'] = color
    return entry


class MotorCADDesigner:
    """Professional 3D CAD design for hybrid rocket motors"""

    def __init__(self):
        # Anahtarlar geriye dönük korunur; değerler merkezi DB'den gelir.
        self.materials_db = {
            'chamber': {
                'steel_304': _cad_material('ss_304', ('density', 'yield_strength'), '#C0C0C0'),
                'aluminum_6061': _cad_material('aluminum_6061', ('density', 'yield_strength'), '#A8A8A8'),
                'inconel_718': _cad_material('inconel_718', ('density', 'yield_strength'), '#808080'),
            },
            'nozzle': {
                'graphite': _cad_material('graphite', ('density', 'melting_point'), '#2F2F2F'),
                'tungsten': _cad_material('tungsten', ('density', 'melting_point'), '#404040'),
                'copper': _cad_material('copper', ('density', 'melting_point'), '#B87333'),
            },
            'injector': {
                'stainless_steel': _cad_material('ss_316', ('density', 'yield_strength'), '#E5E5E5'),
                'titanium': _cad_material('titanium_6al4v', ('density', 'yield_strength'), '#C4C4C4'),
            }
        }

        self.standard_dimensions = {
            'motor_classes': {
                'H': {'diameter': 0.075, 'length': 0.4},
                'I': {'diameter': 0.075, 'length': 0.6},
                'J': {'diameter': 0.098, 'length': 0.7},
                'K': {'diameter': 0.098, 'length': 0.9},
                'L': {'diameter': 0.150, 'length': 1.2},
                'M': {'diameter': 0.150, 'length': 1.5}
            }
        }

    def generate_3d_motor_assembly(self, motor_data: Dict) -> Dict:
        """Generate complete 3D motor assembly with all components"""

        # Yerel kopyada çalış: aşağıdaki motor_data.update(...) çağrıcının
        # motor_results sözlüğünü YERİNDE değiştiriyordu (chamber_length'i
        # kaba L* kuralıyla ezip /calculate yanıtını bozuyordu)
        #
        # Faz 5B / H4-2: kopya artık aynı zamanda BİRİM olarak normalize
        # edilir. Ölçüldü (HEAD 9d3728e): ham ``/calculate_solid`` yanıtı
        # verilince STL zarfı 126 313 × 126 313 × 174 992 mm çıkıyordu
        # (gerçek 126.31 × 126.31 × 782.68 mm) — çünkü buradaki her okuma
        # girdiyi koşulsuz METRE kabul ediyordu, katı rotası ise mm döndürür.
        from hrma.export.motor_geometry import (
            normalise_export_geometry, resolve_grain_m)
        motor_data, _unit_report = normalise_export_geometry(motor_data)
        grain_geo, grain_reason = resolve_grain_m(motor_data)

        try:
            # Extract motor parameters from calculation results
            chamber_diameter = motor_data.get('chamber_diameter', 0.1)  # m
            throat_diameter = motor_data.get('throat_diameter', 0.02)  # m
            exit_diameter = motor_data.get('exit_diameter', 0.04)  # m

            print(f"CAD Debug - Chamber: {chamber_diameter}, Throat: {throat_diameter}, Exit: {exit_diameter}")

            # Check for design configuration
            design_config = motor_data.get('design_config', {})
            motor_config = design_config.get('motor', {})
            injector_config = design_config.get('injector', {})

            # ---- GERÇEK ÇÖZÜCÜ GEOMETRİSİ ----
            # Önce motor_results'taki hesaplanmış değerler; anahtar yoksa eski
            # kaba kurallara düşülür. (Eski davranış: port=0.4·D, L=f(L*) gibi
            # kurallar çözücü çıktısını YOK SAYIYORDU — STL çıktısı analizle
            # tutarsızdı.)
            def _real(key, lo, hi):
                v = motor_data.get(key)
                try:
                    v = float(v)
                except (TypeError, ValueError):
                    return None
                return v if (np.isfinite(v) and lo < v < hi) else None

            total_impulse = motor_data.get('total_impulse', 10000)
            thrust = motor_data.get('thrust', 1000)
            burn_time = motor_data.get('burn_time', 10)
            l_star = motor_data.get('l_star', 1.0)

            chamber_length = _real('chamber_length', 0.02, 5.0)
            if chamber_length is None:
                # Eski L* kuralı (yalnız gerçek değer yoksa)
                throat_area = np.pi * (throat_diameter / 2) ** 2
                chamber_length = (l_star * throat_area) / (np.pi * (chamber_diameter / 2) ** 2)
                chamber_length = max(0.3, min(2.0, chamber_length))
            if motor_config.get('chamber_length_override'):
                chamber_length = motor_config['chamber_length_override'] / 1000.0

            # Nozul konturu: 2D kesit ve 3D görselleştirmeyle AYNI kaynak
            noz_pts_mm, noz_meta = sample_nozzle_inner_contour(motor_data)
            nozzle_length = noz_meta['z_exit'] / 1000.0

            # Duvar kalınlıkları
            # v2.6.26 (Y5): kullanıcının cidarı ÇİZİLİR. Eski kod hem öneriye
            # sabitliydi hem de 0.12·D üst sınırıyla kırpıyordu; kırpma
            # kullanıcının tasarımını sessizce değiştirdiği için kaldırıldı
            # (çizim sözlüğü, kütle dökümü ve STL artık AYNI kalınlığı taşır).
            wall_case, _wall_src = _chamber_wall_effective_m(motor_data,
                                                             chamber_diameter)
            noz_geo = motor_data.get('nozzle_geometry') or {}
            wall_noz = noz_geo.get('wall_thickness')
            wall_noz = (wall_noz / 1000.0) if wall_noz else max(0.003, 0.1 * throat_diameter)

            # Grain: gerçek port + gerçek boy. H4-1: yoksa GRAIN ÇİZİLMEZ.
            # Eski kod portu ``chamber_diameter * 0.4``, boyu
            # ``chamber_length - 0.05`` ile uyduruyordu; sıvı çift yakıtlı
            # motorda grain fiziksel olarak yokken STL/3B görünümde
            # Ø39.7 mm portlu bir katı yakıt bloğu görünüyordu (ölçüldü:
            # liquid fuel_grain.stl 95.22 × 95.22 × 47.96 mm).
            if grain_geo is not None:
                port_diameter = grain_geo['port_initial']
                grain_length = min(grain_geo['length'], 0.98 * chamber_length)
            else:
                port_diameter = None
                grain_length = None
            liner = min(max(0.02 * chamber_diameter, 0.0015), 0.005)

            # Enjektör: TEK doğruluk kaynağı (_injector_spec) — teknik çizim,
            # PDF, STEP/DXF ve bu mesh AYNI enjektörü anlatmalı.
            # v2.6.26 (K2): burası `injector_design`'ı DOĞRUDAN okuyordu;
            # çizim sözlüğü ise panel sonucunu kullanıyordu. Ölçüldü: aynı
            # koşuda mesh 11 delik x 2,457 mm delerken çizim 125 delik x
            # 0,957 mm yazıyordu. STL'i açan kişi çizimdeki parçayı GÖRMÜYORDU.
            inj_spec = _injector_spec(motor_data)
            injector_orifices_real = inj_spec['n_orifices']
            if not injector_orifices_real and injector_config.get('n_holes_override'):
                injector_orifices_real = int(injector_config['n_holes_override'])
            # Gerçek (kırpılmamış) sayı korunur: MESH kararlılığı için delik
            # sayısı sınırlanır ama teknik çizim/spesifikasyon çıktısı gerçek
            # sayıyı yazmalıdır (2026-07-19 denetimi: çözücü 41 orifis derken
            # çizimde 16 görünüyordu).
            if injector_orifices_real:
                injector_orifices = max(1, min(int(injector_orifices_real),
                                               MESH_MAX_INJECTOR_ORIFICES))
            else:
                # Hiçbir çözücü delik üretmedi -> DELİK AÇILMAZ. Eski kod 8
                # delik uydurup çapını akıştan türetiyordu; kullanıcı bunun
                # hesaplanmış bir desen olduğunu sanıyordu (v2.6.26 denetimi).
                injector_orifices = 0
            ori_mm = inj_spec['orifice_diameter_mm']
            # Çap yalnız delik sayısıyla BİRLİKTE anlamlıdır; biri yoksa
            # diğeri de çizilmez.
            orifice_diameter = (max(0.0005, min(0.01, ori_mm / 1000.0))
                                if (ori_mm and injector_orifices) else 0.0)
            if not orifice_diameter:
                injector_orifices = 0

            # Türetilen boyutları KOPYAYA yaz (çağıranın dict'i korunur)
            motor_data.update({
                'chamber_length': chamber_length,
                'nozzle_length': nozzle_length,
                'port_diameter': port_diameter,
                'injector_orifices': injector_orifices,          # MESH için kırpılmış
                'injector_orifices_real': injector_orifices_real,  # gerçek sayı
                'orifice_diameter': orifice_diameter,
                'design_config': design_config
            })

            # ---- Bileşen katıları (kapalı profil revolve — boolean'sız, watertight) ----
            print("CAD Debug - Creating chamber mesh...")
            cap_t = min(max(1.6 * wall_case, 0.008), 0.3 * chamber_diameter / 2 + 0.008)
            chamber_mesh = self._chamber_solid(chamber_diameter, chamber_length, wall_case, cap_t)

            print("CAD Debug - Creating nozzle mesh...")
            nozzle_mesh = self._nozzle_solid(noz_pts_mm, wall_noz)

            print("CAD Debug - Creating injector mesh...")
            injector_mesh = self._create_injector_head(chamber_diameter, motor_data)

            if grain_geo is not None:
                print("CAD Debug - Creating fuel grain mesh...")
                slack = max(0.004, chamber_length - grain_length)
                zg0 = 0.35 * slack
                fuel_grain_mesh = self._grain_solid(
                    chamber_diameter / 2 - liner, port_diameter / 2, zg0,
                    zg0 + grain_length
                )
            else:
                print("CAD Debug - no grain in the result; grain mesh skipped")
                fuel_grain_mesh = None

            # ---- Yerleşim: z=0 kapak iç yüzü, kamara [0, L], nozul [L, L+Ln] ----
            assembly_meshes = []

            chamber_mesh.visual.face_colors = [200, 200, 200, 100]
            assembly_meshes.append(('Chamber', chamber_mesh))

            nozzle_mesh.apply_translation([0, 0, chamber_length])
            nozzle_mesh.visual.face_colors = [50, 50, 50, 255]
            assembly_meshes.append(('Nozzle', nozzle_mesh))

            # Enjektör plakası kamara içinde, kapak iç yüzüne yakın
            injector_mesh.apply_translation([0, 0, 0.006 + 0.015])
            injector_mesh.visual.face_colors = [150, 150, 150, 200]
            assembly_meshes.append(('Injector', injector_mesh))

            if fuel_grain_mesh is not None:
                fuel_grain_mesh.visual.face_colors = [139, 69, 19, 150]
                assembly_meshes.append(('Fuel Grain', fuel_grain_mesh))

            print("CAD Debug - Creating plotly visualization...")
            # Create plotly visualization
            plotly_data = self._create_plotly_visualization(assembly_meshes, motor_data)

            print("CAD Debug - Generating technical drawings...")
            # Generate technical drawings
            technical_drawings = self._generate_technical_drawings(motor_data)

            print("CAD Debug - Creating material specifications...")
            # Create material specifications
            material_specs = self._generate_material_specifications(motor_data)

            return {
                'assembly_meshes': assembly_meshes,
                'plotly_visualization': plotly_data,
                'technical_drawings': technical_drawings,
                'material_specifications': material_specs,
                'manufacturing_notes': self._generate_manufacturing_notes(motor_data),
                'performance_summary': self._generate_cad_performance_summary(motor_data)
            }

        except Exception as e:
            print(f"CAD generation error: {str(e)}")
            import traceback
            traceback.print_exc()
            return {
                'error': f'CAD generation failed: {str(e)}',
                'assembly_meshes': [],
                'plotly_visualization': None,
                'technical_drawings': None,
                'material_specifications': {},
                'manufacturing_notes': [],
                'performance_summary': {}
            }


    @staticmethod
    def _fix_solid(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
        """Revolve çıktısını STL'e uygun hale getir: dejenere üçgenleri at,
        normal yönünü dışa çevir (negatif hacim = ters sarım)."""
        mesh.update_faces(mesh.nondegenerate_faces())
        mesh.remove_unreferenced_vertices()
        mesh.merge_vertices()
        if mesh.volume < 0:
            mesh.invert()
        return mesh

    def _chamber_solid(self, diameter: float, length: float,
                       wall: float, cap_t: float) -> trimesh.Trimesh:
        """Baş kapak + silindirik tüp tek kapalı profil revolve katısı (m)."""
        r_in = diameter / 2
        r_out = r_in + wall
        profile = np.array([
            [0.0, -cap_t],
            [r_out, -cap_t],
            [r_out, length],
            [r_in, length],
            [r_in, 0.0],
            [0.0, 0.0],
            [0.0, -cap_t],
        ])
        return self._fix_solid(trimesh.creation.revolve(profile))

    def _nozzle_solid(self, inner_pts_mm, wall: float) -> trimesh.Trimesh:
        """Gerçek iç konturdan duvarlı nozul katısı.

        inner_pts_mm: sample_nozzle_inner_contour çıktısı [(z_mm, r_mm), ...]
        (z=0 konverjan başlangıcı). Dönen katı z=0'dan başlar (metre).
        """
        inner = [(r / 1000.0, z / 1000.0) for z, r in inner_pts_mm]
        outer = [(r + wall, z) for r, z in reversed(inner)]
        profile = np.array(inner + outer + [inner[0]])
        return self._fix_solid(trimesh.creation.revolve(profile))

    def _grain_solid(self, r_outer: float, r_port: float,
                     z0: float, z1: float) -> trimesh.Trimesh:
        """Silindirik delikli yakıt grain'i — halka profil revolve (m)."""
        r_port = min(max(r_port, 1e-4), r_outer - 5e-4)
        profile = np.array([
            [r_port, z0],
            [r_outer, z0],
            [r_outer, z1],
            [r_port, z1],
            [r_port, z0],
        ])
        return self._fix_solid(trimesh.creation.revolve(profile))

    def _create_combustion_chamber(self, diameter: float, length: float) -> trimesh.Trimesh:
        """Create combustion chamber geometry"""
        try:
            # Validate inputs
            if diameter <= 0 or length <= 0:
                raise ValueError(f"Invalid chamber dimensions: diameter={diameter}, length={length}")

            # Create outer cylinder
            outer_radius = diameter / 2
            inner_radius = max(outer_radius - 0.005, outer_radius * 0.8)  # 5mm wall thickness or 20% of radius

            # Create cylinder with hole
            outer_cylinder = trimesh.creation.cylinder(radius=outer_radius, height=length)
            inner_cylinder = trimesh.creation.cylinder(radius=inner_radius, height=length + 0.01)

            # Boolean difference for hollow chamber
            chamber = outer_cylinder.difference(inner_cylinder)

            return chamber
        except Exception as e:
            print(f"Chamber creation error: {str(e)}")
            # Return simple cylinder as fallback
            return trimesh.creation.cylinder(radius=diameter/2, height=length)

    def _create_nozzle(self, throat_diameter: float, exit_diameter: float, length: float, motor_data: Dict = {}) -> trimesh.Trimesh:
        """Create convergent-divergent nozzle geometry"""
        try:
            # Validate inputs
            if throat_diameter <= 0 or exit_diameter <= 0 or length <= 0:
                raise ValueError(f"Invalid nozzle dimensions: throat={throat_diameter}, exit={exit_diameter}, length={length}")

            # Calculate nozzle profile
            throat_radius = throat_diameter / 2
            exit_radius = exit_diameter / 2

            # Create convergent section - use motor data angles
            conv_length = length * 0.3
            conv_angle_deg = motor_data.get('convergent_angle', 15.0)  # degrees
            conv_angle = np.radians(conv_angle_deg)
            conv_inlet_radius = throat_radius + conv_length * np.tan(conv_angle)

            # Create divergent section - use motor data angles
            div_length = length * 0.7
            div_angle_deg = motor_data.get('divergent_angle', 12.0)  # degrees
            div_angle = np.radians(div_angle_deg)

            # Generate profile points
            z_points = np.linspace(0, length, 50)
            r_points = []

            for z in z_points:
                if z <= conv_length:
                    # Convergent section
                    r = conv_inlet_radius - (conv_inlet_radius - throat_radius) * (z / conv_length)
                else:
                    # Divergent section
                    z_div = z - conv_length
                    r = throat_radius + (exit_radius - throat_radius) * (z_div / div_length)
                r_points.append(r)

            # Create revolution surface
            profile_2d = np.column_stack([r_points, z_points])
            nozzle = trimesh.creation.revolve(profile_2d, angle=2*np.pi)

            return nozzle

        except Exception as e:
            print(f"Nozzle creation error: {str(e)}")
            # Return simple cone as fallback
            return trimesh.creation.cone(radius=exit_diameter/2, height=length)

    def _create_injector_head(self, chamber_diameter: float, motor_data: Dict) -> trimesh.Trimesh:
        """Create injector head with orifices"""
        try:
            radius = chamber_diameter / 2
            thickness = 0.03  # 30mm thick

            # Main injector plate
            injector_plate = trimesh.creation.cylinder(radius=radius, height=thickness)

            # Create injection orifices
            # v2.6.26: sayı/çap ÇÖZÜCÜDEN gelir. Gelmiyorsa DELİK AÇILMAZ —
            # eski 8 delik x 3 mm varsayılanı çizilmiş bir tasarım gibi
            # görünüyordu ama hiçbir hesaptan çıkmıyordu (uydurma geometri).
            orifice_count = int(motor_data.get('injector_orifices') or 0)
            orifice_diameter = _real_scalar(motor_data.get('orifice_diameter')) or 0.0
            if orifice_count <= 0 or orifice_diameter <= 0:
                return injector_plate

            # Arrange orifices in circle
            orifice_radius = radius * 0.7
            for i in range(orifice_count):
                angle = 2 * np.pi * i / orifice_count
                x = orifice_radius * np.cos(angle)
                y = orifice_radius * np.sin(angle)

                # Create orifice hole
                orifice = trimesh.creation.cylinder(
                    radius=orifice_diameter/2,
                    height=thickness + 0.001
                )
                orifice.apply_translation([x, y, -0.0005])
                injector_plate = injector_plate.difference(orifice)

            return injector_plate

        except Exception as e:
            print(f"Injector creation error: {str(e)}")
            # Return simple plate as fallback
            return trimesh.creation.cylinder(radius=chamber_diameter/2, height=0.03)

    def _create_fuel_grain(self, chamber_diameter: float, chamber_length: float, motor_data: Dict) -> trimesh.Trimesh:
        """Create fuel grain geometry with port"""
        try:
            outer_radius = chamber_diameter / 2 - 0.01  # 10mm clearance
            port_diameter = motor_data.get('port_diameter', chamber_diameter * 0.3)
            port_radius = port_diameter / 2

            # Fuel grain length (slightly shorter than chamber)
            grain_length = chamber_length - 0.05

            # Create outer cylinder
            outer_grain = trimesh.creation.cylinder(radius=outer_radius, height=grain_length)

            # Create port hole
            port_hole = trimesh.creation.cylinder(radius=port_radius, height=grain_length + 0.01)

            # Boolean difference
            fuel_grain = outer_grain.difference(port_hole)

            # Position in chamber
            fuel_grain.apply_translation([0, 0, 0.025])

            return fuel_grain

        except Exception as e:
            print(f"Fuel grain creation error: {str(e)}")
            # Return simple cylinder as fallback
            return trimesh.creation.cylinder(radius=chamber_diameter/4, height=chamber_length)

    def _create_plotly_visualization(self, assembly_meshes: List, motor_data: Dict) -> str:
        """Create interactive 3D visualization with Plotly"""
        try:
            fig = make_subplots(
                rows=2, cols=2,
                specs=[[{"type": "scene", "colspan": 2}, None],
                       [{"type": "xy"}, {"type": "xy"}]],
                subplot_titles=("3D Motor Assembly", "Cross-Section View", "Performance Chart"),
                vertical_spacing=0.1
            )

            # 3D Assembly view
            colors = ['lightblue', 'darkgray', 'silver', 'brown']
            mesh_added = False

            for i, (name, mesh) in enumerate(assembly_meshes):
                try:
                    if mesh is not None and hasattr(mesh, 'vertices') and hasattr(mesh, 'faces'):
                        vertices = mesh.vertices
                        faces = mesh.faces

                        if len(vertices) > 0 and len(faces) > 0:
                            # BDATA DUZELTMESI (v2.5.2): plotly 6.x numpy
                            # dizilerini fig.to_json()'da ikili (base64
                            # 'bdata') olarak yaziyor; gomulu plotly.js
                            # 1.58.5 bu bicimi cozemez ve 3D gorunum BOS
                            # kalir. Listeye cevirerek duz JSON uretiyoruz.
                            fig.add_trace(
                                go.Mesh3d(
                                    x=vertices[:, 0].tolist(),
                                    y=vertices[:, 1].tolist(),
                                    z=vertices[:, 2].tolist(),
                                    i=faces[:, 0].tolist(),
                                    j=faces[:, 1].tolist(),
                                    k=faces[:, 2].tolist(),
                                    color=colors[i % len(colors)],
                                    opacity=0.7,
                                    name=name
                                ),
                                row=1, col=1
                            )
                            mesh_added = True
                        else:
                            print(f"Warning: Empty mesh for {name}")
                    else:
                        print(f"Warning: Invalid mesh object for {name}")
                except Exception as mesh_error:
                    print(f"Error processing mesh {name}: {str(mesh_error)}")
                    continue

            # If no meshes were added, create a simple fallback representation
            if not mesh_added:
                print("No valid meshes found, creating fallback visualization")
                self._add_fallback_3d_motor(fig, motor_data, row=1, col=1)

            # Cross-section view
            self._add_cross_section_view(fig, motor_data, row=2, col=1)

            # Performance chart
            self._add_performance_chart(fig, motor_data, row=2, col=2)

            # Update layout
            fig.update_layout(
                title="UZAYTEK Hybrid Rocket Motor - 3D CAD Design",
                scene=dict(
                    xaxis_title="X (m)",
                    yaxis_title="Y (m)",
                    zaxis_title="Z (m)",
                    aspectmode='data'
                ),
                height=800,
                showlegend=True
            )

            return fig.to_json()

        except Exception as e:
            print(f"Plotly visualization error: {str(e)}")
            import traceback
            traceback.print_exc()
            # Return simple plot data as fallback
            return self._create_fallback_visualization(motor_data)

    def _add_fallback_3d_motor(self, fig, motor_data: Dict, row: int, col: int):
        """Add simple 3D motor representation when meshes fail"""
        try:
            # Get motor dimensions
            chamber_diameter = motor_data.get('chamber_diameter', 0.1)
            chamber_length = motor_data.get('chamber_length', 0.5)
            throat_diameter = motor_data.get('throat_diameter', 0.02)
            exit_diameter = motor_data.get('exit_diameter', 0.04)
            nozzle_length = motor_data.get('nozzle_length', 0.15)

            # Create simple cylindrical chamber
            theta = np.linspace(0, 2*np.pi, 20)
            z_chamber = np.linspace(0, chamber_length, 10)

            # Chamber surface
            theta_mesh, z_mesh = np.meshgrid(theta, z_chamber)
            x_chamber = (chamber_diameter/2) * np.cos(theta_mesh)
            y_chamber = (chamber_diameter/2) * np.sin(theta_mesh)

            fig.add_trace(
                go.Surface(
                    x=x_chamber,
                    y=y_chamber,
                    z=z_mesh,
                    colorscale='Greys',
                    opacity=0.7,
                    name='Chamber',
                    showscale=False
                ),
                row=row, col=col
            )

            # Simple nozzle cone
            z_nozzle = np.linspace(chamber_length, chamber_length + nozzle_length, 10)
            r_nozzle = np.linspace(throat_diameter/2, exit_diameter/2, 10)

            theta_noz, z_noz = np.meshgrid(theta, z_nozzle)
            r_noz_mesh = np.array([r_nozzle]).T
            x_nozzle = r_noz_mesh * np.cos(theta_noz)
            y_nozzle = r_noz_mesh * np.sin(theta_noz)

            fig.add_trace(
                go.Surface(
                    x=x_nozzle,
                    y=y_nozzle,
                    z=z_noz,
                    colorscale='Blues',
                    opacity=0.8,
                    name='Nozzle',
                    showscale=False
                ),
                row=row, col=col
            )

        except Exception as e:
            print(f"Error creating fallback 3D motor: {str(e)}")
            # Add basic scatter points as last resort
            fig.add_trace(
                go.Scatter3d(
                    x=[0, 0.1, 0.1, 0],
                    y=[0, 0, 0.05, 0.05],
                    z=[0, 0, 0.1, 0.1],
                    mode='markers+lines',
                    name='Motor Outline'
                ),
                row=row, col=col
            )

    def _create_fallback_visualization(self, motor_data: Dict) -> str:
        """Create fallback visualization when main function fails"""
        try:
            fig = go.Figure()

            # Simple 3D representation
            chamber_diameter = motor_data.get('chamber_diameter', 0.1)
            chamber_length = motor_data.get('chamber_length', 0.5)

            # Chamber outline
            fig.add_trace(go.Scatter3d(
                x=[0, chamber_length, chamber_length, 0, 0],
                y=[0, 0, 0, 0, 0],
                z=[chamber_diameter/2, chamber_diameter/2, -chamber_diameter/2, -chamber_diameter/2, chamber_diameter/2],
                mode='lines',
                name='Chamber Outline',
                line=dict(color='blue', width=4)
            ))

            # Nozzle outline
            nozzle_length = motor_data.get('nozzle_length', 0.15)
            exit_diameter = motor_data.get('exit_diameter', 0.04)

            fig.add_trace(go.Scatter3d(
                x=[chamber_length, chamber_length + nozzle_length],
                y=[0, 0],
                z=[chamber_diameter/2, exit_diameter/2],
                mode='lines',
                name='Nozzle Top',
                line=dict(color='red', width=3)
            ))

            fig.add_trace(go.Scatter3d(
                x=[chamber_length, chamber_length + nozzle_length],
                y=[0, 0],
                z=[-chamber_diameter/2, -exit_diameter/2],
                mode='lines',
                name='Nozzle Bottom',
                line=dict(color='red', width=3)
            ))

            fig.update_layout(
                title="UZAYTEK Hybrid Rocket Motor - Simplified View",
                scene=dict(
                    xaxis_title="Length (m)",
                    yaxis_title="Y (m)",
                    zaxis_title="Radius (m)",
                    aspectmode='data'
                ),
                height=600,
                showlegend=True
            )

            return fig.to_json()

        except Exception as e:
            print(f"Fallback visualization error: {str(e)}")
            # Absolute minimum fallback
            simple_fig = go.Figure()
            simple_fig.add_trace(go.Scatter3d(
                x=[0, 0.5, 0.5, 0],
                y=[0, 0, 0, 0],
                z=[0, 0, 0.1, 0.1],
                mode='markers+lines',
                name='Basic Motor Shape'
            ))
            simple_fig.update_layout(title="Motor Visualization (Simplified)")
            return simple_fig.to_json()

    def _add_cross_section_view(self, fig, motor_data: Dict, row: int, col: int):
        """2D kesit — geometri ve açılar ÇÖZÜCÜNÜN kendi çıktısından.

        Eski sürüm açıları `motor_data.get('convergent_angle', 15.0)` /
        `('divergent_angle', 12.0)` ile okuyordu; bu anahtarlar motor
        sonucunda HİÇ YOK, dolayısıyla her motor için 15°/12° çiziliyor ve
        lejantta öyle etiketleniyordu (2026-07-19 denetimi). Gerçek değerler
        `nozzle_angles` / `nozzle_contour.divergent` altında. Ayrıca kontur
        artık sample_nozzle_inner_contour ile çizilir — 2D kesit, 3D CAD ve
        DXF ile TEK kaynak (bell lüle artık düz koni gibi görünmez).
        """

        chamber_diameter = motor_data.get('chamber_diameter', 0.1)
        chamber_length = motor_data.get('chamber_length', 0.5)
        throat_diameter = motor_data.get('throat_diameter', 0.02)
        exit_diameter = motor_data.get('exit_diameter', 0.04)

        conv_deg, div_deg, angle_type = _nozzle_half_angles(motor_data)

        chamber_top = chamber_diameter / 2
        chamber_bottom = -chamber_diameter / 2
        nozzle_start = chamber_length

        # Gerçek iç kontur (mm -> m); z=0 kamara çıkışı
        pts_mm, meta = sample_nozzle_inner_contour(motor_data)
        noz_x = [nozzle_start + z / 1000.0 for z, _r in pts_mm]
        noz_r = [r / 1000.0 for _z, r in pts_mm]
        throat_pos = nozzle_start + meta['z_throat'] / 1000.0
        throat_r = meta['r_throat'] / 1000.0
        nozzle_end = nozzle_start + meta['z_exit'] / 1000.0

        # Draw chamber
        fig.add_trace(
            go.Scatter(
                x=[0, chamber_length, chamber_length, 0, 0],
                y=[chamber_top, chamber_top, chamber_bottom, chamber_bottom, chamber_top],
                mode='lines',
                name='Chamber',
                line=dict(color='blue', width=2)
            ),
            row=row, col=col
        )

        # Draw nozzle profile from the solver contour
        fig.add_trace(
            go.Scatter(
                x=noz_x + noz_x[::-1],
                y=noz_r + [-r for r in noz_r[::-1]],
                fill='toself',
                name=f'Nozzle ({meta.get("noz_type", "conical")})',
                fillcolor='rgba(128,128,128,0.3)',
                line=dict(color='gray')
            ),
            row=row, col=col
        )

        # Add throat line indicator
        fig.add_trace(
            go.Scatter(
                x=[throat_pos, throat_pos],
                y=[-throat_r, throat_r],
                mode='lines',
                name='Throat',
                line=dict(color='red', width=3, dash='dash')
            ),
            row=row, col=col
        )

        annotations = []
        angle_length = 0.03  # açı göstergesi çizgi boyu [m]

        # Açı göstergeleri YALNIZ gerçek açı varsa çizilir/etiketlenir.
        if conv_deg is not None:
            conv_angle_rad = np.radians(conv_deg)
            conv_mid_x = nozzle_start + (throat_pos - nozzle_start) * 0.5
            conv_mid_r = chamber_top - (chamber_top - throat_r) * 0.5
            conv_end_x = conv_mid_x + angle_length * np.cos(np.pi - conv_angle_rad)
            conv_end_y = conv_mid_r + angle_length * np.sin(np.pi - conv_angle_rad)
            fig.add_trace(
                go.Scatter(
                    x=[conv_mid_x, conv_end_x],
                    y=[conv_mid_r, conv_end_y],
                    mode='lines',
                    name=f'Conv. {conv_deg:.1f}°',
                    line=dict(color='orange', width=2, dash='dot')
                ),
                row=row, col=col
            )
            annotations.append(dict(
                x=conv_end_x, y=conv_end_y,
                text=f'{conv_deg:.1f}°',
                showarrow=False,
                font=dict(size=9, color='orange')
            ))

        if div_deg is not None:
            div_angle_rad = np.radians(div_deg)
            div_mid_x = throat_pos + (nozzle_end - throat_pos) * 0.5
            div_mid_r = throat_r + (div_mid_x - throat_pos) * np.tan(div_angle_rad)
            div_end_x = div_mid_x + angle_length * np.cos(div_angle_rad)
            div_end_y = div_mid_r + angle_length * np.sin(div_angle_rad)
            div_label = ('Div. throat %.1f°' % div_deg if angle_type == 'bell'
                         else 'Div. %.1f°' % div_deg)
            fig.add_trace(
                go.Scatter(
                    x=[div_mid_x, div_end_x],
                    y=[div_mid_r, div_end_y],
                    mode='lines',
                    name=div_label,
                    line=dict(color='green', width=2, dash='dot')
                ),
                row=row, col=col
            )
            annotations.append(dict(
                x=div_end_x, y=div_end_y,
                text=f'{div_deg:.1f}°',
                showarrow=False,
                font=dict(size=9, color='green')
            ))

        # Chamber diameter annotation
        annotations.append(dict(
            x=-chamber_length * 0.1,
            y=0,
            text=f'D = {chamber_diameter*1000:.1f} mm',
            showarrow=False,
            font=dict(size=10),
            textangle=90
        ))

        # Throat diameter annotation
        annotations.append(dict(
            x=throat_pos,
            y=-throat_r - chamber_diameter * 0.15,
            text=f'dt = {throat_diameter*1000:.2f} mm',
            showarrow=False,
            font=dict(size=10)
        ))

        # Exit diameter annotation
        annotations.append(dict(
            x=nozzle_end,
            y=-exit_diameter/2 - chamber_diameter * 0.15,
            text=f'de = {exit_diameter*1000:.1f} mm',
            showarrow=False,
            font=dict(size=10)
        ))

        # Expansion ratio: çözücünün değeri varsa o, yoksa geometriden
        expansion_ratio = _real_scalar(motor_data.get('expansion_ratio'))
        if expansion_ratio is None:
            expansion_ratio = (exit_diameter / throat_diameter) ** 2
        annotations.append(dict(
            x=(throat_pos + nozzle_end) / 2,
            y=chamber_diameter * 0.3,
            text=f'ε = {expansion_ratio:.1f}',
            showarrow=False,
            font=dict(size=10, color='purple')
        ))

        fig.update_xaxes(title_text="Length (m)", row=row, col=col)
        fig.update_yaxes(title_text="Radius (m)", row=row, col=col)

        # Add annotations to the layout (they'll apply to the subplot)
        if hasattr(fig, 'add_annotation'):
            for ann in annotations:
                fig.add_annotation(ann, row=row, col=col)

    def _add_performance_chart(self, fig, motor_data: Dict, row: int, col: int):
        """Add performance characteristics chart.

        DUZELTME (v2.5.2): eski surum burada UYDURMA bir egri ciziyordu
        (sabit itkiye %10'luk dogrusal dusus ekleyip 'realistic thrust curve
        variation' diye etiketliyordu). Teknik cizim ciktisinda hesaplanmamis
        bir egriyi hesaplanmis gibi gostermek yanilticidir. Artik once GERCEK
        egri aranir (transient / thrust_curve / port_history); yoksa sabit
        tasarim itkisi cizilir ve etikette bunun bir VARSAYIM oldugu yazar.

        Ayrica diziler listeye cevrilir: plotly 6.x numpy'i ikili (bdata)
        yaziyor, gomulu plotly.js 1.58.5 cozemiyor ve egri BOS kaliyordu.
        """
        time_s, thrust_n, label = None, None, None

        transient = motor_data.get('transient') or {}
        curve = motor_data.get('thrust_curve') or {}
        if transient.get('time') and transient.get('thrust'):
            time_s = list(transient['time'])
            thrust_n = list(transient['thrust'])
            label = 'Thrust (computed transient)'
        elif curve.get('time') and curve.get('thrust'):
            time_s = list(curve['time'])
            thrust_n = list(curve['thrust'])
            label = 'Thrust (computed curve)'
        else:
            burn_time = float(motor_data.get('burn_time', 10) or 10)
            design_thrust = float(motor_data.get('thrust', 1000) or 1000)
            time_s = [0.0, burn_time]
            thrust_n = [design_thrust, design_thrust]
            label = 'Thrust (design point, constant-thrust assumption)'

        fig.add_trace(
            go.Scatter(
                x=[float(v) for v in time_s],
                y=[float(v) for v in thrust_n],
                mode='lines',
                name=label,
                line=dict(color='red', width=2)
            ),
            row=row, col=col
        )

        fig.update_xaxes(title_text="Time (s)", row=row, col=col)
        fig.update_yaxes(title_text="Thrust (N)", row=row, col=col)

    def _generate_technical_drawings(self, motor_data: Dict) -> Dict:
        """İmalat spesifikasyonu — ÇÖZÜCÜNÜN kendi sonuçlarından.

        Eski sürümde cidar kalınlığı sabit 5.0 mm, enjektör plakası 30 mm ve
        malzemeler ('Steel 304' / 'Graphite' / 'Stainless Steel 316') motor
        sonucundan bağımsızdı; 20 kN'lik bir motorda yapısal analiz 29 mm cidar
        isterken çizim 5 mm yazıyordu (2026-07-19 denetimi). Artık:
          - cidar kalınlığı: structural_analysis.chamber_analysis
          - enjektör plakası: structural_analysis.end_cap_analysis (düz kapak)
          - malzeme: yapısal analizde seçilen materials_db kaydı
          - lüle açıları: nozzle_angles / nozzle_contour
        Değer yoksa sabit sayı yazılmaz; alan NOT_AVAILABLE_SPEC olur.
        Tolerans ve yüzey pürüzlülüğü tasarım kararı DEĞİLDİR; standart
        değerler 'basis' alanında kaynağıyla etiketlenir.
        """

        drawings = {}

        wall_design = _chamber_wall_design(motor_data)
        wall_m = wall_design['thickness_m']
        wall_source = wall_design['source']
        _mat_key, mat_name, _rho = _chamber_material(motor_data)
        conv_deg, div_deg, noz_type = _nozzle_half_angles(motor_data)
        inj = _injector_spec(motor_data)

        struct = motor_data.get('structural_analysis') or {}
        plate_mm = _real_nested(struct, ('end_cap_analysis', 'flat_head_thickness'))

        # Chamber drawing
        # v2.6.26 (Y3): 'outer_diameter' aslında İÇ (kamara) çapını yazıyordu,
        # hemen yanında ayrı bir 'wall_thickness' alanı varken. Ölçüldü: katı
        # modelin mesh köşelerinden okunan gerçek dış çap 184,37 mm iken ölçü
        # tablosu 152,53 mm diyordu (152,53 + 2 x 15,92 = 184,37). Atölye
        # Ø152 mm boru alıp 15,92 mm cidar bırakacak şekilde tornalasa kalan
        # delik 120,7 mm olurdu; grain'in dış çapı 146,4 mm — parça takılmaz.
        # Artık iç ve dış çap AYRI ve ikisi de katı modelin gerçeğiyle tutar.
        bore_mm = _real_scalar(motor_data.get('chamber_diameter'))
        bore_mm = bore_mm * 1000.0 if bore_mm is not None else None
        outer_mm = ((bore_mm + 2.0 * wall_m * 1000.0)
                    if (bore_mm is not None and wall_m) else None)
        length_m = _real_scalar(motor_data.get('chamber_length'))
        length_mm = length_m * 1000.0 if length_m is not None else None
        drawings['chamber'] = {
            # Kamara İÇ çapı (yanma hacmi / grain dış çapı bu ölçüye oturur)
            'inner_diameter': bore_mm if bore_mm is not None else NOT_AVAILABLE_SPEC,
            # Boru dış çapı = iç çap + 2 x cidar (katı modelle birebir aynı)
            'outer_diameter': outer_mm if outer_mm is not None else NOT_AVAILABLE_SPEC,
            'diameter_convention': ('inner_diameter is the chamber bore; '
                                    'outer_diameter = inner_diameter + 2 x '
                                    'wall_thickness and matches the CAD solid'),
            'wall_thickness': (wall_m * 1000.0) if wall_m else NOT_AVAILABLE_SPEC,
            'wall_thickness_source': wall_source,
            # Hangi kalınlık çizildi, yapısal analiz ne öneriyor, ekrandaki
            # emniyet katsayısı hangisine ait — üçü de aynı satırda.
            'wall_thickness_as_designed': (wall_design['as_designed_mm']
                                           if wall_design['as_designed_mm'] is not None
                                           else NOT_AVAILABLE_SPEC),
            'wall_thickness_recommended': (wall_design['recommended_mm']
                                           if wall_design['recommended_mm'] is not None
                                           else NOT_AVAILABLE_SPEC),
            'wall_thickness_note': wall_design['note'],
            'safety_factor_at_drawn_wall': (wall_design['safety_factor']
                                            if wall_design['safety_factor'] is not None
                                            else NOT_AVAILABLE_SPEC),
            'length': (length_m * 1000.0) if length_m is not None else NOT_AVAILABLE_SPEC,
            'material': mat_name or NOT_AVAILABLE_SPEC,
            'surface_finish': DRAWING_SURFACE_FINISH_CHAMBER,
            'finish_basis': DRAWING_SURFACE_FINISH_BASIS,
            # v2.6.26 (P4): tolerans artık ÖLÇÜNÜN KENDİSİNDEN aranır.
            # Öncesi: sabit '+-0.1 mm' çap ve '+-0.5 mm' boy — hem motorun
            # boyutundan bağımsızdı, hem de hemen yanındaki 'basis' alanı
            # "ISO 2768-m" diyordu ama o standardın tablosu ölçüyle DEĞİŞİR
            # (Ø100 mm için m sınıfı ±0.3 mm, f sınıfı ±0.15 mm). Yani
            # sayılar kaynağa uymuyordu: yanlış künye.
            'tolerances': _iso2768_tolerance_block(bore_mm, outer_mm,
                                                   length_mm),
        }

        # Nozzle drawing
        # Boy: `or 0.0` zinciri yerine açık koşul — geçersiz boy 0 mm olarak
        # yazılmaz (aynı hata geometri özetinde gerçekten 0 mm üretiyordu).
        nozzle_len_m = _nozzle_length_m(motor_data)
        drawings['nozzle'] = {
            'throat_diameter': motor_data.get('throat_diameter', 0.02) * 1000,  # mm
            'exit_diameter': motor_data.get('exit_diameter', 0.04) * 1000,  # mm
            'length': ((nozzle_len_m * 1000.0) if nozzle_len_m is not None
                       else NOT_AVAILABLE_SPEC),  # mm
            'nozzle_type': noz_type,
            'convergence_angle': conv_deg if conv_deg is not None else NOT_AVAILABLE_SPEC,
            'divergence_angle': div_deg if div_deg is not None else NOT_AVAILABLE_SPEC,
            'divergence_angle_meaning': ('bell: throat exit angle (theta_n); the '
                                         'wall angle decreases toward the exit'
                                         if noz_type == 'bell'
                                         else 'conical: constant half angle'),
            'divergent_exit_angle': (
                _real_scalar(((motor_data.get('nozzle_contour') or {})
                              .get('divergent') or {}).get('exit_angle'))
                or NOT_AVAILABLE_SPEC),
            'angle_source': 'solver nozzle_angles / nozzle_contour',
            'material': (motor_data.get('nozzle_material')
                         or motor_data.get('throat_material')
                         or NOT_AVAILABLE_SPEC),
            'surface_finish': DRAWING_SURFACE_FINISH_NOZZLE,
            'finish_basis': DRAWING_SURFACE_FINISH_BASIS
        }

        # Injector drawing
        drawings['injector'] = {
            'plate_diameter': (inj['plate_diameter_mm']
                               if inj['plate_diameter_mm'] else NOT_AVAILABLE_SPEC),
            'plate_thickness': plate_mm if plate_mm else NOT_AVAILABLE_SPEC,
            'plate_thickness_source': ('structural analysis (flat closure head '
                                       'at chamber pressure)' if plate_mm
                                       else 'not available'),
            'orifice_count': inj['n_orifices'] or NOT_AVAILABLE_SPEC,
            'orifice_diameter': inj['orifice_diameter_mm'] or NOT_AVAILABLE_SPEC,
            'injector_type': inj['type'] or NOT_AVAILABLE_SPEC,
            'orifice_source': inj['source'],
            'material': motor_data.get('injector_material') or NOT_AVAILABLE_SPEC,
            'surface_finish': DRAWING_SURFACE_FINISH_INJECTOR,
            'finish_basis': DRAWING_SURFACE_FINISH_BASIS
        }

        return drawings

    def _generate_material_specifications(self, motor_data: Dict) -> Dict:
        """Malzeme spesifikasyonları — kamara kaydı materials_db'den (gerçek).

        Kamara malzemesi yapısal analizde SEÇİLEN kayıttır; özellikleri merkezi
        materials_db'den okunur (eski sürüm kullanıcı ne seçerse seçsin
        'AISI 304' basıyordu). Lüle/enjektör için motor sonucunda malzeme
        seçimi yoksa satır 'reference design' olarak etiketlenir.
        """

        mat_key, mat_name, _rho = _chamber_material(motor_data)
        chamber_spec = None
        if mat_key:
            try:
                rec = get_material(str(mat_key))
                chamber_spec = {
                    'designation': rec.get('name', mat_name),
                    'properties': {
                        'tensile_strength': f"{rec['ultimate_strength'] / 1e6:.0f} MPa",
                        'yield_strength': f"{rec['yield_strength'] / 1e6:.0f} MPa",
                        'density': f"{rec['density'] / 1000.0:.2f} g/cm3",
                        'melting_point': f"{rec.get('melting_point', 'n/a')} K",
                        'thermal_conductivity': f"{rec.get('thermal_conductivity', 'n/a')} W/m K"
                    },
                    'source': rec.get('source', 'hrma materials_db'),
                    'selected_by': 'structural analysis material selection'
                }
            except Exception:
                chamber_spec = None

        specs = {
            'chamber_material': chamber_spec or {
                'designation': NOT_AVAILABLE_SPEC,
                'properties': {},
                'source': 'no material selected in this analysis run'
            },
            # Lüle ve enjektör malzemesi bu analiz koşusunda SEÇİLMİYOR; aşağıdaki
            # kayıtlar merkezi materials_db'den okunan REFERANS tasarımlardır ve
            # 'basis' alanıyla böyle etiketlenir (kullanıcı seçimi değildir).
            'nozzle_material': self._reference_material_spec(
                motor_data.get('nozzle_material') or motor_data.get('throat_material'),
                'graphite'),
            'injector_material': self._reference_material_spec(
                motor_data.get('injector_material'), 'ss_316')
        }

        return specs

    @staticmethod
    def _reference_material_spec(selected_key, default_key) -> Dict:
        """materials_db kaydından spesifikasyon; seçim yoksa referans etiketi."""
        key = selected_key or default_key
        try:
            rec = get_material(str(key))
        except Exception:
            return {'designation': NOT_AVAILABLE_SPEC, 'properties': {},
                    'basis': 'material not found in materials_db'}
        return {
            'designation': rec.get('name', str(key)),
            'properties': {
                'tensile_strength': f"{rec['ultimate_strength'] / 1e6:.0f} MPa",
                'yield_strength': f"{rec['yield_strength'] / 1e6:.0f} MPa",
                'density': f"{rec['density'] / 1000.0:.2f} g/cm3",
                'melting_point': f"{rec.get('melting_point', 'n/a')} K",
                'thermal_conductivity': f"{rec.get('thermal_conductivity', 'n/a')} W/m K"
            },
            'source': rec.get('source', 'hrma materials_db'),
            'basis': ('selected in this analysis run' if selected_key
                      else 'reference design - not selected in this analysis run')
        }

    def _generate_manufacturing_notes(self, motor_data: Dict) -> List[str]:
        """İmalat notları — ölçülü adımlar ÇÖZÜCÜNÜN kendi sonuçlarından.

        Eski sürüm motor_data'yı hiç okumuyordu: 500 N'lik motorla 50 kN'lik
        motorun notları birebir aynı çıkıyordu ("bore to final ID",
        "graphite blank", "1.5x operating pressure"). Komşu fonksiyonlar
        (_generate_technical_drawings, _generate_material_specifications)
        2026-07-19 denetiminde çözücüye bağlanmıştı, bu fonksiyon atlanmıştı.

        Artık gerçek sayı taşıyan adımlar:
          - kamara: gerçek iç çap + yapısal analizin cidar kalınlığı/malzemesi
          - lüle: gerçek boğaz çapı, seçilmişse gerçek lüle malzemesi
          - enjektör: _injector_spec'in delik sayısı/çapı (tek doğruluk kaynağı)
          - basınç testi: gerçek kamara basıncı + yapısal tasarım basıncı
        Değer yoksa sabit sayı yazılmaz, alan NOT_AVAILABLE_SPEC olur. Sayı
        üretilemeyen adımlar bu motora özel hesaplanmaz; sondaki BASIS bloğu
        bunu açıkça söyler (manufacturing_complexity ile aynı desen).
        """

        md = motor_data or {}
        struct = md.get('structural_analysis') or {}

        def _mm(value):
            metres = _real_scalar(value)
            return metres * 1000.0 if metres is not None else None

        chamber_id_mm = _mm(md.get('chamber_diameter'))
        wall_design = _chamber_wall_design(md)
        wall_m = wall_design['thickness_m']
        wall_source = wall_design['source']
        wall_mm = wall_m * 1000.0 if wall_m is not None else None
        _mat_key, chamber_mat, _rho = _chamber_material(md)
        throat_mm = _mm(md.get('throat_diameter'))
        nozzle_mat = md.get('nozzle_material') or md.get('throat_material')
        inj = _injector_spec(md)
        pc_bar = _real_scalar(md.get('chamber_pressure'))
        design_p_bar = _real_nested(struct, ('design_parameters', 'design_pressure'))
        design_factor = _real_nested(struct,
                                     ('design_parameters', 'design_pressure_factor'))

        # 1 - kamara: iç çap ve cidar yapısal analizden gelir
        if chamber_id_mm is not None:
            chamber_note = (
                f"1. Chamber: machine from "
                f"{chamber_mat or 'the chamber material selected in this run'} "
                f"stock; bore to {chamber_id_mm:.1f} mm ID")
            chamber_note += (f", leave {wall_mm:.1f} mm wall ({wall_source})"
                             if wall_mm is not None
                             else f"; wall thickness {NOT_AVAILABLE_SPEC}")
            # v2.6.26 (Y5): tezgâha giden not, çizilen cidar ile yapısal
            # önerinin AYNI OLMADIĞINI söylemeden geçemez. Torna başındaki
            # kişi hangi kalınlığın hangi emniyet katsayısına ait olduğunu
            # görmeden talaş kaldırmamalı.
            if wall_design['note']:
                chamber_note += f". NOTE: {wall_design['note']}"
        else:
            chamber_note = f"1. Chamber: bore diameter {NOT_AVAILABLE_SPEC}"

        # 2 - lüle: boğaz çapı çözücüden; malzeme yalnız SEÇİLDİYSE yazılır
        nozzle_note = (
            f"2. Nozzle: CNC machine from "
            f"{nozzle_mat or 'the nozzle blank material (not selected in this run)'}")
        nozzle_note += (f"; finish throat to {throat_mm:.2f} mm diameter"
                        if throat_mm is not None
                        else f"; throat diameter {NOT_AVAILABLE_SPEC}")
        nozzle_note += f"; throat finish target {DRAWING_SURFACE_FINISH_NOZZLE}"

        # 3 - enjektör: çizim/CAD ile AYNI kaynaktan (bkz. _injector_spec)
        if inj['n_orifices'] and inj['orifice_diameter_mm']:
            injector_note = (
                f"3. Injector: drill {inj['n_orifices']} orifices at "
                f"{inj['orifice_diameter_mm']:.2f} mm diameter and deburr each one; "
                f"face finish target {DRAWING_SURFACE_FINISH_INJECTOR} "
                f"(source: {inj['source']})")
        else:
            injector_note = (f"3. Injector: orifice count and diameter "
                             f"{NOT_AVAILABLE_SPEC} (source: {inj['source']})")

        # 5 - basınç testi: "1.5x" UYDURMA DEĞİL, yapısal analizin kendi
        # tasarım basıncı yazılır. Test seviyesini seçmek bu yazılımın işi
        # değildir; yalnız hesaplanan basınçlar bildirilir.
        if pc_bar is not None and design_p_bar is not None:
            factor_txt = (f", factor {design_factor:.2f}"
                          if design_factor is not None else "")
            pressure_note = (
                f"5. Pressure test: operating pressure {pc_bar:.1f} bar; the wall "
                f"was sized to {design_p_bar:.1f} bar design pressure{factor_txt} "
                f"by the structural analysis. The proof/burst test level is set by "
                f"the applicable code, not by this analysis.")
        elif pc_bar is not None:
            pressure_note = (
                f"5. Pressure test: operating pressure {pc_bar:.1f} bar; no "
                f"structural design pressure in this run and no proof factor is "
                f"computed here.")
        else:
            pressure_note = f"5. Pressure test level: {NOT_AVAILABLE_SPEC}"

        notes = [
            "MANUFACTURING INSTRUCTIONS:",
            chamber_note,
            nozzle_note,
            injector_note,
            "4. Threads: ANSI B1.1 Class 2A/2B fit",
            pressure_note,
            "",
            "ASSEMBLY SEQUENCE:",
            "1. Install fuel grain in chamber",
            "2. Mount nozzle with high-temp sealant",
            "3. Attach injector with O-ring seal",
            "4. Connect propellant feed lines",
            "5. Perform leak test with nitrogen",
            "",
            "SAFETY REQUIREMENTS:",
            "- Welding per AWS D1.1",
            "- NDT inspection of pressure boundaries",
            "- Hydrostatic test before first firing",
            "- Maintain detailed test records",
            "",
            "BASIS:",
            f"- {MANUFACTURING_NOTE_BASIS}",
            f"- {MANUFACTURING_STANDARD_BASIS}",
            f"- surface finish targets: {DRAWING_SURFACE_FINISH_BASIS}",
        ]

        return notes

    def _generate_cad_performance_summary(self, motor_data: Dict) -> Dict:
        """CAD kütle/geometri özeti — kütleler GERÇEK kalınlık ve malzemeden."""

        nozzle_mass = self._estimate_component_mass('nozzle', motor_data)
        chamber_mass = self._estimate_component_mass('chamber', motor_data)
        injector_mass = self._estimate_component_mass('injector', motor_data)
        dry_mass = chamber_mass + nozzle_mass + injector_mass

        wall_design = _chamber_wall_design(motor_data)
        wall_m = wall_design['thickness_m']
        wall_source = wall_design['source']
        _key, mat_name, _rho = _chamber_material(motor_data)

        # Bileşenlerden biri geçersizse (eksik/NaN) toplam uzunluk 0 mm DEĞİL
        # None'dır. Eski `or 0.0` yedeği _real_scalar'ın None'ını yutuyor,
        # geçersiz kamara boyu geometri özetinde sessizce 0 mm katkı yapıyordu:
        # kullanıcı 56 mm'lik "toplam boy" görüp bunun hesaplandığını sanıyordu.
        # 'sıfır' ile 'hesaplanamadı' bu projede aynı şey değildir.
        chamber_len_m = _real_scalar(motor_data.get('chamber_length'))
        chamber_d_m = _real_scalar(motor_data.get('chamber_diameter'))
        thrust_n = _real_scalar(motor_data.get('thrust'))
        nozzle_len_m = _nozzle_length_m(motor_data)
        total_length_mm = ((chamber_len_m + nozzle_len_m) * 1000.0
                           if (chamber_len_m is not None and nozzle_len_m is not None)
                           else None)

        # Aynı kural geometri özetinin BÜTÜN alanları için geçerlidir. Eski
        # `motor_data.get('chamber_diameter', 0.1)` kalıbı iki ayrı yoldan
        # yanlış sonuç veriyordu: anahtar hiç yoksa 100 mm çaplı / 500 mm boylu
        # UYDURMA bir motorun hacmini hesaplanmış gibi basıyor, anahtar varken
        # değeri None ise (girdi doğrulamada elenen alanlar) çarpma TypeError
        # ile patlıyordu. Artık geçersiz girdide alan None kalır.
        chamber_volume_cm3 = (
            np.pi * (chamber_d_m / 2.0) ** 2 * chamber_len_m * 1e6
            if (chamber_d_m is not None and chamber_len_m is not None)
            else None)

        # v2.6.26 (Y3): 'max_diameter' kamaranın İÇ çapını yazıyordu. Bu alan
        # gövde tüpü / yük hattı seçimine giren ZARF çapıdır; iç çap yazmak
        # aracı cidar kalınlığının iki katı kadar küçük gösteriyordu (ölçülen
        # koşuda 152,53 mm yerine gerçek 184,37 mm). Zarf, 3B katının
        # KULLANDIĞI cidarla hesaplanır ki mesh ile çelişmesin; lüle çıkışı
        # kamaradan genişse (yüksek genişleme oranı) o kazanır.
        # Zarf KAMARADAN başlar: kamara çapı geçersizse zarf hesaplanamaz ve
        # alan None kalır. (Yalnız lüle çıkışına bakıp sayı üretmek, geçersiz
        # girdide "hesaplanmış" görünen bir çap basmak olurdu.)
        env_wall_m, env_wall_src = _chamber_wall_effective_m(motor_data, chamber_d_m)
        if chamber_d_m is None or env_wall_m is None:
            max_diameter_mm = None
        else:
            chamber_outer_mm = (chamber_d_m + 2.0 * env_wall_m) * 1000.0
            exit_d_m = _real_scalar(motor_data.get('exit_diameter'))
            noz_wall_m = _real_scalar((motor_data.get('nozzle_geometry') or {})
                                      .get('wall_thickness'))
            noz_wall_m = (noz_wall_m / 1000.0) if noz_wall_m is not None else None
            # Lülenin en geniş yeri ÇIKIŞ değil, çoğu tasarımda KONVERJAN
            # GİRİŞİdir (kamara çapında başlar). Yalnız çıkışa bakan eski
            # hesap, düşük genişleme oranlı motorlarda zarfı olduğundan küçük
            # gösteriyordu: ölçülen koşuda 162,53 mm yazıyordu, katının gerçek
            # zarfı 168,11 mm idi (lüle mesh'i kamaradan genişti). Kontur
            # örneklenebiliyorsa zarf ONDAN okunur — böylece sayı, çizilen
            # katıyla tanım gereği aynı olur.
            noz_max_r_m = None
            try:
                _pts_mm, _meta = sample_nozzle_inner_contour(motor_data)
                if _pts_mm:
                    noz_max_r_m = max(r for _z, r in _pts_mm) / 1000.0
            except Exception:
                noz_max_r_m = None
            if noz_max_r_m is None:
                _cands = [d for d in (exit_d_m, chamber_d_m) if d is not None]
                noz_max_r_m = (max(_cands) / 2.0) if _cands else None
            nozzle_outer_mm = ((noz_max_r_m + noz_wall_m) * 2.0 * 1000.0
                               if (noz_max_r_m is not None and noz_wall_m is not None)
                               else None)
            max_diameter_mm = max(v for v in (chamber_outer_mm, nozzle_outer_mm)
                                  if v is not None)

        return {
            'geometry_summary': {
                'total_length': total_length_mm,  # mm (None = hesaplanamadı)
                'max_diameter': max_diameter_mm,  # mm — ZARF (dış) çapı
                'max_diameter_basis': ('outer envelope: max(chamber bore + 2 x '
                                       'wall, nozzle exit + 2 x nozzle wall); '
                                       f'chamber wall from {env_wall_src}'),
                'chamber_bore_diameter': ((chamber_d_m * 1000.0)
                                          if chamber_d_m is not None else None),  # mm
                'chamber_volume': chamber_volume_cm3,  # cm3
                'thrust_to_weight': (thrust_n / (dry_mass * G_0)
                                     if (thrust_n is not None and dry_mass > 0)
                                     else None)
            },
            'mass_breakdown': {
                'chamber_mass': chamber_mass,  # kg
                'nozzle_mass': nozzle_mass,  # kg
                'injector_mass': injector_mass,  # kg
                'total_dry_mass': dry_mass,  # kg
                # H4-7: bu toplam motorun TAM kuru kütlesi DEĞİLDİR — kapaklar
                # (uç tıpalar) burada yok, yapısal analizin toplamında var.
                # Ölçüldü (2 kN hibrit): burası 13,7130 kg,
                # structural_analysis...total_weight 16,8366 kg (%22,8 fark) ve
                # ikisi de "kuru kütle" adıyla yayımlanıyordu. Kapsam artık
                # sayının yanında yazar; .eng dosyası da farkı beyan eder
                # (openrocket_integration.dry_mass_reconciliation).
                'total_dry_mass_scope': (
                    'chamber + as-drawn nozzle + injector plate. Closures / '
                    'end caps are NOT included here; the structural weight '
                    'analysis reports them and its total is what the .eng '
                    'export writes.'),
                # Lülenin OTORİTATİF kütlesi budur: çizilen katının kesik koni
                # halkası hacmi V = pi(2*t*r_ort + t^2)*L. Formül Faz 4'te Lean
                # ile ispatlandı (docs/BICIMSEL_ISPATLAR.md,
                # HRMA.frustumAnnulusVolume_eq_integral). Aynı sonuçtaki diğer
                # iki lüle kütlesi YAKLAŞIMDIR ve kaynağında öyle beyanlıdır:
                # structural %30 başparmak kuralı, nozzle_design yalnız
                # diverjan koni.
                'nozzle_mass_basis': (
                    'AUTHORITATIVE: as-drawn solid, frustum-annulus volume '
                    'V = pi(2*t*r_mid + t^2)*L with the same contour, wall and '
                    'material as the STEP/STL parts; formula formally verified '
                    '(docs/BICIMSEL_ISPATLAR.md). The rule-of-thumb nozzle '
                    'weight in structural_analysis and the divergent-cone-only '
                    'estimate in nozzle_design are approximations, not this.'),
                # Kütlelerin neye dayandığı kullanıcıya açıkça söylenir.
                'wall_thickness_mm': (wall_m * 1000.0) if wall_m else None,
                'wall_thickness_source': wall_source,
                'wall_thickness_recommended_mm': wall_design['recommended_mm'],
                'wall_thickness_note': wall_design['note'],
                'chamber_material': mat_name or NOT_AVAILABLE_SPEC,
                # Kütleler GERÇEK geometri x yoğunluk ile hesaplanır; kaba
                # oranlarla (ör. itergaç kütlesinin %25'i) DEĞİL.
                'mass_basis': ('solid geometry x material density from '
                               'materials_db (chamber: pi x L x (r_out^2 - '
                               'r_in^2); injector: plate disc minus orifices)'),
            },
            'manufacturing_complexity': {
                # v2.6.26 (P4) KALDIRILDI: 'machining_time': '24-48 hours' ve
                # 'assembly_time': '4-6 hours'. Bunlar TERMİNDİR ve V2.6.26
                # planı §2.2 gereği kapsam dışıdır: HRMA'nın ne tezgâh saati
                # verisi ne iş gücü modeli var; iki sayı da 500 N'lik motorla
                # 50 kN'lik motorda aynıydı. Sıvı motor tarafında aynı karar
                # MANUFACTURING_COST_STATUS ile uygulanmıştı; arayüz boş hücre
                # yerine bu durumu basabilsin diye alanın yokluğu bildirilir.
                'effort_status': MANUFACTURING_EFFORT_STATUS,
                'skill_level': 'Advanced machinist required',
                'special_tooling': 'Diamond boring bar for nozzle',
                'basis': MANUFACTURING_EFFORT_BASIS
            }
        }

    def _estimate_component_mass(self, component: str, motor_data: Dict) -> float:
        """Bileşen kütlesi — GERÇEK cidar kalınlığı ve GERÇEK malzeme yoğunluğu.

        Eski sürüm kamara kütlesini sabit 5 mm cidar + sabit 7850 kg/m^3 ile
        hesaplıyordu; aynı motor sonucunda yapısal analizin önerdiği kalınlık
        (ör. 20 kN motorda 29 mm) hazır dururken kütle 5 kata kadar sapıyor,
        buradan türeyen total_dry_mass ve thrust_to_weight de yanlış çıkıyordu
        (2026-07-19 denetimi, kritik bulgu).

        Kalınlık/yoğunluk yoksa CAD katmanının 3B meshte kullandığı AYNI
        yedek kural uygulanır (0.045·D_ch) — böylece görsel ile kütle çelişmez.
        """

        chamber_d = _real_scalar(motor_data.get('chamber_diameter')) or 0.1
        # 3B mesh, zarf çapı ve kütle TEK fonksiyondan okur (yedek kural dahil)
        wall_m, _src = _chamber_wall_effective_m(motor_data, chamber_d)
        _key, _name, density = _chamber_material(motor_data)
        if density is None:
            density = get_material('steel_4130')['density']

        if component == 'chamber':
            # Yapısal analizle AYNI hacim modeli: cidar iç çapın DIŞINA eklenir
            # (structural_analysis._calculate_weight ile birebir tutarlı).
            inner_r = chamber_d / 2
            outer_r = inner_r + wall_m
            length = _real_scalar(motor_data.get('chamber_length')) or 0.5
            volume = np.pi * length * (outer_r**2 - inner_r**2)
            return volume * density

        elif component == 'nozzle':
            # v2.6.26: kütle ÇİZİLEN katıdan gelir — aynı iç kontur, aynı
            # cidar, aynı malzeme (bkz. _nozzle_solid). İki ayrı kusur vardı:
            #
            # (O3) Çözücü, lüle cidar malzemesi verilmediğinde sessizce ÇELİĞE
            #      düşüyor ve kütleyi 7850 kg/m³ ile hesaplıyordu. Kullanıcı
            #      grafit seçtiğinde motor sonucunda nozzle_material='graphite'
            #      yazıyor ama kütle çelikten geliyordu (4,36 kat fazla;
            #      tungstende 2,46 kat az).
            # (kapsam) Çözücünün estimated_mass'i YALNIZ diverjan koninin
            #      yüzeyini sayar; CAD katısı konverjanı da içerir. Ölçüldü:
            #      çözücü 0,03885 kg derken katının gerçek kabuğu 0,08948 kg
            #      (2,30 kat) — yani "kütle dökümü" çizilen parçaya ait değildi.
            #
            # Kontur bu koşuda örneklenemezse (eksik geometri) çözücünün değeri
            # yoğunluk düzeltmesiyle kullanılır; o da yoksa yapısal tahmin.
            noz_geo = motor_data.get('nozzle_geometry') or {}
            selected_key = (motor_data.get('nozzle_material')
                            or motor_data.get('throat_material'))
            density_noz = None
            if selected_key:
                try:
                    density_noz = _real_scalar(
                        get_material(str(selected_key))['density'])
                except Exception:
                    density_noz = None
            if density_noz is None:
                density_noz = get_material('graphite')['density']

            wall_noz = _real_scalar(noz_geo.get('wall_thickness'))
            wall_noz = ((wall_noz / 1000.0) if wall_noz is not None else
                        max(0.003, 0.1 * (_real_scalar(
                            motor_data.get('throat_diameter')) or 0.02)))
            try:
                pts_mm, _meta = sample_nozzle_inner_contour(motor_data)
                # Cidar iç kontura DIŞARI eklenir (_nozzle_solid:613 —
                # `outer = [(r + wall, z) ...]`), yani halka hacmi
                # pi*((r+t)^2 - r^2)*dz = pi*(2*r*t + t^2)*dz.
                # Eski hesap kabuğu konturun ORTASINA koyup yalnız 2*pi*r*t*dz
                # sayıyordu; pi*t^2*dz terimi düşüyordu. İnce cidarda fark
                # ihmal edilebilir ama cidar kalınlaşınca büyür (oran
                # 1 + t/(2r)): ölçülen koşuda t=7,79 mm ile kütle 0,694 kg
                # çıkıyordu, çizilen katı 0,751 kg idi (%7,7 eksik).
                volume = 0.0
                for (z0, r0), (z1, r1) in zip(pts_mm[:-1], pts_mm[1:]):
                    dz = (z1 - z0) / 1000.0
                    r_mid = (r0 + r1) / 2000.0
                    volume += np.pi * ((r_mid + wall_noz) ** 2 - r_mid ** 2) * abs(dz)
                if volume > 0:
                    return volume * density_noz
            except Exception:
                pass

            mass = _real_scalar(noz_geo.get('estimated_mass'))
            if mass is not None:
                # Geometri (yüzey x kalınlık) doğru olduğundan yoğunluk
                # oranıyla ÖLÇEKLEMEK tam düzeltmedir — yeni bir sayı
                # uydurulmaz, yanlış yoğunluk düzeltilir.
                used_rho = _real_scalar(noz_geo.get('wall_material_density'))
                if used_rho is not None and abs(density_noz - used_rho) > 1.0:
                    return mass * (density_noz / used_rho)
                return mass
            struct_noz = _real_nested(motor_data.get('structural_analysis') or {},
                                      ('weight_analysis', 'nozzle_weight'))
            if struct_noz is not None:
                return struct_noz
            return 0.0

        elif component == 'injector':
            # Plaka kalınlığı: yapısal analizin düz kapak kalınlığı
            plate_m = _real_nested(motor_data.get('structural_analysis') or {},
                                   ('end_cap_analysis', 'flat_head_thickness'))
            plate_m = (plate_m / 1000.0) if plate_m else wall_m * 2.0
            radius = chamber_d / 2 + wall_m
            # Orifis deliklerinin çıkardığı hacim GERÇEK delik sayısı/çapından
            inj = _injector_spec(motor_data)
            hole_volume = 0.0
            if inj['n_orifices'] and inj['orifice_diameter_mm']:
                r_hole = inj['orifice_diameter_mm'] / 2000.0
                hole_volume = inj['n_orifices'] * np.pi * r_hole**2 * plate_m
            volume = max(0.0, np.pi * radius**2 * plate_m - hole_volume)
            return volume * density

        return 0.0

    #: STL dosyalarının birimi. STL formatının birim başlığı YOKTUR; CAD ve
    #: dilimleyici yazılımların fiili sözleşmesi milimetredir ve bu projenin
    #: STEP çıktısı da (AP214) mm'dir. Mesh'ler ise METRE ile kurulur, bu
    #: yüzden dışa aktarımda ölçeklenirler.
    #: Faz 4B / A1 — ölçülen kusur: aynı ZIP'te STEP zarfı 1069.62 mm iken
    #: STL zarfı 1.0696 (metre) idi; README ve ZIP manifesti "mm" diyordu.
    #: 1000× birim hatası, kapatılmış tank STEP hatasının aynı sınıfı.
    STL_UNITS_PER_METRE = 1000.0

    def export_stl_files(self, assembly_meshes: List, output_dir: str = None):
        """Export STL files for 3D printing/machining.

        BİRİM SÖZLEŞMESİ (A1): dosyalar MİLİMETRE yazılır — STEP ile aynı.
        Mesh'ler metre kurulduğu için dışa aktarımda ``STL_UNITS_PER_METRE``
        ile ölçeklenmiş bir KOPYA yazılır; çağıranın mesh nesneleri (Plotly
        görselleştirmesi ve kütle dökümü aynı nesneleri kullanır) DEĞİŞMEZ.

        YOL SÖZLEŞMESİ (A10): dönen liste MUTLAK dosya yollarıdır ve gerçekten
        yazılan dosyaları gösterir; ilk eleman varsa birleşik
        ``motor_assembly.stl``tir. Çağıran bu yolları kullanmalıdır — sabit
        bir dizinden (``cwd/cad_exports``) okumak yanlış/eski dosya sunar.

        v2.6.26 — İSTEKLER ARASI KİRLENME KAPATILDI.

        Varsayılan çıktı dizini ``./cad_exports/`` idi ve dosya adları
        sabitti (``motor_assembly.stl``, ``chamber.stl`` ...). Uç nokta
        dosyayı diskten GERİ OKUDUĞU için iki eşzamanlı istek aynı yola
        yazıyor ve biri diğerinin geometrisini indiriyordu. ÖLÇÜLDÜ: iki
        farklı motorla (Ø120/L1000 ve Ø300/L2000) altı eşzamanlı denemenin
        ikisinde A isteği HTTP 200 ile B'nin STL'ini aldı. Üretimde sunucu
        8 iş parçacığıyla çalışıyor (``packaging/launcher.py``), yani bu
        teorik bir yarış değil.

        Artık her çağrı kendi geçici dizinine yazar. Çağıran dosyayı
        okuduktan sonra dizini silmelidir (``shutil.rmtree``); silmezse
        işletim sistemi geçici dizin temizliğinde alır.

        ``output_dir`` açıkça verilirse (ör. kullanıcının seçtiği bir klasöre
        toplu dışa aktarım) o kullanılır — davranış değişmez.
        """

        import os
        from hrma.export.export_workspace import (
            atomic_produce, new_workspace, purge_stale_workspaces)
        if output_dir is None:
            purge_stale_workspaces()  # D10: çökme sonrası kalanları topla
            output_dir = new_workspace('hrma_stl_')
        else:
            os.makedirs(output_dir, exist_ok=True)
        output_dir = os.path.abspath(output_dir)

        exported_files = []
        valid_meshes = []

        def _mm(mesh):
            """Metre kurulmuş mesh'in MİLİMETRE ölçekli KOPYASI (A1).

            Kopya şart: aynı nesneler Plotly görselleştirmesinde ve kütle
            dökümünde kullanılıyor; yerinde ölçeklemek onları da bozardı.
            """
            scaled = mesh.copy()
            scaled.apply_scale(self.STL_UNITS_PER_METRE)
            return scaled

        try:
            # First export individual components
            for name, mesh in assembly_meshes:
                if mesh is not None and hasattr(mesh, 'export'):
                    filename = os.path.join(
                        output_dir, f"{name.lower().replace(' ', '_')}.stl")
                    try:
                        mesh_mm = _mm(mesh)
                        # Atomik yazma (D1): yarım STL indirilmesin.
                        atomic_produce(filename, mesh_mm.export)
                        exported_files.append(filename)
                        valid_meshes.append(mesh_mm)
                        print(f"Successfully exported: {filename}")
                    except Exception as e:
                        # OPUS DENETİM DÜZELTMESİ: eski kod hata durumunda
                        # SESSİZCE tek-üçgenlik sahte STL yazıyordu — bozuk
                        # çıktı geçerli exportmuş gibi pakete giriyordu.
                        # Artık hata yükseltilir; endpoint kullanıcıya raporlar.
                        raise RuntimeError(
                            f"{name} STL export başarısız: {e}") from e
                else:
                    print(f"Warning: Invalid mesh for {name}")

            # Create combined motor assembly STL
            if valid_meshes:
                try:
                    import trimesh.util
                    # valid_meshes ZATEN mm ölçekli kopyalardır (bkz. _mm)
                    combined_mesh = trimesh.util.concatenate(valid_meshes)
                    assembly_filename = os.path.join(output_dir,
                                                     'motor_assembly.stl')
                    atomic_produce(assembly_filename, combined_mesh.export)
                    exported_files.append(assembly_filename)
                    print(f"Successfully exported combined assembly: {assembly_filename}")
                except Exception as e:
                    # Birleşik assembly üretilemezse sahte STL YAZILMAZ —
                    # bileşen dosyaları geçerliyse onlarla devam edilir,
                    # hiçbiri yoksa hata yükseltilir (aşağıda).
                    print(f"Error creating combined assembly: {str(e)}")

        except RuntimeError:
            raise
        except Exception as e:
            # OPUS DENETİM DÜZELTMESİ: eski catch-all, tek-üçgenlik sahte
            # STL yazıp başarı gibi dönüyordu. Bozuk çıktı üretmek yasak.
            raise RuntimeError(f"STL export başarısız: {e}") from e

        if not exported_files:
            raise RuntimeError("STL export başarısız: geçerli mesh üretilemedi")

        # Ensure motor_assembly.stl is first in the list if it exists
        motor_assembly_files = [f for f in exported_files if 'motor_assembly' in f.lower()]
        other_files = [f for f in exported_files if 'motor_assembly' not in f.lower()]

        if motor_assembly_files:
            exported_files = motor_assembly_files + other_files

        return exported_files

    def generate_cad_report(self, motor_data: Dict) -> str:
        """Generate comprehensive CAD design report"""

        cad_data = self.generate_3d_motor_assembly(motor_data)

        report = []
        report.append("UZAYTEK HYBRID ROCKET MOTOR")
        report.append("3D CAD DESIGN SPECIFICATION")
        report.append("=" * 50)
        report.append(f"Generated: {motor_data.get('motor_name', 'UZAYTEK-HRM-001')}")
        report.append("")

        # Technical drawings section
        report.append("TECHNICAL DRAWINGS:")
        report.append("-" * 30)
        for component, specs in cad_data['technical_drawings'].items():
            report.append(f"\n{component.upper()}:")
            for key, value in specs.items():
                if isinstance(value, dict):
                    report.append(f"  {key}:")
                    for k, v in value.items():
                        report.append(f"    {k}: {v}")
                else:
                    report.append(f"  {key}: {value}")

        # Material specifications
        report.append("\n\nMATERIAL SPECIFICATIONS:")
        report.append("-" * 30)
        for component, specs in cad_data['material_specifications'].items():
            report.append(f"\n{component.replace('_', ' ').upper()}:")
            report.append(f"  Material: {specs['designation']}")
            for key, value in specs['properties'].items():
                report.append(f"  {key}: {value}")

        # Manufacturing notes
        report.append("\n\nMANUFACTURING NOTES:")
        report.append("-" * 30)
        for note in cad_data['manufacturing_notes']:
            report.append(note)

        # Performance summary
        report.append("\n\nCAD PERFORMANCE SUMMARY:")
        report.append("-" * 30)
        perf = cad_data['performance_summary']
        for category, data in perf.items():
            report.append(f"\n{category.replace('_', ' ').upper()}:")
            for key, value in data.items():
                # None = hesaplanamadı; metin raporda "None" yerine açık etiket
                # basılır (total_length ve thrust_to_weight None olabilir).
                if value is None:
                    report.append(f"  {key}: {NOT_AVAILABLE_SPEC}")
                elif isinstance(value, float):
                    report.append(f"  {key}: {value:.3f}")
                else:
                    report.append(f"  {key}: {value}")

        return "\n".join(report)


# =============================================================================
# DetailedCADGenerator - Engineering Cross-Section Views (Plotly)
# Originally from detailed_cad_generator.py
# =============================================================================

class DetailedCADGenerator:
    """Generate detailed engineering CAD visualizations for rocket motors"""

    def __init__(self):
        self.colors = {
            'chamber': '#2E4057',      # Dark blue-gray
            'nozzle': '#048A81',       # Teal
            'injector': '#C73E1D',     # Red
            'cooling': '#0077B6',      # Blue
            'fuel_feed': '#F77F00',    # Orange
            'ox_feed': '#FCBF49',      # Yellow
            'insulation': '#F8F9FA',   # Light gray
            'structure': '#495057',    # Gray
            'bolts': '#212529',        # Dark gray
            'seals': '#28A745',        # Green
            'sensors': '#6F42C1'       # Purple
        }

    def generate_liquid_motor_cad(self, motor_data: Dict) -> Dict:
        """Generate detailed liquid motor CAD with cross-section"""

        # Extract dimensions
        chamber_diameter = motor_data.get('chamber_diameter', 100) / 1000  # Convert to meters
        chamber_length = motor_data.get('chamber_length', 200) / 1000
        throat_diameter = motor_data.get('throat_diameter', 50) / 1000
        exit_diameter = motor_data.get('exit_diameter', 80) / 1000
        nozzle_length = motor_data.get('nozzle_length', 150) / 1000

        # Create dual view: External + Cross-section
        fig = make_subplots(
            rows=1, cols=2,
            subplot_titles=('External View', 'Cross-Section View'),
            specs=[[{'type': 'scatter3d'}, {'type': 'scatter3d'}]],
            horizontal_spacing=0.05
        )

        # Generate external view components
        external_traces = self._create_external_components(
            chamber_diameter, chamber_length, throat_diameter,
            exit_diameter, nozzle_length, motor_data
        )

        # Generate cross-section components
        cross_section_traces = self._create_cross_section_components(
            chamber_diameter, chamber_length, throat_diameter,
            exit_diameter, nozzle_length, motor_data
        )

        # Add external view traces
        for trace in external_traces:
            fig.add_trace(trace, row=1, col=1)

        # Add cross-section traces
        for trace in cross_section_traces:
            fig.add_trace(trace, row=1, col=2)

        # Update layout
        fig.update_layout(
            title={
                'text': f'Engineering CAD: {motor_data.get("motor_name", "Liquid Motor")}',
                'x': 0.5,
                'font': {'size': 16}
            },
            scene=dict(
                xaxis_title='Length (m)',
                yaxis_title='Width (m)',
                zaxis_title='Height (m)',
                camera=dict(eye=dict(x=1.5, y=1.5, z=1.2)),
                aspectmode='cube'
            ),
            scene2=dict(
                xaxis_title='Length (m)',
                yaxis_title='Radius (m)',
                zaxis_title='Height (m)',
                camera=dict(eye=dict(x=0.1, y=1.8, z=1.2)),
                aspectmode='cube'
            ),
            showlegend=True,
            width=1400,
            height=700
        )

        return {
            'plot_json': fig.to_json(),
            'component_details': self._get_component_details(motor_data),
            'dimensions': {
                'chamber_diameter': chamber_diameter * 1000,
                'chamber_length': chamber_length * 1000,
                'throat_diameter': throat_diameter * 1000,
                'exit_diameter': exit_diameter * 1000,
                'nozzle_length': nozzle_length * 1000
            }
        }

    def _create_external_components(self, chamber_dia, chamber_len, throat_dia,
                                  exit_dia, nozzle_len, motor_data) -> List:
        """Create external view components"""
        traces = []

        # Main chamber body
        chamber_mesh = self._create_cylinder_mesh(
            center=(0, 0, 0),
            radius=chamber_dia/2,
            height=chamber_len,
            color=self.colors['chamber'],
            name='Chamber Body'
        )
        traces.append(chamber_mesh)

        # Injector head
        injector_thickness = 0.05
        injector_mesh = self._create_cylinder_mesh(
            center=(-injector_thickness/2, 0, 0),
            radius=chamber_dia/2 + 0.01,
            height=injector_thickness,
            color=self.colors['injector'],
            name='Injector Head'
        )
        traces.append(injector_mesh)

        # Nozzle
        nozzle_mesh = self._create_nozzle_mesh(
            start_pos=(chamber_len, 0, 0),
            throat_radius=throat_dia/2,
            exit_radius=exit_dia/2,
            length=nozzle_len,
            color=self.colors['nozzle'],
            name='Nozzle',
            motor_data=motor_data
        )
        traces.append(nozzle_mesh)

        # Cooling jacket
        cooling_mesh = self._create_cylinder_mesh(
            center=(chamber_len/2, 0, 0),
            radius=chamber_dia/2 + 0.02,
            height=chamber_len * 0.8,
            color=self.colors['cooling'],
            opacity=0.3,
            name='Cooling Jacket'
        )
        traces.append(cooling_mesh)

        # Feed lines
        # Oxidizer feed (top)
        ox_feed = self._create_feed_line(
            start=(chamber_len * 0.3, chamber_dia/2 + 0.03, chamber_dia/2 + 0.05),
            end=(chamber_len * 0.3, chamber_dia/2 + 0.03, chamber_dia/2 + 0.15),
            radius=0.015,
            color=self.colors['ox_feed'],
            name='Oxidizer Feed'
        )
        traces.append(ox_feed)

        # Fuel feed (side)
        fuel_feed = self._create_feed_line(
            start=(chamber_len * 0.7, chamber_dia/2 + 0.05, 0),
            end=(chamber_len * 0.7, chamber_dia/2 + 0.15, 0),
            radius=0.012,
            color=self.colors['fuel_feed'],
            name='Fuel Feed'
        )
        traces.append(fuel_feed)

        # Mounting flanges
        flanges = self._create_mounting_flanges(chamber_dia, chamber_len)
        traces.extend(flanges)

        # Sensors and instrumentation
        sensors = self._create_sensors(chamber_dia, chamber_len)
        traces.extend(sensors)

        return traces

    def _create_cross_section_components(self, chamber_dia, chamber_len, throat_dia,
                                       exit_dia, nozzle_len, motor_data) -> List:
        """Create cross-section view showing internal components"""
        traces = []

        # Chamber wall cross-section
        wall_thickness = 0.008  # 8mm wall
        chamber_profile = self._create_chamber_cross_section(
            chamber_dia, chamber_len, wall_thickness
        )
        traces.append(chamber_profile)

        # Injector internal structure
        injector_internal = self._create_injector_cross_section(
            chamber_dia, motor_data
        )
        traces.extend(injector_internal)

        # Cooling channels
        cooling_channels = self._create_cooling_channels_cross_section(
            chamber_dia, chamber_len
        )
        traces.extend(cooling_channels)

        # Nozzle internal profile
        nozzle_profile = self._create_nozzle_cross_section(
            chamber_len, throat_dia, exit_dia, nozzle_len
        )
        traces.append(nozzle_profile)

        # Combustion chamber internal
        combustion_chamber = self._create_combustion_chamber_cross_section(
            chamber_dia, chamber_len
        )
        traces.append(combustion_chamber)

        # Flow visualization arrows
        flow_arrows = self._create_flow_arrows_cross_section(
            chamber_dia, chamber_len, nozzle_len
        )
        traces.extend(flow_arrows)

        return traces

    def _create_cylinder_mesh(self, center, radius, height, color, name, opacity=0.8):
        """Create a detailed cylinder mesh"""
        n_theta = 32
        n_z = 2

        theta = np.linspace(0, 2*np.pi, n_theta)
        z = np.linspace(-height/2, height/2, n_z)

        # Create mesh points
        x_cyl = []
        y_cyl = []
        z_cyl = []

        for zi in z:
            for th in theta:
                x_cyl.append(center[0] + zi)
                y_cyl.append(center[1] + radius * np.cos(th))
                z_cyl.append(center[2] + radius * np.sin(th))

        # Create faces
        i, j, k = [], [], []
        for iz in range(n_z - 1):
            for ith in range(n_theta - 1):
                # Current quad indices
                p1 = iz * n_theta + ith
                p2 = iz * n_theta + (ith + 1)
                p3 = (iz + 1) * n_theta + ith
                p4 = (iz + 1) * n_theta + (ith + 1)

                # Two triangles per quad
                i.extend([p1, p2, p1])
                j.extend([p2, p4, p3])
                k.extend([p3, p3, p4])

        return go.Mesh3d(
            x=x_cyl, y=y_cyl, z=z_cyl,
            i=i, j=j, k=k,
            color=color,
            opacity=opacity,
            name=name,
            showlegend=True
        )

    def _create_nozzle_mesh(self, start_pos, throat_radius, exit_radius, length, color, name, motor_data=None):
        """Create detailed nozzle with convergent-divergent profile and angles"""
        n_points = 50

        # Nozzle geometry with proper angles
        conv_length = length * 0.3  # 30% convergent
        div_length = length * 0.7   # 70% divergent

        # Angles for nozzle sections - use calculated values from motor data
        if motor_data:
            conv_angle = motor_data.get('convergent_angle', 15.0)  # degrees (convergent half-angle)
            div_angle = motor_data.get('divergent_angle', 12.0)   # degrees (divergent half-angle)

            # Override with nozzle design data if available
            nozzle_data = motor_data.get('nozzle_design', {})
            if 'convergence_angle' in nozzle_data:
                conv_angle = nozzle_data['convergence_angle']
            if 'divergence_angle' in nozzle_data:
                div_angle = nozzle_data['divergence_angle']
        else:
            # Default values when no motor data provided
            conv_angle = 15.0
            div_angle = 12.0

        # Calculate chamber radius from convergent angle
        chamber_radius = throat_radius + conv_length * math.tan(math.radians(conv_angle))

        # Nozzle profile with linear convergent and divergent sections
        x_profile = np.linspace(0, length, n_points)

        r_profile = []
        for x in x_profile:
            if x < conv_length:
                # Convergent section (linear with 15 deg half-angle)
                progress = x / conv_length
                r = chamber_radius - (chamber_radius - throat_radius) * progress
            else:
                # Divergent section (linear with 12 deg half-angle)
                div_x = x - conv_length
                r = throat_radius + div_x * math.tan(math.radians(div_angle))
            r_profile.append(r)

        # Create revolution surface
        theta = np.linspace(0, 2*np.pi, 32)
        x_noz, y_noz, z_noz = [], [], []

        for i, x in enumerate(x_profile):
            for th in theta:
                x_noz.append(start_pos[0] + x)
                y_noz.append(start_pos[1] + r_profile[i] * np.cos(th))
                z_noz.append(start_pos[2] + r_profile[i] * np.sin(th))

        return go.Scatter3d(
            x=x_noz, y=y_noz, z=z_noz,
            mode='markers',
            marker=dict(size=2, color=color),
            name=name,
            showlegend=True
        )

    def _create_injector_cross_section(self, chamber_dia, motor_data):
        """Create detailed injector cross-section"""
        traces = []

        # Get injector pattern from motor data
        injector_type = motor_data.get('injector_type', 'unlike_impinging')
        hole_count = motor_data.get('injector_holes', 24)

        # Create injector holes pattern
        if injector_type == 'unlike_impinging':
            holes = self._create_impinging_injector_holes(chamber_dia, hole_count)
        else:
            holes = self._create_coaxial_injector_holes(chamber_dia, hole_count)

        traces.extend(holes)

        # Injector face
        injector_face = go.Scatter3d(
            x=[-0.02, -0.02, -0.02, -0.02],
            y=[-chamber_dia/2, chamber_dia/2, chamber_dia/2, -chamber_dia/2],
            z=[-chamber_dia/2, -chamber_dia/2, chamber_dia/2, chamber_dia/2],
            mode='lines',
            line=dict(color=self.colors['injector'], width=6),
            name='Injector Face',
            showlegend=True
        )
        traces.append(injector_face)

        return traces

    def _create_cooling_channels_cross_section(self, chamber_dia, chamber_len):
        """Create cooling channel cross-section"""
        traces = []

        # Cooling channels around chamber wall
        n_channels = 24
        channel_depth = 0.003  # 3mm deep

        for i in range(n_channels):
            angle = i * 2 * np.pi / n_channels

            # Channel path
            x_channel = np.linspace(0, chamber_len, 20)
            y_channel = [(chamber_dia/2 - channel_depth) * np.cos(angle)] * 20
            z_channel = [(chamber_dia/2 - channel_depth) * np.sin(angle)] * 20

            channel = go.Scatter3d(
                x=x_channel,
                y=y_channel,
                z=z_channel,
                mode='lines',
                line=dict(color=self.colors['cooling'], width=3),
                name='Cooling Channel' if i == 0 else None,
                showlegend=True if i == 0 else False
            )
            traces.append(channel)

        return traces

    def _create_chamber_cross_section(self, chamber_dia, chamber_len, wall_thickness):
        """Create chamber wall cross-section"""

        # Outer wall
        x_outer = [0, chamber_len, chamber_len, 0, 0]
        y_outer = [chamber_dia/2 + wall_thickness, chamber_dia/2 + wall_thickness,
                  -chamber_dia/2 - wall_thickness, -chamber_dia/2 - wall_thickness,
                  chamber_dia/2 + wall_thickness]
        z_outer = [0, 0, 0, 0, 0]

        # Inner wall
        x_inner = [0, chamber_len, chamber_len, 0, 0]
        y_inner = [chamber_dia/2, chamber_dia/2, -chamber_dia/2, -chamber_dia/2, chamber_dia/2]
        z_inner = [0, 0, 0, 0, 0]

        return go.Scatter3d(
            x=x_outer + x_inner,
            y=y_outer + y_inner,
            z=z_outer + z_inner,
            mode='lines',
            line=dict(color=self.colors['chamber'], width=4),
            name='Chamber Wall',
            showlegend=True
        )

    def _create_mounting_flanges(self, chamber_dia, chamber_len):
        """Create mounting flanges and bolt patterns"""
        traces = []

        # Forward flange
        forward_flange = self._create_flange(
            position=(-0.03, 0, 0),
            inner_dia=chamber_dia,
            outer_dia=chamber_dia + 0.04,
            thickness=0.02,
            bolt_count=8
        )
        traces.extend(forward_flange)

        # Aft flange
        aft_flange = self._create_flange(
            position=(chamber_len + 0.01, 0, 0),
            inner_dia=chamber_dia,
            outer_dia=chamber_dia + 0.04,
            thickness=0.02,
            bolt_count=8
        )
        traces.extend(aft_flange)

        return traces

    def _create_sensors(self, chamber_dia, chamber_len):
        """Create sensor and instrumentation components"""
        traces = []

        # Pressure transducers
        pressure_sensors = [
            {'pos': (chamber_len * 0.2, chamber_dia/2 + 0.01, chamber_dia/4), 'name': 'Chamber Pressure'},
            {'pos': (chamber_len * 0.8, chamber_dia/2 + 0.01, -chamber_dia/4), 'name': 'Injector Pressure'}
        ]

        for sensor in pressure_sensors:
            sensor_trace = go.Scatter3d(
                x=[sensor['pos'][0]],
                y=[sensor['pos'][1]],
                z=[sensor['pos'][2]],
                mode='markers',
                marker=dict(size=8, color=self.colors['sensors'], symbol='diamond'),
                name=sensor['name'],
                showlegend=True
            )
            traces.append(sensor_trace)

        return traces

    def _get_component_details(self, motor_data) -> Dict:
        """Sıvı motor bileşen özeti — çözücü sonucundan.

        Eski sürüm bu bloğu tamamen sabit dolduruyordu (24 kanal, 24 delik,
        'Inconel 718' / 'C-C Composite' / 'Stainless Steel 316L', 'Regenerative')
        ve kullanıcı bunu kendi tasarımının bileşen özeti sanıyordu; aynı
        oturumda çözücü 80 kanal raporluyordu (2026-07-19 denetimi).

        Beklenen sözleşme — istek gövdesinde motor sonucunun şu alanları
        bulunmalıdır: injector_design (number_of_elements / number_of_orifices),
        cooling_system (cooling_channels), cooling_type, chamber_material,
        nozzle_material, injector_material. Alan yoksa SABİT DEĞER YAZILMAZ;
        NOT_AVAILABLE_SPEC döner. (Not: yalnızca UI'nin sabit gönderdiği
        'injector_holes' anahtarı bilerek okunmaz — o bir arayüz sabitidir,
        tasarım sonucu değil.)
        """
        md = motor_data or {}
        inj_design = md.get('injector_design') or {}
        cooling = md.get('cooling_system') or {}

        holes = _real_scalar(inj_design.get('number_of_elements')
                             or inj_design.get('number_of_orifices')
                             or md.get('injector_elements'))
        channels = _real_scalar(cooling.get('cooling_channels')
                                or md.get('cooling_channels'))
        dp = _real_scalar(inj_design.get('injection_pressure_drop_fuel_bar')
                          or inj_design.get('injection_pressure_drop_bar')
                          or md.get('injector_dp'))
        thrust = _real_scalar(md.get('thrust'))
        isp = _real_scalar(md.get('isp'))
        pc = _real_scalar(md.get('chamber_pressure'))

        return {
            'injector': {
                'type': (inj_design.get('injector_type') or md.get('injector_type')
                         or NOT_AVAILABLE_SPEC),
                'hole_count': int(round(holes)) if holes else NOT_AVAILABLE_SPEC,
                'pressure_drop': f"{dp:.2f} bar" if dp else NOT_AVAILABLE_SPEC,
                'source': 'solver injector_design' if holes else 'not available'
            },
            'cooling': {
                'type': md.get('cooling_type') or NOT_AVAILABLE_SPEC,
                'channel_count': int(round(channels)) if channels else NOT_AVAILABLE_SPEC,
                'coolant': md.get('fuel_type') or NOT_AVAILABLE_SPEC,
                'source': 'solver cooling_system' if channels else 'not available'
            },
            'materials': {
                'chamber': (_chamber_material(md)[1] or md.get('chamber_material')
                            or NOT_AVAILABLE_SPEC),
                'nozzle': md.get('nozzle_material') or NOT_AVAILABLE_SPEC,
                'injector': md.get('injector_material') or NOT_AVAILABLE_SPEC
            },
            'performance': {
                'thrust': f"{thrust:.0f} N" if thrust else NOT_AVAILABLE_SPEC,
                'isp': f"{isp:.1f} s" if isp else NOT_AVAILABLE_SPEC,
                'chamber_pressure': f"{pc:.1f} bar" if pc else NOT_AVAILABLE_SPEC
            }
        }

    def generate_solid_motor_cad(self, motor_data: Dict) -> Dict:
        """Generate detailed solid motor CAD with grain geometry"""

        # Similar structure but for solid motor
        # Will implement grain patterns, inhibitor, case details
        fig = make_subplots(
            rows=1, cols=2,
            subplot_titles=('External View', 'Grain Cross-Section'),
            specs=[[{'type': 'scatter3d'}, {'type': 'scatter3d'}]],
            horizontal_spacing=0.05
        )

        # Add solid motor specific components...
        # (Implementation would be similar but with grain geometry, inhibitors, etc.)

        return {
            'plot_json': fig.to_json(),
            'component_details': self._get_solid_component_details(motor_data)
        }

    def _get_solid_component_details(self, motor_data) -> Dict:
        """Katı motor bileşen özeti — kasa verileri YAPISAL analizden.

        Eski sürüm kasayı sabit yazıyordu ('Steel 4130', '5mm', SF 2.5);
        emniyet katsayısı bu yazılımın en kritik çıktısı ve gerçek yapısal
        analiz zaten mevcuttu (2026-07-19 denetimi).
        """
        md = motor_data or {}
        struct = md.get('structural_analysis') or {}
        wall_m, wall_source = _chamber_wall_thickness_m(md)
        _key, mat_name, _rho = _chamber_material(md)
        sf = (_real_scalar(struct.get('safety_factor_total'))
              or _real_scalar(struct.get('safety_factor'))
              or _real_nested(struct, ('safety_analysis', 'minimum_safety_factor')))
        grain = md.get('grain_design') or {}

        return {
            'grain': {
                'type': (grain.get('grain_type') or md.get('grain_type')
                         or NOT_AVAILABLE_SPEC),
                'segments': (grain.get('number_of_segments')
                             or md.get('grain_count') or NOT_AVAILABLE_SPEC),
                'inhibitor': (grain.get('inhibitor') or md.get('inhibitor')
                              or NOT_AVAILABLE_SPEC)
            },
            'case': {
                'material': mat_name or NOT_AVAILABLE_SPEC,
                'thickness': (f"{wall_m * 1000.0:.2f} mm" if wall_m
                              else NOT_AVAILABLE_SPEC),
                'thickness_source': wall_source,
                'factor_of_safety': sf if sf else NOT_AVAILABLE_SPEC,
                'factor_of_safety_source': ('structural analysis' if sf
                                            else 'not available')
            }
        }

    def _create_impinging_injector_holes(self, chamber_dia, hole_count):
        """Create impinging injector holes pattern"""
        traces = []

        # Create concentric rings of holes
        inner_ring = hole_count // 3
        middle_ring = hole_count // 3
        outer_ring = hole_count - inner_ring - middle_ring

        rings = [
            (inner_ring, chamber_dia * 0.15),
            (middle_ring, chamber_dia * 0.25),
            (outer_ring, chamber_dia * 0.35)
        ]

        for holes_in_ring, radius in rings:
            for i in range(holes_in_ring):
                angle = i * 2 * np.pi / holes_in_ring
                x_hole = -0.015
                y_hole = radius * np.cos(angle)
                z_hole = radius * np.sin(angle)

                hole = go.Scatter3d(
                    x=[x_hole], y=[y_hole], z=[z_hole],
                    mode='markers',
                    marker=dict(size=4, color=self.colors['fuel_feed']),
                    name='Injector Hole' if len(traces) == 0 else None,
                    showlegend=True if len(traces) == 0 else False
                )
                traces.append(hole)

        return traces

    def _create_coaxial_injector_holes(self, chamber_dia, hole_count):
        """Create coaxial injector holes pattern"""
        traces = []

        # Coaxial elements in grid pattern
        rows = int(np.sqrt(hole_count))
        cols = hole_count // rows

        for i in range(rows):
            for j in range(cols):
                y_pos = (i - rows/2) * chamber_dia * 0.1
                z_pos = (j - cols/2) * chamber_dia * 0.1

                # Central fuel hole
                fuel_hole = go.Scatter3d(
                    x=[-0.015], y=[y_pos], z=[z_pos],
                    mode='markers',
                    marker=dict(size=3, color=self.colors['fuel_feed']),
                    name='Fuel Hole' if len(traces) == 0 else None,
                    showlegend=True if len(traces) == 0 else False
                )
                traces.append(fuel_hole)

                # Surrounding oxidizer holes
                for k in range(4):
                    angle = k * np.pi / 2
                    ox_y = y_pos + 0.005 * np.cos(angle)
                    ox_z = z_pos + 0.005 * np.sin(angle)

                    ox_hole = go.Scatter3d(
                        x=[-0.015], y=[ox_y], z=[ox_z],
                        mode='markers',
                        marker=dict(size=2, color=self.colors['ox_feed']),
                        name='Oxidizer Hole' if len(traces) == 1 else None,
                        showlegend=True if len(traces) == 1 else False
                    )
                    traces.append(ox_hole)

        return traces

    def _create_feed_line(self, start, end, radius, color, name):
        """Create a feed line pipe"""
        # Simple cylinder between two points
        direction = np.array(end) - np.array(start)
        length = np.linalg.norm(direction)

        # Create cylinder along line
        n_points = 20
        theta = np.linspace(0, 2*np.pi, n_points)

        x_line = np.linspace(start[0], end[0], 10)
        y_line, z_line = [], []

        for x in x_line:
            for th in theta:
                # Perpendicular to line direction
                y_line.append(start[1] + radius * np.cos(th))
                z_line.append(start[2] + radius * np.sin(th))

        return go.Scatter3d(
            x=x_line * len(theta),
            y=y_line,
            z=z_line,
            mode='markers',
            marker=dict(size=2, color=color),
            name=name,
            showlegend=True
        )

    def _create_flange(self, position, inner_dia, outer_dia, thickness, bolt_count):
        """Create mounting flange with bolt pattern"""
        traces = []

        # Flange body
        flange_body = self._create_cylinder_mesh(
            center=position,
            radius=outer_dia/2,
            height=thickness,
            color=self.colors['structure'],
            name='Flange'
        )
        traces.append(flange_body)

        # Bolt holes
        bolt_radius = (inner_dia + outer_dia) / 4
        for i in range(bolt_count):
            angle = i * 2 * np.pi / bolt_count
            bolt_y = position[1] + bolt_radius * np.cos(angle)
            bolt_z = position[2] + bolt_radius * np.sin(angle)

            bolt = go.Scatter3d(
                x=[position[0]],
                y=[bolt_y],
                z=[bolt_z],
                mode='markers',
                marker=dict(size=4, color=self.colors['bolts'], symbol='circle'),
                name='Bolt' if i == 0 else None,
                showlegend=True if i == 0 else False
            )
            traces.append(bolt)

        return traces

    def _create_nozzle_cross_section(self, chamber_len, throat_dia, exit_dia, nozzle_len):
        """Create nozzle cross-section profile"""
        n_points = 50
        x_profile = np.linspace(chamber_len, chamber_len + nozzle_len, n_points)

        # Bell nozzle profile
        r_profile = []
        for x in x_profile:
            progress = (x - chamber_len) / nozzle_len
            if progress < 0.3:  # Convergent
                r = throat_dia/2 + (exit_dia/2 - throat_dia/2) * (1 - ((1-progress)/0.3)**2)
            else:  # Divergent
                div_progress = (progress - 0.3) / 0.7
                r = throat_dia/2 + (exit_dia/2 - throat_dia/2) * (div_progress**0.6)
            r_profile.append(r)

        # Upper and lower profiles
        return go.Scatter3d(
            x=list(x_profile) + list(x_profile),
            y=r_profile + [-r for r in r_profile],
            z=[0] * len(r_profile) * 2,
            mode='lines',
            line=dict(color=self.colors['nozzle'], width=4),
            name='Nozzle Profile',
            showlegend=True
        )

    def _create_combustion_chamber_cross_section(self, chamber_dia, chamber_len):
        """Create combustion chamber internal view"""
        return go.Scatter3d(
            x=[0, chamber_len, chamber_len, 0, 0],
            y=[chamber_dia/2, chamber_dia/2, -chamber_dia/2, -chamber_dia/2, chamber_dia/2],
            z=[0, 0, 0, 0, 0],
            mode='lines',
            line=dict(color='rgba(255, 100, 0, 0.5)', width=3, dash='dash'),
            name='Combustion Chamber',
            showlegend=True
        )

    def _create_flow_arrows_cross_section(self, chamber_dia, chamber_len, nozzle_len):
        """Create flow direction arrows"""
        traces = []

        # Flow arrows in chamber
        n_arrows = 5
        for i in range(n_arrows):
            x_pos = chamber_len * (i + 1) / (n_arrows + 1)

            arrow = go.Scatter3d(
                x=[x_pos, x_pos + 0.02],
                y=[0, 0],
                z=[0, 0],
                mode='lines+markers',
                line=dict(color='red', width=4),
                marker=dict(size=[2, 6], symbol=['circle', 'diamond']),
                name='Flow Direction' if i == 0 else None,
                showlegend=True if i == 0 else False
            )
            traces.append(arrow)

        return traces
