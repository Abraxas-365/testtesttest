"""Metadata fetcher for RAG sources."""

import os
import logging
import re
from typing import Optional, Dict, Any
from datetime import datetime
from urllib.parse import urlparse, unquote
from dateutil import parser as date_parser

try:
    from msgraph.generated.models.o_data_errors.o_data_error import ODataError
except ImportError:
    ODataError = None

logger = logging.getLogger(__name__)


class SourceMetadataFetcher:
    """Fetch metadata from various source types (GCS, SharePoint, etc.)."""
    
    def __init__(self):
        self.gcs_client = None
        self.graph_client = None
        self._init_clients()
    
    def _init_clients(self):
        """Initialize API clients."""
        try:
            from google.cloud import storage
            self.gcs_client = storage.Client()
            logger.info("✅ GCS client initialized")
        except Exception as e:
            logger.warning(f"⚠️ GCS client not available: {e}")
        
        try:
            from msgraph import GraphServiceClient
            from azure.identity import ClientSecretCredential
            
            tenant_id = os.getenv('GRAPH_TENANT_ID')
            client_id = os.getenv('GRAPH_CLIENT_ID')
            client_secret = os.getenv('GRAPH_CLIENT_SECRET')
            
            if all([tenant_id, client_id, client_secret]):
                credential = ClientSecretCredential(
                    tenant_id=tenant_id,
                    client_id=client_id,
                    client_secret=client_secret
                )
                self.graph_client = GraphServiceClient(
                    credentials=credential,
                    scopes=['https://graph.microsoft.com/.default']
                )
                logger.info("✅ Microsoft Graph client initialized")
            else:
                logger.warning("⚠️ Graph credentials not configured")
        except Exception as e:
            logger.warning(f"⚠️ Graph client not available: {e}")
    
    async def get_metadata(self, source_uri: str) -> Dict[str, Any]:
        """
        Get metadata for a source URI.
        
        🛡️ FAULT TOLERANT: Returns minimal metadata if fetch fails.
        """
        if not source_uri:
            return {'metadata_available': False}
        
        try:
            parsed = urlparse(source_uri)
            
            if parsed.scheme == 'gs':
                return await self._get_gcs_metadata(source_uri)
            
            elif 'sharepoint.com' in source_uri.lower():
                return await self._get_sharepoint_metadata(source_uri)
            
            elif parsed.scheme in ['http', 'https']:
                return {
                    'source_type': 'web',
                    'url': source_uri,
                    'file_name': self._extract_filename_from_url(source_uri),
                    'metadata_available': False
                }
            
            else:
                logger.warning(f"Unknown source type: {source_uri}")
                return {
                    'source_type': 'unknown',
                    'uri': source_uri,
                    'file_name': self._extract_filename_from_url(source_uri),
                    'metadata_available': False
                }
                
        except Exception as e:
            logger.error(f"❌ Error fetching metadata for {source_uri}: {e}")
            return {
                'file_name': self._extract_filename_from_url(source_uri),
                'metadata_available': False,
                'metadata_error': str(e)
            }

    async def _get_gcs_metadata(self, gcs_uri: str) -> Dict[str, Any]:
        """
        Fetch metadata from Google Cloud Storage.
        
        🛡️ FAULT TOLERANT: Returns minimal metadata if fetch fails.
        """
        if not self.gcs_client:
            return {
                'source_type': 'gcs', 'uri': gcs_uri, 'file_name': self._extract_filename_from_url(gcs_uri),
                'metadata_available': False, 'metadata_error': 'GCS client not available'
            }
        
        try:
            path = gcs_uri.replace('gs://', '')
            bucket_name, blob_path = path.split('/', 1)
            bucket = self.gcs_client.bucket(bucket_name)
            blob = await asyncio.to_thread(bucket.get_blob, blob_path)

            if not blob:
                raise FileNotFoundError(f"GCS object not found: {gcs_uri}")

            metadata = {
                'source_type': 'gcs', 'uri': gcs_uri, 'file_name': blob.name.split('/')[-1],
                'full_path': blob.name, 'size': blob.size,
                'size_human': self._human_readable_size(blob.size), 'content_type': blob.content_type,
                'created': blob.time_created.isoformat() if blob.time_created else None,
                'updated': blob.updated.isoformat() if blob.updated else None,
                'created_human': self._human_readable_time(blob.time_created),
                'updated_human': self._human_readable_time(blob.updated),
                'md5_hash': blob.md5_hash, 'owner': blob.owner.get('entity') if blob.owner else None,
                'storage_class': blob.storage_class, 'metadata_available': True
            }
            
            if blob.metadata:
                metadata['custom_metadata'] = blob.metadata
            
            logger.info(f"📦 Fetched GCS metadata: {blob.name}")
            return metadata
            
        except Exception as e:
            logger.warning(f"⚠️ GCS metadata error (non-critical): {e}")
            return {
                'source_type': 'gcs', 'uri': gcs_uri, 'file_name': self._extract_filename_from_url(gcs_uri),
                'metadata_available': False, 'metadata_error': str(e)
            }

    async def _get_sharepoint_metadata(self, sharepoint_url: str) -> Dict[str, Any]:
        """
        Fetch metadata from SharePoint via Microsoft Graph.
        
        🛡️ FAULT TOLERANT: Returns minimal metadata if fetch fails.
        """
        file_name_fallback = self._extract_filename_from_url(sharepoint_url)
        
        if not self.graph_client or not ODataError:
            return {
                'source_type': 'sharepoint', 'url': sharepoint_url, 'file_name': file_name_fallback,
                'metadata_available': False, 'metadata_error': 'Graph client not available'
            }
        
        try:
            logger.info(f"🔍 Parsing SharePoint URL: {sharepoint_url}")
            parsed_data = self._parse_sharepoint_url(sharepoint_url)
            
            if not parsed_data:
                raise ValueError("Could not parse SharePoint URL structure")
            
            tenant, site_path, file_path = parsed_data['tenant'], parsed_data['site_path'], parsed_data['file_path']
            logger.info(f"  Tenant: {tenant}, Site: {site_path}, File path: {file_path}")
            
            site_result = await self.graph_client.sites.by_site_id(f"{tenant}:{site_path}").get()
            if not site_result or not site_result.id:
                raise ValueError("SharePoint site not found")

            site_id = site_result.id
            logger.info(f"✅ Found site ID: {site_id}")

            drives_result = await self.graph_client.sites.by_site_id(site_id).drives.get()
            if not drives_result or not drives_result.value:
                raise ValueError("No document libraries found in site")

            target_drive = next((d for d in drives_result.value if d.name in ['Documents', 'Shared Documents', 'Documentos']), drives_result.value[0])
            drive_id = target_drive.id
            logger.info(f"✅ Using drive: {target_drive.name} (ID: {drive_id})")

            clean_path = file_path
            for lib_name in ['Shared Documents', 'Documents', 'Documentos', 'Shared%20Documents']:
                if clean_path.startswith(f"{lib_name}/"):
                    clean_path = clean_path[len(lib_name) + 1:]
                    break
            
            logger.info(f"🔎 Looking for file item: {clean_path}")
            item_result = await self.graph_client.sites.by_site_id(site_id).drives.by_drive_id(drive_id).root.item_with_path(clean_path).get()

            if not item_result:
                raise FileNotFoundError("File not found at specified path in SharePoint")

            metadata = {
                'source_type': 'sharepoint', 'url': sharepoint_url, 'file_name': item_result.name, 'full_path': clean_path,
                'web_url': item_result.web_url, 'site_name': site_result.display_name, 'site_id': site_id,
                'drive_name': target_drive.name, 'drive_id': drive_id, 'size': item_result.size,
                'size_human': self._human_readable_size(item_result.size),
                'created': item_result.created_date_time.isoformat() if item_result.created_date_time else None,
                'updated': item_result.last_modified_date_time.isoformat() if item_result.last_modified_date_time else None,
                'created_human': self._human_readable_time(item_result.created_date_time),
                'updated_human': self._human_readable_time(item_result.last_modified_date_time),
                'created_by': item_result.created_by.user.display_name if item_result.created_by and item_result.created_by.user else None,
                'modified_by': item_result.last_modified_by.user.display_name if item_result.last_modified_by and item_result.last_modified_by.user else None,
                'content_type': item_result.file.mime_type if item_result.file else None,
                'e_tag': item_result.e_tag, 'metadata_available': True
            }
            logger.info(f"✅ Fetched SharePoint metadata for: {metadata['file_name']}")
            return metadata

        except ODataError as ode:
            error_message = str(ode.error.message) if ode.error and ode.error.message else "Unknown ODataError"
            logger.warning(f"⚠️ SharePoint metadata unavailable (ODataError): {error_message}")
            return {
                'source_type': 'sharepoint', 'url': sharepoint_url, 'file_name': file_name_fallback,
                'metadata_available': False, 'metadata_error': error_message
            }
        except Exception as e:
            logger.error(f"❌ SharePoint metadata fetch failed (non-critical): {e}")
            return {
                'source_type': 'sharepoint', 'url': sharepoint_url, 'file_name': file_name_fallback,
                'metadata_available': False, 'metadata_error': str(e)
            }
    
    def _parse_sharepoint_url(self, url: str) -> Optional[Dict[str, str]]:
        try:
            url = unquote(url)
            tenant_match = re.search(r'([\w-]+)\.sharepoint\.com', url)
            if not tenant_match: return None
            tenant = tenant_match.group(1)

            site_match = re.search(r'/sites/([\w-]+)', url)
            site_path = f"/sites/{site_match.group(1)}" if site_match else '/'

            path_match = re.search(r'/sites/[\w-]+/(.*?)(?:$|\?)', url)
            file_path = path_match.group(1).strip('/') if path_match else url.split('?')[0].split('/')[-1]

            return {'tenant': tenant, 'site_path': site_path, 'file_path': file_path}
        except Exception as e:
            logger.error(f"❌ Error parsing SharePoint URL: {e}")
            return None
    
    def _extract_filename_from_url(self, url: str) -> str:
        try:
            url = unquote(url)
            if 'file=' in url and (match := re.search(r'file=([^&]+)', url)):
                return unquote(match.group(1))
            
            path_parts = url.split('/')
            return next((part.split('?')[0] for part in reversed(path_parts) if part and '?' not in part), 'documento_desconocido')
        except Exception:
            return 'archivo_desconocido'

    def _human_readable_size(self, size_bytes: int) -> str:
        if not isinstance(size_bytes, (int, float)) or size_bytes < 0: return "0 B"
        units = ['B', 'KB', 'MB', 'GB', 'TB']
        size = float(size_bytes)
        unit_index = 0
        while size >= 1024.0 and unit_index < len(units) - 1:
            size /= 1024.0
            unit_index += 1
        return f"{size:.2f} {units[unit_index]}"
    
    def _human_readable_time(self, dt) -> str:
        if not dt: return "Unknown"
        try:
            dt = date_parser.parse(dt) if isinstance(dt, str) else dt
            now = datetime.now(dt.tzinfo)
            seconds = (now - dt).total_seconds()
            if seconds < 60: return "just now"
            minutes = seconds / 60
            if minutes < 60: return f"{int(minutes)} minute{'s' if minutes >= 2 else ''} ago"
            hours = minutes / 60
            if hours < 24: return f"{int(hours)} hour{'s' if hours >= 2 else ''} ago"
            days = hours / 24
            if days < 7: return f"{int(days)} day{'s' if days >= 2 else ''} ago"
            weeks = days / 7
            if weeks < 4.345: return f"{int(weeks)} week{'s' if weeks >= 2 else ''} ago"
            months = days / 30.437
            if months < 12: return f"{int(months)} month{'s' if months >= 2 else ''} ago"
            years = days / 365.25
            return f"{int(years)} year{'s' if years >= 2 else ''} ago"
        except Exception:
            return "Unknown"

