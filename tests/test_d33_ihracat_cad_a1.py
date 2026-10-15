"""ÖH D33-2 / ihracat-cad a1 — bekçiler.

Kalemler:
  OH-D32-04  ``cad_visualization._injector_spec`` çözücünün orifis alanlarını
             okuyamıyordu; STL/çizim 0 delik derken STEP 12 delik deliyordu.
  OH-UC-09   ``liquid_results_to_motor_geometry({})`` üreteç varsayılanı
             üretiyordu (P15B4-06'nın katı/hibrit kardeşlerinde kapattığı
             sınıf).

Ölçüm kanıtı: ``docs/scofield/raw/OH/D33-2/ihracat-cad/a1/once.json`` ve
``sonra.json`` (aynı betik, iki ağaç).
"""
import math

import pytest

from hrma.export.cad_visualization import (
    MotorCADDesigner, _injector_block, _injector_spec,
    _injector_circuit_summary, _mesh_orifice_plan, MESH_MAX_INJECTOR_ORIFICES)
from hrma.export.motor_geometry import liquid_results_to_motor_geometry
from hrma.export.step_export import (
    INJECTOR_BLOCK_ORDER, injector_circuits_from_block, resolve_injector_plan)


# --------------------------------------------------------------------------
# Gövdeler — çözücünün GERÇEKTE yayımladığı alan adlarıyla (once.json A0)
# --------------------------------------------------------------------------
def _sivi_govde():
    """10 kN LOX/RP-1 koşumunun enjektör alanları (once.json bölüm A0)."""
    return {
        'chamber_diameter': 0.061535,
        'chamber_length': 0.284457,
        'throat_diameter': 0.030767,
        'exit_diameter': 0.217559,
        'chamber_pressure': 100.0,
        'injector_design': {
            'injector_type': 'impinging',
            'number_of_elements': 6.0,
            'oxidizer_orifice_diameter_mm': 2.492039220545476,
            'fuel_orifice_diameter_mm': 2.3216897511776033,
            'injection_pressure_drop_fuel_bar': 22.0,
            'injection_pressure_drop_bar': 22.0,
        },
        'injector_results': {
            'plate_structural': {'plate_thickness_mm': 6.0,
                                 'plate_diameter_mm': 80.0,
                                 'plate_mass_kg': 1.2, 'material': 'SS316'},
        },
    }


def _hibrit_govde():
    """Tek devreli (oksitleyici) hibrit — gerileme tabanı."""
    return {
        'chamber_diameter': 0.15,
        'injector_design': {'injector_type': 'showerhead',
                            'number_of_orifices': 7,
                            'orifice_diameter_mm': 2.3895029878023664,
                            'injection_pressure_drop_bar': 12.0},
        'injector_design_detail': {
            'ox_circuit': {'n_orifices': 7,
                           'orifice_d_mm': 2.3895029878023664,
                           'delta_p_bar': 12.0}},
        'injector_results': {
            'plate_structural': {'plate_thickness_mm': 8.0,
                                 'plate_diameter_mm': 120.0,
                                 'material': 'SS316'}},
    }


# --------------------------------------------------------------------------
# OH-D32-04
# --------------------------------------------------------------------------
def test_injector_spec_sivi_devrelerini_cozer():
    """ÖLÇÜLDÜ (once.json A1): ``n_orifices=None`` / ``source='not
    available'`` — aynı gövdede STEP 12 delik deliyordu. Alan adları artık
    STEP ile ortak."""
    spec = _injector_spec(_sivi_govde())
    assert spec['n_orifices'] == 12, spec
    adlar = {c['name']: c for c in spec['circuits']}
    assert set(adlar) == {'oxidizer', 'fuel'}
    assert adlar['oxidizer']['n'] == 6
    assert adlar['fuel']['n'] == 6
    assert adlar['oxidizer']['d_mm'] == pytest.approx(2.492039220545476)
    assert adlar['fuel']['d_mm'] == pytest.approx(2.3216897511776033)
    # Çözücünün ADINI verdiği alanlar künyede durur (uydurma değil).
    assert adlar['oxidizer']['diameter_field'].endswith(
        'oxidizer_orifice_diameter_mm')
    assert adlar['fuel']['diameter_field'].endswith('fuel_orifice_diameter_mm')


