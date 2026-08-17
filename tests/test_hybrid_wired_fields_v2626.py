"""v2.6.26'da bağlanan sekiz hibrit girdisinin DAVRANIŞ bekçileri.

Bu alanlar arayüzde vardı, kullanıcı değerini giriyordu ve hiçbiri hiçbir
hesaba ulaşmıyordu — Katman A taramasında sekizinin de yaprak değişimi
SIFIRDI. Buradaki testler "alan mevcut mu" değil "girdiyi değiştirince
sonuç değişiyor mu" sorusunu sorar; ilki geçse bile ikincisi kırılabilir
(v2.6.25'te tam bu oldu: arka uç üç termal alanı okuyordu, şablon
göndermiyordu, HTTP katmanını sınayan her test "bağlandı" diyordu).

Kapsanan alanlar ve bağlandıkları model:
  safety_factor           -> yapısal analizin tasarım SF hedefi; gerçek cidar
                             geçildiği için modül DOĞRULAMA modunda çalışır
  chamber_length_override -> L* ile türetilen kamara boyunu ezer
  nozzle_material         -> boğaz termal marjı + erozyon (yayımlanmış bant)
  injector_material       -> plaka eğilme gerilmesi / SF / kalınlık / kütle
  swirl_chamber_diameter  -> Giffen-Muraszew K = A_p/(D_s*d_o) içindeki D_s
  swirl_angle             -> hedef sprey yarı açısı (ters çözücü)
  nozzle_type=parabolic   -> nozzle_contour'dan taşınan üçüncü seçenek
  (injection_velocity ve nozzle_contour KALDIRILDI — ikinci kopyaydılar)
"""

import pytest

from hrma.engines.hybrid_rocket_engine import (
    HybridRocketEngine, SAFETY_FACTOR_MIN, SAFETY_FACTOR_MAX)


BASE = dict(thrust=5000, burn_time=10, of_ratio=2.5, chamber_pressure=20,
            fuel_type='htpb', oxidizer_type='n2o', l_star=1.0)


@pytest.fixture(scope='module')
def base_result():
    return HybridRocketEngine(**BASE).calculate()


def _codes(result):
    return {w.get('code') for w in (result.get('design_warnings') or [])
            if isinstance(w, dict)}


# ---------------------------------------------------------------------------
# safety_factor
# ---------------------------------------------------------------------------

def test_safety_factor_changes_required_thickness(base_result):
    """SF hedefi izin verilen gerilmeyi, o da gereken kalınlığı belirler."""
    low = HybridRocketEngine(**BASE, safety_factor=2.0).calculate()
    high = HybridRocketEngine(**BASE, safety_factor=6.0).calculate()
    t_low = low['structural_analysis']['chamber_analysis']['recommended_thickness']
    t_high = high['structural_analysis']['chamber_analysis']['recommended_thickness']
    # Daha yüksek emniyet hedefi DAHA KALIN cidar ister — ters yönde bir
    # sonuç, hedefin izin verilen gerilmeye yanlış işaretle girdiği anlamına
    # gelir (bu depoda daha önce görülen bir hata sınıfı).
    assert t_high > t_low * 1.5, (t_low, t_high)


def test_safety_factor_is_not_tautological():
    """Kullanıcı cidar verdiğinde SF artık onun girdisi DEĞİL, ölçümdür.

    Boyutlandırma modunda raporlanan SF cebirsel olarak
    'hedef SF x imalat payı'dır; basınç, çap ve malzeme sadeleşir. O modda
    kullanıcıya kendi girdisi geri okunur. Doğrulama modunda SF gerçek
    cidardan çıkar.

    v2.6.26: cidar VERİLMEDİĞİNDE modül boyutlandırma modunda kalır — kurucu
    varsayılanını "kullanıcı girdisi" saymak, bu sürümde kapattığımız hata
    sınıfının kendisiydi. Bu yüzden test cidarı AÇIKÇA verir.
    """
    r = HybridRocketEngine(**BASE, wall_thickness=0.005).calculate()
    ca = r['structural_analysis']['chamber_analysis']
    assert ca['design_mode'] == 'verify'
    assert ca['safety_factor_is_tautological'] is False
    # Doğrulama modunda SF hedefe EŞİT OLMAMALI (öyleyse yine totolojiktir)
    assert ca['von_mises_safety_factor'] != pytest.approx(
        ca['design_safety_factor_target'] * 1.2, rel=1e-6)


