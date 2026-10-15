"""
Common fixes and utilities for all motor types (Hybrid, Liquid, Solid)
Addresses all 17 common issues across the HRMA system

ÖH Z5S / P10-Z5S-B (28 Ağustos 2026) — bu modülün ÜRÜN AKIŞINDAKİ YERİ
=====================================================================
``hrma/app.py`` bu modülden BEŞ adı içe aktarır (``validation``,
``calculations``, ``graph_fixes``, ``fuel_mixer``, ``export_fixes``) ama
ÖLÇÜLDÜ: yalnız BİRİ çağrılıyor —
``validation.validate_pressure_consistency`` (``/calculate_liquid`` ΔP
kapısı). ``calculations``, ``fuel_mixer``, ``export_fixes`` ve
``graph_fixes`` için depoda (test dışı) TEK bir çağrı yeri yoktur.

Bu, aşağıdaki düzeltmeleri gereksiz kılmaz — tam tersi: ölü kol sessizce
uydurma sayı üretmeye devam ederse ilk bağlandığı gün ürün akışına o sayıyı
sokar. Dolayısıyla ölü kollar da FAIL-CLOSED hâle getirildi ve ölü oldukları
BURADA yazılıdır (sessiz bırakmak çözüm değildir).
"""

import numpy as np
import plotly.graph_objects as go
from typing import Dict, Tuple, Optional, List
import warnings

# Chug ΔP/Pc eşiği: TEK SAYISAL TANIM ``hrma.analysis.acoustic_modes``tadır.
# ÖH Z5S / P10-Z5S-B (P10B1-16): buradaki ``0.15`` o eşiğin DÖRDÜNCÜ kopyasıydı
# ve tek CANLI kopyaydı (``/calculate_liquid`` ΔP kapısını bu satır besliyor).
# Sayı DEĞİŞMEDİ (0,15) — değişen, sayının artık tek kaynaktan gelmesidir; eşik
# oradan güncellenirse ürün kapısı da onunla birlikte hareket eder.
from hrma.analysis.acoustic_modes import CHUG_DP_RATIO_MINIMUM
from hrma.constants import G_0

# İstemci/çağıran girdisi doğrulama: tek kapı. ``num`` bool'u, NaN/Inf'i ve
# sayı olmayanı reddeder — bu modüldeki kopyalar etmiyordu (P10B1-17).
from hrma.utils import input_guard as _ig

class CommonValidation:
    """Common validation utilities for all motor types"""

    @staticmethod
    def validate_pressure_consistency(tank_pressure: float, chamber_pressure: float) -> Tuple[bool, str]:
        """
        Issue #6: Validate tank pressure > chamber pressure
        """
        if tank_pressure <= chamber_pressure:
            return False, f"Tank pressure ({tank_pressure} bar) must be greater than chamber pressure ({chamber_pressure} bar)"

        # Eşik TEK KAYNAKTAN (P10B1-16). Değer bugünkü sabitle BİT-AYNI
        # (0,15) — mesaj metni de dâhil hiçbir sayı kaymaz.
        min_pressure_drop = CHUG_DP_RATIO_MINIMUM * chamber_pressure
        if (tank_pressure - chamber_pressure) < min_pressure_drop:
            return False, f"Insufficient pressure drop. Need at least {min_pressure_drop:.1f} bar drop for proper injection"

        return True, "Pressure validation passed"
    
    @staticmethod
    def validate_diameter_consistency(chamber_diameter: float, injector_diameter: float) -> Tuple[bool, str]:
        """
        Issue #5: Validate injector diameter < chamber diameter
        """
        if injector_diameter >= chamber_diameter:
            return False, f"Injector diameter ({injector_diameter} mm) must be less than chamber diameter ({chamber_diameter} mm)"
        
        if injector_diameter > 0.9 * chamber_diameter:
            return False, f"Injector diameter too large. Should be < 90% of chamber diameter for structural integrity"
        
        return True, "Diameter validation passed"
    
    @staticmethod
    def validate_total_impulse_consistency(total_impulse: float, thrust: float, burn_time: float) -> Tuple[bool, str]:
        """
        Issue #3: Validate total impulse = thrust * burn time
        """
        calculated_impulse = thrust * burn_time
        tolerance = 0.01  # 1% tolerance
        
        if abs(calculated_impulse - total_impulse) > tolerance * total_impulse:
            return False, f"Total impulse mismatch: Given {total_impulse} N·s, but Thrust×Time = {calculated_impulse} N·s"
        
        return True, "Total impulse validation passed"
    
    @staticmethod
    def validate_finite_area_combustion(contraction_ratio: Optional[float], mass_flux: Optional[float]) -> Tuple[bool, str]:
        """
        Issue #12: Validate only ONE of contraction ratio OR mass flux is provided
        """
        if contraction_ratio is not None and mass_flux is not None:
            return False, "For finite area combustion, provide EITHER contraction ratio OR mass flux, not both"
        
        if contraction_ratio is None and mass_flux is None:
            return False, "For finite area combustion, provide either contraction ratio or mass flux"
        
        return True, "Finite area combustion validation passed"

