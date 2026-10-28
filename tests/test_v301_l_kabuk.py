# -*- coding: utf-8 -*-
"""V301 / L-KABUK — sıvı rejeneratif cidar ÇİFT KATMAN (astar + dış kabuk).

Kanıt dizini: docs/scofield/raw/OH/V301/kati-sivi/L-KABUK/ (RAPOR.md,
olcum_once.json ⟷ olcum_sonra.json, ornek_arama.json, ters_mutasyon.json).

Kök (ölçüldü, taban 688bc30b2): rejeneratif yolda sıcak gaz cidarı = yapısal
hazne cidarıydı. Isıl zincir ince cidar (CuCrZr ~1 mm), basınç çemberi kalın
cidar (CuCrZr SF 2,5 ile 8,07 mm) istiyordu; biri ötekini bozuyor, örnek sıvı
motor kritik bayrakla açılıyor ve imalat kapısı STEP/STL/DXF'i reddediyordu.

Bekçiler:
  * iki katman: astar (SP-125 Eş. 4-27 eğilme terimi + Eş. 4-31 ısıl terim)
    ve dış kabuk (çember, dış yarıçap) sayıları yayımlanan girdilerden
    yeniden kurulur; çizilen cidar = yığın;
  * kalem 7: geçerli tasarım noktası kritiksiz + kapı açık + üç dışa aktarım
    200; örnek dosyanın KENDİ girdileriyle aynı iddia (bugün KIRMIZI — bkz.
    ``test_ornek_dosya_girdileriyle_kritik_yok_kapi_acik``);
  * rejeneratif olmayan yollar: iki katman işlevleri patlatılmışken de 200 ve
    blokta yeni alan yok (bit-aynılık bekçisinin ürün yolu karşılığı);
  * RP-1 kok eşiği iki kademe (728 K hüküm / 561 K uyarı);
  * film tipi + %0 film adlı 422; dış kabuk malzemesi kapısı;
  * imalat kapısı katman katman (gevşetme yok); FEA köprüsü motorun geri
    çektiği hükmü ve iki katmanı tanır; Bartz özellik kümesi tek kaynak.
"""
import contextlib
import io
import json
import os
import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
ORNEK_DOSYA = KOK / 'examples' / 'Example Liquid LOX-RP1 25kN.hrma'
H = {'Host': '127.0.0.1:8080'}

#: Kalem 7 — örneğe EN YAKIN geçerli nokta (ornek_arama.json): astar CuCrZr
#: 1,0 mm, dış kabuk HRMA varsayılanı (Inconel 718, HRMA boyutlandırır),
#: O/F 2,0, Pc 50 bar. Bedel: Isp_vak 309,2 → 301,1 s.
GECERLI_NOKTA = {'chamber_material': 'cucrzr', 'chamber_wall_thickness': 1.0,
                 'mixture_ratio': 2.0, 'chamber_pressure': 50,
                 'feed_pressure': 75}


def _ornek_alanlari():
    return dict(json.loads(ORNEK_DOSYA.read_text(encoding='utf-8'))
                ['inputs']['fields'])


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


def _kos(client, ek=None, sil=()):
    yuk = _ornek_alanlari()
    yuk.update(ek or {})
    for k in sil:
        yuk.pop(k, None)
    return _sessiz(client.post, '/calculate_liquid', json=yuk, headers=H)


def _govde(client, ek=None):
    r = _kos(client, ek)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


def _kritik(b):
    return sorted({w.get('code') for w in (b.get('input_warnings') or [])
                   if isinstance(w, dict) and w.get('severity') == 'critical'})


def _md(b):
    md = dict(b.get('motor_geometry') or {})
    md.setdefault('motor_name', 'Example Liquid LOX-RP1 25kN')
    return md


def _kapi(md):
    from hrma.export.cad_visualization import manufacturing_safety_refusals
    return manufacturing_safety_refusals(json.loads(json.dumps(md)))


@pytest.fixture(scope='module')
def gecerli(client):
    return _govde(client, GECERLI_NOKTA)


@pytest.fixture(scope='module')
def ornek(client):
    return _govde(client)


