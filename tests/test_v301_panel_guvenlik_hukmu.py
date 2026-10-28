"""V301/PANEL kalem 1 (NK-18 + NK-17 + K-C1 AÇIK 5) — güvenlik hükmü TEK işlevden.

ÖLÇÜLEN KUSUR (``docs/scofield/raw/OH/V301/panel/guvenlik_once.json``,
taban 2facae6a0): aynı tasarım için Performans Özeti, güverte GÜVENLİK
sekmesi ve PDF güvenlik bölümü üç ayrı yapısal hüküm basıyordu (örnek
hibrit: NOT_EVALUATED / UNSAFE 5/5 / SAFE). Sekmenin UNSAFE'i ucun kendi
çıplak cidar Bartz tahmininden geliyordu (hibrit 3304 K ss_304, katı
1684 K yalıtımsız kasa) ve ``do_not_proceed`` + ``redesign_required``
basıyordu (KABUL K2 bulguları 6-7).

Kural: hesaplanmış motorun yapısal hükmü motorun KENDİ zincirinin hükmüdür
(``safety_analysis.motor_structural_verdict``). Güvenlik sekmesi ve PDF o
kaydı benimser; motor sonucu varken uç çıplak cidar tahminini KOŞMAZ, yani
sekme ısı modülünden / termal panelden bağımsızdır (termal panel ayrıca
düzeltildiğinde güvenlik paneline dokunmak gerekmez).

Bekçiler: üç örnek + bir UNSAFE vaka × (özet, sekme, PDF) aynı hüküm; yol
tablosu panel ⟷ sunucu aynı; ısı modülü bozulsa da sekme yanıtı bit-aynı;
düzenlenmiş girdi motor hükmünü kazanmaz; itki uydurulmaz.
"""
import copy
import hashlib
import json

import pytest

from hrma.analysis.safety_analysis import (
    MOTOR_STRUCTURAL_VERDICT_BLOCKS,
    STRUCTURAL_VERDICT_SOURCE_MODULE,
    STRUCTURAL_VERDICT_SOURCE_MOTOR,
    SafetyAnalyzer,
    motor_structural_verdict,
)
from tests.test_d37_panel_js_t5_guvenlik_sinifi import (  # noqa: F401
    ORNEK_HIBRIT, ORNEK_KATI, ORNEK_SIVI, SIVI_SURE_S, _node, _sessiz,
    client, katalog_json, needs_node)

VAKALAR = {
    'hibrit_ornek': 'hybrid',
    'hibrit_ince_cidar_1mm': 'hybrid',
    'kati_ornek': 'solid',
    'sivi_ornek': 'liquid',
}


def _alanlar(yol):
    return json.loads(yol.read_text(encoding='utf-8'))['inputs']['fields']


@pytest.fixture(scope='module')
def sonuclar(client):
    hib = _alanlar(ORNEK_HIBRIT)
    istekler = {
        'hibrit_ornek': ('/calculate', hib),
        # UNSAFE vaka: aynı örnek, kullanıcı cidarı 1 mm (doğrulama kipi).
        'hibrit_ince_cidar_1mm': ('/calculate', dict(hib, wall_thickness=1.0)),
        'kati_ornek': ('/calculate_solid', _alanlar(ORNEK_KATI)),
        'sivi_ornek': ('/calculate_liquid', dict(
            _alanlar(ORNEK_SIVI), max_burn_duration=SIVI_SURE_S)),
    }
    out = {}
    for ad, (uc, govde) in istekler.items():
        r = _sessiz(client.post, uc, json=govde)
        assert r.status_code == 200, (ad, r.get_data(as_text=True)[:300])
        out[ad] = r.get_json()
    return out


