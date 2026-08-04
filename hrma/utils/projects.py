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

# --- Sabitler ---------------------------------------------------------------

FILE_EXT = '.hrma'
TRASH_DIRNAME = '.trash'

# Tek proje dosyası için üst sınır (ARGE raporu: 1 MB)
MAX_PROJECT_BYTES = 1024 * 1024

# Ad kuralı: [A-Za-z0-9 _.-] 1-80 karakter (nokta ile başlama ayrıca denetlenir)
NAME_MAX_LEN = 80
_NAME_RE = re.compile(r'^[A-Za-z0-9 _.\-]{1,80}$')

# Windows'ta dosya adı olarak kullanılamayan ayrılmış adlar
_WINDOWS_RESERVED = frozenset(
    ['CON', 'PRN', 'AUX', 'NUL']
    + [f'COM{i}' for i in range(1, 10)]
    + [f'LPT{i}' for i in range(1, 10)]
)

PROJECT_FORMAT_TAG = 'hrma-project'
PROJECT_FORMAT_VERSION = 1
MOTOR_TYPES = frozenset(['hybrid', 'solid', 'liquid'])

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


# --- Ad ve yol denetimi -----------------------------------------------------

def validate_name(name: Any) -> str:
    """Proje adını beyaz listeyle doğrula; geçerliyse adı döndür."""
    if not isinstance(name, str):
        raise ProjectNameError('Project name must be a string')
    if not _NAME_RE.match(name):
        raise ProjectNameError(
            'Invalid project name: only letters, digits, space, underscore, '
            f'dot and hyphen are allowed (1-{NAME_MAX_LEN} characters)')
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
    """
    path = _project_path(name)
    if not os.path.exists(path):
        raise ProjectNotFoundError(f"Project '{name}' not found")

    doc = _read_project_file(path)
    try:
        validate_payload(doc)
    except ProjectValidationError as e:
        raise ProjectCorruptError(f'Project file does not match the schema: {e}')

    warnings: List[str] = []
    saved_version = doc.get('app_version')
    if isinstance(saved_version, str) and saved_version != APP_VERSION:
        warnings.append(
            f'Project was saved with app version {saved_version}; '
            f'current version is {APP_VERSION}')
    for stamp in ('app_version', 'created_at', 'updated_at'):
        if stamp not in doc:
            warnings.append(f"Project file is missing the '{stamp}' stamp")
    return doc, warnings


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
