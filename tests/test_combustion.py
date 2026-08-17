"""Yanma analizi fizik regresyon testleri (v2.6.2 fizik denetimi).

Kapsam:
  * F005 — `_fallback_equilibrium_composition`: Cantera YOKKEN kullanılan ürün
    bileşimi. Eski kod itici çiftinden BAĞIMSIZ sabit bir sözlük
    ({'CO2':0.22,'CO':0.08,'H2O':0.12,'N2':0.54,...}) döndürüyordu; LOX/HTPB
    gibi azotsuz bir çiftte bile ürünlerin %54'ü N2 sayılıyor, karışım molekül
    ağırlığı her çiftte 29.6 g/mol'e çakılıyordu. Cantera requirements.txt'te
    OLMADIĞI için bu yol temiz kurulumda VARSAYILANDIR — bu dosyadaki testler
    o yolu (cantera_available=False zorlanarak) doğrudan sınar.
  * F032 — `_calculate_isentropic_efficiency`: eski kurgu payı kayan-denge,
    paydayı donmuş cp tabanında hesapladığı için oran yapısal olarak 1'i aşıyor
    ve [0.8, 1.0] kırpması yüzünden fonksiyon fiilen HER ZAMAN 1.0 döndürüyordu.
  * F034 — `analyze_combustion` çıkış istasyonu: eski kod çıkış basıncını
    SABİT 1.0 bar alıyordu (motorun gerçek genişleme oranından bağımsız).
  * v2.6.27 alev sıcaklığı — `_estimate_flame_temperature`: eski kod
    ``self.gas.HP = h_reactants, p`` ile HP dengesi kuruyordu. Cantera'nın HP
    setter'ı BİLEŞİMİ DONDURUR; 3000 K'de dengelenmiş (ayrışmış) yakıt-zengin
    karışımın donmuş entalpisi hedefe hiçbir T'de inemediği için setter
    CanteraError fırlatıyor, kod SESSİZCE ampirik zarfa düşüyordu (ölçüldü:
    htpb/N2O O/F<=1 noktalarının tamamı). Yeni yol entalpi hedefli kök
    aramasıdır ve düşüş artık BEYANLIDIR. Bu dosyadaki
    `TestAlevSicakligiKaynagiBeyanli` sınıfı hem sayıyı hem beyanı kilitler.

Referans denklemler ve kaynaklar ilgili fonksiyonların docstring'lerindedir.
"""

import ast
import inspect
import pathlib
import textwrap

import numpy as np
import pytest

from hrma.engines.combustion_analysis import CombustionAnalyzer
# Bağımlılık kapısı + kırık-yol teşhis metni TEK KAYNAKTAN gelir; aynı metin
# iki dosyada tanımlanmaz (parti 31 / T2-2).
from tests.bagimlilik_kapisi import kapi
from tests.test_combustion_cea_validation import CANTERA_YOLU_KIRIK


# Ürün türlerinin atom sayıları — element korunumu denetimi için
_SPECIES_ATOMS = {
    'CO2': {'C': 1, 'O': 2},
    'CO': {'C': 1, 'O': 1},
    'H2O': {'H': 2, 'O': 1},
    'H2': {'H': 2},
    'N2': {'N': 2},
    'O2': {'O': 2},
    'AL2O3_l': {'AL': 2, 'O': 3},
    'AL2O3_s': {'AL': 2, 'O': 3},
    'AL': {'AL': 1},
}


@pytest.fixture()
def empirical():
    """Cantera'sız (temiz kurulum) davranışını zorlayan analizör."""
    ca = CombustionAnalyzer()
    ca.cantera_available = False
    ca.gas = None
    return ca


def _fallback_chamber(analyzer, fuel, oxidizer, of_ratio,
                      pressure=20.0, temperature=3300.0):
    elements = analyzer._calculate_elemental_composition(fuel, oxidizer, of_ratio)
    comp = analyzer._fallback_equilibrium_composition(
        elements, pressure, temperature, 'chamber')
    return elements, comp


