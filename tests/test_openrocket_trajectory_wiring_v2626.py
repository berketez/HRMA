"""v2.6.26 ölü girdi kilitleri — OpenRocket dışa aktarımı + yörünge dalı.

Bu dosya iki kalemi bekçiye bağlar (docs/dev/kusur_partileri.json, P4 ve P5):

P4 — ``.openrocket.flight_profile.simulation_settings.wind_speed``
    Değer 0 m/s olarak SABİT yazılıyordu. Oysa hibrit sayfasında gerçek bir
    rüzgâr alanı var (advanced.html:1563), istekle gönderiliyor ve AYNI
    isteğin yörünge dalında kullanılıyor (app.py:1117). Kullanıcı 12 m/s
    girse bile dışa aktarım "rüzgârsız" diyordu; varsayılanın da 0 olması
    kusuru gizliyordu. Artık fırlatma koşulu çağırandan gelir
    (``resolve_launch_settings``); gelmediyse sayı UYDURULMAZ, alan None
    kalır ve nedeni ``simulation_settings_source`` içinde yazılıdır.

P5 — ``.trajectory.vehicle_parameters.cross_sectional_area``
    A = π·d²/4 bağıntısının kendisi doğru ve girdisine BAĞLI: ölçüldü,
    istekte ``vehicle_diameter`` değişince alan da değişiyor. Yaprağın
    tarayıcıda sabit görünmesinin nedeni bu modül değil, sayfada
    ``id="vehicle_diameter"`` elemanının hiç bulunmamasıdır
    (advanced.html:3292 → ``?.value || 0.15``). Buradaki testler modül
    tarafındaki canlı bağı KİLİTLER ki düzeltme sırasında sessizce
    sabitlenmesin.
"""

import contextlib
import io

import numpy as np
import pytest

from hrma.analysis.trajectory_analysis import TrajectoryAnalyzer
from hrma.export.openrocket_integration import (
    EXPORTER_DEFAULT_SETTINGS,
    LAUNCH_SETTING_SOURCE_LABELS,
    OpenRocketExporter,
)
from tests.test_field_wiring_layer_b import HYBRID_BASE


