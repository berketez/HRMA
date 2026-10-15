#!/usr/bin/env python3
"""Euler yolunun bit-özdeşlik referanslarını dondurur (viskoz tasarım §11.3).

Viskoz kampanya (docs/mimari/cfd-viskoz-tasarimi.md) Euler çekirdeğine
DOKUNMAMA sözü verir (§5.1 kompozisyon ilkesi). Bu sözün ölçülebilir
karşılığı, V0 başlamadan ÖNCE bugünkü çözücüyle dondurulan dört referans
alandır:

    {60×12, 120×24} × {izantropik, şoklu}

Vaka kurulumu BURADA YAZILMAZ: tek kaynak ``tests/cfd/conftest.py``
içindeki ``EULER_REFERANS_VAKALARI`` kaydıdır (aynı kaydı oturum
fikstürleri ve bekçi de okur). Böylece "referans" ile "testin koştuğu
vaka" ayrı ayrı sürüklenemez.

Dosya içeriği KÜÇÜK tutulur — yalnız yakınsanan korunumlu durum dizisi
U = [ρ, ρu_z, ρu_r, E] (ni, nj, 4) + JSON künye. Alan dizileri (M, T,
kesit ortalamaları) TÜRETİLEBİLİR olduğu için yazılmaz; kalıntı geçmişi
de yazılmaz (ilk/son değerleri künyede).

Bekçi: ``tests/cfd/test_euler_bit_ozdesligi.py``.

Kullanım:
    PYTHONPATH=. python3 tools/cfd_referans_dondur.py            # eksikleri üret
    PYTHONPATH=. python3 tools/cfd_referans_dondur.py --zorla    # hepsini yenile
    PYTHONPATH=. python3 tools/cfd_referans_dondur.py --vaka sok_60x12

DİKKAT: mevcut bir referansı yenilemek (``--zorla``) Euler yolunun
değiştiğini KABUL etmektir. Gerekçesi partinin kaydına yazılmadan
yapılmaz — bekçinin kırmızısını susturmanın kolay yolu budur ve
sözleşmenin anlamını yok eder.
"""

import argparse
import datetime as _dt
import hashlib
import json
import pathlib
import platform
import subprocess
import sys
import time

import numpy as np

KOK = pathlib.Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from hrma.cfd import kernels                                     # noqa: E402
from hrma.cfd.euler_core import (                                # noqa: E402
    prim_to_cons_axisym, residual_axisym,
)
from tests.cfd.conftest import (                                 # noqa: E402
    EULER_REFERANS_VAKALARI, euler_referans_coz, lule_gridi,
)

REFERANS_DIZINI = KOK / 'data' / 'cfd_referans'


def _git_durumu():
    """(commit, kirli, degisen_dosyalar, olculebildi) — üretim anının depo durumu.

    ÖH D19 / altyapi — defter P10B4-14. Eski sürüm git ölçülemediğinde
    ``('', False)`` döndürüyordu: "ölçemedim" hâli TEMİZ sayılıyordu
    (fail-OPEN). Ölçülemeyen durum artık ayrı bir bayrakla taşınır ve kapı
    onu reddeder — ölçemediğimiz şeyi temiz ilan etmeyiz.
    """
    try:
        commit = subprocess.check_output(
            ['git', '-C', str(KOK), 'rev-parse', 'HEAD'],
            text=True, stderr=subprocess.DEVNULL).strip()
        porcelain = subprocess.check_output(
            ['git', '-C', str(KOK), 'status', '--porcelain'],
            text=True, stderr=subprocess.DEVNULL)
    except (subprocess.CalledProcessError, OSError):
        return '', None, [], False
    degisenler = sorted(x[3:].strip() for x in porcelain.splitlines()
                        if x.strip())
    return commit, bool(degisenler), degisenler, True


