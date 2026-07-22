"""
Uç parametreleri + sıvı/hibrit fizik bekçileri (v2.5.2, 2026-07-19).

Bağımsız bir modelin (Codex gpt-5.6-sol) taramasında bulunan ve kodla
sayısal olarak doğrulanan altı kusuru kalıcı hale getirmemek için yazıldı.
Her sınıf tek bir bulguyu kilitler:

  1. /api/advanced-performance-analysis 'nozzle_mach' — uç, gaz hâli ve oda
     basıncını Mach çözücüsüne AKTARMALI (eskiden yalnız boğaz alanı, lüle
     boyu ve genişleme oranı geçiyor; çözücü 20 bar / gamma 1.20 / 1 atm
     varsayılanlarına düşüyordu).
  2. /api/advanced-performance-analysis '3d_surface' — yakıt/oksitleyici
     kimliği aktarılmalı (eskiden LOX/RP-1 koşusunda bile HTPB/N2O referans
     yüzeyi çiziliyordu).
  3. Sıvı motor: SABİT genişleme oranında çıkış Mach'ı irtifayla DEĞİŞMEZ
     (Ae/At ve gamma belirler); basınç-itki terimi ise değişir.
  4. Sıvı motor: soğutma entegrasyonu yakınsak koniyi ıraksak lüle boyunun
     içinden çalmaz; yakınsak uzunluk AYRI eklenir.
  5. Sıvı motor: tank hacmi TEK modelden gelir ve kullanıcı yoğunluğunu
     dinler (besleme kartı ile ayrıntılı tank kartı aynı değeri verir).
  6. Hibrit motor: port >= kamara isteği REDDEDİLİR (HTTP 400) ve hiçbir
     kütle negatif olmaz.

Not: bu dosya sunucuya port bağlamaz; Flask test_client kullanır.
"""

import json
import warnings

import numpy as np
import pytest

warnings.filterwarnings('ignore')

ENDPOINT = '/api/advanced-performance-analysis'


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _figure(response):
    """Yanıttan plotly figürünü çıkarır (plot_data JSON *string* gelir)."""
    assert response.status_code == 200, response.get_data(as_text=True)[:400]
    body = response.get_json()
    assert body['status'] == 'success', body
    fig = body['plot_data']
    return json.loads(fig) if isinstance(fig, str) else fig


def _figure_text(fig):
    """Figürün tüm metinlerini (başlık + açıklamalar) tek dizede toplar."""
    layout = fig.get('layout') or {}
    parts = [json.dumps(layout.get('title', ''))]
    for ann in (layout.get('annotations') or []):
        parts.append(str(ann.get('text', '')))
    return ' '.join(parts)


def _mach_values(fig):
    """Mach kontur izindeki sonlu z değerleri."""
    for trace in fig.get('data', []):
        if trace.get('type') == 'contour':
            z = np.asarray(trace['z'], dtype=float)
            return z[np.isfinite(z)]
    raise AssertionError('Mach kontur izi bulunamadi')


# ---------------------------------------------------------------------------
# 1) Nozul Mach ucu: gaz hâli ve oda basıncı GERÇEKTEN çözücüye gidiyor
# ---------------------------------------------------------------------------
class TestNozzleMachEndpointForwardsGasState:

    BASE = {
        'analysis_type': 'nozzle_mach',
        'throat_area': 0.0012,
        'nozzle_length': 0.25,
        'expansion_ratio': 16.0,
        'chamber_temperature': 3400.0,
        'molecular_weight': 22.0,
    }

    def test_chamber_pressure_changes_the_regime(self, client):
        """Oda basıncı rejimi (aşırı/az genişleme) belirler; grafiği DEĞİŞTİRMELİ."""
        low = _figure(client.post(ENDPOINT, json=dict(self.BASE,
                                                      chamber_pressure=5.0,
                                                      gamma=1.20)))
        high = _figure(client.post(ENDPOINT, json=dict(self.BASE,
                                                       chamber_pressure=200.0,
                                                       gamma=1.20)))
        assert _figure_text(low) != _figure_text(high), (
            'Oda basinci 5 bar -> 200 bar degistiginde Mach figuru hic '
            'degismedi: uc hala chamber_pressure alanini dusuruyor.')

    def test_gamma_changes_the_mach_solution(self, client):
        """Alan-Mach bağıntısını gamma yönetir; Mach alanı DEĞİŞMELİ."""
        soft = _mach_values(_figure(client.post(
            ENDPOINT, json=dict(self.BASE, chamber_pressure=50.0, gamma=1.14))))
        stiff = _mach_values(_figure(client.post(
            ENDPOINT, json=dict(self.BASE, chamber_pressure=50.0, gamma=1.30))))
        assert abs(float(soft.max()) - float(stiff.max())) > 1e-3, (
            'gamma 1.14 -> 1.30 degistiginde cikis Mach sayisi ayni kaldi: '
            'uc gamma alanini dusuruyor (cozucu 1.20 varsayilaninda).')

    def test_supplied_gas_state_is_not_reported_as_assumed(self, client):
        """Geçirilen alanlar figürün 'Assumed' listesinde YER ALMAMALI."""
        fig = _figure(client.post(ENDPOINT, json=dict(
            self.BASE, chamber_pressure=50.0, gamma=1.22,
            chamber_diameter=0.14)))
        text = _figure_text(fig)
        assumed = text.split('Assumed (not supplied by this call):')
        if len(assumed) > 1:
            tail = assumed[1]
            for token in ('gamma =', 'Pc =', 'Tc =', 'MW =',
                          'chamber diameter'):
                assert token not in tail, (
                    f"'{token}' hala varsayim olarak raporlaniyor; uc bu "
                    f"alani cozucuye gecirmiyor.")


