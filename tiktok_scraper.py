#!/usr/bin/env python3
"""
Script per raccogliere video TikTok usando TikTok-Api (davidteather)
STEP 2: TikTok scraper con argparse + RapidAPI Transcript Integration
"""

import os
import json
import re
import logging
import argparse
import sys
import asyncio
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Carica le variabili d'ambiente dal file .env
load_dotenv('.env')

# Controlla se TikTokApi è installato
try:
    from TikTokApi import TikTokApi
except ImportError:
    print("❌ ERRORE: TikTokApi non è installato!")
    print("Esegui: pip install TikTokApi")
    print("Poi: python -m playwright install")
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
    logger = logging.getLogger('TikTokScraper')
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Rimuovi handler esistenti per evitare duplicati
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Handler console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Handler file
    log_filename = f"logs/tiktok_scraper_{datetime.now().strftime('%Y%m%d')}.log"
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger

def parse_arguments():
    """Configura argparse - Pattern simile a Twitter scraper"""
    parser = argparse.ArgumentParser(
        description='TikTok Scraper avanzato con filtri, automazione e transcript',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Esempi di utilizzo:
  # Cerca video per hashtag
  %(prog)s --hashtag AI --count 20

  # Cerca video di un utente specifico
  %(prog)s --user therock --count 15

  # Video trending
  %(prog)s --trending --count 25

  # Con transcript audio
  %(prog)s --hashtag AI --count 10 --add-transcript

  # Modalità automatica
  %(prog)s --hashtag tech --count 30 --auto --quiet

  # Debug mode
  %(prog)s --hashtag startup --count 10 --verbose

  # Test configurazione
  %(prog)s --hashtag test --dry-run
        """
    )
    
    # Modalità di ricerca (mutuamente esclusive)
    search_group = parser.add_mutually_exclusive_group(required=False)
    
    search_group.add_argument(
        '--hashtag',
        type=str,
        help='Hashtag da cercare (senza #). Es: AI, tech, startup'
    )
    
    search_group.add_argument(
        '--user', '-u',
        type=str,
        help='Username TikTok da cui prendere video. Es: therock, tiktok'
    )
    
    search_group.add_argument(
        '--trending',
        action='store_true',
        help='Scarica video trending di TikTok'
    )
    
    # Parametri comuni
    parser.add_argument(
        '--count', '-n',
        type=int,
        default=20,
        help='Numero video da raccogliere (default: 20, min: 5, max: 100)'
    )
    
    # ✅ NUOVO: Parametri transcript
    parser.add_argument(
        '--add-transcript',
        action='store_true',
        help='Aggiungi transcript audio dei video usando RapidAPI TikTok Transcript'
    )
    
    parser.add_argument(
        '--transcript-language',
        type=str,
        default='auto',
        help='Lingua per transcript (auto, en, it, es, fr, de, etc.) - default: auto'
    )
    
    # Filtri video
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
    
    # Filtri contenuto (simili a Twitter)
    parser.add_argument(
        '--no-filter',
        action='store_true',
        help='Disabilita filtri qualità contenuto (mantiene tutti i video)'
    )
    
    parser.add_argument(
        '--min-desc-length',
        type=int,
        default=10,
        help='Lunghezza minima descrizione significativa (default: 10 caratteri)'
    )
    
    # Output e configurazione
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
    
    parser.add_argument(
        '--download-videos',
        action='store_true',
        help='Scarica anche i file video (attenzione: richiede molto spazio)'
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version='TikTokScraper v1.1 - Con Transcript Support'
    )
    
    args = parser.parse_args()
    
    # Validazione argomenti
    
    # Gestione verbosity
    if args.quiet and args.verbose:
        parser.error("❌ Non puoi usare --quiet e --verbose insieme!")
    
    if args.verbose:
        args.log_level = 'DEBUG'
    elif args.quiet:
        args.log_level = 'ERROR'
    
    # Validazione modalità ricerca
    if args.auto and not (args.hashtag or args.user or args.trending):
        parser.error("❌ Modalità --auto richiede --hashtag, --user o --trending!")
    
    # Validazione count
    if args.count < 5 or args.count > 100:
        parser.error(f"❌ Count deve essere tra 5 e 100 (ricevuto: {args.count})")
    
    # Validazione durata
    if args.min_duration and args.max_duration:
        if args.min_duration >= args.max_duration:
            parser.error("❌ min-duration deve essere < max-duration")
    
    # Pulizia input
    if args.hashtag:
        args.hashtag = args.hashtag.lstrip('#').strip()
        if not args.hashtag:
            parser.error("❌ Hashtag non può essere vuoto!")
    
    if args.user:
        args.user = args.user.lstrip('@').strip()
        if not args.user:
            parser.error("❌ Username non può essere vuoto!")
    
    # Validazione directory output
    try:
        os.makedirs(args.output_dir, exist_ok=True)
    except Exception as e:
        parser.error(f"❌ Impossibile creare directory {args.output_dir}: {e}")
    
    return args

def get_ms_token(args, logger):
    """Ottieni MS Token da argomenti, .env o chiedi all'utente"""
    ms_token = args.ms_token or os.environ.get("TIKTOK_MS_TOKEN") or os.environ.get("ms_token")
    
    if not ms_token and not args.auto:
        logger.warning("⚠️  MS Token non trovato!")
        logger.info("💡 Per ottenere MS Token:")
        logger.info("   1. Vai su tiktok.com nel browser")
        logger.info("   2. Apri Developer Tools (F12)")
        logger.info("   3. Vai tab Application > Cookies > tiktok.com")
        logger.info("   4. Cerca cookie 'ms_token' e copia il valore")
        
        if not args.auto:
            ms_token = input("\n📝 Inserisci MS Token (o premi Enter per continuare senza): ").strip()
    
    if ms_token:
        logger.info("✅ MS Token configurato!")
    else:
        logger.warning("⚠️  Procedo senza MS Token (possibili limitazioni)")
    
    return ms_token

# ✅ NUOVO: Funzioni transcript
def get_video_transcript(video_url, language='auto', logger=None):
    """Ottiene transcript del video usando RapidAPI TikTok Transcript"""
    
    # Ottieni API key da .env
    rapidapi_key = os.environ.get('RAPIDAPI_KEY') or os.environ.get('TIKTOK_TRANSCRIPT_API_KEY')
    
    if not rapidapi_key:
        logger.warning("⚠️  RAPIDAPI_KEY non trovato in .env - transcript disabilitato")
        return None
    
    try:
        logger.debug(f"🎙️  Richiesta transcript per: {video_url[:50]}...")
        
        # ✅ CORRETTO: Endpoint e metodo dalla documentazione
        url = "https://tiktok-video-transcript.p.rapidapi.com/transcribe"
        
        headers = {
            "X-RapidAPI-Key": rapidapi_key,
            "X-RapidAPI-Host": "tiktok-video-transcript.p.rapidapi.com"
        }
        
        # ✅ CORRETTO: Parametri GET come query string
        params = {
            "url": video_url,
            "language": "eng-US" if language == 'en' else language,
            "timestamps": "false"
        }
        
        # ✅ CORRETTO: GET request invece di POST
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            
            # Estrai transcript dal response
            transcript_text = None
            
            # Gestisci diversi formati di response
            if isinstance(data, dict):
                # Possibili chiavi per il transcript
                transcript_text = (
                    data.get('transcript') or 
                    data.get('text') or 
                    data.get('transcription') or
                    data.get('result', {}).get('transcript') or
                    data.get('data', {}).get('transcript')
                )
            elif isinstance(data, str):
                transcript_text = data
            
            if transcript_text and len(transcript_text.strip()) > 0:
                logger.debug(f"✅ Transcript ottenuto: {len(transcript_text)} caratteri")
                return {
                    'text': transcript_text.strip(),
                    'language': language,
                    'source': 'rapidapi_tiktok_transcript',
                    'available_languages': data.get('available_languages', []),
                    'confidence': data.get('confidence'),
                    'duration': data.get('duration')
                }
            else:
                logger.debug("⚠️  Transcript vuoto o non disponibile")
                return None
                
        elif response.status_code == 429:
            logger.warning("🚫 Rate limit RapidAPI raggiunto per transcript")
            return None
        elif response.status_code == 402:
            logger.warning("💳 Quota RapidAPI esaurita per transcript")
            return None
        else:
            logger.warning(f"⚠️  Errore RapidAPI transcript: {response.status_code}")
            logger.debug(f"Response: {response.text[:200]}")
            return None
            
    except requests.exceptions.Timeout:
        logger.warning("⏱️  Timeout richiesta transcript")
        return None
    except requests.exceptions.RequestException as e:
        logger.warning(f"⚠️  Errore rete transcript: {e}")
        return None
    except Exception as e:
        logger.warning(f"⚠️  Errore generico transcript: {e}")
        return None
    
    """Ottiene transcript del video usando RapidAPI TikTok Transcript"""
    
    # Ottieni API key da .env
    rapidapi_key = os.environ.get('RAPIDAPI_KEY') or os.environ.get('TIKTOK_TRANSCRIPT_API_KEY')
    
    if not rapidapi_key:
        logger.warning("⚠️  RAPIDAPI_KEY non trovato in .env - transcript disabilitato")
        return None
    
    try:
        logger.debug(f"🎙️  Richiesta transcript per: {video_url[:50]}...")
        
        # RapidAPI endpoint
        url = "https://tiktok-video-transcript.p.rapidapi.com/get_transcript"
        
        headers = {
            "X-RapidAPI-Key": rapidapi_key,
            "X-RapidAPI-Host": "tiktok-video-transcript.p.rapidapi.com",
            "Content-Type": "application/json"
        }
        
        # Payload per RapidAPI
        payload = {
            "url": video_url,
            "language": language if language != 'auto' else None
        }
        
        # Rimuovi parametri None
        payload = {k: v for k, v in payload.items() if v is not None}
        
        # Chiamata API con timeout
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            
            # Estrai transcript dal response
            transcript_text = None
            
            # Gestisci diversi formati di response
            if isinstance(data, dict):
                # Possibili chiavi per il transcript
                transcript_text = (
                    data.get('transcript') or 
                    data.get('text') or 
                    data.get('transcription') or
                    data.get('result', {}).get('transcript')
                )
            elif isinstance(data, str):
                transcript_text = data
            
            if transcript_text and len(transcript_text.strip()) > 0:
                logger.debug(f"✅ Transcript ottenuto: {len(transcript_text)} caratteri")
                return {
                    'text': transcript_text.strip(),
                    'language': language,
                    'source': 'rapidapi_tiktok_transcript',
                    'available_languages': data.get('available_languages', []),
                    'confidence': data.get('confidence'),
                    'duration': data.get('duration')
                }
            else:
                logger.debug("⚠️  Transcript vuoto o non disponibile")
                return None
                
        elif response.status_code == 429:
            logger.warning("🚫 Rate limit RapidAPI raggiunto per transcript")
            return None
        elif response.status_code == 402:
            logger.warning("💳 Quota RapidAPI esaurita per transcript")
            return None
        else:
            logger.warning(f"⚠️  Errore RapidAPI transcript: {response.status_code}")
            logger.debug(f"Response: {response.text[:200]}")
            return None
            
    except requests.exceptions.Timeout:
        logger.warning("⏱️  Timeout richiesta transcript")
        return None
    except requests.exceptions.RequestException as e:
        logger.warning(f"⚠️  Errore rete transcript: {e}")
        return None
    except Exception as e:
        logger.warning(f"⚠️  Errore generico transcript: {e}")
        return None

def should_get_transcript(args, video_count, logger):
    """Decide se ottenere transcript in base ai parametri e quota"""
    if not args.add_transcript:
        return False
    
    # Controlla se abbiamo API key
    rapidapi_key = os.environ.get('RAPIDAPI_KEY') or os.environ.get('TIKTOK_TRANSCRIPT_API_KEY')
    if not rapidapi_key:
        logger.warning("⚠️  Transcript richiesto ma RAPIDAPI_KEY mancante")
        return False
    
    # Avviso per piano free
    if video_count > 10:
        logger.warning(f"⚠️  Piano Free RapidAPI limitato (~100 richieste/mese)")
        logger.warning(f"⚠️  Stai processando {video_count} video - potresti esaurire quota")
    
    return True

def clean_description(desc, logger):
    """Pulisce la descrizione del video (simile a clean_tweet_text)"""
    try:
        if not desc:
            return ""
        
        # Rimuove hashtag multipli consecutivi
        desc = re.sub(r'(#\w+\s*){3,}', '', desc)
        # Rimuove menzioni multiple
        desc = re.sub(r'(@\w+\s*){3,}', '', desc)
        # Rimuove spazi multipli
        desc = re.sub(r'\s+', ' ', desc).strip()
        
        return desc
    except Exception as e:
        logger.warning(f"⚠️  Errore pulizia descrizione: {e}")
        return desc

def is_meaningful_description(clean_desc, search_term, min_length, logger):
    """Decide se la descrizione ha abbastanza contenuto (simile a is_meaningful_text)"""
    try:
        if not clean_desc:
            return False
        
        # Rimuovi il termine di ricerca per contare il resto
        if search_term:
            desc_without_term = clean_desc.replace(search_term, "").replace(search_term.lower(), "")
            desc_without_term = desc_without_term.strip()
        else:
            desc_without_term = clean_desc
        
        # Criteri per descrizione "significativa"
        if len(desc_without_term) < min_length:
            return False
        
        # Se è solo hashtag e simboli
        if re.match(r'^[#@\s\W]*$', desc_without_term):
            return False
        
        return True
        
    except Exception as e:
        logger.warning(f"⚠️  Errore valutazione descrizione: {e}")
        return True

def apply_video_filters(video_data, args, search_term, logger):
    """Applica filtri ai video (durata, views, descrizione)"""
    try:
        # Filtro durata
        duration = video_data.get('duration', 0)
        if args.min_duration and duration < args.min_duration:
            logger.debug(f"🗑️  Video {video_data.get('id')} scartato: durata {duration}s < {args.min_duration}s")
            return False
        
        if args.max_duration and duration > args.max_duration:
            logger.debug(f"🗑️  Video {video_data.get('id')} scartato: durata {duration}s > {args.max_duration}s")
            return False
        
        # Filtro visualizzazioni
        stats = video_data.get('stats', {})
        views = stats.get('playCount', 0)
        if args.min_views and views < args.min_views:
            logger.debug(f"🗑️  Video {video_data.get('id')} scartato: views {views} < {args.min_views}")
            return False
        
        # Filtro descrizione (se abilitato)
        if not args.no_filter:
            desc = video_data.get('description', '')
            clean_desc = clean_description(desc, logger)
            
            if not is_meaningful_description(clean_desc, search_term, args.min_desc_length, logger):
                logger.debug(f"🗑️  Video {video_data.get('id')} scartato: descrizione non significativa")
                return False
        
        return True
        
    except Exception as e:
        logger.warning(f"⚠️  Errore applicazione filtri: {e}")
        return True  # In caso di errore, mantieni il video

async def search_hashtag_videos(api, hashtag, count, args, logger):
    """Cerca video per hashtag"""
    try:
        logger.info(f"🔍 Cercando {count} video per hashtag #{hashtag}")
        
        # Controllo transcript
        get_transcript = should_get_transcript(args, count, logger)
        if get_transcript:
            logger.info("🎙️  Transcript abilitato - tempo di elaborazione aumentato")
        
        hashtag_obj = api.hashtag(name=hashtag)
        
        videos = []
        processed = 0
        kept = 0
        
        async for video in hashtag_obj.videos(count=count * 2):  # Richiedi più video per compensare filtri
            processed += 1
            video_dict = video.as_dict
            
            # Estrai dati principali con transcript
            video_data = extract_video_data(
                video_dict, 'hashtag', hashtag, logger, 
                get_transcript=get_transcript, 
                transcript_language=args.transcript_language
            )
            
            # Applica filtri
            if apply_video_filters(video_data, args, hashtag, logger):
                videos.append(video_data)
                kept += 1
                logger.debug(f"✅ Video {video_data['id']} mantenuto")
                
                if kept >= count:
                    break
            
            # Limite massimo per evitare loop infiniti
            if processed >= count * 3:
                break
        
        logger.info(f"📊 Risultati hashtag #{hashtag}:")
        logger.info(f"   - Processati: {processed}")
        logger.info(f"   - Mantenuti: {kept}")
        logger.info(f"   - Scartati: {processed - kept}")
        if get_transcript:
            transcript_count = sum(1 for v in videos if v.get('transcript'))
            logger.info(f"   - Con transcript: {transcript_count}")
        
        return videos
        
    except Exception as e:
        logger.error(f"❌ Errore ricerca hashtag #{hashtag}: {e}")
        return []

async def search_user_videos(api, username, count, args, logger):
    """Cerca video di un utente"""
    try:
        logger.info(f"🔍 Cercando {count} video dell'utente @{username}")
        
        # Controllo transcript
        get_transcript = should_get_transcript(args, count, logger)
        if get_transcript:
            logger.info("🎙️  Transcript abilitato - tempo di elaborazione aumentato")
        
        user_obj = api.user(username)
        
        # Prova a ottenere info utente
        try:
            user_info = await user_obj.info()
            logger.info(f"👤 Utente trovato: {user_info.get('userInfo', {}).get('user', {}).get('nickname', username)}")
        except Exception as e:
            logger.warning(f"⚠️  Impossibile ottenere info utente: {e}")
        
        videos = []
        processed = 0
        kept = 0
        
        async for video in user_obj.videos(count=count * 2):
            processed += 1
            video_dict = video.as_dict
            
            # Estrai dati principali con transcript
            video_data = extract_video_data(
                video_dict, 'user', username, logger,
                get_transcript=get_transcript,
                transcript_language=args.transcript_language
            )
            
            # Applica filtri
            if apply_video_filters(video_data, args, username, logger):
                videos.append(video_data)
                kept += 1
                logger.debug(f"✅ Video {video_data['id']} mantenuto")
                
                if kept >= count:
                    break
            
            if processed >= count * 3:
                break
        
        logger.info(f"📊 Risultati utente @{username}:")
        logger.info(f"   - Processati: {processed}")
        logger.info(f"   - Mantenuti: {kept}")
        logger.info(f"   - Scartati: {processed - kept}")
        if get_transcript:
            transcript_count = sum(1 for v in videos if v.get('transcript'))
            logger.info(f"   - Con transcript: {transcript_count}")
        
        return videos
        
    except Exception as e:
        logger.error(f"❌ Errore ricerca utente @{username}: {e}")
        return []

async def search_trending_videos(api, count, args, logger):
    """Cerca video trending"""
    try:
        logger.info(f"🔍 Cercando {count} video trending")
        
        # Controllo transcript
        get_transcript = should_get_transcript(args, count, logger)
        if get_transcript:
            logger.info("🎙️  Transcript abilitato - tempo di elaborazione aumentato")
        
        videos = []
        processed = 0
        kept = 0
        
        async for video in api.trending.videos(count=count * 2):
            processed += 1
            video_dict = video.as_dict
            
            # Estrai dati principali con transcript
            video_data = extract_video_data(
                video_dict, 'trending', 'trending', logger,
                get_transcript=get_transcript,
                transcript_language=args.transcript_language
            )
            
            # Applica filtri
            if apply_video_filters(video_data, args, 'trending', logger):
                videos.append(video_data)
                kept += 1
                logger.debug(f"✅ Video trending {video_data['id']} mantenuto")
                
                if kept >= count:
                    break
            
            if processed >= count * 3:
                break
        
        logger.info(f"📊 Risultati trending:")
        logger.info(f"   - Processati: {processed}")
        logger.info(f"   - Mantenuti: {kept}")
        logger.info(f"   - Scartati: {processed - kept}")
        if get_transcript:
            transcript_count = sum(1 for v in videos if v.get('transcript'))
            logger.info(f"   - Con transcript: {transcript_count}")
        
        return videos
        
    except Exception as e:
        logger.error(f"❌ Errore ricerca trending: {e}")
        return []

def extract_video_data(video_dict, search_type, search_term, logger, get_transcript=False, transcript_language='auto'):
    """Estrae e normalizza dati dal video TikTok + transcript opzionale"""
    try:
        # Dati base del video
        video_id = video_dict.get('id', 'unknown')
        desc = video_dict.get('desc', '')
        
        # Dati autore
        author = video_dict.get('author', {})
        author_username = author.get('uniqueId', 'unknown')
        author_nickname = author.get('nickname', 'unknown')
        
        # Statistiche
        stats = video_dict.get('stats', {})
        
        # Musica
        music = video_dict.get('music', {})
        
        # Video info
        video_info = video_dict.get('video', {})
        duration = video_info.get('duration', 0)
        
        # Data creazione
        create_time = video_dict.get('createTime', 0)
        try:
            created_at = datetime.fromtimestamp(int(create_time)).isoformat() if create_time else None
        except:
            created_at = None
        
        # Pulisci descrizione
        clean_desc = clean_description(desc, logger)
        
        # ✅ NUOVO: Costruisci URL TikTok pubblico per transcript
        tiktok_public_url = f"https://www.tiktok.com/@{author_username}/video/{video_id}"
        
        # URL video diretto (per download)
        video_direct_url = video_info.get('playAddr', '') or video_dict.get('video', {}).get('downloadAddr', '')
        
        # ✅ NUOVO: Ottieni transcript se richiesto (usa URL pubblico)
        transcript_data = None
        if get_transcript and author_username != 'unknown' and video_id != 'unknown':
            transcript_data = get_video_transcript(tiktok_public_url, transcript_language, logger)
        
        # ✅ MODIFICATO: Struttura dati con transcript e URL pubblico
        video_data = {
            'id': video_id,
            'description': desc,
            'clean_description': clean_desc,
            'desc_length': len(clean_desc),
            'original_desc_length': len(desc),
            'created_at': created_at,
            'author_username': author_username,
            'author_nickname': author_nickname,
            'author_id': author.get('id', 'unknown'),
            'duration': duration,
            'search_type': search_type,
            'search_term': search_term,
            'stats': {
                'views': stats.get('playCount', 0),
                'likes': stats.get('diggCount', 0),
                'comments': stats.get('commentCount', 0),
                'shares': stats.get('shareCount', 0)
            },
            'music': {
                'id': music.get('id', ''),
                'title': music.get('title', ''),
                'author': music.get('authorName', '')
            },
            'hashtags': extract_hashtags_from_desc(desc),
            'video_url': video_direct_url,  # URL diretto per download
            'tiktok_url': tiktok_public_url,  # ✅ NUOVO: URL pubblico TikTok
            'cover_url': video_info.get('cover', ''),
            'meaningful_content': True,
            'filter_applied': True,
            'min_desc_length_used': 10,  # Verrà aggiornato
            # ✅ NUOVO: Campi transcript
            'transcript': transcript_data,
            'transcript_available': bool(transcript_data),
            'transcript_text': transcript_data.get('text') if transcript_data else None,
            'transcript_language': transcript_data.get('language') if transcript_data else None
        }
        
        return video_data
        
    except Exception as e:
        logger.warning(f"⚠️  Errore estrazione dati video: {e}")
        return {
            'id': 'error',
            'description': '',
            'clean_description': '',
            'transcript': None,
            'transcript_available': False,
            'tiktok_url': '',
            'video_url': '',
            'error': str(e)
        }
    """Estrae e normalizza dati dal video TikTok + transcript opzionale"""
    try:
        # Dati base del video
        video_id = video_dict.get('id', 'unknown')
        desc = video_dict.get('desc', '')
        
        # Dati autore
        author = video_dict.get('author', {})
        author_username = author.get('uniqueId', 'unknown')
        author_nickname = author.get('nickname', 'unknown')
        
        # Statistiche
        stats = video_dict.get('stats', {})
        
        # Musica
        music = video_dict.get('music', {})
        
        # Video info
        video_info = video_dict.get('video', {})
        duration = video_info.get('duration', 0)
        
        # Data creazione
        create_time = video_dict.get('createTime', 0)
        try:
            created_at = datetime.fromtimestamp(int(create_time)).isoformat() if create_time else None
        except:
            created_at = None
        
        # Pulisci descrizione
        clean_desc = clean_description(desc, logger)
        
        # URL video per transcript
        video_url = video_info.get('playAddr', '') or video_dict.get('video', {}).get('downloadAddr', '')
        
        # ✅ NUOVO: Ottieni transcript se richiesto
        transcript_data = None
        if get_transcript and video_url:
            transcript_data = get_video_transcript(video_url, transcript_language, logger)
        
        # ✅ MODIFICATO: Struttura dati con transcript
        video_data = {
            'id': video_id,
            'description': desc,
            'clean_description': clean_desc,
            'desc_length': len(clean_desc),
            'original_desc_length': len(desc),
            'created_at': created_at,
            'author_username': author_username,
            'author_nickname': author_nickname,
            'author_id': author.get('id', 'unknown'),
            'duration': duration,
            'search_type': search_type,
            'search_term': search_term,
            'stats': {
                'views': stats.get('playCount', 0),
                'likes': stats.get('diggCount', 0),
                'comments': stats.get('commentCount', 0),
                'shares': stats.get('shareCount', 0)
            },
            'music': {
                'id': music.get('id', ''),
                'title': music.get('title', ''),
                'author': music.get('authorName', '')
            },
            'hashtags': extract_hashtags_from_desc(desc),
            'video_url': video_url,
            'cover_url': video_info.get('cover', ''),
            'meaningful_content': True,
            'filter_applied': True,
            'min_desc_length_used': 10,  # Verrà aggiornato
            # ✅ NUOVO: Campi transcript
            'transcript': transcript_data,
            'transcript_available': bool(transcript_data),
            'transcript_text': transcript_data.get('text') if transcript_data else None,
            'transcript_language': transcript_data.get('language') if transcript_data else None
        }
        
        return video_data
        
    except Exception as e:
        logger.warning(f"⚠️  Errore estrazione dati video: {e}")
        return {
            'id': 'error',
            'description': '',
            'clean_description': '',
            'transcript': None,
            'transcript_available': False,
            'error': str(e)
        }

def extract_hashtags_from_desc(description):
    """Estrae hashtag dalla descrizione"""
    try:
        hashtags = re.findall(r'#(\w+)', description)
        return hashtags
    except:
        return []

def save_videos(videos, search_type, search_term, args, logger):
    """Salva video in JSON con nome incrementale"""
    if not videos:
        logger.warning("⚠️  Nessun video da salvare")
        return None
    
    try:
        # ✅ NUOVO: Funzione per nome file incrementale
        def get_next_filename(output_dir, prefix="tiktok_scraper", extension=".json"):
            """Trova il prossimo numero disponibile per il file"""
            counter = 1
            while True:
                filename = f"{output_dir}/{prefix}_#{counter}{extension}"
                if not os.path.exists(filename):
                    return filename, counter
                counter += 1
        
        # ✅ NUOVO: Nome file incrementale
        base_prefix = args.output_prefix if args.output_prefix else "tiktok_scraper"
        filename, file_number = get_next_filename(args.output_dir, base_prefix)
        
        # Statistiche sui video
        total_duration = sum(video.get('duration', 0) for video in videos)
        total_views = sum(video.get('stats', {}).get('views', 0) for video in videos)
        total_likes = sum(video.get('stats', {}).get('likes', 0) for video in videos)
        
        # ✅ NUOVO: Statistiche transcript
        videos_with_transcript = sum(1 for video in videos if video.get('transcript_available'))
        total_transcript_chars = sum(len(video.get('transcript_text', '') or '') for video in videos)
        
        # Hashtag più frequenti
        all_hashtags = []
        for video in videos:
            all_hashtags.extend(video.get('hashtags', []))
        
        hashtag_freq = {}
        for hashtag in all_hashtags:
            hashtag_freq[hashtag] = hashtag_freq.get(hashtag, 0) + 1
        
        top_hashtags = dict(sorted(hashtag_freq.items(), key=lambda x: x[1], reverse=True)[:10])
        
        # ✅ MODIFICATO: Prepara i dati da salvare con transcript
        data = {
            'metadata': {
                'search_type': search_type,
                'search_term': search_term,
                'collection_time': datetime.now().isoformat(),
                'total_videos': len(videos),
                'script_version': 'tiktok_scraper_v1.1_with_transcript',
                'filters_applied': {
                    'content_filter_applied': not args.no_filter,
                    'min_desc_length': args.min_desc_length,
                    'min_duration': args.min_duration,
                    'max_duration': args.max_duration,
                    'min_views': args.min_views
                },
                'transcript_config': {
                    'transcript_enabled': args.add_transcript,
                    'transcript_language': args.transcript_language,
                    'videos_with_transcript': videos_with_transcript,
                    'transcript_success_rate': round((videos_with_transcript / len(videos)) * 100, 1) if videos else 0
                },
                'output_info': {
                    'directory': args.output_dir,
                    'prefix': args.output_prefix,
                    'filename': filename
                },
                'statistics': {
                    'total_duration_seconds': total_duration,
                    'average_duration': round(total_duration / len(videos), 1) if videos else 0,
                    'total_views': total_views,
                    'total_likes': total_likes,
                    'average_views': round(total_views / len(videos), 1) if videos else 0,
                    'top_hashtags': top_hashtags,
                    'total_hashtags_found': len(set(all_hashtags)),
                    'total_transcript_characters': total_transcript_chars,
                    'average_transcript_length': round(total_transcript_chars / videos_with_transcript, 1) if videos_with_transcript else 0
                }
            },
            'videos': videos
        }
        
        # Salva in JSON
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        
        logger.info(f"💾 File salvato con successo: {filename}")
        logger.info(f"📊 Statistiche salvate:")
        logger.info(f"   - Video totali: {len(videos)}")
        logger.info(f"   - Durata totale: {total_duration} secondi")
        logger.info(f"   - Visualizzazioni totali: {total_views:,}")
        logger.info(f"   - Like totali: {total_likes:,}")
        if args.add_transcript:
            logger.info(f"   - Video con transcript: {videos_with_transcript}/{len(videos)}")
            logger.info(f"   - Caratteri transcript: {total_transcript_chars:,}")
        
        return filename
        
    except Exception as e:
        logger.error(f"❌ Errore salvataggio: {e}")
        return None

def print_summary(videos, search_type, search_term, logger):
    """Stampa riassunto dettagliato dei video raccolti (simile a print_summary)"""
    if not videos:
        return
    
    try:
        logger.info(f"📊 RIASSUNTO FINALE - {search_type.upper()}: {search_term}")
        logger.info("=" * 60)
        
        # Statistiche generali
        total_videos = len(videos)
        total_duration = sum(video.get('duration', 0) for video in videos)
        total_views = sum(video.get('stats', {}).get('views', 0) for video in videos)
        
        logger.info(f"📈 Video raccolti: {total_videos}")
        logger.info(f"⏱️  Durata totale: {total_duration} secondi ({total_duration/60:.1f} minuti)")
        logger.info(f"👀 Visualizzazioni totali: {total_views:,}")
        
        # ✅ NUOVO: Statistiche transcript
        videos_with_transcript = sum(1 for video in videos if video.get('transcript_available'))
        if videos_with_transcript > 0:
            logger.info(f"🎙️  Video con transcript: {videos_with_transcript}/{total_videos} ({(videos_with_transcript/total_videos)*100:.1f}%)")
            
            total_transcript_chars = sum(len(video.get('transcript_text', '') or '') for video in videos)
            avg_transcript_length = total_transcript_chars / videos_with_transcript if videos_with_transcript else 0
            logger.info(f"📝 Lunghezza media transcript: {avg_transcript_length:.0f} caratteri")
        
        # Statistiche descrizioni
        avg_desc_length = sum(video.get('desc_length', 0) for video in videos) / total_videos
        logger.info(f"📏 Lunghezza media descrizione: {avg_desc_length:.1f} caratteri")
        
        # Top 3 video più visti
        top_videos = sorted(videos, key=lambda x: x.get('stats', {}).get('views', 0), reverse=True)[:3]
        
        logger.info(f"🏆 Top 3 video più visti:")
        for i, video in enumerate(top_videos):
            views = video.get('stats', {}).get('views', 0)
            author = video.get('author_username', 'unknown')
            desc_preview = video.get('clean_description', '')[:60] + "..." if len(video.get('clean_description', '')) > 60 else video.get('clean_description', '')
            transcript_status = "🎙️" if video.get('transcript_available') else "❌"
            logger.info(f"{i+1}. ({views:,} views) @{author} {transcript_status}: {desc_preview}")
        
        # Filtri applicati
        sample_video = videos[0] if videos else {}
        filters_applied = []
        
        if sample_video.get('filter_applied', True):
            filters_applied.append(f"Descrizione significativa")
        else:
            filters_applied.append("Descrizione: NESSUN FILTRO")
        
        filters_applied.append(f"Ricerca: {search_type}")
        
        if videos_with_transcript > 0:
            filters_applied.append("Transcript: ATTIVO")
        
        logger.info(f"🎯 Filtri applicati: {', '.join(filters_applied)}")
        
    except Exception as e:
        logger.error(f"⚠️  Errore nel riassunto: {e}")

async def main():
    """Funzione principale - TikTok Scraper con Transcript"""
    # Parse argomenti
    args = parse_arguments()
    
    # Setup logger
    logger = setup_logger(args.log_level)
    
    logger.info("🎵 TIKTOK SCRAPER - v1.1")
    logger.info("🎯 Pattern simile a Twitter scraper")
    logger.info("🔧 Basato su TikTok-Api (davidteather)")
    logger.info("🎙️  Con supporto transcript RapidAPI")
    logger.info("=" * 60)
    
    # Dry run check
    if args.dry_run:
        logger.info("🧪 DRY RUN MODE - Test configurazione")
        logger.info(f"   - Modalità: {args.hashtag and 'hashtag' or args.user and 'user' or args.trending and 'trending' or 'non specificata'}")
        logger.info(f"   - Target: {args.hashtag or args.user or 'trending' if args.trending else 'N/A'}")
        logger.info(f"   - Count: {args.count}")
        logger.info(f"   - Filtri: {'DISATTIVATI' if args.no_filter else 'ATTIVI'}")
        logger.info(f"   - Transcript: {'ATTIVO' if args.add_transcript else 'DISATTIVO'}")
        logger.info(f"   - Output: {args.output_dir}/{args.output_prefix}...")
        logger.info("✅ Configurazione valida! Rimuovi --dry-run per eseguire.")
        return
    
    try:
        # 1. Ottieni MS Token
        ms_token = get_ms_token(args, logger)
        
        # ✅ NUOVO: Controllo API key transcript
        if args.add_transcript:
            rapidapi_key = os.environ.get('RAPIDAPI_KEY') or os.environ.get('TIKTOK_TRANSCRIPT_API_KEY')
            if rapidapi_key:
                logger.info("✅ RapidAPI key trovata - transcript abilitato")
            else:
                logger.warning("⚠️  --add-transcript specificato ma RAPIDAPI_KEY mancante nel .env")
                logger.warning("⚠️  Continuo senza transcript")
                args.add_transcript = False
        
        # 2. Determina modalità di ricerca
        search_type = None
        search_term = None
        
        if args.hashtag:
            search_type = 'hashtag'
            search_term = args.hashtag
        elif args.user:
            search_type = 'user'
            search_term = args.user
        elif args.trending:
            search_type = 'trending'
            search_term = 'trending'
        else:
            # Modalità interattiva
            if not args.auto:
                print("\n" + "=" * 60)
                print("🎵 TIKTOK SCRAPER - Modalità Interattiva")
                print("=" * 60)
                print("Scegli modalità di ricerca:")
                print("1. Hashtag - Cerca video per hashtag")
                print("2. User - Cerca video di un utente")
                print("3. Trending - Video trending di TikTok")
                
                choice = input("\nScegli (1/2/3): ").strip()
                
                if choice == '1':
                    hashtag = input("📝 Inserisci hashtag (senza #): ").strip().lstrip('#')
                    if hashtag:
                        search_type = 'hashtag'
                        search_term = hashtag
                        args.hashtag = hashtag
                elif choice == '2':
                    user = input("📝 Inserisci username (senza @): ").strip().lstrip('@')
                    if user:
                        search_type = 'user'
                        search_term = user
                        args.user = user
                elif choice == '3':
                    search_type = 'trending'
                    search_term = 'trending'
                    args.trending = True
                
                if not search_type:
                    logger.error("❌ Nessuna modalità di ricerca valida selezionata!")
                    sys.exit(1)
            else:
                logger.error("❌ Modalità --auto richiede --hashtag, --user o --trending!")
                sys.exit(1)
        
        # 3. Log configurazione finale
        logger.info(f"🎯 Configurazione finale:")
        logger.info(f"   - Modalità: {search_type}")
        logger.info(f"   - Target: {search_term}")
        logger.info(f"   - Quantità: {args.count} video")
        logger.info(f"   - Browser: {args.browser}")
        
        filter_status = "DISATTIVATI" if args.no_filter else f"ATTIVI (min {args.min_desc_length} char)"
        logger.info(f"   - Filtri contenuto: {filter_status}")
        
        # ✅ NUOVO: Log configurazione transcript
        if args.add_transcript:
            logger.info(f"   - Transcript: ATTIVO (lingua: {args.transcript_language})")
            logger.info(f"   - ⚠️  Tempo elaborazione: +10-30s per video")
        else:
            logger.info(f"   - Transcript: DISATTIVO")
        
        if args.min_duration or args.max_duration:
            duration_filter = f"Durata: {args.min_duration or 0}-{args.max_duration or '∞'}s"
            logger.info(f"   - {duration_filter}")
        
        if args.min_views:
            logger.info(f"   - Views minime: {args.min_views:,}")
        
        logger.info(f"   - Output: {args.output_dir}/{args.output_prefix}...")
        
        # 4. Crea TikTok API session
        logger.info("🔧 Inizializzazione TikTok API...")
        
        async with TikTokApi() as api:
            # Configura sessioni
            session_params = {
                'num_sessions': 1,
                'sleep_after': 3,
                'browser': args.browser
            }
            
            # Aggiungi MS token se disponibile
            if ms_token:
                session_params['ms_tokens'] = [ms_token]
            
            # Configura proxy se richiesto
            if args.use_proxy:
                proxy_url = os.environ.get('PROXY_URL')
                if proxy_url:
                    session_params['proxies'] = [proxy_url]
                    logger.info(f"🌐 Proxy configurato: {proxy_url[:20]}...")
                else:
                    logger.warning("⚠️  --use-proxy specificato ma PROXY_URL non trovato in .env")
            
            try:
                await api.create_sessions(**session_params)
                logger.info("✅ Sessione TikTok API creata con successo!")
            except Exception as e:
                logger.error(f"❌ Errore creazione sessione TikTok: {e}")
                logger.info("💡 Suggerimenti:")
                logger.info("   - Installa browser: python -m playwright install")
                logger.info("   - Verifica MS Token (dai cookie di tiktok.com)")
                logger.info("   - Prova con proxy: --use-proxy")
                logger.info("   - Controlla connessione internet")
                sys.exit(1)
            
            # 5. Esegui ricerca in base alla modalità
            videos = []
            
            if search_type == 'hashtag':
                videos = await search_hashtag_videos(api, search_term, args.count, args, logger)
            elif search_type == 'user':
                videos = await search_user_videos(api, search_term, args.count, args, logger)
            elif search_type == 'trending':
                videos = await search_trending_videos(api, args.count, args, logger)
            
            # 6. Aggiorna metadati filtri nei video
            for video in videos:
                video['filter_applied'] = not args.no_filter
                video['min_desc_length_used'] = args.min_desc_length
            
            # 7. Salva e mostra risultati
            if videos:
                filename = save_videos(videos, search_type, search_term, args, logger)
                print_summary(videos, search_type, search_term, logger)
                
                logger.info("🎉 SCRAPING COMPLETATO CON SUCCESSO!")
                logger.info(f"📁 File: {filename}")
                logger.info(f"📊 Video TikTok raccolti: {len(videos)}")
                
                # ✅ NUOVO: Messaggi specifici per transcript
                if args.add_transcript:
                    transcript_count = sum(1 for v in videos if v.get('transcript_available'))
                    logger.info(f"🎙️  Transcript ottenuti: {transcript_count}/{len(videos)}")
                
                # Messaggi specifici per modalità
                if search_type == 'hashtag':
                    logger.info(f"🏷️  Hashtag #{search_term} analizzato")
                elif search_type == 'user':
                    logger.info(f"👤 Profilo @{search_term} analizzato")
                elif search_type == 'trending':
                    logger.info("🔥 Video trending analizzati")
                
                # Info download video
                if args.download_videos:
                    logger.info("📥 Download video abilitato (funzionalità futura)")
                
            else:
                # Messaggi di errore informativi
                logger.warning(f"😔 Nessun video trovato per {search_type}: {search_term}")
                
                logger.info("💡 Suggerimenti per migliorare i risultati:")
                
                if search_type == 'hashtag':
                    logger.info(f"   - Verifica che #{search_term} sia un hashtag popolare")
                    logger.info("   - Prova hashtag più generici (es: funny, dance, tech)")
                elif search_type == 'user':
                    logger.info(f"   - Verifica che @{search_term} esista e abbia video pubblici")
                    logger.info("   - Controlla lo spelling del username")
                elif search_type == 'trending':
                    logger.info("   - I trending potrebbero essere limitati geograficamente")
                
                if not args.no_filter:
                    logger.info(f"   - Abbassa soglia: --min-desc-length 5 (ora: {args.min_desc_length})")
                    logger.info("   - Disabilita filtri: --no-filter")
                
                if args.min_views:
                    logger.info(f"   - Riduci --min-views (ora: {args.min_views:,})")
                
                logger.info("   - Verifica MS Token e configurazione")
                logger.info("   - Prova con proxy: --use-proxy")
                logger.info("   - TikTok potrebbe aver bloccato le richieste")
                
    except KeyboardInterrupt:
        logger.info("⏹️  Operazione interrotta dall'utente")
        sys.exit(130)  # Standard exit code for Ctrl+C
    except Exception as e:
        logger.error(f"❌ Errore generale: {e}")
        logger.debug(f"🔍 Stack trace completo:", exc_info=True)
        
        # Suggerimenti in base al tipo di errore
        error_str = str(e).lower()
        
        if "playwright" in error_str:
            logger.info("💡 Errore Playwright - esegui: python -m playwright install")
        elif "ms_token" in error_str or "session" in error_str:
            logger.info("💡 Problema MS Token - ottieni token dai cookie tiktok.com")
        elif "blocked" in error_str or "bot" in error_str:
            logger.info("💡 TikTok ha rilevato bot - prova con proxy diverso")
        elif "timeout" in error_str:
            logger.info("💡 Timeout - TikTok potrebbe essere lento o irraggiungibile")
        elif "rapidapi" in error_str:
            logger.info("💡 Problema RapidAPI - controlla RAPIDAPI_KEY o quota")
        else:
            logger.info("🔧 Riprova o controlla la configurazione")
        
        sys.exit(1)

if __name__ == "__main__":
    # Esegui funzione asincrona
    asyncio.run(main())