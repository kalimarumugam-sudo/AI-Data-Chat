import streamlit as st
from dotenv import load_dotenv
from os import getenv
from openai import OpenAI
import re
import pandas as pd
import duckdb
import json
import logging
import boto3
from botocore.exceptions import ClientError

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# LLM PROVIDER SELECTION - Comment/Uncomment to switch between providers
# =============================================================================
# 
# TO SWITCH PROVIDERS:
# 1. For OpenAI: Keep lines 25-26 uncommented, comment out lines 29-31
# 2. For Bedrock: Comment out lines 25-26, uncomment lines 29-31
#
# OpenAI uses: GPT-4 with streaming responses
# Bedrock uses: Claude 3.5 Sonnet (configured in .env file)
# =============================================================================

# Option 1: OpenAI (Comment out these 2 lines to disable)
USE_OPENAI = True

# Option 2: AWS Bedrock (Uncomment these 3 lines to enable)
# USE_OPENAI = False
# from config.aws_config import aws_config, bedrock_config
# bedrock_client = aws_config.get_session().client('bedrock-runtime')
 
# Initialize OpenAI client placeholder; set when OpenAI is enabled
client = None
if USE_OPENAI:
    client = OpenAI(api_key=getenv("OPENAI_API_KEY"))

def load_prompt_template():
    """Load the main prompt from prompt.md"""
    try:
        with open("resources/prompt.md", "r") as f:
            return f.read()
    except FileNotFoundError:
        logger.error("prompt.md not found in resources/ directory")
        return """You are a helpful data analyst. Generate SQL queries using DuckDB syntax with 'df' as the table name."""

def get_current_schema(dataframe):
    """Generate schema info for prompt template"""
    if dataframe is None:
        return "No data currently loaded."
    
    schema_parts = [f"Table 'df' with {len(dataframe)} rows:"]
    for col in dataframe.columns:
        dtype = str(dataframe[col].dtype)
        # Simplify dtype names for clarity
        if 'int' in dtype:
            dtype_simple = "INTEGER"
        elif 'float' in dtype:
            dtype_simple = "DECIMAL"
        elif 'datetime' in dtype:
            dtype_simple = "DATETIME"
        elif 'object' in dtype:
            dtype_simple = "TEXT"
        else:
            dtype_simple = dtype.upper()
        
        schema_parts.append(f"- {col} ({dtype_simple})")
    
    return "\n".join(schema_parts)

def extract_sql_query(text):
    """Extract SQL query from LLM response (strips trailing semicolons)."""
    # Look for SQL code blocks first
    sql_pattern = r'```sql\s*(.*?)\s*```'
    match = re.search(sql_pattern, text, re.DOTALL | re.IGNORECASE)
    if match:
        query = match.group(1).strip()
        return query.rstrip(';')
    
    # Fallback: Look for SELECT statements
    select_pattern = r'(SELECT.*?)(?:\n\n|$)'
    match = re.search(select_pattern, text, re.DOTALL | re.IGNORECASE)
    if match:
        query = match.group(1).strip()
        return query.rstrip(';')
    
    return None

def call_llm(messages):
    """Make LLM API call using configured provider"""
    try:
        if USE_OPENAI:
            response = client.chat.completions.create(
                model="gpt-4",
                messages=messages,
                stream=False,
                temperature=0.1  # Lower temperature for more consistent SQL generation
            )
            return response.choices[0].message.content
        else:
            # Bedrock call
            return get_bedrock_response(messages)
            
    except Exception as e:
        logger.error(f"LLM API call failed: {e}")
        return f"Error getting AI response: {str(e)}"

def get_bedrock_response(messages, model_id=None):
    """Get response from AWS Bedrock Claude API"""
    try:
        from config.aws_config import bedrock_config
        
        # Use the LLM model ID from config (Claude 3.5 Sonnet)
        model_id = model_id or bedrock_config.llm_model_id
        
        # Convert messages to Claude format
        system_message = ""
        conversation_messages = []
        
        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                conversation_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
        
        # Prepare request body for Claude with optimized settings
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4000,
            "temperature": 0.1,  # Lower temperature for more consistent SQL generation
            "top_p": 0.9,        # Focused responses
            "system": system_message,
            "messages": conversation_messages
        }
        
        # Get Bedrock client
        session = boto3.Session(
            profile_name=getenv('AWS_PROFILE', 'bedrock'),
            region_name=getenv('AWS_REGION', 'us-east-1')
        )
        bedrock_client = session.client('bedrock-runtime')
        
        # Call Bedrock
        response = bedrock_client.invoke_model(
            modelId=model_id,
            contentType='application/json',
            accept='application/json',
            body=json.dumps(body)
        )
        
        # Parse response
        response_body = json.loads(response['body'].read())
        
        # Extract text content
        if 'content' in response_body and len(response_body['content']) > 0:
            return response_body['content'][0]['text']
        else:
            return "Sorry, I couldn't generate a response."
            
    except Exception as e:
        raise e

def execute_duckdb_query(query, dataframe):
    """Execute SQL query on dataframe using DuckDB"""
    try:
        conn = duckdb.connect()
        conn.register('df', dataframe)
        result = conn.execute(query).fetchdf()
        conn.close()
        return result
    except Exception as e:
        logger.error(f"DuckDB query failed: {e}")
        return f"Error executing query: {str(e)}"

def execute_oracle_query(query):
    """Execute SQL query on Oracle database"""
    try:
        from .database_tools import get_db_manager, get_db_status, init_database_connection, set_db_status
        
        # Ensure Oracle connection
        if not get_db_status():
            if init_database_connection():
                set_db_status(True)
            else:
                return "Oracle database connection failed."
        
        db_manager = get_db_manager()
        result = db_manager.execute_query(query)
        return result
        
    except Exception as e:
        logger.error(f"Oracle query failed: {e}")
        return f"Error executing Oracle query: {str(e)}"

