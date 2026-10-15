"""ÖH Dalga-21 · ihracat · aşama 1 — onarım bekçileri.

Her sınıf bir defter kalemini bekler. Ölçümler
``docs/scofield/raw/OH/D21/ihracat/a1/{once,sonra}.json`` içindedir; ters
mutasyon kanıtı ``mutasyon.json``da.
"""

import json
import os
import tempfile

import pytest


# ---------------------------------------------------------------------------
# Ortak yardımcılar
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _tank_govdesi(**degistir):
    """Sözleşmeye UYGUN ``propellant_tanks`` gövdesi (ölçümle aynı)."""
    olcu = {'diameter': 300.0, 'length': 1200.0, 'wall_thickness': 4.0}
    yapisal = {'material': 'aluminum_6061', 'pressure_rating': 25.0}
    ic = {'slosh_baffles': {}, 'anti_vortex_device': {}}
    gövde = {
        'fuel_tank': {'dimensions': dict(olcu), 'structural': dict(yapisal),
                      'internal_structures': dict(ic)},
        'oxidizer_tank': {'dimensions': dict(olcu, length=1500.0),
                          'structural': dict(yapisal),
                          'internal_structures': dict(ic)},
    }
    gövde.update(degistir)
    return gövde


#: Yapısal analizi TAM (cidar + kapak) imalat gövdesi.
def _imalat_govdesi(**degistir):
    md = {
        'motor_name': 'D21_IHRACAT', 'chamber_diameter': 0.1,
        'chamber_length': 0.25, 'throat_diameter': 0.05,
        'exit_diameter': 0.109, 'nozzle_length': 0.12, 'length_units': 'm',
        'structural_analysis': {
            'chamber_analysis': {'design_mode': 'verify',
                                 'wall_thickness_used_mm': 5.0,
                                 'recommended_thickness': 5.0},
            'end_cap_analysis': {'flat_head_thickness': 9.0,
                                 'head_thickness_used_mm': 9.0,
                                 'recommended_type': 'flat',
                                 'design_mode': 'size'},
        },
    }
    md.update(degistir)
    return md


# ---------------------------------------------------------------------------
# P9B2-19 — STEP içe aktarma birimi ifade SIRASINA bağlı okunuyordu
# ---------------------------------------------------------------------------

_SPEC_SIRASI = """ISO-10303-21;
HEADER;
FILE_DESCRIPTION((''),'2;1');
ENDSEC;
DATA;
#10 = ( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.) );
#11 = DIMENSIONAL_EXPONENTS(1.,0.,0.,0.,0.,0.,0.);
#12 = MEASURE_WITH_UNIT(LENGTH_MEASURE({olcek}),#10);
#13 = ( CONVERSION_BASED_UNIT('{ad}',#12) LENGTH_UNIT() NAMED_UNIT(#11) );
ENDSEC;
END-ISO-10303-21;
"""


