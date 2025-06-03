#!/usr/bin/env python3
"""
Script per raccogliere tweet per hashtag usando Twitter API v2
Versione con debugging completo
"""

import os
import json
import logging
import time
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

# Configurazione logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def check_credentials():
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
        value = os.getenv(var)
        if not value:
            missing.append(var)
        else:
            # Mostra prime e ultime 4 lettere per debug (nascondendo il centro)
            masked = value[:4] + "***" + value[-4:] if len(value) > 8 else "***"
            print(f"✅ {var}: {masked}")
    
    if missing:
        print("❌ Credenziali mancanti nel file .env:")
        for var in missing:
            print(f"   - {var}")
        return False
    
    print("✅ Tutte le credenziali sono configurate!")
    return True

def create_twitter_clients():
    """Crea e restituisce i client Twitter secondo la documentazione"""
    try:
        # Client App Access Token (per ricerche pubbliche - consigliato)
        api = pytwitter.Api(
            consumer_key=os.getenv('TWITTER_CONSUMER_KEY'),
            consumer_secret=os.getenv('TWITTER_CONSUMER_SECRET'),
            bearer_token=os.getenv('TWITTER_BEARER_TOKEN')
        )
        
        # Client User Access Token (per operazioni autenticate dell'utente)
        my_api = pytwitter.Api(
            consumer_key=os.getenv('TWITTER_CONSUMER_KEY'),
            consumer_secret=os.getenv('TWITTER_CONSUMER_SECRET'),
            access_token=os.getenv('TWITTER_ACCESS_TOKEN'),
            access_secret=os.getenv('TWITTER_ACCESS_TOKEN_SECRET'),
        )
        
        print("✅ Client Twitter creati con successo!")
        print("  - api: App Access Token (per ricerche)")
        print("  - my_api: User Access Token (per operazioni utente)")
        return api, my_api
        
    except Exception as e:
        print(f"❌ Errore nella creazione del client: {e}")
        return None, None

def test_basic_connection(api):
    """Testa la connessione con una richiesta molto semplice"""
    try:
        print("🔍 Test connessione base...")
        
        # Test più semplice possibile - cerca solo 5 tweet generici
        response = api.search_tweets(
            query="hello",
            max_results=10
        )
        
        if response.data:
            print(f"✅ Connessione OK! API risponde correttamente")
            print(f"📊 Trovati {len(response.data)} tweet di test")
            
            # Mostra un esempio per debug
            first_tweet = response.data[0]
            preview = first_tweet.text[:50] + "..." if len(first_tweet.text) > 50 else first_tweet.text
            print(f"📝 Esempio tweet: {preview}")
            return True
        else:
            print("⚠️  API risponde ma nessun risultato per 'hello'")
            return True
            
    except Exception as e:
        error_str = str(e)
        print(f"❌ Test connessione fallito: {e}")
        
        if "401" in error_str:
            print("🔑 Errore 401: Credenziali non valide")
            print("   - Controlla Consumer Key/Secret")
            print("   - Controlla Bearer Token")
            print("   - Verifica che l'app Twitter sia attiva")
        elif "403" in error_str:
            print("🚫 Errore 403: Accesso negato")
            print("   - L'app potrebbe non avere i permessi necessari")
            print("   - Controlla le impostazioni dell'app su Twitter Developer")
        elif "429" in error_str:
            print("⏱️  Errore 429: Rate limit anche per il test base")
            print("   - Il piano Free ha limiti molto bassi")
            print("   - Aspetta 15 minuti e riprova")
        
        return False

