#!/usr/bin/env python3
"""
Core CLI Utils - Argparse patterns comuni
Elimina duplicazione tra TikTok e Twitter scrapers per gestione CLI
"""

import os
import argparse


def add_common_arguments(parser):
    """
    Aggiunge argomenti comuni a tutti i scrapers
    
    Args:
        parser: ArgumentParser da configurare
    """
    
    # Parametri quantità e output
    parser.add_argument(
        '--count', '-n',
        type=int,
        default=20,
        help='Numero items da raccogliere (default: 20)'
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        default='data',
        help='Directory output per file JSON (default: data/)'
    )
    
    parser.add_argument(
        '--output-prefix',
        type=str,
        default='',
        help='Prefisso per nome file output'
    )
    
    # Logging e modalità
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Livello di logging (default: INFO)'
    )
    
    parser.add_argument(
        '-q', '--quiet',
        action='store_true',
        help='Modalità silenziosa: mostra solo errori'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Modalità verbosa: mostra dettagli (equivale a --log-level DEBUG)'
    )
    
    parser.add_argument(
        '--auto',
        action='store_true',
        help='Modalità automatica: non chiede input utente'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Test configurazione senza eseguire ricerca vera'
    )


def add_content_filter_arguments(parser, default_min_length=10):
    """
    Aggiunge argomenti per filtri contenuto comuni
    
    Args:
        parser: ArgumentParser da configurare
        default_min_length: Lunghezza minima testo default
    """
    
    parser.add_argument(
        '--no-filter',
        action='store_true',
        help='Disabilita filtro contenuto significativo'
    )
    
    parser.add_argument(
        '--min-text-length',
        type=int,
        default=default_min_length,
        help=f'Lunghezza minima testo significativo (default: {default_min_length})'
    )


def validate_common_arguments(args, parser):
    """
    Valida argomenti comuni e applica correzioni
    
    Args:
        args: Argomenti parsati
        parser: Parser per errori
    
    Returns:
        args: Argomenti validati e corretti
    """
    
    # Gestione conflitti verbosity
    if args.quiet and args.verbose:
        parser.error("❌ Non puoi usare --quiet e --verbose insieme!")
    
    if args.verbose:
        args.log_level = 'DEBUG'
    elif args.quiet:
        args.log_level = 'ERROR'
    
    # Validazione directory output
    try:
        os.makedirs(args.output_dir, exist_ok=True)
    except Exception as e:
        parser.error(f"❌ Impossibile creare directory {args.output_dir}: {e}")
    
    return args


def validate_count_argument(args, parser, min_count=5, max_count=100):
    """
    Valida argomento count con range personalizzabile
    
    Args:
        args: Argomenti parsati
        parser: Parser per errori
        min_count: Count minimo
        max_count: Count massimo
    """
    
    if args.count < min_count or args.count > max_count:
        parser.error(f"❌ Count deve essere tra {min_count} e {max_count} (ricevuto: {args.count})")


def clean_hashtag_input(hashtag_input, parser):
    """
    Pulisce input hashtag (rimuove # e valida)
    
    Args:
        hashtag_input (str): Input hashtag grezzo
        parser: Parser per errori
    
    Returns:
        str: Hashtag pulito
    """
    
    if not hashtag_input:
        return hashtag_input
    
    # Rimuovi # iniziale e spazi
    cleaned = hashtag_input.lstrip('#').strip()
    
    if not cleaned:
        parser.error("❌ Hashtag non può essere vuoto!")
    
    return cleaned


def clean_username_input(username_input, parser):
    """
    Pulisce input username (rimuove @ e valida)
    
    Args:
        username_input (str): Input username grezzo  
        parser: Parser per errori
    
    Returns:
        str: Username pulito
    """
    
    if not username_input:
        return username_input
    
    # Rimuovi @ iniziale e spazi
    cleaned = username_input.lstrip('@').strip()
    
    if not cleaned:
        parser.error("❌ Username non può essere vuoto!")
    
    return cleaned


def check_auto_mode_requirements(args, parser, required_fields):
    """
    Verifica che modalità auto abbia tutti i campi richiesti
    
    Args:
        args: Argomenti parsati
        parser: Parser per errori
        required_fields (list): Lista campi richiesti per auto mode
    """
    
    if not args.auto:
        return
    
    missing_fields = []
    for field in required_fields:
        if not getattr(args, field, None):
            missing_fields.append(f"--{field.replace('_', '-')}")
    
    if missing_fields:
        parser.error(f"❌ Modalità --auto richiede: {', '.join(missing_fields)}")


def print_configuration_summary(args, extra_info=None):
    """
    Stampa riassunto configurazione per dry-run o debug
    
    Args:
        args: Argomenti configurati
        extra_info (dict): Info aggiuntive specifiche del scraper
    """
    
    print("🧪 CONFIGURAZIONE:")
    print(f"   - Count: {args.count}")
    print(f"   - Output: {args.output_dir}/{args.output_prefix}...")
    print(f"   - Log level: {args.log_level}")
    print(f"   - Auto mode: {'SÌ' if args.auto else 'NO'}")
    print(f"   - Filtri contenuto: {'DISATTIVATI' if args.no_filter else 'ATTIVI'}")
    
    if hasattr(args, 'min_text_length'):
        print(f"   - Min text length: {args.min_text_length}")
    
    # Info extra specifiche del scraper
    if extra_info:
        for key, value in extra_info.items():
            print(f"   - {key}: {value}")


# ============= WRAPPERS COMPATIBILITÀ =============

