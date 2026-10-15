# -*- coding: utf-8 -*-
"""ÖH Dalga-26 — katı kulvarı, aşama 2 bekçileri.

Kapsanan kalemler (ölçüm:
``docs/scofield/raw/OH/D26/kati/a2/{once_taban,once,sonra}.json``):

* **P2B1-03** (bekçi-kırmızı, borç imi kalktı) — CAD lüle panelinin
  yayımladığı boğaz erozyonu tahmini çözücünün fiilen koştuğu katsayıyı
  izlemiyordu.
* **P2B3-03** (bekçi-kırmızı, borç imi kalktı) — aynı tahmin ve lüle
  malzemesi alanı kullanıcının malzeme seçiminden bağımsızdı.
* **OH-D25-07** — çıkış konisinin motor gövde zarfını aşması hiçbir yerde
  bildirilmiyordu (kapı MUTLAK 1000 mm idi).
* **OH-D25-08** — ``core_diameter`` için iki çelişen kabul kümesi
  (kurucu ⟷ ``/calculate_solid`` ucu).
* **OH-D25-10** — ``throat_exceeds_case`` üç kapısı iki ayrı boğaz sayısı
  okuyordu (sessiz 1-500 mm kelepçesi).
* **OH-D25-03** — ``chamber_diameter`` adı yanıtta üç yaprakta üç büyüklük.

Bekçilerin altın değerleri üründen İTHAL EDİLMEZ: kural bağımsız hesaplanır
ya da iki katmanın birbirine eşitliği çakılır.
"""
import contextlib
import io
import json
import re
from pathlib import Path

import pytest

from hrma.engines.solid_rocket_engine import (
    SOLID_EXIT_DIAMETER_ABSOLUTE_LIMIT_M,
    SolidRocketEngine,
    _core_diameter_domain,
    _throat_erosion_pc_ref_bar,
)
from tests.support.kanit import kanit_gerekli

KOK = Path(__file__).resolve().parents[1]
MOTOR_KAYNAK = KOK / 'hrma' / 'engines' / 'solid_rocket_engine.py'
APP_KAYNAK = KOK / 'hrma' / 'app.py'
I18N_COMMON = KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js'


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


def _motor(**ov):
    kur = {'chamber_pressure': 40}
    for ad in ('grain_type', 'propellant_type', 'chamber_diameter',
               'grain_length', 'core_diameter', 'chamber_pressure'):
        if ad in ov:
            kur[ad] = ov.pop(ad)
    return SolidRocketEngine(overrides=(ov or None), **kur)


def _tahmin(**ov):
    eng = _motor(**ov)
    perf = _sessiz(eng._design_nozzle_geometry)
    return eng, perf


@pytest.fixture(scope='module')
def istemci():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _post(istemci, govde):
    r = _sessiz(istemci.post, '/calculate_solid', json=govde)
    return r.status_code, (r.get_json() or {})


_KATI_TABAN = {
    'motor_type': 'solid', 'engine_type': 'solid',
    'chamber_pressure': 40, 'burn_time': 3,
    'propellant_type': 'APCP',
    'chamber_diameter': 100, 'core_diameter': 30,
    'grain_length': 500, 'chamber_length': 500,
    'grain_type': 'bates',
}


