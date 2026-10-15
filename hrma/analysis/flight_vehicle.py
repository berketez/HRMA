"""
hrma/analysis/flight_vehicle.py

Uçan-araç (launch site) köprüsü için TEK normalize kaynağı (kural #11).

Üç motor tipi (hybrid / solid / liquid) FARKLI sonuç sözlüğü şemaları üretir:
alan adları, iç içe yerleşim ve BİRİMLER tipe göre değişir. Bu modül onları
TEK "uçan araç" şemasına indirger; böylece launch_site.html ve 6-DOF çözücüsü
motor tipinden bağımsız çalışır (üç ayrı ``thrustProvider`` yerine tek Python
normalize).

Çıktı şeması (``normalize``):
  {
    'motor_type': 'hybrid'|'solid'|'liquid',
    'motor_name': str,
    'thrust_curve': {'time': [s...], 'thrust': [N...]} | None,
    'thrust': float | None,             # temsili/ortalama itki [N]
    'burn_time': float | None,          # [s]
    'propellant_mass': float | None,    # [kg]
    'engine_inert_mass': float | None,  # [kg] PROPELAN HARİÇ (atıl/kuru)
    'engine_inert_mass_is_estimate': bool,
    'engine_inert_mass_note': str | None,
    'engine_od_m': float | None,        # motor dış çapı [m]
    'engine_od_unit_source': str|None,  # dış çapın birimi NASIL kazanıldı
    'engine_length_m': float | None,    # motor toplam boyu [m]
    'source': str,                      # 'results'|'project'|'example'
  }

ÇİFT-SAYIM TUZAĞI (spec TUZAK2): ``engine_inert_mass`` motorun ATIL (kuru)
kütlesidir; propelanı İÇERMEZ. 6-DOF çözücüsü toplam kuru kütleyi
``airframe_dry_mass + engine_inert_mass`` olarak, propelanı ise ayrı
(``propellant_mass``) alır. Aynı kütleyi iki kez saymamak için bu ayrım
zorunludur — normalize propelanı atıl kütleye ASLA eklemez.

BİRİM SÖZLEŞMESİ (ÖH D24 / defter P15B2-03) — BU MODÜL ARTIK MOTOR TİPİNDEN
BİRİM ÇIKARMAZ. Eskiden burada "hybrid METRE, solid/liquid MİLİMETRE" yazılı
bir tip↔birim tablosu vardı ve ``chamber_diameter`` o tabloya göre ya olduğu
gibi alınıyor ya da 1000'e bölünüyordu. Tablo ürünün DIŞINDA duran bir
bilgiydi: üretici birimini değiştirse (ya da beyan etse) okuyucu bunu
göremezdi. ÖLÇÜLDÜ (taban ``88a29d3``, ``docs/scofield/raw/OH/D24/hibrit/a1/
once.json`` bölüm C): hibrit sonucun ``length_units`` beyanı **'m'** olduğu
hâlde modül beyanı hiç okumuyordu (``resolve_length_m_kullaniyor = false``);
beyan ``'mm'`` yapılmış bir sonuçta da AYNI sayıyı döndürüyordu, yani birim
yalanı sessizce geçiyordu.

Bugünkü kural: uzunluk birimi ÜRETİCİNİN BEYANINDAN kazanılır ve tek otorite
``hrma/export/motor_geometry.py``dir (``resolve_length_m``: normalize
``motor_geometry`` bloğu > ``length_units`` beyanı > iki-okuma bant kuralı).
Kazanılamayan alan UYDURULMAZ: ``engine_od_m`` ``None`` kalır ve
``engine_od_unit_source`` hangi yolun seçildiğini (ya da ``missing`` /
``ambiguous``) söyler. Birimi ADIYLA beyan eden alanlar (``*_mm``) eskisi gibi
doğrudan çevrilir — orada çıkarım zaten yoktur.
"""

from typing import Any, Dict, List, Optional, Tuple

from hrma.utils import input_guard

_MOTOR_TYPES = ('hybrid', 'solid', 'liquid')

_DEFAULT_NAMES = {
    'hybrid': 'Hybrid Motor',
    'solid': 'Solid Motor',
    'liquid': 'Liquid Motor',
}


# --- Küçük yardımcılar ------------------------------------------------------

