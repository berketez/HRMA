"""Faz 4B / bulgu A12 — OpenRocket dışa aktarımı eksik veriyi dosyaya çevirmez.

Ölçüm (2 Ağustos 2026, HEAD a7ff1e7), düzeltmeden önce:

  (a) ``OpenRocketExporter().export_motor_file({})`` geçerli bir .eng dosyası
      üretiyordu ve motor satırı şuydu —

          M0-UZAYTEK-HRM-001 0.0 500.0 P 1.000 1.000 UZAYTEK

      yani ÇAPI SIFIR, boyu yer tutucu 500 mm, itici kütlesi imza varsayılanı
      1,000 kg, sınıf harfi 10000 N·s varsayılanından gelen "M" olan bir motor.
      İtki eğrisi de uyduruktu: ``0.010 1000.0`` / ``10.000 1000.0``. OpenRocket
      bu dosyayı sorunsuz yükler; kullanıcı gerçek bir motor sanır.

  (b) ``create_flight_simulation_data`` çağıran araç vermediğinde sessizce
      5 kg / 0,10 m / 1,5 m'lik bir araç kurup ondan ``estimated_apogee``
      üretiyordu; çıktıda bunun bir varsayım olduğunu söyleyen HİÇBİR alan
      yoktu. Oysa çağıran (app.py::_resolve_vehicle_spec) her alanın kaynağını
      ``rocket_params['sources']`` içinde ZATEN yazıyordu — dışa aktarıcı o
      sözlüğü okumuyordu.

  (c) Aynı iki kusur .ork proje şablonunda da vardı: boş sözlükten
      ``<motor>M0-UZAYTEK-HRM-001</motor>`` ve 0,5 m x Ø0,1 m'lik bir motor
      yuvası olan geçerli bir proje çıkıyordu.

Sözleşme (fail-closed):
  * Kritik alanlar (kasa çapı, kamara boyu, itici kütlesi, toplam impuls, itki
    eğrisi) GERÇEK sonuçtan çözülemiyorsa .eng / .ork ÜRETİLMEZ, açık hata
    döner. Yer tutucu sayı yazılmaz.
  * "Çözülemiyor" ile "üst seviyede o adla yok" aynı şey değildir: aynı sayı
    motor tipine göre farklı anahtarda yayımlanıyor (katı ``propellant_mass``,
    sıvı ``total_mass_flow`` x ``burn_time``). Önce gerçek değer aranır.
  * Araç kullanıcıdan gelmiyorsa apoje ÜRETİLMEZ; her hâlükârda
    ``rocket_parameters_source`` yazılır ve dışa aktarıcının örnek aracı
    "exporter_example" diye etiketlenir.
"""

import io
import contextlib
import math

import pytest

from hrma.export.openrocket_integration import (
    ENG_REQUIRED_FIELDS,
    EXPORTER_EXAMPLE_VEHICLE,
    OpenRocketExportDataError,
    OpenRocketExporter,
)


NAN = float('nan')
INF = float('inf')


def _silent(fn, *args, **kwargs):
    """Çözücülerin print gürültüsünü yutar."""
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


# Kritik alanların hepsi dolu, en yalın geçerli motor. Buradan tek tek alan
# çıkarılarak kapının her alanı ayrı ayrı koruduğu ölçülür.
TAM_MOTOR = {
    'motor_name': 'FAZ4B',
    'thrust': 1000.0,
    'burn_time': 5.0,
    'total_impulse': 5000.0,
    'isp': 210.0,
    'propellant_mass_total': 2.0,
    'chamber_diameter': 0.10,
    'chamber_length': 0.30,
    'throat_diameter': 0.02,
    'exit_diameter': 0.05,
}

# Gerçek bir araç (kullanıcıdan gelmiş gibi).
GERCEK_ARAC = {
    'dry_mass': 12.0,
    'diameter': 0.11,
    'length': 1.8,
    'drag_coefficient': 0.55,
}


@pytest.fixture()
def exporter():
    return OpenRocketExporter()


