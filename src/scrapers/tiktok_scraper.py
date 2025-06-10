#!/usr/bin/env python3
"""
TikTok Scraper - Versione con PAGINATION COMPLETA
✅ Aggiunto supporto pagination per recuperare TUTTI i commenti
✅ 4 modalità: limited, adaptive, paginated, auto
✅ Batch processing con rate limiting
"""

import os
import json
import re
import sys
import asyncio
import requests
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv

# ✅ IMPORT DAI MODULI CORE (sostituiscono funzioni duplicate)
from src.core.logger import setup_tiktok_logger
from src.core.text_utils import (
    extract_hashtags_from_desc, clean_description, 
    is_meaningful_description
)
from src.core.cli_utils import (
    setup_tiktok_argparse, validate_common_arguments, validate_tiktok_arguments,
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
# ✅ NUOVE FUNZIONI PAGINATION COMMENTI
# ================================

async def get_all_video_comments_paginated(api, video_id, include_replies=False, max_replies=3, 
                                         max_total_comments=None, batch_size=50, 
                                         delay_between_batches=2, logger=None):
    """
    ✅ NUOVO: Recupera TUTTI i commenti di un video usando pagination
    
    Args:
        api: TikTokApi instance
        video_id: ID del video
        include_replies: Se includere risposte ai commenti
        max_replies: Max risposte per commento
        max_total_comments: Limite massimo commenti totali (None = illimitato)
        batch_size: Commenti per batch/pagina (default: 50)
        delay_between_batches: Secondi di attesa tra batch (anti rate-limit)
        logger: Logger per debug
    
    Returns:
        list: Lista completa di tutti i commenti con metadata pagination
    """
    try:
        if not video_id or video_id == 'unknown':
            logger.debug("⚠️  Video ID mancante per pagination commenti")
            return []
        
        logger.info(f"🔄 PAGINATION: Recuperando TUTTI i commenti per video {video_id}")
        logger.info(f"📊 Config: batch_size={batch_size}, max_total={max_total_comments or 'illimitato'}")
        
        video_obj = api.video(id=video_id)
        
        all_comments = []
        batch_count = 0
        total_processed = 0
        start_time = time.time()
        
        # Pagination loop - continua fino a che ci sono commenti
        async for comment in video_obj.comments(count=max_total_comments or 999999):
            try:
                comment_dict = comment.as_dict
                comment_text = comment_dict.get('text', '').strip()
                
                # Filtra commenti vuoti
                if comment_text and len(comment_text) >= 2:
                    # Struttura commento base
                    comment_obj = {
                        "text": comment_text,
                        "comment_id": comment_dict.get('cid', 'unknown'),
                        "replies_count": 0,
                        "has_replies": False,
                        "replies": [],
                        "batch_number": batch_count + 1,  # Metadata pagination
                        "comment_index": len(all_comments) + 1  # Posizione globale
                    }
                    
                    # Recupera risposte se richiesto
                    if include_replies:
                        try:
                            replies_list = []
                            reply_count = 0
                            
                            async for reply in comment.replies(count=max_replies * 2):
                                try:
                                    reply_dict = reply.as_dict
                                    reply_text = reply_dict.get('text', '').strip()
                                    
                                    if reply_text and len(reply_text) >= 2:
                                        reply_obj = {
                                            "text": reply_text,
                                            "reply_id": reply_dict.get('cid', 'unknown')
                                        }
                                        replies_list.append(reply_obj)
                                        reply_count += 1
                                        
                                        if reply_count >= max_replies:
                                            break
                                            
                                except Exception as e:
                                    logger.debug(f"⚠️  Errore elaborazione singola risposta: {e}")
                                    continue
                            
                            comment_obj["replies"] = replies_list
                            comment_obj["replies_count"] = len(replies_list)
                            comment_obj["has_replies"] = len(replies_list) > 0
                            
                        except Exception as e:
                            logger.debug(f"⚠️  Errore recupero risposte: {e}")
                    
                    all_comments.append(comment_obj)
                    total_processed += 1
                    
                    # Progress logging ogni batch_size commenti
                    if total_processed % batch_size == 0:
                        batch_count += 1
                        elapsed = time.time() - start_time
                        rate = total_processed / elapsed if elapsed > 0 else 0
                        
                        logger.info(f"📦 Batch #{batch_count}: {total_processed} commenti | {rate:.1f}/sec | {elapsed:.1f}s")
                        
                        # Delay anti rate-limit tra batch
                        if delay_between_batches > 0:
                            logger.debug(f"⏳ Pausa {delay_between_batches}s...")
                            await asyncio.sleep(delay_between_batches)
                    
                    # Limite massimo raggiunto
                    if max_total_comments and total_processed >= max_total_comments:
                        logger.info(f"🛑 Limite massimo raggiunto: {max_total_comments} commenti")
                        break
                        
            except Exception as e:
                logger.debug(f"⚠️  Errore elaborazione commento: {e}")
                continue
        
        # Statistiche finali
        elapsed_total = time.time() - start_time
        avg_rate = total_processed / elapsed_total if elapsed_total > 0 else 0
        total_replies = sum(comment.get('replies_count', 0) for comment in all_comments)
        
        logger.info(f"✅ PAGINATION COMPLETATA per video {video_id}")
        logger.info(f"📊 Commenti: {len(all_comments)} | Tempo: {elapsed_total:.1f}s | Rate: {avg_rate:.1f}/sec")
        
        if include_replies:
            logger.info(f"💬 Risposte raccolte: {total_replies}")
        
        # Aggiungi metadata globali
        for comment in all_comments:
            comment["pagination_metadata"] = {
                "total_comments_in_video": len(all_comments),
                "total_batches": batch_count + 1,
                "collection_duration_seconds": round(elapsed_total, 2),
                "average_rate_per_second": round(avg_rate, 2),
                "collection_timestamp": datetime.now().isoformat()
            }
        
        return all_comments
        
    except Exception as e:
        logger.error(f"❌ Errore pagination commenti per video {video_id}: {e}")
        return []


async def get_video_comments_smart(api, video_id, pagination_mode="limited", max_comments=10, 
                                 include_replies=False, max_replies=3, 
                                 batch_size=50, max_total_comments=None, logger=None):
    """
    ✅ NUOVO: Funzione SMART che decide automaticamente tra pagination e limite fisso
    
    Args:
        pagination_mode (str): 
            - "limited": Usa limite fisso (comportamento originale)
            - "adaptive": Pagination fino a max_total_comments
            - "paginated": Pagination completa - TUTTI i commenti
            - "auto": Decide automaticamente
    """
    
    if pagination_mode == "limited":
        # Comportamento originale - limite fisso
        logger.debug(f"💬 Modalità LIMITED: max {max_comments} commenti")
        return await get_video_comments(api, video_id, max_comments, include_replies, max_replies, logger)
    
    elif pagination_mode == "paginated":
        # Pagination completa - TUTTI i commenti
        logger.debug(f"🔄 Modalità PAGINATED: recupero TUTTI i commenti")
        return await get_all_video_comments_paginated(
            api, video_id, include_replies, max_replies, 
            max_total_comments=None, batch_size=batch_size, 
            delay_between_batches=2.0, logger=logger
        )
    
    elif pagination_mode == "adaptive":
        # Pagination con limite massimo
        logger.debug(f"🎯 Modalità ADAPTIVE: max {max_total_comments or 'illimitato'} commenti")
        return await get_all_video_comments_paginated(
            api, video_id, include_replies, max_replies,
            max_total_comments=max_total_comments, batch_size=batch_size, 
            delay_between_batches=2.0, logger=logger
        )
    
    else:  # "auto"
        # Decide automaticamente in base ai metadati del video
        logger.debug(f"🤖 Modalità AUTO: decisione automatica")
        
        # Per ora usa adaptive con limite ragionevole
        default_limit = 500  # Limite ragionevole per auto mode
        logger.debug(f"🎯 AUTO-MODE: usando adaptive con limite {default_limit}")
        
        return await get_all_video_comments_paginated(
            api, video_id, include_replies, max_replies,
            max_total_comments=default_limit, batch_size=batch_size, 
            delay_between_batches=2.0, logger=logger
        )


# ================================
# FUNZIONI COMMENTI ORIGINALI (MANTIENUTE PER COMPATIBILITÀ)
# ================================

async def get_video_comments(api, video_id, max_comments=10, include_replies=False, max_replies=3, logger=None):
    """Recupera i commenti di un video TikTok con opzioni per risposte nested - VERSIONE ORIGINALE"""
    try:
        if not video_id or video_id == 'unknown':
            logger.debug("⚠️  Video ID mancante per commenti")
            return []
        
        if include_replies:
            logger.debug(f"💬 Recuperando commenti + risposte per video {video_id} (max {max_replies} risposte per commento)...")
        else:
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
                    # Struttura commento base
                    comment_obj = {
                        "text": comment_text,
                        "comment_id": comment_dict.get('cid', 'unknown'),
                        "replies_count": 0,
                        "has_replies": False,
                        "replies": []
                    }
                    
                    # ✅ Recupera risposte se richiesto
                    if include_replies:
                        try:
                            replies_list = []
                            reply_count = 0
                            
                            # Ottieni risposte al commento
                            async for reply in comment.replies(count=max_replies * 2):
                                try:
                                    reply_dict = reply.as_dict
                                    reply_text = reply_dict.get('text', '').strip()
                                    
                                    if reply_text and len(reply_text) >= 2:
                                        reply_obj = {
                                            "text": reply_text,
                                            "reply_id": reply_dict.get('cid', 'unknown')
                                        }
                                        replies_list.append(reply_obj)
                                        reply_count += 1
                                        
                                        if reply_count >= max_replies:
                                            break
                                            
                                except Exception as e:
                                    logger.debug(f"⚠️  Errore elaborazione singola risposta: {e}")
                                    continue
                            
                            # Aggiorna commento con risposte
                            comment_obj["replies"] = replies_list
                            comment_obj["replies_count"] = len(replies_list)
                            comment_obj["has_replies"] = len(replies_list) > 0
                            
                            if len(replies_list) > 0:
                                logger.debug(f"✅ Commento {comment_obj['comment_id']}: {len(replies_list)} risposte raccolte")
                                
                        except Exception as e:
                            logger.debug(f"⚠️  Errore recupero risposte per commento {comment_obj.get('comment_id')}: {e}")
                            # Mantieni commento anche se risposte falliscono
                    
                    comments_list.append(comment_obj)
                    comment_count += 1
                    
                    # Fermati quando raggiungi il limite
                    if comment_count >= max_comments:
                        break
                        
            except Exception as e:
                logger.debug(f"⚠️  Errore elaborazione singolo commento: {e}")
                continue
        
        # Calcola statistiche totali
        total_replies = sum(comment.get('replies_count', 0) for comment in comments_list)
        
        if include_replies and total_replies > 0:
            logger.debug(f"✅ Raccolti {len(comments_list)} commenti + {total_replies} risposte per video {video_id}")
        else:
            logger.debug(f"✅ Raccolti {len(comments_list)} commenti per video {video_id}")
            
        return comments_list
        
    except Exception as e:
        logger.debug(f"⚠️  Errore recupero commenti per video {video_id}: {e}")
        return []


def should_get_comments(args, video_count, logger):
    """Decide se recuperare commenti in base ai parametri"""
    if not args.add_comments:
        return False
    
    # ✅ NUOVO: Warning specifici per pagination
    if getattr(args, 'pagination_mode', 'limited') != 'limited':
        if args.pagination_mode == 'paginated':
            logger.warning(f"⚠️  Modalità PAGINATED per {video_count} video - può richiedere ORE!")
        elif args.pagination_mode == 'adaptive':
            max_total = getattr(args, 'max_total_comments', 1000)
            estimated_time = video_count * (max_total / 100)  # Stima ~100 commenti/minuto
            logger.warning(f"⚠️  Modalità ADAPTIVE ({max_total} commenti/video) - tempo stimato: ~{estimated_time:.0f} minuti")
        elif args.pagination_mode == 'auto':
            logger.warning(f"⚠️  Modalità AUTO - tempo variabile basato sui video")
    elif video_count > 20:
        logger.warning(f"⚠️  Recupero commenti per {video_count} video - potrebbe essere lento")
        logger.warning(f"⚠️  Considera di ridurre --count per test più veloci")
    
    if args.include_replies and getattr(args, 'pagination_mode', 'limited') != 'limited':
        logger.warning(f"⚠️  Pagination + risposte abilitato - tempo MOLTO aumentato")
    
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
# FUNZIONI UTILITY (SPECIFICHE TIKTOK)
# ================================

def apply_video_filters(video_data, args, search_term, logger):
    """Applica filtri ai video (durata, views, descrizione, data creazione)"""
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
        
        # ✅ Filtro data creazione
        if getattr(args, 'created_after', None):
            try:
                from datetime import datetime
                video_created_at = video_data.get('created_at')
                if video_created_at:
                    # Parse della data del video (formato ISO)
                    video_date = datetime.fromisoformat(video_created_at.replace('Z', '+00:00'))
                    # Parse della data filtro
                    filter_date = datetime.strptime(args.created_after, '%Y-%m-%d')
                    
                    if video_date.date() <= filter_date.date():
                        logger.debug(f"🗑️  Video {video_data.get('id')} scartato: creato {video_date.date()} <= {filter_date.date()}")
                        return False
                else:
                    logger.debug(f"🗑️  Video {video_data.get('id')} scartato: data creazione mancante")
                    return False
            except Exception as e:
                logger.warning(f"⚠️  Errore filtro data per video {video_data.get('id')}: {e}")
                # In caso di errore nella data, mantieni il video
        
        # Filtro descrizione (se abilitato)
        if not args.no_filter:
            desc = video_data.get('description', '')
            # ✅ USA MODULO CORE per pulizia descrizione
            clean_desc = clean_description(desc, logger)
            
            # ✅ USA MODULO CORE per valutazione significatività
            if not is_meaningful_description(clean_desc, search_term, args.min_desc_length, logger):
                logger.debug(f"🗑️  Video {video_data.get('id')} scartato: descrizione non significativa")
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
        
        # Struttura dati TikTok con supporto risposte commenti + PAGINATION
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
            'comments': [],  # Sarà popolato con oggetti nested con risposte
            'comments_count': 0,
            'comments_retrieved': False,
            'total_replies_count': 0,
            'replies_retrieved': False,
            # ✅ NUOVO: Metadata pagination
            'pagination_used': False,
            'pagination_mode': 'limited',
            'total_comments_collected': 0,
            'collection_duration_seconds': 0
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
            'total_replies_count': 0,
            'replies_retrieved': False,
            'pagination_used': False,
            'pagination_mode': 'limited',
            'error': str(e)
        }


