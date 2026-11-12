# Comparação de modelos de previsão

**Resultado:** com os inscritos do ano já divulgados, o melhor método 1 ano à frente é o nível comum + inscritos, com erro 8% menor que repetir o último ano. Sem esse dado, o nível comum + desvio do curso erra 8% menos que a suavização simples por curso e 20% menos nos cursos abaixo de 3 candidatos por vaga; no geral, empata com repetir o último ano.

Reproduzir: `python -W ignore -m analises.comparacao_modelos` (detalhe por par em `resultados_comparacao_modelos.csv`).

## Como foi testado

- 12 anos de corte (2012–2017 e 2020–2025): cada método só vê os dados até o corte e prevê os anos seguintes.
- Todos os métodos são avaliados nos mesmos pares curso-ano.
- A diferença contra "repetir o último ano" tem intervalo de 95% por bootstrap de cursos.

## Erro absoluto em candidatos por vaga, 1 ano à frente

| Método | Todos (966 pares) | Cortes 2020–2025 (607) | Cortes 2023–2025 (319) | Abaixo de 3 cand/vaga (429) |
|---|---|---|---|---|
| **Nível comum + desvio** | **1,060** | **0,777** | **0,572** | **0,387** |
| Repetir o último ano | 1,069 | 0,789 | 0,589 | 0,406 |
| Suavização com alfa único | 1,129 | 0,868 | 0,589 | 0,427 |
| Suavização por curso (modelo anterior) | 1,151 | 0,912 | 0,637 | 0,483 |
| Combinação (ridge + suavização) | 1,193 | 0,895 | 0,612 | 0,430 |
| Ridge em painel | 1,301 | 0,948 | 0,671 | 0,442 |
| Holt amortecido | 1,347 | 1,071 | 0,765 | 0,592 |
| Média de 3 anos | 1,368 | 1,166 | 0,701 | 0,513 |
| Árvores (gradient boosting) em painel | 1,467 | 1,132 | 0,827 | 0,484 |

Diferença do novo modelo contra "repetir o último ano":

| Recorte | Diferença | Intervalo de 95% | Leitura |
|---|---|---|---|
| Todos | −0,009 | −0,040 a 0,021 | empate |
| Cortes 2020–2025 | −0,013 | −0,039 a 0,012 | empate |
| Cortes 2023–2025 | −0,017 | −0,048 a 0,011 | empate |
| Abaixo de 3 cand/vaga | −0,019 | −0,029 a −0,010 | ganho pequeno, mas claro |

Em 2 e 3 anos à frente, ele não ganha de repetir o último ano: 1,445 contra 1,413 (intervalo de 0,000 a 0,065) e 1,726 contra 1,714 (intervalo de −0,020 a 0,047).

Para identificar quem fica abaixo de 1, 1 ano à frente: encontra 81% dos casos e acerta 85% dos alertas. Repetir o último ano fica em 80% e 83%; o modelo anterior, em 74% e 85%.

## Família ARIMA

**Nenhuma variante de ARIMA errou menos que o nível comum + desvio.** Nos cursos de baixa procura, as variantes ARIMA ajustadas direto na série ficaram claramente atrás dele. Reproduzir: `python -W ignore -m analises.comparacao_arima`.

Mesmos 966 pares, 1 ano à frente, com a série anual em log(1 + cand/vaga) e os anos sem dado tratados como faltantes.

| Método | Todos | Abaixo de 3 cand/vaga | Cursos com 12+ anos |
|---|---|---|---|
| **Nível comum + desvio** | **1,060** | **0,387** | **1,000** |
| Repetir o último ano | 1,069 | 0,406 | 1,008 |
| ARIMA(0,1,1) | 1,095 | 0,417 | 1,035 |
| Nível comum + ARIMA(0,1,1) no desvio | 1,099 | 0,389 | 1,054 |
| ARIMA(1,1,0) | 1,103 | 0,412 | 1,009 |
| ARIMA escolhido por AICc em cada curso | 1,113 | 0,423 | 1,042 |
| Passeio aleatório com tendência (0,1,0) | 1,123 | 0,430 | 1,033 |
| ARIMA(1,1,1) | 1,143 | 0,436 | 1,062 |
| Theta | 1,162 | 0,446 | 1,123 |
| Nível comum + AR(1) no desvio | 1,169 | 0,410 | 1,114 |
| AR(1) | 1,171 | 0,467 | 1,131 |

