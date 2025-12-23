-- DROP SCHEMA public;

CREATE SCHEMA public AUTHORIZATION pg_database_owner;

COMMENT ON SCHEMA public IS 'standard public schema';

-- DROP SEQUENCE public.action_log_log_id_seq;

CREATE SEQUENCE public.action_log_log_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.commodity_prices_id_seq;

CREATE SEQUENCE public.commodity_prices_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 9223372036854775807
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.daily_todos_id_seq;

CREATE SEQUENCE public.daily_todos_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.fx_rates_id_seq;

CREATE SEQUENCE public.fx_rates_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 9223372036854775807
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.historical_earnings_earnings_id_seq;

CREATE SEQUENCE public.historical_earnings_earnings_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.ignored_events_ignored_event_id_seq;

CREATE SEQUENCE public.ignored_events_ignored_event_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.portfolio_holdings_id_seq;

CREATE SEQUENCE public.portfolio_holdings_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.portfolio_transactions_id_seq;

CREATE SEQUENCE public.portfolio_transactions_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.portfolios_id_seq;

CREATE SEQUENCE public.portfolios_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.price_hit_log_hit_id_seq;

CREATE SEQUENCE public.price_hit_log_hit_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.price_update_log_log_id_seq;

CREATE SEQUENCE public.price_update_log_log_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.raw_stock_valuations_id_seq;

CREATE SEQUENCE public.raw_stock_valuations_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 9223372036854775807
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.sens_sens_id_seq;

CREATE SEQUENCE public.sens_sens_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.stock_analysis_analysis_id_seq;

CREATE SEQUENCE public.stock_analysis_analysis_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.stock_categories_category_id_seq;

CREATE SEQUENCE public.stock_categories_category_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.stock_price_levels_level_id_seq;

CREATE SEQUENCE public.stock_price_levels_level_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.watchlist_watchlist_id_seq;

CREATE SEQUENCE public.watchlist_watchlist_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;-- public.commodity_prices definition

-- Drop table

-- DROP TABLE public.commodity_prices;

CREATE TABLE public.commodity_prices (
	id bigserial NOT NULL,
	symbol text NOT NULL,
	commodity text NOT NULL,
	price numeric(20, 8) NOT NULL,
	unit text NOT NULL,
	currency text DEFAULT 'USD'::text NOT NULL,
	as_of_ts timestamptz NULL,
	collected_ts timestamptz DEFAULT now() NOT NULL,
	"source" text NOT NULL,
	source_field text NULL,
	url text NULL,
	quality text NULL,
	notes text NULL,
	CONSTRAINT commodity_prices_pkey PRIMARY KEY (id),
	CONSTRAINT commodity_prices_price_nonneg CHECK ((price >= (0)::numeric))
);
CREATE INDEX idx_commodity_prices_collected_ts ON public.commodity_prices USING btree (collected_ts DESC);
CREATE INDEX idx_commodity_prices_symbol_asof_ts ON public.commodity_prices USING btree (symbol, as_of_ts DESC);
CREATE INDEX idx_commodity_prices_symbol_collected_ts ON public.commodity_prices USING btree (symbol, collected_ts DESC);


-- public.commodity_universe definition

-- Drop table

-- DROP TABLE public.commodity_universe;

CREATE TABLE public.commodity_universe (
	symbol text NOT NULL,
	commodity text NOT NULL,
	is_active bool DEFAULT true NOT NULL,
	priority int4 DEFAULT 100 NOT NULL,
	CONSTRAINT commodity_universe_pkey PRIMARY KEY (symbol)
);
CREATE INDEX idx_commodity_universe_active_priority ON public.commodity_universe USING btree (is_active, priority, symbol);


-- public.daily_todos definition

-- Drop table

-- DROP TABLE public.daily_todos;

CREATE TABLE public.daily_todos (
	id serial4 NOT NULL,
	task_date date NOT NULL,
	title text NOT NULL,
	description text NULL,
	ticker varchar(16) NULL,
	priority text DEFAULT 'medium'::text NOT NULL,
	status text DEFAULT 'active'::text NOT NULL,
	sort_order int4 NULL,
	created_at timestamptz DEFAULT now() NOT NULL,
	updated_at timestamptz DEFAULT now() NOT NULL,
	completed_at timestamptz NULL,
	CONSTRAINT daily_todos_pkey PRIMARY KEY (id),
	CONSTRAINT daily_todos_priority_check CHECK ((priority = ANY (ARRAY['low'::text, 'medium'::text, 'high'::text]))),
	CONSTRAINT daily_todos_status_check CHECK ((status = ANY (ARRAY['active'::text, 'done'::text, 'deferred'::text])))
);


