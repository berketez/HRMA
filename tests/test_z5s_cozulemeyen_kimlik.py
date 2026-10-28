"""ÖH Z5S / S4 — ÇÖZÜLEMEYEN KİMLİK bekçileri.

Kapsanan defter kalemleri:

* **P16B1-02** (kritik) — künye adın ÇÖZÜLDÜĞÜNE değil DOLU olduğuna
  bakıyordu: ``chamber_material='peynir'`` isteğinde motor
  ``warn.hybrid.chamber_material_unknown`` üretip çeliğe düşerken künye
  yine ``chamber_material_source: 'user_supplied'`` diyordu.
* **P16B1-03** (kritik) — yalnız harf büyüklüğü (``'STEEL_4130'``) ısı
  zincirini A36 jenerik çeliğine düşürüyor, yapısal zincir AISI 4130'da
  kalıyordu: TEK yanıtta İKİ malzeme, sıfır beyan.
* **P16B3-03** (kritik) — tanınmayan ad termal uçta ``risk_level='HIGH'``
  + ``melting_safety_factor≈0,5965`` + ``withheld=False`` bastırıyordu.
* **P7B3-16** (kritik) + **P16B1-32** — ``/api/regression-analysis``
  tanımsız yakıtı sessizce HTPB yapıyor, yanıt İKİ farklı yakıt adı
  taşıyordu (``fuel_type='peynir'`` ⟷ ``fuel_name='HTPB'``).
* **P7B3-27** — aynı malzeme adı dört kardeş uçta ÜÇ farklı sessiz yedeğe
  düşüyordu.
* **P7B1-07** — çözülemeyen ad yapısal emniyet katsayısını SF = 1
  eşiğinin öbür yakasına taşıyordu; künye "kullanıcı verdi + doğrulama
  yayımlandı" diyordu.
* **P16B1-21** — tanımsız ``nozzle_type`` sessizce çan lülesine
  düşüyordu; ``""`` de varsayılana değil çan dalına gidiyordu.

ÖLÇÜM KAYITLARI: ``docs/scofield/raw/OH/Z5S/s4/`` (``once_supurme.json``
= onarımdan önceki tam süpürme, ``sonra_supurme.json`` = sonrası,
``sonra_kimlik_repro.json`` = kimliğin hükmü belirlediği vakalar).
"""
import pytest

from hrma.app import app
from hrma.analysis.heat_transfer_analysis import (HeatTransferAnalyzer,
                                                  UnresolvedMaterial,
                                                  resolve_material_key)
from hrma.analysis.regression_analysis import (RegressionAnalyzer,
                                               UnresolvedFuelType)


# --- Ortak gövdeler --------------------------------------------------------
#: Hibrit tasarım isteği (``/calculate``); figürler kapalı — bu dosyanın
#: ölçtüğü şey kimlik, çizim değil.
KIMLIK_HIBRIT = {
    'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
    'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
    'chamber_pressure': 20.0, 'l_star': 1.0, 'expansion_ratio': 4.0,
    'include_plots': False,
}
KIMLIK_TERMAL = {
    'chamber_pressure': 20.0, 'chamber_temperature': 3000.0,
    'chamber_diameter': 0.1, 'chamber_length': 0.5, 'burn_time': 10.0,
    'throat_diameter': 0.02, 'wall_thickness': 0.005,
}
KIMLIK_YAPISAL = {
    'chamber_pressure': 20.0, 'chamber_diameter': 0.1,
    'chamber_length': 0.5, 'throat_diameter': 0.02, 'burn_time': 10.0,
}
KIMLIK_GUVENLIK = {
    'chamber_pressure': 20.0, 'chamber_temperature': 3000.0,
    'thrust': 1000.0, 'burn_time': 10.0, 'propellant_mass': 5.0,
    'chamber_diameter': 0.1, 'chamber_length': 0.5,
    'throat_diameter': 0.02, 'mdot_total': 1.0, 'wall_thickness': 0.005,
}
KIMLIK_DUVAR = {
    'chamber_pressure': 20, 'chamber_temperature': 3000,
    'chamber_diameter': 0.1, 'chamber_length': 0.5, 'burn_time': 10,
    'mdot_total': 1.0, 'wall_thickness': 0.005, 'n_stations': 20,
}
KIMLIK_REGRESYON = {
    'burn_time': 10.0, 'mdot_ox': 1.0,
    'port_diameter_initial': 0.03, 'port_diameter_final': 0.05,
    'chamber_length': 0.3,
}
#: SF = 1 eşiğinin İKİ YAKASINI aynı geometride gösteren yük (P7B1-07).
KIMLIK_ESIK = {
    'chamber_pressure': 100.0, 'chamber_diameter': 0.2,
    'chamber_length': 0.5, 'throat_diameter': 0.04,
    'burn_time': 10.0, 'wall_thickness': 0.0035,
}

