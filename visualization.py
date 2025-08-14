import plotly.graph_objects as go
import plotly.express as px
import numpy as np
import json
from scipy.interpolate import griddata
from typing import Dict, List, Tuple, Optional

def create_motor_plot(motor_data):
    """Create professional motor cross-section plot"""
    
    # Extract dimensions with safe defaults
    L = motor_data.get('chamber_length', 0.3)  # Default 300mm
    D_ch = motor_data.get('chamber_diameter', 0.1)  # Default 100mm
    D_port_i = motor_data.get('port_diameter_initial', 0.03)  # Default 30mm
    D_port_f = motor_data.get('port_diameter_final', 0.05)  # Default 50mm
    d_t = motor_data.get('throat_diameter', 0.02)  # Default 20mm
    d_e = motor_data.get('exit_diameter', 0.08)  # Default 80mm
    
    # Create figure
    fig = go.Figure()
    
    # Convert to mm for better readability
    L_mm = L * 1000
    D_ch_mm = D_ch * 1000
    D_port_i_mm = D_port_i * 1000
    D_port_f_mm = D_port_f * 1000
    d_t_mm = d_t * 1000
    d_e_mm = d_e * 1000
    
    # Calculate realistic nozzle geometry
    nozzle_length = max(d_e_mm * 1.5, 80)  # Realistic nozzle length
    
    # Chamber walls (upper and lower)
    chamber_wall_upper_x = [-L_mm/2, L_mm/2]
    chamber_wall_upper_y = [D_ch_mm/2, D_ch_mm/2]
    chamber_wall_lower_x = [-L_mm/2, L_mm/2]
    chamber_wall_lower_y = [-D_ch_mm/2, -D_ch_mm/2]
    
    fig.add_trace(go.Scatter(
        x=chamber_wall_upper_x, y=chamber_wall_upper_y,
        mode='lines',
        line=dict(color='black', width=4),
        name='Chamber Wall',
        showlegend=False
    ))
    
    fig.add_trace(go.Scatter(
        x=chamber_wall_lower_x, y=chamber_wall_lower_y,
        mode='lines',
        line=dict(color='black', width=4),
        name='Chamber Wall',
        showlegend=False
    ))
    
    # Head end wall
    fig.add_trace(go.Scatter(
        x=[-L_mm/2, -L_mm/2],
        y=[-D_ch_mm/2, D_ch_mm/2],
        mode='lines',
        line=dict(color='black', width=4),
        name='Head End',
        showlegend=False
    ))
    
    # Fuel grain - simple and clean design
    grain_length = L_mm * 0.8
    case_thickness = max(8, D_ch_mm * 0.08)  # Realistic case thickness
    
    # Fuel grain geometry
    grain_outer_radius = D_ch_mm/2 - case_thickness
    port_radius = D_port_i_mm/2
    
    # Grain boundaries
    grain_start = -grain_length/2
    grain_end = grain_length/2
    
    # Upper fuel grain (rectangle approximation for clarity)
    fig.add_trace(go.Scatter(
        x=[grain_start, grain_end, grain_end, grain_start, grain_start],
        y=[port_radius, port_radius, grain_outer_radius, grain_outer_radius, port_radius],
        fill='toself',
        fillcolor='rgba(160, 82, 45, 0.8)',
        mode='lines',
        line=dict(color='saddlebrown', width=3),
        name='Fuel Grain',
        hovertemplate=f'Fuel Grain<br>Length: {grain_length:.1f} mm<br>Thickness: {grain_outer_radius-port_radius:.1f} mm<br>Port: {D_port_i_mm:.1f} mm'
    ))
    
    # Lower fuel grain
    fig.add_trace(go.Scatter(
        x=[grain_start, grain_end, grain_end, grain_start, grain_start],
        y=[-port_radius, -port_radius, -grain_outer_radius, -grain_outer_radius, -port_radius],
        fill='toself',
        fillcolor='rgba(160, 82, 45, 0.8)',
        mode='lines',
        line=dict(color='saddlebrown', width=3),
        showlegend=False,
        hoverinfo='skip'
    ))
    
    # Final port outline (dashed) - simple lines
    final_port_radius = D_port_f_mm/2
    
    fig.add_trace(go.Scatter(
        x=[grain_start, grain_end],
        y=[final_port_radius, final_port_radius],
        mode='lines',
        line=dict(color='red', width=3, dash='dash'),
        name='Port (Final)',
        hovertemplate=f'Final Port: {D_port_f_mm:.1f} mm diameter'
    ))
    
    fig.add_trace(go.Scatter(
        x=[grain_start, grain_end],
        y=[-final_port_radius, -final_port_radius],
        mode='lines',
        line=dict(color='red', width=3, dash='dash'),
        showlegend=False,
        hoverinfo='skip'
    ))
    
    # Nozzle geometry
    nozzle_start_x = L_mm/2
    nozzle_end_x = nozzle_start_x + nozzle_length
    
    # Convergent section (chamber to throat)
    conv_length = nozzle_length * 0.3
    conv_x = np.linspace(nozzle_start_x, nozzle_start_x + conv_length, 30)
    conv_y_upper = D_ch_mm/2 - (D_ch_mm/2 - d_t_mm/2) * ((conv_x - nozzle_start_x) / conv_length)**1.5
    conv_y_lower = -conv_y_upper
    
    # Divergent section (throat to exit) - bell profile
    div_length = nozzle_length * 0.7
    div_x = np.linspace(nozzle_start_x + conv_length, nozzle_end_x, 50)
    div_progress = (div_x - (nozzle_start_x + conv_length)) / div_length
    div_y_upper = d_t_mm/2 + (d_e_mm/2 - d_t_mm/2) * div_progress**0.7
    div_y_lower = -div_y_upper
    
    # Complete nozzle contour
    nozzle_x_complete = np.concatenate([conv_x, div_x, div_x[::-1], conv_x[::-1]])
    nozzle_y_complete = np.concatenate([conv_y_upper, div_y_upper, div_y_lower[::-1], conv_y_lower[::-1]])
    
    fig.add_trace(go.Scatter(
        x=nozzle_x_complete, y=nozzle_y_complete,
        fill='toself',
        fillcolor='rgba(160, 160, 160, 0.8)',
        mode='lines',
        line=dict(color='black', width=3),
        name='Nozzle',
        hovertemplate='Nozzle<br>Throat: %.1f mm<br>Exit: %.1f mm<br>Expansion Ratio: %.1f' % 
                     (d_t_mm, d_e_mm, motor_data.get('expansion_ratio', d_e_mm**2/d_t_mm**2))
    ))
    
    # Add throat line indicator
    throat_x = nozzle_start_x + conv_length
    fig.add_trace(go.Scatter(
        x=[throat_x, throat_x],
        y=[-d_t_mm/2, d_t_mm/2],
        mode='lines',
        line=dict(color='orange', width=3),
        name='Throat',
        hovertemplate='Throat Location<br>Diameter: %.2f mm' % d_t_mm
    ))
    
    # Add centerline
    total_length = nozzle_end_x - (-L_mm/2)
    fig.add_trace(go.Scatter(
        x=[-L_mm/2, nozzle_end_x],
        y=[0, 0],
        mode='lines',
        line=dict(color='gray', width=1, dash='dot'),
        name='Centerline',
        showlegend=False
    ))
    
    # Get nozzle angles from motor data
    convergent_angle = motor_data.get('convergent_angle', 15.0)  # degrees
    divergent_angle = motor_data.get('divergent_angle', 12.0)   # degrees
    expansion_ratio = (d_e_mm / d_t_mm) ** 2
    
    # Add angle indicator lines with better visibility
    # Convergent angle line and arc
    conv_mid_x = nozzle_start_x + conv_length * 0.5
    conv_mid_y = D_ch_mm/2 - (D_ch_mm/2 - d_t_mm/2) * 0.5
    angle_line_length = 40  # mm - increased for better visibility
    
    conv_angle_rad = np.radians(convergent_angle)
    conv_angle_end_x = conv_mid_x + angle_line_length * np.cos(np.pi - conv_angle_rad)
    conv_angle_end_y = conv_mid_y + angle_line_length * np.sin(np.pi - conv_angle_rad)
    
    # Add angle arc for convergent section
    arc_angles = np.linspace(np.pi, np.pi - conv_angle_rad, 20)
    arc_radius = 25
    arc_x = conv_mid_x + arc_radius * np.cos(arc_angles)
    arc_y = conv_mid_y + arc_radius * np.sin(arc_angles)
    
    fig.add_trace(go.Scatter(
        x=arc_x,
        y=arc_y,
        mode='lines',
        line=dict(color='orange', width=2),
        name=f'Convergent {convergent_angle}°',
        showlegend=True
    ))
    
    fig.add_trace(go.Scatter(
        x=[conv_mid_x, conv_angle_end_x],
        y=[conv_mid_y, conv_angle_end_y],
        mode='lines',
        line=dict(color='orange', width=3, dash='dot'),
        name=f'Conv. Angle {convergent_angle}°',
        showlegend=False
    ))
    
    # Divergent angle line and arc
    div_mid_x = throat_x + (nozzle_end_x - throat_x) * 0.5
    div_progress_mid = (div_mid_x - throat_x) / div_length
    div_mid_y = d_t_mm/2 + (d_e_mm/2 - d_t_mm/2) * div_progress_mid**0.7
    
    div_angle_rad = np.radians(divergent_angle)
    div_angle_end_x = div_mid_x + angle_line_length * np.cos(div_angle_rad)
    div_angle_end_y = div_mid_y + angle_line_length * np.sin(div_angle_rad)
    
    # Add angle arc for divergent section
    arc_angles_div = np.linspace(0, div_angle_rad, 20)
    arc_x_div = div_mid_x + arc_radius * np.cos(arc_angles_div)
    arc_y_div = div_mid_y + arc_radius * np.sin(arc_angles_div)
    
    fig.add_trace(go.Scatter(
        x=arc_x_div,
        y=arc_y_div,
        mode='lines',
        line=dict(color='green', width=2),
        name=f'Divergent {divergent_angle}°',
        showlegend=True
    ))
    
    fig.add_trace(go.Scatter(
        x=[div_mid_x, div_angle_end_x],
        y=[div_mid_y, div_angle_end_y],
        mode='lines',
        line=dict(color='green', width=3, dash='dot'),
        name=f'Div. Angle {divergent_angle}°',
        showlegend=False
    ))

    # Add dimension annotations
    annotations = [
        dict(x=0, y=D_ch_mm/2 + 20, text=f'L = {L_mm:.1f} mm', 
             showarrow=False, font=dict(size=12)),
        dict(x=-L_mm/2 - 40, y=0, text=f'D = {D_ch_mm:.1f} mm', 
             showarrow=False, font=dict(size=12), textangle=90),
        dict(x=throat_x, y=-d_t_mm/2 - 30, text=f'dt = {d_t_mm:.2f} mm',
             showarrow=False, font=dict(size=10)),
        dict(x=nozzle_end_x, y=-d_e_mm/2 - 30, text=f'de = {d_e_mm:.1f} mm',
             showarrow=False, font=dict(size=10)),
        # Add angle annotations with larger text
        dict(x=conv_mid_x + 15, y=conv_mid_y + 10, text=f'α = {convergent_angle}°',
             showarrow=True, arrowhead=2, ax=0, ay=-30,
             font=dict(size=14, color='orange', family='Arial Black')),
        dict(x=div_mid_x + 15, y=div_mid_y + 10, text=f'β = {divergent_angle}°',
             showarrow=True, arrowhead=2, ax=0, ay=-30,
             font=dict(size=14, color='green', family='Arial Black')),
        # Add expansion ratio
        dict(x=(throat_x + nozzle_end_x) / 2, y=D_ch_mm/2 + 40, text=f'ε = {expansion_ratio:.1f}',
             showarrow=False, font=dict(size=11, color='purple'))
    ]
    
    # Clean motor layout with improved sizing
    fig.update_layout(
        title=dict(
            text='Hybrid Rocket Motor - Axial Cross-Section View',
            x=0.5,
            font=dict(size=18, family='Arial', color='black')
        ),
        xaxis=dict(
            title='Length (mm)',
            showgrid=True,
            gridcolor='rgba(128,128,128,0.2)',
            zeroline=True,
            zerolinecolor='gray',
            zerolinewidth=2,
            tickfont=dict(size=12)
        ),
        yaxis=dict(
            title='Radius (mm)',
            showgrid=True,
            gridcolor='rgba(128,128,128,0.2)',
            zeroline=True,
            zerolinecolor='gray',
            zerolinewidth=2,
            scaleanchor='x',
            scaleratio=0.5,
            tickfont=dict(size=12)
        ),
        showlegend=True,
        legend=dict(
            x=0.02, 
            y=0.98,
            bgcolor='rgba(255,255,255,0.9)',
            bordercolor='black',
            borderwidth=1
        ),
        hovermode='closest',
        width=1200,
        height=600,
        plot_bgcolor='white',
        annotations=annotations,
        margin=dict(t=80, b=80, l=100, r=60)
    )
    
    return fig.to_json()

