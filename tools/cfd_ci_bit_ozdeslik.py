#!/usr/bin/env python3
"""Euler bit-özdeşlik sözleşmesini KOŞULAN PLATFORMDA kurar (ÖH P13B1-03).

Neden gerekli
-------------
``tests/cfd/test_euler_bit_ozdesligi.py`` 1e-12 bit-özdeşlik beyanı taşır ama
karşılaştırdığı dört referansın DÖRDÜ de ``darwin/arm64``ta dondurulmuştur
(``data/cfd_referans/*.npz`` künyeleri). CI ``ubuntu`` koştuğu için her vaka
"platform farklı" dalına, yani TOLERANS dalına düşüyor: 1e-12 beyanı CI'da
BİR KEZ bile sınanmıyordu (defter P13B1-03).

Bu araç sözleşmeyi platformdan bağımsız biçimde kurar: aynı vakayı İKİ AYRI
SÜREÇTE çözer ve iki korunumlu durumu BİT DÜZEYİNDE karşılaştırır. Ölçülen
şey referansın taşınabilirliği değil, ÇÖZÜCÜNÜN o platformdaki
BELİRLENİMİDİR — bit-özdeşlik sözleşmesinin dayandığı önerme budur.

Ayrı süreç şart: aynı süreçte ikinci çözüm, karma tohumu (PYTHONHASHSEED),
sözlük sırası ve ilk çağrıda kurulan önbellekler gibi süreç ömrüne bağlı
etkileri PAYLAŞIR ve onları göremez.

FAIL-CLOSED: çözüm yakınsamazsa, vaka kaydı okunamazsa ya da alt süreç
düşerse çıkış kodu 1'dir — "ölçemedim" yeşile sayılmaz.

Kullanım:
    PYTHONPATH=. python3 tools/cfd_ci_bit_ozdeslik.py
    PYTHONPATH=. python3 tools/cfd_ci_bit_ozdeslik.py --vaka izantropik_60x12
    PYTHONPATH=. python3 tools/cfd_ci_bit_ozdeslik.py --rapor rapor.json
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import platform
import subprocess
import sys
import tempfile

KOK = pathlib.Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:                          # pragma: no cover
    sys.path.insert(0, str(KOK))

#: CI'da koşulan varsayılan küme. Küçük ızgaralar seçildi: sözleşme
#: BELİRLENİM sözleşmesidir, ızgara boyu onu güçlendirmez ama CI süresini
#: doğrusal büyütür (60x12 ~5 s, 120x24 ~4 kat).
VARSAYILAN_VAKALAR = ('izantropik_60x12', 'sok_60x12')

#: Sözleşmenin beyan ettiği bağıl sapma tabanı. Bu araç TAM SIFIR bekler;
#: eşik yalnız hükmü insan diline çevirirken kullanılır.
BEYAN_EDILEN_BANT = 1e-12


def _coz_ve_yaz(kunye, hedef):
    """Alt süreç girişi: vakayı çözer, korunumlu durumu ``hedef``e yazar."""
    import numpy as np
    from hrma.cfd.euler_core import prim_to_cons_axisym
    from tests.cfd.conftest import EULER_REFERANS_VAKALARI, euler_referans_coz

    vaka = EULER_REFERANS_VAKALARI[kunye]
    _, sonuc = euler_referans_coz(kunye)
    if not sonuc['converged']:
        raise SystemExit(f'{kunye}: koşum yakınsamadı '
                         f'({sonuc["convergence_basis"]})')
    f = sonuc['fields']
    U = prim_to_cons_axisym(f['rho_kg_m3'], f['u_z_m_s'], f['u_r_m_s'],
                            f['pressure_Pa'], vaka['cozucu']['gamma'])
    np.save(hedef, np.ascontiguousarray(U, dtype=np.float64))
    return 0


def _alt_surec(kunye, hedef, tohum):
    cevre = dict(os.environ, PYTHONPATH=str(KOK), PYTHONHASHSEED=str(tohum),
                 PYTHONDONTWRITEBYTECODE='1')
    r = subprocess.run(
        [sys.executable, str(pathlib.Path(__file__).resolve()),
         '--_coz', kunye, '--_hedef', str(hedef)],
        cwd=str(KOK), capture_output=True, text=True, timeout=3600, env=cevre)
    return r.returncode, (r.stdout + r.stderr)[-800:]


def kos(kunyeler):
    """Her vakayı iki ayrı süreçte çözer; hüküm sözlüğü döndürür."""
    import numpy as np
    hukum = {
        'platform': sys.platform,
        'machine': platform.machine(),
        'python': platform.python_version(),
        'numpy': np.__version__,
        'beyan_edilen_bant': BEYAN_EDILEN_BANT,
        'vakalar': {},
    }
    with tempfile.TemporaryDirectory() as d:
        for kunye in kunyeler:
            a = pathlib.Path(d, f'{kunye}_a.npy')
            b = pathlib.Path(d, f'{kunye}_b.npy')
            kod_a, cik_a = _alt_surec(kunye, a, 0)
            kod_b, cik_b = _alt_surec(kunye, b, 12345)
            if kod_a != 0 or kod_b != 0 or not a.exists() or not b.exists():
                hukum['vakalar'][kunye] = {
                    'hukum': 'OLCULEMEDI',
                    'cikis_a': kod_a, 'cikis_b': kod_b,
                    'gunluk': (cik_a + cik_b)[-600:]}
                continue
            Ua, Ub = np.load(a), np.load(b)
            if Ua.shape != Ub.shape:
                hukum['vakalar'][kunye] = {'hukum': 'SEKIL FARKLI',
                                           'a': list(Ua.shape),
                                           'b': list(Ub.shape)}
                continue
            mutlak = float(np.max(np.abs(Ua - Ub)))
            olcek = float(np.max(np.abs(Ua))) or 1.0
            bagil = mutlak / olcek
            hukum['vakalar'][kunye] = {
                'hukum': 'BIT-AYNI' if mutlak == 0.0 else 'AYRISTI',
                'bit_ayni': mutlak == 0.0,
                'max_mutlak_fark': mutlak,
                'max_bagil_fark': bagil,
                'bant_icinde': bagil <= BEYAN_EDILEN_BANT,
                'sekil': list(Ua.shape),
            }
    return hukum


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--vaka', action='append',
                    help=f'vaka künyesi (varsayılan: {", ".join(VARSAYILAN_VAKALAR)})')
    ap.add_argument('--rapor', help='hüküm JSON`unun yazılacağı yol')
    ap.add_argument('--_coz', help=argparse.SUPPRESS)
    ap.add_argument('--_hedef', help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    if args._coz:                                    # alt süreç kipi
        return _coz_ve_yaz(args._coz, args._hedef)

    kunyeler = args.vaka or list(VARSAYILAN_VAKALAR)
    hukum = kos(kunyeler)
    metin = json.dumps(hukum, ensure_ascii=False, indent=2)
    print(metin)
    if args.rapor:
        pathlib.Path(args.rapor).write_text(metin + '\n', encoding='utf-8')

    kotu = [k for k, v in hukum['vakalar'].items() if not v.get('bit_ayni')]
    if kotu:
        print(f'\nEuler bit-ozdeslik sozlesmesi {sys.platform}/'
              f'{platform.machine()} platformunda KURULMADI: {kotu}',
              file=sys.stderr)
        return 1
    print(f'\nEuler bit-ozdeslik sozlesmesi {sys.platform}/'
          f'{platform.machine()} platformunda KURULDU '
          f'({len(kunyeler)} vaka, iki ayri surec, max fark 0.0)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
