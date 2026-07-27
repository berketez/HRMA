"""
Regression Rate Analysis Module
Hibrit roket yakıt regresyon hızı analizi ve görselleştirmesi

Marxman difüzyon-limitli regresyon TEORİSİ (Marxman & Gilbert, 9th Int.
Symp. Combustion, 1963; Sutton & Biblarz, Rocket Propulsion Elements,
9. baskı, Böl. 16) regresyon hızını yerel TOPLAM kütle akısına bağlar:

    r_dot = a_teorik · G_total^0.8 · x^-0.2

AMA: bu modülün kullandığı (a, n) çiftleri teorik değil DENEYSEL fitlerdir
ve literatürde bu fitlerin korelasyon değişkeni OKSİTLEYİCİ akısıdır
(Doran et al. AIAA 2007-5352; Zilliac & Karabeyoglu AIAA 2006-4504 Tablo 2 —
her ikisi de r = a·G_ox^n formunda yayımlanmıştır).

>>> v2.6.2 FİZİK DENETİMİ DÜZELTMESİ (bulgu F018) — VARSAYILAN 'ox' OLDU <<<
G_ox tabanlı bir fit katsayısını G_total ile beslemek ÇİFT SAYIMDIR: yakıt
akısının etkisi zaten a katsayısının içinde kalibre edilmiştir, üstüne bir de
G_fuel eklenince r_dot sistematik olarak (1+1/OF)^n kadar şişer. ÖLÇÜLDÜ
(HTPB a=3.68e-5, n=0.555, G_ox=350 kg/m²s): O/F=6'da +%9.8, O/F=2'de +%32.6,
O/F=1.5'te +%45.8. Projenin kendi doğrulama katmanı (record_adapters.py::
_run_hybrid) bu nedenle zaten flux_mode='ox' ile koşuyordu; ürün varsayılanı
şimdi onunla HİZALANDI (parafin alt kümesinde 'ox' ile medAPE %6.9 / bias
+%9.4 — DB'deki en iyi hibrit performansı).

Eski gerekçe ("G_ox-only regresyonu düşük tahmin eder, güvenli olmayan yön")
YANLIŞ TEŞHİSTİ: sapmanın kaynağı akı tabanı değil, HTPB katsayısının
kendisidir (bkz. F019 uyarısı warn.hybrid.htpb_coeff_bias). Akı tabanını
değiştirerek katsayı hatasını kapatmak, iki hatayı üst üste bindirmektir.

flux_mode='total' hâlâ seçilebilir (Marxman teorik formuna yakın davranış
istenirse) ama bu durumda çift-sayım uyarısı üretilir.

>>> v2.6.2 FİZİK DENETİMİ (bulgu F058) — YAKIT AKISI ARTIK BOY-ORTALAMASI <<<
'total' modunda G_fuel eskiden port ÇIKIŞ değeriydi (tüm grain boyunca üretilen
yakıt tek bir kesitten geçiyormuş gibi). Marxman'da G_total yereldir: baş uçta
G_fuel = 0, kuyruk uçta tam değer; boy ortalaması çıkışın YARISIDIR. Docstring
bunu "konservatif üst sınır" diye kabul ediyordu, ama sonuç (r_dot, port çapı,
yakıt debisi) kullanıcıya doğrudan SAYI olarak sunulduğu için bu konservatiflik
belirsizlik değil sistematik sapmadır. Varsayılan artık 'average'
(bkz. FUEL_FLUX_STATION_FACTORS); eski davranış fuel_flux_station='exit' ile
seçilebilir.
"""

import numpy as np
import plotly.graph_objects as go
from typing import Dict, Tuple


def _w(code: str, severity: str = "warning", **params) -> Dict:
    """i18n uyarısı: dile bağlı sabit metin YERİNE yapısal kayıt.

    Sözleşme solid_rocket_engine.py::_w ile birebir aynıdır:
    ``{"code", "params", "severity"}``; severity ∈ {critical, warning, info}.
    Kod adlandırması: ``warn.hybrid.<slug>``.
    """
    return {"code": code, "params": params, "severity": severity}
