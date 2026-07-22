"""Uydurma veri bekçisi (v2.5.2).

Berke'nin 2026-07-19 uyarısı: "hiçbir şey uydurma olamaz". O gün elle iki
vaka bulundu ve düzeltildi:

  1. cad_visualization._add_performance_chart sabit tasarım itkisine %10'luk
     yapay bir doğrusal düşüş ekleyip bunu "itki eğrisi" diye teknik çizime
     basıyordu. Kullanıcı hesaplanmış bir eğri sanıyordu.
  2. visualization.py enjektör şemasında her deliğin hızına ve Reynolds
     sayısına np.random ile gürültü ekliyordu. Kullanıcı hover'da delikler
     arası gerçek bir dağılım gördüğünü sanıyordu; model tüm delikleri eşit
     kabul ediyor.

Bu dosya o sınıfın geri gelmesini engeller. Tek ölçüt:

    "Kullanıcı bu sayının kendi girdisinden hesaplandığına inanır mı?
     İnanıyorsa, gerçekten hesaplanmalı."

Kapsam dışı (meşru rastgelelik): belirsizlik/Monte Carlo modülleri rastgele
örneklem ÜRETMEK için vardır, orada tohumlanmış rastgelelik amaçtır.
"""

import re
import warnings
from pathlib import Path

import pytest

warnings.filterwarnings('ignore')

REPO = Path(__file__).resolve().parents[1]
PKG = REPO / 'hrma'

# Rastgeleliğin MEŞRU olduğu modüller: işleri örneklem üretmek.
RANDOM_ALLOWED = {
    'hrma/analysis/uncertainty.py',
    'hrma/analysis/uq_adapters.py',
}
# Monte Carlo örnekleyicileri motor sınıflarının içinde de olabilir; orada
# yalnız TOHUMLANMIŞ üreteç (default_rng(seed)) kabul edilir — tekrarlanabilir
# olmayan global np.random.* çağrısı değil.
SEEDED_RNG = re.compile(r'default_rng\s*\(')
GLOBAL_RANDOM = re.compile(r'np\.random\.(randn|rand|normal|uniform|choice|randint)\s*\(')


def _py_files():
    for path in sorted(PKG.rglob('*.py')):
        rel = path.relative_to(REPO).as_posix()
        if '__pycache__' in rel:
            continue
        yield rel, path


class TestNoUnseededRandomInResults:
    """Sonuç yolunda tohumsuz rastgelelik olamaz."""

    def test_no_global_np_random_in_result_paths(self):
        offenders = []
        for rel, path in _py_files():
            if rel in RANDOM_ALLOWED:
                continue
            text = path.read_text(encoding='utf-8')
            for match in GLOBAL_RANDOM.finditer(text):
                line_no = text[:match.start()].count('\n') + 1
                line = text.splitlines()[line_no - 1].strip()
                # Tohumlanmış üreteçten türeyen çağrılar (rng.normal gibi)
                # bu desene zaten uymaz; yine de yorum satırını atla.
                if line.startswith('#'):
                    continue
                offenders.append(f'{rel}:{line_no}: {line}')
        assert not offenders, (
            'Sonuc yolunda tohumsuz rastgelelik bulundu. Kullaniciya sunulan '
            'bir sayi calisma arasinda degisiyorsa hesaplanmis degildir:\n  '
            + '\n  '.join(offenders))

    def test_monte_carlo_uses_seeded_generator(self):
        """Meşru rastgelelik kullanan yerler tohumlanmış üreteç kullanmalı."""
        sampler = PKG / 'engines' / 'solid_rocket_engine.py'
        text = sampler.read_text(encoding='utf-8')
        if 'monte_carlo' in text.lower():
            assert SEEDED_RNG.search(text), (
                'Monte Carlo tohumlanmis ureteç kullanmali (tekrarlanabilirlik).')


