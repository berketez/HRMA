"""
hrma/analysis/flight_vehicle.py + hrma/utils/projects.py airframe testleri.

Kapsam:
  1. normalize() — üç motor tipi (hybrid/solid/liquid) için sentetik sonuç
     sözlüğü -> tek uçan-araç şeması. BİRİM doğruluğu (hybrid OD metre / solid+
     liquid OD milimetre-> metre), thrust_curve kaynağı, ad çözümü.
  2. ÇİFT-SAYIM (spec TUZAK2): engine_inert_mass HER tipte propelanı DIŞLAR.
  3. recompute_from_project() — .hrma girdilerinden gerçek motoru yeniden
     hesaplama (katı motor, çevrimdışı/hızlı) + dispatch redleri.
  4. projects.py airframe gidiş-dönüşü (kaydet -> yükle -> byte-eşit) ve şema
     redleri (iç içe nesne / None reddi).

Sentetik sözlüklerdeki alan adları/birimleri motor sonuç dict'lerinden
(hrma/engines/*_rocket_engine.py) DOĞRUDAN türetilmiştir; kod değişirse bu
testler kırılmalıdır.

ÖH FAZ B-4 (bekçi dalgası, 27 Ağustos 2026)
-------------------------------------------
Bu dosya kampanyanın en kalabalık kusuru-koruyan bekçi kümesiydi (S2 §3.1,
9 kayıt). Ortak desen: bekçiler ÇEVRİMİ (mm→m) ve ŞEMAYI sınıyor, alanın
ANLAMINI sormuyordu; sentetik fikstürler ölçülen kusuru (iki kaynak, tank
kütlesi, künye/oran çelişkisi) hiç taşımadığı için kusur test ortamında
görünmez bile oluyordu. Bu dalgada:

  * suçlu iddialar taşındı — sabit çakması (``== 0.15`` / ``== 43.5`` /
    ``== 0.209``) yerine SÖZLEŞME iddiası yazıldı; böylece doğru onarım
    testi kırmak zorunda kalmıyor, yanlış onarım hâlâ kırıyor;
  * bugün ürün kusuru yüzünden kırmızıya düşen bekçiler
    ``xfail(strict=True)`` + defter kimliğiyle BORÇ İMİ olarak duruyor
    (depoda tescilli desen; onarım dalgası imi kaldıracak — im kalkmazsa
    strict kip XPASS ile bağırır).

İlgili defter kalemleri: P4B3-04 (recompute sessiz varsayılanları),
P4B3-08 (hibrit engine_od_m = kamara deliği), P4B3-09 (sıvı iki toplam
boydan kısası), P4B3-19 (hibrit künye 27,37× yalan), P4B3-20 (sıvı atıl
kütle tankları dışlıyor), P15B2-02 (ikiz ``_mm_to_m``; negatif mm → 200 +
``engine_od_m = −120,0``).
"""

import re

import pytest

from hrma.analysis import flight_vehicle as fv
from hrma.utils import projects as store


# ---------------------------------------------------------------------------
# ÖLÇÜLEN GERÇEK MOTOR DEĞERLERİ (fikstürleri gerçeğe çapalar)
# ---------------------------------------------------------------------------
# Kaynak: docs/scofield/raw/P04/B3-repro-05.py koşumları + 27 Ağu 2026 canlı
# yeniden ölçüm. Sentetik fikstürler bu sayıları taşımadığı sürece ölçülen
# kusurlar test ortamında GÖRÜNMEZ (kampanyanın kör-fikstür deseni).

# 3 kN N2O/HTPB hibrit (P4B3-19): künye "~0,25 × propelan" diyor.
OLCULEN_HIBRIT_PROP_KG = 7.9590
OLCULEN_HIBRIT_INERT_KG = 54.4513          # gerçek yapısal hesaptan
# 3 kN hibrit kamara (P4B3-08): iç çap + cidar → gerçek kasa dış çapı.
OLCULEN_HIBRIT_KAMARA_MM = 112.214
OLCULEN_HIBRIT_CIDAR_MM = 11.709
# 10 kN LOX/RP-1 sıvı (P4B3-09 / P4B3-20).
OLCULEN_SIVI_UZUNLUK_KISA_MM = 209.49855160897653   # key_dimensions (yakınsak DÜŞMÜŞ)
OLCULEN_SIVI_UZUNLUK_TAM_M = 0.2708577429354722     # component_sizing (METRE)
OLCULEN_SIVI_MOTOR_KURU_KG = 43.50319619781663
OLCULEN_SIVI_TANK_KG = 77.95481798301827
OLCULEN_SIVI_PROP_NOMINAL_KG = 1025.28430345157
OLCULEN_SIVI_PROP_YUKLENEN_KG = 1179.0769489693052

#: Künye metninin ilan ettiği oranı ("~0.25 x propellant mass") çeker.
_KUNYE_ORAN = re.compile(r'~?\s*([0-9]*\.?[0-9]+)\s*[x×]\s*propellant',
                         re.IGNORECASE)

#: "Girdi yerine varsayılan kondu" beyanını arayan sözcük süzgeci.
_IKAME_SOZCUK = re.compile(
    r'default|missing|substitut|assum|eksik|varsay|not_supplied', re.I)


def kunye_orani(note):
    """Künye metnindeki 'propelanın X katı' iddiasını sayı olarak döndür."""
    if not isinstance(note, str):
        return None
    m = _KUNYE_ORAN.search(note)
    return float(m.group(1)) if m else None


def ikame_beyani(results):
    """Sonuç sözlüğünde 'eksik girdi yerine varsayılan konuldu' beyanı ara.

    Alan adı ya da uyarı kodu düzeyinde arar; hiçbiri yoksa boş liste döner
    (= ikame SESSİZ yapılmış). Uydurma-veri-yasağının recompute tarafındaki
    karşılığı budur.
    """
    beyan = [k for k in results if _IKAME_SOZCUK.search(str(k))]
    for w in (results.get('warnings') or []):
        kod = w.get('code') if isinstance(w, dict) else w
        if _IKAME_SOZCUK.search(str(kod)):
            beyan.append(str(kod))
    return beyan


# ---------------------------------------------------------------------------
# Sentetik motor sonuç sözlükleri (gerçek şemaların minimal karşılıkları)
# ---------------------------------------------------------------------------

def hybrid_results(**over):
    """/calculate hibrit yanıtı: motor alt-sözlüğü sarmalı.

    Gerçek anahtarlar: motor.thrust (:997), motor.burn_time (:1041),
    motor.propellant_mass_total (:1032), motor.chamber_diameter (:1013, METRE),
    motor.design_summary.key_dimensions.{dry_mass_estimate_kg (:1242, =0.25*prop),
    total_motor_length_mm (:1240)}, motor.transient {time, thrust}.
    """
    motor = {
        'thrust': 5000.0,
        'burn_time': 8.0,
        'propellant_mass_total': 12.0,
        'chamber_diameter': 0.15,  # METRE (self.D_ch)
        'transient': {
            'time': [0.0, 1.0, 2.0, 3.0, 4.0],
            'thrust': [100.0, 200.0, 300.0, 200.0, 100.0],
        },
        'design_summary': {
            'key_dimensions': {
                'dry_mass_estimate_kg': 3.0,       # = 0.25 * 12.0
                'total_motor_length_mm': 1200.0,   # mm
            },
        },
    }
    motor.update(over.pop('motor', {}))
    doc = {'motor': motor}
    doc.update(over)
    return doc


