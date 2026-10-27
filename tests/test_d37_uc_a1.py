# -*- coding: utf-8 -*-
"""ÖH D37 A1a uc-kapi a1 — uç sözleşmesi bekçileri (parça 1: kalem 1-3).

Kanıt: ``docs/scofield/raw/OH/A1a/uc-kapi/a1/`` (rapor.md, once/, sonra/,
mutasyon.md, patch/).

(a) OH-D32-02 — ÖK-21 uç yarısı, ``/calculate_liquid`` + ``/calculate_solid``:
    * ZORUNLU sınıf: alan silinince 422 + ``invalid_fields`` alanı ADIYLA anar
      (ölçülen sınıf: sıvıda itki / hazne basıncı / O/F + iki kimlik; katıda
      hazne basıncı + geometri kipinin üçlüsü). Bugün yeşil — kapı gevşerse
      kırmızı.
    * İSTEĞE BAĞLI sınıf (kanonik varsayılan + ``defaults_applied``): yalnız
      kanonik değeri formun eski ön-dolgusuna SAYICA EŞİT ölçülen alanlar.
      Uygulama ``patch/ok21_kanonik_kunye.patch`` — rapor §1.5 DUR'u ana
      model kararıyla çözüldü: yama ``hrma/app.py``ye UYGULANDI, çakışan dört
      bekçi "iddia alana bağlanır" desenine çevrildi (rapor §1.5 kapanışı).
      Bu sınıfın ``xfail(strict=True)`` işareti KALDIRILDI; testler yeşil.
(b) OH-AS-03 — çözülemeyen kimlikten güvenlik hükmü çıkmaz: üç negatif kimlik
    × üç yüzey (API / panel / PDF). API ayağı bu kulvarda onarıldı (tanınmayan
    motor tipi ADIYLA 400; depoda tanınmayan itici adı patlayıcı eksenini
    ADIYLA geri çeker). Panel ve PDF ayaklarının kırmızıları
    ``xfail(strict=True)`` + DEVİR A4.

PARÇA 2 (kalem 4-8):
(c) CM-H1 — hibrit ``/calculate``: plaka kalınlığı motorun ``injector_design``
    bloğuna YALNIZ kazanılmışsa (``request_value`` künyesiyle; ön-dolgu
    metinde adıyla) girer; kazanılmamışsa sayı yok + ``not_earned`` ve CAD
    girdisine kopyalanmaz. ``plate_structural`` üçüncü yolu (CM-H1c) yalnız
    ölçüldü — bekçi değil, DEVİR.
(d) B2-R4 — 6-DOF ``series_sampling`` (``series``in YANINDA; ad kümesi sabit;
    seri değerleri çözücünün ham değerleri, önce/sonra bit-aynı).
(e) OH-D30-12 sunucu ayağı — UQ ``conditionality`` gövdede (aynen; yoksa yok).
(f) OH-D37-T1 — bilinmeyen istek anahtarı künyesi: strict xfail + DEVİR.
"""
import json
import os
import re
import subprocess

import pytest

from hrma.engines.solid_rocket_engine import SOLID_DEFAULT_GEOMETRY_MM
from tests.support import form_defaults

from hrma.app import app

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SABLON = os.path.join(KOK, 'hrma', 'templates')
PANEL_JS = os.path.join(KOK, 'hrma', 'static', 'js', 'panels',
                        'safety_panel.js')

#: Küçük taban gövdeleri — D32 app-api-uc a1 ölçümüyle aynı (kıyaslanabilir).
UC_SIVI_TABAN = {'thrust': 10000.0, 'chamber_pressure': 30.0,
                 'mixture_ratio': 2.2, 'fuel_type': 'rp1',
                 'oxidizer_type': 'lox'}
# v3.0.1 T-ÇAPA-B: eski çekirdek 30 mm @ 40 bar port boğulan motordu
# (A_p/A_t 0,947) ve K-A kapısından beri 422 ``port_smaller_than_throat``.
# Bu dosyanın konusu künye/ön-dolgu, port boğulması değil: geometri tek
# tanım ``SOLID_DEFAULT_GEOMETRY_MM``den (değer kopyalanmaz).
UC_KATI_TABAN = {'propellant_type': 'apcp', 'chamber_pressure': 40.0,
                 **{k: float(v) for k, v in SOLID_DEFAULT_GEOMETRY_MM.items()}}

#: Ölçülen ZORUNLU sınıf (once/alan_alan.json ``zorunlu_422`` + sıvının
#: ``KRITIK_GIRDILER``i). Alan silinince 422 ve ad.
UC_SIVI_ZORUNLU = ('thrust', 'chamber_pressure', 'mixture_ratio',
                   'fuel_type', 'oxidizer_type')
UC_KATI_ZORUNLU = ('chamber_pressure', 'chamber_diameter', 'grain_length',
                   'core_diameter')

