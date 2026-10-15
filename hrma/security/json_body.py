"""JSON gövdesinin biçim denetimi, uç içinde (V3 SG-2 bölüm C, SG-07 b).

``hrma/app.py::_reject_malformed_json_body`` gövde kapısı bozuk JSON'u,
JSON skaleri ve diziyi uca ulaşmadan 400 ile keser; ama yalnız
``_JSON_BODY_GATE_MAX_BYTES`` (1 MiB) altındaki gövdelerde. Daha büyük
gövde kapıdan geçer (büyük gövdeli uçların kendi boyut kapıları önce
çalışsın diye) ve ucun kendi ``request.json`` zincirine düşer.

KUSUR (ölçüldü, ``docs/scofield/raw/OH/V3/guvenlik/sgc/sonuc/
sg07b_once.json``; 1 MiB'ı az aşan gövdeler, test istemcisi gerçek sunucu
ayarıyla):

* ``/export_tank_cad``: dizi, skaler ve bozuk JSON -> HTML 500. Sebep:
  ``except TankCADDataError`` dalı. Ad ``try`` içinde içe aktarılıyordu;
  hata içe aktarmadan ÖNCE çıkınca ``except`` ifadesi değerlendirilirken
  ``UnboundLocalError`` atılıyor, uç kendi hata sözleşmesini hiç
  kullanamıyordu.
* ``/api/slosh-analysis``: bozuk JSON -> HTML 500 (aynı kalıp:
  ``except SloshGirdiHatasi``); dizi ve skaler -> JSON 500, gövdede ham
  Python metni (``'list' object has no attribute 'get'``).

Bu modül, kapının kullandığı AYNI makine-okur kodları (``malformed_json_body``
/ ``body_not_an_object``, 400) uç içinde verir; böylece istemci gövdenin
boyutundan bağımsız tek sözleşme görür. Flask'a bağımlı değildir: girdi
``request.get_json(silent=True)``'nin sonucudur.
"""

#: Biçim hatasının HTTP kodu (istemci hatası; gövde kapısıyla aynı).
MALFORMED_BODY_HTTP_STATUS = 400


def json_object_error(parsed):
    """Gövde JSON nesnesi (sözlük) değilse ``(gövde, 400)``, ise ``None``.

    ``parsed``: ``request.get_json(silent=True)`` sonucu. Bu çağrı bozuk
    JSON'da ``None`` döner (JSON ``null`` da ``None``'dır; ikisi de nesne
    değildir ve aynı yoldan reddedilir). Hiçbir hesap başlatılmaz, değer
    uydurulmaz.
    """
    if isinstance(parsed, dict):
        return None
    if parsed is None:
        return ({
            'status': 'error',
            'error': 'malformed_json_body',
            'message': ('The request body is not a valid JSON object (it '
                        'could not be parsed, or it is JSON null). No '
                        'analysis was attempted.'),
        }, MALFORMED_BODY_HTTP_STATUS)
    return ({
        'status': 'error',
        'error': 'body_not_an_object',
        'message': ('The request body must be a JSON object (a mapping of '
                    'field names to values); received '
                    + type(parsed).__name__ + '. No analysis was attempted.'),
    }, MALFORMED_BODY_HTTP_STATUS)