class TestP9B219StepBirimSirasi:
    """ÖLÇÜLDÜ (once.json A): inç/foot/mil dalı KURALLARA UYGUN dosyalarda
    hiç ateşlenmiyordu — üçü de ``'mm'`` okunuyordu, çünkü birim dosyadaki
    ifade SIRASINA bağlıydı ve ISO 10303-21'de SI taban birimi dönüşümlü
    birimden ÖNCE gelir. 7 vakanın 3'ü yanlıştı; onarımdan sonra 0."""

    @staticmethod
    def _yaz(tmp_path, metin, ad='u.step'):
        p = tmp_path / ad
        p.write_text(metin)
        return str(p)

    @pytest.mark.parametrize('ad,olcek,beklenen', [
        ('INCH', '25.4', 'inch'),
        ('FOOT', '304.8', 'ft'),
        ('THOU', '0.0254', 'mil'),
    ])
    def test_donusumlu_birim_SI_tabanini_yener(self, tmp_path, ad, olcek,
                                               beklenen):
        """Asıl kusur: SI_UNIT satırı önce geldiği için dönüşüm görülmüyordu."""
        from hrma.importers.step_import import _detect_declared_unit
        yol = self._yaz(tmp_path,
                        _SPEC_SIRASI.format(ad=ad, olcek=olcek), f'{ad}.step')
        birim, _ham = _detect_declared_unit(yol)
        assert birim == beklenen, (
            f'{ad} beyan eden dosya {birim!r} okundu; dosyadaki '
            'SI_UNIT(.MILLI.,.METRE.) dönüşümün TABANIDIR, dosyanın birimi '
            'değildir')

    def test_yalniz_SI_birimi_olan_dosya_mm_kalir(self, tmp_path):
        """Onarım fazla da olamaz: dönüşüm yoksa SI birimi geçerlidir."""
        from hrma.importers.step_import import _detect_declared_unit
        yol = self._yaz(tmp_path,
                        'ISO-10303-21;\nDATA;\n'
                        '#10 = ( LENGTH_UNIT() NAMED_UNIT(*) '
                        'SI_UNIT(.MILLI.,.METRE.) );\nENDSEC;\n')
        assert _detect_declared_unit(yol)[0] == 'mm'

    def test_CELISKILI_beyan_fail_closed(self, tmp_path):
        """İki farklı dönüşümlü birim -> birim KAZANILMAMIŞTIR (tahmin yok)."""
        from hrma.importers.step_import import _detect_declared_unit
        metin = _SPEC_SIRASI.format(ad='INCH', olcek='25.4').replace(
            "ENDSEC;\nEND-ISO",
            "#14 = ( CONVERSION_BASED_UNIT('FOOT',#12) LENGTH_UNIT() "
            "NAMED_UNIT(#11) );\nENDSEC;\nEND-ISO")
        yol = self._yaz(tmp_path, metin, 'celiskili.step')
        assert _detect_declared_unit(yol) == (None, None), (
            'çelişen iki birim beyanından biri seçilirse ölçek sessizce '
            'uydurulmuş olur')

    def test_ic_ice_gecmis_tek_satir_da_cozulur(self, tmp_path):
        """Bazı yazıcılar iki ifadeyi tek satıra basar; ayrıştırıcı yine
        dönüşümlü birimi bulmalı (eski kod burada da 'mm' diyordu)."""
        from hrma.importers.step_import import _detect_declared_unit
        yol = self._yaz(tmp_path,
                        "ISO-10303-21;\nDATA;\n"
                        "#10 = ( LENGTH_UNIT() NAMED_UNIT(*) "
                        "SI_UNIT(.MILLI.,.METRE.) ) #13 = ( "
                        "CONVERSION_BASED_UNIT('INCH',#12) LENGTH_UNIT() "
                        "NAMED_UNIT(#11) );\nENDSEC;\n", 'tek.step')
        assert _detect_declared_unit(yol)[0] == 'inch'


# ---------------------------------------------------------------------------
# P9B2-18 — birim çıkarım YORUMU kodla çelişiyordu (1000x)
# ---------------------------------------------------------------------------

class TestP9B218BirimYorumuKodlaTutar:
    """ÖLÇÜLDÜ (once.json B): yorum *"belirsiz bant (ör. 1.0) çap için mm
    kabul edilir"* diyordu; kod ``chamber_diameter=1.0`` için 1,0 METRE
    (kaynak ``'si'``), ``throat_diameter=1.0`` için ise ``None``
    (``'ambiguous'``) üretiyordu. Yorumun vaadi ile kodun sonucu arasında
    1000 kat vardı ve yorum üçüncü davranıştan hiç söz etmiyordu."""

    @staticmethod
    def _kaynak():
        import hrma.export.motor_geometry as MG
        with open(MG.__file__, encoding='utf-8') as fh:
            return fh.read()

    def test_yanlis_yorum_cumlesi_kaynakta_YOK(self):
        assert 'çap için mm kabul edilir' not in self._kaynak(), (
            'kodun 1,0 için METRE ürettiği ölçüldü; yorum hâlâ mm diyorsa '
            'okuyucu 1000 kat yanlış yönlendirilir')

    def test_olculen_davranis_yorumla_ayni(self):
        from hrma.export import motor_geometry as MG
        assert MG.length_in_meters_banded(
            1.0, 'chamber_diameter', MG.DIAMETER_SI_MAX_M) == (1.0, 'si')
        assert MG.length_in_meters_banded(
            1.0, 'throat_diameter', MG.DIAMETER_SI_MAX_M) == (None,
                                                              'ambiguous')

    def test_yorum_gecerli_kurali_ADIYLA_aniyor(self):
        """Yorum bugünkü hükmü yönlendirmeli: iki-okuma birleşim kuralı."""
        k = self._kaynak()
        assert 'İKİ-OKUMA BİRLEŞİM KURALI' in k
        assert 'length_in_meters_banded' in k