#: Ölçülen İSTEĞE BAĞLI + kanonik = eski ön-dolgu sınıfı (once/alan_alan.json
#: ``farksiz`` + ``sayica_farksiz``; kanonik değer ön-dolguya eşit olanlar).
#: ``fuel_heat_capacity`` (sıvı) ve ``web_thickness`` (katı) bilerek YOK:
#: ilkinin kanonik değeri motor durumunda tutulmuyor (soğutma modelinin yerel
#: tablosu), ikincisi çözücü çıktısıdır (``computed_by_solver``) — rapor §1.3.
UC_SIVI_KANONIK = ('chamber_roughness', 'coolant_flow_percent',
                   'coolant_inlet_temp', 'safety_factor',
                   'turbopump_efficiency')
UC_KATI_KANONIK = ('ambient_temp', 'erosive_m', 'liner_density',
                   'liner_thickness', 'outer_diameter', 'yield_strength',
                   'igniter_pressure_fraction')

@pytest.fixture(scope='module')
def istemci():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _post(istemci, yol, govde):
    r = istemci.post(yol, json=govde)
    return r.status_code, (r.get_json() or {})


def _kunye(govde):
    return {k.get('field'): k for k in (govde.get('defaults_applied') or [])
            if isinstance(k, dict)}


def _sayisal_yapraklar(x, yol='', out=None):
    """Yayımlanan SAYI/bool/None yaprakları (künye metinleri hariç)."""
    if out is None:
        out = {}
    if isinstance(x, dict):
        for k, v in x.items():
            if not yol and k in ('defaults_applied', 'input_source'):
                continue
            _sayisal_yapraklar(v, yol + '/' + str(k), out)
    elif isinstance(x, list):
        for i, v in enumerate(x):
            _sayisal_yapraklar(v, '%s[%d]' % (yol, i), out)
    elif not isinstance(x, str):
        out[yol] = x
    return out


def _on_dolgu(sablon, alan):
    t = open(os.path.join(SABLON, sablon), encoding='utf-8').read()
    for m in re.finditer(r'<input\b[^>]*>', t):
        e = m.group(0)
        if re.search(r'\bid\s*=\s*"%s"' % re.escape(alan), e):
            v = re.search(r'\bvalue\s*=\s*"([^"]+)"', e)
            return float(v.group(1)) if v else None
    return None


# ===========================================================================
# (a) OH-D32-02 — ZORUNLU sınıf: 422 + alan adı
# ===========================================================================
class TestOHD3202ZorunluAlanAdiylaReddedilir:

    @pytest.mark.parametrize('alan', UC_SIVI_ZORUNLU)
    def test_sivi_zorunlu_alan_silinince_422_ve_ad(self, istemci, alan):
        kod, j = _post(istemci, '/calculate_liquid',
                       {k: v for k, v in UC_SIVI_TABAN.items() if k != alan})
        assert kod == 422, (alan, kod)
        assert alan in {r.get('field') for r in j.get('invalid_fields') or []}
        assert 'defaults_applied' not in j

    @pytest.mark.parametrize('alan', UC_KATI_ZORUNLU)
    def test_kati_zorunlu_alan_silinince_422_ve_ad(self, istemci, alan):
        kod, j = _post(istemci, '/calculate_solid',
                       {k: v for k, v in UC_KATI_TABAN.items() if k != alan})
        assert kod == 422, (alan, kod)
        assert alan in {r.get('field') for r in j.get('invalid_fields') or []}
        assert 'defaults_applied' not in j


# ===========================================================================
# (a) OH-D32-02 — İSTEĞE BAĞLI sınıf: kanonik + defaults_applied
# ===========================================================================
_KANONIK_VAKALAR = (
    [('/calculate_liquid', UC_SIVI_TABAN, 'liquid.html', a) for a in UC_SIVI_KANONIK]
    + [('/calculate_solid', UC_KATI_TABAN, 'solid.html', a) for a in UC_KATI_KANONIK])


@pytest.mark.parametrize('yol,taban,sablon,alan', _KANONIK_VAKALAR,
                         ids=[v[3] for v in _KANONIK_VAKALAR])
def test_gonderilmeyen_alan_kanonik_degeriyle_kunyede(istemci, yol, taban,
                                                      sablon, alan):
    """Alan silinince 200 + künye ADIYLA ve DEĞERİYLE; değer ön-dolguya eşit
    (ÖNEMLİ kapısı: kanonik ≠ ön-dolgu olan alan bu sınıfa giremez) ve
    beyan edilen değer açıkça gönderildiğinde yayımlanan HİÇBİR sayı
    değişmez (beyan = kullanılan)."""
    govde = {k: v for k, v in taban.items() if k != alan}
    kod, j = _post(istemci, yol, govde)
    assert kod == 200, kod
    kunye = _kunye(j).get(alan)
    assert kunye is not None, '%s gönderilmedi ama künyede yok' % alan
    assert kunye['reason'] == 'endpoint_default'
    assert kunye['value'] == pytest.approx(_on_dolgu(sablon, alan),
                                           rel=1e-12), (
        'kanonik değer eski ön-dolgudan farklı: ÖNEMLİ sınıf (Sunum 1)')
    kod2, j2 = _post(istemci, yol, dict(govde, **{alan: kunye['value']}))
    assert kod2 == 200
    assert alan not in _kunye(j2), 'gönderilen alan künyede sayılıyor'
    assert _sayisal_yapraklar(j) == _sayisal_yapraklar(j2), (
        'beyan edilen değer çözücünün kullandığı değer değil')


