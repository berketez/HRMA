"""V301/UÇUŞ C-1 — Fırlatma Sahası kayıtlı projeden SAYFANIN motorunu uçurur.

Berke'nin "kesin düzeltilecek" maddesi (26 Eki): Fırlatma Sahası "kayıtlı
proje" kaynağı motoru ``hrma/analysis/flight_vehicle._recompute_*`` ile
KENDİSİ kuruyordu (modül yedekleri: ``chamber_diameter 100``, ``thrust
10000`` …; sayfa ucunun ~10 argümanı eksik). ÖLÇÜLDÜ
(``docs/scofield/raw/OH/V301/ucus/c1_once.json``, taban 688bc30b2):

    örnek       alan                 son hesap (uç)   kayıtlı proje
    katı        engine_inert_mass    3,08984 kg       4,55362 kg
    katı        engine_od_m          0,08300 m        0,10480 m
    hibrit      propellant_mass      14,54060 kg      12,94567 kg
    hibrit      engine_inert_mass    11,19531 kg      9,64180 kg
    hibrit      engine_od_m          0,093797 m       0,089431 m
    hibrit      engine_length_m      1,16019 m        1,09871 m

Onarım: recompute sayfanın hesap ucunun GÖVDESİNİ koşar
(``flight_vehicle.run_page_calculation``; ``app.test_request_context`` +
görünüm işlevi) ve yükü ürünün tek eşlemesi kurar (``page_payload``; eskiden
``tests/test_example_projects.calculate_payload``). Bu dosya:

  * üç örnek projede kaynak=kayıtlı proje aracı ⟷ kaynak=son hesap aracı
    BİT-AYNI (itki, yanma süresi, itici, atıl kütle, dış çap, boy, itki
    eğrisi ve künyeler) — ``==``, tolerans YOK;
  * ucun adlı reddi recompute'tan ve ``/api/flight-vehicle``dan AYNEN
    geçer (eksik zorunlu girdi → 422 ``incomplete_input``, alan adlarıyla);
  * ``calculate_payload`` adı içe aktarılabilir kalır ve ürün eşlemesinin
    kendisidir (KABUL kulvarı + örnek üretici bu adı kullanıyor).

Ters mutasyon (kanıt dizini ``mutasyon.md``): eski ``_recompute_solid``
geri konunca katı düğümü KIRMIZI (4,5536 ⟷ 3,0898 kg).
"""

import pytest

from hrma.analysis import flight_vehicle as fv
from tests.test_example_projects import (
    ENDPOINTS, EXAMPLES_DIR, HEADERS, NAMES, calculate_payload,
    load_example_doc)

#: Bekçinin karşılaştırdığı araç alanları (UCUS.md C-1: kuru kütle, itici
#: kütlesi, dış çap, boy, itki eğrisi, yanma süresi) + itki ve iki künye.
KARSILASTIRILAN_ARAC_ALANLARI = (
    'thrust', 'burn_time', 'propellant_mass', 'engine_inert_mass',
    'engine_od_m', 'engine_length_m', 'thrust_curve',
    'engine_inert_mass_is_estimate', 'engine_inert_mass_note',
    'engine_od_unit_source', 'motor_type')


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    return app.test_client()


@pytest.fixture()
def ornek_deposu(monkeypatch):
    """Proje deposu examples/ dizini (salt okunur kullanım)."""
    monkeypatch.setenv('HRMA_PROJECTS_DIR', str(EXAMPLES_DIR))


_SON_HESAP = {}


def _son_hesap_araci(client, motor_type):
    """Motor sayfasının son hesabı -> FlightHandoff'un yayımladığı araç.

    Sayfa hesap ucunun yanıtını ``/api/flight-vehicle`` source='results''a
    verir (flight_handoff.js publish); burada aynı iki adım koşulur.
    """
    if motor_type not in _SON_HESAP:
        alanlar = load_example_doc(motor_type)['inputs']['fields']
        r = client.post(ENDPOINTS[motor_type],
                        json=calculate_payload(motor_type, alanlar),
                        headers=HEADERS)
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        v = client.post('/api/flight-vehicle', headers=HEADERS, json={
            'source': 'results', 'motor_type': motor_type,
            'results': r.get_json()})
        assert v.status_code == 200, v.get_data(as_text=True)[:300]
        _SON_HESAP[motor_type] = v.get_json()['vehicle']
    return _SON_HESAP[motor_type]


@pytest.mark.parametrize('motor_type', sorted(NAMES))
def test_kayitli_proje_araci_son_hesapla_bit_ayni(client, ornek_deposu,
                                                   motor_type):
    """Kayıtlı proje kaynağı, sayfanın son hesabıyla AYNI aracı uçurur."""
    r = client.post('/api/flight-vehicle', headers=HEADERS, json={
        'source': 'project', 'name': NAMES[motor_type]})
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    proje = r.get_json()['vehicle']
    son = _son_hesap_araci(client, motor_type)
    ayrisan = [f'{k}: proje {proje.get(k)!r} ⟷ son hesap {son.get(k)!r}'
               for k in KARSILASTIRILAN_ARAC_ALANLARI
               if proje.get(k) != son.get(k)]
    assert not ayrisan, (
        f'{motor_type}: Fırlatma Sahası kayıtlı projeden motor sayfasının '
        'hesapladığından FARKLI bir araç uçuruyor:\n  ' + '\n  '.join(ayrisan))
    assert proje['source'] == 'project'
    assert proje['motor_name'] == NAMES[motor_type]


