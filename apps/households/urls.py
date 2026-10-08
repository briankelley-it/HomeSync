from django.urls import path

from . import views

app_name = "households"

urlpatterns = [
    path("new/", views.HouseholdCreateView.as_view(), name="create"),
    path("switch/", views.switch_household, name="switch"),
    path("settings/", views.HouseholdSettingsView.as_view(), name="settings"),
    path("members/", views.MembersView.as_view(), name="members"),
    path("members/<int:pk>/role/", views.change_member_role, name="change_role"),
    path("members/<int:pk>/remove/", views.remove_member, name="remove_member"),
    path("invitations/<int:pk>/revoke/", views.revoke_invitation, name="revoke_invitation"),
    path("invitations/<str:token>/", views.accept_invitation, name="accept_invitation"),
]
