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
    'engine_length_m': float | None,    # motor toplam boyu [m]
    'source': str,                      # 'results'|'project'|'example'
  }

ÇİFT-SAYIM TUZAĞI (spec TUZAK2): ``engine_inert_mass`` motorun ATIL (kuru)
kütlesidir; propelanı İÇERMEZ. 6-DOF çözücüsü toplam kuru kütleyi
``airframe_dry_mass + engine_inert_mass`` olarak, propelanı ise ayrı
(``propellant_mass``) alır. Aynı kütleyi iki kez saymamak için bu ayrım
zorunludur — normalize propelanı atıl kütleye ASLA eklemez.

BİRİM UYARISI (kod-teyitli): ``chamber_diameter`` motor tipine göre farklı
birimdedir. Hybrid'de METRE (``self.D_ch``), solid/liquid'de MİLİMETRE. Bu
yüzden dış çap dönüşümü tipe özeldir; ortak bir ``/1000`` YAPILAMAZ.
"""

from typing import Any, Dict, List, Optional, Tuple

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
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float('inf'), float('-inf')):  # NaN / +-Inf
        return None
    return f


def _get(d: Any, *path: str) -> Any:
    """İç içe sözlükten güvenli okuma (``dict.get`` zinciri)."""
    cur = d
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _mm_to_m(value: Any) -> Optional[float]:
    """Milimetre değerini metreye çevir (None-güvenli)."""
    f = _num(value)
    return f / 1000.0 if f is not None else None


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
    transient = eng.get('transient') if isinstance(eng.get('transient'), dict) else {}
    curve = _curve(transient.get('time'), transient.get('thrust'))

    return {
        'thrust_curve': curve,
        'thrust': _num(eng.get('thrust')),
        'burn_time': _num(eng.get('burn_time')),
        'propellant_mass': _num(eng.get('propellant_mass_total')),
        'engine_inert_mass': inert,
        'engine_inert_mass_is_estimate': True,
        'engine_inert_mass_note': (
            'estimated as ~0.25 x propellant mass (hybrid dry mass has no '
            'component breakdown)'),
        # Hybrid chamber_diameter ZATEN METRE (self.D_ch) -> bölme YOK.
        'engine_od_m': _num(eng.get('chamber_diameter')),
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

    # Dış çap: kasa dış çapı (cad_design) tercih; yoksa hazne çapı (mm).
    od_mm = _get(results, 'cad_design', 'case_design', 'outer_diameter')
    if od_mm is None:
        od_mm = results.get('chamber_diameter')  # mm

    return {
        'thrust_curve': _curve(tc.get('time'), tc.get('thrust')),
        'thrust': _num(results.get('average_thrust')),
        'burn_time': _num(results.get('burn_time')),
        'propellant_mass': _num(results.get('propellant_mass')),
        'engine_inert_mass': _num(masses.get('dry_mass_kg')),
        'engine_inert_mass_is_estimate': False,
        'engine_inert_mass_note': None,
        'engine_od_m': _mm_to_m(od_mm),
        'engine_length_m': _mm_to_m(kd.get('total_length_mm')),
    }


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

    return {
        # Kararlı sonuç itki eğrisi taşımaz (transient sıvıda modellenmiyor).
        'thrust_curve': None,
        'thrust': _num(results.get('thrust')),
        'burn_time': _num(results.get('burn_time')),
        'propellant_mass': prop,
        'engine_inert_mass': inert,
        'engine_inert_mass_is_estimate': False,
        'engine_inert_mass_note': None,
        'engine_od_m': _mm_to_m(results.get('chamber_diameter')),  # mm -> m
        'engine_length_m': _mm_to_m(kd.get('overall_length_mm')),
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


def _f(fields: Dict, key: str, default: Any = None) -> Any:
    """Alanı oku; boş string/None -> default (form boş bırakmışsa)."""
    if key not in fields:
        return default
    v = fields[key]
    if v is None or (isinstance(v, str) and v.strip() == ''):
        return default
    return v


def _recompute_hybrid(fields: Dict) -> Dict:
    """Hibrit motoru fields'ten yeniden hesapla (/calculate ile aynı kurulum)."""
    from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
    engine = HybridRocketEngine(
        thrust=_f(fields, 'thrust'),
        burn_time=_f(fields, 'burn_time'),
        total_impulse=_f(fields, 'total_impulse'),
        of_ratio=_f(fields, 'of_ratio', 1.0),
        chamber_pressure=_f(fields, 'chamber_pressure', 20.0),
        # Birincil anahtar atmospheric_pressure; form DOM id'i single_pressure.
        atmospheric_pressure=_f(fields, 'atmospheric_pressure',
                                _f(fields, 'single_pressure', 1.0)),
        chamber_temperature=_f(fields, 'chamber_temperature'),
        gamma=_f(fields, 'gamma', 1.25),
        gas_constant=_f(fields, 'gas_constant'),
        l_star=_f(fields, 'l_star', 1.0),
        expansion_ratio=_f(fields, 'expansion_ratio', 0),
        nozzle_type=_f(fields, 'nozzle_type', 'conical'),
        thrust_coefficient=_f(fields, 'thrust_coefficient', 0),
        regression_a=_f(fields, 'regression_a'),
        regression_n=_f(fields, 'regression_n'),
        fuel_density=_f(fields, 'fuel_density'),
        combustion_type=_f(fields, 'combustion_type', 'infinite'),
        chamber_diameter_input=_f(fields, 'chamber_diameter_input', 0),
        fuel_type=_f(fields, 'fuel_type', 'htpb'),
        oxidizer_type=_f(fields, 'oxidizer_type', 'n2o'),
        injector_type=_f(fields, 'injector_type', 'showerhead'),
        initial_port_diameter=_f(fields, 'initial_port_diameter') or None,
        initial_gox=_f(fields, 'mass_flux_chamber') or None,
        tank_temperature=_f(fields, 'oxidizer_temp') or None,
        motor_name=_f(fields, 'motor_name', ''),
        motor_description=_f(fields, 'motor_description', ''),
    )
    return engine.calculate()


