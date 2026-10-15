"""Köken kapısı: ``Origin`` ve ``Sec-Fetch-Site`` denetimi (V3 SG-2, bölüm A).

``hrma/app.py::_reject_cross_origin`` önce Host (DNS rebinding) kapısını
çalıştırır, sonra bu modüldeki :func:`request_rejection`'ı çağırır. Bu
modül Flask'a bağımlı değildir; düz değerlerle çalışır.

Kapattığı iki kusur (SG-0 raporu ``docs/scofield/raw/OH/V3/guvenlik/
SG0_saldiri_yuzeyi.md``):

SG-02 — PORTSUZ ORIGIN PORT DENETİMİNİ ATLIYORDU.
    Eski kapı ``if self_port and origin_port and ...`` biçimindeydi. Origin
    portsuz geldiğinde (``http://localhost``, ``https://localhost``,
    ``http://[::1]``) ``origin_port`` None olur ve karşılaştırma HİÇ
    yapılmazdı. Ölçüldü (SG-0, ``poc/sonuc/sg_ag_kapilar.json``):
    HRMA_SELF_PORT=8080 iken bu üç köken 200 alıyordu, aynı ana makinenin
    ``:80`` yazılmış hâli ise 403. Oysa portsuz Origin "port yok" demek
    değildir: köken serileştirmesi varsayılan portu YAZMAZ (RFC 6454 §6.1),
    ``http`` için bu 80, ``https`` için 443'tür (RFC 9110 §4.2.1-4.2.2).
    Artık port şemadan türetilir ve yine sunucunun kendi portuyla
    karşılaştırılır; türetilemiyorsa (bilinmeyen şema) ret.

    Kaynaktan çalıştırma yolu (``start.sh``/``start.bat`` -> ``hrma/run.py``)
    HRMA_SELF_PORT'u hiç doldurmuyordu; kapı orada her geri döngü portuna
    açıktı. ``hrma/run.py`` artık :func:`register_self_port` ile doldurur
    (paketli başlatıcı ``packaging/launcher.py`` zaten dolduruyordu).

SG-02c — PORT BİLİNMEYİNCE KAPI GEVŞİYORDU (bölüm C, ana model izni 12 Eki).
    ``HRMA_SELF_PORT`` ayarsızken (``flask run``, WSGI gömme, testler)
    port denetimi HİÇ yapılmıyor, 127.0.0.1'in başka portundaki sayfa
    durum değiştiren istek atabiliyordu (SG-0 tehdit modeli). Aynı köken
    kuralı şema + ana makine + PORT'tur (RFC 6454 §4-5). Artık port
    bilinmiyorsa sunucunun portu isteğin KENDİ ``Host`` başlığından alınır
    (:func:`self_port_from_host`): tarayıcı Host'u hedef adresin portuyla
    yazar ve sayfa onu değiştiremez (RFC 9110 §7.2), Host'un geri döngü
    olduğunu ise bir önceki kapı zaten şart koşar. Host'tan da port
    türetilemiyorsa ``Origin`` taşıyan istek reddedilir (fail-closed).

SG-06 — YAN ETKİLİ GET UÇLARI YALNIZ HOST KAPISIYLA KORUNUYORDU.
    Köken kapısı yalnız durum değiştiren metodlarda çalışıyordu. Üç GET ucu
    ise okuma değildir (bkz. :data:`SIDE_EFFECT_GET_ENDPOINTS`). Geri
    döngünün başka bir portundaki yerel sayfa (``<img src>`` ya da
    ``fetch``) bu yan etkileri tetikleyebiliyordu. Artık bu uçlarda
    ``Sec-Fetch-Site`` yalnız ``same-origin`` / ``none`` olabilir ve
    ``Origin`` varsa durum değiştiren isteklerle AYNI kuraldan geçer.
    Başlıksız istek (curl, eski web görünümü, test istemcisi) geçer: kapı
    tarayıcının kendiliğinden eklediği, sayfanın değiştiremediği
    başlıklara dayanır; başlıksız yerel istemci zaten doğrudan çağırabilir.
"""

import os
from urllib.parse import urlsplit

#: Sunucunun GERÇEKTEN bağlandığı portun ortam değişkeni adı. Paketli
#: başlatıcı (``packaging/launcher.py``) aynı adı yazar; ``hrma/app.py``
#: içe aktarılırken bu değişkeni ``app.config`` içine alır.
SELF_PORT_ENV = 'HRMA_SELF_PORT'

