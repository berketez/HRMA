"""ÖH Dalga-15 · bağlama haritası (tools/wiring_map.py) hataları — bekçiler.

Beş kalem: H1a, H1b, H2, H3, H4, H5. Hepsi haritanın KENDİ ölçümünden
çıktı; sayıların tamamı ``docs/scofield/raw/OH/D15/harita/once.json`` ⟷
``sonra.json`` dosyalarındandır.

Her sınıf, onarım geçici olarak geri alındığında KIRMIZI olacak biçimde
yazılmıştır (ters-mutasyon kanıtı:
``docs/scofield/raw/OH/D15/harita/mutasyon.py`` +
``mutasyon_sonuc.json``).

Neden bu dosya var: harita ÖLÇÜMDEN üretiliyor, yani kod değişince kendisi
de değişiyor — ama haritanın gösterdiği kusurlar kod tarafında sabitlenmezse
bir sonraki dalgada geri gelirler. Harita bulur, bu dosya kilitler.
"""

import contextlib
import io
import math

import pytest

from hrma.engines.injector_design import USER_CD_RANGE
from hrma.export import openrocket_integration as ORI
from hrma.export.motor_geometry import LENGTH_SI_MAX_M
from tests.support import inventory, shake
from tests.test_field_wiring_layer_b import HYBRID_BASE


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    return app.test_client()


def _hesapla(istemci, **ezme):
    yuk = dict(HYBRID_BASE)
    yuk.update(ezme)
    yanit = _sessiz(istemci.post, '/calculate', json=yuk)
    return yanit, (yanit.get_json() or {})


@pytest.fixture(scope='module')
def taban(istemci):
    """Sağlıklı hibrit koşu — HYBRID_BASE, hiçbir alan sarsılmamış."""
    return _hesapla(istemci)


