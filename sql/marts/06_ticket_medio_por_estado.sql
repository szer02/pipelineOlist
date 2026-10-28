-- Grão: uma UF do cliente.
-- Qual o ticket médio de cada estado?
-- Ticket médio: receita (soma de preco, sem frete) de cada pedido válido,
-- somada primeiro no pedido, e a média por pedido depois. O grão muda duas
-- vezes: item -> pedido (CTE) -> UF (SELECT final).
WITH receita_pedido AS (
    -- Grão: um pedido válido com pelo menos um item.
    SELECT
        p.pedido_id,
        p.cliente_id,
        sum(i.preco) AS receita
    FROM refined.pedidos      AS p
    JOIN refined.itens_pedido AS i ON i.pedido_id = p.pedido_id
    WHERE p.status NOT IN ('canceled', 'unavailable')
    GROUP BY p.pedido_id, p.cliente_id
)
SELECT
    c.uf,
    count(*)                AS pedidos,
    round(avg(r.receita), 2) AS ticket_medio
FROM receita_pedido   AS r
JOIN refined.clientes AS c ON c.cliente_id = r.cliente_id
GROUP BY c.uf
ORDER BY ticket_medio DESC, c.uf
