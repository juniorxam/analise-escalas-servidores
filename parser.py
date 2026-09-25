#!/usr/bin/env python3
"""Consolida dias trabalhados de dois espelhos de escala (PDF ou imagem).

Uso:
  python analise_vinculos.py vinculo1.png vinculo2.pdf --saida relatorio

Para OCR de imagens/PDFs digitalizados, instale Tesseract e pytesseract.
O relatório não substitui a conferência funcional: sempre revise as evidências.
"""
from __future__ import annotations
import argparse, csv, json, re, shutil, subprocess, sys
from collections import Counter
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path
from typing import Optional

MONTHS = {
    'janeiro':1,'fevereiro':2,'marco':3,'março':3,'abril':4,'maio':5,'junho':6,
    'julho':7,'agosto':8,'setembro':9,'outubro':10,'novembro':11,'dezembro':12,
}
# Códigos considerados como presença/trabalho por padrão. Ajuste via --codigos-trabalho.
DEFAULT_WORKED = {'M','T','T4','N6','N','P','PD','PN','HR','S*HR','E*HR','EH','EHR','PLANTAO','PLANTÃO'}
ALL_CODES = {'M','T','T4','N6','N','P','HR','S*HR','E*HR','F*HR','FT*HR','AF','A51','PD','PN','EH','EHR','FH','FHR','FTHR','TROCA','FALTA','AFASTADO'}

@dataclass
class DayRecord:
    day: int
    code: str
    source: str
    page: int = 1
    confidence: str = 'media'

@dataclass
class DocumentResult:
    source: str
    text: str
    metadata: dict
    days: list[DayRecord]
    hours: dict
    warnings: list[str]


def normalize_code(value: str) -> str:
    v = value.upper().replace(' ', '')
    v = v.replace('−','-').replace('–','-')
    # OCR frequentemente confunde asterisco e caracteres próximos.
    v = v.replace('＊','*')
    return v


def run_pdftotext(path: Path) -> str:
    exe = shutil.which('pdftotext')
    if exe:
        try:
            p = subprocess.run([exe, '-layout', str(path), '-'], capture_output=True, text=True, timeout=60)
            if p.returncode == 0 and p.stdout.strip():
                return p.stdout
        except Exception:
            pass
    # Fallback puro Python: permite usar PDFs textuais no Streamlit mesmo
    # quando Poppler/pdftotext não foi instalado no computador do usuário.
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        chunks=[]
        for page in reader.pages:
            try:
                chunks.append(page.extract_text(extraction_mode='layout') or '')
            except TypeError:
                chunks.append(page.extract_text() or '')
        text='\n\n'.join(chunks)
        # Versões antigas do pypdf podem ignorar o layout. Nesse caso,
        # tenta pdfplumber, que preserva melhor as colunas da escala.
        if text.strip() and any(len(re.findall(r'(?<!\d)(?:[1-9]|[12]\d|30)(?!\d)', line)) >= 20 for line in text.splitlines()):
            return text
    except Exception:
        pass
    try:
        import pdfplumber
        with pdfplumber.open(str(path)) as pdf:
            text='\n\n'.join(page.extract_text(layout=True) or '' for page in pdf.pages)
            return text
    except Exception:
        return ''


def render_pdf(path: Path):
    try:
        from pdf2image import convert_from_path
        return convert_from_path(str(path), dpi=220, fmt='png')
    except Exception as exc:
        raise RuntimeError(f'Não foi possível renderizar {path.name}: {exc}')


def preprocess(image):
    from PIL import ImageOps, ImageFilter
    gray = ImageOps.grayscale(image)
    # OCR fica mais estável quando a imagem pequena é ampliada.
    if gray.width < 1800:
        gray = gray.resize((gray.width * 2, gray.height * 2))
    return gray.filter(ImageFilter.SHARPEN)


