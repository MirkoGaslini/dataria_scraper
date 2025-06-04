#!/usr/bin/env python3
"""
Script completo per raccogliere tweet per hashtag usando Twitter API v2
Versione finale con filtro intelligente per contenuti testuali significativi
"""

import os
import json
import re
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
        print(f"❌ Errore creazione client: {e}")
        return None

def clean_tweet_text(text):
    """Rimuove link ma mantiene il resto"""
    try:
        # Rimuove link https://t.co/...
        text = re.sub(r'https://t\.co/\w+', '', text)
        # Rimuove spazi multipli
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    except Exception as e:
        print(f"⚠️  Errore pulizia testo: {e}")
        return text  # Restituisce testo originale se fallisce

def is_meaningful_text(clean_text, hashtag):
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
        print(f"⚠️  Errore valutazione testo: {e}")
        return True  # In caso di errore, mantieni il tweet

def search_hashtag(api, hashtag, max_results=10):
    """Cerca tweet per hashtag con filtro intelligente"""
    try:
        print(f"\n🔍 Cercando #{hashtag} (filtro intelligente)...")
        
        # Query base senza filtri media
        response = api.search_tweets(
            query=f"#{hashtag} -is:retweet",
            max_results=max_results,
            tweet_fields=[
                'id', 'text', 'created_at', 'author_id', 
                'conversation_id', 'public_metrics', 'lang'
            ],
            expansions=['author_id'],
            user_fields=['id', 'name', 'username']
        )
        
        if not response.data:
            print(f"❌ Nessun tweet trovato per #{hashtag}")
            return []
        
        # Processa utenti se disponibili
        users_dict = {}
        if hasattr(response, 'includes') and response.includes and response.includes.users:
            for user in response.includes.users:
                users_dict[user.id] = {
                    'username': user.username,
                    'name': user.name
                }
        
        # Filtra tweet in base al contenuto testuale
        filtered_tweets = []
        discarded_count = 0
        
        for tweet in response.data:
            try:
                # Pulisci il testo dai link
                clean_text = clean_tweet_text(tweet.text)
                
                # Verifica se c'è abbastanza contenuto testuale utile
                if is_meaningful_text(clean_text, hashtag):
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
                        'meaningful_content': True
                    }
                    filtered_tweets.append(tweet_data)
                else:
                    discarded_count += 1
                    print(f"🗑️  Scartato tweet {discarded_count}: {clean_text[:50]}...")
                    
            except Exception as e:
                print(f"⚠️  Errore processando tweet {tweet.id}: {e}")
                continue  # Continua con il prossimo tweet
        
        print(f"✅ Processati {len(response.data)} tweet")
        print(f"📊 Mantenuti: {len(filtered_tweets)} | Scartati: {discarded_count}")
        
        return filtered_tweets
        
    except Exception as e:
        error_str = str(e)
        print(f"❌ Errore ricerca: {e}")
        
        if "429" in error_str:
            print("⚠️  Rate limit raggiunto - aspetta 15 minuti")
        elif "401" in error_str:
            print("🔑 Credenziali non valide")
        elif "403" in error_str:
            print("🚫 Accesso negato")
        elif "422" in error_str:
            print("📝 Parametri query non validi")
        else:
            print(f"🔧 Errore tecnico: {type(e).__name__}")
        
        return []

def save_tweets(tweets, hashtag):
    """Salva tweet in JSON con metadati estesi"""
    if not tweets:
        print("⚠️  Nessun tweet da salvare")
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
                'script_version': 'final_with_smart_filter',
                'filtering_enabled': True,
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
        
        print(f"💾 Salvato: {filename}")
        return filename
        
    except Exception as e:
        print(f"❌ Errore salvataggio: {e}")
        return None

