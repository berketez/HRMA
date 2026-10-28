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
    'engine_inert_mass': float | None,  # [kg] UÇAN ATIL KÜTLE (nominal yanan itici hariç)
    'engine_inert_mass_is_estimate': bool,
    'engine_inert_mass_note': str | None,
    'engine_od_m': float | None,        # motor dış çapı [m]
    'engine_od_unit_source': str|None,  # dış çapın birimi NASIL kazanıldı
    'engine_length_m': float | None,    # motor toplam boyu [m]
    'source': str,                      # 'results'|'project'|'example'
  }

ADI VE ETİKETİ (V301/HİBRİT-DIŞA, 28 Eki): ``engine_inert_mass`` motorun
uçuşta araca kattığı ATIL kütledir — arayüzde "Flying inert mass" / "Uçan atıl
kütle", künyesi ``engine_inert_mass_note``. Hibrit/katıda motor kuru
kütlesidir; sıvıda motor kuru kütlesi + itici tankı kuru yapısı + yüklenen eksi
nominal (yedek) itici (``_liquid_inert_mass``). ÖLÇÜLDÜ (örnek sıvı): JSON'da
``design_summary.masses.engine_mass_kg`` ile bu alan FARKLI büyüklüklerdir
(motor ⟷ uçan atıl), aynı adla gösterilmez. Alan adı DEĞİŞMEDİ: araç şemasının
anahtarıdır (6-DOF, Fırlatma Sahası, FlightHandoff localStorage kaydı, kayıtlı
araçlar) ve anlamı aynı kayıttaki künyeyle beyanlıdır.

ÇİFT-SAYIM TUZAĞI (spec TUZAK2): ``engine_inert_mass`` ATIL kütledir;
nominal yanan propelanı İÇERMEZ. 6-DOF çözücüsü toplam kuru kütleyi
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


#: V301/FİZİK-2 (kalem 6, KABUL 13-14): çizilen lüle dış zarfının künyesi.
DRAWN_NOZZLE_ENVELOPE_SOURCE = (
    'drawn nozzle outer profile (hrma.export.cad_visualization.'
    'nozzle_wall_profile, the profile the STEP/STL nozzle solid is revolved '
    'from: inner contour + nozzle wall, or + the two-layer jacket stack)')


#: Profilin boğaz/çıkış çapı ⟷ motorun yayımladığı çap eşleşme toleransı
#: (bağıl). Aynı sayının mm ⟷ m dönüşümü ve kayan nokta payı; fizik eşiği
#: değildir (ölçülen gerçek fark 0).
ENVELOPE_PROFILE_MATCH_REL_TOL = 1e-9


