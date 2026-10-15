# -*- coding: utf-8 -*-
"""ÖH Dalga-17 · kulvar **ihracat** · aşama 1 — bekçiler.

Kapsanan kalemler:

- **P7B3-35** (Fable-D15 ŞART) + **OH-D16-02** ``/api/export-stl`` işaret
  kapısı STL sözleşmesinin zorunlu alanı ``port_diameter``ı taramıyordu:
  ``port_diameter = -0,05`` → HTTP 200 + 281.684 baytlık STL. Kardeş CAD
  uçları (``/export_solid_motor_cad``, ``/export_liquid_cad``) tek bozuk
  ölçüde ham 500 veriyordu.
- **P9B3-11** (Fable-D15 ŞART) sıvı .eng'inde zarf-kütle ayrışması yalnız
  yorum satırındaydı; makine-okur ``eng_envelope_warning`` alanı yoktu.
- **P9B4-01** (Fable-D15 ŞART) + **OH-D16-14** künyesiz CEA önbellek /
  çevrimdışı depo kaydı SI diye servis ediliyordu.
- **OH-D16-03** (+ **P9B1-16** daraltılmış başlığı)
  ``generate_3d_motor_assembly`` uydurma Ø0,1 / boğaz 0,02 / çıkış 0,04
  varsayılanlarıyla CAD üretiyordu.
- **P15B4-05** ``cad_design`` adı altında üç farklı şekil.
- **OH-Z2-01** ihraç künyesinin DEĞERİNİ kilitleyen bekçi yoktu.

Her bekçi ters mutasyonla kırmızıya çevrilebildiği ölçülerek yazıldı;
mutasyon defteri ``docs/scofield/raw/OH/D17/ihracat/a1/04_mutasyon.txt``.
"""
import contextlib
import io
import json
import math
import os

import pytest

from hrma.app import app
from tests.bagimlilik_kapisi import kurulu_mu

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: STEP üreten düğümlerin kapısı. CI'ın ana ``pytest`` işi build123d'yi
#: BİLEREK kurmaz; bu düğümler orada atlanır, ``step-export`` işinde koşar.
#: Kurulum sorusu find_spec ile sorulur (``tests/bagimlilik_kapisi.py``):
#: ``step_export.BUILD123D_AVAILABLE`` ``except Exception`` ile kurulduğu
#: için "kurulu değil" gerekçesine dayanak olamaz
#: (``test_ci_kapsam_kapisi.py::TestAtlamaGerekcesiDurust``).
_STEP_GEREKLI = pytest.mark.skipif(
    not kurulu_mu('build123d'),
    reason='build123d kurulu değil (STEP üretimi atlanır)')


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


@pytest.fixture(scope='module')
def istemci():
    app.config['TESTING'] = True
    return app.test_client()


#: Sağlıklı hibrit gövde — kapıların GEÇİRMESİ gerekeni ölçmek için.
SAGLIKLI_HIBRIT = {
    'motor_type': 'hybrid', 'chamber_diameter': 0.15, 'chamber_length': 0.30,
    'throat_diameter': 0.03, 'exit_diameter': 0.06, 'port_diameter': 0.05,
}
SAGLIKLI_KATI = {
    'motor_type': 'solid', 'chamber_diameter': 0.1, 'chamber_length': 0.4,
    'throat_diameter': 0.02, 'exit_diameter': 0.04,
}


