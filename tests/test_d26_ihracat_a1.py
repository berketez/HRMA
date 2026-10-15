"""ÖH Dalga-26 / ihracat aşama-1 bekçileri.

Kalemler
--------
OH-Z5-12  Kamara boyu bandının ret iletisi ⟷ kapının kendisi; ret, birim
          çevriminin ÜRETTİĞİ sayıyı basıyordu, kullanıcının yazdığını değil.
P9B1-25   Yayımlanmış ama çizilemez kamara boyu (negatif / 0 / NaN / metin)
          sessizce atılıp yerine L* türetmesi çiziliyordu.
P15B2-06  ``hrma/data`` altındaki merkezî fiziksel sabit literalleri
          (R ve g_0 ayakları fix aşamasında kapandı; kalan ``101325``).
P15B4-01  Aynı imalat paketinde STEP +X, STL +Z: 90° dönüklük, künyede eksen
          sözcüğü yok (bekçi-kırmızı borç imi kaldırıldı).

Bekçi borcu (P13B4-10 dağıtımı, ihracat satırları)
--------------------------------------------------
P9B1-02   Zarf çapı ÜRETİLEN katılardan ölçülür (formül tahmini ayrı alanda).
P9B4-04   Kriyojen depolama durumu kapısı: sıcaklık verilmezse ortam
          varsayılanına düşülmez.

Ölçüm kanıtı: ``docs/scofield/raw/OH/D26/ihracat/a1/{once,sonra}.json``
(betik ``olcum.py``; taban 7751531).
"""
import contextlib
import io
import os
import re
import tempfile

import numpy as np
import pytest


def _quiet(fn, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*args, **kwargs)


#: l_star YAYIMLAYAN geçerli gövde — P9B1-25'in ölçüldüğü gövdenin aynısı.
#: (l_star olmayan gövdede ret "türetecek L* yok"tan geliyordu; Fable-D20
#: çürütme reddinin adıyla andığı ayrım budur.)
def _base_motor(**over):
    md = {
        'chamber_diameter': 0.1,      # m
        'throat_diameter': 0.025,     # m
        'exit_diameter': 0.075,       # m
        'l_star': 1.0,                # m
        'chamber_pressure': 20.0,
        'motor_type': 'hybrid',
    }
    md.update(over)
    return md


def _assembly(md):
    from hrma.export.cad_visualization import MotorCADDesigner
    return _quiet(MotorCADDesigner().generate_3d_motor_assembly, dict(md))


# ---------------------------------------------------------------------------
# OH-Z5-12 — bant metni ⟷ kapı, ve retin andığı sayı
# ---------------------------------------------------------------------------

