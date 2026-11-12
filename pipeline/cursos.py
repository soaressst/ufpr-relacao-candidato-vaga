import os
import re
import unicodedata

import pandas as pd

# Padronização dos nomes de curso do NC-UFPR, que mudaram de formato ao longo dos anos:
#   2003–2018: "Agronomia - Campus Palotina - MT"
#   2019:      "Administração Pública - N (Bacharelado) - Campus Matinhos"
#   2020+:     "Administração Pública - Bacharelado - Matinhos - PR - N"
# A chave (nome, grau, cidade, turno) permite juntar as séries de um mesmo curso.

GRAUS = {
    "bacharelado": "Bacharelado",
    "licenciatura": "Licenciatura",
    "tecnologico": "Tecnológico",
    "formacao do tecnologo": "Tecnológico",
    "licenciatura/bacharelado": "Licenciatura/Bacharelado",
    "bacharelado/licenciatura": "Licenciatura/Bacharelado",
}

# MT (antigo) e I (M+V) (novo) são o mesmo período integral manhã + tarde
TURNOS = {
    "M": "M", "T": "T", "V": "T", "N": "N",
    "MT": "I", "I (M+V)": "I", "I (M+T)": "I", "I": "I",
    "M(+T)": "I", "T(+M)": "I", "M(+T)/T(+M)": "I", "M(+T) - T(+M)": "I",
    "MN": "MN", "I (M+N)": "MN",
    "TN": "TN", "I (V+N)": "TN", "I (T+N)": "TN", "T(+N)": "TN",
    "MTN": "MTN", "EAD": "EaD",
}


def _sem_acento(texto):
    texto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in texto if not unicodedata.combining(c))