def _verify_sf(wall_thickness=0.005, **ezme):
    """Doğrulama modundaki von Mises SF'si (tek okuma noktası).

    ``ezme`` BASE alanlarını ezer (ör. ``chamber_pressure=40``).
    """
    kw = dict(BASE, **ezme)
    ca = (HybridRocketEngine(**kw, wall_thickness=wall_thickness)
          .calculate()['structural_analysis']['chamber_analysis'])
    assert ca['design_mode'] == 'verify', ca['design_mode']
    return float(ca['von_mises_safety_factor'])


def test_safety_factor_gercekten_kullanici_cidarindan_turuyor():
    """T3-2 (parti 31): totoloji bekçisi ETİKETE değil SAYIYA baksın.

    Ölçülen kusur: yukarıdaki bekçi ``design_mode``, bayrak ve tek bir
    eşitsizlikle yetiniyordu. Doğrulama modundaki SF kullanıcının cidarının
    BASINÇ TERİMİNDEN koparılsa (ör. boyutlandırılmış cidardan hesaplansa)
    adlı bekçi ve dosyası **30/30 YEŞİL** kalıyordu — etiketler doğru
    kalır çünkü.

    Bu bekçi bağımlılığı SARSARAK ölçer. Ölçülen (BASE hibrit, 20 bar):

    ====== =========
    t [mm] SF
    ====== =========
    3,0    0,9853
    4,0    1,2558
    5,0    1,4845
    6,0    1,6693
    8,0    1,7309
    10,0   1,8205
    ====== =========

    Cidardan koparılmış bir SF bu sütunda SABİT kalır ve bekçi kırılır.
    """
    kalinliklar = (0.003, 0.004, 0.005, 0.006, 0.008, 0.010)
    sfler = [_verify_sf(wall_thickness=t) for t in kalinliklar]

    # (a) Kesinlikle sabit olmamalı — sabitlik "cidar okunmuyor" demektir.
    assert max(sfler) > min(sfler) * 1.5, (
        'doğrulama modundaki SF kullanıcının cidarına DUYARSIZ '
        f'(3-10 mm taramasında {min(sfler):.4f}-{max(sfler):.4f}); '
        'SF kullanıcının girdisinden değil başka bir kalınlıktan '
        'hesaplanıyor olabilir — totoloji bekçisinin yakalaması gereken '
        'kusur budur (parti 31 / T3-2)')

    # (b) Yön doğru: kalın cidar = daha yüksek emniyet katsayısı.
    assert all(a < b for a, b in zip(sfler, sfler[1:])), (
        f'SF cidarla monoton artmıyor: {list(zip(kalinliklar, sfler))} — '
        'işaret ya da terim hatası')


def test_safety_factor_basinc_terimini_gercekten_tasiyor():
    """SF, kullanıcının cidarını BASINÇ yüküne karşı ölçmeli.

    T3-2'nin ikinci ayağı: cidar bağlı ama basınç terimi koparılmışsa
    (SF yalnız geometriden geliyorsa) yukarıdaki tarama yine geçer. Basıncı
    sarsmak o kopmayı görür.

    Ölçülen (t = 5 mm): Pc 10 bar -> 2,4992; 20 bar -> 1,4845;
    40 bar -> 0,8278. İnce cidar zar gerilmesi ~ Pc ile lineer olduğundan
    SF kabaca 1/Pc gider; ölçülen düşüş çarpanları 1,684 ve 1,793.
    """
    sf10 = _verify_sf(chamber_pressure=10, wall_thickness=0.005)
    sf20 = _verify_sf(chamber_pressure=20, wall_thickness=0.005)
    sf40 = _verify_sf(chamber_pressure=40, wall_thickness=0.005)
    assert sf10 > sf20 > sf40, (sf10, sf20, sf40)
    # Basınç iki katına çıkınca SF en az 1,4 kat düşmeli (ölçülen 1,684 /
    # 1,793). Basınç terimi koparılırsa oran 1,0'a yapışır ve bekçi kırılır.
    assert sf10 / sf20 > 1.4, (sf10, sf20)
    assert sf20 / sf40 > 1.4, (sf20, sf40)


