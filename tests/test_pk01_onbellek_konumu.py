"""PK-01 / P17B4-06 — yakıt önbelleği paketin İÇİNE yazılmaz.

Paketli macOS .app ilk açılışta WebPropellantAPI önbelleğini ``hrma/data``
altına (paket kökü) yazıyordu; imzalı paketin içine her yazım kod imzasını
bozar. Önbellek artık ``USER_DATA_DIR`` altında. Bekçi, dizinin paket kökü
dışında ve kullanıcı veri dizini altında olduğunu ölçer (HRMA_USER_DATA_DIR
geçici dizine yönlendirilir, alt süreçte içe aktarılır).
"""
import json
import pathlib
import subprocess
import sys

KOK = pathlib.Path(__file__).resolve().parents[1]


def _olc(tmp_path):
    kod = (
        "import json, hrma\n"
        "from hrma.data.web_propellant_api import WebPropellantAPI\n"
        "a = WebPropellantAPI()\n"
        "print(json.dumps({'cache': a.cache_dir, 'paket': hrma.__file__}))\n"
    )
    env = {'HRMA_USER_DATA_DIR': str(tmp_path / 'kullanici'), 'PATH': '/usr/bin:/bin',
           'HOME': str(tmp_path), 'MPLBACKEND': 'Agg'}
    r = subprocess.run([sys.executable, '-c', kod], cwd=str(KOK), env=env,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_onbellek_kullanici_veri_dizininde(tmp_path):
    d = _olc(tmp_path)
    cache = pathlib.Path(d['cache']).resolve()
    assert cache == (tmp_path / 'kullanici' / 'propellant_cache').resolve()
    assert cache.is_dir()


def test_onbellek_paket_koku_disinda(tmp_path):
    d = _olc(tmp_path)
    # Paket kökü = hrma paketinin bir üstü (DATA_DIR = <kök>/data orada;
    # paketli .app'te bu dizin bundle'ın içidir).
    kok = pathlib.Path(d['paket']).resolve().parent.parent
    cache = pathlib.Path(d['cache']).resolve()
    assert kok not in cache.parents and cache != kok
