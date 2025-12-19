"""
Redis cache for SalesSwarm-Agentic session management
"""
import json
import os
from typing import Any, Dict, Optional
from datetime import datetime

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from ..utils.logger import agent_logger


class RedisSessionCache:
    """Redis-based session cache for swarm agents"""
    
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self._connect()
    
    def _connect(self):
        """Connect to Redis server"""
        if not REDIS_AVAILABLE:
            agent_logger.log_warning("Redis not installed. Using in-memory cache only.")
            return
        
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        redis_password = os.getenv('REDIS_PASSWORD', None)
        
        try:
            self.redis_client = redis.from_url(
                redis_url,
                password=redis_password if redis_password else None,
                decode_responses=True
            )
            # Test connection
            self.redis_client.ping()
            agent_logger.log_system_info("REDIS_CONNECTED", f"Connected to Redis at {redis_url}")
        except Exception as e:
            agent_logger.log_warning(f"Redis connection failed: {e}. Using in-memory cache only.")
            self.redis_client = None
    
    def _get_key(self, prefix: str, session_id: str) -> str:
        """Generate Redis key"""
        return f"salesswarm:{prefix}:{session_id}"
    
    # Session Management
    def store_session_data(self, session_id: str, key: str, data: Dict[str, Any], ttl: int = 86400) -> bool:
        """Store session data with TTL (default 24 hours)"""
        if not self.redis_client:
            return False
        
        try:
            redis_key = self._get_key(key, session_id)
            self.redis_client.set(redis_key, json.dumps(data), ex=ttl)
            return True
        except Exception as e:
            agent_logger.log_error(f"Redis store error: {e}")
            return False
    
    def get_session_data(self, session_id: str, key: str) -> Optional[Dict[str, Any]]:
        """Get session data"""
        if not self.redis_client:
            return None
        
        try:
            redis_key = self._get_key(key, session_id)
            data = self.redis_client.get(redis_key)
            return json.loads(data) if data else None
        except Exception as e:
            agent_logger.log_error(f"Redis get error: {e}")
            return None
    
    def delete_session_data(self, session_id: str, key: str) -> bool:
        """Delete session data"""
        if not self.redis_client:
            return False
        
        try:
            redis_key = self._get_key(key, session_id)
            self.redis_client.delete(redis_key)
            return True
        except Exception as e:
            agent_logger.log_error(f"Redis delete error: {e}")
            return False
    
    # Campaign Data
    def store_campaign_data(self, campaign_id: str, data: Dict[str, Any]) -> bool:
        """Store campaign processing data"""
        return self.store_session_data(campaign_id, "campaign", data)
    
    def get_campaign_data(self, campaign_id: str) -> Optional[Dict[str, Any]]:
        """Get campaign data"""
        return self.get_session_data(campaign_id, "campaign")
    
    # Lead Enrichment Data
    def store_enrichment_data(self, session_id: str, data: Dict[str, Any]) -> bool:
        """Store lead enrichment data"""
        return self.store_session_data(session_id, "enrichment", data)
    
    def get_enrichment_data(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get lead enrichment data"""
        return self.get_session_data(session_id, "enrichment")
    
    # Email Sequence Data
    def store_email_sequence(self, lead_id: str, campaign_id: str, data: Dict[str, Any]) -> bool:
        """Store email sequence for a lead"""
        key = f"email:{campaign_id}"
        return self.store_session_data(lead_id, key, data)
    
    def get_email_sequence(self, lead_id: str, campaign_id: str) -> Optional[Dict[str, Any]]:
        """Get email sequence for a lead"""
        key = f"email:{campaign_id}"
        return self.get_session_data(lead_id, key)
    
    # Qualification Data
    def store_qualification_data(self, lead_id: str, data: Dict[str, Any]) -> bool:
        """Store lead qualification result"""
        return self.store_session_data(lead_id, "qualification", data)
    
    def get_qualification_data(self, lead_id: str) -> Optional[Dict[str, Any]]:
        """Get lead qualification result"""
        return self.get_session_data(lead_id, "qualification")
    
    # Company Intelligence Data
    def store_company_intel(self, company_url: str, data: Dict[str, Any], ttl: int = 604800) -> bool:
        """Store company intelligence (TTL 7 days)"""
        # Use URL hash as key
        import hashlib
        url_hash = hashlib.md5(company_url.encode()).hexdigest()[:12]
        return self.store_session_data(url_hash, "company_intel", data, ttl)
    
    def get_company_intel(self, company_url: str) -> Optional[Dict[str, Any]]:
        """Get cached company intelligence"""
        import hashlib
        url_hash = hashlib.md5(company_url.encode()).hexdigest()[:12]
        return self.get_session_data(url_hash, "company_intel")
    
    # Bulk Operations
    def get_all_session_data(self, session_id: str) -> Dict[str, Any]:
        """Get all data for a session"""
        return {
            "campaign": self.get_campaign_data(session_id),
            "enrichment": self.get_enrichment_data(session_id),
            "qualification": self.get_qualification_data(session_id),
        }


# Global instance
_redis_cache_instance = None


def get_redis_cache() -> RedisSessionCache:
    """Get global Redis cache instance"""
    global _redis_cache_instance
    if _redis_cache_instance is None:
        _redis_cache_instance = RedisSessionCache()
    return _redis_cache_instance