class TestOHZ512KamaraBandiIletisi:
    """Ürün, kabul ettiğini söylediği sayıyı reddedemez."""

    def test_bandin_ust_ucu_cizilebilir(self):
        """ÖLÇÜLDÜ (taban 7751531): ``chamber_length = 5.0`` REDDEDİLİYORDU.

        Ret iletisi tam o sayıyı bandın içinde gösteriyordu:
        *"outside the band this exporter can draw [0.02, 5] m"*. Kapı
        ``lo < v < hi`` (keskin), ileti kapalı aralıktı.
        """
        from hrma.export.cad_visualization import CHAMBER_LENGTH_MAX_M
        cad = _assembly(_base_motor(chamber_length=CHAMBER_LENGTH_MAX_M))
        assert not cad.get('error'), cad.get('error')

    def test_bandin_alt_ucu_cizilebilir(self):
        from hrma.export.cad_visualization import CHAMBER_LENGTH_MIN_M
        cad = _assembly(_base_motor(chamber_length=CHAMBER_LENGTH_MIN_M))
        assert not cad.get('error'), cad.get('error')

    def test_ilan_edilen_alt_sinir_ULASILABILIR(self):
        """İlan edilen alt sınır, birim çözümünün bandının dışında olamaz.

        ÖLÇÜLDÜ (``once.json`` -> ``OH-Z5-12.sinirlar``): sabit 0,02 m idi
        ama 0,02 ve 0,021 m girdileri DAHA ÖNCE, birim çözümünde
        ``out_of_band`` diye reddediliyordu — çünkü o katman
        ``MotorDataValidator.limits['chamber_length'] = [0,05; 20,0] m``
        uyguluyor. Yani ilan edilen sınıra ulaşmak MÜMKÜN DEĞİLDİ.
        """
        from hrma.export.cad_visualization import CHAMBER_LENGTH_MIN_M
        from hrma.validation.motor_validation import MotorDataValidator
        band = MotorDataValidator().limits['chamber_length']
        assert CHAMBER_LENGTH_MIN_M >= float(band['min']), (
            f'ihracat alt sınırı {CHAMBER_LENGTH_MIN_M} m, doğrulayıcının '
            f"bandı [{band['min']}, {band['max']}] m — ilan ulaşılamaz")

    def test_bant_disi_boy_hala_reddedilir(self):
        """Bant kapandı diye kapı gevşemedi."""
        from hrma.export.cad_visualization import CHAMBER_LENGTH_MAX_M
        cad = _assembly(_base_motor(
            chamber_length=CHAMBER_LENGTH_MAX_M + 0.5))
        assert cad.get('error')
        assert 'chamber_length_out_of_range' in cad['error']
        assert cad['assembly_meshes'] == []

    def test_ret_KULLANICININ_YAZDIGI_sayiyi_anar(self):
        """ÖLÇÜLDÜ (``once.json`` -> ``OH-Z5-12.birim_sezgisi``).

        ``chamber_length = 5.5`` + ``length_units = 'mm'`` girdisinde ret
        *"chamber length 0.0055 m is outside the band"* diyordu; kullanıcının
        yazdığı **5.5** iletide HİÇ geçmiyordu, dolayısıyla hangi sayıyı
        düzelteceği okunamıyordu.
        """
        cad = _assembly(_base_motor(chamber_length=5.5, length_units='mm'))
        hata = cad.get('error') or ''
        assert 'chamber_length_out_of_range' in hata, hata
        assert '5.5' in hata, hata
        # Çevrilen sayı da kaybolmaz: kullanıcı çevrimi görebilmeli.
        assert '0.0055' in hata, hata

    def test_ilan_edilen_bant_kapinin_KENDISI_dir(self):
        """Metindeki aralık, kapının uçlarıyla aynı sayıları yazmalı."""
        from hrma.export.cad_visualization import (CHAMBER_LENGTH_MAX_M,
                                                   CHAMBER_LENGTH_MIN_M)
        cad = _assembly(_base_motor(chamber_length=CHAMBER_LENGTH_MAX_M + 0.5))
        hata = cad['error']
        assert f'[{CHAMBER_LENGTH_MIN_M:g}, {CHAMBER_LENGTH_MAX_M:g}]' in hata
        assert 'included' in hata, hata


# ---------------------------------------------------------------------------
# P9B1-25 — yayımlanmış ama çizilemez boy
# ---------------------------------------------------------------------------

#: ``chamber_length`` alanı YAYIMLANMIŞ ama çizilebilir bir boy değil.
CIZILEMEZ_BOYLAR = [
    ('negatif', -0.5),
    ('negatif_kucuk', -0.25),
    ('sifir', 0.0),
    ('nan', float('nan')),
    ('sonsuz', float('inf')),
    ('metin', 'abc'),
]


