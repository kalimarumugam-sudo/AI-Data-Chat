import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import numpy as np
from .data_loader import load_data
from .ai_service import USE_OPENAI, enhanced_query_handler
from .database_tools import (
    get_db_manager,
    get_db_status,
    set_db_status,
    init_database_connection,
    close_database_connection,
)

greeting = """
You can use this sidebar to filter and sort the data based on the columns available in the data table. Here are some examples of the kinds of questions you can ask me:

1. **Filtering:** Show only Voice products for Destination North Region.
2. **Sorting:** Show all rates for East Region in descending order.
3. **Answer questions about the data:** What is the average rate for South Region and Product Voice?
4. **Aggregations:** Show the top 5 suppliers by total volume.

You can also say **Reset** to clear the current filter/sort, or **Help** for more usage tips.
"""

def enhance_data_processing(df):
    """Enhance data processing with date and numeric column conversion"""
    if df is None:
        return df
    
    # Convert date columns to datetime if they exist
    date_columns = ['Next Valid From', 'Next Valid Until']
    for col in date_columns:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
    
    # Ensure numeric columns are properly formatted
    numeric_columns = ['Rate', 'Next Rate', 'Next Rate Diff', 'FP Diff', 'Proportion', 'Floor Price', 'Volume']
    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    return df

def create_dashboard_styling():
    """Add professional dashboard CSS styling"""
    st.markdown("""
    <style>
    .main .block-container {
        padding-top: 0.5rem;
        padding-bottom: 0rem;
        padding-left: 1rem;
        padding-right: 1rem;
    }
    .stApp > header {
        background-color: transparent;
    }
    .stApp {
        margin-top: 0;
    }
    .main .block-container {
        max-width: 100%;
    }
    .stImage {
        margin-bottom: 0rem;
    }
    .stTitle {
        margin-bottom: 0rem;
    }
    .stMarkdown {
        margin-top: 0rem;
        margin-bottom: 0rem;
    }
    .stMarkdown p {
        margin: 0.5rem 0 0 0 !important;
        padding: 0 !important;
    }
    .stPlotlyChart {
        margin-bottom: 0rem;
    }
    .stSubheader {
        margin-top: 0rem;
        margin-bottom: 0rem;
    }
    </style>
    """, unsafe_allow_html=True)

def create_kpi_metrics(data):
    """Create KPI metrics dashboard"""
    if data is None or data.empty:
        return
    
    # Use the actual column names from CSV
    rate_col = 'Rate'
    volume_col = 'Volume'
    supplier_col = 'Supplier'
    
    if rate_col not in data.columns:
        st.warning(f"Rate column not found. Available columns: {list(data.columns)}")
        return
    
    # Calculate KPIs from actual data
    total_records = len(data)
    avg_rate = data[rate_col].mean() if not data[rate_col].isna().all() else 0
    
    # Calculate revenue using Rate * Proportion
    if volume_col in data.columns:
        total_revenue = (data[rate_col] * data[volume_col]).sum()
    else:
        total_revenue = data[rate_col].sum()
    
    # Get unique suppliers
    unique_suppliers = data[supplier_col].nunique() if supplier_col in data.columns else 0
    
    # KPI metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="Total Records",
            value=f"{total_records:,.0f}",
            delta="Active Dataset"
        )
    
    with col2:
        st.metric(
            label="Average Rate",
            value=f"${avg_rate:.2f}" if avg_rate > 0 else "N/A",
            delta="Current Period"
        )
    
    with col3:
        st.metric(
            label="Total Revenue",
            value=f"${total_revenue:,.0f}" if total_revenue > 0 else "N/A",
            delta="Calculated"
        )
    
    with col4:
        st.metric(
            label="Unique Suppliers",
            value=f"{unique_suppliers}",
            delta="Active"
        )

