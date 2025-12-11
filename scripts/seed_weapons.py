#!/usr/bin/env python3
"""
Seeding script to populate the database with CODM weapons.
"""
import os
import sys
import asyncio
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from core.database.database_pg_proxy import DatabasePostgresProxy
from config.config import WEAPON_CATEGORIES

# Weapon data
WEAPONS = {
    "assault_rifle": [
        "AK117", "AK-47", "ASM10", "BK57", "CR-56 AMAX", "DR-H", "EM2", "FFAR 1",
        "FR .556", "Grau 5.56", "HBRa3", "HVK-30", "ICR-1", "Kilo 141", "KN-44",
        "Krig 6", "LK24", "M13", "M16", "M4", "Man-O-War", "Oden", "Peacekeeper MK2",
        "Type 25", "AS VAL", "Swordfish", "Maddox", "FFAR 1", "Groza", "Type 19",
        "BP50", "LAG 53"
    ],
    "smg": [
        "AGR 556", "CBR4", "Chicom", "Cordite", "Fennec", "GKS", "HG 40", "KSP 45",
        "LAPA", "MAC-10", "MSMC", "MX9", "OTs 9", "PDW-57", "Pharo", "PP19 Bizon",
        "PPSh-41", "QXR", "QQ9", "Razorback", "RUS-79U", "Switchblade X9", "Striker 45",
        "CX-9", "Tec-9", "ISO", "USS 9"
    ],
    "lmg": [
        "Chopper", "Hades", "Holger 26", "M4LMG", "RPD", "S36", "UL736", "Dingo",
        "Bruen MK9", "MG42"
    ],
    "sniper": [
        "Arctic .50", "DL Q33", "Koshka", "Locus", "M21 EBR", "NA-45", "Outlaw",
        "Rytec AMR", "SVD", "XPR-50", "ZRG 20mm", "HDR", "LW3-Tundra"
    ],
    "marksman": [
        "Kilo Bolt-Action", "MK2", "SKS", "SP-R 208"
    ],
    "shotgun": [
        "BY15", "Echo", "HS0405", "HS2126", "JAK-12", "KRM-262", "R9-0", "Shorty",
        "Striker", "Argus"
    ],
    "pistol": [
        ".50 GS", "J358", "L-CAR 9", "MW11", "Renetti", "Shorty", "Dobvra", "Nail Gun"
    ],
    "launcher": [
        "FHJ-18", "SMRS", "Thumper", "D13 Sector"
    ]
}

async def seed_weapons():
    print("🌱 Seeding weapons...")
    
    # Initialize DB
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("❌ DATABASE_URL not found in environment variables")
        return

    db = DatabasePostgresProxy(db_url)
    
    total_added = 0
    
    for category_key, weapon_list in WEAPONS.items():
        print(f"\nProcessing category: {category_key}...")
        
        # Ensure category exists (although setup_database.sql should have created them)
        # We rely on add_weapon to handle category lookup
        
        for weapon_name in weapon_list:
            success = db.add_weapon(category_key, weapon_name)
            if success:
                print(f"  ✅ Added: {weapon_name}")
                total_added += 1
            else:
                print(f"  ⚠️ Failed/Skipped: {weapon_name}")
                
    print(f"\n✨ Seeding complete! Added {total_added} weapons.")

if __name__ == "__main__":
    asyncio.run(seed_weapons())
