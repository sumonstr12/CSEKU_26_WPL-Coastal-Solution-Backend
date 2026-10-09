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
from .responder_views import (
    ResponderAcceptRequestView,
    ResponderAvailabilityView,
    ResponderBadgeView,
    ResponderContextView,
    ResponderMapView,
    ResponderMissionStatusView,
    ResponderOverviewView,
    ResponderProfileView,
    ResponderReportsView,
    ResponderSectionView,
    ResponderSheltersView,
)
from .authority_views import (
    AuthorityOverviewView,
    AuthorityBadgeView,
    AuthorityReportsView,
    AuthorityVerifyReportView,
    AuthoritySheltersView,
    AuthorityMapView,
    AuthorityProfileView,
    AuthoritySectionView,
)
from .volunteer_views import (
    VolunteerOverviewView,
    VolunteerBadgeView,
    VolunteerReportsView,
    VolunteerSheltersView,
    VolunteerMapView,
    VolunteerProfileView,
    VolunteerSectionView,
    VolunteerAvailabilityView,
    VolunteerCompleteTaskView,
    VolunteerUpdateTaskView,
    VolunteerOperationsView,
    VolunteerJoinOperationView,
    VolunteerActivitiesView,
)
from .citizen_views import (
    CitizenOverviewView as CitizenOverviewV2,
    CitizenBadgeView,
    CitizenSheltersView,
    CitizenMapView,
    CitizenProfileView,
)
from .notification_views import (
    NotificationListView,
    NotificationSummaryView,
    NotificationReadAllView,
    NotificationReadView,
)

urlpatterns = [
    # Citizen — FE-compatible (citizen_views)
    path('citizen/overview/', CitizenOverviewV2.as_view(), name='dashboard-overview'),
    path('citizen/badges/', CitizenBadgeView.as_view(), name='citizen-badges'),
    path('citizen/shelters/', CitizenSheltersView.as_view(), name='citizen-shelters'),
    path('citizen/map/', CitizenMapView.as_view(), name='citizen-map'),
    path('citizen/profile/', CitizenProfileView.as_view(), name='citizen-profile'),

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

    path('responder/context/', ResponderContextView.as_view(), name='responder-context'),
    path('responder/overview/', ResponderOverviewView.as_view(), name='responder-overview'),
    path('responder/badges/', ResponderBadgeView.as_view(), name='responder-badges'),
    path('responder/reports/', ResponderReportsView.as_view(), name='responder-reports'),
    path('responder/shelters/', ResponderSheltersView.as_view(), name='responder-shelters'),
    path('responder/map/', ResponderMapView.as_view(), name='responder-map'),
    path('responder/profile/', ResponderProfileView.as_view(), name='responder-profile'),
    path('responder/section/<str:key>/', ResponderSectionView.as_view(), name='responder-section'),
    path('responder/availability/', ResponderAvailabilityView.as_view(), name='responder-availability'),
    path('responder/requests/<int:pk>/accept/', ResponderAcceptRequestView.as_view(), name='responder-request-accept'),
    path('responder/missions/<int:pk>/status/', ResponderMissionStatusView.as_view(), name='responder-mission-status'),

    # Local Authority
    path('authority/overview/', AuthorityOverviewView.as_view(), name='authority-overview'),
    path('authority/badges/', AuthorityBadgeView.as_view(), name='authority-badges'),
    path('authority/reports/', AuthorityReportsView.as_view(), name='authority-reports'),
    path('authority/reports/<int:pk>/verify/', AuthorityVerifyReportView.as_view(), name='authority-report-verify'),
    path('authority/shelters/', AuthoritySheltersView.as_view(), name='authority-shelters'),
    path('authority/map/', AuthorityMapView.as_view(), name='authority-map'),
    path('authority/profile/', AuthorityProfileView.as_view(), name='authority-profile'),
    path('authority/section/<str:key>/', AuthoritySectionView.as_view(), name='authority-section'),

    # Community Volunteer
    path('volunteer/overview/', VolunteerOverviewView.as_view(), name='volunteer-overview'),
    path('volunteer/badges/', VolunteerBadgeView.as_view(), name='volunteer-badges'),
    path('volunteer/reports/', VolunteerReportsView.as_view(), name='volunteer-reports'),
    path('volunteer/shelters/', VolunteerSheltersView.as_view(), name='volunteer-shelters'),
    path('volunteer/map/', VolunteerMapView.as_view(), name='volunteer-map'),
    path('volunteer/profile/', VolunteerProfileView.as_view(), name='volunteer-profile'),
    path('volunteer/section/<str:key>/', VolunteerSectionView.as_view(), name='volunteer-section'),
    path('volunteer/availability/', VolunteerAvailabilityView.as_view(), name='volunteer-availability'),
    path('volunteer/tasks/<str:pk>/complete/', VolunteerCompleteTaskView.as_view(), name='volunteer-task-complete'),
    path('volunteer/tasks/<str:pk>/update/', VolunteerUpdateTaskView.as_view(), name='volunteer-task-update'),
    path('volunteer/operations/', VolunteerOperationsView.as_view(), name='volunteer-operations'),
    path('volunteer/operations/<str:key>/join/', VolunteerJoinOperationView.as_view(), name='volunteer-operation-join'),
    path('volunteer/activities/', VolunteerActivitiesView.as_view(), name='volunteer-activities'),

    path('notifications/', NotificationListView.as_view(), name='notifications'),
    path('notifications/summary/', NotificationSummaryView.as_view(), name='notifications-summary'),
    path('notifications/read-all/', NotificationReadAllView.as_view(), name='notifications-read-all'),
    path('notifications/<int:pk>/read/', NotificationReadView.as_view(), name='notification-read'),
]