# ---------------------------------------------------------------------------
# Kalem 1 — iki katmanlı cidar: sayılar yayımlanan girdilerden yeniden kurulur
# ---------------------------------------------------------------------------
class TestIkiKatman:

    def test_katmanlar_ve_cizilen_yigin(self, gecerli):
        cs = gecerli['structural_analysis']['chamber_structure']
        assert cs['wall_model'] == 'two_layer_regenerative'
        assert cs['wall_model_basis_key'] == 'liq.wall.model.two_layer_basis'
        astar, kabuk = cs['wall_layers']
        assert astar['role'] == 'liner' and kabuk['role'] == 'closeout'
        assert astar['material_key'] == 'cucrzr'
        assert astar['thickness_mm'] == pytest.approx(1.0, rel=1e-12)
        h = cs['channel_depth_mm']
        assert h == pytest.approx(
            gecerli['cooling_system']['channel_height_mm'], rel=1e-12)
        yigin = astar['thickness_mm'] + h + kabuk['thickness_mm']
        assert cs['wall_stack_thickness_mm'] == pytest.approx(yigin, rel=1e-12)
        # CAD'in çizdiği alan yığındır (tek katı gövde).
        assert cs['wall_thickness'] == pytest.approx(yigin, rel=1e-12)
        assert cs['wall_stack_safety_factor'] == pytest.approx(
            min(astar['safety_factor'], kabuk['safety_factor']), rel=1e-12)
        # Isıl zincirin sıcak cidarı = astar (sığma ölçütü aynı sayıyı okur).
        fit = gecerli['cooling_system']['channel_count_fit']
        assert fit['hot_wall_thickness_mm'] == pytest.approx(1.0, rel=1e-12)

    def test_astar_gerilmesi_formulden(self, gecerli):
        """SP-125 Eş. 4-27 eğilme terimi (6M/t², M = Δp·w²/12) + Eş. 4-31
        ısıl terimi E·α·ΔT/(2(1−ν)); kesme 0,75·Δp·w/t; σ_eş = √(σ²+3τ²)."""
        from hrma.data.materials_db import get_material_safe
        cs = gecerli['structural_analysis']['chamber_structure']
        astar = cs['wall_layers'][0]
        st = astar['governing_station']
        rec, _ = get_material_safe('cucrzr')
        t = astar['thickness_mm'] / 1e3
        w = cs['channel_width_mm'] / 1e3
        dp = st['pressure_difference_bar'] * 1e5
        sig_b = dp * w * w / (2.0 * t * t)
        sig_th = (rec['elastic_modulus'] * rec['thermal_expansion']
                  * (st['T_hot_K'] - st['T_cold_K'])
                  / (2.0 * (1.0 - rec['poisson_ratio'])))
        tau = 0.75 * dp * w / t
        assert st['bending_stress_MPa'] == pytest.approx(sig_b / 1e6, rel=1e-9)
        assert st['thermal_stress_MPa'] == pytest.approx(sig_th / 1e6, rel=1e-9)
        assert st['shear_stress_MPa'] == pytest.approx(tau / 1e6, rel=1e-9)
        sig_eq = ((sig_b + sig_th) ** 2 + 3.0 * tau * tau) ** 0.5
        assert st['stress_MPa'] == pytest.approx(sig_eq / 1e6, rel=1e-9)
        assert st['safety_factor'] == pytest.approx(
            st['yield_at_mean_temperature_MPa'] / st['stress_MPa'], rel=1e-9)
        # Akma astarın ORTALAMA sıcaklığında.
        assert st['mean_temperature_K'] == pytest.approx(
            0.5 * (st['T_hot_K'] + st['T_cold_K']), rel=1e-12)

    def test_dis_kabuk_cember_ve_boyutlandirma(self, gecerli):
        cs = gecerli['structural_analysis']['chamber_structure']
        kabuk = cs['wall_layers'][1]
        p = kabuk['coolant_pressure_bar'] * 1e5
        t = kabuk['thickness_mm'] / 1e3
        r_out = kabuk['outer_radius_mm'] / 1e3
        assert kabuk['stress_MPa'] == pytest.approx(p * r_out / t / 1e6,
                                                    rel=1e-9)
        assert kabuk['safety_factor'] == pytest.approx(
            kabuk['yield_at_temperature_MPa'] / kabuk['stress_MPa'], rel=1e-9)
        # Boyutlandırma: gereksinim ≥ 2 mm tabanı, çizilen = bir üst levha.
        from hrma.engines.liquid_rocket_engine import (
            STANDARD_WALL_THICKNESS_MM, WALL_THICKNESS_MANUFACTURING_MIN_M)
        assert kabuk['required_thickness_mm'] >= (
            WALL_THICKNESS_MANUFACTURING_MIN_M * 1e3 - 1e-12)
        ust = min(s for s in STANDARD_WALL_THICKNESS_MM
                  if s >= kabuk['required_thickness_mm'])
        assert kabuk['thickness_mm'] == pytest.approx(ust, rel=1e-12)
        assert kabuk['thickness_source'].startswith('sized by HRMA')
        # Basınç tek kaynaktan: besleme bütçesinin yakıt zinciri (P_c +
        # total_fuel, ceket dâhil) — hazne basıncının üstünde ve künyeli.
        assert kabuk['coolant_pressure_bar'] > GECERLI_NOKTA['chamber_pressure']
        assert 'pump_discharge_pressure_fuel' in kabuk['coolant_pressure_basis']
        # Kabuğun sıcaklığı = marşın en yüksek soğutucu yığın sıcaklığı.
        sm = gecerli['thermal_protection']['station_march']
        assert kabuk['mean_temperature_K'] == pytest.approx(
            sm['coolant_exit_temperature_K'], rel=1e-9)
        # Basıncı taşıyan üye kabuktur: blok çember sayıları kabuğun.
        assert cs['hoop_safety_factor'] == pytest.approx(
            kabuk['safety_factor'], rel=1e-12)
        assert cs['material_key'] == kabuk['material_key'] == 'inconel_718'


