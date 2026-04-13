--highest list price increases per store

SELECT name, product_id, brand, store, link, image, scrape_date,
       prev_list_price,
       list_price                      AS current_list_price,
       list_price_diff                 AS price_increase,
       ROUND(list_price_pct_change, 2) AS pct_increase,
       rank
FROM (
    SELECT *,
        ROW_NUMBER() OVER (PARTITION BY store ORDER BY list_price_pct_change DESC) AS rank
    FROM price_changes
    WHERE list_price > prev_list_price
)
WHERE rank <= 20
ORDER BY store, rank;