#: Kirli ağaçtan dondurulan referans YENİDEN ÜRETİLEMEZ: künyedeki commit o
#: dosyanın hangi kaynaktan çıktığını SÖYLEMEZ, çünkü çalışma ağacındaki
#: yamalar commit'te yoktur. ÖLÇÜLDÜ (docs/scofield/raw/OH/D19/altyapi/a1/
#: once_p10b4_14.json): sevk edilen dört Euler referansının DÖRDÜ de
#: ``git_calisma_agaci_kirli: true`` (commit a8e03547) — araç kirliliği
#: künyeye YAZIYOR ama dondurmayı REDDETMİYORDU. Beyan çözüm değildir.
KIRLI_AGAC_GEREKCESI = (
    'Kirli çalışma ağacından dondurulan bit-özdeşlik referansı yeniden '
    'üretilemez: künyedeki commit dosyanın kaynağını temsil etmez. Ya ağacı '
    'temizleyin (git stash / commit) ya da --kirli-agaca-izin-ver ve '
    '--gerekce ile NEDEN kabul edilebilir olduğunu künyeye yazdırın.')


def kirlilik_kapisi(izin=False, gerekce=''):
    """Dondurma öncesi depo durumu kapısı; künyeye yazılacak sözlüğü döndürür.

    FAIL-CLOSED: ağaç kirliyse ya da durum ÖLÇÜLEMİYORSA dondurma
    ``SystemExit`` ile durur. Açık izin verilirse gerekçe ZORUNLUDUR ve
    künyeye yazılır — sessiz istisna bırakılmaz.
    """
    commit, kirli, degisenler, olculebildi = _git_durumu()
    kunye = {
        'git_commit': commit,
        'git_calisma_agaci_kirli': bool(kirli) if olculebildi else None,
        'git_durumu_olculebildi': olculebildi,
        'git_kirli_dosyalar': degisenler[:50],
        'git_kirli_dosya_sayisi': len(degisenler),
        'git_kirli_izin_gerekcesi': '',
    }
    if not olculebildi:
        raise SystemExit(
            'Depo durumu ÖLÇÜLEMEDİ (git yok ya da bu ağaç bir depo değil) — '
            'referansın hangi kaynaktan çıktığı kanıtlanamaz, dondurma '
            'DURDU.\n' + KIRLI_AGAC_GEREKCESI)
    if not kirli:
        return kunye
    ozet = ', '.join(degisenler[:8]) + (' …' if len(degisenler) > 8 else '')
    if not izin:
        raise SystemExit(
            f'Çalışma ağacı KİRLİ ({len(degisenler)} dosya: {ozet}) — '
            'dondurma DURDU.\n' + KIRLI_AGAC_GEREKCESI)
    if not gerekce.strip():
        raise SystemExit(
            '--kirli-agaca-izin-ver verildi ama --gerekce boş — kirli ağaç '
            'istisnası künyeye YAZILMADAN kabul edilmez.')
    kunye['git_kirli_izin_gerekcesi'] = gerekce.strip()
    return kunye


def _numba_surumu():
    if not kernels.NUMBA_AVAILABLE:
        return None
    import numba
    return numba.__version__


