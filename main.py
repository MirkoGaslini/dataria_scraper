#!/usr/bin/env python3
"""
Script semplificato per raccogliere tweet per hashtag
SENZA test di connessione preliminari - va dritto al punto
"""

import os
import json
from datetime import datetime
from dotenv import load_dotenv

# Carica le variabili d'ambiente dal file .env
load_dotenv()

try:
    import pytwitter
except ImportError:
    print("❌ ERRORE: python-twitter-v2 non è installato!")
    print("Esegui: pip install python-twitter-v2 python-dotenv")
    exit(1)

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
        if not os.getenv(var):
            missing.append(var)
    
    if missing:
        print("❌ Credenziali mancanti nel file .env:")
        for var in missing:
            print(f"   - {var}")
        return False
    
    print("✅ Tutte le credenziali sono configurate!")
    return True

def create_twitter_client():
    """Crea client Twitter semplificato"""
    try:
        # Solo Bearer Token per semplicità
        api = pytwitter.Api(
            bearer_token=os.getenv('TWITTER_BEARER_TOKEN')
        )
        print("✅ Client Twitter creato!")
        return api
    except Exception as e:
        print(f"❌ Errore client: {e}")
        return None

def search_hashtag(api, hashtag, max_results=10):
    """Cerca tweet per hashtag - versione con testo completo"""
    try:
        print(f"\n🔍 Cercando #{hashtag}...")
        
        # Ricerca con richiesta esplicita del testo completo
        response = api.search_tweets(
            query=f"#{hashtag}",
            max_results=max_results,
            tweet_fields=['text', 'created_at', 'author_id']  # Richiede campi specifici
        )
        
        if not response.data:
            print(f"❌ Nessun tweet trovato per #{hashtag}")
            return []
        
        # Estrai solo i dati essenziali
        tweets = []
        for tweet in response.data:
            tweet_data = {
                'id': tweet.id,
                'text': tweet.text,
                'created_at': str(tweet.created_at) if tweet.created_at else None,
                'author_id': tweet.author_id,
                'hashtag': hashtag
            }
            tweets.append(tweet_data)
        
        print(f"✅ Trovati {len(tweets)} tweet!")
        return tweets
        
    except Exception as e:
        error_str = str(e)
        print(f"❌ Errore ricerca: {e}")
        
        if "429" in error_str:
            print("⚠️  Rate limit raggiunto - aspetta 15 minuti")
        elif "401" in error_str:
            print("🔑 Credenziali non valide")
        elif "403" in error_str:
            print("🚫 Accesso negato")
        
        return []

def save_tweets(tweets, hashtag):
    """Salva tweet in JSON"""
    if not tweets:
        return None
    
    os.makedirs('data', exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"data/{hashtag}_{timestamp}.json"
    
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump({
                'hashtag': hashtag,
                'timestamp': datetime.now().isoformat(),
                'count': len(tweets),
                'tweets': tweets
            }, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Salvato: {filename}")
        return filename
    except Exception as e:
        print(f"❌ Errore salvataggio: {e}")
        return None

def main():
    """Funzione principale semplificata"""
    print("🐦 DATARIA SCRAPER - Versione Semplificata")
    print("=" * 50)
    
    # 1. Verifica credenziali
    if not check_credentials():
        return
    
    # 2. Crea client
    api = create_twitter_client()
    if not api:
        return
    
    # 3. Input utente - DIRETTO, senza test
    print("\n" + "=" * 50)
    hashtag = input("📝 Inserisci hashtag (senza #): ").strip()
    
    if not hashtag:
        print("❌ Hashtag vuoto!")
        return
    
    hashtag = hashtag.lstrip('#')
    
    try:
        max_results = input("🔢 Quanti tweet? (default 10): ").strip()
        max_results = int(max_results) if max_results else 10
        max_results = max(10, min(max_results, 100))  # Tra 10 e 100
    except ValueError:
        max_results = 10
    
    # 4. Cerca tweet
    tweets = search_hashtag(api, hashtag, max_results)
    
    # 5. Salva e mostra risultati
    if tweets:
        filename = save_tweets(tweets, hashtag)
        
        print(f"\n🎉 SUCCESSO!")
        print(f"📊 Tweet raccolti: {len(tweets)}")
        print(f"📁 File: {filename}")
        
        # Mostra alcuni esempi
        print(f"\n📝 Primi 3 tweet:")
        for i, tweet in enumerate(tweets[:3]):
            text = tweet['text'][:60] + "..." if len(tweet['text']) > 60 else tweet['text']
            print(f"{i+1}. {text}")
    else:
        print("\n😔 Nessun tweet raccolto")

if __name__ == "__main__":
    main()