@pytest.fixture(scope='module')
def gercek_hibrit():
    """Çözücünün GERÇEK çıktısı — kapının fazla agresif olmadığının kanıtı."""
    from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
    result = _silent(lambda: HybridRocketEngine(
        thrust=2000, burn_time=10, of_ratio=6.0, chamber_pressure=20).calculate())
    result['motor_name'] = 'FAZ4B_REAL'
    return result


def _motor_satiri(eng_text):
    """.eng motor satırı (yorum olmayan ilk satır) alanlarına ayrılır."""
    for line in eng_text.splitlines():
        if line and not line.startswith(';'):
            return line.split()
    raise AssertionError('.eng dosyasında motor satırı yok')


# ---------------------------------------------------------------------------
# (a) .eng kapısı — eksik veri çalıştırılabilir dosyaya çevrilmez
# ---------------------------------------------------------------------------

class TestEngKapisi:

    def test_bos_motor_data_eng_uretmez(self, exporter):
        """Ölçülen kusur: boş sözlükten ``M0-... 0.0 500.0 P 1.000 1.000``."""
        with pytest.raises(OpenRocketExportDataError) as hata:
            exporter.export_motor_file({})
        eksik = set(hata.value.missing_fields)
        # Sözleşme listesi modülde tek yerde tanımlı; buradan makinece denetlenir
        # ki listeden sessizce alan düşürülmesin.
        assert eksik == set(ENG_REQUIRED_FIELDS), eksik
        assert set(ENG_REQUIRED_FIELDS) == {
            'case_diameter', 'chamber_length', 'propellant_mass',
            'total_impulse', 'thrust_curve'}

    def test_none_ve_bos_liste_de_kabul_edilmez(self, exporter):
        for kotu in (None, [], 'motor', 0):
            with pytest.raises(OpenRocketExportDataError):
                exporter.export_motor_file(kotu)

    def test_export_eng_file_alias_ayni_kapidan_gecer(self, exporter):
        """Takma ad kapıyı atlatan ikinci bir yol OLMAMALI."""
        with pytest.raises(OpenRocketExportDataError):
            exporter.export_eng_file({})

    def test_dosyaya_yazma_yolu_da_kapali(self, exporter, tmp_path):
        hedef = tmp_path / 'sahte.eng'
        with pytest.raises(OpenRocketExportDataError):
            exporter.export_motor_file({}, str(hedef))
        assert not hedef.exists(), 'reddedilen motor için dosya yaratılmış'

    @pytest.mark.parametrize('cikarilan,beklenen', [
        (('chamber_diameter', 'exit_diameter', 'throat_diameter'), 'case_diameter'),
        (('chamber_length',), 'chamber_length'),
        (('propellant_mass_total',), 'propellant_mass'),
    ])
    def test_tek_kritik_alan_eksikse_kapi_kapanir(self, exporter, cikarilan,
                                                  beklenen):
        data = {k: v for k, v in TAM_MOTOR.items() if k not in cikarilan}
        with pytest.raises(OpenRocketExportDataError) as hata:
            exporter.export_motor_file(data)
        assert beklenen in hata.value.missing_fields

    def test_itki_verisi_yoksa_kapi_kapanir(self, exporter):
        """İtki de yanma süresi de yoksa eğri UYDURULMAZ (eski: 1000 N x 10 s)."""
        data = {k: v for k, v in TAM_MOTOR.items()
                if k not in ('thrust', 'burn_time', 'total_impulse')}
        with pytest.raises(OpenRocketExportDataError) as hata:
            exporter.export_motor_file(data)
        assert 'thrust_curve' in hata.value.missing_fields
        assert 'total_impulse' in hata.value.missing_fields

    @pytest.mark.parametrize('deger', [0.0, -1.0, NAN, INF, None, 'iki kilo'])
    def test_gecersiz_itici_kutlesi_1_kg_ile_doldurulmaz(self, exporter, deger):
        """Eski imza varsayılanı 1,000 kg idi; 0/NaN/negatif onunla örtülüyordu."""
        data = dict(TAM_MOTOR, propellant_mass_total=deger)
        with pytest.raises(OpenRocketExportDataError) as hata:
            exporter.export_motor_file(data)
        assert 'propellant_mass' in hata.value.missing_fields

    @pytest.mark.parametrize('deger', [0.0, -0.02, NAN, INF])
    def test_gecersiz_geometri_yer_tutucuya_dusmez(self, exporter, deger):
        data = dict(TAM_MOTOR, chamber_diameter=deger, exit_diameter=deger,
                    throat_diameter=deger)
        with pytest.raises(OpenRocketExportDataError) as hata:
            exporter.export_motor_file(data)
        assert 'case_diameter' in hata.value.missing_fields

    def test_hata_mesaji_eksik_alani_ve_gerekcesini_soyler(self, exporter):
        """Kullanıcı arayüzde bu metni görüyor (solid.html:4590 result.error)."""
        with pytest.raises(OpenRocketExportDataError) as hata:
            exporter.export_motor_file({})
        mesaj = str(hata.value)
        assert 'NOT generated' in mesaj
        for alan in ('case_diameter', 'propellant_mass', 'thrust_curve'):
            assert alan in mesaj
        assert hata.value.reasons, 'gerekçe sözlüğü boş'

    def test_hata_valueerror_alt_sinifi(self, exporter):
        """app.py uçları ``except Exception`` ile sarıyor; tip sözleşmesi."""
        assert issubclass(OpenRocketExportDataError, ValueError)
        with pytest.raises(ValueError):
            exporter.export_motor_file({})


