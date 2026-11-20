#!/usr/bin/env python3
"""CI hesap ortamı künyesi + iki bit-aynılık sondası (3.0.7 SÜREÇ kalem 4).

Neden
-----
3.0.6 yayın treninde CI'ın her tam koşusu ~%40-50 sahte kırmızı verdi. İki
test Linux'ta "koşudan koşuya" son basamakta ayrışıyordu:

* ``tests/test_v306_kati_tane.py::test_k2_kartus_tane_fea_bit_ayni`` —
  tane kesiti FEA'sının port gerinimi; ÖLÇÜLDÜ (CI günlükleri): yalnız İKİ
  değer görülüyor, ``100 * 0.005312855644371872`` (çapa) ve
  ``100 * 0.005312855644371993`` (rc.4, rc.9, 11 ve 13 Kas gecelik).
  Ayrışma ``100 *`` çarpımında değil, FEA çıktısının kendisinde (~139 ulp).
* ``tests/test_d17_termo_ucus_a1.py::TestP4B314RuzgarBoyutu::
  test_ruzgarsiz_kosum_bit_ayni`` — 6-DOF/yörünge menzili; rc.5'te bağıl
  1,39e-6 (``capa_rel`` payı 1e-6), 15 Eki'de 3,6e-7.

Aynı commit'in (e2f8ff17e) beş gecelik koşusunda k2 iki kez kırmızı, üç kez
yeşil; kırmızı olduğu iki koşuda dilim 3 işi 36,0 / 36,2 dk, yeşil olduğu
üçünde 18,1 / 22,6 / 27,0 dk sürdü — yani ayrışma koşucu sınıfına bağlı.
GitHub'ın ``ubuntu-latest`` filosu farklı işlemcili sanal makinelerden
oluşur; numpy (SIMD dağıtımı: AVX512 makinede SVML yolları) ve OpenBLAS
(``DYNAMIC_ARCH`` çekirdek seçimi: Zen / Haswell / SkylakeX) çalışma anında
işlemciye göre FARKLI kod yolu seçer ve kayan nokta işlem sırası değişir.
CI günlüklerinde işlemci bilgisi YOKTU; bu araç onu ve sonuçları basar.

Onarım (``.github/workflows/tests.yml`` ``pytest`` işinin ortamı): BLAS
çekirdek ailesi (``OPENBLAS_CORETYPE``), iş parçacığı sayısı ve numpy SIMD
dağıtımı (``NPY_DISABLE_CPU_FEATURES``: AVX512 ailesi) SABİTLENİR; böylece
hangi makine gelirse gelsin aynı kod yolu koşar. Tolerans değişmez.

Komutlar
--------
``kunye [--olc] [--json YOL]``
    Bu sürecin künyesi: işletim sistemi, işlemci modeli ve bayrakları, numpy
    taban/dağıtım/etkin SIMD özellikleri, yüklü OpenBLAS kütüphanelerinin
    çekirdek adı ve iş parçacığı sayısı, sabitleme değişkenleri. ``--olc``:
    iki sondanın değeri (``repr`` ve ``float.hex``).
``iki-kip --json YOL``
    Sondaları alt süreçte iki kez koşar: iş ortamıyla (SABİTLİ) ve sabitleme
    değişkenleri silinmiş ortamla (SABİTSİZ). Kök gösterimi: aynı makinede
    sabitsiz değer sabitliden farklıysa ayrışmayı makinenin kod yolu seçimi
    yapıyordur.
``karsilastir --dizin DİZİN``
    Dilim işlerinin künyelerini toplar (yalnız standart kütüphane), işlemci ⟷
    değer tablosunu basar. SABİTLİ değerler bütün dilimlerde bit-aynı değilse
    çıkış 1 (belirlenimcilik sözleşmesi bozuk).
"""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import io
import json
import os
import pathlib
import platform
import subprocess
import sys
from typing import Dict, List, Optional