def ocr_image(image) -> tuple[str, list[dict]]:
    try:
        import pytesseract
    except ImportError:
        raise RuntimeError('pytesseract não está instalado. Execute: pip install -r requirements.txt')
    img = preprocess(image)
    cfg = '--psm 6'
    text = pytesseract.image_to_string(img, lang='por+eng', config=cfg)
    data = pytesseract.image_to_data(img, lang='por+eng', config=cfg, output_type=pytesseract.Output.DICT)
    words = []
    for i, raw in enumerate(data['text']):
        token = raw.strip()
        if token:
            words.append({'text': token, 'x': data['left'][i], 'y': data['top'][i],
                          'w': data['width'][i], 'h': data['height'][i],
                          'conf': float(data['conf'][i]) if str(data['conf'][i]).strip() not in ('','-1') else 0})
    return text, words


def find_period(text: str) -> tuple[Optional[int], Optional[int]]:
    low = text.lower()
    # Referência Setembro/2026 ou Setembro de 2026.
    m = re.search(r'(janeiro|fevereiro|mar[cç]o|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\s*(?:de|/|-)\s*(20\d{2})', low)
    if m: return MONTHS[m.group(1)], int(m.group(2))
    m = re.search(r'(\d{1,2})\s*[/-]\s*(\d{1,2})\s*[/-]\s*(20\d{2})', text)
    if m: return int(m.group(2)), int(m.group(3))
    return None, None


def metadata_from_text(text: str) -> dict:
    def get(pattern):
        m = re.search(pattern, text, re.I)
        return re.sub(r'\s+', ' ', m.group(1)).strip() if m else ''
    month, year = find_period(text)
    return {
        'nome': get(r'Nome\s*:\s*([^\n]+)'),
        'cpf': get(r'CPF\s*:\s*([0-9.\-]+)'),
        'matricula': get(r'Matr[ií]cula\s*:\s*([A-Za-z0-9\-]+)'),
        'lotacao': get(r'Lota[cç][aã]o\s*:\s*([^\n]+)'),
        'contrato': get(r'Contrato\s*:\s*([^\n]+)'),
        'referencia_mes': month, 'referencia_ano': year,
        'carga_horaria': get(r'(?:Carga Hor[aá]ria Geral|Contratado)\s*:?\s*([0-9]+\s*h)')
    }


def extract_hours(text: str) -> dict:
    out = {}
    patterns = {
        'contratado': r'Contratado\s*:\s*([0-9]+\s*h)',
        'equivalente': r'Equivalente\s*:\s*([0-9]+\s*h)',
        'escalada': r'Carga Hor[aá]ria escalada\s*:\s*([0-9]+\s*h)',
        'plantao_presencial': r'Plant[aã]o presencial\s*:\s*([0-9]+\s*h)',
        'sobreaviso': r'Sobreaviso\s*:\s*([0-9]+\s*h)',
        'acumulado': r'Total\s*:\s*([0-9]+\s*h)',
    }
    for k,p in patterns.items():
        m = re.search(p, text, re.I)
        if m: out[k] = m.group(1)
    return out


def code_candidates(words):
    # Permite códigos compostos e variações que OCR tende a gerar.
    pats = [r'^(?:E\*)?(?:M|T4|T|N6|N|P|S?\*?HR|E\*?HR|F\*?HR|FT\*?HR|AF|A51|PD|PN)$', r'^(?:EH|EHR|FH|FHR|FTHR)$']
    found=[]
    for w in words:
        token=normalize_code(w['text'])
        if any(re.match(p, token) for p in pats):
            found.append((w, token))
    return found


def day_candidates(words):
    out=[]
    for w in words:
        t=w['text'].strip()
        if re.fullmatch(r'0?[1-9]|[12][0-9]|3[01]', t):
            out.append((w, int(t)))
    return out


def records_from_words(words, source, page, month, year) -> list[DayRecord]:
    codes=code_candidates(words); days=day_candidates(words); records=[]
    for cw, code in codes:
        cx=cw['x']+cw['w']/2; cy=cw['y']+cw['h']/2
        # No quadro da escala, o código fica abaixo do número do dia; procura alinhamento vertical.
        possibles=[]
        for dw, day in days:
            dx=dw['x']+dw['w']/2; dy=dw['y']+dw['h']/2
            if abs(dx-cx) <= max(35, cw['w']*2.0) and dy < cy and cy-dy < 420:
                possibles.append((abs(dx-cx)+abs(cy-dy)*0.08, day, dw))
        if possibles:
            _, day, dw=min(possibles)
            if not month or day <= 31:
                conf='alta' if abs((dw['x']+dw['w']/2)-cx) < 18 else 'media'
                records.append(DayRecord(day, code, source, page, conf))
    return records


