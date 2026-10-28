"""v3.0.1 (V301/H) — hibrit bilinen sınırlar (CHANGELOG 3.0.1 "Known
limitations", Berke onayı: "hepsini").

Kanıt: ``docs/scofield/raw/OH/V301/bilinen/hibrit/`` (RAPOR.md, once/h1-h4
json'ları, ters mutasyon).

H1 — kullanıcı tank kipinde (``tank_pressure_source = 'user'``) tank kabı:
  ÖLÇÜLDÜ (once.json, taban 6369bf037): kap bloğu NOT_MODELLED ("basınçla
  beslenen tank girdisi yok" — kulvar T'den beri yanlış); slosh tankı doymuş
  sıvı yoğunluğuyla boyutlanıyordu (785,10 kg/m³; devre 60 bar'da 803,03
  kullanıyor) ve hacim 60 ⟷ 80 bar bit-aynıydı.
  Ana model kararı: MEOP = P_tank; kap P_sat kipiyle AYNI analizörden geçer;
  tank sıvısı ρ(P_tank, T) (N₂O'da devrenin giriş hâli yoğunluğu, aynı işlev);
  O/F kaymasının blowdown durumu geçmiş ister → NOT_MODELLED (beyanlı).

Kâhinler ürün kodundan bağımsızdır: ``PressureVesselAnalyzer`` doğrudan
çağrılır (aynı girdiler → aynı sözlük), CoolProp N₂O EOS (Lemmon & Span
2006) ρ(P, T), AIAA S-080A proof/burst katsayıları (1,5 / 2,0) literal.
"""
from __future__ import annotations

import contextlib
import io
import math
import warnings

import pytest

H1 = {
    'thrust': 1000.0, 'burn_time': 10.0, 'chamber_pressure': 20.0,
    'of_ratio': 7.5, 'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
    'tank_pressure': 50.0, 'injector_type': 'showerhead',
    'injector_material': 'stainless_steel', 'chamber_material': 'steel_304',
    'wall_thickness': 5.0, 'safety_factor': 4.0, 'pressure_drop': 4.0,
    'include_plots': False,
}
U = {'tank_pressure_source': 'user'}
#: AIAA S-080A-2018 metalik kap: proof = 1,5 × MEOP, burst = 2,0 × MEOP
#: (kâhin — ürün sabitinden OKUNMAZ).
AIAA_PROOF_KATSAYISI = 1.5
AIAA_BURST_KATSAYISI = 2.0

_CACHE = {}


def _post(yol, govde):
    from hrma.app import app
    app.config['TESTING'] = True
    with contextlib.redirect_stdout(io.StringIO()), warnings.catch_warnings():
        warnings.simplefilter('ignore')
        with app.test_client() as ist:
            r = ist.post(yol, json=govde)
    return r.status_code, r.get_json()


def _ok(anahtar, govde, yol='/calculate'):
    if anahtar not in _CACHE:
        _CACHE[anahtar] = _post(yol, govde)
    kod, j = _CACHE[anahtar]
    assert kod == 200, j
    return j


def _n2o_user(p):
    return _ok(f'n2o_u{p}', dict(H1, tank_pressure=p, **U))['motor']


# =========================================================================
# H1 — kullanıcı tank kipinde tank kabı (MEOP), slosh, O/F kayması
# =========================================================================
def test_h1_kap_modellenir_meop_kullanici_tank_basinci():
    m = _n2o_user(60.0)
    kap = m['oxidizer_tank_pressure_vessel']
    assert kap['status'] == 'modelled'
    assert kap['meop_bar'] == 60.0 == m['tank_pressure']
    assert kap['tank_pressure_source'] == 'user'
    # Künye: tanım gereği işletme basıncı + modellenmeyen iki etki adıyla.
    for parca in ('by definition', 'regulator lock-up', 'thermal excursion'):
        assert parca in kap['meop_source'], parca
    assert 'tank_blowdown solution' not in kap['meop_source']