# ---------------------------------------------------------------------------
# Kalem 7 — geçerli örnek tasarım noktası + örnek dosya bekçisi
# ---------------------------------------------------------------------------
class TestGecerliOrnekNoktasi:

    @staticmethod
    def _uc_uclari(client, md):
        # STEP üretimi build123d ister. Ana CI `pytest` işi build123d'yi BİLEREK
        # kurmaz (numpy<2 pini); bu düğüm orada devredilmiş atlama olur ve
        # build123d KURULU `step-export` işinde (tests.yml) sıfır atlama
        # bütçesiyle koşar — tools/atlama_kapisi.py STEP_DEVIR_DESENI.
        pytest.importorskip('build123d')
        out = {}
        for ad, yol in (('step', '/api/export-step'),
                        ('stl', '/api/export-stl-zip'),
                        ('dxf', '/api/export-dxf')):
            r = _sessiz(client.post, yol,
                        json={'motor_data': md, 'motor_type': 'liquid'},
                        headers=H)
            out[ad] = r.status_code
        return out

    def test_gecerli_nokta_kritik_yok_kapi_acik_uc_disa_aktarim(
            self, client, gecerli):
        assert _kritik(gecerli) == []
        md = _md(gecerli)
        assert _kapi(md) == []
        assert self._uc_uclari(client, md) == {'step': 200, 'stl': 200,
                                               'dxf': 200}

    def test_ornek_dosya_girdileriyle_kritik_yok_kapi_acik(self, client):
        """BUGÜN KIRMIZI, ÖRNEK TAZELENİNCE YEŞİL (bilerek).

        Örnek dosya (examples/Example Liquid LOX-RP1 25kN.hrma) bugün astarı
        Inconel 718 ile tanımlıyor: iki katmanlı modelde Inconel astar 1,0
        mm'de 1119 K (izin 977 K) ve ısıl gerilme SF 1,04 < 2,5 — fiziksel
        olarak geçersiz bir rejeneratif tasarım; ayrıca O/F 2,3 / Pc 70 bar'da
        birikim dökülürse CuCrZr de erir (SP-8087 §3.4.1). Örneği ana model
        günün sonunda kalem 7'nin tablosuyla (RAPOR.md §7: astar CuCrZr 1,0
        mm, O/F 2,0, Pc 50 bar, besleme 75 bar; dış kabuk varsayılanı)
        yeniden üretir; bu bekçi o zaman yeşile döner. Dosyadan okur — girdi
        burada yazılmaz.
        """
        b = _govde(client)
        assert _kritik(b) == [], _kritik(b)
        md = _md(b)
        assert _kapi(md) == []
        assert self._uc_uclari(client, md) == {'step': 200, 'stl': 200,
                                               'dxf': 200}


