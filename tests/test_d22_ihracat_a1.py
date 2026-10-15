# -*- coding: utf-8 -*-
"""ÖH D22 / ihracat a1 — onarım bekçileri.

Her sınıf, ölçülmüş bir kusurun geri gelmesini görür. Ters-mutasyon
kanıtları: docs/scofield/raw/OH/D22/ihracat/a1/mutasyon.json
"""
import contextlib
import io
import json

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


# ==========================================================================
# P9B5-13 — ölçekleme eşiği süreksizliği
# ==========================================================================
class TestP9B513OlceklemeSurekliligi:
    """Referans boğaz çapı itkiye göre SÜREKLİ değişir (sıçrama yok)."""

    def _v(self):
        from hrma.data.nasa_realtime_validator import NASARealtimeValidator
        return NASARealtimeValidator()

    def test_esik_civarinda_sicrama_yok(self):
        v = self._v()
        ref = v.nasa_motors['F-1']
        F, Pc = ref['thrust_sl_N'], ref['chamber_pressure_bar']
        alt = v.validate_motor_calculation(
            'F-1', ref['throat_diameter_mm'], thrust_N=F * 1.0999,
            chamber_pressure_bar=Pc)['nasa_reference_mm']
        ust = v.validate_motor_calculation(
            'F-1', ref['throat_diameter_mm'], thrust_N=F * 1.1001,
            chamber_pressure_bar=Pc)['nasa_reference_mm']
        # ÖLÇÜLEN KUSUR: 914,400 -> 959,074 mm (+%4,886) — itki %0,02 arttı.
        sicrama = abs(ust - alt) / alt * 100.0
        assert sicrama < 0.05, (
            'ölçekleme eşiği süreksizlik yaratıyor: %.4f%% sıçrama' % sicrama)

    def test_oran_bir_iken_ozdeslik(self):
        v = self._v()
        ref = v.nasa_motors['F-1']
        r = v.validate_motor_calculation(
            'F-1', ref['throat_diameter_mm'],
            thrust_N=ref['thrust_sl_N'],
            chamber_pressure_bar=ref['chamber_pressure_bar'])
        assert r['nasa_reference_mm'] == pytest.approx(
            ref['throat_diameter_mm'], rel=1e-12)

    def test_pc_olcegi_artik_dusmuyor(self):
        """Aynı itki, iki kat Pc: sqrt(Pc_ref/Pc) düzeltmesi uygulanır."""
        v = self._v()
        ref = v.nasa_motors['F-1']
        tek = v.validate_motor_calculation(
            'F-1', ref['throat_diameter_mm'], thrust_N=ref['thrust_sl_N'],
            chamber_pressure_bar=ref['chamber_pressure_bar'])
        cift = v.validate_motor_calculation(
            'F-1', ref['throat_diameter_mm'], thrust_N=ref['thrust_sl_N'],
            chamber_pressure_bar=ref['chamber_pressure_bar'] * 2)
        assert cift['nasa_reference_mm'] < tek['nasa_reference_mm']
        assert cift['nasa_reference_mm'] == pytest.approx(
            tek['nasa_reference_mm'] / (2 ** 0.5), rel=1e-9)


