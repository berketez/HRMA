"""
Real CAD File Generator for Liquid Rocket Propellant Tanks
Generates STEP, STL, and DXF files compatible with CATIA/SolidWorks
"""

import math
import numpy as np
import os
import json
from typing import Dict, List, Tuple
import tempfile
import zipfile
from datetime import datetime

from hrma.utils.input_guard import finite_number


def _hrma_version() -> str:
    """Üretilen paketin hangi sürümden çıktığını kaydeder (izlenebilirlik)."""
    try:
        from hrma import __version__
        return __version__
    except Exception:
        return 'unknown'

try:
    import FreeCAD
    import Part
    import Mesh
    import Draft
    FREECAD_AVAILABLE = True
except ImportError:
    FREECAD_AVAILABLE = False
    print("FreeCAD not available - using fallback geometry generation")


# ---------------------------------------------------------------------------
# Girdap önleyici düzenek — birim normalizasyonu (T13, 3 Ağustos 2026)
# ---------------------------------------------------------------------------
#
# NEDEN: Sıvı motor çözücüsü ``anti_vortex_device`` sözlüğünü İKİ FARKLI
# birimle yayımlıyor (``liquid_rocket_engine.py:5650-5673``):
#
#     'diameter': av_diameter,                  # METRE
#     'height':   av_height,                    # METRE
#     'vane_radial_length_mm': ... * 1000.0,    # MİLİMETRE
#     'vane_thickness': TANK_VANE_GAUGE_MM,     # MİLİMETRE
#
# Bu modül ise ürettiği paketin TAMAMINI milimetre olarak beyan ediyor
# (``self.units = "mm"``, ``drawing_spec['units'] = 'mm'``,
# ``project_info.units = 'mm'``). Eski kod çapı doğrudan mm sanıyordu
# (``diameter = av_config['diameter']  # mm``), yani düzenek imalata giden
# pakette tam 1000 kat küçük iniyordu.
#
# ÖLÇÜLDÜ (10 kN RP1/LOX, ``POST /export_tank_cad`` paketi, 3 Ağustos 2026):
#   oxidizer_tank_geometry.json -> anti_vortex_device.diameter = 0,235585
#   aynı sözlükte vane_radial_length_mm = 117,7923  ->  2x = 235,5846 mm
#   oran 235,5846 / 0,235585 = 1000,0   (tank çapı 785,282 mm)
#   yani paket mm olarak okunduğunda düzenek/tank oranı 0,0003 çıkıyordu;
#   çözücünün beyan ettiği oran 0,30'dur.
#
# ÇEVİRİ NASIL DOĞRULANIR: büyüklük sezgisiyle DEĞİL, çözücünün kendi
# geometrik özdeşliğiyle. Çözücü kanadı göbekten dış çapa uzatır
# (``vane_radial_len = av_diameter / 2``), dolayısıyla
#
#     diameter[mm] == 2 x vane_radial_length_mm
#
# her koşulda geçerlidir. Ölçek çarpanı bu özdeşlikten ÇIKARILIR. Özdeşlik
# tutmuyorsa ve sözlük kendi birimini de beyan etmiyorsa değer UYDURULMAZ:
# alan ``None`` olur ve ``units`` alanı ``UNRESOLVED`` yazar.
#
# Yükseklik aynı çarpanı paylaşır çünkü çözücü ikisini de tank çapından aynı
# aritmetikle üretir (``diameter * D_RATIO`` ve ``diameter * H_RATIO``): ikisi
# tanım gereği aynı birimdedir.

#: Özdeşlik karşılaştırmasının bağıl toleransı (kayan nokta gürültüsü payı).
_AV_IDENTITY_RTOL = 1e-6


def _as_float(value):
    """Sayıya çevirir; çevrilemeyen ya da sonlu olmayan değer için ``None``.

    Kural burada YAZILMAZ; deponun değer katmanı kapısından okunur
    (``input_guard.finite_number``, ÖH D28 / OH-D27-11). Eski elle yazılmış
    gövde ``bool``u eliyemiyordu: ``float(True) == 1.0`` bir girdap
    önleyici çapını 1,0 yapıyordu.
    """
    return finite_number(value)