#: Malzeme kimliğini okuyan DÖRT kardeş uç — hepsi aynı cevabı vermeli.
MALZEME_UCLARI = [
    ('/analyze_thermal_safety', KIMLIK_TERMAL),
    ('/analyze_structural_safety', KIMLIK_YAPISAL),
    ('/analyze_safety', KIMLIK_GUVENLIK),
    ('/api/analysis/wall-profile', KIMLIK_DUVAR),
]


@pytest.fixture(scope='module')
def istemci():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _yapraklar(o, yol='', out=None):
    """Yanıtın bütün yapraklarını ``{yol: değer}`` olarak düzleştirir."""
    if out is None:
        out = {}
    if isinstance(o, dict):
        for k, v in o.items():
            _yapraklar(v, f'{yol}.{k}' if yol else k, out)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            _yapraklar(v, f'{yol}[{i}]', out)
    else:
        out[yol] = o
    return out


def _sayilar(j):
    """Yanıttaki bütün SAYI yapraklarını döner (bool sayı değildir)."""
    return {k: v for k, v in _yapraklar(j).items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)}


# ===========================================================================
# P16B1-03 — HARF BÜYÜKLÜĞÜ EKSENİ
# ===========================================================================
class TestHarfBuyuklugu:
    """Yalnız harf büyüklüğü SAYIYI değiştiremez."""

    @pytest.mark.parametrize('yol,govde', MALZEME_UCLARI)
    def test_buyuk_harfli_ad_kanonik_adla_ayni_sayilari_verir(
            self, istemci, yol, govde):
        """ÖLÇÜLDÜ (``once_supurme.json``): ``'STEEL_4130'`` termal uçta
        ``melting_safety_factor = 0,5965`` (A36), ``'steel_4130'`` ise
        ``0,5736`` (AISI 4130) veriyordu — aynı malzemenin iki yazımı iki
        farklı motor demekti."""
        kanonik = istemci.post(yol, json=dict(govde, material='steel_4130'))
        buyuk = istemci.post(yol, json=dict(govde, material='STEEL_4130'))
        assert kanonik.status_code == 200
        assert buyuk.status_code == 200
        assert _sayilar(buyuk.get_json()) == _sayilar(kanonik.get_json()), (
            'Harf büyüklüğü sayıları değiştiriyor: ad hâlâ ham sözlük '
            'aramasıyla çözülüyor olabilir.')

    def test_calculate_tek_yanitta_tek_malzeme_tasir(self, istemci):
        """ÖLÇÜLDÜ: ``chamber_material='STEEL_4130'`` isteğinde

            motor.structural_analysis.material_properties.name
                = 'AISI 4130 low-alloy steel (normalized)'
            motor.heat_transfer_analysis.material_properties.name
                = 'Carbon steel (generic, A36-class)'

        Aynı motorun iki modülü iki farklı malzemeyle koşuyordu."""
        j = istemci.post('/calculate',
                         json=dict(KIMLIK_HIBRIT,
                                   chamber_material='STEEL_4130')).get_json()
        motor = j['motor']
        isi = motor['heat_transfer_analysis']['material_properties']['name']
        yapisal = motor['structural_analysis']['material_properties']['name']
        assert isi == yapisal, (
            f'Tek yanıtta iki malzeme: ısı zinciri {isi!r}, yapısal zincir '
            f'{yapisal!r}.')

    def test_modul_kendisi_de_harf_buyuklugunu_cozer(self):
        """Uç kapısı olmasa da modül çözmeli (ikinci savunma hattı)."""
        assert resolve_material_key('STEEL_4130') == 'steel_4130'
        assert resolve_material_key('  Steel_4130 ') == 'steel_4130'
        # materials_db'nin KENDİ takma adı; yeni takma ad icat edilmedi.
        assert resolve_material_key('in718') == 'inconel_718'