# ==========================================================================
# P9B3-23 — emniyet çizicisinde x/y uzunluk uyuşmazlığı
# ==========================================================================
class TestP9B323XEkseniIkamesi:
    """Yayımlanmış x sessizce ÖRNEK İNDİSİNE çevrilmez."""

    UYUSMAZ = {'type': 'scatter', 'name': 'Thrust',
               'x': [0.0, 1.0, 2.0],
               'y': [10.0, 20.0, 30.0, 40.0, 50.0]}
    FIGUR = {'data': [UYUSMAZ],
             'layout': {'xaxis': {'title': {'text': 'Time (s)'}}}}

    def test_uyusmayan_iz_cizilebilir_sayilmaz(self):
        from hrma.export import chart_render as cr
        assert cr._trace_xy(self.UYUSMAZ) is None
        assert cr._is_drawable_trace(self.UYUSMAZ) is False

    def test_figur_reddedilir_ve_gerekce_verilir(self):
        from hrma.export import chart_render as cr
        gerekce = cr.fallback_refusal_reason(self.FIGUR)
        assert gerekce is not None
        assert 'x values' in gerekce and 'sample index' in gerekce

    def test_png_uretilmez(self):
        from hrma.export import chart_render as cr
        # ÖLÇÜLEN KUSUR: 40.667 baytlık, ekseni "Time (s)" etiketli ama
        # örnek indisi çizen bir PNG üretiliyordu.
        assert cr.matplotlib_png(self.FIGUR, 600, 400) is None

    def test_cozulemeyen_bdata_da_reddedilir(self):
        from hrma.export import chart_render as cr
        iz = {'type': 'scatter', 'name': 'X',
              'x': {'dtype': 'f8', 'bdata': 'BOZUK!!'},
              'y': [1.0, 2.0, 3.0]}
        assert cr._trace_xy(iz) is None
        assert cr.fallback_refusal_reason({'data': [iz], 'layout': {}}) \
            is not None

    def test_saglikli_izler_gerilemez(self):
        from hrma.export import chart_render as cr
        ok = {'type': 'scatter', 'name': 'OK', 'x': [0, 1, 2],
              'y': [1.0, 2.0, 3.0]}
        fig = {'data': [ok], 'layout': {}}
        assert cr.fallback_refusal_reason(fig) is None
        assert cr.matplotlib_png(fig, 400, 300) is not None

    def test_x_hic_yoksa_ornek_indisi_mesrudur(self):
        """plotly'nin kendi anlamı: x'i olmayan iz indisle çizilir."""
        from hrma.export import chart_render as cr
        iz = {'type': 'scatter', 'name': 'NoX', 'y': [1.0, 2.0, 3.0]}
        assert cr._trace_xy(iz) == ([0, 1, 2], [1.0, 2.0, 3.0])
        assert cr.fallback_refusal_reason({'data': [iz], 'layout': {}}) is None


# ==========================================================================
# P9B4-11 — /api/chemical-species sıcaklık kapısı
# ==========================================================================
class TestP9B411SicaklikKapisi:

    @pytest.mark.parametrize('T', [-500, 0, -0.001, float('inf'),
                                   float('nan'), 'sicak', None, True])
    def test_fiziksel_olmayan_sicaklik_422(self, istemci, T):
        r = _sessiz(istemci.post, '/api/chemical-species',
                    json={'species_name': 'CO', 'temperature': T})
        assert r.status_code == 422, 'T=%r için %s' % (T, r.status_code)
        j = r.get_json()
        assert j['error'] == 'invalid_temperature'
        assert j['invalid_fields'][0]['field'] == 'temperature'

    def test_gecerli_sicaklik_gecer(self, istemci):
        r = _sessiz(istemci.post, '/api/chemical-species',
                    json={'species_name': 'CO', 'temperature': 298.15})
        assert r.status_code == 200
        j = r.get_json()
        assert j['status'] == 'success'
        termo = j['species_data']['thermodynamic_properties']
        # ÖH D24 / P10B3-10 — ÇAPA GÜNCELLENDİ (ÖK-05 bekçi çevirisi).
        # chemical_database NASA polinomlarında ``R = 8.314`` (kesilmiş)
        # yazıyordu; artık merkezden okuyor (hrma.constants.R_MOLAR =
        # R_UNIVERSAL/1000 = 8,314462618, CODATA 2018). cp R'ye DOĞRUSAL
        # bağlı olduğundan çapa aynı çarpanla kaydı — ÖLÇÜLDÜ:
        #   29,139212528006638 -> 29,140833928562483
        # oran = 1,0000556432523455 = 8,314462618/8,314 (16 hane birebir).
        # Bant DARALTILMADI/GENİŞLETİLMEDİ (rel=1e-9 aynı); yalnız çapa
        # sayısı CODATA tabanına taşındı.
        assert termo['cp'] == pytest.approx(29.140833928562483, rel=1e-9)

    def test_aralik_disinda_success_denmez(self, istemci):
        """Sayı yayımlanamıyorsa hüküm 'success' olamaz (gerekçe adlı)."""
        r = _sessiz(istemci.post, '/api/chemical-species',
                    json={'species_name': 'CO', 'temperature': 3000.0})
        assert r.status_code == 200
        j = r.get_json()
        assert j['status'] == 'unavailable'
        assert j['unavailable_reason'] == \
            'temperature_outside_coefficient_range'
        termo = j['species_data']['thermodynamic_properties']
        assert termo['cp'] is None


