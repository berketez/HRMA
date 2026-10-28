# -*- coding: utf-8 -*-
"""V3.0.5 / SIVI-CIDAR — sıvı cidar/termal hükmünde fiziksel olmayan sayı yok.

Kanıt dizini: docs/scofield/raw/OH/V301/sivi-cidar/ (RAPOR.md, olcum/).

Kalem 1 (S1) — kök (ÖLÇÜLDÜ, taban 379e35f23, ``olcum/k1_once.json``): istasyon
marşı koşmayan rejeneratif sıvıda (Pc 100 bar, Inconel 718 astar 5 mm; marş
ince-cidar zarfıyla reddediliyor) astar katmanı sıcak cidarı 800 K tasarım
varsayımında TUTUYOR ve soğuk yüzü T_sıcak − q·t/k diye kuruyordu:
T_soğuk −2164,87 K, ortalama −682,44 K, SF 0,2026 (ret, ama fiziksel olmayan
sayılarla). Etanol rejeneratifte aynı dal −2501,4 K yayımlıyordu.

Onarım (Berke 28 Eki: "madem çözülmemiş, çözelim"): marş koşmayan yolda
boğaz istasyonu 1B seri devreyle ÇÖZÜLÜR (gaz tarafı h_gc ⟷ silindirik astar
iletimi ⟷ soğutucu Dittus-Boelter + Sieder-Tate + kaburga kanadı), ceketin iki
ucunda (soğutucu giriş ve toplu çıkış sıcaklığı). Çözüm yolu yoksa (soğutucu
özellik tablosu yok) eski varsayım fiziksel tutarlılık kapısından geçer;
tutarsızsa katman hükmü sayılarıyla GERİ ÇEKİLİR (sıcaklık/SF yayımlanmaz).

Bekçiler:
  * üç motor tipinin bütün ``wall_layers`` sıcaklıkları > 0 K ve fiziksel
    sırada (T_soğutucu < T_soğuk ≤ T_ort ≤ T_sıcak < T_c);
  * boğaz çözümü yayımlanan sayılardan yeniden kurulur (seri devre);
  * tutarsız varsayımda hüküm geri çekilir, gerekçe sayılarıyla, uyarı EN + TR;
  * geri çekilen katman ekranda hangi sıcaklıkta hangi sınırın aşıldığını
    sayılarıyla söyler (uyarı kanalı).
"""
import contextlib
import io
import json
import math
import os
from pathlib import Path

import pytest

from tests.support import form_defaults

KOK = Path(__file__).resolve().parents[1]
H = {'Host': '127.0.0.1:8080'}

#: tests/test_z5guard_ihrac_veri.py SIVI_GOVDE ile aynı gövde (kopya değil,
#: o modülün sabiti okunur).
from tests.test_z5guard_ihrac_veri import SIVI_GOVDE  # noqa: E402