Diferença contra o nível comum + desvio (positivo = o ARIMA erra mais; intervalo de 95%):

| Método | Todos | Abaixo de 3 cand/vaga |
|---|---|---|
| ARIMA(0,1,1) | +0,035 (−0,008 a 0,083) | +0,030 (0,017 a 0,044) |
| ARIMA(1,1,0) | +0,043 (0,008 a 0,081) | +0,025 (0,009 a 0,041) |
| ARIMA por AICc | +0,053 (−0,001 a 0,124) | +0,036 (0,023 a 0,050) |
| Nível comum + ARIMA(0,1,1) | +0,039 (−0,004 a 0,092) | +0,002 (−0,016 a 0,019) |

- **Séries curtas limitam o ARIMA.** São no máximo 21 pontos anuais, e a mediana é de 14 por curso. Estimar coeficientes por curso gera mais ruído que sinal.
- **Em 13,9% dos pares o curso tinha menos de 6 anos de dados**, e o ARIMA repetiu o último ano. Nenhum ajuste falhou nos demais. Restringir aos cursos com 6+ ou 12+ anos não muda a conclusão.
- **SARIMA não se aplica:** os dados são anuais, sem sazonalidade.
- **ARIMA não resolve o longo prazo:** ele não antecipa os choques comuns, como a queda de 2017 a 2021.

## Modelo hierárquico, ARIMAX e inscritos do ano

**O melhor resultado 1 ano à frente veio de somar o total de inscritos do ano ao nível comum: erro 8% menor que repetir o último ano.** Ele só serve para o próximo vestibular, depois que a UFPR divulga as inscrições. Reproduzir: `python -W ignore -m analises.comparacao_hierarquico`.

| Método | Todos | Cortes 2023–2025 | Abaixo de 3 cand/vaga | 3 anos à frente |
|---|---|---|---|---|
| **Nível comum + inscritos do ano** | **0,985** | 0,577 | **0,368** | não se aplica |
| Nível comum + desvio | 1,060 | **0,572** | 0,387 | 1,726 |
| Repetir o último ano | 1,069 | 0,589 | 0,406 | **1,714** |
| Hierárquico com tendência por área e local | 1,264 | 0,814 | 0,383 | 2,024 |
| Hierárquico (efeitos mistos) | 1,286 | 0,801 | 0,404 | 2,029 |
| ARIMAX com população de 15 a 19 anos | 1,349 | 0,658 | 0,421 | 4,126 |

Contra repetir o último ano, o ajuste pelos inscritos ganha no geral (−0,084; intervalo de 95% de −0,149 a −0,030) e nos cursos de baixa procura (−0,038; de −0,056 a −0,021). Nos cortes de 2023–2025 há empate (−0,012; de −0,044 a 0,019).

- **Como funciona:** cada 1% a mais de inscritos no total move o nível comum em cerca de 0,91%, estimado só com anos anteriores.
- **Cuidado no teste:** o total vem da soma dos concorrentes por curso, que inclui o próprio curso previsto.
- **Cuidado em 2027:** as inscrições subiram 9% com a prova em fase única, uma mudança que o histórico não cobre.
- **Hierárquico e ARIMAX:** extrapolar tendências por curso aumentou o erro. O ARIMAX ainda usa a projeção de população de 2018 em anos anteriores a ela, o que o favorece, e mesmo assim perdeu.

## Por que ele funciona

A queda de procura é em boa parte comum a todos os cursos e persiste (−28% na mediana de 2020 para 2021). O desvio de cada curso tem mais ruído. O modelo separa as duas partes:

- **Nível comum:** soma das variações medianas de log(1 + cand/vaga), ano a ano. Usa o valor do último ano.
- **Desvio do curso:** suavizado com alfa = 0,8, escolhido só com anos anteriores em cada corte.

## Cuidados

- **Ele foi desenhado depois de ver os resultados dos outros métodos.** O alfa é escolhido sem olhar o futuro, mas a ideia do modelo não. A confirmação limpa virá com o resultado de 2027.
- **Modelos mais complexos perderam.** Ridge e árvores têm poucos dados por curso e não preveem os choques de cada ano.
- **A previsão não tem tendência:** é igual para 2027–2032. Serve para o próximo vestibular, não para projetar anos distantes.
