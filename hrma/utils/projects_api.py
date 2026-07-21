"""
HRMA proje kaydet/yükle HTTP API'si (Flask Blueprint).

Rotalar (url_prefix YOK, tam yol):
  GET  /api/projects              -> proje listesi
  POST /api/projects/save         -> {"name": ..., "payload": {...}, "overwrite": bool?}
  GET  /api/projects/load/<name>  -> kayıtlı proje belgesi + source + warnings
  POST /api/projects/delete       -> {"name": ...} (kalıcı silme değil, .trash'e taşır)

Hata sözleşmesi: {"error": "..."} + uygun HTTP kodu. İstemci hata mesajları
İngilizce'dir (arayüz çevirisi frontend tarafında yapılır).

Güvenlik: proje adı beyaz liste + realpath kapsama denetimi projects.py
katmanında uygulanır; burada ayrıca istek gövdesi boyut sınırı vardır
(1 MB'lik proje belgesi + JSON zarfı payı).
"""

from flask import Blueprint, jsonify, request

from hrma.utils import projects as project_store

projects_api = Blueprint('projects_api', __name__)

# Kayıt isteği gövdesi üst sınırı: 1 MB'lik belge + zarf/kaçış payı.
# Belge boyutu asıl sınırı projects.MAX_PROJECT_BYTES uygular.
MAX_REQUEST_BYTES = 2 * project_store.MAX_PROJECT_BYTES

# Yükleme yanıtlarındaki kaynak etiketi (uydurma-veri-yasağı: verinin
# nereden geldiği her yanıtta açıkça belirtilir)
SOURCE_TAG = 'hrma-project-file'


def _error(message: str, status: int):
    """Tek biçimli hata yanıtı: {"error": ...} + HTTP kodu."""
    return jsonify({'error': message}), status


def _store_error(exc: project_store.ProjectError):
    """Depo istisnasını uygun HTTP koduna eşle."""
    if isinstance(exc, project_store.ProjectNotFoundError):
        return _error(str(exc), 404)
    if isinstance(exc, project_store.ProjectExistsError):
        return _error(str(exc), 409)
    if isinstance(exc, project_store.ProjectTooLargeError):
        return _error(str(exc), 413)
    if isinstance(exc, project_store.ProjectCorruptError):
        return _error(str(exc), 422)
    # ProjectNameError, ProjectValidationError ve diğer istemci hataları
    return _error(str(exc), 400)


def _json_body():
    """İstek gövdesini JSON sözlük olarak al; değilse None döndür."""
    if request.content_length is not None and request.content_length > MAX_REQUEST_BYTES:
        return None, _error(
            f'Request body exceeds {MAX_REQUEST_BYTES} bytes', 413)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, _error('Request body must be a JSON object', 400)
    return data, None


@projects_api.route('/api/projects', methods=['GET'])
def api_projects_list():
    """Kayıtlı projeleri listele (bozuk dosyalar corrupt=true ile işaretli)."""
    try:
        items = project_store.list_projects()
    except OSError as e:
        return _error(f'Projects directory cannot be read: {e}', 500)
    return jsonify({'projects': items, 'count': len(items)})


@projects_api.route('/api/projects/save', methods=['POST'])
def api_projects_save():
    """Projeyi kaydet. Aynı ad varsa overwrite=true bayrağı zorunlu (409)."""
    data, err = _json_body()
    if err:
        return err

    name = data.get('name')
    payload = data.get('payload')
    overwrite = data.get('overwrite', False)
    if name is None:
        return _error("Missing required field 'name'", 400)
    if payload is None:
        return _error("Missing required field 'payload'", 400)
    if not isinstance(overwrite, bool):
        return _error("Field 'overwrite' must be a boolean", 400)

    try:
        info = project_store.save_project(name, payload, overwrite=overwrite)
    except project_store.ProjectError as e:
        return _store_error(e)
    except OSError as e:
        return _error(f'Project could not be written: {e}', 500)

    result = {'status': 'saved'}
    result.update(info)
    return jsonify(result)


@projects_api.route('/api/projects/load/<name>', methods=['GET'])
def api_projects_load(name):
    """Projeyi yükle: source etiketi + warnings listesiyle döner.

    Eksik alanlar sunucu tarafında SESSİZCE doldurulmaz; belge diskteki
    haliyle döner. estimated listesi her zaman boştur (bu API hiçbir alanı
    tahminle doldurmaz) ve sözleşmeyi açıkça belgelemek için yanıtta durur.
    """
    try:
        doc, warnings = project_store.load_project(name)
    except project_store.ProjectError as e:
        return _store_error(e)
    except OSError as e:
        return _error(f'Project could not be read: {e}', 500)

    return jsonify({
        'status': 'loaded',
        'source': SOURCE_TAG,
        'name': doc.get('name', name),
        'project': doc,
        'warnings': warnings,
        'estimated': [],  # hiçbir alan tahminle doldurulmadı
    })


@projects_api.route('/api/projects/delete', methods=['POST'])
def api_projects_delete():
    """Projeyi .trash/ altına taşı (kalıcı silme yapılmaz)."""
    data, err = _json_body()
    if err:
        return err
    name = data.get('name')
    if name is None:
        return _error("Missing required field 'name'", 400)

    try:
        info = project_store.delete_project(name)
    except project_store.ProjectError as e:
        return _store_error(e)
    except OSError as e:
        return _error(f'Project could not be moved to trash: {e}', 500)

    result = {'status': 'deleted'}
    result.update(info)
    return jsonify(result)