def _mole_fractions(comp):
    return {sp: d['mole_fraction'] for sp, d in comp['species'].items()}


class TestFallbackCompositionDependsOnPropellants:
    """F005: bileşim artık itici çiftinden türüyor, sabit sözlükten değil."""

    def test_nitrogen_free_pair_has_no_nitrogen(self, empirical):
        """LOX/HTPB azot İÇERMEZ; eski sabit sözlük %54 N2 veriyordu."""
        _, comp = _fallback_chamber(empirical, {'htpb': 100}, 'lox', 2.0)
        x = _mole_fractions(comp)
        assert 'N2' not in x, f"Azotsuz çiftte N2 üretildi: {x}"

    def test_nitrous_pair_does_contain_nitrogen(self, empirical):
        """N2O/HTPB'de N2 baskın üründür (oksitleyicinin kütlece 2/3'ü azot)."""
        _, comp = _fallback_chamber(empirical, {'htpb': 100}, 'n2o', 6.0)
        x = _mole_fractions(comp)
        assert x.get('N2', 0.0) > 0.4

    def test_molecular_weight_is_not_pinned(self, empirical):
        """MW her çiftte 29.6 g/mol'e çakılmıyor; çift başına farklı çıkıyor."""
        cases = [
            ({'htpb': 100}, 'lox', 2.0),
            ({'htpb': 100}, 'n2o', 6.0),
            ({'paraffin': 100}, 'lox', 2.5),
            ({'pmma': 100}, 'lox', 1.5),
            ({'pe': 100}, 'h2o2', 5.0),
        ]
        mws = [_fallback_chamber(empirical, *c)[1]['molecular_weight']
               for c in cases]
        assert len(set(round(m, 3) for m in mws)) == len(mws), (
            f"MW değerleri ayrışmıyor: {mws}")
        # Eski davranışın imzası: hepsi 29.6'ya çakılıydı
        assert not all(abs(m - 29.6) < 0.5 for m in mws)

    @pytest.mark.parametrize("fuel,ox,of,mw_lo,mw_hi", [
        # CEA gerçek değerleri (PHYSICS_AUDIT F005 ölçümü): htpb/lox 22.0,
        # htpb/n2o 25.5. Atom dengesi ayrışmayı modellemediği için MW'yi
        # sistematik ~%2 YÜKSEK verir; bant bunu kapsar.
        ({'htpb': 100}, 'lox', 2.0, 21.5, 24.0),
        ({'htpb': 100}, 'n2o', 6.0, 25.0, 27.0),
    ])
    def test_molecular_weight_near_cea(self, empirical, fuel, ox, of, mw_lo, mw_hi):
        _, comp = _fallback_chamber(empirical, fuel, ox, of)
        assert mw_lo <= comp['molecular_weight'] <= mw_hi


