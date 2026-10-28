"""ÖH D18 / kulvar kati / aşama 1 — onarımların bekçileri.

Her sınıf TEK bir kalemi kilitler ve ters mutasyonla kırmızıya döndüğü
kanıtlanmıştır (``docs/scofield/raw/OH/D18/kati/a1/mutasyon.json``).
Ölçümler ``once.json`` / ``sonra.json`` dosyalarındadır.
"""
import contextlib
import io
import json
import os
import re

import pytest
from tests.support.kanit import kanit_gerekli

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


def _motor(**kw):
    from hrma.engines.solid_rocket_engine import (
        SOLID_DEFAULT_GEOMETRY_MM, SolidRocketEngine)
    # V301/K-A (22 Eki): eski çapa A_p/A_t = 0,947'lik boğulan portlu
    # varsayılan motoru kilitliyordu (çekirdek 30 mm); örnek motorun TEK
    # tanımı okunur. Kuru kütle çapaları çekirdekten bağımsızdır (kasa
    # zinciri; ölçüldü: 30 ve 48 mm'de rel 1e-9 içinde aynı).
    p = dict(grain_type='bates', propellant_type='apcp',
             chamber_diameter=100.0, grain_length=500.0,
             core_diameter=float(SOLID_DEFAULT_GEOMETRY_MM['core_diameter']),
             chamber_pressure=40.0)
    p.update(kw)
    return SolidRocketEngine(**p)


def _oku(yol):
    with io.open(os.path.join(KOK, yol), encoding='utf-8') as fh:
        return fh.read()


@pytest.fixture(scope='module')
def client():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


UC_TABAN_D18 = dict(motor_name='D18-KATI', propellant_type='apcp',
                    grain_type='bates', chamber_pressure=40.0, thrust=5000.0,
                    burn_time=3.0, chamber_diameter=100.0, grain_length=500.0,
                    core_diameter=30.0, expansion_ratio=8.0)


# ---------------------------------------------------------------------------
# P2B3-11 — CAD grain tablosu HESAPLANMIŞ değere 'not computed' diyemez
# ---------------------------------------------------------------------------
class TestGrainTablosuHesaplananiGosteriyor:
    """ÖLÇÜLDÜ (once.json P2B3-11): arayüzün okuduğu beş anahtardan
    (type / outer_diameter / core_diameter / web_thickness /
    propellant_mass) star'da 1, wagon_wheel ve end_burner'da 3 tanesi
    grain raporunda YOKTU; ``solid.html`` fmtField eksik anahtar için
    'not computed' basıyor. Oysa üçünde de yakıt kütlesi aynı koşuda
    hesaplanmıştı (star 5,886103 / wagon 5,988566 / end_burner 7,107853 kg)
    ve yanıtın kökünde duruyordu — YANLIŞ BİR BEYANDI."""

    UI_ANAHTARLARI = ('type', 'outer_diameter', 'core_diameter',
                      'web_thickness', 'propellant_mass')

    @pytest.mark.parametrize('gt', ['bates', 'star', 'wagon_wheel',
                                    'finocyl', 'slotted', 'end_burner'])
    def test_eksik_anahtar_kalmadi_ya_da_BEYANLI(self, gt):
        e = _motor(grain_type=gt)
        rapor = _sessiz(e._analyze_grain_geometry)
        for k in self.UI_ANAHTARLARI:
            assert k in rapor, '%s: %s anahtarı hiç yok' % (gt, k)
            if rapor[k] is None:
                # Değer gerçekten yoksa NEDEN yok, adıyla yazılmalı.
                assert isinstance(rapor.get(k + '_status'), str), (
                    '%s: %s boş ama beyanı yok' % (gt, k))
                assert isinstance(rapor.get(k + '_basis'), str)

    @pytest.mark.parametrize('gt', ['bates', 'star', 'wagon_wheel',
                                    'finocyl', 'slotted', 'end_burner'])
    def test_yakit_kutlesi_KOKTEKI_sayiyla_ayni(self, gt):
        """Panelde ayrı bir sayı türetilmez: tek kaynak _propellant_volume."""
        e = _motor(grain_type=gt)
        rapor = _sessiz(e._analyze_grain_geometry)
        beklenen = float(e._propellant_volume() * e.rho_p)
        assert rapor['propellant_mass'] == pytest.approx(beklenen, rel=1e-12)

    def test_end_burner_cekirdegi_UYGULANAMAZ_diye_beyanli(self):
        """End burner'da çekirdek GERÇEKTEN yok; doğru beyan 'hesaplanmadı'
        değil 'uygulanamaz'dır ve gerekçesi fmtField ipucuna düşer."""
        rapor = _sessiz(_motor(grain_type='end_burner')._analyze_grain_geometry)
        assert rapor['core_diameter'] is None
        assert rapor['core_diameter_status'] == 'not_applicable'
        assert rapor['web_thickness_status'] == 'not_applicable'
        assert 'no central core' in rapor['core_diameter_basis']


