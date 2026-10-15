"""ÖH Dalga-18 / ihracat a1 — bekçiler.

Kapsanan kalemler:

* **P16B4-02** (Fable-D16 ŞART) — birim kapısı ihracat ailesinin ALTI
  üyesinde de üreticiden ÖNCE; ``app.py`` etiket demetini ikinci kez
  yazmıyor, ``motor_geometry.UNEARNED_UNIT_SOURCES``tan okuyor;
  ``/api/export-step``in girdi/analiz eksikliği 500 değil adlı 422.
* **P16B4-09** (Fable-D16 ŞART) — ``/api/export-complete-zip`` işaret ve
  sıralama kapısını ÜRETİCİLERDEN ÖNCE uyguluyor; sağlıklı gövde aynen
  200.
* **P9B5-12** (Fable-D16 ŞART) — ``oxidizer_reference_density`` yapısal
  ``state_reason`` anahtarı yayımlıyor; ``database_integrations`` kapısı
  NOT METNİNİ değil o anahtarı okuyor.
* **P9B5-07** (Fable-D16 ŞART) — ölü ``_HIBRIT_TAHMIN_ADLARI`` /
  ``_KATI_TAHMIN_ADLARI`` silindi; tanınmayan itici mesajı GERÇEK
  tanıklık kümesini söylüyor. İkinci yarı (şablon seçenek kilidi)
  ÖLÇÜLÜR ve kayda geçer — şablonlar arayüz kulvarının sahasıdır.
* **P13B1-02** (D17 devri) — ``/api/export-pdf/<tip>`` boş gövdeden
  rapor yayımlamıyor.

Ölçüm dosyaları: ``docs/scofield/raw/OH/D18/ihracat/a1/{once,sonra}.json``
(taban 9071a64).
"""
import ast
import contextlib
import io
import json
import os
import re

import pytest

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
def client():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


#: ÖLÇÜLEN sağlıklı gövde (once.json / sonra.json ``iyi_govde``).
IYI_GOVDE = {
    'motor_name': 'D18OLC', 'motor_type': 'solid',
    'chamber_diameter': 0.1, 'chamber_length': 0.3,
    'throat_diameter': 0.02, 'exit_diameter': 0.05,
    'chamber_pressure': 40.0, 'thrust': 1000.0, 'burn_time': 5.0,
    'propellant_mass': 2.0, 'total_impulse': 5000.0,
    'grain_length': 0.25, 'port_diameter_initial': 0.03,
}

#: Birim kapısının uygulanması gereken ihracat ailesi (ŞART'ın saydığı
#: beş kardeş + kapının zaten bulunduğu ``-stl``).
IHRACAT_AILESI = (
    '/api/export-stl',
    '/api/export-eng',
    '/api/export-dxf',
    '/api/export-step',
    '/api/export-drawings-pdf',
    '/api/export-complete-zip',
)


def _post(client, yol, yuk):
    return _sessiz(client.post, yol, json=yuk)


