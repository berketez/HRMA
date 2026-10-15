"""İstek bütçesi tavanları ve 413 beyanı (V3 SG-2 / SG-03, SG-07).

İki aile: uç başına KALEM SAYISI tavanı (:func:`item_budget_error`, SG-03)
ve bütün uçlarda gövde BAYT tavanının 413 beyanı (:func:`body_budget_error`,
SG-07; Content-Length taşımayan parçalı gövde için
:func:`streamed_body_budget_error`, SG-07 a; ayrıntı o fonksiyonlarda).

KUSUR (SG-0, ``docs/scofield/raw/OH/V3/guvenlik/poc/sonuc/sg_kaynak.json``):
``/api/comparative-analysis`` (``motor_configs``) ve ``/api/validate-fuel``
(``composition``) kalem sayısını hiç sınırlamıyordu; tek tavan 32 MiB gövde
bütçesiydi. Ölçülen: 200.000 konfigürasyon -> 3,8 s ve 17 MiB yanıt;
100.000 bileşen -> 13,5 MiB yanıt; 1.000.000 bileşen -> 422 ve her öğe için
bir ``invalid_fields`` kaydı. Kardeş uçlar (xlsx sayfa/satır/hücre, csv
satır, FEA ağ) kendi tavanlarını AÇIK hata ile beyan ediyor; bu iki uç
etmiyordu.

Desen kardeş ``hrma/app.py::_xlsx_budget_error`` ile aynıdır: sessiz
kırpma YOK, aşım 413 + hangi alanın hangi tavanı hangi sayıyla aştığı.

TAVANLARIN DAYANAĞI (ölçüm: ``docs/scofield/raw/OH/V3/guvenlik/sg2a/
sonuc/sg03_tavan_once.json``):

* Gerçek kullanım. Karşılaştırma paneli (``comparative_panel.js``)
  konfigürasyonu kullanıcının her hesaptan sonra elle bastığı "Snapshot"
  düğmesiyle tek tek ekler (tek ``snapshots.push``); örnek projelerde
  (``examples/*.hrma``) ``motor_configs`` 0 kez geçer. ``/api/validate-fuel``
  ucunu bugün çağıran arayüz kodu YOK (bileşim editörü OH-D31-05'te,
  çağıran ``validateComposition`` OH-D32-11'de söküldü); ucu yalnız API
  tüketicileri çağırır ve örnek projelerde ``composition`` 0 kez geçer.
* NASA CEA'nın kendi reaktan tablosu en çok 24 reaktan alır
  (``rocketcea/py_cea.inc``: ``PARAMETER (MAXR=24)``; yakıt + oksitleyici
  toplamı). 24'ü aşan bir yakıt listesi zaten bir CEA karışımı olamaz.
* Maliyet. Tavanın kendisinde iş ihmal edilebilir: 256 konfigürasyon
  34 ms / 31,7 KB, 64 bileşen 0,3 ms / 9,3 KB (tavanın 10 katında:
  2560 konfigürasyon 56 ms / 228 KB, 640 bileşen 1,6 ms / 89 KB). Yani
  tavanlar meşru kullanımı kesmeyecek kadar yüksek; gövde sınırına kadar
  bellekte kurulan işi ve yanıt büyütmesini kesecek kadar düşüktür.
"""

import io

#: ``/api/comparative-analysis`` ``motor_configs`` sözlüğünde en çok
#: konfigürasyon sayısı. Elle eklenen anlık görüntü başına bir kalem.
COMPARATIVE_MAX_CONFIGS = 256

#: ``/api/validate-fuel`` ``composition`` listesinde en çok bileşen sayısı.
#: NASA CEA reaktan tablosunun (MAXR = 24) 2,6 katı pay bırakır.
FUEL_COMPOSITION_MAX_ITEMS = 64

#: Aşım yanıtının HTTP kodu (413 "istek fazla büyük"; kardeş xlsx bütçesi
#: ile aynı). Kalem ve gövde tavanı aynı kodu kullanır.
BUDGET_EXCEEDED_HTTP_STATUS = 413