# ---------------------------------------------------------------------------
# P2B1-03 — tahmin ÇÖZÜCÜNÜN katsayısını izler
# ---------------------------------------------------------------------------
class TestP2B103TahminCozucuyuIzler:

    @pytest.mark.parametrize('a_ref', (0.001, 0.05, 0.15, 0.3))
    def test_yayimlanan_hiz_cozucunun_modelinden_ayrilmaz(self, a_ref):
        """Yayımlanan tahmin = çözücünün TAKTIĞI modelin aynı basınçtaki hızı.

        İki sayı da aynı nesneden okunur; altın sabit yoktur, iki katmanın
        AYRILAMAZLIĞI çakılır.
        """
        eng, perf = _tahmin(erosion_factor=a_ref)
        est = perf['performance']['erosion_estimate']
        model = eng._throat_erosion_model()
        assert model is not None and model.a_ref_mm_s == pytest.approx(a_ref)
        assert est['status'] == 'computed'
        assert est['coefficient_source'] == 'user_supplied'
        assert est['rate_mm_s'] == pytest.approx(
            model.rate_mm_s(est['chamber_pressure_bar']), abs=1e-4), (
            f'çözücü a_ref={a_ref} ile koşuyor, tasarım bloğu '
            f"{est['rate_mm_s']} mm/s yayımlıyor")

    def test_katsayi_degisince_yayimlanan_sayi_da_degisir(self):
        """ÖLÇÜLEN KUSUR: 4 durumda 1 ayırt edici hız (ölü alan)."""
        hizlar = []
        for ov in ({}, {'erosion_factor': 0.001},
                   {'erosion_factor': 0.05}, {'erosion_factor': 0.15}):
            _, perf = _tahmin(**dict(ov))
            hizlar.append(perf['performance']['erosion_estimate']['rate_mm_s'])
        assert len(set(hizlar)) == len(hizlar), (
            f'katsayı ekseninde tahmin hâlâ atıl: {hizlar}')

    def test_metin_alani_da_ayni_sayidan_turer(self):
        """``erosion_rate`` metni ile ``erosion_estimate`` ayrışamaz."""
        _, perf = _tahmin(erosion_factor=0.05)
        p = perf['performance']
        est = p['erosion_estimate']
        assert p['erosion_rate'] == f"{est['rate_mm_s']:.3f} mm/s"
        assert p['erosion_rate_status'] == est['status']

    def test_katsayi_yokken_kaynak_malzeme_kaydidir(self):
        _, perf = _tahmin()
        est = perf['performance']['erosion_estimate']
        assert est['coefficient_source'] == 'material_record'
        assert est['status'] == 'computed'


# ---------------------------------------------------------------------------
# P2B3-03 — tahmin ve CAD lüle paneli KULLANICININ malzemesini izler
# ---------------------------------------------------------------------------
class TestP2B303TahminMalzemeyiIzler:

    @pytest.mark.parametrize('secim,beklenen', [
        ('graphite', 'graphite'),
        ('carbon_carbon', 'carbon_carbon'),
        ('C-C', 'carbon_carbon'),
    ])
    def test_bandi_olan_malzemede_kardes_blokla_ayni(self, secim, beklenen):
        eng, perf = _tahmin(nozzle_material=secim)
        est = perf['performance']['erosion_estimate']
        kardes = eng._nozzle_erosion_reference()
        assert kardes is not None and kardes.material == beklenen
        assert est['material'] == kardes.material, (
            f"kullanıcı '{kardes.material}' seçti, blok "
            f"'{est['material']}' yayımlıyor")
        assert est['rate_mm_s'] == pytest.approx(
            kardes.rate_mm_s(est['chamber_pressure_bar']), abs=1e-4)

    @pytest.mark.parametrize('secim', ('steel', 'tungsten', 'phenolic'))
    def test_bandi_olmayan_malzemede_sayi_yayimlanmaz(self, secim):
        """Fail-closed (Doktrin 1): grafit katsayısı İKAME EDİLMEZ."""
        eng, perf = _tahmin(nozzle_material=secim)
        p = perf['performance']
        est = p['erosion_estimate']
        assert eng._nozzle_erosion_reference() is None
        assert est['status'] == 'not_evaluated'
        assert est['rate_mm_s'] is None and est['band_mm_s'] is None
        assert p['erosion_rate'] is None
        assert est['material'] == secim
        assert est['reason'] and 'graphite' in est['reason'].lower()
        # Aynı yanıttaki kardeş beyanla çelişmemeli.
        assert _sessiz(eng.analyze_nozzle_material)['erosion'] == \
            'no published data'

    def test_kunye_referans_basincini_ikinci_kez_yazmaz(self):
        """``input_field`` metnindeki basınç modelin kendi varsayılanıdır."""
        _, perf = _tahmin(nozzle_material='tungsten')
        est = perf['performance']['erosion_estimate']
        assert ('%g bar' % _throat_erosion_pc_ref_bar()) in est['input_field']

    @pytest.mark.parametrize('secim', ('graphite', 'carbon_carbon', 'steel',
                                       'tungsten', 'phenolic'))
    def test_cad_lule_malzemesi_secimi_izler(self, secim):
        eng, perf = _tahmin(nozzle_material=secim)
        assert perf['material_key'] == eng._nozzle_material_key()
        assert perf['material_key'] == secim
        assert perf['material'], 'lüle malzemesi adı boş yayımlanamaz'

    def test_cad_lule_malzemesi_artik_sabit_degil(self):
        """ÖLÇÜLEN KUSUR: 6 seçimde 1 ayırt edici CAD malzeme adı."""
        adlar = []
        for secim in ('graphite', 'carbon_carbon', 'steel', 'tungsten',
                      'phenolic'):
            _, perf = _tahmin(nozzle_material=secim)
            adlar.append(perf['material'])
        assert len(set(adlar)) == len(adlar), (
            f'CAD lüle paneli hâlâ tek ad basıyor: {adlar}')

    def test_kaynakta_kosulsuz_grafit_kalmadi(self):
        """``for_material('graphite')`` artık KOD olarak kurulmuyor (AST).

        Metin taraması yerine AST: yorum ve belge metinleri sayılmaz, geri
        dönen tek satırlık bir çağrı ise sayılır.
        """
        import ast
        agac = ast.parse(MOTOR_KAYNAK.read_text(encoding='utf-8'))
        cagrilar = [
            d for d in ast.walk(agac)
            if isinstance(d, ast.Call)
            and isinstance(d.func, ast.Attribute)
            and d.func.attr == 'for_material'
            and d.args and isinstance(d.args[0], ast.Constant)
            and d.args[0].value == 'graphite']
        assert not cagrilar, (
            'lüle erozyonu yine koşulsuz grafitten kuruluyor '
            f'(satır: {[c.lineno for c in cagrilar]})')


