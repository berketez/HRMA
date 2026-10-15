"""ÖH Z5S / P10-A — Enjektör kararlılık hükmünün bekçileri.

Paketin tek teması: enjektör kararlılık/kavitasyon hükmünün UYDURMA bir
varsayılan sayıya, KOPYALANMIŞ bir eşiğe ve DENETİMSİZ bir emniyet
katsayısına dayanması. Yedi kalem, üç dosya:

    P10B2-04 (KRİTİK)  ΔP/Pc paydası uydurma 20 bar'a bölünüyordu
    P10B2-14           ΔP/Pc bandı eşiğin beşinci kopyasıydı (0,10 ⟷ 0,15)
    P10B1-10           _check_warnings'te çıplak 0.2 + "<20%" dizesi
    P10B1-11           tek-kaynak bekçisi o iki biçimi göremiyordu
    P10B1-21           N₂O psat kritik nokta üstünde sessizce sabitleniyordu
    P10B1-22           Nurick K_c yanlış istasyondan kuruluyordu
    P10B1-25           plaka hedef SF'si hiç denetlenmiyordu (-1 -> NaN)

Her bekçi kusurun ÖLÇÜLDÜĞÜ biçimi sınar; mutasyon kanıtları
docs/scofield/raw/OH/Z5S/p10a/mutasyon.txt içindedir.
"""
import ast
import math
import os
import re
import warnings

import pytest

from hrma.analysis import acoustic_modes
from hrma.utils import injector_design as uid
from hrma.utils.injector_design import (
    InjectorPlateInputError, injector_plate_structural)
from hrma.validation import validation_system as vs
from hrma.validation.validation_system import validator

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VALIDATION_PY = os.path.join(REPO_ROOT, 'hrma', 'validation',
                             'validation_system.py')
UTILS_INJ_PY = os.path.join(REPO_ROOT, 'hrma', 'utils', 'injector_design.py')

CELIK = {'name': 'AISI 4130', 'yield_strength': 435e6, 'density': 7850.0}


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def oku(yol):
    with open(yol, encoding='utf-8') as f:
        return f.read()


def sessiz_enjektor(**ek):
    varsayilan = dict(mdot_ox=1.2, chamber_pressure=20.0, tank_pressure=50.0,
                      oxidizer_temp=293.0, oxidizer_type='n2o')
    varsayilan.update(ek)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return uid.InjectorDesign(**varsayilan)


# ===========================================================================
# P10B2-04 (KRİTİK) — ΔP/Pc paydası GERÇEK kamara basıncı
# ===========================================================================
def test_dp_pc_paydasi_UYDURULMUYOR_gercek_Pc_kullaniliyor():
    """ÖLÇÜLEN KUSUR: payda her koşumda 20 bar'dı.

    ``validate_injector_data`` içinde ``data.get('chamber_pressure', 20)``
    yazıyordu ve çağıranın verdiği ``injector_results`` sözlüğünde böyle bir
    anahtar HİÇ YOKTU. Ölçülen sonuç (28 Ağustos 2026):

        Pc = 40 bar, ΔP = 8 bar -> gerçek oran 0,20 (SP-8089'un tam
        önerdiği değer) ama basılan oran 0,40 ve SAHTE bir 'dp_pc_high'
        uyarısı.
    """
    rapor = validator.comprehensive_validation(
        {'chamber_pressure': 40.0}, {'pressure_drop': 8.0}, 'n2o_htpb')
    kunye = rapor['injector_assessment']['pressure_drop_ratio']
    assert kunye['status'] == 'evaluated'
    assert kunye['chamber_pressure_bar'] == pytest.approx(40.0)
    assert kunye['ratio'] == pytest.approx(0.20, abs=1e-9), (
        'oran gerçek Pc ile kurulmuyor (uydurma payda geri gelmiş olabilir)')
    kodlar = [w['code'] for w in
              rapor['critical_warnings'] + rapor['regular_warnings']]
    assert 'warn.validation.dp_pc_high' not in kodlar, (
        'sağlıklı bir tasarımda sahte dp_pc_high uyarısı yandı: ' + str(kodlar))
    assert 'warn.validation.dp_pc_low' not in kodlar


