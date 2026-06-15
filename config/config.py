"""
Configuration for Oracle Database Integration
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

@dataclass
class OracleConfig:
    """Oracle database configuration."""
    user: str
    password: str
    dsn: str
    thick_mode: bool = False
    
    def validate(self) -> bool:
        """Validate that all required fields are set."""
        return all([
            self.user,
            self.password,
            self.dsn
        ])

# Load configuration from environment variables
oracle_config = OracleConfig(
    user=os.getenv("ORACLE_USER", ""),
    password=os.getenv("ORACLE_PASSWORD", ""),
    dsn=os.getenv("ORACLE_DSN", ""),
    thick_mode=os.getenv("ORACLE_THICK_MODE", "false").lower() == "true"
)
