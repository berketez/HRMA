# -*- coding: utf-8 -*-
"""ÖH D30 · yapisal-sistem · aşama 1/1 bekçileri.

İki kalem:

``P16B3-24`` (D29 DEVİR)
    ``/analyze_safety``: hibrit yakıt ``htpb`` TNT tablosunda yoktu ve
    ``liquid_biprop`` sınıfına düşüyordu. Kalemin BU yarısı D29'da
    (``4b689a56`` / ``0cfd5d25``, OH-D28-08) onarıldı; buradaki bekçiler
    o onarımı kilitler. KALAN yarı D30'da ölçüldü ve onarıldı: künye
    ``propellant_class`` ile ``known_propellant_classes``i yan yana
    yayımlıyordu ama D29'un TÜRETİLMİŞ hibrit sınıfı o listede YOKTU —
    10 istekten 9'unda yayımlanan sınıf yanıtın HİÇBİR listesinde
    geçmiyordu (kanıt: ``docs/scofield/raw/OH/D30/yapisal-sistem/a1/
    once.json`` K4 → ``sonra.json`` K4).

``P13B4-10`` (ZORLA — bekçi borcu)
    ``docs/scofield/raw/OH/D26/ana_model/p13b410_dagitim.json`` içinde
    ``kulvar='yapisal-sistem'`` ve ``odendi`` BOŞ olan beş kalem
    (P5B1-01, P5B2-01, P5B2-02, P5B2-03, P5B4-38). Borcun ölçütü:
    "kusuru TANIMLAYAN sembolü ANAN tek test yok". Her sınıf o sembolü
    ADIYLA çağırır; hiçbiri uçtan dolaylı geçmez.
"""
import pytest

from hrma.analysis.regression_analysis import (
    RegressionAnalyzer, UnresolvedFuelType)
from hrma.analysis.safety_analysis import (
    ANTIDOTE_WITHHELD,
    HYBRID_DEFAULT_OXIDIZER,
    KNOWN_PROPELLANT_CLASSES,
    SafetyAnalyzer,
    TOXIC_LEVEL_NOT_EVALUATED,
    TOXIC_RESOLUTION_TABULATED,
    UnresolvedChamberMaterial,
    WALL_TEMP_NOT_COMPUTED,
    hybrid_oxidizer_tnt_equivalent,
)

#: P16B3-24'ün kendi gövdesi (rapor 17,5 kg TNT yazıyor: 17,5 / 0,35 = 50 kg).
GUVENLIK = {
    'chamber_pressure': 20.0, 'chamber_temperature': 3000.0,
    'thrust': 1000.0, 'burn_time': 10.0, 'propellant_mass': 50.0,
    'chamber_diameter': 0.1, 'wall_thickness': 0.005,
    'material': 'steel_4130', 'motor_type': 'hybrid',
}


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _guvenlik(client, **ek):
    govde = dict(GUVENLIK)
    govde.update(ek)
    return client.post('/analyze_safety', json=govde)


