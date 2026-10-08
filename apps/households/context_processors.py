def household(request):
    """Expose the active household, membership, and household switcher to templates."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}
    return {
        "household": getattr(request, "household", None),
        "membership": getattr(request, "membership", None),
        "user_memberships": user.memberships.select_related("household"),
    }
