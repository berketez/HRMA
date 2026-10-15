"""ÖH D24 · kulvar `ihracat` · aşama 2 — onarım bekçileri.

Her sınıf bir defter kalemine bağlıdır ve ters-mutasyonla kırmızıya
düşürüldüğü kanıtlanmıştır (``docs/scofield/raw/OH/D24/ihracat/a2/
mutasyon.json``). Ölçüm dosyaları: ``once.json`` (taban 88a29d3 arşivi) ve
``sonra.json`` (bu ağaç).
"""
import ast
import io
import contextlib
import os
import re

import pytest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _oku(*p):
    with open(os.path.join(KOK, *p), encoding='utf-8') as fh:
        return fh.read()


# ===========================================================================
# P9B3-24 — OpenRocketExporter.generate_technical_report ölü ikizi
# ===========================================================================
class TestP9B324OluIkiz:
    """Ölü ikiz geri gelmez; CANLI ikiz aynı yalanları taşımaz.

    ÖLÇÜLDÜ (``once.json`` -> ``M1_P9B3_24``, taban 88a29d3): 93 satır,
    ürün çağıranı 0, uydurma varsayılan 4 (``chamber_pressure``, ``of_ratio``,
    ``c_star``, ``cf`` -> ``get(ad, 0)``), koşulsuz "✓" 4, ve boş gövdeyle::

        Chamber Pressure: 0.0 bar / O/F Ratio: 0.00
        C* Efficiency: 0 m/s      / Thrust Coefficient: 0.000
    """

    def test_sembol_openrocket_ihracatcisinda_yok(self):
        from hrma.export.openrocket_integration import OpenRocketExporter
        assert not hasattr(OpenRocketExporter, 'generate_technical_report'), (
            'ölü ikiz geri gelmiş: 0 ürün çağıranı olan, uydurma varsayılan '
            've koşulsuz onay basan metin raporu')

    def test_kaynakta_tanim_yok(self):
        kaynak = _oku('hrma', 'export', 'openrocket_integration.py')
        agac = ast.parse(kaynak)
        adlar = {f.name for f in ast.walk(agac)
                 if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))}
        assert 'generate_technical_report' not in adlar

    def test_cstar_hiz_olarak_verim_diye_basilmiyor(self):
        """``c_star`` [m/s] hiçbir ihraç yolunda "C* Efficiency" olamaz."""
        for modul in ('openrocket_integration.py', 'pdf_generator.py',
                      'cad_visualization.py', 'drawing_generator.py'):
            kaynak = _oku('hrma', 'export', modul)
            for satir in kaynak.splitlines():
                govde = satir.split('#')[0]
                if 'C* Efficiency' not in govde:
                    continue
                assert 'c_star' not in govde or 'efficiency' in govde, (
                    f'{modul}: karakteristik hız "C* Efficiency" başlığıyla '
                    f'basılıyor -> {satir.strip()}')

    def test_canli_pdf_ikizi_yerinde(self):
        """Silinen sembolün adı CANLI ikizde durmalı (yanlış silme kapısı)."""
        from hrma.export.pdf_generator import PDFReportGenerator
        assert callable(getattr(PDFReportGenerator,
                                'generate_technical_report', None))


# ===========================================================================
# P9B4-22 — burn_rate_*_used ⟷ burn_rate_basis çelişkisi
# ===========================================================================
@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _solid(client, **kw):
    govde = {'motor_name': 'd24a2', 'propellant_type': 'apcp',
             'chamber_pressure': 40, 'chamber_diameter': 100,
             'grain_length': 500, 'core_diameter': 30,
             'grain_outer_diameter': 90, 'nozzle_throat_diameter': 25,
             'nozzle_expansion_ratio': 8}
    govde.update(kw)
    r = client.post('/calculate_solid', json=govde)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