KOK = pathlib.Path(__file__).resolve().parents[1]

#: CI'da kod yolunu sabitleyen ortam — değerlerin TEK kaynağı. tests.yml
#: (iş akışı düzeyi ``env``) ve release.yml (``testler`` işi) bunun AYNASIDIR;
#: bekçi: tests/test_v307_surec.py::test_ci_hesap_ortami_tek_kaynaktan.
#:
#: * ``OPENBLAS_CORETYPE=Zen``: OpenBLAS (numpy ve scipy tekerleklerindeki
#:   DYNAMIC_ARCH kopyaları) hangi işlemcide olursa olsun Zen çekirdeklerini
#:   (AVX2 + FMA3) seçer; AMD koşucular bunu zaten seçer, Intel AVX512
#:   koşucular SkylakeX çekirdeklerine geçmez.
#: * ``NPY_DISABLE_CPU_FEATURES``: numpy'nin çalışma anı SIMD dağıtımında
#:   AVX512 ailesi kapalı → Intel koşucu da AMD gibi AVX2 yollarını koşar
#:   (SVML aşkın işlevleri, x86-simd-sort). Makinede olmayan özelliği
#:   kapatmak sessizdir (numpy 1.26.4 yerelde ölçüldü); dağıtım listesinde
#:   olmayan ad yalnız ImportWarning verir (varsayılan süzgeçte gizli).
#: * İş parçacığı sayısı 4: GitHub'ın 4 çekirdekli standart koşucusunun
#:   bugünkü varsayılanı; açık yazılınca koşucu boyutuna bağlı kalmaz.
SABIT_ORTAM = {
    'OPENBLAS_CORETYPE': 'Zen',
    'OPENBLAS_NUM_THREADS': '4',
    'OMP_NUM_THREADS': '4',
    'NPY_DISABLE_CPU_FEATURES': ('AVX512F AVX512CD AVX512_KNL AVX512_KNM AVX512_SKX '
                                 'AVX512_CLX AVX512_CNL AVX512_ICL AVX512_SPR'),
}
SABIT_DEGISKENLER = tuple(SABIT_ORTAM)
KUNYE_ADI = 'ci-hesap-kunyesi.json'
#: Sondaların ölçtüğü iki değer (anahtar → açıklama).
SONDALAR = {
    'k2_kartus_fea_yuzde': 'test_v306_kati_tane::test_k2_kartus_tane_fea_bit_ayni '
                           '(100 × max_bore_strain)',
    'ruzgarsiz_menzil_m': 'test_d17_termo_ucus_a1::TestP4B314RuzgarBoyutu::'
                          'test_ruzgarsiz_kosum_bit_ayni (range_distance)',
}


# ---------------------------------------------------------------------------
# Künye
# ---------------------------------------------------------------------------
def _islemci() -> Dict[str, object]:
    bilgi: Dict[str, object] = {'model': None, 'bayraklar': [], 'cekirdek': os.cpu_count()}
    if sys.platform.startswith('linux'):
        try:
            metin = pathlib.Path('/proc/cpuinfo').read_text(encoding='utf-8', errors='replace')
        except OSError:
            metin = ''
        for satir in metin.splitlines():
            if satir.startswith('model name') and bilgi['model'] is None:
                bilgi['model'] = satir.split(':', 1)[1].strip()
            if satir.startswith('flags'):
                bayrak = set(satir.split(':', 1)[1].split())
                bilgi['bayraklar'] = sorted(bayrak & {'avx', 'avx2', 'fma', 'avx512f',
                                                      'avx512bw', 'avx512vl', 'avx512dq'})
                break
    elif sys.platform == 'darwin':
        try:
            bilgi['model'] = subprocess.run(
                ['sysctl', '-n', 'machdep.cpu.brand_string'], capture_output=True,
                text=True, timeout=10).stdout.strip() or None
        except (OSError, subprocess.SubprocessError):
            pass
    return bilgi