def create_visualizations(data):
    """Create interactive Plotly visualizations"""
    if data is None or data.empty:
        return
    
    rate_col = 'Rate'
    volume_col = 'Volume'
    supplier_col = 'Supplier'
    
    if rate_col not in data.columns:
        return
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Top 10 Suppliers by Volume grouped by Destination
        if supplier_col in data.columns and volume_col in data.columns and 'Destination' in data.columns:
            try:
                # Calculate total volume by supplier and destination
                supplier_dest_volumes = data.groupby([supplier_col, 'Destination'])[volume_col].sum().reset_index()
                
                # Get top 10 suppliers overall
                top_suppliers = data.groupby(supplier_col)[volume_col].sum().nlargest(10).index
                
                # Filter to only show top 10 suppliers
                top_10_data = supplier_dest_volumes[supplier_dest_volumes[supplier_col].isin(top_suppliers)]
                
                if not top_10_data.empty:
                    # Create stacked bar chart
                    fig_supplier_dest = px.bar(
                        top_10_data,
                        x=supplier_col,
                        y=volume_col,
                        color='Destination',
                        title='Top 10 Suppliers by Volume (Grouped by Destination)',
                        barmode='stack'
                    )
                    fig_supplier_dest.update_layout(height=400)
                    st.plotly_chart(fig_supplier_dest, use_container_width=True)
                else:
                    st.info("No supplier volume data available for visualization")
            except Exception as e:
                st.warning(f"Could not create supplier chart: {str(e)}")
        else:
            st.info("Required columns not available for supplier analysis")
    
    with col2:
        # Rate vs Floor Price scatter plot grouped by destination
        if 'Floor Price' in data.columns and 'Destination' in data.columns:
            try:
                # Filter out null values for better visualization
                plot_data = data.dropna(subset=['Floor Price', rate_col])
                
                if not plot_data.empty:
                    fig_rate_floor = px.scatter(
                        plot_data, 
                        x='Floor Price', 
                        y=rate_col, 
                        color='Destination',
                        title='Rate vs Floor Price by Destination',
                        hover_data=['Destination', 'Supplier', 'Product'] if 'Product' in data.columns else ['Destination', 'Supplier']
                    )
                    fig_rate_floor.update_layout(height=400)
                    st.plotly_chart(fig_rate_floor, use_container_width=True)
                else:
                    st.info("No valid rate/floor price data for visualization")
            except Exception as e:
                st.warning(f"Could not create rate comparison chart: {str(e)}")
        else:
            st.info("Floor Price or Destination column not available for comparison")

def ensure_oracle_connection(show_message=False):
    """Automatically connect to Oracle if not already connected"""
    if not get_db_status():
        try:
            if init_database_connection():
                set_db_status(True)
                if show_message:
                    st.success("✅ Connected to Oracle database")
                return True
        except Exception as e:
            st.error(f"❌ Failed to connect to Oracle: {str(e)}")
            return False
    return get_db_status()