def solid_results(**over):
    """/calculate_solid yanıtı: düz (top-level) sözlük.

    Gerçek anahtarlar: average_thrust (:4357), burn_time (:4356),
    propellant_mass (:4363), thrust_curve {time, thrust, ...} (:4381),
    design_summary.masses.dry_mass_kg (:4322), design_summary.key_dimensions.
    total_length_mm (:4306), cad_design.case_design.outer_diameter (:2483, MM).
    """
    r = {
        'average_thrust': 6800.0,
        'burn_time': 2.2,
        'propellant_mass': 6.5,
        'chamber_diameter': 100.0,  # MM
        'thrust_curve': {
            'time': [0.0, 0.5, 1.0, 1.5, 2.0],
            'thrust': [7000.0, 6900.0, 6800.0, 6700.0, 500.0],
            'pressure': [40.0, 39.0, 38.0, 37.0, 5.0],
        },
        'cad_design': {'case_design': {'outer_diameter': 116.0}},  # MM
        'design_summary': {
            'masses': {'dry_mass_kg': 5.5, 'propellant_mass_kg': 6.5},
            'key_dimensions': {'total_length_mm': 773.0},           # mm
        },
    }
    r.update(over)
    return r


def liquid_results(**over):
    """/calculate_liquid yanıtı: düz (top-level) sözlük.

    Gerçek anahtarlar: thrust (:3625), burn_time (:3702), chamber_diameter
    (:3658, MM), total_mass_flow (:3648), design_summary.masses.
    {propellant_mass_kg (:3770), engine_mass_kg (:3766)}, design_summary.
    key_dimensions.overall_length_mm (:3763), feed_system.total_mass (:1225).
    """
    r = {
        'thrust': 10000.0,
        'burn_time': 300.0,
        'chamber_diameter': 99.2,   # MM
        'total_mass_flow': 3.4,
        'engine_mass_estimate': 43.5,
        'feed_system': {'total_mass': 18.0},  # ALT KÜME (feed+turbopump)
        'design_summary': {
            'masses': {
                'propellant_mass_kg': 1025.0,
                'engine_mass_kg': 43.5,        # TAM motor kuru kütlesi
            },
            'key_dimensions': {'overall_length_mm': 209.0},  # mm
        },
    }
    r.update(over)
    return r


# ---------------------------------------------------------------------------
# 1. normalize — hibrit
# ---------------------------------------------------------------------------

class TestNormalizeHybrid:
    def test_schema_and_values(self):
        v = fv.normalize('hybrid', hybrid_results(), motor_name='H1')
        assert v['motor_type'] == 'hybrid'
        assert v['motor_name'] == 'H1'
        assert v['source'] == 'results'
        assert v['thrust'] == 5000.0
        assert v['burn_time'] == 8.0
        assert v['propellant_mass'] == 12.0
        assert v['engine_inert_mass'] == 3.0

    def test_od_stays_in_meters_no_division(self):
        """BİRİM kapısı: hibritte chamber_diameter METRE, ortak /1000 YOK.

        ÖH B-4 (defter P4B3-08) — eski hâli tek bir ``== 0.15`` çakmasıydı ve
        o eşitlik BİRİM sorusunun yanında ANLAM sorusunu da dondurmuştu:
        "dış çap alanına kamara DELİĞİNİ koymak doğrudur" hükmü testin içine
        gömülüydü (ölçüldü: yayımlanan 112,214 mm ⟷ gerçek kasa dış çapı
        135,632 mm, −%17,3). İddia birim sorusuna indirgendi; anlam sorusunu
        ``test_od_kasa_dis_capidir`` sorar (bugün xfail borç imiyle).
        """
        v = fv.normalize('hybrid', hybrid_results())
        kamara_m = 0.15                       # fikstürün chamber_diameter'ı
        assert v['engine_od_m'] is not None
        # (a) mm sanılıp 1000'e BÖLÜNMEMİŞ
        assert v['engine_od_m'] != pytest.approx(kamara_m / 1000.0)
        # (b) metre sanılıp 1000 ile ÇARPILMAMIŞ (mm sızıntısı)
        assert v['engine_od_m'] < 10.0 * kamara_m
        # (c) dış çap kamara deliğinden küçük olamaz (onarım bunu BÜYÜTÜR)
        assert v['engine_od_m'] >= kamara_m

    def test_od_kasa_dis_capidir(self):
        """``engine_od_m`` ADI gereği DIŞ çaptır: iç çap + 2×cidar.

        Şema beyanı (flight_vehicle.py:23) 'motor dış çapı [m]' diyor ve katı
        kol gerçekten dış çapı koyuyor. Fikstür ölçülen yapısal bloğu taşır
        (``structural_analysis.chamber_analysis`` — structural_analysis.py:983
        ``wall_thickness_used_mm`` / :1035 ``diameter``), böylece iki anlamın
        farkı test ortamında GÖRÜNÜR olur.

        ÖH Z5S / PK2 ONARILDI (defter P4B3-08) — xfail borç imi SÖKÜLDÜ.
        ÖNCE: hibrit ``engine_od_m`` kamara DELİĞİNİ yayımlıyordu
        (``_num(eng["chamber_diameter"])``) oysa kardeş katı kol aynı alana
        kasa DIŞ çapını koyuyordu (cad_design.case_design.outer_diameter).
        Ölçüldü (3 kN N2O/HTPB): yayımlanan 112,214 mm ⟷ gerçek dış çap
        135,632 mm (iç çap + 2×11,709 mm cidar), −%17,3; launch_site.html
        bu sayıyı gövde çapının ALT SINIRI olarak ön-dolduruyordu → S_ref
        %46,1 eksik, apoje +%2,27 iyimser.
        SONRA: ``_hybrid_outer_diameter_m`` dış çapı yapısal bloktan kuruyor;
        bu fikstürde 0,135632 m. Yapısal blok YOKSA cidar UYDURULMAZ, kamara
        çapına düşülür (bugünkü davranış korunur).
        """
        ic_cap_m = OLCULEN_HIBRIT_KAMARA_MM / 1000.0
        cidar_m = OLCULEN_HIBRIT_CIDAR_MM / 1000.0
        doc = hybrid_results(motor={
            'chamber_diameter': ic_cap_m,          # METRE (self.D_ch)
            'structural_analysis': {'chamber_analysis': {
                'diameter': OLCULEN_HIBRIT_KAMARA_MM,        # mm, İÇ çap
                'wall_thickness_used_mm': OLCULEN_HIBRIT_CIDAR_MM,
            }},
        })
        v = fv.normalize('hybrid', doc)
        gercek_od_m = ic_cap_m + 2.0 * cidar_m     # 0,135632 m
        assert v['engine_od_m'] > ic_cap_m, (
            f"engine_od_m {v['engine_od_m']:.6f} m kamara deliğine eşit — "
            f'cidar ({OLCULEN_HIBRIT_CIDAR_MM} mm) hiç sayılmamış')
        # Cidar en az bir kez sayılmış olmalı (onarım daha büyük bir dış çap
        # yayımlarsa — yalıtım/kaplama — iddia yine sağlanır).
        assert v['engine_od_m'] >= gercek_od_m - 1e-9, (
            f"engine_od_m {v['engine_od_m']:.6f} m < gerçek dış çap "
            f'{gercek_od_m:.6f} m')

    def test_length_mm_to_m(self):
        v = fv.normalize('hybrid', hybrid_results())
        assert v['engine_length_m'] == pytest.approx(1.2)

    def test_inert_flagged_estimate(self):
        """Tahmin bayrağı + künye VAR ve künye SAYIYLA TUTUYOR.

        ÖH B-4 (defter P4B3-19) — eski hâli künyenin BOŞ OLMADIĞINI sınıyordu
        (``assert v['engine_inert_mass_note']``), içeriğinin yayımlanan sayıyla
        tutup tutmadığını sormuyordu. Künye bir ORAN ilan ediyorsa (``~0.25 x
        propellant mass``) o oran ölçülebilir bir iddiadır: burada dürüst
        fikstürle (3,0 kg = 0,25 × 12,0 kg) sağlandığı gösterilir, gerçek
        motor sayılarıyla ise ``test_kunye_orani_sayiyla_tutar`` (xfail borç
        imi) ile ölçülür.
        """
        doc = hybrid_results()
        v = fv.normalize('hybrid', doc)
        assert v['engine_inert_mass_is_estimate'] is True
        assert v['engine_inert_mass_note']

        oran = kunye_orani(v['engine_inert_mass_note'])
        assert oran is not None, (
            'künye bir ORAN ilan etmiyor: ' + repr(v['engine_inert_mass_note']))
        assert v['engine_inert_mass'] == pytest.approx(
            oran * v['propellant_mass'], rel=1e-9), (
            f"künye {oran} × propelan diyor ({oran * v['propellant_mass']:.4f} "
            f"kg) ama yayımlanan atıl kütle {v['engine_inert_mass']:.4f} kg")

    def test_kunye_orani_sayiyla_tutar(self):
        """Künyenin ilan ettiği oran GERÇEK motor sayılarında da tutmalı.

        Fikstür ölçülen motoru taşır (kampanyanın kör-fikstür deseninin
        kırılması): künye ya sayıyla tutar ya da o oranı ilan ETMEZ.

        ÖH Z5S / PK2 ONARILDI (defter P4B3-19) — xfail borç imi SÖKÜLDÜ.
        ÖNCE: künye SABİT metindi ("estimated as ~0.25 x propellant mass")
        oysa değer motorun gerçek yapısal hesabından
        (structural_analysis.weight_analysis.total_weight) geliyordu.
        Ölçüldü (3 kN N2O/HTPB): propelan 7,9590 kg, atıl kütle 54,4513 kg,
        künyenin vaadi 1,9897 kg → ORAN 27,37× (fark +52,462 kg);
        launch_site.html cümleyi ekrana basıyordu ve kullanıcı 54 kg'ı
        abartı sanıp aşağı çekerse uçuş çözümü tehlikeli iyimserleşiyordu.
        SONRA: künye yayımlanan sayıdan üretiliyor (``_hybrid_inert_note``).
        Bu fikstürde artık oran İDDİA EDİLMİYOR: 'dry mass computed by the
        motor structural model, NOT the 0.25 rule of thumb; measured
        dry/propellant ratio 6.84'. Kural gerçekten tutuyorsa (3,0 = 0,25 ×
        12,0) eski cümle aynen yazılır — bkz. ``test_inert_flagged_estimate``.
        """
        doc = hybrid_results(motor={
            'propellant_mass_total': OLCULEN_HIBRIT_PROP_KG,
            'design_summary': {'key_dimensions': {
                'dry_mass_estimate_kg': OLCULEN_HIBRIT_INERT_KG,
                'total_motor_length_mm': 1294.7,
            }},
        })
        v = fv.normalize('hybrid', doc)
        oran = kunye_orani(v['engine_inert_mass_note'])
        if oran is None:            # künye artık oran ilan etmiyorsa dürüst
            return
        assert v['engine_inert_mass'] == pytest.approx(
            oran * v['propellant_mass'], rel=0.05), (
            f"künye {oran} × propelan = "
            f"{oran * v['propellant_mass']:.4f} kg diyor; yayımlanan "
            f"{v['engine_inert_mass']:.4f} kg → "
            f"{v['engine_inert_mass'] / (oran * v['propellant_mass']):.2f}× "
            'yalan künye')

    def test_thrust_curve_from_transient(self):
        v = fv.normalize('hybrid', hybrid_results())
        assert v['thrust_curve'] is not None
        assert v['thrust_curve']['time'] == [0.0, 1.0, 2.0, 3.0, 4.0]
        assert v['thrust_curve']['thrust'][2] == 300.0

    def test_no_transient_yields_null_curve(self):
        doc = hybrid_results()
        doc['motor'].pop('transient')
        v = fv.normalize('hybrid', doc)
        assert v['thrust_curve'] is None

    def test_unwrapped_motor_dict_also_accepted(self):
        """Sarmalı olan ve olmayan girdi AYNI aracı vermeli.

        ÖH B-4 (defter P4B3-08) — eski hâli iki sabit çakmasıydı
        (``thrust == 5000.0``, ``engine_od_m == 0.15``) ve ikincisi kamara
        deliğini "dış çap" sayan hükmü İKİNCİ kez çapalıyordu. Testin gerçek
        sözleşmesi sabitler değil DENKLİK: ``/calculate`` sarmalı ile
        ``recompute``ın çıplak sözlüğü aynı araca inmelidir. Yeni iddia hem
        daha güçlü (12 alanın tamamı) hem de onarımdan bağımsız.
        """
        doc = hybrid_results()
        v_sarmal = fv.normalize('hybrid', doc)
        v_ciplak = fv.normalize('hybrid', hybrid_results()['motor'])
        assert v_ciplak == v_sarmal
        assert v_ciplak['thrust'] == 5000.0        # sarmalı sökme kaybetmedi
        assert v_ciplak['engine_od_m'] is not None


