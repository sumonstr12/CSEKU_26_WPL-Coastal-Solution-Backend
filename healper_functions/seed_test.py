from geopy.geocoders import Nominatim

geolocator = Nominatim(user_agent="test_app", timeout=10)

# Test 1: Simple query
result = geolocator.geocode("Dhaka, Bangladesh", country_codes="bd")
print("Result:", result)
print("Lat/Lng:", (result.latitude, result.longitude) if result else None)