def _sessiz(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


@pytest.fixture(scope='module')
def client(tmp_path_factory):
    os.environ.setdefault('HRMA_PROJECTS_DIR',
                          str(tmp_path_factory.mktemp('projeler')))
    os.environ.setdefault('BROWSER', 'echo')
    from hrma.app import app
    return app.test_client()


def _sivi(client, **ek):
    r = _sessiz(client.post, '/calculate_liquid',
                json=dict(SIVI_GOVDE, **ek), headers=H)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


@pytest.fixture(scope='module')
def kalin(client):
    """Inconel 5 mm astar: marş ince-cidar zarfıyla reddedilir."""
    return _sivi(client, chamber_wall_thickness=5)


@pytest.fixture(scope='module')
def ince(client):
    """Inconel 1 mm astar: RP-1 istasyon marşı koşar."""
    return _sivi(client)


@pytest.fixture(scope='module')
def etanol(client):
    """Etanol rejeneratif: soğutucu özellik tablosu yok (çözüm yolu yok)."""
    return _sivi(client, fuel_type='ethanol', mixture_ratio=1.5)


def _katmanlar(b):
    return b['structural_analysis']['chamber_structure']['wall_layers']


def _kodlar(b, siddet=None):
    return [w for w in (b.get('input_warnings') or [])
            if isinstance(w, dict)
            and (siddet is None or w.get('severity') == siddet)]


def _sicaklik_alanlari(dugum, yol=''):
    """wall_layers altında bütün sayısal sıcaklık alanları (ad, değer)."""
    if isinstance(dugum, dict):
        for k, v in dugum.items():
            alt = f'{yol}.{k}'
            if (isinstance(v, (int, float)) and not isinstance(v, bool)
                    and (k.startswith('T_') or 'temperature_K' in k)
                    and k.endswith('_K')
                    and not any(s in k for s in ('drop', 'minus',
                                                 'difference'))):
                yield alt, float(v)
            else:
                yield from _sicaklik_alanlari(v, alt)
    elif isinstance(dugum, list):
        for i, v in enumerate(dugum):
            yield from _sicaklik_alanlari(v, f'{yol}[{i}]')


def _istasyon_sirasi(st, T_c, yol):
    """T_soğutucu < T_soğuk ≤ T_ort ≤ T_sıcak < T_c (varsa)."""
    sorun = []
    th, tc = st.get('T_hot_K'), st.get('T_cold_K')
    tm, tsog = st.get('mean_temperature_K'), st.get('T_coolant_K')
    if th is not None and tc is not None and not tc <= th:
        sorun.append(f'{yol}: T_cold {tc} > T_hot {th}')
    if tm is not None and th is not None and tc is not None \
            and not tc <= tm <= th:
        sorun.append(f'{yol}: T_mean {tm} not between {tc} and {th}')
    if tsog is not None and tc is not None and not tsog < tc:
        sorun.append(f'{yol}: T_cold {tc} not above coolant {tsog}')
    if T_c is not None and th is not None and not th < T_c:
        sorun.append(f'{yol}: T_hot {th} not below T_c {T_c}')
    return sorun


def _fiziksel_sira_sorunlari(b):
    sorun = []
    st_blok = (b.get('structural_analysis') or {}).get('chamber_structure')
    katmanlar = (st_blok or {}).get('wall_layers') or []
    for yol, deger in _sicaklik_alanlari(katmanlar, 'wall_layers'):
        if not (math.isfinite(deger) and deger > 0.0):
            sorun.append(f'{yol} = {deger} (not a temperature)')
    T_c = b.get('chamber_temperature')
    for i, kat in enumerate(katmanlar):
        for ad in ('governing_station', 'throat_station'):
            if isinstance(kat.get(ad), dict):
                sorun += _istasyon_sirasi(kat[ad], T_c,
                                          f'wall_layers[{i}].{ad}')
        for j, s in enumerate(kat.get('throat_solution_bounds') or []):
            sorun += _istasyon_sirasi(
                s, T_c, f'wall_layers[{i}].throat_solution_bounds[{j}]')
        if kat.get('max_temperature_K') is not None and \
                kat.get('mean_temperature_K') is not None:
            if not kat['mean_temperature_K'] <= kat['max_temperature_K']:
                sorun.append(f'wall_layers[{i}]: mean above max')
    return sorun


# ---------------------------------------------------------------------------
# Kalem 1 — bekçi: üç motor tipinin bütün wall_layers sıcaklıkları fiziksel
# ---------------------------------------------------------------------------
class TestCidarSicaklikFiziksel:

    @pytest.mark.parametrize('vaka', ['ince', 'kalin', 'etanol', 'ornek'])
    def test_sivi_vakalari_fiziksel_sirada(self, request, client, vaka):
        if vaka == 'ornek':
            from tests.test_example_projects import (ENDPOINTS, HEADERS,
                                                     calculate_payload,
                                                     load_example_doc)
            f = dict(load_example_doc('liquid')['inputs']['fields'])
            r = _sessiz(client.post, ENDPOINTS['liquid'],
                        json=calculate_payload('liquid', f), headers=HEADERS)
            assert r.status_code == 200
            b = r.get_json()
        else:
            b = request.getfixturevalue(vaka)
        assert _katmanlar(b), 'rejeneratif sıvıda iki katman bekleniyor'
        assert _fiziksel_sira_sorunlari(b) == []

    @pytest.mark.parametrize('tip', ['hybrid', 'solid'])
    def test_hibrit_kati_ornek_fiziksel(self, client, tip):
        from tests.test_example_projects import (ENDPOINTS, HEADERS,
                                                 calculate_payload,
                                                 load_example_doc)
        f = dict(load_example_doc(tip)['inputs']['fields'])
        r = _sessiz(client.post, ENDPOINTS[tip],
                    json=calculate_payload(tip, f), headers=HEADERS)
        assert r.status_code == 200
        b = r.get_json()
        # Bugün katı/hibritte iki katmanlı cidar yok; çıkarsa aynı kural.
        assert _fiziksel_sira_sorunlari(b) == []


# ---------------------------------------------------------------------------
# Kalem 1 — marş koşmayan yolda boğaz ÇÖZÜLÜR (seri devre yeniden kurulur)
# ---------------------------------------------------------------------------
class TestBogazCozumu:

    def test_mars_reddedildi_ve_cozum_kaynagi(self, kalin):
        tp = kalin['thermal_protection']
        assert 'station_march' not in tp
        assert 'thin-wall envelope' in tp['station_march_status']
        astar = _katmanlar(kalin)[0]
        assert astar['temperature_source'].startswith('SOLVED at the throat')
        assert len(astar['throat_solution_bounds']) == 2
        assert {s['coolant_bound'] for s in astar['throat_solution_bounds']} \
            == {'coolant_inlet', 'coolant_exit'}

    def test_seri_devre_yayimlanan_sayilardan(self, kalin):
        from hrma.data.materials_db import get_material_safe
        cs = kalin['cooling_system']
        astar = _katmanlar(kalin)[0]
        k = float(get_material_safe(astar['material_key'])[0][
            'thermal_conductivity'])
        # r1 = boğaz yarıçapı: istasyonun kendi yayımladığı r_mm
        r1 = astar['throat_station']['r_mm'] / 1000.0
        r2 = r1 + astar['thickness_mm'] / 1000.0
        T_c = float(kalin['chamber_temperature'])
        h_gc = float(cs['gas_side_conductance_throat'])
        uclar = {'coolant_inlet': cs['coolant_inlet_temperature'],
                 'coolant_exit': cs['coolant_exit_temperature']}
        for s in astar['throat_solution_bounds']:
            assert s['T_coolant_K'] == pytest.approx(
                uclar[s['coolant_bound']], rel=1e-12)
            assert s['gas_side_conductance_W_m2K'] == pytest.approx(
                h_gc, rel=1e-12)
            r_sog = 1.0 / (s['coolant_htc_W_m2K']
                           * s['fin_area_ratio_gas_side'])
            r_top = 1.0 / h_gc + r1 * math.log(r2 / r1) / k + r_sog
            q = (T_c - s['T_coolant_K']) / r_top
            assert s['heat_flux_MW_m2'] == pytest.approx(q / 1e6, rel=1e-9)
            assert s['T_hot_K'] == pytest.approx(T_c - q / h_gc, rel=1e-9)
            assert s['T_cold_K'] == pytest.approx(
                s['T_coolant_K'] + q * r_sog, rel=1e-9)
        yon = min(astar['throat_solution_bounds'],
                  key=lambda s: s['safety_factor'])
        assert astar['safety_factor'] == yon['safety_factor']
        assert astar['max_temperature_K'] == max(
            s['T_hot_K'] for s in astar['throat_solution_bounds'])

    def test_erime_ustu_cozulen_sicaklik_sayilariyla_uyarida(self, kalin):
        """Çözülen sıcak cidar erimenin üstünde: hüküm geri çekilir ve uyarı
        hangi sıcaklıkta hangi sınırın aşıldığını sayılarıyla taşır."""
        astar = _katmanlar(kalin)[0]
        assert astar['verdict'] == 'withheld'
        mv = astar['model_validity']
        assert mv['model_validity_limit_exceeded'] is True
        olcum = mv['model_validity_evaluations']['liner_hot_wall']
        assert olcum['wall_temperature_K'] == pytest.approx(
            astar['max_temperature_K'], rel=1e-12)
        assert olcum['wall_temperature_K'] > olcum['melting_point_K']
        uy = [w for w in _kodlar(kalin, 'critical')
              if w.get('code') == 'warn.liquid.liner_outside_validity']
        assert len(uy) == 1
        p = uy[0]['params']
        assert p['temperature_K'] == round(olcum['wall_temperature_K'], 1)
        assert p['melting_K'] == round(olcum['melting_point_K'], 1)
        assert p['curve_last_K'] == round(
            olcum['derating_curve_last_point_K'], 1)

    def test_imalat_kapisi_gercek_sicaklikla_reddeder(self, kalin):
        from hrma.export.cad_visualization import \
            manufacturing_safety_refusals
        md = dict(kalin.get('motor_geometry') or {})
        md.setdefault('motor_name', 'SIVI-CIDAR')
        ret = manufacturing_safety_refusals(json.loads(json.dumps(md)))
        astar = [r for r in ret if r.get('layer') == 'liner']
        nedenler = {r['reason'] for r in astar}
        assert 'outside_model_validity' in nedenler, ret
        t = _katmanlar(kalin)[0]['max_temperature_K']
        assert any(str(t) in (r.get('validity_basis') or '')
                   for r in astar), astar

    def test_ince_astarda_mars_yolu_degismedi(self, ince):
        """Marş koşan yol: kaynak 'solved: RP-1 station march', iki uç
        bandı yok (bit-aynılık ölçümü RAPOR'da)."""
        astar = _katmanlar(ince)[0]
        assert astar['temperature_source'].startswith('solved: RP-1')
        assert 'throat_solution_bounds' not in astar
        assert astar['governing_station']['T_coolant_K'] > 0.0


# ---------------------------------------------------------------------------
# Kalem 1 — çözüm yolu yoksa: tutarsız varsayımda hüküm sayılarıyla geri çekilir
# ---------------------------------------------------------------------------
class TestTutarsizVarsayim:

    def test_sayi_yayimlanmaz_gerekce_sayilariyla(self, etanol):
        astar = _katmanlar(etanol)[0]
        assert astar['verdict'] == 'withheld'
        for alan in ('mean_temperature_K', 'max_temperature_K',
                     'stress_MPa', 'safety_factor'):
            assert astar[alan] is None, alan
        ac = astar['assumption_check']
        assert ac['conduction_drop_K'] > ac['hot_wall_minus_coolant_K']
        assert ac['hot_wall_minus_coolant_K'] == pytest.approx(
            ac['assumed_hot_wall_K'] - ac['coolant_temperature_K'],
            rel=1e-12)
        assert ac['coolant_temperature_K'] == pytest.approx(
            etanol['cooling_system']['coolant_exit_temperature'], rel=1e-12)
        gerekce = astar['withheld_reason']
        assert f"{ac['conduction_drop_K']:.1f} K" in gerekce
        assert f"{ac['hot_wall_minus_coolant_K']:.1f} K" in gerekce
        assert 'ethanol' in gerekce          # eksik girdi ADIYLA
        cs = etanol['structural_analysis']['chamber_structure']
        assert cs['wall_stack_safety_factor'] is None

    def test_kritik_uyari_ve_parametreleri(self, etanol):
        uy = [w for w in _kodlar(etanol, 'critical') if w.get('code')
              == 'warn.liquid.liner_wall_assumption_inconsistent']
        assert len(uy) == 1
        ac = _katmanlar(etanol)[0]['assumption_check']
        p = uy[0]['params']
        assert p['drop_K'] == round(ac['conduction_drop_K'], 1)
        assert p['room_K'] == round(ac['hot_wall_minus_coolant_K'], 1)
        # eski 'fail' uyarısı (uydurma SF ile) artık yok
        assert not [w for w in _kodlar(etanol) if w.get('code')
                    == 'warn.liquid.liner_below_target']


@pytest.mark.parametrize('anahtar', [
    'warn.liquid.liner_wall_assumption_inconsistent',
    'warn.liquid.liner_outside_validity',
    'warn.liquid.closeout_outside_validity'])
def test_yeni_uyarilar_en_tr(anahtar):
    js = (KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js').read_text(
        encoding='utf-8')
    assert js.count("'%s':" % anahtar) == 2
    en, tr = [satir.split("':", 1)[1] for satir in js.splitlines()
              if satir.strip().startswith("'%s':" % anahtar)]
    assert en != tr


# ---------------------------------------------------------------------------
# Kalem 2 (S1) — termal panelin malzemesi = motorun sıcak gaz cidarı
# ---------------------------------------------------------------------------
def _motor_sicak_cidar(tip, b):
    """Motorun KENDİ kaydından sıcak gaz cidarının (malzeme, kalınlık mm)."""
    kok = b.get('motor') or b
    sa = kok.get('structural_analysis') or {}
    if tip == 'liquid':
        cs = sa.get('chamber_structure') or {}
        astar = [k for k in cs.get('wall_layers') or []
                 if k.get('role') == 'liner']
        assert astar, 'rejeneratif örnekte astar katmanı bekleniyor'
        return astar[0]['material_key'], astar[0]['thickness_mm']
    if tip == 'hybrid':
        return ((sa.get('design_parameters') or {}).get('material'),
                ((kok.get('heat_transfer_analysis') or {}).get(
                    'design_parameters') or {}).get('wall_thickness'))
    ca = sa.get('case_analysis') or {}
    return ca.get('case_material'), ca.get('wall_thickness_mm')


@pytest.mark.skipif(__import__('shutil').which('node') is None,
                    reason='node kurulu değil')
@pytest.mark.parametrize('tip', ['liquid', 'hybrid', 'solid'])
def test_termal_panel_malzemesi_motorun_sicak_cidari(client, tip):
    """Örnek × termal panel: panelin gönderdiği malzeme/kalınlık motorun sıcak
    gaz cidarıdır; ucun bastığı ad, kanonik izin ve erime o kaydınkidir.

    Kök (ölçüldü, main 379e35f23, ``olcum/k2_once.json``): örnek sıvıda panel
    ``chamber_structure.material_key`` (= DIŞ KABUK inconel_718) ve YIĞIN
    kalınlığı (5,5 mm) gönderiyordu; uç 977 / 1533 K basıyordu, astar
    CuCrZr (773 / 1349 K) 1,0 mm."""
    from hrma.data.materials_db import get_material_safe, temperature_limits
    from tests.test_example_projects import (ENDPOINTS, HEADERS,
                                             calculate_payload,
                                             load_example_doc)
    from tests.test_panel_units_v2626 import _run_harness
    f = dict(load_example_doc(tip)['inputs']['fields'])
    r = _sessiz(client.post, ENDPOINTS[tip], json=calculate_payload(tip, f),
                headers=HEADERS)
    assert r.status_code == 200
    b = r.get_json()
    oneri = {k: v for k, v in
             _run_harness(b, tip)['panels']['thermal']['suggestions'].items()
             if v is not None}
    anahtar, kalinlik_mm = _motor_sicak_cidar(tip, b)
    rec, kanon = get_material_safe(anahtar)
    assert get_material_safe(oneri['material'])[1] == kanon
    assert oneri['wall_thickness'] == pytest.approx(kalinlik_mm / 1000.0,
                                                    rel=1e-12)
    rt = _sessiz(client.post, '/analyze_thermal_safety', json=oneri,
                 headers=HEADERS)
    assert rt.status_code == 200, rt.get_data(as_text=True)[:300]
    ta = rt.get_json()['thermal_analysis']
    tl = temperature_limits(rec)
    assert ta['material_properties']['name'] == rec['name']
    assert ta['material_properties']['melting_point'] == pytest.approx(
        tl['melting_K'], rel=1e-12)
    assert ta['safety_analysis']['threshold_ladder']['allowable_K'] == \
        pytest.approx(tl['allowable_K'], rel=1e-12)


@pytest.mark.parametrize('anahtar', ['panel.thermal.help.hotWallThickness',
                                     'panel.thermal.help.hotWallMaterial'])
def test_termal_ipuclari_en_tr_ve_alanda(anahtar):
    js = (KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js').read_text(
        encoding='utf-8')
    assert js.count("'%s':" % anahtar) == 2
    panel = (KOK / 'hrma' / 'static' / 'js' / 'panels' /
             'thermal_panel.js').read_text(encoding='utf-8')
    assert "'%s']" % anahtar in panel


# ---------------------------------------------------------------------------
# Kalem 3 (S1) — iki katmanlı cidarın FEA'sı: dış kabuk gövdesi, gerçek hüküm
# ---------------------------------------------------------------------------
def _ornek_sivi(client):
    from tests.test_example_projects import (ENDPOINTS, HEADERS,
                                             calculate_payload,
                                             load_example_doc)
    f = dict(load_example_doc('liquid')['inputs']['fields'])
    r = _sessiz(client.post, ENDPOINTS['liquid'],
                json=calculate_payload('liquid', f), headers=HEADERS)
    assert r.status_code == 200
    return r.get_json()


@pytest.fixture(scope='module')
def ornek_fea(client):
    from hrma.fea import bridge
    m = _ornek_sivi(client)
    return m, _sessiz(bridge.run_structural_from_motor, m)


class TestIkiKatmanFEA:

    def test_ornek_sivi_fea_hukum_verir(self, ornek_fea):
        """Kök (ölçüldü, main 379e35f23, ``olcum/k3_once.json``): örnek
        sıvının FEA hükmü 'iki_katmanli_cidar_tek_govde_modeli' ile geri
        çekiliyordu. Artık dış kabuk gövdesiyle hüküm VERİLİR."""
        _m, fea = ornek_fea
        h = fea['meta']['hukum']
        assert h['verildi'] is True, h['geri_cekme_gerekceleri']
        assert h['geri_cekme_gerekceleri'] == []
        assert h['converged'] is True
        assert (h['kuvvet_dengesi'] or {}).get('holds') is True
        assert fea['load_model']['distribution'] == 'coolant_uniform_closeout'

    def test_kabuk_govdesi_motorun_katman_kaydindan(self, ornek_fea):
        from hrma.fea.bridge import extract_structural_inputs
        m, _fea = ornek_fea
        cs = m['structural_analysis']['chamber_structure']
        astar, kabuk = cs['wall_layers']
        inp = extract_structural_inputs(m)
        ik = inp['two_layer_closeout']
        assert inp['thickness_m'] == pytest.approx(
            kabuk['thickness_mm'] / 1000.0, rel=1e-12)
        assert ik['offset_m'] == pytest.approx(
            (astar['thickness_mm'] + cs['channel_depth_mm']) / 1000.0,
            rel=1e-12)
        assert inp['inner_pressure_pa'] == pytest.approx(
            kabuk['coolant_pressure_bar'] * 1e5, rel=1e-12)
        assert inp['material'].name == kabuk['material_key']
        assert inp['material'].yield_strength == pytest.approx(
            kabuk['yield_at_temperature_MPa'] * 1e6, rel=1e-9)
        assert inp['pressure_load'].yalniz_radyal is True
        # Kabuk iç yüzeyi gaz konturunun dışında, ötelemesi kadar.
        import numpy as np
        r_gaz0 = float(np.asarray(inp['nozzle_points'])[:, 1].max())
        r_kabuk = float(np.asarray(inp['contour'])[:, 1].max())
        assert r_kabuk == pytest.approx(r_gaz0 + ik['offset_m'], rel=1e-3)

    def test_fea_zar_gerilmesi_motorun_kabuk_cemberiyle_tutarli(
            self, ornek_fea):
        """FEA'nın membran gerilmesi (P_m) motorun kabuk çember gerilmesiyle
        aynı büyüklük (ölçüldü 369,35 ⟷ 370,51 MPa); FEA SF'si ASME
        elastik yolunun oranıdır: akma / max(1,5·P_m, P_L+P_b)."""
        m, fea = ornek_fea
        kabuk = m['structural_analysis']['chamber_structure'][
            'wall_layers'][1]
        scl = fea['meta']['hukum']['scl_lineerlestirme']
        assert scl['P_m_maks_pa'] / 1e6 == pytest.approx(
            kabuk['stress_MPa'], rel=0.01)
        akma = kabuk['yield_at_temperature_MPa'] * 1e6
        payda = max(1.5 * scl['P_m_maks_pa'], scl['P_L_Pb_maks_pa'])
        assert fea['meta']['hukum']['min_safety_factor'] == pytest.approx(
            akma / payda, rel=1e-9)

    def test_katman_hukumleri_astar_motordan_kabuk_fea(self, ornek_fea):
        m, fea = ornek_fea
        kh = fea['meta']['hukum']['katman_hukumleri']
        astar, kabuk = kh['layers']
        motor_astar = m['structural_analysis']['chamber_structure'][
            'wall_layers'][0]
        assert astar['role'] == 'liner'
        assert astar['safety_factor'] == motor_astar['safety_factor']
        assert astar['verdict'] == motor_astar['verdict']
        assert kabuk['role'] == 'closeout'
        assert kabuk['safety_factor'] == \
            fea['meta']['hukum']['min_safety_factor']
        assert kh['stack_min_safety_factor'] == min(
            astar['safety_factor'], kabuk['safety_factor'])

    def test_geri_cekilen_motor_hukmu_sayilariyla(self, client, ince):
        """Inconel 1 mm (z5 gövdesi): astarın çözülen sıcak cidarı düşürme
        verisinin üstünde → motor hükmü fiziksel olarak geri çekili; köprü
        de tutar ve HANGİ sıcaklıkta HANGİ sınırın aşıldığını taşır."""
        from hrma.fea import bridge
        fea = _sessiz(bridge.run_structural_from_motor, ince)
        h = fea['meta']['hukum']
        assert 'motor_cidar_hukmu_geri_cekildi' in h['geri_cekme_gerekceleri']
        assert 'iki_katmanli_cidar_tek_govde_modeli' not in \
            h['geri_cekme_gerekceleri']
        olc = h['motor_cidar_kapisi']['gecerlilik_olcumleri']
        motor = ince['structural_analysis']['chamber_structure'][
            'model_validity_evaluations']
        assert olc['liner_hot_wall']['wall_temperature_K'] == \
            motor['liner_hot_wall']['wall_temperature_K']
        assert str(round(olc['liner_hot_wall']['wall_temperature_K'], 1))[:4] \
            in h['motor_cidar_kapisi']['beyan']
        panel = (KOK / 'hrma' / 'static' / 'js' / 'fea_panel.js').read_text(
            encoding='utf-8')
        assert 'gecerlilik_olcumleri' in panel
        assert "'panel.fea.validity.row'" in panel

    def test_tek_katmanli_sivi_eski_yol(self, client):
        """Film soğutmalı (tek katman) sıvıda FEA girdisi DEĞİŞMEDİ."""
        from hrma.fea.bridge import extract_structural_inputs
        b = _sivi(client, cooling_type='film_cooling',
                  film_cooling_percent=5.0)
        inp = extract_structural_inputs(b)
        assert inp['two_layer_closeout'] is None
        assert inp['load_model']['distribution'] == 'isentropic_1d'
        assert inp['pressure_load'].yalniz_radyal is False


@pytest.mark.parametrize('anahtar', [
    'panel.fea.validity.row', 'panel.fea.validity.liner_hot_wall',
    'panel.fea.validity.closeout', 'panel.fea.validity.wall'])
def test_fea_gecerlilik_anahtarlari_en_tr(anahtar):
    js = (KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js').read_text(
        encoding='utf-8')
    assert js.count("'%s':" % anahtar) == 2


def test_yalniz_radyal_yuk_eksenel_bileske_sifir():
    """Yalnız radyal iç basınç: eksenel düğüm kuvvetleri sıfır, radyal
    toplam p·2π·r·L (ince silindir) ve çember gerilmesi p·r/t'ye yakınsar."""
    import numpy as np
    from hrma.fea.mesh_axisym import build_wall_mesh
    from hrma.fea.structural_axisym import (InnerPressureLoad, Material,
                                            solve_pressure)
    r, t, L, p = 0.05, 0.001, 0.2, 5.0e6
    kontur = np.array([[0.0, r], [L, r]])
    mesh = build_wall_mesh(kontur, t, n_axial=64, n_radial=4)
    yuk = InnerPressureLoad(p_ref_pa=p, yalniz_radyal=True)
    res = solve_pressure(mesh, Material(E=200e9, nu=0.3,
                                        yield_strength=500e6), yuk)
    kd = res.meta['kuvvet_dengesi']
    assert kd['ic_basinc_eksenel_n'] == 0.0
    assert abs(kd['mesnet_eksenel_tepkisi_n']) < 1e-6 * p * np.pi * r * r
    assert res.scl_beyani['P_m_maks_pa'] == pytest.approx(
        p * (r + t / 2) / t, rel=0.02)


# ---------------------------------------------------------------------------
# Kalem 4 (S2) — sıvı toplam impuls: motor TEK sayı yayımlar, herkes onu okur
# ---------------------------------------------------------------------------
class TestToplamImpuls:

    def test_motor_yayimlar_ve_tuketiciler_ayni_sayiyi_okur(self, client):
        """Kök (ölçüldü, main 379e35f23, ``olcum/k4_once.json``): üst düzey
        ``total_impulse`` yoktu; sunucu PDF tablosu None ("N/A"), güvenlik
        bölümü ve OpenRocket özeti kendi itki × süresini türetiyordu."""
        from hrma.export.openrocket_integration import OpenRocketExporter
        from hrma.export.pdf_generator import PDFReportGenerator
        from hrma.export.pdf_safety import build_pdf_safety
        m = _ornek_sivi(client)
        assert m['burn_time'] > 0
        ti = m['total_impulse']
        assert ti == m['thrust'] * m['burn_time']
        assert 'thrust x burn_time' in m['total_impulse_basis']
        assert PDFReportGenerator._resolve_performance(
            'total_impulse', {}, m) == ti
        assert OpenRocketExporter.resolve_total_impulse(m) == (
            ti, 'total_impulse')
        guv, kunye = _sessiz(build_pdf_safety, m, dict(m))
        assert kunye['inputs_resolved']['total_impulse'] == \
            'report_performance:total_impulse'
        um = guv['explosive_hazards']['fragment_hazards'][
            'unrestrained_motor']
        assert um['total_impulse_ns'] == ti

    def test_sure_yoksa_yayimlanmaz(self, client):
        from tests.test_example_projects import (ENDPOINTS, HEADERS,
                                                 calculate_payload,
                                                 load_example_doc)
        f = dict(load_example_doc('liquid')['inputs']['fields'])
        f.pop('max_burn_duration', None)
        r = _sessiz(client.post, ENDPOINTS['liquid'],
                    json=calculate_payload('liquid', f), headers=HEADERS)
        assert r.status_code == 200
        m = r.get_json()
        assert m['burn_time_source'] == 'not_supplied'
        assert 'total_impulse' not in m
        assert 'total_impulse_basis' not in m


def test_astar_hedef_altinda_iken_fea_satiri_yigin_sf_gorur(client):
    """CuCrZr 5 mm astar, Pc 50 bar: marş koşar, astar motor hükmü 'fail'
    (SF < 1, geçerlilik içinde). FEA dış kabuğu çözer; köprünün katman
    hükümleri yığının en küçük tasarım SF'sini ASTARDAN verir ve panel satırı
    bu sayıyı görür (yeşil 'converged' basılmaz)."""
    from hrma.fea import bridge
    m = _sivi(client, chamber_material='cucrzr', chamber_wall_thickness=5,
              chamber_pressure=50)
    astar = _katmanlar(m)[0]
    assert astar['verdict'] == 'fail', astar['verdict']
    fea = _sessiz(bridge.run_structural_from_motor, m)
    h = fea['meta']['hukum']
    kh = h['katman_hukumleri']
    if h['verildi']:
        assert kh['stack_governing_layer'] == 'liner'
        assert kh['stack_min_safety_factor'] == astar['safety_factor']
    else:
        assert kh['stack_min_safety_factor'] is None
    panel = (KOK / 'hrma' / 'static' / 'js' / 'fea_panel.js').read_text(
        encoding='utf-8')
    govde = panel[panel.index('function acStructuralVerdict'):]
    govde = govde[:govde.index('const SPEC_STRUCTURAL')]
    assert 'stack_min_safety_factor' in govde
