"""ÖH Dalga-16 / kulvar ihracat, aşama 1 — onarım bekçileri.

Her iddia, onarımdan ÖNCE ölçülmüş bir kusura bağlıdır ve o kusurun TERSİ
enjekte edildiğinde KIRMIZI olur (ters-mutasyon kanıtı; ÖK-05 / P14 kuralı).
Ölçüm dosyaları: ``docs/scofield/raw/OH/D16/ihracat/a1/``.

Kapsanan kalemler:
  OH-Z5-06  chemical_database N2 NASA-7 cp katsayıları
  P9B4-14   materials_db termal servis klampı ⟷ erime noktası
  P16B4-02  /api/export-stl birim sezgisi (iki-okuma birleşimi)
  P16B4-09  /api/export-complete-zip boş paket
  P16B4-15  /api/export-eng RASP başlığında sıfıra yuvarlanan kütle
  P16B4-16  /api/export-drawings-pdf çizicisi düşünce sessiz küçülme
  P13B3-03  data/validation çapalarının tüketicisi
"""
import io
import json
import os
import zipfile

import pytest

from hrma.app import app
from hrma.data.chemical_database import ChemicalDatabase
from hrma.data.materials_db import MATERIALS, _validate_materials


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def iyi_motor():
    """Ölçüm betiklerindeki İYİ gövde (once_uc.json ile aynı)."""
    return {
        'motor_name': 'FUZZBASE', 'motor_type': 'solid',
        'chamber_diameter': 0.1, 'chamber_length': 0.3,
        'throat_diameter': 0.02, 'exit_diameter': 0.05,
        'chamber_pressure': 40.0, 'thrust': 1000.0, 'burn_time': 5.0,
        'propellant_mass': 2.0, 'total_impulse': 5000.0,
    }


# ---------------------------------------------------------------------------
# OH-Z5-06 — N2 cp katsayıları JANAF'ı tutturmalı
# ---------------------------------------------------------------------------
#: NIST-JANAF (Chase 1998) N2 gaz cp [J/mol/K]. Bu sayılar bir ÖLÇÜMDÜR,
#: modelden türetilmez — bekçinin eşiği kendi koruduğu koddan gelmez (H2/B19
#: kuralı). Taban ölçümü: 700 K'de -%11,20 · 1000 K'de -%12,27 sapma vardı.
JANAF_N2_CP_J_MOL_K = {300.0: 29.124, 500.0: 29.580,
                       700.0: 30.754, 1000.0: 32.697}
#: NASA-7 polinomunun düşük-sıcaklık (200-1000 K) setinin JANAF'a karşı
#: yayımlanmış uyum bandı; kusur bunun 20 katı bir sapma üretiyordu.
NASA7_JANAF_TOLERANS_YUZDE = 1.0


class TestZ506N2Katsayilari:
    def test_n2_cp_janaf_bandinda(self):
        db = ChemicalDatabase()
        sapmalar = {}
        for T, ref in JANAF_N2_CP_J_MOL_K.items():
            cp = db.calculate_cp('N2', T)
            assert cp is not None, T
            sapmalar[T] = 100.0 * (cp - ref) / ref
        kotu = {T: s for T, s in sapmalar.items()
                if abs(s) > NASA7_JANAF_TOLERANS_YUZDE}
        assert not kotu, (
            'N2 cp JANAF bandının dışında (OH-Z5-06): %s' % sapmalar)

    def test_n2_a4_a5_standart_nasa7_setinden(self):
        """Katsayı DEĞERİ kilitlenir — türev bir büyüklük değil, kaydın kendisi."""
        a = ChemicalDatabase().get_species('N2').cp_coefficients
        assert a[3] == pytest.approx(5.641515e-09, rel=1e-6), a
        assert a[4] == pytest.approx(-2.444854e-12, rel=1e-6), a

    def test_h2o_kaydi_bozulmadi(self):
        """Bozukluk TEKİLDİ: kardeş kayıt aynı bantta kalmalı."""
        db = ChemicalDatabase()
        for T, ref in ((300.0, 33.596), (500.0, 35.226), (1000.0, 41.268)):
            cp = db.calculate_cp('H2O', T)
            assert abs(100.0 * (cp - ref) / ref) < NASA7_JANAF_TOLERANS_YUZDE


