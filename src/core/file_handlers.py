#!/usr/bin/env python3
"""
File Handlers - Gestione salvataggio Parquet e upload S3
✅ Supporto per formati JSONL e Parquet
✅ Upload automatico su S3 con gestione errori
✅ Compatibilità con strutture nested TikTok
"""

import os
import json
import boto3
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from botocore.exceptions import ClientError, NoCredentialsError
import logging


def save_videos_jsonl(videos: List[Dict], search_type: str, search_term: str, args, logger) -> Optional[str]:
    """
    ✅ ORIGINALE: Salva video in formato JSONL (mantienuto per compatibilità)
    
    Args:
        videos: Lista video da salvare
        search_type: Tipo di ricerca
        search_term: Termine di ricerca  
        args: Argomenti CLI
        logger: Logger
        
    Returns:
        str: Path del file salvato o None se errore
    """
    if not videos:
        logger.warning("⚠️  Nessun video da salvare")
        return None
    
    try:
        # Funzione per nome file incrementale
        def get_next_filename(output_dir, prefix="tiktok_scraper", extension=".jsonl"):
            """Trova il prossimo numero disponibile per il file"""
            counter = 1
            while True:
                filename = f"{output_dir}/{prefix}_#{counter}{extension}"
                if not os.path.exists(filename):
                    return filename, counter
                counter += 1
        
        # Nome file con info multiple users
        if search_type == 'multiple_users':
            base_prefix = args.output_prefix if args.output_prefix else f"tiktok_multiple_users"
        else:
            base_prefix = args.output_prefix if args.output_prefix else "tiktok_scraper"
            
        filename, file_number = get_next_filename(args.output_dir, base_prefix, ".jsonl")
        
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
                    'search_term': search_term,
                    'file_number': file_number,
                    'format': 'jsonl'
                })
                
                # Scrivi una riga JSON per video (formato JSONL)
                json_line = json.dumps(video_with_metadata, ensure_ascii=False, default=str)
                f.write(json_line + '\n')
        
        logger.info(f"💾 File JSONL salvato: {filename}")
        return filename
        
    except Exception as e:
        logger.error(f"❌ Errore salvataggio JSONL: {e}")
        return None


def save_videos_parquet(videos: List[Dict], search_type: str, search_term: str, args, logger) -> Optional[str]:
    """
    ✅ NUOVO: Salva video in formato Parquet per analytics veloci
    
    Args:
        videos: Lista video da salvare
        search_type: Tipo di ricerca
        search_term: Termine di ricerca
        args: Argomenti CLI
        logger: Logger
        
    Returns:
        str: Path del file salvato o None se errore
    """
    if not videos:
        logger.warning("⚠️  Nessun video da salvare")
        return None
    
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
        
        # Funzione per nome file incrementale  
        def get_next_filename(output_dir, prefix="tiktok_scraper", extension=".parquet"):
            """Trova il prossimo numero disponibile per il file"""
            counter = 1
            while True:
                filename = f"{output_dir}/{prefix}_#{counter}{extension}"
                if not os.path.exists(filename):
                    return filename, counter
                counter += 1
        
        # Nome file con info multiple users
        if search_type == 'multiple_users':
            base_prefix = args.output_prefix if args.output_prefix else f"tiktok_multiple_users"
        else:
            base_prefix = args.output_prefix if args.output_prefix else "tiktok_scraper"
            
        filename, file_number = get_next_filename(args.output_dir, base_prefix, ".parquet")
        
        # Aggiungi metadati a ogni video
        collection_time = datetime.now().isoformat()
        
        processed_videos = []
        for video in videos:
            # Aggiungi metadati di collezione a ogni video
            video_with_metadata = video.copy()
            video_with_metadata.update({
                'collection_time': collection_time,
                'search_type': search_type,
                'search_term': search_term,
                'file_number': file_number,
                'format': 'parquet'
            })
            processed_videos.append(video_with_metadata)
        
        # Converti in DataFrame pandas
        logger.debug("🔄 Convertendo dati in DataFrame pandas...")
        df = pd.json_normalize(processed_videos)
        
        # ✅ Gestione colonne con strutture complesse (comments, replies)
        logger.debug(f"📊 DataFrame shape: {df.shape} (righe: {len(df)}, colonne: {len(df.columns)})")
        
        # Converti in Table PyArrow per maggiore controllo
        logger.debug("🔄 Convertendo in PyArrow Table...")
        table = pa.Table.from_pandas(df)
        
        # Salva con compressione ottimale per analytics
        logger.debug(f"💾 Salvando Parquet: {filename}")
        pq.write_table(
            table, 
            filename,
            compression='snappy',  # Ottimo balance tra velocità e compressione
            use_dictionary=True,   # Efficiente per stringhe ripetute (username, etc.)
            write_statistics=True  # Metadati per query veloci
        )
        
        # Statistiche file
        file_size = os.path.getsize(filename)
        file_size_mb = file_size / (1024 * 1024)
        
        logger.info(f"💾 File Parquet salvato: {filename}")
        logger.info(f"📊 Dimensione: {file_size_mb:.2f} MB")
        logger.info(f"🗂️  Righe: {len(df):,}, Colonne: {len(df.columns)}")
        
        return filename
        
    except ImportError:
        logger.error("❌ PyArrow non installato. Installa con: pip install pyarrow")
        return None
    except Exception as e:
        logger.error(f"❌ Errore salvataggio Parquet: {e}")
        logger.debug(f"🔍 Dettaglio errore:", exc_info=True)
        return None


