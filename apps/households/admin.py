from django.contrib import admin

from .models import ActivityLog, Household, Invitation, Membership


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    autocomplete_fields = ["user"]


@admin.register(Household)
class HouseholdAdmin(admin.ModelAdmin):
    list_display = ["name", "currency", "created_by", "created_at"]
    search_fields = ["name"]
    inlines = [MembershipInline]


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ["email", "household", "role", "expires_at", "accepted_at", "revoked"]
    list_filter = ["role", "revoked"]
    readonly_fields = ["token_hash"]


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ["description", "household", "actor", "created_at"]
    list_filter = ["verb"]
