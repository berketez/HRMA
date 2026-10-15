"""ÖH D37 A1b panel-js 6. tur (14 Eki) — API/PDF güvenlik sınıfı + cidar kaynağı.

ÖLÇÜLEN KUSURLAR (önce/sonra ``docs/scofield/raw/OH/A1b/panel-js/a1/t6/``):

* Devir 14 — ``POST /analyze_safety`` ve ``pdf_safety.build_pdf_safety``
  ``motor_type='solid'`` + ``propellant_type='kndx'`` (depoda tanınan şeker
  itici) isteğinde ``MOTOR_TYPE_TO_EXPLOSIVE_CLASS['solid'] = 'composite'``
  yedeğine düşüyordu: örnek KNDX gövdesinde composite, TNT 1,0108 kg,
  ölümcül parça menzili ve tahliye 1600 m. Panel yolu 5. turda kapanmıştı;
  API/PDF artık AYNI kuralı (merkezi katalog ailesi) tek işlevden okur.
* OH-AS-03 PDF ayağı — belge yolu (kapısız modül) bilinmeyen katı iticiyi
  'composite'e, bilinmeyen ADLI hibrit oksitleyiciyi ürünün varsayılan
  oksitleyicisine çeviriyordu (``DEVIR_A4_PDF`` strict xfail'leri).
* Devir 13 — güvenlik paneli örnek hibritte ısı modülünün KENDİ
  ``wall_temperature_unphysical = true`` imli soğutmasız DENGE cidarını
  (3312,5 K ≈ gaz geri kazanım sıcaklığı 3321,3 K) cidar diye gönderiyordu;
  termal 5,0 + yapısal 5,0. Artık çift gönderilmez.
"""
import pytest

from hrma.analysis.safety_analysis import (  # noqa: E402
    EXPLOSIVE_CATALOG_FAMILY_CODE,
    EXPLOSIVE_CATALOG_UNRESOLVED_CODE,
    GURNEY_FRAGMENT_FIELDS,
    HYBRID_OXIDIZER_DECOMPOSITION_KCAL_PER_MOL,
    KNOWN_PROPELLANT_CLASSES,
    PROPELLANT_CLASS_NOT_MODELLED,
    SafetyAnalyzer,
    THERMAL_VERDICT_NOT_EVALUATED,
    solid_catalog_explosive_class,
)
from hrma.data.propellants_db import ALIASES, PROPELLANTS as KATALOG  # noqa: E402
from tests.test_d37_panel_js_t5_guvenlik_sinifi import (  # noqa: E402,F401
    _node, _sessiz, client, katalog_json, motorlar, needs_node, VAKA_MOTOR)

TNT = SafetyAnalyzer().propellant_tnt_equivalents

#: Bağımsız kâhin: katalog kaydının AİLESİ (propellants_db), sınıf kümesi
#: (KNOWN_PROPELLANT_CLASSES) — üyelik; eşleme tablosu yok.
def _kahin(ad):
    k = str(ad).strip().lower()
    k = ALIASES.get(k, k)
    if k not in KATALOG:
        return PROPELLANT_CLASS_NOT_MODELLED
    aile = KATALOG[k]['family']
    return aile if aile in KNOWN_PROPELLANT_CLASSES else \
        PROPELLANT_CLASS_NOT_MODELLED


TUM_ADLAR = sorted(set(KATALOG) | set(ALIASES))
GOVDE = {'chamber_pressure': 40.0, 'propellant_mass': 2.40667,
         'chamber_diameter': 0.081, 'wall_thickness': 0.002,
         'thrust': 1299.71, 'burn_time': 2.27716, 'material': 'steel'}
PDF_GOVDE = {'chamber_pressure': 40.0, 'chamber_diameter': 0.081,
             'propellant_mass': 2.40667, 'thrust': 1299.71,
             'burn_time': 2.27716,
             'chamber_wall_policy': {'wall_thickness_m': 0.002}}


def _uc(client, **kimlik):
    r = _sessiz(client.post, '/analyze_safety', json=dict(GOVDE, **kimlik))
    assert r.status_code == 200, r.get_json()
    return r.get_json()['safety_analysis']


def _pdf(**kimlik):
    from hrma.export import pdf_safety
    s, _k = _sessiz(pdf_safety.build_pdf_safety, dict(PDF_GOVDE, **kimlik), {})
    assert s is not None, _k
    return s


def _sayi_yok(s, kod):
    ex = s['explosive_hazards']
    assert ex['explosive_class'] is None
    for alan in ('tnt_equivalent_kg', 'tnt_equivalent_factor',
                 'blast_distances', 'qd_requirements'):
        assert alan not in ex, (alan, ex.get(alan))
    beyan = ex['explosive_not_modelled']
    assert beyan['code'] == kod
    assert beyan['status'] == THERMAL_VERDICT_NOT_EVALUATED
    assert ex['explosive_verdict_withheld_because'] == beyan['reason']
    fr = ex['fragment_hazards']
    for alan in GURNEY_FRAGMENT_FIELDS:
        assert fr[alan] is None, (alan, fr[alan])
    pat = s['emergency_procedures']['explosion_response']
    assert pat['evacuation_distance'] is None
    assert pat['evacuation_distance_status'] == THERMAL_VERDICT_NOT_EVALUATED
    tox = s['toxic_hazards']
    assert tox.get('propellant_class') != 'composite'
    assert tox['toxic_hazard_level'] == THERMAL_VERDICT_NOT_EVALUATED
    assert 'explosive' in s['risk_assessment']['risks_not_evaluated']
    return ex