def records_from_pdf_words(words, source, page=1) -> list[DayRecord]:
    """Mapeia códigos para a coluna do dia usando coordenadas do PDF.

    É mais confiável que a ordem do texto quando o PDF foi gerado pelo
    navegador e contém várias linhas de setores na mesma página.
    """
    numeric=[]
    for w in words:
        t=str(w.get('text','')).strip()
        if re.fullmatch(r'[1-9]|[12]\d|30', t):
            numeric.append((w, int(t)))
    groups=[]
    for w, day in numeric:
        top=float(w.get('top', w.get('y', 0)))
        group=next((g for g in groups if abs(g[0]-top) <= 3), None)
        if group is None:
            group=[top, []]; groups.append(group)
        group[1].append((w, day))
    groups=[g for g in groups if len(g[1]) >= 20 and {d for _,d in g[1]} >= {1,30}]
    if not groups:
        return []
    _, calendar=sorted(groups, key=lambda g: (-len(g[1]), g[0]))[0]
    columns=[]
    for w, day in calendar:
        x=float(w.get('x0', w.get('x', 0))) + float(w.get('width', w.get('w', 0))) / 2
        columns.append((x, day))
    calendar_bottom=max(float(w.get('bottom', w.get('y', 0)+w.get('height', w.get('h', 0)))) for w, _ in calendar)
    token_re=re.compile(r'^(?:E\*)?(?:FT\*HR|F\*HR|E\*HR|S\*HR|FT\*T|F\d+|FTHR|FHR|EHR|HR|AF|A51|PD|PN|EH|FH|TROCA|M|T4|T|N6|N|P|FALTA)$', re.I)
    records=[]
    for w in words:
        code=normalize_code(str(w.get('text','')).strip())
        top=float(w.get('top', w.get('y', 0)))
        if top <= calendar_bottom or not token_re.match(code):
            continue
        x=float(w.get('x0', w.get('x', 0))) + float(w.get('width', w.get('w', 0))) / 2
        nearest=min(columns, key=lambda pair: abs(pair[0]-x))
        if abs(nearest[0]-x) <= 14:
            records.append(DayRecord(nearest[1], code, source, page, 'alta'))
    return records


def records_from_text(text, source, page=1) -> list[DayRecord]:
    """Extrai códigos respeitando a posição das colunas do espelho HTML/PDF.

    Nesse modelo os números dos dias ficam em uma linha e os códigos aparecem
    em outra, exatamente abaixo deles. A associação por proximidade de texto
    (por exemplo, ``PD 2``) desloca o resultado; por isso primeiro capturamos
    as colunas da linha que contém os dias 1..30 e depois projetamos cada código
    para a coluna mais próxima.
    """
    lines=text.splitlines()
    day_line_index=-1; day_columns=[]
    for idx, line in enumerate(lines):
        nums=list(re.finditer(r'(?<!\d)([1-9]|[12]\d|30)(?!\d)', line))
        values=[int(m.group(1)) for m in nums]
        if len(nums) >= 20 and 1 in values and 30 in values:
            # A linha com mais dias é preferida à linha de justificativas.
            if len(nums) > len(day_columns):
                day_line_index=idx
                day_columns=[(m.start(1), int(m.group(1))) for m in nums]

    # Inclui códigos conhecidos e alguns códigos específicos que aparecem
    # nesse sistema (ex.: F114 e FT*T), mantendo-os fora do total padrão.
    token_re=re.compile(r'(?<![A-Za-z0-9])(?:E\*)?(?:FT\*HR|F\*HR|E\*HR|S\*HR|FT\*T|F\d+|FTHR|FHR|EHR|HR|AF|A51|PD|PN|EH|FH|TROCA|M|T4|T|N6|N|P|FALTA)(?![A-Za-z0-9])', re.I)
    records=[]
    if day_line_index >= 0:
        end=len(lines)
        for idx in range(day_line_index+1, len(lines)):
            if re.search(r'Exibindo\s+\d+', lines[idx], re.I):
                end=idx; break
        for line in lines[day_line_index+1:end]:
            for match in token_re.finditer(line):
                code=normalize_code(match.group(0))
                col=match.start()
                nearest=min(day_columns, key=lambda x: abs(x[0]-col))
                # Evita capturar palavras de descrições longas alinhadas por acaso.
                if abs(nearest[0]-col) <= 8:
                    records.append(DayRecord(nearest[1], code, source, page, 'alta'))
        return records

    # Fallback para PDFs simples sem a linha de cabeçalho 1..30.
    code_re=r'((?:E\*)?(?:M|T4|T|N6|N|P|S\*HR|E\*HR|FT\*HR|F\*HR|HR|AF|A51|PD|PN|EH|EHR|FHR|FTHR))'
    for line in lines:
        for m in re.finditer(rf'(?:(\b(?:0?[1-9]|[12][0-9]|3[01])\b)\s*{code_re}|{code_re}\s*(?:dia\s*)?(\b(?:0?[1-9]|[12][0-9]|3[01])\b))', line, re.I):
            groups=[g for g in m.groups() if g]
            nums=[g for g in groups if g.isdigit()]
            codes=[g for g in groups if not g.isdigit()]
            if nums and codes: records.append(DayRecord(int(nums[0]), normalize_code(codes[0]), source, page, 'media'))
    return records


