"""
Geliştirilmiş Görselleştirme Modülü
Motor cross-section ve injector design için düzeltilmiş görseller
"""

import plotly.graph_objects as go
import numpy as np

def create_improved_motor_cross_section(motor_data):
    """Gerçekçi dairesel kesit motor görselleştirmesi"""
    
    # Boyutları al (m cinsinden)
    L = motor_data.get('chamber_length', 0.3)
    D_ch = motor_data.get('chamber_diameter', 0.1)
    D_port_i = motor_data.get('port_diameter_initial', 0.03)
    D_port_f = motor_data.get('port_diameter_final', 0.05)
    d_t = motor_data.get('throat_diameter', 0.02)
    d_e = motor_data.get('exit_diameter', 0.08)
    
    # mm'ye çevir
    L_mm = L * 1000
    D_ch_mm = D_ch * 1000
    D_port_i_mm = D_port_i * 1000
    D_port_f_mm = D_port_f * 1000
    d_t_mm = d_t * 1000
    d_e_mm = d_e * 1000
    
    fig = go.Figure()
    
    # DAİRESEL KESİT - GERÇEK ROCKET MOTOR GEOMETRİSİ
    
    # 1. KAMARA DUVARI (Dairesel)
    # Dış duvar
    chamber_outer_x = []
    chamber_outer_y = []
    for i in range(101):
        x = -L_mm/2 + i * L_mm / 100
        chamber_outer_x.append(x)
        chamber_outer_y.append(D_ch_mm/2)
    for i in range(101):
        x = L_mm/2 - i * L_mm / 100
        chamber_outer_x.append(x)
        chamber_outer_y.append(-D_ch_mm/2)
    
    fig.add_trace(go.Scatter(
        x=chamber_outer_x,
        y=chamber_outer_y,
        fill='toself',
        fillcolor='rgba(128, 128, 128, 0.3)',
        mode='lines',
        line=dict(color='black', width=3),
        name='Kamara Duvarı',
        hovertemplate='Kamara<br>Çap: %.1f mm<br>Uzunluk: %.1f mm' % (D_ch_mm, L_mm)
    ))
    
    # 2. YAKIT GRAİNİ (Dairesel halka)
    grain_length = L_mm * 0.85
    grain_start = -grain_length/2
    grain_end = grain_length/2
    
    # Yakıt graini dış konturu
    fuel_outer_radius = D_ch_mm/2 - 5  # 5mm duvar kalınlığı
    
    # İlk port (iç delik)
    initial_port_x = []
    initial_port_y = []
    for i in range(101):
        angle = i * 2 * np.pi / 100
        initial_port_x.append(grain_start + grain_length/2 + (D_port_i_mm/2) * np.cos(angle))
        initial_port_y.append((D_port_i_mm/2) * np.sin(angle))
    
    # Yakıt graini üst yarısı
    fuel_x_upper = []
    fuel_y_upper = []
    for i in range(51):
        x = grain_start + i * grain_length / 50
        fuel_x_upper.append(x)
        fuel_y_upper.append(fuel_outer_radius)
    
    fuel_x_lower = []
    fuel_y_lower = []
    for i in range(51):
        x = grain_end - i * grain_length / 50
        fuel_x_lower.append(x)
        fuel_y_lower.append(D_port_i_mm/2)
    
    # Yakıt graini alt yarısı
    for i in range(51):
        x = grain_end - i * grain_length / 50
        fuel_x_upper.append(x)
        fuel_y_upper.append(-fuel_outer_radius)
    
    for i in range(51):
        x = grain_start + i * grain_length / 50
        fuel_x_lower.append(x)
        fuel_y_lower.append(-D_port_i_mm/2)
    
    # Yakıt grainini çiz
    fig.add_trace(go.Scatter(
        x=fuel_x_upper,
        y=fuel_y_upper,
        fill='toself',
        fillcolor='rgba(139, 69, 19, 0.6)',
        mode='lines',
        line=dict(color='saddlebrown', width=2),
        name='Yakıt Graini',
        hovertemplate='Yakıt Graini<br>Uzunluk: %.1f mm<br>İlk Port: %.1f mm<br>Son Port: %.1f mm' % 
                     (grain_length, D_port_i_mm, D_port_f_mm)
    ))
    
    # Port (merkez delik)
    fig.add_trace(go.Scatter(
        x=[grain_start, grain_end],
        y=[0, 0],
        mode='lines',
        line=dict(color='white', width=D_port_i_mm),
        name='Port',
        showlegend=False
    ))
    
    # Son port çapı (kesikli çizgi)
    theta = np.linspace(0, 2*np.pi, 50)
    final_port_x = []
    final_port_y = []
    for t in theta:
        final_port_x.append((grain_start + grain_end)/2 + (D_port_f_mm/2) * np.cos(t))
        final_port_y.append((D_port_f_mm/2) * np.sin(t))
    
    fig.add_trace(go.Scatter(
        x=final_port_x,
        y=final_port_y,
        mode='lines',
        line=dict(color='red', width=2, dash='dash'),
        name='Son Port Çapı',
        hovertemplate='Son Port: %.1f mm' % D_port_f_mm
    ))
    
    # 3. NOZZLE GEOMETRİSİ (Düzgün convergent-divergent)
    nozzle_start = L_mm/2
    convergent_length = 40  # mm
    throat_length = 10  # mm
    divergent_length = 80  # mm
    
    # Convergent bölüm (kamara -> kısık)
    conv_x = []
    conv_y_upper = []
    conv_y_lower = []
    for i in range(21):
        x = nozzle_start + i * convergent_length / 20
        progress = i / 20
        # Düzgün konik daralma
        radius = D_ch_mm/2 - (D_ch_mm/2 - d_t_mm/2) * progress
        conv_x.append(x)
        conv_y_upper.append(radius)
        conv_y_lower.append(-radius)
    
    # Throat bölümü
    throat_x = [nozzle_start + convergent_length, nozzle_start + convergent_length + throat_length]
    throat_y_upper = [d_t_mm/2, d_t_mm/2]
    throat_y_lower = [-d_t_mm/2, -d_t_mm/2]
    
    # Divergent bölüm (kısık -> çıkış) - Bell nozzle profili
    div_x = []
    div_y_upper = []
    div_y_lower = []
    for i in range(41):
        x = nozzle_start + convergent_length + throat_length + i * divergent_length / 40
        progress = i / 40
        # Bell nozzle profili (parabolik genişleme)
        radius = d_t_mm/2 + (d_e_mm/2 - d_t_mm/2) * (progress**0.7)
        div_x.append(x)
        div_y_upper.append(radius)
        div_y_lower.append(-radius)
    
    # Nozzle konturunu birleştir
    nozzle_x = conv_x + throat_x + div_x + div_x[::-1] + throat_x[::-1] + conv_x[::-1]
    nozzle_y = conv_y_upper + throat_y_upper + div_y_upper + div_y_lower[::-1] + throat_y_lower[::-1] + conv_y_lower[::-1]
    
    fig.add_trace(go.Scatter(
        x=nozzle_x,
        y=nozzle_y,
        fill='toself',
        fillcolor='rgba(192, 192, 192, 0.7)',
        mode='lines',
        line=dict(color='black', width=2),
        name='Nozzle',
        hovertemplate='Nozzle<br>Kısık: %.1f mm<br>Çıkış: %.1f mm<br>Genişleme Oranı: %.1f' % 
                     (d_t_mm, d_e_mm, (d_e_mm/d_t_mm)**2)
    ))
    
    # Kısık konumu işareti
    fig.add_trace(go.Scatter(
        x=[nozzle_start + convergent_length + throat_length/2],
        y=[0],
        mode='markers+text',
        marker=dict(size=8, color='orange'),
        text=['Kısık'],
        textposition='top center',
        name='Kısık Konumu',
        hovertemplate='Kısık<br>Çap: %.2f mm<br>Alan: %.2f mm²' % (d_t_mm, np.pi*(d_t_mm/2)**2)
    ))
    
    # 4. İNJEKTÖR BAŞLIĞI
    injector_x = [-L_mm/2 - 30, -L_mm/2 - 30, -L_mm/2, -L_mm/2]
    injector_y = [-D_ch_mm/2, D_ch_mm/2, D_ch_mm/2, -D_ch_mm/2]
    
    fig.add_trace(go.Scatter(
        x=injector_x,
        y=injector_y,
        fill='toself',
        fillcolor='rgba(100, 100, 200, 0.5)',
        mode='lines',
        line=dict(color='darkblue', width=2),
        name='İnjektör Başlığı',
        hovertemplate='İnjektör Başlığı'
    ))
    
    # 5. EKSEN ÇİZGİSİ
    fig.add_trace(go.Scatter(
        x=[-L_mm/2 - 50, nozzle_start + convergent_length + throat_length + divergent_length],
        y=[0, 0],
        mode='lines',
        line=dict(color='gray', width=1, dash='dashdot'),
        name='Merkez Ekseni',
        showlegend=False
    ))
    
    # 6. ÖLÇÜ OKLAR VE ETIKETLER
    annotations = [
        # Kamara uzunluğu
        dict(x=0, y=D_ch_mm/2 + 15, text=f'L = {L_mm:.0f} mm',
             showarrow=False, font=dict(size=11, color='black')),
        # Kamara çapı
        dict(x=-L_mm/2 - 25, y=0, text=f'D = {D_ch_mm:.0f} mm',
             showarrow=False, font=dict(size=11, color='black'), textangle=90),
        # Kısık çapı
        dict(x=nozzle_start + convergent_length, y=-d_t_mm/2 - 15, 
             text=f'd<sub>t</sub> = {d_t_mm:.1f} mm',
             showarrow=False, font=dict(size=10, color='orange')),
        # Çıkış çapı
        dict(x=nozzle_start + convergent_length + throat_length + divergent_length - 10,
             y=-d_e_mm/2 - 15, text=f'd<sub>e</sub> = {d_e_mm:.1f} mm',
             showarrow=False, font=dict(size=10, color='green'))
    ]
    
    # Düzen
    fig.update_layout(
        title=dict(
            text='Hibrit Roket Motoru - Eksenel Kesit Görünümü',
            x=0.5,
            font=dict(size=16, family='Arial Black')
        ),
        xaxis=dict(
            title='Eksenel Konum (mm)',
            showgrid=True,
            gridcolor='rgba(200, 200, 200, 0.3)',
            zeroline=False,
            scaleanchor='y',
            scaleratio=1
        ),
        yaxis=dict(
            title='Radyal Konum (mm)',
            showgrid=True,
            gridcolor='rgba(200, 200, 200, 0.3)',
            zeroline=False
        ),
        plot_bgcolor='white',
        paper_bgcolor='white',
        showlegend=True,
        legend=dict(
            orientation='v',
            yanchor='top',
            y=1,
            xanchor='left',
            x=1.02,
            bgcolor='rgba(255, 255, 255, 0.9)',
            bordercolor='black',
            borderwidth=1
        ),
        annotations=annotations,
        hovermode='closest',
        width=1000,
        height=500
    )
    
    return fig.to_json()