# ---------------------------------------------------------------------------
# 2) Denge performans yüzeyi: yakıt çifti kimliği aktarılıyor
# ---------------------------------------------------------------------------
class TestPerformanceSurfaceUsesPropellantIdentity:

    BASE = {
        'analysis_type': '3d_surface',
        'chamber_pressure': 50,
        'optimal_of_ratio': 2.5,
        'base_isp': 300,
        # Tarama pahalı: en küçük ızgara yeterli (kimlik testi)
        'grid_n': 3,
        'pc_range': [40, 60],
    }

    def test_propellant_pair_changes_the_surface(self, client):
        """Yakıt çifti değişince ÇÖZÜLEN yüzey de değişmeli.

        Not: CombustionAnalyzer bu sürümde yalnız hibrit katı yakıtları
        (htpb/paraffin/pe/pmma/abs/pla/aluminum) çözebiliyor; bu yüzden
        kimlik duyarlılığı iki çözülebilir çiftle sınanır. Sıvı bipropellant
        çifti için yüzey boşluklarla ve "0/N nodes solved" etiketiyle
        DÜRÜSTÇE çizilir (bkz. test_unsolvable_pair_is_reported_honestly).
        """
        a = _figure(client.post(ENDPOINT, json=dict(
            self.BASE, fuel_type='htpb', oxidizer_type='n2o',
            of_range=[2.0, 3.0])))
        b = _figure(client.post(ENDPOINT, json=dict(
            self.BASE, fuel_type='pmma', oxidizer_type='n2o',
            of_range=[2.0, 3.0])))
        za = np.asarray(a['data'][0]['z'], dtype=float)
        zb = np.asarray(b['data'][0]['z'], dtype=float)
        both = np.isfinite(za) & np.isfinite(zb)
        assert both.any(), 'Iki taramada da ortak cozulmus dugum yok'
        assert not np.allclose(za[both], zb[both]), (
            'N2O/HTPB ve N2O/PMMA ayni Isp yuzeyini verdi: uc yakit '
            'kimligini dusuruyor ve referans cifti cozuyor.')

    def test_oxidizer_identity_changes_the_surface(self, client):
        a = _figure(client.post(ENDPOINT, json=dict(
            self.BASE, fuel_type='htpb', oxidizer_type='n2o',
            of_range=[2.0, 3.0])))
        b = _figure(client.post(ENDPOINT, json=dict(
            self.BASE, fuel_type='htpb', oxidizer_type='lox',
            of_range=[2.0, 3.0])))
        za = np.asarray(a['data'][0]['z'], dtype=float)
        zb = np.asarray(b['data'][0]['z'], dtype=float)
        both = np.isfinite(za) & np.isfinite(zb)
        assert both.any()
        assert not np.allclose(za[both], zb[both]), (
            'N2O ve LOX ayni yuzeyi verdi: uc oksitleyici kimligini dusuruyor.')

    def test_supplied_pair_is_not_flagged_as_reference(self, client):
        fig = _figure(client.post(ENDPOINT, json=dict(
            self.BASE, fuel_type='htpb', oxidizer_type='lox',
            of_range=[2.0, 3.0])))
        text = _figure_text(fig)
        assert 'reference pair' not in text, (
            'Yakit cifti verildigi halde figur hala "reference pair" '
            'uyarisi basiyor.')
        assert 'LOX' in text and 'HTPB' in text, text[:300]

    def test_unsolvable_pair_is_reported_honestly(self, client):
        """Çözücünün desteklemediği çift SESSİZCE başka bir çifte düşmemeli.

        LOX/RP-1 bu sürümdeki denge çözücüsünün kapsamı dışında. Doğru
        davranış: figürün etiketi istenen çifti göstermesi ve düğümlerin
        'unsolved' olarak raporlanması. Yanlış davranış (düzeltilen hata):
        HTPB/N2O yüzeyini çizip LOX/RP-1 sanmak.
        """
        fig = _figure(client.post(ENDPOINT, json=dict(
            self.BASE, fuel_type='rp1', oxidizer_type='lox',
            of_range=[2.0, 3.0])))
        text = _figure_text(fig)
        assert 'RP1' in text and 'LOX' in text, text[:300]
        assert 'HTPB' not in text and 'N2O' not in text, (
            'Istenen cift LOX/RP-1 iken figur HTPB/N2O referansini gosteriyor.')
        assert 'unsolved' in text, (
            'Cozulemeyen dugumler "unsolved" olarak raporlanmiyor.')


