"""P3 bekçisi: katı motor çıktısında sabitlenmiş kalan yaprakların testi.

v2.6.26 bağlama denetimi katı motorda 29 kalem + bir blok çıkardı. Kalıp her
seferinde aynıydı: kullanıcı bir girdiyi değiştiriyor, çıktıdaki o yaprak
kıpırdamıyordu.

  * Yakıt kimliği hiç gelmiyordu — sayfada ``propellant_type`` alanı yoktu,
    ``/calculate_solid`` her koşuda 'apcp' varsayıyordu. KNDX seçen kullanıcı
    HTPB elastomerin grain mekaniğini (E = 6 MPa, kopma uzaması %35) ve
    APCP'nin iki-fazlı kaybını görüyordu.
  * Nozul yarı açıları, itki katsayısı, yalıtım kalınlıkları, ateşleyici
    şarjı ve birleşim "güvenilirliği" elle yazılmış sayılardı.
  * ``outer_diameter`` alanı yok sayılıyor, grain dış çapı olarak
    ``chamber_diameter`` kullanılıyordu — iki alanın da etiketi yanlıştı.

Bu dosya o sabitlerin geri gelmesini engeller. Ölçüt tek: girdi değişince
fiziksel olarak bağlı çıktı DEĞİŞMEK zorundadır; hesaplanamayan alan sayı
değil ``NOT_MODELLED`` / ``not_sized`` / ``None`` döndürmelidir.
"""

import json
from pathlib import Path

import pytest