def _drawn_nozzle_outer_od_m(motor: Any) -> Tuple[Optional[float], str]:
    """Çizilen lülenin EN BÜYÜK dış çapı [m] — CAD'in katı profili (tek kaynak).

    V301/FİZİK-2 (kalem 6). ÖLÇÜLDÜ (KABUL K3; docs/scofield/raw/OH/V301/
    fizik-2/k6_olcu_once.json): uçuş aracı gövde zarfını lüle çıkışının İÇ
    çapından kuruyordu — sıvı 189,555 mm ⟷ çizilen 200,5 mm (ceket), katı
    89 mm (kasa) ⟷ çizilen lüle 91 mm. Zarf artık STEP/STL lüle katısının
    kurulduğu profilden okunur (CAD'in kendi girdi normalleştirmesiyle,
    STEP'in çağrısıyla aynı ``require_solved_length=True``). Profil
    çözülemezse ``None`` + neden: çağıran eski kuralı beyanla sürdürür.
    """
    if not isinstance(motor, dict):
        return None, 'no motor result'
    try:
        import copy
        from hrma.export.cad_visualization import nozzle_wall_profile
        from hrma.export.motor_geometry import normalise_export_geometry
        md, _rapor = normalise_export_geometry(copy.deepcopy(motor))
        prof = nozzle_wall_profile(md, unit='mm', require_solved_length=True)
        r_max = max(float(r) for _z, r in prof['outer'])
        meta = prof.get('meta') or {}
    except Exception as exc:          # noqa: BLE001 — neden adıyla döner
        return None, ('drawn nozzle profile not resolved (%s)'
                      % type(exc).__name__)
    # Profil MOTORUN kendi boğaz ve çıkış çapıyla kurulmuş olmalı: eksik
    # sonuçta CAD genel yedek geometriyle (ör. 20 mm boğaz) çizer; o profil
    # bu motorun zarfı değildir, benimsenmez (eski kural beyanla sürer).
    for alan, anahtar in (('throat_diameter', 'r_throat'),
                          ('exit_diameter', 'r_exit')):
        d_m = _num(md.get(alan))
        r_mm = _num(meta.get(anahtar))
        if d_m is None or r_mm is None or abs(2.0 * r_mm / 1000.0 - d_m) > (
                ENVELOPE_PROFILE_MATCH_REL_TOL * d_m):
            return None, ('drawn nozzle profile is not built from this '
                          'motor\'s own %s' % alan)
    od = _num(2.0 * r_max / 1000.0)
    if od is None or od <= 0.0:
        return None, 'drawn nozzle profile has no positive radius'
    return od, DRAWN_NOZZLE_ENVELOPE_SOURCE


def _drawn_chamber_outer_od_m(motor: Any) -> Tuple[Optional[float], str]:
    """Çizilen kamaranın dış çapı [m] = delik + 2 × CAD'in çizdiği cidar.

    V301/FİZİK-2 (kalem 6): sıvıda zarfın kamara terimi İÇ kamara çapıydı.
    Cidar CAD'in 3B katı, kütle ve zarf için okuduğu TEK işlevden
    (``cad_visualization._chamber_wall_effective_m``; iki katmanlı cidarda
    yığın). Çözülemezse ``None`` + neden.
    """
    if not isinstance(motor, dict):
        return None, 'no motor result'
    try:
        import copy
        from hrma.export.cad_visualization import _chamber_wall_effective_m
        from hrma.export.motor_geometry import normalise_export_geometry
        md, _rapor = normalise_export_geometry(copy.deepcopy(motor))
        d_m = _num(md.get('chamber_diameter'))
        cidar_m, cidar_kaynak = _chamber_wall_effective_m(md, d_m)
    except Exception as exc:          # noqa: BLE001
        return None, ('drawn chamber wall not resolved (%s)'
                      % type(exc).__name__)
    if d_m is None or _num(cidar_m) is None:
        return None, 'drawn chamber wall not resolved'
    if 'fallback' in str(cidar_kaynak).lower():
        # CAD'in genel yedek cidarı bu motorun cidarı değildir.
        return None, 'drawn chamber wall is the CAD geometric fallback'
    return d_m + 2.0 * float(cidar_m), (
        'drawn chamber outer diameter (bore + 2 x wall from hrma.export.'
        'cad_visualization._chamber_wall_effective_m: %s)' % cidar_kaynak)


