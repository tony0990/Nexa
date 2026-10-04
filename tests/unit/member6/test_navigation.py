from nexa.ui.navigation import ALL_PAGE_KEYS, SIDEBAR_KEYS, WORKFLOW_PAGES


def test_sidebar_matches_member6_shell():
    assert SIDEBAR_KEYS == [
        "dashboard",
        "meeting",
        "review",
        "schedule",
        "people",
        "email_history",
        "audit",
        "settings",
    ]
    assert WORKFLOW_PAGES == ["search", "email_preview"]
    assert ALL_PAGE_KEYS == SIDEBAR_KEYS + WORKFLOW_PAGES