def setup_tiktok_argparse():
    """
    Crea parser TikTok con argomenti comuni + specifici
    
    Returns:
        ArgumentParser: Parser configurato per TikTok
    """
    
    parser = argparse.ArgumentParser(
        description='TikTok Scraper avanzato con rilevanza, commenti e transcript',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Argomenti comuni
    add_common_arguments(parser)
    add_content_filter_arguments(parser, default_min_length=10)
    
    # Modalità di ricerca TikTok (mutuamente esclusive)
    search_group = parser.add_mutually_exclusive_group(required=False)
    
    search_group.add_argument(
        '--hashtag',
        type=str,
        help='Hashtag da cercare (senza #)'
    )
    
    search_group.add_argument(
        '--user', '-u',
        type=str,
        help='Username TikTok da cui prendere video'
    )
    
    search_group.add_argument(
        '--trending',
        action='store_true',
        help='Scarica video trending di TikTok'
    )
    
    # Parametri specifici TikTok
    parser.add_argument(
        '--relevance-threshold',
        type=float,
        default=0.45,
        help='Soglia rilevanza video (0.0-1.0, default: 0.45)'
    )
    
    parser.add_argument(
        '--add-transcript',
        action='store_true',
        help='Aggiungi transcript audio dei video'
    )
    
    parser.add_argument(
        '--transcript-language',
        type=str,
        default='auto',
        help='Lingua per transcript (auto, en, it, es, fr, de, etc.) - default: auto'
    )
    
    parser.add_argument(
        '--add-comments',
        action='store_true',
        help='Aggiungi commenti dei video'
    )
    
    parser.add_argument(
        '--max-comments',
        type=int,
        default=10,
        help='Numero massimo commenti per video (default: 10)'
    )
    
    # Filtri video TikTok
    parser.add_argument(
        '--min-duration',
        type=int,
        help='Durata minima video in secondi (opzionale)'
    )
    
    parser.add_argument(
        '--max-duration',
        type=int,
        help='Durata massima video in secondi (opzionale)'
    )
    
    parser.add_argument(
        '--min-views',
        type=int,
        help='Numero minimo di visualizzazioni (opzionale)'
    )
    
    parser.add_argument(
        '--created-after',
        type=str,
        help='Filtra video creati dopo questa data (formato: YYYY-MM-DD)'
    )
    
    parser.add_argument(
        '--min-desc-length',
        type=int,
        default=10,
        help='Lunghezza minima descrizione significativa (default: 10 caratteri)'
    )
    
    # Configurazione TikTok API
    parser.add_argument(
        '--ms-token',
        type=str,
        help='MS Token da cookie TikTok (se non in .env)'
    )
    
    parser.add_argument(
        '--browser',
        type=str,
        default='chromium',
        choices=['chromium', 'firefox', 'webkit'],
        help='Browser per Playwright (default: chromium)'
    )
    
    parser.add_argument(
        '--use-proxy',
        action='store_true',
        help='Abilita uso proxy (configura in .env: PROXY_URL)'
    )
    
    return parser
    
def validate_tiktok_arguments(args, parser):
    """
    Validazioni specifiche TikTok
    
    Args:
        args: Argomenti parsati
        parser: Parser per errori
    """
    
    # Validazione modalità auto
    if args.auto and not (args.hashtag or args.user or args.trending):
        parser.error("❌ Modalità --auto richiede --hashtag, --user o --trending!")
    
    # Validazione max-comments
    if args.max_comments < 1 or args.max_comments > 50:
        parser.error(f"❌ max-comments deve essere tra 1 e 50 (ricevuto: {args.max_comments})")
    
    # Validazione relevance-threshold
    if args.relevance_threshold < 0.0 or args.relevance_threshold > 1.0:
        parser.error(f"❌ relevance-threshold deve essere tra 0.0 e 1.0 (ricevuto: {args.relevance_threshold})")
    
    # Validazione durata
    if args.min_duration and args.max_duration:
        if args.min_duration >= args.max_duration:
            parser.error("❌ min-duration deve essere < max-duration")
    
    # ✅ NUOVO: Validazione created-after
    if getattr(args, 'created_after', None):
        try:
            from datetime import datetime
            datetime.strptime(args.created_after, '%Y-%m-%d')
        except ValueError:
            parser.error("❌ created-after deve essere in formato YYYY-MM-DD (es: 2025-06-01)")
    
    # Pulizia input
    if args.hashtag:
        args.hashtag = clean_hashtag_input(args.hashtag, parser)
    
    if args.user:
        args.user = clean_username_input(args.user, parser)
    
    return args


def setup_twitter_argparse():
    """
    Crea parser Twitter con argomenti comuni + specifici
    
    Returns:
        ArgumentParser: Parser configurato per Twitter
    """
    
    parser = argparse.ArgumentParser(
        description='Twitter Scraper avanzato con filtri lingua, date e automazione',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Argomenti comuni
    add_common_arguments(parser)
    add_content_filter_arguments(parser, default_min_length=10)
    
    # Parametri specifici Twitter
    parser.add_argument(
        '--hashtag',  # RIMOSSO -h che confligge con --help
        type=str,
        help='Hashtag da cercare (senza #)'
    )
    
    parser.add_argument(
        '--lang', '-l',
        type=str,
        default='it',
        choices=['it', 'en', 'es', 'fr', 'de', 'pt', 'ja', 'ko', 'ar'],
        help='Lingua tweet (default: it)'
    )
    
    parser.add_argument(
        '--start-date',
        type=str,
        help='Data inizio ricerca (formato: YYYY-MM-DD)'
    )
    
    parser.add_argument(
        '--end-date', 
        type=str,
        help='Data fine ricerca (formato: YYYY-MM-DD)'
    )
    
    parser.add_argument(
        '--last-days',
        type=int,
        help='Cerca negli ultimi N giorni (max 7 per Piano Free)'
    )
    
    return parser