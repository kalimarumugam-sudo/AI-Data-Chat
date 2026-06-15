import os
from typing import Dict, Any
import boto3
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class AWSConfig:
    """AWS Configuration class"""
    
    def __init__(self):
        self.region = os.getenv('AWS_REGION', 'us-east-1')
        self.profile = os.getenv('AWS_PROFILE', 'bedrock')
        
    def get_credentials(self):
        """Get AWS credentials using the specified profile"""
        session = boto3.Session(profile_name=self.profile)
        return session.get_credentials()
    
    def get_session(self):
        """Get boto3 session with the specified profile"""
        return boto3.Session(
            profile_name=self.profile,
            region_name=self.region
        )

class BedrockConfig:
    """Bedrock Configuration class"""
    
    def __init__(self):
        self.model_id = os.getenv('BEDROCK_MODEL_ID', 'amazon.titan-embed-text-v1')
        self.max_tokens = 512
        # LLM model for text generation - Claude 3.5 Sonnet (Excellent for data analysis)
        self.llm_model_id = os.getenv('BEDROCK_LLM_MODEL_ID', 'anthropic.claude-3-5-sonnet-20240620-v1:0')

class AppConfig:
    """Application Configuration class"""
    
    def __init__(self):
        self.log_level = os.getenv('LOG_LEVEL', 'info')
        self.batch_size = int(os.getenv('BATCH_SIZE', '25'))

# Configuration instances
aws_config = AWSConfig()
bedrock_config = BedrockConfig()
app_config = AppConfig()

def validate_config() -> bool:
    """
    Validate required configuration
    
    Returns:
        bool: True if configuration is valid
        
    Raises:
        ValueError: If there are configuration errors
    """
    errors = []
    
    # Check AWS credentials
    if not os.getenv('AWS_REGION'):
        print('Warning: AWS_REGION not set, using default: us-east-1')
    
    # Check Bedrock model
    if not os.getenv('BEDROCK_MODEL_ID'):
        print('Warning: BEDROCK_MODEL_ID not set, using default: amazon.titan-embed-text-v1')
    
    if errors:
        raise ValueError(f"Configuration errors:\n{chr(10).join(errors)}")
    
    return True

def get_bedrock_client():
    """
    Get a Bedrock client using the configured AWS session
    
    Returns:
        boto3.client: Bedrock client
    """
    session = aws_config.get_session()
    return session.client('bedrock-runtime')

def get_config_dict() -> Dict[str, Any]:
    """
    Get all configuration as a dictionary
    
    Returns:
        Dict[str, Any]: Configuration dictionary
    """
    return {
        'aws': {
            'region': aws_config.region,
            'profile': aws_config.profile
        },
        'bedrock': {
            'model_id': bedrock_config.model_id,
            'max_tokens': bedrock_config.max_tokens,
            'llm_model_id': bedrock_config.llm_model_id
        },
        'app': {
            'log_level': app_config.log_level,
            'batch_size': app_config.batch_size
        }
    }

if __name__ == "__main__":
    # Validate configuration when run directly
    try:
        validate_config()
        print("Configuration validation successful!")
        print("Current configuration:")
        config = get_config_dict()
        for section, values in config.items():
            print(f"\n{section.upper()}:")
            for key, value in values.items():
                print(f"  {key}: {value}")
    except ValueError as e:
        print(f"Configuration validation failed: {e}")
