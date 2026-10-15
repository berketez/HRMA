"""Referans O/F tablosu + tabloya oturtulmuş çan eğrisi tarayıcısı.

BU MODÜL BİR DENGE ÇÖZÜCÜSÜ DEĞİLDİR — künye (ÖH Z5S / P10-Z5S-B, P10B1-04)
===========================================================================
Modülün eski başlığı "Uses NASA CEA data and real-time calculations" diyordu.
ÖLÇÜLDÜ (28 Ağustos 2026, ``docs/scofield/raw/OH/Z5S/p10b/olcum_once.json``):

* ``_calculate_isp_*`` çan eğrisinin TEPESİNİ ``theoretical_optimums``
  tablosundaki sayıya KOYAR (``deviation = |O/F − tablo| / tablo``). Bu yüzden
  ``argmax`` tanım gereği tablo değerinin en yakın ızgara noktasıdır: dört
  hibrit çiftin dördünde de dönen "optimum"un tabloya uzaklığı ızgara
  adımının yarısından (0,112245) küçüktü (0,0102 / 0,0408 / 0,0469 / 0,0714).
* ``chamber_pressure`` optimumun YERİNİ hiç değiştirmiyor: Pc = 1 bar ile
  Pc = 1000 bar arasındaki fark dört çiftte de **tam 0,000000**. Verim
  çarpanı Pc'den bağımsız olduğu için basınç yalnız Isp'nin BÜYÜKLÜĞÜNÜ
  ölçekler, tepenin yerini değil.

Karar (P10B1-04): araç GERÇEK bir tarama yapmadığı için "tablo geri okuyucu"
olarak KÜNYELENİR. Ne tablo sayıları ne eğri değiştirildi; değişen, dönen
sözlüğün artık ne olduğunu SÖYLEMESİdir (``is_equilibrium_search=False``,
``optimum_of_ratio_basis``, ``chamber_pressure_affects_optimum=False``).
Gerçek denge taraması ``hrma.engines.combustion_analysis.CombustionAnalyzer``
üzerindedir ve ``/api/find-optimum-of`` ucu ONU çağırır.

TABLO KÜNYESİ (P10B1-01)
------------------------
``theoretical_optimums`` deponun İÇİNDE derlenmiş bir referans tablodur.
Eski ``get_recommendation`` cümlesi bu sayıyı "(NASA/industry standard)" diye
sunuyordu; bu atıf bu depoda SAYFA düzeyinde doğrulanmamıştır ve deponun
kendi kuralı ("doğrulayamıyorsan atfı koyma", bkz.
``hrma/analysis/acoustic_modes.py`` künye hükmü) gereği kaldırıldı. Sayılar
DEĞİŞMEDİ — değişen, dayanaksız atfın düşmesidir.
"""

import numpy as np
from typing import Dict, Optional

#: Referans tablonun ne olduğu — kullanıcıya giden her cümlede bu künye
#: taşınır. Doğrulanmamış bir kuruma atıf YAPILMAZ (P10B1-01).
REFERENCE_TABLE_BASIS = (
    'HRMA in-repository reference table of commonly quoted design O/F '
    'ratios. It is NOT a computed optimum for the requested operating '
    'point and it has not been verified page-by-page against a primary '
    'source in this repository.')

#: Referans tablodaki her çiftin AİT OLDUĞU motor sınıfı. Bu eşleme eskiden
#: yalnız yorum satırıydı; ``get_recommendation`` motor tipini hiç okumadığı
#: için (P10B1-02) hibrit, sıvı, katı ve uydurma ``'ZURAFA'`` için BİT-AYNI
#: cümle üretiliyordu (ölçüldü: beş tipin beşi de aynı dize). Yorum artık
#: VERİ: motor tipi hükme girer.
PAIR_MOTOR_CLASS = {
    # Hybrid propellants
    ('n2o', 'htpb'): 'hybrid',
    ('n2o', 'paraffin'): 'hybrid',
    ('lox', 'htpb'): 'hybrid',
    ('lox', 'paraffin'): 'hybrid',
    # Liquid propellants
    ('lox', 'lh2'): 'liquid',
    ('lox', 'rp1'): 'liquid',
    ('lox', 'methane'): 'liquid',
    ('lox', 'ch4'): 'liquid',
    ('n2o4', 'mmh'): 'liquid',
    ('n2o4', 'udmh'): 'liquid',
    # Solid propellants (effective O/F for reference)
    ('ap', 'htpb'): 'solid',
    ('ap', 'pban'): 'solid',
}