def test_iki_uretici_ayni_delik_planini_verir():
    """STL/çizim ile STEP aynı gövdede AYNI planı okumalı (kalemin çekirdeği)."""
    for govde, tip in ((_sivi_govde(), 'liquid'), (_hibrit_govde(), 'hybrid')):
        spec = _injector_spec(govde)
        plan = resolve_injector_plan(govde, motor_type=tip)
        assert spec['n_orifices'] == sum(c['n'] for c in plan['circuits'])
        assert [(c['name'], c['n'], c['d_mm']) for c in spec['circuits']] == \
               [(c['name'], c['n'], c['d_mm']) for c in plan['circuits']]


def test_kaynak_onceligi_tek_yerde_tanimli():
    """ÖLÇÜLDÜ (once.json A4): iki blok da varken STL paneli (125 x Ø0,957 mm),
    STEP ``injector_design``i (12 delik) okuyordu — aynı ZIP'te iki makine."""
    govde = _sivi_govde()
    govde['injector_results'].update({'number_of_orifices': 125,
                                      'orifice_diameter_mm': 0.957,
                                      'injector_type': 'pintle'})
    spec = _injector_spec(govde)
    plan = resolve_injector_plan(govde, motor_type='liquid')
    # Sıra artık TEK yerde; doktrin (v2.6.26 K2) paneli BİRİNCİL sayar ve
    # iki üretici de aynı bloğu seçer.
    assert spec['n_orifices'] == sum(c['n'] for c in plan['circuits']) == 125
    assert INJECTOR_BLOCK_ORDER[0] == 'injector_results'
    assert _injector_block(govde)[1] == 'injector_results'
    # K2 melez yasağı: kazanan blok panel ise ΔP de panelden okunur.
    govde['injector_results']['pressure_drop_bar'] = 4.0
    assert _injector_spec(govde)['pressure_drop_bar'] == 4.0


def test_bos_panel_sirayi_kilitlemez():
    """ÖLÇÜLDÜ (once.json A2): panel yalnız plaka kalınlığı taşıyorken bile
    blok olarak seçiliyor, delik planı ``injector_design``de duruyordu →
    STL 0 delik, STEP 12 delik. Devre yayımlamayan blok sırayı KİLİTLEMEZ."""
    govde = _sivi_govde()          # paneli yalnız plate_structural taşır
    spec = _injector_spec(govde)
    assert spec['n_orifices'] == 12
    assert spec['source'] == 'motor result injector_design'
    assert _injector_block(govde)[1] == 'injector_design'


def test_tek_cap_yalniz_devreler_ortakken_yayimlanir():
    """Fail-closed: iki devre farklı çaptaysa TEK çap alanı doldurulmaz
    (ortalamak ya da birini seçmek çap uydurmak olurdu)."""
    assert _injector_spec(_sivi_govde())['orifice_diameter_mm'] is None
    tek = _injector_spec(_hibrit_govde())
    assert tek['orifice_diameter_mm'] == pytest.approx(2.3895029878023664)


def test_imalat_notu_ve_cizim_devre_basina_yazar():
    """ÖLÇÜLDÜ (once.json A5): aynı koşuda imalat notu 'orifice count and
    diameter NOT AVAILABLE' diyordu — STEP 12 deliği delmişken."""
    d = MotorCADDesigner.__new__(MotorCADDesigner)
    notlar = d._generate_manufacturing_notes(_sivi_govde())
    inj_not = [n for n in notlar if str(n).startswith('3. Injector:')]
    assert inj_not, notlar
    assert 'NOT AVAILABLE' not in inj_not[0]
    assert '2.4920 mm (oxidizer)' in inj_not[0]
    assert '2.3217 mm (fuel)' in inj_not[0]

    ciz = d._generate_technical_drawings(_sivi_govde())['injector']
    assert ciz['orifice_count'] == 12
    assert [(c['circuit'], c['count']) for c in ciz['orifice_circuits']] == \
           [('oxidizer', 6), ('fuel', 6)]
    assert ciz['injector_type'] == 'impinging'


def test_plaka_gercekten_12_delik_tasir():
    """Topolojik ölçüm: kapalı yüzeyde cins = (2 - euler) / 2; N delikli
    plakanın cinsi N'dir. ÖLÇÜLDÜ (once.json A7): cins 0 (128 üçgen)."""
    md = _sivi_govde()
    md['injector_mesh_circuits'] = _mesh_orifice_plan(
        _injector_spec(md)['circuits'])
    mesh = MotorCADDesigner.__new__(MotorCADDesigner)._create_injector_head(
        md['chamber_diameter'], md)
    assert bool(mesh.is_volume)
    assert (2 - int(mesh.euler_number)) // 2 == 12


