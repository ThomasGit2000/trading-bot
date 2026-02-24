"""
Momentum Stock Screener - Generates ~500 NYSE momentum stocks
Uses Yahoo Finance for real-time momentum calculation
"""

import yfinance as yf
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
warnings.filterwarnings('ignore')

# Large-cap and mid-cap NYSE stocks (high liquidity candidates)
NYSE_STOCKS = [
    # S&P 500 + Russell 1000 NYSE-listed stocks
    "MMM", "ABT", "ABBV", "ACN", "ADBE", "AMD", "AES", "AFL", "A", "APD",
    "AKAM", "ALB", "ALK", "ALL", "GOOGL", "GOOG", "MO", "AMZN", "AEE", "AAL",
    "AEP", "AXP", "AIG", "AMT", "AWK", "AMP", "ABC", "AME", "AMGN", "APH",
    "ADI", "ANSS", "AON", "APA", "AAPL", "AMAT", "APTV", "ACGL", "ADM", "ANET",
    "AJG", "AIZ", "T", "ATO", "ADSK", "ADP", "AZO", "AVB", "AVY", "AXON",
    "BKR", "BALL", "BAC", "BK", "BAX", "BDX", "BRK.B", "BBY", "BIO", "TECH",
    "BIIB", "BLK", "BA", "BKNG", "BWA", "BSX", "BMY", "AVGO", "BR", "BRO",
    "BF.B", "BLDR", "BG", "BXP", "CHRW", "CDNS", "CZR", "CPT", "CPB", "COF",
    "CAH", "KMX", "CCL", "CARR", "CTLT", "CAT", "CBOE", "CBRE", "CDW", "CE",
    "COR", "CNC", "CNP", "CF", "CRL", "SCHW", "CHTR", "CVX", "CMG", "CB",
    "CHD", "CI", "CINF", "CTAS", "CSCO", "C", "CFG", "CLX", "CME", "CMS",
    "KO", "CTSH", "CL", "CMCSA", "CAG", "COP", "ED", "STZ", "CEG", "COO",
    "CPRT", "GLW", "CPAY", "CTVA", "CSGP", "COST", "CTRA", "CCI", "CSX", "CMI",
    "CVS", "DHR", "DRI", "DVA", "DAY", "DECK", "DE", "DAL", "DVN", "DXCM",
    "FANG", "DLR", "DFS", "DG", "DLTR", "D", "DPZ", "DOV", "DOW", "DHI",
    "DTE", "DUK", "DD", "EMN", "ETN", "EBAY", "ECL", "EIX", "EW", "EA",
    "ELV", "EMR", "ENPH", "ETR", "EOG", "EPAM", "EQT", "EFX", "EQIX", "EQR",
    "ERIE", "ESS", "EL", "EG", "EVRG", "ES", "EXC", "EXPE", "EXPD", "EXR",
    "XOM", "FFIV", "FDS", "FICO", "FAST", "FRT", "FDX", "FIS", "FITB", "FSLR",
    "FE", "FI", "FMC", "F", "FTNT", "FTV", "FOXA", "FOX", "BEN", "FCX",
    "GRMN", "IT", "GE", "GEHC", "GEV", "GEN", "GNRC", "GD", "GIS", "GM",
    "GPC", "GILD", "GPN", "GL", "GDDY", "GS", "HAL", "HIG", "HAS", "HCA",
    "DOC", "HSIC", "HSY", "HES", "HPE", "HLT", "HOLX", "HD", "HON", "HRL",
    "HST", "HWM", "HPQ", "HUBB", "HUM", "HBAN", "HII", "IBM", "IEX", "IDXX",
    "ITW", "INCY", "IR", "PODD", "INTC", "ICE", "IFF", "IP", "IPG", "INTU",
    "ISRG", "IVZ", "INVH", "IQV", "IRM", "JBHT", "JBL", "JKHY", "J", "JNJ",
    "JCI", "JPM", "JNPR", "K", "KVUE", "KDP", "KEY", "KEYS", "KMB", "KIM",
    "KMI", "KKR", "KLAC", "KHC", "KR", "LHX", "LH", "LRCX", "LW", "LVS",
    "LDOS", "LEN", "LII", "LLY", "LIN", "LYV", "LKQ", "LMT", "L", "LOW",
    "LULU", "LYB", "MTB", "MRO", "MPC", "MKTX", "MAR", "MMC", "MLM", "MAS",
    "MA", "MTCH", "MKC", "MCD", "MCK", "MDT", "MRK", "META", "MET", "MTD",
    "MGM", "MCHP", "MU", "MSFT", "MAA", "MRNA", "MHK", "MOH", "TAP", "MDLZ",
    "MPWR", "MNST", "MCO", "MS", "MOS", "MSI", "MSCI", "NDAQ", "NTAP", "NFLX",
    "NEM", "NWSA", "NWS", "NEE", "NKE", "NI", "NDSN", "NSC", "NTRS", "NOC",
    "NCLH", "NRG", "NUE", "NVDA", "NVR", "NXPI", "ORLY", "OXY", "ODFL", "OMC",
    "ON", "OKE", "ORCL", "OTIS", "PCAR", "PKG", "PLTR", "PANW", "PARA", "PH",
    "PAYX", "PAYC", "PYPL", "PNR", "PEP", "PFE", "PCG", "PM", "PSX", "PNW",
    "PNC", "POOL", "PPG", "PPL", "PFG", "PG", "PGR", "PLD", "PRU", "PEG",
    "PTC", "PSA", "PHM", "QRVO", "PWR", "QCOM", "DGX", "RL", "RJF", "RTX",
    "O", "REG", "REGN", "RF", "RSG", "RMD", "RVTY", "RHI", "ROK", "ROL",
    "ROP", "ROST", "RCL", "SPGI", "CRM", "SBAC", "SLB", "STX", "SRE", "NOW",
    "SHW", "SPG", "SWKS", "SJM", "SW", "SNA", "SOLV", "SO", "LUV", "SWK",
    "SBUX", "STT", "STLD", "STE", "SYK", "SMCI", "SYF", "SNPS", "SYY", "TMUS",
    "TROW", "TTWO", "TPR", "TRGP", "TGT", "TEL", "TDY", "TFX", "TER", "TSLA",
    "TXN", "TXT", "TMO", "TJX", "TSCO", "TT", "TDG", "TRV", "TRMB", "TFC",
    "TYL", "TSN", "USB", "UBER", "UDR", "ULTA", "UNP", "UAL", "UPS", "URI",
    "UNH", "UHS", "VLO", "VTR", "VLTO", "VRSN", "VRSK", "VZ", "VRTX", "VTRS",
    "VICI", "V", "VST", "VMC", "WRB", "GWW", "WAB", "WBA", "WMT", "DIS",
    "WBD", "WM", "WAT", "WEC", "WFC", "WELL", "WST", "WDC", "WY", "WMB",
    "WTW", "WYNN", "XEL", "XYL", "YUM", "ZBRA", "ZBH", "ZTS",
    # Additional NYSE high-volume stocks
    "BABA", "JD", "PDD", "NIO", "XPEV", "LI", "BIDU", "TME", "BILI", "IQ",
    "TAL", "EDU", "VIPS", "YY", "HUYA", "DOYU", "WB", "ZH", "TUYA", "KC",
    "FTCH", "WISH", "OPEN", "SOFI", "HOOD", "COIN", "RIVN", "LCID", "FSR",
    "CHPT", "QS", "BLNK", "EVGO", "NKLA", "GOEV", "RIDE", "WKHS", "ARVL",
    "PSNY", "FFIE", "MULN", "REE", "PTRA", "XOS", "HYLN", "VLCN", "GGR",
    "SQ", "AFRM", "UPST", "LC", "TREE", "LDI", "UWMC", "RKT", "GHLD",
    "W", "ETSY", "CHWY", "RVLV", "RENT", "REAL", "RDFN", "OPEN", "CSGP",
    "ZG", "Z", "COMP", "ANGI", "IAC", "MTCH", "BMBL", "GRND", "APPS",
    "U", "RBLX", "DKNG", "PENN", "RSI", "GENI", "SKLZ", "PLTK", "SLGG",
    "GME", "AMC", "BB", "BBBY", "EXPR", "KOSS", "NAKD", "SNDL", "TLRY",
    "CGC", "ACB", "CRON", "OGI", "HEXO", "VFF", "GRWG", "CURLF", "GTBIF",
    "PLUG", "FCEL", "BLDP", "BE", "BLOOM", "ENPH", "SEDG", "RUN", "NOVA",
    "ARRY", "SPWR", "CSIQ", "JKS", "DQ", "MAXN", "STEM", "ENVX", "QS",
    "CLNE", "GEVO", "NKLA", "HYLN", "PTRA", "XOS", "REE", "GOEV", "RIDE",
    "CRSP", "EDIT", "NTLA", "BEAM", "VERV", "SGMO", "BLUE", "FATE", "ALNY",
    "MRNA", "BNTX", "NVAX", "VXRT", "INO", "OCGN", "SAVA", "SRNE", "AGEN",
    "ARCT", "IBIO", "CODX", "QDEL", "DGX", "LH", "PKI", "A", "TMO", "DHR"
]

