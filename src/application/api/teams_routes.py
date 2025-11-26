"""
API routes for Microsoft Teams integration with file support.
"""
import os
import logging
import asyncio
from fastapi import APIRouter, Request, BackgroundTasks
import httpx

from src.application.di import get_container
from src.services.teams_integration import TeamsAgentIntegration
from src.services.document_service import TeamsDocumentService

logger = logging.getLogger(__name__)
router = APIRouter()


async def get_bot_token(tenant_id: str, client_id: str, client_secret: str) -> str:
    """Get Bot Framework access token."""
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "https://api.botframework.com/.default"
            }
        )
        
        if token_response.status_code != 200:
            raise Exception(f"Failed to get token: {token_response.text}")
        
        return token_response.json()["access_token"]


async def send_typing_indicator(
    service_url: str,
    conversation_id: str,
    access_token: str
):
    """
    Send typing indicator to Teams.
    Shows the "... is typing" animation to the user.
    """
    typing_url = f"{service_url}/v3/conversations/{conversation_id}/activities"
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            typing_response = await client.post(
                typing_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                },
                json={
                    "type": "typing"
                }
            )
            
            if typing_response.status_code in [200, 201]:
                logger.info("✅ Typing indicator sent")
            else:
                logger.warning(f"⚠️ Typing indicator failed: {typing_response.status_code}")
                
    except Exception as e:
        logger.warning(f"⚠️ Error sending typing indicator: {e}")


async def send_teams_reply(
    service_url: str,
    conversation_id: str,
    activity_id: str,
    message_text: str,
    access_token: str
):
    """Send reply to Teams."""
    reply_url = f"{service_url}/v3/conversations/{conversation_id}/activities/{activity_id}"
    
    logger.info(f"💡 Posting reply to Teams")
    logger.info(f"   URL: {reply_url[:100]}...")
    logger.info(f"   Message length: {len(message_text)} chars")
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        reply_response = await client.post(
            reply_url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            },
            json={
                "type": "message",
                "text": message_text
            }
        )
        
        logger.info(f"💬 Reply status: {reply_response.status_code}")
        
        if reply_response.status_code not in [200, 201]:
            logger.error(f"❌ Failed to send: {reply_response.text}")
            raise Exception(f"Teams API error: {reply_response.status_code}")
        
        logger.info("✅ Message sent successfully to Teams!")


async def send_processing_message_if_slow(
    service_url: str,
    conversation_id: str,
    activity_id: str,
    access_token: str,
    delay_seconds: int = 10
):
    """
    Envía mensaje de 'procesando' solo si la operación tarda más de X segundos.
    
    Args:
        service_url: Teams service URL
        conversation_id: Teams conversation ID
        activity_id: ID del mensaje original
        access_token: Bot Framework token
        delay_seconds: Segundos a esperar antes de enviar mensaje (default: 10)
    """
    try:
        # Esperar X segundos
        await asyncio.sleep(delay_seconds)
        
        # Si llegamos aquí, el procesamiento está tardando mucho
        logger.info(f"⏰ Procesamiento > {delay_seconds}s → Enviando mensaje proactivo")
        
        await send_teams_reply(
            service_url=service_url,
            conversation_id=conversation_id,
            activity_id=activity_id,
            message_text=(
                "⏳ **Procesando tu solicitud...**\n\n"
                "Esto puede tomar un momento. Te enviaré la respuesta en breve. 🔄"
            ),
            access_token=access_token
        )
        
        # Continuar enviando typing indicators cada 10s después del mensaje
        while True:
            await asyncio.sleep(10)
            await send_typing_indicator(service_url, conversation_id, access_token)
            logger.info("🔄 Typing indicator enviado (procesamiento largo)")
            
    except asyncio.CancelledError:
        # El procesamiento terminó rápido (< delay_seconds)
        logger.info(f"✅ Respuesta rápida (< {delay_seconds}s), sin mensaje proactivo")
        raise
    except Exception as e:
        logger.warning(f"⚠️ Error en mensaje proactivo: {e}")


