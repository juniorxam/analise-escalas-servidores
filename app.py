from __future__ import annotations

import io
import json
import tempfile
import hashlib
from pathlib import Path

import pandas as pd
import streamlit as st

from analise_vinculos import (
    DEFAULT_WORKED,
    make_report,
    normalize_code,
    parse_document,
    write_outputs,
)

st.set_page_config(page_title='Análise de dois vínculos', page_icon='📊', layout='wide')

st.title('Análise de dois vínculos')
st.caption('Compare dias trabalhados, coincidências e carga horária a partir de dois PDFs ou imagens.')

with st.sidebar:
    st.header('Arquivos')
    arquivo1 = st.file_uploader('Arquivo do vínculo 1', type=['pdf', 'png', 'jpg', 'jpeg', 'tif', 'tiff'], key='v1')
    arquivo2 = st.file_uploader('Arquivo do vínculo 2', type=['pdf', 'png', 'jpg', 'jpeg', 'tif', 'tiff'], key='v2')
    st.divider()
    opcoes = ['PD', 'PN', 'HR', 'S*HR', 'E*HR', 'EH', 'EHR', 'F*HR', 'FT*HR', 'AF', 'TROCA']
    codigos = st.multiselect('Códigos que contam como trabalho', opcoes, default=[x for x in opcoes if x in DEFAULT_WORKED])
    analisar = st.button('Analisar arquivos', type='primary', use_container_width=True)
    st.info('A análise é auxiliar. Revise o relatório e os documentos originais antes de concluir um caso.')

if not arquivo1 or not arquivo2:
    st.info('Envie os dois arquivos na barra lateral para começar.')
    st.markdown('''### O que será exibido\n\n- Dias trabalhados em cada vínculo;\n- Dias coincidentes;\n- Dias exclusivos de cada vínculo;\n- Códigos encontrados por dia;\n- Metadados e carga horária identificados;\n- Downloads em CSV, JSON e HTML.''')
    st.stop()

def upload_fingerprint(upload, codes):
    if upload is None:
        return ''
    payload = upload.getvalue()
    return hashlib.sha1(payload).hexdigest() + '|' + upload.name + '|' + ','.join(sorted(codes))


selected_codes = {normalize_code(x) for x in codigos}
fingerprint = upload_fingerprint(arquivo1, selected_codes) + '|' + upload_fingerprint(arquivo2, selected_codes)

if analisar or 'resultado' not in st.session_state or st.session_state.get('fingerprint') != fingerprint:
    with st.spinner('Lendo os documentos e executando OCR quando necessário...'):
        try:
            with tempfile.TemporaryDirectory() as tmp:
                p1 = Path(tmp) / arquivo1.name
                p2 = Path(tmp) / arquivo2.name
                p1.write_bytes(arquivo1.getvalue())
                p2.write_bytes(arquivo2.getvalue())
                doc1 = parse_document(p1)
                doc2 = parse_document(p2)
                resultado = make_report(doc1, doc2, selected_codes)
                resultado['_docs'] = [doc1, doc2]
                st.session_state['resultado'] = resultado
                st.session_state['fingerprint'] = fingerprint
        except Exception as exc:
            st.error(f'Não foi possível analisar os arquivos: {exc}')
            st.stop()

resultado = st.session_state['resultado']
resumo = resultado['resumo']

st.subheader(f"{resultado.get('servidor') or 'Servidor não identificado'}")
periodo = resultado.get('periodo', {})
st.caption(f"Referência: {periodo.get('mes') or '?'} / {periodo.get('ano') or '?'}")

m1, m2, m3, m4 = st.columns(4)
m1.metric('Dias — vínculo 1', resumo['dias_trabalhados_vinculo_1'])
m2.metric('Dias — vínculo 2', resumo['dias_trabalhados_vinculo_2'])
m3.metric('Dias coincidentes', resumo['dias_coincidentes'], delta='atenção' if resumo['dias_coincidentes'] else 'nenhuma coincidência', delta_color='inverse')
m4.metric('Dias distintos', resumo['dias_distintos_no_total'])

if resumo['dias_coincidentes']:
    st.warning(f"Foram encontrados dias coincidentes: {', '.join(map(str, resumo['dias_coincidentes_lista']))}.")