# ---------------------------------------------------------------------------
# 3) Sıvı motor: sabit lülede çıkış Mach'ı irtifayla değişmez
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def fixed_nozzle_engine():
    from hrma.engines.liquid_rocket_engine import LiquidRocketEngine
    engine = LiquidRocketEngine(
        thrust=10000, chamber_pressure=50, mixture_ratio=2.5,
        fuel_type='rp1', oxidizer_type='lox',
        overrides={'nozzle_expansion_ratio': 16.0})
    engine.calculate_nozzle_geometry()
    return engine


class TestFixedNozzleExitMach:

    ALTITUDES = [0, 10000, 30000, 100000]

    def test_exit_mach_is_constant_with_altitude(self, fixed_nozzle_engine):
        data = fixed_nozzle_engine.calculate_altitude_performance(self.ALTITUDES)
        machs = [d['exit_mach_number'] for d in data]
        assert max(machs) - min(machs) < 1e-6, (
            f"Sabit genisleme oraninda cikis Mach'i irtifayla degisti: "
            f"{machs}. Sabit geometride Me yalniz Ae/At ve gamma ile "
            f"belirlenir (Sutton & Biblarz Eq. 3-15).")

    def test_exit_mach_matches_the_area_ratio(self, fixed_nozzle_engine):
        data = fixed_nozzle_engine.calculate_altitude_performance([0])
        expected = fixed_nozzle_engine._mach_from_area_ratio_supersonic(
            fixed_nozzle_engine.expansion_ratio, fixed_nozzle_engine.gamma)
        assert data[0]['exit_mach_number'] == pytest.approx(expected, rel=1e-6)

    def test_exit_velocity_is_constant_with_altitude(self, fixed_nozzle_engine):
        data = fixed_nozzle_engine.calculate_altitude_performance(self.ALTITUDES)
        vels = [d['exit_velocity'] for d in data]
        assert max(vels) - min(vels) < 1e-6, (
            f"Cikis hizi sabit geometride irtifayla degisti: {vels}")

    def test_pressure_thrust_term_does_change(self, fixed_nozzle_engine):
        """Irtifayla degisen buyukluk basinc-itki terimidir, Mach degil."""
        data = fixed_nozzle_engine.calculate_altitude_performance(self.ALTITUDES)
        pt = [d['pressure_thrust'] for d in data]
        cf = [d['thrust_coefficient'] for d in data]
        assert pt[-1] > pt[0], (
            f"Basinc-itki terimi irtifayla artmadi: {pt}")
        assert cf[-1] > cf[0], f"CF irtifayla artmadi: {cf}"

    def test_exit_pressure_is_fixed_by_geometry(self, fixed_nozzle_engine):
        data = fixed_nozzle_engine.calculate_altitude_performance(self.ALTITUDES)
        pe = [d['exit_pressure_bar'] for d in data]
        assert max(pe) - min(pe) < 1e-9, (
            f"Sabit lulede cikis STATIK basinci irtifayla degisti: {pe}")


