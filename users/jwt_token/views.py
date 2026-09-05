from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework.response import Response
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator


@method_decorator(csrf_exempt, name='dispatch')
class CookieTokenRefreshView(TokenRefreshView):

    def post(self, request, *args, **kwargs):
        refresh_token = request.COOKIES.get("refresh_token")

        print("Refresh Token from cookie:", refresh_token)

        if not refresh_token:
            return Response(
                {"error": "No refresh token in cookie"},
                status=400
            )

        data = request.data.copy()
        data["refresh"] = refresh_token

        serializer = self.get_serializer(data=data)

        serializer.is_valid(raise_exception=True)

        return Response(serializer.validated_data)
