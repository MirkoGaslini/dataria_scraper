#!/usr/bin/env python3
"""
Core Text Utils - Elaborazione testo comune
Elimina duplicazione tra TikTok e Twitter scrapers per pulizia e analisi testo
"""

import re


def extract_hashtags(text):
    """
    Estrae hashtag da qualsiasi testo
    
    Args:
        text (str): Testo da analizzare
    
    Returns:
        list: Lista hashtag (senza #)
    """
    try:
        if not text:
            return []
        hashtags = re.findall(r'#(\w+)', text)
        return hashtags
    except Exception:
        return []


def clean_text_base(text, remove_links=True, remove_consecutive_patterns=False, 
                   platform="generic", logger=None):
    """
    Pulizia testo base comune
    
    Args:
        text (str): Testo da pulire
        remove_links (bool): Rimuove link HTTP/HTTPS
        remove_consecutive_patterns (bool): Rimuove pattern consecutivi (TikTok style)
        platform (str): Platform per regole specifiche ('tiktok', 'twitter')
        logger: Logger per warning
    
    Returns:
        str: Testo pulito
    """
    try:
        if not text:
            return ""
        
        cleaned = text
        
        # Rimuove link
        if remove_links:
            if platform == "twitter":
                # Twitter usa t.co per link shortened
                cleaned = re.sub(r'https://t\.co/\w+', '', cleaned)
            else:
                # Link generici HTTP/HTTPS
                cleaned = re.sub(r'https?://[^\s]+', '', cleaned)
        
        # Rimuove pattern consecutivi (logica TikTok)
        if remove_consecutive_patterns:
            # Rimuove hashtag multipli consecutivi
            cleaned = re.sub(r'(#\w+\s*){3,}', '', cleaned)
            # Rimuove menzioni multiple consecutive
            cleaned = re.sub(r'(@\w+\s*){3,}', '', cleaned)
        
        # Normalizza spazi multipli
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        return cleaned
        
    except Exception as e:
        if logger:
            logger.warning(f"⚠️  Errore pulizia testo: {e}")
        return text


def is_meaningful_content(text, search_term=None, min_length=10, platform="generic", logger=None):
    """
    Determina se il contenuto testuale è "significativo"
    
    Args:
        text (str): Testo da valutare  
        search_term (str): Termine di ricerca da escludere dal conteggio
        min_length (int): Lunghezza minima richiesta
        platform (str): Platform per logiche specifiche
        logger: Logger per warning
    
    Returns:
        bool: True se contenuto significativo
    """
    try:
        if not text:
            return False
        
        # Rimuovi il termine di ricerca per contare il resto del contenuto
        content_to_check = text
        if search_term:
            # Case insensitive replacement
            content_to_check = content_to_check.replace(search_term, "")
            content_to_check = content_to_check.replace(search_term.lower(), "")
            
            # Per Twitter rimuovi anche hashtag version
            if platform == "twitter":
                content_to_check = content_to_check.replace(f"#{search_term}", "")
                content_to_check = content_to_check.replace(f"#{search_term.lower()}", "")
        
        content_to_check = content_to_check.strip()
        
        # Check lunghezza minima
        if len(content_to_check) < min_length:
            return False
        
        # Check se è solo simboli/emoji/hashtag/menzioni
        if re.match(r'^[#@\s\W]*$', content_to_check):
            return False
        
        return True
        
    except Exception as e:
        if logger:
            logger.warning(f"⚠️  Errore valutazione contenuto: {e}")
        return True  # In caso di errore, mantieni il contenuto


# ============= WRAPPERS COMPATIBILITÀ =============

def extract_hashtags_from_desc(description):
    """TikTok wrapper - mantiene compatibilità esatta"""
    return extract_hashtags(description)


def clean_description(desc, logger=None):
    """TikTok wrapper - mantiene compatibilità esatta""" 
    return clean_text_base(
        text=desc, 
        remove_links=False,  # TikTok non rimuove link nella clean_description originale
        remove_consecutive_patterns=True,  # TikTok rimuove pattern consecutivi
        platform="tiktok",
        logger=logger
    )


def clean_tweet_text(text, logger=None):
    """Twitter wrapper - mantiene compatibilità esatta"""
    return clean_text_base(
        text=text,
        remove_links=True,  # Twitter rimuove t.co links
        remove_consecutive_patterns=False,  # Twitter non ha questa logica
        platform="twitter", 
        logger=logger
    )


def is_meaningful_description(clean_desc, search_term, min_length, logger=None):
    """TikTok wrapper - mantiene compatibilità esatta"""
    return is_meaningful_content(
        text=clean_desc,
        search_term=search_term,
        min_length=min_length,
        platform="tiktok",
        logger=logger
    )


def is_meaningful_text(clean_text, hashtag, min_length, logger=None):
    """Twitter wrapper - mantiene compatibilità esatta"""
    return is_meaningful_content(
        text=clean_text,
        search_term=hashtag,
        min_length=min_length,
        platform="twitter",
        logger=logger
    )