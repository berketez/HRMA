"""V306/DİL-SUNUCU bekçileri — sunucu metinlerinde üslup ve ham metin.

Kanıt: docs/scofield/raw/OH/V306/dil-sunucu/RAPOR.md. Hepsi hafif (motor
koşturmaz); sayı/hüküm değil METİN sözleşmesini kilitler.
"""
import ast
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: 'invented' üslubunun bu kulvarda bilerek bırakıldığı yerler (başka
#: kulvarın bölgesi; RAPOR §5 DEVİR). Liste ancak KÜÇÜLEBİLİR.
INVENT_DEVIR = {
    # Ek tur (9 Kas 16:2x): sıvı motorun 22 ve /calculate_liquid'in 4 metni
    # çevrildi; liste küçüldü.
    'hrma/analysis/slosh_analysis.py': 1,         # 3.0.7 dosyası
}


def _docstring_disi_dizgiler(yol):
    agac = ast.parse(yol.read_text(encoding='utf-8'))
    belge = set()
    for d in ast.walk(agac):
        if (isinstance(d, ast.Expr) and isinstance(d.value, ast.Constant)
                and isinstance(d.value.value, str)):
            belge.add(id(d.value))
    for d in ast.walk(agac):
        if (isinstance(d, ast.Constant) and isinstance(d.value, str)
                and id(d) not in belge):
            yield d


def test_invented_uslubu_yalniz_devir_bolgelerinde():
    sayac = {}
    for yol in sorted((ROOT / 'hrma').rglob('*.py')):
        for d in _docstring_disi_dizgiler(yol):
            metin = re.sub(r'inventor', '', d.value, flags=re.I)
            if re.search(r'invent', metin, re.I):
                rel = yol.relative_to(ROOT).as_posix()
                sayac[rel] = sayac.get(rel, 0) + 1
    fazla = {k: v for k, v in sayac.items()
             if v > INVENT_DEVIR.get(k, 0)}
    assert not fazla, ("'invented' üslubu kullanıcı/API metnine döndü "
                       '(tarafsız dil: used / assumed / published): %r' % fazla)


def test_kap_payi_esikle_celismez():
    from hrma.analysis.pressure_vessel import (
        MARGINAL_BURST_MARGIN, _esik_alti_metni)
    for pay in (1.1996, 1.19949, 1.199999999, 1.15, 1.0):
        metin = _esik_alti_metni(pay, MARGINAL_BURST_MARGIN)
        assert float(metin) < MARGINAL_BURST_MARGIN, (pay, metin)


def test_kap_kod_kapsami_kunyesi_secimi_soyler():
    from hrma.analysis.pressure_vessel import NASA_5012C_SCOPE_BASIS as k
    assert 'in this release' not in k
    assert 'HRMA choice' in k and 'NASA-STD-5001B' in k
    assert not re.search(r'5001B[^.]*\d\.\d', k), (
        '5001B katsayısı künyeye yazılmaz (birincil kaynakla doğrulanmadı)')


def test_emniyet_denetimi_kodla_yayimlanir():
    from hrma.app import _dogrulayici_uyari_kayitlari
    from hrma.validation.motor_validation import MotorDataValidator
    uyarilar = []
    MotorDataValidator()._perform_safety_checks(
        {'thrust': 60000.0, 'burn_time': 120.0}, 'hybrid', [], uyarilar)
    kayitlar = _dogrulayici_uyari_kayitlari(uyarilar)
    kodlar = {k['code'] for k in kayitlar}
    assert kodlar == {'warn.validator.thrust_professional_stand',
                      'warn.validator.burn_time_long'}
    for k in kayitlar:
        assert k['fallback'] == k['params']['message']
        assert 'test stand' in k['fallback'] or 'thermal' in k['fallback']
    assert kayitlar[0]['params']['thrust_N'] == 60000.0


def test_pdf_bekletilen_hucre_metni():
    from hrma.export import pdf_generator as pg
    G = pg.PDFReportGenerator
    assert G._fmt(None) == 'N/A'
    jeton = pg._EKSIK_HUCRE.set(pg.EKSIK_HUCRE_BEKLETILDI)
    try:
        assert G._fmt(None) == 'not published'
        assert G._fmt_unit(None, 'kg') == 'not published'
        assert G._fmt(2.0) != 'not published'
    finally:
        pg._EKSIK_HUCRE.reset(jeton)
    assert pg._ceket_kapisi_etkin({'cooling_circuit_publication': {
        'status': 'not_solved', 'withheld_reason_code': 'jacket_model_limit'}})
    assert not pg._ceket_kapisi_etkin({})


def test_cd_dayanagi_sekil_duzeyinde():
    from hrma.engines.injector_design import discharge_coefficient
    _cd, dayanak = discharge_coefficient('sharp', 4.0)
    assert 'reattaching' in dayanak and 'Fig. 13 p. 38' in dayanak
    _cd, dayanak = discharge_coefficient('radiused', 3.0)
    assert 'Fig. 13' not in dayanak, 'yuvarlatılmış girişe keskin şekil atfı'


def test_kesit_olcusu_yuvarlanmaz():
    from hrma.visualization.visualization import _olcu_mm_metni
    assert _olcu_mm_metni(3.5) == '3.5'
    assert _olcu_mm_metni(364.0) == '364'
    assert _olcu_mm_metni(120.25) == '120.25'


def test_dogrulama_reddi_tek_sabit():
    kaynak = (ROOT / 'hrma' / 'app.py').read_text(encoding='utf-8')
    kod = re.sub(r'(?m)^\s*#.*$', '', kaynak)
    assert kod.count("'Validation failed'") == 1, (
        "'Validation failed' literal olarak yeniden yazıldı; "
        'VALIDATION_FAILED_ERROR kullanın (ekran sözlüğü anahtarıyla birebir)')


def test_cidar_paragrafinda_ham_alan_adi_yok():
    kaynak = (ROOT / 'hrma' / 'app.py').read_text(encoding='utf-8')
    i = kaynak.index("'The wall thickness is the wall HRMA sized in the motor '")
    paragraf = kaynak[i:i + 600].split(')', 1)[0]
    assert 'motor_wall_source' not in paragraf
    assert 'verdict_source' not in paragraf


@pytest.mark.parametrize('anahtar', ['graphite', 'carbon_carbon'])
def test_nozul_izin_sicakligi_kunyesi(anahtar):
    from hrma.data.materials_db import get_material, temperature_limits
    from hrma.engines.solid_rocket_engine import _izin_sicakligi_kunyesi
    kayit = get_material(anahtar)
    metin = _izin_sicakligi_kunyesi(anahtar, kayit, temperature_limits(kayit))
    assert anahtar in metin and 'governs' in metin
    assert 'Record source:' in metin