# =====================================================================
# P7B3-35 (ŞART) + OH-D16-02 — işaret kapısı STL sözleşmesini tarasın
# =====================================================================
class TestP7B335IsaretKapisiPortCapi:

    def test_negatif_port_capi_422_ve_alan_adi(self, istemci):
        """ÖLÇÜM (taban 2426b4d): 200 + 281.684 B STL. Artık 422."""
        govde = dict(SAGLIKLI_HIBRIT, port_diameter=-0.05)
        r = _sessiz(istemci.post, '/api/export-stl',
                    json={'motor_data': govde})
        assert r.status_code == 422, (
            'negatif port çapı imal edilemez bir katıdır; STL yazılmamalı')
        j = r.get_json()
        assert j['error'] == 'invalid_export_geometry'
        # Kullanıcı hangi alanı düzelteceğini ADIYLA görmeli.
        alanlar = [f['field'] for f in j['invalid_fields']]
        assert 'port_diameter' in alanlar
        gerekce = [f['reason'] for f in j['invalid_fields']
                   if f['field'] == 'port_diameter']
        assert gerekce == ['must_be_positive']

    def test_isaret_kapisi_STL_sozlesmesinin_TAMAMINI_tariyor(self):
        """Alan listesi İKİNCİ KEZ YAZILMAZ: iki sözleşmenin birleşimi.

        Kusurun kökü bir unutulmuş addı, tek bir vaka değil. Bekçi bu
        yüzden vakayı değil SÖZLEŞMEYİ kilitler: ``_STL_REQUIRED_FIELDS``e
        yarın eklenecek bir ad da kapıya girmek zorundadır.
        """
        import hrma.app as A
        taranan = set(A._sign_checked_geometry_fields())
        sozlesme = set()
        for adlar in A._STL_REQUIRED_FIELDS.values():
            sozlesme.update(adlar)
        assert sozlesme <= taranan, (
            f'işaret kapısının görmediği zorunlu alan: '
            f'{sorted(sozlesme - taranan)}')
        # Üretici listesi de korunur (daraltma değil, genişletme).
        assert set(A._EXPORT_GEOMETRY_FIELDS) <= taranan

    def test_saglikli_govde_hala_STL_uretiyor(self, istemci):
        """ÖK-22: kapı sağlıklı envanteri daraltmaz."""
        r = _sessiz(istemci.post, '/api/export-stl',
                    json={'motor_data': dict(SAGLIKLI_HIBRIT)})
        assert r.status_code == 200
        assert len(r.get_data()) > 100_000

    def test_kati_cad_ucu_SIFIR_olcude_ham_500_vermiyor(self, istemci):
        """ÖLÇÜM (taban): chamber_diameter 0 → HTTP 500 + gövdede paket
        README metni. Sunucu bozulmadı; istemcinin ölçüsü bozuktu.

        Sıfır İŞARET kapısının konusu değildir (negatif değil): burada
        üreticilerin adlı reddi (``no_exportable_artifacts``) beklenir.
        """
        govde = dict(SAGLIKLI_KATI, chamber_diameter=0)
        r = _sessiz(istemci.post, '/export_solid_motor_cad',
                    json={'motor_data': govde})
        assert r.status_code == 422, 'üretici reddi 500 ile bildirilemez'
        j = r.get_json()
        assert j['status'] == 'no_exportable_artifacts'
        # Gerekçe ÜRETİCİ BAŞINA taşınır, tek dizeye ezilmez.
        assert j['failed_generators']
        assert all('generator' in g and 'reason' in g
                   for g in j['failed_generators'])

    def test_kati_cad_ucu_NEGATIF_olcude_ISARET_kapisina_takiliyor(
            self, istemci):
        """ŞART (Fable-D17, OH-D16-02): eski gövde ``j['status'] in
        ('error', 'no_exportable_artifacts')`` diyordu; negatif ölçü
        ÜRETİCİNİN de reddettiği bir gövde olduğu için kapı sökülse bile
        422 geliyor ve bekçi bunu göremiyordu (ölçüldü: kapıyı iki uçtan
        söken MC mutasyonunda sınıf 8/8 YEŞİL kalıyordu).

        Bu yüzden ŞART koşulan hüküm ÜRETİCİ REDDİ DEĞİL, İŞARET KAPISI:
        ``invalid_export_geometry`` + alan adı + ``must_be_positive``.
        """
        govde = dict(SAGLIKLI_KATI, chamber_diameter=-0.1)
        r = _sessiz(istemci.post, '/export_solid_motor_cad',
                    json={'motor_data': govde})
        assert r.status_code == 422, 'üretici reddi 500 ile bildirilemez'
        j = r.get_json()
        assert j['status'] == 'error'
        assert j['error'] == 'invalid_export_geometry', (
            'negatif ölçü işaret kapısında durmalı; üreticinin ayrı '
            'gerekçesiyle 422 olması kapının yerini tutmaz')
        assert {'field': 'chamber_diameter',
                'reason': 'must_be_positive'} in [
                    {'field': f['field'], 'reason': f['reason']}
                    for f in j['invalid_fields']]

    def test_sivi_cad_ucu_NEGATIF_olcude_ISARET_kapisina_takiliyor(
            self, istemci):
        """ŞART (Fable-D17, OH-D16-02) 2. yarısı: sıvı uç için negatif-ölçü
        vakası HİÇ YOKTU. Gövde bu ucun sözleşmesindeki gibi MİLİMETRE.
        """
        r = _sessiz(istemci.post, '/export_liquid_cad',
                    json={'motor_data': {
                        'motor_type': 'liquid', 'chamber_diameter': -100.0,
                        'chamber_length': 400.0, 'throat_diameter': 20.0,
                        'exit_diameter': 40.0}})
        assert r.status_code == 422
        j = r.get_json()
        assert j['status'] == 'error'
        assert j['error'] == 'invalid_export_geometry'
        assert {'field': 'chamber_diameter',
                'reason': 'must_be_positive'} in [
                    {'field': f['field'], 'reason': f['reason']}
                    for f in j['invalid_fields']]

    @_STEP_GEREKLI
    def test_sivi_cad_ucu_uretici_reddini_adiyla_tasiyor(self, istemci):
        """ÖLÇÜM (taban): metre cinsinden gövde → 500 + README başlığı."""
        r = _sessiz(istemci.post, '/export_liquid_cad',
                    json={'motor_data': dict(SAGLIKLI_HIBRIT)})
        assert r.status_code == 422
        j = r.get_json()
        assert j['status'] == 'no_exportable_artifacts'
        gerekceler = ' '.join(g['reason'] for g in j['failed_generators'])
        # Üreticinin ADLI reddi kullanıcıya ULAŞMALI.
        assert 'chamber_length' in gerekceler

    def test_kati_cad_ucu_saglikli_govdede_hala_paket_veriyor(self, istemci):
        """ÖK-22 kilidi. Bu ucun sözleşmesi MİLİMETREdir (girdisi
        ``/calculate_solid`` sonucudur), o yüzden gövde de mm."""
        r = _sessiz(istemci.post, '/export_solid_motor_cad',
                    json={'motor_data': {
                        'motor_type': 'solid', 'chamber_diameter': 100.0,
                        'chamber_length': 400.0, 'throat_diameter': 20.0,
                        'exit_diameter': 40.0}})
        assert r.status_code == 200
        assert r.get_data()[:2] == b'PK'

    def test_kati_cad_ucu_METRE_govdeyi_ARTIK_cizmiyor(self, istemci):
        """ÖLÇÜM (taban 2426b4d): metre cinsinden gövde 200 + 113.703 B ZIP
        veriyordu; içindeki STL Ø100 mm'lik UYDURMA varsayılan gövdeydi
        (çünkü 0,1 mm kamara birimini kazanamıyor ve düşürülüyor). STEP
        üreticisi aynı gövdeyi ZATEN reddediyordu — paket içi çelişki."""
        r = _sessiz(istemci.post, '/export_solid_motor_cad',
                    json={'motor_data': dict(SAGLIKLI_KATI)})
        assert r.status_code == 422
        gerekce = ' '.join(g['reason']
                           for g in r.get_json()['failed_generators'])
        assert 'chamber_diameter' in gerekce


