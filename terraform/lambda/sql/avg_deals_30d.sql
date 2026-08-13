-- highest discount vs 30-day average price per store
SELECT
    name,
    product_id,
    brand,
    store,
    link,
    image,
    current_price,
    avg_price_30d,
    pct_discount,
    rank
FROM
    (
        WITH
            date_range AS (
                SELECT
                    MAX(scrape_date) AS latest_date
                FROM
                    products
            ),
            avg_30d AS (
                SELECT
                    product_id,
                    store,
                    ROUND(AVG(price), 2) AS avg_price_30d
                FROM
                    products,
                    date_range
                WHERE
                    scrape_date >= date_add ('day', -30, latest_date)
                    AND scrape_date < latest_date
                GROUP BY
                    product_id,
                    store
            ),
            latest AS (
                SELECT
                    p.product_id,
                    p.store,
                    p.name,
                    p.brand,
                    p.link,
                    p.image,
                    p.price,
                    p.scrape_date
                FROM
                    products p,
                    date_range
                WHERE
                    p.scrape_date = latest_date
                    AND p.is_available = TRUE
            )
        SELECT
            l.name,
            l.product_id,
            l.brand,
            l.store,
            l.link,
            l.image,
            l.price AS current_price,
            a.avg_price_30d,
            ROUND(
                (a.avg_price_30d - l.price) / a.avg_price_30d * 100,
                2
            ) AS pct_discount,
            ROW_NUMBER() OVER (
                PARTITION BY
                    l.store
                ORDER BY
                    (a.avg_price_30d - l.price) / a.avg_price_30d DESC
            ) AS rank
        FROM
            latest l
            JOIN avg_30d a ON l.product_id = a.product_id
            AND l.store = a.store
        WHERE
            a.avg_price_30d > 0
            AND l.price < a.avg_price_30d
    )
WHERE
    rank <= 20
ORDER BY
    store,
    rank;