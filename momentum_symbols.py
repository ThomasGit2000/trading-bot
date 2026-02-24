"""
NYSE Momentum Stocks - ~500 symbols
Ready to use in trading applications
"""

MOMENTUM_STOCKS = [
    # Top Tech Momentum
    "NVDA", "AVGO", "META", "PLTR", "MSFT", "ORCL", "AMD", "NFLX", "GOOGL", "GOOG",
    "AMAT", "LRCX", "MU", "ANET", "KLAC", "CSCO", "INTC", "CRM", "ADBE", "INTU",
    "SNPS", "CDNS", "CRWD", "NOW", "PANW", "DDOG", "ZS", "NET", "MDB", "SNOW",

    # Financials Momentum
    "JPM", "GS", "MS", "BAC", "WFC", "BLK", "AXP", "COF", "SCHW", "ICE",
    "CME", "SPGI", "MCO", "MSCI", "NDAQ", "CBOE", "KKR", "APO", "ARES", "BX",
    "TPG", "CG", "OWL", "VCTR", "STEP", "HLNE", "AMG", "APAM", "BN", "BAM",

    # Industrial Momentum
    "GE", "GEV", "CAT", "RTX", "HON", "DE", "LMT", "NOC", "GD", "BA",
    "ETN", "PH", "EMR", "ROK", "CMI", "PCAR", "FAST", "URI", "PWR", "WAB",
    "TDG", "TT", "CARR", "OTIS", "IR", "DOV", "ITW", "SWK", "SNA", "AME",

    # Healthcare Momentum
    "LLY", "UNH", "TMO", "ABT", "DHR", "ISRG", "SYK", "BSX", "MDT", "ZBH",
    "VRTX", "REGN", "AMGN", "GILD", "BIIB", "MRNA", "BMY", "MRK", "PFE", "JNJ",
    "MCK", "CAH", "ABC", "CI", "ELV", "HUM", "CNC", "MOH", "DVA", "HCA",

    # Consumer Momentum
    "AMZN", "WMT", "COST", "TJX", "HD", "LOW", "ORLY", "AZO", "TSCO", "ULTA",
    "NKE", "LULU", "RL", "TPR", "DECK", "CMG", "MCD", "SBUX", "YUM", "DRI",
    "CCL", "RCL", "BKNG", "HLT", "MAR", "LVS", "WYNN", "MGM", "DKNG", "PENN",

    # Energy Momentum
    "XOM", "CVX", "COP", "EOG", "SLB", "BKR", "HAL", "OXY", "PSX", "MPC",
    "VLO", "FANG", "DVN", "APA", "EQT", "TRGP", "OKE", "KMI", "WMB", "ET",

    # Materials Momentum
    "LIN", "APD", "SHW", "ECL", "DD", "PPG", "NUE", "STLD", "FCX", "NEM",
    "MLM", "VMC", "ALB", "MOS", "CF", "CE", "EMN", "LYB", "DOW", "BALL",

    # Real Estate Momentum
    "PLD", "AMT", "CCI", "EQIX", "SPG", "O", "DLR", "PSA", "WELL", "EXR",
    "AVB", "EQR", "VTR", "VICI", "IRM", "UDR", "MAA", "ESS", "REG", "KIM",

    # Utilities Momentum
    "NEE", "SO", "DUK", "CEG", "AEP", "D", "SRE", "EXC", "XEL", "ED",
    "PEG", "ETR", "WEC", "ES", "AEE", "DTE", "FE", "PPL", "CNP", "CMS",
    "NRG", "VST", "ATO", "NI", "EVRG", "LNT", "AWK", "PCG", "EIX", "PNW",

    # Communication Services Momentum
    "T", "VZ", "TMUS", "CMCSA", "CHTR", "DIS", "WBD", "PARA", "FOX", "FOXA",
    "NWSA", "NWS", "EA", "TTWO", "ZM", "DOCU", "SPOT", "LYV", "MTCH", "IAC",

    # Semiconductors Momentum
    "NVDA", "AVGO", "AMD", "QCOM", "TXN", "ADI", "NXPI", "MCHP", "ON", "MPWR",
    "SWKS", "QRVO", "MRVL", "LRCX", "AMAT", "KLAC", "ASML", "TSM", "ARM", "SMCI",

    # EV & Clean Energy Momentum
    "TSLA", "RIVN", "LCID", "NIO", "XPEV", "LI", "GM", "F", "STLA", "HMC",
    "ENPH", "SEDG", "FSLR", "RUN", "NOVA", "ARRY", "PLUG", "FCEL", "BE", "CHPT",

    # Fintech Momentum
    "V", "MA", "PYPL", "SQ", "COIN", "HOOD", "AFRM", "UPST", "SOFI", "LC",
    "FISV", "FIS", "GPN", "CPAY", "FI", "WEX", "FOUR", "TOST", "BILL", "MQ",

    # Software & Cloud Momentum
    "CRM", "NOW", "ADBE", "ORCL", "SAP", "WDAY", "VEEV", "HUBS", "ZS", "CRWD",
    "PANW", "FTNT", "OKTA", "DDOG", "MDB", "SNOW", "NET", "TEAM", "DOCN", "PATH",

    # Biotech Momentum
    "MRNA", "BNTX", "NVAX", "CRSP", "EDIT", "NTLA", "BEAM", "VERV", "BLUE", "FATE",
    "ALNY", "IONS", "SGEN", "ARGX", "SWTX", "NTRA", "EXAS", "GH", "ILMN", "TXG",

    # China ADR Momentum
    "BABA", "JD", "PDD", "NIO", "XPEV", "LI", "BIDU", "TME", "BILI", "IQ",
    "TAL", "EDU", "VIPS", "FUTU", "BZUN", "ZH", "KC", "TUYA", "HUYA", "DOYU",

    # Crypto & Blockchain Momentum
    "COIN", "MARA", "RIOT", "HUT", "BTBT", "BITF", "CIFR", "HIVE", "CLSK", "CORZ",
    "IREN", "BTDR", "MSTR", "SMLR", "NCTY", "ARBK", "GREE", "WULF", "DMGI", "BTCS",

    # Meme & Retail Favorites
    "GME", "AMC", "BBBY", "BB", "EXPR", "KOSS", "CLOV", "WISH", "PLTR", "SOFI",

    # Cannabis Momentum
    "TLRY", "CGC", "ACB", "CRON", "OGI", "HEXO", "SNDL", "VFF", "GRWG", "CURLF",

    # Cybersecurity Momentum
    "PANW", "CRWD", "ZS", "FTNT", "OKTA", "CYBR", "QLYS", "VRNS", "TENB", "SAIL",

    # AI & Data Momentum
    "NVDA", "PLTR", "AI", "SNOW", "MDB", "DDOG", "PATH", "SOUN", "BBAI", "PRCT",

    # Aerospace & Defense Momentum
    "LMT", "RTX", "NOC", "GD", "BA", "LHX", "TDG", "HWM", "TXT", "HII",
    "LDOS", "SAIC", "BAH", "CACI", "KTOS", "RKLB", "SPCE", "RDW", "ASTR", "ASTS",

    # Transportation Momentum
    "UNP", "CSX", "NSC", "UPS", "FDX", "JBHT", "ODFL", "XPO", "CHRW", "SAIA",
    "DAL", "UAL", "LUV", "AAL", "JBLU", "ALK", "HA", "SAVE", "ULCC", "SNCY",

    # Insurance Momentum
    "PGR", "TRV", "CB", "ALL", "MET", "AFL", "PRU", "AIG", "HIG", "CINF",
    "WRB", "AXS", "RNR", "ACGL", "KNSL", "RYAN", "ERIE", "GL", "UNM", "CNO",

    # REITs Momentum
    "PLD", "AMT", "CCI", "EQIX", "SPG", "PSA", "O", "DLR", "WELL", "VTR",
    "IRM", "EXR", "VICI", "AVB", "EQR", "UDR", "MAA", "ESS", "SUI", "ELS",

    # Media & Entertainment Momentum
    "DIS", "NFLX", "WBD", "PARA", "LYV", "SPOT", "RBLX", "U", "TTWO", "EA",

    # Auto Momentum
    "TSLA", "GM", "F", "RIVN", "LCID", "NIO", "XPEV", "LI", "STLA", "HMC",
    "TM", "RACE", "AN", "PAG", "LAD", "ABG", "SAH", "GPI", "ORLY", "AZO",

    # Retail Momentum
    "AMZN", "WMT", "TGT", "COST", "HD", "LOW", "TJX", "ROST", "BBY", "DG",
    "DLTR", "KR", "ACI", "SFM", "GO", "BJ", "OLLI", "FIVE", "ULTA", "WSM",

    # Food & Beverage Momentum
    "KO", "PEP", "MDLZ", "HSY", "KHC", "GIS", "K", "CAG", "CPB", "SJM",
    "MKC", "HRL", "TSN", "PPC", "SAFM", "JJSF", "LANC", "POST", "BRBR", "CELH",

    # Telecom Momentum
    "T", "VZ", "TMUS", "LUMN", "FTR", "USM", "TDS", "SHEN", "CNSL", "GOGO",

    # Chemicals Momentum
    "LIN", "APD", "DD", "DOW", "LYB", "EMN", "CE", "HUN", "OLN", "CC",
    "WLK", "AXTA", "RPM", "PPG", "SHW", "ECL", "ALB", "MOS", "NTR", "CF",

    # Metals & Mining Momentum
    "NEM", "FCX", "GOLD", "AEM", "KGC", "AU", "AGI", "PAAS", "HL", "CDE",
    "NUE", "STLD", "X", "CLF", "AA", "ATI", "CENX", "KALU", "CMC", "RS"
]

# Deduplicate while preserving order
seen = set()
MOMENTUM_STOCKS = [x for x in MOMENTUM_STOCKS if not (x in seen or seen.add(x))]

print(f"Total momentum stocks: {len(MOMENTUM_STOCKS)}")

# Export as simple list
if __name__ == "__main__":
    print("\nMomentum Stocks List:")
    print(MOMENTUM_STOCKS)