@pytest.fixture(scope='module')
def sekme(sonuclar, katalog_json, client):
    """Güverte GÜVENLİK sekmesi: panelin gövdesi (bağlam dahil) → uç."""
    out = _node({'loadCatalog': True, 'catalog': katalog_json, 'vakalar': {
        ad: {'motorType': VAKALAR[ad], 'results': sonuclar[ad]}
        for ad in VAKALAR}})
    yanit = {}
    for ad in VAKALAR:
        govde = out['govdeler'][ad]
        r = _sessiz(client.post, '/analyze_safety', json=govde)
        assert r.status_code == 200, (ad, r.get_data(as_text=True)[:300])
        yanit[ad] = {'govde': govde, 'j': r.get_json()}
    return yanit


def _ozet_hukmu(ad, r):
    """Performans Özeti / sonuç kartının OKUDUĞU çözücü alanı (kâhin)."""
    mt = VAKALAR[ad]
    if mt == 'hybrid':
        sa = r['motor']['structural_analysis']['safety_analysis']
        return sa['status'], sa['verdict_withheld'] is True
    if mt == 'solid':
        st = r['safety_analysis']['pressure_safety']['vessel_status']
        return ('NOT_EVALUATED' if st == 'NOT_EVALUATED' else st,
                st == 'NOT_EVALUATED')
    cs = r['structural_analysis']['chamber_structure']
    # Sıvı kartı boyutlandırılmış cidarda "VERDICT WITHHELD" ya da "tasarım
    # hedefi geri okunur" basar: hüküm sözcüğü yayımlanmaz.
    assert (cs.get('verdict_withheld') is True
            or cs.get('safety_factor_is_tautological') is True)
    return 'NOT_EVALUATED', True


# ---------------------------------------------------------------------------
# 1) TEK İŞLEV — kayıt çözücünün kendi alanıdır
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('ad', sorted(VAKALAR))
def test_tek_islev_ozetin_okudugu_alani_okur(sonuclar, ad):
    kayit = motor_structural_verdict(VAKALAR[ad], sonuclar[ad])
    durum, geri = _ozet_hukmu(ad, sonuclar[ad])
    assert kayit['source'] == STRUCTURAL_VERDICT_SOURCE_MOTOR
    assert kayit['status'] == durum
    assert kayit['withheld'] is geri


def test_beklenen_hukumler(sonuclar):
    """Ölçülen sonuç (guvenlik_sonra.json): üç örnek geri çekili, ince cidar UNSAFE."""
    hukum = {ad: motor_structural_verdict(VAKALAR[ad], sonuclar[ad])['status']
             for ad in VAKALAR}
    assert hukum == {'hibrit_ornek': 'NOT_EVALUATED',
                     'hibrit_ince_cidar_1mm': 'UNSAFE',
                     'kati_ornek': 'NOT_EVALUATED',
                     'sivi_ornek': 'NOT_EVALUATED'}


@pytest.mark.parametrize('mt,bos', [('hybrid', {}), ('solid', {'x': 1}),
                                    ('liquid', None), ('peynir', {'a': 1})])
def test_blok_yoksa_kayit_uydurulmaz(mt, bos):
    assert motor_structural_verdict(mt, bos) is None


def _js_tablo(js, ad):
    import re
    blok = re.search(r'const %s = \{(.*?)\};' % ad, js, re.S)
    assert blok, '%s panelde yok' % ad
    tablo = {}
    for satir in re.finditer(r"(\w+):\s*\[((?:\s*\[[^\]]*\],?)+)\s*\]",
                             blok.group(1), re.S):
        tablo[satir.group(1)] = tuple(
            '.'.join(re.findall(r"'([^']+)'", yol))
            for yol in re.findall(r"\[([^\[\]]*)\]", satir.group(2)))
    return tablo


def test_yol_tablosu_panel_ile_ayni():
    """Panelin taşıdığı bloklar = sunucunun okuduğu bloklar (tek tablo)."""
    import pathlib
    from hrma.analysis.safety_analysis import MOTOR_WALL_ZONE_BLOCKS
    js = (pathlib.Path(__file__).resolve().parents[1] / 'hrma' / 'static'
          / 'js' / 'panels' / 'safety_panel.js').read_text(encoding='utf-8')
    assert _js_tablo(js, 'MOTOR_VERDICT_BLOCKS') == {
        k: tuple(v) for k, v in MOTOR_STRUCTURAL_VERDICT_BLOCKS.items()}
    assert _js_tablo(js, 'MOTOR_ZONE_BLOCKS') == {
        k: tuple(v) for k, v in MOTOR_WALL_ZONE_BLOCKS.items()}