# ---------------------------------------------------------------------------
# P16B4-02 — BİRİM KAPISI ALTI UÇTA
# ---------------------------------------------------------------------------
class TestP16B402BirimKapisi:
    """Birimi kazanılmamış uzunlukla HİÇBİR ihracat çıktısı üretilmez.

    ÖLÇÜLDÜ (taban 9071a64, ``once.json`` A bölümü) — ``exit_diameter=3.0``:

    ======================== ====== ==========================================
    uç                       HTTP   gövde
    ======================== ====== ==========================================
    ``-stl``                 422    ``unresolved_geometry_units`` (kapı vardı)
    ``-eng``                 200    geçerli ``.eng``
    ``-dxf``                 200    43.380 B imalat çizimi
    ``-drawings-pdf``        200    137.608 B PDF
    ``-complete-zip``        200    106.100 B paket (5 dosya)
    ``-step``                500    adsız üretici hatası
    ======================== ====== ==========================================
    """

    @pytest.mark.parametrize('yol', IHRACAT_AILESI)
    @pytest.mark.parametrize('alan,deger', [
        ('exit_diameter', 3.0),
        ('chamber_length', 0.015),
    ])
    def test_kazanilmamis_birim_alti_ucta_da_adiyla_reddedilir(
            self, client, yol, alan, deger):
        govde = dict(IYI_GOVDE)
        govde[alan] = deger
        r = _post(client, yol, {'motor_data': govde})
        assert r.status_code == 422, (
            f'{yol}: birimi kazanılmamış {alan}={deger} ile HTTP '
            f'{r.status_code} döndü — imalat çıktısı üretilmiş olabilir '
            f'({len(r.get_data())} B)')
        j = r.get_json() or {}
        assert j.get('status') == 'unresolved_geometry_units', j
        adlar = [f.get('field') for f in (j.get('invalid_fields') or [])]
        assert alan in adlar, (
            f'{yol}: ret gerekçesi alanı ADIYLA söylemiyor: {j}')

    def test_saglikli_govde_alti_ucun_hicbirinden_reddedilmez(self, client):
        """Kapı YENİ BİR BANT KOYMAZ: ölçülen sağlıklı gövde geçer.

        ``-step`` bu gövdede yapısal analiz taşımadığı için (ayrı ve
        DOĞRU bir ret) 422 ``incomplete_export_inputs`` verir; birim
        gerekçesiyle reddedilmediği doğrulanır.
        """
        for yol in IHRACAT_AILESI:
            r = _post(client, yol, {'motor_data': dict(IYI_GOVDE)})
            j = r.get_json() if r.status_code >= 400 else None
            assert (j or {}).get('status') != 'unresolved_geometry_units', (
                f'{yol}: sağlıklı gövde birim gerekçesiyle reddedildi: {j}')

    @_STEP_GEREKLI
    def test_step_eksik_girdiyi_500_degil_adli_422_ile_reddeder(self, client):
        """ŞART: "export-step'in 500'ü adlı 422'ye dönsün".

        ÖLÇÜLDÜ: sağlıklı gövdede bile ``-step`` HTTP 500 + "chamber wall
        thickness is not available from the structural analysis ...
        refusing to emit a manufacturing STEP with an assumed wall"
        veriyordu. Ret DOĞRU, taşıyıcı yanlıştı.
        """
        r = _post(client, '/api/export-step', {'motor_data': dict(IYI_GOVDE)})
        assert r.status_code == 422, (
            f'HTTP {r.status_code}: {r.get_data(as_text=True)[:200]}')
        j = r.get_json() or {}
        assert j.get('error') == 'incomplete_export_inputs', j
        assert 'refusing to emit' in str(j.get('message', '')), j

    def test_app_py_etiket_demetini_ikinci_kez_yazmaz(self):
        """ŞART (2): tek tanım noktası ``motor_geometry``.

        ÖLÇÜLDÜ (``once.json`` ``A_literal_demet``): ``app.py`` içinde
        ``('ambiguous', 'out_of_band')`` literali 1 kez geçiyordu ve
        ``UNEARNED_UNIT_SOURCES`` hiç ithal edilmiyordu.
        """
        kaynak = open(os.path.join(KOK, 'hrma', 'app.py'),
                      encoding='utf-8').read()
        assert "('ambiguous', 'out_of_band')" not in kaynak, (
            'app.py birimi kazanılmamış etiketleri İKİNCİ KEZ yazıyor; '
            'motor_geometry.UNEARNED_UNIT_SOURCES tek tanım noktasıdır')
        assert 'UNEARNED_UNIT_SOURCES' in kaynak

    def test_kapi_tek_kaynagi_gercekten_okur(self, client):
        """Küme genişletilirse kapı da genişler (tek kaynak kanıtı).

        Etiket demeti kopyalanmış olsaydı bu genişletme kapıya
        YANSIMAZDI; bekçi tam olarak o kopyayı görür.
        """
        from hrma.export import motor_geometry as MG
        eski = MG.UNEARNED_UNIT_SOURCES
        try:
            MG.UNEARNED_UNIT_SOURCES = frozenset(eski | {'declared:m'})
            r = _post(client, '/api/export-dxf',
                      {'motor_data': dict(IYI_GOVDE, length_units='m')})
            assert r.status_code == 422, (
                'kapı tek kaynağı okumuyor: küme genişletildiği hâlde '
                f'HTTP {r.status_code} döndü')
            assert (r.get_json() or {}).get('status') == \
                'unresolved_geometry_units'
        finally:
            MG.UNEARNED_UNIT_SOURCES = eski


