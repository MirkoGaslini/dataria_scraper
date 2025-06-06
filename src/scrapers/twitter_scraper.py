#!/usr/bin/env python3
"""
Twitter Scraper - Versione Refactorizzata
Usa moduli core per eliminare duplicazioni
"""

import os
import json
import sys
from datetime import datetime
from dotenv import load_dotenv

# ✅ IMPORT DAI MODULI CORE (sostituiscono funzioni duplicate)
from src.core.logger import setup_twitter_logger
from src.core.text_utils import clean_tweet_text, is_meaningful_text
from src.core.date_utils import validate_date_arguments
from src.core.cli_utils import (
    setup_twitter_argparse, validate_common_arguments, 
    validate_count_argument, clean_hashtag_input,
    check_auto_mode_requirements, print_configuration_summary
)

# Carica le variabili d'ambiente dal file .env
load_dotenv()

# Controlla se pytwitter è installato
try:
    import pytwitter
except ImportError:
    print("❌ ERRORE: python-twitter-v2 non è installato!")
    print("Esegui: pip install python-twitter-v2 python-dotenv")
    exit(1)


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
                # ✅ USA MODULO CORE per pulizia testo
                clean_text = clean_tweet_text(tweet.text, logger)
                
                # ✅ USA MODULO CORE per valutazione significatività
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
        
        # Gestione errori dettagliata
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
    """Salva tweet in formato JSONL - Una riga per tweet"""
    if not tweets:
        logger.warning("⚠️  Nessun tweet da salvare")
        return None
    
    try:
        # Nome file con timestamp e estensione .jsonl
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{output_dir}/{output_prefix}{hashtag}_{timestamp}.jsonl"
        
        # Aggiungi metadati di collezione
        collection_time = datetime.now().isoformat()
        
        # Salva in formato JSONL - una riga per tweet
        with open(filename, 'w', encoding='utf-8') as f:
            for tweet in tweets:
                # Aggiungi metadati di collezione a ogni tweet
                tweet_with_metadata = tweet.copy()
                tweet_with_metadata.update({
                    'collection_time': collection_time,
                    'search_term': hashtag,
                    'platform': 'twitter'
                })
                
                # Scrivi una riga JSON per tweet (formato JSONL)
                json_line = json.dumps(tweet_with_metadata, ensure_ascii=False, default=str)
                f.write(json_line + '\n')
        
        # Calcola statistiche per log (come prima)
        total_original_chars = sum(tweet['original_length'] for tweet in tweets)
        total_clean_chars = sum(tweet['text_length'] for tweet in tweets)
        tweets_with_links = sum(1 for tweet in tweets if tweet['has_links'])
        
        logger.info(f"💾 File JSONL salvato con successo: {filename}")
        logger.info(f"📊 Tweet salvati: {len(tweets)} (una riga per tweet)")
        logger.info(f"📊 Statistiche:")
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
        
        # Summary filtri
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
    """Funzione principale - Twitter Scraper Refactorizzato"""
    
    # ✅ USA MODULO CORE per argparse
    parser = setup_twitter_argparse()
    args = parser.parse_args()
    
    # ✅ USA MODULO CORE per validazioni comuni
    args = validate_common_arguments(args, parser)
    validate_count_argument(args, parser, min_count=10, max_count=500)
    
    # ✅ USA MODULO CORE per logger
    logger = setup_twitter_logger(args.log_level)
    
    logger.info("🐦 TWITTER SCRAPER - Versione Refactorizzata")
    logger.info("🏗️  Usa moduli core comuni")
    logger.info("=" * 60)
    
    # Dry run check
    if args.dry_run:
        logger.info("🧪 DRY RUN MODE - Test configurazione")
        extra_info = {
            'Hashtag': args.hashtag or 'Da richiedere',
            'Lingua': args.lang,
            'Date filter': 'ATTIVO' if (args.start_date or args.last_days) else 'default'
        }
        print_configuration_summary(args, extra_info)
        logger.info("✅ Configurazione valida! Rimuovi --dry-run per eseguire.")
        return
    
    try:
        # 1. Verifica credenziali
        if not check_credentials(logger):
            sys.exit(1)
        
        # 2. ✅ USA MODULO CORE per gestione filtri temporali
        start_time, end_time = validate_date_arguments(args, parser, logger)
        
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
        
        # ✅ USA MODULO CORE per pulizia hashtag
        hashtag = clean_hashtag_input(hashtag, parser)
        
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
            # Messaggi di errore informativi
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