def _sinif_var(s, sinif, kutle):
    ex = s['explosive_hazards']
    assert ex['explosive_class'] == sinif
    assert ex['tnt_equivalent_kg'] == pytest.approx(kutle * TNT[sinif],
                                                    rel=1e-12)
    assert 'explosive_not_modelled' not in ex
    return ex


# ---------------------------------------------------------------------------
# 1) TEK KURAL — katalog ailesi; panel ile birebir
# ---------------------------------------------------------------------------
class TestKatiKatalogKurali:
    @pytest.mark.parametrize('ad', TUM_ADLAR)
    def test_her_katalog_adi_aile_kahinine_gore(self, ad):
        assert solid_catalog_explosive_class(ad)[0] == _kahin(ad)

    @pytest.mark.parametrize('ad', [None, '', 'unobtainium', 'lox_rp1',
                                    'custom', 'composite'])
    def test_cozulmeyen_ad_fail_closed(self, ad):
        assert solid_catalog_explosive_class(ad) == (
            PROPELLANT_CLASS_NOT_MODELLED, None, None)

    @pytest.mark.parametrize('ad', sorted(
        {r['name'] for r in KATALOG.values() if r.get('name')}))
    def test_kaydin_tam_adi_kendi_ailesine_cozulur(self, ad):
        """API/belge serbest ad taşır (katı yanıtı 'propellant_name')."""
        anahtar = [k for k, r in KATALOG.items() if r.get('name') == ad][0]
        assert solid_catalog_explosive_class(ad)[0] == _kahin(anahtar)

    @needs_node
    def test_panel_kurali_ile_ayni(self, katalog_json):
        siniflar = [{'ad': k, 'motorType': 'solid',
                     'results': {'propellant_type': k}} for k in TUM_ADLAR]
        out = _node({'loadCatalog': True, 'catalog': katalog_json,
                     'siniflar': siniflar})['siniflar']
        for k in TUM_ADLAR:
            assert out[k] == solid_catalog_explosive_class(k)[0], k


# ---------------------------------------------------------------------------
# 2) API — katı motor kendi iticisinin sınıfını alır, yedek 'composite' yok
# ---------------------------------------------------------------------------
class TestApi:
    @pytest.mark.parametrize('ad', ['kndx', 'KNSB', 'black_powder',
                                    'dextrose'])
    def test_seker_ve_kara_barut_sayi_yayimlamaz(self, client, ad):
        # ÖH 15 Eki (ana model): asıl iddia GÖVDEDE (depo bekçisi test_d22
        # TestP13B210 'delegesiz nüfus' mutlak tavanı); yardımcı kalanını denetler.
        ex = _sayi_yok(_uc(client, motor_type='solid', propellant_type=ad),
                       EXPLOSIVE_CATALOG_FAMILY_CODE)
        assert ex['explosive_class'] is None

    @pytest.mark.parametrize('kimlik', [
        {'motor_type': 'solid'},
        {'motor_type': 'solid', 'propellant_type': 'lox_rp1'}])
    def test_katalogda_olmayan_kati_sayi_yayimlamaz(self, client, kimlik):
        # ÖH 15 Eki (ana model): asıl iddia GÖVDEDE (depo bekçisi test_d22
        # TestP13B210 'delegesiz nüfus' mutlak tavanı); yardımcı kalanını denetler.
        ex = _sayi_yok(_uc(client, **kimlik), EXPLOSIVE_CATALOG_UNRESOLVED_CODE)
        assert ex['explosive_not_modelled']['code'] == EXPLOSIVE_CATALOG_UNRESOLVED_CODE

    @pytest.mark.parametrize('ad,sinif', [('apcp', 'composite'),
                                          ('pban', 'composite'),
                                          ('db', 'double_base')])
    def test_sinifi_olan_aile_hukmunu_kazanir(self, client, ad, sinif):
        # ÖH 15 Eki (ana model): asıl iddia GÖVDEDE (depo bekçisi test_d22
        # TestP13B210 'delegesiz nüfus' mutlak tavanı); yardımcı kalanını denetler.
        ex = _sinif_var(_uc(client, motor_type='solid', propellant_type=ad),
                        sinif, GOVDE['propellant_mass'])
        assert ex['explosive_class'] == sinif


