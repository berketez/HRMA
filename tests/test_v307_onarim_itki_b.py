"""V307/ONARIM-İTKİ-B — mühendis turu (19 Kas 2026) bulgularının bekçileri.

Bulgu raporu: ``~/HRMA-calisma/2026-11-19/MUHENDIS-ITKI/BULGULAR.md``.
Kanıt ve RAPOR: ``docs/scofield/raw/OH/V307/onarim-itki-b/``.
"""
import math
import os

import pytest

from hrma.utils import injector_design as uid
from hrma.utils.injector_design import (
    InjectorPlateInputError, injector_plate_structural)

# Plaka malzemesi: P10B1-25 bekçisinin kaydı (tek tanım, oradan okunur).
from tests.test_z5s_enjektor_kararlilik import CELIK  # noqa: E402


def _plaka(sf=None, motor=None):
    return injector_plate_structural(
        delta_P_bar=4.0, plate_diameter_m=0.1, material_props=CELIK,
        material_name='AISI 4130', plate_thickness_m=0.006,
        n_holes=12, hole_diameter_m=0.0015, required_sf=sf,
        motor_target_sf=motor)


# ===========================================================================
# M7-ITKI-9 — hibrit plaka, motorun tasarım hedefiyle denetlenir
# ===========================================================================
def test_itki9_kullanici_hedefi_yoksa_motorun_hedefi_kullanilir():
    r = _plaka(None, 4.0)
    assert r['required_safety_factor'] == pytest.approx(4.0)
    assert r['required_safety_factor_source'] == 'motor_design_target'
    # Gereken kalınlık sqrt(SF) ile ölçeklenir: 4,0 / 2,0 hedef oranı.
    v = _plaka(None, None)
    assert v['required_safety_factor_source'] == 'default'
    assert r['required_thickness_mm'] / v['required_thickness_mm'] == (
        pytest.approx(math.sqrt(4.0 / uid.INJECTOR_PLATE_DEFAULT_SF),
                      rel=1e-3))


def test_itki9_kullanici_hedefi_motorun_hedefinden_once_gelir():
    r = _plaka(3.0, 4.0)
    assert r['required_safety_factor'] == pytest.approx(3.0)
    assert r['required_safety_factor_source'] == 'user'


@pytest.mark.parametrize('motor', [0.0, -1.0, float('nan'), 'abc'])
def test_itki9_gecersiz_motor_hedefi_sessizce_varsayilana_dusmez(motor):
    with pytest.raises(InjectorPlateInputError):
        _plaka(None, motor)


@pytest.fixture(scope='module')
def hibrit_plaka_yaniti():
    os.environ.setdefault('HRMA_PROJECTS_DIR', os.path.expanduser(
        '~/HRMA-calisma/2026-11-19/ONARIM-ITKI-B/projeler'))
    from tests.support.kabul_sayfa_yukleri import SAYFA_YUKLERI
    from hrma.app import app
    yuk = dict(SAYFA_YUKLERI['hybrid'])
    # Mühendisin adımı: Enjektör Malzemesi = Paslanmaz çelik 316.
    yuk['injector_material'] = 'stainless_steel'
    yanit = app.test_client().post('/calculate', json=yuk)
    assert yanit.status_code == 200
    return yanit.get_json()


def test_itki9_hibrit_ornek_plaka_hedefi_motorun_yapisal_hedefiyle_ayni(
        hibrit_plaka_yaniti):
    """ÖNCE: plaka hedefi 2,00 (``default``), gereken 9,54 mm; motorun
    kamara/kapak/lüle/cıvata hedefi 4,0. SONRA: plaka da 4,0 hedefle,
    gereken 13,49 mm (mühendisin el hesabı: Roark 10b + PG-52 η 0,9246,
    p 5,0525 MPa, a 51,615 mm -> 13,49 mm)."""
    d = hibrit_plaka_yaniti
    ps = d['injector']['plate_structural']
    hedef = d['motor']['structural_analysis']['chamber_analysis'][
        'design_safety_factor_target']
    assert ps['required_safety_factor'] == pytest.approx(hedef)
    assert ps['required_safety_factor_source'] == 'motor_design_target'
    assert ps['required_thickness_mm'] == pytest.approx(13.49, abs=0.01)
    assert ps['load_cases']['startup_shutdown']['required_thickness_mm'] == (
        pytest.approx(13.49, abs=0.01))


