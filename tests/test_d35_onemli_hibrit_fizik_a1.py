"""ÖH D35 · onemli-hibrit-fizik · a1 — DAVRANIŞ BEKÇİLERİ.

Kapsanan kalemler
-----------------
OH-ON-01  Aynı yanıtta iki enjektör çözümü vardı ve birbirini tutmuyordu.
          Ölçüldü (``docs/scofield/raw/OH/D35/onemli-hibrit-fizik/a1/
          once.json``, koşul ``H1``; Ornek-H1: 1000 N, Pc 20 bar, tank
          50 bar, O/F 7,5, N2O/HTPB, duş başlığı):

            motor.injector_design :  3 × Ø2,1115 mm · ΔP 30,5434 bar
            injector              : 32 × Ø0,9055 mm · ΔP  4,0000 bar

          Plaka mukavemet denetimi ikinci plana koşuyor ve "SF 4,107"
          diyordu; aynı yanıtın kendi ΔP'siyle eğilme gerilmesi 436,578 MPa
          (ss_316 akma 240 MPa) ve SF 0,550. Chug ΔP/Pc kapısı da 4 bar'ı
          derecelendirip 0,20 (bandın içi) görüyordu; çözülen ΔP ile oran
          1,5272, yani 0,35 tavanının 4,4 katı.

          4 bar kullanıcının SEÇTİĞİ bir sayı değildi: ``advanced.html:4444``
          gizli ``designConfigPanel`` içindeki ``pressure_drop_percent``
          (value="20") alanını her koşuda ``0,20·Pc`` olarak gönderiyor.

OH-ON-02  Ürünün kendi TAM ADAPTE lülesi kendi kabul bandının dışında
          sayılıyordu: Pc 20 bar deniz seviyesinde ε = 3,9041 iken sabit
          (4, 250) bandı uyarı basıyordu; buna karşılık ε = 50 (ağır aşırı
          genleşme, ayrılma öngörülü) aynı banttan SESSİZCE geçiyordu.

Bu dosyadaki her iddia ters-mutasyonla kanıtlanmıştır:
``docs/scofield/raw/OH/D35/onemli-hibrit-fizik/a1/mutasyon.py``.
"""
import ast
import math
import os

import pytest

from hrma.app import app
from hrma.validation.validation_system import validator
from hrma.utils.injector_design import DP_SOURCE_SOLVER, DP_SOURCE_USER

os.environ.setdefault('HRMA_HEADLESS', '1')

#: Cowork görsel turunun (21 Eylül 2026) Ornek-H1 motoru + gizli panelin
#: her koşuda gönderdiği alanlar.
ORNEK_H1 = {
    'thrust': 1000.0, 'burn_time': 10.0, 'chamber_pressure': 20.0,
    'of_ratio': 7.5, 'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
    'tank_pressure': 50.0, 'injector_type': 'showerhead',
    'injector_material': 'stainless_steel', 'chamber_material': 'steel_304',
    'wall_thickness': 5.0, 'safety_factor': 4.0,
    'pressure_drop': 4.0,          # advanced.html:4444 — gizli panel
}


def _kosu(**degisiklik):
    yuk = dict(ORNEK_H1)
    yuk.update(degisiklik)
    app.config['TESTING'] = True
    with app.test_client() as ist:
        cevap = ist.post('/calculate', json=yuk)
    assert cevap.status_code == 200, (cevap.status_code, yuk)
    return cevap.get_json()


@pytest.fixture(scope='module')
def h1():
    return _kosu()


def _kodlar(govde):
    dog = govde.get('validation') or {}
    return [u.get('code') for u in
            (dog.get('critical_warnings') or []) +
            (dog.get('regular_warnings') or [])]


