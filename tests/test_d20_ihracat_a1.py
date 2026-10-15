"""ÖH Dalga-20 · kulvar **ihracat** · aşama 1 — bekçiler.

Her sınıf bir defter kalemini kilitler. Kanıt (önce/sonra sayılar,
ters-mutasyon) ``docs/scofield/raw/OH/D20/ihracat/a1/`` altındadır.
"""
import json
import math

import pytest

from hrma.data.chemical_database import ChemicalDatabase
from hrma.data.external_data_fetcher import (
    OxidizerStateError, oxidizer_liquid_density, oxidizer_reference_density)
from hrma.export.cad_visualization import (
    DetailedCADGenerator, MotorCADDesigner, drawable_hole_count,
    json_safe_cad_design)


# ---------------------------------------------------------------------------
# P9B1-26 — enjektör delik sayısı kapısı (kardeş desenler AYNI hükmü verir)
# ---------------------------------------------------------------------------
#: Ölçülen taban davranışı (``once.json`` bölüm B / probe):
#:   coaxial(0)   -> ZeroDivisionError      impinging(0)   -> 0 iz
#:   coaxial(0,5) -> ZeroDivisionError      impinging(0,5) -> TypeError
#:   coaxial(-3)  -> ValueError (NaN->int)  impinging(-3)  -> 0 iz
CIZILEMEZ_DELIK_SAYILARI = (0, 0.5, -3, -1, float('nan'), float('inf'),
                            None, 'çok')
CIZILEBILIR_DELIK_SAYILARI = (1, 2, 3, 4, 12, 4.0)


class TestP9B126EnjektorDelikKapisi:
    def test_cizilemez_sayilar_hicbir_desende_COKMEZ(self):
        g = DetailedCADGenerator()
        for hc in CIZILEMEZ_DELIK_SAYILARI:
            for ad in ('_create_coaxial_injector_holes',
                       '_create_impinging_injector_holes'):
                izler = getattr(g, ad)(0.1, hc)
                assert izler == [], (
                    f'{ad}({hc!r}) çizilemez sayıda desen üretti: {izler!r}')

    def test_iki_kardes_desen_AYNI_kumeyi_reddeder(self):
        """Asıl kusur ÇÖKME değil, kardeşlerin FARKLI hüküm vermesiydi."""
        g = DetailedCADGenerator()
        red_co, red_imp = set(), set()
        for hc in CIZILEMEZ_DELIK_SAYILARI + CIZILEBILIR_DELIK_SAYILARI:
            for ad, kume in (('_create_coaxial_injector_holes', red_co),
                             ('_create_impinging_injector_holes', red_imp)):
                try:
                    bos = not getattr(g, ad)(0.1, hc)
                except Exception as exc:      # pragma: no cover - kusur yolu
                    pytest.fail(f'{ad}({hc!r}) yükseltti: {exc!r}')
                if bos:
                    kume.add(repr(hc))
        assert red_co == red_imp, (
            f'kardeş desenler ayrışıyor: yalnız coaxial {red_co - red_imp}, '
            f'yalnız impinging {red_imp - red_co}')

    def test_gercek_delik_sayilari_AYNEN_cizilir(self):
        """Kapı daraltmadı: çizilebilir sayılarda iz sayısı bit-aynı."""
        g = DetailedCADGenerator()
        assert len(g._create_coaxial_injector_holes(0.1, 1)) == 5
        assert len(g._create_coaxial_injector_holes(0.1, 2)) == 10
        assert len(g._create_coaxial_injector_holes(0.1, 3)) == 15
        assert len(g._create_coaxial_injector_holes(0.1, 4)) == 20
        assert len(g._create_impinging_injector_holes(0.1, 3)) == 3
        assert len(g._create_impinging_injector_holes(0.1, 4)) == 4

    def test_kapi_TEK_KAYNAK(self):
        """Hüküm tek fonksiyondadır; kopya kalsaydı bu test kırmızı olurdu."""
        assert drawable_hole_count(4.0) == 4
        assert drawable_hole_count(0) is None
        assert drawable_hole_count(0.5) is None
        assert drawable_hole_count(-3) is None
        assert drawable_hole_count(True) is None
        assert drawable_hole_count(float('nan')) is None


# ---------------------------------------------------------------------------
# OH-D17-11 — NASA-7 katsayı setinin geçerlilik aralığı
# ---------------------------------------------------------------------------
#: JANAF referansı (J/mol/K). Kusur bu noktalarda ölçüldü.
JANAF_N2 = {300.0: 29.12, 800.0: 31.43, 1500.0: 34.852, 2000.0: 35.971}