class CommonCalculations:
    """Common calculation fixes for all motor types"""
    
    @staticmethod
    def calculate_mass_flow_rate(thrust: float, isp: float, g0: float = G_0) -> float:
        """
        Issue #11: Correct mass flow rate calculation
        Formula: mdot = F / (g0 * Isp)
        """
        if isp <= 0:
            raise ValueError(f"Specific impulse must be positive (got {isp})")
        
        mdot = thrust / (g0 * isp)
        return mdot
    
    @staticmethod
    def calculate_reynolds_number(density: float, velocity: float, diameter: float, viscosity: float) -> float:
        """
        Issue #15: Correct Reynolds number calculation
        Re = ρ * v * D / μ
        """
        if viscosity <= 0:
            raise ValueError(f"Viscosity must be positive (got {viscosity})")
        
        Re = density * velocity * diameter / viscosity
        
        # Physical validation
        if Re < 1000:
            warnings.warn(f"Low Reynolds number ({Re:.0f}), laminar flow expected")
        elif Re > 200000:
            warnings.warn(f"Very high Reynolds number ({Re:.0f}), check design parameters")
        
        return Re
    
    #: ``calculate_total_impulse_auto`` alanlarının BİRİMLERİ — hata
    #: gövdesinde alan ADIYLA birlikte taşınır (adlı-hata sözleşmesi).
    _IMPULSE_UNITS = {'thrust': 'N', 'burn_time': 's', 'total_impulse': 'N*s'}

    @staticmethod
    def calculate_total_impulse_auto(thrust: Optional[float], burn_time: Optional[float],
                                    total_impulse: Optional[float]) -> Dict[str, float]:
        """
        Issue #2 & #3: Auto-calculate missing parameter from the other two

        ÖH Z5S / P10-Z5S-B (P10B1-17) — BOOL DELİĞİ + SESSİZ SAÇMA SAYI.
        ÖLÇÜLDÜ (28 Ağustos 2026, ``raw/OH/Z5S/p10b/olcum_once.json``), eski
        gövde şunları KABUL ediyordu:

          ``thrust=True, burn_time=10``      -> total_impulse **10,0 N*s**
                (``True`` Python'da 1'dir; bir itki değeri sanıldı)
          ``thrust=NaN,  burn_time=10``      -> total_impulse **NaN**
          ``thrust='1000'``                  -> ham ``TypeError``
                (adsız çökme; hangi alan olduğu yanıtta yok)
          ``thrust=1000, burn_time=0``       -> total_impulse **0,0**
          ``thrust=-1000, burn_time=10``     -> total_impulse **-10000,0**

        Kapı deponun kendi tek kapısıdır: ``hrma.utils.input_guard.num`` aynı
        ``True`` değerini DOĞRU reddediyordu ("'thrust' must be a number (got
        bool)"); bu kopya onu çağırmıyordu. Artık çağırıyor.

        POZİTİFLİK YENİ BİR EŞİK DEĞİLDİR: itki, yanma süresi ve toplam impuls
        bir motor için tanım gereği pozitiftir (deponun ``_positive_float``
        ilkesi). Sıfır süre / sıfır itki "hesaplandı" diye dönmez.

        Raises:
            hrma.utils.input_guard.InputError: alan sayı değil, sonlu değil ya
                da pozitif değil — hata metni ALANI ADLANDIRIR.
            ValueError: iki alandan azı verildi ya da üçü tutarsız.
        """
        ham = {'thrust': thrust, 'burn_time': burn_time,
               'total_impulse': total_impulse}
        temiz = {}
        for ad, deger in ham.items():
            if deger is None:
                temiz[ad] = None
                continue
            # bool / NaN / Inf / sayı-olmayan burada, ALAN ADIYLA düşer.
            sayi = _ig.num(ham, ad,
                           unit=CommonCalculations._IMPULSE_UNITS[ad],
                           required=True)
            if sayi <= 0:
                raise _ig.InputError(
                    f"'{ad}' must be greater than zero "
                    f"({CommonCalculations._IMPULSE_UNITS[ad]}); got {sayi:g}")
            temiz[ad] = sayi

        thrust = temiz['thrust']
        burn_time = temiz['burn_time']
        total_impulse = temiz['total_impulse']
        provided_count = sum(x is not None for x in [thrust, burn_time, total_impulse])

        if provided_count < 2:
            raise ValueError("At least 2 of 3 parameters (thrust, burn_time, total_impulse) must be provided")

        if provided_count == 3:
            # Validate consistency
            calculated = thrust * burn_time
            if abs(calculated - total_impulse) > 0.01 * total_impulse:
                raise ValueError(f"Inconsistent values: Thrust×Time = {calculated} ≠ {total_impulse}")

        # Calculate missing parameter — paydaların pozitifliği yukarıda
        # garanti edildi, sıfıra bölme kalmadı.
        if thrust is None:
            thrust = total_impulse / burn_time
        elif burn_time is None:
            burn_time = total_impulse / thrust
        elif total_impulse is None:
            total_impulse = thrust * burn_time

        return {
            'thrust': thrust,
            'burn_time': burn_time,
            'total_impulse': total_impulse
        }

