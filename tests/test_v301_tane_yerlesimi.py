"""V301/S1-6 (28 Eki) — tane yerleşimi: gövdeye yapıştırılmış ⟷ kartuş yüklü.

Gerinim çözümü yalnız gövdeye yapıştırılmış taneyi biliyordu ve bunu kendisi
beyan ediyordu ("this solver has no input for that configuration"). Katı örnek
(KNDX BATES, 40 bar) bu varsayımla %2,209 port gerinimi ⟷ %2,0 kapasite
(SF 0,906) ve "tane gerinimi kapasiteyi aşıyor" uyarısı veriyordu; gerinimin
%1,833'ü kürleme büzülmesinin gövdeyle kısıtlanmasından geliyordu. KN-şeker
BATES segmentleri kalıpta dökülüp gövdeye takılır (NASA SP-8073 §1
cartridge-loaded). Bekçiler:

* varsayılan (alan yok) = açık 'case_bonded' = bugünkü sayılar (bit-aynı);
* kartuş yüklüde ısıl gerinim 0 ve port gerinimi doğrusal süperpozisyonla
  tam olarak basınç payıdır (toplam − ısıl);
* tanınmayan değer sessizce varsayılana düşmez: 422, kabul edilen değerlerle;
* sayfada alan, iki seçenek, "?" ipucu (EN + TR) ve gövdede alan var;
* dağıtılan katı örnek kartuş yüklüdür ve gerinim uyarısı vermez.
"""
import contextlib
import io
import json
import pathlib
import re

import pytest

from hrma.app import app
from hrma.engines.solid_rocket_engine import (GRAIN_SUPPORT_CARTRIDGE,
                                              GRAIN_SUPPORT_OPTIONS)
from tests.support.kabul_sayfa_yukleri import SAYFA_YUKLERI

KOK = pathlib.Path(__file__).resolve().parents[1]
GERINIM_UYARI_KODU = 'warn.solid.grain_strain_exceeds_capability'
ORNEK = KOK / 'examples' / 'Example Solid KNDX BATES 75mm.hrma'


def _hesapla(**ek):
    app.config['TESTING'] = True
    govde = dict(SAYFA_YUKLERI['solid'])
    govde.pop('grain_support', None)
    govde.update(ek)
    with contextlib.redirect_stdout(io.StringIO()):
        yanit = app.test_client().post('/calculate_solid', json=govde)
    return yanit.status_code, (yanit.get_json() or {})


def _tane(sonuc):
    return sonuc['structural_analysis']['grain_structural']


def _kodlar(sonuc):
    return [w.get('code') for w in (sonuc.get('warnings') or [])
            if isinstance(w, dict)]


@pytest.fixture(scope='module')
def uc_sonuc():
    return {
        'yok': _hesapla(),
        'case_bonded': _hesapla(grain_support='case_bonded'),
        'cartridge_loaded': _hesapla(grain_support='cartridge_loaded'),
    }


def test_varsayilan_govdeye_yapistirilmis_ve_beyanli(uc_sonuc):
    kod, sonuc = uc_sonuc['yok']
    assert kod == 200
    tane = _tane(sonuc)
    assert tane['grain_support'] == 'case_bonded'
    assert tane['grain_support_source'] == 'default (not supplied)'
    assert 'case-bonded grain' in tane['bonding_assumption']
    assert 'this solver has no input' not in tane['bonding_assumption']


def test_acik_case_bonded_varsayilanla_bit_ayni(uc_sonuc):
    _, yok = uc_sonuc['yok']
    _, acik = uc_sonuc['case_bonded']
    a, b = _tane(yok), _tane(acik)
    for alan in ('bore_strain_percent', 'strain_safety_factor',
                 'thermal_only_bore_strain_percent', 'max_grain_stress_mpa',
                 'crack_propagation_risk'):
        assert a[alan] == b[alan], alan
    assert _tane(acik)['grain_support_source'] == 'user input'