def test_cozulmemis_kaynak_listesi_guverte_ile_ayni():
    import pathlib
    import re
    from hrma.analysis.safety_analysis import (
        SOLID_CASE_TEMPERATURE_PATH, WALL_TEMP_SOURCES_NOT_SOLVED)
    js = (pathlib.Path(__file__).resolve().parents[1] / 'hrma' / 'static'
          / 'js' / 'analysis_dock.js').read_text(encoding='utf-8')
    liste = re.search(r'const WALL_TEMP_SOURCE_NOT_SOLVED = \[(.*?)\];',
                      js, re.S).group(1)
    assert tuple(re.findall(r"'([^']+)'", liste)) == \
        WALL_TEMP_SOURCES_NOT_SOLVED
    assert ("const SOLID_CASE_TEMPERATURE_PATH = '%s'"
            % SOLID_CASE_TEMPERATURE_PATH) in js


# ---------------------------------------------------------------------------
# 2) SEKME — özetle aynı hüküm, aynı gerekçe
# ---------------------------------------------------------------------------
@needs_node
@pytest.mark.parametrize('ad', sorted(VAKALAR))
def test_sekme_ozetle_ayni_hukum(sonuclar, sekme, ad):
    kayit = motor_structural_verdict(VAKALAR[ad], sonuclar[ad])
    st = sekme[ad]['j']['safety_analysis']['structural_safety']
    assert st['verdict_source'] == STRUCTURAL_VERDICT_SOURCE_MOTOR
    assert st['structural_integrity'] == kayit['status']
    assert st['verdict_withheld'] is kayit['withheld']
    assert st['verdict_withheld_reasons'] == kayit['reasons']
    assert st['verdict_basis'] == kayit['basis']
    ra = sekme[ad]['j']['safety_analysis']['risk_assessment']
    if kayit['withheld']:
        assert ra['individual_risks']['structural'] is None
        assert 'structural' in ra['risks_not_evaluated']


@needs_node
def test_unsafe_vakada_risk_sozcugu_ozetle_ayni(sonuclar, sekme):
    sa = sonuclar['hibrit_ince_cidar_1mm']['motor']['structural_analysis'][
        'safety_analysis']
    assert (sa['status'], sa['risk_level']) == ('UNSAFE', 'HIGH')
    ra = sekme['hibrit_ince_cidar_1mm']['j']['safety_analysis'][
        'risk_assessment']
    # Yapısal eksen HIGH bandının üst ucu: geri sınıflandırınca HIGH.
    assert ra['individual_risks']['structural'] == 4.0


@needs_node
@pytest.mark.parametrize('ad', ['hibrit_ornek', 'kati_ornek'])
def test_ana_hesap_kritiksizken_sekme_ilerleme_demez(sekme, ad):
    """KABUL K2 bulgu 6-7: çıplak cidar tahmini 'do_not_proceed' üretmez."""
    s = sekme[ad]['j']['safety_analysis']
    kodlar = {(r or {}).get('code') for r in s['recommendations']}
    assert 'warn.safety.do_not_proceed' not in kodlar
    assert 'warn.safety.redesign_required' not in kodlar
    th = s['thermal_safety']
    if ad == 'hibrit_ornek':
        # ÖRNEK-PANEL DEVİR 1: hibrit cidar = motorun bölge modeli; kasa
        # sıcaklığı beyanlı, ondan sayı türetilmez, gerekçe bölgelerle.
        assert th['thermal_verdict'] == 'withheld'
        assert 'motor result' in th['wall_temperature_source']
        zones = th['motor_wall_zones']['zones']
        assert [z['verdict'] for z in zones] == [
            'PROTECTED_DURING_BURN', 'LINER_REQUIRED', 'LINER_REQUIRED']
        assert 'LINER_REQUIRED' in th['thermal_verdict_withheld_because']
        assert 'HRMA-sized liner' in th['thermal_verdict_withheld_because']
    else:
        # Katı: motorun ÇÖZDÜĞÜ kasa sıcaklığı (yalıtım + astar arkası).
        assert th['thermal_verdict'] == 'issued'
        assert th['wall_temperature_source'] == \
            'motor_data wall_temperature_hot/cold contract'
    assert s['risk_assessment']['risk_level'] in ('LOW', 'MEDIUM')