# ---------------------------------------------------------------------------
# P9B4-14 — servis/emniyet sınırı erime noktasını aşamaz
# ---------------------------------------------------------------------------
class TestP9B414ServisKlampi:
    def test_hicbir_kayit_erimenin_ustunde_servis_sinirI_yayimlamaz(self):
        ihlal = {
            ad: (m.get('melting_point'), m.get(alan), alan)
            for ad, m in MATERIALS.items()
            for alan in ('max_service_temperature', 'allowable_temperature')
            if isinstance(m.get('melting_point'), (int, float))
            and isinstance(m.get(alan), (int, float))
            and m[alan] > m['melting_point']}
        assert not ihlal, (
            'servis/emniyet sınırı erime noktasının üstünde (P9B4-14): %s'
            % ihlal)

    def test_yukleme_ani_degismez_ihlali_reddeder(self):
        """Kapının KENDİSİ sınanır: bozuk bir kayıt yüklenirken patlamalı."""
        ad = 'steel_4130'
        eski = MATERIALS[ad]['max_service_temperature']
        MATERIALS[ad]['max_service_temperature'] = 2000
        try:
            with pytest.raises(ValueError, match='melting_point'):
                _validate_materials()
        finally:
            MATERIALS[ad]['max_service_temperature'] = eski
        _validate_materials()      # geri yazım doğrulanır

    def test_bes_kaydin_klampi_kendi_erimesine_esit(self):
        for ad in ('steel', 'steel_4130', 'steel_4340', 'ss_304', 'ss_316'):
            m = MATERIALS[ad]
            assert m['max_service_temperature'] == m['melting_point'], ad


# ---------------------------------------------------------------------------
# P16B4-02 — birim çözümü: iki-okuma birleşimi
# ---------------------------------------------------------------------------
class TestP16B402BirimBirlesimi:
    def test_bandin_ici_metre_okunur_mm_yedegine_dusmez(self):
        from hrma.export.motor_geometry import length_in_meters_banded
        # ÖLÇÜLDÜ (taban): 1,5 / 2,0 / 5,0 -> 1,5 / 2,0 / 5,0 MİLİMETRE
        for v in (1.5, 2.0, 5.0):
            metre, kaynak = length_in_meters_banded(v, 'chamber_diameter', 1.0)
            assert kaynak == 'si', (v, kaynak)
            assert metre == pytest.approx(v)

    def test_mm_okumasi_tek_makul_olan_mm_kalir(self):
        from hrma.export.motor_geometry import length_in_meters_banded
        for v, beklenen in ((100.0, 0.1), (1000.0, 1.0), (10.0, 0.01)):
            metre, kaynak = length_in_meters_banded(v, 'chamber_diameter', 1.0)
            assert kaynak == 'mm', (v, kaynak)
            assert metre == pytest.approx(beklenen)

    def test_iki_okuma_da_makulse_sayi_uretilmez(self):
        from hrma.export.motor_geometry import length_in_meters_banded
        metre, kaynak = length_in_meters_banded(1.5, 'throat_diameter', 1.0)
        assert metre is None and kaynak == 'ambiguous'

    def test_iki_okuma_da_imkansizsa_sayi_uretilmez(self):
        from hrma.export.motor_geometry import length_in_meters_banded
        metre, kaynak = length_in_meters_banded(6000.0, 'chamber_diameter', 1.0)
        assert metre is None and kaynak == 'out_of_band'

    def test_stl_ucu_1p5_metrelik_hazneyi_1p5_metre_uretir(self, client, iyi_motor):
        """UÇ düzeyi: ölçülen kusur 56 mm'lik sessiz yedekti."""
        r = client.post('/api/export-stl',
                        json={'motor_data': dict(iyi_motor,
                                                 chamber_diameter=1.5)})
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        kutu = _stl_kutusu(r.get_data())
        assert kutu is not None
        assert kutu[0] > 1000.0, kutu     # 1,5 m hazne -> metre mertebesi

    def test_stl_ucu_cozulemeyen_birimi_reddeder(self, client, iyi_motor):
        # exit_diameter = 3,0: hem 3,0 m hem 3,0 mm doğrulayıcının yazılı
        # bandının ([0,002; 5,0] m) İÇİNDE — hüküm kazanılamaz, sayı üretilmez.
        r = client.post('/api/export-stl',
                        json={'motor_data': dict(iyi_motor,
                                                 exit_diameter=3.0)})
        assert r.status_code == 422, r.status_code
        j = r.get_json()
        assert j['status'] == 'unresolved_geometry_units'
        assert [f['field'] for f in j['invalid_fields']] == ['exit_diameter']
        assert j['invalid_fields'][0]['reason'] == 'ambiguous'