#: Tanınan motor sınıfları. Liste dışı bir tip SESSİZCE kabul edilmez
#: (fail-closed): ``get_recommendation('ZURAFA', ...)`` artık ValueError.
#:
#: ÖH D15 (1 Eyl 2026): burada ``('hybrid', 'liquid', 'solid')`` LİTERALİ
#: duruyordu ve ``tests/test_sabit_tek_kaynak.py`` bunu ikiz olarak
#: bildiriyordu — üçlünün adlandırılmış tanımı yalnız ``hrma/constants.py``
#: içinde olabilir. Ad korunur (dışa açık API: ``oor.SUPPORTED_MOTOR_TYPES``
#: test ve çağrı yerlerinde kullanılıyor), literal MERKEZE bağlanır.
#: SIRA merkezinkine geçer ('hybrid', 'solid', 'liquid'); bu ad yalnız
#: üyelik denetiminde ve hata metninin ``join``inde kullanıldığı için
#: davranış aynıdır (ölçüldü: kullanan bekçiler küme/iterasyon olarak
#: okuyor, sıraya bağlı iddia yok).
from hrma.constants import MOTOR_TYPES as _MERKEZ_MOTOR_TYPES

SUPPORTED_MOTOR_TYPES = _MERKEZ_MOTOR_TYPES

#: Tarama bandı, referans O/F'nin KATLARI olarak kurulur (P10B1-03).
#: Bunlar fiziksel eşik DEĞİL, ızgara kurma çarpanlarıdır: tek işlevleri
#: referans tepenin bandın İÇİNDE (kenarında değil) kalmasını garanti
#: etmektir. Eski sabit band ``linspace(1.0, 5.0, 50)`` referans değeri 5,0'in
#: üstünde olan çiftlerde optimumu tam bant KENARINA oturtuyordu — ölçüldü:
#: 12 çiftin 4'ünde (n2o/htpb 5,00 ⟷ tablo 7,50; n2o/paraffin 5,00 ⟷ 8,00;
#: ap/htpb 5,00 ⟷ 6,00; ap/pban 5,00 ⟷ 5,50) dönen sözlük iki çelişen sayıyı
#: yan yana taşıyordu.
SCAN_BAND_LOW_FACTOR = 0.4
SCAN_BAND_HIGH_FACTOR = 1.8
SCAN_POINTS = 50


