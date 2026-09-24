# Análise de dois vínculos

Aplicativo em Python para receber **dois arquivos**, cada um podendo ser imagem (`.png`, `.jpg`, `.jpeg`, `.tif`) ou PDF, extrair códigos da escala e consolidar os dias trabalhados por vínculo.

## Interface visual com Streamlit

Instale as dependências e os componentes de OCR:

```bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr tesseract-ocr-por poppler-utils
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Inicie a aplicação:

```bash
streamlit run app.py
```

O Streamlit abrirá uma página no navegador. Na barra lateral, envie os arquivos dos dois vínculos, selecione os códigos que devem contar como trabalho e clique em **Analisar arquivos**.

A interface mostra cards de resumo, alerta de dias coincidentes, tabela dia a dia, gráfico comparativo, carga horária identificada, texto extraído para conferência e botões para baixar CSV, JSON e HTML.

## Uso por linha de comando

Também é possível executar sem interface:

```bash
python analise_vinculos.py vinculo_1.png vinculo_2.pdf --saida saida/servidor_001
```

Para contar somente o código `PD`:

```bash
python analise_vinculos.py a.png b.png --codigos-trabalho PD --saida saida/caso_001
```

## O que é analisado

O principal alerta é a lista de **dias coincidentes** entre os dois vínculos. Por padrão, a aplicação considera `PD`, `PN`, `HR`, `S*HR`, `E*HR`, `EH`, `EHR` e `PLANTAO` como códigos de trabalho. O critério pode ser alterado na barra lateral ou pelo parâmetro `--codigos-trabalho`.

Os códigos dos dias continuam aparecendo na tabela mesmo quando não são considerados dias trabalhados. Assim, `F*HR`, `FT*HR`, `AF` e outros códigos podem ser auditados sem contaminar o total padrão.

## Observações importantes

A extração depende da qualidade do PDF/imagem e do desenho da tela. PDFs textuais são lidos por `pypdf`, sem depender obrigatoriamente de `pdftotext`; PDFs escaneados e imagens ainda precisam de OCR. Para o modelo de escala enviado, que possui vários setores/registros na mesma página, o programa usa a linha de referência dos dias `1` a `30` e associa cada código à coluna correspondente. Ele também preserva códigos específicos do modelo, como `F114`, `FT*T` e `T`, para conferência, sem incluí-los automaticamente no total de dias trabalhados. Em documentos com layout diferente, revise a tabela e o texto extraído.

O resultado é **apoio à análise**, não uma conclusão administrativa ou jurídica. Antes de usar em um caso, confira manualmente o servidor, competência, matrícula, lotação, códigos e a regra local de compatibilidade de jornadas.

O arquivo de exemplo fornecido pelo usuário mostra códigos `PD` nos dias 2, 3, 7, 9, 10, 14, 16, 17, 21, 23, 24, 28 e 30. Ele pode ser usado como primeiro arquivo para validar a instalação; um segundo arquivo é necessário para gerar a comparação.