# ---------------------------------------------------------------------------
# P2B3-13 — boğaz gövdeyi aşarsa NEGATİF yakınsak boy yayımlanmaz
# ---------------------------------------------------------------------------
class TestBogazGovdeyiAsinca:
    """ÖLÇÜLDÜ (once.json P2B3-13): motor_validation aralıklarının İÇİNDE
    kalan meşru girdilerle d_boğaz/D = 1,565 / 1,805 / 1,765 ölçüldü ve
    ``cad_design.nozzle_design.convergent_length`` −48,97 / −69,70 /
    −99,40 mm yayımlandı; toplam boy ıraksak bölümden KISA çıkıyordu ve
    hiçbir uyarı kodu bunu söylemiyordu."""

    ASIRI = dict(chamber_diameter=100.0, grain_length=3000.0,
                 core_diameter=15.0, chamber_pressure=5.0)
    NORMAL = dict(chamber_diameter=100.0, grain_length=500.0,
                  core_diameter=30.0, chamber_pressure=40.0)
    #: V301/K-A: NORMAL'in çapası (``_design_nozzle_geometry``) port
    #: kapısından geçmez ve bit-aynı kalır; ``calculate_performance`` yolu
    #: ise eski çapa A_p/A_t = 0,947'lik boğulan portlu varsayılan motoru
    #: kilitliyordu -> o yolda örnek motorun geçerli çekirdeği (48 mm).
    NORMAL_GECERLI = dict(NORMAL, core_diameter=48.0)

    def test_asiri_bogazda_sayi_YAYIMLANMIYOR_ve_gerekce_var(self):
        nz = _sessiz(_motor(**self.ASIRI)._design_nozzle_geometry)
        assert nz['throat_over_case_ratio'] > 1.0, nz['throat_over_case_ratio']
        assert nz['throat_exceeds_case'] is True
        assert nz['convergent_length'] is None, (
            'negatif/uydurma yakınsak boy hâlâ yayımlanıyor: %r'
            % nz['convergent_length'])
        assert nz['total_length'] is None
        assert nz['convergent_length_status'] == 'not_physical'
        assert 'does not exist' in nz['convergent_length_basis']

    def test_normal_geometride_davranis_DEGISMEDI(self):
        nz = _sessiz(_motor(**self.NORMAL)._design_nozzle_geometry)
        assert nz['throat_exceeds_case'] is False
        # ÖH KİTAP p1b (B11, §28-36 Ş-3): eski 59,793950180294374 geri
        # çözülmüş APCP dörtlüsündendi (boğaz c* 1598,2 ile boyutlanıyordu);
        # CEA denge dörtlüsüyle ölçülen yeni taban (boğaz −%0,40).
        # V301/T-ÇAPA-A: N-CEA-2 (katı termokimya motorun Pc'sinde NASA CEA'dan) sonrası yeniden
        # ölçüldü: 59,901521132815716 -> 59,94333101222664 mm (CEA kapalı aynı
        # motor eski sayıyı verir).
        assert nz['convergent_length'] == pytest.approx(59.94333101222664,
                                                        rel=1e-9)
        assert nz['convergent_length_status'] == 'computed'

    def test_IHRAC_yolundaki_ikinci_kopya_da_kapali(self):
        """``export/motor_geometry.py:511`` ÖNCE ``nozzle_angles.
        convergent_length_mm`` alanını okur; kapı yalnız cad_design'a
        konsaydı negatif boy STEP/STL yoluna oradan sızmaya devam ederdi.
        Bu yüzden kapı İKİ kopyada da ölçülür.

        V301/K-A (22 Eki) — TERS KAPIYA ÇEVRİLDİ: boğazı gövdeyi aşan motorda
        port boğazdan da küçüktür (A_p/A_t < 1); tasarım artık HİÇ
        yayımlanmaz (KT-23), yani ihraç yoluna ne negatif ne de başka bir
        boy ulaşabilir. Ret, boğazı tek kaynaktan taşır."""
        from hrma.engines.solid_rocket_engine import SolidDesignRejected
        e = _motor(**self.ASIRI)
        with pytest.raises(SolidDesignRejected) as exc:
            _sessiz(e.calculate_performance)
        assert exc.value.code == 'port_smaller_than_throat'
        kunye = exc.value.invalid_fields[0]
        assert kunye['throat_diameter_mm'] == pytest.approx(
            float(_sessiz(e._estimate_throat_diameter)) * 1000.0, rel=1e-9)

    def test_normal_geometride_IKINCI_kopya_da_sayi_veriyor(self):
        res = _sessiz(_motor(**self.NORMAL_GECERLI).calculate_performance)
        ang = res['nozzle_angles']
        assert ang['throat_exceeds_case'] is False
        assert ang['convergent_length_mm'] > 0
        assert ang['nozzle_length_mm'] > 0
        assert res['design_summary']['key_dimensions']['total_length_mm'] > 0


