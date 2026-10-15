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
- Kütle listesine NEGATİF ya da sonlu olmayan kütle GİRMEZ; üretecek bir
  girdi (negatif uzunluk/yarıçap/kalınlık/yoğunluk, negatif beyan edilmiş
  kütle) sessizce kabul edilmez.

Fizik kapısı (Z5S/P0): ``<length>`` alanı dosyada var ama sonlu bir sayı
değilse ya da negatifse dosya REDDEDİLİR (``error`` + ``error_code``);
sessizce 0 m'ye düşürülmez. Ölçülen kusurlar: negatif uzunluk gövde
kütlesini -0,379 kg yapıp toplamı 0,939 -> 0,182 kg'a düşürüyordu
(P16B4-03); ``NaN`` uzunluk 1,2 m'lik tüpü sıfırlayıp roketi 1,5 -> 0,3 m
yapıyordu (P16B4-04) — her ikisi de sıfır uyarıyla.

``mapping_report`` sözleşmesi: ``skipped`` YALNIZ içe aktarılmayan
BİLEŞENİ listeler. Geometrisi aktarılmış ama kütlesi tahmin edilememiş bir
bileşen "atlanmış" değildir; bu boşluk ``warnings`` kanalından bildirilir.
Böylece aynı bileşen hem ``mapped`` hem ``skipped`` listesinde görünmez
(P16B4-05 iç çelişkisi).

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
import xml.parsers.expat as expat

import numpy as np
# ÖH D26 / OH-D25-14: ``np.trapz`` NumPy 2.0'da ad alanından
# KALDIRILDI (np.trapezoid); ad TEK YERDE çözülür.
from hrma.utils.numeric_compat import trapezoid as _trapezoid

from hrma.importers import motor_file

try:
    # defusedxml İSTEĞE BAĞLI ek katmandır, asıl kapı DEĞİL. requirements.txt
    # ve paket listesinde YOK (V3 SG-2 / SG-01, ana model kararı: yeni
    # bağımlılık eklenmez, §27-11). XXE'yi aşağıdaki üç katman kapatır ve
    # defusedxml yokken de kapalı kaldığı ölçüldü (SG-0 poc/sonuc/
    # sg_enjeksiyon.json; bekçi tests/test_v3_guvenlik.py). Kuruluysa
    # ayrıştırıcı DTD/varlık/harici başvuruyu ayrıca hiç çözmez.
    from defusedxml.ElementTree import fromstring as _defused_fromstring
except ImportError:  # pragma: no cover - paket yoksa expat sertleştirmesi devrede
    _defused_fromstring = None

# --- ZIP/gzip bomba koruması sınırları ---
# Açılmış toplam içerik sınırı; 20 MB'lık upload sınırıyla (api.py) birlikte
# ~5:1 üzeri genişleme oranlarını da dolaylı olarak sınırlar.
ORK_MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
ORK_ZIP_MAX_MEMBER_COUNT = 200

# --- Fiziksel zarf (P9B5-16) ---
#
# ÖLÇÜLDÜ (ÖH D16/ihracat a2, taban 6fde52b): işaret kapıları vardı ama
# BÜYÜKLÜK kapısı yoktu. ``<length>1e9</length>`` bir gövde tüpü
#
#     HTTP 200 · bileşen kütlesi 588.106.144,75 kg ·
#     ``aero.body_length`` = 1.000.000.000,15 m · ``warnings`` = [ ]
#
# üretiyordu; ``<radius>1e9</radius>`` ise ``aero.body_diameter``a
# 2.000.000.000 m ve 15.079.644.737 kg bileşen kütlesi yazıyordu. İkisi de
# ``/api/six-dof-analysis`` sözleşmesine (BarrowmanAero) ve 6-DOF panelinin
# kütle/ağırlık-merkezi tablosuna DOĞRUDAN giriyordu.
#
# Zarf, uçmuş en büyük araçlardan TÜRETİLİR ve cömerttir — işi fizik
# parametresi olmak değil, saçmayı yakalamaktır:
#   * uzunluk: uçmuş en uzun araç Starship/Super Heavy ~121 m (SpaceX),
#     Saturn V 110,6 m, N1 105,3 m → tek BİLEŞEN için 200 m üst sınır
#     her gerçek tasarımın kat kat üstünde.
#   * yarıçap: en büyük gövde çapı N1 birinci kademe tabanı 17,0 m
#     (yarıçap 8,5 m), Saturn V 10,06 m, Starship 9,0 m → 20 m yarıçap
#     (40 m çap) üst sınırı aynı şekilde cömerttir.
#
# Bant TEK KAYNAKTIR: hem uzunluk kapısı hem yarıçap kapısı bu iki adı
# okur, metinlerini de bu sayılardan üretir (elle yazılmış ikinci kopya
# yok).
ORK_COMPONENT_LENGTH_MAX_M = 200.0
ORK_COMPONENT_RADIUS_MAX_M = 20.0