def test_dusuk_dp_gercekten_KRITIK_basiyor():
    """Payda doğruyken gerçek chug riski artık sessiz kalmaz."""
    rapor = validator.comprehensive_validation(
        {'chamber_pressure': 50.0}, {'pressure_drop': 4.0}, 'n2o_htpb')
    kodlar = [w['code'] for w in rapor['critical_warnings']]
    assert 'warn.validation.dp_pc_low' in kodlar, (
        'ΔP/Pc = 0,08 (bandın çok altında) kritik uyarı üretmedi')
    assert rapor['injector_assessment'][
        'pressure_drop_ratio']['ratio'] == pytest.approx(0.08, abs=1e-9)


def test_Pc_yoksa_hukum_VERILMEZ_ve_adiyla_beyan_edilir():
    """Fail-closed: payda çözülemiyorsa sayı uydurulmaz, hüküm geri çekilir.

    Girdi bilerek "başka her ekseni temiz" seçilir (isp/c*/gama/OF bandın
    içinde, Re ve çıkış hızı bandın içinde). Böylece TEK eksik şey ΔP/Pc
    paydasıdır: eski sözleşme burada ``validation_passed = True`` diyordu,
    yani hiç yapılmamış bir denetimi 'geçti' sayıyordu. Bu bekçi tam o
    fail-open'ı ölçer — başka bir kritik uyarı arkasına saklanamaz.

    ÖH V3 taban-c (14 Eki) — ÇAPA KAYDI: O/F 3,0 → 7,5. Berke kararı
    ``dfa28c46`` (ÖH fix-37a) n2o_htpb O/F doğrulama bandını
    (0,5-6,0) → (4,0-12,0) yaptı ("alt uç DARALDI: O/F 2,5 artık uyarı
    alıyor"); 3,0 yeni bandın DIŞINDA kaldığı için girdi artık "temiz"
    değildi (``warn.validation.of_out_of_range``) ve bekçi asıl ölçtüğü
    fail-open'a ulaşamadan düşüyordu. 7,5 aynı kararın adıyla andığı
    sayfa varsayılanıdır (N₂O/HTPB tepe O/F 7-8 literatür künyesi, bandın
    İÇİ). Niyet aynı: TEK eksik ΔP/Pc paydası; diğer eksenler değişmedi.
    """
    motor_temiz = {'isp': 200.0, 'c_star': 1500.0, 'gamma': 1.20,
                   'of_ratio': 7.5}
    enjektor_temiz = {'pressure_drop': 8.0, 'reynolds_number': 50000.0,
                      'exit_velocity': 30.0}
    rapor = validator.comprehensive_validation(
        motor_temiz, enjektor_temiz, 'n2o_htpb')
    assert rapor['critical_warnings'] == [] and rapor['regular_warnings'] == [], (
        'ölçüm çapası kaymış: bu girdi başka uyarı üretmemeliydi — '
        f"{rapor['critical_warnings']} {rapor['regular_warnings']}")
    kunye = rapor['injector_assessment']['pressure_drop_ratio']
    assert kunye['status'] == 'not_evaluated'
    assert kunye['ratio'] is None, 'ölçülemeyen eksen için sayı üretilmiş'
    assert 'chamber_pressure' in kunye['missing_inputs'], (
        'eksik alan ADIYLA söylenmiyor')
    assert rapor['axes_not_evaluated'] == ['pressure_drop_ratio']
    assert rapor['assessment_complete'] is False
    # Ölçülmeyen eksen 'geçti' diyemez ve yeşil rozet basamaz.
    assert rapor['validation_passed'] is False
    assert rapor['overall_status']['code'] != 'status.normal'


