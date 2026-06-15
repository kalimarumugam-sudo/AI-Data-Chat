"""
Schema Service for Oracle Database Integration
Provides schema extraction, business dictionary management, and API endpoints
for natural language to SQL generation.
"""

import json
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
import os
from .database_tools import get_db_manager, get_db_status

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class ColumnInfo:
    """Information about a database column."""
    column_name: str
    data_type: str
    nullable: bool
    primary_key: bool = False
    foreign_key: bool = False
    referenced_table: Optional[str] = None
    referenced_column: Optional[str] = None
    description: Optional[str] = None

@dataclass
class TableInfo:
    """Information about a database table."""
    table_name: str
    schema_name: str
    columns: List[ColumnInfo]
    description: Optional[str] = None
    row_count: Optional[int] = None

@dataclass
class BusinessMapping:
    """Business term to schema field mapping."""
    business_term: str
    table_name: str
    column_name: str
    description: str
    synonyms: List[str] = None
    category: str = "general"
    confidence: float = 1.0

class SchemaService:
    """Service for managing Oracle schema and business dictionary."""
    
    def __init__(self, schema_file: str = "data/metadata/oracle_schema.json", 
                 business_dict_file: str = "data/metadata/business_dictionary.json"):
        self.schema_file = schema_file
        self.business_dict_file = business_dict_file
        self.schema_cache: Optional[Dict[str, Any]] = None
        self.business_dict_cache: Optional[Dict[str, Any]] = None
        self.last_schema_update: Optional[datetime] = None
        
    def extract_oracle_schema(self) -> Dict[str, Any]:
        """Extract complete schema metadata from Oracle database."""
        if not get_db_status():
            raise ConnectionError("Oracle database is not connected")
        
        db_manager = get_db_manager()
        schema_metadata = {
            "extraction_timestamp": datetime.now().isoformat(),
            "database_info": {},
            "schemas": {},
            "tables": {},
            "relationships": [],
            "statistics": {}
        }
        
        try:
            # Get database information
            db_info_query = """
            SELECT 
                SYS_CONTEXT('USERENV', 'DB_NAME') as db_name,
                SYS_CONTEXT('USERENV', 'DB_DOMAIN') as db_domain,
                SYS_CONTEXT('USERENV', 'INSTANCE_NAME') as instance_name
            FROM DUAL
            """
            db_info = db_manager.execute_query(db_info_query)
            if not db_info.empty:
                schema_metadata["database_info"] = db_info.iloc[0].to_dict()
            
            # Get current user's schema (simplified approach)
            try:
                current_user_query = "SELECT USER as schema_name FROM DUAL"
                current_user = db_manager.execute_query(current_user_query)
                if not current_user.empty:
                    schema_metadata["schemas"] = [{"schema_name": current_user.iloc[0]['SCHEMA_NAME']}]
                else:
                    schema_metadata["schemas"] = [{"schema_name": "USER"}]
            except Exception as e:
                logger.warning(f"Could not get current user: {e}")
                schema_metadata["schemas"] = [{"schema_name": "USER"}]
            
            # Get tables from current user's schema (simplified approach)
            tables_query = """
            SELECT 
                USER as schema_name,
                TABLE_NAME,
                NUM_ROWS
            FROM USER_TABLES
            ORDER BY TABLE_NAME
            """
            tables = db_manager.execute_query(tables_query)
            
            for _, table_row in tables.iterrows():
                table_info = table_row.to_dict()
                schema_name = table_info['SCHEMA_NAME']
                table_name = table_info['TABLE_NAME']
                full_table_name = f"{schema_name}.{table_name}"
                
                # Get columns for this table (simplified approach)
                columns_query = """
                SELECT 
                    COLUMN_NAME,
                    DATA_TYPE,
                    DATA_LENGTH,
                    DATA_PRECISION,
                    DATA_SCALE,
                    NULLABLE,
                    DATA_DEFAULT
                FROM USER_TAB_COLUMNS
                WHERE TABLE_NAME = :table_name
                ORDER BY COLUMN_ID
                """
                
                columns = db_manager.execute_query(columns_query, {
                    'table_name': table_name
                })
                
                table_columns = []
                for _, col_row in columns.iterrows():
                    col_info = col_row.to_dict()
                    column = ColumnInfo(
                        column_name=col_info['COLUMN_NAME'],
                        data_type=col_info['DATA_TYPE'],
                        nullable=col_info['NULLABLE'] == 'Y',
                        primary_key=False,  # Simplified - no primary key detection
                        description=None    # Simplified - no comments
                    )
                    table_columns.append(asdict(column))
                
                # Skip foreign key relationships for now (simplified approach)
                # This requires ALL_* views which the user may not have access to
                
                # Store table information
                table_info_obj = TableInfo(
                    table_name=table_name,
                    schema_name=schema_name,
                    columns=table_columns,
                    description=table_info.get('TABLE_COMMENT'),
                    row_count=table_info.get('NUM_ROWS')
                )
                
                schema_metadata["tables"][full_table_name] = asdict(table_info_obj)
            
            # Skip table relationships for now (simplified approach)
            # This requires ALL_* views which the user may not have access to
            schema_metadata["relationships"] = []
            
            # Calculate statistics
            schema_metadata["statistics"] = {
                "total_schemas": len(schema_metadata["schemas"]),
                "total_tables": len(schema_metadata["tables"]),
                "total_relationships": len(schema_metadata["relationships"]),
                "total_columns": sum(len(table["columns"]) for table in schema_metadata["tables"].values())
            }
            
            logger.info(f"Successfully extracted schema metadata: {schema_metadata['statistics']}")
            return schema_metadata
            
        except Exception as e:
            logger.error(f"Error extracting Oracle schema: {e}")
            raise
    
    def save_schema(self, schema_data: Dict[str, Any]) -> None:
        """Save schema metadata to JSON file."""
        try:
            with open(self.schema_file, 'w', encoding='utf-8') as f:
                json.dump(schema_data, f, indent=2, ensure_ascii=False)
            self.schema_cache = schema_data
            self.last_schema_update = datetime.now()
            logger.info(f"Schema metadata saved to {self.schema_file}")
        except Exception as e:
            logger.error(f"Error saving schema: {e}")
            raise
    
    def load_schema(self) -> Dict[str, Any]:
        """Load schema metadata from JSON file."""
        if self.schema_cache:
            return self.schema_cache
            
        try:
            if os.path.exists(self.schema_file):
                with open(self.schema_file, 'r', encoding='utf-8') as f:
                    schema_data = json.load(f)
                self.schema_cache = schema_data
                logger.info(f"Schema metadata loaded from {self.schema_file}")
                return schema_data
            else:
                logger.warning(f"Schema file {self.schema_file} not found")
                return {}
        except Exception as e:
            logger.error(f"Error loading schema: {e}")
            return {}
    
    def create_business_dictionary_template(self) -> Dict[str, Any]:
        """Create a template business dictionary with common mappings."""
        template = {
            "metadata": {
                "version": "1.0",
                "created": datetime.now().isoformat(),
                "description": "Business dictionary for mapping business terms to Oracle schema fields"
            },
            "categories": {
                "customer": "Customer-related terms",
                "product": "Product and inventory terms", 
                "sales": "Sales and revenue terms",
                "financial": "Financial and accounting terms",
                "operational": "Operational and process terms",
                "general": "General business terms"
            },
            "mappings": [
                {
                    "business_term": "customer",
                    "table_name": "CUSTOMERS",
                    "column_name": "CUSTOMER_ID",
                    "description": "Customer identifier",
                    "synonyms": ["client", "buyer", "account"],
                    "category": "customer",
                    "confidence": 1.0
                },
                {
                    "business_term": "customer name",
                    "table_name": "CUSTOMERS", 
                    "column_name": "CUSTOMER_NAME",
                    "description": "Full name of the customer",
                    "synonyms": ["client name", "buyer name", "account name"],
                    "category": "customer",
                    "confidence": 1.0
                },
                {
                    "business_term": "product",
                    "table_name": "PRODUCTS",
                    "column_name": "PRODUCT_ID", 
                    "description": "Product identifier",
                    "synonyms": ["item", "goods", "merchandise"],
                    "category": "product",
                    "confidence": 1.0
                },
                {
                    "business_term": "sales amount",
                    "table_name": "SALES",
                    "column_name": "AMOUNT",
                    "description": "Sales transaction amount",
                    "synonyms": ["revenue", "sales value", "transaction amount"],
                    "category": "sales",
                    "confidence": 1.0
                },
                {
                    "business_term": "order date",
                    "table_name": "ORDERS",
                    "column_name": "ORDER_DATE",
                    "description": "Date when order was placed",
                    "synonyms": ["purchase date", "transaction date"],
                    "category": "sales",
                    "confidence": 1.0
                }
            ]
        }
        return template
    
    def load_business_dictionary(self) -> Dict[str, Any]:
        """Load business dictionary from JSON file."""
        if self.business_dict_cache:
            return self.business_dict_cache
            
        try:
            if os.path.exists(self.business_dict_file):
                with open(self.business_dict_file, 'r', encoding='utf-8') as f:
                    business_dict = json.load(f)
                self.business_dict_cache = business_dict
                logger.info(f"Business dictionary loaded from {self.business_dict_file}")
                return business_dict
            else:
                # Create template if file doesn't exist
                template = self.create_business_dictionary_template()
                self.save_business_dictionary(template)
                return template
        except Exception as e:
            logger.error(f"Error loading business dictionary: {e}")
            return self.create_business_dictionary_template()
    
    def save_business_dictionary(self, business_dict: Dict[str, Any]) -> None:
        """Save business dictionary to JSON file."""
        try:
            with open(self.business_dict_file, 'w', encoding='utf-8') as f:
                json.dump(business_dict, f, indent=2, ensure_ascii=False)
            self.business_dict_cache = business_dict
            logger.info(f"Business dictionary saved to {self.business_dict_file}")
        except Exception as e:
            logger.error(f"Error saving business dictionary: {e}")
            raise
    
    def add_business_mapping(self, mapping: BusinessMapping) -> None:
        """Add a new business mapping to the dictionary."""
        business_dict = self.load_business_dictionary()
        
        new_mapping = {
            "business_term": mapping.business_term,
            "table_name": mapping.table_name,
            "column_name": mapping.column_name,
            "description": mapping.description,
            "synonyms": mapping.synonyms or [],
            "category": mapping.category,
            "confidence": mapping.confidence
        }
        
        business_dict["mappings"].append(new_mapping)
        self.save_business_dictionary(business_dict)
        logger.info(f"Added business mapping: {mapping.business_term} -> {mapping.table_name}.{mapping.column_name}")
    
    def update_business_mapping(self, business_term: str, updated_mapping: Dict[str, Any]) -> bool:
        """Update an existing business mapping."""
        business_dict = self.load_business_dictionary()
        
        for i, mapping in enumerate(business_dict["mappings"]):
            if mapping["business_term"].lower() == business_term.lower():
                business_dict["mappings"][i].update(updated_mapping)
                self.save_business_dictionary(business_dict)
                logger.info(f"Updated business mapping: {business_term}")
                return True
        
        logger.warning(f"Business mapping not found: {business_term}")
        return False
    
    def remove_business_mapping(self, business_term: str) -> bool:
        """Remove a business mapping from the dictionary."""
        business_dict = self.load_business_dictionary()
        
        original_count = len(business_dict["mappings"])
        business_dict["mappings"] = [
            mapping for mapping in business_dict["mappings"]
            if mapping["business_term"].lower() != business_term.lower()
        ]
        
        if len(business_dict["mappings"]) < original_count:
            self.save_business_dictionary(business_dict)
            logger.info(f"Removed business mapping: {business_term}")
            return True
        else:
            logger.warning(f"Business mapping not found: {business_term}")
            return False
    
    def get_combined_schema(self) -> Dict[str, Any]:
        """Get combined schema metadata and business dictionary for AI consumption."""
        schema_data = self.load_schema()
        business_dict = self.load_business_dictionary()
        
        combined = {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "schema_version": schema_data.get("extraction_timestamp", "unknown"),
                "business_dict_version": business_dict.get("metadata", {}).get("created", "unknown")
            },
            "database_schema": schema_data,
            "business_dictionary": business_dict,
            "ai_context": {
                "available_tables": list(schema_data.get("tables", {}).keys()),
                "business_terms": [mapping["business_term"] for mapping in business_dict.get("mappings", [])],
                "categories": business_dict.get("categories", {}),
                "relationships": schema_data.get("relationships", [])
            }
        }
        
        return combined
    
    def refresh_schema(self) -> Dict[str, Any]:
        """Extract fresh schema from Oracle and update cache."""
        try:
            schema_data = self.extract_oracle_schema()
            self.save_schema(schema_data)
            logger.info("Schema refreshed successfully")
            return schema_data
        except Exception as e:
            logger.error(f"Error refreshing schema: {e}")
            raise
    
    def search_business_terms(self, query: str) -> List[Dict[str, Any]]:
        """Search business dictionary for terms matching the query."""
        business_dict = self.load_business_dictionary()
        query_lower = query.lower()
        
        matches = []
        for mapping in business_dict.get("mappings", []):
            business_term = mapping["business_term"].lower()
            
            # Check if business term is in the query (bidirectional search)
            if business_term in query_lower or query_lower in business_term:
                matches.append(mapping)
                continue
            
            # Check synonyms
            for synonym in mapping.get("synonyms", []):
                synonym_lower = synonym.lower()
                if synonym_lower in query_lower or query_lower in synonym_lower:
                    matches.append(mapping)
                    break
            
            # Check description
            if mapping.get("description"):
                desc_lower = mapping["description"].lower()
                if desc_lower in query_lower or query_lower in desc_lower:
                    matches.append(mapping)
        
        return matches
    
    def get_table_suggestions(self, business_term: str) -> List[Dict[str, Any]]:
        """Get table suggestions based on business term."""
        schema_data = self.load_schema()
        business_dict = self.load_business_dictionary()
        
        # Find mappings for this business term
        term_mappings = [
            mapping for mapping in business_dict.get("mappings", [])
            if mapping["business_term"].lower() == business_term.lower()
        ]
        
        suggestions = []
        for mapping in term_mappings:
            table_name = mapping["table_name"]
            full_table_name = f"{mapping.get('schema_name', 'USER')}.{table_name}"
            
            if full_table_name in schema_data.get("tables", {}):
                table_info = schema_data["tables"][full_table_name]
                suggestions.append({
                    "table_name": full_table_name,
                    "description": table_info.get("description", ""),
                    "column_count": len(table_info.get("columns", [])),
                    "row_count": table_info.get("row_count"),
                    "business_mapping": mapping
                })
        
        return suggestions