@needs_node
def test_sivida_cozulmus_cift_aynen_kullanilir(sekme):
    th = sekme['sivi_ornek']['j']['safety_analysis']['thermal_safety']
    assert th['wall_temperature_source'] == \
        'motor_data wall_temperature_hot/cold contract'
    g = sekme['sivi_ornek']['govde']
    assert th['estimated_wall_temperature_k'] == pytest.approx(
        g['wall_temperature_hot'], rel=1e-12)


@needs_node
@pytest.mark.parametrize('ad', sorted(VAKALAR))
def test_sekme_isi_modulunden_bagimsiz(client, sekme, monkeypatch, ad):
    """Motor sonucu varken uç ısı modülünü ÇAĞIRMAZ: modül bozulsa da yanıt
    bit-aynı (termal panel düzeltmeleri güvenlik hükmünü değiştirmez)."""
    from hrma.analysis import heat_transfer_analysis as hta

    def _bozuk(*a, **k):
        raise AssertionError('ısı modülü çağrıldı')

    monkeypatch.setattr(hta.HeatTransferAnalyzer, 'analyze_heat_transfer',
                        _bozuk)
    r = _sessiz(client.post, '/analyze_safety', json=sekme[ad]['govde'])
    assert r.status_code == 200
    sha = lambda j: hashlib.sha256(json.dumps(  # noqa: E731
        j, sort_keys=True, default=str).encode()).hexdigest()
    assert sha(r.get_json()) == sha(sekme[ad]['j'])


# ---------------------------------------------------------------------------
# 3) PDF — aynı tek işlev (DEVİR: hrma/export/pdf_safety.py bu kulvara
#    kapalı; yama docs/scofield/raw/OH/V301/panel/DEVIR_pdf_safety_motor_
#    verdict.patch). Yama uygulanınca strict xfail XPASS olur ve kırmızıya
#    döner: işaret o anda kaldırılır.
# ---------------------------------------------------------------------------
def _pdf(sonuc, mt):
    from hrma.app import _build_pdf_motor_data, _build_pdf_analysis_sections
    from hrma.export.pdf_safety import build_pdf_safety
    if mt == 'hybrid':
        md = sonuc['motor']
    elif mt == 'liquid':
        md = {'motor_type': 'liquid', 'thrust': sonuc.get('thrust'),
              'chamber_pressure': sonuc.get('chamber_pressure'),
              'burn_time': sonuc.get('burn_time')}
    else:
        geo = sonuc.get('motor_geometry') or {}
        md = {'motor_name': 'HRMA-SOLID', 'motor_type': 'solid',
              'propellant_type': sonuc.get('propellant_name'),
              'chamber_diameter': geo.get('chamber_diameter') * 1000,
              'chamber_length': geo.get('chamber_length') * 1000,
              'propellant_mass': sonuc.get('propellant_mass'),
              'thrust': sonuc.get('max_thrust'),
              'burn_time': sonuc.get('burn_time'),
              'chamber_pressure': sonuc.get('chamber_pressure')}
    md2 = _sessiz(_build_pdf_motor_data, dict(md), dict(sonuc))
    ar2 = _sessiz(_build_pdf_analysis_sections, md2, dict(sonuc))
    s, _k = _sessiz(build_pdf_safety, md2, ar2)
    assert s is not None, _k
    return s