class TestP9B422KullanildiAdiHukumTasir:
    """"used" adı bir iddiadır; aynı yanıt onu yalanlayamaz.

    ÖLÇÜLDÜ (``once.json`` -> ``M2_P9B4_22``, taban 88a29d3): kndx/knsb
    gövdelerinde ``burn_rate_basis`` "... was NOT used ..." derken
    ``burn_rate_a_used`` = 0,0007876462766690173 / 0,0011398387343702558
    dolu sayı taşıyordu (``CELISKI: true``).
    """

    @staticmethod
    def _basis(sonuc):
        yigin = [sonuc]
        while yigin:
            d = yigin.pop()
            if isinstance(d, dict):
                if isinstance(d.get('burn_rate_basis'), str):
                    return d['burn_rate_basis']
                yigin.extend(v for v in d.values() if isinstance(v, dict))
        return None

    @pytest.mark.parametrize('yakit', ['kndx', 'knsb'])
    def test_parcali_yasada_used_alanlari_bos(self, client, yakit):
        sonuc = _solid(client, propellant_type=yakit)
        girdiler = sonuc['burn_rate_inputs']
        temel = self._basis(sonuc)
        assert temel and 'NOT used' in temel, (
            f'{yakit}: senaryo geçersiz — parçalı yasa etkin değil')
        assert girdiler['burn_rate_pair_used'] is False
        assert girdiler['burn_rate_a_used'] is None, (
            f'{yakit}: yanıt "bu çift KULLANILMADI" derken '
            f'burn_rate_a_used = {girdiler["burn_rate_a_used"]!r}')
        assert girdiler['burn_rate_n_used'] is None

    @pytest.mark.parametrize('yakit', ['kndx', 'knsb'])
    def test_cozulen_cift_kaybolmuyor(self, client, yakit):
        """Bilgi kaybı YOK: çözülen çift ``*_resolved`` ile aynen durur."""
        from hrma.engines.solid_rocket_engine import _catalog_burn_rate
        sonuc = _solid(client, propellant_type=yakit)
        girdiler = sonuc['burn_rate_inputs']
        a_cat, n_cat = _catalog_burn_rate(yakit)
        assert girdiler['burn_rate_a_resolved'] == pytest.approx(float(a_cat))
        assert girdiler['burn_rate_n_resolved'] == pytest.approx(float(n_cat))
        gerekce = girdiler.get('burn_rate_pair_unused_reason') or ''
        assert yakit in gerekce and '_resolved' in gerekce, (
            'ret gerekçesi hangi yasanın ezdiğini ve çiftin nerede '
            f'durduğunu söylemiyor: {gerekce!r}')

    def test_yasa_yokken_davranis_degismedi(self, client):
        """APCP'de parçalı yasa yok -> ``*_used`` eskisi gibi sayı taşır."""
        from hrma.engines.solid_rocket_engine import _catalog_burn_rate
        sonuc = _solid(client, propellant_type='apcp')
        girdiler = sonuc['burn_rate_inputs']
        a_cat, n_cat = _catalog_burn_rate('apcp')
        assert girdiler['burn_rate_pair_used'] is True
        assert girdiler['burn_rate_a_used'] == pytest.approx(float(a_cat))
        assert girdiler['burn_rate_n_used'] == pytest.approx(float(n_cat))

    def test_kunye_beyanla_yetinmiyor(self, client):
        """Eski ``_basis`` metni çelişkiyi BEYANLA karşılıyordu; artık hüküm
        makine-okur bir alanda."""
        sonuc = _solid(client, propellant_type='kndx')
        temel = sonuc['burn_rate_inputs']['_basis']
        assert 'burn_rate_pair_used' in temel
        assert 'separate question' not in temel, (
            'beyan çözüm yerine geçiyor: künye hâlâ "ayrı bir soru" diyor')