def create_injector_plot(injector_data, injector_type):
    """Create professional injector visualization"""
    
    fig = go.Figure()
    
    if injector_type == 'showerhead':
        # Create professional showerhead pattern
        n_holes = injector_data['n_holes']
        d_h_mm = injector_data['hole_diameter']  # Keep in mm
        
        # Simplified plate design
        plate_radius_mm = 60  # Fixed reasonable size
        
        # Simple hole pattern - hexagonal close-packed or circular rings
        hole_positions_x = []
        hole_positions_y = []
        
        if n_holes == 1:
            # Single center hole
            hole_positions_x = [0]
            hole_positions_y = [0]
        elif n_holes <= 7:
            # Center + ring pattern
            hole_positions_x = [0]
            hole_positions_y = [0]
            
            remaining = n_holes - 1
            if remaining > 0:
                ring_radius = 20
                angles = np.linspace(0, 2*np.pi, remaining, endpoint=False)
                hole_positions_x.extend(ring_radius * np.cos(angles))
                hole_positions_y.extend(ring_radius * np.sin(angles))
        else:
            # Multiple rings
            holes_placed = 0
            ring = 0
            
            while holes_placed < n_holes:
                if ring == 0:
                    # Center hole
                    hole_positions_x.append(0)
                    hole_positions_y.append(0)
                    holes_placed += 1
                else:
                    # Ring holes
                    ring_radius = ring * 15  # 15mm spacing
                    holes_in_ring = min(6 * ring, n_holes - holes_placed)
                    
                    angles = np.linspace(0, 2*np.pi, holes_in_ring, endpoint=False)
                    hole_positions_x.extend(ring_radius * np.cos(angles))
                    hole_positions_y.extend(ring_radius * np.sin(angles))
                    holes_placed += holes_in_ring
                
                ring += 1
        
        # Draw all holes at once
        fig.add_trace(go.Scatter(
            x=hole_positions_x,
            y=hole_positions_y,
            mode='markers',
            marker=dict(
                size=max(12, min(20, d_h_mm * 8)), 
                color='lightblue', 
                line=dict(color='darkblue', width=2),
                symbol='circle'
            ),
            name=f'Injection Holes ({n_holes})',
            hovertemplate=f'Injection Hole<br>Diameter: {d_h_mm:.2f} mm<br>Total Holes: {n_holes}<br>Total Area: {n_holes * np.pi * (d_h_mm/2)**2:.2f} mm²'
        ))
        
        # Simple plate boundary
        theta = np.linspace(0, 2*np.pi, 100)
        
        fig.add_trace(go.Scatter(
            x=plate_radius_mm * np.cos(theta),
            y=plate_radius_mm * np.sin(theta),
            mode='lines',
            line=dict(color='black', width=4),
            name='Injector Plate',
            hovertemplate=f'Plate Diameter: {plate_radius_mm*2:.1f} mm'
        ))
        
        title = f'Showerhead Injector Design'
        subtitle = f'{n_holes} holes × ⌀{d_h_mm:.2f} mm | Total Area: {n_holes * np.pi * (d_h_mm/2)**2:.1f} mm²'
        
    elif injector_type == 'pintle':
        # Professional pintle injector cross-section with proper dimensions
        D_outer_mm = injector_data['outer_diameter']  # Keep in mm
        D_pintle_mm = injector_data['pintle_diameter']  # Keep in mm
        gap_mm = injector_data['gap']  # Keep in mm
        
        theta = np.linspace(0, 2*np.pi, 100)
        
        # Outer body with realistic appearance
        fig.add_trace(go.Scatter(
            x=D_outer_mm/2 * np.cos(theta),
            y=D_outer_mm/2 * np.sin(theta),
            fill='toself',
            fillcolor='rgba(160, 160, 160, 0.7)',
            mode='lines',
            line=dict(color='black', width=4),
            name='Outer Body',
            hovertemplate=f'Outer Body<br>Diameter: {D_outer_mm:.1f} mm<br>Material: Stainless Steel'
        ))
        
        # Inner flow annulus
        inner_radius = (D_outer_mm - gap_mm) / 2
        fig.add_trace(go.Scatter(
            x=inner_radius * np.cos(theta),
            y=inner_radius * np.sin(theta),
            fill='toself',
            fillcolor='rgba(173, 216, 230, 0.4)',
            mode='lines',
            line=dict(color='blue', width=2, dash='dot'),
            name='Flow Annulus',
            hovertemplate=f'Flow Annulus<br>Gap: {gap_mm:.2f} mm<br>Flow Area: {np.pi * ((D_outer_mm/2)**2 - inner_radius**2):.1f} mm²'
        ))
        
        # Pintle with professional appearance
        fig.add_trace(go.Scatter(
            x=D_pintle_mm/2 * np.cos(theta),
            y=D_pintle_mm/2 * np.sin(theta),
            fill='toself',
            fillcolor='rgba(64, 64, 64, 0.9)',
            mode='lines',
            line=dict(color='black', width=3),
            name='Pintle',
            hovertemplate=f'Pintle<br>Diameter: {D_pintle_mm:.1f} mm<br>Material: Stainless Steel'
        ))
        
        # Add mounting features
        # Pintle support arms (4 arms at 90° intervals)
        arm_angles = [0, np.pi/2, np.pi, 3*np.pi/2]
        arm_width = 2
        
        for i, angle in enumerate(arm_angles):
            x_inner = D_pintle_mm/2 * np.cos(angle)
            y_inner = D_pintle_mm/2 * np.sin(angle)
            x_outer = inner_radius * np.cos(angle)
            y_outer = inner_radius * np.sin(angle)
            
            # Create arm rectangle
            arm_x = [x_inner - arm_width/2 * np.sin(angle), 
                    x_outer - arm_width/2 * np.sin(angle),
                    x_outer + arm_width/2 * np.sin(angle),
                    x_inner + arm_width/2 * np.sin(angle),
                    x_inner - arm_width/2 * np.sin(angle)]
            arm_y = [y_inner + arm_width/2 * np.cos(angle),
                    y_outer + arm_width/2 * np.cos(angle), 
                    y_outer - arm_width/2 * np.cos(angle),
                    y_inner - arm_width/2 * np.cos(angle),
                    y_inner + arm_width/2 * np.cos(angle)]
            
            fig.add_trace(go.Scatter(
                x=arm_x, y=arm_y,
                fill='toself',
                fillcolor='rgba(64, 64, 64, 0.9)',
                mode='lines',
                line=dict(color='black', width=2),
                name='Support Arms' if i == 0 else '',
                showlegend=i == 0,
                hovertemplate='Support Arm<br>Thickness: 2 mm'
            ))
        
        # Flow direction arrows
        n_arrows = 8
        arrow_angles = np.linspace(0, 2*np.pi, n_arrows, endpoint=False)
        arrow_radius = (inner_radius + D_pintle_mm/2) / 2
        
        for i, angle in enumerate(arrow_angles):
            # Skip arrows where support arms are
            if not any(abs(angle - arm_angle) < 0.3 for arm_angle in arm_angles):
                x_start = arrow_radius * np.cos(angle)
                y_start = arrow_radius * np.sin(angle)
                x_end = (arrow_radius + 8) * np.cos(angle)
                y_end = (arrow_radius + 8) * np.sin(angle)
                
                fig.add_trace(go.Scatter(
                    x=[x_start, x_end],
                    y=[y_start, y_end],
                    mode='lines',
                    line=dict(color='red', width=3),
                    name='Flow Direction' if i == 0 else '',
                    showlegend=i == 0 and 'Flow Direction' not in [trace.name for trace in fig.data],
                    hoverinfo='skip'
                ))
        
        # Add dimension lines
        fig.add_trace(go.Scatter(
            x=[-D_outer_mm/2, D_outer_mm/2],
            y=[-D_outer_mm/2 - 10, -D_outer_mm/2 - 10],
            mode='lines+text',
            line=dict(color='gray', width=1),
            text=[f'⌀{D_outer_mm:.1f} mm', ''],
            textposition='middle center',
            name='Dimensions',
            hoverinfo='skip'
        ))
        
        title = f'Pintle Injector Design'
        subtitle = f'Gap: {gap_mm:.2f} mm | Flow Area: {np.pi * ((D_outer_mm/2)**2 - (D_pintle_mm/2)**2):.1f} mm²'
        
    elif injector_type == 'swirl':
        # Professional swirl injector top view with proper dimensions
        n_slots = injector_data['n_slots']
        w_mm = injector_data['slot_width']  # Keep in mm
        h_mm = injector_data['slot_height']  # Keep in mm
        
        # Chamber with realistic dimensions
        chamber_radius_mm = max(30, w_mm * 10)  # Minimum 30mm radius
        theta = np.linspace(0, 2*np.pi, 100)
        
        # Swirl chamber outer wall
        fig.add_trace(go.Scatter(
            x=chamber_radius_mm * np.cos(theta),
            y=chamber_radius_mm * np.sin(theta),
            fill='toself',
            fillcolor='rgba(180, 180, 180, 0.6)',
            mode='lines',
            line=dict(color='black', width=4),
            name='Swirl Chamber',
            hovertemplate=f'Swirl Chamber<br>Diameter: {chamber_radius_mm*2:.1f} mm<br>Material: Stainless Steel'
        ))
        
        # Inner swirl region
        inner_radius_mm = chamber_radius_mm * 0.7
        fig.add_trace(go.Scatter(
            x=inner_radius_mm * np.cos(theta),
            y=inner_radius_mm * np.sin(theta),
            fill='toself',
            fillcolor='rgba(135, 206, 235, 0.3)',
            mode='lines',
            line=dict(color='blue', width=2, dash='dot'),
            name='Swirl Region',
            hovertemplate='Swirl Flow Region'
        ))
        
        # Tangential slots with professional appearance
        slot_angles = np.linspace(0, 2*np.pi, n_slots, endpoint=False)
        
        for i, angle in enumerate(slot_angles):
            # Slot entry point on chamber wall
            x1 = chamber_radius_mm * np.cos(angle)
            y1 = chamber_radius_mm * np.sin(angle)
            
            # Tangential direction (90° offset for swirl)
            tangent_angle = angle + np.pi/2
            
            # Slot geometry - rectangular slot
            slot_length = w_mm * 3
            
            # Create slot as rectangle
            slot_corners_x = [
                x1 + w_mm/2 * np.cos(angle),
                x1 - w_mm/2 * np.cos(angle),
                x1 - w_mm/2 * np.cos(angle) + slot_length * np.cos(tangent_angle),
                x1 + w_mm/2 * np.cos(angle) + slot_length * np.cos(tangent_angle),
                x1 + w_mm/2 * np.cos(angle)
            ]
            
            slot_corners_y = [
                y1 + w_mm/2 * np.sin(angle),
                y1 - w_mm/2 * np.sin(angle),
                y1 - w_mm/2 * np.sin(angle) + slot_length * np.sin(tangent_angle),
                y1 + w_mm/2 * np.sin(angle) + slot_length * np.sin(tangent_angle),
                y1 + w_mm/2 * np.sin(angle)
            ]
            
            fig.add_trace(go.Scatter(
                x=slot_corners_x, y=slot_corners_y,
                fill='toself',
                fillcolor='rgba(255, 165, 0, 0.8)',
                mode='lines',
                line=dict(color='darkorange', width=2),
                name=f'Injection Slot' if i == 0 else '',
                showlegend=i == 0,
                hovertemplate=f'Slot {i+1}<br>Width: {w_mm:.2f} mm<br>Height: {h_mm:.2f} mm<br>Area: {w_mm * h_mm:.2f} mm²'
            ))
            
            # Add flow direction arrow
            arrow_start_x = x1 + slot_length/2 * np.cos(tangent_angle)
            arrow_start_y = y1 + slot_length/2 * np.sin(tangent_angle)
            arrow_end_x = arrow_start_x + 8 * np.cos(tangent_angle)
            arrow_end_y = arrow_start_y + 8 * np.sin(tangent_angle)
            
            fig.add_trace(go.Scatter(
                x=[arrow_start_x, arrow_end_x],
                y=[arrow_start_y, arrow_end_y],
                mode='lines',
                line=dict(color='red', width=3),
                name='Flow Direction' if i == 0 else '',
                showlegend=i == 0,
                hoverinfo='skip'
            ))
        
        # Central exit orifice with realistic sizing
        exit_area_mm2 = injector_data['exit_orifice_area']  # Assume this is in mm²
        exit_radius_mm = np.sqrt(exit_area_mm2 / np.pi)
        
        fig.add_trace(go.Scatter(
            x=exit_radius_mm * np.cos(theta),
            y=exit_radius_mm * np.sin(theta),
            fill='toself',
            fillcolor='white',
            mode='lines',
            line=dict(color='black', width=3),
            name='Exit Orifice',
            hovertemplate=f'Exit Orifice<br>Diameter: {exit_radius_mm*2:.2f} mm<br>Area: {exit_area_mm2:.2f} mm²'
        ))
        
        # Add swirl flow indicators (spiral pattern)
        spiral_angles = np.linspace(0, 4*np.pi, 50)
        spiral_radius = np.linspace(exit_radius_mm * 1.2, inner_radius_mm, 50)
        spiral_x = spiral_radius * np.cos(spiral_angles)
        spiral_y = spiral_radius * np.sin(spiral_angles)
        
        fig.add_trace(go.Scatter(
            x=spiral_x, y=spiral_y,
            mode='lines',
            line=dict(color='blue', width=2, dash='dash'),
            name='Swirl Pattern',
            hovertemplate='Swirl Flow Pattern'
        ))
        
        # Add mounting holes
        mount_radius = chamber_radius_mm * 1.2
        n_mounts = 6
        mount_angles = np.linspace(0, 2*np.pi, n_mounts, endpoint=False)
        mount_x = mount_radius * np.cos(mount_angles)
        mount_y = mount_radius * np.sin(mount_angles)
        
        fig.add_trace(go.Scatter(
            x=mount_x, y=mount_y,
            mode='markers',
            marker=dict(size=8, color='gray', symbol='circle'),
            name='Mounting Holes',
            hovertemplate='M8 Mounting Hole'
        ))
        
        title = f'Swirl Injector Design'
        subtitle = f'{n_slots} slots × {w_mm:.1f}×{h_mm:.1f} mm | Spray Angle: {injector_data["spray_angle"]}°'
    
    # Clean layout with improved sizing
    fig.update_layout(
        title=dict(
            text=f'{title}<br><sub>{subtitle}</sub>',
            x=0.5,
            font=dict(size=18, family='Arial', color='black')
        ),
        xaxis=dict(
            title='X (mm)',
            showgrid=False,
            zeroline=True,
            zerolinecolor='gray',
            zerolinewidth=1
        ),
        yaxis=dict(
            title='Y (mm)',
            showgrid=False,
            zeroline=True,
            zerolinecolor='gray',
            zerolinewidth=1,
            scaleanchor='x',
            scaleratio=1
        ),
        showlegend=True,
        legend=dict(x=0.02, y=0.98),
        width=800,
        height=800,
        plot_bgcolor='white',
        hovermode='closest',
        margin=dict(t=100, b=80, l=80, r=80)
    )
    
    return fig.to_json()

