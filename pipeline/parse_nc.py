import os
import re
import csv

import pandas as pd
from bs4 import BeautifulSoup

from pipeline.db import RAIZ

# Converte os arquivos brutos do NC-UFPR (data/raw/nc_ufpr) numa tabela única por curso e ano
# (data/silver/nc_candidato_vaga.csv), sem alterar os números publicados.
#   concorrentes: inscritos que disputam vaga (sem treineiros, quando a fonte separa)
#   treineiros:   inscritos sem direito a vaga (só existe de 2007 em diante)
#   cand_vaga_publicada: o valor impresso pelo NC, usado para conferir a leitura

PASTA_RAW = os.path.join(RAIZ, "data", "raw", "nc_ufpr")
ARQUIVO_SILVER = os.path.join(RAIZ, "data", "silver", "nc_candidato_vaga.csv")
NUMERO = re.compile(r"^\d+(,\d+)?$")


def _texto_html(caminho):
    bruto = open(caminho, "rb").read()
    try:
        return bruto.decode("utf-8")
    except UnicodeDecodeError:
        return bruto.decode("latin1")


def _inteiro(texto):
    # Contagens: "1.234" ou "0956" -> 1234 / 956
    return int(texto.replace(".", ""))


def _razao(texto):
    # Cand/vaga aparece como "5,76", "06.62" ou "1738" (duas casas decimais implícitas)
    if "," in texto or "." in texto:
        return float(texto.replace(",", "."))
    return int(texto) / 100


def _linhas_html(caminho):
    """Células de texto de cada <tr> mais interno (sem tabela aninhada)."""
    sopa = BeautifulSoup(_texto_html(caminho), "html.parser")
    for tr in sopa.find_all("tr"):
        if tr.find("table"):
            continue
        celulas = [re.sub(r"\s+", " ", c.get_text(" ", strip=True)) for c in tr.find_all(["td", "th"])]
        if celulas:
            yield celulas


def ler_html_simples(caminho, ano):
    """Formatos de 2003 a 2015: uma linha por curso com inscritos/concorrentes, (treineiros), vagas e cand/vaga."""
    registros = []
    for celulas in _linhas_html(caminho):
        if any(c.lower().startswith("total") for c in celulas):
            continue
        numeros = [c for c in celulas if NUMERO.match(c.replace(".", ""))]
        textos = [c for c in celulas if c and not NUMERO.match(c.replace(".", ""))]
        if ano == 2003:
            # Código | Turno | Nome do Curso | Inscritos | Vagas | Cand/Vaga
            if len(celulas) != 6 or not NUMERO.match(celulas[0]):
                continue
            curso = f"{celulas[2]} - {celulas[1]}"
            concorrentes, treineiros, vagas, cv = celulas[3], None, celulas[4], celulas[5]
        elif len(numeros) == 3 and len(textos) == 1:
            curso = textos[0]
            concorrentes, treineiros, vagas, cv = numeros[0], None, numeros[1], numeros[2]
        elif len(numeros) == 4 and len(textos) == 1:
            curso = textos[0]
            concorrentes, treineiros, vagas, cv = numeros
        else:
            continue
        registros.append({
            "ano": ano,
            "curso": re.sub(r"\s*\(\d\)\s*", " ", curso).strip(),
            "concorrentes": _inteiro(concorrentes),
            "treineiros": _inteiro(treineiros) if treineiros else None,
            "vagas": _inteiro(vagas),
            "cand_vaga_publicada": _razao(cv),
        })
    return registros


def ler_html_categorias(caminho, ano):
    """2016: uma linha por curso com V/I/C/V por categoria de cota; as 4 últimas colunas são T, V, I e C/V do total."""
    registros = []
    for celulas in _linhas_html(caminho):
        if len(celulas) < 8 or NUMERO.match(celulas[0]) or celulas[0].upper().startswith("TOTAL"):
            continue
        treineiros, vagas, concorrentes, cv = celulas[-4:]
        if not all(NUMERO.match(x.replace(".", "")) for x in (treineiros, vagas, concorrentes, cv)):
            continue
        registros.append({
            "ano": ano,
            "curso": celulas[0],
            "concorrentes": _inteiro(concorrentes),
            "treineiros": _inteiro(treineiros),
            "vagas": _inteiro(vagas),
            "cand_vaga_publicada": _razao(cv),
        })
    return registros


