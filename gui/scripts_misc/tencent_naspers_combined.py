import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt

# -----------------------------------
# CONSTANT FUNDAMENTAL INPUTS
# -----------------------------------

PROSUS_TENCENT_STAKE = 0.228
NASPERS_PROSUS_STAKE = 0.434
LOOKTHROUGH = PROSUS_TENCENT_STAKE * NASPERS_PROSUS_STAKE

NASPERS_SHARES = 628_849_928
NPSNY_ADR_RATIO = 0.25

TENCENT_SHARES = 9_200_000_000

# -----------------------------------
# TICKERS
# -----------------------------------

TCEHY = "TCEHY"
NPSNY = "NPSNY"

# -----------------------------------
# DOWNLOAD DATA
# -----------------------------------

start = "2023-01-01"
end_date = pd.to_datetime("today").strftime("%Y-%m-%d")

print(f"Fetching data from {start} to {end_date}...")


def get_close(ticker):
    df = yf.download(
        ticker, start=start, end=end_date, auto_adjust=False, progress=False
    )
    if isinstance(df.columns, pd.MultiIndex):
        return df["Close"].iloc[:, 0]
    return df["Close"]


tcehy = get_close(TCEHY)
npsny = get_close(NPSNY)

df = pd.concat([tcehy, npsny], axis=1)
df.columns = ["TCEHY", "NPSNY"]
df.dropna(inplace=True)

# -----------------------------------
# DISCOUNT CALCULATION
# -----------------------------------

df["Tencent_MktCap_USD"] = df["TCEHY"] * TENCENT_SHARES
df["Naspers_Tencent_Value_USD"] = df["Tencent_MktCap_USD"] * LOOKTHROUGH
df["Tencent_NAV_per_NPN_USD"] = df["Naspers_Tencent_Value_USD"] / NASPERS_SHARES
df["Tencent_NAV_per_NPSNY"] = df["Tencent_NAV_per_NPN_USD"] * NPSNY_ADR_RATIO
df["Discount"] = 1 - (df["NPSNY"] / df["Tencent_NAV_per_NPSNY"])

for window in [200, 50, 14]:
    df[f"Disc_MA{window}"] = df["Discount"].rolling(window).mean()

# -----------------------------------
# NORMALIZED OVERLAY DATA
# -----------------------------------

normalized_data = df[["TCEHY", "NPSNY"]].div(df[["TCEHY", "NPSNY"]].iloc[0]).mul(100)
difference = normalized_data["TCEHY"] - normalized_data["NPSNY"]

# -----------------------------------
# PLOT
# -----------------------------------

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), sharex=True)

ax1.plot(
    normalized_data.index,
    normalized_data["TCEHY"],
    label="Tencent (TCEHY)",
    color="blue",
)
ax1.plot(
    normalized_data.index,
    normalized_data["NPSNY"],
    label="Naspers (NPSNY)",
    color="orange",
)
ax1.fill_between(
    difference.index,
    0,
    difference,
    where=(difference >= 0),
    color="green",
    alpha=0.2,
    label="Tencent > Naspers",
)
ax1.fill_between(
    difference.index,
    0,
    difference,
    where=(difference < 0),
    color="red",
    alpha=0.2,
    label="Naspers > Tencent",
)
ax1.set_ylabel("Relative Price (Base 100)", fontsize=12)
ax1.legend(loc="upper left")
ax1.grid(True, linestyle="--", alpha=0.6)

ax1_twin = ax1.twinx()
ax1_twin.plot(
    difference.index,
    difference,
    label="Difference",
    color="purple",
    linestyle="--",
    linewidth=1.5,
)
ax1_twin.set_ylabel("Difference", fontsize=12)
ax1_twin.legend(loc="upper right")
ax1_twin.axhline(y=0, color="gray", linestyle="-", linewidth=0.5)

ax2.plot(df.index, df["Discount"], label="Discount")
ax2.plot(df.index, df["Disc_MA200"], label="200d MA")
ax2.plot(df.index, df["Disc_MA50"], label="50d MA")
ax2.plot(df.index, df["Disc_MA14"], label="14d MA")
ax2.set_xlabel("Date", fontsize=12)
ax2.set_ylabel("Discount", fontsize=12)
ax2.legend(loc="upper left")
ax2.grid(True, linestyle="--", alpha=0.6)

fig.suptitle(f"Tencent vs Naspers Analysis (From {start})", fontsize=14)
fig.autofmt_xdate()

plt.savefig("tencent_naspers_combined.png", dpi=150)
plt.close()

print("Chart saved to tencent_naspers_combined.png")