# ===========================================================================
# (b) OH-AS-03 — çözülemeyen kimlik × API / panel / PDF
# ===========================================================================
AS03_GOVDE = {'chamber_pressure': 50, 'propellant_mass': 50,
          'chamber_diameter': 0.1, 'wall_thickness': 0.005}
AS03_PDF_GOVDE = {'chamber_pressure': 50.0, 'chamber_diameter': 0.1,
             'propellant_mass': 50.0,
             'chamber_wall_policy': {'wall_thickness_m': 0.005}}
AS03_NEGATIF = {
    'N1_motor': {'motor_type': 'warp_drive', 'propellant_type': 'apcp'},
    'N2_itici': {'motor_type': 'solid', 'propellant_type': 'unobtainium'},
    'N3_oksitleyici': {'motor_type': 'hybrid',
                       'oxidizer_type': 'unobtainium'},
}
AS03_POZITIF = {
    'P1_kati_apcp': {'motor_type': 'solid', 'propellant_type': 'apcp'},
    'P2_hibrit_n2o': {'motor_type': 'hybrid', 'oxidizer_type': 'n2o'},
    'P3_sivi_ad': {'motor_type': 'liquid',
                   'propellant_type': 'RP-1/LOX (Kerosene/Liquid Oxygen)'},
    'P4_toksik_ad': {'motor_type': 'liquid', 'propellant_type': 'n2o4_mmh'},
}
# DEVİR OH-AS-03 panel ayağı KAPANDI (panel-js 5. tur, 14 Eki; ana model
# çevirisi, dört koşul): safety_panel.js fromResults itici sınıfını motorun
# KENDİ iticisinden türetiyor, tanınmayan itici/oksitleyici 'not_modelled'
# gidiyor (tests/test_d37_panel_js_t5_guvenlik_sinifi.py). N2/N3 strict xfail
# XPASS verdiği için im kaldırıldı; beklenti (panel hüküm ÜRETMEZ) aynı,
# eski 'composite' eşlemesi geri gelirse bu düğümler KIRMIZI olur.
# DEVİR OH-AS-03 PDF ayağı da KAPANDI (panel-js 6. tur, 14 Eki; dört koşul):
# (1) im, kapanan 'belge çözülemeyen itici/oksitleyici adını motor tipi
# yedeğiyle ürün sınıfına çeviriyor' devrinden türemişti ve strict XPASS
# verdi; (2) kâhin aynı beklenti (belge tanınmayan iticide/oksitleyicide
# hüküm ÜRETMEZ) + panelin katı kuralı (katalog ailesi; panel-js 5. tur
# bekçisi) + ucun 400 oksitleyici kapısı; (3) tolerans yok; (4) yorum + rapor
# satırı. Ters mutasyon (eski 'composite' yedeği / varsayılan oksitleyici)
# N2/N3'ü KIRMIZI yapar (docs/scofield/raw/OH/A1b/panel-js/a1/mutasyon.md).


def _hukum(explosive):
    e = explosive or {}
    return bool(isinstance(e.get('tnt_equivalent_kg'), (int, float))
                or e.get('blast_distances') or e.get('explosive_class'))


def _api_hukum(istemci, kimlik):
    kod, j = _post(istemci, '/analyze_safety', dict(AS03_GOVDE, **kimlik))
    e = (j.get('safety_analysis') or {}).get('explosive_hazards') or {}
    return kod, j, _hukum(e)


#: Negatif kimliklerin BİLİNMEYEN alanı ve değeri (ret ya da geri çekme
#: gerekçesi onu ADIYLA anmak zorunda).
AS03_BILINMEYEN = {
    'N1_motor': ('motor_type', 'warp_drive'),
    'N2_itici': ('propellant_type', 'unobtainium'),
    'N3_oksitleyici': ('oxidizer_type', 'unobtainium'),
}