def test_h1_kap_ayni_analizorden_ayni_girdilerle():
    """Kopya kural yok: blok = analizörün AYNI girdilerle doğrudan çağrısı."""
    from hrma.analysis.pressure_vessel import PressureVesselAnalyzer
    from hrma.engines.hybrid_rocket_engine import OX_TANK_MATERIAL_DEFAULT
    m = _n2o_user(60.0)
    kap = m['oxidizer_tank_pressure_vessel']
    sl = m['oxidizer_tank_slosh']
    assert kap['inner_diameter_m'] == sl['tank_diameter_m']
    beklenen = PressureVesselAnalyzer().analyze(
        meop_bar=60.0, inner_diameter_mm=sl['tank_diameter_m'] * 1000.0,
        material=OX_TANK_MATERIAL_DEFAULT, wall_thickness_mm=None,
        temperature_K=kap['design_temperature_K'])
    pv = kap['pressure_vessel']
    for anahtar in ('required_thickness_mm', 'wall_thickness_used_mm',
                    'mawp_bar', 'proof_pressure_bar',
                    'required_burst_pressure_bar', 'actual_burst_pressure_bar',
                    'burst_margin', 'status', 'head_thickness_selected_mm'):
        assert pv[anahtar] == beklenen[anahtar], anahtar
    assert pv['proof_pressure_bar'] == pytest.approx(
        AIAA_PROOF_KATSAYISI * 60.0, rel=1e-12)
    assert pv['required_burst_pressure_bar'] == pytest.approx(
        AIAA_BURST_KATSAYISI * 60.0, rel=1e-12)


def test_h1_kap_tasarim_sicakligi_tank_sicakligi():
    from hrma.engines.hybrid_rocket_engine import TANK_TEMPERATURE_DEFAULT_K
    kap = _n2o_user(60.0)['oxidizer_tank_pressure_vessel']
    assert kap['design_temperature_K'] == TANK_TEMPERATURE_DEFAULT_K
    j = _ok('n2o_u60_T280', dict(H1, tank_pressure=60.0, oxidizer_temp=280.0,
                                 **U))
    kap280 = j['motor']['oxidizer_tank_pressure_vessel']
    assert kap280['design_temperature_K'] == 280.0
    assert 'user input' in kap280['design_temperature_source']


def test_h1_slosh_tanki_rho_p_tank_t_ile_boyutlanir():
    """V = (m_ox / ρ(P_tank, T)) / doluluk; ρ = devrenin giriş hâli
    yoğunluğu = CoolProp N₂O EOS (kâhin)."""
    CP = pytest.importorskip('CoolProp.CoolProp')
    from hrma.engines.hybrid_rocket_engine import TANK_FILL_FRACTION_DEFAULT
    for p in (60.0, 80.0):
        m = _n2o_user(p)
        sl = m['oxidizer_tank_slosh']
        rho_eos = CP.PropsSI('D', 'T', 293.15, 'P', p * 1e5, 'N2O')
        assert sl['liquid_density_kg_m3'] == pytest.approx(rho_eos,
                                                           rel=1e-12)
        assert sl['liquid_density_kg_m3'] == m['injector_design'][
            'inlet_state']['liquid_density_kg_m3']
        v = sl['liquid_mass_kg'] / sl['liquid_density_kg_m3'] \
            / TANK_FILL_FRACTION_DEFAULT
        assert sl['tank_volume_m3'] == pytest.approx(v, rel=1e-12)
        assert sl['liquid_fill_fraction'] == TANK_FILL_FRACTION_DEFAULT
        assert 'P_tank' in sl['liquid_density_basis']
        assert "tank_pressure_source = 'user'" in sl['tank_volume_source']
    # Basınç artınca sıkıştırılmış sıvı yoğunlaşır → tank küçülür.
    assert (_n2o_user(80.0)['oxidizer_tank_slosh']['tank_volume_m3']
            < _n2o_user(60.0)['oxidizer_tank_slosh']['tank_volume_m3'])


def test_h1_of_kaymasi_blowdown_durumu_beyanli_not_modelled():
    of = _n2o_user(60.0)['of_shift']
    assert of['status'] == 'modelled'
    assert of['regulated'].get('of_ratio_design') is not None
    assert of['blowdown']['status'] == 'NOT_MODELLED'
    assert 'pressure history' in of['blowdown']['reason']
    assert 'regulated' in of['user_tank_pressure_basis']
    assert 'time_s' not in of['blowdown']


def test_h1_lox_kullanici_kipi_kap_referans_durumda():
    from hrma.data.external_data_fetcher import OXIDIZER_REFERENCE_STATE
    m = _ok('lox_u30', dict(H1, oxidizer_type='lox', of_ratio=2.5,
                            tank_pressure=30.0, **U))['motor']
    kap = m['oxidizer_tank_pressure_vessel']
    assert kap['status'] == 'modelled'
    assert kap['meop_bar'] == 30.0
    assert kap['design_temperature_K'] == OXIDIZER_REFERENCE_STATE['lox'][0]
    assert 'No compressed-liquid' in m['oxidizer_tank_slosh'][
        'liquid_density_basis']