# ---------------------------------------------------------------------------
# 2. normalize — katı
# ---------------------------------------------------------------------------

class TestNormalizeSolid:
    def test_schema_and_values(self):
        v = fv.normalize('solid', solid_results(), motor_name='S1')
        assert v['motor_type'] == 'solid'
        assert v['thrust'] == 6800.0       # average_thrust
        assert v['burn_time'] == 2.2
        assert v['propellant_mass'] == 6.5
        assert v['engine_inert_mass'] == 5.5   # dry_mass_kg (propelan HARİÇ)

    def test_od_prefers_case_outer_diameter_mm_to_m(self):
        v = fv.normalize('solid', solid_results())
        assert v['engine_od_m'] == pytest.approx(0.116)  # 116 mm -> m

    def test_od_falls_back_to_chamber_diameter(self):
        r = solid_results()
        r.pop('cad_design')
        v = fv.normalize('solid', r)
        assert v['engine_od_m'] == pytest.approx(0.100)  # 100 mm -> m

    def test_length_mm_to_m(self):
        v = fv.normalize('solid', solid_results())
        assert v['engine_length_m'] == pytest.approx(0.773)

    def test_thrust_curve_extracts_time_thrust_only(self):
        v = fv.normalize('solid', solid_results())
        assert v['thrust_curve'] is not None
        assert set(v['thrust_curve'].keys()) == {'time', 'thrust'}
        assert len(v['thrust_curve']['time']) == 5

    def test_inert_not_estimate(self):
        v = fv.normalize('solid', solid_results())
        assert v['engine_inert_mass_is_estimate'] is False


# ---------------------------------------------------------------------------
# 3. normalize — sıvı
# ---------------------------------------------------------------------------

