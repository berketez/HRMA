"""3.0.7 — M7-UCUS-4 seçenek (a): çalkantı yayım kuralı (birim bekçisi).

Berke 19 Kas: "çözülsün" → seçenek (a); ana model 20 Kas uyguladı.

Kural (``hrma.app._calkanti_yayim_kurali``): genel hüküm çalkantı kaynaklı
kararsızlık ve pencere varken doğrusal sınır aşılmasa da bağlaşık koşunun
tüm-uçuş sayıları yayımlanmaz (pencerede genlik başlangıç bozucusuna bağlı
büyür). İki nedenin geçerlilik sınırı tek alanda: ``t_gecersiz_bas_s``.

Hızlı test: 6-DOF koşmaz, sentetik hüküm bloğuyla işlevin kendisini sınar.
Uçtan uca karşılığı ``test_v307_ucus_govde.py::TestUcBaglasik``.
"""
import copy

import pytest

from hrma import app as app_mod
from hrma.analysis import six_dof_slosh as k2


def _ozet():
    return {
        'apogee': 5153.7, 'apogee_time': 21.4, 'apogee_msl_m': 5203.7,
        'max_speed': 180.0, 'max_mach': 0.55, 'max_alpha_deg': 3.3,
        'max_alpha_low_q_deg': 4.0, 'lateral_drift_at_end': 120.0,
        'stable': True, 'static_margin_full': 1.63,
        'static_margin_empty': 1.70,
        'flight_verdict': {'flight': 'apogee_reached', 'stability': 'stable'},
    }


def _blok(hukum, pencereler, asildi=False, t_asim=None):
    return {
        'slosh_stability': {
            'genel_hukum': hukum,
            'pencereler': pencereler,
            'baglanmayan_tanklar': [],
            'dogrusal_sinir': {
                'asildi': asildi, 't_ilk_asim_s': t_asim,
                'tank_id_ilk_asim': 'n2o' if asildi else None,
                'asim_sonrasi_kod': k2.DOGRUSAL_GECERLILIK_DISI if asildi else None,
            },
        },
    }


PENCERELER = [
    {'t1': 5.25, 't2': 8.0, 'mod': 'calkanti', 'tank_id': 'n2o'},
    {'t1': 3.535, 't2': 10.32, 'mod': 'calkanti', 'tank_id': 'n2o'},
    # gövde penceresi geçerlilik sınırını belirlemez (tohum kuralı çalkantı
    # genliği içindir)
    {'t1': 1.0, 't2': 2.0, 'mod': 'govde', 'tank_id': None},
]


def test_pencere_varken_baglasik_sayilar_yayimlanmaz():
    s, b = _ozet(), _blok(k2.HUKUM_CALKANTI_KARARSIZ, copy.deepcopy(PENCERELER))
    app_mod._calkanti_yayim_kurali(s, b)
    y = b['yayim']
    assert y['neden_kodu'] == app_mod.CALKANTI_YAYIM_NEDENI_PENCERE \
        == 'BAGLASIK_KOSU_KARARSIZ_PENCERE'
    assert y['gecerlilik'] == app_mod.CALKANTI_YAYIM_PENCERE_KODU \
        == 'KARARSIZ_PENCERE_GENLIK_TOHUMA_BAGLI'
    assert y['t_ilk_asim_s'] is None
    assert y['t_gecersiz_bas_s'] == 3.535      # ilk ÇALKANTI penceresinin başı
    assert y['referans_kosu']['etiket_kodu'] == app_mod.CALKANTI_RIJIT_REFERANS
    for alan in app_mod._CALKANTI_TUM_UCUS_ALANLARI:
        assert s[alan] is None, alan
        assert alan in y['yayimlanmayan_alanlar'], alan
    assert s['flight_verdict']['stability'] == 'not_evaluated'
    assert 'flight_verdict.stability' in y['yayimlanmayan_alanlar']
    # geometri yayımlanmaya devam eder
    assert s['static_margin_full'] == 1.63


def test_sinir_asiminda_gecersiz_bas_ilk_asim_anidir():
    s = _ozet()
    b = _blok(k2.HUKUM_CALKANTI_KARARSIZ, copy.deepcopy(PENCERELER),
              asildi=True, t_asim=27.93)
    app_mod._calkanti_yayim_kurali(s, b)
    y = b['yayim']
    assert y['neden_kodu'] == app_mod.CALKANTI_YAYIM_NEDENI
    assert y['t_ilk_asim_s'] == 27.93
    assert y['t_gecersiz_bas_s'] == 27.93
    assert s['apogee'] is None


def test_pencere_yoksa_yayim_gecerli_ve_dokunulmaz():
    s, b = _ozet(), _blok(k2.HUKUM_KARARLI, [])
    once = copy.deepcopy(s)
    app_mod._calkanti_yayim_kurali(s, b)
    y = b['yayim']
    assert y['neden_kodu'] is None
    assert y['gecerlilik'] == app_mod.CALKANTI_YAYIM_GECERLI
    assert y['t_gecersiz_bas_s'] is None
    assert y['yayimlanmayan_alanlar'] == []
    assert y['referans_kosu']['etiket_kodu'] == app_mod.CALKANTI_RIJIT_KARSILASTIRMA
    assert s == once


def test_baska_hukumde_pencere_listesi_kurali_tetiklemez():
    # pencere listesi dolu ama genel hüküm çalkantı kaynaklı değil (ör. yanma
    # içi rijit gövde kararsızlığı): bu kural uygulanmaz
    s, b = _ozet(), _blok('YANMA_ICI_RIJIT_GOVDE_KARARSIZ',
                          [{'t1': 1.0, 't2': 2.0, 'mod': 'govde'}])
    app_mod._calkanti_yayim_kurali(s, b)
    assert b['yayim']['neden_kodu'] is None
    assert s['apogee'] == 5153.7


@pytest.mark.parametrize('bozuk_t1', [float('nan'), float('inf'), None, True, 'x'])
def test_pencere_basi_bilinmiyorsa_sinir_null_fail_closed(bozuk_t1):
    # sınır bilinmiyorsa alan None: istemciler koşunun tamamını geçerlilik
    # dışı sayar (ONARIM2_ORTAK istemci kuralı 2)
    s = _ozet()
    b = _blok(k2.HUKUM_CALKANTI_KARARSIZ,
              [{'t1': bozuk_t1, 't2': 9.0, 'mod': 'calkanti', 'tank_id': 'n2o'}])
    app_mod._calkanti_yayim_kurali(s, b)
    y = b['yayim']
    assert y['neden_kodu'] == 'BAGLASIK_KOSU_KARARSIZ_PENCERE'
    assert y['t_gecersiz_bas_s'] is None
    assert s['apogee'] is None


def test_iki_neden_tek_demette():
    assert app_mod.CALKANTI_YAYIM_NEDENLERI == (
        'BAGLASIK_KOSU_DOGRUSAL_SINIRI_ASTI', 'BAGLASIK_KOSU_KARARSIZ_PENCERE')
