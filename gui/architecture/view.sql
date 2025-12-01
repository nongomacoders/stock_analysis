-- View: public.v_live_valuations

-- DROP VIEW public.v_live_valuations;

CREATE OR REPLACE VIEW public.v_live_valuations
 AS
 WITH latest_price AS (
         SELECT DISTINCT ON (daily_stock_data.ticker) daily_stock_data.ticker,
            daily_stock_data.close_price AS current_price,
            daily_stock_data.trade_date AS price_date
           FROM daily_stock_data
          ORDER BY daily_stock_data.ticker, daily_stock_data.trade_date DESC
        ), dates AS (
         SELECT raw_stock_valuations.ticker,
            min(raw_stock_valuations.results_period_end) AS start_date,
            max(raw_stock_valuations.results_period_end) AS end_date
           FROM raw_stock_valuations
          GROUP BY raw_stock_valuations.ticker
        ), growth_calc AS (
         SELECT d.ticker,
            d.end_date AS financials_date,
            earliest.heps_12m_zarc AS start_heps,
            latest.heps_12m_zarc AS end_heps,
            latest.dividend_12m_zarc AS latest_div,
            latest.nav_ps_zarc AS latest_nav,
            (d.end_date - d.start_date)::numeric / 365.25 AS num_years
           FROM dates d
             JOIN raw_stock_valuations earliest ON d.ticker::text = earliest.ticker::text AND d.start_date = earliest.results_period_end
             JOIN raw_stock_valuations latest ON d.ticker::text = latest.ticker::text AND d.end_date = latest.results_period_end
        )
 SELECT p.ticker,
    p.current_price,
    round(p.current_price / NULLIF(g.end_heps, 0::numeric), 2) AS pe_ratio,
    round(g.latest_div / NULLIF(p.current_price, 0::numeric) * 100::numeric, 2) AS div_yield_perc,
        CASE
            WHEN g.start_heps > 0::numeric AND g.end_heps > g.start_heps AND g.num_years >= 1::numeric THEN round(p.current_price / NULLIF(g.end_heps, 0::numeric) / NULLIF((power(g.end_heps / g.start_heps, 1.0 / g.num_years) - 1::numeric) * 100::numeric, 0::numeric), 2)
            ELSE NULL::numeric
        END AS peg_ratio_historical,
        CASE
            WHEN g.end_heps > 0::numeric AND g.latest_nav > 0::numeric THEN round(sqrt(22.5 * g.end_heps * g.latest_nav), 0)
            ELSE NULL::numeric
        END AS graham_fair_value,
        CASE
            WHEN g.end_heps > 0::numeric AND g.latest_nav > 0::numeric THEN round((p.current_price - sqrt(22.5 * g.end_heps * g.latest_nav)) / sqrt(22.5 * g.end_heps * g.latest_nav) * 100::numeric, 2)
            ELSE NULL::numeric
        END AS valuation_premium_perc,
        CASE
            WHEN g.start_heps > 0::numeric AND g.end_heps > g.start_heps AND g.num_years >= 1::numeric THEN round((power(g.end_heps / g.start_heps, 1.0 / g.num_years) - 1::numeric) * 100::numeric, 2)
            ELSE NULL::numeric
        END AS historical_growth_cagr,
    g.financials_date
   FROM latest_price p
     JOIN growth_calc g ON p.ticker::text = g.ticker::text;

ALTER TABLE public.v_live_valuations
    OWNER TO postgres;