class TestNormalizeLiquid:
    def test_schema_and_values(self):
        v = fv.normalize('liquid', liquid_results(), motor_name='L1')
        assert v['motor_type'] == 'liquid'
        assert v['thrust'] == 10000.0
        assert v['burn_time'] == 300.0
        assert v['propellant_mass'] == 1025.0

    def test_thrust_curve_is_null(self):
        v = fv.normalize('liquid', liquid_results())
        assert v['thrust_curve'] is None

    def test_od_mm_to_m(self):
        v = fv.normalize('liquid', liquid_results())
        assert v['engine_od_m'] == pytest.approx(0.0992)

    def test_length_mm_to_m(self):
        """BİRİM kapısı — TEK kaynaklı fikstürde mm → m.

        ÖH B-4 KAPSAM BEYANI (defter P4B3-09): bu bekçi yalnız çevrimi ölçer.
        Gerçek sıvı yanıtında AYNI boy İKİ yerde yayımlanıyor
        (``design_summary.key_dimensions.overall_length_mm`` = 209,499 mm ⟷
        ``component_sizing.component_dimensions.overall_length`` = 0,270858 m,
        %+29,29) ve normalize sessizce KISA olanı seçiyor. Bu fikstür ikinci
        kaynağı taşımadığı için o soruyu SORAMAZ; soruyu
        ``test_iki_toplam_boydan_secim_beyan_edilir`` sorar (xfail borç imi).
        """
        r = liquid_results()
        assert 'component_sizing' not in r          # fikstür tek kaynaklı
        v = fv.normalize('liquid', r)
        assert v['engine_length_m'] == pytest.approx(0.209)

    def test_iki_toplam_boydan_secim_beyan_edilir(self):
        """Çok kaynaklı alanda ya TAM boy seçilir ya da seçim BEYAN edilir.

        ÖH Z5S / PK2 ONARILDI (defter P4B3-09) — xfail borç imi SÖKÜLDÜ.
        ÖNCE: sıvı ``engine_length_m`` aynı yanıttaki İKİ toplam boydan KISA
        olanı sessizce seçiyordu (``_mm_to_m(kd["overall_length_mm"])``).
        Ölçüldü (10 kN LOX/RP-1): kamara 97,959 + yakınsak 61,359 + ıraksak
        111,539 = 270,858 mm = ``component_sizing.component_dimensions.
        overall_length`` iken ``key_dimensions.overall_length_mm`` =
        209,499 mm (YAKINSAK bölüm düşmüş), %+29,29 fark; launch_site.html
        gövde boyu alt sınırını (boy + 1,0 m) bu sayıdan kuruyordu.
        SONRA: ``_liquid_overall_length_m`` üç bölümü de içeren TAM toplamı
        seçiyor — bu fikstürde 0,2708577429354722 m. Tek kaynaklı yanıtta
        davranış BİT-AYNI (bkz. ``test_length_mm_to_m``).
        """
        r = liquid_results()
        r['design_summary']['key_dimensions']['overall_length_mm'] = \
            OLCULEN_SIVI_UZUNLUK_KISA_MM
        r['component_sizing'] = {'component_dimensions': {
            'overall_length': OLCULEN_SIVI_UZUNLUK_TAM_M,     # METRE
            'maximum_diameter': 99.192,                       # mm
        }}
        v = fv.normalize('liquid', r)
        beyan = [k for k in v if 'length' in k and k != 'engine_length_m']
        assert (v['engine_length_m'] == pytest.approx(
            OLCULEN_SIVI_UZUNLUK_TAM_M, rel=1e-9) or beyan), (
            f"engine_length_m = {v['engine_length_m']:.6f} m — aynı yanıttaki "
            f'{OLCULEN_SIVI_UZUNLUK_TAM_M:.6f} m toplam boydan '
            f'%{100 * (OLCULEN_SIVI_UZUNLUK_TAM_M / v["engine_length_m"] - 1):.2f} '
            'kısa ve hangi kaynağın seçildiğini söyleyen alan yok')

    def test_inert_uses_full_engine_dry_mass_not_feed_subset(self):
        """Atıl kütle besleme ALT KÜMESİ olamaz; tam kuru kütleden küçük olamaz.

        ÖH B-4 (defter P4B3-20) — eski hâli ``== 43.5`` sabitiyle TANKLARI
        DIŞLAYAN sayıyı kilitliyordu: adı "TAM motor kuru kütlesi" derken
        şemada hiç görünmeyen 77,955 kg tank kütlesini dışarıda tutan değeri
        doğru ilan ediyordu (onarım bu testi kırmak zorunda kalırdı). İddia
        sözleşmeye taşındı: alt küme (18,0) DEĞİL ve tam kuru kütleden KÜÇÜK
        değil — atıl kütlenin BÜYÜMESİ (tanklar) artık serbest.
        """
        r = liquid_results()
        motor_kuru = r['design_summary']['masses']['engine_mass_kg']
        besleme = r['feed_system']['total_mass']
        v = fv.normalize('liquid', r)
        assert v['engine_inert_mass'] != besleme        # alt küme değil
        assert v['engine_inert_mass'] >= motor_kuru     # tam kuru kütle tabanı

    def test_inert_tank_kutlesini_icerir_ya_da_beyan_eder(self):
        """Uçan atıl kütle ya tankları İÇERİR ya da dışladığını SÖYLER.

        Çift-sayım (TUZAK2) yasağı eksik-sayımı meşrulaştırmaz: 6-DOF kuru
        kütlesi ``airframe_dry_mass + engine_inert_mass``tır, tank kütlesi
        iki toplamın da dışında kalırsa uçmayan bir araç çözülür.

        ÖH Z5S / PK2 ONARILDI (defter P4B3-20) — xfail borç imi SÖKÜLDÜ.
        ÖNCE: sıvı ``engine_inert_mass`` tankları ve artık propelanı DIŞARIDA
        bırakıyordu, üstelik "tahmin değil / not yok" damgasıyla
        (is_estimate=False, note=None). Ölçüldü (10 kN LOX/RP-1): atıl kütle
        43,503 kg iken ``propellant_tanks.system_summary.total_tank_mass``
        = 77,955 kg (motor atıl kütlesinin 1,79 KATI) şemada hiç yoktu;
        yüklenen ⟷ nominal propelan farkı 153,793 kg da yoktu.
        SONRA: ``_liquid_inert_mass`` uçan atıl kütleyi 275,251 kg olarak
        kuruyor (43,503 + 77,955 + 153,793) ve künye kalem kalem söylüyor.
        Tank alanı YOKSA sayı uydurulmaz; künye neyin dışarıda kaldığını
        yazar (bkz. ``test_inert_uses_full_engine_dry_mass_not_feed_subset``).
        """
        r = liquid_results()
        r['design_summary']['masses']['engine_mass_kg'] = \
            OLCULEN_SIVI_MOTOR_KURU_KG
        r['design_summary']['masses']['propellant_mass_kg'] = \
            OLCULEN_SIVI_PROP_NOMINAL_KG
        r['propellant_tanks'] = {'system_summary': {
            'total_tank_mass': OLCULEN_SIVI_TANK_KG,
            'total_propellant_mass': OLCULEN_SIVI_PROP_YUKLENEN_KG,
            'total_propellant_mass_nominal': OLCULEN_SIVI_PROP_NOMINAL_KG,
        }}
        v = fv.normalize('liquid', r)
        icerir = v['engine_inert_mass'] >= (
            OLCULEN_SIVI_MOTOR_KURU_KG + OLCULEN_SIVI_TANK_KG - 1e-9)
        beyan_eder = bool(v['engine_inert_mass_note']) and \
            'tank' in str(v['engine_inert_mass_note']).lower()
        assert icerir or beyan_eder, (
            f"engine_inert_mass = {v['engine_inert_mass']:.3f} kg; şemada "
            f'görünmeyen tank kütlesi {OLCULEN_SIVI_TANK_KG:.3f} kg '
            f'({OLCULEN_SIVI_TANK_KG / OLCULEN_SIVI_MOTOR_KURU_KG:.2f}×) ve '
            f'künye {v["engine_inert_mass_note"]!r}')

    def test_inert_falls_back_to_feed_system_when_no_engine_mass(self):
        r = liquid_results()
        r['design_summary']['masses'].pop('engine_mass_kg')
        r.pop('engine_mass_estimate')
        v = fv.normalize('liquid', r)
        assert v['engine_inert_mass'] == 18.0  # son çare: feed_system.total_mass

    def test_propellant_falls_back_to_mdot_times_burn(self):
        r = liquid_results()
        r['design_summary']['masses'].pop('propellant_mass_kg')
        v = fv.normalize('liquid', r)
        assert v['propellant_mass'] == pytest.approx(3.4 * 300.0)


# ---------------------------------------------------------------------------
# 4. ÇİFT-SAYIM — engine_inert propelanı İÇERMEZ (spec TUZAK2)
# ---------------------------------------------------------------------------