def normalize_anti_vortex_mm(av_config, tank_diameter_mm=None):
    """Girdap önleyici sözlüğünü paketin birimine (mm) çevirir.

    Dönen sözlük özgün alanları korur, ``diameter``/``height`` alanlarını
    MİLİMETRE'ye çevirir ve çevirinin nasıl belirlendiğini açıkça yazar:

    * ``units``                 -> ``'mm'`` ya da ``'UNRESOLVED'``
    * ``solver_units``          -> kaynağın birimi (``'m'`` / ``'mm'`` / ...)
    * ``unit_scale_to_mm``      -> uygulanan çarpan
    * ``unit_resolution_basis`` -> çarpanın hangi ölçütle bulunduğu
    * ``diameter_solver_value`` / ``height_solver_value`` -> ham değerler

    ``tank_diameter_mm`` verilirse düzeneğin tanka SIĞDIĞI ayrıca ölçülür ve
    ``fits_inside_tank`` alanıyla bildirilir (sığmıyorsa gizlenmez).
    """
    if not isinstance(av_config, dict):
        return av_config

    out = dict(av_config)
    raw_d = _as_float(av_config.get('diameter'))
    raw_h = _as_float(av_config.get('height'))
    vane_mm = _as_float(av_config.get('vane_radial_length_mm'))

    scale = None
    solver_units = None
    basis = None

    # 1) Birincil ölçüt: çözücünün kendi geometrik özdeşliği.
    if raw_d is not None and raw_d > 0 and vane_mm is not None and vane_mm > 0:
        expected_mm = 2.0 * vane_mm
        tol = _AV_IDENTITY_RTOL * expected_mm
        if abs(raw_d - expected_mm) <= tol:
            scale, solver_units = 1.0, 'mm'
            basis = ('diameter already matches 2 x vane_radial_length_mm '
                     '(the solver geometric identity), so it is already in '
                     'millimetres - no conversion applied')
        elif abs(raw_d * 1000.0 - expected_mm) <= tol:
            scale, solver_units = 1000.0, 'm'
            basis = ('diameter x 1000 matches 2 x vane_radial_length_mm (the '
                     'solver geometric identity), so the solver published it '
                     'in metres - converted to millimetres')

    # 2) İkincil ölçüt: sözlük birimini kendisi beyan ediyorsa ona uyulur.
    declared = str(av_config.get('units', '')).strip().lower()
    _BEYAN = {'mm': 'mm', 'millimetre': 'mm', 'millimeter': 'mm',
              'm': 'm', 'metre': 'm', 'meter': 'm'}
    beyan_birimi = _BEYAN.get(declared)
    if scale is None:
        if beyan_birimi == 'mm':
            scale, solver_units = 1.0, 'mm'
            basis = 'unit taken from the declared "units" field of the source'
        elif beyan_birimi == 'm':
            scale, solver_units = 1000.0, 'm'
            basis = 'unit taken from the declared "units" field of the source'

    # ÖH D24 / P9B2-23 — ÇELİŞKİ SESSİZ KAPATILMAZ.
    # ÖLÇÜLDÜ (taban 88a29d3, ``once.json`` M6): sözlük ``units: "m"`` beyan
    # ederken geometrik özdeşlik ``mm`` diyorsa çıktı, çelişkinin HİÇ
    # yaşanmadığı (``units: "mm"``) sözlüğünkiyle BİREBİR aynıydı —
    # ``unit_declaration_conflict`` alanı yok, ``unit_resolution_basis``
    # yalnız özdeşliği anlatıyor. Yani kaynağın kendi içinde 1000 kat
    # tutarsız olduğu, paketi alan imalatçıya HİÇBİR yerden söylenmiyordu.
    #
    # Özdeşlik ölçüm, beyan ise iddiadır: seçim ÖZDEŞLİKTE kalır (bir alanın
    # adında taşıdığı ``_mm`` ile çapraz doğrulanmış sayı, serbest bir metin
    # alanından güçlüdür). Değişen şey, çelişkinin ARTIK ADIYLA yayımlanması.
    if (beyan_birimi is not None and solver_units is not None
            and beyan_birimi != solver_units):
        out['unit_declaration_conflict'] = {
            'declared_units': av_config.get('units'),
            'resolved_units': solver_units,
            'resolved_by': 'solver geometric identity '
                           '(diameter == 2 x vane_radial_length_mm)',
            'detail': ('the source declares "%s" but its own geometry says '
                       '"%s"; the measured identity was used and the '
                       'declaration was NOT silently accepted. The source '
                       'dictionary is internally inconsistent by a factor of '
                       '1000 - check the producer before manufacturing.'
                       % (av_config.get('units'), solver_units)),
        }
        basis = (basis + '; WARNING: this contradicts the source\'s own '
                 '"units" declaration ("%s") - see '
                 'unit_declaration_conflict' % (av_config.get('units'),))

    if scale is None:
        # 3) Ölçüt yok -> UYDURMA YOK. Ham değer korunur, çevrilmiş alanlar
        #    boş bırakılır ve paket bunu açıkça söyler.
        out['diameter'] = None
        out['height'] = None
        out['units'] = 'UNRESOLVED'
        out['solver_units'] = 'UNRESOLVED'
        out['unit_scale_to_mm'] = None
        out['unit_resolution_basis'] = (
            'unit of diameter/height could not be resolved: the source has '
            'neither a usable vane_radial_length_mm cross-check nor a '
            'declared "units" field. No value is guessed - use '
            'diameter_solver_value / height_solver_value with the unit of '
            'whoever produced them.')
    else:
        out['diameter'] = None if raw_d is None else raw_d * scale
        out['height'] = None if raw_h is None else raw_h * scale
        out['units'] = 'mm'
        out['solver_units'] = solver_units
        out['unit_scale_to_mm'] = scale
        out['unit_resolution_basis'] = basis

    out['diameter_solver_value'] = av_config.get('diameter')
    out['height_solver_value'] = av_config.get('height')

    tank_d = _as_float(tank_diameter_mm)
    if tank_d is not None and tank_d > 0 and _as_float(out.get('diameter')):
        d_mm = float(out['diameter'])
        out['fits_inside_tank'] = bool(0.0 < d_mm <= tank_d)
        out['device_to_tank_diameter_ratio'] = d_mm / tank_d

    return out


def normalize_internal_structures(tank_config):
    """``internal_structures`` kopyasını mm olarak tutarlı hâle getirir.

    Yalnız ``anti_vortex_device`` çevrilir; bafl, ağız ve enstrümantasyon
    alanlarını çözücü zaten mm yayımlıyor (``liquid_rocket_engine.py:5700+``).
    """
    internals = (tank_config or {}).get('internal_structures')
    if not isinstance(internals, dict):
        return internals
    device = internals.get('anti_vortex_device')
    if not isinstance(device, dict):
        return internals
    tank_d = ((tank_config.get('dimensions') or {}).get('diameter')
              if isinstance(tank_config.get('dimensions'), dict) else None)
    out = dict(internals)
    out['anti_vortex_device'] = normalize_anti_vortex_mm(device, tank_d)
    return out


# ---------------------------------------------------------------------------
# Tank CAD paketinin GİRDİ SÖZLEŞMESİ (ÖH Z5S / S7, defter P16B4-17)
# ---------------------------------------------------------------------------
#
# ÖLÇÜLDÜ (28 Ağustos 2026, bu ağaçta):
#
#   POST /export_tank_cad {'tank_data': <calculate_liquid'in
#                          feed_system.tanks bloğu>}
#     -> HTTP 500  {"error": "CAD export error: 'dimensions'"}
#
# Yani ret gövdesi ham bir Python SÖZLÜK ANAHTARI sızdırıyor ve istemciye
# hangi yapının beklendiğini SÖYLEMİYOR. Aynı koşunun ``propellant_tanks``
# bloğu ise 200 + 46 KB ZIP üretiyor: uç ölü değil, sözleşmesi YAZILI DEĞİL.
# ``feed_system.tanks`` makul görünen ama farklı şekilli bir kardeş blok
# (``volume``/``pressure``/``material`` düz alanlar) ve kullanıcıya "yanlış
# blok yolladın" denmiyordu.
#
# Sözleşme aşağıdaki üreticilerin GERÇEKTEN okuduğu alanlardan çıkarıldı
# (bu dosyada: _generate_fallback_files, _generate_cad_instructions,
# _generate_simple_stl, _generate_drawings, _generate_manufacturing_specs):
TANK_CAD_REQUIRED_TANKS = ('oxidizer_tank', 'fuel_tank')
#: Her tankın ``dimensions`` bloğunda SONLU ve POZİTİF olması gereken ölçüler
#: (milimetre; ``propellant_tanks`` bunları ``* 1000`` ile yayımlar).
TANK_CAD_REQUIRED_DIMENSIONS = ('diameter', 'length', 'wall_thickness')
#: Tank STL mesh'inin çevresel bölüntü sayısı (ÖH D15 / defter P9B2-16).
#: Eskiden ``30`` çağrı yerinde gömülüydü; tek yerde tanımlanır ki mesh
#: yoğunluğu ile bekçinin beklediği üçgen sayısı ayrışmasın.
TANK_MESH_RESOLUTION = 30
#: Sözleşmenin geri kalanı: malzeme adı, basınç sınıfı ve iç yapı bloğu.
#:
#: ÖH D21 / defter P9B2-27 — ``pressure_rating`` EKLENDİ. Kapı, üreticilerin
#: GERÇEKTEN okuduğu alanlardan çıkarılmıştı ama ``_generate_drawing_notes``
#: gözden kaçmıştı. ÖLÇÜLDÜ (taban ``35aa279``): kapıdan GEÇEN bir gövde
#: (``dimensions`` + ``structural.material`` + ``internal_structures`` tam)
#: yine ham ``KeyError: 'pressure_rating'`` ile çöküyordu — yani sözleşme
#: kapısı vardı ama sözleşmeyi eksik yazıyordu. Alan uydurma değildir:
#: ``liquid_rocket_engine`` onu ``propellant_tanks[...]['structural']
#: ['pressure_rating']`` olarak (bar) YAYIMLIYOR ve imalat notundaki
#: "Pressure test to 1.5x design pressure" satırı onsuz anlamsızdır.
TANK_CAD_REQUIRED_BLOCKS = (
    ('structural', ('material', 'pressure_rating')),
    ('internal_structures', ('slosh_baffles', 'anti_vortex_device')),
)


