"""ÖH Dalga-32 / fea-cfd aşama-2 bekçisi — OH-D31-15 üç durumlu yakınsama.

KUSUR (ölçüldü: docs/scofield/raw/OH/D32/fea-cfd/a2/once.json). CFD
çözücüsünün öz-tutarlılık kapısı YALNIZ örtük 2. mertebe yolu kapsıyor
(``SELFCONSISTENCY_GATE_SCOPE = 'line_implicit_j+second_order'``). AÇIK
yolda (varsayılan ssp_rk2) plato-dondurma bayat operatörün kalıntısını
yayımlar ve hüküm O sayıdan verilirdi. §11.3'ün dört bit-özdeşlik
referansının ÜÇÜNDE şemanın kendi (canlı minmod) kalıntısı yayımlanandan
kat kat büyükken bayrak ``converged=True`` idi:

    izantropik  60×12 :        1,00×   (operatör CANLI — hüküm hak edilmiş)
    şoklu       60×12 :       44,29×   (tol 2e-6,  şema 8,8308e-05)
    şoklu      120×24 :      398,71×   (tol 2e-6,  şema 5,5102e-04)
    izantropik 120×24 : 2,9030e+07×    (tol 1e-10, şema 2,1183e-04)

Kapsam D31'de ADIYLA yayımlanmıştı (``selfconsistency_gate_scope`` /
``in_gate_scope`` / ``verdict_outside_gate_scope``) ama BEYAN ÇÖZÜM
DEĞİLDİR: tüketiciler bayrağı okuyordu, beyanı değil — panel yeşil
'CONVERGED' rozeti basıyor, ayrılma köprüsü ``judgment_confidence='firm'``
veriyor, uç bayrağı ``bool()`` ile geçiriyordu (ölçüm once.json K3/K4).

ONARIM (Berke kararı 15 Eyl 2026 §3, seçenek A; Astra (c) hükmü —
docs/scofield/raw/OH/D32/oturum-devri/berke_kararlari_2026-09-15.md):
``converged`` ÜÇ DEĞERLİDİR — True (hüküm verildi) / False (ÖLÇÜLMÜŞ engel)
/ None (gerekli değerlendirme YAPILMADI, ``convergence_status=
'not_evaluated'``) — ve üç durum TÜM tüketicilerde birlikte taşınır.
Dört referans künyesi P10B4-14 deseniyle yenilendi: DİZİLER BİT-AYNI,
yalnız hüküm alanları + gerekçe değişti (kanıt: kunye_yenileme.json).
Kök onarım (kapıyı açık yola genişletmek + referansları GERÇEKTEN yeniden
koşmak) 2.7'de kalır.

TASARIM TUZAĞI, ADIYLA: hüküm yokluğu bir DİZGE ile ('NOT_EVALUATED')
taşınamaz — ``bool('NOT_EVALUATED')`` True'dur ve kusur aynen sürerdi
(Astra'nın adlandırdığı tuzak). Bu dosya bunu da ölçer.
"""

import ast
import hashlib
import json
import pathlib
import re
import shutil
import subprocess

import numpy as np
import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
REFERANS_DIZINI = KOK / 'data' / 'cfd_referans'
PANEL_JS = KOK / 'hrma' / 'static' / 'js' / 'panels' / 'cfd_panel.js'
NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node kurulu değil')

# ÖH D37 A3a cfd-kok-a (F-05 + OH-DK-12/13/14; Berke Sunum 3a onayı, 24 Eylül
# 2026): dört referans BİLEREK yeniden koşulup donduruldu. D32'de kapsam
# dışında hüküm verdiği için "yargılanmadı"ya çekilen üç referanstan ikisi
# (sok_60x12, sok_120x24) şoklu akışta dondurma kapandığı için artık CANLI
# operatörle yakınsıyor — hüküm KAZANILMIŞ. izantropik_120x24 hâlâ dondurma
# yolunda biter → 'not_evaluated' kalır.
YARGILANMAYAN = ('izantropik_120x24',)
YARGILANAN = ('izantropik_60x12', 'sok_60x12', 'sok_120x24')