def test_h1_psat_kipi_degismedi_ve_kullanici_alanlari_yok():
    """Kendinden basınçlı kip: MEOP blowdown serisinin maksimumu (bit-aynı
    kanıtı once/h1 md5'inde; burada yapı)."""
    m = _ok('n2o_psat', dict(H1))['motor']
    kap = m['oxidizer_tank_pressure_vessel']
    assert kap['meop_bar'] == max(m['tank_blowdown']['tank_pressure_bar'])
    assert 'tank_pressure_source' not in kap
    assert 'liquid_density_basis' not in m['oxidizer_tank_slosh']
    assert 'user_tank_pressure_basis' not in m['of_shift']


def test_h1_lox_varsayilan_kap_reddi_artik_kullanici_kipini_gosterir():
    kap = _ok('lox_def', dict(H1, oxidizer_type='lox', of_ratio=2.5))[
        'motor']['oxidizer_tank_pressure_vessel']
    assert kap['status'] == 'NOT_MODELLED'
    assert 'does not exist on the hybrid page' not in kap['reason']
    assert "tank_pressure_source = 'user'" in kap['reason']
    assert 'meop_bar' not in kap


def test_h1_tank_sicakligi_tanimsiz_oksitleyicide_sayi_uydurulmaz():
    from hrma.engines import hybrid_rocket_engine as h

    class _Motor:
        oxidizer_type = 'gox'
        tank_temperature = None
        _user_tank_feed = {'tank_pressure_bar': 40.0}

    durum = h.user_tank_vessel_state(_Motor())
    assert durum['design_temperature_K'] is None
    assert durum['meop_bar'] == 40.0
    assert 'no reference liquid state' in durum['fields'][
        'design_temperature_source']


# =========================================================================
# H2 — koaksiyel enjektör devrede (tek akışkanlı eleman), ekran = devre
# =========================================================================
#: Ekran = devre eşitliği (tek kanon) ve kâhin toleransı.
KANON_REL = 1e-12


def _koaks(anahtar, **ek):
    return _ok(anahtar, dict(H1, injector_type='coaxial', **ek))


def test_h2_koaksiyel_devrede_cozulur_nhne_ve_besleme_dp():
    from hrma.engines.injector_design import COAXIAL_SINGLE_FLUID_TYPE
    j = _koaks('koaks_psat')
    ozet = j['motor']['injector_design']
    det = j['motor']['injector_design_detail']
    oxc = det['ox_circuit']
    assert ozet.get('status') != 'not_analyzed', ozet
    assert ozet['model_injector_type'] == COAXIAL_SINGLE_FLUID_TYPE
    assert ozet['injector_type'] == 'coaxial'
    assert oxc['flow_model'] == 'NHNE'
    # Besleme gerçeği: P₁ = P_sat(T) (kendinden basınçlı), ΔP = P₁ − P_c.
    assert oxc['delta_p_bar'] == pytest.approx(
        oxc['vapor_pressure_bar'] - H1['chamber_pressure'], rel=1e-12)
    assert ozet['feed_pressure_source'] == \
        'n2o_saturation_at_tank_temperature'
    assert 'coaxial_geometry' in ozet and 'EQUIVALENT' in ozet[
        'orifice_plan_basis']


def test_h2_ekran_devreyi_tuketir():
    j = _koaks('koaks_psat')
    g = j['motor']['injector_design_detail']['coaxial_geometry']
    oxc = j['motor']['injector_design_detail']['ox_circuit']
    inj = j['injector']
    esler = (('injection_area', 'total_flow_area_mm2'),
             ('inner_jet_diameter', 'inner_jet_diameter_mm'),
             ('annulus_inner_diameter', 'annulus_inner_diameter_mm'),
             ('annulus_outer_diameter', 'annulus_outer_diameter_mm'),
             ('annulus_gap', 'annulus_gap_mm'),
             ('recess_length', 'recess_length_mm'),
             ('inner_flow_fraction', 'inner_flow_fraction'),
             ('element_count', 'element_count'))
    for ekran, devre in esler:
        assert inj[ekran] == pytest.approx(g[devre], rel=KANON_REL), ekran
    assert inj['pressure_drop_bar'] == pytest.approx(oxc['delta_p_bar'],
                                                     rel=KANON_REL)
    assert inj['discharge_coefficient'] == oxc['cd']
    assert inj['pressure_drop_source'] == 'injector circuit solution'
    assert inj['circuit_solution'].startswith('consumed')