def test_dogrulama_uretilemezse_hukum_ADIYLA_GERI_CEKILIYOR(client,
                                                            monkeypatch):
    """``/calculate``'ın 'Validation report skipped' fail-open'ı kapandı.

    ÖLÇÜLEN KUSUR: rapor üretilemediğinde hata yalnız sunucu günlüğüne
    yazılıyor ve ``validation`` anahtarı yanıttan DÜŞÜYORDU. Kullanıcı
    tarafında bu, "doğrulama temiz" ile ayırt edilemeyen bir sessizlikti.
    Artık hüküm GERİ ÇEKİLİR ve geri çekildiği söylenir; uyarı dizileri
    KONMAZ (boş dizi 'denetlendi, temiz çıktı' demek olurdu).
    """
    import hrma.app as A

    def catlat(*a, **k):
        raise RuntimeError('kasitli catlak')

    monkeypatch.setattr(A.validator, 'comprehensive_validation', catlat)
    cevap = client.post('/calculate', json={
        'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0, 'fuel_type': 'htpb',
        'oxidizer_type': 'n2o', 'chamber_pressure': 20.0, 'l_star': 1.0,
        'expansion_ratio': 4.0})
    assert cevap.status_code == 200, 'hesap kırılmamalıydı (yalnız hüküm düşer)'
    dogrulama = cevap.get_json().get('validation')
    assert dogrulama is not None, 'geri çekilme SESSİZ kaldı (anahtar düştü)'
    assert dogrulama['status'] == 'not_evaluated'
    assert dogrulama['validation_passed'] is False
    assert dogrulama['error_type'] == 'RuntimeError'
    assert 'critical_warnings' not in dogrulama, (
        'ölçülmemiş denetim için boş uyarı dizisi basılmış (sahte gösterge)')
    assert 'regular_warnings' not in dogrulama


def test_uydurma_20_bar_varsayilani_kaynakta_YOK():
    """Kusurun biçimi geri gelmesin: ``get('chamber_pressure', <sayı>)`` yasak."""
    agac = ast.parse(oku(VALIDATION_PY), filename=VALIDATION_PY)
    suclu = []
    for dugum in ast.walk(agac):
        if not isinstance(dugum, ast.Call):
            continue
        fn = dugum.func
        if not (isinstance(fn, ast.Attribute) and fn.attr == 'get'):
            continue
        if len(dugum.args) != 2:
            continue
        anahtar, varsayilan = dugum.args
        if (isinstance(anahtar, ast.Constant)
                and anahtar.value == 'chamber_pressure'
                and isinstance(varsayilan, ast.Constant)
                and isinstance(varsayilan.value, (int, float))
                and varsayilan.value != 0):
            suclu.append((dugum.lineno, varsayilan.value))
    assert not suclu, (
        'kamara basıncı için SIFIRDAN FARKLI bir varsayılan geri gelmiş '
        f'(hüküm o sayıya bölünür): {suclu}')


# ===========================================================================
# P10B2-14 — ΔP/Pc bandı TEK KAYNAKTAN
# ===========================================================================
def test_dp_pc_bandinin_alt_siniri_TEK_KAYNAK_NESNESI():
    """Değer eşitliği YETMEZ — kusur tam olarak "aynı sayıyı iki yerde
    tutmak"tı. Kimlik ancak ithal edilmişse sağlanır."""
    alt, ust = validator.injector_limits['pressure_drop_ratio']
    assert alt is acoustic_modes.CHUG_DP_RATIO_MINIMUM, (
        'ΔP/Pc alt sınırı acoustic_modes\'tan ithal edilmiyor (kopya geri '
        f'gelmiş olabilir): {alt!r}')
    assert alt == 0.15, 'göç sessiz sayı değişikliği DEĞİLDİR'
    # Üst sınır ayrı gerekçelidir (besleme maliyeti); chug eşiği değildir.
    assert ust is vs.INJECTOR_DP_PC_CEILING
    assert ust != acoustic_modes.CHUG_DP_RATIO_MINIMUM


#: Bu dosyada mekanik olarak 0,15/0,20 taşıyan AMA chug ΔP/Pc kuralı OLMAYAN
#: geçişler. Gerekçesiz muafiyet yoktur (kardeş bekçinin INJ_SEMANTIK_DISI
#: sözleşmesiyle aynı biçim).
VS_SEMANTIK_DISI = {
    'hole_diameter': 'enjektör deliği çapı alt sınırı [mm] — basınç oranı değil',
}