class TestP9B125CizilemezBoyAdiylaReddedilir:
    """Reddedilen girdi ile girdisizlik AYNI çıktıyı veremez."""

    @pytest.mark.parametrize('etiket,boy', CIZILEMEZ_BOYLAR,
                             ids=[c[0] for c in CIZILEMEZ_BOYLAR])
    def test_cizilemez_boy_reddedilir(self, etiket, boy):
        """ÖLÇÜLDÜ (taban 7751531, ``once.json`` -> ``P9B1-25``).

        l_star = 1,0 m yayımlayan gövdede -0,5 / -0,25 / 0,0 / NaN / 'abc'
        ve "alan hiç yok" ALTISI DA hatasız, BİT-AYNI katıyı çizdi
        (toplam boy 229,3818 mm, max çap 109,0 mm, künye "derived from the
        characteristic length"). Kullanıcının girdisi sessizce atılıyordu.
        """
        cad = _assembly(_base_motor(chamber_length=boy))
        assert cad.get('error'), (
            f'{etiket}: {boy!r} kamara boyu sessizce kabul edildi')
        assert 'chamber_length_published_but_not_drawable' in cad['error']
        assert cad['assembly_meshes'] == []

    @pytest.mark.parametrize('etiket,boy', CIZILEMEZ_BOYLAR,
                             ids=[c[0] for c in CIZILEMEZ_BOYLAR])
    def test_ret_iletisi_girdiyi_adiyla_yazar(self, etiket, boy):
        hata = _assembly(_base_motor(chamber_length=boy))['error']
        assert repr(boy) in hata, (etiket, hata)

    def test_girdisizlik_hala_L_yildizdan_turetir(self):
        """Kapı yalnız YAYIMLANMIŞ ama kullanılamaz değeri reddeder."""
        cad = _assembly(_base_motor())
        assert not cad.get('error'), cad.get('error')
        kaynak = cad['performance_summary']['geometry_summary'][
            'chamber_length_source']
        assert 'L*' in kaynak

    def test_acik_None_girdisizlik_sayilir(self):
        """Çözücüler alanı ``None`` ile boş bırakır; bu bir GİRDİ değildir."""
        cad = _assembly(_base_motor(chamber_length=None))
        assert not cad.get('error'), cad.get('error')

    def test_reddedilen_girdi_ile_girdisizlik_AYIRT_EDILIR(self):
        """Kusurun imzası: altı yol da aynı 229,3818 mm'yi çiziyordu."""
        yok = _assembly(_base_motor())
        neg = _assembly(_base_motor(chamber_length=-0.5))
        assert not yok.get('error') and neg.get('error')
        assert neg['assembly_meshes'] == [] and yok['assembly_meshes']


# ---------------------------------------------------------------------------
# P15B2-06 — hrma/data literalleri (tek kaynak)
# ---------------------------------------------------------------------------

#: Merkezî tanımı ``hrma/constants.py``de olan sabitlerin literal desenleri.
MERKEZI_SABIT_DESENLERI = {
    'R_kmol (R_UNIVERSAL)': r'(?<![\w.])8314(?:\.\d+)?(?![\w.])',
    'R_mol (R_MOLAR / R_STAR_ICAO)': r'(?<![\w.])8\.314\d*(?![\w.])',
    'g_0 (G_0)': r'(?<![\w.])9\.8(?:0665|1)(?![\w.])',
    'P deniz seviyesi (P_SEA_LEVEL_PA)': r'(?<![\w.])101325(?:\.0+)?(?![\w.])',
    'Stefan-Boltzmann (STEFAN_BOLTZMANN)': r'(?<![\w.])5\.670\d*e-0?8(?![\w.])',
}


def _hrma_data_dizini():
    import hrma.data
    return os.path.dirname(os.path.abspath(hrma.data.__file__))


class TestP15B206MerkeziSabitLiterali:
    """Aynı fiziksel sabit ``hrma/data`` altında ikinci kez yazılmaz."""

    def test_hrma_data_altinda_literal_yok(self):
        """ÖLÇÜLDÜ (taban 7751531, ``once.json`` -> ``P15B2-06``).

        R / g_0 / Stefan-Boltzmann ayakları fix aşamasında kapanmıştı ama
        aynı sınıftan BEŞ ``101325`` literali duruyordu:
        ``chemical_database.py`` 618 ve 635, ``open_source_propellant_api.py``
        548, 555 ve 742.
        """
        bulgular = []
        kok = _hrma_data_dizini()
        for ad in sorted(os.listdir(kok)):
            if not ad.endswith('.py'):
                continue
            yol = os.path.join(kok, ad)
            with open(yol, encoding='utf-8') as fh:
                for i, satir in enumerate(fh.read().splitlines(), 1):
                    kod = satir.split('#', 1)[0]
                    for sabit, desen in MERKEZI_SABIT_DESENLERI.items():
                        if re.search(desen, kod):
                            bulgular.append(f'{ad}:{i} {sabit} -> '
                                            f'{kod.strip()[:80]}')
        assert not bulgular, (
            'hrma/constants.py\'de tanımlı sabit hrma/data altında yeniden '
            'yazılmış:\n  ' + '\n  '.join(bulgular))

    def test_P_SEA_LEVEL_PA_ISA_tablosundan_TURETILIR(self):
        """Merkezî sabit de ikinci bir literal olamaz."""
        from hrma.constants import ISA_LAYERS, P_SEA_LEVEL_PA
        assert P_SEA_LEVEL_PA == ISA_LAYERS[0][3]

    def test_tuketiciler_sabiti_ITHAL_eder(self):
        import hrma.data.chemical_database as cdb
        import hrma.data.open_source_propellant_api as osp
        from hrma.constants import P_SEA_LEVEL_PA
        assert cdb.P_SEA_LEVEL_PA is P_SEA_LEVEL_PA
        assert osp.P_SEA_LEVEL_PA is P_SEA_LEVEL_PA


