from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from parser import DEFAULT_WORKED, make_report, normalize_code, parse_document, write_outputs
from pdf_report import build_pdf_report

st.set_page_config(page_title='Escalas | Análise de vínculos', page_icon='📊', layout='wide', initial_sidebar_state='expanded')

st.markdown('''
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');
:root { --ink:#172033; --muted:#667085; --blue:#2563eb; --cyan:#06b6d4; --line:#e7ebf3; --soft:#f5f7fb; }
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
h1, h2, h3 { font-family: 'Space Grotesk', sans-serif; color:var(--ink); letter-spacing:-.03em; }
[data-testid="stAppViewContainer"] { background:linear-gradient(180deg,#f8faff 0%,#ffffff 35%); }
[data-testid="stSidebar"] { background:#101827; border-right:1px solid #243044; }
[data-testid="stSidebar"] * { color:#e8edf7 !important; }
[data-testid="stSidebar"] [data-baseweb="select"] > div { background:#1b2638; border-color:#3a4a66; }
[data-testid="stSidebar"] .stButton button { background:linear-gradient(135deg,#3b82f6,#06b6d4); border:0; color:#fff !important; font-weight:700; }
[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] { background:#182337; border:1px dashed #526887; }
.hero { padding: 22px 28px; border-radius:24px; background:linear-gradient(125deg,#111c33 0%,#1e3a68 55%,#0e7490 100%); color:#fff; box-shadow:0 16px 38px rgba(29,55,100,.18); margin: 4px 0 24px; }
.hero .eyebrow { color:#9bdcf0; text-transform:uppercase; letter-spacing:.14em; font-size:.72rem; font-weight:700; }
.hero h1 { color:#fff; margin:.25rem 0 .3rem; font-size:2.1rem; }
.hero p { color:#d7e6f7; margin:0; font-size:1rem; }
.identity { background:#fff; border:1px solid var(--line); border-radius:18px; padding:16px 20px; margin-bottom:18px; box-shadow:0 8px 24px rgba(18,35,65,.05); }
.identity .name { font-family:'Space Grotesk'; font-size:1.4rem; font-weight:700; color:var(--ink); }
.identity .ref { color:var(--muted); font-size:.9rem; margin-top:3px; }
.metric-card { background:#fff; border:1px solid var(--line); border-radius:18px; padding:17px 18px; min-height:112px; box-shadow:0 8px 22px rgba(18,35,65,.04); }
.metric-label { color:var(--muted); font-size:.82rem; font-weight:600; }
.metric-value { color:var(--ink); font-family:'Space Grotesk'; font-size:2.15rem; font-weight:700; margin-top:7px; }
.metric-accent { height:4px; border-radius:5px; margin-top:12px; background:linear-gradient(90deg,#2563eb,#38bdf8); }
.metric-warning .metric-accent { background:linear-gradient(90deg,#f97316,#ef4444); }
.metric-success .metric-accent { background:linear-gradient(90deg,#10b981,#34d399); }
.section-title { font-family:'Space Grotesk'; font-size:1.2rem; font-weight:700; color:var(--ink); margin:12px 0 8px; }
.status-pill { display:inline-block; padding:6px 11px; border-radius:999px; font-size:.78rem; font-weight:700; background:#ecfdf5; color:#047857; }
.status-pill.warn { background:#fff7ed; color:#c2410c; }
div[data-testid="stTabs"] button { font-weight:700; color:#667085; }
div[data-testid="stTabs"] button[aria-selected="true"] { color:#2563eb; }
[data-testid="stDataFrame"] { border:1px solid var(--line); border-radius:14px; overflow:hidden; }
.small-note { color:#7b8799; font-size:.82rem; }
</style>
''', unsafe_allow_html=True)

st.markdown('''<div class="hero"><div class="eyebrow">Painel de conferência funcional</div><h1>Análise de dois vínculos</h1><p>Compare escalas, identifique coincidências e organize evidências em poucos segundos.</p></div>''', unsafe_allow_html=True)

