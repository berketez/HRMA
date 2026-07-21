"""OpenRocket (.ork) tasarım dosyası içe aktarımı.

Girdi ``parse_ork(data)`` ile bayt dizisi olarak alınır ve üç kap biçimi
tanınır:
- ZIP arşivi (``rocket.ork`` girdisi aranır; gömülü ``*.rse`` itki
  eğrileri de ayrıştırılır),
- gzip'li XML (OpenRocket'in varsayılan sıkıştırılmış kaydı),
- düz XML (eski biçim).

Eşleme hedefi HRMA 6-DOF sözleşmesidir (/api/six-dof-analysis,
hrma/analysis/six_dof_trajectory.BarrowmanAero): ``body_diameter``,
``body_length``, ``nose_length``, ``nose_type``, ``fin_count``,
``fin_root_chord``, ``fin_tip_chord``, ``fin_span``, ``fin_sweep``,
``fin_position`` — tümü metre (SI). Bilinmeyen alan None KALIR; hiçbir
varsayılan sessizce doldurulmaz (uydurma-veri-yasağı kimliği).

Kütle politikası:
- ``masscomponent`` doğrudan aktarılır (``estimated: false``).
- Yapısal bileşenler (nosecone/bodytube/transition/finset) dosyanın KENDİ
  malzeme yoğunluğu (``<material type="bulk" density>``) ile
  geometri × yoğunluk TAHMİNİ olarak aktarılır (``estimated: true``);
  yoğunluk dosyada yoksa tahmin YAPILMAZ, atlandığı raporlanır.

Güvenlik: DTD/ENTITY içeren XML reddedilir; ZIP açılırken yol traversal
reddi ve açılmış toplam boyut sınırı (bomba koruması) uygulanır; hiçbir
girdi diske yazılmaz.

Kullanıcıya görünen tüm metinler İngilizce'dir (UI kuralı).
"""

import io
import re
import zipfile
import zlib
import xml.etree.ElementTree as ET

import numpy as np

from hrma.importers import motor_file

# --- ZIP/gzip bomba koruması sınırları ---
# Açılmış toplam içerik sınırı; 20 MB'lık upload sınırıyla (api.py) birlikte
# ~5:1 üzeri genişleme oranlarını da dolaylı olarak sınırlar.
ORK_MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
ORK_ZIP_MAX_MEMBER_COUNT = 200

# Serbest biçimli kanat taraması: kiriş uzunluğu örnekleme sayısı
# (deterministik sayısal integral çözünürlüğü)
FIN_SCANLINE_SAMPLES = 513

# Gövde çapı gruplama toleransı [m] — 0.1 mm altı farklar aynı çap sayılır
DIAMETER_DISTINCT_TOL_M = 1e-4

# XML güvenliği: DTD/entity bildirimli belgeler işlenmeden reddedilir
_XML_FORBIDDEN = re.compile(rb'<!\s*(?:DOCTYPE|ENTITY)', re.IGNORECASE)

# Burun biçimi eşlemesi: HRMA BarrowmanAero yalnız ogive/conical/parabolic
# tanır; birebir karşılığı olmayan biçimler parabolic'e YAKLAŞTIRILIR ve
# mapping_report.approximated içinde raporlanır.
_NOSE_SHAPE_EXACT = {'ogive': 'ogive', 'conical': 'conical',
                     'parabolic': 'parabolic'}
_NOSE_SHAPE_FALLBACK = 'parabolic'

# Aktarılmayan (skipped) bileşen etiketleri — kurtarma/uçuş donanımı ve
# HRMA aero modelinde karşılığı olmayan parçalar
_SKIP_TAGS = frozenset({
    'parachute', 'streamer', 'shockcord', 'railbutton', 'launchlug',
    'innertube', 'centeringring', 'bulkhead', 'engineblock', 'tubecoupler',
    'tubefin', 'tubefinset', 'ellipticalfinset', 'podset', 'boosterset',
    'parallelstage',
})


class _ZipSafetyError(Exception):
    """ZIP güvenlik reddi (traversal / bomba)."""


