"""ÖH D37 fea-hiz — OpenBLAS iş parçacığı varsayılanı bekçisi.

Bulgu (doğrulama yapısal B6): ``hrma/fea/structural_axisym.py`` ``spsolve``
8.450 serbestlikte yüklü makinede 44,8 s ⟷ ``OPENBLAS_NUM_THREADS=1`` ile
0,16 s. Kontrollü ölçüm (``docs/scofield/raw/OH/D37/fea-hiz/a1/``, 5 tur,
yük ~35-40): yapısal ``spsolve`` medyan 1,92 s ⟷ 0,095 s, düzlem 1,32 s ⟷
0,12 s; hafif yükte (~5, ``hafif_yuk.json``) de 0,263 s ⟷ 0,038 s ve
0,297 s ⟷ 0,049 s; süreç içi A/B'de (aynı süreç ve girdi) yavaşlığı scipy'nin
SuperLU'sunun bağlı olduğu OpenBLAS havuzu belirliyor (yalnız o havuz 1 →
hızlı, yalnız numpy'ninki 1 → yavaş). 2/4 iş parçacığı 1'den hızlı değil;
CPU/duvar 1'de ~0,9, 2'de 1,0-3,1, 4'te 1,9-7,1; varsayılanda yüklüde
4,8-10,5, hafif yükte 13,8 (rapor §1.2).

Onarım ``hrma/__init__.py``nin başında, numpy içe aktarılmadan ÖNCE:
kullanıcı OpenBLAS'ın okuduğu değişkenlerden hiçbirini koymadıysa
``OPENBLAS_NUM_THREADS`` = ``hrma.BLAS_DEFAULT_THREADS``.

Bekçiler (hepsi AYRI SÜREÇTE: OpenBLAS iş parçacığı sayısını yüklenirken
bir kez okur, bu süreçte numpy zaten yüklü olabilir):
  (a) varsayılan tek yerde, boş ortamda yazılıyor, ``import hrma`` numpy'yi
      yüklemiyor, kullanıcı değeri (OPENBLAS/GOTO/OMP) korunuyor;
  (b) üç çözücü noktası (yapısal spsolve, termal splu, düzlem spsolve)
      iş parçacığı ayarından bağımsız BİT-AYNI;
  (c) ters mutasyon: varsayılan çağrısı kaldırılınca (a)'nın hükmü kırmızı;
      asıl dosyaya dokunulmaz (md5 önce = sonra).

``threadpoolctl`` ürün bağımlılığı DEĞİLDİR; kuruluysa havuzun gerçek iş
parçacığı sayısı da doğrulanır, değilse yalnız ortam sözleşmesi sınanır
(atlama yok).
"""
import ast
import hashlib
import json
import os
import pathlib
import subprocess
import sys

import pytest

from hrma import BLAS_DEFAULT_THREADS, BLAS_THREAD_ENV_VARS

KOK = pathlib.Path(__file__).resolve().parents[1]
INIT = KOK / 'hrma' / '__init__.py'

#: Alt sürecin ortamından temizlenen değişkenler (pytest sürecinin kendi
#: değerleri — ör. bu süreçte ``import hrma`` ile yazılan — sızmasın).
#: Düz metin (ürün demetinden türetilmez — denetçi Ş1: demetten bir ad
#: düşerse temizlik de onu atlardı).
TEMIZLENEN = ('OPENBLAS_NUM_THREADS', 'GOTO_NUM_THREADS', 'OMP_NUM_THREADS',
              'VECLIB_MAXIMUM_THREADS', 'MKL_NUM_THREADS')

#: Mutasyon hedefi: onarımın tek çağrı satırı.
CAGRI_SATIRI = '\n_set_blas_thread_default()\n'

SONDA = r'''
import json, os, sys
import hrma
sonuc = {
    "numpy_hrma_ile_yuklendi": "numpy" in sys.modules,
    "ortam": {ad: os.environ.get(ad) for ad in
              ("OPENBLAS_NUM_THREADS", "GOTO_NUM_THREADS", "OMP_NUM_THREADS")},
    "sabit": getattr(hrma, "BLAS_DEFAULT_THREADS", None),
    "hrma_dosyasi": hrma.__file__,
}
import numpy, scipy.sparse.linalg
try:
    from threadpoolctl import threadpool_info
except ImportError:
    sonuc["havuz"] = None
else:
    sonuc["havuz"] = sorted({p["num_threads"] for p in threadpool_info()
                             if p["internal_api"] == "openblas"})
print(json.dumps(sonuc))
'''


