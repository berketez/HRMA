"""
PDF Report Generator for HRMA System
Professional motor analysis reports with charts and data
"""

import os
import io
import base64
from datetime import datetime
from typing import Dict, List, Optional, Any
import json

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

from jinja2 import Environment, BaseLoader
import plotly.graph_objects as go
import plotly.io as pio


class PDFReportGenerator:
    """Generate professional PDF reports for rocket motor analysis"""
    
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.setup_custom_styles()
        
    def setup_custom_styles(self):
        """Setup custom paragraph styles"""
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            spaceAfter=30,
            alignment=TA_CENTER,
            textColor=colors.darkblue
        ))
        
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=16,
            spaceAfter=12,
            spaceBefore=20,
            textColor=colors.darkred,
            borderWidth=1,
            borderColor=colors.darkred,
            borderPadding=5
        ))
        
        self.styles.add(ParagraphStyle(
            name='AnalysisData',
            parent=self.styles['Normal'],
            fontSize=10,
            leftIndent=20,
            fontName='Helvetica'
        ))

    @staticmethod
    def _fmt(value, pattern: str = '{:.1f}', missing: str = 'N/A') -> str:
        """Sayısal değeri güvenli biçimlendirir; eksik/geçersizse 'N/A'.

        Rapor katmanı sabit/uydurma değer basmaz (Dalga 2): analiz sonucu
        yoksa alan 'N/A' görünür — eski sabit SF 4.0 tarzı dolgu YOK.
        """
        try:
            number = float(value)
        except (TypeError, ValueError):
            return missing
        if number != number or number in (float('inf'), float('-inf')):
            return missing
        return pattern.format(number)

    def generate_motor_analysis_report(self, motor_data: Dict, analysis_results: Dict, 
                                     charts: List[str], report_type: str = 'complete') -> bytes:
        """
        Generate complete motor analysis PDF report
        
        Args:
            motor_data: Motor configuration and parameters
            analysis_results: Analysis calculations and results
            charts: List of base64 encoded chart images
            report_type: 'complete', 'summary', or 'technical'
            
        Returns:
            PDF file as bytes
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, 
                              rightMargin=72, leftMargin=72,
                              topMargin=72, bottomMargin=18)
        
        story = []
        
        # Title Page
        story.extend(self._create_title_page(motor_data, report_type))
        story.append(PageBreak())
        
        # Executive Summary
        if report_type in ['complete', 'summary']:
            story.extend(self._create_executive_summary(analysis_results))
            story.append(PageBreak())
        
        # Motor Configuration
        story.extend(self._create_motor_configuration(motor_data))
        story.append(PageBreak())
        
        # Analysis Results
        story.extend(self._create_analysis_results(analysis_results))
        
        # Charts and Visualizations
        if charts:
            story.append(PageBreak())
            story.extend(self._create_charts_section(charts))
        
        # Technical Appendix
        if report_type == 'complete':
            story.append(PageBreak())
            story.extend(self._create_technical_appendix(motor_data, analysis_results))
        
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()

    def _create_title_page(self, motor_data: Dict, report_type: str) -> List:
        """Create title page"""
        story = []
        
        # Main title
        motor_type = motor_data.get('motor_type', 'Unknown').title()
        title = f"{motor_type} Motor Analysis Report"
        story.append(Paragraph(title, self.styles['CustomTitle']))
        story.append(Spacer(1, 0.5*inch))
        
        # Motor name/designation
        motor_name = motor_data.get('motor_name', 'Unnamed Motor')
        story.append(Paragraph(f"Motor Designation: <b>{motor_name}</b>", 
                             self.styles['Heading2']))
        story.append(Spacer(1, 0.3*inch))
        
        # Report info table
        report_info = [
            ['Report Type:', report_type.title()],
            ['Generated:', datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
            ['Motor Type:', motor_type],
            ['Analysis Software:', 'UZAYTEK HRMA v2.0'],
            ['Standards:', 'NASA SP-125, NASA-STD-5012, NASA SP-8124']
        ]
        
        table = Table(report_info, colWidths=[2*inch, 3*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('BACKGROUND', (1, 0), (1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        story.append(table)
        story.append(Spacer(1, 1*inch))
        
        # Disclaimer
        disclaimer = """
        <b>DISCLAIMER:</b> This analysis is for educational and research purposes only. 
        Actual rocket motor design and testing should be performed by qualified engineers 
        following all applicable safety standards and regulations. The authors assume no 
        responsibility for the use of this analysis in actual motor design or testing.
        """
        story.append(Paragraph(disclaimer, self.styles['Normal']))
        
        return story

    def _create_executive_summary(self, analysis_results: Dict) -> List:
        """Create executive summary section"""
        story = []
        
        story.append(Paragraph("Executive Summary", self.styles['SectionHeader']))
        
        # Performance highlights
        performance = analysis_results.get('performance', {})
        thrust = performance.get('thrust', 0)
        isp = performance.get('specific_impulse', 0)
        burn_time = performance.get('burn_time', 0)
        # Gerçek toplam impuls varsa onu kullan; yoksa F*t_b yaklaşımı
        total_impulse = performance.get('total_impulse')
        if total_impulse is None:
            total_impulse = thrust * burn_time

        summary_text = f"""
        This report presents a comprehensive analysis of the rocket motor performance
        and characteristics. Key performance metrics include:

        • Maximum Thrust: {self._fmt(thrust)} N
        • Specific Impulse: {self._fmt(isp)} s
        • Burn Time: {self._fmt(burn_time)} s
        • Total Impulse: {self._fmt(total_impulse)} N⋅s

        The analysis was conducted using NASA-standard methodologies and includes
        thermal, structural, and performance evaluations.
        """
        
        story.append(Paragraph(summary_text, self.styles['Normal']))
        story.append(Spacer(1, 0.3*inch))
        
        # Safety assessment
        safety = analysis_results.get('safety', {})
        safety_status = "ACCEPTABLE" if safety.get('overall_rating', 0) > 7 else "REVIEW REQUIRED"
        
        safety_text = f"""
        <b>Safety Assessment: {safety_status}</b><br/>
        Overall Safety Rating: {safety.get('overall_rating', 0):.1f}/10<br/>
        Critical Issues: {len(safety.get('critical_issues', []))}
        """
        
        story.append(Paragraph(safety_text, self.styles['Normal']))
        
        return story

    def _create_motor_configuration(self, motor_data: Dict) -> List:
        """Create motor configuration section"""
        story = []
        
        story.append(Paragraph("Motor Configuration", self.styles['SectionHeader']))
        
        # Configuration table
        config_data = []
        
        # Basic parameters
        config_data.extend([
            ['Motor Type', motor_data.get('motor_type', 'N/A')],
            ['Propellant Type', motor_data.get('propellant_type', 'N/A')],
            ['Chamber Diameter', f"{motor_data.get('chamber_diameter', 0):.2f} mm"],
            ['Chamber Length', f"{motor_data.get('chamber_length', 0):.2f} mm"],
            ['Throat Diameter', f"{motor_data.get('throat_diameter', 0):.2f} mm"],
            ['Exit Diameter', f"{motor_data.get('exit_diameter', 0):.2f} mm"],
            ['Expansion Ratio', f"{motor_data.get('expansion_ratio', 0):.1f}"]
        ])
        
        # Add motor-specific parameters
        if motor_data.get('motor_type') == 'solid':
            config_data.extend([
                ['Grain Configuration', motor_data.get('grain_type', 'N/A')],
                ['Propellant Mass', f"{motor_data.get('propellant_mass', 0):.2f} kg"],
                ['Grain Density', f"{motor_data.get('grain_density', 0):.0f} kg/m³"]
            ])
        elif motor_data.get('motor_type') == 'liquid':
            config_data.extend([
                ['Oxidizer', motor_data.get('oxidizer_type', 'N/A')],
                ['Fuel', motor_data.get('fuel_type', 'N/A')],
                ['O/F Ratio', f"{motor_data.get('of_ratio', 0):.2f}"],
                ['Chamber Pressure', f"{motor_data.get('chamber_pressure', 0):.1f} bar"]
            ])
        
        table = Table(config_data, colWidths=[2.5*inch, 2.5*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightblue),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        story.append(table)
        
        return story

    def _create_analysis_results(self, analysis_results: Dict) -> List:
        """Create detailed analysis results section"""
        story = []
        
        story.append(Paragraph("Analysis Results", self.styles['SectionHeader']))
        
        # Performance Analysis
        performance = analysis_results.get('performance', {})
        story.append(Paragraph("Performance Metrics", self.styles['Heading3']))
        
        perf_data = [
            ['Parameter', 'Value', 'Unit'],
            ['Maximum Thrust', self._fmt(performance.get('thrust')), 'N'],
            ['Specific Impulse', self._fmt(performance.get('specific_impulse')), 's'],
            ['Chamber Pressure', self._fmt(performance.get('chamber_pressure')), 'bar'],
            ['Exit Velocity', self._fmt(performance.get('exit_velocity')), 'm/s'],
            ['Mass Flow Rate', self._fmt(performance.get('mass_flow_rate'), '{:.3f}'), 'kg/s'],
            ['Burn Time', self._fmt(performance.get('burn_time')), 's'],
            ['Total Impulse', self._fmt(performance.get('total_impulse')), 'N⋅s']
        ]
        
        perf_table = Table(perf_data, colWidths=[2*inch, 1.5*inch, 1*inch])
        perf_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey])
        ]))
        
        story.append(perf_table)
        story.append(Spacer(1, 0.2*inch))
        
        # Thermal Analysis — gerçek Bartz sonuçları (app.py bölüm besleyicisi
        # motor.heat_transfer_analysis'ten doldurur; uydurma değer yok).
        thermal = analysis_results.get('thermal', {})
        if thermal:
            story.append(Paragraph("Thermal Analysis", self.styles['Heading3']))

            thermal_data = [
                ['Parameter', 'Value', 'Unit'],
                ['Max Wall Temperature', self._fmt(thermal.get('max_wall_temp')), 'K'],
                ['Heat Flux', self._fmt(thermal.get('heat_flux'), '{:.2f}'), 'MW/m²'],
                ['Cooling Requirement', self._fmt(thermal.get('cooling_req')), 'kW']
            ]
            # İsteğe bağlı gerçek-analiz satırları (varsa eklenir)
            if thermal.get('adiabatic_wall_temp') is not None:
                thermal_data.append(['Adiabatic Wall Temperature',
                                     self._fmt(thermal.get('adiabatic_wall_temp')), 'K'])
            if thermal.get('gas_side_coefficient') is not None:
                thermal_data.append(['Gas-Side Coefficient (Bartz)',
                                     self._fmt(thermal.get('gas_side_coefficient'), '{:.0f}'),
                                     'W/m²K'])

            thermal_table = Table(thermal_data, colWidths=[2*inch, 1.5*inch, 1*inch])
            thermal_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.red),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))

            story.append(thermal_table)

        # Structural Analysis — GERÇEK emniyet faktörleri (Dalga 2).
        # Eski davranış: rapor katmanına hiç yapısal bölüm girmiyordu ve
        # dışa aktarımlar sabit SF (4.0) yazabiliyordu. Artık yalnız gerçek
        # analiz değerleri basılır; veri yoksa bölüm hiç oluşmaz.
        structural = analysis_results.get('structural', {})
        if structural:
            story.append(Spacer(1, 0.2*inch))
            story.append(Paragraph("Structural Analysis", self.styles['Heading3']))

            structural_data = [['Parameter', 'Value', 'Unit']]

            def _add_structural_row(label, key, pattern='{:.2f}', unit='-'):
                if structural.get(key) is not None:
                    structural_data.append(
                        [label, self._fmt(structural.get(key), pattern), unit]
                    )

            _add_structural_row('Safety Factor (pressure only)', 'safety_factor_pressure')
            _add_structural_row('Safety Factor (pressure + thermal)', 'safety_factor_total')
            _add_structural_row('Minimum Safety Factor (all modes)', 'min_safety_factor')
            _add_structural_row('Von Mises Stress', 'von_mises_stress_MPa', unit='MPa')
            _add_structural_row('Hoop Stress (total)', 'hoop_stress_MPa', unit='MPa')
            if structural.get('status'):
                structural_data.append(['Structural Status', str(structural['status']), '-'])
            if structural.get('risk_level'):
                structural_data.append(['Risk Level', str(structural['risk_level']), '-'])

            if len(structural_data) > 1:
                structural_table = Table(structural_data,
                                         colWidths=[2.5*inch, 1.5*inch, 0.75*inch])
                structural_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 0), (-1, -1), 10),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1),
                     [colors.white, colors.lightgrey])
                ]))
                story.append(structural_table)

        return story

    def _create_charts_section(self, charts: List[str]) -> List:
        """Create charts and visualizations section"""
        story = []
        
        story.append(Paragraph("Analysis Charts", self.styles['SectionHeader']))
        
        for i, chart_data in enumerate(charts):
            try:
                # Decode base64 image
                image_data = base64.b64decode(chart_data)
                image_buffer = io.BytesIO(image_data)
                
                # Create image
                img = Image(image_buffer)
                img.drawHeight = 4*inch
                img.drawWidth = 6*inch
                
                story.append(Paragraph(f"Chart {i+1}", self.styles['Heading3']))
                story.append(img)
                story.append(Spacer(1, 0.2*inch))
                
            except Exception as e:
                story.append(Paragraph(f"Chart {i+1}: Error loading image - {str(e)}", 
                                     self.styles['Normal']))
        
        return story

    def _create_technical_appendix(self, motor_data: Dict, analysis_results: Dict) -> List:
        """Create technical appendix with formulas and references"""
        story = []
        
        story.append(Paragraph("Technical Appendix", self.styles['SectionHeader']))
        
        # Analysis methodology
        story.append(Paragraph("Analysis Methodology", self.styles['Heading3']))
        methodology_text = """
        This analysis employs NASA-standard methodologies for rocket motor performance 
        evaluation:
        
        • NASA SP-125: Liquid-Propellant Rocket Engine Performance
        • NASA-STD-5012: Pressure Vessels & Pressurized Systems
        • NASA SP-8124: Thermal Design Criteria
        
        Key equations used in the analysis include isentropic flow relations, 
        combustion thermodynamics, and heat transfer correlations.
        """
        story.append(Paragraph(methodology_text, self.styles['Normal']))
        
        # Assumptions
        story.append(Paragraph("Analysis Assumptions", self.styles['Heading3']))
        assumptions = [
            "• Steady-state combustion conditions",
            "• Isentropic expansion through nozzle",
            "• Uniform propellant properties",
            "• Perfect gas behavior for combustion products",
            "• Adiabatic combustion chamber walls (where applicable)"
        ]
        
        for assumption in assumptions:
            story.append(Paragraph(assumption, self.styles['Normal']))
        
        return story

    def export_plotly_chart_to_image(self, plotly_json: str, format: str = 'png') -> str:
        """Convert Plotly chart to base64 image"""
        try:
            fig_dict = json.loads(plotly_json)
            fig = go.Figure(fig_dict)
            
            # Export as image
            img_bytes = pio.to_image(fig, format=format, width=800, height=600)
            img_base64 = base64.b64encode(img_bytes).decode()
            
            return img_base64
            
        except Exception as e:
            print(f"Error converting chart: {str(e)}")
            return ""

    def generate_quick_summary_report(self, motor_data: Dict, analysis_results: Dict) -> bytes:
        """Generate a quick summary report (2-3 pages)"""
        return self.generate_motor_analysis_report(
            motor_data, analysis_results, [], 'summary'
        )

    def generate_technical_report(self, motor_data: Dict, analysis_results: Dict, 
                                charts: List[str]) -> bytes:
        """Generate a complete technical report with all charts"""
        return self.generate_motor_analysis_report(
            motor_data, analysis_results, charts, 'complete'
        )