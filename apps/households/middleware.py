from .models import Membership

SESSION_KEY = "current_household_id"


class CurrentHouseholdMiddleware:
    """Attach the user's active household and membership to each request.

    Sets ``request.household`` and ``request.membership`` (both ``None`` for
    anonymous users or users without a household). The active household is
    stored in the session and always re-validated against the database, so a
    removed member immediately loses access.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.household = None
        request.membership = None
        if request.user.is_authenticated:
            memberships = Membership.objects.filter(user=request.user).select_related("household")
            selected_id = request.session.get(SESSION_KEY)
            membership = None
            if selected_id:
                membership = memberships.filter(household_id=selected_id).first()
            if membership is None:
                membership = memberships.order_by("created_at").first()
                if membership:
                    request.session[SESSION_KEY] = membership.household_id
                else:
                    request.session.pop(SESSION_KEY, None)
            if membership:
                request.membership = membership
                request.household = membership.household
        return self.get_response(request)