class TankCADDataError(ValueError):
    """Tank CAD paketi ÜRETİLEMEZ: girdi sözleşmeyi karşılamıyor.

    ÖH D21 / defter P9B2-27. Sözleşme kapısı (``tank_data_contract_problem``)
    ÖNCE yalnız HTTP ucunda vardı; kütüphaneyi doğrudan çağıran bir tüketici
    (paketleyici betikler, testler, gelecekteki uçlar) aynı eksik gövdeyle
    ham ``KeyError('fuel_tank')`` alıyordu. Artık kapı ÜRETİCİNİN KENDİSİNDE:
    hata Python anahtar adı değil, ucun kendi alan yolunu (``invalid_fields``)
    taşır ve ``ValueError`` türevi olduğu için mevcut ``except ValueError ->
    4xx`` dalları davranışını korur.
    """

    def __init__(self, code, fields):
        self.code = code
        self.fields = fields
        adlar = ', '.join(
            str(f.get('field')) for f in (fields or []) if isinstance(f, dict))
        super().__init__(
            'The tank CAD package is built from the solver block published '
            "as 'propellant_tanks' (each tank carries 'dimensions', "
            "'structural' and 'internal_structures'). Unusable or missing "
            f'fields: {adlar or code}. No manufacturing file was generated.')


def tank_data_contract_problem(tank_data):
    """``tank_data`` imalat paketi üretmeye uygun mu?

    Uygunsa ``None``; değilse ``(hata_kodu, eksik_alan_listesi)`` döner.
    Alan adları NOKTA YOLUDUR (``oxidizer_tank.dimensions.diameter``) —
    istemci hangi bloğu yollayacağını buradan okur. Python anahtar hatası
    metni İSTEMCİYE ÇIKMAZ; ret, ucun kendi alan adlarıyla konuşur.

    Fail-closed: eksik ölçüden imalat çizimi üretilmez. Eksik ölçüyü
    ``0`` ya da üreteç varsayılanıyla doldurmak, kullanıcının hiç vermediği
    bir tankın imalat paketini indirmesi demektir (aynı ilke:
    ``step_export.generate_tank_step``'in 'refusing to emit a manufacturing
    STEP built from generator defaults' reddi).
    """
    if not isinstance(tank_data, dict):
        return 'invalid_tank_data', [{
            'field': 'tank_data',
            'reason': 'not_an_object',
            'received_type': type(tank_data).__name__,
        }]

    problems = []
    for tank in TANK_CAD_REQUIRED_TANKS:
        block = tank_data.get(tank)
        if not isinstance(block, dict):
            problems.append({
                'field': tank,
                'reason': 'missing' if block is None else 'not_an_object',
                'received_type': type(block).__name__,
            })
            continue

        dims = block.get('dimensions')
        if not isinstance(dims, dict):
            problems.append({
                'field': f'{tank}.dimensions',
                'reason': 'missing' if dims is None else 'not_an_object',
                'received_type': type(dims).__name__,
            })
        else:
            for key in TANK_CAD_REQUIRED_DIMENSIONS:
                raw = dims.get(key)
                if raw is None:
                    problems.append({'field': f'{tank}.dimensions.{key}',
                                     'reason': 'missing'})
                    continue
                if isinstance(raw, bool):
                    problems.append({'field': f'{tank}.dimensions.{key}',
                                     'reason': 'not_a_number'})
                    continue
                try:
                    value = float(raw)
                except (TypeError, ValueError):
                    problems.append({'field': f'{tank}.dimensions.{key}',
                                     'reason': 'not_a_number'})
                    continue
                if not math.isfinite(value):
                    problems.append({'field': f'{tank}.dimensions.{key}',
                                     'reason': 'not_finite'})
                elif value <= 0:
                    problems.append({'field': f'{tank}.dimensions.{key}',
                                     'reason': 'not_positive'})

        for name, inner_keys in TANK_CAD_REQUIRED_BLOCKS:
            inner = block.get(name)
            if not isinstance(inner, dict):
                problems.append({
                    'field': f'{tank}.{name}',
                    'reason': 'missing' if inner is None else 'not_an_object',
                    'received_type': type(inner).__name__,
                })
                continue
            for key in inner_keys:
                if inner.get(key) is None:
                    problems.append({'field': f'{tank}.{name}.{key}',
                                     'reason': 'missing'})

    if problems:
        return 'invalid_tank_data', problems
    return None