# =====================================================================
# P16B3-24
# =====================================================================
class TestP16B324HibritTntSinifi:
    """``htpb`` artık sıvı çift-iticinin sayısını ÖDÜNÇ ALMIYOR."""

    def test_htpb_SIVI_cift_iticinin_sayisini_odunc_ALMIYOR(self):
        an = SafetyAnalyzer()
        sinif, _dayanak = an._resolve_explosive_class('htpb', 'hybrid')
        assert sinif != 'liquid_biprop', (
            'P16B3-24 geri geldi: hibrit yakıt LOX/RP-1 sınıfına düşüyor')
        assert sinif == 'hybrid_%s' % HYBRID_DEFAULT_OXIDIZER, sinif

    def test_hibrit_faktoru_TURETIMDEN_gelir_literal_DEGIL(self):
        """Sayı seçilmez, ``e_ox / e_TNT`` bölmesinden çıkar."""
        an = SafetyAnalyzer()
        sinif = 'hybrid_%s' % HYBRID_DEFAULT_OXIDIZER
        assert an.propellant_tnt_equivalents[sinif] == (
            hybrid_oxidizer_tnt_equivalent(HYBRID_DEFAULT_OXIDIZER)), (
            'tablodaki hibrit faktörü türetimden KOPMUŞ (kalibrasyon)')

    def test_kunye_kendini_YALANLAMIYOR_cozulen_sinif_yayimlanan_listede(self):
        """ÖLÇÜLEN KUSUR (D30): ``propellant_class`` yayımlanıyordu ama
        yanıtın yayımladığı sınıf listelerinin HİÇBİRİNDE yoktu.

        ``KNOWN_PROPELLANT_CLASSES`` panelin SEÇTİRDİĞİ kümedir ve öyle
        kalır; ``_resolvable_propellant_classes`` ÇÖZÜLEBİLEN kümedir.
        Çözülen sınıf ikisinin BİRLEŞİMİNDE olmak zorundadır.
        """
        an = SafetyAnalyzer()
        for ad in ('htpb', 'paraffin', 'pe', 'pmma', 'abs', 'apcp'):
            kunye = an._classify_toxic_inventory(ad, 'hybrid')
            sinif = kunye['propellant_class']
            birlesim = set(kunye['known_propellant_classes']) | set(
                kunye['resolvable_propellant_classes'])
            assert sinif in birlesim, (
                "'%s': künye '%s' sınıfını yayımlıyor ama yayımladığı "
                'listelerin hiçbirinde yok' % (ad, sinif))

    def test_cozulebilir_liste_TABLODAN_gelir_ikinci_kez_yazilmaz(self):
        an = SafetyAnalyzer()
        assert an._resolvable_propellant_classes() == sorted(
            an.propellant_tnt_equivalents), (
            'çözülebilir sınıf listesi TNT tablosundan kopmuş (doktrin 4)')
        # Panelin kümesi bu kümenin ALT kümesidir, tersi değil.
        assert set(KNOWN_PROPELLANT_CLASSES) <= set(
            an._resolvable_propellant_classes())

    def test_uc_kunyesi_cozulebilir_sinif_listesini_YAYIMLIYOR(self, client):
        r = _guvenlik(client, propellant_type='htpb')
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        kunye = (r.get_json() or {}).get('toxic_basis') or {}
        sinif = kunye.get('propellant_class')
        assert sinif, 'künye sınıfı yayımlamıyor'
        birlesim = set(kunye.get('known_propellant_classes') or []) | set(
            kunye.get('resolvable_propellant_classes') or [])
        assert sinif in birlesim, (
            'uç künyesi kendini yalanlıyor: %s / %s' % (sinif, sorted(birlesim)))

    def test_kunye_alanlari_toxic_hazards_BLOGUNA_sizmiyor(self, client):
        """Panel sağırlık sözleşmesi (``test_z5s_hukum_kanali``) korunur."""
        r = _guvenlik(client, propellant_type='htpb')
        toksik = ((r.get_json() or {}).get('safety_analysis') or {}).get(
            'toxic_hazards') or {}
        assert 'resolvable_propellant_classes' not in toksik, (
            'yeni künye alanı bloğa sızdı; panel sözleşmesini kırar')


# =====================================================================
# P13B4-10 — bekçi borcu (5 kalem)
# =====================================================================
class TestP13B410P5B101YapisalHukumGeriOkumasi:
    """P5B1-01 — kazanılmış SF 21,58 iken UNSAFE/HIGH; hüküm kullanıcının
    kendi hedefinin geri okunmasıydı. TANIMLAYICI SEMBOL:
    ``hrma.app._withhold_unearned_structural_verdict``.
    """

    def test__withhold_unearned_structural_verdict_TOTOLOJIK_SFde_hukmu_CEKER(
            self):
        from hrma.app import _withhold_unearned_structural_verdict
        sonuc = {
            'chamber_analysis': {'design_mode': 'size',
                                 'safety_factor_is_tautological': True},
            'safety_analysis': {'status': 'ACCEPTABLE', 'risk_level': 'LOW'},
        }
        beyan = _withhold_unearned_structural_verdict(sonuc, True)
        assert beyan['verdict'] == 'withheld', beyan
        assert 'safety_factor_is_tautological' in \
            beyan['verdict_withheld_reasons'], beyan
        assert sonuc['safety_analysis']['status'] != 'ACCEPTABLE', (
            'kazanılmamış ONAY geri çekilmedi')
        assert sonuc['safety_analysis'].get('verdict_basis'), (
            'hüküm çekildi ama gerekçesi yazılmadı')

    def test__withhold_unearned_structural_verdict_UYARIYI_susturmaz(self):
        """ONAY geri çekilir, UYARI çekilmez (kalemin ikinci ayağı)."""
        from hrma.app import _withhold_unearned_structural_verdict
        sonuc = {
            'chamber_analysis': {'design_mode': 'size',
                                 'safety_factor_is_tautological': True},
            'safety_analysis': {'status': 'UNSAFE', 'risk_level': 'HIGH'},
        }
        _withhold_unearned_structural_verdict(sonuc, True)
        assert sonuc['safety_analysis']['status'] == 'UNSAFE', (
            'gerçek uyarı NOT_EVALUATED ile susturuldu')


class TestP13B410P5B201CidarSicakligiOrtamaDusmuyor:
    """P5B2-01 — termal panel HER istekte 293,15 K'ye düşüyordu ve 2877,8 K
    cidara LOW/ACCEPTABLE basılıyordu. TANIMLAYICI SEMBOLLER:
    ``SafetyAnalyzer._resolve_wall_temperatures`` +
    ``WALL_TEMP_NOT_COMPUTED`` + ``_wall_temperature_was_computed``.
    """

    def test__resolve_wall_temperatures_hesaplanamayinca_KUNYEYI_isaretler(
            self):
        an = SafetyAnalyzer()
        ic, dis, kaynak = an._resolve_wall_temperatures(
            {}, 'steel_4130', 0.005, 293.15)
        assert kaynak.startswith(WALL_TEMP_NOT_COMPUTED), (
            'yedek cidar sıcaklığı hesaplanmış gibi künyeleniyor: %r' % kaynak)
        assert not an._wall_temperature_was_computed(kaynak), (
            'kapı yedek künyeyi "hesaplandı" sayıyor — hüküm kazanılmamış '
            'sayıdan üretilir')
        assert ic == dis == pytest.approx(293.15), (ic, dis)

    def test__resolve_wall_temperatures_SOZLESMEYI_okur_ortama_dusmez(self):
        an = SafetyAnalyzer()
        ic, dis, kaynak = an._resolve_wall_temperatures(
            {'wall_temperature_hot': 2877.8, 'wall_temperature_cold': 800.0},
            'steel_4130', 0.005, 293.15)
        assert ic == pytest.approx(2877.8) and dis == pytest.approx(800.0)
        assert an._wall_temperature_was_computed(kaynak), kaynak