# ---------------------------------------------------------------------------
# Küçük yardımcılar
# ---------------------------------------------------------------------------
def _to_float(value):
    """Metni float'a çevir; 'auto' ve sayısal olmayan değerlerde None."""
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower().startswith('auto'):
        return None
    if ',' in s and '.' not in s:
        s = s.replace(',', '.')
    try:
        v = float(s)
    except ValueError:
        return None
    return v if np.isfinite(v) else None


def _child_float(elem, name):
    return _to_float(elem.findtext(name))


def _component_name(elem, fallback):
    name = elem.findtext('name')
    return name.strip() if name and name.strip() else fallback


def _material_bulk_density(elem):
    """Bileşenin <material type="bulk" density="..."> yoğunluğu [kg/m3].

    Dosyada yoksa None — tahmin İÇİN varsayılan yoğunluk UYDURULMAZ.
    """
    material = elem.find('material')
    if material is None:
        return None
    if (material.get('type') or '').lower() != 'bulk':
        return None
    return _to_float(material.get('density'))


def _resolve_axial_offset(elem, parent_start, parent_length, own_length,
                          warnings, label):
    """Bileşenin burundan eksenel BAŞLANGIÇ konumunu [m] çöz.

    Yeni biçim ``<axialoffset method="...">`` ya da eski biçim
    ``<position type="...">`` okunur. Dönen ikili:
    (start_m, approximate_flag).
    """
    node = elem.find('axialoffset')
    if node is None:
        node = elem.find('position')
        method = (node.get('type') or '').lower() if node is not None else None
    else:
        method = (node.get('method') or '').lower()
    value = _to_float(node.text) if node is not None else None
    if method is None or value is None:
        warnings.append(
            f"{label}: axial position not found in file; assumed flush "
            "with the parent tube's aft end.")
        method, value = 'bottom', 0.0
        approximate = True
    else:
        approximate = False
    if method == 'top':
        start = parent_start + value
    elif method in ('middle', 'center'):
        start = parent_start + parent_length / 2.0 + value - own_length / 2.0
    elif method == 'bottom':
        start = parent_start + parent_length + value - own_length
    elif method == 'absolute':
        start = value
    else:
        warnings.append(
            f"{label}: unknown axial position method '{method}'; treated "
            "as offset from the parent's top.")
        start = parent_start + value
        approximate = True
    return start, approximate


# ---------------------------------------------------------------------------
# Kap biçimleri: ZIP / gzip
# ---------------------------------------------------------------------------
def _read_member_bounded(zip_file, member_name, remaining_budget):
    """ZIP girdisini parça parça, bütçe aşımında keserek oku."""
    chunks, total = [], 0
    with zip_file.open(member_name) as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            total += len(chunk)
            if total > remaining_budget:
                raise _ZipSafetyError(
                    'ZIP archive expands beyond the allowed size limit '
                    '(possible zip bomb); import rejected.')
            chunks.append(chunk)
    return b''.join(chunks)