# Serbest biçimli kanat taraması: kiriş uzunluğu örnekleme sayısı
# (deterministik sayısal integral çözünürlüğü)
FIN_SCANLINE_SAMPLES = 513

# Gövde çapı gruplama toleransı [m] — 0.1 mm altı farklar aynı çap sayılır
DIAMETER_DISTINCT_TOL_M = 1e-4

# XML güvenliği: DTD/entity bildirimli belgeler işlenmeden reddedilir.
#
# ÖLÇÜM (Faz 4 denetimi): bu tarama YALNIZCA ham bayt üzerinde yapılıyordu.
# UTF-8 kodlu içerik "DTD rejected" alırken aynı içeriğin UTF-16 kopyası
# (494 bayt -> 1000 karakter) bekçiyi ATLATIP ayrıştırıcıya ulaşıyordu:
# UTF-16'da '<!DOCTYPE' baytları '<\x00!\x00D\x00O\x00...' biçiminde olduğu
# için bayt regex'i eşleşmiyor. Düzeltme üç katmanlıdır:
#   1) ham bayt regex'i (ucuz, UTF-8/ASCII için hızlı ret),
#   2) kodlama tespiti + metne çevirip metin regex'i (kodlamadan bağımsız),
#   3) expat'ın KENDİ kodlama çözümüyle yapısal tarama (kesin katman).
# Üç katmanın üçü de standart kütüphanedir ve her kurulumda vardır. Bunlardan
# geçen belge DTD taşımaz; ayrıştırma defusedxml KURULUYSA onunla (ek katman,
# forbid_dtd/forbid_entities/forbid_external), değilse CPython ElementTree ile
# yapılır (o da harici varlığı diskten/ağdan çözmez). defusedxml
# requirements'ta YOKTUR; paketli üründe bulunacağı varsayılmaz (V3 SG-2 /
# SG-01 beyan düzeltmesi: eski cümle ayrıştırıcının her kurulumda DTD/varlık
# çözmediğini ima ediyordu).
_XML_FORBIDDEN = re.compile(rb'<!\s*(?:DOCTYPE|ENTITY)', re.IGNORECASE)
_XML_FORBIDDEN_TEXT = re.compile(r'<!\s*(?:DOCTYPE|ENTITY)', re.IGNORECASE)

# Kullanıcıya dönen tek ret mesajı (UI kuralı: İngilizce)
_XML_RED_MESAJI = ('XML documents containing DTD or ENTITY declarations '
                   'are rejected for security reasons.')

# Bayt sırası işareti (BOM) -> kodlama
_BOM_KODLAMALARI = (
    (b'\x00\x00\xfe\xff', 'utf-32-be'),
    (b'\xff\xfe\x00\x00', 'utf-32-le'),
    (b'\xef\xbb\xbf', 'utf-8-sig'),
    (b'\xfe\xff', 'utf-16-be'),
    (b'\xff\xfe', 'utf-16-le'),
)

# <?xml ... encoding="..."?> bildirimi (yalnız ASCII uyumlu kodlamalarda görünür)
_XML_DECL_ENCODING_RE = re.compile(rb'''encoding\s*=\s*["']([A-Za-z0-9._\-]+)["']''')

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


class _XMLGuvenlikRed(Exception):
    """XML güvenlik reddi: DTD ya da varlık (entity) bildirimi bulundu."""


# ---------------------------------------------------------------------------
# XML güvenliği: kodlamadan bağımsız DTD/ENTITY bekçisi + sert ayrıştırıcı
# ---------------------------------------------------------------------------
def _xml_kodlama_adaylari(raw):
    """Ham baytlar için olası kodlamaları öncelik sırasıyla döndür.

    Sıra: BOM -> baytların sıfır deseni (XML özdevinimli tanıma) ->
    ``<?xml encoding="...">`` bildirimi -> yaygın varsayılanlar.
    """
    adaylar = []
    for bom, enc in _BOM_KODLAMALARI:
        if raw.startswith(bom):
            adaylar.append(enc)
            break

    if not adaylar and len(raw) >= 4:
        b0, b1, b2, b3 = raw[0], raw[1], raw[2], raw[3]
        # XML belgesi '<' ile başlar; sıfır bayt deseni genişliği ele verir
        if b0 == 0 and b1 == 0 and b3 != 0:
            adaylar.append('utf-32-be')
        elif b1 == 0 and b2 == 0 and b3 == 0:
            adaylar.append('utf-32-le')
        elif b0 == 0 and b1 != 0:
            adaylar.append('utf-16-be')
        elif b0 != 0 and b1 == 0:
            adaylar.append('utf-16-le')

    bildirim = _XML_DECL_ENCODING_RE.search(raw[:512])
    if bildirim:
        try:
            adaylar.append(bildirim.group(1).decode('ascii'))
        except UnicodeDecodeError:
            pass

    adaylar.extend(('utf-8', 'utf-16', 'utf-32'))
    # Sırayı bozmadan tekrarları at
    gorulen, sirali = set(), []
    for enc in adaylar:
        anahtar = enc.lower()
        if anahtar not in gorulen:
            gorulen.add(anahtar)
            sirali.append(enc)
    return sirali


