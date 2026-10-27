"""
HRMA proje kaydet/yükle deposu (dosya tabanlı).

Projeler kullanıcının belgeler dizini altında saklanır:
  - Varsayılan: ~/Documents/HRMA/projects (Documents yoksa ~/HRMA/projects)
  - Ortam değişkeni HRMA_PROJECTS_DIR ile değiştirilebilir (test için).

Her proje tek bir "<ad>.hrma" JSON dosyasıdır. Yazma atomiktir
(tempfile + os.replace — hrma/data/offline_store.py deseni). Silme kalıcı
değildir: dosya projects_dir/.trash/ altına zaman damgasıyla taşınır.

Güvenlik:
  - Proje adı beyaz listeyle sınırlıdır: [A-Za-z0-9 _.-], 1-80 karakter,
    nokta ile başlayamaz, nokta/boşluk ile bitemez (Windows uyumu),
    Windows ayrılmış adları (CON, NUL, ...) reddedilir.
  - Çözülen gerçek yol (realpath) projects_dir dışına çıkıyorsa
    (ör. dizine bırakılmış sembolik bağ) işlem reddedilir.

Uydurma-veri-yasağı: eksik alanlar SESSİZCE doldurulmaz. Şema doğrulaması
kaydetme sırasında yapılır; yükleme sırasında dosya şemaya uymuyorsa hata
verilir, sunucu tarafında yalnızca damga alanları (app_version, created_at,
updated_at, name) yazılır ve bunlar veri değil üstveridir.
"""

import json
import math
import os
import re
import tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from hrma import __version__ as APP_VERSION
# Motor türleri TEK KAYNAKTAN gelir (hrma/constants.py). Bu dosyadaki üç
# kullanım da ÜYELİK sorar ('in' / sorted()), o yüzden merkezde demetten
# TÜRETİLEN küme biçimi alınır. Takma adla içe aktarılıyor ki modül düzeyinde
# ikinci bir atama satırı olmasın: 'MOTOR_TYPES = MOTOR_TYPE_SET' yazmak
# tutarlılık kancasına (check-consistency) yalancı "farklı değer" alarmı
# verdiriyordu — ölçüldü. Bekçi: tests/test_sabit_tek_kaynak.py (kimlik).
from hrma.constants import MOTOR_TYPE_SET as MOTOR_TYPES

# --- Sabitler ---------------------------------------------------------------

FILE_EXT = '.hrma'
TRASH_DIRNAME = '.trash'

# Tek proje dosyası için üst sınır (ARGE raporu: 1 MB)
MAX_PROJECT_BYTES = 1024 * 1024

# Ad kuralı: İngilizce ve Türkçe harfler, rakam, boşluk, _ . - ; 1-80 karakter
# (nokta ile başlama ayrıca denetlenir). v3.0.1 (NK-51, son kullanıcı testi):
# kural metni "harf" diyordu ama "Şimşek-1" reddediliyordu. Yalnız önceden
# birleşik (NFC) Türkçe harfler eklendi; birleştirici işaretli (NFD) yazım,
# öteki alfabeler ve görünmez karakterler reddedilir (benzer görünen ad
# hilesine kapı açılmaz). İstemci aynası: hrma/static/js/project_bar.js
# NAME_RE (tests/test_project_ui_contract.py iki sınıfı karşılaştırır).
NAME_MAX_LEN = 80
_NAME_CHARS = 'A-Za-z0-9çğıöşüÇĞİÖŞÜ _.\\-'
_NAME_RE = re.compile('^[' + _NAME_CHARS + ']{1,80}$')
_NAME_CHAR_RE = re.compile('[' + _NAME_CHARS + ']')

# Windows'ta dosya adı olarak kullanılamayan ayrılmış adlar
_WINDOWS_RESERVED = frozenset(
    ['CON', 'PRN', 'AUX', 'NUL']
    + [f'COM{i}' for i in range(1, 10)]
    + [f'LPT{i}' for i in range(1, 10)]
)

PROJECT_FORMAT_TAG = 'hrma-project'
PROJECT_FORMAT_VERSION = 1
# MOTOR_TYPES burada TANIMLI DEĞİLDİR — yukarıda hrma.constants'tan takma adla
# içe aktarılır (tek tanım noktası).

# Kaydedilen belgede izin verilen üst seviye anahtarlar.
# Damga alanları (app_version, created_at, updated_at) istemciden gelirse
# kabul edilir (yükle->kaydet gidiş-dönüşü için) ama sunucu tarafından ezilir.
_ALLOWED_TOP_KEYS = frozenset([
    'format', 'format_version', 'name', 'description', 'motor_type',
    'inputs', 'results_summary', 'app_version', 'created_at', 'updated_at',
])
_ALLOWED_INPUT_KEYS = frozenset(
    ['fields', 'dynamic', 'ui_state', 'dock_overrides', 'airframe'])


# --- Hata sınıfları ---------------------------------------------------------

class ProjectError(Exception):
    """Proje deposu hatalarının ortak atası."""


class ProjectNameError(ProjectError):
    """Geçersiz veya güvensiz proje adı."""


class ProjectValidationError(ProjectError):
    """Şema doğrulaması başarısız (istemci hatası)."""


