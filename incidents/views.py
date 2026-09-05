from django.db import transaction

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from .models import (
    IncidentReport,
    EvidenceAttachment,
)

from .serializers import (
    IncidentReportCreateSerializer,
    IncidentReportDetailSerializer,
    EvidenceAttachmentSerializer,
)


# ============================================================
# CREATE INCIDENT REPORT
# ============================================================

class IncidentReportCreateView(APIView):
    def post(self, request):

        serializer = IncidentReportCreateSerializer(
            data=request.data,
            context={
                "request": request
            }
        )

        if not serializer.is_valid():

            return Response(
                {
                    "success": False,
                    "message": "Incident report validation failed.",
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        try:

            with transaction.atomic():

                incident = serializer.save()

                # --------------------------------------------
                # Handle uploaded evidence
                # --------------------------------------------

                files = request.FILES.getlist("files")

                if files:

                    image_count = 0
                    video_count = 0

                    for uploaded_file in files:

                        content_type = (
                            uploaded_file.content_type or ""
                        ).lower()

                        # ------------------------------------
                        # Determine file type
                        # ------------------------------------

                        if content_type.startswith("image/"):

                            file_type = "photo"
                            image_count += 1

                        elif content_type.startswith("video/"):

                            file_type = "video"
                            video_count += 1

                        elif content_type.startswith("audio/"):

                            file_type = "audio"

                        else:

                            file_type = "document"

                        # ------------------------------------
                        # Maximum number of files
                        # ------------------------------------

                        if image_count > 5:

                            return Response(
                                {
                                    "success": False,
                                    "message": (
                                        "Maximum 5 images are allowed."
                                    )
                                },
                                status=status.HTTP_400_BAD_REQUEST
                            )

                        if video_count > 1:

                            return Response(
                                {
                                    "success": False,
                                    "message": (
                                        "Maximum 1 video is allowed."
                                    )
                                },
                                status=status.HTTP_400_BAD_REQUEST
                            )

                        # ------------------------------------
                        # Create evidence
                        # ------------------------------------

                        EvidenceAttachment.objects.create(
                            incident=incident,
                            uploaded_by=request.user if request.user.is_authenticated else None,
                            file=uploaded_file,
                            file_type=file_type,
                            mime_type=content_type,
                        )

                # Return complete incident

                response_serializer = (
                    IncidentReportDetailSerializer(
                        incident,
                        context={
                            "request": request
                        }
                    )
                )

                return Response(
                    {
                        "success": True,
                        "message": (
                            "Incident report submitted successfully."
                        ),
                        "data": response_serializer.data,
                    },
                    status=status.HTTP_201_CREATED
                )

        except Exception as e:

            return Response(
                {
                    "success": False,
                    "message": (
                        "Failed to submit incident report."
                    ),
                    "error": str(e),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ============================================================
# INCIDENT REPORT LIST
# ============================================================

class IncidentReportListView(APIView):
    def get(self, request):

        incidents = (
            IncidentReport.objects
            .select_related(
                "category",
                "reporter",
            )
            .prefetch_related(
                "damage_types",
                "evidence",
            )
            .order_by("-created_at")
        )

        serializer = IncidentReportDetailSerializer(
            incidents,
            many=True,
            context={
                "request": request
            }
        )

        return Response(
            {
                "success": True,
                "count": incidents.count(),
                "data": serializer.data,
            },
            status=status.HTTP_200_OK
        )


# ============================================================
# INCIDENT REPORT DETAIL
# ============================================================

class IncidentReportDetailView(APIView):
    def get(self, request, pk):

        try:

            incident = (
                IncidentReport.objects
                .select_related(
                    "category",
                    "reporter",
                )
                .prefetch_related(
                    "damage_types",
                    "evidence",
                )
                .get(pk=pk)
            )

        except IncidentReport.DoesNotExist:

            return Response(
                {
                    "success": False,
                    "message": "Incident report not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = IncidentReportDetailSerializer(
            incident,
            context={
                "request": request
            }
        )

        return Response(
            {
                "success": True,
                "data": serializer.data,
            },
            status=status.HTTP_200_OK
        )