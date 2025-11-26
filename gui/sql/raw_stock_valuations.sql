-- Raw Stock Valuations Table
-- Stores multi-year fundamental data per ticker from ShareData financial results pages
-- One row per (ticker, financial year/period) combination

CREATE TABLE IF NOT EXISTS public.raw_stock_valuations (
    ticker varchar(20) NOT NULL,
    results_period_end date NOT NULL,
    results_period_label varchar(100) NOT NULL,
    heps_12m_zarc numeric(18, 4) NULL,
    dividend_12m_zarc numeric(18, 4) NULL,
    cash_gen_ps_zarc numeric(18, 4) NULL,
    nav_ps_zarc numeric(18, 4) NULL,
    quick_ratio numeric(18, 6) NULL,
    source varchar(50) DEFAULT 'sharedata' NULL,
    created_at timestamptz DEFAULT now() NULL,
    updated_at timestamptz DEFAULT now() NULL,
    CONSTRAINT raw_stock_valuations_pkey PRIMARY KEY (ticker, results_period_end),
    CONSTRAINT raw_stock_valuations_ticker_fkey FOREIGN KEY (ticker) 
        REFERENCES public.stock_details(ticker) ON DELETE CASCADE
);

-- Index for efficient querying of latest period per ticker
CREATE INDEX IF NOT EXISTS idx_raw_stock_valuations_ticker 
    ON public.raw_stock_valuations 
    USING btree (ticker, results_period_end DESC);

-- Comments for documentation
COMMENT ON TABLE public.raw_stock_valuations IS 'Historical fundamental data for multiple periods per ticker, scraped from ShareData';
COMMENT ON COLUMN public.raw_stock_valuations.results_period_end IS 'End date of the financial period (e.g., 2025-03-31 for Mar 2025)';
COMMENT ON COLUMN public.raw_stock_valuations.results_period_label IS 'Full human-readable period label from ShareData (e.g., "Mar 2025 Final (12m) 23 Jun 2025")';
COMMENT ON COLUMN public.raw_stock_valuations.heps_12m_zarc IS '12 Month HEPS in ZAR cents';
COMMENT ON COLUMN public.raw_stock_valuations.dividend_12m_zarc IS '12 Month Dividend in ZAR cents';
COMMENT ON COLUMN public.raw_stock_valuations.cash_gen_ps_zarc IS 'Cash Generated Per Share in ZAR cents';
COMMENT ON COLUMN public.raw_stock_valuations.nav_ps_zarc IS 'Net Asset Value Per Share in ZAR cents';
COMMENT ON COLUMN public.raw_stock_valuations.quick_ratio IS 'Quick Ratio (may be NULL for some sectors/periods)';
