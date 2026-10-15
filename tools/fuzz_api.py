#!/usr/bin/env python3
"""HRMA API fuzz düzeneği (V3 SG-1; karar §28-33, §27-11).

Kendi düzeneğimiz: yeni bağımlılık YOK (hypothesis/atheris kullanılmaz).
Ürünün bütün uçları (``app.url_map``) tohumlu rastgele ve sınır değer
girdileriyle Flask ``test_client`` üzerinden sınanır; gerçek sunucu açılmaz.

Güvenli düzenek (her koşuda, ``hrma`` içe aktarılmadan ÖNCE kurulur):

* **Dış ağ kalkanı** — ``socket.socket.connect``/``connect_ex``,
  ``socket.create_connection`` ve ``urllib`` açılışı yerel olmayan hedefe
  istisna atar; ayrıca ``socket.connect`` denetim olayı (audit hook) C
  düzeyindeki bağlantıları da keser. Engellenen deneme SAYILIR ve rapora
  girer (bulgu değildir; kalkanın işidir).
* **Süreç/yan etki kalkanı** — ``subprocess``/``os.system``/``os.exec*``/
  ``os.posix_spawn``/``os.fork``/``webbrowser.open``/``os.startfile``/
  ``os.kill`` denetim olayları engellenir; ``os._exit`` etkisizleştirilir;
  güncelleme yardımcıları (indirme, kurulum, tarayıcı açma, sürüm denetimi)
  kayıt tutan yerine geçenlerle değiştirilir.
* **Dosya kalkanı** — ``HOME``, ``TMPDIR``, ``HRMA_PROJECTS_DIR``,
  ``HRMA_USER_DATA_DIR``, ``HRMA_TILE_CACHE_DIR``, ``HRMA_TEMP``,
  ``MPLCONFIGDIR``, ``NUMBA_CACHE_DIR`` ve çalışma dizini geçici köke
  yönlendirilir. Geçici kök DIŞINA yazma/silme/taşıma denemesi denetim
  olayında engellenir ve ``yan_etki`` bulgusu olarak kaydedilir; ayrıca
  depo ağacının (``hrma/``, ``data/``, ``examples/``) koşu öncesi/sonrası
  dosya izi karşılaştırılır.

Kabul (her istek): HTTP 500 yok (503 süre bütçesi hariç); doğrulama sınıfı
≤ ``VALIDATION_TIME_LIMIT_S``, geçerli-uç değer sınıfı ≤
``VALID_EDGE_TIME_LIMIT_S``; yanıtta kaçışsız betik ya da şablon
değerlendirmesi yok; JSON yanıt katı JSON (NaN/Infinity sızmaz); geçici kök
dışında dosya yan etkisi yok; bellek tepesi artışı ≤
``MEMORY_PEAK_LIMIT_BYTES``.

Kullanım::

    python3 tools/fuzz_api.py --kip hizli --cikti /yol/sonuc.json
    HRMA_FUZZ_KIP=tam python3 tools/fuzz_api.py --cikti /yol/sonuc.json

Çıkış kodu: bulgu yoksa 0, bulgu varsa 1, düzenek hatasında 2.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import math
import os
import pathlib
import random
import re
import resource
import signal
import socket
import sys
import tempfile
import time
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Adlandırılmış sabitler (CLAUDE.md §11: ikinci literal kopya yok)
# ---------------------------------------------------------------------------

#: Varsayılan tohum (koşu günü, 14 Eki 2026). Aynı tohum aynı vakaları üretir.
FUZZ_DEFAULT_SEED = 20261014
#: Kip seçen çevre değişkeni; ``hizli`` (CI) ya da ``tam`` (elle).
FUZZ_MODE_ENV = 'HRMA_FUZZ_KIP'
FUZZ_MODES = ('hizli', 'tam')
#: Uç başına vaka sayısı.
FAST_CASES_PER_ENDPOINT = 3
FULL_CASES_PER_ENDPOINT = 30
#: Kabul süre sınırları (s).
VALIDATION_TIME_LIMIT_S = 2.0
VALID_EDGE_TIME_LIMIT_S = 30.0
#: Takılma sayılan sert sınır (s): istek bu sürede dönmezse kesilir.
VALIDATION_HARD_TIMEOUT_S = 20.0
VALID_EDGE_HARD_TIMEOUT_S = 45.0
#: Ağır uçta yalnız doğrulama sınıfı gider; yine de sert sınır.
HEAVY_HARD_TIMEOUT_S = 10.0
#: Tek isteğin bellek tepesi artışı tavanı (bayt).
MEMORY_PEAK_LIMIT_BYTES = 1024 ** 3
#: Girdi sınıflarının boyutları.
DEEP_JSON_LEVELS = 1000
#: JSON gövde kapısını zorlayan çok derin gövde (bayt olarak tavanın altında).
EXTREME_DEEP_JSON_LEVELS = 100_000
LONG_STRING_CHARS = 200_000
#: JSON gövde kapısının (``app._JSON_BODY_GATE_MAX_BYTES``) üstünde ama genel
#: gövde tavanının altında kalan nesne-olmayan gövde için hedef bayt.
OVER_GATE_PAD_FACTOR = 1.25
KEY_EXPLOSION_KEYS = 20_000
#: Kip başına toplam duvar saati bütçesi (s): CI hızlı kipi 60 s, elle tam
#: kip 40 dk (SG-1 brifi).
MODE_WALL_BUDGET_S = {'hizli': 60.0, 'tam': 2400.0}
#: Kalkan öz sınamasının bağlandığı belgeleme adresi (RFC 5737 TEST-NET-3;
#: yönlendirilmez, kalkan bağlantıdan ÖNCE keser).
SELF_TEST_REMOTE_ADDRESS = ('203.0.113.1', 9)
#: Sunucunun kendini bildirdiği port (köken kapısı için).
FUZZ_SELF_PORT = 8080
#: Raporda istek gövdesinin kırpılma uzunluğu.
REPORT_BODY_HEAD_CHARS = 240
#: Yansıma/şablon değerlendirmesi imzası.
SENTINEL = 'HRMAFZ'
SENTINEL_END = 'ZFAMRH'

#: Ağır uçlar (CFD, FEA, 3B, kampanya, toplu tarama): YALNIZ yapısal
#: doğrulama sınıfı gönderilir (geçerli değerle çözücü çalıştırılmaz).
HEAVY_RULES = {
    '/api/cfd/nozzle': 'CFD çözücü',
    '/api/cfd-analysis': 'CFD (emekli, 501)',
    '/api/fea/structural': 'FEA',
    '/api/fea/thermal': 'FEA',
    '/api/fea/planar-grain': 'FEA',
    '/api/six-dof-analysis': '6 serbestlik dereceli yörünge (60 s bütçe)',
    '/api/trajectory-analysis': 'yörünge',
    '/api/solid-monte-carlo': 'Monte Carlo kampanyası',
    '/parametric-analysis': 'parametrik tarama',
    '/api/uncertainty-analysis': 'belirsizlik kampanyası',
    '/api/correlation-report': 'korelasyon raporu (her çağrı tam koşu)',
    '/api/generate-3d': '3B geometri',
    '/api/detailed-cad/<motor_type>': '3B CAD',
    '/export_tank_cad': 'CAD dışa aktarım',
    '/export_solid_motor_cad': 'CAD dışa aktarım',
    '/export_liquid_cad': 'CAD dışa aktarım',
    '/api/export-step': '3B STEP dışa aktarım',
    '/api/export-stl': '3B STL dışa aktarım',
    '/api/export-stl-zip': '3B STL dışa aktarım',
    '/api/export-cad': '3B CAD dışa aktarım',
    '/api/export-complete-zip': '3B paket dışa aktarım',
    '/api/generate-complete-package': '3B paket dışa aktarım',
    '/api/professional-analysis': 'toplu analiz (emekli, 501)',
    '/api/kinetic-analysis': 'kinetik (emekli, 501)',
}

#: Yan etkili uçlar: kodları okundu (rapor), yan etkileri yerine geçenle ya da
#: geçici dizinle etkisiz; YALNIZ doğrulama sınıfı gönderilir.
SIDE_EFFECT_RULES = {
    '/api/user-guide/open': 'masaüstü görüntüleyici açar (subprocess open); '
                            'HRMA_HEADLESS=1 + süreç kalkanı',
    '/api/update/check': 'GitHub sürüm denetimi (ağ); yerine geçen',
    '/api/update/download': 'sürüm paketi indirir; yerine geçen',
    '/api/update/install': 'paketi kurar, uygulamayı yeniden başlatır '
                           '(os._exit); yerine geçen',
    '/api/update/open-download': 'sistem tarayıcısını açar; yerine geçen',
    '/api/tile/cache/clear': 'karo önbelleğini siler; önbellek geçici kökte',
    '/api/tile/<layer_key>/<int:z>/<int:x>/<int:y>': 'GIBS karo vekili (ağ + '
                            'disk); ağ kalkanı, önbellek geçici kökte',
    '/api/projects/save': 'proje dizinine yazar; dizin geçici kökte',
    '/api/projects/delete': 'projeyi çöpe taşır; dizin geçici kökte',
}

#: Tamamen dışarıda kalan (uç, metod) çiftleri ve gerekçesi.
EXCLUDED = {
    ('/api/correlation-report', 'GET'): 'gövdesiz GET her çağrıda tam '
        'korelasyon koşusu başlatır; doğrulama sınıfı kurulamaz (ağır)',
}

#: Kendi taşıyıcısı olan yükleme uçları.
UPLOAD_RULES = ('/api/import/ork', '/api/import/motor-file',
                '/api/import/step', '/api/validation/upload-csv')

#: Ürünün başlıksız/JSON dışı gövdeyi meşru saydığı uçlar (gövde kapısının
#: ``_NON_JSON_BODY_ENDPOINTS`` kümesinin kural karşılığı; uçtan okunur).
_NON_JSON_ENDPOINT_NAMES_ATTR = '_NON_JSON_BODY_ENDPOINTS'

# Girdi sınıfları ----------------------------------------------------------

#: Sınıf adı -> (kabul süre sınırı türü). 'gecerli_uc' dışındaki her sınıf
#: doğrulama sınıfıdır.
VALID_EDGE_CLASS = 'gecerli_uc'

JSON_FIELD_CLASSES = (
    'tip_karisikligi', 'sayisal_gecersiz', 'buyuk_tam_sayi', 'uzun_dize',
    'unicode', 'yol_kacisi', 'enjeksiyon', 'derin_json_alan',
)
JSON_BODY_CLASSES = (
    'bos_govde', 'yanlis_content_type', 'json_olmayan_govde', 'bozuk_json',
    'derin_json_govde', 'anahtar_patlamasi', 'eksik_alan', 'fazla_alan',
    'buyuk_nesne_olmayan_govde',
)
#: Ağır uçlara giden YAPISAL doğrulama sınıfları (çözücüye ulaşamaz: gövde
#: kapısı ya da ucun ilk satırı reddeder).
HEAVY_CLASSES = ('bos_govde', 'yanlis_content_type', 'json_olmayan_govde',
                 'bozuk_json', 'derin_json_govde',
                 'buyuk_nesne_olmayan_govde')

TYPE_POOL = ('1', 'abc', [1, 2], {'a': 1}, None, True, False, [], {}, '')
INVALID_NUMBERS = (float('nan'), float('inf'), float('-inf'))
#: JSON metnine ham yazılan taşma belirteci (``json.loads`` → inf).
OVERFLOW_TOKEN = '1e999'
VALID_EDGE_NUMBERS = (1e308, -1e308, -0.0, 5e-324, 0, -1, 1e-12, 1e12,
                      2 ** 53 + 1)
#: ``float()`` dönüşümünde OverflowError üreten büyük tam sayı.
HUGE_INT = 10 ** 400
UNICODE_POOL = ('\u202eRTL', 'a\u200bb', 'e\u0301', '\ud800', '\U0001F600',
                'a\x00b', '\ufeff', 'İıĞğŞş', '\u0000' * 4)
PATH_POOL = ('../../../../etc/passwd', '/etc/passwd',
             '..\\..\\windows\\win.ini', 'a\x00.hrma', '%2e%2e%2f%2e%2e',
             'C:\\Windows\\x', '~/x', '....//....//x', '/', '.')
INJECTION_POOL = (
    f'<script>alert("{SENTINEL}")</script>',
    f'"><img src=x onerror=alert(1)>{SENTINEL}',
    f'{SENTINEL}{{{{7*7}}}}{SENTINEL_END}',
    f'{SENTINEL}${{7*7}}{SENTINEL_END}',
    f'{SENTINEL}#{{7*7}}{SENTINEL_END}',
    f'{SENTINEL}{{0.__class__}}{SENTINEL_END}',
    f'{SENTINEL}%(x)s%s%n{SENTINEL_END}',
    "=cmd|' /C calc'!A0",
    '@SUM(1+1)*cmd|x',
    "'; DROP TABLE t;--",
)
WRONG_CONTENT_TYPES = ('text/plain', 'application/x-www-form-urlencoded',
                       'multipart/form-data; boundary=x', 'application/xml',
                       None)
NON_OBJECT_BODIES = ('[]', '[1,2,3]', '42', '"metin"', 'null', 'true',
                     '-0.0', 'NaN')
MALFORMED_BODIES = (b'{"a":', b'{', b"{'a':1}", b'\xff\xfe\x00',
                    b'{"a":1}}', b'{"a":1,}', b'\x00', b'[{"a":')
EXTRA_FIELDS = {'__proto__': {'polluted': True}, 'constructor': None,
                f'{SENTINEL}_extra': 1}


#: Bilinçli 5xx: 503 = çözücü süre bütçesi aşıldı (beyanlı); 501 = emekli
#: uç halefini adlandırır (``/api/cfd-analysis`` vb.).
INTENTIONAL_5XX = frozenset({501, 503})
#: Üçüncü taraf kütüphanenin kendi paket dizinine yazdığı çalışma dosyası
#: (rocketcea, NASA CEA Fortran girdisi ``f.inp``): kullanıcı dizini değildir;
#: kalkan izin verir ama SAYAR ve rapora yazar (paketleme devri).
THIRD_PARTY_WRITE_PACKAGES = ('rocketcea',)


class FuzzTimeout(BaseException):
    """İstek sert süre sınırını aştı (``except Exception`` yakalamaz)."""


class ShieldBlocked(PermissionError):
    """Kalkan bir dış etkiyi (ağ, süreç, dosya) engelledi."""


# ---------------------------------------------------------------------------
# Kalkanlar
# ---------------------------------------------------------------------------

class Shield:
    """Ağ, süreç ve dosya kalkanı; denetim olayları + yamalar.

    ``active`` bayrağı yalnız istek atılırken açıktır; denetim kancası süreç
    boyunca kalır (Python kaldırmaya izin vermez), bayrak kapalıyken hiçbir
    şey yapmaz.
    """

    PROCESS_EVENTS = frozenset({
        'subprocess.Popen', 'os.system', 'os.exec', 'os.posix_spawn',
        'os.spawn', 'os.fork', 'os.forkpty', 'os.startfile',
        'webbrowser.open', 'os.kill', 'os.killpg', 'pty.spawn',
    })
    FILE_MUTATION_EVENTS = frozenset({
        'os.remove', 'os.rmdir', 'os.rename', 'os.replace', 'os.mkdir',
        'os.truncate', 'os.symlink', 'os.link', 'shutil.rmtree',
        'shutil.move', 'shutil.copyfile', 'os.chmod', 'os.chown',
        'os.utime',
    })
    _WRITE_FLAGS = (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND
                    | os.O_TRUNC)

    def __init__(self, allowed_roots, third_party_roots=()):
        self.allowed_roots = [os.path.realpath(str(p)) for p in allowed_roots]
        self.third_party_roots = [os.path.realpath(str(p))
                                  for p in third_party_roots]
        self.third_party_writes = {}
        self.active = False
        self.network_blocked = []
        self.process_blocked = []
        self.file_blocked = []
        self.sqlite_paths = set()
        self.request_events = []
        self._installed = False

    # -- yardımcılar --------------------------------------------------------
    @staticmethod
    def is_local_address(address):
        if isinstance(address, (str, bytes)):
            return True  # AF_UNIX
        if not isinstance(address, tuple) or not address:
            return False
        host = address[0]
        if isinstance(host, bytes):
            host = host.decode('ascii', 'replace')
        host = str(host).strip('[]').lower()
        return (host in ('localhost', '::1', '0:0:0:0:0:0:0:1')
                or host.startswith('127.'))

    def _inside_allowed(self, path):
        if path is None:
            return True
        if isinstance(path, int):
            return True  # açık tanımlayıcı
        try:
            text = os.fsdecode(path)
        except (TypeError, ValueError):
            return False
        if text in (os.devnull, '/dev/null', 'nul'):
            return True
        real = os.path.realpath(os.path.abspath(text))
        for root in self.allowed_roots:
            if real == root or real.startswith(root + os.sep):
                return True
        for root in self.third_party_roots:
            if real.startswith(root + os.sep):
                self.third_party_writes[real] = (
                    self.third_party_writes.get(real, 0) + 1)
                return True
        return False

    def _record(self, bucket, item):
        bucket.append(item)
        self.request_events.append(item)

    # -- denetim kancası ----------------------------------------------------
    def _audit(self, event, args):
        if not self.active:
            return
        if event == 'socket.connect':
            address = args[1] if len(args) > 1 else None
            if not self.is_local_address(address):
                self._record(self.network_blocked,
                             {'olay': event, 'hedef': repr(address)[:120]})
                raise ShieldBlocked(
                    f'HRMA fuzz kalkanı: dış ağ engellendi ({address!r})')
            return
        if event in ('urllib.Request',):
            url = str(args[0]) if args else ''
            if not re.match(r'^https?://(127\.|localhost|\[::1\])', url):
                self._record(self.network_blocked,
                             {'olay': event, 'hedef': url[:120]})
                raise ShieldBlocked(
                    f'HRMA fuzz kalkanı: dış ağ engellendi ({url[:80]})')
            return
        if event in self.PROCESS_EVENTS:
            if event == 'os.kill' and args and args[0] == os.getpid() \
                    and len(args) > 1 and args[1] == 0:
                return
            self._record(self.process_blocked,
                         {'olay': event, 'arg': repr(args)[:160]})
            raise ShieldBlocked(f'HRMA fuzz kalkanı: {event} engellendi')
        if event == 'open':
            path = args[0] if args else None
            mode = args[1] if len(args) > 1 else None
            flags = args[2] if len(args) > 2 else 0
            writing = False
            if isinstance(mode, str) and any(c in mode for c in 'wax+'):
                writing = True
            if isinstance(flags, int) and flags & self._WRITE_FLAGS:
                writing = True
            if writing and not self._inside_allowed(path):
                self._record(self.file_blocked,
                             {'olay': event, 'yol': os.fsdecode(path)
                              if not isinstance(path, int) else path,
                              'kip': mode})
                raise ShieldBlocked(
                    f'HRMA fuzz kalkanı: geçici kök dışına yazma ({path})')
            return
        if event in self.FILE_MUTATION_EVENTS:
            paths = [a for a in args[:2] if isinstance(a, (str, bytes,
                                                           os.PathLike))]
            for path in paths:
                if not self._inside_allowed(path):
                    self._record(self.file_blocked,
                                 {'olay': event, 'yol': os.fsdecode(path)})
                    raise ShieldBlocked(
                        f'HRMA fuzz kalkanı: geçici kök dışında {event}')
            return
        if event == 'sqlite3.connect':
            database = args[0] if args else None
            if database is not None and not self._inside_allowed(database):
                self.sqlite_paths.add(os.fsdecode(database)
                                      if not isinstance(database, int)
                                      else str(database))
            return

    # -- yamalar --------------------------------------------------------------
    def install(self):
        if self._installed:
            return
        self._installed = True
        sys.addaudithook(self._audit)
        shield = self

        original_connect = socket.socket.connect
        original_connect_ex = socket.socket.connect_ex

        def guarded_connect(sock, address):
            if shield.active and not Shield.is_local_address(address):
                shield._record(shield.network_blocked,
                               {'olay': 'socket.socket.connect',
                                'hedef': repr(address)[:120]})
                raise ShieldBlocked(
                    f'HRMA fuzz kalkanı: dış ağ engellendi ({address!r})')
            return original_connect(sock, address)

        def guarded_connect_ex(sock, address):
            if shield.active and not Shield.is_local_address(address):
                shield._record(shield.network_blocked,
                               {'olay': 'socket.socket.connect_ex',
                                'hedef': repr(address)[:120]})
                raise ShieldBlocked(
                    f'HRMA fuzz kalkanı: dış ağ engellendi ({address!r})')
            return original_connect_ex(sock, address)

        socket.socket.connect = guarded_connect
        socket.socket.connect_ex = guarded_connect_ex

        original_create = socket.create_connection

        def guarded_create(address, *a, **kw):
            if shield.active and not Shield.is_local_address(address):
                shield._record(shield.network_blocked,
                               {'olay': 'socket.create_connection',
                                'hedef': repr(address)[:120]})
                raise ShieldBlocked(
                    f'HRMA fuzz kalkanı: dış ağ engellendi ({address!r})')
            return original_create(address, *a, **kw)

        socket.create_connection = guarded_create

        import urllib.request
        original_open = urllib.request.OpenerDirector.open

        def guarded_open(opener, fullurl, *a, **kw):
            url = fullurl if isinstance(fullurl, str) else getattr(
                fullurl, 'full_url', str(fullurl))
            if shield.active and not re.match(
                    r'^https?://(127\.|localhost|\[::1\])', str(url)):
                shield._record(shield.network_blocked,
                               {'olay': 'urllib.OpenerDirector.open',
                                'hedef': str(url)[:120]})
                raise urllib.error.URLError(
                    'HRMA fuzz kalkanı: dış ağ engellendi')
            return original_open(opener, fullurl, *a, **kw)

        urllib.request.OpenerDirector.open = guarded_open

        def guarded_exit(code=0):
            shield._record(shield.process_blocked,
                           {'olay': 'os._exit', 'arg': repr(code)})
            raise ShieldBlocked('HRMA fuzz kalkanı: os._exit engellendi')

        os._exit = guarded_exit


def prepare_environment(temp_root):
    """Kullanıcı verisi köklerini geçici köke yönlendirir (içe aktarmadan önce).

    Döndürür: geçici kök altındaki dizinlerin sözlüğü.
    """
    temp_root = pathlib.Path(temp_root).resolve()
    dirs = {name: temp_root / name for name in (
        'home', 'tmp', 'projects', 'user_data', 'tiles', 'hrma_temp', 'cwd',
        'mpl', 'numba')}
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    (dirs['home'] / 'Documents').mkdir(exist_ok=True)
    (dirs['home'] / 'Downloads').mkdir(exist_ok=True)
    env = {
        'HOME': dirs['home'],
        'TMPDIR': dirs['tmp'],
        'TMP': dirs['tmp'],
        'TEMP': dirs['tmp'],
        'HRMA_PROJECTS_DIR': dirs['projects'],
        'HRMA_USER_DATA_DIR': dirs['user_data'],
        'HRMA_TILE_CACHE_DIR': dirs['tiles'],
        'HRMA_TEMP': dirs['hrma_temp'],
        'MPLCONFIGDIR': dirs['mpl'],
        'NUMBA_CACHE_DIR': dirs['numba'],
        'XDG_DATA_HOME': dirs['home'] / '.local' / 'share',
        'XDG_CACHE_HOME': dirs['home'] / '.cache',
        'APPDATA': dirs['home'] / 'AppData',
    }
    for key, value in env.items():
        os.environ[key] = str(value)
    os.environ['HRMA_HEADLESS'] = '1'
    os.environ['MPLBACKEND'] = 'Agg'
    os.environ['BROWSER'] = 'echo'
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    sys.dont_write_bytecode = True
    tempfile.tempdir = None
    os.chdir(str(dirs['cwd']))
    return dirs


def third_party_write_roots():
    """``THIRD_PARTY_WRITE_PACKAGES`` paketlerinin kurulu dizinleri."""
    import importlib.util
    roots = []
    for name in THIRD_PARTY_WRITE_PACKAGES:
        spec = importlib.util.find_spec(name)
        if spec is not None and spec.submodule_search_locations:
            roots.extend(spec.submodule_search_locations)
    return roots


def install_update_stubs():
    """Güncelleme yardımcılarını kayıt tutan yerine geçenlerle değiştirir."""
    from hrma.utils import update_checker
    calls = []

    def stub(name):
        def _stub(*a, **kw):
            calls.append(name)
            return {'status': 'fuzz_stub', 'function': name}
        return _stub

    for name in ('check_for_update', 'start_download', 'download_status',
                 'start_install', 'open_download_in_browser'):
        if hasattr(update_checker, name):
            setattr(update_checker, name, stub(name))
    return calls


def tree_fingerprint(paths):
    """Depo ağacının (mtime, boyut) izi; dosya yan etkisini yakalar."""
    seen = {}
    for base in paths:
        base = pathlib.Path(base)
        if not base.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d != '__pycache__']
            for name in filenames:
                full = os.path.join(dirpath, name)
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                seen[full] = (st.st_mtime_ns, st.st_size)
    return seen


def fingerprint_diff(before, after):
    changed = sorted(p for p in after if before.get(p) != after[p])
    removed = sorted(p for p in before if p not in after)
    return {'degisen_ya_da_yeni': changed, 'silinen': removed}


def max_rss_bytes():
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss if sys.platform == 'darwin' else rss * 1024


# ---------------------------------------------------------------------------
# Yanıt kâhinleri (saf işlevler; bekçi testleri bunları doğrudan sınar)
# ---------------------------------------------------------------------------

def _reject_constant(token):
    raise ValueError(f'katı olmayan JSON belirteci: {token}')


def strict_json_problem(raw_bytes):
    """Yanıt katı JSON değilse sorunu döndürür (NaN/Infinity sızıntısı)."""
    try:
        json.loads(raw_bytes, parse_constant=_reject_constant)
    except ValueError as exc:
        return str(exc)[:160]
    return None


_TEMPLATE_EVAL = re.compile(
    re.escape(SENTINEL) + r'(?:49|<class [^>]*>)' + re.escape(SENTINEL_END))
_RAW_SCRIPT = re.compile(r'<script>alert\("' + re.escape(SENTINEL) + r'"\)',
                         re.IGNORECASE)
_RAW_IMG = re.compile(r'<img src=x onerror=alert\(1\)>' + re.escape(SENTINEL),
                      re.IGNORECASE)


def reflection_problem(body_text, content_type):
    """Yanıtta şablon değerlendirmesi ya da HTML bağlamında kaçışsız yük."""
    if _TEMPLATE_EVAL.search(body_text or ''):
        return 'şablon/biçim değerlendirmesi (imza 49 ya da <class ...>)'
    ctype = (content_type or '').lower()
    if 'json' in ctype:
        return None  # JSON metni HTML değildir (nosniff + application/json)
    if _RAW_SCRIPT.search(body_text or '') or _RAW_IMG.search(body_text or ''):
        return 'HTML yanıtında kaçışsız betik yansıması'
    return None


def spreadsheet_formula_problem(raw_bytes):
    """XLSX yanıtında kullanıcı yükünden doğan formül hücresi."""
    try:
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
            for name in zf.namelist():
                if not name.startswith('xl/worksheets/'):
                    continue
                xml = zf.read(name).decode('utf-8', 'replace')
                for match in re.finditer(r'<f>([^<]*)</f>', xml):
                    if 'cmd' in match.group(1) or SENTINEL in match.group(1):
                        return f'formül hücresi: {match.group(1)[:80]}'
    except (zipfile.BadZipFile, KeyError, OSError):
        return None
    return None


NETWORK_EVENTS = frozenset({
    'socket.connect', 'socket.socket.connect', 'socket.socket.connect_ex',
    'socket.create_connection', 'urllib.Request',
    'urllib.OpenerDirector.open'})
#: Fuzz yükünün süreç argümanına ulaştığını gösteren imler.
_COMMAND_INJECTION_MARKS = (SENTINEL, '../', 'cmd|', '/etc/passwd')


def shield_event_problem(event):
    """Kalkan olayı bulgu mu? Ağ: hayır (kalkanın işi). Süreç: yalnız fuzz
    yükü argümana ulaştıysa (komut enjeksiyonu). Dosya: geçici kök dışına
    her yazma/silme bulgudur."""
    name = event.get('olay')
    if name in NETWORK_EVENTS:
        return None
    if name in Shield.PROCESS_EVENTS or name == 'os._exit':
        arg = str(event.get('arg', ''))
        if any(mark in arg for mark in _COMMAND_INJECTION_MARKS):
            return 'komut_enjeksiyonu'
        return None
    return 'yan_etki'


def classify_response(status, content_type, raw, path, method, case_class,
                      elapsed_s, rss_growth, limits=None):
    """Bir yanıtı kabul ölçütleriyle sınar; bulgu türlerini döndürür."""
    limits = limits or {}
    problems = []
    if status >= 500 and status not in INTENTIONAL_5XX:
        problems.append(('http_500', f'HTTP {status}'))
    # Süre sınıfı yanıttan okunur: uç isteği KABUL ettiyse (2xx) hesap
    # yapılmıştır, geçerli-uç değer sınırı geçerlidir; reddettiyse (4xx)
    # doğrulama sınıfıdır ve hızlı dönmelidir. Geçerli-uç vakası her durumda
    # geniş sınırla ölçülür.
    accepted = status is not None and (200 <= status < 300
                                       or status in INTENTIONAL_5XX)
    limit = (VALID_EDGE_TIME_LIMIT_S
             if case_class == VALID_EDGE_CLASS or accepted
             else VALIDATION_TIME_LIMIT_S)
    limit = limits.get('time', limit)
    if elapsed_s > limit:
        problems.append(('kararlilik_sure',
                         f'{elapsed_s:.2f} s > {limit:.0f} s'))
    if rss_growth > MEMORY_PEAK_LIMIT_BYTES:
        problems.append(('bellek', f'ru_maxrss +{rss_growth / 1e6:.0f} MB'))
    ctype = (content_type or '').lower()
    text = raw.decode('utf-8', 'replace') if raw else ''
    if 'json' in ctype:
        problem = strict_json_problem(raw)
        if problem:
            problems.append(('json_gecersiz', problem))
    elif status >= 400 and (path.startswith('/api/') or method != 'GET'):
        problems.append(('json_olmayan_hata',
                         f'HTTP {status} {ctype or "tipsiz"}'))
    refl = reflection_problem(text, ctype)
    if refl:
        problems.append(('yansima', refl))
    if 'spreadsheetml' in ctype:
        formula = spreadsheet_formula_problem(raw)
        if formula:
            problems.append(('formul_enjeksiyonu', formula))
    return problems


# ---------------------------------------------------------------------------
# Vaka üretimi
# ---------------------------------------------------------------------------

def _deep(levels, kind='dict'):
    value = 1
    for _ in range(levels):
        value = {'a': value} if kind == 'dict' else [value]
    return value


def _deep_text(levels, kind='list'):
    if kind == 'list':
        return '[' * levels + ']' * levels
    return '{"a":' * levels + '1' + '}' * levels


def _json_bytes(obj):
    return json.dumps(obj, allow_nan=True, ensure_ascii=True).encode('utf-8')


def _numeric_fields(seed):
    return [k for k, v in seed.items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)]


def _pick_field(rng, seed, fallback_fields):
    fields = list(seed) or list(fallback_fields) or ['value']
    return rng.choice(sorted(fields))


class Case:
    __slots__ = ('cls', 'sub', 'method', 'path', 'body', 'content_type',
                 'query', 'files', 'headers')

    def __init__(self, cls, sub, method, path, body=None, content_type=None,
                 query=None, files=None, headers=None):
        self.cls = cls
        self.sub = sub
        self.method = method
        self.path = path
        self.body = body
        self.content_type = content_type
        self.query = query
        self.files = files
        self.headers = headers or {}

    def summary(self):
        if self.files is not None:
            body = {k: (v[1] if isinstance(v, tuple) else str(v)[:40])
                    for k, v in self.files.items()}
            body_head = json.dumps(body, ensure_ascii=False)[
                :REPORT_BODY_HEAD_CHARS]
            length = None
        elif isinstance(self.body, (bytes, bytearray)):
            body_head = self.body[:REPORT_BODY_HEAD_CHARS].decode(
                'utf-8', 'replace')
            length = len(self.body)
        else:
            body_head = None
            length = 0
        return {'metod': self.method, 'yol': self.path,
                'sorgu': self.query, 'content_type': self.content_type,
                'govde_bas': body_head, 'govde_bayt': length}


def json_body_case(rng, cls, path, method, seed, fields):
    """JSON gövdeli bir uç için ``cls`` sınıfından tek vaka."""
    ct = 'application/json'
    if cls == VALID_EDGE_CLASS:
        numeric = _numeric_fields(seed)
        body = dict(seed)
        if numeric:
            field = rng.choice(sorted(numeric))
            value = rng.choice(VALID_EDGE_NUMBERS)
        else:
            field = _pick_field(rng, seed, fields)
            value = rng.choice(VALID_EDGE_NUMBERS)
        body[field] = value
        return Case(cls, f'{field}={value!r}', method, path,
                    _json_bytes(body), ct)
    if cls in JSON_FIELD_CLASSES:
        body = dict(seed)
        field = _pick_field(rng, seed, fields)
        if cls == 'tip_karisikligi':
            value = rng.choice(TYPE_POOL)
            body[field] = value
            return Case(cls, f'{field}={value!r}'[:80], method, path,
                        _json_bytes(body), ct)
        if cls == 'sayisal_gecersiz':
            if rng.random() < 0.25:
                body[field] = 0
                raw = _json_bytes(body).replace(
                    f'"{field}": 0'.encode(), f'"{field}": {OVERFLOW_TOKEN}'
                    .encode(), 1)
                return Case(cls, f'{field}={OVERFLOW_TOKEN}', method, path,
                            raw, ct)
            value = rng.choice(INVALID_NUMBERS)
            if rng.random() < 0.3:
                value = str(value)  # "nan" / "inf" dizesi
            body[field] = value
            return Case(cls, f'{field}={value!r}', method, path,
                        _json_bytes(body), ct)
        if cls == 'buyuk_tam_sayi':
            body[field] = rng.choice((HUGE_INT, -HUGE_INT))
            return Case(cls, f'{field}=±10**400', method, path,
                        _json_bytes(body), ct)
        if cls == 'uzun_dize':
            body[field] = rng.choice(('A', 'Ğ', '9')) * LONG_STRING_CHARS
            return Case(cls, f'{field}={LONG_STRING_CHARS} karakter', method,
                        path, _json_bytes(body), ct)
        if cls == 'unicode':
            value = rng.choice(UNICODE_POOL)
            body[field] = value
            return Case(cls, f'{field}={value!r}', method, path,
                        _json_bytes(body), ct)
        if cls == 'yol_kacisi':
            value = rng.choice(PATH_POOL)
            body[field] = value
            return Case(cls, f'{field}={value!r}', method, path,
                        _json_bytes(body), ct)
        if cls == 'enjeksiyon':
            value = rng.choice(INJECTION_POOL)
            body[field] = value
            return Case(cls, f'{field}={value!r}'[:80], method, path,
                        _json_bytes(body), ct)
        if cls == 'derin_json_alan':
            kind = rng.choice(('dict', 'list'))
            body[field] = _deep(DEEP_JSON_LEVELS, kind)
            return Case(cls, f'{field}=derinlik {DEEP_JSON_LEVELS} {kind}',
                        method, path, _json_bytes(body), ct)
    if cls == 'bos_govde':
        return Case(cls, 'b""', method, path, b'', ct)
    if cls == 'yanlis_content_type':
        wrong = rng.choice(WRONG_CONTENT_TYPES)
        return Case(cls, f'Content-Type={wrong}', method, path,
                    _json_bytes(seed), wrong)
    if cls == 'json_olmayan_govde':
        raw = rng.choice(NON_OBJECT_BODIES)
        return Case(cls, raw, method, path, raw.encode(), ct)
    if cls == 'bozuk_json':
        raw = rng.choice(MALFORMED_BODIES)
        return Case(cls, repr(raw), method, path, raw, ct)
    if cls == 'derin_json_govde':
        if rng.random() < 0.5:
            levels, kind = EXTREME_DEEP_JSON_LEVELS, rng.choice(('list',
                                                                 'dict'))
        else:
            levels, kind = DEEP_JSON_LEVELS, 'dict'
        return Case(cls, f'gövde derinlik {levels} {kind}', method, path,
                    _deep_text(levels, kind).encode(), ct)
    if cls == 'anahtar_patlamasi':
        body = dict(seed)
        for i in range(KEY_EXPLOSION_KEYS):
            body[f'k{i}'] = i
        return Case(cls, f'+{KEY_EXPLOSION_KEYS} anahtar', method, path,
                    _json_bytes(body), ct)
    if cls == 'eksik_alan':
        body = dict(seed)
        if body and rng.random() < 0.8:
            field = rng.choice(sorted(body))
            body.pop(field)
            sub = f'-{field}'
        else:
            body = {}
            sub = '{}'
        return Case(cls, sub, method, path, _json_bytes(body), ct)
    if cls == 'fazla_alan':
        body = dict(seed)
        body.update(EXTRA_FIELDS)
        return Case(cls, '+__proto__/constructor', method, path,
                    _json_bytes(body), ct)
    if cls == 'buyuk_nesne_olmayan_govde':
        gate = _json_gate_bytes()
        count = int(gate * OVER_GATE_PAD_FACTOR) // 2
        raw = ('[' + ','.join(['1'] * count) + ']').encode()
        return Case(cls, f'dizi gövde {len(raw)} bayt (> gövde kapısı)',
                    method, path, raw, ct)
    raise ValueError(f'bilinmeyen sınıf: {cls}')


_GATE_CACHE = {}


def _json_gate_bytes():
    if 'gate' not in _GATE_CACHE:
        from hrma import app as app_module
        _GATE_CACHE['gate'] = int(app_module._JSON_BODY_GATE_MAX_BYTES)
    return _GATE_CACHE['gate']


# Yükleme uçları ---------------------------------------------------------------

def _truncated_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr('rocket.ork', '<openrocket>' + 'x' * 2000 + '</openrocket>')
    data = buf.getvalue()
    return data[:len(data) // 2]


def _traversal_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr('../../../../evil.ork', '<openrocket/>')
    return buf.getvalue()


UPLOAD_BLOBS = {
    'rastgele': lambda rng: bytes(rng.getrandbits(8) for _ in range(4096)),
    'bos': lambda rng: b'',
    'kesik_zip': lambda rng: _truncated_zip(),
    'yol_kacisli_zip': lambda rng: _traversal_zip(),
    'xml_dtd': lambda rng: (b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x '
                            b'SYSTEM "file:///etc/passwd">]><r>&x;</r>'),
    'kesik_step': lambda rng: b'ISO-10303-21;\nHEADER;\nFILE_DESCRIPTION((',
    'nan_satirlari': lambda rng: b'time,thrust\n0,NaN\n1,inf\n2,1e999\n',
    'enjeksiyon': lambda rng: ('=cmd|\' /C calc\'!A0,' + INJECTION_POOL[0]
                               + '\n').encode(),
}
UPLOAD_NAMES = ('motor.ork', '../../evil.ork', 'a\x00.ork', 'x.step',
                'x.eng', 'x.rse', 'x.csv', 'x' * 300 + '.ork', '',
                'İçerik.STEP')


def upload_case(rng, path, method, cls):
    blob_name = rng.choice(sorted(UPLOAD_BLOBS))
    blob = UPLOAD_BLOBS[blob_name](rng)
    name = rng.choice(UPLOAD_NAMES)
    if path == '/api/validation/upload-csv':
        if cls == 'yanlis_content_type' or rng.random() < 0.5:
            return Case('bozuk_dosya', f'text/csv {blob_name}', method, path,
                        blob, 'text/csv')
        text = blob.decode('utf-8', 'replace')
        body = {'csv_text': text,
                'predicted_curve': rng.choice(TYPE_POOL)}
        return Case('bozuk_dosya', f'json csv_text {blob_name}', method,
                    path, _json_bytes(body), 'application/json')
    if path == '/api/import/motor-file':
        text = blob.decode('utf-8', 'replace')
        body = {'content': text, 'filename': name,
                'prediction': rng.choice(TYPE_POOL)}
        return Case('bozuk_dosya', f'{blob_name} ad={name[:20]!r}', method,
                    path, _json_bytes(body), 'application/json')
    if path == '/api/import/ork' and rng.random() < 0.3:
        encoded = rng.choice((base64.b64encode(blob).decode(), '!!!yok!!!',
                              ''))
        body = {'content_base64': encoded, 'filename': name}
        return Case('bozuk_dosya', f'json base64 {blob_name}', method, path,
                    _json_bytes(body), 'application/json')
    files = {'file': (io.BytesIO(blob), name)}
    if path == '/api/import/step':
        files['solid_index'] = rng.choice(('-1', 'NaN', '1e999', 'abc',
                                           '99999999999999999999', '0'))
    return Case('bozuk_dosya', f'çok parçalı {blob_name} ad={name[:20]!r}',
                method, path, files=files)


# Yol parametreli ve GET uçları ------------------------------------------------

PATH_ARG_POOL = PATH_POOL + INJECTION_POOL[:3] + UNICODE_POOL[:3] + (
    'x' * 300, '..', 'liquid', 'solid', 'hybrid', 'complete', 'NaN', '-1')
INT_ARG_POOL = (0, 1, 2 ** 31, 2 ** 63, 10 ** 30, 99999999)
QUERY_KEYS = ('lang', 'q', 'refresh', 'motor', 'x')


def _fill_rule(rng, rule, fixed=None):
    """Kuraldaki ``<...>`` değişkenlerini fuzz değerleriyle doldurur."""
    from urllib.parse import quote

    def repl(match):
        spec = match.group(1)
        conv, _, name = spec.rpartition(':')
        if fixed and name in fixed:
            return fixed[name]
        if conv == 'int':
            return str(rng.choice(INT_ARG_POOL))
        value = rng.choice(PATH_ARG_POOL)
        safe = '/' if conv == 'path' else ''
        return quote(value.encode('utf-8', 'surrogatepass'), safe=safe)

    return re.sub(r'<([^>]+)>', repl, rule)


def get_case(rng, rule, method, fixed=None):
    path = _fill_rule(rng, rule, fixed)
    key = rng.choice(QUERY_KEYS)
    value = rng.choice(PATH_POOL + INJECTION_POOL + UNICODE_POOL[:3])
    sub = f'{path[:60]} ?{key}={value!r}'[:100]
    query = {key: value.encode('utf-8', 'surrogatepass').decode(
        'utf-8', 'replace')}
    return Case('sorgu_ve_yol', sub, method, path, query=query)


# ---------------------------------------------------------------------------
# Plan: uç × sınıf
# ---------------------------------------------------------------------------

def _view_fields(view):
    """Görünüm kaynağının okuduğu alan adları (seed yoksa hedef alanlar)."""
    import inspect
    try:
        src = inspect.getsource(view)
    except (OSError, TypeError):
        return []
    names = set(re.findall(r"\.get\(\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]",
                           src))
    names |= set(re.findall(r"\[\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s*\]",
                            src))
    return sorted(names)[:40]


def build_plan(app, rule_filter=None):
    """(kural, metod) başına plan kaydı listesi."""
    from tests.support import uc_katalogu
    catalog = uc_katalogu.kayitlar()
    import hrma.app as app_module
    non_json = getattr(app_module, _NON_JSON_ENDPOINT_NAMES_ATTR)
    plan = []
    for rule in sorted(app.url_map.iter_rules(), key=lambda r: (r.rule,
                                                                r.endpoint)):
        if rule_filter and not re.search(rule_filter, rule.rule):
            continue
        methods = sorted(m for m in (rule.methods or ())
                         if m not in ('HEAD', 'OPTIONS'))
        for method in methods:
            key = (rule.rule, method)
            entry = {'rule': rule.rule, 'method': method,
                     'endpoint': rule.endpoint}
            if key in EXCLUDED:
                entry['kip'] = 'dislandi'
                entry['gerekce'] = EXCLUDED[key]
                plan.append(entry)
                continue
            view = app.view_functions.get(rule.endpoint)
            record = catalog.get(rule.rule) if method == 'POST' else None
            fixed = None
            if record is not None and record.istek_yolu:
                fixed = _fixed_args(rule.rule, record.istek_yolu)
            entry['fixed'] = fixed
            seed = {}
            if record is not None and record.sinif == 'olculebilir':
                try:
                    seed = uc_katalogu.taban_yuk(rule.rule)
                except Exception as exc:  # katalog kaynağı eksikse
                    entry['seed_hata'] = f'{type(exc).__name__}: {exc}'[:160]
                    seed = {}
            entry['seed'] = seed if isinstance(seed, dict) else {}
            entry['fields'] = _view_fields(view) if view else []
            entry['katalog_sinifi'] = record.sinif if record else None
            if rule.rule in HEAVY_RULES:
                entry['kip'] = 'agir'
                entry['gerekce'] = HEAVY_RULES[rule.rule]
                classes = [c for c in HEAVY_CLASSES
                           if not (c == 'yanlis_content_type'
                                   and rule.endpoint in non_json)]
                if rule.endpoint in non_json:
                    # Ucun kendi taşıyıcısı var: yalnız nesne-olmayan JSON
                    # gövde, uç ilk satırında reddeder (çözücüye ulaşmaz).
                    classes = ['json_olmayan_govde',
                               'buyuk_nesne_olmayan_govde']
                entry['classes'] = classes
            elif rule.rule in UPLOAD_RULES:
                entry['kip'] = 'yukleme'
                entry['classes'] = ['bozuk_dosya']
            elif method == 'GET':
                entry['kip'] = ('yan_etkili' if rule.rule in SIDE_EFFECT_RULES
                                else 'get')
                entry['classes'] = ['sorgu_ve_yol']
            elif rule.rule in SIDE_EFFECT_RULES:
                entry['kip'] = 'yan_etkili'
                entry['gerekce'] = SIDE_EFFECT_RULES[rule.rule]
                classes = list(JSON_FIELD_CLASSES) + [
                    c for c in JSON_BODY_CLASSES
                    if not (c == 'yanlis_content_type'
                            and rule.endpoint in non_json)]
                entry['classes'] = classes
            else:
                entry['kip'] = 'tam'
                classes = list(JSON_FIELD_CLASSES) + list(JSON_BODY_CLASSES)
                if entry['seed']:
                    classes.append(VALID_EDGE_CLASS)
                if rule.endpoint in non_json:
                    classes = [c for c in classes
                               if c != 'yanlis_content_type']
                entry['classes'] = classes
            if rule.rule in SIDE_EFFECT_RULES:
                entry['gerekce'] = SIDE_EFFECT_RULES[rule.rule]
            plan.append(entry)
    return plan


def _fixed_args(rule, example_path):
    names = re.findall(r'<(?:[^:>]+:)?([^>]+)>', rule)
    pattern = '^' + re.sub(r'<[^>]+>', '([^/]+)', rule) + '$'
    match = re.match(pattern, example_path)
    if not match:
        return None
    return dict(zip(names, match.groups()))


def generate_cases(entry, n_cases, seed_value, endpoint_index):
    """Bir plan kaydı için ``n_cases`` deterministik vaka."""
    rng = random.Random(f'{seed_value}:{entry["rule"]}:{entry["method"]}')
    classes = entry['classes']
    cases = []
    for i in range(n_cases):
        # Sınıflar dönüşümlü: hızlı kipte uçlar arası kaydırma bütün
        # sınıfların süit genelinde kapsanmasını sağlar.
        cls = classes[(endpoint_index * n_cases + i) % len(classes)]
        if cls == 'sorgu_ve_yol':
            cases.append(get_case(rng, entry['rule'], entry['method'],
                                  entry.get('fixed')))
            continue
        if cls == 'bozuk_dosya':
            cases.append(upload_case(rng, entry['rule'], entry['method'],
                                     cls))
            continue
        path = _fill_rule(rng, entry['rule'], entry.get('fixed')) \
            if '<' in entry['rule'] else entry['rule']
        if entry['kip'] == 'agir' and '<' in entry['rule'] \
                and rng.random() < 0.5:
            path = _fill_rule(rng, entry['rule'])
        cases.append(json_body_case(rng, cls, path, entry['method'],
                                    entry['seed'], entry['fields']))
    return cases


# ---------------------------------------------------------------------------
# Koşu
# ---------------------------------------------------------------------------

def _timeout_handler(signum, frame):
    raise FuzzTimeout()


def send(client, case, hard_timeout_s, shield, captured):
    headers = {'Host': f'127.0.0.1:{FUZZ_SELF_PORT}',
               'Origin': f'http://127.0.0.1:{FUZZ_SELF_PORT}',
               'Sec-Fetch-Site': 'same-origin'}
    headers.update(case.headers)
    kwargs = {'headers': headers, 'method': case.method}
    if case.query:
        kwargs['query_string'] = case.query
    if case.files is not None:
        kwargs['data'] = case.files
        kwargs['content_type'] = 'multipart/form-data'
    elif case.body is not None:
        kwargs['data'] = case.body
        if case.content_type is not None:
            kwargs['content_type'] = case.content_type
    shield.request_events = []
    captured.clear()
    rss0 = max_rss_bytes()
    t0 = time.perf_counter()
    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.setitimer(signal.ITIMER_REAL, hard_timeout_s)
    shield.active = True
    outcome = {}
    try:
        resp = client.open(case.path, **kwargs)
        raw = resp.get_data()
        outcome.update(status=resp.status_code,
                       content_type=resp.headers.get('Content-Type', ''),
                       raw=raw)
        resp.close()
    except FuzzTimeout:
        outcome.update(status=None, takildi=True)
    except BaseException as exc:  # noqa: BLE001 — düzenek her şeyi kaydeder
        outcome.update(status=None, kacan_istisna=f'{type(exc).__name__}: '
                       f'{str(exc)[:200]}')
    finally:
        shield.active = False
        signal.setitimer(signal.ITIMER_REAL, 0)
    outcome['elapsed_s'] = time.perf_counter() - t0
    outcome['rss_growth'] = max_rss_bytes() - rss0
    outcome['shield_events'] = list(shield.request_events)
    outcome['exceptions'] = list(captured)
    return outcome


def run(args):
    mode = args.kip
    n_cases = (args.vaka if args.vaka else
               (FAST_CASES_PER_ENDPOINT if mode == 'hizli'
                else FULL_CASES_PER_ENDPOINT))
    temp_root = pathlib.Path(tempfile.mkdtemp(
        prefix='hrma_fuzz_', dir=args.gecici_kok or None)).resolve()
    dirs = prepare_environment(temp_root)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    watched = [ROOT / 'hrma', ROOT / 'data', ROOT / 'examples']
    before = tree_fingerprint(watched)
    t_import = time.perf_counter()
    from hrma.app import app
    import_s = time.perf_counter() - t_import
    from hrma.security import origin_gate
    import flask
    app.config['TESTING'] = False
    app.config['PROPAGATE_EXCEPTIONS'] = False
    origin_gate.register_self_port(app, FUZZ_SELF_PORT)
    update_calls = install_update_stubs()
    captured = []

    def on_exception(sender, exception, **extra):
        import traceback
        frames = traceback.extract_tb(exception.__traceback__)
        own = [f for f in frames if '/hrma/' in f.filename]
        where = (f'{pathlib.Path(own[-1].filename).relative_to(ROOT)}:'
                 f'{own[-1].lineno}' if own else None)
        captured.append({'tip': type(exception).__name__,
                         'ileti': str(exception)[:200], 'yer': where})

    flask.got_request_exception.connect(on_exception, app)
    shield = Shield([temp_root], third_party_write_roots())
    shield.install()
    client = app.test_client()
    plan = build_plan(app, args.uc)
    t_start = time.perf_counter()
    rss_start = max_rss_bytes()
    findings = []
    endpoints = []
    total_cases = 0
    for index, entry in enumerate(plan):
        summary = {k: entry.get(k) for k in ('rule', 'method', 'endpoint',
                                             'kip', 'gerekce',
                                             'katalog_sinifi', 'seed_hata')}
        if entry['kip'] == 'dislandi':
            summary['vaka'] = 0
            endpoints.append(summary)
            continue
        cases = generate_cases(entry, n_cases, args.tohum, index)
        statuses, class_counts = {}, {}
        slowest = 0.0
        net_count = proc_count = 0
        rss_peak = 0
        for number, case in enumerate(cases):
            if entry['kip'] == 'agir':
                hard = HEAVY_HARD_TIMEOUT_S
            elif case.cls == VALID_EDGE_CLASS:
                hard = VALID_EDGE_HARD_TIMEOUT_S
            else:
                hard = VALIDATION_HARD_TIMEOUT_S
            out = send(client, case, hard, shield, captured)
            total_cases += 1
            class_counts[case.cls] = class_counts.get(case.cls, 0) + 1
            status = out.get('status')
            statuses[str(status)] = statuses.get(str(status), 0) + 1
            slowest = max(slowest, out['elapsed_s'])
            rss_peak = max(rss_peak, out['rss_growth'])
            problems = []
            if out.get('takildi'):
                problems.append(('takilma',
                                 f'{hard:.0f} s sert sınırda kesildi'))
            elif out.get('kacan_istisna'):
                problems.append(('kacan_istisna', out['kacan_istisna']))
            else:
                problems = classify_response(
                    status, out['content_type'], out['raw'], case.path,
                    case.method, case.cls, out['elapsed_s'],
                    out['rss_growth'])
            for ev in out['shield_events']:
                kind = shield_event_problem(ev)
                if kind:
                    problems.append((kind, json.dumps(ev,
                                                      ensure_ascii=False)))
                if ev['olay'] in NETWORK_EVENTS:
                    net_count += 1
                elif ev['olay'] in Shield.PROCESS_EVENTS \
                        or ev['olay'] == 'os._exit':
                    proc_count += 1
            for kind, detail in problems:
                findings.append({
                    'tur': kind, 'ayrinti': detail, 'uc': entry['rule'],
                    'metod': entry['method'], 'vaka_no': number,
                    'sinif': case.cls, 'alt': case.sub,
                    'istek': case.summary(), 'status': status,
                    'sure_s': round(out['elapsed_s'], 3),
                    'yanit_bas': (out.get('raw') or b'')[:200].decode(
                        'utf-8', 'replace'),
                    'istisna': out['exceptions'],
                    'kalkan_olaylari': out['shield_events'],
                })
        summary.update(vaka=len(cases), siniflar=class_counts,
                       durumlar=statuses, en_uzun_s=round(slowest, 3),
                       ag_engellenen=net_count, surec_engellenen=proc_count,
                       en_buyuk_rss_artisi_bayt=rss_peak)
        endpoints.append(summary)
        if args.sure_butcesi and (time.perf_counter() - t_start
                                  > args.sure_butcesi):
            findings.append({'tur': 'butce', 'ayrinti':
                             'duvar saati bütçesi aşıldı; koşu kesildi',
                             'uc': entry['rule'], 'metod': entry['method']})
            break
    duration = time.perf_counter() - t_start
    after = tree_fingerprint(watched)
    diff = fingerprint_diff(before, after)
    if diff['degisen_ya_da_yeni'] or diff['silinen']:
        findings.append({'tur': 'yan_etki', 'uc': '*', 'metod': '*',
                         'ayrinti': 'depo ağacında dosya değişti',
                         'fark': diff})
    result = {
        '_meta': {
            'tohum': args.tohum, 'kip': mode, 'uc_basina_vaka': n_cases,
            'python': sys.version.split()[0], 'kok': str(ROOT),
            'gecici_kok': str(temp_root), 'hrma_ithal_s': round(import_s, 2),
            'sure_s': round(duration, 1),
            'zaman': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
            'rss_bas_bayt': rss_start, 'rss_son_bayt': max_rss_bytes(),
            'uc_kural_metod_sayisi': len(plan),
            'kural_sayisi': len({e['rule'] for e in plan}),
            'vaka_sayisi': total_cases,
            'kalkan': {
                'ag_engellenen': len(shield.network_blocked),
                'ag_hedefleri': sorted({e['hedef'] for e in
                                        shield.network_blocked})[:20],
                'surec_engellenen': len(shield.process_blocked),
                'surec_olaylari': shield.process_blocked[:20],
                'dosya_engellenen': len(shield.file_blocked),
                'dosya_olaylari': shield.file_blocked[:20],
                'sqlite_gecici_kok_disi': sorted(shield.sqlite_paths),
                'ucuncu_taraf_paket_yazmasi': shield.third_party_writes,
                'guncelleme_yerine_gecen_cagrilari': len(update_calls),
            },
            'sabitler': {
                'VALIDATION_TIME_LIMIT_S': VALIDATION_TIME_LIMIT_S,
                'VALID_EDGE_TIME_LIMIT_S': VALID_EDGE_TIME_LIMIT_S,
                'MEMORY_PEAK_LIMIT_BYTES': MEMORY_PEAK_LIMIT_BYTES,
                'DEEP_JSON_LEVELS': DEEP_JSON_LEVELS,
                'EXTREME_DEEP_JSON_LEVELS': EXTREME_DEEP_JSON_LEVELS,
                'LONG_STRING_CHARS': LONG_STRING_CHARS,
                'KEY_EXPLOSION_KEYS': KEY_EXPLOSION_KEYS,
            },
            'depo_agaci_fark': diff,
            'dizinler': {k: str(v) for k, v in dirs.items()},
        },
        'uclar': endpoints,
        'bulgular': findings,
    }
    return result


def shield_self_test(temp_root):
    """Kalkanın gerçekten engellediğini ölçer (bekçi alt süreçte koşar).

    Her deneme kalkan AÇIKKEN yapılır; dönen sözlükte her satır ``True``
    olmalıdır (engellendi). Geçici kök İÇİNE yazma serbest kalmalıdır.
    """
    dirs = prepare_environment(temp_root)
    shield = Shield([pathlib.Path(temp_root).resolve()])
    shield.install()
    outside = pathlib.Path(temp_root).resolve().parent / (
        pathlib.Path(temp_root).name + '_kalkan_disi.txt')
    results = {}

    def attempt(name, func):
        shield.active = True
        try:
            func()
            results[name] = False
        except (ShieldBlocked, OSError) as exc:
            results[name] = isinstance(exc, ShieldBlocked) or (
                'kalkan' in str(exc))
        finally:
            shield.active = False

    import subprocess
    import urllib.request
    attempt('socket_create_connection',
            lambda: socket.create_connection(SELF_TEST_REMOTE_ADDRESS, 1))
    attempt('socket_connect', lambda: socket.socket().connect(
        SELF_TEST_REMOTE_ADDRESS))
    attempt('urllib', lambda: urllib.request.urlopen(
        f'http://{SELF_TEST_REMOTE_ADDRESS[0]}/', timeout=1))
    attempt('subprocess', lambda: subprocess.run(['true'], check=False))
    attempt('os_system', lambda: os.system('true'))
    attempt('os_exit', lambda: os._exit(0))
    attempt('dosya_disari_yazma', lambda: open(outside, 'w').close())
    attempt('dosya_disari_silme', lambda: os.remove(str(outside)))
    shield.active = True
    try:
        inside = dirs['tmp'] / 'ic.txt'
        inside.write_text('x', encoding='utf-8')
        results['ic_yazma_serbest'] = inside.read_text(encoding='utf-8') == 'x'
    finally:
        shield.active = False
    results['disari_dosya_olusmadi'] = not outside.exists()
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--kip', choices=FUZZ_MODES,
                        default=os.environ.get(FUZZ_MODE_ENV, 'hizli'))
    parser.add_argument('--tohum', type=int, default=FUZZ_DEFAULT_SEED)
    parser.add_argument('--vaka', type=int, default=0,
                        help='uç başına vaka (0 = kipin varsayılanı)')
    parser.add_argument('--uc', default=None,
                        help='kural süzgeci (düzenli ifade)')
    parser.add_argument('--cikti', required=True)
    parser.add_argument('--gecici-kok', default=None)
    parser.add_argument('--sure-butcesi', type=float, default=None,
                        help='duvar saati üst sınırı (s); verilmezse kipin '
                             'bütçesi (MODE_WALL_BUDGET_S)')
    parser.add_argument('--kalkan-oz-sinama', action='store_true',
                        help='yalnız kalkanı sına, sonucu --cikti\'ya yaz')
    args = parser.parse_args(argv)
    if args.kip not in FUZZ_MODES:
        parser.error(f'kip {FUZZ_MODES} dışında')
    if args.sure_butcesi is None:
        args.sure_butcesi = MODE_WALL_BUDGET_S[args.kip]
    out = pathlib.Path(args.cikti)
    if args.kalkan_oz_sinama:
        root = tempfile.mkdtemp(prefix='hrma_kalkan_',
                                dir=args.gecici_kok or None)
        result = shield_self_test(root)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=1),
                       encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False))
        return 0 if all(result.values()) else 1
    result = run(args)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1,
                              default=str), encoding='utf-8')
    meta = result['_meta']
    print(f"fuzz: {meta['kip']} tohum={meta['tohum']} "
          f"uç={meta['uc_kural_metod_sayisi']} vaka={meta['vaka_sayisi']} "
          f"bulgu={len(result['bulgular'])} süre={meta['sure_s']} s "
          f"ağ_engellenen={meta['kalkan']['ag_engellenen']}")
    return 1 if result['bulgular'] else 0


if __name__ == '__main__':
    sys.exit(main())
