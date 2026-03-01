# overview_config.py — Overview pane locators
#
# Selectors from #pane-overview in dashboard/index.html.
# Key elements:
#   .health-badge         IDLE / NOMINAL / DEGRADED / CRITICAL badge
#   .health-kpi-val       p95, RPS, VUs, Error KPI values in the hero
#   .card / .card-value   metric cards grid
#   #hVus, #hReqs, ...    mini stats in the topbar (visible from any pane)

title = "Overview"
startUrl = "/"

elements = dict(
    # Pane container
    pane            = ("css", "#pane-overview"),

    # Health hero block
    health_hero     = ("css", "#healthHero"),
    health_badge    = ("css", "#healthBadge"),

    # Hero KPI values (inside health-hero)
    kpi_p95         = ("css", "#herP95Val"),
    kpi_rps         = ("css", "#herRpsVal"),
    kpi_vus         = ("css", "#herVusVal"),
    kpi_err         = ("css", "#herErrVal"),

    # Metric cards grid
    cards_container = ("css", "#pane-overview .cards"),
    card_reqs       = ("css", "#cReqs"),
    card_rps        = ("css", "#cRps"),
    card_vus        = ("css", "#cVus"),
    card_err        = ("css", "#cErr"),
    card_elapsed    = ("css", "#cElapsed"),
    card_p95        = ("css", "#cP95"),
    card_apdex      = ("css", "#cApdex"),

    # All metric card titles (generic)
    all_cards       = ("css", "#pane-overview .card"),
    all_card_labels = ("css", "#pane-overview .card-label"),

    # Mini header stats (visible from any pane, e.g. after a run)
    hstat_vus       = ("css", "#hVus"),
    hstat_reqs      = ("css", "#hReqs"),
    hstat_rps       = ("css", "#hRps"),
    hstat_p95       = ("css", "#hP95"),
    hstat_fail      = ("css", "#hFail"),
)