def test_h2_geometri_kahini_alan_bolunmesi():
    """A_iç = f·A, d = 2√(A_iç/π), (π/4)(D_o² − D_i²) = A_anülüs,
    t = max(0,5 mm; 0,1·d), girinti = 1·d (HRMA plaka kuralları, literal)."""
    for anahtar, ek in (('koaks_psat', {}),
                        ('koaks_pay04', {'coaxial_inner_flow_fraction': 0.4})):
        g = _koaks(anahtar, **ek)['motor']['injector_design_detail'][
            'coaxial_geometry']
        A = g['total_flow_area_mm2']
        f = g['inner_flow_fraction']
        d = 2.0 * math.sqrt(f * A / math.pi)
        t = max(0.5, 0.1 * d)
        D_i = d + 2.0 * t
        D_o = math.sqrt(D_i ** 2 + 4.0 * (1.0 - f) * A / math.pi)
        assert g['inner_jet_diameter_mm'] == pytest.approx(d, rel=1e-12)
        assert g['post_wall_thickness_mm'] == pytest.approx(t, rel=1e-12)
        assert g['annulus_inner_diameter_mm'] == pytest.approx(D_i, rel=1e-12)
        assert g['annulus_outer_diameter_mm'] == pytest.approx(D_o, rel=1e-12)
        assert g['annulus_gap_mm'] == pytest.approx((D_o - D_i) / 2.0,
                                                    rel=1e-12)
        assert g['recess_length_mm'] == pytest.approx(d, rel=1e-12)
        assert g['inner_jet_area_mm2'] + g['annulus_area_mm2'] == \
            pytest.approx(A, rel=1e-12)
    g4 = _koaks('koaks_pay04', coaxial_inner_flow_fraction=0.4)[
        'motor']['injector_design_detail']['coaxial_geometry']
    assert g4['inner_flow_fraction'] == 0.4
    assert g4['inner_flow_fraction_source'] == \
        'request (coaxial_inner_flow_fraction)'


def test_h2_nhne_kahini_toplam_alan_hedef_debiyi_tasir():
    from hrma.engines.injector_design import nhne_mass_flow
    j = _koaks('koaks_psat')
    oxc = j['motor']['injector_design_detail']['ox_circuit']
    g = j['motor']['injector_design_detail']['coaxial_geometry']
    nh = oxc['nhne']
    p1 = H1['chamber_pressure'] + oxc['delta_p_bar']
    rho = oxc['mdot_kg_s'] / (oxc['velocity_m_s']
                              * g['total_flow_area_mm2'] * 1e-6)
    mdot = nhne_mass_flow(oxc['cd'], g['total_flow_area_mm2'] * 1e-6, p1,
                          H1['chamber_pressure'], nh['p_sat_bar'], 293.15,
                          rho)['mdot_kg_s']
    assert mdot == pytest.approx(oxc['mdot_kg_s'], rel=1e-9)


def test_h2_kullanici_tank_kipi_ve_lox_spi():
    j = _koaks('koaks_u60', tank_pressure=60.0, **U)
    oxc = j['motor']['injector_design_detail']['ox_circuit']
    assert oxc['delta_p_bar'] == pytest.approx(60.0 - 20.0, rel=1e-12)
    assert j['injector']['pressure_drop_bar'] == pytest.approx(40.0,
                                                               rel=1e-12)
    jl = _koaks('koaks_lox', oxidizer_type='lox', of_ratio=2.5)
    oxl = jl['motor']['injector_design_detail']['ox_circuit']
    gl = jl['motor']['injector_design_detail']['coaxial_geometry']
    assert oxl['flow_model'] == 'SPI'
    rho = oxl['mdot_kg_s'] / (oxl['velocity_m_s']
                              * gl['total_flow_area_mm2'] * 1e-6)
    a_spi = oxl['mdot_kg_s'] / (oxl['cd'] * math.sqrt(
        2.0 * rho * oxl['delta_p_bar'] * 1e5))
    assert gl['total_flow_area_mm2'] * 1e-6 == pytest.approx(a_spi,
                                                            rel=1e-12)