# ===========================================================================
# P16B3-03 + P7B3-27 — ÇÖZÜLEMEYEN AD HÜKÜM ÜRETEMEZ
# ===========================================================================
class TestCozulemeyenMalzeme:

    @pytest.mark.parametrize('yol,govde', MALZEME_UCLARI)
    @pytest.mark.parametrize('ad', ['peynir', 'inconel718', 'aluminum6061'])
    def test_hukum_uretilmez_ve_ad_adiyla_reddedilir(
            self, istemci, yol, govde, ad):
        """ÖLÇÜLDÜ: dördü de 200 + TAM hüküm dönüyordu; termal uçta
        ``risk_level='HIGH'`` ve ``melting_safety_factor=0,5965`` (yani
        A36 çeliğinin marjı) basılıyordu."""
        r = istemci.post(yol, json=dict(govde, material=ad))
        assert r.status_code == 422, (
            f'{yol} çözülemeyen {ad!r} adıyla hâlâ hüküm üretiyor.')
        j = r.get_json()
        assert j['error'] == 'unresolved_material'
        kunye = j['invalid_fields'][0]
        assert kunye['field'] == 'material'
        assert kunye['requested'] == ad
        assert kunye['resolution'] == 'unresolved'
        # Kabul edilen adlar gövdede: kullanıcı doğrusunu bulabilmeli.
        assert 'inconel_718' in kunye['available']['canonical']
        # Hiçbir emniyet katsayısı/hüküm sızmamalı.
        yap = _yapraklar(j)
        assert not [k for k in yap if 'safety_factor' in k or
                    'risk_level' in k], (
            'Ret gövdesinde hüküm alanı var — sayı yine üretilmiş.')

    def test_dort_kardes_uc_ayni_ada_ayni_cevabi_verir(self, istemci):
        """P7B3-27: ölçüldü — ``'inconel718'`` termal ve cidar uçlarında
        A36 çeliğine, yapısal uçta AISI 4130'a, güvenlik ucunda yine
        çeliğe düşüyordu. Tek ad, üç farklı malzeme."""
        siniflar = {yol: istemci.post(yol, json=dict(g, material='inconel718'))
                    .status_code for yol, g in MALZEME_UCLARI}
        assert set(siniflar.values()) == {422}, siniflar

    def test_modul_sessiz_yedege_dusmez(self):
        """``self.materials.get(material, self.materials['steel'])``
        kalıbının geri gelmediğinin bekçisi."""
        with pytest.raises(UnresolvedMaterial):
            HeatTransferAnalyzer().analyze_heat_transfer(
                {'chamber_pressure': 20.0, 'chamber_temperature': 3000.0,
                 'chamber_diameter': 0.1, 'chamber_length': 0.5,
                 'burn_time': 10.0, 'mdot_total': 1.0},
                material='peynir', wall_thickness=0.005)

    def test_ad_gonderilmediginde_ucun_kendi_varsayilani_korunur(
            self, istemci):
        """Onarım yeni bir ret DOĞURMAZ: alan hiç gelmediğinde davranış
        aynen bugünküdür ve ``defaults_applied`` bunu zaten söylüyor."""
        r = istemci.post('/analyze_thermal_safety', json=dict(KIMLIK_TERMAL))
        assert r.status_code == 200
        assert 'material' in r.get_json()['defaults_applied']


