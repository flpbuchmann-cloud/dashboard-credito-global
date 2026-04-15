"""
Glossário e Metodologia do Dashboard de Crédito de Financeiras.
"""

GLOSSARIO_METODOLOGIA = r"""
## Como Ler Este Dashboard

Este dashboard avalia a **saúde financeira e de crédito** de empresas financeiras listadas nos EUA,
cobrindo três setores: **Banco**, **Card/Outros** (ex.: AXP) e **Asset Manager** (ex.: BX, KKR, APO).

Todos os valores são **trimestrais** (isolados, não acumulados no ano) salvo quando marcados
**LTM** (Last Twelve Months = soma dos últimos 4 trimestres). Valores anualizados usam o
fator **x4** (trimestre x 4).

---

## 1. DRE (Demonstracao de Resultados)

### Todos os Setores

| Indicador | O que e | Por que importa |
|---|---|---|
| **Receita Total** | Receita liquida consolidada. Em bancos/cards, ja desconta a despesa de juros. | Ponto de partida: se a receita cai, todo o resto tende a piorar. |
| **NII (Net Interest Income)** | Receita de Juros - Despesa de Juros. E a "margem" que o banco ganha ao emprestar. | Principal fonte de receita de bancos. Funciona como a "margem bruta" de uma industria. |
| **Receita Nao-Juros** | Tarifas, comissoes, receita de cartoes, seguros, taxas de gestao. | Diversificacao: menos dependencia de juros = receita mais estavel. |
| **Provisao p/ Credito** | Reserva que o banco separa para cobrir calotes esperados (PDD). | Sobe quando a carteira piora; consome diretamente o lucro. |
| **Despesas Operacionais** | NoninterestExpense: salarios, tecnologia, aluguel, etc. | Indica eficiencia da operacao. |
| **Efficiency Ratio** | Despesas Op / (NII + Receita Nao-Juros). | Quanto menor, melhor. **<55%** excelente; **55-65%** aceitavel; **>65%** banco obeso. |
| **Lucro Liquido** | Resultado final, apos todas as despesas, juros e impostos. | O que sobra para o acionista. |

### Banco (exclusivos)

| Indicador | O que e | Por que importa |
|---|---|---|
| **PPNR (Pre-Provision Net Revenue)** | NII + Receita Nao-Juros - Despesas Operacionais. | O "EBITDA do banco": prova se a operacao gera caixa *antes* de pagar a conta dos calotes. Bancos ruins tem PPNR fraco e sobrevivem manipulando reservas. |

### Card/Outros e Asset Manager (exclusivos)

| Indicador | O que e | Por que importa |
|---|---|---|
| **EBIT** | Lucro operacional antes de juros e impostos. | Mede a eficiencia operacional pura. |
| **EBITDA** | EBIT + Depreciacao & Amortizacao. | "Geracao de caixa operacional aproximada." Principal metrica para credores. |
| **Margens (EBIT, EBITDA, Liquida)** | Cada lucro acima dividido pela receita, em %. | Permite comparar rentabilidade entre empresas de tamanhos diferentes. |

---

## 2. Rentabilidade e Eficiencia (Card/Outros e Asset Manager)

| Indicador | Formula | Interpretacao |
|---|---|---|
| **ROE** | Lucro Liquido (x4) / PL Medio | Retorno sobre o capital dos acionistas. |
| **ROA** | Lucro Liquido (x4) / Ativo Total Medio | Retorno sobre todos os ativos. Bancos operam com ROA baixo (0,5-1,5%) pela alta alavancagem. |
| **NIM** | NII (x4) / Ativo Total Medio | "Spread" que o banco ganha sobre seus ativos. |
| **Equity Multiplier** | AT Medio / PL Medio | Grau de alavancagem. Bancos tipicamente 10-12x. |
| **Decomposicao DuPont** | ROE = ROA x Equity Multiplier | Separa o retorno em eficiencia (ROA) e alavancagem. |

---

## 3. Fluxo de Caixa (Card/Outros e Asset Manager)

*Nao exibido para Bancos - a estrutura de caixa bancaria e diferente de empresas tradicionais.*

| Indicador | O que e | Referencia |
|---|---|---|
| **FCO** | Fluxo de Caixa Operacional. | Positivo e consistente = negocio autossustentavel. |
| **FCL** | FCO + Capex. Caixa livre apos investimentos. | Positivo = sobra caixa para pagar divida e dividendos. |
| **FCO/EBITDA** | Conversao de caixa. | Perto de 100% = saudavel. |
| **Dividendos / Recompra** | Retorno de capital ao acionista. | Compromissos de caixa recorrentes. |

---

## 4. Estrutura de Capital (Card/Outros e Asset Manager)

*Nao exibido para Bancos - bancos usam metricas regulatorias de capital (CET1, SLR).*

| Indicador | O que e | Referencia |
|---|---|---|
| **Divida Bruta / Liquida** | Total de obrigacoes financeiras, com e sem desconto de caixa. | < 2x EBITDA confortavel; > 3,5x risco elevado. |
| **Tangible Book Value** | PL - Intangiveis. | Valor conservador: exclui ativos que "evaporam" em crise. |
| **Interest Coverage** | EBITDA LTM / Despesas Financeiras LTM. | Capacidade de pagar juros. > 3x saudavel. |

---

## 5. Metricas Exclusivas -- Banco

Estas secoes aparecem **somente para empresas classificadas como Banco** e seguem o ranking de 20 indicadores para analise bancaria.

### I. Capital e Solvencia

Bancos precisam manter "colchoes" de capital para absorver perdas. Os reguladores (Basel III) definem minimos.

| Indicador | Formula | Referencia |
|---|---|---|
| **CET1 Ratio** | Common Equity Tier 1 / RWA (Standardized). | Capital de mais alta qualidade vs ativos ponderados por risco. **>11,5%** benchmark. Linha regulatoria minima: 10,5% (com buffers). |
| **Tier 1 Ratio** | Tier 1 Capital / RWA. | Inclui CET1 + instrumentos adicionais (AT1). |
| **Total Capital Ratio** | Capital Total (Tier 1 + Tier 2) / RWA. | Camada mais ampla de protecao. |
| **SLR (Supplementary Leverage Ratio)** | Tier 1 / Total de Ativos (sem ponderacao). | Trava de seguranca: impede que bancos escondam risco usando ponderacao. **>5%** para G-SIBs. |
| **RWA ($)** | Risk-Weighted Assets em dolares. | Tamanho "real" do balanco ajustado por risco. Derivado do supplement ou calculado: PL / Tier1 Ratio. |
| **RWA Density** | RWA / Ativo Total. | Perfil de risco: ~20% custodias (BNY), ~35-50% bancos universais (JPM). Se cai de repente, investigar. |
| **Tangible Book Value** | PL - Intangiveis. | Colchao real de capital excluindo goodwill. |

> **Graficos**: Evolucao QoQ dos ratios regulatorios + CET1 com linha minima regulatoria + RWA em $B + RWA Density.

### II. Liquidez e Qualidade do Funding

| Indicador | O que e | Referencia |
|---|---|---|
| **CASA Ratio** | Depositos Nao-Remunerados / Total Depositos. | A maior vantagem competitiva (moat). Bancos com 30-40% amassam a concorrencia quando juros sobem. BNY usa depositos medios do Financial Supplement. |
| **Loan-to-Deposit** | Emprestimos / Depositos. | O "oxigenio" do banco. **70-85%** ideal. >100% = refem de divida de atacado. |
| **LCR (Liquidity Coverage Ratio)** | HQLA / Saidas Liquidas de Caixa em 30 dias. | O banco aguenta 30 dias de panico total? Regulador exige >100%. **>115%** e confortavel. |
| **NSFR (Net Stable Funding Ratio)** | Funding Estavel Disponivel / Funding Estavel Requerido. | Mede se o banco financia ativos de longo prazo com recursos de longo prazo. >100% obrigatorio. |
| **Spread LCR - NSFR** | LCR - NSFR. | Se negativo (NSFR > LCR), o funding de longo prazo e mais confortavel que a liquidez de curto prazo. |
| **Composicao de Depositos** | Grafico: Non-Interest-Bearing, IB Domestico, IB Internacional. | Depositos estrangeiros tendem a ser mais volateis. NIB e o "dinheiro gratis". |

> **Grafico LCR vs NSFR**: Linhas de evolucao com spread e linha regulatoria minima (100%).

### III. Qualidade de Credito e Inadimplencia

A carteira de emprestimos e o coracao do banco. Estas metricas medem o "estrago" dos calotes.

| Indicador | O que e | Referencia |
|---|---|---|
| **Carteira Bruta** | Total de emprestimos concedidos antes de provisoes. | Tamanho da exposicao de credito. |
| **Loan Growth YoY** | Crescimento da carteira vs mesmo tri do ano anterior. | Se cresce muito acima do PIB, o banco pode estar afrouxando criterios ("selecao adversa"). A fatura chega em 18-24 meses via NCOs. |
| **Reserve / Loans** | Provisao Acumulada (ACL) / Carteira Bruta. | O "bunker" da crise. Na crise de 2008, quem operava abaixo de 1,5% faliu. O banco quer crescer? Otimo, mas esse indice nao pode cair. |
| **NPL (Nonaccrual)** | Emprestimos em que o banco parou de reconhecer juros. | Complementado por NPA (Nonperforming Assets) do Financial Supplement quando indisponivel no XBRL. |
| **Coverage (ACL/NPL)** | Provisao Acumulada / NPL. | E como um seguro: **>100%** = banco ja guardou dinheiro suficiente para cobrir todos os calotes atuais. **>130%** para bancos de cartao (sem garantia). |
| **Texas Ratio** | NPL / (TCE + ACL). | "O teste zumbi." **>50%** alerta vermelho; **>100%** = banco zumbi (calotes excedem reservas + capital). |
| **NCO Ratio** | Net Charge-Offs (anualizados) / Emprestimos Medios. | A perda nua e crua: divida que o banco jogou a toalha e baixou a prejuizo. Mede a (in)competencia real da mesa de credito. *Dados do Financial Supplement.* |
| **Provision / NCOs** | Provisao trimestral / Net Charge-Offs. | A bussola da diretoria. >1x = provisionando mais do que perde (conservador). <1x = consumindo reservas do passado para maquiar lucro. *Dados do Financial Supplement.* |
| **Provision Ratio** | Provisao (DRE trimestral) / Receita. | Quanto da receita e "comida" por novas provisoes no trimestre. |

### IV. Rentabilidade e Eficiencia Bancaria

| Indicador | O que e | Referencia |
|---|---|---|
| **RoTCE** | LL (x4) / Tangible Common Equity Medio. | **A metrica soberana.** Mede retorno sobre capital tangivel (exclui goodwill). **>15%** excelencia; **<10%** destruindo valor. |
| **ROE / ROA** | Retornos classicos (anualizados sobre medias). | ROA de 1%+ e solido para bancos. ROE = ROA x Equity Multiplier (DuPont). |
| **NIM (Net Interest Margin)** | Do Financial Supplement: NII / Average Earning Assets. | O rei da intermediacao. Quando vem do supplement, usa *earning assets* reais (nao proxy com ativo total). 2-3% tipico. |
| **Risk-Adjusted NIM** | (NII - Provisao) x 4 / AT Medio. | NIM "limpa": desconta o custo dos calotes. De que adianta cobrar 20% no cartao se o calote come 16%? |
| **Asset Yield** | Taxa media que os ativos rendosos geram. | Se sobe furiosamente, o banco pode estar saindo de clientes Prime para subprime. *Financial Supplement.* |
| **Cost of IB Deposits** | Taxa media paga nos depositos remunerados. | A "dor do financiamento." Banco que segura esse custo sem perder clientes tem poder de marca. *Financial Supplement.* |
| **Cost of All Deposits** | Cost IB Deposits x (IB Deposits / Total Deposits). | Custo diluido incluindo depositos gratis (NIB). Quanto menor, mais competitivo. |
| **Interest Spread** | Asset Yield - Cost of IB Liabilities. | Diferenca bruta entre o que cobra e o que paga. O NIM e superior porque inclui o efeito diluidor do NIB. *Financial Supplement.* |
| **PPNR** | NII + Receita Nao-Juros - Opex. | O "EBITDA bancario." Se o PPNR nao cobre a provisao, o banco esta em estresse. |
| **Efficiency Ratio** | Opex / (NII + Receita Nao-Juros). | **<55%** excelente; **55-65%** aceitavel; **>65%** banco obeso. |
| **Operating Leverage YoY** | Crescimento% Receita - Crescimento% Opex. | A "trajetoria da tesoura." Positivo = banco ganhando escala. Negativo = custos subindo mais rapido que receita. |
| **Payout (LTM)** | Dividendos 12m / Lucro 12m. | Bancos com CET1 robusto distribuem >40%. Se muito alto com CET1 baixo, e insustentavel. |

> **Graficos**: RoTCE/ROE/ROA + NIM vs Risk-Adj NIM + Operating Leverage (barras verde/vermelho) + Efficiency com benchmark 55% + Asset Yield vs Cost of Deposits + Interest Spread.

---

## 6. Metricas Exclusivas -- Asset Manager

Seguem a **metodologia Moody's para Asset Management Firms**.

### Metricas de Gestao

| Indicador | O que e | Referencia |
|---|---|---|
| **FRE (Fee-Related Earnings)** | Management Fees - OpEx. Lucro recorrente. | O "salario fixo" da gestora. Se FRE nao cobre a divida, o credito e fragil. |
| **FRE Margin** | FRE / Management Fees. | **>55%** excelente; **<40%** preocupante. |
| **SRE** | Spread de operacoes de seguro (ex.: APO/Athene). | Receita estavel similar ao NII de um banco. |
| **DE (Distributable Earnings)** | FRE + Performance Realizada - Impostos. | Caixa disponivel para distribuir. Stress test: zerar performance e ver se sobrevive. |

### Alavancagem e Cobertura (Moody's)

| Indicador | Formula | Escala Moody's |
|---|---|---|
| **Gross Debt / EBITDA** | Divida Bruta / EBITDA. Moody's usa divida BRUTA. | A <1-2x, Baa 2-3,5x, Ba 3,5-5x, B >5x. |
| **Revenue Stability** | Media(YoY) / Desvio(YoY) em 20 trimestres. | Quanto maior, mais previsivel. |
| **EBITDA/Interest (5yr)** | Cobertura de juros media 5 anos. | Suaviza ciclos. |

### AUM e Capital

| Indicador | O que e | Por que importa |
|---|---|---|
| **Fee-Paying AUM** | AUM que gera taxa de gestao. | Nem todo AUM gera receita. |
| **% Permanent Capital** | AUM em veiculos sem resgate. | Quanto maior, mais estavel. 100% = ideal. |
| **Dry Powder** | Capital comprometido nao investido. | "Receita contratada do futuro." |

### Benchmarks Moody's

| Fator | Aaa-Aa | A | Baa | Ba | B |
|---|---|---|---|---|---|
| Gross Debt / EBITDA | <1x | 1-2x | 2-3,5x | 3,5-5x | >5x |
| EBITDA / Interest (5yr) | >15x | 8-15x | 4-8x | 2-4x | <2x |
| FRE Margin | >60% | 50-60% | 40-50% | 30-40% | <30% |
| Revenue Stability | >4,0 | 2,5-4,0 | 1,5-2,5 | 0,8-1,5 | <0,8 |

---

## 7. Cronograma de Vencimento da Divida

O grafico mostra os **vencimentos futuros** da divida LP, ano a ano, comparados com a posicao de liquidez.

**Para Bancos:** A barra de referencia e o **HQLA Pool** (High-Quality Liquid Assets = Caixa + Depositos em Bancos/Fed + Titulos de investimento). E o "caixa verdadeiro" de um banco -- ativos que podem ser vendidos ou usados como colateral rapidamente.

**Para Card/Outros e AM:** A barra de referencia e a **Liquidez Total** (Caixa + Aplicacoes de curto prazo).

**Como interpretar:**
- **Barras concentradas** em 1-2 anos = risco de refinanciamento ("muro de vencimentos").
- **Barras distribuidas** = perfil saudavel.
- Se o HQLA/Caixa cobre os vencimentos dos proximos 2-3 anos, a liquidez e confortavel.
- Anos: Ano 1 = proximo ano (ex.: 2026), Ano 2 = seguinte (2027), etc.

---

## 8. Fontes dos Dados

| Fonte | Tipo de Dado | Prioridade |
|---|---|---|
| **SEC EDGAR (XBRL)** | DRE, Balanco, DFC, ratios regulatorios (CET1, Tier1, SLR). | **Primaria** -- dados estruturados e auditados. |
| **Financial Supplement** | Average Balances, Yields & Rates, NCOs, NPA, LCR, NSFR, CET1/RWA reais, composicao de depositos. | **Priorizado** quando disponivel -- dados mais granulares que o XBRL. Extraido de PDFs trimestrais do site de RI. |
| **Earnings Release (via Gemini)** | Metricas nao-GAAP, FRE, DE, AUM. | **Suplementar** -- usado quando XBRL e Supplement nao tem o dado. |

> **Hierarquia de dados**: Financial Supplement > XBRL > Earnings Release. Quando o supplement esta disponivel, seus valores (NIM real, CET1 Standardized, NCOs, LCR/NSFR) sobrescrevem as aproximacoes do XBRL.

- **Periodicidade:** Trimestral (10-Q) e Anual (10-K). Valores isolados por trimestre.
- **Moeda:** USD.

---

## Tabela de Siglas

| Sigla | Significado |
|---|---|
| NII | Net Interest Income (Receita Liquida de Juros) |
| NIM | Net Interest Margin |
| PPNR | Pre-Provision Net Revenue |
| NCO | Net Charge-Offs (Baixas Liquidas) |
| NPL | Non-Performing Loans (Inadimplentes) |
| NPA | Non-Performing Assets |
| ACL | Allowance for Credit Losses (Provisao Acumulada) |
| CET1 | Common Equity Tier 1 |
| RWA | Risk-Weighted Assets |
| SLR | Supplementary Leverage Ratio |
| LCR | Liquidity Coverage Ratio |
| NSFR | Net Stable Funding Ratio |
| HQLA | High-Quality Liquid Assets |
| CASA | Current Account Savings Account (Depositos Nao-Remunerados / Total) |
| LTD | Loan-to-Deposit Ratio |
| RoTCE | Return on Tangible Common Equity |
| FRE | Fee-Related Earnings |
| DE | Distributable Earnings |
| AUM | Assets Under Management |
| LTM | Last Twelve Months |
| YoY | Year-over-Year |
| QoQ | Quarter-over-Quarter |
"""