def test_kartus_yuklude_isil_gerinim_yok_basinc_payi_kalir(uc_sonuc):
    _, yapisik = uc_sonuc['case_bonded']
    kod, kartus = uc_sonuc['cartridge_loaded']
    assert kod == 200
    y, k = _tane(yapisik), _tane(kartus)
    assert k['grain_support'] == GRAIN_SUPPORT_CARTRIDGE
    assert k['thermal_only_bore_strain_percent'] == 0.0
    # Doğrusal elastisite: port gerinimi = basınç payı + ısıl pay. BATES'te
    # gerilme yığılması 1, yani kartuş gerinimi = toplam − ısıl (yapışık).
    assert y['stress_concentration_factor'] == 1.0
    beklenen = (y['bore_strain_percent']
                - y['thermal_only_bore_strain_percent'])
    assert k['bore_strain_percent'] == pytest.approx(beklenen, rel=1e-9)
    assert k['strain_safety_factor'] > y['strain_safety_factor']
    assert 'SP-8073' in k['bonding_assumption']


def test_yerlesim_balistigi_degistirmez(uc_sonuc):
    _, yapisik = uc_sonuc['case_bonded']
    _, kartus = uc_sonuc['cartridge_loaded']
    for alan in ('total_impulse', 'specific_impulse', 'burn_time',
                 'average_thrust', 'max_thrust'):
        if alan in yapisik:
            assert kartus[alan] == yapisik[alan], alan


def test_taninmayan_deger_422_kabul_edilenlerle():
    kod, sonuc = _hesapla(grain_support='glued')
    assert kod == 422
    alanlar = {f['field']: f for f in sonuc.get('invalid_fields') or []}
    assert 'grain_support' in alanlar
    assert alanlar['grain_support']['reason'] == 'unknown_option'
    for secenek in GRAIN_SUPPORT_OPTIONS:
        assert secenek in alanlar['grain_support']['message']


def test_sayfada_alan_secenekler_ipucu_ve_govde():
    sablon = (KOK / 'hrma' / 'templates' / 'solid.html').read_text(
        encoding='utf-8')
    blok = re.search(r'<select id="grain_support">(.*?)</select>', sablon,
                     re.S)
    assert blok, 'select#grain_support yok'
    degerler = re.findall(r'<option value="([^"]+)"', blok.group(1))
    assert tuple(degerler) == GRAIN_SUPPORT_OPTIONS
    etiket = re.search(r'<label for="grain_support">(.*?)</label>', sablon,
                       re.S)
    assert etiket and 'tooltip-text' in etiket.group(1)
    assert "grain_support: document.getElementById('grain_support').value" \
        in sablon
    i18n = (KOK / 'hrma' / 'static' / 'js' / 'i18n_pages.js').read_text(
        encoding='utf-8')
    for anahtar in ('solid.ui.grain_support', 'solid.ui.grain_support_help',
                    'solid.ui.grain_support_case_bonded',
                    'solid.ui.grain_support_cartridge_loaded'):
        # EN ve TR blokları: anahtar iki kez tanımlı
        assert i18n.count(f"'{anahtar}':") == 2, anahtar
    assert "'solid.ui.grain_support': 'Tane Yerleşimi'" in i18n


def test_dagitilan_kati_ornek_kartus_yuklu_ve_gerinim_uyarisi_yok():
    belge = json.loads(ORNEK.read_text(encoding='utf-8'))
    assert belge['inputs']['fields']['grain_support'] == 'cartridge_loaded'
    assert 'kartuş yüklü' in belge['description']
    assert SAYFA_YUKLERI['solid']['grain_support'] == 'cartridge_loaded'
    app.config['TESTING'] = True
    with contextlib.redirect_stdout(io.StringIO()):
        yanit = app.test_client().post('/calculate_solid',
                                       json=SAYFA_YUKLERI['solid'])
    assert yanit.status_code == 200
    sonuc = yanit.get_json()
    assert GERINIM_UYARI_KODU not in _kodlar(sonuc)
    assert _tane(sonuc)['strain_safety_factor'] >= 1.0