# ===========================================================================
# P7B1-07 — SF = 1 EŞİĞİNİN GEÇİLMESİ
# ===========================================================================
class TestEsikGecisi:

    def test_sessiz_yedek_hukmu_esigin_obur_yakasina_tasiyordu(self,
                                                               istemci):
        """KUSURUN BÜYÜKLÜĞÜ — bugün de bağımsız ölçülebilir.

        Aynı geometride kullanıcının malzemesi ile sessiz yedeğin (çelik)
        hükmü SF = 1'in İKİ FARKLI yakasında: yani bir alt çizgi
        eksikliği "geçmedi"yi "geçti" yapıyordu.
        """
        al = istemci.post('/analyze_structural_safety',
                          json=dict(KIMLIK_ESIK, material='aluminum_6061'))
        celik = istemci.post('/analyze_structural_safety',
                             json=dict(KIMLIK_ESIK, material='steel_4130'))
        sf_al = (al.get_json()['structural_analysis']['safety_analysis']
                 ['minimum_safety_factor'])
        sf_celik = (celik.get_json()['structural_analysis']['safety_analysis']
                    ['minimum_safety_factor'])
        assert sf_al < 1.0 < sf_celik, (sf_al, sf_celik)

    def test_cozulemeyen_ad_artik_hic_sf_uretmiyor(self, istemci):
        """Yazım hatası artık hüküm üretemez — ne geçen ne kalan."""
        r = istemci.post('/analyze_structural_safety',
                         json=dict(KIMLIK_ESIK, material='aluminum6061'))
        assert r.status_code == 422
        assert r.get_json()['error'] == 'unresolved_material'

    def test_dogrulama_iddiasi_cozulemeyen_adla_kurulamaz(self, istemci):
        """Ret gövdesinde ne ``is_verification`` ne ``design_basis`` olmalı:
        çözülemeyen kimlikle doğrulama YAYIMLANMAZ."""
        j = istemci.post('/analyze_structural_safety',
                         json=dict(KIMLIK_ESIK,
                                   material='aluminum6061')).get_json()
        assert 'design_basis' not in j
        assert 'is_verification' not in _yapraklar(j)