# ===========================================================================
# H1a — UZUNLUK BİRİMİ BEYAN EDİLİR, BÜYÜKLÜKTEN TAHMİN EDİLMEZ
# ===========================================================================
class TestH1aBirimBeyani:
    """5 m'yi aşan kamara boyu "demek ki mm" diye 1000'e bölünüyordu.

    Ölçüm (once.json): HYBRID_BASE üstünde TEK alan sarsımı
      of_ratio 1,25       -> L = 6,733 m -> .eng zarfı 159,4 x  6,7 mm
      fuel_density 460    -> L = 6,897 m -> .eng zarfı 162,5 x  6,9 mm
      regression_n 0,2775 -> L = 17,318 m -> .eng zarfı 142,4 x 17,3 mm
    Motorun sayısı doğruydu (uzun grain), kaybolan BİRİMDİ.
    """

    def test_hibrit_sonucu_birimini_beyan_eder(self, taban):
        _yanit, govde = taban
        assert govde.get('motor', {}).get('length_units') == 'm', (
            'hibrit motor sonucu uzunluk birimini beyan etmiyor; dışa '
            'aktarım katmanı büyüklükten tahmin etmek zorunda kalır')

    def test_esik_ustu_kamara_boyu_mm_SANILMAZ(self):
        """resolve_geometry beyanı okur; eşik (5 m) artık tek otorite değil."""
        uzun = 3.0 * LENGTH_SI_MAX_M          # 15 m — eşiğin belirgin üstü
        motor = {
            'length_units': 'm',
            'chamber_length': uzun,
            'chamber_diameter': 0.1324,
            'throat_diameter': 0.0487,
            'exit_diameter': 0.0974,
        }
        geo = ORI.OpenRocketExporter().resolve_geometry(motor)
        assert geo['chamber_length'] == pytest.approx(uzun, rel=1e-12), (
            f"beyan edilmiş {uzun} m kamara boyu {geo['chamber_length']} m "
            f"olarak okundu — büyüklük çıkarımı beyanı ezmiş")
        assert geo['fields']['chamber_length'] == 'declared:m'
        assert geo['source'] == 'declared'
        assert not geo['notes'], f'beklenmeyen birim notu: {geo["notes"]}'

    def test_beyan_yokken_eski_davranis_AYNEN_surer(self):
        """Beyan yoksa çıkarım eskisi gibi çalışır (geriye uyum)."""
        motor = {'chamber_length': 3.5094, 'chamber_diameter': 0.1525,
                 'throat_diameter': 0.0487, 'exit_diameter': 0.0974}
        geo = ORI.OpenRocketExporter().resolve_geometry(motor)
        assert geo['fields']['chamber_length'] == 'si'
        assert geo['source'] == 'inferred'

    def test_uzun_kamarali_motor_HTTP_200_ve_dogru_zarf(self, istemci):
        yanit, govde = _hesapla(istemci, regression_n=0.2775)
        assert yanit.status_code == 200, (
            f'uzun grain HTTP {yanit.status_code}: {str(govde)[:200]}')
        boy_m = govde['motor']['chamber_length']
        # ÖH D32 / P7B1-06 (D31 devri) — İDDİA ÇEVRİLDİ, gerekçe:
        # bu koşul canlı sabit ``LENGTH_SI_MAX_M``e bakıyordu ve o sabit ELLE
        # 5,0 yazılıydı. Sabit artık doğrulayıcının kanonundan türetiliyor
        # (``LENGTH_UNIT_INFERENCE_MAX_M`` = ``chamber_length`` bandının üst
        # ucu = 20,0 m). Eski hâliyle iddia, ölçüm koşulunu korumak yerine
        # eşiğin kanona YÜKSELMESİNİ yasaklayan bir mandala dönüşüyordu
        # (D31 dersi 20): eşik 17,318 m'yi geçemezdi, ÖK-16 çelişkisi ve
        # bandı olmayan ``nozzle_*`` alanlarındaki 1000 kat kusur canlı
        # kalırdı. Koşulun ASIL anlamı "boy, D15'te kusuru üreten ESKİ
        # tek-eşikli sezginin üstünde olsun"dur; o eşik bugün bir ürün zarfı
        # değil TARİHTİR, bu yüzden burada tarihî değer olarak adıyla durur.
        D15_ESKI_CIKARIM_ESIGI_M = 5.0
        assert boy_m > D15_ESKI_CIKARIM_ESIGI_M, (
            f'ölçüm koşulu kayboldu: bu koşuda kamara boyu D15 çıkarım '
            f'eşiğinin üstünde olmalıydı, {boy_m} m çıktı')
        eng = (govde.get('openrocket') or {}).get('eng_file') or ''
        rasp = [s for s in eng.splitlines() if s and not s.startswith(';')]
        assert rasp, '.eng dosyası üretilmemiş'
        alanlar = rasp[0].split()
        # fix-11 (3 Eyl 2026): .eng başlığı boyu ENG_HEADER_DECIMALS['length_mm']
        # ondalıkla yazar (1 → yarım birim 0,05 mm); rel=1e-6 (0,017 mm) biçim
        # çözünürlüğünün altındaydı ve D18 fizik boyu 17318,4→17283,847 mm'ye
        # kaydırınca (yuvarlama 0,047 mm) tabanda tesadüfen yeşil olan iddia
        # kırmızı düştü. Tolerans biçimden türetilir, sayı uydurulmaz.
        from hrma.export.openrocket_integration import ENG_HEADER_DECIMALS
        _yarim_birim = 0.5 * 10.0 ** (-ENG_HEADER_DECIMALS['length_mm'])
        assert float(alanlar[2]) == pytest.approx(boy_m * 1000.0, abs=_yarim_birim), (
            f'RASP boy alanı {alanlar[2]} mm, motorun boyu {boy_m} m')


