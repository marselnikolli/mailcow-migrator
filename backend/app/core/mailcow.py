import requests
from typing import Optional
from app.config import settings

class MailcowClient:
    def __init__(self, base_url: str = None, api_key: str = None):
        self.base_url = base_url or settings.MAILCOW_URL
        self.api_key = api_key or settings.MAILCOW_API_KEY
        self.headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json"
        }
    
    def _make_request(self, method: str, endpoint: str, data: Optional[dict] = None) -> dict:
        """Make API request to Mailcow."""
        url = f"{self.base_url}/api/v1/{endpoint}"
        try:
            if method == "GET":
                response = requests.get(url, headers=self.headers)
            elif method == "POST":
                response = requests.post(url, headers=self.headers, json=data)
            elif method == "PUT":
                response = requests.put(url, headers=self.headers, json=data)
            elif method == "DELETE":
                response = requests.delete(url, headers=self.headers)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            return response.json() if response.text else {}
        except requests.RequestException as e:
            raise Exception(f"Mailcow API error: {str(e)}")
    
    def create_mailbox(self, email: str, password: str) -> bool:
        """Create a mailbox in Mailcow."""
        domain = email.split("@")[1]
        local_part = email.split("@")[0]
        
        data = {
            "local_part": local_part,
            "domain": domain,
            "password": password,
            "password2": password,
            "quota": 0
        }
        
        try:
            result = self._make_request("POST", "add/mailbox", data)
            return True
        except Exception as e:
            raise Exception(f"Failed to create mailbox: {str(e)}")
    
    def check_mailbox_exists(self, email: str) -> bool:
        """Check if mailbox exists in Mailcow."""
        try:
            result = self._make_request("GET", f"get/mailbox/{email}")
            return True
        except Exception:
            return False
    
    def create_domain(self, domain: str) -> bool:
        """Create a domain in Mailcow."""
        data = {
            "domain": domain,
            "description": f"Domain: {domain}"
        }
        
        try:
            result = self._make_request("POST", "add/domain", data)
            return True
        except Exception as e:
            raise Exception(f"Failed to create domain: {str(e)}")
    
    def check_domain_exists(self, domain: str) -> bool:
        """Check if domain exists in Mailcow."""
        try:
            result = self._make_request("GET", f"get/domain/{domain}")
            return True
        except Exception:
            return False