class TestFallbackAtomBalance:
    """F005: ürünler elemental girdiyi korumalı (kütle/atom korunumu)."""

    @pytest.mark.parametrize("fuel,ox,of", [
        ({'htpb': 100}, 'lox', 2.0),
        ({'htpb': 100}, 'n2o', 6.0),
        ({'htpb': 100}, 'lox', 5.0),          # yakıt-fakir
        ({'htpb': 80, 'aluminum': 20}, 'lox', 2.0),
        ({'pmma': 100}, 'lox', 1.5),
    ])
    def test_element_mass_is_conserved(self, empirical, fuel, ox, of):
        elements, comp = _fallback_chamber(empirical, fuel, ox, of)
        mw = comp['molecular_weight']
        atomic = empirical._ATOMIC_MASS
        recovered = {el: 0.0 for el in atomic}
        for sp, x in _mole_fractions(comp).items():
            for el, n in _SPECIES_ATOMS[sp].items():
                recovered[el] += x * n * atomic[el] / mw
        for el, target in elements.items():
            # Bağıl tolerans %0.5: girdideki yaklaşık monomer MW'leri
            # (ör. HTPB 54.0 vs 54.1) zaten bu mertebede sapma taşıyor.
            assert recovered[el] == pytest.approx(target, abs=1e-3, rel=5e-3), (
                f"{el} korunmadı: girdi {target:.6f}, ürünlerde {recovered[el]:.6f}")

    def test_fuel_lean_produces_excess_oxygen_and_no_co(self, empirical):
        """Oksijen fazlasında tam oksidasyon: CO2+H2O+artık O2, CO yok."""
        _, comp = _fallback_chamber(empirical, {'htpb': 100}, 'lox', 5.0)
        x = _mole_fractions(comp)
        assert x.get('O2', 0.0) > 0.05
        assert 'CO' not in x and 'H2' not in x

    def test_fuel_rich_produces_co_and_h2(self, empirical):
        """Yakıt-zenginde su-gaz kayması CO ve H2 üretir."""
        _, comp = _fallback_chamber(empirical, {'htpb': 100}, 'lox', 2.0)
        x = _mole_fractions(comp)
        assert x.get('CO', 0.0) > x.get('CO2', 0.0)
        assert x.get('H2', 0.0) > 0.0

    def test_water_gas_shift_constant_is_satisfied(self, empirical):
        """K(T) = (X_CO2·X_H2)/(X_CO·X_H2O) tanımı çözümde birebir sağlanmalı."""
        T = 3300.0
        _, comp = _fallback_chamber(empirical, {'htpb': 100}, 'lox', 2.0,
                                    temperature=T)
        x = _mole_fractions(comp)
        k_solved = (x['CO2'] * x['H2']) / (x['CO'] * x['H2O'])
        k_expected = float(np.exp(empirical._WGS_LNK_A / T + empirical._WGS_LNK_B))
        assert k_solved == pytest.approx(k_expected, rel=1e-6)

    def test_aluminium_is_oxidised_to_alumina(self, empirical):
        """Metalize yakıtta Al2O3 üretilir; yanma sıcaklığında sıvı fazdadır."""
        _, comp = _fallback_chamber(empirical, {'htpb': 80, 'aluminum': 20},
                                    'lox', 2.0, temperature=3300.0)
        x = _mole_fractions(comp)
        assert x.get('AL2O3_l', 0.0) > 0.0
        assert 'AL2O3_s' not in x  # 3300 K > 2327 K ergime noktası

    def test_alumina_is_solid_below_melting_point(self, empirical):
        _, comp = _fallback_chamber(empirical, {'htpb': 80, 'aluminum': 20},
                                    'lox', 2.0, temperature=2000.0)
        assert 'AL2O3_s' in _mole_fractions(comp)


class TestFallbackFailsClosed:
    """F005: türetilemeyen girdide sessizce sahte bileşim döndürülmemeli."""

    def test_empty_elements_raise(self, empirical):
        with pytest.raises(ValueError):
            empirical._fallback_equilibrium_composition(
                {'C': 0.0, 'H': 0.0, 'O': 0.0, 'N': 0.0, 'AL': 0.0},
                20.0, 3300.0, 'chamber')

    def test_unsupported_propellant_raises(self, empirical):
        with pytest.raises(ValueError):
            empirical._calculate_elemental_composition(
                {'unobtainium': 100}, 'lox', 2.0)
        with pytest.raises(ValueError):
            empirical._calculate_elemental_composition(
                {'htpb': 100}, 'unobtainium', 2.0)

    def test_fallback_is_flagged_to_the_user(self, empirical):
        """Atom-dengesi yolu kullanıcıya görünür uyarı taşımalı (kod sözleşmesi)."""
        _, comp = _fallback_chamber(empirical, {'htpb': 100}, 'lox', 2.0)
        assert comp['source'] == 'atom_balance_fallback'
        warn = comp['warning']
        assert warn['code'] == 'warn.combustion.equilibrium_fallback'
        assert warn['severity'] == 'warning'
        assert warn['params']['station'] == 'chamber'