class TestNoDoubleCounting:
    """engine_inert_mass + propellant_mass = ıslak; inert TEK BAŞINA kuru olmalı.

    Çözücü toplam kuru kütleyi airframe_dry + engine_inert alır, propelanı
    AYRI ekler. engine_inert propelanı çoktan içeriyorsa propelan iki kez
    sayılır. Testler: normalize'ın inert alanı SADECE kuru kütle alanına eşit,
    propelanı toplamıyor.
    """

    def test_solid_inert_equals_pure_dry_not_wet(self):
        r = solid_results()
        r['design_summary']['masses']['dry_mass_kg'] = 5.0
        r['propellant_mass'] = 20.0
        v = fv.normalize('solid', r)
        assert v['engine_inert_mass'] == 5.0            # saf kuru
        assert v['propellant_mass'] == 20.0
        # ıslak (25.0) DEĞİL; toplam kütle çözücüde ayrı hesaplanır.
        assert v['engine_inert_mass'] != 25.0
        assert v['engine_inert_mass'] < v['propellant_mass']

    def test_hybrid_inert_is_dry_estimate_excluding_propellant(self):
        """Atıl kütle KURU alandan gelir; propelan ona EKLENMEZ.

        ÖH B-4 (defter P4B3-19) — eski fikstür ``dry = 0,25 × prop`` (10 ⟷ 40)
        seçilmişti, yani künyenin iddiasıyla ÇAKIŞIYORDU: çift-sayım iddiası
        o tesadüf yüzünden künye denetimiyle ayırt edilemiyordu. Fikstür
        ölçülen motora çevrildi (7,9590 kg propelan ⟷ 54,4513 kg atıl kütle,
        oran 6,84× — künyenin 0,25'iyle hiç örtüşmüyor); çift-sayım sorusu
        artık künyeden BAĞIMSIZ ölçülüyor.
        """
        r = hybrid_results()
        r['motor']['propellant_mass_total'] = OLCULEN_HIBRIT_PROP_KG
        r['motor']['design_summary']['key_dimensions']['dry_mass_estimate_kg'] = \
            OLCULEN_HIBRIT_INERT_KG
        v = fv.normalize('hybrid', r)
        assert v['engine_inert_mass'] == OLCULEN_HIBRIT_INERT_KG   # kuru alan
        assert v['propellant_mass'] == OLCULEN_HIBRIT_PROP_KG
        # Islak toplam (62,4103 kg) atıl kütle alanına SIZMAMALI.
        assert v['engine_inert_mass'] != pytest.approx(
            OLCULEN_HIBRIT_INERT_KG + OLCULEN_HIBRIT_PROP_KG)

    def test_liquid_inert_excludes_propellant(self):
        """Sıvı atıl kütle propelanı içermez (TUZAK2) — sabit çakması YOK.

        ÖH B-4 (defter P4B3-20) — eski hâli ``== 43.5`` ile tankları dışlayan
        sayıyı ikinci kez kilitliyordu; testin gerçek konusu ÇİFT SAYIM.
        İddia sözleşmeye taşındı: atıl kütle ıslak toplam olamaz ve
        propelandan küçük kalır (tank kütlesi eklense bile 121,5 « 1025).
        """
        r = liquid_results()
        motor_kuru = r['design_summary']['masses']['engine_mass_kg']
        prop_kaynak = r['design_summary']['masses']['propellant_mass_kg']
        v = fv.normalize('liquid', r)
        assert v['engine_inert_mass'] < v['propellant_mass']
        # Islak toplam (1068,5 kg) atıl kütle alanına SIZMAMALI.
        assert v['engine_inert_mass'] != pytest.approx(
            motor_kuru + prop_kaynak)

    @pytest.mark.parametrize('mt, factory', [
        ('hybrid', hybrid_results),
        ('solid', solid_results),
        ('liquid', liquid_results),
    ])
    def test_inert_and_propellant_are_distinct_fields(self, mt, factory):
        v = fv.normalize(mt, factory())
        assert v['engine_inert_mass'] is not None
        assert v['propellant_mass'] is not None
        # İki ayrı, birbirine eşit olmayan alan (kuru != islak != propelan).
        assert v['engine_inert_mass'] != v['propellant_mass']


# ---------------------------------------------------------------------------
# 5. Şema / hata yolları / ad çözümü
# ---------------------------------------------------------------------------

REQUIRED_KEYS = {
    'motor_type', 'motor_name', 'thrust_curve', 'thrust', 'burn_time',
    'propellant_mass', 'engine_inert_mass', 'engine_inert_mass_is_estimate',
    'engine_inert_mass_note', 'engine_od_m', 'engine_length_m', 'source',
}


class TestSchemaAndErrors:
    @pytest.mark.parametrize('mt, factory', [
        ('hybrid', hybrid_results),
        ('solid', solid_results),
        ('liquid', liquid_results),
    ])
    def test_all_required_keys_present(self, mt, factory):
        v = fv.normalize(mt, factory())
        assert REQUIRED_KEYS <= set(v.keys())

    def test_source_passthrough(self):
        v = fv.normalize('solid', solid_results(), source='project')
        assert v['source'] == 'project'

    def test_unknown_motor_type_raises(self):
        with pytest.raises(ValueError):
            fv.normalize('plasma', solid_results())

    def test_non_dict_results_raises(self):
        with pytest.raises(TypeError):
            fv.normalize('solid', [1, 2, 3])

    def test_name_resolution_priority(self):
        # açık ad > sonuç sözlüğü > varsayılan
        assert fv.normalize('solid', solid_results(), motor_name='X')['motor_name'] == 'X'
        r = solid_results(motor_name='FromResults')
        assert fv.normalize('solid', r)['motor_name'] == 'FromResults'
        assert fv.normalize('solid', solid_results())['motor_name'] == 'Solid Motor'

    def test_missing_fields_become_none_not_zero(self):
        """Uydurma-veri-yasağı: eksik alan None; sessizce 0 sayılmaz.

        ÖH B-4 KAPSAM BEYANI (defter P4B3-04): bu bekçi DOĞRU ilkeyi yalnız
        ``normalize`` tarafında kilitliyor. Aynı modülün ``recompute_from_
        project`` kolu TERSİNİ yapıyor — ``_f`` (flight_vehicle.py:317-324)
        eksik alanın yerine sessizce varsayılan koyup TAM sonuç üretiyor.
        Bu asimetriyi ölçen bekçiler: ``TestRecomputeGirdiDurustlugu``
        (xfail borç imleri). Buradaki iddia üç normalize koluna genişletildi;
        eskiden yalnız katı kol denenmişti.
        """
        v = fv.normalize('solid', {'average_thrust': 100.0})
        assert v['thrust'] == 100.0
        assert v['propellant_mass'] is None
        assert v['engine_inert_mass'] is None
        assert v['engine_length_m'] is None
        # Kardeş kollar da uydurmuyor (tek satırlık girdi, gerisi eksik).
        vh = fv.normalize('hybrid', {'thrust': 100.0})
        assert (vh['propellant_mass'], vh['engine_inert_mass'],
                vh['engine_od_m'], vh['engine_length_m']) == (None,) * 4
        vl = fv.normalize('liquid', {'thrust': 100.0})
        assert (vl['propellant_mass'], vl['engine_inert_mass'],
                vl['engine_od_m'], vl['engine_length_m']) == (None,) * 4


# ---------------------------------------------------------------------------
# 6. recompute_from_project — gerçek katı motor (çevrimdışı, hızlı)
# ---------------------------------------------------------------------------

