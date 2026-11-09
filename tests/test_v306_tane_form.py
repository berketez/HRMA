"""V306/TANE C1-K1..K5 — katı form alanlarının dürüstlüğü.

Kaynak: docs/scofield/raw/OH/V305/ci/C1/RAPOR.md (K1-K5) ve ORTAK kurallar
("her girdinin yanında açıklama": ne olduğu + birim, hesaba etkisi, boş
bırakılırsa ne olduğu, koddaki kabul aralığı; API alan adı ve kaynaksız
'tipik değer' yazılmaz).

* K1 — boğaz / çıkış çapı (ve genişleme oranı) çözücünün çıktısıdır: kutu
  salt okunur, hesap öncesi uydurma sayı (15 / 35 mm, 5,44) basılmaz, ipucu
  bunu dürüstçe söyler.
* K2 — ateşleme gecikmesi ve yıldız fileto hiçbir hesaba girmez: kutular
  proje dosyalarıyla geriye uyum için durur, ipucu "hesaba girmez" der.
  (V306/KATI-KALAN kalem 5: yıldız fileto kutusu kalktı; eski projedeki
  anahtar göçte adıyla yok sayılır.)
* K3 — test standı alanları: ipucu ve grup başlığı motor hesabına
  girmediklerini söyler.
* K4 — aviyonik kütlesi araç kalemidir: beyan kategorisi
  'vehicle_item_not_motor' (yapısal çıktı değil).
* K5 — örnek katı (Ø75 / 32) yüklüyken finocyl / slotted seçilince geometriye
  bağlı kutular boşaltılır; boş kutuda çözücü varsayılanını geometrik sınıra
  indirip beyan eder (adlı 422 yerine geçerli tasarım).
"""
import contextlib
import io
import json
import pathlib
import re

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
SOLID = KOK / 'hrma' / 'templates' / 'solid.html'
I18N = KOK / 'hrma' / 'static' / 'js' / 'i18n_pages.js'
ORNEK = KOK / 'examples' / 'Example Solid KNDX BATES 75mm.hrma'

#: Bu kalemlerde değişen ipucu anahtarları (solid.ui.*).
IPUCLARI = {
    'K1': ('nozzle_throat_diameter_critical_parameter_that',
           'nozzle_exit_diameter_larger_exit_provides',
           'ratio_of_exit_area_to_throat'),
    # V306/KATI-KALAN (kalem 5): yıldız fileto kutusu (star_fillet) ve
    # ipucu KALKTI (hesaba girmeyen girdi formda durmaz); eski proje
    # dosyasındaki anahtarı göç adıyla yok sayar. Bekçi:
    # tests/test_v306_kati_kalan.py::TestK5StarFillet.
    'K2': ('delay_time_from_ignition_signal_to',),
    'K3': ('maximum_pressure_measurement_range_of_pressure',
           'data_acquisition_sampling_rate_higher_rates',
           'maximum_thrust_measurement_capacity_of_load',
           'sensor_calibration_coefficient_to_convert_raw',
           'total_recording_duration_including_pre_ignition',
           'low_pass_filter_cutoff_frequency_for',
           'overall_measurement_uncertainty_for_monte_carlo'),
    'K4': ('mass_of_electronic_systems_including_flight',),
    'K5': ('thickness_of_each_fin_slot_affects',
           'radial_length_of_fin_slots_from',
           'slot_width_tooltip', 'slot_depth_tooltip'),
}


def _src(p):
    return p.read_text(encoding='utf-8')


def _i18n_iki(anahtar):
    """(EN, TR) metni — anahtar EN ve TR bloklarında birer kez."""
    s = _src(I18N)
    bul = re.findall(r"'" + re.escape(anahtar) + r"': '((?:[^'\\]|\\.)*)'", s)
    assert len(bul) == 2, (anahtar, len(bul))
    return bul[0], bul[1]


def _sayfa_ipucu(anahtar):
    m = re.findall(r'data-i18n="' + re.escape(anahtar) + r'">(.*?)</span>',
                   _src(SOLID), re.S)
    assert len(m) == 1, (anahtar, len(m))
    return m[0]


def _input(fid):
    m = re.findall(r'<input type="number" id="' + fid + r'" [^>]*>', _src(SOLID))
    assert len(m) == 1, fid
    return m[0]