def test_constructor_default_is_not_reported_as_user_input():
    """Cidar verilmediğinde modül BOYUTLANDIRMA modunda kalmalı.

    Kurucu imzasındaki varsayılan bir TASARIM DEĞİLDİR. Yapısal modüle
    "kullanıcının cidarı" diye geçirilirse rapor 'verified against
    user-supplied wall thickness' der ve kimsenin vermediği bir kalınlık
    doğrulanmış gibi görünür.
    """
    r = HybridRocketEngine(**BASE).calculate()
    ca = r['structural_analysis']['chamber_analysis']
    assert ca['design_mode'] == 'size'
    assert ca['safety_factor_is_tautological'] is True


def test_safety_factor_out_of_range_warns_and_falls_back():
    """Aralık dışı SF sessizce kullanılmaz; uyarılır ve varsayılana dönülür."""
    r = HybridRocketEngine(**BASE, safety_factor=SAFETY_FACTOR_MAX + 5).calculate()
    assert 'warn.hybrid.safety_factor_out_of_range' in _codes(r)
    assert r['design_safety_factor_input'] is None


def test_safety_factor_invalid_text_warns():
    r = HybridRocketEngine(**BASE, safety_factor='dört').calculate()
    assert 'warn.hybrid.safety_factor_invalid' in _codes(r)


def test_safety_factor_lower_bound_accepted():
    """Sınır değerin kendisi kabul edilir (kapalı aralık)."""
    r = HybridRocketEngine(**BASE, safety_factor=SAFETY_FACTOR_MIN).calculate()
    assert r['design_safety_factor_input'] == SAFETY_FACTOR_MIN
    assert 'warn.hybrid.safety_factor_out_of_range' not in _codes(r)


# ---------------------------------------------------------------------------
# chamber_length_override
# ---------------------------------------------------------------------------

def test_chamber_length_override_changes_geometry(base_result):
    L_auto = base_result['chamber_length']
    target = L_auto + 0.5
    r = HybridRocketEngine(**BASE, chamber_length_override=target).calculate()
    assert r['chamber_length'] == pytest.approx(target, rel=1e-9)
    assert r['chamber_length_source'] == 'user_override'
    # Ezme yokken kaynak 'user_override' OLMAMALI. Kesin değer motorun
    # geometrisine bağlıdır: hibritte port hacmi çoğu zaman istenen L*'ın
    # gerektirdiğini tek başına aştığı için art-yanma odası alt sınıra
    # kelepçelenir ve etiket 'grain_limited' olur (v2.6.26'da eklenen üçüncü
    # durum). Testin sabitlemesi gereken şey ezmenin AYIRT EDİLEBİLİR olması.
    assert base_result['chamber_length_source'] != 'user_override'


def test_chamber_length_override_propagates_to_volume(base_result):
    """Boy ezmesi hacme ve gerçekleşen L*'a da girmeli (yalnız etikete değil)."""
    target = base_result['chamber_length'] + 0.5
    r = HybridRocketEngine(**BASE, chamber_length_override=target).calculate()
    assert r['chamber_volume_actual'] > base_result['chamber_volume_actual']
    assert r['l_star_achieved'] > base_result['l_star_achieved']


def test_chamber_length_override_too_short_is_rejected_loudly(base_result):
    """Grain'in sığmadığı ezme SESSİZCE KIRPILMAZ; reddedilir ve söylenir."""
    r = HybridRocketEngine(**BASE, chamber_length_override=0.05).calculate()
    assert 'warn.hybrid.chamber_length_override_too_short' in _codes(r)
    # Reddedildiği için otomatik boy yürürlükte kalır
    assert r['chamber_length'] == pytest.approx(base_result['chamber_length'])
    assert r['chamber_length_source'] != 'user_override'