# ---------------------------------------------------------------------------
# OH-D25-07 — çıkış konisi gövde zarfını aşınca BİLDİRİLİR
# ---------------------------------------------------------------------------
def _uyari_kodlari(eng):
    res = _sessiz(eng.calculate_performance)
    return sorted({w.get('code') for w in (res.get('warnings') or [])
                   if isinstance(w, dict)})


class TestOHD2507ZarfKapisi:

    @pytest.mark.parametrize('ov', [
        {'chamber_diameter': 100, 'grain_length': 500, 'core_diameter': 30,
         'chamber_pressure': 40, 'test_altitude': 25000},
        {'chamber_diameter': 80, 'grain_length': 900, 'core_diameter': 20,
         'chamber_pressure': 60, 'test_altitude': 20000},
        # ÖH KİTAP p1b (B11, §28-36 Ş-3) — KURULUŞ YENİDEN SEÇİLDİ (ov2):
        # eski irtifa 30 km idi. APCP kaydı CEA denge dörtlüsüne geçince
        # (denge γ_s 1,1338) optimum ε büyüdü ve bu gövdede çıkış çapı
        # 0,956 → 1,105 m oldu: MUTLAK kapı (1,0 m) da ateşleniyor, testin
        # önkoşulu ("yalnız GÖRELİ kapının yakaladığı kusur") bozuldu.
        # Niyet (büyük gövdeli, yüksek irtifa motorunda zarfı aşan ama mutlak
        # eşiğin altında kalan lüle) 27 km ile korunur: çıkış 0,912 m (eski
        # dörtlüyle 0,796 m); 1,0 m'ye %8,8 pay.
        {'chamber_diameter': 150, 'grain_length': 1500, 'core_diameter': 40,
         'chamber_pressure': 50, 'test_altitude': 27000},
    ])
    def test_zarfi_asan_lule_sessiz_kalmaz(self, ov):
        eng = _motor(**dict(ov))
        d_exit = float(eng._design_exit_diameter())
        # Kuralın kendisi bağımsız kurulur: çıkış > gövde ise uyarı olmalı.
        assert d_exit > float(eng.D_chamber), 'gövde seçimi kusuru göstermiyor'
        # ... ve MUTLAK kapı bu gövdelerde ateşlenmiyor (kusurun sebebi).
        assert d_exit <= SOLID_EXIT_DIAMETER_ABSOLUTE_LIMIT_M
        assert 'warn.solid.exit_cone_exceeds_case' in _uyari_kodlari(eng)

    def test_zarfin_icinde_kalan_lulede_uyari_yok(self):
        eng = _motor(chamber_diameter=100, grain_length=500,
                     core_diameter=30, chamber_pressure=40)
        assert float(eng._design_exit_diameter()) < float(eng.D_chamber)
        assert 'warn.solid.exit_cone_exceeds_case' not in _uyari_kodlari(eng)

    def test_uyari_iki_capi_ve_orani_tasir(self):
        eng = _motor(chamber_diameter=100, grain_length=500,
                     core_diameter=30, chamber_pressure=40,
                     test_altitude=25000)
        res = _sessiz(eng.calculate_performance)
        kayit = [w for w in res['warnings']
                 if w.get('code') == 'warn.solid.exit_cone_exceeds_case']
        assert len(kayit) == 1
        par = kayit[0]['params']
        d_exit_mm = float(eng._design_exit_diameter()) * 1000.0
        d_case_mm = float(eng.D_chamber) * 1000.0
        assert par['exit_diameter_mm'] == pytest.approx(d_exit_mm, abs=0.05)
        assert par['case_diameter_mm'] == pytest.approx(d_case_mm, abs=0.05)
        assert par['ratio'] == pytest.approx(d_exit_mm / d_case_mm, abs=0.005)
        assert par['ratio'] > 1.0

    def test_mutlak_esik_adlandirildi_ve_ikinci_kez_yazilmadi(self):
        kaynak = MOTOR_KAYNAK.read_text(encoding='utf-8')
        assert 'if d_exit > 1.0' not in kaynak, (
            'mutlak çıkış çapı eşiği yine çıplak sayı olarak yazılmış')
        assert SOLID_EXIT_DIAMETER_ABSOLUTE_LIMIT_M == 1.0

    @pytest.mark.parametrize('dil_bloku', (0, 1))
    def test_i18n_karsiligi_iki_dilde_de_var(self, dil_bloku):
        metin = I18N_COMMON.read_text(encoding='utf-8')
        gecisler = [m.start() for m in re.finditer(
            re.escape("'warn.solid.exit_cone_exceeds_case'"), metin)]
        assert len(gecisler) >= 2, (
            'yeni uyarı kodunun EN ve TR karşılığı yok: %s' % gecisler)
        # Aynı dil bloğundaki kardeşiyle yan yana durmalı (dosya sonuna
        # eklenmiş kaçak anahtar değil).
        kardes = [m.start() for m in re.finditer(
            re.escape("'warn.solid.exit_diameter_large'"), metin)]
        assert abs(gecisler[dil_bloku] - kardes[dil_bloku]) < 1200


