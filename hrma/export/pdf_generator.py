"""
PDF Report Generator for HRMA System
Professional motor analysis reports with charts and data
"""

import os
import io
import base64
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
import json

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.graphics.shapes import Drawing


def _hrma_version() -> str:
    """Rapor künyesindeki yazılım sürümü — tek kaynaktan (hrma/__init__.py).

    Eski kod sabit 'v2.0' yazıyordu (2026-07-16 denetim bulgusu); artık
    sürüm bump'ı raporlara otomatik yansır.
    """
    try:
        from hrma import __version__
        return __version__
    except Exception:
        return 'unknown'
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

from jinja2 import Environment, BaseLoader
import plotly.graph_objects as go
import plotly.io as pio

# --------------------------------------------------------------------------
# Grafik gömme sabitleri — TEK tanım noktası (CLAUDE.md kural 11).
# Eski kod 800x600 ölçeksiz PNG üretiyordu; A4 sayfa genişliğine gerilince
# baskıda bulanıklaşıyordu ("grafiğin çözünürlüğü çok kötü" şikayeti).
# --------------------------------------------------------------------------
CHART_EXPORT_WIDTH_PX = 1600     # kaleido render genişliği [px]
CHART_EXPORT_HEIGHT_PX = 1000    # kaleido render yüksekliği [px]
CHART_EXPORT_SCALE = 2           # cihaz piksel oranı -> 3200x2000 gerçek px
# A4 (595.27 pt) eksi 72 pt sol + 72 pt sağ kenar boşluğu = 451.27 pt.
CHART_MAX_WIDTH_INCH = 6.1       # güvenli sayfa içi genişlik [inch]
CHART_MAX_HEIGHT_INCH = 4.4      # tek grafik için üst yükseklik sınırı [inch]

# PDF beyaz zeminlidir; arayüzün koyu tema figürleri olduğu gibi gömülürse
# koyu kutu + koyu yazı okunamaz hale gelir. Dönüşümden ÖNCE tek noktada
# aydınlık palete çevrilir.
CHART_PRINT_PAPER_COLOR = '#ffffff'
CHART_PRINT_FONT_COLOR = '#111111'
CHART_PRINT_GRID_COLOR = '#d5d9de'
CHART_PRINT_LINE_COLOR = '#333333'

# Grafik gömülemediğinde basılan not. DİKKAT: 'Error loading image' metni
# bilinçli olarak kullanılmaz — kullanıcıya hata yığını değil, durum
# bildirilir (tests/test_pdf_charts.py bu metni gözler).
CHART_UNAVAILABLE_NOTE = (
    'Chart unavailable - this figure could not be rendered on the server '
    '(image renderer not available or chart data not recognised).'
)

# --------------------------------------------------------------------------
# Uzunluk birimi çözümü — TEK tanım noktası.
# Hibrit yolunda motor ölçüleri METRE, katı yolunda MİLİMETRE gelir; eski kod
# ikisini de ':.2f mm' ile basıyor ve hibritte "Chamber Diameter 0.10 mm" gibi
# fiziksel olarak imkânsız satırlar üretiyordu (2026-07-19 denetimi).
# Kural: motorun EN BÜYÜK uzunluk alanı bu eşikten küçükse girdiler metredir.
# Milimetrede en büyük ölçü daima > 5 (5 mm'lik motor yok); metrede ise 5 m'yi
# aşan bir hazne/lüle boyu roket motoru pratiğinde bulunmaz.
LENGTH_UNIT_METRE_MAX = 5.0

# Güvenlik puanı kabul eşiği (0-10 ölçeği) — tek tanım noktası.
SAFETY_RATING_ACCEPTABLE = 7.0
LENGTH_KEYS = ('chamber_diameter', 'chamber_length', 'throat_diameter',
               'exit_diameter', 'nozzle_length', 'grain_length')


