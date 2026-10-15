# -*- coding: utf-8 -*-
"""V3 kararlılık bekçisi — SO-0 (karar §28-33: kararlılık temel ilke).

Bulgu (12 Eki tam süit, dilim 2; rapor docs/scofield/raw/OH/V3/kararlilik/
rapor.md): 18 düğüm paralel dilimde KIRMIZI, seri koşuda YEŞİL idi
(``KeyError: 'LOX / RP1'`` / ``'LOX / CH4'``; çevrim 'not_modelled').

Kök neden iki parçalıdır:

* Tetik (test): ``tests/test_combustion_cea_validation.py::_cea_oksitleyici``
  her çağrıda ``add_new_oxidizer`` ile AYNI adlı kartı yeniden tanımlar;
  RocketCEA bu durumda süreç-global sonuç önbelleğini (``_CacheObjDict``)
  bütünüyle boşaltır (rocketcea/cea_obj.py:144-146).
* Kırılganlık (ürün): ``hrma.engines.cycle_power_balance._get_cea`` kurduğu
  ``CEA_Obj``'yi süreç boyunca önbellekler; kütüphane kaydı (``desc``)
  silinince bu nesnenin her yeni noktası ``setTcK`` satırında KeyError verir
  (cea_obj.py:957) ve çevrim süreç ölene dek 'not_modelled' kalır.

Düzeltme ürün tarafındadır: önbellek isabetinde kütüphane kaydı doğrulanır,
kayıt yoksa nesne yeniden kurulur. Bu dosyadaki bekçiler kütüphane
önbelleğini YALNIZ teste özel bir kopyada boşaltır (``monkeypatch``); test
bitince asıl sözlük geri gelir — bekçinin kendisi yeni bir kirletici olmaz.

Ters mutasyon (``_get_cea`` önbellek isabetinde doğrulamasız döner) bu
dosyanın üç bekçisini de KIRMIZIYA çevirir (rapor.md, 'Mutasyon').
"""
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from tests.bagimlilik_kapisi import kapi
from tests.test_d16_hibrit_a2 import _coz

try:
    import rocketcea.cea_obj as _cea_module
    ROCKETCEA_YOLU_ACIK = True
    ROCKETCEA_ITHAL_HATASI = ''
except Exception as _rc_exc:        # pragma: no cover - ortama bağlı
    _cea_module = None
    ROCKETCEA_YOLU_ACIK = False
    ROCKETCEA_ITHAL_HATASI = f'{type(_rc_exc).__name__}: {_rc_exc}'

from hrma.engines import cycle_power_balance as cpb

KOK = Path(__file__).resolve().parents[1]

#: Teste özel oksitleyici kartının adı (yalnız yamalı kart sözlüğüne yazılır).
_SINAMA_KARTI = 'LOX_V3_KARARLILIK'

#: 12 Eki dilim 2'deki gerçek sıra, en kısa hâliyle: önce çevrim önbelleğini
#: dolduran bir düğüm, sonra kirletici dosya, sonra kurban sınıfı.
_DOLDURAN = ('tests/test_d16_hibrit_a2.py::TestB408TurbomakineVerimKapisi'
             '::test_varsayilan_secim_bozulmadi')
_KIRLETICI = 'tests/test_combustion_cea_validation.py'
_KURBAN = 'tests/test_d16_hibrit_a2.py::TestB409NegatifPompaDeltaP'

#: Alt süreç koşusunun süre tavanı [s] (ölçülen ~2-10 s; yük payı dahil).
_ALT_SUREC_TAVANI_S = 200


@pytest.fixture
def cea_kapisi():
    kapi('rocketcea', ROCKETCEA_YOLU_ACIK,
         'rocketcea KURULU ama `import rocketcea.cea_obj` yüklenemedi: '
         f'{ROCKETCEA_ITHAL_HATASI}')


@pytest.fixture
def yalitilmis_kutuphane(cea_kapisi, monkeypatch):
    """RocketCEA'nın süreç-global önbelleğini, kart sözlüğünü ve çevrim
    önbelleğini teste özel KOPYALARLA değiştirir; test bitince asılları
    geri gelir."""
    monkeypatch.setattr(_cea_module, '_CacheObjDict',
                        dict(_cea_module._CacheObjDict))
    monkeypatch.setattr(_cea_module, 'oxCards', dict(_cea_module.oxCards))
    monkeypatch.setattr(cpb, '_CEA_CACHE', {})
    return _cea_module