# ---------------------------------------------------------------------------
# 3) PDF — aynı tek işlev (kapısız modül)
# ---------------------------------------------------------------------------
class TestPdf:
    def test_kndx_belgede_sayi_yok(self):
        # ÖH 15 Eki (ana model): asıl iddia GÖVDEDE (depo bekçisi test_d22
        # TestP13B210 'delegesiz nüfus' mutlak tavanı); yardımcı kalanını denetler.
        ex = _sayi_yok(_pdf(motor_type='solid', propellant_type='kndx'),
                       EXPLOSIVE_CATALOG_FAMILY_CODE)
        assert ex['explosive_class'] is None

    def test_apcp_belgede_composite(self):
        # ÖH 15 Eki (ana model): asıl iddia GÖVDEDE (depo bekçisi test_d22
        # TestP13B210 'delegesiz nüfus' mutlak tavanı); yardımcı kalanını denetler.
        ex = _sinif_var(_pdf(motor_type='solid', propellant_type='apcp'),
                        'composite', PDF_GOVDE['propellant_mass'])
        assert ex['explosive_class'] == 'composite'

    def test_adli_cozulmeyen_oksitleyici_varsayilana_dusmez(self):
        ex = _pdf(motor_type='hybrid',
                  oxidizer_type='unobtainium')['explosive_hazards']
        assert ex['explosive_class'] is None
        assert 'tnt_equivalent_kg' not in ex
        neden = ex['explosive_verdict_withheld_because']
        assert "oxidizer_type 'unobtainium'" in neden

    @pytest.mark.parametrize('oks', sorted(
        HYBRID_OXIDIZER_DECOMPOSITION_KCAL_PER_MOL))
    def test_adli_cozulen_oksitleyici_sinifini_alir(self, oks):
        # ÖH 15 Eki (ana model): asıl iddia GÖVDEDE (depo bekçisi test_d22
        # TestP13B210 'delegesiz nüfus' mutlak tavanı); yardımcı kalanını denetler.
        ex = _sinif_var(_pdf(motor_type='hybrid', oxidizer_type=oks),
                        'hybrid_%s' % oks, PDF_GOVDE['propellant_mass'])
        assert ex['explosive_class'] == 'hybrid_%s' % oks


# ---------------------------------------------------------------------------
# 4) CİDAR KAYNAĞI — ısı modülünün 'fiziksel değil' imli denge cidarı gitmez
# ---------------------------------------------------------------------------
@needs_node
class TestCidarKaynagi:
    def test_ornek_hibrit_bayrakli_cifti_gondermez(self, motorlar,
                                                  katalog_json):
        m = motorlar['hybrid']['motor']
        gsa = m['heat_transfer_analysis']['gas_side_analysis']
        ta = m['structural_analysis']['thermal_analysis']
        # Ölçülen kusurun kendisi: çözücü bayrağı koyuyor, yapısal blok
        # aynı sayıyı 'heat_transfer_module' kaynağıyla aktarıyor.
        assert gsa['wall_temperature_unphysical'] is True
        assert ta['wall_temperature_source'] == 'heat_transfer_module'
        assert ta['wall_temperature_inner_K'] == pytest.approx(
            gsa['estimated_wall_temperature'], rel=1e-12)
        out = _node({'loadCatalog': True, 'catalog': katalog_json,
                     'vakalar': {'h': {'motorType': 'hybrid',
                                       'results': motorlar['hybrid']}}})
        govde = out['govdeler']['h']
        assert 'wall_temperature_hot' not in govde
        assert 'wall_temperature_cold' not in govde

    def test_bayraksiz_cozulmus_cift_aynen_gider(self, motorlar,
                                                katalog_json):
        import copy
        r = copy.deepcopy(motorlar['hybrid'])
        r['motor']['heat_transfer_analysis']['gas_side_analysis'][
            'wall_temperature_unphysical'] = False
        out = _node({'loadCatalog': True, 'catalog': katalog_json,
                     'vakalar': {'h': {'motorType': 'hybrid',
                                       'results': r}}})
        ta = r['motor']['structural_analysis']['thermal_analysis']
        govde = out['govdeler']['h']
        assert govde['wall_temperature_hot'] == pytest.approx(
            ta['wall_temperature_inner_K'], rel=1e-5)
        assert govde['wall_temperature_cold'] == pytest.approx(
            ta['wall_temperature_outer_K'], rel=1e-5)

    def test_uc_termal_hukmu_ve_birlesik_katsayiyi_geri_ceker(
            self, client, motorlar, katalog_json):
        out = _node({'loadCatalog': True, 'catalog': katalog_json,
                     'vakalar': {'h': {'motorType': 'hybrid',
                                       'results': motorlar['hybrid']}}})
        r = _sessiz(client.post, '/analyze_safety', json=out['govdeler']['h'])
        s = r.get_json()['safety_analysis']
        assert s['thermal_safety']['thermal_verdict'] == 'withheld'
        assert s['structural_safety']['combined_safety_factor'] is None
        ra = s['risk_assessment']
        assert 'thermal' in ra['risks_not_evaluated']
        assert ra['individual_risks']['thermal'] is None