# ==========================================================================
# P9B5-09 + P9B4-06 — molekül ağırlığı SAYIdır
# ==========================================================================
class TestP9B509MolekulAgirligiTipi:

    def test_pubchem_dizesi_sayiya_cevrilir(self):
        from hrma.data.open_source_propellant_api import _as_molecular_weight
        assert _as_molecular_weight('46.07') == pytest.approx(46.07)
        assert _as_molecular_weight(46.07) == pytest.approx(46.07)

    @pytest.mark.parametrize('deger', ['', 'n/a', None, 0, '0', -3, True,
                                       'NaN'])
    def test_sayi_olmayan_deger_uydurulmaz(self, deger):
        from hrma.data.open_source_propellant_api import _as_molecular_weight
        assert _as_molecular_weight(deger) is None

    def test_paket_anlik_goruntusunde_metin_mw_yok(self):
        from hrma.data.offline_store import SNAPSHOT_PATH
        d = json.load(open(SNAPSHOT_PATH, encoding='utf-8'))
        metin = {k: v['data']['molecular_weight']
                 for k, v in (d.get('entries') or {}).items()
                 if isinstance(v.get('data'), dict)
                 and isinstance(v['data'].get('molecular_weight'), str)}
        assert metin == {}, 'metin molecular_weight kaldı: %s' % metin

    def test_ayristirici_ham_dizeyi_gecirmiyor(self):
        """Kaynak sözleşmesi: MolecularWeight tek dönüştürücüden geçer."""
        import inspect
        from hrma.data import open_source_propellant_api as api
        kaynak = inspect.getsource(api)
        assert "props.get('MolecularWeight', 0)" not in kaynak
        assert '_as_molecular_weight(props.get(' in kaynak


# ==========================================================================
# P9B4-02 — paket anlık görüntüsünde KAZANILMAMIŞ künye
# ==========================================================================
class TestP9B402KazanilmisKunye:

    def _kayitlar(self):
        from hrma.data.offline_store import SNAPSHOT_PATH
        d = json.load(open(SNAPSHOT_PATH, encoding='utf-8'))
        return [(k, v['data']) for k, v in (d.get('entries') or {}).items()
                if isinstance(v.get('data'), dict)
                and isinstance(v['data'].get('summary'), dict)]

    def test_cagrilmayan_kaynak_iddia_edilmez(self):
        for ad, veri in self._kayitlar():
            kaynaklar = veri['summary'].get('sources_used') or []
            assert not any('spacex' in str(s).lower() for s in kaynaklar), (
                '%s hâlâ SpaceX kaynağı iddia ediyor; kendi '
                'flight_validation bloğu: %r'
                % (ad, (veri.get('flight_validation') or {}).get('source')))

    def test_basarisiz_bilesenli_kayit_yuksek_guven_alamaz(self):
        for ad, veri in self._kayitlar():
            durumlar = [(veri.get(b) or {}).get('status')
                        for b in ('fuel_properties', 'oxidizer_properties',
                                  'combustion_data')]
            if any(s != 'success' for s in durumlar):
                assert veri['summary'].get('confidence') != 'high', (
                    '%s bileşen durumları %r iken high güven iddia ediyor'
                    % (ad, durumlar))

    def test_paketli_kayit_high_olamaz(self):
        """Paketli anlık görüntü canlı değildir; üreticinin kendi kuralı."""
        for ad, veri in self._kayitlar():
            assert veri['summary'].get('confidence') in ('medium', 'low'), ad
            assert veri['summary'].get('confidence_basis')

    def test_kaynak_listesi_bilesenlerden_kazanilir(self):
        for ad, veri in self._kayitlar():
            kaynaklar = set(veri['summary'].get('sources_used') or [])
            kazanilmis = set()
            for b in ('fuel_properties', 'oxidizer_properties',
                      'combustion_data'):
                blok = veri.get(b) or {}
                if blok.get('status') != 'success':
                    continue
                metin = str(blok.get('source') or '').lower()
                if 'nist' in metin:
                    kazanilmis.add('NIST Webbook')
                if 'cea' in metin:
                    kazanilmis.add('NASA CEA')
            assert kaynaklar <= kazanilmis, (
                '%s kazanılmamış kaynak iddia ediyor: %s'
                % (ad, kaynaklar - kazanilmis))