class OptimumOFRatioFinder:
    """Referans O/F tablosu + tabloya oturtulmuş çan eğrisi.

    Bu sınıf bir DENGE ÇÖZÜCÜSÜ DEĞİLDİR; modül başlığındaki künyeye bakın.
    """

    def __init__(self):
        # Theoretical optimum O/F ratios for common propellant combinations.
        # Sınıf eşlemesi PAIR_MOTOR_CLASS'ta (yorum değil, veri).
        self.theoretical_optimums = {
            # Hybrid propellants
            ('n2o', 'htpb'): 7.5,
            ('n2o', 'paraffin'): 8.0,
            ('lox', 'htpb'): 2.3,
            ('lox', 'paraffin'): 2.5,

            # Liquid propellants
            ('lox', 'lh2'): 6.0,      # Hydrogen/LOX
            ('lox', 'rp1'): 2.77,     # RP-1/LOX (Saturn V)
            ('lox', 'methane'): 3.5,  # Methane/LOX (Raptor)
            ('lox', 'ch4'): 3.5,      # Alternative methane notation
            ('n2o4', 'mmh'): 2.1,     # Hypergolic
            ('n2o4', 'udmh'): 2.6,    # Hypergolic

            # Solid propellants (effective O/F for reference)
            ('ap', 'htpb'): 6.0,      # APCP
            ('ap', 'pban'): 5.5,      # PBAN
        }

        # 2026-07-15: Eski "polinom" katsayıları uydurmaydı ve N2O/HTPB için
        # 400 s Isp raporluyordu (gerçek teorik vakum ~250 s). Kaldırıldı;
        # yerine literatür tabanlı teorik vakum Isp tepe değerleri (Sutton,
        # Rocket Propulsion Elements, tipik CEA sonuçları) + çan eğrisi şekli
        # kullanılır. Bu araç bir TARAMA aracıdır: optimum O/F oranının YERİ
        # güvenilirdir, mutlak Isp için gerçek CEA hesabı esas alınmalıdır.
        #
        # ÖH Z5S / P10-Z5S-B DÜZELTMESİ: yukarıdaki "YERİ güvenilirdir"
        # cümlesi FAZLA İDDİALIYDI ve ölçümle çürüdü — yer tablodan GELİR,
        # ölçülmez (P10B1-04 künyesi). Sayılar değişmedi, iddia düzeltildi.
        self.peak_vac_isp = {
            ('n2o', 'htpb'): 250, ('n2o', 'paraffin'): 255,
            ('lox', 'htpb'): 330, ('lox', 'paraffin'): 335,
            ('lox', 'lh2'): 455, ('lox', 'rp1'): 355,
            ('lox', 'methane'): 365, ('lox', 'ch4'): 365,
            ('n2o4', 'mmh'): 335, ('n2o4', 'udmh'): 330,
        }
        # ÖH D16 / OH-Z5-17: bu tablo artık sıvı dalın da TEK KAYNAĞIDIR.
        # P10-Z5S-B'nin beyanlı bıraktığı ayrım (``_liquid_reference``
        # kendi tepe Isp'lerini yazıyordu: lh2 450, rp1 350, methane 380 ve
        # geri kalan her çift için sabit 320) BİRLEŞTİRİLDİ; hüküm ve
        # değişen sayıların listesi ``_liquid_reference`` docstring'inde.
        # Buradaki sayılar DEĞİŞMEDİ — sıvı dal onları okumaya başladı.

    # ------------------------------------------------------------------
    # Referans tablo erişimi — tek kapı, künyeli
    # ------------------------------------------------------------------
    def reference_optimum(self, motor_type: str, oxidizer: str,
                          fuel: str) -> Dict:
        """Referans tablo değerini KÜNYESİYLE döndür (hesaplanmış optimum DEĞİL).

        ``motor_type`` hükme GİRER (P10B1-02): tanınmayan tip fail-closed
        reddedilir, tanınan ama çiftin tablo sınıfıyla uyuşmayan tip
        ``class_matches_request=False`` ile İŞARETLENİR.

        Raises:
            ValueError: ``motor_type`` :data:`SUPPORTED_MOTOR_TYPES` dışında.
        """
        istenen = str(motor_type or '').strip().lower()
        if istenen not in SUPPORTED_MOTOR_TYPES:
            # Kullaniciya gorunur metin -> Ingilizce.
            raise ValueError(
                f"'motor_type' must be one of: "
                f"{', '.join(SUPPORTED_MOTOR_TYPES)}; got {motor_type!r}")

        key = (str(oxidizer or '').lower(), str(fuel or '').lower())
        theoretical = self.theoretical_optimums.get(key)
        tablo_sinifi = PAIR_MOTOR_CLASS.get(key)
        return {
            'motor_type': istenen,
            'oxidizer': key[0],
            'fuel': key[1],
            'available': theoretical is not None,
            'reference_of_ratio': theoretical,
            'reference_table_motor_class': tablo_sinifi,
            'class_matches_request': (tablo_sinifi == istenen
                                      if tablo_sinifi else None),
            'basis': REFERENCE_TABLE_BASIS,
            'is_equilibrium_search': False,
        }

    def _scan_band(self, reference_of: float) -> np.ndarray:
        """Referans tepeyi İÇİNE alan tarama ızgarası (P10B1-03).

        Band referans değerin katlarından kurulur; böylece tepe hiçbir zaman
        bandın kenarına düşmez ve dönen sözlük iki çelişen sayı taşımaz.
        """
        alt = max(0.1, SCAN_BAND_LOW_FACTOR * float(reference_of))
        ust = SCAN_BAND_HIGH_FACTOR * float(reference_of)
        return np.linspace(alt, ust, SCAN_POINTS)

    @staticmethod
    def _band_edge(index: int, points: int) -> bool:
        """Bulunan tepe bandın KENARINDA mı? (kenar = optimum değil)"""
        return index == 0 or index == points - 1

    def find_optimum_hybrid(self, oxidizer: str, fuel: str,
                           chamber_pressure: float = 20.0) -> Dict:
        """Hibrit için referans O/F etrafında Isp taraması.

        DİKKAT (künye): bu bir denge çözümü DEĞİLDİR. Çan eğrisinin tepesi
        referans tablo değerine KONUR, dolayısıyla dönen ``optimum_of_ratio``
        tablo değerinin en yakın ızgara noktasıdır ve ``chamber_pressure``
        onun YERİNİ değiştirmez (ölçüldü: Pc 1 ⟷ 1000 bar farkı 0,000000).
        Dönen sözlük bunu ``is_equilibrium_search`` ve
        ``chamber_pressure_affects_optimum`` alanlarıyla SÖYLER.

        Raises:
            ValueError: the propellant pair has no reference data (see
                _calculate_isp_hybrid). No silent default is produced.
        """

        # Try to get from theoretical database first
        key = (oxidizer.lower(), fuel.lower())
        theoretical = self.theoretical_optimums.get(key, None)
        if theoretical is None:
            # Bandın kendisi referans değerden türetildiği için bilinmeyen
            # çift ARTIK BANDA BİLE GİREMEZ; ret _calculate_isp_hybrid ile
            # aynı cümledir (tek ret metni).
            self._calculate_isp_hybrid(oxidizer, fuel, 1.0, chamber_pressure)

        # Search range — referans tepeyi içine alacak biçimde TÜRETİLİR
        of_range = self._scan_band(theoretical)
        isp_values = []

        # Calculate ISP for each O/F ratio
        for of_ratio in of_range:
            isp = self._calculate_isp_hybrid(oxidizer, fuel, of_ratio, chamber_pressure)
            isp_values.append(isp)

        # Find maximum
        max_idx = int(np.argmax(isp_values))
        optimum_of = of_range[max_idx]
        max_isp = isp_values[max_idx]

        # Create performance curve
        performance_curve = {
            'of_ratios': of_range.tolist(),
            'isp_values': isp_values
        }

        return {
            'optimum_of_ratio': optimum_of,
            'max_isp': max_isp,
            'theoretical_optimum': theoretical,
            'performance_curve': performance_curve,
            'oxidizer': oxidizer,
            'fuel': fuel,
            'chamber_pressure': chamber_pressure,
            # --- KÜNYE (P10B1-03 / P10B1-04) ------------------------------
            'is_equilibrium_search': False,
            'optimum_of_ratio_basis': (
                'reference-table bell curve: the efficiency peak is placed AT '
                'theoretical_optimum by construction, so this value is the '
                'grid point nearest the table entry, not a searched optimum'),
            'chamber_pressure_affects_optimum': False,
            'reference_table_basis': REFERENCE_TABLE_BASIS,
            'scan_band': [float(of_range[0]), float(of_range[-1])],
            'scan_points': int(SCAN_POINTS),
            'optimum_at_band_edge': self._band_edge(max_idx, len(of_range)),
        }

    def find_optimum_liquid(self, oxidizer: str, fuel: str,
                          chamber_pressure: float = 100.0) -> Dict:
        """Sıvı için referans O/F etrafında Isp taraması.

        Künye hibrit dalıyla AYNIDIR (tablo geri okuma). Band artık sabit
        ``1,0-5,0`` değil, referans değerin katlarından türetilir — eski
        sabit band 12 çiftin 4'ünde optimumu tam bant kenarına (5,0000)
        oturtuyor ve dönen sözlük ``theoretical_optimum`` ile çelişiyordu.
        """

        key = (oxidizer.lower(), fuel.lower())
        theoretical = self.theoretical_optimums.get(key, None)

        # Bandın merkezi, Isp eğrisinin GERÇEKTEN kullandığı referanstır —
        # tablo ile ``_liquid_reference`` ayrışırsa band yanlış yere kurulurdu.
        _, optimal_of = self._liquid_reference(oxidizer, fuel)
        of_range = self._scan_band(optimal_of)

        isp_values = []

        for of_ratio in of_range:
            isp = self._calculate_isp_liquid(oxidizer, fuel, of_ratio, chamber_pressure)
            isp_values.append(isp)

        max_idx = int(np.argmax(isp_values))
        optimum_of = of_range[max_idx]
        max_isp = isp_values[max_idx]

        return {
            'optimum_of_ratio': optimum_of,
            'max_isp': max_isp,
            'theoretical_optimum': theoretical,
            'performance_curve': {
                'of_ratios': of_range.tolist(),
                'isp_values': isp_values
            },
            'oxidizer': oxidizer,
            'fuel': fuel,
            'chamber_pressure': chamber_pressure,
            # --- KÜNYE (P10B1-03 / P10B1-04) ------------------------------
            'is_equilibrium_search': False,
            'optimum_of_ratio_basis': (
                'reference-table bell curve: the efficiency peak is placed AT '
                'the reference O/F by construction, so this value is the grid '
                'point nearest that entry, not a searched optimum'),
            'chamber_pressure_affects_optimum': False,
            'reference_table_basis': REFERENCE_TABLE_BASIS,
            'scan_band': [float(of_range[0]), float(of_range[-1])],
            'scan_points': int(SCAN_POINTS),
            'optimum_at_band_edge': self._band_edge(max_idx, len(of_range)),
            'curve_peak_of_ratio': float(optimal_of),
        }

    def _calculate_isp_hybrid(self, oxidizer: str, fuel: str,
                            of_ratio: float, chamber_pressure: float) -> float:
        """Calculate ISP for hybrid motor at given O/F ratio.

        Raises:
            ValueError: the propellant pair is not in the reference table.
                DUZELTME (v2.5.2): eski kod tabloda olmayan cift icin sessizce
                O/F=7.0 (N2O/HTPB degeri) ve 250 s tepe Isp varsayiyordu, yani
                yakit/oksitleyici secilmeden de 'optimum' uretiyordu. Sessiz
                varsayilan YASAK; cagiran taraf ya tam yanma analizini
                calistirmali ya da secimi duzeltmelidir.
        """
        # Çan eğrisi: tepe = literatür teorik vakum Isp, konum = teorik optimum
        key = (oxidizer.lower(), fuel.lower())
        theoretical = self.theoretical_optimums.get(key)
        base_isp = self.peak_vac_isp.get(key)
        if theoretical is None or base_isp is None:
            # Kullaniciya gorunur metin -> Ingilizce.
            raise ValueError(
                f"No optimum O/F data for pair {oxidizer.upper()}+{fuel.upper()}; "
                f"run full combustion analysis or verify propellant selection.")
        deviation = abs(of_ratio - theoretical) / theoretical
        efficiency = np.exp(-2 * deviation**2)

        # Basınç düzeltmesi ZAYIF olmalı: Isp'nin Pc bağımlılığı c* üzerinden
        # yüzde birkaç mertebesindedir (eski sqrt(Pc/20) 30 bar'da +%22 veriyordu)
        pressure_factor = float(np.clip((chamber_pressure / 20.0) ** 0.05, 0.92, 1.08))

        isp = base_isp * efficiency * pressure_factor
        return max(50.0, float(isp))

    def _liquid_reference(self, oxidizer: str, fuel: str):
        """Sıvı çan eğrisinin (tepe Isp, tepe O/F) çifti — TEK yerde.

        Eskiden bu seçim yalnız ``_calculate_isp_liquid``ın içindeydi;
        ``find_optimum_liquid`` bandı ondan bağımsız kuruyordu (P10B1-03'ün
        kökü). Artık band ile eğri AYNI referanstan doğar.

        ÖH D16 / OH-Z5-17 — İKİ TEPE-Isp TABLOSUNUN BİRLEŞTİRİLMESİ
        -----------------------------------------------------------
        Bu fonksiyon kendi tepe Isp sayılarını YAZIYORDU (lh2 450, rp1 350,
        methane 380, geri kalan her çift için sabit 320) ve bunlar sınıfın
        ``peak_vac_isp`` tablosuyla ÇELİŞİYORDU. Ölçüldü
        (``docs/scofield/raw/OH/D16/sivi/a1/once.json``): tabloda bulunan
        **8 çiftin 8'i** iki farklı tepe Isp taşıyordu; en büyük fark
        N2O/HTPB'de 250 ⟷ 320, yani 70 s.

        Hüküm (sessiz seçim değil, gerekçeli): TEK KAYNAK ``peak_vac_isp``
        olur. O tablo künyelidir (Sutton, *Rocket Propulsion Elements*,
        tipik CEA sonuçları — sınıfın kendi yorumunda yazılı) ve ÇİFT ile
        anahtarlanır. Buradaki sayılar ise kaynaksızdı ve YALNIZ YAKITLA
        anahtarlanıyordu, oksitleyiciyi hiç okumuyordu. Ölçülen sonucu:
        ``n2o/rp1`` (referans tablolarda YOK) sessizce 350 s / O/F 2,77
        üretiyordu, yani LOX/RP-1'in sayısı N2O için basılıyordu; uydurma
        bir oksitleyici adı bile sayı alıyordu (ölçümde 4 vaka). Çift
        anahtarına dönmek bu sessiz varsayılanı da kapatır: tanınmayan çift
        artık ``ValueError`` ile fail-closed reddedilir.

        DEĞİŞEN SAYILAR (beyanlı): tepe Isp lh2 450->455, rp1 350->355,
        methane/ch4 380->365, htpb/mmh/udmh için sabit 320 -> çiftin kendi
        tablo değeri. O/F sayıları DEĞİŞMEZ: buradaki 6,0 / 2,77 / 3,5 zaten
        ``theoretical_optimums``un LOX satırlarının kopyasıydı.

        Raises:
            ValueError: the propellant pair is not in the reference tables —
                the same no-silent-default rule as the hybrid branch
                (v2.5.2). The fuel alone is NOT enough: the oxidizer moves
                the peak.
        """
        key = (oxidizer.lower(), fuel.lower())
        theoretical = self.theoretical_optimums.get(key)
        base_isp = self.peak_vac_isp.get(key)
        if theoretical is None or base_isp is None:
            # Kullaniciya gorunur metin -> Ingilizce.
            raise ValueError(
                f"No optimum O/F data for pair "
                f"{oxidizer.upper()}+{fuel.upper()}; "
                f"run full combustion analysis or verify propellant "
                f"selection.")
        return base_isp, theoretical

    def _calculate_isp_liquid(self, oxidizer: str, fuel: str,
                            of_ratio: float, chamber_pressure: float) -> float:
        """Calculate ISP for liquid motor at given O/F ratio.

        Raises:
            ValueError: unknown fuel AND unknown propellant pair — same
                no-silent-default rule as the hybrid branch (v2.5.2).
        """
        base_isp, optimal_of = self._liquid_reference(oxidizer, fuel)

        # Calculate efficiency based on deviation from optimum
        deviation = abs(of_ratio - optimal_of) / optimal_of
        efficiency = np.exp(-3 * deviation**2)  # Sharper curve for liquids

        # Basınç düzeltmesi zayıf tutulur (Isp ~ birkaç % / Pc dekadı)
        pressure_factor = float(np.clip((chamber_pressure / 100.0) ** 0.08, 0.90, 1.08))

        isp = base_isp * efficiency * pressure_factor
        return max(100.0, float(isp))

    def get_recommendation(self, motor_type: str, oxidizer: str, fuel: str,
                           measured_of_ratio: Optional[float] = None) -> str:
        """Referans O/F cümlesi — KÜNYELİ, ve ölçülen sayıyla ÇELİŞMEZ.

        ``measured_of_ratio`` verilirse (ucun gerçek denge taramasından gelen
        sayı) cümle İKİ sayıyı da, her birinin kaynağını ve aralarındaki farkı
        söyler. Eski cümle yalnız tablo sayısını basıyor ve onu "(NASA/industry
        standard)" diye sunuyordu; aynı yanıtta ölçülen 6,8452 dururken
        kullanıcıya 7,50 gösteriliyordu (P10B1-01, ölçüldü).

        Raises:
            ValueError: ``motor_type`` tanınmıyor (P10B1-02, fail-closed).
        """
        ref = self.reference_optimum(motor_type, oxidizer, fuel)
        etiket = f"{fuel.upper()}/{oxidizer.upper()}"
        tip = ref['motor_type']

        if not ref['available']:
            temel = (f"No reference O/F value for {etiket} as a {tip} motor. "
                     f"Use the combustion analysis result for this pair.")
            if measured_of_ratio is not None:
                temel += (f" Computed optimum O/F (combustion equilibrium "
                          f"scan): {float(measured_of_ratio):.2f}.")
            return temel

        sinif_notu = ''
        if ref['class_matches_request'] is False:
            sinif_notu = (f" NOTE: this pair is listed under "
                          f"{ref['reference_table_motor_class']} motors in the "
                          f"reference table, not {tip}.")

        if measured_of_ratio is None:
            return (f"Reference O/F ratio for {etiket} ({tip}): "
                    f"{ref['reference_of_ratio']:.2f} — reference table "
                    f"value, not a computed optimum for your operating "
                    f"point.{sinif_notu}")

        olculen = float(measured_of_ratio)
        referans = float(ref['reference_of_ratio'])
        fark = olculen - referans
        yuzde = (100.0 * fark / referans) if referans else float('nan')
        return (f"Computed optimum O/F for {etiket} ({tip}): {olculen:.2f} "
                f"(combustion equilibrium scan at your chamber pressure). "
                f"Reference table value: {referans:.2f} "
                f"(difference {fark:+.2f}, {yuzde:+.1f}%). The reference "
                f"value is not computed for your operating point; the "
                f"scanned value is.{sinif_notu}")

# Global instance
of_optimizer = OptimumOFRatioFinder()