def _num(value: Any) -> Optional[float]:
    """Değeri sonlu ``float``'a çevir; olmuyorsa ``None``.

    Sözde-veri üretmez: ``None``, NaN, sonsuz ve dönüştürülemez değerler
    ``None`` olur (uydurma-veri-yasağı: eksik alan sessizce 0 sayılmaz).

    ÖH D30 / termo-ucus a1 · defter OH-D29-06 (OH-D27-11 termo payı) —
    KARAR ARTIK MERKEZDE. Hüküm
    :func:`hrma.utils.input_guard.finite_number`'dadır (TEK KAYNAK,
    CLAUDE.md kural #11); bu ad modül içi takma addır. Kardeşi
    ``_mm_to_m`` D26'da (P15B2-02) zaten ``input_guard.mm_to_m_read``'e
    bağlanmıştı; ``_num``'ın bağlanması D28'de ENGELLİYDİ, engel
    birleşmeyle kalktı (ölçüldü: ``once.json`` K1).

    ÖLÇÜLEN AYRIŞMA (``once.json`` K3, 18 prob): yerel tanım merkezden
    **2 kararda** ayrışıyordu. Yerel süzgeç ``isinstance(value, bool)``
    idi; ``numpy.bool_`` Python ``bool``un alt sınıfı DEĞİLDİR, oysa
    ``float()`` onu da 1,0/0,0'a çevirir — çözücü sonuçları numpy
    taşıdığı için bu delik gerçektir. Ürün yüzeyinde ölçülen sonuç
    (``once.json`` K4): ``normalize('hybrid', {'thrust': np.bool_(True),
    ...})`` uçan araç şemasına **1,0 N itki**, **1,0 s yanma süresi** ve
    **1,0 kg propelan** yazıyordu. ``finite_number`` numpy doğruluk
    değerini ``dtype.kind == 'b'`` ördek denetimiyle eler.
    """
    return input_guard.finite_number(value)


def _get(d: Any, *path: str) -> Any:
    """İç içe sözlükten güvenli okuma (``dict.get`` zinciri)."""
    cur = d
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _mm_to_m(value: Any) -> Optional[float]:
    """Milimetre değerini metreye çevir (None-güvenli).

    YALNIZ birimini ADIYLA beyan eden alanlar (``*_mm``) için kullanılır;
    beyansız bir alanın birimini varsaymak için KULLANILMAZ (P15B2-03).

    ÖH D26 / app-api a5 (defter P15B2-02) — İKİZ SÖZLEŞME KAPANDI. Depoda
    ``_mm_to_m`` adında İKİ tanım vardı ve aynı girdiye farklı karar
    veriyorlardı: ``hrma/app.py`` tarafı ``0`` ve NEGATİFİ reddederken bu
    tanım onları geçiriyordu (ölçüldü, taban 7751531: ``-120`` mm →
    ``-0,12`` m). Bir boy/çap NEGATİF olamaz; bu modülün kendi birim
    otoritesi (``motor_geometry.resolve_length_m``) da sonlu-pozitif
    olmayanı zaten reddediyor (``f <= 0.0 -> (None, 'missing')``), yani
    burada gevşek kalması modülün İÇİNDE bir çelişkiydi.

    Karar artık ``hrma.utils.input_guard.mm_to_m_read`` içindedir (tek
    kaynak, kural #11); burada yalnız metre ayağı alınır — ret nedenini
    isteyen çağıran merkezi doğrudan çağırır.
    """
    return input_guard.mm_to_m_read(value)[0]


def _length_m(node: Any, key: str) -> Tuple[Optional[float], str]:
    """Uzunluğu ÜRETİCİNİN BEYANINDAN metreye çöz (P15B2-03).

    Tek birim otoritesi ``hrma.export.motor_geometry.resolve_length_m``tir
    (CLAUDE.md kural #11): normalize ``motor_geometry`` bloğu > ``length_units``
    beyanı > iki-okuma bant kuralı. Burada ikinci bir sezgi YAZILMAZ.

    Döner: ``(metre veya None, kaynak etiketi)``. Otorite yüklenemezse
    ``(None, 'unit_authority_unavailable')`` döner — sessizce bir birim
    varsayılmaz (fail-closed).
    """
    if not isinstance(node, dict):
        return None, 'missing'
    try:
        from hrma.export.motor_geometry import resolve_length_m
    except Exception:                       # pragma: no cover - kurulum arızası
        return None, 'unit_authority_unavailable'
    return resolve_length_m(node, key)


def _curve(time: Any, thrust: Any) -> Optional[Dict[str, List[float]]]:
    """(time, thrust) dizilerinden temiz bir itki eğrisi kur ya da ``None``.

    Kurallar: her iki dizi liste/tuple, eşit uzunlukta ve >= 2 nokta olmalı;
    elemanlar sonlu sayıya çevrilebilmeli. Tek nokta veya bozuk dizi -> None
    (6-DOF paneli >3 nokta arıyor; burada asgari geçerlilik denetlenir).
    """
    if not isinstance(time, (list, tuple)) or not isinstance(thrust, (list, tuple)):
        return None
    if len(time) != len(thrust) or len(time) < 2:
        return None
    t_out: List[float] = []
    f_out: List[float] = []
    for t, f in zip(time, thrust):
        tv = _num(t)
        fv = _num(f)
        if tv is None or fv is None:
            return None
        t_out.append(tv)
        f_out.append(fv)
    return {'time': t_out, 'thrust': f_out}