-- public.fx_rates definition

-- Drop table

-- DROP TABLE public.fx_rates;

CREATE TABLE public.fx_rates (
	id bigserial NOT NULL,
	pair text NOT NULL,
	rate numeric(20, 8) NOT NULL,
	as_of_ts timestamptz NULL,
	collected_ts timestamptz DEFAULT now() NOT NULL,
	"source" text NOT NULL,
	url text NULL,
	notes text NULL,
	CONSTRAINT fx_rates_pkey PRIMARY KEY (id),
	CONSTRAINT fx_rates_rate_nonneg CHECK ((rate >= (0)::numeric))
);
CREATE INDEX idx_fx_rates_pair_collected_ts ON public.fx_rates USING btree (pair, collected_ts DESC);


-- public.fx_universe definition

-- Drop table

-- DROP TABLE public.fx_universe;

CREATE TABLE public.fx_universe (
	pair text NOT NULL,
	is_active bool DEFAULT true NOT NULL,
	priority int4 DEFAULT 100 NOT NULL,
	CONSTRAINT fx_universe_pkey PRIMARY KEY (pair)
);
CREATE INDEX idx_fx_universe_active_priority ON public.fx_universe USING btree (is_active, priority, pair);


-- public.portfolios definition

-- Drop table

-- DROP TABLE public.portfolios;

CREATE TABLE public.portfolios (
	id serial4 NOT NULL,
	"name" varchar(100) NOT NULL,
	created_at timestamp DEFAULT CURRENT_TIMESTAMP NULL,
	CONSTRAINT portfolios_pkey PRIMARY KEY (id)
);


-- public.price_update_log definition

-- Drop table

-- DROP TABLE public.price_update_log;

CREATE TABLE public.price_update_log (
	log_id serial4 NOT NULL,
	update_timestamp timestamptz DEFAULT CURRENT_TIMESTAMP NULL,
	records_saved int4 NULL,
	CONSTRAINT price_update_log_pkey PRIMARY KEY (log_id)
);


-- public.stock_categories definition

-- Drop table

-- DROP TABLE public.stock_categories;

CREATE TABLE public.stock_categories (
	category_id serial4 NOT NULL,
	"name" varchar(100) NOT NULL,
	description text NULL,
	CONSTRAINT stock_categories_pkey PRIMARY KEY (category_id),
	CONSTRAINT uq_stock_categories_name UNIQUE (name)
);
COMMENT ON TABLE public.stock_categories IS 'Normalized list of stock categories (e.g., Banks, Mining, Retail)';


-- public.stock_details definition

-- Drop table

-- DROP TABLE public.stock_details;

CREATE TABLE public.stock_details (
	ticker varchar(20) NOT NULL,
	update_q1 date NULL,
	update_q2 date NULL,
	update_q3 date NULL,
	update_q4 date NULL,
	earnings_q1 date NULL,
	earnings_q2 date NULL,
	earnings_q3 date NULL,
	earnings_q4 date NULL,
	market_cap int8 NULL,
	exchange_name varchar(50) NULL,
	priority varchar(10) NULL,
	full_name varchar(255) NULL,
	stock_category_id int4 NULL,
	CONSTRAINT financial_report_dates_pkey PRIMARY KEY (ticker),
	CONSTRAINT fk_stock_details_stock_category FOREIGN KEY (stock_category_id) REFERENCES public.stock_categories(category_id) ON DELETE SET NULL
);
CREATE INDEX idx_stock_details_stock_category_id ON public.stock_details USING btree (stock_category_id);


-- public.stock_price_levels definition

-- Drop table

-- DROP TABLE public.stock_price_levels;