# ===========================================================================
# OH-ON-01 — TEK ENJEKTÖR ÇÖZÜMÜ
# ===========================================================================
def test_ON01_iki_enjektor_blogu_AYNI_plani_anlatiyor(h1):
    """``injector`` ⟷ ``motor.injector_design``: delik sayısı, delik çapı, ΔP."""
    inj = h1['injector']
    devre = h1['motor']['injector_design']
    assert devre.get('status') != 'not_analyzed', devre
    assert int(inj['n_holes']) == int(devre['number_of_orifices']), (
        'aynı yanıtta iki farklı delik SAYISI var: '
        f"injector={inj['n_holes']} devre={devre['number_of_orifices']}")
    assert inj['hole_diameter'] == pytest.approx(
        devre['orifice_diameter_mm'], rel=1e-9), (
        'aynı yanıtta iki farklı delik ÇAPI var: '
        f"injector={inj['hole_diameter']} devre={devre['orifice_diameter_mm']}")
    assert inj['pressure_drop'] == pytest.approx(
        devre['injection_pressure_drop_bar'], rel=1e-9), (
        'aynı yanıtta iki farklı ΔP var: '
        f"injector={inj['pressure_drop']} "
        f"devre={devre['injection_pressure_drop_bar']}")
    assert inj.get('orifice_plan_is_canon') is True, (
        'delik planı devre çözücüsünden TÜKETİLMİYOR (yeniden türetiliyor)')


def test_ON01_gizli_panelin_4_bari_SESSIZCE_kazanmiyor(h1):
    """Beyansız ``pressure_drop`` ΔP'yi ezemez (fail-closed)."""
    inj = h1['injector']
    assert inj['pressure_drop_source'] == DP_SOURCE_SOLVER, (
        'gizli panelin gönderdiği ΔP hâlâ "kullanıcı ezmesi" diye '
        f"künyeleniyor: {inj['pressure_drop_source']}")
    assert inj['pressure_drop'] > ORNEK_H1['pressure_drop'], (
        'yayımlanan ΔP hâlâ istekteki 4 bar')


def test_ON01_ACIK_beyanli_ezme_UYGULANIR_ve_ayrisma_yayimlanir():
    """Kullanıcı ``pressure_drop_source="user"`` derse ezme geçer.

    O durumda iki plan meşru biçimde ayrışır; ayrışma SESSİZ kalmaz.
    """
    govde = _kosu(pressure_drop_source='user')
    inj = govde['injector']
    assert inj['pressure_drop'] == pytest.approx(4.0, rel=1e-9)
    assert inj['pressure_drop_source'] == DP_SOURCE_USER
    sapma = govde['injector']['plate_structural'].get('hole_plan_disagreement')
    assert sapma and 'pressure_drop_bar' in sapma['fields'], (
        'iki plan ayrışıyor ama yanıt bunu ADIYLA söylemiyor: ' + str(sapma))


def test_ON01_plaka_denetimi_DENETLEDIGI_plakayi_ADIYLA_yayimliyor(h1):
    plaka = h1['injector']['plate_structural']
    inj = h1['injector']
    assert plaka['status'] == 'analyzed', plaka
    assert plaka['delta_P_bar'] == pytest.approx(inj['pressure_drop'],
                                                 rel=1e-9), (
        'plaka, enjektörün çözdüğünden BAŞKA bir ΔP ile denetleniyor')
    assert int(plaka['n_holes']) == int(inj['n_holes'])
    # Rapor delik çapını 4 ondalığa yuvarlayarak yayımlar (sözleşme);
    # kıyas o yuvarlamanın mertebesinde yapılır.
    assert plaka['hole_diameter_mm'] == pytest.approx(inj['hole_diameter'],
                                                      abs=5e-5)
    assert plaka.get('hole_plan_agrees_with_circuit') is True, (
        'denetlenen plaka devre çözümüyle uyuşmuyor: '
        + str(plaka.get('hole_plan_disagreement')))