def test_h2_dp_ezmesinde_ekran_kendi_dp_siyle_beyanli():
    j = _koaks('koaks_ezme', pressure_drop_source='user')
    inj = j['injector']
    assert inj['pressure_drop_bar'] == 4.0
    assert inj['circuit_solution'].startswith('not consumed')
    # Aynı geometri işlevi kendi alanına uygulanır.
    from hrma.engines.injector_design import coaxial_element_geometry
    g = coaxial_element_geometry(inj['injection_area'] * 1e-6,
                                 inj['inner_flow_fraction'])
    assert inj['inner_jet_diameter'] == pytest.approx(g['d_inner'] * 1e3,
                                                      rel=1e-12)


def test_h2_sivi_yolu_ayri_ad_koaksiyel_tek_akiskan_sivida_yok():
    from hrma.engines.injector_design import (
        COAXIAL_SINGLE_FLUID_TYPE, _VALID_TYPES, design_coaxial_element,
        design_injector)
    assert COAXIAL_SINGLE_FLUID_TYPE not in _VALID_TYPES
    with pytest.raises(ValueError, match='coax_swirl'):
        design_coaxial_element({'motor_type': 'liquid', 'mdot_ox': 1.0,
                                'Pc_bar': 30.0})
    with pytest.raises(ValueError, match='Invalid injector_type'):
        design_injector({'motor_type': 'liquid',
                         'injector_type': COAXIAL_SINGLE_FLUID_TYPE,
                         'mdot_ox': 1.0, 'mdot_fuel': 0.4, 'Pc_bar': 30.0})


@pytest.mark.parametrize('pay,neden', [(0.05, 'out_of_range'),
                                       (0.95, 'out_of_range'),
                                       ('0.5', 'not_a_number'),
                                       (True, 'not_a_number'),
                                       (float('nan'), 'not_a_number')])
def test_h2_python_api_pay_kapisi(pay, neden):
    from hrma.engines.injector_design import (ElementPlanInputError,
                                              design_coaxial_element)
    with pytest.raises(ElementPlanInputError) as e:
        design_coaxial_element({
            'motor_type': 'hybrid', 'mdot_ox': 0.4, 'Pc_bar': 20.0,
            'fluid_ox': 'n2o', 'T_ox_K': 293.15,
            'coaxial': {'inner_flow_fraction': pay}})
    assert e.value.invalid_fields[0]['reason'] == neden


def test_h2_sabitler_tek_yerde_ekran_kimlik_takma_adi():
    import hrma.engines.injector_design as dev
    import hrma.utils.injector_design as ekr
    for ad in ('COAX_INNER_FLOW_FRACTION', 'COAX_INNER_FLOW_FRACTION_BAND',
               'COAX_INNER_FLOW_FRACTION_BASIS', 'COAX_RECESS_LD',
               'COAX_WALL_MIN_MM'):
        assert getattr(ekr, ad) is getattr(dev, ad), ad


# =========================================================================
# H3 — doymuş N₂O girişinde K_c = 0 / flaş uyarıları bilgi kaydına iner
# (E2 KARAR-8; ana model 22 Eki, ajan durdurulduktan sonra)
# =========================================================================
def _inj_uyarilari(j):
    return (j.get('injector') or {}).get('warnings') or []


def test_h3_doymus_giriste_kavitasyon_ve_flas_bilgi_kaydina_iner():
    from hrma.utils.injector_design import (
        SATURATED_INLET_NOTE, SATURATED_INLET_NOTE_CODE)
    uy = _inj_uyarilari(_ok('h3_psat', H1))
    metinler = [w for w in uy if isinstance(w, str)]
    assert not any(m.startswith('Cavitation risk') for m in metinler), metinler
    assert 'Flash boiling risk detected' not in metinler, metinler
    bilgi = [w for w in uy if isinstance(w, dict)
             and w.get('code') == SATURATED_INLET_NOTE_CODE]
    assert len(bilgi) == 1, uy
    assert bilgi[0]['severity'] == 'info'
    assert bilgi[0]['message'] == SATURATED_INLET_NOTE


def test_h3_kullanici_tank_kipinde_degerlendirme_aynen_kalir():
    """P₁ > P_v: bayrak kapalı, bilgi kaydı yok (değerlendirme eskisi gibi)."""
    from hrma.utils.injector_design import SATURATED_INLET_NOTE_CODE
    uy = _inj_uyarilari(_ok('h3_u60', dict(H1, tank_pressure=60.0, **U)))
    assert not any(isinstance(w, dict)
                   and w.get('code') == SATURATED_INLET_NOTE_CODE
                   for w in uy), uy