def _recompute_solid(fields: Dict) -> Dict:
    """Katı motoru fields'ten yeniden hesapla (/calculate_solid ile aynı)."""
    from hrma.engines.solid_rocket_engine import SolidRocketEngine
    motor = SolidRocketEngine(
        grain_type=_f(fields, 'grain_type', 'bates'),
        propellant_type=_f(fields, 'propellant_type', 'apcp'),
        chamber_diameter=_f(fields, 'chamber_diameter', 100),
        grain_length=_f(fields, 'grain_length', 500),
        core_diameter=_f(fields, 'core_diameter', 30),
        chamber_pressure=_f(fields, 'chamber_pressure', 40),
        burn_rate_a=_f(fields, 'burn_rate_a', 0.005),
        burn_rate_n=_f(fields, 'burn_rate_n', 0.35),
        overrides=dict(fields),
    )
    return motor.calculate_performance()


def _recompute_liquid(fields: Dict) -> Dict:
    """Sıvı motoru fields'ten yeniden hesapla (/calculate_liquid ile aynı)."""
    from hrma.engines.liquid_rocket_engine import LiquidRocketEngine
    engine = LiquidRocketEngine(
        thrust=_f(fields, 'thrust', 10000),
        chamber_pressure=_f(fields, 'chamber_pressure', 100),
        mixture_ratio=_f(fields, 'mixture_ratio', 2.5),
        fuel_type=_f(fields, 'fuel_type', 'rp1'),
        oxidizer_type=_f(fields, 'oxidizer_type', 'lox'),
        cooling_type=_f(fields, 'cooling_type', 'regenerative'),
        injector_type=_f(fields, 'injector_type', 'impinging'),
        overrides=dict(fields),
    )
    return engine.calculate_performance()