# ---------------------------------------------------------------------------
# (b) "Çapı sıfır motor dosyası hiçbir yolla üretilemez"
# ---------------------------------------------------------------------------

class TestSifirCapliMotorUretilemez:

    def test_dogrudan_create_eng_file_cagrisi_da_reddedilir(self, exporter):
        """Son kapı: metot doğrudan çağrılsa bile sıfır çap yazılmaz."""
        with pytest.raises(OpenRocketExportDataError):
            exporter._create_eng_file(
                'M0-TEST', 0.0, 500.0, 1.0, 10000.0,
                [(0.0, 0.0), (0.01, 1000.0), (10.0, 1000.0), (10.01, 0.0)],
                dict(TAM_MOTOR))

    @pytest.mark.parametrize('capi,boyu,kutlesi', [
        (0.0, 300.0, 2.0),
        (-5.0, 300.0, 2.0),
        (NAN, 300.0, 2.0),
        (100.0, 0.0, 2.0),
        (100.0, 300.0, 0.0),
        (100.0, 300.0, NAN),
    ])
    def test_gecersiz_baslik_alani_yazilmaz(self, exporter, capi, boyu, kutlesi):
        with pytest.raises(OpenRocketExportDataError):
            exporter._create_eng_file(
                'X-TEST', capi, boyu, kutlesi, 5000.0,
                [(0.0, 0.0), (0.01, 1000.0), (5.0, 1000.0), (5.01, 0.0)],
                dict(TAM_MOTOR))

    def test_bos_itki_egrisi_ile_dosya_yazilmaz(self, exporter):
        with pytest.raises(OpenRocketExportDataError):
            exporter._create_eng_file('X-TEST', 100.0, 300.0, 2.0, 5000.0, [],
                                      dict(TAM_MOTOR))

    @pytest.mark.parametrize('yol', ['export_motor_file', 'export_eng_file'])
    def test_hicbir_genel_yol_bozuk_motor_satiri_uretmez(self, exporter, yol):
        """Üretilebilen her .eng dosyasının başlık alanları sonlu ve pozitif."""
        bozuk_girdiler = [
            {},
            {'motor_name': 'X'},
            dict(TAM_MOTOR, propellant_mass_total=0.0),
            dict(TAM_MOTOR, chamber_length=NAN),
        ]
        for girdi in bozuk_girdiler:
            with pytest.raises(OpenRocketExportDataError):
                getattr(exporter, yol)(girdi)

    def test_gecerli_motor_hala_uretilir_ve_alanlari_fiziksel(self, exporter):
        """Kapı fazla agresif OLMAMALI: gerçek veriyle dosya çıkmalı."""
        eng = exporter.export_motor_file(dict(TAM_MOTOR))
        alanlar = _motor_satiri(eng)
        assert len(alanlar) == 7, alanlar
        cap, boy = float(alanlar[1]), float(alanlar[2])
        itici, yuklu = float(alanlar[4]), float(alanlar[5])
        for deger in (cap, boy, itici, yuklu):
            assert math.isfinite(deger) and deger > 0.0
        assert cap == pytest.approx(100.0, rel=1e-6)   # kasa = kamara iç çapı
        assert boy == pytest.approx(300.0, rel=1e-6)
        assert itici == pytest.approx(2.0, rel=1e-9)

    def test_gercek_cozucu_ciktisi_kapiyi_gecer(self, exporter, gercek_hibrit):
        eng = exporter.export_motor_file(dict(gercek_hibrit))
        alanlar = _motor_satiri(eng)
        assert float(alanlar[1]) > 0.0 and float(alanlar[2]) > 0.0
        # .eng motor satırı kütleyi 3 ondalıkla yazar (RASP biçimi).
        assert float(alanlar[4]) == pytest.approx(
            gercek_hibrit['propellant_mass_total'], abs=1e-3)

    def test_designation_sinif_harfini_uydurmuyor(self, exporter):
        """``M0-...`` dizesinin "M"si 10000 N·s varsayılanından geliyordu."""
        assert exporter._designation({}) == 'UNKNOWN-UZAYTEK-HRM-001'
        assert not exporter._designation({}).startswith('M0')
        # Gerçek veriyle sınıf harfi yine üretilir
        assert exporter._designation(dict(TAM_MOTOR)).startswith('L')