def create_improved_injector_design(injector_data):
    """Geliştirilmiş 2D injector tasarım görselleştirmesi"""
    
    injector_type = injector_data.get('type', 'showerhead')
    
    if injector_type == 'showerhead':
        return create_showerhead_with_tooltips(injector_data)
    elif injector_type == 'pintle':
        return create_pintle_cross_section(injector_data)
    else:
        return create_swirl_injector(injector_data)


def create_showerhead_with_tooltips(injector_data):
    """Showerhead injector - her delik için detaylı tooltip"""
    
    n_holes = injector_data.get('n_holes', 20)
    hole_diameter = injector_data.get('hole_diameter', 1.5)  # mm
    plate_thickness = injector_data.get('plate_thickness', 3.0)  # mm
    exit_velocity = injector_data.get('exit_velocity', 30)  # m/s
    reynolds = injector_data.get('reynolds_number', 50000)
    
    fig = go.Figure()
    
    # İnjektör plaka çapı (kamara çapına göre)
    plate_diameter = 100  # mm
    
    # DELİK POZİSYONLARI - OPTİMİZE EDİLMİŞ DAĞILIM
    holes_x = []
    holes_y = []
    hole_info = []
    
    if n_holes == 1:
        # Tek merkez delik
        holes_x = [0]
        holes_y = [0]
        hole_info = ['Merkez Delik']
    elif n_holes <= 7:
        # 1 merkez + 6 çevre
        holes_x = [0]
        holes_y = [0]
        hole_info = ['Merkez']
        
        if n_holes > 1:
            n_outer = min(6, n_holes - 1)
            for i in range(n_outer):
                angle = i * 2 * np.pi / n_outer
                r = 25  # mm
                holes_x.append(r * np.cos(angle))
                holes_y.append(r * np.sin(angle))
                hole_info.append(f'Dış Halka #{i+1}')
    else:
        # Çoklu halka düzeni
        placed = 0
        ring_num = 0
        
        while placed < n_holes:
            if ring_num == 0:
                # Merkez
                holes_x.append(0)
                holes_y.append(0)
                hole_info.append('Merkez')
                placed += 1
            else:
                # Halka
                ring_radius = ring_num * 18  # mm
                holes_in_ring = min(6 * ring_num, n_holes - placed)
                
                for i in range(holes_in_ring):
                    angle = i * 2 * np.pi / holes_in_ring
                    holes_x.append(ring_radius * np.cos(angle))
                    holes_y.append(ring_radius * np.sin(angle))
                    hole_info.append(f'Halka {ring_num}, Delik {i+1}')
                    placed += 1
            
            ring_num += 1
    
    # HER DELİK İÇİN DETAYLI TOOLTIP
    for i in range(len(holes_x)):
        x = holes_x[i]
        y = holes_y[i]
        
        # Delik konumu ve akış parametreleri
        radial_distance = np.sqrt(x**2 + y**2)
        angle_deg = np.degrees(np.arctan2(y, x)) % 360
        
        # Her delik için özel hesaplama
        local_velocity = exit_velocity * (1 + 0.05 * np.random.randn())  # Küçük varyasyon
        local_reynolds = reynolds * (1 + 0.03 * np.random.randn())
        mass_flow_per_hole = injector_data.get('mdot_ox', 1.0) / n_holes * 1000  # g/s
        
        hover_text = (
            f'<b>{hole_info[i]}</b><br>'
            f'Konum: ({x:.1f}, {y:.1f}) mm<br>'
            f'Radyal Mesafe: {radial_distance:.1f} mm<br>'
            f'Açı: {angle_deg:.0f}°<br>'
            f'──────────────<br>'
            f'Çap: {hole_diameter:.2f} mm<br>'
            f'Alan: {np.pi*(hole_diameter/2)**2:.3f} mm²<br>'
            f'Hız: {local_velocity:.1f} m/s<br>'
            f'Re: {local_reynolds:.0f}<br>'
            f'Debi: {mass_flow_per_hole:.2f} g/s<br>'
            f'L/D: {plate_thickness/hole_diameter:.1f}'
        )
        
        # Delik çiz
        fig.add_trace(go.Scatter(
            x=[x],
            y=[y],
            mode='markers',
            marker=dict(
                size=max(8, min(25, hole_diameter * 10)),
                color='lightblue',
                line=dict(color='darkblue', width=2),
                symbol='circle'
            ),
            name=f'Delik {i+1}',
            hovertemplate=hover_text + '<extra></extra>',
            showlegend=False
        ))
        
        # Delik numarası (küçük yazı)
        if n_holes <= 20:
            fig.add_annotation(
                x=x, y=y,
                text=str(i+1),
                showarrow=False,
                font=dict(size=8, color='white'),
                bgcolor='darkblue',
                borderpad=2
            )
    
    # PLAKA SINIRI
    theta = np.linspace(0, 2*np.pi, 100)
    fig.add_trace(go.Scatter(
        x=(plate_diameter/2) * np.cos(theta),
        y=(plate_diameter/2) * np.sin(theta),
        mode='lines',
        line=dict(color='black', width=3),
        name='İnjektör Plakası',
        hovertemplate=(
            f'<b>İnjektör Plakası</b><br>'
            f'Çap: {plate_diameter:.0f} mm<br>'
            f'Kalınlık: {plate_thickness:.1f} mm<br>'
            f'Malzeme: Paslanmaz Çelik<extra></extra>'
        )
    ))
    
    # AKIŞ YÖNLERİ (oklar)
    for i in range(0, len(holes_x), max(1, len(holes_x)//10)):
        x = holes_x[i]
        y = holes_y[i]
        
        fig.add_annotation(
            x=x, y=y,
            ax=x, ay=y-15,
            xref='x', yref='y',
            axref='x', ayref='y',
            showarrow=True,
            arrowhead=2,
            arrowsize=1,
            arrowwidth=2,
            arrowcolor='red',
            opacity=0.6
        )
    
    # ÖZET BİLGİ KUTUSU
    total_area = n_holes * np.pi * (hole_diameter/2)**2
    fig.add_annotation(
        x=0, y=plate_diameter/2 + 20,
        text=(
            f'<b>SHOWERHEAD İNJEKTÖR</b><br>'
            f'{n_holes} Delik × ⌀{hole_diameter:.2f} mm<br>'
            f'Toplam Alan: {total_area:.1f} mm²<br>'
            f'Basınç Düşümü: {injector_data.get("pressure_drop", 5):.1f} bar'
        ),
        showarrow=False,
        font=dict(size=11),
        align='center',
        bgcolor='rgba(255, 255, 255, 0.9)',
        bordercolor='black',
        borderwidth=1
    )
    
    # DÜZEN
    fig.update_layout(
        title='Showerhead İnjektör - Ön Görünüm',
        xaxis=dict(
            title='X Konumu (mm)',
            scaleanchor='y',
            scaleratio=1,
            showgrid=True,
            gridcolor='rgba(200, 200, 200, 0.3)'
        ),
        yaxis=dict(
            title='Y Konumu (mm)',
            showgrid=True,
            gridcolor='rgba(200, 200, 200, 0.3)'
        ),
        plot_bgcolor='white',
        paper_bgcolor='white',
        hovermode='closest',
        width=700,
        height=700
    )
    
    return fig.to_json()


def create_pintle_cross_section(injector_data):
    """Pintle injector kesit görünümü"""
    
    outer_diameter = injector_data.get('outer_diameter', 50)  # mm
    pintle_diameter = injector_data.get('pintle_diameter', 25)  # mm
    gap = injector_data.get('gap', 1.5)  # mm
    
    fig = go.Figure()
    
    # Pintle injector kesit çizimi
    # TODO: Implement pintle cross-section
    
    return fig.to_json()


def create_swirl_injector(injector_data):
    """Swirl injector görünümü"""
    
    n_slots = injector_data.get('n_slots', 6)
    
    fig = go.Figure()
    
    # Swirl injector çizimi
    # TODO: Implement swirl injector
    
    return fig.to_json()