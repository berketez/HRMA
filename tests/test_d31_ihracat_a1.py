# -*- coding: utf-8 -*-
"""ÖH D31 / ihracat a1 — onarım bekçileri.

Her sınıf, ölçülmüş bir kusurun geri gelmesini görür.
Ölçümler: docs/scofield/raw/OH/D31/ihracat/a1/once_p9b321.json,
sonra_p9b321.json, sonra_failclosed.json
Ters-mutasyon kanıtı: docs/scofield/raw/OH/D31/ihracat/a1/mutasyon.json
"""
import ast
import contextlib
import io
import json
import os

import pytest


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


@pytest.fixture(scope='module')
def istemci():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _pdf_metni(bayt):
    from pypdf import PdfReader
    return '\n'.join((p.extract_text() or '')
                     for p in PdfReader(io.BytesIO(bayt)).pages)


# ==========================================================================
# P9B3-21 — PDF'in güvenlik bölümü besleniyor (sunucuda TEK KOŞUM)
# ==========================================================================
class TestP9B321GuvenlikBeslemesi:
    """ÖLÇÜLEN KUSUR (taban 9d70e9ed, once_p9b321.json):

    Ürünün PDF indiren DÖRT yeri de gövdeye ``safety`` koymuyor (4/4) ve üç
    motor tipinin GERÇEK sayfa yüküyle üretilen ``complete`` raporunda
    güvenlik bölümü 3/3 koşumda "NOT EVALUATED IN THIS RUN" diyor, altı
    tehlike bloğunun 0'ı basılıyordu.
    """

    #: Sayfa yüklerinin ÖLÇÜLMÜŞ biçimleri (once_p9b321.json). Sayılar
    #: gerçek çözücü koşumlarından alınmıştır; buradaki iş biçimi
    #: (hangi alan hangi iç içe blokta) korumaktır.
    YUKLER = {
        'sivi': (
            {'motor_name': 'BEKCI-SIVI', 'motor_type': 'liquid',
             'propellant_type': 'RP-1/LOX (Kerosene/Liquid Oxygen)',
             'chamber_diameter': 112.17303406538404,
             'chamber_pressure': 30.0},
            {'openrocket': {'motor_summary': {'propellant_mass': 109.4}},
             'structural_analysis': {'chamber_structure': {
                 'wall_thickness': 2.0, 'material_key': 'steel_4130'}}},
        ),
        'kati': (
            {'motor_name': 'BEKCI-KATI', 'motor_type': 'solid',
             'propellant_type': 'Ammonium Perchlorate Composite Propellant',
             'chamber_diameter': 124.76256495492507,
             'chamber_pressure': 40.0,
             'propellant_mass': 6.264252905747166},
            {'structural_analysis': {'case_analysis': {
                'wall_thickness_mm': 2.9943015589182016,
                'case_material': 'steel_4130'}}},
        ),
        'hibrit': (
            {'motor_name': 'BEKCI-HIBRIT',
             'chamber_diameter': 0.0794183882579662,
             'chamber_pressure': 20.0,
             'propellant_mass_total': 4.497560907804656,
             'chamber_wall_policy': {'wall_thickness_m': 0.009367779912125954,
                                     'wall_thickness_mm': 9.367779912125954}},
            {},
        ),
    }

    #: pdf_generator.HAZARD_BLOCKS'un başlıkları — İKİNCİ LİSTE TUTULMAZ.
    @staticmethod
    def _basliklar():
        from hrma.export.pdf_generator import PDFReportGenerator
        return [b for _a, b in PDFReportGenerator.HAZARD_BLOCKS]

    def _rapor(self, istemci, md, ar):
        r = _sessiz(istemci.post, '/api/export-pdf/complete',
                    json={'motor_data': md, 'analysis_results': ar,
                          'charts': []})
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        return _pdf_metni(r.get_data())

    @pytest.mark.parametrize('tip', sorted(YUKLER))
    def test_tehlike_bloklari_uc_motor_tipinde_de_iniyor(self, istemci, tip):
        md, ar = self.YUKLER[tip]
        metin = self._rapor(istemci, md, ar)
        # ÖLÇÜLEN KUSUR: 0/6 blok, bölüm "NOT EVALUATED IN THIS RUN".
        assert 'NOT EVALUATED IN THIS RUN' not in metin, tip
        assert 'Hazard details' in metin, tip
        dusen = [b for b in self._basliklar() if b not in metin]
        assert not dusen, 'düşen tehlike bloğu (%s): %r' % (tip, dusen)

    def test_koken_kunyesi_basiliyor(self, istemci):
        """Sunucuda koşan hüküm KÖKENİYLE basılır (hangi alan, hangi
        varsayılan) — belge, okuduğu sayının nereden geldiğini söyler."""
        md, ar = self.YUKLER['kati']
        metin = self._rapor(istemci, md, ar)
        assert 'Safety analysis provenance' in metin
        assert 'Inputs resolved from' in metin

    def test_gercek_cozucu_yoluyla_uctan_uca(self, istemci):
        """Sentetik yük değil: GERÇEK ``/calculate_solid`` sonucu."""
        r = _sessiz(istemci.post, '/calculate_solid', json={
            'motor_name': 'BEKCI-E2E', 'propellant_type': 'apcp',
            'grain_type': 'bates', 'chamber_pressure': 40.0,
            'thrust': 5000.0, 'burn_time': 3.0, 'chamber_diameter': 100.0,
            'grain_length': 500.0, 'core_diameter': 30.0,
            'expansion_ratio': 8.0})
        assert r.status_code == 200
        cr = r.get_json() or {}
        geo = cr.get('motor_geometry') or {}
        md = {'motor_name': 'BEKCI-E2E', 'motor_type': 'solid',
              'propellant_type': cr.get('propellant_name'),
              'chamber_diameter': (geo.get('chamber_diameter') or 0) * 1000,
              'chamber_pressure': cr.get('chamber_pressure'),
              'propellant_mass': cr.get('propellant_mass')}
        assert 'safety' not in cr, 'çözücü safety yayımlıyorsa yük değişti'
        metin = self._rapor(istemci, md, cr)
        assert 'NOT EVALUATED IN THIS RUN' not in metin
        dusen = [b for b in self._basliklar() if b not in metin]
        assert not dusen, 'düşen blok (uçtan uca): %r' % dusen

    # ---- FAIL-CLOSED (Doktrin 1) ----------------------------------------
    @pytest.mark.parametrize('eksilt,beklenen', [
        ('propellant_mass', 'propellant mass'),
        ('chamber_pressure', 'chamber pressure'),
        ('chamber_diameter', 'chamber diameter'),
    ])
    def test_eksik_olcude_hukum_uretilmez(self, istemci, eksilt, beklenen):
        md, ar = self.YUKLER['kati']
        md = {k: v for k, v in md.items() if k != eksilt}
        metin = self._rapor(istemci, md, ar)
        assert 'NOT EVALUATED IN THIS RUN' in metin
        assert 'Hazard details' not in metin
        # Eksik ölçü ADIYLA söylenir; yerine sayı konmaz.
        assert 'no usable value for' in metin
        assert beklenen in metin

    def test_cidar_kalinligi_yoksa_hukum_uretilmez(self, istemci):
        md, _ar = self.YUKLER['kati']
        metin = self._rapor(istemci, md, {})
        assert 'NOT EVALUATED IN THIS RUN' in metin
        assert 'wall thickness' in metin

    def test_bant_disi_basinc_bar_sanilmaz(self, istemci):
        """Pa gönderilmiş bir basınç bar sanılıp hüküm üretmez."""
        md, ar = self.YUKLER['kati']
        metin = self._rapor(istemci, dict(md, chamber_pressure=4.0e6), ar)
        assert 'NOT EVALUATED IN THIS RUN' in metin
        assert 'chamber pressure' in metin

    def test_istekle_gelen_safety_ezilmez(self, istemci):
        """Eski sözleşme korunur: gövdede safety varsa sunucu koşmaz."""
        md, ar = self.YUKLER['kati']
        # Yük, sunucunun KOŞABİLECEĞİ tam ölçüyü de taşır (cidar kalınlığı
        # ``ar`` içinde): kapı kalkarsa sunucu hükmü isteğinkini EZER ve
        # bekçi bunu görür (ters-mutasyon kanıtı).
        ar = dict(ar, safety={
            'risk_assessment': {'risk_level': 'ISTEKTEN'},
            'toxic_hazards': {'toxic_propellants': ['N2O4']}})
        metin = self._rapor(istemci, md, ar)
        assert 'ISTEKTEN' in metin
        assert 'N2O4' in metin
        assert 'Safety analysis provenance' not in metin

    def test_bant_disi_capla_hukum_uretilmez(self, istemci):
        """``resolve_length_m`` 'out_of_band' dediğinde sayı üretilmez.

        Doğrulayıcının yazılı bandı ``chamber_diameter [0,01; 5,0] m``.
        7,0 metre okumasıyla bandın ÜSTÜNDE, milimetre okumasıyla
        (0,007 m) ALTINDA kalır: iki okumanın ikisi de imkânsız, sayı
        yayımlanmaz. (Bu bant için 'ambiguous' kolu boştur — iki okumanın
        birlikte makul olması ``f in [10; 5,0]`` gerektirir.)
        """
        md, ar = self.YUKLER['kati']
        metin = self._rapor(istemci, dict(md, chamber_diameter=7.0), ar)
        assert 'NOT EVALUATED IN THIS RUN' in metin
        assert 'chamber diameter' in metin


