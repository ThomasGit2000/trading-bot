"""
Master Stock Universe - Categorized NYSE Momentum Stocks
~500 stocks organized by sector/category
"""

STOCK_CATEGORIES = {
    "MEGA_CAP_TECH": {
        "description": "Mega-cap technology leaders",
        "symbols": [
            "AAPL", "MSFT", "GOOGL", "GOOG", "META", "NVDA", "AVGO", "ORCL",
            "CRM", "ADBE", "CSCO", "ACN", "IBM", "INTC", "AMD", "QCOM"
        ]
    },

    "SEMICONDUCTORS": {
        "description": "Semiconductor & chip makers",
        "symbols": [
            "NVDA", "AMD", "AVGO", "QCOM", "TXN", "ADI", "NXPI", "MCHP",
            "ON", "MPWR", "SWKS", "QRVO", "LRCX", "AMAT", "KLAC", "MU",
            "MRVL", "SMCI", "ARM", "TSM", "ASML", "INTC"
        ]
    },

    "SOFTWARE_CLOUD": {
        "description": "Enterprise software & cloud",
        "symbols": [
            "CRM", "NOW", "ADBE", "ORCL", "SAP", "WDAY", "VEEV", "HUBS",
            "TEAM", "DOCN", "PATH", "MDB", "SNOW", "DDOG", "NET", "BILL",
            "OKTA", "ZM", "DOCU", "CFLT", "GTLB", "ESTC", "PD", "DBX"
        ]
    },

    "CYBERSECURITY": {
        "description": "Cybersecurity companies",
        "symbols": [
            "PANW", "CRWD", "ZS", "FTNT", "OKTA", "CYBR", "QLYS", "VRNS",
            "TENB", "S", "SAIL", "RPD", "NSIT", "LDOS", "BAH", "SAIC"
        ]
    },

    "FINTECH": {
        "description": "Financial technology & payments",
        "symbols": [
            "V", "MA", "PYPL", "SQ", "COIN", "HOOD", "AFRM", "UPST",
            "SOFI", "LC", "FISV", "FIS", "GPN", "CPAY", "FI", "WEX",
            "FOUR", "TOST", "BILL", "MQ", "PAYO", "DLO"
        ]
    },

    "BANKS_MAJOR": {
        "description": "Major banks & financial institutions",
        "symbols": [
            "JPM", "BAC", "WFC", "C", "GS", "MS", "USB", "PNC", "TFC",
            "COF", "AXP", "SCHW", "BK", "STT", "NTRS", "CFG", "KEY",
            "RF", "HBAN", "MTB", "FITB", "ZION", "CMA", "FHN"
        ]
    },

    "ASSET_MANAGERS": {
        "description": "Asset managers & private equity",
        "symbols": [
            "BLK", "KKR", "APO", "ARES", "BX", "CG", "TPG", "OWL",
            "VCTR", "STEP", "HLNE", "AMG", "APAM", "BN", "BAM", "IVZ",
            "BEN", "TROW", "FHI", "EV", "JHG", "AB"
        ]
    },

    "INSURANCE": {
        "description": "Insurance companies",
        "symbols": [
            "PGR", "TRV", "CB", "ALL", "MET", "AFL", "PRU", "AIG",
            "HIG", "CINF", "WRB", "AXS", "RNR", "ACGL", "KNSL", "RYAN",
            "ERIE", "GL", "UNM", "CNO", "AIZ", "LNC", "PFG", "VOYA"
        ]
    },

    "HEALTHCARE_PHARMA": {
        "description": "Pharmaceutical & healthcare majors",
        "symbols": [
            "LLY", "UNH", "JNJ", "MRK", "PFE", "ABBV", "BMY", "AMGN",
            "GILD", "REGN", "VRTX", "BIIB", "MRNA", "ZTS", "CI", "ELV",
            "HUM", "CNC", "MOH", "DVA", "HCA", "THC", "UHS", "ACHC"
        ]
    },

    "MEDICAL_DEVICES": {
        "description": "Medical devices & equipment",
        "symbols": [
            "TMO", "DHR", "ABT", "ISRG", "SYK", "BSX", "MDT", "ZBH",
            "EW", "BDX", "BAX", "HOLX", "IDXX", "DXCM", "PODD", "ALGN",
            "TFX", "STE", "RVTY", "A", "WAT", "MTD", "PKI"
        ]
    },

    "BIOTECH": {
        "description": "Biotechnology companies",
        "symbols": [
            "MRNA", "BNTX", "NVAX", "CRSP", "EDIT", "NTLA", "BEAM",
            "VERV", "BLUE", "FATE", "ALNY", "IONS", "SGEN", "ARGX",
            "SWTX", "NTRA", "EXAS", "GH", "ILMN", "TXG", "VCYT"
        ]
    },

    "INDUSTRIALS_DIVERSIFIED": {
        "description": "Diversified industrials",
        "symbols": [
            "GE", "GEV", "HON", "MMM", "CAT", "DE", "EMR", "ITW",
            "ETN", "PH", "ROK", "CMI", "DOV", "IR", "AME", "XYL",
            "NDSN", "ROP", "IEX", "FTV", "GGG", "RBC"
        ]
    },

    "AEROSPACE_DEFENSE": {
        "description": "Aerospace & defense contractors",
        "symbols": [
            "RTX", "LMT", "NOC", "GD", "BA", "LHX", "TDG", "HWM",
            "TXT", "HII", "LDOS", "SAIC", "BAH", "CACI", "KTOS",
            "RKLB", "SPCE", "RDW", "ASTS", "LUNR"
        ]
    },

    "TRANSPORTATION": {
        "description": "Logistics & transportation",
        "symbols": [
            "UNP", "CSX", "NSC", "UPS", "FDX", "JBHT", "ODFL", "XPO",
            "CHRW", "SAIA", "EXPD", "LSTR", "HUBG", "SNDR", "WERN",
            "KNX", "ARCB", "ECHO", "GXO", "XPO"
        ]
    },

    "AIRLINES": {
        "description": "Major airlines",
        "symbols": [
            "DAL", "UAL", "LUV", "AAL", "JBLU", "ALK", "HA", "SAVE",
            "ULCC", "ALGT", "SKYW", "MESA", "RYAAY", "VLRS"
        ]
    },

    "CONSUMER_RETAIL": {
        "description": "Consumer retail & e-commerce",
        "symbols": [
            "AMZN", "WMT", "TGT", "COST", "HD", "LOW", "TJX", "ROST",
            "BBY", "DG", "DLTR", "KR", "ACI", "SFM", "GO", "BJ",
            "OLLI", "FIVE", "ULTA", "WSM", "RH", "W", "ETSY", "CHWY"
        ]
    },

    "AUTO_RETAIL": {
        "description": "Auto dealers & parts retail",
        "symbols": [
            "ORLY", "AZO", "AAP", "GPC", "AN", "PAG", "LAD", "ABG",
            "SAH", "GPI", "SMP", "DORM", "CWH", "LCII", "LKQ", "MNRO"
        ]
    },

    "RESTAURANTS": {
        "description": "Restaurant chains",
        "symbols": [
            "MCD", "SBUX", "CMG", "YUM", "DRI", "QSR", "WING", "TXRH",
            "DENN", "EAT", "CAKE", "DIN", "PLAY", "JACK", "SHAK", "BROS"
        ]
    },

    "FOOD_BEVERAGE": {
        "description": "Food & beverage companies",
        "symbols": [
            "KO", "PEP", "MDLZ", "HSY", "KHC", "GIS", "K", "CAG",
            "CPB", "SJM", "MKC", "HRL", "TSN", "PPC", "JJSF", "LANC",
            "POST", "BRBR", "CELH", "MNST", "BF.B", "STZ", "TAP"
        ]
    },

    "HOTELS_LEISURE": {
        "description": "Hotels, casinos & leisure",
        "symbols": [
            "MAR", "HLT", "H", "IHG", "WH", "CHH", "CCL", "RCL",
            "NCLH", "LVS", "WYNN", "MGM", "CZR", "DKNG", "PENN",
            "BKNG", "ABNB", "EXPE", "TRIP", "MTN", "SKX"
        ]
    },

    "ENERGY_OIL_GAS": {
        "description": "Oil & gas producers",
        "symbols": [
            "XOM", "CVX", "COP", "EOG", "OXY", "DVN", "APA", "FANG",
            "MRO", "HES", "PXD", "EQT", "RRC", "AR", "SWN", "CTRA",
            "MTDR", "CHRD", "PR", "MGY", "VTLE", "ESTE"
        ]
    },

    "ENERGY_SERVICES": {
        "description": "Energy services & equipment",
        "symbols": [
            "SLB", "BKR", "HAL", "FTI", "NOV", "CHX", "WHD", "OII",
            "HP", "PTEN", "NBR", "RIG", "VAL", "DO", "NE"
        ]
    },

    "ENERGY_MIDSTREAM": {
        "description": "Pipelines & midstream",
        "symbols": [
            "WMB", "KMI", "OKE", "TRGP", "ET", "EPD", "MMP", "PAA",
            "MPLX", "ENLC", "WES", "HESM", "DCP", "CEQP", "AM"
        ]
    },

    "REFINING": {
        "description": "Refiners & marketing",
        "symbols": [
            "PSX", "MPC", "VLO", "DINO", "PBF", "DK", "CVI", "PARR"
        ]
    },

    "UTILITIES": {
        "description": "Electric & gas utilities",
        "symbols": [
            "NEE", "SO", "DUK", "AEP", "D", "SRE", "EXC", "XEL",
            "ED", "PEG", "ETR", "WEC", "ES", "AEE", "DTE", "FE",
            "PPL", "CNP", "CMS", "NRG", "VST", "ATO", "NI", "EVRG",
            "LNT", "AWK", "PCG", "EIX", "PNW", "CEG"
        ]
    },

    "REITS_DIVERSIFIED": {
        "description": "Diversified REITs",
        "symbols": [
            "PLD", "AMT", "CCI", "EQIX", "SPG", "PSA", "O", "DLR",
            "WELL", "VTR", "IRM", "EXR", "VICI", "AVB", "EQR", "UDR",
            "MAA", "ESS", "SUI", "ELS", "CPT", "AIV", "REG", "KIM"
        ]
    },

    "MATERIALS_CHEMICALS": {
        "description": "Chemicals & specialty materials",
        "symbols": [
            "LIN", "APD", "SHW", "ECL", "DD", "PPG", "RPM", "AXTA",
            "CE", "EMN", "HUN", "OLN", "CC", "WLK", "LYB", "DOW",
            "ALB", "FMC", "MOS", "NTR", "CF", "SMG", "CTVA"
        ]
    },

    "METALS_MINING": {
        "description": "Metals & mining",
        "symbols": [
            "NEM", "FCX", "GOLD", "AEM", "KGC", "AU", "AGI", "PAAS",
            "HL", "CDE", "NUE", "STLD", "X", "CLF", "AA", "ATI",
            "CENX", "KALU", "CMC", "RS", "SCHN", "ZEUS"
        ]
    },

    "EV_AUTOMAKERS": {
        "description": "Electric vehicle makers",
        "symbols": [
            "TSLA", "RIVN", "LCID", "NIO", "XPEV", "LI", "FSR", "GOEV",
            "VFS", "PSNY", "FFIE", "MULN", "WKHS", "NKLA", "HYLN"
        ]
    },

    "TRADITIONAL_AUTO": {
        "description": "Traditional automakers",
        "symbols": [
            "GM", "F", "STLA", "TM", "HMC", "RACE", "HYMTF", "MBGAF"
        ]
    },

    "CLEAN_ENERGY": {
        "description": "Clean energy & solar",
        "symbols": [
            "ENPH", "SEDG", "FSLR", "RUN", "NOVA", "ARRY", "SPWR",
            "CSIQ", "JKS", "DQ", "MAXN", "STEM", "PLUG", "FCEL",
            "BE", "BLDP", "CHPT", "EVGO", "BLNK", "CLNE", "GEVO"
        ]
    },

    "CHINA_ADR": {
        "description": "Chinese ADRs",
        "symbols": [
            "BABA", "JD", "PDD", "NIO", "XPEV", "LI", "BIDU", "TME",
            "BILI", "IQ", "TAL", "EDU", "VIPS", "FUTU", "BZUN", "ZH",
            "KC", "TUYA", "HUYA", "DOYU", "ATHM", "LX", "YMM"
        ]
    },

    "CRYPTO_BLOCKCHAIN": {
        "description": "Crypto & blockchain stocks",
        "symbols": [
            "COIN", "MARA", "RIOT", "HUT", "BTBT", "BITF", "CIFR",
            "HIVE", "CLSK", "CORZ", "IREN", "BTDR", "MSTR", "SMLR",
            "NCTY", "ARBK", "GREE", "WULF", "SOS", "CAN"
        ]
    },

    "AI_DATA": {
        "description": "AI & data analytics",
        "symbols": [
            "NVDA", "PLTR", "AI", "SNOW", "MDB", "DDOG", "PATH",
            "SOUN", "BBAI", "PRCT", "UPST", "BIGC", "ESTC", "SUMO"
        ]
    },

    "GAMING_ESPORTS": {
        "description": "Gaming & esports",
        "symbols": [
            "RBLX", "U", "EA", "TTWO", "DKNG", "PENN", "RSI", "GENI",
            "SKLZ", "PLTK", "SLGG", "EGLX", "AGAE", "GMBL"
        ]
    },

    "CANNABIS": {
        "description": "Cannabis stocks",
        "symbols": [
            "TLRY", "CGC", "ACB", "CRON", "OGI", "HEXO", "SNDL", "VFF",
            "GRWG", "IIPR", "GTBIF", "CURLF", "TCNNF", "CRLBF"
        ]
    },

    "MEME_RETAIL": {
        "description": "Retail favorite / meme stocks",
        "symbols": [
            "GME", "AMC", "BB", "BBBY", "EXPR", "KOSS", "CLOV", "WISH",
            "PLTR", "SOFI", "HOOD", "RIVN", "LCID"
        ]
    },

    "TELECOM": {
        "description": "Telecommunications",
        "symbols": [
            "T", "VZ", "TMUS", "LUMN", "FTR", "USM", "TDS", "SHEN",
            "CNSL", "GOGO", "ATUS", "CABO", "WOW", "BAND"
        ]
    },

    "MEDIA_ENTERTAINMENT": {
        "description": "Media & entertainment",
        "symbols": [
            "DIS", "NFLX", "WBD", "PARA", "LYV", "SPOT", "RBLX",
            "ROKU", "FUBO", "COUR", "DUOL", "MTCH", "IAC", "ANGI"
        ]
    },

    "HOMEBUILDERS": {
        "description": "Homebuilders",
        "symbols": [
            "DHI", "LEN", "NVR", "PHM", "TOL", "KBH", "MDC", "MHO",
            "TMHC", "MTH", "CCS", "GRBK", "SKY", "BZH", "MER"
        ]
    },

    "BUILDING_MATERIALS": {
        "description": "Building materials",
        "symbols": [
            "MLM", "VMC", "CX", "EXP", "SUM", "USLM", "ROCK", "IBP",
            "BLD", "BLDR", "BECN", "GMS", "TILE", "TREX", "AZEK"
        ]
    }
}