def _stl_kutusu(ham):
    import struct
    if len(ham) < 84:
        return None
    n = struct.unpack('<I', ham[80:84])[0]
    if len(ham) < 84 + 50 * n:
        return None
    mn = [float('inf')] * 3
    mx = [float('-inf')] * 3
    for i in range(n):
        o = 84 + 50 * i + 12
        for v in range(3):
            xyz = struct.unpack('<3f', ham[o + 12 * v:o + 12 * v + 12])
            for k in range(3):
                mn[k] = min(mn[k], xyz[k])
                mx[k] = max(mx[k], xyz[k])
    return [mx[k] - mn[k] for k in range(3)]


# ---------------------------------------------------------------------------
# P16B4-15 — RASP başlığında sıfıra yuvarlanan alan
# ---------------------------------------------------------------------------
class TestP16B415YuvarlamaKapisi:
    def test_yazildiginda_sifir_olan_kutle_reddedilir(self, client, iyi_motor):
        for kutle in (1e-9, 4e-4):
            r = client.post('/api/export-eng',
                            json={'motor_data': dict(iyi_motor,
                                                     propellant_mass=kutle)})
            assert r.status_code == 422, (kutle, r.status_code)

    def test_yazildiginda_gorunen_en_kucuk_kutle_gecer(self, client, iyi_motor):
        r = client.post('/api/export-eng',
                        json={'motor_data': dict(iyi_motor,
                                                 propellant_mass=1e-3)})
        assert r.status_code == 200
        satir = _rasp_satiri(r.get_json()['content'])
        assert satir.split()[4] == '0.001', satir

    def test_motor_satirinda_sifir_alan_hic_yazilmaz(self, client, iyi_motor):
        """Dosyanın KENDİ yasağı: sıfır alanlı motor satırı üretilemez."""
        r = client.post('/api/export-eng', json={'motor_data': dict(iyi_motor)})
        assert r.status_code == 200
        alanlar = _rasp_satiri(r.get_json()['content']).split()
        for i in (1, 2, 4, 5):
            assert float(alanlar[i]) > 0.0, alanlar

    def test_hassasiyet_tek_kaynaktan_gelir(self):
        from hrma.export.openrocket_integration import ENG_HEADER_DECIMALS
        assert ENG_HEADER_DECIMALS['propellant_mass_kg'] == 3
        assert ENG_HEADER_DECIMALS['diameter_mm'] == 1


def _rasp_satiri(icerik):
    for satir in (icerik or '').splitlines():
        if satir and not satir.startswith(';'):
            return satir
    raise AssertionError('RASP motor satırı yok')