# ===========================================================================
# P16B1-02 — KÜNYE ADIN ÇÖZÜLDÜĞÜNE BAKAR
# ===========================================================================
class TestKunyeDurustlugu:

    # v3.0.1 kulvar M (Ayberk tur 1): ``/calculate`` çözülemeyen kamara
    # malzemesini artık ADLI 422 ile REDDEDER. Aşağıdaki üç bekçi eskiden
    # HTTP 200 yanıtında künyenin dürüstlüğünü ve geri çekilmiş hükmü
    # kilitliyordu; o yanıtın bütün sayıları kullanıcının SORMADIĞI
    # malzemenindi (ölçüldü: docs/scofield/raw/OH/V301/ayberk1/malzeme/
    # once.json S4 — 'peynir' -> 200, motor ss_304'le koşuyor). Künye
    # iddiası (P16B1-02: "kullanıcı verdi" yalanı yok) aynen korunur ve
    # ret gövdesinin KENDİSİNDE sınanır; motorun uyarı sözleşmesi doğrudan
    # motor çağrısında sınanır (uç onu artık hiç çağırmıyor).
    def test_cozulemeyen_ad_user_supplied_diye_kunyelenmez(self, istemci):
        """ÖLÇÜLDÜ: ``chamber_material='peynir'`` isteğinde motor
        ``warn.hybrid.chamber_material_unknown`` üretirken künye aynı
        yanıtta ``'user_supplied'`` yazıyordu. v3.0.1 M: istek reddedilir;
        ret künyesi adı ÇÖZÜLMEMİŞ olarak söyler."""
        r = istemci.post('/calculate',
                         json=dict(KIMLIK_HIBRIT, chamber_material='peynir'))
        assert r.status_code == 422
        kunye = r.get_json()['invalid_fields'][0]
        assert kunye['field'] == 'chamber_material'
        assert kunye['source'] == 'user_supplied_unresolved'
        assert kunye['requested'] == 'peynir'
        assert kunye['resolved_to'] is None
        assert kunye['reason']

    def test_cozulemeyen_kimlikte_yapisal_hukum_geri_cekilir(self, istemci):
        """Z3/Z4 deseni bir adım öteye: çözülemeyen kimlikle ne HÜKÜM ne
        SAYI yayımlanır (v3.0.1 M; eskiden sayılar ss_304'ündü)."""
        r = istemci.post('/calculate',
                         json=dict(KIMLIK_HIBRIT, chamber_material='peynir'))
        assert r.status_code == 422
        j = r.get_json()
        assert j['error'] == 'unresolved_material'
        assert 'motor' not in j and 'structural_design_basis' not in j

    def test_motorun_kendi_uyarisi_hala_kullaniciya_ulasiyor(self, istemci):
        """Motorun uyarı sözleşmesi (doğrudan motor kullanımı) BOZULMADI."""
        from hrma.engines.hybrid_rocket_engine import (
            HybridRocketEngine, HYBRID_CHAMBER_MATERIAL_DEFAULT)
        from hrma.data.materials_db import get_material_safe
        e = HybridRocketEngine.__new__(HybridRocketEngine)
        e.design_warnings = []
        assert e._resolve_chamber_material('peynir') == get_material_safe(
            HYBRID_CHAMBER_MATERIAL_DEFAULT)[1]
        kodlar = [w.get('code') for w in e.design_warnings]
        assert 'warn.hybrid.chamber_material_unknown' in kodlar

    def test_takma_ad_cozumu_kunyede_adiyla_yazilir(self, istemci):
        """``'STEEL_4130'`` sessizce düzeltilmez, DÜZELTİLDİĞİ söylenir."""
        j = istemci.post('/calculate',
                         json=dict(KIMLIK_HIBRIT,
                                   chamber_material='STEEL_4130')).get_json()
        kunye = j['structural_design_basis']
        assert kunye['chamber_material_resolution'] == 'case_normalised'
        assert kunye['chamber_material_resolved_to'] == 'steel_4130'

    def test_kanonik_adda_kunye_ek_alan_uretmez(self, istemci):
        """Söylenecek bir şey yoksa susulur: kanonik adla gelen isteğin
        gövdesi BİT-AYNI kalır (yeni alan eklenmez)."""
        j = istemci.post('/calculate',
                         json=dict(KIMLIK_HIBRIT,
                                   chamber_material='steel_4130')).get_json()
        kunye = j['structural_design_basis']
        assert kunye['chamber_material_source'] == 'user_supplied'
        assert 'chamber_material_requested' not in kunye
        assert 'chamber_material_resolution' not in kunye