# Generate flat list of all symbols
def get_all_symbols():
    """Get all unique symbols from all categories"""
    all_symbols = set()
    for category_data in STOCK_CATEGORIES.values():
        all_symbols.update(category_data["symbols"])
    return sorted(list(all_symbols))

# Generate symbols by category
def get_symbols_by_category(category_name):
    """Get symbols for a specific category"""
    if category_name in STOCK_CATEGORIES:
        return STOCK_CATEGORIES[category_name]["symbols"]
    return []

# Get category for a symbol
def get_symbol_category(symbol):
    """Get category name for a symbol"""
    for cat_name, cat_data in STOCK_CATEGORIES.items():
        if symbol in cat_data["symbols"]:
            return cat_name
    return "UNCATEGORIZED"

# Default position sizes by category
CATEGORY_POSITION_SIZES = {
    "MEGA_CAP_TECH": 5,
    "SEMICONDUCTORS": 10,
    "SOFTWARE_CLOUD": 15,
    "CYBERSECURITY": 15,
    "FINTECH": 20,
    "BANKS_MAJOR": 20,
    "ASSET_MANAGERS": 15,
    "INSURANCE": 20,
    "HEALTHCARE_PHARMA": 10,
    "MEDICAL_DEVICES": 10,
    "BIOTECH": 25,
    "INDUSTRIALS_DIVERSIFIED": 15,
    "AEROSPACE_DEFENSE": 10,
    "TRANSPORTATION": 15,
    "AIRLINES": 30,
    "CONSUMER_RETAIL": 15,
    "AUTO_RETAIL": 20,
    "RESTAURANTS": 20,
    "FOOD_BEVERAGE": 25,
    "HOTELS_LEISURE": 20,
    "ENERGY_OIL_GAS": 20,
    "ENERGY_SERVICES": 30,
    "ENERGY_MIDSTREAM": 30,
    "REFINING": 25,
    "UTILITIES": 30,
    "REITS_DIVERSIFIED": 25,
    "MATERIALS_CHEMICALS": 20,
    "METALS_MINING": 30,
    "EV_AUTOMAKERS": 15,
    "TRADITIONAL_AUTO": 25,
    "CLEAN_ENERGY": 30,
    "CHINA_ADR": 50,
    "CRYPTO_BLOCKCHAIN": 50,
    "AI_DATA": 20,
    "GAMING_ESPORTS": 30,
    "CANNABIS": 100,
    "MEME_RETAIL": 50,
    "TELECOM": 40,
    "MEDIA_ENTERTAINMENT": 20,
    "HOMEBUILDERS": 20,
    "BUILDING_MATERIALS": 25
}

def get_position_size(symbol):
    """Get recommended position size for a symbol based on its category"""
    category = get_symbol_category(symbol)
    return CATEGORY_POSITION_SIZES.get(category, 20)

def generate_position_sizes_json(symbols):
    """Generate position sizes JSON for a list of symbols"""
    return {symbol: get_position_size(symbol) for symbol in symbols}


if __name__ == "__main__":
    all_symbols = get_all_symbols()
    print(f"Total unique symbols: {len(all_symbols)}")
    print(f"\nCategories ({len(STOCK_CATEGORIES)}):")
    for cat_name, cat_data in STOCK_CATEGORIES.items():
        print(f"  {cat_name}: {len(cat_data['symbols'])} stocks - {cat_data['description']}")
