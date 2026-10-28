-- Grão: uma situação de entrega ('no_prazo' ou 'atrasado').
-- O atraso derruba a nota?
-- Denominador do mart 03: delivered com data de entrega. Chegar no dia
-- previsto é no prazo (compara data com data, não hora com data).
-- Nota do pedido como no mart 04: média das avaliações do pedido, para cada
-- pedido contar uma vez. Nota baixa: nota do pedido até 2.
WITH nota_pedido AS (
    -- Grão: um pedido avaliado.
    SELECT pedido_id, avg(nota) AS nota
    FROM refined.avaliacoes
    GROUP BY pedido_id
),
entrega_pedido AS (
    -- Grão: um pedido entregue (delivered com data de entrega).
    SELECT
        pedido_id,
        CASE
            WHEN data_entrega::DATE <= data_entrega_prevista THEN 'no_prazo'
            WHEN data_entrega::DATE >  data_entrega_prevista THEN 'atrasado'
        END AS situacao
    FROM refined.pedidos
    WHERE status = 'delivered'
      AND data_entrega IS NOT NULL
)
SELECT
    e.situacao,
    count(*)                                                AS pedidos_avaliados,
    round(avg(n.nota), 2)                                   AS nota_media,
    round(100.0 * count(*) FILTER (n.nota <= 2) / count(*), 1) AS pct_nota_baixa
FROM entrega_pedido AS e
JOIN nota_pedido    AS n ON n.pedido_id = e.pedido_id
GROUP BY e.situacao
ORDER BY e.situacao DESC