def _is_dark(color) -> bool:
    """'#rrggbb' / 'rgb(r,g,b)' rengi koyu mu? Çözülemezse False."""
    try:
        text = str(color).strip().lower()
        if text.startswith('#'):
            text = text[1:]
            if len(text) == 3:
                text = ''.join(c * 2 for c in text)
            if len(text) < 6:
                return False
            r, g, b = (int(text[i:i + 2], 16) for i in (0, 2, 4))
        elif text.startswith('rgb'):
            parts = text[text.find('(') + 1:text.find(')')].split(',')
            r, g, b = (float(p) for p in parts[:3])
        else:
            return False
        # ITU-R BT.601 luma
        return (0.299 * r + 0.587 * g + 0.114 * b) < 128.0
    except Exception:
        return False


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

    @staticmethod
    def _length_scale_to_mm(motor_data: Dict) -> Tuple[float, str]:
        """Girdi uzunluk birimini çözer; (mm'ye çarpan, birim_adı) döner.

        Açık bildirim (`length_units`) varsa ona uyulur; yoksa motorun en büyük
        uzunluk alanına bakılır (bkz. LENGTH_UNIT_METRE_MAX).
        """
        declared = str((motor_data or {}).get('length_units') or '').lower()
        if declared in ('m', 'metre', 'meter'):
            return 1000.0, 'm'
        if declared in ('mm', 'millimetre', 'millimeter'):
            return 1.0, 'mm'

        largest = 0.0
        for key in LENGTH_KEYS:
            try:
                value = float((motor_data or {}).get(key))
            except (TypeError, ValueError):
                continue
            if value == value and value > largest:
                largest = value
        if largest <= 0.0:
            return 1.0, 'mm'  # ölçü yok; dönüşüm uygulanmaz
        return (1000.0, 'm') if largest < LENGTH_UNIT_METRE_MAX else (1.0, 'mm')

    def _fmt_length_mm(self, motor_data: Dict, key: str,
                       pattern: str = '{:.2f}') -> str:
        """Uzunluğu daima mm olarak biçimlendirir (birim otomatik çözülür)."""
        scale, _unit = self._length_scale_to_mm(motor_data)
        try:
            value = float(motor_data.get(key))
        except (TypeError, ValueError):
            return 'N/A'
        if value != value or value in (float('inf'), float('-inf')):
            return 'N/A'
        return pattern.format(value * scale) + ' mm'

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
            ['Analysis Software:', f'UZAYTEK HRMA v{_hrma_version()}'],
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
        
        # Safety assessment — YALNIZ gerçek güvenlik analizi varsa puan basılır.
        # Eski kod 'safety' anahtarı hiç yokken bile bölümü basıyor, 0.0/10 ve
        # "REVIEW REQUIRED" yazıyordu; kullanıcı hiç çalıştırılmamış bir
        # analizin motorunu sıfır puanladığını sanıyordu (2026-07-19 denetimi).
        safety = analysis_results.get('safety') or {}
        rating = safety.get('overall_rating')
        try:
            rating = float(rating)
        except (TypeError, ValueError):
            rating = None
        if rating is None or rating != rating:
            rating = None

        if rating is None:
            safety_text = (
                '<b>Safety Assessment: NOT EVALUATED IN THIS RUN</b><br/>'
                'No safety analysis result was supplied with this report, so no '
                'safety rating is reported. Run the safety analysis to include '
                'this section.'
            )
        else:
            safety_status = ("ACCEPTABLE" if rating > SAFETY_RATING_ACCEPTABLE
                             else "REVIEW REQUIRED")
            safety_text = f"""
        <b>Safety Assessment: {safety_status}</b><br/>
        Overall Safety Rating: {rating:.1f}/10
        (acceptance threshold {SAFETY_RATING_ACCEPTABLE:.0f}/10)<br/>
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
        
        # Ölçüler daima mm basılır; girdi birimi otomatik çözülür ve tabloda
        # açıkça yazılır (hibrit yolu metre, katı yolu mm gönderiyor).
        _scale, input_unit = self._length_scale_to_mm(motor_data)

        # Basic parameters
        config_data.extend([
            ['Motor Type', motor_data.get('motor_type')
             or 'N/A (not reported by solver)'],
            ['Propellant Type', motor_data.get('propellant_type')
             or 'N/A (not reported by solver)'],
            ['Chamber Diameter', self._fmt_length_mm(motor_data, 'chamber_diameter')],
            ['Chamber Length', self._fmt_length_mm(motor_data, 'chamber_length')],
            ['Throat Diameter', self._fmt_length_mm(motor_data, 'throat_diameter')],
            ['Exit Diameter', self._fmt_length_mm(motor_data, 'exit_diameter')],
            ['Expansion Ratio', self._fmt(motor_data.get('expansion_ratio'))],
            ['Dimension units', f'mm (input interpreted as {input_unit})']
        ])

        # Motora özgü satırlar VERİ VARLIĞINA göre eklenir; eskiden yalnız
        # motor_type == 'solid'/'liquid' ise basılıyordu, hibrit sonucunda bu
        # anahtar olmadığı için O/F, oksitleyici ve yakıt satırları hiç
        # görünmüyordu (2026-07-19 denetimi).
        if motor_data.get('grain_type') or motor_data.get('grain_density'):
            config_data.extend([
                ['Grain Configuration', motor_data.get('grain_type', 'N/A')],
                ['Propellant Mass', self._fmt(motor_data.get('propellant_mass'),
                                              '{:.2f}') + ' kg'],
                ['Grain Density', self._fmt(motor_data.get('grain_density'),
                                            '{:.0f}') + ' kg/m3']
            ])
        if (motor_data.get('oxidizer_type') or motor_data.get('fuel_type')
                or motor_data.get('of_ratio') is not None):
            config_data.extend([
                ['Oxidizer', motor_data.get('oxidizer_type', 'N/A')],
                ['Fuel', motor_data.get('fuel_type', 'N/A')],
                ['O/F Ratio', self._fmt(motor_data.get('of_ratio'), '{:.2f}')],
                ['Chamber Pressure', self._fmt(motor_data.get('chamber_pressure'))
                 + ' bar']
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

    # ------------------------------------------------------------------
    # Grafik boru hattı
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_plotly_payload(chart_data) -> Optional[Dict]:
        """Girdi Plotly figür tanımı ise sözlüğünü, değilse None döndürür.

        Arayüz grafikleri JSON.stringify({data, layout}) olarak gönderiyor
        (templates/*.html PDF toplayıcıları). Eski kod bunu base64 PNG
        sanıp b64decode ediyordu; çözülen çöp reportlab'e verilince her
        grafik hata satırına düşüyordu — kök neden buydu.
        """
        if isinstance(chart_data, dict):
            payload = chart_data
        else:
            if isinstance(chart_data, bytes):
                try:
                    chart_data = chart_data.decode('utf-8')
                except Exception:
                    return None
            if not isinstance(chart_data, str):
                return None
            text = chart_data.strip()
            if not text.startswith('{'):
                return None
            try:
                payload = json.loads(text)
            except Exception:
                return None
        if not isinstance(payload, dict):
            return None
        if 'data' in payload or 'layout' in payload:
            return payload
        return None

    @staticmethod
    def _apply_print_theme(fig: 'go.Figure') -> 'go.Figure':
        """Koyu tema figürünü baskı (beyaz zemin) paletine çevirir.

        Tek nokta: hem rapor bölümü hem tekil grafik dışa aktarımı buradan
        geçer, böylece PDF'lerde tema tutarlıdır.
        """
        fig.update_layout(
            template='plotly_white',
            paper_bgcolor=CHART_PRINT_PAPER_COLOR,
            plot_bgcolor=CHART_PRINT_PAPER_COLOR,
            font_color=CHART_PRINT_FONT_COLOR,
        )
        axis_style = dict(
            color=CHART_PRINT_FONT_COLOR,
            gridcolor=CHART_PRINT_GRID_COLOR,
            zerolinecolor=CHART_PRINT_GRID_COLOR,
            linecolor=CHART_PRINT_LINE_COLOR,
        )
        # 2B eksenler (3B sahnelerde bu çağrılar sessizce etkisizdir).
        try:
            fig.update_xaxes(**axis_style)
            fig.update_yaxes(**axis_style)
        except Exception:
            pass
        # Lejant / başlık / dipnot: koyu zemin varsayımıyla açık renkli
        # yazılmış olabilir — okunur koyu renge çekilir.
        try:
            legend = fig.layout.legend
            if legend is not None:
                fig.update_layout(legend=dict(
                    bgcolor='rgba(255,255,255,0.85)',
                    bordercolor=CHART_PRINT_GRID_COLOR,
                    font=dict(color=CHART_PRINT_FONT_COLOR)))
        except Exception:
            pass
        try:
            for ann in (fig.layout.annotations or ()):
                if ann.font is None or ann.font.color is None \
                        or not _is_dark(ann.font.color):
                    ann.font.color = CHART_PRINT_FONT_COLOR
        except Exception:
            pass
        try:
            scene = fig.layout.scene
            if scene is not None:
                fig.update_layout(scene=dict(
                    xaxis=dict(**axis_style), yaxis=dict(**axis_style),
                    zaxis=dict(**axis_style),
                    bgcolor=CHART_PRINT_PAPER_COLOR))
        except Exception:
            pass
        return fig

    @staticmethod
    def _chart_title(payload: Optional[Dict], index: int) -> str:
        """Figür başlığı varsa onu, yoksa 'Chart N' döndürür."""
        try:
            title = (payload or {}).get('layout', {}).get('title')
            if isinstance(title, dict):
                title = title.get('text')
            title = str(title or '').strip()
            if title:
                return title
        except Exception:
            pass
        return f'Chart {index}'

    def _chart_to_png_bytes(self, chart_data) -> Optional[bytes]:
        """Grafik girdisini PNG baytlarına çevirir; başarısızsa None.

        İki biçim desteklenir (geriye dönük uyum korunur):
          1. Plotly figür JSON'u  -> kaleido ile yüksek çözünürlüklü PNG
          2. base64 kodlu PNG/JPEG -> olduğu gibi çözülür
        kaleido kurulu değilse (paketli sürümde eksik olabilir) çökme
        YOKTUR: None döner, çağıran bölüm 'chart unavailable' notu basar.
        """
        payload = self._parse_plotly_payload(chart_data)
        if payload is not None:
            try:
                fig = go.Figure(payload)
                self._apply_print_theme(fig)
                return pio.to_image(
                    fig, format='png',
                    width=CHART_EXPORT_WIDTH_PX,
                    height=CHART_EXPORT_HEIGHT_PX,
                    scale=CHART_EXPORT_SCALE)
            except Exception as exc:  # kaleido yok / figür bozuk
                print(f"Chart render skipped: {exc}")
                return None
        # base64 gövde (data URI öneki olabilir)
        try:
            if isinstance(chart_data, bytes):
                raw = chart_data
                if raw[:4] in (b'\x89PNG', b'\xff\xd8\xff\xe0'):
                    return raw
                chart_data = raw.decode('utf-8')
            text = str(chart_data).strip()
            if text.startswith('data:') and ',' in text:
                text = text.split(',', 1)[1]
            decoded = base64.b64decode(text, validate=False)
            if not decoded:
                return None
            # Geçerli bir raster mı? (PNG / JPEG / GIF imzaları)
            if decoded[:8].startswith(b'\x89PNG') or decoded[:3] == b'\xff\xd8\xff' \
                    or decoded[:3] == b'GIF':
                return decoded
            return None
        except Exception:
            return None

    @staticmethod
    def _fit_image(png_bytes: bytes) -> Optional[Image]:
        """PNG'yi en-boy oranını koruyarak sayfa içine sığdırır.

        Eski kod 6x4 inch'e ZORLUYORDU; kare olmayan figürler eziliyor,
        geniş figürler kenar boşluğuna taşıyordu.
        """
        try:
            from reportlab.lib.utils import ImageReader
            buffer = io.BytesIO(png_bytes)
            width_px, height_px = ImageReader(buffer).getSize()
            if not width_px or not height_px:
                return None
            aspect = float(height_px) / float(width_px)
            draw_width = CHART_MAX_WIDTH_INCH * inch
            draw_height = draw_width * aspect
            if draw_height > CHART_MAX_HEIGHT_INCH * inch:
                draw_height = CHART_MAX_HEIGHT_INCH * inch
                draw_width = draw_height / aspect
            buffer.seek(0)
            return Image(buffer, width=draw_width, height=draw_height)
        except Exception:
            return None

    def _create_charts_section(self, charts: List[str]) -> List:
        """Create charts and visualizations section"""
        story = []

        story.append(Paragraph("Analysis Charts", self.styles['SectionHeader']))

        for i, chart_data in enumerate(charts):
            payload = self._parse_plotly_payload(chart_data)
            heading = self._chart_title(payload, i + 1)
            story.append(Paragraph(heading, self.styles['Heading3']))

            png_bytes = self._chart_to_png_bytes(chart_data)
            img = self._fit_image(png_bytes) if png_bytes else None
            if img is None:
                story.append(Paragraph(CHART_UNAVAILABLE_NOTE,
                                       self.styles['Normal']))
                story.append(Spacer(1, 0.15 * inch))
                continue

            story.append(img)
            story.append(Spacer(1, 0.2 * inch))

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

    def export_plotly_chart_to_image(self, plotly_json, format: str = 'png',
                                     width: int = CHART_EXPORT_WIDTH_PX,
                                     height: int = CHART_EXPORT_HEIGHT_PX,
                                     scale: int = CHART_EXPORT_SCALE) -> str:
        """Convert a Plotly chart to a base64 image string.

        Çözünürlük sabitleri modül başında tanımlıdır (baskı kalitesi);
        çağıran özel bir boyut isterse parametreyle ezebilir. Figür koyu
        temadan baskı temasına burada da çevrilir (tek nokta).
        """
        try:
            fig_dict = (plotly_json if isinstance(plotly_json, dict)
                        else json.loads(plotly_json))
            fig = go.Figure(fig_dict)
            self._apply_print_theme(fig)

            img_bytes = pio.to_image(fig, format=format, width=width,
                                     height=height, scale=scale)
            return base64.b64encode(img_bytes).decode()

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