class TestFallbackContractMatchesCantera:
    """Fallback sözlüğü Cantera yolunun anahtarlarını birebir taşımalı.

    (2026-07-12 saha hatası: eski fallback düz tür-kesri sözlüğü döndürüyor,
    tüketiciler comp['gamma'] okuduğu için Cantera'sız makinelerde /calculate
    KeyError('gamma') ile 400 dönüyordu.)
    """

    REQUIRED = ('species', 'temperature', 'pressure', 'density',
                'molecular_weight', 'cp', 'cv', 'gamma', 'gamma_frozen',
                'enthalpy', 'entropy')

    def test_keys_present(self, empirical):
        _, comp = _fallback_chamber(empirical, {'htpb': 100}, 'n2o', 6.0)
        for key in self.REQUIRED:
            assert key in comp, f"Fallback sözleşmesinde '{key}' eksik"

    def test_thermo_scalars_are_consistent(self, empirical):
        _, comp = _fallback_chamber(empirical, {'htpb': 100}, 'n2o', 6.0,
                                    pressure=20.0, temperature=3300.0)
        R = empirical.R_universal / comp['molecular_weight']
        assert comp['cp'] - comp['cv'] == pytest.approx(R, rel=1e-9)
        assert comp['cp'] / comp['cv'] == pytest.approx(comp['gamma'], rel=1e-9)
        # İdeal gaz: rho = p/(R·T)
        assert comp['density'] == pytest.approx(20.0e5 / (R * 3300.0), rel=1e-9)
        assert 1.18 <= comp['gamma'] <= 1.33

    def test_end_to_end_analysis_runs_without_cantera(self, empirical):
        """Cantera'sız tam analiz çalışmalı ve çift başına farklı c* vermeli."""
        r1 = empirical.analyze_combustion({'htpb': 100}, 'n2o', 6.0, 20.0,
                                          expansion_ratio=10.0)
        r2 = empirical.analyze_combustion({'htpb': 100}, 'lox', 2.0, 20.0,
                                          expansion_ratio=10.0)
        assert r1['performance']['c_star'] > 0
        assert abs(r1['performance']['c_star']
                   - r2['performance']['c_star']) > 20.0


class TestExitStationFollowsExpansionRatio:
    """F034: çıkış istasyonu sabit 1.0 bar değil, ε'dan çözülüyor."""

    def test_basis_flag_reports_the_source(self, empirical):
        r_default = empirical.analyze_combustion({'htpb': 100}, 'n2o', 6.0, 20.0)
        assert r_default['conditions']['exit']['basis'] == 'sea_level_default'
        r_eps = empirical.analyze_combustion({'htpb': 100}, 'n2o', 6.0, 20.0,
                                             expansion_ratio=25.0)
        assert r_eps['conditions']['exit']['basis'] == 'expansion_ratio'

    def test_exit_pressure_decreases_with_expansion_ratio(self, empirical):
        pressures = [
            empirical.analyze_combustion({'htpb': 100}, 'n2o', 6.0, 20.0,
                                         expansion_ratio=float(eps)
                                         )['conditions']['exit']['P']
            for eps in (4, 10, 25, 60)
        ]
        assert all(a > b for a, b in zip(pressures, pressures[1:])), pressures

    def test_exit_pressure_matches_isentropic_area_relation(self, empirical):
        """p_e, alan-Mach + izentropik basınç bağıntısıyla birebir tutmalı."""
        gamma = 1.22
        pc, eps = 20.0, 25.0
        p_e = empirical._exit_pressure_from_expansion(eps, gamma, pc)
        # Ters kontrol: p_e'den Mach, Mach'ten alan oranı
        m_e = np.sqrt(2.0 / (gamma - 1.0)
                      * ((pc / p_e) ** ((gamma - 1.0) / gamma) - 1.0))
        exponent = (gamma + 1.0) / (2.0 * (gamma - 1.0))
        eps_back = (1.0 / m_e) * ((2.0 / (gamma + 1.0))
                                  * (1.0 + 0.5 * (gamma - 1.0) * m_e ** 2)) ** exponent
        assert eps_back == pytest.approx(eps, rel=1e-6)

    def test_sea_level_anchor_is_isa_not_one_bar(self, empirical):
        """Çapa ISA deniz seviyesi 1.01325 bar; eski kod 1.0 yazıyordu."""
        r = empirical.analyze_combustion({'htpb': 100}, 'n2o', 6.0, 20.0)
        assert r['conditions']['exit']['P'] == pytest.approx(1.01325, rel=1e-6)