class TestOHD1711SicaklikAraligiKapisi:
    def setup_method(self):
        self.db = ChemicalDatabase()

    def test_aralik_disinda_SAYI_YAYIMLANMAZ(self):
        """N₂ 1500 K'de −%24,7, 2000 K'de NEGATİF, 3000 K'de −614 idi."""
        for T in (1500.0, 2000.0, 3000.0):
            assert self.db.calculate_cp('N2', T) is None, T
            assert self.db.calculate_enthalpy('N2', T) is None, T
            assert self.db.calculate_entropy('N2', T) is None, T

    def test_hicbir_turde_NEGATIF_cp_yayimlanmaz(self):
        """Isı sığası negatif olamaz — bu bir tutarlılık şartıdır."""
        kotu = {}
        for ad in self.db.get_all_species_names():
            for T in (200.0, 300.0, 500.0, 800.0, 1000.0, 1500.0, 2000.0,
                      3000.0, 6000.0):
                cp = self.db.calculate_cp(ad, T)
                if cp is not None and cp <= 0.0:
                    kotu[(ad, T)] = cp
        assert not kotu, f'negatif/sıfır cp yayımlandı: {kotu}'

    def test_aralik_icinde_sayilar_BIT_AYNI(self):
        """Kapı geçerli bölgeye DOKUNMADI (JANAF %1 bandı)."""
        for T, ref in JANAF_N2.items():
            cp = self.db.calculate_cp('N2', T)
            band = self.db.coefficient_validity_range(
                self.db.get_species('N2'))
            if band[0] <= T <= band[1]:
                assert cp is not None, T
                assert abs(100.0 * (cp - ref) / ref) < 1.0, (T, cp, ref)
            else:
                assert cp is None, (T, cp)

    def test_beyan_ile_veri_ARTIK_AYNI_seyi_soyluyor(self):
        """``temperature_ranges`` iki aralık beyan ediyor, katsayı seti bir."""
        durum = self.db.species_data_status('N2')
        assert durum['declared_temperature_ranges'] == [[200, 1000],
                                                        [1000, 6000]]
        assert durum['coefficient_validity_range_K'] == [200.0, 1000.0]
        sp = self.db.get_species('N2')
        assert len(sp.cp_coefficients) == 7, (
            'tek 7-katsayılı set varsayımı bozuldu; kapı gözden geçirilmeli')

    def test_her_turde_beyanin_UST_SINIRI_asilmiyor(self):
        for ad in self.db.get_all_species_names():
            sp = self.db.get_species(ad)
            band = self.db.coefficient_validity_range(sp)
            if band is None:
                continue
            assert self.db.calculate_cp(ad, band[1] + 1.0) is None, ad
            assert self.db.calculate_cp(ad, band[0] - 1.0) is None, ad


# ---------------------------------------------------------------------------
# OH-D19-02 — sıvı bandı dışında yoğunluk yayımlanmaz
# ---------------------------------------------------------------------------
BANT_DISI_VAKALAR = (('lox', 293.15), ('lox', 298.15), ('n2o4', 400.0),
                     ('n2o4', 298.15))
BANT_ICI_VAKALAR = (('lox', 90.19), ('lox', 100.0), ('n2o4', 293.15),
                    ('n2o', 293.15), ('h2o2', 293.15))