def search_tweets_by_hashtag(api, hashtag, max_results=50):
    """
    Cerca tweet per un hashtag specifico
    
    Args:
        api: Client Twitter
        hashtag: Hashtag da cercare (senza #)
        max_results: Numero massimo di risultati (max 100)
    
    Returns:
        Lista di tweet
    """
    try:
        print(f"\n🔍 Cercando tweet per #{hashtag}...")
        
        # Costruisci la query di ricerca - sintassi semplificata
        query = f"#{hashtag} -is:retweet"
        
        print(f"📝 Query utilizzata: {query}")
        
        # Esegui la ricerca con il client app (api)
        response = api.search_tweets(
            query=query,
            max_results=min(max_results, 100),  # Twitter API v2 limite: 100
            tweet_fields=[
                'created_at', 'author_id', 'public_metrics', 
                'lang', 'possibly_sensitive'
            ],
            expansions=['author_id'],
            user_fields=['username', 'name', 'public_metrics', 'verified']
        )
        
        if not response.data:
            print(f"❌ Nessun tweet trovato per #{hashtag}")
            return []
        
        # Processa i risultati
        tweets = []
        users_dict = {}
        
        # Crea dizionario degli utenti se presenti
        if hasattr(response, 'includes') and response.includes and response.includes.users:
            for user in response.includes.users:
                users_dict[user.id] = {
                    'username': user.username,
                    'name': user.name,
                    'verified': user.verified if hasattr(user, 'verified') else False,
                    'followers': user.public_metrics.followers_count if user.public_metrics else 0
                }
        
        # Processa i tweet
        for tweet in response.data:
            author_info = users_dict.get(tweet.author_id, {})
            
            # Estrai le metriche del tweet
            metrics = {}
            if tweet.public_metrics:
                metrics = {
                    'retweets': tweet.public_metrics.retweet_count,
                    'likes': tweet.public_metrics.like_count,
                    'replies': tweet.public_metrics.reply_count,
                    'quotes': tweet.public_metrics.quote_count,
                }
            
            tweet_data = {
                'id': tweet.id,
                'text': tweet.text,
                'created_at': tweet.created_at.isoformat() if tweet.created_at else None,
                'author_id': tweet.author_id,
                'author_username': author_info.get('username', 'unknown'),
                'author_name': author_info.get('name', 'unknown'),
                'author_verified': author_info.get('verified', False),
                'author_followers': author_info.get('followers', 0),
                'hashtag_searched': hashtag,
                'language': tweet.lang,
                'possibly_sensitive': tweet.possibly_sensitive,
                'metrics': metrics,
                'url': f"https://twitter.com/{author_info.get('username', 'unknown')}/status/{tweet.id}"
            }
            tweets.append(tweet_data)
        
        print(f"✅ Trovati {len(tweets)} tweet per #{hashtag}")
        return tweets
        
    except Exception as e:
        error_str = str(e)
        if "429" in error_str or "Too Many Requests" in error_str:
            print(f"⚠️  Rate limit raggiunto per #{hashtag}")
            print("💡 Suggerimenti:")
            print("   - Aspetta 15 minuti prima di riprovare")
            print("   - Usa hashtag meno popolari") 
            print("   - Riduci il numero di tweet richiesti")
            print("   - Controlla i limiti del tuo piano Twitter Developer")
            print("   - Piano Free: 500 tweet/mese totali")
        else:
            print(f"❌ Errore nella ricerca per #{hashtag}: {e}")
        return []

def save_tweets_to_json(tweets, hashtag):
    """Salva i tweet in un file JSON"""
    if not tweets:
        print("⚠️  Nessun tweet da salvare")
        return None
        
    # Crea directory data se non esiste
    os.makedirs('data', exist_ok=True)
    
    # Nome file con timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"data/{hashtag}_{timestamp}.json"
    
    # Prepara i dati da salvare
    data = {
        'metadata': {
            'hashtag': hashtag,
            'collection_time': datetime.now().isoformat(),
            'total_tweets': len(tweets),
            'script_version': '1.1-debug'
        },
        'tweets': tweets
    }
    
    # Salva in JSON
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        print(f"💾 Tweet salvati in: {filename}")
        return filename
    except Exception as e:
        print(f"❌ Errore nel salvataggio: {e}")
        return None