def _limpa(texto):
    # Remove números de nota de rodapé grudados no nome ("Biológicas20", "Madeireira44")
    texto = re.sub(r"(?<=[A-Za-zÀ-ÿ\)])\d+\b", "", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _normaliza_nome(nome):
    nome = _sem_acento(nome).lower()
    nome = re.sub(r"[^a-z0-9()/ ]", " ", nome)
    nome = re.sub(r"\s*/\s*", "/", nome)
    return re.sub(r"\s+", " ", nome).strip()


# Variações do nome da cidade entre edições
CIDADES = {"Jandaia": "Jandaia do Sul"}


def _turno(texto):
    t = re.sub(r"\s+", " ", texto.strip().upper())
    return TURNOS.get(t, TURNOS.get(t.replace(" ", ""), None))


def _grau(texto):
    return GRAUS.get(_normaliza_nome(texto))


def chave_curso(curso):
    """Devolve (nome, grau, cidade, turno). grau/cidade/turno podem ser None quando o formato não informa."""
    if not isinstance(curso, str):
        return (None, None, None, None)
    curso = _limpa(curso)
    partes = [p.strip() for p in re.split(r" [-–] ", curso)]

    # ABI (Área Básica de Ingresso) é um ingresso diferente do curso com grau definido
    abi = bool(re.search(r"\bABI\b", curso))
    grau_abi = re.search(r"ABI\s*\((Bacharelado|Licenciatura)\)", curso)

    # Formato 2020+: Nome - Grau - Cidade - PR - Turno
    if len(partes) >= 4 and partes[-2] == "PR":
        turno = _turno(partes[-1])
        cidade = CIDADES.get(partes[-3], partes[-3])
        resto = partes[:-3]
        grau = _grau(resto[-1]) if len(resto) > 1 else None
        nome_partes = resto[:-1] if grau or (len(resto) > 1 and resto[-1] == "ABI") else resto
        nome = " - ".join(nome_partes)
        if grau is None and grau_abi:
            grau = grau_abi.group(1)
        nome = re.sub(r"\s*ABI\s*(\((Bacharelado|Licenciatura)\))?", "", nome)
        if re.search(r"(Licenciatura|Bacharelado)$", nome) and grau is None:
            grau = _grau(nome.split()[-1])
            nome = nome.rsplit(" ", 1)[0]
        return (_normaliza_nome(nome) + (" abi" if abi else ""), grau, cidade, turno)

    # Formatos antigos: extrai "Campus X", "(Grau)" e o turno
    cidade = "Curitiba"
    grau = None
    turno = None
    nome_partes = []
    for p in partes:
        campus = re.match(r"Campus (.+)$", p)
        m_grau = re.match(r"^(.*?)\s*\(([^)]*)\)$", p)
        if campus:
            cidade = CIDADES.get(campus.group(1).strip(), campus.group(1).strip())
        elif _turno(p):
            turno = _turno(p)
        elif m_grau and _turno(m_grau.group(1)) and _grau(m_grau.group(2)):
            # 2019: "N (Bacharelado)"
            turno = _turno(m_grau.group(1))
            grau = _grau(m_grau.group(2))
        else:
            nome_partes.append(p)
    nome = re.sub(r"\s*ABI\s*", " ", " - ".join(nome_partes))
    return (_normaliza_nome(nome) + (" abi" if abi else ""), grau, cidade, turno)


def mapear_historico(df, ano_ref=2026):
    """Acrescenta a coluna Curso_Ref: o nome do curso em `ano_ref` ao qual cada linha do histórico pertence.

    Liga pela chave completa (nome, grau, cidade, turno). Linhas antigas sem grau só são ligadas
    quando (nome, cidade, turno) corresponde a um único curso de `ano_ref`; se houver, por exemplo,
    Bacharelado e Licenciatura com o mesmo nome, a linha antiga fica de fora para não misturar séries.
    Linhas que não se ligam a nenhum curso de `ano_ref` ficam com Curso_Ref vazio.
    """
    df = df.copy()
    chaves = df["Curso"].map(chave_curso)
    df["_chave"] = chaves
    df["_chave3"] = chaves.map(lambda k: (k[0], k[2], k[3]))

    ref = df[df["Ano"] == ano_ref].drop_duplicates("Curso")
    por_chave = {}
    por_chave3 = {}
    for curso, chave in zip(ref["Curso"], ref["_chave"]):
        if chave[0] is None or chave[3] is None:
            continue
        por_chave.setdefault(chave, set()).add(curso)
        por_chave3.setdefault((chave[0], chave[2], chave[3]), set()).add(curso)

    nomes_ref = set(ref["Curso"])

    def ligar(linha):
        # Nome idêntico ao de `ano_ref` liga direto, sem passar pela chave
        if linha["Ano"] == ano_ref or linha["Curso"] in nomes_ref:
            return linha["Curso"] if linha["Curso"] in nomes_ref else None
        alvo = por_chave.get(linha["_chave"], set())
        if len(alvo) == 1:
            return next(iter(alvo))
        if linha["_chave"][1] is None:
            alvo = por_chave3.get(linha["_chave3"], set())
            if len(alvo) == 1:
                return next(iter(alvo))
        return None

    df["Curso_Ref"] = df.apply(ligar, axis=1)
    df = df.drop(columns=["_chave", "_chave3"])
    if ano_ref == ANO_REF_TABELA:
        df = _aplicar_tabela(df)
    return df


# Tabela de correspondência revisada à mão (nome do histórico -> curso de 2026).
# tipo: automatico/confirmado = entra no modelo; duvida = ligação provável, ainda fora até alguém
# confirmar; combinado = ingresso único que em 2026 se divide em mais de um curso; sem_correspondente.
ARQUIVO_CORRESPONDENCIA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                       "data", "ref", "correspondencia_cursos.csv")
ANO_REF_TABELA = 2026
TIPOS_LIGADOS = {"automatico", "confirmado"}


def _aplicar_tabela(df):
    """Substitui Curso_Ref pela tabela de correspondência. Nomes que não estão na tabela (ex.: um
    vestibular novo) mantêm a ligação automática e são avisados para entrarem na tabela."""
    if not os.path.exists(ARQUIVO_CORRESPONDENCIA):
        return df
    tabela = pd.read_csv(ARQUIVO_CORRESPONDENCIA).fillna("")
    destino = dict(zip(tabela["curso_original"],
                       tabela["curso_2026"].where(tabela["tipo"].isin(TIPOS_LIGADOS), "")))
    na_tabela = df["Curso"].isin(destino)
    novos = sorted(df.loc[~na_tabela & (df["Ano"] != ANO_REF_TABELA), "Curso"].unique())
    if novos:
        print(f"Aviso: {len(novos)} nome(s) fora de {os.path.relpath(ARQUIVO_CORRESPONDENCIA)}"
              f" (ligação automática): {novos[:5]}")
    df.loc[na_tabela, "Curso_Ref"] = df.loc[na_tabela, "Curso"].map(destino).replace("", None)
    return df