# ---------------------------------------------------------------------------
# P16B4-09 — boş komple paket
# ---------------------------------------------------------------------------
class TestP16B409BosPaket:
    def test_hicbir_uretici_basaramadiysa_paket_yayimlanmaz(self, client,
                                                            iyi_motor,
                                                            monkeypatch):
        # ÖH D16 birleştirme (ana model, 1 Eyl 2026): kulvar worktree'sinde
        # chamber_diameter=-0,10 BÜTÜN üreticileri düşürüyordu. Birleşik
        # ağaçta .eng üreticisi negatif çapı 'yok' sayıp P17S1-01'in
        # BEYANLI yer tutucu sözleşmesiyle (case_diameter_source='exit' +
        # 'chamber diameter NOT available' notu) dosya yazıyor — dürüst ve
        # kilitli davranış (tests/test_unit_contract.py::
        # test_placeholder_is_declared_when_case_is_unknown). Bekçinin
        # konusu 'her üretici düşünce paket yayımlanmaz' olduğu için .eng
        # üreticisi ADIYLA düşürülür; iddialar aynen.
        #
        # ÖH D18 / ihracat a1 — BEKÇİ ÇEVRİLDİ (kusuru koruyordu).
        # P16B4-09'un Fable-D16 ŞART'ı gereği ``chamber_diameter=-0,10``
        # artık ÜRETİCİLERDEN ÖNCE, ``_reject_unphysical_export_geometry``
        # ile adıyla reddediliyor (422 ``invalid_export_geometry``).
        # Bu bekçi ise negatif çapı yalnız "üreticileri düşürmek için bir
        # araç" olarak kullanıyordu ve dolayısıyla GEÇ REDDİ (üretim
        # denendikten sonra) sözleşme diye kilitliyordu. Bekçinin KONUSU
        # ("her üretici düşünce paket yayımlanmaz") aynen korunur: artık
        # SAĞLIKLI gövde + BEŞ üreticinin adıyla düşürülmesiyle ölçülür,
        # ve erken reddin kendisi ayrıca iddia edilir. İddia zayıflamadı,
        # güçlendi.
        from hrma.export import openrocket_integration as ORI

        def _reddet(self_, *a, **k):
            raise ORI.OpenRocketExportDataError(
                ['propellant_mass_kg'],
                {'propellant_mass_kg': 'enjekte edilmiş ölçüm arızası'},
                what='.eng')

        def _coken(*a, **k):
            raise RuntimeError('bekçi: üretici adıyla düşürüldü')

        monkeypatch.setattr(ORI.OpenRocketExporter, 'export_motor_file',
                            _reddet)
        import hrma.app as _A
        # ÖH D24 / fix-22 — YAMA ÖRNEĞE DEĞİL SINIFA (D23 fix-20 ile aynı
        # gerekçe, bu kez KAYNAK taraf). ``_A.cad_designer`` modül düzeyi bir
        # ÖRNEKTİR ve ``generate_3d_motor_assembly`` adı sınıftan MİRAS gelir;
        # ``monkeypatch`` böyle bir adı geri alırken adı SİLMEZ, eski işlevi
        # ÖRNEK NİTELİĞİ olarak yazar. Kalıcı örnek niteliği sınıfı GÖLGELER
        # ve bu dosyadan SONRA sınıf üstünden yapılan yamalar örneğe ULAŞMAZ.
        # ÖLÇÜLDÜ (taban kaydı-7 birleşme kırmızısı): bu dosya koşunca
        # ``tests/test_d18_ihracat_a1.py::TestP16B409KomplePaket::
        # test_hepsi_dustu_kapisi_yerinde_kalir`` kırmızıya dönüyordu —
        # o test CAD üreticisini SINIF üstünden düşürüyor, yama gölgelenince
        # üretici başarıyor ve "hepsi düştü" kapısı hiç ateşlenmiyordu (tek
        # dosya koşumunda görünmeyen sıra bağımlılığı). Bu bekçinin kendi
        # iddiası değişmez: uç aynı örneği kullanır, üretici yine düşer.
        monkeypatch.setattr(type(_A.cad_designer),
                            'generate_3d_motor_assembly', _coken)
        monkeypatch.setattr('hrma.export.drawing_generator.generate_dxf',
                            _coken)
        monkeypatch.setattr(
            'hrma.export.drawing_generator.generate_drawing_pdf', _coken)
        monkeypatch.setattr(
            'hrma.export.step_export.generate_step_assembly', _coken)
        r = client.post('/api/export-complete-zip',
                        json={'motor_data': dict(iyi_motor)})
        assert r.status_code == 422, r.status_code
        j = r.get_json()
        assert j['status'] == 'no_exportable_artifacts'
        assert j['failed_generators'], j

    def test_negatif_cap_uretim_denenmeden_reddedilir(self, client,
                                                      iyi_motor):
        """ÖH D18 / P16B4-09 (Fable-D16 ŞART) — kapı üreticilerden ÖNCE.

        ÖLÇÜLDÜ (taban 9071a64): bu gövde HTTP 200 + 1.860 B'lik bir
        ``complete_package.zip`` veriyordu (``.eng`` üreticisi negatif
        çapı beyanlı yer tutucuyla yazdığı için "hepsi düştü" kapısı hiç
        ateşlenmiyordu).
        """
        r = client.post('/api/export-complete-zip',
                        json={'motor_data': dict(iyi_motor,
                                                 chamber_diameter=-0.10)})
        assert r.status_code == 422, r.status_code
        j = r.get_json() or {}
        assert j.get('error') == 'invalid_export_geometry', j
        assert 'chamber_diameter' in [f.get('field')
                                      for f in (j.get('invalid_fields') or [])]

    def test_saglikli_govde_paketi_uretmeye_devam_eder(self, client, iyi_motor):
        r = client.post('/api/export-complete-zip',
                        json={'motor_data': dict(iyi_motor)})
        assert r.status_code == 200
        with zipfile.ZipFile(io.BytesIO(r.get_data())) as z:
            adlar = z.namelist()
        muhendislik = [a for a in adlar
                       if not a.endswith(('MANIFEST.txt',
                                          'motor_geometry.json'))]
        assert muhendislik, adlar


