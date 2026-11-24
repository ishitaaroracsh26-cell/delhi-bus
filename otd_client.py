"""
DilliTransit - Delhi Open Transit Data (OTD) Client
Handles authorized connection to the official Delhi Open Transit Data portal (otd.delhi.gov.in).
When credentials are not present, securely provides transparent fallback to calibrated sample feeds.
"""

import os
import urllib.request
import urllib.error
import time
from typing import Dict, Any, Optional

class DelhiOTDClient:
    """
    Interface for Delhi Open Transit Data GTFS-Realtime feeds.
    Respects API credential rules, validates authorization, and provides transparent telemetry attribution.
    """
    BASE_URL = "https://otd.delhi.gov.in/api/realtime"

    def __init__(self):
        self.api_key: Optional[str] = os.environ.get("DELHI_OTD_API_KEY")
        self.data_source_mode = os.environ.get("DATA_SOURCE_MODE", "auto")
        self.is_connected = False
        self.last_sync_time: Optional[float] = None
        self.last_error: Optional[str] = None
        self.cached_vehicle_count = 0

        # Attempt initial verification if key is present
        if self.api_key:
            self._verify_connection()

    def _verify_connection(self):
        """Test the official endpoint with the provided credentials."""
        endpoint = f"{self.BASE_URL}/VehiclePositions.pb?key={self.api_key}"
        try:
            req = urllib.request.Request(
                endpoint,
                headers={"User-Agent": "DilliTransit-Hackathon/1.0"}
            )
            # Short timeout to avoid hanging if network is unreachable
            with urllib.request.urlopen(req, timeout=4) as response:
                if response.status == 200:
                    self.is_connected = True
                    self.last_sync_time = time.time()
                    self.last_error = None
                else:
                    self.is_connected = False
                    self.last_error = f"HTTP {response.status} from OTD portal"
        except urllib.error.HTTPError as e:
            self.is_connected = False
            self.last_error = f"HTTP {e.code}: {e.reason}"
        except Exception as e:
            self.is_connected = False
            self.last_error = f"Connection failed ({type(e).__name__}): {str(e)}"

    def get_feed_status(self) -> Dict[str, Any]:
        """Return transparent attribution of the telemetry data source."""
        if self.api_key and self.is_connected:
            return {
                "status": "LIVE",
                "source": "Delhi Open Transit Data (OTD) Portal",
                "portal_url": "https://otd.delhi.gov.in/",
                "protocol": "GTFS-Realtime (Protocol Buffers)",
                "endpoint": "VehiclePositions.pb",
                "authenticated": True,
                "last_sync_time": self.last_sync_time,
                "label": "Live Delhi GTFS-Realtime Data",
                "notes": "Connected to official Govt. of NCT of Delhi transport telemetry feed."
            }
        else:
            reason = "No DELHI_OTD_API_KEY configured" if not self.api_key else self.last_error
            return {
                "status": "SAMPLE",
                "source": "Calibrated Physics Probe Telemetry",
                "portal_url": "https://otd.delhi.gov.in/",
                "protocol": "GTFS Static Route Topology + Probe-Vehicle Simulation",
                "authenticated": False,
                "last_sync_time": time.time(),
                "label": "Sample & Calibrated Data",
                "reason": reason,
                "instructions": (
                    "To switch to live Delhi transit data: 1) Register at https://otd.delhi.gov.in/ "
                    "2) Request an API Key for Real Time Data. 3) Set DELHI_OTD_API_KEY in your .env file or environment."
                )
            }
