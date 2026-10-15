"""V3 cfd-sure bekçileri — CFD süre beyanı dürüstlüğü (karar §28-21 CFDS, defter D-8).

KAPATILAN KUSURLAR (main 3edc78b9'de ölçüldü)
---------------------------------------------
1. ``POST /api/cfd/nozzle`` yanıtındaki ``runtime_basis`` cümlesi HER koşuda
   Euler tablosunu (``CFD_RESOLUTION_WORST_CASE_S``) okuyordu. Viskoz koşu
   yüzlerce saniye sürerken "Measured worst case for this level and backend:
   19.9 s" basıyordu (C1 yeniden denetim-7: main 312,4 s, yazıcı kayıtları
   449-651 s; viskoz beyan 286,9 s da aşılıyordu).
2. İki tablonun sayıları şoklu Pb vakasını KAPSAMIYORDU: coarse şoklu Euler
   koşusu kendi beyanını 1,08-1,18× aşıyordu (beyan 10,2 s, ölçülen
   11,0-12,0 s).

SÖZLEŞMELER
-----------
A. Beyan koşunun KİPİNE göre TEK işlevden seçilir
   (``hrma.app._cfd_worst_case_declaration``): viskoz koşu viskoz tablodan
   (seviye × türbülans × arka uç), Euler koşusu Euler tablosundan. İki dal da
   gerçek uçtan sınanır. Ölçülmemiş hücre "NOT MEASURED" diye adlandırılır;
   "None s" basılmaz, tahmin yazılmaz.
B. Tablo değerleri ÖLÇÜM KAYDINA bağlıdır (kanıt kapılı): her yayımlanan
   hücre = o hücrenin ham kayıtlarındaki en büyük ``runtime_s``, 0,1 s'ye
   yukarı yuvarlanmış; her hücrede Pb'siz taban + şoklu Pb vakaları, en az iki
   tekrar, tavana (``DEFAULT_MAX_ITERS``) giden koşu. Beklenen değer burada HAM
   kayıtlardan bağımsız olarak yeniden hesaplanır (üretici betik
   ``beyan_uret.py`` kullanılmaz).
C. Beyan metni ölçüm koşulunu (makine, çekirdek, iş parçacığı, yük) adlandırır
   ve bu metin de kayıttan üretilen metinle aynıdır.
"""

import ast
import glob
import json
import math
import os
import pathlib
import types

import pytest

from tests.support.kanit import kanit_gerekli
from tests.test_cfd_endpoint import _sessiz, govde, viskoz_blok

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
UC = '/api/cfd/nozzle'

#: Kanıt yolları (okuma yalnız ``kanit_gerekli`` kapısından; yayın dalında
#: docs'suz ağaçta B/C bölümü gerekçeyle atlanır).
_KANIT = REPO_ROOT / 'docs' / 'scofield' / 'raw' / 'OH' / 'V3' / 'cfd-sure'
BEYAN_KANITI = _KANIT / 'beyan_kaniti.json'
#: 15 Eki (ana model): Euler hücreleri sakin ölçümden (olcum/kayit_sakin_15eki,
#: main 47466832), viskoz hücreler 14 Eki yüklü ölçümünden (olcum/kayit) — birleşik kopya.
KAYIT_DIZINI = _KANIT / 'olcum' / 'kayit_birlesik'
PLAN = _KANIT / 'olcum' / 'plan.py'

#: Beyan cümlesinin değişmeyen başı (panel ve denetim araçları bu ifadeyi
#: arıyor; kip/tablo adı cümlenin DEVAMINDA).
CUMLE_BASI = 'Measured worst case for this level and backend: '


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _beyan_parcasi(metin):
    """runtime_basis içindeki beyan parçası ('<sayı> s' ya da NOT MEASURED…)."""
    assert CUMLE_BASI in metin, metin
    return metin.split(CUMLE_BASI, 1)[1].split(' - ', 1)[0]


# ---------------------------------------------------------------------------
# A. Seçim tek işlevden; iki dal gerçek uçtan sınanır
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def yanit_euler(client):
    """Pb'siz coarse Euler koşusu (yakınsar, ~2 s)."""
    r = _sessiz(client.post, UC, json=govde())
    assert r.status_code == 200, r.get_data(as_text=True)[:600]
    return r.get_json()['cfd']


