-- highest price decreases per store (sale price)

SELECT name, product_id, brand, store, scrape_date,
       prev_price,
       price                       AS current_price,
       -price_diff                 AS price_decrease,
       ROUND(-price_pct_change, 2) AS pct_decrease,
       rank
FROM (
    SELECT *,
        ROW_NUMBER() OVER (PARTITION BY store ORDER BY price_pct_change ASC) AS rank
    FROM price_changes
    WHERE price < prev_price
)
WHERE rank <= 5
ORDER BY store, rank;