def dondur(kunye, zorla=False, depo_kunyesi=None):
    """Tek vakayı koşar ve .npz olarak yazar; (yol, meta) döndürür."""
    yol = REFERANS_DIZINI / f'euler_{kunye}.npz'
    if yol.exists() and not zorla:
        print(f'  {kunye}: dosya zaten var, atlanıyor ({yol.name}) — '
              f'yenilemek için --zorla')
        return yol, None

    vaka = EULER_REFERANS_VAKALARI[kunye]
    t0 = time.perf_counter()
    _, sonuc = euler_referans_coz(kunye)
    sure = time.perf_counter() - t0

    if not sonuc['converged']:
        raise SystemExit(
            f'{kunye}: koşum yakınsamadı ({sonuc["convergence_basis"]}) — '
            f'yakınsamayan alan referans olarak DONDURULMAZ')

    f = sonuc['fields']
    U = prim_to_cons_axisym(f['rho_kg_m3'], f['u_z_m_s'], f['u_r_m_s'],
                            f['pressure_Pa'], vaka['cozucu']['gamma'])
    U = np.ascontiguousarray(U, dtype=np.float64)

    depo = depo_kunyesi if depo_kunyesi is not None else kirlilik_kapisi()
    kalinti = np.asarray(sonuc['residual_history'])
    meta = {
        'kunye': kunye,
        'amac': ('Euler yolunun bit-özdeşlik regresyon referansı — viskoz '
                 'tasarım belgesi §11.3'),
        'grid': {'ni': vaka['ni'], 'nj': vaka['nj']},
        'cozucu': dict(vaka['cozucu']),
        'kosum': {
            # ÜÇ DURUMLU HÜKÜM (OH-D31-15): None = hüküm YARGILANMADI.
            # bool() burada üçüncü durumu False'a ezerdi ve künye
            # "yakınsamadı" diye okunurdu.
            'converged': (None if sonuc['converged'] is None
                          else bool(sonuc['converged'])),
            'convergence_status': sonuc['convergence_status'],
            'convergence_basis': sonuc['convergence_basis'],
            'iterations': int(sonuc['iterations']),
            'residual_last': float(kalinti[-1]),
            'residual_first': float(kalinti[0]),
            'mass_flow_in_kg_s': float(sonuc['mass_flow_in_kg_s']),
            'mass_flow_out_kg_s': float(sonuc['mass_flow_out_kg_s']),
            'mass_balance_rel': float(sonuc['mass_balance_rel']),
            'energy_balance_rel': float(sonuc['energy_balance_rel']),
            'shock_sensor_columns': int(sonuc['shock_sensor_columns']),
            'limiter_frozen_at_iter': (
                None if sonuc['limiter_frozen_at_iter'] is None
                else int(sonuc['limiter_frozen_at_iter'])),
            'wall_clock_s': round(sure, 2),
        },
        'olusturma_tarihi_utc': _dt.datetime.now(
            _dt.timezone.utc).replace(microsecond=0).isoformat(),
        **depo,
        'platform': sys.platform,
        'machine': platform.machine(),
        'platform_tam': platform.platform(),
        'python': platform.python_version(),
        'numpy': np.__version__,
        'numba': _numba_surumu(),
        'kernel_backend': sonuc['kernel_backend'],
        'dizi_beyani': (
            'U = prim_to_cons_axisym(fields.rho_kg_m3, u_z_m_s, u_r_m_s, '
            'pressure_Pa, gamma) — çözücünün YAYIMLADIĞI alanlardan aynı '
            'çekirdek fonksiyonuyla türetildi (çözücünün iç dizisi doğrudan '
            'kopyalanmadı; bekçi de aynı dönüşümden geçer, karşılaştırma '
            'tek yolludur). Birimler SI: [kg/m³, kg/(m²·s), kg/(m²·s), '
            'J/m³].'),
        'uretici': 'tools/cfd_referans_dondur.py',
    }

    REFERANS_DIZINI.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(yol, U=U, meta_json=json.dumps(meta,
                                                       ensure_ascii=False))
    boyut = yol.stat().st_size
    print(f'  {kunye}: {sonuc["iterations"]} iter, {sure:.1f} s, arka uç '
          f'{sonuc["kernel_backend"]}, kalıntı {kalinti[-1]:.3e} → '
          f'{yol.name} ({boyut / 1024:.1f} KiB, ham '
          f'{U.nbytes / 1024:.1f} KiB)')
    return yol, meta


#: ``Pb is None`` dalının kalıntı referansı (ÖH D18 / P6B1-02).
#:
#: ÖLÇÜLEN KUSUR: dört referans vakanın DÖRDÜ de ``Pb`` VERİLMİŞ koşumdur
#: (``conftest.IZANTROPIK_COZUCU``/``SOK_COZUCU``: ``Pb=LULE_PB`` /
#: ``LULE_PB_SOK``). Oysa ``_outlet_state``in ``Pb is None`` dalı ürün
#: ucunun (``/api/cfd/nozzle``) VARSAYILANIDIR ve ``euler_core.py``
#: "Euler yolunun bit-özdeşlik sözleşmesi bu dalın üstünde durur" diye
#: beyan ediyordu. Dal bilerek bozulduğunda dört bekçi de bit-YEŞİL
#: kalıyordu — beyan yanlıştı.
#:
#: ÇÖZÜM ve MALİYETİ: yeni bir ÇÖZÜM dondurulmaz (dört yeni koşu = dakika
#: sınıfı maliyet). Zaten donmuş DÖRT durumun ``Pb=None`` ile alınan
#: KALINTISI dondurulur: tek kalıntı çağrısı (milisaniye sınıfı) ama
#: ``_outlet_state``in ``Pb is None`` dalını GERÇEKTEN çalıştırır, çünkü
#: kalıntı çıkış hayaletini bu daldan kurar. Böylece dalın aritmetiği bit
#: düzeyinde kilitlenir.
PB_NONE_DOSYA = 'euler_pb_none_kalinti.npz'