# ---------------------------------------------------------------------------
# P15B4-01 — imalat paketinin TEK eksen sözleşmesi
# ---------------------------------------------------------------------------

class TestP15B401EksenSozlesmesi:
    """Aynı paketteki STEP ve STL 90° dönük olamaz."""

    def test_sozlesme_TEK_yerde_yazili(self):
        from hrma.export import motor_geometry, step_export
        assert step_export.STEP_AXIS_NOTE is motor_geometry.EXPORT_AXIS_NOTE
        assert motor_geometry.EXPORT_AXIS == 'X'
        assert motor_geometry.MESH_BUILD_AXIS == 'Z'

    def test_cad_sozlugu_ekseni_ADIYLA_yayimlar(self):
        """ÖLÇÜLDÜ: sözlükte 'x-axis' / 'z-up' / 'orientation' sayacı 0'dı."""
        cad = _assembly(_base_motor(chamber_length=0.3))
        assert not cad.get('error'), cad.get('error')
        blok = cad.get('axis_convention')
        assert isinstance(blok, dict), 'eksen künyesi yok'
        assert blok['export_axis'] == 'X'
        assert blok['mesh_build_axis'] == 'Z'
        assert 'STEP' in blok['note'] and 'STL' in blok['note']

    def test_yazilan_STL_paket_ekseninde(self):
        """Dosyaya yazılan kopya +X'e çevrilir; bellekteki mesh +Z kalır.

        ÖLÇÜLDÜ (``once.json`` -> ``P15B4-01``, üç motorun gerçek çözücü
        sonuçlarıyla): 5 parçanın 5'inde STEP ve STL zarfları birebir aynı
        sayıları TERS SIRADA taşıyordu (katı chamber STEP
        612,168/104,800/104,800 <-> STL 104,800/104,800/612,168).
        """
        trimesh = pytest.importorskip('trimesh')
        from hrma.export.cad_visualization import MotorCADDesigner
        cad = _assembly(_base_motor(chamber_length=0.3))
        assert not cad.get('error'), cad.get('error')

        # Bellekteki mesh: eksen +Z (görüntüleyici / kütle / zarf ölçümü)
        bellek = dict(cad['assembly_meshes'])['Chamber']
        v = np.asarray(bellek.vertices)
        bellek_zarf = v.max(axis=0) - v.min(axis=0)
        assert bellek_zarf[2] == pytest.approx(max(bellek_zarf)), (
            f'bellekteki mesh +Z değil: {bellek_zarf}')

        # Dosyaya yazılan kopya: eksen +X (STEP ve DXF ile aynı)
        out = tempfile.mkdtemp(prefix='d26-ih-eksen-')
        _quiet(MotorCADDesigner().export_stl_files, cad['assembly_meshes'],
               output_dir=out)
        mesh = trimesh.load(os.path.join(out, 'chamber.stl'))
        dosya_zarf = np.asarray(mesh.extents)
        assert dosya_zarf[0] == pytest.approx(max(dosya_zarf)), (
            f'yazılan STL +X değil: {dosya_zarf}')
        # Aynı katı: bileşenler yalnız YER DEĞİŞTİRDİ, büyümedi/küçülmedi.
        assert sorted(dosya_zarf) == pytest.approx(
            sorted(bellek_zarf * 1000.0), rel=1e-9)


# ---------------------------------------------------------------------------
# BEKÇİ BORCU (P13B4-10 dağıtımı) — dokunduğum dosyaların kapalı kalemleri
# ---------------------------------------------------------------------------