#: ``app.config`` anahtarı (ortam değişkeniyle aynı ad).
SELF_PORT_CONFIG_KEY = 'HRMA_SELF_PORT'

#: Şemanın varsayılan portu. Tarayıcı kökeni serileştirirken bu portu
#: YAZMAZ (RFC 6454 §6.1); portsuz Origin'in portu buradan türetilir.
#: http 80 (RFC 9110 §4.2.1), https 443 (RFC 9110 §4.2.2).
SCHEME_DEFAULT_PORTS = {'http': 80, 'https': 443}

#: Durum değiştirmeyen metodlar. Bunlarda köken kapısı yalnız
#: :data:`SIDE_EFFECT_GET_ENDPOINTS` uçlarında çalışır. OPTIONS hiçbir
#: uçta görünüm çalıştırmaz (Flask'ın otomatik yanıtı), denetlenmez.
SAFE_METHODS = frozenset({'GET', 'HEAD', 'OPTIONS'})

#: GET ile çağrılan ama OKUMA OLMAYAN uçlar (Flask uç adı, ``request.endpoint``):
#:
#: * ``tile_proxy`` (``/api/tile/<katman>/<z>/<x>/<y>``) — karo önbellekte
#:   yoksa NASA GIBS'ten çekip DİSKE yazar (önbellek büyür, dış ağ açılır).
#: * ``correlation_report`` (``/api/correlation-report``) — ilk çağrıda
#:   ağır senkron korelasyon koşusu (kilitli; eşzamanlı istekler bekler).
#: * ``update_check`` (``/api/update/check``) — GitHub API'ye çıkış isteği.
#: * ``check_database_status`` (``/api/database-status``) — önbellek
#:   soğukken ya da ``?refresh=1`` ile ``db_manager.test_connections()``
#:   üzerinden CANLI NIST WebBook isteği (dış ağ; ağ yavaşken iş
#:   parçacığını saniyelerce tutar). SG-2 şart turu (13 Eki, denetim Ş1)
#:   ekledi: geri döngünün başka portundaki sayfa ``<img>`` ve no-cors
#:   ``fetch`` ile bu isteği tetikleyebiliyordu (gerçek Chromium'da
#:   ölçüldü). Arayüzün kendi çağrıları göreli yoldur (same-origin), geçer.
#:
#: HEAD de görünümü çalıştırır (Flask HEAD'i GET görünümüyle yanıtlar),
#: o yüzden HEAD de bu kümede denetlenir.
SIDE_EFFECT_GET_ENDPOINTS = frozenset({
    'tile_proxy',
    'correlation_report',
    'update_check',
    'check_database_status',
})

#: Yan etkili GET uçlarında kabul edilen ``Sec-Fetch-Site`` değerleri.
#:
#: * ``same-origin`` — HRMA'nın kendi sayfası (``fetch``, three.js doku
#:   yükleyicisi): aynı şema + ana makine + port.
#: * ``none`` — kullanıcı adres çubuğuna yazdı ya da yer imini açtı
#:   (kullanıcı eylemi, sayfa tetiklemedi).
#:
#: ``same-site`` KABUL EDİLMEZ: 127.0.0.1'in BAŞKA portundaki sayfa
#: tarayıcıya göre aynı sitedir (site = şema + ana makine; port sayılmaz).
#: SG-06'nın tehdit modeli tam olarak budur.
ALLOWED_FETCH_SITES = frozenset({'same-origin', 'none'})


def origin_parts(raw_origin):
    """``(şema, ana makine, etkin port)`` döndürür.

    Etkin port: Origin'de yazılıysa o, yazılı değilse şemanın varsayılanı
    (:data:`SCHEME_DEFAULT_PORTS`); bilinmeyen şemada None. Ayrıştırılamayan
    değerde (``'null'``, geçersiz port ``':abc'``) ana makine None döner.
    """
    if not raw_origin:
        return (None, None, None)
    try:
        parts = urlsplit(raw_origin)
        scheme = (parts.scheme or '').lower()
        host = parts.hostname
        port = parts.port          # geçersiz portta ValueError
    except (ValueError, TypeError):
        return (None, None, None)
    if port is None:
        port = SCHEME_DEFAULT_PORTS.get(scheme)
    return (scheme or None, host, port)


