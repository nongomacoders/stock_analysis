import logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(asctime)s - %(message)s',
    datefmt='%H:%M:%S'
)

logging.info("Starting script and setting up logger.")

import sys
import os
import pandas as pd
import matplotlib
try:
    matplotlib.use('TkAgg')
    logging.info("Successfully set Matplotlib backend to 'TkAgg'.")
except Exception as e:
    logging.error(f"Failed to set Matplotlib backend: {e}")
    sys.exit(1)

import matplotlib.pyplot as plt
import mplfinance as mpf

logging.info("Successfully imported Matplotlib and Mplfinance.")

try:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from data.yfinance_provider import YFinanceProvider
    from tools.fractal_levels import find_fractal_levels
    from tools.kmeans_levels import find_kmeans_levels
    from tools.kde_levels import find_kde_levels
    from tools.pivot_points import calculate_pivot_points
    from tools.zigzag_levels import find_zigzag_sr_levels
    logging.info("Successfully imported all custom project modules.")
except ImportError as e:
    logging.error(f"Failed to import a project module. Check paths and file names: {e}")
    sys.exit(1)

# --- Configuration ---
SYMBOL = 'PAN.JO'
START_DATE = '2024-01-01'
END_DATE = '2025-09-29'
REPLAY_SPEED = 0.05
MIN_BARS = 30
RECALC_INTERVAL = 5

# --- Select the Support/Resistance Method ---
# Options: 'fractal', 'kmeans', 'kde', 'zigzag', 'pivot'
SR_METHOD_CHOICE = 'fractal'

def get_sr_levels(method: str, df: pd.DataFrame):
    """A wrapper function to call the selected S/R method."""
    # This check prevents errors on very small data windows for all methods
    if len(df) < 20: 
        return []
    
    if method == 'fractal':
        supports, resistances = find_fractal_levels(df.copy())
        return supports + resistances
    
    elif method == 'kmeans':
        return find_kmeans_levels(df.copy(), n_clusters=6, order=5)
    
    # --- ADDED KDE OPTION ---
    elif method == 'kde':
        # Use average candle size as a dynamic bandwidth for the KDE
        avg_candle_size = (df['high'] - df['low']).mean()
        if pd.isna(avg_candle_size) or avg_candle_size == 0:
            return [] # Avoid errors if candle size is zero or NaN
        levels, _, _ = find_kde_levels(df.copy(), bandwidth=avg_candle_size, order=5)
        return levels
        
    # --- ADDED ZIGZAG OPTION ---
    elif method == 'zigzag':
        levels, _ = find_zigzag_sr_levels(df.copy(), deviation=0.05, n_clusters=6)
        return levels

    elif method == 'pivot':
        pivot_df = calculate_pivot_points(df.copy())
        # Ensure there's a previous day to calculate from
        if not pivot_df.empty:
            last_day = pivot_df.iloc[-1]
            levels = [
                last_day.get(p) for p in ['s3', 's2', 's1', 'pp', 'r1', 'r2', 'r3']
            ]
            # Filter out any None values if columns don't exist
            return [level for level in levels if level is not None]
        return []
        
    else: 
        logging.warning(f"Unknown S/R Method '{method}'. No levels will be calculated.")
        return []

if __name__ == "__main__":
    logging.info("Starting main execution block.")
    
    full_data = pd.DataFrame()
    try:
        logging.info(f"Attempting to fetch data for {SYMBOL} from {START_DATE} to {END_DATE}.")
        provider = YFinanceProvider(SYMBOL, START_DATE, END_DATE)
        full_data = provider.get_all_data()
        logging.info(f"Data fetching complete. Total rows: {len(full_data)}")
    except Exception as e:
        logging.error(f"An exception occurred during data fetching: {e}")
        sys.exit(1)

    if len(full_data) <= MIN_BARS:
        logging.error(f"Not enough data for replay. Loaded {len(full_data)} bars, but need > {MIN_BARS}.")
        sys.exit(1)

    fig, ax = None, None
    try:
        logging.info("Creating Matplotlib figure and axes.")
        fig, ax = plt.subplots(figsize=(15, 8))
        plt.style.use('dark_background')
        fig.set_facecolor('#121212')
        ax.set_facecolor('#121212')
        plt.ion()
        logging.info("Plot creation successful. Interactive mode is ON.")
        logging.info(f"Using Matplotlib backend: {matplotlib.get_backend()}")
    except Exception as e:
        logging.error(f"Failed to create Matplotlib plot: {e}")
        sys.exit(1)

    sr_levels = []
    
    logging.info(f"Starting replay loop from bar {MIN_BARS} to {len(full_data)}...")
    try:
        for i in range(MIN_BARS, len(full_data)):
            if not plt.fignum_exists(fig.number):
                logging.info("Plot window closed by user. Terminating replay.")
                break
            
            current_data = full_data.iloc[:i]
            ax.clear()

            if i % RECALC_INTERVAL == 0:
                sr_levels = get_sr_levels(SR_METHOD_CHOICE, current_data) or []

            mpf.plot(current_data, ax=ax, type='candle', style='nightclouds', volume=False)
            
            if sr_levels is not None and len(sr_levels) > 0:
                for level in sr_levels:
                    ax.axhline(y=level, color='cyan', linestyle='--', linewidth=0.7, alpha=0.8)

            ax.set_title(f"Replay: {SYMBOL} | Bar {i - MIN_BARS + 1}/{len(full_data) - MIN_BARS}")
            
            fig.canvas.draw()
            fig.canvas.flush_events()
            plt.pause(REPLAY_SPEED)

    except Exception as e:
        logging.error(f"An unexpected error occurred during the replay loop at bar {i}: {e}", exc_info=True)
    finally:
        logging.info("Replay loop finished or was interrupted.")
        if plt.fignum_exists(fig.number):
            logging.info("Displaying final plot. Close the plot window to exit.")
            plt.ioff()
            plt.show()
        else:
            logging.info("Script finished, but no plot window was open.")