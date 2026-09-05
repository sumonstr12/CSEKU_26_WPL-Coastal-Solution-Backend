from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from .models import (
    IncidentReport,
    IncidentCategory,
    DamageType,
    EvidenceAttachment,
)


# ============================================================
# CATEGORY SERIALIZER
# ============================================================

class IncidentCategorySerializer(serializers.ModelSerializer):

    class Meta:
        model = IncidentCategory
        fields = [
            "id",
            "name",
            "name_bn",
            "description",
            "description_bn",
            "icon",
            "color_code",
            "default_priority",
        ]


# ============================================================
# DAMAGE TYPE SERIALIZER
# ============================================================

class DamageTypeSerializer(serializers.ModelSerializer):

    class Meta:
        model = DamageType
        fields = [
            "id",
            "name",
            "name_bn",
        ]


# ============================================================
# EVIDENCE SERIALIZER
# ============================================================

class EvidenceAttachmentSerializer(serializers.ModelSerializer):

    class Meta:
        model = EvidenceAttachment

        fields = [
            "id",
            "file",
            "file_name",
            "file_size",
            "file_type",
            "mime_type",
            "description",
            "description_bn",
            "latitude",
            "longitude",
            "is_verified",
            "is_public",
            "uploaded_at",
        ]

        read_only_fields = [
            "id",
            "file_name",
            "file_size",
            "is_verified",
            "uploaded_at",
        ]



# INCIDENT REPORT CREATE SERIALIZER

class IncidentReportCreateSerializer(serializers.ModelSerializer):

    # Category comes as ID
    category = serializers.PrimaryKeyRelatedField(
        queryset=IncidentCategory.objects.filter(
            is_active=True
        )
    )

    # Damage types come as list of IDs
    damage_types = serializers.PrimaryKeyRelatedField(
        queryset=DamageType.objects.filter(
            is_active=True
        ),
        many=True,
        required=False,
    )

    class Meta:
        model = IncidentReport

        fields = [
            # Basic information
            "category",
            "description",
            "description_bn",
            "situation",

            # Damage
            "damage_types",

            # Location
            "latitude",
            "longitude",
            "location_accuracy",
            "location_source",
            "address",
            "village",
            "union",
            "upazila",
            "district",
            "division",

            # Reporter
            "reporter_name",
            "reporter_phone",
            "is_anonymous",

            # Time
            "incident_time",

            # Affected people
            "affected_people_estimate",
            "affected_families_estimate",
            "injuries_count",
            "fatalities_count",
            "property_damage_estimate",

            # SOS
            "is_sos",

            # Additional
            "additional_info",
        ]

        read_only_fields = [
            "title",
            "title_bn",
            "status",
            "priority",
            "severity",
            "reporter",
            "report_time",
            "last_modified_by",
            "created_at",
            "updated_at",
        ]

    # VALIDATION
    def validate(self, attrs):

        # -----------------------------------------
        # GPS validation
        # -----------------------------------------

        latitude = attrs.get("latitude")
        longitude = attrs.get("longitude")

        if (latitude is None) != (longitude is None):
            raise serializers.ValidationError({
                "location": (
                    "Latitude and longitude must be provided together."
                )
            })


        # Future incident time

        incident_time = attrs.get("incident_time")

        if incident_time and incident_time > timezone.now():
            raise serializers.ValidationError({
                "incident_time": (
                    "Incident time cannot be in the future."
                )
            })

        # Anonymous reporter validation

        is_anonymous = attrs.get(
            "is_anonymous",
            False
        )

        reporter_name = attrs.get("reporter_name")
        reporter_phone = attrs.get("reporter_phone")

        if is_anonymous:
            # For anonymous reports, reporter account
            # is not required.
            pass

        return attrs


    # CREATE
    @transaction.atomic
    def create(self, validated_data):

        damage_types = validated_data.pop(
            "damage_types",
            []
        )

        request = self.context.get("request")


        # Reporter

        reporter = None

        if request and request.user.is_authenticated:
            reporter = request.user

        # Category
        category = validated_data["category"]


        # Generate title
        district = validated_data.get("district")
        upazila = validated_data.get("upazila")

        location = upazila or district

        if location:
            title = (
                f"{category.name} Incident - {location}"
            )
        else:
            title = f"{category.name} Incident"

        # Anonymous report

        if validated_data.get("is_anonymous", False):
            reporter = None

        # Create incident

        incident = IncidentReport.objects.create(
            reporter=reporter,
            title=title,
            status="submitted",
            **validated_data
        )

        # Damage types

        if damage_types:
            incident.damage_types.set(
                damage_types
            )

        return incident

# INCIDENT REPORT DETAIL SERIALIZER

class IncidentReportDetailSerializer(serializers.ModelSerializer):

    category = IncidentCategorySerializer(
        read_only=True
    )

    damage_types = DamageTypeSerializer(
        many=True,
        read_only=True
    )

    evidence = EvidenceAttachmentSerializer(
        many=True,
        read_only=True
    )

    reporter_name = serializers.SerializerMethodField()

    class Meta:
        model = IncidentReport

        fields = [
            "id",

            "title",
            "title_bn",

            "description",
            "description_bn",

            "category",

            "status",
            "priority",
            "severity",
            "situation",

            "damage_types",

            "latitude",
            "longitude",
            "location_accuracy",
            "location_source",

            "address",
            "village",
            "union",
            "upazila",
            "district",
            "division",

            "reporter_name",
            "is_anonymous",

            "report_time",
            "incident_time",

            "affected_people_estimate",
            "affected_families_estimate",
            "injuries_count",
            "fatalities_count",
            "property_damage_estimate",

            "is_sos",

            "evidence",

            "additional_info",

            "created_at",
            "updated_at",
        ]

    def get_reporter_name(self, obj):

        if obj.is_anonymous:
            return "Anonymous"

        if obj.reporter:
            return getattr(
                obj.reporter,
                "full_name",
                obj.reporter.username
            )

        return None