# ================================
# ✅ FUNZIONI DI RICERCA AGGIORNATE CON PAGINATION
# ================================

async def search_hashtag_videos(api, hashtag, count, args, logger):
    """✅ AGGIORNATO: Cerca video per hashtag con supporto pagination"""
    try:
        logger.info(f"🔍 Cercando {count} video per hashtag #{hashtag}")
        
        # Controllo transcript e commenti
        get_transcript = should_get_transcript(args, count, logger)
        get_comments = should_get_comments(args, count, logger)
        
        # ✅ NUOVO: Info pagination
        if get_comments and getattr(args, 'pagination_mode', 'limited') != 'limited':
            mode_descriptions = {
                'limited': f"primi {args.max_comments} commenti",
                'adaptive': f"fino a {getattr(args, 'max_total_comments', 1000)} commenti per video",
                'paginated': "TUTTI i commenti disponibili (può richiedere ore)",
                'auto': "modalità automatica intelligente"
            }
            mode_desc = mode_descriptions.get(args.pagination_mode, 'modalità sconosciuta')
            logger.info(f"🔄 Pagination commenti: {mode_desc}")
        
        if get_transcript:
            logger.info("🎙️  Transcript abilitato - tempo di elaborazione aumentato")
        
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
                # ✅ AGGIORNATO: Usa la nuova funzione smart per commenti
                if get_comments:
                    try:
                        comments = await get_video_comments_smart(
                            api=api,
                            video_id=video_data['id'],
                            pagination_mode=getattr(args, 'pagination_mode', 'limited'),
                            max_comments=args.max_comments,
                            include_replies=args.include_replies,
                            max_replies=args.max_replies,
                            batch_size=getattr(args, 'batch_size', 50),
                            max_total_comments=getattr(args, 'max_total_comments', None),
                            logger=logger
                        )
                        
                        video_data['comments'] = comments
                        video_data['comments_count'] = len(comments)
                        video_data['comments_retrieved'] = True
                        
                        # ✅ NUOVO: Metadata pagination
                        if comments and getattr(args, 'pagination_mode', 'limited') != 'limited':
                            video_data['pagination_used'] = True
                            video_data['pagination_mode'] = args.pagination_mode
                            
                            # Estrai metadata dal primo commento se disponibile
                            if comments and 'pagination_metadata' in comments[0]:
                                pagination_meta = comments[0]['pagination_metadata']
                                video_data['total_comments_collected'] = pagination_meta.get('total_comments_in_video', len(comments))
                                video_data['collection_duration_seconds'] = pagination_meta.get('collection_duration_seconds', 0)
                        
                        # Statistiche risposte
                        if args.include_replies:
                            total_replies = sum(comment.get('replies_count', 0) for comment in comments)
                            video_data['total_replies_count'] = total_replies
                            video_data['replies_retrieved'] = True
                        else:
                            video_data['total_replies_count'] = 0
                            video_data['replies_retrieved'] = False
                            
                    except Exception as e:
                        logger.debug(f"⚠️  Errore recupero commenti per video {video_data['id']}: {e}")
                        video_data['comments'] = []
                        video_data['comments_count'] = 0
                        video_data['comments_retrieved'] = False
                        video_data['total_replies_count'] = 0
                        video_data['replies_retrieved'] = False
                
                videos.append(video_data)
                kept += 1
                logger.debug(f"✅ Video {video_data['id']} mantenuto")
                
                if kept >= count:
                    break
            
            # Limite massimo per evitare loop infiniti
            if processed >= count * 5:
                break
        
        # ✅ AGGIORNATO: Statistiche con info pagination
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
            
            # ✅ NUOVO: Statistiche pagination
            if getattr(args, 'pagination_mode', 'limited') != 'limited':
                paginated_videos = sum(1 for v in videos if v.get('pagination_used'))
                total_collection_time = sum(v.get('collection_duration_seconds', 0) for v in videos)
                logger.info(f"   - Video con pagination: {paginated_videos}")
                logger.info(f"   - Tempo raccolta commenti: {total_collection_time:.1f} secondi")
            
            if args.include_replies:
                total_replies = sum(v.get('total_replies_count', 0) for v in videos)
                logger.info(f"   - Risposte totali: {total_replies}")
        
        return videos
        
    except Exception as e:
        logger.error(f"❌ Errore ricerca hashtag #{hashtag}: {e}")
        return []