# ---------------------------------------------------------------------------
# Rejeneratif OLMAYAN yollar: iki katman işlevleri hiç çağrılmaz
# ---------------------------------------------------------------------------
class TestTekKatmanBitAyni:

    @pytest.fixture
    def patlat(self, monkeypatch):
        from hrma.engines import liquid_rocket_engine as L

        def _patla(*a, **k):
            raise AssertionError('iki katman işlevi rejeneratif olmayan '
                                 'yolda çağrıldı')
        monkeypatch.setattr(L.LiquidRocketEngine, '_wall_stack_assessment',
                            _patla)
        monkeypatch.setattr(L.LiquidRocketEngine,
                            '_two_layer_structural_design', _patla)

    @pytest.mark.parametrize('ek', [
        {'cooling_type': 'ablative'}, {'cooling_type': 'radiative'},
        {'cooling_type': 'film_cooling', 'film_cooling_percent': 10}])
    def test_sivi_tek_katman(self, client, patlat, ek):
        b = _govde(client, ek)
        cs = b['structural_analysis']['chamber_structure']
        for alan in ('wall_model', 'wall_layers', 'wall_stack_safety_factor',
                     'wall_stack_thickness_mm'):
            assert alan not in cs

    @pytest.mark.parametrize('tip', ['hybrid', 'solid'])
    def test_hibrit_kati_ornek(self, client, patlat, tip):
        from tests.test_example_projects import (ENDPOINTS, HEADERS,
                                                 calculate_payload,
                                                 load_example_doc)
        f = dict(load_example_doc(tip)['inputs']['fields'])
        r = _sessiz(client.post, ENDPOINTS[tip],
                    json=calculate_payload(tip, f), headers=HEADERS)
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Kalem 3 — RP-1 kok eşiği iki kademe
# ---------------------------------------------------------------------------
class TestKokIkiKademe:

    def test_sabitler_ve_kaynak(self):
        from hrma.analysis import regen_cooling as R
        assert R.RP1_COKING_LIMIT_TEMP_K == 728.0
        assert R.RP1_COKING_TEMP_K == 561.0
        assert 'SP-8087' in R.RP1_COKING_BASIS
        assert 'CR-168277' in R.RP1_COKING_BASIS
        assert 'NOT mean' in R.RP1_COKING_BASIS

    def test_561_728_arasi_yalniz_uyari(self, ornek):
        sm = ornek['thermal_protection']['station_march']
        t = sm['peak_coolant_side_wall_temperature_K']
        assert 561.0 < t < 728.0
        assert sm['coking'] is False and sm['coking_risk'] is True
        assert sm['coking_threshold_K'] == 728.0
        assert sm['coking_warning_threshold_K'] == 561.0
        kodlar = {(w['code'], w['severity'])
                  for w in ornek['input_warnings'] if isinstance(w, dict)}
        assert ('warn.liquid.solved_coolant_side_coking', 'warning') in kodlar
        assert not any(c == 'warn.liquid.coolant_wall_above_rp1_limit'
                       for c, _s in kodlar)

    def test_728_ustu_kritik(self, client):
        b = _govde(client, {'chamber_material': 'cucrzr',
                            'chamber_wall_thickness': 1.0,
                            'chamber_pressure': 30, 'feed_pressure': 45})
        sm = b['thermal_protection']['station_march']
        assert sm['peak_coolant_side_wall_temperature_K'] > 728.0
        assert sm['coking'] is True
        assert 'warn.liquid.coolant_wall_above_rp1_limit' in _kritik(b)
        assert any(str(w).startswith('COKING LIMIT:') for w in sm['warnings'])