# ===========================================================================
# P9B5-29 — gömülü rp1 CID'i (ÇÜRÜTÜLDÜ; kapı kilidi burada da ölçülür)
# ===========================================================================
class TestP9B529GomuluKarisimCidi:
    """Kalem başlığı ölçümle ÇÜRÜTÜLDÜ; ölçüm bekçi olarak bırakıldı.

    Başlık ``known_cids['rp1'] = 11006`` ile "n-dodecane as surrogate"
    yorumunun çeliştiğini söylüyordu. ÖLÇÜLDÜ (``once.json`` -> ``M3_P9B5_29``,
    TABANDA): ``known_cids_karisim_anahtarlari: []``,
    ``known_cids_11006_tasiyor: false``, ``dodecane_yorumu_var: false``.
    Gömülü CID'ler D15 / defter P9B4-05 ile silinmişti; başlığın anlattığı kod
    taban ağacında YOK. Kalemin "bekçisiz" notu da ölçümle çürüdü —
    ``tests/test_z5guard_ihrac_veri.py`` zaten kapıyı koruyordu; buradaki
    bekçi o iddiayı DEĞİL, çürütmenin kendisini kalıcı kılar.
    """

    def test_karisimlarin_gomulu_cidi_yok(self):
        from hrma.data.open_source_propellant_api import (
            OpenSourcePropellantAPI)
        api = OpenSourcePropellantAPI()
        for karisim in ('rp1', 'kerosene', 'paraffin', 'paraffin_wax'):
            assert karisim not in api.known_cids
            assert karisim in api.PUBCHEM_POLYMER_DENY

    def test_hekzadekan_cidi_hicbir_ada_bagli_degil(self):
        from hrma.data.open_source_propellant_api import (
            OpenSourcePropellantAPI)
        api = OpenSourcePropellantAPI()
        assert 11006 not in set(api.known_cids.values()), (
            'CID 11006 (hekzadekan, C16H34, MA 226,44) bir ada geri bağlanmış')

    def test_celiskili_dodecane_yorumu_yok(self):
        kaynak = _oku('hrma', 'data', 'open_source_propellant_api.py')
        for satir in kaynak.splitlines():
            if 'dodecane' in satir.lower():
                assert 'C12' not in satir, (
                    'CID 11006 yeniden "n-dodecane vekili" diye anlatılıyor; '
                    'o kayıt hekzadekandır')


# ===========================================================================
# P9B5-30 — burn_rate_n ⟷ pressure_exponent ikizi
# ===========================================================================
class TestP9B530UstelIkizi:
    """Saint-Robert üsteli TEK adla yayımlanır.

    ÖLÇÜLDÜ (``once.json`` -> ``M4_P9B5_30``, taban 88a29d3):
    kndx için ``burn_rate_n`` 0,45 ⟷ ``pressure_exponent`` 0,35 (fark −0,10,
    %22); apcp'de ikisi rastlantıyla eşitti.
    """

    @staticmethod
    def _ui(ad):
        from hrma.data.open_source_propellant_api import (
            OpenSourcePropellantAPI)
        with contextlib.redirect_stdout(io.StringIO()):
            return OpenSourcePropellantAPI().get_propellant_for_ui(
                'solid_propellant', ad)

    @pytest.mark.parametrize('ad', ['apcp', 'kndx'])
    def test_ikinci_ustel_yayimlanmiyor(self, ad):
        d = self._ui(ad)
        assert 'pressure_exponent' not in d, (
            f'{ad}: aynı büyüklük iki adla yayımlanıyor '
            f'(burn_rate_n={d.get("burn_rate_n")!r}, '
            f'pressure_exponent={d.get("pressure_exponent")!r})')

    def test_ustel_hala_yayimlaniyor(self):
        """Ad silindi, BÜYÜKLÜK silinmedi (aşırı onarım kapısı)."""
        d = self._ui('kndx')
        assert isinstance(d.get('burn_rate_n'), (int, float))
        assert d['burn_rate_n'] == pytest.approx(0.45)

    def test_kaynakta_sabit_ustel_literali_yok(self):
        kaynak = _oku('hrma', 'data', 'open_source_propellant_api.py')
        canli = [ln for ln in kaynak.splitlines()
                 if re.search(r"^\s*'pressure_exponent':", ln)]
        assert not canli, f'sabit ikinci üstel geri gelmiş: {canli}'


