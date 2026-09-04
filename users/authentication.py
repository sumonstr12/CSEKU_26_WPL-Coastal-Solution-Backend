from django.contrib.auth.backends import BaseBackend
from django.db.models import Q
from django.contrib.auth import get_user_model

User = get_user_model()


class UserAuthenticationBackend(BaseBackend):

    def authenticate(self, request, username=None, password=None, **kwargs):

        if username is None or password is None:
            return None

        try:
            user = User.objects.get(
                Q(username=username) |
                Q(email=username)
            )
        except User.DoesNotExist:
            return None
        except User.MultipleObjectsReturned:
            return None

        if user.check_password(password) and user.is_active:
            return user

        return None

    def get_user(self, user_id):

        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None