# ---------------------------------------------------------------------------
# Kalem 4 — Bartz özellik kümesi tek kaynak (toplu zincir = RP-1 marşı)
# ---------------------------------------------------------------------------
def test_bartz_ozellik_kumesi_tek_kaynak(gecerli):
    sm = gecerli['thermal_protection']['station_march']
    gps = sm['gas_property_set']
    assert gps['applied'] is True
    assert gps['cp_chamber_source'] == \
        'CEA equilibrium chamber cp at the solved (Pc, O/F)'
    from hrma.analysis import regen_cooling as R
    yakalanan = []
    asil = R.RegenCooling.solve

    def _yakala(self):
        yakalanan.append(self)
        return asil(self)
    import unittest.mock as um
    with um.patch.object(R.RegenCooling, 'solve', _yakala):
        from hrma.app import app
        with app.test_client() as c:
            yuk = _ornek_alanlari()
            yuk.update(GECERLI_NOKTA)
            _sessiz(c.post, '/calculate_liquid', json=yuk, headers=H)
    assert yakalanan
    md = yakalanan[-1]._md_gas
    assert md['gas_cp'] == pytest.approx(gps['cp_J_kgK'], rel=1e-12)
    assert md['gas_viscosity'] == pytest.approx(gps['mu_Pa_s'], rel=1e-12)
    assert md['prandtl'] == pytest.approx(gps['Pr'], rel=1e-12)


# ---------------------------------------------------------------------------
# Kalem 6 — film tipi + %0 film adlı 422; dış kabuk malzemesi kapısı
# ---------------------------------------------------------------------------
class TestUcKapilari:

    def test_film_tipi_sifir_film_adli_422(self, client):
        r = _kos(client, {'cooling_type': 'film_cooling',
                          'film_cooling_percent': 0})
        assert r.status_code == 422
        g = r.get_json()
        assert g['error'] == 'film_cooling_type_requires_film'
        assert g['message_key'] == 'err.liquid.film_cooling_type_without_film'
        alan = g['invalid_fields'][0]
        assert alan['field'] == 'film_cooling_percent'
        assert alan['label_key'] == 'liq.ui.film_cooling'

    def test_film_alani_gonderilmezse_200(self, client):
        r = _kos(client, {'cooling_type': 'film_cooling'},
                 sil=('film_cooling_percent',))
        assert r.status_code == 200

    def test_kabuk_malzemesi_taninmazsa_422(self, client):
        r = _kos(client, {'closeout_material': 'unobtainium'})
        assert r.status_code == 422
        g = r.get_json()
        from hrma.engines.liquid_rocket_engine import (
            CLOSEOUT_MATERIAL_CHOICES)
        assert g['invalid_fields'][0]['allowed_values'] == list(
            CLOSEOUT_MATERIAL_CHOICES)

    def test_kabuk_secimi_ve_kalinligi_kullanilir(self, client):
        b = _govde(client, dict(GECERLI_NOKTA, closeout_material='steel_304',
                                closeout_thickness=12.0))
        kabuk = b['structural_analysis']['chamber_structure']['wall_layers'][1]
        assert kabuk['material_key'] == 'ss_304'
        assert kabuk['thickness_mm'] == pytest.approx(12.0, rel=1e-12)
        assert kabuk['thickness_source'] == 'user input (closeout_thickness)'
        assert kabuk['material_selection_source'] == \
            'user input (closeout material)'

    def test_kabuk_kalinligi_bant_disi_422(self, client):
        r = _kos(client, {'closeout_thickness': 0.01})
        assert r.status_code == 422
        alanlar = [f.get('field') for f in r.get_json()['invalid_fields']]
        assert 'closeout_thickness' in alanlar