# Dizilerin sha256'sı: yeniden dondurmadan SONRA ölçüldü (ARA KAYIT 7 —
# dizi farkı ARA KAYIT 6 ile 5/5 yok). Çakılıdır: ileride "künyeyi
# güncelledim" diyerek dizi değiştirilemez; gerçek yeniden dondurma
# yenileme gerekçesiyle ve yeni sayılarla yapılır.
DIZI_SHA256 = {
    'izantropik_60x12':
        'bde61e6852dd9b65fd4cdfccd1ee39d90e52f64ac0732e3164e9777678d2fae6',
    'izantropik_120x24':
        '907f83c876bf5c43acb722cc6867163226e96ed4fd26e4c08e2f693950bb1b63',
    'sok_60x12':
        'e0458f1a85c10b5d1c4ecd632435787a51e695597f588f9719bf9d5d7a9fcfca',
    'sok_120x24':
        'abbff57a2fe64d4c6aa56a2ad4f80b6c7c6dc3fd564044fd7dd7425ea94945ae',
}


def _referans(kunye):
    yol = REFERANS_DIZINI / f'euler_{kunye}.npz'
    with np.load(yol, allow_pickle=False) as z:
        U = np.array(z['U'])
        meta = json.loads(str(z['meta_json']))
    return U, meta


# ---------------------------------------------------------------------------
# G1 — dört referansın künyesi: hüküm üç durumlu, diziler çakılı
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('kunye', YARGILANMAYAN)
def test_G1a_kapsam_disi_referans_hukum_YAYIMLAMIYOR(kunye):
    """Dondurma yolunda biten referans 'yargılanmadı' der (OH-D31-15)."""
    _U, meta = _referans(kunye)
    kos = meta['kosum']
    assert kos['converged'] is None, (
        f'{kunye}: künye hâlâ hüküm yayımlıyor (converged='
        f'{kos["converged"]!r}) — kapsam dışında verilmiş hüküm KAZANILMAMIŞ '
        f'hükümdür (OH-D31-15)')
    assert kos['convergence_status'] == 'not_evaluated', (
        f'{kunye}: hükmün cinsi {kos["convergence_status"]!r}; '
        f'"not_evaluated" bekleniyordu')
    assert not isinstance(kos['converged'], str), (
        f'{kunye}: hüküm bir DİZGE ile taşınıyor — bool() onu True yapar '
        f've kusur sürer')
    assert kos.get('verdict_basis', '').strip(), (
        f'{kunye}: hüküm yok ama GEREKÇE de yok — sessiz boşluk')


@pytest.mark.parametrize('kunye', YARGILANAN)
def test_G1b_kapsam_ici_referans_hukmu_KORUNDU(kunye):
    """Operatörü CANLI olan referansın hükmü verilmiş (kazanılmış) hükümdür."""
    _U, meta = _referans(kunye)
    kos = meta['kosum']
    assert kos['converged'] is True, (
        f'{kunye}: hak edilmiş hüküm geri çekilmiş — onarım kapsamı aştı')
    assert kos['convergence_status'] == 'converged'


@pytest.mark.parametrize('kunye', sorted(DIZI_SHA256))
def test_G1c_kunye_yenilemesi_DIZIYE_DOKUNMADI(kunye):
    """Dizi çakılı; yeniden dondurma ADIYLA ve gerekçesiyle beyanlı."""
    U, meta = _referans(kunye)
    sha = hashlib.sha256(np.ascontiguousarray(U).tobytes()).hexdigest()
    assert sha == DIZI_SHA256[kunye], (
        f'{kunye}: dondurulmuş dizi DEĞİŞMİŞ (sha256 {sha}) — referans '
        f'yenilemesi ayrı bir karardır; gerekçesi ve yeni sayılarıyla yapılır')
    gerekce = meta.get('yenileme_gerekcesi', '')
    assert 'cfd-kok-a' in gerekce and 'F-05' in gerekce, (
        f'{kunye}: yeniden dondurmanın gerekçesi künyede yok — hangi kararla '
        f'ne değiştiği dosyanın kendisinden okunamıyor')
    assert meta.get('uretici') == 'tools/cfd_referans_dondur.py'
    assert 'referans_dondur_a3a.py' in meta.get('uretici_betik', '')


# ---------------------------------------------------------------------------
# G2 — ayrılma köprüsü: üç durum, üç etiket
# ---------------------------------------------------------------------------

def _sentetik(converged):
    from tests.cfd.test_ayrilma import ASIRI_PROFIL, _sentetik_sonuc
    res = _sentetik_sonuc(ASIRI_PROFIL)
    res['converged'] = converged
    return res


@pytest.mark.parametrize('hukum,beklenen', [
    (True, 'firm'), (False, 'suspect'), (None, 'not_evaluated')])