# ---------------------------------------------------------------------------
# P9B2-14 — cleanup_workspace ürün kodunda HİÇ çağrılmıyordu
# ---------------------------------------------------------------------------

class TestP9B214CalismaDiziniTemizligi:
    """ÖLÇÜLDÜ (once.json D): ``cleanup_workspace``ın ürün kodunda tek
    ``git grep`` isabeti bir docstring satırıydı; üç ihraç isteği ``/tmp``te
    3 dizin ve 217.852 bayt bırakıyordu ve 24 saatlik yaş kapısı yüzünden bir
    gün silinmiyordu. Bekçi ÜRÜNÜ ölçer: temizliği testin kendisi YAPMAZ
    (savcı §3.3-C'nin totolojik bekçi kusuru)."""

    @staticmethod
    def _hrma_dizinleri():
        from hrma.export.export_workspace import HRMA_TEMP_PREFIXES
        kok = tempfile.gettempdir()
        try:
            adlar = os.listdir(kok)
        except OSError:
            return set()
        return {a for a in adlar if a.startswith(HRMA_TEMP_PREFIXES)
                and os.path.isdir(os.path.join(kok, a))}

    @pytest.mark.parametrize('uc,en_az_bayt', [
        ('/api/export-dxf', 10000),
        ('/api/export-drawings-pdf', 10000),
    ])
    def test_indirme_sonrasi_calisma_dizini_KALMIYOR(self, client, uc,
                                                     en_az_bayt):
        md = {'motor_name': 'd21tmp', 'chamber_diameter': 0.1,
              'chamber_length': 0.25, 'throat_diameter': 0.05,
              'exit_diameter': 0.109, 'nozzle_length': 0.12,
              'length_units': 'm'}
        once = self._hrma_dizinleri()
        r = client.post(uc, json={'motor_data': md})
        assert r.status_code == 200, r.get_data(as_text=True)[:200]
        # Dosya GERÇEKTEN iniyor: temizlik ürünü boşaltmamalı.
        assert len(r.get_data()) >= en_az_bayt
        yeni = self._hrma_dizinleri() - once
        assert yeni == set(), (
            f'{uc} indirildikten sonra {sorted(yeni)} çalışma dizini '
            'kaldı; cleanup_workspace yine bağlanmamış')

    def test_temizleyici_TANIMAYAN_dizine_dokunmaz(self, tmp_path):
        """Onarım fazla da olamaz: proje öneki olmayan dizin silinmez."""
        from hrma.export.export_workspace import cleanup_paths, workspace_of
        yabanci = tmp_path / 'kullanici_belgeleri'
        yabanci.mkdir()
        (yabanci / 'onemli.txt').write_text('dokunma')
        assert workspace_of(str(yabanci / 'onemli.txt')) is None
        assert cleanup_paths(str(yabanci / 'onemli.txt')) == 0
        assert (yabanci / 'onemli.txt').exists()

    def test_detach_file_baytlari_KORUYARAK_siler(self, tmp_path):
        from hrma.export.export_workspace import detach_file, new_workspace
        d = new_workspace('hrma_dxf_')
        p = os.path.join(d, 'x.bin')
        with open(p, 'wb') as fh:
            fh.write(b'0123456789' * 100)
        buf = detach_file(p)
        assert buf.read() == b'0123456789' * 100
        assert not os.path.isdir(d)


# ---------------------------------------------------------------------------
# P9B2-17 — başarı mesajı pakette OLMAYAN bir dosyayı vaat ediyordu
# ---------------------------------------------------------------------------

