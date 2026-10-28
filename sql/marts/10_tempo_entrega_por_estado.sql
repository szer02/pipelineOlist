-- Grão: uma UF do cliente.
-- Quantos dias leva da compra até a entrega, por estado?
-- Denominador do mart 03: delivered com data de entrega. Parte de data_compra
-- (o tempo que o cliente espera), não de data_envio (o tempo da
-- transportadora). date_diff('day', ...) conta dias de calendário.
WITH entrega_pedido AS (
    -- Grão: um pedido entregue (delivered com data de entrega).
    SELECT
        c.uf,
        date_diff('day', p.data_compra, p.data_entrega) AS dias
    FROM refined.pedidos  AS p
    JOIN refined.clientes AS c ON c.cliente_id = p.cliente_id
    WHERE p.status = 'delivered'
      AND p.data_entrega IS NOT NULL
)
SELECT
    uf,
    count(*)            AS entregues,
    round(avg(dias), 1) AS dias_medio,
    median(dias)        AS dias_mediana
FROM entrega_pedido
GROUP BY uf
ORDER BY dias_medio, uf