# ---------------------------------------------------------------------------
# OH-D25-08 — TEK kabul kümesi
# ---------------------------------------------------------------------------
class TestOHD2508TekKabulKumesi:

    @pytest.mark.parametrize('core', (0, 2, 5, 30, 95, 100))
    def test_end_burnerda_uc_ile_kurucu_ayni_karari_verir(self, istemci,
                                                          core):
        """Kanonik küme uç-yanmalıda port kısıtı OLMADIĞINI söyler."""
        try:
            _motor(grain_type='end_burner', core_diameter=core,
                   chamber_diameter=100, grain_length=500)
            kurucu_kabul = True
        except Exception:
            kurucu_kabul = False
        govde = dict(_KATI_TABAN)
        govde.update({'grain_type': 'end_burner', 'core_diameter': core})
        kod, _ = _post(istemci, govde)
        assert (kod != 400) == kurucu_kabul, (
            f'core={core}: kurucu {kurucu_kabul}, uç HTTP {kod}')

    @pytest.mark.parametrize('core,beklenen', [(2, 400), (100, 400),
                                               (30, None), (95, None)])
    def test_radyal_grainde_band_degismedi(self, istemci, core, beklenen):
        """İmalat payı korunur: radyal tiplerde davranış BİT-AYNI."""
        govde = dict(_KATI_TABAN)
        govde.update({'grain_type': 'bates', 'core_diameter': core})
        kod, _ = _post(istemci, govde)
        if beklenen is None:
            assert kod != 400
        else:
            assert kod == beklenen

    def test_ret_kunyesi_kanonik_kumeyi_tasir(self, istemci):
        govde = dict(_KATI_TABAN)
        govde.update({'grain_type': 'bates', 'core_diameter': 2})
        kod, js = _post(istemci, govde)
        assert kod == 400 and js.get('error_type') == 'BandIhlali'
        alan = js['invalid_fields'][0]
        assert alan['field'] == 'core_diameter'
        assert alan['reason'] == 'out_of_accepted_range'
        assert alan['grain_type'] == 'bates'
        kanonik = _core_diameter_domain('bates', 100.0)
        assert alan['canonical_range'] == kanonik['accepted_range']
        assert alan['canonical_range_text'] == kanonik['accepted_range_text']
        # Uç bandı kanonik kümenin İÇİNDE kalmalı (pay ekler, genişletmez).
        assert alan['accepted_range'][0] >= kanonik['accepted_range'][0]
        assert alan['accepted_range'][1] <= kanonik['accepted_range'][1]

    def test_uc_bandi_kanonik_kumeden_turetilir(self):
        """Band uçta ELLE yazılmaz — türetme fonksiyonundan gelir."""
        import hrma.app as appmod
        for tip, D in (('bates', 100.0), ('end_burner', 100.0),
                       ('star', 250.0)):
            kanonik = _core_diameter_domain(tip, D)
            alt, ust = appmod._core_diameter_uc_bandi(kanonik, D)
            if tip == 'end_burner':
                assert (alt, ust) == (0.0, None)
            else:
                pay = float(appmod.SOLID_CORE_WALL_MARGIN_MM)
                assert alt == pytest.approx(kanonik['accepted_range'][0] + pay)
                assert ust == pytest.approx(kanonik['accepted_range'][1] - pay)

    def test_uc_katmaninda_elle_yazilmis_band_kalmadi(self):
        kaynak = APP_KAYNAK.read_text(encoding='utf-8')
        assert 'validate_input_range(core_diameter, 5, chamber_diameter-5' \
            not in kaynak, ('uç katmanı yine kendi bandını yazıyor '
                            '(kanonik kümeden türetilmiyor)')