# ---------------------------------------------------------------------------
# 4) Sıvı motor: soğutma entegrasyonu yakınsak koniyi ayrıca sayıyor
# ---------------------------------------------------------------------------
class TestCoolingIntegrationGeometry:

    def test_convergent_length_is_added_not_stolen(self, fixed_nozzle_engine):
        from hrma.engines.liquid_rocket_engine import CONVERGENT_HALF_ANGLE_DEG
        eng = fixed_nozzle_engine
        cooling = eng.calculate_cooling_requirements()

        d_ch = cooling['chamber_diameter'] / 1000.0  # m
        expected_conv = (d_ch - eng.d_t) / (
            2.0 * np.tan(np.radians(CONVERGENT_HALF_ANGLE_DEG)))

        assert cooling['convergent_length'] / 1000.0 == pytest.approx(
            expected_conv, rel=1e-9)
        # Iraksak bolum L_nozzle'in TAMAMI olmali (eskiden %70'i)
        assert cooling['divergent_length'] / 1000.0 == pytest.approx(
            eng.L_nozzle, rel=1e-9)
        # Yakinsak koni iraksak boydan CALINMIYOR
        assert cooling['convergent_length'] > 0.0

    def test_cooled_channel_length_covers_all_three_sections(
            self, fixed_nozzle_engine):
        cooling = fixed_nozzle_engine.calculate_cooling_requirements()
        expected = (cooling['chamber_length'] + cooling['convergent_length']
                    + cooling['divergent_length'])
        assert cooling['cooled_channel_length'] == pytest.approx(expected,
                                                                rel=1e-9)

    def test_nozzle_surface_area_uses_slant_length(self, fixed_nozzle_engine):
        """Konik yüzey eğik uzunlukla hesaplanır -> eksen yaklaşımından BÜYÜK."""
        eng = fixed_nozzle_engine
        cooling = eng.calculate_cooling_requirements()
        d_ch = cooling['chamber_diameter'] / 1000.0
        l_conv = cooling['convergent_length'] / 1000.0
        l_div = cooling['divergent_length'] / 1000.0
        # Eksen uzunluguyla (egimsiz) kaba alt sinir
        axial_only = (np.pi * 0.5 * (d_ch + eng.d_t) * l_conv
                      + np.pi * 0.5 * (eng.d_t + eng.d_e) * l_div)
        assert cooling['nozzle_surface_area'] > axial_only, (
            'Lule yuzey alani egik uzunluk yerine eksen uzunlugu kullaniyor.')

    def test_heat_load_is_the_sum_of_the_two_sections(self,
                                                      fixed_nozzle_engine):
        cooling = fixed_nozzle_engine.calculate_cooling_requirements()
        assert cooling['total_heat_load'] == pytest.approx(
            cooling['chamber_heat_load'] + cooling['nozzle_heat_load'],
            rel=1e-9)
        assert cooling['nozzle_heat_load'] > 0


# ---------------------------------------------------------------------------
# 5) Sıvı motor: tank hacmi tek kaynaktan ve kullanıcı yoğunluğunu dinliyor
# ---------------------------------------------------------------------------
def _run_liquid(overrides):
    from hrma.engines.liquid_rocket_engine import LiquidRocketEngine
    engine = LiquidRocketEngine(
        thrust=10000, chamber_pressure=50, mixture_ratio=2.5,
        fuel_type='rp1', oxidizer_type='lox',
        overrides=dict({'max_burn_duration': 60}, **overrides))
    return engine, engine.calculate_performance()


def _tank_pair(result):
    """(besleme kartı m³, ayrıntılı kart m³) — oksitleyici ve yakıt."""
    feed = result['feed_system']['tanks']
    detail = result['propellant_tanks']
    return (
        (feed['oxidizer_tank']['volume'],
         detail['oxidizer_tank']['dimensions']['volume'] / 1000.0),
        (feed['fuel_tank']['volume'],
         detail['fuel_tank']['dimensions']['volume'] / 1000.0),
    )


