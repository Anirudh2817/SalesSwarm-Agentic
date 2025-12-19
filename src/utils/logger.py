"""
Logging utility for SalesSwarm-Agentic agents
"""
import logging
import sys
from datetime import datetime
from typing import Optional


class AgentLogger:
    """Structured logger for swarm agents"""
    
    def __init__(self, name: str = "SalesSwarm"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        
        # Console handler with formatting
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setLevel(logging.DEBUG)
            formatter = logging.Formatter(
                '%(asctime)s | %(levelname)s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
    
    def _format_message(self, tag: str, message: str, agent_id: Optional[str] = None) -> str:
        """Format log message with tag and optional agent ID"""
        if agent_id:
            return f"[{tag}] [{agent_id}] {message}"
        return f"[{tag}] {message}"
    
    def log_agent_action(self, agent_id: str, action: str, details: str = ""):
        """Log an agent action"""
        msg = self._format_message("AGENT_ACTION", f"{action}: {details}", agent_id)
        self.logger.info(msg)
    
    def log_event(self, event_type: str, session_id: str, data: str = ""):
        """Log a swarm event"""
        msg = f"[EVENT] [{event_type}] Session: {session_id} | {data}"
        self.logger.info(msg)
    
    def log_llm_call(self, agent_id: str, model: str, tokens: int = 0):
        """Log an LLM API call"""
        msg = self._format_message("LLM_CALL", f"Model: {model}, Tokens: {tokens}", agent_id)
        self.logger.debug(msg)
    
    def log_api_call(self, endpoint: str, method: str, status: int):
        """Log an API call"""
        msg = f"[API] {method} {endpoint} -> {status}"
        self.logger.info(msg)
    
    def log_system_info(self, tag: str, message: str):
        """Log system information"""
        msg = self._format_message(tag, message)
        self.logger.info(msg)
    
    def log_warning(self, message: str, agent_id: Optional[str] = None):
        """Log a warning"""
        msg = self._format_message("WARNING", message, agent_id)
        self.logger.warning(msg)
    
    def log_error(self, message: str, agent_id: Optional[str] = None):
        """Log an error"""
        msg = self._format_message("ERROR", message, agent_id)
        self.logger.error(msg)
    
    def info(self, message: str):
        """Simple info log"""
        self.logger.info(message)
    
    def debug(self, message: str):
        """Simple debug log"""
        self.logger.debug(message)
    
    def error(self, message: str):
        """Simple error log"""
        self.logger.error(message)


# Global logger instance
agent_logger = AgentLogger()
