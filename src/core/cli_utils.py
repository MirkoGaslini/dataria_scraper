#!/usr/bin/env python3
"""
Core CLI Utils - Argparse patterns comuni + PAGINATION + MULTIPLE USERS + PARQUET + S3
Versione aggiornata con supporto pagination, multiple users, Parquet e S3
"""

import os
import argparse
import re
from urllib.parse import urlparse


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
        help='Directory output per file (default: data/)'
    )
    
    parser.add_argument(
        '--output-prefix',
        type=str,
        default='',
        help='Prefisso per nome file output'
    )
    
    # ✅ NUOVO: Formato file output
    parser.add_argument(
        '--output-format',
        type=str,
        choices=['jsonl', 'parquet'],
        default='jsonl',
        help='Formato file output: jsonl (human-readable) o parquet (analytics, più veloce) - default: jsonl'
    )
    
    # ✅ NUOVO: S3 Upload
    parser.add_argument(
        '--s3-uri',
        type=str,
        help='URI S3 per upload automatico (es: s3://mio-bucket/cartella/) - opzionale'
    )
    
    parser.add_argument(
        '--s3-auto-upload',
        action='store_true',
        help='Upload automatico su S3 dopo salvataggio locale (richiede --s3-uri)'
    )
    
    parser.add_argument(
        '--s3-only',
        action='store_true',
        help='Salva SOLO su S3, elimina file locale dopo upload (richiede --s3-uri)'
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


def add_pagination_arguments(parser):
    """✅ NUOVO: Aggiunge argomenti CLI per pagination commenti"""
    
    # Gruppo pagination
    pagination_group = parser.add_argument_group('📄 Pagination Commenti')
    
    pagination_group.add_argument(
        '--pagination-mode',
        type=str,
        choices=['auto', 'paginated', 'limited', 'adaptive'],
        default='limited',
        help='''Modalità recupero commenti:
• limited: Solo primi N commenti (veloce, default)
• adaptive: Tutti i commenti fino a --max-total-comments (bilanciata)
• paginated: TUTTI i commenti disponibili (lenta ma completa)
• auto: Decide automaticamente in base al video'''
    )
    
    pagination_group.add_argument(
        '--max-total-comments',
        type=int,
        default=1000,
        help='Limite massimo commenti totali per pagination (default: 1000)'
    )
    
    pagination_group.add_argument(
        '--batch-size',
        type=int,
        default=50,
        help='Commenti per batch in pagination (default: 50)'
    )
    
    pagination_group.add_argument(
        '--delay-between-batches',
        type=float,
        default=2.0,
        help='Secondi di pausa tra batch (anti rate-limit, default: 2.0)'
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
    
    # ✅ NUOVO: Validazione S3
    args = validate_s3_arguments(args, parser)
    
    # ✅ NUOVO: Validazione formato output
    args = validate_output_format_arguments(args, parser)
    
    return args


def validate_s3_arguments(args, parser):
    """
    ✅ NUOVO: Valida argomenti S3
    
    Args:
        args: Argomenti parsati
        parser: Parser per errori
    
    Returns:
        args: Argomenti validati
    """
    
    # Validazione S3 URI
    if args.s3_uri:
        try:
            parsed_uri = urlparse(args.s3_uri)
            
            # Deve essere formato s3://bucket/path/
            if parsed_uri.scheme != 's3':
                parser.error(f"❌ S3 URI deve iniziare con 's3://' (ricevuto: {args.s3_uri})")
            
            if not parsed_uri.netloc:
                parser.error(f"❌ S3 URI deve specificare un bucket (ricevuto: {args.s3_uri})")
            
            # Estrai bucket e path
            args.s3_bucket = parsed_uri.netloc
            args.s3_path = parsed_uri.path.lstrip('/') if parsed_uri.path else ''
            
            # Assicurati che il path termini con / se specificato
            if args.s3_path and not args.s3_path.endswith('/'):
                args.s3_path += '/'
                
            print(f"✅ S3 configurato: bucket={args.s3_bucket}, path={args.s3_path or '(root)'}")
            
        except Exception as e:
            parser.error(f"❌ Errore parsing S3 URI: {e}")
    else:
        args.s3_bucket = None
        args.s3_path = ''
    
    # Validazione dipendenze S3
    if args.s3_auto_upload and not args.s3_uri:
        parser.error("❌ --s3-auto-upload richiede --s3-uri")
    
    if args.s3_only and not args.s3_uri:
        parser.error("❌ --s3-only richiede --s3-uri")
    
    if args.s3_only and not args.s3_auto_upload:
        # s3-only implica auto-upload
        args.s3_auto_upload = True
    
    # Check credenziali AWS se S3 richiesto
    if args.s3_uri:
        aws_access_key = os.environ.get('AWS_ACCESS_KEY_ID')
        aws_secret_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
        aws_profile = os.environ.get('AWS_PROFILE')
        
        if not aws_access_key and not aws_profile:
            print("⚠️  ATTENZIONE: Credenziali AWS non trovate nelle variabili d'ambiente")
            print("💡 Configura una di queste opzioni:")
            print("   - AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY nel .env")
            print("   - AWS_PROFILE nel .env") 
            print("   - aws configure (AWS CLI)")
            print("   - IAM Role (se su EC2/Lambda)")
            
            if not args.auto:
                confirm = input("Continuare comunque? [y/N]: ").strip().lower()
                if confirm != 'y':
                    parser.error("Operazione annullata dall'utente")
    
    return args


def validate_output_format_arguments(args, parser):
    """
    ✅ NUOVO: Valida argomenti formato output
    
    Args:
        args: Argomenti parsati  
        parser: Parser per errori
        
    Returns:
        args: Argomenti validati
    """
    
    # Check dipendenze per Parquet
    if args.output_format == 'parquet':
        try:
            import pyarrow  # Test import
            print("✅ PyArrow disponibile per formato Parquet")
        except ImportError:
            parser.error("❌ Formato Parquet richiede PyArrow. Installa con: pip install pyarrow")
    
    print(f"📁 Formato output: {args.output_format.upper()}")
    
    return args


def validate_pagination_arguments(args, parser):
    """✅ NUOVO: Valida argomenti pagination specifici"""
    
    # Validazione max-total-comments
    if args.max_total_comments < 1 or args.max_total_comments > 50000:
        parser.error(f"❌ max-total-comments deve essere tra 1 e 50000 (ricevuto: {args.max_total_comments})")
    
    # Validazione batch-size
    if args.batch_size < 1 or args.batch_size > 500:
        parser.error(f"❌ batch-size deve essere tra 1 e 500 (ricevuto: {args.batch_size})")
    
    # Validazione delay-between-batches
    if args.delay_between_batches < 0 or args.delay_between_batches > 60:
        parser.error(f"❌ delay-between-batches deve essere tra 0 e 60 secondi (ricevuto: {args.delay_between_batches})")
    
    # Dependency check
    if args.pagination_mode != 'limited' and not args.add_comments:
        parser.error("❌ Modalità pagination richiede --add-comments")
    
    # Warning per modalità lente
    if args.pagination_mode == 'paginated' and not args.auto:
        print("⚠️  ATTENZIONE: Modalità PAGINATED può richiedere ore per video virali!")
        if not args.auto:
            confirm = input("Continuare? [y/N]: ").strip().lower()
            if confirm != 'y':
                parser.error("Operazione annullata dall'utente")
    
    elif args.pagination_mode == 'adaptive' and args.max_total_comments > 5000:
        print(f"⚠️  ATTENZIONE: max-total-comments={args.max_total_comments} è molto alto")
    
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


def load_users_from_file(users_file_path, parser):
    """
    ✅ NUOVO: Carica lista utenti da file
    
    Args:
        users_file_path (str): Percorso al file utenti
        parser: Parser per errori
    
    Returns:
        list: Lista username puliti
    """
    
    if not users_file_path:
        return []
    
    try:
        if not os.path.exists(users_file_path):
            parser.error(f"❌ File utenti non trovato: {users_file_path}")
        
        with open(users_file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        users = []
        for i, line in enumerate(lines, 1):
            line = line.strip()
            
            # Salta righe vuote e commenti
            if not line or line.startswith('#'):
                continue
            
            # Supporta formati:
            # username
            # @username  
            # https://www.tiktok.com/@username
            
            if line.startswith('https://'):
                # Estrai username da URL TikTok
                if 'tiktok.com/@' in line:
                    username = line.split('@')[-1].split('/')[0].split('?')[0]
                else:
                    parser.error(f"❌ URL non valido alla riga {i}: {line}")
            else:
                # Username diretto
                username = line.lstrip('@')
            
            # Pulisci e valida
            username = username.strip()
            if not username:
                continue
                
            # Valida formato username (lettere, numeri, underscore, punto)
            import re
            if not re.match(r'^[a-zA-Z0-9._-]+$', username):
                parser.error(f"❌ Username non valido alla riga {i}: {username}")
            
            users.append(username)
        
        if not users:
            parser.error(f"❌ Nessun username valido trovato in {users_file_path}")
        
        # Rimuovi duplicati mantenendo ordine
        unique_users = []
        seen = set()
        for user in users:
            if user not in seen:
                unique_users.append(user)
                seen.add(user)
        
        return unique_users
        
    except FileNotFoundError:
        parser.error(f"❌ File utenti non trovato: {users_file_path}")
    except UnicodeDecodeError:
        parser.error(f"❌ Errore encoding file {users_file_path} - usa UTF-8")
    except Exception as e:
        parser.error(f"❌ Errore lettura file utenti: {e}")


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
    print(f"   - Formato: {args.output_format.upper()}")  # ✅ NUOVO
    print(f"   - Log level: {args.log_level}")
    print(f"   - Auto mode: {'SÌ' if args.auto else 'NO'}")
    print(f"   - Filtri contenuto: {'DISATTIVATI' if args.no_filter else 'ATTIVI'}")
    
    # ✅ NUOVO: Info S3
    if args.s3_uri:
        print(f"   - S3 URI: {args.s3_uri}")
        print(f"   - S3 Upload: {'AUTO' if args.s3_auto_upload else 'MANUALE'}")
        print(f"   - S3 Only: {'SÌ' if args.s3_only else 'NO'}")
    else:
        print(f"   - S3: DISATTIVATO")
    
    # ✅ NUOVO: Info pagination
    if hasattr(args, 'pagination_mode'):
        print(f"   - Pagination mode: {args.pagination_mode}")
        if args.pagination_mode != 'limited':
            print(f"   - Max total comments: {args.max_total_comments}")
            print(f"   - Batch size: {args.batch_size}")
    
    if hasattr(args, 'min_text_length'):
        print(f"   - Min text length: {args.min_text_length}")
    
    # Info extra specifiche del scraper
    if extra_info:
        for key, value in extra_info.items():
            print(f"   - {key}: {value}")


# ============= WRAPPERS COMPATIBILITÀ =============

def setup_tiktok_argparse():
    """
    ✅ AGGIORNATO: Crea parser TikTok con argomenti comuni + specifici + PAGINATION + MULTIPLE USERS + PARQUET + S3
    
    Returns:
        ArgumentParser: Parser configurato per TikTok con tutte le features
    """
    
    parser = argparse.ArgumentParser(
        description='🎵 TikTok Scraper avanzato con PAGINATION, MULTIPLE USERS, PARQUET, S3, rilevanza, commenti e transcript',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Argomenti comuni (ora include Parquet + S3)
    add_common_arguments(parser)
    add_content_filter_arguments(parser, default_min_length=10)
    
    # ✅ NUOVO: Argomenti pagination
    add_pagination_arguments(parser)
    
    # ✅ AGGIORNATO: Modalità di ricerca TikTok (mutuamente esclusive + multiple users)
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
        '--users-file',
        type=str,
        help='File con lista utenti TikTok (uno per riga, supporta URL)'
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
        help='Numero massimo commenti per video in modalità limited (default: 10)'
    )
    
    parser.add_argument(
        '--include-replies',
        action='store_true',
        help='Includi risposte ai commenti (nested structure)'
    )
    
    parser.add_argument(
        '--max-replies',
        type=int,
        default=3,
        help='Numero massimo risposte per commento (default: 3)'
    )
    
    # ✅ NUOVO: Parametri specifici per multiple users
    parser.add_argument(
        '--count-per-user',
        type=int,
        help='Video per utente quando usi --users-file (default: usa --count)'
    )
    
    parser.add_argument(
        '--parallel-users',
        action='store_true',
        help='Elabora utenti in parallelo (più veloce ma più carico API)'
    )
    
    parser.add_argument(
        '--stop-on-error',
        action='store_true',
        help='Ferma tutto se un utente fallisce (default: continua con gli altri)'
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
    ✅ AGGIORNATO: Validazioni specifiche TikTok + PAGINATION + MULTIPLE USERS + PARQUET + S3
    
    Args:
        args: Argomenti parsati
        parser: Parser per errori
    """
    
    # ✅ AGGIORNATO: Validazione modalità auto (ora include users-file)
    if args.auto and not (args.hashtag or args.user or args.users_file or args.trending):
        parser.error("❌ Modalità --auto richiede --hashtag, --user, --users-file o --trending!")
    
    # ✅ NUOVO: Carica e valida utenti da file
    args.users_list = []
    if args.users_file:
        args.users_list = load_users_from_file(args.users_file, parser)
        
        # Log numero utenti caricati
        print(f"📋 Caricati {len(args.users_list)} utenti da {args.users_file}")
        
        # Validazione count-per-user
        if args.count_per_user:
            if args.count_per_user < 1 or args.count_per_user > 50:
                parser.error(f"❌ count-per-user deve essere tra 1 e 50 (ricevuto: {args.count_per_user})")
        else:
            # Usa count normale se count-per-user non specificato
            args.count_per_user = args.count
            
        # Warning per troppe richieste
        total_requests = len(args.users_list) * args.count_per_user
        if total_requests > 200 and not args.auto:
            print(f"⚠️  ATTENZIONE: {len(args.users_list)} utenti × {args.count_per_user} video = {total_requests} video totali")
            print("⚠️  Questo può richiedere molto tempo e molte richieste API")
            if not args.auto:
                confirm = input("Continuare? [y/N]: ").strip().lower()
                if confirm != 'y':
                    parser.error("Operazione annullata dall'utente")
    
    # Validazione max-comments
    if args.max_comments < 1 or args.max_comments > 50:
        parser.error(f"❌ max-comments deve essere tra 1 e 50 (ricevuto: {args.max_comments})")
    
    # Validazione max-replies
    if args.max_replies < 1 or args.max_replies > 20:
        parser.error(f"❌ max-replies deve essere tra 1 e 20 (ricevuto: {args.max_replies})")
    
    # Validazione include-replies dependency
    if args.include_replies and not args.add_comments:
        parser.error("❌ --include-replies richiede --add-comments")
    
    # Validazione relevance-threshold
    if args.relevance_threshold < 0.0 or args.relevance_threshold > 1.0:
        parser.error(f"❌ relevance-threshold deve essere tra 0.0 e 1.0 (ricevuto: {args.relevance_threshold})")
    
    # Validazione durata
    if args.min_duration and args.max_duration:
        if args.min_duration >= args.max_duration:
            parser.error("❌ min-duration deve essere < max-duration")
    
    # Validazione created-after
    if getattr(args, 'created_after', None):
        try:
            from datetime import datetime
            datetime.strptime(args.created_after, '%Y-%m-%d')
        except ValueError:
            parser.error("❌ created-after deve essere in formato YYYY-MM-DD (es: 2025-06-01)")
    
    # ✅ NUOVO: Validazione pagination
    args = validate_pagination_arguments(args, parser)
    
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
    
    # Argomenti comuni (ora include Parquet + S3)
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