def _envelope_od_m(od_m: Optional[float], od_kaynak: str,
                   kd: Dict, motor: Any = None
                   ) -> Tuple[Optional[float], str]:
    """Motorun dış ZARFI [m]: kasa/kamara dış çapı ile lüle dış zarfının büyüğü.

    v3.0.1 (26 Eki 2026, son kullanıcı testi NK-47): fırlatma sahası gövde
    çapının alt sınırını ``engine_od_m``den kuruyor (launch_site.html
    ``applyVehicle``). Sıvıda bu alan iç kamara çapıydı (örnek 25 kN
    LOX/RP-1: 109,4 mm) ve 189,6 mm'lik lüle çıkışı hesaba girmiyordu; 0,15 m
    gövdeli bir araç bu motorla 231 km apojeye "uçuyordu". Lüle çıkışı
    motorun dış zarfının parçasıdır: gövde ondan küçük olamaz.

    V301/FİZİK-2 (kalem 6): lüle terimi artık ÇİZİLEN dış zarftır
    (``_drawn_nozzle_outer_od_m``; et ve ceket dahil). Profil çözülemezse
    eski kural sürer: çıkış İÇ çapı yanıtın ``design_summary.key_dimensions``
    alanından (mm, adıyla); o da yayımlanmamışsa UYDURULMAZ, eski değer ve
    kaynağı aynen kalır.
    """
    cizilen_od, cizilen_kaynak = _drawn_nozzle_outer_od_m(motor)
    if cizilen_od is not None:
        if od_m is None or cizilen_od > od_m:
            return cizilen_od, (cizilen_kaynak + ' — larger than the '
                                f'case/chamber outer diameter ({od_kaynak}); '
                                'the body must enclose the drawn nozzle')
        return od_m, od_kaynak
    cikis_mm = _num(kd.get('nozzle_exit_mm'))
    alan = 'design_summary.key_dimensions.nozzle_exit_mm'
    if cikis_mm is None:
        cikis_mm = _num(kd.get('nozzle_exit_diameter_mm'))
        alan = 'design_summary.key_dimensions.nozzle_exit_diameter_mm'
    if cikis_mm is None or cikis_mm <= 0.0:
        return od_m, od_kaynak
    cikis_m = cikis_mm / 1000.0
    if od_m is None or cikis_m > od_m:
        return cikis_m, (f'nozzle exit diameter ({alan}, mm) — larger than '
                         f'the case/chamber diameter ({od_kaynak}); the body '
                         'must enclose the nozzle exit')
    return od_m, od_kaynak


def _ilk_sayi(kd: Dict, *anahtarlar: str) -> Optional[float]:
    """``kd`` içinde ilk SONLU sayı olan anahtarın değeri (yoksa None)."""
    for anahtar in anahtarlar:
        deger = _num(kd.get(anahtar))
        if deger is not None:
            return deger
    return None


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
    od_m, od_kaynak = _envelope_od_m(*_hybrid_outer_diameter_m(eng), kd,
                                     eng)

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
        # V301/FİZİK-2 (kalem 6): THE toplam boy CAD-2'nin tek tanımı
        # (ön kapak + oda + çizilen lüle); yoksa eski kapaksız toplam.
        'engine_length_m': _mm_to_m(_ilk_sayi(
            kd, 'total_motor_length_with_caps_mm',
            'total_motor_length_mm')),
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
    od_m, od_kaynak = _envelope_od_m(od_m, od_kaynak, kd, results)

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
        # V301/FİZİK-2 (kalem 6): kapaklı toplam (kasa + çizilen lüle +
        # çizilen ön kapak) — hibritle aynı tanım; yoksa eski toplam.
        'engine_length_m': _mm_to_m(_ilk_sayi(
            kd, 'total_length_with_closure_mm', 'total_length_mm')),
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
    # V301/FİZİK-2 (kalem 6): kamara terimi ÇİZİLEN dış çap (delik + 2 ×
    # CAD cidarı); çözülemezse eski iç çap okuması adıyla kalır.
    kamara_od, kamara_kaynak = _drawn_chamber_outer_od_m(results)
    if kamara_od is None:
        kamara_od, kamara_kaynak = _length_m(results, 'chamber_diameter')
    od_m, od_kaynak = _envelope_od_m(kamara_od, kamara_kaynak, kd, results)

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
        # V301/FİZİK-2 (kalem 6): kapaklı toplam (çizilen düz kapak +
        # kamara + yakınsak + ıraksak) — hibrit/katıyla aynı tanım.
        'engine_length_m': (
            _mm_to_m(kd.get('overall_length_with_closure_mm'))
            if _num(kd.get('overall_length_with_closure_mm'))
            is not None else _liquid_overall_length_m(results, kd)),
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




# --- Gövde ⟷ motor uygunluğu (NK-47, TEK işlev) -----------------------------