def test_esik_degeri_validation_system_icinde_YENIDEN_DOGMADI():
    """0,15/0,20 bu dosyada SAYI olarak bir daha yazılamaz (AST).

    Sahip çözümü sözlük anahtarından yapılır: ``'hole_diameter': (0.2, 5.0)``
    bandındaki 0,2 bir MİLİMETRE'dir, chug oranı değildir — muafiyeti
    ADIYLA kayıtlıdır.
    """
    kaynak = oku(VALIDATION_PY)
    agac = ast.parse(kaynak, filename=VALIDATION_PY)
    satirlar = kaynak.split('\n')
    ebeveyn = {}
    for ust in ast.walk(agac):
        for cocuk in ast.iter_child_nodes(ust):
            ebeveyn[cocuk] = ust
    suclu = []
    for dugum in ast.walk(agac):
        if not isinstance(dugum, ast.Constant):
            continue
        if isinstance(dugum.value, bool) or not isinstance(
                dugum.value, (int, float)):
            continue
        if not any(abs(dugum.value - h) < 1e-12 for h in (0.15, 0.20)):
            continue
        # Sahip: en yakın sözlük anahtarı ya da atama adı.
        sahip, n = None, dugum
        while n in ebeveyn:
            ust = ebeveyn[n]
            if isinstance(ust, ast.Dict):
                for anahtar, deger in zip(ust.keys, ust.values):
                    if deger is n and isinstance(anahtar, ast.Constant):
                        sahip = str(anahtar.value)
                break
            if isinstance(ust, ast.Assign):
                for hedef in ust.targets:
                    if isinstance(hedef, ast.Name):
                        sahip = hedef.id
                break
            n = ust
        if sahip in VS_SEMANTIK_DISI:
            continue
        suclu.append((dugum.lineno, sahip,
                      satirlar[dugum.lineno - 1].strip()[:80]))
    assert not suclu, (
        'chug eşiği validation_system.py içinde SAYI olarak yaşıyor — tek '
        f'tanım yeri hrma/analysis/acoustic_modes.py: {suclu}')


def test_bant_kunyesi_kaynagi_ADIYLA_soyluyor():
    """Künye kazanılır: bandın nereden geldiği raporda yazılı olmalı."""
    rapor = validator.comprehensive_validation(
        {'chamber_pressure': 20.0}, {'pressure_drop': 4.0}, 'n2o_htpb')
    kaynak = rapor['injector_assessment']['pressure_drop_ratio']['band_source']
    assert 'CHUG_DP_RATIO_MINIMUM' in kaynak
    assert 'INJECTOR_DP_PC_CEILING' in kaynak
    assert 'not a stability criterion' in kaynak, (
        'üst sınırın chug ölçütü OLMADIĞI beyanı düşmüş')


def test_HRMA_kendi_varsayilan_hibridi_KENDI_dogrulayicisini_geciyor(client):
    """P10B2-14'ün ürün ayağı: eskiden kendi varsayılanı kendi limitini
    geçemiyordu (payda 20 sabitken Pc≠20 olan her tasarım ya sahte yüksek
    ya sahte düşük çıkıyordu)."""
    for pc in (10.0, 20.0, 40.0):
        govde = {'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
                 'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
                 'chamber_pressure': pc, 'l_star': 1.0,
                 'expansion_ratio': 4.0, 'tank_pressure': 2.0 * pc + 10.0}
        cevap = client.post('/calculate', json=govde)
        assert cevap.status_code == 200, (pc, cevap.status_code)
        dogrulama = cevap.get_json()['validation']
        kunye = dogrulama['injector_assessment']['pressure_drop_ratio']
        assert kunye['status'] == 'evaluated', (pc, kunye)
        assert kunye['chamber_pressure_bar'] == pytest.approx(pc), (
            f'Pc={pc} koşumunda payda motorun kendi basıncı değil: {kunye}')
        kodlar = [w['code'] for w in dogrulama['critical_warnings']]
        assert 'warn.validation.dp_pc_low' not in kodlar, (
            f'HRMA kendi varsayılan hibridini Pc={pc} bar\'da chug-riskli '
            f'ilan etti: {kunye}')


# ===========================================================================
# P10B1-21 — psat kritik nokta üstünde SAYI ÜRETMEZ
# ===========================================================================
def test_kritik_nokta_ustunde_buhar_basinci_URETILMEZ():
    """ÖLÇÜLEN KUSUR (28 Ağustos 2026): T = 1000 K'de p_vapor_bar = 50,525
    (293,15 K'nin doyma basıncı) ve kullanıcıya giden cümle
    "P_v = 50.5 bar at 1000 K" idi. N₂O kritik sıcaklığı 309,52 K."""
    enj = sessiz_enjektor(oxidizer_temp=1000.0, oxidizer_density=800.0)
    assert enj.p_vapor_bar is None, (
        'kritik nokta üstünde buhar basıncı sayısı üretilmiş: '
        f'{enj.p_vapor_bar}')
    gerekce = enj.p_vapor_unavailable_reason
    assert gerekce and '309.52' in gerekce, (
        'geri çekilme gerekçesi kritik sıcaklığı ADIYLA söylemiyor: '
        f'{gerekce}')


