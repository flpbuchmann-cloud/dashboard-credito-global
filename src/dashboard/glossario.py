"""
Glossário e Metodologia do Dashboard de Crédito Global.

Contém o texto completo em Markdown para exibição via st.markdown().
"""

GLOSSARIO_METODOLOGIA = r"""
## 📖 Glossário e Metodologia

> Este glossário explica **todos os indicadores** do dashboard em linguagem acessível.
> Pense nele como um "dicionário" de cada número que você vê nas tabelas e gráficos.
> Os dados são trimestrais e referem-se a **empresas não-financeiras** listadas nos EUA.

---

### 1. DRE — Demonstração do Resultado

A DRE mostra se a empresa está **ganhando ou perdendo dinheiro** nas suas operações, trimestre a trimestre. É como o "extrato de desempenho" do período.

| Indicador | O que é | Como interpretar |
|---|---|---|
| **Receita Líquida** | Tudo que a empresa faturou no trimestre, já descontando devoluções e impostos sobre vendas. | É o ponto de partida — quanto "entrou" de fato. |
| **CPV (Custo dos Produtos Vendidos)** | Quanto custou produzir ou comprar aquilo que foi vendido (matéria-prima, mão de obra direta, etc.). Aparece como valor negativo. | Quanto menor em relação à receita, mais eficiente é a produção. |
| **Resultado Bruto** | Receita Líquida + CPV (que é negativo). É o lucro antes de qualquer despesa administrativa ou comercial. | Mostra se o "negócio principal" da empresa é rentável. |
| **Despesas com Vendas** | Gastos para vender o produto: marketing, comissões, frete de entrega, etc. | Empresas de consumo tendem a ter valores altos aqui. |
| **Despesas G&A** | Despesas Gerais e Administrativas: salários da diretoria, aluguel do escritório, TI, jurídico, etc. | São os custos para "manter a empresa funcionando", independentemente de quanto ela vende. |
| **EBIT** | *Earnings Before Interest and Taxes* — Lucro Operacional. É o resultado depois de todas as despesas operacionais, mas antes de juros e impostos. | Mede a eficiência puramente operacional, sem influência da estrutura de capital. |
| **D&A** | Depreciação e Amortização. Representa o "desgaste" de máquinas, equipamentos e ativos intangíveis. Extraído do fluxo de caixa pois lá aparece de forma consolidada. | É uma despesa contábil (não sai dinheiro do caixa), mas reflete a necessidade futura de reinvestimento. |
| **EBITDA** | EBIT + D&A. Remove o efeito da depreciação para mostrar a geração de caixa operacional "bruta". Calculado de cima para baixo (*top-down*); quando não disponível, usa-se o caminho inverso: LL + Desp.Fin. + IR + D&A (*bottom-up*). | É o indicador mais usado por analistas de crédito para medir capacidade de pagamento. Pense nele como o "oxigênio financeiro" da empresa. |
| **Resultado Financeiro** | Saldo entre receitas financeiras (rendimento de aplicações) e despesas financeiras (juros de dívidas). | Se negativo, a empresa paga mais juros do que ganha com aplicações — normal para empresas alavancadas. |
| **Receitas Financeiras** | Rendimentos de aplicações, ganhos cambiais, etc. | Costuma ser pequeno em relação à receita operacional. |
| **Despesas Financeiras** | Juros pagos sobre dívidas, perdas cambiais, custos de captação. | Quanto maior, mais "pesada" é a dívida da empresa. |
| **Lucro Antes do IR** | Resultado após somar o resultado financeiro ao EBIT. | Mostra o lucro antes do governo "tirar a parte dele". |
| **IR/CSLL** | Imposto de Renda e contribuições. Nos EUA, a taxa federal corporativa é 21%. | Valores muito diferentes de 21% podem indicar benefícios fiscais, prejuízos acumulados ou itens extraordinários. |
| **Lucro Líquido** | O que sobra de fato para os acionistas, depois de todas as despesas, juros e impostos. | É o "resultado final" — mas atenção: lucro líquido não é a mesma coisa que dinheiro em caixa. |

#### Margens (%)

Margens transformam valores absolutos em percentuais da receita, permitindo comparar empresas de tamanhos diferentes.

| Margem | Fórmula | O que revela |
|---|---|---|
| **Margem Bruta** | Resultado Bruto / Receita | Poder de precificação e eficiência produtiva. Tech costuma ter >60%; commodities, <30%. |
| **Margem EBIT** | EBIT / Receita | Eficiência operacional total, incluindo despesas administrativas e comerciais. |
| **Margem EBITDA** | EBITDA / Receita | Capacidade de geração de caixa operacional em relação ao faturamento. |
| **Margem Líquida** | Lucro Líquido / Receita | Quanto de cada real faturado vira lucro de fato para o acionista. |

#### Crescimento (Growth)

| Métrica | Significado |
|---|---|
| **QoQ (Quarter-over-Quarter)** | Variação em relação ao **trimestre imediatamente anterior**. Captura tendência de curto prazo, mas sofre efeito de sazonalidade. |
| **YoY (Year-over-Year)** | Variação em relação ao **mesmo trimestre do ano anterior**. Elimina sazonalidade e é a métrica preferida para avaliar crescimento real. |

---

### 2. Fluxo de Caixa

Enquanto a DRE mostra o lucro "contábil", o fluxo de caixa mostra o **dinheiro de verdade** que entrou e saiu. Uma empresa pode ter lucro e estar sem caixa (e vice-versa).

| Indicador | O que é | Como interpretar |
|---|---|---|
| **FCO (Fluxo de Caixa Operacional)** | Dinheiro gerado (ou consumido) pelas operações do dia a dia: vender, cobrar, pagar fornecedores, salários, impostos. | Se negativo por vários trimestres seguidos, a empresa está "queimando caixa" — sinal de alerta. |
| **Capex** | *Capital Expenditure* — investimento em ativos fixos (fábricas, equipamentos, tecnologia). Aparece como valor negativo. | Empresas em crescimento ou capital-intensivas (petróleo, telecom) têm Capex alto. |
| **FCL (Fluxo de Caixa Livre)** | FCO + Capex. É o dinheiro que sobra depois de manter e expandir as operações. | É o caixa "disponível" para pagar dívida, distribuir dividendos ou fazer aquisições. Indicador-chave para crédito. |
| **FCO/EBITDA** | Conversão de caixa: quanto do EBITDA vira dinheiro de verdade. | Idealmente >70%. Se consistentemente baixo, o EBITDA pode estar "inflado" por itens não-caixa ou variações de capital de giro. |
| **FCO/Receita** | Percentual da receita que vira caixa operacional. | Complementa a margem EBITDA com uma visão de caixa real. |
| **FCL/Receita** | Percentual da receita que vira caixa livre. | Empresas com >10% costumam ter boa flexibilidade financeira. |
| **Capex/Receita** | Intensidade de investimento em relação ao faturamento. | Setores como petróleo e mineração costumam ficar entre 15-30%. |
| **Juros Pagos** | Desembolso efetivo de juros no período (regime de caixa, não de competência). | Pode diferir da despesa financeira da DRE por causa de juros capitalizados ou diferenças de timing. |
| **Amortização de Dívida** | Pagamento do principal de dívidas que venceram no período. | Junto com juros, mostra o "peso" total do serviço da dívida. |
| **Captação** | Novas dívidas contratadas no período. | Se consistentemente maior que a amortização, a empresa está aumentando seu endividamento. |
| **Dividendos** | Dinheiro distribuído aos acionistas. | Se a empresa paga dividendos altos mesmo com FCL negativo, está financiando dividendos com dívida — risco. |
| **FC de Financiamento** | Saldo líquido de captações, amortizações, dividendos e recompra de ações. | Negativo = empresa está devolvendo mais capital do que captando (geralmente positivo para crédito). |

---

### 3. Estrutura de Capital

Mostra **de onde vem o dinheiro** que financia a empresa: dívida (capital de terceiros) ou patrimônio líquido (capital dos sócios).

| Indicador | O que é | Como interpretar |
|---|---|---|
| **Caixa** | Dinheiro em conta corrente e aplicações de liquidez imediata. | É a "reserva de emergência" da empresa. |
| **Aplicações Fin. CP** | Investimentos de curto prazo (CDBs, títulos, *money market*). | Facilmente conversíveis em caixa. |
| **Liquidez Total** | Caixa + Aplicações Fin. CP. | Representa todo o dinheiro prontamente disponível. |
| **Dívida CP (Curto Prazo)** | Dívidas que vencem nos próximos 12 meses. | Dívida CP alta em relação à Liquidez Total é um risco de refinanciamento. |
| **Dívida LP (Longo Prazo)** | Dívidas com vencimento acima de 12 meses (bonds, empréstimos). | Geralmente é a maior parte da dívida. Prazo longo dá mais previsibilidade. |
| **Dívida Bruta** | Dívida CP + Dívida LP. Tudo que a empresa deve a credores financeiros. | Não inclui fornecedores nem obrigações trabalhistas/fiscais. |
| **Dívida Líquida** | Dívida Bruta − Liquidez Total. Desconta o caixa disponível. | É a métrica padrão de endividamento. Se negativa, a empresa tem mais caixa do que dívida (posição confortável). |
| **PL (Patrimônio Líquido)** | Valor contábil que pertence aos acionistas: capital social + lucros acumulados − prejuízos. | Se negativo, a empresa deve mais do que possui — situação crítica. |

**Gráficos desta seção:**
- **Composição da Dívida (CP vs LP):** Mostra quanto da dívida vence em breve vs. no longo prazo.
- **Dívida vs Receita:** Contextualiza o tamanho da dívida em relação ao faturamento.
- **Dívida Líquida vs Alavancagem:** Evolução do endividamento ao longo do tempo.

---

### 4. Capital de Giro

O capital de giro mostra a **saúde do ciclo operacional** — o tempo entre pagar fornecedores e receber dos clientes. Pense como o "fluxo de sangue" da operação diária.

| Indicador | O que é | Como interpretar |
|---|---|---|
| **Contas a Receber (AR)** | Vendas já realizadas mas ainda não recebidas em dinheiro. | Valores crescentes podem indicar clientes demorando mais para pagar ou reconhecimento agressivo de receita. |
| **Estoques** | Produtos acabados, em processo ou matérias-primas esperando para ser vendidos. | Estoques crescendo muito mais rápido que a receita pode indicar dificuldade de vender. |
| **Fornecedores (AP)** | Compras de matérias-primas/serviços ainda não pagas. | Prazos maiores com fornecedores aliviam a necessidade de capital de giro (é um "financiamento espontâneo"). |
| **Capital de Giro** | AR + Estoques − Fornecedores. Quanto a empresa precisa financiar do seu ciclo operacional. | Positivo = a empresa precisa de capital para financiar o intervalo entre pagar e receber. Negativo = o ciclo se autofinancia (comum em varejo). |

#### Prazos Médios (em dias) — calculados sobre o acumulado dos últimos 12 meses (LTM)

| Prazo | Fórmula | Significado |
|---|---|---|
| **DSO** (*Days Sales Outstanding*) | Contas a Receber / (Receita LTM / 360) | Quantos dias, em média, a empresa leva para **receber** dos clientes. |
| **DIO** (*Days Inventory Outstanding*) | Estoques / (Custo LTM / 360) | Quantos dias o estoque fica "parado" antes de ser vendido. |
| **DPO** (*Days Payables Outstanding*) | Fornecedores / (Custo LTM / 360) | Quantos dias a empresa leva para **pagar** seus fornecedores. |
| **Ciclo de Conversão de Caixa (CCC)** | DSO + DIO − DPO | Quantos dias a empresa precisa financiar entre o pagamento de insumos e o recebimento de vendas. Quanto menor (ou mais negativo), melhor. |

---

### 5. Múltiplos e Indicadores de Crédito

São os **índices que os analistas de crédito e agências de rating mais olham** para avaliar se uma empresa consegue honrar suas dívidas. Os valores usam o acumulado dos últimos 12 meses (**LTM** — *Last Twelve Months*) para suavizar sazonalidade.

#### Alavancagem

| Indicador | Fórmula | O que mede | Referência geral |
|---|---|---|---|
| **DL/EBITDA** | Dívida Líquida / EBITDA LTM | Quantos anos de geração de caixa operacional seriam necessários para quitar a dívida líquida. | <2x: conservador · 2-3x: moderado · >4x: elevado |
| **DL/FCO** | Dívida Líquida / FCO LTM | Mesma lógica, mas usando o caixa operacional real (não o EBITDA teórico). | Complementa DL/EBITDA quando há distorções no EBITDA. |
| **DL/Receita** | Dívida Líquida / Receita LTM | Quanto da dívida líquida equivale ao faturamento anual. | Útil para setores onde EBITDA é volátil (commodities). |

#### Cobertura de Juros e Serviço da Dívida

| Indicador | Fórmula | O que mede |
|---|---|---|
| **Cobertura de Juros (EBITDA)** | EBITDA LTM / max(Juros Pagos, Desp. Financeiras) LTM | Quantas vezes o EBITDA cobre o pagamento de juros. Usa o maior entre juros pagos (caixa) e despesa financeira (competência) para ser conservador. Abaixo de 2x é preocupante. |
| **Cobertura de Juros (EBIT)** | EBIT LTM / mesmo denominador | Versão mais conservadora, pois não adiciona D&A de volta. |
| **DSCR** (*Debt Service Coverage Ratio*) | FCO LTM / (Amortização + Juros Pagos) LTM | Capacidade de pagar juros **e** principal com o caixa gerado. Abaixo de 1x significa que a empresa não gera caixa suficiente para cobrir o serviço da dívida. |

#### Estrutura e Solvência

| Indicador | Fórmula | O que mede |
|---|---|---|
| **Multiplicador de PL** (*Equity Multiplier*) | Ativo Total / PL | Quanto dos ativos é financiado por PL. Quanto maior, mais alavancada. Um valor de 3x significa que para cada R$ 1 dos sócios, há R$ 3 em ativos (ou seja, R$ 2 de dívida/passivos). |
| **Debt-to-Assets** | Dívida Bruta / Ativo Total | Que fração dos ativos é financiada por dívida financeira. |
| **Dív.CP / Dív.Total** | Dívida CP / Dívida Bruta | Concentração no curto prazo. Quanto maior, mais risco de refinanciamento. |
| **Dív.Total/PL** | Dívida Bruta / PL | Relação entre capital de terceiros (financeiro) e capital próprio. |

#### Liquidez

| Indicador | Fórmula | O que mede |
|---|---|---|
| **Liquidez Corrente** | Ativo Circulante / Passivo Circulante | Para cada R$ 1 que a empresa deve no curto prazo, quanto ela tem de ativo realizável no curto prazo. Acima de 1x é o mínimo esperado. |
| **Liquidez Seca** | (Ativo Circulante − Estoques) / Passivo Circulante | Igual à corrente, mas exclui estoques (que podem ser difíceis de vender rapidamente). |
| **Cash Ratio** | Liquidez Total / Passivo Circulante | A versão mais conservadora: considera apenas caixa e aplicações de curtíssimo prazo. |
| **Solvência Geral** | Ativo Total / (Passivo Circulante + Passivo Não Circulante) | Capacidade da empresa de pagar **todos** os seus passivos com todos os seus ativos. Abaixo de 1x = patrimônio líquido negativo. |

#### Outros

| Indicador | Fórmula | O que mede |
|---|---|---|
| **Custo da Dívida** | Despesas Financeiras LTM / média(Dívida Bruta dos 2 últimos trimestres) | Taxa de juros efetiva que a empresa paga sobre sua dívida. Permite comparar com o custo de mercado e avaliar se está favorável. |
| **Capex/EBITDA** | Capex LTM / EBITDA LTM | Quanto da geração de caixa é reinvestida em ativos fixos. Se muito alto (>80%), sobra pouco para pagar dívida. |
| **Payout** | Dividendos LTM / Lucro Líquido LTM | Quanto do lucro é distribuído aos acionistas. Payout muito alto + alavancagem elevada é um sinal de alerta. |

---

### 6. ROIC, WACC e EVA — Criação de Valor

Estes indicadores respondem à pergunta fundamental: **a empresa gera retorno acima do custo do capital que utiliza?**

| Indicador | Fórmula | O que é |
|---|---|---|
| **Taxa Marginal de IR** | 21% (fixa) | Taxa federal de imposto de renda corporativo nos EUA, conforme referências de McKinsey e Assaf Neto. Usada para ajustar o EBIT ao efeito fiscal. |
| **NOPAT** | EBIT LTM × (1 − 21%) | *Net Operating Profit After Taxes* — lucro operacional ajustado por impostos, sem influência da estrutura de capital. É o "lucro puro" da operação. |
| **Capital Investido** | Média de (Dívida Líquida + PL) dos últimos 2 trimestres | Todo o capital empregado na operação, tanto de credores quanto de acionistas. Exclui caixa excedente (que não está "trabalhando" na operação), conforme metodologia McKinsey. |
| **ROIC** | NOPAT / Capital Investido | Retorno sobre o capital investido. Quanto a empresa gera de lucro operacional para cada R$ 1 investido. |
| **WACC** | E/(E+D) × Re + D/(E+D) × Rd × (1−21%) | Custo médio ponderado de capital. O "mínimo" que a empresa precisa gerar para remunerar credores e acionistas. Neste dashboard: Re = 10% (custo do equity, fixo) e Rd = custo efetivo da dívida, com pesos a valor contábil. |
| **EVA** | (ROIC − WACC) × Capital Investido | *Economic Value Added*. Se positivo, a empresa gera valor acima do custo do capital — está "criando riqueza". Se negativo, está destruindo valor, mesmo que tenha lucro contábil. |

> **Simplificações adotadas:** O custo do equity (Re) é fixo em 10%, e os pesos de dívida/equity são por valor contábil (não de mercado). São aproximações úteis para análise de crédito comparativa, não para valuation preciso.

---

### 7. Modelo Fleuriet — Análise Dinâmica do Capital de Giro

O modelo Fleuriet (ou modelo dinâmico) classifica a **saúde financeira de curto prazo** da empresa em 6 tipos, com base em três variáveis. É amplamente usado na análise de crédito brasileira.

| Variável | Fórmula | Significado |
|---|---|---|
| **CDG** (Capital de Giro) | PL + Passivo Não Circulante − Ativo Não Circulante | Capital permanente (longo prazo) que sobra para financiar as operações de curto prazo. Pense como a "folga financeira estrutural". |
| **NCG** (Necessidade de Capital de Giro) | (Contas a Receber + Estoques) − (Fornecedores + Obrigações Fiscais CP) | Quanto a operação diária demanda de recursos. Se positiva, a empresa precisa de financiamento para o ciclo operacional. |
| **T** (Saldo de Tesouraria) | CDG − NCG | O que sobra (ou falta) de recursos de longo prazo depois de cobrir a necessidade operacional. Tesouraria negativa indica dependência de crédito de curto prazo — vulnerabilidade. |

#### Classificação e Score (1 a 10)

| Tipo | CDG | NCG | T | Score | Situação | Descrição |
|---|---|---|---|---|---|---|
| **I** | + | − | + | 9–10 | Excelente | A operação gera caixa (NCG negativa) e sobra capital de longo prazo. Situação ideal. |
| **II** | + | + | + | 6–8 | Sólida | A empresa tem capital de longo prazo suficiente para cobrir a necessidade operacional, e ainda sobra tesouraria. |
| **III** | + | + | − | 4–5 | Insatisfatória | O capital de longo prazo existe mas não cobre toda a necessidade operacional. Depende de crédito de curto prazo para fechar a conta. |
| **IV** | − | − | + | 4 | Alto Risco | Tesouraria positiva, mas capital de longo prazo é negativo. A empresa financia ativos de longo prazo com recursos de curto prazo — risco estrutural. |
| **V** | − | − | − | 3 | Muito Ruim | Capital de giro e tesouraria negativos. A empresa depende fortemente de crédito de curto prazo. |
| **VI** | − | + | − | 1–2 | Péssima | Pior cenário. Capital de giro negativo, operação demanda recursos, e não há folga de tesouraria. Risco iminente de insolvência. |

> O score dentro de cada faixa varia conforme a **magnitude relativa** das variáveis (por exemplo, no Tipo II, um T muito maior que NCG eleva o score para 8).

---

### 8. Cronograma de Vencimento da Dívida

O gráfico de barras mostra o **perfil de amortização** da dívida ao longo dos próximos anos, comparado ao caixa disponível.

**Como ler o gráfico:**
- Cada barra representa o volume de dívida que vence naquele ano.
- A linha ou barra de referência mostra o caixa/liquidez total atual.
- **"Muro de vencimentos"** (*maturity wall*): anos com concentração alta de vencimentos representam risco de refinanciamento — a empresa precisará rolar ou pagar aquele volume de uma vez.

**O que observar:**
- A empresa tem caixa suficiente para cobrir os vencimentos dos próximos 1-2 anos?
- Há concentração perigosa em algum ano específico?
- Os vencimentos estão bem distribuídos ao longo do tempo?

> O cronograma é extraído diretamente dos *filings* (relatórios) publicados pela empresa na SEC, via parsing de tabelas HTML.

---

### 9. Fontes dos Dados e Metodologia de Coleta

| Fonte | O que fornece | Prioridade |
|---|---|---|
| **SEC EDGAR — XBRL Company Facts API** | Dados financeiros padronizados (balanço, DRE, fluxo de caixa) reportados trimestralmente (10-Q) e anualmente (10-K) por empresas listadas nos EUA. | Primária — base de todos os indicadores. |
| **Earnings Release via Gemini AI** | Dados complementares extraídos de press releases de resultados usando IA generativa (Google Gemini). Útil quando a empresa publica métricas adicionais não presentes no XBRL. | Suplementar — preenche lacunas. |
| **Financial Supplement** | Suplementos financeiros publicados por algumas empresas com dados operacionais detalhados. | Priorizado quando disponível (mais detalhado). |
| **HTML Filing Parser** | Extração de tabelas de cronograma de vencimento da dívida diretamente dos *filings* depositados na SEC. | Específico para cronograma de amortização. |

> **Periodicidade:** Os dados são trimestrais. Indicadores marcados como **LTM** (*Last Twelve Months*) somam os últimos 4 trimestres para dar uma visão anualizada, eliminando efeito de sazonalidade.

> **Limitações:** Os dados XBRL dependem da padronização adotada por cada empresa ao reportar. Eventualmente, tags diferentes podem ser usadas para conceitos similares, o que pode gerar pequenas discrepâncias.

---

### Tabela de Siglas Rápida

| Sigla | Significado |
|---|---|
| LTM | *Last Twelve Months* — acumulado dos últimos 12 meses (4 trimestres) |
| QoQ | *Quarter-over-Quarter* — variação trimestral sequencial |
| YoY | *Year-over-Year* — variação em relação ao mesmo trimestre do ano anterior |
| CP | Curto Prazo (até 12 meses) |
| LP | Longo Prazo (acima de 12 meses) |
| DL | Dívida Líquida |
| FCO | Fluxo de Caixa Operacional |
| FCL | Fluxo de Caixa Livre (*Free Cash Flow*) |
| PL | Patrimônio Líquido |
| AT | Ativo Total |
| AC | Ativo Circulante |
| PC | Passivo Circulante |
| PNC | Passivo Não Circulante |
| AR | *Accounts Receivable* (Contas a Receber) |
| AP | *Accounts Payable* (Fornecedores) |
| D&A | Depreciação e Amortização |
| DSCR | *Debt Service Coverage Ratio* |
| CCC | Ciclo de Conversão de Caixa |
| ROIC | *Return on Invested Capital* |
| WACC | *Weighted Average Cost of Capital* |
| EVA | *Economic Value Added* |
| NOPAT | *Net Operating Profit After Taxes* |
| CDG | Capital de Giro (no contexto Fleuriet) |
| NCG | Necessidade de Capital de Giro |
| T | Saldo de Tesouraria |
"""