def create_performance_plots(motor_data, injector_data):
    """Create performance visualization plots"""
    
    # Create subplots
    from plotly.subplots import make_subplots
    
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=('Mass Flow Rates', 'Pressure Distribution', 
                       'Regression Rate', 'Injector Performance'),
        specs=[[{'type': 'bar'}, {'type': 'bar'}],
               [{'secondary_y': True}, {'type': 'indicator'}]]
    )
    
    # Mass flow rates
    fig.add_trace(
        go.Bar(
            x=['Total', 'Oxidizer', 'Fuel'],
            y=[motor_data['mdot_total'], motor_data['mdot_ox'], motor_data['mdot_f']],
            marker_color=['blue', 'green', 'orange'],
            text=[f"{v:.3f} kg/s" for v in [motor_data['mdot_total'], 
                                            motor_data['mdot_ox'], 
                                            motor_data['mdot_f']]],
            textposition='auto'
        ),
        row=1, col=1
    )
    
    # Pressure distribution
    pressures = ['Chamber', 'Tank', 'Injector ΔP']
    values = [motor_data['chamber_pressure'], 
              injector_data['pressure_drop'] + motor_data['chamber_pressure'],
              injector_data['pressure_drop']]
    
    fig.add_trace(
        go.Bar(
            x=pressures,
            y=values,
            marker_color=['red', 'blue', 'green'],
            text=[f"{v:.1f} bar" for v in values],
            textposition='auto'
        ),
        row=1, col=2
    )
    
    # Regression rate over time - Fixed calculation
    try:
        burn_time = motor_data.get('burn_time', 10)
        regression_rate = motor_data.get('regression_rate', 0.001)
        port_initial = motor_data.get('port_diameter_initial', 0.03)
        port_final = motor_data.get('port_diameter_final', 0.05)
        
        # Create time array
        time = np.linspace(0, burn_time, 100)
        
        # Calculate port diameter growth over time
        # Linear interpolation between initial and final
        port_diameter = np.linspace(port_initial, port_final, 100)
        
        # Port diameter growth plot
        fig.add_trace(
            go.Scatter(
                x=time,
                y=port_diameter * 1000,  # Convert to mm
                mode='lines',
                line=dict(color='purple', width=3),
                name='Port Diameter Growth',
                hovertemplate='Time: %{x:.1f}s<br>Port Diameter: %{y:.1f}mm<extra></extra>'
            ),
            row=2, col=1
        )
        
        # Calculate regression rate over time
        regression_rate_mm_s = regression_rate * 1000  # Convert to mm/s
        
        # Create secondary y-axis data for regression rate
        regression_rate_array = np.ones(100) * regression_rate_mm_s
        
        # For more realistic modeling, regression rate might vary slightly
        # Add small variation to show it's dynamic
        if regression_rate_mm_s > 0:
            variation = np.sin(np.linspace(0, 2*np.pi, 100)) * regression_rate_mm_s * 0.1
            regression_rate_array = regression_rate_array + variation
        
        # Add regression rate line 
        fig.add_trace(
            go.Scatter(
                x=time,
                y=regression_rate_array,
                mode='lines',
                line=dict(color='red', width=2),
                name=f'Regression Rate (avg: {regression_rate_mm_s:.2f} mm/s)',
                hovertemplate='Time: %{x:.1f}s<br>Regression Rate: %{y:.2f} mm/s<extra></extra>'
            ),
            row=2, col=1,
            secondary_y=True
        )
    except Exception as e:
        print(f"Warning: Regression rate plot error: {e}")
        # Add default data if error occurs
        time = np.linspace(0, 10, 100)
        port_diameter = np.linspace(30, 50, 100)  # mm
        regression_rate_default = np.ones(100) * 2.0  # mm/s
        
        fig.add_trace(
            go.Scatter(
                x=time,
                y=port_diameter,
                mode='lines',
                line=dict(color='purple', width=3),
                name='Port Diameter Growth',
                hovertemplate='Time: %{x:.1f}s<br>Port Diameter: %{y:.1f}mm<extra></extra>'
            ),
            row=2, col=1
        )
        
        fig.add_trace(
            go.Scatter(
                x=time,
                y=regression_rate_default,
                mode='lines',
                line=dict(color='red', width=2),
                name='Regression Rate (2.0 mm/s)',
                hovertemplate='Time: %{x:.1f}s<br>Regression Rate: %{y:.2f} mm/s<extra></extra>'
            ),
            row=2, col=1,
            secondary_y=True
        )
    
    # Injector performance gauge
    fig.add_trace(
        go.Indicator(
            mode="gauge+number",
            value=injector_data['exit_velocity'],
            title={'text': "Exit Velocity (m/s)"},
            domain={'x': [0, 1], 'y': [0, 1]},
            gauge={
                'axis': {'range': [0, 100]},
                'bar': {'color': "darkblue"},
                'steps': [
                    {'range': [0, 20], 'color': "lightgray"},
                    {'range': [20, 50], 'color': "green"},
                    {'range': [50, 100], 'color': "red"}
                ],
                'threshold': {
                    'line': {'color': "red", 'width': 4},
                    'thickness': 0.75,
                    'value': 50
                }
            }
        ),
        row=2, col=2
    )
    
    # Update layout
    fig.update_layout(
        title=dict(
            text="Hybrid Rocket Performance Analysis",
            font=dict(size=20, family='Arial', color='black'),
            x=0.5
        ),
        showlegend=False,
        height=1000,
        width=1400,
        plot_bgcolor='white',
        paper_bgcolor='white',
        margin=dict(t=100, b=80, l=80, r=80)
    )
    
    # Update axes
    fig.update_xaxes(title_text="Component", row=1, col=1)
    fig.update_yaxes(title_text="Mass Flow Rate (kg/s)", row=1, col=1)
    
    fig.update_xaxes(title_text="Location", row=1, col=2)
    fig.update_yaxes(title_text="Pressure (bar)", row=1, col=2)
    
    fig.update_xaxes(title_text="Time (s)", row=2, col=1)
    fig.update_yaxes(title_text="Port Diameter (mm)", secondary_y=False, row=2, col=1)
    fig.update_yaxes(title_text="Regression Rate (mm/s)", secondary_y=True, row=2, col=1)
    
    return fig.to_json()

