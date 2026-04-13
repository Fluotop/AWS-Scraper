-- highest list price decreases per store

SELECT name, product_id, brand, is_available, store, link, image, scrape_date,
       prev_list_price,
       list_price                                                        AS current_list_price,
       prev_list_price - list_price                                      AS price_decrease,
       ROUND((prev_list_price - list_price) / prev_list_price * 100, 2) AS pct_decrease,
       rank
FROM (
    SELECT *,
        ROW_NUMBER() OVER (
            PARTITION BY store
            ORDER BY (prev_list_price - list_price) / prev_list_price DESC
        ) AS rank
    FROM price_changes
    WHERE prev_list_price > 0
      AND list_price < prev_list_price
      AND is_available = TRUE
)
WHERE rank <= 20
ORDER BY store, rank;
