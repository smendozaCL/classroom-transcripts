import streamlit as st
from utils.view_table import get_table_client, list_table_items
from datetime import datetime
from operator import itemgetter
import pytz
import time
import assemblyai as aai
import os

# Initialize session state for status values if not already set
if "transcription_statuses" not in st.session_state:
    st.session_state.transcription_statuses = [
        "queued",  # Initial state
        "processing",  # Being transcribed
        "completed",  # Done
        "error",  # Failed
        "failed"  # Another error state
    ]

# US timezone options
US_TIMEZONES = [
    'US/Eastern',
    'US/Central', 
    'US/Mountain',
    'US/Pacific',
    'US/Alaska',
    'US/Hawaii'
]

# Initialize timezone in session state
if "timezone" not in st.session_state:
    st.session_state.timezone = 'US/Pacific'

# Add timezone picker to sidebar
with st.sidebar:
    st.session_state.timezone = st.selectbox(
        "Select Timezone",
        options=US_TIMEZONES,
        index=US_TIMEZONES.index(st.session_state.timezone),
        help="Choose your local timezone",
        format_func=lambda x: x.replace('US/', '')
    )

# Update local_tz to use session state
local_tz = pytz.timezone(st.session_state.timezone)

# Initialize AssemblyAI client
aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")
transcriber = aai.Transcriber()

def format_file_size(size_in_bytes):
    """Convert bytes to human readable format"""
    if not isinstance(size_in_bytes, (int, float)):
        return "N/A"
    for unit in ["B", "KB", "MB", "GB"]:
        if size_in_bytes < 1024:
            return f"{size_in_bytes:.2f} {unit}"
        size_in_bytes /= 1024
    return f"{size_in_bytes:.2f} TB"

# Get timezone abbreviation
def get_timezone_abbr(tz):
    """Get timezone abbreviation (e.g., PST, EST)"""
    return datetime.now(pytz.timezone(tz)).strftime('%Z')

def get_transcript_status(transcript_id):
    """Get transcript status from AssemblyAI"""
    # Skip test data
    if transcript_id.startswith('test_'):
        return "completed"
        
    try:
        transcript = aai.Transcript.get_by_id(transcript_id)
        return transcript.status.value
    except Exception as e:
        if "not found" in str(e).lower():
            return "error"  # Transcript doesn't exist in AssemblyAI
        st.error(f"Error getting transcript status: {str(e)}")
        return "error"

st.title("🔍 Audio Files & Transcriptions")

# Initialize table client
table_client = get_table_client()

@st.cache_data(ttl=300)
def get_transcript_statuses():
    """Get all transcript statuses in one API call"""
    try:
        # Create parameters to get all transcripts
        params = aai.ListTranscriptParameters(
            limit=100  # Adjust limit as needed
        )
        response = transcriber.list_transcripts(params)
        
        # Create mapping of transcript ID to status
        status_map = {}
        for t in response.transcripts:
            # Handle test data
            if t.id.startswith('test_'):
                status_map[t.id] = "completed"
            else:
                status_map[t.id] = t.status.value
                
        # Get next page if available
        while response.page_details.before_id_of_prev_url:
            params.before_id = response.page_details.before_id_of_prev_url
            response = transcriber.list_transcripts(params)
            for t in response.transcripts:
                if t.id.startswith('test_'):
                    status_map[t.id] = "completed"
                else:
                    status_map[t.id] = t.status.value
                    
        return status_map
    except Exception as e:
        st.error(f"Error getting transcript statuses: {str(e)}")
        return {}

@st.cache_data(ttl=300)
def load_table_data(_table_client):
    """Load and process table data with caching"""
    items = list_table_items(_table_client)
    if not items:
        return []
    
    # Get all transcript statuses at once
    transcript_statuses = get_transcript_statuses()
    
    items_list = []
    progress_bar = st.progress(0, "Processing items...")
    
    for i, item in enumerate(items):
        item_dict = dict(item)
        
        # Add formatted size
        if "blobSize" in item_dict:
            item_dict["formatted_size"] = format_file_size(item_dict["blobSize"])
        
        # Get status from cached transcript statuses
        if "transcriptId" in item_dict:
            item_dict["status"] = transcript_statuses.get(item_dict["transcriptId"], "error")
        else:
            item_dict["status"] = "pending"
            
        item_dict["_previous_status"] = item_dict["status"]
        
        # Process timestamp
        if "uploadTime" not in item_dict:
            item_dict["uploadTime"] = item_dict.get("Timestamp", datetime.min)
            
        try:
            dt = datetime.fromisoformat(item_dict["uploadTime"].replace('Z', '+00:00'))
            local_dt = dt.astimezone(local_tz)
            item_dict["_timestamp"] = local_dt
            item_dict["uploadTime"] = local_dt
        except ValueError as e:
            st.error(f"Error parsing time: {e}")
            
        items_list.append(item_dict)
        
        progress = (i + 1) / len(items)
        progress_bar.progress(progress, f"Processing {i + 1} of {len(items)} items...")
    
    progress_bar.empty()
    return items_list

with st.spinner("Loading table data..."):
    items_list = load_table_data(table_client)
    
