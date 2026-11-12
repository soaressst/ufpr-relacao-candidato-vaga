# Por que alguns cursos têm poucos candidatos por vaga

**Resultado:** o problema é falta de candidatos, não excesso de vagas. Nos 24 cursos que caíram abaixo de 1 entre 2017 e 2026, os candidatos caíram 76% e as vagas, 4%. A baixa procura se concentra no interior e no litoral, nas engenharias e nas licenciaturas, enquanto saúde e computação seguram a procura total.

Reproduzir: `python -W ignore -m analises.causas_baixa_procura`. Média de 2024–2026 contra as vagas de referência. São associações nos dados, não prova de causa.

## A queda veio dos candidatos

Nos 96 cursos com dados em 2017 e em 2026:

| | 2017 | 2026 | Variação |
|---|---|---|---|
| Candidatos | 45.026 | 34.581 | −23% |
| Vagas de referência | 4.574 | 4.513 | −1% |

No curso típico, os candidatos caíram 57% e as vagas não mudaram.

## A procura se concentrou

| Área (96 cursos) | Candidatos 2017 | Candidatos 2026 | Variação |
|---|---|---|---|
| Computação | 1.493 | 2.074 | +39% |
| Saúde | 19.957 | 19.898 | 0% |
| Humanas e direito | 6.359 | 4.405 | −31% |
| Artes e design | 1.322 | 810 | −39% |
| Gestão e negócios | 3.434 | 1.777 | −48% |
| Agrárias e ambiente | 1.229 | 595 | −52% |
| Engenharias | 8.478 | 3.991 | −53% |
| Exatas e naturais | 2.505 | 972 | −61% |
| Letras | 249 | 59 | −76% |

Saúde passou de 44% para 58% dos candidatos. Por grau, a licenciatura caiu 62%, o bacharelado 21% e o tecnológico 13%. Por local, o interior e o litoral caíram 40%, e Curitiba 20%.

## Onde estão os cursos abaixo de 1

| Grupo | Cursos | Abaixo de 1 |
|---|---|---|
| Matinhos | 12 | 58% |
| Engenharias | 24 | 50% |
| Palotina | 9 | 44% |
| Jandaia do Sul | 7 | 43% |
| Pontal do Paraná | 7 | 29% |
| Curitiba | 105 | 13% |

Os menores valores: Eng. de Aquicultura em Palotina (0,08), Eng. de Alimentos em Jandaia do Sul (0,17), Eng. de Aquicultura em Pontal (0,19), Eng. de Energia em Palotina (0,24) e Ciências em Matinhos (0,26).

## O que pesa quando se controla o resto

Regressão de log(cand/vaga) em 141 cursos (R² = 0,45), comparando com um bacharelado integral de saúde em Curitiba:

| Característica | Efeito em cand/vaga | p |
|---|---|---|
| Engenharias | −84% | < 0,001 |
| Agrárias e ambiente | −77% | 0,002 |
| Gestão e negócios | −71% | 0,008 |
| Interior e litoral | −57% | 0,001 |
| Tecnológico | −48% | 0,046 |
| Licenciatura | −38% | 0,031 |
| Turno noturno | −26% | 0,295 (não significativo) |
| Número de vagas | sem efeito claro | 0,329 |

Mais da metade da variação (55%) segue sem explicação nestes dados.

## Hipóteses para as causas (ainda não testadas curso a curso)

- **Ensino a distância.** No país, 77% dos ingressantes em licenciatura escolheram EaD, segundo o [Censo divulgado em 2022](https://www.folhape.com.br/noticias/ensino-a-distancia-cresce-474-em-uma-decada-diz-inep/245876/). Em engenharia, o EaD passou de menos de 15% dos ingressos em 2017 para [58% em 2024](https://revistapesquisa.fapesp.br/ead-responde-por-mais-de-50-dos-ingressos-em-engenharia/). Isso combina com as quedas de licenciatura e engenharia.
- **Demografia, só em parte.** Os jovens de 15 a 19 anos no Paraná caíram 16% de 2017 a 2026 ([IBGE, projeção revisão 2018](https://sidra.ibge.gov.br/tabela/7358)). A mediana de candidatos por vaga caiu 57%.
- **Outras portas de entrada.** A própria UFPR oferece vagas remanescentes pelo Enem: [704 em 2024](https://www.bemparana.com.br/noticias/parana/ufpr-abre-inscricoes-para-cursos-de-graduacao-sem-vestibular-e-sem-taxa-de-inscricao/), das quais 230 em Palotina e 125 em Matinhos. O SiSU e outras universidades também concorrem pelos mesmos candidatos; não medimos esse efeito.
- **Campus em cidade pequena.** Morar longe de casa custa caro, e isso pode pesar mais no interior. Com só 5 cidades, os dados não permitem testar.

Para testar melhor: nota de corte e ingressos por modalidade (microdados do Censo da Educação Superior do INEP), e a origem dos candidatos, de forma agregada.

## Cuidados

- 2021–2026 usa os candidatos da base da Liga.
- Ficam de fora da comparação 2017–2026 os cursos com ingresso único de bacharelado e licenciatura, o que tende a subestimar a queda das licenciaturas em Geografia, História, Filosofia e outras.
- As áreas foram agrupadas por nós, a partir dos nomes dos cursos.