class TestTankVolumeSingleSource:

    def test_feed_and_detailed_cards_agree(self):
        _, result = _run_liquid({})
        (ox_feed, ox_detail), (fuel_feed, fuel_detail) = _tank_pair(result)
        assert ox_feed == pytest.approx(ox_detail, rel=1e-9), (
            f"Ayni kosuda iki farkli oksitleyici tank hacmi: besleme "
            f"{ox_feed:.4f} m3 vs ayrintili {ox_detail:.4f} m3")
        assert fuel_feed == pytest.approx(fuel_detail, rel=1e-9), (
            f"Ayni kosuda iki farkli yakit tank hacmi: besleme "
            f"{fuel_feed:.4f} m3 vs ayrintili {fuel_detail:.4f} m3")

    def test_user_density_drives_both_cards(self):
        _, base = _run_liquid({})
        _, light = _run_liquid({'oxidizer_density': 900,
                                'fuel_density': 700})
        (ox_feed_b, ox_det_b), (fu_feed_b, fu_det_b) = _tank_pair(base)
        (ox_feed_l, ox_det_l), (fu_feed_l, fu_det_l) = _tank_pair(light)

        assert ox_feed_l > ox_feed_b * 1.05, (
            f"Kullanici oksitleyici yogunlugunu dusurdu ama BESLEME tank "
            f"hacmi degismedi: {ox_feed_b:.4f} -> {ox_feed_l:.4f} m3")
        assert fu_feed_l > fu_feed_b * 1.05, (
            f"Kullanici yakit yogunlugunu dusurdu ama BESLEME tank hacmi "
            f"degismedi: {fu_feed_b:.4f} -> {fu_feed_l:.4f} m3")
        assert ox_feed_l == pytest.approx(ox_det_l, rel=1e-9)
        assert fu_feed_l == pytest.approx(fu_det_l, rel=1e-9)

    def test_reported_density_matches_the_user_input(self):
        _, result = _run_liquid({'oxidizer_density': 900, 'fuel_density': 700})
        detail = result['propellant_tanks']
        assert detail['oxidizer_tank']['propellant_data']['density'] == \
            pytest.approx(900.0)
        assert detail['fuel_tank']['propellant_data']['density'] == \
            pytest.approx(700.0)
        assert detail['oxidizer_tank']['propellant_data'][
            'density_source'] == 'user input'

    def test_density_source_is_labelled_when_not_supplied(self):
        _, result = _run_liquid({})
        summary = result['propellant_tanks']['system_summary']
        assert summary['oxidizer_density_source'] == 'built-in propellant table'
        assert 'single tank-sizing model' in summary['sizing_model']


# ---------------------------------------------------------------------------
# 6) Hibrit motor: port >= kamara reddedilir, negatif kütle imkansız
# ---------------------------------------------------------------------------
HYBRID_ENDPOINT_PAYLOAD = {
    'motor_type': 'hybrid',
    'thrust': 5000,
    'burn_time': 10,
    'of_ratio': 6.0,
    'chamber_pressure': 30,
    'atmospheric_pressure': 1.0,
    'fuel_type': 'htpb',
    'oxidizer_type': 'n2o',
    'mass_flux_chamber': 80,
}


class TestHybridImpossibleChamberGeometry:

    def test_engine_rejects_port_larger_than_chamber(self):
        from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
        with pytest.raises(ValueError) as exc:
            engine = HybridRocketEngine(
                thrust=5000, burn_time=10, of_ratio=6.0,
                chamber_pressure=30, chamber_diameter_input=40,
                initial_gox=80, track_performance=False)
            engine.calculate()
        message = str(exc.value)
        assert 'chamber diameter' in message.lower()
        assert 'port' in message.lower()

    def test_endpoint_returns_400(self, client):
        payload = dict(HYBRID_ENDPOINT_PAYLOAD, chamber_diameter_input=40)
        r = client.post('/calculate', json=payload)
        assert r.status_code == 400, (
            'Imkansiz geometri (port >= kamara) 400 yerine '
            f'{r.status_code} dondu — hesap sessizce devam ediyor.')
        body = r.get_json()
        assert 'chamber diameter' in json.dumps(body).lower()

    def test_valid_geometry_has_no_negative_masses(self):
        from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
        engine = HybridRocketEngine(
            thrust=5000, burn_time=10, of_ratio=6.0, chamber_pressure=30,
            chamber_diameter_input=400, initial_gox=80,
            track_performance=False)
        results = engine.calculate()
        for key in ('fuel_mass', 'fuel_mass_loaded', 'oxidizer_mass',
                    'propellant_mass_total'):
            assert results[key] > 0, f"{key} pozitif degil: {results[key]}"
        assert results['fuel_mass_loaded'] >= results['fuel_mass'], (
            'Yuklenen yakit yanan yakittan az olamaz (sliver negatif olur).')
        assert 0.0 <= results['fuel_sliver_fraction'] < 1.0
        assert engine.D_ch > engine.D_port_initial
        assert engine.D_port_final <= engine.D_ch
