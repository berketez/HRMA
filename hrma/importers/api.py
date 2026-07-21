"""Import API Blueprint'i (``importers_api``).

Uçlar (tam yol, url_prefix YOK — app.py'de
``app.register_blueprint(importers_api)`` ile kaydedilir):

- POST /api/import/motor-file — RASP .eng / RockSim .rse itki eğrisi
  dosyası; istek JSON: {"content": str, "filename": str,
  "prediction": ops. {"time": [...], "thrust": [...]}}.
  ``prediction`` verilirse dosyadaki eğri, HRMA tahminiyle CSV
  doğrulama akışıyla AYNI metriklerle karşılaştırılır
  (hrma/validation/user_data_validation.compare).
- POST /api/import/ork — OpenRocket .ork; multipart ``file`` alanı YA DA
  JSON {"content_base64": str, "filename": ops.}.

Yanıt sözleşmesi upload-csv ucuyla tutarlıdır: başarıda
``{"status": "success", "source": ..., "warnings": [...], ...}``;
ayrıştırma hatasında 400 + ``{"status": "error", "error": msg}``;
boyut aşımında 413. Dosya adı yalnız uzantı beyaz listesi için kullanılır,
hiçbir zaman dosya sistemi yoluna çevrilmez.
"""

import base64
import binascii

from flask import Blueprint, jsonify, request

from hrma.importers import motor_file, ork_import
from hrma.validation.user_data_validation import compare as \
    compare_thrust_curves

importers_api = Blueprint('importers_api', __name__)

# İstek boyut sınırları (ARGE kararı): itki eğrisi metin dosyaları küçüktür,
# .ork ZIP'leri dekal içerebilir. Sınırlar SIKIŞTIRILMIŞ yükleme boyutudur;
# ZIP açılım sınırı ork_import.ORK_MAX_UNCOMPRESSED_BYTES ile ayrıca
# korunur.
MOTOR_FILE_MAX_BYTES = 2 * 1024 * 1024
ORK_MAX_BYTES = 20 * 1024 * 1024

# İstemciden gelen dosya adı beyaz listesi (yalnız uzantı denetimi)
ALLOWED_MOTOR_FILE_EXTENSIONS = ('.eng', '.rse')
ALLOWED_ORK_EXTENSIONS = ('.ork', '.xml')

# Content-Length ön denetimi için JSON/multipart zarf payı
_ENVELOPE_SLACK_BYTES = 512 * 1024


def _safe_filename(name):
    """İstemci dosya adını görüntüleme/uzantı denetimi için sadeleştir.

    Yol ayraçları atılır (yalnız son bileşen kalır), uzunluk sınırlanır.
    Bu ad HİÇBİR ZAMAN dosya sistemi yoluna çevrilmez.
    """
    if not isinstance(name, str):
        return ''
    base = name.replace('\\', '/').rsplit('/', 1)[-1].strip()
    return base[:200]


def _payload_too_large(limit_bytes):
    return jsonify({
        'status': 'error',
        'error': (f'Uploaded content exceeds the '
                  f'{limit_bytes // (1024 * 1024)} MB limit for this '
                  'endpoint.'),
    }), 413