@pytest.mark.parametrize('motor_type', sorted(NAMES))
def test_recompute_sayfa_ucunun_yanit_govdesidir(motor_type):
    """recompute sonucu = aynı yükle sayfa ucunun yanıt gövdesi (bit-aynı)."""
    doc = load_example_doc(motor_type)
    mt, sonuc = fv.recompute_from_project(doc)
    assert mt == motor_type
    durum, govde = fv.run_page_calculation(
        motor_type, calculate_payload(motor_type, doc['inputs']['fields']))
    assert durum == 200
    assert sonuc == govde


def test_calculate_payload_urun_eslemesinin_kendisidir():
    """Test adı yeniden dışa aktarımdır; ikinci bir eşleme YAZILMAZ."""
    assert calculate_payload is fv.page_payload
    assert ENDPOINTS is fv.CALCULATION_ENDPOINTS


def test_hibrit_eslemesi_sayfa_toplayicisinin_istisnalarini_tasir():
    yuk = fv.page_payload('hybrid', {'single_pressure': 1.013,
                                     'thrust': 3000.0, 'burn_time': 10.0})
    assert 'single_pressure' not in yuk
    assert yuk['atmospheric_pressure'] == 1.013
    assert yuk['total_impulse'] == 30000.0
    assert yuk['contraction_ratio'] == 0
    assert yuk['mass_flux_chamber'] == 0
    assert yuk['calculate_trajectory'] is False


@pytest.mark.parametrize('itki, sure', [('', 10.0), (3000.0, ''),
                                        (True, 10.0), ('3000', 10.0)])
def test_hibrit_bos_ya_da_sayi_olmayan_alanin_carpimi_uydurulmaz(itki, sure):
    """Kayıtlı projede boş alan '' olarak durur (proje şeridi): sayfa
    toplam impulsu yalnız İKİ alan da sayıyken gönderir. Eski test eşlemesi
    ``'' * 10.0`` ile TypeError → 500 üretirdi."""
    yuk = fv.page_payload('hybrid', {'thrust': itki, 'burn_time': sure})
    assert 'total_impulse' not in yuk


def test_kati_ve_sivi_alanlari_birebir_gecer():
    alanlar = {'grain_type': 'bates', 'core_diameter': 32.0, 'x': ''}
    for mt in ('solid', 'liquid'):
        yuk = fv.page_payload(mt, alanlar)
        assert yuk == alanlar and yuk is not alanlar


# ---------------------------------------------------------------------------
# Ucun adlı reddi AYNEN taşınır (recompute sayı uydurmaz)
# ---------------------------------------------------------------------------

def _kaydet(motor_type, alanlar, ad):
    from hrma.utils import projects
    projects.save_project(ad, {
        'format': 'hrma-project', 'format_version': 1,
        'motor_type': motor_type, 'inputs': {'fields': dict(alanlar)}})
    return ad


@pytest.fixture()
def gecici_depo(tmp_path, monkeypatch):
    monkeypatch.setenv('HRMA_PROJECTS_DIR', str(tmp_path / 'projeler'))
    return tmp_path


@pytest.mark.parametrize('motor_type, beklenen', [
    ('solid', {'chamber_pressure', 'propellant_type', 'chamber_diameter',
               'grain_length', 'core_diameter'}),
    ('liquid', {'thrust', 'chamber_pressure', 'mixture_ratio', 'fuel_type',
                'oxidizer_type'}),
])
def test_eksik_proje_ucun_adli_reddini_alir(client, gecici_depo, motor_type,
                                            beklenen):
    ad = _kaydet(motor_type, {'motor_name': 'bos'}, 'UCUS-C1-bos-' + motor_type)
    r = client.post('/api/flight-vehicle', headers=HEADERS,
                    json={'source': 'project', 'name': ad})
    assert r.status_code == 422, r.get_data(as_text=True)[:400]
    govde = r.get_json()
    assert govde['status'] == 'incomplete_input'
    assert set(govde['missing_fields']) == beklenen
    assert govde['source'] == 'project'
    assert govde['project'] == ad
    assert govde['calculation_endpoint'] == ENDPOINTS[motor_type]
    assert 'vehicle' not in govde


def test_gecersiz_kati_geometri_ucun_kendi_422_si(client, gecici_depo):
    """Boğulan port: ``/calculate_solid`` ne diyorsa uçuş ucu da onu der."""
    alanlar = {'grain_type': 'bates', 'propellant_type': 'apcp',
               'chamber_diameter': 100, 'grain_length': 500,
               'core_diameter': 30, 'chamber_pressure': 40,
               'burn_rate_a': 0.005, 'burn_rate_n': 0.35}
    uc = client.post('/calculate_solid', json=alanlar, headers=HEADERS)
    assert uc.status_code == 422
    ad = _kaydet('solid', alanlar, 'UCUS-C1-bogulan')
    r = client.post('/api/flight-vehicle', headers=HEADERS,
                    json={'source': 'project', 'name': ad})
    assert r.status_code == 422
    govde, uc_govde = r.get_json(), uc.get_json()
    assert govde.get('error') == uc_govde.get('error')
    assert govde.get('invalid_fields') == uc_govde.get('invalid_fields')


def test_red_valueerror_alt_sinifidir():
    """Eski çağıranların fail-closed dalı (``except (ValueError, KeyError)``)."""
    assert issubclass(fv.ProjectCalculationRejected, ValueError)
    with pytest.raises(ValueError):
        fv.recompute_from_project({'motor_type': 'solid',
                                   'inputs': {'fields': {}}})


def test_modul_yedekleri_ve_kendi_kurulumu_sokuldu():
    """Motoru kendisi kuran eski kollar ürün yüzeyinde YOK (tek yol: uç)."""
    for ad in ('_recompute_hybrid', '_recompute_solid', '_recompute_liquid',
               '_f', '_declare_substitutions'):
        assert not hasattr(fv, ad), ad