# =====================================================================
# P9B3-11 (ŞART) — zarf-kütle ayrışması MAKİNE-OKUR
# =====================================================================
def _sivi_zarf_fikstürü():
    """İticiyi TUTMAYAN kamara zarfı + beyan edilmiş tanklar.

    Sayılar Fable-D15'in bağımsız ölçümüyle aynı çalışma noktasından:
    zarf 103,19 x 69,99 mm, 1025,28 kg itici, tanklar 1.211,6 L.
    """
    d1, l1 = 605.138, 1512.845
    d2, l2 = 734.012, 1835.029
    v_m3 = (math.pi / 4 * (d1 / 1000) ** 2 * (l1 / 1000)
            + math.pi / 4 * (d2 / 1000) ** 2 * (l2 / 1000))
    return {
        'motor_type': 'liquid', 'motor_name': 'D17-ZARF',
        'chamber_diameter': 0.10319, 'chamber_length': 0.06999,
        'throat_diameter': 0.049, 'exit_diameter': 0.098,
        'propellant_mass': 1025.28, 'total_impulse': 2.5e6,
        'burn_time': 30.0, 'thrust': 83000.0,
        'propellant_tanks': {
            'fuel_tank': {'dimensions': {'diameter': d1, 'length': l1}},
            'oxidizer_tank': {'dimensions': {'diameter': d2, 'length': l2}},
            'system_summary': {'total_volume': v_m3 * 1000.0},
        },
    }


