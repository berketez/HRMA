"""
Kalici cevrimdisi propellant veri deposu (offline store).

Iki katmanli okuma:
1. Kullanici cache dosyasi (yazilabilir): platforma uygun kullanici-veri dizini
   altinda propellant_cache.json. Basarili canli ag cekimleri buraya yazilir.
   - macOS  : ~/Library/Application Support/HRMA/
   - Windows: %APPDATA%/HRMA/
   - Linux  : $XDG_DATA_HOME/HRMA/ veya ~/.local/share/HRMA/
   Ortam degiskeni HRMA_USER_DATA_DIR ile dizin degistirilebilir (test icin).
2. Paketle gelen snapshot (salt okunur): hrma/data/offline_snapshot.json.
   Kullanici cache'inde bulunmayan anahtarlar snapshot'tan okunur.

Paket dizini salt-okunur olabilecegi icin (PyInstaller bundle) paket icine
asla yazilmaz; yazma yalnizca kullanici-veri dizinine yapilir (tmp + rename
ile atomik). Anahtarlar make_key() ile uretilir; float parametreler
yuvarlanir ki anahtar sayisi patlamasin.

Eszamanlilik (v2.6.26): put() bir OKU-DEGISTIR-YAZ dizisidir. Denetimde
8 surec x 60 yazma sonunda 480 kaydin 413'u KAYBOLDU (%86): her surec
dosyayi kendi okudugu hâlin uzerine yaziyordu, son yazan kazaniyordu.
Artik tum dizi surecler arasi ozel (exclusive) bir dosya kilidi altinda
yurur ve kilit altinda dosya TAZE okunur (memo atlanir). get() de derin
kopya dondurur; cagiran donen sozlugu degistirse bile sureç ici onbellek
bozulmaz (ayni desen: hrma/engines/cea_bridge.py:399-402).
"""

import copy
import json
import os
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Optional

try:  # POSIX (macOS, Linux)
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None

try:  # Windows
    import msvcrt
except ImportError:  # pragma: no cover - POSIX
    msvcrt = None

# Paketle gelen salt okunur snapshot (testler bu degiskeni monkeypatch'ler)
SNAPSHOT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'offline_snapshot.json')

CACHE_FILENAME = 'propellant_cache.json'

#: Surecler arasi yazma kilidi dosyasi (icerigi kullanilmaz, yalniz kilit
#: tasiyicisidir; cache dosyasinin kendisi kilitlenmez cunku os.replace ile
#: inode degisir ve kilit kaybolurdu)
LOCK_FILENAME = 'propellant_cache.lock'

#: Kilit bekleme ust siniri [s]. Asilirsa yazma atlanir (put() False doner);
#: uygulama asla kilitte asili kalmaz.
LOCK_TIMEOUT_SECONDS = 30.0

# path -> ((mtime_ns, size), parsed_json) — ayni dosyayi tekrar tekrar parse
# etmemek icin. Boyut da anahtarda: ayni nanosaniyede iki yazma olursa
# bayat memo servis edilmesin.
_read_memo: Dict[str, tuple] = {}

# Surec ici yazma kilidi (ayni surecteki thread'ler icin); surecler arasi
# koruma _exclusive_lock ile saglanir.
_write_lock = threading.RLock()


class OfflineStoreLockError(OSError):
    """Yazma kilidi zaman asimina ugradi."""


@contextmanager
def _exclusive_lock(directory: str):
    """Surecler arasi ozel yazma kilidi (POSIX flock / Windows msvcrt).

    Kilit ayri bir .lock dosyasi uzerindedir; hedef JSON os.replace ile
    degistirildigi icin (inode degisir) hedefin kendisi kilitlenemez.
    """
    lock_path = os.path.join(directory, LOCK_FILENAME)
    handle = open(lock_path, 'a+b')
    try:
        if fcntl is not None:
            deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
            while True:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise OfflineStoreLockError(
                            f"offline store lock timeout after "
                            f"{LOCK_TIMEOUT_SECONDS:g}s")
                    time.sleep(0.01)
        elif msvcrt is not None:  # pragma: no cover - Windows yolu
            deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
            while True:
                try:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise OfflineStoreLockError(
                            f"offline store lock timeout after "
                            f"{LOCK_TIMEOUT_SECONDS:g}s")
                    time.sleep(0.01)
        # Ne fcntl ne msvcrt varsa (egzotik platform) surec ici kilitle
        # yetinilir; sessizce yanlis sonuc uretmek yerine calismaya devam.
        yield
    finally:
        try:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            elif msvcrt is not None:  # pragma: no cover - Windows yolu
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        handle.close()


def _user_data_dir() -> str:
    """Platforma uygun yazilabilir kullanici-veri dizini."""
    override = os.environ.get('HRMA_USER_DATA_DIR')
    if override:
        return override

    home = os.path.expanduser('~')
    if sys.platform == 'darwin':
        return os.path.join(home, 'Library', 'Application Support', 'HRMA')
    if os.name == 'nt':
        base = os.environ.get('APPDATA') or os.path.join(home, 'AppData', 'Roaming')
        return os.path.join(base, 'HRMA')
    base = os.environ.get('XDG_DATA_HOME') or os.path.join(home, '.local', 'share')
    return os.path.join(base, 'HRMA')