def test_hibrit_tek_devresi_gerilemez():
    """Tek devreli motorun katısı 7 deliğini KORUR (ilk halka 0,7·R'de)."""
    md = _hibrit_govde()
    md['injector_mesh_circuits'] = _mesh_orifice_plan(
        _injector_spec(md)['circuits'])
    mesh = MotorCADDesigner.__new__(MotorCADDesigner)._create_injector_head(
        md['chamber_diameter'], md)
    assert bool(mesh.is_volume)
    assert (2 - int(mesh.euler_number)) // 2 == 7


def test_mesh_kirpmasi_devreleri_dusurmez():
    """Kırpma sınırı aşılsa bile HER devre temsil edilir ve toplam sınırı
    aşmaz — tek devreyi düşürmek plakayı yanlış anlatırdı."""
    devreler = [{'name': 'oxidizer', 'n': 200, 'd_mm': 1.0},
                {'name': 'fuel', 'n': 40, 'd_mm': 0.8}]
    plan = _mesh_orifice_plan(devreler)
    assert {p['name'] for p in plan} == {'oxidizer', 'fuel'}
    assert all(p['n'] >= 1 for p in plan)
    assert sum(p['n'] for p in plan) == MESH_MAX_INJECTOR_ORIFICES
    assert _mesh_orifice_plan([]) == []


def test_enjektor_yoksa_delik_uydurulmaz():
    """Fail-closed: hiçbir blok orifis yayımlamıyorsa sayı ÜRETİLMEZ."""
    spec = _injector_spec({'chamber_diameter': 0.1})
    assert spec['n_orifices'] is None
    assert spec['circuits'] == []
    assert spec['source'] == 'not available'


def test_alan_semasi_ikinci_kez_yazilmaz():
    """TEK KAYNAK: devre çözümü ``step_export``tedir; CAD katmanı onu
    çağırır, kendi alan listesini tutmaz."""
    import inspect

    import hrma.export.cad_visualization as cv

    kaynak = inspect.getsource(cv._injector_spec)
    # Çözüm ortak seçiciden geçer (blok seçimi + devre şeması tek yerde).
    assert 'resolve_injector_circuits(' in kaynak
    gövde = kaynak.split('\"\"\"')[-1]      # docstring'i dışarıda bırak
    for ad in ('oxidizer_orifice_diameter_mm', 'fuel_orifice_diameter_mm',
               'number_of_elements', 'n_holes', 'hole_diameter',
               'ox_orifice_count', 'fuel_orifice_count'):
        assert f"'{ad}'" not in gövde, (
            f'{ad} alan adı CAD katmanında İKİNCİ KEZ yazılmış')
    # Blok SIRASI da ikinci kez yazılmaz: seçim ortak seçicidedir, CAD
    # katmanında blok adları yalnız KÜNYE/kapsam kararı için geçer, bir
    # öncelik listesi kurmaz.
    secici = inspect.getsource(cv._injector_block)
    assert 'resolve_injector_circuits(' in secici
    assert 'for ' not in secici, (
        'CAD katmanı blokları kendi sırasıyla geziyor')
    # Çekirdek gerçekten ortak: iki çağrı da aynı fonksiyondan geçer.
    devreler, _eksik = injector_circuits_from_block(
        _sivi_govde(), _sivi_govde()['injector_design'], {},
        motor_type='liquid')
    assert sum(c['n'] for c in devreler) == 12
    # ... ve seçici, STEP üreticisinin kullandığının TA KENDİSİDİR.
    import hrma.export.step_export as se
    assert (inspect.getsource(se.resolve_injector_plan)
            .count('resolve_injector_circuits(') == 1)


def test_devre_ozeti_metni():
    assert _injector_circuit_summary([]) is None
    assert _injector_circuit_summary(
        [{'name': 'oxidizer', 'n': 6, 'd_mm': 2.492039}]) == \
        '6 x 2.4920 mm (oxidizer)'


# --------------------------------------------------------------------------
# OH-UC-09
# --------------------------------------------------------------------------
_UYDURULAN = {
    # ÖLÇÜLDÜ (once.json B1): boş sözlükten dönen üreteç varsayılanları.
    'chamber_diameter': 0.15, 'chamber_length': 0.3, 'throat_diameter': 0.03,
    'exit_diameter': 0.09, 'expansion_ratio': 9.0, 'chamber_pressure': 50.0,
    'burn_time': 0.0, 'thrust': 0.0, 'isp': 0.0, 'of_ratio': 0.0,
}


