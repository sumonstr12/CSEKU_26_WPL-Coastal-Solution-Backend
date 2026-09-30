from django.urls import path
from .profile_views import MyProfileView

urlpatterns = [
    path("me/", MyProfileView.as_view(), name="profile-me"),
]