# ===========================================================================
# P9B5-31 — advanced.html koşulsuz return; altındaki ölü akış
# ===========================================================================
class TestP9B531OluAkis:
    """Ölü API akışı silindi; yerine "geçici olarak kapalı" kod bırakılmadı.

    ÖLÇÜLDÜ (``once.json`` -> ``M5_P9B5_31``): koşulsuz ``return;`` satır
    3265, altında 58 satır (51 dolu) ulaşılamaz kod, içinde
    ``/api/get-propellant-properties`` çağrısı ve ``showSuccess``.
    """

    @staticmethod
    def _kaynak():
        return _oku('hrma', 'templates', 'advanced.html')

    def test_kosulsuz_return_ve_gerekcesi_yok(self):
        metin = self._kaynak()
        assert 'Skip API call for now to avoid override issues' not in metin

    def test_olu_fetch_blogu_yok(self):
        metin = self._kaynak()
        # Yakıt özelliği çekme akışının ölü kalıntıları
        for iz in ("propellant_type: 'hybrid_fuel'",
                   'if (props.regression_a) regressionA.value'):
            assert iz not in metin, f'ölü akış kalıntısı duruyor: {iz}'

    def test_literatur_tablosu_yerinde(self):
        """Silme, KAYNAKLI tabloyu götürmedi (aşırı onarım kapısı)."""
        metin = self._kaynak()
        assert 'const fuelProperties' in metin
        for yakit in ('htpb', 'pe', 'pmma', 'paraffin', 'abs'):
            assert f"'{yakit}':" in metin

    def test_yerel_tablo_ile_api_ayrisiyor_gerekce_gecerli(self):
        """Ölü akış canlansaydı sayılar DEĞİŞİRDİ — silme gerekçesinin ölçümü.

        ``once.json`` -> ``M5b_P9B5_31_regres``: beş yakıtta ayrışma.
        """
        from hrma.data.open_source_propellant_api import (
            OpenSourcePropellantAPI)
        metin = self._kaynak()
        m = re.search(r'const fuelProperties = \{(.*?)\n            \};',
                      metin, re.S)
        assert m, 'yerel tablo bulunamadı'
        yerel = {}
        for satir in m.group(1).splitlines():
            mm = re.match(r"\s*'([a-z0-9_]+)':\s*\{ density: ([0-9.e-]+), "
                          r"a: ([0-9.e-]+), n: ([0-9.e-]+)", satir)
            if mm:
                yerel[mm.group(1)] = (float(mm.group(2)), float(mm.group(3)),
                                      float(mm.group(4)))
        api = OpenSourcePropellantAPI()
        ayrisan = []
        for ad, (rho, a, n) in yerel.items():
            if ad in ('custom', 'mixture'):
                continue
            with contextlib.redirect_stdout(io.StringIO()):
                d = api.get_propellant_for_ui('hybrid_fuel', ad)
            if d.get('regression_a') is None:
                continue
            if (abs(float(d['regression_a']) - a) > 1e-15
                    or abs(float(d['regression_n']) - n) > 1e-12
                    or abs(float(d['density']) - rho) > 1e-9):
                ayrisan.append(ad)
        assert len(ayrisan) >= 5, (
            'silme gerekçesi çürüdü: açık kaynak API katmanı artık yerel '
            f'literatür tablosuyla aynı sayıları veriyor ({ayrisan})')