def _xml_metinleri(raw):
    """Ham baytları çözülebilen TÜM aday kodlamalarla metne çevir.

    Tek bir "doğru" kodlama seçilmez: her başarılı çözüm ayrı ayrı
    taranır, böylece yanlış tahmin bekçiyi kör etmez.
    """
    metinler = []
    for enc in _xml_kodlama_adaylari(raw):
        try:
            metinler.append(raw.decode(enc))
        except (UnicodeDecodeError, LookupError, ValueError):
            continue
    return metinler


def _xml_yapisal_tarama(raw):
    """expat'ın kendi kodlama çözümüyle DTD/varlık bildirimi ara.

    Kesin katman: expat kodlamayı (UTF-8/UTF-16 BE-LE/ISO-8859-1...)
    kendisi çözdüğü için tarama kodlamadan bağımsızdır. Belge bozuksa
    burada karar verilmez — asıl ayrıştırıcının hata mesajı korunur.

    Returns
    -------
    bool
        DTD/varlık bildirimi görüldüyse True.
    """
    parser = expat.ParserCreate()

    def _red(*args, **kwargs):
        raise _XMLGuvenlikRed(_XML_RED_MESAJI)

    parser.StartDoctypeDeclHandler = _red
    parser.EntityDeclHandler = _red
    parser.UnparsedEntityDeclHandler = _red
    # Harici varlık başvurusunu ÇÖZME (0 => expat hata verir, dosya/URL
    # açılmaz): SSRF ve yerel dosya sızdırma yolu kapatılır.
    parser.ExternalEntityRefHandler = lambda *args, **kwargs: 0

    try:
        parser.Parse(raw, True)
    except _XMLGuvenlikRed:
        return True
    except expat.ExpatError:
        # Biçim hatası: kararı asıl ayrıştırıcı versin
        return False
    return False


def _xml_guvenlik_denetimi(raw):
    """Üç katmanlı DTD/ENTITY bekçisi; reddedilirse hata mesajı döndür.

    Katmanlar: ham bayt regex + kodlama-bağımsız metin regex + expat
    yapısal tarama. defusedxml bu bekçinin parçası DEĞİLDİR; kuruluysa
    ``_guvenli_xml_ayristir``'da ek katman olarak devreye girer.
    """
    if _XML_FORBIDDEN.search(raw):
        return _XML_RED_MESAJI
    for metin in _xml_metinleri(raw):
        if _XML_FORBIDDEN_TEXT.search(metin):
            return _XML_RED_MESAJI
    if _xml_yapisal_tarama(raw):
        return _XML_RED_MESAJI
    return None


def _guvenli_xml_ayristir(raw):
    """DTD/varlık çözmeyen ayrıştırıcıyla kök elemanı döndür.

    defusedxml kuruluysa ``forbid_dtd/forbid_entities/forbid_external``
    ile ayrıştırılır. Kurulu değilse belge zaten yukarıdaki expat
    taramasından geçmiştir; ayrıca CPython'un ElementTree'si harici
    varlıkları hiçbir koşulda ağdan/diskten çözmez.
    """
    if _defused_fromstring is not None:
        return _defused_fromstring(raw, forbid_dtd=True,
                                   forbid_entities=True, forbid_external=True)
    return ET.fromstring(raw)