class ProjectNotFoundError(ProjectError):
    """İstenen proje mevcut değil."""


class ProjectExistsError(ProjectError):
    """Aynı adla proje zaten var (overwrite bayrağı gerekli)."""


class ProjectTooLargeError(ProjectError):
    """Proje belgesi boyut sınırını aşıyor."""


class ProjectCorruptError(ProjectError):
    """Diskteki proje dosyası okunamıyor / şemaya uymuyor."""


# --- Dizin çözümü -----------------------------------------------------------

def projects_dir() -> str:
    """Proje dosyalarının saklandığı dizin (yoksa oluşturulur).

    Öncelik: HRMA_PROJECTS_DIR ortam değişkeni > ~/Documents/HRMA/projects
    (Documents dizini varsa) > ~/HRMA/projects.
    """
    override = os.environ.get('HRMA_PROJECTS_DIR')
    if override:
        path = override
    else:
        home = os.path.expanduser('~')
        documents = os.path.join(home, 'Documents')
        if os.path.isdir(documents):
            path = os.path.join(documents, 'HRMA', 'projects')
        else:
            path = os.path.join(home, 'HRMA', 'projects')
    os.makedirs(path, exist_ok=True)
    return path


def _trash_dir() -> str:
    """Silinen projelerin taşındığı çöp dizini (yoksa oluşturulur)."""
    path = os.path.join(projects_dir(), TRASH_DIRNAME)
    os.makedirs(path, exist_ok=True)
    return path


# --- Örnek proje tohumlama --------------------------------------------------

#: Tohumlama damga dosyası. Nokta ile başlar: list_projects() dot-dosyaları
#: zaten atlıyor, damga hiçbir listede proje olarak görünmez. Sürüm eki
#: bilinçli: ilerde örnek seti köklü değişirse .seeded_v2 ile bir kez daha
#: (yine ezmeden) tohumlanabilir.
SEED_STAMP_FILENAME = '.seeded_v1'


