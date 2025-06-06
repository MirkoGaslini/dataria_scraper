#!/usr/bin/env python3
"""
Core Logger - Logging comune per tutti i scrapers
Elimina duplicazione tra TikTok e Twitter scrapers
"""

import os
import logging
from datetime import datetime


def setup_logger(logger_name="Scraper", log_file_prefix="scraper", log_level="INFO"):
    """
    Configura il logger professionale parametrizzato
    
    Args:
        logger_name (str): Nome del logger (es: 'TikTokScraper', 'TwitterScraper')
        log_file_prefix (str): Prefisso file log (es: 'tiktok_scraper', 'scraper') 
        log_level (str): Livello logging ('DEBUG', 'INFO', 'WARNING', 'ERROR')
    
    Returns:
        logging.Logger: Logger configurato
    """
    # Crea directory logs se non esiste
    os.makedirs('logs', exist_ok=True)
    
    # Configura formato
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Logger principale
    logger = logging.getLogger(logger_name)
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Rimuovi handler esistenti per evitare duplicati
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Handler console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Handler file
    log_filename = f"logs/{log_file_prefix}_{datetime.now().strftime('%Y%m%d')}.log"
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger


def setup_tiktok_logger(log_level="INFO"):
    """Wrapper per TikTok scraper - mantiene compatibilità"""
    return setup_logger(
        logger_name="TikTokScraper",
        log_file_prefix="tiktok_scraper", 
        log_level=log_level
    )


def setup_twitter_logger(log_level="INFO"):
    """Wrapper per Twitter scraper - mantiene compatibilità"""
    return setup_logger(
        logger_name="TwitterScraper",
        log_file_prefix="scraper",  # Twitter usa 'scraper_' come prefisso
        log_level=log_level
    )