else:
    st.success('Nenhum dia coincidente foi identificado pelos códigos selecionados.')

total_codigos = sum(len(doc.days) for doc in resultado['_docs'])
if total_codigos == 0:
    st.error('Nenhum código de escala foi reconhecido. Consulte a aba “Documentos e avisos” para conferir o texto extraído e os avisos do OCR.')
else:
    encontrados = sorted({r.code for doc in resultado['_docs'] for r in doc.days})
    st.caption(f"Códigos reconhecidos nos arquivos: {', '.join(encontrados)} — registros extraídos: {total_codigos}.")

aba_dias, aba_graficos, aba_documentos = st.tabs(['Dias consolidados', 'Visualização', 'Documentos e avisos'])

with aba_dias:
    st.subheader('Conferência dia a dia')
    df = pd.DataFrame(resultado['dias'])
    if df.empty:
        st.warning('Nenhum código de jornada foi extraído. Verifique o OCR e o layout do documento.')
    else:
        df['coincidente'] = df['coincidente'].map({True: 'SIM', False: 'não'})
        st.dataframe(
            df.rename(columns={'dia': 'Dia', 'vinculo_1': 'Vínculo 1', 'vinculo_2': 'Vínculo 2', 'coincidente': 'Coincidente'}),
            use_container_width=True, hide_index=True,
            column_config={'Coincidente': st.column_config.TextColumn(width='small')},
        )
        st.caption('Os códigos aparecem mesmo quando não estão marcados como trabalho, para facilitar a auditoria.')

with aba_graficos:
    st.subheader('Comparação dos dias')
    graf = pd.DataFrame({
        'Vínculo 1': [resumo['dias_trabalhados_vinculo_1']],
        'Vínculo 2': [resumo['dias_trabalhados_vinculo_2']],
        'Coincidentes': [resumo['dias_coincidentes']],
    }, index=['Dias'])
    st.bar_chart(graf, color=['#1f77b4', '#ff7f0e', '#d62728'])
    st.subheader('Carga horária identificada')
    horas = []
    for i, doc in enumerate(resultado['_docs'], 1):
        for chave, valor in doc.hours.items():
            horas.append({'Vínculo': f'Vínculo {i}', 'Indicador': chave.replace('_', ' ').title(), 'Valor': valor})
    if horas:
        st.dataframe(pd.DataFrame(horas), use_container_width=True, hide_index=True)
    else:
        st.info('Nenhuma carga horária foi identificada automaticamente.')

with aba_documentos:
    for i, doc in enumerate(resultado['_docs'], 1):
        st.markdown(f'#### Vínculo {i}: `{doc.source}`')
        meta = {k: v for k, v in doc.metadata.items() if v not in ('', None)}
        if meta:
            st.json(meta)
        if doc.warnings:
            for aviso in doc.warnings:
                st.warning(aviso)
        with st.expander('Texto extraído (para conferência)'):
            st.text(doc.text[:12000] if doc.text else 'Nenhum texto foi extraído.')

# Gera os mesmos formatos do modo de linha de comando em memória.
base = Path(tempfile.gettempdir()) / 'relatorio_streamlit'
report_download = {k: v for k, v in resultado.items() if k != '_docs'}
with tempfile.TemporaryDirectory() as outdir:
    outbase = Path(outdir) / 'relatorio'
    write_outputs(report_download, outbase)
    html_bytes = outbase.with_suffix('.html').read_bytes()
    csv_bytes = outbase.with_suffix('.csv').read_bytes()
    json_bytes = outbase.with_suffix('.json').read_bytes()

st.divider()
st.subheader('Baixar relatório')
d1, d2, d3 = st.columns(3)
d1.download_button('Baixar CSV', csv_bytes, 'relatorio_vinculos.csv', 'text/csv', use_container_width=True)
d2.download_button('Baixar JSON', json_bytes, 'relatorio_vinculos.json', 'application/json', use_container_width=True)
d3.download_button('Baixar HTML', html_bytes, 'relatorio_vinculos.html', 'text/html', use_container_width=True)

st.caption('Versão Streamlit — o resultado depende da qualidade do arquivo e do OCR. Confirme os dias nos documentos originais.')