# ---------------------------------------------------------------------------
# OH-D25-10 — TEK boğaz kaynağı, üç kapı
# ---------------------------------------------------------------------------
_KAPI_GOVDELERI = (
    {'chamber_diameter': 100, 'grain_length': 500, 'core_diameter': 30,
     'chamber_pressure': 40},
    {'chamber_diameter': 100, 'grain_length': 3000, 'core_diameter': 15,
     'chamber_pressure': 10},
    {'chamber_diameter': 900, 'grain_length': 6000, 'core_diameter': 60,
     'chamber_pressure': 5},
    {'chamber_diameter': 700, 'grain_length': 5000, 'core_diameter': 40,
     'chamber_pressure': 5},
)


class TestOHD2510TekBogazKaynagi:

    @pytest.mark.parametrize('ov', _KAPI_GOVDELERI)
    def test_uc_kapi_ayni_hukmu_verir(self, ov):
        eng = _motor(**dict(ov))
        res = _sessiz(eng.calculate_performance)
        kodlar = sorted({w.get('code') for w in (res.get('warnings') or [])
                         if isinstance(w, dict)})
        kapilar = {
            'uyari': 'warn.solid.throat_exceeds_case' in kodlar,
            'cad': bool(res['cad_design']['nozzle_design']
                        ['throat_exceeds_case']),
            'performans': bool(res['nozzle_angles']['throat_exceeds_case']),
        }
        assert len(set(kapilar.values())) == 1, (
            f'kapılar ayrıştı: {kapilar}')
        # Hüküm bağımsız olarak da doğrulanır.
        beklenen = (float(eng._estimate_throat_diameter())
                    >= float(eng.D_chamber))
        assert set(kapilar.values()) == {beklenen}

    @pytest.mark.parametrize('ov', _KAPI_GOVDELERI)
    def test_yayimlanan_bogaz_capi_tek_sayidir(self, ov):
        eng = _motor(**dict(ov))
        res = _sessiz(eng.calculate_performance)
        cad = res['cad_design']['nozzle_design']['throat_diameter']
        perf = res['nozzle_angles']['throat_diameter_mm']
        assert cad == pytest.approx(perf, rel=1e-9), (
            f'CAD {cad} mm ⟷ performans {perf} mm')

    def test_sessiz_kelepce_kalkti(self):
        """500 mm'yi aşan boğaz artık 500'e indirilmiyor (fail-open kapandı).

        Kelepçenin varlığı bağımsız ölçülür: ham geometrik çap
        ``_design_throat_area``dan kurulur ve yayımlanan sayıyla
        karşılaştırılır.
        """
        import numpy as np
        eng = _motor(chamber_diameter=700, grain_length=5000,
                     core_diameter=40, chamber_pressure=5)
        A_t, _ = eng._design_throat_area()
        cd = getattr(eng, 'discharge_coeff', 1.0)
        A_geom = A_t / cd if 0.0 < cd < 1.0 else A_t
        ham = 2.0 * float(np.sqrt(A_geom / np.pi))
        assert ham > 0.5, 'gövde seçimi kelepçe bölgesine düşmüyor'
        assert float(eng._estimate_throat_diameter()) == pytest.approx(
            ham, rel=1e-12)
        # ... ve bu gövdede boğaz gerçekten gövdeden büyük olmadığı hâlde
        # eski kelepçe kapıyı yanlış yönde çeviriyordu; kural şimdi doğru.
        assert eng._throat_exceeds_case(ham) is (ham >= float(eng.D_chamber))

    def test_kelepce_kaynaktan_kaldirildi(self):
        """``_estimate_throat_diameter`` gövdesinde min/max kelepçesi yok (AST)."""
        import ast
        agac = ast.parse(MOTOR_KAYNAK.read_text(encoding='utf-8'))
        govde = [d for d in ast.walk(agac)
                 if isinstance(d, ast.FunctionDef)
                 and d.name == '_estimate_throat_diameter']
        assert len(govde) == 1
        kelepce = [d for d in ast.walk(govde[0])
                   if isinstance(d, ast.Call)
                   and isinstance(d.func, ast.Name)
                   and d.func.id in ('min', 'max')]
        assert not kelepce, (
            'sessiz boğaz kelepçesi geri kondu '
            f'(satır: {[c.lineno for c in kelepce]})')

    def test_olcut_tek_yerde_tanimli(self):
        """``d >= D_chamber`` karşılaştırması üç yerde ayrı yazılmaz (AST)."""
        import ast
        kaynak = MOTOR_KAYNAK.read_text(encoding='utf-8')
        agac = ast.parse(kaynak)
        tanim = [d for d in ast.walk(agac)
                 if isinstance(d, ast.FunctionDef)
                 and d.name == '_throat_exceeds_case']
        assert len(tanim) == 1, 'ölçütün tek tanım noktası yok'
        kopya = []
        for d in ast.walk(agac):
            if not (isinstance(d, ast.Compare) and d.ops
                    and isinstance(d.ops[0], ast.GtE)):
                continue
            sag = d.comparators[0]
            if (isinstance(sag, ast.Attribute) and sag.attr == 'D_chamber'
                    and tanim[0].lineno <= d.lineno <= tanim[0].end_lineno):
                continue          # tanımın kendisi
            if isinstance(sag, ast.Attribute) and sag.attr == 'D_chamber':
                kopya.append(d.lineno)
        assert not kopya, f'kapı ölçütü yine kopyalanmış (satır {kopya})'