@router.post("/teams/message")
async def process_teams_message(request: Request):
    """
    Process message from Microsoft Teams bot.
    Handles text messages and file attachments (PDF/DOCX).
    Shows typing indicator while processing.
    """
    try:
        body = await request.json()
        
        logger.info("="*60)
        logger.info("📨 RECEIVED TEAMS MESSAGE")
        logger.info("="*60)
        
        activity_type = body.get("type", "")
        
        if activity_type != "message":
            logger.info(f"⭕️ Ignoring activity type: {activity_type}")
            return {"status": "ok"}
        
        user_message = body.get("text", "").strip()
        attachments = body.get("attachments", [])
        
        from_data = body.get("from", {})
        user_id = from_data.get("id", "")
        user_name = from_data.get("name", "Unknown User")
        
        service_url = body.get("serviceUrl", "")
        conversation = body.get("conversation", {})
        conversation_id = conversation.get("id", "")
        activity_id = body.get("id", "")
        
        logger.info(f"👤 User: {user_name}")
        logger.info(f"💬 Message: '{user_message}'")
        logger.info(f"📎 Attachments: {len(attachments)}")
        
        try:
            tenant_id = os.getenv("GRAPH_TENANT_ID")
            client_id = os.getenv("GRAPH_CLIENT_ID")
            client_secret = os.getenv("GRAPH_CLIENT_SECRET")
            
            access_token = await get_bot_token(tenant_id, client_id, client_secret)
            
            # Enviar typing indicator inicial
            await send_typing_indicator(
                service_url=service_url,
                conversation_id=conversation_id,
                access_token=access_token
            )
        except Exception as typing_error:
            logger.warning(f"⚠️ Typing indicator failed: {typing_error}")
        
        processed_files = []
        
        if attachments:
            logger.info("="*60)
            logger.info("📥 PROCESSING FILE ATTACHMENTS")
            logger.info("="*60)
            
            bot_token = await get_bot_token(tenant_id, client_id, client_secret)
            
            project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
            location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-east4")
            doc_service = TeamsDocumentService(project_id, location)
            
            for idx, attachment in enumerate(attachments):
                content_type = attachment.get("contentType", "")
                name = attachment.get("name", f"file_{idx}")
                
                logger.info(f"📄 Attachment {idx + 1}:")
                logger.info(f"   Name: {name}")
                logger.info(f"   Type: {content_type}")
                
                if content_type == "application/vnd.microsoft.teams.file.download.info":
                    logger.info("✅ Teams file detected")
                    
                    content = attachment.get("content", {})
                    download_url = content.get("downloadUrl", "")
                    file_type = content.get("fileType", "")
                    
                    logger.info(f"   Download URL: {download_url[:80]}...")
                    logger.info(f"   File type: {file_type}")
                    
                    try:
                        file_bytes = await doc_service.download_file(
                            download_url,
                            bot_token=bot_token
                        )
                        
                        if file_type == "pdf":
                            extraction = await doc_service.extract_text_from_pdf(file_bytes)
                        elif file_type == "docx":
                            extraction = await doc_service.extract_text_from_docx(file_bytes)
                        else:
                            logger.warning(f"⚠️ Unsupported file type: {file_type}")
                            extraction = {"success": False, "error": f"Unsupported file type: {file_type}"}
                        
                        if extraction.get("success"):
                            processed_files.append({
                                "filename": name,
                                "text": extraction["text"],
                                "char_count": extraction["char_count"],
                                "method": extraction["method"]
                            })
                            logger.info(f"✅ Extracted {extraction['char_count']} chars from {name}")
                        else:
                            processed_files.append({
                                "filename": name,
                                "error": extraction.get("error", "Unknown error")
                            })
                            logger.error(f"❌ Extraction failed: {extraction.get('error')}")
                    
                    except Exception as e:
                        logger.error(f"❌ Error processing {name}: {e}")
                        processed_files.append({
                            "filename": name,
                            "error": str(e)
                        })
                
                elif content_type.startswith("image/"):
                    logger.info("🖼️ Inline image detected")
                    
                    content_url = attachment.get("contentUrl", "")
                    
                    try:
                        async with httpx.AsyncClient() as client:
                            img_response = await client.get(
                                content_url,
                                headers={"Authorization": f"Bearer {bot_token}"}
                            )
                            img_response.raise_for_status()
                            
                            logger.info(f"✅ Downloaded image: {len(img_response.content)} bytes")
                            
                            processed_files.append({
                                "filename": name,
                                "text": "[Image file - vision processing not implemented]",
                                "char_count": 0
                            })
                    
                    except Exception as e:
                        logger.error(f"❌ Image download failed: {e}")
                        processed_files.append({
                            "filename": name,
                            "error": str(e)
                        })
                
                else:
                    logger.warning(f"⚠️ Unknown attachment type: {content_type}")
        
        full_prompt = user_message if user_message else "Please analyze the attached document(s)."
        
        if processed_files:
            full_prompt += "\n\n--- 📎 Attached Documents ---\n"
            
            for doc in processed_files:
                if "error" not in doc:
                    full_prompt += f"\n[File: {doc['filename']}]\n"
                    full_prompt += f"{doc['text']}\n"
                    full_prompt += f"\n--- End of {doc['filename']} ({doc['char_count']} characters) ---\n"
                else:
                    full_prompt += f"\n[File: {doc['filename']}] - Error: {doc['error']}\n"
        
        logger.info(f"📝 Complete prompt: {len(full_prompt)} characters")
        
        logger.info("="*60)
        logger.info("🤖 ROUTING TO AGENT")
        logger.info("="*60)
        
        container = get_container()
        agent_service = await container.get_agent_service()
        group_mapping_repo = await container.init_group_mapping_repository()
        
        teams_integration = TeamsAgentIntegration(agent_service, group_mapping_repo)
        
        # NUEVA LÓGICA: Mensaje proactivo solo si demora > 10 segundos
        slow_message_task = None
        try:
            # Iniciar temporizador de 10 segundos
            slow_message_task = asyncio.create_task(
                send_processing_message_if_slow(
                    service_url=service_url,
                    conversation_id=conversation_id,
                    activity_id=activity_id,
                    access_token=access_token,
                    delay_seconds=10  # Configurable: cambiar aquí si necesitas más/menos tiempo
                )
            )
            
            logger.info("⏱️ Timer iniciado: enviará mensaje si demora > 10s")
            
            # Procesar el mensaje (puede tardar 2s o 60s)
            result = await teams_integration.process_message(
                user_message=full_prompt,
                aad_user_id=user_id,
                user_name=user_name,
                session_id=conversation_id,
                from_data=from_data
            )
            
        finally:
            # Cancelar el temporizador (si aún no se envió el mensaje)
            if slow_message_task:
                slow_message_task.cancel()
                try:
                    await slow_message_task
                except asyncio.CancelledError:
                    pass
                logger.info("✅ Procesamiento completado")
        
        response_text = result.get("response", "Sorry, I couldn't process your request.")
        
        if processed_files:
            summary = "\n\n---\n📎 **Processed files:**\n"
            for doc in processed_files:
                if "error" not in doc:
                    summary += f"✅ {doc['filename']} ({doc['char_count']:,} characters)\n"
                else:
                    summary += f"❌ {doc['filename']} - {doc['error']}\n"
            
            response_text = summary + "\n" + response_text
        
        logger.info(f"🤖 Agent response ready ({len(response_text)} chars)")
        
        logger.info("="*60)
        logger.info("📤 SENDING RESPONSE TO TEAMS")
        logger.info("="*60)
        
        try:
            await send_teams_reply(
                service_url=service_url,
                conversation_id=conversation_id,
                activity_id=activity_id,
                message_text=response_text,
                access_token=access_token
            )
            
            logger.info("="*60)
            logger.info("✅ REQUEST COMPLETED SUCCESSFULLY")
            logger.info("="*60)
            
        except Exception as send_error:
            logger.error(f"❌ Error sending reply: {send_error}")
        
        return {"status": "ok"}
    
    except Exception as e:
        logger.error("="*60)
        logger.error("❌ ERROR IN TEAMS MESSAGE HANDLER")
        logger.error("="*60)
        logger.error(f"Error: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


@router.get("/teams/health")
async def teams_health():
    """Health check."""
    return {
        "status": "healthy",
        "service": "Teams Integration with Smart Proactive Messages",
        "features": {
            "smart_proactive_messaging": True,
            "threshold": "10 seconds",
            "behavior": "Sends 'processing' message only if operation takes > 10s",
            "typing_indicator": True,
            "file_support": True,
            "supported_types": [
                "application/vnd.microsoft.teams.file.download.info (PDF, DOCX)",
                "image/* (inline images)"
            ],
            "processing": "PyPDF2 + python-docx + Gemini (optional)"
        }
    }