class TestP9B217PaketVaadiGercekle:
    """ÖLÇÜLDÜ (once.json C): arayüz "• Manufacturing specifications"
    indiğini söylüyordu; paketteki dosya ``manufacturing_checklist_TEMPLATE
    .json`` (doldurulmamış ŞABLON). Pakette 'manufacturing specification'
    adlı hiçbir dosya yoktu."""

    @staticmethod
    def _metinler():
        import hrma
        kok = os.path.dirname(os.path.dirname(os.path.abspath(hrma.__file__)))
        with open(os.path.join(kok, 'hrma', 'templates', 'liquid.html'),
                  encoding='utf-8') as fh:
            tpl = fh.read()
        with open(os.path.join(kok, 'hrma', 'static', 'js', 'i18n_pages.js'),
                  encoding='utf-8') as fh:
            js = fh.read()
        return tpl, js

    def test_vaat_edilen_ad_UYDURMA_degil(self):
        tpl, js = self._metinler()
        for etiket, metin in (('şablon', tpl), ('i18n sözlüğü', js)):
            assert '• Manufacturing specifications' not in metin, (
                f'{etiket} pakette bulunmayan bir dosya adı vaat ediyor')
        # Gerçek dosya adı hem şablonda hem sözlükte geçiyor.
        assert 'manufacturing_checklist_TEMPLATE.json' in tpl
        assert 'manufacturing_checklist_TEMPLATE.json' in js

    def test_paket_gercekten_o_dosyayi_tasiyor(self):
        """Vaat ile paket AYNI dosyayı anlatmalı (iki yönlü ölçüm)."""
        import zipfile
        from hrma.export.cad_export import cad_generator
        from hrma.export.export_workspace import cleanup_paths
        yol = cad_generator.generate_tank_cad(_tank_govdesi())
        try:
            with zipfile.ZipFile(yol) as zf:
                adlar = set(zf.namelist())
        finally:
            cleanup_paths(yol)
        assert 'manufacturing_checklist_TEMPLATE.json' in adlar
        assert not any('manufacturing_specification' in a.lower()
                       for a in adlar), (
            'pakette gerçekten "manufacturing specification" adlı bir dosya '
            'varsa vaat metni yeniden ölçülmeli')


# ---------------------------------------------------------------------------
# P9B2-27 — eksik tank alt sözlüğünde ham KeyError + aynı yolun tekrarı
# ---------------------------------------------------------------------------

