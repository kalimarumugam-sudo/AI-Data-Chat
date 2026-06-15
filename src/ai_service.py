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

def get_business_dictionary_simple():
    """Get simplified business dictionary for prompt injection"""
    try:
        from .schema_service import SchemaService
        schema_service = SchemaService()
        business_dict = schema_service.load_business_dictionary()
        
        mappings = business_dict.get("mappings", [])
        if not mappings:
            return "No business dictionary mappings available."
        
        dict_parts = ["Business Terms Available:"]
        
        # Always include CARRIER table schema first (most important)
        carrier_mapping = None
        for mapping in mappings:
            if mapping.get("business_term") == "carrier":
                carrier_mapping = mapping
                break
        
        if carrier_mapping:
            term = carrier_mapping.get("business_term", "")
            table = carrier_mapping.get("table_name", "")
            column = carrier_mapping.get("column_name", "")
            dict_parts.append(f"- '{term}' → {table}.{column}")
            
            # Add CARRIER table schema information
            table_schema = carrier_mapping.get("table_schema", {})
            if table_schema:
                columns = table_schema.get("columns", [])
                key_columns = table_schema.get("key_columns", [])
                if columns:
                    dict_parts.append(f"  Table {table} columns: {', '.join(columns[:15])}{'...' if len(columns) > 15 else ''}")
                if key_columns:
                    dict_parts.append(f"  Key columns: {', '.join(key_columns)}")
        
        # Add other mappings (limit to prevent prompt bloat)
        for mapping in mappings[:10]:  # Reduced limit to make room for CARRIER schema
            if mapping.get("business_term") == "carrier":
                continue  # Skip carrier as we already added it
                
            term = mapping.get("business_term", "")
            table = mapping.get("table_name", "")
            column = mapping.get("column_name", "")
            
            if term and table and column:
                dict_parts.append(f"- '{term}' → {table}.{column}")
        
        return "\n".join(dict_parts)
        
    except Exception as e:
        logger.error(f"Error loading business dictionary: {e}")
        return "Business dictionary not available."

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

def check_and_execute_custom_query(user_message: str):
    """
    Check if the user message matches any custom queries in the business dictionary
    and execute them with proper parameter extraction.
    """
    try:
        logger.info(f"Checking custom queries for message: {user_message}")
        from .schema_service import SchemaService
        schema_service = SchemaService()
        business_dict = schema_service.load_business_dictionary()
        
        # Extract mappings from business dictionary
        mappings = business_dict.get('mappings', [])
        logger.info(f"Loaded business dictionary with {len(mappings)} entries")
        
        # Check for custom queries in business dictionary
        for entry in mappings:
            if 'custom_query' in entry:
                business_term = entry.get('business_term', '')
                synonyms = entry.get('synonyms', [])
                
                logger.info(f"Checking custom query for business term: {business_term}")
                
                # Check if user message contains the business term or any synonym
                user_lower = user_message.lower()
                if (business_term.lower() in user_lower or 
                    any(synonym.lower() in user_lower for synonym in synonyms)):
                    
                    logger.info(f"Found custom query for: {business_term}")
                    
                    # Extract parameters based on business term
                    custom_query = entry['custom_query']
                    
                    if business_term == 'outbound bilateral rate':
                        # Extract carrier_name and destination_name
                        carrier_name = extract_carrier_name(user_message)
                        destination_name = extract_destination_name(user_message)
                        
                        # Replace parameters in custom query
                        custom_query = custom_query.replace('{carrier_name}', carrier_name)
                        custom_query = custom_query.replace('{destination_name}', destination_name)
                        
                    elif business_term == 'spl':
                        # Extract carrier_name
                        carrier_name = extract_carrier_name(user_message)
                        custom_query = custom_query.replace('{carrier_name}', carrier_name)
                        
                    elif business_term == 'auto finalization status':
                        # Extract auto_finalization_name
                        auto_finalization_name = extract_auto_finalization_name(user_message)
                        custom_query = custom_query.replace('{auto_finalization_name}', auto_finalization_name)
                    
                    logger.info(f"Executing custom query: {custom_query[:200]}...")
                    
                    # Execute the custom query using the existing Oracle connection
                    query_result = execute_oracle_query(custom_query)
                    
                    if query_result is not None and not query_result.empty:
                        # Remove completely empty rows and rows with all null/empty values
                        empty_rows = query_result.isnull().all(axis=1).sum()
                        if empty_rows > 0:
                            logger.info(f"Found {empty_rows} completely empty rows")
                            query_result = query_result.dropna(how='all')
                        
                        # Also remove rows where all values are empty strings or whitespace
                        def is_empty_row(row):
                            return all(str(val).strip() == '' or pd.isna(val) for val in row)
                        
                        before_count = len(query_result)
                        query_result = query_result[~query_result.apply(is_empty_row, axis=1)]
                        after_count = len(query_result)
                        
                        if before_count != after_count:
                            logger.info(f"Removed {before_count - after_count} rows with empty/whitespace values")
                        
                        logger.info(f"Custom query returned {len(query_result)} rows with columns: {list(query_result.columns)}")
                        logger.info(f"First 3 rows: {query_result.head(3).to_dict('records')}")
                        
                        # Format the response
                        ai_response = f"Here's the query for '{business_term}':"
                        
                        return ai_response, custom_query, query_result, "custom_query"
                    else:
                        return f"No results found for {business_term}.", custom_query, None, "custom_query"
        
        return None
        
    except Exception as e:
        logger.error(f"Error in check_and_execute_custom_query: {e}")
        return None