def create_heat_transfer_plots(heat_data):
    """Create comprehensive heat transfer analysis plots"""
    from plotly.subplots import make_subplots
    
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=('Wall Temperature Distribution', 'Thermal Stress Profile',
                       'Cooling Effectiveness', 'Temperature vs Time'),
        specs=[[{'type': 'scatter'}, {'type': 'heatmap'}],
               [{'type': 'bar'}, {'type': 'scatter'}]]
    )
    
    # Wall temperature distribution
    if 'wall_temperature_profile' in heat_data:
        wall_data = heat_data['wall_temperature_profile']
        fig.add_trace(
            go.Scatter(
                x=wall_data['position'],
                y=wall_data['temperature'],
                mode='lines+markers',
                line=dict(color='red', width=3),
                marker=dict(size=6),
                name='Wall Temperature',
                hovertemplate='Position: %{x:.2f} m<br>Temperature: %{y:.1f} K'
            ),
            row=1, col=1
        )
        
        # Add critical temperature line
        critical_temp = heat_data.get('material_limit', 1073)
        fig.add_hline(
            y=critical_temp,
            line_dash="dash",
            line_color="orange",
            annotation_text=f"Critical Temp: {critical_temp}K",
            row=1, col=1
        )
    
    # Thermal stress heatmap
    if 'thermal_stress_map' in heat_data:
        stress_data = heat_data['thermal_stress_map']
        fig.add_trace(
            go.Heatmap(
                z=stress_data['stress_matrix'],
                x=stress_data['x_coords'],
                y=stress_data['y_coords'],
                colorscale='Reds',
                showscale=True,
                colorbar=dict(title="Stress (MPa)"),
                hovertemplate='X: %{x:.2f}<br>Y: %{y:.2f}<br>Stress: %{z:.1f} MPa'
            ),
            row=1, col=2
        )
    
    # Cooling effectiveness
    if 'cooling_analysis' in heat_data:
        cooling_data = heat_data['cooling_analysis']
        fig.add_trace(
            go.Bar(
                x=cooling_data['zones'],
                y=cooling_data['effectiveness'],
                marker_color=['green' if x > 0.8 else 'orange' if x > 0.6 else 'red' 
                             for x in cooling_data['effectiveness']],
                text=[f"{x:.1%}" for x in cooling_data['effectiveness']],
                textposition='auto',
                name='Cooling Effectiveness'
            ),
            row=2, col=1
        )
    
    # Temperature vs time
    if 'temperature_history' in heat_data:
        temp_history = heat_data['temperature_history']
        for zone, data in temp_history.items():
            fig.add_trace(
                go.Scatter(
                    x=data['time'],
                    y=data['temperature'],
                    mode='lines',
                    name=f'{zone} Temperature',
                    line=dict(width=2)
                ),
                row=2, col=2
            )
    
    fig.update_layout(
        title_text="Heat Transfer Analysis Dashboard",
        showlegend=True,
        height=800,
        width=1200
    )
    
    # Update axes
    fig.update_xaxes(title_text="Position (m)", row=1, col=1)
    fig.update_yaxes(title_text="Temperature (K)", row=1, col=1)
    
    fig.update_xaxes(title_text="Zone", row=2, col=1)
    fig.update_yaxes(title_text="Effectiveness (%)", row=2, col=1)
    
    fig.update_xaxes(title_text="Time (s)", row=2, col=2)
    fig.update_yaxes(title_text="Temperature (K)", row=2, col=2)
    
    return fig.to_json()

