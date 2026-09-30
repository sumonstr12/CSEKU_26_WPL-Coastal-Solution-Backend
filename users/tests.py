from django.test import TestCase
from users.models import AdministrativeArea, CitizenProfile, CommunityVolunteerProfile, User
from healper_functions.register_helper import create_role_profile


class CommunityVolunteerRegistrationProfileTests(TestCase):
	def create_user(self, role, district):
		return User.objects.create_user(
			phone_number=f"+880170000{User.objects.count():04d}",
			full_name="Registration Test User",
			password="test-password",
			role=role,
			district=district,
		)

	def test_bagerhat_volunteer_gets_matching_district_area(self):
		area = AdministrativeArea.objects.create(
			name="Bagerhat",
			area_type=AdministrativeArea.AreaType.DISTRICT,
		)
		self.create_user(User.Role.COMMUNITY_VOLUNTEER, "বাগেরহাট")
		user = User.objects.get(full_name="Registration Test User")

		create_role_profile(user)

		profile = CommunityVolunteerProfile.objects.get(user=user)
		self.assertEqual(profile.administrative_area, area)

	def test_chattogram_volunteer_gets_matching_district_area(self):
		area = AdministrativeArea.objects.create(
			name="Chattogram",
			area_type=AdministrativeArea.AreaType.DISTRICT,
		)
		self.create_user(User.Role.COMMUNITY_VOLUNTEER, "চট্টগ্রাম")
		user = User.objects.get(full_name="Registration Test User")

		create_role_profile(user)

		profile = CommunityVolunteerProfile.objects.get(user=user)
		self.assertEqual(profile.administrative_area, area)

	def test_volunteer_profile_remains_unassigned_without_matching_area(self):
		self.create_user(User.Role.COMMUNITY_VOLUNTEER, "Unknown district")
		user = User.objects.get(full_name="Registration Test User")

		with self.assertLogs("healper_functions.register_helper", level="WARNING"):
			create_role_profile(user)

		profile = CommunityVolunteerProfile.objects.get(user=user)
		self.assertIsNone(profile.administrative_area)

	def test_existing_area_less_volunteer_profile_is_assigned(self):
		area = AdministrativeArea.objects.create(
			name="Bagerhat",
			area_type=AdministrativeArea.AreaType.DISTRICT,
		)
		user = self.create_user(User.Role.COMMUNITY_VOLUNTEER, "বাগেরহাট")
		profile = CommunityVolunteerProfile.objects.create(user=user)

		create_role_profile(user)

		profile.refresh_from_db()
		self.assertEqual(profile.administrative_area, area)

	def test_citizen_profile_creation_is_unchanged(self):
		user = self.create_user(User.Role.CITIZEN, "খুলনা")

		create_role_profile(user)

		self.assertTrue(CitizenProfile.objects.filter(user=user).exists())