def test_buhar_basinci_yokken_hukumler_GERI_CEKILIYOR():
    """Sayı yoksa hüküm de yok: ne "kavitasyon riski var" ne "yok"."""
    enj = sessiz_enjektor(oxidizer_temp=1000.0, oxidizer_density=800.0)
    uyarilar = enj._check_warnings(30.0, 50000.0)
    kavitasyon = [u for u in uyarilar if 'Cavitation' in u]
    flas = [u for u in uyarilar if 'Flash boiling' in u]
    assert kavitasyon and 'NOT evaluated' in kavitasyon[0]
    assert flas and 'NOT evaluated' in flas[0]
    # Uydurma sayı hiçbir cümleye giremez.
    metin = ' '.join(uyarilar)
    assert 'P_v = ' not in metin, (
        'geri çekilmiş hükümde yine bir buhar basıncı sayısı basılmış: '
        + metin)
    assert str(uid.N2O_PSAT_FALLBACK_BAR) not in metin


def test_buhar_basinci_kunyesi_RAPORDA_yayimlaniyor():
    """Kullanılan (ya da kullanılamayan) P_v ürün çıktısında görünür.

    P10B1-22 düzeltmesi kavitasyon uyarısındaki YANLIŞ-POZİTİFLERİ
    söndürdüğü için, o cümleye binmiş olan "P_v şu kadardı" bilgisi
    depolanabilir sıvılarda görünmez kalırdı. Künye artık uyarıya değil
    RAPORA bağlı ve kardeş modülle aynı anahtarları taşıyor.
    """
    for ox, beklenen in (('h2o2', uid.VAPOR_PRESSURE_ASSUMED_BAR),
                         ('n2o4', uid.VAPOR_PRESSURE_ASSUMED_BAR)):
        enj = sessiz_enjektor(oxidizer_type=ox, tank_pressure=70,
                              oxidizer_temp=293.15)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            rapor = enj.calculate()
        assert rapor['vapor_pressure_bar'] == pytest.approx(beklenen)
        assert 'assumed' in rapor['vapor_pressure_basis'], (
            f'{ox}: varsayım "varsayıldı" demeden veriliyor -> '
            + str(rapor['vapor_pressure_basis']))
        assert repr(ox) in rapor['vapor_pressure_basis']

    # Geri çekilen hâlde SAYI yoktur ama GEREKÇE vardır.
    yok = sessiz_enjektor(oxidizer_temp=1000.0, oxidizer_density=800.0)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        rapor_yok = yok.calculate()
    assert rapor_yok['vapor_pressure_bar'] is None
    assert 'not defined at 1000.00 K' in rapor_yok['vapor_pressure_basis']


def test_bant_ici_sicaklikta_psat_ve_kunye_YERINDE():
    """Fail-closed sağlıklı yolu kesmiyor: 250-300 K aralığı çalışıyor."""
    for T, beklenen in ((250.0, 16.35), (293.0, 50.37)):
        enj = sessiz_enjektor(oxidizer_temp=T)
        assert enj.p_vapor_bar == pytest.approx(beklenen, abs=0.05)
        assert 'saturation curve' in enj.p_vapor_basis
        assert f'{T:.2f} K' in enj.p_vapor_basis