# ---------------------------------------------------------------------------
# P16B4-16 — çizici düşünce sessiz küçülme
# ---------------------------------------------------------------------------
class TestP16B416CiziciDusunce:
    def test_cizim_uretilemezse_pdf_yayimlanmaz(self, client, iyi_motor,
                                                monkeypatch):
        import hrma.export.chart_render as cr
        monkeypatch.setitem(cr._state, 'broken', True)
        r = client.post('/api/export-drawings-pdf',
                        json={'motor_data': dict(iyi_motor)})
        assert r.status_code == 503, (r.status_code, len(r.get_data()))
        j = r.get_json()
        assert j['status'] == 'renderer_unavailable'

    def test_cizici_saglamken_cizimli_pdf_iner(self, client, iyi_motor):
        r = client.post('/api/export-drawings-pdf',
                        json={'motor_data': dict(iyi_motor)})
        assert r.status_code == 200
        # Ölçüldü: çizimli belge 129.300 B, çizimsiz 5.122 B.
        assert len(r.get_data()) > 50_000, len(r.get_data())


# ---------------------------------------------------------------------------
# P13B3-03 — data/validation çapalarının tüketicisi
# ---------------------------------------------------------------------------
_CAPA_DIZINI = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'data', 'validation')

#: Ölçülen taban (P13B3-03): bu beş çapayı hiçbir test/ürün dosyası
#: okumuyordu. Bu sınıf onların TÜKETİCİSİdir — çapa artık bekçiye bağlı.
TUKETICISIZ_CAPALAR = (
    'thermal_bartz_accuracy_band.json',
    'twophase_particle_loading_loss.json',
    'acoustic_f1_first_tangential.json',
    'acoustic_cylindrical_chamber_modes.json',
    'nozzle_boldman_conical_1968.json',
)


def _capa(ad):
    with open(os.path.join(_CAPA_DIZINI, ad), encoding='utf-8') as fh:
        return json.load(fh)


class TestP13B303CapaTuketicisi:
    @pytest.mark.parametrize('ad', TUKETICISIZ_CAPALAR)
    def test_capa_okunabilir_ve_kunyeli(self, ad):
        k = _capa(ad)
        for alan in ('schema_version', 'case', 'expected_outputs', 'source',
                     'confidence'):
            assert alan in k, (ad, alan)
        assert k['source'].get('title'), ad

    def test_iki_faz_denge_limiti_kapali_formdan_yeniden_uretilir(self):
        """``twophase_particle_loading_loss`` çapası ARTIK ölçülüyor.

        Kaydın kendi ``reference_formulas`` bloğu bağımsız olarak burada
        yeniden türetilir; çapa sayıları ile karışım termodinamiği
        birbirini tutmalı (kaydın ``tolerance_pct`` alanı kullanılır).
        """
        import math
        k = _capa('twophase_particle_loading_loss.json')
        g = k['inputs']['worked_example']
        R, cp, cs = (g['gas_constant_J_kgK'], g['gas_cp_J_kgK'],
                     g['condensed_phase_cs_J_kgK'])
        Tc = g['chamber_temperature_K']
        tol = float(k['tolerance_pct'])
        denge = k['expected_outputs']['equilibrium_limit']
        for beta in g['beta_values']:
            bek = denge['beta_%.2f' % beta]
            R_mix = (1 - beta) * R
            cp_mix = (1 - beta) * cp + beta * cs
            cv_mix = (1 - beta) * (cp - R) + beta * cs
            gam = cp_mix / cv_mix
            cstar = (math.sqrt(R_mix * Tc / gam)
                     * ((gam + 1) / 2) ** ((gam + 1) / (2 * (gam - 1))))
            assert abs(100 * (R_mix - bek['R_mix']) / bek['R_mix']) < tol
            assert abs(100 * (gam - bek['gamma_mix'])
                       / bek['gamma_mix']) < tol
            assert abs(100 * (cstar - bek['cstar_m_s'])
                       / bek['cstar_m_s']) < tol

    def test_gecikme_kaybi_MODELLENMEDI_beyani_korunur(self):
        """Kayıt kendi eksiğini beyan ediyor; sessizce 'modellendi'ye dönemez."""
        k = _capa('twophase_particle_loading_loss.json')
        assert (k['expected_outputs']['lag_loss']['_status']
                == 'NOT_MODELLED')

    def test_bartz_bandi_sayisal_h_icermez_beyani_korunur(self):
        k = _capa('thermal_bartz_accuracy_band.json')
        beklenen = k['expected_outputs']
        assert 'NOT_DIGITIZED' in beklenen
        bantlar = [b['band'] for b in beklenen['published_error_bands_pct']]
        assert bantlar == ['+50', '+45', '+80 ila -45'], bantlar