def parse_document(path: Path) -> DocumentResult:
    ext=path.suffix.lower(); text=''; records=[]; warnings=[]; pages=[]
    positional_records=False
    if ext == '.pdf':
        text=run_pdftotext(path)
        if not text.strip():
            warnings.append('Não foi possível extrair texto do PDF. Instale as dependências com: pip install -r requirements.txt')
        try:
            import pdfplumber
            with pdfplumber.open(str(path)) as pdf:
                for i, page_obj in enumerate(pdf.pages, 1):
                    words=page_obj.extract_words(x_tolerance=1, y_tolerance=2, keep_blank_chars=False, use_text_flow=False)
                    page_records=records_from_pdf_words(words, path.name, i)
                    records.extend(page_records)
                    positional_records = positional_records or bool(page_records)
        except Exception as exc:
            warnings.append(f'Leitura posicional do PDF indisponível: {exc}')
        try: pages=render_pdf(path)
        except Exception as exc: warnings.append(str(exc))
    else:
        try:
            from PIL import Image
            pages=[Image.open(path)]
        except Exception as exc: raise RuntimeError(f'Não foi possível abrir {path}: {exc}')
    meta=metadata_from_text(text); month,year=meta['referencia_mes'],meta['referencia_ano']
    all_ocr=[]
    for i, image in enumerate(pages, 1):
        try:
            ocr_text, words=ocr_image(image); all_ocr.append(ocr_text)
            if not text: text += '\n' + ocr_text
            records.extend(records_from_words(words, path.name, i, month, year))
        except RuntimeError as exc: warnings.append(str(exc)); break
    if not text: text='\n'.join(all_ocr)
    if not meta['nome'] or not meta['referencia_mes']:
        meta=metadata_from_text(text)
        month,year=meta['referencia_mes'],meta['referencia_ano']
    # Em PDFs com coordenadas, não misture a segunda leitura textual: ela pode
    # deslocar códigos para outra coluna e criar falsos dias coincidentes.
    # Para imagens ou PDFs sem coordenadas, o parser textual continua sendo o fallback.
    if not positional_records:
        records.extend(records_from_text(text, path.name))
    # Deduplica conservando a melhor confiança.
    unique={}
    rank={'baixa':0,'media':1,'alta':2}
    for r in records:
        k=(r.day,r.code,r.page)
        if k not in unique or rank[r.confidence]>rank[unique[k].confidence]: unique[k]=r
    records=sorted(unique.values(), key=lambda r:(r.day,r.code,r.page))
    return DocumentResult(path.name, text, meta, records, extract_hours(text), warnings)