# ===========================================================================
# P10B1-22 — Nurick K_c enjektörün KENDİ istasyonundan
# ===========================================================================
def test_Kc_paydasi_boyutlandirilan_deltaP_ile_TUTARLI():
    """ÖLÇÜLEN KUSUR: payda ``P_tank − P_c``, yani orifisin üstündeki basınç
    tank basıncı sanılıyordu; oysa delik ``delta_P_inj`` ile
    BOYUTLANDIRILMIŞTI. T = 250 K'de eski hüküm K_c = 1,12 (uyarı yanıyor),
    enjektörün kendi istasyonuyla K_c = 1,91 (uyarı gerekmiyor)."""
    enj = sessiz_enjektor(oxidizer_temp=250.0)
    assert enj.delta_P_inj == pytest.approx(4.0)
    assert enj.injector_inlet_pressure_bar == pytest.approx(
        enj.P_c + enj.delta_P_inj)
    k_c = ((enj.injector_inlet_pressure_bar - enj.p_vapor_bar)
           / enj.delta_P_inj)
    assert k_c == pytest.approx(1.912, abs=0.01)
    eski = ((enj.P_tank - enj.p_vapor_bar)
            / max(enj.P_tank - enj.P_c, 1e-9))
    assert eski == pytest.approx(1.122, abs=0.01), 'ölçüm çapası kaymış'
    uyarilar = [u for u in enj._check_warnings(30.0, 50000.0)
                if 'Cavitation' in u]
    assert not uyarilar, (
        'enjektör girişiyle tutarlı K_c 1,5 eşiğinin ÜSTÜNDEYKEN uyarı '
        f'yandı (eski payda geri gelmiş olabilir): {uyarilar}')


def test_Kc_esigi_DEGISMEDI():
    """Yeni eşik icat edilmedi: yalnız istasyon düzeltildi."""
    assert uid.NURICK_KC_LIMIT == 1.5


def test_gercek_kavitasyonda_uyari_HALA_yaniyor_ve_istasyonu_ADLI():
    """Doymuş N₂O'da (P₁ < P_v) hüküm korunur ve sayının hangi istasyona
    ait olduğu cümlede yazar."""
    enj = sessiz_enjektor(oxidizer_temp=293.0)
    uyarilar = [u for u in enj._check_warnings(30.0, 50000.0)
                if 'Cavitation risk' in u]
    assert uyarilar, '293 K doymuş N₂O\'da kavitasyon uyarısı düştü'
    metin = uyarilar[0]
    assert 'injector inlet P_1' in metin, (
        'hangi istasyonun basıncı kullanıldığı cümlede yok: ' + metin)
    assert 'dP = ' in metin


def test_besleme_sinirli_dalda_iki_bicim_AYNI_sayiyi_veriyor():
    """``delta_P_inj = P_tank − P_c`` olan dalda eski ve yeni biçim
    özdeştir — bu, düzeltmenin bir eşik kayması DEĞİL istasyon düzeltmesi
    olduğunun kanıtıdır."""
    enj = sessiz_enjektor(chamber_pressure=30.0, tank_pressure=31.0,
                          oxidizer_temp=250.0)
    assert enj.delta_P_inj == pytest.approx(enj.P_tank - enj.P_c)
    yeni = ((enj.injector_inlet_pressure_bar - enj.p_vapor_bar)
            / enj.delta_P_inj)
    eski = ((enj.P_tank - enj.p_vapor_bar)
            / max(enj.P_tank - enj.P_c, 1e-9))
    assert yeni == pytest.approx(eski, rel=1e-12)


def test_Kc_kardes_modulle_AYNI_sozlesmede():
    """engines/injector_design.py ``dp = P₁ − Pc`` ve
    ``K_c = (P₁ − P_v)/(P₁ − Pc)`` kuruyor. utils artık aynı istasyondan
    çalışıyor: iki modül aynı girdide aynı sayıyı vermeli."""
    enj = sessiz_enjektor(oxidizer_temp=250.0)
    p1 = enj.injector_inlet_pressure_bar
    kardes = (p1 - enj.p_vapor_bar) / max(p1 - enj.P_c, 1e-9)
    bizim = (p1 - enj.p_vapor_bar) / max(enj.delta_P_inj, 1e-9)
    assert bizim == pytest.approx(kardes, rel=1e-12)


# ===========================================================================
# P10B1-25 — plaka hedef emniyet katsayısı DENETLENİYOR
# ===========================================================================
def _plaka(sf):
    return injector_plate_structural(
        delta_P_bar=4.0, plate_diameter_m=0.1, material_props=CELIK,
        material_name='AISI 4130', plate_thickness_m=0.006,
        n_holes=12, hole_diameter_m=0.0015, required_sf=sf)


