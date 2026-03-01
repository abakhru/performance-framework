# discover_config.py — Discover pane locators
#
# Selectors from #pane-discover in dashboard/index.html.
# The pane hosts a multi-step wizard:
#   Step 1: Source selection (URL scan, file upload, manual, etc.)
#   Step 2: Discover (runs probe)
#   Step 3: Review (endpoint table)
#   Step 4: Run config
#   Steps 5/6: Notify / Save & Launch
#
# Key elements tested in regression:
#   #pane-discover               pane container
#   #wizContainer                wizard root
#   .wiz-steps / .wiz-step       step indicator pills
#   #wizSrcUrl                   URL scan source card (default selected)
#   #wizUrl                      URL input field
#   #wizToken                    auth token input
#   #wiz2NextBtn                 "Next →" button (disabled until URL entered)

title = "Discover"
startUrl = "/"

elements = dict(
    # Pane container
    pane             = ("css", "#pane-discover"),

    # Wizard wrapper
    wiz_container    = ("css", "#wizContainer"),

    # Step indicator pills
    wiz_steps        = ("css", ".wiz-steps"),
    all_wiz_steps    = ("css", ".wiz-step"),
    wiz_step_1       = ("css", "#wizStep1Tab"),
    wiz_step_2       = ("css", "#wizStep2Tab"),

    # Step 1: source selection
    wiz_pane_1       = ("css", "#wizPane1"),
    src_url_card     = ("css", "#wizSrcUrl"),
    src_file_card    = ("css", "#wizSrcFile"),

    # URL scan inputs
    url_input        = ("css", "#wizUrl"),
    token_input      = ("css", "#wizToken"),
    deep_scan_chk    = ("css", "#wizDeepScan"),

    # Navigation button
    next_btn         = ("css", "#wiz2NextBtn"),

    # Step 3 review table
    preview_table    = ("css", ".disc-preview-table"),
    disc_count       = ("css", ".disc-count"),

    # Save & run
    disc_save_btn    = ("css", ".disc-save-btn"),
    disc_msg         = ("css", ".disc-msg"),
)