def _kutuphane_onbellegini_bosalt(co, yol):
    """RocketCEA'nın kendi iki boşaltma yolu (cea_obj.py:119-125, 144-146)."""
    if yol == 'clearCache':
        co.clearCache(show_size=False)
        return
    # add_new_card: ad kart sözlüğünde VARSA önbellek bütünüyle silinir —
    # kirletici testin yaptığı tam olarak budur (aynı adla ikinci tanım).
    kart = '\n'.join(co.oxCards['LOX'])
    co.add_new_oxidizer(_SINAMA_KARTI, kart)
    co.add_new_oxidizer(_SINAMA_KARTI, kart)


@pytest.mark.parametrize('yakit', ['rp1', 'methane'])
@pytest.mark.parametrize('yol', ['clearCache', 'add_new_card'])
def test_library_cache_clear_keeps_cycle_solution_bit_identical(
        yalitilmis_kutuphane, yol, yakit):
    """Kütüphane önbelleği boşaldıktan sonra çevrim YİNE yakınsar ve
    çözüm boşaltmadan önceki çözümle BİT-AYNIDIR."""
    co = yalitilmis_kutuphane
    once = _coz(fuel=yakit)
    nesne = cpb._get_cea(yakit, 'lox')
    assert nesne is not None and nesne.desc in co.getCacheDict()

    _kutuphane_onbellegini_bosalt(co, yol)
    # Ön koşul: boşaltma GERÇEKTEN oldu; olmadıysa bekçi boşa döner.
    assert nesne.desc not in co.getCacheDict(), (
        f'{yol} kütüphane kaydını silmedi — bekçi ölçmüyor')

    sonra = _coz(fuel=yakit)
    assert once.converged and sonra.converged, (once.warnings,
                                                sonra.warnings)
    assert sonra.to_dict() == once.to_dict()


def test_stale_cached_object_is_rebuilt_not_reused(yalitilmis_kutuphane):
    """Kayıt silinince önbellekteki nesne YENİDEN KURULUR ve kurucu kaydı
    yeniden açar; kayıt yerindeyken aynı nesne döner (sıcak yol değişmez)."""
    co = yalitilmis_kutuphane
    ilk = cpb._get_cea('rp1', 'lox')
    assert cpb._get_cea('rp1', 'lox') is ilk
    co.clearCache(show_size=False)
    ikinci = cpb._get_cea('rp1', 'lox')
    assert ikinci is not ilk
    assert ikinci.desc == ilk.desc and ikinci.desc in co.getCacheDict()
    assert cpb._get_cea('rp1', 'lox') is ikinci