class TestOHD1902BantDisiYogunluk:
    @pytest.mark.parametrize('ox,T', BANT_DISI_VAKALAR)
    def test_skaler_kanal_bant_disinda_SAYI_VERMEZ(self, ox, T):
        from hrma.app import get_oxidizer_density

        assert oxidizer_reference_density(ox, T)['state_reason'] == \
            'outside_liquid_band', 'vaka artık bant dışı değil'
        with pytest.raises(OxidizerStateError):
            get_oxidizer_density(ox, T)
        with pytest.raises(OxidizerStateError):
            oxidizer_liquid_density(ox, T)

    @pytest.mark.parametrize('ox,T', BANT_ICI_VAKALAR)
    def test_bant_ici_degerler_BIT_AYNI(self, ox, T):
        from hrma.app import get_oxidizer_density

        kunye = oxidizer_reference_density(ox, T)
        assert kunye['state_reason'] != 'outside_liquid_band'
        assert get_oxidizer_density(ox, T) == kunye['density']

    def test_kunye_ile_skaler_kanal_CELISMEZ(self):
        """Asıl kusur buydu: künye 'geçersiz' derken skaler sayı veriyordu."""
        from hrma.app import get_oxidizer_density

        for ox in ('n2o', 'lox', 'h2o2', 'n2o4'):
            for T in (90.19, 200.0, 293.15, 298.15, 400.0):
                try:
                    kunye = oxidizer_reference_density(ox, T)
                except OxidizerStateError:
                    # Tek kaynağın KENDİ fail-closed dalı (N₂O doyma bandı);
                    # skaler kanal da aynı istisnayı taşımalı.
                    with pytest.raises(OxidizerStateError):
                        get_oxidizer_density(ox, T)
                    continue
                try:
                    get_oxidizer_density(ox, T)
                    sayi_var = True
                except OxidizerStateError:
                    sayi_var = False
                assert sayi_var == (
                    kunye['state_reason'] != 'outside_liquid_band'), (
                    f'{ox} @{T} K: künye {kunye["state_reason"]!r} derken '
                    f'skaler kanal {"sayı verdi" if sayi_var else "reddetti"}')

    def test_sozluk_sozlesmesi_KORUNDU(self):
        """Altı modül + dört bekçi bu anahtarları okuyor — hiçbiri düşmedi."""
        veri = oxidizer_reference_density('lox', 293.15)
        for anahtar in ('density', 'source', 'basis', 'reference_T_K',
                        'state_applied', 'state_reason', 'note'):
            assert anahtar in veri, anahtar
        assert veri['density'] == 1141.0


# ---------------------------------------------------------------------------
# P9B1-31 — cad_design bloğu repr() METNİ taşımaz
# ---------------------------------------------------------------------------
CAD_GOVDESI = {'chamber_diameter': 0.1, 'chamber_length': 0.25,
               'throat_diameter': 0.05, 'exit_diameter': 0.109}


class TestP9B131CadDesignSemasi:
    def test_yanit_kopyasi_trimesh_repr_TASIMAZ(self):
        cad = MotorCADDesigner().generate_3d_motor_assembly(dict(CAD_GOVDESI))
        assert cad.get('assembly_meshes'), 'ölçüm gövdesi ağ üretmiyor'
        güvenli = json_safe_cad_design(cad)
        gövde = json.dumps(güvenli, default=str)
        assert '<trimesh.' not in gövde, 'repr() metni hâlâ yanıtta'
        assert 'object at 0x' not in gövde
        assert 'assembly_meshes' not in güvenli

    def test_kunye_UYDURMA_DEGIL_olculmus(self):
        cad = MotorCADDesigner().generate_3d_motor_assembly(dict(CAD_GOVDESI))
        özet = json_safe_cad_design(cad)['assembly_mesh_summary']
        assert özet, 'ağ künyesi boş'
        for kayıt, (ad, mesh) in zip(özet, cad['assembly_meshes']):
            assert kayıt['name'] == str(ad)
            assert kayıt['vertex_count'] == len(mesh.vertices)
            assert kayıt['face_count'] == len(mesh.faces)
            assert kayıt['vertex_count'] > 0 and kayıt['face_count'] > 0

    def test_surec_ici_tuketici_AGI_KAYBETMEZ(self):
        """``export_stl_files`` sözlüğün KENDİSİNİ okur — kopya dönmeli."""
        cad = MotorCADDesigner().generate_3d_motor_assembly(dict(CAD_GOVDESI))
        n = len(cad['assembly_meshes'])
        json_safe_cad_design(cad)
        assert len(cad['assembly_meshes']) == n, 'kaynak sözlük bozuldu'

    def test_govde_JSON_serilesir(self):
        """ÖH D24 / OH-D23-01: gövde İDDİASIZDI.

        ``json.dumps`` tek başına ne gövdenin BİR ŞEY taşıdığını ne
        gidiş-dönüş kaybını ne de NaN/Infinity sızıntısını sınar — boş
        sözlük de sorunsuz serileşir.
        """
        cad = MotorCADDesigner().generate_3d_motor_assembly(dict(CAD_GOVDESI))
        guvenli = json_safe_cad_design(cad)
        metin = json.dumps(guvenli, allow_nan=False)   # default=str OLMADAN
        geri = json.loads(metin)
        assert geri == guvenli, 'CAD gövdesi gidiş-dönüşte değişti'
        assert isinstance(guvenli, dict) and guvenli, (
            'CAD gövdesi boş — "serileşiyor" iddiası vakumluk')


# ---------------------------------------------------------------------------
# P9B5-07 (2. yarı) — sunulan seçenek sunulabilen seçenektir
# ---------------------------------------------------------------------------
#: Sunucunun HİÇBİR ucunun çözemediği, bu yüzden şablonda kilitlenen adlar.
KILITLI_OKSITLEYICILER = ('air', 'custom')


