#!/usr/bin/env python3
"""
TikTok Scraper - Versione Refactorizzata
Usa moduli core per eliminare duplicazioni, mantiene logiche specifiche TikTok
"""

import os
import json
import re
import sys
import asyncio
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

# ✅ IMPORT DAI MODULI CORE (sostituiscono funzioni duplicate)
from src.core.logger import setup_tiktok_logger
from src.core.text_utils import (
    extract_hashtags_from_desc, clean_description, 
    is_meaningful_description
)
from src.core.cli_utils import (
    setup_tiktok_argparse, validate_common_arguments,
    validate_count_argument, clean_hashtag_input, clean_username_input,
    check_auto_mode_requirements, print_configuration_summary
)

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


# ================================
# FUNZIONI TRANSCRIPT (SPECIFICHE TIKTOK)
# ================================

def get_video_transcript(video_url, language='auto', logger=None):
    """Ottiene transcript del video usando RapidAPI TikTok Transcript"""
    rapidapi_key = os.environ.get('RAPIDAPI_KEY') or os.environ.get('TIKTOK_TRANSCRIPT_API_KEY')
    
    if not rapidapi_key:
        logger.warning("⚠️  RAPIDAPI_KEY non trovato in .env - transcript disabilitato")
        return None
    
    try:
        logger.debug(f"🎙️  Richiesta transcript per: {video_url[:50]}...")
        
        url = "https://tiktok-video-transcript.p.rapidapi.com/transcribe"
        
        headers = {
            "X-RapidAPI-Key": rapidapi_key,
            "X-RapidAPI-Host": "tiktok-video-transcript.p.rapidapi.com"
        }
        
        params = {
            "url": video_url,
            "language": "eng-US" if language == 'en' else language,
            "timestamps": "false"
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            
            transcript_text = None
            if isinstance(data, dict):
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
                    'source': 'rapidapi_tiktok_transcript'
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
            return None
            
    except requests.exceptions.Timeout:
        logger.warning("⏱️  Timeout richiesta transcript")
        return None
    except Exception as e:
        logger.warning(f"⚠️  Errore generico transcript: {e}")
        return None


def should_get_transcript(args, video_count, logger):
    """Decide se ottenere transcript in base ai parametri e quota"""
    if not args.add_transcript:
        return False
    
    rapidapi_key = os.environ.get('RAPIDAPI_KEY') or os.environ.get('TIKTOK_TRANSCRIPT_API_KEY')
    if not rapidapi_key:
        logger.warning("⚠️  Transcript richiesto ma RAPIDAPI_KEY mancante")
        return False
    
    if video_count > 10:
        logger.warning(f"⚠️  Piano Free RapidAPI limitato (~100 richieste/mese)")
        logger.warning(f"⚠️  Stai processando {video_count} video - potresti esaurire quota")
    
    return True


# ================================
# FUNZIONI RILEVANZA (SPECIFICHE TIKTOK)
# ================================

def calculate_hashtag_relevance(search_term, video_hashtags, logger):
    """Calcola rilevanza basata su hashtag del video"""
    try:
        if not video_hashtags or not search_term:
            return 0.0
        
        search_term_lower = search_term.lower().strip()
        matches = 0
        partial_matches = 0
        
        for hashtag in video_hashtags:
            hashtag_lower = hashtag.lower().strip()
            
            # Match esatto
            if search_term_lower == hashtag_lower:
                matches += 2  # Peso maggiore per match esatto
            # Match parziale (search_term contenuto nell'hashtag)
            elif search_term_lower in hashtag_lower:
                matches += 1.5
            # Match parziale inverso (hashtag contenuto nel search_term)
            elif hashtag_lower in search_term_lower:
                partial_matches += 1
        
        # Calcola score (normalizzato tra 0 e 1)
        total_score = matches + (partial_matches * 0.5)
        max_possible_score = len(video_hashtags) * 2  # Peso massimo per tutti hashtag
        
        hashtag_score = min(total_score / max_possible_score, 1.0) if max_possible_score > 0 else 0.0
        
        logger.debug(f"🏷️  Hashtag relevance: {hashtag_score:.2f} (matches: {matches}, partial: {partial_matches})")
        return hashtag_score
        
    except Exception as e:
        logger.warning(f"⚠️  Errore calcolo hashtag relevance: {e}")
        return 0.0


def calculate_description_relevance(search_term, description, logger):
    """Calcola rilevanza basata sulla descrizione del video"""
    try:
        if not description or not search_term:
            return 0.0
        
        search_term_lower = search_term.lower().strip()
        description_lower = description.lower()
        
        # Conta occorrenze del termine di ricerca nella descrizione
        search_words = search_term_lower.split()
        matches = 0
        
        for word in search_words:
            word_count = description_lower.count(word)
            matches += word_count
        
        # Normalizza in base alla lunghezza della descrizione
        description_words = len(description_lower.split())
        
        if description_words == 0:
            return 0.0
        
        # Score normalizzato (max 1.0)
        description_score = min(matches / max(description_words * 0.1, 1), 1.0)
        
        logger.debug(f"📝 Description relevance: {description_score:.2f} (matches: {matches}, words: {description_words})")
        return description_score
        
    except Exception as e:
        logger.warning(f"⚠️  Errore calcolo description relevance: {e}")
        return 0.0


def calculate_video_relevance(search_term, video_data, relevance_threshold, logger):
    """Calcola score di rilevanza complessivo del video"""
    try:
        hashtags = video_data.get('hashtags', [])
        description = video_data.get('description', '')
        
        # Calcola score per hashtag e descrizione
        hashtag_score = calculate_hashtag_relevance(search_term, hashtags, logger)
        description_score = calculate_description_relevance(search_term, description, logger)
        
        # Peso combinato: hashtag hanno più importanza (60%) della descrizione (40%)
        relevance_score = (hashtag_score * 0.6) + (description_score * 0.4)
        
        # Usa la soglia configurabile
        is_relevant = relevance_score >= relevance_threshold
        
        logger.debug(f"🎯 Final relevance: {relevance_score:.3f} ({'✅ RELEVANT' if is_relevant else '❌ NOT RELEVANT'})")
        
        return {
            'relevance_score': round(relevance_score, 3),
            'is_relevant': is_relevant,
            'hashtag_score': round(hashtag_score, 3),
            'description_score': round(description_score, 3)
        }
        
    except Exception as e:
        logger.warning(f"⚠️  Errore calcolo rilevanza video: {e}")
        return {
            'relevance_score': 0.0,
            'is_relevant': False,
            'hashtag_score': 0.0,
            'description_score': 0.0
        }


# ================================
# FUNZIONI COMMENTI (SPECIFICHE TIKTOK)
# ================================

async def get_video_comments(api, video_id, max_comments=10, logger=None):
    """Recupera i commenti di un video TikTok"""
    try:
        if not video_id or video_id == 'unknown':
            logger.debug("⚠️  Video ID mancante per commenti")
            return []
        
        logger.debug(f"💬 Recuperando commenti per video {video_id}...")
        
        # Crea oggetto video per ottenere commenti
        video_obj = api.video(id=video_id)
        
        comments_list = []
        comment_count = 0
        
        # Itera sui commenti del video
        async for comment in video_obj.comments(count=max_comments * 2):  # Richiedi più commenti per sicurezza
            try:
                comment_dict = comment.as_dict
                comment_text = comment_dict.get('text', '').strip()
                
                # Filtra commenti vuoti o troppo corti
                if comment_text and len(comment_text) >= 2:
                    comment_obj = {
                        "text": comment_text
                    }
                    comments_list.append(comment_obj)
                    comment_count += 1
                    
                    # Fermati quando raggiungi il limite
                    if comment_count >= max_comments:
                        break
                        
            except Exception as e:
                logger.debug(f"⚠️  Errore elaborazione singolo commento: {e}")
                continue
        
        logger.debug(f"✅ Raccolti {len(comments_list)} commenti per video {video_id}")
        return comments_list
        
    except Exception as e:
        logger.debug(f"⚠️  Errore recupero commenti per video {video_id}: {e}")
        return []


def should_get_comments(args, video_count, logger):
    """Decide se recuperare commenti in base ai parametri"""
    if not args.add_comments:
        return False
    
    if video_count > 20:
        logger.warning(f"⚠️  Recupero commenti per {video_count} video - potrebbe essere lento")
        logger.warning(f"⚠️  Considera di ridurre --count per test più veloci")
    
    return True


# ================================
# FUNZIONI UTILITY (SPECIFICHE TIKTOK)
# ================================

def apply_video_filters(video_data, args, search_term, logger):
    """Applica filtri ai video (durata, views, descrizione, rilevanza)"""
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
        views = stats.get('views', 0)
        if args.min_views and views < args.min_views:
            logger.debug(f"🗑️  Video {video_data.get('id')} scartato: views {views} < {args.min_views}")
            return False
        
        # Filtro descrizione (se abilitato)
        if not args.no_filter:
            desc = video_data.get('description', '')
            # ✅ USA MODULO CORE per pulizia descrizione
            clean_desc = clean_description(desc, logger)
            
            # ✅ USA MODULO CORE per valutazione significatività
            if not is_meaningful_description(clean_desc, search_term, args.min_desc_length, logger):
                logger.debug(f"🗑️  Video {video_data.get('id')} scartato: descrizione non significativa")
                return False
        
        # Filtro rilevanza
        is_relevant = video_data.get('is_relevant', True)
        if not is_relevant:
            relevance_score = video_data.get('relevance_score', 0.0)
            logger.debug(f"🗑️  Video {video_data.get('id')} scartato: rilevanza {relevance_score:.3f} < {args.relevance_threshold}")
            return False
        
        return True
        
    except Exception as e:
        logger.warning(f"⚠️  Errore applicazione filtri: {e}")
        return True  # In caso di errore, mantieni il video


def extract_video_data(video_dict, search_type, search_term, logger, get_transcript=False, transcript_language='auto', relevance_threshold=0.45):
    """Estrae e normalizza dati dal video TikTok"""
    try:
        # Dati base del video
        video_id = video_dict.get('id', 'unknown')
        desc = video_dict.get('desc', '')
        
        # Dati autore
        author = video_dict.get('author', {})
        author_username = author.get('uniqueId', 'unknown')
        
        # Statistiche
        stats = video_dict.get('stats', {})
        
        # Video info
        video_info = video_dict.get('video', {})
        duration = video_info.get('duration', 0)
        
        # Data creazione
        create_time = video_dict.get('createTime', 0)
        try:
            created_at = datetime.fromtimestamp(int(create_time)).isoformat() if create_time else None
        except:
            created_at = None
        
        # URL TikTok pubblico
        tiktok_public_url = f"https://www.tiktok.com/@{author_username}/video/{video_id}"
        
        # Ottieni transcript se richiesto
        transcript_text = None
        if get_transcript and author_username != 'unknown' and video_id != 'unknown':
            transcript_data = get_video_transcript(tiktok_public_url, transcript_language, logger)
            if transcript_data:
                transcript_text = transcript_data.get('text')
        
        # ✅ USA MODULO CORE per estrazione hashtag
        hashtags = extract_hashtags_from_desc(desc)
        
        # Struttura dati TikTok
        video_data = {
            'id': video_id,
            'description': desc,
            'created_at': created_at,
            'author_username': author_username,
            'duration': duration,
            'search_term': search_term,
            'stats': {
                'views': stats.get('playCount', 0),
                'likes': stats.get('diggCount', 0),
                'comments': stats.get('commentCount', 0),
                'shares': stats.get('shareCount', 0)
            },
            'hashtags': hashtags,
            'tiktok_url': tiktok_public_url,
            'transcript_text': transcript_text,
            'transcript_available': bool(transcript_text),
            'comments': [],  # Sarà popolato con oggetti [{"text": "..."}, {"text": "..."}]
            'comments_count': 0,
            'comments_retrieved': False
        }
        
        # Calcola rilevanza del video
        relevance_data = calculate_video_relevance(search_term, video_data, relevance_threshold, logger)
        video_data.update(relevance_data)
        
        return video_data
        
    except Exception as e:
        logger.warning(f"⚠️  Errore estrazione dati video: {e}")
        return {
            'id': 'error',
            'description': '',
            'transcript_text': None,
            'transcript_available': False,
            'tiktok_url': '',
            'comments': [],
            'comments_count': 0,
            'comments_retrieved': False,
            'error': str(e)
        }


# ================================
# FUNZIONI DI RICERCA (SPECIFICHE TIKTOK)
# ================================

async def search_hashtag_videos(api, hashtag, count, args, logger):
    """Cerca video per hashtag"""
    try:
        logger.info(f"🔍 Cercando {count} video per hashtag #{hashtag}")
        
        # Controllo transcript e commenti
        get_transcript = should_get_transcript(args, count, logger)
        get_comments = should_get_comments(args, count, logger)
        
        if get_transcript:
            logger.info("🎙️  Transcript abilitato - tempo di elaborazione aumentato")
        if get_comments:
            logger.info(f"💬 Commenti abilitati (max {args.max_comments} per video) - tempo di elaborazione aumentato")
        
        hashtag_obj = api.hashtag(name=hashtag)
        
        videos = []
        processed = 0
        kept = 0
        
        async for video in hashtag_obj.videos(count=count * 3):  # Richiedi più video per compensare filtri
            processed += 1
            video_dict = video.as_dict
            
            # Estrai dati principali
            video_data = extract_video_data(
                video_dict, 'hashtag', hashtag, logger, 
                get_transcript=get_transcript, 
                transcript_language=args.transcript_language,
                relevance_threshold=args.relevance_threshold
            )
            
            # Applica filtri
            if apply_video_filters(video_data, args, hashtag, logger):
                # Aggiungi commenti se richiesto
                if get_comments:
                    try:
                        comments = await get_video_comments(api, video_data['id'], args.max_comments, logger)
                        video_data['comments'] = comments
                        video_data['comments_count'] = len(comments)
                        video_data['comments_retrieved'] = True
                    except Exception as e:
                        logger.debug(f"⚠️  Errore recupero commenti per video {video_data['id']}: {e}")
                        video_data['comments'] = []
                        video_data['comments_count'] = 0
                        video_data['comments_retrieved'] = False
                
                videos.append(video_data)
                kept += 1
                logger.debug(f"✅ Video {video_data['id']} mantenuto")
                
                if kept >= count:
                    break
            
            # Limite massimo per evitare loop infiniti
            if processed >= count * 5:
                break
        
        logger.info(f"📊 Risultati hashtag #{hashtag}:")
        logger.info(f"   - Processati: {processed}")
        logger.info(f"   - Mantenuti: {kept}")
        logger.info(f"   - Scartati: {processed - kept}")
        
        if get_transcript:
            transcript_count = sum(1 for v in videos if v.get('transcript_available'))
            logger.info(f"   - Con transcript: {transcript_count}")
            
        if get_comments:
            comments_count = sum(1 for v in videos if v.get('comments_retrieved'))
            total_comments = sum(v.get('comments_count', 0) for v in videos)
            logger.info(f"   - Con commenti: {comments_count}")
            logger.info(f"   - Commenti totali: {total_comments}")
        
        return videos
        
    except Exception as e:
        logger.error(f"❌ Errore ricerca hashtag #{hashtag}: {e}")
        return []


async def search_user_videos(api, username, count, args, logger):
    """Cerca video di un utente"""
    try:
        logger.info(f"🔍 Cercando {count} video dell'utente @{username}")
        
        # Controllo transcript e commenti
        get_transcript = should_get_transcript(args, count, logger)
        get_comments = should_get_comments(args, count, logger)
        
        if get_transcript:
            logger.info("🎙️  Transcript abilitato - tempo di elaborazione aumentato")
        if get_comments:
            logger.info(f"💬 Commenti abilitati (max {args.max_comments} per video) - tempo di elaborazione aumentato")
        
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
        
        async for video in user_obj.videos(count=count * 3):
            processed += 1
            video_dict = video.as_dict
            
            # Estrai dati principali
            video_data = extract_video_data(
                video_dict, 'user', username, logger,
                get_transcript=get_transcript,
                transcript_language=args.transcript_language,
                relevance_threshold=args.relevance_threshold
            )
            
            # Applica filtri
            if apply_video_filters(video_data, args, username, logger):
                # Aggiungi commenti se richiesto
                if get_comments:
                    try:
                        comments = await get_video_comments(api, video_data['id'], args.max_comments, logger)
                        video_data['comments'] = comments
                        video_data['comments_count'] = len(comments)
                        video_data['comments_retrieved'] = True
                    except Exception as e:
                        logger.debug(f"⚠️  Errore recupero commenti per video {video_data['id']}: {e}")
                        video_data['comments'] = []
                        video_data['comments_count'] = 0
                        video_data['comments_retrieved'] = False
                
                videos.append(video_data)
                kept += 1
                logger.debug(f"✅ Video {video_data['id']} mantenuto")
                
                if kept >= count:
                    break
            
            if processed >= count * 5:
                break
        
        logger.info(f"📊 Risultati utente @{username}:")
        logger.info(f"   - Processati: {processed}")
        logger.info(f"   - Mantenuti: {kept}")
        logger.info(f"   - Scartati: {processed - kept}")
        
        if get_transcript:
            transcript_count = sum(1 for v in videos if v.get('transcript_available'))
            logger.info(f"   - Con transcript: {transcript_count}")
            
        if get_comments:
            comments_count = sum(1 for v in videos if v.get('comments_retrieved'))
            total_comments = sum(v.get('comments_count', 0) for v in videos)
            logger.info(f"   - Con commenti: {comments_count}")
            logger.info(f"   - Commenti totali: {total_comments}")
        
        return videos
        
    except Exception as e:
        logger.error(f"❌ Errore ricerca utente @{username}: {e}")
        return []


async def search_trending_videos(api, count, args, logger):
    """Cerca video trending"""
    try:
        logger.info(f"🔍 Cercando {count} video trending")
        
        # Controllo transcript e commenti
        get_transcript = should_get_transcript(args, count, logger)
        get_comments = should_get_comments(args, count, logger)
        
        if get_transcript:
            logger.info("🎙️  Transcript abilitato - tempo di elaborazione aumentato")
        if get_comments:
            logger.info(f"💬 Commenti abilitati (max {args.max_comments} per video) - tempo di elaborazione aumentato")
        
        videos = []
        processed = 0
        kept = 0
        
        async for video in api.trending.videos(count=count * 3):
            processed += 1
            video_dict = video.as_dict
            
            # Estrai dati principali
            video_data = extract_video_data(
                video_dict, 'trending', 'trending', logger,
                get_transcript=get_transcript,
                transcript_language=args.transcript_language,
                relevance_threshold=args.relevance_threshold
            )
            
            # Applica filtri
            if apply_video_filters(video_data, args, 'trending', logger):
                # Aggiungi commenti se richiesto
                if get_comments:
                    try:
                        comments = await get_video_comments(api, video_data['id'], args.max_comments, logger)
                        video_data['comments'] = comments
                        video_data['comments_count'] = len(comments)
                        video_data['comments_retrieved'] = True
                    except Exception as e:
                        logger.debug(f"⚠️  Errore recupero commenti per video {video_data['id']}: {e}")
                        video_data['comments'] = []
                        video_data['comments_count'] = 0
                        video_data['comments_retrieved'] = False
                
                videos.append(video_data)
                kept += 1
                logger.debug(f"✅ Video trending {video_data['id']} mantenuto")
                
                if kept >= count:
                    break
            
            if processed >= count * 5:
                break
        
        logger.info(f"📊 Risultati trending:")
        logger.info(f"   - Processati: {processed}")
        logger.info(f"   - Mantenuti: {kept}")
        logger.info(f"   - Scartati: {processed - kept}")
        
        if get_transcript:
            transcript_count = sum(1 for v in videos if v.get('transcript_available'))
            logger.info(f"   - Con transcript: {transcript_count}")
            
        if get_comments:
            comments_count = sum(1 for v in videos if v.get('comments_retrieved'))
            total_comments = sum(v.get('comments_count', 0) for v in videos)
            logger.info(f"   - Con commenti: {comments_count}")
            logger.info(f"   - Commenti totali: {total_comments}")
        
        return videos
        
    except Exception as e:
        logger.error(f"❌ Errore ricerca trending: {e}")
        return []


# ================================
# FUNZIONI SALVATAGGIO E SUMMARY (SPECIFICHE TIKTOK)
# ================================

def save_videos(videos, search_type, search_term, args, logger):
    """Salva video in JSON con nome incrementale - FORMATO ORIGINALE ESATTO"""
    if not videos:
        logger.warning("⚠️  Nessun video da salvare")
        return None
    
    try:
        # Funzione per nome file incrementale (come originale)
        def get_next_filename(output_dir, prefix="tiktok_scraper", extension=".json"):
            """Trova il prossimo numero disponibile per il file"""
            counter = 1
            while True:
                filename = f"{output_dir}/{prefix}_#{counter}{extension}"
                if not os.path.exists(filename):
                    return filename, counter
                counter += 1
        
        # Nome file incrementale
        base_prefix = args.output_prefix if args.output_prefix else "tiktok_scraper"
        filename, file_number = get_next_filename(args.output_dir, base_prefix)
        
        # Metadata ESATTE come nel codice originale TikTok (semplificata)
        data = {
            'metadata': {
                'search_type': search_type,
                'search_term': search_term,
                'collection_time': datetime.now().isoformat(),
                'total_videos': len(videos)
            },
            'videos': videos  # MANTIENE ESATTAMENTE il formato originale TikTok
        }
        
        # Salva in JSON
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        
        logger.info(f"💾 File salvato con successo: {filename}")
        logger.info(f"📊 Video salvati: {len(videos)}")
        
        if args.add_transcript:
            transcript_count = sum(1 for video in videos if video.get('transcript_available'))
            logger.info(f"   - Video con transcript: {transcript_count}/{len(videos)}")
            
        if args.add_comments:
            comments_count = sum(1 for video in videos if video.get('comments_retrieved'))
            total_comments = sum(video.get('comments_count', 0) for video in videos)
            logger.info(f"   - Video con commenti: {comments_count}/{len(videos)}")
            logger.info(f"   - Commenti totali: {total_comments:,}")
        
        return filename
        
    except Exception as e:
        logger.error(f"❌ Errore salvataggio: {e}")
        return None


def print_summary(videos, search_type, search_term, logger):
    """Stampa riassunto dettagliato dei video raccolti"""
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
        
        # Statistiche rilevanza
        relevant_videos = sum(1 for video in videos if video.get('is_relevant', False))
        avg_relevance = sum(video.get('relevance_score', 0) for video in videos) / total_videos if total_videos else 0
        logger.info(f"🎯 Video rilevanti: {relevant_videos}/{total_videos} ({(relevant_videos/total_videos)*100:.1f}%)")
        logger.info(f"📊 Rilevanza media: {avg_relevance:.3f}")
        
        # Statistiche transcript
        videos_with_transcript = sum(1 for video in videos if video.get('transcript_available'))
        if videos_with_transcript > 0:
            logger.info(f"🎙️  Video con transcript: {videos_with_transcript}/{total_videos} ({(videos_with_transcript/total_videos)*100:.1f}%)")
            
            total_transcript_chars = sum(len(video.get('transcript_text', '') or '') for video in videos)
            avg_transcript_length = total_transcript_chars / videos_with_transcript if videos_with_transcript else 0
            logger.info(f"📝 Lunghezza media transcript: {avg_transcript_length:.0f} caratteri")
        
        # Statistiche commenti
        videos_with_comments = sum(1 for video in videos if video.get('comments_retrieved'))
        if videos_with_comments > 0:
            total_comments = sum(video.get('comments_count', 0) for video in videos)
            avg_comments = total_comments / videos_with_comments if videos_with_comments else 0
            logger.info(f"💬 Video con commenti: {videos_with_comments}/{total_videos} ({(videos_with_comments/total_videos)*100:.1f}%)")
            logger.info(f"💭 Commenti totali: {total_comments}")
            logger.info(f"📈 Media commenti per video: {avg_comments:.1f}")
        
        # Top 3 video più visti
        top_videos = sorted(videos, key=lambda x: x.get('stats', {}).get('views', 0), reverse=True)[:3]
        
        logger.info(f"🏆 Top 3 video più visti:")
        for i, video in enumerate(top_videos):
            views = video.get('stats', {}).get('views', 0)
            author = video.get('author_username', 'unknown')
            desc_preview = video.get('description', '')[:60] + "..." if len(video.get('description', '')) > 60 else video.get('description', '')
            relevance = video.get('relevance_score', 0)
            transcript_status = "🎙️" if video.get('transcript_available') else "❌"
            comments_status = f"💬{video.get('comments_count', 0)}" if video.get('comments_retrieved') else "❌"
            logger.info(f"{i+1}. ({views:,} views) @{author} [R:{relevance:.2f}] {transcript_status} {comments_status}: {desc_preview}")
        
    except Exception as e:
        logger.error(f"⚠️  Errore nel riassunto: {e}")


# ================================
# FUNZIONE PRINCIPALE
# ================================

async def main():
    """Funzione principale - TikTok Scraper Refactorizzato"""
    
    # ✅ USA MODULO CORE per argparse
    parser = setup_tiktok_argparse()
    args = parser.parse_args()
    
    # ✅ USA MODULO CORE per validazioni comuni
    args = validate_common_arguments(args, parser)
    validate_count_argument(args, parser, min_count=5, max_count=100)
    
    # ✅ USA MODULO CORE per logger
    logger = setup_tiktok_logger(args.log_level)
    
    logger.info("🎵 TIKTOK SCRAPER - Versione Refactorizzata")
    logger.info("🏗️  Usa moduli core comuni")
    logger.info("🎯 Features: Rilevanza, Commenti, Transcript")
    logger.info("=" * 60)
    
    # Dry run check
    if args.dry_run:
        logger.info("🧪 DRY RUN MODE - Test configurazione")
        mode = 'hashtag' if args.hashtag else 'user' if args.user else 'trending' if args.trending else 'non specificata'
        target = args.hashtag or args.user or 'trending' if args.trending else 'N/A'
        extra_info = {
            'Modalità': mode,
            'Target': target,
            'Transcript': 'ATTIVO' if args.add_transcript else 'DISATTIVO',
            'Commenti': 'ATTIVO' if args.add_comments else 'DISATTIVO',
            'Soglia rilevanza': args.relevance_threshold
        }
        print_configuration_summary(args, extra_info)
        logger.info("✅ Configurazione valida! Rimuovi --dry-run per eseguire.")
        return
    
    try:
        # 1. Ottieni MS Token
        ms_token = get_ms_token(args, logger)
        
        # 2. Controllo API key transcript
        if args.add_transcript:
            rapidapi_key = os.environ.get('RAPIDAPI_KEY') or os.environ.get('TIKTOK_TRANSCRIPT_API_KEY')
            if rapidapi_key:
                logger.info("✅ RapidAPI key trovata - transcript abilitato")
            else:
                logger.warning("⚠️  --add-transcript specificato ma RAPIDAPI_KEY mancante nel .env")
                logger.warning("⚠️  Continuo senza transcript")
                args.add_transcript = False
        
        # 3. Determina modalità di ricerca
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
        
        # ✅ USA MODULI CORE per pulizia input
        if search_type == 'hashtag':
            search_term = clean_hashtag_input(search_term, parser)
        elif search_type == 'user':
            search_term = clean_username_input(search_term, parser)
        
        # 4. Log configurazione finale
        logger.info(f"🎯 Configurazione finale:")
        logger.info(f"   - Modalità: {search_type}")
        logger.info(f"   - Target: {search_term}")
        logger.info(f"   - Quantità: {args.count} video")
        logger.info(f"   - Soglia rilevanza: {args.relevance_threshold}")
        
        filter_status = "DISATTIVATI" if args.no_filter else f"ATTIVI (min {args.min_desc_length} char)"
        logger.info(f"   - Filtri contenuto: {filter_status}")
        
        if args.add_transcript:
            logger.info(f"   - Transcript: ATTIVO (lingua: {args.transcript_language})")
            logger.info(f"   - ⚠️  Tempo elaborazione: +10-30s per video")
        else:
            logger.info(f"   - Transcript: DISATTIVO")
            
        if args.add_comments:
            logger.info(f"   - Commenti: ATTIVO (max {args.max_comments} per video)")
            logger.info(f"   - ⚠️  Tempo elaborazione: +5-15s per video")
        else:
            logger.info(f"   - Commenti: DISATTIVO")
        
        # 5. Crea TikTok API session
        logger.info("🔧 Inizializzazione TikTok API...")
        
        async with TikTokApi() as api:
            # Configura sessioni
            session_params = {
                'num_sessions': 1,
                'sleep_after': 3,
                'browser': getattr(args, 'browser', 'chromium')
            }
            
            # Aggiungi MS token se disponibile
            if ms_token:
                session_params['ms_tokens'] = [ms_token]
            
            # Configura proxy se richiesto
            if getattr(args, 'use_proxy', False):
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
            
            # 6. Esegui ricerca in base alla modalità
            videos = []
            
            if search_type == 'hashtag':
                videos = await search_hashtag_videos(api, search_term, args.count, args, logger)
            elif search_type == 'user':
                videos = await search_user_videos(api, search_term, args.count, args, logger)
            elif search_type == 'trending':
                videos = await search_trending_videos(api, args.count, args, logger)
            
            # 7. Salva e mostra risultati
            if videos:
                filename = save_videos(videos, search_type, search_term, args, logger)
                print_summary(videos, search_type, search_term, logger)
                
                logger.info("🎉 SCRAPING COMPLETATO CON SUCCESSO!")
                logger.info(f"📁 File: {filename}")
                logger.info(f"📊 Video TikTok raccolti: {len(videos)}")
                
                # Messaggi specifici per features
                if args.add_transcript:
                    transcript_count = sum(1 for v in videos if v.get('transcript_available'))
                    logger.info(f"🎙️  Transcript ottenuti: {transcript_count}/{len(videos)}")
                
                if args.add_comments:
                    comments_count = sum(1 for v in videos if v.get('comments_retrieved'))
                    total_comments = sum(v.get('comments_count', 0) for v in videos)
                    logger.info(f"💬 Commenti ottenuti: {comments_count}/{len(videos)} video ({total_comments} commenti totali)")
                
                # Messaggi specifici per modalità
                if search_type == 'hashtag':
                    logger.info(f"🏷️  Hashtag #{search_term} analizzato")
                elif search_type == 'user':
                    logger.info(f"👤 Profilo @{search_term} analizzato")
                elif search_type == 'trending':
                    logger.info("🔥 Video trending analizzati")
                
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
                    logger.info(f"   - Abbassa soglia rilevanza: --relevance-threshold 0.3 (ora: {args.relevance_threshold})")
                    logger.info(f"   - Abbassa soglia: --min-desc-length 5 (ora: {args.min_desc_length})")
                    logger.info("   - Disabilita filtri: --no-filter")
                
                if getattr(args, 'min_views', None):
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


def main_sync():
    """Wrapper sincrono per compatibilità"""
    asyncio.run(main())


if __name__ == "__main__":
    main_sync()