# ---------------------------------------------------------------------------
# P2B3-14 — safety_margin_k YALNIZ kasa marjıdır ve bunu söyler
# ---------------------------------------------------------------------------
class TestIsilMarjKapsamiYaziliyor:
    """ÖLÇÜLDÜ (once.json P2B3-14): çelik kasada case_max 811,0 /
    grain_max 333,0 / safety_margin +285,59 yan yana ETİKETSİZ duruyordu;
    marjın hangi limite ait olduğunu söyleyen tek alan yoktu."""

    def _limitler(self, mat):
        e = _motor(overrides={'case_material': mat})
        _sessiz(e.calculate_performance)
        tm = _sessiz(e._calculate_thermal_analysis)['thermal_management']
        return tm['material_temperature_limits']

    @pytest.mark.parametrize('mat', ['steel_4130', 'aluminum_6061'])
    def test_marj_hangi_limite_ait_oldugunu_soyluyor(self, mat):
        lim = self._limitler(mat)
        assert lim['safety_margin_applies_to'] == 'case_max_temp_k'
        assert 'CASE margin only' in lim['safety_margin_basis']

    @pytest.mark.parametrize('mat', ['steel_4130', 'aluminum_6061'])
    def test_grain_marji_UYDURULMUYOR_ama_beyanli(self, mat):
        lim = self._limitler(mat)
        assert lim['grain_safety_margin_k'] is None
        assert lim['grain_safety_margin_status'] == 'NOT_MODELLED'
        assert 'NOT the grain temperature' in lim['grain_safety_margin_basis']

    def test_hukum_kapsami_da_yazili(self):
        e = _motor()
        _sessiz(e.calculate_performance)
        ht = _sessiz(e._calculate_thermal_analysis)['heat_transfer']
        assert 'case wall only' in ht['thermal_protection_rating_scope']