# ---------------------------------------------------------------------------
# OH-D25-03 — kanonik ad + künye
# ---------------------------------------------------------------------------
def _yapraklar(o, ad, yol=''):
    bulunan = []
    if isinstance(o, dict):
        for k, v in o.items():
            alt = f'{yol}.{k}' if yol else k
            if k == ad and not isinstance(v, (dict, list)):
                bulunan.append((alt, v))
            bulunan.extend(_yapraklar(v, ad, alt))
    elif isinstance(o, list):
        for i, v in enumerate(o[:3]):
            bulunan.extend(_yapraklar(v, ad, f'{yol}[{i}]'))
    return bulunan


class TestOHD2503KanonikAd:

    @pytest.fixture(scope='class')
    def yanit(self, istemci):
        govde = dict(_KATI_TABAN)
        govde['insulation_thickness'] = 3
        kod, js = _post(istemci, govde)
        assert kod == 200
        return js

    def test_akustik_yaprak_kendi_adini_tasir(self, yanit):
        girdiler = yanit['acoustic_modes']['inputs']
        assert 'chamber_diameter' not in girdiler
        assert girdiler['equivalent_cavity_diameter_m'] == pytest.approx(
            yanit['acoustic_modes']['equivalent_cavity']['diameter_m'],
            rel=1e-12)
        assert girdiler['equivalent_cavity_diameter_basis']

    def test_ayni_ad_daha_az_yaprakta(self, yanit):
        yap = _yapraklar(yanit, 'chamber_diameter')
        yollar = sorted(y for y, _ in yap)
        assert 'acoustic_modes.inputs.chamber_diameter' not in yollar
        assert 'chamber_diameter' in yollar

    def test_kunye_kanonik_anlami_soyler(self, yanit):
        k = yanit['chamber_diameter_kunye']
        assert k['unit'] == 'mm'
        assert k['quantity'] == 'grain outer diameter'
        assert k['value'] == pytest.approx(yanit['chamber_diameter'],
                                           rel=1e-12)
        assert k['basis']

    def test_kunye_ayni_adli_kardesleri_gercekten_sayar(self, yanit):
        """Künye bir liste basmakla kalmaz: saydığı yollar yanıtta VAR ve
        büyüklükleri üst düzeydekinden FARKLI."""
        k = yanit['chamber_diameter_kunye']
        assert k['same_name_elsewhere']
        for kayit in k['same_name_elsewhere']:
            dugum = yanit
            for parca in kayit['path'].split('.'):
                assert isinstance(dugum, dict) and parca in dugum, (
                    f"künye var olmayan yaprağı sayıyor: {kayit['path']}")
                dugum = dugum[parca]
            assert kayit['quantity'] and kayit['unit']
            if kayit['unit'] == 'm':
                assert float(dugum) * 1000.0 != pytest.approx(
                    yanit['chamber_diameter'], rel=1e-9), (
                    f"{kayit['path']} üst düzeyle AYNI büyüklük; künye "
                    'gereksiz yere ayrı ilan ediyor')

    def test_kalan_ayni_adli_yaprak_sahibiyle_ilan_edilmis(self, yanit):
        """Sahası dışındaki yaprak sessizce bırakılmaz, künyede adlanır."""
        k = yanit['chamber_diameter_kunye']
        yollar = {x['path'] for x in k['same_name_elsewhere']}
        kalan = {y for y, _ in _yapraklar(yanit, 'chamber_diameter')
                 if y != 'chamber_diameter'}
        assert kalan <= yollar, (
            f'künyede ilan edilmemiş aynı adlı yaprak: {kalan - yollar}')