# ===========================================================================
# M7-ITKI-11 — hibrit PDF: HRMA sütunu kuramsal (adıyla), teslim c* ayrı satır
# ===========================================================================
def _hibrit_cea_hikayesi(lang='en', csv=None):
    from hrma.export import rapor_sozluk
    from hrma.export.pdf_generator import PDFReportGenerator
    gen = PDFReportGenerator(lang=lang)
    blok = {'schema': 'hrma.cea_comparison/1', 'status': 'available',
            'operating_point': {'chamber_pressure_bar': 30.0,
                                'of_ratio': 6.0, 'expansion_ratio': 5.035},
            'rows': [{'quantity': 'c_star', 'hrma': 1599.4, 'cea': 1599.1,
                      'delta_pct': 0.019, 'unit': 'm/s'}]}
    ar = {'cea_comparison': blok}
    if csv is not None:
        ar['motor'] = {'c_star_efficiency': csv}
    with rapor_sozluk.dil_baglami(lang):
        return gen._create_cea_comparison_section(ar)


def _hikaye_metni(story):
    parcalar = []
    for s in story:
        if type(s).__name__ == 'Table':
            for satir in s._cellvalues:
                for h in satir:
                    parcalar.append(h.getPlainText() if hasattr(
                        h, 'getPlainText') else str(h))
        elif hasattr(s, 'getPlainText'):
            parcalar.append(s.getPlainText())
    return ' | '.join(parcalar)


CSV_ORNEK = {'applied': True, 'eta_c_star': 0.89,
             'c_star_delivered_m_s': 1423.4660813865244,
             'c_star_theoretical_m_s': 1599.400091445533}


def test_itki11_hibrit_pdf_hrma_sutunu_kuramsal_diye_adlandirilir():
    metin = _hikaye_metni(_hibrit_cea_hikayesi('en', CSV_ORNEK))
    assert 'HRMA (theoretical, before efficiencies)' in metin, metin


def test_itki11_hibrit_pdf_teslim_c_yildiz_satiri_basilir_en_tr():
    en = _hikaye_metni(_hibrit_cea_hikayesi('en', CSV_ORNEK))
    assert ('1423.5 m/s = η_c* 0.890 × theoretical 1599.4 m/s'
            in en), en
    tr = _hikaye_metni(_hibrit_cea_hikayesi('tr', CSV_ORNEK))
    assert 'teslim c*' in tr and '1423,5 m/s' in tr, tr
    assert 'HRMA (teorik, verimlerden önce)' in tr, tr
    assert 'Delivered' not in tr and 'theoretical' not in tr, tr


def test_itki11_c_yildiz_verimi_yoksa_teslim_satiri_uydurulmaz():
    metin = _hikaye_metni(_hibrit_cea_hikayesi('en', None))
    assert 'Delivered c*' not in metin


# ===========================================================================
# M7-ITKI-17 — vakum tasarımı sıvı PDF'i tasarım ortamını ve DS ayrılmasını yazar
# ===========================================================================
DA_VAKUM = {
    'mode': 'vacuum', 'is_sea_level': False, 'pressure_bar': 0.0,
    'altitude_m': None,
    'sea_level': {'status': 'separated', 'exit_pressure_bar': 0.0566,
                  'separation_pressure_bar': 0.4053,
                  'max_attached_expansion_ratio_2dp': 13.36}}


def _sivi_performans_metni(lang, da):
    from hrma.export import rapor_sozluk
    from hrma.export.pdf_generator import PDFReportGenerator
    gen = PDFReportGenerator(lang=lang)
    ar = {'performance': {'thrust': 25000.0, 'specific_impulse': 322.4,
                          'chamber_pressure': 50.0}}
    if da is not None:
        ar['design_ambient'] = da
    md = {'motor_type': 'liquid', 'motor_name': 'L'}
    with rapor_sozluk.dil_baglami(lang):
        return _hikaye_metni(gen._create_analysis_results(ar, md))


def test_itki17_vakum_tasarimi_pdf_ortami_ve_ds_ayrilmasini_yazar_en():
    metin = _sivi_performans_metni('en', DA_VAKUM)
    assert 'Design ambient: vacuum (0 bar).' in metin, metin
    assert ('Ground test at sea level (1.01325 bar): the nozzle separates '
            '(exit pressure 0.0566 bar') in metin, metin
    assert 'no sea-level thrust or Isp is published' in metin


