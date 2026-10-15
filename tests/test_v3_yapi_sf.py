"""V3 yapi-sf bekçileri (7 Eki 2026, karar §28-21).

Kök neden (ölçüldü, main 393960ce, örnek "Example Hybrid N2O-HTPB 3kN"):

* Kamara cidarı 23,08 mm ``sizing_feasible = True`` ile "SF 4 hedefiyle
  boyutlandırıldı" diye yayımlanıyor, aynı cidarda ``safety_factor_total``
  0,8267 yayımlanıyordu. Boyutlandırma yalnız BASINÇ hoop gerilmesini hedefe
  oturtuyor (14,375 MPa → SF 4,80), yayımlanan SF ise ısıl hoop gerilmesini
  (69,09 MPa) de taşıyordu.
* Aynı yanıtta üç lüle kütlesi: 0,4275 kg (CAD dökümü), 0,3248 kg
  (``nozzle_geometry.estimated_mass``) ve 24,78 kg (kütle dökümünde kamara
  kütlesinin %30'u).

Sözleşmeler:

1. Boyutlandırılmış cidar AYNI modelde kendi hedefini tutturur ya da
   ``sizing_feasible = False`` + gerekçe basar (fail-closed).
2. Aynı yanıtta bir bileşenin TEK kütlesi vardır (lüle: çizilen katı).
"""

import json
import math
import pathlib

import numpy as np
import pytest

from hrma.analysis.structural_analysis import (
    MANUFACTURING_ALLOWANCE_FACTOR, THIN_WALL_T_OVER_R_LIMIT,
    StructuralAnalyzer)
from hrma.data.materials_db import build_materials_view

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Hazne yükü: 20 bar MEOP (tasarım çarpanı 1,5 → 3 MPa), Ø100 mm.
_MOTOR = {'chamber_pressure': 20.0, 'chamber_diameter': 0.1,
          'chamber_length': 0.5, 'throat_diameter': 0.02,
          'ambient_temperature': 293.15}
_DESIGN_PRESSURE_FACTOR = 1.5
_TARGET_SF = 4.0
_REF_WALL_M = 0.004


def _motor(t_hot, t_cold, ref=_REF_WALL_M):
    m = dict(_MOTOR, wall_temperature_hot=t_hot, wall_temperature_cold=t_cold)
    if ref is not None:
        m['wall_temperature_reference_thickness'] = ref
    return m


def _size(motor, material='steel_4130'):
    return StructuralAnalyzer().analyze_structure(
        motor, material=material,
        design_pressure_factor=_DESIGN_PRESSURE_FACTOR,
        design_safety_factor=_TARGET_SF)


# ---------------------------------------------------------------------------
# 3. tur Ş2-2 (karar §28-37 seçenek (a)) — ortak kâhinler. (C) bütün
# hibritleri geçerlilik dışına aldığı için 'issued' dalı GEÇERLİLİK İÇİ bir
# vakayla sınanır; aşağıdaki yardımcılar test_d26_app_api_a5,
# test_uc_durustluk_kapilari ve test_z5i18n_kalan çevirilerince de kullanılır
# (tek tanım).
# ---------------------------------------------------------------------------
#: Geçerlilik İÇİ cidar sıcaklıkları [K] (steel_4130 eğrisinin son noktası
#: 700 °C = 973,15 K'nin ve erime noktasının altında; kâhin malzeme kaydı).
GECERLILIK_ICI_SICAK_K = 600.0
GECERLILIK_ICI_SOGUK_K = 590.0
#: Tehlikeli kullanıcı cidarı [m]: ince cidar basınç hoop'u tek başına
#: akmayı aşar (kâhin ``basinc_hoop_akmayi_asar``).
TEHLIKELI_CIDAR_M = 0.0003
#: Kullanıcının seçtiği hazne malzemesi (beyan 'user_supplied' olur).
DOGRULAMA_MALZEMESI = 'steel_4130'


def gecerlilik_ici_dogrulama(cidar_m, material=DOGRULAMA_MALZEMESI):
    """Geçerlilik İÇİ vakada kullanıcının cidarıyla (doğrulama kipi) gerçek
    yapısal modül sonucu."""
    return StructuralAnalyzer().analyze_structure(
        _motor(GECERLILIK_ICI_SICAK_K, GECERLILIK_ICI_SOGUK_K),
        material=material, design_pressure_factor=_DESIGN_PRESSURE_FACTOR,
        design_safety_factor=_TARGET_SF, actual_wall_thickness=cidar_m)


def malzeme_kaydina_gore_gecerlilik_disi(structural):
    """BAĞIMSIZ kâhin: yayımlanan cidar sıcaklıkları ⟷ malzeme kaydının
    kendi erime noktası ve düşürme eğrisinin son noktası
    (``structural_model_validity``'yi çağırmaz)."""
    mat = build_materials_view()[structural['design_parameters']['material']]
    egri_son_K = max(float(k) for k in mat['derating_curve']) + 273.15
    ta = structural['thermal_analysis']
    sicak = [float(ta['wall_temperature_inner_K'])]
    sd = ta.get('strength_derating') or {}
    if sd.get('wall_temperature_K') is not None:
        sicak.append(float(sd['wall_temperature_K']))
    return any(T >= float(mat['melting_point']) or T > egri_son_K
               for T in sicak)


def basinc_hoop_akmayi_asar(cidar_m, material=DOGRULAMA_MALZEMESI):
    """BAĞIMSIZ kâhin: ince cidar basınç hoop'u P_d·r/t, malzeme kaydının
    düşürülmemiş akma dayanımından (düşürme katsayısı en çok 1) büyükse hiçbir
    sıcaklıkta SF >= 1 olamaz (toplam hoop >= basınç hoop'u)."""
    mat = build_materials_view()[material]
    p_d = _MOTOR['chamber_pressure'] * 1e5 * _DESIGN_PRESSURE_FACTOR
    r = _MOTOR['chamber_diameter'] / 2.0
    ust = float(mat['yield_strength']) * max(mat['derating_curve'].values())
    return p_d * r / cidar_m > ust


# ---------------------------------------------------------------------------
# 1) Sözleşme: boyutlandırılmış cidar hedefini tutturur YA DA fail-closed
# ---------------------------------------------------------------------------
class TestBoyutlandirmaKendiHedefiniTutturur:

    @pytest.mark.parametrize('t_hot,t_cold', [
        (293.15, 293.15),     # ısıl yol kapalı (ΔT = 0)
        (500.0, 499.0),       # küçük gradyan
        (500.0, 495.0),
        (600.0, 590.0),
        (500.0, 460.0),       # büyük gradyan → ulaşılamaz
        (800.0, 700.0),
    ])
    def test_uygunluk_hedefi_tutturmakla_esdeger(self, t_hot, t_cold):
        """``sizing_feasible`` ⟺ yayımlanan toplam hoop SF >= hedef."""
        ca = _size(_motor(t_hot, t_cold))['chamber_analysis']
        assert ca['design_mode'] == 'size'
        tuttu = ca['hoop_safety_factor'] >= _TARGET_SF * (1.0 - 1e-9)
        assert ca['sizing_feasible'] is tuttu, (
            f'ΔT = {t_hot - t_cold} K: sizing_feasible = '
            f"{ca['sizing_feasible']} ama yayımlanan SF "
            f"{ca['hoop_safety_factor']:.4f} (hedef {_TARGET_SF})")
        if not ca['sizing_feasible']:
            assert isinstance(ca['sizing_infeasible_reason'], str)
            assert 'thermal' in ca['sizing_infeasible_reason']
            assert ca['safety_factor_reads_back_target'] is False

    def test_uygun_vakada_hedef_x_pay_geri_okunur(self):
        ca = _size(_motor(500.0, 495.0))['chamber_analysis']
        assert ca['sizing_feasible'] is True
        assert ca['sizing_load'] == 'pressure_plus_thermal'
        assert ca['hoop_safety_factor'] == pytest.approx(
            _TARGET_SF * MANUFACTURING_ALLOWANCE_FACTOR, rel=1e-9)
        assert ca['safety_factor_reads_back_target'] is True

    def test_iki_senaryo_ortak_cidarda_hedefi_tutar(self):
        """Yayımlanan cidar tektir; ISIL SENARYOLARIN İKİSİ de o cidarda
        değerlendirilir. 2. tur Ş7 (denetim U6): bağlayan senaryo hedef ×
        imalat payını (4,8) rel 1e-9 TUTAR, öbürü ≥ 4,8'dir. Eski sürüm
        yalnız ≥ 4,0 sınıyordu ve denetçinin MA mutasyonunda (boyutlandırma
        yalnız ilk senaryoyu sınar) YEŞİL kalıyordu.

        Kâhin bağımsızdır: her senaryo ürünün boyutlandırma yolundan değil,
        DOĞRULAMA kipinden (kullanıcı cidarı = yayımlanan cidar, ΔT elle
        ölçeklenmiş) yeniden değerlendirilir."""
        A = StructuralAnalyzer()
        motor = _motor(500.0, 495.0)
        res = _size(motor)
        ca = res['chamber_analysis']
        t_m = ca['recommended_thickness'] / 1000.0
        hedef_pay = _TARGET_SF * MANUFACTURING_ALLOWANCE_FACTOR
        sf = {}
        for ad, sen in ca['thermal_scenarios'].items():
            mat = A.materials['steel_4130']
            der = A._derate_strength(mat, sen['derating_temp_K'])
            # Doğrulama kipinde gradyan ölçeklenmez; referansı aynı cidara
            # taşımak için ΔT değerlendirilen cidara ölçeklenmiş verilir.
            dT_t = sen['delta_T_K'] * t_m / _REF_WALL_M
            ana = A._analyze_chamber_wall(
                3.0e6, 0.1, 0.5, mat, derating=der, wall_delta_T=dT_t,
                actual_thickness=t_m, design_safety_factor=_TARGET_SF)
            sf[ad] = ana['hoop_safety_factor']
        baglayan = min(sf, key=sf.get)
        assert sf[baglayan] == pytest.approx(hedef_pay, rel=1e-9), sf
        for ad, deger in sf.items():
            assert deger >= hedef_pay * (1 - 1e-9), (
                f'{ad}: ortak cidarda SF {deger:.6f} < {hedef_pay}')

    def test_ulasilamaz_vakada_basinc_cidari_ayni_kalir(self):
        """Fail-closed: hedef tutmuyorsa yeni bir cidar UYDURULMAZ; basınç-
        yalnız boyutlandırma kalınlığı yayımlanır ve SF ölçümdür."""
        ca_T = _size(_motor(500.0, 460.0))['chamber_analysis']
        assert ca_T['sizing_feasible'] is False
        assert ca_T['hoop_safety_factor'] < _TARGET_SF


# ---------------------------------------------------------------------------
# 2) Bağımsız kâhin: ince cidar kapalı biçim (ikinci yol)
# ---------------------------------------------------------------------------
def _derated_yield(mat, T_K):
    """materials_db eğrisinden doğrudan doğrusal ara değer (ürün
    fonksiyonu ``_derate_strength`` KULLANILMAZ)."""
    curve = mat['derating_curve']
    xs = sorted(curve)
    return mat['yield_strength'] * float(
        np.interp(T_K - 273.15, xs, [curve[x] for x in xs]))


def _sigma_th(mat, dT):
    """Timoshenko & Goodier / Roark Ch.16: σ = E·α·ΔT / (2(1−ν))."""
    return (mat['elastic_modulus'] * mat['thermal_expansion'] * dT
            / (2.0 * (1.0 - mat['poisson_ratio'])))


class TestKapaliBicimKahini:

    def test_ince_cidar_kok_formulu(self):
        """P·r/t + k·t = S  ⇒  t = (S − √(S² − 4·k·P·r)) / (2k),
        k = σ_th(ΔT_ref)/t_ref (sabit akı, ΔT ∝ t). Ortak cidar iki
        senaryonun kökünün büyüğüdür."""
        T_hot, T_cold = 500.0, 495.0
        res = _size(_motor(T_hot, T_cold))
        ca = res['chamber_analysis']
        mat = build_materials_view()['steel_4130']
        P = _MOTOR['chamber_pressure'] * 1e5 * _DESIGN_PRESSURE_FACTOR
        r = _MOTOR['chamber_diameter'] / 2.0
        dT = T_hot - T_cold
        kokler = []
        for T_der, dT_s in ((T_hot, 0.15 * dT),
                            (0.5 * (T_hot + T_cold), dT)):
            S = (_derated_yield(mat, T_der) / _TARGET_SF
                 / MANUFACTURING_ALLOWANCE_FACTOR)
            k = _sigma_th(mat, dT_s) / _REF_WALL_M
            kokler.append((S - math.sqrt(S * S - 4.0 * k * P * r)) / (2.0 * k))
        t_kahin = max(kokler)
        assert t_kahin / r < THIN_WALL_T_OVER_R_LIMIT
        assert ca['recommended_thickness'] / 1000.0 == pytest.approx(
            t_kahin, rel=1e-9)
        # ΔT değerlendirilen cidara ölçeklenmiş yayımlanır.
        assert ca['wall_delta_T_at_evaluated_wall_K'] == pytest.approx(
            res['thermal_analysis']['wall_delta_T_K'] * t_kahin / _REF_WALL_M,
            rel=1e-9)

    def test_isil_yol_kapaliyken_bit_ayni(self):
        """ΔT = 0: boyutlandırma eski basınç-yalnız akışın ta kendisi."""
        ca = _size(dict(_MOTOR))['chamber_analysis']
        mat = build_materials_view()['steel_4130']
        P = _MOTOR['chamber_pressure'] * 1e5 * _DESIGN_PRESSURE_FACTOR
        r = _MOTOR['chamber_diameter'] / 2.0
        t_min = P * r / (mat['yield_strength'] / _TARGET_SF)
        assert ca['sizing_load'] == 'pressure_only'
        assert ca['recommended_thickness'] / 1000.0 == (
            t_min * MANUFACTURING_ALLOWANCE_FACTOR)


# ---------------------------------------------------------------------------
# 3) Örnek hibrit: kök vaka + lüle kütlesi tek kaynak
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def ornek_hibrit(tmp_path_factory):
    import os
    os.environ.setdefault('HRMA_PROJECTS_DIR',
                          str(tmp_path_factory.mktemp('hrma_projeler')))
    from tests.test_example_projects import (
        HEADERS, NAMES, calculate_payload)
    from hrma.app import app
    with open(REPO_ROOT / 'examples' / (NAMES['hybrid'] + '.hrma'),
              encoding='utf-8') as f:
        fields = json.load(f)['inputs']['fields']
    # Rota literal yazılır (d24 rota çıkarımı bekçisi çözülemeyen çağrı
    # saymasın); hibrit hesap ucu = test_example_projects.ENDPOINTS['hybrid'].
    r = app.test_client().post('/calculate',
                               json=calculate_payload('hybrid', fields),
                               headers=HEADERS)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()