CREATE TABLE public.stock_price_levels (
	level_id serial4 NOT NULL,
	ticker varchar(20) NOT NULL,
	price_level numeric(12, 2) NULL,
	level_type varchar(50) NULL,
	date_added date DEFAULT CURRENT_DATE NULL,
	is_long bool DEFAULT true NULL,
	CONSTRAINT stock_price_levels_level_type_check CHECK (((level_type)::text = ANY ((ARRAY['entry'::character varying, 'target'::character varying, 'stop_loss'::character varying, 'support'::character varying, 'resistance'::character varying])::text[]))),
	CONSTRAINT stock_price_levels_pkey PRIMARY KEY (level_id),
	CONSTRAINT stock_price_levels_ticker_price_type_unique UNIQUE (ticker, price_level, level_type),
	CONSTRAINT stock_price_levels_ticker_fkey FOREIGN KEY (ticker) REFERENCES public.stock_details(ticker) ON DELETE CASCADE
);
CREATE INDEX stock_price_levels_ticker_idx ON public.stock_price_levels USING btree (ticker);
CREATE UNIQUE INDEX stock_price_levels_unique_entry ON public.stock_price_levels USING btree (ticker) WHERE ((level_type)::text = 'entry'::text);
CREATE UNIQUE INDEX stock_price_levels_unique_stoploss ON public.stock_price_levels USING btree (ticker) WHERE ((level_type)::text = 'stop_loss'::text);
CREATE UNIQUE INDEX stock_price_levels_unique_target ON public.stock_price_levels USING btree (ticker) WHERE ((level_type)::text = 'target'::text);


-- public.watchlist definition

-- Drop table

-- DROP TABLE public.watchlist;

CREATE TABLE public.watchlist (
	watchlist_id serial4 NOT NULL,
	ticker varchar(20) NOT NULL,
	target_price numeric(12, 2) NULL,
	entry_price numeric(12, 2) NULL,
	stop_loss numeric(12, 2) NULL,
	reward_risk_ratio numeric(10, 2) NULL,
	date_added date DEFAULT CURRENT_DATE NULL,
	notes text NULL,
	status varchar(20) DEFAULT 'Pending'::character varying NULL,
	is_long bool DEFAULT true NULL,
	CONSTRAINT watchlist_pkey PRIMARY KEY (watchlist_id),
	CONSTRAINT watchlist_ticker_unique UNIQUE (ticker),
	CONSTRAINT watchlist_ticker_fkey FOREIGN KEY (ticker) REFERENCES public.stock_details(ticker) ON DELETE CASCADE
);
CREATE INDEX watchlist_ticker_idx ON public.watchlist USING btree (ticker);

-- Table Triggers

create trigger trg_compute_watchlist_reward_risk_ratio before
insert
    or
update
    on
    public.watchlist for each row execute function compute_watchlist_reward_risk_ratio();


-- public.action_log definition

-- Drop table

-- DROP TABLE public.action_log;

CREATE TABLE public.action_log (
	log_id serial4 NOT NULL,
	ticker varchar(20) NOT NULL,
	log_timestamp timestamptz DEFAULT CURRENT_TIMESTAMP NULL,
	trigger_type varchar(50) NULL,
	trigger_content text NULL,
	ai_analysis text NULL,
	is_read bool DEFAULT false NULL,
	CONSTRAINT action_log_pkey PRIMARY KEY (log_id),
	CONSTRAINT action_log_ticker_fkey FOREIGN KEY (ticker) REFERENCES public.stock_details(ticker) ON DELETE CASCADE
);

-- Table Triggers

create trigger action_log_notify_trigger after
insert
    or
update
    on
    public.action_log for each row execute function notify_action_log_change();


-- public.daily_stock_data definition

-- Drop table

-- DROP TABLE public.daily_stock_data;

CREATE TABLE public.daily_stock_data (
	ticker varchar(20) NOT NULL,
	trade_date date NOT NULL,
	open_price numeric(12, 2) NULL,
	high_price numeric(12, 2) NULL,
	low_price numeric(12, 2) NULL,
	close_price numeric(12, 2) NULL,
	volume int8 NULL,
	CONSTRAINT daily_stock_data_pkey PRIMARY KEY (ticker, trade_date),
	CONSTRAINT daily_stock_data_ticker_fkey FOREIGN KEY (ticker) REFERENCES public.stock_details(ticker) ON DELETE CASCADE
);


-- public.historical_earnings definition

-- Drop table

-- DROP TABLE public.historical_earnings;