if items_list:
    # Sort by timestamp
    items_list.sort(key=lambda x: x.get("_timestamp", datetime.min), reverse=True)

    # Define column order
    columns = [
        "status",
        "uploadTime",
        "RowKey",
        "formatted_size",
        "transcriptId",
        "audioUrl",
        "blobContentType",
        "blobLastModified"
    ]

    # Reorder dataframe columns and preserve status
    items_list = [{
        **{col: item.get(col) for col in columns},
        "status": item.get("status", "pending"),  # Default to pending if no status
        "_previous_status": item.get("status")  # Store original status for comparison
    } for item in items_list]

    st.dataframe(
        items_list,
        use_container_width=True,
        column_config={
            "status": st.column_config.SelectboxColumn(
                "Status",
                options=st.session_state.transcription_statuses,
                required=True,
                default="pending"
            ),
            "uploadTime": st.column_config.DatetimeColumn(
                f"Upload Time ({get_timezone_abbr(st.session_state.timezone)})",
                help=f"Time shown in {local_tz.zone}",
                format="YYYY-MM-DD HH:mm:ss"
            ),
            "RowKey": st.column_config.TextColumn("File Name"),
            "formatted_size": st.column_config.TextColumn("Size"),
            "transcriptId": st.column_config.TextColumn("Transcript ID"),
            "audioUrl": st.column_config.LinkColumn("Audio URL"),
            "blobContentType": st.column_config.TextColumn("Content Type"),
            "blobLastModified": st.column_config.DatetimeColumn(
                "Last Modified", format="D MMM YYYY, h:mm a"
            ),
        },
        hide_index=True,  # Hide the index column for cleaner display
    )

    # Show item count
    st.caption(f"Total files: {len(items_list)}")

    # Allow JSON view
    if st.checkbox("View Raw Data"):
        st.json(items_list)

    # Add this after the dataframe display
    if st.button("Update Status"):
        progress_bar = st.progress(0, "Updating statuses...")
        updates = [item for item in items_list if item.get("status") != item.get("_previous_status")]
        
        for i, item in enumerate(updates):
            try:
                # Update the entity in the table
                table_client.update_entity(
                    mode="merge",
                    entity={
                        "PartitionKey": item["PartitionKey"],
                        "RowKey": item["RowKey"],
                        "status": item["status"],
                    },
                )
                # Update progress
                progress = (i + 1) / len(updates)
                progress_bar.progress(progress, f"Updated {i + 1} of {len(updates)} items...")
                st.success(f"Updated status for {item['RowKey']}")
            except Exception as e:
                st.error(f"Error updating status for {item['RowKey']}: {str(e)}")
        
        progress_bar.empty()  # Remove progress bar when done
else:
    st.info("No files found in the system")

# Query builder
st.divider()
st.subheader("🔎 Query Builder")
query_type = st.selectbox(
    "Query Type", ["All Items", "By Partition Key", "By Row Key", "Custom Filter"]
)

if query_type == "By Partition Key":
    partition_key = st.text_input("Partition Key")
    if partition_key:
        try:
            items = list_table_items(table_client, f"PartitionKey eq '{partition_key}'")
            if items:
                st.dataframe([dict(item) for item in items])
            else:
                st.info("No items found with this partition key")
        except Exception as e:
            st.error(f"Query error: {str(e)}")

elif query_type == "By Row Key":
    row_key = st.text_input("Row Key")
    if row_key:
        try:
            items = list_table_items(table_client, f"RowKey eq '{row_key}'")
            if items:
                st.dataframe([dict(item) for item in items])
            else:
                st.info("No items found with this row key")
        except Exception as e:
            st.error(f"Query error: {str(e)}")

elif query_type == "Custom Filter":
    filter_query = st.text_input(
        "Filter Query", help="Example: PartitionKey eq 'key' and RowKey ge '2024'"
    )
    if filter_query:
        try:
            items = list_table_items(table_client, filter_query)
            if items:
                st.dataframe([dict(item) for item in items])
            else:
                st.info("No items found matching filter")
        except Exception as e:
            st.error(f"Query error: {str(e)}")

# Table operations
st.divider()
st.subheader("⚙️ Table Operations")
with st.expander("Delete Items"):
    st.warning("⚠️ Deletion operations are permanent")
    delete_type = st.selectbox("Delete By", ["Single Item", "Partition Key", "Filter"])

    if delete_type == "Single Item":
        pk = st.text_input("Partition Key of item to delete")
        rk = st.text_input("Row Key of item to delete")
        if st.button("Delete Item", type="primary"):
            if pk and rk:
                try:
                    table_client.delete_entity(pk, rk)
                    st.success(f"Deleted item with PK: {pk}, RK: {rk}")
                except Exception as e:
                    st.error(f"Delete error: {str(e)}")
            else:
                st.error("Both Partition Key and Row Key are required")

    elif delete_type == "Partition Key":
        pk = st.text_input("Partition Key to delete")
        if st.button("Delete All Items in Partition", type="primary"):
            if pk:
                try:
                    items = list_table_items(table_client, f"PartitionKey eq '{pk}'")
                    count = 0
                    for item in items:
                        table_client.delete_entity(item["PartitionKey"], item["RowKey"])
                        count += 1
                    st.success(f"Deleted {count} items from partition {pk}")
                except Exception as e:
                    st.error(f"Delete error: {str(e)}")
            else:
                st.error("Partition Key is required")