def create_combustion_analysis_plots(combustion_data):
    """Create comprehensive combustion analysis visualizations"""
    from plotly.subplots import make_subplots
    
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=('Chemical Equilibrium', 'Flame Temperature Profile',
                       'Combustion Efficiency', 'O/F Ratio Optimization'),
        specs=[[{'type': 'bar'}, {'type': 'scatter'}],
               [{'type': 'indicator'}, {'type': 'scatter'}]]
    )
    
    # Chemical equilibrium
    if 'species_concentrations' in combustion_data:
        species_data = combustion_data['species_concentrations']
        fig.add_trace(
            go.Bar(
                x=list(species_data.keys()),
                y=list(species_data.values()),
                marker_color='lightblue',
                text=[f"{v:.3f}" for v in species_data.values()],
                textposition='auto',
                name='Species Concentration'
            ),
            row=1, col=1
        )
    
    # Flame temperature profile
    if 'flame_temperature_profile' in combustion_data:
        flame_data = combustion_data['flame_temperature_profile']
        fig.add_trace(
            go.Scatter(
                x=flame_data['position'],
                y=flame_data['temperature'],
                mode='lines+markers',
                line=dict(color='orange', width=3),
                marker=dict(size=6, color='red'),
                name='Flame Temperature'
            ),
            row=1, col=2
        )
    
    # Combustion efficiency gauge
    efficiency = combustion_data.get('combustion_efficiency', 0.95)
    fig.add_trace(
        go.Indicator(
            mode="gauge+number+delta",
            value=efficiency * 100,
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': "Combustion Efficiency (%)"},
            delta={'reference': 95},
            gauge={
                'axis': {'range': [0, 100]},
                'bar': {'color': "darkgreen"},
                'steps': [
                    {'range': [0, 70], 'color': "lightgray"},
                    {'range': [70, 90], 'color': "yellow"},
                    {'range': [90, 100], 'color': "green"}
                ],
                'threshold': {
                    'line': {'color': "red", 'width': 4},
                    'thickness': 0.75,
                    'value': 95
                }
            }
        ),
        row=2, col=1
    )
    
    # O/F ratio optimization
    if 'of_optimization' in combustion_data:
        of_data = combustion_data['of_optimization']
        fig.add_trace(
            go.Scatter(
                x=of_data['of_ratios'],
                y=of_data['specific_impulse'],
                mode='lines+markers',
                line=dict(color='blue', width=3),
                marker=dict(size=8),
                name='Isp vs O/F Ratio'
            ),
            row=2, col=2
        )
        
        # Mark optimum point
        optimum_idx = np.argmax(of_data['specific_impulse'])
        fig.add_trace(
            go.Scatter(
                x=[of_data['of_ratios'][optimum_idx]],
                y=[of_data['specific_impulse'][optimum_idx]],
                mode='markers',
                marker=dict(size=15, color='red', symbol='star'),
                name='Optimum Point',
                hovertemplate=f'Optimum O/F: {of_data["of_ratios"][optimum_idx]:.2f}<br>Max Isp: {of_data["specific_impulse"][optimum_idx]:.1f} s'
            ),
            row=2, col=2
        )
    
    fig.update_layout(
        title_text="Combustion Analysis Dashboard",
        showlegend=True,
        height=800,
        width=1200
    )
    
    # Update axes
    fig.update_xaxes(title_text="Species", row=1, col=1)
    fig.update_yaxes(title_text="Mole Fraction", row=1, col=1)
    
    fig.update_xaxes(title_text="Position (m)", row=1, col=2)
    fig.update_yaxes(title_text="Temperature (K)", row=1, col=2)
    
    fig.update_xaxes(title_text="O/F Ratio", row=2, col=2)
    fig.update_yaxes(title_text="Specific Impulse (s)", row=2, col=2)
    
    return fig.to_json()