class TestOHAS03ApiAyagi:

    @pytest.mark.parametrize('ad', sorted(AS03_NEGATIF))
    def test_bilinmeyen_kimlik_hukum_URETMEZ_ve_ADIYLA_anilir(
            self, istemci, ad):
        """İki meşru biçim: kapalı sözlük (motor tipi, oksitleyici) ADIYLA
        4xx; serbest metin itici adı 200 + patlayıcı ekseni ADIYLA geri
        çekilir (ucun eksen-bazlı sözleşmesi, Z5S)."""
        alan, deger = AS03_BILINMEYEN[ad]
        kod, j, hukum = _api_hukum(istemci, AS03_NEGATIF[ad])
        assert not hukum, '%s: çözülemeyen kimlikten TNT/mesafe hükmü' % ad
        if kod == 200:
            e = (j.get('safety_analysis') or {}).get(
                'explosive_hazards') or {}
            neden = str(e.get('explosive_verdict_withheld_because') or '')
            assert alan in neden and repr(deger) in neden, (
                'geri çekme gerekçesi eksik kimliği ADIYLA anmıyor: %r'
                % neden)
            assert "no motor_type was supplied" not in neden, (
                'gerekçe kullanıcının GÖNDERDİĞİ motor tipini yok sayıyor')
        else:
            assert 400 <= kod < 500, kod
            assert j.get('field') == alan, (
                'ret gövdesi eksik kimliği ADIYLA anmıyor: %r' % j)
            assert j.get('accepted_values'), 'kabul edilen değerler yok'

    def test_serbest_metin_iticide_kardes_eksenler_ESIRGENMEZ(self, istemci):
        """Eksen-bazlı sözleşme: yalnız patlayıcı ekseni geri çekilir."""
        kod, j, _h = _api_hukum(istemci, AS03_NEGATIF['N2_itici'])
        assert kod == 200, kod
        s = j.get('safety_analysis') or {}
        assert (s.get('pressure_safety') or {}).get('vessel_status'), (
            'basınç ekseni de düştü — geri çekme eksen-bazlı değil')

    @pytest.mark.parametrize('ad', sorted(AS03_POZITIF))
    def test_taninan_kimlik_hukmunu_KAZANIR(self, istemci, ad):
        """Kapı körlemesine ret değildir: depoca tanınan ad geçer."""
        kod, _j, hukum = _api_hukum(istemci, AS03_POZITIF[ad])
        assert kod == 200, (ad, kod)
        if ad != 'P4_toksik_ad':
            assert hukum, '%s: tanınan kimlik hükmünü kaybetti' % ad


NODE_SARMAL = r"""
const fs = require('fs');
const MT = process.argv[3];
const R = JSON.parse(process.argv[4]);
let cfg = null;
const ui = new Proxy({}, {get: (t, k) => {
  if (k === 't') return (x) => x;
  if (k === 'motorDict') return () => (R.motor || {});
  return () => undefined;
}});
global.window = {AnalysisDock: {ui: ui, register: (c) => { cfg = c; },
                                getMotorType: () => MT}};
eval(fs.readFileSync(process.argv[2], 'utf8'));
const sug = cfg.fromResults(R);
process.stdout.write(JSON.stringify({
  motor_type: sug.motor_type, propellant_type: sug.propellant_type,
  oxidizer_type: sug.oxidizer_type}));
"""


def _panel_hukum(istemci, kimlik, tmp_path):
    """Panelin GÖNDERECEĞİ kimlik (node'da ``fromResults``) → uç → hüküm."""
    motor = {k: v for k, v in kimlik.items() if k != 'motor_type'}
    motor['propellant_name'] = kimlik.get('propellant_type')
    yol = tmp_path / 'panel.js'
    yol.write_text(NODE_SARMAL, encoding='utf-8')
    c = subprocess.run(['node', str(yol), PANEL_JS, kimlik['motor_type'],
                        json.dumps({'motor': motor})],
                       capture_output=True, text=True, timeout=60)
    assert c.returncode == 0, c.stderr[-800:]
    gonderilen = {k: v for k, v in json.loads(c.stdout).items()
                  if v not in (None, '')}
    return _api_hukum(istemci, gonderilen)[2]


class TestOHAS03PanelAyagi:

    def test_N1_bilinmeyen_motor_panelde_hukum_URETMEZ(self, istemci,
                                                        tmp_path):
        assert not _panel_hukum(istemci, AS03_NEGATIF['N1_motor'], tmp_path)

    def test_N2_bilinmeyen_itici_panelde_hukum_URETMEZ(self, istemci,
                                                        tmp_path):
        assert not _panel_hukum(istemci, AS03_NEGATIF['N2_itici'], tmp_path)

    def test_N3_bilinmeyen_oksitleyici_panelde_hukum_URETMEZ(self, istemci,
                                                              tmp_path):
        assert not _panel_hukum(istemci, AS03_NEGATIF['N3_oksitleyici'],
                                tmp_path)


def _pdf_hukum(kimlik):
    from hrma.export import pdf_safety
    safety, _k = pdf_safety.build_pdf_safety(dict(AS03_PDF_GOVDE, **kimlik), {})
    return _hukum((safety or {}).get('explosive_hazards'))