def _extract_from_zip(data):
    """ZIP arşivinden rocket.ork XML'ini ve gömülü .rse girdilerini çıkar.

    Dönen: {'xml': bytes, 'rse': [(ad, metin)], 'warnings': [...]}
    ya da {'error': str}.
    """
    warnings = []
    try:
        zip_file = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        return {'error': f'Corrupt ZIP archive: {exc}'}
    infos = zip_file.infolist()
    if len(infos) > ORK_ZIP_MAX_MEMBER_COUNT:
        return {'error': (
            f'ZIP archive contains {len(infos)} entries (limit '
            f'{ORK_ZIP_MAX_MEMBER_COUNT}); import rejected.')}
    declared_total = 0
    for info in infos:
        norm = info.filename.replace('\\', '/')
        parts = norm.split('/')
        if norm.startswith('/') or re.match(r'^[A-Za-z]:', norm) \
                or '..' in parts:
            return {'error': (
                f"Unsafe path in ZIP archive rejected: '{info.filename}'.")}
        declared_total += max(info.file_size, 0)
    if declared_total > ORK_MAX_UNCOMPRESSED_BYTES:
        return {'error': ('ZIP archive expands beyond the allowed size '
                          'limit (possible zip bomb); import rejected.')}
    names = [i.filename for i in infos if not i.is_dir()]
    ork_names = [n for n in names if n.lower().endswith('.ork')]
    target = next((n for n in ork_names
                   if n.replace('\\', '/').rsplit('/', 1)[-1].lower()
                   == 'rocket.ork'), None)
    if target is None and ork_names:
        target = ork_names[0]
        warnings.append(f"'rocket.ork' not found in the archive; using "
                        f"'{target}' instead.")
    if target is None:
        return {'error': ("ZIP archive does not contain a 'rocket.ork' "
                          'design file.')}
    budget = ORK_MAX_UNCOMPRESSED_BYTES
    try:
        xml_bytes = _read_member_bounded(zip_file, target, budget)
        budget -= len(xml_bytes)
        rse_entries = []
        for name in names:
            if name.lower().endswith('.rse'):
                raw = _read_member_bounded(zip_file, name, budget)
                budget -= len(raw)
                rse_entries.append((name, raw.decode('utf-8',
                                                     errors='replace')))
    except _ZipSafetyError as exc:
        return {'error': str(exc)}
    except (zipfile.BadZipFile, zlib.error) as exc:
        return {'error': f'Corrupt ZIP archive: {exc}'}
    return {'xml': xml_bytes, 'rse': rse_entries, 'warnings': warnings}


def _bounded_gunzip(data):
    """gzip verisini boyut sınırıyla aç; aşımda _ZipSafetyError."""
    decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        out = decompressor.decompress(data, ORK_MAX_UNCOMPRESSED_BYTES + 1)
    except zlib.error as exc:
        raise _ZipSafetyError(f'Corrupt gzip data: {exc}')
    if len(out) > ORK_MAX_UNCOMPRESSED_BYTES:
        raise _ZipSafetyError(
            'gzip data expands beyond the allowed size limit; import '
            'rejected.')
    return out


# ---------------------------------------------------------------------------
# Serbest biçimli kanat → eşdeğer trapez
# ---------------------------------------------------------------------------
def _polygon_chord(points, y):
    """Kapalı poligonun y yüksekliğindeki toplam kiriş uzunluğu (scanline)."""
    xs = []
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        if y1 == y2:
            continue
        if (y1 <= y < y2) or (y2 <= y < y1):
            t = (y - y1) / (y2 - y1)
            xs.append(x1 + t * (x2 - x1))
    xs.sort()
    return sum(xs[i + 1] - xs[i] for i in range(0, len(xs) - 1, 2))


def _freeform_to_trapezoid(points):
    """Serbest biçimli kanadı alan + MAC korunumlu eşdeğer trapeze indir.

    points: kök hücum kenarından (0,0) başlayıp kök firar kenarında biten
    çokgen köşeleri [m] (OpenRocket <finpoints> sırası); kök kirişi y=0
    üzerinde kapatılır.

    Dönen dict: root/tip/span/sweep [m], area [m2], mac [m], notes [str]
    ya da None (dejenere geometri).
    """
    if len(points) < 3:
        return None
    span = max(y for _, y in points)
    if span <= 0:
        return None
    ys = np.linspace(0.0, span, FIN_SCANLINE_SAMPLES)
    # Üst uçta yarı-açık kesişim kuralı kirişi 0'a düşürür; limitten (alt
    # taraftan) örnekle — uç kiriş değeri korunur, integral doğru kalır.
    sample_ys = np.minimum(ys, span * (1.0 - 1e-9))
    chords = np.array([_polygon_chord(points, y) for y in sample_ys])
    area = float(np.trapz(chords, ys))
    if area <= 0:
        return None
    mac = float(np.trapz(chords ** 2, ys)) / area
    notes = []
    # Trapez kısıtları: cr+ct = 2A/s; MAC_trap = (2/3)(P^2 - cr*ct)/P
    chord_sum = 2.0 * area / span
    product = chord_sum ** 2 - 1.5 * mac * chord_sum
    disc = chord_sum ** 2 - 4.0 * product
    if disc < 0:
        disc = 0.0
    root = (chord_sum + disc ** 0.5) / 2.0
    tip = (chord_sum - disc ** 0.5) / 2.0
    if tip < 0:
        # MAC bir trapezle korunamayacak kadar büyük: alan+açıklık korunur
        tip = 0.0
        root = chord_sum
        notes.append('fin MAC could not be preserved exactly; area and '
                     'span preserved with a triangular planform')
    # Süpürme: uç hücum kenarı x konumu (en yüksek y'deki en küçük x)
    tip_candidates = [x for x, y in points if abs(y - span) <= 1e-9]
    sweep = min(tip_candidates) if tip_candidates else 0.0
    return {'root': root, 'tip': tip, 'span': span, 'sweep': sweep,
            'area': area, 'mac': mac, 'notes': notes}