def _linhas_pdf(caminho):
    import pdfplumber
    with pdfplumber.open(caminho) as pdf:
        for pagina in pdf.pages:
            for tabela in pagina.extract_tables():
                for linha in tabela:
                    yield [re.sub(r"\s+", " ", c or "").strip() for c in linha]


def ler_pdf_categorias(caminho, ano):
    """2017: mesmo layout de 2016 (T, V, I e C/V do total nas 4 últimas colunas)."""
    registros = []
    for celulas in _linhas_pdf(caminho):
        if len(celulas) < 8 or not celulas[0] or celulas[0].upper().startswith(("TOTAL", "CURSO")):
            continue
        treineiros, vagas, concorrentes, cv = celulas[-4:]
        if not all(NUMERO.match(x.replace(".", "")) for x in (treineiros, vagas, concorrentes, cv)):
            continue
        registros.append({
            "ano": ano, "curso": celulas[0],
            "concorrentes": _inteiro(concorrentes), "treineiros": _inteiro(treineiros),
            "vagas": _inteiro(vagas), "cand_vaga_publicada": _razao(cv),
        })
    return registros


def ler_pdf_2020(caminho, ano):
    """2020: Campus | Curso | 9 categorias com (C, V, C/V) | T. Sem coluna de total: soma as categorias."""
    registros = []
    for celulas in _linhas_pdf(caminho):
        if len(celulas) != 30 or not celulas[1] or not NUMERO.match(celulas[-1].replace(".", "")):
            continue
        c = [_inteiro(celulas[i]) for i in range(2, 29, 3)]
        v = [_inteiro(celulas[i]) for i in range(3, 29, 3)]
        # "Administração - Bacharelado - M" + "Curitiba - PR" -> mesmo formato dos anos seguintes
        nome, _, turno = celulas[1].rpartition(" - ")
        concorrentes, vagas = sum(c), sum(v)
        registros.append({
            "ano": ano, "curso": f"{nome} - {celulas[0]} - {turno}",
            "concorrentes": concorrentes, "treineiros": _inteiro(celulas[-1]),
            "vagas": vagas, "cand_vaga_publicada": round(concorrentes / vagas, 2) if vagas else None,
        })
    return registros


ARQUIVO_VAGAS = os.path.join(RAIZ, "data", "silver", "nc_vagas_por_curso.csv")
CIDADES = ["Curitiba", "Matinhos", "Palotina", "Toledo", "Jandaia do Sul", "Pontal do Paraná", "Terra Roxa"]
CIDADE_REGEX = r"Curitiba|Matinhos|Palotina|Toledo|Jandaia(?: do Sul)?|Pontal(?: do Paraná)?|Terra Roxa"
CIDADE_COMPLETA = {"Jandaia": "Jandaia do Sul", "Pontal": "Pontal do Paraná"}
GRAUS_TEXTO = ["Licenciatura/Bacharelado", "Bacharelado", "Licenciatura", "Tecnológico", "Formação do Tecnólogo"]
LINHA_VAGAS = re.compile(
    r"^(?P<cidade>" + CIDADE_REGEX + r")\s+(?P<meio>[^\d]*?)\s*"
    r"(?P<turno>I \([^)]*\)|[MTVN]\(\+[MTVN]\)(?:/[MTVN]\(\+[MTVN]\))?|EaD|[MTVN]{1,3})\s+"
    r"(?P<s1>\d+)\**\s+(?P<s2>\d+)\**\s+(?P<total>\d+)\**$"
)