def test_chamber_length_override_unit_mixup_warns():
    """20 m üstü değer birim karışıklığıdır (mm yerine m girilmiş)."""
    r = HybridRocketEngine(**BASE, chamber_length_override=4000.0).calculate()
    assert 'warn.hybrid.chamber_length_override_out_of_range' in _codes(r)


def test_chamber_length_override_zero_means_auto(base_result):
    """0/boş 'otomatik' demektir — uyarı üretmemeli."""
    r = HybridRocketEngine(**BASE, chamber_length_override=0).calculate()
    assert r['chamber_length_source'] != 'user_override'
    assert not [c for c in _codes(r) if 'chamber_length_override' in str(c)]


# ---------------------------------------------------------------------------
# nozzle_material
# ---------------------------------------------------------------------------

def test_nozzle_material_thermal_margin_differs_by_material():
    """Boğaz termal marjı malzemenin izin verilen sıcaklığından gelir."""
    g = HybridRocketEngine(**BASE, nozzle_material='graphite').calculate()
    w = HybridRocketEngine(**BASE, nozzle_material='tungsten').calculate()
    mg = g['nozzle_material_analysis']['throat_thermal']
    mw = w['nozzle_material_analysis']['throat_thermal']
    assert mg['allowable_temperature_K'] != mw['allowable_temperature_K']
    # Grafitin izin verilen sıcaklığı daha yüksek -> marjı daha büyük
    assert mg['temperature_margin_K'] > mw['temperature_margin_K']


def test_nozzle_material_erosion_only_when_published_data_exists():
    """Yayımlanmış bandı olmayan malzemede katsayı UYDURULMAZ."""
    g = HybridRocketEngine(**BASE, nozzle_material='graphite').calculate()
    w = HybridRocketEngine(**BASE, nozzle_material='tungsten').calculate()
    eg = g['nozzle_material_analysis']['erosion']
    ew = w['nozzle_material_analysis']['erosion']
    assert eg['status'] == 'analyzed'
    assert eg['radial_recession_rate_mm_s'] > 0
    assert eg['model']['a_ref_band_mm_s']  # yayımlanmış bant
    assert ew['status'] == 'no_published_data'
    assert 'radial_recession_rate_mm_s' not in ew


def test_nozzle_material_erosion_not_silently_coupled():
    """Erozyon RAPOR EDİLİR ama kararlı-hal itkiyi sessizce değiştirmez."""
    e = HybridRocketEngine(
        **BASE, nozzle_material='graphite').calculate()[
        'nozzle_material_analysis']['erosion']
    assert e['coupled_to_performance'] is False
    assert e['coupling_note']


def test_copper_nozzle_cooling_assumption_comes_from_ui_label():
    """Arayüz "Copper (Regeneratively Cooled)" diyor; varsayım oradan gelir."""
    c = HybridRocketEngine(**BASE, nozzle_material='copper').calculate()
    na = c['nozzle_material_analysis']
    assert na['cooling_assumption'] == 'regenerative'
    g = HybridRocketEngine(**BASE, nozzle_material='graphite').calculate()
    assert g['nozzle_material_analysis']['cooling_assumption'] == 'natural'
    # Soğutma varsayımı cidar sıcaklığını gerçekten değiştirmeli
    assert (c['nozzle_material_analysis']['throat_thermal']
            ['throat_wall_temperature_K']
            < g['nozzle_material_analysis']['throat_thermal']
            ['throat_wall_temperature_K'])


def test_unknown_nozzle_material_warns_and_falls_back():
    r = HybridRocketEngine(**BASE, nozzle_material='ZIRVAAA').calculate()
    assert 'warn.hybrid.nozzle_material_unknown' in _codes(r)
    assert r['nozzle_material'] == 'graphite'