def is_oracle_query(response_text, sql_query):
    """Determine if this should be executed against Oracle based on AI response and SQL content"""
    if not sql_query:
        return False
    
    # STRICT: Only go to Oracle if user explicitly mentioned database keywords
    # Check the original user message, not just the AI response
    user_message = getattr(is_oracle_query, '_current_user_message', '')
    database_keywords = ['database', 'db', 'oracle']
    
    # Debug logging
    logger.info(f"Checking user message for database keywords: '{user_message}'")
    logger.info(f"Database keywords to check: {database_keywords}")
    
    # Only check if user explicitly mentioned database keywords
    if not any(keyword in user_message.lower() for keyword in database_keywords):
        logger.info("No database keywords in user message - treating as local query")
        return False
    
    # If user mentioned database keywords, then check AI response for Oracle indicators
    oracle_indicators = ['oracle', 'database', 'db', 'business term']
    found_indicators = [indicator for indicator in oracle_indicators if indicator in response_text.lower()]
    if found_indicators:
        logger.info(f"Found Oracle indicators in response: {found_indicators}")
        return True
    
    # Check SQL for Oracle-specific syntax only if user mentioned database
    oracle_sql_patterns = [
        r'\w+\.\w+',  # schema.table pattern
        r'TO_DATE\(',  # Oracle date function
        r'SYSDATE',    # Oracle system date
    ]
    
    for pattern in oracle_sql_patterns:
        if re.search(pattern, sql_query, re.IGNORECASE):
            logger.info(f"Found Oracle SQL pattern: {pattern}")
            return True
    
    logger.info("No Oracle indicators found - treating as local query")
    return False

def handle_data_reload(user_message):
    """Handle data reload requests"""
    reload_keywords = ['reset', 'restore', 'reload', 'refresh', 'update', 'refresh data', 'reload data']
    if any(keyword in user_message.lower() for keyword in reload_keywords):
        try:
            from .data_loader import load_data, load_rates_data
            load_data.clear()
            load_rates_data.clear()
            df, success_message, error_message = load_data()
            if df is not None:
                st.session_state.current_df = df
                return True, f"Data reloaded successfully. {success_message}"
            else:
                return True, f"Error reloading data: {error_message}"
        except Exception as e:
            return True, f"Error during data reload: {str(e)}"
    
    return False, None

def process_user_message(user_message: str, dataframe):
    """
    Main function to process user messages using prompt-driven approach.
    
    This replaces the complex enhanced_query_handler with a simple, 
    prompt-driven approach that trusts the AI to make routing decisions.
    """
    
    # Handle special data reload requests
    is_reload, reload_message = handle_data_reload(user_message)
    if is_reload:
        return reload_message, None, None, "local"
    
    try:
        prompt_template = load_prompt_template()
        schema_info = get_current_schema(dataframe)
        logger.info(f"Schema info being sent to AI: {schema_info[:200]}...")
        system_prompt = prompt_template.replace("${SCHEMA}", schema_info)
        
        # Single AI call - let the prompt handle all routing logic
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        ai_response = call_llm(messages)
        
        # Debug logging
        logger.info(f"AI response (first 500 chars): {ai_response[:500]}")
        
        # Extract and execute SQL if present
        sql_query = extract_sql_query(ai_response)
        logger.info(f"Extracted SQL query: {sql_query}")
        if sql_query:
            # Pass user message to is_oracle_query function
            is_oracle_query._current_user_message = user_message
            
            # Let AI response and SQL content determine execution target
            if is_oracle_query(ai_response, sql_query):
                query_result = execute_oracle_query(sql_query)
                
                # Remove empty rows from Oracle query results
                if query_result is not None and not query_result.empty:
                    logger.info(f"Oracle query returned {len(query_result)} rows with columns: {list(query_result.columns)}")
                    logger.info(f"First few rows data: {query_result.head().to_dict('records')}")
                    
                    # Remove completely empty rows and rows with all null/empty values
                    empty_rows = query_result.isnull().all(axis=1).sum()
                    if empty_rows > 0:
                        logger.info(f"Found {empty_rows} completely empty rows in Oracle query")
                        query_result = query_result.dropna(how='all')
                    
                    # Also remove rows where all values are empty strings or whitespace
                    def is_empty_row(row):
                        return all(str(val).strip() == '' or pd.isna(val) for val in row)
                    
                    before_count = len(query_result)
                    query_result = query_result[~query_result.apply(is_empty_row, axis=1)]
                    after_count = len(query_result)
                    
                    if before_count != after_count:
                        logger.info(f"Removed {before_count - after_count} rows with empty/whitespace values from Oracle query")
                    
                    logger.info(f"Final result: {len(query_result)} rows after cleanup")
                
                data_source = "oracle"
            else:
                logger.info("Executing local DuckDB query...")
                query_result = execute_duckdb_query(sql_query, dataframe)
                logger.info(f"Local query result type: {type(query_result)}")
                if hasattr(query_result, 'shape'):
                    logger.info(f"Local query result shape: {query_result.shape}")
                data_source = "local"
            
            return ai_response, sql_query, query_result, data_source
        else:
            # No SQL query - just return the AI response
            return ai_response, None, None, "local"
            
    except Exception as e:
        logger.error(f"Error processing user message: {e}")
        return f"Error processing your request: {str(e)}", None, None, "local"

# Backward compatibility alias
enhanced_query_handler = process_user_message