with st.sidebar:
    st.markdown('### Configuração da análise')
    st.caption('Envie os dois espelhos de escala para iniciar a comparação.')
    arquivo1 = st.file_uploader('Arquivo do vínculo 1', type=['pdf', 'png', 'jpg', 'jpeg', 'tif', 'tiff'], key='v1')
    arquivo2 = st.file_uploader('Arquivo do vínculo 2', type=['pdf', 'png', 'jpg', 'jpeg', 'tif', 'tiff'], key='v2')
    st.divider()
    opcoes = ['PD', 'PN', 'HR', 'S*HR', 'E*HR', 'EH', 'EHR', 'F*HR', 'FT*HR', 'AF', 'TROCA']
    codigos = st.multiselect('Códigos considerados trabalho', opcoes, default=[x for x in opcoes if x in DEFAULT_WORKED], help='Folgas, faltas e afastamentos ficam visíveis, mas não entram no total padrão.')
    analisar = st.button('Analisar arquivos', type='primary', use_container_width=True)
    st.divider()
    st.caption('A análise é auxiliar. Revise os documentos originais antes de concluir um caso.')

if not arquivo1 or not arquivo2:
    st.markdown('<div class="identity"><div class="name">Comece por aqui</div><div class="ref">Envie os dois arquivos na barra lateral. A comparação aparecerá nesta área.</div></div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown('**01 · Carregue**\n\nEnvie um arquivo para cada vínculo em PDF ou imagem.')
    with c2:
        st.markdown('**02 · Compare**\n\nO sistema extrai os códigos e alinha os dias da escala.')
    with c3:
        st.markdown('**03 · Exporte**\n\nBaixe a tabela consolidada em CSV, JSON ou HTML.')
    st.stop()


def upload_fingerprint(upload, codes):
    payload = upload.getvalue()
    return hashlib.sha1(payload).hexdigest() + '|' + upload.name + '|' + ','.join(sorted(codes))


selected_codes = {normalize_code(x) for x in codigos}
fingerprint = upload_fingerprint(arquivo1, selected_codes) + '|' + upload_fingerprint(arquivo2, selected_codes)

if analisar or 'resultado' not in st.session_state or st.session_state.get('fingerprint') != fingerprint:
    with st.spinner('Processando escalas e alinhando as colunas de dias...'):
        try:
            with tempfile.TemporaryDirectory() as tmp:
                p1, p2 = Path(tmp) / arquivo1.name, Path(tmp) / arquivo2.name
                p1.write_bytes(arquivo1.getvalue()); p2.write_bytes(arquivo2.getvalue())
                doc1, doc2 = parse_document(p1), parse_document(p2)
                resultado = make_report(doc1, doc2, selected_codes)
                resultado['_docs'] = [doc1, doc2]
                st.session_state['resultado'] = resultado
                st.session_state['fingerprint'] = fingerprint
        except Exception as exc:
            st.error(f'Não foi possível analisar os arquivos: {exc}')
            st.stop()

resultado = st.session_state['resultado']
resumo = resultado['resumo']
periodo = resultado.get('periodo', {})
servidor = resultado.get('servidor') or 'Servidor não identificado'

st.markdown(f'''<div class="identity"><div class="name">{servidor}</div><div class="ref">Referência: {periodo.get('mes') or '?'} / {periodo.get('ano') or '?'} &nbsp; · &nbsp; Critério: {', '.join(resultado.get('criterio_codigos_trabalho', [])) or 'nenhum código selecionado'}</div></div>''', unsafe_allow_html=True)

m1, m2, m3, m4 = st.columns(4)
metrics = [
    ('Dias — vínculo 1', resumo['dias_trabalhados_vinculo_1'], '', 'metric-card'),
    ('Dias — vínculo 2', resumo['dias_trabalhados_vinculo_2'], '', 'metric-card'),
    ('Dias coincidentes', resumo['dias_coincidentes'], 'metric-warning' if resumo['dias_coincidentes'] else 'metric-success', 'metric-card'),
    ('Dias distintos', resumo['dias_distintos_no_total'], '', 'metric-card'),
]
for col, (label, value, extra, base) in zip((m1, m2, m3, m4), metrics):
    with col:
        st.markdown(f'<div class="{base} {extra}"><div class="metric-label">{label}</div><div class="metric-value">{value}</div><div class="metric-accent"></div></div>', unsafe_allow_html=True)

if resumo['dias_coincidentes']:
    st.warning(f"Atenção: dias coincidentes identificados — {', '.join(map(str, resumo['dias_coincidentes_lista']))}.")
else:
    st.success('Nenhum dia coincidente foi identificado pelos códigos selecionados.')

total_codigos = sum(len(doc.days) for doc in resultado['_docs'])
if total_codigos == 0:
    st.error('Nenhum código de escala foi reconhecido. Consulte “Documentos e avisos” para verificar o texto extraído e os avisos.')
else:
    encontrados = sorted({r.code for doc in resultado['_docs'] for r in doc.days})
    st.markdown(f'<span class="status-pill">Leitura concluída</span> &nbsp; <span class="small-note">{total_codigos} registros · códigos encontrados: {", ".join(encontrados)}</span>', unsafe_allow_html=True)

aba_dias, aba_graficos, aba_documentos = st.tabs(['Dias consolidados', 'Indicadores', 'Documentos e avisos'])

with aba_dias:
    st.markdown('<div class="section-title">Conferência dia a dia</div>', unsafe_allow_html=True)
    df = pd.DataFrame(resultado['dias'])
    if df.empty:
        st.warning('Nenhum código de jornada foi extraído. Verifique o OCR e o layout do documento.')
    else:
        df['coincidente'] = df['coincidente'].map({True: 'SIM', False: 'não'})
        styled = df.rename(columns={'dia': 'Dia', 'vinculo_1': 'Vínculo 1', 'vinculo_2': 'Vínculo 2', 'coincidente': 'Coincidente'})
        st.dataframe(styled, use_container_width=True, hide_index=True, height=min(620, 95 + len(styled) * 36), column_config={'Dia': st.column_config.NumberColumn(width='small'), 'Coincidente': st.column_config.TextColumn(width='small')})
        st.caption('Os códigos de faltas, trocas e afastamentos permanecem visíveis para auditoria.')

with aba_graficos:
    st.markdown('<div class="section-title">Comparação rápida</div>', unsafe_allow_html=True)
    graf = pd.DataFrame({'Vínculo 1': [resumo['dias_trabalhados_vinculo_1']], 'Vínculo 2': [resumo['dias_trabalhados_vinculo_2']], 'Coincidentes': [resumo['dias_coincidentes']]}, index=['Dias'])
    st.bar_chart(graf, color=['#2563eb', '#06b6d4', '#f97316'])
    st.markdown('<div class="section-title">Carga horária identificada</div>', unsafe_allow_html=True)
    horas = []
    for i, doc in enumerate(resultado['_docs'], 1):
        for chave, valor in doc.hours.items(): horas.append({'Vínculo': f'Vínculo {i}', 'Indicador': chave.replace('_', ' ').title(), 'Valor': valor})
    if horas: st.dataframe(pd.DataFrame(horas), use_container_width=True, hide_index=True)
    else: st.info('Nenhuma carga horária foi identificada automaticamente.')

with aba_documentos:
    for i, doc in enumerate(resultado['_docs'], 1):
        with st.expander(f'Vínculo {i} · {doc.source}', expanded=(i == 1)):
            meta = {k: v for k, v in doc.metadata.items() if v not in ('', None)}
            if meta: st.json(meta)
            if doc.warnings:
                for aviso in doc.warnings: st.warning(aviso)
            with st.expander('Texto extraído para conferência'):
                st.text(doc.text[:12000] if doc.text else 'Nenhum texto foi extraído.')

report_download = {k: v for k, v in resultado.items() if k != '_docs'}
with tempfile.TemporaryDirectory() as outdir:
    outbase = Path(outdir) / 'relatorio'; write_outputs(report_download, outbase)
    html_bytes, csv_bytes, json_bytes = (outbase.with_suffix(ext).read_bytes() for ext in ('.html', '.csv', '.json'))
pdf_bytes = build_pdf_report(resultado)

st.divider()
st.markdown('<div class="section-title">Exportar análise</div>', unsafe_allow_html=True)
d1, d2, d3, d4 = st.columns(4)
d1.download_button('Baixar CSV', csv_bytes, 'relatorio_vinculos.csv', 'text/csv', use_container_width=True)
d2.download_button('Baixar JSON', json_bytes, 'relatorio_vinculos.json', 'application/json', use_container_width=True)
d3.download_button('Baixar HTML', html_bytes, 'relatorio_vinculos.html', 'text/html', use_container_width=True)
d4.download_button('Baixar PDF profissional', pdf_bytes, 'relatorio_vinculos.pdf', 'application/pdf', use_container_width=True)
st.caption('Versão Streamlit · resultado auxiliar sujeito à conferência nos documentos originais.')