#: ``test_solid_recompute_end_to_end``ün projesi. ÖLÇÜLDÜ (27 Ağu 2026): bu
#: sekiz alanın SEKİZİ DE ``_recompute_solid``in varsayılanıyla aynı
#: (flight_vehicle.py:366-376), yani belge BOŞ bir belgeden ayırt edilemez —
#: bekçinin tek başına "proje gerçekten okundu" diyememesinin sebebi budur.
#: V301/T-ÇAPA-A: çekirdek 30 -> 76 mm. 30 mm + a = 0,005 portu boğulan
#: motordur (A_p/A_t 0,396 -> K-A KT-23 422); 76 mm ölçülen A_p/A_t 2,218
#: (tests/test_faz4_motor_kapilari.KATI_TABAN ile aynı ölçüm). Artık sekiz
#: alanın YEDİSİ ``_recompute_solid`` varsayılanıyla aynı; çekirdek farklı.
#: ``_recompute_solid``in kendi 30 mm varsayılanı ürün kusuru: T-ÇAPA-A
#: RAPOR DEVİR 1 (boş/eksik proje düğümleri o yüzden kırmızı kalır).
#: V301/UÇUŞ C-1 (DEVİR 1 KAPANDI): ``_recompute_*`` ve modül yedekleri
#: SÖKÜLDÜ; recompute sayfa ucunu koşar, eksik zorunlu alan ucun adlı reddi
#: olur (``fv.ProjectCalculationRejected``, ``ValueError`` alt sınıfı).
SOLID_PROJE_ALANLARI = {
    'grain_type': 'bates', 'propellant_type': 'apcp',
    'chamber_diameter': 100, 'grain_length': 500,
    'core_diameter': 76, 'chamber_pressure': 40,
    'burn_rate_a': 0.005, 'burn_rate_n': 0.35,
}

#: Yukarıdaki belgenin ÖLÇÜLEN çıktısı (27 Ağu 2026, HEAD 344714d).
#: ÖH KİTAP p1b (B11, §28-36 Ş-3): itki 6739,133989599616 ve motor boyu
#: 0,773479676663654 m APCP kaydının geri çözülmüş dörtlüsündendi; CEA denge
#: dörtlüsüyle ölçülen yeni taban (ε denge γ_s ile büyüdü → lüle uzadı).
#: V301/T-ÇAPA-A — YENİDEN ÖLÇÜLDÜ (26 Eki, 76 mm çekirdek; aynı yol
#: recompute_from_project -> normalize, iki koşu bit-aynı). Eski -> yeni:
#: itki 6787,4256 -> 10301,9063 N; süre 2,18631 -> 0,68653 s; yakıt
#: 6,46815 -> 3,00236 kg (geometri + a = 0,005); atıl 6,00140 -> 6,45346 kg
#: (K-A KT-03 astar radyal, K-A RAPOR §5'teki 6,0014 -> 6,4535 ile aynı);
#: dış çap 0,1048 -> 0,13396 m (KT-02: kasa iç + 2·cidar, bu itkinin
#: cidarıyla); boy 0,78599 -> 0,79716 m; termokimya N-CEA-2 (CEA, Pc'de).
#: Aşağıdaki tarihçe yorumları eski sayılara aittir.
SOLID_PROJE_OLCUM = {
    'thrust': 10301.90633210043,
    'burn_time': 0.6865322362722804,
    'propellant_mass': 3.002357267182695,
    # ÖH D18 (P2B4-04): liner halkası kuru kütleye EKLENDİ (daha önce
    # 0 kg giriyordu — atalet kütlesi eksikti, kütle kesri iyimserdi ve bu
    # çapa o eksik sayıyı kilitliyordu). Ölçülen yeni değer aynı gövdeyle
    # 6,001397012523196 kg; fark 0,4614 kg = varsayılan 2 mm liner halkası.
    'engine_inert_mass': 6.4534577390220145,
    # V301/FİZİK-2 (kalem 6, KABUL 13-14) — YENİDEN ÖLÇÜLDÜ, gerekçeli: eski
    # 0,13396 m lüle çıkışının İÇ çapıydı (key_dimensions.nozzle_exit_mm
    # 133,959); araç zarfı artık ÇİZİLEN dış zarftır — STEP/STL lüle
    # katısının profili (iç + et): 0,144165 m. Eski boy 0,79716 m kapaksız
    # ve çözücü lüle boyuyla kuruluydu; araç boyu artık CAD-2'nin tek tanımı
    # (kasa + çizilen lüle 798,443 mm + çizilen ön kapak 12,654 mm).
    'engine_od_m': 0.14416492252724383,
    'engine_length_m': 0.8110972111275743,
}


class TestRecomputeProjectSolid:
    def test_solid_recompute_end_to_end(self):
        """.hrma → gerçek katı motor → araç şeması, SAYISAL çapayla.

        ÖH B-4 (defter P4B3-04) — eski hâli altı alanı geniş bantlarla
        sınıyordu (``thrust > 1000``, ``1 < prop < 100``, ``0,10 ≤ od ≤
        0,20``): zincirin herhangi bir yerindeki %50'lik bir kayma bile
        bandın içinde kalır, bekçi susardı. Bantlar ölçülmüş değerlere
        çapalandı (rel=1e-6 — platform kayan nokta sözleşmesi).
        """
        doc = {'motor_type': 'solid',
               'inputs': {'fields': dict(SOLID_PROJE_ALANLARI)}}
        motor_type, results = fv.recompute_from_project(doc)
        assert motor_type == 'solid'
        # V301/UÇUŞ C-1: recompute sayfanın hesap ucunun GÖVDESİNİ koşar;
        # sonuç, aynı yükle ``/calculate_solid``in yanıtıyla BİT-AYNI olmalı
        # (eskiden ``_recompute_solid`` motoru kendisi kuruyordu). Aşağıdaki
        # altı çapa bu belgede DEĞİŞMEDİ (ölçüldü: eski kurulum ile uç bu
        # sekiz alanda aynı sayıyı veriyor; ayrışma örnek projelerin uç
        # argümanlarındaydı — tests/test_v301_ucus_proje_kaynagi.py).
        durum, uc_govdesi = fv.run_page_calculation(
            'solid', fv.page_payload('solid', SOLID_PROJE_ALANLARI))
        assert durum == 200
        assert results == uc_govdesi
        v = fv.normalize(motor_type, results, source='project')

        assert v['source'] == 'project'
        for alan, olculen in SOLID_PROJE_OLCUM.items():
            assert v[alan] == pytest.approx(olculen, rel=1e-6), (
                f'{alan}: {v[alan]!r} ⟷ ölçülen {olculen!r}')
        # Katı motorda gerçek itki eğrisi taşınır.
        assert v['thrust_curve'] is not None
        assert len(v['thrust_curve']['time']) > 3

    def test_proje_alanlari_sonucu_gercekten_suruyor(self):
        """Belgedeki alan DEĞİŞİNCE sonuç ölçülebilir biçimde değişmeli.

        ÖH B-4: uçtan uca bekçi tek bir belgeyle koştuğu için "alanlar
        gerçekten okundu mu" sorusunu hiç sormuyordu (defter P4B3-04'ün
        kör noktası). Hazne basıncı 40 → 70 bar taşınır; itki ve atıl kütle
        ölçülebilir biçimde değişmelidir.
        """
        def _kos(**degisim):
            alanlar = dict(SOLID_PROJE_ALANLARI, **degisim)
            mt, res = fv.recompute_from_project(
                {'motor_type': 'solid', 'inputs': {'fields': alanlar}})
            return fv.normalize(mt, res, source='project')

        taban = _kos()
        yuksek = _kos(chamber_pressure=70)
        assert yuksek['thrust'] > taban['thrust'] * 1.10, (
            f"40 bar {taban['thrust']:.3f} N ⟷ 70 bar "
            f"{yuksek['thrust']:.3f} N — hazne basıncı zincire girmiyor")
        assert yuksek['engine_inert_mass'] > taban['engine_inert_mass'] * 1.10


