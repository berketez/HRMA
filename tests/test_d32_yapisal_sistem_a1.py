"""ÖH Dalga-32 / yapisal-sistem a1 — onarım bekçileri.

Tek kalem:

  OH-FT-06 (Fable TOPLU kati-01 yeni bulgusu, düşük)
      ``end_cap_analysis`` HÜKMÜ kapak tipine göre adıyla yayımlıyordu
      (``head_safety_factor_by_type``, ``head_stress_by_type_MPa``,
      künyesi ``head_safety_factor_by_type_basis``) ama KALINLIĞI tek bir
      ``head_thickness_used_mm`` ile yayımlıyordu; o sayının hangi kapak
      tipine ait olduğunu söyleyen alan da, sayının kendi künyesi de
      YOKTU. 'used' adı "imalata giden kalınlık" diye okunuyordu; oysa
      ihraç katmanı DÜZ kapak modeller ve ``flat_head_thickness``ı alır.

      ÖLÇÜLDÜ (taban ``dd1dcddc``,
      ``docs/scofield/raw/OH/D32/yapisal-sistem/a1/once.json``):

        A) blok 17 anahtar yayımlıyor; ``tip_alani_var = false``,
           ``kunye_alani_var = false``, ``kalinlik_tip_eslemesi_var = false``
        B) /calculate_solid (Ø100 mm / 40 bar / çelik):
              head_thickness_used_mm            =  3,008744 mm (dished)
              ihraç katmanının imalat kapağı    = 15,180585 mm (FLAT)
              oran                              =  5,045490
        C) kütle bloğu: ``kutle_tip_alani_var = false`` — 2,622378 mm'lik
           (dished) kapaktan çıkan kütle, 12,646962 mm'lik düz kapağın
           kütlesi sanılabiliyordu

      Onarım SAYI DEĞİŞTİRMEZ; sözleşmeyi makine-okur yapar:
      ``head_thickness_used_type``, ``head_thickness_field_by_type``,
      ``head_thickness_used_basis`` ve kütle tarafında
      ``end_cap_thickness_used_type``.

Ölçümler: docs/scofield/raw/OH/D32/yapisal-sistem/a1/{once,sonra}.json
Ters-mutasyon: docs/scofield/raw/OH/D32/yapisal-sistem/a1/mutasyon.json
"""
import pytest

from hrma.analysis.structural_analysis import StructuralAnalyzer


#: Fable kati-01'in ölçtüğü vaka: çelik, Ø100 mm, 40 bar.
MAT = {'yield_strength': 250e6, 'poisson_ratio': 0.3, 'safety_factor': 2.0}
BASINC_PA = 4.0e6
CAP_M = 0.100


@pytest.fixture(scope='module')
def analyzer():
    return StructuralAnalyzer()


@pytest.fixture(scope='module')
def kapak_boyutlandirma(analyzer):
    return analyzer._analyze_end_caps(
        BASINC_PA, CAP_M, dict(MAT), derating=None,
        design_safety_factor=2.0, actual_thickness=None)


@pytest.fixture(scope='module')
def kapak_dogrulama(analyzer):
    return analyzer._analyze_end_caps(
        BASINC_PA, CAP_M, dict(MAT), derating=None,
        design_safety_factor=2.0, actual_thickness=0.008)


