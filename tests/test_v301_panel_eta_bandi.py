"""V301/PANEL kalem 2 (C-6, H-PANEL AÇIK 2) — hibrit η_c* belirsizlik bandı.

ÖLÇÜLEN KUSUR (``docs/scofield/raw/OH/V301/panel/eta_bandi_once.json``):
kaynaklı varsayılan η_c* 0,89, 26 doğrulama kaydının ortancasıdır; ama
belirsizlik dağılımı σ 0,03 / kesme 0,80-1,00 kullanıyordu. Aynı kayıtların
örnek σ'sı (n − 1) 0,0574, aralığı 0,77-0,99 — yayımlanan P5-P95 bandı
gözlenen saçılımın yaklaşık yarısıydı (c* 150,9 m/s ⟷ sonra 254,5 m/s).

Bekçiler: σ kayıtlardan yeniden hesaplanır; kaynaklı varsayılanda dağılım o
σ ve aralıkla kurulur; kullanıcı η'sında beyanlı σ 0,03 kalır.
"""
import glob
import json
import pathlib
import statistics

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]


def _kayitlar(kayit):
    degerler = []
    for yol in sorted(glob.glob(str(
            KOK / 'hrma' / 'data' / 'validation_records' / 'hybrid'
            / '*.json'))):
        r = json.loads(pathlib.Path(yol).read_text(encoding='utf-8'))
        if not any(r['test_id'].startswith(p)
                   for p in kayit['record_prefixes']):
            continue
        e = (r.get('measured') or {}).get('c_star_efficiency')
        if e is not None:
            degerler.append(float(e))
    return degerler


def test_sigma_kayitlardan_yeniden_hesaplanir():
    from hrma.engines.hybrid_rocket_engine import HYBRID_ETA_C_STAR_MEASURED
    kayit = HYBRID_ETA_C_STAR_MEASURED[('n2o', 'htpb')]
    degerler = _kayitlar(kayit)
    assert len(degerler) == kayit['n_tests'] == 26
    # Sabit 4 basamağa yuvarlanmıştır; tolerans yuvarlama adımının yarısı.
    assert statistics.stdev(degerler) == pytest.approx(
        kayit['sample_stdev'], abs=5e-5)
    assert (min(degerler), max(degerler)) == tuple(kayit['measured_band'])


def _eta(inputs):
    from hrma.analysis import uq_adapters as uqa
    return uqa.center_hybrid_eta_distribution(
        uqa.build_distributions('hybrid', None), inputs)['eta_c_star']


def test_kaynakli_varsayilanda_dagilim_kayitlardan():
    from hrma.engines.hybrid_rocket_engine import HYBRID_ETA_C_STAR_MEASURED
    kayit = HYBRID_ETA_C_STAR_MEASURED[('n2o', 'htpb')]
    d = _eta({'oxidizer_type': 'n2o', 'fuel_type': 'htpb'})
    assert d.mean == d.nominal_value() == kayit['eta_c_star']
    assert d.sigma == kayit['sample_stdev']
    assert (d.low, d.high) == tuple(kayit['measured_band'])
    assert 'sample standard deviation (n - 1)' in d.source_note


def test_kullanici_etasinda_beyanli_sigma_kalir():
    from hrma.analysis.uncertainty import DEFAULT_UQ_MODELS
    beyan = DEFAULT_UQ_MODELS['hybrid']['eta_c_star']
    d = _eta({'oxidizer_type': 'n2o', 'fuel_type': 'htpb',
              'combustion_efficiency': 92.0})
    assert d.mean == pytest.approx(0.92)
    assert d.sigma == beyan.sigma == 0.03
    assert (d.low, d.high) == (beyan.low, beyan.high)
    assert 'as declared' in d.source_note


def test_kaynaksiz_ciftte_dagilim_degismez():
    from hrma.analysis import uq_adapters as uqa
    once = uqa.build_distributions('hybrid', None)['eta_c_star']
    d = _eta({'oxidizer_type': 'lox', 'fuel_type': 'paraffin'})
    assert (d.mean, d.sigma, d.low, d.high, d.nominal_override) == (
        once.mean, once.sigma, once.low, once.high, once.nominal_override)