# ---------------------------------------------------------------------------
# Küçük yardımcılar
# ---------------------------------------------------------------------------
#: Metin -> float çevirisi TEK TANIMDIR: ``motor_file._to_float``.
#:
#: ÖH D28 / altyapi (defter OH-D27-11, altyapi payı). Burada ikinci bir
#: uygulama duruyordu ve docstring'i ayrı bir davranış vaat ediyordu:
#: "'auto' ve sayısal olmayan değerlerde None". ÖLÇÜLDÜ (33 vakalık
#: korpus, ``once.json``/``sonra.json``): iki uygulama 33/33 vakada AYNI
#: değeri döndürüyor, fark 0. ``'auto'`` dalı ÖLÜ KODDU — ``float('auto…')``
#: zaten ``ValueError`` atıp ``None`` üretiyor. Yani ayrı tanım hiçbir
#: davranış taşımıyor, yalnız iki kopyanın ayrışma riskini taşıyordu.
#: ``motor_file`` bu modülde zaten ithal ediliyor (yukarıda), yeni bağımlılık
#: doğmadı. Sözleşme ve sayılar DEĞİŞMEDİ.
_to_float = motor_file._to_float


def _child_float(elem, name):
    return _to_float(elem.findtext(name))


def _component_name(elem, fallback):
    name = elem.findtext('name')
    return name.strip() if name and name.strip() else fallback


def _component_length(elem, field, tag, name, warnings, warn_missing=True):
    """Bileşen uzunluğunu [m] fizik kapısından geçirerek çöz.

    Dönen ikili: ``(length_m, None)`` ya da ``(None, hata_sözlüğü)``.

    - Alan yoksa/boşsa 0 m kabul edilir; ``warn_missing`` ise bildirilir.
    - Alan var ama sonlu bir sayı değilse (``NaN``, ``inf``, metin) ya da
      negatifse dosya REDDEDİLİR. Sessiz 0'a düşürme, dosyada olmayan bir
      geometriyi uydurmak demektir; negatif uzunluk ise hem negatif kütle
      hem kaymış eksenel konum üretir.
    """
    raw = elem.findtext(field)
    text = '' if raw is None else str(raw).strip()
    if not text:
        if warn_missing:
            warnings.append(
                f"{tag} '{name}': <{field}> is missing in the file; treated "
                'as 0 m in the axial layout.')
        return 0.0, None
    value = _to_float(text)
    if value is None:
        return None, motor_file.error_result(
            'unphysical_component_length',
            f"{tag} '{name}': <{field}> is '{text[:40]}', which is not a "
            'finite number. Component lengths must be finite, non-negative '
            'metres; the file is rejected instead of silently importing '
            '0 m.')
    if value < 0:
        return None, motor_file.error_result(
            'unphysical_component_length',
            f"{tag} '{name}': <{field}> is {value:g} m. Component lengths "
            'must be non-negative: a negative length produces negative '
            'component mass and shifts every axial position, so the file is '
            'rejected.')
    if value > ORK_COMPONENT_LENGTH_MAX_M:
        return None, motor_file.error_result(
            'unphysical_component_length',
            f"{tag} '{name}': <{field}> is {value:g} m, above the "
            f'{ORK_COMPONENT_LENGTH_MAX_M:g} m physical envelope for a '
            'single component (the tallest vehicle ever flown is about '
            '121 m overall). Such a value produces a geometry x density '
            'mass and an axial layout that are not a rocket, so the file '
            'is rejected instead of importing them into the 6-DOF '
            'contract.')
    if value == 0.0 and warn_missing:
        warnings.append(f"{tag} '{name}': <{field}> is 0 m; the component "
                        'contributes no axial length.')
    return value, None