class TestOrnekHibrit:

    def test_kamara_hedefi_tutmuyorsa_fail_closed_beyan(self, ornek_hibrit):
        ca = ornek_hibrit['motor']['structural_analysis']['chamber_analysis']
        assert ca['design_mode'] == 'size'
        tuttu = (ca['hoop_safety_factor']
                 >= ca['design_safety_factor_target'] * (1.0 - 1e-9))
        assert ca['sizing_feasible'] is tuttu, (
            f"sizing_feasible {ca['sizing_feasible']} ⟷ SF "
            f"{ca['hoop_safety_factor']:.4f} / hedef "
            f"{ca['design_safety_factor_target']}")
        if not tuttu:
            assert 'thermal' in (ca['sizing_infeasible_reason'] or '')

    def test_lule_kutlesi_tek_kaynak(self, ornek_hibrit):
        m = ornek_hibrit['motor']
        w = m['structural_analysis']['weight_analysis']
        cad = ornek_hibrit['cad_design']['performance_summary'][
            'mass_breakdown']['nozzle_mass']
        assert w['nozzle_weight_source'] == 'drawn_solid'
        kutleler = {
            'weight_analysis.nozzle_weight': w['nozzle_weight'],
            'cad mass_breakdown.nozzle_mass': cad,
            'nozzle_geometry.estimated_mass':
                m['nozzle_geometry']['estimated_mass'],
            'nozzle_design.geometry.estimated_mass':
                m['nozzle_design']['geometry']['estimated_mass'],
        }
        assert len({round(v, 12) for v in kutleler.values()}) == 1, kutleler

    def test_kuru_kutle_dokumden(self, ornek_hibrit):
        w = ornek_hibrit['motor']['structural_analysis']['weight_analysis']
        assert w['total_weight'] == (w['chamber_weight'] + w['nozzle_weight']
                                     + w['end_caps_weight'])
        kd = ornek_hibrit['design_summary']['key_dimensions']
        assert kd['dry_mass_estimate_kg'] == w['total_weight']

    # --- 2. tur (12 Eki 2026) -------------------------------------------
    def test_referans_cidar_isi_modulunun_cidari(self, ornek_hibrit):
        """Ş2 (denetim U2): hibrit sabit nokta döngüsü ısı modülünün koştuğu
        cidarı yapısal boyutlandırmaya REFERANS olarak geçirir. Kâhin ısı
        modülünün KENDİ yayımladığı cidar
        (``heat_transfer_analysis.design_parameters.wall_thickness``).
        Denetçinin MB mutasyonu (referans None) bu testi kırar."""
        m = ornek_hibrit['motor']
        ca = m['structural_analysis']['chamber_analysis']
        isi_mm = m['heat_transfer_analysis']['design_parameters'][
            'wall_thickness']
        ref = ca['thermal_reference_wall_thickness_mm']
        assert ref is not None, 'referans cidar geçirilmedi (ΔT TUTULUYOR)'
        assert ref == pytest.approx(isi_mm, rel=1e-12)
        # Sabit noktada yayımlanan cidar ısı zincirinin cidarıdır.
        assert ref == pytest.approx(ca['recommended_thickness'], rel=1e-12)
        assert 'scaled with thickness' in (ca['sizing_infeasible_reason']
                                           or '')

    def test_kontrol_senaryosu_yoneten_senaryodur(self, ornek_hibrit):
        """Ş1: ulaşılamaz örnek hibritte ``sizing_controlling_case``
        ulaşılabilir en iyi SF'yi sınırlayan senaryodur ve yayımlanan
        yöneten senaryoya (``governing_thermal_scenario``) eşittir."""
        ca = ornek_hibrit['motor']['structural_analysis']['chamber_analysis']
        assert ca['sizing_feasible'] is False
        assert ca['sizing_controlling_case'] == ca[
            'governing_thermal_scenario']

    def test_model_gecerlilik_siniri_ornek_hibrit(self, ornek_hibrit):
        """(C) — karar §28-24: örnek hibritte kamara 3368 K'de (erime
        1705 K) değerlendiriliyor. Bayrak yanar; OLUMLU ya da SAYISAL
        tasarım hükmü verilmez; sayılar tanı künyesiyle kalır; ulaşılamaz
        gerekçesi MODEL sınırını söyler."""
        s = ornek_hibrit['motor']['structural_analysis']
        ca, sa = s['chamber_analysis'], s['safety_analysis']
        ta = s['thermal_analysis']
        # Bağımsız kâhin: yayımlanan sıcaklık ⟷ malzeme kaydı.
        mat = build_materials_view()[s['design_parameters']['material']]
        egri_son_K = max(mat['derating_curve']) + 273.15
        sicak = max(ta['wall_temperature_inner_K'],
                    ta['strength_derating']['wall_temperature_K'])
        beklenen = (sicak >= mat['melting_point'] or sicak > egri_son_K)
        assert beklenen is True
        assert ca['model_validity_limit_exceeded'] is True
        assert s['model_validity_limit_exceeded'] is True
        assert 'model_validity_limit_exceeded' in sa[
            'verdict_withheld_reasons']
        assert sa['verdict_withheld'] is True
        assert sa['verdict_safety_factor'] is None
        assert sa['headline_safety_factor'] is None
        assert sa['status'] not in ('SAFE', 'ACCEPTABLE')
        assert sa['measured_scope_status'] not in ('SAFE', 'ACCEPTABLE')
        assert ca['sizing_infeasible_reason'].startswith(
            'MODEL LIMIT, NOT A PROPERTY OF THE REAL MOTOR')
        assert ca['safety_factor_basis'].startswith('DIAGNOSTIC ONLY')
        assert s['weight_analysis']['model_validity_limit_exceeded'] is True
        kd = ornek_hibrit['design_summary']['key_dimensions']
        assert kd['dry_mass_model_validity_limit_exceeded'] is True
        assert 'DIAGNOSTIC ONLY' in kd['dry_mass_basis']
        # Sayılar SİLİNMEZ (tanı amaçlı kalır).
        assert isinstance(ca['safety_factor_total'], float)


# ---------------------------------------------------------------------------
# 4) 2. tur denetçi şartları (12 Eki 2026) — analizör düzeyi
# ---------------------------------------------------------------------------
class TestKontrolSenaryosu:
    """Ş1 (denetim U1): ``sizing_controlling_case`` toplam-hoop çözümünü
    BAĞLAYAN senaryoyu adlandırır."""

    @pytest.mark.parametrize('t_hot,t_cold', [
        (500.0, 495.0), (600.0, 590.0), (700.0, 690.0)])
    def test_baglayan_senaryo_adlandirilir(self, t_hot, t_cold):
        ca = _size(_motor(t_hot, t_cold))['chamber_analysis']
        assert ca['sizing_feasible'] is True
        assert ca['sizing_load'] == 'pressure_plus_thermal'
        assert ca['sizing_controlling_case'] == 'cooled_gradient'
        sen = ca['thermal_scenarios']
        hedef_pay = _TARGET_SF * MANUFACTURING_ALLOWANCE_FACTOR
        assert sen['cooled_gradient']['hoop_safety_factor'] == pytest.approx(
            hedef_pay, rel=1e-9)
        assert sen['hot_soak']['hoop_safety_factor'] >= hedef_pay


class TestModelGecerlilikSiniri:
    """(C) — karar §28-24: ölçüt TEK yerde (``structural_model_validity``);
    sınır aşılınca olumlu ve sayısal tasarım hükmü verilmez."""

    def test_olcut_iki_dal(self):
        from hrma.analysis.structural_analysis import (
            MODEL_VALIDITY_REASON_DERATING_DATA, MODEL_VALIDITY_REASON_MELTING,
            structural_model_validity)
        A = StructuralAnalyzer()
        mat = A.materials['steel_4130']
        egri_son_K = max(mat['derating_curve']) + 273.15
        erime_K = float(mat['melting_point'])
        vakalar = {
            # (sıcaklık K) -> beklenen gerekçe kümesi (bağımsız kâhin:
            # malzeme kaydının kendi eğrisi ve erime noktası)
            egri_son_K - 1.0: set(),
            egri_son_K: set(),
            egri_son_K + 1.0: {MODEL_VALIDITY_REASON_DERATING_DATA},
            erime_K: {MODEL_VALIDITY_REASON_DERATING_DATA,
                      MODEL_VALIDITY_REASON_MELTING},
        }
        for T, beklenen in vakalar.items():
            g = structural_model_validity(
                {'tek': A._derate_strength(mat, T)})
            assert set(g['model_validity_reasons']) == beklenen, T
            assert g['model_validity_limit_exceeded'] is bool(beklenen), T

    @pytest.mark.parametrize('t_hot,t_cold,beklenen', [
        (600.0, 590.0, False),     # eğri içinde
        (1000.0, 990.0, True),     # 700 °C eğri sonunun üstünde
        (1800.0, 1700.0, True),    # erime üstü (iç yüz)
    ])
    def test_hukum_fail_closed(self, t_hot, t_cold, beklenen):
        res = _size(_motor(t_hot, t_cold))
        ca, sa = res['chamber_analysis'], res['safety_analysis']
        assert ca['model_validity_limit_exceeded'] is beklenen
        assert ('model_validity_limit_exceeded'
                in sa['verdict_withheld_reasons']) is beklenen
        if beklenen:
            assert sa['verdict_safety_factor'] is None
            assert sa['headline_safety_factor'] is None
            assert sa['status'] not in ('SAFE', 'ACCEPTABLE')
            assert sa['measured_scope_status'] not in ('SAFE', 'ACCEPTABLE')
            assert res['weight_analysis'][
                'model_validity_limit_exceeded'] is True
            if not ca['sizing_feasible']:
                assert ca['sizing_infeasible_reason'].startswith(
                    'MODEL LIMIT')

    def test_dogrulama_kipinde_de_gecerli(self):
        """Kullanıcı cidarı (doğrulama kipi) da aynı ölçütten geçer: kazanılmış
        bir SF bile geçerlilik dışı sıcaklıkta onay üretemez."""
        res = StructuralAnalyzer().analyze_structure(
            _motor(1000.0, 999.0), material='steel_4130',
            design_pressure_factor=_DESIGN_PRESSURE_FACTOR,
            design_safety_factor=_TARGET_SF, actual_wall_thickness=0.02)
        assert res['chamber_analysis']['design_mode'] == 'verify'
        assert res['chamber_analysis']['model_validity_limit_exceeded'] is True
        sa = res['safety_analysis']
        assert sa['status'] not in ('SAFE', 'ACCEPTABLE')
        assert sa['verdict_safety_factor'] is None


# ---------------------------------------------------------------------------
# 5) Ş3 — panelde görünen ΔT ile ısıl hoop gerilmesi aynı cidara ait
# ---------------------------------------------------------------------------
_TAHMIN_YUKU = {'chamber_pressure': 50, 'chamber_diameter': 0.15,
                'chamber_length': 0.3, 'throat_diameter': 0.05,
                'chamber_temperature': 3000, 'material': 'steel_4130'}


@pytest.fixture(scope='module')
def tahmin_yolu_yaniti(tmp_path_factory):
    import os
    os.environ.setdefault('HRMA_PROJECTS_DIR',
                          str(tmp_path_factory.mktemp('hrma_projeler_t3')))
    from hrma.app import app
    r = app.test_client().post('/analyze_structural_safety',
                               json=_TAHMIN_YUKU,
                               headers={'Host': '127.0.0.1:8080'})
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()


class TestDeltaTAyniCidar:

    def test_gosterilen_dT_isil_gerilmeyi_verir(self, tahmin_yolu_yaniti):
        """E·α·ΔT_değerlendirilen / (2(1−ν)) = chamber.thermal_hoop_stress
        (rel 1e-9) ve ΔT_ref × t_değ / t_ref = ΔT_değ."""
        s = tahmin_yolu_yaniti.get('structural_analysis') or tahmin_yolu_yaniti
        ca, ta = s['chamber_analysis'], s['thermal_analysis']
        assert ca['design_mode'] == 'size'
        mat = build_materials_view()['steel_4130']
        dT_deg = ta['wall_delta_T_at_evaluated_wall_K']
        assert _sigma_th(mat, dT_deg) / 1e6 == pytest.approx(
            ca['thermal_hoop_stress'], rel=1e-9)
        t_ref = ta['thermal_reference_wall_thickness_mm']
        t_deg = ta['evaluated_wall_thickness_mm']
        assert t_deg == ca['wall_thickness_used_mm']
        assert ta['wall_delta_T_K'] * t_deg / t_ref == pytest.approx(
            dT_deg, rel=1e-12)
        # Referans ΔT iç/dış sıcaklıklarla aynı cidara aittir (eski alan
        # anlamını korur, sayı değişmez).
        assert t_ref != pytest.approx(t_deg, rel=1e-6)

    def test_panel_iki_dT_satiri(self):
        """Panel iki ΔT'yi iki ayrı i18n anahtarlı satırda, ucun alanlarından
        basar (EN = TR)."""
        js = (REPO_ROOT / 'hrma' / 'static' / 'js' / 'panels'
              / 'structural_panel.js').read_text(encoding='utf-8')
        assert "'panel.structural.wallTempRefWall'" in js
        assert 'th.thermal_reference_wall_thickness_mm' in js
        assert "'panel.structural.wallTempDeltaEvaluated'" in js
        assert 'th.wall_delta_T_at_evaluated_wall_K' in js
        # (C) geçerlilik satırı: render() onu çağırır, bayrağı okur, gerekçe
        # kodu cümleye çevrilir.
        assert 'html += modelValidityBlock(ca);' in js
        assert 'ca.model_validity_limit_exceeded !== true' in js
        for k in ("'panel.structural.badgeModelValidity'",
                  "'panel.structural.modelValidityNote'",
                  "'panel.structural.reasonModelValidity'",
                  'model_validity_limit_exceeded: ['):
            assert k in js, k
        i18n = (REPO_ROOT / 'hrma' / 'static' / 'js'
                / 'i18n_common.js').read_text(encoding='utf-8')
        for k in ('panel.structural.wallTempRefWall',
                  'panel.structural.wallTempDeltaEvaluated',
                  'panel.structural.reasonModelValidity',
                  'panel.structural.badgeModelValidity',
                  'panel.structural.modelValidityNote'):
            assert i18n.count("'" + k + "'") == 2, k   # EN + TR


# ---------------------------------------------------------------------------
# 6) Ş6 — yeni/değişen künyeler EN = TR (sunucu metni sözlüğü)
# ---------------------------------------------------------------------------
_NODE_SONDA = r"""
'use strict';
const fs = require('fs'); const path = require('path'); const vm = require('vm');
const [staticDir, girdiYolu] = process.argv.slice(2);
const P = JSON.parse(fs.readFileSync(girdiYolu, 'utf8'));
const depo = {};
const sb = {
    console: { log: function () {}, warn: function () {}, error: function () {} },
    JSON: JSON, Math: Math, Number: Number, Array: Array, Object: Object,
    String: String, Boolean: Boolean, RegExp: RegExp, Date: Date,
    isFinite: isFinite, parseFloat: parseFloat, parseInt: parseInt,
    setTimeout: setTimeout, clearTimeout: clearTimeout,
    document: { readyState: 'complete', addEventListener: function () {},
                querySelectorAll: function () { return []; },
                querySelector: function () { return null; },
                documentElement: { setAttribute: function () {} },
                createElement: function () { return { style: {} }; } },
    localStorage: {
        getItem: function (k) { return (k in depo) ? depo[k] : null; },
        setItem: function (k, v) { depo[k] = String(v); },
        removeItem: function (k) { delete depo[k]; } },
    navigator: { language: 'en-US' },
    matchMedia: function () { return { matches: true }; },
    performance: { now: function () { return 0; } },
    requestAnimationFrame: null,
};
sb.window = sb; sb.globalThis = sb;
vm.createContext(sb);
function kos(f) {
    vm.runInContext(fs.readFileSync(f, 'utf8'), sb, { filename: f }); }
kos(path.join(staticDir, 'i18n.js'));
kos(path.join(staticDir, 'i18n_common.js'));
kos(path.join(staticDir, 'i18n_charts.js'));
const out = {};
['en', 'tr'].forEach(function (dil) {
    if (sb.I18N.setLang) { sb.I18N.setLang(dil); } else { sb.I18N.lang = dil; }
    out[dil] = P.metinler.map(function (m) { return sb.I18N.serverText(m); });
});
console.log(JSON.stringify(out));
"""


def _kunye_metinleri():
    from hrma.analysis import structural_analysis as sa
    yeni = [sa.MODEL_VALIDITY_BASIS, sa.MODEL_VALIDITY_SAFETY_FACTOR_BASIS,
            sa.MODEL_VALIDITY_MASS_BASIS, sa.MODEL_VALIDITY_VERDICT_BASIS,
            sa.DRAWN_NOZZLE_MASS_BASIS, sa.FRUSTUM_APPROXIMATION_MASS_BASIS,
            sa.DRY_MASS_BASIS_DRAWN_NOZZLE,
            sa.DRY_MASS_BASIS_DRAWN_NOZZLE_OUTSIDE_VALIDITY]
    # Yanıttan okunan künyeler (değişen/yeni metinler, ürün yolundan).
    res = _size(_motor(500.0, 460.0))
    ca = res['chamber_analysis']
    yeni += [ca['wall_delta_T_at_evaluated_wall_K_basis'],
             ca['safety_factor_is_tautological_basis'],
             ca['safety_factor_basis'],
             res['safety_analysis'][
                 'binding_safety_factor_is_tautological_basis']]
    ca_ok = _size(_motor(500.0, 495.0))['chamber_analysis']
    yeni.append(ca_ok['safety_factor_basis'])
    return yeni