def test_sivi_donusturucu_bos_sozlukten_sayi_uretmez():
    """ÖLÇÜLDÜ (once.json B1): 14 anahtar / 10 sayı ve künye YOK. Katı
    kardeş aynı çağrıda 5 anahtar / 0 sayı / 14 künye veriyordu."""
    out = liquid_results_to_motor_geometry({})
    sayilar = {k: v for k, v in out.items()
               if isinstance(v, (int, float)) and not isinstance(v, bool)}
    assert sayilar == {}, sayilar
    for ad in _UYDURULAN:
        assert ad not in out, f'{ad} hâlâ uydurma varsayılanla yazılıyor'
    kunye = out.get('geometry_unresolved') or {}
    assert set(kunye) == set(_UYDURULAN)
    # Künye NEREYE bakıldığını söyler (katı koldaki sözleşmenin aynısı).
    assert all('looked at' in v for v in kunye.values())


def test_sivi_donusturucu_sessiz_sifir_yayimlamaz():
    """``burn_time/thrust/isp/of_ratio`` yedeği 0,0 idi: 'hesaplanmadı'
    hâli SIFIR diye yayımlanıyordu."""
    out = liquid_results_to_motor_geometry({})
    for ad in ('burn_time', 'thrust', 'isp', 'of_ratio'):
        assert out.get(ad) is None
    assert out['injector_design']['injection_pressure_drop_bar'] is None


def test_sivi_donusturucu_kismi_sozlukte_yalniz_cozuleni_yazar():
    """ÖLÇÜLDÜ (once.json B4): yalnız ``chamber_diameter`` verilen sözlükten
    14 anahtar / 10 sayı dönüyordu; gerisi uydurmaydı."""
    out = liquid_results_to_motor_geometry({'chamber_diameter': 61.53})
    assert out['chamber_diameter'] == pytest.approx(0.06153)
    assert 'chamber_length' not in out
    assert 'throat_diameter' not in out
    assert set(out['geometry_unresolved']) == set(_UYDURULAN) - {
        'chamber_diameter'}


def test_sivi_donusturucu_gercek_sayilari_bozmaz():
    """Gerileme bekçisi: çözücü yayımladıysa değer AYNEN taşınır ve künye
    hiç yazılmaz (once.json B3 ile sonra.json B3 bit-aynı)."""
    ham = {'chamber_diameter': 61.535, 'chamber_length': 284.457,
           'throat_diameter': 0.030767, 'exit_diameter': 0.217559,
           'expansion_ratio': 50.0, 'chamber_pressure': 100.0,
           'burn_time': 400.0, 'thrust': 10000.0, 'isp_sea_level': 245.562493,
           'mixture_ratio': 2.5}
    out = liquid_results_to_motor_geometry(ham)
    assert 'geometry_unresolved' not in out
    assert out['chamber_diameter'] == pytest.approx(0.061535)
    assert out['chamber_length'] == pytest.approx(0.284457)
    assert out['throat_diameter'] == pytest.approx(0.030767)
    assert out['exit_diameter'] == pytest.approx(0.217559)
    assert out['expansion_ratio'] == 50.0
    assert out['chamber_pressure'] == 100.0
    assert out['burn_time'] == 400.0
    assert out['thrust'] == 10000.0
    assert out['isp'] == pytest.approx(245.562493)
    assert out['of_ratio'] == 2.5


def test_uc_donusturucu_ayni_fail_closed_sozlesmesini_paylasir():
    """Üç motorun üçü de boş sözlükte sayı üretmez ve künye yayımlar."""
    from hrma.export.motor_geometry import (
        hybrid_results_to_motor_geometry, solid_results_to_motor_geometry)

    for fn in (liquid_results_to_motor_geometry,
               solid_results_to_motor_geometry,
               hybrid_results_to_motor_geometry):
        out = fn({})
        sayilar = [k for k, v in out.items()
                   if isinstance(v, (int, float)) and not isinstance(v, bool)]
        assert sayilar == [], (fn.__name__, sayilar)
        assert out.get('geometry_unresolved'), fn.__name__
        assert not any(math.isfinite(v) for v in out.values()
                       if isinstance(v, float))