@pytest.fixture(scope='module')
def yanit_viskoz(client):
    """Laminer coarse viskoz koşu, iterasyon bütçesi bandın ALT ucu (ucuz)."""
    from hrma.app import CFD_MAX_ITERS_MIN
    r = _sessiz(client.post, UC, json=govde(
        viscous=viskoz_blok(), max_iterations=CFD_MAX_ITERS_MIN))
    assert r.status_code == 200, r.get_data(as_text=True)[:600]
    return r.get_json()['cfd']


def test_euler_yaniti_euler_tablosundan(yanit_euler):
    from hrma.app import CFD_RESOLUTION_WORST_CASE_S
    seviye = yanit_euler['grid']['resolution']
    arka = yanit_euler['kernel_backend']
    assert yanit_euler['viscous']['enabled'] is False
    beklenen = CFD_RESOLUTION_WORST_CASE_S[seviye][arka]
    metin = yanit_euler['runtime_basis']
    assert _beyan_parcasi(metin) == f'{beklenen} s', metin
    assert 'from CFD_RESOLUTION_WORST_CASE_S' in metin
    assert 'CFD_VISCOUS_WORST_CASE_S' not in metin


def test_viskoz_yaniti_viskoz_tablodan(yanit_viskoz):
    """Eski kusur: viskoz yanıt Euler beyanını basıyordu (19.9 s)."""
    from hrma.app import CFD_RESOLUTION_WORST_CASE_S, CFD_VISCOUS_WORST_CASE_S
    v = yanit_viskoz
    assert v['viscous']['enabled'] is True
    seviye = v['grid']['resolution']
    arka = v['kernel_backend']
    kip = v['viscous']['turbulence']
    beklenen = CFD_VISCOUS_WORST_CASE_S[seviye][kip][arka]
    euler = CFD_RESOLUTION_WORST_CASE_S[seviye][arka]
    # Ön koşul: iki tablo bu hücrede ayırt edilebilir (yoksa bekçi kör olur).
    assert beklenen != euler, (beklenen, euler)
    metin = v['runtime_basis']
    assert _beyan_parcasi(metin) == f'{beklenen} s', metin
    assert 'from CFD_VISCOUS_WORST_CASE_S' in metin
    assert f"turbulence '{kip}'" in metin
    assert 'from CFD_RESOLUTION_WORST_CASE_S' not in metin
    # Aynı yanıttaki viskoz blok da AYNI tabloyu taşır (tek kaynak).
    assert v['viscous']['measured_worst_case_s'] == CFD_VISCOUS_WORST_CASE_S[seviye]


def test_secim_islevi_her_hucrede_dogru_tablo():
    from hrma.app import (CFD_RESOLUTION_LEVELS, CFD_RESOLUTION_WORST_CASE_S,
                          CFD_VISCOUS_WORST_CASE_S,
                          _cfd_worst_case_declaration)
    for seviye in CFD_RESOLUTION_LEVELS:
        for arka in ('numba', 'numpy'):
            tablo, _kip, sn = _cfd_worst_case_declaration(seviye, arka, None)
            assert tablo == 'CFD_RESOLUTION_WORST_CASE_S'
            assert sn == CFD_RESOLUTION_WORST_CASE_S[seviye].get(arka)
            for turb in ('none', 'sa_neg'):
                tablo, _kip, sn = _cfd_worst_case_declaration(
                    seviye, arka, types.SimpleNamespace(turbulence=turb))
                assert tablo == 'CFD_VISCOUS_WORST_CASE_S'
                assert sn == ((CFD_VISCOUS_WORST_CASE_S.get(seviye) or {})
                              .get(turb) or {}).get(arka), (seviye, turb, arka)


def test_olculmeyen_hucre_adiyla_tahminsiz():
    """Tabloda olmayan hücre 'None s' ya da başka tablonun sayısını basmaz."""
    from hrma.app import _cfd_runtime_basis
    metin = _cfd_runtime_basis('coarse', 'olculmemis_arka_uc',
                               types.SimpleNamespace(turbulence='none'))
    assert _beyan_parcasi(metin).startswith('NOT MEASURED'), metin
    assert 'None' not in metin
    metin_e = _cfd_runtime_basis('coarse', 'olculmemis_arka_uc', None)
    assert _beyan_parcasi(metin_e).startswith('NOT MEASURED'), metin_e