def _check_component_radius(externals):
    """Çözülmüş yarıçapları fiziksel zarftan geçir (P9B5-16).

    Dönen: ``None`` (hepsi geçti) ya da hata sözlüğü.

    Uzunluk kapısının SİMETRİĞİdir. Eskiden negatif yarıçap yalnız kütle
    tahminini düşürüyordu (bileşen kütle listesinden sessizce çıkıyordu),
    devasa yarıçap ise HİÇBİR kapıya takılmadan ``aero.body_diameter``a
    yazılıyordu. Yarıçap, kütleden bağımsız olarak aero eşlemesine giren
    bir GEOMETRİ alanıdır; oraya fizik-dışı bir sayı girerse dosya
    reddedilir.
    """
    for ext in externals:
        for key in ('fore_radius', 'aft_radius'):
            radius = ext.get(key)
            if radius is None:
                continue
            # Alan adı bileşenin KENDİ etiketinden gelir; komşudan
            # miras alınmışsa (``auto``) o da adıyla söylenir.
            alan = (ext.get('radius_fields') or {}).get(key)
            if alan is None:
                alan = ('aftradius' if key == 'aft_radius' else 'foreradius')
                alan += " (resolved from a neighbour's 'auto' radius)"
            if not np.isfinite(radius):
                return motor_file.error_result(
                    'unphysical_component_radius',
                    f"{ext['tag']} '{ext['name']}': <{alan}> is {radius:g}, "
                    'which is not a finite number. Component radii must be '
                    'finite, non-negative metres; the file is rejected '
                    'instead of importing the value into the aero mapping.')
            if radius < 0:
                return motor_file.error_result(
                    'unphysical_component_radius',
                    f"{ext['tag']} '{ext['name']}': <{alan}> is {radius:g} m. "
                    'Component radii must be non-negative: a negative radius '
                    'turns the thin-wall volume into a solid-rod volume and '
                    'still reaches the aero mapping, so the file is '
                    'rejected.')
            if radius > ORK_COMPONENT_RADIUS_MAX_M:
                return motor_file.error_result(
                    'unphysical_component_radius',
                    f"{ext['tag']} '{ext['name']}': <{alan}> is {radius:g} m, "
                    f'above the {ORK_COMPONENT_RADIUS_MAX_M:g} m physical '
                    'envelope for a single component (the widest stage ever '
                    'flown is about 17 m across). The file is rejected '
                    'instead of importing it into the 6-DOF contract.')
    return None


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
        return motor_file.error_result('corrupt_zip',
                                       f'Corrupt ZIP archive: {exc}')
    infos = zip_file.infolist()
    if len(infos) > ORK_ZIP_MAX_MEMBER_COUNT:
        return motor_file.error_result('zip_member_limit', (
            f'ZIP archive contains {len(infos)} entries (limit '
            f'{ORK_ZIP_MAX_MEMBER_COUNT}); import rejected.'))
    declared_total = 0
    for info in infos:
        norm = info.filename.replace('\\', '/')
        parts = norm.split('/')
        if norm.startswith('/') or re.match(r'^[A-Za-z]:', norm) \
                or '..' in parts:
            return motor_file.error_result('unsafe_zip_path', (
                f"Unsafe path in ZIP archive rejected: "
                f"'{info.filename}'."))
        declared_total += max(info.file_size, 0)
    if declared_total > ORK_MAX_UNCOMPRESSED_BYTES:
        return motor_file.error_result(
            'zip_bomb',
            'ZIP archive expands beyond the allowed size limit (possible '
            'zip bomb); import rejected.')
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
        return motor_file.error_result(
            'no_rocket_ork',
            "ZIP archive does not contain a 'rocket.ork' design file.")
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
        return motor_file.error_result('zip_bomb', str(exc))
    except (zipfile.BadZipFile, zlib.error) as exc:
        return motor_file.error_result('corrupt_zip',
                                       f'Corrupt ZIP archive: {exc}')
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
    area = float(_trapezoid(chords, ys))
    if area <= 0:
        return None
    mac = float(_trapezoid(chords ** 2, ys)) / area
    # --- ÖH D24 / defter P9B5-34: HEDEF MAC'İN KENDİ ÇÖZÜNÜRLÜK TABANI -----
    # ``mac`` bir integral DEĞERİ değil, ``FIN_SCANLINE_SAMPLES`` noktalı
    # yamuk kuralının KESTİRİMİDİR. Aşağıdaki "MAC korunamadı" hükmü, bu
    # kestirimle trapezin kapalı-form MAC'ini karşılaştırarak veriliyor;
    # dolayısıyla kestirimin kendi hatasından küçük bir sapma HÜKÜM DEĞİL,
    # GÜRÜLTÜDÜR. Taban uydurulmaz, ÖLÇÜLÜR: aynı integral yarı çözünürlükte
    # bir kez daha alınır ve iki kestirimin farkı çözünürlük tabanı sayılır
    # (yamuk kuralı h² ile yakınsadığı için gerçek hata bu farkın ~1/3'üdür;
    # yani taban ~3 kat muhafazakârdır).
    ys_kaba = ys[::2]
    chords_kaba = chords[::2]
    alan_kaba = float(_trapezoid(chords_kaba, ys_kaba))
    mac_kaba = (float(_trapezoid(chords_kaba ** 2, ys_kaba)) / alan_kaba
                if alan_kaba > 0 else mac)
    mac_cozunurluk_tabani = abs(mac - mac_kaba)
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
        # --- ÖH D24 / defter P9B5-34: NOT KAZANILIR, KOŞULSUZ BASILMAZ -----
        # ÖLÇÜLDÜ (``a2/once.json`` -> ``M6_P9B5_34``, taban 88a29d3): ÜÇGEN
        # kanatta (uçta tek nokta) bu dal daima ateşleniyordu, çünkü üçgen
        # dönüşümün SINIR halidir — ct = 0, cr = chord_sum, MAC = (2/3)·cr —
        # ve ``tip`` yalnız kayan nokta artığı kadar negatife düşüyordu.
        # Basılan not ise "MAC korunamadı" diyordu. Ölçülen gerçek:
        #
        #   üçgen (dik / süpürmeli): hedef MAC 0,10000019073 m
        #                            trapez MAC 0,10000000000 m
        #                            bağıl fark 1,9e-06  = tarama gürültüsü
        #
        # Yani MAC KORUNMUŞTU; sapmanın tamamı hedefin kendi tarama hatasıydı
        # (513 noktalı yamuk kuralı). Not, dosyayı içe aktaran kullanıcıya
        # olmayan bir bilgi kaybı bildiriyordu.
        #
        # Not artık ÖLÇÜLEREK kazanılır: trapezin kapalı-form MAC'i hedefle
        # karşılaştırılır ve sapma yalnız hedefin ÖLÇÜLEN çözünürlük tabanını
        # (+ kayan nokta yuvarlaması) aştığında bildirilir — ve o zaman
        # SAYIYLA bildirilir. Gerçekten temsil edilemeyen bir dış çizgide
        # (MAC > (2/3)·chord_sum, ör. elmas/içbükey kanat) dal aynen çalışır.
        mac_trapez = (2.0 / 3.0) * root
        sapma = abs(mac_trapez - mac)
        tolerans = mac_cozunurluk_tabani + 8.0 * float(np.finfo(float).eps) * mac
        if sapma > tolerans:
            notes.append(
                'fin MAC could not be preserved exactly; area and span '
                'preserved with a triangular planform (target MAC '
                f'{mac:.6g} m, achieved {mac_trapez:.6g} m, '
                f'relative deviation {sapma / mac:.3g})')
    # Süpürme: uç hücum kenarı x konumu (en yüksek y'deki en küçük x)
    tip_candidates = [x for x, y in points if abs(y - span) <= 1e-9]
    sweep = min(tip_candidates) if tip_candidates else 0.0
    return {'root': root, 'tip': tip, 'span': span, 'sweep': sweep,
            'area': area, 'mac': mac, 'notes': notes}


