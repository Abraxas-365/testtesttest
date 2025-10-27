"""Sample tool implementations for ADK agents."""

from datetime import datetime
from typing import Any


def search_web(query: str) -> dict[str, Any]:
    """
    Search the web for information.

    Args:
        query: The search query

    Returns:
        A dictionary with search results
    """
    # This is a placeholder implementation
    # In production, you would integrate with a real search API
    return {
        "status": "success",
        "query": query,
        "results": [
            {
                "title": f"Result for: {query}",
                "url": "https://example.com",
                "snippet": f"This is a sample search result for {query}",
            }
        ],
        "timestamp": datetime.now().isoformat(),
    }


def calculate(expression: str) -> dict[str, Any]:
    """
    Perform mathematical calculations.

    Args:
        expression: A mathematical expression to evaluate

    Returns:
        A dictionary with the calculation result
    """
    try:
        # Note: In production, use a safe math parser instead of eval
        # This is just for demonstration purposes
        result = eval(expression, {"__builtins__": {}}, {})
        return {
            "status": "success",
            "expression": expression,
            "result": result,
        }
    except Exception as e:
        return {
            "status": "error",
            "expression": expression,
            "error": str(e),
        }


def get_weather(city: str, country: str = "US") -> dict[str, Any]:
    """
    Get current weather information for a city.

    Args:
        city: The name of the city
        country: The country code (default: US)

    Returns:
        A dictionary with weather information
    """
    # This is a placeholder implementation
    # In production, you would integrate with a real weather API
    return {
        "status": "success",
        "location": f"{city}, {country}",
        "temperature": "72°F",
        "conditions": "Sunny",
        "humidity": "45%",
        "wind_speed": "10 mph",
        "timestamp": datetime.now().isoformat(),
    }


def get_current_time(city: str) -> dict[str, Any]:
    """
    Returns the current time in a specified city.

    Args:
        city: The name of the city

    Returns:
        A dictionary with the current time
    """
    return {
        "status": "success",
        "city": city,
        "time": datetime.now().strftime("%I:%M %p"),
        "timezone": "UTC",
    }