class TankCADGenerator:
    """Professional CAD file generator for propellant tanks"""
    
    def __init__(self):
        self.units = "mm"  # All dimensions in millimeters
        self.tolerance = 0.01  # 0.01mm tolerance
        
    def generate_tank_cad(self, tank_data: Dict) -> str:
        """Tank imalat paketini üretir; yolu döndürür.

        ÖH D21 / defter P9B2-27 — İKİ KUSUR BİRLİKTE ONARILDI.

        1. **Ham ``KeyError`` gövdesi.** ÖLÇÜLDÜ (taban ``35aa279``,
           ``once.json`` bölüm E): ``fuel_tank`` bloğu eksik bir gövdeyle bu
           üretici ``KeyError: 'fuel_tank'``, ``wall_thickness`` eksikken
           ``KeyError: 'wall_thickness'`` yükseltiyordu. Sözleşme kapısı
           yalnız HTTP ucunda vardı; kütüphaneyi doğrudan çağıran tüketici
           Python anahtar adıyla karşılaşıyordu. Kapı artık ÜRETİCİDE ve tek
           kaynaktan (``tank_data_contract_problem``) okunuyor — uç kendi
           422'sini üretmeye devam eder, davranışı değişmez.

        2. **Başarısız yol bir kez daha deneniyordu.** ``except`` dalı, YENİ
           bir yol denemiyordu: ``FREECAD_AVAILABLE`` yanlışken ``try``
           içinde çağrılan fonksiyonun ta kendisini
           (``_generate_fallback_files``) ikinci kez çağırıyordu. Aynı girdi
           aynı kodda ikinci kez patlar; kazanılan tek şey, ilk denemenin
           yarım yazdığı dosyaların üstüne ikinci bir yarım yazma turudur.
           Yedek yol artık YALNIZ FreeCAD yolu denendi ve düştüyse çalışır.

        Ayrıca (P9B2-14 ile aynı ilke): üretim başarısızsa çalışma dizini
        ``/tmp``de bırakılmaz.
        """
        sorun = tank_data_contract_problem(tank_data)
        if sorun is not None:
            kod, alanlar = sorun
            raise TankCADDataError(kod, alanlar)

        # Create temporary directory for CAD files
        # D10: /tmp birikmesi (ölçüldü: 77 dizin / 17 MB, temizlik yolu yok).
        # Dizin artık ortak çalışma alanı yardımcısından alınır; her açılışta
        # 24 saatten eski HRMA geçici dizinleri toplanır.
        from hrma.export.export_workspace import (
            cleanup_workspace, new_workspace, purge_stale_workspaces)
        purge_stale_workspaces()
        temp_dir = new_workspace('tank_cad_')

        try:
            if not FREECAD_AVAILABLE:
                return self._generate_fallback_files(tank_data, temp_dir)
            try:
                return self._generate_freecad_files(tank_data, temp_dir)
            except Exception as e:
                # FreeCAD yolu düştü -> BAŞKA bir yol denenir (yedek üretici).
                print(f"CAD generation error (FreeCAD path): {str(e)}")
                return self._generate_fallback_files(tank_data, temp_dir)
        except BaseException:
            cleanup_workspace(temp_dir)
            raise
    
    def _generate_freecad_files(self, tank_data: Dict, output_dir: str) -> str:
        """Generate CAD files using FreeCAD"""
        
        # Create new FreeCAD document
        doc = FreeCAD.newDocument("PropellantTanks")
        
        # Generate oxidizer tank
        ox_tank = self._create_tank_solid(
            tank_data['oxidizer_tank'], 
            "Oxidizer_Tank", 
            doc
        )
        
        # Generate fuel tank  
        fuel_tank = self._create_tank_solid(
            tank_data['fuel_tank'],
            "Fuel_Tank", 
            doc,
            offset_x=tank_data['oxidizer_tank']['dimensions']['diameter'] * 1.2
        )
        
        # Generate internal structures
        self._create_internal_structures(
            tank_data['oxidizer_tank'], 
            "OX_Internals", 
            doc
        )
        
        # Export files
        exported_files = []
        
        # Export STEP files (CATIA/SolidWorks compatible)
        step_file = os.path.join(output_dir, "Tank_Assembly.step")
        Part.export(doc.Objects, step_file)
        exported_files.append(step_file)
        
        # Export individual components
        for obj in doc.Objects:
            if hasattr(obj, 'Shape'):
                step_file = os.path.join(output_dir, f"{obj.Label}.step")
                obj.Shape.exportStep(step_file)
                exported_files.append(step_file)
                
                # Also export STL for 3D printing
                stl_file = os.path.join(output_dir, f"{obj.Label}.stl")
                mesh = Mesh.Mesh()
                mesh.addFacets(obj.Shape.tessellate(0.1))
                mesh.write(stl_file)
                exported_files.append(stl_file)
        
        # Generate engineering drawings + manufacturing specs
        # (2026-08-03: yedek yolda olduğu gibi burada da paket listesine
        # eklenmiyorlardı; FreeCAD kurulu olsaydı aynı dosyalar bu yolda da
        # ZIP dışında kalırdı.)
        exported_files.append(self._generate_drawings(tank_data, output_dir))
        exported_files.append(
            self._generate_manufacturing_specs(tank_data, output_dir))

        # Close document
        FreeCAD.closeDocument(doc.Name)
        
        # Create ZIP package
        return self._create_zip_package(output_dir, exported_files)
    
    def _create_tank_solid(self, tank_config: Dict, name: str, doc, offset_x: float = 0) -> object:
        """Create solid tank geometry in FreeCAD"""
        
        dimensions = tank_config['dimensions']
        diameter = dimensions['diameter']  # mm
        length = dimensions['length']      # mm
        wall_thickness = dimensions['wall_thickness']  # mm
        
        # Create outer cylinder
        outer_cylinder = Part.makeCylinder(
            diameter/2, 
            length, 
            FreeCAD.Vector(offset_x, 0, 0),
            FreeCAD.Vector(0, 0, 1)
        )
        
        # Create inner cylinder (hollow)
        inner_diameter = diameter - 2 * wall_thickness
        inner_cylinder = Part.makeCylinder(
            inner_diameter/2,
            length + 1,  # Slightly longer for clean boolean
            FreeCAD.Vector(offset_x, 0, -0.5),
            FreeCAD.Vector(0, 0, 1)
        )
        
        # Boolean difference to create hollow tank
        tank_shell = outer_cylinder.cut(inner_cylinder)
        
        # Create FreeCAD object
        tank_obj = doc.addObject("Part::Feature", name)
        tank_obj.Shape = tank_shell
        tank_obj.Label = name
        
        # Set material properties
        tank_obj.addProperty("App::PropertyString", "Material", "Properties")
        tank_obj.Material = tank_config['structural']['material']
        
        tank_obj.addProperty("App::PropertyFloat", "WallThickness", "Properties")
        tank_obj.WallThickness = wall_thickness
        
        tank_obj.addProperty("App::PropertyFloat", "PressureRating", "Properties")
        tank_obj.PressureRating = tank_config['structural']['pressure_rating']
        
        return tank_obj
    
    def _create_internal_structures(self, tank_config: Dict, name: str, doc) -> List[object]:
        """Create internal tank structures (baffles, anti-vortex)"""
        
        internals = tank_config['internal_structures']
        structures = []
        
        # Create slosh baffles
        for i, baffle in enumerate(internals['slosh_baffles']):
            baffle_obj = self._create_baffle(baffle, f"Baffle_{i+1}", doc)
            structures.append(baffle_obj)
        
        # Create anti-vortex device
        # T13: çözücü çapı/yüksekliği METRE yayımlıyor, bu paket ise mm ile
        # çalışıyor. Katı kurulmadan önce birim normalize edilir.
        anti_vortex = normalize_anti_vortex_mm(
            internals['anti_vortex_device'],
            (tank_config.get('dimensions') or {}).get('diameter'))
        av_obj = self._create_anti_vortex(anti_vortex, "Anti_Vortex_Device", doc)
        structures.append(av_obj)
        
        return structures
    
    def _create_baffle(self, baffle_config: Dict, name: str, doc) -> object:
        """Create individual slosh baffle"""
        
        outer_diameter = baffle_config['outer_diameter']  # mm
        inner_diameter = baffle_config['inner_diameter']  # mm
        thickness = baffle_config['thickness']            # mm
        position = baffle_config['position']              # mm from bottom
        hole_diameter = baffle_config['hole_diameter']    # mm
        hole_count = baffle_config['hole_count']
        
        # Create ring shape
        outer_circle = Part.Wire(Part.makeCircle(outer_diameter/2))
        inner_circle = Part.Wire(Part.makeCircle(inner_diameter/2))
        
        # Create face with hole
        ring_face = Part.Face([outer_circle, inner_circle])
        
        # Extrude to create solid
        baffle_solid = ring_face.extrude(FreeCAD.Vector(0, 0, thickness))
        
        # Add flow holes
        hole_radius = hole_diameter / 2
        hole_spacing_radius = (outer_diameter + inner_diameter) / 4
        
        for i in range(hole_count):
            angle = (i / hole_count) * 2 * np.pi
            hole_x = hole_spacing_radius * np.cos(angle)
            hole_y = hole_spacing_radius * np.sin(angle)
            
            hole_cylinder = Part.makeCylinder(
                hole_radius,
                thickness + 1,
                FreeCAD.Vector(hole_x, hole_y, -0.5),
                FreeCAD.Vector(0, 0, 1)
            )
            
            baffle_solid = baffle_solid.cut(hole_cylinder)
        
        # Position baffle in tank
        baffle_solid = baffle_solid.translate(FreeCAD.Vector(0, 0, position))
        
        # Create FreeCAD object
        baffle_obj = doc.addObject("Part::Feature", name)
        baffle_obj.Shape = baffle_solid
        baffle_obj.Label = name
        
        # Add properties
        baffle_obj.addProperty("App::PropertyString", "Material", "Properties")
        baffle_obj.Material = baffle_config['material']
        
        baffle_obj.addProperty("App::PropertyInteger", "HoleCount", "Properties")
        baffle_obj.HoleCount = hole_count
        
        baffle_obj.addProperty("App::PropertyFloat", "OpenAreaRatio", "Properties")
        baffle_obj.OpenAreaRatio = baffle_config['open_area_ratio']
        
        return baffle_obj
    
    @staticmethod
    def anti_vortex_vane_geometry(av_config: Dict) -> Dict:
        """Katı modelin kanat geometrisini ÇÖZÜCÜNÜN yayımladığı alandan kurar.

        NEDEN (EK-GÖZLEM-2, 2026-08-03): kütle modeli ile katı model aynı
        kanadı anlatmıyordu. Çözücü kanadı merkezden dış çapa uzatıp kütleyi
        ``N x h x (D/2) x t x rho`` ile hesaplıyor — yani modelinde GÖBEK YOK
        ve radyal uzunluk ``D/2``. Katı model ise ``hub_radius = 0,2 x D``
        yapıp kanadı oradan ``D/2``'ye uzatıyordu: radyal uzunluk ``0,3 x D``,
        yani yayımlanan kütlenin dayandığı uzunluktan **%40 kısa**. Aynı
        nesnenin iki farklı geometrisi vardı; STEP dosyasını ölçen kullanıcı
        arayüzdeki kütleyi doğrulayamazdı.

        Bağlayıcı tanım ÇÖZÜCÜNÜNKİDİR, çünkü (1) kütle dökümüne giren ve
        kullanıcıya bugün ulaşan sayı odur, (2) ``vane_radial_length_mm``
        çözücünün açıkça YAYIMLADIĞI bir sözleşme alanıdır (birim çözümü de
        zaten ona demirleniyor), (3) katı yolu FreeCAD kurulu olmadığı için
        bugün hiç koşmuyor, dolayısıyla kırılacak bir tüketicisi yok.

        Sonuç: radyal uzunluk yeniden TÜRETİLMEZ, yayımlanan alandan OKUNUR;
        kanat merkezden başlar ve göbek eklenmez (kütle modelinde olmayan bir
        kütle katıya konmaz).
        """
        diameter = float(av_config['diameter'])            # mm
        half = diameter / 2.0
        vane_len = _as_float(av_config.get('vane_radial_length_mm'))
        if vane_len is None or vane_len <= 0:
            # Alan yoksa çözücünün kendi özdeşliğine düşülür (D/2) — bu bir
            # TAHMİN değil, aynı sözlükteki geometri tanımının kendisi.
            vane_len = half
            basis = ('vane_radial_length_mm missing; fell back to the solver '
                     'geometric identity D/2')
        else:
            basis = ('radial length read from the solver published field '
                     'vane_radial_length_mm (same length its mass model uses)')
        return {
            'vane_length_mm': vane_len,
            # Kanat dış çapta biter; başlangıç yarıçapı buradan çıkar.
            'vane_start_radius_mm': half - vane_len,
            'vane_width_mm': float(av_config['vane_thickness']),
            'vane_height_mm': float(av_config['height']),
            'vane_count': int(av_config['vane_count']),
            'hub_modelled': False,
            'basis': basis,
        }

    def _create_anti_vortex(self, av_config: Dict, name: str, doc) -> object:
        """Create anti-vortex device with radial vanes.

        GİRDİ SÖZLEŞMESİ (T13): ``av_config`` ``normalize_anti_vortex_mm``
        çıktısı olmalıdır, yani ``diameter``/``height`` MİLİMETRE. Ham çözücü
        sözlüğü doğrudan verilirse düzenek 1000 kat küçük kurulur; bu yüzden
        birim çözülememişse katı üretmek yerine hata verilir (sessiz yanlış
        geometri, açık hatadan beterdir).

        Kanat ölçüleri ``anti_vortex_vane_geometry`` ile belirlenir; oradaki
        not göbek/uzunluk kararının gerekçesini taşır (EK-GÖZLEM-2).
        """
        if av_config.get('units') == 'UNRESOLVED':
            raise ValueError(
                'anti-vortex device unit is unresolved; refusing to build a '
                'solid from an unknown unit (see unit_resolution_basis)')
        geom = self.anti_vortex_vane_geometry(av_config)
        vane_count = geom['vane_count']
        vane_length = geom['vane_length_mm']
        vane_width = geom['vane_width_mm']
        vane_height = geom['vane_height_mm']
        start_r = geom['vane_start_radius_mm']

        vanes = []
        for i in range(vane_count):
            angle = (i / vane_count) * 2 * np.pi

            # Create vane as a box
            vane_box = Part.makeBox(vane_length, vane_width, vane_height)

            # Position vane
            vane_box = vane_box.translate(FreeCAD.Vector(start_r, -vane_width/2, 0))

            # Rotate vane
            vane_box = vane_box.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), np.degrees(angle))

            vanes.append(vane_box)

        # Kanatlar birleştirilir; göbek EKLENMEZ (bkz. anti_vortex_vane_geometry)
        av_solid = vanes[0]
        for vane in vanes[1:]:
            av_solid = av_solid.fuse(vane)

        # Create FreeCAD object
        av_obj = doc.addObject("Part::Feature", name)
        av_obj.Shape = av_solid
        av_obj.Label = name
        
        # Add properties
        av_obj.addProperty("App::PropertyString", "Material", "Properties")
        av_obj.Material = av_config['material']
        
        av_obj.addProperty("App::PropertyInteger", "VaneCount", "Properties")
        av_obj.VaneCount = vane_count
        
        return av_obj
    
    def _generate_fallback_files(self, tank_data: Dict, output_dir: str) -> str:
        """Generate CAD files without FreeCAD (geometry data only)"""
        
        exported_files = []
        
        # Generate geometric specifications
        for tank_name, tank_config in [('oxidizer_tank', tank_data['oxidizer_tank']), 
                                     ('fuel_tank', tank_data['fuel_tank'])]:
            
            # Create geometry specification file
            geom_file = os.path.join(output_dir, f"{tank_name}_geometry.json")
            
            geometry_spec = {
                'tank_type': tank_name,
                'dimensions': tank_config['dimensions'],
                'material': tank_config['structural']['material'],
                # T13: paket mm beyan ediyor; girdap önleyicinin metre gelen
                # çap/yükseklik alanları burada mm'ye çevrilir.
                'internal_structures': normalize_internal_structures(
                    tank_config),
                'cad_instructions': self._generate_cad_instructions(tank_config),
                'manufacturing_notes': self._generate_manufacturing_instructions(tank_config)
            }
            
            with open(geom_file, 'w') as f:
                json.dump(geometry_spec, f, indent=2)
            exported_files.append(geom_file)
        
        # ÖLÇÜLDÜ (2026-08-03): aşağıdaki üç üretici dosyalarını çalışma
        # dizinine GERÇEKTEN yazıyordu ama hiçbiri exported_files'a
        # eklenmediği için ZIP'e girmiyordu — indirilen paket yalnız 4 dosya
        # içeriyordu (iki geometry.json + iki step). oxidizer_tank.stl,
        # fuel_tank.stl, engineering_drawings.json ve
        # manufacturing_checklist_TEMPLATE.json sessizce düşüyordu. Üstelik
        # arayüzün başarı mesajı "STL files" ve "Engineering drawings"
        # indiğini SÖYLÜYORDU: iddia ile gerçek çelişiyordu.
        exported_files.extend(self._generate_simple_stl(tank_data, output_dir))
        exported_files.append(self._generate_drawings(tank_data, output_dir))
        exported_files.append(
            self._generate_manufacturing_specs(tank_data, output_dir))

        # GERÇEK STEP (2026-07-13): FreeCAD'e gerek kalmadan build123d/OCC
        # ile tank katıları. Buton yıllardır "STEP/STL" diyordu ama STEP hiç
        # üretilmiyordu; artık kuruluysa üretir, değilse notunu pakete yazar.
        try:
            from hrma.export.step_export import generate_tank_step
            from hrma.export.cad_visualization import (
                tank_head_assessment)
            # BİRİM: tank_data['...']['dimensions'] MİLİMETRE taşır (sıvı motor
            # `ox_tank_diameter * 1000` yazar) ve generate_tank_step de mm bekler.
            # v2.6.2 öncesinde buradaki varsayılanlar METRE cinsindendi (0.3/0.8)
            # ve step_export gelen değeri ayrıca 1000 ile çarpıyordu: gerçek veri
            # geldiğinde 300 mm'lik tank 300 METRE olarak kuruluyor, OpenCascade
            # o katıyı üretemeyip sessizce boş dosya döndürüyordu. Varsayılan yol
            # doğru görünüyordu çünkü 0.3 m × 1000 = 300 mm idi — yani hata
            # yalnızca veri VARKEN ortaya çıkıyordu.
            step_files = generate_tank_step({
                # v2.6.27 dürüstlük kapısı: buradaki 300.0 / 800.0 mm uydurma
                # varsayılanları KALDIRILDI. Ölçü çözümde yoksa None geçer ve
                # generate_tank_step 'refusing to emit a manufacturing STEP
                # built from generator defaults' ValueError'ı ile REDDEDER;
                # aşağıdaki except bunu STEP_NOT_AVAILABLE.txt notuna yazar —
                # yani eksik veri artık Ø300×800 mm bir "imalat" tankına değil,
                # açık bir ret beyanına dönüşür.
                # ÖH D15 / defter P9B2-15: ``wall_thickness`` de GEÇİRİLİR.
                # Geçirilmediği için tank STEP'i içi DOLU bir kütük olarak
                # çiziliyordu (ölçüldü: 2844,64 kg ⟷ yayımlanan 47,62 kg =
                # 59,7 kat) ve aynı paketteki ``*_geometry.json`` oymayı
                # ZATEN tarif ediyordu. Alan
                # ``TANK_CAD_REQUIRED_DIMENSIONS``te zorunlu olduğu için
                # burada yedek üretilmez.
                'fuel_tank': {
                    'diameter': tank_data['fuel_tank']['dimensions'].get('diameter'),
                    'length': tank_data['fuel_tank']['dimensions'].get('length'),
                    'wall_thickness':
                        tank_data['fuel_tank']['dimensions'].get('wall_thickness'),
                    'volume': tank_data['fuel_tank']['dimensions'].get('volume'),
                    'analysed_head_type': (tank_data['fuel_tank'].get(
                        'pressure_vessel') or {}).get('head_type'),
                    # ÖH V31 CV-0: kapak hükmü etikete (tek kaynak).
                    'head_assessment': tank_head_assessment(
                        'fuel_tank', tank_data['fuel_tank']),
                },
                'oxidizer_tank': {
                    'diameter': tank_data['oxidizer_tank']['dimensions'].get('diameter'),
                    'length': tank_data['oxidizer_tank']['dimensions'].get('length'),
                    'wall_thickness':
                        tank_data['oxidizer_tank']['dimensions'].get('wall_thickness'),
                    'volume':
                        tank_data['oxidizer_tank']['dimensions'].get('volume'),
                    'analysed_head_type': (tank_data['oxidizer_tank'].get(
                        'pressure_vessel') or {}).get('head_type'),
                    'head_assessment': tank_head_assessment(
                        'oxidizer_tank', tank_data['oxidizer_tank']),
                },
            }, out_dir=output_dir)
            exported_files.extend(step_files.values())
        except Exception as exc:
            note = os.path.join(output_dir, 'STEP_NOT_AVAILABLE.txt')
            with open(note, 'w') as f:
                f.write(f'STEP üretilemedi: {exc}\n'
                        f'Kurulum: pip install build123d "numpy<2"\n')
            exported_files.append(note)

        return self._create_zip_package(output_dir, exported_files)
    
    def _generate_cad_instructions(self, tank_config: Dict) -> Dict:
        """Generate step-by-step CAD modeling instructions"""
        
        dimensions = tank_config['dimensions']
        from hrma.export.cad_visualization import (
            TANK_FLAT_HEAD_DECLARATION, tank_head_assessment,
            tank_head_declaration, tank_shell_geometry_mm)
        geo = tank_shell_geometry_mm(
            'tank', dimensions['diameter'], dimensions['length'],
            dimensions['wall_thickness'])

        return {
            # ÖH V3 CAD A2 · H4: talimat, aynı paketteki STEP/STL'in çizdiği
            # kabuğun AYNISINI tarif eder (tek kaynak
            # ``cad_visualization.tank_shell_geometry_mm``). Eski talimat
            # dış çapı D sayıp iki ucu AÇIK bir boru tarif ediyordu
            # (iç silindir boy + 1 mm), STEP ise yarıküre başlık çiziyordu.
            'step1_outer_cylinder': {
                'operation': 'Create cylinder (outer envelope)',
                'diameter': geo['outer_diameter_mm'],
                'length': geo['outer_length_mm'],
                'position': [geo['x_min_mm'], 0, 0],
                'axis': '+X',
            },
            'step2_inner_cylinder': {
                'operation': 'Create cylinder (propellant cavity)',
                'diameter': geo['inner_diameter_mm'],
                'length': geo['inner_length_mm'],
                'position': [0, 0, 0],
                'axis': '+X',
            },
            'step3_boolean_cut': {
                'operation': 'Boolean cut (outer - inner)',
                # ÖH V31 CV-0: beyan + kapağın hesaplanan SF'si ve kapı
                # hükmü (``cad_visualization.tank_head_declaration``).
                'result': ('Hollow tank shell with flat heads: '
                           + TANK_FLAT_HEAD_DECLARATION + '; '
                           + tank_head_declaration(
                               tank_head_assessment('tank', tank_config))),
            },
            'step4_baffles': {
                'operation': 'Create slosh baffles',
                'count': len(tank_config['internal_structures']['slosh_baffles']),
                'baffle_specs': tank_config['internal_structures']['slosh_baffles']
            },
            'step5_anti_vortex': {
                'operation': 'Create anti-vortex device',
                # T13: modelleme talimatı da mm ile verilir (bkz. modül notu).
                'specs': normalize_anti_vortex_mm(
                    tank_config['internal_structures']['anti_vortex_device'],
                    dimensions.get('diameter')),
            },
            'step6_assembly': {
                'operation': 'Assemble all components',
                'constraints': ['Concentric alignment', 'Vertical positioning']
            }
        }
    
    def _generate_simple_stl(self, tank_data: Dict, output_dir: str) -> List[str]:
        """Tank STL'leri — STEP ile AYNI kabuk, AYNI eksen (+X).

        Yazdığı dosyaların yollarını DÖNDÜRÜR (2026-08-03): dönüş değeri
        yoktu, çağıran da paket listesine ekleyemiyordu — dosyalar diske
        yazılıp ZIP'e hiç girmiyordu (bkz. ``_generate_fallback_files``).

        ÖH V3 CAD A2 · H9 (karar §28-21 (b)). ÖLÇÜLDÜ (7 Eki CAD kontrolü,
        sıvı + ``max_burn_duration = 30``): STL içi DOLU bir zarftı (156,6 L /
        255,6 L; aynı paketteki STEP kabuğu 5,20 L / 7,23 L) ve ekseni Z'ydi
        (STEP X) — 3B baskıda dolu blok çıkıyordu. Mesh artık STEP'in
        döndürdüğü meridyen profilinin AYNISINDAN kurulur
        (``cad_visualization.tank_shell_geometry_mm`` +
        ``tank_shell_mesh_mm``): boşluk Ø D x L, cidar t dışarı, düz uçlar,
        eksen +X. Kesit sayısı ``TANK_MESH_RESOLUTION``.
        """
        from hrma.export.cad_visualization import (
            tank_shell_geometry_mm, tank_shell_mesh_mm)
        written = []
        for tank_name, tank_config in [('oxidizer_tank', tank_data['oxidizer_tank']),
                                     ('fuel_tank', tank_data['fuel_tank'])]:

            dimensions = tank_config['dimensions']
            stl_file = os.path.join(output_dir, f"{tank_name}.stl")
            geometri = tank_shell_geometry_mm(
                tank_name, dimensions['diameter'], dimensions['length'],
                dimensions['wall_thickness'])
            mesh = tank_shell_mesh_mm(geometri, TANK_MESH_RESOLUTION)
            self._write_stl_file(stl_file, mesh.vertices.tolist(),
                                 mesh.faces.tolist(), tank_name)
            written.append(stl_file)
        return written

    def _write_stl_file(self, filename: str, vertices: List, faces: List, name: str):
        """Write STL file"""
        
        with open(filename, 'w') as f:
            f.write(f"solid {name}\n")
            
            for face in faces:
                # Calculate normal vector
                v1 = np.array(vertices[face[0]])
                v2 = np.array(vertices[face[1]])
                v3 = np.array(vertices[face[2]])
                
                edge1 = v2 - v1
                edge2 = v3 - v1
                normal = np.cross(edge1, edge2)
                normal = normal / np.linalg.norm(normal)
                
                f.write(f"  facet normal {normal[0]:.6f} {normal[1]:.6f} {normal[2]:.6f}\n")
                f.write("    outer loop\n")
                
                for vertex_idx in face:
                    v = vertices[vertex_idx]
                    f.write(f"      vertex {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
                
                f.write("    endloop\n")
                f.write("  endfacet\n")
            
            f.write(f"endsolid {name}\n")
    
    def _generate_drawings(self, tank_data: Dict, output_dir: str) -> str:
        """Generate 2D engineering drawings.

        Yazdığı dosyanın yolunu DÖNDÜRÜR (2026-08-03) — ayrıntı için
        ``_generate_simple_stl``.
        """

        # Create drawing specification
        drawing_spec = {
            'title': 'Propellant Tank Assembly',
            'scale': '1:10',
            'units': 'mm',
            'views': {
                'front_view': self._create_front_view(tank_data),
                'side_view': self._create_side_view(tank_data),
                'section_view': self._create_section_view(tank_data)
            },
            'dimensions': self._extract_key_dimensions(tank_data),
            'notes': self._generate_drawing_notes(tank_data)
        }
        
        drawing_file = os.path.join(output_dir, 'engineering_drawings.json')
        with open(drawing_file, 'w') as f:
            json.dump(drawing_spec, f, indent=2)
        return drawing_file

    def _generate_manufacturing_specs(self, tank_data: Dict,
                                      output_dir: str) -> str:
        """Jenerik imalat KONTROL LİSTESİ üretir — tasarımdan türetilmiş değil.

        Yazdığı dosyanın yolunu DÖNDÜRÜR (2026-08-03) — ayrıntı için
        ``_generate_simple_stl``.


        v2.6.2 dürüstlük düzeltmesi:
        Bu dosya eskiden ``manufacturing_specifications.json`` adıyla ve
        "imalat spesifikasyonu" havasıyla iniyordu. Oysa içindekilerin
        ÇOĞU hesaptan gelmiyordu: bafl ve bağlantı elemanı malzemesi,
        kaynak prosesi (AWS D17.1), ±0,1 mm işleme toleransı, yüzey
        pürüzlülüğü, 1,5x basınç testi, helyum sızıntı eşiği ve montaj
        sırası hepsi SABİT metinlerdi. Yalnız tank kabuğu malzemesi
        gerçekten girdiden geliyordu.

        Bu ayrımı kullanıcının görmesi imkânsızdı; dosya bir bütün olarak
        "hesaplanmış" izlenimi veriyordu. Üstelik FreeCAD pratikte hiçbir
        zaman kurulu olmadığı için tank CAD paketi HER ZAMAN bu yoldan
        çıkıyor, yani şablon her kullanıcıya ulaşıyordu.

        Artık her alan ``source`` etiketi taşır:
          ``analysis``  — bu koşudan hesaplandı
          ``template``  — jenerik örnek, tasarımınıza ait DEĞİL
        ve dosya adı bunu yansıtır.
        """
        ox_struct = tank_data['oxidizer_tank']['structural']
        fuel_struct = tank_data['fuel_tank']['structural']

        def analysis(value, note=None):
            d = {'value': value, 'source': 'analysis'}
            if note:
                d['note'] = note
            return d

        def template(value):
            return {'value': value, 'source': 'template',
                    'note': 'Generic example — NOT derived from your design.'}

        manufacturing_spec = {
            'DISCLAIMER': (
                'This file is a GENERIC CHECKLIST, not a manufacturing '
                'specification. Only fields marked source="analysis" come from '
                'your motor. Every field marked source="template" is a fixed '
                'example: materials, weld process, tolerances, surface finish, '
                'test pressures and the assembly sequence are NOT derived from '
                'your design and must be set by a qualified engineer against '
                'the applicable pressure-vessel code and your own requirements.'
            ),
            'project_info': {
                'title': 'Liquid Rocket Propellant Tanks',
                'date': datetime.now().isoformat(),
                'revision': 'A',
                'units': 'mm',
                'hrma_version': _hrma_version(),
            },
            'materials': {
                # Tank kabuğu malzemesi GERÇEKTEN hesaptan gelir: dayanım ve
                # yoğunluk aynı materials_db kaydından okunur ve cidar
                # kalınlığı ondan boyutlandırılır.
                'oxidizer_tank': analysis(
                    ox_struct.get('material'),
                    f"yield {ox_struct.get('yield_strength_mpa')} MPa, "
                    f"density {ox_struct.get('density_kg_m3')} kg/m3"),
                'fuel_tank': analysis(
                    fuel_struct.get('material'),
                    f"yield {fuel_struct.get('yield_strength_mpa')} MPa, "
                    f"density {fuel_struct.get('density_kg_m3')} kg/m3"),
                'baffles': template('Aluminum 6061-T6'),
                'fasteners': template('Stainless Steel 316'),
            },
            'manufacturing_processes': {
                'tank_shells': template('Spin forming or deep drawing'),
                'welding': template('TIG welding per AWS D17.1'),
                'machining': template('CNC machining +/-0.1 mm tolerance'),
                'surface_finish': template(
                    'Ra 3.2 um internal, Ra 6.3 um external'),
            },
            'quality_requirements': {
                # Tasarım basıncı hesaptan gelir; test ÇARPANI ve sızıntı
                # eşiği koda gömülü örneklerdir.
                'design_pressure_bar': analysis(
                    ox_struct.get('pressure_rating')),
                'pressure_test': template('1.5x design pressure'),
                'leak_test': template('Helium leak test < 1e-6 std cm3/s'),
                'dimensional_inspection': template(
                    '100% inspection of critical dimensions'),
                'material_certification': template(
                    'Mill test certificates required'),
            },
            'assembly_sequence': template([
                '1. Machine tank shells',
                '2. Fabricate internal structures',
                '3. Weld baffles to tank walls',
                '4. Install anti-vortex devices',
                '5. Weld end caps',
                '6. Pressure test individual tanks',
                '7. Final assembly and leak test',
            ]),
        }

        # Ad, içeriğin ne olduğunu söylüyor: şablon kontrol listesi.
        spec_file = os.path.join(output_dir,
                                 'manufacturing_checklist_TEMPLATE.json')
        with open(spec_file, 'w', encoding='utf-8') as f:
            json.dump(manufacturing_spec, f, indent=2, ensure_ascii=False)
        return spec_file

    def _create_zip_package(self, temp_dir: str, files: List[str]) -> str:
        """Create ZIP package of all CAD files"""
        
        zip_filename = f"propellant_tanks_cad_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        zip_path = os.path.join(temp_dir, zip_filename)
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in files:
                if os.path.exists(file_path):
                    zipf.write(file_path, os.path.basename(file_path))
        
        return zip_path
    
    @staticmethod
    def _tank_geometries(tank_data: Dict) -> Dict:
        """İki tankın kabuk geometrisi — STEP/STL ile TEK kaynak (ÖH V3 CAD A2 · H4)."""
        from hrma.export.cad_visualization import tank_shell_geometry_mm
        return {
            ad: tank_shell_geometry_mm(
                ad, tank_data[ad]['dimensions']['diameter'],
                tank_data[ad]['dimensions']['length'],
                tank_data[ad]['dimensions']['wall_thickness'])
            for ad in ('oxidizer_tank', 'fuel_tank')}

    def _create_front_view(self, tank_data: Dict) -> Dict:
        """Create front view drawing data.

        ÖH V3 CAD A2 · H4: zarf, çizilen kabuğun DIŞ zarfıdır (boşluk +
        dışarı eklenen cidar); eskiden boşluk ölçüsü "outline" diye
        yazılıyordu.
        """
        geo = self._tank_geometries(tank_data)
        return {
            'view_type': 'front',
            **{ad: {'outline': 'flat-ended cylinder',
                    'diameter': g['outer_diameter_mm'],
                    'height': g['outer_length_mm']}
               for ad, g in geo.items()},
        }

    def _create_side_view(self, tank_data: Dict) -> Dict:
        """Create side view drawing data.

        Çizim künyesi ``'units': 'mm'`` diyor, bu yüzden girdap önleyici de
        mm olarak taşınır (T13).
        """
        ox = tank_data['oxidizer_tank']
        return {
            'view_type': 'side',
            'shows_internal_structures': True,
            'baffles': ox['internal_structures']['slosh_baffles'],
            'anti_vortex': normalize_anti_vortex_mm(
                ox['internal_structures']['anti_vortex_device'],
                (ox.get('dimensions') or {}).get('diameter')),
        }
    
    def _create_section_view(self, tank_data: Dict) -> Dict:
        """Create section view drawing data"""
        return {
            'view_type': 'section_A-A',
            'cutting_plane': 'vertical_centerline',
            'shows_wall_thickness': True,
            'shows_internal_details': True
        }
    
    def _extract_key_dimensions(self, tank_data: Dict) -> Dict:
        """Extract key dimensions for drawings.

        ÖH V3 CAD A2 · H4: "overall" ölçüler çizilen kabuğun DIŞ zarfıdır;
        boyutlandırmanın D x L'si boşluktur (``cavity_*``). Eskiden boşluk
        ölçüsü "overall" diye yazılıyordu.
        """
        from hrma.export.cad_visualization import (
            TANK_FLAT_HEAD_DECLARATION, tank_head_assessment,
            tank_head_declaration)
        geo = self._tank_geometries(tank_data)
        return {
            ad: {'overall_diameter': g['outer_diameter_mm'],
                 'overall_length': g['outer_length_mm'],
                 'cavity_diameter': g['inner_diameter_mm'],
                 'cavity_length': g['inner_length_mm'],
                 'wall_thickness': g['wall_mm'],
                 # ÖH V31 CV-0: kapağın SF'si ve kapı hükmü.
                 'heads': (TANK_FLAT_HEAD_DECLARATION + '; '
                           + tank_head_declaration(
                               tank_head_assessment(ad, tank_data[ad])))}
            for ad, g in geo.items()}

    def _generate_drawing_notes(self, tank_data: Dict) -> List[str]:
        """Generate drawing notes"""
        return [
            f"1. Material: {tank_data['oxidizer_tank']['structural']['material']}",
            f"2. Pressure rating: {tank_data['oxidizer_tank']['structural']['pressure_rating']} bar",
            "3. All welds per AWS D17.1",
            "4. Pressure test to 1.5x design pressure",
            "5. All dimensions in mm unless noted",
            "6. Surface finish: Ra 3.2 μm internal",
            "7. Leak test: < 1e-6 std cm³/s helium"
        ]
    
    def _generate_manufacturing_instructions(self, tank_config: Dict) -> Dict:
        """Generate detailed manufacturing instructions"""
        return {
            'material_preparation': [
                f"Cut {tank_config['structural']['material']} sheet to size",
                "Inspect material certificates",
                "Clean all surfaces"
            ],
            'forming_operations': [
                "Roll cylinder to required diameter",
                "Weld longitudinal seam with TIG process",
                "Machine weld smooth"
            ],
            'machining_operations': [
                "Machine end faces square and parallel",
                "Drill and tap mounting holes",
                "Deburr all edges"
            ],
            'assembly_steps': [
                "Fit internal structures",
                "Weld baffles in position",
                "Install anti-vortex device",
                "Final weld end caps"
            ],
            'quality_control': [
                "Dimensional inspection",
                "Pressure test",
                "Leak test",
                "Final inspection"
            ]
        }

# Global instance
cad_generator = TankCADGenerator()