class TestRecomputeGirdiDurustlugu:
    """recompute'un EKSİK GİRDİ politikası (defter P4B3-04).

    ``normalize`` eksik alanı ``None`` yapar (uydurma-veri-yasağı,
    ``TestSchemaAndErrors::test_missing_fields_become_none_not_zero``);
    aynı modülün ``recompute_from_project`` kolu ise ``_f``
    (flight_vehicle.py:317-324) ile sessizce varsayılan koyar. Bu sınıf o
    ASİMETRİYİ ölçer; iki bekçi de bugün ürün kusuru yüzünden kırmızıdır ve
    xfail(strict) borç imiyle durur.
    """

    def test_bos_proje_tam_sonuc_uretmez(self):
        """Boş belge ya reddedilir ya da hangi girdinin uydurulduğu söylenir.

        ÖH Z5S / PK2 ONARILDI (defter P4B3-04) — xfail borç imi SÖKÜLDÜ.
        ÖNCE: boş ``inputs.fields`` ile ``recompute_from_project`` TAM sonuç
        üretiyordu — ölçüldü (katı) 64 anahtar, 6739,134 N / 2,186 s /
        6,468 kg ve "girdi eksik, varsayılan kullanıldı" diyen tek bir kayıt
        yoktu; kullanıcının ekranında bu sonuç ``source='project'`` künyesiyle
        kendi projesi gibi görünüyordu.
        SONRA: 66 anahtar — ``input_defaults_substituted`` (ikame edilen 8
        alanın adı) + ``input_defaults_substituted_note``. Alanların hepsi
        verilmişse sözlüğe DOKUNULMAZ (sağlıklı yol bit-aynı).
        """
        try:
            _mt, results = fv.recompute_from_project(
                {'motor_type': 'solid', 'inputs': {'fields': {}}})
        except (ValueError, KeyError):
            return                      # fail-closed: dürüst davranış
        beyan = ikame_beyani(results)
        assert beyan, (
            f'boş projeden {len(results)} anahtarlı tam sonuç geldi '
            f'(itki {results.get("average_thrust")!r}, yanma '
            f'{results.get("burn_time")!r}) ve hangi girdinin varsayılanla '
            'ikame edildiğini söyleyen tek alan/uyarı yok')

    def test_eksik_alan_sessizce_ikame_edilmez(self):
        """Eksik alan yerine varsayılan konduysa BEYAN edilmeli.

        ÖH Z5S / PK2 ONARILDI (defter P4B3-04) — xfail borç imi SÖKÜLDÜ.
        ÖNCE: TEK eksik alan aracı sessizce değiştiriyordu — ölçüldü (katı,
        hazne basıncı alanı çıkarıldı) itki 8628,123 → 6739,134 N (−%21,9),
        atıl kütle 9,695 → 5,540 kg (−%42,9); hibritte of_ratio vakası daha
        ağırdı (propelan +%71, atıl kütle +%460, boy +%415).
        SONRA: ``_f`` ikameyi kaydediyor, ``_declare_substitutions`` künyeyi
        sonuca yazıyor (``input_defaults_substituted = ['chamber_pressure']``).
        UÇ KATMANI KAPSAM DIŞI: /api/flight-vehicle (app.py) bu künyeyi
        tüketiciye taşımıyor — bu borç PK5/app.py zincirine devredildi.
        """
        tam = dict(SOLID_PROJE_ALANLARI, chamber_pressure=70)
        eksik = {k: v for k, v in tam.items() if k != 'chamber_pressure'}
        _mt, r_tam = fv.recompute_from_project(
            {'motor_type': 'solid', 'inputs': {'fields': tam}})
        try:
            _mt2, r_eksik = fv.recompute_from_project(
                {'motor_type': 'solid', 'inputs': {'fields': eksik}})
        except (ValueError, KeyError):
            return                      # fail-closed: dürüst davranış
        v_tam = fv.normalize('solid', r_tam, source='project')
        v_eksik = fv.normalize('solid', r_eksik, source='project')
        sessiz = (v_tam['thrust'] != pytest.approx(v_eksik['thrust'], rel=1e-9)
                  and not ikame_beyani(r_eksik))
        assert not sessiz, (
            f"hazne basıncı alanı yokken itki {v_tam['thrust']:.3f} N yerine "
            f"{v_eksik['thrust']:.3f} N (%"
            f"{100 * (v_eksik['thrust'] / v_tam['thrust'] - 1):.1f}), atıl "
            f"kütle {v_tam['engine_inert_mass']:.3f} → "
            f"{v_eksik['engine_inert_mass']:.3f} kg — ikameyi söyleyen "
            'alan/uyarı yok')


class TestRecomputeDispatch:
    def test_unknown_motor_type_raises(self):
        with pytest.raises(ValueError):
            fv.recompute_from_project({'motor_type': 'plasma',
                                       'inputs': {'fields': {}}})

    def test_non_dict_doc_raises(self):
        with pytest.raises(TypeError):
            fv.recompute_from_project(['not', 'a', 'doc'])


# ---------------------------------------------------------------------------
# 7. projects.py — airframe gidiş-dönüşü + şema redleri
# ---------------------------------------------------------------------------

@pytest.fixture()
def proj_dir(tmp_path, monkeypatch):
    """İzole proje dizini (env override) — test_projects_store.py deseni."""
    d = tmp_path / 'projects'
    monkeypatch.setenv('HRMA_PROJECTS_DIR', str(d))
    return d


def airframe_payload(airframe, **over):
    """airframe içeren geçerli, sentetik proje yükü."""
    payload = {
        'format': 'hrma-project',
        'format_version': 1,
        'motor_type': 'hybrid',
        'inputs': {
            'fields': {'thrust': 1000.0, 'burn_time': 10.0},
            'airframe': airframe,
        },
        'results_summary': {'isp': 245.0},
    }
    payload.update(over)
    return payload


class TestAirframeProjectRoundTrip:
    def test_airframe_saved_and_loaded_byte_equal(self, proj_dir):
        airframe = {
            'body_diameter': 0.15,
            'body_length': 2.5,
            'nose_type': 'ogive',
            'nose_length': 0.40,
            'fin_count': 4,
            'fin_root': 0.20,
            'fin_tip': 0.10,
            'fin_span': 0.11,
            'fin_sweep': 0.08,
            'fin_position': 1.80,
            'airframe_dry_mass': 8.0,
            'cd0': 0.45,
            'launch_elevation': 84.0,
            'launch_azimuth': 90.0,
            'rail_length': 5.0,
            'latitude_deg': 39.0,
            'default_fins': True,
        }
        store.save_project('flying', airframe_payload(airframe))
        doc, _warnings = store.load_project('flying')
        assert doc['inputs']['airframe'] == airframe

    def test_airframe_optional_absent_still_valid(self, proj_dir):
        payload = {
            'format': 'hrma-project', 'format_version': 1,
            'motor_type': 'solid',
            'inputs': {'fields': {'chamber_diameter': 100.0}},
        }
        store.save_project('noair', payload)
        doc, _ = store.load_project('noair')
        assert 'airframe' not in doc['inputs']

    def test_airframe_rejects_nested_object(self, proj_dir):
        with pytest.raises(store.ProjectValidationError):
            store.validate_payload(airframe_payload({'fins': {'count': 4}}))

    def test_airframe_rejects_none_value(self, proj_dir):
        with pytest.raises(store.ProjectValidationError):
            store.validate_payload(airframe_payload({'body_diameter': None}))

    def test_airframe_rejects_non_finite(self, proj_dir):
        with pytest.raises(store.ProjectValidationError):
            store.validate_payload(airframe_payload({'cd0': float('inf')}))

    def test_airframe_must_be_object(self, proj_dir):
        payload = airframe_payload({})
        payload['inputs']['airframe'] = [1, 2, 3]
        with pytest.raises(store.ProjectValidationError):
            store.validate_payload(payload)

    def test_airframe_accepts_scalars_only(self, proj_dir):
        # str/num/bool serbest; overwrite gidiş-dönüşü de korunur.
        af = {'nose_type': 'vonKarman', 'fin_count': 3, 'default_fins': False,
              'cd0': 0.5}
        store.save_project('af2', airframe_payload(af))
        store.save_project('af2', airframe_payload({**af, 'cd0': 0.6}),
                            overwrite=True)
        doc, _ = store.load_project('af2')
        assert doc['inputs']['airframe']['cd0'] == 0.6


