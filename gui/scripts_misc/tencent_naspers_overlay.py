

import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt

# 1. Define the tickers
TENCENT_TICKER = 'TCEHY'  # Tencent Holdings Ltd (OTC)
NASPERS_TICKER = 'NPSNY'  # Naspers Ltd (OTC)

# 2. Fetch historical data
# We'll fetch data for the last 5 years
start_date = '2020-01-01'
end_date = pd.to_datetime('today').strftime('%Y-%m-%d')

print(f"Fetching data for {TENCENT_TICKER} and {NASPERS_TICKER} from {start_date} to {end_date}...")

try:
    # Fetch data without auto_adjust to see the raw structure
    tencent_data = yf.download(TENCENT_TICKER, start=start_date, end=end_date)
    naspers_data = yf.download(NASPERS_TICKER, start=start_date, end=end_date)
except Exception as e:
    print(f"An error occurred while fetching data: {e}")
    exit()

if tencent_data.empty or naspers_data.empty:
    print("Could not retrieve data for one or both tickers. Please check the ticker symbols or date range.")
    exit()

# 3. Select the 'Close' price and combine into a single DataFrame
# The yfinance library sometimes returns a MultiIndex for OTC stocks.
# We need to check the column structure and select the correct 'Close' column.

# Check if columns are MultiIndex
if isinstance(tencent_data.columns, pd.MultiIndex):
    tencent_close = tencent_data['Close'].iloc[:, 0] # Select the first column under 'Close'
    naspers_close = naspers_data['Close'].iloc[:, 0] # Select the first column under 'Close'
else:
    # Assume single-level index, which is the standard behavior
    tencent_close = tencent_data['Close']
    naspers_close = naspers_data['Close']

# Combine the two Series into a single DataFrame
combined_data = pd.DataFrame({
    'Tencent': tencent_close,
    'Naspers': naspers_close
})

# Drop any rows with missing data (e.g., non-trading days for one stock)
combined_data.dropna(inplace=True)

# 4. Normalize the data to show relative performance
# We normalize by dividing all prices by the first price in the series and multiplying by 100
# This sets the starting point for both stocks to 100, allowing for a direct comparison of percentage change
normalized_data = combined_data.div(combined_data.iloc[0]).mul(100)

# 5. Plot the normalized data
plt.figure(figsize=(12, 6))
plt.plot(normalized_data.index, normalized_data['Tencent'], label='Tencent (TCEHY)')
plt.plot(normalized_data.index, normalized_data['Naspers'], label='Naspers (NPSNY)')

# Add titles and labels
plt.title(f'Relative Stock Price Performance: Tencent vs. Naspers (Normalized to 100 on {normalized_data.index[0].strftime("%Y-%m-%d")})', fontsize=14)
plt.xlabel('Date', fontsize=12)
plt.ylabel('Relative Price (Base 100)', fontsize=12)
plt.legend(loc='upper left')
plt.grid(True, linestyle='--', alpha=0.6)

# Format the x-axis for better date display
plt.gcf().autofmt_xdate()

# 6. Save the plot to a file
output_file = 'tencent_naspers_overlay_chart.png'
plt.savefig(output_file)
print(f"\nChart successfully saved to {output_file}")
print("Script execution complete.")