# ===========================================================================
# P9B5-34 — ÜÇGEN kanatta gereksiz "MAC korunamadı" notu
# ===========================================================================
class TestP9B534UcgenKanatMacNotu:
    """Not KAZANILIR: yalnız MAC gerçekten korunamadığında yazılır.

    ÖLÇÜLDÜ (``once.json`` -> ``M6_P9B5_34``, taban 88a29d3): üçgen kanatta
    hedef MAC 0,10000019073 m, trapez MAC 0,10000000000 m, bağıl fark
    1,9e-06 (513 noktalı tarama gürültüsü) — buna rağmen not basılıyordu.
    """

    UCGEN = [(0.0, 0.0), (0.0, 0.20), (0.15, 0.0)]
    UCGEN_SUPURMELI = [(0.0, 0.0), (0.10, 0.20), (0.15, 0.0)]
    TRAPEZ = [(0.0, 0.0), (0.05, 0.20), (0.12, 0.20), (0.15, 0.0)]
    #: MAC > (2/3)·(2A/s): trapezle TEMSİL EDİLEMEZ (kök yakını kalın, uç ince)
    TEMSIL_EDILEMEZ = [(0.0, 0.0), (0.0, 0.10), (0.0725, 0.10), (0.0725, 0.20),
                       (0.0775, 0.20), (0.0775, 0.10), (0.15, 0.10),
                       (0.15, 0.0)]

    @staticmethod
    def _don(pts):
        from hrma.importers.ork_import import _freeform_to_trapezoid
        r = _freeform_to_trapezoid([(float(x), float(y)) for x, y in pts])
        assert r is not None
        return r

    @pytest.mark.parametrize('ad', ['UCGEN', 'UCGEN_SUPURMELI'])
    def test_ucgende_not_basilmiyor(self, ad):
        r = self._don(getattr(self, ad))
        assert r['tip'] == pytest.approx(0.0, abs=1e-12), (
            'senaryo geçersiz: bu geometri üçgene inmiyor')
        assert not r['notes'], (
            'üçgen kanatta "MAC korunamadı" notu basılıyor; dönüşüm bu sınır '
            f'halde kesindir: {r["notes"]}')

    def test_ucgende_mac_gercekten_korunuyor(self):
        """Notun basılmaması KEYFİ değil: sapma tarama gürültüsü kadar."""
        r = self._don(self.UCGEN)
        mac_trapez = (2.0 / 3.0) * r['root']
        assert abs(mac_trapez - r['mac']) / r['mac'] < 1e-5

    def test_trapezde_not_zaten_yok(self):
        assert not self._don(self.TRAPEZ)['notes']

    def test_temsil_edilemeyen_bicimde_not_KAZANILIYOR(self):
        """Kapı körlemesine kapatılmadı: gerçek kayıpta not sayıyla basılır."""
        r = self._don(self.TEMSIL_EDILEMEZ)
        assert r['tip'] == pytest.approx(0.0, abs=1e-12)
        assert r['notes'], (
            'MAC gerçekten korunamayan dış çizgide de not susuyor — kapı '
            'körlemesine kapatılmış')
        metin = r['notes'][0]
        assert 'target MAC' in metin and 'achieved' in metin, (
            f'not sayı taşımıyor: {metin!r}')
        assert 'relative deviation' in metin

    def test_notun_bildirdigi_sayilar_gercek(self):
        r = self._don(self.TEMSIL_EDILEMEZ)
        metin = r['notes'][0]
        m = re.search(r'target MAC ([0-9.e+-]+) m, achieved ([0-9.e+-]+) m',
                      metin)
        assert m, metin
        assert float(m.group(1)) == pytest.approx(r['mac'], rel=1e-5)
        assert float(m.group(2)) == pytest.approx((2.0 / 3.0) * r['root'],
                                                  rel=1e-5)