class TestP9B227TankSozlesmeKapisi:
    """ÖLÇÜLDÜ (once.json E): ``generate_tank_cad`` eksik gövdede
    ``KeyError: 'fuel_tank'`` / ``KeyError: 'wall_thickness'`` yükseltiyordu
    ve sözleşme kapısı yalnız HTTP ucundaydı. Üstelik kapıdan GEÇEN bir
    gövde bile ``KeyError: 'pressure_rating'`` ile çöküyordu — kapı vardı ama
    sözleşmeyi eksik yazıyordu."""

    @pytest.mark.parametrize('bozuk,beklenen_alan', [
        ({'oxidizer_tank': _tank_govdesi()['oxidizer_tank']}, 'fuel_tank'),
        ({}, 'oxidizer_tank'),
    ])
    def test_eksik_blokta_HAM_KeyError_yok(self, bozuk, beklenen_alan):
        from hrma.export.cad_export import TankCADDataError, cad_generator
        with pytest.raises(TankCADDataError) as exc:
            cad_generator.generate_tank_cad(bozuk)
        alanlar = [f['field'] for f in exc.value.fields]
        assert beklenen_alan in alanlar
        assert 'KeyError' not in str(exc.value)

    def test_kapidan_GECEN_govde_pressure_rating_ile_cokmuyor(self):
        """Kalemin asıl kökü: sözleşme, üreticinin okuduğu alanı saymıyordu.
        ``_generate_drawing_notes`` ``structural.pressure_rating``ı ÇIPLAK
        indeksle okuyor; alan sözleşmede yoksa kapı boşuna vardır."""
        from hrma.export.cad_export import (TANK_CAD_REQUIRED_BLOCKS,
                                            TankCADDataError, cad_generator)
        yapisal = dict(TANK_CAD_REQUIRED_BLOCKS)['structural']
        assert 'pressure_rating' in yapisal, (
            'üretici bu alanı çıplak indeksle okuyor; sözleşmede yoksa kapı '
            'geçildikten SONRA ham KeyError üretilir'
        )
        govde = _tank_govdesi()
        govde['oxidizer_tank']['structural'].pop('pressure_rating')
        with pytest.raises(TankCADDataError) as exc:
            cad_generator.generate_tank_cad(govde)
        assert 'oxidizer_tank.structural.pressure_rating' in [
            f['field'] for f in exc.value.fields]

    def test_uc_adlandirilmis_422_veriyor(self, client):
        govde = _tank_govdesi()
        govde['fuel_tank']['dimensions'].pop('wall_thickness')
        r = client.post('/export_tank_cad', json={'tank_data': govde})
        assert r.status_code == 422, r.get_data(as_text=True)[:200]
        j = r.get_json()
        assert 'fuel_tank.dimensions.wall_thickness' in [
            f['field'] for f in j['invalid_fields']]
        assert 'KeyError' not in json.dumps(j)

    def test_saglikli_govde_HALA_paket_uretiyor(self, client):
        """Kapı fazla da olamaz (ÖK-22): sağlıklı envanter geçmeli."""
        r = client.post('/export_tank_cad', json={'tank_data': _tank_govdesi()})
        assert r.status_code == 200
        assert len(r.get_data()) > 10000

    def test_basarisiz_yol_AYNI_yolu_tekrar_denemiyor(self):
        """``except`` dalı ``try`` içindekiyle AYNI fonksiyonu çağırıyordu:
        aynı girdi aynı kodda ikinci kez patlar, kazanılan tek şey ikinci bir
        yarım yazma turudur."""
        import inspect

        from hrma.export.cad_export import TankCADGenerator
        kaynak = inspect.getsource(TankCADGenerator.generate_tank_cad)
        gövde = kaynak.split('"""')[-1]
        assert gövde.count('_generate_fallback_files') == 2, (
            'yedek üretici gövdede iki kez geçmeli: FreeCAD yoksa doğrudan, '
            'FreeCAD yolu düşerse yedek olarak — üçüncü bir çağrı aynı yolun '
            'tekrarı demektir')
        assert '_generate_freecad_files' in gövde


# ---------------------------------------------------------------------------
# P9B1-17 — baş kapak yapısal analize sorulmadan uydurma kuralla çiziliyordu
# ---------------------------------------------------------------------------