def _tira_rodape(s1, s2, total):
    """Notas de rodapé sobrescritas viram dígitos grudados ("40²⁶ 0 40²⁷" -> "4026 0 4027").

    Se 1.º sem + 2.º sem não fecha com o total, procura os cortes que fecham.
    Devolve a lista de leituras possíveis (a mais provável primeiro); vazia se nenhuma fecha.
    """
    if int(s1) + int(s2) == int(total):
        return [(int(s1), int(s2), int(total))]
    # Testa cortes nos três números. Regras: nota de rodapé não começa com "0"; total plausível
    # (até 250 vagas); preferir notas seguidas (ex.: 26 e 27) e, depois, o corte que tira menos dígitos
    def nota_ok(resto):
        return resto == "" or not resto.startswith("0")

    candidatos = []
    for i in range(1, len(s1) + 1):
        for k in range(1, len(s2) + 1):
            for j in range(1, len(total) + 1):
                a, b, t = int(s1[:i]), int(s2[:k]), int(total[:j])
                restos = [s1[i:], s2[k:], total[j:]]
                if a + b != t or t > 250 or not any(restos) or not all(nota_ok(r) for r in restos):
                    continue
                notas = sorted(int(r) for r in restos if r)
                seguidas = all(y - x == 1 for x, y in zip(notas, notas[1:]))
                candidatos.append((not seguidas, sum(len(r) for r in restos), a, b, t))
    melhor = min(candidatos)[0] if candidatos else None
    # Só ficam as leituras do grupo preferido (notas seguidas ou não); a ordem decide o padrão
    return [(a, b, t) for ruim, _, a, b, t in sorted(candidatos) if ruim == melhor]


def ler_quadro_vagas(caminho, ano):
    """2021-2026: quadro "Cursos e Vagas" do guia ou Anexo II do edital.

    Cada linha é "Cidade Curso [- ]Grau Turno 1ºsem 2ºsem Total". Nomes longos quebram em três
    linhas no PDF: começo do nome / "Cidade [Grau] Turno n n n" / fim do nome.
    """
    import pdfplumber
    registros = []
    with pdfplumber.open(caminho) as pdf:
        linhas = []
        no_quadro = False
        for pagina in pdf.pages:
            texto = pagina.extract_text() or ""
            pagina_linhas = [l.strip() for l in texto.split("\n") if l.strip()]
            # O quadro simples começa na página com cabeçalho de 1.º e 2.º semestre e continua
            # nas páginas seguintes (sem cabeçalho) enquanto houver linhas de curso
            if re.search(r"1\.?\s*º\s*Sem", texto, re.I) and re.search(r"2\.?\s*º\s*Sem", texto, re.I):
                no_quadro = True
            elif no_quadro and not any(LINHA_VAGAS.match(re.sub(r"(?<=[A-Za-zÀ-ÿ])\d+(?=\s)", "", l)) for l in pagina_linhas):
                no_quadro = False
            if no_quadro:
                linhas += pagina_linhas

    # A cidade pode aparecer sozinha numa linha (ex.: "Matinhos") e valer para as linhas de curso
    # seguintes, que vêm sem cidade. Repete a cidade nessas linhas; "***" some.
    juntas = []
    cidade_atual = None
    for linha in linhas:
        if re.fullmatch(r"\**", linha):
            continue
        # Nota grudada no nome da cidade: "Matinhos** Administração ..." (edital de 2027)
        linha = re.sub(r"^(" + CIDADE_REGEX + r")\*+", r"\1", linha)
        if re.fullmatch(CIDADE_REGEX, linha):
            cidade_atual = linha
            continue
        limpa = re.sub(r"(?<=[A-Za-zÀ-ÿ])\d+(?=\s)", "", linha)
        inicio = re.match(CIDADE_REGEX, linha)
        if inicio:
            cidade_atual = inicio.group(0)
        elif cidade_atual and not re.match(r"total", linha, re.I) and LINHA_VAGAS.match(f"{cidade_atual} {limpa}"):
            linha = f"{cidade_atual} {linha}"
        juntas.append(linha)
    linhas = juntas

    for i, linha in enumerate(linhas):
        # Remove números de nota de rodapé grudados no nome ("Biológicas7")
        limpa = re.sub(r"(?<=[A-Za-zÀ-ÿ])\d+(?=\s)", "", linha)
        m = LINHA_VAGAS.match(limpa)
        if not m:
            continue
        meio = m.group("meio").strip(" -")
        if meio in GRAUS_TEXTO or meio == "":
            # Linha quebrada: o nome está na linha de cima e (às vezes) na de baixo
            antes = linhas[i - 1] if i > 0 and not LINHA_VAGAS.match(linhas[i - 1]) else ""
            depois = linhas[i + 1] if i + 1 < len(linhas) and not LINHA_VAGAS.match(linhas[i + 1]) else ""
            if depois and not any(depois.startswith(c) for c in CIDADES) and len(depois) < 40:
                nome = f"{antes} {depois}"
            else:
                nome = antes
            meio = f"{nome.strip()} {meio}".strip()
        # Padroniza para o formato da base: "Nome - Grau - Cidade - PR - Turno"
        meio = re.sub(r"\s+", " ", meio.replace("*", "").replace("–", "-")).strip(" -")
        cidade = CIDADE_COMPLETA.get(m.group("cidade"), m.group("cidade"))
        grau = None if "ABI" in meio else next((g for g in GRAUS_TEXTO if meio.endswith(g)), None)
        nome = meio[: -len(grau)].strip(" -") if grau else meio
        if grau == "Formação do Tecnólogo":
            grau = "Tecnológico"
        curso = f"{nome} - {grau} - {cidade} - PR - {m.group('turno')}" if grau else \
                f"{nome} - {cidade} - PR - {m.group('turno')}"
        leituras = _tira_rodape(m.group("s1"), m.group("s2"), m.group("total"))
        if not leituras:
            print(f"   ! {ano}: vagas inconsistentes, linha ignorada: {linha}")
            continue
        registros.append({
            "ano": ano, "curso": re.sub(r"\s+", " ", curso),
            "vagas_1sem": leituras[0][0], "vagas_2sem": leituras[0][1], "vagas": leituras[0][2],
            "leituras": leituras,
        })
    return registros


