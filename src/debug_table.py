import streamlit as st
from utils.view_table import get_table_client, list_table_items

st.title("🔍 Table Debug View")

# Initialize table client
table_client = get_table_client()

# Display raw table data
st.subheader("📋 Raw Table Data")
try:
    items = list_table_items(table_client)
    if items:
        # Convert to list of dicts for display
        items_list = [dict(item) for item in items]
        st.dataframe(
            items_list,
            use_container_width=True,
            column_config={
                "PartitionKey": st.column_config.TextColumn("Partition Key"),
                "RowKey": st.column_config.TextColumn("Row Key"),
                "Timestamp": st.column_config.DatetimeColumn("Timestamp", format="D MMM YYYY, h:mm a"),
            }
        )
        
        # Show item count
        st.caption(f"Total items: {len(items_list)}")
        
        # Allow JSON view
        if st.checkbox("View as JSON"):
            st.json(items_list)
    else:
        st.info("No items found in table")
except Exception as e:
    st.error(f"Error loading table data: {str(e)}")

# Query builder
st.divider()
st.subheader("🔎 Query Builder")
query_type = st.selectbox(
    "Query Type",
    ["All Items", "By Partition Key", "By Row Key", "Custom Filter"]
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
    filter_query = st.text_input("Filter Query", help="Example: PartitionKey eq 'key' and RowKey ge '2024'")
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
    delete_type = st.selectbox(
        "Delete By",
        ["Single Item", "Partition Key", "Filter"]
    )
    
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