CREATE TABLE public.historical_earnings (
	earnings_id serial4 NOT NULL,
	ticker varchar(20) NOT NULL,
	"period" varchar(20) NOT NULL,
	heps numeric(10, 2) NOT NULL,
	notes text NULL,
	results_date date NOT NULL,
	CONSTRAINT historical_earnings_pkey PRIMARY KEY (earnings_id),
	CONSTRAINT historical_earnings_ticker_period_key UNIQUE (ticker, period),
	CONSTRAINT historical_earnings_ticker_fkey FOREIGN KEY (ticker) REFERENCES public.stock_details(ticker) ON DELETE CASCADE
);
CREATE INDEX idx_historical_earnings_ticker ON public.historical_earnings USING btree (ticker);


-- public.ignored_events definition

-- Drop table

-- DROP TABLE public.ignored_events;

CREATE TABLE public.ignored_events (
	ignored_event_id serial4 NOT NULL,
	ticker varchar(20) NOT NULL,
	event_type varchar(20) NOT NULL,
	event_date date NOT NULL,
	date_ignored timestamp DEFAULT CURRENT_TIMESTAMP NULL,
	CONSTRAINT ignored_events_pkey PRIMARY KEY (ignored_event_id),
	CONSTRAINT ignored_events_ticker_event_type_event_date_key UNIQUE (ticker, event_type, event_date),
	CONSTRAINT ignored_events_ticker_fkey FOREIGN KEY (ticker) REFERENCES public.stock_details(ticker) ON DELETE CASCADE
);


-- public.portfolio_holdings definition

-- Drop table

-- DROP TABLE public.portfolio_holdings;

CREATE TABLE public.portfolio_holdings (
	id serial4 NOT NULL,
	portfolio_id int4 NULL,
	ticker varchar(20) NOT NULL,
	quantity numeric(15, 4) NOT NULL,
	average_buy_price numeric(15, 2) NOT NULL,
	last_updated timestamp DEFAULT CURRENT_TIMESTAMP NULL,
	CONSTRAINT portfolio_holdings_pkey PRIMARY KEY (id),
	CONSTRAINT portfolio_holdings_portfolio_id_ticker_key UNIQUE (portfolio_id, ticker),
	CONSTRAINT portfolio_holdings_portfolio_id_fkey FOREIGN KEY (portfolio_id) REFERENCES public.portfolios(id) ON DELETE CASCADE,
	CONSTRAINT portfolio_holdings_ticker_fkey FOREIGN KEY (ticker) REFERENCES public.stock_details(ticker) ON DELETE CASCADE
);


-- public.portfolio_transactions definition

-- Drop table

-- DROP TABLE public.portfolio_transactions;

CREATE TABLE public.portfolio_transactions (
	id serial4 NOT NULL,
	portfolio_id int4 NULL,
	ticker varchar(20) NOT NULL,
	transaction_type varchar(10) NOT NULL,
	quantity numeric(15, 4) NOT NULL,
	price numeric(15, 2) NOT NULL,
	transaction_date timestamp DEFAULT CURRENT_TIMESTAMP NULL,
	fees numeric(15, 2) DEFAULT 0.0 NULL,
	notes text NULL,
	CONSTRAINT portfolio_transactions_pkey PRIMARY KEY (id),
	CONSTRAINT portfolio_transactions_transaction_type_check CHECK (((transaction_type)::text = ANY ((ARRAY['BUY'::character varying, 'SELL'::character varying])::text[]))),
	CONSTRAINT portfolio_transactions_portfolio_id_fkey FOREIGN KEY (portfolio_id) REFERENCES public.portfolios(id) ON DELETE CASCADE,
	CONSTRAINT portfolio_transactions_ticker_fkey FOREIGN KEY (ticker) REFERENCES public.stock_details(ticker) ON DELETE CASCADE
);


-- public.price_hit_log definition

-- Drop table

-- DROP TABLE public.price_hit_log;

