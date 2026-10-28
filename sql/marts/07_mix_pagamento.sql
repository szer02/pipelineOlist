-- Grão: um tipo de pagamento.
-- Quanto do dinheiro pago entra por cartão, boleto, voucher e débito?
-- Só pedidos válidos. pagamentos tem PK (pedido_id, pagamento_seq): um pedido
-- pago com dois vouchers e um cartão tem três linhas, e o JOIN com pedidos
-- fica no grão do pagamento (pedido_id é PK em pedidos, FK em pagamentos).
--
-- Por que a soma de valor (15.739.137,01) passa da receita do mart 01
-- (13.494.400,74): receita é só preco dos itens; valor é o que o cliente
-- pagou. A diferença de 2.244.736,27 é quase toda frete (2.241.126,29). O
-- resto: 365 pedidos pagaram mais que preco + frete (+3.039,16, juros do
-- parcelamento), 209 pagaram menos (-200,78), 8 pedidos válidos têm pagamento
-- e nenhum item (+915,06) e 1 tem item e nenhum pagamento (-143,46).
-- Por que a soma de pedidos (100.417) passa dos 98.206 pedidos válidos com
-- pagamento: a coluna pedidos conta pedidos distintos dentro de cada tipo, e
-- um pedido pago com dois tipos (ex.: voucher + cartão) conta uma vez em cada
-- um. Não soma entre tipos, como pedidos no mart 02.
-- not_defined não aparece: os 3 pagamentos com esse tipo são de pedidos
-- canceled.
SELECT
    pg.tipo,
    count(*)                                                 AS pagamentos,
    count(DISTINCT pg.pedido_id)                             AS pedidos,
    sum(pg.valor)                                            AS valor,
    round(100.0 * sum(pg.valor) / sum(sum(pg.valor)) OVER (), 1) AS pct_valor
FROM refined.pagamentos AS pg
JOIN refined.pedidos    AS p ON p.pedido_id = pg.pedido_id
WHERE p.status NOT IN ('canceled', 'unavailable')
GROUP BY pg.tipo
ORDER BY valor DESC