# V301/FİZİK-2 (27 Eki): DEVİR yaması hrma/export/pdf_safety.py'ye olduğu
# gibi uygulandı (DEVIR_pdf_safety_motor_verdict.patch); strict xfail işareti
# kaldırıldı. Dört vakada PDF = özet = sekme ölçüldü
# (docs/scofield/raw/OH/V301/fizik-2/k2_k3_pdf_guvenlik.json).
@pytest.mark.parametrize('ad', sorted(VAKALAR))
def test_pdf_ozetle_ayni_hukum(sonuclar, ad):
    kayit = motor_structural_verdict(VAKALAR[ad], sonuclar[ad])
    pdf = _pdf(sonuclar[ad], VAKALAR[ad])
    st = pdf['structural_safety']
    assert st['verdict_source'] == STRUCTURAL_VERDICT_SOURCE_MOTOR
    assert st['structural_integrity'] == kayit['status']


# ---------------------------------------------------------------------------
# 4) UÇ — düzenlenmiş girdi, eksik blok, itki
# ---------------------------------------------------------------------------
@needs_node
def test_duzenlenmis_cidar_motor_hukmunu_kazanmaz(client, sekme):
    govde = dict(sekme['hibrit_ornek']['govde'], wall_thickness=0.003)
    r = _sessiz(client.post, '/analyze_safety', json=govde)
    st = r.get_json()['safety_analysis']['structural_safety']
    assert st['verdict_source'] == STRUCTURAL_VERDICT_SOURCE_MODULE
    ret = st['motor_verdict_not_adopted']
    assert ret['reason'] == 'structural_inputs_differ_from_motor_result'
    assert [f['field'] for f in ret['fields']] == ['wall_thickness']


@needs_node
def test_hukum_bloksuz_motor_sonucu_adiyla_reddedilir(client, sekme):
    govde = dict(sekme['hibrit_ornek']['govde'], motor_result={'motor': {}})
    r = _sessiz(client.post, '/analyze_safety', json=govde)
    assert r.status_code == 422
    j = r.get_json()
    assert j['error'] == 'motor_result_without_structural_verdict'
    assert j['invalid_fields'][0]['field'] == 'motor_result'


@pytest.mark.parametrize('deger', ['SAFE', 3, ['x']])
def test_motor_sonucu_nesne_olmali(client, deger):
    govde = {'chamber_pressure': 30.0, 'propellant_mass': 10.0,
             'chamber_diameter': 0.08, 'wall_thickness': 0.004,
             'motor_type': 'hybrid', 'motor_result': deger}
    r = _sessiz(client.post, '/analyze_safety', json=govde)
    assert r.status_code in (400, 422)
    assert 'motor_result' in json.dumps(r.get_json())


def test_itki_uydurulmaz(client):
    govde = {'chamber_pressure': 30.0, 'propellant_mass': 10.0,
             'chamber_diameter': 0.08, 'wall_thickness': 0.004,
             'motor_type': 'hybrid', 'burn_time': 5.0}
    j = _sessiz(client.post, '/analyze_safety', json=govde).get_json()
    assert 'thrust' not in j['defaults_applied']
    s = j['safety_analysis']
    assert s['inputs_used']['thrust_n'] is None
    assert s['thrust_dependent_not_evaluated']['status'] == 'NOT_EVALUATED'
    um = s['explosive_hazards']['fragment_hazards']['unrestrained_motor']
    assert um['required_restraint_force_n'] is None


@needs_node
def test_kati_sekme_tepe_itkisi_pdf_ile_ayni(sonuclar, sekme):
    assert sekme['kati_ornek']['govde']['thrust'] == pytest.approx(
        sonuclar['kati_ornek']['max_thrust'], rel=1e-5)