# ---------------------------------------------------------------------------
# P2B4-01 — itki biçmi sınıfı TEK kaynaktan
# ---------------------------------------------------------------------------
class TestTekBicimSiniflandirici:
    """ÖLÇÜLDÜ (once.json P2B4-01): 6 grain x 3 geometri x 3 basınç = 54
    koşunun 30'unda (%55,6) ``grain_design.burn_profile`` ile
    ``detailed_analysis.thrust_profile_analysis.thrust_curve_type`` FARKLI
    sınıf söylüyordu (ör. star 100/500/30 @40 bar: 'regressive' ⟷
    'Progressive-Regressive'). Onarımdan sonra 0/54."""

    #: V301/K-A (22 Eki): eski çapa A_p/A_t = 0,947'lik boğulan portlu
    #: varsayılan motoru kilitliyordu. bates 30 -> 48 mm (örnek motor),
    #: finocyl 150/800 @20 bar 40 -> 70 mm (A_p/A_t 0,67 -> 1,31); ikisi de
    #: boğulan portluydu ve artık yayımlanmıyor. Öteki satırlar geçerli.
    IZGARA = [('bates', 100.0, 500.0, 48.0, 40.0),
              ('star', 100.0, 500.0, 30.0, 40.0),
              ('wagon_wheel', 100.0, 300.0, 50.0, 90.0),
              ('finocyl', 150.0, 800.0, 70.0, 20.0),
              ('slotted', 100.0, 300.0, 50.0, 20.0),
              ('end_burner', 100.0, 500.0, 30.0, 40.0)]

    @pytest.mark.parametrize('gt,D,L,c,pc', IZGARA)
    def test_iki_alan_AYNI_sinifi_soyluyor(self, gt, D, L, c, pc):
        e = _motor(grain_type=gt, chamber_diameter=D, grain_length=L,
                   core_diameter=c, chamber_pressure=pc)
        res = _sessiz(e.calculate_performance)
        eski = (res.get('grain_design') or {}).get('burn_profile')
        yeni = ((res.get('detailed_analysis') or {})
                .get('thrust_profile_analysis') or {}).get('thrust_curve_type')
        assert eski == (yeni or '').lower() or (eski is None and not yeni), (
            '%s: burn_profile %r ⟷ thrust_curve_type %r' % (gt, eski, yeni))

    def test_sinif_belirlenemezse_NEUTRAL_uydurulmuyor(self):
        """Eski kopya örnek<20 dalında koşulsuz 'neutral' üretiyordu."""
        e = _motor()
        rapor = _sessiz(e._thrust_shape_report, [1.0, 1.0], None)
        assert rapor['shape'] == 'Undetermined'
        # Alanın sözleşmesi: sınıf yoksa None + gerekçe (sessiz 'neutral' yok)
        res = _sessiz(e.calculate_performance)
        gd = res['grain_design']
        assert gd['burn_profile_status'] in ('classified', 'undetermined')
        if gd['burn_profile'] is None:
            assert gd['burn_profile_status'] == 'undetermined'
        assert 'thrust_profile_analysis' in gd['burn_profile_source']


# ---------------------------------------------------------------------------
# P2B4-04 / P2B4-07 — kütle zinciri
# ---------------------------------------------------------------------------
class TestKuruKutleZinciri:
    """ÖLÇÜLDÜ (once.json): (a) liner kalınlığı 0,1 -> 50 mm iken
    dry_mass_kg 16,286993 kg'da SABİT; (b) liner_density 200/1200/3000 için
    ``_dry_mass_breakdown.total_kg`` 11,7631/16,2870/24,4300 iken
    ``_calculate_dry_mass()`` üçünde de 16,2870 — iki yol %38 ayrışmıştı;
    (c) 10/10/3 mm motorda dry_mass_kg 0,100000 ⟷ inert toplam 0,084638
    (beyansız 100 g tabanı)."""

    def _e(self, **ov):
        taban = {'insulation_thickness': 20.0}
        taban.update(ov)
        return _motor(overrides=taban)

    def test_liner_KALINLIGI_kuru_kutleyi_hareket_ettiriyor(self):
        ince = self._e(liner_thickness=0.1)
        kalin = self._e(liner_thickness=50.0)
        a = float(_sessiz(ince._calculate_dry_mass))
        b = float(_sessiz(kalin._calculate_dry_mass))
        assert b > 1.5 * a, 'liner kalınlığı kuru kütleye girmiyor: %r -> %r' % (a, b)
        assert _sessiz(kalin._dry_mass_breakdown)['liner_kg'] > 20 * _sessiz(
            ince._dry_mass_breakdown)['liner_kg']

    def test_liner_YOGUNLUGU_kuru_kutleyi_hareket_ettiriyor(self):
        hafif = float(_sessiz(
            self._e(liner_thickness=5.0, liner_density=200.0
                    )._calculate_dry_mass))
        agir = float(_sessiz(
            self._e(liner_thickness=5.0, liner_density=3000.0
                    )._calculate_dry_mass))
        assert agir > 1.5 * hafif, (hafif, agir)

    @pytest.mark.parametrize('rho', [200.0, 1200.0, 3000.0])
    def test_IKI_YOL_ayrisamaz(self, rho):
        e = self._e(liner_thickness=5.0, liner_density=rho)
        dokum = _sessiz(e._dry_mass_breakdown)
        toplam = float(_sessiz(e._calculate_dry_mass))
        assert dokum['total_kg'] == pytest.approx(toplam, rel=1e-12), (
            'döküm %r ⟷ _calculate_dry_mass %r' % (dokum['total_kg'], toplam))

    def test_kucuk_motorda_100g_TABANI_yok(self):
        # V301/K-A (KT-03): astar radyal yer kaplayınca 10 mm'lik motorun
        # kasası 14 mm'ye çıktı ve fiziksel kütle 0,128 kg oldu (100 g
        # eşiğinin ÜSTÜ — taban değil, gerçek kütle). Düğümün iddiası
        # (100 g tabanı yok) ince astarla (0,5 mm; 0,0953 kg) ölçülür.
        e = _motor(chamber_diameter=10.0, grain_length=10.0,
                   core_diameter=3.0, overrides={'liner_thickness': 0.5})
        toplam = float(_sessiz(e._calculate_dry_mass))
        dokum = _sessiz(e._dry_mass_breakdown)
        assert toplam == pytest.approx(dokum['total_kg'], rel=1e-12)
        assert toplam < 0.1, 'kuru kütle hâlâ 100 g tabanına oturuyor: %r' % toplam

    def test_bileşenler_toplami_TAM(self):
        e = self._e(liner_thickness=5.0)
        d = _sessiz(e._dry_mass_breakdown)
        parcalar = ('case_kg', 'closure_kg', 'nozzle_kg', 'insulation_kg',
                    'liner_kg', 'igniter_misc_kg')
        assert sum(d[k] for k in parcalar) == pytest.approx(d['total_kg'],
                                                            rel=1e-12)