# K-2 (2. tur) notu: tests/test_combustion_cea_validation.py kartı artık
# yalnız YOKSA tanıtıyor; bu sıra o dosyayla TETİKSİZ kalır (yeşilliği
# artık bir şey kanıtlamaz). Tetik aşağıda bekçinin KENDİ içinde üretilir:
# test_self_made_trigger_then_victim_same_process_green.
def test_polluter_then_victim_same_process_green(cea_kapisi, tmp_path):
    """12 Eki dilim 2 sırası (doldurucu -> kirletici -> kurban) TEK süreçte
    yeşil. Toplanan düğüm sayısı denetlenir ('no tests ran' sahte temiz
    sayılmaz)."""
    junit = tmp_path / 'sira.xml'
    ortam = dict(os.environ)
    ortam.update(HRMA_PROJECTS_DIR=str(tmp_path / 'projeler'), BROWSER='echo',
                 OMP_NUM_THREADS='2', VECLIB_MAXIMUM_THREADS='2',
                 MKL_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2')
    (tmp_path / 'projeler').mkdir()
    sonuc = subprocess.run(
        [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
         f'--junitxml={junit}', _DOLDURAN, _KIRLETICI, _KURBAN],
        cwd=KOK, env=ortam, capture_output=True, text=True,
        timeout=_ALT_SUREC_TAVANI_S)
    vakalar = list(ET.parse(junit).getroot().iter('testcase'))
    sira = [v.get('classname', '') for v in vakalar]
    dusen = [f"{v.get('classname')}::{v.get('name')}" for v in vakalar
             if v.find('failure') is not None or v.find('error') is not None]

    assert sira and sira[0].endswith('TestB408TurbomakineVerimKapisi'), sira[:3]
    assert any(s.startswith('tests.test_combustion_cea_validation')
               for s in sira), 'kirletici dosya koşmadı'
    kurban = [s for s in sira if s.endswith('TestB409NegatifPompaDeltaP')]
    assert kurban, ('kurban sınıfı koşmadı', sonuc.stdout[-800:])
    assert not dusen and sonuc.returncode == 0, (dusen, sonuc.stdout[-1500:])



# ===========================================================================
# 2. tur (14 Eki) — K-1…K-4 (rapor.md "2. tur (14 Eki) — K-1…K-4")
# ===========================================================================
import ast
import json
import re
import textwrap

from hrma.engines import cea_bridge as cb

#: K-1 bekçisinin noktası: başka testlerin lru önbelleğine düşmeyecek kadar
#: sıra dışı bir oda basıncı [bar] (25 kN RP-1/LOX ölçümünün komşusu).
_K1_PC_BAR = 61.37
_K1_MR = 2.6
_K1_EPS = 20.0
#: Statik tablo yedeği (yalnız düşüşün GÖRÜNÜR olduğunu sınamak için).
_K1_YEDEK = {'c_star': 1700.0, 'T_c': 3500.0, 'gamma': 1.2, 'mw': 22.0}

#: RocketCEA ``CEA_Obj`` genel yöntemleri (rocketcea 1.2.x, dir(CEA_Obj)).
#: Kurulu sürümde fazlası varsa liste eksik demektir (aşağıda denetlenir).
_CEA_YONTEMLERI = frozenset({
    'estimate_Ambient_Isp', 'getFrozen_IvacCstrTc', 'getFrozen_PambCf',
    'getMRforER', 'get_Chamber_Cp', 'get_Chamber_Density', 'get_Chamber_H',
    'get_Chamber_MachNumber', 'get_Chamber_MolWt_gamma',
    'get_Chamber_SonicVel', 'get_Chamber_Transport', 'get_Cstar',
    'get_Densities', 'get_Enthalpies', 'get_Entropies', 'get_Exit_Transport',
    'get_HeatCapacities', 'get_Isp', 'get_IvacCstrTc',
    'get_IvacCstrTc_ChmMwGam', 'get_IvacCstrTc_ThtMwGam',
    'get_IvacCstrTc_exitMwGam', 'get_MachNumber', 'get_PambCf', 'get_PcOvPe',
    'get_Pinj_over_Pcomb', 'get_SonicVelocities', 'get_SpeciesMassFractions',
    'get_SpeciesMoleFractions', 'get_Tcomb', 'get_Temperatures',
    'get_Throat_Isp', 'get_Throat_MolWt_gamma', 'get_Throat_PcOvPe',
    'get_Throat_Transport', 'get_description', 'get_eps_at_PcOvPe',
    'get_eqratio', 'get_exit_MolWt_gamma', 'get_full_cea_output',
    'setupCards'})
_KILIT_ADI = '_CEA_STATE_LOCK'
_YALITIM_ADI = 'ensure_isolated_cea_data_dir'
_KOPRU_MODULU = 'hrma.engines.cea_bridge'
#: Bugün CEA_Obj kuran ürün modülleri (taramanın boşa dönmediğinin ölçüsü).
_BILINEN_CEA_MODULLERI = {
    'hrma/engines/cea_bridge.py', 'hrma/engines/cycle_power_balance.py',
    'hrma/data/web_propellant_api.py', 'hrma/data/external_data_fetcher.py'}


@pytest.fixture
def temiz_kopru_onbellegi():
    """Köprünün iki lru önbelleği test başında ve sonunda boşaltılır (yalnız
    hız önbelleği; içerik CEA'nın kendi hesabıdır)."""
    cb._cea_obj.cache_clear()
    cb._compute_rocketcea.cache_clear()
    yield
    cb._cea_obj.cache_clear()
    cb._compute_rocketcea.cache_clear()


def _bagimsiz_cstar(ox, yakit, pc_bar, mr):
    """Kâhin: köprüden BAĞIMSIZ, taze kurulmuş CEA_Obj'nin c*'ı [m/s].

    RocketCEA sonuçları ``desc`` başına süreç-global bir sözlükte saklar;
    taze nesne aynı sözlüğü görseydi köprünün az önce yazdığı sonucu geri
    okurdu (bağımsız olmazdı). Bu yüzden kâhin BOŞ bir sözlükle çözülür,
    sonra önceki sözlük yerine konur."""
    co = _cea_module
    with cb._CEA_STATE_LOCK:
        onceki = co._CacheObjDict
        co._CacheObjDict = {}
        try:
            nesne = co.CEA_Obj(oxName=ox, fuelName=yakit)
            return float(nesne.get_Cstar(Pc=pc_bar * cb.BAR_TO_PSIA,
                                         MR=mr)) * cb.FT_PER_S_TO_M_PER_S
        finally:
            co._CacheObjDict = onceki


@pytest.mark.parametrize('yol', ['clearCache', 'add_new_card'])
def test_k1_bridge_rebuilds_stale_cea_obj_instead_of_static_table(
        yalitilmis_kutuphane, temiz_kopru_onbellegi, yol):
    """K-1: kütüphane önbelleği boşaldıktan sonra köprünün YENİ noktası yine
    CEA'dır (statik tabloya inmez) ve c* bağımsız kâhinle BİT-AYNIDIR."""
    co = yalitilmis_kutuphane
    isinma = cb.get_combustion_properties('rp1', 'lox', _K1_PC_BAR - 1.0,
                                          _K1_MR, expansion_ratio=_K1_EPS,
                                          fallback=_K1_YEDEK)
    assert isinma['source'] == 'rocketcea'
    nesne = cb._cea_obj('LOX', 'RP1', None)
    assert nesne.desc in co.getCacheDict()

    _kutuphane_onbellegini_bosalt(co, yol)
    assert nesne.desc not in co.getCacheDict(), (
        f'{yol} kütüphane kaydını silmedi — bekçi ölçmüyor')

    sonra = cb.get_combustion_properties('rp1', 'lox', _K1_PC_BAR, _K1_MR,
                                         expansion_ratio=_K1_EPS,
                                         fallback=_K1_YEDEK)
    assert sonra['source'] == 'rocketcea', sonra['validity']
    assert 'fallback_reason' not in sonra['validity']
    assert sonra['c_star_m_s'] == _bagimsiz_cstar('LOX', 'RP1', _K1_PC_BAR,
                                                  _K1_MR)


def test_k1_live_object_is_reused_while_record_alive(yalitilmis_kutuphane,
                                                     temiz_kopru_onbellegi):
    """Kayıt yerindeyken aynı nesne döner (sıcak yol değişmez); kayıt
    silinince yeni nesne kurulur ve kayıt yeniden açılır."""
    co = yalitilmis_kutuphane
    with cb._CEA_STATE_LOCK:
        ilk = cb._live_cea_obj('LOX', 'CH4', None)
        assert cb._live_cea_obj('LOX', 'CH4', None) is ilk
        co.clearCache(show_size=False)
        ikinci = cb._live_cea_obj('LOX', 'CH4', None)
    assert ikinci is not ilk and ikinci.desc in co.getCacheDict()


def test_k1_keyerror_from_lost_record_is_retried_once(
        yalitilmis_kutuphane, temiz_kopru_onbellegi, monkeypatch):
    """Çözüm SIRASINDA kayıt kaybolursa nesne yeniden kurulur ve çağrı bir
    kez yeniden denenir; kayıt yerindeyken gelen KeyError denenmez."""
    co = yalitilmis_kutuphane
    gercek = cb._solve_with_cea_obj
    cagri = []

    def kaybeden(c, *a):
        cagri.append(c)
        if len(cagri) == 1:
            co.clearCache(show_size=False)
            raise KeyError(c.desc)
        return gercek(c, *a)

    monkeypatch.setattr(cb, '_solve_with_cea_obj', kaybeden)
    with cb._CEA_STATE_LOCK:
        sonuc = cb._compute_rocketcea_locked('RP1', 'LOX', _K1_PC_BAR + 1.0,
                                             _K1_MR, _K1_EPS, None, None)
    assert len(cagri) == 2 and cagri[1] is not cagri[0]
    assert sonuc['c_star_m_s'] == _bagimsiz_cstar('LOX', 'RP1',
                                                  _K1_PC_BAR + 1.0, _K1_MR)

    def hep_keyerror(c, *a):
        cagri.append(c)
        raise KeyError('kayit-yerinde')

    cagri.clear()
    monkeypatch.setattr(cb, '_solve_with_cea_obj', hep_keyerror)
    with pytest.raises(KeyError), cb._CEA_STATE_LOCK:
        cb._compute_rocketcea_locked('RP1', 'LOX', _K1_PC_BAR + 2.0, _K1_MR,
                                     _K1_EPS, None, None)
    assert len(cagri) == 1


def _i18n_anahtar_metinleri(anahtar):
    js = (KOK / 'hrma/static/js/i18n_common.js').read_text(encoding='utf-8')
    return re.findall(r"'" + re.escape(anahtar) + r"'\s*:\s*'((?:[^'\\]|\\.)*)'",
                      js)


def test_k1_fallback_with_cea_installed_is_named_not_silent(
        cea_kapisi, temiz_kopru_onbellegi, monkeypatch):
    """CEA KURULU iken çağrı düşerse statik tabloya iniş yanıtta ADIYLA
    yazılır: validity['fallback_reason'] + {code, params, severity} kaydı;
    kodun EN ve TR metni var ve {error} yer tutucusunu taşıyor."""
    def patlayan(*a, **k):
        raise RuntimeError('olcum')

    monkeypatch.setattr(cb, '_compute_rocketcea', patlayan)
    r = cb.get_combustion_properties('rp1', 'lox', _K1_PC_BAR, _K1_MR,
                                     expansion_ratio=_K1_EPS,
                                     fallback=_K1_YEDEK)
    assert r['source'] == 'static_table'
    v = r['validity']
    assert v['fallback_reason'] == cb.FALLBACK_REASON_CEA_CALL_FAILED
    assert v['fallback_warning'] == {
        'code': cb.WARN_CEA_CALL_FAILED, 'params': {'error': 'RuntimeError'},
        'severity': 'warning'}
    json.dumps(r)   # yanıt gövdesine olduğu gibi girer
    metinler = _i18n_anahtar_metinleri(cb.WARN_CEA_CALL_FAILED)
    assert len(metinler) == 2, metinler          # EN + TR
    assert all('{error}' in m for m in metinler)


def test_k2_validation_helper_does_not_clear_library_cache(cea_kapisi,
                                                           monkeypatch):
    """K-2: doğrulama dosyasının kart yardımcısı ikinci çağrıda kartı
    YENİDEN tanımlamaz, dolayısıyla RocketCEA'nın süreç-global sonuç
    önbelleğini boşaltmaz (tetik kalktı)."""
    import rocketcea.input_cards as ic
    from tests import test_combustion_cea_validation as dogrulama
    kartlar = dict(_cea_module.oxCards)
    kartlar.pop(dogrulama._CEA_N2O_SIVI_KARTI, None)
    # add_new_oxidizer cea_obj'nin, yardımcının denetimi input_cards'ın
    # adıyla okur; ürün ortamında ikisi AYNI sözlüktür — burada da öyle.
    monkeypatch.setattr(_cea_module, 'oxCards', kartlar)
    monkeypatch.setattr(ic, 'oxCards', kartlar)
    monkeypatch.setattr(_cea_module, '_CacheObjDict',
                        {'V3_K2_NOBETCI': object()})
    assert dogrulama._cea_oksitleyici('N2O') == dogrulama._CEA_N2O_SIVI_KARTI
    assert dogrulama._cea_oksitleyici('N2O') == dogrulama._CEA_N2O_SIVI_KARTI
    assert 'V3_K2_NOBETCI' in _cea_module.getCacheDict(), (
        'kart yardımcısı aynı adlı kartı yeniden tanımladı: RocketCEA '
        'önbelleği boşaldı (12 Eki dilim 2 tetiği geri geldi)')


_TETIK_DOSYASI = textwrap.dedent("""\
    import rocketcea.cea_obj as co

    def test_tetik_kutuphane_onbellegini_bosaltir():
        kayitlar = list(co.getCacheDict())
        assert any(k.startswith('LOX / ') for k in kayitlar), (
            'doldurucu kütüphane kaydı açmadı', kayitlar)
        kart = '\\n'.join(co.oxCards['LOX'])
        co.add_new_oxidizer('LOX_V3_TETIK', kart)
        co.add_new_oxidizer('LOX_V3_TETIK', kart)
        assert not co.getCacheDict(), 'tetik önbelleği boşaltmadı'
    """)


def test_self_made_trigger_then_victim_same_process_green(cea_kapisi,
                                                         tmp_path):
    """K-2'den sonra tetik bekçinin KENDİ içinde üretilir: doldurucu ->
    (aynı adlı kartı iki kez tanıtan) tetik -> kurban, TEK süreçte. Tetik
    düğümü önbelleğin GERÇEKTEN boşaldığını kendisi doğrular (tetiksiz
    yeşil sayılmaz); kurban yeşil kalmalı."""
    tetik = tmp_path / 'test_v3_tetik.py'
    tetik.write_text(_TETIK_DOSYASI, encoding='utf-8')
    junit = tmp_path / 'tetik.xml'
    ortam = dict(os.environ)
    ortam.update(HRMA_PROJECTS_DIR=str(tmp_path / 'projeler'), BROWSER='echo',
                 OMP_NUM_THREADS='2', VECLIB_MAXIMUM_THREADS='2',
                 MKL_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2')
    (tmp_path / 'projeler').mkdir()
    sonuc = subprocess.run(
        [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
         '--rootdir', str(KOK), '-c', str(KOK / 'pytest.ini'),
         f'--junitxml={junit}', _DOLDURAN, str(tetik), _KURBAN],
        cwd=KOK, env=ortam, capture_output=True, text=True,
        timeout=_ALT_SUREC_TAVANI_S)
    vakalar = list(ET.parse(junit).getroot().iter('testcase'))
    adlar = [f"{v.get('classname')}::{v.get('name')}" for v in vakalar]
    dusen = [a for a, v in zip(adlar, vakalar)
             if v.find('failure') is not None or v.find('error') is not None]
    assert adlar and 'TestB408TurbomakineVerimKapisi' in adlar[0], adlar[:3]
    assert any('test_tetik_kutuphane_onbellegini_bosaltir' in a
               for a in adlar), ('tetik koşmadı', adlar)
    assert any('TestB409NegatifPompaDeltaP' in a for a in adlar), (
        'kurban koşmadı', sonuc.stdout[-800:])
    assert not dusen and sonuc.returncode == 0, (dusen, sonuc.stdout[-1500:])


# --- K-4: CEA çağrıları köprünün TEK kilidi altında (AST, belirlenimci) ----
def _cea_modulleri():
    return sorted(
        str(y.relative_to(KOK)) for y in (KOK / 'hrma').glob('**/*.py')
        if 'CEA_Obj' in y.read_text(encoding='utf-8'))


def _kilit_with_mi(dugum):
    for oge in dugum.items:
        e = oge.context_expr
        ad = getattr(e, 'id', None) or getattr(e, 'attr', None)
        if ad == _KILIT_ADI:
            return True
    return False


def _kilit_denetimi(agac):
    """(kilit dışı CEA çağrıları, sayılan CEA çağrısı) — sözcüksel kural:
    çağrı ``with _CEA_STATE_LOCK:`` gövdesinde, ya da YALNIZ kilit altında
    çağrılan bir işlevin gövdesinde olmalı (modül içi, sabit nokta)."""
    ebeveyn = {}
    for d in ast.walk(agac):
        for c in ast.iter_child_nodes(d):
            ebeveyn[c] = d

    def zincir(d):
        while d in ebeveyn:
            d = ebeveyn[d]
            yield d

    def kilitte(d):
        return any(isinstance(a, ast.With) and _kilit_with_mi(a)
                   for a in zincir(d))

    def islev(d):
        for a in zincir(d):
            if isinstance(a, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return a.name
        return None

    cagri_yerleri = {}
    for d in ast.walk(agac):
        if isinstance(d, ast.Call) and isinstance(d.func, ast.Name):
            cagri_yerleri.setdefault(d.func.id, []).append(d)
    tanimli = {d.name for d in ast.walk(agac)
               if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef))}
    kilitli_islev = set()
    degisti = True
    while degisti:
        degisti = False
        for ad in tanimli - kilitli_islev:
            yerler = cagri_yerleri.get(ad, [])
            if yerler and all(kilitte(y) or islev(y) in kilitli_islev
                              for y in yerler):
                kilitli_islev.add(ad)
                degisti = True

    disarida, sayi = [], 0
    for d in ast.walk(agac):
        if not isinstance(d, ast.Call):
            continue
        f = d.func
        cea = ((isinstance(f, ast.Attribute) and f.attr in _CEA_YONTEMLERI)
               or (isinstance(f, ast.Name) and f.id == 'CEA_Obj')
               or (isinstance(f, ast.Attribute) and f.attr == 'CEA_Obj'))
        if not cea:
            continue
        sayi += 1
        if not (kilitte(d) or islev(d) in kilitli_islev):
            disarida.append((d.lineno, ast.unparse(f)))
    return disarida, sayi


def test_k4_cea_method_list_covers_installed_rocketcea(cea_kapisi):
    kurulu = {n for n in dir(_cea_module.CEA_Obj) if not n.startswith('_')}
    assert kurulu <= _CEA_YONTEMLERI, sorted(kurulu - _CEA_YONTEMLERI)


def test_k4_every_cea_call_is_under_the_bridge_lock():
    """K-4: ürün kodunda HER CEA_Obj kurulumu ve yöntem çağrısı köprünün
    süreç kilidi altında (Fortran COMMON durumu süreç-global; 4 iş
    parçacığında sessiz yanlış sayı ölçüldü, rapor.md 2. tur)."""
    moduller = _cea_modulleri()
    assert _BILINEN_CEA_MODULLERI <= set(moduller), moduller
    ihlal = {}
    for yol in moduller:
        agac = ast.parse((KOK / yol).read_text(encoding='utf-8'))
        disarida, sayi = _kilit_denetimi(agac)
        assert sayi > 0, f'{yol}: CEA çağrısı sayılmadı — tarama boşa dönüyor'
        if disarida:
            ihlal[yol] = disarida
    assert not ihlal, f'kilit dışında CEA çağrısı: {ihlal}'


def test_k4_single_lock_and_isolated_data_dir_before_construction():
    """Kilit TEKTİR (köprü dışındaki her ``_CEA_STATE_LOCK`` bağı köprüden
    ithaldir) ve ``CEA_Obj`` kuran her işlev önce süreç başına yalıtılmış
    veri dizinini sabitler."""
    for yol in _cea_modulleri():
        agac = ast.parse((KOK / yol).read_text(encoding='utf-8'))
        yalitim_adlari = {_YALITIM_ADI}
        for d in ast.walk(agac):
            if isinstance(d, ast.ImportFrom) and d.module == _KOPRU_MODULU:
                for a in d.names:
                    if a.name == _YALITIM_ADI and a.asname:
                        yalitim_adlari.add(a.asname)
            if yol == 'hrma/engines/cea_bridge.py':
                continue
            if isinstance(d, ast.ImportFrom):
                for a in d.names:
                    if (a.asname or a.name) == _KILIT_ADI:
                        assert d.module == _KOPRU_MODULU and \
                            a.name == _KILIT_ADI, (yol, d.lineno)
            elif isinstance(d, (ast.Assign, ast.AnnAssign)):
                hedefler = d.targets if isinstance(d, ast.Assign) \
                    else [d.target]
                for h in hedefler:
                    assert getattr(h, 'id', None) != _KILIT_ADI, (
                        f'{yol}:{d.lineno}: ikinci CEA kilidi tanımlanmış')
        for f in ast.walk(agac):
            if not isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            kurulum = [c for c in ast.walk(f) if isinstance(c, ast.Call)
                       and getattr(c.func, 'id', None) == 'CEA_Obj']
            if not kurulum:
                continue
            yalitim = [c for c in ast.walk(f) if isinstance(c, ast.Call)
                       and (getattr(c.func, 'id', None)
                            or getattr(c.func, 'attr', None)) in yalitim_adlari]
            assert yalitim and min(c.lineno for c in yalitim) < \
                min(c.lineno for c in kurulum), (
                f'{yol}:{f.name}: CEA_Obj yalıtılmış veri dizini '
                f'sabitlenmeden kuruluyor')


_ES_BETIGI = textwrap.dedent("""\
    import json, os, sys
    sys.path.insert(0, sys.argv[1])
    kip, cikti = sys.argv[2], sys.argv[3]
    from concurrent.futures import ThreadPoolExecutor
    sys.stdout = open(os.devnull, 'w')
    from hrma.engines import cycle_power_balance as cpb
    from hrma.engines import cea_bridge as cb
    from hrma.data.web_propellant_api import WebPropellantAPI
    web = object.__new__(WebPropellantAPI)
    isler = []
    for y, mrs in (('rp1', (0.31, 0.43, 6.1)), ('methane', (0.29, 0.41, 5.7)),
                   ('lh2', (0.73, 1.07, 5.3))):
        for mr in mrs:
            for p in (83.0, 127.0, 211.0):
                isler.append(('pb', y, mr, p))
    for y, mr in (('rp1', 2.41), ('methane', 3.37), ('ethanol', 1.47)):
        for pc in (47.0, 97.0, 163.0):
            isler.append(('cb', y, mr, pc))
    for y, ox, mr in (('rp1', 'lox', 2.53), ('mmh', 'n2o4', 1.93)):
        isler.append(('web', y, ox, mr))
    def kos(i):
        if i[0] == 'pb':
            r = cpb.preburner_gas_properties(i[1], 'lox', i[2], i[3])
        elif i[0] == 'cb':
            r = cb.get_combustion_properties(i[1], 'lox', i[3], i[2],
                                             expansion_ratio=31.0)
        else:
            r = web._use_rocketcea_library(i[1], i[2], 59.0, i[3])
            r.pop('fetched_at', None)
        return repr(i), json.dumps(r, sort_keys=True, default=repr)
    if kip == 'seri':
        sonuc = dict(map(kos, isler))
    else:
        with ThreadPoolExecutor(max_workers=int(kip)) as ex:
            sonuc = dict(ex.map(kos, isler))
    json.dump(sonuc, open(cikti, 'w'), sort_keys=True)
    """)

#: Eşzamanlı kıyasın iş parçacığı sayısı (waitress threads=4, run.py).
_ES_IS_PARCACIGI = 4
#: Betiğin sabit iş listesinin boyu: 3 yakıt × 3 O/F × 3 basınç ön yakıcı
#: + 3 × 3 köprü noktası + 2 web yolu (toplanan iş sayısı denetlenir).
_ES_IS_SAYISI = 27 + 9 + 2


def test_k4_concurrent_equals_serial_bit_identical(cea_kapisi, tmp_path):
    """İkinci kanıt: sabit iş listesi TAZE süreçte seri ve 4 iş
    parçacığında çözülür; bütün yapraklar BİT-AYNI. (Kilitsiz kodda aynı
    kıyas 5 koşunun 5'inde 19-32 yaprak farkı verdi; rapor.md 2. tur.)"""
    betik = tmp_path / 'es_kiyas.py'
    betik.write_text(_ES_BETIGI, encoding='utf-8')
    ortam = dict(os.environ)
    ortam.update(HRMA_PROJECTS_DIR=str(tmp_path / 'projeler'),
                 BROWSER='echo', OMP_NUM_THREADS='2')
    (tmp_path / 'projeler').mkdir()
    ciktilar = {}
    for kip in ('seri', str(_ES_IS_PARCACIGI)):
        cikti = tmp_path / f'{kip}.json'
        r = subprocess.run([sys.executable, '-I', str(betik), str(KOK), kip,
                            str(cikti)], env=ortam, capture_output=True,
                           text=True, timeout=_ALT_SUREC_TAVANI_S)
        assert r.returncode == 0, r.stderr[-1500:]
        ciktilar[kip] = json.loads(cikti.read_text())
    seri, es = ciktilar['seri'], ciktilar[str(_ES_IS_PARCACIGI)]
    assert len(seri) == _ES_IS_SAYISI and set(seri) == set(es)
    farkli = sorted(k for k in seri if seri[k] != es[k])
    assert not farkli, farkli