class TestP9B311ZarfUyarisiMakineOkur:

    def test_uretici_makine_okur_kayit_yaziyor(self):
        from hrma.export.openrocket_integration import OpenRocketExporter
        rapor = {}
        icerik = _sessiz(OpenRocketExporter().export_motor_file,
                         _sivi_zarf_fikstürü(), report=rapor)
        assert icerik, 'sıvı yolu ret değil: dosya BEYANLA yazılır'
        kayit = rapor['eng_envelope_warning']
        assert kayit is not None, (
            'zarf iticiyi tutmuyor; bunu yalnız yorum satırında söylemek '
            'RASP tüketicisi ve arayüz için görünmez demektir')
        assert kayit['error'] == 'propellant_outside_envelope'
        # Sayılar UYDURULMAZ: dosyanın kendi yorumuyla AYNI olmalı.
        assert kayit['envelope_diameter_mm'] == pytest.approx(103.19, abs=0.01)
        assert kayit['propellant_mass_kg'] == pytest.approx(1025.28)
        assert kayit['envelope_bulk_density_kg_m3'] > 1e6
        assert kayit['declared_tank_bulk_density_kg_m3'] == pytest.approx(
            846.2, abs=0.5)
        assert kayit['declared_tank_volume_m3'] == pytest.approx(1.2116,
                                                                 abs=1e-3)
        # Üst sınır İKİNCİ KEZ YAZILMAZ: deponun tek tanım noktasından.
        from hrma.data.propellants_db import PROPELLANT_DENSITY_RANGE_KG_M3
        assert (kayit['propellant_density_upper_bound_kg_m3']
                == PROPELLANT_DENSITY_RANGE_KG_M3[1])
        assert kayit['declared_tank_source']

    def test_kayit_dosyanin_yorum_satiriyla_ayni_hukmu_veriyor(self):
        """Beyan iki yerde: dosya + API. İkisi ÇELİŞEMEZ."""
        from hrma.export.openrocket_integration import OpenRocketExporter
        rapor = {}
        icerik = _sessiz(OpenRocketExporter().export_motor_file,
                         _sivi_zarf_fikstürü(), report=rapor)
        yorum_var = any('NOT inside the envelope' in s
                        for s in icerik.splitlines())
        assert yorum_var == (rapor['eng_envelope_warning'] is not None)

    def test_saglikli_motorda_uyari_YOK(self):
        """Yanlış pozitif olmasın: zarfı tutan motorda alan None."""
        from hrma.export.openrocket_integration import OpenRocketExporter
        md = {'motor_type': 'solid', 'motor_name': 'D17-SAG',
              'chamber_diameter': 0.1048, 'chamber_length': 0.6,
              'throat_diameter': 0.02, 'exit_diameter': 0.04,
              'propellant_mass': 6.468, 'total_impulse': 12000.0,
              'burn_time': 3.0, 'thrust': 4000.0}
        rapor = {}
        _sessiz(OpenRocketExporter().export_motor_file, md, report=rapor)
        assert rapor['eng_envelope_warning'] is None

    def test_calculate_blogu_alani_yayimliyor(self, istemci):
        """``eng_error`` ile AYNI blokta, aynı şemada."""
        r = _sessiz(istemci.post, '/calculate', json={
            'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
            'chamber_pressure': 20.0, 'fuel_type': 'htpb',
            'oxidizer_type': 'n2o'})
        assert r.status_code == 200
        orb = r.get_json()['openrocket']
        assert 'eng_envelope_warning' in orb, (
            'alan blokta HİÇ yoktu (ölçüldü); varlığı sözleşmedir')
        assert 'eng_error' in orb

    def test_export_eng_ucu_ayni_alani_yayimliyor(self, istemci):
        r = _sessiz(istemci.post, '/api/export-eng',
                    json={'motor_data': _sivi_zarf_fikstürü()})
        assert r.status_code == 200
        j = r.get_json()
        assert j['eng_envelope_warning'] is not None
        assert (j['eng_envelope_warning']['error']
                == 'propellant_outside_envelope')

    def test_rapor_sozlugu_istekler_arasinda_TASINMIYOR(self):
        """Paylaşılan örnek niteliği = sızıntı. İki ayrı rapor karışmamalı."""
        from hrma.export.openrocket_integration import OpenRocketExporter
        e = OpenRocketExporter()
        r1, r2 = {}, {}
        _sessiz(e.export_motor_file, _sivi_zarf_fikstürü(), report=r1)
        md = {'motor_type': 'solid', 'motor_name': 'D17-SAG',
              'chamber_diameter': 0.1048, 'chamber_length': 0.6,
              'throat_diameter': 0.02, 'exit_diameter': 0.04,
              'propellant_mass': 6.468, 'total_impulse': 12000.0,
              'burn_time': 3.0, 'thrust': 4000.0}
        _sessiz(e.export_motor_file, md, report=r2)
        assert r1['eng_envelope_warning'] is not None
        assert r2['eng_envelope_warning'] is None