def test_itki17_vakum_tasarimi_pdf_ortami_turkce_yazar():
    metin = _sivi_performans_metni('tr', DA_VAKUM)
    assert 'Tasarım ortamı: vakum (0 bar).' in metin, metin
    assert 'nozulda akış ayrılır (çıkış basıncı 0,0566 bar' in metin, metin
    assert 'Ground test' not in metin and 'Design ambient' not in metin


def test_itki17_deniz_seviyesi_tasariminda_ortam_satiri_yok():
    metin = _sivi_performans_metni('en', {'mode': 'sea_level',
                                          'is_sea_level': True,
                                          'pressure_bar': 1.01325})
    assert 'Design ambient' not in metin and 'Ground test' not in metin


# ===========================================================================
# M7-ITKI-3 / M7-ITKI-5 — katı: verimi VEREN ve tahmini TUTAN alan adıyla
# ===========================================================================
#: Mühendisin K8 adımları (alüminyumlu büyük motor: Ø200/80 × 400 mm,
#: 60 bar; boğaz 38,7 mm > SP-8039 alt sınırı 25,4 mm) — sayfanın bu
#: adımlarda gönderdiği gövdenin örnek gövdeden farkı (tarayıcıda yakalandı,
#: ``docs/scofield/raw/OH/V307/onarim-itki-b/betik/out_K8_istek.json``).
K8_FARK = {'outer_diameter': 200, 'burn_rate_a': 0.0022334, 'density': 1810,
           'chamber_pressure': 60, 'wet_mass': 22.525, 'dry_mass': 3.419,
           'web_thickness': 60,
           'propellant_name': 'HTPB/AP/Al Composite (aluminized)',
           'burn_rate_n': 0.35, 'propellant_type': 'htpb_ap_al',
           'grain_length': 400, 'burn_rate_preset': 'custom',
           'propellant_mass': 19.106, 'core_diameter': 80}


def _kati(*bos):
    os.environ.setdefault('HRMA_PROJECTS_DIR', os.path.expanduser(
        '~/HRMA-calisma/2026-11-19/ONARIM-ITKI-B/projeler'))
    from tests.support.kabul_sayfa_yukleri import SAYFA_YUKLERI
    from hrma.app import app
    yuk = dict(SAYFA_YUKLERI['solid'], **K8_FARK)
    for alan in bos:
        yuk.pop(alan)
    r = app.test_client().post('/calculate_solid', json=yuk)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


@pytest.fixture(scope='module')
def kati_k8():
    """Nozul Verimi ve Kinetik Verim boş; sayfa Cf 0,98 gönderir."""
    return _kati('nozzle_efficiency', 'kinetic_efficiency')


def test_itki5_deger_cf_alanindan_geliyorsa_cf_alani_adlandirilir(kati_k8):
    b = kati_k8['delivered_performance_basis']
    assert b['nozzle_efficiency_table']['source'] == 'request_field'
    assert b['nozzle_efficiency_table']['request_field'] == 'cf_efficiency'
    assert b['nozzle_efficiency_table']['value'] == pytest.approx(0.98)


def test_itki3_tahmini_tutan_alan_cf_olarak_yayimlanir_sayi_degismez(kati_k8):
    tp = kati_k8['delivered_performance_basis']['two_phase_loss']
    assert tp['applied_to_isp'] is False
    assert tp['not_applied_reason'] == 'request_efficiency_supplied'
    assert tp['not_applied_fields'] == ['cf_efficiency']
    # KARAR 0 (b) aynı: sayfa sayısı mühendisin ölçtüğüyle aynı (225,7 s).
    assert kati_k8['isp_sea_level'] == pytest.approx(225.67, abs=0.01)


def test_itki3_uc_alan_bossa_yerlesik_tahmin_uygulanir():
    """Mühendisin K12 kök doğrulaması: üç alan boş -> %4,30, Isp 217,06 s
    (el hesabı 225,67·(0,985/0,980)·(1−0,04302) = 217,07 s)."""
    d = _kati('nozzle_efficiency', 'kinetic_efficiency', 'cf_efficiency')
    tp = d['delivered_performance_basis']['two_phase_loss']
    assert tp['applied_to_isp'] is True
    assert tp['not_applied_fields'] == []
    assert tp['applied_loss_percent'] == pytest.approx(4.30, abs=0.01)
    assert d['isp_sea_level'] == pytest.approx(217.06, abs=0.01)