from hrma.engines.solid_rocket_engine import (
    SOLID_CONDENSED_MASS_FRACTION,
    SOLID_GRAIN_MECHANICS,
    SOLID_IGNITER,
    SolidRocketEngine,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / 'examples' / 'Example Solid KNDX BATES 75mm.hrma'

#: Yerel güven sınırı kapısı olmadan uç nokta 403 döner.
LOCAL_HOST = {'Host': '127.0.0.1:8080'}


@pytest.fixture(scope='module')
def base_payload():
    """Taban yük: uygulamanın kendi kaydetme yolundan geçmiş GERÇEK proje."""
    fields = json.loads(EXAMPLE.read_text(encoding='utf-8'))['inputs']['fields']
    return dict(fields)


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def run(client, base_payload, **degisim):
    payload = dict(base_payload)
    payload.update(degisim)
    resp = client.post('/calculate_solid', json=payload, headers=LOCAL_HOST)
    assert resp.status_code == 200, resp.get_data(as_text=True)[:400]
    body = resp.get_json()
    assert 'error' not in body, body.get('error')
    return body


def leaf(body, path):
    node = body
    for part in path.split('.'):
        assert isinstance(node, dict) and part in node, (
            f'{path} yolunda {part} yok')
        node = node[part]
    return node


# ---------------------------------------------------------------------------
# 1) Yakıt kimliği çözücüye ULAŞIYOR MU (kalem 1-11)
# ---------------------------------------------------------------------------
class TestPropellantIdentityReachesSolver:

    def test_grain_mechanics_follow_the_selected_propellant(
            self, client, base_payload):
        """HTPB elastomer ile dökme şeker aynı grain mekaniğini alamaz."""
        apcp = run(client, base_payload, propellant_type='apcp')
        sugar = run(client, base_payload, propellant_type='knsu')

        path = 'structural_analysis.grain_structural'
        for field in ('grain_elastic_modulus_mpa', 'grain_poisson_ratio',
                      'grain_thermal_expansion_1k', 'cure_temperature_k',
                      'strain_capability_percent'):
            assert leaf(apcp, f'{path}.{field}') != leaf(sugar, f'{path}.{field}'), (
                f'{field} yakıt değişince sabit kaldı')

        # Değerler tablonun KENDİSİnden gelmeli (ikinci bir kopya yok).
        assert leaf(apcp, f'{path}.grain_elastic_modulus_mpa') == pytest.approx(
            SOLID_GRAIN_MECHANICS['apcp']['elastic_modulus_pa'] / 1e6)
        assert leaf(sugar, f'{path}.strain_capability_percent') == pytest.approx(
            SOLID_GRAIN_MECHANICS['knsu']['strain_capability'] * 100)

    def test_identity_is_derived_from_the_burn_rate_preset(
            self, client, base_payload):
        """Sayfada yakıt kimliği alanı yok: ön ayar anahtarı kimliği taşır."""
        payload = dict(base_payload)
        payload.pop('propellant_type', None)
        body = run(client, payload, burn_rate_preset='knsu')
        assert body['propellant_type'] == 'knsu'

    def test_identity_is_derived_from_the_free_text_name(
            self, client, base_payload):
        """Katalogtan seçim yapılmadıysa serbest metin ad da tanınır."""
        payload = dict(base_payload)
        payload.pop('propellant_type', None)
        body = run(client, payload, burn_rate_preset='custom',
                   propellant_name='KNDX - Potassium Nitrate/Dextrose 65/35')
        assert body['propellant_type'] == 'kndx'

    def test_empty_identity_field_does_not_block_derivation(self, client,
                                                            base_payload):
        """Katalog satırı seçilmeyince arayüz BOŞ STRING gönderir.

        Boş değer "kullanıcı APCP seçti" sayılırsa ad/ön ayar yolu kapanır ve
        motor yine sessizce APCP çözer — düzeltmenin kendisi delinmiş olur.
        """
        body = run(client, base_payload, propellant_type='')
        assert body['propellant_type'] == 'kndx'

    def test_unmatched_propellant_name_is_declared_not_silent(
            self, client, base_payload):
        """Kendi karışımını yazan kullanıcı HTPB sayılarını sessizce almamalı."""
        body = run(client, base_payload, propellant_type='',
                   burn_rate_preset='custom', propellant_name='My Custom Mix')
        codes = {w.get('code') for w in body.get('warnings', [])
                 if isinstance(w, dict)}
        assert 'warn.solid.propellant_type_unresolved' in codes

    def test_explicit_type_beats_the_derived_one(self, client, base_payload):
        body = run(client, base_payload, propellant_type='double_base',
                   burn_rate_preset='knsu', propellant_name='KNSU')
        assert body['propellant_type'] == 'double_base'

    def test_two_phase_loss_follows_the_condensed_mass_fraction(
            self, client, base_payload):
        """Metalize APCP ile dumansız çift bazlı aynı kaybı raporlayamaz."""
        path = ('detailed_analysis.performance_metrics.'
                'theoretical_vs_actual_isp.two_phase_losses')
        apcp = leaf(run(client, base_payload, propellant_type='apcp'), path)
        double_base = leaf(run(client, base_payload,
                               propellant_type='double_base'), path)
        sugar = leaf(run(client, base_payload, propellant_type='knsu'), path)

        assert apcp > 0 and sugar > 0
        assert double_base == 0.0, 'dumansız yakıtta iki-fazlı kayıp olmaz'
        assert apcp != sugar
        # X_p tablosuyla tutarlı sıralama: şekerde yoğuşmuş faz daha ağır.
        assert (SOLID_CONDENSED_MASS_FRACTION['knsu']
                > SOLID_CONDENSED_MASS_FRACTION['apcp'])
        assert sugar > apcp

    def test_grain_temperature_limit_follows_the_propellant_and_is_labelled(
            self, client, base_payload):
        path = ('thermal_analysis.thermal_management.'
                'material_temperature_limits')
        apcp = run(client, base_payload, propellant_type='apcp')
        sugar = run(client, base_payload, propellant_type='knsu')
        assert (leaf(apcp, f'{path}.grain_max_temp_k')
                != leaf(sugar, f'{path}.grain_max_temp_k'))
        # Bu sayı ölçülmüş bir servis limiti DEĞİL: temeli beyan edilmeli.
        basis = leaf(apcp, f'{path}.grain_max_temp_basis').lower()
        assert 'cure' in basis and 'not a measured' in basis


# ---------------------------------------------------------------------------
# 2) Karışım oranları katalogtan (kalem 12-14)
# ---------------------------------------------------------------------------
class TestPublishedMixture:

    PATH = 'manufacturing_analysis.propellant_manufacturing.mixing_requirements'

    def test_percentages_follow_the_catalogue_record(self, client,
                                                     base_payload):
        apcp = leaf(run(client, base_payload, propellant_type='apcp'),
                    self.PATH)
        sugar = leaf(run(client, base_payload, propellant_type='knsu'),
                     self.PATH)
        assert apcp['oxidizer_percent'] != sugar['oxidizer_percent']
        assert apcp['fuel_percent'] != sugar['fuel_percent']
        # Şeker yakıtında bağlayıcı YOKTUR: sayı uydurulmamalı.
        assert sugar['binder_percent'] is None
        assert apcp['binder_percent'] is not None

    def test_untabulated_composition_reports_no_numbers(self, client,
                                                        base_payload):
        """Homojen çift bazlıda yüzde kaydı yok — sayı üretilmemeli."""
        mix = leaf(run(client, base_payload, propellant_type='double_base'),
                   self.PATH)
        assert mix['status'] == 'not_tabulated'
        for field in ('oxidizer_percent', 'fuel_percent', 'binder_percent'):
            assert mix[field] is None, f'{field} uydurulmuş'

    def test_additives_are_never_invented(self, client, base_payload):
        """Hiçbir katalog kaydı katkı oranı tablolamıyor."""
        for propellant in ('apcp', 'knsu', 'black_powder'):
            mix = leaf(run(client, base_payload, propellant_type=propellant),
                       self.PATH)
            assert mix['additives_percent'] is None


# ---------------------------------------------------------------------------
# 3) Nozul paneli (kalem 15-17)
# ---------------------------------------------------------------------------
class TestNozzlePanel:

    def test_published_half_angles_follow_the_user_input(self, client,
                                                         base_payload):
        base = run(client, base_payload)
        edited = run(client, base_payload, convergent_angle=40,
                     divergent_angle=12)
        assert leaf(base, 'cad_design.nozzle_design.convergent_angle') != \
            leaf(edited, 'cad_design.nozzle_design.convergent_angle')
        assert leaf(edited, 'cad_design.nozzle_design.divergent_angle') == \
            pytest.approx(12.0)
        # Açı ile uzunluk AYNI kaynaktan gelmeli.
        assert leaf(base, 'cad_design.nozzle_design.convergent_length') != \
            leaf(edited, 'cad_design.nozzle_design.convergent_length')

    def test_thrust_coefficient_is_computed_not_fixed(self, client,
                                                      base_payload):
        path = 'cad_design.nozzle_design.performance.thrust_coefficient'
        low = leaf(run(client, base_payload, chamber_pressure=30), path)
        high = leaf(run(client, base_payload, chamber_pressure=90), path)
        altitude = leaf(run(client, base_payload, test_altitude=10000), path)
        assert low != high != altitude
        assert low != pytest.approx(1.65), 'eski sabit geri geldi'


# ---------------------------------------------------------------------------
# 4) Yalıtım paketi (kalem 18-20)
# ---------------------------------------------------------------------------
class TestInsulationSystem:

    def test_ablative_liner_declares_no_net_heating_contract(
            self, client, base_payload):
        """KNDX kapak astarı: kalınlık YOK, rejim + gerekçe ZORUNLU.

        DEĞİŞİKLİK GEREKÇESİ (v2.6.27 blokaj denetimi): testin eski hâli
        'high > low' diye kalınlığın basınçla artmasını istiyordu. O
        kalınlıklar sabit-0.5 blokaj + soğuk-cidar akısıyla üretilmiş,
        gerileme hızı (0.36-0.92 mm/s) modelin kendi 0.35 mm/s geçerlilik
        tavanını İHLAL EDEN zarf-dışı sayılardı — 'sized' diye basılmaları
        kusurun kendisiydi. Yüzey enerji dengesi çözülünce KNDX çalışma
        noktasında (T_recovery, yüzey ablasyon sıcaklığına yakın) her iki
        kapak da 'no_net_heating' rejimine düşer: yarı-kararlı gerileme ~0,
        kalınlığı ise kasa/bond hattı iletim sınırı belirler ve bu modül
        onu MODELLEMİYOR. Dolayısıyla kusuru 'high > low' ile korumak artık
        imkânsız; bekçi SÖZLEŞMEYİ kilitler: sayı uydurulmaz (None), statü
        ve rejim beyan edilir, gerekçe validity_note'ta durur. (Kalınlığın
        gerçekten ısı yüküne bağlandığı 'sized' yol, APCP noktasında
        tests/test_kati_ablatif_baglama.py bekçileriyle kilitlidir.)
        """
        for pc in (30, 90):
            body = run(client, base_payload, chamber_pressure=pc)
            for station in ('forward_insulation', 'aft_insulation'):
                blok = leaf(body, f'cad_design.insulation_system.{station}')
                assert blok['thickness'] is None, (
                    f'Pc={pc} {station}: no_net_heating rejiminde kalınlık '
                    f'yayımlanmış — 0.0/4.0 mm sınıfı sessiz tehlike geri '
                    f'gelmiş olabilir')
                assert blok['thickness_status'] == 'NOT_MODELLED'
                assert blok['recession_regime'] == 'no_net_heating'
                assert blok['total_recession_mm'] == pytest.approx(0.0)
                # Üfleme yokken blokaj da yok: psi=1 limiti beyan edilmeli.
                assert blok['blowing_blockage'] == pytest.approx(1.0)
                assert blok['b_prime'] == pytest.approx(0.0)
                note = blok['validity_note']
                assert note and 'NO NET HEATING' in note
                assert 'case/bond-line' in note, (
                    'gerekçe iletim/bond sınırına işaret etmeli')

    def test_forward_and_aft_stations_are_distinct(self, client,
                                                   base_payload):
        """İki kapak aynı istasyon değil: malzeme VE gaz katsayısı farklı.

        v2.6.27 (B6-4) düzeltmesinin kilidi: v2.6.26'da iki kapak da boğaz
        akısıyla boyutlanıyor ve aynı sayıyı yayımlıyordu. Artık ön kapak
        hazne istasyonu + elastomer (EPDM, SP-8093 kubbe pratiği), lüle
        girişi boğaz istasyonu + silika-fenolik (SP-8115) olmalı.
        """
        ins = leaf(run(client, base_payload), 'cad_design.insulation_system')
        fwd, aft = ins['forward_insulation'], ins['aft_insulation']
        assert fwd['material'] != aft['material']
        assert 'EPDM' in fwd['material']
        assert 'Silica-phenolic' in aft['material']
        # Hazne ve boğaz Bartz katsayıları aynı sayı olamaz (boğaz kat kat
        # büyüktür — daralan kesitte kütle akısı artar).
        assert fwd['h_gas_W_m2K'] != aft['h_gas_W_m2K']
        assert aft['h_gas_W_m2K'] > fwd['h_gas_W_m2K']

    def test_forward_insulation_declares_its_conservative_basis(
            self, client, base_payload):
        fwd = leaf(run(client, base_payload),
                   'cad_design.insulation_system.forward_insulation')
        assert fwd['thickness'] != pytest.approx(5.0)
        assert 'conservative upper bound' in fwd['basis']

    def test_thermal_barrier_density_follows_the_liner_input(
            self, client, base_payload):
        path = 'cad_design.insulation_system.thermal_barrier.density'
        assert leaf(run(client, base_payload, liner_density=900), path) == \
            pytest.approx(900.0)
        assert leaf(run(client, base_payload, liner_density=1800), path) == \
            pytest.approx(1800.0)

    def test_inhibitor_coating_thickness_is_not_invented(self, client,
                                                         base_payload):
        coat = leaf(run(client, base_payload),
                    'cad_design.insulation_system.inhibitor_coating')
        assert coat['thickness'] is None
        assert coat['thickness_status'] == 'NOT_MODELLED'


# ---------------------------------------------------------------------------
# 5) Ateşleyici bloğu (kalem 21-25 + EK BULGU)
# ---------------------------------------------------------------------------
class TestIgniterSystem:

    GRAIN = 'cad_design.igniter_system.igniter_grain'

    def test_charge_mass_scales_with_free_volume(self, client, base_payload):
        """75 mm'lik motorla iki katı boyundaki motor aynı şarjı alamaz."""
        short = leaf(run(client, base_payload), f'{self.GRAIN}.mass')
        long = leaf(run(client, base_payload, grain_length=720),
                    f'{self.GRAIN}.mass')
        assert long > short > 0
        assert short != pytest.approx(2.0), 'eski sabit 2.0 g geri geldi'

    def test_charge_mass_scales_with_target_ignition_pressure(
            self, client, base_payload):
        low = leaf(run(client, base_payload, igniter_pressure_fraction=0.10),
                   f'{self.GRAIN}.mass')
        high = leaf(run(client, base_payload, igniter_pressure_fraction=0.30),
                    f'{self.GRAIN}.mass')
        assert high == pytest.approx(3.0 * low, rel=1e-6), (
            'serbest hacim ölçütü basınçta doğrusal olmalı')

    def test_ignition_pressure_is_declared_as_a_design_choice(
            self, client, base_payload):
        grain = leaf(run(client, base_payload), self.GRAIN)
        assert grain['ignition_pressure_fraction_of_pc'] == pytest.approx(
            SOLID_IGNITER['pressure_fraction_default'])
        assert 'DESIGN CHOICE' in grain['basis']
        assert 'SP-8051' in grain['basis']

    def test_unmodelled_igniter_fields_report_no_numbers(self, client,
                                                         base_payload):
        cad = leaf(run(client, base_payload), 'cad_design.igniter_system')
        assert cad['igniter_grain']['burn_time'] is None
        assert cad['igniter_grain']['burn_time_status'] == 'NOT_MODELLED'
        for field in ('diameter', 'length', 'wall_thickness'):
            assert cad['igniter_case'][field] is None, (
                f'ateşleyici kabı {field} uydurulmuş')
        assert cad['igniter_case']['status'] == 'NOT_MODELLED'
        assert cad['electrical_system']['resistance'] is None
        assert cad['electrical_system']['status'] == 'NOT_MODELLED'


# ---------------------------------------------------------------------------
# 6) Erozif yanma port oranı (kalem 26)
# ---------------------------------------------------------------------------
def test_final_port_factor_comes_from_the_regression_series(client,
                                                            base_payload):
    """Eski ifade cebirsel olarak her motorda 1.0 veriyordu."""
    path = ('detailed_analysis.grain_regression_analysis.'
            'erosive_burning_effects')
    bates = leaf(run(client, base_payload), path)
    star = leaf(run(client, base_payload, grain_type='star', star_points=6,
                    star_radius=18), path)
    assert bates['port_diameter_factor_final'] != \
        star['port_diameter_factor_final']
    assert 'solver regression series' in \
        bates['port_diameter_ratio_final_basis']


# ---------------------------------------------------------------------------
# 7) Kapak cıvata birleşimi (kalem 27-28)
# ---------------------------------------------------------------------------
class TestClosureJoint:

    PATH = 'structural_analysis.assembly_integrity'

    def test_reliability_percentage_is_gone(self, client, base_payload):
        integrity = leaf(run(client, base_payload), self.PATH)
        assert integrity['joint_reliability'] is None
        assert integrity['joint_reliability_status'] == 'NOT_MODELLED'

    def test_joint_is_not_sized_without_a_bolt_count(self, client,
                                                     base_payload):
        joint = leaf(run(client, base_payload), f'{self.PATH}.closure_joint')
        assert joint['status'] == 'not_sized'
        assert 'separation_factor' not in joint

    def test_safety_factors_follow_the_bolt_pattern(self, client,
                                                    base_payload):
        few = leaf(run(client, base_payload, closure_bolt_count=4),
                   f'{self.PATH}.closure_joint')
        many = leaf(run(client, base_payload, closure_bolt_count=12),
                    f'{self.PATH}.closure_joint')
        small = leaf(run(client, base_payload, closure_bolt_count=4,
                         closure_bolt_size='M5'),
                     f'{self.PATH}.closure_joint')
        assert many['separation_factor'] > few['separation_factor']
        assert small['separation_factor'] < few['separation_factor']
        assert few['status'] == 'sized'

    def test_pressure_drives_the_joint(self, client, base_payload):
        low = leaf(run(client, base_payload, closure_bolt_count=6,
                       chamber_pressure=20), f'{self.PATH}.closure_joint')
        high = leaf(run(client, base_payload, closure_bolt_count=6,
                        chamber_pressure=90), f'{self.PATH}.closure_joint')
        assert low['separation_factor'] > high['separation_factor']


# ---------------------------------------------------------------------------
# 8) Grain dış çapı / kasa iç çapı ayrımı (kalem 29)
# ---------------------------------------------------------------------------
class TestGrainOuterDiameter:

    def test_outer_diameter_drives_the_grain(self, client, base_payload):
        """Alan 'grain dış çapı' diye etiketli; grain'i o belirlemeli."""
        big = run(client, base_payload, outer_diameter=75)
        small = run(client, base_payload, outer_diameter=60)
        assert small['propellant_mass'] < big['propellant_mass']
        assert small['total_impulse'] < big['total_impulse']
        assert leaf(small, 'cad_design.case_design.grain_outer_diameter') == \
            pytest.approx(60.0)

    def test_chamber_diameter_is_the_case_bore(self, client, base_payload):
        """Etiketi 'kasa iç çapı': kasa zincirini o belirlemeli."""
        narrow = run(client, base_payload, outer_diameter=75,
                     chamber_diameter=80)
        wide = run(client, base_payload, outer_diameter=75,
                   chamber_diameter=95)
        assert leaf(narrow, 'cad_design.case_design.inner_diameter') == \
            pytest.approx(80.0)
        assert leaf(wide, 'cad_design.case_design.inner_diameter') == \
            pytest.approx(95.0)
        # Grain aynı kaldığı için yakıt kütlesi DEĞİŞMEMELİ.
        assert narrow['propellant_mass'] == pytest.approx(
            wide['propellant_mass'])
        # Kasa gerilmesi ise değişmeli (hoop yarıçapı kasa iç yarıçapıdır).
        assert leaf(narrow, 'structural_analysis.case_analysis.hoop_stress_mpa') \
            != leaf(wide, 'structural_analysis.case_analysis.hoop_stress_mpa')

    def test_case_bore_smaller_than_the_grain_is_reported(self, client,
                                                          base_payload):
        body = run(client, base_payload, outer_diameter=75,
                   chamber_diameter=70, insulation_thickness=3)
        codes = {w.get('code') for w in body.get('warnings', [])
                 if isinstance(w, dict)}
        assert 'warn.solid.case_bore_too_small' in codes
        # Geometrik alt sınır uygulanmalı: grain + 2 x yalıtım.
        assert leaf(body, 'cad_design.case_design.inner_diameter') == \
            pytest.approx(81.0)

    def test_field_is_no_longer_declared_unwired(self, client, base_payload):
        declared = []
        for fields in run(client, base_payload)['unwired_inputs'].values():
            declared.extend(fields or [])
        assert 'outer_diameter' not in declared, (
            'alan bağlandı ama hâlâ "kullanılmıyor" diye bildiriliyor')


# ---------------------------------------------------------------------------
# 9) İmalat resmi bloğu (EK BULGU 3)
# ---------------------------------------------------------------------------
def test_manufacturing_drawings_do_not_publish_invented_tolerances(
        client, base_payload):
    dims = leaf(run(client, base_payload),
                'cad_design.manufacturing_drawings.critical_dimensions')
    assert dims['status'] == 'NOT_MODELLED'
    for field in ('throat_diameter', 'case_bore', 'grain_fit', 'thread_class',
                  'surface_finish'):
        assert dims[field] is None, f'{field} toleransı uydurulmuş'


# ---------------------------------------------------------------------------
# 10) Sayfa sözleşmesi: kimlik ve yeni girdiler forma bağlı mı
# ---------------------------------------------------------------------------
class TestSolidPageSendsTheNewFields:

    @pytest.fixture(scope='class')
    def page(self):
        return (ROOT / 'hrma' / 'templates' / 'solid.html').read_text(
            encoding='utf-8')

    def test_payload_carries_the_propellant_identity(self, page):
        assert 'propellant_type: currentPropellantKey()' in page
        assert 'function currentPropellantKey()' in page

    def test_new_inputs_exist_and_are_collected(self, page):
        for field in ('closure_bolt_count', 'closure_bolt_size',
                      'closure_bolt_class', 'igniter_pressure_fraction'):
            assert f'id="{field}"' in page, f'{field} girdisi sayfada yok'
            assert f'{field}:' in page, f'{field} yükte gönderilmiyor'

    def test_mixture_panel_has_no_hardcoded_fallback(self, page):
        """Arayüz, çözücü boş bıraktığı yüzdeyi UYDURMAMALI."""
        for stale in ('mixingReqs.oxidizer_percent || 68',
                      'mixingReqs.fuel_percent || 18',
                      'mixingReqs.binder_percent || 12',
                      'mixingReqs.additives_percent || 2'):
            assert stale not in page, f'arayüzde sahte varsayılan: {stale}'
        assert 'fmtPercentOrNA(mixingReqs.oxidizer_percent)' in page


# ---------------------------------------------------------------------------
# 11) Serbest hacim TEK kaynaktan
# ---------------------------------------------------------------------------
def test_free_volume_has_a_single_definition(client, base_payload):
    """Ateşleyici ve rapor aynı serbest hacmi kullanmalı."""
    body = run(client, base_payload)
    reported_l = leaf(body, 'grain_design.case_free_volume_l')
    igniter_l = leaf(body, 'cad_design.igniter_system.igniter_grain.free_volume_l')
    assert reported_l == pytest.approx(igniter_l)

    motor = SolidRocketEngine(chamber_diameter=75, grain_length=360,
                              core_diameter=32, chamber_pressure=40)
    assert motor._case_free_volume() > 0