# =====================================================================
# P9B4-01 (ŞART) + OH-D16-14 — künyesiz CEA kaydı yayımlanamaz
# =====================================================================
class TestP9B401BirimKunyesi:

    def test_kunyesiz_kayit_reddediliyor(self):
        """ÖLÇÜM (taban): künyesiz {c*: 2500, T: 4500} kapıdan GEÇİYORDU.

        Fiziksel tavan (3000 m/s) tek başına yetmez: 2500 ft/s = 762 m/s,
        yani bandın altında kalan emperyal kayıt görünmez.
        """
        from hrma.data import web_propellant_api as W
        ihlal = W._birim_sozlesmesi_ihlali(
            {'c_star': 2500.0, 'chamber_temperature': 4500.0})
        assert ihlal is not None
        assert 'unit label' in ihlal

    def test_etiketli_SI_kaydi_hala_geciyor(self):
        """ÖK-22: sağlıklı envanter daralmaz."""
        from hrma.data import web_propellant_api as W
        assert W._birim_sozlesmesi_ihlali({
            'c_star': 1800.0, 'c_star_units': 'm/s',
            'chamber_temperature': 3500.0,
            'chamber_temperature_units': 'K'}) is None

    def test_yalniz_sicaklik_kunyesi_eksikse_de_reddediliyor(self):
        from hrma.data import web_propellant_api as W
        ihlal = W._birim_sozlesmesi_ihlali({
            'c_star': 1800.0, 'c_star_units': 'm/s',
            'chamber_temperature': 3500.0})
        assert ihlal is not None
        assert 'chamber_temperature' in ihlal

    def test_cevrimdisi_depo_kunyesiz_kaydi_SERVIS_ETMIYOR(self):
        """ÖLÇÜM (taban): depo yolu kaydı c*=2500 ile geri veriyordu."""
        from hrma.data import web_propellant_api as W
        from hrma.data import offline_store
        api = _sessiz(W.WebPropellantAPI)
        gercek = offline_store.get_entry
        offline_store.get_entry = lambda k: {
            'data': {'c_star': 2500.0, 'chamber_temperature': 4500.0,
                     'gamma': 1.2, 'molecular_weight': 22.0},
            'timestamp': '2026-08-20T00:00:00', 'age_seconds': 1000.0,
            'origin': 'user_cache'}
        try:
            assert _sessiz(api._load_offline_store,
                           'webapi:cea|rp1|lox|250|2.5') is None
        finally:
            offline_store.get_entry = gercek

    def test_paketli_anlik_goruntu_kapiyi_GECIYOR(self):
        """Onarım paketi kırmıyor: 4 CEA kaydının 4'ü de künyeli."""
        from hrma.data import web_propellant_api as W
        yol = os.path.join(KOK, 'hrma', 'data', 'offline_snapshot.json')
        with open(yol, encoding='utf-8') as fh:
            snap = json.load(fh)
        sayim = 0
        for _k, v in snap.get('entries', {}).items():
            d = v.get('data') if isinstance(v, dict) and 'data' in v else v
            if isinstance(d, dict) and isinstance(d.get('c_star'),
                                                  (int, float)):
                sayim += 1
                assert W._birim_sozlesmesi_ihlali(d) is None, _k
        assert sayim == 4

    def test_metin_ayristiricisi_kunyeyi_KAZANIYOR(self):
        """Üretici künyeyi yazmazsa okuma kapısı kendi verisini reddeder.

        Künye uydurma DEĞİL: desen 'CSTAR, M/SEC' / 'T, K' başlığını şart
        koşuyor, yani birim ayrıştırmanın kendisinden geliyor.
        """
        from hrma.data import web_propellant_api as W
        api = _sessiz(W.WebPropellantAPI)
        metin = ('Isp, sec  350.5\n CSTAR, M/SEC  1800.0\n'
                 ' T, K  3500.0\n GAMMAs  1.2\n M, (1/n)  22.0\n')
        d = _sessiz(api._parse_cea_output, metin, 'rp1', 'lox')
        assert d['c_star_units'] == 'm/s'
        assert d['chamber_temperature_units'] == 'K'
        assert W._birim_sozlesmesi_ihlali(d) is None


