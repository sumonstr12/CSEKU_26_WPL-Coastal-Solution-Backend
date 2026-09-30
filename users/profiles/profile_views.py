"""
Profile views for the Profiles UI.

GET  /api/profiles/me/   → full profile (user + role-specific nested data)
PATCH /api/profiles/me/  → partial update matching ProfileEditModal payload
"""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .profile_serializers import ProfileReadSerializer, ProfileUpdateSerializer


class MyProfileView(APIView):
    """
    Retrieve or update the authenticated user's profile.

    Response shape is flat + nested `profile` so the React Profiles UI
    can consume it without transformation.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        data = ProfileReadSerializer().to_representation(request.user)
        return Response(
            {
                "status": True,
                "message": "Profile fetched successfully.",
                "data": data,
            },
            status=status.HTTP_200_OK,
        )

    def patch(self, request):
        serializer = ProfileUpdateSerializer(
            data=request.data,
            partial=True,
            context={"request": request},
        )
        if not serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": "Profile update failed.",
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer.update(request.user, serializer.validated_data)

        data = ProfileReadSerializer().to_representation(request.user)
        return Response(
            {
                "status": True,
                "message": "প্রোফাইল আপডেট হয়েছে",
                "data": data,
            },
            status=status.HTTP_200_OK,
        )