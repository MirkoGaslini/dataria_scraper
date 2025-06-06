#!/usr/bin/env python3
"""
Core Date Utils - Gestione date comune
Estrae logica complessa date dal Twitter scraper per riutilizzo
"""

from datetime import datetime, timedelta


def validate_dates(start_date_str, end_date_str=None, logger=None, max_days_back=7):
    """
    Valida e converte le date in formato ISO per API
    
    Args:
        start_date_str (str): Data inizio (YYYY-MM-DD)
        end_date_str (str): Data fine (YYYY-MM-DD), opzionale
        logger: Logger per warning
        max_days_back (int): Giorni massimi indietro per warning
    
    Returns:
        tuple: (start_iso, end_iso) o (None, None) se errore
    """
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        
        # Se end_date non specificata, usa oggi
        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        else:
            end_date = datetime.now()
            if logger:
                logger.info(f"📅 End date non specificata, uso oggi: {end_date.strftime('%Y-%m-%d')}")
        
        if start_date >= end_date:
            raise ValueError("Data inizio deve essere precedente a data fine")
        
        # Controllo Piano Free (warning se troppo indietro)
        today = datetime.now()
        days_back = (today - start_date).days
        
        if days_back > max_days_back and logger:
            logger.warning(f"⚠️  Data inizio {days_back} giorni fa")
            logger.warning(f"⚠️  Piano Free limitato a ~{max_days_back} giorni - possibili errori API")
            logger.info("💡 Suggerimento: usa date più recenti o Piano Basic")
        
        # Converte in formato ISO per API
        start_iso = start_date.strftime('%Y-%m-%dT00:00:00Z')
        end_iso = end_date.strftime('%Y-%m-%dT23:59:59Z')
        
        if logger:
            logger.info(f"📅 Filtro date validato: {start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}")
        
        return start_iso, end_iso
        
    except ValueError as e:
        if logger:
            logger.error(f"❌ Errore formato date: {e}")
            logger.info("💡 Formato richiesto: YYYY-MM-DD (es: 2025-06-01)")
        return None, None


def process_last_days_filter(last_days, logger=None):
    """
    Converte --last-days in start_time/end_time
    
    Args:
        last_days (int): Numero giorni indietro
        logger: Logger per info
    
    Returns:
        tuple: (start_iso, end_iso) o (None, None) se errore
    """
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=last_days)
        
        start_iso = start_date.strftime('%Y-%m-%dT00:00:00Z')
        end_iso = end_date.strftime('%Y-%m-%dT23:59:59Z')
        
        if logger:
            logger.info(f"📅 Filtro ultimi {last_days} giorni: {start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}")
        
        return start_iso, end_iso
        
    except Exception as e:
        if logger:
            logger.error(f"❌ Errore calcolo date: {e}")
        return None, None


def validate_date_arguments(args, parser, logger=None):
    """
    Valida e processa argomenti date da argparse
    
    Args:
        args: Argomenti parsati (con start_date, end_date, last_days)
        parser: Parser per errori
        logger: Logger per info
    
    Returns:
        tuple: (start_iso, end_iso) o (None, None) se nessun filtro date
    """
    
    # Validazione date conflittuali
    if getattr(args, 'last_days', None) and (getattr(args, 'start_date', None) or getattr(args, 'end_date', None)):
        parser.error("❌ Non usare --last-days insieme a --start-date/--end-date!")
    
    # Validazione last_days range
    if getattr(args, 'last_days', None):
        if args.last_days < 1 or args.last_days > 7:
            parser.error("❌ --last-days deve essere tra 1 e 7 (Piano Free)")
    
    # Processa filtri temporali
    start_time, end_time = None, None
    
    if getattr(args, 'last_days', None):
        start_time, end_time = process_last_days_filter(args.last_days, logger)
        if not start_time:
            parser.error("❌ Errore calcolo date da --last-days")
            
    elif getattr(args, 'start_date', None):
        start_time, end_time = validate_dates(
            args.start_date, 
            getattr(args, 'end_date', None), 
            logger
        )
        if not start_time:
            parser.error("❌ Date non valide")
    
    return start_time, end_time


def format_date_for_display(iso_date_string):
    """
    Converte data ISO in formato leggibile per display
    
    Args:
        iso_date_string (str): Data in formato ISO
    
    Returns:
        str: Data formattata (YYYY-MM-DD)
    """
    try:
        if not iso_date_string:
            return "N/A"
        
        # Parse ISO format
        dt = datetime.fromisoformat(iso_date_string.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d')
        
    except Exception:
        return iso_date_string


def get_relative_date_description(start_iso, end_iso):
    """
    Genera descrizione relativa del range date
    
    Args:
        start_iso (str): Data inizio ISO
        end_iso (str): Data fine ISO
    
    Returns:
        str: Descrizione relativa (es: "ultimi 3 giorni", "dal 2025-06-01")
    """
    try:
        if not start_iso or not end_iso:
            return "ultimi 7 giorni (default API)"
        
        start_dt = datetime.fromisoformat(start_iso.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end_iso.replace('Z', '+00:00'))
        
        # Calcola differenza in giorni
        days_diff = (end_dt - start_dt).days
        
        # Se end è oggi, descrivi come "ultimi X giorni"
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        if end_dt.date() == today.date():
            return f"ultimi {days_diff} giorni"
        else:
            return f"dal {start_dt.strftime('%Y-%m-%d')} al {end_dt.strftime('%Y-%m-%d')}"
            
    except Exception:
        return "range personalizzato"


def is_recent_date_range(start_iso, end_iso, days_threshold=7):
    """
    Verifica se il range date è "recente" (entro soglia)
    
    Args:
        start_iso (str): Data inizio ISO
        end_iso (str): Data fine ISO  
        days_threshold (int): Soglia giorni per considerare "recente"
    
    Returns:
        bool: True se range è recente
    """
    try:
        if not start_iso:
            return True  # Nessun filtro = recente
        
        start_dt = datetime.fromisoformat(start_iso.replace('Z', '+00:00'))
        today = datetime.now()
        
        days_back = (today - start_dt).days
        return days_back <= days_threshold
        
    except Exception:
        return True  # Default safe


# ============= TWITTER COMPATIBILITY WRAPPER =============

def twitter_validate_dates(start_date_str, end_date_str, logger):
    """Wrapper esatto per compatibilità Twitter scraper"""
    return validate_dates(start_date_str, end_date_str, logger, max_days_back=7)


def twitter_process_last_days_filter(last_days, logger):
    """Wrapper esatto per compatibilità Twitter scraper"""
    return process_last_days_filter(last_days, logger)