# ---------------------------------------------------------------------------
# Yapısal kütle tahminleri (dosyadaki yoğunlukla; yoksa tahmin YOK)
# ---------------------------------------------------------------------------
def _estimate_structural_mass(tag, elem, geometry):
    """Geometri × dosya yoğunluğu kütle tahmini.

    Dönen: (mass_kg, yöntem_notu) ya da (None, atlama_nedeni).
    """
    density = _material_bulk_density(elem)
    if density is None or density <= 0:
        return None, ('no bulk material density in file; mass not '
                      'estimated (no fabricated defaults)')
    thickness = _child_float(elem, 'thickness')
    filled = (elem.findtext('filled') or '').strip().lower() == 'true'
    if tag == 'bodytube':
        radius = geometry.get('radius')
        length = geometry.get('length')
        if radius is None or length is None or thickness is None:
            return None, 'tube radius/length/thickness missing in file'
        inner = max(radius - thickness, 0.0)
        volume = np.pi * (radius ** 2 - inner ** 2) * length
        method = 'thin-wall tube volume x material density'
    elif tag == 'nosecone':
        radius = geometry.get('aft_radius')
        length = geometry.get('length')
        if radius is None or length is None:
            return None, 'nose radius/length missing in file'
        if filled:
            volume = np.pi * radius ** 2 * length / 3.0
            method = 'solid conical volume approximation x density'
        else:
            if thickness is None:
                return None, 'nose shell thickness missing in file'
            slant = float(np.hypot(length, radius))
            volume = np.pi * radius * slant * thickness
            method = 'conical thin-shell (lateral area x thickness) x density'
    elif tag == 'transition':
        r1 = geometry.get('fore_radius')
        r2 = geometry.get('aft_radius')
        length = geometry.get('length')
        if r1 is None or r2 is None or length is None:
            return None, 'transition radii/length missing in file'
        if filled:
            volume = np.pi * length * (r1 ** 2 + r1 * r2 + r2 ** 2) / 3.0
            method = 'solid frustum volume x density'
        else:
            if thickness is None:
                return None, 'transition shell thickness missing in file'
            slant = float(np.hypot(length, r1 - r2))
            volume = np.pi * (r1 + r2) * slant * thickness
            method = 'frustum thin-shell (lateral area x thickness) x density'
    elif tag in ('trapezoidfinset', 'freeformfinset'):
        area = geometry.get('panel_area')
        count = geometry.get('count')
        if area is None or count is None or thickness is None:
            return None, 'fin area/count/thickness missing in file'
        volume = area * thickness * count
        method = 'fin planform area x thickness x count x density'
    else:
        return None, f'no mass model for component type {tag}'
    return float(volume * density), method