async def search_user_videos(api, username, count, args, logger):
    """✅ AGGIORNATO: Cerca video di un utente con supporto pagination"""
    try:
        logger.info(f"🔍 Cercando {count} video dell'utente @{username}")
        
        # Controllo transcript e commenti
        get_transcript = should_get_transcript(args, count, logger)
        get_comments = should_get_comments(args, count, logger)
        
        # Info pagination
        if get_comments and getattr(args, 'pagination_mode', 'limited') != 'limited':
            mode_descriptions = {
                'limited': f"primi {args.max_comments} commenti",
                'adaptive': f"fino a {getattr(args, 'max_total_comments', 1000)} commenti per video",
                'paginated': "TUTTI i commenti disponibili",
                'auto': "modalità automatica"
            }
            mode_desc = mode_descriptions.get(args.pagination_mode, 'modalità sconosciuta')
            logger.info(f"🔄 Pagination commenti: {mode_desc}")
        
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
                # ✅ AGGIORNATO: Usa la nuova funzione smart per commenti
                if get_comments:
                    try:
                        comments = await get_video_comments_smart(
                            api=api,
                            video_id=video_data['id'],
                            pagination_mode=getattr(args, 'pagination_mode', 'limited'),
                            max_comments=args.max_comments,
                            include_replies=args.include_replies,
                            max_replies=args.max_replies,
                            batch_size=getattr(args, 'batch_size', 50),
                            max_total_comments=getattr(args, 'max_total_comments', None),
                            logger=logger
                        )
                        
                        video_data['comments'] = comments
                        video_data['comments_count'] = len(comments)
                        video_data['comments_retrieved'] = True
                        
                        # Metadata pagination
                        if comments and getattr(args, 'pagination_mode', 'limited') != 'limited':
                            video_data['pagination_used'] = True
                            video_data['pagination_mode'] = args.pagination_mode
                            
                            if comments and 'pagination_metadata' in comments[0]:
                                pagination_meta = comments[0]['pagination_metadata']
                                video_data['total_comments_collected'] = pagination_meta.get('total_comments_in_video', len(comments))
                                video_data['collection_duration_seconds'] = pagination_meta.get('collection_duration_seconds', 0)
                        
                        # Aggiungi statistiche risposte
                        if args.include_replies:
                            total_replies = sum(comment.get('replies_count', 0) for comment in comments)
                            video_data['total_replies_count'] = total_replies
                            video_data['replies_retrieved'] = True
                        else:
                            video_data['total_replies_count'] = 0
                            video_data['replies_retrieved'] = False
                            
                    except Exception as e:
                        logger.debug(f"⚠️  Errore recupero commenti per video {video_data['id']}: {e}")
                        video_data['comments'] = []
                        video_data['comments_count'] = 0
                        video_data['comments_retrieved'] = False
                        video_data['total_replies_count'] = 0
                        video_data['replies_retrieved'] = False
                
                videos.append(video_data)
                kept += 1
                logger.debug(f"✅ Video {video_data['id']} mantenuto")
                
                if kept >= count:
                    break
            
            if processed >= count * 5:
                break
        
        # Statistiche con pagination
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
            
            if getattr(args, 'pagination_mode', 'limited') != 'limited':
                paginated_videos = sum(1 for v in videos if v.get('pagination_used'))
                total_collection_time = sum(v.get('collection_duration_seconds', 0) for v in videos)
                logger.info(f"   - Video con pagination: {paginated_videos}")
                logger.info(f"   - Tempo raccolta commenti: {total_collection_time:.1f} secondi")
            
            if args.include_replies:
                total_replies = sum(v.get('total_replies_count', 0) for v in videos)
                logger.info(f"   - Risposte totali: {total_replies}")
        
        return videos
        
    except Exception as e:
        logger.error(f"❌ Errore ricerca utente @{username}: {e}")
        return []


