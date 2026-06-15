"""
Direct Database Tools for Oracle Integration
Simpler approach than MCP server - direct database connection
"""

import streamlit as st
import pandas as pd
import oracledb
from typing import Dict, Any, Optional, List
from config.config import oracle_config
import logging

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Direct Oracle database connection manager."""
    
    def __init__(self):
        self.connection = None
        self.connected = False
    
    def connect(self) -> bool:
        """Connect to Oracle database."""
        try:
            if not oracle_config.validate():
                error_msg = "Oracle configuration is incomplete. Please check your environment variables."
                logger.error(error_msg)
                try:
                    st.error(error_msg)
                except:
                    pass  # Not in Streamlit context
                return False
            
            # Initialize Oracle client if needed
            if oracle_config.thick_mode:
                oracledb.init_oracle_client()
            
            # Create connection
            self.connection = oracledb.connect(
                user=oracle_config.user,
                password=oracle_config.password,
                dsn=oracle_config.dsn
            )
            self.connected = True
            logger.info("Connected to Oracle database successfully")
            return True
            
        except Exception as e:
            error_msg = f"Database connection failed: {str(e)}"
            logger.error(f"Failed to connect to Oracle database: {e}")
            try:
                st.error(error_msg)
            except:
                pass  # Not in Streamlit context
            return False
    
    def disconnect(self):
        """Disconnect from Oracle database."""
        if self.connection:
            self.connection.close()
            self.connected = False
            logger.info("Disconnected from Oracle database")
    
    def execute_query(self, sql: str, parameters: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
        """Execute SQL query and return results as DataFrame."""
        if not self.connected:
            raise RuntimeError("Not connected to Oracle database")
        
        try:
            cursor = self.connection.cursor()
            
            if parameters:
                cursor.execute(sql, parameters)
            else:
                cursor.execute(sql)
            
            # Get column names
            columns = [desc[0] for desc in cursor.description]
            
            # Fetch all results
            results = cursor.fetchall()
            
            # Convert to DataFrame
            df = pd.DataFrame(results, columns=columns)
            
            cursor.close()
            return df
            
        except Exception as e:
            logger.error(f"Error executing query: {e}")
            raise
    
    def get_tables_list(self) -> List[Dict[str, Any]]:
        """Get list of tables in current schema."""
        if not self.connected:
            raise RuntimeError("Not connected to Oracle database")
        
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                SELECT table_name, num_rows, last_analyzed 
                FROM user_tables 
                ORDER BY table_name
            """)
            
            tables = []
            for row in cursor.fetchall():
                tables.append({
                    "table_name": row[0],
                    "num_rows": row[1],
                    "last_analyzed": str(row[2]) if row[2] else None
                })
            
            cursor.close()
            return tables
            
        except Exception as e:
            logger.error(f"Error getting tables list: {e}")
            raise
    
    def describe_table(self, table_name: str, schema_name: Optional[str] = None) -> Dict[str, Any]:
        """Get table structure information."""
        if not self.connected:
            raise RuntimeError("Not connected to Oracle database")
        
        try:
            cursor = self.connection.cursor()
            
            # Get column information
            if schema_name:
                cursor.execute("""
                    SELECT column_name, data_type, data_length, nullable, data_default
                    FROM all_tab_columns 
                    WHERE table_name = :table_name AND owner = :schema_name
                    ORDER BY column_id
                """, {"table_name": table_name.upper(), "schema_name": schema_name.upper()})
            else:
                cursor.execute("""
                    SELECT column_name, data_type, data_length, nullable, data_default
                    FROM user_tab_columns 
                    WHERE table_name = :table_name
                    ORDER BY column_id
                """, {"table_name": table_name.upper()})
            
            columns = cursor.fetchall()
            
            if not columns:
                return {"error": f"Table {table_name} not found"}
            
            # Format column information
            column_info = []
            for col in columns:
                column_info.append({
                    "column_name": col[0],
                    "data_type": col[1],
                    "data_length": col[2],
                    "nullable": col[3],
                    "data_default": str(col[4]) if col[4] else None
                })
            
            cursor.close()
            return {
                "table_name": table_name,
                "schema_name": schema_name,
                "columns": column_info
            }
            
        except Exception as e:
            logger.error(f"Error describing table: {e}")
            raise
    
    def get_table_sample(self, table_name: str, limit: int = 10, schema_name: Optional[str] = None) -> pd.DataFrame:
        """Get sample data from table."""
        if not self.connected:
            raise RuntimeError("Not connected to Oracle database")
        
        try:
            # Build query with proper schema qualification
            if schema_name:
                query = f"SELECT * FROM {schema_name}.{table_name} WHERE ROWNUM <= :limit"
            else:
                query = f"SELECT * FROM {table_name} WHERE ROWNUM <= :limit"
            
            return self.execute_query(query, {"limit": limit})
            
        except Exception as e:
            logger.error(f"Error getting table sample: {e}")
            raise
    
    def test_connection(self) -> str:
        """Test database connection."""
        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT 'Connected to Oracle Database' as status FROM DUAL")
            result = cursor.fetchone()
            cursor.close()
            return result[0]
        except Exception as e:
            return f"Connection Error: {str(e)}"

# Global database manager instance
db_manager = DatabaseManager()

def get_db_manager() -> DatabaseManager:
    """Get the global database manager instance."""
    return db_manager

def init_database_connection() -> bool:
    """Initialize database connection."""
    return db_manager.connect()

def close_database_connection():
    """Close database connection."""
    db_manager.disconnect()

# Streamlit session state helpers
def get_db_status():
    """Get database connection status for Streamlit."""
    if 'db_connected' not in st.session_state:
        st.session_state.db_connected = False
    return st.session_state.db_connected

def set_db_status(status: bool):
    """Set database connection status for Streamlit."""
    st.session_state.db_connected = status