def _ortam(kok, ek=None):
    env = dict(os.environ)
    for ad in TEMIZLENEN:
        env.pop(ad, None)
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['PYTHONPATH'] = str(kok)
    env.update(ek or {})
    return env


def _sonda(kok, ek=None, kod=SONDA, zaman=180):
    r = subprocess.run([sys.executable, '-c', kod], cwd=str(kok),
                       env=_ortam(kok, ek), capture_output=True, text=True,
                       timeout=zaman)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout.strip().splitlines()[-1])


def _varsayilan_ihlalleri(s, beklenen=BLAS_DEFAULT_THREADS):
    """Boş ortamda ``import hrma`` sonrası sözleşme; ihlal listesi döner."""
    ihlal = []
    if s['numpy_hrma_ile_yuklendi']:
        ihlal.append('import hrma numpy yükledi — ayar numpy\'den sonra kalır')
    if s['ortam']['OPENBLAS_NUM_THREADS'] != str(beklenen):
        ihlal.append(f"OPENBLAS_NUM_THREADS={s['ortam']['OPENBLAS_NUM_THREADS']!r}"
                     f", beklenen {beklenen!r}")
    for ad in ('GOTO_NUM_THREADS', 'OMP_NUM_THREADS'):
        if s['ortam'][ad] is not None:
            ihlal.append(f'{ad} yazıldı ({s["ortam"][ad]!r}) — kapsam dışı')
    if s['havuz'] is not None and s['havuz'] != [beklenen]:
        ihlal.append(f"OpenBLAS havuzları {s['havuz']}, beklenen [{beklenen}]")
    return ihlal


