from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

NAVY = colors.HexColor('#111C33')
BLUE = colors.HexColor('#2563EB')
CYAN = colors.HexColor('#06B6D4')
INK = colors.HexColor('#172033')
MUTED = colors.HexColor('#667085')
LINE = colors.HexColor('#E3E8F1')
SOFT = colors.HexColor('#F5F7FB')
ORANGE = colors.HexColor('#F97316')
GREEN = colors.HexColor('#059669')


def _safe(value):
    return escape(str(value if value not in (None, '') else '—'))


def _footer(canvas, doc):
    canvas.saveState()
    width, _ = A4
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(18 * mm, 13 * mm, width - 18 * mm, 13 * mm)
    canvas.setFont('Helvetica', 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 8 * mm, 'Análise de dois vínculos · Relatório auxiliar')
    canvas.drawRightString(width - 18 * mm, 8 * mm, f'Página {doc.page}')
    canvas.restoreState()


def _styles():
    base = getSampleStyleSheet()
    return {
        'title': ParagraphStyle('ReportTitle', parent=base['Title'], fontName='Helvetica-Bold', fontSize=24, leading=28, textColor=colors.white, spaceAfter=4),
        'subtitle': ParagraphStyle('ReportSubtitle', parent=base['Normal'], fontName='Helvetica', fontSize=9.5, leading=13, textColor=colors.HexColor('#D7E6F7')),
        'h1': ParagraphStyle('H1', parent=base['Heading1'], fontName='Helvetica-Bold', fontSize=14, leading=18, textColor=INK, spaceBefore=10, spaceAfter=8),
        'h2': ParagraphStyle('H2', parent=base['Heading2'], fontName='Helvetica-Bold', fontSize=10.5, leading=13, textColor=INK, spaceBefore=8, spaceAfter=5),
        'body': ParagraphStyle('Body', parent=base['BodyText'], fontName='Helvetica', fontSize=8.5, leading=12, textColor=INK),
        'muted': ParagraphStyle('Muted', parent=base['BodyText'], fontName='Helvetica', fontSize=8, leading=11, textColor=MUTED),
        'card_label': ParagraphStyle('CardLabel', parent=base['Normal'], fontName='Helvetica-Bold', fontSize=7.3, leading=9, textColor=MUTED),
        'card_value': ParagraphStyle('CardValue', parent=base['Normal'], fontName='Helvetica-Bold', fontSize=19, leading=22, textColor=INK),
        'table_head': ParagraphStyle('TableHead', parent=base['Normal'], fontName='Helvetica-Bold', fontSize=7.5, leading=9, textColor=colors.white),
        'table_cell': ParagraphStyle('TableCell', parent=base['Normal'], fontName='Helvetica', fontSize=7.5, leading=9, textColor=INK),
        'table_cell_bold': ParagraphStyle('TableCellBold', parent=base['Normal'], fontName='Helvetica-Bold', fontSize=7.5, leading=9, textColor=INK),
    }