class TestP9B117KapakImalatKapisi:
    """ÖLÇÜLDÜ (once.json F + K): kapak analizi olmayan gövdede aynı
    dosyadaki iki basınç-sınırı parçası zıt davranıyordu — cidar ``None``
    dönüp imalat STEP'ini REDDEDİYOR, kapak 8,00 mm ÜRETİLİYORDU. Katı
    motorun yapısal analizi kapak kalınlığı hiç yayımlamıyor (ölçüldü:
    ``assembly_integrity.closure_joint.status == 'not_sized'``), yani
    uydurma sayı imalat dosyasına gerçekten iniyordu."""

    def test_kapi_ISTENDIGINDE_sayi_uretmez(self):
        """Kapı mekanizması: ``require_analysis=True`` -> sayı YOK, gerekçe VAR."""
        from hrma.export.cad_visualization import (CAP_REFUSED_NO_ANALYSIS,
                                                   _front_cap_design)
        d = _front_cap_design({}, wall_mm=3.0, bore_radius_mm=50.0,
                              require_analysis=True)
        assert d['thickness_mm'] is None
        assert d['from_analysis'] is False
        assert d['source'] == CAP_REFUSED_NO_ANALYSIS
        for parca in ('closure head', 'end_cap_analysis', 'pressure boundary',
                      'generator geometry rule'):
            assert parca in d['source']

    def test_imalat_STEPi_kapiyi_HENUZ_kullanmiyor_ve_bunu_yaziyor(self):
        """DÜRÜSTLÜK BEKÇİSİ — kalem KISMEN kapandı.

        ÖLÇÜLDÜ: kapı ``generate_step_assembly``a bağlandığında katı ve sıvı
        motorların imalat STEP'i tamamen kayboluyor (o iki motorun yapısal
        analizi kapak kalınlığı yayımlamıyor; 4 dosyada 27 bekçi kırmızı).
        Bu yüzden kapı bu dalgada BAĞLANMADI ve kod bunu ADIYLA söylemek
        zorunda: gerekçe silinirse okuyucu, kapağın analizden geldiğini
        sanır."""
        import inspect

        from hrma.export import step_export
        kaynak = inspect.getsource(step_export.generate_step_assembly)
        assert 'require_analysis' in kaynak, (
            'kapının neden bağlanmadığı kodda yazılı olmalı'
        )
        assert 'KAPI BU DALGADA BAĞLANMADI' in kaynak

    def test_cidar_ile_kapak_ayrismasi_OLCULUR(self):
        """Asıl kusur kardeşlerin ayrışmasıydı; bekçi onu ölçer."""
        from hrma.export.cad_visualization import (_chamber_wall_design,
                                                   _front_cap_design)
        cidar = _chamber_wall_design({})
        varsayilan = _front_cap_design({}, wall_mm=3.0, bore_radius_mm=50.0)
        zorunlu = _front_cap_design({}, wall_mm=3.0, bore_radius_mm=50.0,
                                    require_analysis=True)
        # Kusurun ÖLÇÜSÜ: analiz yokken cidar sayı üretmiyor, kapak 8,00 mm
        # üretiyor. Kapı açıldığında ikisi aynı hükmü verir.
        assert cidar['thickness_m'] is None
        assert varsayilan['thickness_mm'] == 8.0
        assert zorunlu['thickness_mm'] is None

    def test_varsayilan_yol_varsayimi_KUNYESIYLE_cizmeye_devam_eder(self):
        """Varsayılan yol (önizleme + bugünkü imalat) varsayımı çizer ama
        künyesinde 'ASSUMED' der — davranış korunur."""
        from hrma.export.cad_visualization import _front_cap_design
        d = _front_cap_design({}, wall_mm=3.0, bore_radius_mm=50.0)
        assert d['thickness_mm'] == 8.0
        assert d['from_analysis'] is False
        assert d['source'].startswith('ASSUMED closure head')

    def test_analizden_gelen_kalinlik_AYNEN_kullanilir(self):
        from hrma.export.cad_visualization import _front_cap_design
        md = {'structural_analysis': {
            'end_cap_analysis': {'flat_head_thickness': 12.34}}}
        for zorunlu in (False, True):
            d = _front_cap_design(md, wall_mm=3.0, bore_radius_mm=50.0,
                                  require_analysis=zorunlu)
            assert d['thickness_mm'] == 12.34
            assert d['from_analysis'] is True


# ---------------------------------------------------------------------------
# P15B4-05 / P9B1-31 — ``cad_design`` adı altında birbirinden bağımsız şekiller
# ---------------------------------------------------------------------------