# ---------------------------------------------------------------------------
# Borç imleri gerçekten kalktı mı?
# ---------------------------------------------------------------------------
class TestBorcImleriKalkti:

    def test_erozyon_bekcisinde_xfail_imi_kalmadi(self):
        """Borç imleri SÜSLEYİCİ olarak kalktı (AST; yorum metni sayılmaz)."""
        import ast
        agac = ast.parse((KOK / 'tests' / 'test_erosion.py')
                         .read_text(encoding='utf-8'))
        imli = []
        for d in ast.walk(agac):
            if not isinstance(d, ast.FunctionDef):
                continue
            for s in d.decorator_list:
                if 'xfail' in ast.unparse(s):
                    imli.append(d.name)
        assert not imli, (
            f'P2B1-03 / P2B3-03 borç imleri hâlâ duruyor: {imli}')

    def test_olcum_kaniti_yerinde(self):
        kanit = KOK / 'docs/scofield/raw/OH/D26/kati/a2'
        for ad in ('olcum.py', 'once_taban.json', 'sonra.json'):
            assert (kanit_gerekli(kanit / ad)).exists(), f'kanıt eksik: {ad}'
        once = json.loads((kanit_gerekli(kanit / 'once_taban.json')).read_text('utf-8'))
        sonra = json.loads((kanit_gerekli(kanit / 'sonra.json')).read_text('utf-8'))
        # Kanıt kendi iddiasını taşımalı (bayat ölçüm bekçisi).
        assert once['P2B1-03']['tahmin_katsayidan_bagimsiz'] is True
        assert sonra['P2B1-03']['tahmin_katsayidan_bagimsiz'] is False
        assert once['P2B3-03']['cad_paneli_malzemeden_bagimsiz'] is True
        assert sonra['P2B3-03']['cad_paneli_malzemeden_bagimsiz'] is False
        assert once['OH-D25-07']['zarfi_asip_sessiz_kalan'] == 3
        assert sonra['OH-D25-07']['zarfi_asip_sessiz_kalan'] == 0
        assert once['OH-D25-08']['ayrisan_sayisi'] == 3
        assert sonra['OH-D25-08']['ayrisan_sayisi'] == 0
        assert once['OH-D25-10']['kapilarin_ayristigi_govde'] == 1
        assert sonra['OH-D25-10']['kapilarin_ayristigi_govde'] == 0
        assert once['OH-D25-03']['yaprak_sayisi'] == 3
        assert sonra['OH-D25-03']['yaprak_sayisi'] == 2


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main([__file__, '-v']))