# ===========================================================================
# H1b — YAN ÇIKTI (.eng) ANA SONUCU DÜŞÜRMEZ
# ===========================================================================
class TestH1bIhracatHatasiBeyanEdilir:
    """.eng üretilemezse motor sonucu 200 kalır; ret ADIYLA beyan edilir.

    Ölçüm (once.json): ``OpenRocketExportDataError`` /calculate'in dış
    ``except Exception``ına düşüyor ve TÜM istek 400 dönüyordu.
    """

    def test_saglikli_kosuda_eng_dolu_ve_hata_yok(self, taban):
        yanit, govde = taban
        assert yanit.status_code == 200
        orx = govde['openrocket']
        assert orx.get('eng_file'), 'sağlıklı koşuda .eng üretilmemiş'
        assert orx.get('eng_error') is None, (
            f'sağlıklı koşuda hata beyanı var: {orx.get("eng_error")}')

    def test_ihracat_reddi_motor_sonucunu_DUSURMEZ(self, istemci,
                                                   monkeypatch):
        """Kapı ateşlendiğinde: 200 + eng_file None + eng_error dolu."""
        def _reddet(self, *a, **k):
            raise ORI.OpenRocketExportDataError(
                ['propellant_mass_kg'],
                {'propellant_mass_kg': 'enjekte edilmis olcum arizasi'},
                what='.eng')
        monkeypatch.setattr(ORI.OpenRocketExporter, 'export_motor_file',
                            _reddet)
        yanit, govde = _hesapla(istemci)
        assert yanit.status_code == 200, (
            f'.eng reddi tüm isteği düşürdü (HTTP {yanit.status_code})')
        orx = govde['openrocket']
        assert orx['eng_file'] is None, 'ret varken sahte .eng yazılmış'
        hata = orx['eng_error']
        assert hata and hata['error'] == 'missing_export_data'
        assert hata['missing_fields'] == ['propellant_mass_kg']
        assert 'propellant_mass_kg' in hata['field_reasons']
        # Ana sonuç yerinde: motor gerçekten çözülmüş.
        assert govde['motor']['thrust'] == pytest.approx(HYBRID_BASE['thrust'])


# ===========================================================================
# H2 — calculate_trajectory KAPISI
# ===========================================================================
class TestH2YorungeKapisi:
    """Kanal vardı, kapı yoktu: ``'false'`` metni yörüngeyi AÇIYORDU.

    Ölçüm (once.json): False -> yörünge yok, 0 -> yörünge yok,
    ``'false'`` -> yörünge VAR (8 anahtarlı tam uçuş bloğu + figür).
    """

    @pytest.mark.parametrize('deger', [False, 'false', 0, 'off'])
    def test_kapali_bayrak_yorungeyi_ATLAR(self, istemci, deger):
        yanit, govde = _hesapla(istemci, calculate_trajectory=deger)
        assert yanit.status_code == 200
        yor = govde.get('trajectory')
        assert isinstance(yor, dict), f'{deger!r}: yörünge bloğu sözlük değil'
        assert yor.get('skipped') is True, (
            f'{deger!r} gönderildiği hâlde yörünge hesaplandı: '
            f'{sorted(yor)[:8]}')
        assert yor.get('reason') == 'calculate_trajectory_false'
        # Atlanan adım UÇUŞ SAYISI YAYIMLAMAZ.
        assert 'performance' not in yor and 'trajectory' not in yor
        assert (govde.get('plots') or {}).get('trajectory') is None

    def test_acik_bayrakta_yorunge_tam(self, taban):
        _yanit, govde = taban
        yor = govde['trajectory']
        assert yor.get('skipped') is None
        assert 'performance' in yor and 'flight_status' in yor

    def test_bayrak_olmayan_deger_ADIYLA_reddedilir(self, istemci):
        yanit, govde = _hesapla(istemci, calculate_trajectory='peynir')
        assert yanit.status_code >= 400
        assert 'calculate_trajectory' in str(govde)

    def test_slim_atlanan_yorungeyi_KIRPILMIS_gibi_gostermez(self, istemci):
        """?slim=1 + atlanan yörünge: "düşürüldü" künyesi basılmaz.

        slim=1 iki ağır alanı (``trajectory``/``motor_data``) düşürdüğünü
        BEYAN eder. Atlanan yörünge bloğunda o alanlar zaten yoktur —
        hesaplanmadılar. İkisini aynı künyeyle anlatmak, hiç koşmamış bir
        adımı "kırpılmış çıktı" gibi gösterirdi.
        """
        yuk = dict(HYBRID_BASE)
        yuk['calculate_trajectory'] = False
        yanit = _sessiz(istemci.post, '/calculate?slim=1', json=yuk)
        assert yanit.status_code == 200
        yor = (yanit.get_json() or {})['trajectory']
        assert yor.get('skipped') is True
        assert 'omitted_fields' not in yor, (
            'atlanan yörünge slim künyesiyle "düşürülmüş" gösterildi')