# ---------------------------------------------------------------------------
# P16B4-09 — KOMPLE PAKET İŞARET/SIRALAMA KAPISI
# ---------------------------------------------------------------------------
class TestP16B409KomplePaket:
    """Negatif ölçü ile "komple tasarım paketi" YAYIMLANMAZ.

    ÖLÇÜLDÜ (taban 9071a64, ``once.json`` B bölümü):
    ``chamber_diameter = -0,10`` -> HTTP **200** + 1.860 B'lik
    ``..._complete_package.zip`` (MANIFEST.txt + motor_geometry.json +
    ``.eng``). Beş üreticiden dördü düşüyordu ama ``.eng`` üreticisi
    negatif çapı yazarak BAŞARDIĞI için "hepsi düştü" kapısı hiç
    ateşlenmiyordu.
    """

    @pytest.mark.parametrize('alan,deger', [
        ('chamber_diameter', -0.10),
        ('chamber_length', -0.5),
    ])
    def test_negatif_olcu_uretilmeden_once_adiyla_reddedilir(
            self, client, alan, deger):
        govde = dict(IYI_GOVDE)
        govde[alan] = deger
        r = _post(client, '/api/export-complete-zip', {'motor_data': govde})
        assert r.status_code == 422, (
            f'{alan}={deger} ile HTTP {r.status_code}, '
            f'{len(r.get_data())} B paket indi')
        j = r.get_json() or {}
        # "hepsi düştü" kapısı DEĞİL: kusur ÜRETİM DENENMEDEN yakalanır.
        assert j.get('error') == 'invalid_export_geometry', j
        assert j.get('status') != 'no_exportable_artifacts', (
            'ret hâlâ "üreticilerin hepsi düştü" yolundan geliyor; kapı '
            'üreticilerden ÖNCE kurulmalıydı')
        adlar = [f.get('field') for f in (j.get('invalid_fields') or [])]
        assert alan in adlar, j

    def test_saglikli_govde_aynen_200_ve_paket_eksilmez(self, client):
        """Ölçülen sağlıklı gövde 200 ve ürettiği dosyalar aynen.

        ``once.json`` ``iyi_govde``: 8 girdi (MANIFEST, geometry, .eng,
        DXF, çizim PDF'i, üç STL).
        """
        import zipfile
        r = _post(client, '/api/export-complete-zip',
                  {'motor_data': dict(IYI_GOVDE)})
        assert r.status_code == 200, r.get_data(as_text=True)[:200]
        with zipfile.ZipFile(io.BytesIO(r.get_data())) as z:
            adlar = sorted(i.filename for i in z.infolist())
        assert 'MANIFEST.txt' in adlar
        assert any(a.endswith('.stl') for a in adlar), adlar
        assert any(a.endswith('.dxf') for a in adlar), adlar
        assert any(a.endswith('.eng') for a in adlar), adlar
        assert len(adlar) >= 8, adlar

    def test_hepsi_dustu_kapisi_yerinde_kalir(self, client, monkeypatch):
        """ŞART: "mevcut 'hepsi düştü' kapısı kalır"."""
        import hrma.app as A

        def _coken(*a, **kw):
            raise RuntimeError('bekçi: üretici bilerek düşürüldü')

        # ÖH D23 fix-20 — YAMA ÖRNEĞE DEĞİL SINIFA. ``A.cad_designer`` ve
        # ``A.openrocket_exporter`` modül düzeyi ÖRNEKLERDİR ve yamalanan ad
        # sınıftan MİRAS gelir. ``monkeypatch.setattr`` böyle bir adı geri
        # alırken adı SİLMEZ, eski (sınıftan gelen) işlevi ÖRNEK NİTELİĞİ
        # olarak yazar — ölçüldü (MonkeyPatch ile birebir):
        #     undo öncesi  : 'm' in o.__dict__  -> False
        #     undo sonrası : 'm' in o.__dict__  -> True
        # Kalıcı örnek niteliği sınıfı GÖLGELER; bu testten sonra sınıf
        # üstünden yapılan her yama o örneğe ULAŞMAZ. Ölçülen zarar: bu
        # dosya koşunca ``tests/test_hybrid_wiring_v2626.py::
        # TestYardimciCiktiAnaliziOldurmez`` iki testi kırmızıya dönüyordu
        # (ikisi de ``ORI.OpenRocketExporter.export_motor_file``i SINIF
        # üstünden yamalıyor; yama örneğe ulaşmayınca ret yolu hiç
        # ateşlenmiyor). Tek dosya koşumunda görünmeyen, birleşik koşumda
        # ateşlenen sıra bağımlılığıydı.
        # Sınıf üstünden yamada bu artık yok (ad sınıf sözlüğünde GERÇEKTEN
        # var, undo onu geri koyar). Bu testin kendi iddiası değişmez:
        # uç aynı örneği kullanıyor, üretici yine düşüyor.
        monkeypatch.setattr(type(A.cad_designer), 'generate_3d_motor_assembly',
                            _coken)
        monkeypatch.setattr(type(A.openrocket_exporter), 'export_motor_file',
                            _coken)
        monkeypatch.setattr('hrma.export.drawing_generator.generate_dxf',
                            _coken)
        monkeypatch.setattr(
            'hrma.export.drawing_generator.generate_drawing_pdf', _coken)
        monkeypatch.setattr('hrma.export.step_export.generate_step_assembly',
                            _coken)
        r = _post(client, '/api/export-complete-zip',
                  {'motor_data': dict(IYI_GOVDE)})
        assert r.status_code == 422
        assert (r.get_json() or {}).get('status') == 'no_exportable_artifacts'