def _yuklu_kutuphaneler() -> List[str]:
    """Süreçteki paylaşımlı kütüphane yolları (Linux /proc, macOS dyld)."""
    if sys.platform.startswith('linux'):
        try:
            satirlar = pathlib.Path('/proc/self/maps').read_text().splitlines()
        except OSError:
            return []
        return sorted({s.split()[-1] for s in satirlar if '/' in s.split()[-1]})
    if sys.platform == 'darwin':
        libc = ctypes.CDLL(None)
        libc._dyld_get_image_name.restype = ctypes.c_char_p
        libc._dyld_get_image_name.argtypes = [ctypes.c_uint32]
        return sorted({libc._dyld_get_image_name(i).decode('utf-8', 'replace')
                       for i in range(libc._dyld_image_count())})
    return []


def _openblas() -> List[Dict[str, object]]:
    """Yüklü her OpenBLAS'ın çekirdek adı, iş parçacığı sayısı, yapılandırması."""
    sonuc = []
    for yol in _yuklu_kutuphaneler():
        if 'openblas' not in pathlib.Path(yol).name.lower():
            continue
        kayit: Dict[str, object] = {'yol': yol}
        try:
            lib = ctypes.CDLL(yol)
        except OSError as hata:
            kayit['hata'] = str(hata)
            sonuc.append(kayit)
            continue
        for ad, alan, tur in (('get_corename', 'cekirdek', ctypes.c_char_p),
                              ('get_config', 'yapilandirma', ctypes.c_char_p),
                              ('get_num_threads', 'is_parcacigi', ctypes.c_int)):
            for onek in ('openblas_', 'scipy_openblas_'):
                for sonek in ('', '64_'):
                    islev = getattr(lib, onek + ad + sonek, None)
                    if islev is None:
                        continue
                    islev.restype = tur
                    deger = islev()
                    kayit[alan] = deger.decode() if isinstance(deger, bytes) else deger
                    break
                if alan in kayit:
                    break
        sonuc.append(kayit)
    return sonuc


def _numpy_simd() -> Dict[str, object]:
    import numpy
    try:
        from numpy.core import _multiarray_umath as m
    except ImportError:  # numpy 2
        from numpy._core import _multiarray_umath as m  # type: ignore
    return {'surum': numpy.__version__,
            'taban': list(getattr(m, '__cpu_baseline__', [])),
            'dagitim': list(getattr(m, '__cpu_dispatch__', [])),
            'etkin': sorted(k for k, v in getattr(m, '__cpu_features__', {}).items() if v)}


def kunye() -> Dict[str, object]:
    import numpy  # noqa: F401 — BLAS'ı yükler
    import scipy.linalg  # noqa: F401 — scipy'nin BLAS'ını yükler
    import scipy.sparse.linalg  # noqa: F401
    return {
        'platform': '%s/%s' % (sys.platform, platform.machine()),
        'python': platform.python_version(),
        'islemci': _islemci(),
        'numpy': _numpy_simd(),
        'scipy': __import__('scipy').__version__,
        'openblas': _openblas(),
        'sabitler': {ad: os.environ.get(ad) for ad in SABIT_DEGISKENLER},
        'dilim': os.environ.get('HRMA_CI_DILIM'),
    }


# ---------------------------------------------------------------------------
# Sondalar — testlerin AYNI çağrıları (test dosyalarına dokunulmadı)
# ---------------------------------------------------------------------------
def _sessiz():
    yigin = contextlib.ExitStack()
    yigin.enter_context(contextlib.redirect_stdout(io.StringIO()))
    yigin.enter_context(contextlib.redirect_stderr(io.StringIO()))
    return yigin


