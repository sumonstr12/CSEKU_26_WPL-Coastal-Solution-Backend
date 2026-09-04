from rest_framework.permissions import BasePermission
from django.contrib.auth import get_user_model

from users.models import User

User = get_user_model()

class IsCitizen(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role == User.Role.CITIZEN


#         SYSTEM_ADMINISTRATOR = (
#             "SYSTEM_ADMINISTRATOR",
#             "System Administrator",
#         )


class isDisasterManagementOfficer(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role == User.Role.DISASTER_MANAGEMENT_OFFICER

class IsSystemAdmin(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role == User.Role.SYSTEM_ADMINISTRATOR

class IsCommunityVolunteer(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role == User.Role.COMMUNITY_VOLUNTEER

class IsResponder(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role == User.Role.RESPONDER
    

class IsLocalAuthority(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role == User.Role.LOCAL_AUTHORITY