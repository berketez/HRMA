"""
Structural Analysis Module
Wall thickness calculation and safety factor analysis for hybrid rocket motors
"""

import numpy as np
import json
from typing import Dict, List, Tuple, Optional

from hrma.data.materials_db import build_materials_view
# Cıvata mukavemet sınıfı tablosu (ISO 898-1:2013 Table 3) — depodaki TEK
# kaynak. Aynı tablo /api/bolted-joint ucunu da besler; motor sonucundaki
# cıvata bloğu artık ondan habersiz değil (v2.6.26).
from hrma.analysis.bolted_joint import _bolt_class_props

# Kullanıcı tasarım emniyet katsayısı vermediğinde cıvata boyutlandırmasında
# kullanılan BEYAN EDİLEN varsayılan (literatür kaynağı yoktur; eski
# sürümdeki 4.0 davranışı korunur ki girdisiz koşularda sonuç değişmesin).
_BOLT_SAFETY_FACTOR_DEFAULT = 4.0

# Cidar sicakligi bilinmedigi durumda kullanilan radyasyon-denge tahmini:
# sogutmasiz gaz-tarafi cidar, malzemenin kisa-sureli servis sinirinin bu
# kadarina kadar isinir varsayilir (bkz. _estimate_wall_delta_T). Gercek
# deger her zaman isi transferi modulunden alinmalidir.
WALL_TEMP_SERVICE_FRACTION = 0.9

# İmalat/korozyon payı: boyutlandırma (size) modunda kod-minimum kalınlığa
# uygulanan pay. BU BİR EMNİYET FAKTÖRÜ DEĞİLDİR — toleranslı sac/boru
# temini, tornalama payı ve korozyon payı için ayrılmış malzeme kalınlığıdır
# (ASME BPVC VIII-1 UG-25 korozyon payı deseni; sayısal değer kod
# zorunluluğu değil, BEYAN EDİLEN tasarım kabulüdür — kaynak yok).
# F003 (2026-07-25): eskiden 1.2 çarpanı fonksiyon gövdesine gömülüydü ve
# raporlanan emniyet faktörünü doğrudan şişiriyordu; artık ayrı isimli sabit
# olarak çıktıda beyan edilir.
MANUFACTURING_ALLOWANCE_FACTOR = 1.2

# ASME BPVC VIII-2 Part 5.2.2 / Section III NB-3222.2 gerilme sınıflandırması:
#   birincil membran (P)      -> sınır Sm
#   birincil+ikincil (P+Q)    -> sınır 3*Sm (shakedown / plastik uyum)
# Sm, ASME Section II-D (1999+) kriteriyle min(Su/3, Sy/1.5) alınır.
ASME_SM_UTS_DIVISOR = 3.0
ASME_SM_YIELD_DIVISOR = 1.5
ASME_SHAKEDOWN_MULTIPLIER = 3.0


def published_material_record(mat_props):
    """materials_db kaydının YANITA konan biçimi — beyanlarıyla birlikte.

    İki modül (yapısal analiz + ısı transferi) AYNI kaydı yayımlıyor. Metin
    iki yerde yazılırsa biri güncellenip diğeri eskiyor; tek kaynak burasıdır.

    Yayımlanan iki beyan:

    ``safety_factor_basis``
        Ad çakışması: ``safety_factor`` materials_db'nin bu malzeme için
        ÖNERDİĞİ tasarım katsayısıdır (çelik 4,0; inconel 3,0), kullanıcının
        girdiği tasarım emniyet katsayısı DEĞİLDİR. Değer doğru, sunum
        yanıltıcıydı: kullanıcı SF=6 girip burada 4,0 görünce "girdim yutuldu"
        diye okuyordu.

    ``derating_curve``
        v2.6.26 SABİT ÇIKTI DÜZELTMESİ. Eğri ham sözlük olarak
        (``{20: 1.00, 200: 0.92, ...}``) yayımlanıyordu; JSON'da anahtar
        metne dönüşünce yaprağın ADI sayının kendisi oluyordu
        (``derating_curve.20``). 20 °C noktası HER malzemede tam 1.0
        olduğundan bu yaprak her koşuda sabit çıkıyor, adı da hiçbir şey
        anlatmadığı için neden sabit olduğu okunamıyordu. Artık adlandırılmış
        iki dizi + gerekçe olarak yayımlanır. Hesap zinciri bu biçimi DEĞİL,
        materials_db kaydının kendisini okur (``_derate_strength``,
        ``pressure_vessel``); burada yalnız SUNUM değişir.
    """
    if not isinstance(mat_props, dict):
        return mat_props
    published = dict(
        mat_props,
        safety_factor_basis=(
            'materials_db recommended design factor for this material - NOT '
            'the design safety factor entered by the user'),
    )
    curve = mat_props.get('derating_curve')
    if isinstance(curve, dict) and curve:
        try:
            points = sorted((float(t), float(r)) for t, r in curve.items())
        except (TypeError, ValueError):
            return published
        published['derating_curve'] = {
            'temperatures_c': [p[0] for p in points],
            'yield_retention': [p[1] for p in points],
            'basis': (
                'tabulated yield-strength retention of this material versus '
                'metal temperature, read from the materials_db record '
                '(MMPDS / MIL-HDBK-5 derating pattern). temperatures_c and '
                'yield_retention are DATABASE values, not computed from this '
                'design; the first point is the room-temperature reference '
                'where the retention is 1.0 by definition, because the curve '
                'is normalised to the room-temperature yield strength. '
                'Intermediate temperatures are linearly interpolated and the '
                'ends are clamped.'),
        }
    return published


def _mk_warning(code: str, severity: str = 'info', **params) -> Dict:
    """Yapılandırılmış iki-dilli uyarı/öneri kaydı (D-track sözleşmesi).

    Backend dilsiz kalır; frontend ``TF(code, params)`` ile metni kurar.
    Şema: ``{code: 'warn.<subsystem>.<slug>', params: {...}, severity: ...}``.
    Öneri metinleri artık sabit İngilizce string DEĞİL; i18n sözlüğü koda
    göre TR/EN metni üretir. Katalog: docs/v262_specs/D_codes_analysis.md.
    """
    return {'code': code, 'params': params, 'severity': severity}