async def search_trending_videos(api, count, args, logger):
    """✅ AGGIORNATO: Cerca video trending con supporto pagination"""
    try:
        logger.info(f"🔍 Cercando {count} video trending")
        
        # Controllo transcript e commenti
        get_transcript = should_get_transcript(args, count, logger)
        get_comments = should_get_comments(args, count, logger)
        
        # Info pagination
        if get_comments and getattr(args, 'pagination_mode', 'limited') != 'limited':
            mode_descriptions = {
                'limited': f"primi {args.max_comments} commenti",
                'adaptive': f"fino a {getattr(args, 'max_total_comments', 1000)} commenti per video",
                'paginated': "TUTTI i commenti disponibili",
                'auto': "modalità automatica"
            }
            mode_desc = mode_descriptions.get(args.pagination_mode, 'modalità sconosciuta')
            logger.info(f"🔄 Pagination commenti: {mode_desc}")
        
        if get_transcript:
            logger.info("🎙️  Transcript abilitato - tempo di elaborazione aumentato")
        
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
                # ✅ AGGIORNATO: Usa la nuova funzione smart per commenti
                if get_comments:
                    try:
                        comments = await get_video_comments_smart(
                            api=api,
                            video_id=video_data['id'],
                            pagination_mode=getattr(args, 'pagination_mode', 'limited'),
                            max_comments=args.max_comments,
                            include_replies=args.include_replies,
                            max_replies=args.max_replies,
                            batch_size=getattr(args, 'batch_size', 50),
                            max_total_comments=getattr(args, 'max_total_comments', None),
                            logger=logger
                        )
                        
                        video_data['comments'] = comments
                        video_data['comments_count'] = len(comments)
                        video_data['comments_retrieved'] = True
                        
                        # Metadata pagination
                        if comments and getattr(args, 'pagination_mode', 'limited') != 'limited':
                            video_data['pagination_used'] = True
                            video_data['pagination_mode'] = args.pagination_mode
                            
                            if comments and 'pagination_metadata' in comments[0]:
                                pagination_meta = comments[0]['pagination_metadata']
                                video_data['total_comments_collected'] = pagination_meta.get('total_comments_in_video', len(comments))
                                video_data['collection_duration_seconds'] = pagination_meta.get('collection_duration_seconds', 0)
                        
                        # Aggiungi statistiche risposte
                        if args.include_replies:
                            total_replies = sum(comment.get('replies_count', 0) for comment in comments)
                            video_data['total_replies_count'] = total_replies
                            video_data['replies_retrieved'] = True
                        else:
                            video_data['total_replies_count'] = 0
                            video_data['replies_retrieved'] = False
                            
                    except Exception as e:
                        logger.debug(f"⚠️  Errore recupero commenti per video {video_data['id']}: {e}")
                        video_data['comments'] = []
                        video_data['comments_count'] = 0
                        video_data['comments_retrieved'] = False
                        video_data['total_replies_count'] = 0
                        video_data['replies_retrieved'] = False
                
                videos.append(video_data)
                kept += 1
                logger.debug(f"✅ Video trending {video_data['id']} mantenuto")
                
                if kept >= count:
                    break
            
            if processed >= count * 5:
                break
        
        # Statistiche con pagination
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
            
            if getattr(args, 'pagination_mode', 'limited') != 'limited':
                paginated_videos = sum(1 for v in videos if v.get('pagination_used'))
                total_collection_time = sum(v.get('collection_duration_seconds', 0) for v in videos)
                logger.info(f"   - Video con pagination: {paginated_videos}")
                logger.info(f"   - Tempo raccolta commenti: {total_collection_time:.1f} secondi")
            
            if args.include_replies:
                total_replies = sum(v.get('total_replies_count', 0) for v in videos)
                logger.info(f"   - Risposte totali: {total_replies}")
        
        return videos
        
    except Exception as e:
        logger.error(f"❌ Errore ricerca trending: {e}")
        return []