@pytest.mark.parametrize('sf', [-1.0, -0.001, 0.0, 0, float('nan'),
                                float('inf'), True, False, 'abc', [2.0]])
def test_gecersiz_hedef_SF_ADIYLA_reddediliyor(sf):
    """ÖLÇÜLEN KUSUR: ``safety_factor = -1`` -> status 'analyzed',
    required_safety_factor -1.0, required_thickness_mm NaN (JSON'da null),
    warnings []. ``safety_factor = 0`` ise SESSİZCE 2,0 oluyordu."""
    with pytest.raises(InjectorPlateInputError) as hata:
        _plaka(sf)
    assert "'safety_factor'" in str(hata.value), (
        'ret gerekçesi alanı ADIYLA söylemiyor: ' + str(hata.value))


def test_gecerli_SF_kunyesiyle_gecıyor():
    kullanici = _plaka(3.0)
    assert kullanici['required_safety_factor'] == pytest.approx(3.0)
    assert kullanici['required_safety_factor_source'] == 'user'
    assert math.isfinite(kullanici['required_thickness_mm'])
    varsayilan = _plaka(None)
    assert varsayilan['required_safety_factor'] == pytest.approx(
        uid.INJECTOR_PLATE_DEFAULT_SF)
    assert varsayilan['required_safety_factor_source'] == 'default', (
        'varsayılan ile kullanıcının sayısı künyede ayrışmıyor')


def test_hicbir_raporda_NaN_kalinlik_YOK():
    """Geçersiz SF artık rapora hiç ulaşamaz; ulaşsaydı NaN üretirdi."""
    for sf in (0.5, 1.0, 2.0, 6.0):
        r = _plaka(sf)
        assert math.isfinite(r['required_thickness_mm'])
        assert r['required_thickness_mm'] > 0


def test_uc_gecersiz_SF_icin_ADLI_422_donuyor(client):
    """Doktrin: istemci girdisi hatası adlı 4xx'tir; 200 + NaN değil."""
    govde = {'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
             'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
             'chamber_pressure': 20.0, 'l_star': 1.0, 'expansion_ratio': 4.0,
             'injector_material': 'steel_4130'}
    for bozuk in (-1, 0, 'abc'):
        cevap = client.post('/calculate', json=dict(govde, safety_factor=bozuk))
        assert cevap.status_code == 422, (bozuk, cevap.status_code)
        govde_json = cevap.get_json()
        alanlar = [a['field'] for a in govde_json.get('invalid_fields', [])]
        assert alanlar == ['safety_factor'], (bozuk, govde_json)
    # Geçerli SF aynı istekte 200 döner (kapı sağlıklı yolu kesmiyor).
    iyi = client.post('/calculate', json=dict(govde, safety_factor=2.0))
    assert iyi.status_code == 200
    plaka = iyi.get_json()['injector']['plate_structural']
    assert plaka['required_safety_factor_source'] == 'user'


# ===========================================================================
# P10B1-10 — _check_warnings eşiği ithal ediyor (AST; karar+metin mutasyonu
# tests/test_enjektor_sozlesme_borclari.py::
# test_check_warnings_KARARI_ve_METNI_esikten_TURETILIYOR içinde)
# ===========================================================================
def test_check_warnings_icinde_ciplak_esik_literali_YOK():
    kaynak = oku(UTILS_INJ_PY)
    agac = ast.parse(kaynak, filename=UTILS_INJ_PY)
    hedef = None
    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.FunctionDef) and dugum.name == '_check_warnings':
            hedef = dugum
            break
    assert hedef is not None, '_check_warnings bulunamadı (ad değişmiş)'
    suclu = []
    for dugum in ast.walk(hedef):
        if isinstance(dugum, ast.Constant):
            if isinstance(dugum.value, bool):
                continue
            if isinstance(dugum.value, (int, float)) and any(
                    abs(dugum.value - h) < 1e-12 for h in (0.15, 0.20)):
                suclu.append(('sayı', dugum.lineno, dugum.value))
            if isinstance(dugum.value, str) and re.search(r'\d+\s*%',
                                                          dugum.value):
                suclu.append(('dize', dugum.lineno, dugum.value[:50]))
    assert not suclu, (
        '_check_warnings eşiği yine kendi içinde taşıyor (karar ya da '
        f'metin): {suclu}')