class TestOHAS03PdfAyagi:

    def test_N1_bilinmeyen_motor_belgede_hukum_URETMEZ(self):
        assert not _pdf_hukum(AS03_NEGATIF['N1_motor'])

    def test_N2_bilinmeyen_itici_belgede_hukum_URETMEZ(self):
        assert not _pdf_hukum(AS03_NEGATIF['N2_itici'])

    def test_N3_bilinmeyen_oksitleyici_belgede_hukum_URETMEZ(self):
        assert not _pdf_hukum(AS03_NEGATIF['N3_oksitleyici'])

    def test_pozitif_denetim_belge_taninan_kimlikte_hukum_verir(self):
        """Negatif bekçiler körlemesine yeşil değil: tanınan kimlik hüküm
        alıyor (belge yolu çalışıyor)."""
        assert _pdf_hukum(AS03_POZITIF['P1_kati_apcp'])


# ###########################################################################
# PARÇA 2 (kalem 4-8) — (c) CM-H1 · (d) B2-R4 · (e) OH-D30-12 · (f) OH-D37-T1
# ###########################################################################
import contextlib  # noqa: E402
import hashlib  # noqa: E402
import io  # noqa: E402

from tests.support.kanit import kanit_gerekli  # noqa: E402

KANIT = 'docs/scofield/raw/OH/A1a/uc-kapi/a1'

#: Ornek-H1 — ``tests/test_d35_onemli_hibrit_fizik_a1.py`` ORNEK_H1 ile aynı
#: (Cowork 21 Eyl motoru + gizli panelin alanları; ``injector_material``
#: dâhil). ``plate_thickness`` BİLEREK yok: API/elle gövde yolu.
CMH1_ORNEK_H1 = {
    'thrust': 1000.0, 'burn_time': 10.0, 'chamber_pressure': 20.0,
    'of_ratio': 7.5, 'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
    'tank_pressure': 50.0, 'injector_type': 'showerhead',
    'injector_material': 'stainless_steel', 'chamber_material': 'steel_304',
    'wall_thickness': 5.0, 'safety_factor': 4.0, 'pressure_drop': 4.0,
}
CMH1_KOSULLAR = {
    'plaka_on_dolgu': dict(CMH1_ORNEK_H1, plate_thickness=3.0),
    'plakasiz': dict(CMH1_ORNEK_H1),
    'plakasiz_malzemesiz': {k: v for k, v in CMH1_ORNEK_H1.items()
                            if k != 'injector_material'},
}


@pytest.fixture(scope='module')
def cmh1():
    """Üç koşulun yanıtı + CAD üreticisine VERİLEN ``injector_results``.

    CAD girdisi casusla okunur (yanıtta ``cad_input`` yoktur); casus modül
    sonunda geri alınır.
    """
    import hrma.app as A
    asil = A.cad_designer.generate_3d_motor_assembly
    yakalanan = {}

    def casus(md, *a, **k):
        yakalanan['injector_results'] = (
            dict(md.get('injector_results'))
            if isinstance(md.get('injector_results'), dict) else None)
        return asil(md, *a, **k)

    A.cad_designer.generate_3d_motor_assembly = casus
    out = {}
    try:
        app.config['TESTING'] = True
        with app.test_client() as c:
            for ad, govde in CMH1_KOSULLAR.items():
                yakalanan.clear()
                with contextlib.redirect_stdout(io.StringIO()), \
                        contextlib.redirect_stderr(io.StringIO()):
                    r = c.post('/calculate', json=govde)
                assert r.status_code == 200, (ad, r.get_data(as_text=True)[:300])
                out[ad] = (r.get_json(), dict(yakalanan))
    finally:
        A.cad_designer.generate_3d_motor_assembly = asil
    return out


