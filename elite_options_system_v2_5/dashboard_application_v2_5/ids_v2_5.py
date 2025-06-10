# elite_options_system_v2_5/dashboard_application_v2_5/ids_v2_5.py
# Authoritative Dashboard Component IDs for EOTS V2.5 "Apex Predator"
# This file must be lean, containing only IDs for core application containers,
# stores, and primary user controls.

# Core Application Structure & State
ID_URL_LOCATION = "eots-url-location-id" # Changed prefix for v2.5 clarity
ID_PAGE_CONTENT = "eots-page-content-id" # Renamed from ID_MAIN_CONTENT_AREA
ID_MASTER_HEADER = "eots-master-header-id" # New as per directive
ID_STATUS_ALERT_CONTAINER = "eots-status-alert-container-id" # Renamed from ID_STATUS_DISPLAY_ALERT

# Data Stores
ID_MAIN_DATA_STORE = "eots-main-data-store-id" # Renamed from ID_MAIN_DATA_STORE_MEMORY / ID_SERVER_SIDE_STORE
# Note: Specific store types (memory, server-side) are implementation details.
# The ID here is for the primary dcc.Store holding the main analysis bundle.
# Other stores like ID_CURRENT_MODE_STORE might be kept if deemed essential for core app state.
ID_CURRENT_MODE_STORE = "eots-current-mode-store-id" # Kept as it's core to mode switching
ID_REFRESH_INTERVAL_STORE = "eots-refresh-interval-store-id" # Kept as it's core to refresh logic

# Primary User Controls
ID_SYMBOL_INPUT = "eots-symbol-input-id" # Kept, prefix changed
ID_MANUAL_REFRESH_BUTTON = "eots-manual-refresh-button-id" # Renamed from ID_FETCH_DATA_BUTTON
ID_REFRESH_INTERVAL_DROPDOWN = "eots-refresh-interval-dropdown-id" # Kept, prefix changed

# Timer/Interval Components
ID_INTERVAL_LIVE_UPDATE = "eots-interval-live-update-id" # Renamed from ID_AUTO_REFRESH_INTERVAL_COMPONENT

# Other essential core IDs (example, can be refined)
ID_CONTROL_PANEL_CONTAINER = "eots-control-panel-container-id" # For grouping controls
ID_MODE_SELECTOR_TABS = "eots-mode-selector-tabs-id" # Mode switching is core

# IDs explicitly NOT included as per directive (dynamic rendering pattern):
# - Static IDs for individual charts (e.g., ID_GIB_OI_BASED_GAUGE_VIZ)
# - IDs for minor labels or outputs that are not primary user controls or core containers.

# Ensure all used IDs are defined here. If other IDs are essential for the
# core app structure (loading, page switching, main data flow, primary interactions),
# they can be added. This list is based on Directive 1.1.

if __name__ == '__main__':
    # Print all defined IDs for verification
    all_ids = {name: value for name, value in locals().items() if name.startswith("ID_")}
    print("Defined Core Dashboard IDs for EOTS v2.5:")
    for name, value in all_ids.items():
        print(f"  {name}: \"{value}\"")
    print(f"Total Core IDs: {len(all_ids)}")