# ---------------------------------------------------------------------------
# (c) Kritik alanlar GERÇEK anahtarlardan çözülür (kapı = kör ret değil)
# ---------------------------------------------------------------------------

class TestGercekAlanlardanCozum:

    def test_kati_motorun_itici_kutlesi_kendi_anahtarindan_okunur(self, exporter):
        """Ölçüm: /calculate_solid üst seviyede ``propellant_mass_total``
        yayımlamıyor; ``propellant_mass`` = 6,468 kg orada."""
        data = {k: v for k, v in TAM_MOTOR.items()
                if k != 'propellant_mass_total'}
        data['propellant_mass'] = 6.468146574659687
        mass, source = exporter.resolve_propellant_mass(data)
        assert mass == pytest.approx(6.468146574659687)
        assert source == 'propellant_mass'
        eng = exporter.export_motor_file(data)
        assert float(_motor_satiri(eng)[4]) == pytest.approx(6.468, abs=1e-3)

    def test_sivi_motorun_itici_kutlesi_debiden_turetilir(self, exporter):
        """Ölçüm: /calculate_liquid kütle yerine ``total_mass_flow`` = 3,418
        kg/s ve ``burn_time`` = 300 s yayımlıyor (sayfa da bunu çarpıyor)."""
        data = {k: v for k, v in TAM_MOTOR.items()
                if k != 'propellant_mass_total'}
        data['total_mass_flow'] = 3.4176143448385665
        mass, source = exporter.resolve_propellant_mass(data)
        assert source == 'mdot_x_burn_time'
        assert mass == pytest.approx(3.4176143448385665 * TAM_MOTOR['burn_time'])

    def test_itici_kutlesi_1_kg_varsayilanina_asla_dusmez(self, exporter):
        """Eski davranış: bulunamayınca 1,000 kg. Şimdi None + kapı."""
        mass, source = exporter.resolve_propellant_mass({'thrust': 100.0})
        assert mass is None and source == 'none'

    def test_toplam_impuls_gercek_egriden_turetilir(self, exporter):
        data = {k: v for k, v in TAM_MOTOR.items() if k != 'total_impulse'}
        data['thrust_curve'] = {'time': [0.0, 1.0, 2.0, 3.0],
                                'thrust': [1000.0, 1000.0, 1000.0, 1000.0]}
        impulse, source = exporter.resolve_total_impulse(data)
        assert source == 'curve_integral'
        assert impulse == pytest.approx(3000.0, rel=1e-9)

    def test_toplam_impuls_itki_x_sure_ile_turetilir(self, exporter):
        data = {k: v for k, v in TAM_MOTOR.items() if k != 'total_impulse'}
        impulse, source = exporter.resolve_total_impulse(data)
        assert source == 'thrust_x_burn_time'
        assert impulse == pytest.approx(1000.0 * 5.0)

    def test_toplam_impuls_10000_varsayilanina_asla_dusmez(self, exporter):
        assert exporter.resolve_total_impulse({}) == (None, 'none')

    def test_ortalama_itki_average_thrust_alanindan_okunur(self, exporter):
        """Ölçüm: katı çözücü ``thrust`` değil ``average_thrust`` yayımlıyor."""
        value, source = exporter.resolve_average_thrust(
            {'average_thrust': 6704.935576774943})
        assert source == 'average_thrust'
        assert value == pytest.approx(6704.935576774943)

    def test_itki_verisi_yoksa_egri_bos_doner(self, exporter):
        """Eski sabit-itki yedeği 1000 N x 10 s UYDURUYORDU."""
        points, source = exporter.resolve_thrust_curve({})
        assert points == []
        assert source == 'unavailable'

    def test_kaynak_beyani_eng_dosyasina_yazilir(self, exporter):
        eng = exporter.export_motor_file(dict(TAM_MOTOR))
        assert '; propellant mass:' in eng
        assert '; total impulse (' in eng

    def test_cozucunun_yanma_suresi_varsayimi_dosyaya_tasinir(self, exporter):
        """Sıvı çözücü ``burn_time_source`` = 'assumed 300 s burn' beyan ediyor;
        itici kütlesi ve toplam impuls bu süreden türeyebilir."""
        data = dict(TAM_MOTOR, burn_time_source='assumed 300 s burn')
        eng = exporter.export_motor_file(data)
        assert 'burn time basis (declared by the solver): assumed 300 s burn' in eng