# ===========================================================================
# P14M1-11 — yanlışı savunan totoloji bekçisi (çevrildi)
# ===========================================================================
class TestP14M111KilitliBekciCevrildi:
    """Bekçi artık ürünün BAYRAĞIYLA tutarlılık arar, sabitliği ŞART koşmaz.

    ÖLÇÜLDÜ (``once.json`` -> ``M7_P14M1_11``, taban 88a29d3):
    ``sabit_kilit_asserti: true``, ``protokol_mesaji: true``,
    ``iki_yonlu_iddia: false`` -> savcının "YANLIŞI-SAVUNAN" hükmü.
    """

    @staticmethod
    def _govde():
        kaynak = _oku('tests', 'test_kati_rapor_ornekleme.py')
        agac = ast.parse(kaynak)
        for f in ast.walk(agac):
            if (isinstance(f, ast.FunctionDef)
                    and f.name.startswith(
                        'test_cidar_verilmeyince_emniyet_katsayisi')):
                return ast.get_source_segment(kaynak, f) or ''
        return None

    def test_bekci_duruyor(self):
        assert self._govde() is not None, (
            'P14M1-11 bekçisi silinmiş; kilit kaldırılırken iddia da '
            'kaldırılmış olamaz')

    def test_kosulsuz_sabitlik_sarti_yok(self):
        govde = self._govde()
        kod = '\n'.join(ln for ln in govde.splitlines()
                        if not ln.lstrip().startswith('#'))
        # `len(katsayilar) == 1` yalnız bayrak True dalının İÇİNDE olabilir.
        agac = ast.parse('if True:\n' + '\n'.join(
            '    ' + ln for ln in kod.splitlines()))
        kosulsuz = []
        for d in ast.walk(agac):
            if not isinstance(d, ast.FunctionDef):
                continue
            for st in d.body:
                if (isinstance(st, ast.Assert)
                        and 'len(katsayilar) == 1' in ast.unparse(st.test)):
                    kosulsuz.append(ast.unparse(st.test))
        assert not kosulsuz, (
            'sabit-katsayı şartı fonksiyon gövdesinde koşulsuz duruyor: '
            'totolojiyi kaldıran onarım bu bekçiyi kırar')

    def test_iki_yonlu_iddia_var(self):
        govde = self._govde()
        assert 'safety_factor_is_tautological' in govde
        assert 'len(katsayilar) > 1' in govde, (
            'bayrak False olduğunda SF\'nin artık eko OLAMAYACAĞI '
            'sınanmıyor — bekçi tek yönlü kalmış')

    def test_bugunku_urun_totolojik_dali_gercekten_kosuyor(self):
        """Senaryo canlı: ürün bugün bayrağı True veriyor (dal ölçülebilir)."""
        from hrma.engines.solid_rocket_engine import SolidRocketEngine
        m = SolidRocketEngine(chamber_pressure=40)
        ca = m._calculate_structural_analysis()['case_analysis']
        assert ca['design_mode'] == 'size'
        assert ca['safety_factor_is_tautological'] is True


