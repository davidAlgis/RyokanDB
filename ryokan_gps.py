import time

from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import ArcGIS, Nominatim


class RyokanLocator:
    def __init__(self):
        # 1. Primary: OpenStreetMap (Detailed, strict)
        self.geolocator_osm = Nominatim(user_agent="ryokan_explorer_v2")
        self.geocode_osm = RateLimiter(
            self.geolocator_osm.geocode, min_delay_seconds=1.1
        )

        # 2. Fallback: ArcGIS (Excellent for commercial POIs/Hotels)
        self.geolocator_arcgis = ArcGIS()
        # ArcGIS is robust but we still want to be polite
        self.geocode_arcgis = RateLimiter(
            self.geolocator_arcgis.geocode, min_delay_seconds=0.5
        )

    def clean_address(self, address):
        if not address:
            return ""
        # Remove common scraping artifacts
        return address.replace("Show map", "").strip()

    def get_coordinates(self, name, address):
        """
        Tries to find coordinates using multiple strategies and providers.
        Returns: (lat, lon) or (None, None)
        """
        clean_addr = self.clean_address(address)

        # --- Strategy 1: OSM with Address ---
        try:
            loc = self.geocode_osm(clean_addr)
            if loc:
                return loc.latitude, loc.longitude
        except:
            pass

        # --- Strategy 2: ArcGIS with Name + Address (Very effective) ---
        try:
            # ArcGIS handles "Ryokan Name, City" very well
            query = f"{name}, {clean_addr}"
            loc = self.geocode_arcgis(query)
            if loc:
                return loc.latitude, loc.longitude
        except:
            pass

        # --- Strategy 3: ArcGIS with Name + "Japan" ---
        try:
            query = f"{name} Japan"
            loc = self.geocode_arcgis(query)
            if loc:
                return loc.latitude, loc.longitude
        except:
            pass

        # --- Strategy 4: OSM with Name + "Japan" (Last resort) ---
        try:
            query = f"{name} Japan"
            loc = self.geocode_osm(query)
            if loc:
                return loc.latitude, loc.longitude
        except:
            pass

        return None, None