class TestBekciBorcuP9B102ZarfCapiOLCULUR:
    """P9B1-02 (kapalı, doğrudan bekçisi yoktu): zarf çapı ÖLÇÜLÜR.

    Kusur: sıvıda bildirilen zarf çapı 71,53 mm iken aynı koşuda üretilen
    katının gerçek zarfı 223,71 mm idi — bildirilen sayı bir FORMÜLDEN
    geliyordu, çizilen katıdan değil.
    """

    def test_max_diameter_katilardan_olculur(self):
        cad = _assembly(_base_motor(chamber_length=0.3))
        gs = cad['performance_summary']['geometry_summary']
        from hrma.export.cad_visualization import _measured_envelope_diameter_mm
        olculen, _kunye = _measured_envelope_diameter_mm(
            cad['assembly_meshes'])
        assert olculen is not None
        assert gs['max_diameter'] == pytest.approx(olculen, rel=1e-9), (
            f"yayımlanan {gs['max_diameter']} mm, katılardan ölçülen "
            f'{olculen} mm')

    def test_formul_tahmini_AYRI_alanda_durur(self):
        cad = _assembly(_base_motor(chamber_length=0.3))
        gs = cad['performance_summary']['geometry_summary']
        assert 'max_diameter_basis' in gs
        assert 'MEASURED' in gs['max_diameter_basis'].upper()


class TestBekciBorcuP9B404KriyojenDepolamaDurumu:
    """P9B4-04 (kapalı, doğrudan bekçisi yoktu): kriyojen ortam sıcaklığına
    düşürülmez.

    Kusur: depolama-durumu kapısı doğruydu ama tüketicinin
    ``temperature = 298.15`` varsayılanı kapıyı hiç çalıştırmıyordu — LOX
    298 K'de sorgulanıyordu.
    """

    def test_kriyojenlerin_depolama_durumu_ortam_degil(self):
        from hrma.data.open_source_propellant_api import (
            OpenSourcePropellantAPI)
        durumlar = OpenSourcePropellantAPI.DEFAULT_STORAGE_STATE
        for akiskan in ('Oxygen', 'Hydrogen', 'Methane', 'Nitrogen'):
            durum = durumlar[akiskan]
            assert durum['mode'] == 'saturated_liquid', akiskan
            assert durum['T'] < 200.0, (
                f'{akiskan} depolama sıcaklığı {durum["T"]} K — kriyojen '
                'ortam sıcaklığında saklanmaz')

    def test_sicaklik_verilmezse_depolama_durumu_kullanilir(self):
        """Varsayılan ``None``dır; ortam sabiti kapıyı atlayamaz."""
        import inspect

        from hrma.data.open_source_propellant_api import (
            OpenSourcePropellantAPI)
        imza = inspect.signature(
            OpenSourcePropellantAPI.get_coolprop_properties)
        assert imza.parameters['temperature'].default is None, (
            'sıcaklık varsayılanı sabit bir sayı — depolama-durumu kapısı '
            'hiç çalışmaz (P9B4-04)')