class TestInputsActuallyDriveOutputs:
    """Kullanıcı girdisi çıktıyı gerçekten değiştirmeli.

    Bugün iki 'ölü girdi' bulundu: enjektör basınç düşümü override'ı ve katı
    motorun hedef itkisi kullanıcıdan alınıp hesaba hiç sokulmuyordu. Bu
    sınıf ana girdiler için duyarlılık bekçisidir.
    """

    @staticmethod
    def _hybrid(**overrides):
        from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
        params = dict(thrust=1000, burn_time=10, of_ratio=6.0,
                      chamber_pressure=20.0)
        params.update(overrides)
        return HybridRocketEngine(**params).calculate()

    def test_chamber_pressure_changes_geometry(self):
        low = self._hybrid(chamber_pressure=15.0)
        high = self._hybrid(chamber_pressure=45.0)
        assert low['throat_diameter'] != high['throat_diameter'], \
            'Oda basinci bogaz capini degistirmeli'

    def test_of_ratio_changes_flow_split(self):
        lean = self._hybrid(of_ratio=4.0)
        rich = self._hybrid(of_ratio=8.0)
        assert lean['mdot_ox'] != rich['mdot_ox'], 'O/F oksitleyici debisini degistirmeli'
        assert lean['mdot_f'] != rich['mdot_f'], 'O/F yakit debisini degistirmeli'

    def test_thrust_target_changes_size(self):
        small = self._hybrid(thrust=500)
        large = self._hybrid(thrust=5000)
        assert large['throat_diameter'] > small['throat_diameter'], \
            'Hedef itki motor boyutunu buyutmeli'

    def test_injector_type_reaches_results(self):
        """Enjektör tipi motor sonucuna ulaşmalı (eskiden 'showerhead' sabitti)."""
        shower = self._hybrid(injector_type='showerhead')
        swirl = self._hybrid(injector_type='swirl')
        assert shower['injector_design']['injector_type'] == 'showerhead'
        assert swirl['injector_design']['injector_type'] == 'swirl'

    def test_tank_temperature_reaches_injector(self):
        """Tank sıcaklığı N2O enjektör tasarımını değiştirmeli."""
        cold = self._hybrid(tank_temperature=263.15)
        warm = self._hybrid(tank_temperature=303.15)
        cold_area = cold['injector_design']['total_injector_area_mm2']
        warm_area = warm['injector_design']['total_injector_area_mm2']
        # Soğuk tankta doyma basıncı düşer, aynı debiyi geçirmek için daha
        # büyük alan gerekir. 263 K -> 22.96 mm2, 303 K -> 8.62 mm2.
        assert cold_area > warm_area * 1.5, (
            f'Tank sicakligi enjektor alanini degistirmeli (N2O doyma '
            f'basinci): 263 K={cold_area:.2f} mm2, 303 K={warm_area:.2f} mm2')


class TestChartsCarryComputedData:
    """Grafiklere giren seriler çözücü çıktısından gelmeli."""

    def test_cad_performance_chart_labels_its_assumption(self):
        """Gerçek eğri yoksa çizilen seri VARSAYIM olduğunu söylemeli."""
        source = (PKG / 'export' / 'cad_visualization.py').read_text(encoding='utf-8')
        assert 'constant-thrust assumption' in source, (
            'Gercek egri yokken cizilen itki serisi, varsayim oldugunu '
            'etiketiyle belirtmeli (eski surum uydurma bir dusus egrisi cizip '
            'hesaplanmis gibi gosteriyordu).')
        assert '0.1 * time' not in source, \
            'Yapay itki dususu geri gelmis'

    def test_injector_hover_reports_design_values(self):
        """Enjektör hover'ı uydurulmuş delik-başı sapma göstermemeli."""
        source = (PKG / 'visualization' / 'visualization.py').read_text(encoding='utf-8')
        assert 'np.random.randn' not in source, (
            'Enjektor hover metninde rastgele sapma geri gelmis; model tum '
            'delikleri esit kabul ediyor, sunum da oyle olmali.')


class TestFallbacksAreLabelled:
    """Hesap düşerse sonuç sessizce 'normal' görünmemeli."""

    def test_optimum_of_rejects_undefined_pair(self):
        """Desteklenmeyen propellant çiftinde sessiz varsayılan dönmemeli."""
        from hrma.app import app
        client = app.test_client()
        resp = client.post('/api/find-optimum-of', json={
            'motor_type': 'hybrid', 'oxidizer': 'custom', 'fuel': 'custom',
            'chamber_pressure': 20.0,
        })
        assert resp.status_code == 400, \
            'Tanimsiz propellant ciftinde optimum O/F uydurulmamali'
        assert 'error' in resp.get_json()

    def test_structural_reports_thermal_margin(self):
        """Emniyet durumu sıcaklık marjını da yansıtmalı."""
        from hrma.analysis.structural_analysis import StructuralAnalyzer
        res = StructuralAnalyzer().analyze_structure({
            'chamber_pressure': 50, 'chamber_diameter': 0.15,
            'chamber_length': 0.6, 'throat_diameter': 0.05,
            'burn_time': 10, 'chamber_temperature': 3000,
        }, material='steel_4130')
        safety = res['safety_analysis']
        assert safety.get('thermal_margin_ratio') is not None, \
            'Cidar sicakligi / servis siniri orani raporlanmali'
        assert safety['status'] != 'SAFE', (
            'Cidari servis sinirinin %90 seviyesinde olan motor SAFE gorunmemeli')