# ---------------------------------------------------------------------------
# 8. BİRİM ÇEVRİMİNİN İKİZ TANIMI + fiziksel olmayan ölçü (defter P15B2-02)
# ---------------------------------------------------------------------------
# Bu dosyadaki BEŞ bekçi (hibrit/katı/sıvı ``*_mm_to_m`` ve iki ``od_*``)
# çevrimi ölçüyor, ÇEVRİMİN SÖZLEŞMESİNİ hiç sormuyordu: depoda ``_mm_to_m``
# adında İKİ ayrı tanım vardı (``hrma/app.py`` varsayılanlı, ``hrma/
# analysis/flight_vehicle.py`` varsayılansız) ve aynı girdiye farklı
# karar veriyorlardı. (ÖH D29 a2 / P7B1-21: app tarafındaki ölü
# sarmalayıcı silindi; karşılaştırma artık ürünün gerçekten okuduğu
# ``hrma.app._mm_to_m_read`` ile yapılıyor — bkz. aşağıdaki künye.) Ölçülen ürün sonucu: POST /api/flight-vehicle fiziksel
# olmayan ölçüyü künyesiz HTTP 200 ile yayımlıyor
# (``engine_od_m = -120,0`` — hibrit kolda hem işaret kapısı hem çevrim yok).
#
# Uç katmanının kardeş bekçisi tests/test_flight_bridge_wiring.py'nin
# konusudur (bu dosya modül sözleşmesini kilitler).

def _ikiz_sozlesme_tablosu():
    """İki ``mm -> m`` çevriminin aynı girdilere verdiği kararlar.

    ÖH D29 / app-api-uc a2 (P7B1-21) — SORULAN KOL DEĞİŞTİ, İDDİA DEĞİL.
    Tablo eskiden ``hrma.app._mm_to_m(value, default_m)`` ile kuruluyordu;
    o sarmalayıcı ÖLÜ olduğu için (ürün içinde 0 çağrı — ölçüldü:
    ``docs/scofield/raw/OH/D29/app-api-uc/a2/once.json`` K7, AST sayımı)
    silindi ve yalnız bu bekçi tarafından ayakta tutuluyordu. Ürünün
    GERÇEKTEN okuduğu app tarafı kolu ``_mm_to_m_read``tir ve silinen
    sarmalayıcı zaten onun üzerine kuruluydu
    (``default_m if durum != WALL_INPUT_OK else metre``); o iki satır
    buraya, testin kendi "reddetti" tanımına taşındı.

    İddia AYNEN duruyor: iki kol aynı girdiye aynı kararı vermeli.
    """
    from hrma.app import WALL_INPUT_OK, _mm_to_m_read

    def app_mm_to_m(value, default_m):
        """Silinen ``hrma.app._mm_to_m``in gövdesi (bire bir)."""
        metre, durum = _mm_to_m_read(value)
        return default_m if durum != WALL_INPUT_OK else metre

    # app kolu reddettiğinde VARSAYILANA döner; bu yüzden varsayılan değeri
    # "reddettim" işareti sayılır. Girdi listesinde 5 mm (= 0,005 m) YOKTUR,
    # yoksa geçerli bir çevrim reddediliyor sanılırdı.
    varsayilan = 0.005
    girdiler = [123.0, '250', 0.0, -5.0, None, '', 'abc',
                float('nan'), float('inf'), True]
    satirlar = []
    for g in girdiler:
        a = app_mm_to_m(g, varsayilan)
        b = fv._mm_to_m(g)
        a_reddetti = (a == varsayilan)
        b_reddetti = (b is None)
        # NaN/Inf geçiren kol da "kabul etti" sayılır (a_reddetti False).
        uyumlu = (a_reddetti == b_reddetti) and (
            a_reddetti or (b is not None and a == pytest.approx(b)))
        satirlar.append((g, a, b, uyumlu))
    return satirlar


# ÖH D26 / app-api a5 — ``xfail(strict=True)`` BORÇ İMİ KALDIRILDI.
#
# İmin gerekçesi şuydu: ``_mm_to_m`` adında İKİ tanım vardı ve aynı girdiye
# farklı karar veriyorlardı (``hrma/app.py`` sıfır/negatifi reddedip
# varsayılana düşüyor, ``hrma/analysis/flight_vehicle.py`` sıfır ve
# NEGATİFİ geçiriyordu: −5 mm → −0,005 m).
#
# ONARIM (kural #11, tek kaynak): karar tek bir yere,
# ``hrma.utils.input_guard.mm_to_m_read``a alındı; her iki tanım da onu
# ÇAĞIRIR. ÖLÇÜLDÜ (taban 7751531 ⟷ bu ağaç, ``once.json``/``sonra.json``
# ``ikiz_ayrisan_sayisi``): ayrışan girdi sayısı 8 → 0. İm kalkmasaydı test
# XPASS(strict) ile süiti kırardı; testin kendisi AYNEN duruyor ve bundan
# sonra gerçek bir bekçidir.
def test_ikiz_mm_to_m_ayni_sozlesmeyi_tasir():
    """Aynı adı taşıyan iki çevrim aynı girdiyi aynı biçimde karara bağlamalı."""
    ayrisan = [(g, a, b) for g, a, b, uyumlu in _ikiz_sozlesme_tablosu()
               if not uyumlu]
    assert not ayrisan, 'ayrışan girdiler: ' + '; '.join(
        f'{g!r}: app={a!r} ⟷ flight_vehicle={b!r}' for g, a, b in ayrisan)


# ÖH D24 / hibrit a1 — ``xfail(strict=True)`` KALDIRILDI (kırılan bekçi
# kaydı: docs/scofield/raw/OH/D24/hibrit/a1/rapor.md).
#
# İşaret/sıfır kapısı P15B2-03 onarımının YAN ÜRÜNÜ olarak kapandı: üç
# normalize de dış çapı artık ``_length_m`` üzerinden, yani tek birim
# otoritesi ``hrma.export.motor_geometry.resolve_length_m`` ile çözüyor ve o
# otorite sonlu-POZİTİF olmayan değeri zaten reddediyor (``f <= 0.0 ->
# (None, 'missing')``). ÖLÇÜLDÜ (bu ağaç): altı parametrenin altısı da
# ``engine_od_m is None`` veriyor — işaretçi marker XPASS(strict) olduğu için
# artık KIRMIZI olurdu; kusuru anlatan marker kaldırıldı, testin kendisi
# AYNEN duruyor ve bundan sonra gerçek bir bekçidir.
#
# P15B2-02'nin İKİZ-SÖZLEŞME ayağı (``_mm_to_m``in app.py ⟷ flight_vehicle
# ayrışması) HÂLÂ AÇIK: yukarıdaki ``test_ikiz_mm_to_m_ayni_sozlesmeyi_tasir``
# xfail olarak duruyor ve dokunulmadı.
@pytest.mark.parametrize('mt', ['hybrid', 'solid', 'liquid'])
@pytest.mark.parametrize('deger', [-120.0, 0.0])
def test_fiziksel_olmayan_olcu_yayimlanmaz(mt, deger):
    """Negatif/sıfır çap bir ölçü değildir: ``None`` olmalı ya da reddedilmeli."""
    results = {'motor': {'chamber_diameter': deger}} if mt == 'hybrid' \
        else {'chamber_diameter': deger}
    try:
        v = fv.normalize(mt, results)
    except ValueError:
        return                          # fail-closed: dürüst davranış
    assert v['engine_od_m'] is None, (
        f'{mt}: chamber_diameter={deger!r} → engine_od_m='
        f'{v["engine_od_m"]!r} (fiziksel olmayan ölçü künyesiz yayımlandı)')