def _resolver_ambiguas(df):
    """Quando a nota de rodapé deixa mais de uma leitura (ex.: "1512 0 1513" = 15 ou 151 vagas),
    fica a leitura mais próxima do mesmo curso em outros anos; sem outros anos, a mais próxima
    da mediana de vagas daquele ano."""
    firmes = df[df["leituras"].map(len) == 1]
    referencia = firmes.groupby("curso")["vagas"].median()
    mediana_ano = firmes.groupby("ano")["vagas"].median()
    for i, linha in df[df["leituras"].map(len) > 1].iterrows():
        alvo = referencia.get(linha["curso"], mediana_ano[linha["ano"]])
        a, b, t = min(linha["leituras"], key=lambda x: abs(x[2] - alvo))
        df.loc[i, ["vagas_1sem", "vagas_2sem", "vagas"]] = [a, b, t]
        df.loc[i, "leitura_ambigua"] = True
    return df


def converter_vagas():
    manifesto = pd.read_csv(os.path.join(PASTA_RAW, "manifesto.csv"))
    registros = []
    quadros = manifesto[(manifesto["ano"] >= 2021) & manifesto["arquivo"].str.contains("documento_")]
    for _, linha in quadros.iterrows():
        novos = ler_quadro_vagas(os.path.join(RAIZ, linha["arquivo"]), int(linha["ano"]))
        registros += novos
    df = pd.DataFrame(registros).drop_duplicates(["ano", "curso"]).reset_index(drop=True)
    df["leitura_ambigua"] = False
    df = _resolver_ambiguas(df)
    for ano, grupo in df.groupby("ano"):
        print(f"-> {ano}: {len(grupo)} cursos, {int(grupo['vagas'].sum())} vagas "
              f"({int(grupo['leitura_ambigua'].sum())} com nota de rodapé ambígua)")
    df = df.drop(columns="leituras")
    df.to_csv(ARQUIVO_VAGAS, index=False)
    return df


ARQUIVO_OCUPACAO = os.path.join(RAIZ, "data", "silver", "nc_ocupacao_por_curso.csv")