def header_container():
    """Create a header container with logo and title"""
    st.markdown("""
    <div style="text-align: left; margin-top: 0; padding-top: 0;">
        <h1 style="color: black; margin: 0; padding: 0;">AI Data Chat Dashboard</h1>
        <p style="color: #666; margin: 5px 0 0 0; font-size: 20px;">Comprehensive Analysis & Insights with AI Chat</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")  # This horizontal line belongs to the header section

def is_calculation_result(sql_query, query_result):
    #check if the query is a calculation result
    calc_keywords = ['avg','count', 'sum', 'min', 'max']
    if any(keyword in sql_query.lower() for keyword in calc_keywords):
        return True
    else:
        return False

def run_app():
    """Main function to run the Streamlit application"""
    # Streamlit app configuration
    st.set_page_config(
        page_title="AI Data Chat Dashboard", 
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Add dashboard styling
    create_dashboard_styling()

    # Load the data from external file
    df, success_message, error_message = load_data()

    # Check if data loaded successfully
    if df is not None:
        # Enhance data processing
        df = enhance_data_processing(df)
        # Initialize session state for current dataframe
        if 'current_df' not in st.session_state:
            st.session_state.current_df = df
    else:
        # Handle error case - no data loaded
        st.error(f"❌ Failed to load data: {error_message}")
        st.markdown("""
        **To use this application:**
        1. Ensure 'sample_rates.csv' exists in the data/csv/ directory
        2. Check that the CSV file is properly formatted
        3. Restart the application after adding the file
        """)
        st.stop()  # Stop execution if no data

    # Create professional dashboard header
    header_container()
    
    # Show data loading status
    
    # Create KPI metrics dashboard
    if df is not None:
        create_kpi_metrics(st.session_state.current_df)

    # Initialize session state
    if "openai_model" not in st.session_state:
        st.session_state["openai_model"] = "gpt-4"

    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": greeting}]

    # Sidebar - Chat Interface (Hideable)
    with st.sidebar:
        # Add logo if it exists
        try:
            st.image("resources/logo.png", width=200)
        except:
            pass  # If logo doesn't exist, just continue without it
        
        st.subheader("💬 AI Data Chat")
        
        # Show current LLM provider
        provider_name = "🤖 OpenAI GPT-4" if USE_OPENAI else "🧠 AWS Bedrock Claude 3.5 Sonnet"
        st.info(f"**LLM Provider:** {provider_name}")
        
        st.write("Talk to your Data!")
        
        # Clear chat button at top
        if st.button("🗑️ Clear Chat", use_container_width=True):
            st.session_state.messages = [{"role": "assistant", "content": greeting}]
            st.rerun()

        st.divider()
        
        # Display chat history in the middle
        chat_container = st.container(height=400)
        with chat_container:
            # Ensure greeting is always shown if no messages exist or if first message isn't greeting
            if not st.session_state.messages or (st.session_state.messages and st.session_state.messages[0].get("content") != greeting):
                st.session_state.messages = [{"role": "assistant", "content": greeting}] + st.session_state.messages
            
            for message in st.session_state.messages:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])

    # Chat input at the very bottom of sidebar
    with st.sidebar:
        # Chat input (positioned at bottom)
        if prompt := st.chat_input("Ask about your data here..."):
            # Add user message to chat history
            st.session_state.messages.append({"role": "user", "content": prompt})
            
            # Show user message in sidebar
            with chat_container:
                # Show user message
                with st.chat_message("user"):
                    st.markdown(prompt)

                # Generate assistant response using enhanced handler (routes local vs Oracle)
                with st.chat_message("assistant"):
                    try:
                        # Ensure Oracle connection is available (but don't show message yet)
                        ensure_oracle_connection(show_message=False)

                        # Use enhanced query handler (intelligent routing behind the scenes)
                        ai_response, sql_query, query_result, data_source = enhanced_query_handler(
                            prompt, st.session_state.current_df
                        )
                        
                        # Show connection message only if we actually used Oracle
                        if data_source in ["oracle", "custom_query"]:
                            st.success("✅ Connected to Oracle database")

                        # Display AI response
                        st.markdown(ai_response)

                        # If a SQL query produced results, show and apply them
                        if sql_query and query_result is not None and not isinstance(query_result, str):
                            # print(f"DEBUG: Processing query results - data_source: {data_source}, result_type: {type(query_result)}")
                            st.code(sql_query, language="sql")
                            

                            if data_source == "local" and not is_calculation_result(sql_query, query_result):
                                # For local queries, update the data table
                                st.session_state.current_df = query_result
                                st.success(f"✅ Local query executed! Updated table with {len(query_result)} rows.")
                                # Don't rerun to avoid clearing the chat
                            else:
                                # For Oracle queries, display results in chat instead of updating data table
                                st.success(f"✅ Oracle query executed! Found {len(query_result)} rows.")
                                
                                # Display results in chat with compact table only
                                if len(query_result) > 0:
                                    st.markdown("**Query Results:**")
                                    
                                    # Show compact interactive dataframe by default
                                    if len(query_result) <= 10:
                                        # Show all rows if 10 or fewer
                                        st.dataframe(query_result, use_container_width=True, hide_index=True)
                                    else:
                                        # Show first 5 rows with note
                                        st.dataframe(query_result.head(5), use_container_width=True, hide_index=True)
                                        st.info(f"📊 Showing first 5 rows of {len(query_result)} total results.")
                                else:
                                    st.info("No results found.")

                        # Persist assistant message
                        st.session_state.messages.append({"role": "assistant", "content": ai_response})

                    except Exception as e:
                        error_msg = f"Error processing your request: {str(e)}"
                        st.error(error_msg)
                        st.session_state.messages.append({"role": "assistant", "content": error_msg})

    # Main content area - Visualizations and Data Display    
    st.markdown("---")
    
    # Create visualizations
    if df is not None:
        create_visualizations(st.session_state.current_df)
    
    # Data Display Section
    st.markdown("---")
    st.markdown("#### Filtered Data")
    
    # Display current data (either original or query results)
    st.dataframe(
        st.session_state.current_df, 
        use_container_width=True, 
        height=300,
        hide_index=True,
        key="data"
    )

if __name__ == "__main__":
    run_app()