CREATE TABLE public.price_hit_log (
	hit_id serial4 NOT NULL,
	ticker varchar(10) NOT NULL,
	price_level numeric NOT NULL,
	hit_timestamp timestamp DEFAULT CURRENT_TIMESTAMP NULL,
	level_type varchar(20) NULL,
	level_id int4 NULL,
	CONSTRAINT price_hit_log_level_type_chk CHECK (((level_type IS NULL) OR ((level_type)::text = ANY ((ARRAY['support'::character varying, 'resistance'::character varying, 'entry'::character varying, 'target'::character varying, 'stop_loss'::character varying])::text[])))),
	CONSTRAINT price_hit_log_pkey PRIMARY KEY (hit_id),
	CONSTRAINT price_hit_log_level_id_fkey FOREIGN KEY (level_id) REFERENCES public.stock_price_levels(level_id) ON DELETE SET NULL,
	CONSTRAINT price_hit_log_ticker_fkey FOREIGN KEY (ticker) REFERENCES public.stock_details(ticker) ON DELETE CASCADE
);
CREATE UNIQUE INDEX idx_ticker_level_date ON public.price_hit_log USING btree (ticker, price_level, ((hit_timestamp)::date));
CREATE INDEX price_hit_log_ticker_ts_idx ON public.price_hit_log USING btree (ticker, hit_timestamp DESC);
CREATE UNIQUE INDEX price_hit_log_uniq_per_day ON public.price_hit_log USING btree (ticker, level_type, price_level, ((hit_timestamp)::date));


-- public.raw_stock_valuations definition

-- Drop table

-- DROP TABLE public.raw_stock_valuations;

CREATE TABLE public.raw_stock_valuations (
	id bigserial NOT NULL,
	ticker varchar(20) NOT NULL,
	results_period_end date NOT NULL, -- End date of the financial period (e.g., 2025-03-31 for Mar 2025)
	results_period_label varchar(100) NOT NULL, -- Full human-readable period label from ShareData (e.g., "Mar 2025 Final (12m) 23 Jun 2025")
	heps_12m_zarc numeric(18, 4) NULL, -- 12 Month HEPS in ZAR cents
	dividend_12m_zarc numeric(18, 4) NULL, -- 12 Month Dividend in ZAR cents
	cash_gen_ps_zarc numeric(18, 4) NULL, -- Cash Generated Per Share in ZAR cents
	nav_ps_zarc numeric(18, 4) NULL, -- Net Asset Value Per Share in ZAR cents
	quick_ratio numeric(18, 6) NULL, -- Quick Ratio (may be NULL for some sectors/periods)
	"source" varchar(50) DEFAULT 'sharedata'::character varying NOT NULL,
	created_at timestamptz DEFAULT now() NOT NULL,
	results_release_date date NULL,
	period_months int4 NULL,
	CONSTRAINT raw_stock_valuations_pkey PRIMARY KEY (id),
	CONSTRAINT raw_stock_valuations_ticker_period_uniq UNIQUE (ticker, results_period_end),
	CONSTRAINT raw_stock_valuations_ticker_fk FOREIGN KEY (ticker) REFERENCES public.stock_details(ticker) ON DELETE CASCADE
);
CREATE INDEX idx_raw_stock_valuations_ticker ON public.raw_stock_valuations USING btree (ticker, results_period_end DESC);
CREATE INDEX raw_stock_valuations_ticker_idx ON public.raw_stock_valuations USING btree (ticker);
COMMENT ON TABLE public.raw_stock_valuations IS 'Historical fundamental data for multiple periods per ticker, scraped from ShareData';

-- Column comments

COMMENT ON COLUMN public.raw_stock_valuations.results_period_end IS 'End date of the financial period (e.g., 2025-03-31 for Mar 2025)';
COMMENT ON COLUMN public.raw_stock_valuations.results_period_label IS 'Full human-readable period label from ShareData (e.g., "Mar 2025 Final (12m) 23 Jun 2025")';
COMMENT ON COLUMN public.raw_stock_valuations.heps_12m_zarc IS '12 Month HEPS in ZAR cents';
COMMENT ON COLUMN public.raw_stock_valuations.dividend_12m_zarc IS '12 Month Dividend in ZAR cents';
COMMENT ON COLUMN public.raw_stock_valuations.cash_gen_ps_zarc IS 'Cash Generated Per Share in ZAR cents';
COMMENT ON COLUMN public.raw_stock_valuations.nav_ps_zarc IS 'Net Asset Value Per Share in ZAR cents';
COMMENT ON COLUMN public.raw_stock_valuations.quick_ratio IS 'Quick Ratio (may be NULL for some sectors/periods)';


-- public.sens definition