def upload_to_s3(local_file_path: str, s3_bucket: str, s3_path: str, args, logger) -> bool:
    """
    ✅ NUOVO: Upload file su S3 con gestione errori robusta
    
    Args:
        local_file_path: Path del file locale
        s3_bucket: Nome bucket S3
        s3_path: Path nel bucket (senza bucket name)
        args: Argomenti CLI
        logger: Logger
        
    Returns:
        bool: True se upload riuscito, False altrimenti
    """
    try:
        if not os.path.exists(local_file_path):
            logger.error(f"❌ File locale non trovato: {local_file_path}")
            return False
        
        # Estrai nome file
        filename = os.path.basename(local_file_path)
        s3_key = f"{s3_path}{filename}" if s3_path else filename
        
        logger.info(f"☁️  Uploading su S3: s3://{s3_bucket}/{s3_key}")
        
        # Crea client S3
        s3_client = boto3.client('s3')
        
        # Dimensione file per progress
        file_size = os.path.getsize(local_file_path)
        file_size_mb = file_size / (1024 * 1024)
        
        logger.info(f"📤 Upload in corso... ({file_size_mb:.2f} MB)")
        
        # Upload con metadata
        extra_args = {
            'Metadata': {
                'uploaded_by': 'tiktok_scraper',
                'upload_time': datetime.now().isoformat(),
                'search_type': getattr(args, 'search_type', 'unknown'),
                'format': 'parquet' if local_file_path.endswith('.parquet') else 'jsonl'
            }
        }
        
        # Se è un file Parquet, aggiungi content-type appropriato
        if local_file_path.endswith('.parquet'):
            extra_args['ContentType'] = 'application/octet-stream'
        elif local_file_path.endswith('.jsonl'):
            extra_args['ContentType'] = 'application/x-ndjson'
        
        s3_client.upload_file(
            local_file_path,
            s3_bucket, 
            s3_key,
            ExtraArgs=extra_args
        )
        
        # Verifica upload
        try:
            s3_client.head_object(Bucket=s3_bucket, Key=s3_key)
            logger.info(f"✅ Upload completato: s3://{s3_bucket}/{s3_key}")
            
            # URL per accesso (se bucket pubblico)
            s3_url = f"https://{s3_bucket}.s3.amazonaws.com/{s3_key}"
            logger.debug(f"🔗 URL S3: {s3_url}")
            
            return True
            
        except ClientError as e:
            logger.error(f"❌ Verifica upload fallita: {e}")
            return False
            
    except NoCredentialsError:
        logger.error("❌ Credenziali AWS non trovate!")
        logger.info("💡 Configura credenziali AWS:")
        logger.info("   - AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY")
        logger.info("   - aws configure")
        logger.info("   - IAM Role (se su EC2)")
        return False
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        
        if error_code == 'NoSuchBucket':
            logger.error(f"❌ Bucket S3 non trovato: {s3_bucket}")
        elif error_code == 'AccessDenied':
            logger.error(f"❌ Accesso negato al bucket S3: {s3_bucket}")
            logger.info("💡 Verifica permessi IAM per s3:PutObject")
        else:
            logger.error(f"❌ Errore S3 ({error_code}): {e}")
        
        return False
        
    except Exception as e:
        logger.error(f"❌ Errore generico upload S3: {e}")
        logger.debug(f"🔍 Dettaglio errore:", exc_info=True)
        return False