#: Hibrit atıl kütlesi için tarihsel başparmak kuralı (kuru kütle ≈ oran ×
#: propelan). TEK TANIM NOKTASI (kural #11): hem künye metni hem de künyenin
#: sayıyla tutup tutmadığını sınayan dal buradan okur — ikisi ayrı yazılırsa
#: künye sayıdan yeniden kopar (ÖH defter P4B3-19).
HYBRID_INERT_RULE_OF_THUMB_RATIO = 0.25
#: Künyenin "oran kuralı geçerli" sayılması için gereken bağıl yakınlık.
_RULE_OF_THUMB_REL_TOL = 1e-6


def _hybrid_inert_note(inert: Optional[float], prop: Optional[float],
                       basis: Any) -> Optional[str]:
    """Hibrit atıl kütle künyesini YAYIMLANAN SAYIDAN üret (P4B3-19).

    Eski hâli SABİT bir cümleydi ("estimated as ~0.25 x propellant mass")
    ve motorun gerçek yapısal hesabından gelen değerle çelişiyordu:
    ÖLÇÜLDÜ (3 kN N2O/HTPB) propelan 7,9590 kg, atıl kütle 54,4513 kg,
    künyenin vaadi 1,9897 kg → oran 27,37× (fark +52,462 kg). Cümlenin iki
    yarısı da yanlıştı (ne oran tutuyordu ne de değer bir başparmak
    kuralından geliyordu).

    Yeni sözleşme: oran iddiası YALNIZCA sayı gerçekten o kuralı sağlıyorsa
    yazılır. Sağlamıyorsa künye oran İDDİA ETMEZ; değerin nereden geldiğini
    (motorun ``dry_mass_basis`` künyesi) söyler ve ölçülen oranı bir kural
    gibi değil, bir GÖZLEM olarak bildirir.
    """
    basis_txt = basis.strip() if isinstance(basis, str) and basis.strip() else None
    if inert is None:
        return ('hybrid dry mass not published by the motor model'
                + (' (' + basis_txt + ')' if basis_txt else ''))
    if prop is not None and prop > 0.0:
        beklenen = HYBRID_INERT_RULE_OF_THUMB_RATIO * prop
        if abs(inert - beklenen) <= _RULE_OF_THUMB_REL_TOL * abs(beklenen):
            return (f'estimated as ~{HYBRID_INERT_RULE_OF_THUMB_RATIO:g} x '
                    'propellant mass (hybrid dry mass has no component '
                    'breakdown)')
    note = ('dry mass computed by the motor structural model, NOT the '
            f'{HYBRID_INERT_RULE_OF_THUMB_RATIO:g} rule of thumb')
    if prop is not None and prop > 0.0:
        note += f'; measured dry/propellant ratio {inert / prop:.2f}'
    if basis_txt:
        note += '; basis: ' + basis_txt
    return note


def _hybrid_outer_diameter_m(eng: Dict) -> Tuple[Optional[float], str]:
    """Hibrit motorun DIŞ çapı [m] (P4B3-08).

    Şema beyanı (modül başlığı) 'motor dış çapı' diyor ve kardeş katı kol
    gerçekten kasa DIŞ çapını koyuyor (``cad_design.case_design.
    outer_diameter``). Hibrit kol ise ``chamber_diameter``, yani kamara
    DELİĞİNİ yayımlıyordu. ÖLÇÜLDÜ (3 kN N2O/HTPB): yayımlanan 112,214 mm
    ⟷ gerçek dış çap 135,632 mm (iç çap + 2×11,709 mm cidar), −%17,3;
    launch_site.html gövde çapının ALT SINIRINI bu sayıdan kuruyor →
    S_ref %46,1 eksik, apoje +%2,27 iyimser.

    Dış çap yapısal analizden (iç çap + 2×cidar) kurulur. Yapısal blok yoksa
    UYDURULMAZ: kamara çapına düşülür (bugünkü davranış korunur; cidar
    bilinmiyorsa bir kalınlık icat edilmez).
    """
    ca = _get(eng, 'structural_analysis', 'chamber_analysis') or {}
    ic_mm = _num(ca.get('diameter'))                    # mm, İÇ çap
    cidar_mm = _num(ca.get('wall_thickness_used_mm'))
    if ic_mm is None:
        ic_mm = _num(ca.get('inner_diameter_mm'))
    if cidar_mm is None:
        cidar_mm = _num(ca.get('wall_thickness_mm'))
    if ic_mm is not None and cidar_mm is not None and cidar_mm >= 0.0:
        return ((ic_mm + 2.0 * cidar_mm) / 1000.0,
                'structural_analysis.chamber_analysis (mm, declared by name)')
    # P15B2-03: kamara çapına düşerken birim TİPTEN DEĞİL, üreticinin
    # beyanından kazanılır. Kazanılamazsa sayı üretilmez.
    return _length_m(eng, 'chamber_diameter')


