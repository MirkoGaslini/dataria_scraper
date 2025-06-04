#!/usr/bin/env python3
"""
Script per raccogliere tweet per hashtag usando Twitter API v2
STEP 2: Step 1 + LOGGER PROFESSIONALE al posto dei print
"""

import os
import json
import re
import logging
from datetime import datetime
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
    
    # Handler console (sostituisce i print)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Handler file
    log_filename = f"logs/scraper_{datetime.now().strftime('%Y%m%d')}.log"
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger

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
        return False
    
    logger.info("✅ Tutte le credenziali sono configurate!")
    return True

def create_twitter_client(logger):
    """Crea client Twitter semplificato"""
    try:
        # Solo Bearer Token per semplicità
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
        return text  # Restituisce testo originale se fallisce

def is_meaningful_text(clean_text, hashtag, logger):
    """Decide se il tweet ha abbastanza contenuto testuale"""
    try:
        # Rimuovi l'hashtag stesso per contare il resto
        text_without_hashtag = clean_text.replace(f"#{hashtag}", "").replace(f"#{hashtag.lower()}", "")
        text_without_hashtag = text_without_hashtag.strip()
        
        # Criteri per tweet "significativo"
        if len(text_without_hashtag) < 10:  # Meno di 10 caratteri oltre hashtag
            return False
        
        # Se è solo hashtag e simboli/emoji
        if re.match(r'^[#@\s\W]*$', text_without_hashtag):
            return False
        
        return True
        
    except Exception as e:
        logger.warning(f"⚠️  Errore valutazione testo: {e}")
        return True  # In caso di errore, mantieni il tweet

def search_hashtag(api, hashtag, max_results=10, lang='it', logger=None):
    """Cerca tweet per hashtag con filtro intelligente + LINGUA"""
    try:
        logger.info(f"🔍 Cercando {max_results} tweet per #{hashtag} (lingua: {lang})")
        
        # Query con filtro lingua italiana
        query = f"#{hashtag} lang:{lang} -is:retweet"
        logger.debug(f"📝 Query utilizzata: {query}")
        
        # API call identica a ieri (che funzionava)
        response = api.search_tweets(
            query=query,
            max_results=max_results,
            tweet_fields=[
                'id', 'text', 'created_at', 'author_id', 
                'conversation_id', 'public_metrics', 'lang'
            ],
            expansions=['author_id'],
            user_fields=['id', 'name', 'username']
        )
        
        if not response.data:
            logger.warning(f"❌ Nessun tweet trovato per #{hashtag} in lingua {lang}")
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
                if is_meaningful_text(clean_text, hashtag, logger):
                    author_info = users_dict.get(tweet.author_id, {})
                    
                    tweet_data = {
                        'id': tweet.id,
                        'text': tweet.text,           # Testo originale
                        'clean_text': clean_text,     # Testo senza link
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
                        'language_filter': lang
                    }
                    filtered_tweets.append(tweet_data)
                    logger.debug(f"✅ Tweet {tweet.id} mantenuto ({len(clean_text)} char)")
                else:
                    discarded_count += 1
                    logger.debug(f"🗑️  Tweet {tweet.id} scartato: {clean_text[:50]}...")
                    
            except Exception as e:
                logger.warning(f"⚠️  Errore processando tweet {tweet.id}: {e}")
                continue  # Continua con il prossimo tweet
        
        logger.info(f"📊 Risultati filtering:")
        logger.info(f"   - Processati: {len(response.data)} tweet")
        logger.info(f"   - Mantenuti: {len(filtered_tweets)}")
        logger.info(f"   - Scartati: {discarded_count}")
        logger.info(f"   - Lingua: {lang}")
        
        return filtered_tweets
        
    except Exception as e:
        error_str = str(e)
        logger.error(f"❌ Errore ricerca #{hashtag}: {e}")
        
        if "429" in error_str:
            logger.error("🚫 Rate limit raggiunto")
            logger.info("💡 Suggerimenti:")
            logger.info("   - Aspetta 15-30 minuti")
            logger.info("   - Piano Free Twitter molto limitato")
            logger.info("   - Considera upgrade a Piano Basic")
        elif "401" in error_str:
            logger.error("🔑 Credenziali non valide")
        elif "403" in error_str:
            logger.error("🚫 Accesso negato")
        elif "422" in error_str:
            logger.error("📝 Parametri query non validi")
        else:
            logger.error(f"🔧 Errore tecnico: {type(e).__name__}")
        
        return []