# ==========================================================================
# P9B3-21 — TEK KAYNAK: zorunlu dörtlü /analyze_safety kapısıyla aynı
# ==========================================================================
class TestP9B321TekKaynak:
    """PDF besleme kapısı ile ``/analyze_safety`` kapısı AYRIŞAMAZ.

    Uçtaki demet yerel bir değişkendir (içe aktarılamaz), bu yüzden
    kaynaktan AST ile okunur — iki liste ayrışırsa bekçi kırmızıya döner.
    """

    @staticmethod
    def _uctaki_demet():
        import hrma.app as app_modulu
        yol = app_modulu.__file__
        agac = ast.parse(open(yol, encoding='utf-8').read())
        for dugum in ast.walk(agac):
            if not isinstance(dugum, ast.FunctionDef):
                continue
            if dugum.name != 'analyze_safety':
                continue
            for alt in ast.walk(dugum):
                if not isinstance(alt, ast.Assign):
                    continue
                for hedef in alt.targets:
                    if (isinstance(hedef, ast.Name)
                            and hedef.id == 'REQUIRED_SAFETY_FIELDS'):
                        return tuple(ast.literal_eval(alt.value))
        return None

    def test_zorunlu_dortlu_ayni(self):
        from hrma.export.pdf_safety import PDF_SAFETY_REQUIRED_FIELDS
        uctaki = self._uctaki_demet()
        assert uctaki is not None, (
            '/analyze_safety içindeki REQUIRED_SAFETY_FIELDS bulunamadı; '
            'kapı taşındıysa bu bekçi de taşınmalı')
        assert set(uctaki) == set(PDF_SAFETY_REQUIRED_FIELDS), (
            'PDF besleme kapısı /analyze_safety kapısından ayrıştı: '
            'uç=%r pdf=%r' % (uctaki, PDF_SAFETY_REQUIRED_FIELDS))

    def test_varsayilan_degerleri_yeniden_yazilmamis(self):
        """Künyedeki varsayılanlar çözümleyicinin İMZASINDAN okunur."""
        import inspect
        from hrma.analysis.safety_analysis import SafetyAnalyzer
        from hrma.export import pdf_safety
        imza = inspect.signature(
            SafetyAnalyzer.analyze_comprehensive_safety).parameters
        kaynak = inspect.getsource(pdf_safety)
        # ÖH D35 / OH-ON-06 (bekçi ÇEVRİLDİ, gerekçe): ``propellant_type``
        # artık İMZADA da varsayılansızdır (``None``) — o varsayılan bir
        # hibrit motora KATI kompozit hükmü bastırıyordu. Bekçinin KONUSU
        # ("değer pdf_safety içinde İKİNCİ KEZ yazılmasın") aynen korunur
        # ve kapsamı GENİŞLER: varsayılanı olan alan için değer tekrarı
        # aranır, olmayan alan için varsayılanın gerçekten yokluğu.
        for ad in ('propellant_type', 'material'):
            varsayilan = imza[ad].default
            if varsayilan is None:
                assert ad in ('propellant_type', 'motor_type',
                              'oxidizer_type'), (
                    '%r varsayılansız kaldı ama kimlik alanı değil' % ad)
                continue
            assert isinstance(varsayilan, str)
            assert repr(varsayilan) not in kaynak, (
                '%r varsayılanı pdf_safety içinde ikinci kez yazılmış' % ad)

    def test_birim_tablosu_beyanli(self):
        """Kaynak tablosundaki her birim çevrim tablosunda tanımlı."""
        from hrma.export.pdf_safety import (SAFETY_INPUT_SOURCES,
                                            _BIRIM_CARPANI)
        for alan, girisler in SAFETY_INPUT_SOURCES.items():
            for yol, birim in girisler:
                assert birim in _BIRIM_CARPANI, (alan, yol, birim)
                assert yol.split(':', 1)[0] in ('md', 'ar'), yol


