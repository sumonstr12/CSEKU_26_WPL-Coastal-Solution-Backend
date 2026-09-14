from django.urls import path
from .views import *

urlpatterns = [
    path('citizen/overview/', CitizenOverviewView.as_view(), name='dashboard-overview'),
]