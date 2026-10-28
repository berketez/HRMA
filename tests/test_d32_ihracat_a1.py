"""ÖH D32 / ihracat a1 — OH-D31-16: iki katı üreticisi AYNI motoru anlatır.

ÖLÇÜLEN KUSUR (taban ``dd1dcddc``, ``docs/scofield/raw/OH/D32/ihracat/a1/
once_oh_d31_16.json``). Ham ``/calculate_liquid`` sonucu iki katı üreticisine
verildiğinde çizilen parça kümeleri ayrışıyordu::

    STL  (cad_visualization)  -> chamber, nozzle              (2 parça)
    STEP (step_export)        -> chamber, injector, nozzle    (3 parça)

``/api/export-complete-zip`` bu ayrışmayı yakalayıp paketi **HTTP 422** ile
reddediyordu (``status = generators_disagree_on_parts``,
``only_in_step = ['injector']``). Kapı DOĞRU davranıyordu — aynı ZIP'ten iki
farklı makine okunamaz — ama sonuç şuydu: **sıvı motorun komple tasarım
paketi üründe hiç üretilemiyordu.** Bekçiler
``tests/test_z5_teslim_kanali.py::TestA4GirdiUyarisiTasima`` (×2) taban
``9d70e9ed``den beri kırmızıydı.

KÖK NEDEN: ÖH D15 / defter P9B1-13 doktrini YARIM uygulanmıştı. O dalgada
ölçülen kusur şuydu — aynı koşuda enjektör plakası DÖRT ayrı sayıydı ve
üreticiler kamaranın ÖN KAPAK kalınlığını plaka yerine koyuyordu (mesh/gerçek
oranı 10,0x). ``cad_visualization`` ``_injector_plate_design``e bağlandı:
plaka kalınlığı yayımlanmamışsa plaka çizilmez, tartılmaz, ihraç edilmez.
``step_export`` bağlanmadı; ``t_inj = cap_design['flat_mm']`` ile TAM O YASAK
İKAMEYİ sürdürdü ve kapak da yoksa saf bir üreteç sabitine
(0,9 × kapak, 6-24 mm kelepçesi) düşüyordu.

Çelişki iki bekçi arasında AYNI DOSYADA, AYNI FİKSTÜRDE duruyordu::

    tests/test_export_generators.py::TestSTLQuality
        ::test_injector_orifices_actually_drilled  -> STL'de plaka YOK
    tests/test_export_generators.py::TestSTEP
        ::test_step_assembly_roundtrip             -> STEP'te plaka VAR

Plaka kalınlığı HRMA'da TÜRETİLMEZ: kullanıcının enjektör panelinden gelir
(``hrma/utils/injector_design.py``: ``injector_plate_structural`` kalınlığı
çağırandan alır, ``plate_thickness_earned`` ile künyeler; kendi hesapladığı
``required_thickness_mm`` yapısal GEREKSİNİMDİR, tasarım değil). Dolayısıyla
fail-closed hüküm tektir: kalınlık yoksa plaka İKİ üreticide de çizilmez.
"""

import contextlib
import io
import json
import os

import pytest

from tests.support import form_defaults

from tests.bagimlilik_kapisi import kurulu_mu
from tests.support.kanit import kanit_gerekli

_B123D = kurulu_mu('build123d')
_kati_gerekli = pytest.mark.skipif(
    not _B123D, reason='build123d kurulu değil (gerekçe DOĞRULANDI: find_spec)')

#: Montaj dosyaları parça listesinde sayılmaz (kapının kendi sözleşmesi).
_BIRLESIK = {'motor_assembly', 'assembly'}

#: Enjektör panelinin TASARLANAN plaka kalınlığı [mm] — ürün yolunda
#: kullanıcıdan gelir.
PANEL_PLAKA_MM = 6.0