def _package_dir() -> str:
    """hrma paket dizini (…/hrma). Testler bunu monkeypatch'ler."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def examples_source_dir() -> Optional[str]:
    """Paketle gelen örnek .hrma projelerinin dizini; yoksa None.

    Öncelik: HRMA_EXAMPLES_DIR ortam değişkeni (test/tanılama) > paket
    kökünün YANINDAKİ examples/ dizini. "Paket kökünün yanı" desteklenen
    her yerleşimde aynı yere düşer (self_install.py yerleşim şeması):

      - geliştirme (git deposu): <depo>/hrma        → <depo>/examples
      - paketli macOS: …/Contents/Resources/app/hrma → …/Resources/app/examples
      - paketli Windows: <INSTDIR>/app/hrma          → <INSTDIR>/app/examples

    Dizin gerçekten yoksa None döner — uydurulmuş bir yol döndürülmez,
    tohumlama açıkça 'no_source' bildirir.
    """
    override = os.environ.get('HRMA_EXAMPLES_DIR')
    if override:
        return override if os.path.isdir(override) else None
    candidate = os.path.join(os.path.dirname(_package_dir()), 'examples')
    return candidate if os.path.isdir(candidate) else None


def seed_examples() -> Dict:
    """Paket örneklerini kullanıcı proje dizinine BİR KEZ tohumla.

    Kurallar (v2.6.26 bakım dalgası):
      * Damga dosyası (SEED_STAMP_FILENAME) varsa HİÇBİR şey yapılmaz —
        kullanıcı örnekleri sildiyse her açılışta geri gelmezler.
      * Var olan dosya ASLA ezilmez (kullanıcı aynı adla kendi projesini
        kaydetmiş olabilir); atlanan dosyalar dönüşte beyan edilir.
      * Ad kuralına uymayan kaynak dosyalar kopyalanmaz (kopyalansalar
        list_projects onları 'unloadable' işaretlerdi) ve beyan edilir.
      * Kopyalama atomiktir (tempfile + os.replace — _atomic_write_json
        deseni); yarım dosya proje dizinine hiçbir koşulda düşmez.

    Dönüş: {'status': 'seeded'|'already_seeded'|'no_source',
            'copied': [...], 'skipped_existing': [...],
            'skipped_invalid': [...], 'source_dir': str|None}
    """
    dest = projects_dir()
    stamp_path = os.path.join(dest, SEED_STAMP_FILENAME)
    result: Dict[str, Any] = {
        'copied': [], 'skipped_existing': [], 'skipped_invalid': [],
        'source_dir': None,
    }
    if os.path.exists(stamp_path):
        result['status'] = 'already_seeded'
        return result

    source = examples_source_dir()
    result['source_dir'] = source
    if source is None:
        result['status'] = 'no_source'
        return result
    try:
        filenames = sorted(os.listdir(source))
    except OSError:
        result['status'] = 'no_source'
        return result

    for filename in filenames:
        if filename.startswith('.') or not filename.endswith(FILE_EXT):
            continue
        stem = filename[:-len(FILE_EXT)]
        try:
            validate_name(stem)
        except ProjectNameError:
            result['skipped_invalid'].append(filename)
            continue
        target = os.path.join(dest, filename)
        if os.path.exists(target):
            result['skipped_existing'].append(filename)
            continue
        with open(os.path.join(source, filename), 'rb') as f:
            blob = f.read()
        fd, tmp_path = tempfile.mkstemp(
            prefix='.hrma_seed_', suffix='.tmp', dir=dest)
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(blob)
            os.replace(tmp_path, target)  # atomik: tmp + rename
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        result['copied'].append(filename)

    # Damga, kopyalama BİTİNCE yazılır: yarıda kesilen tohumlama bir sonraki
    # açılışta (yine ezmeden) tamamlanır. Hiç dosya kopyalanmamış olsa bile
    # yazılır — hepsi zaten vardıysa da tohumlama "yapılmış" sayılır.
    _atomic_write_json(stamp_path, {
        'seeded_at': datetime.now().isoformat(timespec='seconds'),
        'app_version': APP_VERSION,
        'source_dir': source,
        'copied': result['copied'],
        'skipped_existing': result['skipped_existing'],
        'skipped_invalid': result['skipped_invalid'],
    })
    result['status'] = 'seeded'
    return result


# --- Eski örnek kopyalarının tazelenmesi (v3.0.1) ---------------------------
# ÖLÇÜLDÜ (26 Eki 2026, geliştirme makinesi): tohumlama örnekleri kullanıcı
# dizinine BİR KEZ kopyalar (.seeded_v1) ve sonra hiç güncellemez. Dizindeki
# üç örnek 796a56aab (2.6.27) sürümündeydi; katı örnek eski "tek çap"
# anlamıyla chamber_diameter = outer_diameter = 75 mm taşıyordu ve 3.0.1'in
# kasa kapısında 422 alıyordu ("kasa iç çapı 75 mm … en az 85,0 mm") —
# 3.0.0'dan yükselten her kullanıcı örneği açınca hata görecekti.
#
# Kural: kullanıcı dizinindeki örnek, paketle DAĞITILMIŞ bir örnek
# sürümüyle BAYT BAYT aynıysa (kullanıcı hiç değiştirmemiş) güncel sürümle
# atomik olarak değiştirilir. Değiştirilmiş kopyaya DOKUNULMAZ (kullanıcının
# işi ezilmez); kullanıcının sildiği örnek geri GETİRİLMEZ. Her sürüm bir
# kez çalışır (damga: EXAMPLE_REFRESH_STAMP_FILENAME, app_version alanı).
# Dağıtılmış sürümlerin karmaları paketle gelir:
# examples/SHIPPED_EXAMPLE_HASHES_FILENAME (git geçmişinden üretildi;
# examples/generate_examples.py her üretimde yeni sürümü ekler).

#: Tazeleme damgası (nokta dosyası: list_projects onu proje saymaz).
EXAMPLE_REFRESH_STAMP_FILENAME = '.examples_refresh.json'
#: Paketle gelen "dağıtılmış örnek sürümleri" karma dosyası (examples/ içinde;
#: .hrma olmadığı için tohumlama onu kopyalamaz).
SHIPPED_EXAMPLE_HASHES_FILENAME = 'shipped_example_hashes.json'


def _sha256_of_file(path: str) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for blok in iter(lambda: f.read(65536), b''):
            h.update(blok)
    return h.hexdigest()


def _shipped_example_hashes(source: str) -> Dict[str, set]:
    """examples/ yanındaki karma dosyası: {dosya adı: {sha256, ...}}.

    Dosya yoksa ya da okunamıyorsa BOŞ sözlük döner — hiçbir kopya
    "dağıtılmış sürüm" sayılmaz, yani hiçbir şey ezilmez (fail-closed).
    """
    try:
        with open(os.path.join(source, SHIPPED_EXAMPLE_HASHES_FILENAME),
                  'r', encoding='utf-8') as f:
            belge = json.load(f)
    except (OSError, ValueError):
        return {}
    karmalar = belge.get('hashes') if isinstance(belge, dict) else None
    if not isinstance(karmalar, dict):
        return {}
    return {ad: {h for h in liste if isinstance(h, str)}
            for ad, liste in karmalar.items() if isinstance(liste, list)}


def refresh_seeded_examples() -> Dict:
    """Kullanıcının DEĞİŞTİRMEDİĞİ eski örnek kopyalarını güncel sürümle değiştir.

    Dönüş: {'status': 'refreshed'|'already_refreshed'|'not_seeded'|'no_source',
            'refreshed': [...], 'kept_modified': [...], 'up_to_date': [...],
            'skipped_missing': [...], 'source_dir': str|None}
    """
    dest = projects_dir()
    result: Dict[str, Any] = {
        'refreshed': [], 'kept_modified': [], 'up_to_date': [],
        'skipped_missing': [], 'source_dir': None,
    }
    # Hiç tohumlanmamış dizin seed_examples'ın işidir (ilk kurulum).
    if not os.path.exists(os.path.join(dest, SEED_STAMP_FILENAME)):
        result['status'] = 'not_seeded'
        return result
    stamp_path = os.path.join(dest, EXAMPLE_REFRESH_STAMP_FILENAME)
    try:
        with open(stamp_path, 'r', encoding='utf-8') as f:
            onceki = json.load(f)
        if not isinstance(onceki, dict):
            onceki = {}
    except (OSError, ValueError):
        onceki = {}
    if onceki.get('app_version') == APP_VERSION:
        result['status'] = 'already_refreshed'
        return result

    source = examples_source_dir()
    result['source_dir'] = source
    if source is None:
        result['status'] = 'no_source'
        return result
    dagitilmis = _shipped_example_hashes(source)
    onceki_yazilan = onceki.get('written') if isinstance(
        onceki.get('written'), dict) else {}
    yazilan: Dict[str, str] = {}
    try:
        filenames = sorted(os.listdir(source))
    except OSError:
        result['status'] = 'no_source'
        return result

    for filename in filenames:
        if filename.startswith('.') or not filename.endswith(FILE_EXT):
            continue
        try:
            validate_name(filename[:-len(FILE_EXT)])
        except ProjectNameError:
            continue
        kaynak = os.path.join(source, filename)
        hedef = os.path.join(dest, filename)
        guncel = _sha256_of_file(kaynak)
        if not os.path.exists(hedef):
            # Kullanıcı silmiş: geri getirilmez.
            result['skipped_missing'].append(filename)
            continue
        mevcut = _sha256_of_file(hedef)
        if mevcut == guncel:
            result['up_to_date'].append(filename)
            yazilan[filename] = guncel
            continue
        bilinen = set(dagitilmis.get(filename, set()))
        if isinstance(onceki_yazilan.get(filename), str):
            bilinen.add(onceki_yazilan[filename])
        if mevcut not in bilinen:
            # Kullanıcı değiştirmiş (ya da bilinmeyen bir sürüm): dokunma.
            result['kept_modified'].append(filename)
            continue
        with open(kaynak, 'rb') as f:
            blob = f.read()
        fd, tmp_path = tempfile.mkstemp(
            prefix='.hrma_seed_', suffix='.tmp', dir=dest)
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(blob)
            os.replace(tmp_path, hedef)  # atomik: tmp + rename
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        result['refreshed'].append(filename)
        yazilan[filename] = guncel

    _atomic_write_json(stamp_path, {
        'refreshed_at': datetime.now().isoformat(timespec='seconds'),
        'app_version': APP_VERSION,
        'source_dir': source,
        'refreshed': result['refreshed'],
        'kept_modified': result['kept_modified'],
        'skipped_missing': result['skipped_missing'],
        'written': yazilan,
    })
    result['status'] = 'refreshed'
    return result


# --- Ad ve yol denetimi -----------------------------------------------------

def validate_name(name: Any) -> str:
    """Proje adını beyaz listeyle doğrula; geçerliyse adı döndür."""
    if not isinstance(name, str):
        raise ProjectNameError('Project name must be a string')
    if not _NAME_RE.match(name):
        # Hangi karakterin sorun olduğu söylenir (NK-51); repr görünmez
        # karakterleri de (\u200b vb.) okunur kılar.
        yasak = sorted({ch for ch in name if not _NAME_CHAR_RE.match(ch)})
        ek = f' (not allowed: {"".join(yasak)!r})' if yasak else ''
        raise ProjectNameError(
            'Invalid project name: only letters (A-Z and Turkish '
            'ç ğ ı İ ö ş ü), digits, space, underscore, dot and hyphen are '
            f'allowed (1-{NAME_MAX_LEN} characters){ek}')
    if name.startswith('.'):
        raise ProjectNameError('Project name must not start with a dot')
    if name.endswith('.') or name.endswith(' '):
        raise ProjectNameError('Project name must not end with a dot or space')
    stem = name.split('.', 1)[0].rstrip(' ')
    if stem.upper() in _WINDOWS_RESERVED:
        raise ProjectNameError('Project name is a reserved device name')
    return name


def _project_path(name: str) -> str:
    """Ad -> tam dosya yolu; realpath kapsama denetimiyle.

    Çözülen gerçek yol projects_dir altında ve doğrudan onun içinde
    değilse (sembolik bağ kaçışı vb.) reddedilir.
    """
    validate_name(name)
    base = os.path.realpath(projects_dir())
    path = os.path.join(base, name + FILE_EXT)
    real = os.path.realpath(path)
    if os.path.dirname(real) != base or not os.path.basename(real).endswith(FILE_EXT):
        raise ProjectNameError('Project path escapes the projects directory')
    return path


# --- Şema doğrulama ---------------------------------------------------------

_SCALAR_TYPES = (str, int, float, bool)


def _is_finite_number(value: Any) -> bool:
    """Sayı sonlu mu? (NaN/Infinity JSON'a güvenle yazılamaz)."""
    if isinstance(value, bool):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    return True


def _validate_json_tree(value: Any, path: str, depth: int = 0) -> None:
    """Ağacın yalnızca JSON-yerli, sonlu değerler içerdiğini doğrula."""
    if depth > 16:
        raise ProjectValidationError(f'{path}: nesting too deep')
    if value is None or isinstance(value, _SCALAR_TYPES):
        if not _is_finite_number(value):
            raise ProjectValidationError(f'{path}: non-finite number is not allowed')
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ProjectValidationError(f'{path}: object keys must be strings')
            _validate_json_tree(item, f'{path}.{key}', depth + 1)
        return
    if isinstance(value, list):
        for i, item in enumerate(value):
            _validate_json_tree(item, f'{path}[{i}]', depth + 1)
        return
    raise ProjectValidationError(
        f'{path}: unsupported value type {type(value).__name__}')


def _validate_fields(fields: Any) -> None:
    """inputs.fields: düz sözlük — değerler yalnız str/num/bool.

    İç içe nesne/liste ve None reddedilir (uydurma-veri-yasağı: boş değer
    sessizce saklanmaz, istemci alanı hiç göndermemelidir).
    """
    if not isinstance(fields, dict):
        raise ProjectValidationError('payload.inputs.fields must be an object')
    for key, value in fields.items():
        if not isinstance(key, str) or not key:
            raise ProjectValidationError(
                'payload.inputs.fields keys must be non-empty strings')
        if value is None or not isinstance(value, _SCALAR_TYPES):
            raise ProjectValidationError(
                f'payload.inputs.fields.{key}: value must be a string, '
                'number or boolean (nested objects are not allowed)')
        if not _is_finite_number(value):
            raise ProjectValidationError(
                f'payload.inputs.fields.{key}: non-finite number is not allowed')


def _validate_airframe(airframe: Any) -> None:
    """inputs.airframe: uçan-araç gövde/kanat parametreleri — düz skaler sözlük.

    _validate_fields ile AYNI kural (uydurma-veri-yasağı): değerler yalnız
    str/num/bool; iç içe nesne/liste ve None reddedilir. Bu alan launch_site
    airframe panelinin (gövde çapı/boyu, burun, kanatlar, cd0, fırlatma
    açıları, rüzgar, latitude vb.) .hrma içine gidiş-dönüşünü sağlar.
    """
    if not isinstance(airframe, dict):
        raise ProjectValidationError('payload.inputs.airframe must be an object')
    for key, value in airframe.items():
        if not isinstance(key, str) or not key:
            raise ProjectValidationError(
                'payload.inputs.airframe keys must be non-empty strings')
        if value is None or not isinstance(value, _SCALAR_TYPES):
            raise ProjectValidationError(
                f'payload.inputs.airframe.{key}: value must be a string, '
                'number or boolean (nested objects are not allowed)')
        if not _is_finite_number(value):
            raise ProjectValidationError(
                f'payload.inputs.airframe.{key}: non-finite number is not allowed')


def _validate_results_summary(summary: Any) -> None:
    """results_summary: düz sözlük, skaler değerler (özet amaçlı)."""
    if not isinstance(summary, dict):
        raise ProjectValidationError('payload.results_summary must be an object')
    for key, value in summary.items():
        if not isinstance(key, str) or not key:
            raise ProjectValidationError(
                'payload.results_summary keys must be non-empty strings')
        if value is not None and not isinstance(value, _SCALAR_TYPES):
            raise ProjectValidationError(
                f'payload.results_summary.{key}: value must be a scalar')
        if not _is_finite_number(value):
            raise ProjectValidationError(
                f'payload.results_summary.{key}: non-finite number is not allowed')


def validate_payload(payload: Any) -> None:
    """İstemciden gelen proje yükünü şemaya göre doğrula.

    Zorunlu: format=="hrma-project", format_version==1,
    motor_type in {hybrid, solid, liquid}, inputs.fields (düz sözlük).
    Opsiyonel: name, description, inputs.dynamic, inputs.ui_state,
    inputs.dock_overrides, inputs.airframe (uçan-araç panosu), results_summary.
    """
    if not isinstance(payload, dict):
        raise ProjectValidationError('payload must be a JSON object')

    unknown = sorted(set(payload.keys()) - _ALLOWED_TOP_KEYS)
    if unknown:
        raise ProjectValidationError(
            f"payload contains unknown keys: {', '.join(unknown)}")

    if payload.get('format') != PROJECT_FORMAT_TAG:
        raise ProjectValidationError(
            f"payload.format must be '{PROJECT_FORMAT_TAG}'")
    version = payload.get('format_version')
    if isinstance(version, bool) or version != PROJECT_FORMAT_VERSION:
        raise ProjectValidationError(
            f'payload.format_version must be {PROJECT_FORMAT_VERSION}')
    motor_type = payload.get('motor_type')
    if motor_type not in MOTOR_TYPES:
        raise ProjectValidationError(
            "payload.motor_type must be one of: " + ', '.join(sorted(MOTOR_TYPES)))

    for key in ('name', 'description'):
        if key in payload and not isinstance(payload[key], str):
            raise ProjectValidationError(f'payload.{key} must be a string')

    inputs = payload.get('inputs')
    if not isinstance(inputs, dict):
        raise ProjectValidationError('payload.inputs must be an object')
    unknown_inputs = sorted(set(inputs.keys()) - _ALLOWED_INPUT_KEYS)
    if unknown_inputs:
        raise ProjectValidationError(
            f"payload.inputs contains unknown keys: {', '.join(unknown_inputs)}")
    if 'fields' not in inputs:
        raise ProjectValidationError('payload.inputs.fields is required')
    _validate_fields(inputs['fields'])

    if 'dynamic' in inputs:
        if not isinstance(inputs['dynamic'], (dict, list)):
            raise ProjectValidationError(
                'payload.inputs.dynamic must be an object or array')
        _validate_json_tree(inputs['dynamic'], 'payload.inputs.dynamic')
    for key in ('ui_state', 'dock_overrides'):
        if key in inputs:
            if not isinstance(inputs[key], dict):
                raise ProjectValidationError(f'payload.inputs.{key} must be an object')
            _validate_json_tree(inputs[key], f'payload.inputs.{key}')

    if 'airframe' in inputs:
        _validate_airframe(inputs['airframe'])

    if 'results_summary' in payload:
        _validate_results_summary(payload['results_summary'])


# --- Okuma yardımcıları -----------------------------------------------------

def _read_project_file(path: str) -> Dict:
    """Diskteki proje dosyasını oku; bozuksa ProjectCorruptError."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            doc = json.load(f)
    except ValueError as e:
        raise ProjectCorruptError(f'Project file is not valid JSON: {e}')
    except OSError as e:
        raise ProjectCorruptError(f'Project file cannot be read: {e}')
    if not isinstance(doc, dict):
        raise ProjectCorruptError('Project file root must be a JSON object')
    return doc


def _atomic_write_json(path: str, doc: Dict) -> None:
    """JSON belgesini tempfile + os.replace ile atomik yaz."""
    directory = os.path.dirname(path)
    fd, tmp_path = tempfile.mkstemp(prefix='.hrma_project_', suffix='.tmp', dir=directory)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(doc, f, ensure_ascii=False, indent=1, allow_nan=False)
        os.replace(tmp_path, path)  # atomik: tmp + rename
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# --- Genel API --------------------------------------------------------------

def save_project(name: str, payload: Dict, overwrite: bool = False) -> Dict:
    """Projeyi doğrula, damgala ve atomik olarak diske yaz.

    Dönen sözlük: name, created_at, updated_at, app_version, motor_type.
    Aynı ad varsa ve overwrite False ise ProjectExistsError yükseltilir.
    """
    path = _project_path(name)
    validate_payload(payload)

    exists = os.path.exists(path)
    if exists and not overwrite:
        raise ProjectExistsError(
            f"Project '{name}' already exists; pass overwrite=true to replace it")

    now = datetime.now().isoformat(timespec='seconds')
    created_at = now
    if exists:
        # Üzerine yazarken orijinal oluşturulma damgası korunur
        try:
            existing = _read_project_file(path)
            if isinstance(existing.get('created_at'), str):
                created_at = existing['created_at']
        except ProjectCorruptError:
            pass  # bozuk eski dosya: yeni damga ile ez

    doc = dict(payload)
    # Sunucu damgaları — istemciden gelen değerler ezilir (üstveri, veri değil)
    doc['name'] = name
    doc['app_version'] = APP_VERSION
    doc['created_at'] = created_at
    doc['updated_at'] = now

    serialized = json.dumps(doc, ensure_ascii=False, allow_nan=False)
    size = len(serialized.encode('utf-8'))
    if size > MAX_PROJECT_BYTES:
        raise ProjectTooLargeError(
            f'Project document is {size} bytes; limit is {MAX_PROJECT_BYTES} bytes (1 MB)')

    _atomic_write_json(path, doc)
    return {
        'name': name,
        'motor_type': doc['motor_type'],
        'app_version': APP_VERSION,
        'created_at': created_at,
        'updated_at': now,
    }


def load_project(name: str) -> Tuple[Dict, List[str]]:
    """Projeyi diskten oku, şemayı doğrula; (belge, warnings) döndür.

    Eksik alanlar SESSİZCE doldurulmaz: belge diskteki haliyle döner,
    yalnızca uyarı listesi eklenir (ör. farklı app_version ile kaydedilmiş).
    Tek istisna beyanlı sürüm göçüdür (v3.0.1: eski katı projede tane çapı
    anlamındaki kasa çapı boşaltılır); göç bellekteki belgeye uygulanır,
    diskteki dosya değişmez ve adlı bir uyarı kaydı eklenir.
    """
    doc, records = load_project_records(name)
    warnings = [load_warning_text(r) for r in records]
    return doc, warnings


def load_project_records(name: str) -> Tuple[Dict, List[Dict]]:
    """``load_project``ın kayıt biçimi: (belge, uyarı kayıtları).

    Uyarı metinleri (``load_project``) ve makine kayıtları (projeler API'si)
    AYNI listeden kurulur; göç kaydı ikisinde de aynı sırada durur.
    """
    path = _project_path(name)
    if not os.path.exists(path):
        raise ProjectNotFoundError(f"Project '{name}' not found")

    doc = _read_project_file(path)
    try:
        validate_payload(doc)
    except ProjectValidationError as e:
        raise ProjectCorruptError(f'Project file does not match the schema: {e}')

    records = load_warning_records(doc)
    goc = _solid_legacy_case_bore_migration(doc)
    if goc is not None:
        records.append(goc)
    return doc, records


# --------------------------------------------------------------------------
# Yükleme uyarıları — makine kodu + parametre (V3 KK 2. tur, REL D-5)
# --------------------------------------------------------------------------
# ÖLÇÜLDÜ (dal tabanı 1b4bbff7): eski sürümle kaydedilmiş proje açılınca
# uyarı YALNIZ İngilizce düz metindi; proje şeridi onu TR kipinde de
# İngilizce basıyordu. Uyarı artık sıvı motor uyarılarıyla aynı biçimde
# ``{code, params, severity}`` kaydıdır; metni arayüz i18n anahtarıyla
# kurar (EN = TR). ``load_project``ın düz metin listesi GERİYE UYUMLU kalır
# (aynı kayıtlardan, bu sözlükten kurulur; bayt-aynı).
LOAD_WARNING_APP_VERSION_MISMATCH = 'warn.project.app_version_mismatch'
LOAD_WARNING_MISSING_STAMP = 'warn.project.missing_stamp'
LOAD_WARNING_SOLID_LEGACY_CASE_BORE = 'warn.project.solid_legacy_case_bore'
#: Sunucunun İngilizce yedek metinleri (i18n_common.js 'en' ile birebir;
#: bekçi tests/test_v3_kucuk.py::TestProjeYuklemeUyarisi).
_LOAD_WARNING_TEXT_EN = {
    LOAD_WARNING_APP_VERSION_MISMATCH: (
        'Project was saved with app version {saved_version}; '
        'current version is {current_version}'),
    LOAD_WARNING_MISSING_STAMP: "Project file is missing the '{stamp}' stamp",
    LOAD_WARNING_SOLID_LEGACY_CASE_BORE: (
        'This solid project was saved with app version {saved_version}: its '
        'Chamber Diameter ({chamber_diameter_mm} mm) is not larger than the '
        'grain outer diameter ({outer_diameter_mm} mm). Versions before 3.0.1 '
        'read that field as the grain diameter; from 3.0.1 on it is the case '
        'inner diameter, which must hold the grain, liner and insulation. The '
        'field was left empty, so the case is derived from the grain, liner '
        'and insulation. Enter your own case inner diameter if you have one.'),
}

#: Katı sayfada ``chamber_diameter``ın KASA İÇ ÇAPI anlamına geçtiği sürüm
#: (V301/K-A karar A, 22 Eki 2026: ``outer_diameter`` gönderilirse
#: ``chamber_diameter`` daima kasa iç çapıdır).
_SOLID_CASE_BORE_SEMANTICS_FROM = (3, 0, 1)


def _version_tuple(value: Any) -> Optional[Tuple[int, ...]]:
    """'3.0.0' → (3, 0, 0); çözülemeyen sürüm None (göç uygulanmaz)."""
    if not isinstance(value, str):
        return None
    m = re.match(r'^\s*(\d+)\.(\d+)\.(\d+)', value)
    return tuple(int(x) for x in m.groups()) if m else None


def _finite_number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _solid_legacy_case_bore_migration(doc: Dict) -> Optional[Dict]:
    """3.0.1 öncesi katı projede tane çapı anlamındaki kasa çapını boşalt.

    ÖLÇÜLDÜ (26 Eki 2026): 3.0.0'dan kalan katı örnek ``chamber_diameter``
    = ``outer_diameter`` = 75 mm taşıyordu; 3.0.1 bu alanı kasa iç çapı
    okuduğu için tasarım 422 ile reddediliyordu (75 mm < 75 + 2·(2 + 3)).
    Eski sürümlerde alan tane çapı anlamındaydı; kasa ondan türetiliyordu.

    Göç YALNIZ şu imzada uygulanır: katı proje, kayıt sürümü 3.0.1'den eski,
    ``chamber_diameter`` ≤ ``outer_diameter`` (kasa taneden büyük değil —
    kasa iç çapı olarak fiziksel olarak olanaksız, eski anlamın imzası).
    Alan boşaltılır (sayfa göndermez, sunucu kasayı türetir ve
    ``case_bore`` künyesiyle beyan eder); diskteki dosya DEĞİŞMEZ ve göç
    adlı bir yükleme uyarısıyla kullanıcıya söylenir (sessiz değil).
    Kasa taneden büyükse alana dokunulmaz: o artık gerçek bir kasa çapıdır,
    sığmıyorsa 3.0.1'in adlı 422'si gereken en küçük çapı söyler.
    """
    if doc.get('motor_type') != 'solid':
        return None
    surum = _version_tuple(doc.get('app_version'))
    if surum is None or surum >= _SOLID_CASE_BORE_SEMANTICS_FROM:
        return None
    fields = (doc.get('inputs') or {}).get('fields')
    if not isinstance(fields, dict):
        return None
    kasa = _finite_number(fields.get('chamber_diameter'))
    tane = _finite_number(fields.get('outer_diameter'))
    if kasa is None or tane is None or kasa > tane:
        return None
    fields['chamber_diameter'] = ''

    def _yaz(v: float):
        return int(v) if float(v).is_integer() else round(v, 3)
    return {'code': LOAD_WARNING_SOLID_LEGACY_CASE_BORE,
            'severity': 'warning',
            'params': {'saved_version': doc.get('app_version'),
                       'chamber_diameter_mm': _yaz(kasa),
                       'outer_diameter_mm': _yaz(tane)}}
_LOAD_STAMPS = ('app_version', 'created_at', 'updated_at')


def load_warning_records(doc: Dict) -> List[Dict]:
    """Yüklenen belgenin uyarı kayıtları: ``{code, params, severity}``."""
    records: List[Dict] = []
    saved_version = doc.get('app_version')
    if isinstance(saved_version, str) and saved_version != APP_VERSION:
        records.append({'code': LOAD_WARNING_APP_VERSION_MISMATCH,
                        'severity': 'warning',
                        'params': {'saved_version': saved_version,
                                   'current_version': APP_VERSION}})
    for stamp in _LOAD_STAMPS:
        if stamp not in doc:
            records.append({'code': LOAD_WARNING_MISSING_STAMP,
                            'severity': 'warning',
                            'params': {'stamp': stamp}})
    return records


def load_warning_text(record: Dict) -> str:
    """Kaydın İngilizce yedek metni (``load_project`` düz listesi)."""
    return _LOAD_WARNING_TEXT_EN[record['code']].format(**record['params'])


def list_projects() -> List[Dict]:
    """Projeleri listele: ad, motor_type, updated_at, results_summary özeti.

    Bozuk / okunamayan / güvensiz dosyalar listeyi KIRMAZ; girdide
    corrupt=true ve reason alanı ile işaretlenir. Son güncellenene göre
    (yeniden eskiye) sıralanır, bozuklar sona gider.
    """
    base = os.path.realpath(projects_dir())
    entries: List[Dict] = []
    try:
        filenames = sorted(os.listdir(base))
    except OSError:
        return []

    for filename in filenames:
        if filename.startswith('.') or not filename.endswith(FILE_EXT):
            continue
        stem = filename[:-len(FILE_EXT)]
        entry: Dict[str, Any] = {'name': stem, 'corrupt': False}

        # Ad kuralına uymayan veya dizin dışına çözülen dosyalar yüklenemez;
        # gizlemek yerine işaretlenir (sessiz veri kaybı yasağı).
        try:
            _project_path(stem)
        except ProjectNameError as e:
            entry['corrupt'] = True
            entry['reason'] = f'unloadable file name: {e}'
            entries.append(entry)
            continue

        try:
            doc = _read_project_file(os.path.join(base, filename))
        except ProjectCorruptError as e:
            entry['corrupt'] = True
            entry['reason'] = str(e)
            entry['reason_kind'] = 'unreadable'
            entries.append(entry)
            continue

        # Listeleme, YÜKLEMEYLE AYNI ŞEMA KAPISINDAN geçer. Eskiden burada
        # yalnız "geçerli JSON + kök sözlük" denetimi vardı; şemaya uymayan
        # bir dosya listede corrupt=False, yani SAĞLAM görünüyor, tıklanınca
        # load_project ProjectCorruptError veriyordu (2026-08-27 ölçümü:
        # {"bu": "sema degil"} → listede sağlam, açılışta 'unknown keys: bu').
        # Liste ile yükleme aynı gerçeği söylemek zorunda: açılamayacak dosya
        # açılabilir gösterilmez (sessiz vaat yasağı).
        try:
            validate_payload(doc)
        except ProjectValidationError as e:
            entry['corrupt'] = True
            entry['reason'] = f'Project file does not match the schema: {e}'
            entry['reason_kind'] = 'schema'
            entries.append(entry)
            continue

        # Yalnızca liste için gereken alanlar döndürülür
        motor_type = doc.get('motor_type')
        entry['motor_type'] = motor_type if motor_type in MOTOR_TYPES else None
        entry['updated_at'] = doc.get('updated_at') if isinstance(doc.get('updated_at'), str) else None
        entry['description'] = doc.get('description') if isinstance(doc.get('description'), str) else None
        summary = doc.get('results_summary')
        entry['results_summary'] = summary if isinstance(summary, dict) else None
        entries.append(entry)

    def _sort_key(item: Dict) -> Tuple:
        # Bozuklar sona; sağlamlar updated_at'e göre yeniden eskiye
        if item['corrupt']:
            return (1, '', item['name'])
        return (0, _inverse_ts(item.get('updated_at')), item['name'])

    entries.sort(key=_sort_key)
    return entries


def _inverse_ts(ts: Optional[str]) -> str:
    """ISO zaman damgasını ters sıralama anahtarına çevir (yeni önce)."""
    if not ts:
        return '\uffff'  # damgasızlar en sona
    # ISO-8601 dizgileri leksikografik sıralanabilir; ters çevirmek için
    # her karakteri maksimum kod noktasından çıkarıyoruz.
    return ''.join(chr(0x10FFFF - ord(c)) for c in ts)


def delete_project(name: str) -> Dict:
    """Projeyi kalıcı silme YERİNE .trash/ altına zaman damgasıyla taşı."""
    path = _project_path(name)
    if not os.path.exists(path):
        raise ProjectNotFoundError(f"Project '{name}' not found")

    trash = _trash_dir()
    stamp = datetime.now().strftime('%Y%m%dT%H%M%S')
    trash_name = f'{stamp}-{name}{FILE_EXT}'
    trash_path = os.path.join(trash, trash_name)
    counter = 1
    while os.path.exists(trash_path):
        trash_name = f'{stamp}-{counter}-{name}{FILE_EXT}'
        trash_path = os.path.join(trash, trash_name)
        counter += 1
    os.replace(path, trash_path)
    return {'name': name, 'trashed_to': os.path.join(TRASH_DIRNAME, trash_name)}