def _resolve_name(motor_name: Any, results: Dict, motor_type: str) -> str:
    """Araç adını çöz: açık ad > sonuç sözlüğü > motor tipine göre varsayılan."""
    if isinstance(motor_name, str) and motor_name.strip():
        return motor_name.strip()
    candidates = [
        results.get('motor_name') if isinstance(results, dict) else None,
        _get(results, 'motor', 'motor_name'),
        _get(results, 'motor_geometry', 'motor_name'),
    ]
    for cand in candidates:
        if isinstance(cand, str) and cand.strip():
            return cand.strip()
    return _DEFAULT_NAMES.get(motor_type, 'Motor')


# --- Motor-tipine özel normalize'lar ---------------------------------------

def _normalize_hybrid(results: Dict) -> Dict[str, Any]:
    """Hibrit motor sonucu -> uçan-araç şeması.

    Gerçek alan adları (hrma/engines/hybrid_rocket_engine.py):
      thrust (:997), burn_time (:1041), propellant_mass_total (:1032),
      chamber_diameter (:1013, METRE), design_summary.key_dimensions.
      {dry_mass_estimate_kg (:1242, =0.25*prop TAHMİN),
       total_motor_length_mm (:1240)}.
    ``/calculate`` sonucu {motor: {...}, ...} sarmalar; recompute doğrudan
    derlenmiş dict döndürür — ikisi de desteklenir (unwrap).
    thrust_curve: kullanıcı transient çalıştırdıysa motor.transient
    {time, thrust} (transient_panel.js:165); yoksa None.
    """
    eng = results.get('motor') if isinstance(results.get('motor'), dict) else results
    kd = _get(eng, 'design_summary', 'key_dimensions') or {}

    inert = _num(kd.get('dry_mass_estimate_kg'))
    prop = _num(eng.get('propellant_mass_total'))
    transient = eng.get('transient') if isinstance(eng.get('transient'), dict) else {}
    curve = _curve(transient.get('time'), transient.get('thrust'))
    od_m, od_kaynak = _hybrid_outer_diameter_m(eng)

    return {
        'thrust_curve': curve,
        'thrust': _num(eng.get('thrust')),
        'burn_time': _num(eng.get('burn_time')),
        'propellant_mass': prop,
        'engine_inert_mass': inert,
        'engine_inert_mass_is_estimate': True,
        # P4B3-19: künye SABİT metin değil, yayımlanan sayıdan üretilir.
        'engine_inert_mass_note': _hybrid_inert_note(
            inert, prop, kd.get('dry_mass_basis')),
        # P4B3-08: alanın ADI DIŞ çap; kamara deliği değil (bkz. yardımcı).
        'engine_od_m': od_m,
        'engine_od_unit_source': od_kaynak,
        'engine_length_m': _mm_to_m(kd.get('total_motor_length_mm')),
    }


def _normalize_solid(results: Dict) -> Dict[str, Any]:
    """Katı motor sonucu -> uçan-araç şeması.

    Gerçek alan adları (hrma/engines/solid_rocket_engine.py):
      thrust_curve {time, thrust, ...} (:4381, top-level),
      average_thrust (:4357), burn_time (:4356), propellant_mass (:4363),
      design_summary.masses.dry_mass_kg (:4322, propelan HARİÇ),
      design_summary.key_dimensions.total_length_mm (:4306),
      cad_design.case_design.outer_diameter (:2483, MİLİMETRE).
    """
    masses = _get(results, 'design_summary', 'masses') or {}
    kd = _get(results, 'design_summary', 'key_dimensions') or {}
    tc = results.get('thrust_curve') if isinstance(results.get('thrust_curve'), dict) else {}

    # Dış çap: kasa dış çapı (cad_design) tercih; yoksa hazne çapı.
    # P15B2-03: tercih sırası DEĞİŞMEDİ, birim çıkarımı değişti — hazne
    # çapına düşülürken birim artık üreticinin beyanından kazanılır
    # ('solid = mm' tip tablosu ürünün dışındaydı).
    od_mm = _get(results, 'cad_design', 'case_design', 'outer_diameter')
    if od_mm is not None:
        od_m = _mm_to_m(od_mm)
        od_kaynak = 'cad_design.case_design.outer_diameter (mm, declared by name)'
    else:
        od_m, od_kaynak = _length_m(results, 'chamber_diameter')

    return {
        'thrust_curve': _curve(tc.get('time'), tc.get('thrust')),
        'thrust': _num(results.get('average_thrust')),
        'burn_time': _num(results.get('burn_time')),
        'propellant_mass': _num(results.get('propellant_mass')),
        'engine_inert_mass': _num(masses.get('dry_mass_kg')),
        'engine_inert_mass_is_estimate': False,
        'engine_inert_mass_note': None,
        'engine_od_m': od_m,
        'engine_od_unit_source': od_kaynak,
        'engine_length_m': _mm_to_m(kd.get('total_length_mm')),
    }