class TestIsentropicEfficiency:
    """F032: verim artık kırpmayla 1.0'a sabitlenmiyor."""

    def _eta(self, analyzer, **kw):
        r = analyzer.analyze_combustion({'htpb': 100}, 'n2o', 6.0, 20.0, **kw)
        return r['performance']['thermodynamic_properties']['isentropic_efficiency']

    def test_definition_is_entropy_based(self, empirical):
        """eta = Δh / (Δh + T_e·Δs) — istasyon tablosundan birebir türemeli."""
        props = {
            'chamber': {'enthalpy': 0.0, 'entropy': 8.0, 'temperature': 3300.0},
            'exit': {'enthalpy': -2400.0, 'entropy': 8.2, 'temperature': 1500.0},
        }
        eta = empirical._calculate_isentropic_efficiency(props)
        expected = 2400.0 / (2400.0 + 1500.0 * 0.2)
        assert eta == pytest.approx(expected, rel=1e-12)
        assert eta < 1.0  # kırpma YOK: entropi üretimi verimi düşürür

    def test_ideal_expansion_gives_unity(self, empirical):
        props = {
            'chamber': {'enthalpy': 0.0, 'entropy': 8.0, 'temperature': 3300.0},
            'exit': {'enthalpy': -2400.0, 'entropy': 8.0, 'temperature': 1500.0},
        }
        assert empirical._calculate_isentropic_efficiency(props) == pytest.approx(1.0)

    def test_negative_entropy_generation_is_capped_at_unity(self, empirical):
        """s_e < s_c fiziksel değil (model tutarsızlığı): üst sınır 1.0."""
        props = {
            'chamber': {'enthalpy': 0.0, 'entropy': 8.0, 'temperature': 3300.0},
            'exit': {'enthalpy': -2400.0, 'entropy': 7.5, 'temperature': 1500.0},
        }
        assert empirical._calculate_isentropic_efficiency(props) == 1.0

    def test_no_expansion_is_undefined_not_fabricated(self, empirical):
        props = {
            'chamber': {'enthalpy': 0.0, 'entropy': 8.0, 'temperature': 3300.0},
            'exit': {'enthalpy': 0.0, 'entropy': 8.0, 'temperature': 3300.0},
        }
        assert empirical._calculate_isentropic_efficiency(props) == 1.0

    def test_lower_clip_at_08_is_gone(self, empirical):
        """Eski kod alt sınırı 0.8'e kırpıyordu; artık gerçek değer geçmeli."""
        props = {
            'chamber': {'enthalpy': 0.0, 'entropy': 8.0, 'temperature': 3300.0},
            'exit': {'enthalpy': -1000.0, 'entropy': 8.5, 'temperature': 1500.0},
        }
        eta = empirical._calculate_isentropic_efficiency(props)
        assert eta == pytest.approx(1000.0 / (1000.0 + 750.0), rel=1e-12)
        assert eta < 0.8

    def test_with_cantera_value_is_informative(self):
        """Cantera varken verim 1.0'a çakılmamalı ve ε ile azalmalı.

        Ölçüldü (htpb/n2o O/F=6, Pc=20 bar): ε=4 -> 0.9314, ε=10 -> 0.8917,
        ε=25 -> 0.8738, ε=60 -> 0.8669. Eski kurgu hepsinde 1.0 veriyordu.
        """
        ca = CombustionAnalyzer()
        # Bağımlılık kapısı (parti 31 / T2-2): cantera YOKSA atla, KURULU ama
        # mekanizma zinciri yüklenemiyorsa KIRMIZI — ürün kusuru atlanamaz.
        kapi('cantera', ca.cantera_available, CANTERA_YOLU_KIRIK)
        etas = [self._eta(ca, expansion_ratio=float(eps)) for eps in (4, 10, 25, 60)]
        assert all(0.5 < e < 1.0 for e in etas), etas
        assert all(a > b for a, b in zip(etas, etas[1:])), etas