def _i18n_cifti(anahtar):
    import re
    yol = os.path.join(os.path.dirname(__file__), '..', 'hrma', 'static',
                       'js', 'i18n_pages.js')
    metin = open(yol, encoding='utf-8').read()
    return re.findall(r"^\s*'" + re.escape(anahtar)
                      + r"': '((?:[^'\\]|\\.)*)',?\s*$", metin, re.M)


def test_itki3_ekran_metni_alanlari_adlandirir_iki_alan_demez():
    en, tr = _i18n_cifti('solid.basis.two_phase_request_efficiency')
    assert '{fields}' in en and '{fields}' in tr
    assert 'Clear both fields' not in en and 'iki alanı da' not in tr
    en, tr = _i18n_cifti('solid.basis.nozzle_form_cf')
    assert en.startswith('Nozzle discharge efficiency (Cf) {value}')
    assert tr.startswith('Nozul boşalma verimi (Cf) {value}')
    yol = os.path.join(os.path.dirname(__file__), '..', 'hrma', 'templates',
                       'solid.html')
    sayfa = open(yol, encoding='utf-8').read()
    assert "n.request_field === 'cf_efficiency'" in sayfa
    assert 'not_applied_fields' in sayfa


# ===========================================================================
# M7-ITKI-2 — plaka hükmü: yarı-statik üst sınır + modellenmeyenler (EN+TR);
# hibrit uyarısında malzeme adı yok (TR'de İngilizce kalıyordu), malzeme
# ve hedef Tasarım Raporu'nda anahtarıyla
# ===========================================================================
def _sozluk_cifti(dosya, anahtar):
    import re
    yol = os.path.join(os.path.dirname(__file__), '..', 'hrma', 'static',
                       'js', dosya)
    metin = open(yol, encoding='utf-8').read()
    return re.findall(r"^\s*'" + re.escape(anahtar)
                      + r"': '((?:[^'\\]|\\.)*)',?\s*$", metin, re.M)


def test_itki2_sivi_plaka_hukmu_yari_statik_ve_kapsam_disini_soyler():
    en, tr = _sozluk_cifti('i18n_pages.js', 'liq.ui.injplate_analyzed')
    for parca in ('quasi-static upper bound', 'excludes pressure surges',
                  'Water hammer', 'dynamic amplification', 'thermal stress',
                  'fatigue'):
        assert parca in en, parca
    for parca in ('yarı-statik bir üst sınırdır', 'basınç darbeleri hariçtir',
                  'Su koçu', 'dinamik büyütme', 'ısıl gerilme', 'yorulma'):
        assert parca in tr, parca
    sayfa = open(os.path.join(os.path.dirname(__file__), '..', 'hrma',
                              'templates', 'liquid.html'),
                 encoding='utf-8').read()
    assert "'dynamic amplification, thermal stress and fatigue are not '" in sayfa


def test_itki2_hibrit_tasarim_raporu_kapsam_malzeme_hedef_satirlari():
    for anahtar in ('app.rep.plateScope', 'app.rep.plateScopeText',
                    'app.rep.plateMaterial', 'app.rep.plateTargetSf',
                    'app.rep.plateTargetSfMotor'):
        assert len(_sozluk_cifti('i18n_common.js', anahtar)) == 2, anahtar
    en, tr = _sozluk_cifti('i18n_common.js', 'app.rep.plateScopeText')
    assert 'quasi-static upper bound' in en and 'fatigue' in en
    assert 'yarı-statik üst sınır' in tr and 'yorulma' in tr
    js = open(os.path.join(os.path.dirname(__file__), '..', 'hrma', 'static',
                           'js', 'app.js'), encoding='utf-8').read()
    assert "'adv.mat.' + plk.material_key" in js
    assert 'T(plkMalzemeAnahtari, ' in js
    assert "T('app.rep.plateScope', 'Plate Check Scope')" in js


def test_itki2_iki_durumlu_plaka_uyarisinda_malzeme_adi_yok(
        hibrit_plaka_yaniti):
    uyarilar = hibrit_plaka_yaniti['injector']['plate_structural']['warnings']
    assert uyarilar, 'örnek 3 mm plaka hedefin altında: uyarı bekleniyordu'
    for u in uyarilar:
        assert u.endswith('mm given.'), u
        assert 'Stainless' not in u, u