# ==========================================================================
# P9B4-09 — kriyojenik süneklik hükmü kaydın kendi alanı
# ==========================================================================
class TestP9B409KriyojenikSema:

    def test_sema_alani_zorunlu(self):
        from hrma.data import materials_db as mdb
        assert 'cryogenic_ductility' in mdb.REQUIRED_FIELDS

    def test_her_kayit_hukmunu_beyan_ediyor(self):
        from hrma.data import materials_db as mdb
        eksik = [k for k, v in mdb.MATERIALS.items()
                 if v.get('cryogenic_ductility')
                 not in mdb.CRYOGENIC_DUCTILITY_VALUES]
        assert eksik == [], 'beyansız kayıt: %s' % eksik

    def test_beyansiz_kayit_yuklemede_reddedilir(self):
        from hrma.data import materials_db as mdb
        yedek = dict(mdb.MATERIALS['steel_4130'])
        try:
            mdb.MATERIALS['steel_4130'] = {
                k: v for k, v in yedek.items()
                if k != 'cryogenic_ductility'}
            with pytest.raises(ValueError) as hata:
                mdb._validate_materials()
            assert 'cryogenic_ductility' in str(hata.value)
        finally:
            mdb.MATERIALS['steel_4130'] = yedek
        mdb._validate_materials()

    def test_kume_kayitlardan_turetilir(self):
        from hrma.data import materials_db as mdb
        assert mdb.DBTT_SENSITIVE == frozenset(
            k for k, v in mdb.MATERIALS.items()
            if v.get('cryogenic_ductility') == 'dbtt_sensitive')
        assert 'steel_4130' in mdb.DBTT_SENSITIVE

    def test_hukum_kazanilmamis_malzemeye_guvence_verilmez(self):
        """not_qualified / always_brittle -> None (False DEĞİL)."""
        from hrma.data import materials_db as mdb
        for ad in ('titanium_6al4v', 'ti_grade2_cp', 'magnesium_az31b'):
            assert mdb.is_dbtt_sensitive(ad) is None, ad
        for ad in ('graphite', 'carbon_carbon', 'ablative'):
            assert mdb.is_dbtt_sensitive(ad) is None, ad
        # kazanılmış hükümler değişmedi
        assert mdb.is_dbtt_sensitive('steel_4340') is True
        assert mdb.is_dbtt_sensitive('aisi_4340') is True
        assert mdb.is_dbtt_sensitive('ss_304') is False
        assert mdb.is_dbtt_sensitive('unobtainium') is None

    def test_tuketici_listeleriyle_celiskisiz(self):
        """pressure_vessel'in üç listesi kayıtların beyanıyla çelişmez."""
        from hrma.data import materials_db as mdb
        from hrma.analysis import pressure_vessel as pv
        for ad in pv.ALWAYS_BRITTLE_MATERIALS:
            assert mdb.MATERIALS[ad]['cryogenic_ductility'] == \
                'always_brittle', ad
        for ad in pv.CRYO_EXEMPT_MATERIALS:
            assert mdb.MATERIALS[ad]['cryogenic_ductility'] == \
                'cryo_ductile', ad