class TestBekciBorcuP9B403KategoriSabitiTABLOYUEZEMEZ:
    """P9B4-03 (kapalı, doğrudan bekçisi yoktu): kategori sabiti yayımlanmaz.

    Kusur: ``get_propellant_for_ui`` her UI alanını
    ``props.get(<ham anahtar>, <KATEGORİ SAYISI>)`` deseniyle dolduruyordu.
    Ham veri yoksa yayımlanan sayı akışkanın DEĞİL kategorinin sayısıydı
    (hybrid_fuel 920, liquid_fuel 800, solid_propellant 1800, oxidizer 1200)
    ve ``{**local_props, **api_props}`` birleşiminde MERKEZÎ TABLOYU
    EZİYORDU — N₂O₄ için depo 1443 bilirken uç 1200 yayımlıyordu.

    Kapı ``hrma/app.py::_strip_category_defaults``tadır: bir alanı besleyen
    ham anahtar ``get_comprehensive_properties`` çıktısında yoksa o sayı
    kategori varsayılanıdır ve yayından DÜŞÜRÜLÜR (ve düşenler
    ``category_defaults_suppressed`` ile adıyla bildirilir).
    """

    #: Veri katmanının kategori dalları — sayı DEĞİL, deseni sabitler.
    KATEGORI_SABITLERI = {
        'hybrid_fuel': 920,
        'liquid_fuel': 800,
        'solid_propellant': 1800,
    }

    def test_veri_katmani_kategori_sabitini_URETIYOR(self):
        """Bekçinin ölçtüğü kusur BUGÜN de üretiliyor (totoloji değil).

        Kapı app katmanındadır; veri katmanı hâlâ kategori sayısını
        döndürür. Bu iddia düşerse aşağıdaki kapı iddiası boşa döner.
        """
        from hrma.data.open_source_propellant_api import (
            OpenSourcePropellantAPI)
        api = OpenSourcePropellantAPI()
        ui = _quiet(api.get_propellant_for_ui, 'liquid_fuel', 'rp1')
        assert not ui.get('error'), ui.get('error')
        assert ui['density'] == self.KATEGORI_SABITLERI['liquid_fuel'], (
            f"liquid_fuel/rp1 yoğunluğu {ui['density']} — kategori sabiti "
            'deseni değişmiş, bekçi güncellenmeli')
        ham = _quiet(api.get_comprehensive_properties, 'rp1')
        assert 'density' not in ham and 'density_kg_m3' not in ham, (
            'ham veride yoğunluk var — sayı artık kategoriden gelmiyor')

    def test_kapi_kanitsiz_alani_DUSURUR(self):
        """Ham anahtarı olmayan alan uca çıkmaz."""
        from hrma.app import _strip_category_defaults
        temiz, dusenler = _quiet(
            _strip_category_defaults, 'rp1',
            {'density': self.KATEGORI_SABITLERI['liquid_fuel'],
             'boiling_point': 300})
        assert 'density' not in temiz, (
            f'kategori yoğunluğu yayımdan düşmedi: {temiz}')
        assert 'density' in dusenler

    def test_kapi_GERCEK_kaynakli_alani_KORUR(self):
        """Kapı kör değildir: ham anahtarı olan alan yerinde kalır.

        ``apcp`` ham künyesinde ``molecular_weight`` PubChem'den gelir;
        o alan düşürülürse kapı gerçek veriyi de siliyor demektir.
        """
        from hrma.app import _strip_category_defaults
        from hrma.data.open_source_propellant_api import (
            OpenSourcePropellantAPI)
        ham = _quiet(OpenSourcePropellantAPI().get_comprehensive_properties,
                     'apcp')
        if 'molecular_weight' not in ham:
            pytest.skip('apcp ham künyesinde molecular_weight yok '
                        '(çevrimdışı kayıt farklı)')
        temiz, dusenler = _quiet(
            _strip_category_defaults, 'apcp',
            {'density': self.KATEGORI_SABITLERI['solid_propellant'],
             'molecular_weight': ham['molecular_weight']})
        assert 'molecular_weight' in temiz, (
            'gerçek kaynaklı alan da düşürüldü — kapı kör')
        assert dusenler == ['density']


class TestBekciBorcuP9B410YanmaSicakligindaCp:
    """P9B4-10 (kapalı, doğrudan bekçisi yoktu): geçerlilik aralığı DIŞINDA
    sayı yayımlanmaz.

    Kusur: ``/api/chemical-species`` yanma sıcaklığında termodinamik olarak
    imkânsız değerler basıyordu — CO için c_p = −314,85 J/(mol·K), O₂ için
    704,74 (JANAF 3000 K: 37,79). Elde TEK 7-katsayılı düşük-sıcaklık NASA
    seti var; polinom kendi aralığının dışında değerlendiriliyordu.

    Var olan bekçi (``test_chemical_db_no_write.py``) yalnız ILIMAN
    sıcaklıkta (500 / 1000 K) sondalıyordu; kusur 2000 K'nin ÜSTÜNDEDİR.
    """

    #: Yanma bölgesi — kusurun ölçüldüğü sıcaklıklar [K].
    YANMA_SICAKLIKLARI = (2000.0, 3000.0, 3600.0)

    @pytest.mark.parametrize('tur', ['CO', 'O2', 'H2O', 'CO2', 'N2'])
    def test_yanma_sicakliginda_sayi_YAYIMLANMAZ(self, tur):
        from hrma.data.chemical_database import ChemicalDatabase
        db = ChemicalDatabase()
        if db.get_species(tur) is None:
            pytest.skip(f'{tur} bu katalogda yok')
        for T in self.YANMA_SICAKLIKLARI:
            assert db.calculate_cp(tur, T) is None, (
                f'{tur} @ {T} K: katsayı setinin geçerlilik aralığı dışında '
                'c_p yayımlandı (kusurun imzası CO @3000 K = -314,85)')
            assert db.calculate_enthalpy(tur, T) is None, (
                f'{tur} @ {T} K: aynı katsayılar integre edilip entalpi '
                'yayımlandı')

    def test_gecerlilik_araliginda_sayi_HALA_gelir(self):
        """Kapı gevşek değil ama kör de değil: aralık içinde sayı var."""
        from hrma.data.chemical_database import ChemicalDatabase
        db = ChemicalDatabase()
        cp = db.calculate_cp('CO', 300.0)
        assert cp is not None and 25.0 < cp < 35.0, (
            f'CO @300 K c_p = {cp} — JANAF 29,14 J/(mol·K) beklenir')

    def test_gecerlilik_araligi_ADIYLA_yayimlanir(self):
        """Tüketici, sayının neden gelmediğini okuyabilmeli."""
        from hrma.data.chemical_database import ChemicalDatabase
        db = ChemicalDatabase()
        durum = db.species_data_status('CO')
        band = durum['coefficient_validity_range_K']
        assert band, 'geçerlilik aralığı yayımlanmıyor'
        assert band[1] <= min(self.YANMA_SICAKLIKLARI), (
            f'ilan edilen aralık {band} yanma bölgesini kapsıyor ama '
            'karşılığı olan katsayı seti depoda yok')
        assert durum['declared_temperature_ranges']