# ---------------------------------------------------------------------------
# P9B5-12 — HÂL GEREKÇESİ YAPISAL ANAHTARDA
# ---------------------------------------------------------------------------
class TestP9B512HalGerekcesi:
    """Hüküm SERBEST METİNDEN değil yapısal anahtardan okunur.

    ÖLÇÜLDÜ (taban 9071a64, ``once.json`` C bölümü): tek kaynağın
    ``note`` metni değiştirildiğinde ``_get_fallback_properties`` kapısı
    sessizce açılıyor ve ``('O2', 293,15 K)`` için ``density = 1141,0
    kg/m³`` yayımlanıyordu — O₂ orada GAZ (~1,31 kg/m³), yani gerçeğin
    ~870 katı.
    """

    def test_state_reason_anahtari_yayimlanir(self):
        from hrma.data.external_data_fetcher import (
            oxidizer_reference_density)
        beklenen = {
            ('n2o', 293.15): 'applied',
            ('lox', 90.19): 'not_modelled',
            ('lox', 293.15): 'outside_liquid_band',
            ('lox', 500.0): 'outside_liquid_band',
        }
        for (ad, T), gerekce in beklenen.items():
            r = oxidizer_reference_density(ad, T)
            assert 'state_reason' in r, (
                f'{ad}@{T}: yapısal gerekçe anahtarı yok: {sorted(r)}')
            assert r['state_reason'] == gerekce, (ad, T, r['state_reason'])

    def test_mevcut_anahtarlar_aynen_korunur(self):
        """ŞART: "ek anahtar, altı okuyucu ve dört bekçi etkilenmez"."""
        from hrma.data.external_data_fetcher import (
            oxidizer_reference_density)
        for ad, T in (('n2o', 293.15), ('lox', 90.19), ('h2o2', 293.15)):
            r = oxidizer_reference_density(ad, T)
            for anahtar in ('density', 'source', 'basis', 'reference_T_K',
                            'state_applied', 'note'):
                assert anahtar in r, (ad, T, anahtar, sorted(r))

    def test_not_metni_degistirilse_de_sayi_yayimlanmaz(self, monkeypatch):
        """ŞART bekçisi — kapı METNE bağlı olsaydı bu test kırmızı olurdu."""
        from hrma.data import database_integrations as DBI
        gercek = DBI.oxidizer_reference_density

        def sahte(key, temperature=None):
            kayit = dict(gercek(key, temperature))
            if kayit.get('note'):
                kayit['note'] = 'the requested temperature is not applied here'
            return kayit

        monkeypatch.setattr(DBI, 'oxidizer_reference_density', sahte)
        d = DBI.NistWebBookAPI()._get_fallback_properties('O2', 293.15)
        assert 'density' not in d or d.get('density') is None, (
            'not metni değiştirilince 293,15 K için yoğunluk yayımlandı: '
            f'{d.get("density")}')
        assert d.get('density_error'), d

    def test_sivi_bandinda_sayi_aynen_yayimlanir(self):
        from hrma.data import database_integrations as DBI
        d = DBI.NistWebBookAPI()._get_fallback_properties('O2', 90.19)
        assert d.get('density') == pytest.approx(1141.0)
        assert not d.get('density_error')


