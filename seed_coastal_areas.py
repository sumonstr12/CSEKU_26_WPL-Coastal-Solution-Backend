# seed_coastal_areas.py
import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'coastal_solution_backend.settings')  # Replace with your project's settings
django.setup()

from users.models import AdministrativeArea

# Data structure: Division -> Districts -> Upazilas
coastal_data = {
    "Barishal": {
        "Barguna": ["Amtali", "Bamna", "Barguna Sadar", "Betagi", "Patharghata", "Taltali"],
        "Barishal": ["Agailjhara", "Babuganj", "Bakerganj", "Banaripara", "Barishal Sadar", "Gaurnadi", "Hizla",
                     "Mehendiganj", "Muladi", "Wazirpur"],
        "Bhola": ["Bhola Sadar", "Burhanuddin", "Char Fasson", "Daulatkhan", "Lalmohan", "Manpura", "Tazumuddin"],
        "Jhalokati": ["Jhalokati Sadar", "Kanthalia", "Nalchity", "Rajapur"],
        "Patuakhali": ["Bauphal", "Dashmina", "Galachipa", "Kalapara", "Mirzaganj", "Patuakhali Sadar", "Rangabali",
                       "Dumki"],
        "Pirojpur": ["Bhandaria", "Kawkhali", "Mathbaria", "Nazirpur", "Nesarabad", "Pirojpur Sadar", "Zianagar"],
    },
    "Chattogram": {
        "Chandpur": ["Chandpur Sadar", "Faridganj", "Haimchar", "Hajiganj", "Kachua", "Matlab Dakshin", "Matlab Uttar",
                     "Shahrasti"],
        "Chattogram": ["Anwara", "Banshkhali", "Boalkhali", "Chandanaish", "Fatikchhari", "Hathazari", "Lohagara",
                       "Mirsharai", "Patiya", "Rangunia", "Raozan", "Sandwip", "Satkania", "Sitakunda"],
        "Cox's Bazar": ["Chakaria", "Cox's Bazar Sadar", "Kutubdia", "Maheshkhali", "Ramu", "Teknaf", "Ukhia", "Pekua"],
        "Feni": ["Chhagalnaiya", "Daganbhuiyan", "Feni Sadar", "Parshuram", "Sonagazi", "Fulgazi"],
        "Lakshmipur": ["Lakshmipur Sadar", "Raipur", "Ramganj", "Ramgati", "Kamalnagar"],
        "Noakhali": ["Begumganj", "Noakhali Sadar", "Senbagh", "Subarnachar", "Kabirhat", "Companiganj", "Chatkhil"],
    },
    "Dhaka": {
        "Gopalganj": ["Gopalganj Sadar", "Kashiani", "Kotalipara", "Muksudpur", "Tungipara"],
        "Madaripur": ["Kalkini", "Madaripur Sadar", "Rajoir", "Shibchar"],
        "Munshiganj": ["Gazaria", "Lohajang", "Munshiganj Sadar", "Sirajdikhan", "Sreenagar", "Tongibari"],
        "Shariatpur": ["Bhedarganj", "Damudya", "Gosairhat", "Naria", "Shariatpur Sadar", "Zajira"],
        "Faridpur": ["Alfadanga", "Bhanga", "Boalmari", "Charbhadrasan", "Faridpur Sadar", "Madhukhali", "Nagarkanda",
                     "Sadarpur", "Saltha"],
        "Rajbari": ["Baliakandi", "Goalandaghat", "Pangsha", "Rajbari Sadar", "Kalukhali"],
    },
    "Khulna": {
        "Bagerhat": ["Bagerhat Sadar", "Chitalmari", "Fakirhat", "Kachua", "Mollahat", "Mongla", "Morrelganj", "Rampal",
                     "Sarankhola"],
        "Jessore": ["Abhaynagar", "Bagherpara", "Chaugachha", "Jessore Sadar", "Jhikargachha", "Keshabpur",
                    "Manirampur", "Sharsha"],
        "Khulna": ["Batiaghata", "Dacope", "Dighalia", "Dumuria", "Koyra", "Paikgachha", "Phultala", "Rupsha",
                   "Terokhada"],
        "Satkhira": ["Assasuni", "Debhata", "Kalaroa", "Kaliganj", "Satkhira Sadar", "Shyamnagar", "Tala"],
        "Narail": ["Kalia", "Lohagara", "Narail Sadar"],
    },
}


def seed_administrative_areas():
    print("Starting to seed coastal administrative areas...")
    print("=" * 60)

    created_count = 0
    existing_count = 0

    for division_name, districts in coastal_data.items():
        # Create or get Division
        division, created = AdministrativeArea.objects.get_or_create(
            name=division_name,
            area_type=AdministrativeArea.AreaType.DIVISION,
            defaults={'parent': None}
        )
        if created:
            created_count += 1
            print(f"✓ Created Division: {division_name} (ID: {division.id})")
        else:
            existing_count += 1
            print(f"ℹ Division already exists: {division_name} (ID: {division.id})")

        for district_name, upazilas in districts.items():
            district, created = AdministrativeArea.objects.get_or_create(
                name=district_name,
                area_type=AdministrativeArea.AreaType.DISTRICT,
                defaults={'parent': division}
            )
            if created:
                created_count += 1
                print(f"  ✓ Created District: {district_name} (ID: {district.id})")
            else:
                existing_count += 1
                print(f"  ℹ District already exists: {district_name} (ID: {district.id})")
                # Ensure parent is set correctly
                if district.parent != division:
                    district.parent = division
                    district.save()
                    print(f"    ↳ Updated parent for {district_name}")

            for upazila_name in upazilas:
                upazila, created = AdministrativeArea.objects.get_or_create(
                    name=upazila_name,
                    area_type=AdministrativeArea.AreaType.UPAZILA,
                    defaults={'parent': district}
                )
                if created:
                    created_count += 1
                    print(f"    ✓ Created Upazila: {upazila_name} (ID: {upazila.id})")
                else:
                    existing_count += 1
                    # Ensure parent is set correctly
                    if upazila.parent != district:
                        upazila.parent = district
                        upazila.save()
                        print(f"    ↳ Updated parent for {upazila_name}")

    print("=" * 60)
    print(f"\n✅ Seeding completed!")
    print(f"   New entries created: {created_count}")
    print(f"   Existing entries found: {existing_count}")
    print(f"   Total entries in DB: {AdministrativeArea.objects.count()}")

    # Show summary
    print("\n📊 Summary:")
    print(f"   Divisions: {AdministrativeArea.objects.filter(area_type='DIVISION').count()}")
    print(f"   Districts: {AdministrativeArea.objects.filter(area_type='DISTRICT').count()}")
    print(f"   Upazilas: {AdministrativeArea.objects.filter(area_type='UPAZILA').count()}")


if __name__ == "__main__":
    seed_administrative_areas()