# ---------------------------------------------------------------------------
# Kalem 2 — imalat kapısı katman katman (gevşetme yok)
# ---------------------------------------------------------------------------
class TestKapiKatmanlari:

    def test_astar_sf_birin_alti_adli_ret(self, gecerli):
        md = json.loads(json.dumps(_md(gecerli)))
        md['structural_analysis']['chamber_structure']['wall_layers'][0][
            'safety_factor'] = 0.5
        ret = _kapi(md)
        assert any(r['part'] == 'chamber_liner' and r['reason'] ==
                   'sf_below_one' and r['layer'] == 'liner' for r in ret)
        assert all(r['part'] != 'chamber_closeout' for r in ret)

    def test_kabuk_gecerlilik_disi_adli_ret(self, gecerli):
        md = json.loads(json.dumps(_md(gecerli)))
        kat = md['structural_analysis']['chamber_structure']['wall_layers'][1]
        kat['model_validity'] = {'model_validity_limit_exceeded': True}
        ret = _kapi(md)
        assert any(r['part'] == 'chamber_closeout'
                   and r['reason'] == 'outside_model_validity' for r in ret)

    def test_katman_sf_yoksa_ret(self, gecerli):
        md = json.loads(json.dumps(_md(gecerli)))
        md['structural_analysis']['chamber_structure']['wall_layers'][1][
            'safety_factor'] = None
        ret = _kapi(md)
        assert any(r['part'] == 'chamber_closeout'
                   and r['reason'] == 'sf_missing' for r in ret)

    def test_cizim_kunyesi_yigini_soyler(self, gecerli):
        from hrma.export.cad_visualization import _chamber_wall_design
        d = _chamber_wall_design(_md(gecerli))
        assert d['two_layer_wall']['note_key'] == 'out.cad.twoLayerWall.note'
        # V301 CAD-2 kalem 8: katmanlar artık İKİ katı gövde; kanallar
        # kesilmez ve bu beyan edilir (eski metin "ONE solid ... channels are
        # not drawn" idi).
        assert 'TWO solids' in d['source'] and 'NOT cut' in d['source']
        assert d['two_layer_wall']['channels_drawn'] is False
        assert d['two_layer_wall']['layers_drawn_as'] == 'two_solids'


# ---------------------------------------------------------------------------
# Kalem 5 — FEA köprüsü: motorun geri çektiği hüküm + iki katman
# ---------------------------------------------------------------------------
class TestFeaKoprusu:

    def test_geri_cekilen_motor_hukmu_kopruyu_de_tutar(self):
        from hrma.fea.bridge import _sivi_motor_cidar_kapisi
        k = _sivi_motor_cidar_kapisi({'structural_analysis': {
            'chamber_structure': {'verdict_withheld': True}}}, 'liquid')
        assert k['gerekceler'] == ['motor_cidar_hukmu_geri_cekildi']

    def test_iki_katmanli_cidarda_katmanlar_kendi_sicakliginda(self, gecerli):
        """V3.0.5 SIVI-CIDAR kalem 3 — BEKLENTİ DEĞİŞTİ: köprü iki
        katmanlı cidarda artık yığını tek homojen gövde olarak ağlamıyor;
        FEA gövdesi DIŞ KABUKTUR (kendi malzemesi, sıcaklığı, soğutucu
        basıncı), astar hükmü motordan. 'iki_katmanli_cidar_tek_govde_
        modeli' gerekçesi bu yüzden KALKTI; geçerli noktada (CuCrZr 1 mm,
        astar 'pass') kapı hükmü tutmaz. Ölçüm: docs/scofield/raw/OH/V301/
        sivi-cidar/olcum/k3_once.json ⟷ k3_sonra.json (örnek sıvı FEA
        verildi False → True, min SF 1,925 = akma / (1,5·P_m), P_m 369,4 MPa
        ⟷ motorun kabuk çemberi 370,5 MPa)."""
        from hrma.fea.bridge import _sivi_motor_cidar_kapisi
        k = _sivi_motor_cidar_kapisi(gecerli, 'liquid')
        assert 'iki_katmanli_cidar_tek_govde_modeli' not in k['gerekceler']
        assert k['gerekceler'] == []
        kat = gecerli['structural_analysis']['chamber_structure'][
            'wall_layers']
        assert [x['temperature_K'] for x in k['katman_akmalari']] == [
            kat[0]['mean_temperature_K'], kat[1]['mean_temperature_K']]

    def test_tek_katman_ve_diger_motorlar_etkilenmez(self):
        from hrma.fea.bridge import _sivi_motor_cidar_kapisi
        assert _sivi_motor_cidar_kapisi({}, 'hybrid')['gerekceler'] == []
        assert _sivi_motor_cidar_kapisi(
            {'structural_analysis': {'chamber_structure': {}}},
            'liquid')['gerekceler'] == []

    def test_panel_kopru_hukmunu_verildi_ile_okur(self):
        js = (KOK / 'hrma' / 'static' / 'js' / 'fea_panel.js').read_text(
            encoding='utf-8')
        govde = js[js.index('function acStructuralVerdict'):]
        govde = govde[:govde.index('const SPEC_STRUCTURAL')]
        assert 'hk.verildi === false' in govde
        assert 'panel.fea.verdictWithheld' in govde