def airframe_fit_conflicts(engine_od_m: Any, engine_length_m: Any,
                           body_diameter_m: Any,
                           body_length_m: Any) -> List[Dict[str, Any]]:
    """Gövde bu motoru TAŞIYABİLİR mi? Çelişki listesi (boş = uygun).

    V301/UÇUŞ NK-47 (son kullanıcı testi 26 Eki): Fırlatma Sahası 189,6 mm
    lüle çıkışlı sıvı motoru 0,15 m gövdeyle uyarısız 231 km'ye
    "uçuruyordu"; aynı motoru sıvı sayfasının 6-DOF paneli "bu gövde bu
    motoru taşıyamaz" diye işaretliyordu. İki yer iki ayrı hüküm veriyordu.
    Hüküm artık TEK yerdedir: ``/api/six-dof-analysis`` bu işlevi motor
    zarfı (``engine_od_m`` / ``engine_length_m`` — :func:`normalize`ın
    yayımladığı alanlar) istekte geldiğinde çağırır; iki sayfa da aynı ucu
    çağırır.

    Kural (yeni eşik İCAT EDİLMEZ — geometrinin kendisi): gövde dış çapı
    motorun dış zarfından (kasa/kamara dış çapı ile lüle çıkış çapının
    büyüğü) küçük olamaz; gövde boyu motor boyundan kısa olamaz. Zarf ya da
    gövde ölçüsü bilinmiyorsa (``None``) o denetim YAPILMAZ ve bir sayı
    uydurulmaz.
    """
    od = _num(engine_od_m)
    boy = _num(engine_length_m)
    cap = _num(body_diameter_m)
    gboy = _num(body_length_m)
    out: List[Dict[str, Any]] = []
    if od is not None and od > 0.0 and cap is not None and cap < od:
        out.append({
            'field': 'body_diameter', 'reason': 'body_narrower_than_engine',
            'body_diameter_m': cap, 'engine_od_m': od, 'unit': 'm',
            'message': (
                f'The body outer diameter {cap * 1000.0:.1f} mm is smaller '
                f'than the engine envelope {od * 1000.0:.1f} mm (case/chamber '
                'outer diameter or nozzle exit, whichever is larger): this '
                'airframe cannot carry this engine.'),
        })
    if boy is not None and boy > 0.0 and gboy is not None and gboy < boy:
        out.append({
            'field': 'body_length', 'reason': 'body_shorter_than_engine',
            'body_length_m': gboy, 'engine_length_m': boy, 'unit': 'm',
            'message': (
                f'The body length {gboy:.3f} m is shorter than the engine '
                f'length {boy:.3f} m: this airframe cannot carry this engine.'),
        })
    return out


# --- .hrma projesinden yeniden hesap (recompute) ---------------------------
#
# V301/UÇUŞ C-1 (27 Eki 2026) — KAYITLI PROJE, SAYFANIN HESAPLADIĞI MOTORU
# UÇURUR. Eskiden burada üç ``_recompute_*`` işlevi motoru KENDİSİ kuruyordu:
# modül yedekleri (``chamber_diameter 100``, ``thrust 10000`` …) ve sayfa
# ucunun geçirdiği argümanların bir kısmıyla. ÖLÇÜLDÜ (26 Eki 15:00 +
# ``docs/scofield/raw/OH/V301/ucus/c1_once.json``): katı örnekte kuru kütle
# uç 3,0898 ⟷ proje 4,5536 kg, dış çap 83 ⟷ 104,8 mm (kasa 100 mm modül
# yedeği); hibrit örnekte itici 14,5406 ⟷ 12,9457 kg, kuru 11,1953 ⟷
# 9,6418 kg (η_c* ve /calculate'in ~10 argümanı geçmiyordu). Yani Fırlatma
# Sahası "kayıtlı proje" seçildiğinde motor sayfasında hesaplanandan BAŞKA
# bir motor uçuruyordu.
#
# Bugünkü kural: recompute motor KURMAZ. Sayfanın çağırdığı hesap ucunun
# GÖVDESİNİ (``/calculate``, ``/calculate_solid``, ``/calculate_liquid``)
# aynı yükle koşar ve ucun yanıt gövdesini olduğu gibi döndürür. Böylece
# girdi ayrıştırma, kapılar, beyanlı varsayılanlar (``defaults_applied``) ve
# adlı retler TEK yerde kalır: uçta. Eksik alan için recompute sayı
# UYDURMAZ; uç ne diyorsa (beyanlı varsayılan ya da adlı ret) o geçerlidir.