class GraphFixes:
    """Common graph and visualization fixes"""
    
    @staticmethod
    def create_safe_plot(fig_data: Dict, container_id: str) -> str:
        """
        Issue #1: Fix graph corruption on multiple clicks
        """
        # Always purge existing plot first
        purge_script = f"if(document.getElementById('{container_id}')) {{ Plotly.purge('{container_id}'); }}"
        
        # Create new plot
        plot_script = f"Plotly.newPlot('{container_id}', {fig_data});"
        
        return purge_script + plot_script
    
    @staticmethod
    def toggle_plot_visibility(container_id: str) -> str:
        """
        Issue #1: Toggle plot visibility instead of recreating
        """
        return f"""
        const container = document.getElementById('{container_id}');
        if (container.style.display === 'none') {{
            container.style.display = 'block';
        }} else {{
            container.style.display = 'none';
        }}
        """

class FuelMixtureSystem:
    """
    Issue #7: Support for custom fuel mixtures and compositions
    """
    
    def __init__(self):
        # Regresyon katsayıları merkezi tablodan gelir (magic-number kuralı):
        # hrma/data/propellant_database.py HYBRID_REGRESSION_COEFFICIENTS
        from hrma.data.propellant_database import HYBRID_REGRESSION_COEFFICIENTS as _RC
        self.base_fuels = {
            'htpb': {'density': 920, 'a': _RC['htpb']['a'], 'n': _RC['htpb']['n']},
            'paraffin': {'density': 900, 'a': _RC['paraffin']['a'], 'n': _RC['paraffin']['n']},
            'carbon': {'density': 2200, 'a': _RC['carbon']['a'], 'n': _RC['carbon']['n']},
            'aluminum_oxide': {'density': 3950, 'a': _RC['al2o3']['a'], 'n': _RC['al2o3']['n']}
        }
    
    #: ``n`` üsleri bu bağıl toleransın içindeyse ``a`` katsayıları AYNI
    #: fiziksel boyuttadır ve kütle payıyla toplanabilir. Tolerans bir tasarım
    #: eşiği değil, kayan nokta gürültüsü payıdır (deponun gürültü tabanı
    #: 1e-12'nin çok üstünde tutuldu ki tablo yuvarlamaları geçebilsin).
    REGRESSION_EXPONENT_TOLERANCE = 1e-9

    def create_mixture(self, components: Dict[str, float]) -> Dict:
        """
        Create custom fuel mixture from components
        components: {'fuel_name': mass_fraction, ...}

        ÖH Z5S / P10-Z5S-B (P10B1-15) — BOYUTÇA TUTARSIZ KARIŞIM KURALI.
        Hibrit regresyon yasası ``r_dot = a * G_ox**n`` olduğu için ``a``nın
        fiziksel BOYUTU ``n``e bağlıdır: ``[a] = [uzunluk/zaman] /
        [kütle akısı]**n``. Farklı ``n``li iki ``a``yı toplamak, farklı
        boyuttaki iki niceliği toplamaktır.

        ÖLÇÜLDÜ (28 Ağustos 2026): tablodaki dört bileşenin ``n``leri
        0,555 / 0,620 / 0,450 / 0,350 — hepsi FARKLI. htpb+paraffin yarı yarıya
        karışımında ``a`` doğrudan toplamla 7,690e-05; aynı karışım ``G_ox``
        1000 kat büyük bir birimde ölçülüp geri çevrildiğinde 8,792e-05
        (**+%14,34**). Yani "karışımın regresyon katsayısı" seçilen BİRİM
        SİSTEMİNE göre değişiyordu — bu bir sayı değil, bir sanrıdır.

        Karar: FAIL-CLOSED. ``n``ler eşitse (tek boyut) ``a`` kütle payıyla
        toplanır ve künye bunu söyler; değilse sayı ÜRETİLMEZ.

        YOĞUNLUK DA DÜZELTİLDİ (beyanlı, aynı kusur sınıfı): kütle payları
        verildiğinde karışım yoğunluğu hacim toplamıyla kurulur
        (``V = Σ m_i/ρ_i`` → ``1/ρ = Σ w_i/ρ_i``); eski aritmetik ortalama
        yalnız HACİM payları için doğrudur. htpb+paraffin yarı yarıya için
        eski değer 910,0, doğrusu 909,80 kg/m³.

        Raises:
            ValueError: paylar 1,0'a toplanmıyor, bileşen tanınmıyor, pay
                pozitif değil ya da ``n`` üsleri ayrışıyor (boyut uyuşmazlığı).
        """
        total_fraction = sum(components.values())
        if abs(total_fraction - 1.0) > 0.001:
            raise ValueError(f"Mass fractions must sum to 1.0 (got {total_fraction})")

        for fuel, fraction in components.items():
            if fuel not in self.base_fuels:
                raise ValueError(f"Unknown fuel component: {fuel}")
            if not isinstance(fraction, (int, float)) or isinstance(fraction, bool):
                raise ValueError(
                    f"Mass fraction for '{fuel}' must be a number "
                    f"(got {type(fraction).__name__})")
            if not (fraction > 0):
                raise ValueError(
                    f"Mass fraction for '{fuel}' must be greater than zero "
                    f"(got {fraction})")

        # BOYUT KAPISI — ``a``lar ancak aynı ``n``de toplanabilir.
        usler = {fuel: float(self.base_fuels[fuel]['n']) for fuel in components}
        en_kucuk, en_buyuk = min(usler.values()), max(usler.values())
        if (en_buyuk - en_kucuk) > self.REGRESSION_EXPONENT_TOLERANCE:
            raise ValueError(
                "Regression coefficients cannot be mass-averaged across "
                "components with different exponents: [a] = [length/time] / "
                "[mass flux]**n depends on n, so the sum would be "
                "dimensionally inconsistent and would change with the unit "
                "system. Exponents: "
                + ', '.join(f"{ad}={us:g}" for ad, us in sorted(usler.items()))
                + ". Provide a measured regression law for the blend instead.")

        # Aynı boyut: ``a`` kütle payıyla toplanabilir; ``n`` ortak değerdir.
        mixture = {'density': 0.0, 'a': 0.0, 'n': en_kucuk}
        ters_yogunluk = 0.0
        for fuel, fraction in components.items():
            props = self.base_fuels[fuel]
            ters_yogunluk += float(fraction) / float(props['density'])
            mixture['a'] += float(props['a']) * float(fraction)
        mixture['density'] = 1.0 / ters_yogunluk

        # KÜNYE: hangi kural uygulandı, hangi kural uygulanmadı.
        mixture['density_rule'] = (
            'volume-additive from mass fractions: 1/rho = sum(w_i / rho_i)')
        mixture['regression_rule'] = (
            'mass-weighted a at a common exponent n=%g; valid only because '
            'all components share this exponent' % en_kucuk)
        mixture['components'] = {ad: float(pay)
                                 for ad, pay in components.items()}
        return mixture