def test_itki2_plaka_uyarisi_tr_ekranda_tam_turkce(tmp_path):
    from tests.test_d35_dil_safligi_a1 import (
        DUZENEK, NODE, en_kalinti, node_kos)
    if NODE is None:
        pytest.skip('node kurulu değil')
    duzenek = tmp_path / 'duzenek.js'
    duzenek.write_text(DUZENEK, encoding='utf-8')
    kaynak = ('Injector plate safety factor 0.20 is below the target 4.00 in '
              'the start/shutdown load case (face load 50.53 bar): 13.49 mm '
              'required, 3.00 mm given.')
    tr = node_kos(duzenek, tmp_path, serverTexts=[kaynak])['serverTr'][0]
    assert tr.startswith('Enjektör plakası emniyet katsayısı 0,20, marş/kesme'), tr
    assert '13,49 mm gerekli, 3,00 mm verildi.' in tr, tr
    assert not en_kalinti(tr), en_kalinti(tr)


# ===========================================================================
# M7-ITKI-18 — katı KONTROL kutusu iç itici anahtarını basmaz
# ===========================================================================
def test_itki18_propellant_parametreli_her_kati_kodu_yakit_adiyla_basilir():
    """i18n_common.js'te ``{propellant}`` taşıyan her ``warn.solid.*`` kodu
    solid.html ``YAKIT_PARAMETRELERI`` tablosunda: parametre ``solid.prop.*``
    adına çevrilir (ÖNCE: 'apcp_nonaluminized için NASA CEA termokimyası')."""
    import re
    kok = os.path.join(os.path.dirname(__file__), '..', 'hrma')
    sozluk = open(os.path.join(kok, 'static', 'js', 'i18n_common.js'),
                  encoding='utf-8').read()
    kodlar = set(re.findall(
        r"'(warn\.solid\.[a-z_]+)': '[^']*\{propellant\}", sozluk))
    assert 'warn.solid.thermochemistry_nominal_composition' in kodlar
    sayfa = open(os.path.join(kok, 'templates', 'solid.html'),
                 encoding='utf-8').read()
    bas = sayfa.index('const YAKIT_PARAMETRELERI = {')
    tablo = sayfa[bas:sayfa.index('};', bas)]
    eksik = sorted(k for k in kodlar
                   if not re.search(r"'" + re.escape(k)
                                    + r"': \[[^\]]*'propellant'", tablo))
    assert not eksik, eksik
    en, tr = _i18n_cifti('solid.prop.apcp_nonaluminized')
    assert tr == 'AP/HTPB Kompozit (alüminyumsuz)'


# ===========================================================================
# M7-ITKI-15 — TR teknik PDF: dayanak metinlerinde İngilizce / iç ad yok
# ===========================================================================
IC_AD = __import__('re').compile(r'\b[a-z]{2,}(?:_[a-z0-9]+)+\b')  # m_ox, p_e gibi simgeler hariç


@pytest.mark.parametrize('alan', ['burn_time_basis', 'isp_delivered_avg_basis',
                                  'oxidizer_mass_basis',
                                  'oxidizer_mass_inventory_basis'])
def test_itki15_hibrit_dayanak_metinleri_tr_pdfte_turkce_ve_ic_adsiz(
        hibrit_plaka_yaniti, alan):
    """ÖNCE (hibrit TR teknik PDF): 'Yanma süresinin dayanağı: DELIVERED
    quantities come from … burn_time = tank_blowdown.burn_duration_s …'.
    Metin çözücünün BU koşudaki cümlesidir (motor modülü değişirse bekçi
    kırmızı: sözlük karşılığı düşer)."""
    from hrma.export import rapor_sozluk
    en = hibrit_plaka_yaniti['motor'][alan]
    tr = rapor_sozluk.cevir(en, 'tr')
    assert tr != en, en[:80]
    from tests.test_d35_dil_safligi_a1 import en_kalinti
    assert not en_kalinti(tr), (alan, en_kalinti(tr))
    assert not IC_AD.findall(tr), (alan, IC_AD.findall(tr))
    assert 'DELIVERED' not in tr and 'LOADED' not in tr