# ===========================================================================
# (c) CM-H1 — plaka kalınlığı motor enjektör bloğuna yalnız kazanılmışsa
# ===========================================================================
class TestCMH1PlakaKalinligiKunyesi:

    def test_on_dolgu_kopyalanir_request_value_ile(self, cmh1):
        j, _cad = cmh1['plaka_on_dolgu']
        assert j['injector']['plate_thickness_earned'] is True
        for blok in (j['injector_design'], j['motor']['injector_design']):
            assert blok['plate_thickness_mm'] == 3.0
            # Sayı enjektör çözümünün KENDİ sayısıdır (ikinci kaynak yok).
            assert blok['plate_thickness_mm'] == j['injector']['plate_thickness']
            assert blok['plate_thickness_source'] == 'request_value'
            assert blok['plate_thickness_source'] != 'user_supplied'

    def test_basis_sablonun_on_dolgusunu_aniyor(self, cmh1):
        """Metin ŞABLONUN gerçek ön-dolgusuyla eşlenir: A6b K6-h ön-dolguyu
        söktüğünde (ya da değer değiştiğinde) bu bekçi kırmızıya döner ve
        künye metni güncellenir — bayat beyan kalmaz."""
        on_dolgu = _on_dolgu('advanced.html', 'plate_thickness')
        assert on_dolgu == 3.0, on_dolgu
        j, _cad = cmh1['plaka_on_dolgu']
        metin = j['injector_design']['plate_thickness_basis']
        assert 'pre-fill' in metin
        assert 'value="%s"' % _on_dolgu_ham('advanced.html',
                                            'plate_thickness') in metin
        assert 'not user_supplied' in metin

    @pytest.mark.parametrize('kosul', ['plakasiz', 'plakasiz_malzemesiz'])
    def test_kazanilmamis_kalinlik_bloga_girmez(self, cmh1, kosul):
        j, _cad = cmh1[kosul]
        assert j['injector']['plate_thickness_earned'] is False
        for blok in (j['injector_design'], j['motor']['injector_design']):
            assert 'plate_thickness_mm' not in blok, blok
            assert blok['plate_thickness_source'] == 'not_earned'

    def test_kazanilmis_kalinlik_cad_girdisine_gider(self, cmh1):
        _j, cad = cmh1['plaka_on_dolgu']
        assert cad['injector_results']['plate_thickness'] == 3.0

    @pytest.mark.parametrize('kosul', ['plakasiz', 'plakasiz_malzemesiz'])
    def test_kazanilmamis_kalinlik_cad_girdisine_KOPYALANMAZ(self, cmh1, kosul):
        j, cad = cmh1[kosul]
        assert isinstance(cad['injector_results'], dict)
        assert 'plate_thickness' not in cad['injector_results']
        # Yanıttaki ``injector`` bloğu DEĞİŞMEDİ (kopya süzüldü).
        assert j['injector']['plate_thickness'] == 3.0

    def test_malzemesiz_plakasiz_cizim_panel_kalinligi_okumuyor(self, cmh1):
        """``plate_structural`` üretilmeyen koşulda CAD'in ikinci okuma yolu
        (``injector_results.plate_thickness``) kapandı: çizim plakayı
        panelin kazanılmamış kalınlığından kurmuyor (fail-closed)."""
        j, _cad = cmh1['plakasiz_malzemesiz']
        cizim = j['cad_design']['technical_drawings']['injector']
        assert not str(cizim['plate_thickness_source']).startswith(
            'injector panel'), cizim['plate_thickness_source']


def _on_dolgu_ham(sablon, alan):
    t = open(os.path.join(SABLON, sablon), encoding='utf-8').read()
    for m in re.finditer(r'<input\b[^>]*>', t):
        e = m.group(0)
        if re.search(r'\bid\s*=\s*"%s"' % re.escape(alan), e):
            v = re.search(r'\bvalue\s*=\s*"([^"]+)"', e)
            return v.group(1) if v else None
    return None


# ===========================================================================
# (d) B2-R4 — 6-DOF ``series_sampling`` künyesi (series'in YANINDA)
# ===========================================================================
SIXDOF_GOVDE = {'dry_mass': 20.0, 'propellant_mass': 10.0,
                'thrust': 3000.0, 'burn_time': 5.0}
#: ``series`` bloğunun bugünkü anahtar kümesi (D25 OH-D24-16 ``altitude_datum``
#: dâhil). Künye bu kümeye GİRMEZ.
SIXDOF_SERIES_ANAHTARLARI = {'time', 'altitude', 'north', 'east', 'speed',
                             'mach', 'alpha_deg', 'altitude_datum'}
SIXDOF_SAMPLING_ADLARI = {'decimated', 'n_total', 'n_returned', '_basis'}


@pytest.fixture(scope='module')
def sixdof():
    """İki koşu (uzun: seyreltilir; ``t_max = 1 s``: seyreltilmez) + casusla
    okunan çözücü ham çıktısı."""
    from hrma.analysis import six_dof_trajectory as S6
    asil = S6.SixDOFTrajectory.solve
    ham = {}

    def casus(self, *a, **k):
        r = asil(self, *a, **k)
        ham['res'] = r
        return r

    S6.SixDOFTrajectory.solve = casus
    out = {}
    try:
        app.config['TESTING'] = True
        with app.test_client() as c:
            for ad, g in (('uzun', dict(SIXDOF_GOVDE)),
                          ('kisa', dict(SIXDOF_GOVDE, t_max=1.0))):
                ham.clear()
                r = c.post('/api/six-dof-analysis', json=g)
                assert r.status_code == 200, r.get_data(as_text=True)[:300]
                out[ad] = (r.get_json(), ham['res'])
    finally:
        S6.SixDOFTrajectory.solve = asil
    return out