TUM_ANAHTARLAR = [a for liste in IPUCLARI.values() for a in liste]


@pytest.mark.parametrize('k', TUM_ANAHTARLAR)
def test_ipucu_api_adi_ve_kaynaksiz_tipik_deger_tasimaz(k):
    """ORTAK: ipucunda API alan/kategori adı ve kaynaksız 'tipik' yok."""
    en, tr = _i18n_iki('solid.ui.' + k)
    sayfa = _sayfa_ipucu('solid.ui.' + k)
    for metin in (en, tr, sayfa):
        assert 'unwired_inputs' not in metin, metin
        for ham in ('computed_by_solver', 'test_bench_only', 'informational"',
                    'geometry_not_modelled', '/api/'):
            assert ham not in metin, (ham, metin)
        assert not re.search(r'\btypical', metin, re.I), metin
        assert not re.search(r'\btipik', metin, re.I), metin
    # Sayfadaki İngilizce yedek, sözlüğün EN metniyle aynıdır.
    assert sayfa.replace('&amp;', '&') == en.replace("\\'", "'")


@pytest.mark.parametrize('k', TUM_ANAHTARLAR)
def test_ipucu_bos_ve_aralik_soyler(k):
    """Her ipucu boş bırakılınca ne olduğunu ya da kutunun salt okunur
    olduğunu söyler; girdi alanlarında kabul aralığı yazılıdır."""
    en, tr = _i18n_iki('solid.ui.' + k)
    if k in IPUCLARI['K1']:
        assert 'read-only' in en and 'salt okunur' in tr
        return
    assert 'Blank' in en and 'Boş' in tr
    assert ('accepts' in en or 'Accepted' in en)
    assert 'kabul' in tr.lower()


@pytest.mark.parametrize('k', IPUCLARI['K2'] + IPUCLARI['K3'])
def test_k2_k3_hesaba_girmedigini_soyler(k):
    en, tr = _i18n_iki('solid.ui.' + k)
    assert 'no calculation reads it' in en or 'no motor calculation reads it' in en
    assert 'hiçbir hesap okumaz' in tr or 'hiçbir motor hesabı okumaz' in tr


def test_k3_grup_basligi_test_standi_planlamasi():
    en, tr = _i18n_iki('solid.ui.8_measurement_test_equipment')
    assert 'Test Stand Planning' in en and 'not used in the motor calculation' in en
    assert 'Test Standı Planlaması' in tr and 'motor hesabına girmez' in tr
    assert ('data-i18n="solid.ui.8_measurement_test_equipment">' + en + '</h2>'
            in _src(SOLID))


@pytest.mark.parametrize('fid', ['throat_diameter', 'exit_diameter',
                                 'expansion_ratio'])
def test_k1_cikti_kutusu_salt_okunur_ve_bos_baslar(fid):
    etiket = _input(fid)
    assert ' readonly' in etiket
    assert 'value=""' in etiket, (
        'hesap öncesi kutuda uydurma sayı basılıyor: ' + etiket)


def test_k1_genisleme_orani_yedek_cap_uydurmaz():
    s = _src(SOLID)
    i = s.index('function updateExpansionRatio()')
    govde = s[i:s.index('\n        }\n', i)]
    assert '|| 15' not in govde and '|| 35' not in govde


def test_k1_k2_k3_cozucu_beyani_degismedi():
    """Kategoriler aynı (çözücü hâlâ okumuyor): ipucu beyanla tutarlı."""
    from hrma.engines.solid_rocket_engine import SolidRocketEngine
    e = SolidRocketEngine(grain_type='bates', propellant_type='apcp',
                          chamber_diameter=100.0, core_diameter=30.0,
                          chamber_pressure=40.0)
    u = e.unwired_inputs()
    assert {'throat_diameter', 'exit_diameter', 'expansion_ratio'} <= set(
        u['computed_by_solver'])
    assert 'ignition_delay' in u['informational']
    assert u['geometry_not_modelled'] == ['star_fillet']
    assert {'calibration_factor', 'data_collection_time', 'filter_cutoff',
            'load_cell_capacity', 'pressure_sensor_range',
            'sampling_freq'} <= set(u['test_bench_only'])