class ExportFixes:
    """
    Issue #17: Fix export functionality for STL, motor files, etc.

    ÖH Z5S / P10-Z5S-B (P10B1-18) — BOŞ GİRDİDEN UYDURMA DOSYA.
    ÖLÇÜLDÜ (28 Ağustos 2026): ``generate_motor_file({})`` çağrısı hiçbir
    künye taşımayan TAM bir OpenRocket ``.eng`` dosyası basıyordu —

        ``100.0 300.0 0 5.000 10.000 HRMA``
        ``0.000 0.0 / 0.100 1000.0 / 10.000 1000.0 / 10.100 0.0``

    yani 100 mm çap, 300 mm boy, 5 kg yakıt, 10 kg toplam kütle ve 10 saniye
    boyunca 1000 N'luk düz bir itki eğrisi. Bu dosya bir uçuş simülatörüne
    (OpenRocket) yüklenebilir bir belgedir; içindeki tek bir sayı bile
    hesaplanmamıştır. ``generate_basic_stl({})`` aynı şekilde 100 mm/300 mm
    varsayılanlarından bir katı gövde üretiyordu.

    Karar: FAIL-CLOSED. Zorunlu alan yoksa dosya ÜRETİLMEZ; hata alanları
    ADIYLA sayar. "ASSUMED künyesi" seçeneği reddedildi — üretilen dosya
    HRMA'dan çıktıktan sonra künyesinden ayrılır (başka bir programa girdi
    olur), dolayısıyla künye onu güvenli yapmaz.
    """

    #: Bu ESKİ yardımcının ``.eng`` satırında yazdığı HER alan; hiçbiri
    #: varsayılamaz. ADI KASITLI OLARAK FARKLI: deponun KANONİK ``.eng``
    #: yazıcısı ``hrma/export/openrocket_integration.py``dir ve orada
    #: ``ENG_REQUIRED_FIELDS`` ADIYLA BAŞKA bir şema yaşar
    #: (``case_diameter``/``chamber_length``/``total_impulse``). İki liste
    #: aynı ada sahip olsaydı "aynı sabitin iki değeri" olurdu; oysa bunlar
    #: İKİ AYRI ŞEMADIR. Yeni kod kanonik yazıcıyı kullanmalıdır — bu
    #: yardımcı yalnız fail-closed hâle getirildi, canlandırılmadı.
    _ENG_LEGACY_REQUIRED_FIELDS = ('motor_name', 'diameter', 'length',
                                   'propellant_mass', 'total_mass',
                                   'thrust_curve')

    #: STL gövdesi için zorunlu geometri alanları.
    STL_REQUIRED_FIELDS = ('chamber_length', 'chamber_diameter')

    @staticmethod
    def _eksik_alanlar(motor_data: Dict, alanlar) -> list:
        """Verilmemiş (yok / None / boş dize) zorunlu alanların ADLARI."""
        if not isinstance(motor_data, dict):
            raise ValueError(
                f"motor_data must be a mapping (got "
                f"{type(motor_data).__name__})")
        eksik = []
        for ad in alanlar:
            deger = motor_data.get(ad)
            if deger is None or (isinstance(deger, str) and not deger.strip()):
                eksik.append(ad)
        return eksik

    @staticmethod
    def generate_basic_stl(motor_data: Dict) -> str:
        """Generate basic STL file content.

        Raises:
            ValueError: zorunlu geometri alanı eksik ya da pozitif değil —
                hata ALANLARI ADLANDIRIR (P10B1-18, fail-closed).
        """
        eksik = ExportFixes._eksik_alanlar(motor_data,
                                           ExportFixes.STL_REQUIRED_FIELDS)
        if eksik:
            raise ValueError(
                "Cannot generate STL: required geometry is missing "
                f"({', '.join(eksik)}). No default dimensions are assumed.")

        L = _ig.num(motor_data, 'chamber_length', unit='mm', required=True)
        D = _ig.num(motor_data, 'chamber_diameter', unit='mm', required=True)
        for ad, deger in (('chamber_length', L), ('chamber_diameter', D)):
            if deger <= 0:
                raise ValueError(
                    f"'{ad}' must be greater than zero (mm); got {deger:g}")

        stl_content = f"""solid motor_assembly
facet normal 0 0 1
  outer loop
    vertex 0 0 0
    vertex {D} 0 0
    vertex {D/2} {D*0.866} 0
  endloop
endfacet
facet normal 0 0 -1
  outer loop
    vertex 0 0 {L}
    vertex {D/2} {D*0.866} {L}
    vertex {D} 0 {L}
  endloop
endfacet
endsolid motor_assembly"""
        
        return stl_content
    
    @staticmethod
    def generate_motor_file(motor_data: Dict) -> str:
        """Generate OpenRocket .eng file content.

        Deponun KANONİK ``.eng`` yazıcısı
        ``hrma.export.openrocket_integration``dır; yeni kod onu kullanmalıdır.
        Bu eski yardımcı yalnız fail-closed hâle getirildi: eksik alanda
        dosya ÜRETİLMEZ, uydurma bir motor yazılmaz.

        Raises:
            ValueError: zorunlu alan eksik, sayısal alan geçersiz ya da itki
                eğrisi kullanılabilir değil — hata ALANLARI ADLANDIRIR.
        """
        eksik = ExportFixes._eksik_alanlar(
            motor_data, ExportFixes._ENG_LEGACY_REQUIRED_FIELDS)
        if eksik:
            raise ValueError(
                "Cannot generate .eng file: the motor data does not provide "
                f"these required fields: {', '.join(eksik)}. No placeholder "
                "motor is written - a default-mass, default-thrust motor "
                "would load in OpenRocket and look real.")

        diameter = _ig.num(motor_data, 'diameter', unit='mm', required=True)
        length = _ig.num(motor_data, 'length', unit='mm', required=True)
        propellant_mass = _ig.num(motor_data, 'propellant_mass', unit='kg',
                                  required=True)
        total_mass = _ig.num(motor_data, 'total_mass', unit='kg',
                             required=True)
        for ad, deger in (('diameter', diameter), ('length', length),
                          ('propellant_mass', propellant_mass),
                          ('total_mass', total_mass)):
            if deger <= 0:
                raise ValueError(
                    f"'{ad}' must be greater than zero; got {deger:g}")
        if total_mass < propellant_mass:
            raise ValueError(
                f"'total_mass' ({total_mass:g} kg) is smaller than "
                f"'propellant_mass' ({propellant_mass:g} kg); the loaded "
                f"motor cannot weigh less than its propellant.")

        thrust_curve = motor_data.get('thrust_curve')
        try:
            noktalar = [(float(t), float(f)) for t, f in thrust_curve]
        except (TypeError, ValueError) as e:
            raise ValueError(
                f"'thrust_curve' must be a sequence of (time_s, thrust_N) "
                f"pairs of numbers: {e}")
        if len(noktalar) < 2:
            raise ValueError(
                f"'thrust_curve' needs at least two points; got "
                f"{len(noktalar)}.")

        motor_name = str(motor_data.get('motor_name')).strip()
        eng_content = f"; Motor file generated by HRMA\n"
        eng_content += f"; {motor_name}\n"
        eng_content += f"{diameter:.1f} {length:.1f} "
        eng_content += f"0 {propellant_mass:.3f} "
        eng_content += f"{total_mass:.3f} HRMA\n"

        for time, thrust in noktalar:
            eng_content += f"{time:.3f} {thrust:.1f}\n"

        eng_content += ";\n"

        return eng_content

# Global instances
validation = CommonValidation()
calculations = CommonCalculations()
graph_fixes = GraphFixes()
fuel_mixer = FuelMixtureSystem()
export_fixes = ExportFixes()