def sonda_k2() -> float:
    """``test_k2_kartus_tane_fea_bit_ayni``: kartuş yüklü bates, 60 bar."""
    if str(KOK) not in sys.path:
        sys.path.insert(0, str(KOK))
    from hrma.app import app
    app.config['TESTING'] = True
    ornek = KOK / 'examples' / 'Example Solid KNDX BATES 75mm.hrma'
    alanlar = json.loads(ornek.read_text(encoding='utf-8'))['inputs']['fields']
    with app.test_client() as c, _sessiz():
        r = c.post('/calculate_solid', json=dict(alanlar, grain_support='cartridge_loaded',
                                                 chamber_pressure=60))
        if r.status_code != 200:
            raise RuntimeError('calculate_solid %s' % r.status_code)
        j = r.get_json()
        gs = j['structural_analysis']['grain_structural']
        gd = j['grain_design']
        govde = {'grain_type': 'bates', 'propellant_type': j['propellant_type'],
                 'outer_diameter_mm': gd['outer_diameter_mm'],
                 'core_diameter_mm': gd['inner_diameter_mm'],
                 'chamber_pressure_bar': j['chamber_pressure'],
                 'grain_length_mm': gd['grain_length_mm'],
                 'grain_support': 'cartridge_loaded',
                 'ambient_temp': gs['storage_temperature_k'],
                 'case_radial_expansion_mm': gs['case_radial_expansion_mm']}
        r = c.post('/api/fea/planar-grain', json=govde)
        if r.status_code != 200:
            raise RuntimeError('planar-grain %s' % r.status_code)
    return 100 * r.get_json()['fea']['scalars']['max_bore_strain']


def sonda_menzil() -> float:
    """``test_ruzgarsiz_kosum_bit_ayni``: rüzgârsız, 85°, paraşüt 2 m²."""
    if str(KOK) not in sys.path:
        sys.path.insert(0, str(KOK))
    from hrma.analysis.trajectory_analysis import TrajectoryAnalyzer
    ta = TrajectoryAnalyzer()
    ta.set_vehicle_parameters(mass_dry=20.0, diameter=0.15, drag_coefficient=0.5, length=2.5)
    motor = {'thrust': 3000.0, 'burn_time': 5.0, 'propellant_mass_total': 10.0,
             'total_impulse': 15000.0}
    with _sessiz():
        r = ta.calculate_trajectory(motor, {'launch_angle': 85.0, 'wind_speed': 0.0,
                                            'parachute_area': 2.0})
    return r['performance']['trajectory_metrics']['range_distance']


def olc() -> Dict[str, Dict[str, str]]:
    sonuc = {}
    for ad, islev in (('k2_kartus_fea_yuzde', sonda_k2), ('ruzgarsiz_menzil_m', sonda_menzil)):
        try:
            x = islev()
            sonuc[ad] = {'repr': repr(x), 'hex': float(x).hex()}
        except Exception as hata:  # noqa: BLE001 — künye ölçümü düşerse adıyla yazılır
            sonuc[ad] = {'hata': '%s: %s' % (type(hata).__name__, str(hata)[:200])}
    return sonuc


# ---------------------------------------------------------------------------
# Komutlar
# ---------------------------------------------------------------------------
def _yaz(veri, yol: Optional[str]):
    metin = json.dumps(veri, ensure_ascii=False, indent=1)
    if yol:
        pathlib.Path(yol).write_text(metin + '\n', encoding='utf-8')
    return metin


def _alt_surec(sabitli: bool) -> Dict[str, object]:
    ortam = dict(os.environ)
    if not sabitli:
        for ad in SABIT_DEGISKENLER:
            ortam.pop(ad, None)
    ortam['PYTHONPATH'] = str(KOK) + os.pathsep + ortam.get('PYTHONPATH', '')
    s = subprocess.run([sys.executable, str(pathlib.Path(__file__).resolve()), 'kunye', '--olc'],
                       capture_output=True, text=True, timeout=900, env=ortam, cwd=str(KOK))
    if s.returncode != 0:
        return {'hata': 'çıkış %d: %s' % (s.returncode, s.stderr[-800:])}
    return json.loads(s.stdout)