def _liquid_overall_length_m(results: Dict, kd: Dict) -> Optional[float]:
    """Sıvı motorun TOPLAM boyu [m] (P4B3-09).

    Aynı yanıtta İKİ toplam boy yayımlanıyor ve normalize sessizce KISA
    olanı seçiyordu. ÖLÇÜLDÜ (10 kN LOX/RP-1):
      ``design_summary.key_dimensions.overall_length_mm`` = 209,499 mm
          (= kamara + ıraksak; YAKINSAK bölüm DÜŞMÜŞ — motorun kendi
          kaynağında ``cooling['chamber_length'] + nozzle_length*1000``)
      ``component_sizing.component_dimensions.overall_length`` = 0,270858 m
          (= kamara + yakınsak + ıraksak, METRE)
    Fark %+29,29. launch_site.html gövde boyu alt sınırını (boy + 1,0 m) bu
    sayıdan kuruyor, yani kısa değer aracı sistematik olarak kısaltıyordu.

    Seçim kuralı: bileşen boyutlandırmasının TAM toplamı varsa o kullanılır
    (üç bölümü de içerir); yoksa key_dimensions'ın mm değerine düşülür.
    Sayı uydurulmaz — iki kaynak da yoksa ``None``.
    """
    tam_m = _num(_get(results, 'component_sizing', 'component_dimensions',
                      'overall_length'))          # METRE
    kisa_m = _mm_to_m(kd.get('overall_length_mm'))
    if tam_m is not None:
        # Kısa kaynak yoksa da tam kaynak meşrudur; ikisi varsa TAM olan
        # (yakınsak bölümü içeren) seçilir.
        if kisa_m is None or tam_m >= kisa_m:
            return tam_m
    return kisa_m


def _liquid_inert_mass(results: Dict,
                       engine_dry: Optional[float]
                       ) -> Tuple[Optional[float], Optional[str]]:
    """Sıvı motorun UÇAN atıl kütlesi [kg] + künyesi (P4B3-20).

    Eski hâli motorun kuru kütlesini "tahmin değil / not yok" damgasıyla
    yayımlıyordu. ÖLÇÜLDÜ (10 kN LOX/RP-1): atıl kütle 43,503 kg iken
    ``propellant_tanks.system_summary.total_tank_mass`` = 77,955 kg (motor
    atıl kütlesinin 1,79 KATI) şemada hiç yoktu; yüklenen ⟷ nominal propelan
    farkı 153,793 kg da yoktu → 231,7 kg gerçek uçan kütle hiçbir alanda
    görünmüyordu.

    ÇİFT-SAYIM (TUZAK2) yasağı EKSİK sayımı meşrulaştırmaz: 6-DOF kuru
    kütlesi ``airframe_dry_mass + engine_inert_mass``tır ve tank yapısı iki
    toplamın da dışında kalırsa uçmayan bir araç çözülür. Tank KURU yapısı
    ve YANMAYAN (rezerv) propelan uçuş boyunca ölü ağırlıktır; ikisi de
    ``propellant_mass``ın (nominal yanan kütle) dışındadır, yani eklemek
    çift sayım DEĞİLDİR.

    Sayı uydurulmaz: alan yoksa eklenmez ve künye neyin DIŞARIDA kaldığını
    söyler (fail-closed künye).
    """
    if engine_dry is None:
        return None, ('engine dry mass not published by the motor model; '
                      'tank structure and residual propellant are therefore '
                      'not accounted for either')
    ss = _get(results, 'propellant_tanks', 'system_summary') or {}
    tank = _num(ss.get('total_tank_mass'))
    yuklenen = _num(ss.get('total_propellant_mass'))
    nominal = _num(ss.get('total_propellant_mass_nominal'))
    artik = None
    if yuklenen is not None and nominal is not None and yuklenen > nominal:
        artik = yuklenen - nominal

    toplam = engine_dry
    parcalar = [f'engine dry mass {engine_dry:.3f} kg']
    if tank is not None and tank > 0.0:
        toplam += tank
        parcalar.append(f'propellant tank dry structure {tank:.3f} kg')
    if artik is not None and artik > 0.0:
        toplam += artik
        parcalar.append(
            f'loaded-minus-nominal (reserve) propellant {artik:.3f} kg')

    if len(parcalar) == 1:
        return toplam, ('engine dry mass only: this result publishes no '
                        'propellant tank mass, so tank structure and any '
                        'residual propellant are NOT included')
    return toplam, ('flying inert mass = ' + ' + '.join(parcalar)
                    + '; the nominal burned propellant is reported separately '
                      '(no double counting)')