# ---------------------------------------------------------------------------
# v2.6.27 — Adyabatik alev sıcaklığı: hem SAYI hem KAYNAK BEYANI kilitlenir
# ---------------------------------------------------------------------------
CA_SOURCE_PATH = pathlib.Path(
    inspect.getsourcefile(CombustionAnalyzer)).resolve()


@pytest.fixture(scope='module')
def denge():
    """Gerçek Cantera'lı analizör (denge yolu sınanacak)."""
    ca = CombustionAnalyzer()
    # Bağımlılık kapısı (parti 31 / T2-2), yukarıdakiyle aynı gerekçe.
    kapi('cantera', ca.cantera_available, CANTERA_YOLU_KIRIK)
    return ca


def _oda(analyzer, of_ratio, pressure=30.0):
    return analyzer.analyze_combustion(
        {'htpb': 100.0}, 'n2o', float(of_ratio), float(pressure)
    )['conditions']['chamber']


class TestAlevSicakligiKaynagiBeyanli:
    """Sıcaklığın nereden geldiği kullanıcıdan gizlenemez."""

    def test_of1_denge_cozumunden_gelir(self, denge):
        """O/F=1.0 htpb/N2O 30 bar — ESKİ kodun sessizce düştüğü nokta.

        Eski HP yolu burada CanteraError alıp ampirik zarfa (1277.3 K)
        düşüyordu ve bunu yalnız sunucu günlüğüne yazıyordu. Entalpi hedefli
        kök araması aynı noktada gerçek denge sıcaklığını buluyor: ölçüldü,
        1137.45 K (gri30, p=30 bar). Tolerans ±25 K mekanizma/sürüm oynaması
        içindir; ampirik değere (1277.3 K) 140 K uzaktır, yani bu test
        düşüşü ayırt eder.
        """
        oda = _oda(denge, 1.0)
        assert oda['temperature_source'] == 'equilibrium'
        assert oda['T'] == pytest.approx(1137.5, abs=25.0), oda['T']
        assert 'warning' not in oda, 'denge yolunda uyarı taşınmamalı'

    def test_of03_ampirik_zarf_beyanli(self, denge):
        """O/F=0.3'te denge kökü YOK (gri30'da katı karbon yok) — düşüş beyanlı.

        Sayının kendisi ampirik olabilir; kabul edilemez olan, ampirik değerin
        beyansız (denge çözümüymüş gibi) ekrana çıkmasıdır.
        """
        oda = _oda(denge, 0.3)
        assert oda['temperature_source'] == 'empirical_envelope'
        uyari = oda['warning']
        assert uyari['code'] == 'warn.combustion.flame_temperature_empirical'
        assert uyari['severity'] == 'warning'
        assert uyari['params']['reason'] in {
            'cantera_unavailable', 'missing_formation_enthalpy',
            'no_enthalpy_root', 'solver_error', 'nonphysical_temperature'}
        assert uyari['params']['of_ratio'] == pytest.approx(0.3)

    def test_hp_yolunun_yakinsadigi_nokta_kaymadi(self, denge):
        """Eşdeğerlik çapası: HP'nin BUGÜN çözdüğü noktada değer kımıldamaz.

        HEAD'in HP yolu O/F=4.0 / 30 bar'da yakınsıyor ve 2821.1299938218 K
        veriyor (ölçüldü, aynı gri30 sürümüyle). Kök araması aynı denklemi
        çözdüğü için aynı kökü bulmalıdır: ölçülen fark 2.5e-09 K. Eşik
        0.5 K — sayısal gürültüye yer bırakır, yöntem değişikliğini yakalar.
        """
        oda = _oda(denge, 4.0)
        assert oda['temperature_source'] == 'equilibrium'
        assert oda['T'] == pytest.approx(2821.1299938218, abs=0.5), oda['T']

    def test_cagiranin_dayattigi_sicaklik_denge_sayilmaz(self, denge):
        """chamber_temperature verildiğinde hiçbir alev çözümü yapılmaz."""
        r = denge.analyze_combustion({'htpb': 100.0}, 'n2o', 6.0, 30.0, 2800.0)
        assert r['conditions']['chamber']['temperature_source'] == \
            'user_specified'

    def test_cantera_yokken_de_beyan_var(self, empirical):
        """Ampirik kurulumda da alan DOLU olmalı (sessiz boşluk yok)."""
        oda = _oda(empirical, 6.0)
        assert oda['temperature_source'] == 'empirical_envelope'
        assert oda['warning']['params']['reason'] == 'cantera_unavailable'