def _md5(yol):
    return hashlib.md5(yol.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# (a) Varsayılan: tek yerde, setdefault, kullanıcı değeri korunur
# ---------------------------------------------------------------------------
def test_varsayilan_bos_ortamda_numpyden_once_yazilir():
    s = _sonda(KOK)
    assert pathlib.Path(s['hrma_dosyasi']).resolve() == INIT.resolve()
    assert s['sabit'] == BLAS_DEFAULT_THREADS
    assert _varsayilan_ihlalleri(s) == []


#: Ölçümle SEÇİLEN değer (fea-hiz/a1 rapor.md §1-§2: 1 iş parçacığı üç
#: yük koşulunda da en hızlı ya da en hızlıyla eşit; 2 ve 4 hiçbir çözücüde
#: 1'i geçmiyor). Denetçi şartı Ş2: beklentiler sabitin KENDİSİNDEN
#: okununca 1 → 4/14 kayması yeşil kalıyordu; değer burada düz metinle
#: kilitlenir, değiştirmek yeni ölçüm + bu satırın bilinçli güncellemesidir.
OLCULEN_VARSAYILAN = 1

#: OpenBLAS'ın iş parçacığı sayısını okuduğu değişkenler (OpenBLAS
#: kaynağı; fea-hiz/a1 kütüphane matrisi). Denetçi şartı Ş1: parametre
#: listesi ürünün demetinden türetilince demetten bir ad düşünce o vaka da
#: kayboluyordu (kullanıcının OMP değeri ezilir, bekçi görmezdi).
KULLANICI_DEGISKENLERI = ('OPENBLAS_NUM_THREADS', 'GOTO_NUM_THREADS',
                          'OMP_NUM_THREADS')


def test_secilen_varsayilan_olculen_degerde_kilitli():
    assert BLAS_DEFAULT_THREADS == OLCULEN_VARSAYILAN
    s = _sonda(KOK)
    assert s['ortam']['OPENBLAS_NUM_THREADS'] == str(OLCULEN_VARSAYILAN)
    assert _varsayilan_ihlalleri(s, beklenen=OLCULEN_VARSAYILAN) == []


def test_urun_demeti_kullanici_degiskenlerini_kapsar():
    assert set(BLAS_THREAD_ENV_VARS) >= set(KULLANICI_DEGISKENLERI), (
        BLAS_THREAD_ENV_VARS)


@pytest.mark.parametrize('ad', KULLANICI_DEGISKENLERI)
def test_kullanici_degeri_korunur(ad):
    s = _sonda(KOK, {ad: '3'})
    assert s['ortam'][ad] == '3'
    # Kullanıcı herhangi bir OpenBLAS değişkeni koyduysa ürün HİÇBİR şey
    # yazmaz: OpenBLAS'ta OPENBLAS_NUM_THREADS önceliklidir (fea-hiz/a1
    # kütüphane matrisi: OMP=3 + OPENBLAS=1 iki sırada da 1), yani kullanıcının
    # OMP/GOTO değerinin yanına yazmak o değeri EZERDİ.
    for diger in KULLANICI_DEGISKENLERI:
        if diger != ad:
            assert s['ortam'].get(diger) is None, (diger, s['ortam'])
    if s['havuz'] is not None:
        assert s['havuz'] == [3]


def test_sabit_ve_ortam_yazimi_tek_yerde():
    """``OPENBLAS_NUM_THREADS`` hrma/ ve packaging/ .py kaynaklarında YALNIZ
    hrma/__init__.py'de geçer; ``BLAS_DEFAULT_THREADS`` tek kez atanır."""
    dosyalar = subprocess.run(
        ['git', '-C', str(KOK), 'ls-files', '--', 'hrma/*.py', 'packaging/*.py'],
        capture_output=True, text=True, check=True, timeout=60).stdout.split()
    assert 'hrma/__init__.py' in dosyalar
    gecen, atanan = [], []
    for ad in dosyalar:
        metin = (KOK / ad).read_text(encoding='utf-8', errors='replace')
        if 'OPENBLAS_NUM_THREADS' in metin:
            gecen.append(ad)
        if 'BLAS_DEFAULT_THREADS' in metin:
            for dugum in ast.walk(ast.parse(metin)):
                if isinstance(dugum, (ast.Assign, ast.AnnAssign)):
                    hedefler = (dugum.targets if isinstance(dugum, ast.Assign)
                                else [dugum.target])
                    if any(isinstance(h, ast.Name) and h.id == 'BLAS_DEFAULT_THREADS'
                           for h in hedefler):
                        atanan.append(ad)
    assert gecen == ['hrma/__init__.py']
    assert atanan == ['hrma/__init__.py']


def test_ayar_dosyadaki_ilk_ucuncu_parti_ithaldan_once():
    """Varsayılan çağrısı modül gövdesinde os/sys dışındaki her ithaldan
    ÖNCE durur (ileride üste eklenen bir ``import numpy`` onarımı sessizce
    öldürmesin)."""
    govde = ast.parse(INIT.read_text(encoding='utf-8')).body
    cagri = [i for i, d in enumerate(govde)
             if isinstance(d, ast.Expr) and isinstance(d.value, ast.Call)
             and getattr(d.value.func, 'id', None) == '_set_blas_thread_default']
    assert len(cagri) == 1
    for i, d in enumerate(govde[:cagri[0]]):
        if isinstance(d, ast.Import):
            assert {a.name for a in d.names} <= {'os', 'sys'}, ast.dump(d)
        assert not isinstance(d, ast.ImportFrom), ast.dump(d)


# ---------------------------------------------------------------------------
# (b) Üç çözücü: ayardan bağımsız bit-aynı
# ---------------------------------------------------------------------------
COZUCU_SONDA = r'''
import hashlib, json, sys
import hrma
import numpy as np
from hrma.fea import structural_axisym as SA
from hrma.fea import thermal_axisym as TA
from hrma.fea import planar_grain as PG
from hrma.fea.mesh_axisym import build_wall_mesh
from hrma.fea.mesh_planar import build_grain_section_mesh

def sha(*dd):
    h = hashlib.sha256()
    for a in dd:
        a = np.ascontiguousarray(np.asarray(a, dtype=np.float64))
        h.update(str(a.shape).encode()); h.update(a.tobytes())
    return h.hexdigest()

out = {}
# yapısal: 64x64 Lamé halkası (B6 boyutu, 8.450 serbestlik)
m = build_wall_mesh([(0.0, 0.10), (0.10, 0.10)], 0.10, 64, 64)
r = SA.solve_pressure(m, SA.Material(E=200e9, nu=0.3, yield_strength=250e6,
                                     name="fh"), 10e6, axial_fix="z_min")
out["yapisal_spsolve"] = sha(r.displacement, r.stress_nodal, r.stress_gauss)
# termal: 64x64 cidar, 10 adım (splu + SuperLU.solve)
m = build_wall_mesh([(0.0, 0.05), (0.10, 0.05)], 0.02, n_axial=64, n_radial=64)
r = TA.solve_transient(m, TA.ThermalMaterial(rho=7800.0, cp=500.0, k=15.0,
                                            name="fh"),
                       np.linspace(0.0, 0.4, 11),
                       inner_bc=TA.ConvectionBC(h=2000.0, T_inf=3000.0),
                       outer_bc=TA.AmbientBC(h=15.0, T_ambient=300.0),
                       T_initial=300.0)
out["termal_splu"] = sha(r.T_history)
# düzlem: tam halka 128x32 (8.448 serbestlik)
m = build_grain_section_mesh(0.02, 0.05, n_theta=128, n_radial=32,
                             symmetry_fraction=1)
r = PG.solve_plane_strain_section(m, SA.Material(E=6.0e6, nu=0.49, name="fh"),
                                  5e6, outer_bc="bonded_rigid")
out["duzlem_spsolve"] = sha(r.displacement, r.stress_nodal, r.stress_gauss)
try:
    from threadpoolctl import threadpool_info
    out["_havuz"] = sorted({p["num_threads"] for p in threadpool_info()
                            if p["internal_api"] == "openblas"})
except ImportError:
    out["_havuz"] = None
print(json.dumps(out))
'''


def test_uc_cozucu_is_parcacigi_ayarindan_bagimsiz_bit_ayni():
    """Ürün yolu (boş ortam → varsayılan) ⟷ 2 ⟷ 4 iş parçacığı.

    Varsayılan (14) iş parçacığı burada KOŞULMAZ: yüklü makinede tek çözüm
    saniyelerce sürebiliyor (bulgunun kendisi; ölçümde en kötü 13,0 s). 14
    dahil dört eşiğin bit-aynılığı fea-hiz/a1 ölçümünde aynı boyutta, üç
    koşul × 5 turda kayıtlı (yüklü, nice, hafif yük). Ağ bulgunun kendi
    boyutunda (B6: 8.450 serbestlik); bu boyutta bir sonda üç çözücüyü
    saniyenin altında koşar. 2 ve 4 çok iş parçacıklı yolu gerçekten
    çalıştırır: yapısal/düzlem tam çözümünde CPU/duvar 2'de 2,2-3,1, 4'te
    4,0-7,1 (``olcum.json``, ``hafif_yuk.json``). ``kucuk_ag.json``: 32×32
    ağda da 4 iş parçacığında ``spsolve`` çağrısının CPU/duvarı 6-7 —
    işçiler küçük ağda da uyanır; boyut bulgunun boyutu olduğu için seçildi."""
    urun = _sonda(KOK, kod=COZUCU_SONDA, zaman=300)
    iki = _sonda(KOK, {'OPENBLAS_NUM_THREADS': '2'}, kod=COZUCU_SONDA, zaman=300)
    dort = _sonda(KOK, {'OPENBLAS_NUM_THREADS': '4'}, kod=COZUCU_SONDA,
                  zaman=300)
    for s, beklenen in ((urun, BLAS_DEFAULT_THREADS), (iki, 2), (dort, 4)):
        if s['_havuz'] is not None:
            assert s['_havuz'] == [beklenen], s['_havuz']
    anahtarlar = ('yapisal_spsolve', 'termal_splu', 'duzlem_spsolve')
    for k in anahtarlar:
        assert urun[k] == iki[k] == dort[k], k


# ---------------------------------------------------------------------------
# (c) Ters mutasyon: varsayılan kaldırılınca (a) kırmızı
# ---------------------------------------------------------------------------
def test_ters_mutasyon_varsayilan_kalkinca_kirmizi(tmp_path):
    md5_once = _md5(INIT)
    orj = INIT.read_text(encoding='utf-8')
    assert orj.count(CAGRI_SATIRI) == 1
    mutant = orj.replace(CAGRI_SATIRI, '\n')

    def _paket(ad, kaynak):
        kok = tmp_path / ad
        (kok / 'hrma').mkdir(parents=True)
        (kok / 'hrma' / '__init__.py').write_text(kaynak, encoding='utf-8')
        return kok

    # Aynı düzenekte asıl kaynağın kopyası YEŞİL: kırmızının sebebi düzenek
    # değil mutasyondur.
    s_orj = _sonda(_paket('orj', orj))
    assert _varsayilan_ihlalleri(s_orj) == []

    s_mut = _sonda(_paket('mut', mutant))
    assert pathlib.Path(s_mut['hrma_dosyasi']).parent.parent == tmp_path / 'mut'
    ihlal = _varsayilan_ihlalleri(s_mut)
    assert any('OPENBLAS_NUM_THREADS' in i for i in ihlal), ihlal

    # Asıl dosya hiç değişmedi (geri alma gerekmedi; md5 eşit).
    assert _md5(INIT) == md5_once