# ---------------------------------------------------------------------------
# P2B4-08 — geri çekilmiş künye kullanıcıya gitmiyor
# ---------------------------------------------------------------------------
class TestChugKunyesiGeriCekilmisAtifTasimiyor:
    """ÖLÇÜLDÜ (once.json P2B4-08): transient chug uyarısı
    '(SP-8089)' basıyordu; deponun eşiği tanımlayan TEK kaynağı
    (acoustic_modes.CHUG_THRESHOLD_SOURCE) o atfı açıkça geri çekiyor."""

    def test_kunye_TEK_kaynaktan_geliyor(self):
        from hrma.analysis.acoustic_modes import CHUG_THRESHOLD_CITATION
        govde = _oku('hrma/analysis/transient_ballistics.py')
        assert 'chugging risk (SP-8089)' not in govde
        assert 'chugging risk ({CHUG_THRESHOLD_CITATION})' in govde
        assert 'SP-8089' not in CHUG_THRESHOLD_CITATION

    def test_uzun_gerekce_ile_KISA_kunye_ayni_seyi_soyluyor(self):
        from hrma.analysis.acoustic_modes import (CHUG_THRESHOLD_CITATION,
                                                  CHUG_THRESHOLD_SOURCE)
        assert 'not attributed to it' in CHUG_THRESHOLD_SOURCE
        # Kısa künyenin andığı her kaynak uzun gerekçede de anılmalı.
        for parca in ('Sutton & Biblarz', 'SP-194'):
            assert parca in CHUG_THRESHOLD_CITATION
            assert parca in CHUG_THRESHOLD_SOURCE

    def test_i18n_deseni_uretilen_cumleyi_YAKALIYOR(self):
        from hrma.analysis.acoustic_modes import CHUG_THRESHOLD_CITATION
        js = _oku('hrma/static/js/i18n_charts.js')
        m = re.search(r'\[/(\^t=.*?chugging risk[^/]*)/,', js)
        assert m, 'i18n chug deseni bulunamadı'
        desen = m.group(1).replace('\\/', '/')
        ornek = ('t=3.10s: ΔP/Pc=0.11 < 0.15 — chugging risk (%s)'
                 % CHUG_THRESHOLD_CITATION)
        assert re.match(desen, ornek), (desen, ornek)