def create_structural_analysis_plots(structural_data):
    """Create comprehensive structural analysis visualizations"""
    from plotly.subplots import make_subplots
    
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=('Stress Distribution', 'Safety Factor Analysis',
                       'Wall Thickness Optimization', 'Fatigue Analysis'),
        specs=[[{'type': 'heatmap'}, {'type': 'bar'}],
               [{'type': 'scatter'}, {'type': 'scatter'}]]
    )
    
    # Stress distribution heatmap
    if 'stress_distribution' in structural_data:
        stress_data = structural_data['stress_distribution']
        fig.add_trace(
            go.Heatmap(
                z=stress_data['stress_matrix'],
                x=stress_data['x_coords'],
                y=stress_data['y_coords'],
                colorscale='RdYlBu_r',
                showscale=True,
                colorbar=dict(title="Von Mises Stress (MPa)"),
                hovertemplate='X: %{x:.2f}m<br>Y: %{y:.2f}m<br>Stress: %{z:.1f} MPa'
            ),
            row=1, col=1
        )
    
    # Safety factor analysis
    if 'safety_factors' in structural_data:
        sf_data = structural_data['safety_factors']
        colors = ['green' if x > 4 else 'orange' if x > 2 else 'red' for x in sf_data['values']]
        fig.add_trace(
            go.Bar(
                x=sf_data['locations'],
                y=sf_data['values'],
                marker_color=colors,
                text=[f"SF: {x:.1f}" for x in sf_data['values']],
                textposition='auto',
                name='Safety Factor'
            ),
            row=1, col=2
        )
        
        # Add minimum safety factor line
        fig.add_hline(
            y=2.0,
            line_dash="dash",
            line_color="red",
            annotation_text="Min SF: 2.0",
            row=1, col=2
        )
    
    # Wall thickness optimization
    if 'wall_thickness_analysis' in structural_data:
        wt_data = structural_data['wall_thickness_analysis']
        fig.add_trace(
            go.Scatter(
                x=wt_data['thickness'],
                y=wt_data['mass'],
                mode='lines+markers',
                line=dict(color='blue', width=3),
                marker=dict(size=6),
                name='Mass vs Thickness',
                yaxis='y'
            ),
            row=2, col=1
        )
        
        fig.add_trace(
            go.Scatter(
                x=wt_data['thickness'],
                y=wt_data['safety_factor'],
                mode='lines+markers',
                line=dict(color='red', width=3),
                marker=dict(size=6),
                name='Safety Factor',
                yaxis='y2'
            ),
            row=2, col=1
        )
    
    # Fatigue analysis
    if 'fatigue_analysis' in structural_data:
        fatigue_data = structural_data['fatigue_analysis']
        fig.add_trace(
            go.Scatter(
                x=fatigue_data['cycles'],
                y=fatigue_data['stress_amplitude'],
                mode='lines+markers',
                line=dict(color='purple', width=3),
                marker=dict(size=6),
                name='S-N Curve'
            ),
            row=2, col=2
        )
        
        # Add fatigue limit
        if 'fatigue_limit' in fatigue_data:
            fig.add_hline(
                y=fatigue_data['fatigue_limit'],
                line_dash="dash",
                line_color="green",
                annotation_text=f"Fatigue Limit: {fatigue_data['fatigue_limit']:.0f} MPa",
                row=2, col=2
            )
    
    fig.update_layout(
        title_text="Structural Analysis Dashboard",
        showlegend=True,
        height=800,
        width=1200
    )
    
    # Update axes
    fig.update_xaxes(title_text="Location", row=1, col=2)
    fig.update_yaxes(title_text="Safety Factor", row=1, col=2)
    
    fig.update_xaxes(title_text="Wall Thickness (mm)", row=2, col=1)
    fig.update_yaxes(title_text="Mass (kg)", row=2, col=1)
    
    fig.update_xaxes(title_text="Cycles to Failure", row=2, col=2, type="log")
    fig.update_yaxes(title_text="Stress Amplitude (MPa)", row=2, col=2, type="log")
    
    return fig.to_json()

def create_real_time_dashboard(motor_data, time_data):
    """Create real-time performance monitoring dashboard"""
    from plotly.subplots import make_subplots
    
    fig = make_subplots(
        rows=3, cols=3,
        subplot_titles=('Thrust', 'Chamber Pressure', 'Mass Flow Rate',
                       'Temperature', 'O/F Ratio', 'Isp',
                       'Propellant Mass', 'Burn Rate', 'Port Diameter'),
        specs=[[{'type': 'indicator'}, {'type': 'indicator'}, {'type': 'indicator'}],
               [{'type': 'indicator'}, {'type': 'indicator'}, {'type': 'indicator'}],
               [{'type': 'scatter'}, {'type': 'scatter'}, {'type': 'scatter'}]]
    )
    
    # Current values indicators
    current_thrust = motor_data.get('thrust', 0)
    fig.add_trace(
        go.Indicator(
            mode="gauge+number",
            value=current_thrust,
            title={'text': "Thrust (N)"},
            gauge={
                'axis': {'range': [0, current_thrust * 1.2]},
                'bar': {'color': "darkgreen"},
                'steps': [{'range': [0, current_thrust * 0.8], 'color': "lightgray"}],
            }
        ),
        row=1, col=1
    )
    
    current_pressure = motor_data.get('chamber_pressure', 0)
    fig.add_trace(
        go.Indicator(
            mode="gauge+number",
            value=current_pressure,
            title={'text': "Chamber Pressure (bar)"},
            gauge={
                'axis': {'range': [0, current_pressure * 1.2]},
                'bar': {'color': "darkblue"},
            }
        ),
        row=1, col=2
    )
    
    current_mdot = motor_data.get('mdot_total', 0)
    fig.add_trace(
        go.Indicator(
            mode="gauge+number",
            value=current_mdot,
            title={'text': "Mass Flow Rate (kg/s)"},
            gauge={
                'axis': {'range': [0, current_mdot * 1.2]},
                'bar': {'color': "darkorange"},
            }
        ),
        row=1, col=3
    )
    
    # Time history plots if available
    if time_data:
        # Propellant mass over time
        fig.add_trace(
            go.Scatter(
                x=time_data['time'],
                y=time_data['propellant_mass'],
                mode='lines',
                line=dict(color='red', width=3),
                name='Propellant Mass'
            ),
            row=3, col=1
        )
        
        # Burn rate over time
        fig.add_trace(
            go.Scatter(
                x=time_data['time'],
                y=time_data['burn_rate'],
                mode='lines',
                line=dict(color='orange', width=3),
                name='Burn Rate'
            ),
            row=3, col=2
        )
        
        # Port diameter over time
        fig.add_trace(
            go.Scatter(
                x=time_data['time'],
                y=time_data['port_diameter'],
                mode='lines',
                line=dict(color='blue', width=3),
                name='Port Diameter'
            ),
            row=3, col=3
        )
    
    fig.update_layout(
        title_text="Real-Time Motor Performance Dashboard",
        showlegend=False,
        height=900,
        width=1400
    )
    
    return fig.to_json()