def item_budget_error(field, items, maximum):
    """Kalem sayısı tavanı aşıldıysa ``(gövde, 413)``, aşılmadıysa ``None``.

    ``items``: ``len()`` destekleyen kap (sözlük ya da liste). Gövde,
    alanın adını, tavanı ve gelen sayıyı taşır; hiçbir hesap yapılmadığını
    açıkça söyler (sessiz kırpma yasak).
    """
    count = len(items)
    if count <= maximum:
        return None
    return ({
        'status': 'error',
        'error': 'item_budget_exceeded',
        'limit': field,
        'field': field,
        'maximum': maximum,
        'requested': count,
        'message': (f"'{field}' holds {count} items; the limit is "
                    f'{maximum}. Nothing was computed.'),
    }, BUDGET_EXCEEDED_HTTP_STATUS)


def body_budget_error(content_length, maximum):
    """Gövde bayt tavanı aşıldıysa ``(gövde, 413)``, aşılmadıysa ``None``.

    V3 SG-2 yan bulgusu (SG-07). ``hrma/app.py`` gövde tavanını
    ``MAX_CONTENT_LENGTH`` ile koyar ve "aşan istekler Flask tarafından 413
    ile reddedilir" diye beyan eder. ÖLÇÜLDÜ (``docs/scofield/raw/OH/V3/
    guvenlik/sg2a/sonuc/govde_tavani_once.json``; ölçülebilir 62 POST
    ucu, tavan ölçüm için 1,1 MB'a indirildi): beyan yalnız 8 uçta tutuyor
    (HTML 413); 45 uç 500 JSON, 2 uç 500 HTML, 4 uç 400, 3 uç 422 veriyordu.
    Sebep: Werkzeug gövde OKUNURKEN ``RequestEntityTooLarge`` atar ve
    uçların ``except Exception`` dalı bunu kendi hatasına çevirir.

    Bu yardımcı ``before_request``'ten çağrılır: ``Content-Length`` tavanı
    aşıyorsa gövde HİÇ okunmadan, her uçta aynı JSON 413 döner. Tavan
    ``app.config['MAX_CONTENT_LENGTH']``'ten okunur (tek kaynak app.py);
    burada ikinci bir sayı YOKTUR. ``Content-Length`` taşımayan (chunked)
    gövdede karar verilemez (``None`` döner); o yol Werkzeug'un akış
    sınırına kalır.
    """
    if not maximum or content_length is None:
        return None
    if int(content_length) <= int(maximum):
        return None
    return ({
        'status': 'error',
        'error': 'request_body_too_large',
        'limit': 'body_bytes',
        'maximum': int(maximum),
        'requested': int(content_length),
        'message': (f'The request body is {int(content_length)} bytes; the '
                    f'limit is {int(maximum)} bytes. The body was not read '
                    'and nothing was computed.'),
    }, BUDGET_EXCEEDED_HTTP_STATUS)


#: Parçalı gövde okunurken tek okumanın boyutu [bayt]. Bellek tepe noktasını
#: değil yalnız çağrı sayısını belirler; tepe noktası tavanın kendisidir.
STREAM_READ_CHUNK_BYTES = 64 * 1024