def origin_rejection(raw_origin, self_port, is_loopback):
    """``Origin`` başlığına göre ret nedeni (dize) ya da ``None``.

    * Başlık yoksa geçer (curl, native web görünümü, aynı köken GET).
    * Ana makine geri döngü değilse ``'origin_not_loopback'`` (``'null'``
      kökeni de buraya düşer: sandbox iframe, ``file://``).
    * Etkin port sunucunun portuna EŞİT olmalı; değilse ya da Origin'in
      portu türetilemiyorsa ``'origin_port_mismatch'``.
    * Sunucunun portu da bilinmiyorsa (``self_port`` boş) ret
      ``'self_port_unknown'`` (SG-02c, fail-closed): portu bilinmeyen
      sunucu "aynı köken" diyemez. :func:`request_rejection` önce Host'tan
      türetmeyi dener; bu dal yalnız o da başarısızsa çalışır.

    ``is_loopback``: Host kapısının kullandığı geri döngü yüklemi
    (``hrma/app.py::_is_loopback``); iki kapı aynı tanımı paylaşsın diye
    dışarıdan verilir.
    """
    if not raw_origin:
        return None
    _scheme, host, port = origin_parts(raw_origin)
    if not is_loopback(host):
        return 'origin_not_loopback'
    if not self_port:
        return 'self_port_unknown'
    if port is None or int(port) != int(self_port):
        return 'origin_port_mismatch'
    return None


def fetch_site_rejection(sec_fetch_site):
    """``Sec-Fetch-Site`` başlığına göre ret nedeni ya da ``None``.

    Başlık yoksa geçer (eski web görünümü, başlıksız yerel istemci). Varsa
    yalnız :data:`ALLOWED_FETCH_SITES` geçer; tanınmayan değer de reddedilir
    (fail-closed).
    """
    if sec_fetch_site is None:
        return None
    if str(sec_fetch_site).strip().lower() in ALLOWED_FETCH_SITES:
        return None
    return 'fetch_site_not_same_origin'


def self_port_from_host(request_host, scheme):
    """Sunucunun portu isteğin ``Host`` başlığından (SG-02c); yoksa None.

    Host'ta port yazılıysa o, yazılı değilse şemanın varsayılanı
    (:data:`SCHEME_DEFAULT_PORTS`; Host da varsayılan portu yazmaz, RFC 9110
    §7.2). Host boşsa, port geçersizse ya da şema bilinmiyorsa None: çağıran
    bunu "port bilinmiyor" sayar ve kapı kapanır.
    """
    if not request_host:
        return None
    try:
        port = urlsplit('//' + str(request_host)).port
    except (ValueError, TypeError):
        return None
    return port if port is not None else SCHEME_DEFAULT_PORTS.get(
        (scheme or '').lower())


def request_rejection(method, endpoint, headers, self_port, is_loopback,
                      request_host=None, scheme=None):
    """Host kapısından SONRAKİ köken kararı: ret nedeni ya da ``None``.

    Parametreler düz değerdir: ``method`` (``request.method``),
    ``endpoint`` (``request.endpoint``), ``headers`` (``.get`` destekleyen
    eşleme), ``self_port`` (``app.config['HRMA_SELF_PORT']``),
    ``is_loopback`` (Host kapısının yüklemi), ``request_host``
    (``request.host``) ve ``scheme`` (``request.scheme``).

    ``self_port`` boşsa sunucunun portu ``request_host``'tan türetilir
    (SG-02c, :func:`self_port_from_host`); o da olmazsa Origin taşıyan
    istek reddedilir.
    """
    method = (method or '').upper()
    if not self_port:
        self_port = self_port_from_host(request_host, scheme)
    if method in SAFE_METHODS:
        if method == 'OPTIONS' or endpoint not in SIDE_EFFECT_GET_ENDPOINTS:
            return None
        reason = fetch_site_rejection(headers.get('Sec-Fetch-Site'))
        if reason:
            return reason
    return origin_rejection(headers.get('Origin'), self_port, is_loopback)


def register_self_port(app, port):
    """Sunucunun bağlandığı portu köken kapısına bildirir; portu döndürür.

    Hem ortam değişkenine (paketli başlatıcıyla aynı ad; sonradan içe
    aktarılan kod da görür) hem ``app.config``'e yazar (``hrma/app.py``
    ortam değişkenini yalnız içe aktarılırken okur; ``hrma/run.py`` ise
    uygulamayı portu seçmeden ÖNCE içe aktarıyor).
    """
    port = int(port)
    os.environ[SELF_PORT_ENV] = str(port)
    app.config[SELF_PORT_CONFIG_KEY] = port
    return port