SHIFT_WINDOWS = {
    'M': [(7, 13)],
    'T': [(13, 19)],
    'T4': [(14, 18)],
    'N6': [(19, 25)],
    'N': [(19, 25)],       # atravessa a meia-noite até 01h
    'P': [(7, 31)],        # entrada e saída às 07h do dia seguinte
    'PD': [(7, 19)],
    'PN': [(19, 31)],      # atravessa a meia-noite até 07h
}


def _schedule_windows(codes, worked):
    def base_code(code):
        code=normalize_code(code)
        return code[2:] if code.startswith('E*') else code
    selected = [normalize_code(code) for code in codes if base_code(code) in worked or normalize_code(code) in worked]
    windows=[]
    unknown=[]
    for code in selected:
        base=base_code(code)
        if base in SHIFT_WINDOWS:
            windows.extend((start, end, code) for start, end in SHIFT_WINDOWS[base])
        else:
            unknown.append(code)
    return selected, windows, unknown


def make_report(a: DocumentResult,b: DocumentResult, worked: set[str]) -> dict:
    def by_day(doc):
        d={}
        for r in doc.days:
            d.setdefault(r.day,[]).append(r.code)
        return {k:sorted(set(v)) for k,v in d.items()}
    da,db=by_day(a),by_day(b)
    def is_worked(code):
        code=normalize_code(code)
        return code in worked or (code.startswith('E*') and code[2:] in worked)
    wa={d for d,codes in da.items() if any(is_worked(c) for c in codes)}
    wb={d for d,codes in db.items() if any(is_worked(c) for c in codes)}
    same_day=sorted(wa & wb); union=sorted(wa | wb)
    schedule_analysis={}; schedule_overlap=[]; same_day_without_overlap=[]; undetermined=[]
    for day in same_day:
        codes_a, windows_a, unknown_a = _schedule_windows(da.get(day, []), worked)
        codes_b, windows_b, unknown_b = _schedule_windows(db.get(day, []), worked)
        pairs=[(ca, cb) for sa, ea, ca in windows_a for sb, eb, cb in windows_b if max(sa, sb) < min(ea, eb)]
        if pairs:
            schedule_analysis[day]={'status':'sobreposição de horário','pares':pairs}
            schedule_overlap.append(day)
        elif unknown_a or unknown_b or not windows_a or not windows_b:
            schedule_analysis[day]={'status':'horário não determinado','pares':[], 'codigos_indeterminados':sorted(set(unknown_a+unknown_b))}
            undetermined.append(day)
        else:
            schedule_analysis[day]={'status':'turnos diferentes sem sobreposição','pares':[]}
            same_day_without_overlap.append(day)
    month=a.metadata.get('referencia_mes') or b.metadata.get('referencia_mes')
    year=a.metadata.get('referencia_ano') or b.metadata.get('referencia_ano')
    def rows(days):
        return [{'dia':d,'vinculo_1':', '.join(da.get(d,[])),'vinculo_2':', '.join(db.get(d,[])),
                 'coincidente':d in same_day,
                 'sobreposicao_horarios':d in schedule_overlap,
                 'situacao_horarios':schedule_analysis.get(d,{}).get('status','—')} for d in days]
    return {'periodo':{'mes':month,'ano':year},'criterio_codigos_trabalho':sorted(worked),
            'servidor':a.metadata.get('nome') or b.metadata.get('nome'),
            'documentos':[{'arquivo':a.source,'metadata':a.metadata,'carga_horaria':a.hours,'avisos':a.warnings},
                          {'arquivo':b.source,'metadata':b.metadata,'carga_horaria':b.hours,'avisos':b.warnings}],
            'resumo':{'dias_trabalhados_vinculo_1':len(wa),'dias_trabalhados_vinculo_2':len(wb),
                      'dias_coincidentes':len(same_day),'dias_distintos_no_total':len(union),
                      'dias_coincidentes_lista':same_day,
                      'dias_sobreposicao_horarios':len(schedule_overlap),
                      'dias_sobrepostos_lista':schedule_overlap,
                      'dias_mesmo_dia_sem_sobreposicao':same_day_without_overlap,
                      'dias_horario_nao_determinado':undetermined},
            'analise_horarios':schedule_analysis,
            'dias':rows(union)}