# ---------------------------------------------------------------------------
# (d) .ork / simülasyon dosyası aynı kapıdan geçer
# ---------------------------------------------------------------------------

class TestOrkKapisi:

    def test_bos_motor_data_ork_uretmez(self, exporter):
        with pytest.raises(OpenRocketExportDataError) as hata:
            exporter.create_ork_project_template({})
        assert '.ork' in str(hata.value)

    def test_create_simulation_file_ayni_kapidan_gecer(self, exporter):
        with pytest.raises(OpenRocketExportDataError):
            exporter.create_simulation_file({})

    def test_gecerli_motorda_ork_hala_uretilir(self, exporter):
        xml = exporter.create_ork_project_template(dict(TAM_MOTOR))
        assert '<openrocket' in xml
        assert '<motor>M0-' not in xml, 'uydurma sınıf/çap geri geldi'
        # Motor yuvası gerçek geometriden: 0,30 m boy, Ø0,10 m kasa
        assert '<length>0.3</length>' in xml
        assert '<outerradius>0.05</outerradius>' in xml

    def test_arac_verilmeyince_ork_ornek_araci_beyan_eder(self, exporter):
        """XML bir sayı yazmak zorunda; ama bunun örnek olduğunu SÖYLEMELİ."""
        xml = exporter.create_ork_project_template(dict(TAM_MOTOR))
        assert 'EXAMPLE' in xml
        assert 'is NOT your rocket' in xml

    def test_gercek_arac_verilince_ornek_uyarisi_yok(self, exporter):
        xml = exporter.create_ork_project_template(
            dict(TAM_MOTOR), dict(GERCEK_ARAC, name='Kullanici Araci'))
        assert 'is NOT your rocket' not in xml
        assert '<name>Kullanici Araci</name>' in xml


# ---------------------------------------------------------------------------
# (e) A12/b — uydurma araçtan apoje üretilmez, kaynak her zaman beyan edilir
# ---------------------------------------------------------------------------