class TestPropertyEndpointsReportProvenance:
    """Özellik uçları kaynağı hakkında yalan söylememeli."""

    def test_unknown_compound_does_not_fabricate_heat_of_formation(self):
        """Formülden türetilemeyen büyüklük uydurulmamalı.

        Eski sürüm bilinmeyen bir bileşiğin oluşum entalpisini SERBEST
        ATOMLARIN entalpilerini toplayarak buluyordu (C: +716.68, H: +217.97
        kJ/mol). C4H6O2 için +4062 kJ/mol dönüyordu; gerçek değer -430
        mertebesinde, yani hem büyüklük hem işaret yanlıştı. Üstelik yanıt
        'NASA CEA Database' diye etiketleniyordu.
        """
        from hrma.app import app
        client = app.test_client()
        resp = client.post('/api/validate-fuel', json={
            'composition': [{'formula': 'C4H6O2', 'percentage': 100.0}]})
        assert resp.status_code == 200
        data = resp.get_json()
        props = data['mixture_properties']

        # Molekül ağırlığı formülden GERÇEKTEN türetilebilir, o kalmalı.
        assert props['molecular_weight'] == pytest.approx(86.09, abs=0.05)
        # Oluşum entalpisi türetilemez -> uydurma yerine None + açıklama.
        assert props['heat_of_formation'] is None
        assert 'cannot be derived' in (props['heat_of_formation_note'] or '')
        # Kaynak atfı gerçeği söylemeli: CEA tablosundan gelmiyor.
        assert 'NASA CEA Database' != data['source']
        assert 'formula' in data['source'].lower()

    def test_known_species_reports_cea_table(self):
        from hrma.app import app
        client = app.test_client()
        resp = client.post('/api/validate-fuel', json={
            'composition': [{'formula': 'CH4', 'percentage': 100.0}]})
        data = resp.get_json()
        assert data['mixture_properties']['heat_of_formation'] == pytest.approx(-74.85, abs=0.1)
        assert 'CEA' in data['source']

    def test_mixture_density_is_not_invented(self):
        """Bileşen yoğunluğu bilinmiyorsa karışım yoğunluğu uydurulmamalı."""
        from hrma.app import app
        client = app.test_client()
        data = client.post('/api/validate-fuel', json={
            'composition': [{'formula': 'C4H6O2', 'percentage': 100.0}]}).get_json()
        props = data['mixture_properties']
        assert props['density'] is None
        assert 'unavailable' in props['density_method']


class TestCryogenicPropertiesUseStorageState:
    """Kriyojenik iticiler depolama durumunda sorgulanmalı."""

    @pytest.mark.parametrize('fluid,expected_density', [
        ('lox', 1141.0),
        ('lh2', 70.8),
        ('methane', 422.6),
    ])
    def test_cryogen_returns_liquid_density(self, fluid, expected_density):
        """Eski sürüm 298 K / 1 atm soruyordu; LOX 90 K'de kaynar, yani
        dönen değer GAZ yoğunluğuydu (1.3 kg/m3). Tank hacmi ~870 kat yanlış
        çıkıyordu."""
        from hrma.data.open_source_propellant_api import OpenSourcePropellantAPI
        props = OpenSourcePropellantAPI().get_coolprop_properties(fluid)
        density = props.get('density')
        if density is None:
            pytest.skip('CoolProp bu ortamda kullanilamiyor')
        assert density == pytest.approx(expected_density, rel=0.02), (
            f'{fluid} sivi yogunlugu bekleniyor, {density:.2f} kg/m3 geldi')
        assert 'liquid' in (props.get('phase') or '')
        assert 'saturated liquid' in (props.get('state') or '')

    def test_user_specified_temperature_reports_actual_phase(self):
        """Kullanıcı oda sıcaklığı dayatırsa fazı DÜRÜSTÇE söylemeli."""
        from hrma.data.open_source_propellant_api import OpenSourcePropellantAPI
        props = OpenSourcePropellantAPI().get_coolprop_properties(
            'lox', temperature=298.15, pressure=101325)
        if props.get('phase') is None:
            pytest.skip('CoolProp bu ortamda kullanilamiyor')
        assert 'gas' in props['phase']
        assert 'user-specified' in (props.get('state') or '')