def _normalize_liquid(results: Dict) -> Dict[str, Any]:
    """Sıvı motor sonucu -> uçan-araç şeması.

    Gerçek alan adları (hrma/engines/liquid_rocket_engine.py):
      thrust (:3625), burn_time (:3702), design_summary.masses.
      propellant_mass_kg (:3770, = mdot_total*burn_time),
      chamber_diameter (:3658, MİLİMETRE),
      design_summary.key_dimensions.overall_length_mm (:3763).

    engine_inert_mass: TAM motor kuru kütlesi
    ``design_summary.masses.engine_mass_kg`` (= component_sizing.
    total_dry_mass = chamber+nozzle+injector+turbopump+feed+controls, :5835).
    NOT (spec sapması, gerekçeli): spec ``feed_system.total_mass`` (:1225)
    diyordu; ancak o değer YALNIZCA feed_lines+turbopump (:4316), yani tam
    kuru kütlenin ALT KÜMESİ. Uçan araç için komple motor atıl kütlesi
    gerekir. Her iki değer de propelan hariç (çift-sayım güvenli); engine_mass_kg
    fiziksel olarak doğru olan. feed_system.total_mass yalnız son çare fallback.
    """
    masses = _get(results, 'design_summary', 'masses') or {}
    kd = _get(results, 'design_summary', 'key_dimensions') or {}

    prop = _num(masses.get('propellant_mass_kg'))
    if prop is None:
        mdot = _num(results.get('total_mass_flow'))
        bt = _num(results.get('burn_time'))
        if mdot is not None and bt is not None:
            prop = mdot * bt

    inert = _num(masses.get('engine_mass_kg'))
    if inert is None:
        inert = _num(results.get('engine_mass_estimate'))
    if inert is None:
        inert = _num(_get(results, 'feed_system', 'total_mass'))
    inert, inert_note = _liquid_inert_mass(results, inert)
    od_m, od_kaynak = _length_m(results, 'chamber_diameter')

    return {
        # Kararlı sonuç itki eğrisi taşımaz (transient sıvıda modellenmiyor).
        'thrust_curve': None,
        'thrust': _num(results.get('thrust')),
        'burn_time': _num(results.get('burn_time')),
        'propellant_mass': prop,
        # P4B3-20: uçan atıl kütle tankları ve artık propelanı İÇERİR;
        # içeremediğinde bunu künyede SÖYLER.
        'engine_inert_mass': inert,
        'engine_inert_mass_is_estimate': False,
        'engine_inert_mass_note': inert_note,
        # P15B2-03: birim TİPTEN değil, üreticinin beyanından kazanılır.
        'engine_od_m': od_m,
        'engine_od_unit_source': od_kaynak,
        # P4B3-09: aynı yanıttaki İKİ toplam boydan TAM olanı seçilir.
        'engine_length_m': _liquid_overall_length_m(results, kd),
    }


_NORMALIZERS = {
    'hybrid': _normalize_hybrid,
    'solid': _normalize_solid,
    'liquid': _normalize_liquid,
}


# --- Genel API --------------------------------------------------------------

def normalize(motor_type: str, results: Dict,
              motor_name: Optional[str] = None,
              source: str = 'results') -> Dict[str, Any]:
    """Motor sonucunu tek "uçan araç" şemasına indirge.

    Parametreler
    ------------
    motor_type : 'hybrid' | 'solid' | 'liquid'
    results    : ilgili ``/calculate*`` route'unun ürettiği sonuç sözlüğü
                 (hybrid'de {motor: {...}} sarmalı da kabul edilir).
    motor_name : açık ad; verilmezse sonuçtan/varsayılandan çözülür.
    source     : 'results' (oturum köprüsü) | 'project' (.hrma recompute) |
                 'example' (demo araç).

    Dönüş: modül başındaki şema. Eksik alanlar ``None`` olur (uydurma yok).
    """
    mt = (motor_type or '').strip().lower()
    if mt not in _MOTOR_TYPES:
        raise ValueError(
            f'unknown motor_type {motor_type!r}; expected one of {_MOTOR_TYPES}')
    if not isinstance(results, dict):
        raise TypeError('results must be a dict')

    vehicle = _NORMALIZERS[mt](results)
    vehicle['motor_type'] = mt
    vehicle['motor_name'] = _resolve_name(motor_name, results, mt)
    vehicle['source'] = source
    return vehicle