# ===========================================================================
# H3 — HARİTANIN KATI REFAKAT DEĞERLERİ KIRPMA BANDININ İÇİNDE
# ===========================================================================
class TestH3KatiRefakatDegerleri:
    """Refakat değeri kırpma sınırının üstündeyse alan YALANCI ÖLÜ görünür.

    Ölçüm (once.json): star_radius 18 -> 27 ve fin_length 25 -> 37,5
    sarsımlarında yanıt BİT-AYNI (ikisi de 17,20 / 18,275 mm'ye kırpılıyor);
    haritada iki alan da ÖLÜ çıkıyordu. Bant içinde ölçülünce ikisi de
    binlerce yaprağı oynatıyor.
    """

    ALANLAR = (('star_radius', 'star', 'star_points'),
               ('fin_length', 'finocyl', 'fin_count'))

    @staticmethod
    def _katı_taban():
        import json
        import pathlib
        import sys
        kok = pathlib.Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(kok / 'tools'))
        import wiring_map as wm
        ornek = kok / 'examples' / wm.EXAMPLE_FOR['solid']
        with ornek.open(encoding='utf-8') as fh:
            proje = json.load(fh)
        taban = dict((proje.get('inputs') or {}).get('fields') or {})
        ozellikler = inventory.field_specs_for('solid')
        for ad, alan in ozellikler.items():
            if ad in taban or alan.kind != 'choice':
                continue
            deger = alan.default or (list(alan.options)[0]
                                     if alan.options else None)
            # V3.0.5 T-ÇAPA-C1 (altyapı): seçenekleri Jinja döngüsüyle basılan
            # seçici (K-C2 5633a8448: katı yakıt seçici) statik şablonda
            # '{{ o.key }}' yer tutucusu taşır — bu bir değer DEĞİL; tarayıcı
            # o alanı işlenmiş sayfadan okur. Yer tutucu gövdeye konmaz.
            if isinstance(deger, str) and '{{' in deger:
                continue
            if deger not in (None, ''):
                taban[ad] = deger
        return wm, taban

    @pytest.mark.parametrize('alan,grain,kardes', ALANLAR)
    def test_refakat_degeri_sarsimla_birlikte_KIRPILMAZ(
            self, istemci, alan, grain, kardes):
        wm, taban = self._katı_taban()
        baglam = dict(wm.CONTEXTS['solid'][alan])
        assert baglam.get('grain_type') == grain
        assert kardes in baglam, f'{alan} refakatinde {kardes} yok'

        def kos(ezme):
            yuk = dict(taban)
            yuk.update(ezme)
            yanit = _sessiz(istemci.post, '/calculate_solid', json=yuk,
                            headers=shake.HEADERS)
            assert yanit.status_code == 200, (
                f'{ezme} HTTP {yanit.status_code}')
            return dict(shake.leaves(yanit.get_json()))

        onceki = kos(baglam)
        kirpilan = [y for y, d in onceki.items()
                    if y.endswith('.clipped') or '.clipped[' in y]
        assert alan not in [str(onceki[y]) for y in kirpilan], (
            f'{alan} refakat değeri ({baglam[alan]}) motorun kırpma '
            f'sınırının üstünde — bu değerle ölçüm yalancı ölü verir')

        ozellik = inventory.field_specs_for('solid')[alan]
        sarsilmis_deger = shake.perturb(
            shake.FieldSpec(name=alan, kind=ozellik.kind,
                            lo=ozellik.minimum, hi=ozellik.maximum,
                            options=tuple(ozellik.options or ()),
                            context=baglam),
            baglam[alan])
        assert sarsilmis_deger is not None
        sonraki = kos(dict(baglam, **{alan: sarsilmis_deger}))
        degisen = shake.differing_paths(onceki, sonraki)
        gercek = [y for y in degisen if not shake.is_echo(y, alan)]
        assert len(gercek) > 100, (
            f'{alan}: {baglam[alan]} -> {sarsilmis_deger} sarsımı yalnız '
            f'{len(gercek)} yaprak oynattı; refakat değeri hâlâ kırpma '
            f'bandının dışında olabilir')