class TestMekanizmaBeyani:
    """Denge arka ucunun kimliği çıktının parçasıdır."""

    def test_mekanizma_alanlari_sonucta(self, denge):
        r = denge.analyze_combustion({'htpb': 100.0}, 'n2o', 6.0, 30.0)
        assert r['mechanism'] == denge._mechanism_id
        assert r['mechanism'] in {'gri30', 'h2o2'}
        tavan = r['mechanism_T_ceiling_K']
        # Termo tavanı türlerin EN DÜŞÜK max_temp'idir; ölçüldü: gri30 ->
        # 3000 K (CH3O), h2o2 -> 3500 K. Bant, mekanizma değişse de anlamlı
        # kalsın diye geniş tutuldu.
        assert 2000.0 <= tavan <= 6000.0, tavan
        assert tavan == pytest.approx(
            min(sp.thermo.max_temp for sp in denge.gas.species()))

    def test_cantera_yokken_mekanizma_uydurulmaz(self, empirical):
        r = empirical.analyze_combustion({'htpb': 100.0}, 'n2o', 6.0, 30.0)
        assert r['mechanism'] == 'empirical'
        assert r['mechanism_T_ceiling_K'] is None


class TestOluDallarGeriGelmemis:
    """Kaldırılan ölü kodun geri sızmadığını kilitler."""

    def test_nasa_gas_dali_kaynakta_gecmiyor(self):
        """'nasa_gas.yaml' bir TÜR veritabanıdır ('phases:' yoktur).

        ct.Solution ile HİÇBİR koşulda yüklenemez; zincirin ilk basamağı
        olarak durduğu sürece "önce NASA-CEA veritabanı denenir" yalanını
        üretir ve gerçekte her zaman gri30 kullanılır.
        """
        kaynak = CA_SOURCE_PATH.read_text(encoding='utf-8')
        assert 'nasa_gas' not in kaynak, (
            'ölü NASA tür-veritabanı dalı geri gelmiş: %s' % CA_SOURCE_PATH)

    def test_hp_setter_geri_gelmemis(self):
        """Bekçinin Cantera'sız CI'da da çalışan yedeği.

        Davranış testleri (yukarıdaki O/F=1.0) Cantera yoksa atlanır; bu
        denetim atlanmaz. AST üstünde çalışır, yani docstring'deki
        ``self.gas.HP = ...`` anlatımına ALDANMAZ — yalnız gerçek atama
        düğümünü arar.
        """
        agac = ast.parse(textwrap.dedent(inspect.getsource(
            CombustionAnalyzer._estimate_flame_temperature)))
        for dugum in ast.walk(agac):
            if not isinstance(dugum, ast.Assign):
                continue
            for hedef in dugum.targets:
                assert not (isinstance(hedef, ast.Attribute)
                            and hedef.attr in {'HP', 'UV'}), (
                    'donmuş-bileşim HP/UV setter yolu geri gelmiş')