-- Drop table

-- DROP TABLE public.sens;

CREATE TABLE public.sens (
	sens_id serial4 NOT NULL,
	ticker varchar(20) NOT NULL,
	publication_datetime timestamptz NOT NULL,
	"content" text NOT NULL,
	CONSTRAINT sens_pkey PRIMARY KEY (sens_id),
	CONSTRAINT sens_ticker_fkey FOREIGN KEY (ticker) REFERENCES public.stock_details(ticker) ON DELETE CASCADE
);
CREATE INDEX idx_sens_ticker_datetime ON public.sens USING btree (ticker, publication_datetime DESC);


-- public.stock_analysis definition

-- Drop table

-- DROP TABLE public.stock_analysis;

CREATE TABLE public.stock_analysis (
	analysis_id serial4 NOT NULL,
	ticker varchar(20) NOT NULL,
	research text NULL,
	strategy text NULL,
	deepresearch text NULL,
	deepresearch_date date NULL,
	CONSTRAINT stock_analysis_pkey PRIMARY KEY (analysis_id),
	CONSTRAINT stock_analysis_ticker_key UNIQUE (ticker),
	CONSTRAINT stock_analysis_ticker_fkey FOREIGN KEY (ticker) REFERENCES public.stock_details(ticker) ON DELETE CASCADE
);


-- public.v_latest_commodity_prices source

CREATE OR REPLACE VIEW public.v_latest_commodity_prices
AS SELECT DISTINCT ON (symbol) symbol,
    commodity,
    price,
    unit,
    currency,
    as_of_ts,
    collected_ts,
    source,
    source_field,
    url,
    quality,
    notes
   FROM commodity_prices
  ORDER BY symbol, collected_ts DESC;


-- public.v_latest_fx_rates source

CREATE OR REPLACE VIEW public.v_latest_fx_rates
AS SELECT DISTINCT ON (pair) pair,
    rate,
    as_of_ts,
    collected_ts,
    source,
    url,
    notes
   FROM fx_rates
  ORDER BY pair, collected_ts DESC;


-- public.v_live_valuations source

CREATE OR REPLACE VIEW public.v_live_valuations
AS WITH latest_price AS (
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
            WHEN g.start_heps > 0::numeric AND g.end_heps > 0::numeric AND g.num_years >= 1::numeric THEN round((power(g.end_heps / g.start_heps, 1.0 / g.num_years) - 1::numeric) * 100::numeric, 2)
            ELSE NULL::numeric
        END AS historical_growth_cagr,
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
    round(g.num_years, 1) AS years_history,
    g.financials_date
   FROM latest_price p
     JOIN growth_calc g ON p.ticker::text = g.ticker::text;



-- DROP FUNCTION public.compute_watchlist_reward_risk_ratio();

CREATE OR REPLACE FUNCTION public.compute_watchlist_reward_risk_ratio()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
  reward numeric;
  risk numeric;
BEGIN
  -- Default to NULL if any of the inputs are missing
  IF NEW.target_price IS NULL OR NEW.entry_price IS NULL OR NEW.stop_loss IS NULL THEN
    NEW.reward_risk_ratio := NULL;
    RETURN NEW;
  END IF;

  IF COALESCE(NEW.is_long, true) THEN
    reward := NEW.target_price - NEW.entry_price;
    risk := NEW.entry_price - NEW.stop_loss;
  ELSE
    reward := NEW.entry_price - NEW.target_price;
    risk := NEW.stop_loss - NEW.entry_price;
  END IF;

  -- Protect against division by zero or negative risk values
  IF risk IS NULL OR risk <= 0 THEN
    NEW.reward_risk_ratio := NULL;
  ELSE
    NEW.reward_risk_ratio := ROUND((reward / risk)::numeric, 2);
  END IF;

  RETURN NEW;
END;
$function$
;

-- DROP FUNCTION public.notify_action_log_change();

CREATE OR REPLACE FUNCTION public.notify_action_log_change()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN
    -- Send notification on action_log_changes channel
    -- Payload contains the ticker that was affected
    PERFORM pg_notify(
        'action_log_changes',
        json_build_object(
            'ticker', NEW.ticker,
            'log_id', NEW.log_id,
            'is_read', NEW.is_read
        )::text
    );
    RETURN NEW;
END;
$function$
;