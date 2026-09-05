import os
import django

# Django settings configure
os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "coastal_solution_backend.settings"
)

django.setup()


from incidents.models import IncidentCategory, DamageType


# ============================================================
# INCIDENT CATEGORIES
# ============================================================

categories = [
    {
        "name": "Cyclone",
        "name_bn": "ঘূর্ণিঝড়",
        "description": "A severe tropical storm characterized by strong winds and heavy rainfall.",
        "description_bn": "প্রবল বাতাস ও ভারী বৃষ্টিপাতসহ সৃষ্ট শক্তিশালী ঘূর্ণিঝড়।",
        "icon": "tornado",
        "color_code": "#DC2626",
        "default_priority": "critical",
    },
    {
        "name": "Storm Surge",
        "name_bn": "জলোচ্ছ্বাস",
        "description": "Abnormal rise of seawater caused by a storm.",
        "description_bn": "ঝড় বা ঘূর্ণিঝড়ের কারণে সমুদ্রের পানির অস্বাভাবিক উচ্চতা বৃদ্ধি।",
        "icon": "waves",
        "color_code": "#2563EB",
        "default_priority": "critical",
    },
    {
        "name": "Flood",
        "name_bn": "বন্যা",
        "description": "Overflow or accumulation of water that inundates normally dry land.",
        "description_bn": "অতিরিক্ত পানি প্রবাহ বা জমে যাওয়ার কারণে স্বাভাবিকভাবে শুষ্ক এলাকা প্লাবিত হওয়া।",
        "icon": "droplets",
        "color_code": "#0284C7",
        "default_priority": "high",
    },
    {
        "name": "River Erosion",
        "name_bn": "নদীভাঙন",
        "description": "Loss of riverbank land caused by river currents and water flow.",
        "description_bn": "নদীর স্রোত ও পানির প্রবাহের কারণে নদীর তীরের ভূমি ক্ষয়।",
        "icon": "land-plot",
        "color_code": "#92400E",
        "default_priority": "high",
    },
    {
        "name": "Heavy Rainfall",
        "name_bn": "অতিবৃষ্টি",
        "description": "Unusually heavy or prolonged rainfall.",
        "description_bn": "অস্বাভাবিকভাবে অতিরিক্ত বা দীর্ঘস্থায়ী বৃষ্টিপাত।",
        "icon": "cloud-rain",
        "color_code": "#4F46E5",
        "default_priority": "high",
    },
    {
        "name": "Salinity",
        "name_bn": "লবণাক্ততা",
        "description": "Increased salt concentration in soil or water.",
        "description_bn": "মাটি বা পানিতে লবণের মাত্রা বেড়ে যাওয়া।",
        "icon": "sprout",
        "color_code": "#65A30D",
        "default_priority": "medium",
    },
    {
        "name": "Waterlogging",
        "name_bn": "পানিবন্দী",
        "description": "Accumulation of water in residential, agricultural, or urban areas.",
        "description_bn": "বসতবাড়ি, কৃষিজমি বা এলাকায় অতিরিক্ত পানি জমে যাওয়া।",
        "icon": "cloud-sun-rain",
        "color_code": "#0891B2",
        "default_priority": "medium",
    },
]


# ============================================================
# CREATE / UPDATE CATEGORIES
# ============================================================

for data in categories:

    category, created = IncidentCategory.objects.update_or_create(
        name=data["name"],
        defaults=data,
    )

    if created:
        print(f"Created category: {category.id} - {category.name}")
    else:
        print(f"Updated category: {category.id} - {category.name}")


# ============================================================
# DAMAGE TYPES
# ============================================================

damage_types = [
    {
        "name": "House Damage",
        "name_bn": "বসতবাড়ির ক্ষতি",
    },
    {
        "name": "House Destroyed",
        "name_bn": "বসতবাড়ি সম্পূর্ণ ধ্বংস",
    },
    {
        "name": "Embankment Damage",
        "name_bn": "বাঁধের ক্ষতি",
    },
    {
        "name": "Embankment Breach",
        "name_bn": "বাঁধ ভেঙে যাওয়া",
    },
    {
        "name": "Road Damage",
        "name_bn": "রাস্তার ক্ষতি",
    },
    {
        "name": "Road Submerged",
        "name_bn": "রাস্তা পানিতে তলিয়ে যাওয়া",
    },
    {
        "name": "Bridge Damage",
        "name_bn": "সেতুর ক্ষতি",
    },
    {
        "name": "Crop Damage",
        "name_bn": "ফসলের ক্ষতি",
    },
    {
        "name": "Agricultural Land Damaged",
        "name_bn": "কৃষিজমির ক্ষতি",
    },
    {
        "name": "Fishery Damage",
        "name_bn": "মৎস্যখামারের ক্ষতি",
    },
    {
        "name": "Livestock Loss",
        "name_bn": "গবাদিপশুর ক্ষতি",
    },
    {
        "name": "Tree Damage",
        "name_bn": "গাছপালার ক্ষতি",
    },
    {
        "name": "Electricity Outage",
        "name_bn": "বিদ্যুৎ সংযোগ বিচ্ছিন্ন",
    },
    {
        "name": "Communication Disruption",
        "name_bn": "যোগাযোগ ব্যবস্থা বিঘ্নিত",
    },
    {
        "name": "Drinking Water Contamination",
        "name_bn": "সুপেয় পানি দূষিত",
    },
    {
        "name": "Drinking Water Shortage",
        "name_bn": "সুপেয় পানির সংকট",
    },
    {
        "name": "Waterlogging",
        "name_bn": "পানিবন্দী",
    },
    {
        "name": "Coastal Inundation",
        "name_bn": "উপকূলীয় এলাকা প্লাবিত",
    },
    {
        "name": "Land Erosion",
        "name_bn": "ভূমি ক্ষয়",
    },
    {
        "name": "Riverbank Erosion",
        "name_bn": "নদীর তীর ভাঙন",
    },
    {
        "name": "Saltwater Intrusion",
        "name_bn": "লবণাক্ত পানি প্রবেশ",
    },
    {
        "name": "School Damage",
        "name_bn": "শিক্ষাপ্রতিষ্ঠানের ক্ষতি",
    },
    {
        "name": "Healthcare Facility Damage",
        "name_bn": "স্বাস্থ্যকেন্দ্রের ক্ষতি",
    },
    {
        "name": "Market Damage",
        "name_bn": "বাজারের ক্ষতি",
    },
    {
        "name": "Injury",
        "name_bn": "আহত ব্যক্তি",
    },
    {
        "name": "Fatality",
        "name_bn": "প্রাণহানি",
    },
    {
        "name": "Missing Person",
        "name_bn": "নিখোঁজ ব্যক্তি",
    },
    {
        "name": "Displacement",
        "name_bn": "বাস্তুচ্যুতি",
    },
]


# ============================================================
# CREATE / UPDATE DAMAGE TYPES
# ============================================================

for data in damage_types:

    damage, created = DamageType.objects.update_or_create(
        name=data["name"],
        defaults=data,
    )

    if created:
        print(f"Created damage type: {damage.id} - {damage.name}")
    else:
        print(f"Updated damage type: {damage.id} - {damage.name}")


print("\nData seeding completed successfully!")