def _ozet_satiri(veri: Dict[str, object]) -> str:
    k = veri.get('kunye', veri)
    isl = (k.get('islemci') or {}) if isinstance(k, dict) else {}
    cekirdek = ','.join(str(b.get('cekirdek')) for b in (k.get('openblas') or []))
    avx512 = 'AVX512F' in ((k.get('numpy') or {}).get('etkin') or [])
    return '%s | OpenBLAS %s | numpy AVX512 %s' % (isl.get('model'), cekirdek or '-',
                                                    'AÇIK' if avx512 else 'kapalı')


def komut_kunye(a) -> int:
    veri = {'kunye': kunye()}
    if a.olc:
        veri['olcum'] = olc()
    print(_yaz(veri, a.json))
    return 0


def komut_iki_kip(a) -> int:
    veri = {'sabitli': _alt_surec(True), 'sabitsiz': _alt_surec(False),
            'dilim': os.environ.get('HRMA_CI_DILIM')}
    _yaz(veri, a.json)
    for kip in ('sabitli', 'sabitsiz'):
        v = veri[kip]
        print('%-8s %s' % (kip, _ozet_satiri(v) if 'kunye' in v else v.get('hata')))
        for ad in SONDALAR:
            print('          %-22s %s' % (ad, (v.get('olcum') or {}).get(ad)))
    return 0 if all('kunye' in veri[k] for k in ('sabitli', 'sabitsiz')) else 1


def komut_karsilastir(a) -> int:
    dosyalar = sorted(pathlib.Path(a.dizin).rglob(KUNYE_ADI))
    if not dosyalar:
        print('künye yok: %s altında %s bulunamadı' % (a.dizin, KUNYE_ADI))
        return 1
    satirlar, degerler = [], {ad: set() for ad in SONDALAR}
    hatalar = []
    for yol in dosyalar:
        veri = json.loads(yol.read_text(encoding='utf-8'))
        for kip in ('sabitli', 'sabitsiz'):
            v = veri.get(kip) or {}
            if 'kunye' not in v:
                hatalar.append('%s %s: %s' % (yol.parent.name, kip, v.get('hata')))
                continue
            olcum = v.get('olcum') or {}
            for ad in SONDALAR:
                d = (olcum.get(ad) or {}).get('repr') or ('HATA ' + str((olcum.get(ad) or {}).get('hata')))
                if kip == 'sabitli':
                    degerler[ad].add(d)
            satirlar.append('%-6s %-8s %s | %s' % (
                veri.get('dilim') or yol.parent.name, kip, _ozet_satiri(v),
                ' '.join('%s=%s' % (ad, (olcum.get(ad) or {}).get('repr')) for ad in SONDALAR)))
    print('\n'.join(satirlar))
    for h in hatalar:
        print('HATA', h)
    bozuk = [ad for ad, kume in degerler.items() if len(kume) != 1]
    for ad, kume in degerler.items():
        print('SABİTLİ %-22s %d ayrı değer: %s' % (ad, len(kume), sorted(kume)))
    if bozuk or hatalar:
        print('BELİRLENİMCİLİK BOZUK: sabitli ortamda dilimler arasında farklı değer '
              '(%s) — işlemci sütununa bakın' % ', '.join(bozuk or ['ölçüm hatası']))
        return 1
    print('BELİRLENİMCİLİK TAMAM: %d dilim, sabitli değerler bit-aynı' % len(dosyalar))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    alt = ap.add_subparsers(dest='komut', required=True)
    k = alt.add_parser('kunye')
    k.add_argument('--olc', action='store_true')
    k.add_argument('--json')
    i = alt.add_parser('iki-kip')
    i.add_argument('--json', required=True)
    c = alt.add_parser('karsilastir')
    c.add_argument('--dizin', required=True)
    a = ap.parse_args(argv)
    return {'kunye': komut_kunye, 'iki-kip': komut_iki_kip,
            'karsilastir': komut_karsilastir}[a.komut](a)


if __name__ == '__main__':
    sys.exit(main())
