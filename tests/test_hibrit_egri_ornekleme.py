"""Hibrit yayın eğrilerinin tepeyi koruyan seyreltmesi (B2-4) — bekçiler.

Ölçülen kusur (14 Ağustos 2026): port 5 mm + t_b 50 s girdisinde
``thrust_curve`` 17 317 nokta / 1,29 MB, ``of_shift_performance`` 17 317
nokta / 1,28 MB — yanıtın %94'ü iki dizi. Katı motor aynı kusuru B2-3'te
çözmüştü; algoritma hrma.analysis.curve_sampling ortak modülüne taşındı
ve hibrit AYNI koddan seyreltir (parametre tutarlılığı kuralı: iki motor
iki kopya taşıyamaz).

Uygulama sonrası ölçüm (bu dosyadaki eşiklerin kaynağı):
yayımlanan 400 / hesaplanan 17 317, impuls sapması %0,0007, tepe itki ve
O/F-Isp uçları birebir korunuyor, iki blok toplamı 62 KB.
"""

import re
import warnings
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope='module')
def uc_kosu():
    """Uç girdi çözümü (bir kez çözülür, tüm testler paylaşır)."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
        e = HybridRocketEngine(thrust=1000.0, burn_time=50.0, of_ratio=7.0,
                               chamber_pressure=30.0, fuel_type='htpb',
                               oxidizer_type='n2o',
                               initial_port_diameter=0.005)
        r = e.calculate()
    return e, r


@pytest.fixture(scope='module')
def normal_kosu():
    """Kısa yanma: dizi zaten tavanın altında, seyreltme YAPILMAMALI."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
        e = HybridRocketEngine(thrust=1000.0, burn_time=3.0, of_ratio=7.0,
                               chamber_pressure=30.0, fuel_type='htpb',
                               oxidizer_type='n2o')
        r = e.calculate()
    return e, r


def test_uc_girdide_yayin_tavana_iner(uc_kosu):
    """17 bin noktalı yanıt şişkinliği kapandı: yayın ≤ tavan + pay."""
    from hrma.analysis.curve_sampling import THRUST_CURVE_MAX_POINTS
    e, r = uc_kosu
    tc = r['thrust_curve']
    s = tc['sampling']
    assert s['points_computed'] > 5000, (
        'uç girdi artık uç değil — test senaryosu gözden geçirilmeli')
    # Kova uçları + zorunlu örnekler tavanı birkaç örnek aşabilir; pay 24
    # (tavanın %6'sı). Eski kusur 43 KATIYDI, pay bunu maskeleyemez.
    assert len(tc['time']) <= THRUST_CURVE_MAX_POINTS + 24
    assert s['decimated'] is True
    assert len(tc['time']) == len(tc['thrust']) == len(tc['pressure']) == \
        len(tc['mass_flow'])


def test_impuls_seyreltmeden_etkilenmez(uc_kosu):
    """Yayımlanan eğriden trapezle hesaplanan impuls ≤ binde 5 sapar.

    (Türetilmiş sayılar zaten TAM çözünürlükten gelir; bu test, grafiği
    okuyan bir mühendisin eğriden çıkaracağı alanın da dürüst kaldığını
    kilitler. Ölçülen gerçek sapma %0,0007.)
    """
    e, r = uc_kosu
    tc = r['thrust_curve']
    I_tam = float(np.trapz(np.asarray(e._thrust_history),
                           np.asarray(e._time_history)))
    I_yayin = float(np.trapz(np.asarray(tc['thrust']),
                             np.asarray(tc['time'])))
    assert abs(I_yayin - I_tam) / I_tam <= 0.005


def test_kritik_ornekler_zorunlu_taSInir(uc_kosu):
    """Tepe itki, tepe basınç ve O/F-Isp uçları yayında BİREBİR var."""
    e, r = uc_kosu
    tc = r['thrust_curve']
    ofp = r['of_shift_performance']
    assert max(tc['thrust']) == float(np.max(e._thrust_history))
    assert max(tc['pressure']) == float(np.max(e._pc_history))
    assert max(ofp['of_ratio']) == float(np.max(e._of_history))
    assert min(ofp['of_ratio']) == float(np.min(e._of_history))
    assert max(ofp['isp']) == float(np.max(e._isp_history))
    assert min(ofp['isp']) == float(np.min(e._isp_history))