# ===========================================================================
# P15B2-11 — tek adın üç ayrı büyüklüğü taşıması
# ===========================================================================
class TestP15B211RolAdlari:
    """``step_import`` eşikleri rolüne/boyutuna göre adlandırılmış olmalı.

    ÖLÇÜLDÜ (``once.json`` -> ``M8_P15B2_11``, taban 88a29d3): tek
    ``_EPS = 1e-9``, dört kullanım, üç farklı boyut (boyutsuz / mm / mm²),
    rol künyesi yok. Sayı DEĞİŞMEDİ; ayrışan yalnız adlar ve künyeler.
    """

    def test_rol_adlari_var_ve_kunyeli(self):
        import hrma.importers.step_import as si
        kaynak = _oku('hrma', 'importers', 'step_import.py')
        for ad in ('_UNIT_VECTOR_MIN_NORM', '_RELATIVE_DIV_FLOOR_MM',
                   '_DEGENERATE_AREA_MM2'):
            assert hasattr(si, ad), f'{ad} tanımlı değil'
            assert re.search(r'^#:.*\n(#:.*\n)*' + ad + r'\s*=', kaynak,
                             re.M), f'{ad} künyesiz tanımlanmış'

    def test_eski_coklu_rol_adi_kalmadi(self):
        kaynak = _oku('hrma', 'importers', 'step_import.py')
        canli = [ln for ln in kaynak.splitlines()
                 if not ln.lstrip().startswith('#')
                 and re.search(r'(?<![A-Za-z0-9_])_EPS(?![A-Za-z0-9_])', ln)]
        assert not canli, (
            f'tek ad üç boyutu taşımaya dönmüş: {canli}')

    def test_degerler_degismedi(self):
        import hrma.importers.step_import as si
        assert si._UNIT_VECTOR_MIN_NORM == 1e-9
        assert si._RELATIVE_DIV_FLOOR_MM == 1e-9
        assert si._DEGENERATE_AREA_MM2 == 1e-9

    def test_dort_kullanim_da_kendi_adini_kullaniyor(self):
        kaynak = _oku('hrma', 'importers', 'step_import.py')
        assert 'n > _UNIT_VECTOR_MIN_NORM' in kaynak
        assert kaynak.count('_RELATIVE_DIV_FLOOR_MM)') == 2
        assert 'total_area <= _DEGENERATE_AREA_MM2' in kaynak

    def test_kardes_tanimlar_farkli_rol_olarak_beyanli(self):
        """Kalemin "üç mertebe" iddiası: adlar aynı DEĞİL, roller ayrı.

        Bu bekçi kardeş kulvarların dosyalarını DEĞİŞTİRMEZ; yalnız üç
        değerin hâlâ ayrıştığını ve birinin sessizce diğerine çekilmediğini
        kayda geçirir (ölçüm: ``M8_P15B2_11``).
        """
        bl = _oku('hrma', 'flow', 'boundary_layer.py')
        q1 = _oku('hrma', 'flow', 'quasi1d.py')
        js = _oku('hrma', 'static', 'js', 'analysis_dock.js')
        # ÖH D26 / fix-25b: sınır tabakası payının adı ARTIK ÇIPLAK DEĞİL.
        # D25 fea-cfd a2 (be85980) tam da BU kalemi (P15B2-11) uygulayıp
        # ``_EPS`` -> ``_LAMBDA_COMPARE_EPS`` yeniden adlandırmasını yaptı:
        # ad, taşıdığı role (boyutsuz Thwaites λ karşılaştırma payı) bağlandı.
        # DEĞER DEĞİŞMEDİ (1e-12) — bu bir çapa kayması değil, ad değişimidir.
        # Bekçi yeni adı okur; eski çıplak ad İKİZ OLARAK GERİ EKLENMEZ.
        assert re.search(r'^_LAMBDA_COMPARE_EPS\s*=\s*1e-12', bl, re.M)
        assert re.search(r'^_MACH_EPS\s*=\s*1e-9', q1, re.M)
        assert re.search(r'DIFF_REL_EPS\s*=\s*1e-5', js)
        # Kalemin asıl iddiası: çıplak ad geri gelip üç rolü yeniden tek
        # ada toplamasın (step_import.py için aynı bekçi yukarıda var).
        canli = [ln for ln in bl.splitlines()
                 if not ln.lstrip().startswith('#')
                 and re.search(r'(?<![A-Za-z0-9_])_EPS(?![A-Za-z0-9_])', ln)]
        assert not canli, f'çıplak _EPS sınır tabakasına geri dönmüş: {canli}'