# =====================================================================
# OH-D16-03 (+ P9B1-16) — uydurma çap varsayılanları
# =====================================================================
class TestOHD1603UydurmaCapVarsayilani:

    @pytest.mark.parametrize('govde,ad', [
        ({}, 'boş sözlük'),
        ({'chamber_length': 0.3}, 'yalnız kamara boyu'),
        ({'l_star': 1.0}, 'yalnız L*'),
        ({'chamber_length': 0.3, 'throat_diameter': 0.02,
          'exit_diameter': 0.04}, 'çap hariç her şey'),
    ])
    def test_yayimlanmamis_cap_MOTOR_URETMIYOR(self, govde, ad):
        """ÖLÇÜM (taban): {'chamber_length': 0.3} → Chamber+Nozzle mesh."""
        from hrma.export.cad_visualization import MotorCADDesigner
        d = _sessiz(MotorCADDesigner().generate_3d_motor_assembly, dict(govde))
        assert not (d.get('assembly_meshes') or []), (
            f'{ad}: yayımlanmamış çaptan katı doğuyor')
        assert d.get('error'), f'{ad}: ret gerekçesi ADLANDIRILMALI'

    def test_ret_gerekcesi_ALANI_ADIYLA_soyluyor(self):
        from hrma.export.cad_visualization import MotorCADDesigner
        d = _sessiz(MotorCADDesigner().generate_3d_motor_assembly,
                    {'chamber_length': 0.3})
        assert 'chamber_diameter' in d['error']
        assert 'not_available' in d['error']

    def test_bogaz_ve_cikis_capi_da_kapida(self):
        from hrma.export.cad_visualization import MotorCADDesigner
        tasarimci = MotorCADDesigner()
        d = _sessiz(tasarimci.generate_3d_motor_assembly,
                    {'chamber_diameter': 0.15, 'chamber_length': 0.3})
        assert 'throat_diameter' in d['error']
        d = _sessiz(tasarimci.generate_3d_motor_assembly,
                    {'chamber_diameter': 0.15, 'chamber_length': 0.3,
                     'throat_diameter': 0.03})
        assert 'exit_diameter' in d['error']

    def test_saglikli_govde_hala_mesh_uretiyor(self):
        """ÖK-22: kapı sağlıklı envanteri daraltmaz."""
        from hrma.export.cad_visualization import MotorCADDesigner
        d = _sessiz(MotorCADDesigner().generate_3d_motor_assembly,
                    dict(SAGLIKLI_HIBRIT))
        assert not d.get('error')
        assert len(d['assembly_meshes']) >= 2

    def test_export_cad_ucu_ARTIK_200_success_DEMIYOR(self, istemci):
        """ÖLÇÜM (taban): 200 'success' + 3 STL indirme bağlantısı."""
        r = _sessiz(istemci.post, '/api/export-cad',
                    json={'motor_data': {'chamber_length': 0.3}})
        assert r.status_code == 422
        j = r.get_json()
        assert j['status'] == 'no_exportable_artifacts'
        assert 'chamber_diameter' in j['failed_generators'][0]['reason']

    def test_iki_kardes_uc_ayni_govdeye_AYNI_hukmu_veriyor(self, istemci):
        """Kusurun sınıfı buydu: hükmü geometri değil UCUN KİMLİĞİ veriyordu.

        ÖLÇÜM (taban): aynı gövdeye /api/export-cad 200 + 3 STL,
        /api/export-stl 400. Artık ikisi de reddediyor.
        """
        govde = {'motor_data': {'chamber_length': 0.3}}
        a = _sessiz(istemci.post, '/api/export-cad', json=govde)
        b = _sessiz(istemci.post, '/api/export-stl', json=govde)
        assert a.status_code >= 400 and b.status_code >= 400


# =====================================================================
# OH-Z2-01 — ihraç künyesinin DEĞERİ kilitli
# =====================================================================
def _cizim_satirlari(motor):
    """Çizimin kamara sayfasındaki (etiket, değer) satırları."""
    from hrma.export import drawing_generator as DG
    hazir, d = _sessiz(DG._prepare, motor)
    return _sessiz(DG._schedule_rows, hazir, d)


def _satir(satirlar, etiket):
    for ad, deger in satirlar:
        if ad == etiket:
            return deger
    return None


