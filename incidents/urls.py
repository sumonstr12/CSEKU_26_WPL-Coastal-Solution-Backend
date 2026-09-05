from django.urls import path
from .views import *

urlpatterns = {

    #     # INCIDENT REPORT
    #     path('incidents/', IncidentReportListView.as_view(), name='incident-list'),
    #     path('incidents/create/', IncidentReportCreateView.as_view(), name='incident-create'),
    #     path('incidents/<int:pk>/', IncidentReportDetailView.as_view(), name='incident-detail'),
    #     path('incidents/<int:pk>/update/', IncidentReportUpdateView.as_view(), name='incident-update'),
    #
    #     # EVIDENCE
    #     path('evidence/create/', EvidenceAttachmentCreateView.as_view(), name='evidence-create'),
    #     path('evidence/', EvidenceAttachmentListView.as_view(), name='evidence-list'),
    #     path('evidence/<int:pk>/delete/', EvidenceAttachmentDeleteView.as_view(), name='evidence-delete'),
    #
    #     # VERIFICATION
    #     path('verification/create/', IncidentVerificationView.as_view(), name='verification-create'),
    #
    #     # TRIAGE
    #     path('triage/create/', IncidentTriageView.as_view(), name='triage-create'),
    #
    #     # RESPONDER
    #     path('responders/', ResponderListView.as_view(), name='responder-list'),
    #     path('responders/<int:pk>/', ResponderDetailView.as_view(), name='responder-detail'),
    #     path('responders/availability/', ResponderAvailabilityUpdateView.as_view(), name='responder-availability'),
    #     path('responders/<int:pk>/areas/', ResponderAreaUpdateView.as_view(), name='responder-areas'),
    #
    #     # RESPONSE ASSIGNMENT
    #     path('assignments/create/', ResponseAssignmentCreateView.as_view(), name='assignment-create'),
    #     path('assignments/', ResponseAssignmentListView.as_view(), name='assignment-list'),
    #     path('assignments/<int:pk>/status/', ResponseAssignmentStatusUpdateView.as_view(), name='assignment-status'),
    #
    #     # RESPONSE ACTION
    #     path('actions/create/', ResponseActionCreateView.as_view(), name='action-create'),
    #     path('actions/', ResponseActionListView.as_view(), name='action-list'),
    #
    #     # ALERT
    #     path('alerts/create/', AlertCreateView.as_view(), name='alert-create'),
    #     path('alerts/', AlertListView.as_view(), name='alert-list'),
    #     path('alerts/active/', ActiveAlertListView.as_view(), name='alert-active'),
    #     path('alerts/<int:pk>/deactivate/', AlertDeactivateView.as_view(), name='alert-deactivate'),
    #
    #     # NOTIFICATION
    #     path('notifications/', NotificationListView.as_view(), name='notification-list'),
    #     path('notifications/<int:pk>/read/', NotificationReadView.as_view(), name='notification-read'),
    #     path('notifications/read-all/', NotificationReadAllView.as_view(), name='notification-read-all'),
    #
    #     # INCIDENT CATEGORIES
    #     path('categories/', IncidentCategoryListView.as_view(), name='category-list'),
    # ]

    # Incident Report
    path("incidents/", IncidentReportListView.as_view(), name="incident-list"),
    path("incidents/create/", IncidentReportCreateView.as_view(), name="incident-create"),
    path("incidents/<int:pk>/", IncidentReportDetailView.as_view(), name="incident-detail"),
}