def test_runtime_basis_tek_islevden_uretiliyor():
    """Uçta ikinci bir seçim yazılmaz: 'runtime_basis' anahtarının değeri
    ``_cfd_runtime_basis`` çağrısıdır ve tablolara o işlev dışında runtime_basis
    için dokunulmaz (kaynak DOSYADAN AST ile okunur)."""
    agac = ast.parse((REPO_ROOT / 'hrma' / 'app.py').read_text(encoding='utf-8'))
    degerler = [d.values[i] for d in ast.walk(agac) if isinstance(d, ast.Dict)
                for i, k in enumerate(d.keys)
                if isinstance(k, ast.Constant) and k.value == 'runtime_basis']
    assert len(degerler) == 1, len(degerler)
    cagri = degerler[0]
    assert (isinstance(cagri, ast.Call) and isinstance(cagri.func, ast.Name)
            and cagri.func.id == '_cfd_runtime_basis'), ast.dump(cagri)[:200]
    islevler = {n.name: n for n in agac.body if isinstance(n, ast.FunctionDef)}
    govde_adlari = {n.id for n in ast.walk(islevler['_cfd_runtime_basis'])
                    if isinstance(n, ast.Name)}
    assert '_cfd_worst_case_declaration' in govde_adlari
    assert not govde_adlari & {'CFD_RESOLUTION_WORST_CASE_S',
                               'CFD_VISCOUS_WORST_CASE_S'}, govde_adlari


def test_beyan_olcum_kosulunu_adlandiriyor(yanit_euler, yanit_viskoz):
    from hrma.app import CFD_WORST_CASE_MEASURED_ON
    assert '@@' not in CFD_WORST_CASE_MEASURED_ON
    for parca in ('cores', 'NUMBA_NUM_THREADS=', 'load average',
                  'shocked back-pressure', 'iteration ceiling'):
        assert parca in CFD_WORST_CASE_MEASURED_ON, parca
    for v in (yanit_euler, yanit_viskoz):
        assert v['runtime_basis'].endswith(CFD_WORST_CASE_MEASURED_ON)


# ---------------------------------------------------------------------------
# B/C. Tablo değerleri ölçüm kaydına bağlı (kanıt kapılı)
# ---------------------------------------------------------------------------

def _yukari_01(x):
    return math.ceil(round(x * 10.0, 6)) / 10.0


def _plan():
    ns = {}
    yol = kanit_gerekli(PLAN)
    exec(compile(pathlib.Path(yol).read_text(encoding='utf-8'), str(yol),
                 'exec'), ns)
    return ns


def _ham_kayitlar():
    dizin = kanit_gerekli(KAYIT_DIZINI)
    yollar = sorted(glob.glob(os.path.join(str(dizin), '*.json')))
    assert yollar, f'ölçüm kaydı yok: {dizin}'
    return [(os.path.basename(y), json.loads(pathlib.Path(y).read_text(
        encoding='utf-8'))) for y in yollar]


def _bagimsiz_tablolar():
    """Ham kayıtlardan iki tabloyu ve hücre başına koşu listesini kurar."""
    from hrma.cfd.steady import DEFAULT_MAX_ITERS
    plan = _plan()
    hucre = {}
    for ad, k in _ham_kayitlar():
        if k['http'] != 200:
            continue
        o, h = k['olcum'], k['hucre']
        if o['iterasyon'] != DEFAULT_MAX_ITERS:
            continue
        arka = o['kernel_backend']
        anahtar = ((h['seviye'], arka) if h['viskoz'] == 'kapali'
                   else (h['seviye'], h['viskoz'], arka))
        vaka = 'taban' if h['vaka'] == 'taban' else f"sok_{int(h['Pb_Pa'])}"
        hucre.setdefault(anahtar, {}).setdefault(vaka, []).append(
            (ad, o['runtime_s'], bool(o['viscous_enabled'])))
    euler, viskoz = {}, {}
    for anahtar, vakalar in hucre.items():
        pbler = (plan['EULER_SOK_PB_PA'][anahtar[0]] if len(anahtar) == 2
                 else plan['VISKOZ_SOK_PB_PA'])
        beklenen = ['taban'] + [f'sok_{int(p)}' for p in pbler]
        if any(len(vakalar.get(v, [])) < plan['EN_AZ_TEKRAR'] for v in beklenen):
            continue                                  # ölçülmedi
        hepsi = [x for v in beklenen for x in vakalar[v]]
        assert all(x[2] == (len(anahtar) == 3) for x in hepsi), anahtar
        deger = _yukari_01(max(x[1] for x in hepsi))
        if len(anahtar) == 2:
            euler.setdefault(anahtar[0], {})[anahtar[1]] = deger
        else:
            viskoz.setdefault(anahtar[0], {}).setdefault(anahtar[1], {})[
                anahtar[2]] = deger
    return euler, viskoz, hucre