def save_and_upload_videos(videos: List[Dict], search_type: str, search_term: str, args, logger) -> Tuple[Optional[str], bool]:
    """
    ✅ NUOVO: Funzione master che gestisce salvataggio e upload in base ai parametri CLI
    
    Args:
        videos: Lista video da salvare
        search_type: Tipo di ricerca
        search_term: Termine di ricerca
        args: Argomenti CLI
        logger: Logger
        
    Returns:
        Tuple[str, bool]: (local_file_path, s3_upload_success)
    """
    if not videos:
        logger.warning("⚠️  Nessun video da salvare")
        return None, False
    
    # 1. Salvataggio locale nel formato scelto
    logger.info(f"💾 Salvando in formato {args.output_format.upper()}...")
    
    if args.output_format == 'parquet':
        local_file_path = save_videos_parquet(videos, search_type, search_term, args, logger)
    else:  # jsonl (default)
        local_file_path = save_videos_jsonl(videos, search_type, search_term, args, logger)
    
    if not local_file_path:
        logger.error("❌ Salvataggio locale fallito!")
        return None, False
    
    # 2. Statistiche salvataggio
    print_save_statistics(videos, local_file_path, args, logger)
    
    # 3. Upload S3 se richiesto
    s3_upload_success = False
    
    if args.s3_uri and args.s3_auto_upload:
        logger.info(f"☁️  Iniziando upload su S3...")
        s3_upload_success = upload_to_s3(local_file_path, args.s3_bucket, args.s3_path, args, logger)
        
        if s3_upload_success:
            logger.info("✅ Upload S3 completato!")
            
            # 4. Rimuovi file locale se s3-only
            if args.s3_only:
                try:
                    os.remove(local_file_path)
                    logger.info(f"🗑️  File locale rimosso (S3-only mode): {local_file_path}")
                except Exception as e:
                    logger.warning(f"⚠️  Errore rimozione file locale: {e}")
        else:
            logger.error("❌ Upload S3 fallito - file mantenuto localmente")
    
    elif args.s3_uri and not args.s3_auto_upload:
        logger.info(f"💡 File salvato localmente. Per upload manuale usa:")
        logger.info(f"   aws s3 cp {local_file_path} {args.s3_uri}")
    
    return local_file_path, s3_upload_success