def build_pdf_report(resultado: dict) -> bytes:
    """Renderiza o relatório consolidado em um PDF A4 profissional."""
    styles = _styles()
    resumo = resultado.get('resumo', {})
    periodo = resultado.get('periodo', {})
    servidor = resultado.get('servidor') or 'Servidor não identificado'
    criterios = ', '.join(resultado.get('criterio_codigos_trabalho', [])) or 'nenhum código selecionado'
    coincidencias = resumo.get('dias_coincidentes_lista', [])
    horario_overlap = resumo.get('dias_sobrepostos_lista', [])
    horario_sem_overlap = resumo.get('dias_mesmo_dia_sem_sobreposicao', [])

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=18 * mm, title='Relatório de análise de dois vínculos',
        author='Análise de dois vínculos',
    )
    story = []

    # Cabeçalho visual em duas faixas, inspirado no painel web.
    header = Table([
        [Paragraph('RELATÓRIO DE CONFERÊNCIA', styles['subtitle'])],
        [Paragraph('Análise de dois vínculos', styles['title'])],
        [Paragraph('Comparação de dias trabalhados, códigos de escala e possíveis coincidências.', styles['subtitle'])],
    ], colWidths=[174 * mm], rowHeights=[8 * mm, 13 * mm, 9 * mm])
    header.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), NAVY),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#163A68')),
        ('LEFTPADDING', (0, 0), (-1, -1), 10), ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LINEBELOW', (0, -1), (-1, -1), 3, CYAN),
    ]))
    story += [header, Spacer(1, 7 * mm)]

    identity = Table([
        [Paragraph('<b>Servidor</b><br/>' + _safe(servidor), styles['body']),
         Paragraph('<b>Referência</b><br/>' + _safe(f"{periodo.get('mes') or '?'} / {periodo.get('ano') or '?'}"), styles['body']),
         Paragraph('<b>Códigos considerados</b><br/>' + _safe(criterios), styles['body'])]
    ], colWidths=[73 * mm, 40 * mm, 61 * mm])
    identity.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), SOFT), ('BOX', (0, 0), (-1, -1), .6, LINE),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 9),
        ('RIGHTPADDING', (0, 0), (-1, -1), 9), ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8), ('LINEAFTER', (0, 0), (1, 0), .5, LINE),
    ]))
    legend = Table([[
        Paragraph('<b>Legenda oficial de horários</b><br/>M: 07h–13h &nbsp; | &nbsp; N6: 19h–01h &nbsp; | &nbsp; PD: 07h–19h &nbsp; | &nbsp; PN: 19h–07h<br/>T4: 14h–18h &nbsp; | &nbsp; T: 13h–19h &nbsp; | &nbsp; P: 07h–07h do dia seguinte<br/>A51 = licença maternidade &nbsp; | &nbsp; F1 = férias &nbsp; | &nbsp; F114 = atestado médico &nbsp; | &nbsp; F128 = falta plantão 12h<br/><b>E*</b> antes do código = plantão extra (ex.: E*PD, E*PN).', styles['muted'])
    ]], colWidths=[174 * mm])
    legend.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F0F7FF')), ('BOX', (0, 0), (-1, -1), .5, colors.HexColor('#B8D4F5')),
        ('LEFTPADDING', (0, 0), (-1, -1), 9), ('RIGHTPADDING', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story += [identity, Spacer(1, 3 * mm), legend, Spacer(1, 5 * mm), Paragraph('Resumo executivo', styles['h1'])]

    metric_values = [
        ('Dias · vínculo 1', resumo.get('dias_trabalhados_vinculo_1', 0), BLUE),
        ('Dias · vínculo 2', resumo.get('dias_trabalhados_vinculo_2', 0), CYAN),
        ('Dias coincidentes', resumo.get('dias_coincidentes', 0), ORANGE if coincidencias else GREEN),
        ('Dias distintos', resumo.get('dias_distintos_no_total', 0), BLUE),
    ]
    cards = []
    for label, value, accent in metric_values:
        card = Table([[Paragraph(label, styles['card_label'])], [Paragraph(str(value), styles['card_value'])]], colWidths=[40 * mm])
        card.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.white), ('BOX', (0, 0), (-1, -1), .7, LINE),
            ('LINEABOVE', (0, 0), (-1, 0), 3, accent), ('LEFTPADDING', (0, 0), (-1, -1), 7),
            ('RIGHTPADDING', (0, 0), (-1, -1), 7), ('TOPPADDING', (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ]))
        cards.append(card)
    metrics = Table([cards], colWidths=[43 * mm] * 4)
    metrics.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 3)]))
    story += [metrics, Spacer(1, 5 * mm)]

    if coincidencias:
        notice_text = '<b>Atenção:</b> foram identificados dias coincidentes nos dois vínculos: ' + ', '.join(map(str, coincidencias)) + '.'
        notice_color, notice_bg = ORANGE, colors.HexColor('#FFF4E8')
    else:
        notice_text = '<b>Resultado:</b> nenhum dia coincidente foi identificado pelos códigos selecionados.'
        notice_color, notice_bg = GREEN, colors.HexColor('#ECFDF5')
    notice = Table([[Paragraph(notice_text, styles['body'])]], colWidths=[174 * mm])
    notice.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), notice_bg), ('BOX', (0, 0), (-1, -1), .7, notice_color), ('LEFTPADDING', (0, 0), (-1, -1), 9), ('RIGHTPADDING', (0, 0), (-1, -1), 9), ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8)]))
    story += [notice]
    if horario_overlap:
        overlap_notice = Table([[Paragraph('<b>Sobreposição real de horário:</b> ' + ', '.join(map(str, horario_overlap)) + '.', styles['body'])]], colWidths=[174 * mm])
        overlap_notice.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#FDECEC')), ('BOX', (0, 0), (-1, -1), .7, colors.HexColor('#D92D20')), ('LEFTPADDING', (0, 0), (-1, -1), 9), ('RIGHTPADDING', (0, 0), (-1, -1), 9), ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8)]))
        story += [Spacer(1, 2 * mm), overlap_notice]
    elif horario_sem_overlap:
        no_overlap_notice = Table([[Paragraph('<b>Turnos diferentes:</b> nos dias ' + ', '.join(map(str, horario_sem_overlap)) + ', houve trabalho no mesmo dia, mas sem sobreposição entre os horários conhecidos.', styles['body'])]], colWidths=[174 * mm])
        no_overlap_notice.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#EFF6FF')), ('BOX', (0, 0), (-1, -1), .7, colors.HexColor('#60A5FA')), ('LEFTPADDING', (0, 0), (-1, -1), 9), ('RIGHTPADDING', (0, 0), (-1, -1), 9), ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8)]))
        story += [Spacer(1, 2 * mm), no_overlap_notice]
    story += [Spacer(1, 4 * mm), Paragraph('Conferência dia a dia', styles['h1'])]

    header_row = [Paragraph(x, styles['table_head']) for x in ['Dia', 'Vínculo 1', 'Vínculo 2', 'Mesmo dia', 'Situação dos horários']]
    rows = [header_row]
    for item in resultado.get('dias', []):
        hit = bool(item.get('coincidente'))
        rows.append([
            Paragraph(_safe(item.get('dia')), styles['table_cell_bold']),
            Paragraph(_safe(item.get('vinculo_1')), styles['table_cell']),
            Paragraph(_safe(item.get('vinculo_2')), styles['table_cell']),
            Paragraph('SIM' if hit else 'não', styles['table_cell_bold']),
            Paragraph(_safe(item.get('situacao_horarios')), styles['table_cell']),
        ])
    if len(rows) == 1:
        rows.append([Paragraph('—', styles['table_cell']), Paragraph('Nenhum registro extraído', styles['table_cell']), Paragraph('—', styles['table_cell']), Paragraph('—', styles['table_cell']), Paragraph('—', styles['table_cell'])])
    day_table = Table(rows, colWidths=[14 * mm, 42 * mm, 42 * mm, 25 * mm, 51 * mm], repeatRows=1)
    table_commands = [
        ('BACKGROUND', (0, 0), (-1, 0), NAVY), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), .35, LINE), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 7), ('RIGHTPADDING', (0, 0), (-1, -1), 7),
        ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]
    for i, item in enumerate(resultado.get('dias', []), start=1):
        table_commands.append(('BACKGROUND', (0, i), (-1, i), colors.HexColor('#FFF4E8') if item.get('coincidente') else (colors.white if i % 2 else SOFT)))
        if item.get('coincidente'):
            table_commands.append(('TEXTCOLOR', (3, i), (3, i), ORANGE))
        if item.get('sobreposicao_horarios'):
            table_commands.append(('TEXTCOLOR', (4, i), (4, i), colors.HexColor('#B42318')))
    day_table.setStyle(TableStyle(table_commands))
    story.append(day_table)

    story += [Spacer(1, 5 * mm), Paragraph('Notas de conferência', styles['h1'])]
    notes = [
        'Este relatório é auxiliar e deve ser conferido com os documentos originais.',
        'Os códigos aparecem na tabela mesmo quando não foram selecionados como trabalho, para facilitar a auditoria.',
        f"Registros extraídos: {sum(len(doc.days) for doc in resultado.get('_docs', []))}.",
    ]
    for note in notes:
        story.append(Paragraph('• ' + _safe(note), styles['body']))
        story.append(Spacer(1, 1.5 * mm))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