# ---------------------------------------------------------------------------
# P9B5-07 — TANIKLIK KÜMESİ DÜRÜST
# ---------------------------------------------------------------------------
class TestP9B507Taniklik:
    """Ürün, YAPMADIĞI bir denetimi yaptığını söylemez.

    ÖLÇÜLDÜ (``once_p9b507_ast.json``, taban 9071a64):
    ``_HIBRIT_TAHMIN_ADLARI`` ve ``_KATI_TAHMIN_ADLARI`` sınıfta
    ATANIYOR (1 kez) ama HİÇ OKUNMUYOR (0 kez) — ölü. Buna rağmen
    tanınmayan itici mesajı "...and it is not in this module's own
    estimate tables" diyordu.
    """

    KAYNAK = os.path.join(KOK, 'hrma', 'data', 'open_source_propellant_api.py')

    def test_olu_sabitler_silindi(self):
        """AST ile: ne atama ne okuma. (Dize sayımı açıklamayı da sayar.)"""
        agac = ast.parse(open(self.KAYNAK, encoding='utf-8').read())
        olu = ('_HIBRIT_TAHMIN_ADLARI', '_KATI_TAHMIN_ADLARI')
        bulunan = []
        for dugum in ast.walk(agac):
            if isinstance(dugum, ast.Name) and dugum.id in olu:
                bulunan.append(dugum.id)
            elif isinstance(dugum, ast.Attribute) and dugum.attr in olu:
                bulunan.append(dugum.attr)
        assert not bulunan, (
            f'ölü tahmin-adı kümeleri hâlâ kodda: {sorted(set(bulunan))}')

    def test_tahmin_tablolari_hala_estimate_yardimcilarini_besler(self):
        """Silinen KÜMELERDİR; tabloların kendisi canlı kalmalı."""
        from hrma.data.open_source_propellant_api import (
            OpenSourcePropellantAPI)
        api = OpenSourcePropellantAPI()
        assert api._estimate_regression_a('htpb') == pytest.approx(0.0003)
        assert api._estimate_burn_rate_a('kndx') == pytest.approx(0.008)
        assert api._estimate_isp('apcp') == 265

    def test_mesaj_gercek_taniklik_kumesini_soyler(self):
        from hrma.data.open_source_propellant_api import (
            OpenSourcePropellantAPI)
        r = _sessiz(OpenSourcePropellantAPI().get_propellant_for_ui,
                    'hybrid_fuel', 'zirbirzort')
        assert r.get('error') == 'unknown_propellant', r
        mesaj = str(r.get('message', ''))
        assert "estimate tables" not in mesaj, (
            'mesaj hâlâ danışılmayan tahmin tablolarını tanık gösteriyor: '
            + mesaj)
        assert 'catalogue' in mesaj and 'CoolProp' in mesaj, mesaj
        assert r.get('recognised_by') == ['propellant_database catalogue',
                                          'CoolProp fluid mapping'], r

    def test_taninan_adlar_etkilenmez(self):
        from hrma.data.open_source_propellant_api import (
            OpenSourcePropellantAPI)
        api = OpenSourcePropellantAPI()
        for tur, ad in (('hybrid_fuel', 'htpb'), ('solid_propellant', 'kndx')):
            r = _sessiz(api.get_propellant_for_ui, tur, ad)
            assert 'error' not in r, (tur, ad, r)
            assert len(r) >= 7, (tur, ad, sorted(r))

    def test_sablon_secenek_kilidi_KAYIT(self, client):
        """ŞART (2) — ÖLÇÜLÜR VE KAYDA GEÇER (ÖH D20'de küme DARALDI).

        ``advanced.html``de ETKİN (``disabled`` olmayan) itici seçenekleri
        ile ``/api/get-propellant-properties``in tanıdığı adlar
        ÖRTÜŞMÜYOR. ÖLÇÜLDÜ (taban 9071a64 ve bu ağaç — DEĞİŞMEDİ):

        ============================  ====
        seçenek                       HTTP
        ============================  ====
        ``fuel_type=pla``             422
        ``fuel_type=aluminum``        422
        ``oxidizer_type=air``         422
        ``oxidizer_type=custom``      422
        ============================  ====

        (``carbon`` ve ``al2o3`` şablonda ZATEN ``disabled``.) Onarım
        şablonu değiştirmeyi gerektirir; ``hrma/templates/**`` ARAYÜZ
        kulvarının sahasıdır, bu yüzden burada yalnız ÖLÇÜLÜR. Bekçi
        kusuru KORUMAZ: beklenen küme daralırsa (yani şablon düzelirse)
        kırmızıya döner ve kalemin kapanmasını zorunlu kılar.

        ÖH D20 / ihracat a1 — **KÜME DARALDI, KAYIT GÜNCELLENDİ.** Bekçi
        tasarımı gereği kırmızıya döndü (kardeş-dal ölçümü arayüz dalının
        bu dalgada ``templates/``e dokunmadığını gösterdi, engel kalktı).
        Yeni ölçüm (taban ``14acd1d`` -> ``dalga20/ihracat``):

        * ``oxidizer_type=air`` ve ``oxidizer_type=custom`` **kilitlendi**
          (``disabled``). Gerekçe: ikisini de ``/calculate`` de reddediyor
          (400: "Cannot resolve an oxidizer density for 'air'" /
          "Unsupported oxidizer key 'custom'"), yani sunucunun HİÇBİR ucu
          çözmüyordu; ``custom`` ayrıca yoğunluk/viskozite alanlarına
          1000 / 0,001 yer tutucularını yazıyordu.
        * ``fuel_type=pla`` ve ``fuel_type=aluminum`` **kilitlenmedi**:
          ölçüldü, ``/calculate`` ikisini de **200** ile çözüyor; oradaki
          422 yalnız özellik ARAMASINDA. Çalışan özelliği kilitlemek
          gerileme olurdu. Manşetin bu yarısı böylece daraldı.

        Bekçinin sözleşmesi aynen: küme daralırsa da genişlerse de kırmızı.
        """
        yol = os.path.join(KOK, 'hrma', 'templates', 'advanced.html')
        metin = open(yol, encoding='utf-8').read()
        secenek_re = re.compile(r'<option\s+([^>]*)>', re.I)
        olcum = {}
        for kimlik, tur in (('fuel_type', 'hybrid_fuel'),
                            ('oxidizer_type', 'oxidizer')):
            i = metin.find('id="%s"' % kimlik)
            assert i >= 0, kimlik
            blok = metin[i:metin.find('</select>', i)]
            for oz in secenek_re.findall(blok):
                if 'disabled' in oz.lower():
                    continue
                m = re.search(r'value\s*=\s*"([^"]*)"', oz)
                if not (m and m.group(1)):
                    continue
                r = _post(client, '/api/get-propellant-properties',
                          {'propellant_type': tur, 'propellant_name':
                           m.group(1)})
                olcum['%s=%s' % (kimlik, m.group(1))] = r.status_code
        tanınmayan = sorted(k for k, v in olcum.items() if v != 200)
        assert tanınmayan == ['fuel_type=aluminum', 'fuel_type=pla'], (
            'şablon ⟷ tanınan adlar kümesi DEĞİŞTİ (ölçüm: ' + json.dumps(
                olcum, sort_keys=True) + '). ÖH D20 kaydı: yalnız pla ve '
            'aluminum ETKİN kalır (ikisini de /calculate 200 ile çözer); '
            'air ve custom kilitlidir. Küme daraldıysa defterden '
            'düşürülmeli, genişlediyse yeni bir gerileme var.')


