"""STEP içe aktarma HTTP uç noktası (Flask Blueprint: ``step_import_api``).

POST /api/import/step — multipart dosya alır, ``analyze_step`` ile geometri
analizi yapar, ölçü adaylarını JSON döndürür. Blueprint app.py'ye ana Claude
tarafından kaydedilir; bu modül app.py'yi import ETMEZ (bağımsız kalır).

Güvenlik notları:
  - Yüklenen dosya adı ASLA disk yolunda kullanılmaz; içerik ``tempfile``
    ile üretilen güvenli geçici yola yazılır (yol traversal imkansız).
  - Uzantı beyaz listesi (.step/.stp) + 50 MB boyut sınırı (Content-Length
    başlığı VE akış okuma sırasında çift kontrol; chunked yüklemede başlık
    olmayabilir).
  - STEP düz metindir; ZIP/XML işlenmez (sıkıştırılmış .stpz reddedilir),
    dolayısıyla ZIP bombası / XML entity yüzeyi yoktur.

MVP eşzamanlılık kararı: analiz senkron koşar ve yanıtına süre ölçümü
(``analysis_seconds``) eklenir. 60 sn üstü sürebilecek dev montajlar için
hrma/utils/job_runner.py deseni (submit + GET /api/jobs/<id> yoklaması)
sonraki aşamada bağlanmalıdır — burada bilinçli olarak uygulanmadı.

Kullanıcıya dönen tüm metinler İngilizce'dir (UI kuralı).
"""

import os
import tempfile
import time

from flask import Blueprint, jsonify, request

try:
    from hrma.importers.step_import import analyze_step
except ImportError:  # paket __init__ henüz yoksa: dosya yolundan yükle
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location(
        'hrma_importers_step_import_fallback',
        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     'step_import.py'))
    _mod = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    analyze_step = _mod.analyze_step

# ---------------------------------------------------------------------------
# Uç nokta parametreleri (parametre tutarlılığı kuralı: tek yerde tanım;
# depo genelinde başka upload sınırı tanımı yok — Grep ile doğrulandı).
# ---------------------------------------------------------------------------
#: Azami yükleme boyutu (bayt). 50 MB: büyük montaj STEP'leri dahi metin
#: olarak genelde 10-20 MB'tır; üstü kötü niyet/deneysel kabul edilir.
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
#: İzin verilen dosya uzantıları (küçük harf karşılaştırılır).
ALLOWED_EXTENSIONS = ('.step', '.stp')
#: Akış okuma parça boyutu (bayt).
READ_CHUNK_BYTES = 1024 * 1024

#: analyze_step 'error_kind' -> HTTP durum kodu eşlemesi.
_ERROR_STATUS = {
    'bad_request': 400,
    'invalid_file': 422,
    'internal': 500,
    'dependency_missing': 501,
}

step_import_api = Blueprint('step_import_api', __name__)


def _error(message, status):
    return jsonify({'source': 'step_import', 'error': message,
                    'warnings': []}), status


@step_import_api.route('/api/import/step', methods=['POST'])
def import_step_file():
    """STEP dosyası yükle -> geometri analizi + ölçü adayları (JSON)."""
    # 1) Boyut ön kontrolü (başlık varsa akışa girmeden reddet)
    clen = request.content_length
    if clen is not None and clen > MAX_UPLOAD_BYTES:
        return _error(
            f'file too large (limit {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)',
            413)

    upload = request.files.get('file')
    if upload is None or not (upload.filename or '').strip():
        return _error("missing file field 'file' (multipart/form-data)", 400)

    # 2) Uzantı beyaz listesi — istemci adı yalnızca burada ve yanıt
    #    etiketinde kullanılır, asla disk yolunda kullanılmaz.
    client_name = os.path.basename(upload.filename)
    ext = os.path.splitext(client_name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return _error(
            'unsupported file extension; expected one of: '
            + ', '.join(ALLOWED_EXTENSIONS), 400)

    # 3) İsteğe bağlı solid_index (montaj dosyasında katı seçimi)
    solid_index = None
    raw_idx = request.form.get('solid_index')
    if raw_idx is not None and str(raw_idx).strip() != '':
        try:
            solid_index = int(str(raw_idx).strip())
        except ValueError:
            return _error('solid_index must be an integer', 400)
        if solid_index < 0:
            return _error('solid_index must be >= 0', 400)

    # 4) Güvenli geçici dosyaya akışla yaz (boyut sınırı akışta da uygulanır)
    fd, tmp_path = tempfile.mkstemp(prefix='hrma_step_upload_', suffix='.step')
    total = 0
    try:
        with os.fdopen(fd, 'wb') as out:
            while True:
                chunk = upload.stream.read(READ_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    return _error(
                        'file too large '
                        f'(limit {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)',
                        413)
                out.write(chunk)
        if total == 0:
            return _error('uploaded file is empty', 400)

        # 5) Analiz (senkron) + süre ölçümü
        t0 = time.perf_counter()
        result = analyze_step(tmp_path, solid_index=solid_index)
        elapsed = time.perf_counter() - t0
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    result['analysis_seconds'] = round(elapsed, 3)
    result['filename'] = client_name
    status = 200
    if 'error' in result:
        status = _ERROR_STATUS.get(result.get('error_kind'), 422)
    return jsonify(result), status