def _shigley_fatigue_strength_fraction(s_ut_pa: float) -> float:
    """Shigley Fig. 6-18 yorulma dayanımı kesri f(S_ut).

    v2.6.2 fizik denetimi, bulgu F181. Kod bu kesri SABİT 0.9 alıyordu ve
    docstring'inde bunu "S_u <= ~490 MPa için" diye kabul ediyordu, ama zarf
    hiç zorlanmıyordu: steel_4130 (730 MPa), inconel_718 ve titanyum
    alaşımlarında gerçek f ~0.77-0.82'dir.

    f'in fazla alınması Basquin çapasını (10^3 çevrimdeki gerilme) yükseltir
    ve sonlu ömrü OLDUĞUNDAN UZUN gösterir — konservatif olmayan yön.

    Shigley's Mechanical Engineering Design, 10. baskı, Fig. 6-18'den
    okunan çapa noktaları (S_ut kpsi -> f), aralarında doğrusal enterpolasyon:
        70 kpsi  (483 MPa) -> 0.90
       100 kpsi  (689 MPa) -> 0.82
       150 kpsi (1034 MPa) -> 0.79
       200 kpsi (1379 MPa) -> 0.77
    Bant dışında uçtaki değer korunur (eğri yataylaşır).
    """
    import numpy as _np
    s_mpa = float(s_ut_pa) / 1e6
    pts_mpa = [483.0, 689.0, 1034.0, 1379.0]
    pts_f = [0.90, 0.82, 0.79, 0.77]
    return float(_np.interp(s_mpa, pts_mpa, pts_f))


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
        gerilmesinin klasik buyuklugu:

            sigma_thermal = E * alpha * delta_T / (2 * (1 - nu))

        Kaynak: Timoshenko & Goodier "Theory of Elasticity" (uzun silindir,
        eksenel kisitli hal); Boley & Weiner "Theory of Thermal Stresses"
        Ch.10-11; Roark's Formulas for Stress & Strain 9th ed. Ch.16.

        DUZELTME (v2.5.2): onceki surum "konservatif olmak icin" 2 faktorunu
        dusurmuyor, yani gerilmeyi sistematik olarak 2 KAT sisiriyordu. Bu
        muhafazakarlik degil hataydi: her sicak motorun von Mises SF'si 1'in
        altina dusuyor, tasarim penceresi kayboluyordu. Klasik yuzey degeri
        geri konuldu; muhafazakarlik, gradyanin (delta_T) tahmininde ve
        sicaklik derating'inde korunur.

        delta_T <= 0 (sogutmasiz/izotermal cidar) ise termal gerilme 0 alinir.
        """
        E = mat_props['elastic_modulus']
        alpha = mat_props['thermal_expansion']
        nu = mat_props['poisson_ratio']

        dT = max(0.0, delta_T)
        sigma_thermal = E * alpha * dT / (2.0 * (1.0 - nu))

        return {
            'delta_T': dT,                          # K  (kullanilan cidar gradyani)
            'thermal_hoop_stress': sigma_thermal,   # Pa (tensile, dis yuzde)
            'thermal_hoop_stress_MPa': sigma_thermal / 1e6,
            'formula': 'sigma_th = E*alpha*dT/(2*(1-nu))  [Timoshenko/Boley-Weiner/Roark Ch.16]'
        }

    def _estimate_wall_delta_T(self, motor_data: Dict, mat_props: Dict) -> Tuple[float, float]:
        """Cidar ic/dis sicaklik degerlerini tahmin et.

        Tercih sirasi:
          1) motor_data['wall_temperature_hot'] / 'wall_temperature_cold'
             (isi transferi modulunun cidar analizinden gelen GERCEK degerler;
             hybrid/liquid/solid motor zincirleri bu anahtarlari doldurur)
          2) chamber_temperature'tan radyasyon-denge TAHMINI: sogutmasiz cidar
             ic yuzu alev sicakligina degil, isi kaybiyla dengelendigi bir
             ara sicakliga oturur.

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

        # DUZELTME (v2.5.2): eski tahmin ic yuzu min(T_hazne, max_service_temp)
        # aliyordu, yani cidar sicakligi bilinmeyen HER motor tam olarak
        # malzeme servis sinirinda varsayiliyordu. Bu, hem derating'i hem
        # gradyani ayni anda en kotu degerine sabitleyip her sicak motoru
        # CRITICAL yapiyordu. Kisa sureli atesleme + radyasyon/iletim kaybi
        # altinda cidar servis sinirina TAM oturmaz; servis sinirinin bir
        # miktar altinda dengelenir. Tahmin bu nedenle servis sinirinin
        # WALL_TEMP_SERVICE_FRACTION kati ile sinirlanir (yine alev
        # sicakligini asamaz). Gercek deger her zaman isi transferi
        # modulunden (secenek 1) gelmelidir.
        T_cap = mat_props.get('max_service_temp', float(T_chamber)) * WALL_TEMP_SERVICE_FRACTION
        T_inner = min(float(T_chamber), T_cap)

        # DUZELTME (v2.5.2, ikinci tur): dis yuzu DOGRUDAN ortam sicakligina
        # esitlemek fiziksel degildi. Cidar sicakligi bilinmeyen motor
        # "sogutmasiz" kabul edilmelidir; sogutmasiz ince metal cidarda
        # kesit boyunca gradyan KUCUKTUR, cunku iletim direnci (t/k) dis
        # yuzey kayip direncinden kat kat kucuktur. Dis yuzey enerji dengesi:
        #
        #   k/t * (T_ic - T_dis) = h_konv * (T_dis - T_ortam)
        #                          + eps * sigma * (T_dis^4 - T_ortam^4)
        #
        # 5 mm celikte (k/t = 9000 W/m^2K) bu denge ~2 K'lik bir gradyan
        # verir; eski varsayim 430 K veriyordu, yani gercek olmayan bir
        # rejeneratif sogutma (3.9 MW/m^2 atim) varsayiyordu. Sonuc: cidar
        # sicakligi verilmeyen HER motor sahte CRITICAL cikiyordu.
        # Gercek sogutmali degerler yol 1'den (isi transferi modulu) gelir.
        t_wall = float(motor_data.get('wall_thickness', 0.005) or 0.005)
        k_wall = float(mat_props.get('thermal_conductivity', 45.0) or 45.0)
        emissivity = float(mat_props.get('emissivity', 0.3) or 0.3)
        h_conv_out = 10.0        # W/m^2K, dogal konveksiyon (durgun hava)
        SIGMA_SB = 5.670374419e-8

        T_amb = float(T_ambient)
        T_outer = T_inner        # baslangic: izotermal
        for _ in range(60):      # sabit nokta iterasyonu (monoton, hizli yakinsar)
            q_loss = (h_conv_out * (T_outer - T_amb)
                      + emissivity * SIGMA_SB * (T_outer ** 4 - T_amb ** 4))
            T_new = T_inner - q_loss * t_wall / k_wall
            T_new = min(T_inner, max(T_amb, T_new))
            if abs(T_new - T_outer) < 1e-3:
                T_outer = T_new
                break
            T_outer = 0.5 * (T_outer + T_new)   # gevsetme (radyasyon T^4 icin)

        return T_inner, T_outer

    def _check_buckling(self, pressure: float, radius: float, thickness: float,
                        length: float, mat_props: Dict,
                        axial_compression_force: float = 0.0) -> Dict:
        """Ince-cidarli silindir burkulma kontrolu (NASA SP-8007).

        Iki mod kontrol edilir:
          A) Eksenel basma burkulmasi (itki/montaj/ucus basma yuku):
             sigma_cl = E / sqrt(3(1-nu^2)) * (t/r)      [klasik]
             sigma_cr = gamma * sigma_cl                  [tasarim]
             gamma = 1 - 0.901*(1 - exp(-phi)),  phi = (1/16)*sqrt(r/t)
          B) Dis basinc burkulmasi (uzun silindir, klasik elastik):
             p_cl = E/(4(1-nu^2)) * (t/r)^3

        Kaynak: NASA SP-8007 "Buckling of Thin-Walled Circular Cylinders"
        (revised 1968), NTRS 19680026348.

        DENETIM DUZELTMESI (#203): Eski surum, burkulma emniyetini kapali-uc
        IC BASINC boylamsal gerilmesiyle (p*r/2t) karsilastiriyordu. Bu gerilme
        CEKMEdir — kabuk burkulmaz, aksine stabilize olur (SP-8007 basincli
        silindirlerde knockdown'in IYILESTIGINI soyler). Dogru burkulma yuku
        GERCEK eksenel BASMAdir (itki, montaj on-yuku, ucus ataleti):
            sigma_basma = F / (2*pi*r*t)
            net = max(sigma_basma - p*r/(2t), 0)   [basinc cekmesi kredisi]
        Basinc-stabilizasyon gamma iyilesmesi muhafazakarlik icin ALINMAZ;
        yalnizca net-kesit gerilme kredisi kullanilir. Basma yuku yoksa
        (F=0) net=0 -> eksenel burkulma bu yuk durumunda olusmaz, SF=inf.

        FIZIK DENETIMI F075 (2026-07-25) — ZARF DUZELTMESI (formuller dogruydu).
        Denklemler NASA SP-8007 ile birebir uyusuyor; sorun YUK DURUMU
        zarfindaydi:
          (a) IKI YUK DURUMU degerlendirilir. Burkulma gercekte BASINCSIZ
              durumda (nakliye, montaj on-yuku, ates oncesi/kapanis, ucus
              atalet yuku) kritiktir; eski surum yalnizca basincli duruma
              bakiyordu. Artik hem basincli hem basincsiz durum hesaplanir ve
              YONETEN (dusuk SF'li) olan raporlanir. Basincsiz durumda cekme
              kredisi yoktur, dolayisiyla o durum daima yonetir; basincli
              durum tani amaciyla ayrica raporlanir.
          (b) STABILIZE KREDI ALT SINIR BASINCTAN alinir. Eski surum krediyi
              tasarim basinci (1.5*Pc) ile hesapliyordu; kredi CIKARILDIGI
              icin daha yuksek tasarim basinci NET BASMAYI AZALTIYOR, yani
              konservatif olmuyordu. Cagiran artik MEOP'u (Pc) gecer.
          (c) 'length' argumani artik cikti tanisinda kullanilir: dis basinc
              formulu UZUN silindir varsayimidir (uzunluktan bagimsiz), kisa
              silindirlerde gercek kritik basinc daha yuksektir -> bu form
              konservatiftir. L/r orani raporlanarak varsayim BEYAN edilir.
        Uretim yolu notu: cagirici zincirin 'thrust' anahtarini gecirmesi
        gerekir; gecirilmezse F=0 ve eksenel burkulma her zaman SAFE cikar.
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

        # Uygulanan NET eksenel BASMA gerilmesi (bkz. docstring #203):
        # basma (F/2πrt) eksi ic-basinc boylamsal CEKME kredisi (p*r/2t).
        # F075: kredi YALNIZ basincli yuk durumunda gecerlidir; basincsiz
        # durumda (nakliye/montaj/atesleme oncesi) kredi YOKTUR.
        if thickness > 0 and radius > 0:
            sigma_compression = (axial_compression_force
                                 / (2.0 * np.pi * radius * thickness))
            sigma_pressure_tension = pressure * radius / (2.0 * thickness)
            applied_pressurized = max(
                sigma_compression - sigma_pressure_tension, 0.0)
            applied_unpressurized = max(sigma_compression, 0.0)
        else:
            sigma_compression = float('inf')
            sigma_pressure_tension = 0.0
            applied_pressurized = float('inf')
            applied_unpressurized = float('inf')

        def _sf(applied: float) -> float:
            return (sigma_cr_axial / applied if applied > 0 else float('inf'))

        sf_pressurized = _sf(applied_pressurized)
        sf_unpressurized = _sf(applied_unpressurized)
        # Yoneten yuk durumu: dusuk SF'li olan (kredi yalnizca yardim ettigi
        # icin pratikte daima basincsiz durum).
        if sf_unpressurized <= sf_pressurized:
            governing_case = 'unpressurized'
            applied_axial_stress = applied_unpressurized
            axial_buckling_sf = sf_unpressurized
        else:
            governing_case = 'pressurized'
            applied_axial_stress = applied_pressurized
            axial_buckling_sf = sf_pressurized

        # B) Dis basinc burkulmasi (uzun silindir klasik)
        # Konservatif olarak uygulanan dis basinci = tasarim basincinin
        # buyuklugu kadar alinabilir; burada referans olarak 1 atm dis ortam
        # (kapali kazan ic basinci ic'e dogru cidari destekler, ancak vakum/
        # dis basinc senaryosu icin kritik dis basinc raporlanir).
        p_cr_external = E / (4.0 * (1.0 - nu**2)) * (thickness / radius)**3 if radius > 0 else float('inf')
        # F075(c): bu form UZUN silindir varsayimidir (L'den bagimsiz). Kisa
        # silindirlerde gercek kritik dis basinc daha yuksektir, dolayisiyla
        # form konservatiftir; varsayim L/r ile birlikte BEYAN edilir.
        length_over_radius = (float(length) / radius
                              if radius > 0 and length else None)

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
            # #203 sonrasi eklenen tanilar: uygulanan basma kuvveti ve
            # ic-basinc cekme kredisi (raporlanan applied = NET basma)
            'axial_compression_force_N': axial_compression_force,
            'pressure_stabilizing_stress_MPa': (sigma_pressure_tension / 1e6
                                                if np.isfinite(sigma_pressure_tension) else 0.0),
            # F075: iki yuk durumu ayri ayri raporlanir; yoneten olan
            # yukaridaki 'axial_buckling_safety_factor' alanina yazilir.
            'axial_buckling_safety_factor_pressurized': sf_pressurized,
            'axial_buckling_safety_factor_unpressurized': sf_unpressurized,
            'applied_axial_stress_pressurized_MPa': (
                applied_pressurized / 1e6
                if np.isfinite(applied_pressurized) else float('inf')),
            # v2.6.26 — SABİT ÇIKTI BEYANI. Bu alan sık sık TAM 0.0 çıkar ve
            # okuyucu "hesaplanmadı" sanır; oysa hesaplanır ve TABANA KENETLİ
            # (max(...,0)) çıkar: ic-basinc boylamsal cekmesi eksenel basmayi
            # asinca net basma sifirdir.
            'applied_axial_stress_pressurized_basis': (
                'net axial compression in the pressurised load case: '
                'max(thrust compression F/(2*pi*r*t) - internal pressure '
                'longitudinal tension p*r/(2t), 0). A value of exactly zero '
                'is the clamp, not a missing model: the pressure tension '
                'exceeds the axial compression, so this load case cannot '
                'buckle the shell and the unpressurised case governs. Both '
                'contributors are published next to this field '
                '(axial_compression_force_N, '
                'pressure_stabilizing_stress_MPa).'),
            'applied_axial_stress_unpressurized_MPa': (
                applied_unpressurized / 1e6
                if np.isfinite(applied_unpressurized) else float('inf')),
            'governing_load_case': governing_case,
            'stabilizing_pressure_bar': pressure / 1e5,
            # F075(c): dis basinc formu uzunluktan bagimsiz (uzun silindir);
            # kisa silindirlerde konservatif.
            'length_over_radius': length_over_radius,
            'external_pressure_model': (
                'long-cylinder classical form (length-independent); '
                'conservative for short cylinders'),
            'source': 'NASA SP-8007 (1968), NTRS 19680026348'
        }
    
    def analyze_structure(self, motor_data: Dict, material: str = 'steel_4130',
                         design_pressure_factor: float = 1.5,
                         design_safety_factor: Optional[float] = None,
                         actual_wall_thickness: Optional[float] = None) -> Dict:
        """
        Complete structural analysis

        Args:
            motor_data: Motor performance and geometry data
            material: Material type
            design_pressure_factor: Safety factor for design pressure
            design_safety_factor: Tasarım emniyet katsayısı hedefi (v2.6.26 —
                arayüzün 'Safety Factor' alanı; _analyze_chamber_wall bunu
                zaten destekliyordu ama buradan İLETİLMİYORDU, alan ölüydü).
                None -> malzeme kaydındaki eski varsayılan.
            actual_wall_thickness: Kullanıcının GERÇEK cidar kalınlığı [m].
                Verilirse hazne cidarı DOĞRULAMA modunda değerlendirilir
                (SF gerçek cidardan); None -> eski boyutlandırma modu.

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
                derating=der, wall_delta_T=dT,
                actual_thickness=actual_wall_thickness,
                design_safety_factor=design_safety_factor
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

        # Burkulma kontrolu (NASA SP-8007) - hazne cidari geometrisiyle.
        # #203: eksenel BASMA yuku olarak motor itkisi kullanilir (ucus/montaj
        # basmasinin ust sinari — itkinin tamami kabuktan gecer varsayimi,
        # muhafazakar). motor_data'da thrust yoksa 0 -> saf ic basinc
        # eksenel burkulma yaratamaz (cekme), SF=inf/SAFE raporlanir.
        # FIZIK DENETIMI F075(b) (2026-07-25): stabilize eden ic basinc
        # kredisi ALT SINIR basinctan (MEOP = Pc) alinir, tasarim basincindan
        # (1.5*Pc) DEGIL. Kredi net basmadan CIKARILDIGI icin daha yuksek bir
        # basinc kullanmak net basmayi azaltir, yani konservatif olmaz.
        # OLCULDU (Pc=50 bar, D=150 mm, F=500 kN, T_ic=860 K): kredi
        # 27.74 MPa -> 18.49 MPa; basincli durum SF 181.09 -> 161.66.
        # Kaynak: NASA SP-8007 (1968) — basinc stabilizasyonu yalnizca fiilen
        # mevcut olan basinctan kredi alir.
        # v2.6.26: burkulma DEĞERLENDİRİLEN cidarla yapılır — doğrulama
        # modunda kullanıcının gerçek cidarı, boyutlandırma modunda önerilen
        # kalınlık (o modda iki değer zaten aynıdır).
        chamber_t = chamber_analysis['wall_thickness_used_mm'] / 1000.0  # m
        axial_force = float(motor_data.get('thrust', 0.0) or 0.0)  # N
        buckling_analysis = self._check_buckling(
            chamber_pressure, chamber_diameter / 2.0, chamber_t,
            chamber_length, mat_props,
            axial_compression_force=axial_force,
        )
        
        # Nozzle analysis
        # v2.6.26 — TASARIM EMNİYET KATSAYISI ARTIK BURAYA DA GEÇİYOR.
        # Üç fonksiyon (lüle, kapak, cıvata) kullanıcının SF girdisini
        # destekliyordu ama çağrı satırları onu geçmiyordu; sonuçta
        # kullanıcının 'Safety Factor' alanı YALNIZ hazne cidarına
        # uygulanıyor, lüle ve kapak malzeme kaydının kendi katsayısında
        # (çelikte 4.0) kilitli kalıyordu. ÖLÇÜLDÜ: safety_factor=2.0
        # girildiğinde nozzle_analysis.safety_factor ve
        # end_cap_analysis.head_safety_factor 4.0'da SABİT kaldı — tek
        # motorda iki farklı tasarım emniyet katsayısı kullanılıyordu.
        nozzle_analysis = self._analyze_nozzle_structure(
            design_pressure, throat_diameter, chamber_diameter, mat_props,
            nozzle_type, design_safety_factor=design_safety_factor
        )

        # End cap analysis
        end_cap_analysis = self._analyze_end_caps(
            design_pressure, chamber_diameter, mat_props,
            design_safety_factor=design_safety_factor
        )

        # Bolt/fastener analysis
        fastener_analysis = self._analyze_fasteners(
            design_pressure, chamber_diameter, mat_props,
            design_safety_factor=design_safety_factor,
            bolt_property_class=motor_data.get('bolt_property_class')
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
        # FIZIK DENETIMI F074 (2026-07-25): dayanim derating'i KESIT ORTALAMA
        # sicakliginda (yoneten senaryonun derating sicakligi) yapilir, ancak
        # SERVIS SINIRI / yumusama / surunme kontrolu TEPE (ic yuz) metal
        # sicakliginda yapilmalidir. Eski cagri yalnizca wall_temp_structural
        # geciyordu; 'cooled_gradient' yonettiginde bu ORTALAMA cidar
        # sicakligidir ve sicak yuz servis sinirini astiginda bile bayrak
        # False kaliyordu. OLCULDU (T_ic=860 K, T_dis=560 K, steel_4130,
        # servis siniri 811 K): oran 0.8755 -> 1.0604, exceeds False -> True.
        # Kaynak: MMPDS / malzeme ureticisi kisa-sureli maruziyet sinirlari.
        safety_analysis = self._analyze_safety_factors(
            chamber_analysis, nozzle_analysis, end_cap_analysis, mat_props,
            buckling_analysis=buckling_analysis,
            wall_temperature_K=wall_temp_structural,
            peak_wall_temperature_K=T_inner_wall,
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
                # F074: strength_derating['exceeds_max_service_temp'] KESIT
                # ORTALAMA sicakliginda hesaplanir (derating icin dogru taban),
                # bu yuzden sicak yuz limiti astiginda False kalabilir. Servis
                # siniri kararinin dogru tabani TEPE (ic yuz) sicakligidir.
                'exceeds_max_service_temp_peak':
                    safety_analysis.get('exceeds_max_service_temp_peak', False),
                'service_temperature_basis': (
                    'peak (inner-wall) metal temperature; strength derating '
                    'uses the section-average temperature'),
            },
            'buckling_analysis': buckling_analysis,
            # v2.6.26 — AD CAKISMASI BEYAN EDILIYOR.
            # mat_props['safety_factor'] materials_db'nin bu malzeme icin
            # ONERDIGI tasarim katsayisidir (celik 4,0; inconel 3,0).
            # Kullanicinin girdigi tasarim emniyet katsayisi DEGILDIR ama
            # ayni adi tasiyor: kullanici SF=6 girip bu alanda 4,0 gorunce
            # 'girdim yutuldu' diye okuyor. Deger dogru, sunum yaniltici.
            'material_properties': published_material_record(mat_props),
            'design_parameters': {
                'material': material,
                'design_pressure': design_pressure / 1e5,  # bar
                'design_pressure_factor': design_pressure_factor,
                # v2.6.26 — SABİT ÇIKTI BEYANI. Bu çarpan çağıran motorun
                # geçtiği bir SABİTTİR (hibritte hybrid_rocket_engine.py
                # analyze_structure çağrısında design_pressure_factor=1.5) ve
                # kullanıcının emniyet katsayısı DEĞİLDİR: ikisi çarpışır.
                'design_pressure_factor_basis': (
                    'design pressure = chamber pressure x this design '
                    'pressure factor. The factor is passed in as a constant '
                    'by the calling engine, it is NOT computed here and it is '
                    'NOT the safety_factor entered by the user - it is a '
                    'separate multiplier that compounds with it (proof/burst '
                    'pressure margin over MEOP).'),
                'wall_temperature_K': wall_temp_structural
            }
        }
    
    def _analyze_chamber_wall(self, pressure: float, diameter: float,
                            length: float, mat_props: Dict,
                            derating: Optional[Dict] = None,
                            wall_delta_T: float = 0.0,
                            actual_thickness: Optional[float] = None,
                            design_safety_factor: Optional[float] = None) -> Dict:
        """Hazne cidarı: BOYUTLANDIR (size) veya DOĞRULA (verify).

        DENETIM DUZELTMESI (2026-06): Artik TERMAL gerilme ve sicaklik
        DERATING'i dahil edilir. Onceki surum:
          - termal hoop gerilmeyi tamamen ihmal ediyordu,
          - oda-sicakligi yield'ini kullaniyordu (3000 K cidarda gercek-disi).
        Bu, SF'yi gercegin cok ustunde gosteriyordu. Toplam gerilme:
            sigma_total_hoop = sigma_pressure_hoop + sigma_thermal
        ve SF'ler DERATE EDILMIS yield'e gore hesaplanir.

        FİZİK DENETİMİ F003 (2026-07-25) — DÖNGÜSEL MANTIK KALDIRILDI.
        Eski akış şuydu:
            allowable = sigma_y_der / SF_mal
            t_rec     = 1.2 * P*r/allowable
            sigma     = P*r/t_rec
            SF        = sigma_y_der / sigma
        Bu cebirsel olarak SF = SF_mal * 1.2 verir; P, r, D, tasarım basınç
        faktörü ve malzeme dayanımı TAMAMEN sadeleşir. ÖLÇÜLDÜ (steel_4130,
        D=150 mm): Pc = 5 / 20 / 50 bar için SF hep 4.8000, hoop hep
        95.54 MPa; tasarım basınç faktörü 1.0 -> 1.5 değişince de SF sabit.
        Yani kullanıcıya "emniyet faktörü" diye kendi girdisi geri okunuyordu.

        Doğru yapı İKİ AYRI MODDUR (aynı desen bu depoda
        ``pressure_vessel.py::analyze`` içinde zaten doğru kurulmuştur;
        ASME BPVC VIII-1 UG-27 t hesabı + UG-98/MAWP mevcut-t geri hesabı):
          * ``actual_thickness is None`` -> **size**: t_req = P*r/(sigma_all)
            hesaplanır, imalat payıyla önerilir. Bu modda raporlanan emniyet
            faktörü TANIM GEREĞİ hedef SF x imalat payıdır — çıktıda
            ``safety_factor_is_tautological=True`` ile açıkça işaretlenir.
          * ``actual_thickness`` verilirse -> **verify**: gerilme KULLANICININ
            GERÇEK cidarından hesaplanır (sigma = P*r/t_gerçek veya kalın
            cidarda Lame) ve SF = sigma_y_der/sigma gerçek bir doğrulamadır;
            basınç, çap ve malzeme artık sadeleşmez.

        Ayrıca materials_db'deki ``safety_factor`` bir MALZEME ÖZELLİĞİ
        DEĞİL tasarım/otorite kararıdır; ``design_safety_factor`` argümanıyla
        çağırana taşındı (None -> geriye dönük uyum için malzeme kaydı).

        Args:
            derating: _derate_strength sonucu (None ise oda-sicakligi yield).
            wall_delta_T: Cidar boyunca termal gradyan [K] (>0 sicak ic yuz).
            actual_thickness: Kullanıcının GERÇEK cidar kalınlığı [m].
                Verilirse doğrulama modu; None ise boyutlandırma modu.
            design_safety_factor: Tasarım emniyet faktörü hedefi (çağıranın
                kararı). None -> mat_props['safety_factor'] (eski davranış).
        """

        radius = diameter / 2
        yield_strength = mat_props['yield_strength']
        safety_factor = (float(design_safety_factor)
                         if design_safety_factor is not None
                         else mat_props['safety_factor'])

        # Derate edilmis yield (varsa). Termal degerlendirme bu deger uzerinden.
        if derating is not None:
            yield_for_design = derating['derated_yield_strength']
            derated_ultimate = derating['derated_ultimate_strength']
        else:
            yield_for_design = yield_strength
            derated_ultimate = mat_props['ultimate_strength']

        # Required wall thickness (thin wall approximation)
        # t = P*r / (sigma_allow). DERATE edilmis yield kullanilir -> daha kalin
        # cidar gerekebilir (konservatif).
        allowable_stress = yield_for_design / safety_factor
        min_thickness = pressure * radius / allowable_stress

        # Önerilen kalınlık = kod minimumu + imalat/korozyon payı (bkz. modül
        # sabiti MANUFACTURING_ALLOWANCE_FACTOR).
        recommended_thickness = min_thickness * MANUFACTURING_ALLOWANCE_FACTOR

        # F003: gerilme hesabında KULLANILAN kalınlık — doğrulama modunda
        # kullanıcının gerçek cidarı, boyutlandırma modunda önerilen kalınlık.
        if actual_thickness is not None and float(actual_thickness) > 0:
            design_mode = 'verify'
            evaluated_thickness = float(actual_thickness)
        else:
            design_mode = 'size'
            evaluated_thickness = recommended_thickness

        # Ince-cidar varsayimi gecerlilik kontrolu (t/r < 0.1, yani D/t > 20)
        # -> Shigley "Mechanical Engineering Design", Roark's Formulas Ch.13.
        t_over_r = evaluated_thickness / radius if radius > 0 else float('inf')
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
        thin_pressure_hoop = pressure * radius / evaluated_thickness
        a_inner = radius                              # ic yaricap (silindir ici)
        b_outer = radius + evaluated_thickness        # dis yaricap
        if b_outer > a_inner:
            lame_peak_hoop = pressure * (b_outer**2 + a_inner**2) / (b_outer**2 - a_inner**2)
        else:
            lame_peak_hoop = thin_pressure_hoop
        if not thin_wall_valid:
            # Kalin-cidar rejimi: konservatif olarak Lame tepe degerini kullan.
            pressure_hoop_stress = max(thin_pressure_hoop, lame_peak_hoop)
        else:
            pressure_hoop_stress = thin_pressure_hoop

        longitudinal_stress = pressure * radius / (2 * evaluated_thickness)

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

        # Basınç-YALNIZ von Mises (birincil yük). Termal terim çıkarılınca
        # aynı 2B/3B form uygulanır — F026 gereği emniyet sepetinde birincil
        # yük kullanılabilsin diye ayrıca raporlanır.
        if not thin_wall_valid:
            sigma_r = -pressure
            von_mises_pressure = np.sqrt(0.5 * (
                (pressure_hoop_stress - longitudinal_stress) ** 2
                + (longitudinal_stress - sigma_r) ** 2
                + (sigma_r - pressure_hoop_stress) ** 2))
        else:
            von_mises_pressure = np.sqrt(
                pressure_hoop_stress**2
                - pressure_hoop_stress * longitudinal_stress
                + longitudinal_stress**2)
        von_mises_sf_pressure = (yield_for_design / von_mises_pressure
                                 if von_mises_pressure > 0 else float('inf'))

        # --- ASME gerilme SINIFLANDIRMASI (F026, 2026-07-25) --------------
        # Basınç hoop'u BİRİNCİL (P, yük kontrollü); termal gradyan gerilmesi
        # İKİNCİL (Q, deplasman kontrollü) gerilmedir. İkisini toplayıp AKMA
        # dayanımıyla oranlamak yanlıştır: ikincil gerilme akma üstünde
        # plastik uyumla (shakedown) kendini sınırlar, kırılma yaratmaz.
        # ÖLÇÜLDÜ (rejeneratif cidar, T_ic=800 K, T_dis=500 K, Pc=50 bar,
        # steel_4130, D=150 mm): P=70.7 MPa, Q=505.5 MPa, P+Q=576.2 MPa ->
        # eski tek kriter SF=0.556 ve status='UNSAFE' veriyordu. ASME
        # kriteri: Sm=243.3 MPa; P/Sm=0.291 (KABUL), (P+Q)/3Sm=0.789
        # (shakedown SAĞLANIYOR). Yani tamamen normal bir rejeneratif hazne
        # yanlış şekilde UNSAFE ilan ediliyordu.
        # Kaynak: ASME BPVC VIII-2 (2021) Part 5.2.2 (gerilme sınıflandırma)
        # ve 5.5.6; ASME III NB-3222.2 (3Sm shakedown kuralı).
        # NOT: termal tepe çekme DIŞ yüzeyde, Lame basınç tepesi İÇ
        # yüzeydedir — toplama konservatiftir ama eş-konumlu değildir.
        Sm = min(derated_ultimate / ASME_SM_UTS_DIVISOR,
                 yield_for_design / ASME_SM_YIELD_DIVISOR)
        primary_ratio = pressure_hoop_stress / Sm if Sm > 0 else float('inf')
        shakedown_ratio = (hoop_stress / (ASME_SHAKEDOWN_MULTIPLIER * Sm)
                           if Sm > 0 else float('inf'))

        return {
            'minimum_thickness': min_thickness * 1000,  # mm
            'recommended_thickness': recommended_thickness * 1000,  # mm
            # F003: hangi modda çalışıldı ve gerilme hangi kalınlıktan çıktı
            'design_mode': design_mode,                 # 'size' | 'verify'
            'wall_thickness_used_mm': evaluated_thickness * 1000,
            'design_safety_factor_target': safety_factor,
            'manufacturing_allowance_factor': MANUFACTURING_ALLOWANCE_FACTOR,
            # v2.6.26 — SABİT ÇIKTI BEYANI: bu çarpan bu tasarımdan
            # hesaplanmaz, modül sabitidir (structural_analysis.py:35).
            'manufacturing_allowance_factor_basis': (
                'manufacturing allowance constant (structural_analysis.py '
                'MANUFACTURING_ALLOWANCE_FACTOR): recommended thickness = '
                'minimum thickness x this factor. It is NOT computed from '
                'this design and it is NOT a safety factor - it is stock '
                'tolerance, machining and corrosion allowance taken from '
                'general tube/plate manufacturing practice (ASME BPVC VIII-1 '
                'UG-25 corrosion-allowance pattern).'),
            'safety_factor_is_tautological': bool(design_mode == 'size'),
            'safety_factor_basis': (
                'sized to allowable: SF = target_SF x manufacturing allowance '
                '(input read back, NOT an independent verification)'
                if design_mode == 'size' else
                'verified against user-supplied wall thickness'),
            # F026: ASME birincil / birincil+ikincil sınıflandırması
            'asme_Sm_MPa': Sm / 1e6,
            'asme_primary_membrane_ratio': primary_ratio,      # P/Sm  (<=1 kabul)
            'asme_shakedown_ratio': shakedown_ratio,           # (P+Q)/3Sm (<=1 kabul)
            'asme_primary_ok': bool(primary_ratio <= 1.0),
            'asme_shakedown_ok': bool(shakedown_ratio <= 1.0),
            'von_mises_safety_factor_pressure': von_mises_sf_pressure,
            'von_mises_stress_pressure': von_mises_pressure / 1e6,  # MPa
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
                                chamber_diameter: float, mat_props: Dict, nozzle_type: str,
                                derating: Optional[Dict] = None,
                                design_safety_factor: Optional[float] = None,
                                actual_throat_thickness: Optional[float] = None) -> Dict:
        """Boğaz bölgesi yapısal kontrolü (boyutlandır / doğrula).

        FİZİK DENETİMİ F027 (2026-07-25) — İKİ KUSUR GİDERİLDİ:
        (1) TAUTOLOJİ: effective_stress = SCF*P*r_t/(min_t*SCF) = allowable
            olduğundan safety_factor = yield/allowable = SF_mal her zaman.
            ÖLÇÜLDÜ: Pc 5..500 bar ve tüm malzemeler için SF = 4.0000 sabit.
            Bu bir doğrulama değil, girdinin geri okunmasıdır — hazne
            cidarıyla (F003) aynı size/verify ayrımı uygulandı.
        (2) DERATING YOK: boğaz motorun EN SICAK istasyonudur (Bartz tepe ısı
            akısı orada) ama yield ODA SICAKLIĞI değeriyle alınıyordu; aynı
            çağrıda hazne cidarı derate ediliyordu. ÖLÇÜLDÜ: T_c=3200 K'de
            hazne retention=0.537 (yield 460 -> 247 MPa) iken boğaz izin
            verilen gerilmesi 1.86 kat FAZLA gösteriliyordu. Boğaz artık aynı
            _derate_strength çıktısını kullanır.
        Kaynak: ince-cidar hoop — Sutton & Biblarz "Rocket Propulsion
        Elements" Ch. 8 / Roark's Ch. 13; derating — MMPDS / MIL-HDBK-5
        Fig. 2.3.1.1.1.

        NOT (kapsam dışı, beyan): boğaz termal gradyan gerilmesi (rejeneratif
        boğazda genellikle baskın yük) bu fonksiyonda hesaplanmaz.
        """

        throat_radius = throat_diameter / 2
        chamber_radius = chamber_diameter / 2
        yield_strength = mat_props['yield_strength']
        safety_factor = (float(design_safety_factor)
                         if design_safety_factor is not None
                         else mat_props['safety_factor'])
        if derating is not None:
            yield_for_design = derating['derated_yield_strength']
        else:
            yield_for_design = yield_strength

        # Throat section is critical (smallest diameter, highest stress)
        allowable_stress = yield_for_design / safety_factor
        min_throat_thickness = pressure * throat_radius / allowable_stress

        # Boğaz geçiş bölgesi gerilme yığılması. 2.0 (konik) / 1.5 (çan)
        # değerleri BEYAN EDİLEN tasarım kabulüdür: iç basınçlı kabuk geçiş
        # bölgesi için tipik K_t bandı (1.5-3.0) içindedir, ancak gerçek
        # geometriden (yakınsak koni açısı, boğaz fileto yarıçapı R_c/R_t)
        # türetilmemiştir — Peterson'da "konik nozul boğazı = 2.0" diye bir
        # tablo girdisi yoktur (F182). Doğrulama modunda bu katsayı SF'yi
        # doğrudan etkiler; geometriden hesaplanan K_t ile değiştirilmelidir.
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
        # F027: gerilme, DEĞERLENDİRİLEN kalınlıktan hesaplanır. Doğrulama
        # modunda bu kullanıcının gerçek boğaz cidarıdır; boyutlandırma
        # modunda önerilen (SCF paylı) kalınlıktır ve o durumda sonuç tanım
        # gereği allowable'a eşittir -> tautolojik olarak işaretlenir.
        if (actual_throat_thickness is not None
                and float(actual_throat_thickness) > 0):
            design_mode = 'verify'
            evaluated_thickness = float(actual_throat_thickness)
        else:
            design_mode = 'size'
            evaluated_thickness = required_throat_thickness

        if evaluated_thickness > 0:
            effective_stress = (stress_concentration_factor * pressure * throat_radius
                                / evaluated_thickness)
        else:
            effective_stress = float('inf')

        # Nozzle wall thickness variation
        chamber_thickness = pressure * chamber_radius / allowable_stress

        return {
            'throat_diameter': throat_diameter * 1000,  # mm
            'min_throat_thickness': min_throat_thickness * 1000,  # mm
            'required_throat_thickness': required_throat_thickness * 1000,  # mm
            'throat_thickness_used_mm': evaluated_thickness * 1000,
            'design_mode': design_mode,                 # 'size' | 'verify'
            'chamber_thickness': chamber_thickness * 1000,  # mm
            'stress_concentration_factor': stress_concentration_factor,
            'stress_concentration_basis': ('declared design assumption, not '
                                           'derived from throat fillet geometry'),
            'throat_stress': effective_stress / 1e6,  # MPa
            # F027: derate edilmiş akmaya göre (hazne cidarıyla AYNI taban)
            'safety_factor': (yield_for_design / effective_stress
                              if effective_stress > 0 else float('inf')),
            'yield_strength_used_MPa': yield_for_design / 1e6,
            'safety_factor_is_tautological': bool(design_mode == 'size'),
            'nozzle_type': nozzle_type
        }
    
    def _analyze_end_caps(self, pressure: float, diameter: float, mat_props: Dict,
                          derating: Optional[Dict] = None,
                          design_safety_factor: Optional[float] = None,
                          actual_thickness: Optional[float] = None) -> Dict:
        """Kapak (baş / enjektör tarafı) kalınlığı ve gerçek kapak gerilmesi.

        FİZİK DENETİMİ F004 (2026-07-25) — SİLİNDİR FORMÜLÜ DÜZ PLAKADAN
        KALDIRILDI. Eski kod kapak emniyet faktörünü şöyle üretiyordu:

            bolt_circle_stress = P * (D_civata/2) / t_duz
            head_safety_factor = allowable / bolt_circle_stress

        ``P*R/t`` bir SİLİNDİR ince-cidar hoop bağıntısıdır; düz dairesel
        kapağa, üstelik cıvata dairesi yarıçapıyla uygulanmasının Roark,
        Shigley veya ASME'de karşılığı YOKTUR. ÖLÇÜLDÜ (steel_4130,
        D=150 mm): gerçek kapak SF'si her basınçta 4.00 iken kod 5 bar'da
        10.28 (2.57x FAZLA), 150 bar'da 1.878, 300 bar'da 1.328 (3.01x AZ —
        tehlikeli yön) veriyordu; sqrt(allowable/P) gibi ölçekleniyordu.
        Daha kötüsü Pc >= 50 bar'da bu uydurma sayı minimum_safety_factor'ü
        yönetiyor, Pc >= 150 bar'da tüm motoru UNSAFE ilan ediyordu.

        Doğrusu, kapağın KENDİ eğilme/membran gerilmesidir:
          * Düz dairesel kapak (üniform basınç, kenar basit mesnetli):
                sigma_max = 3*P*a^2*(3+nu) / (8*t^2)
            Kaynak: Roark's Formulas for Stress and Strain, Tablo 11.2
            (uniform yüklü dairesel plaka). Bu kalınlık ASME BPVC VIII-1
            UG-34 cıvatalı düz kapak formu t = d*sqrt(C*P/(S*E)), C=0.30 ile
            %1 içinde örtüşür (çapraz kontrol olarak da raporlanır).
          * 2:1 elipsoidal (dished) kapak: ASME UG-32(d) denkleminin tersi
                sigma = P*(D/t + 0.2) / (2*E)
        Emniyet faktörü ÖNERİLEN kapak tipinin gerilmesinden ve DİĞER
        istasyonlarla AYNI referans dayanımdan (derate edilmiş akma)
        hesaplanır — eski sürüm allowable (=yield/SF) tabanlıydı, bu yüzden
        emniyet sepetinde tanım gereği SF_mal kat daha küçük çıkıp min()'i
        neredeyse her zaman kazanıyordu (bulgu F073).

        Args:
            derating: _derate_strength sonucu (None -> oda sıcaklığı).
            design_safety_factor: tasarım SF hedefi (None -> malzeme kaydı).
            actual_thickness: gerçek kapak kalınlığı [m]; verilirse doğrulama
                modu (F003 ile aynı size/verify ayrımı).
        """

        radius = diameter / 2
        yield_strength = mat_props['yield_strength']
        safety_factor = (float(design_safety_factor)
                         if design_safety_factor is not None
                         else mat_props['safety_factor'])
        if derating is not None:
            yield_for_design = derating['derated_yield_strength']
        else:
            yield_for_design = yield_strength

        poisson_ratio = mat_props['poisson_ratio']
        allowable_stress = yield_for_design / safety_factor

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

        # ASME BPVC VIII-1 UG-34 çapraz kontrolü (cıvatalı düz kapak):
        #     t = d * sqrt(C*P/(S*E)),  C = 0.30
        # İkinci terim (1.9*W*h_G/(S*E*d^3), cıvata momenti) BURADA YOKTUR:
        # flanş cıvata yükü W ve conta kolu h_G bu fonksiyonun girdisi değil.
        # Terim atlandığı için UG-34 değeri gerçek cıvatalı kapaktan İNCE
        # çıkar; bu yüzden yalnız çapraz kontrol olarak raporlanır, kalınlık
        # önerisi Roark plaka eğilmesinden verilir (ikisi %1 içinde örtüşür).
        UG34_C_BOLTED_FLAT = 0.30
        ug34_flat_thickness = diameter * np.sqrt(
            UG34_C_BOLTED_FLAT * pressure / (allowable_stress * joint_efficiency))

        recommended_type = ('dished' if dished_head_thickness < flat_head_thickness
                            else 'flat')

        # Değerlendirilen kapak kalınlığı: doğrulama modunda kullanıcının
        # gerçek kapağı, boyutlandırma modunda önerilen tipin kalınlığı.
        sized_thickness = (dished_head_thickness if recommended_type == 'dished'
                           else flat_head_thickness)
        if actual_thickness is not None and float(actual_thickness) > 0:
            design_mode = 'verify'
            evaluated_thickness = float(actual_thickness)
        else:
            design_mode = 'size'
            evaluated_thickness = sized_thickness

        # GERÇEK kapak gerilmesi (önerilen tipe göre):
        if recommended_type == 'flat':
            # Roark Tablo 11.2 — üniform yüklü dairesel plaka, basit mesnet:
            #     sigma_max = 3*P*a^2*(3+nu)/(8*t^2)
            head_stress = (3.0 * pressure * radius**2 * (3.0 + poisson_ratio)
                           / (8.0 * evaluated_thickness**2))
            stress_model = ('flat circular plate bending, simply supported '
                            '(Roark Table 11.2)')
        else:
            # ASME UG-32(d) 2:1 elipsoidal başlık denkleminin tersi:
            #     t = P*D/(2SE - 0.2P)  ->  sigma = P*(D/t + 0.2)/(2E)
            head_stress = (pressure * (diameter / evaluated_thickness + 0.2)
                           / (2.0 * joint_efficiency))
            stress_model = ('2:1 ellipsoidal head membrane, inverse of '
                            'ASME VIII-1 UG-32(d)')

        # Bolt circle geometrisi (yalnız yerleşim bilgisi). Eski sürümdeki
        # 'bolt_circle_stress' bir SİLİNDİR hoop formülüydü ve kapak emniyet
        # faktörünü yönetiyordu — kaldırıldı; alan geriye dönük uyumluluk
        # için kapağın GERÇEK gerilmesiyle doldurulur.
        bolt_circle_diameter = diameter + 0.05  # 50 mm larger than chamber

        head_safety_factor = (yield_for_design / head_stress
                              if head_stress > 0 else float('inf'))

        return {
            'flat_head_thickness': flat_head_thickness * 1000,  # mm
            'dished_head_thickness': dished_head_thickness * 1000,  # mm
            'asme_ug34_flat_head_thickness': ug34_flat_thickness * 1000,  # mm
            'recommended_type': recommended_type,
            'design_mode': design_mode,                    # 'size' | 'verify'
            'head_thickness_used_mm': evaluated_thickness * 1000,
            'bolt_circle_diameter': bolt_circle_diameter * 1000,  # mm
            'head_stress': head_stress / 1e6,              # MPa (GERÇEK kapak gerilmesi)
            # Geriye dönük alan adı; artık silindir hoop'u DEĞİL, kapağın
            # kendi gerilmesi (bkz. F004).
            'bolt_circle_stress': head_stress / 1e6,       # MPa
            'head_stress_model': stress_model,
            'head_safety_factor': head_safety_factor,
            'yield_strength_used_MPa': yield_for_design / 1e6,
            'safety_factor_is_tautological': bool(design_mode == 'size'),
        }
    
    #: Kapak cıvatalarının varsayılan mukavemet sınıfı. ISO 898-1:2013
    #: sınıflarından 8.8 en yaygın makine cıvatasıdır; kullanıcı/çağıran
    #: sınıfı geçerse o kullanılır. Bu bir kalibrasyon sabiti DEĞİL, beyan
    #: edilen varsayılan malzeme seçimidir ve çıktıda adıyla raporlanır.
    _DEFAULT_BOLT_PROPERTY_CLASS = '8.8'

    def _analyze_fasteners(self, pressure: float, diameter: float,
                           mat_props: Dict,
                           design_safety_factor: Optional[float] = None,
                           bolt_property_class: Optional[str] = None) -> Dict:
        """Kapak cıvatalarının statik çekme boyutlandırması.

        v2.6.26 — İKİ KAYNAKSIZ SABİT KALDIRILDI:

        (1) ``bolt_allowable_stress = 400 MPa``. Kodun kendi yorumu bu değerin
            "LİTERATÜR KAYNAĞI YOKTUR" diye beyan ediyordu ve aynı yorum
            çözümü de gösteriyordu: sınıf bazlı proof gerilmesi ``S_p``
            depoda ZATEN var (``hrma/analysis/bolted_joint._bolt_class_props``,
            ISO 898-1:2013 Table 3). Cıvata izin verilen çekme gerilmesi
            sınıfa göre 400 MPa ile 970 MPa arasında değişir; tek sabit
            kullanmak gerekli cıvata çapını yanlış boyutlandırıyordu.
            Artık izin verilen gerilme = S_p (proof stress) ve hangi sınıftan
            geldiği çıktıda kaynağıyla yazılır.

        (2) ``bolt_safety_factor = 4.0``. Kullanıcının 'Safety Factor' girdisi
            hazne cidarına uygulanırken cıvataya HİÇ ulaşmıyordu — ÖLÇÜLDÜ:
            safety_factor=2.0 ile bu alan 4.0 kaldı. Artık tasarım yükü
            kullanıcının katsayısıyla çarpılır; katsayı verilmezse beyan
            edilen 4.0 varsayılanı korunur.

        SINIR (beyan): burada YALNIZ statik çekme boyutlandırması yapılır.
        Ön-yüklü bağlantıda cıvata yükü F_i + C·P'dir ve asıl kriter
        AYRILMA'dır; o model aynı depoda ``bolted_joint.py``dedir (Shigley
        Eq. 8-24...8-30) ve sıkma boyu bu fonksiyonun girdisi olmadığı için
        buradan çağrılamaz. Uyarı çıktıda korunur.

        Args:
            design_safety_factor: tasarım emniyet katsayısı (None -> 4.0).
            bolt_property_class: '8.8' | '10.9' | '12.9' | 'A2-70'
                (None -> _DEFAULT_BOLT_PROPERTY_CLASS).
        """

        # Total force on end cap
        total_force = pressure * np.pi * (diameter/2)**2  # N
        
        # Assume 8-12 bolts depending on diameter
        if diameter < 0.1:
            num_bolts = 6
        elif diameter < 0.2:
            num_bolts = 8
        else:
            num_bolts = 12
        
        # F072 (2026-07-25) — ETİKET/BİRİM YANILTICISI GİDERİLDİ.
        # Eski sürüm 'force_per_bolt' adıyla TASARIM yükünü (gerçek yükün 4
        # katı) döndürüyordu; UI bunu "cıvata başına" diye gösteriyordu.
        # ÖLÇÜLDÜ (P_design=90 bar, D=150 mm): total=159.0 kN, raporlanan
        # force_per_bolt=79.52 kN, GERÇEK cıvata başına dış yük 19.88 kN
        # (4.00x şişirilmiş etiket). Artık ikisi ayrı alan.
        # v2.6.26: emniyet katsayısı kullanıcının tasarım katsayısıdır;
        # verilmezse eski beyan edilen 4.0 varsayılanı korunur (bkz. docstring).
        bolt_safety_factor = (float(design_safety_factor)
                              if design_safety_factor is not None
                              else _BOLT_SAFETY_FACTOR_DEFAULT)
        bolt_safety_factor_source = ('design input (safety factor)'
                                     if design_safety_factor is not None
                                     else 'declared default (no user value)')
        force_per_bolt = total_force / num_bolts              # GERÇEK dış yük
        design_force_per_bolt = force_per_bolt * bolt_safety_factor

        # Bolt sizing (assume steel bolts, 400 MPa allowable stress).
        # DUZELTME (2026-07-16): Civata cekme kapasitesi NOMINAL kesitten degil,
        # dis dibindeki GERILME ALANI A_t uzerinden tasinir. ISO 898-1 / Shigley
        # Tablo 8-1: A_t ~ 0.75*(pi/4*d_nom^2) (or. M10: A_t=58 mm^2 vs
        # pi/4*10^2=78.5, oran ~0.74). Eski kod gerekli alani dogrudan tam-dolu
        # daireye (pi/4*d^2) ceviriyordu -> civatayi sqrt(0.75)~0.87 kat KUCUK
        # seciyordu (non-konservatif). Dogrusu: gerekli A_t'yi guvenli nominal
        # capa cevir -> A_nom = A_t / 0.75.
        #
        # v2.6.26: izin verilen gerilme artık ISO 898-1:2013 Table 3 PROOF
        # gerilmesidir (bolted_joint._bolt_class_props — depodaki tek cıvata
        # mukavemet kaynağı). 8.8 sınıfında S_p, d <= 16 mm için 580 MPa,
        # d > 16 mm için 600 MPa'dır; çap çözümün kendi sonucu olduğu için
        # küçük sabit-nokta yinelemesiyle kapatılır.
        THREAD_STRESS_AREA_RATIO = 0.75  # A_t / (pi/4*d_nom^2), ISO 898-1 yaklasik
        bolt_class = str(bolt_property_class
                         or self._DEFAULT_BOLT_PROPERTY_CLASS)
        try:
            bolt_props = _bolt_class_props(bolt_class, 16.0)
        except ValueError:
            bolt_class = self._DEFAULT_BOLT_PROPERTY_CLASS
            bolt_props = _bolt_class_props(bolt_class, 16.0)
        for _ in range(3):
            bolt_allowable_stress = float(bolt_props['S_p'])  # Pa (proof)
            required_stress_area = design_force_per_bolt / bolt_allowable_stress
            required_nominal_area = required_stress_area / THREAD_STRESS_AREA_RATIO
            required_bolt_diameter = 2 * np.sqrt(required_nominal_area / np.pi)
            next_props = _bolt_class_props(bolt_class,
                                           required_bolt_diameter * 1000.0)
            if next_props['S_p'] == bolt_props['S_p']:
                break
            bolt_props = next_props

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
            # F072: artık GERÇEK cıvata başına dış yük (eski değer 4x fazlaydı)
            'force_per_bolt': force_per_bolt / 1000,  # kN
            'design_force_per_bolt_N': design_force_per_bolt,  # N (SF'li)
            'external_force_per_bolt_N': force_per_bolt,       # N (gerçek)
            'required_bolt_diameter': required_bolt_diameter * 1000,  # mm
            'recommended_bolt_size': f"M{int(recommended_bolt_size*1000)}",
            'bolt_circle_radius': bolt_circle_radius * 1000,  # mm
            'bolt_spacing': 2 * np.pi * bolt_circle_radius / num_bolts * 1000,  # mm
            'bolt_safety_factor': bolt_safety_factor,
            'bolt_safety_factor_source': bolt_safety_factor_source,
            'bolt_allowable_stress_MPa': bolt_allowable_stress / 1e6,
            # v2.6.26 dürüstlük alanları: izin verilen gerilmenin hangi cıvata
            # sınıfından ve hangi standarttan geldiği çıktıda taşınır.
            'bolt_property_class': bolt_class,
            'bolt_allowable_stress_basis': bolt_props['source'],
            'sizing_basis': ('static tensile sizing only: F_design = SF * P/n '
                             'over thread stress area, allowable = ISO 898-1 '
                             'proof stress S_p; preload and separation are '
                             'NOT modelled here'),
            'warning': bolt_warning,
            # ÖN-YÜK FİZİĞİ YOK: ön-yüklü bağlantıda cıvata yükü F_i + C*P'dir,
            # SF*P/n değil; asıl kritik kriter AYRILMA (F_i/(P(1-C))) burada
            # hiç kontrol edilmez. Doğru model aynı depoda
            # hrma/analysis/bolted_joint.py'dedir (Shigley Eq. 8-24...8-30);
            # sıkma boyu (grip length) ve cıvata sınıfı bu fonksiyonun girdisi
            # olmadığı için buradan otomatik çağrılamaz — kullanıcı yönlendirilir.
            'warnings': [_mk_warning(
                'warn.structural.fastener_preload_not_modeled', 'warning',
                module='bolted_joint')],
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
                # v2.6.2 fizik denetimi, bulgu F181: f SABİT 0.9 alınıyordu.
                # Shigley Fig. 6-18'de f, S_ut'ye BAĞLIDIR ve yüksek dayanımlı
                # malzemelerde belirgin biçimde düşer. f'in fazla alınması
                # 10^3 çevrimdeki gerilme çapasını yükseltir, dolayısıyla
                # sonlu ömrü FAZLA gösterir — KONSERVATİF OLMAYAN yön.
                # Bu kod tabanında steel_4130 (S_u=730 MPa), inconel_718 ve
                # titanyum alaşımları zarfın dışındaydı.
                # Kaynak: Shigley's Mechanical Engineering Design 10. baskı,
                # Fig. 6-18 (f–S_ut eğrisi), Eq. 6-14/6-15 (Basquin a, b).
                f_frac = _shigley_fatigue_strength_fraction(S_u)
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
            # v2.6.26 — 'estimated_cycles' ARTIK TAHMİNDİR.
            # Bu alan tasarım GİRDİSİNİ (design_cycles) geri döndürüyordu:
            # 'tahmini çevrim' adını taşıyan bir alan hiçbir bilgi taşımıyor,
            # kullanıcı ise bunu bir ömür tahmini sanıyordu (aynı sözlükte
            # 'design_cycles' zaten aynı sayıyı veriyor). Artık hesaplanan
            # ömürle (Basquin/Goodman çözümü) aynı değeri taşır; tasarım
            # hedefi 'design_cycles' alanında durur.
            'estimated_cycles': estimated_life,  # çevrim | 'Infinite' (hesap)
            'estimated_cycles_basis': (
                'predicted life for the computed stress state '
                '(Goodman + Basquin); the design target is design_cycles'),
            'estimated_life': estimated_life,    # çevrim sayısı | 'Infinite'
            'fatigue_status': fatigue_status,
            # Yeni alanlar (Dalga 3)
            'max_stress': sigma_max_pa / 1e6,    # MPa (σ_max)
            'mean_stress': sigma_m / 1e6,        # MPa (σ_m = σ_max/2)
            'stress_ratio_R': 0.0,               # basınç çevrimi 0→P→0
            # v2.6.26 — SABİT ÇIKTI BEYANI: R tanım gereği sabittir, çünkü
            # çevrim modeli 0→P→0 seçilmiştir (aşağıdaki 'assumptions').
            'stress_ratio_R_basis': (
                'stress ratio R = sigma_min/sigma_max is fixed at zero BY '
                'THE CYCLE MODEL, not computed: every firing is treated as '
                'one full 0 -> P -> 0 pressure cycle, so the minimum stress '
                'is zero. If your duty cycle keeps the chamber pressurised '
                'between firings (or preloads it), R is not zero and this '
                'Goodman evaluation does not apply.'),
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

        # v2.6.26 — KÜTLE DEĞERLENDİRİLEN CİDARDAN HESAPLANIR.
        # Burada `recommended_thickness` kullanılıyordu: kullanıcı 5 mm cidar
        # girse bile kütle, modülün ÖNERDİĞİ 15,9 mm'den hesaplanıyordu
        # (ölçüldü: 230,7 kg yerine 67,9 kg olmalıydı). Doğrulama modunda
        # kullanıcının tasarımı geçerlidir; boyutlandırma modunda iki değer
        # zaten aynıdır. Aynı hata burkulma kontrolünde de vardı ve bu
        # sürümde düzeltildi — kütle kalemi atlanmıştı.
        chamber_thickness = (
            chamber_analysis.get('wall_thickness_used_mm')
            or chamber_analysis['recommended_thickness']) / 1000  # m
        chamber_diameter = chamber_analysis['diameter'] / 1000  # m
        chamber_length = chamber_analysis['length'] / 1000  # m

        chamber_volume = np.pi * ((chamber_diameter/2 + chamber_thickness)**2 - (chamber_diameter/2)**2) * chamber_length
        chamber_weight = chamber_volume * density

        # Lüle kütlesi: kamara kütlesinin %30'u kabul edilir. Bu bir GEOMETRİ
        # HESABI DEĞİL, mühendislik başparmak kuralıdır; lülenin kendi
        # malzemesi (grafit 1800 vs çelik 7850 kg/m³) burada hiç görünmez.
        # Çıktıda 'nozzle_weight_basis' ile AÇIKÇA beyan edilir ki kullanıcı
        # bunu hesaplanmış bir sayı sanmasın. Gerçek lüle kütlesi
        # nozzle_design modülünün geometri+malzeme çözümünden gelir.
        nozzle_weight = chamber_weight * 0.3
        
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
            'wall_thickness_used_mm': chamber_thickness * 1000,
            'chamber_weight_basis': (
                'cylindrical shell volume x material density, using the '
                'evaluated wall thickness'),
            'nozzle_weight_basis': (
                'ESTIMATE: 30% of chamber weight (engineering rule of thumb, '
                'not a geometry calculation; the nozzle material is not '
                'reflected here)'),
            'weight_breakdown': {
                'chamber_percent': chamber_weight / total_weight * 100,
                'nozzle_percent': nozzle_weight / total_weight * 100,
                'end_caps_percent': end_caps_weight / total_weight * 100
            }
        }
    
    def _analyze_safety_factors(self, chamber_analysis: Dict, nozzle_analysis: Dict,
                              end_cap_analysis: Dict, mat_props: Dict,
                              buckling_analysis: Optional[Dict] = None,
                              wall_temperature_K: Optional[float] = None,
                              peak_wall_temperature_K: Optional[float] = None) -> Dict:
        """Analyze overall safety factors.

        DENETIM DUZELTMESI (2026-06): Burkulma (buckling) emniyet faktoru de
        minimum SF hesabina dahil edilir. chamber_analysis['hoop_safety_factor']
        artik TERMAL+BASINC toplam gerilmeye ve DERATE edilmis yield'e gore
        hesaplanmis olarak gelir; dolayisiyla minimum SF gercekci-konservatif olur.

        FIZIK DENETIMI F074 (2026-07-25) — IKI FARKLI SICAKLIK, IKI FARKLI AMAC.
        Eski surum servis-sinir kontrolunu ``wall_temperature_K`` ile, yani
        YONETEN SENARYONUN DERATING SICAKLIGI ile yapiyordu. 'cooled_gradient'
        senaryosu yonettiginde bu deger ORTALAMA cidar sicakligidir
        (0.5*(T_ic + T_dis)); oysa servis sinirinin asilmasi IC (sicak) yuzde
        olur. Dayanim derating'i icin kesit ortalamasi makul (tasima
        kapasitesini o belirler), ancak SERVIS SINIRI / yumusama / surunme
        kontrolu TEPE metal sicakliginda yapilmalidir.
        Kaynak: MMPDS / malzeme ureticisi kisa-sureli maruziyet sinirlari
        (tepe metal sicakligina uygulanir).
        OLCULDU: T_sicak=860 K, T_soguk=560 K, steel_4130 (servis siniri 811 K)
        -> eski kod T=710 K, oran 0.8755, exceeds=False; tepe tabanli dogru
        deger 860/811 = 1.0604 (>1 -> UNSAFE) ve exceeds=True.

        Args:
            wall_temperature_K: dayanim derating'inin yapildigi sicaklik
                (yoneten senaryonun kesit sicakligi) — raporlanir.
            peak_wall_temperature_K: TEPE (ic yuz) cidar sicakligi — servis
                siniri karsilastirmasi bundan yapilir. Verilmezse geriye donuk
                davranis icin wall_temperature_K'ye duser.
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

        # SICAKLIK MARJI (v2.5.2): gerilme emniyet faktoru tek basina
        # yeterli degil. Sogutmasiz ince metal cidar kesit boyunca neredeyse
        # IZOTERMALDIR (bkz. _estimate_wall_delta_T), yani termal gradyan
        # gerilmesi kucuk kalir ve SF yuksek cikar; asil tehlike cidarin
        # butun olarak malzeme servis sinirina yaklasmasidir (yumusama,
        # surunme, ani mukavemet kaybi). Onceki surumler bu tehlikeyi
        # fiziksel olmayan bir gradyan varsayimiyla dolayli isaret ediyordu;
        # simdi dogrudan sicaklik marjindan degerlendirilir.
        T_derate = wall_temperature_K or chamber_analysis.get('wall_temperature_K')
        # F074: servis siniri TEPE (ic yuz) sicaklikta sinanir.
        T_peak = (peak_wall_temperature_K
                  or chamber_analysis.get('wall_temperature_inner_K')
                  or T_derate)
        T_service = mat_props.get('max_service_temp')
        thermal_margin_ratio = None
        exceeds_service_temp_peak = False
        if T_peak and T_service:
            thermal_margin_ratio = float(T_peak) / float(T_service)
            exceeds_service_temp_peak = bool(float(T_peak) > float(T_service))
            severity = None
            if thermal_margin_ratio >= 1.0:
                severity = ('UNSAFE', 'HIGH')
            elif thermal_margin_ratio >= 0.85:
                severity = ('MARGINAL', 'MEDIUM')
            elif thermal_margin_ratio >= 0.70:
                severity = ('ACCEPTABLE', 'LOW')
            if severity is not None:
                rank = {'SAFE': 0, 'ACCEPTABLE': 1, 'MARGINAL': 2, 'UNSAFE': 3}
                if rank[severity[0]] > rank[status]:
                    status, risk_level = severity

        # UNSAFE durumunda hangi yükün domine ettiğini açıkla (Dalga 0):
        # termal gerilme basınç gerilmesini aşıyorsa sorun soğutma/malzeme
        # kaynaklıdır, cidar kalınlaştırmak tek başına çözmez.
        explanation = ''
        if status == 'UNSAFE':
            thermal = chamber_analysis.get('thermal_hoop_stress', 0.0)
            pressure = chamber_analysis.get('pressure_hoop_stress', 0.0)
            explanation = ('thermal-dominated' if thermal > pressure
                           else 'pressure-dominated')

        # Öneriler artık {code, params, severity} kaydı olarak döner (D-track):
        # sabit İngilizce metin sızmasını önler, frontend TF() ile çevirir.
        recommendations = []
        if min_safety_factor < 3.0:
            recommendations.append(_mk_warning(
                'warn.structural.increase_wall_thickness', 'warning'))
            recommendations.append(_mk_warning(
                'warn.structural.higher_strength_material', 'warning'))
        if chamber_analysis['hoop_safety_factor'] < 3.0:
            recommendations.append(_mk_warning(
                'warn.structural.increase_chamber_wall', 'warning'))
        if nozzle_analysis['safety_factor'] < 3.0:
            recommendations.append(_mk_warning(
                'warn.structural.increase_nozzle_throat', 'warning'))
        # YENI uyarilar (termal + burkulma + ince-cidar)
        if chamber_analysis.get('thermal_hoop_stress', 0.0) > chamber_analysis.get('pressure_hoop_stress', 0.0):
            recommendations.append(_mk_warning(
                'warn.structural.thermal_stress_dominates', 'warning'))
        if not chamber_analysis.get('thin_wall_valid', True):
            recommendations.append(_mk_warning(
                'warn.structural.thin_wall_invalid', 'warning'))
        if buckling_analysis is not None and buckling_analysis['axial_buckling_safety_factor'] < 2.0:
            recommendations.append(_mk_warning(
                'warn.structural.axial_buckling_risk', 'warning'))
        derate = chamber_analysis.get('yield_strength_used_MPa')
        if derate is not None and derate < mat_props['yield_strength'] / 1e6 * 0.7:
            recommendations.append(_mk_warning(
                'warn.structural.severe_derating', 'warning'))

        if thermal_margin_ratio is not None and thermal_margin_ratio >= 0.85:
            recommendations.append(_mk_warning(
                'warn.structural.thermal_margin_service_limit', 'warning'))

        return {
            'minimum_safety_factor': min_safety_factor,
            'risk_level': risk_level,
            'status': status,
            'explanation': explanation,
            'safety_factors': sf_candidates,
            # Cidar sicakligi / malzeme servis siniri. 1.0'i asmasi sicaklik
            # kaynakli yetmezlik demektir; gerilme SF'si yuksek olsa bile.
            # F074: oran TEPE (ic yuz) cidar sicakligindan hesaplanir.
            'thermal_margin_ratio': thermal_margin_ratio,
            'peak_wall_temperature_K': T_peak,
            'derating_wall_temperature_K': T_derate,
            'max_service_temperature_K': T_service,
            'exceeds_max_service_temp_peak': exceeds_service_temp_peak,
            'recommendations': recommendations
        }