class TestOHZ201KunyeDegeriKilidi:
    """Künyenin VARLIĞI değil HÜKMÜ kilitlenir (Z2-B'nin açık bıraktığı yarı).

    ÖLÇÜLDÜ (taban ``2426b4d``): ``git grep -l sf_is_measured tests/`` BOŞ —
    çizimin 'verified / NOT a verification' ayrımını hiçbir test metin ya da
    değer düzeyinde şart koşmuyordu. Aşağıdaki iki bekçi o ayrımı ve
    .eng ⟷ çizim çap eşitliğini kilitler.
    """

    @staticmethod
    def _motor(olculen):
        """Emniyet katsayısı ÖLÇÜLMÜŞ / HEDEFTEN GERİ OKUNMUŞ iki koşum.

        İki blok da SAYI yayımlar; fark yalnız o sayının bir ölçüm mü yoksa
        tasarım hedefinin geri okunması mı olduğudur
        (``safety_factor_is_tautological`` / ``design_mode``). Kusurun tam
        yeri buydu: iki hâl aynı satıra aynı biçimde basılıyordu.
        """
        blok = {
            'design_mode': 'size' if not olculen else 'verify',
            'wall_thickness_used_mm': 5.0,
            'recommended_thickness': 5.0 if not olculen else 3.0,
            'safety_factor_total': 0.941 if not olculen else 2.5,
            'safety_factor_is_tautological': not olculen,
        }
        if not olculen:
            blok['design_safety_factor_target'] = 4.0
        return {
            'motor_type': 'solid', 'motor_name': 'D17-KUNYE',
            'chamber_diameter': 0.1, 'chamber_length': 0.4,
            'throat_diameter': 0.02, 'exit_diameter': 0.04,
            'structural_analysis': {'chamber_analysis': blok},
        }

    def test_olculmemis_SF_kunyesi_dogrulama_IDDIA_EDEMEZ(self):
        """ÖLÇÜLDÜ: 0,94'lük SF çizime iniyor. Sayı GİZLENMEZ (1'in altında
        olduğunu imalatçı görmeli) ama 'doğrulandı' İDDİASI geri çekilir."""
        from hrma.export.cad_visualization import _chamber_wall_design
        motor = self._motor(olculen=False)
        tasarim = _sessiz(_chamber_wall_design, motor)
        # Ön koşul: bekçi gerçekten 'ölçülmemiş ama sayı var' hâlini ölçüyor
        # mu? Ölçmüyorsa test inert olurdu (M8 mutasyonunda yakalandı).
        assert tasarim['safety_factor_is_measured'] is False
        assert tasarim['safety_factor'] is not None

        satirlar = _cizim_satirlari(motor)
        sf = _satir(satirlar, 'Safety factor at the drawn wall')
        assert sf is not None and any(ch.isdigit() for ch in str(sf))
        assert 'NOT a verification' in str(sf), (
            f'ölçülmemiş emniyet katsayısı doğrulanmış gibi basılıyor: {sf!r}')
        # Künyenin GEREKÇESİ de düşmeli, yalnız çekince eki değil.
        temel = _satir(satirlar, 'Safety factor basis')
        assert temel and 'NOT a verification' in str(temel)

    def test_olculmus_SF_kunyesi_cekince_TASIMIYOR(self):
        """Ters yarı: ölçülmüşe 'NOT a verification' basmak da yalandır."""
        from hrma.export.cad_visualization import _chamber_wall_design
        motor = self._motor(olculen=True)
        tasarim = _sessiz(_chamber_wall_design, motor)
        assert tasarim['safety_factor_is_measured'] is True
        satirlar = _cizim_satirlari(motor)
        sf = _satir(satirlar, 'Safety factor at the drawn wall')
        assert 'NOT a verification' not in str(sf), (
            'ölçülmüş emniyet katsayısına çekince künyesi basılıyor')
        assert _satir(satirlar, 'Safety factor basis') is None, (
            'ölçülmüşken "basis" satırı yalnız gürültüdür'
        )

    def test_eng_ve_cizim_AYNI_capi_yaziyor(self):
        """Aynı istekten iki dosya AYNI motoru tarif etmeli (paket-içi
        çelişki sınıfı: P15B4-03'ün grain boyu ikizi)."""
        from hrma.export.openrocket_integration import OpenRocketExporter
        md = dict(SAGLIKLI_KATI, motor_name='D17-CAP',
                  propellant_mass=6.468, total_impulse=12000.0,
                  burn_time=3.0, thrust=4000.0)
        icerik = _sessiz(OpenRocketExporter().export_motor_file, md)
        motor_satiri = [x for x in icerik.splitlines()
                        if x and not x.startswith(';')][0]
        eng_cap_mm = float(motor_satiri.split()[1])
        cizim = _satir(_cizim_satirlari(md), 'Chamber inner diameter')
        cizim_mm = float(str(cizim).split()[0])
        assert eng_cap_mm == pytest.approx(cizim_mm, rel=1e-6), (
            f'.eng {eng_cap_mm} mm, çizim {cizim_mm} mm — aynı istekten '
            'çıkan iki dosya aynı çapı yazmıyor')