def test_G2_ayrilma_guven_etiketi_uc_durumlu(hukum, beklenen):
    from hrma.cfd.separation import assess_separation

    a = assess_separation(_sentetik(hukum), 7.5e5)
    assert a['judgment_confidence'] == beklenen, (
        f'converged={hukum!r} için güven etiketi {a["judgment_confidence"]!r}; '
        f'{beklenen!r} bekleniyordu')
    assert a['converged'] is hukum, (
        'köprü hükmü kendi başına dönüştürmemeli — çözücünün alanı aynen '
        'taşınır')


def test_G2b_yargilanmamis_hukum_SAGLAM_sunulmaz():
    """'not_evaluated' ile 'suspect' aynı cümleyi kurmaz."""
    from hrma.cfd.separation import assess_separation

    yok = assess_separation(_sentetik(None), 7.5e5)
    supheli = assess_separation(_sentetik(False), 7.5e5)
    assert 'YAKINSAMADI' not in yok['judgment_basis'], (
        'hüküm yargılanmadığı hâlde "yakınsamadı" deniyor — bu bir hüküm '
        'uydurmaktır')
    assert 'HÜKÜM VERMEDİ' in yok['judgment_basis']
    assert 'YAKINSAMADI' in supheli['judgment_basis']
    assert yok['judgment_basis'] != supheli['judgment_basis']


# ---------------------------------------------------------------------------
# G3 — koşum künyesi (wall_output): üçüncü durum bool'a ezilmiyor
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('hukum', [True, False, None])
def test_G3_kosum_kunyesi_hukmu_AYNEN_tasir(hukum, monkeypatch):
    from hrma.cfd import wall_output

    monkeypatch.setattr(wall_output, 'viscous_wall_block',
                        lambda result: {'y_plus_loop': {}})
    kunye = wall_output.solution_declaration({
        'converged': hukum,
        'convergence_status': ('not_evaluated' if hukum is None
                               else 'converged' if hukum else 'not_converged'),
        'convergence_basis': 'sentetik',
        'residual_history': np.array([1e-6]),
        'iterations': 10,
    })
    assert kunye['converged'] is hukum, (
        f'künye hükmü {kunye["converged"]!r}; çözücünün {hukum!r} değeri '
        f'AYNEN taşınmalıydı')


def test_G3b_hukum_alani_HIC_yoksa_fail_closed():
    """'hüküm yok' ile 'alan yayımlanmadı' ayrı şeydir; ikincisi False."""
    from hrma.cfd import wall_output

    orj = wall_output.viscous_wall_block
    wall_output.viscous_wall_block = lambda result: {'y_plus_loop': {}}
    try:
        kunye = wall_output.solution_declaration({
            'residual_history': np.array([1e-6]), 'iterations': 3})
    finally:
        wall_output.viscous_wall_block = orj
    assert kunye['converged'] is False, (
        'hüküm alanı hiç yayımlanmamışken künye "hüküm yok" diyemez — '
        'ölçemediğimiz hâl temiz sayılmaz')


# ---------------------------------------------------------------------------
# G4/G5 — kaynak sözleşmesi (AST): bool() üçüncü durumu ezemez
# ---------------------------------------------------------------------------

def _agac(yol):
    return ast.parse(yol.read_text(encoding='utf-8'))


def _bool_cagrisi_mi(dugum, ic_ad):
    """``bool(<ic_ad>['converged'])`` biçiminde bir çağrı mı?"""
    if not (isinstance(dugum, ast.Call) and isinstance(dugum.func, ast.Name)
            and dugum.func.id == 'bool' and len(dugum.args) == 1):
        return False
    arg = dugum.args[0]
    return (isinstance(arg, ast.Subscript)
            and isinstance(arg.value, ast.Name) and arg.value.id == ic_ad
            and isinstance(arg.slice, ast.Constant)
            and arg.slice.value == 'converged')


def _none_korumali_mi(ifexp, ic_ad):
    """``X if <ic_ad>['converged'] is None else bool(...)`` kalıbı mı?

    Üçüncü durumu ayıran ifadenin İÇİNDE bir ``bool()`` bulunması normaldir
    (False/True dalı); yasak olan KORUMASIZ ``bool()``tır. Bekçi bu ikisini
    ayırmak zorunda, yoksa doğru onarımı da kırmızıya düşürür.
    """
    test = ifexp.test
    if not (isinstance(test, ast.Compare) and len(test.ops) == 1
            and isinstance(test.ops[0], ast.Is)
            and isinstance(test.comparators[0], ast.Constant)
            and test.comparators[0].value is None):
        return False
    sol = test.left
    return (isinstance(sol, ast.Subscript)
            and isinstance(sol.value, ast.Name) and sol.value.id == ic_ad
            and isinstance(sol.slice, ast.Constant)
            and sol.slice.value == 'converged')