def _silent(fn, *args, **kwargs):
    """Çözücülerin print gürültüsünü yutar."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        return fn(*args, **kwargs)


# Dışa aktarım testleri motorun kendisini çözmek zorunda değil; eğri ve
# kütleler dışında hiçbir alan simulation_settings'e girmiyor.
MOTOR = {
    'motor_name': 'WIRING-P4',
    'thrust': 5000.0,
    'burn_time': 10.0,
    'total_impulse': 50000.0,
    'isp': 240.0,
    'propellant_mass_total': 27.5,
    'chamber_diameter': 0.152,
    'chamber_length': 0.88,
    'throat_diameter': 0.0305,
    'exit_diameter': 0.061,
}


# ---------------------------------------------------------------------------
# P4 — rüzgâr (ve kardeş fırlatma koşulları) çağırandan gelir
# ---------------------------------------------------------------------------
class TestLaunchSettingsAreWired:

    @pytest.mark.parametrize('wind', [0.0, 3.5, 12.0, 25.0])
    def test_wind_speed_follows_the_caller(self, wind):
        """Kullanıcının rüzgârı çıktıya BİREBİR ulaşmalı (0 dahil).

        ÖNCE: launch_params ne olursa olsun 0 m/s. SONRA: 0 → 0, 12 → 12.
        Kullanıcının yazdığı 0 ile "veri yok" ayrı şeydir; ilki 'request'
        kaynağıyla gelir.
        """
        data = OpenRocketExporter().create_flight_simulation_data(
            MOTOR, launch_params={'wind_speed': wind})
        assert data['simulation_settings']['wind_speed'] == pytest.approx(wind)
        assert data['simulation_settings_source']['wind_speed'] == 'request'

    def test_two_different_winds_give_two_different_leaves(self):
        """Girdi oynayınca yaprak da oynamalı — sabitlenme bekçisi."""
        exporter = OpenRocketExporter()
        calm = exporter.create_flight_simulation_data(
            MOTOR, launch_params={'wind_speed': 0.0})
        gusty = exporter.create_flight_simulation_data(
            MOTOR, launch_params={'wind_speed': 12.0})
        assert (calm['simulation_settings']['wind_speed']
                != gusty['simulation_settings']['wind_speed'])

    def test_missing_wind_is_declared_not_invented(self):
        """Veri yoksa 0 m/s UYDURULMAZ; alan boş kalır ve nedeni yazılır."""
        data = OpenRocketExporter().create_flight_simulation_data(MOTOR)
        settings = data['simulation_settings']
        sources = data['simulation_settings_source']
        assert settings['wind_speed'] is None
        assert sources['wind_speed'] == 'not_supplied'
        # Etiket okunabilir olmalı: dosyayı açan kişi neden boş olduğunu görsün.
        assert 'NOT supplied' in data['simulation_settings_source_labels']['wind_speed']

    @pytest.mark.parametrize('bad', [-3.0, float('nan'), float('inf'), 'kuvvetli'])
    def test_out_of_range_wind_is_rejected_not_silently_used(self, bad):
        """Geçersiz rüzgâr sessizce kabul edilmez ve sıfıra da kırpılmaz."""
        data = OpenRocketExporter().create_flight_simulation_data(
            MOTOR, launch_params={'wind_speed': bad})
        assert data['simulation_settings']['wind_speed'] is None
        assert data['simulation_settings_source']['wind_speed'] == 'invalid_input'

    @pytest.mark.parametrize('key,value', [
        ('launch_angle', 60.0),
        ('launch_angle', 90.0),
        ('launch_altitude', 1500.0),
        ('wind_direction', 210.0),
    ])
    def test_sibling_launch_settings_use_the_same_door(self, key, value):
        """Rüzgârla aynı kapıdan geçen fırlatma koşulları da canlı olmalı.

        app.py'nin yörünge dalında kurduğu ``launch_params`` sözlüğü aynı
        anahtar adlarını kullanır; tek yanıtta iki farklı fırlatma koşulu
        dolaşmasın diye ad birliği kasıtlıdır.
        """
        data = OpenRocketExporter().create_flight_simulation_data(
            MOTOR, launch_params={key: value})
        assert data['simulation_settings'][key] == pytest.approx(value)
        assert data['simulation_settings_source'][key] == 'request'

    def test_launch_angle_outside_the_form_band_is_rejected(self):
        """0–90° bandı dışındaki yükseliş açısı yazılmaz (advanced.html:1553)."""
        data = OpenRocketExporter().create_flight_simulation_data(
            MOTOR, launch_params={'launch_angle': 120.0})
        assert data['simulation_settings']['launch_angle'] is None
        assert data['simulation_settings_source']['launch_angle'] == 'invalid_input'

    def test_exporter_defaults_are_labelled_as_such(self):
        """Arayüzde karşılığı olmayan ayarlar varsayılan kalır ama BEYAN edilir."""
        data = OpenRocketExporter().create_flight_simulation_data(MOTOR)
        settings = data['simulation_settings']
        sources = data['simulation_settings_source']
        for key, default in EXPORTER_DEFAULT_SETTINGS.items():
            assert settings[key] == default
            assert sources[key] == 'exporter_default'
        # Her kaynak etiketinin bir karşılığı olmalı (sessiz anahtar yok).
        for value in sources.values():
            assert value in LAUNCH_SETTING_SOURCE_LABELS


class TestOrkTemplateUsesTheSameSource:

    def test_xml_wind_matches_the_json_setting(self):
        """XML'deki windaverage ile JSON'daki wind_speed tek kaynaktan gelmeli."""
        exporter = OpenRocketExporter()
        launch = {'wind_speed': 12.0, 'launch_angle': 60.0}
        xml = exporter.create_ork_project_template(MOTOR, launch_params=launch)
        settings = exporter.create_flight_simulation_data(
            MOTOR, launch_params=launch)['simulation_settings']
        assert f"<windaverage>{settings['wind_speed']}</windaverage>" in xml
        assert f"<launchrodangle>{settings['launch_angle']}</launchrodangle>" in xml

    def test_xml_declares_the_placeholder_when_no_data_is_supplied(self):
        """XML sayı yazmak zorunda; ama bunun varsayım olduğunu söylemeli."""
        xml = OpenRocketExporter().create_ork_project_template(MOTOR)
        assert '<windaverage>0.0</windaverage>' in xml
        assert 'NO wind data supplied' in xml

    def test_rod_length_is_not_duplicated_in_two_places(self):
        """Rampa boyu tek tanım noktasından (CLAUDE.md kural 11)."""
        rod = EXPORTER_DEFAULT_SETTINGS['launch_rod_length']
        xml = OpenRocketExporter().create_ork_project_template(MOTOR)
        assert f'<launchrodlength>{float(rod)}</launchrodlength>' in xml


# ---------------------------------------------------------------------------
# P5 — kesit alanı araç çapını izler (modül tarafı canlı, kilitlensin)
# ---------------------------------------------------------------------------
TRAJ_MOTOR = {
    'thrust': 3000.0,
    'burn_time': 4.0,
    'total_impulse': 12000.0,
    'isp': 200.0,
    'propellant_mass_total': 8.0,
}


def _trajectory(diameter):
    ta = TrajectoryAnalyzer()
    ta.set_vehicle_parameters(mass_dry=20.0, diameter=diameter,
                              drag_coefficient=0.5)
    return ta.calculate_trajectory(
        TRAJ_MOTOR, {'launch_angle': 85.0, 'launch_altitude': 0.0,
                     'wind_speed': 0.0, 'wind_direction': 0.0})


class TestCrossSectionFollowsDiameter:

    @pytest.mark.parametrize('diameter', [0.10, 0.15, 0.357])
    def test_area_is_the_circle_of_the_given_diameter(self, diameter):
        """A = π·d²/4 — verilen çapın dairesi, sabit bir alan değil."""
        result = _trajectory(diameter)
        area = result['vehicle_parameters']['cross_sectional_area']
        assert area == pytest.approx(np.pi * diameter ** 2 / 4.0, rel=1e-12)

    def test_bigger_diameter_costs_altitude(self):
        """Alan sürüklemeyi ölçeklediği için apoje de çapı izlemeli.

        Alan yalnız raporlanan bir sayı değil; kuvvete giriyor. Bu test
        yaprağın "canlı görünüp" hesaba girmemesini de yakalar.
        """
        small = _trajectory(0.15)
        large = _trajectory(0.357)
        h_small = small['performance']['trajectory_metrics']['max_altitude']
        h_large = large['performance']['trajectory_metrics']['max_altitude']
        assert h_large < h_small


class TestRequestReachesTheTrajectoryBranch:
    """İstekteki ``vehicle_diameter`` /calculate yolunda gerçekten kullanılıyor mu?

    Kusur raporu bu yaprağı SABİT diye işaretledi; ölçüm gösterdi ki uç nokta
    değeri okuyor (app.py:1108) — sabitlik tarayıcı toplayıcısından geliyor
    (advanced.html:3292'de okunan ``id="vehicle_diameter"`` elemanı sayfada
    YOK). Bu test uç noktadaki canlı bağı kilitler.
    """

    @pytest.fixture(scope='class')
    def responses(self):
        from hrma.app import app

        client = app.test_client()
        out = {}
        for diameter in (0.15, 0.30):
            response = _silent(
                client.post, '/calculate',
                json=dict(HYBRID_BASE, vehicle_diameter=diameter),
                headers={'Host': '127.0.0.1:8080'})
            assert response.status_code == 200, \
                f'/calculate HTTP {response.status_code}'
            out[diameter] = response.get_json()
        return out

    def test_area_follows_the_requested_diameter(self, responses):
        for diameter, payload in responses.items():
            vehicle = payload['trajectory']['vehicle_parameters']
            assert vehicle['diameter'] == pytest.approx(diameter)
            assert vehicle['cross_sectional_area'] == pytest.approx(
                np.pi * diameter ** 2 / 4.0, rel=1e-12)

    def test_apogee_moves_with_the_diameter(self, responses):
        h = {d: p['trajectory']['performance']['trajectory_metrics']['max_altitude']
             for d, p in responses.items()}
        assert h[0.30] < h[0.15]

    def test_exported_wind_speed_is_never_an_undeclared_constant(self, responses):
        """P4 sözleşmesi uçtan uca: ya kullanıcının değeri, ya beyan edilmiş boşluk.

        /calculate bugün ``launch_params`` geçirmiyor (app.py:1058) — o satır
        bu partinin dışında. Sözleşme yine de kilitli: rüzgâr ya istekten
        gelir ('request') ya da alan boş kalır. Sessizce yazılmış bir sayı
        (eski 0 m/s) bu testi kırar.
        """
        for payload in responses.values():
            profile = payload['openrocket']['flight_profile']
            settings = profile['simulation_settings']
            sources = profile['simulation_settings_source']
            assert settings['wind_speed'] is None or sources['wind_speed'] == 'request'
            assert settings['launch_angle'] is None or sources['launch_angle'] == 'request'
