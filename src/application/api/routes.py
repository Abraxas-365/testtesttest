"""API routes for the agent service."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from src.application.di import get_container


router = APIRouter()


class InvokeRequest(BaseModel):
    """Request model for invoking an agent."""
    agent_id: str = None
    agent_name: str = None
    prompt: str
    user_id: str = "default_user"
    session_id: Optional[str] = None
    persist_session: bool = False  # Enable to save conversation history


class InvokeResponse(BaseModel):
    """Response model for agent invocation."""
    response: str
    agent_id: Optional[str] = None
    agent_name: Optional[str] = None
    session_id: Optional[str] = None


class AgentInfo(BaseModel):
    """Information about an agent."""
    agent_id: str
    name: str
    description: str
    model: str
    tools_count: int


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@router.post("/invoke", response_model=InvokeResponse)
async def invoke_agent(request: InvokeRequest):
    """
    Invoke an agent with a prompt.

    Either agent_id or agent_name must be provided.
    Set persist_session=true to save conversation history.
    """
    if not request.agent_id and not request.agent_name:
        raise HTTPException(
            status_code=400,
            detail="Either agent_id or agent_name must be provided"
        )

    container = get_container()
    agent_service = await container.get_agent_service()

    try:
        if request.agent_id:
            response = await agent_service.invoke_agent(
                request.agent_id,
                request.prompt,
                user_id=request.user_id,
                session_id=request.session_id,
                persist_session=request.persist_session
            )
            return InvokeResponse(
                response=response,
                agent_id=request.agent_id,
                session_id=request.session_id
            )
        else:
            response = await agent_service.invoke_agent_by_name(
                request.agent_name,
                request.prompt,
                user_id=request.user_id,
                session_id=request.session_id,
                persist_session=request.persist_session
            )
            return InvokeResponse(
                response=response,
                agent_name=request.agent_name,
                session_id=request.session_id
            )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error invoking agent: {str(e)}")


@router.get("/agents", response_model=list[AgentInfo])
async def list_agents(enabled_only: bool = True):
    """
    List all available agents.

    Args:
        enabled_only: If True, return only enabled agents
    """
    container = get_container()
    agent_service = await container.get_agent_service()

    try:
        configs = await agent_service.repository.list_agents(enabled_only)

        return [
            AgentInfo(
                agent_id=config.agent_id,
                name=config.name,
                description=config.description,
                model=config.model.model_name,
                tools_count=len(config.tools)
            )
            for config in configs
        ]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing agents: {str(e)}")


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    """Get detailed information about an agent."""
    container = get_container()
    agent_service = await container.get_agent_service()

    try:
        config = await agent_service.repository.get_agent_by_id(agent_id)

        if not config:
            raise HTTPException(status_code=404, detail="Agent not found")

        return {
            "agent_id": config.agent_id,
            "name": config.name,
            "description": config.description,
            "instruction": config.instruction,
            "model": {
                "model_name": config.model.model_name,
                "temperature": config.model.temperature,
                "max_tokens": config.model.max_tokens,
            },
            "tools": [
                {
                    "tool_id": tool.tool_id,
                    "tool_name": tool.tool_name,
                    "tool_type": tool.tool_type,
                    "description": tool.description,
                }
                for tool in config.tools
            ],
            "sub_agent_ids": config.sub_agent_ids,
            "enabled": config.enabled,
            "metadata": config.metadata,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting agent: {str(e)}")


@router.post("/agents/{agent_id}/reload")
async def reload_agent(agent_id: str):
    """Reload an agent configuration from the database."""
    container = get_container()
    agent_service = await container.get_agent_service()

    try:
        agent = await agent_service.reload_agent(agent_id)

        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        return {"status": "success", "message": f"Agent {agent_id} reloaded"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reloading agent: {str(e)}")