# Remove duplicates and clean
NYSE_STOCKS = list(set([s.upper() for s in NYSE_STOCKS if s]))

def calculate_momentum(symbol):
    """Calculate 12-month momentum (excluding last month) for a stock"""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1y")

        if len(hist) < 200:  # Need enough data
            return None

        # 12-month return excluding last month (standard momentum factor)
        price_12m_ago = hist['Close'].iloc[0]
        price_1m_ago = hist['Close'].iloc[-22] if len(hist) > 22 else hist['Close'].iloc[0]
        current_price = hist['Close'].iloc[-1]

        # Momentum = 12-month return - 1-month return (reversal adjustment)
        momentum_12m = (price_1m_ago - price_12m_ago) / price_12m_ago * 100

        # Also get some basic info
        avg_volume = hist['Volume'].mean()

        return {
            'symbol': symbol,
            'momentum_12m': round(momentum_12m, 2),
            'current_price': round(current_price, 2),
            'avg_volume': int(avg_volume)
        }
    except Exception as e:
        return None

def get_momentum_stocks(min_stocks=500, min_volume=500000):
    """Get top momentum stocks from NYSE"""
    print(f"Screening {len(NYSE_STOCKS)} stocks for momentum...")

    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(calculate_momentum, symbol): symbol for symbol in NYSE_STOCKS}

        for i, future in enumerate(as_completed(futures)):
            result = future.result()
            if result and result['avg_volume'] >= min_volume:
                results.append(result)

            if (i + 1) % 50 == 0:
                print(f"Processed {i + 1}/{len(NYSE_STOCKS)} stocks...")

    # Sort by momentum (highest first)
    df = pd.DataFrame(results)
    df = df.sort_values('momentum_12m', ascending=False)

    # Take top stocks
    df = df.head(min_stocks)

    return df

def save_momentum_list(df, filename="momentum_stocks_list.txt"):
    """Save momentum stocks to a simple list file"""
    with open(filename, 'w') as f:
        f.write("# NYSE Momentum Stocks\n")
        f.write(f"# Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"# Total: {len(df)} stocks\n")
        f.write("# Format: SYMBOL, 12M_MOMENTUM%, PRICE, AVG_VOLUME\n\n")

        for _, row in df.iterrows():
            f.write(f"{row['symbol']}\n")

    # Also save detailed CSV
    df.to_csv(filename.replace('.txt', '.csv'), index=False)
    print(f"Saved {len(df)} stocks to {filename}")

if __name__ == "__main__":
    print("Fetching NYSE momentum stocks...")
    df = get_momentum_stocks(min_stocks=500, min_volume=100000)

    if len(df) > 0:
        save_momentum_list(df, "momentum_stocks_list.txt")
        print(f"\nTop 20 Momentum Stocks:")
        print(df.head(20).to_string(index=False))
    else:
        print("No stocks found. Check internet connection.")