# ---------------------------------------------------------------------------
# P15B4-05 — katı cad_design KENDİNİ TANITIYOR
# ---------------------------------------------------------------------------
class TestCadDesignSemasiKendiniTanitiyor:
    """ÖLÇÜLDÜ (once.json P15B4-05): ``cad_design`` katıda 9 anahtarlı
    tasarım sözlüğü, hibritte 6 anahtarlı görselleştirme sözlüğü, sıvıda
    None; kesişim BOŞ ve okuyucular hangi şekli aldıklarını soramıyor.
    Onarımın KATI yarısı: şeklin adı şeklin içinde."""

    def test_katı_sema_adi_yayimlaniyor(self, client):
        from hrma.engines.solid_rocket_engine import SOLID_CAD_DESIGN_SCHEMA
        r = client.post('/calculate_solid', json=dict(UC_TABAN_D18))
        assert r.status_code == 200, r.get_data(as_text=True)[:200]
        cad = r.get_json().get('cad_design') or {}
        assert cad.get('schema') == SOLID_CAD_DESIGN_SCHEMA
        assert cad['schema'].startswith('hrma.solid.cad_design/')

    def test_okuyucu_HIBRIT_seklini_ayirt_edebiliyor(self, client):
        """Etiketin işe yaradığı yer: iki şekil aynı adı taşıyor ama artık
        katı olan kendini söylüyor, dolayısıyla okuyucu sessiz yedeğe
        düşmek yerine 'bu benim şeklim değil' diyebiliyor."""
        from hrma.engines.solid_rocket_engine import SOLID_CAD_DESIGN_SCHEMA
        r2 = client.post('/calculate', json={
            'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
            'chamber_pressure': 20.0, 'fuel_type': 'htpb',
            'oxidizer_type': 'n2o'})
        assert r2.status_code == 200
        hibrit = r2.get_json().get('cad_design') or {}
        assert hibrit.get('schema') != SOLID_CAD_DESIGN_SCHEMA


# ---------------------------------------------------------------------------
# P2B3-06 — künye atfı ÖLÇÜLMEDEN yazılmaz
# ---------------------------------------------------------------------------
class TestBogazBoyutlandirmaAtfiOlculmemisSebepIcermiyor:
    """Fable-D16 ŞART: yorum, bayatlamayı P2B2-14'e (plato çarpanı sökümü)
    bağlıyordu; denetçi taban 6fde52b'yi çarpan yerindeyken ölçtü ve orada
    da 70,6 / 112,4 çıktı — atıf yanlıştı ve hiç ölçülmemişti."""

    def test_olculmemis_sebep_atfi_kaldirildi(self):
        govde = _oku('hrma/engines/solid_rocket_engine.py')
        assert ('yanma-hızı modeli değiştikçe (P2B2-14, plato çarpanının '
                'sökülmesi)') not in govde
        i = govde.index('SOLID_THROAT_SIZING_REFERENCE = {')
        blok = govde[max(0, i - 2500):i]
        assert 'ölçülmedi' in blok or 'ÖLÇÜLMEMİŞTİ' in blok

    def test_D16_raporu_da_hizalandi(self):
        rapor = _oku(kanit_gerekli('docs/scofield/raw/OH/D16/kati/a2/rapor.md'))
        assert 'DÜZELTME (ÖH D18' in rapor
        assert '6fde52b' in rapor


# ---------------------------------------------------------------------------
# Çapa: ölçülen sayılar (kalemler arası regresyon kilidi)
# ---------------------------------------------------------------------------
def test_olculen_sayilar_capasi():
    """sonra.json'daki ana sayılar. Bu test, kalemlerin ürün etkisini tek
    yerde kilitler; sayı kayarsa yeniden ölçüm gerekir."""
    e = _motor()
    dokum = _sessiz(e._dry_mass_breakdown)
    # V301/K-A (22 Eki, KT-03): astar artık radyal yer kaplar (kasa iç çapı = tane + 2·(astar + yalıtım)); kasa 2·t_astar büyüdü, çapa yeniden ölçüldü (tolerans aynı).
    # 6,001397012523196 -> 6,4534577390220145 kg; küçük motor
    # 0,0945908415254658 -> 0,12844615192502312 kg.
    assert dokum['total_kg'] == pytest.approx(6.4534577390220145, rel=1e-9)
    assert dokum['liner_kg'] == pytest.approx(0.4614371289592694, rel=1e-6)
    kucuk = _motor(chamber_diameter=10.0, grain_length=10.0,
                   core_diameter=3.0)
    assert float(_sessiz(kucuk._calculate_dry_mass)) == pytest.approx(
        0.12844615192502312, rel=1e-9)