def test_iki_seri_ayni_zaman_tabaninda(uc_kosu):
    """thrust_curve ile of_shift_performance zaman dizileri BİREBİR aynı.

    Seri tutarsızlığı kusuru (biri 19,9 s'de biri 20,0 s'de biten seriler)
    8. partide kapatılmıştı; seyreltme onu yeniden açamaz — tek indeks
    kümesi iki bloğa birden uygulanır.
    """
    _, r = uc_kosu
    assert r['thrust_curve']['time'] == r['of_shift_performance']['time']


def test_ilk_ve_son_ornek_korunur(uc_kosu):
    """Yanma penceresinin uçları eğriden okunabilmeli."""
    e, r = uc_kosu
    tc = r['thrust_curve']
    assert tc['time'][0] == float(e._time_history[0])
    assert tc['time'][-1] == float(e._time_history[-1])


def test_ortalamalar_tam_cozunurlukten(uc_kosu):
    """Zaman-ortalamaları seyreltilmiş diziden DEĞİL tam geçmişten gelir."""
    e, r = uc_kosu
    ofp = r['of_shift_performance']
    assert ofp['c_star_time_avg'] == pytest.approx(
        float(np.mean(e._cstar_history)), rel=1e-12)
    assert ofp['isp_time_avg'] == pytest.approx(
        float(np.mean(e._isp_history)), rel=1e-12)


def test_beyan_iki_blokta_da_var(uc_kosu):
    """sampling beyanı: yayın ≠ çözüm çözünürlüğü olduğu açıkça yazılır."""
    _, r = uc_kosu
    for blok in (r['thrust_curve'], r['of_shift_performance']):
        s = blok['sampling']
        assert s['points_computed'] > s['points_published']
        assert s['decimated'] is True
        assert 'UNCHANGED' in s['basis']
        assert s['solver_time_step_s'] is not None


def test_normal_girdide_seyreltme_yok(normal_kosu):
    """Kısa yanmada dizi olduğu gibi yayımlanır; beyan bunu da söyler."""
    e, r = normal_kosu
    tc = r['thrust_curve']
    s = tc['sampling']
    assert s['decimated'] is False
    assert len(tc['time']) == s['points_computed'] == len(e._time_history)


def test_kati_ortak_modulden_okuyor():
    """Katı motorun yerel kopyası SİLİNDİ; iki motor tek kaynaktan okur.

    B2'nin bıraktığı yarım devir tamamlandı: solid_rocket_engine'deki
    _decimate_curve_indices artık kova döngüsü İÇERMEZ, ortak fonksiyona
    delege eder. Kopya geri gelirse (iki algoritmanın sessizce ayrışma
    riski) bu test kırılır. Davranış bit-aynı doğrulandı (sha karşılaştı).
    """
    src = (ROOT / 'hrma' / 'engines' / 'solid_rocket_engine.py').read_text(
        encoding='utf-8')
    govde = src[src.index('def _decimate_curve_indices'):]
    govde = govde[:govde.index('def _published_thrust_curve')]
    assert '_ortak_seyreltme_indeksleri(' in govde
    assert 'linspace' not in govde, 'katıda yerel kova döngüsü geri gelmiş'
    hy = (ROOT / 'hrma' / 'engines' / 'hybrid_rocket_engine.py').read_text(
        encoding='utf-8')
    assert 'from hrma.analysis.curve_sampling import' in hy
    assert '_ortak_seyreltme_indeksleri(' in hy


def test_port_gecmisi_zaten_seyrek():
    """port_history'nin kendi ~200 noktalık seyreltmesi bozulmadı (mevcut
    desen; curve_sampling docstring'i onu emsal gösteriyor)."""
    hy = (ROOT / 'hrma' / 'engines' / 'hybrid_rocket_engine.py').read_text(
        encoding='utf-8')
    assert re.search(r"stride = max\(1, len\(pt\) // 200\)", hy)