# ===========================================================================
# H4 — ENJEKTÖR DEŞARJ KATSAYISI BANDI
# ===========================================================================
class TestH4DesarjKatsayisiBandi:
    """Cd kapısı /calculate'te YOKTU; panel çözücüsü ham değeri alıyordu.

    Ölçüm (once.json): Cd = 1,05 ve -0,3 -> HTTP 200 ama CAD "Not all
    meshes are volumes!"; Cd = 0 -> HTTP 400 + çıplak
    "cannot convert float infinity to integer".
    """

    @pytest.mark.parametrize('cd', [1.05, 0, -0.3, 'peynir'])
    def test_bant_disi_cd_ADIYLA_reddedilir(self, istemci, cd):
        yanit, govde = _hesapla(istemci, discharge_coefficient=cd)
        assert yanit.status_code == 422, (
            f'Cd={cd!r} HTTP {yanit.status_code} ile geçti')
        alanlar = govde.get('invalid_fields') or []
        assert alanlar and alanlar[0]['field'] == 'discharge_coefficient'
        assert alanlar[0]['min'] == USER_CD_RANGE[0]
        assert alanlar[0]['max'] == USER_CD_RANGE[1]

    def test_bant_ici_cd_gecer_ve_CAD_cokmez(self, istemci, taban):
        _yanit, govde = taban
        assert HYBRID_BASE['discharge_coefficient'] == 0.7
        assert (govde.get('cad_design') or {}).get('error') is None
        # Bandın ÜST UCU dahildir (Cd = 1: kayıpsız orifis, fiziksel sınır).
        yanit, _g = _hesapla(istemci,
                             discharge_coefficient=USER_CD_RANGE[1])
        assert yanit.status_code == 200

    def test_bant_TEK_KAYNAKTAN_okunur(self):
        """Sayı app.py'ye ikinci kez yazılamaz."""
        import pathlib
        kok = pathlib.Path(__file__).resolve().parents[1]
        kaynak = (kok / 'hrma' / 'app.py').read_text(encoding='utf-8')
        assert 'USER_CD_RANGE' in kaynak
        assert "'discharge_coefficient', 0.20, 1.0" not in kaynak
        assert math.isclose(USER_CD_RANGE[1], 1.0)