def test_ON01_plaka_SF_yayimlanan_dP_ile_CAPRAZ_tutuyor(h1):
    """Roark Tablo 11.2 durum 10b: σ = 0,75·q·a²/(t²·η), SF = σ_akma/σ.

    Sayı testin içinde SABİTLENMEZ; yanıtın KENDİ yapraklarından yeniden
    kurulur. ΔP yanlış plakadan gelirse bu özdeşlik kırılır.
    """
    plaka = h1['injector']['plate_structural']
    q = plaka['delta_P_bar'] * 1e5                        # Pa
    a = (plaka['plate_diameter_mm'] / 1000.0) / 2.0       # m
    t = plaka['plate_thickness_mm'] / 1000.0              # m
    eta = plaka['ligament_efficiency']
    sigma = 0.75 * q * a ** 2 / (t ** 2 * eta)            # Pa
    assert plaka['bending_stress_MPa'] == pytest.approx(sigma / 1e6, rel=2e-3)
    sf = (plaka['yield_strength_MPa'] * 1e6) / sigma
    assert plaka['safety_factor'] == pytest.approx(sf, rel=2e-3)
    # Ölçülen kusurun kapanışı: aynı plaka 4 bar'a göre SF 4,107 görüyordu.
    assert plaka['safety_factor'] < 1.0, (
        'Ornek-H1 plakası çözülen ΔP ile akmanın altında kalmalı; '
        f"SF = {plaka['safety_factor']} — 4 bar'lık hüküm geri gelmiş olabilir")


def test_ON01_chug_kapisi_COZULEN_dP_yi_derecelendiriyor(h1):
    kunye = h1['validation']['injector_assessment']['pressure_drop_ratio']
    inj = h1['injector']
    assert kunye['status'] == 'evaluated', kunye
    assert kunye['pressure_drop_bar'] == pytest.approx(inj['pressure_drop'],
                                                       rel=1e-9), (
        'chug kapısı enjektörün çözdüğünden başka bir ΔP görüyor')
    assert kunye['ratio'] == pytest.approx(
        inj['pressure_drop'] / ORNEK_H1['chamber_pressure'], rel=1e-3)
    assert kunye['ratio'] > kunye['band'][1], (
        'ΔP/Pc bandın üstünde olmalıydı (ölçüldü: 1,5272 ⟷ tavan 0,35)')
    assert 'warn.validation.dp_pc_high' in _kodlar(h1), (
        'bandın 4 katı dışındaki bir enjektör hâlâ sessizce geçiyor')


# ===========================================================================
# OH-ON-02 — GENLEŞME ORANI HÜKMÜ FİZİKTEN GELİR
# ===========================================================================
def test_ON02_tam_adapte_lule_ARTIK_uyari_almiyor(h1):
    assert 'warn.validation.expansion_ratio_out_of_range' not in _kodlar(h1), (
        'sabit (4, 250) bandı geri gelmiş: tam adapte ε = 3,90 suçlanıyor')
    eksen = h1['validation']['injector_assessment']['expansion_ratio']
    assert eksen['status'] == 'evaluated'
    assert eksen['verdict'] == 'attached_flow'
    assert eksen['separation_predicted'] is False
    # Hüküm koşumun KENDİ ortam basıncına dayanır, sabit sayıya değil.
    assert eksen['ambient_pressure_bar'] > 0
    assert eksen['separation_limit_expansion_ratio'] > eksen['expansion_ratio']


def test_ON02_dusuk_Pc_deniz_seviyesi_de_temiz():
    """Pc = 5 bar: ε ≈ 1,53 — eski bantta uyarı, fizikte tam adapte."""
    govde = _kosu(chamber_pressure=5.0, tank_pressure=40.0, pressure_drop=1.0)
    assert 'warn.validation.expansion_ratio_out_of_range' not in _kodlar(govde)
    eksen = govde['validation']['injector_assessment']['expansion_ratio']
    assert eksen['verdict'] == 'attached_flow', eksen
    assert eksen['expansion_ratio'] < 4.0, (
        'ölçüm çapası kaydı: bu koşum eski bandın ALTINDA olmalıydı')