# ==========================================================================
# OH-D30-04 — changelog 2.6.27 D30/D31 borcu
# ==========================================================================
class TestOHD3004Changelog:
    """2.6.27 kaydı, kullanıcıya görünen davranış değişikliklerini anmak
    zorundadır (hüküm-19 borcu)."""

    @staticmethod
    def _surum():
        yol = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), 'hrma', 'data', 'changelog.json')
        veri = json.load(open(yol, encoding='utf-8'))
        for kayit in veri['versions']:
            # karar §28-19/§28-46: yayımlanmamış 2.6.27 kaydı 3.0.0 adıyla çıkar.
            if str(kayit.get('version')) == '3.0.0':
                return kayit
        raise AssertionError('changelog.json içinde 3.0.0 kaydı yok')

    @staticmethod
    def _govde(kayit):
        return json.dumps(kayit, ensure_ascii=False).lower()

    @pytest.mark.parametrize('imza', [
        'diff_pct',            # payda ölçüm oldu (işaret değişti)
        'description_tr',      # kaldırıldı
        'oxidizer_temp',       # dize -> 400
        'psia',                # çarpanın kesin tanımı
        'defaults_applied',    # ÖK-21 form katmanı sözleşmesi
        'diff_pct_reference',  # paydanın ADI yayımlanan alandır
    ])
    def test_borc_kalemi_anilmis(self, imza):
        govde = self._govde(self._surum())
        assert imza.lower() in govde, (
            '2.6.27 kaydı %r davranış değişikliğini anmıyor' % imza)

    def test_pdf_guvenlik_bolumu_anilmis(self):
        """P9B3-21 kullanıcıya görünür değişiklik: belgeye yeni bölüm."""
        govde = self._govde(self._surum())
        assert 'safety' in govde and 'pdf' in govde