# ================================
# FUNZIONI SALVATAGGIO E SUMMARY (AGGIORNATE)
# ================================

def save_videos(videos, search_type, search_term, args, logger):
    """✅ AGGIORNATO: Salva video in formato JSONL con metadata pagination"""
    if not videos:
        logger.warning("⚠️  Nessun video da salvare")
        return None
    
    try:
        # Funzione per nome file incrementale (come originale)
        def get_next_filename(output_dir, prefix="tiktok_scraper", extension=".jsonl"):
            """Trova il prossimo numero disponibile per il file"""
            counter = 1
            while True:
                filename = f"{output_dir}/{prefix}_#{counter}{extension}"
                if not os.path.exists(filename):
                    return filename, counter
                counter += 1
        
        # Nome file incrementale con estensione .jsonl
        base_prefix = args.output_prefix if args.output_prefix else "tiktok_scraper"
        filename, file_number = get_next_filename(args.output_dir, base_prefix)
        
        # Aggiungi metadati a ogni video per tracciabilità
        collection_time = datetime.now().isoformat()
        
        # Salva in formato JSONL - una riga per video
        with open(filename, 'w', encoding='utf-8') as f:
            for video in videos:
                # Aggiungi metadati di collezione a ogni video
                video_with_metadata = video.copy()
                video_with_metadata.update({
                    'collection_time': collection_time,
                    'search_type': search_type,
                    'search_term': search_term
                })
                
                # Scrivi una riga JSON per video (formato JSONL)
                json_line = json.dumps(video_with_metadata, ensure_ascii=False, default=str)
                f.write(json_line + '\n')
        
        logger.info(f"💾 File JSONL salvato con successo: {filename}")
        logger.info(f"📊 Video salvati: {len(videos)} (una riga per video)")
        
        if args.add_transcript:
            transcript_count = sum(1 for video in videos if video.get('transcript_available'))
            logger.info(f"   - Video con transcript: {transcript_count}/{len(videos)}")
            
        if args.add_comments:
            comments_count = sum(1 for video in videos if video.get('comments_retrieved'))
            total_comments = sum(video.get('comments_count', 0) for video in videos)
            logger.info(f"   - Video con commenti: {comments_count}/{len(videos)}")
            logger.info(f"   - Commenti totali: {total_comments:,}")
            
            # ✅ NUOVO: Statistiche pagination
            if getattr(args, 'pagination_mode', 'limited') != 'limited':
                paginated_count = sum(1 for video in videos if video.get('pagination_used'))
                total_collection_time = sum(video.get('collection_duration_seconds', 0) for video in videos)
                logger.info(f"   - Video con pagination: {paginated_count}/{len(videos)}")
                logger.info(f"   - Tempo raccolta totale: {total_collection_time:.1f} secondi")
            
            if args.include_replies:
                total_replies = sum(video.get('total_replies_count', 0) for video in videos)
                logger.info(f"   - Risposte totali: {total_replies:,}")
        
        return filename
        
    except Exception as e:
        logger.error(f"❌ Errore salvataggio: {e}")
        return None