class TestP15B405CadDesignSekilAdi:
    """ÖLÇÜLDÜ (once.json G): ``/calculate_solid`` 10 anahtarlı ve
    ``schema='hrma.solid.cad_design/1'`` etiketli bir blok, ``/calculate``
    ise 6 anahtarlı ve ETİKETSİZ bir blok yayımlıyordu; ``case_design``
    yalnız katıda vardı. Etiketsiz şekil, tüketicide
    ``.get('case_design', {})`` biçiminde SESSİZ YEDEĞE dönüşüyordu."""

    def test_ihrac_katmani_seklini_ADIYLA_yayimliyor(self, client):
        from hrma.export.cad_visualization import CAD_VISUALIZATION_SCHEMA
        r = client.post('/calculate', json={
            'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
            'chamber_pressure': 20.0, 'fuel_type': 'htpb',
            'oxidizer_type': 'n2o'})
        assert r.status_code == 200
        cad = r.get_json().get('cad_design') or {}
        assert cad.get('schema') == CAD_VISUALIZATION_SCHEMA
        assert cad['schema'].startswith('hrma.cad_visualization.')

    def test_iki_sekil_AYIRT_edilebiliyor(self, client):
        """Kalemin ürünündeki sonucu: okuyucu artık 'bu benim şeklim değil'
        diyebilir; eskiden iki şekil de adsızdı ve ayırt edilemiyordu."""
        from hrma.engines.solid_rocket_engine import SOLID_CAD_DESIGN_SCHEMA
        from hrma.export.cad_visualization import CAD_VISUALIZATION_SCHEMA
        assert CAD_VISUALIZATION_SCHEMA != SOLID_CAD_DESIGN_SCHEMA
        rs = client.post('/calculate_solid', json={
            'motor_type': 'solid', 'thrust': 5000, 'burn_time': 10,
            'chamber_pressure': 30, 'propellant_name': 'apcp',
            'expansion_ratio': 4.0})
        assert rs.status_code == 200
        kati = rs.get_json().get('cad_design') or {}
        assert kati.get('schema') == SOLID_CAD_DESIGN_SCHEMA
        # ``case_design`` KATI şeklin alanıdır; ihraç şekli onu TAŞIMAZ ve
        # artık bunu adıyla söyleyebiliyor (uydurma blok enjekte edilmedi).
        assert 'case_design' in kati

    def test_BASARISIZ_uretim_de_seklini_soyluyor(self):
        """Hata dalında ad düşerse okuyucu yine sessiz yedeğe düşer."""
        from hrma.export.cad_visualization import (CAD_VISUALIZATION_SCHEMA,
                                                   MotorCADDesigner)
        d = MotorCADDesigner().generate_3d_motor_assembly(
            {'chamber_diameter': 'olmayan-sayi'})
        assert d.get('schema') == CAD_VISUALIZATION_SCHEMA

    def test_json_safe_kopya_adi_KAYBETMIYOR(self):
        """P9B1-31: yanıta çıkan kopya da şeklini söylemeli."""
        from hrma.export.cad_visualization import (CAD_VISUALIZATION_SCHEMA,
                                                   MotorCADDesigner,
                                                   json_safe_cad_design)
        cad = MotorCADDesigner().generate_3d_motor_assembly({
            'chamber_diameter': 0.1, 'chamber_length': 0.25,
            'throat_diameter': 0.05, 'exit_diameter': 0.109})
        blok = json_safe_cad_design(cad)
        assert blok.get('schema') == CAD_VISUALIZATION_SCHEMA
        assert '<trimesh.' not in json.dumps(blok, default=str)


# ---------------------------------------------------------------------------
# P9B2-04 / P9B2-24 — yayımlanan boy ⟷ STEP montaj boyu
# ---------------------------------------------------------------------------

class TestP9B20424MontajBoyu:
    """ÖLÇÜLDÜ (sonra.json I): ihraç katmanının YAYIMLADIĞI toplam boy ile
    ürettiği STEP montajının ölçülen boyu 5e-05 mm içinde aynı (413,65405
    ⟷ 413,6541; 396,95278 ⟷ 396,9528) ve yayımlanan sayının künyesi kapağı
    saydığını SÖYLÜYOR. Manşetin "beyansız baş kapağı" gerekçesi ihraç
    katmanında yok. Kalan ayrışma ÇÖZÜCÜNÜN ``design_summary.key_dimensions``
    alanına karşıdır (bu modülün sahası değil) ve montaj adında
    uzlaştırılır."""

    def test_yayimlanan_boy_ile_STEP_montaji_AYNI(self, tmp_path):
        pytest.importorskip('build123d')
        from build123d import import_step

        from hrma.export.cad_visualization import MotorCADDesigner
        from hrma.export.step_export import generate_step_assembly
        md = _imalat_govdesi()
        ozet = ((MotorCADDesigner().generate_3d_motor_assembly(dict(md))
                 .get('performance_summary') or {}).get('geometry_summary')
                or {})
        yayin = ozet.get('total_length')
        files = generate_step_assembly(dict(md),
                                       out_dir=str(tmp_path / 'step'))
        bb = import_step(files['assembly']).bounding_box()
        olculen = float(bb.max.X - bb.min.X)
        assert yayin is not None
        assert olculen == pytest.approx(yayin, abs=1e-3), (
            f'ihraç katmanı {yayin:.5f} mm yayımlarken ürettiği montaj '
            f'{olculen:.5f} mm ölçüldü')

    def test_yayimlanan_boyun_kunyesi_kapagi_ADIYLA_sayiyor(self):
        from hrma.export.cad_visualization import MotorCADDesigner
        ozet = ((MotorCADDesigner()
                 .generate_3d_motor_assembly(_imalat_govdesi())
                 .get('performance_summary') or {}).get('geometry_summary')
                or {})
        assert 'closure' in (ozet.get('total_length_basis') or '')
        # Kapağı SAYMAYAN sayı ayrı adla ve ayrı künyeyle yayımlanır.
        assert ozet['total_length'] > ozet['total_length_estimate']
        assert 'EXCLUDES the forward closure' in (
            ozet.get('total_length_estimate_basis') or '')