# --- .hrma projesinden yeniden hesap (recompute) ---------------------------

def recompute_from_project(doc: Dict) -> Tuple[str, Dict]:
    """Kaydedilmiş .hrma belgesinden motoru YENİDEN hesapla.

    ``doc``: ``projects.load_project()`` ile okunmuş belge. ``motor_type`` ve
    ``inputs.fields`` (DOM id -> değer) alanlarını kullanır.

    Dönüş: ``(motor_type, results)`` — ``results`` ilgili ``/calculate*``
    route'unun ürettiğiyle AYNI şekildedir ve doğrudan :func:`normalize`'a
    verilebilir. Route ince kalsın diye tüm motor kurulumu burada yapılır.

    NEDEN recompute: .hrma yalnızca girdi (``inputs.fields``) + düz-skaler
    ``results_summary`` saklar (projects.py). thrust_curve / propellant_mass /
    boyutlar diskte YOK; tek dürüst yol motoru yeniden koşmaktır.

    KEŞİF (app.js getFormData / solid+liquid form): request anahtarı == DOM id
    olduğundan ``inputs.fields`` doğrudan motor girdisi olarak beslenebilir;
    bilinen tek istisna ``atmospheric_pressure <- single_pressure`` (hibrit).
    """
    if not isinstance(doc, dict):
        raise TypeError('doc must be a dict')
    motor_type = (doc.get('motor_type') or '').strip().lower()
    fields = _get(doc, 'inputs', 'fields')
    if not isinstance(fields, dict):
        fields = {}

    if motor_type == 'hybrid':
        return 'hybrid', _recompute_hybrid(fields)
    if motor_type == 'solid':
        return 'solid', _recompute_solid(fields)
    if motor_type == 'liquid':
        return 'liquid', _recompute_liquid(fields)
    raise ValueError(
        f'unknown motor_type {doc.get("motor_type")!r} in project document')


#: Uydurma-veri-yasağının recompute tarafındaki künye alanları (P4B3-04).
#: İkisi de yalnızca GERÇEKTEN ikame yapıldığında konur; ikame yoksa
#: sonuç sözlüğü eskisiyle bit-aynı kalır.
SUBSTITUTION_FIELD_KEY = 'input_defaults_substituted'
SUBSTITUTION_NOTE_KEY = 'input_defaults_substituted_note'


def _f(fields: Dict, key: str, default: Any = None,
       _substituted: Optional[List[str]] = None) -> Any:
    """Alanı oku; boş string/None -> default (form boş bırakmışsa).

    ÖH defter P4B3-04 — İKAME ARTIK SESSİZ DEĞİL. ``normalize`` eksik alanı
    ``None`` yaparken (uydurma-veri-yasağı) bu kol sessizce varsayılan
    koyuyordu: ÖLÇÜLDÜ (27 Ağu 2026) BOŞ ``inputs.fields`` ile katı motor
    64 anahtarlı TAM sonuç üretiyordu (6739,134 N / 2,186 s / 6,468 kg) ve
    "girdi eksik, varsayılan kullanıldı" diyen tek bir kayıt yoktu; kardeş
    kollarda da aynı (sıvı 63 anahtar 10000 N, hibrit 112 anahtar 1000 N).
    TEK eksik alan aracı sessizce değiştiriyordu (hazne basıncı çıkarılınca
    itki 8628,123 → 6739,134 N, −%21,9; atıl kütle 9,695 → 5,540 kg, −%42,9).

    ``_substituted`` verilirse, UYDURULAN bir değer (default is not None)
    kondu­ğunda alan adı oraya yazılır. ``default is None`` olan çağrılar
    ikame sayılmaz: orada bir sayı icat edilmiyor, eksiklik motora
    "verilmedi" olarak geçiyor.
    """
    if key not in fields:
        if _substituted is not None and default is not None:
            _substituted.append(key)
        return default
    v = fields[key]
    if v is None or (isinstance(v, str) and v.strip() == ''):
        if _substituted is not None and default is not None:
            _substituted.append(key)
        return default
    return v


def _declare_substitutions(results: Any, substituted: List[str]) -> Any:
    """İkame edilen alan adlarını sonuç sözlüğüne KÜNYE olarak ekle.

    İkame yoksa sözlüğe DOKUNULMAZ (sağlıklı yol bit-aynı kalır).
    """
    if not substituted or not isinstance(results, dict):
        return results
    adlar = sorted(set(substituted))
    results[SUBSTITUTION_FIELD_KEY] = adlar
    results[SUBSTITUTION_NOTE_KEY] = (
        'these inputs were MISSING from the saved project and were replaced '
        'by module defaults, so the numbers below are not fully the '
        "user's own design: " + ', '.join(adlar))
    return results


