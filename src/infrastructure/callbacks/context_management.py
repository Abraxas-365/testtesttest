"""Context management callbacks for ADK agents."""

import logging
from google.genai import types

logger = logging.getLogger(__name__)


def safe_context_management_callback(callback_context, llm_request):
    """
    Safely manage conversation history while preserving tool call/response pairs.
    
    This callback prevents context window overflow by intelligently truncating
    history while ensuring function_call and function_response events remain paired.
    
    Args:
        callback_context: ADK CallbackContext object
        llm_request: LlmRequest object containing the prompt to be sent to LLM
        
    Returns:
        None to proceed with the (possibly modified) request
    """
    MAX_HISTORY_MESSAGES = 30 
    
    contents = llm_request.contents
    original_count = len(contents)
    
    if original_count <= MAX_HISTORY_MESSAGES:
        return None  
    
    logger.info(f"🔧 Context management: {original_count} messages, applying safe truncation")
    
    current_message = contents[-1]
    
    keep_contents = []
    pending_function_calls = {}  
    
    for content in reversed(contents[:-1]):
        if len(keep_contents) >= MAX_HISTORY_MESSAGES - 1:
            if not pending_function_calls:
                break  
        
        should_keep = False
        
        if hasattr(content, 'parts') and content.parts:
            for part in content.parts:
                if hasattr(part, 'function_response') and part.function_response:
                    func_response = part.function_response
                    pending_function_calls[func_response.id] = True
                    should_keep = True
                    logger.debug(f"  📥 Found function_response: {func_response.name} (id={func_response.id})")
                    break
                
                elif hasattr(part, 'function_call') and part.function_call:
                    func_call = part.function_call
                    if func_call.id in pending_function_calls:
                        del pending_function_calls[func_call.id]
                        should_keep = True
                        logger.debug(f"  📤 Found matching function_call: {func_call.name} (id={func_call.id})")
                    elif len(keep_contents) < MAX_HISTORY_MESSAGES - 1:
                        should_keep = True
                        logger.debug(f"  🔧 Keeping function_call: {func_call.name}")
                    break
                
                elif hasattr(part, 'text') and part.text:
                    if not pending_function_calls and len(keep_contents) < MAX_HISTORY_MESSAGES - 1:
                        should_keep = True
                    break
        
        if should_keep:
            keep_contents.append(content)
    
    keep_contents.reverse()
    
    keep_contents.append(current_message)
    
    llm_request.contents = keep_contents
    new_count = len(keep_contents)
    
    logger.info(
        f"✅ Context managed: {original_count} → {new_count} messages "
        f"(preserved {len([c for c in keep_contents if any(hasattr(p, 'function_call') for p in getattr(c, 'parts', []))])} tool pairs)"
    )
    
    if pending_function_calls:
        logger.warning(
            f"⚠️ Could not find matching function_calls for {len(pending_function_calls)} responses. "
            f"This may cause issues."
        )
    
    return None  