def print_summary(tweets, hashtag):
    """Stampa riassunto dettagliato dei tweet raccolti"""
    if not tweets:
        return
    
    try:
        print(f"\n📊 RIASSUNTO FINALE - #{hashtag}")
        print("=" * 60)
        
        # Statistiche generali
        total_tweets = len(tweets)
        tweets_with_links = sum(1 for tweet in tweets if tweet['has_links'])
        tweets_text_only = total_tweets - tweets_with_links
        
        print(f"📈 Tweet raccolti: {total_tweets}")
        print(f"🔗 Con link/media: {tweets_with_links}")
        print(f"📝 Solo testo: {tweets_text_only}")
        
        # Statistiche testo
        avg_length = sum(tweet['text_length'] for tweet in tweets) / total_tweets
        print(f"📏 Lunghezza media testo: {avg_length:.1f} caratteri")
        
        # Lingue
        languages = {}
        for tweet in tweets:
            lang = tweet.get('lang', 'unknown')
            languages[lang] = languages.get(lang, 0) + 1
        
        print(f"🌍 Lingue: {dict(sorted(languages.items(), key=lambda x: x[1], reverse=True))}")
        
        # Top 3 tweet più lunghi
        longest_tweets = sorted(tweets, key=lambda x: x['text_length'], reverse=True)[:3]
        
        print(f"\n📝 Top 3 tweet più ricchi di contenuto:")
        for i, tweet in enumerate(longest_tweets):
            clean_preview = tweet['clean_text'][:80] + "..." if len(tweet['clean_text']) > 80 else tweet['clean_text']
            print(f"{i+1}. ({tweet['text_length']} char) @{tweet['author_username']}: {clean_preview}")
        
        print(f"\n🎯 Filtro qualità: Mantenuti solo tweet con contenuto testuale significativo")
        
    except Exception as e:
        print(f"⚠️  Errore nel riassunto: {e}")

def main():
    """Funzione principale"""
    print("🐦 DATARIA SCRAPER - Versione Finale")
    print("📝 Con filtro intelligente per contenuti testuali")
    print("=" * 60)
    
    try:
        # 1. Verifica credenziali
        if not check_credentials():
            return
        
        # 2. Crea client
        api = create_twitter_client()
        if not api:
            return
        
        # 3. Input utente
        print("\n" + "=" * 60)
        hashtag = input("📝 Inserisci hashtag (senza #): ").strip()
        
        if not hashtag:
            print("❌ Hashtag vuoto!")
            return
        
        hashtag = hashtag.lstrip('#')
        
        try:
            max_results = input("🔢 Quanti tweet? (default 20, max 500): ").strip()
            max_results = int(max_results) if max_results else 20
            max_results = max(10, min(max_results, 500))  # Tra 10 e 500
        except ValueError:
            max_results = 20
            print("⚠️  Valore non valido, uso default: 20")
        
        print(f"\n🎯 Cercando {max_results} tweet per #{hashtag}")
        print("🧠 Filtro attivo: solo tweet con contenuto testuale significativo")
        
        # 4. Cerca tweet
        tweets = search_hashtag(api, hashtag, max_results)
        
        # 5. Salva e mostra risultati
        if tweets:
            filename = save_tweets(tweets, hashtag)
            print_summary(tweets, hashtag)
            
            print(f"\n🎉 SUCCESSO!")
            print(f"📁 File salvato: {filename}")
            print(f"📊 Tweet significativi raccolti: {len(tweets)}")
        else:
            print(f"\n😔 Nessun tweet significativo trovato per #{hashtag}")
            print("💡 Suggerimenti:")
            print("   - Prova con hashtag più popolari")
            print("   - Aumenta il numero di tweet da cercare")
            print("   - Controlla se è un problema di rate limiting")
            
    except KeyboardInterrupt:
        print("\n\n⏹️  Operazione interrotta dall'utente")
    except Exception as e:
        print(f"\n❌ Errore generale: {e}")
        print("🔧 Riprova o controlla la configurazione")

if __name__ == "__main__":
    main()