# ---------------------------------------------------------------------------
# Ana ayrıştırıcı
# ---------------------------------------------------------------------------
def parse_ork(data):
    """OpenRocket .ork verisini (bayt) HRMA import şemasına ayrıştır.

    Returns
    -------
    dict
        Başarıda::

            {"source": "ork",
             "aero": {6-DOF sözleşme anahtarları, metre; bilinmeyen None},
             "components": [{"name","mass_kg","x_m","propellant",
                             "estimated","source", ...}],
             "embedded_motors": [normalize motor şemaları],
             "saved_simulations": [{"name", "apogee_m", ...}],
             "mapping_report": {"mapped": [], "approximated": [],
                                "skipped": []},
             "warnings": [str]}

        ``x_m``: bileşen orta noktasının burun ucundan mesafesi [m].
        Hatada ``{"error": str}``.
    """
    if isinstance(data, str):
        data = data.encode('utf-8')
    if not isinstance(data, (bytes, bytearray)):
        return {'error': 'ORK content must be provided as bytes.'}
    data = bytes(data)
    if not data:
        return {'error': 'The uploaded .ork file is empty.'}

    warnings = []
    mapped, approximated, skipped = [], [], []
    rse_entries = []
    if data[:4] == b'PK\x03\x04':
        extraction = _extract_from_zip(data)
        if 'error' in extraction:
            return extraction
        xml_bytes = extraction['xml']
        rse_entries = extraction['rse']
        warnings.extend(extraction['warnings'])
    elif data[:2] == b'\x1f\x8b':
        try:
            xml_bytes = _bounded_gunzip(data)
        except _ZipSafetyError as exc:
            return {'error': str(exc)}
    else:
        xml_bytes = data

    if _XML_FORBIDDEN.search(xml_bytes):
        return {'error': ('XML documents containing DTD or ENTITY '
                          'declarations are rejected for security '
                          'reasons.')}
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        return {'error': f'Invalid XML in .ork file: {exc}'}
    if root.tag != 'openrocket':
        return {'error': ('Not an OpenRocket design file (root element '
                          f'is <{root.tag}>, expected <openrocket>).')}
    rocket = root.find('rocket')
    if rocket is None:
        return {'error': 'The file contains no <rocket> definition.'}
    stages = rocket.findall('./subcomponents/stage')
    if not stages:
        return {'error': 'The rocket has no stages.'}
    if len(stages) > 1:
        warnings.append(
            f'Multi-stage design: only the sustainer (first stage) was '
            f'imported; {len(stages) - 1} additional stage(s) skipped.')
        for stage_elem in stages[1:]:
            skipped.append(
                f"stage '{_component_name(stage_elem, 'unnamed')}': "
                'booster/upper stages are not imported')
    sustainer = stages[0]

    # --- Dış (eksenel dizilen) bileşenler ve konum defteri ---
    externals = []
    running_x = 0.0
    stage_children = sustainer.find('subcomponents')
    if stage_children is None:
        return {'error': 'The sustainer stage has no components.'}
    for elem in stage_children:
        tag = elem.tag
        if tag in ('nosecone', 'bodytube', 'transition'):
            length = _child_float(elem, 'length') or 0.0
            externals.append({
                'elem': elem, 'tag': tag, 'start': running_x,
                'length': length,
                'name': _component_name(elem, tag),
            })
            running_x += length
        elif tag in _SKIP_TAGS:
            skipped.append(f"{tag} '{_component_name(elem, tag)}': "
                           'not part of the HRMA aero/mass mapping')
        else:
            skipped.append(f"{tag} '{_component_name(elem, tag)}': "
                           'unrecognized component type')
    if not externals:
        return {'error': ('No axial components (nose cone / body tube) '
                          'found in the sustainer stage.')}
    body_length = running_x

    # --- Yarıçap çözümü ('auto' değerler komşudan) ---
    for ext in externals:
        elem, tag = ext['elem'], ext['tag']
        if tag == 'nosecone':
            ext['fore_radius'] = 0.0
            ext['aft_radius'] = _child_float(elem, 'aftradius')
        elif tag == 'bodytube':
            radius = _child_float(elem, 'radius')
            ext['fore_radius'] = radius
            ext['aft_radius'] = radius
        else:  # transition
            ext['fore_radius'] = _child_float(elem, 'foreradius')
            ext['aft_radius'] = _child_float(elem, 'aftradius')
    for i, ext in enumerate(externals):  # ileri geçiş: önceki komşudan
        if ext['fore_radius'] is None and i > 0:
            ext['fore_radius'] = externals[i - 1]['aft_radius']
        if ext['aft_radius'] is None and ext['tag'] == 'bodytube':
            ext['aft_radius'] = ext['fore_radius']
    for i in range(len(externals) - 1, -1, -1):  # geri geçiş: sonrakinden
        ext = externals[i]
        if ext['aft_radius'] is None and i + 1 < len(externals):
            ext['aft_radius'] = externals[i + 1]['fore_radius']
        if ext['fore_radius'] is None and ext['tag'] == 'bodytube':
            ext['fore_radius'] = ext['aft_radius']

    diameters = []
    for ext in externals:
        for key in ('fore_radius', 'aft_radius'):
            radius = ext[key]
            if radius is not None and radius > 0:
                diameters.append(2.0 * radius)
        if ext['fore_radius'] is None and ext['aft_radius'] is None:
            warnings.append(
                f"{ext['tag']} '{ext['name']}': radius could not be "
                "resolved ('auto' without a neighbor); excluded from the "
                'body diameter.')
    body_diameter = max(diameters) if diameters else None
    if body_diameter is not None:
        distinct = []
        for diameter in diameters:
            if all(abs(diameter - d) > DIAMETER_DISTINCT_TOL_M
                   for d in distinct):
                distinct.append(diameter)
        if len(distinct) > 1:
            warnings.append(
                f'Multiple body diameters found ({len(distinct)} distinct '
                'values); the maximum outer diameter '
                f'({body_diameter:.4f} m) is used for the aero mapping.')
    else:
        warnings.append('Body diameter could not be determined from the '
                        'file.')

    # --- Burun ---
    nose_length = None
    nose_type = None
    nose_elems = [e for e in externals if e['tag'] == 'nosecone']
    if nose_elems:
        nose = nose_elems[0]
        nose_length = nose['length'] or None
        shape_raw = (nose['elem'].findtext('shape') or '').strip().lower()
        if shape_raw in _NOSE_SHAPE_EXACT:
            nose_type = _NOSE_SHAPE_EXACT[shape_raw]
            mapped.append(f"nosecone '{nose['name']}': length and shape "
                          f"({shape_raw})")
        elif shape_raw:
            nose_type = _NOSE_SHAPE_FALLBACK
            approximated.append(
                f"nosecone '{nose['name']}': shape '{shape_raw}' has no "
                f"HRMA equivalent; approximated as '{_NOSE_SHAPE_FALLBACK}'")
        else:
            warnings.append(f"nosecone '{nose['name']}': shape missing in "
                            'file; nose_type left unset.')
        if len(nose_elems) > 1:
            warnings.append('Multiple nose cones found; the first one is '
                            'used.')
    else:
        warnings.append('No nose cone found in the design.')

    # --- Kanat setleri ---
    components = []
    fin_candidates = []
    for ext in externals:
        parent_start, parent_length = ext['start'], ext['length']
        for elem in ext['elem'].iter():
            if elem.tag not in ('trapezoidfinset', 'freeformfinset'):
                continue
            name = _component_name(elem, elem.tag)
            count = _to_float(elem.findtext('fincount'))
            count = int(count) if count else None
            thickness = _child_float(elem, 'thickness')
            if elem.tag == 'trapezoidfinset':
                root_chord = _child_float(elem, 'rootchord')
                tip_chord = _child_float(elem, 'tipchord')
                span = _child_float(elem, 'height')
                sweep = _child_float(elem, 'sweeplength')
                if sweep is None:
                    warnings.append(f"finset '{name}': sweep length "
                                    'missing; fin_sweep left unset.')
                if None in (root_chord, span) or not count:
                    warnings.append(f"finset '{name}': incomplete geometry; "
                                    'skipped.')
                    skipped.append(f"trapezoidfinset '{name}': incomplete "
                                   'geometry')
                    continue
                if tip_chord is None:
                    tip_chord = 0.0
                    approximated.append(
                        f"trapezoidfinset '{name}': tip chord missing in "
                        'file; treated as 0 (pointed fin)')
                panel_area = span * (root_chord + tip_chord) / 2.0
                mapped.append(f"trapezoidfinset '{name}': {count} fins, "
                              'root/tip/span/sweep')
                fin_notes = []
            else:
                points = [(_to_float(p.get('x')), _to_float(p.get('y')))
                          for p in elem.findall('finpoints/point')]
                points = [(x, y) for x, y in points
                          if x is not None and y is not None]
                trapezoid = _freeform_to_trapezoid(points)
                if trapezoid is None or not count:
                    warnings.append(f"freeform finset '{name}': degenerate "
                                    'outline; skipped.')
                    skipped.append(f"freeformfinset '{name}': degenerate "
                                   'outline')
                    continue
                root_chord = trapezoid['root']
                tip_chord = trapezoid['tip']
                span = trapezoid['span']
                sweep = trapezoid['sweep']
                panel_area = trapezoid['area']
                detail = '; '.join(trapezoid['notes'])
                approximated.append(
                    f"freeformfinset '{name}': converted to an equivalent "
                    'trapezoid preserving planform area and MAC'
                    + (f' ({detail})' if detail else ''))
                fin_notes = trapezoid['notes']
            position, pos_approx = _resolve_axial_offset(
                elem, parent_start, parent_length, root_chord, warnings,
                f"finset '{name}'")
            fin_candidates.append({
                'name': name, 'count': count, 'root': root_chord,
                'tip': tip_chord, 'span': span, 'sweep': sweep,
                'position': position, 'position_approximate': pos_approx,
                'panel_area': panel_area, 'freeform': elem.tag ==
                'freeformfinset', 'notes': fin_notes,
            })
            mass, note = _estimate_structural_mass(
                elem.tag, elem, {'panel_area': panel_area, 'count': count})
            if mass is None:
                skipped.append(f"{elem.tag} '{name}' mass: {note}")
            else:
                components.append({
                    'name': name, 'mass_kg': mass,
                    'x_m': position + root_chord / 2.0,
                    'propellant': False, 'estimated': True,
                    'source': 'geometry_density', 'note': note,
                })
                approximated.append(f"{elem.tag} '{name}' mass: {note}")

    fin_aero = None
    if fin_candidates:
        fin_aero = max(fin_candidates,
                       key=lambda c: c['count'] * c['panel_area'])
        if len(fin_candidates) > 1:
            warnings.append(
                f'{len(fin_candidates)} fin sets found; the largest one '
                f"('{fin_aero['name']}') is used for the aero mapping, all "
                'contribute to the mass list.')
    else:
        warnings.append('No fin set found in the design.')

    # --- Yapısal gövde kütleleri + kütle bileşenleri ---
    for ext in externals:
        geometry = {
            'radius': ext.get('fore_radius') or ext.get('aft_radius'),
            'length': ext['length'],
            'fore_radius': ext.get('fore_radius'),
            'aft_radius': ext.get('aft_radius'),
        }
        mass, note = _estimate_structural_mass(ext['tag'], ext['elem'],
                                               geometry)
        if mass is None:
            skipped.append(f"{ext['tag']} '{ext['name']}' mass: {note}")
        else:
            components.append({
                'name': ext['name'], 'mass_kg': mass,
                'x_m': ext['start'] + ext['length'] / 2.0,
                'propellant': False, 'estimated': True,
                'source': 'geometry_density', 'note': note,
            })
            approximated.append(f"{ext['tag']} '{ext['name']}' mass: "
                                f'{note}')
        if ext['tag'] == 'bodytube':
            mapped.append(f"bodytube '{ext['name']}': length and diameter")
        elif ext['tag'] == 'transition':
            mapped.append(f"transition '{ext['name']}': length and radii")

        # masscomponent'lar (iç içe olabilir; konum dış bileşene göre)
        parent_map = {child: parent for parent in ext['elem'].iter()
                      for child in parent}
        for elem in ext['elem'].iter('masscomponent'):
            name = _component_name(elem, 'mass component')
            mass = _child_float(elem, 'mass')
            if mass is None:
                warnings.append(f"mass component '{name}': mass value "
                                'missing; skipped.')
                skipped.append(f"masscomponent '{name}': no mass value")
                continue
            length = _child_float(elem, 'packedlength') or 0.0
            start, pos_approx = _resolve_axial_offset(
                elem, ext['start'], ext['length'], length, warnings,
                f"mass component '{name}'")
            entry = {
                'name': name, 'mass_kg': mass,
                'x_m': start + length / 2.0,
                'propellant': False, 'estimated': False,
                'source': 'masscomponent',
            }
            holder = parent_map.get(parent_map.get(elem))
            if holder is not None and holder is not ext['elem']:
                entry['position_approximate'] = True
                warnings.append(
                    f"mass component '{name}' is nested inside "
                    f"'{_component_name(holder, holder.tag)}'; its axial "
                    'position was resolved relative to the enclosing '
                    'external component and is approximate.')
            elif pos_approx:
                entry['position_approximate'] = True
            components.append(entry)
            mapped.append(f"masscomponent '{name}': mass and position")

        # Aktarılmayan iç bileşenler raporda görünsün (kurtarma vb.)
        for elem in ext['elem'].iter():
            if elem.tag in _SKIP_TAGS:
                skipped.append(
                    f"{elem.tag} '{_component_name(elem, elem.tag)}': not "
                    'part of the HRMA aero/mass mapping')

    # --- Gömülü .rse itki eğrileri (ZIP içinden) ---
    embedded_motors = []
    for entry_name, entry_text in rse_entries:
        parsed = motor_file.parse_rse(entry_text)
        if 'error' in parsed:
            warnings.append(f"Embedded thrust curve '{entry_name}' could "
                            f"not be parsed: {parsed['error']}")
            continue
        for file_warning in parsed['warnings']:
            warnings.append(f"Embedded thrust curve '{entry_name}': "
                            f'{file_warning}')
        for motor in parsed['motors']:
            motor['meta']['source_file'] = entry_name
            embedded_motors.append(motor)

    # --- Kayıtlı simülasyon sonuçları (çapraz doğrulama kartı için) ---
    saved_simulations = []
    for sim in root.findall('.//simulations/simulation'):
        entry = {'name': sim.findtext('name') or 'unnamed simulation'}
        status = sim.get('status')
        if status:
            entry['status'] = status
        flight = sim.find('.//flightdata')
        if flight is not None:
            for attr, key in (('maxaltitude', 'apogee_m'),
                              ('maxvelocity', 'max_velocity_ms'),
                              ('maxacceleration', 'max_acceleration_ms2'),
                              ('maxmach', 'max_mach'),
                              ('timetoapogee', 'time_to_apogee_s'),
                              ('flighttime', 'flight_time_s'),
                              ('groundhitvelocity',
                               'ground_hit_velocity_ms'),
                              ('launchrodvelocity',
                               'launch_rod_velocity_ms')):
                value = _to_float(flight.get(attr))
                if value is not None:
                    entry[key] = value
        if len(entry) > 1:
            saved_simulations.append(entry)

    aero = {
        'nose_length': nose_length,
        'nose_type': nose_type,
        'body_diameter': body_diameter,
        'body_length': body_length if body_length > 0 else None,
        'fin_count': fin_aero['count'] if fin_aero else None,
        'fin_root_chord': fin_aero['root'] if fin_aero else None,
        'fin_tip_chord': fin_aero['tip'] if fin_aero else None,
        'fin_span': fin_aero['span'] if fin_aero else None,
        'fin_sweep': fin_aero['sweep'] if fin_aero else None,
        'fin_position': fin_aero['position'] if fin_aero else None,
    }
    return {
        'source': 'ork',
        'aero': aero,
        'components': components,
        'embedded_motors': embedded_motors,
        'saved_simulations': saved_simulations,
        'mapping_report': {'mapped': mapped, 'approximated': approximated,
                           'skipped': skipped},
        'warnings': warnings,
    }
