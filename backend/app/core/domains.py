from app.core.mailcow import MailcowClient
from app.db import get_db, dict_from_row
from typing import Optional

class DomainService:
    def __init__(self, mailcow: Optional[MailcowClient] = None):
        # Defaults to the globally configured Mailcow instance; pass an
        # explicit client (e.g. built from a job's own mailcow_url/api_key)
        # to target a different instance instead.
        self.mailcow = mailcow or MailcowClient()
    
    def ensure_domain_exists(self, domain: str, tenant_id: int) -> bool:
        """Ensure domain exists in Mailcow. If not, create it."""
        # Check if domain is already tracked in our database
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM domains WHERE domain = ? AND tenant_id = ?
        """, (domain, tenant_id))
        
        existing_domain = cursor.fetchone()
        
        # If we already created it, return success
        if existing_domain and dict_from_row(existing_domain).get("created_in_mailcow"):
            conn.close()
            return True
        
        # Check if domain exists in Mailcow
        if not self.mailcow.check_domain_exists(domain):
            # Create domain in Mailcow
            try:
                self.mailcow.create_domain(domain)
            except Exception as e:
                conn.close()
                raise Exception(f"Failed to create domain in Mailcow: {str(e)}")
        
        # Add domain to our database
        if existing_domain:
            # Update existing record
            cursor.execute("""
                UPDATE domains SET created_in_mailcow = 1 WHERE domain = ? AND tenant_id = ?
            """, (domain, tenant_id))
        else:
            # Create new record
            cursor.execute("""
                INSERT INTO domains (tenant_id, domain, created_in_mailcow)
                VALUES (?, ?, 1)
            """, (tenant_id, domain))
        
        conn.commit()
        conn.close()
        return True
    
    def get_domain_by_name(self, domain: str, tenant_id: int) -> Optional[dict]:
        """Get domain record from database."""
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM domains WHERE domain = ? AND tenant_id = ?
        """, (domain, tenant_id))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return dict_from_row(row)
        return None
