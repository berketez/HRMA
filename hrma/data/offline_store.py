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
"""

import copy
import json
import os
import sys
import tempfile
from datetime import datetime
from typing import Any, Dict, Optional

# Paketle gelen salt okunur snapshot (testler bu degiskeni monkeypatch'ler)
SNAPSHOT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'offline_snapshot.json')

CACHE_FILENAME = 'propellant_cache.json'

# path -> (mtime, parsed_json) — ayni dosyayi tekrar tekrar parse etmemek icin
_read_memo: Dict[str, tuple] = {}


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


def _json_safe(value: Any) -> Any:
    """Degeri JSON-serilestirilebilir hale getir (numpy tipleri dahil)."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    # numpy skaler/dizileri: item()/tolist() ile yerli tiplere indir
    if type(value).__module__ == 'numpy':
        if hasattr(value, 'item') and getattr(value, 'ndim', 0) == 0:
            try:
                return _json_safe(value.item())
            except (ValueError, TypeError):
                pass
        if hasattr(value, 'tolist'):
            try:
                return _json_safe(value.tolist())
            except (ValueError, TypeError):
                pass
    return str(value)  # son care


def _read_json(path: str) -> Optional[Dict]:
    """JSON dosyasini oku; mtime degismediyse memo'dan don."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None

    memo = _read_memo.get(path)
    if memo is not None and memo[0] == mtime:
        return memo[1]

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None

    if not isinstance(data, dict):
        return None
    _read_memo[path] = (mtime, data)
    return data


def get(key: str) -> Optional[Dict]:
    """Anahtari once kullanici cache'inde, sonra snapshot'ta ara."""
    for path in (user_cache_path(), SNAPSHOT_PATH):
        doc = _read_json(path)
        if not doc:
            continue
        entry = (doc.get('entries') or {}).get(key)
        if isinstance(entry, dict) and 'data' in entry:
            return entry['data']
    return None


def put(key: str, data: Dict) -> bool:
    """Veriyi kullanici cache'ine zaman damgasiyla, atomik olarak yaz."""
    path = user_cache_path()
    try:
        directory = os.path.dirname(path)
        os.makedirs(directory, exist_ok=True)

        existing = _read_json(path)
        doc = copy.deepcopy(existing) if existing else {}
        entries = doc.setdefault('entries', {})
        entries[key] = {
            'data': _json_safe(data),
            'timestamp': datetime.now().isoformat(timespec='seconds'),
        }

        fd, tmp_path = tempfile.mkstemp(prefix='.propellant_cache_', suffix='.tmp', dir=directory)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(doc, f, ensure_ascii=False, indent=1, default=str)
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
