"""
Selected 100 Momentum Stocks - Diversified across categories
Priority: High momentum sectors with broad diversification
"""

SELECTED_STOCKS = {
    # === HIGH MOMENTUM CATEGORIES (4-6 each) ===

    # MEGA_CAP_TECH (6) - Core holdings
    "MEGA_CAP_TECH": ["AAPL", "MSFT", "GOOGL", "META", "NVDA", "AMD"],

    # SEMICONDUCTORS (6) - Hot sector
    "SEMICONDUCTORS": ["AVGO", "QCOM", "TSM", "ASML", "MU", "ARM"],

    # AI_DATA (4) - Momentum leaders
    "AI_DATA": ["PLTR", "AI", "SNOW", "DDOG"],

    # SOFTWARE_CLOUD (4)
    "SOFTWARE_CLOUD": ["CRM", "NOW", "NET", "PANW"],

    # FINTECH (5)
    "FINTECH": ["V", "MA", "SQ", "COIN", "PYPL"],

    # EV_AUTOMAKERS (4)
    "EV_AUTOMAKERS": ["TSLA", "RIVN", "NIO", "LI"],

    # CRYPTO_BLOCKCHAIN (4)
    "CRYPTO_BLOCKCHAIN": ["MARA", "RIOT", "MSTR", "CLSK"],

    # === MEDIUM MOMENTUM (3 each) ===

    # CYBERSECURITY (3)
    "CYBERSECURITY": ["CRWD", "ZS", "FTNT"],

    # BIOTECH (3)
    "BIOTECH": ["MRNA", "CRSP", "ALNY"],

    # HEALTHCARE_PHARMA (3)
    "HEALTHCARE_PHARMA": ["LLY", "UNH", "ABBV"],

    # MEDICAL_DEVICES (3)
    "MEDICAL_DEVICES": ["ISRG", "DHR", "DXCM"],

    # CONSUMER_RETAIL (3)
    "CONSUMER_RETAIL": ["AMZN", "COST", "HD"],

    # RESTAURANTS (3)
    "RESTAURANTS": ["MCD", "CMG", "SBUX"],

    # HOTELS_LEISURE (3)
    "HOTELS_LEISURE": ["BKNG", "ABNB", "DKNG"],

    # MEDIA_ENTERTAINMENT (3)
    "MEDIA_ENTERTAINMENT": ["NFLX", "DIS", "SPOT"],

    # GAMING_ESPORTS (2)
    "GAMING_ESPORTS": ["RBLX", "EA"],

    # HOMEBUILDERS (2)
    "HOMEBUILDERS": ["DHI", "LEN"],

    # BANKS_MAJOR (3)
    "BANKS_MAJOR": ["JPM", "GS", "MS"],

    # ASSET_MANAGERS (2)
    "ASSET_MANAGERS": ["BLK", "KKR"],

    # INDUSTRIALS_DIVERSIFIED (3)
    "INDUSTRIALS_DIVERSIFIED": ["GE", "CAT", "HON"],

    # AEROSPACE_DEFENSE (3)
    "AEROSPACE_DEFENSE": ["RTX", "LMT", "BA"],

    # TRANSPORTATION (2)
    "TRANSPORTATION": ["UPS", "FDX"],

    # === DIVERSIFICATION (1-2 each) ===

    # INSURANCE (2)
    "INSURANCE": ["PGR", "TRV"],

    # UTILITIES (2) - Defensive + momentum (CEG = nuclear AI play)
    "UTILITIES": ["NEE", "CEG"],

    # REITS_DIVERSIFIED (2)
    "REITS_DIVERSIFIED": ["PLD", "AMT"],

    # MATERIALS_CHEMICALS (2)
    "MATERIALS_CHEMICALS": ["LIN", "SHW"],

    # METALS_MINING (2)
    "METALS_MINING": ["NEM", "FCX"],

    # ENERGY_OIL_GAS (2)
    "ENERGY_OIL_GAS": ["XOM", "CVX"],

    # ENERGY_MIDSTREAM (1)
    "ENERGY_MIDSTREAM": ["WMB"],

    # REFINING (1)
    "REFINING": ["PSX"],

    # TRADITIONAL_AUTO (2)
    "TRADITIONAL_AUTO": ["GM", "F"],

    # CLEAN_ENERGY (2)
    "CLEAN_ENERGY": ["ENPH", "FSLR"],

    # CHINA_ADR (2)
    "CHINA_ADR": ["BABA", "PDD"],

    # TELECOM (2)
    "TELECOM": ["TMUS", "VZ"],

    # FOOD_BEVERAGE (2)
    "FOOD_BEVERAGE": ["KO", "PEP"],

    # AUTO_RETAIL (1)
    "AUTO_RETAIL": ["ORLY"],

    # AIRLINES (2)
    "AIRLINES": ["DAL", "UAL"],

    # BUILDING_MATERIALS (1)
    "BUILDING_MATERIALS": ["BLDR"],
}

def get_all_selected():
    """Get flat list of all selected symbols"""
    all_symbols = []
    for symbols in SELECTED_STOCKS.values():
        all_symbols.extend(symbols)
    return all_symbols

def get_category_count():
    """Get count by category"""
    return {cat: len(syms) for cat, syms in SELECTED_STOCKS.items()}

if __name__ == "__main__":
    symbols = get_all_selected()
    print(f"Total: {len(symbols)} stocks across {len(SELECTED_STOCKS)} categories")
    print(f"\nSymbols: {','.join(symbols)}")
    print(f"\nBy category:")
    for cat, syms in SELECTED_STOCKS.items():
        print(f"  {cat}: {len(syms)} - {', '.join(syms)}")