#: motor tipi -> sayfanın hesap ucu. TEK KAYNAK (kural #11):
#: ``tests/test_example_projects.ENDPOINTS`` bunu yeniden dışa aktarır.
CALCULATION_ENDPOINTS = {
    'hybrid': '/calculate',
    'solid': '/calculate_solid',
    'liquid': '/calculate_liquid',
}


def _is_number(value: Any) -> bool:
    """JSON sayısı mı (``bool`` hariç, sonlu)? Toplayıcının ``numById``ı."""
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and _num(value) is not None)


def page_payload(motor_type: str, fields: Any) -> Dict[str, Any]:
    """``inputs.fields`` (form alan kimlikleri) -> sayfanın hesap ucu yükü.

    V301/UÇUŞ C-1: eşleme ``tests/test_example_projects.calculate_payload``
    içindeydi (örnekleri üreten betik ve testler onu kullanıyordu); ürünün
    kendisi ise kayıtlı projeden motoru BAŞKA bir kurulumla hesaplıyordu.
    Eşleme artık ürünün tek yeridir; test adı yeniden dışa aktarımla
    içe aktarılabilir kalır.

    Katı ve sıvı sayfalarında toplayıcı (``collectAllParameters``) alan
    kimliğini yük anahtarı olarak birebir kullanır. Hibrit toplayıcı
    (``advanced.html::getFormData``) şu istisnaları taşır ve burada aynen
    yansıtılır:

      * ``single_pressure -> atmospheric_pressure`` (tek irtifa kipi),
      * ``total_impulse = thrust * burn_time`` (itki/süre kipinde; sayfa bunu
        yalnız İKİ alan da sayıyken gönderir — boş alanın çarpımı uydurulmaz),
      * ``contraction_ratio`` / ``mass_flux_chamber`` alan yoksa 0 (sayfa
        boş alanı 0 gönderir: "türet" sentineli),
      * ``calculate_trajectory`` alan yoksa ``False``: uçuş aracı motoru
        ister, hibrit sayfanın 2B yörünge ekini değil (motor sayıları bu
        bayraktan bağımsızdır — ölçüldü, ``c1_sayfa_once.json``: sayfa
        ``true`` gönderdiğinde de atıl kütle/itici/çap bit-aynı).
    """
    data = dict(fields) if isinstance(fields, dict) else {}
    if motor_type == 'hybrid':
        if 'single_pressure' in data:
            data['atmospheric_pressure'] = data.pop('single_pressure')
        if _is_number(data.get('thrust')) and _is_number(data.get('burn_time')):
            data['total_impulse'] = data['thrust'] * data['burn_time']
        data.setdefault('contraction_ratio', 0)
        data.setdefault('mass_flux_chamber', 0)
        data.setdefault('calculate_trajectory', False)
    return data


class ProjectCalculationRejected(ValueError):
    """Sayfanın hesap ucu kayıtlı projeyi HESAPLAMADI (HTTP != 200).

    ``status`` ve ``body`` ucun KENDİ yanıtıdır (adlı ret: ``error``,
    ``missing_fields``, ``invalid_fields`` …); çağıran onu aynen taşır —
    recompute ikinci bir gerekçe yazmaz, sayı da uydurmaz.
    ``ValueError`` alt sınıfıdır: eski çağıranların "fail-closed" dalı
    (``except (ValueError, KeyError)``) aynen çalışır.
    """

    def __init__(self, motor_type: str, endpoint: str, status: int,
                 body: Any):
        self.motor_type = motor_type
        self.endpoint = endpoint
        self.status = int(status)
        self.body = body if isinstance(body, dict) else {}
        neden = (self.body.get('error') or self.body.get('message')
                 or self.body.get('status') or 'no reason in the body')
        super().__init__(
            f'{endpoint} did not calculate the saved project '
            f'(HTTP {self.status}): {neden}')