# =========================================================================
# H4 — geçici uç: blowdown ⟷ kullanıcı tank kipi
# =========================================================================
_H4_BLOWDOWN = {'feed_mode': 'blowdown', 'tank_temperature': 293.15,
                'liquid_fill_fraction': 0.85}


def test_h4_kullanici_tank_kipi_blowdown_422_regulated_200():
    kod, ret = _post('/api/transient-analysis',
                     dict(H1, tank_pressure=60.0, **U, **_H4_BLOWDOWN))
    assert kod == 422, ret
    assert ret['error'] == 'feed_mode_conflicts_with_tank_pressure_source'
    assert ret['invalid_fields'][0]['field'] == 'feed_mode'
    kod, j = _post('/api/transient-analysis',
                   dict(H1, tank_pressure=60.0, feed_mode='regulated', **U))
    assert kod == 200, j
    # Varsayılan (doyma) kipte blowdown aynen çalışır.
    kod, j = _post('/api/transient-analysis', dict(H1, **_H4_BLOWDOWN))
    assert kod == 200, j


_H4_PANEL_DUZENEGI = r"""
'use strict';
const fs = require('fs'); const vm = require('vm'); const path = require('path');
const IN = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const alanlar = IN.form || {};
const secenek = (v) => ({ value: v, disabled: false });
const sel = { value: IN.secili || 'regulated',
              options: [secenek('regulated'), secenek('blowdown')] };
const not = { style: { display: 'none' } };
const grup = { style: { display: '' } };
const sandbox = { console, JSON, Object, Array, Math, Number, String,
                  isFinite, parseFloat, NaN };
sandbox.window = sandbox;
sandbox.document = { getElementById: (id) => {
    if (id === 'tp_feed_mode') return sel;
    if (id === 'tp_feed_note') return not;
    if (id === 'tp_tank_temp_group' || id === 'tp_fill_group') return grup;
    return (id in alanlar) ? { value: alanlar[id] } : null; } };
if (IN.currentRequest) sandbox.currentRequest = IN.currentRequest;
vm.createContext(sandbox);
const dizin = path.dirname(process.argv[2]);
vm.runInContext(fs.readFileSync(path.join(dizin, 'units_constants.js'), 'utf8'),
                sandbox, { filename: 'units_constants.js' });
vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), sandbox,
                { filename: 'transient_panel.js' });
sandbox.TransientPanel._beslemeKipiniEsle();
const govde = sandbox.TransientPanel._collectMotorParams();
process.stdout.write(JSON.stringify({ blowdown_kapali: sel.options[1].disabled,
    secili: sel.value, not: not.style.display, govde }));
"""


def _h4_panel(tmp_path, girdi):
    import json
    import pathlib
    import shutil
    import subprocess
    node = shutil.which('node')
    if node is None:
        pytest.skip('node kurulu değil')
    panel = (pathlib.Path(__file__).resolve().parents[1] / 'hrma' / 'static'
             / 'js' / 'transient_panel.js')
    duzenek = tmp_path / 'h4.js'
    duzenek.write_text(_H4_PANEL_DUZENEGI, encoding='utf-8')
    dosya = tmp_path / 'in.json'
    dosya.write_text(json.dumps(girdi), encoding='utf-8')
    islem = subprocess.run([node, str(duzenek), str(panel), str(dosya)],
                           capture_output=True, text=True, timeout=60)
    assert islem.returncode == 0, islem.stderr
    return json.loads(islem.stdout)


def test_h4_panel_kullanici_kipinde_blowdown_kapanir(tmp_path):
    s = _h4_panel(tmp_path, {'currentRequest': dict(H1, tank_pressure=60.0,
                                                    **U),
                             'secili': 'blowdown'})
    assert s['blowdown_kapali'] is True
    assert s['secili'] == 'regulated'
    assert s['not'] == ''
    s = _h4_panel(tmp_path, {'currentRequest': dict(H1),
                             'secili': 'blowdown'})
    assert s['blowdown_kapali'] is False and s['secili'] == 'blowdown'
    assert s['not'] == 'none'


def test_h4_panel_form_yedegi_kipi_gonderir(tmp_path):
    s = _h4_panel(tmp_path, {'form': {'tank_pressure_source': 'user',
                                      'thrust': '1000'}})
    assert s['govde'].get('tank_pressure_source') == 'user'
    s = _h4_panel(tmp_path, {'form': {'tank_pressure_source': 'default',
                                      'thrust': '1000'}})
    assert 'tank_pressure_source' not in s['govde']
