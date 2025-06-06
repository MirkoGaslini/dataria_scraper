#!/usr/bin/env python3
"""
TikTok Scraper - Entry Point
Mantiene compatibilità con comando: python tiktok_scraper.py
"""

# Import dal modulo refactorizzato
from src.scrapers.tiktok_scraper import main_sync as main

if __name__ == "__main__":
    main()