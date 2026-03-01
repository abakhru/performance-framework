# navigation_config.py — sidebar tab locators
#
# Selectors derived from dashboard/index.html class/text structure:
#   div.tab                         all sidebar tabs
#   div.tab.active                  currently selected tab
#   div.tab:has-text('<Name>')      individual tab by label

title = "Performance Dashboard"
startUrl = "/"

elements = dict(
    # Container
    sidebar       = ("css", "aside.sidebar"),
    sidebar_nav   = ("css", ".sidebar-nav"),

    # Individual tabs — matched by visible text inside the tab span
    tab_execute   = ("css", ".tab:has-text('Execute')"),
    tab_overview  = ("css", ".tab:has-text('Overview')"),
    tab_endpoints = ("css", ".tab:has-text('Endpoints')"),
    tab_http      = ("css", ".tab:has-text('HTTP Metrics')"),
    tab_log       = ("css", ".tab:has-text('Log')"),
    tab_history   = ("css", ".tab:has-text('History')"),
    tab_discover  = ("css", ".tab:has-text('Discover')"),
    tab_lighthouse = ("css", ".tab:has-text('Lighthouse')"),

    # State
    active_tab    = ("css", ".tab.active"),

    # Status indicator in the header bar
    status_dot    = ("css", "#statusDot"),
    status_label  = ("css", "#statusLabel"),
    profile_chip  = ("css", "#profileChip"),

    # Page title in the top bar
    page_title    = ("css", "#pageTitle"),
)