# ---------------------------------------------------------------------------
# P9B2-13 — ters lüle: kardeş imalat uçları AYNI kapıyı uyguluyor mu?
# ---------------------------------------------------------------------------

class TestP9B213TersLuleKardesUclar:
    """ÖLÇÜLDÜ (once.json H): manşetin iddia ettiği ayrışma (export-step 500
    + "TopoDS::Face" ⟷ export-dxf 200) YOK. Ters lüleyle (çıkış 20 mm <
    boğaz 50 mm) dört kardeş uç da HTTP 422 ``inconsistent_export_geometry``
    veriyor, aynı metinle. Bekçi ayrışmanın GERİ GELMESİNİ bekler."""

    TERS = dict(_imalat_govdesi(), exit_diameter=0.020)

    @pytest.mark.parametrize('uc', ['/api/export-step', '/api/export-dxf',
                                    '/api/export-drawings-pdf'])
    def test_ters_lule_her_kardeste_ADLANDIRILMIS_422(self, client, uc):
        r = client.post(uc, json={'motor_data': dict(self.TERS)})
        assert r.status_code == 422, (
            f'{uc} ters lüleye {r.status_code} verdi: '
            f'{r.get_data(as_text=True)[:200]}')
        j = r.get_json()
        assert j['error'] == 'inconsistent_export_geometry'
        assert 'TopoDS' not in json.dumps(j), (
            'çekirdek istisna metni istemciye sızmış')

    def test_saglikli_lule_ayni_uclardan_GECIYOR(self, client):
        """Kapı fazla olamaz: doğru geometri reddedilmemeli.

        ÖH V3 CAD A1 · H5 — ÇEVRİLDİ (12 Eki 2026, ana model izni, dört
        koşul; rapor ``docs/scofield/raw/OH/V3/cad-duzeltme/rapor.md``
        "Bölüm T"). Karar §28-21 (i): basınç taşıyan parçanın SF'si EKSİKSE
        imalat kapısı kapanır. Bu düğümün gövdesi cidar yayımlayıp SF
        yayımlamıyordu ve artık doğru olarak 422 (``sf_missing``) alıyordu;
        "sağlıklı" gövde yapısal sonucun emniyet katsayısını da taşır. SF'siz
        gövdenin reddi ``tests/test_v3_cad_duzeltme.py::TestH5KapiDallari``
        içinde sınanır.

        Değer BAĞIMSIZ kâhinden (dışa aktarım kod yolundan değil): kalın
        cidarlı silindirin iç yüzündeki tepe çember gerilmesi (Lamé,
        Roark/Shigley) σ = P·(r_o² + r_i²)/(r_o² − r_i²); r_i ve cidar
        gövdenin KENDİ alanlarından, P = 20 bar (bu dosyanın hibrit
        ``/calculate`` fikstürüyle aynı işletme noktası), akma dayanımı
        yapısal modülün varsayılan malzemesi steel_4130'un oda sıcaklığı
        kaydı (``materials_db``, 460 MPa) -> SF ≈ 21,9.
        """
        from hrma.data.materials_db import get_material
        md = _imalat_govdesi()
        kamara = md['structural_analysis']['chamber_analysis']
        kamara_basinci_pa = 20e5
        r_i = 1000.0 * md['chamber_diameter'] / 2.0
        r_o = r_i + kamara['wall_thickness_used_mm']
        tepe_cember_pa = (kamara_basinci_pa * (r_o ** 2 + r_i ** 2)
                          / (r_o ** 2 - r_i ** 2))
        kamara['safety_factor_total'] = (
            get_material('steel_4130')['yield_strength'] / tepe_cember_pa)
        r = client.post('/api/export-dxf', json={'motor_data': md})
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