def user_cache_path() -> str:
    """Kullanici cache dosyasinin tam yolu."""
    return os.path.join(_user_data_dir(), CACHE_FILENAME)


def make_key(source: str, *parts: Any) -> str:
    """Kaynak + parametrelerden deterministik anahtar uret.

    Float'lar 2 ondaliga yuvarlanip :g ile bicimlenir (20.0 -> "20",
    2.5 -> "2.5") — boylece 20.0000001 gibi degerler ayni anahtara duser.
    Ornek: make_key('webapi', 'rp1', 'lox', 20.0, 2.5) -> "webapi:rp1|lox|20|2.5"
    """
    formatted = []
    for part in parts:
        if isinstance(part, bool):
            formatted.append(str(part).lower())
        elif isinstance(part, float):
            formatted.append(f"{round(part, 2):g}")
        elif isinstance(part, int):
            formatted.append(str(part))
        else:
            formatted.append(str(part).strip().lower())
    return f"{source}:" + "|".join(formatted)


def json_safe(value: Any) -> Any:
    """Degeri JSON-serilestirilebilir hale getir (numpy tipleri dahil)."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    # numpy skaler/dizileri: item()/tolist() ile yerli tiplere indir
    if type(value).__module__ == 'numpy':
        if hasattr(value, 'item') and getattr(value, 'ndim', 0) == 0:
            try:
                return json_safe(value.item())
            except (ValueError, TypeError):
                pass
        if hasattr(value, 'tolist'):
            try:
                return json_safe(value.tolist())
            except (ValueError, TypeError):
                pass
    return str(value)  # son care


#: Geriye donuk ad (eski cagrilar kirilmasin)
_json_safe = json_safe


def _read_json(path: str, use_memo: bool = True) -> Optional[Dict]:
    """JSON dosyasini oku; dosya imzasi degismediyse memo'dan don.

    ``use_memo=False`` yazma kilidi altinda kullanilir: okunan hâlin
    diskteki en son hâl oldugundan emin olunmali, yoksa okuma-degistirme-
    yazma dizisi kaybolan kayit uretir.
    """
    try:
        st = os.stat(path)
    except OSError:
        return None
    imza = (st.st_mtime_ns, st.st_size)

    if use_memo:
        memo = _read_memo.get(path)
        if memo is not None and memo[0] == imza:
            return memo[1]

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None

    if not isinstance(data, dict):
        return None
    _read_memo[path] = (imza, data)
    return data


def get(key: str) -> Optional[Dict]:
    """Anahtari once kullanici cache'inde, sonra snapshot'ta ara.

    DERIN KOPYA doner: memo'daki ayristirilmis belge cagirana sizmaz.
    Bulgu: paylasilan mutable nesne donuyordu; cagiran donen sozlugu
    degistirdiginde surec ici onbellek de bozuluyordu (ayni desen dogru
    cozulmus hâliyle hrma/engines/cea_bridge.py:399-402'de mevcuttu).
    """
    for path in (user_cache_path(), SNAPSHOT_PATH):
        doc = _read_json(path)
        if not doc:
            continue
        entry = (doc.get('entries') or {}).get(key)
        if isinstance(entry, dict) and 'data' in entry:
            return copy.deepcopy(entry['data'])
    return None


def put(key: str, data: Dict) -> bool:
    """Veriyi kullanici cache'ine zaman damgasiyla, atomik olarak yaz.

    Tum oku-degistir-yaz dizisi surecler arasi ozel kilit altindadir;
    kilit altinda dosya TAZE okunur. Boylece paralel yazmalarda kayit
    kaybi olmaz (olcum: 8 surec x 60 yazma -> 0 kayip; duzeltme oncesi
    480 kaydin 413'u kayboluyordu).
    """
    path = user_cache_path()
    try:
        directory = os.path.dirname(path)
        os.makedirs(directory, exist_ok=True)

        # Serilestirme kilit DISINDA yapilir: kilit tutma suresi kisa kalsin
        payload = json_safe(data)
        timestamp = datetime.now().isoformat(timespec='seconds')

        with _write_lock, _exclusive_lock(directory):
            existing = _read_json(path, use_memo=False)
            doc = copy.deepcopy(existing) if isinstance(existing, dict) else {}
            entries = doc.get('entries')
            if not isinstance(entries, dict):
                entries = {}
                doc['entries'] = entries
            entries[key] = {'data': payload, 'timestamp': timestamp}

            fd, tmp_path = tempfile.mkstemp(prefix='.propellant_cache_', suffix='.tmp', dir=directory)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(doc, f, ensure_ascii=False, indent=1, default=str)
                    f.flush()
                    # Kilit birakilmadan once icerik diske insin: cokme
                    # aninda bos/yarim dosya ile kalinmasin
                    os.fsync(f.fileno())
                os.replace(tmp_path, path)  # atomik: tmp + rename
            except BaseException:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        return True
    except (OSError, TypeError, ValueError) as e:
        print(f"Offline store write skipped: {e}")
        return False