@importers_api.route('/api/import/motor-file', methods=['POST'])
def import_motor_file():
    """RASP .eng / RockSim .rse itki eğrisi dosyasını içe aktar.

    Başarı yanıtı::

        {"status": "success", "source": "rasp_eng"|"rse",
         "filename": str, "motors": [normalize motor, ...],
         "selected_index": 0, "motor": <varsayılan motor>,
         "warnings": [dosya düzeyi uyarılar],
         "comparison": compare() çıktısı | null}
    """
    if request.content_length is not None and \
            request.content_length > MOTOR_FILE_MAX_BYTES + \
            _ENVELOPE_SLACK_BYTES:
        return _payload_too_large(MOTOR_FILE_MAX_BYTES)
    data = request.get_json(silent=True) or {}
    content = data.get('content')
    filename = _safe_filename(data.get('filename') or '')
    prediction = data.get('prediction')
    if not isinstance(content, str) or not content.strip():
        return jsonify({
            'status': 'error',
            'error': ("No motor file content provided. Send JSON "
                      "{'content': '<file text>', 'filename': 'x.eng', "
                      "'prediction': {'time': [...], 'thrust': [...]} "
                      "(optional)}."),
        }), 400
    if len(content.encode('utf-8', errors='ignore')) > MOTOR_FILE_MAX_BYTES:
        return _payload_too_large(MOTOR_FILE_MAX_BYTES)
    lowered = filename.lower()
    if not lowered.endswith(ALLOWED_MOTOR_FILE_EXTENSIONS):
        return jsonify({
            'status': 'error',
            'error': ('Unsupported motor file type. Allowed extensions: '
                      + ', '.join(ALLOWED_MOTOR_FILE_EXTENSIONS)
                      + '. Provide the original file name in "filename".'),
        }), 400

    if lowered.endswith('.eng'):
        source = 'rasp_eng'
        motor = motor_file.parse_eng(content)
        if 'error' in motor:
            return jsonify({'status': 'error', 'source': source,
                            'error': motor['error']}), 400
        motors = [motor]
        file_warnings = []
    else:
        source = 'rse'
        parsed = motor_file.parse_rse(content)
        if 'error' in parsed:
            return jsonify({'status': 'error', 'source': source,
                            'error': parsed['error']}), 400
        motors = parsed['motors']
        file_warnings = parsed['warnings']

    default_motor = motors[0]
    comparison = None
    if prediction is not None:
        try:
            comparison = compare_thrust_curves(
                {'time': default_motor['time'],
                 'thrust': default_motor['thrust']},
                prediction)
        except ValueError as exc:
            # Dosya çözüldü ama karşılaştırma anlamsız — upload-csv
            # deseniyle aynı: ayrıştırılmış veri yanıt gövdesinde kalır.
            return jsonify({
                'status': 'error', 'error': str(exc), 'source': source,
                'filename': filename, 'motors': motors,
                'selected_index': 0, 'motor': default_motor,
                'warnings': file_warnings,
            }), 400
    return jsonify({
        'status': 'success',
        'source': source,
        'filename': filename,
        'motors': motors,
        'selected_index': 0,
        'motor': default_motor,
        'warnings': file_warnings,
        'comparison': comparison,
    })


@importers_api.route('/api/import/ork', methods=['POST'])
def import_ork():
    """OpenRocket .ork tasarım dosyasını içe aktar.

    Girdi: multipart form ``file`` alanı YA DA JSON
    {"content_base64": str, "filename": ops.}.

    Başarı yanıtı: ``{"status": "success", "filename": str|null}`` +
    ork_import.parse_ork çıktısı (source/aero/components/embedded_motors/
    saved_simulations/mapping_report/warnings).
    """
    if request.content_length is not None and \
            request.content_length > ORK_MAX_BYTES + _ENVELOPE_SLACK_BYTES:
        return _payload_too_large(ORK_MAX_BYTES)

    blob = None
    filename = ''
    upload = request.files.get('file') if request.files else None
    if upload is not None:
        filename = _safe_filename(upload.filename or '')
        blob = upload.read(ORK_MAX_BYTES + 1)
    else:
        data = request.get_json(silent=True) or {}
        encoded = data.get('content_base64')
        filename = _safe_filename(data.get('filename') or '')
        if isinstance(encoded, str) and encoded.strip():
            try:
                blob = base64.b64decode(encoded, validate=True)
            except (binascii.Error, ValueError):
                return jsonify({
                    'status': 'error',
                    'error': "Field 'content_base64' is not valid base64.",
                }), 400
    if blob is None:
        return jsonify({
            'status': 'error',
            'error': ("No .ork content provided. Send the file as a "
                      "multipart 'file' field, or as JSON "
                      "{'content_base64': '...'}."),
        }), 400
    if len(blob) > ORK_MAX_BYTES:
        return _payload_too_large(ORK_MAX_BYTES)
    if filename and not filename.lower().endswith(ALLOWED_ORK_EXTENSIONS):
        return jsonify({
            'status': 'error',
            'error': ('Unsupported design file type. Allowed extensions: '
                      + ', '.join(ALLOWED_ORK_EXTENSIONS) + '.'),
        }), 400

    result = ork_import.parse_ork(blob)
    if 'error' in result:
        return jsonify({'status': 'error', 'source': 'ork',
                        'error': result['error']}), 400
    return jsonify({'status': 'success', 'filename': filename or None,
                    **result})