# ===========================================================================
# P7B3-16 + P16B1-32 — YAKIT KİMLİĞİ
# ===========================================================================
class TestYakitKimligi:

    def test_tanimsiz_yakit_sessizce_htpb_olmaz(self, istemci):
        """ÖLÇÜLDÜ: ``fuel_type='peynir'`` HTTP 200 dönüyor, yanıt
        ``fuel_type='peynir'`` ile ``fuel_name='HTPB'`` yazıyor,
        ``warnings`` boş kalıyordu."""
        r = istemci.post('/api/regression-analysis',
                         json={'motor_data': dict(KIMLIK_REGRESYON,
                                                  fuel_type='peynir')})
        assert r.status_code == 422
        j = r.get_json()
        assert j['error'] == 'unresolved_fuel_type'
        alan = j['invalid_fields'][0]
        assert alan['field'] == 'fuel_type'
        assert alan['requested'] == 'peynir'
        assert 'paraffin' in alan['available']

    def test_yanit_iki_farkli_yakit_adi_tasiyamaz(self, istemci):
        """Kabul edilen her yanıtta ``fuel_type`` ile ``fuel_name`` AYNI
        yakıtı göstermeli."""
        analizci = RegressionAnalyzer()
        for ad in ('htpb', 'paraffin', 'PARAFFIN'):
            j = istemci.post(
                '/api/regression-analysis',
                json={'motor_data': dict(KIMLIK_REGRESYON, fuel_type=ad)}
            ).get_json()
            rd = j['regression_data']
            beklenen = analizci.fuel_properties[rd['fuel_type']]['name']
            assert rd['fuel_name'] == beklenen, (ad, rd['fuel_type'],
                                                 rd['fuel_name'])

    def test_harf_buyuklugu_yakit_sayisini_degistiremez(self, istemci):
        """ÖLÇÜLDÜ: ``'PARAFFIN'`` sessizce HTPB'ye düşüyordu; parafinin
        regresyon hızı HTPB'ninkinin ~5 katı, yani kimlik SAYIYI
        belirliyor."""
        def r_dot(ad):
            j = istemci.post(
                '/api/regression-analysis',
                json={'motor_data': dict(KIMLIK_REGRESYON, fuel_type=ad)}
            ).get_json()
            return j['regression_data']['regression_rate'][0]
        assert r_dot('PARAFFIN') == r_dot('paraffin')
        assert r_dot('paraffin') != r_dot('htpb')

    def test_duzeltilen_yazim_kunyede_soylenir(self, istemci):
        j = istemci.post(
            '/api/regression-analysis',
            json={'motor_data': dict(KIMLIK_REGRESYON, fuel_type='PARAFFIN')}
        ).get_json()
        assert j['regression_data']['fuel_type_requested'] == 'PARAFFIN'
        assert j['regression_data']['fuel_type'] == 'paraffin'

    def test_kanonik_yakitta_ek_alan_uretilmez(self, istemci):
        j = istemci.post(
            '/api/regression-analysis',
            json={'motor_data': dict(KIMLIK_REGRESYON, fuel_type='paraffin')}
        ).get_json()
        assert 'fuel_type_requested' not in j['regression_data']

    def test_bos_yakit_verilmedi_sayilir_ve_hukum_uretilmez(self, istemci):
        """Açık ``""`` "verilmedi"dir — ve VERİLMEYEN yakıt için eğri YOK.

        ÇEVRİLEN BEKÇİ (ÖH D15 / P5B4-38, kulvar yapisal-sistem a1 onarımı).
        Eski hâli ``regression_data.fuel_type == 'htpb'`` bekliyordu, yani
        boş dizeyle gelen isteğin SESSİZCE HTPB eğrisi almasını KİLİTLİYORDU.
        a1 ölçümü (``a1/once.json``): aynı gövde ``fuel_type`` olmadan
        ``fuel_name: 'HTPB'``, ``fuel_type='paraffin'`` ile r_dot[0] 4,68 kat
        büyük — yani yedek "yaklaşık aynı sonuç" değil BAŞKA bir motordur.
        "Verilmedi" sayma ilkesi korunur (alan düşürülür), ama düşürülen
        alan eğriyi YÖNETTİĞİ için hüküm üretilmez: adlı 422.
        """
        r = istemci.post(
            '/api/regression-analysis',
            json={'motor_data': dict(KIMLIK_REGRESYON, fuel_type='')})
        assert r.status_code == 422
        j = r.get_json()
        assert j['error'] == 'missing_fuel_type'
        assert j['missing_fields'] == ['fuel_type']
        assert 'fuel_type' in j['inputs_treated_as_absent']

    def test_sayi_veya_mantiksal_yakit_adi_kabul_edilmez(self, istemci):
        for ham in (3, True, ['htpb']):
            r = istemci.post('/api/regression-analysis',
                             json={'motor_data': dict(KIMLIK_REGRESYON,
                                                      fuel_type=ham)})
            assert r.status_code == 422, ham

    def test_modul_sessiz_yedege_dusmez(self):
        with pytest.raises(UnresolvedFuelType):
            RegressionAnalyzer().analyze_regression_vs_time(
                dict(KIMLIK_REGRESYON, fuel_type='peynir'))


