import os
import uuid

from django.db import transaction

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from rest_framework.permissions import AllowAny
from rest_framework.parsers import MultiPartParser, FormParser

from .models import (
    IncidentReport,
    EvidenceAttachment,
)

from .serializers import (
    IncidentReportCreateSerializer,
    IncidentReportDetailSerializer,
)

from .media_utils import (
    process_uploaded_file,
)

from incidents.supabase_stroage import (
    upload_bytes,
)


# ============================================================
# CREATE INCIDENT REPORT
# ============================================================



class IncidentReportCreateView(APIView):
    permission_classes = [AllowAny]          # ← অ্যানোনিমাস রিপোর্টের জন্য
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = IncidentReportCreateSerializer(
            data=request.data,
            context={"request": request}
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

        files = request.FILES.getlist("files")

        # ----- ফাইল কাউন্ট ভ্যালিডেশন -----
        image_count = 0
        video_count = 0
        for uploaded_file in files:
            content_type = (uploaded_file.content_type or "").lower()
            if content_type.startswith("image/"):
                image_count += 1
            elif content_type.startswith("video/"):
                video_count += 1

        if image_count > 5:
            return Response(
                {"success": False, "message": "Maximum 5 images are allowed."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if video_count > 1:
            return Response(
                {"success": False, "message": "Maximum 1 video is allowed."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                incident = serializer.save()

                for uploaded_file in files:
                    content_type = (uploaded_file.content_type or "").lower()

                    if content_type.startswith("image/"):
                        file_type = "photo"
                    elif content_type.startswith("video/"):
                        file_type = "video"
                    elif content_type.startswith("audio/"):
                        file_type = "audio"
                    else:
                        file_type = "document"

                    original_file_name = uploaded_file.name
                    original_file_size = uploaded_file.size

                    processed = process_uploaded_file(uploaded_file)
                    file_data = processed["data"]
                    processed_content_type = processed["content_type"]
                    extension = processed["extension"]

                    unique_name = f"{uuid.uuid4().hex}{extension}"
                    file_path = f"incidents/{incident.id}/{unique_name}"

                    # ★★★ এখানেই মূল ফিক্স ★★★
                    upload_result = upload_bytes(
                        data=file_data,
                        file_path=file_path,
                        content_type=processed_content_type,
                    )
                    file_url = upload_result["url"]   # ← শুধু url স্ট্রিং নিন

                    EvidenceAttachment.objects.create(
                        incident=incident,
                        uploaded_by=(
                            request.user
                            if request.user.is_authenticated
                            else None
                        ),
                        file_name=unique_name,
                        original_file_name=original_file_name,
                        file_path=file_path,
                        file_url=file_url,
                        original_file_size=original_file_size,
                        file_size=len(file_data),
                        file_type=file_type,
                        mime_type=processed_content_type,
                    )

                response_serializer = IncidentReportDetailSerializer(
                    incident,
                    context={"request": request}
                )

                return Response(
                    {
                        "success": True,
                        "message": "Incident report submitted successfully.",
                        "data": response_serializer.data,
                    },
                    status=status.HTTP_201_CREATED
                )

        except Exception as e:
            import traceback
            traceback.print_exc()   # ডিবাগের জন্য টার্মিনালে দেখাবে
            return Response(
                {
                    "success": False,
                    "message": "Failed to submit incident report.",
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
                    "message": (
                        "Incident report not found."
                    )
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