# ==========================================================================
# OH-D30-08 / P15B2-01 dağıtımı — ihracat sahasındaki yerel değer kapıları
# ==========================================================================
class TestOHD3008P15B201MerkeziKapi:
    """Yerel DEĞER kapıları ``hrma.utils.input_guard`` merkezine bağlı.

    Borç: aynı kötü girdi modüle göre reddediliyor / sessiz None / varsayılan
    oluyordu. Bekçi sembolü DOĞRUDAN sınar (dağıtım dosyasının şartı).
    """

    def test_drawable_hole_count_merkezden_okur(self):
        import inspect
        from hrma.export import cad_visualization as cv
        kaynak = inspect.getsource(cv.drawable_hole_count)
        assert 'finite_number(' in kaynak, 'merkez kapı çağrılmıyor'
        assert 'float(hole_count)' not in kaynak, \
            'yerel float() çevrimi geri geldi'
        # ölçüt DEĞİŞMEDİ (P9B1-26 tablosu)
        assert cv.drawable_hole_count(0) is None
        assert cv.drawable_hole_count(0.5) is None
        assert cv.drawable_hole_count(-3) is None
        assert cv.drawable_hole_count(True) is None
        assert cv.drawable_hole_count(float('nan')) is None
        assert cv.drawable_hole_count(4.0) == 4
        assert cv.drawable_hole_count(1) == 1

    def test_molekul_agirligi_merkezden_okur(self):
        import inspect
        from hrma.data import open_source_propellant_api as api
        kaynak = inspect.getsource(api._as_molecular_weight)
        assert 'finite_positive(' in kaynak, 'merkez kapı çağrılmıyor'
        assert 'math.isfinite' not in kaynak, 'yerel sonluluk denetimi kaldı'
        # PUG-REST alanı DİZE döndürür; 0/negatif/bool sayı değildir
        assert api._as_molecular_weight('46.07') == 46.07
        assert api._as_molecular_weight(0) is None
        assert api._as_molecular_weight(-1) is None
        assert api._as_molecular_weight(True) is None
        assert api._as_molecular_weight('abc') is None