def run_page_calculation(motor_type: str,
                         payload: Dict[str, Any]) -> Tuple[int, Any]:
    """Sayfanın hesap ucunun GÖVDESİNİ koşar: ``(HTTP durumu, JSON gövde)``.

    Uç gövdesi YENİDEN YAZILMAZ ve kopyalanmaz: Flask
    ``app.test_request_context`` ile aynı yol + aynı JSON gövdeyle bir istek
    bağlamı kurulur ve ucun görünüm işlevi doğrudan çağrılır. Dönen yanıt
    sayfanın aldığı yanıtın aynısıdır (aynı ``jsonify`` + ``sanitize``).
    Kökenler/gövde tavanı gibi taşıma kapıları (``before_request``) burada
    koşmaz: onlar dış isteğin (``/api/flight-vehicle``) kapılarıdır ve o
    istek onlardan zaten geçmiştir.
    """
    mt = (motor_type or '').strip().lower()
    if mt not in CALCULATION_ENDPOINTS:
        raise ValueError(
            f'unknown motor_type {motor_type!r}; expected one of {_MOTOR_TYPES}')
    yol = CALCULATION_ENDPOINTS[mt]
    from flask import request as _istek
    from hrma.app import app as _app
    with _app.test_request_context(yol, method='POST', json=payload):
        gorunum = _app.view_functions[_istek.url_rule.endpoint]
        yanit = _app.make_response(gorunum(**(_istek.view_args or {})))
        govde = yanit.get_json(silent=True)
    return yanit.status_code, govde


def recompute_from_project(doc: Dict) -> Tuple[str, Dict]:
    """Kaydedilmiş .hrma belgesinden motoru SAYFANIN HESAP UCUYLA hesapla.

    ``doc``: ``projects.load_project()`` ile okunmuş belge. ``motor_type`` ve
    ``inputs.fields`` (DOM id -> değer) alanlarını kullanır.

    Dönüş: ``(motor_type, results)`` — ``results`` ilgili ``/calculate*``
    ucunun YANIT GÖVDESİDİR (sayfanın ``currentResults``u ile aynı şekil;
    doğrudan :func:`normalize`'a verilebilir).

    NEDEN recompute: .hrma yalnızca girdi (``inputs.fields``) + düz-skaler
    ``results_summary`` saklar (projects.py). thrust_curve / propellant_mass /
    boyutlar diskte YOK; tek dürüst yol motoru sayfanın ucuyla yeniden
    hesaplamaktır.

    Uç projeyi hesaplamazsa (eksik zorunlu girdi, geçersiz geometri …)
    :class:`ProjectCalculationRejected` atılır ve ucun kendi adlı reddini
    taşır.
    """
    if not isinstance(doc, dict):
        raise TypeError('doc must be a dict')
    motor_type = (doc.get('motor_type') or '').strip().lower()
    if motor_type not in CALCULATION_ENDPOINTS:
        raise ValueError(
            f'unknown motor_type {doc.get("motor_type")!r} in project document')
    fields = _get(doc, 'inputs', 'fields')
    if not isinstance(fields, dict):
        fields = {}
    durum, govde = run_page_calculation(motor_type,
                                        page_payload(motor_type, fields))
    if durum != 200 or not isinstance(govde, dict) or govde.get('error'):
        raise ProjectCalculationRejected(
            motor_type, CALCULATION_ENDPOINTS[motor_type], durum, govde)
    return motor_type, govde