def print_save_statistics(videos: List[Dict], local_file_path: str, args, logger):
    """
    ✅ NUOVO: Stampa statistiche dettagliate del salvataggio
    
    Args:
        videos: Lista video salvati
        local_file_path: Path del file salvato
        args: Argomenti CLI
        logger: Logger
    """
    try:
        # Statistiche file
        file_size = os.path.getsize(local_file_path)
        file_size_mb = file_size / (1024 * 1024)
        
        logger.info(f"📊 Video salvati: {len(videos)} (formato: {args.output_format.upper()})")
        logger.info(f"📁 Dimensione file: {file_size_mb:.2f} MB")
        
        # Statistiche multiple users se applicabile
        if hasattr(args, 'users_list') and args.users_list:
            unique_users = set(video.get('source_user', 'unknown') for video in videos)
            logger.info(f"👥 Utenti unici: {len(unique_users)}")
            
            user_counts = {}
            for video in videos:
                user = video.get('source_user', 'unknown')
                user_counts[user] = user_counts.get(user, 0) + 1
            
            top_user = max(user_counts.items(), key=lambda x: x[1]) if user_counts else ('N/A', 0)
            logger.info(f"🏆 Utente più produttivo: @{top_user[0]} ({top_user[1]} video)")
        
        # Statistiche transcript
        if args.add_transcript:
            transcript_count = sum(1 for video in videos if video.get('transcript_available'))
            logger.info(f"🎙️  Video con transcript: {transcript_count}/{len(videos)}")
            
        # Statistiche commenti  
        if args.add_comments:
            comments_count = sum(1 for video in videos if video.get('comments_retrieved'))
            total_comments = sum(video.get('comments_count', 0) for video in videos)
            logger.info(f"💬 Video con commenti: {comments_count}/{len(videos)}")
            logger.info(f"📝 Commenti totali: {total_comments:,}")
            
            # Statistiche pagination
            if getattr(args, 'pagination_mode', 'limited') != 'limited':
                paginated_count = sum(1 for video in videos if video.get('pagination_used'))
                total_collection_time = sum(video.get('collection_duration_seconds', 0) for video in videos)
                logger.info(f"🔄 Video con pagination: {paginated_count}/{len(videos)}")
                logger.info(f"⏱️  Tempo raccolta totale: {total_collection_time:.1f} secondi")
            
            # Statistiche risposte
            if args.include_replies:
                total_replies = sum(video.get('total_replies_count', 0) for video in videos)
                logger.info(f"💬➡️ Risposte totali: {total_replies:,}")
        
    except Exception as e:
        logger.warning(f"⚠️  Errore nel calcolo statistiche: {e}")


def list_s3_files(s3_bucket: str, s3_path: str, logger) -> List[str]:
    """
    ✅ UTILITY: Lista file nel bucket S3 (utile per verifiche)
    
    Args:
        s3_bucket: Nome bucket
        s3_path: Path nel bucket
        logger: Logger
        
    Returns:
        List[str]: Lista file trovati
    """
    try:
        s3_client = boto3.client('s3')
        
        response = s3_client.list_objects_v2(
            Bucket=s3_bucket,
            Prefix=s3_path
        )
        
        files = []
        if 'Contents' in response:
            for obj in response['Contents']:
                files.append(obj['Key'])
                
        logger.info(f"📋 Trovati {len(files)} file in s3://{s3_bucket}/{s3_path}")
        return files
        
    except Exception as e:
        logger.error(f"❌ Errore listing S3: {e}")
        return []


def download_from_s3(s3_bucket: str, s3_key: str, local_path: str, logger) -> bool:
    """
    ✅ UTILITY: Download file da S3 (utile per recupero dati)
    
    Args:
        s3_bucket: Nome bucket
        s3_key: Chiave S3 del file
        local_path: Path locale dove salvare
        logger: Logger
        
    Returns:
        bool: True se download riuscito
    """
    try:
        s3_client = boto3.client('s3')
        
        logger.info(f"📥 Downloading da S3: s3://{s3_bucket}/{s3_key}")
        
        s3_client.download_file(s3_bucket, s3_key, local_path)
        
        # Verifica download
        if os.path.exists(local_path):
            file_size = os.path.getsize(local_path) / (1024 * 1024)
            logger.info(f"✅ Download completato: {local_path} ({file_size:.2f} MB)")
            return True
        else:
            logger.error("❌ File non trovato dopo download")
            return False
            
    except Exception as e:
        logger.error(f"❌ Errore download S3: {e}")
        return False