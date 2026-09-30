from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from incidents.models import IncidentCategory, IncidentReport, ResponseAssignment, Shelter
from users.models import (
    AdministrativeArea,
    CommunityVolunteerProfile,
    User,
)


class VolunteerTaskStatusUpdateTests(APITestCase):
    """The test database is created and discarded by Django for this test case."""

    def setUp(self):
        self.category = IncidentCategory.objects.create(name="Flood")
        self.incident = IncidentReport.objects.create(
            category=self.category,
            description="Test incident for volunteer assignment status updates.",
            district="Khulna",
            title="Deliver emergency supplies",
            village="Test village",
            upazila="Test upazila",
        )
        self.volunteer_user = self.make_user(
            "volunteer-one", "01700000001", User.Role.COMMUNITY_VOLUNTEER
        )
        self.volunteer = CommunityVolunteerProfile.objects.create(user=self.volunteer_user)
        self.other_volunteer_user = self.make_user(
            "volunteer-two", "01700000002", User.Role.COMMUNITY_VOLUNTEER
        )
        self.other_volunteer = CommunityVolunteerProfile.objects.create(
            user=self.other_volunteer_user
        )
        self.non_volunteer = self.make_user(
            "citizen-one", "01700000003", User.Role.CITIZEN
        )

    @staticmethod
    def make_user(username, phone_number, role):
        return User.objects.create_user(
            username=username,
            phone_number=phone_number,
            full_name=username,
            password="test-password",
            role=role,
        )

    def make_assignment(self, volunteer=None, assignment_status="pending"):
        return ResponseAssignment.objects.create(
            incident=self.incident,
            assigned_volunteer=volunteer or self.volunteer,
            status=assignment_status,
            instructions="Deliver supplies to the assigned location.",
        )

    def endpoint(self, assignment):
        return reverse("volunteer-task-status-update", args=[assignment.pk])

    def test_volunteer_can_complete_own_task_and_response_uses_dashboard_shape(self):
        assignment = self.make_assignment()
        self.client.force_authenticate(self.volunteer_user)

        response = self.client.patch(self.endpoint(assignment), {"status": "completed"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            set(response.data), {"id", "title", "place", "due", "status", "detail"}
        )
        self.assertEqual(response.data["status"], "DONE")
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, "completed")

    def test_volunteer_cannot_complete_another_volunteers_task(self):
        assignment = self.make_assignment(volunteer=self.other_volunteer)
        self.client.force_authenticate(self.volunteer_user)

        response = self.client.patch(self.endpoint(assignment), {"status": "completed"})

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, "pending")

    def test_anonymous_request_is_denied(self):
        assignment = self.make_assignment()

        response = self.client.patch(self.endpoint(assignment), {"status": "completed"})

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_volunteer_user_is_denied(self):
        assignment = self.make_assignment()
        self.client.force_authenticate(self.non_volunteer)

        response = self.client.patch(self.endpoint(assignment), {"status": "completed"})

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_invalid_status_returns_validation_error(self):
        assignment = self.make_assignment()
        self.client.force_authenticate(self.volunteer_user)

        response = self.client.patch(self.endpoint(assignment), {"status": "in_progress"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", response.data)

    def test_cancelled_and_declined_tasks_cannot_be_completed(self):
        self.client.force_authenticate(self.volunteer_user)
        for assignment_status in ("cancelled", "declined"):
            with self.subTest(status=assignment_status):
                assignment = self.make_assignment(assignment_status=assignment_status)

                response = self.client.patch(
                    self.endpoint(assignment), {"status": "completed"}
                )

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                assignment.refresh_from_db()
                self.assertEqual(assignment.status, assignment_status)

    def test_repeating_completion_is_idempotent(self):
        assignment = self.make_assignment(assignment_status="completed")
        self.client.force_authenticate(self.volunteer_user)

        response = self.client.patch(self.endpoint(assignment), {"status": "completed"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "DONE")


class IncidentReportListAreaFilteringTests(APITestCase):
    def setUp(self):
        self.category = IncidentCategory.objects.create(name="Area Filter Test")
        self.bagerhat_incident = IncidentReport.objects.create(
            category=self.category,
            description="Incident in the volunteer's assigned district.",
            district="Bagerhat",
            upazila="Fakirhat",
        )
        self.khulan_incident = IncidentReport.objects.create(
            category=self.category,
            description="Incident outside the volunteer's assigned district.",
            district="Khulna",
            upazila="Koyra",
        )
        self.bagerhat_area = AdministrativeArea.objects.create(
            name="Bagerhat",
            area_type=AdministrativeArea.AreaType.DISTRICT,
        )
        self.volunteer_user = User.objects.create_user(
            username="report-area-volunteer",
            phone_number="01710000001",
            full_name="Area Volunteer",
            password="test-password",
            role=User.Role.COMMUNITY_VOLUNTEER,
        )
        self.volunteer_profile = CommunityVolunteerProfile.objects.create(
            user=self.volunteer_user,
            administrative_area=self.bagerhat_area,
        )
        self.citizen_user = User.objects.create_user(
            username="report-area-citizen",
            phone_number="01710000002",
            full_name="Area Citizen",
            password="test-password",
            role=User.Role.CITIZEN,
        )

    def incident_ids(self, response):
        return {incident["id"] for incident in response.data["data"]}

    def test_volunteer_receives_only_assigned_district_incidents(self):
        self.client.force_authenticate(self.volunteer_user)

        response = self.client.get("/api/v1/incidents/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.incident_ids(response), {self.bagerhat_incident.id})

    def test_volunteer_query_parameters_cannot_override_assigned_area(self):
        self.client.force_authenticate(self.volunteer_user)

        response = self.client.get("/api/v1/incidents/?district=Khulna&upazila=Koyra")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.incident_ids(response), {self.bagerhat_incident.id})

    def test_volunteer_without_assigned_area_receives_empty_list(self):
        self.volunteer_profile.administrative_area = None
        self.volunteer_profile.save(update_fields=["administrative_area"])
        self.client.force_authenticate(self.volunteer_user)

        response = self.client.get("/api/v1/incidents/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)
        self.assertEqual(response.data["data"], [])

    def test_citizen_still_receives_all_incidents(self):
        self.client.force_authenticate(self.citizen_user)

        response = self.client.get("/api/v1/incidents/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            self.incident_ids(response),
            {self.bagerhat_incident.id, self.khulan_incident.id},
        )

    def test_anonymous_request_still_receives_all_incidents(self):
        response = self.client.get("/api/v1/incidents/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            self.incident_ids(response),
            {self.bagerhat_incident.id, self.khulan_incident.id},
        )


class VolunteerShelterListTests(APITestCase):
    def setUp(self):
        self.category = IncidentCategory.objects.create(name="Cyclone", name_bn="ঘূর্ণিঝড়")
        self.bagerhat = AdministrativeArea.objects.create(
            name="Bagerhat",
            area_type=AdministrativeArea.AreaType.DISTRICT,
        )
        self.fakirhat = AdministrativeArea.objects.create(
            name="Fakirhat",
            area_type=AdministrativeArea.AreaType.UPAZILA,
            parent=self.bagerhat,
        )
        self.koyra = AdministrativeArea.objects.create(
            name="Koyra",
            area_type=AdministrativeArea.AreaType.UPAZILA,
            parent=AdministrativeArea.objects.create(
                name="Khulna",
                area_type=AdministrativeArea.AreaType.DISTRICT,
            ),
        )
        self.volunteer_user = User.objects.create_user(
            username="shelter-area-volunteer",
            phone_number="01720000001",
            full_name="Bagerhat Volunteer",
            password="test-password",
            role=User.Role.COMMUNITY_VOLUNTEER,
        )
        self.volunteer = CommunityVolunteerProfile.objects.create(
            user=self.volunteer_user,
            administrative_area=self.bagerhat,
        )
        self.citizen_user = User.objects.create_user(
            username="shelter-area-citizen",
            phone_number="01720000002",
            full_name="Test Citizen",
            password="test-password",
            role=User.Role.CITIZEN,
        )
        self.bagerhat_shelter = self.make_shelter(
            "BAG-1", "Bagerhat Shelter", "Bagerhat", "Fakirhat"
        )
        self.other_bagerhat_shelter = self.make_shelter(
            "BAG-2", "Other Bagerhat Shelter", "Bagerhat", "Mongla"
        )
        self.khulan_shelter = self.make_shelter(
            "KHL-1", "Khulna Shelter", "Khulna", "Koyra"
        )
        self.closed_shelter = self.make_shelter(
            "BAG-3", "Closed Bagerhat Shelter", "Bagerhat", "Fakirhat",
            status="CLOSED",
        )
        self.inactive_shelter = self.make_shelter(
            "BAG-4", "Inactive Bagerhat Shelter", "Bagerhat", "Fakirhat",
            is_active=False,
        )
        self.fakirhat_incident = IncidentReport.objects.create(
            category=self.category,
            title="Cyclone Incident - Fakirhat",
            description="Incident within Fakirhat.",
            district="Bagerhat",
            upazila="Fakirhat",
        )
        self.khulan_incident = IncidentReport.objects.create(
            category=self.category,
            title="Flood Incident - Koyra",
            description="Incident outside Bagerhat.",
            district="Khulna",
            upazila="Koyra",
        )

    @staticmethod
    def make_shelter(shelter_id, name, district, upazila, **extra):
        return Shelter.objects.create(
            id=shelter_id,
            name=name,
            district=district,
            upazila=upazila,
            capacity=100,
            occupied=25,
            **extra,
        )

    def endpoint(self):
        return reverse("volunteer-shelter-list")

    def returned_ids(self, response):
        return {shelter["id"] for shelter in response.data["data"]}

    def test_volunteer_receives_active_non_closed_shelters_in_assigned_district(self):
        self.client.force_authenticate(self.volunteer_user)

        response = self.client.get(self.endpoint())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            self.returned_ids(response),
            {self.bagerhat_shelter.id, self.other_bagerhat_shelter.id},
        )
        self.assertEqual(response.data["count"], 2)
        self.assertTrue(response.data["data"][0]["active"])

    def test_query_parameters_cannot_override_volunteer_area(self):
        self.client.force_authenticate(self.volunteer_user)

        response = self.client.get(
            f"{self.endpoint()}?district=Khulna&upazila=Koyra"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            self.returned_ids(response),
            {self.bagerhat_shelter.id, self.other_bagerhat_shelter.id},
        )

    def test_incident_lookup_returns_only_shelters_in_incident_upazila(self):
        self.client.force_authenticate(self.volunteer_user)

        response = self.client.get(
            self.endpoint(), {"incident": self.fakirhat_incident.id}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.returned_ids(response), {self.bagerhat_shelter.id})
        self.assertEqual(response.data["incident"]["id"], self.fakirhat_incident.id)
        self.assertEqual(response.data["incident"]["upazila"], "Fakirhat")

    def test_incident_lookup_cannot_override_area_with_query_parameters(self):
        self.client.force_authenticate(self.volunteer_user)

        response = self.client.get(
            self.endpoint(),
            {
                "incident": self.fakirhat_incident.id,
                "district": "Khulna",
                "upazila": "Koyra",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.returned_ids(response), {self.bagerhat_shelter.id})

    def test_incident_outside_assigned_area_returns_not_found(self):
        self.client.force_authenticate(self.volunteer_user)

        response = self.client.get(
            self.endpoint(), {"incident": self.khulan_incident.id}
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_volunteer_without_area_cannot_use_incident_id_to_find_shelters(self):
        self.volunteer.administrative_area = None
        self.volunteer.save(update_fields=["administrative_area"])
        self.client.force_authenticate(self.volunteer_user)

        response = self.client.get(
            self.endpoint(), {"incident": self.fakirhat_incident.id}
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_upazila_assignment_limits_results_to_that_upazila(self):
        self.volunteer.administrative_area = self.fakirhat
        self.volunteer.save(update_fields=["administrative_area"])
        self.client.force_authenticate(self.volunteer_user)

        response = self.client.get(self.endpoint())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.returned_ids(response), {self.bagerhat_shelter.id})

    def test_volunteer_without_area_receives_empty_list(self):
        self.volunteer.administrative_area = None
        self.volunteer.save(update_fields=["administrative_area"])
        self.client.force_authenticate(self.volunteer_user)

        response = self.client.get(self.endpoint())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)
        self.assertEqual(response.data["data"], [])

    def test_anonymous_request_is_denied(self):
        response = self.client.get(self.endpoint())

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_volunteer_request_is_denied(self):
        self.client.force_authenticate(self.citizen_user)

        response = self.client.get(self.endpoint())

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