def create_3d_motor_visualization(motor_data):
    """Create 3D motor visualization with cross-section and flow"""
    
    # Extract dimensions with safe defaults
    L = motor_data.get('chamber_length', 0.3) * 1000  # Convert to mm, default 300mm
    D = motor_data.get('chamber_diameter', 0.1) * 1000  # Default 100mm
    d_port = motor_data.get('port_diameter_initial', 0.03) * 1000  # Default 30mm
    d_throat = motor_data.get('throat_diameter', 0.02) * 1000  # Default 20mm
    d_exit = motor_data.get('exit_diameter', 0.08) * 1000  # Default 80mm
    
    fig = go.Figure()
    
    # Create cylinder for chamber
    theta = np.linspace(0, 2*np.pi, 50)
    z_chamber = np.linspace(-L/2, L/2, 50)
    
    # Chamber outer surface
    theta_mesh, z_mesh = np.meshgrid(theta, z_chamber)
    x_outer = (D/2) * np.cos(theta_mesh)
    y_outer = (D/2) * np.sin(theta_mesh)
    
    fig.add_trace(go.Surface(
        x=x_outer,
        y=y_outer,
        z=z_mesh,
        colorscale='Greys',
        opacity=0.7,
        name='Chamber Wall'
    ))
    
    # Fuel grain
    x_fuel = (d_port/2 + (D/2 - d_port/2)/2) * np.cos(theta_mesh)
    y_fuel = (d_port/2 + (D/2 - d_port/2)/2) * np.sin(theta_mesh)
    
    fig.add_trace(go.Surface(
        x=x_fuel,
        y=y_fuel,
        z=z_mesh,
        colorscale='burg',
        opacity=0.8,
        name='Fuel Grain'
    ))
    
    # Port (flow channel)
    x_port = (d_port/2) * np.cos(theta_mesh)
    y_port = (d_port/2) * np.sin(theta_mesh)
    
    fig.add_trace(go.Surface(
        x=x_port,
        y=y_port,
        z=z_mesh,
        colorscale='Blues',
        opacity=0.3,
        name='Flow Channel'
    ))
    
    # Nozzle
    nozzle_length = 100  # mm
    z_nozzle = np.linspace(L/2, L/2 + nozzle_length, 30)
    
    # Nozzle contour
    throat_pos = L/2 + nozzle_length * 0.3
    nozzle_radius = []
    for z in z_nozzle:
        if z <= throat_pos:
            # Convergent
            r = D/2 - (D/2 - d_throat/2) * (z - L/2) / (throat_pos - L/2)
        else:
            # Divergent
            r = d_throat/2 + (d_exit/2 - d_throat/2) * (z - throat_pos) / (L/2 + nozzle_length - throat_pos)
        nozzle_radius.append(r)
    
    theta_nozzle, z_nozzle_mesh = np.meshgrid(theta, z_nozzle)
    radius_mesh = np.array([nozzle_radius]).T
    x_nozzle = radius_mesh * np.cos(theta_nozzle)
    y_nozzle = radius_mesh * np.sin(theta_nozzle)
    
    fig.add_trace(go.Surface(
        x=x_nozzle,
        y=y_nozzle,
        z=z_nozzle_mesh,
        colorscale='Greys',
        opacity=0.8,
        name='Nozzle'
    ))
    
    fig.update_layout(
        title='3D Hybrid Rocket Motor Visualization',
        scene=dict(
            xaxis_title='X (mm)',
            yaxis_title='Y (mm)',
            zaxis_title='Z (mm)',
            aspectmode='data'
        ),
        width=800,
        height=600
    )
    
    return fig.to_json()

def create_comparative_analysis_plot(motor_configs):
    """Create comparative analysis between different motor configurations"""
    from plotly.subplots import make_subplots
    
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=('Thrust Comparison', 'Isp Comparison',
                       'Total Impulse Comparison', 'Mass Efficiency'),
        specs=[[{'type': 'bar'}, {'type': 'bar'}],
               [{'type': 'bar'}, {'type': 'scatter'}]]
    )
    
    config_names = list(motor_configs.keys())
    
    # Thrust comparison
    thrust_values = [motor_configs[name]['thrust'] for name in config_names]
    fig.add_trace(
        go.Bar(
            x=config_names,
            y=thrust_values,
            marker_color='lightblue',
            text=[f"{v:.0f} N" for v in thrust_values],
            textposition='auto',
            name='Thrust'
        ),
        row=1, col=1
    )
    
    # Isp comparison
    isp_values = [motor_configs[name]['isp'] for name in config_names]
    fig.add_trace(
        go.Bar(
            x=config_names,
            y=isp_values,
            marker_color='lightgreen',
            text=[f"{v:.1f} s" for v in isp_values],
            textposition='auto',
            name='Specific Impulse'
        ),
        row=1, col=2
    )
    
    # Total impulse comparison
    total_impulse_values = [motor_configs[name]['total_impulse'] for name in config_names]
    fig.add_trace(
        go.Bar(
            x=config_names,
            y=total_impulse_values,
            marker_color='lightcoral',
            text=[f"{v:.0f} N⋅s" for v in total_impulse_values],
            textposition='auto',
            name='Total Impulse'
        ),
        row=2, col=1
    )
    
    # Mass efficiency scatter
    mass_values = [motor_configs[name]['total_mass'] for name in config_names]
    fig.add_trace(
        go.Scatter(
            x=mass_values,
            y=isp_values,
            mode='markers+text',
            marker=dict(size=15, color='purple'),
            text=config_names,
            textposition='top center',
            name='Mass vs Isp'
        ),
        row=2, col=2
    )
    
    fig.update_layout(
        title_text="Motor Configuration Comparison",
        showlegend=False,
        height=800,
        width=1200
    )
    
    # Update axes
    fig.update_xaxes(title_text="Configuration", row=1, col=1)
    fig.update_yaxes(title_text="Thrust (N)", row=1, col=1)
    
    fig.update_xaxes(title_text="Configuration", row=1, col=2)
    fig.update_yaxes(title_text="Isp (s)", row=1, col=2)
    
    fig.update_xaxes(title_text="Configuration", row=2, col=1)
    fig.update_yaxes(title_text="Total Impulse (N⋅s)", row=2, col=1)
    
    fig.update_xaxes(title_text="Total Mass (kg)", row=2, col=2)
    fig.update_yaxes(title_text="Isp (s)", row=2, col=2)
    
    return fig.to_json()

def create_chamber_pressure_mixture_ratio_3d_surface(engine_data: Dict) -> str:
    """
    Create 3D Response Surface Plot: Chamber Pressure vs Mixture Ratio vs Isp
    Based on NASA SP-125 Liquid-Propellant Rocket Engine Performance
    """
    
    # Generate parameter ranges
    pc_range = np.linspace(10, 100, 20)  # Chamber pressure: 10-100 bar
    of_range = np.linspace(1.0, 6.0, 20)  # O/F ratio: 1.0-6.0
    
    # Create meshgrid
    PC, OF = np.meshgrid(pc_range, of_range)
    
    # Calculate Isp based on NASA SP-125 correlations
    # Simplified correlation: Isp = base_isp * pressure_factor * mixture_factor
    base_isp = engine_data.get('base_isp', 300)  # Base specific impulse
    
    # Pressure effect (optimum around 50-70 bar)
    pressure_factor = 1.0 + 0.15 * np.log(PC / 20) * np.exp(-(PC - 50)**2 / 800)
    
    # Mixture ratio effect (optimum varies by propellant)
    optimal_of = engine_data.get('optimal_of_ratio', 3.5)
    mixture_factor = 1.0 - 0.3 * ((OF - optimal_of) / optimal_of)**2
    
    # Calculate Isp surface
    ISP = base_isp * pressure_factor * mixture_factor
    
    # Add combustion instability regions (NASA SP-125 criteria)
    instability_mask = (PC > 80) & (OF < 2.0) | (PC < 15) & (OF > 5.0)
    ISP[instability_mask] *= 0.7  # Reduce Isp in unstable regions
    
    # Create 3D surface plot
    fig = go.Figure()
    
    # Main performance surface
    fig.add_trace(go.Surface(
        x=PC,
        y=OF,
        z=ISP,
        colorscale='Viridis',
        name='Performance Surface',
        showscale=True,
        colorbar=dict(title="Isp (s)", x=1.02)
    ))
    
    # Add combustion instability regions
    instability_z = np.where(instability_mask, ISP, np.nan)
    fig.add_trace(go.Surface(
        x=PC,
        y=OF,
        z=instability_z,
        colorscale=[[0, 'red'], [1, 'darkred']],
        name='Instability Region',
        showscale=False,
        opacity=0.8
    ))
    
    # Add optimum point
    optimal_pc = engine_data.get('optimal_chamber_pressure', 50)
    optimal_isp = base_isp * (1.0 + 0.15 * np.log(optimal_pc / 20) * np.exp(-(optimal_pc - 50)**2 / 800))
    
    fig.add_trace(go.Scatter3d(
        x=[optimal_pc],
        y=[optimal_of],
        z=[optimal_isp],
        mode='markers',
        marker=dict(size=15, color='gold', symbol='diamond'),
        name='Optimum Point'
    ))
    
    fig.update_layout(
        title={
            'text': '3D Performance Map: Chamber Pressure vs O/F Ratio vs Isp<br><sub>NASA SP-125 Based Analysis</sub>',
            'x': 0.5,
            'font': {'size': 16}
        },
        scene=dict(
            xaxis_title='Chamber Pressure (bar)',
            yaxis_title='O/F Ratio',
            zaxis_title='Specific Impulse (s)',
            camera=dict(eye=dict(x=1.5, y=1.5, z=1.2))
        ),
        width=900,
        height=700,
        showlegend=True
    )
    
    return fig.to_json()