def streamed_body_budget_error(environ, maximum):
    """``Content-Length``'siz (parçalı) gövde tavanı aştıysa ``(gövde, 413)``.

    V3 SG-2 bölüm C, SG-07 (a). :func:`body_budget_error` ``Content-Length``
    taşımayan gövdede karar veremiyordu. ÖLÇÜLDÜ (``docs/scofield/raw/OH/V3/
    guvenlik/sgc/sonuc/sg07a_once_werkzeug.json``; gerçek Werkzeug geliştirme
    sunucusu, ``hrma/run.py`` Unix ve Windows-yedek dalları ile ``flask
    run``'ın sunucusu; tavan ölçüm için 1,1 MiB): ``Transfer-Encoding:
    chunked`` ile tavanı aşan gövde

    * JSON uçlarında (5/5) tavanda SESSİZCE KESİLİP bozuk JSON sayılıyordu:
      400 ``malformed_json_body`` (yanlış neden);
    * çok parçalı yükleme uçlarında (STEP, ork) Werkzeug'un HTML 413'ü;
    * ``/api/validation/upload-csv``'de tavanda kesilen CSV AYRIŞTIRILIP
      200 dönüyordu: kullanıcının dosyasının yalnız ilk 1,1 MiB'ı, hiçbir
      uyarı olmadan (eksik veriyle sonuç).

    Waitress (paketli başlatıcı, ``hrma/run.py`` Windows/waitress dalı,
    ``run_windows.py``) parçalı gövdeyi kendisi tamponlayıp
    ``CONTENT_LENGTH`` yazar; orada 8/8 uç zaten JSON 413 veriyordu
    (``sg07a_once_waitress.json``). Bu fonksiyon Werkzeug yolunu aynı
    sözleşmeye getirir: sunucu akışı sonlandırıyorsa (``wsgi.input_terminated``)
    gövde en çok ``maximum + 1`` bayt okunur; tavanı aşarsa hiçbir uç
    çalışmadan JSON 413 döner, aşmazsa okunan gövde ``Content-Length``'li
    sıradan bir istek gövdesi olarak yerine konur (waitress'in yaptığının
    aynısı; ``Transfer-Encoding`` başlığı kalkar). Böylece uçların kendi
    ``content_length`` kapıları da (ork, motor dosyası, STEP, proje kaydı)
    parçalı gövdede çalışır.

    Yalnız ``Transfer-Encoding`` başlığı ``chunked`` içeriyor ve sunucu
    akışı sonlandırıyorsa çalışır. Aynı istekte ``Content-Length`` de varsa
    yok sayılır: ``Transfer-Encoding`` onu geçersiz kılar (RFC 9112 §6.3);
    iki başlığı birlikte gönderen istek de böylece kapıdan kaçamaz ve
    okunan gerçek uzunluk yazılır. Tarayıcının ``fetch``/form gönderileri
    ``Content-Length`` taşıdığı için meşru yol bit-aynıdır.

    SIRA ŞARTI: Werkzeug'da ``request.content_length`` ÖNBELLEKLİ bir
    özelliktir (``werkzeug.utils.cached_property``). Bu fonksiyon ondan
    ÖNCE çağrılmalıdır (``app.py::_reject_oversized_body`` öyle yapar); yoksa
    uçların kendi ``content_length`` kapıları normalleştirilmiş uzunluğu
    değil önbellekteki ``None``'ı görür.

    Tavan ``app.config``'ten gelir (``maximum``); burada ikinci bir sayı
    yoktur. ``environ`` WSGI ortam sözlüğüdür (Flask'a bağımlılık yok).
    """
    if not maximum:
        return None
    encoding = str(environ.get('HTTP_TRANSFER_ENCODING') or '').lower()
    if 'chunked' not in encoding:
        return None
    stream = environ.get('wsgi.input')
    if stream is None or 'wsgi.input_terminated' not in environ:
        # Sunucu akışı sonlandırmıyorsa Werkzeug gövdeyi zaten BOŞ okur
        # (``get_input_stream`` güvenli yedek); okumaya çalışmak askıda
        # kalabilir.
        return None
    maximum = int(maximum)
    received = bytearray()
    while len(received) <= maximum:
        chunk = stream.read(min(STREAM_READ_CHUNK_BYTES,
                                maximum + 1 - len(received)))
        if not chunk:
            break
        received.extend(chunk)
    if len(received) > maximum:
        return ({
            'status': 'error',
            'error': 'request_body_too_large',
            'limit': 'body_bytes',
            'maximum': maximum,
            'requested': None,
            'message': (f'The request body was sent without a Content-Length '
                        f'and exceeds the limit of {maximum} bytes. Reading '
                        'stopped at the limit and nothing was computed.'),
        }, BUDGET_EXCEEDED_HTTP_STATUS)
    environ['wsgi.input'] = io.BytesIO(bytes(received))
    environ['CONTENT_LENGTH'] = str(len(received))
    environ.pop('HTTP_TRANSFER_ENCODING', None)
    environ.pop('wsgi.input_terminated', None)
    return None