class TestOHFT06KapakKalinligiSozlesmesi:
    """``head_thickness_used_mm`` artık kimin kalınlığı olduğunu söylüyor."""

    def test_kalinlik_tipsiz_yayimlanmaz(self, kapak_boyutlandirma,
                                         kapak_dogrulama):
        """Kusurun kendisi: kalınlık var, tipi ve künyesi yok.

        ÖLÇÜLDÜ (once.json bölüm A): ``tip_alani_var = false`` ve
        ``kunye_alani_var = false``; bloğun 17 anahtarının hiçbiri
        ``head_thickness_used_mm``in hangi kapak tipine ait olduğunu
        söylemiyordu. Bu bekçi kalınlık ile kimliğinin BİRLİKTE
        yayımlanmasını sınar: biri varsa diğeri de olmalıdır.
        """
        for blok in (kapak_boyutlandirma, kapak_dogrulama):
            if 'head_thickness_used_mm' not in blok:
                continue
            for alan in ('head_thickness_used_type',
                         'head_thickness_field_by_type',
                         'head_thickness_used_basis'):
                assert alan in blok, (
                    f"end_cap_analysis 'head_thickness_used_mm' yayımlıyor "
                    f"ama '{alan}' yok — kalınlık kimliksiz çıkıyor "
                    f"(OH-FT-06); anahtarlar: {sorted(blok)}")

    def test_boyutlandirma_kipinde_tip_oneri_tipidir(self,
                                                     kapak_boyutlandirma):
        """Boyutlandırma kipinde değerlendirilen kalınlık ÖNERİLEN tipindir.

        Ve yalnız ad değil, SAYI da eşleşmelidir: tipin kendi kalınlık
        alanı ``head_thickness_used_mm`` ile birebir aynı sayıyı vermeli.
        """
        blok = kapak_boyutlandirma
        assert blok['design_mode'] == 'size'
        tip = blok['head_thickness_used_type']
        assert tip == blok['recommended_type'], (
            f"boyutlandırma kipinde head_thickness_used_type {tip!r}, "
            f"recommended_type {blok['recommended_type']!r} — "
            "değerlendirilen kalınlık önerilen tipin kalınlığıdır")
        alan = blok['head_thickness_field_by_type'][tip]
        assert blok[alan] == blok['head_thickness_used_mm'], (
            f"{alan} = {blok[alan]!r} ile head_thickness_used_mm = "
            f"{blok['head_thickness_used_mm']!r} ayrışıyor — tip eşlemesi "
            "yanlış alanı gösteriyor")

    def test_dogrulama_kipinde_tip_kullanicidir(self, kapak_dogrulama):
        """Doğrulama kipinde sayı çağıranın kapağıdır; iki boyutlandırma
        çıktısının hiçbirine eşit değildir.

        ÖLÇÜLDÜ (once.json A2): used 8,0 mm; flat 9,949874 mm;
        dished 1,605136 mm. Tüketici tipi DEĞERLERDEN çıkaramaz, alanın
        kendisi söylemek zorundadır.
        """
        blok = kapak_dogrulama
        assert blok['design_mode'] == 'verify'
        assert blok['head_thickness_used_type'] == 'user_supplied', (
            "doğrulama kipinde head_thickness_used_type 'user_supplied' "
            f"olmalı, {blok['head_thickness_used_type']!r} geldi")
        kullanilan = blok['head_thickness_used_mm']
        assert kullanilan != blok['flat_head_thickness']
        assert kullanilan != blok['dished_head_thickness']

    def test_tip_eslemesi_sarkan_ad_tasimaz(self, kapak_boyutlandirma,
                                            kapak_dogrulama):
        """Eşleme SAYI kopyalamaz, ALAN ADI taşır — ve adlar gerçek olmalı.

        Eşlemenin kendisi sözleşmedir: gösterdiği her ad bloğun içinde
        gerçekten bulunmalı (sarkan atıf yok) ve gösterdiği değer sayı
        olmalı. Ayrıca hüküm eşlemesiyle AYNI tip kümesini kapsamalıdır;
        aksi halde bir tip kalınlığını adıyla okuyamaz.
        """
        for blok in (kapak_boyutlandirma, kapak_dogrulama):
            esleme = blok['head_thickness_field_by_type']
            assert isinstance(esleme, dict) and esleme
            for tip, ad in esleme.items():
                assert ad in blok, (
                    f"head_thickness_field_by_type[{tip!r}] = {ad!r} bloğun "
                    f"anahtarı değil — sarkan alan adı")
                assert isinstance(blok[ad], float), (
                    f"{ad} sayı değil ({blok[ad]!r})")
            assert set(esleme) == set(blok['head_safety_factor_by_type']), (
                "kalınlık eşlemesi ile hüküm eşlemesi aynı tip kümesini "
                f"kapsamıyor: {sorted(esleme)} ⟷ "
                f"{sorted(blok['head_safety_factor_by_type'])}")

    def test_kunye_imalat_alanini_adiyla_gosteriyor(self,
                                                    kapak_boyutlandirma):
        """Künye 'used' adının yanıltmasını AÇIKÇA kapatmalı.

        Künye üç şeyi söylemek zorunda: (1) sayı DEĞERLENDİRME
        kalınlığıdır, imalat beyanı değildir; (2) tipi hangi alan söyler;
        (3) kendi tipini bilen tüketici kalınlığını hangi alandan okur —
        ihraç katmanının DÜZ kapak alanı ADIYLA geçmeli.
        """
        kunye = kapak_boyutlandirma['head_thickness_used_basis']
        assert isinstance(kunye, str) and kunye.strip()
        for parca in ('evaluated', 'head_thickness_used_type',
                      'head_thickness_field_by_type', 'flat_head_thickness',
                      'head_safety_factor_by_type'):
            assert parca in kunye, (
                f"head_thickness_used_basis {parca!r} demiyor — künye "
                f"sözleşmeyi taşımıyor: {kunye!r}")
        assert 'NOT' in kunye, (
            "künye sayının imalat kalınlığı OLMADIĞINI söylemiyor: "
            f"{kunye!r}")

    def test_sayilar_degismedi(self, kapak_boyutlandirma, kapak_dogrulama):
        """Onarım BEYAN onarımıdır: hiçbir yayımlanan sayı kaymadı.

        Taban ölçümü (once.json A1/A2, çelik Ø100 mm / 40 bar).
        """
        b = kapak_boyutlandirma
        assert b['flat_head_thickness'] == pytest.approx(
            9.949874371066201, rel=0, abs=0)
        assert b['dished_head_thickness'] == pytest.approx(
            1.6051364365971108, rel=0, abs=0)
        assert b['asme_ug34_flat_head_thickness'] == pytest.approx(
            9.797958971132712, rel=0, abs=0)
        assert b['head_thickness_used_mm'] == pytest.approx(
            1.6051364365971108, rel=0, abs=0)
        assert kapak_dogrulama['head_thickness_used_mm'] == pytest.approx(
            8.0, rel=0, abs=0)