class TestB2R4SeriesSampling:

    def test_ad_kumesi_sabit_ve_series_yaninda(self, sixdof):
        for ad in ('uzun', 'kisa'):
            j, _res = sixdof[ad]
            assert set(j['series_sampling']) == SIXDOF_SAMPLING_ADLARI
            assert set(j['series']) == SIXDOF_SERIES_ANAHTARLARI, (
                'series bloğunda yeni anahtar doğdu: %s'
                % sorted(set(j['series']) - SIXDOF_SERIES_ANAHTARLARI))

    def test_uzun_seri_seyreltildigini_soyler(self, sixdof):
        j, res = sixdof['uzun']
        s = j['series_sampling']
        n = len(res['time'])
        assert n > 300, n
        assert s['decimated'] is True
        assert s['n_total'] == n
        assert s['n_returned'] == len(j['series']['time']) == 300

    def test_kisa_seri_seyreltilmedigini_soyler(self, sixdof):
        j, res = sixdof['kisa']
        s = j['series_sampling']
        n = len(res['time'])
        assert n <= 300, n
        assert s['decimated'] is False
        assert s['n_total'] == s['n_returned'] == n == len(j['series']['time'])

    @pytest.mark.parametrize('ad', ['uzun', 'kisa'])
    def test_seri_degerleri_cozucunun_ham_degerleri(self, sixdof, ad):
        """Seri değerleri çözücünün ham dizisinden, künyenin ``_basis``inde
        yazılı kuralla (``linspace(0, n-1, min(300, n))`` → int) alınmış
        değerlerdir; künye sayılara dokunmaz."""
        import numpy as np
        j, res = sixdof[ad]
        n = len(res['time'])
        idx = np.linspace(0, n - 1, min(300, n)).astype(int)
        assert j['series']['time'] == res['time'][idx].tolist()
        assert j['series']['altitude'] == res['altitude'][idx].tolist()
        assert j['series']['north'] == res['position'][0][idx].tolist()
        assert j['series']['mach'] == res['mach'][idx].tolist()
        assert '300' in j['series_sampling']['_basis']

    def test_seri_once_sonra_bit_ayni(self, sixdof):
        """Kanıttaki ÖNCE ölçümünün (dal ``9ea1dfc4``) seri sha256'ları ile
        bugünkü yanıt eşit."""
        yol = kanit_gerekli(os.path.join(KOK, KANIT, 'once', 'b2r4.json'))
        once = json.load(open(yol, encoding='utf-8'))['sixdof']
        for ad, anahtar in (('uzun', 'uzun'), ('kisa', 'kisa_t_max_1s')):
            j, _res = sixdof[ad]
            simdi = {k: hashlib.sha256(json.dumps(v).encode()).hexdigest()
                     for k, v in sorted(j['series'].items())}
            assert simdi == once[anahtar]['series_sha256'], ad


# ===========================================================================
# (e) OH-D30-12 sunucu ayağı — UQ ``conditionality`` gövdede
# ===========================================================================
UQ_GOVDE = {'motor_type': 'hybrid', 'level': 'fast', 'n_samples': 30,
            'seed': 7,
            'inputs': {'thrust': 1000.0, 'burn_time': 10.0,
                       'chamber_pressure': 20.0, 'of_ratio': 7.5,
                       'fuel_type': 'htpb', 'oxidizer_type': 'n2o'}}


class TestOHD3012UqKosulluluk:

    def test_uc_cekirdegin_kosulluluk_blogunu_tasiyor(self, istemci):
        from hrma.analysis import uncertainty as U
        yakalanan = {}
        asil = U.run_uncertainty

        def casus(*a, **k):
            r = asil(*a, **k)
            yakalanan['c'] = r.get('conditionality')
            return r

        U.run_uncertainty = casus
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                r = istemci.post('/api/uncertainty-analysis', json=UQ_GOVDE)
        finally:
            U.run_uncertainty = asil
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        j = r.get_json()
        assert isinstance(yakalanan.get('c'), dict)
        # Aynen taşınır: sayı üretilmez, blok çekirdeğinkidir.
        assert j['conditionality'] == json.loads(json.dumps(yakalanan['c']))

    def test_cekirdek_blok_vermezse_alan_KONMAZ(self):
        from hrma.app import _uq_contract_body
        sonuc = {
            'outputs': {}, 'sensitivity': {'per_output': {}},
            'n_samples': 2, 'failed_samples': 0, 'seed': 1,
            'timing': {'wall_s': 0.0},
            'consistency': {'mean_shift_percent': 0.0, 'note': None},
            'sampler': 'lhs', 'uq_version': 'test', 'inputs_used': []}
        assert 'conditionality' not in _uq_contract_body('hybrid', 'fast',
                                                         sonuc)
        sonuc['conditionality'] = 'metin'           # sözlük değil
        assert 'conditionality' not in _uq_contract_body('hybrid', 'fast',
                                                         sonuc)


# ===========================================================================
# (f) OH-D37-T1 — bilinmeyen istek anahtarı sessizce yutuluyor (DEVİR)
# ===========================================================================
#: Ölçüldü (``once/t1.json``, dal ``9ea1dfc4``): üç uçta da bilinmeyen anahtar
#: yanıtı BİT-AYNI bırakıyor ve adı yanıtın hiçbir yerinde geçmiyor. Künye
#: (``unrecognized_request_keys``) bu kulvarda EKLENMEDİ: "tanınan anahtar"
#: kümesinin tek kaynağı yok — istek sözlüğü üç uçta 27 ayrı çağrı hedefine
#: (13 / 8 / 6; ikisi motor kurucusu: ``LiquidRocketEngine(overrides=data)``
#: ve ``_build_solid_engine(data)``) geçiyor (rapor §T1); elle beyaz liste
#: ikinci kaynak olur, erişim izleme ise bütün bu tüketicilerin denetimini
#: ister. Onarılınca strict xfail kırmızıya döner, işaret kaldırılır.
DEVIR_T1 = pytest.mark.xfail(
    strict=True,
    reason=('DEVİR OH-D37-T1 (A1a uc-kapi a1 rapor §T1): bilinmeyen istek '
            'anahtarı künyesiz yutuluyor; tanınan-anahtar kümesinin tek '
            'kaynağı yok — onarım ayrı kalem.'))