def test_k4_aviyonik_arac_kalemi_kategorisi():
    from hrma.engines.solid_rocket_engine import SolidRocketEngine
    e = SolidRocketEngine(grain_type='bates', propellant_type='apcp',
                          chamber_diameter=100.0, core_diameter=30.0,
                          chamber_pressure=40.0)
    u = e.unwired_inputs()
    assert u['vehicle_item_not_motor'] == ['avionics_mass']
    assert 'avionics_mass' not in u['structural_output']
    hepsi = [f for liste in u.values() for f in liste]
    assert hepsi.count('avionics_mass') == 1
    # Sayfa kategoriyi adıyla tanır (makine adına düşmez) ve EN + TR metni var.
    assert re.search(r'\bvehicle_item_not_motor:\s*function', _src(SOLID))
    en, tr = _i18n_iki('solid.msg.unwired_vehicle_item_not_motor')
    assert 'not part of the motor' in en and 'motorun parçası değil' in tr
    en, tr = _i18n_iki('solid.ui.mass_of_electronic_systems_including_flight')
    assert 'not added to the motor dry mass' in en
    assert 'motor kuru kütlesine eklenmez' in tr


def test_k5_kural_tek_yerde_sayfa_sinir_hesaplamaz():
    s = _src(SOLID)
    i = s.index('const GEOMETRIYE_BAGLI_KUTULAR')
    blok = s[i:i + 3400]
    assert "finocyl: ['fin_width', 'fin_length']" in blok
    assert "slotted: ['slot_width', 'slot_depth']" in blok
    # Yalnız GERÇEK kullanıcı olayı (proje geri yüklemesi değil)
    assert blok.count('e.isTrusted') == 2
    assert "el.dataset.userTyped !== 'true'" in blok
    # Yeni proje yüklenince önceki oturumun "elle yazıldı" imleri silinir
    assert "'hrma:project-applied'" in blok
    assert 'delete el.dataset.userTyped' in blok
    # Sayfa geometrik sınırı yeniden yazmaz (0,85 çarpanı motorda)
    assert '0.85' not in blok


def _kati(govde):
    from hrma.app import app
    app.config['TESTING'] = True
    with contextlib.redirect_stdout(io.StringIO()):
        r = app.test_client().post('/calculate_solid', json=govde)
    return r.status_code, r.get_json()


@pytest.mark.parametrize('tip,alan', [('finocyl', 'fin_length'),
                                      ('slotted', 'slot_depth')])
def test_k5_ornek_once_422_bos_kutuda_gecerli_ve_beyanli(tip, alan):
    """ÖLÇÜLDÜ (k5_once.json): örnekte dosyadaki 20 mm sınırın (18,275 mm)
    üstünde → adlı 422. Kutu boşaltılınca çözücü varsayılanını sınıra
    indirir ve hem varsayılan hem kırpma olarak beyan eder."""
    f = dict(json.loads(ORNEK.read_text(encoding='utf-8'))['inputs']['fields'])
    f['grain_type'] = tip
    kod, j = _kati(dict(f))
    assert kod == 422
    assert [x['field'] for x in j['invalid_fields']] == [alan]
    assert j['invalid_fields'][0]['accepted_range'] == [1.0, 18.275]
    for k in ({'finocyl': ('fin_width', 'fin_length'),
               'slotted': ('slot_width', 'slot_depth')}[tip]):
        f[k] = ''
    kod, j = _kati(f)
    assert kod == 200, j
    gd = j['grain_design']
    assert alan in gd['assumed_defaults'] and alan in gd['clipped_inputs']
    derinlik = gd['fin_depth_mm' if tip == 'finocyl' else 'slot_depth_mm']
    assert derinlik == pytest.approx(18.275, abs=1e-9)


def test_k5_varsayilan_sinirli_rozeti_yaniltmaz():
    """Değer verilmeyen alan için 'girdiğiniz değer kullanılmadı' denmez."""
    s = _src(SOLID)
    i = s.index('var kirpilan = gd.clipped_inputs;')
    blok = s[i:i + 2600]
    assert 'if (varsayilanListe.indexOf(id) !== -1) return;' in blok
    assert "T('solid.msg.assumed_default_limited'" in blok
    en, tr = _i18n_iki('solid.msg.assumed_default_limited')
    assert 'limited to the geometric maximum' in en
    assert 'geometrik üst sınırına' in tr