def write_outputs(report, outbase: Path):
    outbase.parent.mkdir(parents=True, exist_ok=True)
    outbase.with_suffix('.json').write_text(json.dumps(report,ensure_ascii=False,indent=2), encoding='utf-8')
    with outbase.with_suffix('.csv').open('w',newline='',encoding='utf-8-sig') as f:
        fields=['dia','vinculo_1','vinculo_2','coincidente','sobreposicao_horarios','situacao_horarios']
        w=csv.DictWriter(f,fieldnames=fields,delimiter=';',extrasaction='ignore'); w.writeheader(); w.writerows(report['dias'])
    r=report['resumo'];
    html=f'''<!doctype html><meta charset="utf-8"><title>Análise de dois vínculos</title>
    <style>body{{font-family:Arial;margin:32px}} table{{border-collapse:collapse}}td,th{{border:1px solid #bbb;padding:7px}} th{{background:#eee}} .alert{{color:#a00;font-weight:bold}}</style>
    <h1>Análise de dois vínculos</h1><p><b>Servidor:</b> {report['servidor'] or 'não identificado'}<br><b>Período:</b> {report['periodo']['mes'] or '?'} / {report['periodo']['ano'] or '?'}</p>
    <ul><li>Vínculo 1: {r['dias_trabalhados_vinculo_1']} dias</li><li>Vínculo 2: {r['dias_trabalhados_vinculo_2']} dias</li><li class="alert">Coincidências: {r['dias_coincidentes']} dias ({', '.join(map(str,r['dias_coincidentes_lista'])) or 'nenhuma'})</li><li>Dias distintos no total: {r['dias_distintos_no_total']}</li></ul>
    <table><tr><th>Dia</th><th>Vínculo 1</th><th>Vínculo 2</th><th>Mesmo dia?</th><th>Sobreposição?</th><th>Situação dos horários</th></tr>{''.join(f"<tr><td>{x['dia']}</td><td>{x['vinculo_1']}</td><td>{x['vinculo_2']}</td><td>{'SIM' if x['coincidente'] else 'não'}</td><td>{'SIM' if x.get('sobreposicao_horarios') else 'não'}</td><td>{x.get('situacao_horarios','—')}</td></tr>" for x in report['dias'])}</table>
    <p><small>Relatório auxiliar. Confirme a leitura dos códigos e a regra administrativa aplicável.</small></p>'''
    outbase.with_suffix('.html').write_text(html,encoding='utf-8')


def main():
    ap=argparse.ArgumentParser(description='Consolida os dias trabalhados em dois vínculos, a partir de PDF ou imagem.')
    ap.add_argument('arquivo1',type=Path); ap.add_argument('arquivo2',type=Path)
    ap.add_argument('-o','--saida',type=Path,default=Path('relatorio_vinculos'),help='base dos arquivos de saída')
    ap.add_argument('--codigos-trabalho',default=','.join(sorted(DEFAULT_WORKED)),help='códigos separados por vírgula')
    args=ap.parse_args()
    for p in (args.arquivo1,args.arquivo2):
        if not p.exists(): ap.error(f'Arquivo não encontrado: {p}')
    worked={normalize_code(x) for x in args.codigos_trabalho.split(',') if x.strip()}
    try: a=parse_document(args.arquivo1); b=parse_document(args.arquivo2)
    except RuntimeError as exc: print(f'ERRO: {exc}',file=sys.stderr); return 2
    report=make_report(a,b,worked); write_outputs(report,args.saida)
    print(json.dumps(report['resumo'],ensure_ascii=False,indent=2))
    print(f'Arquivos gerados: {args.saida.with_suffix(".html")}, {args.saida.with_suffix(".csv")}, {args.saida.with_suffix(".json")}')
    return 0

if __name__=='__main__': raise SystemExit(main())

# Exemplo: python analise_vinculos.py vinculo1.png vinculo2.pdf --saida saida/relatorio
# Para considerar apenas PD: --codigos-trabalho PD
# Para incluir folgas/faltas como categorias, elas continuam no CSV, mas não contam como trabalhadas.