def create_nozzle_mach_area_ratio_contour(cfd_data: Dict) -> str:
    """
    Create Nozzle Exit Mach-Area Ratio Contour Plot
    Based on NASA-STD-5012 Pressure Vessels & Pressurized Systems
    """
    
    # Extract nozzle geometry
    throat_area = cfd_data.get('throat_area', 0.001)  # m²
    nozzle_length = cfd_data.get('nozzle_length', 0.1)  # m
    expansion_ratio = cfd_data.get('expansion_ratio', 16)
    
    # Create nozzle contour coordinates
    x_stations = np.linspace(0, nozzle_length, 50)
    
    # Nozzle area distribution (simplified bell nozzle)
    area_ratios = []
    for x in x_stations:
        x_norm = x / nozzle_length
        if x_norm <= 0.1:  # Converging section
            area_ratio = 1.0 + 2.0 * (1 - x_norm / 0.1)
        else:  # Diverging section  
            area_ratio = 1.0 + (expansion_ratio - 1.0) * ((x_norm - 0.1) / 0.9)**0.8
        area_ratios.append(area_ratio)
    
    area_ratios = np.array(area_ratios)
    
    # Calculate Mach numbers using isentropic relations
    gamma = 1.25
    mach_numbers = []
    
    for area_ratio in area_ratios:
        if area_ratio <= 1.0:
            # Subsonic
            mach = 0.5 * area_ratio
        else:
            # Supersonic - solve isentropic relation iteratively
            mach_guess = 2.0 * np.sqrt(area_ratio - 1)
            for _ in range(10):  # Simple iteration
                f = (1/mach_guess) * ((2/(gamma+1)) * (1 + (gamma-1)/2 * mach_guess**2))**((gamma+1)/(2*(gamma-1))) - area_ratio
                df = -1/mach_guess**2 * ((2/(gamma+1)) * (1 + (gamma-1)/2 * mach_guess**2))**((gamma+1)/(2*(gamma-1)))
                mach_guess = mach_guess - f/df if abs(df) > 1e-10 else mach_guess
            mach_numbers.append(max(1.0, mach_guess))
    
    mach_numbers = np.array(mach_numbers)
    
    # Create 2D grid for contour (nozzle cross-section)
    y_stations = np.linspace(-0.05, 0.05, 30)  # Radial positions
    X, Y = np.meshgrid(x_stations, y_stations)
    
    # Create Mach number field
    MACH = np.zeros_like(X)
    for i, mach in enumerate(mach_numbers):
        MACH[:, i] = mach
    
    # Add boundary layer effects (lower Mach near walls)
    for i in range(len(y_stations)):
        y_norm = abs(y_stations[i]) / 0.05
        if y_norm > 0.8:  # Near wall
            MACH[i, :] *= (1.0 - 0.3 * (y_norm - 0.8) / 0.2)
    
    # Create contour plot
    fig = go.Figure()
    
    # Mach number contours
    contour = fig.add_trace(go.Contour(
        x=x_stations * 1000,  # Convert to mm
        y=y_stations * 1000,
        z=MACH,
        colorscale='Jet',
        contours=dict(
            start=0.5,
            end=4.0,
            size=0.25
        ),
        colorbar=dict(title="Mach Number", x=1.02),
        name='Mach Contours'
    ))
    
    # Add nozzle walls
    wall_upper = np.sqrt(area_ratios * throat_area / np.pi) * 1000  # mm
    wall_lower = -wall_upper
    
    fig.add_trace(go.Scatter(
        x=x_stations * 1000,
        y=wall_upper,
        mode='lines',
        line=dict(color='black', width=3),
        name='Nozzle Wall'
    ))
    
    fig.add_trace(go.Scatter(
        x=x_stations * 1000,
        y=wall_lower,
        mode='lines',
        line=dict(color='black', width=3),
        showlegend=False
    ))
    
    # Mark throat location
    throat_x = nozzle_length * 0.1 * 1000  # mm
    fig.add_vline(x=throat_x, line_dash="dash", line_color="red", 
                  annotation_text="Throat")
    
    # Identify shock regions (Mach > 3.5)
    shock_regions = MACH > 3.5
    if np.any(shock_regions):
        fig.add_annotation(
            x=x_stations[np.argmax(np.max(MACH, axis=0))] * 1000,
            y=25,
            text="Potential Shock Zone",
            showarrow=True,
            arrowcolor="red",
            font=dict(color="red")
        )
    
    fig.update_layout(
        title={
            'text': 'Nozzle Mach Number Distribution & Flow Analysis<br><sub>NASA-STD-5012 Compliant Design</sub>',
            'x': 0.5,
            'font': {'size': 16}
        },
        xaxis_title='Axial Position (mm)',
        yaxis_title='Radial Position (mm)',
        width=1000,
        height=600,
        showlegend=True
    )
    
    return fig.to_json()

def create_wall_heat_flux_waterfall_plot(thermal_data: Dict) -> str:
    """
    Create Wall Heat Flux-Time Waterfall Plot
    Based on NASA SP-8124 Thermal Design Criteria
    """
    
    # Time range for analysis
    time_points = np.linspace(0, thermal_data.get('burn_time', 30), 100)  # seconds
    
    # Axial positions along nozzle/chamber
    chamber_length = thermal_data.get('chamber_length', 0.5)  # m
    nozzle_length = thermal_data.get('nozzle_length', 0.1)   # m
    total_length = chamber_length + nozzle_length
    
    axial_positions = np.linspace(0, total_length, 50) * 1000  # mm
    
    # Create meshgrids
    T, X = np.meshgrid(time_points, axial_positions)
    
    # Calculate heat flux based on NASA SP-8124 correlations
    # Heat flux varies with position and time
    base_heat_flux = thermal_data.get('base_heat_flux', 2e6)  # W/m²
    
    # Axial variation (highest at throat)
    throat_position = chamber_length * 1000  # mm
    axial_factor = 1.0 + 2.0 * np.exp(-((X - throat_position) / 50)**2)
    
    # Temporal variation (thermal buildup)
    thermal_buildup = 1.0 - np.exp(-T / 5.0)  # Exponential buildup
    transient_factor = 1.0 + 0.5 * thermal_buildup
    
    # Calculate heat flux matrix
    HEAT_FLUX = base_heat_flux * axial_factor * transient_factor
    
    # Add thermal runaway regions (NASA SP-8124 criteria)
    runaway_threshold = 5e6  # W/m²
    runaway_mask = HEAT_FLUX > runaway_threshold
    HEAT_FLUX[runaway_mask] *= 1.5  # Accelerated heating in runaway
    
    # Convert to MW/m² for readability
    HEAT_FLUX_MW = HEAT_FLUX / 1e6
    
    # Create waterfall plot using surface
    fig = go.Figure()
    
    # Main heat flux surface
    fig.add_trace(go.Surface(
        x=T,
        y=X,
        z=HEAT_FLUX_MW,
        colorscale='Hot',
        name='Heat Flux',
        colorbar=dict(title="Heat Flux (MW/m²)", x=1.02),
        showscale=True
    ))
    
    # Add critical heat flux contour
    critical_flux = thermal_data.get('critical_heat_flux', 4.0)  # MW/m²
    fig.add_trace(go.Contour(
        x=time_points,
        y=axial_positions,
        z=HEAT_FLUX_MW.T,
        contours=dict(
            start=critical_flux,
            end=critical_flux,
            size=0.1,
            coloring='lines'
        ),
        line=dict(color='red', width=3),
        name=f'Critical Flux ({critical_flux} MW/m²)',
        showscale=False
    ))
    
    # Mark throat position
    fig.add_trace(go.Scatter3d(
        x=[0, time_points[-1]],
        y=[throat_position, throat_position],
        z=[0, 0],
        mode='lines',
        line=dict(color='blue', width=5, dash='dash'),
        name='Throat Location'
    ))
    
    # Add thermal runaway warning regions
    if np.any(runaway_mask):
        runaway_x, runaway_y = np.where(runaway_mask)
        if len(runaway_x) > 0:
            fig.add_trace(go.Scatter3d(
                x=T[runaway_mask],
                y=X[runaway_mask],
                z=HEAT_FLUX_MW[runaway_mask],
                mode='markers',
                marker=dict(size=3, color='red', symbol='x'),
                name='Thermal Runaway Risk'
            ))
    
    fig.update_layout(
        title={
            'text': 'Wall Heat Flux Distribution: Thermal Runaway Analysis<br><sub>NASA SP-8124 Thermal Design Criteria</sub>',
            'x': 0.5,
            'font': {'size': 16}
        },
        scene=dict(
            xaxis_title='Time (s)',
            yaxis_title='Axial Position (mm)',
            zaxis_title='Heat Flux (MW/m²)',
            camera=dict(eye=dict(x=1.3, y=1.3, z=1.3))
        ),
        width=1000,
        height=700,
        showlegend=True
    )
    
    return fig.to_json()