# ===========================================================================
# P16B1-21 — LÜLE KİMLİĞİ
# ===========================================================================
class TestLuleKimligi:

    def test_tanimsiz_lule_sessizce_can_lulesine_dusmez(self, istemci):
        """ÖLÇÜLDÜ: ``nozzle_type='peynir'`` HTTP 200 + konikten 1.100'den
        fazla yaprak farklı bir tasarım dönüyordu; ``inputs_not_used``
        boştu. Düşüşün yönü kullanıcı ALEYHİNE (yazım hatası tasarımı çan
        lülesine 'yükseltiyordu')."""
        r = istemci.post('/calculate',
                         json=dict(KIMLIK_HIBRIT, nozzle_type='peynir'))
        assert r.status_code == 400
        j = r.get_json()
        assert j['error'] == 'unresolved_nozzle_type'
        assert set(j['invalid_fields'][0]['available']) == {
            'conical', 'bell', 'parabolic'}

    def test_bos_lule_varsayilana_duser_can_dalina_degil(self, istemci):
        """ÖLÇÜLDÜ: ``''`` konik varsayılana DEĞİL çan ailesine
        düşüyordu (``30.0 if nozzle_type == 'conical' else 45.0``)."""
        bos = istemci.post('/calculate',
                           json=dict(KIMLIK_HIBRIT, nozzle_type=''))
        konik = istemci.post('/calculate',
                             json=dict(KIMLIK_HIBRIT, nozzle_type='conical'))
        assert bos.status_code == konik.status_code == 200
        assert _sayilar(bos.get_json()) == _sayilar(konik.get_json())
        assert (bos.get_json()['nozzle_type_resolution']['resolution']
                == 'not_supplied')

    def test_harf_buyuklugu_lulede_de_cozulur_ve_soylenir(self, istemci):
        buyuk = istemci.post('/calculate',
                             json=dict(KIMLIK_HIBRIT, nozzle_type='BELL'))
        kucuk = istemci.post('/calculate',
                             json=dict(KIMLIK_HIBRIT, nozzle_type='bell'))
        assert _sayilar(buyuk.get_json()) == _sayilar(kucuk.get_json())
        assert (buyuk.get_json()['nozzle_type_resolution']['resolution']
                == 'case_normalised')

    def test_kanonik_lulede_ek_alan_uretilmez(self, istemci):
        j = istemci.post('/calculate',
                         json=dict(KIMLIK_HIBRIT,
                                   nozzle_type='conical')).get_json()
        assert 'nozzle_type_resolution' not in j

    @pytest.mark.parametrize('yol,govde', [
        ('/calculate', KIMLIK_HIBRIT),
        ('/api/quick-geometry', KIMLIK_HIBRIT),
        ('/api/transient-analysis', KIMLIK_HIBRIT),
        ('/parametric-analysis', dict(KIMLIK_HIBRIT, param_type='of_ratio',
                                      param_start=2.0, param_end=4.0,
                                      param_steps=3)),
    ])
    def test_kardes_hibrit_uclari_ayni_kapiyi_uygular(self, istemci, yol,
                                                      govde):
        r = istemci.post(yol, json=dict(govde, nozzle_type='peynir'))
        assert r.status_code == 400
        assert r.get_json()['error'] == 'unresolved_nozzle_type'

    def test_ayni_yukte_yakit_kapisi_hala_calisiyor(self, istemci):
        """Doğru desenin kaynağı: aynı istekte ``fuel_type='peynir'``
        zaten reddediliyordu; lüle kapısı onu BOZMAMALI."""
        r = istemci.post('/calculate',
                         json=dict(KIMLIK_HIBRIT, fuel_type='peynir'))
        assert r.status_code == 400