def test_itki15_sivi_basinc_dusumu_kaynagi_ve_rapor_girisleri_ic_adsiz():
    from hrma.engines.liquid_rocket_engine import INJECTOR_DP_SOURCE_USER
    from hrma.export import rapor_sozluk
    assert rapor_sozluk.cevir(INJECTOR_DP_SOURCE_USER, 'tr') == (
        'kullanıcı girdisi (enjektör basınç düşümü)')
    for anahtar in ('report.unit.note_geometry', 'report.unit.src_geometry',
                    'report.lth.intro', 'report.inj.intro'):
        tr = rapor_sozluk.metin(anahtar, 'tr')
        assert tr and not IC_AD.findall(tr), (anahtar, IC_AD.findall(tr or ''))


def test_itki9_pdf_plaka_tablosu_hedefin_motordan_geldigini_soyler():
    from hrma.export import rapor_sozluk
    from hrma.export.pdf_generator import PDFReportGenerator
    b = {'status': 'analyzed', 'governing_load_case': 'startup_shutdown',
         'required_safety_factor': 4.0,
         'required_safety_factor_source': 'motor_design_target',
         'load_cases': {'operating': {}, 'startup_shutdown': {}}}
    for dil, parca in (('en', 'design safety-factor target of this motor'),
                       ('tr', 'bu motorun yapısal boyutlandırma hedefiyle')):
        gen = PDFReportGenerator(lang=dil)
        with rapor_sozluk.dil_baglami(dil):
            metin = _hikaye_metni(gen._injector_plate_table(b, 'hybrid_input'))
        assert parca in metin, (dil, metin[-400:])
    b['required_safety_factor_source'] = 'user'
    gen = PDFReportGenerator(lang='en')
    metin = _hikaye_metni(gen._injector_plate_table(b, 'hybrid_input'))
    assert 'design safety-factor target of this motor' not in metin


# M7-ITKI-18 PDF eşi + M7-ITKI-15: katı TR PDF'te itici anahtarı ve
# bileşim sözlüğü dökümü yok
def test_itki18_pdf_itici_tipi_kayit_adiyla():
    from hrma.export import rapor_sozluk
    from hrma.export.pdf_generator import PDFReportGenerator
    ad = PDFReportGenerator._solid_propellant_display(
        'solid', 'apcp_nonaluminized')
    assert ad == 'AP/HTPB Composite (non-aluminized)'
    assert rapor_sozluk.cevir(ad, 'tr') == 'AP/HTPB Kompozit (alüminyumsuz)'
    # Katı değilse ya da sözlükte yoksa değer aynen (uydurma yok).
    assert PDFReportGenerator._solid_propellant_display(
        'liquid', 'apcp_nonaluminized') == 'apcp_nonaluminized'
    assert PDFReportGenerator._solid_propellant_display(
        'solid', 'yok_boyle_itici') == 'yok_boyle_itici'


def test_itki15_pdf_nominal_bilesim_sozluk_dokumu_degil_cumle():
    from hrma.export import rapor_sozluk
    from hrma.export.pdf_generator import PDFReportGenerator
    ar = {'thermochemistry': {
        'source': 'nasa_cea', 'composition_key': 'apcp_nonaluminized',
        'nominal_composition': {'confidence': 'medium',
                                'note': 'nominal composition, HRMA choice'}}}
    for dil in ('en', 'tr'):
        gen = PDFReportGenerator(lang=dil)
        with rapor_sozluk.dil_baglami(dil):
            metin = _hikaye_metni(gen._create_thermochemistry_section(ar))
        assert "{'confidence'" not in metin, metin
        assert ('AP ~85' in metin), metin
    assert "HRMA'nın seçtiği nominal bileşim" in metin, metin


def test_itki18_pdf_kati_uyarisinda_itici_anahtari_yok():
    from hrma.export import rapor_sozluk
    from hrma.export.pdf_generator import PDFReportGenerator
    kayit = {'code': 'warn.solid.thermochemistry_nominal_composition',
             'params': {'propellant': 'apcp_nonaluminized'}}
    for dil, ad in (('en', 'AP/HTPB Composite (non-aluminized)'),
                    ('tr', 'AP/HTPB Kompozit (alüminyumsuz)')):
        with rapor_sozluk.dil_baglami(dil):
            cumle = PDFReportGenerator._warning_sentence(kayit)
        assert ad in cumle and 'apcp_nonaluminized' not in cumle, cumle
