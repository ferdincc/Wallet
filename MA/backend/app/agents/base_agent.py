"""
Base agent class for multi-agent system
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging
from app.agents.reasoning_log import ReasoningLog

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Base class for all agents"""
    
    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"{__name__}.{name}")
        self.reasoning_log: Optional[ReasoningLog] = None
    
    def set_reasoning_log(self, reasoning_log: ReasoningLog):
        """Set the reasoning log for this agent"""
        self.reasoning_log = reasoning_log
    
    @abstractmethod
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute agent task"""
        pass
    
    def log(self, message: str, level: str = "INFO"):
        """Log message"""
        if level == "INFO":
            self.logger.info(message)
        elif level == "ERROR":
            self.logger.error(message)
        elif level == "WARNING":
            self.logger.warning(message)
        else:
            self.logger.debug(message)