# ---------------------------------------------------------------------------
# P13B1-02 — BOŞ GÖVDEDEN RAPOR YOK
# ---------------------------------------------------------------------------
class TestP13B102PdfRaporu:
    """ÖLÇÜLDÜ (``once.json`` E bölümü): ``{}`` gövdesiyle üç rapor türü
    de HTTP 200 ve gerçek bir PDF veriyordu (5.635 / 5.397 / 6.351 B).
    """

    @pytest.mark.parametrize('tur', ['summary', 'technical', 'complete',
                                     'analysis'])
    def test_bos_govdeden_rapor_uretilmez(self, client, tur):
        r = _post(client, '/api/export-pdf/%s' % tur, {})
        assert r.status_code == 422, (
            f'{tur}: HTTP {r.status_code}, {len(r.get_data())} B')
        j = r.get_json() or {}
        assert j.get('error') == 'no_motor_data', j
        assert [f.get('field') for f in (j.get('invalid_fields') or [])] == \
            ['motor_data']

    @pytest.mark.parametrize('tur', ['summary', 'technical', 'complete'])
    def test_motor_verisi_olan_istek_aynen_gecer(self, client, tur):
        r = _post(client, '/api/export-pdf/%s' % tur,
                  {'motor_data': dict(IYI_GOVDE), 'analysis_results': {},
                   'charts': []})
        assert r.status_code == 200, r.get_data(as_text=True)[:200]
        assert r.get_data()[:5] == b'%PDF-'

    def test_cikplak_motor_verisi_hala_gecer(self, client):
        """Kapı EN DAR: "veri yoksa N/A bas" davranışı korunur.

        ``tests/test_pdf_analysis.py::TestNoFabricationWithoutData``
        yalnız ad/tip taşıyan gövdeyle 200 bekliyor; kapı o bekçiyi
        kırmamalı.
        """
        r = _post(client, '/api/export-pdf/summary',
                  {'motor_data': {'motor_type': 'hybrid',
                                  'motor_name': 'NA-TEST'},
                   'analysis_results': {}, 'charts': []})
        assert r.status_code == 200, r.get_data(as_text=True)[:200]


