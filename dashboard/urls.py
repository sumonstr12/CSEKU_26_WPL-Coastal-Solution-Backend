from django.urls import path
from .views import *

urlpatterns = [
    path('citizen/overview/', CitizenOverviewView.as_view(), name='dashboard-overview'),
    path('volunteer/overview/', VolunteerOverviewView.as_view(), name='volunteer-dashboard-overview'),
    path(
        'volunteer/shelters/',
        VolunteerShelterListView.as_view(),
        name='volunteer-shelter-list',
    ),
    path(
        'volunteer/tasks/<int:pk>/status/',
        VolunteerTaskStatusUpdateView.as_view(),
        name='volunteer-task-status-update',
    ),
]