# Regresyon katsayıları TEK yerde tanımlıdır (magic-number kuralı):
# kaynak atıfları için hrma/data/propellant_database.py içindeki tabloya bakın.
from hrma.data.propellant_database import HYBRID_REGRESSION_COEFFICIENTS as _REG

# Sıvılaşan (parafin tipi) yakıtların literatür a/n katsayıları, eriyen sıvı
# tabakadan damlacık kopması (entrainment) etkisini ZATEN içerir; bu yüzden
# parafin için ek entrainment çarpanı UYGULANMAZ (çift sayım olur).
# Klasik (klasik diffüzyon-limitli, non-melting) yakıtlara — ör. HTPB —
# entrainment uygulanmaz. Tablo, hangi yakıtların sıvılaşan sınıfta olduğunu
# ve katsayılarının entrainment'i içerip içermediğini belgeler.
# Kaynak: Karabeyoglu, Altman & Cantwell, JPP 18(3) 2002 (entrainment teorisi);
# Karabeyoglu et al., JPP 20(6) 2004 (SP-1a ölçümleri — a/n entrainment dahil).
LIQUEFYING_FUELS = {
    # yakıt: korelasyon a/n entrainment etkisini içeriyor mu?
    'paraffin': {'entrainment_in_correlation': True},
}

# --- Yakıt akısının port boyunca konumu (v2.6.2 fizik denetimi, bulgu F058) ---
# Marxman'da G_total YEREL bir büyüklüktür:
#     G_total(x) = G_ox + (1/A_port) · ∫₀ˣ ρ_f·π·D·r dx'
# Baş uçta (x=0) G_fuel = 0, kuyruk uçta (x=L) tam değerdir. Sabit r kabulüyle
# integral x ile doğrusaldır, dolayısıyla BOY ORTALAMASI çıkış değerinin tam
# YARISIDIR. Bu modül tek istasyonda çalıştığı için hangi istasyonu temsil
# ettiği açıkça seçilmelidir:
#   'average' (VARSAYILAN): boy-ortalamalı akı (çarpan 0.5). Tek istasyonlu
#            model için doğru temsil budur; çıktı (r_dot, port çapı, yakıt
#            debisi) kullanıcıya doğrudan SAYI olarak sunulduğundan
#            "konservatif üst sınır" burada belirsizlik değil sistematik
#            sapmadır.
#   'exit'   : port çıkış değeri (çarpan 1.0) — eski davranış; kuyruk uçtaki
#            en yüksek yerel regresyonu görmek istendiğinde seçilir.
# Kaynak: Marxman & Gilbert, 9th Int. Symp. Combustion (1963); Sutton &
# Biblarz, Rocket Propulsion Elements 9. baskı, Böl. 16 (yerel akı tanımı);
# Chiaverini & Kuo, AIAA Progress Vol. 218 (2007), Böl. 2.
FUEL_FLUX_STATION_FACTORS = {'average': 0.5, 'exit': 1.0}
DEFAULT_FUEL_FLUX_STATION = 'average'


def _as_list(values) -> list:
    """Plotly izlerine giren diziyi düz Python listesine çevirir.

    Plotly 6.x numpy dizilerini JSON'a base64 'bdata' bloğu olarak yazar;
    uygulamada yüklü plotly.js 1.58.5 bu formatı tanımadığı için grafik
    BOŞ çizilir. Bu yardımcı, tüm figür üretimlerinde tek geçiş noktasıdır.
    """
    if isinstance(values, np.ndarray):
        return [float(v) for v in values.tolist()]
    return [float(v) for v in values]

