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
from .notification_views import (
    NotificationListView,
    NotificationSummaryView,
    NotificationReadAllView,
    NotificationReadView,
)

urlpatterns = [
    path('citizen/overview/', CitizenOverviewView.as_view(), name='dashboard-overview'),
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

    # read-all / summary অবশ্যই <int:pk> এর আগে রাখতে হবে
    path('notifications/', NotificationListView.as_view(), name='notifications'),
    path('notifications/summary/', NotificationSummaryView.as_view(), name='notifications-summary'),
    path('notifications/read-all/', NotificationReadAllView.as_view(), name='notifications-read-all'),
    path('notifications/<int:pk>/read/', NotificationReadView.as_view(), name='notification-read'),
]