#: Kalıntının ``Pb`` DIŞINDA hangi ayarlarla alındığı. Vakanın kendi
#: çözücü sözleşmesinden okunur (TEK KAYNAK: conftest); yalnız ``Pb``
#: bilerek ``None``a çevrilir — ölçülen eksen budur.
PB_NONE_KALINTI_ARGLARI = ('gamma', 'R', 'P0', 'T0')


def _pb_none_kalintisi(kunye, U):
    """Donmuş ``U`` durumunun ``Pb=None`` ile alınan dU/dt kalıntısı."""
    vaka = EULER_REFERANS_VAKALARI[kunye]
    c = vaka['cozucu']
    grid = lule_gridi(vaka['ni'], vaka['nj'])
    dudt, aux = residual_axisym(
        np.ascontiguousarray(U, dtype=np.float64), grid,
        *(c[ad] for ad in PB_NONE_KALINTI_ARGLARI), Pb=None)
    return np.ascontiguousarray(dudt, dtype=np.float64), aux


def dondur_pb_none(zorla=False, depo_kunyesi=None):
    """``Pb is None`` dalının kalıntı referansını yazar; (yol, meta) döner.

    Yeni çözüm KOŞULMAZ: ``euler_<kunye>.npz`` dosyalarındaki donmuş
    durumlar okunur. Dolayısıyla bu dosya, dört referans dosyasının
    TÜREVİDİR ve onlar yenilenmeden yenilenmesi anlamsızdır (künyede
    kaynak dosyaların sha256'sı taşınır — kayarsa bekçi söyler).
    """
    yol = REFERANS_DIZINI / PB_NONE_DOSYA
    if yol.exists() and not zorla:
        print(f'  pb_none: dosya zaten var, atlanıyor ({yol.name}) — '
              f'yenilemek için --zorla')
        return yol, None

    diziler = {}
    kaynak_sha = {}
    ozet = {}
    t0 = time.perf_counter()
    for kunye in sorted(EULER_REFERANS_VAKALARI):
        kaynak = REFERANS_DIZINI / f'euler_{kunye}.npz'
        if not kaynak.exists():
            raise SystemExit(
                f'{kunye}: kaynak referans yok ({kaynak.name}) — '
                f'Pb=None kalıntısı donmuş durumdan TÜRETİLİR, önce '
                f'referans alanları üretin.')
        kaynak_sha[kunye] = hashlib.sha256(kaynak.read_bytes()).hexdigest()
        with np.load(kaynak) as z:
            U = np.array(z['U'])
        dudt, aux = _pb_none_kalintisi(kunye, U)
        diziler[kunye] = dudt
        ozet[kunye] = {
            'dudt_abs_max': float(np.max(np.abs(dudt))),
            'mass_flow_in_kg_s': float(aux['mass_flow_in_kg_s']),
            'mass_flow_out_kg_s': float(aux['mass_flow_out_kg_s']),
        }
    sure = time.perf_counter() - t0

    depo = depo_kunyesi if depo_kunyesi is not None else kirlilik_kapisi()
    meta = {
        'amac': ('_outlet_state Pb is None dalının BİT-ÖZDEŞLİK referansı '
                 '(ÖH D18 / P6B1-02). Dört referans vakanın dördü de Pb '
                 'VERİLMİŞ koşumdur; ürün ucunun varsayılanı olan Pb=None '
                 'dalı dondurmanın DIŞINDAYDI.'),
        'yontem': ('euler_<kunye>.npz içindeki DONMUŞ durum okunur ve '
                   'residual_axisym(..., Pb=None) bir kez çağrılır — yeni '
                   'çözüm koşulmaz. Kalıntı çıkış hayaletini _outlet_state '
                   'üzerinden kurduğu için dal gerçekten çalışır.'),
        'kalinti_arglari': list(PB_NONE_KALINTI_ARGLARI),
        'Pb': None,
        'outlet_subsonic_anchor': 'extrapolate (residual_axisym varsayılanı)',
        'kaynak_referans_sha256': kaynak_sha,
        'ozet': ozet,
        'wall_clock_s': round(sure, 3),
        'olusturma_tarihi_utc': _dt.datetime.now(
            _dt.timezone.utc).replace(microsecond=0).isoformat(),
        **depo,
        'platform': sys.platform,
        'machine': platform.machine(),
        'platform_tam': platform.platform(),
        'python': platform.python_version(),
        'numpy': np.__version__,
        'numba': _numba_surumu(),
        'kernel_backend': 'numba' if kernels.NUMBA_AVAILABLE else 'numpy',
        'uretici': 'tools/cfd_referans_dondur.py --pb-none',
    }

    REFERANS_DIZINI.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(yol, meta_json=json.dumps(meta, ensure_ascii=False),
                        **{f'dudt_{k}': v for k, v in diziler.items()})
    boyut = yol.stat().st_size
    print(f'  pb_none: {len(diziler)} vaka, {sure * 1000:.0f} ms → '
          f'{yol.name} ({boyut / 1024:.1f} KiB)')
    return yol, meta


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--vaka', choices=sorted(EULER_REFERANS_VAKALARI),
                    action='append',
                    help='yalnız bu vaka(lar) (varsayılan: hepsi)')
    ap.add_argument('--zorla', action='store_true',
                    help='mevcut referansı YENİLE (Euler yolu bilerek '
                         'değiştiyse; gerekçe parti kaydına yazılır)')
    ap.add_argument('--pb-none', action='store_true',
                    help='YALNIZ Pb=None kalıntı referansını üret '
                         '(donmuş durumlardan türetilir, yeni çözüm '
                         'koşulmaz — ÖH D18 / P6B1-02)')
    ap.add_argument('--kirli-agaca-izin-ver', action='store_true',
                    dest='kirli_izin',
                    help='KİRLİ çalışma ağacından dondurmaya AÇIK izin '
                         '(--gerekce zorunlu; gerekçe künyeye yazılır) — '
                         'ÖH D19 / P10B4-14')
    ap.add_argument('--gerekce', default='',
                    help='--kirli-agaca-izin-ver ile birlikte ZORUNLU: kirli '
                         'ağaç istisnasının gerekçesi')
    args = ap.parse_args(argv)

    # FAIL-CLOSED KAPI — dondurmadan ÖNCE bir kez çalışır ve künyeyi üretir.
    # Kirli/ölçülemeyen ağaçta SystemExit ile durur (P10B4-14): "kirliliği
    # künyeye yazmak" bir çözüm değildir, kapı budur.
    depo = kirlilik_kapisi(izin=args.kirli_izin, gerekce=args.gerekce)
    if depo.get('git_kirli_izin_gerekcesi'):
        print(f'  UYARI: kirli ağaç istisnası kullanıldı — gerekçe künyeye '
              f'yazılıyor: {depo["git_kirli_izin_gerekcesi"]}')

    if args.pb_none:
        yol, _ = dondur_pb_none(zorla=args.zorla, depo_kunyesi=depo)
        print(f'Pb=None kalıntı referansı: {yol}')
        return 0

    kunyeler = args.vaka or list(EULER_REFERANS_VAKALARI)
    print(f'Euler bit-özdeşlik referansları — {len(kunyeler)} vaka, arka uç '
          f'{"numba" if kernels.NUMBA_AVAILABLE else "numpy"}')
    toplam = 0
    for kunye in kunyeler:
        yol, _ = dondur(kunye, zorla=args.zorla, depo_kunyesi=depo)
        toplam += yol.stat().st_size if yol.exists() else 0
    # Pb=None kalıntısı dört referansın TÜREVİDİR: aynı koşuda tazelenir.
    yol, _ = dondur_pb_none(zorla=args.zorla, depo_kunyesi=depo)
    toplam += yol.stat().st_size if yol.exists() else 0
    print(f'Toplam referans boyutu: {toplam / 1024:.1f} KiB '
          f'({toplam / 1024 / 1024:.2f} MB)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
