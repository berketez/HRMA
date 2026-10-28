"""V301/PANEL kalem 4 (C-5, H-PANEL DEVİR 5) — ΔP/Pc cümlesi kökte, besleme tipine göre.

ÖLÇÜLEN KUSUR (H-PANEL RAPOR §16a): doğrulayıcı tavan aşımında her motora
"besleme basıncı ve POMPA işi artar" diyordu; uç hibritte kaydı sonradan
yeniden adlandırıyordu (``_hibrit_dp_pc_gerekcesi``). Cümle artık
doğrulayıcıda kurulur: pompalı → pompa işi; basınç beslemeli → tank basıncı;
kendinden basınçlı N2O → bilgi notu (ΔP buhar basıncının sonucudur); besleme
tipi bilinmiyorsa bedel adlandırılmaz.
"""
import contextlib
import io
import json
import pathlib

import pytest

from hrma.validation.validation_system import (
    DP_PC_HIGH_CODE_BY_FEED,
    DP_PC_HIGH_FEED_NOT_STATED,
    ValidationSystem,
)

KOK = pathlib.Path(__file__).resolve().parents[1]
I18N = KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js'
#: Tavanın (0,35) üstünde bir enjektör: ΔP/Pc = 15 / 20 = 0,75.
ENJEKTOR = {'pressure_drop': 15.0, 'reynolds_number': 5e4,
            'exit_velocity': 30.0}


def _kayitlar(feed_system):
    return ValidationSystem().validate_injector_data(
        dict(ENJEKTOR), chamber_pressure=20.0, feed_system=feed_system,
        feed_pressure_source='kaynak')


@pytest.mark.parametrize('besleme', sorted(DP_PC_HIGH_CODE_BY_FEED) + [None])
def test_cumle_besleme_tipine_gore(besleme):
    kod, onem = DP_PC_HIGH_CODE_BY_FEED.get(besleme,
                                            DP_PC_HIGH_FEED_NOT_STATED)
    dp = [k for k in _kayitlar(besleme)
          if k['code'].startswith('warn.validation.dp_pc')]
    assert [(k['code'], k['severity']) for k in dp] == [(kod, onem)]
    assert dp[0]['params'] == {'ratio': 0.75, 'max': 0.35}
    assert dp[0]['feed_system'] == besleme
    assert dp[0]['feed_pressure_source'] == 'kaynak'


def test_pompa_yalniz_pompalida_anilir():
    metin = I18N.read_text(encoding='utf-8')

    def cumle(kod):
        bas = metin.index("'%s':" % kod)
        return metin[bas:metin.index('\n', bas)]
    assert 'pump work' in cumle('warn.validation.dp_pc_high')
    for kod in ('warn.validation.dp_pc_high_pressure_fed',
                'warn.validation.dp_pc_self_pressurised'):
        assert 'there is no pump' in cumle(kod), kod
    assert 'pump work' not in cumle('warn.validation.dp_pc_high_feed_not_stated')
    for kod in [k for k, _ in DP_PC_HIGH_CODE_BY_FEED.values()] + [
            DP_PC_HIGH_FEED_NOT_STATED[0]]:
        assert metin.count("'%s':" % kod) == 2, kod      # EN + TR


def test_bilgi_notu_genel_durumu_uyariya_cekmez():
    v = ValidationSystem()
    rapor = v.comprehensive_validation(
        {'chamber_pressure': 20.0}, dict(ENJEKTOR),
        feed_system='self_pressurised', feed_pressure_source='kaynak')
    kodlar = {(k['code'], k['severity']) for k in rapor['regular_warnings']}
    assert ('warn.validation.dp_pc_self_pressurised', 'info') in kodlar
    uyarilar = [k for k in rapor['regular_warnings']
                if k['severity'] == 'warning']
    if not uyarilar and not rapor['critical_warnings'] \
            and not rapor['axes_not_evaluated']:
        assert rapor['overall_status']['code'] == 'status.normal'


@pytest.fixture(scope='module')
def ornek_hibrit():
    from hrma.app import app
    alan = json.loads((KOK / 'examples' / 'Example Hybrid N2O-HTPB 3kN.hrma')
                      .read_text(encoding='utf-8'))['inputs']['fields']
    app.config['TESTING'] = True
    t = io.StringIO()
    with app.test_client() as c, contextlib.redirect_stdout(t), \
            contextlib.redirect_stderr(t):
        r = c.post('/calculate', json=alan)
    assert r.status_code == 200
    return r.get_json()


def test_ornek_hibrit_kendinden_basincli_not(ornek_hibrit):
    from hrma.engines.hybrid_rocket_engine import FEED_PRESSURE_SOURCE_N2O_SAT
    kaynak = ornek_hibrit['motor']['injector_design']['feed_pressure_source']
    assert kaynak == FEED_PRESSURE_SOURCE_N2O_SAT
    dog = ornek_hibrit['validation']
    hepsi = dog['critical_warnings'] + dog['regular_warnings']
    kodlar = [k['code'] for k in hepsi]
    assert 'warn.validation.dp_pc_high' not in kodlar
    dp = [k for k in hepsi if k['code'].startswith('warn.validation.dp_pc')]
    assert [(k['code'], k['severity'], k['feed_system']) for k in dp] == [
        ('warn.validation.dp_pc_self_pressurised', 'info',
         'self_pressurised')]
    assert dog['injector_assessment']['pressure_drop_ratio'][
        'feed_system'] == 'self_pressurised'