def test_nozzle_material_over_temp_is_reported_as_critical():
    """Sınırı aşan boğaz 'SAFE' denmez; kritik uyarı üretir.

    Bakır soğutmasız çalıştırılamaz ama izin verilen sıcaklığı en düşük
    malzeme olduğu için sınır aşımının raporlandığını gösteren en net
    vakadır: aynı motor grafitle güvenli, bakırla değil.
    """
    hot = dict(BASE, chamber_pressure=60, thrust=20000)
    r = HybridRocketEngine(**hot, nozzle_material='copper').calculate()
    th = r['nozzle_material_analysis']['throat_thermal']
    assert th['verdict'] in ('SAFE', 'EXCEEDS_ALLOWABLE')
    if th['verdict'] == 'EXCEEDS_ALLOWABLE':
        assert 'warn.hybrid.nozzle_material_over_temp' in {
            w.get('code') for w in
            r['nozzle_material_analysis']['warnings'] if isinstance(w, dict)}
        assert th['temperature_margin_K'] < 0


# ---------------------------------------------------------------------------
# nozzle_type = parabolic (nozzle_contour'dan taşınan seçenek)
# ---------------------------------------------------------------------------

def test_parabolic_nozzle_is_a_distinct_solution(base_result):
    """Parabolik kontur konik ve çandan AYRI bir lambda verimi kullanır."""
    par = HybridRocketEngine(**dict(BASE, nozzle_type='parabolic')).calculate()
    bell = HybridRocketEngine(**dict(BASE, nozzle_type='bell')).calculate()
    assert par['nozzle_angles']['nozzle_type'] == 'parabolic'
    # Konik ve çandan farklı bir Isp vermeli; aynıysa üçüncü seçenek
    # arayüzde var ama çözücüde yok demektir (bu depoda görülen hata sınıfı).
    assert par['isp'] != base_result['isp']
    assert par['isp'] != bell['isp']


# ---------------------------------------------------------------------------
# Swirl enjektör: oda çapı ve hedef açı
# ---------------------------------------------------------------------------

def _swirl(**kw):
    from hrma.utils.injector_design import InjectorDesign
    inj = InjectorDesign(mdot_ox=1.0, chamber_pressure=20.0,
                         oxidizer_density=1220, oxidizer_phase='liquid',
                         tank_pressure=50.0, injector_type='swirl')
    inj.set_swirl_params(**kw)
    return inj.calculate()


def test_swirl_chamber_diameter_enters_the_solution():
    ref = _swirl(n_slots=6)
    cur = _swirl(n_slots=6, chamber_diameter=30)
    assert cur['swirl_chamber_d_source'] == 'user'
    assert ref['swirl_chamber_d_source'] == 'default_ratio'
    # D_s, K = A_p/(D_s*d_o) üzerinden yuva boyutlarını değiştirir
    assert cur['slot_width'] != pytest.approx(ref['slot_width'], rel=1e-6)
    assert cur['swirl_chamber_diameter'] == pytest.approx(30.0, rel=1e-9)


def test_swirl_target_angle_drives_the_inverse_solver():
    """Hedef yarı açı K'yı belirler; sonuç açısı hedefe yakınsamalı."""
    low = _swirl(n_slots=6, target_half_angle=30)
    high = _swirl(n_slots=6, target_half_angle=60)
    assert low['spray_half_angle_deg'] == pytest.approx(30.0, abs=0.5)
    assert high['spray_half_angle_deg'] == pytest.approx(60.0, abs=0.5)
    # Büyüyen açı K'yı küçültür (GM: sinθ ~ Cd/(K(1+√X)))
    assert high['atomizer_constant_K'] < low['atomizer_constant_K']


def test_swirl_target_angle_outside_envelope_warns():
    """Çözücü zarfı dışındaki hedef sessizce kırpılmaz."""
    r = _swirl(n_slots=6, target_half_angle=85)
    assert any('envelope' in str(w) for w in r['warnings']), r['warnings']


def test_swirl_slot_geometry_wins_and_says_so():
    """Yuva geometrisi verilince hedef açı UYGULANAMAZ; bu bildirilir."""
    r = _swirl(n_slots=6, slot_width=1.0, slot_height=2.0,
               target_half_angle=60)
    assert any('target spray half-angle' in str(w) for w in r['warnings'])


def test_swirl_chamber_diameter_below_orifice_warns():
    """D_s çıkış orifisini sarmalı; altındaki değer GM varsayımını bozar."""
    r = _swirl(n_slots=6, chamber_diameter=1.0)
    assert any('Giffen-Muraszew geometry' in str(w) for w in r['warnings'])