class TestP13B410P5B202ToksikEslemeUlasilabilir:
    """P5B2-02 — kendini yenen sözlük: 120 kg N2O4/MMH'ye NONE + boş PPE +
    "antidot gerekmez". TANIMLAYICI SEMBOLLER:
    ``SafetyAnalyzer._classify_toxic_inventory`` + ``ANTIDOTE_WITHHELD``.
    """

    def test__classify_toxic_inventory_n2o4_mmh_envanterini_COZUYOR(self):
        an = SafetyAnalyzer()
        kunye = an._classify_toxic_inventory('n2o4_mmh', 'liquid')
        assert kunye['resolution'] == TOXIC_RESOLUTION_TABULATED, kunye
        assert set(kunye['components']) >= {'n2o4', 'mmh'}, kunye

    def test_ANTIDOTE_WITHHELD_bos_envanterde_TAVSIYE_yerine_gecer(self):
        an = SafetyAnalyzer()
        satirlar = an._determine_required_antidotes({
            'toxic_components': [],
            'toxic_hazard_level': TOXIC_LEVEL_NOT_EVALUATED,
        })
        assert satirlar == [ANTIDOTE_WITHHELD], satirlar
        assert 'NOT EVALUATED' in ANTIDOTE_WITHHELD

    def test_bos_envanterde_PPE_listesi_BOS_DEGIL(self):
        an = SafetyAnalyzer()
        ppe = an._determine_toxic_ppe_requirements([])
        assert ppe, 'boş envanterde PPE listesi boş — "koruyucu gerekmez" gibi'


class TestP13B410P5B203MalzemeSessizceCelikDegil:
    """P5B2-03 — yazım hatalı malzeme sessizce ``steel_4130`` oluyordu
    (SF 1,964 → 3,286, UNSAFE → MARGINAL). TANIMLAYICI SEMBOL:
    ``SafetyAnalyzer._resolve_chamber_material``.
    """

    @pytest.mark.parametrize('ad', ['aluminum6061', 'AL6061', 'unobtainium',
                                    ''])
    def test__resolve_chamber_material_yazim_hatasini_REDDEDER(self, ad):
        with pytest.raises(UnresolvedChamberMaterial):
            SafetyAnalyzer._resolve_chamber_material(ad)

    def test__resolve_chamber_material_dogru_adi_CELIGE_cevirmez(self):
        kayit, anahtar = SafetyAnalyzer._resolve_chamber_material(
            'aluminum_6061')
        assert anahtar == 'aluminum_6061'
        celik = SafetyAnalyzer._resolve_chamber_material('steel_4130')[0]
        assert kayit['yield_strength'] != celik['yield_strength'], (
            'alüminyum çeliğin akma dayanımıyla değerlendiriliyor')


class TestP13B410P5B438YakitKimligiKaybolmuyor:
    """P5B4-38 — ürün akışında yakıt kimliği kayboluyordu: her yakıt
    sessizce HTPB (parafinde r_dot %-78,5). TANIMLAYICI SEMBOL:
    ``RegressionAnalyzer.resolve_fuel_key``.
    """

    def test_resolve_fuel_key_parafini_HTPBye_CEVIRMEZ(self):
        an = RegressionAnalyzer()
        assert an.resolve_fuel_key('paraffin') == 'paraffin'
        assert an.resolve_fuel_key(' Paraffin ') == 'paraffin'

    @pytest.mark.parametrize('ad', ['sihir', '', None, 42])
    def test_resolve_fuel_key_cozulemeyen_adi_REDDEDER(self, ad):
        an = RegressionAnalyzer()
        with pytest.raises(UnresolvedFuelType):
            an.resolve_fuel_key(ad)

    def test_yakit_adi_REGRESYON_katsayilarini_gercekten_degistirir(self):
        """Kimlik "taşınıyor" demek yetmez: sayı da ayrışmalı."""
        an = RegressionAnalyzer()
        htpb = an.fuel_properties[an.resolve_fuel_key('htpb')]
        paraffin = an.fuel_properties[an.resolve_fuel_key('paraffin')]
        assert (htpb['a'], htpb['n']) != (paraffin['a'], paraffin['n']), (
            'iki yakıt aynı regresyon katsayılarını kullanıyor')
