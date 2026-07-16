"""
Structural Analysis Module
Wall thickness calculation and safety factor analysis for hybrid rocket motors
"""

import numpy as np
import json
from typing import Dict, List, Tuple, Optional

from hrma.data.materials_db import build_materials_view

class StructuralAnalyzer:
    """Structural analysis for hybrid rocket motor chambers.

    DENETIM DUZELTMESI (2026-06): Onceki surum termal gerilmeyi, sicaklikla
    mukavemet derating'ini ve burkulmayi (buckling) TAMAMEN ihmal ediyordu.
    Bu, emniyet faktorunu (SF) gercegin cok ustunde gosteriyordu (3000 K cidar
    sicakliginda gercek SF < 1'e dusebilir). Asagidaki eklemeler bu tehlikeyi
    konservatif yonde duzeltir:
      1) Termal hoop gerilme (radyal sicaklik gradyani)  -> Timoshenko & Goodier,
         Boley & Weiner, Roark's Formulas for Stress & Strain 9th ed. Ch. 16.
      2) Sicakliga bagli yield/ultimate derating          -> MMPDS / MIL-HDBK-5
         Fig. 2.3.1.1.1 (AISI dusuk-alasimli celikler, kisa sureli maruziyet).
      3) Eksenel + dis-basinc burkulmasi                  -> NASA SP-8007.
      4) Ince-cidar varsayimi gecerlilik kontrolu (t/r<0.1) -> Shigley / Roark.
    """

    def __init__(self):
        # Malzeme veritabanı — MERKEZİ kaynaktan (Dalga 0, 2026-07-14).
        #
        # Eski yerel tablo hrma/data/materials_db.py'ye taşındı: mekanik +
        # termal özellikler artık TEK kayıtta (parametre tutarlılığı kuralı;
        # heat_transfer/safety modülleriyle aynı değerler). Alanlar ve
        # derating eğrileri kaynaklarıyla birlikte orada belgelidir.
        # Anahtar uyumluluğu: steel_4130 / aluminum_6061 / inconel_718 /
        # titanium_6al4v aynen korunur; ek malzemeler (ss_304, ss_316,
        # copper, cucrzr, graphite, ablative, steel) de seçilebilir.
        self.materials = build_materials_view()

    # ------------------------------------------------------------------
    # YENI YARDIMCI FONKSIYONLAR (DENETIM DUZELTMESI 2026-06)
    # ------------------------------------------------------------------
    def _derate_strength(self, mat_props: Dict, wall_temp_K: float) -> Dict:
        """Sicakliga bagli mukavemet derating'i.

        Yield ve ultimate dayanim, cidar sicakligi ile DUSER. Onceki surum bunu
        ihmal ediyordu -> 3000 K alev sicakliginda celik yine oda-sicakligi
        dayanimiyla hesaplaniyordu (tehlikeli, gercek-disi).

        Kaynak: MMPDS / MIL-HDBK-5 Fig. 2.3.1.1.1 (AISI dusuk-alasimli celikler,
        kisa-sureli maruziyet); malzeme bazli derating_curve sozlugunden
        lineer interpolasyon yapilir. Egri disina dusen sicakliklarda en yakin
        ucta sabitlenir (konservatif: en yuksek sicaklik noktasinin faktoru).

        Args:
            mat_props: Malzeme ozellik sozlugu (derating_curve icermeli).
            wall_temp_K: Yapisal cidar sicakligi [K].

        Returns:
            Derating sonuclari: derate edilmis yield/ultimate ve retention faktoru.
        """
        wall_temp_C = wall_temp_K - 273.15

        curve = mat_props.get('derating_curve')
        if not curve:
            # Egri yoksa konservatif sabit (orta-seviye kayip) uygula.
            retention = 0.5
        else:
            temps = sorted(curve.keys())
            facs = [curve[t] for t in temps]
            if wall_temp_C <= temps[0]:
                retention = facs[0]
            elif wall_temp_C >= temps[-1]:
                # Egri ustunde: son (en dusuk) faktorde sabitle. Konservatif.
                retention = facs[-1]
            else:
                retention = float(np.interp(wall_temp_C, temps, facs))

        derated_yield = mat_props['yield_strength'] * retention
        derated_ultimate = mat_props['ultimate_strength'] * retention

        return {
            'wall_temperature_C': wall_temp_C,
            'wall_temperature_K': wall_temp_K,
            'strength_retention_factor': retention,
            'derated_yield_strength': derated_yield,            # Pa
            'derated_ultimate_strength': derated_ultimate,      # Pa
            'derated_yield_strength_MPa': derated_yield / 1e6,
            'derated_ultimate_strength_MPa': derated_ultimate / 1e6,
            'room_temp_yield_MPa': mat_props['yield_strength'] / 1e6,
            'exceeds_max_service_temp': bool(
                wall_temp_K > mat_props.get('max_service_temp', float('inf'))
            )
        }

    def _thermal_hoop_stress(self, mat_props: Dict, delta_T: float) -> Dict:
        """Radyal sicaklik gradyaninin yarattigi termal hoop gerilme.

        Ince cidarli silindirde cidar boyunca lineer sicaklik gradyani (ic yuz
        sicak, dis yuz soguk; delta_T = T_ic - T_dis) icin yuzey termal
        gerilmesinin buyuklugu:

            sigma_thermal = E * alpha * delta_T / (1 - nu)      [KONSERVATIF UST SINIR]

        Not / kaynak: Timoshenko & Goodier "Theory of Elasticity" (uzun silindir,
        eksenel kisitli hal) ve Boley & Weiner "Theory of Thermal Stresses"
        Ch.10-11 termal gerilme cozumu; Roark's Formulas for Stress & Strain
        9th ed. Ch.16. Tam ic-dis fark delta_T icin yuzey degeri klasik olarak
        E*alpha*delta_T/(2(1-nu)) seklindedir; ancak biz KONSERVATIF olmak icin
        2 faktorunu DUSURMUYORUZ (gorev tanimindaki E*alpha*dT/(1-nu) formu,
        yuzey-orta-duzlem farki yorumuna ve gerilme yiginlasmasi/kisitlanmaya
        karsi guvenli ust sinir). Bu termal etki cogu durumda BASINC hoop
        gerilmesinden buyuktur ve onceki surumde tamamen yoktu.

        delta_T <= 0 (sogutmasiz/izotermal cidar) ise termal gerilme 0 alinir.
        """
        E = mat_props['elastic_modulus']
        alpha = mat_props['thermal_expansion']
        nu = mat_props['poisson_ratio']

        dT = max(0.0, delta_T)
        # KONSERVATIF: 1/(1-nu) (gorev tanimi). Klasik yuzey degeri 1/(2(1-nu)).
        sigma_thermal = E * alpha * dT / (1.0 - nu)

        return {
            'delta_T': dT,                          # K  (kullanilan cidar gradyani)
            'thermal_hoop_stress': sigma_thermal,   # Pa (tensile, dis yuzde)
            'thermal_hoop_stress_MPa': sigma_thermal / 1e6,
            'formula': 'sigma_th = E*alpha*dT/(1-nu)  [Timoshenko/Boley-Weiner/Roark Ch.16, konservatif]'
        }

    def _estimate_wall_delta_T(self, motor_data: Dict, mat_props: Dict) -> Tuple[float, float]:
        """Cidar ic/dis sicaklik degerlerini tahmin et.

        Tercih sirasi:
          1) motor_data['wall_temperature_hot'] / 'wall_temperature_cold' (1s-iletim modulunden)
          2) chamber_temperature'tan konservatif tahmin (sogutmasiz celik cidar):
             ic yuz alev-tarafi recovery sicakligina yakin oturur. Sogutmasiz
             celik cidar icin literatur ~malzemenin servis sinirina kadar isinir;
             gradyan = T_ic_cidar - T_dis (ortam ~300 K).

        Returns:
            (T_inner_wall_K, T_outer_wall_K)
        """
        # 1) Dogrudan cidar sicakligi verilmisse kullan
        T_hot = motor_data.get('wall_temperature_hot')
        T_cold = motor_data.get('wall_temperature_cold')
        if T_hot is not None and T_cold is not None:
            return float(T_hot), float(T_cold)

        # 2) chamber_temperature'tan konservatif tahmin
        T_chamber = motor_data.get('chamber_temperature')
        T_ambient = motor_data.get('ambient_temperature', 300.0)
        if T_chamber is None:
            # Sicaklik bilgisi yok -> termal etki devre disi (eski davranis korunur).
            return T_ambient, T_ambient

        # Sogutmasiz cidar varsayimi (konservatif): gaz-tarafi cidar yuzeyi,
        # malzeme azami servis sicakligina kadar isinir; ancak alev sicakligini
        # asamaz. Boylece sicak-yuz sicakligini malzeme sinirinda kapariz
        # (kalici rejim, sogutmasiz). Bu, hem derating hem gradyan icin
        # makul-konservatif bir cidar sicakligi verir.
        T_inner = min(float(T_chamber), mat_props.get('max_service_temp', float(T_chamber)))
        T_outer = float(T_ambient)
        return T_inner, T_outer

    def _check_buckling(self, pressure: float, radius: float, thickness: float,
                        length: float, mat_props: Dict) -> Dict:
        """Ince-cidarli silindir burkulma kontrolu (NASA SP-8007).

        Iki mod kontrol edilir:
          A) Eksenel basma burkulmasi (motor sonu kuvveti, gerdirme/montaj yuku):
             sigma_cl = E / sqrt(3(1-nu^2)) * (t/r)      [klasik]
             sigma_cr = gamma * sigma_cl                  [tasarim]
             gamma = 1 - 0.901*(1 - exp(-phi)),  phi = (1/16)*sqrt(r/t)
          B) Dis basinc burkulmasi (uzun silindir, klasik elastik):
             p_cl = E/(4(1-nu^2)) * (t/r)^3

        Kaynak: NASA SP-8007 "Buckling of Thin-Walled Circular Cylinders"
        (revised 1968), NTRS 19680026348. Knockdown gamma ve klasik
        eksenel/dis-basinc formulleri SP-8007 ve Timoshenko shell teorisinden.

        Not: Eksenel burkulma yuku, kapali uctaki basinc kuvvetinden gelen
        eksenel cidar gerilmesi (longitudinal = p*r/(2t)) ile karsilastirilir;
        bu motor montaj/itki yuklerini de yaklasik kapsayan konservatif bir
        eksenel gerilme tabanidir.
        """
        E = mat_props['elastic_modulus']
        nu = mat_props['poisson_ratio']

        # A) Eksenel basma burkulmasi
        if thickness > 0 and radius > 0:
            sigma_cl = E / np.sqrt(3.0 * (1.0 - nu**2)) * (thickness / radius)
            phi = (1.0 / 16.0) * np.sqrt(radius / thickness)
            gamma_kd = 1.0 - 0.901 * (1.0 - np.exp(-phi))
            sigma_cr_axial = gamma_kd * sigma_cl
        else:
            sigma_cl = float('inf')
            gamma_kd = 1.0
            sigma_cr_axial = float('inf')

        # Uygulanan eksenel cidar gerilmesi (longitudinal, kapali-uc basinci)
        applied_axial_stress = pressure * radius / (2.0 * thickness) if thickness > 0 else float('inf')
        axial_buckling_sf = (sigma_cr_axial / applied_axial_stress
                             if applied_axial_stress > 0 else float('inf'))

        # B) Dis basinc burkulmasi (uzun silindir klasik)
        # Konservatif olarak uygulanan dis basinci = tasarim basincinin
        # buyuklugu kadar alinabilir; burada referans olarak 1 atm dis ortam
        # (kapali kazan ic basinci ic'e dogru cidari destekler, ancak vakum/
        # dis basinc senaryosu icin kritik dis basinc raporlanir).
        p_cr_external = E / (4.0 * (1.0 - nu**2)) * (thickness / radius)**3 if radius > 0 else float('inf')

        # Burkulma durum degerlendirmesi (eksenel kritik)
        if axial_buckling_sf < 1.0:
            buckling_status = 'CRITICAL'
        elif axial_buckling_sf < 2.0:
            buckling_status = 'MARGINAL'
        else:
            buckling_status = 'SAFE'

        return {
            'classical_axial_buckling_stress_MPa': (sigma_cl / 1e6
                                                    if np.isfinite(sigma_cl) else float('inf')),
            'knockdown_factor_gamma': gamma_kd,
            'critical_axial_buckling_stress_MPa': (sigma_cr_axial / 1e6
                                                   if np.isfinite(sigma_cr_axial) else float('inf')),
            'applied_axial_stress_MPa': (applied_axial_stress / 1e6
                                         if np.isfinite(applied_axial_stress) else float('inf')),
            'axial_buckling_safety_factor': axial_buckling_sf,
            'critical_external_pressure_bar': (p_cr_external / 1e5
                                               if np.isfinite(p_cr_external) else float('inf')),
            'buckling_status': buckling_status,
            'source': 'NASA SP-8007 (1968), NTRS 19680026348'
        }
    
    def analyze_structure(self, motor_data: Dict, material: str = 'steel_4130',
                         design_pressure_factor: float = 1.5) -> Dict:
        """
        Complete structural analysis
        
        Args:
            motor_data: Motor performance and geometry data
            material: Material type
            design_pressure_factor: Safety factor for design pressure
            
        Returns:
            Structural analysis results
        """
        
        # Extract motor parameters
        chamber_pressure = motor_data.get('chamber_pressure', 20.0) * 1e5  # Pa
        chamber_diameter = motor_data.get('chamber_diameter', 0.1)  # m
        chamber_length = motor_data.get('chamber_length', 0.5)  # m
        throat_diameter = motor_data.get('throat_diameter', 0.02)  # m
        nozzle_type = motor_data.get('nozzle_type', 'conical')
        burn_time = motor_data.get('burn_time', 10)  # s

        # Design pressure
        design_pressure = chamber_pressure * design_pressure_factor

        # Get material properties
        mat_props = self.materials.get(material, self.materials['steel_4130'])

        # DENETIM DUZELTMESI: Cidar sicakligini tahmin et (termal gerilme +
        # derating icin). motor_data 'wall_temperature_hot/cold' veya
        # 'chamber_temperature' tasiyabilir; yoksa termal etki devre disi kalir.
        T_inner_wall, T_outer_wall = self._estimate_wall_delta_T(motor_data, mat_props)

        # OPUS DENETIM DUZELTMESI (major): Eski kod AYNI ANDA hem "cidar
        # servis sicakligina isinmis" (agir derating) hem de "tam soguk
        # gradyan" (tam termal gerilme) varsayiyordu — fiziksel olarak
        # celiskili iki uc durumun yigilmasi her sicak motoru SF~0.10'a
        # cokertiyordu. Iki TUTARLI senaryo ayri degerlendirilir, kritik
        # (dusuk SF'li) olan tasarimi yonetir:
        #   A) Sicak-soak (sogutmasiz kararli hal): cidar ~izotermal sicak
        #      -> derating T_ic'te, gradyan kucuk artik deger (0.15x)
        #   B) Sogutmali gradyan: ic yuz sicak, ortalama cidar daha soguk
        #      -> derating ORTALAMA cidar sicakliginda, gradyan tam
        scenarios = {}
        dT_full = T_inner_wall - T_outer_wall
        for name, (T_derate, dT) in {
            'hot_soak': (T_inner_wall, 0.15 * dT_full),
            'cooled_gradient': (0.5 * (T_inner_wall + T_outer_wall), dT_full),
        }.items():
            der = self._derate_strength(mat_props, T_derate)
            ana = self._analyze_chamber_wall(
                design_pressure, chamber_diameter, chamber_length, mat_props,
                derating=der, wall_delta_T=dT
            )
            scenarios[name] = {'analysis': ana, 'derating': der,
                               'derating_temp_K': T_derate, 'delta_T_K': dT}

        # Yoneten senaryo: dusuk von Mises SF'li olan
        governing = min(
            scenarios,
            key=lambda k: scenarios[k]['analysis'].get(
                'von_mises_safety_factor', float('inf')))
        chamber_analysis = scenarios[governing]['analysis']
        chamber_analysis['governing_thermal_scenario'] = governing
        chamber_analysis['thermal_scenarios'] = {
            k: {'von_mises_safety_factor':
                v['analysis'].get('von_mises_safety_factor'),
                'derating_temp_K': v['derating_temp_K'],
                'delta_T_K': v['delta_T_K']}
            for k, v in scenarios.items()}
        derating = scenarios[governing]['derating']
        wall_temp_structural = scenarios[governing]['derating_temp_K']
        wall_delta_T = scenarios[governing]['delta_T_K']

        # Burkulma kontrolu (NASA SP-8007) - hazne cidari geometrisiyle
        chamber_t = chamber_analysis['recommended_thickness'] / 1000.0  # m
        buckling_analysis = self._check_buckling(
            design_pressure, chamber_diameter / 2.0, chamber_t,
            chamber_length, mat_props
        )
        
        # Nozzle analysis
        nozzle_analysis = self._analyze_nozzle_structure(
            design_pressure, throat_diameter, chamber_diameter, mat_props, nozzle_type
        )
        
        # End cap analysis
        end_cap_analysis = self._analyze_end_caps(
            design_pressure, chamber_diameter, mat_props
        )
        
        # Bolt/fastener analysis
        fastener_analysis = self._analyze_fasteners(
            design_pressure, chamber_diameter, mat_props
        )
        
        # Fatigue analysis
        fatigue_analysis = self._analyze_fatigue(
            chamber_analysis['hoop_stress'], burn_time, mat_props
        )
        
        # Weight analysis
        weight_analysis = self._calculate_weight(
            chamber_analysis, nozzle_analysis, end_cap_analysis, mat_props
        )
        
        # Safety analysis (burkulma da dahil edilir)
        safety_analysis = self._analyze_safety_factors(
            chamber_analysis, nozzle_analysis, end_cap_analysis, mat_props,
            buckling_analysis=buckling_analysis
        )

        return {
            'chamber_analysis': chamber_analysis,
            'nozzle_analysis': nozzle_analysis,
            'end_cap_analysis': end_cap_analysis,
            'fastener_analysis': fastener_analysis,
            'fatigue_analysis': fatigue_analysis,
            'weight_analysis': weight_analysis,
            'safety_analysis': safety_analysis,
            # İki SF raporu (Dalga 0, 2026-07-14): üst seviyede de raporlanır
            # ki UI/rapor katmanı chamber_analysis'e inmek zorunda kalmasın.
            # safety_factor = safety_factor_total (geriye dönük tek-SF alanı).
            'safety_factor_pressure': chamber_analysis.get('safety_factor_pressure'),
            'safety_factor_total': chamber_analysis.get('safety_factor_total'),
            'safety_factor': chamber_analysis.get('safety_factor_total'),
            # YENI (DENETIM DUZELTMESI 2026-06)
            'thermal_analysis': {
                'wall_temperature_inner_K': T_inner_wall,
                'wall_temperature_outer_K': T_outer_wall,
                'wall_delta_T_K': wall_delta_T,
                'strength_derating': derating,
                'thermal_hoop_stress_MPa': chamber_analysis.get('thermal_hoop_stress', 0.0),
            },
            'buckling_analysis': buckling_analysis,
            'material_properties': mat_props,
            'design_parameters': {
                'material': material,
                'design_pressure': design_pressure / 1e5,  # bar
                'design_pressure_factor': design_pressure_factor,
                'wall_temperature_K': wall_temp_structural
            }
        }
    
    def _analyze_chamber_wall(self, pressure: float, diameter: float,
                            length: float, mat_props: Dict,
                            derating: Optional[Dict] = None,
                            wall_delta_T: float = 0.0) -> Dict:
        """Analyze chamber wall thickness and stresses.

        DENETIM DUZELTMESI (2026-06): Artik TERMAL gerilme ve sicaklik
        DERATING'i dahil edilir. Onceki surum:
          - termal hoop gerilmeyi tamamen ihmal ediyordu,
          - oda-sicakligi yield'ini kullaniyordu (3000 K cidarda gercek-disi).
        Bu, SF'yi gercegin cok ustunde gosteriyordu. Toplam gerilme:
            sigma_total_hoop = sigma_pressure_hoop + sigma_thermal
        ve SF'ler DERATE EDILMIS yield'e gore hesaplanir.

        Args:
            derating: _derate_strength sonucu (None ise oda-sicakligi yield).
            wall_delta_T: Cidar boyunca termal gradyan [K] (>0 sicak ic yuz).
        """

        radius = diameter / 2
        yield_strength = mat_props['yield_strength']
        safety_factor = mat_props['safety_factor']

        # Derate edilmis yield (varsa). Termal degerlendirme bu deger uzerinden.
        if derating is not None:
            yield_for_design = derating['derated_yield_strength']
        else:
            yield_for_design = yield_strength

        # Required wall thickness (thin wall approximation)
        # t = P*r / (sigma_allow). DERATE edilmis yield kullanilir -> daha kalin
        # cidar gerekebilir (konservatif).
        allowable_stress = yield_for_design / safety_factor
        min_thickness = pressure * radius / allowable_stress

        # Recommended thickness (add 20% margin)
        recommended_thickness = min_thickness * 1.2

        # Ince-cidar varsayimi gecerlilik kontrolu (t/r < 0.1, yani D/t > 20)
        # -> Shigley "Mechanical Engineering Design", Roark's Formulas Ch.13.
        t_over_r = recommended_thickness / radius if radius > 0 else float('inf')
        thin_wall_valid = bool(t_over_r < 0.1)

        # Basinc kaynakli HOOP gerilme.
        #
        # DENETIM DUZELTMESI (2026-06): Ince-cidar formulu sigma=p*r/t (ic yaricap)
        # t/r >= 0.1 oldugunda GERCEK tepe gerilmeyi OLDUGUNDAN AZ gosterir
        # (Lame cozumune gore ~%5 (t/r=0.1) ... ~%11 (t/r=0.2) dusuk). Tehlikeyi az
        # gostermek YASAK -> t/r >= 0.1 ise basinc hoop'unu LAME kalin-cidar tepe
        # degeriyle (ic yuzey) hesaplariz; bu daima ince-cidar degerinden buyuktur
        # (konservatif). Kaynak: Lame (1833); Timoshenko & Goodier "Theory of
        # Elasticity" Art.28; Roark's Formulas for Stress & Strain 9th ed. Tablo 13.5
        # (kalin silindir, ic basinc): sigma_hoop(ic) = p*(b^2+a^2)/(b^2-a^2).
        thin_pressure_hoop = pressure * radius / recommended_thickness
        a_inner = radius                              # ic yaricap (silindir ici)
        b_outer = radius + recommended_thickness      # dis yaricap
        if b_outer > a_inner:
            lame_peak_hoop = pressure * (b_outer**2 + a_inner**2) / (b_outer**2 - a_inner**2)
        else:
            lame_peak_hoop = thin_pressure_hoop
        if not thin_wall_valid:
            # Kalin-cidar rejimi: konservatif olarak Lame tepe degerini kullan.
            pressure_hoop_stress = max(thin_pressure_hoop, lame_peak_hoop)
        else:
            pressure_hoop_stress = thin_pressure_hoop

        longitudinal_stress = pressure * radius / (2 * recommended_thickness)

        # TERMAL hoop gerilme (radyal gradyan). delta_T<=0 ise 0.
        thermal = self._thermal_hoop_stress(mat_props, wall_delta_T)
        thermal_hoop_stress = thermal['thermal_hoop_stress']

        # TOPLAM hoop gerilme = basinc + termal (dis yuzde ikisi de tensile,
        # konservatif olarak toplanir).
        hoop_stress = pressure_hoop_stress + thermal_hoop_stress

        # Von Mises esdeger gerilme (toplam hoop ile).
        # OPUS DENETIM DUZELTMESI (minor): kalin cidarda ic yuzeyde radyal
        # gerilme sigma_r = -p ihmal edilirse von Mises %5-17 DUSUK cikar
        # (non-konservatif yon). Kalin-cidar rejiminde 3 eksenli form kullanilir.
        if not thin_wall_valid:
            sigma_r = -pressure
            von_mises_stress = np.sqrt(0.5 * (
                (hoop_stress - longitudinal_stress) ** 2
                + (longitudinal_stress - sigma_r) ** 2
                + (sigma_r - hoop_stress) ** 2
            ))
        else:
            von_mises_stress = np.sqrt(
                hoop_stress**2 - hoop_stress * longitudinal_stress + longitudinal_stress**2
            )

        # Safety factors -> DERATE EDILMIS yield'e gore
        hoop_safety_factor = yield_for_design / hoop_stress if hoop_stress > 0 else float('inf')
        von_mises_safety_factor = yield_for_design / von_mises_stress if von_mises_stress > 0 else float('inf')

        # İKİ SF RAPORU (Dalga 0, 2026-07-14): basınç-yalnız (birincil yük)
        # ve basınç+termal (toplam). Termal gerilme İKİNCİL (deplasman
        # kontrollü) yüktür; ayrı raporlanması tasarımcıya hangi etkinin
        # domine ettiğini gösterir. safety_factor_total, mevcut
        # hoop_safety_factor ile aynıdır (geriye dönük uyum).
        safety_factor_pressure = (yield_for_design / pressure_hoop_stress
                                  if pressure_hoop_stress > 0 else float('inf'))
        safety_factor_total = hoop_safety_factor

        return {
            'minimum_thickness': min_thickness * 1000,  # mm
            'recommended_thickness': recommended_thickness * 1000,  # mm
            'hoop_stress': hoop_stress / 1e6,  # MPa (TOPLAM: basinc+termal)
            'pressure_hoop_stress': pressure_hoop_stress / 1e6,  # MPa (sadece basinc; Lame ise tepe)
            'thin_wall_pressure_hoop_MPa': thin_pressure_hoop / 1e6,  # MPa (referans: ince-cidar p*r/t)
            'lame_peak_pressure_hoop_MPa': lame_peak_hoop / 1e6,  # MPa (kalin-cidar Lame tepe, ic yuzey)
            'pressure_hoop_model': 'lame_thick_wall' if not thin_wall_valid else 'thin_wall',
            'thermal_hoop_stress': thermal_hoop_stress / 1e6,  # MPa (sadece termal)
            'longitudinal_stress': longitudinal_stress / 1e6,  # MPa
            'von_mises_stress': von_mises_stress / 1e6,  # MPa
            'hoop_safety_factor': hoop_safety_factor,
            'von_mises_safety_factor': von_mises_safety_factor,
            # İki SF raporu (Dalga 0): basınç-yalnız ve basınç+termal
            'safety_factor_pressure': safety_factor_pressure,
            'safety_factor_total': safety_factor_total,
            'allowable_stress': allowable_stress / 1e6,  # MPa (derate edilmis)
            'yield_strength_used_MPa': yield_for_design / 1e6,  # derate edilmis yield
            'thin_wall_ratio_t_over_r': t_over_r,
            'thin_wall_valid': thin_wall_valid,
            'diameter': diameter * 1000,  # mm
            'length': length * 1000  # mm
        }
    
    def _analyze_nozzle_structure(self, pressure: float, throat_diameter: float,
                                chamber_diameter: float, mat_props: Dict, nozzle_type: str) -> Dict:
        """Analyze nozzle structural requirements"""
        
        throat_radius = throat_diameter / 2
        chamber_radius = chamber_diameter / 2
        yield_strength = mat_props['yield_strength']
        safety_factor = mat_props['safety_factor']
        
        # Throat section is critical (smallest diameter, highest stress)
        allowable_stress = yield_strength / safety_factor
        min_throat_thickness = pressure * throat_radius / allowable_stress
        
        # Nozzle transition stresses (simplified)
        # Higher stress concentration at throat
        stress_concentration_factor = 2.0 if nozzle_type == 'conical' else 1.5

        # Required thickness considering stress concentration
        required_throat_thickness = min_throat_thickness * stress_concentration_factor

        # Effective (peak) stress at throat.
        # DUZELTME (2026-07-16): Eski kod effective_stress'u min_throat_thickness
        # (yigilma payi OLMADAN) uzerinden hesaplayip SCF ile carpiyordu:
        #     effective_stress = P*r_t/min_t*SCF = allowable*SCF
        # burada P ve r_t TAMAMEN sadelesiyor -> bogaz gerilmesi ve emniyet
        # faktoru (=SF_mat/SCF) gercek basinc/geometriden BAGIMSIZ bir SABIT
        # cikiyordu (totoloji). Dogrusu: ONERILEN (SCF payli) kalinliktaki gercek
        # tepe gerilmeyi, ince-cidar hoop'una (P*r_t/t) yigilma faktorunu
        # uygulayarak hesapla -> boylece raporlanan gerilme ile kullanilan
        # kalinlik TUTARLI olur ve SCF yalnizca BIR kez sayilir. Sized bogaz
        # icin sonuc allowable'a esittir, dolayisiyla SF = SF_mat (malzeme emniyet
        # faktoru) olarak dogru raporlanir. Kaynak: Peterson "Stress Concentration
        # Factors"; ince-cidar hoop Sutton & Biblarz / Roark's Ch.13.
        if required_throat_thickness > 0:
            effective_stress = (stress_concentration_factor * pressure * throat_radius
                                / required_throat_thickness)
        else:
            effective_stress = float('inf')
        
        # Nozzle wall thickness variation
        chamber_thickness = pressure * chamber_radius / allowable_stress
        
        return {
            'throat_diameter': throat_diameter * 1000,  # mm
            'min_throat_thickness': min_throat_thickness * 1000,  # mm
            'required_throat_thickness': required_throat_thickness * 1000,  # mm
            'chamber_thickness': chamber_thickness * 1000,  # mm
            'stress_concentration_factor': stress_concentration_factor,
            'throat_stress': effective_stress / 1e6,  # MPa
            'safety_factor': yield_strength / effective_stress,
            'nozzle_type': nozzle_type
        }
    
    def _analyze_end_caps(self, pressure: float, diameter: float, mat_props: Dict) -> Dict:
        """Analyze end cap (head and injector end) requirements"""
        
        radius = diameter / 2
        yield_strength = mat_props['yield_strength']
        safety_factor = mat_props['safety_factor']
        
        # Flat circular plate under pressure
        # Maximum stress at center: sigma = (3/8) * P * (r²/t²) * (3 + nu)
        # Rearranging for thickness: t = r * sqrt((3*P*(3+nu))/(8*sigma_allow))
        
        poisson_ratio = mat_props['poisson_ratio']
        allowable_stress = yield_strength / safety_factor
        
        # Flat head thickness
        flat_head_thickness = radius * np.sqrt((3 * pressure * (3 + poisson_ratio)) / (8 * allowable_stress))
        
        # Dished head thickness — ASME BPVC VIII-1 UG-32(d): 2:1 yari-elipsoidal baslik.
        # DUZELTME (2026-07-16): Eski formul pressure*radius/(2*allowable) = P*D/(4S)
        # idi; bu bir YARIMKURE (hemispherical) kalinligidir, 2:1 elipsoidal DEGIL.
        # 2:1 elipsoidal baslik silindir govdeyle yaklasik ayni kalinligi gerektirir
        # (P*D/(2S)), yarisini degil -> eski deger belirtilen baslik tipi icin 2x
        # ince, non-konservatif. Dogru ASME UG-32(d) formulu:
        #     t = P*D / (2*S*E - 0.2*P),  K = 1.0 (2:1 orani icin)
        # D = ic cap (= diameter), S = allowable_stress, E = kaynak verimi
        # (1.0; dikissiz / tam-radyografi varsayimi).
        joint_efficiency = 1.0
        dished_head_thickness = (pressure * diameter
                                 / (2 * allowable_stress * joint_efficiency - 0.2 * pressure))
        
        # Bolt circle analysis
        bolt_circle_diameter = diameter + 0.05  # 50mm larger than chamber
        bolt_circle_stress = pressure * (bolt_circle_diameter/2) / flat_head_thickness
        
        return {
            'flat_head_thickness': flat_head_thickness * 1000,  # mm
            'dished_head_thickness': dished_head_thickness * 1000,  # mm
            'recommended_type': 'dished' if dished_head_thickness < flat_head_thickness else 'flat',
            'bolt_circle_diameter': bolt_circle_diameter * 1000,  # mm
            'bolt_circle_stress': bolt_circle_stress / 1e6,  # MPa
            'head_safety_factor': allowable_stress / bolt_circle_stress if bolt_circle_stress > 0 else float('inf')
        }
    
    def _analyze_fasteners(self, pressure: float, diameter: float, mat_props: Dict) -> Dict:
        """Analyze bolt and fastener requirements"""
        
        # Total force on end cap
        total_force = pressure * np.pi * (diameter/2)**2  # N
        
        # Assume 8-12 bolts depending on diameter
        if diameter < 0.1:
            num_bolts = 6
        elif diameter < 0.2:
            num_bolts = 8
        else:
            num_bolts = 12
        
        # Force per bolt (with safety factor)
        bolt_safety_factor = 4.0
        force_per_bolt = total_force * bolt_safety_factor / num_bolts
        
        # Bolt sizing (assume steel bolts, 400 MPa allowable stress).
        # DUZELTME (2026-07-16): Civata cekme kapasitesi NOMINAL kesitten degil,
        # dis dibindeki GERILME ALANI A_t uzerinden tasinir. ISO 898-1 / Shigley
        # Tablo 8-1: A_t ~ 0.75*(pi/4*d_nom^2) (or. M10: A_t=58 mm^2 vs
        # pi/4*10^2=78.5, oran ~0.74). Eski kod gerekli alani dogrudan tam-dolu
        # daireye (pi/4*d^2) ceviriyordu -> civatayi sqrt(0.75)~0.87 kat KUCUK
        # seciyordu (non-konservatif). Dogrusu: gerekli A_t'yi guvenli nominal
        # capa cevir -> A_nom = A_t / 0.75. (400 MPa ~ 8.8 sinifi yaklasik izin
        # verilen cekme; sinif-bazli S_p icin bolted_joint.py tablosu kullanilabilir,
        # imza korundugu icin burada sabit tutuldu.)
        bolt_allowable_stress = 400e6  # Pa
        THREAD_STRESS_AREA_RATIO = 0.75  # A_t / (pi/4*d_nom^2), ISO 898-1 yaklasik
        required_stress_area = force_per_bolt / bolt_allowable_stress  # m^2 (gerekli A_t)
        required_nominal_area = required_stress_area / THREAD_STRESS_AREA_RATIO  # m^2
        required_bolt_diameter = 2 * np.sqrt(required_nominal_area / np.pi)  # m (nominal)
        
        # Standard bolt sizes (in meters)
        standard_sizes = [0.006, 0.008, 0.010, 0.012, 0.016, 0.020, 0.024, 0.030, 0.036, 0.042]  # M6 to M42
        suitable_sizes = [size for size in standard_sizes if size >= required_bolt_diameter]
        
        if suitable_sizes:
            recommended_bolt_size = min(suitable_sizes)
        else:
            # If required diameter exceeds largest standard size, use largest available
            recommended_bolt_size = max(standard_sizes)
            # Add warning about custom bolt requirement
        
        # Bolt circle
        bolt_circle_radius = (diameter/2) + 0.025  # 25mm from chamber edge
        
        # Warning if custom bolt needed
        bolt_warning = None
        if not suitable_sizes:
            bolt_warning = f"Required bolt diameter ({required_bolt_diameter*1000:.1f}mm) exceeds largest standard size. Custom bolts needed."
        
        return {
            'total_force': total_force / 1000,  # kN
            'num_bolts': num_bolts,
            'force_per_bolt': force_per_bolt / 1000,  # kN
            'required_bolt_diameter': required_bolt_diameter * 1000,  # mm
            'recommended_bolt_size': f"M{int(recommended_bolt_size*1000)}",
            'bolt_circle_radius': bolt_circle_radius * 1000,  # mm
            'bolt_spacing': 2 * np.pi * bolt_circle_radius / num_bolts * 1000,  # mm
            'bolt_safety_factor': bolt_safety_factor,
            'warning': bolt_warning
        }
    
    def _analyze_fatigue(self, stress: float, burn_time: float,
                         mat_props: Dict,
                         design_cycles: Optional[int] = None) -> Dict:
        """Yorulma analizi — Goodman ortalama-gerilme düzeltmesi (R≈0).

        DALGA 3 DÜZELTMESİ (2026-07-14) — eski sürümün üç hatası giderildi:
          1. BİRİM HATASI: 'stress' MPa cinsinden gelir (analyze_structure,
             chamber_analysis['hoop_stress'] MPa döndürür) ama Pa cinsinden
             fatigue_limit ile oranlanıyordu → SF ~1e6 kat şişkin çıkıyor,
             yorulma daima 'SAFE' görünüyordu (tehlikeyi az gösterme).
          2. GENLİK=TEPE HATASI: tam σ_max 'amplitude' sayılıyor, ortalama
             gerilme etkisi (Goodman) hiç uygulanmıyordu. Basınçlı kap her
             ateşlemede 0 → P → 0 yüklenir (R = σ_min/σ_max ≈ 0); bu
             çevrimde σ_a = σ_m = σ_max/2'dir.
          3. 'Basquin b=10' sabiti ve saniyede-1-tam-çevrim sayımı fiziksel
             dayanaksızdı (yanma içi kamara osilasyonları tam R=0
             basınçlandırma çevrimi DEĞİLDİR, genlikleri Pc'nin küçük bir
             yüzdesidir — çevrim sayılmaz).

        Model (Shigley's Mechanical Engineering Design, 10th ed., Böl. 6):
          Düzeltilmiş Goodman doğrusu (Eq. 6-46):
              1/n_f = σ_a/S_e + σ_m/S_u
          S_e : malzeme kaydındaki fatigue_limit (materials_db — kaynaklı,
                malzemeye özgü değer; jenerik 0.5·S_u kuralı yerine merkezi
                DB değeri kullanılır → parametre tutarlılığı)
          S_u : materials_db 'ultimate_strength'
          Sonlu ömür (n_f < 1): Goodman eşdeğer tam-ters genliği
              σ_ar = σ_a/(1 − σ_m/S_u)
          ile Basquin S-N eğrisi (Shigley Eq. 6-14/6-15):
              S_f = a·N^b,  a = (f·S_u)²/S_e,  b = −log10(f·S_u/S_e)/3,
              f ≈ 0.9 (Fig. 6-18 yaklaşımı — approximate)

        Args:
            stress: σ_max [MPa] — hoop gerilme (analyze_structure MPa yollar)
            burn_time: yanma süresi [s] — bilgi amaçlı; çevrim sayılmaz
            mat_props: get_material() kaydı (fatigue_limit, ultimate_strength)
            design_cycles: tasarım basınçlandırma çevrimi sayısı (hidrotest +
                test kampanyası + uçuş). None → 25 (approximate varsayım;
                endpoint/çağıran geçersiz kılabilir).
        """
        sigma_max_pa = max(float(stress), 0.0) * 1e6   # MPa → Pa
        S_e = float(mat_props['fatigue_limit'])        # Pa (materials_db)
        S_u = float(mat_props['ultimate_strength'])    # Pa (materials_db)
        if design_cycles is None:
            design_cycles = 25  # hidrotest + test kampanyası + uçuş (approx.)
        design_cycles = max(1, int(design_cycles))

        # R ≈ 0 basınç çevrimi: σ_a = σ_m = σ_max/2
        sigma_a = sigma_max_pa / 2.0
        sigma_m = sigma_max_pa / 2.0

        if sigma_a <= 0.0:
            goodman_utilization = 0.0
            fatigue_safety_factor = float('inf')
        else:
            goodman_utilization = sigma_a / S_e + sigma_m / S_u
            fatigue_safety_factor = 1.0 / goodman_utilization

        # Sonlu ömür tahmini — yalnız Goodman doğrusu aşıldıysa (n_f < 1)
        estimated_life = 'Infinite'
        cycle_margin = 'Infinite'
        lcf_warning = None
        if fatigue_safety_factor < 1.0:
            if sigma_m < S_u:
                sigma_ar = sigma_a / (1.0 - sigma_m / S_u)  # Goodman eşdeğeri
                f_frac = 0.9  # Fig. 6-18 (S_u <= ~490 MPa için 0.9; approx.)
                a_basq = (f_frac * S_u) ** 2 / S_e          # Eq. 6-14
                b_basq = -np.log10(f_frac * S_u / S_e) / 3.0  # Eq. 6-15
                N = float(max((sigma_ar / a_basq) ** (1.0 / b_basq), 1.0))
            else:
                N = 0.0  # ortalama gerilme çekme dayanımını aşıyor → statik kırılma
            estimated_life = N
            cycle_margin = N / design_cycles
            if N < 1e3:
                lcf_warning = ('Low-cycle fatigue regime (N < 1000): Basquin '
                               'extrapolation is approximate; strain-life '
                               'method recommended')

        # Durum eşikleri: Goodman SF sonsuz ömre karşı ölçülür. n_f >= 1.5
        # tipik yorulma saçılım payıdır (approximate practice). n_f < 1 ama
        # tahmini ömür tasarım çevriminin >= 10 katıysa MARGINAL (sonlu ömür
        # kabulü), aksi halde CRITICAL.
        if fatigue_safety_factor >= 1.5:
            fatigue_status = 'SAFE'
        elif fatigue_safety_factor >= 1.0:
            fatigue_status = 'MARGINAL'
        elif (isinstance(estimated_life, float)
              and estimated_life / design_cycles >= 10.0):
            fatigue_status = 'MARGINAL'
        else:
            fatigue_status = 'CRITICAL'

        result = {
            # Eski anahtarlar korunur (sözleşme testleri) — anlamları düzeltildi
            'stress_amplitude': sigma_a / 1e6,   # MPa (σ_a = σ_max/2, R=0)
            'fatigue_limit': S_e / 1e6,          # MPa
            'fatigue_safety_factor': fatigue_safety_factor,  # Goodman n_f
            'estimated_cycles': design_cycles,   # tasarım çevrim sayısı
            'estimated_life': estimated_life,    # çevrim sayısı | 'Infinite'
            'fatigue_status': fatigue_status,
            # Yeni alanlar (Dalga 3)
            'max_stress': sigma_max_pa / 1e6,    # MPa (σ_max)
            'mean_stress': sigma_m / 1e6,        # MPa (σ_m = σ_max/2)
            'stress_ratio_R': 0.0,               # basınç çevrimi 0→P→0
            'ultimate_strength': S_u / 1e6,      # MPa
            'goodman_utilization': goodman_utilization,  # σa/Se + σm/Su
            'cycle_margin': cycle_margin,        # tahmini ömür / tasarım çevrimi
            'design_cycles': design_cycles,
            'model': ('Modified Goodman mean-stress correction, R=0 pressure '
                      'cycle (Shigley 10th ed. Eq. 6-46)'),
            'assumptions': [
                'Each firing = one full 0 -> P -> 0 pressure cycle (R = 0)',
                'sigma_a = sigma_m = sigma_max/2',
                'S_e taken from central material record '
                '(materials_db fatigue_limit)',
                'Combustion oscillations are not counted as full cycles',
                f'Design cycle count = {design_cycles} (proof test + test '
                f'campaign + flight; approximate, override via parameter)',
            ],
        }
        if lcf_warning:
            result['warning'] = lcf_warning
        return result
    
    def _calculate_weight(self, chamber_analysis: Dict, nozzle_analysis: Dict,
                        end_cap_analysis: Dict, mat_props: Dict) -> Dict:
        """Calculate structural weight"""
        
        density = mat_props['density']
        
        # Chamber weight
        chamber_thickness = chamber_analysis['recommended_thickness'] / 1000  # m
        chamber_diameter = chamber_analysis['diameter'] / 1000  # m
        chamber_length = chamber_analysis['length'] / 1000  # m
        
        chamber_volume = np.pi * ((chamber_diameter/2 + chamber_thickness)**2 - (chamber_diameter/2)**2) * chamber_length
        chamber_weight = chamber_volume * density
        
        # Nozzle weight (simplified)
        nozzle_weight = chamber_weight * 0.3  # Estimate as 30% of chamber weight
        
        # End caps weight
        end_cap_thickness = min(end_cap_analysis['flat_head_thickness'], end_cap_analysis['dished_head_thickness']) / 1000
        end_cap_area = np.pi * (chamber_diameter/2 + chamber_thickness)**2
        end_caps_weight = 2 * end_cap_area * end_cap_thickness * density  # Two end caps
        
        # Total weight
        total_weight = chamber_weight + nozzle_weight + end_caps_weight
        
        return {
            'chamber_weight': chamber_weight,  # kg
            'nozzle_weight': nozzle_weight,    # kg
            'end_caps_weight': end_caps_weight,  # kg
            'total_weight': total_weight,      # kg
            'weight_breakdown': {
                'chamber_percent': chamber_weight / total_weight * 100,
                'nozzle_percent': nozzle_weight / total_weight * 100,
                'end_caps_percent': end_caps_weight / total_weight * 100
            }
        }
    
    def _analyze_safety_factors(self, chamber_analysis: Dict, nozzle_analysis: Dict,
                              end_cap_analysis: Dict, mat_props: Dict,
                              buckling_analysis: Optional[Dict] = None) -> Dict:
        """Analyze overall safety factors.

        DENETIM DUZELTMESI (2026-06): Burkulma (buckling) emniyet faktoru de
        minimum SF hesabina dahil edilir. chamber_analysis['hoop_safety_factor']
        artik TERMAL+BASINC toplam gerilmeye ve DERATE edilmis yield'e gore
        hesaplanmis olarak gelir; dolayisiyla minimum SF gercekci-konservatif olur.
        """

        sf_candidates = {
            'chamber_hoop': chamber_analysis['hoop_safety_factor'],
            'chamber_von_mises': chamber_analysis['von_mises_safety_factor'],
            'nozzle': nozzle_analysis['safety_factor'],
            'end_cap': end_cap_analysis['head_safety_factor']
        }
        if buckling_analysis is not None:
            sf_candidates['buckling_axial'] = buckling_analysis['axial_buckling_safety_factor']

        min_safety_factor = min(sf_candidates.values())

        # Risk assessment
        if min_safety_factor < 2.0:
            risk_level = 'HIGH'
            status = 'UNSAFE'
        elif min_safety_factor < 3.0:
            risk_level = 'MEDIUM'
            status = 'MARGINAL'
        elif min_safety_factor < 4.0:
            risk_level = 'LOW'
            status = 'ACCEPTABLE'
        else:
            risk_level = 'VERY LOW'
            status = 'SAFE'

        # UNSAFE durumunda hangi yükün domine ettiğini açıkla (Dalga 0):
        # termal gerilme basınç gerilmesini aşıyorsa sorun soğutma/malzeme
        # kaynaklıdır, cidar kalınlaştırmak tek başına çözmez.
        explanation = ''
        if status == 'UNSAFE':
            thermal = chamber_analysis.get('thermal_hoop_stress', 0.0)
            pressure = chamber_analysis.get('pressure_hoop_stress', 0.0)
            explanation = ('thermal-dominated' if thermal > pressure
                           else 'pressure-dominated')

        recommendations = []
        if min_safety_factor < 3.0:
            recommendations.append('Increase wall thickness')
            recommendations.append('Consider higher strength material')
        if chamber_analysis['hoop_safety_factor'] < 3.0:
            recommendations.append('Increase chamber wall thickness')
        if nozzle_analysis['safety_factor'] < 3.0:
            recommendations.append('Increase nozzle throat thickness')
        # YENI uyarilar (termal + burkulma + ince-cidar)
        if chamber_analysis.get('thermal_hoop_stress', 0.0) > chamber_analysis.get('pressure_hoop_stress', 0.0):
            recommendations.append('Thermal stress dominates: add cooling or thermal barrier')
        if not chamber_analysis.get('thin_wall_valid', True):
            recommendations.append('Thin-wall assumption invalid (t/r>=0.1): use thick-wall (Lame) analysis')
        if buckling_analysis is not None and buckling_analysis['axial_buckling_safety_factor'] < 2.0:
            recommendations.append('Axial buckling risk (NASA SP-8007): stiffen or thicken wall')
        derate = chamber_analysis.get('yield_strength_used_MPa')
        if derate is not None and derate < mat_props['yield_strength'] / 1e6 * 0.7:
            recommendations.append('Severe temperature derating (>30% yield loss): cool wall or change material')

        return {
            'minimum_safety_factor': min_safety_factor,
            'risk_level': risk_level,
            'status': status,
            'explanation': explanation,
            'safety_factors': sf_candidates,
            'recommendations': recommendations
        }