def _korumasiz_bool_satirlari(agac, ic_ad):
    """Bir ``is None`` koşullusunun KORUMASI ALTINDA olmayan bool() satırları."""
    korumali = set()
    for d in ast.walk(agac):
        if isinstance(d, ast.IfExp) and _none_korumali_mi(d, ic_ad):
            for alt in ast.walk(d):
                if _bool_cagrisi_mi(alt, ic_ad):
                    korumali.add(id(alt))
    return sorted(d.lineno for d in ast.walk(agac)
                  if _bool_cagrisi_mi(d, ic_ad) and id(d) not in korumali)


@pytest.mark.parametrize('goreli,ic_ad', [
    ('hrma/app.py', 'sonuc'),
    ('hrma/cfd/steady.py', 'sonuc'),
    ('hrma/cfd/separation.py', 'result'),
    ('tools/cfd_referans_dondur.py', 'sonuc'),
])
def test_G4_ciplak_bool_donusumu_KALMADI(goreli, ic_ad):
    """``bool(x['converged'])`` üçüncü durumu sessizce 'yakınsamadı' yapar."""
    agac = _agac(KOK / goreli)
    kalanlar = _korumasiz_bool_satirlari(agac, ic_ad)
    assert not kalanlar, (
        f'{goreli}: {ic_ad}[\'converged\'] hâlâ bool() ile geçiriliyor '
        f'(satır {kalanlar}) — None burada False olur ve "değerlendirilmedi" '
        f'"yakınsamadı" diye yayımlanır')


def test_G5_cozucu_hukmu_UC_DEGERLI_atiyor():
    """steady.py'de hüküm bir koşullu ifadedir, bool() değil."""
    agac = _agac(KOK / 'hrma' / 'cfd' / 'steady.py')
    atamalar = [d for d in ast.walk(agac)
                if isinstance(d, ast.Assign) and len(d.targets) == 1
                and isinstance(d.targets[0], ast.Name)
                and d.targets[0].id == 'converged']
    ucdurumlu = [d for d in atamalar if isinstance(d.value, ast.IfExp)]
    assert ucdurumlu, (
        'steady.py hükmü üç durumlu atamıyor: converged, '
        'verdict_outside_gate_scope\'a bağlı bir koşullu ifade olmalı')
    kaynak = (KOK / 'hrma' / 'cfd' / 'steady.py').read_text(encoding='utf-8')
    assert "convergence_status = 'not_evaluated'" in kaynak, (
        'hükümsüzlüğün cinsi ADIYLA yayımlanmıyor')
    assert re.search(r"converged\s*=\s*None if verdict_outside_gate_scope",
                     kaynak), (
        'hüküm yokluğunun ölçütü kapsam alanına bağlı değil')


# ---------------------------------------------------------------------------
# G6 — panel: sahte 'ok' çıkmıyor (badgesHtml node altında GERÇEKTEN koşar)
# ---------------------------------------------------------------------------

HARNESS = r'''
const fs = require('fs');
const vm = JSON.parse(process.argv[3]);
const src = fs.readFileSync(process.argv[2], 'utf8');
const i = src.indexOf('    function badgesHtml(vm) {');
const j = src.indexOf('\n    function ', i + 10);
if (i < 0 || j < 0) { throw new Error('badgesHtml dilimi bulunamadi'); }
const gov = src.slice(i, j);
if (gov.indexOf('return html;') < 0) { throw new Error('dilim eksik'); }
const rozetler = [];
function badge(t, k, ti) { rozetler.push([k, t, String(ti || '')]); return ''; }
function T(k, f) { return f; }
function TF(k, p, f) {
  return String(f).replace(/\{(\w+)\}/g, function (m, a) {
    return String(p[a]); }); }
function SRV(x) { return String(x == null ? '' : x); }
function txt(x) { return String(x == null ? '-' : x); }
function fmt(x, n) { return x == null ? '-' : Number(x).toFixed(n || 0); }
function fmtExp(x, n) {
  return x == null ? '-' : Number(x).toExponential(n || 3); }
function fmtAuto(x) { return x == null ? '-' : String(x); }
function sigFig(x) { return x == null ? '-' : String(x); }
function isNum(x) { return typeof x === 'number' && isFinite(x); }
function viscousBadgesHtml() { return ''; }
const carpetFallback = false;
eval(gov);
badgesHtml(vm);
console.log(JSON.stringify(rozetler));
'''

