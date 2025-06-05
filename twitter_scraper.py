#!/usr/bin/env python3
"""
Script per raccogliere tweet per hashtag usando Twitter API v2
STEP 3+: Versione migliorata con date + opzioni avanzate
"""

import os
import json
import re
import logging
import argparse
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Carica le variabili d'ambiente dal file .env
load_dotenv()

# Controlla se pytwitter è installato
try:
    import pytwitter
except ImportError:
    print("❌ ERRORE: python-twitter-v2 non è installato!")
    print("Esegui: pip install python-twitter-v2 python-dotenv")
    exit(1)

def setup_logger(log_level="INFO"):
    """Configura il logger professionale"""
    # Crea directory logs se non esiste
    os.makedirs('logs', exist_ok=True)
    
    # Configura formato
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Logger principale
    logger = logging.getLogger('TwitterScraper')
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Rimuovi handler esistenti per evitare duplicati
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Handler console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Handler file
    log_filename = f"logs/scraper_{datetime.now().strftime('%Y%m%d')}.log"
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger

def parse_arguments():
    """Configura argparse - Versione ibrida migliorata"""
    parser = argparse.ArgumentParser(
        description='Twitter Scraper avanzato con filtri lingua, date e automazione completa',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Esempi di utilizzo:
  # Comando base
  %(prog)s --hashtag AI --count 20

  # Con filtri date (max 7 giorni fa per Piano Free)
  %(prog)s --hashtag AI --count 20 --start-date 2025-06-01 --end-date 2025-06-04

  # Modalità automatica completa
  %(prog)s --hashtag startup --count 30 --lang it --auto --quiet

  # Debug con tutti i dettagli
  %(prog)s --hashtag blockchain --count 10 --verbose

  # Senza filtri qualità
  %(prog)s --hashtag news --count 50 --no-filter --output-prefix "raw_"

  # Test configurazione
  %(prog)s --hashtag test --dry-run
        """
    )
    
    # Parametri principali
    parser.add_argument(
        '--hashtag', '-h',
        type=str,
        help='Hashtag da cercare (senza #). Se non specificato, chiede input (tranne con --auto).'
    )
    
    parser.add_argument(
        '--count', '-n',
        type=int,
        default=20,
        help='Numero tweet da raccogliere (default: 20, min: 10, max: 500)'
    )
    
    # ✅ MIGLIORAMENTO: Filtri temporali con validazione migliorata
    parser.add_argument(
        '--start-date',
        type=str,
        help='Data inizio ricerca (OPZIONALE, formato: YYYY-MM-DD). Piano Free: max 7 giorni fa'
    )
    
    parser.add_argument(
        '--end-date', 
        type=str,
        help='Data fine ricerca (OPZIONALE, formato: YYYY-MM-DD). Default: oggi'
    )
    
    parser.add_argument(
        '--last-days',
        type=int,
        help='Alternativa alle date: cerca negli ultimi N giorni (max 7 per Piano Free)'
    )
    
    # Configurazione lingua e filtri
    parser.add_argument(
        '--lang', '-l',
        type=str,
        default='it',
        choices=['it', 'en', 'es', 'fr', 'de', 'pt', 'ja', 'ko', 'ar'],
        help='Lingua tweet (default: it per italiano)'
    )
    
    # ✅ MIGLIORAMENTO: Controllo filtri più granulare
    parser.add_argument(
        '--no-filter',
        action='store_true',
        help='Disabilita filtro contenuto significativo (mantiene tutti i tweet)'
    )
    
    parser.add_argument(
        '--min-text-length',
        type=int,
        default=10,
        help='Lunghezza minima testo significativo (default: 10 caratteri)'
    )
    
    # Output e logging
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
        help='Prefisso per nome file. Es: "daily_" → daily_hashtag_timestamp.json'
    )
    
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Livello di logging (default: INFO)'
    )
    
    # ✅ MIGLIORAMENTO: Modalità verbose/quiet come nella mia versione
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
    
    # Modalità speciali
    parser.add_argument(
        '--auto',
        action='store_true',
        help='Modalità automatica: non chiede input utente (richiede --hashtag)'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Test configurazione senza eseguire ricerca vera'
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version='TwitterScraper Step 3+ - Versione ibrida avanzata'
    )
    
    args = parser.parse_args()
    
    # ✅ MIGLIORAMENTO: Validazione e correzioni più robuste
    
    # Gestione conflitti verbosity
    if args.quiet and args.verbose:
        parser.error("❌ Non puoi usare --quiet e --verbose insieme!")
    
    if args.verbose:
        args.log_level = 'DEBUG'
    elif args.quiet:
        args.log_level = 'ERROR'
    
    # Validazione hashtag in modalità auto
    if args.auto and not args.hashtag:
        parser.error("❌ Modalità --auto richiede --hashtag specificato!")
    
    # Pulizia hashtag
    if args.hashtag:
        args.hashtag = args.hashtag.lstrip('#').strip()
        if not args.hashtag:
            parser.error("❌ Hashtag non può essere vuoto!")
    
    # Validazione count
    if args.count < 10 or args.count > 500:
        parser.error(f"❌ Count deve essere tra 10 e 500 (ricevuto: {args.count})")
    
    # Validazione date conflittuali
    if args.last_days and (args.start_date or args.end_date):
        parser.error("❌ Non usare --last-days insieme a --start-date/--end-date!")
    
    if args.last_days and (args.last_days < 1 or args.last_days > 7):
        parser.error("❌ --last-days deve essere tra 1 e 7 (Piano Free)")
    
    # Validazione directory output
    try:
        os.makedirs(args.output_dir, exist_ok=True)
    except Exception as e:
        parser.error(f"❌ Impossibile creare directory {args.output_dir}: {e}")
    
    return args

def validate_dates(start_date_str, end_date_str, logger):
    """Valida e converte le date in formato ISO per Twitter API"""
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        
        # Se end_date non specificata, usa oggi
        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        else:
            end_date = datetime.now()
            logger.info(f"📅 End date non specificata, uso oggi: {end_date.strftime('%Y-%m-%d')}")
        
        if start_date >= end_date:
            raise ValueError("Data inizio deve essere precedente a data fine")
        
        # ✅ MIGLIORAMENTO: Controllo Piano Free più preciso
        today = datetime.now()
        days_back = (today - start_date).days
        
        if days_back > 7:
            logger.warning(f"⚠️  Data inizio {days_back} giorni fa")
            logger.warning("⚠️  Piano Free Twitter limitato a ~7 giorni - possibili errori API")
            logger.info("💡 Suggerimento: usa date più recenti o Piano Basic")
        
        # Converte in formato ISO per Twitter API
        start_iso = start_date.strftime('%Y-%m-%dT00:00:00Z')
        end_iso = end_date.strftime('%Y-%m-%dT23:59:59Z')
        
        logger.info(f"📅 Filtro date validato: {start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}")
        
        return start_iso, end_iso
        
    except ValueError as e:
        logger.error(f"❌ Errore formato date: {e}")
        logger.info("💡 Formato richiesto: YYYY-MM-DD (es: 2025-06-01)")
        return None, None

def process_last_days_filter(last_days, logger):
    """Converte --last-days in start_time/end_time"""
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=last_days)
        
        start_iso = start_date.strftime('%Y-%m-%dT00:00:00Z')
        end_iso = end_date.strftime('%Y-%m-%dT23:59:59Z')
        
        logger.info(f"📅 Filtro ultimi {last_days} giorni: {start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}")
        
        return start_iso, end_iso
        
    except Exception as e:
        logger.error(f"❌ Errore calcolo date: {e}")
        return None, None

def check_credentials(logger):
    """Verifica che tutte le credenziali siano configurate"""
    required_vars = [
        'TWITTER_CONSUMER_KEY',
        'TWITTER_CONSUMER_SECRET', 
        'TWITTER_ACCESS_TOKEN',
        'TWITTER_ACCESS_TOKEN_SECRET',
        'TWITTER_BEARER_TOKEN'
    ]
    
    missing = []
    for var in required_vars:
        if not os.getenv(var):
            missing.append(var)
    
    if missing:
        logger.error("❌ Credenziali mancanti nel file .env:")
        for var in missing:
            logger.error(f"   - {var}")
        logger.info("💡 Crea file .env con le tue credenziali Twitter API")
        return False
    
    logger.info("✅ Tutte le credenziali sono configurate!")
    return True

def create_twitter_client(logger):
    """Crea client Twitter semplificato"""
    try:
        api = pytwitter.Api(
            bearer_token=os.getenv('TWITTER_BEARER_TOKEN')
        )
        logger.info("✅ Client Twitter creato con successo!")
        return api
    except Exception as e:
        logger.error(f"❌ Errore creazione client: {e}")
        return None

def clean_tweet_text(text, logger):
    """Rimuove link ma mantiene il resto"""
    try:
        # Rimuove link https://t.co/...
        text = re.sub(r'https://t\.co/\w+', '', text)
        # Rimuove spazi multipli
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    except Exception as e:
        logger.warning(f"⚠️  Errore pulizia testo: {e}")
        return text

def is_meaningful_text(clean_text, hashtag, min_length, logger):
    """Decide se il tweet ha abbastanza contenuto testuale"""
    try:
        # Rimuovi l'hashtag stesso per contare il resto
        text_without_hashtag = clean_text.replace(f"#{hashtag}", "").replace(f"#{hashtag.lower()}", "")
        text_without_hashtag = text_without_hashtag.strip()
        
        # Criteri per tweet "significativo"
        if len(text_without_hashtag) < min_length:
            return False
        
        # Se è solo hashtag e simboli/emoji
        if re.match(r'^[#@\s\W]*$', text_without_hashtag):
            return False
        
        return True
        
    except Exception as e:
        logger.warning(f"⚠️  Errore valutazione testo: {e}")
        return True  # In caso di errore, mantieni il tweet

def search_hashtag(api, hashtag, max_results=10, lang='it', start_time=None, end_time=None, 
                  enable_filter=True, min_text_length=10, logger=None):
    """Cerca tweet per hashtag con tutti i filtri configurabili"""
    try:
        logger.info(f"🔍 Cercando {max_results} tweet per #{hashtag} (lingua: {lang})")
        
        if start_time and end_time:
            logger.info(f"📅 Filtro temporale: ATTIVO")
            logger.debug(f"📅 Range: {start_time} - {end_time}")
        else:
            logger.info(f"📅 Periodo: ultimi 7 giorni (default API)")
        
        filter_status = "ATTIVO" if enable_filter else "DISATTIVATO"
        logger.info(f"🎯 Filtro contenuto: {filter_status}")
        
        # Query con filtro lingua
        query = f"#{hashtag} lang:{lang} -is:retweet"
        logger.debug(f"📝 Query utilizzata: {query}")
        
        # API call con/senza filtri temporali
        api_params = {
            'query': query,
            'max_results': max_results,
            'tweet_fields': [
                'id', 'text', 'created_at', 'author_id', 
                'conversation_id', 'public_metrics', 'lang'
            ],
            'expansions': ['author_id'],
            'user_fields': ['id', 'name', 'username']
        }
        
        if start_time and end_time:
            api_params['start_time'] = start_time
            api_params['end_time'] = end_time
        
        response = api.search_tweets(**api_params)
        
        if not response.data:
            logger.warning(f"❌ Nessun tweet trovato per #{hashtag} in lingua {lang}")
            if start_time:
                logger.info("💡 Prova ad allargare il range temporale")
            return []
        
        logger.info(f"📥 Ricevuti {len(response.data)} tweet dall'API")
        
        # Processa utenti se disponibili
        users_dict = {}
        if hasattr(response, 'includes') and response.includes and response.includes.users:
            for user in response.includes.users:
                users_dict[user.id] = {
                    'username': user.username,
                    'name': user.name
                }
            logger.debug(f"👥 Processati {len(users_dict)} utenti")
        
        # Filtra tweet in base al contenuto testuale
        filtered_tweets = []
        discarded_count = 0
        
        for tweet in response.data:
            try:
                # Pulisci il testo dai link
                clean_text = clean_tweet_text(tweet.text, logger)
                
                # Verifica se c'è abbastanza contenuto testuale utile
                if not enable_filter or is_meaningful_text(clean_text, hashtag, min_text_length, logger):
                    author_info = users_dict.get(tweet.author_id, {})
                    
                    tweet_data = {
                        'id': tweet.id,
                        'text': tweet.text,
                        'clean_text': clean_text,
                        'text_length': len(clean_text),
                        'original_length': len(tweet.text),
                        'created_at': str(tweet.created_at) if tweet.created_at else None,
                        'author_id': tweet.author_id,
                        'author_username': author_info.get('username', 'unknown'),
                        'author_name': author_info.get('name', 'unknown'),
                        'hashtag': hashtag,
                        'lang': tweet.lang if hasattr(tweet, 'lang') else None,
                        'has_links': 'https://t.co/' in tweet.text,
                        'meaningful_content': True,
                        'language_filter': lang,
                        'date_filter_applied': start_time is not None,
                        'content_filter_applied': enable_filter,
                        'min_text_length_used': min_text_length
                    }
                    filtered_tweets.append(tweet_data)
                    logger.debug(f"✅ Tweet {tweet.id} mantenuto ({len(clean_text)} char)")
                else:
                    discarded_count += 1
                    logger.debug(f"🗑️  Tweet {tweet.id} scartato: {clean_text[:50]}...")
                    
            except Exception as e:
                logger.warning(f"⚠️  Errore processando tweet {tweet.id}: {e}")
                continue
        
        logger.info(f"📊 Risultati filtering:")
        logger.info(f"   - Processati: {len(response.data)} tweet")
        logger.info(f"   - Mantenuti: {len(filtered_tweets)}")
        logger.info(f"   - Scartati: {discarded_count}")
        logger.info(f"   - Lingua: {lang}")
        logger.info(f"   - Filtro date: {'ATTIVO' if start_time else 'INATTIVO'}")
        logger.info(f"   - Filtro contenuto: {filter_status}")
        
        return filtered_tweets
        
    except Exception as e:
        error_str = str(e)
        logger.error(f"❌ Errore ricerca #{hashtag}: {e}")
        
        # ✅ MIGLIORAMENTO: Gestione errori più dettagliata
        if "429" in error_str:
            logger.error("🚫 Rate limit raggiunto")
            logger.info("💡 Suggerimenti:")
            logger.info("   - Aspetta 15-30 minuti")
            logger.info("   - Piano Free Twitter molto limitato")
            logger.info("   - Considera upgrade a Piano Basic")
        elif "401" in error_str:
            logger.error("🔑 Credenziali non valide - controlla file .env")
        elif "403" in error_str:
            logger.error("🚫 Accesso negato - controlla permessi API")
        elif "422" in error_str or "Invalid" in error_str:
            logger.error("📝 Parametri query non validi")
            if start_time:
                logger.error("   - Possibile problema con filtri date")
                logger.error("   - Piano Free limitato a ~7 giorni indietro")
                logger.info("💡 Prova senza filtri date o usa date più recenti")
        else:
            logger.error(f"🔧 Errore tecnico: {type(e).__name__}")
            logger.debug(f"🔍 Dettaglio errore: {error_str}")
        
        return []

def save_tweets(tweets, hashtag, output_dir, output_prefix, logger):
    """Salva tweet in JSON con metadati estesi"""
    if not tweets:
        logger.warning("⚠️  Nessun tweet da salvare")
        return None
    
    try:
        # Nome file con timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{output_dir}/{output_prefix}{hashtag}_{timestamp}.json"
        
        # Statistiche sui tweet
        total_original_chars = sum(tweet['original_length'] for tweet in tweets)
        total_clean_chars = sum(tweet['text_length'] for tweet in tweets)
        tweets_with_links = sum(1 for tweet in tweets if tweet['has_links'])
        languages = {}
        
        for tweet in tweets:
            lang = tweet.get('lang', 'unknown')
            languages[lang] = languages.get(lang, 0) + 1
        
        # ✅ MIGLIORAMENTO: Metadati più completi
        data = {
            'metadata': {
                'hashtag': hashtag,
                'collection_time': datetime.now().isoformat(),
                'total_tweets': len(tweets),
                'script_version': 'step3_plus_hybrid',
                'filters_applied': {
                    'language_filter': tweets[0].get('language_filter', 'it') if tweets else 'it',
                    'date_filter_applied': tweets[0].get('date_filter_applied', False) if tweets else False,
                    'content_filter_applied': tweets[0].get('content_filter_applied', True) if tweets else True,
                    'min_text_length': tweets[0].get('min_text_length_used', 10) if tweets else 10,
                    'exclude_retweets': True
                },
                'output_info': {
                    'directory': output_dir,
                    'prefix': output_prefix,
                    'filename': filename
                },
                'statistics': {
                    'total_original_characters': total_original_chars,
                    'total_clean_characters': total_clean_chars,
                    'tweets_with_links': tweets_with_links,
                    'tweets_text_only': len(tweets) - tweets_with_links,
                    'average_text_length': round(total_clean_chars / len(tweets), 1),
                    'languages': languages
                }
            },
            'tweets': tweets
        }
        
        # Salva in JSON
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        
        logger.info(f"💾 File salvato con successo: {filename}")
        logger.info(f"📊 Statistiche salvate:")
        logger.info(f"   - Tweet totali: {len(tweets)}")
        logger.info(f"   - Con link: {tweets_with_links}")
        logger.info(f"   - Solo testo: {len(tweets) - tweets_with_links}")
        logger.info(f"   - Lunghezza media: {round(total_clean_chars / len(tweets), 1)} caratteri")
        
        return filename
        
    except Exception as e:
        logger.error(f"❌ Errore salvataggio: {e}")
        return None

def print_summary(tweets, hashtag, logger):
    """Stampa riassunto dettagliato dei tweet raccolti"""
    if not tweets:
        return
    
    try:
        logger.info(f"📊 RIASSUNTO FINALE - #{hashtag}")
        logger.info("=" * 60)
        
        # Statistiche generali
        total_tweets = len(tweets)
        tweets_with_links = sum(1 for tweet in tweets if tweet['has_links'])
        tweets_text_only = total_tweets - tweets_with_links
        
        logger.info(f"📈 Tweet raccolti: {total_tweets}")
        logger.info(f"🔗 Con link/media: {tweets_with_links}")
        logger.info(f"📝 Solo testo: {tweets_text_only}")
        
        # Statistiche testo
        avg_length = sum(tweet['text_length'] for tweet in tweets) / total_tweets
        logger.info(f"📏 Lunghezza media testo: {avg_length:.1f} caratteri")
        
        # Lingue
        languages = {}
        for tweet in tweets:
            lang = tweet.get('lang', 'unknown')
            languages[lang] = languages.get(lang, 0) + 1
        
        logger.info(f"🌍 Lingue trovate: {dict(sorted(languages.items(), key=lambda x: x[1], reverse=True))}")
        
        # Top 3 tweet più lunghi
        longest_tweets = sorted(tweets, key=lambda x: x['text_length'], reverse=True)[:3]
        
        logger.info(f"📝 Top 3 tweet più ricchi di contenuto:")
        for i, tweet in enumerate(longest_tweets):
            clean_preview = tweet['clean_text'][:80] + "..." if len(tweet['clean_text']) > 80 else tweet['clean_text']
            logger.info(f"{i+1}. ({tweet['text_length']} char) @{tweet['author_username']}: {clean_preview}")
        
        # ✅ MIGLIORAMENTO: Summary filtri più dettagliato
        filters_applied = []
        sample_tweet = tweets[0] if tweets else {}
        
        if sample_tweet.get('language_filter'):
            filters_applied.append(f"Lingua: {sample_tweet['language_filter']}")
        
        if sample_tweet.get('content_filter_applied'):
            min_len = sample_tweet.get('min_text_length_used', 10)
            filters_applied.append(f"Contenuto significativo (min {min_len} char)")
        else:
            filters_applied.append("Contenuto: NESSUN FILTRO")
        
        filters_applied.append("Esclusione retweet")
        
        if sample_tweet.get('date_filter_applied'):
            filters_applied.append("Filtro temporale")
        
        logger.info(f"🎯 Filtri applicati: {', '.join(filters_applied)}")
        
    except Exception as e:
        logger.error(f"⚠️  Errore nel riassunto: {e}")

def main():
    """Funzione principale - STEP 3+ Versione ibrida"""
    # Parse argomenti con validazione robusta
    args = parse_arguments()
    
    # Setup logger
    logger = setup_logger(args.log_level)
    
    logger.info("🐦 DATARIA SCRAPER - STEP 3+ HYBRID")
    logger.info("🇮🇹 ✅ Filtro lingua configurabile")
    logger.info("📝 ✅ Logger professionale")
    logger.info("⚙️  ✅ Argparse automazione completa")
    logger.info("📅 ✅ Filtri date avanzati")
    logger.info("🎯 ✅ Controllo filtri granulare")
    logger.info("=" * 60)
    
    # Dry run check
    if args.dry_run:
        logger.info("🧪 DRY RUN MODE - Test configurazione")
        logger.info(f"   - Hashtag: {args.hashtag or 'Da richiedere'}")
        logger.info(f"   - Count: {args.count}")
        logger.info(f"   - Lingua: {args.lang}")
        logger.info(f"   - Date: {args.start_date or 'default'} - {args.end_date or 'default'}")
        logger.info(f"   - Last days: {args.last_days or 'non usato'}")
        logger.info(f"   - Filtro contenuto: {'DISATTIVATO' if args.no_filter else 'ATTIVO'}")
        logger.info(f"   - Output: {args.output_dir}/{args.output_prefix}...")
        logger.info("✅ Configurazione valida! Rimuovi --dry-run per eseguire.")
        return
    
    try:
        # 1. Verifica credenziali
        if not check_credentials(logger):
            sys.exit(1)
        
        # 2. Gestione filtri temporali
        start_time, end_time = None, None
        
        if args.last_days:
            start_time, end_time = process_last_days_filter(args.last_days, logger)
            if not start_time:
                logger.error("❌ Errore calcolo date da --last-days")
                sys.exit(1)
        elif args.start_date and args.end_date:
            start_time, end_time = validate_dates(args.start_date, args.end_date, logger)
            if not start_time:
                logger.error("❌ Date non valide, uscita")
                sys.exit(1)
        elif args.start_date and not args.end_date:
            # Se solo start_date, end_date = oggi
            today_str = datetime.now().strftime('%Y-%m-%d')
            start_time, end_time = validate_dates(args.start_date, today_str, logger)
            if not start_time:
                logger.error("❌ Start date non valida")
                sys.exit(1)
        
        # 3. Crea client
        api = create_twitter_client(logger)
        if not api:
            sys.exit(1)
        
        # 4. Gestisci input hashtag
        hashtag = args.hashtag
        if not hashtag and not args.auto:
            # Modalità interattiva solo se non auto
            print("\n" + "=" * 60)
            hashtag = input("📝 Inserisci hashtag (senza #): ").strip()
        
        if not hashtag:
            logger.error("❌ Hashtag non specificato!")
            if args.auto:
                logger.info("💡 Modalità --auto richiede --hashtag specificato")
            else:
                logger.info("💡 Usa: --hashtag NOME o modalità interattiva senza --auto")
            sys.exit(1)
        
        hashtag = hashtag.lstrip('#')
        
        # 5. Log configurazione finale
        logger.info(f"🎯 Configurazione finale:")
        logger.info(f"   - Hashtag: #{hashtag}")
        logger.info(f"   - Quantità: {args.count} tweet")
        logger.info(f"   - Lingua: {args.lang}")
        
        if start_time:
            logger.info(f"   - Filtro date: ATTIVO")
        else:
            logger.info(f"   - Filtro date: ultimi 7gg (default API)")
        
        filter_status = "DISATTIVATO" if args.no_filter else f"ATTIVO (min {args.min_text_length} char)"
        logger.info(f"   - Filtro contenuto: {filter_status}")
        logger.info(f"   - Output: {args.output_dir}/{args.output_prefix}...")
        
        # 6. Cerca tweet con tutti i filtri
        tweets = search_hashtag(
            api=api,
            hashtag=hashtag,
            max_results=args.count,
            lang=args.lang,
            start_time=start_time,
            end_time=end_time,
            enable_filter=not args.no_filter,
            min_text_length=args.min_text_length,
            logger=logger
        )
        
        # 7. Salva e mostra risultati
        if tweets:
            filename = save_tweets(
                tweets=tweets,
                hashtag=hashtag,
                output_dir=args.output_dir,
                output_prefix=args.output_prefix,
                logger=logger
            )
            print_summary(tweets, hashtag, logger)
            
            logger.info("🎉 SCRAPING COMPLETATO CON SUCCESSO!")
            logger.info(f"📁 File: {filename}")
            
            # Messaggi personalizzati in base ai filtri
            lang_name = {
                'it': 'italiani', 'en': 'inglesi', 'es': 'spagnoli', 
                'fr': 'francesi', 'de': 'tedeschi', 'pt': 'portoghesi'
            }.get(args.lang, f'in {args.lang}')
            
            logger.info(f"📊 Tweet {lang_name} raccolti: {len(tweets)}")
            
            if start_time:
                logger.info("📅 Con filtro temporale applicato")
            
            if not args.no_filter:
                logger.info(f"🎯 Con filtro contenuto significativo (min {args.min_text_length} char)")
            
        else:
            # Messaggi di errore più informativi
            lang_name = {
                'it': 'italiani', 'en': 'inglesi', 'es': 'spagnoli'
            }.get(args.lang, f'in {args.lang}')
            
            logger.warning(f"😔 Nessun tweet {lang_name} trovato per #{hashtag}")
            
            logger.info("💡 Suggerimenti per migliorare i risultati:")
            logger.info("   - Prova hashtag più popolari")
            logger.info(f"   - Prova lingua diversa: --lang en (invece di {args.lang})")
            
            if start_time:
                logger.info("   - Allarga il range temporale o rimuovi filtri date")
            
            if not args.no_filter:
                logger.info(f"   - Abbassa soglia: --min-text-length 5 (ora: {args.min_text_length})")
                logger.info("   - Disabilita filtri: --no-filter")
            
            logger.info("   - Controlla rate limiting (aspetta 15-30 min)")
            logger.info("   - Verifica che hashtag sia scritto correttamente")
            
    except KeyboardInterrupt:
        logger.info("⏹️  Operazione interrotta dall'utente")
        sys.exit(130)  # Standard exit code for Ctrl+C
    except Exception as e:
        logger.error(f"❌ Errore generale: {e}")
        logger.debug(f"🔍 Stack trace completo:", exc_info=True)
        logger.info("🔧 Riprova o controlla la configurazione")
        sys.exit(1)

if __name__ == "__main__":
    main()