def ler_ocupacao(caminho, ano):
    """Relatório de ocupação: por curso, soma das colunas "QTDE" (aprovados em cada categoria)."""
    sopa = BeautifulSoup(_texto_html(caminho), "html.parser")
    tabela = sopa.find("table")
    cabecalho = [c.get_text(strip=True) for c in tabela.find("tr").find_all(["th", "td"])]
    qtde = [i for i, nome in enumerate(cabecalho) if nome.endswith("QTDE")]
    registros = []
    for tr in tabela.find_all("tr")[1:]:
        celulas = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
        if len(celulas) != len(cabecalho) or not celulas[0]:
            continue
        registros.append({
            "ano": ano,
            "curso": re.sub(r"\s+", " ", celulas[0]),
            "tipo": "final" if "final" in os.path.basename(caminho) else "chamada_geral",
            "aprovados": sum(int(celulas[i]) for i in qtde if celulas[i].isdigit()),
        })
    return registros


def converter_ocupacao():
    manifesto = pd.read_csv(os.path.join(PASTA_RAW, "manifesto.csv"))
    registros = []
    for _, linha in manifesto[manifesto["arquivo"].str.contains("ocupacao_")].iterrows():
        registros += ler_ocupacao(os.path.join(RAIZ, linha["arquivo"]), int(linha["ano"]))
    df = pd.DataFrame(registros)
    for (ano, tipo), grupo in df.groupby(["ano", "tipo"]):
        print(f"-> {ano} {tipo}: {len(grupo)} cursos, {grupo['aprovados'].sum()} aprovados")
    df.to_csv(ARQUIVO_OCUPACAO, index=False)
    return df


def converter():
    manifesto = pd.read_csv(os.path.join(PASTA_RAW, "manifesto.csv"))
    registros = []
    for _, linha in manifesto.iterrows():
        caminho = os.path.join(RAIZ, linha["arquivo"])
        if linha["ano"] >= 2021 or "ocupacao_" in caminho:
            continue  # quadro de vagas e ocupação: tratados em converter_vagas() e converter_ocupacao()
        if linha["ano"] <= 2015 and caminho.endswith(".htm"):
            novos = ler_html_simples(caminho, int(linha["ano"]))
        elif linha["ano"] == 2016 and caminho.endswith(".htm"):
            novos = ler_html_categorias(caminho, 2016)
        elif linha["ano"] == 2017:
            novos = ler_pdf_categorias(caminho, 2017)
        elif linha["ano"] == 2020:
            novos = ler_pdf_2020(caminho, 2020)
        else:
            # 2016 em PDF repete o HTML; 2019 traz só os convocados para a 2.ª fase (não os inscritos)
            novos = None
        if novos is not None:
            print(f"-> {linha['ano']}: {len(novos)} cursos ({os.path.basename(caminho)})")
            registros += novos
        else:
            print(f"-> {linha['ano']}: formato ainda não suportado ({os.path.basename(caminho)})")

    df = pd.DataFrame(registros)
    df["fonte"] = "NC-UFPR"
    os.makedirs(os.path.dirname(ARQUIVO_SILVER), exist_ok=True)
    df.to_csv(ARQUIVO_SILVER, index=False, quoting=csv.QUOTE_MINIMAL)
    return df


if __name__ == "__main__":
    print("--- Convertendo NC-UFPR raw -> silver ---")
    df = converter()
    print(f"\n--- {len(df)} linhas gravadas em {os.path.relpath(ARQUIVO_SILVER, RAIZ)} ---")
    print("\n--- Quadro de vagas 2021-2026 ---")
    dv = converter_vagas()
    print(f"\n--- {len(dv)} linhas gravadas em {os.path.relpath(ARQUIVO_VAGAS, RAIZ)} ---")
    print("\n--- Ocupação das vagas 2016-2023 ---")
    do = converter_ocupacao()
    print(f"\n--- {len(do)} linhas gravadas em {os.path.relpath(ARQUIVO_OCUPACAO, RAIZ)} ---")