# ==========================================================================
# P9B3-22 — grafik PDF'i sahte motor raporu üretmez
# ==========================================================================
class TestP9B322GrafikBelgesi:

    def _pdf_metni(self, pdf_bytes):
        from pypdf import PdfReader
        r = PdfReader(io.BytesIO(pdf_bytes))
        return '\n'.join((p.extract_text() or '') for p in r.pages)

    def _grafik(self):
        import plotly.graph_objects as go
        return go.Figure(go.Scatter(x=[0, 1, 2], y=[0, 5, 9],
                                    name='Thrust')).to_json()

    def test_uc_sahte_motor_raporu_basmaz(self, istemci):
        r = _sessiz(istemci.post, '/api/export-chart-pdf',
                    json={'chart_data': self._grafik(),
                          'chart_title': 'Thrust Curve',
                          'motor_name': 'BEKCI'})
        assert r.status_code == 200
        metin = self._pdf_metni(r.get_data())
        # ÖLÇÜLEN KUSUR: 102.803 B, "Executive Summary" + "Motor
        # Configuration" + "Performance" + 17 adet "N/A".
        assert 'Executive Summary' not in metin
        assert 'Motor Configuration' not in metin
        assert 'N/A' not in metin
        assert 'Thrust Curve' in metin

    def test_belge_ne_olmadigini_soyluyor(self, istemci):
        r = _sessiz(istemci.post, '/api/export-chart-pdf',
                    json={'chart_data': self._grafik(),
                          'chart_title': 'Thrust Curve'})
        metin = self._pdf_metni(r.get_data())
        assert 'not a motor analysis report' in metin


# ==========================================================================
# P9B3-21 — güvenlik analizinin tehlike blokları rapora iner
# ==========================================================================
class TestP9B321TehlikeBloklari:

    GUVENLIK = {
        'risk_assessment': {'risk_level': 'MEDIUM',
                            'acceptability': 'ACCEPTABLE_WITH_CONTROLS'},
        'toxic_hazards': {'hazard_level': 'HIGH',
                          'toxic_propellants': ['N2O4']},
        'explosive_hazards': {'hazard_level': 'MEDIUM',
                              'tnt_equivalent_kg': 12.5},
        'safety_equipment': {'required_ppe': ['SCBA', 'Nomex suit']},
        'emergency_procedures': {'spill_response': ['Evacuate 300 m']},
        'operational_safety': {'minimum_safe_distance_m': 300.0},
    }

    def _metin(self, analiz):
        from hrma.export.pdf_generator import PDFReportGenerator
        from pypdf import PdfReader
        pdf = _sessiz(PDFReportGenerator().generate_motor_analysis_report,
                      {'motor_name': 'BEKCI', 'motor_type': 'liquid'},
                      analiz, None, 'complete')
        return '\n'.join((p.extract_text() or '')
                         for p in PdfReader(io.BytesIO(pdf)).pages)

    def test_bloklar_dusmuyor(self):
        metin = self._metin({'safety': self.GUVENLIK})
        # ÖLÇÜLEN KUSUR: 6 bloğun yalnız 1'i (risk seviyesi) basılıyordu.
        for parca in ('SCBA', 'Nomex', 'N2O4', 'Evacuate 300 m',
                      'tnt equivalent kg', 'minimum safe distance'):
            assert parca in metin, 'düşen blok içeriği: %r' % parca

    def test_verilmeyen_blok_uydurulmaz(self):
        metin = self._metin({})
        assert 'Hazard details' not in metin
        assert 'SCBA' not in metin
        assert 'NOT EVALUATED IN THIS RUN' in metin