class TestAracKaynagiBeyani:

    def test_arac_verilmediginde_apoje_uretilmez(self, exporter):
        """Ölçülen kusur: 5 kg'lık uydurma araçtan ``estimated_apogee``."""
        data = exporter.create_flight_simulation_data(dict(TAM_MOTOR))
        assert data['flight_performance'] is None
        assert data['flight_performance_status'] == 'not_computed'
        assert 'dry_mass' in data['flight_performance_missing_fields']
        assert 'diameter' in data['flight_performance_missing_fields']
        assert 'NOT computed' in data['flight_performance_reason']

    def test_rocket_parameters_source_alani_her_zaman_var(self, exporter):
        """Bulgunun sözü: "çıktıda ``rocket_parameters_source`` alanı YOK"."""
        for arac in (None, dict(GERCEK_ARAC)):
            data = exporter.create_flight_simulation_data(dict(TAM_MOTOR), arac)
            assert 'rocket_parameters_source' in data
            assert 'rocket_parameters_source_labels' in data
            assert set(data['rocket_parameters_source']) >= {'dry_mass', 'diameter'}

    def test_ornek_arac_acikca_etiketlenir(self, exporter):
        data = exporter.create_flight_simulation_data(dict(TAM_MOTOR))
        assert data['rocket_parameters_are_exporter_example'] is True
        kaynaklar = data['rocket_parameters_source']
        assert kaynaklar['dry_mass'] == 'exporter_example'
        etiket = data['rocket_parameters_source_labels']['dry_mass']
        assert 'EXAMPLE' in etiket and 'NOT your rocket' in etiket
        # Örnek araç yine de görünür kalır (kullanıcı neyin yazıldığını görsün)
        assert data['rocket_parameters']['dry_mass'] == \
            EXPORTER_EXAMPLE_VEHICLE['dry_mass']

    def test_gercek_arac_verilince_apoje_hesaplanir(self, exporter):
        """Kapı fazla agresif OLMAMALI."""
        data = exporter.create_flight_simulation_data(
            dict(TAM_MOTOR), dict(GERCEK_ARAC))
        assert data['flight_performance_status'] == 'ok'
        assert data['rocket_parameters_are_exporter_example'] is False
        perf = data['flight_performance']
        assert perf['estimated_apogee'] > 0.0
        assert perf['vehicle_is_exporter_example'] is False
        assert perf['vehicle_parameters_source']['dry_mass'] == 'request'

    def test_caganin_kendi_kaynak_beyani_tasinir(self, exporter):
        """app.py::_resolve_vehicle_spec ``sources`` yazıyordu, kimse okumuyordu.

        Beyan ölçülmüş bir sayıya dayandığı için (motorun kendi atıl kütlesi)
        aynen taşınır ve apoje hesaplanır — ama sayının neye dayandığı çıktıda
        kalır.
        """
        arac = dict(GERCEK_ARAC, sources={
            'dry_mass': 'motor_inert_lower_bound:structural',
            'diameter': 'motor_case_lower_bound:chamber_plus_wall',
            'length': 'not_modelled',
            'drag_coefficient': 'not_supplied',
        })
        data = exporter.create_flight_simulation_data(dict(TAM_MOTOR), arac)
        kaynaklar = data['rocket_parameters_source']
        assert kaynaklar['dry_mass'] == 'motor_inert_lower_bound:structural'
        assert kaynaklar['diameter'] == 'motor_case_lower_bound:chamber_plus_wall'
        assert data['rocket_parameters_are_exporter_example'] is False
        assert data['flight_performance_status'] == 'ok'
        # Çözülemeyen etiket sessizce düşürülmez
        assert data['rocket_parameters_source_labels']['dry_mass'] == \
            'motor_inert_lower_bound:structural'

    def test_motor_alanlari_eksikse_de_apoje_uretilmez(self, exporter):
        """Isp/itki/kütle varsayılanlarından apoje türetilmesi de bitti."""
        motor = {k: v for k, v in TAM_MOTOR.items() if k != 'isp'}
        data = exporter.create_flight_simulation_data(motor, dict(GERCEK_ARAC))
        assert data['flight_performance'] is None
        assert 'isp' in data['flight_performance_missing_fields']

    def test_yanitin_hicbir_yerinde_uydurma_apoje_kalmadi(self, exporter,
                                                          gercek_hibrit):
        """Gerçek motor + araçsız istek: sayısal apoje iddiası OLMAMALI."""
        data = exporter.create_flight_simulation_data(dict(gercek_hibrit))
        assert data['flight_performance'] is None
        assert data['rocket_parameters_are_exporter_example'] is True


