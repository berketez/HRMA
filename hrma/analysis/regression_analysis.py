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
        grain_length = motor_data.get('chamber_length', 0.3) * 0.8  # m
        flux_mode = motor_data.get('flux_mode', 'total')  # 'total' (Marxman) | 'ox'

        # Yakıt özelliklerini al
        fuel_props = self.fuel_properties.get(fuel_type, self.fuel_properties['htpb'])
        a = motor_data.get('regression_a', fuel_props['a'])
        n = motor_data.get('regression_n', fuel_props['n'])
        rho_f = motor_data.get('fuel_density', fuel_props['density'])  # kg/m³

        # Zaman dizisi
        time_steps = 100
        time_array = np.linspace(0, burn_time, time_steps)

        # Her zaman adımı için port çapı ve regresyon hızı hesapla
        port_radius = port_initial / 2  # m
        regression_rates = []
        port_diameters = []
        oxidizer_flux = []
        total_flux = []

        dt = burn_time / time_steps

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
        """Regresyon hızı grafiği oluştur"""
        
        fig = go.Figure()
        
        # Regresyon hızı vs zaman
        fig.add_trace(go.Scatter(
            x=regression_data['time'],
            y=regression_data['regression_rate'],
            mode='lines',
            name='Regresyon Hızı',
            line=dict(color='red', width=3),
            hovertemplate='Zaman: %{x:.1f} s<br>Regresyon Hızı: %{y:.3f} mm/s<extra></extra>'
        ))
        
        # İkinci Y ekseni için port çapı
        fig.add_trace(go.Scatter(
            x=regression_data['time'],
            y=regression_data['port_diameter'],
            mode='lines',
            name='Port Çapı',
            line=dict(color='blue', width=3, dash='dash'),
            yaxis='y2',
            hovertemplate='Zaman: %{x:.1f} s<br>Port Çapı: %{y:.1f} mm<extra></extra>'
        ))
        
        # Oksitleyici akış yoğunluğu
        fig.add_trace(go.Scatter(
            x=regression_data['time'],
            y=regression_data['oxidizer_flux'],
            mode='lines',
            name='Oksitleyici Akış Yoğunluğu',
            line=dict(color='green', width=2),
            yaxis='y3',
            visible='legendonly',
            hovertemplate='Zaman: %{x:.1f} s<br>G_ox: %{y:.0f} kg/m²/s<extra></extra>'
        ))
        
        # Grafik düzeni
        fig.update_layout(
            title=dict(
                text=f'{regression_data["fuel_name"]} Regresyon Analizi<br>'
                     f'<sub>a = {regression_data["parameters"]["a"]:.4f}, n = {regression_data["parameters"]["n"]:.2f}</sub>',
                x=0.5,
                font=dict(size=16)
            ),
            xaxis=dict(
                title='Zaman (s)',
                showgrid=True,
                gridcolor='rgba(128,128,128,0.2)'
            ),
            yaxis=dict(
                title='Regresyon Hızı (mm/s)',
                titlefont=dict(color='red'),
                tickfont=dict(color='red'),
                side='left'
            ),
            yaxis2=dict(
                title='Port Çapı (mm)',
                titlefont=dict(color='blue'),
                tickfont=dict(color='blue'),
                anchor='x',
                overlaying='y',
                side='right'
            ),
            yaxis3=dict(
                title='G_ox (kg/m²/s)',
                titlefont=dict(color='green'),
                tickfont=dict(color='green'),
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
            width=800,
            height=500
        )
        
        # Ortalama değerler için notlar
        avg_regression = np.mean(regression_data['regression_rate'])
        initial_port = regression_data['port_diameter'][0]
        final_port = regression_data['port_diameter'][-1]
        
        fig.add_annotation(
            x=0.02, y=0.98,
            xref='paper', yref='paper',
            text=(
                f'<b>Ortalama Değerler:</b><br>'
                f'Regresyon Hızı: {avg_regression:.3f} mm/s<br>'
                f'Başlangıç Port: {initial_port:.1f} mm<br>'
                f'Son Port: {final_port:.1f} mm<br>'
                f'Port Artışı: {(final_port/initial_port - 1)*100:.0f}%'
            ),
            showarrow=False,
            align='left',
            bgcolor='rgba(255, 255, 255, 0.9)',
            bordercolor='black',
            borderwidth=1,
            font=dict(size=10)
        )
        
        return fig.to_json()
    
    def compare_fuel_types(self, base_conditions: Dict) -> str:
        """Farklı yakıt türlerini karşılaştır"""
        
        fig = go.Figure()
        
        colors = ['red', 'blue', 'green', 'orange', 'purple']
        
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
                x=regression_data['time'],
                y=regression_data['regression_rate'],
                mode='lines',
                name=fuel_props['name'],
                line=dict(color=colors[i % len(colors)], width=2),
                hovertemplate=f'{fuel_props["name"]}<br>Zaman: %{{x:.1f}} s<br>Regresyon: %{{y:.3f}} mm/s<extra></extra>'
            ))
        
        # Grafik düzeni
        fig.update_layout(
            title='Yakıt Türleri Regresyon Hızı Karşılaştırması',
            xaxis=dict(title='Zaman (s)'),
            yaxis=dict(title='Regresyon Hızı (mm/s)'),
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
            width=800,
            height=500
        )
        
        return fig.to_json()

# Global instance
regression_analyzer = RegressionAnalyzer()