def _recompute_hybrid(fields: Dict) -> Dict:
    """Hibrit motoru fields'ten yeniden hesapla (/calculate ile aynı kurulum)."""
    from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
    eksik: List[str] = []
    # Birincil anahtar atmospheric_pressure; form DOM id'i single_pressure.
    # İKİSİ DE yoksa ikame vardır; biri varsa yoktur (iç içe ``_f`` çağrısı
    # kaydediciyle sarılırsa var olan alan da "ikame" sanılırdı).
    _atm = _f(fields, 'atmospheric_pressure', _f(fields, 'single_pressure'))
    if _atm is None:
        eksik.append('atmospheric_pressure')
        _atm = 1.0
    engine = HybridRocketEngine(
        thrust=_f(fields, 'thrust'),
        burn_time=_f(fields, 'burn_time'),
        total_impulse=_f(fields, 'total_impulse'),
        of_ratio=_f(fields, 'of_ratio', 1.0, eksik),
        chamber_pressure=_f(fields, 'chamber_pressure', 20.0, eksik),
        atmospheric_pressure=_atm,
        chamber_temperature=_f(fields, 'chamber_temperature'),
        gamma=_f(fields, 'gamma', 1.25, eksik),
        gas_constant=_f(fields, 'gas_constant'),
        l_star=_f(fields, 'l_star', 1.0, eksik),
        expansion_ratio=_f(fields, 'expansion_ratio', 0, eksik),
        nozzle_type=_f(fields, 'nozzle_type', 'conical', eksik),
        thrust_coefficient=_f(fields, 'thrust_coefficient', 0, eksik),
        regression_a=_f(fields, 'regression_a'),
        regression_n=_f(fields, 'regression_n'),
        fuel_density=_f(fields, 'fuel_density'),
        combustion_type=_f(fields, 'combustion_type', 'infinite', eksik),
        chamber_diameter_input=_f(fields, 'chamber_diameter_input', 0, eksik),
        fuel_type=_f(fields, 'fuel_type', 'htpb', eksik),
        oxidizer_type=_f(fields, 'oxidizer_type', 'n2o', eksik),
        injector_type=_f(fields, 'injector_type', 'showerhead', eksik),
        initial_port_diameter=_f(fields, 'initial_port_diameter') or None,
        initial_gox=_f(fields, 'mass_flux_chamber') or None,
        tank_temperature=_f(fields, 'oxidizer_temp') or None,
        motor_name=_f(fields, 'motor_name', ''),
        motor_description=_f(fields, 'motor_description', ''),
    )
    return _declare_substitutions(engine.calculate(), eksik)


def _recompute_solid(fields: Dict) -> Dict:
    """Katı motoru fields'ten yeniden hesapla (/calculate_solid ile aynı)."""
    from hrma.engines.solid_rocket_engine import SolidRocketEngine
    eksik: List[str] = []
    motor = SolidRocketEngine(
        grain_type=_f(fields, 'grain_type', 'bates', eksik),
        propellant_type=_f(fields, 'propellant_type', 'apcp', eksik),
        chamber_diameter=_f(fields, 'chamber_diameter', 100, eksik),
        grain_length=_f(fields, 'grain_length', 500, eksik),
        core_diameter=_f(fields, 'core_diameter', 30, eksik),
        chamber_pressure=_f(fields, 'chamber_pressure', 40, eksik),
        burn_rate_a=_f(fields, 'burn_rate_a', 0.005, eksik),
        burn_rate_n=_f(fields, 'burn_rate_n', 0.35, eksik),
        overrides=dict(fields),
    )
    return _declare_substitutions(motor.calculate_performance(), eksik)


def _recompute_liquid(fields: Dict) -> Dict:
    """Sıvı motoru fields'ten yeniden hesapla (/calculate_liquid ile aynı)."""
    from hrma.engines.liquid_rocket_engine import LiquidRocketEngine
    eksik: List[str] = []
    engine = LiquidRocketEngine(
        thrust=_f(fields, 'thrust', 10000, eksik),
        chamber_pressure=_f(fields, 'chamber_pressure', 100, eksik),
        mixture_ratio=_f(fields, 'mixture_ratio', 2.5, eksik),
        fuel_type=_f(fields, 'fuel_type', 'rp1', eksik),
        oxidizer_type=_f(fields, 'oxidizer_type', 'lox', eksik),
        cooling_type=_f(fields, 'cooling_type', 'regenerative', eksik),
        injector_type=_f(fields, 'injector_type', 'impinging', eksik),
        overrides=dict(fields),
    )
    return _declare_substitutions(engine.calculate_performance(), eksik)