class TestUcusProfiliAracKaynagi:
    """``generate_flight_profile`` zaman-adımlı çözüm için örnek araç kullanır.

    Bu yolda sayı üretilmesine bilerek izin verilir (önizleme grafiği boş
    kalmasın), ama araç ÖRNEK olduğu üç ayrı yerde beyan edilir. Sözleşme:
    örnek araçtan gelen bir irtifa asla beyansız dönmez.
    """

    def test_ornek_arac_uc_yerde_birden_beyan_edilir(self, exporter):
        profile = exporter.generate_flight_profile(dict(TAM_MOTOR))
        assert profile['status'] == 'ok'
        assert profile['vehicle_is_exporter_example'] is True
        assert 'EXAMPLE VEHICLE' in profile['max_altitude_method']
        assert 'EXAMPLE VEHICLE' in \
            profile['performance_summary']['estimated_apogee_method']
        assert profile['rocket_parameters_source']['dry_mass'] == 'exporter_example'

    def test_gercek_arac_verilince_ornek_bayragi_duser(self, exporter):
        profile = exporter.generate_flight_profile(dict(TAM_MOTOR),
                                                   dict(GERCEK_ARAC))
        assert profile['vehicle_is_exporter_example'] is False
        assert 'EXAMPLE VEHICLE' not in profile['max_altitude_method']
        assert profile['max_altitude'] > 0.0

    def test_arac_capi_gercekten_kullanilir(self, exporter):
        """Beyan süs değil: çap sürüklemeye giriyor, apoje onu izlemeli."""
        ince = exporter.generate_flight_profile(
            dict(TAM_MOTOR), dict(GERCEK_ARAC, diameter=0.10))
        kalin = exporter.generate_flight_profile(
            dict(TAM_MOTOR), dict(GERCEK_ARAC, diameter=0.30))
        assert kalin['max_altitude'] < ince['max_altitude']

    def test_itki_verisi_yoksa_profil_kosmaz(self, exporter):
        """Eski kod 1000 N x 10 s uydurup ondan yörünge çiziyordu."""
        motor = {'propellant_mass_total': 2.0}
        profile = exporter.generate_flight_profile(motor)
        assert profile['status'] == 'insufficient_data'
        assert 'thrust_curve' in profile['missing_fields']
        assert profile['max_altitude'] is None


# ---------------------------------------------------------------------------
# (f) Uçtan uca: uç noktalar eksik veride dosya SUNMAZ
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


class TestUcNoktalariFailClosed:

    @pytest.mark.parametrize('yol', ['/api/export-eng', '/api/export-openrocket',
                                     '/api/export-simulation'])
    def test_bos_motor_data_ile_dosya_donmez(self, client, yol):
        response = _silent(client.post, yol, json={'motor_data': {}},
                           headers={'Host': '127.0.0.1:8080'})
        assert response.status_code != 200, \
            f'{yol}: eksik veriden HTTP 200 döndü'
        govde = response.get_data(as_text=True)
        assert 'M0-' not in govde, f'{yol}: yer tutucu motor satırı sızdı'
        assert 'NOT generated' in govde, f'{yol}: hata gerekçesi yok'

    def test_gecerli_motor_hala_eng_dondurur(self, client):
        """Uçlar fazla agresif OLMAMALI."""
        response = _silent(client.post, '/api/export-eng',
                           json={'motor_data': dict(TAM_MOTOR)},
                           headers={'Host': '127.0.0.1:8080'})
        assert response.status_code == 200, response.get_data(as_text=True)[:300]
        payload = response.get_json()
        assert payload['status'] == 'success'
        alanlar = _motor_satiri(payload['content'])
        assert float(alanlar[1]) > 0.0 and float(alanlar[4]) > 0.0