# ===========================================================================
# ÜRÜN SÖZ DAĞARI — kapı ürünün KENDİ seçeneklerini reddediyor mu?
# ===========================================================================
class TestUrunSozDagari:
    """Kapı, ürünün sunduğu seçenekleri kırmamalı; kıran varsa ADIYLA
    bilinmeli (sessiz sürüklenme yok).

    ÖLÇÜLDÜ (28 Ağustos 2026, dört şablondaki 29 malzeme ``<option>``ı
    çözümleyiciden geçirilerek): tek gerçek çakışma katı sayfasının
    ``case_material='composite'`` seçeneğidir. Katı çözücü bu değeri
    ``structural_analysis.case_analysis.case_material`` alanına AYNEN
    yazıyor, ``analysis_dock.readChamberMaterial`` onu okuyor ve paneller
    ``material: 'composite'`` diye POST ediyor.

    Onarımdan ÖNCE: uç bunu sessizce ``steel_4130``e çevirip KOMPOZİT bir
    kasa için ÇELİĞİN emniyet katsayılarını basıyordu.
    Onarımdan SONRA: adlı ``422``.

    Kapı bilerek gevşetilmedi (paketin kapatmakla görevli olduğu sınıf tam
    da budur) ama arkasındaki VERİ boşluğu Berke kararıdır: ``composite``
    ve ``phenolic`` ya ``materials_db``ye bağlanmalı ya formdan
    çıkarılmalıdır (paket yasağı: ``hrma/data/materials_db.py``).
    Bu test o boşluğu KAYIT ALTINDA tutar — kapandığında kırılır ve
    kapandığı fark edilir.
    """

    def test_urun_secenekleri_taranir_ve_bilinen_bosluk_sabit_kalir(self):
        import glob
        import re
        from hrma.app import _resolve_material_request

        cozulmeyen = set()
        for yol in glob.glob('hrma/templates/*.html'):
            html = open(yol, encoding='utf-8').read()
            for kutu in re.finditer(
                    r'<select[^>]*id="([^"]*)"[^>]*>(.*?)</select>',
                    html, re.S):
                alan_id, govde = kutu.group(1), kutu.group(2)
                if 'material' not in alan_id.lower():
                    continue
                if alan_id == 'material_catalog_target':
                    # Malzeme alanı değil: katalog sekmesi seçici
                    # (değerleri 'case' / 'nozzle').
                    continue
                for deger in re.findall(r'<option[^>]*value="([^"]*)"',
                                        govde):
                    if not deger:
                        continue
                    if '{{' in deger:
                        # V301/K-B: sunucu kaydından basılan seçenek (Jinja
                        # ifadesi, değer değil); katı kayıtlarının çözülmesi
                        # tests/test_v301_kati_malzeme.py'de sınanır.
                        continue
                    if _resolve_material_request(deger, 'material',
                                                 'steel')[0] is None:
                        cozulmeyen.add((yol.split('/')[-1], alan_id, deger))
        assert cozulmeyen == set({
            # V301/T-ÇAPA-D (28 Eki ölçümü): sıvı sayfasının 'copper_c101'
            # seçeneği artık materials_db'de çözülüyor (V301/L-KABUK bakır
            # söz dağarı; T-ÇAPA-C1 RAPOR §3 'copper_c101 söz dağarı'). Eski
            # beklenti: ('liquid.html', 'chamber_material', 'copper_c101') —
            # sıvı yarısı da KAPANDI; küme boş.
            # V301/K-B (KT-10/KT-12): katı sayfasının seçenekleri artık
            # sunucu kaydından (ham şablonda yalnız bir Jinja ifadesi var,
            # değer değil): 'phenolic' listeden çıktı (kaynaklı boğaz kaydı ve
            # ablasyon modeli yok; uçta 422), 'composite' motorun kendi ek
            # kaydına (SOLID_CASE_MATERIAL_EXTRA) çözülür ve katı uç onu
            # tanır. Kayıt altındaki boşluğun katı yarısı KAPANDI (eski
            # beklenti: ('solid.html', 'case_material', 'composite') ve
            # ('solid.html', 'nozzle_material', 'phenolic')).
        }), ('Ürünün malzeme söz dağarı ile materials_db arasındaki fark '
            f'değişti: {sorted(cozulmeyen)}')

    def test_kati_kompozit_kasa_artik_sessiz_celik_hukmu_almiyor(
            self, istemci):
        """Ürün yolunun kendisiyle ölçülen sonuç: panelin göndereceği
        değer artık sessiz bir çelik hükmü üretmiyor."""
        r = istemci.post('/analyze_structural_safety',
                         json=dict(KIMLIK_YAPISAL, material='composite'))
        assert r.status_code == 422
        assert r.get_json()['error'] == 'unresolved_material'