class RegressionAnalyzer:
    """Hibrit roket yakıt regresyon analizi"""

    def __init__(self):
        # Farklı yakıt türleri için regresyon parametreleri — SI birimler:
        # r_dot [m/s] = a * (G [kg/m²·s])^n; değerler merkezi tablodan gelir.
        self.fuel_properties = {
            'htpb': {'a': _REG['htpb']['a'], 'n': _REG['htpb']['n'], 'density': 920, 'name': 'HTPB'},
            'paraffin': {'a': _REG['paraffin']['a'], 'n': _REG['paraffin']['n'], 'density': 900, 'name': 'Paraffin Wax'},
            'pe': {'a': _REG['pe']['a'], 'n': _REG['pe']['n'], 'density': 960, 'name': 'Polyethylene'},
            'pmma': {'a': _REG['pmma']['a'], 'n': _REG['pmma']['n'], 'density': 1180, 'name': 'PMMA'},
            'abs': {'a': _REG['abs']['a'], 'n': _REG['abs']['n'], 'density': 1050, 'name': 'ABS Plastic'}
        }

    @staticmethod
    def regression_rate(a: float, n: float, G_ox: float,
                        rho_f: float = None, port_diameter: float = None,
                        grain_length: float = None,
                        flux_mode: str = 'ox',
                        fuel_flux_station: str = DEFAULT_FUEL_FLUX_STATION,
                        max_iter: int = 50, tol: float = 1e-6) -> Dict:
        """Regresyon hızını tek bir port istasyonunda hesaplar.

        r_dot = a · G^n  (SI: r [m/s], G [kg/m²·s])

        flux_mode:
          'ox' (VARSAYILAN): G = G_ox. Modülün (a, n) tablosu G_ox tabanlı
                  DENEYSEL fitlerden gelir (Doran et al. AIAA 2007-5352;
                  Zilliac & Karabeyoglu AIAA 2006-4504 Tablo 2), dolayısıyla
                  katsayının kendi akı tabanıyla değerlendirilmesi TEK tutarlı
                  seçenektir. v2.6.2 fizik denetimi bulgusu F018.
          'total': G = G_ox + G_fuel (Marxman teorik formuna yakın). Yakıt
                  akısı regresyon hızına bağlı olduğundan (G_fuel = mdot_f/
                  A_port, mdot_f = rho_f·π·D·L·r_dot) sabit-nokta iterasyonu
                  yapılır: r → mdot_f → G_fuel → G_total → r ... yakınsayana
                  dek. DİKKAT: G_ox tabanlı katsayıyla birlikte kullanılırsa
                  çift sayım olur (warn.hybrid.flux_mode_double_count).
                  Kaynak: Marxman & Gilbert (1963); Sutton & Biblarz 9th ed.,
                  Böl. 16; Chiaverini & Kuo, "Fundamentals of Hybrid Rocket
                  Combustion and Propulsion", AIAA Progress Vol. 218, 2007.

        fuel_flux_station ('total' modunda anlamlıdır; bulgu F058):
          'average' (VARSAYILAN): G_fuel port BOYUNCA ortalanır (çıkış
                  değerinin yarısı). Marxman'da G_total yereldir; baş uçta
                  G_fuel=0, kuyruk uçta tam değerdir. Tek istasyonlu bu model
                  için doğru temsil boy-ortalamasıdır.
          'exit': G_fuel port ÇIKIŞ değeridir (eski davranış). Yerel en yüksek
                  regresyonu görmek istendiğinde seçilir; tasarım sayısı olarak
                  raporlanırsa r_dot'u O/F=6'da ~%4, O/F=2'de ~%11 yukarı iter.
          Bkz. FUEL_FLUX_STATION_FACTORS yorumundaki kaynaklar.

        'total' modu için rho_f, port_diameter (m) ve grain_length (m)
        zorunludur (G_fuel'in hesaplanabilmesi için). Verilmezse 'ox' moduna
        düşülür ve DÖNEN SÖZLÜKTE uyarı bildirilir (v2.6.2: bu düşüş eskiden
        tamamen sessizdi).

        Döndürür: {'r_dot' [m/s], 'G_ox', 'G_fuel', 'G_fuel_exit', 'G_total',
                   'mdot_f', 'flux_used', 'fuel_flux_station', 'iterations',
                   'converged', 'warnings'}
        'G_fuel' HESAPTA KULLANILAN akıdır (istasyon çarpanı uygulanmış);
        'G_fuel_exit' port çıkışındaki ham değerdir; 'mdot_f' ise grain'in
        TOPLAM yakıt üretimidir (istasyon seçiminden bağımsız fiziksel debi).
        """
        G_ox = max(G_ox, 1e-9)
        warns = []
        station = (fuel_flux_station or DEFAULT_FUEL_FLUX_STATION).lower()
        if station not in FUEL_FLUX_STATION_FACTORS:
            station = DEFAULT_FUEL_FLUX_STATION
        station_factor = FUEL_FLUX_STATION_FACTORS[station]

        # G_total için gerekli geometri yoksa veya 'ox' modu istendiyse:
        if flux_mode == 'ox' or rho_f is None or port_diameter is None or grain_length is None:
            if flux_mode == 'total':
                # v2.6.2: sessiz mod düşüşü YASAK — kullanıcı hangi modelin
                # koştuğunu bilmeli (Codex bulgusu: uyarı kanalı yok).
                warns.append(_w('warn.hybrid.flux_mode_downgraded', 'info'))
            r_dot = a * G_ox ** n
            return {
                'r_dot': r_dot, 'G_ox': G_ox, 'G_fuel': 0.0,
                'G_fuel_exit': 0.0, 'G_total': G_ox,
                'mdot_f': 0.0, 'flux_used': G_ox,
                'fuel_flux_station': station, 'iterations': 0,
                'converged': True, 'mode': 'ox', 'warnings': warns
            }

        # 'total' modu: katsayı tabanıyla uyuşmazlık uyarısı (F018).
        warns.append(_w('warn.hybrid.flux_mode_double_count', 'warning'))
        if station == 'exit':
            # F058: çıkış istasyonu tek bir noktayı temsil eder, grain
            # ortalamasını DEĞİL — kullanıcı hangi tanımı gördüğünü bilmeli.
            warns.append(_w('warn.hybrid.fuel_flux_exit_station', 'info'))

        A_port = np.pi * (port_diameter / 2.0) ** 2
        mdot_ox = G_ox * A_port  # kg/s (sabit; G_ox tanımından)

        # Sabit-nokta iterasyonu: r_dot(G_total) <-> G_total(r_dot)
        # Başlangıç: yalnız G_ox ile (alt sınır tahmin).
        r_dot = a * G_ox ** n
        converged = False
        it = 0
        for it in range(1, max_iter + 1):
            # Grain'in TOPLAM yakıt üretimi (fiziksel debi) ve bunun port
            # çıkışındaki akı karşılığı.
            mdot_f = rho_f * np.pi * port_diameter * grain_length * r_dot
            G_fuel_exit = mdot_f / A_port
            # v2.6.2 FİZİK DENETİMİ (F058): tek istasyonlu modelde kullanılacak
            # akı, seçilen istasyonun akısıdır. 'average' -> çıkışın yarısı.
            G_fuel = station_factor * G_fuel_exit
            G_total = G_ox + G_fuel
            r_new = a * G_total ** n
            if abs(r_new - r_dot) <= tol * max(r_new, 1e-12):
                r_dot = r_new
                converged = True
                break
            r_dot = r_new

        mdot_f = rho_f * np.pi * port_diameter * grain_length * r_dot
        G_fuel_exit = mdot_f / A_port
        G_fuel = station_factor * G_fuel_exit
        G_total = G_ox + G_fuel
        if not converged:
            # OPUS DENETİM DÜZELTMESİ (minor): sessiz yakınsamama yasak.
            # n≥0.7 egzotik yakıt + aşırı yakıt-baskın geometri 50 iterasyonu
            # aşabilir; kullanıcı son iterat kullanıldığını bilmeli.
            # v2.6.2: warnings.warn SUNUCU KONSOLUNA gidiyordu, kullanıcı hiç
            # görmüyordu; artık dönen sözlükte de yapısal kayıt var.
            warns.append(_w('warn.hybrid.regression_not_converged', 'warning',
                            max_iter=max_iter, n=round(float(n), 3),
                            fuel_flux_fraction=round(
                                float(G_fuel / max(G_total, 1e-12)), 3)))
            import warnings
            warnings.warn(
                f"Marxman G_total sabit-nokta iterasyonu {max_iter} adımda "
                f"yakınsamadı (n={n}, G_fuel/G_total="
                f"{G_fuel/max(G_total,1e-12):.3f}); son iterat kullanılıyor.",
                RuntimeWarning)
        return {
            'r_dot': r_dot, 'G_ox': G_ox, 'G_fuel': G_fuel,
            'G_fuel_exit': G_fuel_exit, 'G_total': G_total,
            'mdot_f': mdot_f, 'flux_used': G_total,
            'fuel_flux_station': station, 'iterations': it,
            'converged': converged, 'mode': 'total', 'warnings': warns
        }

    def analyze_regression_vs_time(self, motor_data: Dict) -> Dict:
        """Zamana karşı regresyon hızı analizi.

        flux_mode (motor_data anahtarı): 'ox' (VARSAYILAN — katsayı tabanıyla
        tutarlı; bkz. modül docstring / bulgu F018) veya 'total' (Marxman
        G_total = G_ox + G_fuel; çift sayım uyarısı üretir). 'total' modu için
        yakıt yoğunluğu ve grain boyu gerekir (motor_data'dan veya yakıt
        tablosundan).
        """

        # Motor parametrelerini al
        burn_time = motor_data.get('burn_time', 10.0)  # s
        mdot_ox = motor_data.get('mdot_ox', 1.0)  # kg/s
        port_initial = motor_data.get('port_diameter_initial', 0.03)  # m
        port_final = motor_data.get('port_diameter_final', 0.05)  # m
        fuel_type = motor_data.get('fuel_type', 'htpb')
        # Grain boyu: motor sonucunda VARSA doğrudan kullanılır. v2.5.2'de
        # kamara boyu artık grain + ön-yanma + art-yanma toplamıdır, yani
        # 0.8·L_kamara yaklaşımı grain'i sistematik olarak yanlış ölçekler
        # (G_fuel -> r_dot zincirini kaydırır). Yaklaşım yalnız grain boyu
        # verilmediğinde geriye uyum için kalır.
        grain_length = motor_data.get('grain_length')
        if not grain_length or grain_length <= 0:
            grain_length = motor_data.get('chamber_length', 0.3) * 0.8  # m
        # v2.6.2 (F018): varsayılan 'ox' — tablo katsayıları G_ox tabanlıdır.
        flux_mode = motor_data.get('flux_mode', 'ox')  # 'ox' | 'total' (Marxman)
        # v2.6.2 (F058): 'total' modunda yakıt akısının hangi istasyonu temsil
        # ettiği. Varsayılan boy-ortalaması; 'exit' eski davranıştır.
        fuel_flux_station = motor_data.get('fuel_flux_station',
                                           DEFAULT_FUEL_FLUX_STATION)

        # Yakıt özelliklerini al
        fuel_props = self.fuel_properties.get(fuel_type, self.fuel_properties['htpb'])
        a = motor_data.get('regression_a', fuel_props['a'])
        n = motor_data.get('regression_n', fuel_props['n'])
        rho_f = motor_data.get('fuel_density', fuel_props['density'])  # kg/m³

        # Zaman dizisi. OPUS DENETİM DÜZELTMESİ (minor): dt, linspace grid
        # aralığıyla aynı olmalı (eski tb/steps, tb/(steps-1) griddle %1
        # zamanlama kayması yaratıyordu).
        time_steps = 100
        time_array = np.linspace(0, burn_time, time_steps)

        # Her zaman adımı için port çapı ve regresyon hızı hesapla
        port_radius = port_initial / 2  # m
        regression_rates = []
        port_diameters = []
        oxidizer_flux = []
        total_flux = []

        dt = burn_time / (time_steps - 1)
        run_warnings = []

        for i_step, t in enumerate(time_array):
            # Port alanı ve oksitleyici akış yoğunluğu
            port_area = np.pi * port_radius**2  # m²
            G_ox = mdot_ox / port_area  # kg/m²/s

            # Marxman G_total regresyonu (varsayılan) — iteratif kapanış.
            reg = self.regression_rate(
                a, n, G_ox,
                rho_f=rho_f, port_diameter=2 * port_radius,
                grain_length=grain_length, flux_mode=flux_mode,
                fuel_flux_station=fuel_flux_station
            )
            r_dot = reg['r_dot']  # m/s
            for w in reg.get('warnings', []):
                if w not in run_warnings:
                    run_warnings.append(w)

            # Sonuçları kaydet
            regression_rates.append(r_dot * 1000)  # mm/s'ye çevir
            port_diameters.append(port_radius * 2 * 1000)  # mm'ye çevir
            oxidizer_flux.append(G_ox)
            total_flux.append(reg['G_total'])

            # Port yarıçapını güncelle.
            # v2.6.2 FİZİK DENETİMİ (F158): eski koşul `t < burn_time - dt`
            # kayan-nokta eşitliği yüzünden SON İKİ noktayı özdeş bırakıyordu
            # (100 noktalı ızgarada 99 değil 98 güncelleme). İNDEKS TABANLI
            # koşul ızgarayla birebir tutarlıdır. ÖLÇÜLDÜ (mdot_ox=0.7 kg/s,
            # D_i=50 mm, t_b=10 s, HTPB): D_final 66.119 -> 66.239 mm; büyüme
            # payında %0.74 eksik hesap ortadan kalktı (referans: 100 000
            # adımlı integrasyon 66.239 mm).
            if i_step < time_steps - 1:
                port_radius += r_dot * dt

        return {
            'time': time_array.tolist(),
            'regression_rate': regression_rates,
            'port_diameter': port_diameters,
            'oxidizer_flux': oxidizer_flux,
            'total_flux': total_flux,
            'fuel_type': fuel_type,
            'fuel_name': fuel_props['name'],
            'flux_mode': flux_mode,
            'fuel_flux_station': fuel_flux_station,
            'parameters': {'a': a, 'n': n},
            # v2.6.2: uyarılar kullanıcıya ULAŞAN kanaldan da dönüyor
            # (eskiden yalnız sunucu konsoluna gidiyordu).
            'warnings': run_warnings,
        }
    
    def create_regression_plot(self, regression_data: Dict) -> str:
        """Regresyon hızı grafiği (Plotly JSON).

        NOT (v2.5.2): eksen dizileri _as_list ile PYTHON listesine cevrilir.
        Plotly 6.x, numpy dizilerini JSON'a base64 'bdata' bloklari olarak
        yazar; uygulamanin yukledigi plotly.js 1.58.5 bu formati tanimadigi
        icin grafik BOS cizilir. Ayrica sabit width kaldirildi — kap
        genisligine gore responsive cizilsin.

        v2.5.5: seri ve eksen renkleri merkezi PALETTE'e hizalandi (koyu
        temada 'red'/'blue'/'green' CSS adlari tutarsizdi); JSON cikisi
        _fig_json kapisindan gecer (bdata korumasi tek merkezden).
        """
        # Tembel import: modul yukleme sirasinda dongusel bagimlilik riski
        # olmasin (engines -> analysis -> visualization zinciri).
        from hrma.visualization.visualization import PALETTE, _fig_json

        fig = go.Figure()

        time_axis = _as_list(regression_data['time'])

        # Seri renkleri: kirmizi-ish/mavi-ish/yesil-ish anlam korunarak
        # paletin koyu-tema-guvenli tonlarina esleme.
        col_reg = PALETTE[3]    # regresyon hizi (#ff5d73)
        col_port = PALETTE[6]   # port capi (#7cc4ff)
        col_flux = PALETTE[2]   # oksitleyici akisi (#2dd4a8)

        # Regression rate vs time
        fig.add_trace(go.Scatter(
            x=time_axis,
            y=_as_list(regression_data['regression_rate']),
            mode='lines',
            name='Regression Rate',
            line=dict(color=col_reg, width=3),
            hovertemplate='Time: %{x:.1f} s<br>Regression Rate: %{y:.3f} mm/s<extra></extra>'
        ))

        # Port diameter on the secondary Y axis
        fig.add_trace(go.Scatter(
            x=time_axis,
            y=_as_list(regression_data['port_diameter']),
            mode='lines',
            name='Port Diameter',
            line=dict(color=col_port, width=3, dash='dash'),
            yaxis='y2',
            hovertemplate='Time: %{x:.1f} s<br>Port Diameter: %{y:.1f} mm<extra></extra>'
        ))

        # Oxidizer mass flux
        fig.add_trace(go.Scatter(
            x=time_axis,
            y=_as_list(regression_data['oxidizer_flux']),
            mode='lines',
            name='Oxidizer Mass Flux',
            line=dict(color=col_flux, width=2),
            yaxis='y3',
            visible='legendonly',
            hovertemplate='Time: %{x:.1f} s<br>G_ox: %{y:.0f} kg/m²/s<extra></extra>'
        ))

        # Layout
        fig.update_layout(
            title=dict(
                text=f'{regression_data["fuel_name"]} Regression Analysis<br>'
                     f'<sub>a = {regression_data["parameters"]["a"]:.4f}, n = {regression_data["parameters"]["n"]:.2f}</sub>',
                x=0.5,
                font=dict(size=16)
            ),
            xaxis=dict(
                title='Time (s)',
                showgrid=True,
                gridcolor='rgba(128,128,128,0.2)'
            ),
            # Eksen basligi/tick renkleri kendi serisinin PALETTE rengiyle
            # hizali (v2.5.5) — hangi eksenin hangi seriye ait oldugu
            # koyu zeminde de okunur kalir.
            yaxis=dict(
                title=dict(text='Regression Rate (mm/s)',
                           font=dict(color=col_reg)),
                tickfont=dict(color=col_reg),
                side='left'
            ),
            yaxis2=dict(
                title=dict(text='Port Diameter (mm)',
                           font=dict(color=col_port)),
                tickfont=dict(color=col_port),
                anchor='x',
                overlaying='y',
                side='right'
            ),
            yaxis3=dict(
                title=dict(text='G_ox (kg/m²/s)',
                           font=dict(color=col_flux)),
                tickfont=dict(color=col_flux),
                anchor='free',
                overlaying='y',
                side='right',
                position=0.95
            ),
            plot_bgcolor='white',
            paper_bgcolor='white',
            hovermode='x unified',
            legend=dict(
                orientation='h',
                yanchor='bottom',
                y=1.02,
                xanchor='right',
                x=1
            ),
            height=500
        )

        # Summary annotation
        avg_regression = float(np.mean(regression_data['regression_rate']))
        initial_port = float(regression_data['port_diameter'][0])
        final_port = float(regression_data['port_diameter'][-1])
        growth_pct = ((final_port / initial_port - 1.0) * 100.0
                      if initial_port > 0 else 0.0)

        # v2.5.5: beyaz zemin + siyah kenarli kutu KALDIRILDI — koyu temada
        # goz aliyordu. plotly_dark.js annotation'lara koyu zemin pilini ve
        # okunur yazi rengini kendisi uygular (tek merkezden tema).
        fig.add_annotation(
            x=0.02, y=0.98,
            xref='paper', yref='paper',
            text=(
                f'<b>Average Values</b><br>'
                f'Regression rate: {avg_regression:.3f} mm/s<br>'
                f'Initial port: {initial_port:.1f} mm<br>'
                f'Final port: {final_port:.1f} mm<br>'
                f'Port growth: {growth_pct:.0f}%'
            ),
            showarrow=False,
            align='left',
            font=dict(size=10)
        )

        return _fig_json(fig)
    
    def compare_fuel_types(self, base_conditions: Dict) -> str:
        """Yakıt türü karşılaştırma grafiği (Plotly JSON).

        Eksen dizileri _as_list ile listeye cevrilir (bkz. create_regression_plot
        bdata notu); sabit width kaldirildi. v2.5.5: JSON cikisi _fig_json
        kapisindan gecer, seri renkleri merkezi PALETTE'ten atanir.
        """
        from hrma.visualization.visualization import PALETTE, _fig_json

        fig = go.Figure()

        colors = PALETTE

        # Her yakıt türü için regresyon eğrisi
        for i, (fuel_type, fuel_props) in enumerate(self.fuel_properties.items()):
            # Base conditions'ı kopyala ve yakıt tipini değiştir
            conditions = base_conditions.copy()
            conditions['fuel_type'] = fuel_type
            conditions['regression_a'] = fuel_props['a']
            conditions['regression_n'] = fuel_props['n']
            # v2.6.2 FİZİK DENETİMİ (F159): yoğunluk da yakıtla birlikte
            # DEĞİŞTİRİLMELİ. Eskiden yalnız a/n güncelleniyor, rho_f ise
            # base_conditions['fuel_density'] (ör. parafin 900 kg/m³) olarak
            # kalıyordu; PMMA (1180) ve ABS (1050) eğrileri yanlış yoğunlukla
            # çiziliyordu. Etki flux_mode='total' modunda görünür
            # (G_fuel ∝ rho_f): parafin↔PMMA arası %31 yoğunluk hatası tipik
            # G_fuel/G_total≈0.14 payında G_total'i ~%4.3, r_dot'u ~%2.4
            # kaydırıyordu. 'ox' modunda etki sıfırdır ama tutarsızlık yine
            # de kapatılır (mod değişince sessizce geri gelmesin).
            conditions['fuel_density'] = fuel_props['density']

            # Regresyon analizi yap
            regression_data = self.analyze_regression_vs_time(conditions)

            # Grafiğe ekle
            fig.add_trace(go.Scatter(
                x=_as_list(regression_data['time']),
                y=_as_list(regression_data['regression_rate']),
                mode='lines',
                name=fuel_props['name'],
                line=dict(color=colors[i % len(colors)], width=2),
                hovertemplate=f'{fuel_props["name"]}<br>Time: %{{x:.1f}} s<br>Regression: %{{y:.3f}} mm/s<extra></extra>'
            ))

        # Grafik düzeni
        fig.update_layout(
            title='Fuel Type Regression Rate Comparison',
            xaxis=dict(title='Time (s)'),
            yaxis=dict(title='Regression Rate (mm/s)'),
            plot_bgcolor='white',
            paper_bgcolor='white',
            hovermode='x unified',
            legend=dict(
                orientation='v',
                yanchor='top',
                y=1,
                xanchor='left',
                x=1.02
            ),
            height=500
        )

        return _fig_json(fig)

# Global instance
regression_analyzer = RegressionAnalyzer()