# ---------------------------------------------------------------------------
# Yapısal kütle tahminleri (dosyadaki yoğunlukla; yoksa tahmin YOK)
# ---------------------------------------------------------------------------
def _mass_not_estimated_warning(tag, name, note):
    """Kütlesi tahmin edilemeyen bileşenin uyarı cümlesi — TEK tanım noktası.

    ÖH D33 / OH-UC-10. ÖLÇÜLDÜ (``docs/scofield/raw/OH/D33/ihracat/a1/
    once.json`` K3, taban ``56f88e70``): AYNI cümle iki ayrı f-string
    bloğunda yazılıydı (kanat dalı ve gövde/dış bileşen dalı) ve gerileme
    kilidi (``P9B5-17``,
    ``tests/test_d23_ihracat_a1.py::TestP9B5_17MalzemeYogunluguEksik``) ile
    ``tests/test_z5s_ice_aktarma_kapilari.py``\'nin kilidi YALNIZ dış
    bileşen dalını tutuyordu ('Body' / 'Burun'). Kanat dalı bekçisizdi:
    orada cümlenin sessizce değişmesi ya da düşmesi kimseyi kırmızıya
    çevirmiyordu. İki dal artık aynı cümleyi BURADAN alır.

    ``skipped`` listesine GİRMEZ: bileşenin geometrisi aero eşlemesine
    girdi, yalnız kütlesi tahmin edilemedi (P16B4-05 mapped/skipped
    çelişkisi). Boşluk ``warnings`` kanalından bildirilir.
    """
    return (f"{tag} '{name}': mass could not be estimated ({note}); the "
            'component is absent from the mass list while its geometry is '
            'used for the aero mapping.')