T1_VAKALAR = [
    pytest.param('/calculate_liquid',
                 dict(UC_SIVI_TABAN, engine_cycle='staged_combustion'),
                 'preburner_mode', id='sivi_preburner_mode'),
    pytest.param('/calculate_solid', dict(UC_KATI_TABAN),
                 'zz_bilinmeyen_anahtar', id='kati_uydurma'),
    pytest.param('/calculate',
                 {'thrust': 1000.0, 'burn_time': 10.0,
                  'chamber_pressure': 20.0, 'of_ratio': 7.5,
                  'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
                  'tank_pressure': 50.0, 'injector_type': 'showerhead',
                  'generate_cad': False},
                 'chamber_presure', id='hibrit_yazim_hatasi'),
]


@DEVIR_T1
@pytest.mark.parametrize('yol,govde,anahtar', T1_VAKALAR)
def test_bilinmeyen_istek_anahtari_ADIYLA_anilir(istemci, yol, govde, anahtar):
    g = dict(govde)
    g[anahtar] = 'ox_rich' if anahtar == 'preburner_mode' else 1
    with contextlib.redirect_stdout(io.StringIO()):
        kod, j = _post(istemci, yol, g)
    assert kod == 200, (kod, j)
    assert anahtar in (j.get('unrecognized_request_keys') or []), sorted(j)[:40]

# ---------------------------------------------------------------------------
# (a) ek — denetçi şartları Ş1-Ş3 (ana model, 25 Eyl)
# ---------------------------------------------------------------------------
def test_bekci_listesi_okuyucu_tablosuyla_ayni():
    """Ş1: künye bekçisinin gezdiği alan kümesi uçtaki okuyucu tablosunun
    TAMAMIDIR — tabloya bekçisiz alan eklenemez (beyan = kullanılan her
    alan için ölçülsün)."""
    import hrma.app as uc
    assert set(UC_SIVI_KANONIK) == set(uc._SIVI_KANONIK_VARSAYILAN_OKUYUCULARI)
    assert set(UC_KATI_KANONIK) == set(uc._KATI_KANONIK_VARSAYILAN_OKUYUCULARI)


def test_basinc_beslemede_pompa_verimi_kunyelenmez(istemci):
    """Ş2: basınç beslemeli çevrimde pompa yok → turbopump_efficiency
    künyede YOK; kalan dört kanonik alan VAR."""
    # v3.0.1 T-ÇAPA-B: basınç beslemede ``feed_pressure`` gönderilmezse uç
    # 422 ``pressure_fed_feed_pressure_not_supplied`` döner (L-A SV-03).
    # Konu pompa verimi künyesi: sayfanın gönderdiği şablon varsayılanı
    # verilir (tek kaynak, kopyalanmaz).
    kod, j = _post(istemci, '/calculate_liquid',
                   dict(UC_SIVI_TABAN, engine_cycle='pressure_fed',
                        feed_pressure=form_defaults.sayisal_varsayilanlar(
                            'liquid')['feed_pressure']))
    assert kod == 200, j
    k = _kunye(j)
    assert 'turbopump_efficiency' not in k
    for alan in ('chamber_roughness', 'coolant_flow_percent',
                 'coolant_inlet_temp', 'safety_factor'):
        assert alan in k, alan


@pytest.mark.parametrize('sogutma', ['ablative', 'radiative'])
def test_pasif_sogutmada_puruzluluk_kullanilmaz_ve_kunyelenmez(istemci,
                                                              sogutma):
    """Ş3: pasif soğutmada kanal pürüzlülüğü hiçbir sayıya girmez (açıkça
    farklı bir değer göndermek yayımlanan sayısal yaprakları değiştirmez)
    ve bu yüzden künyede YOK — "uygulanmayan varsayılan sayılmaz"."""
    govde = dict(UC_SIVI_TABAN, cooling_type=sogutma)
    kod, j = _post(istemci, '/calculate_liquid', govde)
    assert kod == 200
    assert 'chamber_roughness' not in _kunye(j)
    kod2, j2 = _post(istemci, '/calculate_liquid',
                     dict(govde, chamber_roughness=25.0))
    assert kod2 == 200
    assert _sayisal_yapraklar(j) == _sayisal_yapraklar(j2), (
        'pürüzlülük pasif soğutmada bir sayıya giriyor — künye kararı yanlış')