class TestP9B507SablonSecenekKilidi:
    def _select_secenekleri(self, sid):
        import os
        import re

        from hrma import __file__ as paket
        yol = os.path.join(os.path.dirname(paket), 'templates',
                           'advanced.html')
        metin = open(yol, encoding='utf-8').read()
        m = re.search(r'<select id="%s"[^>]*>(.*?)</select>' % sid, metin,
                      re.S)
        assert m, f'{sid} select bulunamadı'
        etkin, kapalı = [], []
        for om in re.finditer(r'<option\b([^>]*)>', m.group(1)):
            attrs = om.group(1)
            vm = re.search(r'value="([^"]*)"', attrs)
            v = vm.group(1) if vm else ''
            (kapalı if 'disabled' in attrs else etkin).append(v)
        return etkin, kapalı

    def test_cozulemeyen_oksitleyiciler_ETKIN_DEGIL(self):
        etkin, kapalı = self._select_secenekleri('oxidizer_type')
        for ad in KILITLI_OKSITLEYICILER:
            assert ad not in etkin, (
                f"oxidizer_type='{ad}' hâlâ etkin ama sunucu çözmüyor")
            assert ad in kapalı, ad

    def test_etkin_oksitleyicilerin_HEPSI_cozulur(self):
        """Kilit fazla da olamaz: etkin kalan her ad gerçekten çözülmeli.

        ÇEVRİLDİ (ÖH D25 · OH-D24-04): gövde İDDİASIZDI ve iddia kredisini
        KURULUM yardımcısından (``_select_secenekleri`` içindeki "select
        bulunamadı") alıyordu — testin KENDİ konusu hiç sınanmıyordu.
        Ölçülen iki delik: (i) ``etkin`` boş gelseydi döngü hiç dönmez ve
        test vakumlu yeşil kalırdı; (ii) ``ord_`` künyesiz, yoğunluğu
        ``None`` ya da 0 olan bir sözlük döndürseydi de yeşil kalırdı —
        çağrı yalnız "istisna yükseltmedi"yi ölçüyordu. Bugünkü sözleşme
        ÖLÇÜLDÜ: dönen değer sözlüktür ve ``density`` (sonlu, pozitif),
        ``source`` (boş olmayan künye), ``state_applied`` taşır; istenen
        sıcaklık uygulanmadıysa ``state_reason`` ADIYLA gerekçe verir
        (ölçülen örnek: lox 293,15 K sıvı bandının dışında).
        """
        from hrma.data.external_data_fetcher import (
            oxidizer_reference_density as ord_)

        etkin, _ = self._select_secenekleri('oxidizer_type')
        assert etkin, ('oxidizer_type seçeneklerinin hepsi kapalı görünüyor; '
                       'boş liste bu bekçiyi vakumlu yeşile çevirir')
        for ad in etkin:
            kayit = ord_(ad, 293.15)     # OxidizerStateError yükseltmemeli
            assert isinstance(kayit, dict), (
                '%s: oxidizer_reference_density sözlük döndürmedi (%r)'
                % (ad, type(kayit).__name__))
            yogunluk = kayit.get('density')
            assert isinstance(yogunluk, (int, float)) and not isinstance(
                yogunluk, bool), (
                '%s: density sayı değil (%r)' % (ad, yogunluk))
            assert math.isfinite(float(yogunluk)) and float(yogunluk) > 0.0, (
                '%s: density sonlu-pozitif değil (%r)' % (ad, yogunluk))
            assert isinstance(kayit.get('source'), str) and kayit['source'].strip(), (
                '%s: yoğunluk künyesiz yayımlanıyor (source boş)' % ad)
            assert 'state_applied' in kayit, (
                '%s: istenen sıcaklığın uygulanıp uygulanmadığı '
                'yayımlanmıyor' % ad)
            if not kayit['state_applied']:
                gerekce = kayit.get('state_reason')
                assert isinstance(gerekce, str) and gerekce.strip(), (
                    '%s: sıcaklık uygulanmadı ama gerekçe ADIYLA '
                    'yayımlanmıyor' % ad)

    def test_pla_ve_aluminum_KILITLENMEDI(self):
        """Ölçüldü: /calculate ikisini de 200 ile çözüyor (kilit gerekmez)."""
        etkin, _ = self._select_secenekleri('fuel_type')
        assert 'pla' in etkin and 'aluminum' in etkin
