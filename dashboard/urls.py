from django.urls import path
from .views import *
from .officer_views import (
    OfficerBadgeView,
    OfficerReportsView,
    OfficerVerifyReportView,
    OfficerSheltersView,
    OfficerMapView,
    OfficerNotificationsView,
    OfficerNotificationReadAllView,
    OfficerProfileView,
    OfficerSectionView,
)

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
    path('officer/overview/', OfficerOverviewView.as_view(), name='officer-dashboard-overview'),

    path('officer/badges/', OfficerBadgeView.as_view(), name='officer-badges'),
    path('officer/reports/', OfficerReportsView.as_view(), name='officer-reports'),
    path('officer/reports/<int:pk>/verify/', OfficerVerifyReportView.as_view(), name='officer-report-verify'),
    path('officer/shelters/', OfficerSheltersView.as_view(), name='officer-shelters'),
    path('officer/map/', OfficerMapView.as_view(), name='officer-map'),
    path('officer/notifications/', OfficerNotificationsView.as_view(), name='officer-notifications'),
    path('officer/notifications/read-all/', OfficerNotificationReadAllView.as_view(), name='officer-notifications-read-all'),
    path('officer/profile/', OfficerProfileView.as_view(), name='officer-profile'),
    path('officer/section/<str:key>/', OfficerSectionView.as_view(), name='officer-section'),
]