# ==========================================================================
# OH-D19-03 — cad_visualization yardımcılarında uydurma ölçü varsayılanı
# ==========================================================================
class TestOHD1903UydurmaOlcuVarsayilani:

    def _tasarimci(self):
        from hrma.export.cad_visualization import MotorCADDesigner
        return MotorCADDesigner()

    def test_kesit_bos_govdeyle_cizmez(self):
        from plotly.subplots import make_subplots
        fig = make_subplots(rows=1, cols=1, specs=[[{'type': 'scatter'}]])
        with pytest.raises(ValueError) as hata:
            self._tasarimci()._add_cross_section_view(fig, {}, row=1, col=1)
        assert 'chamber_diameter_not_available' in str(hata.value)

    def test_yedek_3d_bos_govdeyle_cizmez(self):
        from plotly.subplots import make_subplots
        fig = make_subplots(rows=1, cols=1, specs=[[{'type': 'scatter3d'}]])
        with pytest.raises(ValueError) as hata:
            self._tasarimci()._add_fallback_3d_motor(fig, {}, row=1, col=1)
        assert str(hata.value)  # fix-19 (ÖK-22 nüfus tavanı)

    def test_yedek_gorsellestirme_bos_govdeyle_cizmez(self):
        with pytest.raises(ValueError) as hata:
            self._tasarimci()._create_fallback_visualization({})
        assert str(hata.value)  # fix-19 (ÖK-22 nüfus tavanı)

    def test_imalat_cizimine_uydurma_olcu_yazilmaz(self):
        with pytest.raises(ValueError) as hata:
            self._tasarimci()._generate_technical_drawings(
                {'chamber_diameter': 0.1, 'chamber_length': 0.3})
        assert 'throat_diameter_not_available' in str(hata.value)

    def test_detayli_cad_bos_govdeyle_motor_uydurmaz(self):
        from hrma.export.cad_visualization import DetailedCADGenerator
        with pytest.raises(ValueError) as hata:
            _sessiz(DetailedCADGenerator().generate_liquid_motor_cad, {})
        assert str(hata.value)  # fix-19: ret gerekçeli (ÖK-22 iddiasız nüfus tavanı)

    def test_uc_adli_ret_veriyor(self, istemci):
        """Eksik ölçü 500 değil, alan adıyla 422 olur."""
        r = _sessiz(istemci.post, '/api/detailed-cad/liquid',
                    json={'chamber_diameter': 100.0, 'chamber_length': 200.0,
                          'throat_diameter': 50.0, 'exit_diameter': 80.0})
        assert r.status_code == 422
        j = r.get_json()
        assert j['error'] == 'missing_export_geometry'
        assert j['invalid_fields'][0]['field'] == 'nozzle_length'

    def test_tam_govde_hala_ciziliyor(self, istemci):
        r = _sessiz(istemci.post, '/api/detailed-cad/liquid',
                    json={'chamber_diameter': 100.0, 'chamber_length': 200.0,
                          'throat_diameter': 50.0, 'exit_diameter': 80.0,
                          'nozzle_length': 150.0})
        assert r.status_code == 200
        assert r.get_json()['status'] == 'success'

    def test_kaynakta_uydurma_varsayilan_kalmadi(self):
        """Beş yardımcıda ölçü varsayılanı kalıbı yok."""
        import re
        import hrma.export.cad_visualization as cv
        kaynak = open(cv.__file__.replace('.pyc', '.py'),
                      encoding='utf-8').read()
        kalip = re.compile(
            r"motor_data\.get\('(chamber_diameter|chamber_length"
            r"|throat_diameter|exit_diameter|nozzle_length)',\s*[0-9]")
        # Yorum/belge satırlarındaki ALINTILAR sayılmaz — onarımın kendi
        # gerekçesi kusurun birebir metnini taşıyor.
        kod = '\n'.join(
            satir for satir in kaynak.split('\n')
            if not satir.lstrip().startswith('#') and '``' not in satir
            and '`motor_data.get(' not in satir)
        kalan = kalip.findall(kod)
        # ÖLÇÜLEN KUSUR: 22 örnek (once.json OH-D19-03).
        assert kalan == [], 'uydurma ölçü varsayılanı kaldı: %s' % kalan