class TestP15B206TabloOkumasiAracaGORUNUR:
    """Merkezî sabit envanteri aracı TABLODAN OKUMAYI da görmeli.

    ÖH D26 / defter P15B2-06. ``P_SEA_LEVEL_PA`` tek-kaynak kuralının en dar
    biçimiyle tanımlıdır: sayı ``ISA_LAYERS`` tablosunda BİR KEZ yazılıdır,
    sabit onun gözünden okunur. ``tools/sabit_envanteri.py`` böyle bir
    tanımı (``ast.Subscript``) çözemiyordu; ``ast.literal_eval`` düşüyor,
    ``_turetilmis_deger`` (ad / sayı / dört işlem) de görmüyordu — sabit
    envantere HİÇ girmiyordu, yani "merkezde tanımlı ama hiçbir bekçinin
    taramadığı" bir ad doğuyordu. Bu, P10B3-10'da türetilmiş (``BinOp``)
    sabitler için kapatılan kör bandın ikinci ayağıdır.

    ÖLÇÜLDÜ: araç genişletilmeden ``merkez_sabitleri`` çıktısında
    ``P_SEA_LEVEL_PA`` yoktu (ne ayırt edici ne belirsiz listesinde);
    genişletmeden sonra ayırt edici listede 101325,0 ile duruyor ve bu
    sayede depodaki 11 çıplak ``101325`` kullanımı adıyla görünür oldu
    (hepsi TABANDA da vardı; sahipleri
    ``tests/test_d20_altyapi_a1.py::KILITLI_ENVANTER``te yazılı).
    """

    def _arac(self):
        import importlib
        import sys
        kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        araclar = os.path.join(kok, 'tools')
        if araclar not in sys.path:
            sys.path.insert(0, araclar)
        return importlib.import_module('sabit_envanteri'), kok

    def test_arac_tablodan_okunan_sabiti_COZER(self):
        arac, kok = self._arac()
        ayirt, belirsiz = arac.merkez_sabitleri(__import__('pathlib').Path(kok))
        from hrma.constants import P_SEA_LEVEL_PA
        assert 'P_SEA_LEVEL_PA' in ayirt, (
            'tablodan okunan merkezî sabit envantere girmiyor — araç '
            'Subscript tanımına kör (ad hiçbir bekçide taranmaz)')
        assert ayirt['P_SEA_LEVEL_PA'] == pytest.approx(P_SEA_LEVEL_PA)
        assert 'P_SEA_LEVEL_PA' not in belirsiz

    def test_arac_kapsami_GENISLEDI_dar_kalmadi(self):
        """Genişletme kör noktayı kapatır, yeni kör nokta açmaz."""
        arac, kok = self._arac()
        ayirt, _ = arac.merkez_sabitleri(__import__('pathlib').Path(kok))
        # P10B3-10'da kazanılan türetme ayağı (BinOp) yerinde durmalı.
        assert 'R_MOLAR' in ayirt, 'türetilmiş sabit ayağı kayboldu'