# ---------------------------------------------------------------------------
# P16B4-08 — ÇÜRÜTÜLDÜ + gerilemeye karşı kilit
# ---------------------------------------------------------------------------
class TestP16B408OzetTabloCelismesi:
    """Kalem başlığı ölçümle ÇÜRÜTÜLDÜ; bu sınıf kusurun DÖNMESİNİ engeller.

    İddia: *yönetici özeti hesaplanmamış büyüklükler için 0,0 basıyor — aynı
    belgedeki tablo "N/A" diyor*. ÖLÇÜLDÜ (taban 6fde52b, ``once_uc.json``
    P16B4-08): boş istekte belgede 'Maximum Thrust' iki kez geçiyor ve İKİSİ
    de ``N/A``; ``0.0`` hiç yok. Yani çelişki daha önce kapanmış. Kilit
    burada kurulur ki "or 0" deseni geri gelemesin.
    """

    ALANLAR = ('Maximum Thrust', 'Specific Impulse', 'Burn Time',
               'Total Impulse')

    def _pdf_metni(self, client, yuk):
        pypdf = pytest.importorskip('pypdf')
        r = client.post('/api/export-pdf/summary', json=yuk)
        assert r.status_code == 200
        rd = pypdf.PdfReader(io.BytesIO(r.get_data()))
        return '\n'.join((s.extract_text() or '') for s in rd.pages)

    def test_bos_istekte_hicbir_buyukluk_sifir_basmaz(self, client):
        # ÖH D18 / ihracat a1 — BEKÇİ ÇEVRİLDİ (kusuru koruyordu).
        # Bu bekçi TAMAMEN boş gövde (``{}``) ile HTTP 200 + gerçek bir
        # PDF bekliyordu, yani P13B1-02'nin ölçtüğü fail-open davranışı
        # (hiç motor verilmemişken rapor yayımlama) sözleşme diye
        # kilitliyordu. Kalemin KONUSU — "hesaplanmamış büyüklük için 0,0
        # basılmaz, N/A basılır" — DEĞİŞMEDİ ve aynen ölçülür: gövde artık
        # bir motoru tanımlıyor ama hiçbir başarım sayısı taşımıyor.
        import re
        metin = self._pdf_metni(client, {'motor_data': {
            'motor_name': 'P16B408-BOS', 'motor_type': 'hybrid'}})
        for alan in self.ALANLAR:
            okunan = re.findall(re.escape(alan) + r'\s*:?\s*([-\w./]+)', metin)
            assert okunan, alan
            assert set(okunan) == {'N/A'}, (alan, okunan)

    def test_ozet_ile_tablo_ayni_hukmu_veriyor(self, client, iyi_motor):
        import re
        metin = self._pdf_metni(client, {'motor_data': dict(iyi_motor)})
        for alan in self.ALANLAR:
            okunan = re.findall(re.escape(alan) + r'\s*:?\s*([-\w./]+)', metin)
            assert len(set(okunan)) == 1, (
                'aynı belgede iki farklı hüküm (P16B4-08): %s -> %s'
                % (alan, okunan))