# ---------------------------------------------------------------------------
# OH-D16-06 — ENJEKTÖR PLAKASI DELİK ÖLÇEĞİ
# ---------------------------------------------------------------------------
class TestOHD1606EnjektorPlakasi:
    """Küçük çaplı delikler ham mesh hatasıyla düşmez.

    ÖLÇÜLDÜ (taban 9071a64, ``once_ohd1606.json``):

    ==================  ======================================
    girdi               sonuç
    ==================  ======================================
    20 x Ø1,20 mm       katı (2.768 üçgen, ``is_volume=True``)
    120 x Ø0,50 mm      ``ValueError: Not all meshes are volumes!``
    319 x Ø0,30 mm      ``ValueError: Not all meshes are volumes!``
    ==================  ======================================

    KALEM BAŞLIĞI KISMEN ÇÜRÜTÜLDÜ: tetikleyici delik SAYISI değil,
    metre uzayındaki ÖLÇEK. ``trimesh.creation.cylinder`` yarıçap
    0,00025 m ve 0,00015 m'de ``is_volume=False`` bir ağ üretiyor
    (0,0006 m'de sağlıklı); düşüş İLK boolean'da, 0,00 s'de oluyordu.
    Sayı yalnız bağlantılı: çapı imalat bandına kırpan çözüm aynı anda
    delik sayısını yükseltiyor.
    """

    TEMEL = {
        'motor_type': 'liquid', 'motor_name': 'INJ',
        'chamber_diameter': 0.1, 'chamber_length': 0.3,
        'throat_diameter': 0.02, 'exit_diameter': 0.05,
        'injector_results': {
            'injector_type': 'showerhead',
            'plate_structural': {'plate_thickness_mm': 8.0}},
    }

    @pytest.mark.parametrize('adet,cap_m', [
        (20, 0.0012), (120, 0.0005), (319, 0.0003),
    ])
    def test_kucuk_delikler_katiya_donusur(self, adet, cap_m):
        from hrma.export.cad_visualization import MotorCADDesigner
        md = dict(self.TEMEL, injector_orifices=adet,
                  orifice_diameter=cap_m)
        mesh = _sessiz(MotorCADDesigner()._create_injector_head, 0.1, md)
        assert mesh.is_volume, (
            f'{adet} x Ø{cap_m * 1000:.2f} mm: üretilen plaka kapalı bir '
            'hacim değil')
        assert mesh.volume > 0

    def test_referans_plaka_ucgen_sayisi_korunur(self):
        """20 delikli referans vaka DEĞİŞMEDİ (2.768 üçgen)."""
        from hrma.export.cad_visualization import MotorCADDesigner
        md = dict(self.TEMEL, injector_orifices=20, orifice_diameter=0.0012)
        mesh = _sessiz(MotorCADDesigner()._create_injector_head, 0.1, md)
        assert len(mesh.faces) == 2768
        # Hacim mm-uzayı gidiş-dönüşünden ötürü 8. anlamlı basamakta
        # kayar (6.224911047e-05 -> 6.224910956e-05); BEYANLI.
        assert mesh.volume == pytest.approx(6.2249110e-05, rel=1e-6)

    def test_delik_acilamiyorsa_ham_mesh_hatasi_sizmaz(self):
        """Kesici geçersizse gerekçe ADIYLA söylenir (fail-closed)."""
        from hrma.export.cad_visualization import MotorCADDesigner
        md = dict(self.TEMEL, injector_orifices=4, orifice_diameter=0.5)
        with pytest.raises(Exception) as ei:
            _sessiz(MotorCADDesigner()._create_injector_head, 0.1, md)
        metin = str(ei.value)
        assert 'Not all meshes are volumes' not in metin, metin
        assert ('injector_orifices_not_manufacturable' in metin
                or 'injector_plate_not_a_solid' in metin), metin