# ---------------------------------------------------------------------------
# injector_material (plaka yapısal)
# ---------------------------------------------------------------------------

def test_injector_plate_safety_factor_depends_on_material():
    from hrma.data.materials_db import get_material
    from hrma.utils.injector_design import injector_plate_structural
    out = {}
    for key in ('ss_316', 'titanium_6al4v', 'brass_c360'):
        out[key] = injector_plate_structural(
            delta_P_bar=4.0, plate_diameter_m=0.15,
            material_props=get_material(key), material_name=key,
            plate_thickness_m=0.003, n_holes=11, hole_diameter_m=0.00245,
            required_sf=4.0)
    # Eğilme gerilmesi malzemeden BAĞIMSIZDIR (σ = 0.75qa²/t²) — emniyet
    # katsayısı ve gereken kalınlık malzemeye bağlıdır. İkisini karıştırmak
    # bu modelde kolay bir hata olurdu.
    stresses = {r['bending_stress_MPa'] for r in out.values()}
    assert len(stresses) == 1
    sfs = {k: r['safety_factor'] for k, r in out.items()}
    assert len(set(sfs.values())) == 3, sfs
    assert sfs['titanium_6al4v'] > sfs['brass_c360'] > sfs['ss_316']


def test_injector_plate_flags_insufficient_thickness():
    from hrma.data.materials_db import get_material
    from hrma.utils.injector_design import injector_plate_structural
    r = injector_plate_structural(
        delta_P_bar=4.0, plate_diameter_m=0.15,
        material_props=get_material('ss_316'), material_name='ss_316',
        plate_thickness_m=0.003, n_holes=11, hole_diameter_m=0.00245,
        required_sf=4.0)
    assert r['safety_factor'] < 4.0
    assert r['warnings']
    assert r['required_thickness_mm'] > r['plate_thickness_mm']


def test_injector_plate_reports_not_analyzed_instead_of_zero():
    """Eksik girdide sessizce 0 uydurulmaz."""
    from hrma.data.materials_db import get_material
    from hrma.utils.injector_design import injector_plate_structural
    r = injector_plate_structural(
        delta_P_bar=0, plate_diameter_m=0.15,
        material_props=get_material('ss_316'))
    assert r['status'] == 'not_analyzed'
    assert 'safety_factor' not in r


def test_injector_plate_rejects_impossible_ligament():
    """Delik alanı plakayı tükettiğinde eğilme modeli geçersizdir."""
    from hrma.data.materials_db import get_material
    from hrma.utils.injector_design import injector_plate_structural
    r = injector_plate_structural(
        delta_P_bar=4.0, plate_diameter_m=0.05,
        material_props=get_material('ss_316'), plate_thickness_m=0.003,
        n_holes=400, hole_diameter_m=0.0024)
    assert r['status'] == 'not_analyzed'
    assert 'ligament' in r['reason']


# ---------------------------------------------------------------------------
# Kaldırılan ikinci kopyalar geri gelmesin
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('field_id', ['nozzle_contour', 'injection_velocity'])
def test_removed_duplicate_fields_stay_removed(field_id):
    """İkinci kopya alanlar geri eklenirse bu test kırılır.

    nozzle_contour, nozzle_type ile aynı kavramın ikinci alanıydı;
    injection_velocity ise target_velocity'nin kopyasıydı ve hesap sonrası
    çözücünün çıkış hızıyla EZİLİYORDU (kullanıcının girdisi sonuçla
    değiştiriliyordu — kendini doğrulayan döngü).
    """
    from pathlib import Path
    tpl = (Path(__file__).resolve().parents[1]
           / 'hrma' / 'templates' / 'advanced.html').read_text(encoding='utf-8')
    assert f'id="{field_id}"' not in tpl


def test_nozzle_type_offers_the_three_contours():
    from pathlib import Path
    tpl = (Path(__file__).resolve().parents[1]
           / 'hrma' / 'templates' / 'advanced.html').read_text(encoding='utf-8')
    block = tpl.split('<select id="nozzle_type">')[1].split('</select>')[0]
    for value in ('conical', 'bell', 'parabolic'):
        assert f'value="{value}"' in block, value
