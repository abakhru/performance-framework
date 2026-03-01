# endpoints_config.py — Endpoints pane locators
#
# Selectors from #pane-endpoints in dashboard/index.html.
# Key elements:
#   #groupFilter / .filter-btn    group filter pill buttons
#   .filter-btn.active            currently active group filter
#   #opsBody                      tbody of the operations table
#   table                         the main operations table inside the pane

title = "Endpoints"
startUrl = "/"

elements = dict(
    # Pane container
    pane            = ("css", "#pane-endpoints"),

    # Group filter bar
    group_filter    = ("css", "#groupFilter"),
    all_filter_btns = ("css", "#groupFilter .filter-btn"),
    active_filter   = ("css", "#groupFilter .filter-btn.active"),
    filter_all_btn  = ("css", "#groupFilter .filter-btn:has-text('All')"),

    # Operations table
    ops_table       = ("css", "#pane-endpoints table"),
    ops_table_head  = ("css", "#pane-endpoints thead"),
    ops_body        = ("css", "#opsBody"),
    ops_rows        = ("css", "#opsBody tr"),
    waiting_cell    = ("css", "#opsBody td[colspan='9']"),

    # Column headers
    col_operation   = ("css", "#pane-endpoints th:has-text('Operation')"),
    col_reqs        = ("css", "#pane-endpoints th:has-text('Reqs')"),
    col_err_pct     = ("css", "#pane-endpoints th:has-text('Err%')"),
    col_p95         = ("css", "#pane-endpoints th:has-text('p95')"),
)
