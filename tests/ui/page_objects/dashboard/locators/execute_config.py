# execute_config.py — Execute (Run) pane locators
#
# Selectors from #pane-run in dashboard/index.html.
# Key elements:
#   #startBtn / #stopBtn          run control buttons
#   .profile-btn                  load profile selector buttons
#   .profile-btn.active           currently selected profile
#   #cfgBaseUrl                   target URL input
#   #runBanner / #runBannerText   run status banner
#   #cfgVus / #cfgDuration        load config inputs

title = "Execute"
startUrl = "/"

elements = dict(
    # Pane container
    pane            = ("css", "#pane-run"),

    # Load profile picker
    profile_picker  = ("css", ".profile-picker"),
    profile_smoke   = ("css", "#profileBtnSmoke"),
    profile_ramp    = ("css", "#profileBtnRamp"),
    profile_soak    = ("css", "#profileBtnSoak"),
    profile_stress  = ("css", "#profileBtnStress"),
    profile_spike   = ("css", "#profileBtnSpike"),
    active_profile  = ("css", ".profile-picker .profile-btn.active"),

    # Target / auth inputs
    base_url_input  = ("css", "#cfgBaseUrl"),
    auth_token      = ("css", "#cfgAuthToken"),

    # Load configuration inputs
    vus_input       = ("css", "#cfgVus"),
    duration_input  = ("css", "#cfgDuration"),

    # Action buttons
    start_btn       = ("css", "#startBtn"),
    stop_btn        = ("css", "#stopBtn"),

    # Status banner
    run_banner      = ("css", "#runBanner"),
    run_banner_text = ("css", "#runBannerText"),
    run_banner_dot  = ("css", "#runBannerDot"),

    # SLO panel
    slo_panel_toggle = ("css", "#sloPanelToggle"),
    slo_panel       = ("css", "#sloPanel"),
    slo_p95         = ("css", "#sloP95"),
    slo_err_rate    = ("css", "#sloErrRate"),
)