# ===========================================================================
# H5 — SABİT SINIFLANDIRMA KURALLARI
# ===========================================================================
class TestH5SabitSiniflandirma:
    """Sınıflandırma ölçerek genişletildi; gevşetilmedi.

    Ölçüm (once.json -> sonra.json, üç sayfanın taban yanıtı):
    SINIFLANDIRILMAMIŞ 326 -> 157 (hibrit 114 -> 50, sıvı 157 -> 89,
    katı 55 -> 18). ``beyanli_zayif`` 49'da SABİT kaldı: düşüş tamamen
    GÜÇLÜ yollardan geldi.
    """

    @staticmethod
    def _sinif():
        import pathlib
        import sys
        kok = pathlib.Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(kok / 'tools'))
        import sabit_siniflandirma as ss
        return ss

    def test_mod_numaralandirma_ekseni_izgaradir(self):
        ss = self._sinif()
        yapraklar = {
            '.acoustic_modes.modes[0].indices.longitudinal_q': 1,
            '.acoustic_modes.modes[0].indices.radial_n': 0,
            '.acoustic_modes.modes[0].indices.tangential_m': 0,
            '.acoustic_modes.modes[0].frequency_hz': 663.63,
        }
        for yol in list(yapraklar)[:3]:
            sinif, _g = ss.siniflandir(yol, yapraklar[yol], yapraklar)
            assert sinif == 'izgara', (yol, sinif)
        # Frekans SONUÇTUR: aklanmaz.
        sinif, _g = ss.siniflandir('.acoustic_modes.modes[0].frequency_hz',
                                   663.63, yapraklar)
        assert sinif == 'SINIFLANDIRILMAMIS'

    def test_esit_arali_eksen_aklanir_SONUC_aklanmaz(self):
        """Aynı ``*_sweep`` bloğunda eksen ızgara, sonuç değil."""
        ss = self._sinif()
        yapraklar = {}
        for i in range(6):
            yapraklar[f'.slosh.fill_sweep.fill_ratio[{i}]'] = 0.085 + 0.1735 * i
        for i, v in enumerate((0.8300, 0.7789, 0.6959, 0.6048, 0.5207,
                               0.4493)):
            yapraklar[f'.slosh.fill_sweep.slosh_mass_ratio[{i}]'] = v
        sinif, gerekce = ss.siniflandir('.slosh.fill_sweep.fill_ratio[2]',
                                        yapraklar['.slosh.fill_sweep.fill_ratio[2]'],
                                        yapraklar)
        assert sinif == 'izgara', gerekce
        sinif2, _g = ss.siniflandir(
            '.slosh.fill_sweep.slosh_mass_ratio[2]',
            yapraklar['.slosh.fill_sweep.slosh_mass_ratio[2]'], yapraklar)
        assert sinif2 == 'SINIFLANDIRILMAMIS', (
            'eşit aralıklı OLMAYAN sweep sonucu ızgara sayıldı — kural '
            'adla değil ölçümle çalışmalı')

    def test_bilesik_birim_soneki_golgelenmez(self):
        ss = self._sinif()
        assert ss._birimsiz('line_velocity_band_m_s') == 'line_velocity_band'
        yapraklar = {
            '.line.line_velocity_band_m_s[0]': 3.0,
            '.line.line_velocity_band_m_s[1]': 8.0,
            '.line.line_velocity_band_status': 'within',
        }
        sinif, gerekce = ss.siniflandir('.line.line_velocity_band_m_s[0]',
                                        3.0, yapraklar)
        assert sinif == 'beyanli', (sinif, gerekce)

    def test_onekli_beyan_YALNIZ_guclu_dalda_gecerli(self):
        """``rule_source`` gibi önekli beyan jeton eşleşmesi İSTER."""
        ss = self._sinif()
        eslesen = {
            '.cc.rule_min_ratio': 0.15,
            '.cc.rule_source': 'the rule min ratio is 0.15 of chamber pressure',
        }
        sinif, _g = ss.siniflandir('.cc.rule_min_ratio', 0.15, eslesen)
        assert sinif == 'beyanli'
        eslesmeyen = {
            '.cc.rule_min_ratio': 0.15,
            '.cc.rule_source': 'a citation that names nothing relevant',
        }
        sinif2, _g = ss.siniflandir('.cc.rule_min_ratio', 0.15, eslesmeyen)
        assert sinif2 == 'SINIFLANDIRILMAMIS', (
            'önekli beyan zayıf küçük-blok muafiyetine düşmüş — genişletme '
            'yalnız güçlü dal için')

    def test_eksen_baslangici_tanimdir(self):
        ss = self._sinif()
        yapraklar = {'.nozzle_flow_quasi1d.x_m[0]': 0.0,
                     '.nozzle_flow_quasi1d.x_m[1]': 0.0031}
        sinif, _g = ss.siniflandir('.nozzle_flow_quasi1d.x_m[0]', 0.0,
                                   yapraklar)
        assert sinif == 'tanim'
