from incidents.models import IncidentCategory, DamageType

categories = [
    {
        "name": "Cyclone",
        "name_bn": "ঘূর্ণিঝড়",
        "description": "A severe tropical storm characterized by strong winds, heavy rainfall, and potentially destructive coastal impacts.",
        "description_bn": "প্রবল বাতাস, ভারী বৃষ্টিপাত এবং উপকূলীয় এলাকায় ব্যাপক ক্ষয়ক্ষতি সৃষ্টিকারী শক্তিশালী ঘূর্ণিঝড়।",
        "icon": "tornado",
        "color_code": "#DC2626",
        "default_priority": "critical",
    },
    {
        "name": "Storm Surge",
        "name_bn": "জলোচ্ছ্বাস",
        "description": "Abnormal rise of seawater caused by a storm, often resulting in coastal flooding and inundation.",
        "description_bn": "ঘূর্ণিঝড় বা প্রবল ঝড়ের কারণে সমুদ্রের পানি অস্বাভাবিকভাবে বৃদ্ধি পেয়ে উপকূলীয় এলাকা প্লাবিত হওয়ার ঘটনা।",
        "icon": "waves",
        "color_code": "#2563EB",
        "default_priority": "critical",
    },
    {
        "name": "Flood",
        "name_bn": "বন্যা",
        "description": "Overflow or accumulation of water that inundates normally dry land.",
        "description_bn": "অতিরিক্ত পানি প্রবাহ বা জমে যাওয়ার কারণে স্বাভাবিকভাবে শুষ্ক এলাকা পানিতে প্লাবিত হওয়া।",
        "icon": "droplets",
        "color_code": "#0284C7",
        "default_priority": "high",
    },
    {
        "name": "River Erosion",
        "name_bn": "নদীভাঙন",
        "description": "Gradual or rapid loss of riverbank land caused by river currents and water flow.",
        "description_bn": "নদীর স্রোত ও পানির প্রবাহের কারণে নদীর তীরের মাটি ক্ষয় হয়ে জমি ও বসতভিটা বিলীন হওয়ার ঘটনা।",
        "icon": "land-plot",
        "color_code": "#92400E",
        "default_priority": "high",
    },
    {
        "name": "Heavy Rainfall",
        "name_bn": "অতিবৃষ্টি",
        "description": "Unusually heavy or prolonged rainfall that may cause flooding, waterlogging, and other hazards.",
        "description_bn": "অস্বাভাবিকভাবে অতিরিক্ত বা দীর্ঘস্থায়ী বৃষ্টিপাত, যার ফলে বন্যা, পানিবন্দী অবস্থা ও অন্যান্য দুর্যোগ সৃষ্টি হতে পারে।",
        "icon": "cloud-rain",
        "color_code": "#4F46E5",
        "default_priority": "high",
    },
    {
        "name": "Salinity",
        "name_bn": "লবণাক্ততা",
        "description": "Increased salt concentration in soil or water, particularly affecting coastal communities, agriculture, and drinking water.",
        "description_bn": "মাটি বা পানিতে লবণের মাত্রা বেড়ে যাওয়া, যা বিশেষ করে উপকূলীয় জনগোষ্ঠী, কৃষি ও সুপেয় পানির ওপর নেতিবাচক প্রভাব ফেলে।",
        "icon": "sprout",
        "color_code": "#65A30D",
        "default_priority": "medium",
    },
    {
        "name": "Waterlogging",
        "name_bn": "পানিবন্দী",
        "description": "Accumulation of water in residential, agricultural, or urban areas due to heavy rainfall, poor drainage, flooding, or tidal effects.",
        "description_bn": "অতিবৃষ্টি, অপর্যাপ্ত নিষ্কাশন ব্যবস্থা, বন্যা বা জোয়ারের কারণে বসতবাড়ি, কৃষিজমি বা এলাকায় পানি জমে যাওয়ার পরিস্থিতি।",
        "icon": "cloud-sun-rain",
        "color_code": "#0891B2",
        "default_priority": "medium",
    },
]

for data in categories:
    category, created = IncidentCategory.objects.update_or_create(
        name=data["name"],
        defaults=data,
    )

    print(
        f"{'Created' if created else 'Updated'}: "
        f"{category.id} - {category.name}"
    )