def print_summary(videos, search_type, search_term, logger):
    """✅ AGGIORNATO: Stampa riassunto dettagliato con statistiche pagination"""
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
        
        # Statistiche rilevanza (solo per info, non più filtrate)
        relevant_videos = sum(1 for video in videos if video.get('is_relevant', False))
        avg_relevance = sum(video.get('relevance_score', 0) for video in videos) / total_videos if total_videos else 0
        logger.info(f"🎯 Video rilevanti: {relevant_videos}/{total_videos} ({(relevant_videos/total_videos)*100:.1f}%) [INFO ONLY]")
        logger.info(f"📊 Rilevanza media: {avg_relevance:.3f}")
        
        # Statistiche transcript
        videos_with_transcript = sum(1 for video in videos if video.get('transcript_available'))
        if videos_with_transcript > 0:
            logger.info(f"🎙️  Video con transcript: {videos_with_transcript}/{total_videos} ({(videos_with_transcript/total_videos)*100:.1f}%)")
            
            total_transcript_chars = sum(len(video.get('transcript_text', '') or '') for video in videos)
            avg_transcript_length = total_transcript_chars / videos_with_transcript if videos_with_transcript else 0
            logger.info(f"📝 Lunghezza media transcript: {avg_transcript_length:.0f} caratteri")
        
        # ✅ AGGIORNATO: Statistiche commenti e pagination
        videos_with_comments = sum(1 for video in videos if video.get('comments_retrieved'))
        if videos_with_comments > 0:
            total_comments = sum(video.get('comments_count', 0) for video in videos)
            avg_comments = total_comments / videos_with_comments if videos_with_comments else 0
            logger.info(f"💬 Video con commenti: {videos_with_comments}/{total_videos} ({(videos_with_comments/total_videos)*100:.1f}%)")
            logger.info(f"💭 Commenti totali: {total_comments:,}")
            logger.info(f"📈 Media commenti per video: {avg_comments:.1f}")
            
            # ✅ NUOVO: Statistiche pagination
            videos_with_pagination = sum(1 for video in videos if video.get('pagination_used'))
            if videos_with_pagination > 0:
                total_collection_time = sum(video.get('collection_duration_seconds', 0) for video in videos)
                avg_collection_time = total_collection_time / videos_with_pagination if videos_with_pagination else 0
                logger.info(f"🔄 Video con pagination: {videos_with_pagination}/{total_videos}")
                logger.info(f"⏱️  Tempo raccolta commenti: {total_collection_time:.1f} secondi totali")
                logger.info(f"📊 Tempo medio per video: {avg_collection_time:.1f} secondi")
            
            # Statistiche risposte
            videos_with_replies = sum(1 for video in videos if video.get('replies_retrieved'))
            if videos_with_replies > 0:
                total_replies = sum(video.get('total_replies_count', 0) for video in videos)
                avg_replies = total_replies / videos_with_replies if videos_with_replies else 0
                logger.info(f"💬➡️ Video con risposte: {videos_with_replies}/{total_videos}")
                logger.info(f"💭➡️ Risposte totali: {total_replies:,}")
                logger.info(f"📈➡️ Media risposte per video: {avg_replies:.1f}")
        
        # Top 3 video più visti con info pagination
        top_videos = sorted(videos, key=lambda x: x.get('stats', {}).get('views', 0), reverse=True)[:3]
        
        logger.info(f"🏆 Top 3 video più visti:")
        for i, video in enumerate(top_videos):
            views = video.get('stats', {}).get('views', 0)
            author = video.get('author_username', 'unknown')
            desc_preview = video.get('description', '')[:60] + "..." if len(video.get('description', '')) > 60 else video.get('description', '')
            relevance = video.get('relevance_score', 0)
            transcript_status = "🎙️" if video.get('transcript_available') else "❌"
            comments_status = f"💬{video.get('comments_count', 0)}" if video.get('comments_retrieved') else "❌"
            replies_status = f"➡️{video.get('total_replies_count', 0)}" if video.get('replies_retrieved') else ""
            # ✅ NUOVO: Indicatore pagination
            pagination_status = f"🔄{video.get('pagination_mode', 'limited')[0].upper()}" if video.get('pagination_used') else ""
            
            logger.info(f"{i+1}. ({views:,} views) @{author} [R:{relevance:.2f}] {transcript_status} {comments_status}{replies_status} {pagination_status}: {desc_preview}")
        
    except Exception as e:
        logger.error(f"⚠️  Errore nel riassunto: {e}")