class TestOHFT06KutleBlogununKapagi:
    """Kütle bloğu hangi kapağı tarttığını adıyla söylüyor."""

    @pytest.fixture(scope='class')
    def tam(self, analyzer):
        return analyzer.analyze_structure(
            {'chamber_pressure': 40.0, 'chamber_diameter': 0.100,
             'chamber_length': 0.500, 'throat_diameter': 0.030},
            material='steel_4130')

    def test_kutle_kapak_tipini_yayimliyor(self, tam):
        """ÖLÇÜLDÜ (once.json C1): ``kutle_tip_alani_var = false``.

        Kütle 2,622378 mm'lik (dished) kapaktan çıkıyordu, ihraç katmanı
        12,646962 mm'lik DÜZ kapak çiziyordu; blok hangi tasarımın
        kütlesini verdiğini söylemiyordu.
        """
        w = tam['weight_analysis']
        cap = tam['end_cap_analysis']
        assert 'end_cap_thickness_used_type' in w, (
            f"weight_analysis kapak tipini yayımlamıyor: {sorted(w)}")
        assert w['end_cap_thickness_used_type'] == \
            cap['head_thickness_used_type'], (
                "kütle bloğunun kapak tipi ile kapak bloğununki ayrışıyor: "
                f"{w['end_cap_thickness_used_type']!r} ⟷ "
                f"{cap['head_thickness_used_type']!r}")
        assert w['end_cap_thickness_used_mm'] == pytest.approx(
            cap['head_thickness_used_mm'], rel=0, abs=0)

    def test_kutle_kunyesi_tipi_ve_yonlendirmeyi_tasiyor(self, tam):
        w = tam['weight_analysis']
        kunye = w['end_caps_weight_basis']
        # P5B1-11 / Z5S bekçilerinin dayandığı çapa korunur.
        assert 'head_thickness_used_mm' in kunye
        assert 'end_cap_thickness_used_type' in kunye, (
            f"kütle künyesi tip alanını adıyla anmıyor: {kunye!r}")
        assert str(w['end_cap_thickness_used_type']) in kunye, (
            f"kütle künyesi tipin DEĞERİNİ taşımıyor: {kunye!r}")
        assert 'head_thickness_field_by_type' in kunye, (
            "kütle künyesi başka tip tartan tüketiciyi doğru alana "
            f"yönlendirmiyor: {kunye!r}")