def test_kunyeler_tr_karsiligi_var(tmp_path):
    """Ş6 (denetim U5): ekranda görünen yeni/değişen künye metinlerinin TR
    karşılığı sözlükte; EN kimlik = metnin kendisi. Ayrıca künye DEĞERİ OLAN
    alana bağlı (``wall_delta_T_at_evaluated_wall_K``), eski değersiz
    ``thermal_gradient_scale_basis`` yok."""
    import shutil
    import subprocess
    node = shutil.which('node')
    if node is None:
        pytest.skip('node yok: TR sözlük ölçümü koşamaz (gerekçeli atlama)')
    metinler = _kunye_metinleri()
    ca = _size(_motor(500.0, 495.0))['chamber_analysis']
    assert 'thermal_gradient_scale_basis' not in ca
    assert 'sizing_load_model' not in ca
    assert isinstance(ca['wall_delta_T_at_evaluated_wall_K'], float)
    betik = tmp_path / 'sonda.js'
    betik.write_text(_NODE_SONDA, encoding='utf-8')
    girdi = tmp_path / 'girdi.json'
    girdi.write_text(json.dumps({'metinler': metinler}), encoding='utf-8')
    p = subprocess.run([node, str(betik),
                        str(REPO_ROOT / 'hrma' / 'static' / 'js'), str(girdi)],
                       capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr[-2000:]
    out = json.loads(p.stdout.strip().splitlines()[-1])
    for m, en, tr in zip(metinler, out['en'], out['tr']):
        assert en == m, ('EN kimlik değil', m[:80])
        assert tr != m, ('TR karşılığı yok', m[:80])
        assert any(h in tr for h in 'çğıöşüÇĞİÖŞÜ'), ('TR değil', tr[:80])


# ---------------------------------------------------------------------------
# 7) 3. tur Ş2-5 (yeniden denetim-2, karar §28-37) — bekçi açıkları
#    Denetçinin DA, DB, DE, DJ, DG, DH ters mutasyonları bu bekçilerde
#    KIRMIZI olmalı (mutasyon.md "3. tur").
# ---------------------------------------------------------------------------
#: Yalnız hot_soak senaryosunun eğri dışına çıktığı vaka [K] (steel_4130:
#: iç yüz 1000 K > eğri sonu 973,15 K; kesit ortalaması 950 K eğri içinde).
_YALNIZ_HOT_SOAK_K = (1000.0, 900.0)
#: Eğri sonu < servis sınırı olan malzeme ve vaka (ss_316: eğri sonu
#: 1073,15 K < 1100 K < servis sınırı 1143 K), kalın kullanıcı cidarı [m].
_EGRI_SERVIS_ALTI = ('ss_316', 1100.0, 1095.0, 0.02)
_ONAY = ('SAFE', 'ACCEPTABLE')


class TestBekciAciklari:

    def test_yalniz_hot_soak_veri_disi(self):
        """(a) DA: ölçüt HER senaryonun kaydını okur. Kâhin malzeme kaydı:
        iç yüz eğri sonunun üstünde, kesit ortalaması altında; ikisi de
        erimenin altında."""
        from hrma.analysis.structural_analysis import (
            MODEL_VALIDITY_REASON_DERATING_DATA)
        t_hot, t_cold = _YALNIZ_HOT_SOAK_K
        mat = build_materials_view()['steel_4130']
        egri_son_K = max(mat['derating_curve']) + 273.15
        assert t_hot > egri_son_K >= 0.5 * (t_hot + t_cold)
        assert t_hot < mat['melting_point']
        ca = _size(_motor(t_hot, t_cold))['chamber_analysis']
        ev = ca['model_validity_evaluations']
        assert ev['hot_soak']['above_derating_curve_data'] is True
        assert ev['cooled_gradient']['above_derating_curve_data'] is False
        assert ev['hot_soak']['at_or_above_melting_point'] is False
        assert ca['model_validity_limit_exceeded'] is True
        assert ca['model_validity_reasons'] == [
            MODEL_VALIDITY_REASON_DERATING_DATA]

    def test_egri_servis_altinda_malzeme_onay_tavana(self):
        """(b) DB: eğri sonu servis sınırının altında olan malzemede
        ölçülmüş-kapsam onayı da tavana çekilir; sayısal hüküm yok."""
        ad, t_hot, t_cold, cidar = _EGRI_SERVIS_ALTI
        mat = build_materials_view()[ad]
        assert (max(mat['derating_curve']) + 273.15 < t_hot
                < mat['max_service_temp'])
        res = StructuralAnalyzer().analyze_structure(
            _motor(t_hot, t_cold), material=ad,
            design_pressure_factor=_DESIGN_PRESSURE_FACTOR,
            design_safety_factor=_TARGET_SF, actual_wall_thickness=cidar)
        sa = res['safety_analysis']
        assert res['chamber_analysis']['model_validity_limit_exceeded'] is True
        assert sa['status'] not in _ONAY, sa['status']
        assert sa.get('measured_scope_status') not in _ONAY, (
            sa.get('measured_scope_status'))
        assert sa['verdict_safety_factor'] is None

    def test_hukum_gerekcesi_model_siniri(self):
        """(c) DE: geçerlilik dışında hüküm gerekçesi MODEL sınırını söyler
        (Astra: 'mevcut model altında başarısızlık')."""
        from hrma.analysis.structural_analysis import (
            MODEL_VALIDITY_VERDICT_BASIS)
        sa = _size(_motor(*_YALNIZ_HOT_SOAK_K))['safety_analysis']
        assert sa['minimum_safety_factor_verdict_basis'] == (
            MODEL_VALIDITY_VERDICT_BASIS)

    def test_kutle_kunyesi_tani(self):
        """(d) DJ: geçerlilik dışında kütle dökümü tanı künyesi taşır."""
        from hrma.analysis.structural_analysis import MODEL_VALIDITY_MASS_BASIS
        w = _size(_motor(*_YALNIZ_HOT_SOAK_K))['weight_analysis']
        assert w['model_validity_limit_exceeded'] is True
        assert w['model_validity_limit_exceeded_basis'] == (
            MODEL_VALIDITY_MASS_BASIS)


def _json_guvenli(o):
    """Analizör sözlüğünü node'a JSON olarak geçirilebilir yapar: sonlu
    olmayan sayı -> None (JSON.parse 'Infinity' kabul etmez), numpy -> Python."""
    if isinstance(o, dict):
        return {str(k): _json_guvenli(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_json_guvenli(v) for v in o]
    if isinstance(o, (bool, np.bool_)):
        return bool(o)
    if isinstance(o, (int, np.integer)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        return float(o) if math.isfinite(float(o)) else None
    return o


_PANEL_HARNESS = (REPO_ROOT / 'docs' / 'scofield' / 'raw' / 'P11'
                  / 'B4-repro-03.js')


def _panel_render(structural):
    """structural_panel.js'i node altında GERÇEKTEN render eder (mevcut d26
    panel harness deseni: tests/test_d26_arayuz_a3.py::kos)."""
    import shutil
    import subprocess
    from tests.support.kanit import kanit_gerekli
    node = shutil.which('node')
    if node is None:
        pytest.skip('node yok: panel render ölçümü koşamaz (gerekçeli atlama)')
    cfg = {'panelId': 'structural',
           'panelFiles': ['hrma/static/js/panels/structural_panel.js'],
           'dataInline': {'structural_analysis': _json_guvenli(structural)}}
    p = subprocess.run([node, kanit_gerekli(str(_PANEL_HARNESS))],
                       input=json.dumps(cfg), capture_output=True, text=True,
                       timeout=120)
    assert p.returncode == 0, p.stderr[-2000:]
    out = json.loads(p.stdout)
    assert out['error'] is None, out['error']
    return out


class TestPanelRender:
    """(e) DG/DH: panel geçerlilik bloğu ve iki ΔT satırı DAVRANIŞ olarak
    (render çıktısında) ölçülür; kaynak metin çapası yetmez."""

    _ROZET = 'OUTSIDE MODEL VALIDITY'
    _NOT = 'outside the validity limit of the current model'

    def test_bayrak_true_rozet_not_kod(self):
        res = _size(_motor(*_YALNIZ_HOT_SOAK_K))
        ca = res['chamber_analysis']
        assert ca['model_validity_limit_exceeded'] is True
        r = _panel_render(res)
        assert self._ROZET in r['text']
        assert self._NOT in r['text']
        assert 'model_validity_reasons' in r['html']
        for kod in ca['model_validity_reasons']:
            assert kod in r['html'], kod

    @pytest.mark.parametrize('bayrak', ['false', 'yok'])
    def test_bayrak_false_ya_da_yok_hicbiri(self, bayrak):
        res = _size(_motor(GECERLILIK_ICI_SICAK_K, GECERLILIK_ICI_SOGUK_K))
        ca = res['chamber_analysis']
        assert ca['model_validity_limit_exceeded'] is False
        if bayrak == 'yok':
            for k in [k for k in ca if k.startswith('model_validity')]:
                del ca[k]
        r = _panel_render(res)
        assert self._ROZET not in r['text']
        assert self._NOT not in r['text']
        assert 'model_validity_reasons' not in r['html']

    def test_iki_dT_satiri_ucun_sayisiyla(self):
        import re
        res = _size(_motor(GECERLILIK_ICI_SICAK_K, GECERLILIK_ICI_SOGUK_K))
        ta = res['thermal_analysis']
        t_ref = ta['thermal_reference_wall_thickness_mm']
        t_deg = ta['evaluated_wall_thickness_mm']
        dT_deg = ta['wall_delta_T_at_evaluated_wall_K']
        assert isinstance(t_ref, float) and isinstance(dT_deg, float)
        r = _panel_render(res)
        metin = r['text']
        assert 'Wall the temperatures and ΔT above were computed on' in metin
        assert 'ΔT on the evaluated wall (drives the thermal hoop stress)' in (
            metin)
        m = re.search(r'computed on\s+([0-9.]+) mm', metin)
        assert m, metin[:400]
        assert float(m.group(1)) == pytest.approx(t_ref, abs=5e-4)
        m = re.search(r'thermal hoop stress\)\s+([0-9.]+) K · ([0-9.]+) mm',
                      metin)
        assert m, metin[:400]
        assert float(m.group(1)) == pytest.approx(dT_deg, abs=0.05)
        assert float(m.group(2)) == pytest.approx(t_deg, abs=5e-4)


# ---------------------------------------------------------------------------
# 8) 3. tur Ş2-6 — tarama ızgarasının vektör hâli skaler algoritmayla
#    BİT-EŞİT (yayımlanan sayı değişmez). Kâhin: eski skaler döngünün
#    kendisi (aşağıda aynen), değişmeyen skaler model fonksiyonları
#    (``_evaluated_pressure_hoop``, ``_thermal_scale``) üstünde.
# ---------------------------------------------------------------------------
def _eski_skaler_tarama(A, pressure, radius, cases, ref):
    """2. tur sonundaki (4b4f4ccd) ``_thickness_for_total_hoop_allowable``
    gövdesi, aynen (yalnız ``self`` → ``A``)."""
    from hrma.analysis.structural_analysis import (
        SIZING_BISECTION_ITERS, SIZING_SCAN_POINTS, SIZING_SCAN_T_OVER_R_MAX,
        SIZING_SCAN_T_OVER_R_MIN)

    def _ok(t):
        for izinli, sigma_th, _y in cases:
            toplam = (A._evaluated_pressure_hoop(pressure, radius, t)
                      + sigma_th * A._thermal_scale(t, ref))
            if toplam > izinli:
                return False
        return True

    def _oran(t):
        return min(
            izinli / (A._evaluated_pressure_hoop(pressure, radius, t)
                      + sigma_th * A._thermal_scale(t, ref))
            for izinli, sigma_th, _y in cases)

    izgara = radius * np.logspace(np.log10(SIZING_SCAN_T_OVER_R_MIN),
                                  np.log10(SIZING_SCAN_T_OVER_R_MAX),
                                  SIZING_SCAN_POINTS)
    en_iyi, t_en_iyi, ilk = 0.0, None, None
    for i, t in enumerate(izgara):
        t = float(t)
        oran = _oran(t)
        if oran > en_iyi:
            en_iyi, t_en_iyi = oran, t
        if ilk is None and _ok(t):
            ilk = i
    if ilk is None:
        return float('inf'), en_iyi, t_en_iyi
    if ilk == 0:
        return float(izgara[0]), en_iyi, t_en_iyi
    lo, hi = float(izgara[ilk - 1]), float(izgara[ilk])
    for _ in range(SIZING_BISECTION_ITERS):
        orta = 0.5 * (lo + hi)
        if orta <= lo or orta >= hi:
            break
        if _ok(orta):
            hi = orta
        else:
            lo = orta
    return hi, en_iyi, t_en_iyi


#: Bit-eşitlik vaka kümesinin tohumu ve büyüklüğü (kalın cidar bölgesinde
#: pow() ⟷ b*b ayrışmasını yakalayacak kadar vaka).
_BIT_ESIT_TOHUM = 20261012
_BIT_ESIT_VAKA = 24


def _bit_esit_vakalari():
    import random
    rnd = random.Random(_BIT_ESIT_TOHUM)
    vakalar = []
    for _ in range(_BIT_ESIT_VAKA):
        r = 10 ** rnd.uniform(-2, 0)
        cs = []
        for _ in range(rnd.choice([1, 2, 3])):
            y = 10 ** rnd.uniform(7, 9.2)
            cs.append((y / rnd.uniform(1.0, 6.0), rnd.choice(
                [0.0, 10 ** rnd.uniform(5, 9)]), y))
        vakalar.append((10 ** rnd.uniform(5, 7.5), r, cs, rnd.choice(
            [None, r * 10 ** rnd.uniform(-3, -0.5), 0.0])))
    # NaN/inf anlamı (Python min/max/karşılaştırma kararı korunmalı).
    vakalar += [(2e6, 0.05, [(1e8, float('nan'), 4e8)], 0.004),
                (2e6, 0.05, [(float('nan'), 1e7, 4e8), (1e8, 1e7, 4e8)],
                 0.004),
                (2e6, 0.05, [(1e8, float('inf'), 4e8)], 0.004)]
    return vakalar


def test_tarama_vektor_skaler_bit_esit():
    A = StructuralAnalyzer()
    ayrisan = []
    for P, r, cs, ref in _bit_esit_vakalari():
        eski = _eski_skaler_tarama(A, P, r, cs, ref)
        yeni = A._thickness_for_total_hoop_allowable(P, r, cs, ref)
        esit = all(
            (a is None and b is None)
            or (a is not None and b is not None
                and (float(a) == float(b)
                     or (math.isnan(float(a)) and math.isnan(float(b)))))
            for a, b in zip(eski, yeni))
        if not esit:
            ayrisan.append(((P, r, ref), eski, yeni))
    assert not ayrisan, ayrisan[:3]


def test_tarama_izgarasi_noktasal_bit_esit():
    """Izgaranın HER noktasında vektör oran/uygunluk = skaler
    ``_evaluated_pressure_hoop`` + ``_thermal_scale`` (bit-eşit; NaN
    anlamı dahil). Nihai dönüşü değiştirmeyen tek ulp'lik sızıntılar da
    burada görünür."""
    from hrma.analysis.structural_analysis import (
        SIZING_SCAN_POINTS, SIZING_SCAN_T_OVER_R_MAX, SIZING_SCAN_T_OVER_R_MIN)
    A = StructuralAnalyzer()
    for P, r, cs, ref in _bit_esit_vakalari()[:8]:
        izgara = r * np.logspace(np.log10(SIZING_SCAN_T_OVER_R_MIN),
                                 np.log10(SIZING_SCAN_T_OVER_R_MAX),
                                 SIZING_SCAN_POINTS)
        oranlar, uygun = A._total_hoop_grid(P, r, cs, ref, izgara)
        for i, t in enumerate(izgara):
            t = float(t)
            toplamlar = [A._evaluated_pressure_hoop(P, r, t)
                         + s * A._thermal_scale(t, ref) for _iz, s, _y in cs]
            oran = min(iz / tp for (iz, _s, _y), tp in zip(cs, toplamlar))
            ok = not any(tp > iz for (iz, _s, _y), tp in zip(cs, toplamlar))
            assert (oranlar[i] == oran
                    or (math.isnan(oranlar[i]) and math.isnan(oran))), (
                (P, r, ref, i, float(oranlar[i]).hex(), float(oran).hex()))
            assert bool(uygun[i]) is ok, (P, r, ref, i)


# ---------------------------------------------------------------------------
# 9) 3. tur Bölüm B (karar §28-37 Ş2-3 (a), v3.0 bloklayıcı) — (C) model
#    geçerlilik ölçütü SIVI ``chamber_structure`` ve KATI ``case_analysis`` /
#    ``pressure_safety`` çağrı noktalarında (tek ölçüt
#    ``structural_model_validity``).
#    Kâhinler: (1) materials_db kaydının erime noktası ve düşürme eğrisinin
#    son noktası ile ucun KENDİ yayımladığı cidar/kasa sıcaklığı; (2) eski
#    davranış = aynı koşu, ölçüt kapalı (``model_validity_publication`` →
#    {}); main 4d5f2061 dışa aktarımıyla aynı olduğu kanıtta ölçüldü
#    (kanit/16_*, t3b_C_*).
# ---------------------------------------------------------------------------
#: Yeniden denetim-2'nin katı vakası (örnek katı + bu alanlar).
_KATI_ERIME_USTU = {'case_material': 'aluminum_6061',
                    'insulation_thickness': 0, 'grain_type': 'end_burner',
                    'grain_length': 1500, 'flame_temp': 3200,
                    'case_thickness': 4}
#: F1 ``varyant:liquid:cooling_type=radiative``.
_SIVI_RADYATIF = {'cooling_type': 'radiative'}
#: Kapta onay sayılan hükümler (motor ve uç kapısıyla aynı küme).
_KAP_ONAY = ('PASS', 'SAFE', 'ACCEPTABLE', 'OK')


def _duzle(o, yol=''):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from _duzle(v, f'{yol}.{k}' if yol else k)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from _duzle(v, f'{yol}[{i}]')
    else:
        yield yol, o


def _sivi_kati_yanit(tur, ek, gecerlilik_kapali=False):
    """Örnek projeden + ``ek`` alanlarla GERÇEK uç yanıtı. Rotalar literal
    (d24 rota çıkarımı bekçisi)."""
    import hrma.analysis.structural_analysis as sa
    from hrma.app import app
    from tests.test_example_projects import HEADERS, NAMES, calculate_payload
    with open(REPO_ROOT / 'examples' / (NAMES[tur] + '.hrma'),
              encoding='utf-8') as f:
        fields = json.load(f)['inputs']['fields']
    fields.update(ek)
    yuk = calculate_payload(tur, fields)
    eski = sa.model_validity_publication
    if gecerlilik_kapali:
        sa.model_validity_publication = lambda gecerlilik, basis: {}
    try:
        c = app.test_client()
        if tur == 'liquid':
            r = c.post('/calculate_liquid', json=yuk, headers=HEADERS)
        else:
            r = c.post('/calculate_solid', json=yuk, headers=HEADERS)
    finally:
        sa.model_validity_publication = eski
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()


@pytest.fixture(scope='module')
def sivi_kati(tmp_path_factory):
    import os
    os.environ.setdefault('HRMA_PROJECTS_DIR',
                          str(tmp_path_factory.mktemp('hrma_projeler_b')))
    vakalar = {'sivi_radyatif': ('liquid', _SIVI_RADYATIF),
               'kati_erime_ustu': ('solid', _KATI_ERIME_USTU),
               'ornek_sivi': ('liquid', {}), 'ornek_kati': ('solid', {})}
    return {ad: {'yeni': _sivi_kati_yanit(tur, ek),
                 'eski': _sivi_kati_yanit(tur, ek, gecerlilik_kapali=True)}
            for ad, (tur, ek) in vakalar.items()}


def _kayit(anahtar):
    m = build_materials_view()[anahtar]
    return (float(m['melting_point']),
            max(float(k) for k in m['derating_curve']) + 273.15)


class TestSiviKatiGecerlilik:

    def test_sivi_radyatif_onay_ve_sayisal_hukum_vermez(self, sivi_kati):
        from hrma.analysis.structural_analysis import (
            LIQUID_MODEL_VALIDITY_BASIS,
            LIQUID_MODEL_VALIDITY_SAFETY_FACTOR_BASIS,
            MODEL_VALIDITY_REASON_DERATING_DATA,
            MODEL_VALIDITY_REASON_MELTING,
            STRUCTURAL_MODEL_VALIDITY_WITHHELD_REASON)
        cs = sivi_kati['sivi_radyatif']['yeni']['structural_analysis'][
            'chamber_structure']
        erime, egri_son = _kayit(cs['material_key'])
        T = cs['wall_temperature']
        # Kâhin: kayıt ⟷ ucun kendi sıcaklığı (1800 K ≥ 1533 K > 1173,15 K).
        assert T >= erime and T > egri_son, (T, erime, egri_son)
        assert cs['model_validity_limit_exceeded'] is True
        assert set(cs['model_validity_reasons']) == {
            MODEL_VALIDITY_REASON_MELTING, MODEL_VALIDITY_REASON_DERATING_DATA}
        assert cs['verdict_withheld'] is True
        assert cs['verdict_withheld_reasons'] == [
            STRUCTURAL_MODEL_VALIDITY_WITHHELD_REASON]
        assert cs['safety_factor_basis'] == (
            LIQUID_MODEL_VALIDITY_SAFETY_FACTOR_BASIS)
        assert cs['model_validity_limit_exceeded_basis'] == (
            LIQUID_MODEL_VALIDITY_BASIS)
        ev = cs['model_validity_evaluations']['chamber_hot_wall']
        assert ev['wall_temperature_K'] == T
        assert ev['melting_point_K'] == erime
        assert ev['derating_curve_last_point_K'] == pytest.approx(egri_son)
        # Sayılar TANI amaçlı kalır (silinmez).
        assert math.isfinite(cs['hoop_safety_factor'])
        assert math.isfinite(cs['wall_thickness'])

    def test_kati_kasa_erime_ustu_PASS_vermez(self, sivi_kati):
        from hrma.analysis.structural_analysis import (
            MODEL_VALIDITY_REASON_DERATING_DATA,
            MODEL_VALIDITY_REASON_MELTING, SOLID_CASE_MODEL_VALIDITY_BASIS,
            SOLID_CASE_MODEL_VALIDITY_SAFETY_FACTOR_BASIS,
            STRUCTURAL_MODEL_VALIDITY_WITHHELD_REASON)
        y = sivi_kati['kati_erime_ustu']['yeni']
        ps = y['safety_analysis']['pressure_safety']
        ca = y['structural_analysis']['case_analysis']
        T = y['thermal_analysis']['heat_transfer']['case_temperature_k']
        erime, egri_son = _kayit(ps['case_material'])
        assert T >= erime and T > egri_son, (T, erime, egri_son)
        assert str(ps['vessel_status']).upper() not in _KAP_ONAY
        assert ps['vessel_status'] == 'NOT_EVALUATED'
        for blok in (ps, ca):
            assert blok['model_validity_limit_exceeded'] is True
            assert set(blok['model_validity_reasons']) == {
                MODEL_VALIDITY_REASON_MELTING,
                MODEL_VALIDITY_REASON_DERATING_DATA}
            assert blok['verdict_withheld'] is True
            assert blok['verdict_withheld_reasons'] == [
                STRUCTURAL_MODEL_VALIDITY_WITHHELD_REASON]
            assert blok['model_validity_limit_exceeded_basis'] == (
                SOLID_CASE_MODEL_VALIDITY_BASIS)
            ev = blok['model_validity_evaluations']['case_wall_end_of_burn']
            assert ev['wall_temperature_K'] == T
            assert ev['melting_point_K'] == erime
        assert ca['safety_factor_basis'] == (
            SOLID_CASE_MODEL_VALIDITY_SAFETY_FACTOR_BASIS)
        assert 'verified' not in ca['safety_factor_basis']
        assert math.isfinite(ca['safety_factor'])
        assert math.isfinite(ps['burst_pressure_bar'])
        # Eski davranış (ölçüt kapalı) bu vakada PASS veriyordu.
        eski = sivi_kati['kati_erime_ustu']['eski']['safety_analysis'][
            'pressure_safety']
        assert eski['vessel_status'] == 'PASS'

    @pytest.mark.parametrize('vaka', ['ornek_sivi', 'ornek_kati'])
    def test_gecerlilik_ici_bayrak_disi_bit_ayni(self, sivi_kati, vaka):
        a = dict(_duzle(sivi_kati[vaka]['yeni']))
        z = dict(_duzle(sivi_kati[vaka]['eski']))
        fark = sorted(k for k in set(a) | set(z)
                      if a.get(k, '<YOK>') != z.get(k, '<YOK>'))
        assert fark, 'geçerlilik alanları eklenmemiş'
        disari = [k for k in fark if '.model_validity_' not in k]
        assert not disari, disari[:5]
        bayraklar = [v for k, v in a.items()
                     if k.endswith('.model_validity_limit_exceeded')]
        assert bayraklar and all(v is False for v in bayraklar), bayraklar
        assert not [k for k in a if 'verdict_withheld' in k
                    and ('chamber_structure' in k or 'case_analysis' in k
                         or 'pressure_safety' in k)]

    @pytest.mark.parametrize('vaka', ['sivi_radyatif', 'kati_erime_ustu'])
    def test_gecerlilik_disi_yalniz_hukum_alanlari_degisir(self, sivi_kati,
                                                           vaka):
        a = dict(_duzle(sivi_kati[vaka]['yeni']))
        z = dict(_duzle(sivi_kati[vaka]['eski']))
        fark = sorted(k for k in set(a) | set(z)
                      if a.get(k, '<YOK>') != z.get(k, '<YOK>'))
        izinli = ('.model_validity_', '.verdict_withheld',
                  '.safety_factor_basis', '.vessel_status',
                  'case_geometry.note', 'end_cap_analysis._basis')
        disari = [k for k in fark if not any(i in k for i in izinli)]
        assert not disari, disari[:5]
        assert any(k.endswith('.verdict_withheld') for k in fark)

    def test_olcut_uygulanamazsa_gecerli_denmez(self):
        from hrma.analysis.structural_analysis import (
            MODEL_VALIDITY_NOT_EVALUATED_BASIS, model_validity_publication,
            structural_model_validity_at)
        kayit = dict(build_materials_view()['steel_4130'])
        assert structural_model_validity_at(None, {'a': 500.0}) is None
        for bozuk in (float('nan'), float('inf'), -1.0, 0.0, True, 'x', None):
            assert structural_model_validity_at(kayit, {'a': bozuk}) is None
        assert structural_model_validity_at(kayit, {}) is None
        egrisiz = dict(kayit, derating_curve={})
        assert structural_model_validity_at(egrisiz, {'a': 500.0}) is None
        erimesiz = dict(kayit, melting_point=None)
        assert structural_model_validity_at(erimesiz, {'a': 500.0}) is None
        yayim = model_validity_publication(None, 'x')
        assert yayim['model_validity_limit_exceeded'] is None
        assert yayim['model_validity_limit_exceeded_basis'] == (
            MODEL_VALIDITY_NOT_EVALUATED_BASIS)
        assert 'verdict_withheld' not in yayim
        # Kayıt + sonlu sıcaklık: ölçüt hibritteki tek kaynaktan.
        ici = structural_model_validity_at(kayit, {'a': 500.0})
        assert ici['model_validity_limit_exceeded'] is False
        disi = structural_model_validity_at(kayit, {'a': 1800.0})
        assert disi['model_validity_limit_exceeded'] is True

    def test_kayitsiz_kasa_malzemesi_gecerli_ilan_edilmez(self, sivi_kati):
        from hrma.analysis.structural_analysis import (
            MODEL_VALIDITY_NOT_EVALUATED_BASIS)
        y = _sivi_kati_yanit('solid', {'case_material': 'composite',
                                       'case_thickness': 4})
        for blok in (y['safety_analysis']['pressure_safety'],
                     y['structural_analysis']['case_analysis']):
            assert blok['model_validity_limit_exceeded'] is None
            assert blok['model_validity_limit_exceeded_basis'] == (
                MODEL_VALIDITY_NOT_EVALUATED_BASIS)


# --- Panel dalı (sıvı/katı şablonları; node altında GERÇEK render) ---------
def _sablon_fonk(html, ad):
    """Şablonun üst düzey fonksiyonunu söker (8 boşluk girinti kuralı;
    tests/test_z5guard_panel_motor.py ile aynı)."""
    bas = html.find('\n        function %s(' % ad)
    assert bas >= 0, ad
    son = html.find('\n        }\n', bas)
    assert son > bas, ad
    return html[bas + 1:son + len('\n        }')]


_SABLON_SONDA = r"""
'use strict';
const fs = require('fs'); const path = require('path'); const vm = require('vm');
const [staticDir, girdiYolu] = process.argv.slice(2);
const P = JSON.parse(fs.readFileSync(girdiYolu, 'utf8'));
function El(t) { this.tagName = String(t).toUpperCase(); this.children = [];
    this.innerHTML = ''; this.className = ''; this.style = {}; }
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
const grid = new El('div');
const depo = {};
const sb = {
    console: { log: function () {}, warn: function () {}, error: function () {} },
    JSON: JSON, Math: Math, Number: Number, Array: Array, Object: Object,
    String: String, Boolean: Boolean, RegExp: RegExp, Date: Date, Intl: Intl,
    isFinite: isFinite, isNaN: isNaN, parseFloat: parseFloat, parseInt: parseInt,
    setTimeout: setTimeout, clearTimeout: clearTimeout,
    document: { readyState: 'complete', addEventListener: function () {},
                querySelectorAll: function () { return []; },
                querySelector: function () { return null; },
                getElementById: function (id) {
                    return id === 'subsystemsGrid' ? grid : null; },
                documentElement: { setAttribute: function () {}, lang: 'en' },
                createElement: function (t) { return new El(t); } },
    localStorage: {
        getItem: function (k) { return (k in depo) ? depo[k] : null; },
        setItem: function (k, v) { depo[k] = String(v); },
        removeItem: function (k) { delete depo[k]; } },
    navigator: { language: 'en-US' },
    matchMedia: function () { return { matches: true }; },
    performance: { now: function () { return 0; } },
    requestAnimationFrame: null,
};
sb.window = sb; sb.globalThis = sb;
vm.createContext(sb);
function kos(f) { vm.runInContext(fs.readFileSync(f, 'utf8'), sb, { filename: f }); }
kos(path.join(staticDir, 'i18n.js'));
kos(path.join(staticDir, 'i18n_common.js'));
kos(path.join(staticDir, 'i18n_pages.js'));
if (sb.I18N.setLang) { sb.I18N.setLang(P.dil); } else { sb.I18N.lang = P.dil; }
vm.runInContext(P.kaynak, sb, { filename: 'sablon-sokum.js' });
const out = {};
if (P.tur === 'liquid') {
    sb.displayEngineeringCards(P.results);
    out.kart = grid.children.length ? grid.children[0].innerHTML : '';
} else {
    const ps = (P.results.safety_analysis || {}).pressure_safety || {};
    out.serit = sb.vesselVerdictHTML(ps);
    out.kasa = sb.generateStructuralAnalysisHTML(P.results);
    out.guvenlik = sb.generateSafetyAnalysisHTML(P.results);
}
console.log(JSON.stringify(out));
"""

_SIVI_SOKUM = ('numTxt', 'unitTxt', 'pctTxt', 'ortakMetin', 'hrmaFmt',
               'liquidOverallLengthMm', 'displayEngineeringCards')
_KATI_SOKUM = ('numTxt', 'fmtNum', 'ortakMetin', 'fmtField', 'fmtTextField',
               'escapeNoticeText', 'solidWallSourceText',
               'solidVesselWallSourceLabel', 'kasaHukumGeriCekildi',
               'solidCaseModelValidityHTML', 'vesselVerdictHTML',
               'generateStructuralAnalysisHTML', 'generateSafetyAnalysisHTML')


def _sablon_render(tur, results, dil, tmp_path):
    import shutil
    import subprocess
    node = shutil.which('node')
    if node is None:
        pytest.skip('node yok: şablon render ölçümü koşamaz (gerekçeli atlama)')
    sablon = 'liquid.html' if tur == 'liquid' else 'solid.html'
    html = (REPO_ROOT / 'hrma' / 'templates' / sablon).read_text(
        encoding='utf-8')
    adlar = _SIVI_SOKUM if tur == 'liquid' else _KATI_SOKUM
    kaynak = '\n'.join(_sablon_fonk(html, ad) for ad in adlar)
    betik = tmp_path / 'sablon_sonda.js'
    betik.write_text(_SABLON_SONDA, encoding='utf-8')
    girdi = tmp_path / ('girdi_%s_%s.json' % (tur, dil))
    girdi.write_text(json.dumps({'tur': tur, 'dil': dil, 'kaynak': kaynak,
                                 'results': _json_guvenli(results)}),
                     encoding='utf-8')
    p = subprocess.run([node, str(betik),
                        str(REPO_ROOT / 'hrma' / 'static' / 'js'), str(girdi)],
                       capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr[-2000:]
    return json.loads(p.stdout.strip().splitlines()[-1])


def _ortak_sozluk(dil):
    """i18n_common.js'teki dil bloğundan anahtar → metin (ürün dosyası)."""
    import re
    kaynak = (REPO_ROOT / 'hrma' / 'static' / 'js' / 'i18n_common.js'
              ).read_text(encoding='utf-8')
    m = re.search(r'^\s{8}%s:\s*\{' % dil, kaynak, re.M)
    assert m, dil
    govde = kaynak[m.end():]
    govde = govde[:govde.index('\n        }')]
    return dict(re.findall(r"^\s*'([^']+)':\s*'(.*)',?$", govde, re.M))


_PANEL_ANAHTAR = {'liquid': 'panel.structural.liquidModelValidityNote',
                  'solid': 'panel.structural.solidCaseModelValidityNote'}


class TestSiviKatiPanelDali:
    """Hüküm şeridinin geçerlilik dalı DAVRANIŞ olarak (render çıktısında):
    bayrak TRUE → SF satırı 'withheld' + rozet + not + kodlar (EN ve TR);
    FALSE → hiçbiri, SF sayısı basılır."""

    @pytest.mark.parametrize('dil', ['en', 'tr'])
    def test_sivi_karti_gecerlilik_disi(self, sivi_kati, tmp_path, dil):
        sz = _ortak_sozluk(dil)
        res = sivi_kati['sivi_radyatif']['yeni']
        kart = _sablon_render('liquid', res, dil, tmp_path)['kart']
        assert sz['panel.structural.badgeModelValidity'] in kart
        assert sz['panel.structural.verdictWithheld'] in kart
        assert sz[_PANEL_ANAHTAR['liquid']] in kart
        for kod in res['structural_analysis']['chamber_structure'][
                'model_validity_reasons']:
            assert kod in kart, kod
        if dil == 'tr':
            assert any(h in sz[_PANEL_ANAHTAR['liquid']]
                       for h in 'çğıöşüÇĞİÖŞÜ')

    def test_sivi_karti_gecerlilik_ici_degismez(self, sivi_kati, tmp_path):
        sz = _ortak_sozluk('en')
        res = sivi_kati['ornek_sivi']['yeni']
        kart = _sablon_render('liquid', res, 'en', tmp_path)['kart']
        assert sz['panel.structural.badgeModelValidity'] not in kart
        assert sz['panel.structural.verdictWithheld'] not in kart
        assert 'model_validity_reasons' not in kart
        assert 'Safety Factor' in kart

    @pytest.mark.parametrize('dil', ['en', 'tr'])
    def test_kati_serit_ve_kartlar_gecerlilik_disi(self, sivi_kati, tmp_path,
                                                   dil):
        sz = _ortak_sozluk(dil)
        res = sivi_kati['kati_erime_ustu']['yeni']
        out = _sablon_render('solid', res, dil, tmp_path)
        for parca in ('serit', 'kasa'):
            assert sz['panel.structural.badgeModelValidity'] in out[parca]
            assert sz[_PANEL_ANAHTAR['solid']] in out[parca]
            assert 'model_validity_reasons' in out[parca]
        for parca in ('kasa', 'guvenlik'):
            assert sz['panel.structural.verdictWithheld'] in out[parca]
        assert '>PASS</span>' not in out['serit']   # onay rozeti yok
        assert '>NOT_EVALUATED</span>' in out['serit']
        assert '#1b7f4b' not in out['serit']   # onay yeşili yok

    def test_kati_gecerlilik_ici_degismez(self, sivi_kati, tmp_path):
        sz = _ortak_sozluk('en')
        res = sivi_kati['ornek_kati']['yeni']
        out = _sablon_render('solid', res, 'en', tmp_path)
        for parca in ('serit', 'kasa', 'guvenlik'):
            assert sz['panel.structural.badgeModelValidity'] not in out[parca]
            assert sz['panel.structural.verdictWithheld'] not in out[parca]
            assert 'model_validity_reasons' not in out[parca]


# ---------------------------------------------------------------------------
# 10) 4. tur (13 Eki 2026; yeniden denetim-3 Ş3-1, Ş3-2, Ş3-3; karar §28-44)
#     — (C) geçerlilik ölçütünün kapsamı HÜKÜM ya da ONAY iddiası taşıyan
#     bütün yapısal yüzeylere genişler: geçerlilik dışında (aynı bayrak)
#     onay/doğrulama yayımlanmaz, sayılar kalır.
#     Kâhinler: (1) materials_db kaydı (erime, düşürme eğrisinin son noktası)
#     ⟷ ucun KENDİ yayımladığı kasa/cidar sıcaklığı; (2) eski davranış =
#     aynı koşu, ölçüt kapalı (``_sivi_kati_yanit(..., gecerlilik_kapali=
#     True)``; main 02bdba81 dışa aktarımıyla aynı olduğu kanıtta ölçüldü,
#     kanit/t4_*); (3) ince cidar P·r/t ⟷ kaydın oda sıcaklığı akması
#     (girdi alanları + kayıt; kod yolundan bağımsız).
# ---------------------------------------------------------------------------
#: Denetim-3 ``kati_celik``: aynı alanlar, steel_4130 kasa (yalnız eğri dalı).
_KATI_CELIK_DISI = dict(_KATI_ERIME_USTU, case_material='steel_4130')
#: Denetim-3 ``kati_fail`` (Ş3-2): 0,3 mm kasa, geçerlilik dışı + FAIL.
_KATI_INCE_FAIL = dict(_KATI_ERIME_USTU, case_thickness=0.3)
#: Denetim-3 ``kati_taut`` (Ş3-3 (iii)): kasa kalınlığı verilmez →
#: boyutlandırma kipi (örnek projede ``case_thickness`` alanı yoktur).
_KATI_BOYUTLANDIRMA = {k: v for k, v in _KATI_ERIME_USTU.items()
                       if k != 'case_thickness'}
#: Denetim-3 ``kati_ici``: geçerlilik içi, kullanıcı cidarı (doğrulama yolu).
_KATI_ICI = {'case_material': 'steel_4130', 'case_thickness': 3,
             'chamber_pressure': 50}
#: Denetim-3 U1'in iki cümlesinin doğrulama imleri (küçük harfle aranır).
_DOGRULAMA_IMLERI = ('verif', 'an evaluation of that wall')


@pytest.fixture(scope='module')
def kati_t4(tmp_path_factory):
    import os
    os.environ.setdefault('HRMA_PROJECTS_DIR',
                          str(tmp_path_factory.mktemp('hrma_projeler_t4')))
    vakalar = {'kati_celik': _KATI_CELIK_DISI, 'kati_fail': _KATI_INCE_FAIL,
               'kati_taut': _KATI_BOYUTLANDIRMA, 'kati_ici': _KATI_ICI}
    return {ad: {'yeni': _sivi_kati_yanit('solid', ek),
                 'eski': _sivi_kati_yanit('solid', ek,
                                          gecerlilik_kapali=True)}
            for ad, ek in vakalar.items()}


def _kati_vaka(sivi_kati, kati_t4, ad):
    return (sivi_kati['kati_erime_ustu'] if ad == 'kati_al'
            else sivi_kati['ornek_kati'] if ad == 'ornek_kati'
            else kati_t4[ad])


def _kasa_kaydi_disi(y):
    """Kâhin (1): ucun kasa sıcaklığı kayda göre geçerlilik dışında mı."""
    T = y['thermal_analysis']['heat_transfer']['case_temperature_k']
    erime, egri_son = _kayit(
        y['safety_analysis']['pressure_safety']['case_material'])
    return T >= erime or T > egri_son


class TestKatiDogrulamaCumleleri:
    """Ş3-1 (app.py): geçerlilik dışı katıda ``pressure_safety.
    vessel_status_basis`` ve ``case_geometry.note`` doğrulama iddiası
    taşımaz, aynı yanıttaki tanı künyesine (``model_validity_*``) bağlanır;
    geçerlilik içinde iki cümle eski davranışla bit-aynı."""

    @pytest.mark.parametrize('ad', ['kati_al', 'kati_celik', 'kati_taut'])
    def test_gecerlilik_disi_iki_cumle_dogrulama_demez(self, sivi_kati,
                                                       kati_t4, ad):
        v = _kati_vaka(sivi_kati, kati_t4, ad)
        y, z = v['yeni'], v['eski']
        assert _kasa_kaydi_disi(y)
        ps = y['safety_analysis']['pressure_safety']
        ca = y['structural_analysis']['case_analysis']
        assert ps['model_validity_limit_exceeded'] is True
        assert ca['model_validity_limit_exceeded'] is True
        assert ps['vessel_status'] not in _KAP_ONAY
        yeni = {'vessel_status_basis': ps['vessel_status_basis'],
                'note': y['case_geometry']['note']}
        eski = {'vessel_status_basis': z['safety_analysis'][
                    'pressure_safety']['vessel_status_basis'],
                'note': z['case_geometry']['note']}
        for alan, metin in yeni.items():
            kucuk = metin.lower()
            for im in _DOGRULAMA_IMLERI:
                assert im not in kucuk, (ad, alan, metin)
            # Tanı cümlesi aynı yanıttaki künyeye bağlanır.
            assert 'model_validity_limit_exceeded' in metin, (ad, alan)
            assert 'diagnostic' in kucuk, (ad, alan)
            # Eski davranış (ölçüt kapalı) bu alanda doğrulama diyordu.
            assert any(im in eski[alan].lower()
                       for im in _DOGRULAMA_IMLERI), (ad, alan, eski[alan])

    @pytest.mark.parametrize('ad', ['kati_ici', 'ornek_kati'])
    def test_gecerlilik_ici_iki_cumle_bit_ayni(self, sivi_kati, kati_t4, ad):
        v = _kati_vaka(sivi_kati, kati_t4, ad)
        y, z = v['yeni'], v['eski']
        assert not _kasa_kaydi_disi(y)
        assert y['safety_analysis']['pressure_safety'][
            'model_validity_limit_exceeded'] is False
        assert (y['safety_analysis']['pressure_safety']['vessel_status_basis']
                == z['safety_analysis']['pressure_safety'][
                    'vessel_status_basis'])
        assert y['case_geometry']['note'] == z['case_geometry']['note']
        a = dict(_duzle(y))
        e = dict(_duzle(z))
        fark = sorted(k for k in set(a) | set(e)
                      if a.get(k, '<YOK>') != e.get(k, '<YOK>'))
        disari = [k for k in fark if '.model_validity_' not in k]
        assert not disari, disari[:5]


class TestKatiFailSusturulmaz:
    """Ş3-2: karar §28-24 (C) sözleşmesi "onay geri çekilir, FAIL/MARGINAL
    susturulmaz" katıda. Kâhin: ince cidarda P·r/t, kaydın oda sıcaklığı
    akmasını aşıyor ⇒ SF < 1 ⇒ kap hükmü bir UYARIDIR (FAIL), geçerlilik
    dışında da NOT_EVALUATED'a çekilmez."""

    def test_ince_cidar_fail_gecerlilik_disinda_korunur(self, kati_t4):
        y = kati_t4['kati_fail']['yeni']
        assert _kasa_kaydi_disi(y)
        with open(REPO_ROOT / 'examples' / 'Example Solid KNDX BATES 75mm.hrma',
                  encoding='utf-8') as f:
            alanlar = json.load(f)['inputs']['fields']
        alanlar.update(_KATI_INCE_FAIL)
        P = float(alanlar['chamber_pressure']) * 1e5          # Pa
        r = (float(alanlar['outer_diameter']) / 2.0
             + float(alanlar['insulation_thickness'])) / 1000.0  # m
        t = float(alanlar['case_thickness']) / 1000.0           # m
        akma = float(build_materials_view()[alanlar['case_material']][
            'yield_strength'])
        assert P * r / t > akma                    # ⇒ SF < 1 (kâhin)
        ps = y['safety_analysis']['pressure_safety']
        ca = y['structural_analysis']['case_analysis']
        for blok in (ps, ca):
            assert blok['model_validity_limit_exceeded'] is True
            assert blok['verdict_withheld'] is True
        assert ps['vessel_status'] == 'FAIL'
        # Eski davranışta da FAIL idi: ölçüt uyarıyı değiştirmez.
        assert kati_t4['kati_fail']['eski']['safety_analysis'][
            'pressure_safety']['vessel_status'] == 'FAIL'


_KAPAK_SAYILARI = ('head_safety_factor', 'flat_head_thickness',
                   'dished_head_thickness', 'head_thickness_used_mm',
                   'yield_strength_used_MPa', 'head_safety_factor_by_type',
                   'asme_ug34_flat_head_thickness', 'status')


class TestKapakHukmu:
    """Ş3-3 (i), karar §28-44: sıvı ve katı ``end_cap_analysis`` geçerlilik
    dışında (hazne/kasa ile AYNI bayrak) onay taşımaz: bayrak + künye +
    ``verdict_withheld``; katıda "sized and verified" ``_basis``i tanı
    künyesine döner. Sayılar ve ``status`` (CAD bu alandan okur) aynı;
    geçerlilik içinde blok bit-aynı."""

    @pytest.mark.parametrize('ad', ['kati_al', 'kati_celik', 'kati_taut'])
    def test_kati_kapak_gecerlilik_disi(self, sivi_kati, kati_t4, ad):
        from hrma.analysis.structural_analysis import (
            SOLID_CASE_MODEL_VALIDITY_BASIS,
            STRUCTURAL_MODEL_VALIDITY_WITHHELD_REASON)
        from hrma.engines.solid_rocket_engine import SolidRocketEngine
        v = _kati_vaka(sivi_kati, kati_t4, ad)
        y, z = v['yeni'], v['eski']
        assert _kasa_kaydi_disi(y)
        ca = y['structural_analysis']['case_analysis']
        ec = y['structural_analysis']['end_cap_analysis']
        ec_eski = z['structural_analysis']['end_cap_analysis']
        assert ec['model_validity_limit_exceeded'] is True
        assert ec['model_validity_reasons'] == ca['model_validity_reasons']
        assert ec['model_validity_limit_exceeded_basis'] == (
            SOLID_CASE_MODEL_VALIDITY_BASIS)
        assert ec['verdict_withheld'] is True
        assert ec['verdict_withheld_reasons'] == [
            STRUCTURAL_MODEL_VALIDITY_WITHHELD_REASON]
        assert ec['_basis'] == SolidRocketEngine.END_CAP_MODEL_VALIDITY_BASIS
        assert 'verified' not in ec['_basis'].lower()
        assert 'sized and verified' in ec_eski['_basis']   # eski davranış
        for alan in _KAPAK_SAYILARI:
            assert ec[alan] == ec_eski[alan], alan
        # Uç kopyası (motor_geometry) aynı bloğu taşır.
        assert (y['motor_geometry']['structural_analysis']['end_cap_analysis']
                == ec)

    def test_sivi_kapak_gecerlilik_disi(self, sivi_kati):
        from hrma.analysis.structural_analysis import (
            LIQUID_MODEL_VALIDITY_BASIS,
            STRUCTURAL_MODEL_VALIDITY_WITHHELD_REASON)
        y = sivi_kati['sivi_radyatif']['yeni']
        z = sivi_kati['sivi_radyatif']['eski']
        cs = y['structural_analysis']['chamber_structure']
        ec = y['structural_analysis']['end_cap_analysis']
        ec_eski = z['structural_analysis']['end_cap_analysis']
        erime, egri_son = _kayit(cs['material_key'])
        assert cs['wall_temperature'] >= erime
        assert ec['model_validity_limit_exceeded'] is True
        assert ec['model_validity_reasons'] == cs['model_validity_reasons']
        # Kapak dayanımı haznenin AYNI sıcaklığından düşürülür (aynı bayrak).
        assert (ec['model_validity_evaluations']['chamber_hot_wall'][
            'wall_temperature_K'] == cs['wall_temperature'])
        assert ec['model_validity_limit_exceeded_basis'] == (
            LIQUID_MODEL_VALIDITY_BASIS)
        assert ec['verdict_withheld'] is True
        assert ec['verdict_withheld_reasons'] == [
            STRUCTURAL_MODEL_VALIDITY_WITHHELD_REASON]
        for alan in _KAPAK_SAYILARI + ('_basis',):
            assert ec[alan] == ec_eski[alan], alan
        assert 'verdict_withheld' not in ec_eski

    @pytest.mark.parametrize('ad', ['ornek_sivi', 'ornek_kati', 'kati_ici'])
    def test_kapak_gecerlilik_ici_bit_ayni(self, sivi_kati, kati_t4, ad):
        v = (sivi_kati[ad] if ad in sivi_kati else kati_t4[ad])
        assert (v['yeni']['structural_analysis']['end_cap_analysis']
                == v['eski']['structural_analysis']['end_cap_analysis'])

    @pytest.mark.parametrize('ad', ['kati_celik', 'kati_fail', 'kati_taut'])
    def test_gecerlilik_disi_yalniz_hukum_yuzeyleri_degisir(self, kati_t4,
                                                             ad):
        """4. turun sözleşmesi: geçerlilik dışında değişen yapraklar yalnız
        hüküm yüzeyleridir (3. turun dört alanı + bu turun iki doğrulama
        cümlesi ve kapak ``_basis``i)."""
        a = dict(_duzle(kati_t4[ad]['yeni']))
        e = dict(_duzle(kati_t4[ad]['eski']))
        fark = sorted(k for k in set(a) | set(e)
                      if a.get(k, '<YOK>') != e.get(k, '<YOK>'))
        izinli = ('.model_validity_', '.verdict_withheld',
                  '.safety_factor_basis', '.vessel_status',
                  'case_geometry.note', 'end_cap_analysis._basis')
        disari = [k for k in fark if not any(i in k for i in izinli)]
        assert not disari, disari[:5]
        assert any(k.endswith('end_cap_analysis.verdict_withheld')
                   for k in fark)


def test_dock_cidar_kunyesi_hukum_rozeti_tasimaz():
    """Ş3-3 (iv) ölçümü: ``analysis_dock.js``in sıvı/katı cidar okuması
    (WALL_PROVENANCE_PATHS → readWallThicknessProvenance) YALNIZ künye
    sınıfı döndürür; hüküm rozeti ya da onay rengi basmaz (rozet ve hüküm
    structural_panel.js'te, ucun kendi geçerlilik ölçütüyle). Bu bölgeye
    rozet/onay rengi eklenirse geçerlilik dalı da eklenmelidir (karar
    §28-44 (iv))."""
    kaynak = (REPO_ROOT / 'hrma' / 'static' / 'js' / 'analysis_dock.js'
              ).read_text(encoding='utf-8')
    bas = kaynak.index('const WALL_PROVENANCE_PATHS = {')
    son = kaynak.index('ÖNERİ GERİ ÇEKME', bas)
    bolge = kaynak[bas:son]
    assert 'readWallThicknessProvenance' in bolge
    for yasak in ('badge(', "kindColor('ok')", 'KIND_COLORS.ok', 'hd-green',
                  '#2dd4a8', '#1b7f4b', 'VERDICT', 'innerHTML'):
        assert yasak not in bolge, yasak


# ---------------------------------------------------------------------------
# 9) 5. tur (14 Eki; 4. tur devir 1, ana model kararı) — DOCK YAPISAL PANELİ
#    Motorun KENDİ künye bloğu (WALL_PROVENANCE_PATHS: katı case_analysis,
#    sıvı chamber_structure) ``model_validity_limit_exceeded: true`` derken
#    panel, aynı cidarın SICAKLIKSIZ (300 K) koşumundan onay/doğrulama
#    iddiası basmaz. Akış dock'un kendisi: motor yanıtı → fromResults →
#    buildPayload kuralı → /analyze_structural_safety → render (hepsi gerçek).
# ---------------------------------------------------------------------------
_DOCK_EV = (
    "var spec = window.AnalysisDock._registry.filter(function (s) {"
    "  return s.id === 'structural'; })[0];"
    "try { window.AnalysisDock.init({motorType: body.motorType,"
    "  resultsProvider: function () { return body.motor; }}); } catch (e) {}"
    "var sug = spec.fromResults(body.motor);"
    "var out = {suggested: sug, html: null, fields: spec.fields};"
    "if (body.endpoint) { var root = document.createElement('div');"
    "  spec.render(body.endpoint, root); out.html = root.innerHTML; }"
    "return out;")
#: Ekranda onay/doğrulama İDDİASI sayılan ifadeler (olumsuzlar — "not a
#: verification", "not verified" — ve makine alan adları — is_verification_
#: scope — bilerek dışarıda: bunlar iddia değil, geri çekmedir).
_DOCK_ONAY_IDDIASI = (r'\bSAFE\b', r'\bACCEPTABLE\b', r'\bPASS\b',
                      r'VERDICT ISSUED', r'verifies', r'is a verification',
                      r'independent verification', r'would pass')
#: Motorun künye bloğu (analysis_dock.js WALL_PROVENANCE_PATHS ile aynı ad).
_DOCK_KUNYE_BLOGU = {'solid': 'case_analysis', 'liquid': 'chamber_structure',
                     'hybrid': 'chamber_analysis'}
#: Başarısız hükümler: bayrak TRUE iken de SUSTURULMAZ (§28-44 deseni).
_DOCK_BASARISIZ = r'\b(?:UNSAFE|MARGINAL|CRITICAL|FAIL)\b'
_DOCK_VAKA = {'kati_erime_ustu': 'solid', 'sivi_radyatif': 'liquid',
              'ornek_kati': 'solid', 'ornek_sivi': 'liquid'}


def _dock_node(tur, motor, endpoint=None):
    import shutil
    import subprocess
    from tests.support.kanit import kanit_gerekli
    node = shutil.which('node')
    if node is None:
        pytest.skip('node yok: dock paneli ölçümü koşamaz (gerekçeli atlama)')
    cfg = {'panelId': '_yok',
           'panelFiles': ['hrma/static/js/panels/structural_panel.js'],
           'dataInline': {'motorType': tur, 'motor': motor,
                          'endpoint': endpoint},
           'evalFn': _DOCK_EV}
    p = subprocess.run([node, kanit_gerekli(str(_PANEL_HARNESS))],
                       input=json.dumps(cfg), capture_output=True, text=True,
                       timeout=180)
    assert p.returncode == 0, p.stderr[-2000:]
    ev = json.loads(p.stdout)['evaled']
    assert not ev.get('_err'), ev.get('_err')
    return ev


def _dock_yuku(fields, sug):
    """analysis_dock.js buildPayload: seçici değeri + yalnız sonlu sayılar."""
    out = {}
    for f in fields:
        k, var = f[0], f[2]
        v = sug.get(k) if sug.get(k) is not None else var
        if isinstance(f[3], list) or k == 'material':
            out[k] = v
            continue
        try:
            x = float(v)
        except (TypeError, ValueError):
            continue
        if math.isfinite(x):
            out[k] = x
    return out


def _dock_akisi(tur, motor):
    from hrma.app import app
    motor = _json_guvenli(motor)
    ev = _dock_node(tur, motor)
    yuk = _dock_yuku(ev['fields'], ev['suggested'])
    r = app.test_client().post('/analyze_structural_safety', json=yuk)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    uc = _json_guvenli(r.get_json())
    html = _dock_node(tur, motor, uc)['html'] or ''
    import re
    return {'html': html, 'uc': uc,
            'metin': ' '.join(re.sub(r'<[^>]*>', ' ', html).split())}


@pytest.fixture(scope='module')
def dock_paneli(sivi_kati):
    return {ad: _dock_akisi(tur, sivi_kati[ad]['yeni'])
            for ad, tur in _DOCK_VAKA.items()}


def _uc_onay_sayisi(uc):
    """Ucun KENDİ yanıtındaki onay hükmü yaprakları (ön koşul: bekçi boş
    çalışmasın — uç 300 K'de onay yayımlıyor olmalı)."""
    return sum(1 for k, v in _duzle(uc)
               if isinstance(v, str) and v.upper() in _KAP_ONAY
               and k.split('.')[-1] in ('status', 'fatigue_status',
                                         'earned_scope_status'))


class TestDockPaneliGecerlilik:

    @pytest.mark.parametrize('ad', ['kati_erime_ustu', 'sivi_radyatif'])
    def test_gecerlilik_disi_onay_iddiasi_yok(self, sivi_kati, dock_paneli,
                                              ad):
        import re
        tur = _DOCK_VAKA[ad]
        blok = sivi_kati[ad]['yeni']['structural_analysis'][
            _DOCK_KUNYE_BLOGU[tur]]
        assert blok['model_validity_limit_exceeded'] is True
        d = dock_paneli[ad]
        # Ön koşul: uç bu koşumda onay yayımlıyor (panel onu basmamalı).
        assert _uc_onay_sayisi(d['uc']) >= 1, ad
        for desen in _DOCK_ONAY_IDDIASI:
            assert not re.search(desen, d['html']), (ad, desen)
        assert 'withheld' in d['metin']
        assert 'VERDICT WITHHELD' in d['metin']
        assert ('model_validity_limit_exceeded true · motor.structural_'
                'analysis.' + _DOCK_KUNYE_BLOGU[tur]) in d['metin']
        assert 'diagnostic only' in d['metin']
        for kod in blok['model_validity_reasons']:
            assert kod in d['metin'], kod

    @pytest.mark.parametrize('ad', ['ornek_kati', 'ornek_sivi'])
    def test_gecerlilik_ici_bit_ayni(self, sivi_kati, dock_paneli, ad):
        """Bayrak FALSE ⟷ bayrak alanları HİÇ yok: panel çıktısı bit-aynı
        (eski panel bayrağı hiç okumuyordu; kanit/t5_dock_panel_kiyas.json
        main ⟷ dal sha256 eşitliğini ayrıca ölçer). Onaylar susturulmaz."""
        import re
        tur = _DOCK_VAKA[ad]
        motor = json.loads(json.dumps(_json_guvenli(sivi_kati[ad]['yeni'])))
        blok = motor['structural_analysis'][_DOCK_KUNYE_BLOGU[tur]]
        assert blok['model_validity_limit_exceeded'] is False
        for k in [k for k in blok if k.startswith('model_validity')]:
            del blok[k]
        d = dock_paneli[ad]
        assert _dock_akisi(tur, motor)['html'] == d['html']
        assert re.search(r'\bSAFE\b|\bACCEPTABLE\b', d['html']), ad
        assert 'model_validity_limit_exceeded true' not in d['metin']
        assert 'diagnostic only' not in d['metin']


def _bayraksiz(motor, tur):
    """Motor yanıtının kopyası; künye bloğunun ``model_validity*`` alanları
    silinmiş (eski panel bayrağı hiç okumuyordu: eski davranışın kâhini)."""
    m = json.loads(json.dumps(_json_guvenli(motor)))
    blok = (m.get('motor') or m)['structural_analysis'][
        _DOCK_KUNYE_BLOGU[tur]]
    for k in [k for k in blok if k.startswith('model_validity')]:
        del blok[k]
    return m


class TestDockPaneliBasarisizSusturulmaz:

    @pytest.mark.parametrize('ad', ['kati_erime_ustu', 'sivi_radyatif'])
    def test_basarisiz_hukum_sayisi_ayni(self, sivi_kati, dock_paneli, ad):
        import re
        tur = _DOCK_VAKA[ad]
        eski = _dock_akisi(tur, _bayraksiz(sivi_kati[ad]['yeni'], tur))
        n = len(re.findall(_DOCK_BASARISIZ, eski['metin']))
        assert n >= 1, ad   # ön koşul: bu koşumda başarısız hüküm var
        assert len(re.findall(_DOCK_BASARISIZ, dock_paneli[ad]['metin'])) == n

    def test_hibrit_sicaklik_tasininca_panel_karismaz(self, ornek_hibrit):
        """Hibrit örnek: motorun chamber_analysis bayrağı TRUE ama motorun
        çözülmüş cidar sıcaklığı (heat_transfer_module) uca gidiyor; uç aynı
        ölçütü o sıcaklıkta KENDİSİ uyguluyor (kendi bayrağı TRUE, gerekçesi
        MODEL_VALIDITY_VERDICT_BASIS). Panel ikinci kez karışmaz: çıktı,
        bayrak alanları silinmiş motor yanıtıyla bit-aynı."""
        from hrma.analysis.structural_analysis import (
            MODEL_VALIDITY_VERDICT_BASIS)
        md = ornek_hibrit.get('motor') or ornek_hibrit
        assert md['structural_analysis']['chamber_analysis'][
            'model_validity_limit_exceeded'] is True
        ev = _dock_node('hybrid', _json_guvenli(ornek_hibrit))
        sug = ev['suggested']
        assert isinstance(sug['wall_temperature_hot'], float)
        assert isinstance(sug['wall_temperature_cold'], float)
        d = _dock_akisi('hybrid', ornek_hibrit)
        sf = d['uc']['structural_analysis']['safety_analysis']
        assert sf['model_validity_limit_exceeded'] is True
        assert MODEL_VALIDITY_VERDICT_BASIS in d['metin']
        eski = _dock_akisi('hybrid', _bayraksiz(ornek_hibrit, 'hybrid'))
        assert d['html'] == eski['html']

    def test_uc_kendisi_gecerlilik_disiyken_tani_gerekcesi_basilir(
            self, sivi_kati):
        """Katı sayfa (motor sıcaklığı uca gitmez → kapı açık), ama kullanıcı
        cidar sıcaklığı alanlarını motorun kasa sıcaklığıyla elle doldurmuş:
        uç kendi bayrağını TRUE yayımlar ve gerekçesi zaten tanı cümlesidir
        (MODEL_VALIDITY_VERDICT_BASIS) — panel onu silmez; onay yine yok."""
        import re
        from hrma.analysis.structural_analysis import (
            MODEL_VALIDITY_VERDICT_BASIS)
        from hrma.app import app
        motor = _json_guvenli(sivi_kati['kati_erime_ustu']['yeni'])
        blok = motor['structural_analysis']['case_analysis']
        assert blok['model_validity_limit_exceeded'] is True
        T = [v['wall_temperature_K'] for v in
             blok['model_validity_evaluations'].values()
             if isinstance(v, dict) and isinstance(
                 v.get('wall_temperature_K'), float)]
        assert T, blok['model_validity_evaluations']
        ev = _dock_node('solid', motor)
        assert ev['suggested'].get('wall_temperature_hot') in (None, '')
        yuk = _dock_yuku(ev['fields'], ev['suggested'])
        yuk.update(wall_temperature_hot=max(T), wall_temperature_cold=max(T))
        r = app.test_client().post('/analyze_structural_safety', json=yuk)
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        uc = _json_guvenli(r.get_json())
        sf = uc['structural_analysis']['safety_analysis']
        assert sf['model_validity_limit_exceeded'] is True
        assert sf['minimum_safety_factor_verdict_basis'] == (
            MODEL_VALIDITY_VERDICT_BASIS)
        html = _dock_node('solid', motor, uc)['html'] or ''
        metin = ' '.join(re.sub(r'<[^>]*>', ' ', html).split())
        assert MODEL_VALIDITY_VERDICT_BASIS in metin
        assert 'model_validity_limit_exceeded true' in metin
        for desen in _DOCK_ONAY_IDDIASI:
            assert not re.search(desen, html), desen


def test_dock_gecerlilik_notu_tr_karsiligi_var(tmp_path):
    """Yeni iki anahtar (EN = panelin yedek metni, TR çevrili)."""
    import shutil
    import subprocess
    node = shutil.which('node')
    if node is None:
        pytest.skip('node yok: TR sözlük ölçümü koşamaz (gerekçeli atlama)')
    betik = tmp_path / 'i18n_sonda.js'
    betik.write_text(r"""
const fs = require('fs'), path = require('path'), vm = require('vm');
const d = process.argv[2];
const sb = { console: console, JSON: JSON, Math: Math, Object: Object,
  Array: Array, String: String, RegExp: RegExp, Number: Number,
  localStorage: { getItem: function () { return null; },
                  setItem: function () {} },
  navigator: { language: 'en-US' },
  document: { readyState: 'complete', addEventListener: function () {},
    querySelectorAll: function () { return []; },
    querySelector: function () { return null; },
    getElementById: function () { return null; },
    documentElement: { setAttribute: function () {}, lang: 'en' } } };
sb.window = sb; vm.createContext(sb);
['i18n.js', 'i18n_common.js'].forEach(function (f) {
  vm.runInContext(fs.readFileSync(path.join(d, f), 'utf8'), sb); });
const k = ['panel.structural.motorModelValidityNote',
           'panel.structural.diagnosticOnly'];
const out = {};
['en', 'tr'].forEach(function (dil) {
  if (sb.I18N.setLang) { sb.I18N.setLang(dil); } else { sb.I18N.lang = dil; }
  out[dil] = k.map(function (x) { return sb.I18N.t(x, '<YOK>'); });
});
console.log(JSON.stringify(out));
""", encoding='utf-8')
    p = subprocess.run([node, str(betik),
                        str(REPO_ROOT / 'hrma' / 'static' / 'js')],
                       capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr[-2000:]
    out = json.loads(p.stdout.strip().splitlines()[-1])
    panel = (REPO_ROOT / 'hrma' / 'static' / 'js' / 'panels'
             / 'structural_panel.js').read_text(encoding='utf-8')
    for en, tr in zip(out['en'], out['tr']):
        assert en != '<YOK>' and tr != '<YOK>' and en != tr
        assert any(h in tr for h in 'çğıöşüÇĞİÖŞÜ'), tr[:80]
    # EN sözlük metni panelin yedek metniyle aynı (EN = fallback).
    assert "'diagnostic only'" in panel
    assert out['en'][1] == 'diagnostic only'
    assert out['en'][0].replace("'", "\\'")[:40] in panel


# ---------------------------------------------------------------------------
# 6. tur (14 Eki; karar §28-44, 5. tur devir 1) — UÇ /analyze_structural_safety
# KENDİ GEÇERLİLİK BAYRAĞI TRUE İKEN ONAY YAYIMLAMAZ.
#    Ölçülen kusur (kanit/t6_uc_once.json): hibrit örneğin dock akışında uç
#    ``safety_analysis.model_validity_limit_exceeded = true`` iken
#    ``design_target_assessment`` 'SAFE · VERY LOW' ve
#    ``buckling_analysis.axial_buckling_status`` 'SAFE'; sıvı radyatif yükte
#    ayrıca ``fatigue_analysis.fatigue_status`` 'SAFE'.
#    Eski davranışın kâhini: AYNI hesap, yalnız ``safety_analysis``in bayrak
#    alanı silinmiş (uç kapısı bayrağı göremez) — bkz. ``_uc_bayraksiz``.
# ---------------------------------------------------------------------------
#: Ucun onay/doğrulama iddiası taşıyabilen hüküm yaprakları (alan adları).
#: ``bolt_layout_status`` (cıvata adımı geometrisi, sıcaklıktan bağımsız) ve
#: ``wall_thickness_input_status`` (girdi sınıfı) hüküm DEĞİLDİR.
_UC_HUKUM_ALANLARI = ('status', 'risk_level', 'fatigue_status',
                      'axial_buckling_status', 'earned_scope_status',
                      'earned_scope_risk_level', 'measured_scope_status',
                      'measured_scope_risk_level')
#: Onay ve onay riski (risk_level onayın ikizidir: 'VERY LOW' / 'LOW').
_UC_ONAY_DEGERLERI = ('PASS', 'SAFE', 'ACCEPTABLE', 'OK', 'VERY LOW', 'LOW')
_UC_BASARISIZ_DEGERLERI = ('UNSAFE', 'MARGINAL', 'CRITICAL', 'FAIL')


def _uc_hukum_yapraklari(uc, degerler):
    return sorted(k for k, v in _duzle(uc)
                  if isinstance(v, str) and v.upper() in degerler
                  and k.split('.')[-1] in _UC_HUKUM_ALANLARI)


def _uc_cagir(yuk, bayraksiz=False):
    """Gerçek uç çağrısı. ``bayraksiz``: analizör sonucu aynı, yalnız
    ``safety_analysis.model_validity_limit_exceeded`` silinmiş (eski
    davranışın kâhini — uç kapısı bayrağı okuyamaz)."""
    import hrma.app as uygulama
    import hrma.analysis.structural_analysis as yapi_modulu
    asil = uygulama.StructuralAnalyzer
    asil_geri_cek = yapi_modulu.withhold_model_validity_approvals

    class _Bayraksiz(asil):
        def analyze_structure(self, *a, **k):
            r = super().analyze_structure(*a, **k)
            r['safety_analysis'].pop('model_validity_limit_exceeded', None)
            return r

    if bayraksiz:
        uygulama.StructuralAnalyzer = _Bayraksiz
        # 7. tur (dört koşul, rapor): geri çekme ARTIK modülde; eski
        # davranışın kâhini o işlevi de devre dışı bırakır.
        yapi_modulu.withhold_model_validity_approvals = lambda bloklar: []
    try:
        r = uygulama.app.test_client().post('/analyze_structural_safety',
                                            json=yuk)
    finally:
        uygulama.StructuralAnalyzer = asil
        yapi_modulu.withhold_model_validity_approvals = asil_geri_cek
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return _json_guvenli(r.get_json())


def _elle_sicak_yuk(motor, tur):
    """Dock akışının yükü + kullanıcının cidar sıcaklığı alanlarını motorun
    KENDİ değerlendirdiği en yüksek cidar sıcaklığıyla doldurması (motor
    künyesi bu sıcaklığı geçerlilik dışı buluyor)."""
    motor = _json_guvenli(motor)
    blok = motor['structural_analysis'][_DOCK_KUNYE_BLOGU[tur]]
    assert blok['model_validity_limit_exceeded'] is True
    T = [v['wall_temperature_K'] for v in
         blok['model_validity_evaluations'].values()
         if isinstance(v, dict) and isinstance(
             v.get('wall_temperature_K'), float)]
    assert T, blok['model_validity_evaluations']
    ev = _dock_node(tur, motor)
    yuk = _dock_yuku(ev['fields'], ev['suggested'])
    yuk.update(wall_temperature_hot=max(T), wall_temperature_cold=max(T))
    return yuk


@pytest.fixture(scope='module')
def uc_gecerlilik_disi(sivi_kati, ornek_hibrit):
    """Üç geçerlilik dışı uç yanıtı: hibrit örnek DOCK AKIŞI (motor sıcaklığı
    uca gider) + katı / sıvı uç çağrısı (sıcaklık elle)."""
    d = _dock_akisi('hybrid', ornek_hibrit)
    ev = _dock_node('hybrid', _json_guvenli(ornek_hibrit))
    hibrit_yuk = _dock_yuku(ev['fields'], ev['suggested'])
    yuklar = {'hibrit_dock': hibrit_yuk,
              'kati_elle': _elle_sicak_yuk(
                  sivi_kati['kati_erime_ustu']['yeni'], 'solid'),
              'sivi_elle': _elle_sicak_yuk(
                  sivi_kati['sivi_radyatif']['yeni'], 'liquid')}
    out = {ad: {'yuk': y, 'yeni': _uc_cagir(y),
                'eski': _uc_cagir(y, bayraksiz=True)}
           for ad, y in yuklar.items()}
    out['hibrit_dock']['dock'] = d
    return out


class TestUcKendiBayragiOnayYok:

    @pytest.mark.parametrize('ad', ['hibrit_dock', 'kati_elle', 'sivi_elle'])
    def test_onay_yok_withheld_var(self, uc_gecerlilik_disi, ad):
        from hrma.analysis.structural_analysis import (
            STRUCTURAL_MODEL_VALIDITY_WITHHELD_REASON,
            STRUCTURAL_VERDICT_NOT_EVALUATED)
        v = uc_gecerlilik_disi[ad]
        sa = v['yeni']['structural_analysis']['safety_analysis']
        assert sa['model_validity_limit_exceeded'] is True
        # Ön koşul (bekçi boş çalışmasın): eski davranış bu yükte onay
        # yayımlıyordu.
        assert _uc_hukum_yapraklari(v['eski'], _UC_ONAY_DEGERLERI), ad
        assert _uc_hukum_yapraklari(v['yeni'], _UC_ONAY_DEGERLERI) == [], ad
        dta = sa['design_target_assessment']
        geri = sa['model_validity_approvals_withheld']
        # V3 KK (YP7 devri, 14 Eki): dock yükü artık motorun KENDİ tasarım
        # SF hedefini taşır (örnek sıvı 2,5; eskiden malzeme varsayılanı
        # 3,0). Hedef 2,5'te design_target_assessment bir ONAY değil,
        # MARGINAL'dir — §28-44: başarısız hüküm susturulmaz. Geri çekme
        # yalnız eski (bayraksız) yanıtta onay olan hükme uygulanır.
        dta_eski = v['eski']['structural_analysis']['safety_analysis'][
            'design_target_assessment']
        if str(dta_eski['status']).upper() in _UC_ONAY_DEGERLERI:
            assert dta['status'] == STRUCTURAL_VERDICT_NOT_EVALUATED
            assert dta['risk_level'] == STRUCTURAL_VERDICT_NOT_EVALUATED
            assert dta['status_withheld_because'] == (
                STRUCTURAL_MODEL_VALIDITY_WITHHELD_REASON)
            assert 'safety_analysis.design_target_assessment.status' in geri
        else:
            assert str(dta_eski['status']).upper() in (
                _UC_BASARISIZ_DEGERLERI), (ad, dta_eski['status'])
            assert dta['status'] == dta_eski['status'], ad
            assert 'safety_analysis.design_target_assessment.status' not in (
                geri)
        assert v['yeni']['design_basis']['verdict'] == 'withheld'
        for yol in geri:
            blok_yolu, alan = yol.rsplit('.', 1)
            blok = v['yeni']['structural_analysis']
            for p in blok_yolu.split('.'):
                blok = blok[p]
            assert blok[alan] == STRUCTURAL_VERDICT_NOT_EVALUATED
            assert blok[alan + '_withheld_because'] == (
                STRUCTURAL_MODEL_VALIDITY_WITHHELD_REASON)

    @pytest.mark.parametrize('ad', ['hibrit_dock', 'kati_elle', 'sivi_elle'])
    def test_yalniz_onaylar_degisir_sayilar_ve_basarisizlar_ayni(
            self, uc_gecerlilik_disi, ad):
        """Başarısız hüküm sayısı aynı (F4-2: uyarı susturulmaz) ve
        değişen tek yaprak geri çekilen onaylardır; sayılar tanı olarak
        yerinde (bit-aynı)."""
        v = uc_gecerlilik_disi[ad]
        bas_eski = _uc_hukum_yapraklari(v['eski'], _UC_BASARISIZ_DEGERLERI)
        assert bas_eski, ad   # ön koşul: bu koşumda başarısız hüküm var
        assert _uc_hukum_yapraklari(
            v['yeni'], _UC_BASARISIZ_DEGERLERI) == bas_eski
        eski, yeni = dict(_duzle(v['eski'])), dict(_duzle(v['yeni']))
        sa = 'structural_analysis.safety_analysis.'
        geri = v['yeni']['structural_analysis']['safety_analysis'][
            'model_validity_approvals_withheld']
        beklenen = {sa + 'model_validity_limit_exceeded'}
        for yol in geri:
            beklenen.add('structural_analysis.' + yol)
            beklenen.add('structural_analysis.' + yol + '_withheld_because')
        beklenen.add(sa + 'design_target_assessment.risk_level')
        beklenen.update(k for k in yeni
                        if k.startswith(sa + 'model_validity_approvals_'))
        degisen = {k for k in set(eski) | set(yeni)
                   if eski.get(k, '<yok>') != yeni.get(k, '<yok>')}
        assert degisen <= beklenen, sorted(degisen - beklenen)
        for k, x in yeni.items():
            if isinstance(x, (int, float)) and not isinstance(x, bool):
                assert eski[k] == x, k

    def test_hibrit_dock_paneli_safe_basmaz(self, uc_gecerlilik_disi):
        import re
        d = uc_gecerlilik_disi['hibrit_dock']['dock']
        assert d['uc']['structural_analysis']['safety_analysis'][
            'model_validity_limit_exceeded'] is True
        dta_satiri = re.search(r'design_target_assessment(.*?)(?:'
                               r'verdict_safety_factor|$)', d['metin'])
        assert dta_satiri, d['metin'][:400]
        assert 'status: NOT_EVALUATED' in dta_satiri.group(1)
        assert not re.search(r'\bSAFE\b|VERY LOW', d['metin']), (
            re.findall(r'.{60}\bSAFE\b.{20}', d['metin']))
        assert 'withheld' in d['metin']
        assert re.search(_DOCK_BASARISIZ, d['metin'])

    @pytest.mark.parametrize('ad', ['ornek_kati', 'ornek_sivi'])
    def test_gecerlilik_ici_bit_ayni(self, sivi_kati, ad):
        """Bayrak FALSE: kapı hiçbir şeye dokunmaz — yanıt, bayrağı silinmiş
        aynı hesapla bit-aynı (bayrak alanı dışında); onaylar yerinde."""
        tur = _DOCK_VAKA[ad]
        motor = _json_guvenli(sivi_kati[ad]['yeni'])
        ev = _dock_node(tur, motor)
        yuk = _dock_yuku(ev['fields'], ev['suggested'])
        yeni, eski = _uc_cagir(yuk), _uc_cagir(yuk, bayraksiz=True)
        sa = yeni['structural_analysis']['safety_analysis']
        assert sa.pop('model_validity_limit_exceeded') is False
        assert json.dumps(yeni, sort_keys=True) == json.dumps(
            eski, sort_keys=True)
        assert 'model_validity_approvals_withheld' not in sa
        assert not any(k.endswith('_withheld_because')
                       for k, _ in _duzle(yeni))
        assert _uc_hukum_yapraklari(yeni, _UC_ONAY_DEGERLERI), ad


# ---------------------------------------------------------------------------
# 7. tur (14 Eki; karar §28-44, 6. tur devir 1) — MOTORUN KENDİ YAPISAL
# ÇIKTISI DA GEÇERLİLİK DIŞINDA ONAY YAYIMLAMAZ.
#    Ölçülen kusur (dal 6afdb869, rapor 7. tur): örnek hibrit ``/calculate``
#    yanıtında ``motor.structural_analysis.safety_analysis.
#    model_validity_limit_exceeded = true`` iken ``design_target_assessment``
#    'SAFE · VERY LOW', ``buckling_analysis.axial_buckling_status`` 'SAFE'.
#    Kural artık hükmü üreten modülde (``withhold_model_validity_approvals``,
#    ``_analyze_safety_factors``in geçerlilik bloğu). Eski davranışın kâhini:
#    AYNI hesap, yalnız o işlev devre dışı (``_geri_cekme_kapali``).
# ---------------------------------------------------------------------------
#: Modülün geri çektiği hüküm alanları + 6. turun uç alanları (tek küme).
_T7_HUKUM_ALANLARI = _UC_HUKUM_ALANLARI + ('external_buckling_status',
                                           'buckling_status')
#: Doğrudan modül vakaları: (ad, malzeme, motor yükü).
_T7_DISI = {
    'celik_erime_ustu_dis_basinc': ('steel_4130', dict(
        _motor(2000.0, 1990.0), external_pressure=101325.0,
        internal_pressure_min=0.0)),
    'inconel_egri_ustu': ('inconel_718', _motor(1700.0, 1650.0)),
}
_T7_ICI = {
    'celik_ici_dis_basinc': ('steel_4130', dict(
        _motor(GECERLILIK_ICI_SICAK_K, GECERLILIK_ICI_SOGUK_K),
        external_pressure=101325.0, internal_pressure_min=0.0)),
    'inconel_ici': ('inconel_718', _motor(1100.0, 1050.0)),
}


class _geri_cekme_kapali:
    """Eski davranışın kâhini: modülün geri çekme işlevi devre dışı."""

    def __enter__(self):
        import hrma.analysis.structural_analysis as yapi_modulu
        self._m = yapi_modulu
        self._asil = yapi_modulu.withhold_model_validity_approvals
        yapi_modulu.withhold_model_validity_approvals = lambda bloklar: []
        return self

    def __exit__(self, *a):
        self._m.withhold_model_validity_approvals = self._asil
        return False


def _t7_yapraklar(o, degerler, yapisal=False):
    """Hüküm yaprakları; ``yapisal``: yalnız ``structural_analysis``
    altındakiler (motor yanıtının yanma kararlılığı vb. ``status`` alanları
    yapısal hüküm değildir)."""
    return sorted(k for k, v in _duzle(_json_guvenli(o))
                  if isinstance(v, str) and v.upper() in degerler
                  and k.split('.')[-1] in _T7_HUKUM_ALANLARI
                  and (not yapisal or 'structural_analysis' in k))


def _t7_modul(vaka, kapali=False):
    malzeme, motor = vaka
    if kapali:
        with _geri_cekme_kapali():
            return _size(dict(motor), material=malzeme)
    return _size(dict(motor), material=malzeme)


class TestModulGecerlilikOnayYok:

    @pytest.mark.parametrize('ad', sorted(_T7_DISI))
    def test_onay_yok_withheld_var(self, ad):
        from hrma.analysis.structural_analysis import (
            MODEL_VALIDITY_APPROVAL_FIELDS,
            STRUCTURAL_MODEL_VALIDITY_WITHHELD_REASON,
            STRUCTURAL_VERDICT_NOT_EVALUATED)
        yeni = _t7_modul(_T7_DISI[ad])
        eski = _t7_modul(_T7_DISI[ad], kapali=True)
        sa = yeni['safety_analysis']
        assert sa['model_validity_limit_exceeded'] is True
        eski_onay = _t7_yapraklar(eski, _UC_ONAY_DEGERLERI)
        assert eski_onay, ad   # ön koşul: eski davranış onay basıyordu
        assert _t7_yapraklar(yeni, _UC_ONAY_DEGERLERI) == [], ad
        # Geri çekilen yollar = eski davranışın onay yaprakları (risk ikizi
        # hariç), modülün kendi yüzey tablosundan.
        tablo = {y + '.' + h for y, h, _ in MODEL_VALIDITY_APPROVAL_FIELDS}
        beklenen = sorted(k for k in eski_onay if k in tablo)
        assert sorted(sa['model_validity_approvals_withheld']) == beklenen
        for yol in sa['model_validity_approvals_withheld']:
            blok_yolu, alan = yol.rsplit('.', 1)
            blok = yeni
            for p in blok_yolu.split('.'):
                blok = blok[p]
            assert blok[alan] == STRUCTURAL_VERDICT_NOT_EVALUATED
            assert blok[alan + '_withheld_because'] == (
                STRUCTURAL_MODEL_VALIDITY_WITHHELD_REASON)
        assert sa['design_target_assessment']['risk_level'] == (
            STRUCTURAL_VERDICT_NOT_EVALUATED)

    @pytest.mark.parametrize('ad', sorted(_T7_DISI))
    def test_yalniz_onaylar_degisir(self, ad):
        """Başarısız hükümler aynı (F4-2), sayılar bit-aynı, değişen yaprak
        yalnız geri çekilen onaylar + gerekçeleri + yol listesi."""
        yeni = dict(_duzle(_json_guvenli(_t7_modul(_T7_DISI[ad]))))
        eski = dict(_duzle(_json_guvenli(
            _t7_modul(_T7_DISI[ad], kapali=True))))
        bas = sorted(k for k, v in eski.items() if isinstance(v, str)
                     and v.upper() in _UC_BASARISIZ_DEGERLERI)
        assert bas, ad
        assert sorted(k for k, v in yeni.items() if isinstance(v, str)
                      and v.upper() in _UC_BASARISIZ_DEGERLERI) == bas
        geri = [v for k, v in yeni.items()
                if k.startswith('safety_analysis.'
                                'model_validity_approvals_withheld[')]
        beklenen = {'safety_analysis.design_target_assessment.risk_level'}
        for yol in geri:
            beklenen.update({yol, yol + '_withheld_because'})
        beklenen.update(k for k in yeni if k.startswith(
            'safety_analysis.model_validity_approvals_withheld['))
        degisen = {k for k in set(eski) | set(yeni)
                   if eski.get(k, '<yok>') != yeni.get(k, '<yok>')}
        assert degisen <= beklenen, sorted(degisen - beklenen)
        for k, x in yeni.items():
            if isinstance(x, (int, float)) and not isinstance(x, bool):
                assert eski[k] == x, k

    @pytest.mark.parametrize('ad', sorted(_T7_ICI))
    def test_gecerlilik_ici_bit_ayni(self, ad):
        yeni = _json_guvenli(_t7_modul(_T7_ICI[ad]))
        eski = _json_guvenli(_t7_modul(_T7_ICI[ad], kapali=True))
        assert yeni['safety_analysis']['model_validity_limit_exceeded'] is False
        assert json.dumps(yeni, sort_keys=True) == json.dumps(
            eski, sort_keys=True)
        assert 'model_validity_approvals_withheld' not in yeni[
            'safety_analysis']
        assert not any(k.endswith('_withheld_because')
                       for k, _ in _duzle(yeni))
        assert _t7_yapraklar(yeni, _UC_ONAY_DEGERLERI), ad

    def test_advanced_yapisal_kolu(self):
        """``/api/advanced-analysis`` yapısal kolu aynı modülü çağırır."""
        from hrma.app import app
        malzeme, motor = _T7_DISI['celik_erime_ustu_dis_basinc']
        govde = {'analysis_types': ['structural'], 'motor_data': motor,
                 'material_type': malzeme}
        r = app.test_client().post('/api/advanced-analysis', json=govde)
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        yap = r.get_json()['results']['structural_analysis']
        assert yap['safety_analysis']['model_validity_limit_exceeded'] is True
        assert _t7_yapraklar(yap, _UC_ONAY_DEGERLERI) == []
        assert yap['safety_analysis']['model_validity_approvals_withheld']


@pytest.fixture(scope='module')
def hibrit_motor_t7(ornek_hibrit):
    """Örnek hibrit ``/calculate`` (yeni) + aynı yük, geri çekme kapalı."""
    from hrma.app import app
    from tests.test_example_projects import HEADERS, NAMES, calculate_payload
    with open(REPO_ROOT / 'examples' / (NAMES['hybrid'] + '.hrma'),
              encoding='utf-8') as f:
        fields = json.load(f)['inputs']['fields']
    with _geri_cekme_kapali():
        r = app.test_client().post('/calculate',
                                   json=calculate_payload('hybrid', fields),
                                   headers=HEADERS)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return {'yeni': ornek_hibrit, 'eski': r.get_json()}


class TestHibritMotorCiktisi:

    def test_calculate_onay_yok_withheld_var(self, hibrit_motor_t7):
        from hrma.analysis.structural_analysis import (
            STRUCTURAL_VERDICT_NOT_EVALUATED)
        yeni, eski = hibrit_motor_t7['yeni'], hibrit_motor_t7['eski']
        ys = yeni['motor']['structural_analysis']
        assert ys['safety_analysis']['model_validity_limit_exceeded'] is True
        assert _t7_yapraklar(eski['motor']['structural_analysis'],
                             _UC_ONAY_DEGERLERI)   # ön koşul
        # Yanıtın HER yapısal kopyasında (motor + openrocket motor_data)
        # onay yok.
        assert _t7_yapraklar(yeni, _UC_ONAY_DEGERLERI, yapisal=True) == []
        dta = ys['safety_analysis']['design_target_assessment']
        assert dta['status'] == STRUCTURAL_VERDICT_NOT_EVALUATED
        assert dta['risk_level'] == STRUCTURAL_VERDICT_NOT_EVALUATED
        assert ys['buckling_analysis']['axial_buckling_status'] == (
            STRUCTURAL_VERDICT_NOT_EVALUATED)
        assert 'safety_analysis.design_target_assessment.status' in ys[
            'safety_analysis']['model_validity_approvals_withheld']
        # Başarısız hükümler aynı (F4-2: uyarı susturulmaz).
        assert _t7_yapraklar(yeni, _UC_BASARISIZ_DEGERLERI, True) == (
            _t7_yapraklar(eski, _UC_BASARISIZ_DEGERLERI, True))
        assert _t7_yapraklar(yeni, _UC_BASARISIZ_DEGERLERI, True)

    def test_pdf_raporu_onay_basmaz(self, hibrit_motor_t7):
        """PDF yapısal tablosu yalnız ana hükmü basar (ölçüldü: önce de
        SAFE/VERY LOW yoktu); gerileme kilidi."""
        import re
        import shutil
        import subprocess
        from hrma.app import app
        pdftotext = shutil.which('pdftotext')
        if pdftotext is None:
            pytest.skip('pdftotext yok: PDF metni okunamaz (gerekçeli atlama)')
        yeni = _json_guvenli(hibrit_motor_t7['yeni'])
        r = app.test_client().post(
            '/api/export-pdf/complete',
            json={'motor_data': yeni['motor'], 'analysis_results': yeni})
        assert r.status_code == 200 and r.data.startswith(b'%PDF')
        metin = subprocess.run([pdftotext, '-layout', '-', '-'],
                               input=r.data, capture_output=True,
                               timeout=120).stdout.decode('utf-8', 'replace')
        assert 'Structural Status' in metin
        assert not re.search(r'\bSAFE\b|VERY LOW', metin)
        assert re.search(r'Structural Status\s+UNSAFE', metin)


#: KAB devri (i) vakası (docs/kabul/kanit_2026-10-14 gd_sivi_radyatif).
_KAB_SIVI_RADYATIF_1800 = {'cooling_type': 'radiative', 'max_wall_temp': 1800.0}

#: KAB ölçümü (14 Eki) form yolunda KULLANICI cidarıyla alındı: liquid.html
#: o gün ``chamber_wall_thickness`` alanını 5 mm ön-dolguyla açıyordu. Sıvı
#: soğutma F-17 (ed013b81c, main 78fe2254f) kaynaksız ön-dolguyu kaldırdı;
#: alan artık boş ve motor cidarı KENDİ boyutluyor (design_mode 'size',
#: 2,0 mm) — örtük şablon varsayılanına bağlı çapa sessizce bayatladı.
#: Ölçüm koşulu burada AÇIKÇA sabitlenir (ÖH 14 Eki, ana model; beklentiler
#: değişmedi, yalnız girdi ölçümdeki hâline döndü).
_KAB_FORM_CIDARI_MM = 5.0


def _form_sivi(ek):
    """FORM yolu (form_yuku: şablonun sayı varsayılanları) örnek sıvı +
    ``ek`` alanlar (KAB ölçümünün yolu; kullanıcı cidarı açıkça 5 mm)."""
    from hrma.app import app
    from tests.support.form_defaults import form_yuku
    from tests.test_example_projects import HEADERS, NAMES
    with open(REPO_ROOT / 'examples' / (NAMES['liquid'] + '.hrma'),
              encoding='utf-8') as f:
        fields = json.load(f)['inputs']['fields']
    fields['chamber_wall_thickness'] = _KAB_FORM_CIDARI_MM
    fields.update(ek)
    r = app.test_client().post('/calculate_liquid',
                               json=form_yuku('liquid', fields),
                               headers=HEADERS)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()


@pytest.fixture(scope='module')
def kab_sivi_1800(tmp_path_factory):
    import os
    os.environ.setdefault('HRMA_PROJECTS_DIR',
                          str(tmp_path_factory.mktemp('hrma_projeler_t7')))
    motor = _form_sivi(_KAB_SIVI_RADYATIF_1800)
    yeni = _dock_akisi('liquid', motor)
    with _geri_cekme_kapali():
        eski = _dock_akisi('liquid', motor)
    return {'motor': motor, 'yeni': yeni, 'eski': eski}


class TestKabFormYoluSivi:

    def test_dock_paneli_onay_basmaz(self, kab_sivi_1800):
        import re
        yeni, eski = kab_sivi_1800['yeni'], kab_sivi_1800['eski']
        sa = yeni['uc']['structural_analysis']['safety_analysis']
        assert sa['model_validity_limit_exceeded'] is True
        # Ön koşul: KAB ölçümündeki onaylar eski davranışta ekranda.
        # V3 KK (YP7 devri, 14 Eki): dock yükü artık motorun KENDİ hedefini
        # (form 2,5) taşır; KAB ölçümünün 'ACCEPTABLE · LOW'u malzeme
        # varsayılanı 3,0 ile alınmıştı. dta satırı ucun KENDİ (geri çekme
        # kapalı) hükmünü basar; o hüküm başarısızsa §28-44 gereği yeni
        # davranışta da aynen basılır (susturulmaz).
        dta_eski = eski['uc']['structural_analysis']['safety_analysis'][
            'design_target_assessment']
        dta_satiri = 'status: {} · risk_level: {}'.format(
            dta_eski['status'], dta_eski['risk_level'])
        assert dta_satiri in eski['metin']
        if str(dta_eski['status']).upper() in _UC_BASARISIZ_DEGERLERI:
            assert dta_satiri in yeni['metin']
        assert 'Fatigue Status SAFE' in eski['metin']
        assert not re.search(r'\bSAFE\b|\bACCEPTABLE\b|VERY LOW|'
                             r'risk_level: LOW', yeni['metin']), (
            re.findall(r'.{60}(?:\bSAFE\b|ACCEPTABLE|LOW).{20}',
                       yeni['metin']))
        assert 'status: NOT_EVALUATED' in yeni['metin']
        assert re.search(_DOCK_BASARISIZ, yeni['metin'])
        assert _t7_yapraklar(yeni['uc'], _UC_ONAY_DEGERLERI) == []


class TestSiviKartiSfAdlari:
    """KAB devri (ii): motor kartının SF'leri ile dock panelinin kazanılmış
    SF'si AYNI büyüklük değil — ölçüldü, ekranda ADLARIYLA ayrılır."""

    def test_farkli_buyuklukler_kahin(self, kab_sivi_1800):
        # KAB ölçümünün yolu: FORM yolu örnek sıvı (kullanıcı cidarı 5 mm).
        motor = _form_sivi({})
        cs = motor['structural_analysis']['chamber_structure']
        uc = _dock_akisi('liquid', motor)['uc']['structural_analysis']
        ch = uc['chamber_analysis']
        dp = uc['design_parameters']
        # Kart: σ_y(T_sıcak) / σ_çember(P_c) — işletme basıncı, yalnız basınç.
        assert cs['hoop_safety_factor'] == pytest.approx(
            cs['yield_strength_at_wall_temp'] / cs['hoop_stress'], rel=1e-12)
        # Panel: tasarım basıncı (×1,5) ve basınç + ısıl çember gerilmesi.
        assert ch['pressure_hoop_stress'] == pytest.approx(
            cs['hoop_stress'] * dp['design_pressure_factor'], rel=1e-12)
        assert ch['safety_factor_total'] == pytest.approx(
            ch['yield_strength_used_MPa']
            / (ch['pressure_hoop_stress'] + ch['thermal_hoop_stress']),
            rel=1e-12)
        assert ch['thermal_hoop_stress'] > 0.0
        assert dp['design_pressure_factor'] != 1.0
        # Kartın 'Safety Factor' satırı tasarım hedefinin geri okunması.
        assert cs['safety_factor'] != cs['hoop_safety_factor']

    @pytest.mark.parametrize('dil', ['en', 'tr'])
    def test_kart_satirlari_adlariyla(self, sivi_kati, tmp_path, dil):
        import re
        cs = sivi_kati['ornek_sivi']['yeni']['structural_analysis'][
            'chamber_structure']
        kaynak = (REPO_ROOT / 'hrma' / 'static' / 'js' / 'i18n_pages.js'
                  ).read_text(encoding='utf-8')
        sz = {k: v for k, v in re.findall(
            r"'(liq\.msg\.(?:design_sf_target|hoop_sf_operating))':"
            r"\s*'([^']*)'", kaynak)[
                (0 if dil == 'en' else 2):(2 if dil == 'en' else 4)]}
        assert len(sz) == 2, sz
        #: Eski tek satırın adı (anahtarı sözlükten kalktı: tek tüketicisi
        #: bu satırdı; test_i18n_pages yetim anahtar kabul etmez).
        eski_ad = {'en': 'Safety Factor', 'tr': 'Emniyet Katsayısı'}[dil]
        kart = _sablon_render('liquid', sivi_kati['ornek_sivi']['yeni'],
                              dil, tmp_path)['kart']
        for anahtar, deger in (('liq.msg.design_sf_target',
                                'safety_factor'),
                               ('liq.msg.hoop_sf_operating',
                                'hoop_safety_factor')):
            m = re.search('<td>%s:</td><td>([^<]*)</td>'
                          % re.escape(sz[anahtar]), kart)
            assert m, (anahtar, kart[:300])
            assert float(m.group(1).replace(',', '.')) == pytest.approx(
                round(cs[deger], 2), abs=1e-9)
        assert '<td>%s:</td>' % eski_ad not in kart
        if dil == 'tr':
            assert any(h in sz['liq.msg.hoop_sf_operating']
                       for h in 'çğıöşüÇĞİÖŞÜ')