# ===========================================================================
# P16B4-25 — PDF hazne basıncı ham eko + sabit 'bar' etiketi
# ===========================================================================
class TestP16B425HaznebasinciEtiketi:
    """'bar' etiketi kazanılır; bant TEK KAYNAKTAN okunur.

    ÖLÇÜLDÜ (``once.json`` -> ``M9_P16B4_25``, taban 88a29d3):
    ``2000000.0 -> "2000000.0 bar"``, ``-3.0 -> "-3.0 bar"``,
    ``1e12 -> "1000000000000.0 bar"``.
    """

    def test_bant_form_limits_ten_geliyor(self):
        from hrma.export.pdf_generator import chamber_pressure_band_bar
        from hrma.validation.motor_validation import FORM_LIMITS
        alt, ust = chamber_pressure_band_bar()
        bantlar = [d['chamber_pressure'] for d in FORM_LIMITS.values()
                   if isinstance(d, dict) and 'chamber_pressure' in d]
        assert alt == min(float(b[0]) for b in bantlar)
        assert ust == max(float(b[1]) for b in bantlar)
        assert (alt, ust) == (1.0, 500.0)

    @pytest.mark.parametrize('deger', [20.0, 40.0, 1.0, 500.0, 200])
    def test_bant_ici_deger_aynen_gecer(self, deger):
        from hrma.export.pdf_generator import resolve_chamber_pressure_bar
        bar, red = resolve_chamber_pressure_bar(deger)
        assert bar == pytest.approx(float(deger))
        assert red is None

    @pytest.mark.parametrize('deger', [2000000.0, 5.0e6, -3.0, 1.0e12, 0.2])
    def test_bant_disi_deger_bar_etiketiyle_yayimlanmaz(self, deger):
        from hrma.export.pdf_generator import resolve_chamber_pressure_bar
        bar, red = resolve_chamber_pressure_bar(deger)
        assert bar is None, f'{deger} hâlâ "bar" diye yayımlanıyor'
        assert red and 'Chamber pressure was not published' in red
        assert f'{deger:g}' in red, 'ret gerekçesi reddedilen sayıyı söylemiyor'
        assert '1-500 bar' in red, 'ret gerekçesi kabul edilen bandı söylemiyor'

    @pytest.mark.parametrize('deger,iz', [
        (True, 'boolean'), ('kirk', 'not a number'),
        (float('nan'), 'not finite'), (float('inf'), 'not finite')])
    def test_sayi_olmayan_girdi_adiyla_reddediliyor(self, deger, iz):
        from hrma.export.pdf_generator import resolve_chamber_pressure_bar
        bar, red = resolve_chamber_pressure_bar(deger)
        assert bar is None
        assert red and iz in red, f'{deger!r} sessizce düşürülüyor: {red!r}'

    def test_alan_hic_yoksa_gerekce_de_yok(self):
        """Eksik alan bir kusur DEĞİLDİR; olmayan sayı için ret yazılmaz."""
        from hrma.export.pdf_generator import resolve_chamber_pressure_bar
        assert resolve_chamber_pressure_bar(None) == (None, None)

    def test_ret_birim_cevirisi_UYDURMUYOR(self):
        """2 MPa gövdesi 20 bar'a "düzeltilmez" — beyan yoksa sayı yok."""
        from hrma.export.pdf_generator import resolve_chamber_pressure_bar
        bar, _red = resolve_chamber_pressure_bar(2000000.0)
        assert bar is None
        assert bar != pytest.approx(20.0)

    def test_hucre_ve_gerekce_bir_arada(self):
        from hrma.export.pdf_generator import PDFReportGenerator
        g = PDFReportGenerator()
        assert g._fmt_unit(20.0, 'bar') == '20.0 bar'
        bar, red = __import__(
            'hrma.export.pdf_generator', fromlist=['x']
        ).resolve_chamber_pressure_bar(2000000.0)
        assert g._fmt_unit(bar, 'bar') == 'N/A'
        assert red

    def test_ham_eko_kaynakta_kalmadi(self):
        kaynak = _oku('hrma', 'export', 'pdf_generator.py')
        canli = [ln.strip() for ln in kaynak.splitlines()
                 if not ln.lstrip().startswith('#')
                 and "motor_data.get('chamber_pressure')" in ln
                 and "'bar'" in ln]
        assert not canli, f'ham eko geri gelmiş: {canli}'

    def test_kardes_cad_katmani_ayni_kurali_kullaniyor(self):
        """TEK KAYNAK: cad_visualization kendi bandını KURMAZ."""
        kaynak = _oku('hrma', 'export', 'cad_visualization.py')
        assert 'resolve_chamber_pressure_bar' in kaynak
        canli = [ln.strip() for ln in kaynak.splitlines()
                 if not ln.lstrip().startswith('#')
                 and re.search(r'f"\{pc:\.1f\} bar"', ln)]
        assert not canli, f'kardeş katmanda ham eko duruyor: {canli}'