# ================================
# ✅ FUNZIONE PRINCIPALE AGGIORNATA
# ================================

async def main():
    """✅ AGGIORNATO: Funzione principale con supporto pagination completo"""
    
    # ✅ USA MODULO CORE per argparse (ora con pagination)
    parser = setup_tiktok_argparse()
    args = parser.parse_args()
    
    # ✅ USA MODULO CORE per validazioni comuni e TikTok-specifiche (ora con pagination)
    args = validate_common_arguments(args, parser)
    args = validate_tiktok_arguments(args, parser)  # Include validazioni pagination
    validate_count_argument(args, parser, min_count=5, max_count=100)
    
    # ✅ USA MODULO CORE per logger
    logger = setup_tiktok_logger(args.log_level)
    
    logger.info("🎵 TIKTOK SCRAPER - Versione con PAGINATION")
    logger.info("🔄 Features: Pagination, Rilevanza, Commenti + Risposte, Transcript")
    logger.info("=" * 60)
    
    # Dry run check
    if args.dry_run:
        logger.info("🧪 DRY RUN MODE - Test configurazione")
        mode = 'hashtag' if args.hashtag else 'user' if args.user else 'trending' if args.trending else 'non specificata'
        target = args.hashtag or args.user or 'trending' if args.trending else 'N/A'
        
        # ✅ NUOVO: Info pagination nel dry-run
        extra_info = {
            'Modalità': mode,
            'Target': target,
            'Transcript': 'ATTIVO' if args.add_transcript else 'DISATTIVO',
            'Commenti': 'ATTIVO' if args.add_comments else 'DISATTIVO',
            'Risposte': 'ATTIVO' if (args.add_comments and args.include_replies) else 'DISATTIVO',
            'Pagination mode': getattr(args, 'pagination_mode', 'limited'),
            'Max total comments': getattr(args, 'max_total_comments', 'N/A'),
            'Batch size': getattr(args, 'batch_size', 'N/A'),
            'Soglia rilevanza': f"{args.relevance_threshold} (solo metadata)",
            'Filtro data': args.created_after if getattr(args, 'created_after', None) else 'NESSUNO'
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
        
        # 4. Log configurazione finale con pagination
        logger.info(f"🎯 Configurazione finale:")
        logger.info(f"   - Modalità: {search_type}")
        logger.info(f"   - Target: {search_term}")
        logger.info(f"   - Quantità: {args.count} video")
        logger.info(f"   - Soglia rilevanza: {args.relevance_threshold} (solo metadata)")
        
        filter_status = "DISATTIVATI" if args.no_filter else f"ATTIVI (min {args.min_desc_length} char)"
        logger.info(f"   - Filtri contenuto: {filter_status}")
        
        if args.add_transcript:
            logger.info(f"   - Transcript: ATTIVO (lingua: {args.transcript_language})")
            logger.info(f"   - ⚠️  Tempo elaborazione: +10-30s per video")
        else:
            logger.info(f"   - Transcript: DISATTIVO")
            
        if args.add_comments:
            # ✅ NUOVO: Info dettagliate pagination
            pagination_mode = getattr(args, 'pagination_mode', 'limited')
            if pagination_mode == 'limited':
                logger.info(f"   - Commenti: MODALITÀ LIMITED (max {args.max_comments} per video)")
                logger.info(f"   - ⚠️  Tempo elaborazione: +5-15s per video")
            elif pagination_mode == 'adaptive':
                max_total = getattr(args, 'max_total_comments', 1000)
                logger.info(f"   - Commenti: MODALITÀ ADAPTIVE (max {max_total} per video)")
                logger.info(f"   - ⚠️  Tempo elaborazione: +30s-5min per video")
            elif pagination_mode == 'paginated':
                logger.info(f"   - Commenti: MODALITÀ PAGINATED (TUTTI i commenti)")
                logger.info(f"   - ⚠️  Tempo elaborazione: +2-30min per video")
            elif pagination_mode == 'auto':
                logger.info(f"   - Commenti: MODALITÀ AUTO (intelligente)")
                logger.info(f"   - ⚠️  Tempo elaborazione: variabile")
            
            if args.include_replies:
                logger.info(f"   - Risposte: ATTIVATE (max {args.max_replies} per commento)")
                logger.info(f"   - ⚠️  Tempo aggiuntivo per risposte")
                
            # Info batch per pagination
            if pagination_mode != 'limited':
                batch_size = getattr(args, 'batch_size', 50)
                delay = getattr(args, 'delay_between_batches', 2.0)
                logger.info(f"   - Batch size: {batch_size} commenti/batch")
                logger.info(f"   - Delay tra batch: {delay}s")
        else:
            logger.info(f"   - Commenti: DISATTIVO")
        
        if getattr(args, 'min_views', None):
            logger.info(f"   - Views minime: {args.min_views:,}")
        
        if getattr(args, 'created_after', None):
            logger.info(f"   - Video creati dopo: {args.created_after}")
        
        logger.info(f"   - Output: {args.output_dir}/{args.output_prefix}...")
        
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
            
            # 6. Esegui ricerca in base alla modalità (tutte aggiornate con pagination)
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
                
                # ✅ AGGIORNATO: Messaggi specifici per features + pagination
                if args.add_transcript:
                    transcript_count = sum(1 for v in videos if v.get('transcript_available'))
                    logger.info(f"🎙️  Transcript ottenuti: {transcript_count}/{len(videos)}")
                
                if args.add_comments:
                    comments_count = sum(1 for v in videos if v.get('comments_retrieved'))
                    total_comments = sum(v.get('comments_count', 0) for v in videos)
                    pagination_mode = getattr(args, 'pagination_mode', 'limited')
                    
                    logger.info(f"💬 Commenti ottenuti: {comments_count}/{len(videos)} video ({total_comments:,} commenti totali)")
                    logger.info(f"🔄 Modalità pagination: {pagination_mode}")
                    
                    if pagination_mode != 'limited':
                        paginated_count = sum(1 for v in videos if v.get('pagination_used'))
                        total_time = sum(v.get('collection_duration_seconds', 0) for v in videos)
                        logger.info(f"📊 Video con pagination: {paginated_count}/{len(videos)}")
                        logger.info(f"⏱️  Tempo raccolta commenti: {total_time:.1f} secondi")
                    
                    if args.include_replies:
                        total_replies = sum(v.get('total_replies_count', 0) for v in videos)
                        logger.info(f"💬➡️ Risposte ottenute: {total_replies:,} risposte totali")
                
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