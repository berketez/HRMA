"""
Regression Rate Analysis Module
Hibrit roket yakıt regresyon hızı analizi ve görselleştirmesi

Marxman difüzyon-limitli regresyon teorisi (Marxman & Gilbert, 9th Int.
Symp. Combustion, 1963; Sutton & Biblarz, Rocket Propulsion Elements,
9. baskı, Böl. 16) regresyon hızını YEREL TOPLAM kütle akısına bağlar:

    r_dot = a · G_total^n,   G_total = G_ox + G_fuel

Yalnız G_ox kullanmak (eski sürüm), yakıt akısının önemli olduğu düşük
O/F / düşük G_ox rejiminde regresyonu OLDUĞUNDAN DÜŞÜK tahmin eder
(yakıt debisini ve dolayısıyla web tükenme süresini fazla iyimser gösterir
— güvenli olmayan yön). Bu modül varsayılan olarak G_total kullanır;
geriye uyum için G_ox modu opsiyoneldir.
"""

import numpy as np
import plotly.graph_objects as go
from typing import Dict, Tuple
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
                        flux_mode: str = 'total',
                        max_iter: int = 50, tol: float = 1e-6) -> Dict:
        """Marxman regresyon hızını tek bir port istasyonunda hesaplar.

        r_dot = a · G^n  (SI: r [m/s], G [kg/m²·s])

        flux_mode:
          'total' (VARSAYILAN, Marxman): G = G_ox + G_fuel. Yakıt akısı
                  regresyon hızına bağlı olduğundan (G_fuel = mdot_f/A_port,
                  mdot_f = rho_f·π·D·L·r_dot) sabit-nokta iterasyonu yapılır:
                  r → mdot_f → G_fuel → G_total → r ... yakınsayana dek.
                  Kaynak: Marxman & Gilbert (1963); Sutton & Biblarz 9th ed.,
                  Böl. 16; Chiaverini & Kuo, "Fundamentals of Hybrid Rocket
                  Combustion and Propulsion", AIAA Progress Vol. 218, 2007.
          'ox'   : G = G_ox (eski/klasik korelasyon değişkeni — geriye uyum).

        'total' modu için rho_f, port_diameter (m) ve grain_length (m)
        zorunludur (G_fuel'in hesaplanabilmesi için). Verilmezse 'ox' moduna
        düşülür ve uyarı döner.

        Döndürür: {'r_dot' [m/s], 'G_ox', 'G_fuel', 'G_total', 'mdot_f',
                   'flux_used', 'iterations', 'converged'}
        """
        G_ox = max(G_ox, 1e-9)

        # G_total için gerekli geometri yoksa veya 'ox' modu istendiyse:
        if flux_mode == 'ox' or rho_f is None or port_diameter is None or grain_length is None:
            r_dot = a * G_ox ** n
            return {
                'r_dot': r_dot, 'G_ox': G_ox, 'G_fuel': 0.0, 'G_total': G_ox,
                'mdot_f': 0.0, 'flux_used': G_ox, 'iterations': 0,
                'converged': True, 'mode': 'ox'
            }

        A_port = np.pi * (port_diameter / 2.0) ** 2
        mdot_ox = G_ox * A_port  # kg/s (sabit; G_ox tanımından)

        # Sabit-nokta iterasyonu: r_dot(G_total) <-> G_total(r_dot)
        # Başlangıç: yalnız G_ox ile (alt sınır tahmin).
        r_dot = a * G_ox ** n
        converged = False
        it = 0
        for it in range(1, max_iter + 1):
            # Bu istasyondaki yakıt üretimi -> yerel yakıt akısı.
            # Port-çıkış yaklaşımı: tüm grain boyunca üretilen yakıt aynı
            # kesitten geçer (G_fuel = mdot_f / A_port). Bu, port boyunca
            # biriken akının ÜST sınırıdır -> en yüksek r_dot -> web tükenme
            # süresinde KONSERVATİF (güvenli) taraf.
            mdot_f = rho_f * np.pi * port_diameter * grain_length * r_dot
            G_fuel = mdot_f / A_port
            G_total = G_ox + G_fuel
            r_new = a * G_total ** n
            if abs(r_new - r_dot) <= tol * max(r_new, 1e-12):
                r_dot = r_new
                converged = True
                break
            r_dot = r_new

        mdot_f = rho_f * np.pi * port_diameter * grain_length * r_dot
        G_fuel = mdot_f / A_port
        G_total = G_ox + G_fuel
        if not converged:
            # OPUS DENETİM DÜZELTMESİ (minor): sessiz yakınsamama yasak.
            # n≥0.7 egzotik yakıt + aşırı yakıt-baskın geometri 50 iterasyonu
            # aşabilir; kullanıcı son iterat kullanıldığını bilmeli.
            import warnings
            warnings.warn(
                f"Marxman G_total sabit-nokta iterasyonu {max_iter} adımda "
                f"yakınsamadı (n={n}, G_fuel/G_total="
                f"{G_fuel/max(G_total,1e-12):.3f}); son iterat kullanılıyor.",
                RuntimeWarning)
        return {
            'r_dot': r_dot, 'G_ox': G_ox, 'G_fuel': G_fuel, 'G_total': G_total,
            'mdot_f': mdot_f, 'flux_used': G_total, 'iterations': it,
            'converged': converged, 'mode': 'total'
        }

    def analyze_regression_vs_time(self, motor_data: Dict) -> Dict:
        """Zamana karşı regresyon hızı analizi.

        flux_mode (motor_data anahtarı): 'total' (varsayılan, Marxman
        G_total = G_ox + G_fuel) veya 'ox' (eski G_ox-only, geriye uyum).
        'total' modu için yakıt yoğunluğu ve grain boyu gerekir (motor_data'dan
        veya yakıt tablosundan).
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
        flux_mode = motor_data.get('flux_mode', 'total')  # 'total' (Marxman) | 'ox'

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

        for t in time_array:
            # Port alanı ve oksitleyici akış yoğunluğu
            port_area = np.pi * port_radius**2  # m²
            G_ox = mdot_ox / port_area  # kg/m²/s

            # Marxman G_total regresyonu (varsayılan) — iteratif kapanış.
            reg = self.regression_rate(
                a, n, G_ox,
                rho_f=rho_f, port_diameter=2 * port_radius,
                grain_length=grain_length, flux_mode=flux_mode
            )
            r_dot = reg['r_dot']  # m/s

            # Sonuçları kaydet
            regression_rates.append(r_dot * 1000)  # mm/s'ye çevir
            port_diameters.append(port_radius * 2 * 1000)  # mm'ye çevir
            oxidizer_flux.append(G_ox)
            total_flux.append(reg['G_total'])

            # Port yarıçapını güncelle
            if t < burn_time - dt:
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
            'parameters': {'a': a, 'n': n}
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