def extract_carrier_name(user_message: str):
    """Extract carrier name from user message"""
    import re
    
    # Pattern 1: Look for quoted text before "carrier" (most specific)
    # This handles: "...for 'Advanced Wireless Network - UKADVG' carrier"
    quoted_carrier_pattern = r'["\']([^"\']+)["\']\s+carrier'
    quoted_match = re.search(quoted_carrier_pattern, user_message, re.IGNORECASE)
    if quoted_match:
        carrier_name = quoted_match.group(1).strip()
        # Clean up common suffixes
        carrier_name = re.sub(r'\s+(carrier|supplier)$', '', carrier_name, flags=re.IGNORECASE)
        return carrier_name
    
    # Pattern 2: Look for the pattern after "destinations for" and before "carrier"
    # This handles: "...destinations for Advanced Wireless Network - UKADVG carrier"
    pattern1 = r'destinations?\s+for\s+([^,\n]*?)\s+carrier'
    match1 = re.search(pattern1, user_message, re.IGNORECASE)
    if match1:
        carrier_name = match1.group(1).strip()
        # Clean up common suffixes
        carrier_name = re.sub(r'\s+(carrier|supplier)$', '', carrier_name, flags=re.IGNORECASE)
        return carrier_name
    
    # Pattern 3: Look for the pattern after "for" and before "carrier" (for SPL queries)
    # This handles: "...for Advanced Wireless Network - UKADVG carrier"
    pattern2 = r'for\s+([^,\n]*?)\s+carrier'
    match2 = re.search(pattern2, user_message, re.IGNORECASE)
    if match2:
        carrier_name = match2.group(1).strip()
        # Clean up common suffixes
        carrier_name = re.sub(r'\s+(carrier|supplier)$', '', carrier_name, flags=re.IGNORECASE)
        return carrier_name
    
    return ''

def extract_destination_name(user_message: str):
    """Extract destination name from user message"""
    import re
    
    # Pattern 1: Look for quoted text before "destinations" (most specific)
    # This handles: "...for 'thailand' destinations for..."
    quoted_destination_pattern = r'["\']([^"\']+)["\']\s+destinations?'
    quoted_match = re.search(quoted_destination_pattern, user_message, re.IGNORECASE)
    if quoted_match:
        destination_name = quoted_match.group(1).strip()
        # Clean up common suffixes
        destination_name = re.sub(r'\s+(destinations?|destination)$', '', destination_name, flags=re.IGNORECASE)
        return destination_name
    
    # Pattern 2: Look for the pattern after "bilateral rate" and before "destinations"
    # This handles: "...bilateral rate for thailand destinations for..."
    pattern = r'bilateral rate.*?for\s+([^,\n]*?)\s+destinations?'
    match = re.search(pattern, user_message, re.IGNORECASE)
    if match:
        destination_name = match.group(1).strip()
        # Clean up common suffixes
        destination_name = re.sub(r'\s+(destinations?|destination)$', '', destination_name, flags=re.IGNORECASE)
        return destination_name
    
    return ''

def extract_auto_finalization_name(user_message: str):
    """Extract auto finalization name from user message"""
    import re
    
    # First, try to extract from quoted text (most reliable)
    quoted_pattern = r'["\']([^"\']+)["\']'
    quoted_match = re.search(quoted_pattern, user_message)
    if quoted_match:
        auto_finalization_name = quoted_match.group(1).strip()
        return auto_finalization_name
    
    # Fallback to original patterns for backward compatibility
    patterns = [
        r'for\s+([^,\n]+?)(?:\s|$)',
        r'status\s+for\s+([^,\n]+?)(?:\s|$)',
        r'([A-Z][^,\n]*?)(?:\s|$)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, user_message, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            return name
    
    return ''

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
        # Check for custom queries first (before AI processing)
        logger.info(f"About to call check_and_execute_custom_query for: {user_message}")
        custom_query_result = check_and_execute_custom_query(user_message)
        logger.info(f"check_and_execute_custom_query returned: {custom_query_result}")
        if custom_query_result:
            logger.info("Custom query result found, returning early")
            return custom_query_result
        else:
            logger.info("No custom query result, proceeding with AI processing")
        
        # Load and customize prompt template
        prompt_template = load_prompt_template()
        schema_info = get_current_schema(dataframe)
        business_dict = get_business_dictionary_simple()
        
        # Debug logging to see what the AI is receiving
        logger.info(f"Schema info being sent to AI: {schema_info[:200]}...")
        logger.info(f"Business dict being sent to AI: {business_dict[:200]}...")
        
        # Inject dynamic content into prompt
        system_prompt = prompt_template.replace("${SCHEMA}", schema_info)
        system_prompt = system_prompt.replace("{business_context}", business_dict)
        
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