def test_ON02_asiri_genlesme_UYARI_aliyor():
    """ε = 50, deniz seviyesi: Summerfield ayrılma öngörüyor."""
    govde = _kosu(expansion_ratio=50.0)
    eksen = govde['validation']['injector_assessment']['expansion_ratio']
    assert eksen['verdict'] == 'over_expanded_separated', eksen
    assert eksen['separation_predicted'] is True
    # Uyarı TEK kaynaktan basılır (motorun kendi ayrılma zinciri).
    kodlar = {u.get('code') for u in (govde['motor'].get('design_warnings') or [])
              if isinstance(u, dict)}
    assert 'warn.hybrid.nozzle_flow_separation' in kodlar, (
        'ayrılma öngörülen lüle hiçbir uyarı almıyor: ' + str(sorted(kodlar)))
    assert eksen.get('warning_issued_by') == 'warn.hybrid.nozzle_flow_separation'


def test_ON02_ekran_yoksa_HUKUM_GERI_CEKILIR():
    """Fail-closed: ortam basıncını bilen ekran yoksa sabit banda düşülmez."""
    rapor = validator.comprehensive_validation(
        {'chamber_pressure': 20.0, 'expansion_ratio': 3.9},
        {'pressure_drop': 4.0}, 'n2o_htpb')
    eksen = rapor['injector_assessment']['expansion_ratio']
    assert eksen['status'] == 'not_evaluated', eksen
    assert 'nozzle_expansion_screen' in eksen['missing_inputs']
    kodlar = [u['code'] for u in
              rapor['critical_warnings'] + rapor['regular_warnings']]
    assert 'warn.validation.expansion_ratio_not_evaluated' in kodlar
    assert 'warn.validation.expansion_ratio_out_of_range' not in kodlar
    assert rapor['assessment_complete'] is False
    assert rapor['validation_passed'] is False


def test_ON02_ses_ustu_tabani_geometriktir():
    """ε ≤ 1 yakınsak-ıraksak lüle değildir — KRİTİK."""
    rapor = validator.comprehensive_validation(
        {'chamber_pressure': 20.0, 'expansion_ratio': 0.9,
         'nozzle_expansion_screen': {'separation_predicted': False}},
        {'pressure_drop': 4.0}, 'n2o_htpb')
    kodlar = [u['code'] for u in rapor['critical_warnings']]
    assert 'warn.validation.expansion_ratio_not_supersonic' in kodlar
    assert rapor['injector_assessment'][
        'expansion_ratio']['verdict'] == 'not_supersonic'


# ===========================================================================
# YAPISAL — sabit genleşme bandı geri sızmasın
# ===========================================================================
def test_YAPISAL_sabit_genlesme_bandi_geri_gelmedi():
    """``(4, 250)`` ikilisi ``validation_system`` kodunda YAŞAMAMALI.

    Kaynak dosyadan AST ile okunur (``inspect.getsource`` içe aktarma
    sırasına duyarlıdır — taban kaydı dersi).
    """
    import hrma.validation.validation_system as vs
    agac = ast.parse(open(vs.__file__, encoding='utf-8').read())
    suclu = []
    for dugum in ast.walk(agac):
        if not isinstance(dugum, ast.Tuple) or len(dugum.elts) != 2:
            continue
        try:
            ikili = tuple(ast.literal_eval(e) for e in dugum.elts)
        except (ValueError, TypeError, SyntaxError):
            continue
        if ikili == (4, 250):
            suclu.append(dugum.lineno)
    assert not suclu, (
        'sabit genleşme oranı bandı (4, 250) koda geri gelmiş, satır: '
        + str(suclu))


def test_YAPISAL_capa_performans_zinciri_bu_kulvarda_DEGISMEDI(h1):
    """Enjektör onarımı itki/Isp/boğaz zincirine dokunmamalı."""
    m = h1['motor']
    assert m['thrust'] == pytest.approx(1000.0, rel=1e-6)
    assert math.isfinite(m['isp']) and m['isp'] > 0
    assert math.isfinite(m['throat_diameter']) and m['throat_diameter'] > 0