def _estimate_structural_mass(tag, elem, geometry):
    """Geometri × dosya yoğunluğu kütle tahmini.

    Dönen: (mass_kg, yöntem_notu) ya da (None, atlama_nedeni).

    Kapı: yoğunluk yoksa tahmin yapılmaz; yoğunluk VAR ama fizik-dışıysa
    (<= 0) gerekçe bunu ADIYLA söyler — eskiden "dosyada yoğunluk yok"
    deniyordu, yani ret doğruyken gerekçe yanlış alanı suçluyordu
    (P16B4-05). Sonuç kütlesi sonlu ve pozitif olmak zorundadır: negatif
    geometri girdisi kütle bütçesine negatif bileşen sokamaz (P16B4-03).
    """
    density = _material_bulk_density(elem)
    if density is None:
        return None, ('no bulk material density in file; mass not '
                      'estimated (no fabricated defaults)')
    if density <= 0:
        return None, (f'material bulk density in file is {density:g} kg/m3, '
                      'which is not physical; mass not estimated')
    for key in ('radius', 'length', 'fore_radius', 'aft_radius',
                'panel_area'):
        value = geometry.get(key)
        if value is not None and (not np.isfinite(value) or value < 0):
            return None, (f'{key} in file is {value:g}, which is not '
                          'physical; mass not estimated')
    thickness = _child_float(elem, 'thickness')
    if thickness is not None and thickness < 0:
        return None, (f'thickness in file is {thickness:g} m, which is not '
                      'physical; mass not estimated')
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
    mass = float(volume * density)
    if not np.isfinite(mass) or mass <= 0.0:
        return None, (f'the geometry x density estimate evaluates to '
                      f'{mass:g} kg, which is not a usable mass; mass not '
                      'estimated')
    return mass, method


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
        return motor_file.error_result(
            'not_bytes', 'ORK content must be provided as bytes.')
    data = bytes(data)
    if not data:
        return motor_file.error_result(
            'empty_file', 'The uploaded .ork file is empty.')

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
            return motor_file.error_result('gzip_bomb', str(exc))
    else:
        xml_bytes = data

    guvenlik_reddi = _xml_guvenlik_denetimi(xml_bytes)
    if guvenlik_reddi is not None:
        return motor_file.error_result('xml_security', guvenlik_reddi)
    try:
        root = _guvenli_xml_ayristir(xml_bytes)
    except ET.ParseError as exc:
        return motor_file.error_result('invalid_xml',
                                       f'Invalid XML in .ork file: {exc}')
    except ValueError as exc:
        # defusedxml'in DTD/varlık/harici başvuru reddi ValueError türevidir
        # (DefusedXmlException). Bekçi zaten yakalamış olmalı; bu dal
        # ayrıştırıcının son sözünü kullanıcıya aynı mesajla iletir.
        if type(exc).__module__.startswith('defusedxml'):
            return motor_file.error_result('xml_security',
                                           _XML_RED_MESAJI)
        return motor_file.error_result('invalid_xml',
                                       f'Invalid XML in .ork file: {exc}')
    if root.tag != 'openrocket':
        return motor_file.error_result('not_openrocket', (
            'Not an OpenRocket design file (root element is '
            f'<{root.tag}>, expected <openrocket>).'))
    rocket = root.find('rocket')
    if rocket is None:
        return motor_file.error_result(
            'no_rocket_element',
            'The file contains no <rocket> definition.')
    stages = rocket.findall('./subcomponents/stage')
    if not stages:
        return motor_file.error_result('no_stages',
                                       'The rocket has no stages.')
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
        return motor_file.error_result(
            'no_stage_components',
            'The sustainer stage has no components.')
    for elem in stage_children:
        tag = elem.tag
        if tag in ('nosecone', 'bodytube', 'transition'):
            name = _component_name(elem, tag)
            length, length_error = _component_length(elem, 'length', tag,
                                                     name, warnings)
            if length_error is not None:
                return length_error
            externals.append({
                'elem': elem, 'tag': tag, 'start': running_x,
                'length': length,
                'name': name,
            })
            running_x += length
        elif tag in _SKIP_TAGS:
            skipped.append(f"{tag} '{_component_name(elem, tag)}': "
                           'not part of the HRMA aero/mass mapping')
        else:
            skipped.append(f"{tag} '{_component_name(elem, tag)}': "
                           'unrecognized component type')
    if not externals:
        return motor_file.error_result(
            'no_axial_components',
            'No axial components (nose cone / body tube) found in the '
            'sustainer stage.')
    body_length = running_x

    # --- Yarıçap çözümü ('auto' değerler komşudan) ---
    for ext in externals:
        elem, tag = ext['elem'], ext['tag']
        if tag == 'nosecone':
            ext['fore_radius'] = 0.0
            ext['aft_radius'] = _child_float(elem, 'aftradius')
            ext['radius_fields'] = {'fore_radius': None,
                                    'aft_radius': 'aftradius'}
        elif tag == 'bodytube':
            radius = _child_float(elem, 'radius')
            ext['fore_radius'] = radius
            ext['aft_radius'] = radius
            # Gövde tüpünde iki yarıçap da TEK alandan gelir: mesaj
            # dosyanın gerçekten taşıdığı etiketi suçlamalı.
            ext['radius_fields'] = {'fore_radius': 'radius',
                                    'aft_radius': 'radius'}
        else:  # transition
            ext['fore_radius'] = _child_float(elem, 'foreradius')
            ext['aft_radius'] = _child_float(elem, 'aftradius')
            ext['radius_fields'] = {'fore_radius': 'foreradius',
                                    'aft_radius': 'aftradius'}
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

    # P9B5-16: yarıçaplar çözüldü; aero eşlemesine girmeden ÖNCE fiziksel
    # zarftan geçerler (uzunluk kapısının simetriği).
    radius_error = _check_component_radius(externals)
    if radius_error is not None:
        return radius_error

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
                # ÖH D23 / defter P9B5-26 — EKSİK ``tipchord`` ARTIK
                # SESSİZCE 0 OLMUYOR.
                #
                # ÖLÇÜLDÜ (taban ``ef527ae``, ``once.json`` bölümü P9B5-26;
                # 3 kanat, kök 0,20 m, uç 0,10 m, açıklık 0,10 m, kalınlık
                # 3 mm, ρ = 1850 kg/m³):
                #
                #     tipchord VAR  -> toplam kütle 1,115909 kg
                #     tipchord YOK  -> toplam kütle 1,032659 kg  (-%7,46)
                #     warnings      -> ['nosecone ... nose_type left unset.']
                #
                # Yani planform alanını doğrudan belirleyen bir ölçü dosyada
                # yokken ``tip_chord = 0.0`` UYDURULUYOR, kanat kütlesi
                # düşüyor ve ``warnings`` bunu HİÇ anmıyordu (kalemde ölçülen
                # gerçek kanat kaybı -%33). Kardeş alan ``sweeplength``
                # eksikken DOĞRU davranıyor: uydurmuyor, alanı boş bırakıyor
                # ve uyarıyor.
                #
                # ``tipchord`` ``sweeplength``ten farklıdır: yamuk alanının
                # (b·(c_r+c_t)/2) İKİ zorunlu ölçüsünden biridir, isteğe bağlı
                # bir yerleşim parametresi değil. OpenRocket ucu sivri kanadı
                # da ``<tipchord>0.0</tipchord>`` yazarak AÇIKÇA bildirir;
                # etiketin YOKLUĞU "sivri kanat" demek değil, ölçünün
                # bilinmediği demektir. Bu yüzden kalan zorunlu ölçülerle
                # (``rootchord``, ``height``, ``fincount``) AYNI kapıya
                # bağlandı: sayı uydurulmaz, kanat takımı atlanır ve
                # gerekçesi adıyla bildirilir (fail-closed).
                if None in (root_chord, tip_chord, span) or not count:
                    _eksik = [ad for ad, deger in
                              (('rootchord', root_chord),
                               ('tipchord', tip_chord),
                               ('height', span),
                               ('fincount', count or None))
                              if deger is None]
                    _detay = (' (missing: ' + ', '.join(_eksik) + ')'
                              if _eksik else '')
                    warnings.append(f"finset '{name}': incomplete geometry"
                                    f'{_detay}; skipped. No substitute '
                                    'dimension is invented.')
                    skipped.append(f"trapezoidfinset '{name}': incomplete "
                                   f'geometry{_detay}')
                    continue
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
                # 'skipped' YALNIZ içe aktarılmayan bileşen içindir; bu
                # kanat aero eşlemesine girdi, yalnız kütlesi tahmin
                # edilemedi. Boşluk warnings kanalından bildirilir
                # (P16B4-05 mapped/skipped çelişkisi).
                warnings.append(
                    _mass_not_estimated_warning(elem.tag, name, note))
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
            # Bileşen 'skipped' DEĞİL: geometrisi aero eşlemesine girdi,
            # yalnız kütlesi tahmin edilemedi (P16B4-05).
            warnings.append(
                _mass_not_estimated_warning(ext['tag'], ext['name'], note))
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
            raw_mass = elem.findtext('mass')
            mass_text = '' if raw_mass is None else str(raw_mass).strip()
            mass = _to_float(mass_text)
            if mass is None:
                # Gerekçe alanın gerçek durumunu söyler: alan yok mu, yoksa
                # var ama sonlu sayı değil mi (NaN/inf/metin).
                reason = ('no mass value' if not mass_text
                          else f"mass value '{mass_text[:40]}' is not a "
                               'finite number')
                warnings.append(f"mass component '{name}': {reason}; "
                                'skipped.')
                skipped.append(f"masscomponent '{name}': {reason}")
                continue
            if mass < 0:
                return motor_file.error_result(
                    'unphysical_component_mass',
                    f"mass component '{name}': <mass> is {mass:g} kg. "
                    'Component masses must be non-negative; the file is '
                    'rejected instead of importing a negative mass into the '
                    'budget.')
            # packedlength yoksa uyarı üretilmez: extent'i olmayan bir nokta
            # kütle biçim gereği geçerlidir (0 m uydurma değil, tanım).
            length, length_error = _component_length(
                elem, 'packedlength', 'mass component', name, warnings,
                warn_missing=False)
            if length_error is not None:
                return length_error
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