# ---------------------------------------------------------------------------
# Arayüz + i18n: girdiler, ipuçları, seçenek listesi tek kaynak
# ---------------------------------------------------------------------------
class TestArayuz:

    def test_kabuk_secenekleri_motorla_ayni(self):
        from hrma.engines.liquid_rocket_engine import (
            CLOSEOUT_MATERIAL_CHOICES)
        html = (KOK / 'hrma' / 'templates' / 'liquid.html').read_text(
            encoding='utf-8')
        sec = html[html.index('<select id="closeout_material">'):]
        sec = sec[:sec.index('</select>')]
        degerler = [v for v in re.findall(r'value="([^"]*)"', sec) if v]
        assert degerler == list(CLOSEOUT_MATERIAL_CHOICES)

    @pytest.mark.parametrize('anahtar', [
        'liq.ui.closeout_material', 'liq.ui.closeout_material_tip',
        'liq.ui.closeout_thickness', 'liq.ui.closeout_thickness_tip',
        'liq.ui.closeout_material_default', 'liq.js.layer_liner',
        'liq.js.layer_closeout', 'liq.js.wall_stack'])
    def test_form_anahtarlari_en_tr(self, anahtar):
        js = (KOK / 'hrma' / 'static' / 'js' / 'i18n_pages.js').read_text(
            encoding='utf-8')
        assert js.count("'%s':" % anahtar) == 2

    @pytest.mark.parametrize('anahtar', [
        'warn.liquid.coolant_wall_above_rp1_limit',
        'warn.liquid.liner_below_target', 'warn.liquid.closeout_below_target',
        'warn.liquid.closeout_cannot_be_sized',
        'err.liquid.film_cooling_type_without_film',
        'err.liquid.unsupported_closeout_material',
        'out.export.sfGate.part.chamber_liner',
        'out.export.sfGate.part.chamber_closeout',
        'out.cad.twoLayerWall.note', 'liq.wall.model.two_layer_basis',
        'panel.fea.verdictWithheld',
        'panel.fea.withheld.motor_cidar_hukmu_geri_cekildi',
        # V3.0.5 SIVI-CIDAR kalem 3: 'panel.fea.withheld.iki_katmanli_
        # cidar_tek_govde_modeli' kaldırıldı (köprü o gerekçeyi artık
        # üretmiyor; ölü anahtar bekçisi test_i18n_common).
        'panel.regen.cokingRisk'])
    def test_ortak_anahtarlar_en_tr(self, anahtar):
        js = (KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js').read_text(
            encoding='utf-8')
        assert js.count("'%s':" % anahtar) == 2

    def test_sogutma_paneli_rp1_giris_basincini_tohumlar(self, gecerli):
        sm = gecerli['thermal_protection']['station_march']
        from hrma.engines.liquid_rocket_engine import (
            RP1_MARCH_INLET_MARGIN_BAR)
        assert sm['coolant_inlet_pressure_bar'] == pytest.approx(
            GECERLI_NOKTA['chamber_pressure'] + RP1_MARCH_INLET_MARGIN_BAR,
            rel=1e-12)
        js = (KOK / 'hrma' / 'static' / 'js' / 'panels' /
              'cooling_panel.js').read_text(encoding='utf-8')
        assert 'smr.coolant_inlet_pressure_bar' in js
