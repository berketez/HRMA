"""
Regression Rate Analysis Module
Hibrit roket yakıt regresyon hızı analizi ve görselleştirmesi
"""

import numpy as np
import plotly.graph_objects as go
from typing import Dict, Tuple

class RegressionAnalyzer:
    """Hibrit roket yakıt regresyon analizi"""
    
    def __init__(self):
        # Farklı yakıt türleri için regresyon parametreleri
        self.fuel_properties = {
            'htpb': {'a': 0.0003, 'n': 0.5, 'density': 920, 'name': 'HTPB'},
            'paraffin': {'a': 0.0008, 'n': 0.8, 'density': 900, 'name': 'Paraffin Wax'},
            'pe': {'a': 0.0005, 'n': 0.8, 'density': 960, 'name': 'Polyethylene'},
            'pmma': {'a': 0.0004, 'n': 0.65, 'density': 1180, 'name': 'PMMA'},
            'abs': {'a': 0.0003, 'n': 0.7, 'density': 1050, 'name': 'ABS Plastic'}
        }
    
    def analyze_regression_vs_time(self, motor_data: Dict) -> Dict:
        """Zamana karşı regresyon hızı analizi"""
        
        # Motor parametrelerini al
        burn_time = motor_data.get('burn_time', 10.0)  # s
        mdot_ox = motor_data.get('mdot_ox', 1.0)  # kg/s
        port_initial = motor_data.get('port_diameter_initial', 0.03)  # m
        port_final = motor_data.get('port_diameter_final', 0.05)  # m
        fuel_type = motor_data.get('fuel_type', 'htpb')
        grain_length = motor_data.get('chamber_length', 0.3) * 0.8  # m
        
        # Yakıt özelliklerini al
        fuel_props = self.fuel_properties.get(fuel_type, self.fuel_properties['htpb'])
        a = motor_data.get('regression_a', fuel_props['a'])
        n = motor_data.get('regression_n', fuel_props['n'])
        
        # Zaman dizisi
        time_steps = 100
        time_array = np.linspace(0, burn_time, time_steps)
        
        # Her zaman adımı için port çapı ve regresyon hızı hesapla
        port_radius = port_initial / 2  # m
        regression_rates = []
        port_diameters = []
        oxidizer_flux = []
        
        dt = burn_time / time_steps
        
        for t in time_array:
            # Port alanı ve oksitleyici akış yoğunluğu
            port_area = np.pi * port_radius**2  # m²
            G_ox = mdot_ox / port_area  # kg/m²/s
            
            # Regresyon hızı: r_dot = a * G_ox^n
            r_dot = a * (G_ox**n)  # m/s
            
            # Sonuçları kaydet
            regression_rates.append(r_dot * 1000)  # mm/s'ye çevir
            port_diameters.append(port_radius * 2 * 1000)  # mm'ye çevir
            oxidizer_flux.append(G_ox)
            
            # Port yarıçapını güncelle
            if t < burn_time - dt:
                port_radius += r_dot * dt
        
        return {
            'time': time_array.tolist(),
            'regression_rate': regression_rates,
            'port_diameter': port_diameters,
            'oxidizer_flux': oxidizer_flux,
            'fuel_type': fuel_type,
            'fuel_name': fuel_props['name'],
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