def save_tweets(tweets, hashtag, logger):
    """Salva tweet in JSON con metadati estesi"""
    if not tweets:
        logger.warning("⚠️  Nessun tweet da salvare")
        return None
    
    try:
        # Crea directory data se non esiste
        os.makedirs('data', exist_ok=True)
        
        # Nome file con timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"data/{hashtag}_{timestamp}.json"
        
        # Statistiche sui tweet
        total_original_chars = sum(tweet['original_length'] for tweet in tweets)
        total_clean_chars = sum(tweet['text_length'] for tweet in tweets)
        tweets_with_links = sum(1 for tweet in tweets if tweet['has_links'])
        languages = {}
        
        for tweet in tweets:
            lang = tweet.get('lang', 'unknown')
            languages[lang] = languages.get(lang, 0) + 1
        
        # Prepara i dati da salvare
        data = {
            'metadata': {
                'hashtag': hashtag,
                'collection_time': datetime.now().isoformat(),
                'total_tweets': len(tweets),
                'script_version': 'step2_with_logger',
                'filtering_enabled': True,
                'language_filter': tweets[0].get('language_filter', 'it') if tweets else 'it',
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
        logger.info(f"🇮🇹 Filtro lingua: ATTIVO (solo italiano)")
        
        # Top 3 tweet più lunghi
        longest_tweets = sorted(tweets, key=lambda x: x['text_length'], reverse=True)[:3]
        
        logger.info(f"📝 Top 3 tweet più ricchi di contenuto:")
        for i, tweet in enumerate(longest_tweets):
            clean_preview = tweet['clean_text'][:80] + "..." if len(tweet['clean_text']) > 80 else tweet['clean_text']
            logger.info(f"{i+1}. ({tweet['text_length']} char) @{tweet['author_username']}: {clean_preview}")
        
        logger.info(f"🎯 Filtri applicati:")
        logger.info(f"   - Contenuto testuale significativo")
        logger.info(f"   - Solo lingua italiana")
        logger.info(f"   - Esclusione retweet")
        
    except Exception as e:
        logger.error(f"⚠️  Errore nel riassunto: {e}")

def main():
    """Funzione principale - STEP 2"""
    # Setup logger prima di tutto
    logger = setup_logger("INFO")
    
    logger.info("🐦 DATARIA SCRAPER - STEP 2")
    logger.info("🇮🇹 Feature attive: Filtro lingua italiana")
    logger.info("📝 Feature attive: Logger professionale")
    logger.info("=" * 60)
    
    try:
        # 1. Verifica credenziali
        if not check_credentials(logger):
            return
        
        # 2. Crea client
        api = create_twitter_client(logger)
        if not api:
            return
        
        # 3. Input utente (ancora con print per interattività)
        print("\n" + "=" * 60)
        hashtag = input("📝 Inserisci hashtag (senza #): ").strip()
        
        if not hashtag:
            logger.error("❌ Hashtag vuoto!")
            return
        
        hashtag = hashtag.lstrip('#')
        
        try:
            max_results = input("🔢 Quanti tweet? (default 20, max 500): ").strip()
            max_results = int(max_results) if max_results else 20
            max_results = max(10, min(max_results, 500))  # Tra 10 e 500
        except ValueError:
            max_results = 20
            logger.warning("⚠️  Valore non valido, uso default: 20")
        
        logger.info(f"🎯 Configurazione ricerca:")
        logger.info(f"   - Hashtag: #{hashtag}")
        logger.info(f"   - Quantità: {max_results} tweet")
        logger.info(f"   - Lingua: italiano")
        logger.info(f"   - Filtro qualità: attivo")
        
        # 4. Cerca tweet con filtro italiano
        tweets = search_hashtag(api, hashtag, max_results, lang='it', logger=logger)
        
        # 5. Salva e mostra risultati
        if tweets:
            filename = save_tweets(tweets, hashtag, logger)
            print_summary(tweets, hashtag, logger)
            
            logger.info("🎉 SCRAPING COMPLETATO CON SUCCESSO!")
            logger.info(f"📁 File: {filename}")
            logger.info(f"📊 Tweet italiani raccolti: {len(tweets)}")
        else:
            logger.warning(f"😔 Nessun tweet italiano significativo trovato per #{hashtag}")
            logger.info("💡 Suggerimenti:")
            logger.info("   - Prova con hashtag più popolari in Italia")
            logger.info("   - Alcuni hashtag potrebbero essere più usati in inglese")
            logger.info("   - Controlla se è un problema di rate limiting")
            
    except KeyboardInterrupt:
        logger.info("⏹️  Operazione interrotta dall'utente")
    except Exception as e:
        logger.error(f"❌ Errore generale: {e}")
        logger.info("🔧 Riprova o controlla la configurazione")

if __name__ == "__main__":
    main()