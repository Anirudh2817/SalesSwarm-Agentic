"""
Configuration loader for SalesSwarm-Agentic
"""
import os
from typing import Any, Dict, Optional
from dotenv import load_dotenv
import yaml

# Load environment variables
load_dotenv()


class Config:
    """Configuration manager for SalesSwarm-Agentic"""
    
    _instance = None
    _prompts: Dict[str, Any] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_prompts()
        return cls._instance
    
    def _load_prompts(self):
        """Load prompt templates from YAML"""
        prompts_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'config', 'prompts.yaml'
        )
        if os.path.exists(prompts_path):
            with open(prompts_path, 'r') as f:
                self._prompts = yaml.safe_load(f) or {}
    
    # OpenAI Configuration
    @property
    def openai_api_key(self) -> str:
        return os.getenv('OPENAI_API_KEY', '')
    
    @property
    def llm_model(self) -> str:
        return os.getenv('LLM_MODEL', 'gpt-4o')
    
    @property
    def llm_temperature(self) -> float:
        return float(os.getenv('LLM_TEMPERATURE', '0.7'))
    
    # Redis Configuration
    @property
    def redis_url(self) -> str:
        return os.getenv('REDIS_URL', 'redis://localhost:6379')
    
    @property
    def redis_password(self) -> Optional[str]:
        pwd = os.getenv('REDIS_PASSWORD', '')
        return pwd if pwd else None
    
    # Backend Configuration
    @property
    def backend_api_url(self) -> str:
        return os.getenv('BACKEND_API_URL', 'http://localhost:5000')
    
    # Apollo.io Configuration
    @property
    def apollo_api_key(self) -> str:
        return os.getenv('APOLLO_API_KEY', '')
    
    # Server Configuration
    @property
    def port(self) -> int:
        return int(os.getenv('PORT', '8000'))
    
    @property
    def host(self) -> str:
        return os.getenv('HOST', '0.0.0.0')
    
    @property
    def debug(self) -> bool:
        return os.getenv('DEBUG', 'false').lower() == 'true'
    
    # Prompt Templates
    def get_prompt(self, agent: str, template_name: str) -> str:
        """Get prompt template for an agent"""
        agent_prompts = self._prompts.get(agent, {})
        return agent_prompts.get(template_name, '')
    
    def get_system_prompt(self, agent: str) -> str:
        """Get system prompt for an agent"""
        return self.get_prompt(agent, 'system_prompt')


# Global config instance
_config_instance = None


def get_config() -> Config:
    """Get global config instance"""
    global _config_instance
    if _config_instance is None:
        _config_instance = Config()
    return _config_instance
