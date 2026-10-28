# Spec: raw.geolocalizacao -> refined.geolocalizacao

Nada de código e nada gravado no banco. Esta spec só descreve o que a etapa
faria. Todos os números abaixo foram contados em raw.geolocalizacao (somente
leitura). Quando um número muda com a dedup, os dois aparecem, cada um com a
sua definição.

## 0. O que a tabela é

1.000.163 linhas, 5 colunas, todas VARCHAR em raw: geolocation_zip_code_prefix,
geolocation_lat, geolocation_lng, geolocation_city, geolocation_state.
Só 19.015 CEPs distintos: ~52 linhas por CEP em média, mediana 29, máximo
1.146. Ou seja, não é "um ponto por CEP", é uma nuvem de pontos por CEP.

Grão de refined.geolocalizacao: **um ponto observado distinto** (cep, lat, lng,
cidade, uf, exatamente como vieram). Não há chave: cep_prefixo se repete até
1.146 vezes.
Por quê: tirar cópia exata não muda o significado de nenhuma linha (trabalho de
refined); reduzir a um ponto por CEP responde a uma pergunta ("onde fica este
CEP?") e é trabalho de mart.

## 1. Escopo e nome

Lê de raw.geolocalizacao, escreve em refined.geolocalizacao, em script
separado da etapa 2 (os 550.759 de refined continuam valendo). Nunca escreve
em raw. Mesmo vocabulário da etapa 2 (português, snake_case).
Por quê: a tabela só serve para ser juntada com clientes e vendedores pelo
CEP, e o resultado ocupa o mesmo schema das outras oito.

Colunas: cep_prefixo, latitude, longitude, cidade, uf.

## 2. Tipos

- cep_prefixo: VARCHAR. 245.733 linhas de raw (24,6%) começam com zero e as
  1.000.163 têm exatamente 5 dígitos. Como número perderia o zero (mesmo motivo
  de clientes: 23.995 clientes com CEP começando em zero).
- latitude e longitude: DOUBLE, não DECIMAL(10,2). Os valores têm de 3 a 20
  casas decimais, então DECIMAL(10,2) arredondaria 1 ponto de ~1 km para
  ~1,1 km (2 casas = 0,01 grau). Coordenada não é dinheiro: ninguém a soma
  e exatidão de centavo não existe aqui.
- cidade e uf: VARCHAR.
- Conversão: strptime/CAST sem TRY, checagem de formato antes, como na etapa 2.
  Em raw, 0 linhas de latitude e 0 de longitude fora de `-?\d+\.\d+`, e 0 nulos
  em qualquer coluna. Se algum dia aparecer um, a etapa para (sys.exit(1)).
  Por quê: nulo fabricado pela conversão é indistinguível de nulo verdadeiro.

## 3. Duplicatas exatas

Linha inteira repetida (as 5 colunas iguais, como vieram): mantém uma e conta
quantas saíram.
Por quê: 261.831 linhas (26,2%) são repetição exata e não carregam informação.
Resultado esperado: 1.000.163 -> 738.332 linhas (261.831 duplicatas).
Os 19.015 CEPs continuam todos presentes depois da dedup.
Não há normalização antes da dedup: "sao paulo" e "são paulo" no mesmo ponto
são linhas diferentes e as duas ficam (ver regra 4).

## 4. Cidade: mantém como chegou

Nenhuma alteração de texto: sem trim, sem strip_accents, sem conversão de
entidade HTML. Só reporta.
Por quê: refined não corrige fato, e trocar a grafia muda o conteúdo da linha.
Unificar grafias é decisão de mart, que sabe para que JOIN precisa delas.
O que existe hoje em raw (para o mart decidir):
- 8.011 grafias distintas de cidade; 73.437 linhas têm acento. Ex.: "sao paulo"
  135.800 linhas x "são paulo" 24.918.
- 1 linha com espaço na borda ("salvador "), 1 com entidade HTML
  ("florian&oacute;polis").
- 8.556 CEPs têm mais de uma grafia de cidade.
- Referência para o mart: normalizando (trim, strip_accents, colapsar espaços,
  &oacute; -> o), as grafias cairiam de 8.011 para 5.966 cidades distintas e os
  CEPs com mais de uma cidade de 8.556 para 548. Os 548 que sobram são erro de
  digitação ("rio janeiro"), sigla no lugar do nome ("rj") ou cidade vizinha de
  verdade ("camboriu" x "balneario camboriu", CEP 88330); só dá para separar
  olhando um por um.

## 5. UF

Mantém como chegou. Em raw, 0 fora de [A-Z]{2} e 27 UFs, as 27 reais.
Por quê: nada a corrigir.
CEP com mais de uma UF (8 CEPs: 02116 RN/SP, 04011 SP/AC, 21550 AC/RJ,
23056 RJ/AC, 72915 DF/GO, 78557 MT/RO, 79750 MS/RS, 80630 PR/SC): as linhas
ficam, sem escolher uma UF.
Por quê: CEP e UF conflitantes são "chave com conteúdo diferente" e, como na
etapa 2, escolher em silêncio é decidir sem dizer que decidiu. Eles ficam
visíveis na saída (regra 10). Só 7 CEPs de clientes têm UF diferente da UF
da geolocalizacao, então o efeito no mart é pequeno.

## 6. Coordenadas fora do Brasil

Definição: linha com latitude fora de [-33,75; 5,27] **ou** longitude fora de
[-73,99; -34,79] (caixa envolvente do Brasil). NÃO apaga e NÃO corrige. Marca
em coluna booleana `fora_do_brasil`.
Contagem, sempre com a unidade:
- 42 linhas em raw (antes da dedup);
- 33 linhas em refined (depois da dedup, cada linha repetida contada uma vez);
- 21 CEPs (o mesmo antes e depois da dedup).
Por quê: 5 desses 21 CEPs têm TODAS as linhas fora (sem ponto bom para usar).
Ex.: CEP 18243 (SP) em lat 28,01 / lng -15,54, no Atlântico; CEP 28155 (RJ)
com um ponto em Buenos Aires e outro na Itália. 14 desses 21 CEPs são usados
por clientes ou vendedores (48 clientes), então apagar a linha tiraria ponto
de gente real, e o refined não corrige fato.
Quem exclui o ponto é o mart, que decide se prefere "sem localização" ou
"localização aproximada pela UF".
Obs.: a caixa envolvente é grossa de propósito, porque pega só o que é
impossível. Um ponto dentro da caixa mas na UF errada não é detectado aqui.

## 7. O que NÃO fazer: reduzir a uma linha por CEP

refined.geolocalizacao continua com várias linhas por CEP. A redução
(mediana de latitude/longitude por CEP, ~19.015 linhas) NÃO acontece aqui.
Por quê:
- Dispersão grande: 3.015 CEPs (15,9%) têm pontos que se espalham mais de
  0,1 grau (~11 km) e 423 passam de 0,5 grau (~55 km). Média e mediana
  escolhem pontos muito diferentes nesses CEPs, e qual escolher depende da
  pergunta ("onde fica o centro do CEP?" x "onde moram os clientes?").
- A média é arrastada pelos pontos fora do Brasil (a distância máxima dentro
  de um mesmo CEP chega a 77 graus por causa deles); a mediana não.
- Contado em raw, 1.043 CEPs têm 1 linha só e 2.756 têm 100 ou mais: a
  confiança no ponto é muito diferente, e sumir com a contagem apaga isso.
Decisão de redução fica para o mart de geolocalização, com mediana como
candidata e `fora_do_brasil` como filtro. A refined entrega a matéria-prima
sem cópias e etiquetada.

**Aviso a quem consome:** não juntar refined.clientes direto com
refined.geolocalizacao pelo CEP. Como o CEP não é chave aqui, o JOIN multiplica
linhas: 99.441 clientes viram 10.327.728 linhas contra refined (738.332) e
15.083.455 contra raw (1.000.163). Antes do JOIN, reduzir a um ponto por CEP
num mart, com a regra escrita.

## 8. CEPs de clientes e vendedores sem geolocalização

Não é decisão desta tabela, só reporta: 157 dos 14.994 CEPs de clientes
(278 clientes, 278 pedidos) e 7 dos 2.246 CEPs de vendedores (7 vendedores)
não existem em geolocalizacao (exemplos: 70686, 72005, 71919, todos DF).
Por quê: sem esse aviso o JOIN esquece 278 pedidos em silêncio.
Direção oposta: 4.099 dos 19.015 CEPs da tabela não são de nenhum cliente nem
vendedor. Fica na tabela: o refined não filtra por uso.

## 9. Nulos e linhas

Nenhum nulo preenchido; as únicas linhas que saem são as 261.831 cópias exatas
(regra 3). Hoje há 0 nulos em todas as cinco colunas, então a saída deve dizer
"nulos mantidos: nenhum" como na etapa 2.

## 10. Saída na tela

Linha da tabela no formato da etapa 2, mais as contagens que provam as
decisões acima (todas sobre a tabela já deduplicada, salvo indicação):
```
refined.geolocalizacao   1.000.163 -> 738.332 linhas  (261.831 duplicatas)
    nulos mantidos: nenhum
    coordenadas fora do Brasil: 33 linhas em 21 CEPs
    CEPs com mais de uma UF: 8
    CEPs com mais de uma grafia de cidade: 8.556
    aviso: CEP não é chave; reduzir a um ponto por CEP antes de juntar
```
Contagens vindas do banco, milhar com ponto, stdout em utf-8.
Por quê: é o instrumento de conferência. As contagens extras são as decisões
que a spec deixou abertas e precisam continuar visíveis a cada rodada.

## 11. Reexecução e erro

CREATE OR REPLACE TABLE, numa única transação. Antes de transformar,
verifica se raw.geolocalizacao existe: se faltar, diz para rodar
"uv run python -m pipeline.ingestao" e sai com sys.exit(1).
Por quê: mesma razão da etapa 2 (rodar dez vezes = rodar uma).

## 12. Critérios de aceite

- refined.geolocalizacao com 738.332 linhas (261.831 duplicatas removidas).
- 19.015 CEPs distintos, os mesmos de raw.
- cep_prefixo continua com 5 dígitos: 245.733 linhas começam com zero em raw
  e 158.832 em refined (depois da dedup).
- 5 colunas de raw + `fora_do_brasil`, 0 nulos, 27 UFs.
- 8 CEPs com mais de uma UF continuam com todas as UFs.
- 33 linhas com fora_do_brasil = true em refined (42 em raw), em 21 CEPs;
  nenhuma linha apagada por isso.
- Cidades distintas: 8.011, igual a raw (nenhuma grafia alterada).
- Rodar duas vezes imprime exatamente a mesma coisa.

## 13. O que ficou de fora (decisão de mart)

- Qual ponto representa o CEP (mediana x média x primeiro).
- Normalizar grafia de cidade (acento, espaço, entidade HTML).
- Como tratar os CEPs com mais de uma cidade (8.556 como veio, 548 depois de
  normalizar).
- Como tratar os 157 CEPs de clientes sem geolocalização.
- Ponto dentro da caixa do Brasil mas na UF errada.

## 14. O que assumi e não estava no enunciado

- Grão "um ponto observado distinto", sem chave.
- Caixa envolvente do Brasil (-33,75/5,27, -73,99/-34,79) escolhida por mim.
- Coluna `fora_do_brasil` é acréscimo meu: se o curso exigir "nenhuma coluna
  fora do mapa", a alternativa é só reportar na tela.

---

## Observação: registro da revisão pós-correção (aula 3)

> **NÃO USAR COMO REQUISITO.** Esta seção é só histórico do que mudou nesta
> spec depois da correção do desafio 2. Quem implementar segue as seções 0-14
> acima e ignora esta.

- Grão declarado (seção 0): "um ponto observado distinto", sem chave.
- Normalização de cidade removida (seção 4): antes trim/strip_accents/HTML eram
  aplicados em refined; agora a cidade fica como chegou e normalizar virou
  decisão de mart (seção 13). Motivo: muda o conteúdo da linha.
- Dedup (seção 3): resultado passou de 720.496 para 738.332 linhas (261.831
  duplicatas, antes 279.667), porque não há mais normalização antes; removida
  a contradição que citava os dois números.
- Aviso do JOIN acrescentado (seção 7): 99.441 clientes -> 10.327.728 linhas
  contra refined e 15.083.455 contra raw.
- Números corrigidos: cidades distintas normalizadas 5.969 -> 5.966; CEPs com
  mais de uma cidade após normalizar 550 -> 548 (e removido o "547").
- Fora do Brasil (seção 6): definição escrita ("lat ou lng") e contagem
  separada em 42 linhas em raw / 33 em refined / 21 CEPs; saída e critérios
  passaram a usar 33.
- Critério de aceite do CEP com zero ganhou número depois da dedup (158.832).
- Saída na tela (seção 10): "CEPs com mais de uma cidade" passou a 8.556 (como
  veio) e ganhou a linha de aviso de CEP não-chave.
- Referência da seção 5 corrigida: "regra 8" -> "regra 10" (a saída).
- Removido de "assumi" o item do trim de 1 linha (não há mais trim).