class TestOHFT06IhracKatmaniyleCapraz:
    """Yeni eşleme GERÇEK tüketicinin okuduğu sayıyı gösteriyor mu?

    Sözleşme ancak ürün yolunda bağlanırsa sözleşmedir: ihraç katmanı
    (``_front_cap_design``) DÜZ kapak modeller; eşlemenin 'flat' girdisi
    onun imalata soktuğu sayıyı göstermek zorundadır.
    """

    @pytest.fixture(scope='class')
    def kati_yanit(self):
        from hrma.app import app
        app.config['TESTING'] = True
        istemci = app.test_client()
        r = istemci.post('/calculate_solid', json={
            'motor_name': 'OHFT06-KATI', 'propellant_type': 'apcp',
            'grain_type': 'bates', 'chamber_pressure': 40.0,
            'thrust': 5000.0, 'burn_time': 3.0,
            'chamber_diameter': 100.0, 'grain_length': 500.0,
            'core_diameter': 30.0, 'expansion_ratio': 8.0})
        assert r.status_code == 200, r.status_code
        return r.get_json()

    def test_esleme_ihracatin_aldigi_sayiyi_gosteriyor(self, kati_yanit):
        from hrma.export.cad_visualization import _front_cap_design

        cap = kati_yanit['structural_analysis']['end_cap_analysis']
        kapak = _front_cap_design(kati_yanit, wall_mm=2.4,
                                  bore_radius_mm=50.0, require_analysis=True)
        assert kapak['from_analysis'] is True
        alan = cap['head_thickness_field_by_type']['flat']
        assert kapak['thickness_mm'] == pytest.approx(cap[alan], rel=0, abs=0), (
            f"ihraç katmanı {kapak['thickness_mm']!r} mm çiziyor ama "
            f"head_thickness_field_by_type['flat'] -> {alan} = {cap[alan]!r} "
            "— eşleme imalatın okuduğu alanı göstermiyor")

    def test_used_ile_imalat_kalinligi_ayri_buyukluk(self, kati_yanit):
        """Kalemin ta kendisi: iki sayı AYRI büyüklüktür (ölçüm 5,045490x).

        Bu bekçi sayıları eşitlemeye ÇALIŞMAZ — ayrışmanın sürdüğünü ve
        bloğun bunu artık ADIYLA söylediğini sınar.
        """
        from hrma.export.cad_visualization import _front_cap_design

        cap = kati_yanit['structural_analysis']['end_cap_analysis']
        kapak = _front_cap_design(kati_yanit, wall_mm=2.4,
                                  bore_radius_mm=50.0, require_analysis=True)
        if cap['head_thickness_used_type'] == 'flat':
            pytest.skip('öneri düz kapak — iki sayı zaten aynı büyüklük')
        assert kapak['thickness_mm'] != cap['head_thickness_used_mm']
        # ...ve okuyucu farkı bloğun kendisinden çözebilmeli:
        assert cap['head_thickness_used_type'] == cap['recommended_type']
        assert 'flat_head_thickness' in cap['head_thickness_used_basis']