def test_tablolar_ham_olcum_kaydindan_bagimsiz_hesapla_ayni():
    from hrma.app import CFD_RESOLUTION_WORST_CASE_S, CFD_VISCOUS_WORST_CASE_S
    euler, viskoz, _ = _bagimsiz_tablolar()
    assert CFD_RESOLUTION_WORST_CASE_S == euler
    assert CFD_VISCOUS_WORST_CASE_S == viskoz


def test_tablolar_ve_kosul_metni_kanit_jsonuyla_ayni():
    from hrma.app import (CFD_RESOLUTION_WORST_CASE_S, CFD_VISCOUS_WORST_CASE_S,
                          CFD_WORST_CASE_MEASURED_ON)
    k = json.loads(pathlib.Path(kanit_gerekli(BEYAN_KANITI)).read_text(
        encoding='utf-8'))
    assert CFD_RESOLUTION_WORST_CASE_S == k['CFD_RESOLUTION_WORST_CASE_S']
    assert CFD_VISCOUS_WORST_CASE_S == k['CFD_VISCOUS_WORST_CASE_S']
    assert CFD_WORST_CASE_MEASURED_ON == k['CFD_WORST_CASE_MEASURED_ON']


def test_olculen_hicbir_kosu_beyani_asmiyor_ve_soklu_vaka_kapsamda():
    """Kabul (C1 yeniden denetim-8 Ş2 (c)): yanıt kendi içinde çelişmez —
    tablodaki her hücrenin her ölçülen koşusu ``runtime_s ≤ beyan``; hücrelerin
    hepsinde şoklu Pb vakası ölçülmüş."""
    from hrma.app import CFD_RESOLUTION_WORST_CASE_S, CFD_VISCOUS_WORST_CASE_S
    _e, _v, hucre = _bagimsiz_tablolar()
    yayimlanan = 0
    for anahtar, vakalar in hucre.items():
        if len(anahtar) == 2:
            beyan = CFD_RESOLUTION_WORST_CASE_S.get(anahtar[0], {}).get(anahtar[1])
        else:
            beyan = ((CFD_VISCOUS_WORST_CASE_S.get(anahtar[0]) or {})
                     .get(anahtar[1]) or {}).get(anahtar[2])
        if beyan is None:
            continue
        yayimlanan += 1
        assert any(v.startswith('sok_') for v in vakalar), anahtar
        for v, kosular in vakalar.items():
            for ad, sn, _visk in kosular:
                assert sn <= beyan, (ad, sn, beyan)
    assert yayimlanan >= 4, yayimlanan


# ---------------------------------------------------------------------------
# 15 Eki (ana model, 4. tur): koşul metni iki kipi AYRI söyler (Euler sakin,
# viskoz yüklü ölçüm). TR kipte runtime_basis cümlesinin TAMAMI çevrilmeli —
# kuyruk deseni i18n_charts.js MSG_PATTERNS'ta; çevrilemezse üst desen cümleyi
# İngilizce bırakır (fail-closed), bu bekçi o hâli yakalar.
# Kâhin: ürünün kendi cümle kurucusu (_cfd_runtime_basis) + sabit; tarihler ve
# yük aralıkları çeviriye aynen taşınır.
# ---------------------------------------------------------------------------
@pytest.mark.skipif(__import__('shutil').which('node') is None,
                    reason='node yok (TR çeviri düzeneği node vm ile koşar)')
def test_kosul_kuyrugu_tr_kipte_cevrilir():
    import re
    from hrma.app import CFD_WORST_CASE_MEASURED_ON, _cfd_runtime_basis
    from tests.test_v3_kucuk import _CEVIRI_KOSUCU, _node_json
    en_euler = _cfd_runtime_basis('coarse', 'numpy', None)
    en_viskoz = _cfd_runtime_basis('standard', 'numba',
                                   types.SimpleNamespace(turbulence='sa_neg'))
    tr = _node_json(_CEVIRI_KOSUCU, {'metinler': [en_euler, en_viskoz]})['tr']
    for en, t in zip((en_euler, en_viskoz), tr):
        assert t != en, 'cümle TR kipte çevrilmedi (kuyruk deseni tutmuyor)'
        for ing in ('Measured on', 'loaded machine', 'Method:', 'cells:'):
            assert ing not in t, (ing, t)
        assert 'Viskozsuz (Euler) hücreler' in t and 'Viskoz hücreler' in t, t
        for parca in re.findall(r'\d{4}-\d{2}-\d{2}|\d+-\d+\)', CFD_WORST_CASE_MEASURED_ON):
            assert parca in t, (parca, t)