VM_TABAN = {
    'iterations': 26896,
    'residual': {'last': 1.99e-06},
    'plateau': None,
    'inlet': {},
    'budget': {'mass_balance_rel': 1e-09, 'energy_balance_rel': 1e-09,
               'viscous_energy_balance_rel': None},
    'kernel': None, 'kernelBasis': '', 'shockColumns': 0,
    'limiterIter': None, 'limiterCount': 0, 'runtime': None,
    'solverRuntime': None, 'runtimeBasis': '', 'shockBasis': '',
}


def _rozetler(tmp_path, vm):
    betik = tmp_path / 'rozet_kos.js'
    betik.write_text(HARNESS, encoding='utf-8')
    proc = subprocess.run(
        [NODE, str(betik), str(PANEL_JS), json.dumps(vm)],
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-2000:]
    return [tuple(r) for r in json.loads(proc.stdout)]


def _vm(converged, durum, guven):
    vm = dict(VM_TABAN)
    vm.update({
        'converged': converged,
        'convergenceStatus': durum,
        'convergenceBasis': 'çözücünün kendi cümlesi',
        'separation': {'judgment_confidence': guven, 'separated': False,
                       'wall_pressure_margin_min': 3.2,
                       'judgment_basis': 'köprünün kendi cümlesi'},
    })
    return vm


@needs_node
def test_G6a_yargilanmamis_hukum_YESIL_BASILMAZ(tmp_path):
    rozet = _rozetler(tmp_path,
                      _vm(None, 'not_evaluated', 'not_evaluated'))
    metinler = [m for _s, m, _t in rozet]
    assert not any('CONVERGED' in m.upper() and 'NOT' not in m.upper()
                   for m in metinler), (
        f'hüküm yargılanmadığı hâlde "CONVERGED" rozeti basıldı: {metinler}')
    assert not any(s == 'ok' for s, _m, _t in rozet), (
        f'hüküm yokken KABUL rengi basıldı: {rozet}')
    assert any(s == 'warn' and 'no verdict' in m.lower() for s, m, _t in rozet), (
        f'hüküm yokluğu ADIYLA basılmıyor: {rozet}')


@needs_node
def test_G6b_yargilanmamis_hukumde_AYRILMA_rozeti_yesil_degil(tmp_path):
    rozet = _rozetler(tmp_path,
                      _vm(None, 'not_evaluated', 'not_evaluated'))
    for sinif, metin, _t in rozet:
        if 'SEPARATION' in metin.upper() or 'NO SEPARATION' in metin.upper():
            assert sinif != 'ok', (
                f'yargılanmamış alana uygulanmış ayrılma hükmü yeşil: '
                f'{metin!r}')


@needs_node
def test_G6c_hak_edilmis_hukum_YESIL_KALIR(tmp_path):
    """Onarım kapsamı aşmadı: gerçekten yakınsamış koşu hâlâ 'ok'."""
    rozet = _rozetler(tmp_path, _vm(True, 'converged', 'firm'))
    assert any(s == 'ok' and 'CONVERGED' in m.upper()
               for s, m, _t in rozet), rozet


@needs_node
def test_G6d_olculmus_yakinsamama_hala_NOT_CONVERGED(tmp_path):
    rozet = _rozetler(tmp_path, _vm(False, 'not_converged', 'suspect'))
    assert any(s == 'warn' and 'NOT CONVERGED' in m.upper()
               for s, m, _t in rozet), rozet


def test_G6e_panel_dizge_hukmu_KABUL_ETMEZ():
    """Panel dalları ===/kesin eşitlikle yazılmış: dizge yeşil basamaz."""
    kaynak = PANEL_JS.read_text(encoding='utf-8')
    i = kaynak.index('    function badgesHtml(vm) {')
    j = kaynak.index('\n    function ', i + 10)
    gov = kaynak[i:j]
    assert 'vm.converged === true' in gov and 'vm.converged === false' in gov
    assert 'vm.converged === null' in gov, (
        'üçüncü durumun dalı yok — panel hüküm yokluğunu sessizce yutar')
    assert "sep.judgment_confidence === 'firm'" in gov, (
        'kabul rengi hâlâ "suspect DEĞİLSE yeşil" kuralıyla veriliyor; '
        'üçüncü etiket o kuralda yeşil basar')