Z5_SIVI = {
    'fuel_type': 'rp1', 'oxidizer_type': 'lox', 'thrust': 10000,
    'chamber_pressure': 100, 'mixture_ratio': 2.5,
    'nozzle_expansion_ratio': 50, 'max_burn_duration': 400,
    'combustion_efficiency': 97, 'contraction_ratio': 4,
    'characteristic_length': 1.2, 'chamber_wall_thickness': 1,
    'cooling_type': 'regenerative', 'injector_type': 'impinging',
    'engine_cycle': 'pressure_fed', 'safety_factor': 2.5,
    # v3.0.1 T-ÇAPA-B: basınç beslemede ``feed_pressure`` yoksa uç 422
    # ``pressure_fed_feed_pressure_not_supplied`` (L-A SV-03); sayfanın
    # gönderdiği şablon varsayılanı (tek kaynak, kopyalanmaz).
    'feed_pressure': form_defaults.sayisal_varsayilanlar('liquid')[
        'feed_pressure'],
}


def _quiet(fn, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


def _panel_plakali(sonuc, t_mm=PANEL_PLAKA_MM):
    """Kullanıcının enjektör panelinden gelen TASARLANAN plakayı ekler."""
    r = dict(sonuc)
    r['injector_results'] = {
        'plate_structural': {
            'status': 'analyzed',
            'plate_thickness_mm': float(t_mm),
            'material': 'stainless_steel_316',
        },
    }
    return r


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(scope='module')
def sivi(client):
    r = client.post('/calculate_liquid', json=Z5_SIVI)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


def _stl_parcalari(sonuc):
    """STL üreticisinin ÇİZDİĞİ parça adları (montaj hariç)."""
    from hrma.app import cad_designer
    cad = _quiet(cad_designer.generate_3d_motor_assembly, dict(sonuc))
    adlar = {os.path.splitext(os.path.basename(p))[0].lower()
             for p in _quiet(cad_designer.export_stl_files,
                             cad['assembly_meshes'])}
    return adlar - _BIRLESIK


def _step_parcalari(sonuc, out_dir, motor_type='liquid'):
    """STEP üreticisinin ÇİZDİĞİ parça adları (montaj hariç)."""
    from hrma.export.step_export import generate_step_assembly
    files = _quiet(generate_step_assembly, sonuc, out_dir=str(out_dir),
                   motor_type=motor_type)
    return {str(k).lower() for k in files} - _BIRLESIK


# ---------------------------------------------------------------------------
# A — kusurun kendisi: iki üretici aynı parça listesini çizer
# ---------------------------------------------------------------------------
class TestIkiUreticiAyniParcaListesi:

    @_kati_gerekli
    def test_plaka_kalinligi_yoksa_ikisi_de_enjektor_cizmez(self, sivi,
                                                            tmp_path):
        """ÖLÇÜLEN KUSUR: STEP çiziyordu, STL çizmiyordu.

        Taban ``dd1dcddc``: ``only_in_step = ['injector']``. Bu bekçi
        ayrışmanın KENDİSİNİ ölçer — bir ucun HTTP hükmünü değil.
        """
        from hrma.export.cad_visualization import _injector_plate_design
        # Fikstürün önkoşulu GERÇEKTEN kurulu mu: plaka kalınlığı YOK.
        assert _injector_plate_design(sivi)['thickness_m'] is None, (
            'fikstür kurulamadı: bu koşu bir plaka kalınlığı yayımlıyor, '
            'oysa bekçi kalınlığın YOKLUĞUNU ölçüyor')
        stl = _stl_parcalari(sivi)
        step = _step_parcalari(sivi, tmp_path)
        assert 'injector' not in step, (
            'plaka kalınlığı çözülemiyor ama STEP enjektör parçası çizmiş — '
            'kalınlık kamaranın ön kapağından ya da bir üreteç sabitinden '
            'türetilmiş olabilir (ÖH D15 / P9B1-13 bunu reddeder)')
        assert 'injector' not in stl, 'STL enjektör çizmiş (kardeş sözleşme)'
        assert stl == step, (
            'iki katı üreticisi AYNI motordan farklı parça listesi çizdi: '
            f'STL={sorted(stl)} STEP={sorted(step)} '
            f'yalnız_STL={sorted(stl - step)} yalnız_STEP={sorted(step - stl)}')

    @_kati_gerekli
    def test_plaka_kalinligi_kazanildiginda_ikisi_de_enjektor_cizer(
            self, sivi, tmp_path):
        """Fail-closed'ın TERS YÖNÜ: kapı parçayı tümden öldürmez.

        Kalınlık kullanıcının panelinden geldiğinde plaka İKİ üreticide de
        çizilmelidir; yoksa onarım, kusuru "her şeyi reddet" ile örtmüş
        olurdu.
        """
        r = _panel_plakali(sivi)
        from hrma.export.cad_visualization import _injector_plate_design
        assert _injector_plate_design(r)['thickness_m'] == pytest.approx(
            PANEL_PLAKA_MM / 1000.0)
        step = _step_parcalari(r, tmp_path)
        assert 'injector' in step, (
            'plaka kalınlığı kazanıldığı hâlde STEP enjektör çizmiyor — '
            'kapı parçayı tümden öldürmüş')

    @_kati_gerekli
    def test_step_plakasi_kalinligi_panelden_okur(self, sivi, tmp_path):
        """TEK KAYNAK: çizilen kalınlık panelin sayısıdır, kapağın değil.

        Taban ``dd1dcddc``: kalınlık ``cap_design['flat_mm']`` (kamara ön
        kapağı) idi. Bu bekçi, panelin 6,00 mm'sinin dosyaya indiğini ve
        künyenin kaynağı adıyla söylediğini ölçer.
        """
        from hrma.export.step_export import generate_step_assembly
        files = _quiet(generate_step_assembly, _panel_plakali(sivi),
                       out_dir=str(tmp_path), motor_type='liquid')
        metin = ''.join(open(files['injector'], encoding='utf-8',
                             errors='ignore').read().split())
        assert f'plate{PANEL_PLAKA_MM:.2f}mm'.replace(' ', '') in metin, (
            'enjektör STEP dosyası panelin plaka kalınlığını taşımıyor: '
            f'{metin[:300]!r}')
        assert 'injector_results.plate_structural' in metin.replace(
            '\\X2\\', ''), (
            'künye kalınlığın KAYNAĞINI söylemiyor')
        assert 'ASSUMEDplatethickness' not in metin, (
            'uydurma plaka kalınlığı beyanı geri gelmiş — beyan çözüm '
            'değildir, kalınlık ÜRETİLMEZ')

    @_kati_gerekli
    def test_cizilmeyen_enjektor_montaj_adinda_beyan_edilir(self, sivi,
                                                            tmp_path):
        """Sessiz eksilme yok: paketi açan imalatçı gerekçeyi görür."""
        from hrma.export.step_export import generate_step_assembly
        files = _quiet(generate_step_assembly, sivi, out_dir=str(tmp_path),
                       motor_type='liquid')
        metin = ''.join(open(files['assembly'], encoding='utf-8',
                             errors='ignore').read().split())
        assert 'injectorplateNOTmodelled' in metin, (
            'çizilmeyen enjektörün gerekçesi montaj adında yok — parça '
            f'sessizce eksilmiş: {metin[:400]!r}')

    @_kati_gerekli
    def test_uretec_yedegi_geri_gelmemis(self):
        """Ters-mutasyon çapası: kaldırılan üreteç kuralı geri konmasın."""
        from hrma.export import step_export
        for ad in ('INJECTOR_PLATE_FALLBACK_CAP_FRACTION',
                   'INJECTOR_PLATE_FALLBACK_MIN_MM',
                   'INJECTOR_PLATE_FALLBACK_MAX_MM'):
            assert not hasattr(step_export, ad), (
                f'{ad} geri gelmiş: plaka kalınlığı yine üreteç sabitinden '
                'türetilebilir ve iki üretici yeniden ayrışır')


# ---------------------------------------------------------------------------
# B — ürün yüzü: komple paket gerçekten yayımlanıyor
# ---------------------------------------------------------------------------
class TestKomplePaketYayimlaniyor:

    @_kati_gerekli
    def test_sivi_kosumda_paket_422_degil_200(self, client, sivi):
        """ÖLÇÜLDÜ (taban dd1dcddc): 422 generators_disagree_on_parts.

        Paket üretilemiyordu; artık üretiliyor ve İÇİNDE iki üreticinin de
        aynı parçaları var.
        """
        import zipfile
        from io import BytesIO
        r = client.post('/api/export-complete-zip', json={'motor_data': sivi})
        assert r.status_code == 200, r.get_data(as_text=True)[:400]
        adlar = zipfile.ZipFile(BytesIO(r.data)).namelist()
        stl = {os.path.splitext(os.path.basename(a))[0].lower()
               for a in adlar if a.startswith('stl/')} - _BIRLESIK
        step = {os.path.basename(a).rsplit('.', 1)[0].split('_')[-1].lower()
                for a in adlar if a.startswith('step/')} - _BIRLESIK
        assert stl and step, f'pakette katı yok: {sorted(adlar)}'
        assert stl == step, (
            f'paketteki iki katı kümesi ayrışıyor: STL={sorted(stl)} '
            f'STEP={sorted(step)}')

    @_kati_gerekli
    def test_generate_complete_package_de_ayni_hukmu_verir(self, client,
                                                           sivi):
        """Kardeş uç aynı kapıyı kullanır; ikisi birden düzelmeli.

        OH-D31-02 ÜRÜN KARARI (ana model, 15 Eyl): bu uç 2.6.27'de ürün
        yüzüne bağlanmaz, emekli de edilmez — 'yalnız API' olarak yaşar.
        Dolayısıyla bekçisi HTTP sözleşmesini ölçer.
        """
        r = client.post('/api/generate-complete-package',
                        json={'motor_data': sivi})
        govde = r.get_data(as_text=True)[:400]
        assert 'generators_disagree_on_parts' not in govde, (
            'kardeş uç hâlâ parça ayrışması hükmü veriyor: ' + govde)


# ---------------------------------------------------------------------------
# C — kapı KORUNUR: gerçek ayrışma hâlâ reddedilir
# ---------------------------------------------------------------------------
class TestKapiKorunur:
    """Onarım, 422 kapısını SÖKMEDİ — kapı doğru davranıyordu.

    Bu bekçi olmadan, "ayrışmayı kapıyı kaldırarak çözme" mutasyonu sessiz
    kalırdı: paket iki farklı makineyi anlatıp 200 dönerdi.
    """

    def test_ayrisma_kapisi_kaynakta_duruyor(self):
        import inspect
        from hrma import app as app_mod
        kaynak = inspect.getsource(app_mod.export_complete_zip)
        assert 'generators_disagree_on_parts' in kaynak, (
            'parça ayrışması kapısı sökülmüş — iki farklı makineyi anlatan '
            'paket yeniden yayımlanabilir')
        assert 'only_in_stl' in kaynak and 'only_in_step' in kaynak, (
            'kapı ayrışan parçayı ADIYLA söylemiyor')

    def test_bos_enjektor_blogu_hala_reddedilir(self, sivi, tmp_path):
        """Plaka kapısı, ORİFİS REDDİNİ yutmaz (sıra sözleşmesi).

        Kusuru gören mutasyon: plaka kapısını orifis reddinin ÖNÜNE almak.
        O sırada 'enjektör iddia ediliyor ama delikleri çözülemiyor' hâli
        sessizce parçasız bir pakete dönüşür.
        """
        pytest.importorskip('build123d')
        from hrma.export.step_export import generate_step_assembly
        r = _panel_plakali(sivi)
        r['injector_design'] = {}
        r.pop('injector', None)
        r.pop('injector_design_detail', None)
        with pytest.raises(ValueError):
            _quiet(generate_step_assembly, r, out_dir=str(tmp_path),
                   motor_type='liquid')


# ---------------------------------------------------------------------------
# D — ölçüm kaydı: kanıt dosyaları koşulan betikten üretildi
# ---------------------------------------------------------------------------
def test_once_sonra_olcumleri_kayitli():
    """Kanıt paketi dosyada durur (Doktrin 2: sayı üretmeyen onarım yok)."""
    kok = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), 'docs', 'scofield', 'raw', 'OH', 'D32',
        'ihracat', 'a1')
    once = json.load(open(kanit_gerekli(os.path.join(kok, 'once_oh_d31_16.json')),
                          encoding='utf-8'))
    sonra = json.load(open(kanit_gerekli(os.path.join(kok, 'sonra_oh_d31_16.json')),
                           encoding='utf-8'))
    assert once['ayrisiyor'] is True, 'ÖNCE ölçümü kusuru göstermiyor'
    assert once['yalniz_step'] == ['injector']
    assert once['uc_export_complete_zip']['status'] == 422
    assert sonra['ayrisiyor'] is False, 'SONRA ölçümü hâlâ ayrışıyor'
    assert sonra['yalniz_step'] == [] and sonra['yalniz_stl'] == []
    assert sonra['uc_export_complete_zip']['status'] == 200