def test_bagimsiz_istekte_modul_hukmu_adiyla(client):
    """Motor sonucu yoksa modülün kendi denetimi koşar ve bunu söyler."""
    an = SafetyAnalyzer()
    s = _sessiz(an.analyze_comprehensive_safety, motor_data={
        'chamber_pressure': 30.0, 'chamber_diameter': 0.08,
        'wall_thickness': 0.004}, propellant_mass=10.0, motor_type='hybrid')
    assert s['structural_safety']['verdict_source'] == \
        STRUCTURAL_VERDICT_SOURCE_MODULE
    assert 'verdict_withheld' not in s['structural_safety']


def test_benimseme_girdisiz_kayitta_bit_ayni_sayilar(sonuclar):
    """Benimseme modülün çember sayılarını değiştirmez (tanı sayısı)."""
    an = SafetyAnalyzer()
    md = {'chamber_pressure': 30.0, 'chamber_diameter': 0.0847501,
          'wall_thickness': 0.00449435}
    kayit = copy.deepcopy(motor_structural_verdict(
        'hybrid', sonuclar['hibrit_ornek']))
    a = _sessiz(an.analyze_comprehensive_safety, motor_data=dict(md),
                propellant_mass=10.0, motor_type='hybrid',
                material='ss_304')['structural_safety']
    b = _sessiz(an.analyze_comprehensive_safety, motor_data=dict(md),
                propellant_mass=10.0, motor_type='hybrid', material='ss_304',
                motor_verdict=kayit)['structural_safety']
    for alan in ('hoop_stress_mpa', 'yield_safety_factor',
                 'ultimate_safety_factor'):
        assert a[alan] == b[alan]
    assert b['structural_integrity'] == 'NOT_EVALUATED'


@needs_node
def test_kati_sekme_kasa_cifti_motorun_cozdugu(sonuclar, sekme):
    """ÖRNEK-PANEL DEVİR 1: ısıl panelle aynı yol ve aynı kapı."""
    r = sonuclar['kati_ornek']
    t = r['thermal_analysis']['heat_transfer']['case_temperature_k']
    g = sekme['kati_ornek']['govde']
    assert g['wall_temperature_hot'] == pytest.approx(t, rel=1e-5)
    assert g['wall_temperature_cold'] == pytest.approx(t, rel=1e-5)
    th = sekme['kati_ornek']['j']['safety_analysis']['thermal_safety']
    assert th['estimated_wall_temperature_k'] == pytest.approx(t, rel=1e-5)


@needs_node
@pytest.mark.parametrize('ad', sorted(VAKALAR))
def test_python_ve_guverte_cidar_cifti_ayni(sonuclar, sekme, ad):
    """PDF'in okuyucusu (Python) = güvertenin okuyucusu (JS)."""
    from hrma.analysis.safety_analysis import motor_solved_wall_pair
    cift = motor_solved_wall_pair(VAKALAR[ad], sonuclar[ad])
    g = sekme[ad]['govde']
    if cift is None:
        assert 'wall_temperature_hot' not in g
        assert 'wall_temperature_cold' not in g
    else:
        assert g['wall_temperature_hot'] == pytest.approx(cift['hot'], rel=1e-5)
        assert g['wall_temperature_cold'] == pytest.approx(cift['cold'],
                                                           rel=1e-5)
    # Ölçülen: hibritte çift yok (beyanlı bölge), katı ve sıvıda var.
    assert (cift is None) is ad.startswith('hibrit')


@needs_node
@pytest.mark.parametrize('ad', sorted(VAKALAR))
def test_ariza_modu_agirligi_hukum_degil(sekme, ad):
    """ÖRNEK-PANEL DEVİR 2: genel listenin SONUÇ ağırlığı 'severity' değil."""
    st = sekme[ad]['j']['safety_analysis']['structural_safety']
    for mod in st['failure_modes']:
        assert 'severity' not in mod, mod
        assert mod['consequence_severity'] in ('CRITICAL', 'HIGH', 'MEDIUM')
    html = _node({'render': {'h': sekme[ad]['j']}})['html']['h']
    assert 'data-safety-failure-modes-note="1"' in html