# =====================================================================
# P15B4-05 — `cad_design` adı altında ÜÇ FARKLI ŞEY (ÖLÇÜM KİLİDİ)
# =====================================================================
class TestP15B405CadDesignAyrismasi:
    """Kalem bu aşamada ONARILMADI; bu sınıf ölçümü KİLİTLER.

    ÖLÇÜLDÜ (taban ``2426b4d``, ``once.json``): aynı ad üç farklı şekil
    taşıyor — ``/calculate_solid`` 9 anahtar (case_design, grain_geometry,
    ...), ``/calculate`` 6 anahtar (assembly_meshes, ...), ``/calculate_liquid``
    ``None``. Onarımın ikinci yarısı ``hrma/engines/solid_rocket_engine.py``
    içindedir (katı kulvarının sahası), bu yüzden burada yalnız ayrışma
    ölçülür ve BÜYÜMESİ engellenir.

    ÖH D27 fix-26a (8 Eylül 2026): hibrit taraf 6 -> 7 anahtar oldu
    (``axis_convention``, ``a201eeed`` / P15B4-01) ve sayım ölçütü KÜME
    EŞİTLİĞİNE çevrildi; kesişim ayağı değişmedi ve hâlâ boştur.
    """

    def test_iki_sema_KESISMIYOR_ve_bu_kayit_altinda(self, istemci):
        r1 = _sessiz(istemci.post, '/calculate_solid', json={
            'motor_type': 'solid', 'thrust': 5000, 'burn_time': 5,
            'chamber_pressure': 30, 'propellant_type': 'APCP'})
        r2 = _sessiz(istemci.post, '/calculate', json={
            'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
            'chamber_pressure': 20.0, 'fuel_type': 'htpb',
            'oxidizer_type': 'n2o'})
        assert r1.status_code == 200 and r2.status_code == 200
        kati = r1.get_json().get('cad_design')
        hibrit = r2.get_json().get('cad_design')
        assert isinstance(kati, dict) and isinstance(hibrit, dict)
        # ÖH D18 (kati a1): katı şekil artık KENDİNİ TANITIYOR
        # (``schema`` = SOLID_CAD_DESIGN_SCHEMA); bu, kalemin katı yarısının
        # ONARIMIDIR, ayrışmanın büyümesi değil. Bu yüzden ``schema``
        # kesişim ve sayım ölçüsünden ÇIKARILIR: kesişim hâlâ boş olmalı ve
        # kalan anahtar sayıları ölçülen 9/6 olmalıdır. Hibrit yarısı
        # etiketlenince ``schema`` iki tarafta da bulunacak ve kesişimden
        # düşüldüğü için bu bekçi yine doğru soruyu sormaya devam edecek.
        ETIKET = {'schema'}
        kati_alanlar = set(kati) - ETIKET
        hibrit_alanlar = set(hibrit) - ETIKET
        ortak = kati_alanlar & hibrit_alanlar
        assert ortak == set(), (
            f'iki şema kesişmeye başladı: {sorted(ortak)} — ayrışma '
            'ölçüsü değişti, kalem yeniden ölçülmeli')
        # ÖLÇÜLEN ANAHTARLAR — sayı değil KÜME (ÖH D27 fix-26a).
        #
        # Eski ölçü ``len(...) == 9 / == 6`` idi ve D26 birleşince kırmızı
        # verdi: hibrit tarafta 6 -> 7. Yedinci anahtar ÖLÇÜLDÜ
        # (``git log -S "'axis_convention'"``): ``a201eeed`` (ÖH D26 ihracat
        # a1, defter P15B4-01) ``axis_convention`` bloğunu ekledi — STEP /
        # STL / DXF için EXPORT_AXIS ile MESH_BUILD_AXIS'i ADIYLA yayımlayan
        # bir KENDİNİ TANITMA alanı, tıpkı ``schema`` gibi. Ayrışmanın
        # büyümesi DEĞİLDİR: yeni anahtar yalnız hibrit tarafta ve kesişim
        # hâlâ boş (ölçüldü: kesişim = {'schema'}, etiket düşülünce boş).
        #
        # Sayı yerine küme yazılmasının sebebi: ``6 -> 7`` yalnız sayıyı
        # gösterir, HANGİ alanın geldiğini söylemez; ayrıca "bir alan gitti,
        # bir alan geldi" durumunu sessizce geçirir. Küme eşitliği ikisini de
        # yakalar ve kırmızı adı yazar — SIKILAŞTIRMADIR.
        KATI_ALANLAR = {
            'assembly_sequence', 'case_design', 'grain_geometry',
            'igniter_system', 'insulation_system', 'manufacturing_drawings',
            'motor_assembly', 'nozzle_design', 'quality_control',
        }
        HIBRIT_ALANLAR = {
            'assembly_mesh_summary', 'axis_convention', 'manufacturing_notes',
            'material_specifications', 'performance_summary',
            'plotly_visualization', 'technical_drawings',
        }
        assert kati_alanlar == KATI_ALANLAR, (
            'katı cad_design anahtar kümesi değişti; eksik '
            f'{sorted(KATI_ALANLAR - kati_alanlar)}, fazla '
            f'{sorted(kati_alanlar - KATI_ALANLAR)} — kalem yeniden ölçülmeli')
        assert hibrit_alanlar == HIBRIT_ALANLAR, (
            'hibrit cad_design anahtar kümesi değişti; eksik '
            f'{sorted(HIBRIT_ALANLAR - hibrit_alanlar)}, fazla '
            f'{sorted(hibrit_alanlar - HIBRIT_ALANLAR)} — kalem yeniden '
            'ölçülmeli')
        # Onarımın katı yarısı: şekil adını TAŞIYOR ve ad sürümlü.
        from hrma.engines.solid_rocket_engine import SOLID_CAD_DESIGN_SCHEMA
        assert kati.get('schema') == SOLID_CAD_DESIGN_SCHEMA
        assert kati['schema'].startswith('hrma.solid.cad_design/')

    def test_ucus_araci_okumasi_HIBRITTE_dusuyor(self):
        """Kusurun ÜRÜNDEKİ sonucu: aynı yol iki şekilde farklı davranıyor."""
        from hrma.analysis import flight_vehicle as FV
        kati_gibi = {'cad_design': {'case_design': {'outer_diameter': 120.0}}}
        hibrit_gibi = {'cad_design': {'assembly_meshes': [],
                                      'performance_summary': {}}}
        assert FV._get(kati_gibi, 'cad_design', 'case_design',
                       'outer_diameter') == 120.0
        assert FV._get(hibrit_gibi, 'cad_design', 'case_design',
                       'outer_diameter') is None