def print_tweet_summary(tweets):
    """Stampa un riassunto dei tweet raccolti"""
    if not tweets:
        return
    
    print(f"\n📊 RIASSUNTO - {len(tweets)} tweet raccolti:")
    print("=" * 50)
    
    # Statistiche generali
    languages = {}
    total_likes = 0
    total_retweets = 0
    verified_authors = 0
    
    for tweet in tweets:
        # Conta lingue
        lang = tweet.get('language', 'unknown')
        languages[lang] = languages.get(lang, 0) + 1
        
        # Somma metriche
        metrics = tweet.get('metrics', {})
        total_likes += metrics.get('likes', 0)
        total_retweets += metrics.get('retweets', 0)
        
        # Conta autori verificati
        if tweet.get('author_verified', False):
            verified_authors += 1
    
    print(f"🌍 Lingue: {dict(sorted(languages.items(), key=lambda x: x[1], reverse=True))}")
    print(f"❤️  Like totali: {total_likes}")
    print(f"🔄 Retweet totali: {total_retweets}")
    print(f"✅ Autori verificati: {verified_authors}")
    
    # Tweet più popolari
    tweets_sorted = sorted(tweets, key=lambda x: x.get('metrics', {}).get('likes', 0), reverse=True)
    
    print(f"\n🔥 Top 3 tweet più popolari:")
    for i, tweet in enumerate(tweets_sorted[:3]):
        text_preview = tweet['text'][:80] + "..." if len(tweet['text']) > 80 else tweet['text']
        metrics = tweet['metrics']
        print(f"{i+1}. @{tweet['author_username']}: {text_preview}")
        print(f"   👍 {metrics.get('likes', 0)} | 🔄 {metrics.get('retweets', 0)} | 💬 {metrics.get('replies', 0)}")
        print(f"   🔗 {tweet['url']}")
        print()

def main():
    """Funzione principale"""
    print("🐦 DATARIA SCRAPER - Twitter Hashtag Collector")
    print("=" * 60)
    print("🔍 Versione con debugging completo")
    
    # 1. Verifica credenziali
    print("\n🔑 FASE 1: Verifica credenziali")
    if not check_credentials():
        print("\n❌ Configura prima le credenziali nel file .env")
        return
    
    # 2. Crea client Twitter
    print("\n🤖 FASE 2: Creazione client Twitter")
    api, my_api = create_twitter_clients()
    if not api or not my_api:
        return
    
    # 2.5 Test connessione base
    print("\n🧪 FASE 2.5: Test connessione")
    if not test_basic_connection(api):
        print("❌ Problemi di connessione base - impossibile continuare")
        print("\n🔧 Verifica:")
        print("   1. Credenziali corrette nel file .env")
        print("   2. App Twitter attiva e configurata")
        print("   3. Connessione internet")
        return
    
    # 3. Richiedi l'hashtag all'utente
    print("\n" + "=" * 60)
    print("🎯 FASE 3: Raccolta dati")
    hashtag = input("📝 Inserisci l'hashtag da cercare (senza #): ").strip()
    
    if not hashtag:
        print("❌ Hashtag non può essere vuoto!")
        return
    
    # Rimuovi # se l'utente l'ha inserito
    hashtag = hashtag.lstrip('#')
    
    # 4. Chiedi quanti tweet raccogliere
    try:
        max_results = input("🔢 Quanti tweet vuoi raccogliere? (default: 10, max: 100): ").strip()
        max_results = int(max_results) if max_results else 10
        max_results = min(max_results, 100)  # Limite API
    except ValueError:
        max_results = 10
        print("⚠️  Valore non valido, uso default: 10")
    
    print(f"\n🎯 Cercando {max_results} tweet per #{hashtag}")
    
    # 5. Raccoglie tweet
    tweets = search_tweets_by_hashtag(api, hashtag, max_results)
    
    if tweets:
        # 6. Salva i risultati
        filename = save_tweets_to_json(tweets, hashtag)
        
        # 7. Mostra riassunto
        print_tweet_summary(tweets)
        
        print(f"\n🎉 COMPLETATO!")
        print(f"📁 File salvato: {filename}")
        print(f"📊 Tweet raccolti: {len(tweets)}")
    else:
        print(f"\n😔 Nessun tweet trovato per #{hashtag}")
        print("💡 Possibili cause:")
        print("   - Rate limit raggiunto (piano Free: 500 tweet/mese)")
        print("   - Hashtag non popolare o senza tweet recenti")
        print("   - Problemi temporanei dell'API Twitter")
        print("\n🔄 Riprova tra 15-30 minuti con un hashtag diverso")

if __name__ == "__main__":
    main()